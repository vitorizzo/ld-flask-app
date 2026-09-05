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
    op.create_table(
        "customer_collaborator_activation_requests",
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
    op.create_index(
        "ix_customer_collaborator_request_requester_status",
        "customer_collaborator_activation_requests",
        ["requester_user_id", "status"],
    )
    op.create_index(
        "ix_customer_collaborator_request_registry_status",
        "customer_collaborator_activation_requests",
        ["registry_id", "status"],
    )
    op.create_index(
        "ix_customer_collaborator_request_collaborator_status",
        "customer_collaborator_activation_requests",
        ["collaborator_user_id", "status"],
    )


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
