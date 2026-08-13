import os
import json
import redis
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlparse
from redis.exceptions import RedisError

# opzionale: permette override via env
_broker_url = urlparse(os.getenv("CELERY_BROKER_URL", ""))
REDIS_HOST = os.getenv("REDIS_HOST") or (_broker_url.hostname if _broker_url.scheme == "redis" else None) or "localhost"
REDIS_PORT = int(os.getenv("REDIS_PORT") or (_broker_url.port if _broker_url.scheme == "redis" and _broker_url.port else 6379))
REDIS_DB = int(os.getenv("REDIS_DB") or ((_broker_url.path or "/0").lstrip("/") if _broker_url.scheme == "redis" else "0") or "0")

status_string = {
    "start": "avviato",
    "end": "completato",
    "update": "in progress...",
    "error": "errore",
    "attached": "in coda..."
}

TASK_STATUS_ACTIVE_TTL = int(os.getenv("TASK_STATUS_ACTIVE_TTL", "86400"))
TASK_STATUS_ERROR_TTL = int(os.getenv("TASK_STATUS_ERROR_TTL", "604800"))


@lru_cache(maxsize=1)
def get_redis():
    # Non connette attivamente finché non fai un comando, ma evitiamo globale a import-time.
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


def update_task(task_id, descrizione, progress, status, exception=None):
    if not task_id:
        return
    data = {
        "name": descrizione,
        "progress": progress,
        "stato": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if status in ("errore", "error") and exception:
        data["errore"] = str(exception)
    try:
        set_task_status(task_id, data)
    except RedisError:
        return


def set_task_status(task_id, status_dict):
    r = get_redis()
    if "name" not in status_dict:
        status_dict["name"] = task_id
    stato = str(status_dict.get("stato") or "").strip().lower()
    ttl = TASK_STATUS_ERROR_TTL if stato in {"errore", "error", "fallito", "failed"} else TASK_STATUS_ACTIVE_TTL
    r.setex(f"task_status:{task_id}", ttl, json.dumps(status_dict))


def get_all_tasks_status():
    r = get_redis()
    try:
        keys = r.keys("task_status:*")
    except RedisError:
        return []
    task_list = []
    for key in keys:
        try:
            raw = r.get(key)
        except RedisError:
            continue
        if not raw:
            continue
        task = json.loads(raw)
        task["task_id"] = key.replace("task_status:", "", 1).strip()
        stato = (task.get("stato", "") or "").lower()
        if stato not in ("completato",):
            task["terminal"] = stato in ("errore", "error", "fallito", "failed", "revocato", "revoked")
            task["legacy"] = not bool(task.get("updated_at"))
            task_list.append(task)
    return sorted(
        task_list,
        key=lambda task: (bool(task.get("terminal")), str(task.get("updated_at") or "")),
        reverse=False,
    )


def clear_task_status(task_id):
    """Rimuove lo stato del task (quando completato)"""
    r = get_redis()
    task_id = (task_id or "").strip()
    if not task_id:
        return 0
    # Compatibilita' con le vecchie chiavi scritte come "task_status: <id>".
    try:
        return r.delete(f"task_status:{task_id}", f"task_status: {task_id}")
    except RedisError:
        return 0


def clear_all_task_statuses():
    r = get_redis()
    try:
        keys = r.keys("task_status:*")
        if keys:
            r.delete(*keys)
    except RedisError:
        return


def clear_terminal_task_statuses():
    """Rimuove dal monitor soltanto errori/revoche, senza toccare task attivi."""
    r = get_redis()
    cleared = 0
    try:
        for key in r.scan_iter("task_status:*"):
            raw = r.get(key)
            if not raw:
                continue
            try:
                task = json.loads(raw)
            except (TypeError, ValueError):
                continue
            stato = str(task.get("stato") or "").strip().lower()
            if stato in {"errore", "error", "fallito", "failed", "revocato", "revoked"}:
                cleared += int(r.delete(key) or 0)
    except RedisError:
        return cleared
    return cleared
