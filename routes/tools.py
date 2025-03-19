from flask_login import current_user
from bs4 import BeautifulSoup
import html

from models import Menu


def get_user_menu():
    if current_user.is_authenticated:
        role_weight = current_user.role.weight  # Supponendo che `role` abbia un attributo `weight`
        menus = Menu.query.filter(Menu.is_active == True).all()  # Prendi solo i menu attivi
        user_menu = {
            menu.name: "enabled" if role_weight >= menu.weight else "disabled"
            for menu in menus
        }
    else:
        user_menu = {
            menu.name: "disabled" for menu in Menu.query.filter(Menu.is_active == True).all()
        }
    return user_menu


def clean_text(raw_text):
    """
    Pulisce un testo HTML rimuovendo i tag e convertendo le entità HTML.

    :param raw_text: Stringa contenente il testo HTML sporco
    :return: Stringa pulita e leggibile
    """
    if not raw_text:
        return ""

    # Parsing HTML per rimuovere i tag
    soup = BeautifulSoup(raw_text, "html.parser")

    # Estrazione del testo e rimozione dei tag
    cleaned_text = soup.get_text(separator="\n")

    # Decodifica le entità HTML (&egrave; -> è, &amp; -> &)
    cleaned_text = html.unescape(cleaned_text)

    # Rimuove eventuali spazi extra o linee vuote inutili
    cleaned_text = "\n".join([line.strip() for line in cleaned_text.split("\n") if line.strip()])

    return cleaned_text
