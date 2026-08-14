import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const config = JSON.parse(fs.readFileSync(path.join(root, 'data', 'tga_target.json'), 'utf8'));
const require = createRequire(import.meta.url);
const targetApi = require(path.join(root, 'tga_target.js'));
global.window = { PanoptesTgaTarget: targetApi };
const chartApi = require(path.join(root, 'liq_charts.js'))._test;
const now = Date.parse('2026-08-14T00:00:00Z');
const target = targetApi.validateConfig(config, now);
const charts = fs.readFileSync(path.join(root, 'liq_charts.js'), 'utf8');
const app = fs.readFileSync(path.join(root, 'app.js'), 'utf8');
const index = fs.readFileSync(path.join(root, 'index.html'), 'utf8');

assert.equal(config.schema_version, 1);
assert.ok(Number.isFinite(target.value) && target.value > 0, '목표값은 양의 유한수여야 함');
assert.equal(target.unit, 'billion_usd');
assert.equal(target.current_status, 'historical_latest_verified');
assert.ok(Date.parse(target.source_published_date) <= now, '발표일은 미래일 수 없음');
assert.ok(Number.isFinite(Date.parse(target.target_date)), '목표일은 유효한 ISO 날짜여야 함');

const clone = value => JSON.parse(JSON.stringify(value));
const invalid = patch => targetApi.validateConfig({
  treasury_cash_balance_assumption: Object.assign(clone(config.treasury_cash_balance_assumption), patch)
}, now);
assert.equal(targetApi.validateConfig({}, now), null, 'missing 입력은 선을 만들면 안 됨');
assert.equal(invalid({ value: 0 }), null);
assert.equal(invalid({ value: -1 }), null);
assert.equal(invalid({ value: 10001 }), null);
assert.equal(invalid({ unit: 'usd' }), null);
assert.equal(invalid({ source_id: 'unknown' }), null);
assert.equal(invalid({ current_status: 'unknown' }), null);
assert.equal(invalid({ source_published_date: '2027-01-01' }), null);
assert.equal(invalid({ target_date: 'not-a-date' }), null);
assert.equal(invalid({ target_date: '2026-02-30' }), null);
assert.equal(invalid({ current_status: 'current_verified' }), null, '만료 목표를 현행으로 위장하면 안 됨');

const staleDisplay = targetApi.displayModel(target);
assert.equal(staleDisplay.stale, true);
assert.equal(staleDisplay.lineLabel, 'DB 마지막 확인값 850B · Q1-26 · 현행성 미확인');
assert.match(staleDisplay.legendLabel, /확인 260106$/);
const current = invalid({
  current_status: 'current_verified', target_period: 'Q3 2026', target_period_label: 'Q3-26', target_date: '2026-09-30'
});
assert.equal(targetApi.displayModel(current).stale, false);
assert.match(targetApi.displayModel(current).legendLabel, /현행 공식값/);

const data = { sections: { funding: { references: { treasury_cash_balance_assumption: target } } } };
const tga = chartApi.fundingSpecs(data, {}).find(s => s.key === 'TGA');
assert.equal(tga.refs.length, 2, 'active TGA 차트는 목표선+내부 경계선 2개');
assert.equal(tga.refs[0].domain, true, '목표선은 모든 기간에서 y-domain에 포함');
assert.equal(tga.refs[0].label, staleDisplay.lineLabel);
const rendered = chartApi.chartSVG(
  ['2026-08-01', '2026-08-12'], [[880, 964]], ['#ff8a3d'], tga.refs, v => String(v)
).svg;
assert.equal((rendered.match(/stroke-dasharray="4 3"/g) || []).length, 2);

const missing = chartApi.fundingSpecs({ sections: { funding: {} } }, {}).find(s => s.key === 'TGA');
assert.equal(missing.refs.length, 1, '목표 메타가 없으면 내부 경계선만 유지');
assert.match(missing.sub, /미 재무부 목표 데이터 없음/);

assert.match(charts, /treasury_cash_balance_assumption/);
assert.doesNotMatch(charts, /v:\s*850/, '목표값을 렌더러에 하드코딩하면 안 됨');
assert.match(app, /data\/tga_target\.json/);
assert.match(app, /attachTgaTarget/);
assert.match(app, /esc\(refLabel\)/, 'fallback 메타 문자열은 escape해야 함');
assert.ok(index.indexOf('tga_target.js') < index.indexOf('liq_charts.js'));

console.log('tga target contract: ok');
