"""Associate each menu item with its minimum role."""
from alembic import op
import sqlalchemy as sa

revision = "z1c2d3e4f5a6"
down_revision = "y0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("menus") as batch_op:
        batch_op.add_column(sa.Column("minimum_role_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_menus_minimum_role_id_roles", "roles", ["minimum_role_id"], ["id"], ondelete="SET NULL")
        batch_op.create_index("ix_menus_minimum_role_id", ["minimum_role_id"])
    bind = op.get_bind()
    legacy = {20: "customer", 30: "staff", 40: "office", 100: "admin", 500: "dev", 900: "dev", 999: "dev", 1000: "dev"}
    for weight, role_name in legacy.items():
        if role_name == "dev":
            role_predicate = "lower(name) IN ('dev', 'developer')"
        else:
            role_predicate = "lower(name) = :role_name"
        statement = sa.text(f"UPDATE menus SET minimum_role_id = (SELECT id FROM roles WHERE {role_predicate} LIMIT 1) WHERE weight = :weight AND minimum_role_id IS NULL")
        bind.execute(statement, {"role_name": role_name, "weight": weight})


def downgrade():
    with op.batch_alter_table("menus") as batch_op:
        batch_op.drop_index("ix_menus_minimum_role_id")
        batch_op.drop_constraint("fk_menus_minimum_role_id_roles", type_="foreignkey")
        batch_op.drop_column("minimum_role_id")
