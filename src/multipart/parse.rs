use anyhow::Result;
use buf_read_ext::BufReadExt;
use http::{
    HeaderName, HeaderValue,
    header::{self, HeaderMap},
};
use mime::{self, Mime};
use pyo3::{IntoPyObjectExt, exceptions::PyStopIteration, prelude::*, types::PyBytes};
use std::{
    borrow::Cow,
    collections::VecDeque,
    io::{BufRead, Cursor, Read, Write},
    mem,
    sync::Mutex,
};

use super::{
    errors::{error_parsing, error_size, error_state},
    parts::{FilePart, FilePartReader, Node, Part},
    utils::charset_decode,
};

enum MultiPartParserState {
    Clean,
    Termination,
    Headers,
    Value(Part),
    File(FilePart),
    Skip,
    Consumed,
}

impl Default for MultiPartParserState {
    fn default() -> Self {
        Self::Clean
    }
}

struct MultiPartParser {
    boundaries: (Vec<u8>, Vec<u8>, Vec<u8>),
    encoding: String,
    max_part_size: usize,
    state: MultiPartParserState,
    buffer: Vec<u8>,
    bufshift: usize,
    read_size: usize,
    stack: VecDeque<Node>,
}

impl MultiPartParser {
    fn new(boundaries: (Vec<u8>, Vec<u8>, Vec<u8>), encoding: String, max_part_size: usize) -> Self {
        Self {
            boundaries,
            encoding,
            max_part_size,
            state: MultiPartParserState::Clean,
            buffer: Vec::new(),
            bufshift: 0,
            read_size: 0,
            stack: VecDeque::new(),
        }
    }

