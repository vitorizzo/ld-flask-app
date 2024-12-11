import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Carica la configurazione dal file .env
load_dotenv()
DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING")

# Crea un engine globale
engine = create_engine(DB_CONNECTION_STRING, echo=False)

def execute_query(query, params=None):
    """
    Esegue una query generica sul database.
    :param query: La query SQL da eseguire.
    :param params: Parametri opzionali per la query.
    :return: Risultato della query.
    """
    try:
        with engine.connect() as connection:
            if params:
                result = connection.execute(text(query), params)
            else:
                result = connection.execute(text(query))
            return result.fetchall()
    except Exception as e:
        print(f"Errore nell'esecuzione della query: {e}")
        return None

def insert_data(query, params):
    """
    Inserisce dati nel database.
    :param query: La query SQL di INSERT.
    :param params: Parametri per la query.
    :return: True se l'inserimento è riuscito, False altrimenti.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text(query), params)
        return True
    except Exception as e:
        print(f"Errore nell'inserimento dei dati: {e}")
        return False

def update_data(query, params):
    """
    Aggiorna dati nel database.
    :param query: La query SQL di UPDATE.
    :param params: Parametri per la query.
    :return: True se l'aggiornamento è riuscito, False altrimenti.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text(query), params)
        return True
    except Exception as e:
        print(f"Errore nell'aggiornamento dei dati: {e}")
        return False
