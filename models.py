from sqlalchemy.dialects.postgresql import JSONB
from future.backports.datetime import datetime

from extensions import db
from flask_login import UserMixin
from datetime import datetime, timezone
from sqlalchemy.orm import foreign
from sqlalchemy import Sequence

from tools.crypto import EncryptedString
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
    id_art = db.Column(
        db.BigInteger,
        Sequence("articoli_id_art_seq"),
        unique=True,
        nullable=True,
        server_default=db.text("nextval('articoli_id_art_seq'::regclass)")
    )
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
    __tablename__ = "barcode"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)

    cod_bar = db.Column(db.String(255), nullable=False, index=True)
    cod_art = db.Column(db.String(255), nullable=True)  # retrocompatibilità
    id_art = db.Column(db.BigInteger, db.ForeignKey('articoli.id_art'), nullable=True, index=True)

    __table_args__ = (
        db.UniqueConstraint('cod_bar', 'id_art', name='uq_barcode_codbar_idart'),
    )

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
    id_art = db.Column(db.BigInteger, db.ForeignKey('articoli.id_art'), nullable=True, index=True)

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
    id_art = db.Column(
        db.BigInteger,
        db.ForeignKey('articoli.id_art'),
        nullable=True,
        index=True
    )

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
    id_art = db.Column(
        db.BigInteger,
        db.ForeignKey('articoli.id_art'),
        nullable=True,
        index=True
    )

    def to_dict(self):
        return {
            'cod_art': self.cod_art,
            'prestashop': self.prestashop,
            'poleepo': self.poleepo,
            'teamsystem': self.teamsystem
        }


class Giacenza(db.Model):
    id_art = db.Column(db.BigInteger, db.ForeignKey('articoli.id_art'), index=True, nullable=True)
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

    user_roles = db.relationship('UserRole', backref='role', lazy=True)


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

    # RIMOSSI role_id e role
    # role_id = ...
    # role = ...

    roles = db.relationship('UserRole', backref='user', lazy=True)

    @property
    def active_roles(self):
        """Restituisce SOLO i ruoli attivi in questo momento."""
        now = datetime.now()

        if not hasattr(self, "roles"):
            return []

        return [
            ur.role
            for ur in self.roles
            if ur.role is not None and (
                    ur.valid_until is None or ur.valid_until >= now
            )
        ]

    @property
    def max_role_weight(self):
        """Restituisce il peso massimo dei ruoli attivi dell’utente."""
        active = self.active_roles
        if not active:
            return 0
        return max(role.weight for role in active)

    def get_id(self):
        return str(self.id)


class UserRole(db.Model):
    __tablename__ = 'user_roles'

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)

    type = db.Column(db.String(20), nullable=False, default="lifetime")
    # valori: lifetime | until | period

    valid_from = db.Column(db.DateTime, nullable=False, default=datetime.utcnow())
    valid_until = db.Column(db.DateTime, nullable=True)

    notes = db.Column(db.String(255))

    @property
    def is_active(self):
        now = datetime.datetime.now(datetime.UTC)

        if self.type == "lifetime":
            return True

        if self.type == "until":
            return self.valid_until is None or now <= self.valid_until

        if self.type == "period":
            start_ok = now >= self.valid_from
            end_ok = self.valid_until is None or now <= self.valid_until
            return start_ok and end_ok

        return False


class Inventario(db.Model):
    __tablename__ = 'inventari'

    id = db.Column(db.Integer, primary_key=True)
    data_inventario = db.Column(db.Date, unique=True, nullable=False)
    deposito = db.Column(db.String(10), nullable=False, default='000')
    export_inventario = db.Column(db.Boolean, nullable=False, default=False)
    fix_movements = db.Column(db.Boolean, nullable=False, default=False)

    # relazione con righe inventario
    righe = db.relationship('InventarioRiga', backref='inventario', cascade='all, delete-orphan')


