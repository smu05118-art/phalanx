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
const charts = fs.readFileSync(path.join(root, 'liq_charts.js'), 'utf8');
const app = fs.readFileSync(path.join(root, 'app.js'), 'utf8');
const index = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));

assert.equal(config.schema_version, 2);
const aug = targetApi.validateConfig(config, '2026-08-14');
assert.ok(aug, '공식 Treasury 설정은 검증을 통과해야 함');
assert.equal(aug.release.source_id, 'us_treasury_quarterly_borrowing_estimates');
assert.equal(new URL(aug.release.source_url).hostname, 'home.treasury.gov');
assert.equal(aug.release.source_published_date, '2026-08-03');
assert.equal(aug.current.value, 950);
assert.equal(aug.current.target_date, '2026-09-30');
assert.equal(aug.next.value, 850);
assert.equal(aug.next.target_date, '2026-12-31');

const oct = targetApi.validateConfig(config, '2026-10-01');
assert.equal(oct.current.value, 850, '분기 경과 후 다음 공식 가정을 자동 승격');
assert.equal(oct.current.target_date, '2026-12-31');
assert.equal(oct.next, null);
const expired = targetApi.validateConfig(config, '2027-01-01');
assert.equal(expired.current, null, '모든 목표일 경과 후 공식선을 숨김');
assert.equal(expired.next, null);

const invalid = mutate => {
  const candidate = clone(config);
  mutate(candidate);
  return targetApi.validateConfig(candidate, '2026-08-14');
};
assert.equal(targetApi.validateConfig({}, '2026-08-14'), null);
assert.equal(invalid(v => { v.schema_version = 1; }), null);
assert.equal(invalid(v => { v.release.source_id = 'gs_secondary'; }), null);
assert.equal(invalid(v => { v.release.source_url = 'https://example.com/sb0584'; }), null);
assert.equal(invalid(v => { v.release.source_url = 'https://evil@home.treasury.gov/news/press-releases/sb0584'; }), null);
assert.equal(invalid(v => { v.release.source_url += '?draft=1'; }), null);
assert.equal(invalid(v => { v.release.discovery_url = 'https://example.com/latest'; }), null);
assert.equal(invalid(v => { v.release.sources_uses_url = 'javascript:alert(1)'; }), null);
assert.equal(invalid(v => { v.release.source_published_date = '2027-01-01'; }), null);
assert.equal(invalid(v => { v.release.article_content_sha256 = 'bad'; }), null);
assert.equal(invalid(v => { v.assumptions[0].value = 0; }), null);
assert.equal(invalid(v => { v.assumptions[0].value = 10001; }), null);
assert.equal(invalid(v => { v.assumptions[0].unit = 'usd'; }), null);
assert.equal(invalid(v => { v.assumptions[0].target_date = '2026-09-29'; }), null);
assert.equal(invalid(v => { v.assumptions[0].target_date_label = '<img onerror=alert(1)>'; }), null);
assert.equal(invalid(v => { v.assumptions[1].target_date = v.assumptions[0].target_date; v.assumptions[1].target_date_label = v.assumptions[0].target_date_label; v.assumptions[1].target_period = v.assumptions[0].target_period; v.assumptions[1].target_period_label = v.assumptions[0].target_period_label; }), null);

const displays = targetApi.displayModels(aug);
assert.equal(displays.length, 2);
assert.equal(displays[0].lineLabel, '재무부 Q3말 950B · 260930');
assert.equal(displays[1].lineLabel, '다음 Q4말 850B · 261231');
assert.match(displays[0].legendLabel, /공식 발표 260803$/);

const data = {
  updated: '2026-08-14',
  sections: { funding: { references: { treasury_cash_balance_assumptions: config } } }
};
const tga = chartApi.fundingSpecs(data, {}).find(s => s.key === 'TGA');
assert.equal(tga.refs.length, 3, 'TGA 차트는 현재+다음 공식 가정선과 내부 경계선');
assert.equal(tga.refs[0].value, undefined);
assert.equal(tga.refs[0].v, 950);
assert.equal(tga.refs[1].v, 850);
assert.equal(tga.refs[2].v, 900);
assert.equal(tga.refs[0].domain, true);
assert.equal(tga.refs[1].domain, true);
assert.equal(tga.refs[2].domain, undefined, '내부 경계는 y축을 강제 확장하지 않음');
const rendered = chartApi.chartSVG(
  ['2026-08-01', '2026-08-12'], [[880, 964]], ['#ff8a3d'], tga.refs, v => String(v)
).svg;
assert.equal((rendered.match(/stroke-dasharray="4 3"/g) || []).length, 3);
assert.match(rendered, /재무부 Q3말 950B/);
assert.match(rendered, /다음 Q4말 850B/);

const afterExpiry = chartApi.fundingSpecs({
  updated: '2027-01-01',
  sections: { funding: { references: { treasury_cash_balance_assumptions: config } } }
}, {}).find(s => s.key === 'TGA');
assert.equal(afterExpiry.refs.length, 1);
assert.match(afterExpiry.sub, /업데이트 대기/);
const missing = chartApi.fundingSpecs({ updated: '2026-08-14', sections: { funding: {} } }, {}).find(s => s.key === 'TGA');
assert.equal(missing.refs.length, 1);
assert.match(missing.sub, /업데이트 대기/);

assert.match(charts, /treasury_cash_balance_assumptions/);
assert.doesNotMatch(charts, /v:\s*950/, '공식값을 렌더러에 하드코딩하면 안 됨');
assert.doesNotMatch(charts, /v:\s*850/, '다음 공식값도 렌더러에 하드코딩하면 안 됨');
assert.match(charts, /v:\s*900/, '기존 Panoptes 내부 경계는 유지');
assert.match(app, /data\/tga_target\.json/);
assert.match(app, /attachTgaTarget/);
assert.match(app, /esc\(refLabel\)/, 'fallback 메타 문자열은 escape해야 함');
assert.ok(index.indexOf('tga_target.js') < index.indexOf('liq_charts.js'));

console.log('tga target contract: ok');
