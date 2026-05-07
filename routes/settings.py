from flask import request, flash, render_template, Blueprint, jsonify
from flask_login import login_required
from flask_socketio import SocketIO
from sqlalchemy import asc

from extensions import db
from models import Menu, Role, ImportConflict, Articoli
from tools.role_required import role_required
from config.tasks import import_articoli_task, import_barcode_task, import_giacenze_task, import_ps_task
from tools.ps_util import get_product_by_code
from tools.log_utils import log_task, get_logger
import hashlib
from datetime import datetime

logger = get_logger('settings')

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')
socketio = SocketIO()


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
    if not name:
        return jsonify(ok=False, error="Nome obbligatorio"), 400

    parent_id = data.get("parent_id")
    parent_id = int(parent_id) if parent_id is not None else None
    if parent_id is not None and not Menu.query.get(parent_id):
        return jsonify(ok=False, error="Menu padre non trovato"), 404

    weight = int(data.get("weight") or 0)
    route = data.get("route") or None
    is_active = bool(data.get("is_active", True))

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
        is_active=is_active
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
    if not m.name:
        return jsonify(ok=False, error="Nome obbligatorio"), 400

    m.route = data.get("route") or None
    m.weight = int(data.get("weight") or 0)
    m.is_active = bool(data.get("is_active", True))

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
    db.session.commit()
    return jsonify(ok=True, id=m.id, is_active=bool(m.is_active))
