"""add supplier orders

Revision ID: a0b1c2d3e4f5
Revises: 9c0d1e2f3a4b
Create Date: 2026-07-09 15:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a0b1c2d3e4f5"
down_revision = "9c0d1e2f3a4b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "supplier_order_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_supplier_order_groups_name"),
    )
    op.create_index("ix_supplier_order_groups_active_name", "supplier_order_groups", ["is_active", "name"], unique=False)

    op.create_table(
        "supplier_order_group_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("cod_art", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cod_art"], ["articoli.cod_art"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["supplier_order_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "cod_art", name="uq_supplier_order_group_items_group_cod_art"),
    )
    op.create_index("ix_supplier_order_group_items_cod_art", "supplier_order_group_items", ["cod_art"], unique=False)
    op.create_index("ix_supplier_order_group_items_group_sort", "supplier_order_group_items", ["group_id", "sort_order"], unique=False)

    conn = op.get_bind()
    parent_id = conn.execute(
        sa.text(
            """
            SELECT id
            FROM menus
            WHERE lower(name) IN ('strumenti', 'tools')
              AND parent_id IS NULL
            ORDER BY id
            LIMIT 1
            """
        )
    ).scalar()

    existing = conn.execute(sa.text("SELECT id FROM menus WHERE route = '/supplier-orders'")).scalar()
    if existing:
        conn.execute(
            sa.text(
                """
                UPDATE menus
                SET name = 'Ordini fornitori',
                    weight = 40,
                    sort_order = 85,
                    parent_id = :parent_id,
                    is_active = true,
                    is_visible = true,
                    item_type = 'link'
                WHERE id = :id
                """
            ),
            {"id": existing, "parent_id": parent_id},
        )
    else:
        conn.execute(
            sa.text(
                """
                INSERT INTO menus (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
                VALUES ('Ordini fornitori', 40, 85, :parent_id, '/supplier-orders', true, true, 'link')
                """
            ),
            {"parent_id": parent_id},
        )


def downgrade():
    op.execute("DELETE FROM menus WHERE route = '/supplier-orders'")
    op.drop_index("ix_supplier_order_group_items_group_sort", table_name="supplier_order_group_items")
    op.drop_index("ix_supplier_order_group_items_cod_art", table_name="supplier_order_group_items")
    op.drop_table("supplier_order_group_items")
    op.drop_index("ix_supplier_order_groups_active_name", table_name="supplier_order_groups")
    op.drop_table("supplier_order_groups")
