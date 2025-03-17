from config.celery_app import celery, FlaskContextTask
from tools.importazioni import import_articoli, import_giacenze, import_barcode, import_ps


@celery.task(base=FlaskContextTask)
def import_articoli_task():
    return import_articoli()


@celery.task(base=FlaskContextTask)
def import_ps_task():
    return import_ps()


@celery.task(base=FlaskContextTask)
def import_giacenze_task():
    return import_giacenze()

@celery.task(base=FlaskContextTask)
def import_barcode_task():
    return import_barcode()
