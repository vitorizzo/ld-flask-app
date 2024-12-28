from extensions import db
from flask_login import UserMixin
from datetime import datetime


class Menu(db.Model):
    __tablename__ = 'menus'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # Nome del menu (es. "Eventi")
    weight = db.Column(db.Integer, default=0)  # Ordine di visualizzazione
    parent_id = db.Column(db.Integer, db.ForeignKey('menus.id'), nullable=True)  # Per sottomenu
    route = db.Column(db.String(100), nullable=True)  # Route associata al menu
    is_active = db.Column(db.Boolean, default=True)  # Indica se è visibile
    parent = db.relationship('Menu', remote_side=[id], backref='children')  # Relazione per sottomenu

    def __repr__(self):
        return f"<Menu {self.name}>"


class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # Nome del ruolo
    description = db.Column(db.String(150))  # Descrizione del ruolo (opzionale)
    weight = db.Column(db.Integer)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)  # Nome
    surname = db.Column(db.String(150), nullable=False)  # Cognome
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    phone = db.Column(db.String(20))
    birth_date = db.Column(db.Date)
    city = db.Column(db.String(100))
    province = db.Column(db.String(50))
    sex = db.Column(db.Integer, default=0)  # 0 = neutro, 1 = maschio, 2 = femmina
    foto_profilo = db.Column(db.String(255), nullable=True)  # Percorso foto profilo
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False, default=1)  # Ruolo predefinito
    role = db.relationship('Role', backref='users')  # Relazione con Role

    def get_id(self):
        return str(self.id)
