/* liq_charts.js — 유동성 대시보드 v2 렌더러 (의존성 0)
 *
 *   window.renderLiq2(el, data)
 *     el   : 렌더 대상 컨테이너 엘리먼트
 *     data : liquidity2.json 전체 객체
 *
 * 설계 요점 (스케일 문제 해결)
 *   · y도메인은 "표시 윈도(기간칩)" 데이터만으로 min/max + 4% 패딩 — 전 구간이 아님.
 *     → 최근 변화가 화면 높이를 실제로 채운다.
 *   · SOFR/EFFR은 절대금리가 아니라 IORB 대비 스프레드(bp) 시계열을 그린다.
 *   · 기준선은 표시 윈도 도메인 안에 들어올 때만 그린다(도메인 강제확장 금지).
 *
 * 로드 시 부작용 없음 — window.renderLiq2 정의만 한다. CSS는 첫 렌더에서 1회 주입.
 */
(function () {
  'use strict';

  /* ── 팔레트 ─────────────────────────────────────────────────────────── */
  var LC = { green: '#3ddc97', yellow: '#ffd23d', orange: '#ff8a3d', red: '#ff4d5e', gray: '#8a93a3' };
  var LL = { green: '초록불', yellow: '노란불', orange: '주황불', red: '빨간불', gray: '—' };
  var UP = '#ff4d5e';    // 나쁜 방향
  var DOWN = '#4ea1ff';  // 좋은 방향
  var NEUTRAL = '#8a93a3';

  /* 지표별 bad_direction — 어느 쪽으로 움직이면 "나쁜" 것인지.
     배지 색은 부호가 아니라 이 방향성에 맞춘다.
       NETLIQ↓ = 유동성 긴축 = 빨강 / HY_OAS↑ = 크레딧 악화 = 빨강
       VIX↑ = 빨강 / USDKRW↑ = 원화 약세·자금이탈 = 빨강                        */
  var BAD_DIR = {
    NETLIQ: 'down', TGA: 'up', RRP: 'down', RESERVES: 'down',
    SOFR_IORB_BP: 'up', EFFR_IORB_BP: 'up',
    HY_OAS: 'up', IG_OAS: 'up', T10Y2Y: 'down', NFCI: 'up',
    DXY: 'up', USDKRW: 'up', USDJPY: 'up', VIX: 'up'
  };

  var RANGES = [['3M', 3], ['6M', 6], ['1Y', 12], ['ALL', 0]];
  var DEFAULT_RANGE = '6M';

  /* ── 포맷 유틸 ──────────────────────────────────────────────────────── */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function num(v, dp) {
    if (v == null || isNaN(v)) return '—';
    var s = Number(v).toFixed(dp == null ? 2 : dp);
    var p = s.split('.');
    p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return p.join('.');
  }
  function sgn(v, dp) {
    if (v == null || isNaN(v)) return '—';
    return (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(v), dp);
  }
  var F = {
    trillion: function (v) { return v == null ? '—' : '$' + num(v / 1000, 2) + 'T'; },
    billion0: function (v) { return v == null ? '—' : num(v, 0) + 'B'; },
    billion1: function (v) { return v == null ? '—' : num(v, 1) + 'B'; },
    bp: function (v) { return v == null ? '—' : sgn(v, 1) + 'bp'; },
    pct2: function (v) { return v == null ? '—' : num(v, 2) + '%p'; },
    spct2: function (v) { return v == null ? '—' : sgn(v, 2) + '%p'; },
    plain2: function (v) { return num(v, 2); },
    plain3: function (v) { return num(v, 3); },
    won: function (v) { return v == null ? '—' : num(v, 1) + '원'; },
    vix: function (v) { return num(v, 2); }
  };
  var D = {   /* Δ 배지용 — 부호 포함 축약 표기 */
    billion: function (v) { return sgn(v, 0) + 'B'; },
    billion1: function (v) { return sgn(v, 1) + 'B'; },
    bp: function (v) { return sgn(v, 1) + 'bp'; },
    pp: function (v) { return sgn(v, 2) + '%p'; },
    plain2: function (v) { return sgn(v, 2); },
    plain1: function (v) { return sgn(v, 1); }
  };

  /* ── 날짜/시계열 유틸 ──────────────────────────────────────────────── */
  function keysOf(s) { return s ? Object.keys(s).sort() : []; }
  function lastKey(s) { var k = keysOf(s); return k.length ? k[k.length - 1] : null; }
  function lastVal(s) { var k = lastKey(s); return k == null ? null : s[k]; }
  function shiftMonths(ds, m) {
    var p = ds.split('-'), y = +p[0], mo = +p[1] - 1, d = +p[2];
    var t = mo - m, ny = y + Math.floor(t / 12), nm = ((t % 12) + 12) % 12;
    var dim = new Date(Date.UTC(ny, nm + 1, 0)).getUTCDate();
    var pad = function (n) { return (n < 10 ? '0' : '') + n; };
    return ny + '-' + pad(nm + 1) + '-' + pad(Math.min(d, dim));
  }
  function shiftDays(ds, n) {
    var p = ds.split('-');
    var t = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2] - n));
    var pad = function (x) { return (x < 10 ? '0' : '') + x; };
    return t.getUTCFullYear() + '-' + pad(t.getUTCMonth() + 1) + '-' + pad(t.getUTCDate());
  }
  /* days일 전(달력 기준, 그 이하 마지막 유효값) 대비 변화 */
  function calcDelta(series, days) {
    var ks = keysOf(series);
    if (ks.length < 2) return { abs: null, pct: null };
    var lk = ks[ks.length - 1], target = shiftDays(lk, days), base = null;
    for (var i = ks.length - 1; i >= 0; i--) { if (ks[i] <= target) { base = series[ks[i]]; break; } }
    if (base == null) return { abs: null, pct: null };
    var v = series[lk];
    return { abs: v - base, pct: base ? (v - base) / Math.abs(base) * 100 : null };
  }

  /* ── 차트 SVG ───────────────────────────────────────────────────────
     y도메인 = 넘겨받은 (윈도) 값들만의 min/max + 4% 패딩.                */
  var W = 600, H = 168, PL = 8, PR = 54, PT = 14, PB = 22;

  function chartSVG(ks, vs, color, refs, fmt) {
    var n = vs.length;
    if (n < 2) return { svg: '<div class="liq2-empty">표시 구간 데이터 부족</div>', map: null };
    var mn = Math.min.apply(null, vs), mx = Math.max.apply(null, vs);
    var rg = mx - mn;
    var padv = rg > 0 ? rg * 0.04 : (Math.abs(mx) * 0.02 || 1);
    var lo = mn - padv, hi = mx + padv, span = (hi - lo) || 1;
    var pw = W - PL - PR, ph = H - PT - PB;
    var X = function (i) { return PL + pw * (n === 1 ? 0 : i / (n - 1)); };
    var Y = function (v) { return PT + ph * (1 - (v - lo) / span); };

    var s = [];
    /* 가로 그리드 4줄 + 우측 y라벨 */
    for (var g = 0; g < 4; g++) {
      var gv = lo + span * (g / 3), gy = Y(gv);
      s.push('<line class="liq2-grid" x1="' + PL + '" y1="' + gy.toFixed(1) +
        '" x2="' + (W - PR) + '" y2="' + gy.toFixed(1) + '"/>');
      s.push('<text class="liq2-ylab" x="' + (W - PR + 6) + '" y="' + (gy + 3.2).toFixed(1) + '">' +
        esc(fmt(gv)) + '</text>');
    }
    /* 기준선 — 윈도 도메인 밖이면 생략(도메인 강제확장 금지) */
    for (var r = 0; r < refs.length; r++) {
      var rf = refs[r];
      if (rf.v < lo || rf.v > hi) continue;
      var ry = Y(rf.v);
      s.push('<line x1="' + PL + '" y1="' + ry.toFixed(1) + '" x2="' + (W - PR) + '" y2="' + ry.toFixed(1) +
        '" stroke="' + rf.c + '" stroke-width="1"' +
        (rf.solid ? ' opacity=".75"' : ' stroke-dasharray="4 3" opacity=".7"') + '/>');
      if (rf.label) {
        s.push('<text class="liq2-reflab" x="' + (PL + 3) + '" y="' + (ry - 3.5).toFixed(1) +
          '" fill="' + rf.c + '">' + esc(rf.label) + '</text>');
      }
    }
    /* x라벨 4개 (YYYY-MM) */
    var xn = Math.min(4, n);
    for (var t = 0; t < xn; t++) {
      var idx = Math.round((n - 1) * t / (xn - 1 || 1));
      var tx = X(idx), anch = t === 0 ? 'start' : (t === xn - 1 ? 'end' : 'middle');
      s.push('<text class="liq2-xlab" x="' + tx.toFixed(1) + '" y="' + (H - 6) +
        '" text-anchor="' + anch + '">' + esc(ks[idx].slice(0, 7)) + '</text>');
    }
    /* 라인 */
    var pts = [];
    for (var i = 0; i < n; i++) pts.push(X(i).toFixed(1) + ',' + Y(vs[i]).toFixed(1));
    s.push('<polyline points="' + pts.join(' ') + '" fill="none" stroke="' + color +
      '" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>');
    /* 마지막 점 + 값 라벨 */
    var lx = X(n - 1), ly = Y(vs[n - 1]);
    var laby = Math.max(PT + 9, Math.min(H - PB - 3, ly - 8));
    s.push('<circle cx="' + lx.toFixed(1) + '" cy="' + ly.toFixed(1) + '" r="3.2" fill="' + color + '"/>');
    s.push('<text class="liq2-last" x="' + (lx - 5).toFixed(1) + '" y="' + laby.toFixed(1) +
      '" text-anchor="end" fill="' + color + '">' + esc(fmt(vs[n - 1])) + '</text>');
    /* 호버 크로스헤어 */
    s.push('<g class="liq2-hv" style="display:none">' +
      '<line y1="' + PT + '" y2="' + (H - PB) + '" stroke="' + color + '" stroke-width="1" opacity=".45"/>' +
      '<circle r="3.6" fill="none" stroke="' + color + '" stroke-width="1.6"/></g>');

    var svg = '<svg class="liq2-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img">' + s.join('') + '</svg>';
    return { svg: svg, map: { X: X, Y: Y, n: n } };
  }

  /* ── 카드 조립 ─────────────────────────────────────────────────────── */
  function deltaBadge(label, chg, pct, key, dfmt) {
    if (chg == null || isNaN(chg)) {
      return '<span class="liq2-dlt" style="color:' + NEUTRAL + '">' + label + ' —</span>';
    }
    var bad = BAD_DIR[key];
    var arrow = chg > 0 ? '↑' : (chg < 0 ? '↓' : '→');
    var col = NEUTRAL;
    if (bad && chg !== 0) col = ((chg > 0) === (bad === 'up')) ? UP : DOWN;
    var tip = (pct == null || isNaN(pct)) ? '' : ' (' + sgn(pct, 2) + '%)';
    return '<span class="liq2-dlt" style="color:' + col + ';background:' + col + '1f">' +
      label + ' ' + arrow + ' ' + esc(dfmt(chg)) + esc(tip) + '</span>';
  }

  function buildCard(spec, series, cutoff) {
    var wrap = document.createElement('div');
    wrap.className = 'liq2-chart';

    var ks = keysOf(series);
    var wks = cutoff ? ks.filter(function (k) { return k >= cutoff; }) : ks;
    if (wks.length < 2) wks = ks.slice(-2);
    var wvs = wks.map(function (k) { return series[k]; });

    var cur = lastVal(series);
    var dlt = spec.deltas || {};
    var d1 = dlt.d1w != null ? { abs: dlt.d1w, pct: dlt.p1w } : calcDelta(series, 7);
    var d4 = dlt.d4w != null ? { abs: dlt.d4w, pct: dlt.p4w } : calcDelta(series, 28);
    var dfmt = spec.dfmt || D.plain2;

    var head = '<div class="liq2-ct">' +
      '<span class="liq2-name">' + esc(spec.title) + '</span>' +
      '<b class="liq2-cur" style="color:' + spec.color + '">' + esc(spec.fmt(cur)) + '</b>' +
      deltaBadge('1주', d1.abs, d1.pct, spec.key, dfmt) +
      deltaBadge('4주', d4.abs, d4.pct, spec.key, dfmt) +
      '</div>' +
      (spec.sub ? '<div class="liq2-csub">' + esc(spec.sub) + '</div>' : '');

    var built = chartSVG(wks, wvs, spec.color, spec.refs || [], spec.fmt);
    wrap.innerHTML = head + '<div class="liq2-plot">' + built.svg +
      '<div class="liq2-tip" style="display:none"></div></div>';

    if (built.map) attachHover(wrap, wks, wvs, built.map, spec);
    return wrap;
  }

  function attachHover(wrap, ks, vs, map, spec) {
    var svg = wrap.querySelector('svg.liq2-svg');
    var tip = wrap.querySelector('.liq2-tip');
    var hv = wrap.querySelector('.liq2-hv');
    if (!svg || !tip || !hv) return;
    var line = hv.getElementsByTagName('line')[0];
    var dot = hv.getElementsByTagName('circle')[0];
    var plot = wrap.querySelector('.liq2-plot');

    svg.addEventListener('mousemove', function (e) {
      var r = svg.getBoundingClientRect();
      if (!r.width) return;
      var vx = (e.clientX - r.left) / r.width * W;
      var i = Math.round((vx - PL) / (W - PL - PR) * (map.n - 1));
      if (i < 0) i = 0; if (i > map.n - 1) i = map.n - 1;
      var px = map.X(i), py = map.Y(vs[i]);
      line.setAttribute('x1', px.toFixed(1)); line.setAttribute('x2', px.toFixed(1));
      dot.setAttribute('cx', px.toFixed(1)); dot.setAttribute('cy', py.toFixed(1));
      hv.style.display = '';
      tip.innerHTML = '<span class="liq2-tipd">' + esc(ks[i]) + '</span>' +
        '<b style="color:' + spec.color + '">' + esc(spec.fmt(vs[i])) + '</b>';
      tip.style.display = '';
      var pr = plot.getBoundingClientRect();
      var left = px / W * pr.width;
      tip.style.left = Math.max(2, Math.min(pr.width - tip.offsetWidth - 2, left - tip.offsetWidth / 2)) + 'px';
      tip.style.top = Math.max(0, py / H * pr.height - tip.offsetHeight - 8) + 'px';
    });
    svg.addEventListener('mouseleave', function () {
      hv.style.display = 'none';
      tip.style.display = 'none';
    });
  }

  /* ── 차트 정의 ─────────────────────────────────────────────────────── */
  function fundingSpecs(d, S) {
    var ref0 = { v: 0, c: '#8a93a3', solid: true, label: '0' };
    var ref5 = { v: 5, c: '#ff8a3d', label: '+5bp' };
    var ref10 = { v: 10, c: '#ff4d5e', label: '+10bp' };
    return [
      { key: 'NETLIQ', title: 'Net Liquidity (WALCL−TGA−RRP)', color: '#2bc0d4', fmt: F.trillion, dfmt: D.billion },
      { key: 'TGA', title: 'TGA (재무부 현금)', color: '#ff8a3d', fmt: F.billion0, dfmt: D.billion,
        refs: [{ v: 900, c: '#ff8a3d', label: '900B' }] },
      { key: 'RRP', title: 'RRP (역레포 잔고)', color: '#ffd23d', fmt: F.billion1, dfmt: D.billion1 },
      { key: 'RESERVES', title: '지급준비금 (WRESBAL)', color: '#59d0a8', fmt: F.trillion, dfmt: D.billion },
      { key: 'SOFR_IORB_BP', title: 'SOFR − IORB', color: '#ff4d5e', fmt: F.bp, dfmt: D.bp,
        refs: [ref0, ref5, ref10], sub: '레포 스트레스 — 0 위로 벌어지면 담보자금 조달비용 상승' },
      { key: 'EFFR_IORB_BP', title: 'EFFR − IORB', color: '#4ea1ff', fmt: F.bp, dfmt: D.bp,
        refs: [ref0, ref5, ref10], sub: '은행 시스템 — IORB 위로 붙으면 reserve 부족 신호' }
    ];
  }
  function creditSpecs(d, S) {
    var L = ((d.sections || {}).credit || {}).latest || {};
    var g = function (k) { return (L[k] || {}).value != null ? (L[k] || {}).value : lastVal(S[k]); };
    return [
      { key: 'HY_OAS', title: 'HY OAS (하이일드 스프레드)', color: '#ff6b6b', fmt: F.pct2, dfmt: D.pp,
        refs: [{ v: 4.5, c: '#ff8a3d', label: '4.5' }, { v: 5.5, c: '#ff4d5e', label: '5.5' }] },
      { key: 'IG_OAS', title: 'IG OAS (투자등급 스프레드)', color: '#ffab3d', fmt: F.pct2, dfmt: D.pp },
      { key: 'T10Y2Y', title: '10Y − 2Y 커브', color: '#b48cff', fmt: F.spct2, dfmt: D.pp,
        refs: [{ v: 0, c: '#8a93a3', solid: true, label: '0 (역전 경계)' }],
        sub: 'DGS10 ' + F.pct2(g('DGS10')) + ' · DGS2 ' + F.pct2(g('DGS2')) },
      { key: 'NFCI', title: 'NFCI (시카고 연준 금융환경지수)', color: '#8a93a3', fmt: F.plain3, dfmt: D.plain2,
        sub: '양수 = 평균보다 타이트한 금융환경' }
    ];
  }
  function fxvolSpecs(d, S) {
    var L = ((d.sections || {}).fxvol || {}).latest || {};
    var g = function (k) { return (L[k] || {}).value != null ? (L[k] || {}).value : lastVal(S[k]); };
    return [
      { key: 'DXY', title: '달러지수 (광의, DTWEXBGS)', color: '#4dd0e1', fmt: F.plain2, dfmt: D.plain2 },
      { key: 'USDKRW', title: '원/달러', color: '#ff7ab8', fmt: F.won, dfmt: D.plain1 },
      { key: 'USDJPY', title: '엔/달러', color: '#ffd23d', fmt: F.plain2, dfmt: D.plain2 },
      { key: 'VIX', title: 'VIX', color: '#ff4d5e', fmt: F.vix, dfmt: D.plain2,
        refs: [{ v: 20, c: '#ff8a3d', label: '20' }, { v: 30, c: '#ff4d5e', label: '30' }],
        sub: '기대인플레 BEI10 ' + F.pct2(g('BEI10')) + ' · 실질금리 REAL10 ' + F.pct2(g('REAL10')) }
    ];
  }

  /* ── 신호등 카드 (현행 5 + hy/curve/vix/dxy4w = 9) ─────────────────── */
  function lightCards(d) {
    var lights = d.lights || {};
    var fund = (d.sections || {}).funding || {};
    var C = fund.computed || {};
    var FL = fund.latest || {};
    var CL = ((d.sections || {}).credit || {}).latest || {};
    var XL = ((d.sections || {}).fxvol || {}).latest || {};
    var dl = d.deltas || {};
    var v = function (o, k) { return ((o || {})[k] || {}).value; };
    var items = [
      ['repo', '레포 (SOFR−IORB)', F.bp(C.sofr_iorb_bp),
        (C.sofr_iorb_bp != null && C.sofr_iorb_bp > 0) ? 'IORB 위 = 스트레스' : 'IORB 아래 = 안정'],
      ['bank', '은행 (EFFR−IORB)', F.bp(C.effr_iorb_bp),
        (C.effr_iorb_bp != null && C.effr_iorb_bp < 0) ? 'IORB 아래 = 정상' : '경계'],
      ['tga', 'TGA 흡수압력', F.billion0(v(FL, 'TGA')),
        lights.tga === 'green' ? '900B 미만' : '재축적 압력'],
      ['rrp', 'RRP 완충재', F.billion1(v(FL, 'RRP')),
        (v(FL, 'RRP') != null && v(FL, 'RRP') < 20) ? '사실상 고갈' : '남아있음'],
      ['netliq', 'Net Liq 방향', F.trillion(C.net_liquidity),
        sgn(C.net_liquidity_chg_1w, 0) + 'B / 1주'],
      ['hy', 'HY OAS (크레딧)', F.pct2(v(CL, 'HY_OAS')),
        sgn((dl.HY_OAS || {}).d4w, 2) + '%p / 4주'],
      ['curve', '10Y−2Y 커브', F.spct2(v(CL, 'T10Y2Y')),
        (v(CL, 'T10Y2Y') != null && v(CL, 'T10Y2Y') < 0) ? '역전 상태' : '정상 기울기'],
      ['vix', 'VIX (변동성)', F.vix(v(XL, 'VIX')), 'S&P 내재변동성'],
      ['dxy4w', '달러 4주 변화', sgn((dl.DXY || {}).p4w, 2) + '%',
        'DXY ' + F.plain2(v(XL, 'DXY')) + ' — 급등=글로벌 긴축']
    ];
    return items.map(function (it) {
      var col = LC[lights[it[0]]] || LC.gray;
      return '<div class="liq2-lcard" style="border-top:3px solid ' + col + '">' +
        '<div class="liq2-lt">' + esc(it[1]) + '<span class="liq2-dot" style="background:' + col + '"></span></div>' +
        '<div class="liq2-lv">' + esc(it[2]) + '</div>' +
        '<div class="liq2-ls">' + esc(it[3]) + '</div></div>';
    }).join('');
  }

  /* ── CSS (1회 주입) ────────────────────────────────────────────────── */
  var CSS = [
    '.liq2{--liq2-mono:var(--mono,ui-monospace,SFMono-Regular,Menlo,monospace);',
    '--liq2-panel:var(--panel,#12161c);--liq2-line:var(--line,#232a33);--liq2-dim:var(--dim,#8a93a3)}',
    '.liq2-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:6px}',
    '.liq2-head h2{font-size:20px;font-weight:800;margin:0}',
    '.liq2-ov{font-size:12px;font-weight:700;padding:4px 12px;border-radius:999px}',
    '.liq2-chips{display:flex;gap:4px;margin-left:auto;background:var(--liq2-panel);',
    'border:1px solid var(--liq2-line);border-radius:999px;padding:3px}',
    '.liq2-chip{font-family:var(--liq2-mono);font-size:11px;font-weight:700;padding:4px 11px;',
    'border-radius:999px;border:0;background:transparent;color:var(--liq2-dim);cursor:pointer;line-height:1}',
    '.liq2-chip[aria-pressed="true"]{background:#2bc0d422;color:#2bc0d4}',
    '.liq2-sub{color:var(--liq2-dim);font-size:12.5px;margin:0 0 18px}',
    '.liq2-lights{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:22px}',
    '.liq2-lcard{background:var(--liq2-panel);border:1px solid var(--liq2-line);border-radius:12px;',
    'padding:12px 15px;min-width:148px;flex:1 1 148px}',
    '.liq2-lt{font-size:11px;color:var(--liq2-dim);font-weight:600;display:flex;align-items:center;gap:6px}',
    '.liq2-dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-left:auto}',
    '.liq2-lv{font-family:var(--liq2-mono);font-size:20px;font-weight:750;margin-top:4px}',
    '.liq2-ls{font-family:var(--liq2-mono);font-size:10.5px;color:var(--liq2-dim);margin-top:2px}',
    '.liq2-sec{font-size:13px;font-weight:750;margin:0 0 10px;display:flex;align-items:baseline;gap:8px}',
    '.liq2-sec span{font-family:var(--liq2-mono);font-size:10.5px;color:var(--liq2-dim);font-weight:500}',
    '.liq2-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:14px;margin-bottom:24px}',
    '.liq2-chart{background:var(--liq2-panel);border:1px solid var(--liq2-line);border-radius:12px;padding:13px 15px 8px}',
    '.liq2-ct{display:flex;align-items:baseline;gap:7px;flex-wrap:wrap;font-size:12.5px;font-weight:650}',
    '.liq2-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}',
    '.liq2-cur{font-family:var(--liq2-mono);font-size:14.5px;font-weight:800;margin-left:auto}',
    '.liq2-dlt{font-family:var(--liq2-mono);font-size:10px;font-weight:700;padding:2px 6px;border-radius:5px;white-space:nowrap}',
    '.liq2-csub{font-size:10.5px;color:var(--liq2-dim);margin-top:3px;font-family:var(--liq2-mono)}',
    '.liq2-plot{position:relative;margin-top:6px}',
    '.liq2-svg{width:100%;height:auto;display:block;overflow:visible}',
    '.liq2-svg text{font-family:var(--liq2-mono);font-size:10px;fill:var(--liq2-dim)}',
    '.liq2-svg .liq2-reflab{font-size:9px;font-weight:700}',
    '.liq2-svg .liq2-last{font-size:10.5px;font-weight:800}',
    '.liq2-grid-line,.liq2-svg .liq2-grid{stroke:var(--liq2-line);stroke-width:1;opacity:.55}',
    '.liq2-empty{font-size:11.5px;color:var(--liq2-dim);padding:56px 0;text-align:center}',
    '.liq2-tip{position:absolute;pointer-events:none;background:#0b0e13ee;border:1px solid var(--liq2-line);',
    'border-radius:7px;padding:4px 8px;font-family:var(--liq2-mono);font-size:10.5px;white-space:nowrap;z-index:3}',
    '.liq2-tip .liq2-tipd{color:var(--liq2-dim);margin-right:6px}',
    '.liq2-comment{background:var(--liq2-panel);border:1px solid var(--liq2-line);border-radius:14px;',
    'padding:20px 24px;max-width:920px}',
    '.liq2-comment pre{font-family:var(--sans,inherit);font-size:13.5px;line-height:1.85;white-space:pre-wrap;margin:0}',
    '.liq2-cmeta{font-family:var(--liq2-mono);font-size:11px;color:var(--liq2-dim);margin-top:14px;',
    'border-top:1px solid var(--liq2-line);padding-top:10px}'
  ].join('');

  function injectCss() {
    if (typeof document === 'undefined') return;
    if (document.getElementById('liq2Css')) return;
    var st = document.createElement('style');
    st.id = 'liq2Css';
    st.textContent = CSS;
    (document.head || document.documentElement).appendChild(st);
  }

  /* ── 렌더 ───────────────────────────────────────────────────────────── */
  function renderLiq2(el, data) {
    if (!el) return;
    injectCss();
    var d = data || {};
    var sec = d.sections || {};
    var S = {};
    ['funding', 'credit', 'fxvol'].forEach(function (k) {
      var ss = (sec[k] || {}).series || {};
      Object.keys(ss).forEach(function (n) { S[n] = ss[n] || {}; });
    });

    var ov = d.overall || 'gray';
    var ovc = LC[ov] || LC.gray;
    var state = { range: DEFAULT_RANGE };

    /* 전 차트 공통 기준일 — 가장 최근 관측일 */
    var anchor = d.updated || null;
    Object.keys(S).forEach(function (n) {
      var lk = lastKey(S[n]);
      if (lk && (!anchor || lk > anchor)) anchor = lk;
    });

    el.className = (el.className || '').indexOf('liq2') >= 0 ? el.className : ((el.className || '') + ' liq2').trim();
    el.innerHTML =
      '<div class="liq2-head"><h2>💧 유동성 대시보드</h2>' +
      '<span class="liq2-ov" style="background:' + ovc + '22;color:' + ovc + '">종합 ' + esc(LL[ov] || '—') + '</span>' +
      '<div class="liq2-chips" role="group" aria-label="기간">' +
      RANGES.map(function (r) {
        return '<button type="button" class="liq2-chip" data-r="' + r[0] + '" aria-pressed="' +
          (r[0] === state.range) + '">' + r[0] + '</button>';
      }).join('') + '</div></div>' +
      '<p class="liq2-sub">Net Liquidity = 연준 총자산 − TGA − RRP · FRED 실시간 · ' +
      'y축은 선택 기간 데이터만으로 스케일링 · 업데이트 ' + esc(d.updated || '—') + '</p>' +
      '<div class="liq2-lights">' + lightCards(d) + '</div>' +
      '<div class="liq2-sec">① 단기자금 <span>NetLiq · TGA · RRP · 지급준비금 · IORB 대비 스프레드(bp)</span></div>' +
      '<div class="liq2-grid" data-g="funding"></div>' +
      '<div class="liq2-sec">② 크레딧 · 커브 <span>HY/IG OAS · 장단기 금리차 · 금융환경지수</span></div>' +
      '<div class="liq2-grid" data-g="credit"></div>' +
      '<div class="liq2-sec">③ 환율 · 변동성 <span>달러지수 · 원달러 · 엔달러 · VIX</span></div>' +
      '<div class="liq2-grid" data-g="fxvol"></div>' +
      '<div class="liq2-comment"><pre>' + esc(d.commentary || '') + '</pre>' +
      '<div class="liq2-cmeta">자동 생성 해석 — 실시간 FRED 수치 기반. 투자 조언 아님. ' +
      '#NetLiquidity #TGA #RRP #SOFR #IORB #HYOAS #T10Y2Y #DXY #VIX</div></div>';

    var groups = {
      funding: { el: el.querySelector('[data-g="funding"]'), specs: fundingSpecs(d, S) },
      credit: { el: el.querySelector('[data-g="credit"]'), specs: creditSpecs(d, S) },
      fxvol: { el: el.querySelector('[data-g="fxvol"]'), specs: fxvolSpecs(d, S) }
    };

    function draw() {
      var months = 6;
      for (var i = 0; i < RANGES.length; i++) if (RANGES[i][0] === state.range) months = RANGES[i][1];
      var cutoff = (months && anchor) ? shiftMonths(anchor, months) : null;
      Object.keys(groups).forEach(function (gk) {
        var g = groups[gk];
        if (!g.el) return;
        g.el.innerHTML = '';
        g.specs.forEach(function (sp) {
          sp.deltas = (d.deltas || {})[sp.key] || {};
          g.el.appendChild(buildCard(sp, S[sp.key] || {}, cutoff));
        });
      });
    }

    var chips = el.querySelectorAll('.liq2-chip');
    for (var c = 0; c < chips.length; c++) {
      chips[c].addEventListener('click', function (e) {
        state.range = e.currentTarget.getAttribute('data-r');
        for (var j = 0; j < chips.length; j++) {
          chips[j].setAttribute('aria-pressed', String(chips[j].getAttribute('data-r') === state.range));
        }
        draw();
      });
    }
    draw();
  }

  if (typeof window !== 'undefined') window.renderLiq2 = renderLiq2;
  if (typeof module !== 'undefined' && module.exports) module.exports = { renderLiq2: renderLiq2 };
})();
