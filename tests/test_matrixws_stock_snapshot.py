import unittest
from tools.matrixws_stock_snapshot import collect_matrixws_stock


class MatrixStockSnapshotTests(unittest.TestCase):
    def test_verified_erp_examples_keep_final_snapshot(self):
        rows = [dict(**{'M-CODMAGPR': code, 'M-DEP': '0', 'M-GIACATT': value})
                for code, value in [('CF10006','8,000'),('CF10038','8,000'),('CF15001','3,000'),
                                    ('CF10006','9,000'),('CF10038','17,000'),('CF15001','1,000')]]
        stock, stats = collect_matrixws_stock(rows)
        self.assertEqual({row['cod_art']:row['giac_neg'] for row in stock},
                         {'CF10006':9,'CF10038':17,'CF15001':1})
        self.assertEqual(stats['duplicate_rows'], 3)

    def test_depots_zero_negative_invalid_and_repeated_values(self):
        rows = [dict(**{'M-CODMAGPR':code,'M-DEP':depot,'M-GIACATT':value}) for code,depot,value in
                [('A','0','7'),('A','400','2'),('A','0','7'),('B','0','3'),('B','0','0'),
                 ('C','0','-1'),('A','400','1.5'),('A','999','100'),('','0','8')]]
        stock, stats = collect_matrixws_stock(rows)
        self.assertEqual(stock,[dict(cod_art='A',giac_neg=7,giac_www=2),dict(cod_art='C',giac_neg=-1,giac_www=0)])
        self.assertEqual(stats['invalid_rows'],2)
        self.assertEqual(stats['unsupported_depot_rows'],1)
