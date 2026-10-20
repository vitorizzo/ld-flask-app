import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask
from flask_login import LoginManager

from extensions import db
from models import (
    AgentCustomer,
    AgentCustomerZone,
    BusinessRegistry,
    FunctionAccessPolicy,
    Role,
    User,
    UserRole,
)
from routes.settings import settings_bp


class AgentCustomerAssignmentsTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test", SQLALCHEMY_DATABASE_URI="sqlite://")
        db.init_app(self.app)
        self.app.register_blueprint(settings_bp, url_prefix="/settings")
        login = LoginManager(self.app)
        login.user_loader(lambda _user_id: self.admin)
        self.admin = SimpleNamespace(
            id=900,
            is_authenticated=True,
            is_active=True,
            is_anonymous=False,
            max_role_weight=50,
            active_roles=[SimpleNamespace(id=90, name="office", weight=50)],
        )
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        self.role_patch = patch("tools.role_required.get_current_user", return_value=self.admin)
        self.role_patch.start()
        self.tables = [
            Role.__table__, User.__table__, UserRole.__table__, FunctionAccessPolicy.__table__,
            BusinessRegistry.__table__, AgentCustomerZone.__table__, AgentCustomer.__table__,
        ]
        db.metadata.create_all(db.engine, tables=self.tables)
        agent_role = Role(name="agente", weight=30)
        self.office_role = Role(name="office", weight=50)
        self.agent = User(name="Ada", surname="Agenti", email="agent@example.com", password="hash")
        db.session.add_all([agent_role, self.office_role, self.agent])
        db.session.flush()
        db.session.add(UserRole(
            user_id=self.agent.id,
            role_id=agent_role.id,
            type="lifetime",
            valid_from=datetime.now() - timedelta(days=1),
        ))
        self.north = BusinessRegistry(
            kind="customer", source="teamsystem", source_code="C001", display_name="Cliente Nord",
            zone_code="N", zone_description="Nord", is_active=True,
        )
        self.outside = BusinessRegistry(
            kind="customer", source="teamsystem", source_code="C002", display_name="Cliente Sud",
            zone_code="S", zone_description="Sud", is_active=True,
        )
        db.session.add_all([self.north, self.outside])
        db.session.flush()
        self.outside_id = self.outside.id
        db.session.commit()
        with self.client.session_transaction() as session:
            session["_user_id"] = "900"
            session["_fresh"] = True

    def tearDown(self):
        self.role_patch.stop()
        db.session.remove()
        db.metadata.drop_all(db.engine, tables=reversed(self.tables))
        self.context.pop()

    def test_save_and_read_zone_and_individual_customer_assignments(self):
        response = self.client.put(
            f"/settings/api/agent-customers/{self.agent.id}",
            json={"zone_codes": ["N"], "customer_ids": [self.outside_id]},
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["zone_count"], 1)
        self.assertEqual(response.json["customer_count"], 1)
        self.assertEqual(AgentCustomerZone.query.one().zone_description, "Nord")
        self.assertEqual(AgentCustomer.query.one().registry_id, self.outside_id)

        response = self.client.get(f"/settings/api/agent-customers?user_id={self.agent.id}")
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["zone_codes"], ["N"])
        self.assertEqual(response.json["customer_ids"], [self.outside_id])
        self.assertEqual(response.json["assigned_customers"][0]["name"], "Cliente Sud")

    def test_invalid_customer_does_not_replace_existing_assignments(self):
        db.session.add(AgentCustomerZone(user_id=self.agent.id, zone_code="N", zone_description="Nord"))
        db.session.commit()
        response = self.client.put(
            f"/settings/api/agent-customers/{self.agent.id}",
            json={"zone_codes": ["S"], "customer_ids": [999999]},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual([row.zone_code for row in AgentCustomerZone.query.all()], ["N"])
        self.assertEqual(AgentCustomer.query.count(), 0)

    def test_search_is_limited_to_active_customer_records(self):
        response = self.client.get(
            f"/settings/api/agent-customers/search?user_id={self.agent.id}&q=Cliente"
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual({row["code"] for row in response.json["customers"]}, {"C001", "C002"})

    def test_removed_zone_remains_visible_until_the_assignment_is_cleared(self):
        db.session.add(AgentCustomerZone(
            user_id=self.agent.id,
            zone_code="OLD",
            zone_description="Zona archiviata",
        ))
        db.session.commit()
        response = self.client.get(f"/settings/api/agent-customers?user_id={self.agent.id}")
        archived = next(row for row in response.json["zones"] if row["code"] == "OLD")
        self.assertFalse(archived["available"])
        self.assertEqual(archived["description"], "Zona archiviata")
        response = self.client.put(
            f"/settings/api/agent-customers/{self.agent.id}",
            json={"zone_codes": [], "customer_ids": []},
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(AgentCustomerZone.query.count(), 0)


if __name__ == "__main__":
    unittest.main()
