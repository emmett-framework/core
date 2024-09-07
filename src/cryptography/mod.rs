use pyo3::prelude::*;

mod ciphers;
mod kdf;

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    ciphers::init_pymodule(module)?;
    kdf::init_pymodule(module)?;

    Ok(())
}
