import json
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from forms.forms import InventarioForm
from extensions import db
from models import Inventario, InventarioRiga, Articoli, Barcode, User, InventarioRigaVersione
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
                utente_id=current_user.id,
                timestamp=datetime.now(),
                has_versions = False  # Inizialmente non ha versioni
            )

            db.session.add(riga)
            db.session.flush()  # così riga.id è già disponibile senza commit

            rigaversioni = InventarioRigaVersione(
                riga_id=riga.id,  # FK
                quantita_inserita=form.quantita_inserita.data,
                num_pedane=form.num_pedane.data,
                num_cartoni=form.num_cartoni.data,
                num_pezzi_sciolti=form.num_pezzi_sciolti.data,
                utente_id=current_user.id,
                timestamp=datetime.now(),
                ppc=nuovo_ppc,
                cpp=nuovo_cpp
            )

            db.session.add(rigaversioni)
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
        hv = ""
        if r.has_versions:
            hv = "*"
        risultato.append({
            "id": r.id,
            "cod_art": r.articolo_id,
            "descrizione": r.descrizione_articolo,
            "quantita": r.quantita_inserita,
            "utente_id": r.utente_id,
            "barcode": r.barcode_articolo,
            "has_versions": hv
        })

    return jsonify({"success": True, "righe": risultato})


@inventario_bp.route("/versioni/<riga_id>")
@login_required
def versioni_riga(riga_id):
    righe = InventarioRigaVersione.query.filter_by(riga_id=riga_id).all()
    logger.debug(f"Righe versioni trovate: {righe}")
    movimento_orig = InventarioRiga.query.filter_by(id=riga_id).first()
    risultato = []
    for r in righe:
        logger.debug(f"Riga versione: {r}")
        risultato.append({
            "articolo": movimento_orig.descrizione_articolo,
            "riga_id": riga_id,
            "utente_id": r.utente_id,
            "quantita_inserita": r.quantita_inserita,
            "timestamp": r.timestamp,
            "num_pedane": r.num_pedane,
            "num_cartoni": r.num_cartoni,
            "num_pezzi_sciolti": r.num_pezzi_sciolti,
            "ppc": r.ppc,
            "cpp": r.cpp
        })

    return jsonify({"success": True, "righe": risultato})


@inventario_bp.route("/username_by_id/<int:user_id>")
@login_required
def username_by_id(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"success": False, "error": "Utente non trovato"}), 404

    username = f"{user.name} {user.surname}"
    return jsonify({"success": True, "username": username})


@inventario_bp.route("/articolo_by_idMov/<int:id_mov>")
@login_required
def articolo_by_idMov(id_mov):
    mov = InventarioRiga.query.filter_by(id=id_mov).first()
    if not mov:
        return jsonify({"success": False, "error": "Movimento non trovato"}), 404
    cod_art = mov.articolo_id
    dati_articolo = Articoli.query.filter_by(cod_art=cod_art).first()
    if not dati_articolo:
        articolo=""
    else:
        articolo = f"{dati_articolo.descrizione} - {dati_articolo.descrizione_aggiuntiva}"
    return jsonify({"success": True, "descrizione": articolo})


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
    utente = User.query.filter_by(id=user_id).first()
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


@inventario_bp.route('/elimina_movimento/<int:inventario_id>/<string:id_mov>', methods=['DELETE'])
def elimina_movimento(inventario_id, id_mov):
    logger.info(f"Chiamata a route elimina movimento {id_mov} su inventario {inventario_id}")
    try:
        num = InventarioRiga.query.filter_by(inventario_id=inventario_id, id=id_mov).delete()
        db.session.commit()
        logger.info("Cancellazione effettuata con successo!")
        return jsonify({"success": True, "deleted": num})
    except Exception as e:
        logger.warning(f"Errore: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})


@inventario_bp.route('/dati_movimento/<int:inventario_id>/<string:id_mov>', methods=['GET'])
def dati_movimento(inventario_id, id_mov):
    logger.info(f"Chiamata a route dati movimento {id_mov} su inventario {inventario_id}")
    try:
        riga = InventarioRiga.query.filter_by(inventario_id=inventario_id, id=id_mov).first()
        if not riga:
            return jsonify({"success": False, "error": "Movimento non trovato"}), 404

        dati = {
            "id": riga.id,
            "cod_art": riga.articolo_id,
            "descrizione": riga.descrizione_articolo,
            "barcode": riga.barcode_articolo,
            "quantita_inserita": riga.quantita_inserita,
            "num_pedane": riga.num_pedane,
            "num_cartoni": riga.num_cartoni,
            "num_pezzi_sciolti": riga.num_pezzi_sciolti,
            "ppc": riga.ppc,
            "cpp": riga.cpp,
            "utente_id": riga.utente_id,
            "has_versions": riga.has_versions,
            "timestamp": riga.timestamp.strftime("%d/%m/%Y %H:%M") if riga.timestamp else ""
        }

        return jsonify({"success": True, "dati_movimento": dati})
    except Exception as e:
        logger.warning(f"Errore: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


def normalize(v):
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        try:
            return float(v)
        except (ValueError, TypeError):
            return str(v).strip()


@inventario_bp.route('/modifica_dati_movimento/<int:inventario_id>/<string:id_mov>', methods=['POST'])
def modifica_dati_movimento(inventario_id, id_mov):
    logger.info(f"Chiamata a route modifica dati movimento {id_mov} su inventario {inventario_id}")

    campi_da_controllare = [
        "quantita_inserita",
        "num_pedane",
        "num_cartoni",
        "num_pezzi_sciolti",
        "ppc",
        "cpp"
    ]

    try:
        riga = InventarioRiga.query.filter_by(inventario_id=inventario_id, id=id_mov).first()
        if not riga:
            return jsonify({"success": False, "error": "Movimento non trovato"}), 404

        nuovi_dati = request.get_json()
        da_salvare = False
        for c in campi_da_controllare:
            old_val = normalize(getattr(riga, c))
            new_val = normalize(nuovi_dati[c])
            if old_val != new_val:
                logger.debug(f"{c}: {old_val} e {new_val} non sono uguali")
                da_salvare = True
        logger.debug(f"Da salvare: {da_salvare}")
        if da_salvare:
            # salva nuova versione
            riga.quantita_inserita = nuovi_dati["quantita_inserita"]
            riga.num_pedane = nuovi_dati["num_pedane"]
            riga.num_cartoni = nuovi_dati["num_cartoni"]
            riga.num_pezzi_sciolti = nuovi_dati["num_pezzi_sciolti"]
            riga.ppc = nuovi_dati["ppc"]
            riga.cpp = nuovi_dati["cpp"]
            riga.utente_id = current_user.id
            riga.timestamp = datetime.now()
            riga.has_versions = True  # Indica che ci sono versioni di questa riga

            versione = InventarioRigaVersione(
                riga_id=riga.id,
                utente_id=current_user.id,
                quantita_inserita=nuovi_dati["quantita_inserita"],
                num_pedane=nuovi_dati["num_pedane"],
                num_cartoni=nuovi_dati["num_cartoni"],
                num_pezzi_sciolti=nuovi_dati["num_pezzi_sciolti"],
                ppc=nuovi_dati["ppc"],
                cpp=nuovi_dati["cpp"]
            )

            db.session.add(versione)
            db.session.commit()

            return jsonify({"success": True, "message": "Movimento aggiornato con successo"})
            # return jsonify({"success": True, "dati_movimento": nuovi_dati})
        else:
            return jsonify({"success": True, "message": "Nessuna modifica necessaria"}), 200
    except Exception as e:
        logger.warning(f"Errore: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
