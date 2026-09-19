"""Seed the company cards that previously existed as agenda options."""
from alembic import op
import sqlalchemy as sa

revision = "i2b3c4d5e6f7"
down_revision = "i1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    table = sa.table(
        "company_credit_cards",
        sa.column("name", sa.String()),
        sa.column("is_active", sa.Boolean()),
    )
    conn = op.get_bind()
    for name in ("Carta aziendale 1", "Carta aziendale 2"):
        exists = conn.execute(
            sa.select(table.c.name).where(sa.func.lower(table.c.name) == name.lower())
        ).first()
        if not exists:
            conn.execute(table.insert().values(name=name, is_active=True))


def downgrade():
    op.execute(
        sa.text(
            "DELETE FROM company_credit_cards "
            "WHERE name IN ('Carta aziendale 1', 'Carta aziendale 2')"
        )
    )
