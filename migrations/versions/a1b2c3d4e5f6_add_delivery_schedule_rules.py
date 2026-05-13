"""add delivery schedule rules

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-05-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("delivery_routes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("frequency", sa.String(length=20), nullable=False, server_default="weekly"))
        batch_op.add_column(sa.Column("second_weekday", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("second_time", sa.Time(), nullable=True))
        batch_op.add_column(sa.Column("frequency_anchor_date", sa.Date(), nullable=True))

    op.create_table(
        "delivery_schedule_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("target_weekday", sa.Integer(), nullable=True),
        sa.Column("target_time", sa.Time(), nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False, server_default="weekly"),
        sa.Column("second_weekday", sa.Integer(), nullable=True),
        sa.Column("second_time", sa.Time(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["delivery_routes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("delivery_schedule_rules", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_delivery_schedule_rules_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_delivery_schedule_rules_route_id"), ["route_id"], unique=False)


def downgrade():
    with op.batch_alter_table("delivery_schedule_rules", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_delivery_schedule_rules_route_id"))
        batch_op.drop_index(batch_op.f("ix_delivery_schedule_rules_is_active"))
    op.drop_table("delivery_schedule_rules")
    with op.batch_alter_table("delivery_routes", schema=None) as batch_op:
        batch_op.drop_column("frequency_anchor_date")
        batch_op.drop_column("second_time")
        batch_op.drop_column("second_weekday")
        batch_op.drop_column("frequency")