class RettificaInventario(db.Model):
    __tablename__ = 'rettifiche_inventario'

    id = db.Column(db.Integer, primary_key=True)
    inventario_id = db.Column(db.Integer, db.ForeignKey('inventari.id', ondelete='CASCADE'))
    articolo_id = db.Column(db.String(255), nullable=True)
    deposito = db.Column(db.String(10), nullable=False, default='000')
    giacenza = db.Column(db.Integer, nullable=False)
    rilevazione = db.Column(db.Integer, nullable=False)
    rettifica = db.Column(db.Integer, nullable=False)
    utente_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    id_art = db.Column(db.BigInteger, db.ForeignKey('articoli.id_art'), index=True, nullable=True)

    articolo = db.relationship(
        "Articoli",
        primaryjoin=foreign(articolo_id) == Articoli.cod_art,
        backref='rettifiche_inventario'
    )
    utente = db.relationship('User', backref='rettifiche_inventario')


class InventarioRiga(db.Model):
    __tablename__ = 'inventario_righe'

    id = db.Column(db.Integer, primary_key=True)
    inventario_id = db.Column(db.Integer, db.ForeignKey('inventari.id', ondelete='CASCADE'))
    articolo_id = db.Column(db.String(255), db.ForeignKey('articoli.cod_art', ondelete='SET NULL'), nullable=True)
    descrizione_articolo = db.Column(db.String(255), nullable=True)
    barcode_articolo = db.Column(db.String(50), nullable=True)
    quantita_inserita = db.Column(db.Integer, nullable=False)
    has_versions = db.Column(db.Boolean, default=False)  # Indica se la riga ha versioni
    id_art = db.Column(db.BigInteger, db.ForeignKey('articoli.id_art'), nullable=True, index=True)
    # 🆕 Campi aggiuntivi
    num_pedane = db.Column(db.Integer)
    num_cartoni = db.Column(db.Integer)
    num_pezzi_sciolti = db.Column(db.Integer)
    ppc = db.Column(db.Integer)
    cpp = db.Column(db.Integer)

    utente_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    deposito = db.Column(db.String(10), nullable=False, default='000')
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

    articolo = db.relationship('Articoli', foreign_keys=[articolo_id], backref='righe_inventario')
    utente = db.relationship('User', backref='righe_inventario')


class ImportInventari(db.Model):
    __tablename__ = 'import_inventario'

    id = db.Column(db.Integer, primary_key=True)
    inventario_id = db.Column(db.Integer, db.ForeignKey('inventari.id', ondelete='CASCADE'))
    articolo_id = db.Column(db.String(255), nullable=True)
    descrizione_articolo = db.Column(db.String(255), nullable=True)
    deposito = db.Column(db.String(10), nullable=False, default='000')
    quantita_esistente = db.Column(db.Integer, nullable=False)
    costo = db.Column(db.Numeric, nullable=True)
    utente_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    id_art = db.Column(db.BigInteger, db.ForeignKey('articoli.id_art'), index=True, nullable=True)

    articolo = db.relationship(
        "Articoli",
        primaryjoin=foreign(articolo_id) == Articoli.cod_art,
        backref='import_inventario'
    )
    utente = db.relationship('User', backref='import_inventario')


class InventarioRigaVersione(db.Model):
    __tablename__ = 'inventario_righe_versioni'

    id = db.Column(db.Integer, primary_key=True)
    riga_id = db.Column(db.Integer, db.ForeignKey('inventario_righe.id', ondelete='CASCADE'))
    utente_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Copia dei campi da InventarioRiga
    quantita_inserita = db.Column(db.Integer, nullable=False)
    num_pedane = db.Column(db.Integer)
    num_cartoni = db.Column(db.Integer)
    num_pezzi_sciolti = db.Column(db.Integer)
    ppc = db.Column(db.Integer)
    cpp = db.Column(db.Integer)

    riga = db.relationship('InventarioRiga', backref='versioni')
    deposito = db.Column(db.String(10), nullable=False, default='000')
    utente = db.relationship('User', backref='versioni_inventario')


