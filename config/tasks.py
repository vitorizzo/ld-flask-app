# config/tasks.py
from config.celery_app import celery
from tools.importazioni import (
    import_anagrafiche,
    import_articoli,
    import_estratti_conto_clienti,
    import_giacenze,
    import_poleepo_products,
    import_ps,
    run_import_barcode,
)
from tools.log_utils import log_task, get_logger

logger = get_logger('tasks')
mailing_logger = get_logger('mailing_list')


def _run_locked_import(import_name, task_id, task_name, callback):
    from tools.redis_utils import acquire_import_lock, clear_task_status, release_import_lock

    lock_token = acquire_import_lock(import_name)
    if lock_token is None:
        clear_task_status(task_id)
        logger.info("Import %s non avviato: esecuzione precedente ancora attiva", import_name)
        return {
            "success": True,
            "skipped": True,
            "reason": "previous_run_active",
            "message": f"{task_name}: esecuzione precedente ancora attiva.",
        }
    try:
        return callback()
    finally:
        release_import_lock(import_name, lock_token)


@celery.task(bind=True)
@log_task(logger)
def import_articoli_task(self):
    return _run_locked_import(
        "articles", self.request.id, "Importazione articoli",
        lambda: import_articoli(task_id=self.request.id),
    )


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
    return _run_locked_import(
        "stock", self.request.id, "Importazione giacenze",
        lambda: import_giacenze(task_id=self.request.id),
    )


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
def import_estratti_conto_clienti_task(self):
    return import_estratti_conto_clienti(task_id=self.request.id)


@celery.task(bind=True)
@log_task(logger)
def notify_customer_payment_case_task(self, case_id, notification_kind="created"):
    from tools.customer_payment_notifications import notify_customer_payment_case

    return notify_customer_payment_case(case_id, notification_kind=notification_kind)


@celery.task(bind=True)
@log_task(logger)
def send_administration_payment_link_task(self, delivery_id):
    from tools.administration_payment_links import send_administration_payment_link

    return send_administration_payment_link(delivery_id)


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


@celery.task(bind=True)
@log_task(logger)
def create_weekly_events_social_post_task(self):
    from tools.social_events import create_social_event_post
    return {"post_id": create_social_event_post("week", auto=True).id}


@celery.task(bind=True)
@log_task(logger)
def create_weekend_events_social_post_task(self):
    from tools.social_events import create_social_event_post
    return {"post_id": create_social_event_post("weekend", auto=True).id}


@celery.task(bind=True)
@log_task(mailing_logger)
def send_mailing_campaign_task(self, campaign_id, run_id=None):
    from tools.mailing_list import fail_campaign, send_campaign
    try:
        return send_campaign(campaign_id, run_id=run_id)
    except Exception as exc:
        fail_campaign(campaign_id, exc, run_id=run_id)
        raise


@celery.task(bind=True)
@log_task(mailing_logger)
def dispatch_due_mailing_schedules_task(self):
    from tools.mailing_list import dispatch_due_mailing_schedules
    return dispatch_due_mailing_schedules()


@celery.task(bind=True)
@log_task(logger)
def sync_support_mailbox_task(self, limit=100):
    from tools.support_mailbox import sync_support_mailbox
    return sync_support_mailbox(limit=limit)
