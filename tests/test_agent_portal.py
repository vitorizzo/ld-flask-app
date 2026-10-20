import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask, jsonify
from flask_login import LoginManager

from extensions import db
from models import (
    AgentCustomer,
    AgentCustomerZone,
    BusinessRegistry,
    BusinessRegistryContact,
    BusinessRegistryContactLink,
    CustomerAccountEntry,
    CustomerAccountStatementImport,
    RegistryContact,
    RegistryContactPoint,
    User,
)
from routes.agent_portal import agent_portal_bp


class AgentPortalTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test", SQLALCHEMY_DATABASE_URI="sqlite://")
        db.init_app(self.app)
        self.app.register_blueprint(agent_portal_bp, url_prefix="/agent")
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        self.tables = [
            BusinessRegistry.__table__, User.__table__, AgentCustomer.__table__, AgentCustomerZone.__table__,
            CustomerAccountStatementImport.__table__, CustomerAccountEntry.__table__,
            BusinessRegistryContact.__table__, RegistryContact.__table__, RegistryContactPoint.__table__,
            BusinessRegistryContactLink.__table__,
        ]
        db.metadata.create_all(db.engine, tables=self.tables)
        self.agent = User(name="Ada", surname="Agenti", email="agent@example.com", password="hash")
        self.zone_customer = BusinessRegistry(
            kind="customer", source="teamsystem", source_code="A1", display_name="Cliente zona",
            zone_code="Z1", zone_description="Zona Uno", is_active=True,
        )
        self.direct_customer = BusinessRegistry(
            kind="customer", source="teamsystem", source_code="B1", display_name="Cliente diretto",
            zone_code="Z2", zone_description="Zona Due", is_active=True,
        )
        self.other_customer = BusinessRegistry(
            kind="customer", source="teamsystem", source_code="C1", display_name="Cliente non assegnato",
            zone_code="Z2", zone_description="Zona Due", is_active=True,
        )
        db.session.add_all([self.agent, self.zone_customer, self.direct_customer, self.other_customer])
        db.session.flush()
        self.agent_id = self.agent.id
        self.zone_customer_id = self.zone_customer.id
        self.direct_customer_id = self.direct_customer.id
        self.other_customer_id = self.other_customer.id
        db.session.add_all([
            AgentCustomerZone(user_id=self.agent.id, zone_code="Z1", zone_description="Zona Uno"),
            AgentCustomer(user_id=self.agent.id, registry_id=self.direct_customer.id),
        ])
        self.statement = CustomerAccountStatementImport(
            source_file="statement.csv", trace_file="trace.csv", source_sha256="a" * 64,
            record_count=3, customer_count=3, matched_customer_count=3, unmatched_customer_count=0,
            imported_at=datetime.now() - timedelta(minutes=1),
        )
        db.session.add(self.statement)
        db.session.flush()
        for index, registry, amount in [
            (1, self.zone_customer, Decimal("50.00")),
            (2, self.direct_customer, Decimal("-10.00")),
            (3, self.other_customer, Decimal("100.00")),
        ]:
            db.session.add(CustomerAccountEntry(
                import_id=self.statement.id,
                row_number=index,
                registry_id=registry.id,
                source_customer_code=registry.source_code,
                customer_name=registry.display_name,
                document_number=f"DOC{index}",
                description="Fattura",
                is_balance_relevant=True,
                accounting_side="D" if amount > 0 else "A",
                amount=abs(amount),
                signed_amount=amount,
            ))
        db.session.commit()
        self.agent_user = SimpleNamespace(
            id=self.agent_id,
            is_authenticated=True,
            is_active=True,
            is_anonymous=False,
            active_roles=[SimpleNamespace(name="agente")],
        )
        LoginManager(self.app).user_loader(lambda _user_id: self.agent_user)
        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.agent_id)
            session["_fresh"] = True

        def render_stub(template_name, **context):
            if template_name == "agent_portal/customer_credit.html":
                return jsonify(customers=[{
                    "code": item["registry"].source_code,
                    "name": item["registry"].display_name,
                    "balance": str(item["balance"]),
                    "movement_count": item["movement_count"],
                } for item in context["customers"]], total_exposure=str(context["total_exposure"]))
            if template_name == "agent_portal/customer_credit_detail.html":
                return jsonify(
                    code=context["registry"].source_code,
                    balance=str(context["totals"].balance or 0),
                    visible_entries=len(context["entries"].items),
                )
            return jsonify(template=template_name)

        self.render_patch = patch("routes.agent_portal.render_template", side_effect=render_stub)
        self.render_patch.start()

    def tearDown(self):
        self.render_patch.stop()
        db.session.remove()
        db.metadata.drop_all(db.engine, tables=reversed(self.tables))
        self.context.pop()

    def test_credit_area_contains_direct_and_zone_clients_only(self):
        response = self.client.get("/agent/customers")
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual({row["code"] for row in response.json["customers"]}, {"A1", "B1"})
        balances = {row["code"]: row["balance"] for row in response.json["customers"]}
        self.assertEqual(balances, {"A1": "50.00", "B1": "-10.00"})
        self.assertEqual(response.json["total_exposure"], "50.00")

    def test_credit_search_and_outstanding_filter_include_city_and_total(self):
        response = self.client.get("/agent/customers?q=zona&outstanding=1")
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual([row["code"] for row in response.json["customers"]], ["A1"])
        self.assertEqual(response.json["total_exposure"], "50.00")

    def test_agent_can_add_existing_company_customer_to_personal_registry(self):
        response = self.client.get("/agent/api/customer-search?q=non assegnato")
        self.assertEqual(response.status_code, 200, response.json)
        match = next(item for item in response.json["customers"] if item["code"] == "C1")
        response = self.client.post("/agent/api/customers", json={"registry_id": match["id"]})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertFalse(response.json["already_assigned"])
        response = self.client.post("/agent/api/customers", json={"registry_id": match["id"]})
        self.assertTrue(response.json["already_assigned"])
        self.assertEqual(AgentCustomer.query.filter_by(user_id=self.agent_id, registry_id=match["id"]).count(), 1)
        empty_customer = BusinessRegistry(
            kind="customer", source="teamsystem", source_code="D1", display_name="Cliente senza movimenti",
            zone_code="Z3", zone_description="Zona Tre", is_active=True,
        )
        db.session.add(empty_customer)
        db.session.flush()
        db.session.add(AgentCustomer(user_id=self.agent_id, registry_id=empty_customer.id))
        db.session.commit()
        response = self.client.get("/agent/customers/D1")
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["visible_entries"], 0)

    def test_detail_opens_assigned_customer_and_rejects_unassigned_customer(self):
        response = self.client.get("/agent/customers/B1")
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["code"], "B1")
        self.assertEqual(response.json["balance"], "-10.00")
        response = self.client.get("/agent/customers/C1")
        self.assertEqual(response.status_code, 404)

    def test_agent_adds_contact_to_multiple_assigned_customers_and_company_registry(self):
        response = self.client.post("/agent/api/contacts", json={
            "registry_ids": [self.zone_customer_id, self.direct_customer_id],
            "display_name": "Mario Rossi",
            "role": "Referente ordini",
            "points": [{"contact_type": "mobile", "value": "+39 333 1234567", "is_primary": True}],
        })
        self.assertEqual(response.status_code, 201, response.json)
        contact = RegistryContact.query.one()
        links = BusinessRegistryContactLink.query.order_by(BusinessRegistryContactLink.registry_id).all()
        self.assertEqual([link.registry_id for link in links], [self.zone_customer_id, self.direct_customer_id])
        self.assertTrue(all(link.contact_id == contact.id for link in links))
        self.assertEqual(contact.points[0].value, "+39 333 1234567")

        response = self.client.get("/agent/api/contacts")
        self.assertEqual(response.status_code, 200, response.json)
        registry = next(row for row in response.json["registries"] if row["id"] == self.zone_customer_id)
        self.assertEqual(registry["contact_links"][0]["contact"]["display_name"], "Mario Rossi")

    def test_agent_cannot_add_contact_to_unassigned_customer_or_without_number(self):
        response = self.client.post("/agent/api/contacts", json={
            "registry_ids": [self.zone_customer_id, self.other_customer_id],
            "display_name": "Contatto esterno",
            "points": [{"contact_type": "mobile", "value": "3331234567"}],
        })
        self.assertEqual(response.status_code, 404)
        response = self.client.post("/agent/api/contacts", json={
            "registry_ids": [self.zone_customer_id],
            "display_name": "Senza numero",
            "points": [],
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(RegistryContact.query.count(), 0)

    def test_agent_only_features_reject_users_without_agent_role(self):
        self.agent_user.active_roles = [SimpleNamespace(name="staff")]
        response = self.client.get("/agent/customers")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
