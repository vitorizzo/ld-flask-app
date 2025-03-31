import logging
import os
from logging.handlers import RotatingFileHandler

def get_logger(name, level=logging.DEBUG, log_dir="logs"):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{name}.log")
        handler = RotatingFileHandler(log_file, maxBytes=1048576, backupCount=3, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        handler.setLevel(level)
        logger.addHandler(handler)

    return logger

logger = get_logger("test_log")
logger.debug("🔍 Questo è un messaggio di test DEBUG")
logger.info("ℹ️ Questo è un messaggio INFO")
logger.warning("⚠️ Questo è un messaggio WARNING")
logger.error("❌ Questo è un messaggio ERROR")
