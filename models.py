import hashlib

from sqlalchemy.dialects.postgresql import JSONB
from future.backports.datetime import datetime

from extensions import db
from flask_login import UserMixin
from datetime import datetime, timezone, date
from sqlalchemy.orm import foreign
from sqlalchemy import Sequence, Index, UniqueConstraint

from tools.crypto import EncryptedString
from tools.log_utils import get_logger

logger = get_logger('models')


class Menu(db.Model):
    __tablename__ = 'menus'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    weight = db.Column(db.Integer, default=0)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
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
            'sort_order': self.sort_order,
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
    id_art = db.Column(db.BigInteger, db.ForeignKey('articoli.id_art'), nullable=True, index=True)

    articolo = db.relationship('Articoli', foreign_keys=[articolo_id], backref='inventario_export')


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
    __tablename__ = "import_runs"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(64), nullable=False, index=True)
    file_name = db.Column(db.String(255), nullable=True)

    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)

    summary = db.Column(JSONB, nullable=True)

    conflicts = db.relationship(
        "ImportConflict",
        back_populates="run",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )


class ImportConflict(db.Model):
    __tablename__ = "import_conflicts"

    id = db.Column(db.Integer, primary_key=True)

    # FK verso import_runs
    run_id = db.Column(
        db.Integer,
        db.ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=True,          # metti False solo se sei certo che ogni conflitto appartenga a una run
        index=True,
    )

    run = db.relationship("ImportRun", back_populates="conflicts")

    type = db.Column(db.String(100), nullable=False)
    payload = db.Column(JSONB, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    status = db.Column(db.String(20), default="OPEN", nullable=False)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    __table_args__ = (
        Index("ix_import_conflicts_type_status", "type", "status"),
        Index("ix_import_conflicts_run_status", "run_id", "status"),
    )


# ------------------------------------------------------------
# A) Regole persistenti di risoluzione (per evitare conflitti ricorrenti)
# ------------------------------------------------------------
class ImportConflictResolution(db.Model):
    __tablename__ = "import_conflict_resolutions"

    id = db.Column(db.BigInteger, primary_key=True)

    # Tipo conflitto (es. CODICE_RIASSEGNATO_O_DESC_DISCORDANTE, DESCRIZIONE_DIVERGENTE)
    type = db.Column(db.String(64), nullable=False, index=True)

    # Chiave dell’entità “certa” (es. cod_art). La useremo per ritrovare rapidamente la regola.
    entity_key = db.Column(db.String(64), nullable=False, index=True)

    # Campo/ambito del conflitto (es. descrizione, descrizione_aggiuntiva, prezzo, ecc.)
    field = db.Column(db.String(64), nullable=False, index=True)

    # Valori “leggibili” per audit/rollback
    db_value = db.Column(db.Text, nullable=True)
    csv_value = db.Column(db.Text, nullable=True)

    # Fingerprint per riconoscere lo stesso identico conflitto
    db_value_hash = db.Column(db.String(64), nullable=True, index=True)
    csv_value_hash = db.Column(db.String(64), nullable=True, index=True)

    # Decisione
    action = db.Column(db.String(16), nullable=False)  # KEEP_DB / KEEP_CSV

    # Modalità: applica sempre o solo se matcha esattamente lo stato visto (hash)
    mode = db.Column(db.String(16), nullable=False, default="CONDITIONAL")  # CONDITIONAL / ALWAYS

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.Index(
            "ix_icr_lookup",
            "type", "entity_key", "field", "mode", "db_value_hash", "csv_value_hash"
        ),
    )


