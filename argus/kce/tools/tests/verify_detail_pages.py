#!/usr/bin/env python3
"""Offline semantic/regression checks. No packages or network.

Synthetic fixtures exercise absent edge cases; they never become sample facts.
Node, if available locally, additionally executes the client filter/re-sum code.
"""
import copy
from decimal import Decimal
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
import kce_detail_pages as g

ROOT = Path(__file__).resolve().parent
PANEL = json.loads((g.INPUT / "kce_panel_data.json").read_text())
POSITIONS = json.loads((g.INPUT / "kce_table_positions.json").read_text())
AUDIT = json.loads((g.INPUT / "grade_audit.json").read_text())
RESULTS = {}


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.rows, self.scripts, self.links, self.assets, self.ids = [], [], [], [], []
        self.row = None
        self.td = None
        self.script = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.append(a['id'])
        if tag == 'tr':
            self.row = {'attrs': a, 'cells': []}
            self.rows.append(self.row)
        if tag == 'td' and self.row is not None:
            self.td = {'attrs': a, 'text': ''}
            self.row['cells'].append(self.td)
        if tag == 'script':
            self.script = ''
        if tag == 'a':
            self.links.append(a.get('href', ''))
        if tag in ('script', 'img', 'iframe', 'link'):
            self.assets.append(a.get('src') or a.get('href') or '')

    def handle_data(self, data):
        if self.td is not None:
            self.td['text'] += data
        if self.script is not None:
            self.script += data

    def handle_endtag(self, tag):
        if tag == 'td':
            self.td = None
        if tag == 'tr':
            self.row = None
        if tag == 'script':
            self.scripts.append(self.script)
            self.script = None


def fixture():
    def site(i, name, cmp, **kw):
        row = {'id': i, 'nm': name, 'cl': 'client', 'sd': '2020-01', 'ed': '2029-12',
               'reg': '국내', 'seg': '토목', 'agg': False, 'amt': [100] * 4,
               'cmp': cmp, 'bal': [30] * 4, 'sFilled': None}
        row.update(kw)
        return row
    data = {'co': 'synthetic', 'fq': ['2025Q1', '2025Q2', '2025Q3', '2025Q4'], 'sites': [
        site('s1', '관측현장', [10, 10, 7, 11]),
        site('s2', '가공현장', [5, 8, 12, 17], sFilled=[None, 'interp', None, None]),
        site('s3', '합 계', [1000, 2000, 3000, 4000]),
        site('s4', '기타현장 묶음', [100, 300, 700, 900]),
        site('s5', '별도 집계', [50, 100, 150, 200], agg=True),
        site('s6', '결측현장', [None, 1, None, 3]),
    ]}
    for row in data['sites']:
        row['cmp'] = [v * 1000 if v is not None else None for v in row['cmp']]
    panel = {'999999': data}
    audit = {'companies': [{'stock': '999999', 'now': 'fixture', 'quarters': 4,
                             'can': {p: 'conditional' for p in g.PAGES}, 'blocker': []}]}
    return panel, audit


