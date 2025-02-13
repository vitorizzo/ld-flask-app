import csv

from flask import request, flash, render_template, Blueprint, jsonify
from flask_login import login_required
from flask_socketio import emit

from extensions import db
from models import Menu, Role, Articoli
from routes.decorators import role_required


settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.route('/update_menu', methods=['POST'])
@login_required
@role_required('menus')  # Use a string identifier instead
def update_menu():
    try:
        menu_id = request.form.get('menu_id')
        if not menu_id:
            return jsonify({'success': False, 'error': 'Menu ID is missing'}), 400

        menu = Menu.query.get(menu_id)
        if not menu:
            return jsonify({'success': False, 'error': f'No menu found with ID {menu_id}'}), 404

        # Extract form data
        name = request.form.get('name')
        route = request.form.get('route')
        is_active = request.form.get('is_active') == 'true'
        weight = request.form.get('weight')
        parent_id = request.form.get('parent_id')

        # Update the menu in the database
        menu = Menu.query.get(menu_id)
        if menu:
            menu.name = name
            menu.route = route
            menu.is_active = is_active
            menu.weight = weight
            menu.parent_id = parent_id
            db.session.commit()
            # flash('Menu aggiornati con successo!', 'success')
            # return render_template('settings/menus.html', menus=Menu.query.all())
            return jsonify({'success': True, 'message': 'Menu updated successfully'})
        else:
            return jsonify({'success': False, 'error': f'No menu read with ID {menu_id}'}), 404
    except Exception as e:
        db.session.rollback()
        print(f"Error updating menu: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/menu/<int:menu_id>')
def get_menu_data(menu_id):
    menu = Menu.query.get_or_404(menu_id)
    return jsonify(menu.to_dict())


@settings_bp.route('/menus', methods=['GET', 'POST'])
@login_required
@role_required(900)  # Use an integer identifier instead
def manage_menus():
    if request.method == 'POST':
        # Aggiungi o modifica un menu
        name = request.form['name']
        route = request.form['route']
        parent_id = request.form.get('parent_id', None)
        weight = request.form.get('weight', 0)
        new_menu = Menu(name=name, route=route, parent_id=parent_id, weight=weight)
        db.session.add(new_menu)
        db.session.commit()
        flash('Menu salvato con successo!', 'success')
    menus = Menu.query.all()
    roles = Role.query.order_by(Role.weight.desc()).all()
    menu_fields = [column.name for column in Menu.__table__.columns if column.name != 'id']
    return render_template('settings/menus.html', menus=menus, roles=roles, menu_fields=menu_fields)


# Funzione per pulire i caratteri non validi
def clean_text(text):
    if text:
        return text.encode('ascii', 'ignore').decode('ascii')  # Rimuove caratteri non validi
    return text


@settings_bp.route('/import_articoli', methods=['GET', 'POST'])
@login_required
@role_required(100)
def import_articoli():
    file_csv = r"C:\Users\EliteBook\OneDrive\Documents\MEGAsync\PycharmProjects\ld-flask-app\esportazioni\articoli.csv"
    try:
        with open(file_csv, 'r', encoding='utf-8', errors='ignore') as csvfile:
            reader = list(csv.reader(csvfile, delimiter='\t'))  # Converti il reader in lista per calcolare il progresso
            total_rows = len(reader)

            with db.session.no_autoflush:  # Blocca il flush automatico durante l'elaborazione
                for index, row in enumerate(reader):
                    if len(row) >= 5:  # Assicurati che la riga abbia abbastanza colonne
                        cod_art = clean_text(row[0])
                        descrizione = clean_text(row[1])
                        descrizione_aggiuntiva = clean_text(row[2])
                        prezzo = float(row[3]) if row[3].strip() else 0.0  # Converti prezzo a float

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

                    progress = (index + 1) / total_rows * 100
                    emit('progress_update', {'progress': progress}, namespace='/import')

        db.session.commit()
        emit('progress_update', {'progress': 100}, namespace='/import')
        print("Dati importati con successo!")

        return jsonify({'message': 'Dati importati con successo!', 'progress': 100}), 200

    except Exception as e:
        print("Errore durante l'importazione:", e)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
