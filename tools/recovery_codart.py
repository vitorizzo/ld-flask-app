from sqlalchemy import func

from extensions import db
from models import Articoli, Barcode, InventarioRiga


def aggiorna_articolo_id_certi():
    """
    Aggiorna inventario_righe.articolo_id solo nei casi certi:
    - descrizione unica in articoli
    - oppure barcode unico in barcode
    - oppure entrambi univoci e concordi
    """
    righe = InventarioRiga.query.all()
    aggiornati = 0

    for riga in righe:
        descr = (riga.descrizione_articolo or '').strip().lower()
        bar = (riga.barcode_articolo or '').strip()

        cod_descr = None
        cod_bar = None

        # --- Ricerca per descrizione
        if descr:
            articoli_match = Articoli.query.filter(
                func.lower(func.trim(Articoli.descrizione)) == descr
            ).all()
            if len(articoli_match) == 1:
                cod_descr = articoli_match[0].cod_art

        # --- Ricerca per barcode
        if bar:
            barcode_match = Barcode.query.filter(Barcode.cod_bar == bar).all()
            codici_bar = list({b.cod_art for b in barcode_match})
            if len(codici_bar) == 1:
                cod_bar = codici_bar[0]

        # --- Decisione
        nuovo_cod = None
        if cod_descr and not cod_bar:
            nuovo_cod = cod_descr
        elif cod_bar and not cod_descr:
            nuovo_cod = cod_bar
        elif cod_descr and cod_bar and cod_descr == cod_bar:
            nuovo_cod = cod_descr

        # --- Aggiorno solo se certo
        if nuovo_cod:
            riga.articolo_id = nuovo_cod
            aggiornati += 1

    db.session.commit()
    print(f"Aggiornate {aggiornati} righe certe.")
