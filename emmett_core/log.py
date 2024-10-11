import logging
import os
from logging import Formatter, StreamHandler
from logging.handlers import RotatingFileHandler
from threading import Lock

from .datastructures import sdict


_logger_lock = Lock()

LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}

_def_log_config = sdict(
    production=sdict(
        level="warning", format="[%(asctime)s] %(levelname)s in %(module)s: %(message)s", on_app_debug=False
    )
)
_debug_log_format = "> %(levelname)s in %(module)s [%(pathname)s:%(lineno)d]:\n" + "%(message)s"


def create_logger(app):
    Logger = logging.getLoggerClass()

    class DebugLogger(Logger):
        def getEffectiveLevel(self):
            if self.level == 0 and app.debug:
                return logging.DEBUG
            return Logger.getEffectiveLevel(self)

    class DebugHandlerSTD(StreamHandler):
        def emit(self, record):
            StreamHandler.emit(self, record) if app.debug else None

    class HandlerSTD(StreamHandler):
        def emit(self, record):
            StreamHandler.emit(self, record) if not app.debug else None

    class DebugHandlerRF(RotatingFileHandler):
        def emit(self, record):
            RotatingFileHandler.emit(self, record) if app.debug else None

    class HandlerRF(RotatingFileHandler):
        def emit(self, record):
            RotatingFileHandler.emit(self, record) if not app.debug else None

    #: init the console debug handler
    debug_handler = DebugHandlerSTD()
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(Formatter(_debug_log_format))
    logger = logging.getLogger(app.logger_name)
    #: just in case that was not a new logger, get rid of all the handlers already attached to it
    del logger.handlers[:]
    logger.__class__ = DebugLogger
    logger.addHandler(debug_handler)
    #: load application logging config
    app_logs = app.config.logging
    if not app_logs:
        app_logs = _def_log_config
    for lname, lconf in app_logs.items():
        level = LOG_LEVELS.get(lconf.level or "warning", LOG_LEVELS.get("warning"))
        lformat = lconf.format or _def_log_config.production.format
        if filecfg := lconf.file:
            lfile = os.path.join(app.root_path, "logs", lname + ".log")
            max_size = filecfg.max_size or 5 * 1024 * 1024
            file_no = filecfg.no or 4
            handler_cls = DebugHandlerRF if lconf.on_app_debug else HandlerRF
            handler = handler_cls(lfile, maxBytes=max_size, backupCount=file_no)
        else:
            handler_cls = DebugHandlerSTD if lconf.on_app_debug else HandlerSTD
            handler = handler_cls()
        handler.setLevel(level)
        handler.setFormatter(Formatter(lformat))
        logger.addHandler(handler)
    return logger
