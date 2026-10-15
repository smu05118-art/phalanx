# -*- coding: utf-8 -*-
"""제품 절은 회사당 영구 캐시가 아니라 접수번호별 갱신이다."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kdef_products as P


class TestProductRefresh(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        cache = patch.object(P, 'CACHE', self.tmp.name)
        cache.start()
        self.addCleanup(cache.stop)
        self.rec = {'stock': '123456', 'name': 'fixture'}
        self.path = Path(self.tmp.name) / '123456.json'
        self.previous = {'stock': '123456', 'name': 'fixture', 'rcp': '20260515000001',
                         'ok': True, 'note': '', 'text': 'old product'}
        self.path.write_text(json.dumps(self.previous))
        self.log = io.StringIO()

    def call(self, **kwargs):
        return P.collect_one(self.rec, '2026Q2', log=self.log, **kwargs)

    def test_same_receipt_reuses_product_cache_without_network(self):
        with patch.object(P, '_cached_rcp', return_value=self.previous['rcp']), patch.object(P, 'toc') as toc:
            self.assertIsNone(self.call())
        toc.assert_not_called()
        self.assertEqual(json.loads(self.path.read_text()), self.previous)

    def test_new_receipt_refreshes_product_text(self):
        with patch.object(P, '_cached_rcp', return_value='20260814000001'), \
             patch.object(P, 'toc', return_value=[]), \
             patch.object(P, 'find_sections', return_value={'products': {}}), \
             patch.object(P, 'fetch_section', return_value='<p>new product</p>'), \
             patch.object(P, 'parse_tables', return_value=[]):
            self.assertIn('new product', self.call())
        got = json.loads(self.path.read_text())
        self.assertEqual(got['rcp'], '20260814000001')
        self.assertTrue(got['ok'])
        self.assertNotIn('old product', got['text'])

    def test_empty_response_preserves_previous_cache(self):
        before = self.path.read_bytes()
        with patch.object(P, '_cached_rcp', return_value='20260814000001'), \
             patch.object(P, 'toc', return_value=[]), \
             patch.object(P, 'find_sections', return_value={'products': {}}), \
             patch.object(P, 'fetch_section', return_value=''), self.assertRaises(RuntimeError):
            self.call()
        self.assertEqual(self.path.read_bytes(), before)

    def test_fetch_error_preserves_previous_cache(self):
        before = self.path.read_bytes()
        with patch.object(P, '_cached_rcp', return_value='20260814000001'), \
             patch.object(P, 'toc', side_effect=RuntimeError('network')), self.assertRaises(RuntimeError):
            self.call()
        self.assertEqual(self.path.read_bytes(), before)

    def test_fallback_search_uses_correct_half_year_report_kind(self):
        with patch.object(P, '_cached_rcp', return_value=None), \
             patch.object(P, 'search_reports', return_value=[]) as search, \
             patch.object(P, 'pick_report', return_value=[]):
            self.assertIsNone(self.call())
        self.assertEqual(search.call_args.args[-1], 'A002')

    def test_missing_new_product_section_preserves_valid_previous_text(self):
        before = self.path.read_bytes()
        with patch.object(P, '_cached_rcp', return_value='20260814000001'), \
             patch.object(P, 'toc', return_value=[]), patch.object(P, 'find_sections', return_value={}):
            self.call()
        self.assertEqual(self.path.read_bytes(), before)


class TestReportRetry(unittest.TestCase):
    def test_failed_same_receipt_retries_body_and_does_not_renew_failure_forever(self):
        import kdef_reports as R
        from datetime import date
        with tempfile.TemporaryDirectory() as folder, patch.object(R, 'CACHE', folder), \
             patch.object(R.RF, 'today', return_value=date(2026, 10, 15)):
            cache = Path(folder) / '123456' / '2026Q2.json'
            cache.parent.mkdir()
            previous = {'stock': '123456', 'quarter': '2026Q2', 'rcp': '20260814000001',
                        'ok': False, 'note': 'parser failure', '_refresh_checked_on': '2026-10-14'}
            cache.write_text(json.dumps(previous))
            with patch.object(R, 'search_reports', return_value=[('20260814000001', '반기보고서 (2026.06)')]), \
                 patch.object(R, 'toc', side_effect=RuntimeError('body retry reached')) as toc, \
                 self.assertRaisesRegex(RuntimeError, 'body retry reached'):
                R.collect_one({'stock': '123456', 'name': 'fixture'}, '2026Q2', log=io.StringIO())
            toc.assert_called_once_with('20260814000001')
            self.assertEqual(json.loads(cache.read_text()), previous)
