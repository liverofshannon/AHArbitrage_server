import os
import re
import glob
import logging
import logging.handlers
from datetime import datetime

LEVELS = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL}

ROOT_DIR = os.environ.get("ROOT_DIR", "/home/harry/data/config")
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
    seq = max_num + 1

    return os.path.join(log_dir, f"AHarbitrage_web_{today}_{seq}.log")


class _NumberedRotatingHandler(logging.handlers.RotatingFileHandler):
    """大小超限时递增编号轮转，而非追加 .1 .2 后缀"""

    def __init__(self, maxBytes=LOG_MAX_BYTES, encoding="utf-8"):
        self._max_bytes = maxBytes
        self._encoding = encoding
        path = _build_log_path()
        super().__init__(path, maxBytes=maxBytes, backupCount=0, encoding=encoding)

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        new_path = _build_log_path()
        self.baseFilename = new_path
        if not self.delay:
            self.stream = self._open()


class Logger:
    def __init__(self, name="app", level=LOG_LEVEL):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(LEVELS.get(level, logging.INFO))
        self._logger.handlers.clear()

        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # 控制台
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        self._logger.addHandler(ch)

        # 文件（自增编号轮转）
        fh = _NumberedRotatingHandler()
        fh.setFormatter(fmt)
        self._logger.addHandler(fh)

    def debug(self, msg):
        self._logger.debug(msg)

    def info(self, msg):
        self._logger.info(msg)

    def warning(self, msg):
        self._logger.warning(msg)

    def error(self, msg):
        self._logger.error(msg)

    def critical(self, msg):
        self._logger.critical(msg)


log = Logger()
