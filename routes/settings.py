from flask import request, flash, render_template, Blueprint, jsonify, redirect, current_app, url_for
from flask_login import login_required
from flask_socketio import SocketIO
from sqlalchemy import asc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from werkzeug.utils import secure_filename
import os
import uuid

from extensions import db
from models import (
    Menu,
    Role,
    ImportConflict,
    Articoli,
    User,
    UserRole,
    CashBank,
    PosCircuit,
    PosDevice,
    CashDeposit,
    CashIssuedCheck,
    CashSalePayment,
    PosMove,
    CashClosurePos,
    pos_device_circuits,
    CashSalePaymentPosMove,
)
from tools.role_required import role_required
from tools.preferences import build_preferences_sections, load_preferences_into_app_config, save_preferences_from_form
from config.tasks import (
    import_anagrafiche_task,
    import_articoli_task,
    import_barcode_task,
    import_giacenze_task,
    import_poleepo_products_task,
    import_ps_task,
)
from tools.ps_util import get_product_by_code
from tools.log_utils import log_task, get_logger
import hashlib
from datetime import datetime

logger = get_logger('settings')

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')
socketio = SocketIO()


def _form_bool(form, key, default=False):
    if key in form:
        value = str(form.get(key)).strip().lower()
        return value in {"1", "true", "on", "yes"}
    return bool(default)


def _parse_int(value, fallback=None):
    try:
        if value is None or str(value).strip() == "":
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _selected_ids_from_form(form, key):
    raw_values = form.getlist(key) if hasattr(form, "getlist") else []
    ids = []
    for raw in raw_values:
        parsed = _parse_int(raw)
        if parsed is not None:
            ids.append(parsed)
    return ids


def _settings_upload_folder(*parts):
    base = current_app.config.get("UPLOAD_FOLDER")
    if not base:
        base = os.path.join(current_app.root_path, "static", "uploads")
    folder = os.path.join(base, *parts)
    os.makedirs(folder, exist_ok=True)
    return folder


def _save_uploaded_logo(file_storage, prefix="logo"):
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None
    filename = secure_filename(file_storage.filename)
    if not filename:
        return None
    ext = os.path.splitext(filename)[1].lower() or ".png"
    target_name = f"{prefix}_{uuid.uuid4().hex}{ext}"
    folder = _settings_upload_folder("settings", "pos_circuits")
    target_path = os.path.join(folder, target_name)
    file_storage.save(target_path)
    return f"uploads/settings/pos_circuits/{target_name}"


def _promote_default_bank():
    bank = (
        CashBank.query
        .filter(CashBank.is_active.is_(True))
        .order_by(CashBank.sort_order.asc(), CashBank.name.asc())
        .first()
    )
    if bank:
        bank.is_default = True


def _promote_default_device():
    device = (
        PosDevice.query
        .filter(PosDevice.is_active.is_(True))
        .order_by(PosDevice.name.asc())
        .first()
    )
    if device:
        device.is_default = True


@settings_bp.route("/", methods=["GET"])
@login_required
@role_required(900)
@log_task(logger)
def settings_index():
    entries = [
        {
            "title": "Utenti",
            "description": "Anagrafiche, ruoli e stato degli account.",
            "route": url_for("settings.users_index"),
            "icon": "fa-solid fa-users",
            "icon_class": "text-bg-primary",
        },
        {
            "title": "Banche",
            "description": "Conti e istituti usati nei versamenti e negli incassi.",
            "route": url_for("settings.banks_index"),
            "icon": "fa-solid fa-building-columns",
            "icon_class": "text-bg-danger",
        },
        {
            "title": "Circuiti Carte",
            "description": "Circuiti di pagamento associati ai movimenti POS.",
            "route": url_for("settings.pos_circuits_index"),
            "icon": "fa-solid fa-credit-card",
            "icon_class": "text-bg-info",
        },
        {
            "title": "Dispositivi POS",
            "description": "Terminali e dispositivi usati per gli incassi elettronici.",
            "route": url_for("settings.pos_devices_index"),
            "icon": "fa-solid fa-cash-register",
            "icon_class": "text-bg-warning",
        },
        {
            "title": "Configurazione",
            "description": "Chiavi API, soglie, integrazioni e parametri runtime.",
            "route": url_for("settings.preferences"),
            "icon": "fa-solid fa-sliders",
            "icon_class": "text-bg-success",
        },
        {
            "title": "Gestione menù",
            "description": "Struttura della navbar e visibilità delle voci.",
            "route": url_for("settings.manage_menus"),
            "icon": "fa-solid fa-bars",
            "icon_class": "text-bg-dark",
        },
        {
            "title": "Conflitti import",
            "description": "Risoluzione guidata dei conflitti tra sorgenti.",
            "route": url_for("settings.import_conflicts_page"),
            "icon": "fa-solid fa-triangle-exclamation",
            "icon_class": "text-bg-warning",
        },
    ]
    return render_template("settings/index.html", entries=entries)


