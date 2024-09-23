use pyo3::prelude::*;

pub(crate) mod headers;

#[pyfunction]
fn get_content_type(header_value: &str) -> Option<String> {
    headers::get_content_type(header_value).ok()
}

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(get_content_type, module)?)?;

    Ok(())
}
