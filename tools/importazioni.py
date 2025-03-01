from routes.esportazioni_teamsystem import serve_risorsa
from extensions import db
from models import Articoli, Barcode, Giacenza
from flask import jsonify
import csv


# Funzione per pulire i caratteri non validi
def clean_text(text):
    if text:
        return text.encode('ascii', 'ignore').decode('ascii')  # Rimuove caratteri non validi
    return text


def import_articoli():
    print("Importazione articoli avviata...")
    db.create_all()

    # 🔥 Cancella tutti i dati esistenti nella tabella articoli
    db.session.query(Articoli).delete()
    db.session.commit()  # ✅ Conferma l'operazione prima di importare nuovi dati
    print("Tabella articoli svuotata.")

    file_csv = serve_risorsa("ARTICOLI.CSV")
    print(f"File CSV: {file_csv}")
    try:
        with open(file_csv, 'r', encoding='utf-8', errors='ignore') as csvfile:
            reader = list(csv.reader(csvfile, delimiter='\t'))  # Converti il reader in lista per calcolare il progresso
            total_rows = len(reader)
            print(f"Righe totali: {total_rows}")

            with db.session.no_autoflush:  # Blocca il flush automatico durante l'elaborazione
                for index, row in enumerate(reader):
                    # pprint(row)
                    if index > 0 and len(row) >= 5:  # Assicurati che la riga abbia abbastanza colonne
                        cod_art = clean_text(row[0])
                        descrizione = clean_text(row[1])
                        descrizione_aggiuntiva = clean_text(row[2])
                        # Converti prezzo a float
                        prezzo = float(row[3][:-2] + "." + row[3][-2:]) if row[3].strip() else 0.0

                        if cod_art and descrizione:  # Verifica che cod_art e descrizione non siano vuoti
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

                    progress = (index + 1) / total_rows * 100
                    # socketio.emit('progress_update', {'progress': progress}, namespace='/import')

        db.session.commit()
        # socketio.emit('progress_update', {'progress': 100}, namespace='/import')
        print("Articoli importati con successo!")

        return jsonify({'message': 'Articoli importati con successo!', 'progress': 100}), 200

    except Exception as e:
        print("Errore durante l'importazione degli Articoli:", e)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


def import_giacenze():
    print("Importazione giacenze avviata...")
    db.create_all()

    # 🔥 Cancella tutti i dati esistenti nella tabella articoli
    db.session.query(Giacenza).delete()
    db.session.commit()  # ✅ Conferma l'operazione prima di importare nuovi dati
    print("Tabella giacenze svuotata.")

    file_csv = serve_risorsa("GIACENZE.CSV")
    print(f"File CSV: {file_csv}")
    try:
        with open(file_csv, 'r', encoding='utf-8', errors='ignore') as csvfile:
            reader = list(csv.reader(csvfile, delimiter='\t'))  # Converti il reader in lista per calcolare il progresso
            total_rows = len(reader)
            print(f"Righe totali: {total_rows}")

            with db.session.no_autoflush:  # Blocca il flush automatico durante l'elaborazione
                for index, row in enumerate(reader):
                    if index > 0 and len(row) >= 4:  # Assicurati che la riga abbia abbastanza colonne
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
                                                       f" nuovo='{valore_nuovo}'. \nQuale valore vuoi mantenere? "
                                                       f"(v=vecchio, n=nuovo): ").strip().lower()
                                        if scelta == 'n':
                                            setattr(giacenza_esistente, campo, valore_nuovo)
                            else:
                                giac_neg = 0
                                giac_www = 0
                                match deposito:
                                    case 0:
                                        giac_neg = giacenza
                                    case 400:
                                        giac_www = giacenza

                                nuova_giacenza = Giacenza(
                                    cod_art=cod_art,
                                    giac_neg=giac_neg,
                                    giac_www=giac_www,
                                )
                                db.session.add(nuova_giacenza)
                                db.session.flush()

                    progress = (index + 1) / total_rows * 100
                    # socketio.emit('progress_update', {'progress': progress}, namespace='/import')
        print(f"ciclo di filtraggio terminato!")
        db.session.commit()
        # socketio.emit('progress_update', {'progress': 100}, namespace='/import')
        print("Giacenze importate con successo!")

        return jsonify({'message': 'Giacenze importate con successo!', 'progress': 100}), 200

    except Exception as e:
        print("Errore durante l'importazione delle Giacenze:", e)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


def import_barcode():
    print("Importazione codici a barre avviata...")
    db.create_all()

    # 🔥 Cancella tutti i dati esistenti nella tabella articoli
    db.session.query(Barcode).delete()
    db.session.commit()  # ✅ Conferma l'operazione prima di importare nuovi dati
    print("Tabella codici a barre svuotata.")

    file_csv = serve_risorsa("BARSEQ.CSV")
    print(f"File CSV: {file_csv}")
    try:
        with open(file_csv, 'r', encoding='utf-8', errors='ignore') as csvfile:
            reader = list(csv.reader(csvfile, delimiter='\t'))  # Converti il reader in lista per calcolare il progresso
            total_rows = len(reader)
            print(f"Righe totali: {total_rows}")

            with db.session.no_autoflush:  # Blocca il flush automatico durante l'elaborazione
                for index, row in enumerate(reader):
                    if index > 0 and len(row) >= 5:  # Assicurati che la riga abbia abbastanza colonne
                        cod_bar = clean_text(row[3])
                        cod_art = clean_text(row[0])
                        cod_bar = cod_bar.strip()
                        print(f"DEBUG: contenuto senza spazi di cod_bar: {cod_bar}")
                        print(f"DEBUG: contenuto senza spazi di cod_art: {cod_art}")
                        if cod_bar and cod_art:    # Verifica che cod_art e descrizione non siano vuoti
                            print(f"DEBUG: contenuto di cod_bar: {cod_bar}")
                            nuovo_barcode = Barcode(
                                cod_bar=cod_bar,
                                cod_art=cod_art
                            )
                            db.session.add(nuovo_barcode)
                            db.session.flush()

                    progress = (index + 1) / total_rows * 100
                    # socketio.emit('progress_update', {'progress': progress}, namespace='/import')

        db.session.commit()
        # socketio.emit('progress_update', {'progress': 100}, namespace='/import')
        print("Codici a Barre importati con successo!")

        return jsonify({'message': 'Codici a Barre importati con successo!', 'progress': 100}), 200

    except Exception as e:
        print("Errore durante l'importazione dei codici a barre:", e)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
