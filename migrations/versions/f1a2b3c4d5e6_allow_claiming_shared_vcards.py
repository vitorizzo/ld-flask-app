"""allow claiming shared vcards after login

Revision ID: f1a2b3c4d5e6
Revises: ce5f60718293
Create Date: 2026-08-17
"""

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "ce5f60718293"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("registry_contact_import_intents") as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(sa.Column("claim_token_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("claim_expires_at", sa.DateTime(), nullable=True))


def downgrade():
    op.execute("DELETE FROM registry_contact_import_intents WHERE user_id IS NULL")
    with op.batch_alter_table("registry_contact_import_intents") as batch_op:
        batch_op.drop_column("claim_expires_at")
        batch_op.drop_column("claim_token_hash")
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