@settings_bp.route("/users", methods=["GET"])
@login_required
@role_required(900)
@log_task(logger)
def users_index():
    try:
        users = (
            User.query.options(
                selectinload(User.roles).selectinload(UserRole.role)
            )
            .order_by(User.surname.asc(), User.name.asc(), User.id.asc())
            .all()
        )
    except Exception as exc:
        logger.exception("Errore nel caricamento utenti")
        users = []
        flash(f"Impossibile caricare gli utenti: {exc}", "warning")

    return render_template("settings/users.html", users=users)


@settings_bp.route("/banks", methods=["GET", "POST"])
@login_required
@role_required(900)
@log_task(logger)
def banks_index():
    try:
        if request.method == "POST":
            bank_id = _parse_int(request.form.get("bank_id"))
            name = (request.form.get("name") or "").strip()
            if not name:
                flash("Il nome della banca è obbligatorio.", "warning")
                return redirect(url_for("settings.banks_index"))

            bank = CashBank.query.get(bank_id) if bank_id else None
            if bank is None:
                bank = CashBank()
                db.session.add(bank)

            bank.name = name
            bank.is_active = _form_bool(request.form, "is_active", True)
            bank.is_default = _form_bool(request.form, "is_default", False)
            bank.sort_order = _parse_int(request.form.get("sort_order"), 0) or 0

            if bank.is_default:
                CashBank.query.filter(CashBank.id != bank.id).update({"is_default": False})

            db.session.commit()
            flash("Banca salvata con successo.", "success")
            return redirect(url_for("settings.banks_index"))

        banks = (
            CashBank.query
            .order_by(CashBank.is_default.desc(), CashBank.sort_order.asc(), CashBank.name.asc())
            .all()
        )
    except Exception as exc:
        logger.exception("Errore nel caricamento banche")
        banks = []
        flash(f"Impossibile caricare le banche: {exc}", "warning")
    return render_template("settings/banks.html", banks=banks)


