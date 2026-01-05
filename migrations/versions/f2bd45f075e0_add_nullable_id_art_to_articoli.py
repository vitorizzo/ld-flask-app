"""add nullable id_art to articoli

Revision ID: f2bd45f075e0
Revises: b842958acc08
Create Date: 2026-01-05 12:54:12.642472

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2bd45f075e0'
down_revision = 'b842958acc08'
branch_labels = None
depends_on = None


def upgrade():
    # 1) Crea la sequence se non esiste (PostgreSQL)
    op.execute("CREATE SEQUENCE IF NOT EXISTS articoli_id_art_seq")

    # 2) Aggiunge la colonna con default dalla sequence
    with op.batch_alter_table('articoli', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'id_art',
                sa.BigInteger(),
                server_default=sa.text("nextval('articoli_id_art_seq'::regclass)"),
                nullable=True
            )
        )
        batch_op.create_unique_constraint('uq_articoli_id_art', ['id_art'])


def downgrade():
    with op.batch_alter_table('articoli', schema=None) as batch_op:
        batch_op.drop_constraint('uq_articoli_id_art', type_='unique')
        batch_op.drop_column('id_art')

    # (opzionale) elimina la sequence solo se vuoi pulizia completa
    op.execute("DROP SEQUENCE IF EXISTS articoli_id_art_seq")

    # ### end Alembic commands ###
