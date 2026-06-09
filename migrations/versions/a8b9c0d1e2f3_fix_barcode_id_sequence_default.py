"""fix barcode id sequence default

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-06-09 00:00:00.000000

"""
from alembic import op


revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SEQUENCE IF NOT EXISTS barcode_id_seq")
    op.execute("SELECT setval('barcode_id_seq', COALESCE((SELECT MAX(id) FROM barcode), 0) + 1, false)")
    op.execute("ALTER SEQUENCE barcode_id_seq OWNED BY barcode.id")
    op.execute("ALTER TABLE barcode ALTER COLUMN id SET DEFAULT nextval('barcode_id_seq'::regclass)")


def downgrade():
    op.execute("ALTER TABLE barcode ALTER COLUMN id DROP DEFAULT")
