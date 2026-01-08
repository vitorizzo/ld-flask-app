from flask import request, flash, render_template, Blueprint, jsonify
from flask_login import login_required
from flask_socketio import SocketIO
from extensions import db
from models import Menu, Role, ImportConflict, Articoli
from tools.role_required import role_required
from config.tasks import import_articoli_task, import_barcode_task, import_giacenze_task, import_ps_task
from tools.ps_util import get_product_by_code
from tools.log_utils import log_task, get_logger

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
        new_menu = Menu(name=name, route=route, parent_id=parent_id, weight=weight)
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


@settings_bp.route("/resolve_conflict", methods=["POST"])
@login_required
def api_import_conflicts_resolve():
    logger.info("Risoluzione conflitto di importazione richiesta.")
    data = request.get_json(silent=True) or {}
    conflict_id = data.get("id")
    action = data.get("action")  # es: KEEP_CSV
    logger.debug(f"Risoluzione conflitto ID: {conflict_id} con azione: {action}")

    if not conflict_id or not action:
        return jsonify(ok=False, error="Missing 'id' or 'action'"), 400

    c = ImportConflict.query.get(conflict_id)
    if not c:
        return jsonify(ok=False, error="Conflict not found"), 404

    payload = c.payload or {}
    cod_art = payload.get("cod_art")
    csv_data = (payload.get("csv") or {})
    db_data = (payload.get("db") or {})
    logger.debug(f"Conflitto payload: cod_art={cod_art}, csv_data={csv_data}, db_data={db_data}")

    if not cod_art:
        return jsonify(ok=False, error="payload.cod_art missing"), 400

    if action == "KEEP_CSV":
        art = Articoli.query.filter_by(cod_art=cod_art).first()
        if not art:
            return jsonify(ok=False, error=f"Articolo not found for cod_art={cod_art}"), 404

        # Applica CSV -> DB (adatta i nomi campi se diverso)
        if "descrizione" in csv_data:
            art.descrizione = csv_data.get("descrizione")
        if "descrizione_aggiuntiva" in csv_data:
            art.descrizione_aggiuntiva = csv_data.get("descrizione_aggiuntiva")
        if "prezzo" in csv_data:
            art.prezzo = csv_data.get("prezzo")

        db.session.delete(c)
        db.session.commit()
        return jsonify(ok=True, resolved_id=conflict_id, action=action, cod_art=cod_art)

    return jsonify(ok=False, error=f"Unsupported action: {action}"), 400
