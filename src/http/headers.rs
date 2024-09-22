use anyhow::Result;
use mime::Mime;

#[inline]
pub(crate) fn get_content_type(header_value: &str) -> Result<String> {
    let mime: Mime = header_value.parse()?;
    Ok(mime.essence_str().to_owned())
}
