import csv

from routes.esportazioni_teamsystem import serve_risorsa
from tools.ps_util import get_all_products, get_product_images
from extensions import db
from models import Articoli, Barcode, Giacenza
from flask import jsonify
from tools.log_utils import log_task, get_logger

logger = get_logger('importazioni')


def clean_text(text):
    if text:
        return text.encode('ascii', 'ignore').decode('ascii')
    return text


@log_task(logger)
def import_ps():
    logger.info(">>> Entrata nella funzione: import_ps()")
    logger.info("Importazione Prestashop avviata...")

    for prodotto in get_all_products():
        cod_art = prodotto['cod_art']
        pid = prodotto['id']
        existing_articolo = Articoli.query.filter_by(cod_art=cod_art).first()
        if not existing_articolo:
            nuovo_articolo = Articoli(
                cod_art=cod_art,
                descrizione=prodotto['name'],
                prezzo=float(prodotto['price'])
            )
            db.session.add(nuovo_articolo)
            db.session.commit()
            logger.info(f"Articolo {cod_art} inserito.")
        else:
            logger.info(f"Articolo {cod_art} già presente, salto inserimento.")

        p_images = get_product_images(pid, cod_art)
        prodotto['images'] = p_images
        logger.info(f"Prodotto {cod_art} importato: {prodotto['name']} con {len(p_images)} immagini.")


@log_task(logger)
def import_articoli():
    logger.info(">>> Entrata nella funzione: import_articoli()")
    logger.info("Importazione articoli avviata...")
    db.create_all()
    db.session.query(Articoli).delete()
    db.session.commit()
    logger.info("Tabella articoli svuotata.")

    file_csv = serve_risorsa("ARTICOLI.CSV")
    logger.info(f"File CSV: {file_csv}")
    try:
        with open(file_csv, 'r', encoding='utf-8', errors='ignore') as csvfile:
            reader = list(csv.reader(csvfile, delimiter='\t'))
            total_rows = len(reader)
            logger.info(f"Righe totali: {total_rows}")

            with db.session.no_autoflush:
                for index, row in enumerate(reader):
                    if index > 0 and len(row) >= 5:
                        cod_art = clean_text(row[0])
                        descrizione = clean_text(row[1])
                        descrizione_aggiuntiva = clean_text(row[2])
                        prezzo = float(row[3][:-2] + "." + row[3][-2:]) if row[3].strip() else 0.0

                        if cod_art and descrizione:
                            articolo_esistente = Articoli.query.filter_by(cod_art=cod_art).first()
                            if articolo_esistente:
                                modifiche = []
                                if articolo_esistente.descrizione != descrizione:
                                    modifiche.append(("descrizione", articolo_esistente.descrizione, descrizione))
                                if articolo_esistente.descrizione_aggiuntiva != descrizione_aggiuntiva:
                                    modifiche.append(("descrizione_aggiuntiva",
                                                      articolo_esistente.descrizione_aggiuntiva,
                                                      descrizione_aggiuntiva))
                                if float(articolo_esistente.prezzo) != prezzo:
                                    modifiche.append(("prezzo", articolo_esistente.prezzo, prezzo))
                                if modifiche:
                                    for campo, valore_vecchio, valore_nuovo in modifiche:
                                        scelta = input(f"Differenza trovata per {campo}: vecchio='{valore_vecchio}'"
                                                       f" nuovo='{valore_nuovo}'. Quale valore vuoi mantenere? "
                                                       f"(v=vecchio, n=nuovo): ").strip().lower()
                                        if scelta == 'n':
                                            setattr(articolo_esistente, campo, valore_nuovo)
                            else:
                                nuovo_articolo = Articoli(
                                    cod_art=cod_art,
                                    descrizione=descrizione,
                                    descrizione_aggiuntiva=descrizione_aggiuntiva,
                                    prezzo=prezzo
                                )
                                db.session.add(nuovo_articolo)
                                db.session.flush()
        db.session.commit()
        logger.info("Articoli importati con successo!")
        return jsonify({'message': 'Articoli importati con successo!', 'progress': 100}), 200
    except Exception as e:
        logger.exception("Errore durante l'importazione degli Articoli:")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@log_task(logger)
