import unittest
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace as NS
from pypdf import PdfReader
from tools.customer_credit_pdf import communication_pdf


class CreditPdfTests(unittest.TestCase):
    def test_multipage_table_repeats_headers_and_keeps_all_open_documents(self):
        rows = [NS(id=i, import_id=1, source_customer_code='1066', document_date=date(2026,10,1),
                   document_number=f'DOC-{i}', description='Descrizione lunga ' * 8, signed_amount=Decimal('10.25'),
                   is_balance_relevant=True, source_payload={}) for i in range(85)]
        _, pdf = communication_pdf('statement', NS(customer_name='Società prova & figli',source_customer_code='1066'), rows, Decimal('871.25'))
        reader = PdfReader(BytesIO(pdf)); text = '\n'.join(page.extract_text() for page in reader.pages)
        self.assertGreater(len(reader.pages), 1)
        self.assertIn('871,25', text)
        for i in range(85): self.assertIn(f'DOC-{i}', text)
        for page in reader.pages:
            self.assertIn('Pagina', page.extract_text())
            if 'DOC-' in page.extract_text(): self.assertIn('Documento', page.extract_text())

    def test_empty_ledger_and_literal_markup_are_printed_safely(self):
        _, pdf = communication_pdf('statement', NS(customer_name='Cliente <prova>',source_customer_code='1066'), [], 0,
            dict(subject='Situazione {{cliente}}', body='Testo <script>letterale</script>\n{{partite}}\n{{saldo}}'))
        text = PdfReader(BytesIO(pdf)).pages[0].extract_text()
        self.assertIn('Nessuna partita aperta.', text)
        self.assertIn('<script>letterale</script>', text)
        self.assertIn('0,00', text)
