# config/celery_app.py
from celery import Celery
from tools.log_utils import get_logger

logger = get_logger('main')

# Celery instance (NON creare Flask app qui)
celery = Celery(__name__)
celery.flask_app = None  # verrà valorizzata da init_celery()


class FlaskContextTask(celery.Task):
    """Esegue i task dentro app_context() quando la Flask app è disponibile."""
    abstract = True

    def __call__(self, *args, **kwargs):
        app = getattr(celery, "flask_app", None)
        if app is None:
            # fallback: esegui senza contesto (meglio di crashare)
            logger.warning(f"Celery task senza flask_app inizializzata: {self.name}")
            return super().__call__(*args, **kwargs)

        logger.info(f"Esecuzione task Celery: {self.name}")
        with app.app_context():
            result = super().__call__(*args, **kwargs)
            logger.info(f"Task completato: {self.name}")
            return result


def init_celery(app):
    """
    Va chiamata DOPO create_app().
    Collega Celery alla Flask app ed imposta broker/backend/config.
    """
    logger.info("Inizializzazione Celery (post create_app)...")

    celery.flask_app = app

    # Config essenziale
    celery.conf.broker_url = app.config.get("CELERY_BROKER_URL")
    celery.conf.result_backend = app.config.get("CELERY_RESULT_BACKEND")

    # Config aggiuntiva (se esiste)
    celery.config_from_object("config.celeryconfig", silent=True)

    # Assicura che tutti i task usino il contesto Flask
    celery.Task = FlaskContextTask

    # Carica i task (import differito, senza creare loop)
    celery.conf.include = list(set((celery.conf.include or []) + ["config.task"]))

    logger.info("Celery pronto.")
    return celery
