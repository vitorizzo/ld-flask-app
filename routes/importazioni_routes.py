from flask import Blueprint, render_template, flash, redirect, request

from extensions import db
from models import Importazione, ModuloImportazione

importazioni_bp = Blueprint("importazioni_bp", __name__, url_prefix="/importazioni")


@importazioni_bp.route("/inizializza_db_moduli", methods=["GET", "POST"])
def inizializza_db_moduli():
    moduli = [
        {"nome": "articoli", "descrizione": "Archivio articoli"},
        {"nome": "giacenze", "descrizione": "Archivio giacenze"},
        {"nome": "barcode", "descrizione": "Codici a barre"},
        {"nome": "prestashop", "descrizione": "Dati da Prestashop"},
        {"nome": "poleepo_prodotti", "descrizione": "Prodotti da Poleepo"},
        {"nome": "anagrafiche", "descrizione": "Anagrafiche clienti e fornitori"},
        {
            "nome": "estratti_conto_clienti",
            "descrizione": "Estratti conto clienti TeamSystem"
        }
    ]

    aggiunti = 0
    for m in moduli:
        if not ModuloImportazione.query.filter_by(nome=m["nome"]).first():
            db.session.add(ModuloImportazione(**m))
            aggiunti += 1

    db.session.commit()
    flash(f"Inizializzazione completata: {aggiunti} nuovi moduli aggiunti.", "success")
    return redirect(request.referrer or "/")


@importazioni_bp.route("/storico")
def storico_importazioni():
    from sqlalchemy import and_
    from datetime import datetime, timedelta

    # Recupera tutti i moduli per il filtro
    moduli = ModuloImportazione.query.order_by(ModuloImportazione.nome).all()

    # Recupera i parametri dal form
    filtro_modulo = request.args.get("modulo")
    filtro_esito = request.args.get("esito")
    filtro_ultimi = request.args.get("ultimi")
    filtro_da_data = request.args.get("da_data")
    filtro_a_data = request.args.get("a_data")

    # Base query
    query = Importazione.query

    # Filtro modulo
    if filtro_modulo:
        query = query.filter(Importazione.modulo == filtro_modulo)

    # Filtro esito
    if filtro_esito == "successo":
        query = query.filter(Importazione.esito == True)
    elif filtro_esito == "errore":
        query = query.filter(Importazione.esito == False)

    # Filtro per range di date
    if filtro_da_data:
        da_data = datetime.strptime(filtro_da_data, "%Y-%m-%d")
        query = query.filter(Importazione.timestamp >= da_data)

    if filtro_a_data:
        a_data = datetime.strptime(filtro_a_data, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(Importazione.timestamp < a_data)

    # Ordina per data decrescente
    query = query.order_by(Importazione.timestamp.desc())

    # Filtro ultimi N
    if filtro_ultimi and filtro_ultimi.isdigit():
        query = query.limit(int(filtro_ultimi))

    storico = query.all()

    return render_template(
        "storico_importazioni.html",
        storico=storico,
        moduli=moduli,
        modulo_corrente=filtro_modulo
    )
