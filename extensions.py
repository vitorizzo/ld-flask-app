from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from tools.log_utils import get_logger
from sqlalchemy import MetaData

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)

logger = get_logger('extensions')

logger.info("Inizializzazione estensione SQLAlchemy")
db = SQLAlchemy(metadata=metadata)

logger.info("Inizializzazione estensione Mail")
mail = Mail()


