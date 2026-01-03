import csv
from datetime import datetime

from tools.ps_util import get_all_products, get_product_images
from extensions import db
from models import Articoli, Barcode, Giacenza, Importazione
from flask import jsonify
from tools.log_utils import log_task, get_logger

logger = get_logger('importazioni')


def clean_text(text):
    if text:
        return text.encode('ascii', 'ignore').decode('ascii')
    return text


@log_task(logger)
def import_ps(task_id=None):
    from tools.redis_utils import update_task, status_string

    task_name = "Importazione dati da Prestashop"
    update_task(task_id, task_name, 0, status_string['start'])
    logger.info(">>> Entrata nella funzione: import_ps()")
    logger.info("Importazione Prestashop avviata...")

    try:
        products = get_all_products()
        total_rows = len(products)

        for index, prodotto in enumerate(products):
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

            if index % 50 == 0:
                progresso = int((index / total_rows) * 100)
                update_task(task_id, task_name, progresso, status_string['update'])

            logger.info(f"Prodotto {cod_art} importato: {prodotto['name']} con {len(p_images)} immagini.")

        update_task(task_id, task_name, 100, status_string['end'])
        registra_importazione("prestashop", esito=True)

    except Exception as e:
        logger.exception("Errore durante l'importazione Prestashop")
        update_task(task_id, task_name, 0, status_string['error'], e)
        registra_importazione("prestashop", esito=False, messaggio=str(e))
        raise


@log_task(logger)
def import_articoli(task_id=None):
    from routes.esportazioni_teamsystem import serve_risorsa
    from tools.redis_utils import update_task, status_string, clear_task_status
    task_name = "Importazione articoli"
    update_task(task_id, task_name, 0, status_string['start'])
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

            # Evita divisione per zero
            if total_rows <= 1:
                raise Exception("Il file CSV non contiene dati validi")

            with db.session.no_autoflush:
                for index, row in enumerate(reader):
                    if index == 0:
                        continue  # skip header

                    if len(row) >= 5:
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
                                        scelta = 'n'  # oppure 'v' di default o gestito via policy
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

                    # 🔁 Aggiorna progresso ogni 50 righe
                    if index % 50 == 0:
                        progresso = int((index / total_rows) * 100)
                        update_task(task_id, task_name, progresso, status_string['update'])

        db.session.commit()
        update_task(task_id, task_name, 100, status_string['end'])
        logger.info("Articoli importati con successo!")

        if task_id:
            clear_task_status(task_id)
        registra_importazione("articoli", esito=True)
        return {'message': 'Articoli importati con successo!', 'progress': 100}

    except Exception as e:
        logger.exception("Errore durante l'importazione degli Articoli:")
        db.session.rollback()

        update_task(task_id, task_name, 0, status_string['error'], e)
        registra_importazione("articoli", esito=False, messaggio=str(e))
        return {'success': False, 'error': str(e)}


@log_task(logger)
def import_giacenze(task_id=None):
    from routes.esportazioni_teamsystem import serve_risorsa
    from tools.redis_utils import update_task, clear_task_status, status_string
    task_name = "Importazione giacenze da gestionale"
    update_task(task_id, task_name, 0, status_string['start'])
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
                                            modifiche.append((cod_art, "giac_neg", giacenza_esistente.giac_neg,
                                                              giacenza))
                                    case 400:
                                        if giacenza_esistente.giac_www == 0:
                                            setattr(giacenza_esistente, "giac_www", giacenza)
                                        else:
                                            modifiche.append((cod_art, "giac_www", giacenza_esistente.giac_www,
                                                              giacenza))
                                if modifiche:
                                    for articolo, campo, valore_vecchio, valore_nuovo in modifiche:
                                        scelta = input(f"Differenza trovata per il campo {campo} dell'articolo "
                                                       f"{articolo}: vecchio='{valore_vecchio}', "
                                                       f" nuovo='{valore_nuovo}'. "
                                                       f"(v=vecchio, n=nuovo): ").strip().lower()
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
                    # 🔁 Aggiorna progresso ogni 50 righe
                    if index % 50 == 0:
                        progresso = int((index / total_rows) * 100)
                        update_task(task_id, task_name, progresso, status_string['update'])
        logger.info("Ciclo di filtraggio terminato!")
        db.session.commit()
        update_task(task_id, task_name, 100, status_string['end'])
        logger.info("Giacenze importate con successo!")
        if task_id:
            clear_task_status(task_id)
        registra_importazione("giacenze", esito=True)
        return jsonify({'message': 'Giacenze importate con successo!', 'progress': 100}), 200
    except Exception as e:
        logger.exception("Errore durante l'importazione delle Giacenze:")
        db.session.rollback()
        update_task(task_id, task_name, 0, status_string['error'], e)
        registra_importazione("giacenze", esito=False, messaggio=str(e))
        return jsonify({'success': False, 'error': str(e)}), 500


@log_task(logger)
def import_barcode(task_id=None):
    result = run_import_barcode(task_id)
    status_code = 200 if result.get("success", True) else 500
    return jsonify(result), status_code


def run_import_barcode(task_id=None):
    from routes.esportazioni_teamsystem import serve_risorsa
    from tools.redis_utils import update_task, clear_task_status, status_string
    task_name = "Importazione codici a barre articoli da gestionale"
    update_task(task_id, task_name, 0, status_string['start'])
    logger.info(">>> Entrata nella funzione: run_import_barcode()")
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
                        logger.debug("DEBUG: contenuto senza spazi di cod_bar: %s", cod_bar)
                        logger.debug("DEBUG: contenuto senza spazi di cod_art: %s", cod_art)
                        if cod_bar and cod_art:
                            nuovo_barcode = Barcode(
                                cod_bar=cod_bar,
                                cod_art=cod_art
                            )
                            db.session.add(nuovo_barcode)
                            db.session.flush()
                    # 🔁 Aggiorna progresso ogni 50 righe
                    if index % 50 == 0:
                        progresso = int((index / total_rows) * 100)
                        update_task(task_id, task_name, progresso, status_string['update'])
        db.session.commit()
        logger.info("Codici a Barre importati con successo!")
        update_task(task_id, task_name, 100, status_string['end'])
        if task_id:
            clear_task_status(task_id)
        registra_importazione("barcode", esito=True)
        return {'success': True, 'message': 'Codici a Barre importati con successo!', 'progress': 100}
    except Exception as e:
        logger.exception("Errore durante l'importazione dei codici a barre:")
        db.session.rollback()
        update_task(task_id, task_name, 0, status_string['error'], e)
        registra_importazione("barcode", esito=False, messaggio=str(e))
        return {'success': False, 'error': str(e)}


def registra_importazione(modulo, esito=True, messaggio=None):
    nuova_import = Importazione(
        modulo=modulo,
        timestamp=datetime.now(),
        esito=esito,
        messaggio=messaggio
    )
    db.session.add(nuova_import)
    db.session.commit()
