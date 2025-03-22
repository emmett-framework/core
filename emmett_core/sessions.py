from __future__ import annotations

import hashlib
import os
import pickle
import tempfile
import time
import zlib
from typing import Any, Dict, Optional, Type, TypeVar
from uuid import uuid4

from .cryptography import symmetric as crypto_symmetric
from .datastructures import sdict
from .pipeline import Pipe


class SessionData(sdict):
    __slots__ = ("__sid", "__hash", "__expires", "__dump")

    def __init__(self, initial=None, sid=None, expires=None):
        sdict.__init__(self, initial or ())
        object.__setattr__(self, "_SessionData__dump", pickle.dumps(sdict(self)))
        h = hashlib.md5(self._dump).hexdigest()  # noqa: S324
        object.__setattr__(self, "_SessionData__sid", sid)
        object.__setattr__(self, "_SessionData__hash", h)
        object.__setattr__(self, "_SessionData__expires", expires)

    @property
    def _sid(self):
        return self.__sid

    @property
    def _modified(self):
        dump = pickle.dumps(sdict(self))
        h = hashlib.md5(dump).hexdigest()  # noqa: S324
        if h != self.__hash:
            object.__setattr__(self, "_SessionData__dump", dump)
            return True
        return False

    @property
    def _expiration(self):
        return self.__expires

    @property
    def _dump(self):
        # note: self.__dump is updated only on _modified call
        return self.__dump

    def _expires_after(self, value):
        object.__setattr__(self, "_SessionData__expires", value)


class SessionPipe(Pipe):
    __slots__ = ["current"]

    def __init__(
        self,
        current,
        expire: int = 3600,
        secure: bool = False,
        samesite: str = "Lax",
        domain: Optional[str] = None,
        cookie_name: Optional[str] = None,
        cookie_data: Optional[Dict[str, Any]] = None,
    ):
        self.current = current
        self.expire = expire
        self.secure = secure
        self.samesite = samesite
        self.domain = domain
        self.cookie_name = cookie_name or f"emt_session_data_{current.app.name}"
        self.cookie_data = cookie_data or {}

    def _load_session(self, wrapper):
        raise NotImplementedError

    def _new_session(self) -> SessionData:
        raise NotImplementedError

    def _pack_session(self, expiration: int):
        self.current.response.cookies[self.cookie_name] = self._session_cookie_data()
        cookie_data = self.current.response.cookies[self.cookie_name]
        cookie_data["path"] = "/"
        cookie_data["expires"] = expiration
        cookie_data["samesite"] = self.samesite
        if self.secure:
            cookie_data["secure"] = True
        if self.domain is not None:
            cookie_data["domain"] = self.domain
        for key, val in self.cookie_data.items():
            cookie_data[key] = val

    def _close_session(self):
        expiration = self.current.session._expiration or self.expire
        self._pack_session(expiration)

    def _session_cookie_data(self) -> str:
        raise NotImplementedError

    async def open_request(self):
        if self.cookie_name in self.current.request.cookies:
            self.current.session = self._load_session(self.current.request)
        if not self.current.session:
            self.current.session = self._new_session()

    async def open_ws(self):
        if self.cookie_name in self.current.websocket.cookies:
            self.current.session = self._load_session(self.current.websocket)
        if not self.current.session:
            self.current.session = self._new_session()

    async def close_request(self):
        if getattr(self.current.response, "_done", False):
            return
        self._close_session()

    def on_stream(self):
        self.current.response._done = True
        self._close_session()

    def clear(self):
        pass


