"""normalize issued check fields

Revision ID: b7e4d2c9a8f1
Revises: 9f2c8b7d4a61
Create Date: 2026-05-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b7e4d2c9a8f1"
down_revision = "9f2c8b7d4a61"
branch_labels = None
depends_on = None


def _table_columns():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"]: column for column in inspector.get_columns("cash_issued_checks")}


def _table_indexes():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes("cash_issued_checks")}


def upgrade():
    columns = _table_columns()
    indexes = _table_indexes()

    with op.batch_alter_table("cash_issued_checks", schema=None) as batch_op:
        if "flag" not in columns:
            batch_op.add_column(sa.Column("flag", sa.String(length=2), nullable=False, server_default="*"))

        if "due_date" in columns:
            batch_op.alter_column("due_date", existing_type=sa.Date(), nullable=True)

        if "registered_at" not in columns:
            batch_op.add_column(sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True))

        if "ix_cash_issued_checks_registered_at" not in indexes:
            batch_op.create_index(
                batch_op.f("ix_cash_issued_checks_registered_at"),
                ["registered_at"],
                unique=False,
            )

    op.execute(
        "UPDATE cash_issued_checks "
        "SET flag = COALESCE(NULLIF(flag, ''), '*')"
    )
    op.execute(
        "UPDATE cash_issued_checks "
        "SET status = CASE "
        "WHEN status = 'paid' THEN 'rientrato' "
        "WHEN status = 'delivered' THEN 'registrato' "
        "WHEN status = 'cancelled' THEN 'rientrato' "
        "WHEN status IN ('emesso', 'registrato', 'rientrato') THEN status "
        "ELSE 'emesso' END"
    )


def downgrade():
    # This repair migration is intentionally non-destructive on downgrade: it may
    # have only reconciled databases where revision 9f2c8b7d4a61 was already
    # stamped before the issued-check fields were expanded.
    pass
