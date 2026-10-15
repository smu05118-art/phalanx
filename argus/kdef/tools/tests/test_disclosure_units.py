"""실제 공시의 잔고 미공개·혼합통화 해석. 네트워크 없이 원문 캐시를 대조한다."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import kdef_reports as R
import kdef_page as P


def source(stock, quarter='2026Q2'):
    return json.loads((Path(R.CACHE) / stock / (quarter + '.json')).read_text())


class TestDisclosureUnits(unittest.TestCase):
    def test_both_explicit_currency_symbols_split_without_conversion(self):
        data, _ = R.reparse_dict(source('368770'))
        rows = {o['cur']: o['rows'][0] for o in data['orders_all']}
        self.assertEqual((rows['KRW']['gross'], rows['KRW']['delivered'], rows['KRW']['closing']), (60265, 24930, 35335))
        self.assertEqual((rows['USD']['gross'], rows['USD']['delivered'], rows['USD']['closing']), (19.589, 15.377, 4.212))
        self.assertEqual(data['unknown_headers'], [])
        self.assertTrue(all(o['currency_split'] for o in data['orders_all']))

    def test_previously_valid_unprefixed_history_stays_unchanged(self):
        for q, closing in [('2026Q1', 33629), ('2025Q4', 36249), ('2025Q2', 42788), ('2023Q4', 15941)]:
            data, _ = R.reparse_dict(source('368770', q))
            self.assertEqual(R._orders_total(data['orders']), closing)
            self.assertFalse(data['orders'].get('currency_split'))
        # 원문 55,707−12,920는 42,787이나 명시 잔고 42,788은 고쳐 쓰지 않는다.
        data, _ = R.reparse_dict(source('368770', '2025Q2'))
        row = data['orders']['rows'][0]
        self.assertNotEqual(row['gross'] - row['delivered'], row['closing'])

    def test_inconsistent_symbols_or_missing_prefix_fail_closed(self):
        raw = next(t for t in source('368770')['raw_tables'] if '수주년' in t['cols'])
        for bad in ('$24,930', '24,930', 'unreadable'):
            table = copy.deepcopy(raw)
            table['rows'][0][4] = bad
            result = R.parse_sales([table])
            self.assertEqual(result['orders_all'], [], bad)
            self.assertIsNone(result['orders'], bad)
            self.assertEqual(result['unknown_headers'][0]['reason'], 'no_rows')

    def test_missing_unit_caption_does_not_create_currency_observation(self):
        table = copy.deepcopy(next(t for t in source('368770')['raw_tables'] if '수주년' in t['cols']))
        table['lead'] = '수주 현황'
        self.assertEqual(R.parse_sales([table])['orders_all'], [])

    def test_contract_only_disclosure_is_known_absence_never_backlog(self):
        data, _ = R.reparse_dict(source('488900'))
        self.assertTrue(data['ok'])
        self.assertIsNone(data['orders'])
        self.assertEqual(data['unknown_headers'], [])
        self.assertIn('수주잔고 미공시', data['note'])
        self.assertEqual(data['orders_not_applicable'][0]['n_rows'], 3)

    def test_no_absence_classification_without_original_disclosure_evidence(self):
        table = copy.deepcopy(next(t for t in source('488900')['raw_tables'] if '계약명' in t['cols']))
        table['lead'] = '수주 현황'
        self.assertFalse(R._award_not_applicable(table))
        result = R.parse_sales([table])
        self.assertEqual(result['orders_not_applicable'], [])
        self.assertEqual(result['unknown_headers'][0]['reason'], 'award')
        table['cols'].append('수주잔고')
        table['lead'] = '기재하지 않습니다. 공시된 계약현황'
        self.assertFalse(R._award_not_applicable(table))

    def test_build_and_page_keep_currency_values_separate_and_do_not_carry_prior_backlog(self):
        originals = {st: source(st) for st in ('368770', '488900')}
        with tempfile.TemporaryDirectory() as folder, patch.object(R, 'CACHE', folder), patch.object(R, 'write_asset'):
            for st, raw in originals.items():
                path = Path(folder) / st / '2026Q2.json'
                path.parent.mkdir()
                parsed, _ = R.reparse_dict(raw)
                path.write_text(json.dumps(parsed, ensure_ascii=False))
            built = R.build([{'stock': st, 'name': st, 'role': 'part'} for st in originals], ['2026Q2'])
        mixed = built['368770']['quarters']['2026Q2']
        self.assertIsNone(mixed['backlog'])
        self.assertIsNone(mixed['gross'])
        self.assertEqual(mixed['cur'], 'MIXED')
        by = {row['cur']: row for row in mixed['currency_breakdown']}
        self.assertEqual((by['KRW']['unit'], by['KRW']['closing']), ('백만원', 35335))
        self.assertEqual((by['USD']['unit'], by['USD']['closing']), ('천$', 4212))
        absent = built['488900']['quarters']['2026Q2']
        self.assertTrue(absent['ok'])
        self.assertIsNone(absent['backlog'])
        self.assertIn('적용불가', absent['unit_note'])
        data = P.load_all()
        data['reports'].update(built)
        summary = P.summary('368770', data)
        self.assertIsNone(summary['backlog'])
        self.assertIsNone(summary['coverage'])
        html = P.company_html(summary, data)
        for literal in ('통화별 수주 현황', '35,335', '4,212', '백만원', '천$'):
            self.assertIn(literal, html)
        summary = P.summary('488900', data)
        self.assertEqual(summary['latest_q'], '2026Q2')
        self.assertIsNone(summary['backlog'])
