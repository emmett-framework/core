from typing import Any, Dict, Iterator, Optional, Tuple

__version__: str

#: cryptography
def aes128_cfb128_decrypt(data: bytes, key: bytes, nonce: bytes) -> bytes: ...
def aes128_cfb128_encrypt(data: bytes, key: bytes, nonce: bytes) -> bytes: ...
def aes128_cfb8_decrypt(data: bytes, key: bytes, nonce: bytes) -> bytes: ...
def aes128_cfb8_encrypt(data: bytes, key: bytes, nonce: bytes) -> bytes: ...
def aes128_ctr128(data: bytes, key: bytes, nonce: bytes) -> bytes: ...
def aes256_cfb128_decrypt(data: bytes, key: bytes, nonce: bytes) -> bytes: ...
def aes256_cfb128_encrypt(data: bytes, key: bytes, nonce: bytes) -> bytes: ...
def aes256_cfb8_decrypt(data: bytes, key: bytes, nonce: bytes) -> bytes: ...
def aes256_cfb8_encrypt(data: bytes, key: bytes, nonce: bytes) -> bytes: ...
def aes256_ctr128(data: bytes, key: bytes, nonce: bytes) -> bytes: ...
def pbkdf2_sha1(data: bytes, salt: bytes, rounds: int, klen: int) -> bytes: ...
def pbkdf2_sha256(data: bytes, salt: bytes, rounds: int, klen: int) -> bytes: ...
def pbkdf2_sha384(data: bytes, salt: bytes, rounds: int, klen: int) -> bytes: ...
def pbkdf2_sha512(data: bytes, salt: bytes, rounds: int, klen: int) -> bytes: ...

#: routing
class HTTPRouter:
    def add_static_route(
        self, route, path: str, method: str, host: Optional[str] = None, scheme: Optional[str] = None
    ): ...
    def add_re_route(
        self,
        route,
        rule: str,
        rgtmap: Dict[str, str],
        method: str,
        host: Optional[str] = None,
        scheme: Optional[str] = None,
    ): ...
    def match_route_direct(self, method: str, path: str) -> Tuple[Any, Dict[str, Any]]: ...
    def match_route_scheme(self, scheme: str, method: str, path: str) -> Tuple[Any, Dict[str, Any]]: ...
    def match_route_host(self, host: str, method: str, path: str) -> Tuple[Any, Dict[str, Any]]: ...
    def match_route_all(self, host: str, scheme: str, method: str, path: str) -> Tuple[Any, Dict[str, Any]]: ...

class WSRouter:
    def add_static_route(self, route, path: str, host: Optional[str] = None, scheme: Optional[str] = None): ...
    def add_re_route(
        self, route, rule: str, rgtmap: Dict[str, str], host: Optional[str] = None, scheme: Optional[str] = None
    ): ...
    def match_route_direct(self, path: str) -> Tuple[Any, Dict[str, Any]]: ...
    def match_route_scheme(self, scheme: str, path: str) -> Tuple[Any, Dict[str, Any]]: ...
    def match_route_host(self, host: str, path: str) -> Tuple[Any, Dict[str, Any]]: ...
    def match_route_all(self, host: str, scheme: str, path: str) -> Tuple[Any, Dict[str, Any]]: ...

#: http
def get_content_type(header_value: str) -> Optional[str]: ...

#: multipart
class MultiPartReader:
    def __init__(self, content_type_header_value: str, max_part_size: int = 1024 * 1024): ...
    def parse(self, data: bytes): ...
    def contents(self) -> MultiPartContentsIter: ...

class MultiPartContentsIter:
    def __iter__(self) -> Iterator[Tuple[str, bool, Any]]: ...

class FilePartReader:
    content_type: Optional[str]
    content_length: int
    filename: Optional[str]

    def read(self, size: Optional[int] = None) -> bytes: ...
    def __iter__(self) -> Iterator[bytes]: ...

class MultiPartEncodingError(UnicodeDecodeError): ...
class MultiPartExceedingSizeError(RuntimeError): ...
class MultiPartIOError(IOError): ...
class MultiPartParsingError(ValueError): ...
class MultiPartStateError(RuntimeError): ...
