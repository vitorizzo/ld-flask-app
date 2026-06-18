"""add pos validity dates

Revision ID: 4d5e6f708192
Revises: 3c4d5e6f7081
Create Date: 2026-06-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "4d5e6f708192"
down_revision = "3c4d5e6f7081"
branch_labels = None
depends_on = None


def _has_column(bind, table_name, column_name):
    inspector = inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _has_index(bind, table_name, index_name):
    inspector = inspect(bind)
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def upgrade():
    bind = op.get_bind()

    if not _has_column(bind, "pos_devices", "valid_from"):
        op.add_column("pos_devices", sa.Column("valid_from", sa.Date(), nullable=True))
    if not _has_column(bind, "pos_devices", "valid_to"):
        op.add_column("pos_devices", sa.Column("valid_to", sa.Date(), nullable=True))
    if not _has_index(bind, "pos_devices", "ix_pos_devices_valid_from"):
        op.create_index("ix_pos_devices_valid_from", "pos_devices", ["valid_from"], unique=False)
    if not _has_index(bind, "pos_devices", "ix_pos_devices_valid_to"):
        op.create_index("ix_pos_devices_valid_to", "pos_devices", ["valid_to"], unique=False)

    if not _has_column(bind, "pos_circuits", "valid_from"):
        op.add_column("pos_circuits", sa.Column("valid_from", sa.Date(), nullable=True))
    if not _has_column(bind, "pos_circuits", "valid_to"):
        op.add_column("pos_circuits", sa.Column("valid_to", sa.Date(), nullable=True))
    if not _has_index(bind, "pos_circuits", "ix_pos_circuits_valid_from"):
        op.create_index("ix_pos_circuits_valid_from", "pos_circuits", ["valid_from"], unique=False)
    if not _has_index(bind, "pos_circuits", "ix_pos_circuits_valid_to"):
        op.create_index("ix_pos_circuits_valid_to", "pos_circuits", ["valid_to"], unique=False)


def downgrade():
    bind = op.get_bind()

    if _has_index(bind, "pos_circuits", "ix_pos_circuits_valid_to"):
        op.drop_index("ix_pos_circuits_valid_to", table_name="pos_circuits")
    if _has_index(bind, "pos_circuits", "ix_pos_circuits_valid_from"):
        op.drop_index("ix_pos_circuits_valid_from", table_name="pos_circuits")
    if _has_column(bind, "pos_circuits", "valid_to"):
        op.drop_column("pos_circuits", "valid_to")
    if _has_column(bind, "pos_circuits", "valid_from"):
        op.drop_column("pos_circuits", "valid_from")

    if _has_index(bind, "pos_devices", "ix_pos_devices_valid_to"):
        op.drop_index("ix_pos_devices_valid_to", table_name="pos_devices")
    if _has_index(bind, "pos_devices", "ix_pos_devices_valid_from"):
        op.drop_index("ix_pos_devices_valid_from", table_name="pos_devices")
    if _has_column(bind, "pos_devices", "valid_to"):
        op.drop_column("pos_devices", "valid_to")
    if _has_column(bind, "pos_devices", "valid_from"):
        op.drop_column("pos_devices", "valid_from")
