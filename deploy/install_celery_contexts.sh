#!/usr/bin/env bash
# One-time coordinated activation after the ordinary application deploy.
set -euo pipefail
ROOT=/home/tecno/ld-flask-app-working
if [[ ${EUID} -ne 0 ]]; then
  echo 'Eseguire con sudo: sudo bash deploy/install_celery_contexts.sh' >&2
  exit 1
fi
if [[ "$(realpath -- "$ROOT")" != "$ROOT" ]]; then
  echo 'Percorso produzione inatteso' >&2
  exit 1
fi
cd -- "$ROOT"
test -f tools/celery_contexts.py
test -f deploy/systemd/celery-context@.service
test -f deploy/systemd/celery-worker.service
systemctl cat ld-flask-app.service celery-beat.service celery-worker.service >/dev/null
runuser -u tecno -- "$ROOT/venv/bin/python" -B -c 'from pathlib import Path; files=["config/celery_app.py", "tools/celery_contexts.py", "tools/celery_runtime.py", "tools/check_celery_workers.py"]; [compile(Path(p).read_text(encoding="utf8"),p,"exec") for p in files]'
# Check unit syntax before stopping anything or changing the environment.
systemd-analyze verify deploy/systemd/celery-context@.service deploy/systemd/celery-worker.service
BACKUP="$ROOT/.codex_tmp/celery-contexts-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p -- "$BACKUP"
cp -p -- /etc/systemd/system/celery-worker.service "$BACKUP/celery-worker.service"
if [[ -f /etc/systemd/system/celery-context@.service ]]; then
  cp -p -- /etc/systemd/system/celery-context@.service "$BACKUP/celery-context@.service"
fi
if [[ -f .env.local ]]; then cp -p -- .env.local "$BACKUP/env.local"; fi
rollback() {
  trap - ERR
  echo "Attivazione fallita; ripristino un worker seriale che consuma tutte le code. Backup: $BACKUP" >&2
  systemctl stop celery-beat.service ld-flask-app.service || true
  systemctl stop celery-worker.service celery-context@gestionale.service celery-context@notifiche.service celery-context@spedizioni.service || true
  cp -p -- "$BACKUP/celery-worker.service" /etc/systemd/system/celery-worker.service
  runuser -u tecno -- "$ROOT/venv/bin/python" -B -c 'from dotenv import set_key; set_key(".env.local", "CELERY_CONTEXT_QUEUES_ENABLED", "false")'
  mkdir -p /run/systemd/system/celery-worker.service.d
  printf '[Service]\nExecStart=\nExecStart=%s/venv/bin/celery -A celery_worker.celery worker --loglevel=info --pool=solo --prefetch-multiplier=1 --queues=celery,ld_gestionale,ld_notifiche,ld_spedizioni --hostname=fallback@%%H\nTimeoutStopSec=infinity\n' "$ROOT" > /run/systemd/system/celery-worker.service.d/context-rollback.conf
  systemctl disable celery-context@gestionale.service celery-context@notifiche.service celery-context@spedizioni.service || true
  systemctl daemon-reload
  systemctl start celery-worker.service ld-flask-app.service celery-beat.service || true
  exit 1
}
trap rollback ERR
echo 'Fermo Beat e web; il worker termina la task in corso prima di fermarsi.'
systemctl stop celery-beat.service ld-flask-app.service
# Override only the stop timeout: do not kill an import in progress.
mkdir -p /run/systemd/system/celery-worker.service.d
printf '[Service]\nTimeoutStopSec=infinity\n' > /run/systemd/system/celery-worker.service.d/context-transition.conf
systemctl daemon-reload
systemctl stop celery-worker.service
for SERVICE in celery-context@gestionale.service celery-context@notifiche.service celery-context@spedizioni.service; do
  if systemctl cat "$SERVICE" >/dev/null 2>&1; then systemctl stop "$SERVICE"; fi
done
install -m 0644 deploy/systemd/celery-context@.service /etc/systemd/system/celery-context@.service
install -m 0644 deploy/systemd/celery-worker.service /etc/systemd/system/celery-worker.service
if [[ -f /run/systemd/system/celery-worker.service.d/context-rollback.conf ]]; then
  mv -- /run/systemd/system/celery-worker.service.d/context-rollback.conf "$BACKUP/prior-rollback.conf"
fi
runuser -u tecno -- "$ROOT/venv/bin/python" -B -c 'from dotenv import set_key; set_key(".env.local", "CELERY_CONTEXT_QUEUES_ENABLED", "true")'
systemctl daemon-reload
systemctl enable celery-worker.service celery-context@gestionale.service celery-context@notifiche.service celery-context@spedizioni.service
systemctl start celery-worker.service celery-context@gestionale.service celery-context@notifiche.service celery-context@spedizioni.service
runuser -u tecno -- "$ROOT/venv/bin/python" -B tools/check_celery_workers.py
systemctl start ld-flask-app.service celery-beat.service
systemctl --no-pager --full status celery-worker.service celery-context@gestionale.service celery-context@notifiche.service celery-context@spedizioni.service celery-beat.service
trap - ERR
echo "Worker dedicati attivati. Backup: $BACKUP. La pausa MATRIX/file non e' stata modificata."
