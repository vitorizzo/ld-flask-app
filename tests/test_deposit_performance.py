import inspect
from datetime import timedelta
from decimal import Decimal
from sqlalchemy import event
import test_cash_intermediate_deposits as intermediate
from extensions import db
import models
from routes.cassa import api_available_checks_for_deposit, api_list_deposits, VERSABILE_SNAPSHOT_VERSION


class DepositPerformanceTests(intermediate.IntermediateDepositsTests):
    def setUp(self):
        super().setUp()
        names = ['CashClosure', 'CashReceiptClosure', 'CashCustomer', 'CashBank']
        db.metadata.create_all(db.engine, tables=[getattr(models, name).__table__ for name in names])

    def available(self, day):
        with self.app.test_request_context():
            return inspect.unwrap(api_available_checks_for_deposit)(day.isoformat()).get_json()

    def test_history_query_count_does_not_grow(self):
        statements = []
        def record(conn, cursor, sql, params, context, many):
            statements.append(sql)
        event.listen(db.engine, 'before_cursor_execute', record)
        try:
            first = self.available(self.day + timedelta(days=1))
            baseline = len(statements)
            self.assertEqual(first['saldo_versabile_precedente'], 750)
            self.assertEqual(first['contanti_massimi_incasso'], 600)
            self.assertEqual(first['incasso'][0]['id'], 1)
            for i in range(1, 181):
                self.insert(models.CashDay, id=i+1, day_date=self.day+timedelta(days=i))
            db.session.commit(); db.session.remove(); statements.clear()
            result = self.available(self.day + timedelta(days=181))
            self.assertEqual(result['saldo_versabile_precedente'], first['saldo_versabile_precedente'])
            self.assertEqual(len(statements), baseline)
            self.assertFalse(any('FROM cash_days' in sql and 'WITH base' not in sql for sql in statements))
        finally:
            event.remove(db.engine, 'before_cursor_execute', record)

    def test_previous_day_boundary_and_intermediate_deposit(self):
        self.deposit(1, cash=Decimal('300.13'))
        self.assertEqual(self.available(self.day)['saldo_versabile_precedente'], 0)
        self.assertEqual(self.available(self.day+timedelta(days=1))['saldo_versabile_precedente'], 449.87)

    def test_valid_snapshot_used_but_stale_snapshot_ignored(self):
        db.session.execute(models.CashDay.__table__.update().values(status='closed'))
        self.insert(models.CashClosure, id=1, cash_day_id=1,
                    saldo_versabile_finale=900, fiscal_snapshot_stale=False,
                    fiscal_snapshot_version=VERSABILE_SNAPSHOT_VERSION)
        db.session.commit()
        target = self.day + timedelta(days=1)
        self.assertEqual(self.available(target)['saldo_versabile_precedente'], 900)
        db.session.execute(models.CashClosure.__table__.update().values(fiscal_snapshot_stale=True))
        db.session.commit()
        self.assertEqual(self.available(target)['saldo_versabile_precedente'], 750)

    def test_deposits_do_not_load_unrelated_movements(self):
        statements = []
        def record(conn, cursor, sql, params, context, many):
            statements.append(sql)
        db.session.remove()
        event.listen(db.engine, 'before_cursor_execute', record)
        try:
            with self.app.test_request_context():
                result = inspect.unwrap(api_list_deposits)(self.day.isoformat()).get_json()
            self.assertTrue(result['ok'])
            self.assertEqual(result['deposits'], [])
            for table in ['cash_sales', 'cash_expenses', 'cash_moves', 'pos_moves']:
                self.assertFalse(any('FROM '+table in sql for sql in statements), table)
        finally:
            event.remove(db.engine, 'before_cursor_execute', record)
