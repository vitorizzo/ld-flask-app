import logging
import os
import json
import base64
import secrets

from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required, current_user
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timedelta
from sqlalchemy import exists, or_, and_, func
from sqlalchemy.orm import selectinload

from tools.log_utils import get_logger
from tools.role_required import role_required
from extensions import db
from models import CashDay, CashSale, CashExpense, CashMove, PosMove, CashCheck, CashSalePayment, CashExpensePayment, \
    PosDevice, PosCircuit, pos_device_circuits, CashCustomer, CashCustomerAlias, CashBank, CashSaleCheck, \
    CashDrawerCount, CashDrawerCountLine
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
        prev_day = (
            CashDay.query
            .options(
                selectinload(CashDay.closure),
                selectinload(CashDay.drawer_count).selectinload(CashDrawerCount.lines),
            )
            .filter(CashDay.day_date < target_date)
            .order_by(CashDay.day_date.desc())
            .first()
        )

        opening_float = float(_get_effective_closing_cash_drawer_for_day(prev_day) or 0)

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

    result = calculate_closure_pure(
        cash_day_id=cash_day.id,
        opening_float=cash_day.opening_float,
        total_corrispettivi=Decimal(request.args.get("corrispettivi", "0")),
        fondo_finale=fondo_finale,
        saldo_versabile_precedente=saldo_versabile_precedente,
        incasso_consegnato=Decimal(request.args.get("incasso_consegnato", "0")),
    )

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

    # entrambe presenti: vince la più recente
    if drawer_ts and closure_ts:
        if drawer_ts >= closure_ts:
            return drawer_value.quantize(Decimal("0.01"))
        return closure_value.quantize(Decimal("0.01"))

    # fallback prudenziale
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

    description = (data.get("description") or "").strip()
    if not description:
        return jsonify({"ok": False, "error": "Missing description"}), 400

    customer_id = data.get("customer_id")
    customer_label = (data.get("customer_label") or "").strip() or None
    off_cash = bool(data.get("off_cash", False))

    if customer_id:
        customer = CashCustomer.query.filter_by(id=customer_id).first()
        if not customer:
            return jsonify({"ok": False, "error": "Customer not found"}), 400

    try:
        payments_data = _normalize_payments_payload(data)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    sale = CashSale(
        cash_day_id=cash_day.id,
        created_by_user_id=getattr(current_user, "id", None),
        customer_id=customer_id,
        customer_label=customer_label,
        notes=description,
    )

    try:
        for idx, p in enumerate(payments_data, start=1):
            method = (p.get("method") or "").strip().lower()
            if method not in {"cash", "pos", "bank", "check"}:
                raise ValueError(f"Invalid payment method at row {idx}")

            amount = _to_decimal_amount(p.get("amount"), f"payments[{idx}].amount")

            payment = CashSalePayment(
                direction="in",
                method=method,
                off_cash=off_cash,
                amount=amount,
                flag=flag,
                description=description,
            )

            if method == "pos":
                pos_device_id = p.get("pos_device_id")
                pos_circuit_id = p.get("pos_circuit_id")
                if not pos_device_id or not pos_circuit_id:
                    raise ValueError(f"Missing POS device/circuit at row {idx}")
                _validate_pos_pair(pos_device_id, pos_circuit_id)
                payment.pos_device_id = pos_device_id
                payment.pos_circuit_id = pos_circuit_id

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

                sale.checks.append(
                    CashSaleCheck(
                        check_id=check.id,
                        check_amount=amount,
                    )
                )

            sale.payments.append(payment)

        db.session.add(sale)
        db.session.commit()

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
        .options(selectinload(CashDay.sales).selectinload(CashSale.payments))
        .filter(CashDay.day_date == d)
        .first()
    )
    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    items = []
    for s in cash_day.sales:
        pay = []
        for p in (s.payments or []):
            pay.append({
                "id": p.id,
                "direction": p.direction,
                "method": p.method,
                "off_cash": bool(p.off_cash),
                "amount": float(p.amount or 0),
                "flag": p.flag,
                "description": p.description,
                "pos_device_id": p.pos_device_id,
                "pos_circuit_id": p.pos_circuit_id,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            })
        items.append({
            "id": s.id,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "customer_id": s.customer_id,
            "customer_label": s.customer_label,
            "doc_ref": s.doc_ref,
            "notes": s.notes,
            "payments": pay,
        })

    return jsonify({"ok": True, "day_date": d.isoformat(), "sales": items})


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

    description = (data.get("description") or "").strip()
    if not description:
        return jsonify({"ok": False, "error": "Missing description"}), 400

    off_cash = bool(data.get("off_cash", False))

    try:
        payments_data = _normalize_payments_payload(data)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    exp = CashExpense(
        cash_day_id=cash_day.id,
        created_by_user_id=getattr(current_user, "id", None),
        notes=description,
    )

    try:
        for idx, p in enumerate(payments_data, start=1):
            method = (p.get("method") or "").strip().lower()
            if method not in {"cash", "pos", "bank"}:
                if method == "check":
                    raise ValueError("Check payment is not supported for expenses with current data model")
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
                pos_device_id = p.get("pos_device_id")
                pos_circuit_id = p.get("pos_circuit_id")
                if not pos_device_id or not pos_circuit_id:
                    raise ValueError(f"Missing POS device/circuit at row {idx}")
                _validate_pos_pair(pos_device_id, pos_circuit_id)
                payment.pos_device_id = pos_device_id
                payment.pos_circuit_id = pos_circuit_id

            elif method == "bank":
                bank_id = p.get("bank_id")
                if not bank_id:
                    raise ValueError(f"Missing bank_id at row {idx}")
                _validate_bank(bank_id)
                payment.bank_id = bank_id

            exp.payments.append(payment)

        db.session.add(exp)
        db.session.commit()

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
                "pos_device_id": p.pos_device_id,
                "pos_circuit_id": p.pos_circuit_id,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            })
        items.append({
            "id": e.id,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "doc_ref": e.doc_ref,
            "notes": e.notes,
            "payments": pay,
        })

    return jsonify({"ok": True, "day_date": d.isoformat(), "expenses": items})


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

    # 1) device/circuit attivi
    dev = PosDevice.query.filter_by(id=pos_device_id, is_active=True).first()
    if not dev:
        return jsonify({"ok": False, "error": "PosDevice not found or inactive"}), 400

    cir = PosCircuit.query.filter_by(id=pos_circuit_id, is_active=True).first()
    if not cir:
        return jsonify({"ok": False, "error": "PosCircuit not found or inactive"}), 400

    # 2) coppia consentita in tabella ponte
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

    return jsonify({"ok": True, "pos_move_id": m.id}), 201


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

    # preload name/icon per badge
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

    performed_by = (data.get("performed_by") or "").strip()
    if not performed_by:
        return jsonify({"ok": False, "error": "Missing performed_by"}), 400

    notes = (data.get("notes") or "").strip() or None
    kind = (data.get("kind") or "altro").strip() or "altro"

    direction = "in" if raw_amount > 0 else "out"
    amount = abs(raw_amount)

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

    return jsonify({"ok": True, "cash_move_id": m.id}), 201


@cassa_bp.get("/api/day/<day_date>/cash_moves", endpoint="api_list_cash_moves")
@login_required
@role_required(min_weight=MIN_AGENDA_WEIGHT)
def api_list_cash_moves(day_date):
    """
    Lista movimenti di cassa della giornata.
    """
    try:
        d = datetime.strptime(day_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid day_date format (YYYY-MM-DD)"}), 400

    cash_day = CashDay.query.filter(CashDay.day_date == d).first()
    if not cash_day:
        return jsonify({"ok": False, "error": "CashDay not found"}), 404

    moves = (
        CashMove.query
        .filter(CashMove.cash_day_id == cash_day.id)
        .order_by(CashMove.created_at.asc())
        .all()
    )

    out = []
    for m in moves:
        out.append({
            "id": m.id,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "direction": m.direction,
            "amount": float(m.amount or 0),
            "performed_by": m.performed_by,
            "notes": m.notes,
            "kind": m.kind,
        })

    return jsonify({"ok": True, "day_date": d.isoformat(), "cash_moves": out})


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
