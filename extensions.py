from flask_sqlalchemy import SQLAlchemy
from tools.log_utils import get_logger

logger = get_logger('extensions')

logger.info("Inizializzazione estensione SQLAlchemy")
db = SQLAlchemy()