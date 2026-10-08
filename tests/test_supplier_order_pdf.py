import unittest
from datetime import date
import pypdfium2 as pdfium
from tools.supplier_order_pdf import generate_supplier_order_pdf


class SupplierOrderPdfTests(unittest.TestCase):
    def test_landscape_pdf_with_subgroups_total_and_unselected_products(self):
        pdf=generate_supplier_order_pdf(order_id=17,title='Ordine Caffè',order_date=date(2026,10,8),
            rows=[dict(root='CF1',description='Capsule Caffè & Ginseng',subgroup_id=1),dict(root='CF2',description='Cialde non ordinate',subgroup_id=None)],
            subgroup_names={1:'Lavazza a Modo Mio'},quantities={'CF1':12})
        with pdfium.PdfDocument(pdf) as document:
            self.assertEqual(len(document),1);page=document[0];width,height=page.get_size();self.assertGreater(width,height)
            text=page.get_textpage().get_text_range()
            for value in ['Lavazza a Modo Mio','Cialde non ordinate','CF1','CF2','Totale confezioni ordinate','12','08/10/2026']:
                self.assertIn(value,text)

    def test_long_order_paginated_without_losing_last_product(self):
        rows=[dict(root=f'CODE{i:03}',description=('Caffè <speciale> & capsule ' * 6)+str(i),subgroup_id=i//35) for i in range(150)]
        pdf=generate_supplier_order_pdf(order_id=18,title='Ordine lungo '*12,order_date=date(2026,10,8),rows=rows,subgroup_names={i:f'Sistema {i}' for i in range(5)},quantities={'CODE000':5,'CODE149':7})
        with pdfium.PdfDocument(pdf) as document:
            self.assertGreater(len(document),1)
            text='\n'.join(page.get_textpage().get_text_range() for page in document)
            self.assertIn('CODE149',text);self.assertIn('<speciale>',text)
            self.assertEqual(sum(text.count(f'CODE{i:03}') for i in range(150)),150)
