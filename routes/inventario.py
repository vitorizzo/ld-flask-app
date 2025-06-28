import json
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from forms.forms import InventarioForm
from extensions import db
from models import Inventario, InventarioRiga, Articoli, Barcode, User
from datetime import date, datetime

from tools.log_utils import get_logger

logger = get_logger("inventario", level=logging.DEBUG)

inventario_bp = Blueprint('inventario', __name__)


@inventario_bp.route("/nuovo", methods=["POST"])
@login_required
def nuovo_inventario():
    oggi = date.today()
    esistente = Inventario.query.filter_by(data_inventario=oggi).first()

    if esistente:
        return jsonify({
            "success": True,
            "id": esistente.id,
            "data": esistente.data_inventario.strftime("%d-%m-%Y"),
            "gia_esiste": True
        })

    nuovo = Inventario(data_inventario=oggi)
    db.session.add(nuovo)
    db.session.commit()

    return jsonify({
        "success": True,
        "id": nuovo.id,
        "data": nuovo.data_inventario.strftime("%d-%m-%Y"),
        "gia_esiste": False
    })


@inventario_bp.route('/inventario', methods=['GET', 'POST'])
@login_required
def inventario():
    logger.info(f"📥 Route /inventario chiamata: {request.method}")
    today = date.today().isoformat()  # 👈 restituisce 'YYYY-MM-DD'
    form = InventarioForm()
    selected_inventario_id = request.args.get("inv_id", type=int)

    if request.method == "POST":
        logger.info(f"🔧 Richiesta POST ricevuta")
        logger.info(f"📦 Dati ricevuti: {request.form}")

        if form.validate():
            logger.info("✅ Form valido!")
            data_inv = form.data_inventario.data or date.today()

            inventario = Inventario.query.filter_by(data_inventario=data_inv).first()
            if not inventario:
                inventario = Inventario(data_inventario=data_inv)
                db.session.add(inventario)
                db.session.commit()

            cod_art = form.cod_art.data
            articolo = Articoli.query.get(cod_art) if cod_art else None

            if not articolo and form.barcode_articolo.data:
                barcode = Barcode.query.filter_by(cod_bar=form.barcode_articolo.data).first()
                if barcode:
                    articolo = Articoli.query.get(barcode.cod_art)

            # Aggiorna PPC e CPP
            try:
                nuovo_ppc = int(form.hidden_ppc.data or 1)
                nuovo_cpp = int(form.hidden_cpp.data or 1)
                if articolo:
                    if articolo.pezzi_per_collo != nuovo_ppc:
                        articolo.pezzi_per_collo = nuovo_ppc
                    if articolo.colli_per_pedana != nuovo_cpp:
                        articolo.colli_per_pedana = nuovo_cpp
                    db.session.commit()
            except:
                pass  # valori non validi o mancanti

            # Salva riga inventario
            riga = InventarioRiga(
                inventario_id=inventario.id,
                articolo_id=cod_art if articolo else None,
                descrizione_articolo=articolo.descrizione if articolo else form.descrizione_articolo.data,
                barcode_articolo=form.barcode_articolo.data,
                quantita_inserita=form.quantita_inserita.data,
                num_pedane=form.num_pedane.data,
                num_cartoni=form.num_cartoni.data,
                num_pezzi_sciolti=form.num_pezzi_sciolti.data,
                cpp=nuovo_cpp,
                ppc=nuovo_ppc,
                utente_id=current_user.id
            )

            db.session.add(riga)
            db.session.commit()

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"success": True})
            else:
                flash("Conteggio inventario inserito con successo!", "success")
                return redirect(url_for('inventario.inventario', inv_id=inventario.id))
        else:
            logger.warning("❌ Form NON valido")
            logger.warning(form.errors)
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"success": False, "error": "Dati non validi", "form_errors": form.errors}), 400
            else:
                flash("Errore nei dati inseriti", "danger")
    inventari = Inventario.query.order_by(Inventario.data_inventario.desc()).all()
    return render_template('inventario.html', form=form, inventari=inventari,
                           selected_inventario_id=selected_inventario_id, today=today)


@inventario_bp.route("/crea", methods=["POST"])
@login_required
def crea_inventario_con_data():
    data = request.json.get("data_inventario")
    try:
        data_obj = datetime.strptime(data, "%Y-%m-%d").date()
    except Exception:
        return jsonify(success=False, error="Data non valida"), 400

    esistente = Inventario.query.filter_by(data_inventario=data_obj).first()
    if esistente:
        return jsonify({
            "success": True,
            "id": esistente.id,
            "data": esistente.data_inventario.strftime("%d-%m-%Y"),
            "gia_esiste": True
        })

    nuovo = Inventario(data_inventario=data_obj)
    db.session.add(nuovo)
    db.session.commit()

    return jsonify({
        "success": True,
        "id": nuovo.id,
        "data": nuovo.data_inventario.strftime("%d-%m-%Y"),
        "gia_esiste": False
    })


