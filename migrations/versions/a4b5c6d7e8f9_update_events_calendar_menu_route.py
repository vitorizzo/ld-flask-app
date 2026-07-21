"""update events calendar menu route

Revision ID: a4b5c6d7e8f9
Revises: 93a4b5c6d7e8
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa


revision = "a4b5c6d7e8f9"
down_revision = "93a4b5c6d7e8"
branch_labels = None
depends_on = None


def _update_route(connection, route):
    connection.execute(
        sa.text(
            """
            UPDATE menus AS child
               SET route = :route
              FROM menus AS parent
             WHERE child.parent_id = parent.id
               AND lower(child.name) = lower('Calendario Eventi')
               AND lower(parent.name) = lower('Eventi')
            """
        ),
        {"route": route},
    )


def upgrade():
    _update_route(op.get_bind(), "/events/")


def downgrade():
    _update_route(op.get_bind(), "/calendario_eventi")