class CookieSessionPipe(SessionPipe):
    def __init__(
        self,
        current,
        key,
        expire=3600,
        secure=False,
        samesite="Lax",
        domain=None,
        cookie_name=None,
        cookie_data=None,
        compression_level=0,
    ):
        super().__init__(
            current,
            expire=expire,
            secure=secure,
            samesite=samesite,
            domain=domain,
            cookie_name=cookie_name,
            cookie_data=cookie_data,
        )
        self.key = key
        self.compression_level = compression_level

    def _encrypt_data(self) -> str:
        data = pickle.dumps(sdict(self.current.session))
        if self.compression_level:
            data = zlib.compress(data, self.compression_level)
        return crypto_symmetric.encrypt_b64(data, self.key)

    def _decrypt_data(self, data: str) -> SessionData:
        try:
            ddata = crypto_symmetric.decrypt_b64(data, self.key)
            if self.compression_level:
                ddata = zlib.decompress(ddata)
            rv = pickle.loads(ddata)  # noqa: S301
        except Exception:
            rv = None
        return SessionData(rv, expires=self.expire)

    def _load_session(self, wrapper) -> SessionData:
        cookie_data = wrapper.cookies[self.cookie_name].value
        return self._decrypt_data(cookie_data)

    def _new_session(self) -> SessionData:
        return SessionData(expires=self.expire)

    def _session_cookie_data(self) -> str:
        return self._encrypt_data()

    def clear(self):
        raise NotImplementedError(
            f"{self.__class__.__name__} doesn't support sessions clearing. "
            f"Change the 'key' parameter to invalidate existing ones."
        )


class BackendStoredSessionPipe(SessionPipe):
    def _new_session(self):
        return SessionData(sid=str(uuid4()))

    def _session_cookie_data(self) -> str:
        return self.current.session._sid

    def _load_session(self, wrapper) -> Optional[SessionData]:
        sid = wrapper.cookies[self.cookie_name].value
        data = self._load(sid)
        if data is not None:
            return SessionData(data, sid=sid)
        return None

    def _delete_session(self):
        pass

    def _save_session(self, expiration: int):
        pass

    def _close_session(self):
        if not self.current.session:
            self._delete_session()
            if self.current.session._modified:
                #: if we got here means we want to destroy session definitely
                if self.cookie_name in self.current.response.cookies:
                    del self.current.response.cookies[self.cookie_name]
            return
        expiration = self.current.session._expiration or self.expire
        self._save_session(expiration)
        self._pack_session(expiration)

    def _load(self, sid: str):
        return None


class FileSessionPipe(BackendStoredSessionPipe):
    _fs_transaction_suffix = ".__emt_sess"
    _fs_mode = 0o600

    def __init__(
        self,
        current,
        expire=3600,
        secure=False,
        samesite="Lax",
        domain=None,
        cookie_name=None,
        cookie_data=None,
        filename_template="emt_%s.sess",
    ):
        super().__init__(
            current,
            expire=expire,
            secure=secure,
            samesite=samesite,
            domain=domain,
            cookie_name=cookie_name,
            cookie_data=cookie_data,
        )
        if filename_template.endswith(self._fs_transaction_suffix):
            raise RuntimeError(f"filename templates cannot end with {self._fs_transaction_suffix}")
        self._filename_template = filename_template
        self._path = os.path.join(self.current.app.root_path, "sessions")
        #: create required paths if needed
        if not os.path.exists(self._path):
            os.mkdir(self._path)

    def _delete_session(self):
        fn = self._get_filename(self.current.session._sid)
        try:
            os.unlink(fn)
        except OSError:
            pass

    def _save_session(self, expiration):
        if self.current.session._modified:
            self._store(self.current.session, expiration)

    def _get_filename(self, sid):
        return os.path.join(self._path, self._filename_template % str(sid))

    def _load(self, sid):
        try:
            with open(self._get_filename(sid), "rb") as f:
                exp = pickle.load(f)  # noqa: S301
                val = pickle.load(f)  # noqa: S301
        except IOError:
            return None
        if exp < time.time():
            return None
        return val

    def _store(self, session, expiration):
        fn = self._get_filename(session._sid)
        now = time.time()
        exp = now + expiration
        fd, tmp = tempfile.mkstemp(suffix=self._fs_transaction_suffix, dir=self._path)
        f = os.fdopen(fd, "wb")
        try:
            pickle.dump(exp, f, 1)
            pickle.dump(sdict(session), f, pickle.HIGHEST_PROTOCOL)
        finally:
            f.close()
        try:
            os.rename(tmp, fn)
            os.chmod(fn, self._fs_mode)
        except Exception:
            pass

    def clear(self):
        for element in os.listdir(self._path):
            try:
                os.unlink(os.path.join(self._path, element))
            except Exception:
                pass


