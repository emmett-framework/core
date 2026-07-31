use anyhow::Result;
use http::{
    HeaderName, HeaderValue,
    header::{self, HeaderMap},
};
use memchr::memmem::Finder;
use mime::{self, Mime};
use pyo3::{IntoPyObjectExt, exceptions::PyStopIteration, prelude::*, types::PyBytes};
use std::{
    borrow::Cow,
    collections::VecDeque,
    io::Write,
    mem,
    sync::{LazyLock, Mutex},
};

use super::{
    errors::{error_parsing, error_size, error_state},
    parts::{FilePart, FilePartReader, Node, Part},
    utils::charset_decode,
};

#[derive(Default)]
enum MultiPartParserState {
    #[default]
    BoundaryTail,
    LineEnd,
    Headers,
    Value(Part),
    File(FilePart),
    Skip,
    Consumed,
}

static FINDER_CRLF: LazyLock<Finder<'static>> = LazyLock::new(|| Finder::new(b"\r\n"));
static FINDER_CRLF2: LazyLock<Finder<'static>> = LazyLock::new(|| Finder::new(b"\r\n\r\n"));

struct Finders {
    delimiter: Finder<'static>,
    crlf: &'static Finder<'static>,
    crlf2: &'static Finder<'static>,
}

struct MultiPartParser {
    finders: Finders,
    encoding: String,
    max_part_size: usize,
    state: MultiPartParserState,
    carry: Vec<u8>,
    buffer: Vec<u8>,
    stack: VecDeque<Node>,
}

fn stream_find(
    carry: &mut Vec<u8>,
    finder: &Finder<'static>,
    data: &[u8],
    sink: &mut dyn FnMut(&[u8]) -> Result<()>,
) -> Result<Option<usize>> {
    let token_len = finder.needle().len();

    if !carry.is_empty() {
        // look for a match starting within carried bytes
        let border_take = std::cmp::min(data.len(), token_len - 1);
        let mut border = Vec::with_capacity(carry.len() + border_take);
        border.extend_from_slice(carry);
        border.extend_from_slice(&data[..border_take]);
        match finder.find(&border) {
            Some(pos) if pos < carry.len() => {
                sink(&carry[..pos])?;
                let consumed = pos + token_len - carry.len();
                carry.clear();
                return Ok(Some(consumed));
            }
            _ => {}
        }
        if data.len() < token_len - 1 {
            // not enough bytes to rule out a token spanning beyond `data`:
            // accumulate, streaming out any decidable excess
            carry.extend_from_slice(data);
            if carry.len() >= token_len {
                let flush = carry.len() - (token_len - 1);
                sink(&carry[..flush])?;
                carry.drain(..flush);
            }
            return Ok(None);
        }
        // the border check covered any match involving carried bytes: flush them
        sink(carry)?;
        carry.clear();
    }

    match finder.find(data) {
        Some(pos) => {
            sink(&data[..pos])?;
            Ok(Some(pos + token_len))
        }
        None => {
            let keep = std::cmp::min(data.len(), token_len - 1);
            sink(&data[..data.len() - keep])?;
            carry.extend_from_slice(&data[data.len() - keep..]);
            Ok(None)
        }
    }
}

impl MultiPartParser {
    fn new(boundary: &[u8], encoding: String, max_part_size: usize) -> Self {
        let mut delimiter = Vec::with_capacity(2 + boundary.len());
        delimiter.extend_from_slice(b"\r\n");
        delimiter.extend_from_slice(boundary);

        Self {
            finders: Finders {
                delimiter: Finder::new(&delimiter).into_owned(),
                crlf: &FINDER_CRLF,
                crlf2: &FINDER_CRLF2,
            },
            encoding,
            max_part_size,
            state: MultiPartParserState::BoundaryTail,
            carry: Vec::new(),
            buffer: Vec::new(),
            stack: VecDeque::new(),
        }
    }

