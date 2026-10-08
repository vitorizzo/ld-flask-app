from datetime import date, timedelta
from decimal import Decimal
import copy
import unittest
from flask import Flask
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from extensions import db
import models
from tools.cash_math import calculate_closure_pure, apply_intermediate_drawer_totals, current_drawer_preview_payload
from routes.cassa import _calculate_closure_fast_from_db


@compiles(JSONB, 'sqlite')
def compile_jsonb_sqlite(type_, compiler, **kwargs):
    return 'JSON'


class IntermediateDepositsTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.app.config.update(TESTING=True,SQLALCHEMY_DATABASE_URI='sqlite://')
        db.init_app(self.app);self.ctx=self.app.app_context();self.ctx.push()
        names=['CashDay','CashSale','CashSalePayment','CashExpense','CashExpensePayment','CashMove','PosMove','CashCheck','CashSaleCheck','CashDeposit','CashDepositCheck']
        db.metadata.create_all(db.engine,tables=[getattr(models,name).__table__ for name in names])
        self.day=date(2026,10,8)
        self.insert(models.CashDay,id=1,day_date=self.day,opening_float=100)
        self.insert(models.CashSale,id=1,cash_day_id=1,customer_label='Test')
        self.insert(models.CashSalePayment,sale_id=1,method='cash',amount=600,flag='*')
        self.insert(models.CashSalePayment,sale_id=1,method='check',amount=150,flag='*')
        self.insert(models.CashCheck,id=1,customer_id=1,check_number='test1',amount=150,received_date=self.day,due_date=self.day,status='received')
        self.insert(models.CashSaleCheck,sale_id=1,check_id=1,check_amount=150)
        db.session.commit()

    def tearDown(self):
        db.session.remove();self.ctx.pop()

    def insert(self, model, **values):
        # Core fixtures do not invoke the application's live audit listeners.
        db.session.execute(model.__table__.insert().values(**values))

    def deposit(self, id_,cash=0,check=False,type_='versamento_intermedio'):
        self.insert(models.CashDeposit,id=id_,cash_day_id=1,deposit_date=self.day,deposit_type=type_,cash_amount=cash)
        if check:
            self.insert(models.CashDepositCheck,deposit_id=id_,check_id=1,check_amount=150)
            db.session.execute(models.CashCheck.__table__.update().where(models.CashCheck.id==1).values(status='deposited'))
        db.session.commit()

    def calculate(self, delivered, final_float=100):
        args=dict(cash_day_id=1,opening_float=Decimal('100'),total_corrispettivi=Decimal('250'),fondo_finale=Decimal(str(final_float)),saldo_versabile_precedente=Decimal('500'),incasso_consegnato=Decimal(str(delivered)))
        slow=calculate_closure_pure(**args,saldo_movimenti_cassa=Decimal('0'));fast=_calculate_closure_fast_from_db(**args,check_cutoff=self.day)
        for key in ['contanti_fisici','incasso_calcolato','valore_atteso_cassetto','delta_quadratura','versabile_giornata','versabile_residuo','saldo_versabile','totale_versato_intermedio','incasso_consegnato_complessivo']:
            self.assertEqual(slow[key],fast[key],key)
        return fast

    def test_without_intermediate_deposit_is_unchanged(self):
        totals=self.calculate(1000)
        self.assertEqual(totals['valore_atteso_cassetto'],1000);self.assertEqual(totals['versabile_residuo'],1000);self.assertEqual(totals['delta_quadratura'],0)

    def test_cash_intermediate_leaves_only_residual_in_drawer(self):
        self.deposit(1,cash=300)
        totals=self.calculate(700)
        self.assertEqual(totals['contanti_fisici'],700);self.assertEqual(totals['valore_atteso_cassetto'],700)
        self.assertEqual(totals['versabile_giornata'],1000);self.assertEqual(totals['versabile_residuo'],700)
        self.assertEqual(totals['incasso_consegnato_complessivo'],1000);self.assertEqual(totals['saldo_versabile'],1200);self.assertEqual(totals['delta_quadratura'],0)

    def test_check_intermediate_is_removed_once(self):
        self.deposit(1,check=True)
        totals=self.calculate(850)
        self.assertEqual(totals['valore_atteso_cassetto'],850);self.assertEqual(totals['versabile_residuo'],850)
        self.assertEqual(totals['assegni_odierni'],150);self.assertEqual(totals['delta_quadratura'],0)

    def test_multiple_mixed_deposits_and_final_float(self):
        self.deposit(1,cash=300,check=True);self.deposit(2,cash=50)
        totals=self.calculate(500)
        self.assertEqual(totals['contanti_fisici'],500);self.assertEqual(totals['versabile_residuo'],500);self.assertEqual(totals['delta_quadratura'],0)
        totals=self.calculate(600,final_float=0)
        self.assertEqual(totals['valore_atteso_cassetto'],600);self.assertEqual(totals['delta_quadratura'],0)

    def test_previous_income_deposit_does_not_remove_todays_drawer_money(self):
        self.deposit(1,cash=200,type_='versamento_incasso')
        totals=self.calculate(1000)
        self.assertEqual(totals['valore_atteso_cassetto'],1000);self.assertEqual(totals['versabile_residuo'],1000);self.assertEqual(totals['saldo_versabile'],1300)

    def test_intermediate_and_previous_deposits_do_not_double_reduce_saldo(self):
        self.deposit(1,cash=300,check=True);self.deposit(2,cash=200,type_='versamento_incasso')
        totals=self.calculate(550)
        self.assertEqual(totals['valore_atteso_cassetto'],550);self.assertEqual(totals['versabile_residuo'],550);self.assertEqual(totals['saldo_versabile'],850)

    def test_snapshot_compatibility_is_immutable_and_idempotent(self):
        old=dict(totals=dict(totale_versato_intermedio=400,contanti_fisici=1000,valore_atteso_cassetto=1100,valore_atteso_cassetto_fiscal=1000,incasso_calcolato=1100,incasso_calcolato_fiscal=1000,incasso_consegnato=600,delta_quadratura=-500,delta_quadratura_fiscal=-400,versabile_giornata=1000,versabile_residuo=600,saldo_versabile=1600,quadratura_available=True,quadratura_led='red_low'))
        before=copy.deepcopy(old);new=current_drawer_preview_payload(old)
        self.assertEqual(old,before);self.assertEqual(new['totals']['valore_atteso_cassetto'],700);self.assertEqual(new['totals']['delta_quadratura'],-100)
        self.assertEqual(new['totals']['valore_atteso_cassetto_fiscal'],600);self.assertEqual(new['totals']['delta_quadratura_fiscal'],0)
        self.assertEqual(current_drawer_preview_payload(new),new)
        self.assertEqual(new['totals']['saldo_versabile'],1600);self.assertEqual(new['totals']['versabile_residuo'],600)

    def test_cents_are_preserved(self):
        db.session.execute(models.CashSalePayment.__table__.update().where(models.CashSalePayment.method=='cash').values(amount=Decimal('600.19')))
        db.session.execute(models.CashSalePayment.__table__.update().where(models.CashSalePayment.method=='check').values(amount=Decimal('150.37')))
        db.session.execute(models.CashCheck.__table__.update().values(amount=Decimal('150.37')))
        self.deposit(1,cash=Decimal('300.13'),check=True)
        totals=self.calculate(Decimal('550.06'))
        self.assertEqual(totals['valore_atteso_cassetto'],Decimal('550.06'));self.assertEqual(totals['versabile_residuo'],Decimal('550.06'));self.assertEqual(totals['delta_quadratura'],0)

    def test_postdated_check_remains_physical_but_not_payable_today(self):
        db.session.execute(models.CashCheck.__table__.update().values(due_date=self.day+timedelta(days=10)))
        self.deposit(1,cash=300)
        totals=self.calculate(700)
        self.assertEqual(totals['valore_atteso_cassetto'],700);self.assertEqual(totals['versabile_giornata'],850);self.assertEqual(totals['versabile_residuo'],550)


if __name__=='__main__':
    unittest.main()
