from flask import Blueprint, render_template

# Creazione del blueprint
articoli_bp = Blueprint('articoli', __name__, template_folder='../templates')


@articoli_bp.route('/articoli')
def articoli():
    return render_template('articoli_codebar.html')
