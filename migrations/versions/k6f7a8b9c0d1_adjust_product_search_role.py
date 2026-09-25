"""Make the warehouse product search available to staff roles."""
from alembic import op
import sqlalchemy as sa

revision = "k6f7a8b9c0d1"
down_revision = "k5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE menus SET weight=30
        WHERE route='/search/elenco-prodotti'
           OR id=(SELECT id FROM menus WHERE lower(name)=lower('Ricerche')
                  AND parent_id=(SELECT id FROM menus WHERE lower(name)=lower('Strumenti') AND parent_id IS NULL LIMIT 1)
                  LIMIT 1)
    """))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE menus SET weight=40
        WHERE route='/search/elenco-prodotti'
           OR id=(SELECT id FROM menus WHERE lower(name)=lower('Ricerche')
                  AND parent_id=(SELECT id FROM menus WHERE lower(name)=lower('Strumenti') AND parent_id IS NULL LIMIT 1)
                  LIMIT 1)
    """))
