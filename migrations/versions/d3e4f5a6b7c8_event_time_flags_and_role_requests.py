"""event time flags and role activation requests

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-11 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("events", sa.Column("starts_time_known", sa.Boolean(), nullable=True))
    op.add_column("events", sa.Column("ends_time_known", sa.Boolean(), nullable=True))
    op.execute("UPDATE events SET starts_time_known = TRUE WHERE starts_time_known IS NULL")
    op.execute("UPDATE events SET ends_time_known = CASE WHEN ends_at IS NULL THEN FALSE ELSE TRUE END WHERE ends_time_known IS NULL")
    op.alter_column("events", "starts_time_known", existing_type=sa.Boolean(), nullable=False)
    op.alter_column("events", "ends_time_known", existing_type=sa.Boolean(), nullable=False)

    op.create_table(
        "role_activation_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("requested_role", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_role_activation_requests_user_id", "role_activation_requests", ["user_id"], unique=False)
    op.create_index("ix_role_activation_requests_status_created", "role_activation_requests", ["status", "created_at"], unique=False)
    op.create_index("ix_role_activation_requests_user_status", "role_activation_requests", ["user_id", "status"], unique=False)


def downgrade():
    op.drop_index("ix_role_activation_requests_user_status", table_name="role_activation_requests")
    op.drop_index("ix_role_activation_requests_status_created", table_name="role_activation_requests")
    op.drop_index("ix_role_activation_requests_user_id", table_name="role_activation_requests")
    op.drop_table("role_activation_requests")
    op.drop_column("events", "ends_time_known")
    op.drop_column("events", "starts_time_known")
