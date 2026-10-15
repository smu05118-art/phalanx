# -*- coding: utf-8 -*-
"""미공시/정정공시의 재조회와 원문 캐시 보존. 외부 요청 없이 검증한다."""
import copy
from datetime import date
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common
import ksemi_reports as R


class TestReportRefresh(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(R, '_today', return_value=date(2026, 10, 15))
        self.latest = patch.object(R, 'latest_quarter', return_value='2026Q3')
        self.clock.start()
        self.latest.start()
        self.addCleanup(self.clock.stop)
        self.addCleanup(self.latest.stop)

    def record(self, checked='2026-10-15'):
        return {'rcpNo': '20260814000001', 'title': '반기보고서 (2026.06)',
                'nodes': {'ii4': [{'text': '매출 및 수주상황'}]}, 'absent': [],
                'checked_on': checked}

    def test_legacy_negative_cache_rechecks_new_filing(self):
        ix = {'123456|2026Q3': {'none': True}}
        with patch.object(R, 'find_periodic', return_value=[('20261114000001', '분기보고서 (2026.09)')]) as search, \
             patch.object(R, 'toc', return_value=[{'text': '매출 및 수주상황'}]):
            got = R._resolve('123456', '2026Q3', ix)
        search.assert_called_once_with('123456', '2026Q3')
        self.assertEqual(got['rcpNo'], '20261114000001')
        self.assertFalse(ix['123456|2026Q3'].get('none'))

    def test_same_day_negative_cache_does_not_repeat_search(self):
        ix = {'123456|2026Q3': {'none': True, 'checked_on': '2026-10-15'}}
        with patch.object(R, 'find_periodic') as search:
            self.assertIsNone(R._resolve('123456', '2026Q3', ix))
        search.assert_not_called()

    def test_recent_negative_cache_expires_next_day(self):
        ix = {'123456|2026Q3': {'none': True, 'checked_on': '2026-10-14'}}
        with patch.object(R, 'find_periodic', return_value=[]) as search:
            self.assertIsNone(R._resolve('123456', '2026Q3', ix))
        search.assert_called_once()
        self.assertEqual(ix['123456|2026Q3']['checked_on'], '2026-10-15')

    def test_old_report_rechecks_weekly(self):
        self.assertTrue(R._index_fresh(self.record('2026-10-09'), '2025Q4', date(2026, 10, 15)))
        self.assertFalse(R._index_fresh(self.record('2026-10-08'), '2025Q4', date(2026, 10, 15)))
        self.assertFalse(R._index_fresh(self.record('2026-10-16'), '2025Q4', date(2026, 10, 15)))

    def test_same_receipt_revalidation_does_not_download_toc(self):
        ix = {'123456|2026Q2': self.record('2026-10-14')}
        with patch.object(R, 'find_periodic', return_value=[('20260814000001', '반기보고서 (2026.06)')]), \
             patch.object(R, 'toc') as toc:
            R._resolve('123456', '2026Q2', ix)
        toc.assert_not_called()
        self.assertEqual(ix['123456|2026Q2']['checked_on'], '2026-10-15')

    def test_correction_refreshes_receipt(self):
        ix = {'123456|2026Q2': self.record('2026-10-14')}
        with patch.object(R, 'find_periodic', return_value=[('20261015000001', '[정정]반기보고서 (2026.06)')]), \
             patch.object(R, 'toc', return_value=[{'text': '매출 및 수주상황'}]) as toc:
            got = R._resolve('123456', '2026Q2', ix)
        toc.assert_called_once_with('20261015000001')
        self.assertEqual(got['rcpNo'], '20261015000001')

    def test_attachment_only_correction_falls_back_to_existing_body(self):
        ix = {'123456|2026Q2': self.record('2026-10-14')}
        with patch.object(R, 'find_periodic', return_value=[
                ('20261015000001', '[첨부정정]반기보고서 (2026.06)'),
                ('20260814000001', '반기보고서 (2026.06)')]), \
             patch.object(R, 'toc', return_value=[]) as toc:
            got = R._resolve('123456', '2026Q2', ix)
        self.assertEqual(got['rcpNo'], '20260814000001')
        self.assertIn('ii4', got['nodes'])
        toc.assert_called_once_with('20261015000001')

    def test_attachment_only_correction_falls_back_to_next_new_body(self):
        ix = {'123456|2026Q2': self.record('2026-10-14')}
        with patch.object(R, 'find_periodic', return_value=[
                ('20261015000001', '[첨부정정]반기보고서 (2026.06)'),
                ('20261014000001', '[기재정정]반기보고서 (2026.06)')]), \
             patch.object(R, 'toc', side_effect=[[], [{'text': '매출 및 수주상황'}]]):
            got = R._resolve('123456', '2026Q2', ix)
        self.assertEqual(got['rcpNo'], '20261014000001')

    def test_all_candidates_missing_body_preserve_index_and_observations(self):
        ix = {'123456|2026Q2': self.record('2026-10-14')}
        before = copy.deepcopy(ix)
        prior = {'stock': '123456', 'quarters': {'2026Q2': {
            'rcpNo': '20260814000001', 'orders': {'backlog': 17}}}, 'kpi': {'backlog': 17}, 'errors': []}
        with patch.object(R, 'find_periodic', return_value=[('20261015000001', '[첨부정정]반기보고서 (2026.06)')]), \
             patch.object(R, 'toc', return_value=[]), patch.object(R, '_hdr_commit'):
            current = R.collect_one({'stock': '123456', 'name': 'fixture', 'market': 'KOSDAQ', 'industry': 'fixture'},
                                    ['2026Q2'], ix=ix)
        self.assertTrue(current['errors'])
        self.assertEqual(ix, before)
        held = R.preserve_failed_refresh(current, prior)
        self.assertEqual(held['quarters'], prior['quarters'])
        self.assertEqual(held['kpi']['backlog'], 17)
        self.assertEqual(held['refresh_status'], 'retained_after_error')

    def test_invalid_same_day_index_does_not_skip_body_validation(self):
        ix = {'123456|2026Q2': dict(self.record(), nodes={}, absent=['ii4', 'acc', 'seg'])}
        before = copy.deepcopy(ix)
        with patch.object(R, 'find_periodic', return_value=[('20260814000001', '반기보고서 (2026.06)')]), \
             patch.object(R, 'toc', return_value=[]), self.assertRaises(RuntimeError):
            R._resolve('123456', '2026Q2', ix)
        self.assertEqual(ix, before)

    def test_annual_refresh_does_not_remove_previously_found_note(self):
        cur = self.record('2026-10-01')
        cur['nodes']['acc'] = [{'text': '수익인식'}]
        cur['absent'] = ['seg']
        ix = {'123456|2025Q4': cur}
        before = copy.deepcopy(ix)
        with patch.object(R, 'find_periodic', return_value=[('20261015000001', '[정정]사업보고서 (2025.12)')]), \
             patch.object(R, 'toc', return_value=[{'text': '매출 및 수주상황'}]), self.assertRaises(RuntimeError):
            R._resolve('123456', '2025Q4', ix, keys=R.ANNUAL)
        self.assertEqual(ix, before)

    def test_reparse_never_fetches_even_with_stale_negative(self):
        ix = {'123456|2026Q3': {'none': True}}
        with patch.object(R, 'find_periodic') as search:
            self.assertIsNone(R._resolve('123456', '2026Q3', ix, reparse=True))
        search.assert_not_called()

    def test_empty_search_does_not_replace_known_receipt(self):
        ix = {'123456|2026Q2': self.record('2026-10-14')}
        before = copy.deepcopy(ix)
        with patch.object(R, 'find_periodic', return_value=[]), self.assertRaises(RuntimeError):
            R._resolve('123456', '2026Q2', ix)
        self.assertEqual(ix, before)

    def test_search_failure_preserves_index(self):
        ix = {'123456|2026Q2': self.record('2026-10-14')}
        before = copy.deepcopy(ix)
        with patch.object(R, 'find_periodic', side_effect=RuntimeError('network')), self.assertRaises(RuntimeError):
            R._resolve('123456', '2026Q2', ix)
        self.assertEqual(ix, before)


class TestCandidateQuarter(unittest.TestCase):
    def test_wrong_quarter_never_falls_back_even_across_report_kinds(self):
        import ksemi_lib as L
        with patch.object(L, 'search_reports', return_value=[('20261014000001', '[기재정정]반기보고서 (2026.06)')]) as search:
            self.assertEqual(L.find_periodic('123456', '2026Q3'), [])
        self.assertEqual(search.call_count, 3)

    def test_non_december_fiscal_year_keeps_calendar_period_matching(self):
        import ksemi_lib as L
        with patch.object(L, 'search_reports', side_effect=[[], [('20260814000001', '분기보고서 (2026.06)')]]):
            self.assertEqual(L.find_periodic('123456', '2026Q2'), [('20260814000001', '분기보고서 (2026.06)')])


class TestFailedRefresh(unittest.TestCase):
    def test_failed_lookup_does_not_erase_previously_observed_quarters(self):
        previous = {'stock': '123456', 'quarters': {'2026Q2': {'rcpNo': '20260814000001', 'value': 17}}, 'kpi': {'backlog': 17}, 'errors': []}
        current = {'stock': '123456', 'quarters': {}, 'errors': [{'quarter': '2026Q2', 'error': 'network'}]}
        held = R.preserve_failed_refresh(current, previous)
        self.assertEqual(held['quarters'], previous['quarters'])
        self.assertEqual(held['kpi'], previous['kpi'])
        self.assertEqual(held['errors'], current['errors'])
        self.assertEqual(held['refresh_status'], 'retained_after_error')
        self.assertEqual(previous['errors'], [])

    def test_successful_refresh_is_used_without_retaining_old_values(self):
        current = {'stock': '123456', 'quarters': {'2026Q2': {'value': 19}}, 'errors': []}
        self.assertIs(R.preserve_failed_refresh(current, {'quarters': {'2026Q2': {'value': 17}}}), current)
