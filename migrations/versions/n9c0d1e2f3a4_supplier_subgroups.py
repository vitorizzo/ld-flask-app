"""User-defined supplier product subgroups and matrix assignments."""
from alembic import op
import sqlalchemy as sa
from tools.supplier_migration_compat import create_table_if_needed, create_index_if_needed

revision = "n9c0d1e2f3a4"
down_revision = "m8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade():
    create_table_if_needed("supplier_order_subgroups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("supplier_order_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.UniqueConstraint("group_id", "name", name="uq_supplier_subgroup_name"), unique_keys=[('group_id', 'name')])
    create_index_if_needed("ix_supplier_order_subgroups_group_id", "supplier_order_subgroups", ["group_id"])
    create_table_if_needed("supplier_order_subgroup_matrices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("supplier_order_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subgroup_id", sa.Integer(), sa.ForeignKey("supplier_order_subgroups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matrix_code", sa.String(255), nullable=False),
        sa.UniqueConstraint("group_id", "matrix_code", name="uq_supplier_subgroup_matrix"), unique_keys=[('group_id', 'matrix_code')])
    create_index_if_needed("ix_supplier_order_subgroup_matrices_group_id", "supplier_order_subgroup_matrices", ["group_id"])
    create_index_if_needed("ix_supplier_order_subgroup_matrices_subgroup_id", "supplier_order_subgroup_matrices", ["subgroup_id"])


def downgrade():
    op.drop_table("supplier_order_subgroup_matrices")
    op.drop_table("supplier_order_subgroups")
