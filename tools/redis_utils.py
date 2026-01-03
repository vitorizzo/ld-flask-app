import os
import json
import redis
from functools import lru_cache

# opzionale: permette override via env
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

status_string = {
    "start": "avviato",
    "end": "completato",
    "update": "in progress...",
    "error": "errore",
    "attached": "in coda..."
}


@lru_cache(maxsize=1)
def get_redis():
    # Non connette attivamente finché non fai un comando, ma evitiamo globale a import-time.
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)


def update_task(task_id, descrizione, progress, status, exception=None):
    if not task_id:
        return
    data = {
        "name": descrizione,
        "progress": progress,
        "stato": status
    }
    if status in ("errore", "error") and exception:
        data["errore"] = str(exception)
    set_task_status(task_id, data)


def set_task_status(task_id, status_dict):
    r = get_redis()
    if "name" not in status_dict:
        status_dict["name"] = task_id
    r.set(f"task_status: {task_id}", json.dumps(status_dict))


def get_all_tasks_status():
    r = get_redis()
    keys = r.keys("task_status:*")
    task_list = []
    for key in keys:
        raw = r.get(key)
        if not raw:
            continue
        task = json.loads(raw)
        task["task_id"] = key.replace("task_status:", "")
        stato = (task.get("stato", "") or "").lower()
        if stato not in ("completato", "errore", "fallito"):
            task_list.append(task)
    return task_list


def clear_task_status(task_id):
    """Rimuove lo stato del task (quando completato)"""
    r = get_redis()
    # FIX: niente spazio dopo i due punti
    r.delete(f"task_status: {task_id}")


def clear_all_task_statuses():
    r = get_redis()
    keys = r.keys("task_status:*")
    if keys:
        r.delete(*keys)
