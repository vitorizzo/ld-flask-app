from celery import Celery
from tools.app_factory import create_app
from tools.log_utils import get_logger

logger = get_logger('main')

logger.info("Creazione dell'app Flask per Celery...")
flask_app = create_app()

logger.info("Inizializzazione di Celery...")
celery = Celery(
    flask_app.import_name,
    broker=flask_app.config['CELERY_BROKER_URL'],
    backend=flask_app.config['CELERY_RESULT_BACKEND']
)

logger.info("Caricamento configurazione da config.celeryconfig...")
celery.config_from_object('config.celeryconfig')


class FlaskContextTask(celery.Task):
    def __call__(self, *args, **kwargs):
        logger.info(f"Esecuzione task Celery: {self.name}")
        with flask_app.app_context():
            result = super().__call__(*args, **kwargs)
            logger.info(f"Task completato: {self.name}")
            return result


celery.Task = FlaskContextTask

logger.info("Autodiscovery dei task Celery...")
celery.autodiscover_tasks(['config.task.py'])

logger.info("Celery pronto.")