    fn parse_chunk(&mut self, mut data: &[u8]) -> Result<()> {
        loop {
            if data.is_empty() {
                return Ok(());
            }

            match &mut self.state {
                MultiPartParserState::BoundaryTail => {
                    // two lookahead characters decide between a further part and epilogue
                    if self.carry.len() + data.len() < 2 {
                        self.carry.extend_from_slice(data);
                        return Ok(());
                    }
                    let (b0, b1) = match self.carry.len() {
                        0 => (data[0], data[1]),
                        _ => (self.carry[0], data[0]),
                    };
                    if b0 == b'-' && b1 == b'-' {
                        self.state = MultiPartParserState::Consumed;
                        return Ok(());
                    }
                    self.state = MultiPartParserState::LineEnd;
                }

                MultiPartParserState::LineEnd => {
                    match stream_find(&mut self.carry, self.finders.crlf, data, &mut |_| Ok(()))? {
                        Some(consumed) => {
                            data = &data[consumed..];
                            self.state = MultiPartParserState::Headers;
                        }
                        None => return Ok(()),
                    }
                }

                MultiPartParserState::Headers => {
                    let prev_len = self.buffer.len();
                    self.buffer.extend_from_slice(data);
                    let search_from = prev_len.saturating_sub(3);
                    let Some(pos) = self.finders.crlf2.find(&self.buffer[search_from..]) else {
                        return Ok(());
                    };
                    // keep the 2 line terminators as httparse will expect it
                    let headers_end = search_from + pos + 4;
                    let consumed = headers_end - prev_len;
                    self.buffer.truncate(headers_end);

                    let part_headers = {
                        let mut header_memory = [httparse::EMPTY_HEADER; 4];
                        match httparse::parse_headers(&self.buffer, &mut header_memory) {
                            Ok(httparse::Status::Complete((_, raw_headers))) => {
                                let mut headers = HeaderMap::new();
                                for header in raw_headers {
                                    let name = HeaderName::try_from(header.name)?;
                                    let value = HeaderValue::from_bytes(header.value)?;
                                    headers.insert(name, value);
                                }
                                Ok::<HeaderMap, anyhow::Error>(headers)
                            }
                            Ok(httparse::Status::Partial) => Err(error_parsing!("incomplete headers")),
                            Err(_) => Err(error_parsing!("bad headers")),
                        }?
                    };

                    self.buffer.clear();
                    data = &data[consumed..];

                    let mut is_file = false;
                    let mut missing_mime = false;
                    if let Some(cd) = part_headers.get(header::CONTENT_DISPOSITION) {
                        let cds = charset_decode(&self.encoding, cd.as_bytes())?;
                        let cd_params = cds.split_once(';').unwrap_or(("", "")).1;

                        match format!("*/*;{cd_params}").parse::<Mime>() {
                            Ok(mime) => {
                                is_file = mime.get_param("filename").is_some();
                            }
                            Err(_) => {
                                missing_mime = true;
                            }
                        }
                    }

                    match (is_file, missing_mime) {
                        (true, _) => {
                            let filepart = FilePart::new(part_headers, &self.encoding)?;
                            self.state = MultiPartParserState::File(filepart);
                        }
                        (false, true) => {
                            self.state = MultiPartParserState::Skip;
                        }
                        (false, false) => {
                            let part = Part::new(part_headers, &self.encoding)?;
                            self.state = MultiPartParserState::Value(part);
                        }
                    }
                }

                MultiPartParserState::Value(part) => {
                    let value = &mut part.value;
                    let found = stream_find(&mut self.carry, &self.finders.delimiter, data, &mut |bytes| {
                        value.extend_from_slice(bytes);
                        Ok(())
                    })?;
                    if part.value.len() >= self.max_part_size {
                        return Err(error_size!());
                    }

                    match found {
                        Some(consumed) => {
                            data = &data[consumed..];
                            match mem::take(&mut self.state) {
                                MultiPartParserState::Value(part) => self.stack.push_back(Node::Part(part)),
                                _ => unreachable!(),
                            }
                        }
                        None => return Ok(()),
                    }
                }

                MultiPartParserState::File(filepart) => {
                    let file = filepart.file.as_mut().expect("uninitialized file part");
                    let mut written = 0;
                    let found = stream_find(&mut self.carry, &self.finders.delimiter, data, &mut |bytes| {
                        written += bytes.len();
                        file.write_all(bytes).map_err(Into::into)
                    })?;
                    filepart.size = Some(filepart.size.unwrap_or(0) + written);

                    match found {
                        Some(consumed) => {
                            data = &data[consumed..];
                            match mem::take(&mut self.state) {
                                MultiPartParserState::File(mut part) => {
                                    // potentially allow py threads?
                                    part.file.as_mut().unwrap().flush()?;
                                    self.stack.push_back(Node::File(part));
                                }
                                _ => unreachable!(),
                            }
                        }
                        None => return Ok(()),
                    }
                }

                MultiPartParserState::Skip => {
                    match stream_find(&mut self.carry, &self.finders.delimiter, data, &mut |_| Ok(()))? {
                        Some(consumed) => {
                            data = &data[consumed..];
                            self.state = MultiPartParserState::BoundaryTail;
                        }
                        None => return Ok(()),
                    }
                }

                MultiPartParserState::Consumed => return Ok(()),
            }
        }
    }
}

