# config/celery_app.py
from celery import Celery
from tools.log_utils import get_logger

logger = get_logger('main')

# Celery instance (NON creare Flask app qui)
celery = Celery(__name__)
celery.flask_app = None  # verrà valorizzata da init_celery()


class FlaskContextTask(celery.Task):
    """Esegue i task dentro app_context() quando la Flask app è disponibile."""
    abstract = True

    def apply_async(self, args=None, kwargs=None, task_id=None, **options):
        if not self.name.startswith('config.tasks.'):
            return super().apply_async(args=args, kwargs=kwargs, task_id=task_id, **options)
        from uuid import uuid4
        from tools import celery_runtime as runtime
        from tools.celery_contexts import destination
        task_id = task_id or str(uuid4())
        app = getattr(celery, 'flask_app', None)
        if app is not None:
            from tools.celery_schedule_settings import controlled_task, pause_reason, read_document
            with app.app_context():
                reason = pause_reason(self.name, read_document()) if controlled_task(self.name) else None
            if reason:
                runtime.record(self.name, 'paused')
                return runtime.mark_skipped(self, task_id, reason)
        headers = dict(options.get('headers') or {})
        transfer = options.pop('ld_transfer', False)
        previous = (headers.get('ld_runtime') or {}).get('token') if options.get('retries') or transfer else None
        job, reason = runtime.reserve(self.name, task_id, args, kwargs, options.get('expires'),
                                      options.get('countdown'), options.get('eta'), previous)
        if reason:
            return runtime.mark_skipped(self, task_id, reason)
        headers['ld_runtime'] = job
        options.update(headers=headers, queue=destination(self.name))
        # A finite broker expiration matches the reservation deadline, including
        # manual jobs. An expired message can never execute after its replacement.
        if options.get('expires') is None:
            from datetime import datetime, timezone
            options['expires'] = datetime.fromtimestamp(job['deadline'], timezone.utc)
        try:
            return super().apply_async(args=args, kwargs=kwargs, task_id=task_id, **options)
        except Exception:
            runtime.finish(job, 'publish_failed')
            raise

    def __call__(self, *args, **kwargs):
        from tools.import_pause import task_paused

        app = getattr(celery, "flask_app", None)
        if app is None and task_paused(self.name):
            from tools.redis_utils import clear_task_status

            clear_task_status(self.request.id)
            logger.info("Task %s sospeso temporaneamente: MATRIX/file import in pausa", self.name)
            return {
                "success": True,
                "skipped": True,
                "reason": "imports_paused",
                "message": "Importazioni MATRIX e file temporaneamente sospese.",
            }
        if app is None:
            # fallback: esegui senza contesto (meglio di crashare)
            logger.warning(f"Celery task senza flask_app inizializzata: {self.name}")
            return super().__call__(*args, **kwargs)

        logger.info(f"Esecuzione task Celery: {self.name}")
        with app.app_context():
            from tools.celery_schedule_settings import controlled_task, pause_reason, read_document
            from tools import celery_runtime as runtime
            from tools.celery_contexts import task_context, contexts_enabled, destination

            managed = self.name.startswith('config.tasks.') and not self.request.called_directly
            job = (self.request.headers or {}).get('ld_runtime') if managed else None

            if controlled_task(self.name):
                try:
                    reason = pause_reason(self.name, read_document())
                except Exception:
                    if job:
                        try: runtime.finish(job, 'failed')
                        except Exception: logger.exception('Cleanup prenotazione dopo errore configurazione fallito')
                    raise
                if reason:
                    from tools.redis_utils import clear_task_status

                    clear_task_status(self.request.id)
                    if managed:
                        if job: runtime.finish(job, 'paused')
                        else: runtime.record(self.name, 'paused')
                    logger.info("Task %s non eseguito: %s", self.name, reason)
                    return {"success": True, "skipped": True, "reason": reason,
                            "message": "Task sospesa dalle impostazioni Celery."}
            routing_key = (self.request.delivery_info or {}).get('routing_key')
            if managed and contexts_enabled() and routing_key and routing_key != destination(self.name):
                # Preserve legacy queued messages during the transition, moving
                # them to their context without publishing a premature result.
                from celery.exceptions import Ignore
                signature = self.signature_from_request(args=args, kwargs=kwargs, queue=destination(self.name))
                signature.apply_async(ld_transfer=True)
                raise Ignore()
            if not managed:
                result = super().__call__(*args, **kwargs)
            else:
                import time
                from celery.exceptions import Retry
                if not job:
                    job, reason = runtime.reserve(self.name, self.request.id, args, kwargs, self.request.expires)
                    if reason:
                        from tools.redis_utils import clear_task_status
                        clear_task_status(self.request.id)
                        return {"success": True, "skipped": True, "reason": reason}
                started = time.monotonic()
                outcome = 'completed'
                try:
                    with runtime.execution(job, task_context(self.name)):
                        started = time.monotonic()
                        result = super().__call__(*args, **kwargs)
                        if isinstance(result, dict):
                            if result.get('skipped') is True:
                                outcome = 'skip_running' if result.get('reason') == 'previous_run_active' else 'skipped_other'
                            elif result.get('success') is False or result.get('ok') is False:
                                outcome = 'failed'
                except runtime.LeaseLost:
                    from tools.redis_utils import clear_task_status
                    clear_task_status(self.request.id)
                    return {"success": True, "skipped": True, "reason": "reservation_expired"}
                except Retry:
                    outcome = 'release'
                    raise
                except Exception:
                    outcome = 'failed'
                    raise
                finally:
                    try:
                        runtime.finish(job, outcome, time.monotonic()-started if outcome in {'completed', 'failed'} else None)
                    except Exception:
                        logger.exception('Chiusura lease/metriche Celery fallita: %s', self.name)
            logger.info(f"Task completato: {self.name}")
            return result


def init_celery(app):
    """
    Va chiamata DOPO create_app().
    Collega Celery alla Flask app ed imposta broker/backend/config.
    """
    logger.info("Inizializzazione Celery (post create_app)...")

    celery.flask_app = app

    # Config essenziale
    celery.conf.broker_url = app.config.get("CELERY_BROKER_URL")
    celery.conf.result_backend = app.config.get("CELERY_RESULT_BACKEND")

    # Config aggiuntiva (se esiste)
    celery.config_from_object("config.celeryconfig", silent=True)

    # Assicura che tutti i task usino il contesto Flask
    celery.Task = FlaskContextTask
    # Register worker-ready/revocation hooks before the worker starts consuming.
    from tools import celery_runtime  # noqa: F401

    # Carica i task (import differito, senza creare loop)
    celery.conf.include = list(set((celery.conf.include or []) + ["config.tasks"]))

    logger.info("Celery pronto.")
    return celery
