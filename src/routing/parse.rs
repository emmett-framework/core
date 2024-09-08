use anyhow::Result;
use pyo3::{prelude::*, types::PyDate};

#[inline]
pub(super) fn parse_int_arg(py: Python, arg: &str) -> Result<PyObject> {
    let ret = arg.parse::<i32>()?;
    Ok(ret.into_py(py))
}

#[inline]
pub(super) fn parse_float_arg(py: Python, arg: &str) -> Result<PyObject> {
    let ret = arg.parse::<f32>()?;
    Ok(ret.into_py(py))
}

#[inline]
pub(super) fn parse_date_arg(py: Python, arg: &str) -> Result<PyObject> {
    let year = &arg[0..4].parse::<i32>()?;
    let month = &arg[5..7].parse::<u8>()?;
    let day = &arg[8..10].parse::<u8>()?;
    let date = PyDate::new_bound(py, *year, *month, *day)?;
    Ok(date.into_py(py))
}