class RedisSessionPipe(BackendStoredSessionPipe):
    def __init__(
        self,
        current,
        redis,
        prefix="emtsess:",
        expire=3600,
        secure=False,
        samesite="Lax",
        domain=None,
        cookie_name=None,
        cookie_data=None,
    ):
        super().__init__(
            current,
            expire=expire,
            secure=secure,
            samesite=samesite,
            domain=domain,
            cookie_name=cookie_name,
            cookie_data=cookie_data,
        )
        self.redis = redis
        self.prefix = prefix

    def _delete_session(self):
        self.redis.delete(self.prefix + self.current.session._sid)

    def _save_session(self, expiration):
        if self.current.session._modified:
            self.redis.setex(self.prefix + self.current.session._sid, expiration, self.current.session._dump)
        else:
            self.redis.expire(self.prefix + self.current.session._sid, expiration)

    def _load(self, sid):
        data = self.redis.get(self.prefix + sid)
        return pickle.loads(data) if data else data  # noqa: S301

    def clear(self):
        self.redis.delete(self.prefix + "*")


TSessionPipe = TypeVar("TSessionPipe", bound=SessionPipe)


class SessionManager:
    _pipe: Optional[SessionPipe] = None

    @classmethod
    def _build_pipe(cls, handler_cls: Type[TSessionPipe], *args: Any, **kwargs: Any) -> TSessionPipe:
        raise NotImplementedError

    @classmethod
    def cookies(
        cls,
        key: str,
        expire: int = 3600,
        secure: bool = False,
        samesite: str = "Lax",
        domain: Optional[str] = None,
        cookie_name: Optional[str] = None,
        cookie_data: Optional[Dict[str, Any]] = None,
        compression_level: int = 0,
    ) -> CookieSessionPipe:
        return cls._build_pipe(
            CookieSessionPipe,
            key,
            expire=expire,
            secure=secure,
            samesite=samesite,
            domain=domain,
            cookie_name=cookie_name,
            cookie_data=cookie_data,
            compression_level=compression_level,
        )

    @classmethod
    def files(
        cls,
        expire: int = 3600,
        secure: bool = False,
        samesite: str = "Lax",
        domain: Optional[str] = None,
        cookie_name: Optional[str] = None,
        cookie_data: Optional[Dict[str, Any]] = None,
        filename_template: str = "emt_%s.sess",
    ) -> FileSessionPipe:
        return cls._build_pipe(
            FileSessionPipe,
            expire=expire,
            secure=secure,
            samesite=samesite,
            domain=domain,
            cookie_name=cookie_name,
            cookie_data=cookie_data,
            filename_template=filename_template,
        )

    @classmethod
    def redis(
        cls,
        redis: Any,
        prefix: str = "emtsess:",
        expire: int = 3600,
        secure: bool = False,
        samesite: str = "Lax",
        domain: Optional[str] = None,
        cookie_name: Optional[str] = None,
        cookie_data: Optional[Dict[str, Any]] = None,
    ) -> RedisSessionPipe:
        return cls._build_pipe(
            RedisSessionPipe,
            redis,
            prefix=prefix,
            expire=expire,
            secure=secure,
            samesite=samesite,
            domain=domain,
            cookie_name=cookie_name,
            cookie_data=cookie_data,
        )

    @classmethod
    def clear(cls):
        cls._pipe.clear()
