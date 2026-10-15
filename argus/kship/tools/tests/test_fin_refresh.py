"""재무 캐시 갱신과 정정 전 원문 보존. 외부 요청은 사용하지 않는다."""
import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kship_fin as F


class TestFinRefresh(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        for obj, name, value in [(F, 'FIN_CACHE', self.tmp.name), (F, '_log', lambda _: None),
                                  (F.RF, 'today', lambda: datetime.date(2026, 10, 15))]:
            p = patch.object(obj, name, value); p.start(); self.addCleanup(p.stop)
        self.paths = {k: Path(v) for k, v in F.cache_paths('123456', '2026Q2').items()}
        self.paths['meta'].parent.mkdir()
        self.old = {'stock': '123456', 'quarter': '2026Q2', 'rcp': '20260814000001',
                    'sections': {'cons': {}}, 'notes': {'items': {'fin': {}}}, 'note': '',
                    '_refresh_checked_on': '2026-10-14'}
        self.paths['meta'].write_text(json.dumps(self.old))
        self.paths['cons'].write_text('<table>old face</table>')
        self.note = Path(F.note_cache_path('123456', '2026Q2', 'fin'))
        self.note.write_text('<table>old notes</table>')

    def call(self, reports=None):
        return F.collect_quarter('123456', 'fixture', '2026Q2',
                                 {'A002': reports if reports is not None else [('20261015000001', '[기재정정]반기보고서 (2026.06)')]})

    def test_same_receipt_refresh_is_metadata_only(self):
        before = F.cache_fingerprint()
        with patch.object(F, 'toc') as toc:
            self.call([('20260814000001', '반기보고서 (2026.06)')])
        toc.assert_not_called()
        self.assertEqual(F.cache_fingerprint(), before)
        self.assertEqual(json.loads(self.paths['meta'].read_text())['_refresh_checked_on'], '2026-10-15')

    def test_correction_refreshes_body_and_invalidates_old_notes_with_archive(self):
        before = F.cache_fingerprint()
        with patch.object(F, 'toc', return_value=[]), patch.object(F, 'find_fin_sections', return_value={'cons': {'text': 'new'}}), \
             patch.object(F, 'fetch_section', return_value='<table>new face</table>'):
            got = self.call()
        self.assertEqual(got['rcp'], '20261015000001')
        self.assertNotIn('notes', got)
        self.assertFalse(self.note.exists())
        self.assertEqual(self.paths['cons'].read_text(), '<table>new face</table>')
        saved = [p.read_text() for p in (self.paths['meta'].parent / '_revisions').iterdir()]
        self.assertIn('<table>old face</table>', saved)
        self.assertIn('<table>old notes</table>', saved)
        self.assertNotEqual(F.cache_fingerprint(), before)

    def test_section_fetch_failure_keeps_entire_old_receipt(self):
        before = F.cache_fingerprint()
        with patch.object(F, 'toc', return_value=[]), \
             patch.object(F, 'find_fin_sections', return_value={'cons': {'text': 'cons'}, 'shares': {'text': 'shares'}}), \
             patch.object(F, 'fetch_section', side_effect=['<table>new face</table>', RuntimeError('network')]), \
             self.assertRaises(RuntimeError):
            self.call()
        self.assertEqual(F.cache_fingerprint(), before)
        self.assertTrue(self.note.exists())

    def test_empty_search_does_not_replace_valid_receipt(self):
        before = F.cache_fingerprint()
        with self.assertRaises(RuntimeError):
            self.call([])
        self.assertEqual(F.cache_fingerprint(), before)

    def test_negative_cache_rechecks_next_day(self):
        self.paths['meta'].write_text(json.dumps({'rcp': None, 'sections': {}, '_refresh_checked_on': '2026-10-14'}))
        with patch.object(F, 'toc', return_value=[]), patch.object(F, 'find_fin_sections', return_value={'cons': {'text': 'cons'}}), \
             patch.object(F, 'fetch_section', return_value='<table>first face</table>'):
            got = self.call()
        self.assertEqual(got['rcp'], '20261015000001')

    def test_missing_report_search_result_is_error_not_negative_observation(self):
        before = F.cache_fingerprint()
        with self.assertRaises(RuntimeError):
            F.collect_quarter('123456', 'fixture', '2026Q2', {'A002': None})
        self.assertEqual(F.cache_fingerprint(), before)

    def test_metadata_write_failure_restores_entire_quarter(self):
        before = F.cache_fingerprint()
        original_write = F.atomic_write
        def fail_meta(path, text):
            if str(path) == str(self.paths['meta']):
                raise OSError('fixture metadata write failure')
            return original_write(path, text)
        with patch.object(F, 'toc', return_value=[]), \
             patch.object(F, 'find_fin_sections', return_value={'cons': {'text': 'new'}, 'shares': {'text': 'shares'}}), \
             patch.object(F, 'fetch_section', return_value='<table>new face</table>'), \
             patch.object(F, 'atomic_write', side_effect=fail_meta), self.assertRaises(OSError):
            self.call()
        self.assertEqual(F.cache_fingerprint(), before)
        self.assertEqual(json.loads(self.paths['meta'].read_text()), self.old)
        self.assertEqual(self.paths['cons'].read_text(), '<table>old face</table>')
        self.assertEqual(self.note.read_text(), '<table>old notes</table>')
        self.assertFalse(self.paths['shares'].exists())
        self.assertFalse(Path(F._pending_path('123456', '2026Q2')).exists())

    def test_body_write_failure_restores_entire_quarter(self):
        before = F.cache_fingerprint()
        original_write = F.atomic_write
        def fail_body(path, text):
            if str(path) == str(self.paths['cons']):
                raise OSError('fixture body write failure')
            return original_write(path, text)
        with patch.object(F, 'toc', return_value=[]), \
             patch.object(F, 'find_fin_sections', return_value={'cons': {'text': 'new'}}), \
             patch.object(F, 'fetch_section', return_value='<table>new face</table>'), \
             patch.object(F, 'atomic_write', side_effect=fail_body), self.assertRaises(OSError):
            self.call()
        self.assertEqual(F.cache_fingerprint(), before)
        self.assertTrue(self.note.exists())

    def test_failed_rollback_leaves_marker_and_blocks_read_build_and_fingerprint(self):
        with patch.object(F, 'toc', return_value=[]), \
             patch.object(F, 'find_fin_sections', return_value={'cons': {'text': 'new'}}), \
             patch.object(F, 'fetch_section', return_value='<table>new face</table>'), \
             patch.object(F, '_write_meta', side_effect=OSError('metadata failure')), \
             patch.object(F, '_restore_snapshot', side_effect=OSError('restore failure')), self.assertRaises(OSError):
            self.call()
        self.assertTrue(Path(F._pending_path('123456', '2026Q2')).exists())
        with self.assertRaisesRegex(RuntimeError, '교체 미완료'):
            F._read_meta('123456', '2026Q2')
        with self.assertRaisesRegex(RuntimeError, '교체 미완료'):
            F.cache_fingerprint()
        with patch.object(F, 'company_names', return_value={}), self.assertRaisesRegex(RuntimeError, '교체 미완료'):
            F.build_company('123456', ['2026Q2'], name='fixture')

    def test_same_negative_result_updates_only_checkdate(self):
        old = {'stock': '123456', 'quarter': '2026Q2', 'rcp': None, 'title': None, 'kind': 'A002',
               'sections': {}, 'note': 'no_report', 'collected_at': '2026-10-14', '_refresh_checked_on': '2026-10-14'}
        self.paths['meta'].write_text(json.dumps(old))
        before = F.cache_fingerprint()
        got = self.call([])
        self.assertEqual(got['collected_at'], '2026-10-14')
        self.assertEqual(got['_refresh_checked_on'], '2026-10-15')
        self.assertEqual(F.cache_fingerprint(), before)
