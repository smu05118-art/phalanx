/* deriv_charts.js — 파생·수급 지표 차트 (의존성 0, 순수 SVG)
 * 전역: window.renderDeriv(el, data)
 *   data = deriv_kr.json 전체 객체
 *   { _src:{...}, vkospi:{"YYYY-MM-DD":62.41},
 *     opt_net:{"YYYY-MM-DD":{"<투자자>":{"call":억원,"put":억원}}},
 *     fut_net:{"YYYY-MM-DD":{"<투자자>":억원}}, oi:{...}, asof:"..." }
 * 로드 시 부작용 없음(함수 정의만). 외부 라이브러리·fetch 사용 안 함.
 * 스타일 문법은 tech_charts.js(파놉테스 기존 렌더러)와 동일.
 */
(function () {
  'use strict';

  var PERIODS = [
    { k: '1M', n: 21 }, { k: '3M', n: 63 }, { k: '6M', n: 126 },
    { k: '1Y', n: 252 }, { k: '3Y', n: 756 }
  ];
  var DEFAULT_PERIOD = '6M';
  var FLOW_MAX = 120;   // 수급 차트는 최대 120거래일(가독성)
  var CUM_N = 20;       // "최근 N일 누적" 기준

  var VK_STABLE = 60;   // 안정화 임계
  var VK_HI = 75;       // 극단 공포
  var VK_LO = 40;       // 정상권 복귀

  var C = {
    vk: '#ffb545',
    call: '#ff4d5e',
    put: '#3d63d6',
    frgn: '#ff4d5e',
    trust: '#59d0a8',
    fin: '#4ea1ff',
    alt: ['#c58aff', '#f0a6c0', '#7ad0e6', '#e0c15a', '#8a93a3']
  };

  var MONO = 'var(--mono,ui-monospace,SFMono-Regular,Menlo,monospace)';
  var DIM = '#8a93a3';

  var CSS = [
    '.dv-wrap{display:flex;flex-direction:column;gap:12px}',
    '.dv-head{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}',
    '.dv-title{font-size:14px;font-weight:750;letter-spacing:-.01em}',
    '.dv-asof{font-family:' + MONO + ';font-size:10.5px;color:var(--dim,#8a93a3);font-weight:600}',
    '.dv-chips{display:flex;gap:6px}',
    '.dv-chip{font:inherit;font-size:11.5px;line-height:1.5;padding:3px 9px;border:1px solid var(--line,#2a2f3a);',
    'border-radius:999px;background:transparent;color:var(--dim,#8a93a3);cursor:pointer;transition:all .12s}',
    '.dv-chip:hover{border-color:rgba(43,192,212,.5);color:#2bc0d4}',
    '.dv-chip.on{background:rgba(43,192,212,.14);color:#2bc0d4;border-color:rgba(43,192,212,.45)}',
    '.dv-card{background:var(--panel,#12161d);border:1px solid var(--line,#2a2f3a);border-radius:13px;padding:14px 16px}',
    '.dv-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}',
    '@media (max-width:920px){.dv-grid{grid-template-columns:1fr}}',
    '.dv-cardhead{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:4px}',
    '.dv-t{font-size:12px;font-weight:650}',
    '.dv-t em{font-style:normal;color:var(--dim,#8a93a3);font-weight:550}',
    '.dv-v{font-family:' + MONO + ';font-size:12.5px;font-weight:700;white-space:nowrap}',
    '.dv-plot{position:relative}',
    '.dv-plot svg{display:block;width:100%;height:auto;overflow:visible}',
    '.dv-guide{opacity:0}',
    '.dv-plot.on .dv-guide{opacity:1}',
    '.dv-tip{position:absolute;top:2px;transform:translateX(-50%);pointer-events:none;opacity:0;',
    'background:rgba(10,12,16,.92);border:1px solid var(--line,#2a2f3a);border-radius:6px;padding:3px 7px;',
    'font-family:' + MONO + ';font-size:10.5px;color:#e6e9ef;white-space:nowrap;z-index:3;transition:opacity .1s}',
    '.dv-plot.on .dv-tip{opacity:1}',
    '.dv-empty{font-size:11.5px;color:var(--dim,#8a93a3);padding:10px 0}',
    '.dv-legend{display:flex;gap:12px;flex-wrap:wrap;margin-top:6px}',
    '.dv-lg{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--dim,#8a93a3)}',
    '.dv-lgd{width:11px;height:2.5px;border-radius:2px;flex:none}',
    '.dv-lg b{font-family:' + MONO + ';font-weight:700;font-size:10.5px}',
    '.dv-badges{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}',
    '.dv-badge{font-size:11px;font-weight:700;padding:3px 9px;border-radius:999px;border:1px solid;line-height:1.5}',
    '.dv-note{font-size:11.5px;line-height:1.75;color:#cfd5e0;margin-top:8px}',
    '.dv-note b{color:#e6e9ef}',
    '.dv-foot{font-size:10.5px;line-height:1.7;color:var(--dim,#8a93a3);margin-top:8px;',
    'border-top:1px dashed var(--line,#2a2f3a);padding-top:8px}',
    '.dv-key{background:var(--panel,#12161d);border:1px solid rgba(43,192,212,.35);border-radius:13px;padding:13px 16px}',
    '.dv-keyt{font-size:12.5px;font-weight:750;color:#2bc0d4;margin-bottom:8px}',
    '.dv-keyrow{display:grid;grid-template-columns:1fr 1fr;gap:10px}',
    '@media (max-width:760px){.dv-keyrow{grid-template-columns:1fr}}',
    '.dv-keyitem{border:1px solid var(--line,#2a2f3a);border-radius:10px;padding:9px 11px;display:flex;gap:9px;align-items:flex-start}',
    '.dv-ox{font-family:' + MONO + ';font-size:17px;font-weight:800;line-height:1.15;flex:none}',
    '.dv-kq{font-size:11.5px;font-weight:700;color:#e6e9ef}',
    '.dv-kr{font-family:' + MONO + ';font-size:10.5px;color:var(--dim,#8a93a3);margin-top:2px;line-height:1.6}',
    '.dv-src{font-size:10px;color:var(--dim,#8a93a3);font-family:' + MONO + '}'
  ].join('');

  function ensureCss(doc) {
    if (!doc || doc.getElementById('derivChartsCss')) return;
    var s = doc.createElement('style');
    s.id = 'derivChartsCss';
    s.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(s);
  }

  /* ── 포맷/유틸 ─────────────────────────────────────────── */
  function mnum(v) { return String(v).replace('-', '−'); }
  function fx(v, d) { return mnum(v.toFixed(d)); }
  function tickTxt(v) { return mnum(Math.abs(v % 1) < 0.05 ? v.toFixed(0) : v.toFixed(1)); }
  function tail(a, n) { return a.length > n ? a.slice(a.length - n) : a.slice(); }
  function comma(v) {
    var s = String(Math.abs(Math.round(v))), o = '', c = 0;
    for (var i = s.length - 1; i >= 0; i--) {
      o = s.charAt(i) + o;
      if (++c % 3 === 0 && i > 0) o = ',' + o;
    }
    return (v < 0 ? '−' : '') + o;
  }
  function signed(v) { return (v > 0 ? '+' : '') + comma(v); }
  function sum(a) { var t = 0; for (var i = 0; i < a.length; i++) t += a[i] || 0; return t; }
  function isNum(v) { return typeof v === 'number' && isFinite(v); }

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

  /* ── 투자자명 정규화 ────────────────────────────────────── */
  var ALIAS = {
    '외국인투자자': '외국인', '외국인계': '외국인', '외인': '외국인',
    '기타외국인': '기타외국인',
    '기관': '기관계', '기관합계': '기관계', '기관투자자': '기관계',
    '투자신탁': '투신', '자산운용': '투신', '집합투자': '투신',
    '증권': '금융투자', '금융투자업': '금융투자',
    '연기금등': '연기금', '연기금 등': '연기금',
    '개인투자자': '개인'
  };
  // 합산(중복 집계) 항목 — 카운터파티 랭킹에서 제외
  var AGG = { '기관계': 1, '전체': 1, '합계': 1, '기타계': 1, '전체합계': 1 };

  function canon(k) {
    var s = String(k).replace(/\s+/g, '');
    return ALIAS[s] || s;
  }

  /* ── 범용 라인 플롯 ─────────────────────────────────────── */
  /* spec: {w,h,dates,series:[{name,color,vals}],refs:[{v,c,txt}],base,unit,dec,lastLabel} */
  function buildPlot(doc, spec) {
    var W = spec.w || 520, H = spec.h || 176;
    var PL = 10, PR = spec.pr || 46, PT = 16, PB = 22;
    var PW = W - PL - PR, PH = H - PT - PB;
    var dates = spec.dates, n = dates.length;
    var ser = spec.series, dec = spec.dec == null ? 1 : spec.dec;

    var plot = doc.createElement('div');
    plot.className = 'dv-plot';
    if (n < 2) {
      var e = doc.createElement('div');
      e.className = 'dv-empty';
      e.textContent = '표시할 데이터가 없습니다.';
      plot.appendChild(e);
      return plot;
    }

    var dmin = Infinity, dmax = -Infinity, si, i;
    for (si = 0; si < ser.length; si++) {
      for (i = 0; i < ser[si].vals.length; i++) {
        var v = ser[si].vals[i];
        if (!isNum(v)) continue;
        if (v < dmin) dmin = v;
        if (v > dmax) dmax = v;
      }
    }
    if (!isFinite(dmin)) { dmin = 0; dmax = 1; }
    var lo = dmin, hi = dmax;
    var refs = spec.refs || [];
    for (i = 0; i < refs.length; i++) {
      if (refs[i].force) { lo = Math.min(lo, refs[i].v); hi = Math.max(hi, refs[i].v); }
    }
    if (spec.base != null) { lo = Math.min(lo, spec.base); hi = Math.max(hi, spec.base); }
    var pad = (hi - lo) * 0.06 || 1;
    lo -= pad; hi += pad;

    function Y(val) { return PT + (1 - (val - lo) / (hi - lo)) * PH; }
    function X(idx) { return n < 2 ? PL + PW : PL + (idx / (n - 1)) * PW; }

    var s = [];
    s.push('<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + (spec.aria || '차트') + '">');

    var lastY = [];
    for (si = 0; si < ser.length; si++) {
      var lv = null;
      for (i = ser[si].vals.length - 1; i >= 0; i--) { if (isNum(ser[si].vals[i])) { lv = ser[si].vals[i]; break; } }
      lastY.push(lv == null ? null : Y(lv));
    }
    function nearLast(y) {
      for (var q = 0; q < lastY.length; q++) if (lastY[q] != null && Math.abs(lastY[q] - y) < 9) return true;
      return false;
    }

    // 가로 그리드 + 우측 y 라벨
    var ticks = niceTicks(lo, hi, 5);
    for (var ti = 0; ti < ticks.length; ti++) {
      var ty = Y(ticks[ti]);
      s.push('<line x1="' + PL + '" y1="' + ty.toFixed(1) + '" x2="' + (PL + PW) + '" y2="' + ty.toFixed(1) +
        '" stroke="var(--line,#2a2f3a)" stroke-width="1" opacity=".55"/>');
      if (!nearLast(ty)) {
        s.push('<text x="' + (PL + PW + 5) + '" y="' + (ty + 3.2).toFixed(1) + '" fill="' + DIM +
          '" font-size="10" style="font-family:' + MONO + '">' + tickTxt(ticks[ti]) + '</text>');
      }
    }

    // 기준선(0선 등)
    if (spec.base != null && spec.base > lo && spec.base < hi) {
      s.push('<line x1="' + PL + '" y1="' + Y(spec.base).toFixed(1) + '" x2="' + (PL + PW) + '" y2="' +
        Y(spec.base).toFixed(1) + '" stroke="' + DIM + '" stroke-width="1.1" opacity=".45"/>');
    }

    // 점선 기준선 + 우측끝 라벨
    for (var ri = 0; ri < refs.length; ri++) {
      var rf = refs[ri];
      if (rf.v <= lo || rf.v >= hi) continue;
      var ry = Y(rf.v);
      s.push('<line x1="' + PL + '" y1="' + ry.toFixed(1) + '" x2="' + (PL + PW) + '" y2="' + ry.toFixed(1) +
        '" stroke="' + rf.c + '" stroke-width="' + (rf.w || 1) + '" stroke-dasharray="' + (rf.dash || '3 3') +
        '" opacity="' + (rf.o || 0.8) + '"/>');
      if (rf.txt) {
        s.push('<text x="' + (PL + PW - 4) + '" y="' + (ry - 3.5).toFixed(1) + '" text-anchor="end" fill="' +
          rf.c + '" font-size="9.5" opacity=".95">' + rf.txt + '</text>');
      }
    }

    // 라인
    for (si = 0; si < ser.length; si++) {
      var vals = ser[si].vals, d = '', pen = false;
      for (i = 0; i < n; i++) {
        var vv = vals[i];
        if (!isNum(vv)) { pen = false; continue; }
        d += (pen ? 'L' : 'M') + X(i).toFixed(2) + ' ' + Y(vv).toFixed(2);
        pen = true;
      }
      if (d) {
        s.push('<path d="' + d + '" fill="none" stroke="' + ser[si].color +
          '" stroke-width="' + (ser[si].w || 1.6) + '" stroke-linejoin="round" stroke-linecap="round"/>');
      }
    }

    // x축 라벨 — 3개월 이하 구간은 MM-DD, 그 이상은 YYYY-MM
    var xn = n >= 5 ? 5 : 4;
    var short = n <= 70;
    for (var xi = 0; xi < xn; xi++) {
      var idx = Math.round(xi * (n - 1) / (xn - 1));
      var anc = xi === 0 ? 'start' : (xi === xn - 1 ? 'end' : 'middle');
      s.push('<text x="' + X(idx).toFixed(1) + '" y="' + (H - 5) + '" text-anchor="' + anc + '" fill="' + DIM +
        '" font-size="10" style="font-family:' + MONO + '">' +
        (short ? dates[idx].slice(5) : dates[idx].slice(0, 7)) + '</text>');
    }

    // 마지막 점 + 값 라벨
    for (si = 0; si < ser.length; si++) {
      if (lastY[si] == null) continue;
      var lval = null;
      for (i = ser[si].vals.length - 1; i >= 0; i--) { if (isNum(ser[si].vals[i])) { lval = ser[si].vals[i]; break; } }
      s.push('<circle cx="' + X(n - 1).toFixed(2) + '" cy="' + lastY[si].toFixed(2) + '" r="3" fill="' + ser[si].color + '"/>');
      if (spec.lastLabel !== false) {
        s.push('<text x="' + (X(n - 1) + 5).toFixed(1) + '" y="' + (lastY[si] + 3.4).toFixed(1) + '" fill="' +
          ser[si].color + '" font-size="9.5" font-weight="700" style="font-family:' + MONO + '">' +
          (spec.money ? signed(lval) : fx(lval, dec)) + '</text>');
      }
    }

    // 호버 가이드
    var g = ['<g class="dv-guide"><line class="dv-gl" x1="0" y1="' + PT + '" x2="0" y2="' + (PT + PH) +
      '" stroke="' + DIM + '" stroke-width="1" stroke-dasharray="2 2" opacity=".7"/>'];
    for (si = 0; si < ser.length; si++) {
      g.push('<circle class="dv-gd" cx="0" cy="0" r="2.8" fill="' + ser[si].color +
        '" stroke="var(--panel,#12161d)" stroke-width="1.2"/>');
    }
    g.push('</g>');
    s.push(g.join(''));
    s.push('</svg>');

    plot.innerHTML = s.join('');
    var tip = doc.createElement('div');
    tip.className = 'dv-tip';
    plot.appendChild(tip);

    var svg = plot.querySelector('svg');
    var gl = plot.querySelector('.dv-gl');
    var gds = plot.querySelectorAll('.dv-gd');

    function move(ev) {
      var r = svg.getBoundingClientRect();
      if (!r.width) return;
      var px = (ev.clientX - r.left) / r.width * W;
      var idx = Math.round((px - PL) / PW * (n - 1));
      if (idx < 0) idx = 0; else if (idx > n - 1) idx = n - 1;
      var gx = X(idx);
      gl.setAttribute('x1', gx); gl.setAttribute('x2', gx);
      var txt = dates[idx];
      for (var q = 0; q < ser.length; q++) {
        var val = ser[q].vals[idx];
        if (isNum(val)) {
          gds[q].setAttribute('cx', gx);
          gds[q].setAttribute('cy', Y(val));
          gds[q].setAttribute('opacity', '1');
          txt += ' · ' + (ser.length > 1 ? ser[q].name + ' ' : '') +
            (spec.money ? signed(val) : fx(val, dec)) + (spec.unit || '');
        } else {
          gds[q].setAttribute('opacity', '0');
        }
      }
      tip.textContent = txt;
      var lp = gx / W * r.width;
      tip.style.left = Math.max(60, Math.min(r.width - 60, lp)) + 'px';
      plot.className = 'dv-plot on';
    }
    function leave() { plot.className = 'dv-plot'; }
    svg.addEventListener('mousemove', move);
    svg.addEventListener('mouseleave', leave);
    plot.addEventListener('mouseleave', leave);

    return plot;
  }

  /* ── 데이터 정리 ────────────────────────────────────────── */
  function seriesFromMap(map) {
    var dates = [], vals = [], k;
    if (!map) return { dates: dates, vals: vals };
    var keys = [];
    for (k in map) if (Object.prototype.hasOwnProperty.call(map, k)) keys.push(k);
    keys.sort();
    for (var i = 0; i < keys.length; i++) {
      var v = map[keys[i]];
      if (typeof v === 'string') v = parseFloat(v);
      if (!isNum(v)) continue;
      dates.push(keys[i]);
      vals.push(v);
    }
    return { dates: dates, vals: vals };
  }

  /* opt_net → {dates, inv:{name:{call:[],put:[]}}, names:[]} */
  function collectOpt(optNet) {
    var dates = [], k, i, j;
    if (!optNet) return { dates: [], inv: {}, names: [] };
    for (k in optNet) if (Object.prototype.hasOwnProperty.call(optNet, k)) dates.push(k);
    dates.sort();
    var inv = {}, names = [];
    for (i = 0; i < dates.length; i++) {
      var row = optNet[dates[i]] || {};
      for (k in row) {
        if (!Object.prototype.hasOwnProperty.call(row, k)) continue;
        var nm = canon(k);
        if (!inv[nm]) {
          inv[nm] = { call: [], put: [] };
          for (j = 0; j < i; j++) { inv[nm].call.push(null); inv[nm].put.push(null); }
          names.push(nm);
        }
      }
      for (j = 0; j < names.length; j++) {
        var cell = null, kk;
        for (kk in row) {
          if (Object.prototype.hasOwnProperty.call(row, kk) && canon(kk) === names[j]) { cell = row[kk]; break; }
        }
        inv[names[j]].call.push(cell && isNum(+cell.call) ? +cell.call : null);
        inv[names[j]].put.push(cell && isNum(+cell.put) ? +cell.put : null);
      }
    }
    return { dates: dates, inv: inv, names: names };
  }

  /* fut_net → {dates, inv:{name:[]}} */
  function collectFut(futNet) {
    var dates = [], k, i, j;
    if (!futNet) return { dates: [], inv: {}, names: [] };
    for (k in futNet) if (Object.prototype.hasOwnProperty.call(futNet, k)) dates.push(k);
    dates.sort();
    var inv = {}, names = [];
    for (i = 0; i < dates.length; i++) {
      var row = futNet[dates[i]] || {};
      for (k in row) {
        if (!Object.prototype.hasOwnProperty.call(row, k)) continue;
        var nm = canon(k);
        if (!inv[nm]) {
          inv[nm] = [];
          for (j = 0; j < i; j++) inv[nm].push(null);
          names.push(nm);
        }
      }
      for (j = 0; j < names.length; j++) {
        var cell = null, kk;
        for (kk in row) {
          if (Object.prototype.hasOwnProperty.call(row, kk) && canon(kk) === names[j]) { cell = row[kk]; break; }
        }
        inv[names[j]].push(isNum(+cell) ? +cell : null);
      }
    }
    return { dates: dates, inv: inv, names: names };
  }

  /* ── 해석 엔진 ──────────────────────────────────────────── */
  function analyzeVk(dates, vals) {
    var n = vals.length;
    if (!n) return null;
    var last = vals[n - 1], lastDate = dates[n - 1];
    var w = tail(vals, 20), wd = tail(dates, 20);
    var mx = -Infinity, mxi = 0;
    for (var i = 0; i < w.length; i++) if (w[i] > mx) { mx = w[i]; mxi = i; }
    var drop = mx > 0 ? (last - mx) / mx * 100 : 0;
    // 5일 하락추세: 5거래일 전 대비 하락 + 최근 5일 변화 중 하락일 3일 이상
    var dn = 0, cmp5 = n > 5 ? vals[n - 6] : vals[0];
    for (var j = Math.max(1, n - 5); j < n; j++) if (vals[j] < vals[j - 1]) dn++;
    var trendDown = last < cmp5 && dn >= 3;
    var peakout = drop <= -15 && trendDown;
    return {
      last: last, lastDate: lastDate,
      max20: mx, max20Date: wd[mxi] || lastDate,
      drop: drop, dn5: dn, cmp5: cmp5, trendDown: trendDown,
      peakout: peakout,
      stable: last <= VK_STABLE,
      daily: last / Math.sqrt(252)
    };
  }

  function analyzeFlow(opt, cumN) {
    if (!opt.dates.length || !opt.inv['외국인']) return null;
    var f = opt.inv['외국인'];
    var call = sum(tail(f.call, cumN)), put = sum(tail(f.put, cumN));
    var lastCall = null, lastPut = null, i;
    for (i = f.call.length - 1; i >= 0; i--) if (isNum(f.call[i])) { lastCall = f.call[i]; break; }
    for (i = f.put.length - 1; i >= 0; i--) if (isNum(f.put[i])) { lastPut = f.put[i]; break; }

    // 카운터파티: 같은 기간 콜 순매도 1위(합산 항목 제외)
    var cp = null, cpVal = 0;
    for (var q = 0; q < opt.names.length; q++) {
      var nm = opt.names[q];
      if (nm === '외국인' || AGG[nm]) continue;
      var v = sum(tail(opt.inv[nm].call, cumN));
      if (v < cpVal) { cpVal = v; cp = nm; }
    }
    return {
      n: Math.min(cumN, opt.dates.length),
      call: call, put: put,
      lastCall: lastCall, lastPut: lastPut,
      longVol: call > 0 && put > 0,
      cp: cp, cpVal: cpVal,
      from: tail(opt.dates, cumN)[0], to: opt.dates[opt.dates.length - 1]
    };
  }

  function analyzeFut(fut, cumN) {
    if (!fut.dates.length || !fut.inv['외국인']) return null;
    var arr = tail(fut.inv['외국인'], cumN);
    return { n: arr.length, sum: sum(arr), to: fut.dates[fut.dates.length - 1] };
  }

  /* ── 조립 블록 ──────────────────────────────────────────── */
  function el(doc, cls, txt) {
    var d = doc.createElement('div');
    if (cls) d.className = cls;
    if (txt != null) d.textContent = txt;
    return d;
  }

  function badge(doc, txt, color) {
    var b = doc.createElement('span');
    b.className = 'dv-badge';
    b.textContent = txt;
    b.style.color = color;
    b.style.borderColor = color;
    b.style.background = 'transparent';
    return b;
  }

  function legend(doc, items) {
    var w = el(doc, 'dv-legend');
    for (var i = 0; i < items.length; i++) {
      var g = el(doc, 'dv-lg');
      var d = el(doc, 'dv-lgd');
      d.style.background = items[i].color;
      g.appendChild(d);
      var s = doc.createElement('span');
      s.textContent = items[i].name;
      g.appendChild(s);
      if (items[i].note) {
        var b = doc.createElement('b');
        b.style.color = items[i].color;
        b.textContent = items[i].note;
        g.appendChild(b);
      }
      w.appendChild(g);
    }
    return w;
  }

  function cardHead(doc, titleHtml, valueTxt, valueColor) {
    var h = el(doc, 'dv-cardhead');
    var t = doc.createElement('span');
    t.className = 'dv-t';
    t.innerHTML = titleHtml;
    h.appendChild(t);
    var v = doc.createElement('span');
    v.className = 'dv-v';
    v.textContent = valueTxt;
    if (valueColor) v.style.color = valueColor;
    h.appendChild(v);
    return h;
  }

  /* ① 지금 가장 중요한 2가지 */
  function buildKeyBox(doc, a) {
    var box = el(doc, 'dv-key');
    box.appendChild(el(doc, 'dv-keyt', '🎯 지금 가장 중요한 2가지'));
    var row = el(doc, 'dv-keyrow');

    function item(q, ok, reason) {
      var it = el(doc, 'dv-keyitem');
      var ox = el(doc, 'dv-ox', ok ? 'O' : 'X');
      ox.style.color = ok ? '#59d0a8' : '#ff4d5e';
      it.appendChild(ox);
      var body = el(doc, '');
      body.appendChild(el(doc, 'dv-kq', q));
      body.appendChild(el(doc, 'dv-kr', reason));
      it.appendChild(body);
      return it;
    }

    if (!a) {
      box.appendChild(el(doc, 'dv-empty', 'VKOSPI 데이터가 없어 판정할 수 없습니다.'));
      return box;
    }
    row.appendChild(item(
      '① VKOSPI 피크아웃 진행 중인가?',
      a.peakout,
      '20일 최고 ' + fx(a.max20, 2) + '(' + a.max20Date + ') → 현재 ' + fx(a.last, 2) +
      ' · ' + fx(a.drop, 1) + '% (기준 −15%) · 최근 5일 하락 ' + a.dn5 + '/5, 5일전 ' + fx(a.cmp5, 2)
    ));
    row.appendChild(item(
      '② VKOSPI 60 이하 안정화됐나?',
      a.stable,
      '현재 ' + fx(a.last, 2) + ' vs 임계 60 · ' +
      (a.stable ? '60 아래 진입' : '임계 상회 ' + fx(a.last - VK_STABLE, 2) + 'p') +
      ' · 기준일 ' + a.lastDate
    ));
    box.appendChild(row);
    return box;
  }

  /* ② VKOSPI 추이 카드 */
  function buildVkCard(doc, dates, vals, a) {
    var card = el(doc, 'dv-card');
    card.appendChild(cardHead(doc,
      'VKOSPI 추이 <em>· 코스피200 변동성지수 · 기준선 60(안정화 임계)</em>',
      vals.length ? fx(vals[vals.length - 1], 2) : '—', C.vk));
    card.appendChild(buildPlot(doc, {
      w: 1060, h: 230, pr: 54, dates: dates, dec: 2, aria: 'VKOSPI 추이',
      series: [{ name: 'VKOSPI', color: C.vk, vals: vals, w: 1.8 }],
      refs: [
        { v: VK_HI, c: '#ff4d5e', txt: '75 극단 공포' },
        { v: VK_STABLE, c: '#2bc0d4', txt: '60 안정화 임계', w: 1.4, dash: '5 3', o: 0.95, force: true },
        { v: VK_LO, c: '#59d0a8', txt: '40 정상권' }
      ]
    }));

    var bs = el(doc, 'dv-badges');
    if (a) {
      if (a.peakout) bs.appendChild(badge(doc, '⤵ 피크아웃 진행', '#59d0a8'));
      if (a.stable) bs.appendChild(badge(doc, '✅ 60 이하 안정화', '#2bc0d4'));
      if (!a.peakout && !a.stable) bs.appendChild(badge(doc, '⚠ 고변동성 지속', '#ff8a3d'));
      card.appendChild(bs);

      var note = el(doc, 'dv-note');
      note.innerHTML =
        'VKOSPI <b>' + fx(a.last, 2) + '</b> = 향후 30일 예상 변동성 <b>연 ' + fx(a.last, 1) + '%</b> ≈ ' +
        '하루 <b>±' + fx(a.daily, 2) + '%</b> (연 ' + fx(a.last, 1) + '% ÷ √252). ' +
        '20일 최고 ' + fx(a.max20, 2) + ' 대비 <b>' + fx(a.drop, 1) + '%</b>' +
        (a.peakout ? ' — −15% 이상 하락 + 5일 하락추세 조건 충족(피크아웃).'
          : ' — 피크아웃 기준(−15% 하락 & 5일 하락추세) 미충족.');
      card.appendChild(note);
    }
    return card;
  }

  /* ③ 외국인 옵션 순매수(콜 vs 풋) */
  function buildFrgnOptCard(doc, opt, take, fa) {
    var card = el(doc, 'dv-card');
    var f = opt.inv['외국인'];
    var dates = tail(opt.dates, take);
    var head = cardHead(doc,
      '외국인 옵션 순매수 <em>· 콜 vs 풋 (억원)</em>',
      fa ? '최근 ' + fa.n + '일 누적 콜 ' + signed(fa.call) + ' / 풋 ' + signed(fa.put) : '—');
    card.appendChild(head);
    if (!f) {
      card.appendChild(el(doc, 'dv-empty', '투자자별 옵션 순매수 데이터가 없습니다.'));
      return card;
    }
    card.appendChild(buildPlot(doc, {
      w: 520, h: 186, dates: dates, money: true, unit: '억', base: 0, aria: '외국인 옵션 순매수',
      series: [
        { name: '콜', color: C.call, vals: tail(f.call, take) },
        { name: '풋', color: C.put, vals: tail(f.put, take) }
      ]
    }));
    card.appendChild(legend(doc, [
      { name: '콜옵션', color: C.call, note: fa ? signed(fa.call) + '억' : '' },
      { name: '풋옵션', color: C.put, note: fa ? signed(fa.put) + '억' : '' }
    ]));
    var bs = el(doc, 'dv-badges');
    if (fa && fa.longVol) bs.appendChild(badge(doc, '외국인 양매수 = Long Vol', '#c58aff'));
    if (bs.childNodes.length) card.appendChild(bs);
    var note = el(doc, 'dv-note');
    if (fa && fa.longVol) {
      note.innerHTML = '외국인이 최근 ' + fa.n + '거래일 콜(<b>' + signed(fa.call) + '억</b>)·풋(<b>' +
        signed(fa.put) + '억</b>)을 <b>동시 순매수</b> — <b>변동성 확대에 베팅</b>하는 포지션입니다.';
    } else if (fa) {
      note.innerHTML = '최근 ' + fa.n + '거래일 외국인 콜 <b>' + signed(fa.call) + '억</b>, 풋 <b>' +
        signed(fa.put) + '억</b> — 콜·풋 동시 순매수(양매수) 아님, 방향성 베팅 우위.';
    }
    card.appendChild(note);
    return card;
  }

  /* ④ 콜옵션 순매수 주체별 */
  function buildCallByInvCard(doc, opt, take, fa) {
    var card = el(doc, 'dv-card');
    var want = ['외국인', '투신', '금융투자'];
    var cols = { '외국인': C.frgn, '투신': C.trust, '금융투자': C.fin };
    var picked = [], i;
    for (i = 0; i < want.length; i++) if (opt.inv[want[i]]) picked.push(want[i]);
    if (fa && fa.cp && picked.indexOf(fa.cp) < 0) picked.push(fa.cp);
    if (picked.length < 2) {
      for (i = 0; i < opt.names.length && picked.length < 3; i++) {
        if (AGG[opt.names[i]] || picked.indexOf(opt.names[i]) >= 0) continue;
        picked.push(opt.names[i]);
      }
    }
    var dates = tail(opt.dates, take);
    // 색 배정을 먼저 확정해 카드 헤드(카운터파티)와 라인 색을 일치시킨다
    var cmap = {}, ai = 0;
    for (i = 0; i < picked.length; i++) {
      cmap[picked[i]] = cols[picked[i]] || C.alt[ai++ % C.alt.length];
    }
    card.appendChild(cardHead(doc,
      '콜옵션 순매수 주체별 <em>· 카운터파티 관계 (억원)</em>',
      fa && fa.cp ? '카운터파티: ' + fa.cp : '—', fa && fa.cp ? cmap[fa.cp] || C.alt[0] : null));
    if (!picked.length) {
      card.appendChild(el(doc, 'dv-empty', '투자자별 옵션 순매수 데이터가 없습니다.'));
      return card;
    }
    var series = [], lgd = [];
    for (i = 0; i < picked.length; i++) {
      var nm = picked[i];
      var color = cmap[nm];
      var vals = tail(opt.inv[nm].call, take);
      series.push({ name: nm, color: color, vals: vals });
      lgd.push({ name: nm, color: color, note: signed(sum(tail(opt.inv[nm].call, fa ? fa.n : CUM_N))) + '억' });
    }
    card.appendChild(buildPlot(doc, {
      w: 520, h: 186, dates: dates, money: true, unit: '억', base: 0,
      aria: '콜옵션 순매수 주체별', lastLabel: false, series: series
    }));
    card.appendChild(legend(doc, lgd));
    var note = el(doc, 'dv-note');
    if (fa && fa.cp) {
      note.innerHTML = '외국인 콜 순매수의 <b>최대 반대편 주체</b>는 <b>' + fa.cp + '</b> — 같은 기간(' +
        fa.n + '거래일) 콜 <b>' + signed(fa.cpVal) + '억</b>으로 순매도 1위. ' +
        '외국인이 산 콜을 ' + fa.cp + '이(가) 받아낸 구조(합산 항목 제외).';
    } else {
      note.innerHTML = '같은 기간 콜옵션 순매도 우위 주체가 확인되지 않습니다.';
    }
    card.appendChild(note);
    return card;
  }

  function buildFoot(doc, a, fa, fu, src) {
    var f = el(doc, 'dv-foot');
    var lines = [];
    lines.push('※ <b>과거 패턴(고정 각주)</b> — VKOSPI 피크아웃이 확인된 국면에서는 외국인의 <b>선물 매도 포지션 청산</b>이 ' +
      '동반되며 지수 반등이 뒤따르는 경우가 많았습니다(3월말~4월 사례). ' +
      '변동성 피크아웃 → 숏커버 → 현·선물 동반 반등의 순서를 확인하세요.');
    if (fu) {
      lines.push('· 외국인 KOSPI200 선물 최근 ' + fu.n + '거래일 누적 순매수 <b>' + signed(fu.sum) +
        '억</b> (기준일 ' + fu.to + ') — 음수 축소/양전환이 매도 청산 신호.');
    }
    if (a) {
      lines.push('· 변동성 환산: 연 ' + fx(a.last, 1) + '% ≈ 하루 ±' + fx(a.daily, 2) + '% (= ' +
        fx(a.last, 1) + ' ÷ √252). 60 위는 하루 ±' + fx(VK_STABLE / Math.sqrt(252), 2) + '% 이상을 시장이 가격에 반영 중임을 뜻합니다.');
    }
    if (src) lines.push('· 출처: ' + src);
    f.innerHTML = lines.join('<br>');
    return f;
  }

  /* ── 엔트리 ─────────────────────────────────────────────── */
  function renderDeriv(el0, data) {
    if (!el0 || !el0.ownerDocument) return el0;
    var doc = el0.ownerDocument;
    ensureCss(doc);
    while (el0.firstChild) el0.removeChild(el0.firstChild);
    data = data || {};

    var vk = seriesFromMap(data.vkospi);
    var opt = collectOpt(data.opt_net);
    var fut = collectFut(data.fut_net);

    var wrap = el(doc, 'dv-wrap');
    var head = el(doc, 'dv-head');
    var titleBox = el(doc, '');
    var title = el(doc, 'dv-title', '⚡ 파생·수급 — VKOSPI & 투자자별 옵션 순매수');
    titleBox.appendChild(title);
    if (data.asof) titleBox.appendChild(el(doc, 'dv-asof', 'asof ' + String(data.asof).slice(0, 19).replace('T', ' ')));
    head.appendChild(titleBox);

    var chips = el(doc, 'dv-chips');
    var body = el(doc, '');
    body.style.display = 'flex';
    body.style.flexDirection = 'column';
    body.style.gap = '12px';

    var btns = [];
    function render(k) {
      var take = 252, i;
      for (i = 0; i < PERIODS.length; i++) if (PERIODS[i].k === k) take = PERIODS[i].n;
      for (i = 0; i < btns.length; i++) {
        btns[i].className = btns[i].getAttribute('data-k') === k ? 'dv-chip on' : 'dv-chip';
      }
      while (body.firstChild) body.removeChild(body.firstChild);

      var vDates = tail(vk.dates, take), vVals = tail(vk.vals, take);
      var a = analyzeVk(vk.dates, vk.vals);           // 판정은 항상 전체 시계열 기준
      var flowTake = Math.min(take, FLOW_MAX);
      var fa = analyzeFlow(opt, CUM_N);
      var fu = analyzeFut(fut, CUM_N);

      body.appendChild(buildKeyBox(doc, a));
      if (vDates.length) body.appendChild(buildVkCard(doc, vDates, vVals, a));
      else {
        var c0 = el(doc, 'dv-card');
        c0.appendChild(cardHead(doc, 'VKOSPI 추이', '—'));
        c0.appendChild(el(doc, 'dv-empty', 'VKOSPI 데이터가 없습니다.'));
        body.appendChild(c0);
      }

      var grid = el(doc, 'dv-grid');
      grid.appendChild(buildFrgnOptCard(doc, opt, flowTake, fa));
      grid.appendChild(buildCallByInvCard(doc, opt, flowTake, fa));
      body.appendChild(grid);

      var srcTxt = '';
      if (data._src) {
        var parts = [], kk;
        for (kk in data._src) {
          if (!Object.prototype.hasOwnProperty.call(data._src, kk)) continue;
          var sv = data._src[kk];
          parts.push(kk + '=' + (typeof sv === 'string' ? sv : (sv && (sv.name || sv.url || sv.bld)) || 'json'));
        }
        srcTxt = parts.join(' · ');
      }
      body.appendChild(buildFoot(doc, a, fa, fu, srcTxt));
    }

    for (var p = 0; p < PERIODS.length; p++) {
      (function (key) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.className = 'dv-chip';
        b.setAttribute('data-k', key);
        b.textContent = key;
        b.addEventListener('click', function () { render(key); });
        chips.appendChild(b);
        btns.push(b);
      })(PERIODS[p].k);
    }
    head.appendChild(chips);
    wrap.appendChild(head);
    wrap.appendChild(body);
    el0.appendChild(wrap);

    render(DEFAULT_PERIOD);
    return el0;
  }

  if (typeof window !== 'undefined') window.renderDeriv = renderDeriv;
  else if (typeof globalThis !== 'undefined') globalThis.renderDeriv = renderDeriv;
  if (typeof module !== 'undefined' && module.exports) module.exports = renderDeriv;
})();