# ------------------------------------------------------------
# B) Audit delle azioni applicate (rollback/cronologia)
# ------------------------------------------------------------
class ImportConflictAction(db.Model):
    __tablename__ = "import_conflict_actions"

    id = db.Column(db.BigInteger, primary_key=True)

    conflict_id = db.Column(db.Integer, db.ForeignKey("import_conflicts.id", ondelete="CASCADE"), nullable=True)
    type = db.Column(db.String(100), nullable=False)
    key = db.Column(db.String(255), nullable=False)
    action = db.Column(db.String(20), nullable=False)      # KEEP_CSV / KEEP_DB / SKIP

    before = db.Column(JSONB, nullable=True)               # snapshot pre-azione (DB)
    after = db.Column(JSONB, nullable=True)                # snapshot post-azione
    applied = db.Column(db.Boolean, default=False, nullable=False)

    applied_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    applied_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    applied_by_user = db.relationship("User", foreign_keys=[applied_by])
    conflict = db.relationship("ImportConflict", backref=db.backref("actions", lazy="dynamic",
                                                                    cascade="all, delete-orphan"))

    __table_args__ = (
        Index("ix_ica_type_key", "type", "key"),
        Index("ix_ica_conflict_id", "conflict_id"),
        Index("ix_ica_applied_at", "applied_at"),
    )


class SlackConnection(db.Model):
    __tablename__ = 'slack_connections'

    id = db.Column(db.Integer, primary_key=True)

    team_id = db.Column(db.String(64), nullable=False, unique=True)
    team_name = db.Column(db.String(255), nullable=True)

    bot_user_id = db.Column(db.String(64), nullable=True)

    # Token bot (xoxb-...) — lo mettiamo qui per avere più workspace in futuro
    bot_token = db.Column(EncryptedString(256), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc),
                           onupdate=datetime.now(timezone.utc), nullable=True)

    ordine = db.Column(db.Integer, default=0)

    actions = db.relationship(
        'SlackAction',
        back_populates='connection',
        cascade='all, delete-orphan'
    )


class SlackAction(db.Model):
    __tablename__ = 'slack_actions'

    id = db.Column(db.Integer, primary_key=True)
    connection_id = db.Column(
        db.Integer,
        db.ForeignKey('slack_connections.id', ondelete='CASCADE'),
        nullable=False
    )

    trigger_type = db.Column(db.String(64), nullable=False)  # es: message.channels, reaction_added
    action_type = db.Column(db.String(64), nullable=False)   # es: addReaction, postMessage, createTrelloCard...
    config_json = db.Column(db.JSON, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), nullable=False)
    ordine = db.Column(db.Integer, default=0)

    connection = db.relationship('SlackConnection', back_populates='actions')


class SlackEvent(db.Model):
    __tablename__ = "slack_events"

    id = db.Column(db.Integer, primary_key=True)

    # opzionale: per multi-workspace in futuro
    connection_id = db.Column(
        db.Integer,
        db.ForeignKey("slack_connections.id", ondelete="SET NULL"),
        nullable=True
    )
    # es: "message.channels", "reaction_added"
    trigger_type = db.Column(db.String(64), nullable=False, index=True)
    # id evento Slack (se presente): event_id / event_ts / item.ts ecc.
    event_ts = db.Column(db.String(32), nullable=True, index=True)
    # Dedup key: hash del body raw o combinazione stabile (definiremo dopo)
    dedup_key = db.Column(db.String(128), nullable=True, unique=True, index=True)
    # payload originale (o normalizzato) per audit/debug/replay
    payload = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    connection = db.relationship("SlackConnection", backref="events")


# ==========================================================
# Automations v2 — Cross-app (PARALLELO al sistema legacy)
# ==========================================================

class Automation(db.Model):
    __tablename__ = 'automations'

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)

    trigger_app = db.Column(db.String(50), nullable=False)
    trigger_connection = db.Column(db.Integer, nullable=False)
    trigger_type = db.Column(db.String(100), nullable=False)
    trigger_config = db.Column(JSONB, nullable=True)

    enabled = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    actions = db.relationship(
        'AutomationAction',
        backref='automation',
        cascade='all, delete-orphan',
        order_by='AutomationAction.order_index',
        lazy='dynamic'
    )


class AutomationAction(db.Model):
    __tablename__ = 'automation_actions'

    id = db.Column(db.Integer, primary_key=True)

    automation_id = db.Column(
        db.Integer,
        db.ForeignKey('automations.id', ondelete='CASCADE'),
        nullable=False
    )

    order_index = db.Column(db.Integer, nullable=False)

    action_app = db.Column(db.String(50), nullable=False)
    action_type = db.Column(db.String(100), nullable=False)
    action_config = db.Column(JSONB, nullable=True)

    enabled = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            'automation_id',
            'order_index',
            name='uq_automation_action_order'
        ),
    )


