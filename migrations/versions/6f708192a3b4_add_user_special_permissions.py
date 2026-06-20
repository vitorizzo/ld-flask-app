"""add user special permissions

Revision ID: 6f708192a3b4
Revises: 5e6f708192a3
Create Date: 2026-06-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "6f708192a3b4"
down_revision = "5e6f708192a3"
branch_labels = None
depends_on = None


def _has_table(bind, table_name):
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    bind = op.get_bind()

    if not _has_table(bind, "special_permissions"):
        op.create_table(
            "special_permissions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_special_permissions_code"),
        )
        op.create_index("ix_special_permissions_code", "special_permissions", ["code"], unique=False)

    if not _has_table(bind, "user_special_permissions"):
        op.create_table(
            "user_special_permissions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("permission_id", sa.Integer(), nullable=False),
            sa.Column("valid_from", sa.DateTime(), nullable=False),
            sa.Column("valid_until", sa.DateTime(), nullable=True),
            sa.Column("notes", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["permission_id"], ["special_permissions.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_user_special_permissions_permission_id", "user_special_permissions", ["permission_id"], unique=False)
        op.create_index("ix_user_special_permissions_user_id", "user_special_permissions", ["user_id"], unique=False)


def downgrade():
    bind = op.get_bind()

    if _has_table(bind, "user_special_permissions"):
        op.drop_index("ix_user_special_permissions_user_id", table_name="user_special_permissions")
        op.drop_index("ix_user_special_permissions_permission_id", table_name="user_special_permissions")
        op.drop_table("user_special_permissions")

    if _has_table(bind, "special_permissions"):
        op.drop_index("ix_special_permissions_code", table_name="special_permissions")
        op.drop_table("special_permissions")