class DetailTests(unittest.TestCase):
    def test_01_audit_denials_are_not_truthy(self):
        p, a = fixture()
        for raw in [False, 'false', 'no', 'unknown', None, 'unexpected']:
            for page in g.PAGES:
                a['companies'][0]['can'][page] = raw
            self.assertIsNone(g.build_matrix(p, '999999', audit=a))
            self.assertIsNone(g.build_trace(p, {}, '999999', audit=a))
            self.assertIsNone(g.build_backtest(p, '999999', audit=a))
        self.assertIsNone(g.build_matrix(p, '999999', audit={'companies': []}))

    def test_02_null_zero_negative_aggregation_and_fills(self):
        p, a = fixture()
        d = p['999999']
        obs, fill, *others = d['sites']
        self.assertEqual(g.series(d, obs)['values'], [None, 0, -3000, 4000])
        self.assertEqual(g.series(d, fill)['markers'], [None, 'interp', 'interp', None])
        for s in others:
            self.assertEqual(g.series(d, s)['values'], [None] * 4)
        page = Page(g.build_matrix(p, '999999', audit=a))
        row = next(r for r in page.rows if r['attrs'].get('id') == 'total')
        self.assertEqual([c['text'] for c in row['cells'][1:]], ['–', '0.0', '-3.0', '9.0'])
        parsed_fill = next(r for r in page.rows if r['attrs'].get('data-id') == 's2')
        self.assertIn('fli', parsed_fill['cells'][2]['attrs']['class'])
        self.assertIn('fli', parsed_fill['cells'][3]['attrs']['class'])
        bt = g.backtest_data(d)
        self.assertEqual(bt['n'], 2)
        self.assertEqual([f['examples'][0]['id'] for f in bt['folds']], ['s1', 's1'])
        self.assertEqual([f['examples'][0]['predicted'] for f in bt['folds']], [0, -3000])

    def test_03_fill_marker_shapes(self):
        p, _ = fixture()
        d = p['999999'];s = d['sites'][0]
        for marker in [{'cmp': [None, 'p8', None, None]}, {'2025Q2': 'p8'}, {'cmp': {'1': 'p8'}}]:
            s['sFilled'] = marker
            self.assertIsNone(g.filled(s, 'cmp', 0, d['fq']))
            self.assertEqual(g.filled(s, 'cmp', 1, d['fq']), 'p8')
        for marker in [True, {'unsupported': 'opaque'}, 'unknown-src']:
            s['sFilled'] = marker
            self.assertTrue(g.filled(s, 'cmp', 0, d['fq']))
        s['sFilled'] = {'amt': [None, 'interp', None, None]}
        self.assertIsNone(g.filled(s, 'cmp', 1, d['fq']))

    def test_04_nonconsecutive_and_duplicate_identity(self):
        p, a = fixture();d = p['999999']
        d['fq'] = ['2025Q1', '2025Q2', '2025Q4', '2026Q1']
        self.assertIsNone(g.series(d, d['sites'][0])['values'][2])
        self.assertFalse(g.backtest_data(d)['folds'])
        p, a = fixture();d = p['999999']
        duplicate = copy.deepcopy(d['sites'][0]);duplicate['id'] = 's7'
        d['sites'].append(duplicate)
        self.assertEqual(g.series(d, d['sites'][0])['values'], [None] * 4)
        self.assertIsNone(g.build_backtest(p, '999999', audit=a))

    def test_05_prediction_does_not_read_holdout_or_schedule(self):
        p, _ = fixture();d = p['999999']
        old = g.backtest_data(d)['folds'][0]['examples'][0]
        d['sites'][0]['cmp'][2] = 999999
        d['sites'][0]['ed'] = '2100-01'
        d['sites'][0]['bal'] = [999999] * 4
        new = g.backtest_data(d)['folds'][0]['examples'][0]
        self.assertEqual(old['predicted'], new['predicted'])
        self.assertNotEqual(old['actual'], new['actual'])

    def test_06_trace_requires_audit_receipt_and_zero_based_location(self):
        self.assertIsNone(g.build_trace(PANEL, {}, '001260', audit=AUDIT))
        self.assertIsNone(g.build_trace(PANEL, POSITIONS, '011370', audit=AUDIT))
        self.assertIsNone(g.build_trace(PANEL, POSITIONS, '001470', audit=AUDIT))
        q = PANEL['001260']['fq'][0]
        for invalid in [{}, {'rcpNo': 'invalid', 'tables': [{'i': 0}]},
                        {'rcpNo': '20220322000463', 'tables': [{}]}]:
            self.assertIsNone(g.build_trace(PANEL, {'001260': {q: invalid}}, '001260', audit=AUDIT))
        html = g.build_trace(PANEL, POSITIONS, '001260', audit=AUDIT)
        page = Page(html)
        dart = [l for l in page.links if l.startswith('https://dart.')]
        self.assertEqual(len(dart), 19)
        self.assertIn('i=0 (0기반)', html)
        self.assertTrue(all('#' not in l and 'dcmNo' not in l for l in dart))
        self.assertEqual(len(page.ids), len(set(page.ids)))
        for link in page.links:
            if link.startswith('#'):
                self.assertIn(link[1:], page.ids)

    def test_07_input_text_is_data(self):
        p, a = fixture();p['999999']['sites'][0]['nm'] = '</script><script>alert(1)</script>&"'
        page = g.build_matrix(p, '999999', audit=a)
        self.assertNotIn('</script><script>alert(1)', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('</script>', g.json_html(['</script>\u2028&']))

    def test_08_real_numbers_independent_decimal_calculation(self):
        data = PANEL['001260']
        site = next(s for s in data['sites'] if s['id'] == '001260-0003')
        self.assertEqual(Decimal(str(site['cmp'][1])) - Decimal(str(site['cmp'][0])), Decimal('4189.651'))
        self.assertEqual(Decimal(str(site['cmp'][12])) - Decimal(str(site['cmp'][11])), Decimal('-46977.178'))
        reference = Decimal(0);n = 0
        for s in data['sites']:
            if s['agg'] or s['nm'] == '기타현장':
                continue
            if s['cmp'][-1] is not None and s['cmp'][-2] is not None:
                reference += Decimal(str(s['cmp'][-1])) - Decimal(str(s['cmp'][-2]));n += 1
        self.assertEqual(reference, Decimal('63820.409'))
        self.assertEqual(n, 27)
        bt = g.backtest_data(data)
        self.assertEqual(len(bt['folds']), 17)
        self.assertEqual(bt['n'], 114)
        self.assertIsNone(bt['folds'][0]['wape'])
        errors, actuals = Decimal(0), Decimal(0)
        for fold in bt['folds']:
            for row in fold['examples']:
                a, b, c = map(lambda v: Decimal(str(v)), row['cmp'])
                pred, actual = b - a, c - b
                errors += abs(pred - actual);actuals += abs(actual)
        self.assertAlmostEqual(bt['mae'], float(errors / Decimal(bt['n'])))
        self.assertAlmostEqual(bt['wape'], float(errors / actuals * 100))
        RESULTS['manual'] = {'last_quarter_partial_sum_million': str(reference), 'last_quarter_sites': n,
                             'origins': 17, 'samples': bt['n'], 'sites': bt['sites'],
                             'absolute_error_sum_million': str(errors), 'absolute_target_sum_million': str(actuals),
                             'mae_million': bt['mae'], 'wape_percent': bt['wape']}

    def test_09_all_company_gates_and_no_input_mutation(self):
        before = json.dumps(PANEL, ensure_ascii=False, sort_keys=True)
        with tempfile.TemporaryDirectory(prefix='verify-all-', dir=ROOT) as temp:
            manifest = g.build_all(PANEL, POSITIONS, temp, audit=AUDIT)
            self.assertEqual(len(manifest), 29)
            for stock, item in manifest.items():
                for page, state in item['pages'].items():
                    self.assertEqual((Path(temp) / stock / (page + '.html')).exists(), state['generated'])
                    if not g.decision(PANEL, stock, page, AUDIT)[0]:
                        self.assertFalse(state['generated'])
                    if state['generated']:
                        parsed = Page((Path(temp) / stock / (page + '.html')).read_text())
                        self.assertTrue(all(not x or x.startswith(('../vendor/', 'vendor/')) for x in parsed.assets))
                        self.assertEqual(len(parsed.ids), len(set(parsed.ids)))
            RESULTS['company_availability'] = manifest
        self.assertEqual(before, json.dumps(PANEL, ensure_ascii=False, sort_keys=True))
        expected = json.loads((ROOT / 'input_sha256.json').read_text())
        self.assertEqual(expected, {name: hashlib.sha256((ROOT.parent / name).read_bytes()).hexdigest() for name in expected})
        RESULTS['input_hashes_unchanged'] = True

    def test_10_stale_denied_pages_and_output_boundary(self):
        with tempfile.TemporaryDirectory(prefix='verify-stale-', dir=ROOT) as temp:
            d = Path(temp) / '011370';d.mkdir()
            (d / 'matrix.html').write_text('stale')
            with self.assertRaises(FileExistsError):
                g.build_all(PANEL, POSITIONS, temp, ['011370'], audit=AUDIT)
            self.assertFalse((d / 'status.html').exists())
        with self.assertRaises(ValueError):
            g.build_all(PANEL, POSITIONS, ROOT.parent / 'input', ['001260'], audit=AUDIT)

    @unittest.skipUnless(shutil.which('node'), 'local Node unavailable; browser logic check skipped')
    def test_11_execute_client_resummation_and_trace_search(self):
        p, a = fixture()
        page = Page(g.build_matrix(p, '999999', audit=a))
        # A small DOM adapter exercises actual shipped JS, including null != zero,
        # aggregate exclusion, group/search filtering and optional processed totals.
        harness = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const payload=JSON.parse(fs.readFileSync(0,'utf8'));
function wrap(r){return {dataset:Object.fromEntries(Object.entries(r.attrs).filter(([k])=>k.startsWith('data-')).map(([k,v])=>[k.slice(5),v])),hidden:false,
 cells:r.cells.map(c=>({textContent:c.text})),querySelectorAll(){return this.cells;},querySelector(){return this.cells[0];}};}
const rows=payload.rows.filter(r=>'data-q' in r.attrs).map(wrap);
const groups=payload.rows.filter(r=>r.attrs.class==='grp'&&'data-gid' in r.attrs).map(wrap);
const elements={total:wrap(payload.rows.find(r=>r.attrs.id==='total'))};
for(const id of ['search','group','processed','count','coverage']) elements[id]={value:'',checked:false,textContent:'',addEventListener(){}};
const document={getElementById(id){return elements[id];},querySelectorAll(s){if(s==='#tb tr[data-q]')return rows;
 if(s==='#tb tr.grp[data-gid]')return groups;if(s==='#matrix thead th')return Array(5);throw Error(s);}};
const context=vm.createContext({document});vm.runInContext(payload.script,context);
let sum=()=>elements.total.cells.slice(1).map(c=>c.textContent);
assert.deepStrictEqual(sum(),['–','0.0','-3.0','9.0']);
assert(elements.coverage.textContent.includes('2025Q2: 1건'));
elements.search.value='no-match';vm.runInContext('update()',context);assert.deepStrictEqual(sum(),['–','–','–','–']);
elements.search.value='가공현장';vm.runInContext('update()',context);assert.deepStrictEqual(sum(),['–','–','–','5.0']);
elements.processed.checked=true;vm.runInContext('update()',context);assert.deepStrictEqual(sum(),['–','3.0','4.0','5.0']);
assert(elements.coverage.textContent.includes('2025Q2: 1건'));
elements.search.value='합 계';vm.runInContext('update()',context);assert.deepStrictEqual(sum(),['–','–','–','–']);
elements.search.value='';elements.group.value='1';vm.runInContext('update()',context);assert.deepStrictEqual(sum(),['–','–','–','–']);
console.log('matrix JS: null/zero, processed endpoints, search, group, aggregate exclusion PASS');
'''
        completed = subprocess.run(['node', '-e', harness], input=json.dumps({'rows': page.rows, 'script': page.scripts[0]}),
                                   text=True, capture_output=True, check=True)
        RESULTS['client_resum'] = completed.stdout.strip()
        # Parse/syntax-check every real sample script, plus execute trace filtering.
        trace = Page(g.build_trace(PANEL, POSITIONS, '001260', audit=AUDIT))
        tharness = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const script=fs.readFileSync(0,'utf8');const rows=Array.from({length:65},()=>({hidden:false}));
const input={value:'',addEventListener(){}};const count={textContent:''};
const document={querySelectorAll(){return rows;},getElementById(id){return id==='trace-search'?input:count;}};
const c=vm.createContext({document});vm.runInContext(script,c);assert.strictEqual(count.textContent,'65행');
input.value='001260-0003';vm.runInContext('traceFilter()',c);assert.strictEqual(count.textContent,'1행');
console.log('trace JS: default 65 rows and exact-code search PASS');
'''
        done = subprocess.run(['node', '-e', tharness], input=trace.scripts[0], text=True, capture_output=True, check=True)
        RESULTS['client_trace'] = done.stdout.strip()
        for builder in [lambda: g.build_matrix(PANEL, '001260', audit=AUDIT),
                        lambda: g.build_trace(PANEL, POSITIONS, '001260', audit=AUDIT),
                        lambda: g.build_backtest(PANEL, '001260', audit=AUDIT)]:
            for script in Page(builder()).scripts:
                subprocess.run(['node', '--check'], input=script, text=True, capture_output=True, check=True)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DetailTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    RESULTS['tests_run'] = result.testsRun
    RESULTS['failures'] = len(result.failures)
    RESULTS['errors'] = len(result.errors)
    RESULTS['skipped'] = len(result.skipped)
    (ROOT / 'validation_results.json').write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2) + '\n')
    sys.exit(not result.wasSuccessful())
