"""Add app preferences table

Revision ID: 3c4d5e6f7081
Revises: 2b3c4d5e6f70
Create Date: 2026-06-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3c4d5e6f7081"
down_revision = "2b3c4d5e6f70"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False, server_default="Generale"),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("value_type", sa.String(length=20), nullable=False, server_default="text"),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("secret_value", sa.String(length=4096), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_app_preferences_key"),
    )
    op.create_index("ix_app_preferences_category_sort", "app_preferences", ["category", "sort_order"], unique=False)


def downgrade():
    op.drop_index("ix_app_preferences_category_sort", table_name="app_preferences")
    op.drop_table("app_preferences")
