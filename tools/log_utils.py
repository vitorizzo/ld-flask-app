import json
from functools import wraps
import logging
from config.paths_config import LOGS_FOLDER
from logging.handlers import RotatingFileHandler


def log_task(logger):
    def decorator(task_func):
        @wraps(task_func)
        def wrapper(*args, **kwargs):
            logger.info(f">>> Avvio task: {task_func.__name__}")
            try:
                result = task_func(*args, **kwargs)

                # Proviamo a trasformare il risultato in stringa per il log
                try:
                    loggable_result = json.dumps(result) if isinstance(result, (dict, list)) else str(result)
                except Exception:
                    loggable_result = "<Non serializzabile>"

                logger.info(f"✅ Task completato: {task_func.__name__} - Risultato: {loggable_result}")
                return result
            except Exception as e:
                logger.exception(f"❌ Errore nel task {task_func.__name__}: {e}")
                raise
        return wrapper
    return decorator


def debug_loggers():
    print("\n🛠  LOGGERS ATTIVI:")
    logger_dict = logging.Logger.manager.loggerDict

    for name, logger in logger_dict.items():
        if isinstance(logger, logging.Logger):
            print(f"\n🔹 Logger: '{name}'")
            print(f"    Livello: {logging.getLevelName(logger.level)}")
            print(f"    Handlers ({len(logger.handlers)}): ")
            for handler in logger.handlers:
                print(f"      - {handler.__class__.__name__}")
                if hasattr(handler, 'baseFilename'):
                    print(f"        ↳ scrive su: {handler.baseFilename}")
                else:
                    print("        ↳ handler senza file associato")

    root_logger = logging.getLogger()
    print(f"\n🌐 Root Logger: ")
    print(f"    Livello: {logging.getLevelName(root_logger.level)}")
    for handler in root_logger.handlers:
        print(f"      - {handler.__class__.__name__}")
        if hasattr(handler, 'baseFilename'):
            print(f"        ↳ scrive su: {handler.baseFilename}")


class Utf8RotatingFileHandler(RotatingFileHandler):
    def _open(self):
        return open(self.baseFilename, self.mode, encoding='utf-8')  # Forza UTF-8


class AutoFlushRotatingFileHandler(RotatingFileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()


def get_logger(name, level=logging.DEBUG, also_main_log=True):
    import os, inspect

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Se il logger è già configurato, restituisci subito
    if logger.handlers:
        return logger

    os.makedirs(LOGS_FOLDER, exist_ok=True)

    # Handler per il file specifico del modulo
    log_file = os.path.join(LOGS_FOLDER, f"{name}.log")
    file_handler = AutoFlushRotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024, backupCount=5, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    # Handler per il file main.log se richiesto
    if also_main_log and name != 'main':
        main_log_file = os.path.join(LOGS_FOLDER, "main.log")
        main_handler = AutoFlushRotatingFileHandler(main_log_file, maxBytes=1048576, backupCount=3, encoding='utf-8')
        main_handler.setFormatter(formatter)
        main_handler.setLevel(level)
        logger.addHandler(main_handler)

    caller = inspect.stack()[1].filename
    # print(f"🛠 Logger '{name}' creato da: {caller}")

    return logger