class DeliveryRoute(db.Model):
    __tablename__ = "delivery_routes"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)  # es. "marsica"
    slack_channel_id = db.Column(db.String(50), nullable=False, unique=True)

    default_weekday = db.Column(db.Integer, nullable=False)
    # 0 = lunedì ... 6 = domenica

    default_time = db.Column(db.Time, nullable=False)

    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class DeliveryOverride(db.Model):
    __tablename__ = "delivery_overrides"

    id = db.Column(db.Integer, primary_key=True)

    route_id = db.Column(
        db.Integer,
        db.ForeignKey("delivery_routes.id", ondelete="CASCADE"),
        nullable=False,
    )

    delivery_date = db.Column(db.Date, nullable=False)
    override_delivery_date = db.Column(db.Date, nullable=True)

    type = db.Column(
        db.String(20), nullable=False
    )
    # shift | extra | cancel

    note = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    route = db.relationship("DeliveryRoute", backref="overrides")


class SlackOrder(db.Model):
    __tablename__ = "slack_orders"

    id = db.Column(db.Integer, primary_key=True)

    route_id = db.Column(
        db.Integer,
        db.ForeignKey("delivery_routes.id"),
        nullable=True,
    )

    slack_channel_id = db.Column(db.String(50), nullable=False)

    customer_display = db.Column(db.String(255), nullable=False)
    customer_key = db.Column(db.String(255), nullable=False, index=True)

    order_date = db.Column(db.Date, nullable=False)

    planned_delivery_at = db.Column(db.DateTime, nullable=True)

    status = db.Column(
        db.String(30),
        nullable=False,
        default="acquisito",
    )
    # acquisito | listato | controllato | evaso

    raw_text = db.Column(db.Text, nullable=True)

    slack_message_ts = db.Column(db.String(50), nullable=False)
    slack_thread_ts = db.Column(db.String(50), nullable=False)

    has_issues = db.Column(db.Boolean, default=False, nullable=False)

    closed_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    evaded_at = db.Column(db.DateTime, nullable=True, index=True)

    route = db.relationship("DeliveryRoute", backref="orders")

    __table_args__ = (
        db.Index(
            "ix_slack_orders_channel_customer_date",
            "slack_channel_id",
            "customer_key",
            "order_date",
        ),
    )


class SlackOrderEvent(db.Model):
    __tablename__ = "slack_order_events"

    id = db.Column(db.Integer, primary_key=True)

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("slack_orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    type = db.Column(
        db.String(30),
        nullable=False,
    )
    # created | append_text | status_change | note | reaction

    payload = db.Column(JSONB, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    order = db.relationship("SlackOrder", backref="events")


class OrderStatus(db.Model):
    __tablename__ = "order_statuses"

    id = db.Column(db.Integer, primary_key=True)

    # chiave tecnica stabile (usata ovunque)
    code = db.Column(db.String(32), unique=True, nullable=False)

    # label UI
    label = db.Column(db.String(64), nullable=False)

    # ordine logico / visivo
    order_index = db.Column(db.Integer, nullable=False, index=True)

    # reaction Slack associata allo stato
    slack_reaction = db.Column(db.String(64), nullable=True)

    # stato finale (es. evaso)
    is_terminal = db.Column(db.Boolean, default=False, nullable=False)

    # visibilità nel kiosk
    is_visible = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<OrderStatus {self.code}>"

class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)

    requested_ip = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)

    user = db.relationship("User", backref=db.backref("password_reset_tokens", lazy="dynamic"))

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

# ============================================================
# CASSA / AGENDA GIORNALIERA (Prima Nota) — v0 (modelli)
# ============================================================

from sqlalchemy import CheckConstraint


# --- POS: device (canale) + circuiti (many-to-many) ----------------------------

