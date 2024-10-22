use pyo3::{
    create_exception,
    exceptions::{PyIOError, PyRuntimeError, PyUnicodeDecodeError, PyValueError},
};

create_exception!(
    _emmett_core,
    MultiPartEncodingError,
    PyUnicodeDecodeError,
    "MultiPartEncodingError"
);
create_exception!(
    _emmett_core,
    MultiPartParsingError,
    PyValueError,
    "MultiPartParsingError"
);
create_exception!(_emmett_core, MultiPartStateError, PyRuntimeError, "MultiPartStateError");
create_exception!(_emmett_core, MultiPartIOError, PyIOError, "MultiPartIOError");
create_exception!(
    _emmett_core,
    MultiPartExceedingSizeError,
    PyRuntimeError,
    "MultiPartExceedingSizeError"
);

macro_rules! error_encoding {
    () => {
        super::errors::MultiPartEncodingError::new_err("multipart encoding error").into()
    };
}

macro_rules! error_io {
    () => {
        super::errors::MultiPartIOError::new_err("cannot open fd").into()
    };
}

macro_rules! error_parsing {
    ($msg:tt) => {
        super::errors::MultiPartParsingError::new_err($msg).into()
    };
}

macro_rules! error_size {
    () => {
        super::errors::MultiPartExceedingSizeError::new_err("exceeding maximum allowed size").into()
    };
}

macro_rules! error_state {
    () => {
        super::errors::MultiPartStateError::new_err("parsing incomplete").into()
    };
}

pub(crate) use error_encoding;
pub(crate) use error_io;
pub(crate) use error_parsing;
pub(crate) use error_size;
pub(crate) use error_state;
