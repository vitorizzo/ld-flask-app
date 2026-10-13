"""Check readiness of the four systemd workers without waiting on busy solo pools."""
import json
import os
import socket
import subprocess
import time

from dotenv import load_dotenv
import redis

SERVICES = {
    'background': ('celery-worker.service', 'celery'),
    'gestionale': ('celery-context@gestionale.service', 'ld_gestionale'),
    'notifiche': ('celery-context@notifiche.service', 'ld_notifiche'),
    'spedizioni': ('celery-context@spedizioni.service', 'ld_spedizioni'),
}


def main():
    load_dotenv('.env', override=True)
    load_dotenv('.env.local', override=True)
    r = redis.Redis.from_url(os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
                             decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
    deadline = time.monotonic() + 120
    pending = list(SERVICES)
    while time.monotonic() < deadline:
        pending = []
        for name, (service, queue) in SERVICES.items():
            pid = int(subprocess.check_output(['systemctl','show',service,'--property=MainPID','--value']).strip() or 0)
            try:
                raw = r.get('celery:runtime:worker_ready:' + name + '@' + socket.gethostname())
                state = json.loads(raw) if raw else {}
            except (redis.RedisError, ValueError):
                state = {}
            if pid <= 1 or state.get('pid') != pid or state.get('queues') != [queue]:
                pending.append(name)
        if not pending:
            print('Pronti: gestionale, notifiche, spedizioni, background; code corrette.')
            return 0
        time.sleep(2)
    print('Worker non pronti: ' + ', '.join(pending))
    return 1


if __name__ == '__main__': raise SystemExit(main())
