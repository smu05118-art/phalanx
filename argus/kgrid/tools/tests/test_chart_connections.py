import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kgrid_page as P
import kgrid_reports as R

class Connections(unittest.TestCase):
    def test_decimal_terminal_amount(self):
        # 서전기전 반기보고서 20260814001021: 단위 백만원 / 59,066.
        self.assertEqual(R._scaled('59,066.', 1), 59066)
        self.assertIsNone(R._scaled('59,066. 원', 1))
        self.assertIsNone(R._scaled('2,,3.', 1))

    def test_order_table_is_not_customer_table(self):
        t = {'lead': '주요 매출처', 'cols': ['품목', '수주총액', '기납품액', '수주잔고'],
             'rows': [['전력선 및 통신선 등', '6354651', '2291716', '4062935']]}
        self.assertIsNone(R.parse_customers(t))

    def test_explicit_disclosure_is_not_a_numeric_zero(self):
        prefix = '<h1>4. 매출 및 수주상황</h1><p>매출 실적</p><h2>마. 수주상황</h2>'
        self.assertEqual(R.backlog_disclosure(prefix + '잔여 수주잔고 내역이 없습니다.')['status'], '잔여 잔고 없음 명시')
        self.assertEqual(R.backlog_disclosure(prefix + '수주상황은 기재하지 않습니다.')['status'], '수주상황 미기재')
        self.assertIsNone(R.backlog_disclosure(prefix + '고객에게 납품합니다.'))

    def test_vendor_canvas_initializer_order(self):
        data = P.load_all()
        for stock in ['001440', '103590', '189860', '007610']:
            html = P.company(data, stock)
            head = html.split('</head>')[0]
            self.assertNotIn('document.body.appendChild', head)
            self.assertNotIn('new Chart(', head)
            self.assertLess(html.index('chart.umd.min.js'), html.index('var SER='))
            self.assertNotIn('롤포워드(기초+신규', html)
        usd = P.company(data, '103590')
        self.assertIn("cur==='KRW'?100:1", usd)

if __name__ == '__main__':
    unittest.main()
