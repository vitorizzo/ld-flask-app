from flask_login import current_user
from bs4 import BeautifulSoup
import html
from models import Menu
from tools.log_utils import get_logger

logger = get_logger('tools')


def get_user_menu():
    try:
        if current_user.is_authenticated:
            role_weight = current_user.max_role_weight
            menus = Menu.query.filter(Menu.is_active == True).all()
            user_menu = {
                menu.name: "enabled" if role_weight >= menu.weight else "disabled"
                for menu in menus
            }
            logger.debug(f"Generato menu per utente autenticato: peso ruolo {role_weight}")
        else:
            user_menu = {
                menu.name: "disabled" for menu in Menu.query.filter(Menu.is_active == True).all()
            }
            logger.debug("Generato menu per utente non autenticato (tutti disabilitati)")
        return user_menu
    except Exception as e:
        logger.exception("Errore durante la generazione del menu utente:")
        return {}


def clean_text(raw_text):
    try:
        if not raw_text:
            return ""

        soup = BeautifulSoup(raw_text, "html.parser")
        cleaned_text = soup.get_text(separator="\n")
        cleaned_text = html.unescape(cleaned_text)
        cleaned_text = "\n".join([line.strip() for line in cleaned_text.split("\n") if line.strip()])
        logger.debug("Testo HTML pulito correttamente.")
        return cleaned_text
    except Exception as e:
        logger.exception("Errore durante la pulizia del testo HTML:")
        return raw_text
