from extensions import db
from flask_login import UserMixin
from datetime import datetime
from tools.log_utils import get_logger

logger = get_logger('models')


class Menu(db.Model):
    __tablename__ = 'menus'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    weight = db.Column(db.Integer, default=0)
    parent_id = db.Column(db.Integer, db.ForeignKey('menus.id'), nullable=True)
    route = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    parent = db.relationship('Menu', remote_side=[id], backref='children')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'weight': self.weight,
            'parent_id': self.parent_id,
            'route': self.route,
            'is_active': self.is_active,
            'parent': self.parent.name if self.parent else None,
        }

    def __repr__(self):
        return f"<Menu {self.name}>"


class Articoli(db.Model):
    cod_art = db.Column(db.String(255), primary_key=True)
    descrizione = db.Column(db.String(255))
    descrizione_aggiuntiva = db.Column(db.Text)
    prezzo = db.Column(db.Numeric)

    # ⚙️ Nuove colonne
    ppc = db.Column(db.Integer, default=1)  # ppc
    cpp = db.Column(db.Integer, default=1)  # cpp

    def to_dict(self):
        return {
            'cod_art': self.cod_art,
            'descrizione': self.descrizione,
            'descrizione_aggiuntiva': self.descrizione_aggiuntiva,
            'prezzo': self.prezzo,
            'ppc': self.pezzi_per_collo,
            'cpp': self.colli_per_pedana
        }

    def __repr__(self):
        return f"<Articolo {self.cod_art}>"


class Barcode(db.Model):
    cod_bar = db.Column(db.String(255), primary_key=True)
    cod_art = db.Column(db.String(255))

    def to_dict(self):
        return {
            'cod_bar': self.cod_bar,
            'cod_art': self.cod_art
        }

    def __repr__(self):
        return f"<Codice a Barre {self.cod_bar}>"


class Immagini(db.Model):
    file_img = db.Column(db.String(255), primary_key=True)
    cod_art = db.Column(db.String(255))

    def to_dict(self):
        return {
            'file_img': self.file_img,
            'cod_art': self.cod_art
        }

    def __repr__(self):
        return f"<Immagine {self.file_img}>"


class SchedeProdotti(db.Model):
    descrizione = db.Column(db.String(5000), nullable=True)
    short = db.Column(db.String(5000), nullable=True)
    cod_art = db.Column(db.String(255), primary_key=True)

    def to_dict(self):
        return {
            'descrizione': self.descrizione,
            'short': self.short,
            'cod_art': self.cod_art
        }

    def __repr__(self):
        return f"<Scheda Prodotto {self.descrizione}>"


class Sincro(db.Model):
    cod_art = db.Column(db.String(255), primary_key=True)
    prestashop = db.Column(db.Boolean)
    poleepo = db.Column(db.Boolean)
    teamsystem = db.Column(db.Boolean)

    def to_dict(self):
        return {
            'cod_art': self.cod_art,
            'prestashop': self.prestashop,
            'poleepo': self.poleepo,
            'teamsystem': self.teamsystem
        }


class Giacenza(db.Model):
    cod_art = db.Column(db.String(255), primary_key=True)
    giac_neg = db.Column(db.Integer, default=0)
    giac_www = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            'cod_art': self.cod_art,
            'giac_neg': self.giac_neg,
            'giac_www': self.giac_www
        }

    def __repr__(self):
        return f"<Articolo {self.cod_art}>"


class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(150))
    weight = db.Column(db.Integer)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    surname = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    phone = db.Column(db.String(20))
    birth_date = db.Column(db.Date)
    city = db.Column(db.String(100))
    province = db.Column(db.String(50))
    sex = db.Column(db.Integer, default=0)
    foto_profilo = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now())
    updated_at = db.Column(db.DateTime, default=datetime.now(), onupdate=datetime.now())
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False, default=1)
    role = db.relationship('Role', backref='users')

    def get_id(self):
        return str(self.id)


class Inventario(db.Model):
    __tablename__ = 'inventari'

    id = db.Column(db.Integer, primary_key=True)
    data_inventario = db.Column(db.Date, unique=True, nullable=False)

    # relazione con righe inventario
    righe = db.relationship('InventarioRiga', backref='inventario', cascade='all, delete-orphan')


class InventarioRiga(db.Model):
    __tablename__ = 'inventario_righe'

    id = db.Column(db.Integer, primary_key=True)
    inventario_id = db.Column(db.Integer, db.ForeignKey('inventari.id', ondelete='CASCADE'))
    articolo_id = db.Column(db.String(255), db.ForeignKey('articoli.cod_art', ondelete='SET NULL'), nullable=True)
    descrizione_articolo = db.Column(db.String(255), nullable=True)
    barcode_articolo = db.Column(db.String(50), nullable=True)
    quantita_inserita = db.Column(db.Integer, nullable=False)

    # 🆕 Campi aggiuntivi
    num_pedane = db.Column(db.Integer)
    num_cartoni = db.Column(db.Integer)
    num_pezzi_sciolti = db.Column(db.Integer)
    ppc = db.Column(db.Integer)
    cpp = db.Column(db.Integer)

    utente_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

    articolo = db.relationship('Articoli', backref='righe_inventario')
    utente = db.relationship('User', backref='righe_inventario')


class InventarioExport(db.Model):
    __tablename__ = 'inventario_export'

    id = db.Column(db.Integer, primary_key=True)
    inventario_id = db.Column(db.Integer, db.ForeignKey('inventari.id', ondelete='CASCADE'))
    articolo_id = db.Column(db.String(255), db.ForeignKey('articoli.cod_art', ondelete='SET NULL'), nullable=True)
    descrizione_articolo = db.Column(db.String(255), nullable=True)
    barcode_articolo = db.Column(db.String(50), nullable=True)
    giacenza = db.Column(db.Integer, nullable=False)

    articolo = db.relationship('Articoli', backref='inventario_export')


class Importazione(db.Model):
    __tablename__ = 'importazioni'

    id = db.Column(db.Integer, primary_key=True)
    modulo = db.Column(db.String(50), nullable=False)  # es. 'articoli', 'barcode', 'giacenze'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    esito = db.Column(db.Boolean, default=True)  # True = successo, False = errore
    messaggio = db.Column(db.String(255), nullable=True)  # messaggio opzionale, utile in caso di errore


class ModuloImportazione(db.Model):
    __tablename__ = 'moduli_importazione'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    descrizione = db.Column(db.String(255), nullable=True)
