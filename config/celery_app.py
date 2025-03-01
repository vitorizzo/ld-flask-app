from celery import Celery
from tools.app_factory import create_app

# Crea l'app Flask
flask_app = create_app()

# Inizializza Celery con il nome dell'app e le configurazioni prese dalla Flask app
celery = Celery(
    flask_app.import_name,
    broker=flask_app.config['CELERY_BROKER_URL'],
    backend=flask_app.config['CELERY_RESULT_BACKEND']
)

# Carica la configurazione aggiuntiva per Celery (dal file celeryconfig.py)
celery.config_from_object('config.celeryconfig')


# Definisce una classe Task che esegue il task nel contesto dell'app Flask
class FlaskContextTask(celery.Task):
    def __call__(self, *args, **kwargs):
        with flask_app.app_context():
            return super().__call__(*args, **kwargs)


celery.autodiscover_tasks(['config.task.py'])
