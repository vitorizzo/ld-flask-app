"""Add MATRIXWS product price fields and price-list preferences."""
from alembic import op
import sqlalchemy as sa

revision = "j4d5e6f7a8b9"
down_revision = "i3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("articoli", sa.Column("prezzo_1", sa.Numeric(12, 4), nullable=True))
    op.add_column("articoli", sa.Column("prezzo_3", sa.Numeric(12, 4), nullable=True))
    op.add_column("articoli", sa.Column("costo", sa.Numeric(12, 4), nullable=True))
    op.add_column("articoli", sa.Column("aliquota_iva", sa.Numeric(6, 3), nullable=True))
    op.add_column("business_registries", sa.Column("listino_prezzo", sa.String(20), nullable=False, server_default="prezzo3"))
    op.add_column("user", sa.Column("listino_prezzo", sa.String(20), nullable=False, server_default="prezzo3"))


def downgrade():
    op.drop_column("user", "listino_prezzo")
    op.drop_column("business_registries", "listino_prezzo")
    op.drop_column("articoli", "aliquota_iva")
    op.drop_column("articoli", "costo")
    op.drop_column("articoli", "prezzo_3")
    op.drop_column("articoli", "prezzo_1")