def import_giacenze():
    logger.info(">>> Entrata nella funzione: import_giacenze()")
    logger.info("Importazione giacenze avviata...")
    db.create_all()
    db.session.query(Giacenza).delete()
    db.session.commit()
    logger.info("Tabella giacenze svuotata.")

    file_csv = serve_risorsa("GIACENZE.CSV")
    logger.info(f"File CSV: {file_csv}")
    try:
        with open(file_csv, 'r', encoding='utf-8', errors='ignore') as csvfile:
            reader = list(csv.reader(csvfile, delimiter='\t'))
            total_rows = len(reader)
            logger.info(f"Righe totali: {total_rows}")

            with db.session.no_autoflush:
                for index, row in enumerate(reader):
                    if index > 0 and len(row) >= 4:
                        cod_art = clean_text(row[0])
                        giacenza = int(clean_text(row[1])[:-2])
                        deposito = int(clean_text(row[2])[:-2])
                        tipo_valore = int(clean_text(row[3])[:-2])

                        if cod_art and tipo_valore == 1 and giacenza != 0:
                            giacenza_esistente = Giacenza.query.filter_by(cod_art=cod_art).first()
                            if giacenza_esistente:
                                modifiche = []
                                match deposito:
                                    case 0:
                                        if giacenza_esistente.giac_neg == 0:
                                            setattr(giacenza_esistente, "giac_neg", giacenza)
                                        else:
                                            modifiche.append((cod_art, "giac_neg", giacenza_esistente.giac_neg, giacenza))
                                    case 400:
                                        if giacenza_esistente.giac_www == 0:
                                            setattr(giacenza_esistente, "giac_www", giacenza)
                                        else:
                                            modifiche.append((cod_art, "giac_www", giacenza_esistente.giac_www, giacenza))
                                if modifiche:
                                    for articolo, campo, valore_vecchio, valore_nuovo in modifiche:
                                        scelta = input(f"Differenza trovata per il campo {campo} dell'articolo "
                                                       f"{articolo}: vecchio='{valore_vecchio}', "
                                                       f" nuovo='{valore_nuovo}'. (v=vecchio, n=nuovo): ").strip().lower()
                                        if scelta == 'n':
                                            setattr(giacenza_esistente, campo, valore_nuovo)
                            else:
                                giac_neg = 0
                                giac_www = 0
                                match deposito:
                                    case 0: giac_neg = giacenza
                                    case 400: giac_www = giacenza

                                nuova_giacenza = Giacenza(
                                    cod_art=cod_art,
                                    giac_neg=giac_neg,
                                    giac_www=giac_www,
                                )
                                db.session.add(nuova_giacenza)
                                db.session.flush()
        logger.info("Ciclo di filtraggio terminato!")
        db.session.commit()
        logger.info("Giacenze importate con successo!")
        return jsonify({'message': 'Giacenze importate con successo!', 'progress': 100}), 200
    except Exception as e:
        logger.exception("Errore durante l'importazione delle Giacenze:")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@log_task(logger)
def import_barcode():
    logger.info(">>> Entrata nella funzione: import_barcode()")
    logger.info("Importazione codici a barre avviata...")
    db.create_all()
    db.session.query(Barcode).delete()
    db.session.commit()
    logger.info("Tabella codici a barre svuotata.")

    file_csv = serve_risorsa("BARSEQ.CSV")
    logger.info(f"File CSV: {file_csv}")
    try:
        with open(file_csv, 'r', encoding='utf-8', errors='ignore') as csvfile:
            reader = list(csv.reader(csvfile, delimiter='\t'))
            total_rows = len(reader)
            logger.info(f"Righe totali: {total_rows}")

            with db.session.no_autoflush:
                for index, row in enumerate(reader):
                    if index > 0 and len(row) >= 5:
                        cod_bar = clean_text(row[3])
                        cod_art = clean_text(row[0])
                        cod_bar = cod_bar.strip()
                        logger.debug(f"DEBUG: contenuto senza spazi di cod_bar: {cod_bar}")
                        logger.debug(f"DEBUG: contenuto senza spazi di cod_art: {cod_art}")
                        if cod_bar and cod_art:
                            logger.debug(f"DEBUG: contenuto di cod_bar: {cod_bar}")
                            nuovo_barcode = Barcode(
                                cod_bar=cod_bar,
                                cod_art=cod_art
                            )
                            db.session.add(nuovo_barcode)
                            db.session.flush()
        db.session.commit()
        logger.info("Codici a Barre importati con successo!")
        return jsonify({'message': 'Codici a Barre importati con successo!', 'progress': 100}), 200
    except Exception as e:
        logger.exception("Errore durante l'importazione dei codici a barre:")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
