# tools/db_utils.py
import os
from functools import lru_cache

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

from tools.log_utils import get_logger

logger = get_logger("db_utils")


@lru_cache(maxsize=1)
def get_engine():
    """
    Crea e cache-a l'engine SQLAlchemy la prima volta che serve.
    Niente side effects a import-time.
    """
    # carica .env solo quando necessario
    load_dotenv()
    db_conn = os.getenv("DB_CONNECTION_STRING")

    if not db_conn:
        logger.critical("DB_CONNECTION_STRING non trovata nel file .env!")
        raise ValueError("DB_CONNECTION_STRING non trovata nel file .env!")

    return create_engine(db_conn, echo=False)


def execute_query(query, params=None):
    try:
        engine = get_engine()
        with engine.connect() as connection:
            logger.debug(f"Eseguo query: {query} | Parametri: {params}")
            result = connection.execute(text(query), params) if params else connection.execute(text(query))
            fetched = result.fetchall()
            logger.debug(f"Risultato: {fetched}")
            return fetched
    except Exception:
        logger.exception("Errore nell'esecuzione della query:")
        return None


def insert_data(query, params):
    try:
        engine = get_engine()
        with engine.begin() as connection:
            logger.debug(f"Eseguo INSERT: {query} | Parametri: {params}")
            connection.execute(text(query), params)
        return True
    except Exception:
        logger.exception("Errore nell'inserimento dei dati:")
        return False


def update_data(query, params):
    try:
        engine = get_engine()
        with engine.begin() as connection:
            logger.debug(f"Eseguo UPDATE: {query} | Parametri: {params}")
            connection.execute(text(query), params)
        return True
    except Exception:
        logger.exception("Errore nell'aggiornamento dei dati:")
        return False
