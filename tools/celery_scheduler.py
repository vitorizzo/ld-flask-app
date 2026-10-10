"""Persistent Celery Beat scheduler reloading developer preferences every 5s."""
from datetime import datetime, timezone
import json
import time

from celery.beat import PersistentScheduler

from tools.celery_schedule_settings import catalog, effective_schedule, read_document
from tools.log_utils import get_logger

logger = get_logger("celeryconfig")


class PreferenceScheduler(PersistentScheduler):
    def __init__(self, *args, **kwargs):
        self._preferences_checked_at = None
        self._preferences_revision = None
        self._preferences_ready = False
        super().__init__(*args, **kwargs)
        self.max_interval = min(self.max_interval, 5)

    def reload_preferences(self, force=False):
        now = time.monotonic()
        if not force and self._preferences_checked_at is not None and now - self._preferences_checked_at < 5:
            return self._preferences_ready
        self._preferences_checked_at = now
        app = getattr(self.app, "flask_app", None)
        if app is None:
            logger.error("Scheduler Celery: contesto Flask non disponibile; invii sospesi")
            self._preferences_ready = False
            return False
        try:
            with app.app_context():
                doc = read_document()
            if doc["revision"] != self._preferences_revision:
                desired = effective_schedule(doc, app=self.app)
                for name in catalog():
                    if name not in desired:
                        self.schedule.pop(name, None)
                for name, data in desired.items():
                    previous = self.schedule.get(name)
                    entry = self.Entry(name=name, app=self.app, **data)
                    if previous:
                        entry.last_run_at = previous.last_run_at
                        entry.total_run_count = previous.total_run_count
                    self.schedule[name] = entry
                self._heap = None
                self.sync()
                self._preferences_revision = doc["revision"]
                logger.info("Schedulazioni Celery aggiornate: revisione %s, %s attive", doc["revision"], len(desired))
            self._preferences_ready = True
            self.publish_status()
            return True
        except Exception:
            self._preferences_ready = False
            logger.exception("Configurazione Celery non disponibile; invii periodici sospesi fino al recupero")
            self.publish_status(error=True)
            return False

    def publish_status(self, error=False):
        from tools.redis_utils import get_redis
        try:
            get_redis().setex("celery:schedule_settings:heartbeat", 30, json.dumps({
                "revision": self._preferences_revision,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "error": error,
            }))
        except Exception:
            logger.warning("Heartbeat configurazione Celery non disponibile")

    def tick(self, *args, **kwargs):
        if not self.reload_preferences():
            return self.max_interval
        return super().tick(*args, **kwargs)
