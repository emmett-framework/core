use pyo3::{IntoPyObjectExt, prelude::*};
use ring::pbkdf2 as _pbkdf2;
use std::num::NonZeroU32;

#[inline]
fn pbkdf2(
    py: Python,
    data: &[u8],
    salt: &[u8],
    rounds: u32,
    klen: u32,
    hash_algo: _pbkdf2::Algorithm,
) -> PyResult<PyObject> {
    let mut vdata = vec![0u8; klen as usize];
    py.allow_threads(|| {
        let ret: &mut [u8] = &mut vdata;
        _pbkdf2::derive(hash_algo, NonZeroU32::new(rounds).unwrap(), salt, data, ret);
        ret
    })
    .into_py_any(py)
}

#[pyfunction]
#[pyo3(signature = (data, salt, rounds, klen))]
fn pbkdf2_sha1(py: Python, data: &[u8], salt: &[u8], rounds: u32, klen: u32) -> PyResult<PyObject> {
    pbkdf2(py, data, salt, rounds, klen, _pbkdf2::PBKDF2_HMAC_SHA1)
}

#[pyfunction]
#[pyo3(signature = (data, salt, rounds, klen))]
fn pbkdf2_sha256(py: Python, data: &[u8], salt: &[u8], rounds: u32, klen: u32) -> PyResult<PyObject> {
    pbkdf2(py, data, salt, rounds, klen, _pbkdf2::PBKDF2_HMAC_SHA256)
}

#[pyfunction]
#[pyo3(signature = (data, salt, rounds, klen))]
fn pbkdf2_sha384(py: Python, data: &[u8], salt: &[u8], rounds: u32, klen: u32) -> PyResult<PyObject> {
    pbkdf2(py, data, salt, rounds, klen, _pbkdf2::PBKDF2_HMAC_SHA384)
}

#[pyfunction]
#[pyo3(signature = (data, salt, rounds, klen))]
fn pbkdf2_sha512(py: Python, data: &[u8], salt: &[u8], rounds: u32, klen: u32) -> PyResult<PyObject> {
    pbkdf2(py, data, salt, rounds, klen, _pbkdf2::PBKDF2_HMAC_SHA512)
}

pub(crate) fn init_pymodule(module: &Bound<PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(pbkdf2_sha1, module)?)?;
    module.add_function(wrap_pyfunction!(pbkdf2_sha256, module)?)?;
    module.add_function(wrap_pyfunction!(pbkdf2_sha384, module)?)?;
    module.add_function(wrap_pyfunction!(pbkdf2_sha512, module)?)?;

    Ok(())
}
