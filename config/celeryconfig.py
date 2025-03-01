from celery.schedules import crontab
import os

broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
result_backend = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

broker_connection_retry_on_startup = True

beat_schedule = {
    'import-articoli': {
        'task': 'config.tasks.import_articoli_task',
        'schedule': crontab(hour='4', minute='0'),  # Ogni giorno alle 4:00
    },
    'import-giacenze': {
        'task': 'config.tasks.import_giacenze_task',
        'schedule': crontab(hour='4', minute='10'),  # Ogni giorno alle 4:10
    },
    'import-barcode': {
        'task': 'config.tasks.import_barcode_task',
        'schedule': crontab(hour='4', minute='20'),  # Ogni giorno alle 4:20
    },
}

timezone = 'Europe/Rome'
