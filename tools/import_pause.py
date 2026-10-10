"""Temporary switch for MATRIXWS and file import Celery tasks."""
import os


PAUSE_ENV = "MATRIX_FILE_IMPORTS_PAUSED"
IMPORT_TASKS = frozenset(
    "config.tasks." + name
    for name in (
        "import_articoli_task", "import_barcode_task",
        "import_barcode_matrixws_task", "import_giacenze_task",
        "import_giacenze_matrixws_task", "import_anagrafiche_task",
        "import_estratti_conto_clienti_task", "preview_matrixws_articoli_task",
        "compare_file_matrixws_sources_task", "matrixws_test_poll_task",
    )
)


def imports_paused():
    return os.getenv(PAUSE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def task_paused(task_name):
    return task_name in IMPORT_TASKS and imports_paused()
