import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from tools.customer_account_rows import open_account_entries


def row(id, amount, **changes):
    values=dict(id=id,amount=abs(Decimal(amount)),signed_amount=Decimal(amount),import_id=1,
        source_customer_code='1066',document_number='890',document_date=date(2016,5,14),
        source_payload={},is_balance_relevant=True,accounting_reason='001')
    values.update(changes)
    return SimpleNamespace(**values)


class OpenAccountEntriesTests(unittest.TestCase):
    def test_kiwi_invoice_technical_and_receipt_disappear_as_closed(self):
        entries=[row(1,'341.38'),row(2,'341.38',is_balance_relevant=False,accounting_reason='096',source_payload={'installment_number':'01'}),
                 row(3,'-341.38',accounting_reason='096',source_payload={'installment_number':'01'}),
                 row(4,'267.33',document_number='2610',document_date=date(2026,10,5))]
        self.assertEqual([r.id for r in open_account_entries(entries)],[4])
        self.assertEqual(sum(r.signed_amount for r in entries if r.is_balance_relevant),sum(r.signed_amount for r in open_account_entries(entries)))
        self.assertTrue(entries[0].is_balance_relevant)

    def test_partial_settlement_and_unallocated_credit_preserve_net(self):
        entries=[row(1,'100'),row(2,'-40'),row(3,'-30',document_number='CREDIT'),row(4,'100',is_balance_relevant=False)]
        self.assertEqual([r.id for r in open_account_entries(entries)],[1,2,3])
        self.assertEqual(sum(r.signed_amount for r in open_account_entries(entries)),Decimal('30'))

    def test_document_year_suffix_customer_and_snapshot_never_cross_match(self):
        for delta in [dict(document_date=date(2017,5,14)),dict(source_payload={'document_number_suffix':'B'}),
                      dict(source_customer_code='OTHER'),dict(import_id=2),dict(document_number='OTHER')]:
            entries=[row(1,'100'),row(2,'-100',**delta)]
            self.assertEqual(len(open_account_entries(entries)),2,delta)

    def test_missing_identity_and_real_credit_stay_visible(self):
        for delta in [dict(document_date=None),dict(document_number=''),dict(document_number='00000000')]:
            entries=[row(1,'100',**delta),row(2,'-100',**delta)]
            self.assertEqual(len(open_account_entries(entries)),2)
        self.assertEqual(len(open_account_entries([row(1,'-100')])),1)
