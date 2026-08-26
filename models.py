import hashlib
import secrets

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
    is_visible = db.Column(db.Boolean, nullable=False, default=True)
    item_type = db.Column(db.String(20), nullable=False, default='link')
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
            'is_visible': self.is_visible,
            'item_type': self.item_type,
            'parent': self.parent.name if self.parent else None,
        }

    def __repr__(self):
        return f"<Menu {self.name}>"


class AppPreference(db.Model):
    __tablename__ = "app_preferences"
    __table_args__ = (
        db.UniqueConstraint("key", name="uq_app_preferences_key"),
        db.Index("ix_app_preferences_category_sort", "category", "sort_order"),
    )

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80), nullable=False, default="Generale")
    label = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)
    value_type = db.Column(db.String(20), nullable=False, default="text")
    value_text = db.Column(db.Text, nullable=True)
    value_json = db.Column(JSONB, nullable=True)
    secret_value = db.Column(EncryptedString(4096), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<AppPreference {self.key}>"

    @property
    def is_secret(self):
        return (self.value_type or "text") == "secret"

    def python_value(self):
        value_type = (self.value_type or "text").lower()
        if value_type == "secret":
            return self.secret_value
        if value_type == "bool":
            return str(self.value_text or "").strip().lower() in {"1", "true", "yes", "on"}
        if value_type == "int":
            if self.value_text in (None, ""):
                return None
            return int(self.value_text)
        if value_type == "float":
            if self.value_text in (None, ""):
                return None
            return float(self.value_text)
        if value_type == "json":
            return self.value_json
        return self.value_text

    def form_value(self):
        if self.is_secret:
            return ""
        value = self.python_value()
        if value is None:
            return ""
        if isinstance(value, bool):
            return "1" if value else "0"
        return value


class AppVisitor(db.Model):
    __tablename__ = "app_visitors"
    __table_args__ = (
        db.UniqueConstraint("visitor_hash", name="uq_app_visitors_visitor_hash"),
        db.Index("ix_app_visitors_last_seen", "last_seen"),
    )

    id = db.Column(db.Integer, primary_key=True)
    visitor_hash = db.Column(db.String(64), nullable=False)
    first_seen = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    visit_count = db.Column(db.BigInteger, nullable=False, default=1)


class EmailAccount(db.Model):
    __tablename__ = "email_accounts"
    __table_args__ = (
        db.UniqueConstraint("code", name="uq_email_accounts_code"),
        db.Index("ix_email_accounts_enabled", "is_enabled"),
    )

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    smtp_server = db.Column(db.String(255), nullable=False)
    smtp_port = db.Column(db.Integer, nullable=False, default=25)
    use_tls = db.Column(db.Boolean, nullable=False, default=False)
    use_ssl = db.Column(db.Boolean, nullable=False, default=False)
    username = db.Column(db.String(255), nullable=False)
    password_encrypted = db.Column(EncryptedString(2048), nullable=True)
    default_sender = db.Column(db.String(255), nullable=False)
    imap_server = db.Column(db.String(255), nullable=True)
    imap_port = db.Column(db.Integer, nullable=False, default=993)
    imap_use_tls = db.Column(db.Boolean, nullable=False, default=False)
    imap_use_ssl = db.Column(db.Boolean, nullable=False, default=True)
    imap_username = db.Column(db.String(255), nullable=True)
    imap_password_encrypted = db.Column(EncryptedString(2048), nullable=True)
    imap_folder = db.Column(db.String(120), nullable=False, default="INBOX")
    imap_enabled = db.Column(db.Boolean, nullable=False, default=False)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    is_system = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "smtp_server": self.smtp_server,
            "smtp_port": self.smtp_port,
            "use_tls": bool(self.use_tls),
            "use_ssl": bool(self.use_ssl),
            "username": self.username,
            "default_sender": self.default_sender,
            "has_password": bool(self.password_encrypted),
            "imap_server": self.imap_server,
            "imap_port": self.imap_port,
            "imap_use_tls": bool(self.imap_use_tls),
            "imap_use_ssl": bool(self.imap_use_ssl),
            "imap_username": self.imap_username,
            "has_imap_password": bool(self.imap_password_encrypted),
            "imap_folder": self.imap_folder,
            "imap_enabled": bool(self.imap_enabled),
            "is_enabled": bool(self.is_enabled),
            "is_system": bool(self.is_system),
        }


