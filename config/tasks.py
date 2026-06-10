# config/tasks.py
from config.celery_app import celery
from tools.importazioni import (
    import_anagrafiche,
    import_articoli,
    import_giacenze,
    import_poleepo_products,
    import_ps,
    run_import_barcode,
)
from tools.log_utils import log_task, get_logger

logger = get_logger('tasks')


@celery.task(bind=True)
@log_task(logger)
def import_articoli_task(self):
    return import_articoli(task_id=self.request.id)


@celery.task(bind=True)
@log_task(logger)
def import_ps_task(self):
    return import_ps(task_id=self.request.id)


@celery.task(bind=True)
@log_task(logger)
def import_poleepo_products_task(self, options=None):
    return import_poleepo_products(task_id=self.request.id, options=options or {})


@celery.task(bind=True)
@log_task(logger)
def import_giacenze_task(self):
    return import_giacenze(task_id=self.request.id)


@celery.task(bind=True)
@log_task(logger)
def import_barcode_task(self):
    return run_import_barcode(task_id=self.request.id)


@celery.task(bind=True)
@log_task(logger)
def import_anagrafiche_task(self):
    return import_anagrafiche(task_id=self.request.id)


@celery.task(bind=True)
@log_task(logger)
def import_poleepo_orders_task(self, options=None):
    from routes.shipping import run_poleepo_import
    try:
        return run_poleepo_import(options or {}, task_id=self.request.id)
    except Exception as exc:
        from tools.redis_utils import status_string, update_task
        update_task(self.request.id, "Import ordini Poleepo", 0, status_string["error"], exc)
        raise


@celery.task(bind=True)
@log_task(logger)
def sync_poleepo_shipments_task(self, options=None):
    from routes.shipping import run_poleepo_sync_shipments
    try:
        return run_poleepo_sync_shipments(options or {}, task_id=self.request.id)
    except Exception as exc:
        from tools.redis_utils import status_string, update_task
        update_task(self.request.id, "Sync spedizioni Poleepo", 0, status_string["error"], exc)
        raise


@celery.task(bind=True)
@log_task(logger)
def refresh_open_shipments_task(self, options=None):
    from routes.shipping import run_refresh_open_shipments
    try:
        return run_refresh_open_shipments(options or {}, task_id=self.request.id)
    except Exception as exc:
        from tools.redis_utils import status_string, update_task
        update_task(self.request.id, "Aggiornamento tracking spedizioni aperte", 0, status_string["error"], exc)
        raise
