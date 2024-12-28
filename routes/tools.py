from flask_login import current_user

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
