"""발표 탐지·정정 수집의 공통 캐시 계약. 외부 요청 없이 검증한다."""
import datetime
import importlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import report_refresh as R


class TestPolicy(unittest.TestCase):
    def test_latest_candidate_does_not_wait_for_deadline(self):
        for day, quarter in [('2026-10-01', '2026Q3'), ('2027-01-01', '2026Q4'),
                             ('2026-03-31', '2025Q4'), ('2026-04-01', '2026Q1')]:
            self.assertEqual(R.latest_candidate(datetime.date.fromisoformat(day)), quarter)

    def test_daily_recent_weekly_history_and_unknown_dates(self):
        today = datetime.date(2026, 10, 15)
        for q in ['2026Q3', '2026Q2']:
            self.assertFalse(R.due({'_refresh_checked_on': '2026-10-15'}, q, today))
            self.assertTrue(R.due({'_refresh_checked_on': '2026-10-14'}, q, today))
        self.assertFalse(R.due({'_refresh_checked_on': '2026-10-09'}, '2026Q1', today))
        self.assertTrue(R.due({'_refresh_checked_on': '2026-10-08'}, '2026Q1', today))
        for value in [None, '', 'wrong', '2026-10-16']:
            self.assertTrue(R.due({'_refresh_checked_on': value}, '2026Q1', today))

    def test_correction_search_window_reaches_today(self):
        with patch.object(R, 'today', return_value=datetime.date(2026, 10, 15)):
            self.assertEqual(R.window('2025Q4'), ('20251201', '20261015'))

    def test_wrong_quarter_never_becomes_a_new_observation(self):
        old = [('20261014000001', '[기재정정]반기보고서 (2026.06)')]
        self.assertEqual(R.candidates(old, '2026Q3'), [])
        self.assertEqual(R.candidates(old + [('20261113000001', '분기보고서 (2026.09)')], '2026Q3'),
                         [('20261113000001', '분기보고서 (2026.09)')])

    def test_corrections_are_considered_newest_first(self):
        reps = [('20260814000001', '반기보고서 (2026.06)'),
                ('20261014000001', '[첨부정정]반기보고서 (2026.06)'),
                ('20261015000001', '[기재정정]반기보고서 (2026.06)')]
        self.assertEqual([x[0] for x in R.candidates(reps, '2026Q2')],
                         ['20261015000001', '20261014000001', '20260814000001'])

    def test_replacement_archives_exact_original_bytes_and_preserves_good_on_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / '2026Q2.json'
            original = b'{"ok":true,"rcp":"20260814000001","value":7}\n'
            p.write_bytes(original)
            self.assertFalse(R.save(str(p), {'ok': False, 'rcp': '20261015000001'}))
            self.assertEqual(p.read_bytes(), original)
            self.assertTrue(R.save(str(p), {'ok': True, 'rcp': '20261015000001', 'value': 9}))
            self.assertEqual(json.loads(p.read_text())['value'], 9)
            self.assertEqual(next((Path(folder) / '_revisions').iterdir()).read_bytes(), original)


class TestHubCollectors(unittest.TestCase):
    """주요 보고서 수집기에서 정책 호출을 빼먹으면 실패하는 통합 계약."""
    def modules(self):
        for hub, name in [('kdef', 'kdef_reports'), ('kgrid', 'kgrid_reports'),
                          ('knuke', 'knuke_reports'), ('kship', 'kship_yards')]:
            sys.path.insert(0, str(TOOLS.parents[1] / hub / 'tools'))
            yield importlib.import_module(name)

    def call(self, module, quarter='2026Q2'):
        args = {} if module.__name__ == 'kship_yards' else {'log': io.StringIO()}
        return module.collect_one({'stock': '123456', 'name': 'fixture'}, quarter, **args)

    def test_same_receipt_revalidation_preserves_values_without_section_fetch(self):
        for module in self.modules():
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as folder:
                p = Path(folder) / '123456/2026Q2.json'; p.parent.mkdir()
                p.write_text(json.dumps({'ok': True, 'rcp': '20260814000001', 'value': 17}))
                with patch.object(module, 'CACHE', folder), \
                     patch.object(module, 'search_reports', return_value=[('20260814000001', '반기보고서 (2026.06)')]), \
                     patch.object(module, 'toc') as toc:
                    self.assertEqual(self.call(module)['value'], 17)
                toc.assert_not_called()
                self.assertIn('_refresh_checked_on', json.loads(p.read_text()))

    def test_missing_candidate_does_not_use_previous_quarter(self):
        for module in self.modules():
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as folder:
                with patch.object(module, 'CACHE', folder), \
                     patch.object(module, 'search_reports', return_value=[('20261014000001', '[기재정정]반기보고서 (2026.06)')]), \
                     patch.object(module, 'toc') as toc:
                    self.assertFalse(self.call(module, '2026Q3')['ok'])
                toc.assert_not_called()
                self.assertFalse((Path(folder) / '123456/2026Q3.json').exists())

    def test_attachment_without_section_falls_back_to_known_receipt(self):
        for module in self.modules():
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as folder:
                p = Path(folder) / '123456/2026Q2.json'; p.parent.mkdir()
                p.write_text(json.dumps({'ok': True, 'rcp': '20260814000001', 'value': 17}))
                with patch.object(module, 'CACHE', folder), \
                     patch.object(module, 'search_reports', return_value=[('20261014000001', '[첨부정정]반기보고서 (2026.06)'), ('20260814000001', '반기보고서 (2026.06)')]), \
                     patch.object(module, 'toc', return_value=[]) as toc, \
                     patch.object(module, 'find_sections', return_value={}):
                    self.assertEqual(self.call(module)['value'], 17)
                toc.assert_called_once_with('20261014000001')
