"""schede prodotti text fields

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-06-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("schede_prodotti", schema=None) as batch_op:
        batch_op.alter_column(
            "descrizione",
            existing_type=sa.String(length=5000),
            type_=sa.Text(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "short",
            existing_type=sa.String(length=5000),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade():
    with op.batch_alter_table("schede_prodotti", schema=None) as batch_op:
        batch_op.alter_column(
            "short",
            existing_type=sa.Text(),
            type_=sa.String(length=5000),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "descrizione",
            existing_type=sa.Text(),
            type_=sa.String(length=5000),
            existing_nullable=True,
        )
