import logging
import os
import json
import base64
import secrets

from cryptography.hazmat.primitives.ciphers.algorithms import AES
from flask import Blueprint, render_template, request, jsonify, session, current_app
from flask_login import login_required, current_user
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timedelta
from sqlalchemy import exists, or_, and_, func
from sqlalchemy.orm import selectinload

from tools.redis_utils import get_redis
from tools.log_utils import get_logger
from tools.check_utils import change_check_status
from tools.role_required import role_required
from extensions import db
from models import CashDay, CashSale, CashExpense, CashMove, PosMove, CashCheck, CashSalePayment, CashExpensePayment, \
    PosDevice, PosCircuit, pos_device_circuits, CashCustomer, CashCustomerAlias, CashBank, CashSaleCheck, \
    CashDrawerCount, CashDrawerCountLine, CashEcommerce, CashCheckEvent, CashOwnerTake, CashOwnerTakeCheck, \
    CashReceiptClosure, CashSalePaymentPosMove, CashRowCheck, CashIssuedCheck
from tools.cash_math import calculate_closure_pure, next_banking_day, _sum_amount

_ALLOWED_FLAGS = {"*", "**", "+", "x", "#", "!"}

_DRAWER_DENOMINATIONS = [
    Decimal("0.10"),
    Decimal("0.20"),
    Decimal("0.50"),
    Decimal("1.00"),
    Decimal("2.00"),
    Decimal("5.00"),
    Decimal("10.00"),
    Decimal("20.00"),
    Decimal("50.00"),
    Decimal("100.00"),
]

cassa_bp = Blueprint("cassa", __name__, url_prefix="/cassa")
logger = get_logger("cassa", level=logging.INFO)

MIN_AGENDA_WEIGHT = 40

_VAULT_VERSION = 1
_KDF_ITERS = 200_000

# -------------------------
# Helpers base64 + KDF
# -------------------------

def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s.encode("utf-8"))


def _get_cash_day_by_date_or_404(day_date: str):
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return None, (jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400)

    cash_day = CashDay.query.filter(CashDay.day_date == d).first()
    if not cash_day:
        return None, (jsonify({"ok": False, "error": "CashDay not found"}), 404)

    return cash_day, None


def _agenda_day_version_key(day_date) -> str:
    return f"agenda:day:{day_date}:version"


def _bump_agenda_day_version(day_date) -> None:
    try:
        r = get_redis()
        r.incr(_agenda_day_version_key(day_date))
    except Exception:
        logger.exception("Errore incremento agenda day version")


def _get_agenda_day_version(day_date) -> int:
    try:
        r = get_redis()
        return int(r.get(_agenda_day_version_key(day_date)) or 0)
    except Exception:
        return 0


def _serialize_drawer_count(drawer_count: CashDrawerCount | None):
    line_map = {}
    if drawer_count:
        for line in drawer_count.lines or []:
            line_map[str(Decimal(str(line.denomination)).quantize(Decimal("0.01")))] = line

    out_lines = []
    grand_total = Decimal("0")

    for denom in _DRAWER_DENOMINATIONS:
        key = str(denom.quantize(Decimal("0.01")))
        line = line_map.get(key)

        quantity = int(line.quantity) if line else 0
        line_total = Decimal(str(line.line_total)) if line else Decimal("0.00")
        grand_total += line_total

        out_lines.append({
            "denomination": key,
            "quantity": quantity,
            "line_total": str(line_total.quantize(Decimal("0.01"))),
        })

    return {
        "id": drawer_count.id if drawer_count else None,
        "notes": drawer_count.notes if drawer_count else None,
        "lines": out_lines,
        "grand_total": str(grand_total.quantize(Decimal("0.01"))),
    }


def _derive_key(password: str, salt: bytes) -> bytes:
    import hashlib
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _KDF_ITERS,
        dklen=32
    )

_VAULT_REDIS_KEY = "private_vault:unlocked"
_VAULT_STATE_VERSION_KEY = "private_vault:state_version"

def _vault_get_state_version() -> int:
    try:
        r = get_redis()
        return int(r.get(_VAULT_STATE_VERSION_KEY) or 0)
    except Exception:
        return 0

def _vault_set_unlocked_state(unlocked: bool) -> None:
    r = get_redis()

    new_value = "1" if unlocked else "0"
    old_value = r.get(_VAULT_REDIS_KEY)

    r.set(_VAULT_REDIS_KEY, new_value)

    # Incrementa la versione solo se lo stato cambia davvero
    if old_value != new_value:
        r.incr(_VAULT_STATE_VERSION_KEY)

def _vault_get_unlocked_state() -> bool:
    """
    Legge lo stato vault condiviso.
    Default sicuro: locked.
    """
    try:
        r = get_redis()
        return r.get(_VAULT_REDIS_KEY) == "1"
    except Exception:
        return False


def _vault_force_lock() -> None:
    """
    Lock globale del vault.
    Per ora aggiorna Redis e la sessione corrente.
    """
    try:
        _vault_set_unlocked_state(False)
    except Exception:
        logger.exception("Errore aggiornamento stato vault Redis")

    session["pri_vault_unlocked"] = False


def _pri_find_sale(year: int, sale_id: str):
    """
    Cerca una sale PRI nel vault annuale.
    Ritorna: (pri_data, day_node, sale_index, sale_dict) oppure (None, None, None, None)
    """
    pri_data = _pri_load_year(year)

    for day_node in pri_data.get("days", []):
        sales = day_node.get("sales") or []
        for idx, row in enumerate(sales):
            if row.get("id") == sale_id:
                return pri_data, day_node, idx, row

    return None, None, None, None


def _pri_update_sale(year: int, sale_id: str, updates: dict):
    pri_data, day_node, idx, row = _pri_find_sale(year, sale_id)

    if not pri_data:
        return None

    for k, v in updates.items():
        row[k] = v

    row["updated_at"] = datetime.now().isoformat()

    saved = _pri_save_year(year, pri_data)
    if not saved:
        return False

    return row


def _pri_set_sale_checked(year: int, sale_id: str, is_checked: bool):
    pri_data, day_node, idx, row = _pri_find_sale(year, sale_id)

    if not pri_data:
        return None

    row["is_checked"] = bool(is_checked)
    row["updated_at"] = datetime.now().isoformat()

    saved = _pri_save_year(year, pri_data)
    if not saved:
        return False

    return row


def _pri_set_cash_move_checked(year: int, move_id: str, is_checked: bool):
    pri_data, day_node, idx, row = _pri_find_cash_move(year, move_id)

    if not pri_data:
        return None

    row["is_checked"] = bool(is_checked)
    row["updated_at"] = datetime.now().isoformat()

    saved = _pri_save_year(year, pri_data)
    if not saved:
        return False

    return row


def _pri_update_cash_move(year: int, move_id: str, updates: dict):
    pri_data, day_node, idx, row = _pri_find_cash_move(year, move_id)

    if not pri_data:
        return None

    # merge controllato
    for k, v in updates.items():
        row[k] = v

    row["updated_at"] = datetime.now().isoformat()

    saved = _pri_save_year(year, pri_data)
    if not saved:
        return False

    return row


def _pri_find_expense(year: int, expense_id: str):
    """
    Cerca una expense PRI nel vault annuale.
    Ritorna: (pri_data, day_node, expense_index, expense_dict) oppure (None, None, None, None)
    """
    pri_data = _pri_load_year(year)

    for day_node in pri_data.get("days", []):
        expenses = day_node.get("expenses") or []
        for idx, row in enumerate(expenses):
            if row.get("id") == expense_id:
                return pri_data, day_node, idx, row

    return None, None, None, None


def _pri_update_expense(year: int, expense_id: str, updates: dict):
    pri_data, day_node, idx, row = _pri_find_expense(year, expense_id)

    if not pri_data:
        return None

    for k, v in updates.items():
        row[k] = v

    row["updated_at"] = datetime.now().isoformat()

    saved = _pri_save_year(year, pri_data)
    if not saved:
        return False

    return row


def _pri_set_expense_checked(year: int, expense_id: str, is_checked: bool):
    pri_data, day_node, idx, row = _pri_find_expense(year, expense_id)

    if not pri_data:
        return None

    row["is_checked"] = bool(is_checked)
    row["updated_at"] = datetime.now().isoformat()

    saved = _pri_save_year(year, pri_data)
    if not saved:
        return False

    return row


def _pri_find_cash_move(year: int, move_id: str):
    """
    Cerca un cash_move PRI nel vault annuale.
    Ritorna: (pri_data, day_node, move_index, move_dict) oppure (None, None, None, None)
    """
    pri_data = _pri_load_year(year)

    for day_node in pri_data.get("days", []):
        cash_moves = day_node.get("cash_moves") or []
        for idx, row in enumerate(cash_moves):
            if row.get("id") == move_id:
                return pri_data, day_node, idx, row

    return None, None, None, None


def _pri_store_session_key(key: bytes, salt: bytes) -> str:
    key_id = secrets.token_urlsafe(32)
    r = get_redis()
    r.set(
        f"pri_vault:key:{key_id}",
        json.dumps({
            "key": _b64e(key),
            "salt": _b64e(salt),
        })
    )
    return key_id


def _pri_get_session_key() -> bytes | None:
    key_id = session.get("pri_vault_key_id")
    if not key_id:
        return None

    r = get_redis()
    raw = r.get(f"pri_vault:key:{key_id}")
    if not raw:
        return None

    data = json.loads(raw)
    return _b64d(data["key"])


def _pri_get_session_salt() -> bytes | None:
    key_id = session.get("pri_vault_key_id")
    if not key_id:
        return None

    r = get_redis()
    raw = r.get(f"pri_vault:key:{key_id}")
    if not raw:
        return None

    data = json.loads(raw)
    return _b64d(data["salt"])


def _pri_clear_session_key() -> None:
    key_id = session.pop("pri_vault_key_id", None)
    if key_id:
        r = get_redis()
        r.delete(f"pri_vault:key:{key_id}")


def _pri_load_year(year: int) -> dict:
    """
    Carica e decifra il file annuale PRI usando la chiave di sessione in RAM.
    """
    if not session.get("pri_vault_unlocked"):
        raise RuntimeError("Vault non sbloccato")

    key = _pri_get_session_key()
    if not key:
        session["pri_vault_unlocked"] = False
        raise RuntimeError("Chiave vault non disponibile in sessione")

    mount_root, vault_dir, _cfg_year, year_file = _vault_config()

    if not os.path.ismount(mount_root):
        session["pri_vault_unlocked"] = False
        _pri_clear_session_key()
        raise RuntimeError("Vault non montato")

    file_path = os.path.join(vault_dir, f"{year}.enc")

    if not os.path.isfile(file_path):
        return _empty_vault_payload(year)

    with open(file_path, "rb") as f:
        blob = f.read()

    env = json.loads(blob.decode("utf-8"))
    nonce = _b64d(env["aead"]["nonce"])
    ct = _b64d(env["ct"])

    aes = AESGCM(key)
    pt = aes.decrypt(nonce, ct, None)
    return json.loads(pt.decode("utf-8"))


