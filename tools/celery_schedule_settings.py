"""Developer-owned recurring task settings in the existing preferences store."""
from copy import deepcopy
from datetime import datetime, timezone
import re

from celery.schedules import crontab, schedule

from tools.import_pause import IMPORT_TASKS, imports_paused

PREFERENCE_KEY = "celery.periodic_tasks"
CRON_FIELDS = ("minute", "hour", "day_of_week", "day_of_month", "month_of_year")
LABELS = {
    "dispatch-due-mailing-schedules-every-minute": ("Invio campagne programmate", "Email / mailing"),
    "import-articoli": ("Import articoli", "Import MATRIXWS"),
    "import-giacenze": ("Import giacenze", "Import MATRIXWS"),
    "import-barcode": ("Import codici a barre", "Import MATRIXWS"),
    "import-anagrafiche": ("Import anagrafiche", "Import MATRIXWS"),
    "import-customer-account-statements-half-hourly": ("Import estratti conto clienti", "Import file"),
    "poleepo-import-orders": ("Import ordini Poleepo", "Import Poleepo"),
    "poleepo-sync-shipments": ("Sincronizzazione spedizioni Poleepo", "Spedizioni"),
    "shipping-refresh-open": ("Aggiornamento spedizioni aperte", "Spedizioni"),
    "customer-route-order-reminders": ("Promemoria ordini clienti", "Notifiche"),
    "events-social-weekly": ("Post eventi settimanali", "Social"),
    "events-social-weekend": ("Post eventi fine settimana", "Social"),
    "support-mailbox-sync": ("Sincronizzazione casella assistenza", "Email / assistenza"),
}
ALIASES = {
    "config.tasks.import_barcode_matrixws_task": "config.tasks.import_barcode_task",
    "config.tasks.import_giacenze_matrixws_task": "config.tasks.import_giacenze_task",
}


class ScheduleConflict(ValueError):
    pass


def catalog():
    from config.celeryconfig import DEFAULT_BEAT_SCHEDULE
    return DEFAULT_BEAT_SCHEDULE


def frequency_from_schedule(value):
    if isinstance(value, crontab):
        return dict(kind="cron", **{field: str(getattr(value, "_orig_" + field)) for field in CRON_FIELDS})
    return {"kind": "interval", "seconds": int(value.run_every.total_seconds())}


def validate_frequency(data):
    if not isinstance(data, dict):
        raise ValueError("Imposta una frequenza valida.")
    if data.get("kind") == "interval":
        seconds = data.get("seconds")
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 60 <= seconds <= 31 * 86400:
            raise ValueError("L'intervallo deve essere tra 1 minuto e 31 giorni.")
        return {"kind": "interval", "seconds": seconds}
    if data.get("kind") != "cron":
        raise ValueError("Scegli intervallo o calendario.")
    cleaned = {}
    for field in CRON_FIELDS:
        raw = data.get(field)
        if not isinstance(raw, str) or not raw.strip() or len(raw) > 160:
            raise ValueError("Compila tutti i campi del calendario.")
        raw = raw.strip().lower()
        if not re.fullmatch(r"[a-z0-9*,/\-]+", raw) or re.search(r"/0(?:\D|$)", raw):
            raise ValueError("Espressione calendario non valida: " + field)
        cleaned[field] = raw
    try:
        value = crontab(**cleaned)
        if not all(getattr(value, field) for field in CRON_FIELDS):
            raise ValueError("empty range")
        # Reject calendars that never occur (e.g. 31 February).
        value.remaining_estimate(datetime.now(timezone.utc))
    except (ValueError, TypeError, KeyError, RuntimeError) as exc:
        raise ValueError("Calendario non valido o senza date possibili.") from exc
    return dict(kind="cron", **cleaned)


def celery_frequency(data, app=None):
    if data["kind"] == "interval":
        return schedule(data["seconds"], app=app)
    return crontab(app=app, **{field: data[field] for field in CRON_FIELDS})


def default_document(paused=None):
    paused = imports_paused() if paused is None else paused
    return {
        "revision": 0,
        "imports_paused": paused,
        "schedules": {
            name: {"enabled": not (paused and entry["task"] in IMPORT_TASKS),
                   "deleted": False, "frequency": frequency_from_schedule(entry["schedule"])}
            for name, entry in catalog().items()
        },
    }