pos_device_circuits = db.Table(
    "pos_device_circuits",
    db.Column(
        "pos_device_id",
        db.Integer,
        db.ForeignKey("pos_devices.id", ondelete="CASCADE"),
        nullable=False,
    ),
    db.Column(
        "pos_circuit_id",
        db.Integer,
        db.ForeignKey("pos_circuits.id", ondelete="CASCADE"),
        nullable=False,
    ),
    db.PrimaryKeyConstraint("pos_device_id", "pos_circuit_id", name="pk_pos_device_circuits"),
)


class PosDevice(db.Model):
    __tablename__ = "pos_devices"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)  # es. "Nexi banco", "Mobile consegne"
    type = db.Column(db.String(30), nullable=False, default="physical")  # physical|mobile|paybylink|tap_to_pay|other
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)

    circuits = db.relationship(
        "PosCircuit",
        secondary=pos_device_circuits,
        backref=db.backref("devices", lazy="dynamic"),
        lazy="dynamic",
    )

    def __repr__(self):
        return f"<PosDevice {self.name}>"


class PosCircuit(db.Model):
    __tablename__ = "pos_circuits"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)  # es. Pagobancomat, Visa, Amex
    icon = db.Column(db.String(64), nullable=True)  # es. "fa-solid fa-credit-card" oppure "bi-credit-card"
    logo_path = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self):
        return f""


# --- Anagrafiche minime --------------------------------------------------------

class CashCustomer(db.Model):
    __tablename__ = "cash_customers"

    id = db.Column(db.Integer, primary_key=True)

    # nome “di comodo” (quello che mostrerai nel campo principale)
    display_name = db.Column(db.String(255), nullable=False, index=True)

    # anagrafica base (per import futuro + ricerche)
    ragione_sociale = db.Column(db.String(255), nullable=True, index=True)
    partita_iva = db.Column(db.String(32), nullable=True, index=True)
    codice_cliente = db.Column(db.String(64), nullable=True, index=True)

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )

    aliases = db.relationship(
        "CashCustomerAlias",
        backref="customer",
        cascade="all, delete-orphan",
        lazy=True,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "display_name": self.display_name,
            "ragione_sociale": self.ragione_sociale,
            "partita_iva": self.partita_iva,
            "codice_cliente": self.codice_cliente,
        }


