import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('builder',Path(__file__).parents[1]/'build.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
ROOT=Path(__file__).resolve().parents[3]

class BuildTests(unittest.TestCase):
    def test_parse_does_not_execute_code(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'input.js';p.write_text('window.AID={"x":1};evil();')
            with self.assertRaises(ValueError):b.read_assignment(p,'AID')
            p.write_text('window.WRONG={};')
            with self.assertRaises(ValueError):b.read_assignment(p,'AID')
    def test_revision_and_first_seen(self):
        raw={'key':'same','value':0};first=b.merge_history([], [raw], '2026-09-10')
        self.assertEqual(b.merge_history(first,[raw],'2026-09-11'),first)
        revised=b.merge_history(first,[dict(raw,value=10)],'2026-09-12')
        self.assertEqual(len(revised),2)
        self.assertEqual(revised[1]['first_seen_at'],'2026-09-10')
        self.assertEqual(revised[1]['supersedes'],first[0]['id'])
        self.assertEqual(revised[1]['revision'],2)
    def test_duplicate_input_fails(self):
        with self.assertRaises(ValueError):b.merge_history([],[{'key':'a'},{'key':'a'}],'2026-09-10')
    def test_zero_is_not_missing(self):
        self.assertTrue(b.number(0));self.assertFalse(b.number(None));self.assertFalse(b.number(True));self.assertFalse(b.number(float('nan')))
    def test_legacy_offline_data_never_verified(self):
        providers,rows=b.import_signals(b.read_assignment(ROOT/'data_ai.js','AID'))
        self.assertEqual(len(providers),22)
        self.assertNotIn('META',providers)
        self.assertTrue(all(r['verified'] is False and r['direction'] is None for r in rows))
        nbis=[r for r in rows if r['provider']=='NBIS' and r['metric']=='rpo_usd_m']
        self.assertTrue(nbis and all('선수수익' in r['note'] for r in nbis))
    def test_official_validation(self):
        providers,_=b.import_signals(b.read_assignment(ROOT/'data_ai.js','AID'))
        rows=json.loads((ROOT/'data/cloud_signals/reviewed.json').read_text())['signals']
        for r in rows:b.validate_observation(r,providers,b.date('2026-09-10'))
        for change in ({'source_url':'https://assets.nebius.com.evil.invalid/x'}, {'verified_at':'2027-01-01'},
                       {'published_at':'2027-01-01'},{'direction':True},{'value':None},{'evidence':'target'}):
            r=dict(rows[0],**change)
            with self.subTest(change=change),self.assertRaises(ValueError):b.validate_observation(r,providers,b.date('2026-09-10'))
    def test_atomic_size_failure_keeps_file(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'out';p.write_text('old')
            with self.assertRaises(ValueError):b.atomic_write(p,{'x':'x'*b.LIMIT})
            self.assertEqual(p.read_text(),'old')
    def test_integration_exact_shared_source(self):
        a=b.read_assignment(ROOT/'data_ai.js','AID');p,_=b.import_signals(a)
        audit=b.integration_audit(ROOT,a,p)
        self.assertTrue(audit['shared_capex_equal'])
        self.assertTrue(audit['projects']['MSFT'])
        self.assertTrue(all(x['relation'] in ('customer','operator') for xs in audit['projects'].values() for x in xs))
        a=copy.deepcopy(a);a['capex_common']['rows'][0][3]+=1
        self.assertFalse(b.integration_audit(ROOT,a,p)['shared_capex_equal'])

if __name__=='__main__':unittest.main()
