/* ui/patch.js 모듈 8 런타임 하네스 — 브라우저 전역을 최소로 흉내 내고
   국가 큐브 지연 로드를 실제로 돌려본다. node tools/tests/patch_module8_harness.js <shardDir> */
'use strict';
const fs = require('fs'), path = require('path'), assert = require('assert');
const ROOT = path.resolve(__dirname, '..', '..');
const SHARDS = process.argv[2];

const log = [];
function fail(m){ console.log('FAIL ' + m); process.exit(1); }

/* ---- 브라우저 전역 스텁 ---- */
const pending = [];                       /* 주입된 <script> 큐 */
const head = { appendChild(el){ pending.push(el); } };
const main = { innerHTML: '' };
global.document = {
  head,
  getElementById: id => (id === 'main' ? main : null),
  createElement: () => ({ set src(v){ this._src = v; }, get src(){ return this._src; } }),
  addEventListener(){},
  querySelector(){ return null; },
  querySelectorAll(){ return []; },
};
global.window = global;
global.console = console;

let REGION = { cdir: 'data_jp_country/', csets: ['probe_core', 'mem_broad'] };
global.P = { companies: [], cdata: {} };
global.ST = { region: 'JP', tab: 'dash', view: 'overview', cat: 'all', q: '', mode: 'core', split: false };
global.MONTHS = ['2009-01'];
global.CCOL = ['#000'];
global.regionObj = () => REGION;
let CURSET = 'probe_core';
global.setKey = () => CURSET;
global.compObj = () => ({ id: 'x', core_set: CURSET });
global.render = () => {};
let rendered = 0;
global.renderCountry = () => { rendered++; };
global.renderDetail = () => { rendered++; };
global.coTopC = () => null;

/* patch.js는 상단에서 ST/render/regionObj 존재를 확인하고 IIFE로 즉시 실행된다 */
eval(fs.readFileSync(path.join(ROOT, 'ui', 'patch.js'), 'utf8'));
const M = window.__PHX_COUNTRY_LAZY__;
if (!M) fail('모듈 8 훅(__PHX_COUNTRY_LAZY__)이 없다 — 모듈이 로드 중 죽었다');

/* 모듈 8과 무관한 초기 주입(현재 panoptes/research_desk.js 1건)은 기준선으로 걷어낸다 */
const baseline = pending.splice(0).map(el => el.src);

/* 주입된 스크립트를 실제로 실행해 onload를 돌린다 */
function flush(){
  while (pending.length){
    const el = pending.shift();
    const file = path.join(SHARDS, path.basename(el.src));
    log.push(el.src);
    if (fs.existsSync(file)) eval(fs.readFileSync(file, 'utf8'));
    el.onload();                          /* onload=onerror=같은 함수 */
  }
}

/* ---- 1. cdir 모드: 현재 세트 하나만 받는다 ---- */
let done = 0;
M.loadCountry(() => done++);
assert.strictEqual(log.length, 0, '아직 flush 전');
assert.strictEqual(pending.length, 1, '스크립트 1개가 주입돼야 한다');
flush();
assert.strictEqual(done, 1, '콜백이 불려야 한다');
assert.strictEqual(log[0], 'data_jp_country/probe_core.js', '요청 URL: ' + log[0]);
assert.ok(P.country && P.country.probe_core, 'P.country.probe_core 가 병합돼야 한다');
assert.ok(!P.country.mem_broad, '요청하지 않은 세트는 오지 않아야 한다');
assert.ok(M.haveCountry(), 'haveCountry()가 true여야 한다');
assert.ok(!M.pending(), '더 받을 게 없어야 한다');

/* ---- 2. 같은 세트 재요청은 네트워크를 타지 않는다 ---- */
const before = log.length;
M.loadCountry(() => done++);
assert.strictEqual(pending.length, 0, '재요청에서 스크립트가 또 주입되면 안 된다');
assert.strictEqual(log.length, before);
assert.strictEqual(done, 2);

/* ---- 3. 세트를 바꾸면 그 세트만 새로 받는다 ---- */
CURSET = 'mem_broad';
assert.ok(!M.haveCountry(), '새 세트는 아직 없어야 한다');
M.loadCountry(() => done++); flush();
assert.strictEqual(log[log.length - 1], 'data_jp_country/mem_broad.js');
assert.ok(P.country.mem_broad, 'mem_broad 병합');
assert.ok(P.country.probe_core, '이전 세트는 LRU 안에 남아 있어야 한다');

/* ---- 4. csets에 없는 세트는 요청조차 하지 않는다 ---- */
CURSET = 'nope_core';
const n4 = log.length;
M.loadCountry(() => done++);
assert.strictEqual(pending.length, 0, 'csets에 없는 세트를 요청하면 안 된다');
assert.strictEqual(log.length, n4);

/* ---- 5. 404는 한 번만 시도한다 ---- */
REGION = { cdir: 'data_jp_country/', csets: ['probe_core', 'mem_broad', 'ghost_core'] };
CURSET = 'ghost_core';
M.loadCountry(() => done++); flush();     /* 파일이 없으니 onerror 경로 */
const n5 = log.length;
assert.ok(!M.pending(), '실패한 세트는 pending()이 false여야 한다');
M.loadCountry(() => done++);
assert.strictEqual(pending.length, 0, '404 세트를 렌더마다 재요청하면 안 된다');
assert.strictEqual(log.length, n5);

/* ---- 6. LRU: MAXSETS를 넘으면 오래된 세트를 놓아준다 ---- */
for (let i = 0; i < 20; i++){
  const k = 'syn_' + i;
  P.country[k] = { order: [], loc: {} };   /* 샤드가 준 것처럼 직접 넣고 */
  window.PSHC.JP.country[k] = P.country[k];
  M.mergeSet('JP', k);                     /* touch → trimSets */
}
const lru = M.state().lru;
assert.ok(lru.length <= 12, 'LRU 상한 12를 넘었다: ' + lru.length);
assert.ok(!P.country.probe_core, '가장 오래된 세트는 축출됐어야 한다');
assert.ok(P.country.syn_19, '가장 최근 세트는 남아 있어야 한다');

/* ---- 7. cfile 폴백(상태 c)이 살아 있다 ---- */
REGION = { cfile: 'data_kr_country.js' };
ST.region = 'KR'; CURSET = 'kr_core';
M.loadCountry(() => done++);
assert.strictEqual(pending.length, 1, 'cfile 경로가 스크립트를 주입해야 한다');
assert.strictEqual(pending[0].src, 'data_kr_country.js');
pending.length = 0;

/* ---- 8. 빌더 미적용(상태 a): 아무것도 요청하지 않는다 ---- */
REGION = {}; ST.region = 'TW'; CURSET = 'tw_core';
let cb8 = 0; M.loadCountry(() => cb8++);
assert.strictEqual(cb8, 1, '즉시 콜백해야 한다');
assert.strictEqual(pending.length, 0, '요청이 없어야 한다');

console.log('OK  기준선 ' + JSON.stringify(baseline) + '\n    모듈8 요청 ' + log.length + '건: ' + log.join(', '));
