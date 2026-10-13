"""Independent fill, text and border colors for supplier section badges."""
from alembic import op
import sqlalchemy as sa
from tools.supplier_migration_compat import add_column_if_needed

revision = 's4b5c6d7e8f9'
down_revision = 'r3a4b5c6d7e8'
branch_labels = None
depends_on = None


def upgrade():
    for name in ('badge_fill', 'badge_text', 'badge_border'):
        add_column_if_needed('supplier_board_sections', sa.Column(name, sa.String(7), nullable=True))


def downgrade():
    with op.batch_alter_table('supplier_board_sections') as batch:
        for name in ('badge_border', 'badge_text', 'badge_fill'): batch.drop_column(name)
