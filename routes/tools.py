from flask_login import current_user
from bs4 import BeautifulSoup
import html
from models import Menu
from tools.log_utils import get_logger
from tools.role_required import menu_minimum_weight, load_navigation_menus

logger = get_logger('tools')


def get_user_menu():
    try:
        if current_user.is_authenticated:
            role_weight = current_user.max_role_weight
            menus = [menu for menu in load_navigation_menus() if menu.item_type == "link"]
            user_menu = {
                menu.name: "enabled" if role_weight >= (menu_minimum_weight(menu) if menu_minimum_weight(menu) is not None else float("inf")) and menu.is_active else "disabled"
                for menu in menus
            }
            logger.debug(f"Generato menu per utente autenticato: peso ruolo {role_weight}")
        else:
            user_menu = {
                menu.name: "disabled"
                for menu in [item for item in load_navigation_menus() if item.item_type == "link"]
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