#[pyclass(module = "emmett_core._emmett_core", frozen)]
pub(super) struct MultiPartReader {
    boundary: Vec<u8>,
    encoding: String,
    max_part_size: usize,
    // NOTE: boxed as `Finder` alignment exceeds the one guaranteed by Python's allocator
    inner: Mutex<Option<Box<MultiPartParser>>>,
}

#[pymethods]
impl MultiPartReader {
    #[new]
    #[pyo3(signature = (content_type_header_value, max_part_size = 1024 * 1024))]
    fn new(content_type_header_value: &str, max_part_size: Option<usize>) -> Result<Self> {
        let (boundary, charset) = get_multipart_params(content_type_header_value)?;
        Ok(Self {
            boundary,
            encoding: charset,
            max_part_size: max_part_size.unwrap_or(1024 * 1024),
            inner: Mutex::new(None),
        })
    }

    fn parse(&self, data: Cow<[u8]>) -> Result<()> {
        let mut guard = self.inner.lock().unwrap();

        if let Some(inner) = &mut *guard {
            if matches!(inner.state, MultiPartParserState::Consumed) {
                return Ok(());
            }
            return inner.parse_chunk(&data);
        }

        let Some(pos) = Finder::new(&self.boundary).find(&data) else {
            return Err(error_parsing!("EOF before first boundary"));
        };
        let rest = &data[pos + self.boundary.len()..];
        if rest.len() < 2 || &rest[..2] != b"\r\n" {
            return Err(error_parsing!("no CrLf after boundary"));
        }

        let parser = guard.insert(Box::new(MultiPartParser::new(
            &self.boundary,
            self.encoding.clone(),
            self.max_part_size,
        )));
        parser.parse_chunk(rest)
    }

    fn contents(&self, py: Python) -> Result<Py<MultiPartContentsIter>> {
        let mut guard = self.inner.lock().unwrap();

        if let Some(mut inner) = guard.take() {
            if !matches!(
                inner.state,
                MultiPartParserState::BoundaryTail | MultiPartParserState::Consumed
            ) {
                return Err(error_state!());
            }
            let nodes = mem::take(&mut inner.stack);
            return Ok(Py::new(
                py,
                MultiPartContentsIter {
                    inner: Mutex::new(nodes),
                },
            )?);
        }
        Err(error_state!())
    }
}

#[pyclass(module = "emmett_core._emmett_core", frozen)]
pub(super) struct MultiPartContentsIter {
    inner: Mutex<VecDeque<Node>>,
}

#[pymethods]
impl MultiPartContentsIter {
    fn __iter__(pyself: PyRef<Self>) -> PyRef<Self> {
        pyself
    }

    fn __next__(&self, py: Python) -> PyResult<(String, bool, Py<PyAny>)> {
        let mut guard = self.inner.lock().unwrap();

        if let Some(item) = guard.pop_front() {
            return match item {
                Node::Part(node) => Ok((node.name, false, PyBytes::new(py, &node.value[..]).into_py_any(py)?)),
                Node::File(node) => Ok((
                    node.name.clone(),
                    true,
                    Py::new(py, FilePartReader::new(node)?)?.into_py_any(py)?,
                )),
            };
        }
        Err(PyStopIteration::new_err(py.None()))
    }
}

fn get_multipart_params(content_type_header_value: &str) -> Result<(Vec<u8>, String)> {
    let mime: mime::Mime = content_type_header_value.parse()?;
    if mime.type_() != mime::MULTIPART {
        return Err(error_parsing!("not multipart"));
    }

    if let Some(raw_boundary) = mime.get_param(mime::BOUNDARY) {
        let rbs = raw_boundary.as_str();
        let mut boundary = Vec::with_capacity(2 + rbs.len());
        boundary.extend(b"--".iter().copied());
        boundary.extend(rbs.as_bytes());

        let charset = mime.get_param(mime::CHARSET).map_or("utf-8", |v| v.as_str());
        return Ok((boundary, charset.to_owned()));
    }

    Err(error_parsing!("boundary not specified"))
}