@inventario_bp.route('/ultimi_inseriti/<int:inventario_id>')
@login_required
def ultimi_inseriti(inventario_id):
    righe = (
        InventarioRiga.query
        .filter_by(inventario_id=inventario_id, utente_id=current_user.id)
        # o .data_inserimento.desc() se hai un timestamp
        .limit(10)
        .all()
    )

    risultati = []
    for r in righe:
        risultati.append({
            "cod_art": r.articolo_id,
            "descrizione": r.descrizione_articolo,
            "quantita": r.quantita_inserita
        })

    return jsonify({"success": True, "righe": risultati})


@inventario_bp.route('/righe/<int:inventario_id>')
@login_required
def righe_inventario(inventario_id):
    righe = (
        InventarioRiga.query
        .filter_by(inventario_id=inventario_id)
        .order_by(InventarioRiga.id.desc())
        .all()
    )

    risultato = []
    for r in righe:
        risultato.append({
            "id": r.id,
            "cod_art": r.articolo_id,
            "descrizione": r.descrizione_articolo,
            "quantita": r.quantita_inserita,
            "utente_id": r.utente_id,
            "barcode": r.barcode_articolo
        })

    return jsonify({"success": True, "righe": risultato})


@inventario_bp.route("/lista_inventari")
@login_required
def lista_inventari():
    inventari = (
        db.session.query(
            Inventario.id,
            Inventario.data_inventario,
            db.func.count(InventarioRiga.id).label("num_righe")
        )
        .outerjoin(InventarioRiga, Inventario.id == InventarioRiga.inventario_id)
        .group_by(Inventario.id)
        .order_by(Inventario.data_inventario.desc())
        .all()
    )

    lista = []
    for inv in inventari:
        lista.append({
            "id": inv.id,
            "data": inv.data_inventario.strftime("%d-%m-%Y"),
            "num_righe": inv.num_righe
        })

    return jsonify(success=True, inventari=lista)


@inventario_bp.route("/inventario_aggregato/<int:inventario_id>")
@login_required
def inventario_aggregato(inventario_id):
    from sqlalchemy import func

    righe = (
        db.session.query(
            InventarioRiga.articolo_id,
            func.sum(InventarioRiga.quantita_inserita).label("quantita_totale")
        )
        .filter(InventarioRiga.inventario_id == inventario_id)
        .group_by(InventarioRiga.articolo_id)
        .all()
    )

    risultati = []
    for cod_art, quantita in righe:
        articolo = Articoli.query.get(cod_art)
        risultati.append({
            "cod_art": cod_art,
            "descrizione": articolo.descrizione if articolo else "",
            "quantita": quantita
        })

    return jsonify({"success": True, "inventario": risultati})


@inventario_bp.route('/modifica_data/<int:id>', methods=['POST'])
def modifica_data_inventario(id):
    data = request.get_json()
    nuova_data = data.get('nuova_data')
    inventario = Inventario.query.get(id)
    if inventario:
        inventario.data_inventario = nuova_data
        db.session.commit()
        return jsonify(success=True)
    return jsonify(success=False), 404


@inventario_bp.route('/elimina/<int:id>', methods=['DELETE'])
def elimina_inventario(id):
    inventario = Inventario.query.get(id)
    if inventario:
        db.session.delete(inventario)
        db.session.commit()
        return jsonify(success=True)
    return jsonify(success=False), 404


@inventario_bp.route('/movimenti_articolo/<int:inventario_id>/<string:cod_art>')
def movimenti_articolo(inventario_id, cod_art):
    logger.info(f"Chiamata a route movimenti articolo {cod_art} su inventario {inventario_id}")
    try:
        righe = InventarioRiga.query.filter_by(inventario_id=inventario_id, articolo_id=cod_art).all()
        logger.debug(f"Contenuto query: \n{righe}")
        movimenti = [{
            "quantita": r.quantita_inserita,
            "descrizione": r.descrizione_articolo,
            "utente": get_nome_utente(r.utente_id),
            "data": r.timestamp.strftime("%d/%m/%Y %H:%M") if r.timestamp else ""
        } for r in righe]
        logger.debug("Contenuto movimenti:\n" + json.dumps(movimenti, indent=2, ensure_ascii=False))

        return jsonify({"success": True, "movimenti": movimenti})
    except Exception as e:
        logger.warning(f"Errore: {str(e)}")
        return jsonify({"success": False, "error": str(e)})


def get_nome_utente(user_id):
    utente = User.query.filter_by(id=user_id).all()
    logger.debug(f"Utente caricato: {utente}")
    username = utente.name + " " + utente.surname
    return username


@inventario_bp.route('/elimina_movimenti/<int:inventario_id>/<string:cod_art>', methods=['DELETE'])
def elimina_movimenti_articolo(inventario_id, cod_art):
    logger.info(f"Chiamata a route elimina movimenti articolo {cod_art} su inventario {inventario_id}")
    try:
        num = InventarioRiga.query.filter_by(inventario_id=inventario_id, articolo_id=cod_art).delete()
        db.session.commit()
        logger.info("Cancellazione effettuata con successo!")
        return jsonify({"success": True, "deleted": num})
    except Exception as e:
        logger.warning(f"Errore: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})
