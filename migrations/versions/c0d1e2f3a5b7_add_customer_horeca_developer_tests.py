"""add customer_horeca developer test menu

Revision ID: c0d1e2f3a5b7
Revises: b9c0d1e2f4a6
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa


revision = "c0d1e2f3a5b7"
down_revision = "b9c0d1e2f4a6"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("""
        DO $$
        DECLARE
            developer_id INTEGER;
            test_id INTEGER;
            role_id INTEGER;
            link_id INTEGER;
            root_sort INTEGER;
        BEGIN
            SELECT id INTO developer_id
            FROM menus
            WHERE lower(name) = 'developer' AND parent_id IS NULL
            ORDER BY id
            LIMIT 1;

            IF developer_id IS NULL THEN
                SELECT COALESCE(MAX(sort_order), 0) + 1 INTO root_sort
                FROM menus
                WHERE parent_id IS NULL;
                INSERT INTO menus
                    (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
                VALUES
                    ('Developer', 999, root_sort, NULL, NULL, TRUE, TRUE, 'link')
                RETURNING id INTO developer_id;
            ELSE
                UPDATE menus
                SET weight = 999, is_active = TRUE, is_visible = TRUE
                WHERE id = developer_id;
            END IF;

            SELECT id INTO test_id
            FROM menus
            WHERE lower(name) = 'test' AND parent_id = developer_id AND route IS NULL
            ORDER BY id
            LIMIT 1;
            IF test_id IS NULL THEN
                INSERT INTO menus
                    (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
                VALUES
                    ('Test', 999, 90, developer_id, NULL, TRUE, TRUE, 'link')
                RETURNING id INTO test_id;
            ELSE
                UPDATE menus
                SET name = 'Test', weight = 999, sort_order = 90,
                    is_active = TRUE, is_visible = TRUE, item_type = 'link'
                WHERE id = test_id;
            END IF;

            SELECT id INTO role_id
            FROM menus
            WHERE lower(name) = 'customer_horeca' AND parent_id = test_id AND route IS NULL
            ORDER BY id
            LIMIT 1;
            IF role_id IS NULL THEN
                INSERT INTO menus
                    (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
                VALUES
                    ('customer_horeca', 999, 1, test_id, NULL, TRUE, TRUE, 'link')
                RETURNING id INTO role_id;
            ELSE
                UPDATE menus
                SET name = 'customer_horeca', weight = 999, sort_order = 1,
                    is_active = TRUE, is_visible = TRUE, item_type = 'link'
                WHERE id = role_id;
            END IF;

            SELECT id INTO link_id FROM menus WHERE route = '/customer-account/' ORDER BY id LIMIT 1;
            IF link_id IS NULL THEN
                INSERT INTO menus
                    (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
                VALUES
                    ('Situazione contabile', 999, 1, role_id, '/customer-account/', TRUE, TRUE, 'link');
            ELSE
                UPDATE menus SET name = 'Situazione contabile', weight = 999, sort_order = 1,
                    parent_id = role_id, is_active = TRUE, is_visible = TRUE, item_type = 'link'
                WHERE id = link_id;
            END IF;

            link_id := NULL;
            SELECT id INTO link_id FROM menus WHERE route = '/customer-orders/' ORDER BY id LIMIT 1;
            IF link_id IS NULL THEN
                INSERT INTO menus
                    (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
                VALUES
                    ('Fai un ordine', 999, 2, role_id, '/customer-orders/', TRUE, TRUE, 'link');
            ELSE
                UPDATE menus SET name = 'Fai un ordine', weight = 999, sort_order = 2,
                    parent_id = role_id, is_active = TRUE, is_visible = TRUE, item_type = 'link'
                WHERE id = link_id;
            END IF;

            link_id := NULL;
            SELECT id INTO link_id FROM menus WHERE route = '/customer-orders/status' ORDER BY id LIMIT 1;
            IF link_id IS NULL THEN
                INSERT INTO menus
                    (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
                VALUES
                    ('I miei ordini', 999, 3, role_id, '/customer-orders/status', TRUE, TRUE, 'link');
            ELSE
                UPDATE menus SET name = 'I miei ordini', weight = 999, sort_order = 3,
                    parent_id = role_id, is_active = TRUE, is_visible = TRUE, item_type = 'link'
                WHERE id = link_id;
            END IF;
        END $$;
    """))


def downgrade():
    op.execute(sa.text("""
        DO $$
        DECLARE
            developer_id INTEGER;
            test_id INTEGER;
            role_id INTEGER;
        BEGIN
            DELETE FROM menus
            WHERE route IN ('/customer-account/', '/customer-orders/', '/customer-orders/status');

            SELECT id INTO developer_id
            FROM menus
            WHERE lower(name) = 'developer' AND parent_id IS NULL
            ORDER BY id
            LIMIT 1;
            IF developer_id IS NULL THEN
                RETURN;
            END IF;

            SELECT id INTO test_id
            FROM menus
            WHERE lower(name) = 'test' AND parent_id = developer_id AND route IS NULL
            ORDER BY id
            LIMIT 1;
            IF test_id IS NULL THEN
                RETURN;
            END IF;

            SELECT id INTO role_id
            FROM menus
            WHERE lower(name) = 'customer_horeca' AND parent_id = test_id AND route IS NULL
            ORDER BY id
            LIMIT 1;
            IF role_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM menus WHERE parent_id = role_id) THEN
                DELETE FROM menus WHERE id = role_id;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM menus WHERE parent_id = test_id) THEN
                DELETE FROM menus WHERE id = test_id;
            END IF;
        END $$;
    """))
