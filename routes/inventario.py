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

    if form.validate_on_submit():
        data_inv = form.data_inventario.data

        # Controlla se esiste già un inventario per quella data
        inventario = Inventario.query.filter_by(data_inventario=data_inv).first()
        if not inventario:
            inventario = Inventario(data_inventario=data_inv)
            db.session.add(inventario)
            db.session.commit()

        # Cerca articolo per barcode o descrizione
        articolo = None
        if form.barcode_articolo.data:
            barcode = Barcode.query.filter_by(cod_bar=form.barcode_articolo.data).first()
            if barcode:
                articolo = Articoli.query.get(barcode.cod_art)

        if not articolo and form.descrizione_articolo.data:
            articolo = Articoli.query.filter(
                Articoli.descrizione.ilike(f"%{form.descrizione_articolo.data}%")
            ).first()

        # Qui sotto inserisci il controllo e salvataggio dei valori aggiornati
        if 'hidden_ppc' in request.form and articolo:
            nuovo_ppc = int(request.form['hidden_ppc'])
            if nuovo_ppc != articolo.pezzi_per_collo:
                articolo.pezzi_per_collo = nuovo_ppc
                db.session.commit()

        if 'hidden_cpp' in request.form and articolo:
            nuovo_cpp = int(request.form['hidden_cpp'])
            if nuovo_cpp != articolo.colli_per_pedana:
                articolo.colli_per_pedana = nuovo_cpp
                db.session.commit()

        # Inserimento riga inventario
        riga_inventario = InventarioRiga(
            inventario_id=inventario.id,
            articolo_id=articolo.cod_art if articolo else None,
            descrizione_articolo=form.descrizione_articolo.data if not articolo else articolo.descrizione,
            barcode_articolo=form.barcode_articolo.data,
            quantita_inserita=form.quantita_inserita.data,
            utente_id=current_user.id
        )
        # Se l’utente preme “calcola”
        if form.calcola.data and request.method == 'POST':
            try:
                pedane = form.num_pedane.data or 0
                cartoni = form.num_cartoni.data or 0
                pezzi_sciolti = form.num_pezzi_sciolti.data or 0

                articolo = Articoli.query.filter_by(cod_art=form.barcode_articolo.data).first()

                if not articolo:
                    flash("Articolo non trovato per il calcolo automatico.", "danger")
                else:
                    ppc = articolo.pezzi_per_collo if articolo.pezzi_per_collo and articolo.pezzi_per_collo > 0 else 1
                    cpp = articolo.colli_per_pedana if articolo.colli_per_pedana and articolo.colli_per_pedana > 0 else 1

                    totale = pezzi_sciolti + (pedane * cpp + cartoni) * ppc
                    form.quantita_inserita.data = totale
                    flash(f"Quantità calcolata: {totale}", "success")

            except Exception as e:
                flash("Errore nel calcolo quantità.", "danger")

        db.session.add(riga_inventario)
        db.session.commit()

        flash('Conteggio inventario inserito con successo!', 'success')
        return redirect(url_for('inventario.inventario'))

    inventari = Inventario.query.order_by(Inventario.data_inventario.desc()).all()
    return render_template('inventario.html', form=form, inventari=inventari)
