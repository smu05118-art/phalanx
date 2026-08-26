/* llm_charts.js — 파놉테스 🤖 LLM 탭 렌더러 (OpenRouter 랭킹, 의존성 0, 순수 SVG)
 * 전역: window.renderLLM(el, data)   data = data/llm_rankings.json 전체 객체
 * 로드 시 부작용 없음(함수 정의만). 외부 라이브러리·fetch 사용 안 함.
 * 데이터 출처: OpenRouter (openrouter.ai/rankings) · CC BY 4.0
 */
(function () {
  'use strict';

  var DIM = '#8a93a3', ACC = '#2bc0d4', UP = '#59d0a8', DOWN = '#ff5e6c';
  var MONO = 'var(--mono,ui-monospace,SFMono-Regular,Menlo,monospace)';
  var PAL = ['#4ea1ff', '#59d0a8', '#f6c85f', '#e07a5f', '#b892ff', '#2bc0d4', '#ff8a3d', '#7ec8e3', '#ff6b9d', '#9ccc65', '#8a93a3'];
  // 주요 랩 고정색 (스택차트·점유율에서 일관되게)
  var AUTHOR_COLOR = {
    openai: '#10c99a', anthropic: '#d97757', google: '#4e8cff', 'x-ai': '#e6edf3',
    deepseek: '#536dfe', qwen: '#b892ff', alibaba: '#b892ff', 'meta-llama': '#0a84ff', meta: '#0a84ff',
    xiaomi: '#ff6900', tencent: '#3d7eff', 'z-ai': '#00c9a7', mistralai: '#fa500f',
    nvidia: '#76b900', moonshotai: '#22d3ee', minimax: '#f43f6c', stepfun: '#f6c85f',
    stealth: '#c9a0ff', openrouter: '#2bc0d4', microsoft: '#7fbadc', amazon: '#ff9900',
    nousresearch: '#8fd460', inclusionai: '#5cc8ff', bytedance: '#3c8cff', baidu: '#2932e1',
    others: '#5b6472', Others: '#5b6472'
  };

  var CSS = [
    '.or-wrap{display:flex;flex-direction:column;gap:18px;max-width:1280px}',
    /* ── 히어로 ── */
    '.or-hero{position:relative;overflow:hidden;background:linear-gradient(135deg,rgba(43,192,212,.13),rgba(78,161,255,.07) 45%,rgba(184,146,255,.10));border:1px solid rgba(43,192,212,.3);border-radius:16px;padding:20px 24px}',
    '.or-hero:before{content:"";position:absolute;inset:-40%;background:radial-gradient(600px 220px at 18% 0%,rgba(43,192,212,.16),transparent 60%);pointer-events:none}',
    '.or-hero h2{font-size:20px;font-weight:850;letter-spacing:-.02em;display:flex;align-items:center;gap:10px;flex-wrap:wrap}',
    '.or-hero .live{font-size:9.5px;font-weight:800;letter-spacing:.1em;color:#59d0a8;border:1px solid rgba(89,208,168,.4);border-radius:999px;padding:2px 9px;display:inline-flex;align-items:center;gap:5px}',
    '.or-hero .live i{width:6px;height:6px;border-radius:50%;background:#59d0a8;box-shadow:0 0 8px #59d0a8;animation:orPulse 1.6s infinite}',
    '@keyframes orPulse{0%,100%{opacity:1}50%{opacity:.35}}',
    '.or-hero .sub{font-size:12px;color:' + DIM + ';margin-top:5px;line-height:1.6}',
    '.or-hero .sub b{color:var(--ink,#e6edf3)}',
    /* ── 섹션 내비 ── */
    '.or-nav{position:sticky;top:0;z-index:6;display:flex;gap:6px;flex-wrap:wrap;background:rgba(10,14,20,.88);backdrop-filter:blur(8px);padding:9px 2px;border-bottom:1px solid var(--line,#1f2937);margin:0 -2px}',
    '.or-nav a{font-size:11.5px;font-weight:650;color:' + DIM + ';text-decoration:none;padding:4px 11px;border:1px solid var(--line,#1f2937);border-radius:999px;transition:.12s;white-space:nowrap}',
    '.or-nav a:hover{color:' + ACC + ';border-color:rgba(43,192,212,.5)}',
    /* ── KPI ── */
    '.or-kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}',
    '@media(max-width:1150px){.or-kpis{grid-template-columns:repeat(3,1fr)}}',
    '@media(max-width:640px){.or-kpis{grid-template-columns:repeat(2,1fr)}}',
    '.or-kpi{background:var(--panel,#111721);border:1px solid var(--line,#1f2937);border-radius:13px;padding:12px 14px;min-width:0;position:relative;overflow:hidden}',
    '.or-kpi:after{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--kc,' + ACC + ');opacity:.85}',
    '.or-kpi .lab{font-size:10.5px;color:' + DIM + ';font-weight:650;letter-spacing:.02em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.or-kpi .val{font-family:' + MONO + ';font-size:19px;font-weight:800;margin-top:4px;letter-spacing:-.02em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.or-kpi .sub{font-size:10.5px;color:' + DIM + ';margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    /* ── 카드·섹션 ── */
    '.or-sec{scroll-margin-top:64px}',
    '.or-sech{display:flex;align-items:baseline;gap:10px;margin-bottom:10px;flex-wrap:wrap}',
    '.or-sech h3{font-size:14.5px;font-weight:800;margin:0;letter-spacing:-.01em}',
    '.or-sech .hint2{font-size:11px;color:' + DIM + '}',
    '.or-sech .sp{flex:1}',
    '.or-card{background:var(--panel,#111721);border:1px solid var(--line,#1f2937);border-radius:14px;padding:15px 17px;min-width:0}',
    '.or-grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}',
    '@media(max-width:980px){.or-grid2{grid-template-columns:1fr}}',
    /* ── 칩 ── */
    '.or-chips{display:flex;gap:6px;flex-wrap:wrap}',
    '.or-chip{font:inherit;font-size:11.5px;line-height:1.5;padding:3px 11px;border:1px solid var(--line,#1f2937);border-radius:999px;background:transparent;color:' + DIM + ';cursor:pointer;transition:.12s}',
    '.or-chip:hover{border-color:rgba(43,192,212,.5);color:' + ACC + '}',
    '.or-chip.on{background:rgba(43,192,212,.14);color:' + ACC + ';border-color:rgba(43,192,212,.45);font-weight:700}',
    /* ── 리더보드 표 ── */
    '.or-tbl{width:100%;border-collapse:collapse;font-size:12.5px}',
    '.or-tbl th{font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:' + DIM + ';font-weight:700;text-align:right;padding:7px 10px;border-bottom:1px solid var(--line,#1f2937);white-space:nowrap}',
    '.or-tbl th.l,.or-tbl td.l{text-align:left}',
    '.or-tbl td{padding:7px 10px;border-bottom:1px solid rgba(31,41,55,.55);text-align:right;font-family:' + MONO + ';font-size:12px;white-space:nowrap}',
    '.or-tbl tr:hover td{background:rgba(43,192,212,.05)}',
    '.or-tbl td.rk{color:' + DIM + ';font-size:11px;width:30px}',
    '.or-tbl td.mdl{font-family:inherit;max-width:250px;overflow:hidden;text-overflow:ellipsis}',
    '.or-tbl .mn{font-weight:700;font-size:12.5px}',
    '.or-tbl .au{font-size:10.5px;color:' + DIM + ';margin-left:6px}',
    '.or-adot{display:inline-block;width:8px;height:8px;border-radius:2.5px;margin-right:7px;vertical-align:0}',
    '.or-bar{position:relative;height:14px;background:rgba(31,41,55,.5);border-radius:4px;overflow:hidden;min-width:110px}',
    '.or-bar i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;background:linear-gradient(90deg,rgba(43,192,212,.9),rgba(78,161,255,.75))}',
    '.or-chg{font-weight:700}',
    '.or-new{font-size:9.5px;font-weight:800;color:#f6c85f;border:1px solid rgba(246,200,95,.45);padding:1px 6px;border-radius:999px}',
    '.or-more{margin-top:10px;text-align:center}',
    /* ── 플롯 공통 ── */
    '.or-plot{position:relative}',
    '.or-plot svg{display:block;width:100%;height:auto;overflow:visible}',
    '.or-tip{position:absolute;pointer-events:none;opacity:0;background:rgba(8,11,17,.94);border:1px solid var(--line,#1f2937);border-radius:8px;padding:6px 9px;font-family:' + MONO + ';font-size:10.5px;line-height:1.7;color:#e6edf3;white-space:nowrap;z-index:4;transition:opacity .1s;transform:translate(-50%,0)}',
    '.or-plot.on .or-tip{opacity:1}',
    '.or-lgd{display:flex;gap:5px 12px;flex-wrap:wrap;margin-top:9px}',
    '.or-lgd span{display:inline-flex;align-items:center;gap:5px;font-size:10.5px;color:' + DIM + '}',
    '.or-lgd i{width:9px;height:9px;border-radius:3px;flex:0 0 auto}',
    /* ── 벤치마크 ── */
    '.or-brow{display:flex;align-items:center;gap:9px;margin:5px 0}',
    '.or-brow .nm{flex:0 0 218px;font-size:12px;font-weight:650;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.or-brow .tr{flex:1;height:17px;background:rgba(31,41,55,.45);border-radius:5px;overflow:hidden;position:relative}',
    '.or-brow .tr i{position:absolute;left:0;top:0;bottom:0;border-radius:5px}',
    '.or-brow .sc{flex:0 0 44px;font-family:' + MONO + ';font-size:12px;font-weight:800}',
    '@media(max-width:640px){.or-brow .nm{flex-basis:130px;font-size:11px}}',
    /* ── 태스크 ── */
    '.or-mac{display:flex;height:26px;border-radius:8px;overflow:hidden;margin-bottom:12px;border:1px solid var(--line,#1f2937)}',
    '.or-mac div{display:flex;align-items:center;justify-content:center;font-size:10.5px;font-weight:750;color:#0a0e14;min-width:0;overflow:hidden;white-space:nowrap}',
    '.or-tasks{display:grid;grid-template-columns:repeat(auto-fill,minmax(255px,1fr));gap:10px}',
    '.or-task{background:var(--panel2,#0d131c);border:1px solid var(--line,#1f2937);border-radius:11px;padding:11px 13px;min-width:0}',
    '.or-task .tt{font-size:12px;font-weight:750;display:flex;justify-content:space-between;gap:6px;align-items:baseline}',
    '.or-task .tt b{font-family:' + MONO + ';color:' + ACC + '}',
    '.or-task .tm{font-size:11px;color:' + DIM + ';margin-top:6px;line-height:1.8}',
    '.or-task .tm b{color:var(--ink,#e6edf3);font-weight:650}',
    '.or-task .tm i{font-style:normal;font-family:' + MONO + ';font-size:10px}',
    /* ── 앱 ── */
    '.or-apps{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px}',
    '.or-app{display:flex;gap:11px;background:var(--panel2,#0d131c);border:1px solid var(--line,#1f2937);border-radius:11px;padding:11px 13px;min-width:0;transition:.12s}',
    '.or-app:hover{border-color:rgba(43,192,212,.4)}',
    '.or-app .rk2{font-family:' + MONO + ';font-size:15px;font-weight:800;color:' + DIM + ';flex:0 0 26px;text-align:center}',
    '.or-app .rk2.top{color:#f6c85f}',
    '.or-app .bd{min-width:0;flex:1}',
    '.or-app .an{font-size:12.5px;font-weight:750;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.or-app .an a{color:inherit;text-decoration:none}',
    '.or-app .an a:hover{color:' + ACC + '}',
    '.or-app .ad{font-size:10.5px;color:' + DIM + ';margin:3px 0 5px;line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}',
    '.or-app .am{font-family:' + MONO + ';font-size:10.5px;color:' + DIM + '}',
    '.or-app .am b{color:' + ACC + '}',
    /* ── 세션비용 표 ── */
    '.or-foot{font-size:10.5px;color:' + DIM + ';line-height:1.7;border-top:1px solid var(--line,#1f2937);padding-top:12px}',
    '.or-foot a{color:' + ACC + ';text-decoration:none}',
    '.or-empty{font-size:11.5px;color:' + DIM + ';padding:12px 0}'
  ].join('');

  function ensureCss(doc) {
    if (!doc || doc.getElementById('llmChartsCss')) return;
    var s = doc.createElement('style');
    s.id = 'llmChartsCss';
    s.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(s);
  }

  /* ================= helpers ================= */
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function fmtTok(v) {
    if (v == null || isNaN(v)) return '—';
    var a = Math.abs(v);
    // 단위 경계는 반올림 후 판정 (999.97B → '1000.0B'가 아니라 '1.00T')
    if (a >= 999.995e9) return (v / 1e12).toFixed(a >= 9.99995e12 ? 1 : 2) + 'T';
    if (a >= 999.995e6) return (v / 1e9).toFixed(a >= 9.99995e9 ? 1 : 2) + 'B';
    if (a >= 999.95e3) return (v / 1e6).toFixed(1) + 'M';
    if (a >= 999.95) return (v / 1e3).toFixed(1) + 'K';
    return String(Math.round(v));
  }
  function fmtPct(v, dp) { return v == null || isNaN(v) ? '—' : (v * 100).toFixed(dp == null ? 1 : dp) + '%'; }
  function fmtChg(v) {
    if (v == null || isNaN(v)) return '<span class="or-new">NEW</span>';
    var p = v * 100, c = p >= 0 ? UP : DOWN, s = p >= 0 ? '▲' : '▼';
    return '<span class="or-chg" style="color:' + c + '">' + s + Math.abs(p).toFixed(Math.abs(p) >= 100 ? 0 : 1) + '%</span>';
  }
  function authorOf(slug) {
    var m = (window.__orData && window.__orData.models || {})[slug];
    if (m && m.a) return m.a;
    return String(slug || '').split('/')[0];
  }
  function colorOfAuthor(a) { return AUTHOR_COLOR[a] || PAL[hashN(a) % PAL.length]; }
  function hashN(s) { var h = 0; s = String(s || ''); for (var i = 0; i < s.length; i++) { h = (h * 31 + s.charCodeAt(i)) >>> 0; } return h; }
  function nameOf(slug) {
    var D = window.__orData || {};
    var s = String(slug || ''), variant = '';
    var ci = s.indexOf(':');
    if (ci > 0) { variant = s.slice(ci + 1); s = s.slice(0, ci); }
    var m = (D.models || {})[slug] || (D.models || {})[s];
    var n;
    if (m && m.n) n = m.n;
    else {
      n = s.split('/').pop().replace(/-20\d{6}$/, '').replace(/-/g, ' ');
      n = n.replace(/\b[a-z]/g, function (c) { return c.toUpperCase(); });
    }
    if (variant && n.toLowerCase().indexOf('(' + variant.toLowerCase()) < 0) n += ' (' + variant + ')';
    return n;
  }
  function authorName(a) {
    var D = window.__orData || {}, M = D.models || {};
    for (var k in M) { if (M[k].a === a && M[k].ad) return M[k].ad; }
    return a === 'others' || a === 'Others' ? '기타' : a;
  }
  function shade(hex, f) { // f>0 밝게, f<0 어둡게
    var n = parseInt(hex.slice(1), 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255;
    var t = f > 0 ? 255 : 0, p = Math.abs(f);
    r = Math.round(r + (t - r) * p); g = Math.round(g + (t - g) * p); b = Math.round(b + (t - b) * p);
    return '#' + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
  }
  function seriesColor(key) {
    if (key === 'Others' || key === 'others') return AUTHOR_COLOR.others;
    var a = authorOf(String(key).replace(/:free$/, ''));
    var base = AUTHOR_COLOR[a];
    if (!base) return PAL[hashN(key) % PAL.length];
    // 같은 제작사 모델이 스택에서 구분되게 slug 해시로 셰이드 3단 분리
    var v = hashN(key) % 3;
    return v === 1 ? shade(base, 0.22) : v === 2 ? shade(base, -0.2) : base;
  }
  function sum(arr) { var s = 0; for (var i = 0; i < arr.length; i++) s += (arr[i] || 0); return s; }
  function last(arr) { return arr && arr.length ? arr[arr.length - 1] : null; }

  /* ============ 스택 영역차트 (재사용) ============ */
  // pack = {dates, series}, opts = {h, pct(100%모드), topN, id, unitFmt}
  function stackedArea(pack, opts) {
    opts = opts || {};
    var W = 900, H = opts.h || 240, PL2 = 8, PR2 = 52, PT2 = 12, PB2 = 22;
    var dates = pack.dates || [], keys = Object.keys(pack.series || {});
    if (!dates.length || !keys.length) return '<div class="or-empty">데이터 없음</div>';
    // 사용량이 지수 성장하므로 절대량 랭킹은 최근만 남는다 —
    // "그 시점 주간 점유율 피크" 기준으로 뽑아 과거 리더(grok-code-fast 등)도 살린다
    var topN = opts.topN || 10;
    var n0 = dates.length;
    var tots0 = [];
    for (var ti = 0; ti < n0; ti++) {
      var s0 = 0;
      for (var kk = 0; kk < keys.length; kk++) s0 += (pack.series[keys[kk]][ti] || 0);
      tots0.push(s0 || 1);
    }
    var byRecent = keys.map(function (k) {
      var t4 = pack.series[k].slice(-4);
      return [k, sum(t4) / (t4.length || 1)];
    }).sort(function (a, b) { return b[1] - a[1]; });
    var byPeak = keys.map(function (k) {
      var mx = 0;
      for (var i2 = 0; i2 < n0; i2++) { var sh = (pack.series[k][i2] || 0) / tots0[i2]; if (sh > mx) mx = sh; }
      return [k, mx];
    }).sort(function (a, b) { return b[1] - a[1]; });
    var main = [];
    byRecent.slice(0, topN).forEach(function (t) { if (main.indexOf(t[0]) < 0) main.push(t[0]); });
    byPeak.slice(0, topN).forEach(function (t) { if (main.length < topN + 4 && main.indexOf(t[0]) < 0) main.push(t[0]); });
    var restKeys = keys.filter(function (k) { return main.indexOf(k) < 0; });
    var oi = main.indexOf('Others'); if (oi < 0) oi = main.indexOf('others');
    if (restKeys.length) {
      var restSum = dates.map(function (_, i) { return restKeys.reduce(function (s, k) { return s + (pack.series[k][i] || 0); }, 0); });
      if (oi >= 0) { var ok = main[oi]; pack = { dates: dates, series: shallowPick(pack.series, main) }; pack.series[ok] = pack.series[ok].map(function (v, i) { return v + restSum[i]; }); }
      else { pack = { dates: dates, series: shallowPick(pack.series, main) }; pack.series.Others = restSum; main = main.concat(['Others']); }
    } else pack = { dates: dates, series: shallowPick(pack.series, main) };
    // Others는 항상 마지막(맨 아래 대신 맨 위)으로
    main = main.filter(function (k) { return k !== 'Others' && k !== 'others'; }).concat(main.filter(function (k) { return k === 'Others' || k === 'others'; }));

    var n = dates.length;
    var stackTot = dates.map(function (_, i) { return main.reduce(function (s, k) { return s + (pack.series[k][i] || 0); }, 0); });
    var maxT = Math.max.apply(null, stackTot) || 1;
    var x = function (i) { return PL2 + (W - PL2 - PR2) * (n === 1 ? 0.5 : i / (n - 1)); };
    var y = function (v) { return PT2 + (H - PT2 - PB2) * (1 - v / (opts.pct ? 1 : maxT)); };

    var polys = '', legend = '', cum = dates.map(function () { return 0; });
    for (var ki = main.length - 1; ki >= 0; ki--) { /* 아래부터 쌓기: 역순으로 그리면 위 계열이 위에 오도록 아래 로직 유지 */ }
    // 누적: main 순서대로 아래→위
    var layers = [];
    for (var k2 = 0; k2 < main.length; k2++) {
      var key = main[k2], vals = pack.series[key];
      var base = cum.slice();
      cum = cum.map(function (c, i) { return c + (vals[i] || 0); });
      layers.push({ key: key, lo: base, hi: cum.slice() });
    }
    layers.forEach(function (L, li) {
      var col = seriesColor(L.key, li);
      var top = '', bot = '';
      for (var i = 0; i < n; i++) {
        var hv = opts.pct ? (stackTot[i] ? L.hi[i] / stackTot[i] : 0) : L.hi[i];
        top += (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(hv).toFixed(1) + ' ';
      }
      for (var j = n - 1; j >= 0; j--) {
        var lv = opts.pct ? (stackTot[j] ? L.lo[j] / stackTot[j] : 0) : L.lo[j];
        bot += 'L' + x(j).toFixed(1) + ' ' + y(lv).toFixed(1) + ' ';
      }
      polys += '<path d="' + top + bot + 'Z" fill="' + col + '" fill-opacity="0.72" stroke="' + col + '" stroke-opacity="0.9" stroke-width="0.7"/>';
    });
    main.forEach(function (k3, i3) {
      var col = seriesColor(k3, i3);
      var label = (k3 === 'Others' || k3 === 'others') ? '기타' : (opts.labelFn ? opts.labelFn(k3) : nameOf(k3));
      legend += '<span><i style="background:' + col + '"></i>' + esc(label) + '</span>';
    });
    // y축 눈금
    var ticks = '';
    for (var t = 1; t <= 3; t++) {
      var tv = (opts.pct ? t / 3 : maxT * t / 3);
      var ty = y(opts.pct ? t / 3 : tv);
      ticks += '<line x1="' + PL2 + '" y1="' + ty.toFixed(1) + '" x2="' + (W - PR2) + '" y2="' + ty.toFixed(1) + '" stroke="#1f2937" stroke-width="0.6" stroke-dasharray="3 4"/>' +
        '<text x="' + (W - PR2 + 5) + '" y="' + (ty + 3.5).toFixed(1) + '" font-size="9.5" fill="' + DIM + '" font-family="ui-monospace,Menlo,monospace">' + (opts.pct ? Math.round(t / 3 * 100) + '%' : fmtTok(tv)) + '</text>';
    }
    // x축 라벨 (5개)
    var xl = '';
    for (var xi = 0; xi < 5; xi++) {
      var idx = Math.round((n - 1) * xi / 4);
      var anchor = xi === 0 ? 'start' : (xi === 4 ? 'end' : 'middle');
      xl += '<text x="' + x(idx).toFixed(1) + '" y="' + (H - 6) + '" font-size="9.5" fill="' + DIM + '" text-anchor="' + anchor + '" font-family="ui-monospace,Menlo,monospace">' + esc(String(dates[idx]).slice(2)) + '</text>';
    }
    var gid = opts.id || ('sa' + hashN(main.join(',')) % 100000);
    var html = '<div class="or-plot" data-sa="' + gid + '"><svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">' + ticks + polys +
      '<line class="or-guide" x1="0" y1="' + PT2 + '" x2="0" y2="' + (H - PB2) + '" stroke="#e6edf3" stroke-opacity="0" stroke-width="1"/>' + xl + '</svg>' +
      '<div class="or-tip"></div></div><div class="or-lgd">' + legend + '</div>';
    // 호버 데이터 저장
    stackedArea._store[gid] = { dates: dates, main: main, series: pack.series, tot: stackTot, pct: !!opts.pct, W: W, PL: PL2, PR: PR2, labelFn: opts.labelFn };
    return html;
  }
  stackedArea._store = {};

  function bindStackHover(root) {
    root.querySelectorAll('.or-plot[data-sa]').forEach(function (plot) {
      var st = stackedArea._store[plot.dataset.sa]; if (!st) return;
      var svg = plot.querySelector('svg'), tip = plot.querySelector('.or-tip'), guide = plot.querySelector('.or-guide');
      plot.addEventListener('mousemove', function (ev) {
        var r = svg.getBoundingClientRect();
        var fx = (ev.clientX - r.left) / r.width * st.W;
        var frac = Math.min(1, Math.max(0, (fx - st.PL) / (st.W - st.PL - st.PR)));
        var i = Math.round(frac * (st.dates.length - 1));
        var rows = st.main.map(function (k) { return [k, st.series[k][i] || 0]; }).sort(function (a, b) { return b[1] - a[1]; }).slice(0, 6);
        var tot = st.tot[i] || 1;
        tip.innerHTML = '<b>' + esc(st.dates[i]) + '</b> · 합계 ' + fmtTok(tot) + '<br>' + rows.map(function (rw) {
          var lb = (rw[0] === 'Others' || rw[0] === 'others') ? '기타' : (st.labelFn ? st.labelFn(rw[0]) : nameOf(rw[0]));
          return '<span style="color:' + seriesColor(rw[0], 0) + '">●</span> ' + esc(lb) + ' ' + (st.pct ? fmtPct(rw[1] / tot) : fmtTok(rw[1]));
        }).join('<br>');
        var px = (st.PL + frac * (st.W - st.PL - st.PR)) / st.W * r.width;
        tip.style.left = Math.min(r.width - 90, Math.max(90, px)) + 'px';
        tip.style.top = '6px';
        guide.setAttribute('x1', fx.toFixed(1)); guide.setAttribute('x2', fx.toFixed(1));
        guide.setAttribute('stroke-opacity', '0.35');
        plot.classList.add('on');
      });
      plot.addEventListener('mouseleave', function () { plot.classList.remove('on'); guide.setAttribute('stroke-opacity', '0'); });
    });
  }

  /* ================= 메인 렌더 ================= */
  window.renderLLM = function (el, data) {
    ensureCss(el.ownerDocument);
    // 스키마 드리프트·부분 수집에도 탭 전체가 죽지 않게 최상위 키 기본값 보정
    data = data || {};
    var EMPTY_S = function () { return { dates: [], series: {} }; };
    data.models = data.models || {};
    data.leaderboard = data.leaderboard || {};
    ['day', 'week', 'month', 'trending'].forEach(function (k) { data.leaderboard[k] = data.leaderboard[k] || []; });
    data.top_chart = data.top_chart || EMPTY_S();
    data.market_share = data.market_share || EMPTY_S();
    data.tools_series = data.tools_series || EMPTY_S();
    data.images_series = data.images_series || EMPTY_S();
    data.languages = data.languages || {};
    data.programming = data.programming || {};
    data.context = data.context || {};
    data.benchmarks = data.benchmarks || {};
    ['intelligence', 'coding', 'agentic'].forEach(function (k) { data.benchmarks[k] = data.benchmarks[k] || []; });
    data.benchmarks.price_in = data.benchmarks.price_in || {};
    data.tasks = data.tasks || {};
    ['spend', 'tokens'].forEach(function (k) { data.tasks[k] = data.tasks[k] || { macro: [], tasks: [] }; });
    data.session_cost = data.session_cost || {};
    data.session_cost.harnesses = data.session_cost.harnesses || [];
    data.apps = data.apps || {};
    ['day', 'week', 'month'].forEach(function (k) { data.apps[k] = data.apps[k] || []; });
    data.performance = data.performance || [];
    window.__orData = data;
    var ST = { view: 'week', bench: 'intelligence', taskSide: 'spend', harness: guessHarness(data), lang: 'English', prog: 'Python', ctx: '10K', apps: 'week', share: 'pct', lbLimit: 20 };

    function guessHarness(d) {
      var hs = ((d.session_cost || {}).harnesses || []);
      var cc = hs.find(function (h) { return /claude code/i.test(h.label); });
      return cc ? cc.label : (hs[0] || {}).label;
    }

    el.innerHTML = '<div class="or-wrap">' + hero() + nav() + kpis() +
      sec('lb', '🏆 리더보드', '토큰 처리량 순위 · 변화율 = 전주 대비', chipRow('view', [['day', '오늘'], ['week', '주간'], ['month', '월간'], ['trending', '트렌딩']], ST.view)) +
      sec('top', '📈 Top Models — 주간 사용량', '52주 · 상위 10개 모델 + 기타 · 토큰 기준') +
      sec('share', '🧩 시장 점유율 — 모델 제작사', 'OpenRouter 텍스트 토큰 점유율', chipRow('share', [['pct', '비율'], ['abs', '절대']], ST.share)) +
      sec('bench', '🧠 벤치마크 — Artificial Analysis', '지수 상위 모델 · OpenRouter 실사용 모델 기준', chipRow('bench', [['intelligence', '지능'], ['coding', '코딩'], ['agentic', '에이전틱']], ST.bench)) +
      sec('task', '🗂 태스크별 점유율', '최근 30일 · 태스크 분류별 상위 모델', chipRow('taskSide', [['spend', '지출 기준'], ['tokens', '토큰 기준']], ST.taskSide)) +
      sec('cost', '💸 코딩 세션 비용', '유료 사용 중앙값 · 세션 길이별(단발/짧은/본격)', chipRow('harness', (data.session_cost.harnesses || []).map(function (h) { return [h.label, h.label]; }), ST.harness)) +
      sec('lang', '🌐 자연어별 사용량', '일간 토큰 · 3일 이동평균 계열', chipRow('lang', Object.keys(data.languages || {}).map(function (k) { return [k, langKo(k)]; }), ST.lang)) +
      sec('prog', '💻 프로그래밍 언어별', '코드 컨텍스트 감지 기준', chipRow('prog', Object.keys(data.programming || {}).map(function (k) { return [k, k]; }), ST.prog)) +
      sec('ctx', '📏 컨텍스트 길이별 요청', '프롬프트+컴플리션 길이 버킷', chipRow('ctx', [['1K', '< 1K'], ['10K', '1K–10K'], ['100K', '10K–100K'], ['1M', '100K–1M'], ['10M', '1M–10M']], ST.ctx)) +
      sec('tools', '🔧 툴콜 · 🖼 이미지', '주간 툴 호출 수 / 처리 이미지 수') +
      sec('apps', '📱 Top Apps', 'OpenRouter 경유 토큰 상위 앱', chipRow('apps', [['day', '오늘'], ['week', '주간'], ['month', '월간']], ST.apps)) +
      sec('perf', '⚡ 성능 — 지연 vs 처리량', 'p50 기준 · 버블 크기 = 주간 요청 수') +
      footer() + '</div>';

    var W = el.querySelector('.or-wrap');

    function hero() {
      return '<div class="or-hero"><h2>🤖 LLM — OpenRouter 사용량 관제 <span class="live"><i></i>DAILY</span></h2>' +
        '<div class="sub">전세계 개발자가 OpenRouter API로 흘려보낸 <b>실사용 토큰</b> 기준 랭킹 — 벤치마크가 아니라 <b>지갑이 투표한 순위</b>. ' +
        '사용량 기준일 <b>' + esc(data.as_of || '—') + '</b> · 수집 ' + esc(String(data.updated || '').replace('T', ' ').replace('Z', ' UTC')) + ' · 매일 09:00 KST 자동 갱신</div></div>';
    }
    function nav() {
      var items = [['lb', '🏆 리더보드'], ['top', '📈 추이'], ['share', '🧩 점유율'], ['bench', '🧠 벤치마크'], ['task', '🗂 태스크'], ['cost', '💸 세션비용'], ['lang', '🌐 언어'], ['prog', '💻 코드'], ['ctx', '📏 컨텍스트'], ['tools', '🔧 툴·이미지'], ['apps', '📱 앱'], ['perf', '⚡ 성능']];
      return '<div class="or-nav">' + items.map(function (it) { return '<a href="#or-' + it[0] + '">' + it[1] + '</a>'; }).join('') + '</div>';
    }
    function kpis() {
      var wk = data.leaderboard.week || [];
      var totTok = sum(wk.map(function (r) { return r.tok; }));
      var totRq = sum(wk.map(function (r) { return r.rq; }));
      var top1 = wk[0];
      var gain = (data.leaderboard.trending || []).filter(function (r) { return r.ch != null && r.tok > 1e9; })
        .sort(function (a, b) { return b.ch - a.ch; })[0];
      var ts = data.tools_series || { series: {} }, isr = data.images_series || { series: {} };
      var wkTc = sum(Object.keys(ts.series).map(function (k) { return last(ts.series[k]) || 0; }));
      var wkImg = sum(Object.keys(isr.series).map(function (k) { return last(isr.series[k]) || 0; }));
      var app1 = (data.apps.week || [])[0];
      var ms = data.market_share, lastShare = null, lead = null;
      if (ms && ms.dates && ms.dates.length) {
        var li = ms.dates.length - 1, tot2 = 0, best = null;
        Object.keys(ms.series).forEach(function (a) { var v = ms.series[a][li] || 0; tot2 += v; if (a !== 'others' && (!best || v > best[1])) best = [a, v]; });
        if (best && tot2) { lead = best[0]; lastShare = best[1] / tot2; }
      }
      function kpi(color, lab, val, sub) { return '<div class="or-kpi" style="--kc:' + color + '"><div class="lab">' + lab + '</div><div class="val">' + val + '</div><div class="sub">' + sub + '</div></div>'; }
      return '<div class="or-kpis">' +
        kpi(ACC, '주간 총 토큰 (상위 60)', fmtTok(totTok), fmtTok(totRq) + ' 요청') +
        kpi('#f6c85f', '1위 모델', top1 ? esc(nameOf(top1.m)) : '—', top1 ? '점유 ' + fmtPct(top1.tok / totTok) + ' · ' + fmtTok(top1.tok) : '') +
        kpi(UP, '최대 상승 모델', gain ? esc(nameOf(gain.m)) : '—',
          gain ? '전주 대비 ' + (gain.ch >= 10 ? '×' + (gain.ch + 1).toFixed(0)
            : (gain.ch >= 0 ? '+' : '−') + Math.abs(gain.ch * 100).toFixed(0) + '%') : '') +
        kpi('#b892ff', '제작사 점유 1위', lead ? esc(authorName(lead)) : '—', lastShare != null ? '주간 토큰의 ' + fmtPct(lastShare) : '') +
        kpi('#ff8a3d', '주간 툴 호출', fmtTok(wkTc), '이미지 처리 ' + fmtTok(wkImg) + '장') +
        kpi('#7ec8e3', 'Top App', app1 ? esc(app1.title) : '—', app1 ? fmtTok(app1.tok) + ' · 주간' : '') +
        '</div>';
    }
    function sec(id, title, hint, right) {
      return '<div class="or-sec" id="or-' + id + '"><div class="or-sech"><h3>' + title + '</h3><span class="hint2">' + esc(hint || '') + '</span><span class="sp"></span>' + (right || '') + '</div><div class="or-card" data-body="' + id + '"></div></div>';
    }
    function chipRow(key, pairs, cur) {
      return '<div class="or-chips" data-ck="' + key + '">' + pairs.map(function (p) {
        return '<button class="or-chip' + (p[0] === cur ? ' on' : '') + '" data-cv="' + esc(p[0]) + '">' + esc(p[1]) + '</button>';
      }).join('') + '</div>';
    }
    function langKo(k) {
      var M = { 'English': '영어', 'Korean': '한국어', 'Japanese': '일본어', 'Chinese (Simplified)': '중국어(간체)', 'Chinese (Traditional)': '중국어(번체)', 'Spanish': '스페인어', 'French': '프랑스어', 'German': '독일어', 'Russian': '러시아어', 'Portuguese': '포르투갈어', 'Vietnamese': '베트남어', 'Indonesian': '인도네시아어' };
      return M[k] || k;
    }
    function body(id) { return W.querySelector('[data-body="' + id + '"]'); }

    /* ---- 각 섹션 렌더 ---- */
    function rLeaderboard() {
      var rows = data.leaderboard[ST.view] || [];
      if (!rows.length) { body('lb').innerHTML = '<div class="or-empty">데이터 없음</div>'; return; }
      var maxTok = rows[0].tok || 1;
      var totAll = sum(rows.map(function (r) { return r.tok; })) || 1;
      var shown = rows.slice(0, ST.lbLimit);
      var html = '<div style="overflow-x:auto"><table class="or-tbl"><thead><tr>' +
        '<th></th><th class="l">모델</th><th style="min-width:150px">토큰</th><th>점유율</th><th>변화</th><th>요청</th><th>토큰/요청</th></tr></thead><tbody>' +
        shown.map(function (r, i) {
          var a = authorOf(r.m), col = colorOfAuthor(a);
          var tpr = r.rq ? r.tok / r.rq : null; // 요청당 토큰 = 평균 컨텍스트 무게
          return '<tr><td class="rk">' + (i + 1) + '</td>' +
            '<td class="mdl l"><span class="or-adot" style="background:' + col + '"></span><span class="mn">' + esc(nameOf(r.m + (r.v && r.v !== 'standard' ? ':' + r.v : ''))) + '</span><span class="au">' + esc(authorName(a)) + '</span></td>' +
            '<td><div style="display:flex;align-items:center;gap:8px;justify-content:flex-end"><div class="or-bar" style="flex:1"><i style="width:' + Math.max(1.5, r.tok / maxTok * 100).toFixed(1) + '%"></i></div><b>' + fmtTok(r.tok) + '</b></div></td>' +
            '<td style="color:' + ACC + '">' + fmtPct(r.tok / totAll) + '</td>' +
            '<td>' + fmtChg(r.ch) + '</td><td>' + fmtTok(r.rq) + '</td>' +
            '<td style="color:' + DIM + '">' + (tpr != null ? fmtTok(tpr) : '—') + '</td></tr>';
        }).join('') + '</tbody></table></div>' +
        (rows.length > ST.lbLimit ? '<div class="or-more"><button class="or-chip" data-act="more">▼ ' + (rows.length - ST.lbLimit) + '개 더 보기</button></div>'
          : (ST.lbLimit > 20 ? '<div class="or-more"><button class="or-chip" data-act="less">▲ 접기</button></div>' : ''));
      body('lb').innerHTML = html;
      var mb = body('lb').querySelector('[data-act]');
      if (mb) mb.onclick = function () { ST.lbLimit = mb.dataset.act === 'more' ? 60 : 20; rLeaderboard(); };
    }
    function rTop() { body('top').innerHTML = stackedArea(clonePack(data.top_chart), { h: 260, topN: 10, id: 'topchart' }); bindStackHover(body('top')); }
    function rShare() { body('share').innerHTML = stackedArea(clonePack(data.market_share), { h: 250, topN: 12, pct: ST.share === 'pct', id: 'mshare', labelFn: authorName }); bindStackHover(body('share')); }
    function rBench() {
      var rows = (data.benchmarks[ST.bench] || []).slice(0, 22);
      if (!rows.length) { body('bench').innerHTML = '<div class="or-empty">데이터 없음</div>'; return; }
      var mx = rows[0].score || 1, mn = rows[rows.length - 1].score || 0;
      var bars = rows.map(function (r, i) {
        var a = authorOf(r.m), col = colorOfAuthor(a);
        var w = Math.max(4, (r.score - mn * 0.85) / (mx - mn * 0.85) * 100);
        var price = data.benchmarks.price_in[r.p] || data.benchmarks.price_in[r.m];
        return '<div class="or-brow"><div class="nm" title="' + esc(r.name || '') + '">' + (i < 3 ? ['🥇', '🥈', '🥉'][i] + ' ' : '') + esc(nameOf(r.m)) + '</div>' +
          '<div class="tr"><i style="width:' + w.toFixed(1) + '%;background:linear-gradient(90deg,' + col + 'cc,' + col + '66)"></i></div>' +
          '<div class="sc" style="color:' + col + '">' + r.score.toFixed(1) + '</div>' +
          '<div style="flex:0 0 74px;font-family:' + MONO + ';font-size:10px;color:' + DIM + ';text-align:right">' + (price != null ? '$' + price.toFixed(2) + '/M' : '') + '</div></div>';
      }).join('');
      var lab = { intelligence: 'Intelligence Index', coding: 'Coding Index', agentic: 'Agentic Index' }[ST.bench];
      body('bench').innerHTML = '<div style="font-size:10.5px;color:' + DIM + ';margin-bottom:8px">' + lab + ' · 우측 = 가중 입력단가($/M tok) · 출처 Artificial Analysis</div>' + bars;
    }
    function rTask() {
      var side = data.tasks[ST.taskSide] || {};
      var mac = side.macro || [], tks = (side.tasks || []).slice().sort(function (a, b) { return b.share - a.share; }).slice(0, 12);
      var MC = { code: '#4ea1ff', agent: '#59d0a8', data: '#f6c85f', general: '#b892ff' };
      var bar = '<div class="or-mac">' + mac.map(function (m) {
        var c = MC[m.key] || PAL[5];
        return '<div style="flex:' + Math.max(0.02, m.share) + ';background:' + c + '" title="' + esc(m.label) + ' ' + fmtPct(m.share) + '">' + esc(m.label) + ' ' + fmtPct(m.share, 0) + '</div>';
      }).join('') + '</div>';
      var cards = '<div class="or-tasks">' + tks.map(function (t) {
        var c = MC[t.cat] || PAL[5];
        var nm = String(t.tag || '').split(':').pop().replace(/_/g, ' ');
        var models = (t.models || []).slice(0, 3).map(function (m) {
          var d = m.d != null ? ' <i style="color:' + (m.d >= 0 ? UP : DOWN) + '">' + (m.d >= 0 ? '+' : '') + m.d.toFixed(1) + 'pp</i>' : '';
          return '<b>' + esc(nameOf(m.m)) + '</b> ' + fmtPct(m.share, 0) + d;
        }).join('<br>');
        return '<div class="or-task" style="border-left:3px solid ' + c + '"><div class="tt"><span>' + esc(nm) + '</span><b>' + fmtPct(t.share) + '</b></div><div class="tm">' + models + '</div></div>';
      }).join('') + '</div>';
      body('task').innerHTML = bar + cards;
    }
    function rCost() {
      var h = (data.session_cost.harnesses || []).find(function (x) { return x.label === ST.harness; });
      if (!h || !h.models.length) { body('cost').innerHTML = '<div class="or-empty">데이터 없음</div>'; return; }
      var rows = h.models.slice().sort(function (a, b) { return (a.pts.core || 9e9) - (b.pts.core || 9e9); });
      var mx = Math.max.apply(null, rows.map(function (r) { return r.pts.core || 0; })) || 1;
      var html = '<div style="font-size:10.5px;color:' + DIM + ';margin-bottom:10px">단발 = 1회 왕복 · 짧은 = 짧은 세션 · 본격 = 본격 코딩 세션 · 최근 ' + (data.session_cost.window || 30) + '일 유료 사용 중앙값</div>' +
        '<div style="overflow-x:auto"><table class="or-tbl"><thead><tr><th class="l">모델</th><th>단발</th><th>짧은</th><th style="min-width:170px">본격 세션</th></tr></thead><tbody>' +
        rows.map(function (r) {
          var a = authorOf(r.m), col = colorOfAuthor(a);
          var core = r.pts.core;
          return '<tr><td class="mdl l"><span class="or-adot" style="background:' + col + '"></span><span class="mn">' + esc(nameOf(r.m)) + '</span></td>' +
            '<td>' + (r.pts.single != null ? '$' + r.pts.single.toFixed(2) : '—') + '</td>' +
            '<td>' + (r.pts.short != null ? '$' + r.pts.short.toFixed(2) : '—') + '</td>' +
            '<td><div style="display:flex;align-items:center;gap:8px;justify-content:flex-end"><div class="or-bar" style="flex:1"><i style="width:' + (core ? Math.max(2, core / mx * 100).toFixed(1) : 0) + '%;background:linear-gradient(90deg,' + col + 'cc,' + col + '55)"></i></div><b>' + (core != null ? '$' + core.toFixed(2) : '—') + '</b></div></td></tr>';
        }).join('') + '</tbody></table></div>';
      body('cost').innerHTML = html;
    }
    function rLang() { var p = data.languages[ST.lang]; body('lang').innerHTML = p ? stackedArea(clonePack(p), { h: 220, topN: 9, id: 'lang' }) : '<div class="or-empty">데이터 없음</div>'; bindStackHover(body('lang')); }
    function rProg() { var p = data.programming[ST.prog]; body('prog').innerHTML = p ? stackedArea(clonePack(p), { h: 220, topN: 9, id: 'prog' }) : '<div class="or-empty">데이터 없음</div>'; bindStackHover(body('prog')); }
    function rCtx() { var p = data.context[ST.ctx]; body('ctx').innerHTML = p ? stackedArea(clonePack(p), { h: 220, topN: 9, id: 'ctx' }) : '<div class="or-empty">데이터 없음</div>'; bindStackHover(body('ctx')); }
    function rTools() {
      body('tools').innerHTML = '<div class="or-grid2"><div><div style="font-size:12px;font-weight:750;margin-bottom:8px">🔧 툴 호출 수 (주간)</div>' +
        stackedArea(clonePack(data.tools_series), { h: 190, topN: 8, id: 'tools' }) + '</div>' +
        '<div><div style="font-size:12px;font-weight:750;margin-bottom:8px">🖼 처리 이미지 수 (주간)</div>' +
        stackedArea(clonePack(data.images_series), { h: 190, topN: 8, id: 'imgs' }) + '</div></div>';
      bindStackHover(body('tools'));
    }
    function rApps() {
      var rows = data.apps[ST.apps] || [];
      if (!rows.length) { body('apps').innerHTML = '<div class="or-empty">데이터 없음</div>'; return; }
      body('apps').innerHTML = '<div class="or-apps">' + rows.map(function (a, i) {
        var host = '', safeUrl = /^https?:\/\//i.test(a.url || '') ? a.url : null;
        try { host = safeUrl ? new URL(safeUrl).hostname.replace(/^www\./, '') : ''; } catch (e) { }
        return '<div class="or-app"><div class="rk2' + (i < 3 ? ' top' : '') + '">' + (i + 1) + '</div><div class="bd">' +
          '<div class="an">' + (safeUrl ? '<a href="' + esc(safeUrl) + '" target="_blank" rel="noopener">' + esc(a.title) + ' ↗</a>' : esc(a.title)) + '</div>' +
          '<div class="ad">' + esc(a.desc || host) + '</div>' +
          '<div class="am"><b>' + fmtTok(a.tok) + '</b> tokens · ' + fmtTok(a.rq) + ' req</div></div></div>';
      }).join('') + '</div>';
    }
    function rPerf() {
      var rows = (data.performance || []).filter(function (r) { return r.lat > 0 && r.tps > 0; }).slice(0, 90);
      if (!rows.length) { body('perf').innerHTML = '<div class="or-empty">데이터 없음</div>'; return; }
      var W2 = 900, H2 = 330, PL2 = 56, PR2 = 14, PT2 = 14, PB2 = 34;
      var lx = rows.map(function (r) { return Math.log10(r.tps); }), ly = rows.map(function (r) { return Math.log10(r.lat); });
      var xmn = Math.min.apply(null, lx), xmx = Math.max.apply(null, lx), ymn = Math.min.apply(null, ly), ymx = Math.max.apply(null, ly);
      var xr = (xmx - xmn) || 1, yr = (ymx - ymn) || 1;
      var rqmx = Math.max.apply(null, rows.map(function (r) { return r.rq || 0; })) || 1;
      var x = function (v) { return PL2 + (Math.log10(v) - xmn) / xr * (W2 - PL2 - PR2); };
      var y = function (v) { return PT2 + (Math.log10(v) - ymn) / yr * (H2 - PT2 - PB2); }; // 지연은 아래로 갈수록 김
      var dots = rows.map(function (r) {
        var a = authorOf(r.m), col = colorOfAuthor(a);
        var rad = 3 + Math.sqrt((r.rq || 0) / rqmx) * 15;
        return '<circle cx="' + x(r.tps).toFixed(1) + '" cy="' + y(r.lat).toFixed(1) + '" r="' + rad.toFixed(1) + '" fill="' + col + '" fill-opacity="0.5" stroke="' + col + '" stroke-width="1" data-i="' + rows.indexOf(r) + '"><title>' + esc(nameOf(r.m)) + '\n처리량 ' + r.tps + ' tok/s · 지연 ' + (r.lat / 1000).toFixed(1) + 's\n주간 ' + fmtTok(r.rq) + ' 요청' + (r.price ? '\n최속 프로바이더 $' + r.price.toFixed(2) + '/M' : '') + '</title></circle>';
      }).join('');
      // 라벨: 요청수 상위 12
      var labels = rows.slice(0, 12).map(function (r) {
        return '<text x="' + x(r.tps).toFixed(1) + '" y="' + (y(r.lat) - 8).toFixed(1) + '" font-size="9.5" fill="#cdd6de" text-anchor="middle" font-weight="700">' + esc(nameOf(r.m)) + '</text>';
      }).join('');
      var grid = '', gx = '', vals = [1, 3, 10, 30, 100, 300, 1000];
      vals.forEach(function (v) {
        if (Math.log10(v) >= xmn - 0.01 && Math.log10(v) <= xmx + 0.01) {
          grid += '<line x1="' + x(v).toFixed(1) + '" y1="' + PT2 + '" x2="' + x(v).toFixed(1) + '" y2="' + (H2 - PB2) + '" stroke="#1f2937" stroke-width="0.6" stroke-dasharray="3 4"/>' +
            '<text x="' + x(v).toFixed(1) + '" y="' + (H2 - 14) + '" font-size="9.5" fill="' + DIM + '" text-anchor="middle" font-family="ui-monospace,Menlo,monospace">' + v + '</text>';
        }
      });
      [500, 1000, 3000, 10000, 30000].forEach(function (v) {
        if (Math.log10(v) >= ymn - 0.01 && Math.log10(v) <= ymx + 0.01) {
          gx += '<line x1="' + PL2 + '" y1="' + y(v).toFixed(1) + '" x2="' + (W2 - PR2) + '" y2="' + y(v).toFixed(1) + '" stroke="#1f2937" stroke-width="0.6" stroke-dasharray="3 4"/>' +
            '<text x="' + (PL2 - 6) + '" y="' + (y(v) + 3.5).toFixed(1) + '" font-size="9.5" fill="' + DIM + '" text-anchor="end" font-family="ui-monospace,Menlo,monospace">' + (v >= 1000 ? (v / 1000) + 's' : v + 'ms') + '</text>';
        }
      });
      body('perf').innerHTML = '<div style="font-size:10.5px;color:' + DIM + ';margin-bottom:6px">→ 오른쪽 = 빠른 출력(tok/s, 로그) · ↑ 위 = 첫 토큰 빠름(p50 지연, 로그) · 마우스 오버로 상세</div>' +
        '<div class="or-plot"><svg viewBox="0 0 ' + W2 + ' ' + H2 + '">' + grid + gx + dots + labels +
        '<text x="' + (W2 - PR2) + '" y="' + (H2 - 2) + '" font-size="9.5" fill="' + DIM + '" text-anchor="end">처리량 tok/s →</text>' +
        '<text x="12" y="' + (PT2 + 2) + '" font-size="9.5" fill="' + DIM + '" writing-mode="tb" transform="rotate(0)">지연 p50 ↓</text></svg></div>';
    }
    function footer() {
      return '<div class="or-foot">Source: <a href="https://openrouter.ai/rankings" target="_blank" rel="noopener">OpenRouter (openrouter.ai/rankings)</a>, as of ' + esc(data.as_of || '') + ' · CC BY 4.0 · ' +
        '순위 = OpenRouter API 경유 프롬프트+컴플리션 토큰 합산(비공개 요청 제외) · 변형(:free 등)은 별도 랭킹 · 벤치마크 지수는 Artificial Analysis · ' +
        '본 탭은 채택(adoption) 지표이지 품질 지표가 아님 · 매일 09:00 KST GitHub Actions 자동 수집' +
        (data.warnings && data.warnings.length ? ' · ⚠ 부분 수집 경고 ' + data.warnings.length + '건' : '') + '</div>';
    }

    function clonePack(p) { // stackedArea가 Others 합성 시 원본 훼손 방지
      if (!p) return { dates: [], series: {} };
      var s = {}; Object.keys(p.series || {}).forEach(function (k) { s[k] = (p.series[k] || []).slice(); });
      return { dates: (p.dates || []).slice(), series: s };
    }

    /* ---- 칩 이벤트 (위임) ---- */
    W.addEventListener('click', function (ev) {
      var b = ev.target.closest('.or-chip'); if (!b) return;
      var row = b.closest('[data-ck]'); if (!row) return;
      var key = row.dataset.ck, val = b.dataset.cv;
      if (ST[key] === val) return;
      ST[key] = val;
      row.querySelectorAll('.or-chip').forEach(function (c) { c.classList.toggle('on', c === b); });
      if (key === 'view') { ST.lbLimit = 20; rLeaderboard(); }
      else if (key === 'share') rShare();
      else if (key === 'bench') rBench();
      else if (key === 'taskSide') rTask();
      else if (key === 'harness') rCost();
      else if (key === 'lang') rLang();
      else if (key === 'prog') rProg();
      else if (key === 'ctx') rCtx();
      else if (key === 'apps') rApps();
    });

    rLeaderboard(); rTop(); rShare(); rBench(); rTask(); rCost(); rLang(); rProg(); rCtx(); rTools(); rApps(); rPerf();
  };

  function shallowPick(obj, keys) { var o = {}; keys.forEach(function (k) { o[k] = obj[k]; }); return o; }
})();
