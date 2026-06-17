"""Rolling file log so on-device issues can be diagnosed.

Writes to ``profiles/allyoptimizer.log`` (rotated, capped) and also echoes to
the console when running from source. Everything is best-effort — logging never
raises into the app.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from .paths import PROFILES_DIR

LOG_FILE = os.path.join(PROFILES_DIR, "allyoptimizer.log")
_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    logger = logging.getLogger("allyoptimizer")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s")
    try:
        os.makedirs(PROFILES_DIR, exist_ok=True)
        fh = RotatingFileHandler(LOG_FILE, maxBytes=512_000, backupCount=2,
                                 encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    try:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    except Exception:
        pass
    logger.propagate = False
    _logger = logger
    return logger
