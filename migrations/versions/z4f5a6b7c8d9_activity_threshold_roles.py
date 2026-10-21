"""Persist role identity for activity minimum-weight targets."""
from alembic import op
import sqlalchemy as sa

revision = "z4f5a6b7c8d9"
down_revision = "z3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("operational_activities", sa.Column("target_min_role_id", sa.Integer(), nullable=True))
    op.add_column("operational_activities", sa.Column("result_min_role_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_activity_target_min_role", "operational_activities", "roles", ["target_min_role_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_activity_result_min_role", "operational_activities", "roles", ["result_min_role_id"], ["id"], ondelete="SET NULL")


def downgrade():
    op.drop_constraint("fk_activity_result_min_role", "operational_activities", type_="foreignkey")
    op.drop_constraint("fk_activity_target_min_role", "operational_activities", type_="foreignkey")
    op.drop_column("operational_activities", "result_min_role_id")
    op.drop_column("operational_activities", "target_min_role_id")
