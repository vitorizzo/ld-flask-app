"""add cash customer registry links

Revision ID: 3d4e5f607182
Revises: 2c3d4e5f6071
Create Date: 2026-07-14 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "3d4e5f607182"
down_revision = "2c3d4e5f6071"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cash_customer_registry_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cash_customer_id", sa.Integer(), nullable=False),
        sa.Column("registry_id", sa.Integer(), nullable=False),
        sa.Column("match_source", sa.String(length=30), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cash_customer_id"], ["cash_customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["registry_id"], ["business_registries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("registry_id", name="uq_cash_customer_registry_link_registry"),
    )
    op.create_index("ix_cash_customer_registry_link_customer", "cash_customer_registry_links", ["cash_customer_id"], unique=False)
    op.execute(sa.text("""
        INSERT INTO cash_customer_registry_links (cash_customer_id, registry_id, match_source)
        SELECT MIN(cc.id), br.id, 'source_code'
        FROM business_registries br
        JOIN cash_customers cc ON cc.codice_cliente = br.source_code
        WHERE br.kind = 'customer' AND br.source_code IS NOT NULL
        GROUP BY br.id
        HAVING COUNT(DISTINCT cc.id) = 1
    """))
    op.execute(sa.text("""
        INSERT INTO cash_customer_registry_links (cash_customer_id, registry_id, match_source)
        SELECT MIN(cc.id), br.id, 'vat_number'
        FROM business_registries br
        JOIN cash_customers cc ON cc.partita_iva = br.vat_number
        LEFT JOIN cash_customer_registry_links link ON link.registry_id = br.id
        WHERE br.kind = 'customer' AND br.vat_number IS NOT NULL AND link.id IS NULL
        GROUP BY br.id
        HAVING COUNT(DISTINCT cc.id) = 1
    """))


def downgrade():
    op.drop_index("ix_cash_customer_registry_link_customer", table_name="cash_customer_registry_links")
    op.drop_table("cash_customer_registry_links")
