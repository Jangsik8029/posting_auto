"""Blog automation package."""
import logging
import os

_LOG_LEVEL = os.getenv("BLOGBOT_LOG_LEVEL", "INFO").upper()
_root = logging.getLogger("blogbot")
if not _root.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    )
    _root.addHandler(handler)
    _root.setLevel(_LOG_LEVEL)
    _root.propagate = False
