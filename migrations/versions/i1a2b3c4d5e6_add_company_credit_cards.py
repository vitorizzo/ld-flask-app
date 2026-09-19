"""Add company credit cards managed from settings."""
from alembic import op
import sqlalchemy as sa

revision = "i1a2b3c4d5e6"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "company_credit_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_company_credit_cards_is_active", "company_credit_cards", ["is_active"])


def downgrade():
    op.drop_index("ix_company_credit_cards_is_active", table_name="company_credit_cards")
    op.drop_table("company_credit_cards")
