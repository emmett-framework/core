use anyhow::Result;
use encoding::{all as encoders, DecoderTrap, Encoding};
use http::HeaderValue;
use mime::Mime;

use super::errors::error_encoding;

#[allow(dead_code)]
#[inline]
pub(super) fn get_mime_param(hv: &HeaderValue, param: &str) -> Result<Option<String>> {
    let hvs = hv.to_str().unwrap_or("");
    let (_ty, params) = hvs.split_once(';').unwrap_or(("", ""));
    let mime: Mime = format!("*/*; {params}").parse()?;
    Ok(mime.get_param(param).map(|v| v.to_string()))
}

#[inline]
pub(super) fn get_mime_param_encoded(hv: &HeaderValue, param: &str, encoding: &str) -> Result<Option<String>> {
    let hvs = charset_decode(encoding, hv.as_bytes()).unwrap_or_default();
    let (_ty, params) = hvs.split_once(';').unwrap_or(("", ""));
    let mime: Mime = format!("*/*; {params}").parse()?;
    Ok(mime.get_param(param).map(|v| v.to_string()))
}

pub(super) fn charset_decode(charset: &str, bytes: &[u8]) -> Result<String> {
    match charset {
        "us-ascii" => encoders::ASCII.decode(bytes, DecoderTrap::Strict),
        "iso-8859-1" => encoders::ISO_8859_1.decode(bytes, DecoderTrap::Strict),
        "iso-8859-2" => encoders::ISO_8859_2.decode(bytes, DecoderTrap::Strict),
        "iso-8859-3" => encoders::ISO_8859_3.decode(bytes, DecoderTrap::Strict),
        "iso-8859-4" => encoders::ISO_8859_4.decode(bytes, DecoderTrap::Strict),
        "iso-8859-5" => encoders::ISO_8859_5.decode(bytes, DecoderTrap::Strict),
        "iso-8859-6" => encoders::ISO_8859_6.decode(bytes, DecoderTrap::Strict),
        "iso-8859-7" => encoders::ISO_8859_7.decode(bytes, DecoderTrap::Strict),
        "iso-8859-8" => encoders::ISO_8859_8.decode(bytes, DecoderTrap::Strict),
        "iso-8859-10" => encoders::ISO_8859_10.decode(bytes, DecoderTrap::Strict),
        "euc-jp" => encoders::EUC_JP.decode(bytes, DecoderTrap::Strict),
        "iso-2022-jp" => encoders::ISO_2022_JP.decode(bytes, DecoderTrap::Strict),
        "big5" => encoders::BIG5_2003.decode(bytes, DecoderTrap::Strict),
        "koi8-r" => encoders::KOI8_R.decode(bytes, DecoderTrap::Strict),
        "utf-8" => encoders::UTF_8.decode(bytes, DecoderTrap::Strict),
        _ => Err("no encoder".into()),
    }
    .map_err(|_err| error_encoding!())
}
