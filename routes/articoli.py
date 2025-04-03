from flask import Blueprint, render_template
from tools.log_utils import log_task, get_logger

# Logger specifico per articoli
logger = get_logger('articoli')

# Creazione del blueprint
articoli_bp = Blueprint('articoli', __name__, template_folder='../templates')


@articoli_bp.route('/articoli')
@log_task(logger)
def articoli():
    return render_template('articoli_codebar.html')