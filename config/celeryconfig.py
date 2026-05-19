from celery.schedules import crontab
import os
from tools.log_utils import get_logger

logger = get_logger('celeryconfig')

broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
result_backend = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
broker_connection_retry_on_startup = True

logger.info(f"Configurazione Celery: broker_url={broker_url}, result_backend={result_backend}")

beat_schedule = {
    'import-articoli': {
        'task': 'config.tasks.import_articoli_task',
        'schedule': crontab(hour='4', minute='0'),
    },
    'import-giacenze': {
        'task': 'config.tasks.import_giacenze_task',
        'schedule': crontab(hour='4', minute='10'),
    },
    'import-barcode': {
        'task': 'config.tasks.import_barcode_task',
        'schedule': crontab(hour='4', minute='20'),
    },
    'import-anagrafiche': {
        'task': 'config.tasks.import_anagrafiche_task',
        'schedule': crontab(hour='4', minute='30'),
    },
}

timezone = 'Europe/Rome'
logger.info("Scheduler Celery (beat) configurato con 4 task giornalieri.")
