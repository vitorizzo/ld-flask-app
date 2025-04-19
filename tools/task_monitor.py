from celery.result import AsyncResult
from celery.app.control import Control
from config.celery_app import celery


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
    celery.control.revoke(task_id, terminate=True, signal='SIGKILL')
    return {"message": f"Task {task_id} revocato e terminato."}
