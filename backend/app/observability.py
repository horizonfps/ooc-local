import json
import logging
from logging.handlers import RotatingFileHandler

from app.config import CONFIG_DIR

LOG_PATH = CONFIG_DIR / "logs" / "app.log"

logger = logging.getLogger("ooc")


def setup_logging() -> None:
    if logger.handlers:
        return
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def emit(event: str, **props) -> None:
    logger.info("%s %s", event, json.dumps(props, ensure_ascii=False))
