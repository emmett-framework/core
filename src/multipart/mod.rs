use pyo3::prelude::*;

mod errors;
mod parse;
mod parts;
mod utils;

pub(crate) fn init_pymodule(py: Python, module: &Bound<PyModule>) -> PyResult<()> {
    module.add(
        "MultiPartEncodingError",
        py.get_type_bound::<errors::MultiPartEncodingError>(),
    )?;
    module.add("MultiPartIOError", py.get_type_bound::<errors::MultiPartIOError>())?;
    module.add(
        "MultiPartParsingError",
        py.get_type_bound::<errors::MultiPartParsingError>(),
    )?;
    module.add(
        "MultiPartStateError",
        py.get_type_bound::<errors::MultiPartStateError>(),
    )?;
    module.add_class::<parse::MultiPartReader>()?;
    module.add_class::<parse::MultiPartContentsIter>()?;
    module.add_class::<parts::FilePartReader>()?;

    Ok(())
}
