# config/app_config.py
import os

# Determina la cartella del progetto (modifica in base alla tua struttura)
PROJECT_FOLDER = os.path.dirname(os.path.abspath(__file__))
# Imposta la cartella dei log in base alla root del progetto
LOGS_FOLDER = os.path.join(os.path.dirname(PROJECT_FOLDER), "logs")
