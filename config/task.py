from config.celery_app import celery, FlaskContextTask
from tools.importazioni import import_articoli, import_giacenze,  import_ps, run_import_barcode
from tools.log_utils import log_task, get_logger

logger = get_logger('tasks')


@celery.task(base=FlaskContextTask, bind=True)
@log_task(logger)
def import_articoli_task(self):
    return import_articoli(task_id=self.request.id)


@celery.task(base=FlaskContextTask, bind=True)
@log_task(logger)
def import_ps_task(self):
    return import_ps(task_id=self.request.id)


@celery.task(base=FlaskContextTask, bind=True)
@log_task(logger)
def import_giacenze_task(self):
    return import_giacenze(task_id=self.request.id)


@celery.task(base=FlaskContextTask, bind=True)
@log_task(logger)
def import_barcode_task(self):
    return run_import_barcode(task_id=self.request.id)
