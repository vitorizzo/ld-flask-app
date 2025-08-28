from flask import Blueprint, render_template
from tools.log_utils import log_task, get_logger

# Logger specifico per articoli
logger = get_logger('app_installation')

# Creazione del blueprint
installation_bp = Blueprint('installation', __name__, template_folder='../templates')


@installation_bp.route('/app_installation')
@log_task(logger)
def installation():
    return render_template('app_installation.html')