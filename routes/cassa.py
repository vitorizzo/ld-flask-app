import logging
import os
import json
import base64
import secrets
from datetime import date, datetime, timedelta

from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required

from tools.log_utils import get_logger
from tools.role_required import role_required
from extensions import db
from models import CashDay

# Crypto (AES-GCM) - richiede pacchetto "cryptography"
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:
    AESGCM = None


cassa_bp = Blueprint("cassa", __name__, url_prefix="/cassa")
logger = get_logger("cassa", level=logging.INFO)

MIN_AGENDA_WEIGHT = 40

_VAULT_VERSION = 1
_KDF_ITERS = 200_000  # PBKDF2-HMAC-SHA256


# =========================
# Helpers Vault (PRI)
# =========================

def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s.encode("utf-8"))


def _derive_key(password: str, salt: bytes) -> bytes:
    import hashlib
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _KDF_ITERS,
        dklen=32
    )


def _vault_paths() -> tuple[str, int, str]:
    vault_dir = os.environ.get("PRIVATE_VAULT_DIR", "/mnt/archive/runtime")
    year = date.today().year
    year_file = os.path.join(vault_dir, f"{year}.enc")
    return vault_dir, year, year_file


def _atomic_write(path: str, data: bytes) -> None:
    tmp = f"{path}.tmp.{secrets.token_hex(6)}"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _empty_vault_payload(year: int) -> dict:
    # Struttura minima (la estenderemo quando integreremo i movimenti PRI)
    return {"version": 1, "year": year, "days": []}


def _vault_encrypt_json(payload_obj: dict, password: str) -> bytes:
    if AESGCM is None:
        raise RuntimeError("cryptography/AESGCM non disponibile")

    salt = secrets.token_bytes(16)
    key = _derive_key(password, salt)
    aes = AESGCM(key)
    nonce = secrets.token_bytes(12)

    plaintext = json.dumps(payload_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = aes.encrypt(nonce, plaintext, None)

    envelope = {
        "v": _VAULT_VERSION,
        "kdf": {"name": "pbkdf2-hmac-sha256", "iters": _KDF_ITERS, "salt": _b64e(salt)},
        "aead": {"name": "aes-256-gcm", "nonce": _b64e(nonce)},
        "ct": _b64e(ciphertext),
    }
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _vault_decrypt_json(blob: bytes, password: str) -> dict:
    if AESGCM is None:
        raise RuntimeError("cryptography/AESGCM non disponibile")

    env = json.loads(blob.decode("utf-8"))
    salt = _b64d(env["kdf"]["salt"])
    nonce = _b64d(env["aead"]["nonce"])
    ct = _b64d(env["ct"])

    key = _derive_key(password, salt)
    aes = AESGCM(key)
    pt = aes.decrypt(nonce, ct, None)
    return json.loads(pt.decode("utf-8"))


# =========================
# Views
# =========================

@cassa_bp.route("/agenda", methods=["GET"])
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def agenda():
    return render_template("agenda.html")


# =========================
# API: Day (già esistente)
# =========================

@cassa_bp.route("/api/day", methods=["GET"])
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_get_or_create_day():
    date_str = (request.args.get("date") or "").strip()

    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"ok": False, "error": "Invalid date format. Use YYYY-MM-DD"}), 400
    else:
        target_date = date.today()

    day = CashDay.query.filter_by(day_date=target_date).first()

    if not day:
        prev_date = target_date - timedelta(days=1)
        prev_day = CashDay.query.filter_by(day_date=prev_date).first()

        opening_float = 0
        if prev_day and prev_day.closure and prev_day.closure.closing_cash_drawer is not None:
            opening_float = float(prev_day.closure.closing_cash_drawer)

        day = CashDay(
            day_date=target_date,
            opening_float=opening_float,
            status="open",
        )
        db.session.add(day)
        db.session.commit()

    return jsonify({
        "ok": True,
        "day": {
            "id": day.id,
            "day_date": day.day_date.isoformat(),
            "status": day.status,
            "opening_float": float(day.opening_float or 0),
        }
    })


# =========================
# API: Vault privato (PRI)
# =========================

@cassa_bp.route("/api/private/status", methods=["GET"])
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_private_status():
    vault_dir, year, year_file = _vault_paths()

    mounted = os.path.ismount(vault_dir)
    year_file_exists = os.path.isfile(year_file)
    unlocked = bool(session.get("pri_vault_unlocked", False))

    return jsonify({
        "ok": True,
        "vault": {
            "vault_dir": vault_dir,
            "mounted": mounted,
            "year": year,
            "year_file_exists": year_file_exists,
            "unlocked": unlocked,
        }
    })


@cassa_bp.route("/api/private/unlock", methods=["POST"])
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_private_unlock():
    vault_dir, year, year_file = _vault_paths()

    if not os.path.ismount(vault_dir):
        return jsonify({"ok": False, "error": "Vault not available"}), 409

    data = request.get_json(silent=True) or {}
    password = (data.get("password") or "").strip()
    if not password:
        return jsonify({"ok": False, "error": "Missing password"}), 400

    try:
        if os.path.isfile(year_file):
            blob = open(year_file, "rb").read()
            _vault_decrypt_json(blob, password)  # valida password
        else:
            payload = _empty_vault_payload(year)
            blob = _vault_encrypt_json(payload, password)
            _atomic_write(year_file, blob)

        session["pri_vault_unlocked"] = True
        return jsonify({"ok": True, "vault": {"year": year, "unlocked": True}})
    except Exception as e:
        logger.warning("Vault unlock failed: %s", e)
        session["pri_vault_unlocked"] = False
        return jsonify({"ok": False, "error": "Invalid password"}), 401


@cassa_bp.route("/api/private/lock", methods=["POST"])
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_private_lock():
    session["pri_vault_unlocked"] = False
    return jsonify({"ok": True, "vault": {"unlocked": False}})
