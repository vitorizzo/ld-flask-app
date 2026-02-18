import logging
import os
import json
import base64
import secrets

from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from decimal import Decimal
from datetime import date, datetime, timedelta
from sqlalchemy.orm import selectinload

from tools.log_utils import get_logger
from tools.role_required import role_required
from extensions import db
from models import CashDay, CashSale, CashExpense

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


def _derive_key(password: str, salt: bytes) -> bytes:
    import hashlib
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _KDF_ITERS,
        dklen=32
    )


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
    mount_root, vault_dir, year, year_file = _vault_config()

    mounted = os.path.ismount(mount_root)
    vault_dir_exists = os.path.isdir(vault_dir)
    vault_dir_writable = vault_dir_exists and _dir_writable(vault_dir)
    year_file_exists = os.path.isfile(year_file)
    unlocked = bool(session.get("pri_vault_unlocked", False))

    return jsonify({
        "ok": True,
        "vault": {
            "mount_root": mount_root,
            "mounted": mounted,
            "vault_dir": vault_dir,
            "vault_dir_exists": vault_dir_exists,
            "vault_dir_writable": vault_dir_writable,
            "year": year,
            "year_file_exists": year_file_exists,
            "unlocked": unlocked,
        }
    })


@cassa_bp.route("/api/private/unlock", methods=["POST"])
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_private_unlock():
    mount_root, vault_dir, year, year_file = _vault_config()

    if not os.path.ismount(mount_root):
        return jsonify({"ok": False, "error": "Vault not mounted"}), 409

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
            _decrypt_payload(blob, password)  # valida password
        else:
            payload = _empty_vault_payload(year)
            blob = _encrypt_payload(payload, password)
            _atomic_write(year_file, blob)

        session["pri_vault_unlocked"] = True
        return jsonify({"ok": True, "vault": {"year": year, "unlocked": True, "year_file_exists": True}})
    except InvalidTag:
        session["pri_vault_unlocked"] = False
        return jsonify({"ok": False, "error": "Invalid password"}), 401
    except Exception as e:
        logger.exception("Vault unlock unexpected error: %s", e)
        session["pri_vault_unlocked"] = False
        return jsonify({"ok": False, "error": "Vault error"}), 500


@cassa_bp.route("/api/private/lock", methods=["POST"])
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_private_lock():
    session["pri_vault_unlocked"] = False
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
        )
        .filter(CashDay.day_date == d)
        .first()
    )

    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    totals = _compute_day_totals_from_db(cash_day, view=view)
    return jsonify({
        "ok": True,
        "day": {
            "id": cash_day.id,
            "day_date": cash_day.day_date.isoformat(),
            "status": cash_day.status,
            "opening_float": float(_to_dec(cash_day.opening_float)),
        },
        "totals": totals,
        # utile per il frontend per sapere “cosa manca”:
        "note": "Preview calcolata solo su DB aziendale. Il contributo del vault (+/x) verrà integrato dopo.",
    })
