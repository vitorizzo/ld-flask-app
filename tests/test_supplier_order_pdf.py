import unittest
from datetime import date
from types import SimpleNamespace
import pypdfium2 as pdfium
from tools.supplier_order_pdf import generate_supplier_order_pdf
from tools.supplier_order_workflow import regenerate_order_pdf


class SupplierOrderPdfTests(unittest.TestCase):
    def test_landscape_pdf_contains_only_products_with_order_quantities(self):
        pdf=generate_supplier_order_pdf(order_id=17,title='Ordine Caffè',order_date=date(2026,10,8),
            rows=[dict(root='CF1',supplier_code='V001',description='Capsule Caffè & Ginseng',subgroup_id=1),dict(root='CF2',supplier_code='V002',description='Cialde non ordinate',subgroup_id=None)],
            subgroup_names={1:'Lavazza a Modo Mio'},quantities={'CF1':12})
        with pdfium.PdfDocument(pdf) as document:
            self.assertEqual(len(document),1);page=document[0];width,height=page.get_size();self.assertGreater(width,height)
            text=page.get_textpage().get_text_range()
            for value in ['Lavazza a Modo Mio','V001','Totale confezioni ordinate','12','08/10/2026']:
                self.assertIn(value,text)
            for value in ['Cialde non ordinate','V002','CF1','CF2']:
                self.assertNotIn(value,text)

    def test_long_order_paginated_without_losing_last_product(self):
        rows=[dict(root=f'INTERNAL{i:03}',supplier_code=f'CODE{i:03}',description=('Caffè <speciale> & capsule ' * 6)+str(i),subgroup_id=i//35) for i in range(150)]
        quantities={f'INTERNAL{i:03}':i+1 for i in range(90)}
        pdf=generate_supplier_order_pdf(order_id=18,title='Ordine lungo '*12,order_date=date(2026,10,8),rows=rows,subgroup_names={i:f'Sistema {i}' for i in range(5)},quantities=quantities)
        with pdfium.PdfDocument(pdf) as document:
            self.assertGreater(len(document),1)
            text='\n'.join(page.get_textpage().get_text_range() for page in document)
            self.assertIn('CODE089',text);self.assertIn('<speciale>',text);self.assertNotIn('CODE090',text)
            self.assertEqual(sum(text.count(f'CODE{i:03}') for i in range(150)),90)

    def test_confirmed_supplier_order_uses_multiple_pages_and_only_ordered_lines(self):
        rows={f'MATRIX{i:03}':dict(root=f'MATRIX{i:03}',supplier_code=f'V{i:03}',description=f'Product {i} '+'long description '*5,subgroup_id=i//30) for i in range(120)}
        ordered=[SimpleNamespace(matrix_code=f'MATRIX{i:03}',quantity=2,description=rows[f'MATRIX{i:03}']['description'],supplier_code=f'V{i:03}',order_description=rows[f'MATRIX{i:03}']['description'],subgroup_name=None) for i in range(85)]
        card=SimpleNamespace(id=28,title='Long supplier order',order_lines=ordered,order_revision=1)
        regenerate_order_pdf(card,rows,{i:f'System {i}' for i in range(4)})
        self.assertTrue(card.order_pdf.startswith(b'%PDF'));self.assertFalse(card.is_draft)
        with pdfium.PdfDocument(card.order_pdf) as document:
            self.assertGreater(len(document),1)
            text='\n'.join(page.get_textpage().get_text_range() for page in document)
            self.assertIn('V084',text);self.assertNotIn('V085',text)
            self.assertEqual(sum(text.count(f'V{i:03}') for i in range(120)),85)

    def test_coffee_single_page_contains_all_supplier_codes(self):
        rows=[dict(root=f'INTERNAL{i:03}',supplier_code=f'V{i:03}',description='CAPSULE CAFFE MOLTO LUNGO '*6,
                   order_description=f'Borbone miscela {i} 100pz',subgroup_id=i//10) for i in range(39)]
        pdf=generate_supplier_order_pdf(order_id=19,title='Ordine caffè',order_date=date(2026,10,8),
            rows=rows,subgroup_names={i:f'Sistema {i}' for i in range(4)},quantities={f'INTERNAL{i:03}':17 for i in range(39)},single_page=True)
        with pdfium.PdfDocument(pdf) as document:
            self.assertEqual(len(document),1)
            text=document[0].get_textpage().get_text_range()
            for i in range(39):self.assertIn(f'V{i:03}',text)
            self.assertNotIn('INTERNAL',text)
