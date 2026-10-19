"""Add configurable role policies for protected functions."""
from alembic import op
import sqlalchemy as sa

revision = "z2d3e4f5a6b7"
down_revision = "z1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "function_access_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("function_key", sa.String(length=200), nullable=False, unique=True),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False, server_default="app"),
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="minimum"),
        sa.Column("minimum_role_id", sa.Integer(), nullable=True),
        sa.Column("allowed_role_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["minimum_role_id"], ["roles.id"], name="fk_function_access_policies_minimum_role_id_roles", ondelete="SET NULL"),
    )


def downgrade():
    op.drop_table("function_access_policies")
