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


def kill_task(task_id):
    """Revoca e termina un task Celery attivo."""
    task_id = (task_id or "").strip()
    if not task_id:
        return {"message": "ID task mancante.", "cleared": 0}
    celery.control.revoke(task_id, terminate=True, signal='SIGKILL')
    cleared = clear_task_status(task_id)
    return {"message": f"Task {task_id} revocato e rimosso dal monitor.", "cleared": cleared}
