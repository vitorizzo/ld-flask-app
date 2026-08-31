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
def matrixws_test_poll_task(self, batch_uuid, request_meta=None):
    """Completa in background un test MATRIXWS asincrono senza importare alcun dato."""
    from flask import current_app

    from tools.matrixws_client import MatrixWSConfig, MatrixWSError, wait_for_batch_result
    from tools.redis_utils import clear_task_status, status_string, update_task

    request_meta = dict(request_meta or {})
    service_code = str(request_meta.get("service_code") or "").strip()
    test_label = str(request_meta.get("test_label") or service_code or batch_uuid).strip()
    task_name = f"Test MATRIXWS: {test_label}"
    update_task(self.request.id, task_name, 1, status_string["start"])

    def report_progress(_batch_uuid, elapsed):
        progress = min(95, max(1, int(float(elapsed or 0) / 900 * 94) + 1))
        update_task(self.request.id, task_name, progress, status_string["update"])

    try:
        config = MatrixWSConfig.from_app_config(current_app.config)
        result = wait_for_batch_result(
            config,
            batch_uuid,
            poll_timeout=(5, 60),
            poll_interval=2,
            max_wait=15 * 60,
            progress_callback=report_progress,
        )
        response_body = result["json"] if result["json"] is not None else result["text"]
        response_truncated = bool(result["truncated"])
        record_count = None
        if isinstance(response_body, dict) and isinstance(response_body.get("dati"), list):
            record_count = len(response_body["dati"])
            if record_count > 25:
                response_body = {
                    **response_body,
                    "dati": response_body["dati"][:25],
                    "diagnostica_app": {
                        "record_totali": record_count,
                        "record_mostrati": 25,
                        "nota": "Anteprima asincrona limitata: nessun dato e' stato importato.",
                    },
                }
                response_truncated = True

        update_task(self.request.id, task_name, 100, status_string["end"])
        clear_task_status(self.request.id)
        return {
            "ok": bool(result["ok"]),
            "message": (
                f"Batch MATRIXWS completato: {record_count} record ricevuti, nessun dato importato."
                if record_count is not None
                else "Batch MATRIXWS completato, nessun dato importato."
            ),
            "request": {
                **request_meta,
                "batch_uuid": result["batch_uuid"],
                "elapsed_seconds": round(float(result["elapsed"]), 1),
            },
            "response": {
                "status_code": result["status_code"],
                "content_type": result["content_type"],
                "body": response_body,
                "truncated": response_truncated,
            },
        }
    except MatrixWSError as exc:
        update_task(self.request.id, task_name, 0, status_string["error"], exc)
        return {
            "ok": False,
            "kind": exc.kind,
            "message": str(exc),
            "details": exc.details,
            "request": {**request_meta, "batch_uuid": batch_uuid},
        }
    except Exception as exc:
        logger.exception("Errore nel test MATRIXWS asincrono %s", batch_uuid)
        update_task(self.request.id, task_name, 0, status_string["error"], exc)
        return {
            "ok": False,
            "kind": "unexpected",
            "message": "Errore inatteso durante il polling MATRIXWS.",
            "request": {**request_meta, "batch_uuid": batch_uuid},
        }


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