@settings_bp.route("/banks/<int:bank_id>/toggle", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def bank_toggle_active(bank_id):
    bank = CashBank.query.get_or_404(bank_id)
    bank.is_active = not bool(bank.is_active)
    if not bank.is_active and bank.is_default:
        bank.is_default = False
        _promote_default_bank()
    db.session.commit()
    flash("Stato banca aggiornato.", "success")
    return redirect(url_for("settings.banks_index"))


@settings_bp.route("/banks/<int:bank_id>/delete", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def bank_delete(bank_id):
    bank = CashBank.query.get_or_404(bank_id)
    usage_count = (
        CashDeposit.query.filter_by(bank_id=bank.id).count()
        + CashIssuedCheck.query.filter_by(bank_id=bank.id).count()
        + CashSalePayment.query.filter_by(bank_id=bank.id).count()
    )
    if usage_count:
        flash("La banca è usata da movimenti storici: disattivala invece di eliminarla.", "warning")
        return redirect(url_for("settings.banks_index"))

    was_default = bool(bank.is_default)
    db.session.delete(bank)
    db.session.commit()
    if was_default:
        _promote_default_bank()
        db.session.commit()
    flash("Banca eliminata.", "success")
    return redirect(url_for("settings.banks_index"))


@settings_bp.route("/pos-circuits", methods=["GET", "POST"])
@login_required
@role_required(900)
@log_task(logger)
def pos_circuits_index():
    try:
        if request.method == "POST":
            circuit_id = _parse_int(request.form.get("circuit_id"))
            name = (request.form.get("name") or "").strip()
            if not name:
                flash("Il nome del circuito è obbligatorio.", "warning")
                return redirect(url_for("settings.pos_circuits_index"))

            circuit = PosCircuit.query.get(circuit_id) if circuit_id else None
            if circuit is None:
                circuit = PosCircuit()
                db.session.add(circuit)

            circuit.name = name
            circuit.icon = (request.form.get("icon") or "").strip() or None
            uploaded_logo = request.files.get("logo_file")
            if uploaded_logo and uploaded_logo.filename:
                circuit.logo_path = _save_uploaded_logo(uploaded_logo, prefix=f"circuit_{circuit.id or 'new'}")
            circuit.is_active = _form_bool(request.form, "is_active", True)
            db.session.commit()
            flash("Circuito salvato con successo.", "success")
            return redirect(url_for("settings.pos_circuits_index"))

        circuits = PosCircuit.query.order_by(PosCircuit.is_active.desc(), PosCircuit.name.asc()).all()
    except Exception as exc:
        logger.exception("Errore nel caricamento circuiti POS")
        circuits = []
        flash(f"Impossibile caricare i circuiti carte: {exc}", "warning")
    icon_choices = [
        "fa-solid fa-credit-card",
        "fa-solid fa-cc-visa",
        "fa-solid fa-cc-mastercard",
        "fa-solid fa-cc-amex",
        "fa-solid fa-money-check-dollar",
        "fa-solid fa-wallet",
        "fa-solid fa-circle-nodes",
        "fa-solid fa-building-columns",
        "fa-solid fa-hand-holding-dollar",
        "fa-solid fa-receipt",
        "fa-solid fa-landmark",
        "fa-solid fa-cart-shopping",
    ]
    return render_template("settings/pos_circuits.html", circuits=circuits, icon_choices=icon_choices)


@settings_bp.route("/pos-circuits/<int:circuit_id>/toggle", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def pos_circuit_toggle_active(circuit_id):
    circuit = PosCircuit.query.get_or_404(circuit_id)
    circuit.is_active = not bool(circuit.is_active)
    db.session.commit()
    flash("Stato circuito aggiornato.", "success")
    return redirect(url_for("settings.pos_circuits_index"))


@settings_bp.route("/pos-circuits/<int:circuit_id>/delete", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def pos_circuit_delete(circuit_id):
    circuit = PosCircuit.query.get_or_404(circuit_id)
    usage_count = (
        db.session.query(pos_device_circuits).filter(pos_device_circuits.c.pos_circuit_id == circuit.id).count()
        + PosMove.query.filter_by(pos_circuit_id=circuit.id).count()
        + CashClosurePos.query.filter_by(pos_circuit_id=circuit.id).count()
        + CashSalePaymentPosMove.query.join(PosMove).filter(PosMove.pos_circuit_id == circuit.id).count()
    )
    if usage_count:
        flash("Il circuito è usato da dispositivi o movimenti storici: disattivalo invece di eliminarlo.", "warning")
        return redirect(url_for("settings.pos_circuits_index"))

    db.session.delete(circuit)
    db.session.commit()
    flash("Circuito eliminato.", "success")
    return redirect(url_for("settings.pos_circuits_index"))


@settings_bp.route("/pos-devices", methods=["GET", "POST"])
@login_required
@role_required(900)
@log_task(logger)
def pos_devices_index():
    try:
        if request.method == "POST":
            device_id = _parse_int(request.form.get("device_id"))
            name = (request.form.get("name") or "").strip()
            if not name:
                flash("Il nome del dispositivo POS è obbligatorio.", "warning")
                return redirect(url_for("settings.pos_devices_index"))

            device = PosDevice.query.get(device_id) if device_id else None
            if device is None:
                device = PosDevice()
                db.session.add(device)

            device.name = name
            device.type = (request.form.get("type") or "physical").strip() or "physical"
            device.is_active = _form_bool(request.form, "is_active", True)
            device.is_default = _form_bool(request.form, "is_default", False)

            selected_circuits = _selected_ids_from_form(request.form, "circuit_ids")
            for circuit in list(device.circuits.all()):
                device.circuits.remove(circuit)
            if selected_circuits:
                for circuit in PosCircuit.query.filter(PosCircuit.id.in_(selected_circuits)).all():
                    device.circuits.append(circuit)

            if device.is_default:
                PosDevice.query.filter(PosDevice.id != device.id).update({"is_default": False})

            db.session.commit()
            flash("Dispositivo POS salvato con successo.", "success")
            return redirect(url_for("settings.pos_devices_index"))

        circuits_all = PosCircuit.query.order_by(PosCircuit.is_active.desc(), PosCircuit.name.asc()).all()
        devices = PosDevice.query.order_by(PosDevice.is_default.desc(), PosDevice.is_active.desc(), PosDevice.name.asc()).all()
    except Exception as exc:
        logger.exception("Errore nel caricamento dispositivi POS")
        circuits_all = []
        devices = []
        flash(f"Impossibile caricare i dispositivi POS: {exc}", "warning")
    return render_template("settings/pos_devices.html", devices=devices, circuits_all=circuits_all)


@settings_bp.route("/pos-devices/<int:device_id>/toggle", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def pos_device_toggle_active(device_id):
    device = PosDevice.query.get_or_404(device_id)
    device.is_active = not bool(device.is_active)
    if not device.is_active and device.is_default:
        device.is_default = False
        _promote_default_device()
    db.session.commit()
    flash("Stato dispositivo aggiornato.", "success")
    return redirect(url_for("settings.pos_devices_index"))


@settings_bp.route("/pos-devices/<int:device_id>/delete", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def pos_device_delete(device_id):
    device = PosDevice.query.get_or_404(device_id)
    usage_count = (
        db.session.query(pos_device_circuits).filter(pos_device_circuits.c.pos_device_id == device.id).count()
        + PosMove.query.filter_by(pos_device_id=device.id).count()
        + CashClosurePos.query.filter_by(pos_device_id=device.id).count()
        + CashSalePaymentPosMove.query.join(PosMove).filter(PosMove.pos_device_id == device.id).count()
    )
    if usage_count:
        flash("Il dispositivo POS è usato da movimenti storici o associazioni: disattivalo invece di eliminarlo.", "warning")
        return redirect(url_for("settings.pos_devices_index"))

    was_default = bool(device.is_default)
    db.session.delete(device)
    db.session.commit()
    if was_default:
        _promote_default_device()
        db.session.commit()
    flash("Dispositivo POS eliminato.", "success")
    return redirect(url_for("settings.pos_devices_index"))


def _save_role_preferences_from_form(form):
    changed = 0
    for role in Role.query.order_by(Role.weight.asc(), Role.name.asc()).all():
        weight_raw = (form.get(f"role_weight_{role.id}") or "").strip()
        description_raw = (form.get(f"role_description_{role.id}") or "").strip()

        if weight_raw == "":
            continue

        new_weight = int(weight_raw)
        if role.weight != new_weight:
            role.weight = new_weight
            changed += 1

        new_description = description_raw or None
        if role.description != new_description:
            role.description = new_description
            changed += 1

    db.session.commit()
    return changed


@settings_bp.route("/preferences", methods=["GET", "POST"])
@login_required
@role_required(900)
@log_task(logger)
def preferences():
    try:
        if request.method == "POST":
            form_type = (request.form.get("form_type") or "preferences").strip().lower()

            if form_type == "roles":
                changed = _save_role_preferences_from_form(request.form)
                flash("Ruoli aggiornati con successo.", "success")
                logger.info("Aggiornati %s campi ruoli.", changed)
                return redirect(url_for("settings.preferences"))

            changed_keys = save_preferences_from_form(request.form)
            load_preferences_into_app_config(current_app._get_current_object())
            flash("Preferenze salvate con successo.", "success")
            logger.info("Aggiornate preferenze: %s", ", ".join(changed_keys) if changed_keys else "nessuna modifica")
            return redirect(url_for("settings.preferences"))

        sections = build_preferences_sections(current_app._get_current_object())
        try:
            roles = Role.query.order_by(Role.weight.asc(), Role.name.asc()).all()
        except Exception as exc:
            logger.warning("Ruoli non disponibili durante il caricamento preferenze: %s", exc)
            roles = []
        return render_template("settings/preferences.html", sections=sections, roles=roles)
    except Exception as exc:
        db.session.rollback()
        logger.exception("Errore nella pagina preferenze")
        return (
            "<!doctype html><html lang='it'><head><meta charset='utf-8'><title>Preferenze</title></head>"
            "<body style='font-family:sans-serif;padding:24px'>"
            "<h1>Preferenze</h1>"
            "<p>La pagina non e' ancora disponibile per un errore interno.</p>"
            f"<pre>{exc}</pre>"
            "</body></html>",
            200,
        )


@settings_bp.route('/update_menu', methods=['POST'])
@login_required
@role_required(500)
@log_task(logger)
def update_menu():
    try:
        menu_id = request.form.get('menu_id')
        if not menu_id:
            logger.warning("Menu ID mancante.")
            return jsonify({'success': False, 'error': 'Menu ID is missing'}), 400

        menu = Menu.query.get(menu_id)
        if not menu:
            logger.warning(f"Nessun menu trovato con ID {menu_id}")
            return jsonify({'success': False, 'error': f'No menu found with ID {menu_id}'}), 404

        menu.name = request.form.get('name')
        menu.route = request.form.get('route')
        menu.is_active = request.form.get('is_active') == 'true'
        menu.weight = request.form.get('weight')
        menu.parent_id = request.form.get('parent_id')
        menu.sort_order = int(request.form.get("sort_order") or 0)
        db.session.commit()

        logger.info(f"Menu ID {menu_id} aggiornato con successo.")
        return jsonify({'success': True, 'message': 'Menu updated successfully'})
    except Exception as e:
        db.session.rollback()
        logger.exception("Errore nell'aggiornamento menu")
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/menu/<int:menu_id>')
@log_task(logger)
def get_menu_data(menu_id):
    logger.info(f"Richiesta dati menu ID: {menu_id}")
    menu = Menu.query.get_or_404(menu_id)
    return jsonify(menu.to_dict())


@settings_bp.route('/menus', methods=['GET', 'POST'])
@login_required
@role_required(900)
@log_task(logger)
def manage_menus():
    if request.method == 'POST':
        name = request.form['name']
        route = request.form['route']
        parent_id = request.form.get('parent_id', None)
        weight = request.form.get('weight', 0)
        parent_id = request.form.get('parent_id') or None
        parent_id_int = int(parent_id) if parent_id is not None else None
        weight = int(request.form.get('weight') or 0)

        max_sort = (db.session.query(db.func.max(Menu.sort_order))
                    .filter(Menu.parent_id == parent_id_int)
                    .scalar())
        next_sort = (max_sort or 0) + 1

        new_menu = Menu(
            name=name,
            route=route or None,
            parent_id=parent_id_int,
            weight=weight,
            sort_order=next_sort,
            is_active=True
        )
        db.session.add(new_menu)
        db.session.commit()
        flash('Menu salvato con successo!', 'success')
        logger.info(f"Nuovo menu aggiunto: {name}")
    menus = Menu.query.all()
    roles = Role.query.order_by(Role.weight.desc()).all()
    menu_fields = [column.name for column in Menu.__table__.columns if column.name != 'id']
    return render_template('settings/menus.html', menus=menus, roles=roles, menu_fields=menu_fields)


@settings_bp.route('/import_articoli', methods=['GET', 'POST'])
@login_required
@role_required(100)
@log_task(logger)
def lancia_import_articoli():
    logger.info("Importazione articoli richiesta.")
    task = import_articoli_task.delay()
    from tools.redis_utils import update_task, status_string
    update_task(task.id, "Importazione articoli", 0, status_string['attached'])
    return '', 204


@settings_bp.route('/import_ps_data', methods=['GET', 'POST'])
@login_required
@role_required(500)
@log_task(logger)
def lancia_import_prestashop():
    logger.info("Importazione Prestashop richiesta.")
    task = import_ps_task.delay()
    from tools.redis_utils import update_task, status_string
    update_task(task.id, "Importazione dati da Prestashop", 0, status_string['attached'])
    return '', 204


@settings_bp.route('/import_poleepo_products', methods=['GET', 'POST'])
@login_required
@role_required(500)
@log_task(logger)
def lancia_import_prodotti_poleepo():
    logger.info("Importazione prodotti Poleepo richiesta.")
    task = import_poleepo_products_task.delay({})
    from tools.redis_utils import update_task, status_string
    update_task(task.id, "Importazione prodotti da Poleepo", 0, status_string['attached'])
    return '', 204


@settings_bp.route("/reorder_menus", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def reorder_menus():
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []

    if not isinstance(items, list) or not items:
        return jsonify({"ok": False, "error": "Payload non valido: items[] richiesto"}), 400

    try:
        parent_by_id = {
            int(it["id"]): (int(it["parent_id"]) if it.get("parent_id") is not None else None)
            for it in items
            if it.get("id") is not None
        }

        def would_create_cycle(menu_id, parent_id):
            seen = {menu_id}
            current = parent_id
            while current is not None:
                if current in seen:
                    return True
                seen.add(current)
                if current in parent_by_id:
                    current = parent_by_id[current]
                else:
                    parent = Menu.query.get(current)
                    current = parent.parent_id if parent else None
            return False

        # Validazione + update
        for it in items:
            mid = it.get("id")
            if mid is None:
                continue

            mid = int(mid)
            menu = Menu.query.get(mid)
            if not menu:
                continue

            parent_id = it.get("parent_id", None)
            parent_id = int(parent_id) if parent_id is not None else None
            sort_order = it.get("sort_order", 0)

            if parent_id == mid or would_create_cycle(mid, parent_id):
                return jsonify({"ok": False, "error": "Gerarchia menu non valida"}), 400

            menu.parent_id = parent_id
            menu.sort_order = int(sort_order)

        db.session.commit()
        return jsonify({"ok": True, "updated": len(items)})
    except Exception as e:
        db.session.rollback()
        logger.exception("Errore reorder_menus")
        return jsonify({"ok": False, "error": str(e)}), 500


@settings_bp.route('/import_art_descr', methods=['GET', 'POST'])
@login_required
@role_required(500)
@log_task(logger)
def lancia_import_descr_prestashop():
    logger.info("Importazione descrizione articolo da Prestashop richiesta (hardcoded).")
    get_product_by_code('VB075133-21')
    return jsonify({'success': True, 'message': 'Interrogazione conclusa.'})


@settings_bp.route('/import_giacenze', methods=['GET', 'POST'])
@login_required
@role_required(100)
@log_task(logger)
def lancia_import_giacenze():
    logger.info("Importazione giacenze richiesta.")
    task = import_giacenze_task.delay()
    from tools.redis_utils import update_task, status_string
    update_task(task.id, "Importazione giacenze da gestionale", 0, status_string['attached'])
    return '', 204


@settings_bp.route('/import_barcode', methods=['GET', 'POST'])
@login_required
@role_required(100)
@log_task(logger)
def lancia_import_barcode():
    logger.info("Importazione codici a barre richiesta.")
    task = import_barcode_task.delay()
    from tools.redis_utils import update_task, status_string
    update_task(task.id, "Importazione codici a barre articoli da gestionale", 0, status_string['attached'])
    return '', 204


@settings_bp.route('/import_anagrafiche', methods=['GET', 'POST'])
@login_required
@role_required(100)
@log_task(logger)
def lancia_import_anagrafiche():
    logger.info("Importazione anagrafiche richiesta.")
    task = import_anagrafiche_task.delay()
    from tools.redis_utils import update_task, status_string
    update_task(task.id, "Importazione anagrafiche TeamSystem", 0, status_string['attached'])
    if request.accept_mimetypes.best == "application/json" or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "task_id": task.id}), 202
    flash("Importazione anagrafiche avviata.", "success")
    return redirect(request.referrer or "/importazioni/storico")


@settings_bp.route("/import_conflicts", methods=["GET"])
def import_conflicts_page():
    return render_template("settings/import_conflicts.html")


@settings_bp.route("/next_conflict", methods=["GET"])
def api_import_conflicts_next():
    ctype = request.args.get("type")  # es. "barcode" (o None per tutti)

    q = (ImportConflict.query
         .filter(ImportConflict.status == "pending"))

    if ctype:
        q = q.filter(ImportConflict.type == ctype)

    # prende il più vecchio pending
    conflict = (q.order_by(ImportConflict.created_at.asc())
                .first())

    if not conflict:
        return jsonify({"ok": True, "conflict": None})

    return jsonify({
        "ok": True,
        "conflict": {
            "id": conflict.id,
            "type": conflict.type,
            "payload": conflict.payload,
            "created_at": conflict.created_at.isoformat() if conflict.created_at else None,
        }
    })


import hashlib
import json
from flask import request, jsonify
from flask_login import login_required

from extensions import db
from models import ImportConflict, ImportConflictResolution  # adegua i nomi se diversi


def _sha256_text(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@settings_bp.route("/resolve_conflict", methods=["POST"])
@login_required
def resolve_conflict():
    data = request.get_json(silent=True) or {}
    conflict_id = data.get("id")
    action = (data.get("action") or "").strip().upper()
    mode = (data.get("mode") or "CONDITIONAL").strip().upper()  # opzionale dal frontend

    if not conflict_id or action not in {"KEEP_CSV", "KEEP_DB", "SKIP"}:
        return jsonify(ok=False, error="Payload non valido: servono id e action (KEEP_CSV|KEEP_DB|SKIP)."), 400

    c = ImportConflict.query.get(conflict_id)
    if not c:
        return jsonify(ok=False, error="Conflitto non trovato."), 404

    # SKIP: non applica nulla e NON salva una regola; semplicemente lascia il record e passa oltre
    if action == "SKIP":
        return jsonify(ok=True, skipped=True, id=c.id)

    # payload: atteso {cod_art, csv:{...}, db:{...}} come nel tuo esempio
    payload = c.payload or {}
    cod_art = payload.get("cod_art") or payload.get("entity_key")  # fallback
    csv_obj = payload.get("csv") or {}
    db_obj = payload.get("db") or {}

    if not cod_art:
        return jsonify(ok=False, error="Payload conflitto senza cod_art/entity_key."), 400

    # Per ora: memorizziamo una regola per OGNI campo presente nei dict csv/db.
    # (Se vuoi “un solo campo alla volta” lo rendiamo più selettivo nello step successivo.)
    all_fields = sorted(set(list(csv_obj.keys()) + list(db_obj.keys())))
    if not all_fields:
        return jsonify(ok=False, error="Payload conflitto senza campi csv/db."), 400

    created = 0
    for field in all_fields:
        csv_val = csv_obj.get(field)
        db_val = db_obj.get(field)

        r = ImportConflictResolution(
            type=c.type,
            entity_key=str(cod_art),
            field=str(field),

            db_value=None if db_val is None else str(db_val),
            csv_value=None if csv_val is None else str(csv_val),

            db_value_hash=_sha256_text(db_val),
            csv_value_hash=_sha256_text(csv_val),

            action=action,
            mode=mode if mode in {"CONDITIONAL", "ALWAYS"} else "CONDITIONAL",
        )
        db.session.add(r)
        created += 1

    # Applica la risoluzione “adesso” sul DB (se KEEP_CSV)
    # oppure non fa nulla (KEEP_DB), ma in entrambi i casi il conflitto viene rimosso.
    if action == "KEEP_CSV":
        art = Articoli.query.filter_by(cod_art=cod_art).first()
        if not art:
            return jsonify(ok=False, error=f"Articolo not found for cod_art={cod_art}"), 404

        # Applica CSV -> DB (adatta i nomi campi se diverso)
        if "descrizione" in csv_obj:
            art.descrizione = csv_obj.get("descrizione")
        if "descrizione_aggiuntiva" in csv_obj:
            art.descrizione_aggiuntiva = csv_obj.get("descrizione_aggiuntiva")
        if "prezzo" in csv_obj:
            art.prezzo = csv_obj.get("prezzo")

    # Rimuovi il conflitto perché è stato deciso
    db.session.delete(c)
    db.session.commit()

    return jsonify(ok=True, resolved=True, action=action, rules_created=created)


@settings_bp.route("/get_menu_structure", methods=["GET"])
@login_required
@role_required(900)
@log_task(logger)
def get_menu_structure():
    menus = (
        Menu.query
        .order_by(asc(Menu.parent_id), asc(Menu.sort_order), asc(Menu.id))
        .all()
    )
    return jsonify([m.to_dict() for m in menus])


@settings_bp.route("/create_menu", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def create_menu():
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    item_type = (data.get("item_type") or "link").strip()
    if item_type not in ("link", "separator"):
        return jsonify(ok=False, error="Tipo menu non valido"), 400
    if item_type == "separator" and not name:
        name = "Separatore"
    if not name:
        return jsonify(ok=False, error="Nome obbligatorio"), 400

    parent_id = data.get("parent_id")
    parent_id = int(parent_id) if parent_id is not None else None
    if parent_id is not None and not Menu.query.get(parent_id):
        return jsonify(ok=False, error="Menu padre non trovato"), 404

    weight = int(data.get("weight") or 0)
    route = data.get("route") or None
    is_active = bool(data.get("is_active", True))
    is_visible = bool(data.get("is_visible", True))
    if is_active:
        is_visible = True

    # sort_order = ultimo tra i fratelli + 1
    max_sort = (db.session.query(db.func.max(Menu.sort_order))
                .filter(Menu.parent_id == parent_id)
                .scalar())
    sort_order = (max_sort or 0) + 1

    m = Menu(
        name=name,
        route=route,
        parent_id=parent_id,
        weight=weight,
        sort_order=sort_order,
        is_active=is_active,
        is_visible=is_visible,
        item_type=item_type
    )
    db.session.add(m)
    db.session.commit()

    return jsonify(ok=True, id=m.id)


@settings_bp.route("/update_menu_json", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def update_menu_json():
    data = request.get_json(silent=True) or {}
    mid = data.get("id")
    if not mid:
        return jsonify(ok=False, error="ID mancante"), 400

    m = Menu.query.get_or_404(int(mid))

    m.name = (data.get("name") or "").strip()
    item_type = (data.get("item_type") or m.item_type or "link").strip()
    if item_type not in ("link", "separator"):
        return jsonify(ok=False, error="Tipo menu non valido"), 400
    if item_type == "separator" and not m.name:
        m.name = "Separatore"
    if not m.name:
        return jsonify(ok=False, error="Nome obbligatorio"), 400

    m.route = data.get("route") or None
    m.weight = int(data.get("weight") or 0)
    m.is_active = bool(data.get("is_active", True))
    m.is_visible = bool(data.get("is_visible", True))
    if m.is_active:
        m.is_visible = True
    m.item_type = item_type

    if "parent_id" in data:
        parent_id = data.get("parent_id")
        parent_id = int(parent_id) if parent_id is not None else None

        if parent_id == m.id:
            return jsonify(ok=False, error="Un menu non può essere padre di sé stesso"), 400

        current = parent_id
        while current is not None:
            if current == m.id:
                return jsonify(ok=False, error="Gerarchia menu non valida"), 400

            parent = Menu.query.get(current)
            if not parent:
                return jsonify(ok=False, error="Menu padre non trovato"), 404

            current = parent.parent_id

        m.parent_id = parent_id

    db.session.commit()
    return jsonify(ok=True)


@settings_bp.route("/delete_menu/<int:menu_id>", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def delete_menu(menu_id):
    data = request.get_json(silent=True) or {}
    cascade = bool(data.get("cascade", False))

    menu = Menu.query.get_or_404(menu_id)

    children = Menu.query.filter(Menu.parent_id == menu.id).all()
    has_children = len(children) > 0

    if has_children and not cascade:
        return jsonify({
            "ok": False,
            "code": "HAS_CHILDREN",
            "error": "Il menu contiene sotto-menu. Conferma eliminazione con cascata."
        }), 409

    try:
        if cascade:
            # elimina figli (e nipoti) in profondità
            def delete_rec(m):
                for c in Menu.query.filter(Menu.parent_id == m.id).all():
                    delete_rec(c)
                db.session.delete(m)

            delete_rec(menu)
        else:
            db.session.delete(menu)

        db.session.commit()
        return jsonify({"ok": True, "cascade": cascade})

    except Exception as e:
        db.session.rollback()
        logger.exception("Errore delete_menu")
        return jsonify({"ok": False, "error": str(e)}), 500


@settings_bp.route("/toggle_menu_active/<int:menu_id>", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def toggle_menu_active(menu_id):
    m = Menu.query.get_or_404(menu_id)
    m.is_active = not bool(m.is_active)
    if m.is_active:
        m.is_visible = True
    db.session.commit()
    return jsonify(ok=True, id=m.id, is_active=bool(m.is_active))


@settings_bp.route("/toggle_menu_visible/<int:menu_id>", methods=["POST"])
@login_required
@role_required(900)
@log_task(logger)
def toggle_menu_visible(menu_id):
    m = Menu.query.get_or_404(menu_id)
    if m.is_active:
        return jsonify(ok=False, error="Un menu attivo è sempre visibile"), 400
    m.is_visible = not bool(m.is_visible)
    db.session.commit()
    return jsonify(ok=True, id=m.id, is_visible=bool(m.is_visible))