class MailingSubscriber(db.Model):
    __tablename__ = "mailing_subscribers"
    __table_args__ = (db.UniqueConstraint("email_normalized", name="uq_mailing_subscribers_email"),)
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    email_normalized = db.Column(db.String(255), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="subscribed", index=True)
    source = db.Column(db.String(40), nullable=False, default="manual")
    consent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    unsubscribed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    unsubscribe_token = db.Column(db.String(64), nullable=False, unique=True, default=lambda: secrets.token_urlsafe(32))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MailingList(db.Model):
    __tablename__ = "mailing_lists"
    __table_args__ = (db.UniqueConstraint("name", name="uq_mailing_lists_name"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    source_type = db.Column(db.String(30), nullable=False, default="manual", index=True)
    filter_config = db.Column(db.JSON, nullable=False, default=dict)
    is_system = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    members = db.relationship(
        "MailingListMember",
        back_populates="mailing_list",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class MailingListMember(db.Model):
    __tablename__ = "mailing_list_members"
    __table_args__ = (
        db.UniqueConstraint("mailing_list_id", "subscriber_id", name="uq_mailing_list_member"),
        db.Index("ix_mailing_list_members_list_active", "mailing_list_id", "is_active"),
    )

    id = db.Column(db.Integer, primary_key=True)
    mailing_list_id = db.Column(
        db.Integer,
        db.ForeignKey("mailing_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscriber_id = db.Column(
        db.Integer,
        db.ForeignKey("mailing_subscribers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type = db.Column(db.String(30), nullable=False, default="manual")
    source_entity_id = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    mailing_list = db.relationship("MailingList", back_populates="members")
    subscriber = db.relationship("MailingSubscriber", backref=db.backref("list_memberships", lazy="selectin"))


class MailingTemplate(db.Model):
    __tablename__ = "mailing_templates"
    __table_args__ = (db.UniqueConstraint("name", name="uq_mailing_templates_name"),)

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    html_body = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    created_by = db.relationship("User", backref="mailing_templates")


class MailingCampaign(db.Model):
    __tablename__ = "mailing_campaigns"
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(255), nullable=False)
    html_body = db.Column(db.Text, nullable=False)
    account_code = db.Column(db.String(50), nullable=False, default="general")
    mailing_list_id = db.Column(db.Integer, db.ForeignKey("mailing_lists.id"), nullable=True, index=True)
    template_id = db.Column(
        db.Integer,
        db.ForeignKey("mailing_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    recipient_count = db.Column(db.Integer, nullable=False, default=0)
    sent_count = db.Column(db.Integer, nullable=False, default=0)
    failed_count = db.Column(db.Integer, nullable=False, default=0)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_by = db.relationship("User", backref="mailing_campaigns")
    mailing_list = db.relationship("MailingList", backref="campaigns")
    template = db.relationship("MailingTemplate", backref="campaigns")


class MailingCampaignAttachment(db.Model):
    __tablename__ = "mailing_campaign_attachments"
    __table_args__ = (
        db.UniqueConstraint("storage_path", name="uq_mailing_campaign_attachments_storage_path"),
        db.CheckConstraint("file_size > 0", name="ck_mailing_campaign_attachment_size"),
    )

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("mailing_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename = db.Column(db.String(255), nullable=False)
    storage_path = db.Column(db.String(500), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    file_size = db.Column(db.BigInteger, nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    campaign = db.relationship(
        "MailingCampaign",
        backref=db.backref("attachments", cascade="all, delete-orphan", lazy="selectin"),
    )
    created_by = db.relationship("User", backref="mailing_campaign_attachments")


class MailingCampaignSchedule(db.Model):
    __tablename__ = "mailing_campaign_schedules"
    __table_args__ = (
        db.UniqueConstraint("campaign_id", name="uq_mailing_campaign_schedules_campaign"),
        db.Index("ix_mailing_campaign_schedules_due", "status", "next_run_at"),
        db.CheckConstraint(
            "mode IN ('single', 'periodic', 'multiple', 'until')",
            name="ck_mailing_campaign_schedule_mode",
        ),
        db.CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'completed', 'cancelled')",
            name="ck_mailing_campaign_schedule_status",
        ),
        db.CheckConstraint(
            "interval_unit IS NULL OR interval_unit IN ('day', 'week', 'month')",
            name="ck_mailing_campaign_schedule_interval_unit",
        ),
        db.CheckConstraint(
            "interval_value IS NULL OR interval_value > 0",
            name="ck_mailing_campaign_schedule_interval_value",
        ),
        db.CheckConstraint(
            "max_runs IS NULL OR max_runs > 0",
            name="ck_mailing_campaign_schedule_max_runs",
        ),
        db.CheckConstraint(
            "completed_runs >= 0",
            name="ck_mailing_campaign_schedule_completed_runs",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("mailing_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mode = db.Column(db.String(20), nullable=False, default="single")
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    starts_at = db.Column(db.DateTime(timezone=True), nullable=False)
    interval_value = db.Column(db.Integer, nullable=True)
    interval_unit = db.Column(db.String(12), nullable=True)
    ends_at = db.Column(db.DateTime(timezone=True), nullable=True)
    max_runs = db.Column(db.Integer, nullable=True)
    completed_runs = db.Column(db.Integer, nullable=False, default=0)
    next_run_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    last_run_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    campaign = db.relationship(
        "MailingCampaign",
        backref=db.backref("schedule", uselist=False, cascade="all, delete-orphan"),
    )


class MailingCampaignRun(db.Model):
    __tablename__ = "mailing_campaign_runs"
    __table_args__ = (
        db.UniqueConstraint("campaign_id", "run_number", name="uq_mailing_campaign_run_number"),
        db.Index("ix_mailing_campaign_runs_campaign_status", "campaign_id", "status"),
        db.CheckConstraint("run_number > 0", name="ck_mailing_campaign_run_number"),
        db.CheckConstraint(
            "trigger_type IN ('manual', 'scheduled', 'legacy')",
            name="ck_mailing_campaign_run_trigger",
        ),
        db.CheckConstraint(
            "status IN ('pending', 'queued', 'sending', 'sent', 'failed', 'cancelled')",
            name="ck_mailing_campaign_run_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(
        db.Integer,
        db.ForeignKey("mailing_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_number = db.Column(db.Integer, nullable=False)
    trigger_type = db.Column(db.String(20), nullable=False, default="manual")
    scheduled_for = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    recipient_count = db.Column(db.Integer, nullable=False, default=0)
    sent_count = db.Column(db.Integer, nullable=False, default=0)
    failed_count = db.Column(db.Integer, nullable=False, default=0)
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    campaign = db.relationship(
        "MailingCampaign",
        backref=db.backref("runs", cascade="all, delete-orphan", lazy="selectin"),
    )


class MailingDelivery(db.Model):
    __tablename__ = "mailing_deliveries"
    __table_args__ = (
        db.UniqueConstraint("run_id", "subscriber_id", name="uq_mailing_delivery_run_recipient"),
    )
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("mailing_campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = db.Column(
        db.Integer,
        db.ForeignKey("mailing_campaign_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    subscriber_id = db.Column(db.Integer, db.ForeignKey("mailing_subscribers.id", ondelete="CASCADE"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    error_message = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    campaign = db.relationship("MailingCampaign", backref=db.backref("deliveries", cascade="all, delete-orphan"))
    run = db.relationship(
        "MailingCampaignRun",
        backref=db.backref("deliveries", cascade="all, delete-orphan"),
    )
    subscriber = db.relationship("MailingSubscriber")


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


class WineCard(db.Model):
    __tablename__ = "wine_cards"
    __table_args__ = (
        db.Index("ix_wine_cards_customer_status", "customer_registry_id", "status"),
        db.Index("ix_wine_cards_title", "title"),
    )

    id = db.Column(db.Integer, primary_key=True)
    customer_registry_id = db.Column(
        db.Integer,
        db.ForeignKey("business_registries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    template_id = db.Column(
        db.Integer,
        db.ForeignKey("wine_card_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_card_id = db.Column(
        db.Integer,
        db.ForeignKey("wine_cards.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)

    title = db.Column(db.String(180), nullable=False)
    venue_name = db.Column(db.String(180), nullable=True)
    subtitle = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(24), nullable=False, default="draft", index=True)

    customer_view_enabled = db.Column(db.Boolean, nullable=False, default=False, index=True)
    customer_view_token = db.Column(db.String(64), nullable=True, unique=True, index=True)
    layout_config = db.Column(JSONB, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    customer = db.relationship("BusinessRegistry", backref=db.backref("wine_cards", lazy="selectin"))
    template = db.relationship("WineCardTemplate")
    source_card = db.relationship("WineCard", remote_side=[id])
    created_by = db.relationship("User")
    items = db.relationship(
        "WineCardItem",
        back_populates="card",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="WineCardItem.sort_order.asc()",
    )
    sections = db.relationship(
        "WineCardSection",
        back_populates="card",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="WineCardSection.sort_order.asc()",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "customer_registry_id": self.customer_registry_id,
            "template_id": self.template_id,
            "source_card_id": self.source_card_id,
            "title": self.title,
            "venue_name": self.venue_name,
            "subtitle": self.subtitle,
            "status": self.status,
            "customer_view_enabled": self.customer_view_enabled,
            "customer_view_token": self.customer_view_token,
            "layout_config": self.layout_config or {},
            "items_count": len(self.items or []),
        }


class WineCardTemplate(db.Model):
    __tablename__ = "wine_card_templates"
    __table_args__ = (
        db.Index("ix_wine_card_templates_active_order", "is_active", "sort_order"),
    )

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    layout_config = db.Column(JSONB, nullable=False, default=dict)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "layout_config": self.layout_config or {},
            "is_active": self.is_active,
            "sort_order": self.sort_order,
        }


class WineCardSection(db.Model):
    __tablename__ = "wine_card_sections"
    __table_args__ = (
        db.UniqueConstraint("card_id", "code", name="uq_wine_card_section_card_code"),
        db.Index("ix_wine_card_sections_card_visible_order", "card_id", "is_visible", "sort_order"),
    )

    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, db.ForeignKey("wine_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    code = db.Column(db.String(80), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_visible = db.Column(db.Boolean, nullable=False, default=True, index=True)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    card = db.relationship("WineCard", back_populates="sections")
    items = db.relationship(
        "WineCardItem",
        back_populates="section",
        lazy="selectin",
        order_by="WineCardItem.sort_order.asc()",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "card_id": self.card_id,
            "code": self.code,
            "title": self.title,
            "sort_order": self.sort_order,
            "is_visible": self.is_visible,
            "notes": self.notes,
        }


class WineCardItem(db.Model):
    __tablename__ = "wine_card_items"
    __table_args__ = (
        db.UniqueConstraint("card_id", "cod_art", name="uq_wine_card_item_card_cod_art"),
        db.Index("ix_wine_card_items_card_category", "card_id", "category"),
    )

    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, db.ForeignKey("wine_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    section_id = db.Column(db.Integer, db.ForeignKey("wine_card_sections.id", ondelete="SET NULL"), nullable=True, index=True)
    cod_art = db.Column(db.String(255), db.ForeignKey("articoli.cod_art", ondelete="SET NULL"), nullable=True, index=True)

    sort_order = db.Column(db.Integer, nullable=False, default=0)
    category = db.Column(db.String(120), nullable=True, index=True)
    display_description = db.Column(db.String(255), nullable=False)
    winery = db.Column(db.String(180), nullable=True)
    region = db.Column(db.String(120), nullable=True)
    sale_price = db.Column(db.Numeric(10, 2), nullable=True)
    is_visible = db.Column(db.Boolean, nullable=False, default=True, index=True)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    card = db.relationship("WineCard", back_populates="items")
    section = db.relationship("WineCardSection", back_populates="items")
    article = db.relationship("Articoli")

    def to_dict(self):
        return {
            "id": self.id,
            "card_id": self.card_id,
            "section_id": self.section_id,
            "cod_art": self.cod_art,
            "sort_order": self.sort_order,
            "category": self.category,
            "display_description": self.display_description,
            "winery": self.winery,
            "region": self.region,
            "sale_price": float(self.sale_price) if self.sale_price is not None else None,
            "is_visible": self.is_visible,
            "notes": self.notes,
        }


class Barcode(db.Model):
    __tablename__ = "barcode"

    id = db.Column(
        db.BigInteger,
        primary_key=True,
        autoincrement=True,
        server_default=db.text("nextval('barcode_id_seq'::regclass)")
    )

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
    descrizione = db.Column(db.Text, nullable=True)
    short = db.Column(db.Text, nullable=True)
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


class ProductPlatformLink(db.Model):
    __tablename__ = "product_platform_links"
    __table_args__ = (
        db.UniqueConstraint("cod_art", "platform", name="uq_product_platform_links_cod_art_platform"),
        db.Index("ix_product_platform_links_platform_status", "platform", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    cod_art = db.Column(db.String(255), db.ForeignKey("articoli.cod_art", ondelete="CASCADE"), nullable=False, index=True)
    id_art = db.Column(db.BigInteger, db.ForeignKey("articoli.id_art"), nullable=True, index=True)
    platform = db.Column(db.String(40), nullable=False, index=True)
    external_id = db.Column(db.String(255), nullable=True, index=True)
    external_url = db.Column(db.String(1000), nullable=True)
    status = db.Column(db.String(40), nullable=False, default="present", index=True)
    last_sync_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    raw_payload = db.Column(JSONB, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    articolo = db.relationship("Articoli", foreign_keys=[cod_art], backref="platform_links")

    def to_dict(self):
        return {
            "id": self.id,
            "cod_art": self.cod_art,
            "platform": self.platform,
            "external_id": self.external_id,
            "external_url": self.external_url,
            "status": self.status,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_error": self.last_error,
        }


class ProductAsset(db.Model):
    __tablename__ = "product_assets"
    __table_args__ = (
        db.UniqueConstraint(
            "cod_art",
            "asset_type",
            "source_platform",
            "local_path",
            "remote_url",
            name="uq_product_assets_source",
        ),
        db.Index("ix_product_assets_cod_art_type", "cod_art", "asset_type"),
        db.Index("ix_product_assets_source_platform", "source_platform"),
    )

    id = db.Column(db.Integer, primary_key=True)
    cod_art = db.Column(db.String(255), db.ForeignKey("articoli.cod_art", ondelete="CASCADE"), nullable=False, index=True)
    id_art = db.Column(db.BigInteger, db.ForeignKey("articoli.id_art"), nullable=True, index=True)
    asset_type = db.Column(db.String(40), nullable=False, default="image")
    source_platform = db.Column(db.String(40), nullable=False, default="manual", index=True)
    source_external_id = db.Column(db.String(255), nullable=True)
    local_path = db.Column(db.String(1000), nullable=True)
    remote_url = db.Column(db.String(1000), nullable=True)
    original_filename = db.Column(db.String(255), nullable=True)
    content_hash = db.Column(db.String(128), nullable=True, index=True)
    mime_type = db.Column(db.String(120), nullable=True)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    metadata_json = db.Column(JSONB, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    articolo = db.relationship("Articoli", foreign_keys=[cod_art], backref="assets")

    def to_dict(self):
        return {
            "id": self.id,
            "cod_art": self.cod_art,
            "asset_type": self.asset_type,
            "source_platform": self.source_platform,
            "source_external_id": self.source_external_id,
            "local_path": self.local_path,
            "remote_url": self.remote_url,
            "original_filename": self.original_filename,
            "is_primary": self.is_primary,
            "sort_order": self.sort_order,
        }


class ProductPlatformField(db.Model):
    __tablename__ = "product_platform_fields"
    __table_args__ = (
        db.UniqueConstraint(
            "cod_art",
            "platform",
            "field_name",
            "language",
            name="uq_product_platform_fields_value",
        ),
        db.Index("ix_product_platform_fields_cod_art_platform", "cod_art", "platform"),
    )

    id = db.Column(db.Integer, primary_key=True)
    cod_art = db.Column(db.String(255), db.ForeignKey("articoli.cod_art", ondelete="CASCADE"), nullable=False, index=True)
    id_art = db.Column(db.BigInteger, db.ForeignKey("articoli.id_art"), nullable=True, index=True)
    platform = db.Column(db.String(40), nullable=False, index=True)
    field_name = db.Column(db.String(80), nullable=False)
    language = db.Column(db.String(10), nullable=False, default="")
    value_text = db.Column(db.Text, nullable=True)
    value_json = db.Column(JSONB, nullable=True)
    source_external_id = db.Column(db.String(255), nullable=True)
    last_sync_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    articolo = db.relationship("Articoli", foreign_keys=[cod_art], backref="platform_fields")

    def to_dict(self):
        return {
            "id": self.id,
            "cod_art": self.cod_art,
            "platform": self.platform,
            "field_name": self.field_name,
            "language": self.language,
            "value_text": self.value_text,
            "source_external_id": self.source_external_id,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
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
    customer_registry_id = db.Column(db.Integer, db.ForeignKey("business_registries.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.now())
    updated_at = db.Column(db.DateTime, default=datetime.now(), onupdate=datetime.now())

    # RIMOSSI role_id e role
    # role_id = ...
    # role = ...

    roles = db.relationship('UserRole', backref='user', lazy=True)
    customer_registry = db.relationship("BusinessRegistry", foreign_keys=[customer_registry_id])
    customer_memberships = db.relationship(
        "CustomerRegistryMembership",
        foreign_keys="CustomerRegistryMembership.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )

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
                    (ur.valid_from is None or ur.valid_from <= now)
                    and (ur.valid_until is None or ur.valid_until >= now)
            )
        ]

    def has_active_role(self, *role_names):
        allowed = {str(name).strip().lower() for name in role_names if name}
        return any(str(role.name).strip().lower() in allowed for role in self.active_roles or [])

    @property
    def max_role_weight(self):
        """Restituisce il peso massimo dei ruoli attivi dell’utente."""
        active = self.active_roles
        if not active:
            return 0
        return max(role.weight for role in active)

    def get_id(self):
        return str(self.id)


class Event(db.Model):
    __tablename__ = "events"
    __table_args__ = (
        db.Index("ix_events_published_starts_at", "is_published", "starts_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    starts_at = db.Column(db.DateTime(timezone=True), nullable=False)
    ends_at = db.Column(db.DateTime(timezone=True), nullable=True)
    starts_time_known = db.Column(db.Boolean, nullable=False, default=True)
    ends_time_known = db.Column(db.Boolean, nullable=False, default=False)
    location = db.Column(db.String(180), nullable=True)
    summary = db.Column(db.Text, nullable=True)
    details = db.Column(db.Text, nullable=True)
    contact_info = db.Column(db.String(180), nullable=True)
    poster_path = db.Column(db.String(255), nullable=True)
    is_published = db.Column(db.Boolean, nullable=False, default=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    created_by = db.relationship("User", backref="created_events")
    posters = db.relationship(
        "EventPoster",
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="EventPoster.sort_order.asc(), EventPoster.id.asc()",
    )

    @property
    def display_date(self):
        return self.starts_at.strftime("%d/%m/%Y")

    @property
    def display_time(self):
        return self.starts_at.strftime("%H:%M") if self.starts_time_known else ""


class EventPoster(db.Model):
    __tablename__ = "event_posters"
    __table_args__ = (
        db.Index("ix_event_posters_event_sort", "event_id", "sort_order"),
    )

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = db.Column(db.String(255), nullable=False)
    media_type = db.Column(db.String(20), nullable=False, default="image")
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    event = db.relationship("Event", back_populates="posters")


class SocialEventPost(db.Model):
    __tablename__ = "social_event_posts"
    __table_args__ = (
        db.Index("ix_social_event_posts_kind_period", "kind", "period_start", "period_end"),
        db.Index("ix_social_event_posts_status", "status"),
        db.Index("ix_social_event_posts_created_at", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    caption = db.Column(db.Text, nullable=False)
    public_url = db.Column(db.String(500), nullable=False)
    destinations = db.Column(JSONB, nullable=False, default=list)
    status = db.Column(db.String(40), nullable=False, default="draft")
    status_message = db.Column(db.Text, nullable=True)
    payload = db.Column(JSONB, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    published_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_by = db.relationship("User", backref="created_social_event_posts")


class SupplierOrderGroup(db.Model):
    __tablename__ = "supplier_order_groups"
    __table_args__ = (
        db.UniqueConstraint("name", name="uq_supplier_order_groups_name"),
        db.Index("ix_supplier_order_groups_active_name", "is_active", "name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    created_by = db.relationship("User", backref="supplier_order_groups")
    items = db.relationship(
        "SupplierOrderGroupItem",
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="SupplierOrderGroupItem.sort_order.asc(), SupplierOrderGroupItem.id.asc()",
    )

    def __repr__(self):
        return f"<SupplierOrderGroup {self.name}>"


class SupplierOrderGroupItem(db.Model):
    __tablename__ = "supplier_order_group_items"
    __table_args__ = (
        db.UniqueConstraint("group_id", "cod_art", name="uq_supplier_order_group_items_group_cod_art"),
        db.Index("ix_supplier_order_group_items_group_sort", "group_id", "sort_order"),
        db.Index("ix_supplier_order_group_items_cod_art", "cod_art"),
    )

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("supplier_order_groups.id", ondelete="CASCADE"), nullable=False)
    cod_art = db.Column(db.String(255), db.ForeignKey("articoli.cod_art", ondelete="CASCADE"), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    group = db.relationship("SupplierOrderGroup", back_populates="items")
    article = db.relationship("Articoli", foreign_keys=[cod_art])

    def __repr__(self):
        return f"<SupplierOrderGroupItem {self.group_id}:{self.cod_art}>"


class SupplierOrderMatrixName(db.Model):
    __tablename__ = "supplier_order_matrix_names"
    __table_args__ = (
        db.UniqueConstraint("group_id", "matrix_code", name="uq_supplier_order_matrix_names_group_matrix"),
        db.Index("ix_supplier_order_matrix_names_group", "group_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("supplier_order_groups.id", ondelete="CASCADE"), nullable=False)
    matrix_code = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    group = db.relationship("SupplierOrderGroup", backref=db.backref("matrix_names", cascade="all, delete-orphan"))


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
        now = datetime.now()

        if self.type == "lifetime":
            return True

        if self.type == "until":
            return self.valid_until is None or now <= self.valid_until

        if self.type == "period":
            start_ok = now >= self.valid_from
            end_ok = self.valid_until is None or now <= self.valid_until
            return start_ok and end_ok

        return False


class RoleActivationRequest(db.Model):
    __tablename__ = "role_activation_requests"
    __table_args__ = (
        db.Index("ix_role_activation_requests_status_created", "status", "created_at"),
        db.Index("ix_role_activation_requests_user_status", "user_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_role = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="pending")
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("role_activation_requests", lazy=True, cascade="all, delete-orphan"))
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_user_id])


class SupportTicket(db.Model):
    __tablename__ = "support_tickets"
    __table_args__ = (
        db.Index("ix_support_tickets_type_status_created", "ticket_type", "status", "created_at"),
        db.Index("ix_support_tickets_user_status", "user_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    ticket_type = db.Column(db.String(40), nullable=False, default="support")
    status = db.Column(db.String(40), nullable=False, default="open")
    subject = db.Column(db.String(220), nullable=False)
    reply_email = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    role_activation_request_id = db.Column(
        db.Integer,
        db.ForeignKey("role_activation_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_to_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    public_token = db.Column(db.String(64), nullable=False, unique=True, index=True, default=lambda: secrets.token_urlsafe(32))
    closed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("support_tickets", lazy=True))
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_user_id])
    role_activation_request = db.relationship("RoleActivationRequest", backref=db.backref("support_ticket", uselist=False))
    messages = db.relationship(
        "SupportTicketMessage",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="SupportTicketMessage.created_at.asc(), SupportTicketMessage.id.asc()",
    )


class SupportTicketMessage(db.Model):
    __tablename__ = "support_ticket_messages"
    __table_args__ = (
        db.Index("ix_support_ticket_messages_ticket_created", "ticket_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_type = db.Column(db.String(30), nullable=False, default="user")
    sender_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    source = db.Column(db.String(30), nullable=False, default="web")
    external_message_id = db.Column(db.String(500), nullable=True, unique=True, index=True)
    in_reply_to = db.Column(db.String(500), nullable=True, index=True)
    body = db.Column(db.Text, nullable=False)
    email_from = db.Column(db.String(255), nullable=True)
    email_to = db.Column(db.String(255), nullable=True)
    read_by_user_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    read_by_support_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    ticket = db.relationship("SupportTicket", back_populates="messages")
    sender_user = db.relationship("User", foreign_keys=[sender_user_id])
    attachments = db.relationship(
        "SupportTicketAttachment",
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="SupportTicketAttachment.id.asc()",
    )


class SupportTicketAttachment(db.Model):
    __tablename__ = "support_ticket_attachments"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey("support_ticket_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = db.Column(db.String(500), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(120), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    message = db.relationship("SupportTicketMessage", back_populates="attachments")


class SpecialPermission(db.Model):
    __tablename__ = "special_permissions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), nullable=False, unique=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    assignments = db.relationship("UserSpecialPermission", backref="permission", lazy=True)


class UserSpecialPermission(db.Model):
    __tablename__ = "user_special_permissions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id = db.Column(db.Integer, db.ForeignKey("special_permissions.id"), nullable=False, index=True)
    valid_from = db.Column(db.DateTime, nullable=False, default=datetime.now)
    valid_until = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    user = db.relationship("User", backref=db.backref("special_permissions", lazy=True, cascade="all, delete-orphan"))

    @property
    def is_active(self):
        now = datetime.now()
        return (
            self.permission is not None
            and bool(self.permission.is_active)
            and (self.valid_from is None or self.valid_from <= now)
            and (self.valid_until is None or self.valid_until >= now)
        )


class PushSubscription(db.Model):
    __tablename__ = "push_subscriptions"
    __table_args__ = (
        db.UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
        db.Index("ix_push_subscriptions_user_active", "user_id", "is_active"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint = db.Column(db.Text, nullable=False)
    p256dh = db.Column(db.Text, nullable=False)
    auth = db.Column(db.Text, nullable=False)
    user_agent = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )

    user = db.relationship("User", backref=db.backref("push_subscriptions", lazy="dynamic"))

    def to_webpush(self):
        return {
            "endpoint": self.endpoint,
            "keys": {
                "p256dh": self.p256dh,
                "auth": self.auth,
            },
        }


class SharedOrderIntent(db.Model):
    __tablename__ = "shared_order_intents"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    title = db.Column(db.String(255), nullable=True)
    text = db.Column(db.Text, nullable=True)
    url = db.Column(db.Text, nullable=True)
    files = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="received", index=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )

    user = db.relationship("User", backref=db.backref("shared_order_intents", lazy="dynamic"))

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "text": self.text,
            "url": self.url,
            "files": self.files or [],
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


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

    frequency = db.Column(db.String(20), nullable=False, default="weekly")
    # weekly | biweekly | twice_weekly

    second_weekday = db.Column(db.Integer, nullable=True)
    second_time = db.Column(db.Time, nullable=True)
    frequency_anchor_date = db.Column(db.Date, nullable=True)

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


class DeliveryScheduleRule(db.Model):
    __tablename__ = "delivery_schedule_rules"

    id = db.Column(db.Integer, primary_key=True)

    route_id = db.Column(
        db.Integer,
        db.ForeignKey("delivery_routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    scope = db.Column(db.String(20), nullable=False)
    # once | period

    source_date = db.Column(db.Date, nullable=True)
    target_date = db.Column(db.Date, nullable=True)

    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)

    target_weekday = db.Column(db.Integer, nullable=True)
    target_time = db.Column(db.Time, nullable=False)
    frequency = db.Column(db.String(20), nullable=False, default="weekly")
    # weekly | biweekly | twice_weekly

    second_weekday = db.Column(db.Integer, nullable=True)
    second_time = db.Column(db.Time, nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    note = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    route = db.relationship("DeliveryRoute", backref="schedule_rules")


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
    document_issued = db.Column(db.Boolean, nullable=False, default=False, index=True)
    document_issued_at = db.Column(db.DateTime, nullable=True)

    route = db.relationship("DeliveryRoute", backref="orders")
    events = db.relationship(
        "SlackOrderEvent",
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

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

    order = db.relationship("SlackOrder", back_populates="events")


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
    valid_from = db.Column(db.Date, nullable=True, index=True)
    valid_to = db.Column(db.Date, nullable=True, index=True)

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
    valid_from = db.Column(db.Date, nullable=True, index=True)
    valid_to = db.Column(db.Date, nullable=True, index=True)

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


class BusinessRegistry(db.Model):
    __tablename__ = "business_registries"
    __table_args__ = (
        db.UniqueConstraint("kind", "source", "source_code", name="uq_business_registry_kind_source_code"),
        db.Index("ix_business_registry_kind_display", "kind", "display_name"),
        db.Index(
            "ix_business_registry_customer_cluster",
            "kind",
            "category_code",
            "subcategory_code",
        ),
        db.Index(
            "ix_business_registry_customer_action",
            "kind",
            "statistical_code_2",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False, index=True)  # customer|supplier
    source = db.Column(db.String(40), nullable=False, default="teamsystem", index=True)
    source_company_code = db.Column(db.String(16), nullable=True)
    source_record_type = db.Column(db.String(8), nullable=True)
    source_code = db.Column(db.String(64), nullable=False, index=True)

    display_name = db.Column(db.String(255), nullable=False, index=True)
    legal_name = db.Column(db.String(255), nullable=True, index=True)
    vat_number = db.Column(db.String(32), nullable=True, index=True)
    tax_code = db.Column(db.String(32), nullable=True, index=True)

    address = db.Column(db.String(255), nullable=True)
    zip_code = db.Column(db.String(16), nullable=True, index=True)
    city = db.Column(db.String(120), nullable=True, index=True)
    province = db.Column(db.String(8), nullable=True, index=True)
    country = db.Column(db.String(4), nullable=True, default="IT")

    category_code = db.Column(db.String(32), nullable=True)
    category_description = db.Column(db.String(160), nullable=True)
    subcategory_code = db.Column(db.String(32), nullable=True)
    subcategory_description = db.Column(db.String(160), nullable=True)

    area_code = db.Column(db.String(32), nullable=True)
    area_description = db.Column(db.String(160), nullable=True)
    zone_code = db.Column(db.String(32), nullable=True)
    zone_description = db.Column(db.String(160), nullable=True)

    statistical_code_1 = db.Column(db.String(32), nullable=True)
    statistical_description_1 = db.Column(db.String(160), nullable=True)
    statistical_code_2 = db.Column(db.String(32), nullable=True)
    statistical_description_2 = db.Column(db.String(160), nullable=True)
    statistical_code_3 = db.Column(db.String(32), nullable=True)
    statistical_description_3 = db.Column(db.String(160), nullable=True)
    statistical_code_4 = db.Column(db.String(32), nullable=True)
    statistical_description_4 = db.Column(db.String(160), nullable=True)
    statistical_code_5 = db.Column(db.String(32), nullable=True)
    statistical_description_5 = db.Column(db.String(160), nullable=True)

    source_payload = db.Column(db.JSON, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )

    contacts = db.relationship(
        "BusinessRegistryContact",
        backref="registry",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    customer_memberships = db.relationship(
        "CustomerRegistryMembership",
        foreign_keys="CustomerRegistryMembership.registry_id",
        back_populates="registry",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "source": self.source,
            "source_code": self.source_code,
            "display_name": self.display_name,
            "legal_name": self.legal_name,
            "vat_number": self.vat_number,
            "tax_code": self.tax_code,
            "address": self.address,
            "zip_code": self.zip_code,
            "city": self.city,
            "province": self.province,
            "country": self.country,
            "category_code": self.category_code,
            "category_description": self.category_description,
            "subcategory_code": self.subcategory_code,
            "subcategory_description": self.subcategory_description,
            "cluster_key": [self.category_code, self.subcategory_code],
            "area_code": self.area_code,
            "area_description": self.area_description,
            "zone_code": self.zone_code,
            "zone_description": self.zone_description,
            "statistical_codes": {
                "monitor": self.statistical_code_1,
                "action": self.statistical_code_2,
                "statistical_3": self.statistical_code_3,
                "status": self.statistical_code_4,
                "peroni": self.statistical_code_5,
            },
            "statistical_descriptions": {
                "monitor": self.statistical_description_1,
                "action": self.statistical_description_2,
                "statistical_3": self.statistical_description_3,
                "status": self.statistical_description_4,
                "peroni": self.statistical_description_5,
            },
            "is_active": self.is_active,
        }


class CustomerAccountStatementImport(db.Model):
    __tablename__ = "customer_account_statement_imports"

    id = db.Column(db.Integer, primary_key=True)
    source_file = db.Column(db.String(255), nullable=False)
    trace_file = db.Column(db.String(255), nullable=False)
    source_sha256 = db.Column(db.String(64), nullable=False, unique=True, index=True)
    record_count = db.Column(db.Integer, nullable=False, default=0)
    customer_count = db.Column(db.Integer, nullable=False, default=0)
    matched_customer_count = db.Column(db.Integer, nullable=False, default=0)
    unmatched_customer_count = db.Column(db.Integer, nullable=False, default=0)
    imported_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False, index=True)

    entries = db.relationship(
        "CustomerAccountEntry",
        backref="statement_import",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )


class CustomerAccountEntry(db.Model):
    __tablename__ = "customer_account_entries"
    __table_args__ = (
        db.UniqueConstraint("import_id", "row_number", name="uq_customer_account_entry_import_row"),
        db.Index("ix_customer_account_entry_import_customer", "import_id", "registry_id"),
        db.Index("ix_customer_account_entry_import_source", "import_id", "source_customer_code"),
    )

    id = db.Column(db.Integer, primary_key=True)
    import_id = db.Column(
        db.Integer,
        db.ForeignKey("customer_account_statement_imports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    row_number = db.Column(db.Integer, nullable=False)
    registry_id = db.Column(
        db.Integer,
        db.ForeignKey("business_registries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_customer_code = db.Column(db.String(64), nullable=False, index=True)
    customer_name = db.Column(db.String(255), nullable=False)
    registration_date = db.Column(db.Date, nullable=True)
    document_date = db.Column(db.Date, nullable=True)
    due_date = db.Column(db.Date, nullable=True, index=True)
    document_number = db.Column(db.String(64), nullable=True)
    description = db.Column(db.String(255), nullable=True)
    additional_description = db.Column(db.String(255), nullable=True)
    accounting_reason = db.Column(db.String(8), nullable=True, index=True)
    accounting_reference = db.Column(db.String(16), nullable=True)
    is_balance_relevant = db.Column(db.Boolean, nullable=False, default=True, index=True)
    accounting_side = db.Column(db.String(1), nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    signed_amount = db.Column(db.Numeric(14, 2), nullable=False)
    source_payload = db.Column(db.JSON, nullable=True)

    registry = db.relationship(
        "BusinessRegistry",
        backref=db.backref("customer_account_entries", lazy="dynamic"),
    )


class CustomerRegistryMembership(db.Model):
    """Autorizzazione di un utente ad agire per una specifica anagrafica cliente."""

    __tablename__ = "customer_registry_memberships"
    __table_args__ = (
        db.UniqueConstraint("user_id", "registry_id", name="uq_customer_registry_membership_user_registry"),
        db.Index("ix_customer_registry_membership_user_status", "user_id", "status"),
        db.Index("ix_customer_registry_membership_registry_status", "registry_id", "status"),
        db.Index(
            "uq_customer_registry_membership_primary",
            "user_id",
            unique=True,
            postgresql_where=db.text("is_primary AND status = 'active'"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    registry_id = db.Column(
        db.Integer,
        db.ForeignKey("business_registries.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = db.Column(db.String(20), nullable=False, default="owner")  # owner|payments|viewer
    status = db.Column(db.String(20), nullable=False, default="active")
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    source = db.Column(db.String(40), nullable=False, default="manual")
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship("User", foreign_keys=[user_id], back_populates="customer_memberships")
    registry = db.relationship("BusinessRegistry", foreign_keys=[registry_id], back_populates="customer_memberships")
    approved_by = db.relationship("User", foreign_keys=[approved_by_user_id])


class CustomerPaymentCase(db.Model):
    """Pratica LDApp per PayByLink, bonifico dichiarato o pagamento contestato."""

    __tablename__ = "customer_payment_cases"
    __table_args__ = (
        db.Index("ix_customer_payment_case_registry_status", "registry_id", "status"),
        db.Index("ix_customer_payment_case_creator_created", "created_by_user_id", "created_at"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    public_id = db.Column(db.String(48), nullable=False, unique=True, index=True, default=lambda: secrets.token_urlsafe(24))
    registry_id = db.Column(db.Integer, db.ForeignKey("business_registries.id", ondelete="RESTRICT"), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    case_type = db.Column(db.String(24), nullable=False)  # paybylink|bank_transfer|payment_claim
    status = db.Column(db.String(32), nullable=False, default="draft", index=True)
    currency = db.Column(db.String(3), nullable=False, default="EUR")
    declared_amount = db.Column(db.Numeric(14, 2), nullable=False)
    payment_reference = db.Column(db.String(255), nullable=True)
    note = db.Column(db.Text, nullable=True)
    provider = db.Column(db.String(40), nullable=True)
    provider_reference = db.Column(db.String(160), nullable=True, index=True)
    payment_url = db.Column(db.Text, nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    submitted_at = db.Column(db.DateTime(timezone=True), nullable=True)
    provider_confirmed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    rejection_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    registry = db.relationship("BusinessRegistry")
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    allocations = db.relationship("CustomerPaymentAllocation", back_populates="payment_case", cascade="all, delete-orphan")
    evidence = db.relationship("CustomerPaymentEvidence", back_populates="payment_case", cascade="all, delete-orphan")
    events = db.relationship("CustomerPaymentEvent", back_populates="payment_case", cascade="all, delete-orphan")


class CustomerPaymentInstructions(db.Model):
    """Coordinate bancarie centralizzate mostrate nell'area contabile Horeca."""

    __tablename__ = "customer_payment_instructions"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(120), nullable=False, default="Bonifico bancario")
    account_holder = db.Column(db.String(255), nullable=False)
    iban = db.Column(db.String(34), nullable=False)
    bank_name = db.Column(db.String(160), nullable=True)
    bic_swift = db.Column(db.String(16), nullable=True)
    beneficiary_address = db.Column(db.String(255), nullable=True)
    payment_reason_template = db.Column(db.String(500), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    updated_by = db.relationship("User")


class CustomerPaymentAllocation(db.Model):
    __tablename__ = "customer_payment_allocations"
    __table_args__ = (
        db.UniqueConstraint("case_id", "source_item_key", name="uq_customer_payment_allocation_case_item"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    case_id = db.Column(db.BigInteger, db.ForeignKey("customer_payment_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    source_customer_code = db.Column(db.String(64), nullable=False)
    source_item_key = db.Column(db.String(160), nullable=False, index=True)
    current_entry_id = db.Column(db.Integer, db.ForeignKey("customer_account_entries.id", ondelete="SET NULL"), nullable=True)
    allocated_amount = db.Column(db.Numeric(14, 2), nullable=False)
    document_snapshot = db.Column(JSONB, nullable=False, default=dict)

    payment_case = db.relationship("CustomerPaymentCase", back_populates="allocations")
    current_entry = db.relationship("CustomerAccountEntry")


class CustomerPaymentEvidence(db.Model):
    __tablename__ = "customer_payment_evidence"

    id = db.Column(db.BigInteger, primary_key=True)
    case_id = db.Column(db.BigInteger, db.ForeignKey("customer_payment_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    storage_path = db.Column(db.String(500), nullable=False)
    content_type = db.Column(db.String(120), nullable=True)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    payment_case = db.relationship("CustomerPaymentCase", back_populates="evidence")
    uploaded_by = db.relationship("User")


class CustomerPaymentEvent(db.Model):
    __tablename__ = "customer_payment_events"
    __table_args__ = (db.Index("ix_customer_payment_event_case_created", "case_id", "created_at"),)

    id = db.Column(db.BigInteger, primary_key=True)
    case_id = db.Column(db.BigInteger, db.ForeignKey("customer_payment_cases.id", ondelete="CASCADE"), nullable=False)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    event_type = db.Column(db.String(40), nullable=False)
    from_status = db.Column(db.String(32), nullable=True)
    to_status = db.Column(db.String(32), nullable=True)
    message = db.Column(db.Text, nullable=True)
    event_metadata = db.Column(JSONB, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    payment_case = db.relationship("CustomerPaymentCase", back_populates="events")
    actor = db.relationship("User")


class CustomerAccountingItemState(db.Model):
    """Stato operativo LDApp separato dallo stato contabile importato da TeamSystem."""

    __tablename__ = "customer_accounting_item_states"
    __table_args__ = (
        db.UniqueConstraint("registry_id", "source_item_key", name="uq_customer_accounting_item_state_registry_item"),
        db.Index("ix_customer_accounting_item_state_registry_status", "registry_id", "status"),
    )

    id = db.Column(db.BigInteger, primary_key=True)
    registry_id = db.Column(db.Integer, db.ForeignKey("business_registries.id", ondelete="CASCADE"), nullable=False)
    source_customer_code = db.Column(db.String(64), nullable=False)
    source_item_key = db.Column(db.String(160), nullable=False)
    status = db.Column(db.String(32), nullable=False)
    payment_case_id = db.Column(db.BigInteger, db.ForeignKey("customer_payment_cases.id", ondelete="SET NULL"), nullable=True)
    last_seen_entry_id = db.Column(db.Integer, db.ForeignKey("customer_account_entries.id", ondelete="SET NULL"), nullable=True)
    message = db.Column(db.Text, nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    registry = db.relationship("BusinessRegistry")
    payment_case = db.relationship("CustomerPaymentCase")
    last_seen_entry = db.relationship("CustomerAccountEntry")


class CashCustomerRegistryLink(db.Model):
    __tablename__ = "cash_customer_registry_links"
    __table_args__ = (
        db.UniqueConstraint("registry_id", name="uq_cash_customer_registry_link_registry"),
        db.Index("ix_cash_customer_registry_link_customer", "cash_customer_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    cash_customer_id = db.Column(db.Integer, db.ForeignKey("cash_customers.id", ondelete="CASCADE"), nullable=False)
    registry_id = db.Column(db.Integer, db.ForeignKey("business_registries.id", ondelete="CASCADE"), nullable=False)
    match_source = db.Column(db.String(30), nullable=False, default="manual")
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)

    cash_customer = db.relationship("CashCustomer", backref=db.backref("registry_links", lazy="selectin"))
    registry = db.relationship("BusinessRegistry", backref=db.backref("cash_customer_link", uselist=False))


class BusinessRegistryContact(db.Model):
    __tablename__ = "business_registry_contacts"
    __table_args__ = (
        db.UniqueConstraint("registry_id", "contact_type", "value", name="uq_business_registry_contact_value"),
    )

    id = db.Column(db.Integer, primary_key=True)
    registry_id = db.Column(
        db.Integer,
        db.ForeignKey("business_registries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_type = db.Column(db.String(20), nullable=False, index=True)  # email|pec|phone|mobile|fax
    value = db.Column(db.String(255), nullable=False, index=True)
    label = db.Column(db.String(80), nullable=True)
    source_column = db.Column(db.String(16), nullable=True)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "registry_id": self.registry_id,
            "contact_type": self.contact_type,
            "value": self.value,
            "label": self.label,
            "source_column": self.source_column,
            "is_primary": self.is_primary,
        }


class RegistryContact(db.Model):
    __tablename__ = "registry_contacts"

    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(255), nullable=False, index=True)
    role = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    photo_path = db.Column(db.String(500), nullable=True)
    photo_mime = db.Column(db.String(80), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )

    points = db.relationship(
        "RegistryContactPoint",
        backref="contact",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    registry_links = db.relationship(
        "BusinessRegistryContactLink",
        backref="contact",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "display_name": self.display_name,
            "role": self.role,
            "notes": self.notes,
            "has_photo": bool(self.photo_path),
            "photo_url": f"/registry/api/contacts/{self.id}/photo" if self.photo_path else None,
            "is_active": self.is_active,
            "points": [point.to_dict() for point in self.points],
        }


class RegistryContactImportIntent(db.Model):
    __tablename__ = "registry_contact_import_intents"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True)
    suggested_registry_id = db.Column(
        db.Integer,
        db.ForeignKey("business_registries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_filename = db.Column(db.String(255), nullable=True)
    display_name = db.Column(db.String(255), nullable=True)
    phones = db.Column(db.JSON, nullable=True)
    emails = db.Column(db.JSON, nullable=True)
    photo_path = db.Column(db.String(500), nullable=True)
    photo_mime = db.Column(db.String(80), nullable=True)
    claim_token_hash = db.Column(db.String(64), nullable=True)
    claim_expires_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="pending", index=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )

    user = db.relationship("User")
    suggested_registry = db.relationship("BusinessRegistry")

    def to_dict(self):
        return {
            "id": self.id,
            "display_name": self.display_name,
            "phones": self.phones or [],
            "emails": self.emails or [],
            "has_photo": bool(self.photo_path),
            "status": self.status,
        }


class RegistryContactPoint(db.Model):
    __tablename__ = "registry_contact_points"
    __table_args__ = (
        db.UniqueConstraint("contact_id", "contact_type", "value", name="uq_registry_contact_point_value"),
    )

    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(
        db.Integer,
        db.ForeignKey("registry_contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_type = db.Column(db.String(20), nullable=False, index=True)
    value = db.Column(db.String(255), nullable=False, index=True)
    label = db.Column(db.String(80), nullable=True)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "contact_id": self.contact_id,
            "contact_type": self.contact_type,
            "value": self.value,
            "label": self.label,
            "is_primary": self.is_primary,
        }


class BusinessRegistryContactLink(db.Model):
    __tablename__ = "business_registry_contact_links"
    __table_args__ = (
        db.UniqueConstraint("registry_id", "contact_id", name="uq_business_registry_contact_link"),
    )

    id = db.Column(db.Integer, primary_key=True)
    registry_id = db.Column(
        db.Integer,
        db.ForeignKey("business_registries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id = db.Column(
        db.Integer,
        db.ForeignKey("registry_contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = db.Column(db.String(120), nullable=True)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )

    registry = db.relationship(
        "BusinessRegistry",
        backref=db.backref("contact_links", cascade="all, delete-orphan", lazy="selectin"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "registry_id": self.registry_id,
            "contact_id": self.contact_id,
            "role": self.role,
            "is_primary": self.is_primary,
            "is_active": self.is_active,
            "notes": self.notes,
            "contact": self.contact.to_dict() if self.contact else None,
        }


class DeliveryRouteCustomer(db.Model):
    __tablename__ = "delivery_route_customers"
    __table_args__ = (
        db.UniqueConstraint("route_id", "registry_id", name="uq_delivery_route_customer"),
    )

    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(
        db.Integer,
        db.ForeignKey("delivery_routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    registry_id = db.Column(
        db.Integer,
        db.ForeignKey("business_registries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )

    route = db.relationship(
        "DeliveryRoute",
        backref=db.backref("customer_links", cascade="all, delete-orphan", lazy="selectin"),
    )
    registry = db.relationship(
        "BusinessRegistry",
        backref=db.backref("delivery_route_links", cascade="all, delete-orphan", lazy="selectin"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "route_id": self.route_id,
            "registry_id": self.registry_id,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
            "notes": self.notes,
        }


class RouteOrderBoardEntry(db.Model):
    __tablename__ = "route_order_board_entries"
    __table_args__ = (
        db.UniqueConstraint("route_id", "registry_id", "board_date", name="uq_route_order_board_entry"),
        db.Index("ix_route_order_board_entries_route_board", "route_id", "board_date"),
        db.Index("ix_route_order_board_entries_planned", "route_id", "planned_delivery_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(
        db.Integer,
        db.ForeignKey("delivery_routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    registry_id = db.Column(
        db.Integer,
        db.ForeignKey("business_registries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    board_date = db.Column(db.Date, nullable=False, index=True)
    planned_delivery_at = db.Column(db.DateTime, nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False, default="da_chiamare", index=True)
    order_note = db.Column(db.Text, nullable=True)
    order_attachments = db.Column(db.JSON, nullable=True)
    list_done = db.Column(db.Boolean, nullable=False, default=False)
    slack_channel_id = db.Column(db.String(50), nullable=True)
    slack_message_ts = db.Column(db.String(50), nullable=True)
    slack_thread_ts = db.Column(db.String(50), nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )

    route = db.relationship("DeliveryRoute", backref=db.backref("order_board_entries", lazy="selectin"))
    registry = db.relationship("BusinessRegistry", backref=db.backref("route_order_entries", lazy="selectin"))

    def to_dict(self):
        return {
            "id": self.id,
            "route_id": self.route_id,
            "registry_id": self.registry_id,
            "board_date": self.board_date.isoformat() if self.board_date else None,
            "planned_delivery_at": self.planned_delivery_at.isoformat() if self.planned_delivery_at else None,
            "status": self.status,
            "order_note": self.order_note or "",
            "order_attachments": self.order_attachments or [],
            "list_done": self.list_done,
            "slack_channel_id": self.slack_channel_id,
            "slack_message_ts": self.slack_message_ts,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
        }


class CustomerOrderDeliveryOption(db.Model):
    __tablename__ = "customer_order_delivery_options"
    __table_args__ = (
        db.UniqueConstraint("code", name="uq_customer_order_delivery_options_code"),
        db.Index("ix_customer_order_delivery_options_active_sort", "is_active", "sort_order"),
    )

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    requires_value = db.Column(db.Boolean, nullable=False, default=False)
    value_label = db.Column(db.String(80), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "label": self.label,
            "requires_value": self.requires_value,
            "value_label": self.value_label,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
        }


class CustomerOrder(db.Model):
    __tablename__ = "customer_orders"
    __table_args__ = (
        db.Index("ix_customer_orders_registry_status", "registry_id", "status"),
        db.Index("ix_customer_orders_created", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    registry_id = db.Column(db.Integer, db.ForeignKey("business_registries.id", ondelete="RESTRICT"), nullable=False, index=True)
    route_id = db.Column(db.Integer, db.ForeignKey("delivery_routes.id", ondelete="SET NULL"), nullable=True, index=True)
    delivery_option_id = db.Column(db.Integer, db.ForeignKey("customer_order_delivery_options.id", ondelete="SET NULL"), nullable=True)
    delivery_option_value = db.Column(db.String(160), nullable=True)
    order_text = db.Column(db.Text, nullable=True)
    attachments = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="received", index=True)
    route_board_entry_id = db.Column(db.Integer, db.ForeignKey("route_order_board_entries.id", ondelete="SET NULL"), nullable=True)
    slack_order_id = db.Column(db.Integer, db.ForeignKey("slack_orders.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )

    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("customer_orders", lazy="dynamic"))
    registry = db.relationship("BusinessRegistry", backref=db.backref("customer_orders", lazy="selectin"))
    route = db.relationship("DeliveryRoute", backref=db.backref("customer_orders", lazy="selectin"))
    delivery_option = db.relationship("CustomerOrderDeliveryOption")
    route_board_entry = db.relationship("RouteOrderBoardEntry")
    slack_order = db.relationship("SlackOrder")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "registry_id": self.registry_id,
            "route_id": self.route_id,
            "delivery_option": self.delivery_option.to_dict() if self.delivery_option else None,
            "delivery_option_value": self.delivery_option_value,
            "order_text": self.order_text or "",
            "attachments": self.attachments or [],
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CustomerOrderRevision(db.Model):
    __tablename__ = "customer_order_revisions"
    __table_args__ = (
        db.Index("ix_customer_order_revisions_order_created", "order_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("customer_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    change_type = db.Column(db.String(30), nullable=False, default="addition")
    order_text = db.Column(db.Text, nullable=True)
    attachments = db.Column(db.JSON, nullable=True)
    delivery_option_id = db.Column(db.Integer, db.ForeignKey("customer_order_delivery_options.id", ondelete="SET NULL"), nullable=True)
    delivery_option_value = db.Column(db.String(160), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)

    order = db.relationship("CustomerOrder", backref=db.backref("revisions", cascade="all, delete-orphan", lazy="selectin"))
    user = db.relationship("User", foreign_keys=[user_id])
    delivery_option = db.relationship("CustomerOrderDeliveryOption")


class BusinessRegistryAlert(db.Model):
    __tablename__ = "business_registry_alerts"

    id = db.Column(db.Integer, primary_key=True)
    registry_id = db.Column(
        db.Integer,
        db.ForeignKey("business_registries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message = db.Column(db.String(255), nullable=False)
    start_date = db.Column(db.Date, nullable=True, index=True)
    end_date = db.Column(db.Date, nullable=True, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )

    registry = db.relationship("BusinessRegistry", backref=db.backref("alerts", cascade="all, delete-orphan", lazy="selectin"))

    def to_dict(self):
        return {
            "id": self.id,
            "registry_id": self.registry_id,
            "message": self.message,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "is_active": self.is_active,
        }


class CourierIntegration(db.Model):
    __tablename__ = "courier_integrations"
    __table_args__ = (
        db.UniqueConstraint("code", name="uq_courier_integrations_code"),
        db.Index("ix_courier_integrations_enabled", "is_enabled"),
    )

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    is_enabled = db.Column(db.Boolean, nullable=False, default=False)
    base_url = db.Column(db.String(255), nullable=True)
    credentials = db.Column(db.JSON, nullable=True)
    settings = db.Column(db.JSON, nullable=True)
    last_sync_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "is_enabled": bool(self.is_enabled),
            "base_url": self.base_url,
            "settings": self.settings or {},
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
        }


class CourierAccount(db.Model):
    __tablename__ = "courier_accounts"
    __table_args__ = (
        db.UniqueConstraint("courier_code", "account_type", "name", name="uq_courier_accounts_code_type_name"),
        db.Index("ix_courier_accounts_courier_enabled", "courier_code", "is_enabled"),
        db.Index("ix_courier_accounts_account_type", "account_type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    courier_code = db.Column(db.String(30), nullable=False, index=True)
    account_type = db.Column(db.String(30), nullable=False, default="portal", index=True)
    name = db.Column(db.String(120), nullable=False)
    base_url = db.Column(db.String(255), nullable=True)
    username = db.Column(db.String(180), nullable=True)
    password_encrypted = db.Column(EncryptedString(1024), nullable=True)
    valid_from = db.Column(db.Date, nullable=True, index=True)
    valid_to = db.Column(db.Date, nullable=True, index=True)
    extra_config = db.Column(db.JSON, nullable=True)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )

    def to_dict(self, include_secret=False):
        data = {
            "id": self.id,
            "courier_code": self.courier_code,
            "account_type": self.account_type,
            "name": self.name,
            "base_url": self.base_url,
            "username": self.username,
            "has_password": bool(self.password_encrypted),
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "extra_config": self.extra_config or {},
            "is_enabled": bool(self.is_enabled),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_secret:
            data["password"] = self.password_encrypted
        return data


class Shipment(db.Model):
    __tablename__ = "shipments"
    __table_args__ = (
        db.UniqueConstraint("courier_code", "tracking_number", name="uq_shipments_courier_tracking"),
        db.Index("ix_shipments_status", "status"),
        db.Index("ix_shipments_courier_status", "courier_code", "status"),
        db.Index("ix_shipments_customer_registry_id", "customer_registry_id"),
        db.Index("ix_shipments_external_order_id", "external_order_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    courier_code = db.Column(db.String(30), nullable=False, index=True)
    courier_account_id = db.Column(
        db.Integer,
        db.ForeignKey("courier_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    courier_name = db.Column(db.String(80), nullable=True)
    tracking_number = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(40), nullable=False, default="created", index=True)
    status_label = db.Column(db.String(120), nullable=True)
    customer_registry_id = db.Column(
        db.Integer,
        db.ForeignKey("business_registries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_name = db.Column(db.String(255), nullable=True)
    recipient_name = db.Column(db.String(255), nullable=True)
    recipient_address = db.Column(db.Text, nullable=True)
    external_order_id = db.Column(db.String(120), nullable=True, index=True)
    source = db.Column(db.String(40), nullable=True)
    reference = db.Column(db.String(120), nullable=True)
    shipped_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    last_tracking_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    raw_payload = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )

    customer = db.relationship("BusinessRegistry", backref=db.backref("shipments", lazy="selectin"))
    courier_account = db.relationship("CourierAccount", backref=db.backref("shipments", lazy="selectin"))

    def to_dict(self):
        return {
            "id": self.id,
            "courier_code": self.courier_code,
            "courier_account_id": self.courier_account_id,
            "courier_account_name": self.courier_account.name if self.courier_account else None,
            "courier_account_type": self.courier_account.account_type if self.courier_account else None,
            "courier_name": self.courier_name,
            "tracking_number": self.tracking_number,
            "status": self.status,
            "status_label": self.status_label,
            "customer_registry_id": self.customer_registry_id,
            "customer_name": self.customer_name,
            "recipient_name": self.recipient_name,
            "recipient_address": self.recipient_address,
            "external_order_id": self.external_order_id,
            "source": self.source,
            "reference": self.reference,
            "shipped_at": self.shipped_at.isoformat() if self.shipped_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "last_tracking_at": self.last_tracking_at.isoformat() if self.last_tracking_at else None,
            "last_error": self.last_error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ShipmentTrackingEvent(db.Model):
    __tablename__ = "shipment_tracking_events"
    __table_args__ = (
        db.Index("ix_shipment_tracking_events_shipment_at", "shipment_id", "event_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(
        db.Integer,
        db.ForeignKey("shipments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(80), nullable=True)
    location = db.Column(db.String(180), nullable=True)
    description = db.Column(db.Text, nullable=True)
    raw_payload = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)

    shipment = db.relationship(
        "Shipment",
        backref=db.backref("tracking_events", cascade="all, delete-orphan", lazy="selectin"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "shipment_id": self.shipment_id,
            "event_at": self.event_at.isoformat() if self.event_at else None,
            "status": self.status,
            "location": self.location,
            "description": self.description,
        }


class ExternalOrder(db.Model):
    __tablename__ = "external_orders"
    __table_args__ = (
        db.UniqueConstraint("source", "external_id", name="uq_external_orders_source_external_id"),
        db.Index("ix_external_orders_source_status", "source", "status"),
        db.Index("ix_external_orders_customer_registry_id", "customer_registry_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(40), nullable=False, default="poleepo", index=True)
    external_id = db.Column(db.String(120), nullable=False)
    order_number = db.Column(db.String(120), nullable=True, index=True)
    status = db.Column(db.String(40), nullable=False, default="imported", index=True)
    customer_registry_id = db.Column(
        db.Integer,
        db.ForeignKey("business_registries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_name = db.Column(db.String(255), nullable=True)
    recipient_name = db.Column(db.String(255), nullable=True)
    recipient_address = db.Column(db.Text, nullable=True)
    order_total = db.Column(db.Numeric(12, 2), nullable=True)
    currency = db.Column(db.String(3), nullable=True)
    ordered_at = db.Column(db.DateTime, nullable=True)
    raw_payload = db.Column(db.JSON, nullable=True)
    last_sync_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
        nullable=False,
    )

    customer = db.relationship("BusinessRegistry", backref=db.backref("external_orders", lazy="selectin"))

    def to_dict(self):
        return {
            "id": self.id,
            "source": self.source,
            "external_id": self.external_id,
            "order_number": self.order_number,
            "status": self.status,
            "customer_registry_id": self.customer_registry_id,
            "customer_name": self.customer_name,
            "recipient_name": self.recipient_name,
            "recipient_address": self.recipient_address,
            "order_total": float(self.order_total) if self.order_total is not None else None,
            "currency": self.currency,
            "ordered_at": self.ordered_at.isoformat() if self.ordered_at else None,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
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

    fiscal_snapshot_version = db.Column(db.Integer, nullable=False, default=1)
    fiscal_snapshot = db.Column(JSONB, nullable=True)
    fiscal_snapshot_created_at = db.Column(db.DateTime(timezone=True), nullable=True)
    fiscal_snapshot_stale = db.Column(db.Boolean, nullable=False, default=False)

    saldo_versabile_precedente = db.Column(db.Numeric(12, 2), nullable=True)
    versabile_giornata = db.Column(db.Numeric(12, 2), nullable=True)
    saldo_versabile_finale = db.Column(db.Numeric(12, 2), nullable=True)

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


class CashDayAuditEvent(db.Model):
    __tablename__ = "cash_day_audit_events"

    id = db.Column(db.BigInteger, primary_key=True)
    cash_day_id = db.Column(db.Integer, db.ForeignKey("cash_days.id", ondelete="CASCADE"), nullable=False, index=True)

    entity_type = db.Column(db.String(64), nullable=False, index=True)
    entity_id = db.Column(db.String(64), nullable=True, index=True)
    action = db.Column(db.String(24), nullable=False, index=True)

    before = db.Column(JSONB, nullable=True)
    after = db.Column(JSONB, nullable=True)
    reason = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    cash_day = db.relationship("CashDay", backref=db.backref("audit_events", lazy="dynamic", cascade="all, delete-orphan"))
    created_by = db.relationship("User")

    def __repr__(self):
        return f"<CashDayAuditEvent day_id={self.cash_day_id} {self.entity_type}:{self.entity_id} {self.action}>"


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

    flag = db.Column(db.String(2), nullable=False, default="*")

    bank_id = db.Column(db.Integer, db.ForeignKey("cash_banks.id"), nullable=True)

    description = db.Column(db.String(255), nullable=True)

    bank = db.relationship("CashBank")
    pos_links = db.relationship(
        "CashSalePaymentPosMove",
        back_populates="sale_payment",
        cascade="all, delete-orphan",
        lazy="select",
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

    flag = db.Column(db.String(2), nullable=False, default="*")

    bank_id = db.Column(db.Integer, db.ForeignKey("cash_banks.id"), nullable=True)

    pos_card_label = db.Column(db.String(100), nullable=True)
    pos_is_personal = db.Column(db.Boolean, nullable=False, default=False)

    description = db.Column(db.String(255), nullable=True)

    bank = db.relationship("CashBank")


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
    sale_payment_links = db.relationship(
        "CashSalePaymentPosMove",
        back_populates="pos_move",
        cascade="all, delete-orphan",
        lazy="select",
    )

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
    settlement_amount = db.Column(db.Numeric(12, 2), nullable=True)
    scan_path = db.Column(db.String(500), nullable=True)
    scan_mime = db.Column(db.String(100), nullable=True)
    scan_original_name = db.Column(db.String(255), nullable=True)

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


class CashBank(db.Model):
    __tablename__ = "cash_banks"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True, index=True)
    logo_path = db.Column(db.String(255), nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)

    sort_order = db.Column(db.Integer, nullable=False, default=0)

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

    def __repr__(self):
        return f"<CashBank {self.name}>"


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

    bank_id = db.Column(db.Integer, db.ForeignKey("cash_banks.id"), nullable=True, index=True)
    bank = db.relationship("CashBank")

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


class CashDrawerCount(db.Model):
    __tablename__ = "cash_drawer_counts"
    __table_args__ = (
        db.UniqueConstraint("cash_day_id", name="uq_cash_drawer_count_day"),
    )

    id = db.Column(db.Integer, primary_key=True)

    cash_day_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_days.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

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

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True
    )

    notes = db.Column(db.Text, nullable=True)

    cash_day = db.relationship(
        "CashDay",
        backref=db.backref(
            "drawer_count",
            uselist=False,
            cascade="all, delete-orphan",
            lazy="select"
        )
    )

    created_by = db.relationship("User", backref="cash_drawer_counts")

    lines = db.relationship(
        "CashDrawerCountLine",
        backref="drawer_count",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="CashDrawerCountLine.denomination.asc()"
    )

    def __repr__(self):
        return f"<CashDrawerCount day_id={self.cash_day_id}>"


class CashDrawerCountLine(db.Model):
    __tablename__ = "cash_drawer_count_lines"
    __table_args__ = (
        db.UniqueConstraint(
            "drawer_count_id",
            "denomination",
            name="uq_cash_drawer_count_line_denomination"
        ),
        CheckConstraint("denomination > 0", name="ck_drawer_count_line_denomination_pos"),
        CheckConstraint("quantity >= 0", name="ck_drawer_count_line_quantity_nonneg"),
        CheckConstraint("line_total >= 0", name="ck_drawer_count_line_total_nonneg"),
    )

    id = db.Column(db.Integer, primary_key=True)

    drawer_count_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_drawer_counts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    denomination = db.Column(db.Numeric(12, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    line_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)

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

    def __repr__(self):
        return (
            f"<CashDrawerCountLine drawer_count_id={self.drawer_count_id} "
            f"denomination={self.denomination} quantity={self.quantity}>"
        )


class CashEcommerce(db.Model):
    __tablename__ = "cash_ecommerce"

    id = db.Column(db.Integer, primary_key=True)

    cash_day_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_days.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True
    )

    amount = db.Column(db.Numeric(12, 2), nullable=False)

    description = db.Column(db.String(255), nullable=True)

    created_by = db.relationship("User", backref="cash_ecommerce")

    def __repr__(self):
        return f"<CashEcommerce id={self.id} day={self.cash_day_id} amount={self.amount}>"


class CashCheckEvent(db.Model):
    __tablename__ = "cash_check_events"

    id = db.Column(db.Integer, primary_key=True)

    check_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_checks.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    from_status = db.Column(db.String(50), nullable=True)
    to_status = db.Column(db.String(50), nullable=False, index=True)

    # Data "logica" dell'evento (es. data versamento, data incasso, ecc.)
    event_date = db.Column(db.Date, nullable=False, index=True)

    # Timestamp tecnico
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True
    )

    cash_expense_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_expenses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Note libere
    note = db.Column(db.Text, nullable=True)

    # Spese sostenute (bancarie, protesto, ecc.)
    amount_spese = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    # Importo addebitato al cliente (può includere penali)
    customer_charge_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    check = db.relationship("CashCheck", backref=db.backref(
        "events",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="CashCheckEvent.created_at.asc()"
    ))

    created_by = db.relationship("User", backref="cash_check_events")
    cash_expense = db.relationship("CashExpense", backref=db.backref("check_events", lazy="select"))

    def __repr__(self):
        return f"<CashCheckEvent check_id={self.check_id} {self.from_status}->{self.to_status}>"


class CashCheckPayment(db.Model):
    __tablename__ = "cash_check_payments"

    id = db.Column(db.Integer, primary_key=True)
    check_id = db.Column(db.Integer, db.ForeignKey("cash_checks.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_date = db.Column(db.Date, nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    method = db.Column(db.String(20), nullable=False, default="bank")
    note = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    check = db.relationship("CashCheck", backref=db.backref("check_payments", lazy="select", cascade="all, delete-orphan"))
    created_by = db.relationship("User", backref="cash_check_payments")


class CashReceiptClosure(db.Model):
    __tablename__ = "cash_receipt_closures"

    id = db.Column(db.Integer, primary_key=True)

    cash_day_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_days.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    amount = db.Column(db.Numeric(12, 2), nullable=False)

    # fine_giornata | intermedia
    closure_type = db.Column(
        db.String(20),
        nullable=False,
        default="fine_giornata",
        index=True
    )

    description = db.Column(db.String(255), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    updated_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True
    )

    cash_day = db.relationship(
        "CashDay",
        backref=db.backref(
            "receipt_closures",
            cascade="all, delete-orphan",
            lazy="select"
        )
    )

    created_by = db.relationship(
        "User",
        foreign_keys=[created_by_user_id],
        backref="cash_receipt_closures_created"
    )

    updated_by = db.relationship(
        "User",
        foreign_keys=[updated_by_user_id],
        backref="cash_receipt_closures_updated"
    )

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_cash_receipt_closure_amount_nonneg"),
        CheckConstraint(
            "closure_type IN ('fine_giornata','intermedia')",
            name="ck_cash_receipt_closure_type"
        ),
    )

    def __repr__(self):
        return (
            f"<CashReceiptClosure id={self.id} "
            f"day={self.cash_day_id} "
            f"type={self.closure_type} "
            f"amount={self.amount}>"
        )


class CashOwnerTake(db.Model):
    __tablename__ = "cash_owner_takes"

    id = db.Column(db.Integer, primary_key=True)

    cash_day_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_days.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    take_type = db.Column(
        db.String(20),
        nullable=False,
        default="serale",
        index=True
    )  # parziale | serale

    cash_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    check_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    notes = db.Column(db.Text, nullable=True)

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

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True
    )

    updated_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True
    )

    cash_day = db.relationship(
        "CashDay",
        backref=db.backref(
            "owner_takes",
            cascade="all, delete-orphan",
            lazy="select"
        )
    )

    created_by = db.relationship(
        "User",
        foreign_keys=[created_by_user_id],
        backref="cash_owner_takes_created"
    )

    updated_by = db.relationship(
        "User",
        foreign_keys=[updated_by_user_id],
        backref="cash_owner_takes_updated"
    )

    checks = db.relationship(
        "CashOwnerTakeCheck",
        back_populates="owner_take",
        cascade="all, delete-orphan",
        lazy="select"
    )

    __table_args__ = (
        CheckConstraint("cash_amount >= 0", name="ck_cash_owner_take_cash_amount_nonneg"),
        CheckConstraint("check_amount >= 0", name="ck_cash_owner_take_check_amount_nonneg"),
        CheckConstraint(
            "take_type IN ('parziale','serale')",
            name="ck_cash_owner_take_type"
        ),
    )

    def __repr__(self):
        return (
            f"<CashOwnerTake id={self.id} "
            f"day_id={self.cash_day_id} "
            f"type={self.take_type} "
            f"cash={self.cash_amount} "
            f"checks={self.check_amount}>"
        )


class CashOwnerTakeCheck(db.Model):
    __tablename__ = "cash_owner_take_checks"

    id = db.Column(db.Integer, primary_key=True)

    owner_take_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_owner_takes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    check_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_checks.id"),
        nullable=False,
        index=True,
    )

    check_amount = db.Column(db.Numeric(12, 2), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    owner_take = db.relationship(
        "CashOwnerTake",
        back_populates="checks"
    )

    check = db.relationship(
        "CashCheck",
        lazy="select"
    )

    __table_args__ = (
        db.UniqueConstraint(
            "owner_take_id",
            "check_id",
            name="uq_cash_owner_take_check"
        ),
    )

    def __repr__(self):
        return f"<CashOwnerTakeCheck owner_take_id={self.owner_take_id} check_id={self.check_id}>"

class CashSalePaymentPosMove(db.Model):
    __tablename__ = "cash_sale_payment_pos_moves"
    __table_args__ = (
        db.UniqueConstraint(
            "sale_payment_id",
            "pos_move_id",
            name="uq_sale_payment_pos_move"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)

    sale_payment_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_sale_payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    pos_move_id = db.Column(
        db.Integer,
        db.ForeignKey("pos_moves.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    sale_payment = db.relationship(
        "CashSalePayment",
        back_populates="pos_links"
    )

    pos_move = db.relationship(
        "PosMove",
        back_populates="sale_payment_links"
    )


class CashRowCheck(db.Model):
    __tablename__ = "cash_row_checks"

    id = db.Column(db.Integer, primary_key=True)

    # riferimento alla giornata (utile per query veloci per quadrante)
    cash_day_id = db.Column(db.Integer, db.ForeignKey("cash_days.id"), nullable=False, index=True)

    # tipo entità (pos_move, cash_move, sale, expense, ecc.)
    entity_type = db.Column(db.String(50), nullable=False, index=True)

    # id della riga nella tabella originale
    entity_id = db.Column(db.Integer, nullable=False, index=True)

    # stato check
    is_checked = db.Column(db.Boolean, nullable=False, default=True)

    # auditing
    checked_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    checked_at = db.Column(db.DateTime, nullable=True)

    # opzionale per futuro (note controllo)
    note = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("entity_type", "entity_id", name="uq_cash_row_check_entity"),
    )


class CashIssuedCheck(db.Model):
    __tablename__ = "cash_issued_checks"

    id = db.Column(db.Integer, primary_key=True)

    expense_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_expenses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    bank_id = db.Column(
        db.Integer,
        db.ForeignKey("cash_banks.id"),
        nullable=False,
        index=True,
    )

    check_number = db.Column(db.String(50), nullable=False)
    flag = db.Column(db.String(2), nullable=False, default="*")
    due_date = db.Column(db.Date, nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    registered_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)

    status = db.Column(
        db.String(20),
        nullable=False,
        default="emesso",
    )  # emesso | registrato | rientrato

    note = db.Column(db.String(255), nullable=True)

    expense = db.relationship(
        "CashExpense",
        backref=db.backref(
            "issued_checks",
            cascade="all, delete-orphan",
            lazy="selectin",
        ),
    )

    bank = db.relationship("CashBank")

    def __repr__(self):
        return f"<CashIssuedCheck id={self.id} expense_id={self.expense_id} number={self.check_number}>"
