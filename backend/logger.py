import os
import re
import glob
import logging
import logging.handlers
from datetime import datetime
from flask import request, session as flask_session

LEVELS = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL}

ROOT_DIR = os.environ.get("ROOT_DIR", "/home/harry")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB


def _build_log_path():
    today = datetime.now().strftime("%Y-%m-%d")
    log_dir = os.path.join(ROOT_DIR, "log", "web", today)
    os.makedirs(log_dir, exist_ok=True)
    pattern = f"AHarbitrage_web_{today}_*.log"
    existing = glob.glob(os.path.join(log_dir, pattern))
    max_num = 0
    for f in existing:
        m = re.search(rf"AHarbitrage_web_{re.escape(today)}_(\d+)\.log$", os.path.basename(f))
        if m:
            max_num = max(max_num, int(m.group(1)))
    return os.path.join(log_dir, f"AHarbitrage_web_{today}_{max_num + 1}.log")


class _NumberedRotatingHandler(logging.handlers.RotatingFileHandler):
    def __init__(self, maxBytes=LOG_MAX_BYTES, encoding="utf-8"):
        path = _build_log_path()
        super().__init__(path, maxBytes=maxBytes, backupCount=0, encoding=encoding)

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        self.baseFilename = _build_log_path()
        if not self.delay:
            self.stream = self._open()


class Logger:
    def __init__(self, name="app", level=LOG_LEVEL):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(LEVELS.get(level, logging.INFO))
        self._logger.handlers.clear()
        self._name = name

        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)-10s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        self._logger.addHandler(ch)

        fh = _NumberedRotatingHandler()
        fh.setFormatter(fmt)
        self._logger.addHandler(fh)

    def _log(self, level, msg):
        user = flask_session.get("username", "-")
        getattr(self._logger, level)(f"[{user}] {msg}")

    def debug(self, msg):   self._log("debug", msg)
    def info(self, msg):    self._log("info", msg)
    def warning(self, msg): self._log("warning", msg)
    def error(self, msg):   self._log("error", msg)
    def critical(self, msg): self._log("critical", msg)


# 模块级 logger 工厂
def get_logger(name):
    return Logger(name)


log = Logger("app")


def log_request():
    """Flask before_request 钩子：记录每一次请求"""
    log.info(f"{request.method} {request.path}  from {_get_ip()}")


def _get_ip():
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"
