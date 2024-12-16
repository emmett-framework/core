use pyo3::prelude::*;
use std::sync::OnceLock;

mod cryptography;
mod http;
mod multipart;
mod routing;

pub fn get_lib_version() -> &'static str {
    static LIB_VERSION: OnceLock<String> = OnceLock::new();

    LIB_VERSION.get_or_init(|| {
        let version = env!("CARGO_PKG_VERSION");
        version.replace("-alpha", "a").replace("-beta", "b")
    })
}

#[pymodule(gil_used = false)]
fn _emmett_core(py: Python, module: &Bound<PyModule>) -> PyResult<()> {
    module.add("__version__", get_lib_version())?;

    cryptography::init_pymodule(module)?;
    http::init_pymodule(module)?;
    multipart::init_pymodule(py, module)?;
    routing::init_pymodule(module)?;
    Ok(())
}