def _pri_save_year(year: int, data: dict) -> bool|None:
    """
    Cifra e salva il file annuale PRI usando:
    - chiave derivata già presente in RAM
    - salt stabile della sessione vault
    - stesso formato file già usato da _encrypt_payload/_decrypt_payload
    """
    if not session.get("pri_vault_unlocked"):
        raise RuntimeError("Vault non sbloccato")

    key = _pri_get_session_key()
    salt = _pri_get_session_salt()

    if not key or not salt:
        session["pri_vault_unlocked"] = False
        _pri_clear_session_key()
        raise RuntimeError("Chiave vault non disponibile in sessione")

    mount_root, vault_dir, _cfg_year, _year_file = _vault_config()

    if not os.path.ismount(mount_root):
        session["pri_vault_unlocked"] = False
        _pri_clear_session_key()
        return False

    os.makedirs(vault_dir, exist_ok=True)

    file_path = os.path.join(vault_dir, f"{year}.enc")

    plaintext = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    aes = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ct = aes.encrypt(nonce, plaintext, None)

    env = {
        "v": _VAULT_VERSION,
        "kdf": {
            "name": "pbkdf2-hmac-sha256",
            "iters": _KDF_ITERS,
            "salt": _b64e(salt),
        },
        "aead": {
            "name": "aes-256-gcm",
            "nonce": _b64e(nonce),
        },
        "ct": _b64e(ct),
    }

    blob = json.dumps(env, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    try:
        _atomic_write(file_path, blob)
        return True
    except OSError:
        session["pri_vault_unlocked"] = False
        _pri_clear_session_key()
        return False


def _vault_config() -> tuple[str, str, int, str]:
    """
    mount_root: directory che risulta ismount() quando la chiavetta è inserita (es: /mnt/archive/runtime)
    vault_dir:  directory dati dentro mount_root (es: /mnt/archive/runtime/.rt)
    """
    mount_root = os.environ.get("PRIVATE_VAULT_MOUNT_ROOT", "/mnt/archive/runtime").rstrip("/")
    default_vault_dir = os.path.join(mount_root, ".rt")
    vault_dir = os.environ.get("PRIVATE_VAULT_DIR", default_vault_dir).rstrip("/")

    year = date.today().year
    year_file = os.path.join(vault_dir, f"{year}.enc")
    return mount_root, vault_dir, year, year_file


def _vault_device_path() -> str:
    uuid = os.environ.get("PRIVATE_VAULT_DEVICE_UUID", "8504e0b7-47f7-4532-b680-27079279ddf7")
    return f"/dev/disk/by-uuid/{uuid}"


def _vault_device_present() -> bool:
    try:
        return os.path.exists(_vault_device_path())
    except Exception:
        return False


def _atomic_write(path: str, data: bytes) -> None:
    tmp = f"{path}.tmp.{secrets.token_hex(6)}"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _empty_vault_payload(year: int) -> dict:
    return {"version": 1, "year": year, "days": []}


def _encrypt_payload(payload: dict, password: str) -> bytes:
    salt = secrets.token_bytes(16)
    key = _derive_key(password, salt)
    aes = AESGCM(key)
    nonce = secrets.token_bytes(12)

    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ct = aes.encrypt(nonce, plaintext, None)

    env = {
        "v": _VAULT_VERSION,
        "kdf": {"name": "pbkdf2-hmac-sha256", "iters": _KDF_ITERS, "salt": _b64e(salt)},
        "aead": {"name": "aes-256-gcm", "nonce": _b64e(nonce)},
        "ct": _b64e(ct),
    }
    return json.dumps(env, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _decrypt_payload(blob: bytes, password: str) -> dict:
    env = json.loads(blob.decode("utf-8"))
    salt = _b64d(env["kdf"]["salt"])
    nonce = _b64d(env["aead"]["nonce"])
    ct = _b64d(env["ct"])

    key = _derive_key(password, salt)
    aes = AESGCM(key)
    pt = aes.decrypt(nonce, ct, None)
    return json.loads(pt.decode("utf-8"))


def _dir_writable(path: str) -> bool:
    try:
        testfile = os.path.join(path, f".__wtest_{secrets.token_hex(6)}")
        with open(testfile, "wb") as f:
            f.write(b"1")
        os.remove(testfile)
        return True
    except Exception:
        return False


def _get_previous_check_status_before_deposit(check_id: int):
    """
    Restituisce lo stato precedente all'ultimo evento 'deposited' per l'assegno.
    Usa la cronologia CashCheckEvent ordinata per created_at/id.
    """
    events = (
        CashCheckEvent.query
        .filter(CashCheckEvent.check_id == check_id)
        .order_by(CashCheckEvent.created_at.asc(), CashCheckEvent.id.asc())
        .all()
    )

    if not events:
        return None

    deposited_idx = None
    for idx in range(len(events) - 1, -1, -1):
        ev = events[idx]
        if ev.to_status == "deposited":
            deposited_idx = idx
            break

    if deposited_idx is None:
        return None

    if deposited_idx == 0:
        return None

    prev_event = events[deposited_idx - 1]
    return prev_event.to_status


@cassa_bp.delete("/api/deposits/<int:deposit_id>")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_delete_deposit(deposit_id):
    from models import CashDeposit, CashDepositCheck

    deposit = (
        CashDeposit.query
        .options(
            selectinload(CashDeposit.checks)
            .selectinload(CashDepositCheck.check)
        )
        .filter(CashDeposit.id == deposit_id)
        .first()
    )

    if not deposit:
        return jsonify({"ok": False, "error": "Versamento non trovato"}), 404

    try:
        linked_checks = [link.check for link in (deposit.checks or []) if link.check]

        for check in linked_checks:
            prev_status = _get_previous_check_status_before_deposit(check.id)

            if not prev_status:
                return jsonify({
                    "ok": False,
                    "error": f"Impossibile determinare lo stato precedente per assegno {check.id}"
                }), 400

            change_check_status(
                check=check,
                new_status=prev_status,
                user_id=getattr(current_user, "id", None),
                event_date=deposit.deposit_date or date.today(),
                note=f"Eliminazione versamento ID {deposit.id}",
                amount_spese=Decimal("0"),
                customer_charge_amount=Decimal("0"),
            )

        day_version_date = (deposit.deposit_date or date.today()).isoformat()

        db.session.delete(deposit)
        db.session.commit()
        _bump_agenda_day_version(day_version_date)

        return jsonify({
            "ok": True,
            "deposit_id": deposit_id,
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("api_delete_deposit error: %s", e)
        return jsonify({
            "ok": False,
            "error": "Errore interno durante l'eliminazione del versamento"
        }), 500


# =========================
# Views
# =========================

@cassa_bp.route("/agenda", methods=["GET"])
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def agenda():
    return render_template("agenda.html")


# =========================
# API: Day
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

    opening_float = float(_find_latest_previous_cash_balance(target_date) or 0)

    day = CashDay.query.filter_by(day_date=target_date).first()

    if not day:
        day = CashDay(
            day_date=target_date,
            opening_float=opening_float,
            status="open",
        )
        db.session.add(day)
        db.session.commit()
    else:
        current_opening = float(day.opening_float or 0)
        if day.status != "closed" and current_opening != opening_float:
            day.opening_float = opening_float
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

@cassa_bp.post("/api/private/test-write")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_private_test_write():
    try:
        mount_root, vault_dir, year, year_file = _vault_config()

        if not session.get("pri_vault_unlocked"):
            return jsonify({"ok": False, "error": "Vault non sbloccato"}), 400

        data = _pri_load_year(year)

        test_day = date.today().isoformat()

        day_node = next((d for d in data["days"] if d["date"] == test_day), None)
        if not day_node:
            day_node = {
                "date": test_day,
                "sales": [],
                "expenses": [],
                "cash_moves": [],
            }
            data["days"].append(day_node)

        day_node["cash_moves"].append({
            "id": f"test-{secrets.token_hex(4)}",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "kind": "altro",
            "description": "TEST PRI API",
            "amount": 12.34,
            "method": "cash",
            "flag": "x",
            "off_cash": False,
            "meta": {
                "origin": "pri",
                "created_by_user_id": getattr(current_user, "id", None),
                "created_by_name": getattr(current_user, "name", None)
                    or getattr(current_user, "username", None)
                    or "user",
            }
        })

        saved = _pri_save_year(year, data)

        reread = _pri_load_year(year)

        return jsonify({
            "ok": True,
            "saved": bool(saved),
            "year": year,
            "days": reread.get("days", []),
        })

    except Exception as e:
        logger.exception("api_private_test_write error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@cassa_bp.route("/api/private/status", methods=["GET"])
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_private_status():
    mount_root, vault_dir, year, year_file = _vault_config()

    device_present = _vault_device_present()

    if not device_present:
        _vault_force_lock()

        return jsonify({
            "ok": True,
            "vault": {
                "mount_root": mount_root,
                "device_present": False,
                "mounted": False,
                "vault_dir": vault_dir,
                "vault_dir_exists": False,
                "vault_dir_writable": False,
                "year": year,
                "year_file_exists": False,
                "unlocked": False,
                "state_version": _vault_get_state_version(),
            }
        })

    mounted = os.path.ismount(mount_root)

    vault_dir_exists = False
    vault_dir_writable = False
    year_file_exists = False

    if mounted:
        vault_dir_exists = os.path.isdir(vault_dir)
        vault_dir_writable = vault_dir_exists and _dir_writable(vault_dir)
        year_file_exists = os.path.isfile(year_file)

    unlocked = _vault_get_unlocked_state()

    if not mounted or not vault_dir_exists or not vault_dir_writable or not year_file_exists:
        _vault_force_lock()
        unlocked = False

    session["pri_vault_unlocked"] = unlocked

    return jsonify({
        "ok": True,
        "vault": {
            "mount_root": mount_root,
            "device_present": True,
            "mounted": mounted,
            "vault_dir": vault_dir,
            "vault_dir_exists": vault_dir_exists,
            "vault_dir_writable": vault_dir_writable,
            "year": year,
            "year_file_exists": year_file_exists,
            "unlocked": unlocked,
            "state_version": _vault_get_state_version(),
        }
    })


@cassa_bp.route("/api/private/unlock", methods=["POST"])
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_private_unlock():
    mount_root, vault_dir, year, year_file = _vault_config()

    if not _vault_device_present() or not os.path.ismount(mount_root):
        _vault_force_lock()

        return jsonify({
            "ok": True,
            "vault": {
                "year": year,
                "unlocked": False,
                "mounted": False,
                "year_file_exists": False,
                "reason": "vault_not_mounted",
            }
        })

    # se la chiavetta è montata ma la dir dati non esiste, creiamola
    try:
        os.makedirs(vault_dir, exist_ok=True)
    except Exception as e:
        logger.error("Vault dir create failed: %s", e)
        return jsonify({"ok": False, "error": "Vault dir not available"}), 500

    if not _dir_writable(vault_dir):
        return jsonify({"ok": False, "error": "Vault not writable"}), 500

    data = request.get_json(silent=True) or {}
    password = (data.get("password") or "").strip()
    if not password:
        return jsonify({"ok": False, "error": "Missing password"}), 400

    try:
        if os.path.isfile(year_file):
            blob = open(year_file, "rb").read()

            # estrai salt dal file
            env = json.loads(blob.decode("utf-8"))
            salt = _b64d(env["kdf"]["salt"])

            # deriva chiave
            key = _derive_key(password, salt)

            # valida password tentando decrypt
            aes = AESGCM(key)
            nonce = _b64d(env["aead"]["nonce"])
            ct = _b64d(env["ct"])
            aes.decrypt(nonce, ct, None)

        else:
            # primo avvio → crea vault
            salt = secrets.token_bytes(16)
            key = _derive_key(password, salt)

            payload = _empty_vault_payload(year)

            aes = AESGCM(key)
            nonce = secrets.token_bytes(12)
            plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ct = aes.encrypt(nonce, plaintext, None)

            env = {
                "v": _VAULT_VERSION,
                "kdf": {"name": "pbkdf2-hmac-sha256", "iters": _KDF_ITERS, "salt": _b64e(salt)},
                "aead": {"name": "aes-256-gcm", "nonce": _b64e(nonce)},
                "ct": _b64e(ct),
            }

            _atomic_write(year_file, json.dumps(env, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

        # salva chiave in RAM
        key_id = _pri_store_session_key(key, salt)

        _vault_set_unlocked_state(True)
        session["pri_vault_unlocked"] = True
        session["pri_vault_key_id"] = key_id

        return jsonify({"ok": True, "vault": {"year": year, "unlocked": True, "year_file_exists": True}})
    except InvalidTag:
        _vault_force_lock()
        return jsonify({"ok": False, "error": "Invalid password"}), 401
    except Exception as e:
        logger.exception("Vault unlock unexpected error: %s", e)
        _vault_force_lock()
        return jsonify({"ok": False, "error": "Vault error"}), 500


@cassa_bp.route("/api/private/lock", methods=["POST"])
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_private_lock():
    _vault_force_lock()
    return jsonify({"ok": True, "vault": {"unlocked": False}})


# ------------------------------------------------------------
# Totali live (preview) per giornata
# view=fiscal | complete
# ------------------------------------------------------------

FISCAL_FLAGS = {"*", "**", "#", "!"}
ALL_FLAGS = {"*", "**", "+", "x", "#", "!"}

# regole flags (quelle che hai definito)
FLAG_RULES = {
    "*":  {"cash": True,  "q": True,  "s": True},
    "**": {"cash": True,  "q": False, "s": True},
    "+":  {"cash": True,  "q": False, "s": False},
    "x":  {"cash": True,  "q": False, "s": False},
    "#":  {"cash": False, "q": False, "s": False},
    "!":  {"cash": False, "q": True,  "s": True},
}

def _to_dec(x) -> Decimal:
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))

def _pick_flags(view: str) -> set[str]:
    return FISCAL_FLAGS if view == "fiscal" else ALL_FLAGS

def _compute_day_totals_from_db(cash_day, view: str) -> dict:
    """
    Calcolo live basato SOLO su DB aziendale.
    Nota: per 'complete' includiamo +/x solo se sono presenti nel DB (oggi lo sono),
    ma quando attiveremo il vault, +/x verranno spostati lì e qui resteranno fiscali.
    """
    allowed_flags = _pick_flags(view)

    cash_in = Decimal("0")
    cash_out = Decimal("0")
    q_versabile = Decimal("0")
    s_versabile = Decimal("0")

    # --- INCASSI (sales payments)
    for sale in cash_day.sales:
        for p in sale.payments:
            flag = (p.flag or "*").strip()
            if flag not in allowed_flags:
                continue

            amt = _to_dec(p.amount)
            # in/out
            direction = (p.direction or "in").strip()

            # 1) Totale cassa (solo se cash=True e NON off_cash e metodo cash)
            if FLAG_RULES.get(flag, {}).get("cash") is True:
                if (p.off_cash is False) and (p.method == "cash"):
                    if direction == "in":
                        cash_in += amt
                    else:
                        cash_out += amt  # raro su sale, ma gestito

            # 2) Quota/S saldo versabile: per ora lo aggancio SOLO agli incassi (direction in)
            if direction == "in":
                if FLAG_RULES.get(flag, {}).get("q") is True:
                    q_versabile += amt
                if FLAG_RULES.get(flag, {}).get("s") is True:
                    s_versabile += amt

    # --- SPESE (expense payments) incidono sulla cassa se cash=True e cash method
    for exp in cash_day.expenses:
        for p in exp.payments:
            flag = (p.flag or "*").strip()
            if flag not in allowed_flags:
                continue
            amt = _to_dec(p.amount)
            direction = (p.direction or "out").strip()

            if FLAG_RULES.get(flag, {}).get("cash") is True:
                if (p.off_cash is False) and (p.method == "cash"):
                    # spese normalmente "out"
                    if direction == "out":
                        cash_out += amt
                    else:
                        cash_in += amt

            # Nota: versabile NON viene influenzato dalle spese (per definizione tua)

    # --- POS moves: per ora li esponiamo e li sommiamo separati.
    # In seguito, quando modelleremo bene corrispettivi vs POS scontrini vs POS fatture,
    # qui applicheremo le compensazioni come da tua regola.
    pos_in = Decimal("0")
    pos_out = Decimal("0")
    for pm in cash_day.pos_moves:
        amt = _to_dec(pm.amount)
        direction = (pm.direction or "in").strip()
        if direction == "in":
            pos_in += amt
        else:
            pos_out += amt

    total_cash = cash_in - cash_out

    return {
        "view": view,
        "cash_in": float(cash_in),
        "cash_out": float(cash_out),
        "total_cash": float(total_cash),
        "q_versabile": float(q_versabile),
        "s_versabile": float(s_versabile),
        "pos_in": float(pos_in),
        "pos_out": float(pos_out),
        "pos_net": float(pos_in - pos_out),
    }


def _calculate_progressive_saldo_versabile(cash_day: CashDay) -> Decimal:
    """
    Ricostruisce il saldo versabile progressivo della giornata,
    partendo dall'ultima giornata precedente disponibile.
    """
    if not cash_day:
        return Decimal("0")

    prev_day = (
        CashDay.query
        .filter(CashDay.day_date < cash_day.day_date)
        .order_by(CashDay.day_date.desc())
        .first()
    )

    saldo_prev = Decimal("0")
    if prev_day:
        saldo_prev = _calculate_progressive_saldo_versabile(prev_day)

    result = calculate_closure_pure(
        cash_day_id=cash_day.id,
        opening_float=Decimal(str(cash_day.opening_float or 0)),
        total_corrispettivi=Decimal("0"),
        fondo_finale=Decimal("0"),
        saldo_versabile_precedente=saldo_prev,
        saldo_movimenti_cassa=Decimal("0"),
        incasso_consegnato=Decimal("0"),
    )

    return Decimal(str(result.get("saldo_versabile", 0)))


@cassa_bp.get("/api/day/<day_date>/preview")
@role_required(40)
def api_cash_day_preview(day_date):
    """
    Preview live dei totali per la giornata.
    Querystring:
      - view=fiscal|complete (default fiscal)
    """
    view = (request.args.get("view") or "fiscal").strip().lower()
    if view not in ("fiscal", "complete"):
        view = "fiscal"

    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    # Carico con eager loading per evitare N+1.
    cash_day = (
        CashDay.query
        .options(
            selectinload(CashDay.sales).selectinload(CashSale.payments),
            selectinload(CashDay.expenses).selectinload(CashExpense.payments),
            selectinload(CashDay.drawer_count).selectinload(CashDrawerCount.lines),
        )
        .filter(CashDay.day_date == d)
        .first()
    )

    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    CHECK_IN_PANCIA = {"received", "spostato", "anticipato"}
    cutoff = next_banking_day(d)

    # Somma assegni "in pancia" versabili entro cutoff
    assegni_versabili = (
        db.session.query(func.coalesce(func.sum(CashCheck.amount), 0))
        .filter(
            CashCheck.status.in_(CHECK_IN_PANCIA),
            CashCheck.due_date <= cutoff,
        )
        .scalar()
    )

    # Somma assegni "in pancia" postdatati oltre cutoff
    assegni_postdatati = (
        db.session.query(func.coalesce(func.sum(CashCheck.amount), 0))
        .filter(
            CashCheck.status.in_(CHECK_IN_PANCIA),
            CashCheck.due_date > cutoff,
        )
        .scalar()
    )

    saldo_prev_qs = request.args.get("saldo_prev")
    if saldo_prev_qs is not None and str(saldo_prev_qs).strip() != "":
        saldo_versabile_precedente = Decimal(str(saldo_prev_qs))
    else:
        prev_day = (
            CashDay.query
            .filter(CashDay.day_date < d)
            .order_by(CashDay.day_date.desc())
            .first()
        )
        saldo_versabile_precedente = (
            _calculate_progressive_saldo_versabile(prev_day) if prev_day else Decimal("0")
        )

    fondo_finale_qs = request.args.get("fondo_finale")
    if fondo_finale_qs is not None and str(fondo_finale_qs).strip() != "":
        fondo_finale = Decimal(str(fondo_finale_qs))
    else:
        fondo_finale = _get_drawer_count_total_for_day(cash_day)

    totale_corrispettivi = (
        db.session.query(func.coalesce(func.sum(CashReceiptClosure.amount), 0))
        .filter(CashReceiptClosure.cash_day_id == cash_day.id)
        .scalar()
    )
    totale_corrispettivi = Decimal(str(totale_corrispettivi or 0))

    totale_owner_take_cash = (
        db.session.query(func.coalesce(func.sum(CashOwnerTake.cash_amount), 0))
        .filter(CashOwnerTake.cash_day_id == cash_day.id)
        .scalar()
    )

    totale_owner_take_checks = (
        db.session.query(func.coalesce(func.sum(CashOwnerTake.check_amount), 0))
        .filter(CashOwnerTake.cash_day_id == cash_day.id)
        .scalar()
    )

    totale_cash_moves_in = (
        db.session.query(func.coalesce(func.sum(CashMove.amount), 0))
        .filter(
            CashMove.cash_day_id == cash_day.id,
            CashMove.direction == "in",
        )
        .scalar()
    )

    totale_cash_moves_out = (
        db.session.query(func.coalesce(func.sum(CashMove.amount), 0))
        .filter(
            CashMove.cash_day_id == cash_day.id,
            CashMove.direction == "out",
        )
        .scalar()
    )

    totale_owner_take_cash = Decimal(str(totale_owner_take_cash or 0))
    totale_owner_take_checks = Decimal(str(totale_owner_take_checks or 0))
    totale_cash_moves_in = Decimal(str(totale_cash_moves_in or 0))
    totale_cash_moves_out = Decimal(str(totale_cash_moves_out or 0))

    saldo_movimenti_cassa = totale_cash_moves_in - totale_cash_moves_out

    # =========================
    # Totali PRI per modalità full
    # =========================
    pri_sales_cash = Decimal("0")
    pri_expenses_cash = Decimal("0")
    pri_cash_moves_in = Decimal("0")
    pri_cash_moves_out = Decimal("0")

    vault_unlocked = _vault_get_unlocked_state()
    include_pri = vault_unlocked and view == "complete"

    if include_pri:
        try:
            pri_data = _pri_load_year(d.year)
            day_node = next((x for x in pri_data.get("days", []) if x.get("date") == d.isoformat()), None)

            if day_node:
                for row in day_node.get("sales", []):
                    if row.get("method") == "cash":
                        pri_sales_cash += Decimal(str(row.get("amount") or 0))

                for row in day_node.get("expenses", []):
                    if row.get("method") == "cash":
                        pri_expenses_cash += Decimal(str(row.get("amount") or 0))

                for row in day_node.get("cash_moves", []):
                    amount = Decimal(str(row.get("amount") or 0))
                    if row.get("direction") == "in":
                        pri_cash_moves_in += amount
                    else:
                        pri_cash_moves_out += amount

        except Exception as e:
            logger.exception("Errore calcolo preview PRI: %s", e)

    pri_cash_net = (
        pri_sales_cash
        - pri_expenses_cash
        + pri_cash_moves_in
        - pri_cash_moves_out
    )

    totale_incasso_consegnato = (
        totale_owner_take_cash
        + totale_owner_take_checks
    )

    result = calculate_closure_pure(
        cash_day_id=cash_day.id,
        opening_float=cash_day.opening_float,
        total_corrispettivi=totale_corrispettivi,
        fondo_finale=fondo_finale,
        saldo_versabile_precedente=saldo_versabile_precedente,
        saldo_movimenti_cassa=saldo_movimenti_cassa,
        incasso_consegnato=totale_incasso_consegnato,
    )

    result["incasso_consegnato"] = float(totale_incasso_consegnato)
    result["owner_take_cash_amount"] = float(totale_owner_take_cash)
    result["owner_take_check_amount"] = float(totale_owner_take_checks)
    result["cash_moves_in_amount"] = float(totale_cash_moves_in)
    result["cash_moves_out_amount"] = float(totale_cash_moves_out)
    result["cash_moves_net_amount"] = float(saldo_movimenti_cassa)
    result["total_corrispettivi"] = float(totale_corrispettivi)
    result["pri_sales_cash"] = float(pri_sales_cash)
    result["pri_expenses_cash"] = float(pri_expenses_cash)
    result["pri_cash_moves_in"] = float(pri_cash_moves_in)
    result["pri_cash_moves_out"] = float(pri_cash_moves_out)
    result["pri_cash_net"] = float(pri_cash_net)
    result["view_mode"] = "full" if include_pri else "fiscal"

    # =========================
    # Display full/fiscal per KPI
    # =========================
    vault_unlocked = _vault_get_unlocked_state()

    valore_atteso_fiscal = Decimal(str(result.get("valore_atteso_cassetto", 0)))
    incasso_calcolato_fiscal = Decimal(str(result.get("incasso_calcolato", 0)))
    delta_quadratura_fiscal = Decimal(str(result.get("delta_quadratura", 0)))

    if vault_unlocked:
        valore_atteso_display = valore_atteso_fiscal + pri_cash_net
        incasso_calcolato_display = incasso_calcolato_fiscal + pri_cash_net
        delta_quadratura_display = totale_incasso_consegnato - valore_atteso_display
    else:
        valore_atteso_display = valore_atteso_fiscal
        incasso_calcolato_display = incasso_calcolato_fiscal
        delta_quadratura_display = delta_quadratura_fiscal

    result["valore_atteso_cassetto_fiscal"] = float(valore_atteso_fiscal)
    result["incasso_calcolato_fiscal"] = float(incasso_calcolato_fiscal)
    result["delta_quadratura_fiscal"] = float(delta_quadratura_fiscal)

    result["valore_atteso_cassetto"] = float(valore_atteso_display)
    result["incasso_calcolato"] = float(incasso_calcolato_display)
    result["delta_quadratura"] = float(delta_quadratura_display)

    has_owner_take_rows = (
                              db.session.query(func.count(CashOwnerTake.id))
                              .filter(CashOwnerTake.cash_day_id == cash_day.id)
                              .scalar()
                          ) > 0

    has_cash_move_rows = (
                             db.session.query(func.count(CashMove.id))
                             .filter(CashMove.cash_day_id == cash_day.id)
                             .scalar()
                         ) > 0

    quadratura_available = bool(
        (has_owner_take_rows or has_cash_move_rows)
        and result.get("has_corrispettivi")
        and result.get("has_fondo_iniziale")
        and result.get("has_fondo_finale")
    )

    if quadratura_available:
        dq = Decimal(str(result.get("delta_quadratura", 0)))

        if dq < Decimal("-5.00"):
            quadratura_led = "red_low"
        elif dq < Decimal("-2.00"):
            quadratura_led = "yellow_low"
        elif dq <= Decimal("2.00"):
            quadratura_led = "green"
        elif dq <= Decimal("5.00"):
            quadratura_led = "yellow_high"
        else:
            quadratura_led = "red_high"
    else:
        quadratura_led = "off"

    result["quadratura_available"] = quadratura_available
    result["quadratura_led"] = quadratura_led

    totale_ecommerce = (
        db.session.query(func.coalesce(func.sum(CashEcommerce.amount), 0))
        .filter(CashEcommerce.cash_day_id == cash_day.id)
        .scalar()
    )

    result["totale_ecommerce"] = float(totale_ecommerce or 0)
    result["saldo_versabile_precedente"] = float(saldo_versabile_precedente or 0)
    result["saldo_versabile_init"] = float(saldo_versabile_precedente or 0)
    result["fondo_finale"] = float(fondo_finale or 0)

    return jsonify({
        "ok": True,
        "day": {
            "id": cash_day.id,
            "day_date": cash_day.day_date.isoformat(),
        },
        "totals": result,
        "checks_debug": {
            "cutoff_bancabile": cutoff.isoformat(),
            "in_pancia_status": sorted(list(CHECK_IN_PANCIA)),
            "versabili": float(assegni_versabili or 0),
            "postdatati": float(assegni_postdatati or 0),
        }
    })

@cassa_bp.get("/api/days/active")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_days_active():
    """
    Ritorna i giorni che hanno movimentazioni (sales/expenses/cash_moves/pos_moves).
    Querystring:
      - from=YYYY-MM-DD
      - to=YYYY-MM-DD
    Se non passati: mese corrente.
    """
    from_str = (request.args.get("from") or "").strip()
    to_str = (request.args.get("to") or "").strip()

    today = date.today()
    if not from_str or not to_str:
        first = today.replace(day=1)
        # fine mese: primo giorno mese successivo - 1
        next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        last = next_month - timedelta(days=1)
        d_from, d_to = first, last
    else:
        try:
            d_from = datetime.strptime(from_str, "%Y-%m-%d").date()
            d_to = datetime.strptime(to_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"ok": False, "error": "Invalid date format. Use YYYY-MM-DD"}), 400

    if d_from > d_to:
        return jsonify({"ok": False, "error": "Invalid range: from > to"}), 400

    # Hard cap semplice per evitare range enormi
    if (d_to - d_from).days > 370:
        return jsonify({"ok": False, "error": "Range too large (max 370 days)"}), 400

    q = (
        CashDay.query
        .filter(CashDay.day_date.between(d_from, d_to))
        .filter(or_(
            exists().where(CashSale.cash_day_id == CashDay.id),
            exists().where(CashExpense.cash_day_id == CashDay.id),
            exists().where(CashMove.cash_day_id == CashDay.id),
            exists().where(PosMove.cash_day_id == CashDay.id),
        ))
        .with_entities(CashDay.day_date, CashDay.status)
        .order_by(CashDay.day_date.asc())
        .all()
    )

    return jsonify({
        "ok": True,
        "from": d_from.isoformat(),
        "to": d_to.isoformat(),
        "days": [{"day_date": d.isoformat(), "status": s} for d, s in q]
    })


@cassa_bp.post("/api/customers")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_create_customer():
    """
    Crea una nuova anagrafica cliente con eventuali alias.
    Payload:
    {
      "display_name": "Davide (DFL SRL)",
      "ragione_sociale": "DFL SRL",
      "partita_iva": "01234567890",
      "codice_cliente": "1539",
      "aliases": ["Davide", "Armando", "Bar One"]
    }
    """
    data = request.get_json(silent=True) or {}

    display_name = (data.get("display_name") or "").strip()
    ragione_sociale = (data.get("ragione_sociale") or "").strip() or None
    partita_iva = (data.get("partita_iva") or "").strip() or None
    codice_cliente = (data.get("codice_cliente") or "").strip() or None

    raw_aliases = data.get("aliases") or []
    if not isinstance(raw_aliases, list):
        return jsonify({"ok": False, "error": "aliases must be a list"}), 400

    aliases = []
    seen = set()
    for a in raw_aliases:
        s = str(a or "").strip()
        if not s:
            continue
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        aliases.append(s)

    if not display_name:
        if ragione_sociale:
            display_name = ragione_sociale
        elif aliases:
            display_name = aliases[0]
        else:
            return jsonify({"ok": False, "error": "Missing display_name"}), 400

    # controllo soft duplicati principali
    duplicate = CashCustomer.query.filter(
        or_(
            func.lower(CashCustomer.display_name) == display_name.lower(),
            and_(partita_iva is not None, CashCustomer.partita_iva == partita_iva),
            and_(codice_cliente is not None, CashCustomer.codice_cliente == codice_cliente),
        )
    ).first()

    if duplicate:
        return jsonify({
            "ok": False,
            "error": "Customer already exists",
            "customer_id": duplicate.id,
            "display": duplicate.display_name,
        }), 409

    customer = CashCustomer(
        display_name=display_name,
        ragione_sociale=ragione_sociale,
        partita_iva=partita_iva,
        codice_cliente=codice_cliente,
    )

    db.session.add(customer)
    db.session.flush()  # ottengo customer.id senza commit

    for alias in aliases:
        db.session.add(CashCustomerAlias(
            customer_id=customer.id,
            alias=alias,
        ))

    db.session.commit()

    return jsonify({
        "ok": True,
        "customer": {
            "id": customer.id,
            "display": customer.display_name,
            "display_name": customer.display_name,
            "ragione_sociale": customer.ragione_sociale,
            "partita_iva": customer.partita_iva,
            "codice_cliente": customer.codice_cliente,
            "aliases": aliases,
        }
    }), 201


@cassa_bp.get("/api/customers/suggest")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_customers_suggest():
    """
    Ricerca progressiva clienti.
    Querystring:
      - q=... (min 2 char)
    Ritorna:
      customers: [{id, display, display_name, ragione_sociale, partita_iva, codice_cliente, matched_alias}]
    """
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"ok": True, "customers": []})

    like = f"%{q}%"

    # Outerjoin per includere anche clienti senza alias
    rows = (
        db.session.query(
            CashCustomer.id,
            CashCustomer.display_name,
            CashCustomer.ragione_sociale,
            CashCustomer.partita_iva,
            CashCustomer.codice_cliente,
            CashCustomerAlias.alias,
        )
        .outerjoin(CashCustomerAlias, CashCustomerAlias.customer_id == CashCustomer.id)
        .filter(
            or_(
                CashCustomerAlias.alias.ilike(like),
                CashCustomer.display_name.ilike(like),
                CashCustomer.ragione_sociale.ilike(like),
                CashCustomer.partita_iva.ilike(like),
                CashCustomer.codice_cliente.ilike(like),
            )
        )
        .order_by(
            CashCustomer.ragione_sociale.asc().nullslast(),
            CashCustomer.display_name.asc().nullslast(),
            CashCustomer.id.asc(),
        )
        .limit(20)
        .all()
    )

    out = []
    for (cid, display_name, ragione_sociale, piva, codice_cliente, alias) in rows:
        base = (alias or display_name or "").strip()
        rs = (ragione_sociale or "").strip()

        # Se matcho per alias e ho ragione sociale: "davide (DFL SRL)"
        if alias and rs and base.lower() != rs.lower():
            display = f"{base} ({rs})"
        else:
            # fallback: display_name o ragione sociale o altro
            display = base or rs or (codice_cliente or "").strip() or (piva or "").strip() or f"Cliente {cid}"

        out.append({
            "id": cid,
            "display": display,
            "display_name": display_name,
            "ragione_sociale": ragione_sociale,
            "partita_iva": piva,
            "codice_cliente": codice_cliente,
            "matched_alias": alias,
        })

    # Dedup: outerjoin può produrre più righe (più alias)
    seen = set()
    dedup = []
    for x in out:
        k = (x["id"], x["display"])
        if k in seen:
            continue
        seen.add(k)
        dedup.append(x)

    return jsonify({"ok": True, "customers": dedup})


def _to_decimal_amount(value, field_name="amount"):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError(f"Invalid {field_name}")
    if amount <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return amount


def _validate_pos_pair(pos_device_id, pos_circuit_id):
    dev = PosDevice.query.filter_by(id=pos_device_id, is_active=True).first()
    if not dev:
        raise ValueError("PosDevice not found or inactive")

    cir = PosCircuit.query.filter_by(id=pos_circuit_id, is_active=True).first()
    if not cir:
        raise ValueError("PosCircuit not found or inactive")

    allowed = db.session.query(pos_device_circuits).filter(
        pos_device_circuits.c.pos_device_id == pos_device_id,
        pos_device_circuits.c.pos_circuit_id == pos_circuit_id
    ).first()
    if not allowed:
        raise ValueError("Circuit not associated to this POS device")


def _validate_bank(bank_id):
    bank = CashBank.query.filter_by(id=bank_id, is_active=True).first()
    if not bank:
        raise ValueError("CashBank not found or inactive")
    return bank


def _parse_due_date(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Invalid due_date format (YYYY-MM-DD)")


def _normalize_payments_payload(data):
    payments = data.get("payments")
    if not isinstance(payments, list) or not payments:
        raise ValueError("payments must be a non-empty list")
    return payments


def _get_drawer_count_total_for_day(cash_day: CashDay) -> Decimal:
    if not cash_day or not getattr(cash_day, "drawer_count", None):
        return Decimal("0")

    total = Decimal("0")
    for line in (cash_day.drawer_count.lines or []):
        total += Decimal(str(line.line_total or 0))

    return total.quantize(Decimal("0.01"))


def _find_latest_previous_cash_balance(target_date: date) -> Decimal:
    """
    Restituisce l'ultimo fondo cassa finale disponibile prima di target_date.
    Scorre le giornate precedenti in ordine decrescente e prende la prima
    che abbia una fonte valida (CashClosure o CashDrawerCount).
    """
    previous_days = (
        CashDay.query
        .options(
            selectinload(CashDay.closure),
            selectinload(CashDay.drawer_count).selectinload(CashDrawerCount.lines),
        )
        .filter(CashDay.day_date < target_date)
        .order_by(CashDay.day_date.desc())
        .all()
    )

    for day in previous_days:
        has_closure_value = (
            getattr(day, "closure", None) is not None and
            day.closure.closing_cash_drawer is not None
        )
        has_drawer_count = getattr(day, "drawer_count", None) is not None

        if has_closure_value or has_drawer_count:
            return _get_effective_closing_cash_drawer_for_day(day)

    return Decimal("0")


def _get_effective_closing_cash_drawer_for_day(cash_day: CashDay) -> Decimal:
    """
    Restituisce il fondo cassa finale effettivo della giornata scegliendo
    tra CashClosure e CashDrawerCount.
    Vince la fonte più recente tra le due.
    """
    if not cash_day:
        return Decimal("0")

    closure_value = None
    closure_ts = None
    if getattr(cash_day, "closure", None) and cash_day.closure.closing_cash_drawer is not None:
        closure_value = Decimal(str(cash_day.closure.closing_cash_drawer))
        closure_ts = cash_day.closure.created_at

    drawer_value = None
    drawer_ts = None
    if getattr(cash_day, "drawer_count", None):
        drawer_value = _get_drawer_count_total_for_day(cash_day)
        drawer_ts = cash_day.drawer_count.updated_at or cash_day.drawer_count.created_at

    if closure_value is None and drawer_value is None:
        return Decimal("0")

    if closure_value is not None and drawer_value is None:
        return closure_value.quantize(Decimal("0.01"))

    if drawer_value is not None and closure_value is None:
        return drawer_value.quantize(Decimal("0.01"))

    if drawer_ts and closure_ts:
        if drawer_ts >= closure_ts:
            return drawer_value.quantize(Decimal("0.01"))
        return closure_value.quantize(Decimal("0.01"))

    return drawer_value.quantize(Decimal("0.01")) if drawer_ts else closure_value.quantize(Decimal("0.01"))


@cassa_bp.get("/api/checks/due")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_checks_due():
    """
    Ritorna assegni "versabili dalla giornata selezionata":
    - riferimento: date=YYYY-MM-DD (default: oggi)
    - cutoff bancabile: next_banking_day(date)
    - include_today_received=1/0 (default 1)
    - status in (received, spostato, anticipato) (+ retrocompat moved/advanced)
    """
    date_str = (request.args.get("date") or "").strip()

    if date_str:
        try:
            ref_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"ok": False, "error": "Invalid date format. Use YYYY-MM-DD"}), 400
    else:
        ref_date = date.today()

    cutoff = next_banking_day(ref_date)

    include_today_received = (request.args.get("include_today_received") or "1").strip().lower() in ("1", "true", "yes")

    # status corretti + retrocompat
    versabili_status = ("received", "spostato", "anticipato", "moved", "advanced")

    q = CashCheck.query.filter(
        CashCheck.due_date <= cutoff,
        CashCheck.status.in_(versabili_status),
    )

    if not include_today_received:
        q = q.filter(CashCheck.received_date != ref_date)

    checks = (
        q.order_by(CashCheck.due_date.asc(), CashCheck.received_date.asc(), CashCheck.id.asc())
         .limit(50)
         .all()
    )

    items = []
    for c in checks:
        items.append({
            "id": c.id,
            "check_number": c.check_number,
            "bank_name": c.bank_name,
            "abi": c.abi,
            "cab": c.cab,
            "amount": float(c.amount),
            "received_date": c.received_date.isoformat() if c.received_date else None,
            "due_date": c.due_date.isoformat() if c.due_date else None,
            "status": c.status,
            "customer": {
                "id": c.customer.id if c.customer else None,
                "display_name": getattr(c.customer, "display_name", None),
            } if c.customer_id else None,
            "is_received_today": bool(c.received_date == ref_date),
            "is_overdue": bool(c.due_date < ref_date),
        })

    return jsonify({
        "ok": True,
        "ref_date": ref_date.isoformat(),
        "cutoff_bancabile": cutoff.isoformat(),
        "checks": items
    })


@cassa_bp.post("/api/day/<day_date>/sales")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_create_sale(day_date):
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    cash_day = CashDay.query.filter(CashDay.day_date == d).first()
    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    data = request.get_json(silent=True) or {}

    flag = (data.get("flag") or "*").strip()
    if flag not in _ALLOWED_FLAGS:
        return jsonify({"ok": False, "error": f"Invalid flag (allowed: {sorted(_ALLOWED_FLAGS)})"}), 400

    description = (data.get("description") or "").strip() or None

    customer_id = data.get("customer_id")
    customer_label = (data.get("customer_label") or "").strip() or None

    if not description and not customer_id and not customer_label:
        return jsonify({
            "ok": False,
            "error": "Inserisci almeno una descrizione o seleziona un cliente"
        }), 400
    off_cash = bool(data.get("off_cash", False))

    if customer_id:
        customer = CashCustomer.query.filter_by(id=customer_id).first()
        if not customer:
            return jsonify({"ok": False, "error": "Customer not found"}), 400

    try:
        payments_data = _normalize_payments_payload(data)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    # =========================
    # CASO PRI (vault)
    # regola: incasso personale = solo cash, flag x/+
    # =========================
    if flag in {"x", "+"}:
        all_cash = all(((p.get("method") or "").strip().lower() == "cash") for p in payments_data)
        if not all_cash:
            return jsonify({
                "ok": False,
                "error": "Gli incassi PRI supportano solo pagamenti cash"
            }), 400

        if len(payments_data) != 1:
            return jsonify({
                "ok": False,
                "error": "Gli incassi PRI supportano solo un pagamento singolo cash"
            }), 400

        if not session.get("pri_vault_unlocked"):
            return jsonify({"ok": False, "error": "Vault privato non sbloccato"}), 409

        try:
            amount = _to_decimal_amount(payments_data[0].get("amount"), "amount")
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        year = d.year
        pri_data = _pri_load_year(year)

        day_node = next((x for x in pri_data["days"] if x["date"] == d.isoformat()), None)
        if not day_node:
            day_node = {
                "date": d.isoformat(),
                "sales": [],
                "expenses": [],
                "cash_moves": [],
            }
            pri_data["days"].append(day_node)

        pri_row = {
            "id": f"pri-sale-{secrets.token_hex(8)}",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "customer_id": None,
            "customer_label": customer_label,
            "description": description,
            "amount": float(amount),
            "method": "cash",
            "flag": flag,
            "off_cash": bool(off_cash),
            "is_checked": False,
            "meta": {
                "origin": "pri",
                "created_by_user_id": getattr(current_user, "id", None),
                "created_by_name": getattr(current_user, "name", None)
                    or getattr(current_user, "username", None)
                    or "user",
            }
        }

        day_node["sales"].append(pri_row)

        saved = _pri_save_year(year, pri_data)
        if not saved:
            return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

        _bump_agenda_day_version(d.isoformat())

        return jsonify({
            "ok": True,
            "sale_id": pri_row["id"],
            "storage": "pri",
        }), 201

    sale = CashSale(
        cash_day_id=cash_day.id,
        created_by_user_id=getattr(current_user, "id", None),
        customer_id=customer_id,
        customer_label=customer_label,
        notes=description,
    )

    db.session.add(sale)
    db.session.flush()

    try:
        for idx, p in enumerate(payments_data, start=1):
            method = (p.get("method") or "").strip().lower()
            if method not in {"cash", "pos", "bank", "check"}:
                raise ValueError(f"Invalid payment method at row {idx}")

            amount = _to_decimal_amount(p.get("amount"), f"payments[{idx}].amount")

            payment = CashSalePayment(
                sale_id=sale.id,
                direction="in",
                method=method,
                off_cash=off_cash,
                amount=amount,
                flag=flag,
                description=description,
            )
            db.session.add(payment)
            db.session.flush()

            if method == "pos":
                pos_device_id = p.get("pos_device_id")
                pos_circuit_id = p.get("pos_circuit_id")
                if not pos_device_id or not pos_circuit_id:
                    raise ValueError(f"Missing POS device/circuit at row {idx}")

                _validate_pos_pair(pos_device_id, pos_circuit_id)

                # 1) il pagamento resta un CashSalePayment di tipo POS
                #    ma non porta più in sé device/circuit
                # 2) il movimento reale vive in PosMove
                # 3) il legame payment <-> pos_move vive nella tabella ponte

                pos_move = PosMove(
                    cash_day_id=cash_day.id,
                    created_by_user_id=getattr(current_user, "id", None),
                    direction="in",
                    amount=amount,
                    pos_device_id=pos_device_id,
                    pos_circuit_id=pos_circuit_id,
                    doc_ref="INCASSO",
                    notes=description,
                )
                db.session.add(pos_move)
                db.session.flush()

                db.session.add(
                    CashSalePaymentPosMove(
                        sale_payment_id=payment.id,
                        pos_move_id=pos_move.id,
                    )
                )

            elif method == "bank":
                bank_id = p.get("bank_id")
                if not bank_id:
                    raise ValueError(f"Missing bank_id at row {idx}")
                _validate_bank(bank_id)
                payment.bank_id = bank_id

            elif method == "check":
                if not customer_id:
                    raise ValueError(f"Customer required for check payment at row {idx}")

                bank_name = (p.get("bank_name") or "").strip()
                abi = (p.get("abi") or "").strip() or None
                cab = (p.get("cab") or "").strip() or None
                check_number = (p.get("check_number") or "").strip()
                due_date_raw = p.get("due_date")

                if not bank_name:
                    raise ValueError(f"Missing bank_name at row {idx}")
                if not check_number:
                    raise ValueError(f"Missing check_number at row {idx}")
                if not due_date_raw:
                    raise ValueError(f"Missing due_date at row {idx}")

                due_date = _parse_due_date(due_date_raw)

                check = CashCheck(
                    check_number=check_number,
                    abi=abi,
                    cab=cab,
                    bank_name=bank_name,
                    customer_id=customer_id,
                    amount=amount,
                    received_date=d,
                    due_date=due_date,
                    status="received",
                    note=description,
                )
                db.session.add(check)
                db.session.flush()

                change_check_status(
                    check=check,
                    new_status="received",
                    user_id=getattr(current_user, "id", None),
                    event_date=d,
                    note=description,
                    amount_spese=Decimal("0"),
                    customer_charge_amount=Decimal("0"),
                )

                sale.checks.append(
                    CashSaleCheck(
                        check_id=check.id,
                        check_amount=amount,
                    )
                )

        db.session.add(sale)
        db.session.commit()
        _bump_agenda_day_version(d.isoformat())

    except ValueError as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception("api_create_sale error: %s", e)
        return jsonify({"ok": False, "error": "Internal error while creating sale"}), 500

    return jsonify({"ok": True, "sale_id": sale.id}), 201


@cassa_bp.get("/api/day/<day_date>/sales")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_list_sales(day_date):
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    cash_day = (
        CashDay.query
        .options(
            selectinload(CashDay.sales)
            .selectinload(CashSale.payments)
            .selectinload(CashSalePayment.pos_links)
            .selectinload(CashSalePaymentPosMove.pos_move),
            selectinload(CashDay.sales)
            .selectinload(CashSale.checks)
            .selectinload(CashSaleCheck.check),
        )
        .filter(CashDay.day_date == d)
        .first()
    )

    items = []

    if cash_day:
        for s in cash_day.sales:
            sale_checks = list(s.checks or [])
            check_idx = 0

            pay = []
            for p in (s.payments or []):
                row = {
                    "id": p.id,
                    "direction": p.direction,
                    "method": p.method,
                    "off_cash": bool(p.off_cash),
                    "amount": float(p.amount or 0),
                    "flag": p.flag,
                    "description": p.description,
                    "bank_id": p.bank_id,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "storage": "az",
                }

                if p.method == "pos":
                    pos_link = (p.pos_links or [None])[0]
                    pos_move = pos_link.pos_move if pos_link and pos_link.pos_move else None

                    row.update({
                        "pos_move_id": pos_move.id if pos_move else None,
                        "pos_device_id": pos_move.pos_device_id if pos_move else None,
                        "pos_circuit_id": pos_move.pos_circuit_id if pos_move else None,
                        "doc_ref": pos_move.doc_ref if pos_move else None,
                        "notes": pos_move.notes if pos_move else None,
                    })

                elif p.method == "check":
                    linked_sale_check = sale_checks[check_idx] if check_idx < len(sale_checks) else None
                    linked_check = linked_sale_check.check if linked_sale_check and linked_sale_check.check else None
                    check_idx += 1

                    row.update({
                        "check_id": linked_check.id if linked_check else None,
                        "bank_name": linked_check.bank_name if linked_check else None,
                        "abi": linked_check.abi if linked_check else None,
                        "cab": linked_check.cab if linked_check else None,
                        "check_number": linked_check.check_number if linked_check else None,
                        "due_date": linked_check.due_date.isoformat() if linked_check and linked_check.due_date else None,
                    })

                pay.append(row)

            items.append({
                "id": s.id,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "customer_id": s.customer_id,
                "customer_label": s.customer_label,
                "doc_ref": s.doc_ref,
                "notes": s.notes,
                "payments": pay,
                "storage": "az",
            })

    # =========================
    # Merge PRI (vault)
    # =========================
    if session.get("pri_vault_unlocked"):
        try:
            pri_data = _pri_load_year(d.year)
            day_node = next((x for x in pri_data["days"] if x["date"] == d.isoformat()), None)

            if day_node:
                for row in day_node.get("sales", []):
                    items.append({
                        "id": row["id"],
                        "created_at": row.get("created_at"),
                        "customer_id": None,
                        "customer_label": row.get("customer_label"),
                        "doc_ref": None,
                        "notes": row.get("description"),
                        "storage": "pri",
                        "is_checked": bool(row.get("is_checked", False)),
                        "payments": [
                            {
                                "id": f'{row["id"]}-pay',
                                "direction": "in",
                                "method": row.get("method", "cash"),
                                "off_cash": bool(row.get("off_cash", False)),
                                "amount": float(row.get("amount", 0)),
                                "flag": row.get("flag"),
                                "description": row.get("description"),
                                "bank_id": None,
                                "created_at": row.get("created_at"),
                                "storage": "pri",
                            }
                        ],
                    })
        except Exception as e:
            logger.exception("Errore lettura PRI sales: %s", e)

    items.sort(key=lambda x: x.get("created_at") or "")

    return jsonify({"ok": True, "day_date": d.isoformat(), "sales": items})


@cassa_bp.delete("/api/sales/<sale_id>")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_delete_sale(sale_id):

    # =========================
    # CASO PRI (vault)
    # =========================
    if isinstance(sale_id, str) and sale_id.startswith("pri-sale-"):
        if not session.get("pri_vault_unlocked"):
            return jsonify({"ok": False, "error": "Vault privato non sbloccato"}), 409

        year = date.today().year
        pri_data, day_node, idx, row = _pri_find_sale(year, sale_id)

        if not pri_data:
            return jsonify({"ok": False, "error": "Incasso PRI non trovato"}), 404

        del day_node["sales"][idx]

        saved = _pri_save_year(year, pri_data)
        if not saved:
            return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

        _bump_agenda_day_version(day_node["date"])

        return jsonify({
            "ok": True,
            "sale_id": sale_id,
            "storage": "pri",
        })

    # =========================
    # CASO DB aziendale
    # =========================
    try:
        sale_id_int = int(sale_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid sale_id"}), 400

    sale = (
        CashSale.query
        .options(
            selectinload(CashSale.payments).selectinload(CashSalePayment.pos_links),
            selectinload(CashSale.checks).selectinload(CashSaleCheck.check),
        )
        .filter(CashSale.id == sale_id_int)
        .first()
    )

    if not sale:
        return jsonify({"ok": False, "error": "Incasso non trovato"}), 404

    try:
        CashRowCheck.query.filter_by(
            entity_type="sale",
            entity_id=sale.id
        ).delete()

        for sale_check in (sale.checks or []):
            linked_check = sale_check.check
            if linked_check:
                db.session.delete(linked_check)

        for payment in (sale.payments or []):
            for link in (payment.pos_links or []):
                if link.pos_move:
                    CashRowCheck.query.filter_by(
                        entity_type="pos_move",
                        entity_id=link.pos_move.id
                    ).delete()

                    db.session.delete(link.pos_move)

        cash_day = CashDay.query.filter_by(id=sale.cash_day_id).first()
        day_version_date = cash_day.day_date.isoformat() if cash_day else date.today().isoformat()

        db.session.delete(sale)
        db.session.commit()
        _bump_agenda_day_version(day_version_date)

        return jsonify({
            "ok": True,
            "sale_id": sale_id_int,
            "storage": "az",
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("api_delete_sale error: %s", e)
        return jsonify({
            "ok": False,
            "error": "Errore interno durante l'eliminazione dell'incasso"
        }), 500


@cassa_bp.put("/api/sales/<sale_id>")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_update_sale(sale_id):

    data = request.get_json(silent=True) or {}

    flag = (data.get("flag") or "*").strip()
    if flag not in _ALLOWED_FLAGS:
        return jsonify({"ok": False, "error": f"Invalid flag (allowed: {sorted(_ALLOWED_FLAGS)})"}), 400

    description = (data.get("description") or "").strip() or None

    customer_id = data.get("customer_id")
    customer_label = (data.get("customer_label") or "").strip() or None

    if not description and not customer_id and not customer_label:
        return jsonify({
            "ok": False,
            "error": "Inserisci almeno una descrizione o seleziona un cliente"
        }), 400
    off_cash = bool(data.get("off_cash", False))

    if customer_id:
        customer = CashCustomer.query.filter_by(id=customer_id).first()
        if not customer:
            return jsonify({"ok": False, "error": "Customer not found"}), 400

    try:
        payments_data = _normalize_payments_payload(data)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    # =========================
    # CASO PRI (vault)
    # =========================
    if isinstance(sale_id, str) and sale_id.startswith("pri-sale-"):
        if not session.get("pri_vault_unlocked"):
            return jsonify({"ok": False, "error": "Vault privato non sbloccato"}), 409

        if flag not in {"x", "+"}:
            if not session.get("pri_vault_unlocked"):
                return jsonify({"ok": False, "error": "Vault privato non sbloccato"}), 409

            year = date.today().year
            pri_data, day_node, idx, pri_row = _pri_find_sale(year, sale_id)

            if not pri_data:
                return jsonify({"ok": False, "error": "Incasso PRI non trovato"}), 404

            try:
                d_pri = datetime.strptime(day_node["date"], "%Y-%m-%d").date()
            except Exception:
                return jsonify({"ok": False, "error": "Data incasso PRI non valida"}), 400

            cash_day = CashDay.query.filter(CashDay.day_date == d_pri).first()
            if not cash_day:
                cash_day = CashDay(
                    day_date=d_pri,
                    opening_float=float(_find_latest_previous_cash_balance(d_pri) or 0),
                    status="open",
                )
                db.session.add(cash_day)
                db.session.flush()

            sale = CashSale(
                cash_day_id=cash_day.id,
                created_by_user_id=getattr(current_user, "id", None),
                customer_id=customer_id,
                customer_label=customer_label,
                notes=description,
            )

            db.session.add(sale)
            db.session.flush()

            try:
                for idx_p, p in enumerate(payments_data, start=1):
                    method = (p.get("method") or "").strip().lower()
                    if method not in {"cash", "pos", "bank", "check"}:
                        raise ValueError(f"Invalid payment method at row {idx_p}")

                    amount = _to_decimal_amount(p.get("amount"), f"payments[{idx_p}].amount")

                    payment = CashSalePayment(
                        sale_id=sale.id,
                        direction="in",
                        method=method,
                        off_cash=off_cash,
                        amount=amount,
                        flag=flag,
                        description=description,
                    )
                    db.session.add(payment)
                    db.session.flush()

                    if method == "pos":
                        pos_device_id = p.get("pos_device_id")
                        pos_circuit_id = p.get("pos_circuit_id")
                        if not pos_device_id or not pos_circuit_id:
                            raise ValueError(f"Missing POS device/circuit at row {idx_p}")

                        _validate_pos_pair(pos_device_id, pos_circuit_id)

                        pos_move = PosMove(
                            cash_day_id=cash_day.id,
                            created_by_user_id=getattr(current_user, "id", None),
                            direction="in",
                            amount=amount,
                            pos_device_id=pos_device_id,
                            pos_circuit_id=pos_circuit_id,
                            doc_ref="INCASSO",
                            notes=description,
                        )
                        db.session.add(pos_move)
                        db.session.flush()

                        db.session.add(
                            CashSalePaymentPosMove(
                                sale_payment_id=payment.id,
                                pos_move_id=pos_move.id,
                            )
                        )

                    elif method == "bank":
                        bank_id = p.get("bank_id")
                        if not bank_id:
                            raise ValueError(f"Missing bank_id at row {idx_p}")
                        _validate_bank(bank_id)
                        payment.bank_id = bank_id

                    elif method == "check":
                        if not customer_id:
                            raise ValueError(f"Customer required for check payment at row {idx_p}")

                        bank_name = (p.get("bank_name") or "").strip()
                        abi = (p.get("abi") or "").strip() or None
                        cab = (p.get("cab") or "").strip() or None
                        check_number = (p.get("check_number") or "").strip()
                        due_date_raw = p.get("due_date")

                        if not bank_name:
                            raise ValueError(f"Missing bank_name at row {idx_p}")
                        if not check_number:
                            raise ValueError(f"Missing check_number at row {idx_p}")
                        if not due_date_raw:
                            raise ValueError(f"Missing due_date at row {idx_p}")

                        due_date = _parse_due_date(due_date_raw)

                        check = CashCheck(
                            check_number=check_number,
                            abi=abi,
                            cab=cab,
                            bank_name=bank_name,
                            customer_id=customer_id,
                            amount=amount,
                            received_date=d_pri,
                            due_date=due_date,
                            status="received",
                            note=description,
                        )
                        db.session.add(check)
                        db.session.flush()

                        change_check_status(
                            check=check,
                            new_status="received",
                            user_id=getattr(current_user, "id", None),
                            event_date=d_pri,
                            note=description,
                            amount_spese=Decimal("0"),
                            customer_charge_amount=Decimal("0"),
                        )

                        db.session.add(
                            CashSaleCheck(
                                sale_id=sale.id,
                                check_id=check.id,
                                check_amount=amount,
                            )
                        )

                del day_node["sales"][idx]

                saved = _pri_save_year(year, pri_data)
                if not saved:
                    db.session.rollback()
                    return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

                db.session.commit()
                _bump_agenda_day_version(d_pri.isoformat())

                return jsonify({
                    "ok": True,
                    "sale_id": sale.id,
                    "storage": "az",
                    "migrated": "pri_to_az",
                })

            except ValueError as e:
                db.session.rollback()
                return jsonify({"ok": False, "error": str(e)}), 400
            except Exception as e:
                db.session.rollback()
                logger.exception("api_update_sale PRI->AZ error: %s", e)
                return jsonify({
                    "ok": False,
                    "error": "Errore interno durante migrazione incasso PRI -> AZ"
                }), 500

        if len(payments_data) != 1 or (payments_data[0].get("method") or "").strip().lower() != "cash":
            return jsonify({
                "ok": False,
                "error": "Gli incassi PRI supportano solo un pagamento singolo cash"
            }), 400

        try:
            amount = _to_decimal_amount(payments_data[0].get("amount"), "amount")
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        year = date.today().year

        updated_row = _pri_update_sale(year, sale_id, {
            "customer_id": None,
            "customer_label": customer_label,
            "description": description,
            "amount": float(amount),
            "method": "cash",
            "flag": flag,
            "off_cash": bool(off_cash),
        })

        if updated_row is None:
            return jsonify({"ok": False, "error": "Incasso PRI non trovato"}), 404

        if updated_row is False:
            return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

        pri_data, day_node, _, _ = _pri_find_sale(year, sale_id)
        if day_node:
            _bump_agenda_day_version(day_node["date"])

        return jsonify({
            "ok": True,
            "sale_id": sale_id,
            "storage": "pri",
        })

    try:
        sale_id_int = int(sale_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid sale_id"}), 400

    sale = (
        CashSale.query
        .options(
            selectinload(CashSale.payments)
            .selectinload(CashSalePayment.pos_links)
            .selectinload(CashSalePaymentPosMove.pos_move),
            selectinload(CashSale.checks).selectinload(CashSaleCheck.check),
        )
        .filter(CashSale.id == sale_id_int)
        .first()
    )

    if not sale:
        return jsonify({"ok": False, "error": "Incasso non trovato"}), 404

    # =========================
    # MIGRAZIONE AZ -> PRI
    # =========================
    if flag in {"x", "+"}:
        existing_payments = list(sale.payments or [])

        existing_is_single_cash = (
            len(existing_payments) == 1
            and existing_payments[0].method == "cash"
        )

        incoming_is_single_cash = (
            len(payments_data) == 1
            and (payments_data[0].get("method") or "").strip().lower() == "cash"
        )

        if not existing_is_single_cash or not incoming_is_single_cash:
            return jsonify({
                "ok": False,
                "error": "Impossibile trasformare una registrazione con pagamenti multipli o non cash in una registrazione privata. Cancella il movimento ed esegui una nuova registrazione."
            }), 400

        if not session.get("pri_vault_unlocked"):
            return jsonify({"ok": False, "error": "Vault privato non sbloccato"}), 409

        try:
            amount = _to_decimal_amount(payments_data[0].get("amount"), "amount")
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        cash_day = CashDay.query.filter_by(id=sale.cash_day_id).first()
        if not cash_day:
            return jsonify({"ok": False, "error": "CashDay not found"}), 404

        year = cash_day.day_date.year
        pri_data = _pri_load_year(year)

        day_node = next((x for x in pri_data["days"] if x["date"] == cash_day.day_date.isoformat()), None)
        if not day_node:
            day_node = {
                "date": cash_day.day_date.isoformat(),
                "sales": [],
                "expenses": [],
                "cash_moves": [],
            }
            pri_data["days"].append(day_node)

        pri_row = {
            "id": f"pri-sale-{secrets.token_hex(8)}",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "customer_id": None,
            "customer_label": customer_label,
            "description": description,
            "amount": float(amount),
            "method": "cash",
            "flag": flag,
            "off_cash": bool(off_cash),
            "is_checked": False,
            "meta": {
                "origin": "pri",
                "migrated_from": "az",
                "az_sale_id": sale.id,
                "created_by_user_id": getattr(current_user, "id", None),
                "created_by_name": getattr(current_user, "name", None)
                    or getattr(current_user, "username", None)
                    or "user",
            }
        }

        day_node["sales"].append(pri_row)

        saved = _pri_save_year(year, pri_data)
        if not saved:
            return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

        try:
            CashRowCheck.query.filter_by(
                entity_type="sale",
                entity_id=sale.id
            ).delete()

            for sale_check in (sale.checks or []):
                linked_check = sale_check.check
                if linked_check:
                    db.session.delete(linked_check)

            for payment in (sale.payments or []):
                for link in (payment.pos_links or []):
                    if link.pos_move:
                        CashRowCheck.query.filter_by(
                            entity_type="pos_move",
                            entity_id=link.pos_move.id
                        ).delete()
                        db.session.delete(link.pos_move)

            db.session.delete(sale)
            db.session.commit()
            _bump_agenda_day_version(cash_day.day_date.isoformat())

            return jsonify({
                "ok": True,
                "sale_id": pri_row["id"],
                "storage": "pri",
                "migrated": "az_to_pri",
            })

        except Exception as e:
            db.session.rollback()
            logger.exception("api_update_sale AZ->PRI delete error: %s", e)
            return jsonify({
                "ok": False,
                "error": "Incasso salvato nel vault, ma errore durante la rimozione dal DB aziendale"
            }), 500

    cash_day = CashDay.query.filter_by(id=sale.cash_day_id).first()
    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    day_date = cash_day.day_date

    try:
        # 1) elimina eventuali assegni collegati
        for sale_check in (sale.checks or []):
            linked_check = sale_check.check
            if linked_check:
                db.session.delete(linked_check)

        # 2) elimina eventuali pos_move collegati ai pagamenti POS
        for payment in (sale.payments or []):
            for link in (payment.pos_links or []):
                if link.pos_move:
                    CashRowCheck.query.filter_by(
                        entity_type="pos_move",
                        entity_id=link.pos_move.id
                    ).delete()
                    db.session.delete(link.pos_move)

        db.session.flush()

        # 3) elimina righe ponte assegni e pagamenti
        CashSaleCheck.query.filter_by(sale_id=sale.id).delete()
        CashSalePayment.query.filter_by(sale_id=sale.id).delete()
        db.session.flush()

        # 4) aggiorna testata incasso
        sale.customer_id = customer_id
        sale.customer_label = customer_label
        sale.notes = description

        # 5) ricrea pagamenti
        for idx, p in enumerate(payments_data, start=1):
            method = (p.get("method") or "").strip().lower()
            if method not in {"cash", "pos", "bank", "check"}:
                raise ValueError(f"Invalid payment method at row {idx}")

            amount = _to_decimal_amount(p.get("amount"), f"payments[{idx}].amount")

            payment = CashSalePayment(
                sale_id=sale.id,
                direction="in",
                method=method,
                off_cash=off_cash,
                amount=amount,
                flag=flag,
                description=description,
            )
            db.session.add(payment)
            db.session.flush()

            if method == "pos":
                pos_device_id = p.get("pos_device_id")
                pos_circuit_id = p.get("pos_circuit_id")
                if not pos_device_id or not pos_circuit_id:
                    raise ValueError(f"Missing POS device/circuit at row {idx}")

                _validate_pos_pair(pos_device_id, pos_circuit_id)

                pos_move = PosMove(
                    cash_day_id=cash_day.id,
                    created_by_user_id=getattr(current_user, "id", None),
                    direction="in",
                    amount=amount,
                    pos_device_id=pos_device_id,
                    pos_circuit_id=pos_circuit_id,
                    doc_ref="INCASSO",
                    notes=description,
                )
                db.session.add(pos_move)
                db.session.flush()

                db.session.add(
                    CashSalePaymentPosMove(
                        sale_payment_id=payment.id,
                        pos_move_id=pos_move.id,
                    )
                )

            elif method == "bank":
                bank_id = p.get("bank_id")
                if not bank_id:
                    raise ValueError(f"Missing bank_id at row {idx}")
                _validate_bank(bank_id)
                payment.bank_id = bank_id

            elif method == "check":
                if not customer_id:
                    raise ValueError(f"Customer required for check payment at row {idx}")

                bank_name = (p.get("bank_name") or "").strip()
                abi = (p.get("abi") or "").strip() or None
                cab = (p.get("cab") or "").strip() or None
                check_number = (p.get("check_number") or "").strip()
                due_date_raw = p.get("due_date")

                if not bank_name:
                    raise ValueError(f"Missing bank_name at row {idx}")
                if not check_number:
                    raise ValueError(f"Missing check_number at row {idx}")
                if not due_date_raw:
                    raise ValueError(f"Missing due_date at row {idx}")

                due_date = _parse_due_date(due_date_raw)

                check = CashCheck(
                    check_number=check_number,
                    abi=abi,
                    cab=cab,
                    bank_name=bank_name,
                    customer_id=customer_id,
                    amount=amount,
                    received_date=day_date,
                    due_date=due_date,
                    status="received",
                    note=description,
                )
                db.session.add(check)
                db.session.flush()

                change_check_status(
                    check=check,
                    new_status="received",
                    user_id=getattr(current_user, "id", None),
                    event_date=day_date,
                    note=description,
                    amount_spese=Decimal("0"),
                    customer_charge_amount=Decimal("0"),
                )

                db.session.add(
                    CashSaleCheck(
                        sale_id=sale.id,
                        check_id=check.id,
                        check_amount=amount,
                    )
                )

        db.session.commit()
        _bump_agenda_day_version(day_date.isoformat())

        return jsonify({
            "ok": True,
            "sale_id": sale.id
        })

    except ValueError as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception("api_update_sale error: %s", e)
        return jsonify({
            "ok": False,
            "error": "Errore interno durante la modifica dell'incasso"
        }), 500


@cassa_bp.delete("/api/pos_moves/<int:pos_move_id>")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_delete_pos_move(pos_move_id):
    pos_move = PosMove.query.filter_by(id=pos_move_id).first()

    if not pos_move:
        return jsonify({"ok": False, "error": "Movimento POS non trovato"}), 404

    try:
        # se esistono row-check collegati, li elimino
        CashRowCheck.query.filter_by(
            entity_type="pos_move",
            entity_id=pos_move.id
        ).delete()

        cash_day = CashDay.query.filter_by(id=pos_move.cash_day_id).first()
        day_version_date = cash_day.day_date.isoformat() if cash_day else date.today().isoformat()

        db.session.delete(pos_move)
        db.session.commit()
        _bump_agenda_day_version(day_version_date)

        return jsonify({
            "ok": True,
            "pos_move_id": pos_move_id,
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("api_delete_pos_move error: %s", e)
        return jsonify({
            "ok": False,
            "error": "Errore interno durante l'eliminazione del movimento POS"
        }), 500


@cassa_bp.post("/api/day/<day_date>/expenses")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_create_expense(day_date):
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    cash_day = CashDay.query.filter(CashDay.day_date == d).first()
    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    data = request.get_json(silent=True) or {}

    flag = (data.get("flag") or "*").strip()
    if flag not in _ALLOWED_FLAGS:
        return jsonify({"ok": False, "error": f"Invalid flag (allowed: {sorted(_ALLOWED_FLAGS)})"}), 400

    description = (data.get("description") or "").strip() or None

    supplier = (data.get("supplier") or "").strip() or None
    description = (data.get("description") or "").strip() or None

    if not description and not supplier:
        return jsonify({
            "ok": False,
            "error": "Inserisci almeno una descrizione o un fornitore/beneficiario"
        }), 400

    off_cash = bool(data.get("off_cash", False))

    try:
        payments_data = _normalize_payments_payload(data)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    # =========================
    # CASO PRI (vault)
    # regola: spesa personale = solo cash, flag x
    # =========================
    all_cash = all(((p.get("method") or "").strip().lower() == "cash") for p in payments_data)

    if flag == "x":
        if not all_cash:
            return jsonify({
                "ok": False,
                "error": "Le spese PRI supportano solo pagamenti cash"
            }), 400

        if not session.get("pri_vault_unlocked"):
            return jsonify({"ok": False, "error": "Vault privato non sbloccato"}), 409

        year = d.year
        pri_data = _pri_load_year(year)

        day_node = next((x for x in pri_data["days"] if x["date"] == d.isoformat()), None)
        if not day_node:
            day_node = {
                "date": d.isoformat(),
                "sales": [],
                "expenses": [],
                "cash_moves": [],
            }
            pri_data["days"].append(day_node)

        total_amount = sum(Decimal(str(p.get("amount") or 0)) for p in payments_data)

        pri_row = {
            "id": f"pri-exp-{secrets.token_hex(8)}",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "supplier": supplier,
            "description": description,
            "amount": float(total_amount),
            "method": "cash",
            "flag": "x",
            "off_cash": bool(off_cash),
            "is_checked": False,
            "meta": {
                "origin": "pri",
                "created_by_user_id": getattr(current_user, "id", None),
                "created_by_name": getattr(current_user, "name", None)
                    or getattr(current_user, "username", None)
                    or "user",
            }
        }

        day_node["expenses"].append(pri_row)

        saved = _pri_save_year(year, pri_data)
        if not saved:
            return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

        _bump_agenda_day_version(d.isoformat())

        return jsonify({
            "ok": True,
            "expense_id": pri_row["id"],
            "storage": "pri",
        }), 201
    exp = CashExpense(
        cash_day_id=cash_day.id,
        created_by_user_id=getattr(current_user, "id", None),
        supplier=supplier,
        notes=description,
    )

    try:
        for idx, p in enumerate(payments_data, start=1):
            method = (p.get("method") or "").strip().lower()
            if method not in {"cash", "pos", "bank", "check"}:
                raise ValueError(f"Invalid payment method at row {idx}")

            amount = _to_decimal_amount(p.get("amount"), f"payments[{idx}].amount")

            payment = CashExpensePayment(
                direction="out",
                method=method,
                off_cash=off_cash,
                amount=amount,
                flag=flag,
                description=description,
            )

            if method == "pos":
                pos_card_label = (p.get("pos_card_label") or "").strip()
                pos_is_personal = bool(p.get("pos_is_personal", False))

                if not pos_card_label:
                    raise ValueError(f"Missing pos_card_label at row {idx}")

                payment.pos_card_label = pos_card_label
                payment.pos_is_personal = pos_is_personal

            elif method == "bank":
                bank_id = p.get("bank_id")
                if not bank_id:
                    raise ValueError(f"Missing bank_id at row {idx}")
                _validate_bank(bank_id)
                payment.bank_id = bank_id

            elif method == "check":
                bank_id = p.get("bank_id")
                check_number = (p.get("check_number") or "").strip()
                due_date_raw = p.get("due_date")

                if not bank_id:
                    raise ValueError(f"Missing bank_id at row {idx}")

                if not check_number:
                    raise ValueError(f"Missing check_number at row {idx}")

                if not due_date_raw:
                    raise ValueError(f"Missing due_date at row {idx}")

                try:
                    due_date = date.fromisoformat(due_date_raw)
                except Exception:
                    raise ValueError(f"Invalid due_date format at row {idx}")

                payment.bank_id = bank_id

                issued_check = CashIssuedCheck(
                    expense=exp,
                    bank_id=bank_id,
                    check_number=check_number,
                    due_date=due_date,
                    amount=amount,
                )

                db.session.add(issued_check)

            exp.payments.append(payment)

        db.session.add(exp)
        db.session.commit()
        _bump_agenda_day_version(d.isoformat())

    except ValueError as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception("api_create_expense error: %s", e)
        return jsonify({"ok": False, "error": "Internal error while creating expense"}), 500

    return jsonify({"ok": True, "expense_id": exp.id}), 201


@cassa_bp.get("/api/day/<day_date>/expenses")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_list_expenses(day_date):
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    cash_day = (
        CashDay.query
        .options(selectinload(CashDay.expenses).selectinload(CashExpense.payments))
        .filter(CashDay.day_date == d)
        .first()
    )
    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    items = []
    for e in cash_day.expenses:
        pay = []
        for p in (e.payments or []):
            pay.append({
                "id": p.id,
                "direction": p.direction,
                "method": p.method,
                "off_cash": bool(p.off_cash),
                "amount": float(p.amount or 0),
                "flag": p.flag,
                "description": p.description,
                "pos_card_label": p.pos_card_label,
                "pos_is_personal": bool(p.pos_is_personal),
                "created_at": p.created_at.isoformat() if p.created_at else None,
            })
        items.append({
            "id": e.id,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "doc_ref": e.doc_ref,
            "notes": e.notes,
            "storage": "az",
            "payments": pay,
        })

    # =========================
    # Merge PRI (vault)
    # =========================
    if session.get("pri_vault_unlocked"):
        try:
            year = d.year
            pri_data = _pri_load_year(year)

            day_node = next((x for x in pri_data["days"] if x["date"] == d.isoformat()), None)

            if day_node:
                for row in day_node.get("expenses", []):
                    items.append({
                        "id": row["id"],
                        "created_at": row.get("created_at"),
                        "doc_ref": None,
                        "notes": row.get("description"),
                        "supplier": row.get("supplier"),
                        "storage": "pri",
                        "is_checked": bool(row.get("is_checked", False)),
                        "payments": [
                            {
                                "id": f'{row["id"]}-pay',
                                "direction": "out",
                                "method": row.get("method", "cash"),
                                "off_cash": bool(row.get("off_cash", False)),
                                "amount": float(row.get("amount", 0)),
                                "flag": row.get("flag"),
                                "description": row.get("description"),
                                "pos_card_label": None,
                                "pos_is_personal": False,
                                "created_at": row.get("created_at"),
                                "storage": "pri",
                            }
                        ],
                    })
        except Exception as e:
            logger.exception("Errore lettura PRI expenses: %s", e)

    return jsonify({"ok": True, "day_date": d.isoformat(), "expenses": items})


@cassa_bp.delete("/api/expenses/<expense_id>")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_delete_expense(expense_id):

    # =========================
    # CASO PRI (vault)
    # =========================
    if isinstance(expense_id, str) and expense_id.startswith("pri-exp-"):
        if not session.get("pri_vault_unlocked"):
            return jsonify({"ok": False, "error": "Vault privato non sbloccato"}), 409

        year = date.today().year
        pri_data, day_node, idx, row = _pri_find_expense(year, expense_id)

        if not pri_data:
            return jsonify({"ok": False, "error": "Spesa PRI non trovata"}), 404

        del day_node["expenses"][idx]

        saved = _pri_save_year(year, pri_data)
        if not saved:
            return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

        _bump_agenda_day_version(day_node["date"])

        return jsonify({
            "ok": True,
            "expense_id": expense_id,
            "storage": "pri",
        })

    # =========================
    # CASO DB aziendale
    # =========================
    try:
        expense_id_int = int(expense_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid expense_id"}), 400

    expense = (
        CashExpense.query
        .options(selectinload(CashExpense.payments))
        .filter(CashExpense.id == expense_id_int)
        .first()
    )

    if not expense:
        return jsonify({"ok": False, "error": "Spesa non trovata"}), 404

    try:
        CashRowCheck.query.filter_by(
            entity_type="expense",
            entity_id=expense.id
        ).delete()

        cash_day = CashDay.query.filter_by(id=expense.cash_day_id).first()
        day_version_date = cash_day.day_date.isoformat() if cash_day else date.today().isoformat()

        db.session.delete(expense)
        db.session.commit()
        _bump_agenda_day_version(day_version_date)

        return jsonify({
            "ok": True,
            "expense_id": expense_id_int,
            "storage": "az",
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("api_delete_expense error: %s", e)
        return jsonify({
            "ok": False,
            "error": "Errore interno durante l'eliminazione della spesa"
        }), 500


@cassa_bp.put("/api/expenses/<expense_id>")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_update_expense(expense_id):
    data = request.get_json(silent=True) or {}

    flag = (data.get("flag") or "*").strip()
    if flag not in _ALLOWED_FLAGS:
        return jsonify({"ok": False, "error": f"Invalid flag (allowed: {sorted(_ALLOWED_FLAGS)})"}), 400

    supplier = (data.get("supplier") or "").strip() or None
    description = (data.get("description") or "").strip() or None

    if not description and not supplier:
        return jsonify({
            "ok": False,
            "error": "Inserisci almeno una descrizione o un fornitore/beneficiario"
        }), 400

    off_cash = bool(data.get("off_cash", False))

    try:
        payments_data = _normalize_payments_payload(data)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    # =========================
    # CASO PRI (vault)
    # =========================
    if isinstance(expense_id, str) and expense_id.startswith("pri-exp-"):
        if not session.get("pri_vault_unlocked"):
            return jsonify({"ok": False, "error": "Vault privato non sbloccato"}), 409

        all_cash = all(((p.get("method") or "").strip().lower() == "cash") for p in payments_data)
        if not all_cash:
            return jsonify({
                "ok": False,
                "error": "Le spese PRI supportano solo pagamenti cash"
            }), 400

        try:
            total_amount = sum(
                _to_decimal_amount(p.get("amount"), f"payments[{idx}].amount")
                for idx, p in enumerate(payments_data, start=1)
            )
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        year = date.today().year

        # =========================
        # MIGRAZIONE PRI -> AZ
        # =========================
        if flag not in {"x", "+"}:
            if not session.get("pri_vault_unlocked"):
                return jsonify({"ok": False, "error": "Vault privato non sbloccato"}), 409

            year = date.today().year
            pri_data, day_node, idx, pri_row = _pri_find_expense(year, expense_id)

            if not pri_data:
                return jsonify({"ok": False, "error": "Spesa PRI non trovata"}), 404

            try:
                total_amount = sum(
                    _to_decimal_amount(p.get("amount"), f"payments[{i}].amount")
                    for i, p in enumerate(payments_data, start=1)
                )
            except ValueError as e:
                return jsonify({"ok": False, "error": str(e)}), 400

            # recupero giorno dal day_node PRI
            try:
                d_pri = datetime.strptime(day_node["date"], "%Y-%m-%d").date()
            except Exception:
                return jsonify({"ok": False, "error": "Data movimento PRI non valida"}), 400

            cash_day = CashDay.query.filter(CashDay.day_date == d_pri).first()
            if not cash_day:
                cash_day = CashDay(
                    day_date=d_pri,
                    opening_float=float(_find_latest_previous_cash_balance(d_pri) or 0),
                    status="open",
                )
                db.session.add(cash_day)
                db.session.flush()

            exp = CashExpense(
                cash_day_id=cash_day.id,
                created_by_user_id=getattr(current_user, "id", None),
                supplier=supplier,
                notes=description,
            )

            db.session.add(exp)
            db.session.flush()

            try:
                for idx_p, p in enumerate(payments_data, start=1):
                    method = (p.get("method") or "").strip().lower()
                    if method not in {"cash", "pos", "bank", "check"}:
                        raise ValueError(f"Invalid payment method at row {idx_p}")

                    amount = _to_decimal_amount(p.get("amount"), f"payments[{idx_p}].amount")

                    payment = CashExpensePayment(
                        expense_id=exp.id,
                        direction="out",
                        method=method,
                        off_cash=off_cash,
                        amount=amount,
                        flag=flag,
                        description=description,
                    )

                    if method == "pos":
                        pos_card_label = (p.get("pos_card_label") or "").strip()
                        pos_is_personal = bool(p.get("pos_is_personal", False))

                        if not pos_card_label:
                            raise ValueError(f"Missing pos_card_label at row {idx_p}")

                        payment.pos_card_label = pos_card_label
                        payment.pos_is_personal = pos_is_personal

                    elif method == "bank":
                        bank_id = p.get("bank_id")
                        if not bank_id:
                            raise ValueError(f"Missing bank_id at row {idx_p}")
                        _validate_bank(bank_id)
                        payment.bank_id = bank_id

                    elif method == "check":
                        bank_id = p.get("bank_id")
                        check_number = (p.get("check_number") or "").strip()
                        due_date_raw = p.get("due_date")

                        if not bank_id:
                            raise ValueError(f"Missing bank_id at row {idx_p}")
                        if not check_number:
                            raise ValueError(f"Missing check_number at row {idx_p}")
                        if not due_date_raw:
                            raise ValueError(f"Missing due_date at row {idx_p}")

                        try:
                            due_date = date.fromisoformat(due_date_raw)
                        except Exception:
                            raise ValueError(f"Invalid due_date format at row {idx_p}")

                        payment.bank_id = bank_id

                        issued_check = CashIssuedCheck(
                            expense=exp,
                            bank_id=bank_id,
                            check_number=check_number,
                            due_date=due_date,
                            amount=amount,
                        )
                        db.session.add(issued_check)

                    db.session.add(payment)

                # rimuovo dal vault solo dopo aver creato correttamente in DB
                del day_node["expenses"][idx]

                saved = _pri_save_year(year, pri_data)
                if not saved:
                    db.session.rollback()
                    return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

                db.session.commit()
                _bump_agenda_day_version(d_pri.isoformat())

                return jsonify({
                    "ok": True,
                    "expense_id": exp.id,
                    "storage": "az",
                    "migrated": "pri_to_az",
                })

            except ValueError as e:
                db.session.rollback()
                return jsonify({"ok": False, "error": str(e)}), 400
            except Exception as e:
                db.session.rollback()
                logger.exception("api_update_expense PRI->AZ error: %s", e)
                return jsonify({
                    "ok": False,
                    "error": "Errore interno durante migrazione spesa PRI -> AZ"
                }), 500

        updated_row = _pri_update_expense(year, expense_id, {
            "supplier": supplier,
            "description": description,
            "amount": float(total_amount),
            "method": "cash",
            "flag": "x",
            "off_cash": bool(off_cash),
        })

        if updated_row is None:
            return jsonify({"ok": False, "error": "Spesa PRI non trovata"}), 404

        if updated_row is False:
            return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

        pri_data, day_node, _, _ = _pri_find_expense(year, expense_id)
        if day_node:
            _bump_agenda_day_version(day_node["date"])

        return jsonify({
            "ok": True,
            "expense_id": expense_id,
            "storage": "pri",
        })

    # =========================
    # CASO DB aziendale
    # =========================
    try:
        expense_id_int = int(expense_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid expense_id"}), 400

    expense = (
        CashExpense.query
        .options(selectinload(CashExpense.payments))
        .filter(CashExpense.id == expense_id_int)
        .first()
    )

    if not expense:
        return jsonify({"ok": False, "error": "Spesa non trovata"}), 404

    # =========================
    # MIGRAZIONE AZ -> PRI
    # =========================
    if flag in {"x", "+"}:
        existing_payments = list(expense.payments or [])

        existing_is_single_cash = (
            len(existing_payments) == 1
            and existing_payments[0].method == "cash"
        )

        incoming_is_single_cash = (
            len(payments_data) == 1
            and (payments_data[0].get("method") or "").strip().lower() == "cash"
        )

        if not existing_is_single_cash or not incoming_is_single_cash:
            return jsonify({
                "ok": False,
                "error": "Impossibile trasformare una registrazione con pagamenti multipli o non cash in una registrazione privata. Cancella il movimento ed esegui una nuova registrazione."
            }), 400

        if not session.get("pri_vault_unlocked"):
            return jsonify({"ok": False, "error": "Vault privato non sbloccato"}), 409

        try:
            amount = _to_decimal_amount(payments_data[0].get("amount"), "amount")
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        year = date.today().year
        pri_data = _pri_load_year(year)

        cash_day = CashDay.query.filter_by(id=expense.cash_day_id).first()
        if not cash_day:
            return jsonify({"ok": False, "error": "Giornata non trovata"}), 404

        day_node = next((x for x in pri_data["days"] if x["date"] == cash_day.day_date.isoformat()), None)
        if not day_node:
            day_node = {
                "date": cash_day.day_date.isoformat(),
                "sales": [],
                "expenses": [],
                "cash_moves": [],
            }
            pri_data["days"].append(day_node)

        pri_row = {
            "id": f"pri-exp-{secrets.token_hex(8)}",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "supplier": supplier,
            "description": description,
            "amount": float(amount),
            "method": "cash",
            "flag": flag,
            "off_cash": bool(off_cash),
            "is_checked": False,
            "meta": {
                "origin": "pri",
                "migrated_from": "az",
                "az_expense_id": expense.id,
                "created_by_user_id": getattr(current_user, "id", None),
                "created_by_name": getattr(current_user, "name", None)
                    or getattr(current_user, "username", None)
                    or "user",
            }
        }

        day_node["expenses"].append(pri_row)

        saved = _pri_save_year(year, pri_data)
        if not saved:
            return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

        try:
            CashRowCheck.query.filter_by(
                entity_type="expense",
                entity_id=expense.id
            ).delete()

            db.session.delete(expense)
            db.session.commit()
            _bump_agenda_day_version(cash_day.day_date.isoformat())

            return jsonify({
                "ok": True,
                "expense_id": pri_row["id"],
                "storage": "pri",
                "migrated": "az_to_pri",
            })

        except Exception as e:
            db.session.rollback()
            logger.exception("api_update_expense AZ->PRI delete error: %s", e)
            return jsonify({
                "ok": False,
                "error": "Spesa salvata nel vault, ma errore durante la rimozione dal DB aziendale"
            }), 500

    expense.supplier = supplier
    expense.notes = description

    try:
        CashExpensePayment.query.filter_by(expense_id=expense.id).delete()
        CashIssuedCheck.query.filter_by(expense_id=expense.id).delete()
        db.session.flush()

        expense.notes = description

        for idx, p in enumerate(payments_data, start=1):
            method = (p.get("method") or "").strip().lower()
            if method not in {"cash", "pos", "bank", "check"}:
                raise ValueError(f"Invalid payment method at row {idx}")

            amount = _to_decimal_amount(p.get("amount"), f"payments[{idx}].amount")

            payment = CashExpensePayment(
                expense_id=expense.id,
                direction="out",
                method=method,
                off_cash=off_cash,
                amount=amount,
                flag=flag,
                description=description,
            )

            if method == "pos":
                pos_card_label = (p.get("pos_card_label") or "").strip()
                pos_is_personal = bool(p.get("pos_is_personal", False))

                if not pos_card_label:
                    raise ValueError(f"Missing pos_card_label at row {idx}")

                payment.pos_card_label = pos_card_label
                payment.pos_is_personal = pos_is_personal

            elif method == "bank":
                bank_id = p.get("bank_id")
                if not bank_id:
                    raise ValueError(f"Missing bank_id at row {idx}")
                _validate_bank(bank_id)
                payment.bank_id = bank_id

            elif method == "check":
                bank_id = p.get("bank_id")
                check_number = (p.get("check_number") or "").strip()
                due_date_raw = p.get("due_date")

                if not bank_id:
                    raise ValueError(f"Missing bank_id at row {idx}")

                if not check_number:
                    raise ValueError(f"Missing check_number at row {idx}")

                if not due_date_raw:
                    raise ValueError(f"Missing due_date at row {idx}")

                try:
                    due_date = date.fromisoformat(due_date_raw)
                except Exception:
                    raise ValueError(f"Invalid due_date format at row {idx}")

                payment.bank_id = bank_id

                issued_check = CashIssuedCheck(
                    expense=expense,
                    bank_id=bank_id,
                    check_number=check_number,
                    due_date=due_date,
                    amount=amount,
                )

                db.session.add(issued_check)

            db.session.add(payment)

        db.session.commit()

        cash_day = CashDay.query.filter_by(id=expense.cash_day_id).first()
        if cash_day:
            _bump_agenda_day_version(cash_day.day_date.isoformat())

        return jsonify({
            "ok": True,
            "expense_id": expense.id,
            "storage": "az",
        })

    except ValueError as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception("api_update_expense error: %s", e)
        return jsonify({
            "ok": False,
            "error": "Errore interno durante la modifica della spesa"
        }), 500


@cassa_bp.post("/api/day/<day_date>/pos_moves", endpoint="api_create_pos_move")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_create_pos_move(day_date):
    """
    Payload:
    {
      "pos_device_id": 1,
      "pos_circuit_id": 2,
      "amount": 12.50,   # può essere negativo (storno)
      "doc_ref": "CORR", # opzionale
      "notes": "..."     # opzionale
    }
    """
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    cash_day = CashDay.query.filter(CashDay.day_date == d).first()
    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    data = request.get_json(silent=True) or {}

    try:
        raw_amount = Decimal(str(data.get("amount", "0")))
    except (InvalidOperation, TypeError):
        return jsonify({"ok": False, "error": "Invalid amount"}), 400

    if raw_amount == 0:
        return jsonify({"ok": False, "error": "Amount must be non-zero"}), 400

    pos_device_id = data.get("pos_device_id")
    if not pos_device_id:
        return jsonify({"ok": False, "error": "Missing pos_device_id"}), 400

    pos_circuit_id = data.get("pos_circuit_id")
    if not pos_circuit_id:
        return jsonify({"ok": False, "error": "Missing pos_circuit_id"}), 400

    dev = PosDevice.query.filter_by(id=pos_device_id, is_active=True).first()
    if not dev:
        return jsonify({"ok": False, "error": "PosDevice not found or inactive"}), 400

    cir = PosCircuit.query.filter_by(id=pos_circuit_id, is_active=True).first()
    if not cir:
        return jsonify({"ok": False, "error": "PosCircuit not found or inactive"}), 400

    allowed = db.session.query(pos_device_circuits).filter(
        pos_device_circuits.c.pos_device_id == pos_device_id,
        pos_device_circuits.c.pos_circuit_id == pos_circuit_id
    ).first()
    if not allowed:
        return jsonify({"ok": False, "error": "Circuit not associated to this POS device"}), 400

    direction = "in" if raw_amount > 0 else "out"
    amount = abs(raw_amount)

    doc_ref = (data.get("doc_ref") or "").strip() or None
    notes = (data.get("notes") or "").strip() or None

    m = PosMove(
        cash_day_id=cash_day.id,
        created_by_user_id=getattr(current_user, "id", None),
        direction=direction,
        amount=amount,
        pos_device_id=pos_device_id,
        pos_circuit_id=pos_circuit_id,
        doc_ref=doc_ref,
        notes=notes,
    )

    db.session.add(m)
    db.session.commit()
    _bump_agenda_day_version(d.isoformat())

    return jsonify({"ok": True, "pos_move_id": m.id}), 201


@cassa_bp.put("/api/pos_moves/<int:pos_move_id>", endpoint="api_update_pos_move")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_update_pos_move(pos_move_id):
    """
    Payload:
    {
      "pos_device_id": 1,
      "pos_circuit_id": 2,
      "amount": 12.50,   # può essere negativo (storno)
      "doc_ref": "CORR",
      "notes": "..."
    }
    """
    pos_move = PosMove.query.filter_by(id=pos_move_id).first()
    if not pos_move:
        return jsonify({"ok": False, "error": "Movimento POS non trovato"}), 404

    data = request.get_json(silent=True) or {}

    try:
        raw_amount = Decimal(str(data.get("amount", "0")))
    except (InvalidOperation, TypeError):
        return jsonify({"ok": False, "error": "Invalid amount"}), 400

    if raw_amount == 0:
        return jsonify({"ok": False, "error": "Amount must be non-zero"}), 400

    pos_device_id = data.get("pos_device_id")
    if not pos_device_id:
        return jsonify({"ok": False, "error": "Missing pos_device_id"}), 400

    pos_circuit_id = data.get("pos_circuit_id")
    if not pos_circuit_id:
        return jsonify({"ok": False, "error": "Missing pos_circuit_id"}), 400

    dev = PosDevice.query.filter_by(id=pos_device_id, is_active=True).first()
    if not dev:
        return jsonify({"ok": False, "error": "PosDevice not found or inactive"}), 400

    cir = PosCircuit.query.filter_by(id=pos_circuit_id, is_active=True).first()
    if not cir:
        return jsonify({"ok": False, "error": "PosCircuit not found or inactive"}), 400

    allowed = db.session.query(pos_device_circuits).filter(
        pos_device_circuits.c.pos_device_id == pos_device_id,
        pos_device_circuits.c.pos_circuit_id == pos_circuit_id
    ).first()
    if not allowed:
        return jsonify({"ok": False, "error": "Circuit not associated to this POS device"}), 400

    direction = "in" if raw_amount > 0 else "out"
    amount = abs(raw_amount)

    doc_ref = (data.get("doc_ref") or "").strip() or None
    notes = (data.get("notes") or "").strip() or None

    try:
        pos_move.direction = direction
        pos_move.amount = amount
        pos_move.pos_device_id = pos_device_id
        pos_move.pos_circuit_id = pos_circuit_id
        pos_move.doc_ref = doc_ref
        pos_move.notes = notes

        db.session.commit()

        cash_day = CashDay.query.filter_by(id=pos_move.cash_day_id).first()
        if cash_day:
            _bump_agenda_day_version(cash_day.day_date.isoformat())

        return jsonify({
            "ok": True,
            "pos_move_id": pos_move.id
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("api_update_pos_move error: %s", e)
        return jsonify({
            "ok": False,
            "error": "Errore interno durante la modifica del movimento POS"
        }), 500


@cassa_bp.get("/api/day/<day_date>/pos_moves", endpoint="api_list_pos_moves")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_list_pos_moves(day_date):
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    cash_day = CashDay.query.filter(CashDay.day_date == d).first()
    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    moves = (
        PosMove.query
        .filter(PosMove.cash_day_id == cash_day.id)
        .order_by(PosMove.created_at.asc())
        .all()
    )

    dev_map = {x.id: x for x in PosDevice.query.all()}
    cir_map = {x.id: x for x in PosCircuit.query.all()}

    out = []
    for m in moves:
        dev = dev_map.get(m.pos_device_id)
        cir = cir_map.get(m.pos_circuit_id)

        out.append({
            "id": m.id,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "direction": m.direction,
            "amount": float(m.amount or 0),
            "pos_device_id": m.pos_device_id,
            "pos_device_name": dev.name if dev else None,
            "pos_circuit_id": m.pos_circuit_id,
            "pos_circuit_name": cir.name if cir else None,
            "pos_circuit_icon": cir.icon if cir else None,
            "pos_circuit_logo_path": cir.logo_path if cir else None,
            "doc_ref": m.doc_ref,
            "notes": m.notes,
        })

    return jsonify({"ok": True, "day_date": d.isoformat(), "pos_moves": out})


@cassa_bp.get("/api/banks", endpoint="api_list_cash_banks")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_list_cash_banks():
    banks = (
        CashBank.query
        .filter(CashBank.is_active.is_(True))
        .order_by(CashBank.is_default.desc(), CashBank.sort_order.asc(), CashBank.name.asc())
        .all()
    )

    return jsonify({
        "ok": True,
        "banks": [
            {
                "id": b.id,
                "name": b.name,
                "is_default": bool(b.is_default),
            }
            for b in banks
        ]
    })


# =========================
# MOVIMENTI DI CASSA (prelievi/versamenti terzi + spicci)
# =========================

@cassa_bp.post("/api/day/<day_date>/cash_moves", endpoint="api_create_cash_move")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_create_cash_move(day_date):
    """
    Inserimento movimento di cassa.
    Payload:
    {
      "amount": -50.00,                 # negativo=prelievo (out), positivo=versamento (in)
      "performed_by": "Vito",           # chi prende/mette i soldi
      "notes": "Motivo (opzionale)",
      "kind": "altro" | "spicci"        # default "altro"
    }
    """
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    cash_day = CashDay.query.filter(CashDay.day_date == d).first()
    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    data = request.get_json(silent=True) or {}

    try:
        raw_amount = Decimal(str(data.get("amount", "0")))
    except (InvalidOperation, TypeError):
        return jsonify({"ok": False, "error": "Invalid amount"}), 400

    if raw_amount == 0:
        return jsonify({"ok": False, "error": "Amount must be non-zero"}), 400

    performed_by = (data.get("performed_by") or "").strip() or None

    notes = (data.get("notes") or "").strip() or None
    kind = (data.get("kind") or "altro").strip() or "altro"

    direction = "in" if raw_amount > 0 else "out"
    amount = abs(raw_amount)

    flag = "x"

    if flag in {"+", "x"}:
        if not session.get("pri_vault_unlocked"):
            return jsonify({"ok": False, "error": "Vault privato non sbloccato"}), 409

        year = d.year
        pri_data = _pri_load_year(year)

        day_node = next((x for x in pri_data["days"] if x["date"] == d.isoformat()), None)
        if not day_node:
            day_node = {
                "date": d.isoformat(),
                "sales": [],
                "expenses": [],
                "cash_moves": [],
            }
            pri_data["days"].append(day_node)

        pri_row = {
            "id": f"pri-cm-{secrets.token_hex(8)}",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "direction": direction,
            "amount": float(amount),
            "performed_by": performed_by,
            "notes": notes,
            "kind": kind,
            "method": "cash",
            "flag": flag,
            "off_cash": False,
            "meta": {
                "origin": "pri",
                "created_by_user_id": getattr(current_user, "id", None),
                "created_by_name": getattr(current_user, "name", None)
                                   or getattr(current_user, "username", None)
                                   or "user",
            }
        }

        day_node["cash_moves"].append(pri_row)

        saved = _pri_save_year(year, pri_data)
        if not saved:
            return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

        _bump_agenda_day_version(d.isoformat())

        return jsonify({
            "ok": True,
            "cash_move_id": pri_row["id"],
            "storage": "pri",
        }), 201

    m = CashMove(
        cash_day_id=cash_day.id,
        created_by_user_id=getattr(current_user, "id", None),
        direction=direction,
        amount=amount,
        performed_by=performed_by,
        notes=notes,
        kind=kind,
    )

    db.session.add(m)
    db.session.commit()
    _bump_agenda_day_version(d.isoformat())

    return jsonify({"ok": True, "cash_move_id": m.id}), 201


@cassa_bp.get("/api/day/<day_date>/cash_moves", endpoint="api_list_cash_moves")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_list_cash_moves(day_date):
    """
    Lista movimenti di cassa della giornata.
    Integra:
    - DB aziendale
    - vault PRI (se sbloccato)
    """
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    cash_day = CashDay.query.filter(CashDay.day_date == d).first()

    out = []

    # --- DB aziendale
    if cash_day:
        moves = (
            CashMove.query
            .filter(CashMove.cash_day_id == cash_day.id)
            .order_by(CashMove.created_at.asc())
            .all()
        )

        for m in moves:
            out.append({
                "id": m.id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "direction": m.direction,
                "amount": float(m.amount or 0),
                "performed_by": m.performed_by,
                "notes": m.notes,
                "kind": m.kind,
                "storage": "az",
            })

    # --- Vault PRI
    if session.get("pri_vault_unlocked"):
        try:
            pri_data = _pri_load_year(d.year)
            day_node = next((x for x in pri_data["days"] if x["date"] == d.isoformat()), None)

            if day_node:
                for m in (day_node.get("cash_moves") or []):
                    out.append({
                        "id": m.get("id"),
                        "created_at": m.get("created_at"),
                        "direction": m.get("direction"),
                        "amount": float(m.get("amount") or 0),
                        "performed_by": m.get("performed_by"),
                        "is_checked": bool(m.get("is_checked", False)),
                        "notes": m.get("notes"),
                        "kind": m.get("kind"),
                        "flag": m.get("flag"),
                        "storage": "pri",
                    })
        except Exception as e:
            logger.warning("api_list_cash_moves PRI read skipped: %s", e)

    if not out:
        # Se non ci sono movimenti → NON è errore
        return jsonify({
            "ok": True,
            "day_date": d.isoformat(),
            "cash_moves": out
        })

    out.sort(key=lambda x: x.get("created_at") or "")

    return jsonify({
        "ok": True,
        "day_date": d.isoformat(),
        "cash_moves": out
    })


@cassa_bp.get("/api/private/debug-read")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_private_debug_read():
    try:
        if not session.get("pri_vault_unlocked"):
            return jsonify({"ok": False, "error": "Vault non sbloccato"}), 400

        year = date.today().year
        data = _pri_load_year(year)

        return jsonify({
            "ok": True,
            "year": year,
            "data": data
        })

    except Exception as e:
        logger.exception("api_private_debug_read error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@cassa_bp.put("/api/cash_moves/<cash_move_id>", endpoint="api_update_cash_move")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_update_cash_move(cash_move_id):
    """
    Modifica movimento di cassa.
    Payload:
    {
      "amount": -50.00,          # negativo=prelievo (out), positivo=versamento (in)
      "performed_by": "Vito",
      "notes": "Motivo (opzionale)",
      "kind": "altro" | "spicci"
    }
    """
    data = request.get_json(silent=True) or {}

    try:
        raw_amount = Decimal(str(data.get("amount", "0")))
    except (InvalidOperation, TypeError):
        return jsonify({"ok": False, "error": "Invalid amount"}), 400

    if raw_amount == 0:
        return jsonify({"ok": False, "error": "Amount must be non-zero"}), 400

    performed_by = (data.get("performed_by") or "").strip() or None
    notes = (data.get("notes") or "").strip() or None
    kind = (data.get("kind") or "altro").strip() or "altro"

    direction = "in" if raw_amount > 0 else "out"
    amount = abs(raw_amount)

    # =========================
    # CASO PRI (vault)
    # =========================
    if isinstance(cash_move_id, str) and cash_move_id.startswith("pri-cm-"):
        if not session.get("pri_vault_unlocked"):
            return jsonify({"ok": False, "error": "Vault privato non sbloccato"}), 409

        year = date.today().year

        updated_row = _pri_update_cash_move(year, cash_move_id, {
            "direction": direction,
            "amount": float(amount),
            "performed_by": performed_by,
            "notes": notes,
            "kind": kind,
            "flag": "x",
            "method": "cash",
            "off_cash": False,
        })

        if updated_row is None:
            return jsonify({"ok": False, "error": "Movimento PRI non trovato"}), 404

        if updated_row is False:
            return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

        pri_data, day_node, _, _ = _pri_find_cash_move(year, cash_move_id)
        if day_node:
            _bump_agenda_day_version(day_node["date"])

        return jsonify({
            "ok": True,
            "cash_move_id": cash_move_id,
            "storage": "pri",
        })

    # =========================
    # CASO DB aziendale
    # =========================
    try:
        move_id_int = int(cash_move_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid cash_move_id"}), 400

    cash_move = CashMove.query.filter_by(id=move_id_int).first()
    if not cash_move:
        return jsonify({"ok": False, "error": "Movimento di cassa non trovato"}), 404

    try:
        cash_move.direction = direction
        cash_move.amount = amount
        cash_move.performed_by = performed_by
        cash_move.notes = notes
        cash_move.kind = kind

        cash_day = CashDay.query.filter_by(id=cash_move.cash_day_id).first()
        day_version_date = cash_day.day_date.isoformat() if cash_day else date.today().isoformat()

        db.session.commit()
        _bump_agenda_day_version(day_version_date)

        return jsonify({
            "ok": True,
            "cash_move_id": cash_move.id,
            "storage": "az",
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("api_update_cash_move error: %s", e)
        return jsonify({
            "ok": False,
            "error": "Errore interno durante la modifica del movimento di cassa"
        }), 500


@cassa_bp.delete("/api/cash_moves/<cash_move_id>", endpoint="api_delete_cash_move")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_delete_cash_move(cash_move_id):

    # =========================
    # CASO PRI (vault)
    # =========================
    if isinstance(cash_move_id, str) and cash_move_id.startswith("pri-cm-"):
        if not session.get("pri_vault_unlocked"):
            return jsonify({"ok": False, "error": "Vault privato non sbloccato"}), 409

        year = date.today().year
        pri_data, day_node, idx, row = _pri_find_cash_move(year, cash_move_id)

        if not pri_data:
            return jsonify({"ok": False, "error": "Movimento PRI non trovato"}), 404

        del day_node["cash_moves"][idx]

        saved = _pri_save_year(year, pri_data)
        if not saved:
            return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

        _bump_agenda_day_version(day_node["date"])

        return jsonify({
            "ok": True,
            "cash_move_id": cash_move_id,
            "storage": "pri",
        })

    # =========================
    # CASO DB aziendale
    # =========================
    try:
        move_id_int = int(cash_move_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid cash_move_id"}), 400

    cash_move = CashMove.query.filter_by(id=move_id_int).first()

    if not cash_move:
        return jsonify({"ok": False, "error": "Movimento di cassa non trovato"}), 404

    try:
        CashRowCheck.query.filter_by(
            entity_type="cash_move",
            entity_id=cash_move.id
        ).delete()

        cash_day = CashDay.query.filter_by(id=cash_move.cash_day_id).first()
        day_version_date = cash_day.day_date.isoformat() if cash_day else date.today().isoformat()

        db.session.delete(cash_move)
        db.session.commit()
        _bump_agenda_day_version(day_version_date)

        return jsonify({
            "ok": True,
            "cash_move_id": move_id_int,
            "storage": "az",
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("api_delete_cash_move error: %s", e)
        return jsonify({
            "ok": False,
            "error": "Errore interno durante l'eliminazione del movimento di cassa"
        }), 500


@cassa_bp.get("/api/coins/balance", endpoint="api_coins_vault_balance")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_coins_vault_balance():
    """
    Saldo spicci in armadio (cumulativo fino alla data inclusa).
    Querystring:
      ?date=YYYY-MM-DD   (default: oggi)
    Regola:
      out (prelievo da cassa verso armadio)   => +amount armadio
      in  (versamento in cassa da armadio)    => -amount armadio
    """
    date_str = (request.args.get("date") or "").strip()
    if date_str:
        try:
            ref = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"ok": False, "error": "Invalid date format (YYYY-MM-DD)"}), 400
    else:
        ref = datetime.now().date()

    q_out = (
        db.session.query(func.coalesce(func.sum(CashMove.amount), 0))
        .join(CashDay, CashDay.id == CashMove.cash_day_id)
        .filter(
            CashDay.day_date <= ref,
            CashMove.kind == "spicci",
            CashMove.direction == "out",
        )
    )

    q_in = (
        db.session.query(func.coalesce(func.sum(CashMove.amount), 0))
        .join(CashDay, CashDay.id == CashMove.cash_day_id)
        .filter(
            CashDay.day_date <= ref,
            CashMove.kind == "spicci",
            CashMove.direction == "in",
        )
    )

    out_sum = _sum_amount(q_out)
    in_sum = _sum_amount(q_in)

    balance = out_sum - in_sum

    return jsonify({
        "ok": True,
        "ref_date": ref.isoformat(),
        "coins_vault_balance": str(balance),
    })


@cassa_bp.route("/api/pos/devices", methods=["GET"])
def api_pos_devices():
    devices = (
        PosDevice.query
        .filter_by(is_active=True)
        .order_by(PosDevice.name)
        .all()
    )

    return jsonify({
        "ok": True,
        "devices": [
            {
                "id": d.id,
                "name": d.name,
                "is_default": bool(d.is_default)
            }
            for d in devices
        ]
    })


@cassa_bp.route("/api/pos/devices/<int:device_id>/circuits", methods=["GET"])
def api_pos_device_circuits(device_id):

    device = PosDevice.query.filter_by(
        id=device_id,
        is_active=True
    ).first()

    if not device:
        return jsonify({"ok": False, "error": "device_not_found"}), 404

    circuits = [
        c for c in device.circuits
        if c.is_active
    ]

    return jsonify({
        "ok": True,
        "circuits": [
            {
                "id": c.id,
                "name": c.name,
                "icon": c.icon,
                "logo_path": c.logo_path
            }
            for c in circuits
        ]
    })


@cassa_bp.get("/api/day/<day_date>/drawer-count")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_get_drawer_count(day_date):
    cash_day, error_response = _get_cash_day_by_date_or_404(day_date)
    if error_response:
        return error_response

    drawer_count = (
        CashDrawerCount.query
        .options(selectinload(CashDrawerCount.lines))
        .filter(CashDrawerCount.cash_day_id == cash_day.id)
        .first()
    )

    return jsonify({
        "ok": True,
        "day_date": cash_day.day_date.isoformat(),
        "drawer_count": _serialize_drawer_count(drawer_count),
    })


@cassa_bp.post("/api/day/<day_date>/drawer-count")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_save_drawer_count(day_date):
    cash_day, error_response = _get_cash_day_by_date_or_404(day_date)
    if error_response:
        return error_response

    data = request.get_json(silent=True) or {}
    raw_lines = data.get("lines")
    notes = (data.get("notes") or "").strip() or None

    if not isinstance(raw_lines, list):
        return jsonify({"ok": False, "error": "lines must be a list"}), 400

    allowed_denoms = {str(d.quantize(Decimal("0.01"))) for d in _DRAWER_DENOMINATIONS}
    parsed = {}

    try:
        for idx, item in enumerate(raw_lines, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Invalid line at index {idx}")

            denom = Decimal(str(item.get("denomination")))
            denom_key = str(denom.quantize(Decimal("0.01")))

            if denom_key not in allowed_denoms:
                raise ValueError(f"Invalid denomination at row {idx}")

            quantity_raw = item.get("quantity", 0)
            try:
                quantity = int(quantity_raw)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid quantity at row {idx}")

            if quantity < 0:
                raise ValueError(f"Quantity must be non-negative at row {idx}")

            parsed[denom_key] = {
                "denomination": Decimal(denom_key),
                "quantity": quantity,
                "line_total": (Decimal(denom_key) * Decimal(quantity)).quantize(Decimal("0.01")),
            }

    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    try:
        drawer_count = CashDrawerCount.query.filter_by(cash_day_id=cash_day.id).first()

        if not drawer_count:
            drawer_count = CashDrawerCount(
                cash_day_id=cash_day.id,
                created_by_user_id=getattr(current_user, "id", None),
                notes=notes,
            )
            db.session.add(drawer_count)
            db.session.flush()
        else:
            drawer_count.notes = notes

        existing_by_key = {
            str(Decimal(str(line.denomination)).quantize(Decimal("0.01"))): line
            for line in (drawer_count.lines or [])
        }

        for denom in _DRAWER_DENOMINATIONS:
            denom_key = str(denom.quantize(Decimal("0.01")))
            values = parsed.get(denom_key, {
                "denomination": denom,
                "quantity": 0,
                "line_total": Decimal("0.00"),
            })

            line = existing_by_key.get(denom_key)
            if not line:
                line = CashDrawerCountLine(
                    drawer_count_id=drawer_count.id,
                    denomination=values["denomination"],
                )
                db.session.add(line)

            line.quantity = values["quantity"]
            line.line_total = values["line_total"]

        db.session.commit()
        _bump_agenda_day_version(cash_day.day_date.isoformat())

        drawer_count = (
            CashDrawerCount.query
            .options(selectinload(CashDrawerCount.lines))
            .filter(CashDrawerCount.cash_day_id == cash_day.id)
            .first()
        )

        return jsonify({
            "ok": True,
            "day_date": cash_day.day_date.isoformat(),
            "drawer_count": _serialize_drawer_count(drawer_count),
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("api_save_drawer_count error: %s", e)
        return jsonify({"ok": False, "error": "Internal error while saving drawer count"}), 500


@cassa_bp.delete("/api/day/<day_date>/drawer-count")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_delete_drawer_count(day_date):
    cash_day, error_response = _get_cash_day_by_date_or_404(day_date)
    if error_response:
        return error_response

    drawer_count = CashDrawerCount.query.filter_by(cash_day_id=cash_day.id).first()
    if not drawer_count:
        return jsonify({"ok": False, "error": "Drawer count not found"}), 404

    try:
        db.session.delete(drawer_count)
        db.session.commit()
        _bump_agenda_day_version(cash_day.day_date.isoformat())

        return jsonify({
            "ok": True,
            "day_date": cash_day.day_date.isoformat(),
        })
    except Exception as e:
        db.session.rollback()
        logger.exception("api_delete_drawer_count error: %s", e)
        return jsonify({"ok": False, "error": "Internal error while deleting drawer count"}), 500


@cassa_bp.get("/api/day/<day_date>/ecommerce")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_list_ecommerce(day_date):
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    cash_day = CashDay.query.filter(CashDay.day_date == d).first()
    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    rows = (
        CashEcommerce.query
        .filter(CashEcommerce.cash_day_id == cash_day.id)
        .order_by(CashEcommerce.created_at.asc(), CashEcommerce.id.asc())
        .all()
    )

    items = []
    for row in rows:
        items.append({
            "id": row.id,
            "amount": float(row.amount or 0),
            "description": row.description,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "created_by_user_id": row.created_by_user_id,
        })

    return jsonify({
        "ok": True,
        "day_date": d.isoformat(),
        "ecommerce": items,
    })


@cassa_bp.post("/api/day/<day_date>/ecommerce")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_create_ecommerce(day_date):
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    cash_day = CashDay.query.filter(CashDay.day_date == d).first()
    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    data = request.get_json(silent=True) or {}

    description = (data.get("description") or "").strip()
    if not description:
        return jsonify({"ok": False, "error": "Missing description"}), 400

    try:
        amount = _to_decimal_amount(data.get("amount"), "amount")
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    try:
        row = CashEcommerce(
            cash_day_id=cash_day.id,
            created_by_user_id=getattr(current_user, "id", None),
            amount=amount,
            description=description,
        )

        db.session.add(row)
        db.session.commit()
        _bump_agenda_day_version(d.isoformat())

        return jsonify({
            "ok": True,
            "ecommerce_id": row.id,
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.exception("api_create_ecommerce error: %s", e)
        return jsonify({"ok": False, "error": "Internal error while creating ecommerce row"}), 500


@cassa_bp.delete("/api/ecommerce/<int:ecommerce_id>")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_delete_ecommerce(ecommerce_id):
    row = CashEcommerce.query.filter_by(id=ecommerce_id).first()
    if not row:
        return jsonify({"ok": False, "error": "Ecommerce row not found"}), 404

    try:
        cash_day = CashDay.query.filter_by(id=row.cash_day_id).first()
        day_version_date = cash_day.day_date.isoformat() if cash_day else date.today().isoformat()

        cash_day = CashDay.query.filter_by(id=row.cash_day_id).first()
        day_version_date = cash_day.day_date.isoformat() if cash_day else date.today().isoformat()

        return jsonify({
            "ok": True,
            "ecommerce_id": ecommerce_id,
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("api_delete_ecommerce error: %s", e)
        return jsonify({"ok": False, "error": "Internal error while deleting ecommerce row"}), 500


@cassa_bp.put("/api/ecommerce/<int:ecommerce_id>")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_update_ecommerce(ecommerce_id):
    row = CashEcommerce.query.filter_by(id=ecommerce_id).first()
    if not row:
        return jsonify({"ok": False, "error": "Ecommerce row not found"}), 404

    data = request.get_json(silent=True) or {}

    description = (data.get("description") or "").strip()
    if not description:
        return jsonify({"ok": False, "error": "Missing description"}), 400

    try:
        amount = _to_decimal_amount(data.get("amount"), "amount")
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    try:
        cash_day = CashDay.query.filter_by(id=row.cash_day_id).first()
        day_version_date = cash_day.day_date.isoformat() if cash_day else date.today().isoformat()

        row.description = description
        row.amount = amount

        db.session.commit()
        _bump_agenda_day_version(day_version_date)

        return jsonify({
            "ok": True,
            "ecommerce_id": row.id,
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("api_update_ecommerce error: %s", e)
        return jsonify({
            "ok": False,
            "error": "Internal error while updating ecommerce row"
        }), 500


@cassa_bp.get("/api/day/<day_date>/deposit-available-checks")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_available_checks_for_deposit(day_date):
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid date"}), 400

    # versamento incasso:
    # assegni già in mano da prima di oggi, con stato ricevuto o spostato, versabili oggi
    cutoff = next_banking_day(d)

    incasso_checks = (
        CashCheck.query
        .options(selectinload(CashCheck.customer))
        .filter(
            CashCheck.status.in_(["received", "moved"]),
            CashCheck.received_date < d,
            CashCheck.due_date <= cutoff
        )
        .order_by(CashCheck.due_date.asc(), CashCheck.received_date.asc(), CashCheck.id.asc())
        .all()
    )

    # versamento intermedio:
    # assegni ricevuti oggi, ancora semplicemente ricevuti
    intermedio_checks = (
        CashCheck.query
        .options(selectinload(CashCheck.customer))
        .filter(
            CashCheck.status == "received",
            CashCheck.received_date == d
        )
        .order_by(CashCheck.due_date.asc(), CashCheck.received_date.asc(), CashCheck.id.asc())
        .all()
    )

    def serialize_check(c):
        return {
            "id": c.id,
            "check_number": c.check_number,
            "bank_name": c.bank_name,
            "amount": float(c.amount or 0),
            "due_date": c.due_date.isoformat() if c.due_date else None,
            "received_date": c.received_date.isoformat() if c.received_date else None,
            "customer_id": c.customer_id,
            "customer_display_name": c.customer.display_name if c.customer else None,
            "status": c.status,
        }

    # tutti gli assegni ancora "in pancia", anche non versabili oggi
    checks_in_pancia_status = ["received", "moved"]

    saldo_assegni_in_pancia = (
        db.session.query(func.coalesce(func.sum(CashCheck.amount), 0))
        .filter(CashCheck.status.in_(checks_in_pancia_status))
        .scalar()
    )

    saldo_assegni_in_pancia = Decimal(str(saldo_assegni_in_pancia or 0))

    prev_day = (
        CashDay.query
        .filter(CashDay.day_date < d)
        .order_by(CashDay.day_date.desc())
        .first()
    )

    saldo_versabile_precedente = (
        _calculate_progressive_saldo_versabile(prev_day) if prev_day else Decimal("0")
    )

    contanti_massimi_incasso = saldo_versabile_precedente - saldo_assegni_in_pancia
    if contanti_massimi_incasso < 0:
        contanti_massimi_incasso = Decimal("0")

    return jsonify({
        "ok": True,
        "day_date": d.isoformat(),
        "saldo_versabile_precedente": float(saldo_versabile_precedente),
        "saldo_assegni_in_pancia": float(saldo_assegni_in_pancia),
        "contanti_massimi_incasso": float(contanti_massimi_incasso),
        "incasso": [serialize_check(c) for c in incasso_checks],
        "intermedio": [serialize_check(c) for c in intermedio_checks],
    })


@cassa_bp.post("/api/day/<day_date>/deposits")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_create_deposit(day_date):
    from models import CashDeposit, CashDepositCheck

    data = request.get_json() or {}

    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid date"}), 400

    deposit_type = data.get("deposit_type")
    note = data.get("note")
    check_ids = data.get("check_ids", [])
    bank_id = data.get("bank_id")

    try:
        cash_amount = Decimal(str(data.get("cash_amount", 0)))
    except (InvalidOperation, TypeError):
        return jsonify({"ok": False, "error": "Importo contanti non valido"}), 400

    if cash_amount < 0:
        return jsonify({"ok": False, "error": "Importo contanti non valido"}), 400

    if deposit_type not in ["versamento_incasso", "versamento_intermedio"]:
        return jsonify({"ok": False, "error": "Tipo versamento non valido"}), 400

    if not bank_id:
        return jsonify({"ok": False, "error": "Banca versamento obbligatoria"}), 400

    bank = CashBank.query.filter_by(id=bank_id, is_active=True).first()
    if not bank:
        return jsonify({"ok": False, "error": "Banca non valida"}), 400

    day = CashDay.query.filter_by(day_date=d).first()
    if not day:
        return jsonify({"ok": False, "error": "Giornata non trovata"}), 404

    # --- recupero assegni ---
    checks = []
    if check_ids:
        checks = CashCheck.query.filter(CashCheck.id.in_(check_ids)).all()

    # --- VALIDAZIONE ---
    for c in checks:
        if deposit_type == "versamento_incasso":
            cutoff = next_banking_day(d)
            if not (
                    c.status in ["received", "moved"]
                    and c.received_date < d
                    and c.due_date <= cutoff
            ):
                return jsonify({"ok": False, "error": f"Assegno {c.id} non valido per versamento incasso"}), 400

        if deposit_type == "versamento_intermedio":
            if not (c.status == "received" and c.received_date == d):
                return jsonify({"ok": False, "error": f"Assegno {c.id} non valido per versamento intermedio"}), 400

    # --- CREAZIONE DEPOSITO ---
    deposit = CashDeposit(
        cash_day_id=day.id,
        deposit_date=d,
        deposit_type=deposit_type,
        cash_amount=cash_amount,
        bank_id=bank.id,
        note=note,
    )
    db.session.add(deposit)
    db.session.flush()

    # --- COLLEGA ASSEGNI + CAMBIO STATO ---
    for c in checks:
        db.session.add(CashDepositCheck(
            deposit_id=deposit.id,
            check_id=c.id,
            check_amount=c.amount
        ))

        change_check_status(
            check=c,
            new_status="deposited",
            user_id=getattr(current_user, "id", None),
            event_date=d,
            note=f"Versamento {deposit_type} su {bank.name}",
        )

    db.session.commit()
    _bump_agenda_day_version(d.isoformat())

    return jsonify({
        "ok": True,
        "deposit_id": deposit.id
    })


@cassa_bp.get("/api/day/<day_date>/deposits")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_list_deposits(day_date):
    from models import CashDeposit, CashDepositCheck

    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    cash_day = (
        CashDay.query
        .options(
            selectinload(CashDay.deposits).selectinload(CashDeposit.bank),
            selectinload(CashDay.deposits)
            .selectinload(CashDeposit.checks)
            .selectinload(CashDepositCheck.check)
            .selectinload(CashCheck.customer)
        )
        .filter(CashDay.day_date == d)
        .first()
    )

    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    items = []
    total_cash = Decimal("0")
    total_checks = Decimal("0")

    for dep in sorted(cash_day.deposits or [], key=lambda x: (x.deposit_date, x.id)):
        dep_cash = Decimal(str(dep.cash_amount or 0))
        total_cash += dep_cash

        checks = []
        dep_checks_total = Decimal("0")

        for link in dep.checks or []:
            linked_check = link.check
            check_amount = Decimal(str(
                link.check_amount if link.check_amount is not None
                else (linked_check.amount if linked_check else 0)
            ))
            dep_checks_total += check_amount
            total_checks += check_amount

            checks.append({
                "id": linked_check.id if linked_check else None,
                "check_number": linked_check.check_number if linked_check else None,
                "bank_name": linked_check.bank_name if linked_check else None,
                "amount": float(check_amount),
                "due_date": linked_check.due_date.isoformat() if linked_check and linked_check.due_date else None,
                "customer_id": linked_check.customer_id if linked_check else None,
                "customer_display_name": linked_check.customer.display_name if linked_check and linked_check.customer else None,
            })

        items.append({
            "id": dep.id,
            "deposit_date": dep.deposit_date.isoformat() if dep.deposit_date else None,
            "deposit_type": dep.deposit_type,
            "cash_amount": float(dep_cash),
            "checks_total": float(dep_checks_total),
            "total_amount": float(dep_cash + dep_checks_total),
            "bank_id": dep.bank_id,
            "bank_name": dep.bank.name if dep.bank else None,
            "note": dep.note,
            "checks": checks,
            "created_at": dep.created_at.isoformat() if dep.created_at else None,
        })

    return jsonify({
        "ok": True,
        "day_date": d.isoformat(),
        "deposits": items,
        "totals": {
            "cash_amount": float(total_cash),
            "checks_amount": float(total_checks),
            "total_amount": float(total_cash + total_checks),
        }
    })


@cassa_bp.put("/api/deposits/<int:deposit_id>")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_update_deposit(deposit_id):
    from models import CashDeposit, CashDepositCheck

    deposit = (
        CashDeposit.query
        .options(
            selectinload(CashDeposit.checks)
            .selectinload(CashDepositCheck.check)
        )
        .filter(CashDeposit.id == deposit_id)
        .first()
    )

    if not deposit:
        return jsonify({"ok": False, "error": "Versamento non trovato"}), 404

    data = request.get_json(silent=True) or {}

    deposit_type = (data.get("deposit_type") or "").strip()
    note = (data.get("note") or "").strip() or None
    check_ids = data.get("check_ids") or []
    bank_id = data.get("bank_id")

    try:
        cash_amount = Decimal(str(data.get("cash_amount", 0)))
    except (InvalidOperation, TypeError):
        return jsonify({"ok": False, "error": "Importo contanti non valido"}), 400

    if cash_amount < 0:
        return jsonify({"ok": False, "error": "Importo contanti non valido"}), 400

    if deposit_type not in ["versamento_incasso", "versamento_intermedio"]:
        return jsonify({"ok": False, "error": "Tipo versamento non valido"}), 400

    if not isinstance(check_ids, list):
        return jsonify({"ok": False, "error": "check_ids deve essere una lista"}), 400

    if not bank_id:
        return jsonify({"ok": False, "error": "Banca versamento obbligatoria"}), 400

    bank = CashBank.query.filter_by(id=bank_id, is_active=True).first()
    if not bank:
        return jsonify({"ok": False, "error": "Banca non valida"}), 400

    day_date = deposit.deposit_date
    cutoff = next_banking_day(day_date)

    checks = []
    if check_ids:
        checks = CashCheck.query.filter(CashCheck.id.in_(check_ids)).all()

    found_ids = {c.id for c in checks}
    missing_ids = [cid for cid in check_ids if cid not in found_ids]
    if missing_ids:
        return jsonify({"ok": False, "error": f"Assegni non trovati: {missing_ids}"}), 400

    current_check_ids = {
        link.check_id for link in (deposit.checks or [])
    }

    for c in checks:
        is_currently_linked = c.id in current_check_ids

        if deposit_type == "versamento_incasso":
            valid = (
                (c.status in ["received", "moved", "deposited"])
                and c.received_date < day_date
                and c.due_date <= cutoff
            )
        else:
            valid = (
                (c.status in ["received", "deposited"])
                and c.received_date == day_date
            )

        if not valid and not is_currently_linked:
            return jsonify({
                "ok": False,
                "error": f"Assegno {c.id} non valido per il tipo di versamento selezionato"
            }), 400

    try:
        old_links = {link.check_id: link for link in (deposit.checks or [])}
        new_check_ids = set(check_ids)

        removed_ids = set(old_links.keys()) - new_check_ids
        added_ids = new_check_ids - set(old_links.keys())

        for check_id in removed_ids:
            check = old_links[check_id].check
            prev_status = _get_previous_check_status_before_deposit(check.id)

            if not prev_status:
                return jsonify({
                    "ok": False,
                    "error": f"Impossibile determinare lo stato precedente per assegno {check.id}"
                }), 400

            change_check_status(
                check=check,
                new_status=prev_status,
                user_id=getattr(current_user, "id", None),
                event_date=day_date,
                note=f"Rimozione da versamento ID {deposit.id}",
                amount_spese=Decimal("0"),
                customer_charge_amount=Decimal("0"),
            )

        CashDepositCheck.query.filter_by(deposit_id=deposit.id).delete()

        for c in checks:
            db.session.add(CashDepositCheck(
                deposit_id=deposit.id,
                check_id=c.id,
                check_amount=c.amount
            ))

            if c.id in added_ids or c.status != "deposited":
                change_check_status(
                    check=c,
                    new_status="deposited",
                    user_id=getattr(current_user, "id", None),
                    event_date=day_date,
                    note=f"Modifica versamento {deposit_type} su {bank.name}",
                    amount_spese=Decimal("0"),
                    customer_charge_amount=Decimal("0"),
                )

        deposit.deposit_type = deposit_type
        deposit.cash_amount = cash_amount
        deposit.bank_id = bank.id
        deposit.note = note

        db.session.commit()
        _bump_agenda_day_version(day_date.isoformat())

        return jsonify({
            "ok": True,
            "deposit_id": deposit.id
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("api_update_deposit error: %s", e)
        return jsonify({
            "ok": False,
            "error": "Errore interno durante la modifica del versamento"
        }), 500


# ============================================================
# CORRISPETTIVI (CashReceiptClosure)
# ============================================================

from models import CashReceiptClosure


@cassa_bp.route("/api/day/<day_date>/receipt-closures", methods=["GET"])
def get_receipt_closures(day_date):
    day = CashDay.query.filter_by(day_date=day_date).first_or_404()

    rows = (
        CashReceiptClosure.query
        .filter_by(cash_day_id=day.id)
        .order_by(CashReceiptClosure.created_at.asc())
        .all()
    )

    return jsonify([
        {
            "id": r.id,
            "amount": float(r.amount),
            "closure_type": r.closure_type,
            "description": r.description,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ])


@cassa_bp.route("/api/day/<day_date>/receipt-closures", methods=["POST"])
def create_receipt_closure(day_date):
    data = request.get_json()

    day = CashDay.query.filter_by(day_date=day_date).first_or_404()

    amount = data.get("amount")
    closure_type = data.get("closure_type", "fine_giornata")
    description = data.get("description")

    if amount is None:
        return jsonify({"error": "Importo obbligatorio"}), 400

    row = CashReceiptClosure(
        cash_day_id=day.id,
        amount=amount,
        closure_type=closure_type,
        description=description,
        created_by_user_id=current_user.id if current_user.is_authenticated else None,
        updated_by_user_id=current_user.id if current_user.is_authenticated else None,
    )

    db.session.add(row)
    db.session.commit()
    _bump_agenda_day_version(day.day_date.isoformat())

    return jsonify({"success": True})


@cassa_bp.delete("/api/receipt-closures/<int:receipt_closure_id>")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_delete_receipt_closure(receipt_closure_id):
    row = CashReceiptClosure.query.filter_by(id=receipt_closure_id).first()

    if not row:
        return jsonify({"ok": False, "error": "Corrispettivo non trovato"}), 404

    try:
        cash_day = CashDay.query.filter_by(id=row.cash_day_id).first()
        day_version_date = cash_day.day_date.isoformat() if cash_day else date.today().isoformat()

        db.session.delete(row)
        db.session.commit()
        _bump_agenda_day_version(day_version_date)

        return jsonify({
            "ok": True,
            "receipt_closure_id": receipt_closure_id
        })
    except Exception as e:
        db.session.rollback()
        logger.exception("api_delete_receipt_closure error: %s", e)
        return jsonify(
            {"ok": False, "error": "Errore interno durante l'eliminazione del corrispettivo"}
        ), 500


@cassa_bp.put("/api/receipt-closures/<int:receipt_closure_id>")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_update_receipt_closure(receipt_closure_id):
    data = request.get_json(silent=True) or {}

    row = CashReceiptClosure.query.filter_by(id=receipt_closure_id).first()
    if not row:
        return jsonify({"ok": False, "error": "Corrispettivo non trovato"}), 404

    amount_raw = data.get("amount")
    closure_type = (data.get("closure_type") or "").strip()
    description = (data.get("description") or "").strip() or None

    if amount_raw is None:
        return jsonify({"ok": False, "error": "Importo obbligatorio"}), 400

    try:
        amount = _to_decimal_amount(amount_raw, "amount")
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    if closure_type not in {"fine_giornata", "intermedia"}:
        return jsonify({"ok": False, "error": "Tipo chiusura non valido"}), 400

    try:
        row.amount = amount
        row.closure_type = closure_type
        row.description = description
        row.updated_by_user_id = getattr(current_user, "id", None)

        db.session.commit()

        cash_day = CashDay.query.filter_by(id=row.cash_day_id).first()
        if cash_day:
            _bump_agenda_day_version(cash_day.day_date.isoformat())

        return jsonify({
            "ok": True,
            "receipt_closure_id": row.id
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("api_update_receipt_closure error: %s", e)
        return jsonify({
            "ok": False,
            "error": "Errore interno durante la modifica del corrispettivo"
        }), 500


@cassa_bp.get("/api/day/<day_date>/owner-take-available-checks")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_owner_take_available_checks(day_date):
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    cash_day = CashDay.query.filter(CashDay.day_date == d).first()
    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    already_taken_subq = (
        db.session.query(CashOwnerTakeCheck.check_id)
        .join(CashOwnerTake, CashOwnerTake.id == CashOwnerTakeCheck.owner_take_id)
        .filter(CashOwnerTake.cash_day_id == cash_day.id)
        .subquery()
    )

    checks = (
        CashCheck.query
        .options(selectinload(CashCheck.customer))
        .filter(
            CashCheck.received_date == d,
            CashCheck.status.in_(["received", "moved", "spostato"]),
            ~CashCheck.id.in_(already_taken_subq),
        )
        .order_by(CashCheck.due_date.asc(), CashCheck.id.asc())
        .all()
    )

    items = []
    for c in checks:
        items.append({
            "id": c.id,
            "check_number": c.check_number,
            "bank_name": c.bank_name,
            "amount": float(c.amount or 0),
            "received_date": c.received_date.isoformat() if c.received_date else None,
            "due_date": c.due_date.isoformat() if c.due_date else None,
            "status": c.status,
            "customer_id": c.customer_id,
            "customer_display_name": c.customer.display_name if c.customer else None,
        })

    return jsonify({
        "ok": True,
        "day_date": d.isoformat(),
        "checks": items,
    })


@cassa_bp.get("/api/day/<day_date>/owner-takes")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_list_owner_takes(day_date):
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    cash_day = (
        CashDay.query
        .options(
            selectinload(CashDay.owner_takes)
            .selectinload(CashOwnerTake.checks)
            .selectinload(CashOwnerTakeCheck.check)
            .selectinload(CashCheck.customer)
        )
        .filter(CashDay.day_date == d)
        .first()
    )
    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    items = []
    totals_cash = Decimal("0")
    totals_checks = Decimal("0")

    rows = sorted(cash_day.owner_takes or [], key=lambda x: (x.created_at, x.id))

    for row in rows:
        cash_amount = Decimal(str(row.cash_amount or 0))
        check_amount = Decimal(str(row.check_amount or 0))
        total_amount = cash_amount + check_amount

        totals_cash += cash_amount
        totals_checks += check_amount

        checks = []
        for link in row.checks or []:
            linked_check = link.check
            linked_amount = Decimal(str(
                link.check_amount if link.check_amount is not None
                else (linked_check.amount if linked_check else 0)
            ))

            checks.append({
                "id": linked_check.id if linked_check else None,
                "check_number": linked_check.check_number if linked_check else None,
                "bank_name": linked_check.bank_name if linked_check else None,
                "amount": float(linked_amount),
                "due_date": linked_check.due_date.isoformat() if linked_check and linked_check.due_date else None,
                "received_date": linked_check.received_date.isoformat() if linked_check and linked_check.received_date else None,
                "customer_id": linked_check.customer_id if linked_check else None,
                "customer_display_name": linked_check.customer.display_name if linked_check and linked_check.customer else None,
            })

        items.append({
            "id": row.id,
            "take_type": row.take_type,
            "cash_amount": float(cash_amount),
            "check_amount": float(check_amount),
            "total_amount": float(total_amount),
            "notes": row.notes,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "checks": checks,
        })

    return jsonify({
        "ok": True,
        "day_date": d.isoformat(),
        "owner_takes": items,
        "totals": {
            "cash_amount": float(totals_cash),
            "check_amount": float(totals_checks),
            "total_amount": float(totals_cash + totals_checks),
        }
    })


@cassa_bp.post("/api/day/<day_date>/owner-takes")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_create_owner_take(day_date):
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    cash_day = CashDay.query.filter(CashDay.day_date == d).first()
    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    data = request.get_json(silent=True) or {}

    take_type = (data.get("take_type") or "serale").strip()
    notes = (data.get("notes") or "").strip() or None
    check_ids = data.get("check_ids") or []

    if take_type not in {"parziale", "serale"}:
        return jsonify({"ok": False, "error": "Tipo prelievo non valido"}), 400

    try:
        cash_amount = Decimal(str(data.get("cash_amount", 0)))
    except (InvalidOperation, TypeError):
        return jsonify({"ok": False, "error": "Importo contanti non valido"}), 400

    if cash_amount < 0:
        return jsonify({"ok": False, "error": "Importo contanti non valido"}), 400

    if not isinstance(check_ids, list):
        return jsonify({"ok": False, "error": "check_ids deve essere una lista"}), 400

    checks = []
    if check_ids:
        checks = (
            CashCheck.query
            .filter(CashCheck.id.in_(check_ids))
            .all()
        )

    found_ids = {c.id for c in checks}
    missing_ids = [cid for cid in check_ids if cid not in found_ids]
    if missing_ids:
        return jsonify({
            "ok": False,
            "error": f"Assegni non trovati: {missing_ids}"
        }), 400

    already_taken_ids = {
        row.check_id
        for row in (
            db.session.query(CashOwnerTakeCheck.check_id)
            .join(CashOwnerTake, CashOwnerTake.id == CashOwnerTakeCheck.owner_take_id)
            .filter(
                CashOwnerTake.cash_day_id == cash_day.id,
                CashOwnerTakeCheck.check_id.in_(check_ids) if check_ids else False
            )
            .all()
        )
    }

    if already_taken_ids:
        return jsonify({
            "ok": False,
            "error": f"Assegni già associati a un altro prelievo: {sorted(already_taken_ids)}"
        }), 400

    check_amount = Decimal("0")
    for c in checks:
        valid_status = c.status in {"received", "moved", "spostato"}
        valid_day = c.received_date == d
        if not (valid_status and valid_day):
            return jsonify({
                "ok": False,
                "error": f"Assegno {c.id} non valido per questo prelievo"
            }), 400
        check_amount += Decimal(str(c.amount or 0))

    try:
        row = CashOwnerTake(
            cash_day_id=cash_day.id,
            take_type=take_type,
            cash_amount=cash_amount,
            check_amount=check_amount,
            notes=notes,
            created_by_user_id=getattr(current_user, "id", None),
            updated_by_user_id=getattr(current_user, "id", None),
        )

        db.session.add(row)
        db.session.flush()

        for c in checks:
            db.session.add(CashOwnerTakeCheck(
                owner_take_id=row.id,
                check_id=c.id,
                check_amount=c.amount,
            ))

        db.session.commit()
        _bump_agenda_day_version(d.isoformat())

        return jsonify({
            "ok": True,
            "owner_take_id": row.id,
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.exception("api_create_owner_take error: %s", e)
        return jsonify({
            "ok": False,
            "error": "Errore interno durante il salvataggio del prelievo"
        }), 500


@cassa_bp.delete("/api/owner-takes/<int:owner_take_id>")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_delete_owner_take(owner_take_id):
    row = (
        CashOwnerTake.query
        .options(selectinload(CashOwnerTake.checks))
        .filter(CashOwnerTake.id == owner_take_id)
        .first()
    )

    if not row:
        return jsonify({"ok": False, "error": "Prelievo non trovato"}), 404

    try:
        day_date = None
        if row.cash_day_id:
            cash_day = CashDay.query.filter(CashDay.id == row.cash_day_id).first()
            if cash_day:
                day_date = cash_day.day_date.isoformat()

        db.session.delete(row)
        db.session.commit()

        if day_date:
            _bump_agenda_day_version(day_date)

        return jsonify({
            "ok": True,
            "owner_take_id": owner_take_id,
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("api_delete_owner_take error: %s", e)
        return jsonify({
            "ok": False,
            "error": "Errore interno durante l'eliminazione del prelievo"
        }), 500


@cassa_bp.put("/api/owner-takes/<int:owner_take_id>")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_update_owner_take(owner_take_id):
    row = (
        CashOwnerTake.query
        .options(selectinload(CashOwnerTake.checks))
        .filter(CashOwnerTake.id == owner_take_id)
        .first()
    )

    if not row:
        return jsonify({"ok": False, "error": "Prelievo non trovato"}), 404

    data = request.get_json(silent=True) or {}

    take_type = (data.get("take_type") or "").strip()
    notes = (data.get("notes") or "").strip() or None
    check_ids = data.get("check_ids") or []

    if take_type not in {"parziale", "serale"}:
        return jsonify({"ok": False, "error": "Tipo prelievo non valido"}), 400

    try:
        cash_amount = Decimal(str(data.get("cash_amount", 0)))
    except (InvalidOperation, TypeError):
        return jsonify({"ok": False, "error": "Importo contanti non valido"}), 400

    if cash_amount < 0:
        return jsonify({"ok": False, "error": "Importo contanti non valido"}), 400

    if not isinstance(check_ids, list):
        return jsonify({"ok": False, "error": "check_ids deve essere una lista"}), 400

    checks = []
    if check_ids:
        checks = CashCheck.query.filter(CashCheck.id.in_(check_ids)).all()

    found_ids = {c.id for c in checks}
    missing_ids = [cid for cid in check_ids if cid not in found_ids]
    if missing_ids:
        return jsonify({
            "ok": False,
            "error": f"Assegni non trovati: {missing_ids}"
        }), 400

    already_taken_ids = {
        item.check_id
        for item in (
            db.session.query(CashOwnerTakeCheck.check_id)
            .join(CashOwnerTake, CashOwnerTake.id == CashOwnerTakeCheck.owner_take_id)
            .filter(
                CashOwnerTake.cash_day_id == row.cash_day_id,
                CashOwnerTake.id != row.id,
                CashOwnerTakeCheck.check_id.in_(check_ids) if check_ids else False
            )
            .all()
        )
    }

    if already_taken_ids:
        return jsonify({
            "ok": False,
            "error": f"Assegni già associati a un altro prelievo: {sorted(already_taken_ids)}"
        }), 400

    check_amount = Decimal("0")
    cash_day = CashDay.query.filter(CashDay.id == row.cash_day_id).first()

    for c in checks:
        valid_status = c.status in {"received", "moved", "spostato"}
        valid_day = c.received_date == cash_day.day_date
        if not (valid_status and valid_day):
            return jsonify({
                "ok": False,
                "error": f"Assegno {c.id} non valido per questo prelievo"
            }), 400
        check_amount += Decimal(str(c.amount or 0))

    try:
        row.take_type = take_type
        row.cash_amount = cash_amount
        row.check_amount = check_amount
        row.notes = notes
        row.updated_by_user_id = getattr(current_user, "id", None)

        CashOwnerTakeCheck.query.filter_by(owner_take_id=row.id).delete()

        for c in checks:
            db.session.add(CashOwnerTakeCheck(
                owner_take_id=row.id,
                check_id=c.id,
                check_amount=c.amount,
            ))

        db.session.commit()

        if cash_day:
            _bump_agenda_day_version(cash_day.day_date.isoformat())

        return jsonify({
            "ok": True,
            "owner_take_id": row.id,
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("api_update_owner_take error: %s", e)
        return jsonify({
            "ok": False,
            "error": "Errore interno durante l'aggiornamento del prelievo"
        }), 500


@cassa_bp.post("/api/row-check/toggle")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_toggle_row_check():
    data = request.get_json(silent=True) or {}

    entity_type = (data.get("entity_type") or "").strip()
    entity_id = data.get("entity_id")
    cash_day_id = data.get("cash_day_id")

    if not entity_type or entity_id is None or not cash_day_id:
        return jsonify({"ok": False, "error": "Missing parameters"}), 400

    try:
        cash_day_id = int(cash_day_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid cash_day_id"}), 400

    entity_id_str = str(entity_id).strip()

    # =========================
    # CASO PRI: accettiamo il toggle ma non lo persistiamo ancora
    # =========================
    if entity_id_str.startswith("pri-cm-"):
        requested_state = bool(data.get("is_checked", True))
        year = date.today().year

        updated_row = _pri_set_cash_move_checked(year, entity_id_str, requested_state)

        if updated_row is None:
            return jsonify({"ok": False, "error": "Movimento PRI non trovato"}), 404

        if updated_row is False:
            return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

        pri_data, day_node, _, _ = _pri_find_cash_move(year, entity_id_str)
        if day_node:
            _bump_agenda_day_version(day_node["date"])

        return jsonify({
            "ok": True,
            "entity_id": entity_id_str,
            "is_checked": bool(updated_row.get("is_checked")),
            "storage": "pri",
            "persistent": True,
        })

    if entity_id_str.startswith("pri-exp-"):
        requested_state = bool(data.get("is_checked", True))
        year = date.today().year

        updated_row = _pri_set_expense_checked(year, entity_id_str, requested_state)

        if updated_row is None:
            return jsonify({"ok": False, "error": "Spesa PRI non trovata"}), 404

        if updated_row is False:
            return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

        pri_data, day_node, _, _ = _pri_find_expense(year, entity_id_str)
        if day_node:
            _bump_agenda_day_version(day_node["date"])

        return jsonify({
            "ok": True,
            "entity_id": entity_id_str,
            "is_checked": bool(updated_row.get("is_checked")),
            "storage": "pri",
            "persistent": True,
        })

    if entity_id_str.startswith("pri-sale-"):
        requested_state = bool(data.get("is_checked", True))
        year = date.today().year

        updated_row = _pri_set_sale_checked(year, entity_id_str, requested_state)

        if updated_row is None:
            return jsonify({"ok": False, "error": "Incasso PRI non trovato"}), 404

        if updated_row is False:
            return jsonify({"ok": False, "error": "Vault privato non disponibile"}), 409

        pri_data, day_node, _, _ = _pri_find_sale(year, entity_id_str)
        if day_node:
            _bump_agenda_day_version(day_node["date"])

        return jsonify({
            "ok": True,
            "entity_id": entity_id_str,
            "is_checked": bool(updated_row.get("is_checked")),
            "storage": "pri",
            "persistent": True,
        })

    # =========================
    # CASO DB aziendale
    # =========================
    try:
        entity_id_int = int(entity_id_str)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid entity_id"}), 400

    row = CashRowCheck.query.filter_by(
        entity_type=entity_type,
        entity_id=entity_id_int
    ).first()

    try:
        if row:
            row.is_checked = not row.is_checked
            row.checked_by_user_id = getattr(current_user, "id", None)
            row.checked_at = datetime.utcnow() if row.is_checked else None
        else:
            row = CashRowCheck(
                cash_day_id=cash_day_id,
                entity_type=entity_type,
                entity_id=entity_id_int,
                is_checked=True,
                checked_by_user_id=getattr(current_user, "id", None),
                checked_at=datetime.utcnow(),
            )
            db.session.add(row)

        db.session.commit()

        cash_day = CashDay.query.filter_by(id=cash_day_id).first()
        if cash_day:
            _bump_agenda_day_version(cash_day.day_date.isoformat())

        return jsonify({
            "ok": True,
            "entity_id": entity_id_int,
            "is_checked": row.is_checked,
            "storage": "az",
            "persistent": True,
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("api_toggle_row_check error: %s", e)
        return jsonify({"ok": False, "error": "Internal error"}), 500


@cassa_bp.get("/api/row-checks")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_get_row_checks():
    cash_day_id = request.args.get("cash_day_id")
    entity_type = (request.args.get("entity_type") or "").strip()

    if not cash_day_id or not entity_type:
        return jsonify({"ok": False, "error": "Missing parameters"}), 400

    try:
        cash_day_id = int(cash_day_id)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid cash_day_id"}), 400

    rows = (
        CashRowCheck.query
        .filter_by(
            cash_day_id=cash_day_id,
            entity_type=entity_type
        )
        .all()
    )

    return jsonify({
        "ok": True,
        "checks": [
            {
                "entity_id": r.entity_id,
                "is_checked": r.is_checked
            }
            for r in rows
        ]
    })

@cassa_bp.get("/api/day/<day_date>/version")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_day_version(day_date):
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format"}), 400

    return jsonify({
        "ok": True,
        "day_date": d.isoformat(),
        "version": _get_agenda_day_version(d.isoformat()),
    })
