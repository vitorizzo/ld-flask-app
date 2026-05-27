"""create wine cards

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-05-27 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from datetime import datetime, timezone


revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "wine_card_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("layout_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_wine_card_templates_active_order", "wine_card_templates", ["is_active", "sort_order"])
    op.create_index("ix_wine_card_templates_code", "wine_card_templates", ["code"], unique=True)
    op.create_index("ix_wine_card_templates_is_active", "wine_card_templates", ["is_active"])

    op.create_table(
        "wine_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_registry_id", sa.Integer(), nullable=True),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("source_card_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("venue_name", sa.String(length=180), nullable=True),
        sa.Column("subtitle", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("customer_view_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("customer_view_token", sa.String(length=64), nullable=True),
        sa.Column("layout_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["customer_registry_id"], ["business_registries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["template_id"], ["wine_card_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_card_id"], ["wine_cards.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wine_cards_customer_registry_id", "wine_cards", ["customer_registry_id"])
    op.create_index("ix_wine_cards_customer_status", "wine_cards", ["customer_registry_id", "status"])
    op.create_index("ix_wine_cards_customer_view_enabled", "wine_cards", ["customer_view_enabled"])
    op.create_index("ix_wine_cards_customer_view_token", "wine_cards", ["customer_view_token"], unique=True)
    op.create_index("ix_wine_cards_created_by_user_id", "wine_cards", ["created_by_user_id"])
    op.create_index("ix_wine_cards_source_card_id", "wine_cards", ["source_card_id"])
    op.create_index("ix_wine_cards_status", "wine_cards", ["status"])
    op.create_index("ix_wine_cards_template_id", "wine_cards", ["template_id"])
    op.create_index("ix_wine_cards_title", "wine_cards", ["title"])

    templates_table = sa.table(
        "wine_card_templates",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("layout_config", postgresql.JSONB),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(templates_table, [
        {
            "code": "classico",
            "name": "Classico",
            "description": "Stile vicino alle carte Excel attuali, con intestazione centrale e logo in alto.",
            "layout_config": {
                "css_class": "wine-template-classic",
                "font_family": "Calibri, Arial, sans-serif",
                "heading_font_family": "Montserrat, Arial, sans-serif",
                "accent_font_family": "'Monotype Corsiva', 'Brush Script MT', cursive",
                "text_color": "#404040",
                "background_color": "#fffdf8",
                "heading_size": "20pt",
                "subtitle_size": "14pt",
                "section_size": "15pt",
                "item_size": "14pt",
                "meta_size": "11pt",
                "price_x": "82%",
                "item_gap": "0.62cm",
                "section_gap": "0.82cm",
            },
            "is_active": True,
            "sort_order": 10,
            "created_at": now,
            "updated_at": now,
        },
        {
            "code": "moderno",
            "name": "Moderno",
            "description": "Layout pulito, sans-serif, sezioni con accento laterale e spaziatura regolare.",
            "layout_config": {
                "css_class": "wine-template-modern",
                "font_family": "Arial, Helvetica, sans-serif",
                "heading_font_family": "Arial, Helvetica, sans-serif",
                "accent_font_family": "Arial, Helvetica, sans-serif",
                "text_color": "#263238",
                "background_color": "#ffffff",
                "heading_size": "22pt",
                "subtitle_size": "11pt",
                "section_size": "12pt",
                "item_size": "12pt",
                "meta_size": "9.5pt",
                "price_x": "84%",
                "item_gap": "0.42cm",
                "section_gap": "0.75cm",
            },
            "is_active": True,
            "sort_order": 20,
            "created_at": now,
            "updated_at": now,
        },
        {
            "code": "elegante",
            "name": "Elegante",
            "description": "Resa piu' raffinata, serif, titoli ampi e prezzo ben staccato.",
            "layout_config": {
                "css_class": "wine-template-elegant",
                "font_family": "Georgia, 'Times New Roman', serif",
                "heading_font_family": "Georgia, 'Times New Roman', serif",
                "accent_font_family": "'Monotype Corsiva', 'Brush Script MT', cursive",
                "text_color": "#30251f",
                "background_color": "#fffaf1",
                "heading_size": "24pt",
                "subtitle_size": "14pt",
                "section_size": "16pt",
                "item_size": "13.5pt",
                "meta_size": "10.5pt",
                "price_x": "86%",
                "item_gap": "0.72cm",
                "section_gap": "1cm",
            },
            "is_active": True,
            "sort_order": 30,
            "created_at": now,
            "updated_at": now,
        },
        {
            "code": "compatto",
            "name": "Compatto",
            "description": "Pensato per carte lunghe, con font e spaziature ridotte.",
            "layout_config": {
                "css_class": "wine-template-compact",
                "font_family": "Calibri, Arial, sans-serif",
                "heading_font_family": "Montserrat, Arial, sans-serif",
                "accent_font_family": "Calibri, Arial, sans-serif",
                "text_color": "#404040",
                "background_color": "#ffffff",
                "heading_size": "18pt",
                "subtitle_size": "12pt",
                "section_size": "12pt",
                "item_size": "11pt",
                "meta_size": "9pt",
                "price_x": "80%",
                "item_gap": "0.28cm",
                "section_gap": "0.48cm",
            },
            "is_active": True,
            "sort_order": 40,
            "created_at": now,
            "updated_at": now,
        },
    ])

    op.create_table(
        "wine_card_sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["wine_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("card_id", "code", name="uq_wine_card_section_card_code"),
    )
    op.create_index("ix_wine_card_sections_card_id", "wine_card_sections", ["card_id"])
    op.create_index(
        "ix_wine_card_sections_card_visible_order",
        "wine_card_sections",
        ["card_id", "is_visible", "sort_order"],
    )
    op.create_index("ix_wine_card_sections_code", "wine_card_sections", ["code"])
    op.create_index("ix_wine_card_sections_is_visible", "wine_card_sections", ["is_visible"])

    op.create_table(
        "wine_card_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=True),
        sa.Column("cod_art", sa.String(length=255), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("display_description", sa.String(length=255), nullable=False),
        sa.Column("winery", sa.String(length=180), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("sale_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["wine_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["section_id"], ["wine_card_sections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cod_art"], ["articoli.cod_art"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("card_id", "cod_art", name="uq_wine_card_item_card_cod_art"),
    )
    op.create_index("ix_wine_card_items_card_category", "wine_card_items", ["card_id", "category"])
    op.create_index("ix_wine_card_items_card_id", "wine_card_items", ["card_id"])
    op.create_index("ix_wine_card_items_category", "wine_card_items", ["category"])
    op.create_index("ix_wine_card_items_cod_art", "wine_card_items", ["cod_art"])
    op.create_index("ix_wine_card_items_is_visible", "wine_card_items", ["is_visible"])
    op.create_index("ix_wine_card_items_section_id", "wine_card_items", ["section_id"])


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_wine_card_items_section_id")
    op.drop_index("ix_wine_card_items_is_visible", table_name="wine_card_items")
    op.drop_index("ix_wine_card_items_cod_art", table_name="wine_card_items")
    op.drop_index("ix_wine_card_items_category", table_name="wine_card_items")
    op.drop_index("ix_wine_card_items_card_id", table_name="wine_card_items")
    op.drop_index("ix_wine_card_items_card_category", table_name="wine_card_items")
    op.drop_table("wine_card_items")

    op.execute("DROP INDEX IF EXISTS ix_wine_card_sections_is_visible")
    op.execute("DROP INDEX IF EXISTS ix_wine_card_sections_code")
    op.execute("DROP INDEX IF EXISTS ix_wine_card_sections_card_visible_order")
    op.execute("DROP INDEX IF EXISTS ix_wine_card_sections_card_id")
    op.execute("DROP TABLE IF EXISTS wine_card_sections")

    op.drop_index("ix_wine_cards_title", table_name="wine_cards")
    op.drop_index("ix_wine_cards_status", table_name="wine_cards")
    op.execute("DROP INDEX IF EXISTS ix_wine_cards_template_id")
    op.drop_index("ix_wine_cards_source_card_id", table_name="wine_cards")
    op.drop_index("ix_wine_cards_created_by_user_id", table_name="wine_cards")
    op.drop_index("ix_wine_cards_customer_view_enabled", table_name="wine_cards")
    op.drop_index("ix_wine_cards_customer_view_token", table_name="wine_cards")
    op.drop_index("ix_wine_cards_customer_status", table_name="wine_cards")
    op.drop_index("ix_wine_cards_customer_registry_id", table_name="wine_cards")
    op.drop_table("wine_cards")
    op.execute("DROP INDEX IF EXISTS ix_wine_card_templates_is_active")
    op.execute("DROP INDEX IF EXISTS ix_wine_card_templates_code")
    op.execute("DROP INDEX IF EXISTS ix_wine_card_templates_active_order")
    op.execute("DROP TABLE IF EXISTS wine_card_templates")
