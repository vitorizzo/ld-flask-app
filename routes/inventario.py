from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from forms.forms import InventarioForm
from extensions import db
from models import Inventario, InventarioRiga, Articoli, Barcode
from datetime import date

inventario_bp = Blueprint('inventario', __name__)


@inventario_bp.route("/nuovo", methods=["POST"])
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
    form = InventarioForm()
    selected_inventario_id = request.args.get("inv_id", type=int)

    if form.validate_on_submit():
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

        flash("Conteggio inventario inserito con successo!", "success")
        return redirect(url_for('inventario.inventario', inv_id=inventario.id))

    inventari = Inventario.query.order_by(Inventario.data_inventario.desc()).all()
    return render_template('inventario.html', form=form, inventari=inventari,
                           selected_inventario_id=selected_inventario_id)
