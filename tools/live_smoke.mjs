// 배포 후 라이브 스모크 — 배포된 Pages를 실브라우저로 열어 전 탭·전 리전을 순회한다.
// 잡는 것: 템플릿이 객체를 보간한 [object Object] (빌드 산출물에는 안 남는 런타임 전용 결함),
//          탭 렌더 중 예외(pageerror), 렌더 폴백으로 dash에 튕기는 탭(ST.tab 불일치).
// 탭·리전 목록은 페이지 전역(tabIds()·REGIONS)에서 읽으므로 탭이 늘어도 수정할 필요 없다.
// 사용: node tools/live_smoke.mjs [BASE_URL]   (기본: 라이브 Pages)
import { chromium } from 'playwright';
import fs from 'node:fs';

const BASE = (process.argv[2] || process.env.SMOKE_URL || 'https://smu05118-art.github.io/phalanx/').replace(/[?#].*$/, '');
const CB = 'smoke' + Date.now();
const SETTLE_MS = 1500;
const NAV_TIMEOUT = 45000;
const OUT = process.env.SMOKE_OUT || 'smoke-out';
fs.mkdirSync(OUT, { recursive: true });

// 같은 오리진 하위 리소스(data_*.js·ui/*)까지 캐시 무력화 — Pages CDN max-age=600 동안 구버전을 보는 것 방지
const origin = new URL(BASE).origin;
async function bust(route) {
  const req = route.request();
  const u = new URL(req.url());
  if (req.method() === 'GET' && u.origin === origin && !u.searchParams.has('cb')) {
    u.searchParams.set('cb', CB);
    return route.continue({ url: u.toString() });
  }
  return route.continue();
}

const browser = await chromium.launch();
const results = [];

async function check(label, hash, expectTab) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  await page.route('**/*', bust);
  const errors = [], warns = [];
  page.on('pageerror', e => errors.push(String(e && e.message || e).slice(0, 300)));
  page.on('console', m => {
    if (m.type() !== 'error') return;
    const t = m.text().slice(0, 300);
    // 리소스 404 등 네트워크 잡음은 경고로만, 스크립트 예외는 실패로
    (/TypeError|ReferenceError|SyntaxError|RangeError|is not (a function|defined)/.test(t) ? errors : warns).push(t);
  });
  let r = { label, hash, ok: false };
  try {
    await page.goto(`${BASE}?cb=${CB}#${hash}`, { waitUntil: 'load', timeout: NAV_TIMEOUT });
    await page.waitForLoadState('networkidle', { timeout: NAV_TIMEOUT }).catch(() => warns.push('networkidle 타임아웃'));
    await page.waitForTimeout(SETTLE_MS);
    const s = await page.evaluate(() => {
      const txt = document.body.innerText || '';
      const html = (document.getElementById('main') || document.body).innerHTML;
      const ctxOf = (re) => { const m = re.exec(txt); return m ? txt.slice(Math.max(0, m.index - 60), m.index + 40).replace(/\s+/g, ' ') : null; };
      return {
        tab: typeof ST !== 'undefined' ? ST.tab : null,
        region: typeof ST !== 'undefined' ? ST.region : null,
        obj: (txt.match(/\[object Object\]/g) || []).length + (html.match(/\[object Object\]/g) || []).length,
        objCtx: ctxOf(/\[object Object\]/),
        mainLen: html.length,
      };
    });
    r = { ...r, ...s, errors, warns };
    const fails = [];
    if (s.obj) fails.push(`[object Object] ${s.obj}건 — "${s.objCtx}"`);
    if (expectTab && s.tab !== expectTab) fails.push(`탭 이탈: ${expectTab} → ${s.tab}`);
    if (errors.length) fails.push(`스크립트 오류 ${errors.length}건: ${errors[0]}`);
    if (s.mainLen < 200) fails.push(`본문 비어 있음 (${s.mainLen}자)`);
    r.fails = fails;
    r.ok = fails.length === 0;
  } catch (e) {
    r.fails = [`로드 실패: ${String(e.message || e).slice(0, 200)}`];
    r.errors = errors; r.warns = warns;
  }
  if (!r.ok) await page.screenshot({ path: `${OUT}/${label.replace(/[^\w-]/g, '_')}.png`, fullPage: false }).catch(() => {});
  await ctx.close();
  results.push(r);
  console.log(`${r.ok ? 'OK  ' : 'FAIL'} ${label}${r.ok ? '' : '  ' + r.fails.join(' | ')}`);
}

// 1) 목록 수집
const boot = await browser.newPage();
await boot.route('**/*', bust);
await boot.goto(`${BASE}?cb=${CB}`, { waitUntil: 'load', timeout: NAV_TIMEOUT });
await boot.waitForTimeout(SETTLE_MS);
const { tabs, regions } = await boot.evaluate(() => ({
  tabs: typeof tabIds === 'function' ? tabIds() : [...document.querySelectorAll('[data-tab]')].map(b => b.dataset.tab),
  regions: typeof REGIONS !== 'undefined' ? REGIONS.map(r => r.id) : [],
}));
await boot.close();
if (tabs.length < 10 || regions.length < 5) {
  console.error(`목록 수집 이상 — tabs ${tabs.length}, regions ${regions.length}. 페이지 구조가 바뀌었는지 확인`);
  process.exit(2);
}
console.log(`탭 ${tabs.length}개 · 리전 ${regions.length}개 순회 (${BASE})`);

// 2) 전 탭 (기본 리전) 2) 전 리전 dash
for (const t of tabs) await check(`tab:${t}`, `tab=${t}`, t);
for (const g of regions) await check(`region:${g}`, `r=${g}`, 'dash');
await browser.close();

// 3) 보고
const bad = results.filter(r => !r.ok);
const lines = [
  `## 라이브 스모크 — ${bad.length ? `❌ ${bad.length}건 실패` : '✅ 전부 통과'}`,
  '',
  `대상 ${BASE} · 탭 ${tabs.length} · 리전 ${regions.length} · 총 ${results.length}회 로드`,
  '',
];
if (bad.length) {
  lines.push('| 대상 | 실패 사유 |', '|---|---|');
  for (const r of bad) lines.push(`| \`${r.label}\` | ${r.fails.join('<br>').replace(/\|/g, '\\|')} |`);
  lines.push('', '스크린샷은 아티팩트 `live-smoke`에 있습니다.');
}
const warnN = results.reduce((n, r) => n + (r.warns ? r.warns.length : 0), 0);
if (warnN) lines.push('', `경고(실패 아님) ${warnN}건 — 리소스 404·networkidle 타임아웃 등. 상세는 results.json`);
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 2));
fs.writeFileSync(`${OUT}/summary.md`, lines.join('\n') + '\n');
if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, lines.join('\n') + '\n');
process.exit(bad.length ? 1 : 0);
