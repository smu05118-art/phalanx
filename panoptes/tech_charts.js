/* tech_charts.js — 이격도·MDD 추이 차트 (의존성 0, 순수 SVG)
 * 전역: window.renderTechCharts(el, data)
 *   data = tech_indicators.json 전체 객체
 * 로드 시 부작용 없음(함수 정의만). 외부 라이브러리·fetch 사용 안 함.
 */
(function () {
  'use strict';

  var ORDER = ['kospi', 'nasdaq'];
  var LABEL = { kospi: 'KOSPI', nasdaq: 'NASDAQ' };
  var COLOR = { kospi: '#4ea1ff', nasdaq: '#59d0a8' };
  var PERIODS = [
    { k: '3M', n: 63 }, { k: '6M', n: 126 }, { k: '1Y', n: 252 },
    { k: '2Y', n: 504 }, { k: '5Y', n: 1260 }
  ];
  var DEFAULT_PERIOD = '1Y';

  // SVG 좌표계(viewBox) — 실제 폭은 CSS 100%
  var W = 520, H = 176, PL = 10, PR = 44, PT = 16, PB = 22;
  var PW = W - PL - PR, PH = H - PT - PB;

  var MONO = 'var(--mono,ui-monospace,SFMono-Regular,Menlo,monospace)';
  var DIM = '#8a93a3';

  var CSS = [
    '.tc-wrap{display:flex;flex-direction:column;gap:12px}',
    '.tc-head{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}',
    '.tc-title{font-size:14px;font-weight:750;letter-spacing:-.01em}',
    '.tc-chips{display:flex;gap:6px}',
    '.tc-chip{font:inherit;font-size:11.5px;line-height:1.5;padding:3px 9px;border:1px solid var(--line,#2a2f3a);',
    'border-radius:999px;background:transparent;color:var(--dim,#8a93a3);cursor:pointer;transition:all .12s}',
    '.tc-chip:hover{border-color:rgba(43,192,212,.5);color:#2bc0d4}',
    '.tc-chip.on{background:rgba(43,192,212,.14);color:#2bc0d4;border-color:rgba(43,192,212,.45)}',
    '.tc-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}',
    '@media (max-width:920px){.tc-grid{grid-template-columns:1fr}}',
    '.tc-col{display:flex;flex-direction:column;gap:12px;min-width:0}',
    '.tc-card{background:var(--panel,#12161d);border:1px solid var(--line,#2a2f3a);border-radius:13px;padding:14px 16px}',
    '.tc-cardhead{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:4px}',
    '.tc-t{font-size:12px;font-weight:650}',
    '.tc-t em{font-style:normal;color:var(--dim,#8a93a3);font-weight:550}',
    '.tc-v{font-family:' + MONO + ';font-size:12.5px;font-weight:700}',
    '.tc-plot{position:relative}',
    '.tc-plot svg{display:block;width:100%;height:auto;overflow:visible}',
    '.tc-guide{opacity:0}',
    '.tc-plot.on .tc-guide{opacity:1}',
    '.tc-tip{position:absolute;top:2px;transform:translateX(-50%);pointer-events:none;opacity:0;',
    'background:rgba(10,12,16,.92);border:1px solid var(--line,#2a2f3a);border-radius:6px;padding:3px 7px;',
    'font-family:' + MONO + ';font-size:10.5px;color:#e6e9ef;white-space:nowrap;z-index:3;transition:opacity .1s}',
    '.tc-plot.on .tc-tip{opacity:1}',
    '.tc-empty{font-size:11.5px;color:var(--dim,#8a93a3);padding:10px 0}'
  ].join('');

  function ensureCss(doc) {
    if (!doc || doc.getElementById('techChartsCss')) return;
    var s = doc.createElement('style');
    s.id = 'techChartsCss';
    s.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(s);
  }

  function mnum(v) { return String(v).replace('-', '−'); }
  function fx(v, d) { return mnum(v.toFixed(d)); }
  function tickTxt(v) { return mnum(Math.abs(v % 1) < 0.05 ? v.toFixed(0) : v.toFixed(1)); }
  function tail(a, n) { return a.length > n ? a.slice(a.length - n) : a.slice(); }

  function niceTicks(lo, hi, count) {
    var span = hi - lo;
    if (!(span > 0)) return [lo];
    for (var c = count; c >= 2; c--) {
      var raw = span / c;
      var mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
      var nrm = raw / mag;
      var step = (nrm <= 1 ? 1 : nrm <= 2 ? 2 : nrm <= 2.5 ? 2.5 : nrm <= 5 ? 5 : 10) * mag;
      var out = [];
      for (var v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) {
        out.push(Math.round(v * 1e6) / 1e6);
      }
      if (out.length <= 5) return out;
    }
    return [];
  }

  function xAt(i, n) { return n < 2 ? PL + PW : PL + (i / (n - 1)) * PW; }

  /* 카드 1개 생성. spec: {name, kind:'disp'|'mdd', dates, vals, color} */
  function buildCard(doc, spec) {
    var card = doc.createElement('div');
    card.className = 'tc-card';
    var isDisp = spec.kind === 'disp';
    var head = doc.createElement('div');
    head.className = 'tc-cardhead';
    var t = doc.createElement('span');
    t.className = 'tc-t';
    t.innerHTML = LABEL[spec.name] + ' · ' + (isDisp
      ? '50일 이격도 추이'
      : '고점대비 낙폭(MDD) <em>· 52주 고점 기준</em>');
    head.appendChild(t);

    var vals = spec.vals, dates = spec.dates, n = vals.length;
    var last = n ? vals[n - 1] : 0;
    var vEl = doc.createElement('span');
    vEl.className = 'tc-v';
    vEl.style.color = spec.color;
    vEl.textContent = n ? (isDisp ? fx(last, 1) : fx(last, 1) + '%') : '—';
    head.appendChild(vEl);
    card.appendChild(head);

    if (n < 2) {
      var e = doc.createElement('div');
      e.className = 'tc-empty';
      e.textContent = '표시할 데이터가 없습니다.';
      card.appendChild(e);
      return card;
    }

    // y 도메인
    var dmin = Math.min.apply(null, vals), dmax = Math.max.apply(null, vals);
    var lo, hi, refs;
    if (isDisp) {
      lo = Math.min(dmin, 105);
      hi = Math.max(dmax, 105);
      if (dmax >= 118) hi = Math.max(hi, 130);
      refs = [
        { v: 130, c: '#ff4d5e', txt: '130 과열' },
        { v: 105, c: '#4ea1ff', txt: '105 과열해소' }
      ];
    } else {
      lo = Math.min(dmin, -16);
      hi = Math.max(dmax, 1);
      refs = [
        { v: -10, c: '#ff8a3d', txt: '−10 조정' },
        { v: -15, c: '#ff4d5e', txt: '−15 경계' }
      ];
    }
    var pad = (hi - lo) * 0.03 || 1;
    lo -= pad; hi += pad;
    var base = isDisp ? 100 : 0;

    function Y(v) { return PT + (1 - (v - lo) / (hi - lo)) * PH; }
    function X(i) { return xAt(i, n); }

    var s = [];
    s.push('<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' +
      LABEL[spec.name] + ' ' + (isDisp ? '이격도' : 'MDD') + ' 추이">');

    var lastY = Y(last);

    // 가로 그리드 + 우측 y 라벨
    var ticks = niceTicks(lo, hi, 5);
    for (var ti = 0; ti < ticks.length; ti++) {
      var ty = Y(ticks[ti]);
      s.push('<line x1="' + PL + '" y1="' + ty.toFixed(1) + '" x2="' + (PL + PW) + '" y2="' + ty.toFixed(1) +
        '" stroke="var(--line,#2a2f3a)" stroke-width="1" opacity=".55"/>');
      if (Math.abs(ty - lastY) > 9) {
        s.push('<text x="' + (PL + PW + 5) + '" y="' + (ty + 3.2).toFixed(1) + '" fill="' + DIM +
          '" font-size="10" style="font-family:' + MONO + '">' + tickTxt(ticks[ti]) + '</text>');
      }
    }

    // 기준선(100 / 0)
    if (base > lo && base < hi) {
      s.push('<line x1="' + PL + '" y1="' + Y(base).toFixed(1) + '" x2="' + (PL + PW) + '" y2="' +
        Y(base).toFixed(1) + '" stroke="' + DIM + '" stroke-width="1" opacity=".25"/>');
    }

    // 점선 기준선 + 우측끝 라벨
    for (var ri = 0; ri < refs.length; ri++) {
      var rf = refs[ri];
      if (rf.v <= lo || rf.v >= hi) continue;
      var ry = Y(rf.v);
      s.push('<line x1="' + PL + '" y1="' + ry.toFixed(1) + '" x2="' + (PL + PW) + '" y2="' + ry.toFixed(1) +
        '" stroke="' + rf.c + '" stroke-width="1" stroke-dasharray="3 3" opacity=".8"/>');
      s.push('<text x="' + (PL + PW - 4) + '" y="' + (ry - 3.5).toFixed(1) + '" text-anchor="end" fill="' +
        rf.c + '" font-size="9.5" opacity=".95">' + rf.txt + '</text>');
    }

    // 라인
    var d = '';
    for (var i = 0; i < n; i++) {
      d += (i ? 'L' : 'M') + X(i).toFixed(2) + ' ' + Y(vals[i]).toFixed(2);
    }
    s.push('<path d="' + d + '" fill="none" stroke="' + spec.color +
      '" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>');

    // x축 라벨 (YYYY-MM)
    var xn = n >= 5 ? 5 : 4;
    for (var xi = 0; xi < xn; xi++) {
      var idx = Math.round(xi * (n - 1) / (xn - 1));
      var anc = xi === 0 ? 'start' : (xi === xn - 1 ? 'end' : 'middle');
      s.push('<text x="' + X(idx).toFixed(1) + '" y="' + (H - 5) + '" text-anchor="' + anc + '" fill="' + DIM +
        '" font-size="10" style="font-family:' + MONO + '">' + dates[idx].slice(0, 7) + '</text>');
    }

    // 마지막 점 + 현재값
    s.push('<circle cx="' + X(n - 1).toFixed(2) + '" cy="' + lastY.toFixed(2) + '" r="3" fill="' + spec.color + '"/>');
    s.push('<text x="' + (X(n - 1) + 5).toFixed(1) + '" y="' + (lastY + 3.4).toFixed(1) + '" fill="' + spec.color +
      '" font-size="9.5" font-weight="700" style="font-family:' + MONO + '">' +
      (isDisp ? fx(last, 1) : fx(last, 1) + '%') + '</text>');

    // 호버 가이드
    s.push('<g class="tc-guide"><line class="tc-gl" x1="0" y1="' + PT + '" x2="0" y2="' + (PT + PH) +
      '" stroke="' + DIM + '" stroke-width="1" stroke-dasharray="2 2" opacity=".7"/>' +
      '<circle class="tc-gd" cx="0" cy="0" r="2.8" fill="' + spec.color +
      '" stroke="var(--panel,#12161d)" stroke-width="1.2"/></g>');
    s.push('</svg>');

    var plot = doc.createElement('div');
    plot.className = 'tc-plot';
    plot.innerHTML = s.join('');
    var tip = doc.createElement('div');
    tip.className = 'tc-tip';
    plot.appendChild(tip);
    card.appendChild(plot);

    var svg = plot.querySelector('svg');
    var gl = plot.querySelector('.tc-gl');
    var gd = plot.querySelector('.tc-gd');

    function move(ev) {
      var r = svg.getBoundingClientRect();
      if (!r.width) return;
      var px = (ev.clientX - r.left) / r.width * W;
      var i = Math.round((px - PL) / PW * (n - 1));
      if (i < 0) i = 0; else if (i > n - 1) i = n - 1;
      var gx = X(i), gy = Y(vals[i]);
      gl.setAttribute('x1', gx); gl.setAttribute('x2', gx);
      gd.setAttribute('cx', gx); gd.setAttribute('cy', gy);
      tip.textContent = dates[i] + ' · ' + (isDisp ? fx(vals[i], 1) : fx(vals[i], 1) + '%');
      var lp = gx / W * r.width;
      tip.style.left = Math.max(34, Math.min(r.width - 34, lp)) + 'px';
      plot.className = 'tc-plot on';
    }
    function leave() { plot.className = 'tc-plot'; }
    svg.addEventListener('mousemove', move);
    svg.addEventListener('mouseleave', leave);
    plot.addEventListener('mouseleave', leave);

    return card;
  }

  function renderGrid(doc, grid, data, period) {
    var take = DEFAULT_PERIOD;
    for (var pi = 0; pi < PERIODS.length; pi++) if (PERIODS[pi].k === period) take = PERIODS[pi].n;
    if (typeof take !== 'number') take = 252;

    while (grid.firstChild) grid.removeChild(grid.firstChild);

    var any = false;
    for (var oi = 0; oi < ORDER.length; oi++) {
      var name = ORDER[oi];
      var idx = data && data[name];
      var ser = idx && idx.series;
      if (!ser || !ser.dates || !ser.dates.length) continue;
      var m = Math.min(ser.dates.length, ser.disp50.length, ser.mdd52.length);
      var dates = tail(ser.dates.slice(0, m), take);
      var col = doc.createElement('div');
      col.className = 'tc-col';
      col.appendChild(buildCard(doc, {
        name: name, kind: 'disp', dates: dates,
        vals: tail(ser.disp50.slice(0, m), take), color: COLOR[name]
      }));
      col.appendChild(buildCard(doc, {
        name: name, kind: 'mdd', dates: dates,
        vals: tail(ser.mdd52.slice(0, m), take), color: COLOR[name]
      }));
      grid.appendChild(col);
      any = true;
    }
    if (!any) {
      var e = doc.createElement('div');
      e.className = 'tc-empty';
      e.textContent = '시계열 데이터(series)가 없습니다.';
      grid.appendChild(e);
    }
  }

  function renderTechCharts(el, data) {
    if (!el || !el.ownerDocument) return;
    var doc = el.ownerDocument;
    ensureCss(doc);
    while (el.firstChild) el.removeChild(el.firstChild);

    var wrap = doc.createElement('div');
    wrap.className = 'tc-wrap';

    var head = doc.createElement('div');
    head.className = 'tc-head';
    var title = doc.createElement('div');
    title.className = 'tc-title';
    title.textContent = '📊 이격도·MDD 추이 — KOSPI vs NASDAQ';
    head.appendChild(title);

    var chips = doc.createElement('div');
    chips.className = 'tc-chips';
    var grid = doc.createElement('div');
    grid.className = 'tc-grid';

    var btns = [];
    function select(k) {
      for (var i = 0; i < btns.length; i++) {
        btns[i].className = btns[i].getAttribute('data-k') === k ? 'tc-chip on' : 'tc-chip';
      }
      renderGrid(doc, grid, data, k);
    }
    for (var p = 0; p < PERIODS.length; p++) {
      (function (key) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.className = 'tc-chip';
        b.setAttribute('data-k', key);
        b.textContent = key;
        b.addEventListener('click', function () { select(key); });
        chips.appendChild(b);
        btns.push(b);
      })(PERIODS[p].k);
    }
    head.appendChild(chips);
    wrap.appendChild(head);
    wrap.appendChild(grid);
    el.appendChild(wrap);

    select(DEFAULT_PERIOD);
    return el;
  }

  if (typeof window !== 'undefined') window.renderTechCharts = renderTechCharts;
  else if (typeof globalThis !== 'undefined') globalThis.renderTechCharts = renderTechCharts;
  if (typeof module !== 'undefined' && module.exports) module.exports = renderTechCharts;
})();
