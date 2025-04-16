import redis
import json

# Connessione al tuo Redis locale
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)


status_string = {
    "start": "avviato",
    "end": "completato",
    "update": "in progress...",
    "error": "errore",
    "attached": "in coda..."
}


def update_task(task_id, descrizione, progress, status, exception=None):
    if not task_id:
        return
    data = {
        "descrizione": descrizione,
        "progress": progress,
        "stato": status
    }
    if status in ("errore", "error") and exception:
        data["errore"] = str(exception)
    set_task_status(task_id, data)


def set_task_status(task_id, status_dict):
    """Salva/aggiorna lo stato del task"""
    r.set(f"task_status: {task_id}", json.dumps(status_dict))


def get_all_tasks_status():
    """Recupera tutti i task attivi"""
    keys = r.keys("task_status:*")
    task_list = []
    for key in keys:
        task = json.loads(r.get(key))
        task['task_id'] = key.replace("task_status:", "")
        task_list.append(task)
    return task_list


def clear_task_status(task_id):
    """Rimuove lo stato del task (quando completato)"""
    r.delete(f"task_status: {task_id}")
