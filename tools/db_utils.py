import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from tools.log_utils import get_logger
# Logger
logger = get_logger('db_utils')

# Carica la configurazione dal file .env
load_dotenv()
DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING")

if not DB_CONNECTION_STRING:
    logger.critical("DB_CONNECTION_STRING non trovata nel file .env!")
    raise ValueError("DB_CONNECTION_STRING non trovata nel file .env!")

# Crea un engine globale
engine = create_engine(DB_CONNECTION_STRING, echo=False)


def execute_query(query, params=None):
    try:
        with engine.connect() as connection:
            logger.debug(f"Eseguo query: {query} | Parametri: {params}")
            result = connection.execute(text(query), params) if params else connection.execute(text(query))
            fetched = result.fetchall()
            logger.debug(f"Risultato: {fetched}")
            return fetched
    except Exception as e:
        logger.exception("Errore nell'esecuzione della query:")
        return None


def insert_data(query, params):
    try:
        with engine.connect() as connection:
            logger.debug(f"Eseguo INSERT: {query} | Parametri: {params}")
            connection.execute(text(query), params)
        return True
    except Exception as e:
        logger.exception("Errore nell'inserimento dei dati:")
        return False


def update_data(query, params):
    try:
        with engine.connect() as connection:
            logger.debug(f"Eseguo UPDATE: {query} | Parametri: {params}")
            connection.execute(text(query), params)
        return True
    except Exception as e:
        logger.exception("Errore nell'aggiornamento dei dati:")
        return False
