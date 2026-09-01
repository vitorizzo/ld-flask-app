"""add administration PayByLink workflow

Revision ID: b9c0d1e2f4a6
Revises: a8b9c0d1e3f5
Create Date: 2026-08-29 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

from tools.crypto import EncryptedString


revision = "b9c0d1e2f4a6"
down_revision = "a8b9c0d1e3f5"
branch_labels = None
depends_on = None


LINK_TABLE = "administration_payment_links"
DELIVERY_TABLE = "administration_payment_link_deliveries"

LINK_COLUMNS = {
    "id", "public_id", "created_by_user_id", "amount", "currency", "description",
    "status", "provider", "provider_order_id", "provider_reference",
    "provider_operation_id", "provider_security_token", "provider_last_event_id",
    "payment_url", "expires_at", "provider_confirmed_at", "last_error", "created_at",
    "updated_at",
}
DELIVERY_COLUMNS = {
    "id", "payment_link_id", "requested_by_user_id", "recipient_type",
    "recipient_user_id", "recipient_registry_id", "recipient_name", "recipient_email",
    "status", "error_message", "created_at", "sent_at",
}

LINK_INDEXES = (
    ("ix_administration_payment_link_public_id", ("public_id",)),
    ("ix_administration_payment_link_provider_order_id", ("provider_order_id",)),
    ("ix_administration_payment_link_provider_reference", ("provider_reference",)),
    ("ix_administration_payment_link_provider_operation_id", ("provider_operation_id",)),
    ("ix_administration_payment_link_provider_last_event_id", ("provider_last_event_id",)),
    ("ix_administration_payment_link_status", ("status",)),
    ("ix_administration_payment_link_status_created", ("status", "created_at")),
    ("ix_administration_payment_link_creator_created", ("created_by_user_id", "created_at")),
)
DELIVERY_INDEXES = (
    ("ix_administration_payment_link_delivery_status", ("status",)),
    ("ix_administration_payment_link_delivery_link_created", ("payment_link_id", "created_at")),
)


def _create_link_table():
    op.create_table(
        LINK_TABLE,
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("public_id", sa.String(length=48), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_order_id", sa.String(length=18), nullable=True),
        sa.Column("provider_reference", sa.String(length=160), nullable=True),
        sa.Column("provider_operation_id", sa.String(length=160), nullable=True),
        sa.Column("provider_security_token", EncryptedString(length=512), nullable=True),
        sa.Column("provider_last_event_id", sa.String(length=80), nullable=True),
        sa.Column("payment_url", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_order_id"),
        sa.UniqueConstraint("public_id"),
    )


def _create_delivery_table():
    op.create_table(
        DELIVERY_TABLE,
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("payment_link_id", sa.BigInteger(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("recipient_type", sa.String(length=24), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=True),
        sa.Column("recipient_registry_id", sa.Integer(), nullable=True),
        sa.Column("recipient_name", sa.String(length=255), nullable=True),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["payment_link_id"], [f"{LINK_TABLE}.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recipient_registry_id"], ["business_registries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_all_indexes():
    for name, columns in LINK_INDEXES:
        op.create_index(name, LINK_TABLE, list(columns))
    for name, columns in DELIVERY_INDEXES:
        op.create_index(name, DELIVERY_TABLE, list(columns))


def _validate_existing_table(inspector, table_name, required_columns):
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    missing_columns = sorted(required_columns - existing_columns)
    if missing_columns:
        raise RuntimeError(
            f"La tabella preesistente {table_name} e' incompleta; mancano: {', '.join(missing_columns)}"
        )
    primary_key = set(inspector.get_pk_constraint(table_name).get("constrained_columns") or ())
    if primary_key != {"id"}:
        raise RuntimeError(f"La tabella preesistente {table_name} non ha la primary key attesa su id")


def _validate_unique_business_keys(inspector):
    unique_index_columns = {
        tuple(index.get("column_names") or ())
        for index in inspector.get_indexes(LINK_TABLE)
        if index.get("unique")
    }
    unique_constraints = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints(LINK_TABLE)
    }
    available = unique_index_columns | unique_constraints
    missing = [column for column in ("public_id", "provider_order_id") if (column,) not in available]
    if missing:
        raise RuntimeError(
            "La tabella preesistente administration_payment_links non garantisce l'unicita' di: "
            + ", ".join(missing)
        )


def _ensure_equivalent_indexes(bind, table_name, definitions):
    inspector = sa.inspect(bind)
    existing = {
        tuple(index.get("column_names") or ())
        for index in inspector.get_indexes(table_name)
    }
    for name, columns in definitions:
        if tuple(columns) not in existing:
            op.create_index(name, table_name, list(columns))
            existing.add(tuple(columns))


def _insert_menu():
    op.execute(sa.text("""
        INSERT INTO menus (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
        SELECT
            'Manda un link di pagamento',
            40,
            COALESCE((SELECT MAX(child.sort_order) + 1 FROM menus AS child WHERE child.parent_id = parent.id), 1),
            parent.id,
            '/administration/payment-links',
            true,
            true,
            'link'
        FROM menus AS parent
        WHERE lower(parent.name) = lower('Amministrazione')
          AND parent.parent_id IS NULL
          AND NOT EXISTS (SELECT 1 FROM menus WHERE route = '/administration/payment-links')
        ORDER BY parent.id
        LIMIT 1
    """))


def upgrade():
    # In alcuni ambienti db.create_all ha materializzato queste due tabelle prima
    # dell'esecuzione Alembic. Lo schema viene validato e riutilizzato senza toccare i dati.
    if op.get_context().as_sql:
        _create_link_table()
        _create_delivery_table()
        _create_all_indexes()
        _insert_menu()
        return

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    link_exists = inspector.has_table(LINK_TABLE)
    delivery_exists = inspector.has_table(DELIVERY_TABLE)

    if link_exists:
        _validate_existing_table(inspector, LINK_TABLE, LINK_COLUMNS)
        _validate_unique_business_keys(inspector)
    else:
        _create_link_table()

    inspector = sa.inspect(bind)
    if delivery_exists:
        _validate_existing_table(inspector, DELIVERY_TABLE, DELIVERY_COLUMNS)
    else:
        _create_delivery_table()

    _ensure_equivalent_indexes(bind, LINK_TABLE, LINK_INDEXES)
    _ensure_equivalent_indexes(bind, DELIVERY_TABLE, DELIVERY_INDEXES)
    _insert_menu()


def downgrade():
    op.execute(sa.text("DELETE FROM menus WHERE route = '/administration/payment-links'"))
    op.execute(sa.text(f'DROP TABLE IF EXISTS "{DELIVERY_TABLE}"'))
    op.execute(sa.text(f'DROP TABLE IF EXISTS "{LINK_TABLE}"'))
