from celery.result import AsyncResult
from config.celery_app import celery
from tools.redis_utils import clear_task_status


def get_task_status(task_id):
    """Ritorna lo stato attuale di un task."""
    result = AsyncResult(task_id, app=celery)
    return {
        "id": task_id,
        "status": result.status,
        "result": str(result.result) if result.result else None,
        "ready": result.ready(),
        "successful": result.successful(),
        "failed": result.failed()
    }


def kill_task(task_id, *, revoke=True):
    """Revoca un task attivo oppure rimuove un risultato terminale dal monitor."""
    task_id = (task_id or "").strip()
    if not task_id:
        return {"message": "ID task mancante.", "cleared": 0}
    if revoke:
        celery.control.revoke(task_id, terminate=True)
    cleared = clear_task_status(task_id)
    action = "revocato e rimosso" if revoke else "rimosso"
    return {"message": f"Task {task_id} {action} dal monitor.", "cleared": cleared}
