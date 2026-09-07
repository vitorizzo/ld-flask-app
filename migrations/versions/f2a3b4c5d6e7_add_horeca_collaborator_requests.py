"""add horeca collaborator activation requests

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa


revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    table_name = "customer_collaborator_activation_requests"
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("requester_user_id", sa.Integer(), nullable=False),
            sa.Column("collaborator_user_id", sa.Integer(), nullable=False),
            sa.Column("registry_id", sa.Integer(), nullable=False),
            sa.Column("support_ticket_id", sa.Integer(), nullable=True),
            sa.Column("access_scope", sa.String(length=20), server_default="both", nullable=False),
            sa.Column("status", sa.String(length=30), server_default="pending", nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["collaborator_user_id"], ["user.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["registry_id"], ["business_registries.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["requester_user_id"], ["user.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["user.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["support_ticket_id"], ["support_tickets.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("support_ticket_id", name="uq_customer_collaborator_request_ticket"),
        )
        existing_indexes = set()
    else:
        required_columns = {
            "id", "requester_user_id", "collaborator_user_id", "registry_id",
            "support_ticket_id", "access_scope", "status", "notes", "reviewed_at",
            "reviewed_by_user_id", "created_at", "updated_at",
        }
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing_columns = sorted(required_columns - existing_columns)
        if missing_columns:
            raise RuntimeError(
                f"La tabella {table_name} esiste ma è incompleta; colonne mancanti: "
                + ", ".join(missing_columns)
            )
        existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}

    indexes = {
        "ix_customer_collaborator_request_requester_status": ["requester_user_id", "status"],
        "ix_customer_collaborator_request_registry_status": ["registry_id", "status"],
        "ix_customer_collaborator_request_collaborator_status": ["collaborator_user_id", "status"],
    }
    for index_name, columns in indexes.items():
        if index_name not in existing_indexes:
            op.create_index(index_name, table_name, columns)


def downgrade():
    op.drop_index(
        "ix_customer_collaborator_request_collaborator_status",
        table_name="customer_collaborator_activation_requests",
    )
    op.drop_index(
        "ix_customer_collaborator_request_registry_status",
        table_name="customer_collaborator_activation_requests",
    )
    op.drop_index(
        "ix_customer_collaborator_request_requester_status",
        table_name="customer_collaborator_activation_requests",
    )
    op.drop_table("customer_collaborator_activation_requests")
