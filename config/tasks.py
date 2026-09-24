# config/tasks.py
from config.celery_app import celery
from tools.importazioni import (
    import_anagrafiche,
    import_articoli,
    import_articoli_matrixws,
    preview_matrixws_articoli,
    import_barcode_matrixws,
    import_giacenze_matrixws,
    compare_file_matrixws_sources,
    import_estratti_conto_clienti,
    compare_matrixws_customer_statements,
    import_giacenze,
    import_poleepo_products,
    import_ps,
    run_import_barcode,
)
from tools.log_utils import log_task, get_logger

logger = get_logger('tasks')
mailing_logger = get_logger('mailing_list')
customer_payment_logger = get_logger('customer_payment_notifications')


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
        lambda: import_articoli_matrixws(task_id=self.request.id),
    )


@celery.task(bind=True)
@log_task(logger)
def preview_matrixws_articoli_task(self):
    return preview_matrixws_articoli(task_id=self.request.id)


@celery.task(bind=True)
@log_task(logger)
def import_barcode_matrixws_task(self):
    return _run_locked_import(
        "barcodes", self.request.id, "Importazione codici a barre",
        lambda: import_barcode_matrixws(task_id=self.request.id),
    )


@celery.task(bind=True)
@log_task(logger)
def import_giacenze_matrixws_task(self):
    return _run_locked_import(
        "stock", self.request.id, "Importazione giacenze",
        lambda: import_giacenze_matrixws(task_id=self.request.id),
    )


@celery.task(bind=True)
@log_task(logger)
def compare_file_matrixws_sources_task(self):
    return compare_file_matrixws_sources(task_id=self.request.id)


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
        lambda: import_giacenze_matrixws(task_id=self.request.id),
    )


@celery.task(bind=True)
@log_task(logger)
def import_barcode_task(self):
    return _run_locked_import(
        "barcodes", self.request.id, "Importazione codici a barre",
        lambda: import_barcode_matrixws(task_id=self.request.id),
    )


@celery.task(bind=True)
@log_task(logger)
def import_anagrafiche_task(self):
    return import_anagrafiche(task_id=self.request.id)


@celery.task(bind=True)
@log_task(logger)
def import_estratti_conto_clienti_task(self):
    return import_estratti_conto_clienti(task_id=self.request.id)


def _matrixws_diagnostic_preview(value, limit=25):
    """Limita le liste della risposta diagnostica senza alterare il dato importato."""
    record_counts = []
    truncated = False

    def visit(nested):
        nonlocal truncated
        if isinstance(nested, list):
            record_counts.append(len(nested))
            if len(nested) > limit:
                truncated = True
            return [visit(item) for item in nested[:limit]]
        if isinstance(nested, dict):
            return {key: visit(item) for key, item in nested.items()}
        return nested

    preview = visit(value)
    record_count = max(record_counts) if record_counts else None
    return preview, record_count, truncated


@celery.task(bind=True)
@log_task(logger)
def matrixws_test_poll_task(self, batch_uuid, request_meta=None):
    """Completa in background un test MATRIXWS asincrono senza importare alcun dato."""
    from flask import current_app
    from tools.preferences import load_preferences_into_app_config

    from tools.matrixws_client import (
        MatrixWSConfig,
        MatrixWSError,
        call_async,
        extract_batch_uuid,
        renew_secret,
        wait_for_batch_result,
    )
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
        # Il secret puo' essere stato aggiornato dal pannello web mentre il
        # worker era gia' avviato: ricarica le preferenze cifrate dal DB prima
        # di ogni chiamata, evitando di usare il token precedente in memoria.
        load_preferences_into_app_config(current_app._get_current_object())
        config = MatrixWSConfig.from_app_config(current_app.config)
        # Anche l'avvio puo' richiedere diversi minuti sul server MATRIXWS.
        # Deve rimanere nel worker: tenerlo nella richiesta HTTP fa scadere
        # il proxy web prima che il batch restituisca il proprio UUID.
        if not batch_uuid:
            start_result = call_async(
                config,
                request_meta.get("payload") or {},
                method="POST",
                timeout=(5, 300),
            )
            secret_renewed = False
            if start_result.get("status_code") == 401:
                renewed_secret = renew_secret(config)
                from extensions import db
                from models import AppPreference
                preference = AppPreference.query.filter_by(key="matrixws.secret").first()
                if preference is None:
                    raise MatrixWSError(
                        "Secret MATRIXWS rinnovato ma la preferenza non e' disponibile per il salvataggio.",
                        kind="renewal_storage",
                    )
                preference.secret_value = renewed_secret
                preference.value_text = None
                preference.value_json = None
                db.session.commit()
                current_app.config["MATRIXWS_SECRET"] = renewed_secret
                config = MatrixWSConfig.from_app_config(current_app.config)
                start_result = call_async(
                    config,
                    request_meta.get("payload") or {},
                    method="POST",
                    timeout=(5, 300),
                )
                secret_renewed = True
            if not start_result.get("ok"):
                raise MatrixWSError(
                    f"Avvio batch MATRIXWS fallito (HTTP {start_result.get('status_code')}).",
                    kind="response",
                    details={
                        "status_code": start_result.get("status_code"),
                        "body": start_result.get("json")
                        if start_result.get("json") is not None
                        else start_result.get("text"),
                    },
                )
            batch_uuid = extract_batch_uuid(start_result.get("json"))
            if not batch_uuid:
                raise MatrixWSError(
                    "MATRIXWS ha accettato la richiesta ma non ha restituito il batch_uuid.",
                    kind="response",
                    details={"body": start_result.get("json")},
                )
            request_meta.update({
                "url": start_result.get("url"),
                "method": start_result.get("method", "POST"),
                "batch_uuid": batch_uuid,
                "secret_renewed": secret_renewed,
            })
        result = wait_for_batch_result(
            config,
            batch_uuid,
            poll_timeout=(5, max(180, int(request_meta.get("poll_read_timeout_seconds") or 180))),
            poll_interval=2,
            max_wait=max(15, int(request_meta.get("poll_timeout_minutes") or 15)) * 60,
            progress_callback=report_progress,
        )
        response_body = result["json"] if result["json"] is not None else result["text"]
        comparison = None
        if request_meta.get("test_key") == "customer_statements" and isinstance(response_body, dict):
            try:
                comparison = compare_matrixws_customer_statements(response_body)
            except Exception as comparison_exc:
                logger.exception("Confronto 1011/EC_CLI non completato")
                comparison = {"error": str(comparison_exc)}
        response_truncated = bool(result["truncated"])
        response_body, record_count, preview_truncated = _matrixws_diagnostic_preview(response_body)
        response_truncated = response_truncated or preview_truncated
        if preview_truncated:
            diagnostic_meta = {
                "record_totali": record_count,
                "record_mostrati": 25,
                "nota": "Anteprima asincrona limitata: nessun dato e' stato importato.",
            }
            if isinstance(response_body, dict):
                response_body = {**response_body, "diagnostica_app": diagnostic_meta}
            else:
                response_body = {
                    "anteprima": response_body,
                    "diagnostica_app": diagnostic_meta,
                }
        if comparison is not None and isinstance(response_body, dict):
            response_body = {**response_body, "confronto_ec_cli": comparison}

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
@log_task(customer_payment_logger)
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
def dispatch_customer_route_order_reminders_task(self):
    from tools.customer_route_reminders import dispatch_customer_route_order_reminders

    return dispatch_customer_route_order_reminders()


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
