"""Off-drawer company cash expenses affect payable balances, never physical cash."""
import copy,inspect,unittest
from datetime import date,timedelta
from decimal import Decimal
from unittest.mock import patch
from extensions import db
import models
import routes.cassa as cash
import test_cash_intermediate_deposits as base


class OffCashExpenseTests(unittest.TestCase):
    def setUp(self):
        base.IntermediateDepositsTests.setUp(self)
        self.app.secret_key='cash-test-only'
        names=['CashClosure','CashReceiptClosure','CashOwnerTake','CashEcommerce','CashDrawerCount','CashDrawerCountLine','CashClosurePos','CashIssuedCheck','CashRowCheck']
        db.metadata.create_all(db.engine,tables=[getattr(models,name).__table__ for name in names])
        self.insert(models.CashReceiptClosure,cash_day_id=1,amount=250)
        self.insert(models.CashExpense,id=1,cash_day_id=1,supplier='Expense fixture')
        db.session.commit()
    tearDown=base.IntermediateDepositsTests.tearDown
    insert=base.IntermediateDepositsTests.insert
    calculate=base.IntermediateDepositsTests.calculate
    deposit=base.IntermediateDepositsTests.deposit

    def expense(self,amount='86.40',**extra):
        values=dict(expense_id=1,direction='out',method='cash',off_cash=True,flag='*',amount=Decimal(amount))
        values.update(extra);self.insert(models.CashExpensePayment,**values);db.session.commit()

    def test_oct15_regression_off_cash_star_reduces_payable_only(self):
        before=self.calculate(1000);self.expense();after=self.calculate(1000)
        for key in ['contanti_fisici','valore_atteso_cassetto','incasso_calcolato','delta_quadratura','spese_cash']:
            self.assertEqual(before[key],after[key],key)
        for key in ['versabile_giornata','versabile_residuo','saldo_versabile','saldo_attuale']:
            self.assertEqual(before[key]-after[key],Decimal('86.40'),key)
        self.assertEqual(after['versabile_giornata'],Decimal('913.60'))
        self.assertEqual(after['spese_fuori_cassa'],Decimal('86.40'))

    def test_inside_outside_flags_and_payment_methods_not_double_counted(self):
        self.expense('86.40');self.expense('13.60',flag='**');self.expense('20',off_cash=False)
        self.expense('50',flag='!');self.expense('70',method='bank');self.expense('10',direction='in')
        totals=self.calculate(980)
        self.assertEqual(totals['valore_atteso_cassetto'],980)
        self.assertEqual(totals['versabile_giornata'],880)
        self.assertEqual(totals['delta_quadratura'],0)

    def test_intermediate_deposit_and_cents_reduce_payable_once(self):
        self.expense();self.deposit(1,cash=Decimal('300.13'))
        totals=self.calculate(Decimal('699.87'))
        self.assertEqual(totals['valore_atteso_cassetto'],Decimal('699.87'))
        self.assertEqual(totals['versabile_residuo'],Decimal('613.47'))
        self.assertEqual(totals['saldo_versabile'],Decimal('1113.47'))
        self.assertEqual(totals['delta_quadratura'],0)

    def test_outside_expenses_can_exceed_payable_without_changing_drawer(self):
        self.expense('1200.25')
        totals=self.calculate(1000)
        self.assertEqual(totals['valore_atteso_cassetto'],1000)
        self.assertEqual(totals['versabile_giornata'],Decimal('-200.25'))
        self.assertEqual(totals['delta_quadratura'],0)

    def snapshot(self,version=20,marker=False,amount=9999):
        payload=dict(totals=dict(versabile_giornata=1000,versabile_residuo=1000))
        if marker: payload['totals']['off_cash_versabile_calculation_version']=1
        self.insert(models.CashClosure,cash_day_id=1,fiscal_snapshot_version=version,fiscal_snapshot_stale=False,
            saldo_versabile_finale=amount,fiscal_snapshot=dict(payload=payload,report_payload=dict(preview=payload)))
        db.session.execute(models.CashDay.__table__.update().values(status='closed'))
        db.session.commit()
        return payload

    def test_progressive_ignores_old_snapshot_even_with_high_revision(self):
        self.expense();self.snapshot()
        saldo,meta=cash._calculate_progressive_saldo_versabile_fast(self.day+timedelta(days=1))
        self.assertEqual(saldo,Decimal('913.60'));self.assertEqual(meta['source'],'aggregate_from_start')
        self.assertIsNone(cash._latest_fiscal_snapshot_before(self.day+timedelta(days=1)))

    def test_progressive_current_snapshot_plus_new_off_cash_expense(self):
        self.snapshot(version=3,marker=True,amount=Decimal('913.60'))
        tomorrow=self.day+timedelta(days=1)
        self.insert(models.CashDay,id=2,day_date=tomorrow)
        self.insert(models.CashExpense,id=2,cash_day_id=2)
        self.expense('10.25',expense_id=2)
        saldo,meta=cash._calculate_progressive_saldo_versabile_fast(tomorrow+timedelta(days=1))
        self.assertEqual(saldo,Decimal('903.35'));self.assertEqual(meta['source'],'snapshot_plus_aggregate')
        self.assertIsNotNone(cash._latest_fiscal_snapshot_before(tomorrow+timedelta(days=1)))

    def test_detail_contains_negative_outside_expense_and_matches_total(self):
        self.expense()
        with self.app.test_request_context():
            data=inspect.unwrap(cash.api_versabile_detail)(self.day.isoformat()).get_json()
        entry=next(e for e in data['entries'] if e['label']=='Spesa contanti fuori cassa')
        self.assertEqual(entry['amount'],-86.40)
        self.assertEqual(Decimal(str(data['total'])),self.calculate(1000)['versabile_giornata'])

    def test_closed_preview_does_not_return_legacy_cached_totals(self):
        self.expense();self.snapshot()
        with self.app.test_request_context('/?saldo_prev=500&fondo_finale=100'):
            data=inspect.unwrap(cash.api_cash_day_preview)(self.day.isoformat()).get_json()
        self.assertEqual(Decimal(str(data['totals']['versabile_giornata'])),Decimal('913.60'))
        self.assertEqual(Decimal(str(data['totals']['valore_atteso_cassetto'])),1000)
        self.assertTrue(cash._current_versabile_preview(data))

    def test_archived_report_rebuilds_old_preview_without_mutating_archive(self):
        self.expense();old=self.snapshot();archive=dict(preview=old,expenses={'historical':'unchanged'})
        before=copy.deepcopy(archive)
        with self.app.test_request_context('/?view=complete'):
            from flask import session
            session['pri_vault_unlocked']=True
            with patch('routes.cassa._load_private_vault_day_closure_snapshot',return_value=archive),patch('routes.cassa._build_cash_day_preview_payload',return_value=dict(totals=self.calculate(1000))):
                data=inspect.unwrap(cash.api_day_closure_snapshot)(self.day.isoformat()).get_json()
        self.assertEqual(archive,before)
        self.assertEqual(data['snapshot']['expenses'],archive['expenses'])
        self.assertEqual(Decimal(str(data['snapshot']['preview']['totals']['versabile_giornata'])),Decimal('913.60'))
