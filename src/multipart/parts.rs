use anyhow::Result;
use http::header::{self, HeaderMap};
use pyo3::{exceptions::PyStopIteration, prelude::*, types::PyBytes};
use std::{
    fs::File,
    io::{BufRead, BufReader, Read},
    path::PathBuf,
    sync::Mutex,
};
use textnonce::TextNonce;

use super::{
    errors::{error_io, error_parsing},
    utils::get_mime_param_encoded,
};
use crate::http::headers::get_content_type;

pub(super) enum Node {
    Part(Part),
    File(FilePart),
}

pub(super) struct Part {
    pub name: String,
    pub value: Vec<u8>,
}
impl Part {
    pub fn new(headers: HeaderMap, encoding: &str) -> Result<Self> {
        let cd = headers
            .get(header::CONTENT_DISPOSITION)
            .ok_or::<anyhow::Error>(error_parsing!("missing content disposition"))?;
        let name = get_mime_param_encoded(cd, "name", encoding)?
            .ok_or::<anyhow::Error>(error_parsing!("missing name field"))?;

        Ok(Self {
            name,
            value: Vec::new(),
        })
    }
}

pub(super) struct FilePart {
    pub headers: HeaderMap,
    pub name: String,
    filename: Option<String>,
    path: PathBuf,
    pub file: Option<File>,
    pub size: Option<usize>,
    tempdir: Option<PathBuf>,
}

impl FilePart {
    pub fn new(headers: HeaderMap, encoding: &str) -> Result<FilePart> {
        let cd = headers
            .get(header::CONTENT_DISPOSITION)
            .ok_or::<anyhow::Error>(error_parsing!("missing content disposition"))?;
        let name = get_mime_param_encoded(cd, "name", encoding)?
            .ok_or::<anyhow::Error>(error_parsing!("missing name field"))?;
        let filename = get_mime_param_encoded(cd, "filename", encoding)?;
        let mut path = tempfile::Builder::new().prefix("mime_multipart").tempdir()?.into_path();
        let tempdir = Some(path.clone());
        path.push(TextNonce::sized_urlsafe(32).unwrap().into_string());

        let file = File::create(path.clone())?;

        Ok(FilePart {
            headers,
            name,
            filename,
            path,
            file: Some(file),
            size: None,
            tempdir,
        })
    }

    #[inline]
    pub fn filename(&self) -> Option<String> {
        self.filename.clone()
    }

    #[inline]
    pub fn content_type(&self) -> Result<Option<String>> {
        if let Some(cd) = self.headers.get(header::CONTENT_TYPE) {
            return Ok(Some(get_content_type(cd.to_str()?)?));
        }
        Ok(None)
    }

    #[inline]
    pub fn content_length(&self) -> Option<u64> {
        if let Some(cl) = self.headers.get(header::CONTENT_LENGTH) {
            return cl.to_str().unwrap_or("0").parse::<u64>().map(Some).unwrap_or(None);
        }
        None
    }
}

impl Drop for FilePart {
    fn drop(&mut self) {
        if self.tempdir.is_some() {
            let _ = std::fs::remove_file(&self.path);
            let _ = std::fs::remove_dir(self.tempdir.as_ref().unwrap());
        }
    }
}

#[pyclass(module = "emmett_core._emmett_core", frozen)]
pub(super) struct FilePartReader {
    inner: FilePart,
    reader: Mutex<BufReader<File>>,
    size: u64,
}

impl FilePartReader {
    pub fn new(mut inner: FilePart) -> Result<Self> {
        drop(inner.file.take().expect("uninitialized file part"));
        let file = File::open(inner.path.clone()).map_err::<anyhow::Error, _>(|_| error_io!())?;
        let size = file.metadata().unwrap().len();
        let reader = Mutex::new(BufReader::with_capacity(4096, file));
        Ok(Self { inner, reader, size })
    }

    #[inline]
    fn read_chunk(&self, size: usize) -> Result<Vec<u8>> {
        let mut guard = self.reader.lock().unwrap();
        let mut buf = vec![0; size];
        let mut len_read = 0;

        while len_read < size {
            guard.fill_buf()?;
            let rsize = guard.read(&mut buf[len_read..])?;
            if rsize == 0 {
                break;
            }
            len_read += rsize;
        }
        if len_read < size {
            buf.drain(len_read..);
        }
        Ok(buf)
    }

    fn read_all(&self) -> Result<Vec<u8>> {
        let mut guard = self.reader.lock().unwrap();

        guard.fill_buf()?;
        let mut buf = Vec::new();
        guard.read_to_end(&mut buf)?;
        Ok(buf)
    }
}

#[pymethods]
impl FilePartReader {
    #[getter(content_type)]
    fn get_content_type(&self) -> Option<String> {
        self.inner.content_type().unwrap_or(None)
    }

    #[getter(content_length)]
    fn get_content_length(&self) -> u64 {
        if let Some(v) = self.inner.content_length() {
            return v;
        }
        self.size
    }

    #[getter(filename)]
    fn get_filename(&self) -> Option<String> {
        self.inner.filename()
    }

    #[pyo3(signature = (size = None))]
    fn read<'p>(&self, py: Python<'p>, size: Option<usize>) -> Result<Bound<'p, PyBytes>> {
        let buf = match size {
            Some(size) => self.read_chunk(size),
            None => self.read_all(),
        }?;
        Ok(PyBytes::new(py, &buf[..]))
    }

    fn __iter__(pyself: PyRef<Self>) -> PyRef<Self> {
        pyself
    }

    fn __next__<'p>(&self, py: Python<'p>) -> Result<Bound<'p, PyBytes>> {
        let buf = self.read_chunk(4096)?;
        if buf.is_empty() {
            return Err(PyStopIteration::new_err(py.None()).into());
        }
        Ok(PyBytes::new(py, &buf[..]))
    }
}
