"""Add agent customer and zone assignments."""
from alembic import op
import sqlalchemy as sa


revision = "z3e4f5a6b7c8"
down_revision = "z2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_customer_zones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("zone_code", sa.String(length=32), nullable=False),
        sa.Column("zone_description", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "zone_code", name="uq_agent_customer_zone_user_code"),
    )
    op.create_index("ix_agent_customer_zones_user", "agent_customer_zones", ["user_id"])

    op.create_table(
        "agent_customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("registry_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["registry_id"], ["business_registries.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "registry_id", name="uq_agent_customer_user_registry"),
    )
    op.create_index("ix_agent_customers_user", "agent_customers", ["user_id"])


def downgrade():
    op.drop_index("ix_agent_customers_user", table_name="agent_customers")
    op.drop_table("agent_customers")
    op.drop_index("ix_agent_customer_zones_user", table_name="agent_customer_zones")
    op.drop_table("agent_customer_zones")