class CashCustomerAlias(db.Model):
    __tablename__ = "cash_customer_aliases"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("cash_customers.id"), nullable=False, index=True)

    # stringa ricercabile: "davide", "armando", "bar one", ecc.
    alias = db.Column(db.String(255), nullable=False, index=True)

    # opzionale: ti servirà in futuro (person / generic / contact / ecc.)
    alias_type = db.Column(db.String(32), nullable=False, default="person")

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    __table_args__ = (
        db.UniqueConstraint("customer_id", "alias", name="uq_cash_customer_alias_customer_alias"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "alias": self.alias,
            "alias_type": self.alias_type,
        }

# --- Giornata / Chiusura -------------------------------------------------------

class CashDay(db.Model):
    __tablename__ = "cash_days"

    id = db.Column(db.Integer, primary_key=True)
    day_date = db.Column(db.Date, nullable=False, unique=True, index=True)

    opening_float = db.Column(db.Numeric(12, 2), nullable=False, default=0)  # fondo cassa iniziale
    status = db.Column(db.String(12), nullable=False, default="open")        # open|closed

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    closed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    notes = db.Column(db.Text, nullable=True)

    sales = db.relationship(
        "CashSale",
        backref="cash_day",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    expenses = db.relationship(
        "CashExpense",
        backref="cash_day",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    cash_moves = db.relationship(
        "CashMove",
        backref="cash_day",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    pos_moves = db.relationship(
        "PosMove",
        backref="cash_day",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    deposits = db.relationship(
        "CashDeposit",
        backref=db.backref("cash_day", lazy="select"),
        lazy="select",
        cascade="all, delete-orphan"
    )

    closure = db.relationship("CashClosure", backref="cash_day", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CashDay {self.day_date} {self.status}>"


class CashClosure(db.Model):
    __tablename__ = "cash_closures"
    __table_args__ = (
        db.UniqueConstraint("cash_day_id", name="uq_cash_closure_day"),
    )

    id = db.Column(db.Integer, primary_key=True)
    cash_day_id = db.Column(db.Integer, db.ForeignKey("cash_days.id", ondelete="CASCADE"), nullable=False, index=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    closed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # Contati (valori inseriti a fine giornata)
    counted_cash = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    counted_bank_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    # Nota: POS lo contiamo per device/circuit con righe dedicate (CashClosurePos)
    counted_pos_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    # Extra richiesti (es. incasso dato al titolare / versabile)
    owner_take_cash = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    depositable_cash = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    # Differenze (snapshot calcolato al momento della chiusura)
    expected_cash = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    expected_bank_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    expected_pos_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    diff_cash = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    diff_bank = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    diff_pos = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    diff_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    closing_cash_drawer = db.Column(db.Numeric(12, 2), nullable=False, default=0)  # fondo cassa lasciato nel cassetto

    anomaly_flag = db.Column(db.Boolean, nullable=False, default=False)
    anomaly_note = db.Column(db.Text, nullable=True)

    notes = db.Column(db.Text, nullable=True)

    closed_by = db.relationship("User", backref="cash_closures")

    def __repr__(self):
        return f"<CashClosure day_id={self.cash_day_id}>"


class CashClosurePos(db.Model):
    """Righe di dettaglio POS per la chiusura: totals per device + circuito."""
    __tablename__ = "cash_closure_pos"

    id = db.Column(db.Integer, primary_key=True)
    cash_closure_id = db.Column(db.Integer, db.ForeignKey("cash_closures.id", ondelete="CASCADE"), nullable=False, index=True)

    pos_device_id = db.Column(db.Integer, db.ForeignKey("pos_devices.id"), nullable=False)
    pos_circuit_id = db.Column(db.Integer, db.ForeignKey("pos_circuits.id"), nullable=False)

    counted_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    expected_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    diff_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    closure = db.relationship("CashClosure", backref=db.backref("pos_rows", cascade="all, delete-orphan", lazy="dynamic"))
    pos_device = db.relationship("PosDevice")
    pos_circuit = db.relationship("PosCircuit")

    __table_args__ = (
        db.UniqueConstraint("cash_closure_id", "pos_device_id", "pos_circuit_id", name="uq_cash_closure_pos_row"),
    )

    def __repr__(self):
        return f"<CashClosurePos closure={self.cash_closure_id} device={self.pos_device_id} circuit={self.pos_circuit_id}>"


# --- Vendite / Spese + pagamenti multipli -------------------------------------

class CashSale(db.Model):
    __tablename__ = "cash_sales"

    id = db.Column(db.Integer, primary_key=True)
    cash_day_id = db.Column(db.Integer, db.ForeignKey("cash_days.id", ondelete="CASCADE"), nullable=False, index=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # Cliente: o riferimento anagrafica, o label libero (fallback)
    customer_id = db.Column(db.Integer, db.ForeignKey("cash_customers.id"), nullable=True)
    customer_label = db.Column(db.String(120), nullable=True)

    # Per estensioni future (scontrino/fattura)
    doc_ref = db.Column(db.String(80), nullable=True)

    notes = db.Column(db.Text, nullable=True)

    created_by = db.relationship("User", backref="cash_sales")
    customer = db.relationship("CashCustomer")

    payments = db.relationship(
        "CashSalePayment",
        backref="sale",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    checks = db.relationship(
        "CashSaleCheck",
        back_populates="sale",
        lazy="select",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<CashSale id={self.id} day={self.cash_day_id}>"


# --- Vendite / Spese + pagamenti multipli -------------------------------------

class CashSalePayment(db.Model):
    __tablename__ = "cash_sale_payments"
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("cash_sales.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    direction = db.Column(db.String(3), nullable=False, default="in")  # in|out
    method = db.Column(db.String(12), nullable=False)                 # cash|pos|bank|other
    off_cash = db.Column(db.Boolean, nullable=False, default=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)

    # FLAG AGENDA: *, **, +, x, #, !
    flag = db.Column(db.String(2), nullable=False, default="*")

    pos_device_id = db.Column(db.Integer, db.ForeignKey("pos_devices.id"), nullable=True)
    pos_circuit_id = db.Column(db.Integer, db.ForeignKey("pos_circuits.id"), nullable=True)
    description = db.Column(db.String(255), nullable=True)

    pos_device = db.relationship("PosDevice")
    pos_circuit = db.relationship("PosCircuit")

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_cash_sale_payment_amount_nonneg"),
        CheckConstraint("direction IN ('in','out')", name="ck_cash_sale_payment_direction"),
        CheckConstraint(
            "(method <> 'pos') OR (pos_device_id IS NOT NULL AND pos_circuit_id IS NOT NULL)",
            name="ck_cash_sale_payment_pos_requires_device_circuit",
        ),
        CheckConstraint(
            "flag IN ('*','**','+','x','#','!')",
            name="ck_cash_sale_payment_flag",
        ),
    )


class CashExpensePayment(db.Model):
    __tablename__ = "cash_expense_payments"
    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey("cash_expenses.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    direction = db.Column(db.String(3), nullable=False, default="out")  # in|out
    method = db.Column(db.String(12), nullable=False)                  # cash|pos|bank|other
    off_cash = db.Column(db.Boolean, nullable=False, default=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)

    # FLAG AGENDA: *, **, +, x, #, !
    flag = db.Column(db.String(2), nullable=False, default="*")

    pos_device_id = db.Column(db.Integer, db.ForeignKey("pos_devices.id"), nullable=True)
    pos_circuit_id = db.Column(db.Integer, db.ForeignKey("pos_circuits.id"), nullable=True)
    description = db.Column(db.String(255), nullable=True)

    pos_device = db.relationship("PosDevice")
    pos_circuit = db.relationship("PosCircuit")

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_cash_expense_payment_amount_nonneg"),
        CheckConstraint("direction IN ('in','out')", name="ck_cash_expense_payment_direction"),
        CheckConstraint(
            "(method <> 'pos') OR (pos_device_id IS NOT NULL AND pos_circuit_id IS NOT NULL)",
            name="ck_cash_expense_payment_pos_requires_device_circuit",
        ),
        CheckConstraint(
            "flag IN ('*','**','+','x','#','!')",
            name="ck_cash_expense_payment_flag",
        ),
    )


class CashMove(db.Model):
    __tablename__ = "cash_moves"
    id = db.Column(db.Integer, primary_key=True)
    cash_day_id = db.Column(db.Integer, db.ForeignKey("cash_days.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    direction = db.Column(db.String(3), nullable=False)  # in|out
    kind = db.Column(db.String(30), nullable=False, default="altro")
    amount = db.Column(db.Numeric(12, 2), nullable=False)

    # opzionale (se vuoi usarlo per movimenti privati di cassa)
    flag = db.Column(db.String(2), nullable=True)

    performed_by = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    created_by = db.relationship("User", backref="cash_moves")

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_cash_move_amount_nonneg"),
        CheckConstraint("direction IN ('in','out')", name="ck_cash_move_direction"),
        CheckConstraint(
            "flag IS NULL OR flag IN ('*','**','+','x','#','!')",
            name="ck_cash_move_flag",
        ),
    )


class PosMove(db.Model):
    __tablename__ = "pos_moves"
    id = db.Column(db.Integer, primary_key=True)
    cash_day_id = db.Column(db.Integer, db.ForeignKey("cash_days.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    direction = db.Column(db.String(3), nullable=False, default="in")
    amount = db.Column(db.Numeric(12, 2), nullable=False)

    # opzionale (ma utile per distinguere # / * ecc. su POS standalone)
    flag = db.Column(db.String(2), nullable=True)

    pos_device_id = db.Column(db.Integer, db.ForeignKey("pos_devices.id"), nullable=False)
    pos_circuit_id = db.Column(db.Integer, db.ForeignKey("pos_circuits.id"), nullable=False)

    doc_ref = db.Column(db.String(80), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    created_by = db.relationship("User", backref="pos_moves")
    pos_device = db.relationship("PosDevice")
    pos_circuit = db.relationship("PosCircuit")

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_pos_move_amount_nonneg"),
        CheckConstraint("direction IN ('in','out')", name="ck_pos_move_direction"),
        CheckConstraint(
            "flag IS NULL OR flag IN ('*','**','+','x','#','!')",
            name="ck_pos_move_flag",
        ),
    )


class CashExpense(db.Model):
    __tablename__ = "cash_expenses"

    id = db.Column(db.Integer, primary_key=True)
    cash_day_id = db.Column(db.Integer, db.ForeignKey("cash_days.id", ondelete="CASCADE"), nullable=False, index=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    supplier = db.Column(db.String(160), nullable=True)  # fornitore/beneficiario (testo libero)
    category = db.Column(db.String(80), nullable=True)   # es. "spesa minuta", "fornitori"
    doc_ref = db.Column(db.String(80), nullable=True)    # fattura/scontrino

    notes = db.Column(db.Text, nullable=True)

    created_by = db.relationship("User", backref="cash_expenses")

    payments = db.relationship(
        "CashExpensePayment",
        backref="expense",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self):
        return f"<CashExpense id={self.id} day={self.cash_day_id}>"


class CashCheck(db.Model):
    __tablename__ = "cash_checks"

    __table_args__ = (
        db.UniqueConstraint("bank_name", "check_number", name="uq_check_bank_number"),
    )

    id = db.Column(db.Integer, primary_key=True)

    check_number = db.Column(db.String(64), nullable=False, index=True)

    # Dati banca emittente
    abi = db.Column(db.String(5), nullable=True, index=True)
    cab = db.Column(db.String(5), nullable=True, index=True)
    bank_name = db.Column(db.String(120), nullable=True)

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_customers.id"),
        nullable=False,
        index=True
    )

    amount = db.Column(db.Numeric(12, 2), nullable=False)

    received_date = db.Column(db.Date, nullable=False, default=date.today)
    due_date = db.Column(db.Date, nullable=False)

    status = db.Column(
        db.String(20),
        nullable=False,
        default="received",
        index=True
    )

    note = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    customer = db.relationship(
        "CashCustomer",
        backref=db.backref("checks", lazy="select")
    )

    sales = db.relationship(
        "CashSaleCheck",
        back_populates="check",
        lazy="select",
        cascade="all, delete-orphan",
    )


class CashDeposit(db.Model):
    __tablename__ = "cash_deposits"

    id = db.Column(db.Integer, primary_key=True)

    cash_day_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_days.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Data del versamento (può coincidere con la day_date, ma può anche esserci più di un versamento al giorno)
    deposit_date = db.Column(db.Date, nullable=False, default=date.today, index=True)

    # Tipi: "versamento_incasso" | "versamento_intermedio"
    deposit_type = db.Column(db.String(32), nullable=False, default="versamento_incasso", index=True)

    # Contanti versati in questo versamento (gli assegni sono gestiti via tabella ponte)
    cash_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    note = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    # righe assegni (tabella ponte)
    checks = db.relationship(
        "CashDepositCheck",
        back_populates="deposit",
        lazy="select",
        cascade="all, delete-orphan"
    )


class CashDepositCheck(db.Model):
    __tablename__ = "cash_deposit_checks"

    __table_args__ = (
        db.UniqueConstraint("deposit_id", "check_id", name="uq_deposit_check"),
    )

    id = db.Column(db.Integer, primary_key=True)

    deposit_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_deposits.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    check_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_checks.id"),
        nullable=False,
        index=True
    )

    # snapshot opzionale (utile se vuoi vedere "quanto" senza joinare)
    check_amount = db.Column(db.Numeric(12, 2), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    deposit = db.relationship("CashDeposit", back_populates="checks")
    check = db.relationship("CashCheck", lazy="select")


# --- Ponte Incassi ↔ Assegni -------------------------------------------------

class CashSaleCheck(db.Model):
    __tablename__ = "cash_sale_checks"
    __table_args__ = (
        db.UniqueConstraint("sale_id", "check_id", name="uq_sale_check"),
    )

    id = db.Column(db.Integer, primary_key=True)

    sale_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_sales.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    check_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_checks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # snapshot opzionale (coerente con CashDepositCheck)
    check_amount = db.Column(db.Numeric(12, 2), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    sale = db.relationship("CashSale", back_populates="checks")
    check = db.relationship("CashCheck", back_populates="sales")
