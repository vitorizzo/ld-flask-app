"""Move customer and issued check menus under Administration."""
from alembic import op
import sqlalchemy as sa

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def _id(conn, name, parent_id=None):
    clause = "parent_id IS NULL" if parent_id is None else "parent_id = :parent_id"
    params = {"name": name}
    if parent_id is not None:
        params["parent_id"] = parent_id
    return conn.execute(sa.text(f"SELECT id FROM menus WHERE lower(name)=lower(:name) AND {clause} ORDER BY id LIMIT 1"), params).scalar()


def upgrade():
    conn = op.get_bind()
    administration_id = _id(conn, "Amministrazione")
    if not administration_id:
        return
    checks_id = _id(conn, "Gestione assegni", administration_id)
    if not checks_id:
        checks_id = conn.execute(sa.text("""
            INSERT INTO menus (name, weight, sort_order, parent_id, route, is_active, is_visible, item_type)
            VALUES ('Gestione assegni', 40, 80, :parent_id, NULL, true, true, 'link') RETURNING id
        """), {"parent_id": administration_id}).scalar()

    for old_names, target_name, route, sort_order in (
        (("Gestione Assegni Clienti", "Assegni clienti"), "Assegni clienti", "/cassa/agenda/checks", 10),
        (("Gestione Assegni Emessi", "Assegni emessi"), "Assegni emessi", "/cassa/agenda/issued-checks", 20),
    ):
        target = conn.execute(sa.text("SELECT id FROM menus WHERE route=:route ORDER BY id LIMIT 1"), {"route": route}).scalar()
        if target:
            conn.execute(sa.text("UPDATE menus SET name=:name, parent_id=:parent_id, sort_order=:sort_order, route=:route, is_active=true, is_visible=true WHERE id=:id"), {
                "name": target_name, "parent_id": checks_id, "sort_order": sort_order, "route": route, "id": target,
            })
        else:
            for old_name in old_names:
                target = conn.execute(sa.text("SELECT id FROM menus WHERE lower(name)=lower(:name) ORDER BY id LIMIT 1"), {"name": old_name}).scalar()
                if target:
                    conn.execute(sa.text("UPDATE menus SET name=:name, parent_id=:parent_id, sort_order=:sort_order, route=:route WHERE id=:id"), {
                        "name": target_name, "parent_id": checks_id, "sort_order": sort_order, "route": route, "id": target,
                    })
                    break
        conn.execute(sa.text("""
            DELETE FROM menus duplicate
            WHERE duplicate.route=:route AND duplicate.id <> (
                SELECT id FROM menus WHERE route=:route ORDER BY id LIMIT 1
            )
        """), {"route": route})


def downgrade():
    # Keep the entries available; restore their former parent when present.
    conn = op.get_bind()
    agenda_id = _id(conn, "Gestione Agenda", _id(conn, "Amministrazione"))
    if agenda_id:
        conn.execute(sa.text("UPDATE menus SET parent_id=:parent_id, name=:name WHERE route=:route"), {"parent_id": agenda_id, "name": "Gestione Assegni Clienti", "route": "/cassa/agenda/checks"})
        conn.execute(sa.text("UPDATE menus SET parent_id=:parent_id, name=:name WHERE route=:route"), {"parent_id": agenda_id, "name": "Gestione Assegni Emessi", "route": "/cassa/agenda/issued-checks"})