class InventarioExport(db.Model):
    __tablename__ = 'inventario_export'

    id = db.Column(db.Integer, primary_key=True)
    inventario_id = db.Column(db.Integer, db.ForeignKey('inventari.id', ondelete='CASCADE'))
    articolo_id = db.Column(db.String(255), db.ForeignKey('articoli.cod_art', ondelete='SET NULL'), nullable=True)
    descrizione_articolo = db.Column(db.String(255), nullable=True)
    barcode_articolo = db.Column(db.String(50), nullable=True)
    giacenza = db.Column(db.Integer, nullable=False)
    deposito = db.Column(db.String(10), nullable=False, default='000')
    id_art = db.Column(
        db.BigInteger,
        db.ForeignKey('articoli.id_art'),
        nullable=True,
        index=True
    )

    articolo = db.relationship('Articoli', backref='inventario_export')


class Importazione(db.Model):
    __tablename__ = 'importazioni'

    id = db.Column(db.Integer, primary_key=True)
    modulo = db.Column(db.String(50), nullable=False)  # es. 'articoli', 'barcode', 'giacenze'
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    esito = db.Column(db.Boolean, default=True)  # True = successo, False = errore
    messaggio = db.Column(db.String(255), nullable=True)  # messaggio opzionale, utile in caso di errore


class ModuloImportazione(db.Model):
    __tablename__ = 'moduli_importazione'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    descrizione = db.Column(db.String(255), nullable=True)


class TrelloConfig(db.Model):
    __tablename__ = 'trello_configs'

    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(EncryptedString(256), nullable=False)
    token = db.Column(EncryptedString(256), nullable=False)
    id_model = db.Column(db.String(64), nullable=False)
    callback_url = db.Column(db.String(256), nullable=False)
    webhook_id = db.Column(db.String(64), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))


class TrelloConnection(db.Model):
    __tablename__ = 'trello_connections'

    id = db.Column(db.Integer, primary_key=True)
    board_id = db.Column(db.String(128), nullable=False, unique=True)
    board_name = db.Column(db.String(255), nullable=False)
    api_key = db.Column(db.String(255), nullable=False)
    token = db.Column(db.String(255), nullable=False)
    callback_url = db.Column(db.String(256), nullable=True)
    webhook_id = db.Column(db.String(255), nullable=True)
    schema_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc),
                           nullable=True)
    ordine = db.Column(db.Integer, default=0)
    actions = db.relationship('TrelloAction', back_populates='connection', cascade='all, delete-orphan')


class TrelloAction(db.Model):
    __tablename__ = 'trello_actions'

    id = db.Column(db.Integer, primary_key=True)
    connection_id = db.Column(db.Integer, db.ForeignKey('trello_connections.id', ondelete='CASCADE'), nullable=False)
    trigger_type = db.Column(db.String(64), nullable=False)
    action_type = db.Column(db.String(64), nullable=False)
    config_json = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    ordine = db.Column(db.Integer, default=0)
    connection = db.relationship('TrelloConnection', back_populates='actions')


class ImportRun(db.Model):
    __tablename__ = 'import_runs'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(64), nullable=False, index=True)
    file_name = db.Column(db.String(255), nullable=True)

    started_at = db.Column(db.DateTime, default=datetime.utcnow(), nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)

    summary = db.Column(JSONB, nullable=True)

    conflicts = db.relationship(
        'ImportConflict',
        backref='run',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )


class ImportConflict(db.Model):
    __tablename__ = 'import_conflicts'

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(
        db.Integer,
        db.ForeignKey('import_runs.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    type = db.Column(db.String(50), nullable=False)
    # es: CODICE_RIUSATO, DESCRIZIONE_DIVERGENTE, DUPLICATO_POTENZIALE

    payload = db.Column(JSONB, nullable=False)
    # dati grezzi del conflitto (csv_row, articolo_db, diff, ecc.)

    status = db.Column(
        db.String(20),
        nullable=False,
        default='pending'
    )
    # pending | resolved | ignored

    resolution = db.Column(JSONB, nullable=True)
    # scelta operatore (es: keep_db, overwrite, create_new, remap)

    created_at = db.Column(db.DateTime, default=datetime.utcnow(), nullable=False)
    resolved_at = db.Column(db.DateTime, nullable=True)