def normalize_document(raw):
    result = default_document(raw.get("imports_paused", imports_paused()) if isinstance(raw, dict) else None)
    if raw is None:
        return result
    if not isinstance(raw, dict) or not isinstance(raw.get("schedules"), dict):
        raise ValueError("Configurazione Celery non leggibile.")
    if type(raw.get("revision")) is not int or raw["revision"] < 0 or type(raw.get("imports_paused")) is not bool:
        raise ValueError("Configurazione Celery non valida.")
    result["revision"] = raw.get("revision", 0)
    result["imports_paused"] = raw.get("imports_paused", result["imports_paused"])
    for name, value in raw["schedules"].items():
        if name in result["schedules"]:
            if not isinstance(value, dict) or type(value.get("enabled")) is not bool or type(value.get("deleted")) is not bool:
                raise ValueError("Stato task Celery non valido.")
            result["schedules"][name] = dict(enabled=value["enabled"], deleted=value["deleted"],
                                              frequency=validate_frequency(value.get("frequency")))
    return result


def read_document():
    from models import AppPreference
    row = AppPreference.query.filter_by(key=PREFERENCE_KEY).populate_existing().first()
    return normalize_document(deepcopy(row.value_json) if row else None)


def document_rows(document):
    rows = []
    for name, entry in catalog().items():
        label, kind = LABELS.get(name, (name, "Altro"))
        rows.append(dict(document["schedules"][name], id=name, name=label, type=kind, task=entry["task"]))
    return rows


def update_document(name, action, payload, user_id):
    from extensions import db
    from models import AppPreference
    from sqlalchemy.exc import IntegrityError

    revision = payload.get("revision")
    if type(revision) is not int or revision < 0:
        raise ValueError("Ricarica la configurazione prima di salvare.")
    if action not in {"frequency", "play", "pause", "delete", "restore", "imports_play", "imports_pause"}:
        raise ValueError("Operazione non valida.")
    if action.startswith("imports_"):
        if name != "imports":
            raise ValueError("Operazione non valida.")
    elif name not in catalog():
        raise ValueError("Task sconosciuta.")
    row = AppPreference.query.filter_by(key=PREFERENCE_KEY).populate_existing().with_for_update().first()
    doc = normalize_document(deepcopy(row.value_json) if row else None)
    if revision != doc["revision"]:
        raise ScheduleConflict("La configurazione e' cambiata in un'altra sessione. Ricarica prima di riprovare.")
    if action.startswith("imports_"):
        enabled = action == "imports_play"
        doc["imports_paused"] = not enabled
        for key, entry in catalog().items():
            if entry["task"] in IMPORT_TASKS:
                doc["schedules"][key]["enabled"] = enabled
    else:
        value = doc["schedules"][name]
        if value["deleted"] and action != "restore":
            raise ValueError("Ripristina la schedulazione prima di modificarla.")
        if action == "frequency":
            value["frequency"] = validate_frequency(payload.get("frequency"))
        elif action == "delete":
            value.update(deleted=True, enabled=False)
        elif action == "restore":
            value.update(deleted=False, enabled=False)
        else:
            value["enabled"] = action == "play"
    doc["revision"] += 1
    doc["updated_by"] = user_id
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    if row is None:
        row = AppPreference(key=PREFERENCE_KEY, category="Celery", label="Task periodiche Celery", value_type="json")
        db.session.add(row)
    row.value_json = doc
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ScheduleConflict("Configurazione modificata da un'altra sessione. Ricarica.") from exc
    return doc


def effective_schedule(document, app=None):
    result = {}
    for name, entry in catalog().items():
        value = document["schedules"][name]
        if value["enabled"] and not value["deleted"]:
            updated = dict(entry, schedule=celery_frequency(value["frequency"], app=app))
            updated["options"] = dict(entry.get("options", {}))
            if value["frequency"]["kind"] == "interval" and "expires" in updated["options"]:
                updated["options"]["expires"] = min(updated["options"]["expires"], value["frequency"]["seconds"] - 1)
            result[name] = updated
    return result


def controlled_task(task_name):
    canonical = ALIASES.get(task_name, task_name)
    return task_name in IMPORT_TASKS or any(entry["task"] == canonical for entry in catalog().values())


def pause_reason(task_name, document):
    canonical = ALIASES.get(task_name, task_name)
    values = [document["schedules"][name] for name, entry in catalog().items() if entry["task"] == canonical]
    if values:
        return "schedule_paused" if all(value["deleted"] or not value["enabled"] for value in values) else None
    if task_name in IMPORT_TASKS and document["imports_paused"]:
        return "imports_paused"
    return None


def beat_status():
    import json
    from tools.redis_utils import get_redis
    try:
        raw = get_redis().get("celery:schedule_settings:heartbeat")
        return json.loads(raw) if raw else None
    except Exception:
        return None
