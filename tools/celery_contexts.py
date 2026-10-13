"""Task destinations and singleton identities shared by every producer."""
import hashlib
import json
import os

from tools.import_pause import IMPORT_TASKS

PREFIX = "config.tasks."
ALIASES = {
    PREFIX + "import_barcode_matrixws_task": PREFIX + "import_barcode_task",
    PREFIX + "import_giacenze_matrixws_task": PREFIX + "import_giacenze_task",
}
NOTIFICATIONS = {PREFIX + name for name in (
    "notify_customer_payment_case_task", "send_administration_payment_link_task",
    "dispatch_customer_route_order_reminders_task",
)}
SHIPPING = {PREFIX + name for name in (
    "import_poleepo_orders_task", "sync_poleepo_shipments_task", "refresh_open_shipments_task",
    "import_poleepo_products_task",
)}
PERIODIC = NOTIFICATIONS - {PREFIX + "notify_customer_payment_case_task", PREFIX + "send_administration_payment_link_task"}
PERIODIC |= SHIPPING - {PREFIX + "import_poleepo_products_task"}
PERIODIC |= {PREFIX + name for name in (
    "dispatch_due_mailing_schedules_task", "create_weekly_events_social_post_task",
    "create_weekend_events_social_post_task", "sync_support_mailbox_task",
)}
SINGLETONS = IMPORT_TASKS | PERIODIC | {PREFIX + "import_ps_task", PREFIX + "import_poleepo_products_task"}
QUEUES = {"gestionale": "ld_gestionale", "notifiche": "ld_notifiche",
          "spedizioni": "ld_spedizioni", "background": "celery"}


def contexts_enabled():
    return os.getenv("CELERY_CONTEXT_QUEUES_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def canonical_task(name):
    return ALIASES.get(name, name)


def task_context(name):
    if name in IMPORT_TASKS:
        return "gestionale"
    if name in NOTIFICATIONS:
        return "notifiche"
    if name in SHIPPING:
        return "spedizioni"
    return "background"


def destination(name):
    return QUEUES[task_context(name)] if contexts_enabled() else "celery"


def task_route(name, args=None, kwargs=None, options=None, task=None, **extra):
    if name.startswith(PREFIX):
        return {"queue": destination(name)}
    return None


def job_key(name, args=None, kwargs=None, task_id=None):
    canonical = canonical_task(name)
    # Imports have one identity, including their legacy/manual aliases.
    # Diagnostics with different parameters remain independent jobs.
    if name in IMPORT_TASKS and "import_" in name.rsplit(".", 1)[-1]:
        identity = canonical
    elif name in SINGLETONS:
        identity = canonical + json.dumps([args or [], kwargs or {}], sort_keys=True, default=str)
    else:
        identity = canonical + ":" + str(task_id)
    return "celery:runtime:job:" + hashlib.sha256(identity.encode()).hexdigest()
