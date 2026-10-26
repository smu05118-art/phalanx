# -*- coding: utf-8 -*-
"""Regression contract for stale UI, date handling, and fail-closed data use.

The test is deliberately dependency-free.  Static checks run with Python alone;
runtime JavaScript checks use the system Node executable when it is available.
It works in both the source checkout (``jem_site_build.py`` present) and a
public-only checkout (generated ``jem_site/index.html`` present).
"""
import os
import shutil
import subprocess
import unittest
from pathlib import Path


SITE = Path(__file__).resolve().parents[2]
ROOT = SITE.parent
BUILDER = ROOT / "jem_site_build.py"
INDEX = SITE / "index.html"
PUBLIC_INSIGHT = SITE / "insight_charts.js"
SOURCE_INSIGHT = ROOT / "jem_data" / "insight" / "insight_charts.js"
NODE = shutil.which("node")


NODE_CONTRACT = r"""
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const uiSource = fs.readFileSync(process.env.STALE_UI_SOURCE, 'utf8');
const insightSource = fs.readFileSync(process.env.STALE_INSIGHT_SOURCE, 'utf8');
const contract = process.env.STALE_CONTRACT;

function between(source, start, end) {
  const a = source.indexOf(start);
  const b = source.indexOf(end, a + start.length);
  assert(a >= 0, 'missing start marker: ' + start);
  assert(b > a, 'missing end marker: ' + end);
  return source.slice(a, b);
}

function context(extra = {}) {
  const out = Object.assign({console}, extra);
  out.window = out.window || out;
  out.globalThis = out;
  vm.createContext(out);
  return out;
}

function dmmApi() {
  const c = context();
  const code = [
    "function gg2(n){return (n<10?'0':'')+n;}",
    "function gCoName(){return '';}",
    "function gPcqEsc(v){return String(v);}",
    between(uiSource, 'const DMMRR_VER =', '/* DMMRR:end */')
  ].join('\n');
  vm.runInContext(code, c);
  return c.window.DmmRunrate;
}

function dmmFixture(api, source, companyCoverage = '2026-10-26') {
  return {dmm_runrate: {
    schema: api.SCHEMA, status: 'ok', source_month: '2026-10',
    partial_months: ['2026-10'], source,
    co: {X: {raw: 1, runrate: 2, covered_days: 26, total_days: 31,
      coverage_start: '2026-10-01', coverage_end: companyCoverage}},
    held: {}
  }};
}

class Element {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.attributes = {};
    this.className = '';
    this._text = '';
  }
  appendChild(node) { this.children.push(node); return node; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  set innerHTML(_) { throw new Error('innerHTML must not receive evidence fields'); }
  set textContent(value) { this.children = []; this._text = String(value); }
  get textContent() {
    return this._text + this.children.map(node => node.textContent).join(' ');
  }
}

const contracts = {
  fresh_badge() {
    const c = context();
    const code = between(uiSource, 'function freshBadge(', '\nfunction companyCard(');
    vm.runInContext(code + '\nthis.freshBadge=freshBadge;', c);
    assert.equal(c.freshBadge(null), '');
    const badge = c.freshBadge({last_month: null, n_points: 0, missing_last3: true});
    assert(badge.includes('미관측 ⚠️STALE'));
    assert(badge.includes('관측 0pt'));
    const hostile = c.freshBadge({last_month: null,
      n_points: '</span><script>x</script>', missing_last3: true});
    assert(!hostile.includes('<script>'));
  },

  earnings_kst() {
    const instant = '2026-10-27T00:30:00+09:00';
    assert.equal(new Date(instant).getUTCDate(), 26);
    const c = context();
    const code = between(uiSource, 'function earnState(', '\nfunction nowcastOf(');
    vm.runInContext(code +
      '\nthis.earnState=earnState;this.earnChip=earnChip;this.earnCell=earnCell;', c);
    assert.equal(c.earnState('2026-10-26', instant), null);
    assert.equal(c.earnState('2026-10-27', instant).days, 0);
    assert.equal(c.earnState('2026-11-03', instant).days, 7);
    assert.equal(c.earnState('TBD', instant).tbd, true);
    for (const bad of ['', '2026-02-30', '2026-2-03',
      '2026-10-27<script>', 'not-a-date']) {
      assert.equal(c.earnState(bad, instant), null, bad);
    }
    assert.equal(c.earnState('2026-10-27', 'invalid'), null);
    assert.equal(c.earnChip({earn: 'invalid'}), '');
    assert.equal(c.earnCell('invalid'), '—');
  },

  dmm_exact_coverage() {
    const api = dmmApi();
    const now = '2026-10-27T00:30:00+09:00';
    const labels = ['2026-09', '2026-10'];
    const values = [4, 1];
    const valid = api.apply(dmmFixture(api, {coverage_end: '2026-10-26'}),
      api.SRC, labels, values, 'X', now);
    assert.equal(valid.hold, null);
    assert.deepEqual(Array.from(valid.display), [4, 2]);
    assert.deepEqual(Array.from(valid.growth), [4, null]);
    assert.deepEqual(labels, ['2026-09', '2026-10']);
    assert.deepEqual(values, [4, 1]);

    for (const [source, companyCoverage] of [
      [null, '2026-10-26'],
      ['2026-10-26', '2026-10-26'],
      [Object.assign([], {coverage_end: '2026-10-26'}), '2026-10-26'],
      [{}, '2026-10-26'],
      [{coverage_end: '2026-10-25'}, '2026-10-26'],
      [{coverage_end: '2026-10-26'}, '2026-10-25']
    ]) {
      const held = api.apply(dmmFixture(api, source, companyCoverage),
        api.SRC, labels, values, 'X', now);
      assert.equal(held.hold, 'stale_snapshot');
      assert.deepEqual(Array.from(held.display), [4, 1]);
      assert.deepEqual(Array.from(held.growth), [4, null]);
    }
  },

  dmm_boundaries() {
    const api = dmmApi();
    assert.equal(api.jstYmd('2026-10-26T14:59:59Z', -1), '2026-10-25');
    assert.equal(api.jstYmd('2026-10-26T15:00:00Z', -1), '2026-10-26');
    assert.equal(api.nowYm('2026-10-31T14:59:59Z'), '2026-10');
    assert.equal(api.nowYm('2026-10-31T15:00:00Z'), '2026-11');
    const oldMonth = dmmFixture(api, {coverage_end: '2026-10-31'}, '2026-10-31');
    const out = api.apply(oldMonth, api.SRC, ['2026-10'], [1], 'X',
      '2026-10-31T15:00:00Z');
    assert.equal(out.hold, 'stale_source');
  },

  insight_dom_safety() {
    const document = {
      createElement: tag => new Element(tag),
      createTextNode: value => {
        const node = new Element('#text');
        node.textContent = value;
        return node;
      }
    };
    const c = context({document});
    const code = [
      between(insightSource, '  function h(', '\n  function fnum('),
      between(insightSource, '  function fnum(', '\n  function chipText('),
      between(insightSource, '  function chipText(', '\n  function resolve('),
      between(insightSource, '  function evidenceChip(', '\n  function card('),
      'this.evidenceChip=evidenceChip;'
    ].join('\n');
    vm.runInContext(code, c);
    const payload = '<img src=x onerror="globalThis.pwned=1">';
    const link = c.evidenceChip({label: payload, value: 1, unit: '%',
      asof: '2026-01-01<script>', stale: true, age_months: 9,
      note: payload, src: 'https://example.com/source'});
    assert.equal(link.tagName, 'a');
    assert.equal(link.attributes.target, '_blank');
    assert.equal(link.attributes.rel, 'noopener');
    assert.equal(c.pwned, undefined);
    assert(link.textContent.includes(payload));
    assert(link.textContent.includes('2026-01-01<script>'));
    assert(link.textContent.includes('⚠ STALE 9개월'));
    assert(link.children[0].className.includes('stale'));
    assert.equal(link.children[0].attributes.title,
      payload + ' · 최신 근거가 신선도 기준을 넘어 해석 주의');
    const tags = [];
    (function walk(node) {
      tags.push(node.tagName);
      node.children.forEach(walk);
    }(link));
    assert(!tags.includes('img'));
    assert(!tags.includes('script'));
  }
};

assert(Object.hasOwn(contracts, contract), 'unknown contract: ' + contract);
contracts[contract]();
"""


class StaleUiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PUBLIC_INSIGHT.is_file():
            raise AssertionError(f"public insight asset missing: {PUBLIC_INSIGHT}")
        if BUILDER.is_file():
            cls.ui_source_path = BUILDER
        elif INDEX.is_file():
            cls.ui_source_path = INDEX
        else:
            raise AssertionError("need root jem_site_build.py or generated jem_site/index.html")
        cls.ui_source = cls.ui_source_path.read_text(encoding="utf-8")
        cls.insight_source = PUBLIC_INSIGHT.read_text(encoding="utf-8")

    def run_node_contract(self, contract):
        if NODE is None:
            self.skipTest("Node is required for the JavaScript runtime contract")
        env = os.environ.copy()
        env.update({
            "STALE_UI_SOURCE": str(self.ui_source_path),
            "STALE_INSIGHT_SOURCE": str(PUBLIC_INSIGHT),
            "STALE_CONTRACT": contract,
            # The result must not depend on the machine's viewer timezone.
            "TZ": "America/New_York",
        })
        completed = subprocess.run(
            [NODE, "-e", NODE_CONTRACT],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"Node contract {contract!r} failed:\n{completed.stdout}{completed.stderr}",
        )

    def test_source_and_public_insight_are_identical_and_keep_light_theme(self):
        if SOURCE_INSIGHT.is_file():
            self.assertEqual(SOURCE_INSIGHT.read_bytes(), PUBLIC_INSIGHT.read_bytes())
        for token in (
                "--jemi-bg", ':root[data-theme="light"]', "get color()",
                ".jemi-chip.stale", "var(--jemi-bad,#e0574e)", "age_months"):
            with self.subTest(token=token):
                self.assertIn(token, self.insight_source)

    def test_builder_or_generated_page_wires_all_stale_states(self):
        for token in (
                "q.stale?'컨센서스 오래됨':null", "function earnCell(",
                "stale_snapshot: '소스 미갱신", "function freshBadge("):
            with self.subTest(token=token):
                self.assertIn(token, self.ui_source)
        if BUILDER.is_file():
            for token in ("apply_consensus_freshness(",
                          "load_model_state(), _dt.date.today()"):
                with self.subTest(token=token):
                    self.assertIn(token, self.ui_source)

    def test_missing_observation_badge_and_markup_coercion(self):
        self.run_node_contract("fresh_badge")

    def test_earnings_dates_use_kst_independent_of_viewer_timezone(self):
        self.run_node_contract("earnings_kst")

    def test_dmm_requires_exact_global_and_company_coverage(self):
        self.run_node_contract("dmm_exact_coverage")

    def test_dmm_jst_midnight_and_source_month_boundaries(self):
        self.run_node_contract("dmm_boundaries")

    def test_insight_evidence_uses_literal_dom_text(self):
        self.run_node_contract("insight_dom_safety")


if __name__ == "__main__":
    unittest.main()