    fn parse_chunk<T>(&mut self, reader: &mut Cursor<T>) -> Result<()>
    where
        T: AsRef<[u8]>,
    {
        macro_rules! buffered_read {
            ($boundary:expr) => {{
                let peeker = reader.fill_buf()?;
                if peeker.is_empty() {
                    return Ok(());
                }

                // if the chunk is not long enough to check for boundary, buffer
                if (peeker.len() + self.buffer.len()) < $boundary.len() {
                    reader.read_to_end(&mut self.buffer)?;
                    return Ok(());
                }

                let (readn, found) = if self.buffer.is_empty() {
                    reader.stream_until_token($boundary, &mut self.buffer)?
                } else {
                    // we buffered previous contents, chain the two reads
                    let mut buf = Vec::new();
                    let mut chain = self.buffer.chain(&mut *reader);
                    let ret = chain.stream_until_token($boundary, &mut buf)?;
                    self.buffer.truncate(0);
                    self.buffer.extend(buf);
                    ret
                };
                if !found {
                    let bdiff = self.buffer.len() + self.bufshift;
                    if bdiff < readn {
                        let shift = readn - bdiff;
                        self.buffer.extend(&$boundary[..self.bufshift + shift]);
                        self.bufshift += shift;
                    } else {
                        self.bufshift = 0;
                    }
                } else {
                    self.bufshift = 0;
                }
                (readn, found)
            }};

            ($boundary:expr, $target:expr) => {{
                let peeker = reader.fill_buf()?;
                if peeker.is_empty() {
                    return Ok(());
                }

                // if the chunk is not long enough to check for boundary, buffer
                if (peeker.len() + self.buffer.len()) < $boundary.len() {
                    reader.read_to_end(&mut self.buffer)?;
                    return Ok(());
                }

                let (readn, found) = if self.buffer.is_empty() {
                    reader.stream_until_token($boundary, $target)?
                } else {
                    // we buffered previous contents, chain the two reads
                    let mut chain = self.buffer.chain(&mut *reader);
                    let ret = chain.stream_until_token($boundary, $target)?;
                    self.buffer.truncate(0);
                    ret
                };
                if !found {
                    // keep incomplete boundary segment in buffer
                    let bdiff = $target.len() + self.bufshift;
                    if bdiff < readn {
                        let shift = readn - bdiff;
                        self.buffer.extend(&$boundary[..self.bufshift + shift]);
                        self.bufshift += shift;
                    } else {
                        self.bufshift = 0;
                    }
                } else {
                    self.bufshift = 0;
                }
                (readn, found)
            }};
        }

        let (lt, ltlt, lt_boundary) = &self.boundaries;

        loop {
            if let MultiPartParserState::Clean = self.state {
                let peeker = reader.fill_buf()?;
                if (self.buffer.len() + peeker.len()) < 2 {
                    self.buffer.extend(peeker);
                    return Ok(());
                }

                // If the next two lookahead characters are '--', parsing is finished.
                let mut buf = vec![0; 2];
                let mut chain = self.buffer.chain(peeker);
                chain.read_exact(&mut buf)?;
                if buf.len() >= 2 && &buf[..2] == b"--" {
                    self.state = MultiPartParserState::Consumed;
                    return Ok(());
                }

                self.state = MultiPartParserState::Termination;
            }

            if let MultiPartParserState::Termination = self.state {
                let (_, found) = buffered_read!(lt);

                if !found {
                    return Ok(());
                }

                self.buffer.truncate(0);
                self.state = MultiPartParserState::Headers;
            }

            if let MultiPartParserState::Headers = self.state {
                let (_, found) = buffered_read!(ltlt);
                if !found {
                    return Ok(());
                }

                // Keep the 2 line terminators as httparse will expect it
                self.buffer.extend(ltlt.iter().copied());

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

                // clean the buffer
                self.buffer.truncate(0);

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

            if let MultiPartParserState::Value(part) = &mut self.state {
                let (read, found) = buffered_read!(lt_boundary, &mut part.value);
                self.read_size += read;
                if self.read_size >= self.max_part_size {
                    return Err(error_size!());
                }

                if !found {
                    return Ok(());
                }

                let state = mem::take(&mut self.state);
                match state {
                    MultiPartParserState::Value(part) => {
                        self.stack.push_back(Node::Part(part));
                        self.read_size = 0;
                    }
                    _ => unreachable!(),
                }
            }

            if let MultiPartParserState::File(filepart) = &mut self.state {
                let mut buf = Vec::new();
                let (read, found) = buffered_read!(lt_boundary, &mut buf);
                filepart
                    .file
                    .as_mut()
                    .expect("uninitialized file part")
                    .write_all(&buf)?;
                filepart.size = Some(filepart.size.unwrap_or(0) + read);

                if !found {
                    return Ok(());
                }

                let state = mem::take(&mut self.state);
                match state {
                    MultiPartParserState::File(mut part) => {
                        // potentially allow py threads?
                        part.file.as_mut().unwrap().flush()?;
                        self.stack.push_back(Node::File(part));
                    }
                    _ => unreachable!(),
                }
            }

            if let MultiPartParserState::Skip = &mut self.state {
                let (_, found) = buffered_read!(lt_boundary);
                if !found {
                    return Ok(());
                }

                mem::take(&mut self.state);
            }
        }
    }
}

#[pyclass(module = "emmett_core._emmett_core", frozen)]
pub(super) struct MultiPartReader {
    boundary: Vec<u8>,
    encoding: String,
    max_part_size: usize,
    inner: Mutex<Option<MultiPartParser>>,
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
            let mut reader = Cursor::new(data);
            return inner.parse_chunk(&mut reader);
        }

        let mut buf = Vec::new();
        let mut reader = Cursor::new(data);
        let (_, found) = reader.stream_until_token(&self.boundary, &mut buf)?;
        if !found {
            return Err(error_parsing!("EOF before first boundary"));
        }

        let read_boundaries = {
            let peeker = reader.fill_buf()?;
            if peeker.len() > 1 && &peeker[..2] == b"\r\n" {
                let mut output = Vec::with_capacity(2 + self.boundary.len());
                output.push(b'\r');
                output.push(b'\n');
                output.extend(self.boundary.clone());
                (vec![b'\r', b'\n'], vec![b'\r', b'\n', b'\r', b'\n'], output)
            } else {
                return Err(error_parsing!("no CrLf after boundary"));
            }
        };
        *guard = Some(MultiPartParser::new(
            read_boundaries,
            self.encoding.clone(),
            self.max_part_size,
        ));
        guard.as_mut().unwrap().parse_chunk(&mut reader)
    }

    fn contents(&self, py: Python) -> Result<Py<MultiPartContentsIter>> {
        let mut guard = self.inner.lock().unwrap();

        if let Some(mut inner) = guard.take() {
            if !matches!(
                inner.state,
                MultiPartParserState::Clean | MultiPartParserState::Consumed
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
