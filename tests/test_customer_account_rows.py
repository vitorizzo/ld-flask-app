import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from tools.customer_account_rows import (
    customer_statement_row_is_balance_relevant,
    format_customer_document_number,
    open_account_entries,
)


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

    def test_sdo_generated_credit_is_excluded_but_receipt_remains(self):
        invoice = row(1, '378.78')
        receipt = row(2, '-321.22', accounting_reason='096', accounting_reference='00008')
        generated_sdo = row(3, '-57.56', accounting_reason='096', accounting_reference='00001',
                            description='S/DO1197+1482+1', is_balance_relevant=False)
        technical_counterpart = row(4, '57.56', accounting_reason='096', accounting_reference='00000',
                                    description='S/DO1197+1482+1', is_balance_relevant=False)
        self.assertFalse(customer_statement_row_is_balance_relevant('096', '00001', 'S/DO1197+1482+1'))
        self.assertFalse(customer_statement_row_is_balance_relevant('096', '00000', 'RISC. FATTURA'))
        self.assertTrue(customer_statement_row_is_balance_relevant('096', '00008', 'RISC. FATTURA'))
        self.assertTrue(customer_statement_row_is_balance_relevant('001', '00001', 'S/DO-like invoice'))
        self.assertEqual([entry.id for entry in open_account_entries(
            [invoice, receipt, generated_sdo, technical_counterpart]
        )], [1, 2])
        self.assertEqual(sum(entry.signed_amount for entry in open_account_entries(
            [invoice, receipt, generated_sdo, technical_counterpart]
        )), Decimal('57.56'))

    def test_fixed_width_document_numbers_render_as_number_and_series(self):
        self.assertEqual(format_customer_document_number('00238200'), '2382/00')
        self.assertEqual(format_customer_document_number('00148200', '0000'), '1482/00')
        self.assertEqual(format_customer_document_number('00238200', {'document_number_suffix': '0000'}), '2382/00')
        self.assertEqual(format_customer_document_number('0000890'), '890')
        self.assertEqual(format_customer_document_number('00000000'), '')
        self.assertEqual(format_customer_document_number('00238200', '0003'), '2382/00 (bis 3)')
