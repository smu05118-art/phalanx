/* argus_charts.js — ARGUS 대시보드 렌더러 (의존성 0, 순수 SVG, IIFE)
 * 전역: window.renderARGUS(el, data)   data = data/argus_data.js 의 window.ARGUS
 * 로드 시 부작용 없음(함수 정의만). 외부 라이브러리·fetch 사용 안 함.
 * 섹션: ①체인 스코어보드 ②사냥 시그널 ③스프레드 차트 ④태양광 밸류체인 ⑤유가 데크
 */
(function () {
  'use strict';

  var DIM = '#8a93a3', ACC = '#2bc0d4', UP = '#59d0a8', DOWN = '#ff5e6c', WARN = '#f6c85f';
  var MONO = 'var(--mono,ui-monospace,SFMono-Regular,Menlo,monospace)';
  var PAL = ['#4ea1ff', '#59d0a8', '#f6c85f', '#e07a5f', '#b892ff', '#2bc0d4', '#ff8a3d', '#7ec8e3', '#ff6b9d', '#9ccc65'];

  var CSS = [
    '.ag-wrap{display:flex;flex-direction:column;gap:20px}',
    /* 히어로 */
    '.ag-hero{position:relative;overflow:hidden;background:linear-gradient(135deg,rgba(43,192,212,.13),rgba(78,161,255,.06) 45%,rgba(89,208,168,.09));border:1px solid rgba(43,192,212,.3);border-radius:16px;padding:18px 22px}',
    '.ag-hero h2{font-size:19px;font-weight:850;letter-spacing:-.02em}',
    '.ag-hero .sub{font-size:12px;color:' + DIM + ';margin-top:5px;line-height:1.65}',
    '.ag-hero .sub b{color:var(--ink,#e6edf3)}',
    /* 내비 */
    '.ag-nav{position:sticky;top:46px;z-index:12;display:flex;gap:6px;flex-wrap:wrap;background:rgba(10,14,20,.9);backdrop-filter:blur(8px);padding:8px 2px;border-bottom:1px solid var(--line,#1f2937);margin:0 -2px}',
    '.ag-nav a{font-size:11.5px;font-weight:650;color:' + DIM + ';text-decoration:none;padding:4px 11px;border:1px solid var(--line,#1f2937);border-radius:999px;transition:.12s;white-space:nowrap}',
    '.ag-nav a:hover{color:' + ACC + ';border-color:rgba(43,192,212,.5)}',
    /* KPI */
    '.ag-kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}',
    '@media(max-width:980px){.ag-kpis{grid-template-columns:repeat(3,1fr)}}',
    '@media(max-width:620px){.ag-kpis{grid-template-columns:repeat(2,1fr)}}',
    '.ag-kpi{background:var(--panel,#111721);border:1px solid var(--line,#1f2937);border-radius:13px;padding:11px 14px;min-width:0;position:relative;overflow:hidden}',
    '.ag-kpi:after{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--kc,' + ACC + ')}',
    '.ag-kpi .lab{font-size:10.5px;color:' + DIM + ';font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.ag-kpi .val{font-family:' + MONO + ';font-size:19px;font-weight:800;margin-top:3px;letter-spacing:-.02em}',
    '.ag-kpi .sub{font-size:10.5px;color:' + DIM + ';margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    /* 섹션 */
    '.ag-sec{scroll-margin-top:96px}',
    '.ag-sech{display:flex;align-items:baseline;gap:10px;margin-bottom:10px;flex-wrap:wrap}',
    '.ag-sech h3{font-size:15px;font-weight:800;margin:0;letter-spacing:-.01em}',
    '.ag-sech .hint{font-size:11px;color:' + DIM + '}',
    '.ag-sech .sp{flex:1}',
    '.ag-card{background:var(--panel,#111721);border:1px solid var(--line,#1f2937);border-radius:14px;padding:15px 17px;min-width:0}',
    /* 체인 스코어보드 */
    '.ag-chains{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}',
    '.ag-chain{background:var(--panel,#111721);border:1px solid var(--line,#1f2937);border-radius:14px;padding:13px 15px;min-width:0}',
    '.ag-chain .top{display:flex;align-items:center;gap:12px}',
    '.ag-chain .lb{font-size:13px;font-weight:750}',
    '.ag-chain .nn{font-size:10px;color:' + DIM + ';font-family:' + MONO + '}',
    '.ag-gauge{flex:0 0 92px}',
    '.ag-momrow{display:flex;gap:5px;margin-top:10px}',
    '.ag-mom{flex:1;border-radius:7px;padding:4px 2px;text-align:center;min-width:0}',
    '.ag-mom .h{font-size:8.5px;color:' + DIM + ';letter-spacing:.05em}',
    '.ag-mom .v{font-family:' + MONO + ';font-size:10.5px;font-weight:750;margin-top:1px}',
    '.ag-hbadges{display:flex;gap:5px;margin-top:9px;flex-wrap:wrap;min-height:18px}',
    '.ag-hb{font-size:9.5px;font-weight:800;border-radius:999px;padding:2px 8px;letter-spacing:.03em}',
    '.ag-hb.bt{color:' + UP + ';border:1px solid rgba(89,208,168,.45)}',
    '.ag-hb.pw{color:' + DOWN + ';border:1px solid rgba(255,94,108,.45)}',
    '.ag-hb.ac{color:' + WARN + ';border:1px solid rgba(246,200,95,.45)}',
    '.ag-stocks{display:flex;gap:4px;flex-wrap:wrap;margin-top:9px}',
    '.ag-stk{font-size:10px;color:' + DIM + ';border:1px solid var(--line,#1f2937);border-radius:999px;padding:2px 8px;cursor:default}',
    '.ag-stk b{color:var(--ink,#e6edf3);font-weight:650}',
    /* 테이블 */
    '.ag-scroll{overflow-x:auto}',
    '.ag-tbl{width:100%;border-collapse:collapse;font-size:12.5px;min-width:760px}',
    '.ag-tbl th{font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:' + DIM + ';font-weight:700;text-align:right;padding:7px 10px;border-bottom:1px solid var(--line,#1f2937);white-space:nowrap}',
    '.ag-tbl th.l,.ag-tbl td.l{text-align:left}',
    '.ag-tbl td{padding:7px 10px;border-bottom:1px solid rgba(31,41,55,.55);text-align:right;font-family:' + MONO + ';font-size:12px;white-space:nowrap}',
    '.ag-tbl tr:hover td{background:rgba(43,192,212,.05)}',
    '.ag-tbl td.nm{font-family:inherit;font-weight:700;font-size:12.5px}',
    '.ag-tbl td.nm .c{font-size:10px;color:' + DIM + ';font-weight:500;margin-left:6px}',
    '.ag-posbar{position:relative;width:76px;height:8px;background:rgba(31,41,55,.6);border-radius:4px;display:inline-block;vertical-align:middle;margin-right:7px}',
    '.ag-posbar i{position:absolute;top:-2px;width:4px;height:12px;border-radius:2px}',
    '.ag-empty{font-size:11.5px;color:' + DIM + ';padding:12px 0}',
    /* 칩 */
    '.ag-chips{display:flex;gap:6px;flex-wrap:wrap}',
    '.ag-chip{font:inherit;font-size:11.5px;line-height:1.5;padding:3px 11px;border:1px solid var(--line,#1f2937);border-radius:999px;background:transparent;color:' + DIM + ';cursor:pointer;transition:.12s}',
    '.ag-chip:hover{border-color:rgba(43,192,212,.5);color:' + ACC + '}',
    '.ag-chip.on{background:rgba(43,192,212,.14);color:' + ACC + ';border-color:rgba(43,192,212,.45);font-weight:700}',
    /* 차트 그리드 */
    '.ag-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}',
    '.ag-ccard{background:var(--panel,#111721);border:1px solid var(--line,#1f2937);border-radius:13px;padding:11px 13px;min-width:0}',
    '.ag-ccard .h{display:flex;align-items:baseline;gap:7px;flex-wrap:wrap;margin-bottom:5px}',
    '.ag-ccard .t{font-size:12px;font-weight:750;line-height:1.3}',
    '.ag-ccard .u{font-size:9.5px;color:' + DIM + ';font-family:' + MONO + '}',
    '.ag-ccard .lv{margin-left:auto;font-family:' + MONO + ';font-size:12px;font-weight:800}',
    '.ag-badge{font-size:9px;font-weight:800;border-radius:999px;padding:1px 7px}',
    '.ag-more{text-align:center;margin-top:12px}',
    /* 플롯 공통 */
    '.ag-plot{position:relative}',
    '.ag-plot svg{display:block;width:100%;height:auto;overflow:visible}',
    '.ag-tip{position:absolute;pointer-events:none;opacity:0;background:rgba(8,11,17,.94);border:1px solid var(--line,#1f2937);border-radius:8px;padding:6px 9px;font-family:' + MONO + ';font-size:10.5px;line-height:1.7;color:#e6edf3;white-space:nowrap;z-index:4;transition:opacity .1s;transform:translate(-50%,0)}',
    '.ag-plot.on .ag-tip{opacity:1}',
    '.ag-lgd{display:flex;gap:5px 12px;flex-wrap:wrap;margin-top:8px}',
    '.ag-lgd span{display:inline-flex;align-items:center;gap:5px;font-size:10.5px;color:' + DIM + '}',
    '.ag-lgd i{width:9px;height:9px;border-radius:3px;flex:0 0 auto}',
    /* 태양광 플로우 */
    '.ag-flow{display:flex;align-items:stretch;gap:0;flex-wrap:wrap}',
    '.ag-stage{flex:1 1 170px;background:var(--panel2,#0d131c);border:1px solid var(--line,#1f2937);border-radius:12px;padding:11px 13px;min-width:150px}',
    '.ag-stage .sn{font-size:10px;color:' + ACC + ';font-weight:800;letter-spacing:.09em}',
    '.ag-stage .pn{font-size:11.5px;font-weight:700;margin-top:2px;line-height:1.3}',
    '.ag-stage .pv{font-family:' + MONO + ';font-size:17px;font-weight:800;margin-top:5px}',
    '.ag-stage .pu{font-size:9.5px;color:' + DIM + ';font-family:' + MONO + '}',
    '.ag-stage .pm{font-family:' + MONO + ';font-size:10.5px;margin-top:3px}',
    '.ag-arrow{flex:0 0 26px;display:flex;align-items:center;justify-content:center;color:' + DIM + ';font-size:15px}',
    '@media(max-width:700px){.ag-flow{flex-direction:column}.ag-arrow{transform:rotate(90deg);flex-basis:20px}}',
    '.ag-grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}',
    '@media(max-width:980px){.ag-grid2{grid-template-columns:1fr}}',
    /* 유가 KPI */
    '.ag-oilkpis{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}',
    '.ag-oilk{background:var(--panel2,#0d131c);border:1px solid var(--line,#1f2937);border-radius:11px;padding:9px 14px;min-width:120px}',
    '.ag-oilk .l{font-size:10.5px;color:' + DIM + ';font-weight:650}',
    '.ag-oilk .v{font-family:' + MONO + ';font-size:16px;font-weight:800;margin-top:2px}',
    '.ag-oilk .w{font-family:' + MONO + ';font-size:10.5px;margin-top:1px}',
    '.ag-foot{font-size:10.5px;color:' + DIM + ';line-height:1.7;border-top:1px solid var(--line,#1f2937);padding-top:12px}'
  ].join('');

  function ensureCss(doc) {
    if (!doc || doc.getElementById('agChartsCss')) return;
    var s = doc.createElement('style');
    s.id = 'agChartsCss';
    s.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(s);
  }

  /* ───────── helpers ───────── */
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function fin(v) { return v != null && isFinite(v); }
  function fmt(v) {
    if (!fin(v)) return '—';
    var a = Math.abs(v);
    if (a >= 1000) return String(Math.round(v)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    if (a >= 100) return v.toFixed(1);
    if (a >= 1) return v.toFixed(2);
    return v.toFixed(3);
  }
  function fmtPct(v, dp) {
    if (!fin(v)) return '<span style="color:' + DIM + '">—</span>';
    var c = v >= 0 ? UP : DOWN, s = v >= 0 ? '+' : '−';
    return '<span style="color:' + c + ';font-weight:700">' + s + Math.abs(v).toFixed(dp == null ? 1 : dp) + '%</span>';
  }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function hex2rgb(h) { var n = parseInt(h.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
  function mix(c1, c2, t) {
    var a = hex2rgb(c1), b = hex2rgb(c2);
    return 'rgb(' + Math.round(lerp(a[0], b[0], t)) + ',' + Math.round(lerp(a[1], b[1], t)) + ',' + Math.round(lerp(a[2], b[2], t)) + ')';
  }
  function posColor(p) {
    if (!fin(p)) return DIM;
    return p <= 50 ? mix(UP, WARN, p / 50) : mix(WARN, DOWN, (p - 50) / 50);
  }
  function momCell(lab, v) {
    var bg = 'rgba(31,41,55,.4)', col = DIM;
    if (fin(v)) {
      var t = Math.min(1, Math.abs(v) / 8);
      bg = v >= 0 ? 'rgba(89,208,168,' + (0.08 + 0.3 * t).toFixed(2) + ')' : 'rgba(255,94,108,' + (0.08 + 0.3 * t).toFixed(2) + ')';
      col = v >= 0 ? UP : DOWN;
    }
    return '<div class="ag-mom" style="background:' + bg + '"><div class="h">' + lab + '</div><div class="v" style="color:' + col + '">' +
      (fin(v) ? (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(1) : '—') + '</div></div>';
  }
  function huntBadges(hunt) {
    var M = { bottom_turn: ['bt', '🎯 바닥반등'], peak_warn: ['pw', '⚠ 고점경계'], accel: ['ac', '⤴ 가속'] };
    return (hunt || []).map(function (h) { var m = M[h]; return m ? '<span class="ag-hb ' + m[0] + '">' + m[1] + '</span>' : ''; }).join('');
  }
  function stockChips(stocks) {
    return (stocks || []).map(function (s) {
      return '<span class="ag-stk" title="' + esc(s.note || '') + '"><b>' + esc(s.n) + '</b> ' + esc(s.t || '') + '</span>';
    }).join('');
  }
  function spark(v, w, h, color) {
    w = w || 90; h = h || 24;
    var xs = [], f = v.filter(fin);
    if (f.length < 2) return '<svg width="' + w + '" height="' + h + '"></svg>';
    var mn = Math.min.apply(null, f), mx = Math.max.apply(null, f), r = (mx - mn) || 1;
    var d = '', started = false;
    for (var i = 0; i < v.length; i++) {
      if (!fin(v[i])) { started = false; continue; }
      var x = (i / (v.length - 1)) * (w - 2) + 1;
      var y = h - 2 - ((v[i] - mn) / r) * (h - 4);
      d += (started ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
      started = true;
    }
    return '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '"><path d="' + d + '" fill="none" stroke="' + (color || ACC) + '" stroke-width="1.5"/></svg>';
  }
  function gauge(pos) {
    var W = 92, H = 58, cx = 46, cy = 50, r = 38;
    function pt(frac) { var th = Math.PI * (1 - frac); return [cx + r * Math.cos(th), cy - r * Math.sin(th)]; }
    var col = posColor(pos), f = fin(pos) ? pos / 100 : 0;
    var a = pt(0), b = pt(f);
    var arc = fin(pos) && pos > 0.5
      ? '<path d="M' + a[0].toFixed(1) + ' ' + a[1].toFixed(1) + ' A' + r + ' ' + r + ' 0 ' + (f > 0.5 ? 1 : 0) + ' 1 ' + b[0].toFixed(1) + ' ' + b[1].toFixed(1) + '" fill="none" stroke="' + col + '" stroke-width="7" stroke-linecap="round"/>' : '';
    var e = pt(1);
    return '<svg class="ag-gauge" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '">' +
      '<path d="M' + a[0] + ' ' + a[1] + ' A' + r + ' ' + r + ' 0 0 1 ' + e[0] + ' ' + e[1] + '" fill="none" stroke="rgba(31,41,55,.8)" stroke-width="7" stroke-linecap="round"/>' + arc +
      '<text x="' + cx + '" y="' + (cy - 4) + '" text-anchor="middle" font-size="17" font-weight="800" fill="' + col + '" font-family="ui-monospace,Menlo,monospace">' + (fin(pos) ? Math.round(pos) : '—') + '</text>' +
      '<text x="' + cx + '" y="' + (cy + 7) + '" text-anchor="middle" font-size="7.5" fill="' + DIM + '">POS</text></svg>';
  }
  function posBarCell(pos) {
    if (!fin(pos)) return '—';
    return '<span class="ag-posbar"><i style="left:' + Math.min(96, Math.max(0, pos)).toFixed(0) + '%;background:' + posColor(pos) + '"></i></span><b style="color:' + posColor(pos) + '">' + pos.toFixed(0) + '</b>';
  }

  /* ───────── 라인차트 (호버 툴팁 + 사냥 마커) ───────── */
  var CH = {};
  var chSeq = 0;
  function chart(dates, rows, o) {
    // rows: [{name, v, col, hunt}], o: {h, unit, from, idx(100지수화), ymin0}
    o = o || {};
    var from = o.from || 0;
    var ds = dates.slice(from);
    var W = 900, H = o.h || 170, PL = 8, PR = 54, PT = 10, PB = 20;
    var n = ds.length;
    if (!n || !rows.length) return '<div class="ag-empty">데이터 없음</div>';
    var view = rows.map(function (r) {
      var v = r.v.slice(from);
      if (o.idx) {
        var b = null;
        for (var i = 0; i < v.length; i++) if (fin(v[i]) && v[i] !== 0) { b = v[i]; break; }
        v = v.map(function (x) { return fin(x) && b ? x / b * 100 : null; });
      }
      return { name: r.name, v: v, col: r.col, hunt: r.hunt };
    });
    var all = [];
    view.forEach(function (r) { r.v.forEach(function (x) { if (fin(x)) all.push(x); }); });
    if (!all.length) return '<div class="ag-empty">데이터 없음</div>';
    var mn = Math.min.apply(null, all), mx = Math.max.apply(null, all);
    if (o.ymin0 && mn > 0) mn = 0;
    var pad = (mx - mn) * 0.06 || Math.abs(mx) * 0.05 || 1;
    mn -= pad; mx += pad;
    var x = function (i) { return PL + (W - PL - PR) * (n === 1 ? 0.5 : i / (n - 1)); };
    var y = function (v) { return PT + (H - PT - PB) * (1 - (v - mn) / (mx - mn)); };
    var g = '';
    for (var t = 0; t <= 3; t++) {
      var tv = mn + (mx - mn) * t / 3, ty = y(tv);
      g += '<line x1="' + PL + '" y1="' + ty.toFixed(1) + '" x2="' + (W - PR) + '" y2="' + ty.toFixed(1) + '" stroke="#1f2937" stroke-width="0.6" stroke-dasharray="3 4"/>' +
        '<text x="' + (W - PR + 5) + '" y="' + (ty + 3.5).toFixed(1) + '" font-size="9.5" fill="' + DIM + '" font-family="ui-monospace,Menlo,monospace">' + fmt(tv) + '</text>';
    }
    if (mn < 0 && mx > 0) {
      g += '<line x1="' + PL + '" y1="' + y(0).toFixed(1) + '" x2="' + (W - PR) + '" y2="' + y(0).toFixed(1) + '" stroke="' + DIM + '" stroke-width="0.7" stroke-opacity="0.55"/>';
    }
    var xl = '';
    for (var xi = 0; xi < 5; xi++) {
      var idx = Math.round((n - 1) * xi / 4);
      var anchor = xi === 0 ? 'start' : (xi === 4 ? 'end' : 'middle');
      xl += '<text x="' + x(idx).toFixed(1) + '" y="' + (H - 5) + '" font-size="9.5" fill="' + DIM + '" text-anchor="' + anchor + '" font-family="ui-monospace,Menlo,monospace">' + esc(String(ds[idx]).slice(2, 7)) + '</text>';
    }
    var paths = '', marks = '';
    view.forEach(function (r) {
      var d = '', started = false, li = -1;
      for (var i = 0; i < n; i++) {
        if (!fin(r.v[i])) { started = false; continue; }
        d += (started ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(r.v[i]).toFixed(1) + ' ';
        started = true; li = i;
      }
      paths += '<path d="' + d + '" fill="none" stroke="' + r.col + '" stroke-width="1.6" stroke-linejoin="round"/>';
      if (li >= 0 && r.hunt && r.hunt.length) {
        var hc = r.hunt.indexOf('bottom_turn') >= 0 ? UP : (r.hunt.indexOf('peak_warn') >= 0 ? DOWN : WARN);
        marks += '<circle cx="' + x(li).toFixed(1) + '" cy="' + y(r.v[li]).toFixed(1) + '" r="5.5" fill="none" stroke="' + hc + '" stroke-width="2"/>' +
          '<circle cx="' + x(li).toFixed(1) + '" cy="' + y(r.v[li]).toFixed(1) + '" r="2" fill="' + hc + '"/>';
      }
    });
    var id = 'ag' + (++chSeq);
    CH[id] = { ds: ds, rows: view, W: W, PL: PL, PR: PR, unit: o.idx ? 'idx' : (o.unit || '') };
    return '<div class="ag-plot" data-ch="' + id + '"><svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">' + g + paths + marks +
      '<line class="ag-guide" x1="0" y1="' + PT + '" x2="0" y2="' + (H - PB) + '" stroke="#e6edf3" stroke-opacity="0" stroke-width="1"/>' + xl +
      '</svg><div class="ag-tip"></div></div>';
  }
  function bindHover(root) {
    root.querySelectorAll('.ag-plot[data-ch]').forEach(function (plot) {
      if (plot.dataset.bound) return;
      plot.dataset.bound = '1';
      var st = CH[plot.dataset.ch]; if (!st) return;
      var svg = plot.querySelector('svg'), tip = plot.querySelector('.ag-tip'), guide = plot.querySelector('.ag-guide');
      plot.addEventListener('mousemove', function (ev) {
        var r = svg.getBoundingClientRect();
        var fx = (ev.clientX - r.left) / r.width * st.W;
        var frac = Math.min(1, Math.max(0, (fx - st.PL) / (st.W - st.PL - st.PR)));
        var i = Math.round(frac * (st.ds.length - 1));
        var lines = st.rows.map(function (rw) {
          return '<span style="color:' + rw.col + '">●</span> ' + esc(rw.name) + ' <b>' + fmt(rw.v[i]) + '</b>';
        });
        tip.innerHTML = '<b>' + esc(st.ds[i]) + '</b>' + (st.unit && st.unit !== 'idx' ? ' · ' + esc(st.unit) : (st.unit === 'idx' ? ' · 지수(=100)' : '')) + '<br>' + lines.join('<br>');
        var px = (st.PL + frac * (st.W - st.PL - st.PR)) / st.W * r.width;
        tip.style.left = Math.min(r.width - 100, Math.max(100, px)) + 'px';
        tip.style.top = '4px';
        guide.setAttribute('x1', fx.toFixed(1)); guide.setAttribute('x2', fx.toFixed(1));
        guide.setAttribute('stroke-opacity', '0.35');
        plot.classList.add('on');
      });
      plot.addEventListener('mouseleave', function () { plot.classList.remove('on'); guide.setAttribute('stroke-opacity', '0'); });
    });
  }

  /* ───────── 메인 ───────── */
  window.renderARGUS = function (el, data) {
    ensureCss(el.ownerDocument);
    data = data || {};
    data.kpi = data.kpi || {};
    data.axes = data.axes || { wk: [], sol: [], oil: [] };
    data.chains = data.chains || [];
    data.signals = data.signals || { bt: [], pw: [] };
    data.spread = data.spread || { cats: [], series: [] };
    data.solar = data.solar || { series: [] };
    data.oil = data.oil || { series: [] };

    var defCat = (function () {
      var withHunt = data.spread.series.filter(function (r) { return r.hunt && r.hunt.length; });
      if (withHunt.length) return withHunt[0].cat;
      return data.spread.cats[0] || null;
    })();
    var ST = { cat: defCat, spLimit: 24, oilRange: '5y' };

    el.innerHTML = '<div class="ag-wrap">' + hero() + nav() + kpis() +
      sec('board', '🏔 체인 스코어보드', '게이지 = 사이클 위치 percentile(전 이력) · 셀 = 모멘텀 중앙값 %') +
      sec('hunt', '🎯 사냥 시그널', 'bottom_turn: pos≤20 & 4주·1주 반등 / peak_warn: pos≥85 & 4주 하락') +
      sec('spread', '📉 스프레드 차트', '주간 5년 · 마커 = 현재 사냥 시그널', chips()) +
      sec('solar', '☀️ 태양광 밸류체인', '폴리 → 웨이퍼 → 셀 → 모듈 · PVInsights 주간') +
      sec('oil', '🛢 유가 데크', 'petronet 일간 → 주간 다운샘플 · 스프레드 = 제품-두바이', oilChips()) +
      footer() + '</div>';

    var W = el.querySelector('.ag-wrap');
    function body(id) { return W.querySelector('[data-body="' + id + '"]'); }
    function sec(id, title, hint, right) {
      return '<div class="ag-sec" id="ag-' + id + '"><div class="ag-sech"><h3>' + title + '</h3><span class="hint">' + esc(hint || '') + '</span><span class="sp"></span>' + (right || '') + '</div><div data-body="' + id + '"></div></div>';
    }
    function hero() {
      var k = data.kpi;
      return '<div class="ag-hero"><h2>👁 ARGUS — 시클리컬 사이클 관제</h2>' +
        '<div class="sub">정유·화학·태양광 <b>' + (k.n_series || 0) + '개</b> 가격·스프레드 시리즈의 사이클 위치를 상시 감시 — ' +
        '바닥 반등 <b style="color:' + UP + '">' + (k.n_bt || 0) + '건</b> · 고점 경계 <b style="color:' + DOWN + '">' + (k.n_pw || 0) + '건</b> · ' +
        '기준일 <b>' + esc(data.asof || '—') + '</b> · 주간 갱신' + (data.mock ? ' · <b style="color:' + WARN + '">MOCK 데이터</b>' : '') +
        ' · 참고용, 투자조언 아님</div></div>';
    }
    function nav() {
      var items = [['board', '🏔 스코어보드'], ['hunt', '🎯 시그널'], ['spread', '📉 스프레드'], ['solar', '☀️ 태양광'], ['oil', '🛢 유가']];
      return '<div class="ag-nav">' + items.map(function (it) { return '<a href="#ag-' + it[0] + '">' + it[1] + '</a>'; }).join('') + '</div>';
    }
    function kpis() {
      var k = data.kpi;
      var low = data.chains.filter(function (c) { return fin(c.pos); }).sort(function (a, b) { return a.pos - b.pos; })[0];
      var high = data.chains.filter(function (c) { return fin(c.pos); }).sort(function (a, b) { return b.pos - a.pos; })[0];
      function kpi(color, lab, val, sub) { return '<div class="ag-kpi" style="--kc:' + color + '"><div class="lab">' + lab + '</div><div class="val">' + val + '</div><div class="sub">' + sub + '</div></div>'; }
      return '<div class="ag-kpis">' +
        kpi(ACC, '감시 시리즈', String(k.n_series || 0), '가격·스프레드·태양광·유가') +
        kpi(UP, '🎯 바닥 반등', String(k.n_bt || 0), 'bottom_turn 시그널') +
        kpi(DOWN, '⚠ 고점 경계', String(k.n_pw || 0), 'peak_warn 시그널') +
        kpi(WARN, '⤴ 가속', String(k.n_ac || 0), '모멘텀 가속(accel)') +
        kpi('#b892ff', '최저 사이클 체인', low ? esc(low.label) : '—',
          (low ? 'pos ' + low.pos : '') + (high ? ' · 최고 ' + esc(high.label) + ' ' + high.pos : '')) +
        '</div>';
    }
    function chips() {
      return '<div class="ag-chips" data-ck="cat">' + data.spread.cats.map(function (c) {
        var n = data.spread.series.filter(function (r) { return r.cat === c && r.hunt && r.hunt.length; }).length;
        return '<button class="ag-chip' + (c === ST.cat ? ' on' : '') + '" data-cv="' + esc(c) + '">' + esc(c) + (n ? ' <b style="color:' + UP + '">●' + n + '</b>' : '') + '</button>';
      }).join('') + '</div>';
    }
    function oilChips() {
      return '<div class="ag-chips" data-ck="oilRange">' + [['all', '전체'], ['10y', '10년'], ['5y', '5년'], ['1y', '1년']].map(function (p) {
        return '<button class="ag-chip' + (p[0] === ST.oilRange ? ' on' : '') + '" data-cv="' + p[0] + '">' + p[1] + '</button>';
      }).join('') + '</div>';
    }
    function footer() {
      return '<div class="ag-foot">ARGUS — 주간 시황 원장(xlsm) 기반 시클리컬 사이클 계량 · pos = 전 이력 percentile(0=역사적 바닥, 100=역사적 고점) · ' +
        'mom = 1/4/13/26주 변화율 · 종목 매핑은 사업 익스포저 큐레이션(참고용 라벨) · <b>투자조언 아님</b> · 기준일 ' + esc(data.asof || '—') +
        (data.mock ? ' · <span style="color:' + WARN + '">본 화면은 MOCK 데이터 렌더 검증본</span>' : '') + '</div>';
    }

    /* ── ① 스코어보드 ── */
    function rBoard() {
      if (!data.chains.length) { body('board').innerHTML = '<div class="ag-empty">체인 데이터 없음</div>'; return; }
      body('board').innerHTML = '<div class="ag-chains">' + data.chains.map(function (c) {
        var h = c.hunts || {};
        var badges = (h.bt ? '<span class="ag-hb bt">🎯 바닥반등 ' + h.bt + '</span>' : '') +
          (h.pw ? '<span class="ag-hb pw">⚠ 고점 ' + h.pw + '</span>' : '') +
          (h.ac ? '<span class="ag-hb ac">⤴ 가속 ' + h.ac + '</span>' : '');
        var m = c.mom || {};
        return '<div class="ag-chain"><div class="top">' + gauge(c.pos) +
          '<div><div class="lb">' + esc(c.label) + '</div><div class="nn">' + (c.n || 0) + ' series</div></div></div>' +
          '<div class="ag-momrow">' + momCell('1W', m.w1) + momCell('4W', m.w4) + momCell('13W', m.w13) + momCell('26W', m.w26) + '</div>' +
          '<div class="ag-hbadges">' + badges + '</div>' +
          '<div class="ag-stocks">' + stockChips(c.stocks) + '</div></div>';
      }).join('') + '</div>';
    }

    /* ── ② 사냥 시그널 ── */
    function sigTable(rows, kind) {
      if (!rows.length) return '<div class="ag-empty">현재 ' + (kind === 'bt' ? 'bottom_turn' : 'peak_warn') + ' 시그널 없음</div>';
      return '<div class="ag-scroll"><table class="ag-tbl"><thead><tr>' +
        '<th class="l">시리즈</th><th>pos</th><th>pos5y</th><th>1W%</th><th>4W%</th><th>z26</th><th>현재값</th><th>26주</th><th class="l">연관 종목</th>' +
        '</tr></thead><tbody>' + rows.map(function (r) {
          return '<tr><td class="nm l">' + esc(r.name) + '<span class="c">' + esc(r.cat || '') + '</span></td>' +
            '<td>' + posBarCell(r.pos) + '</td>' +
            '<td style="color:' + DIM + '">' + (fin(r.pos5y) ? r.pos5y.toFixed(0) : '—') + '</td>' +
            '<td>' + fmtPct(r.m1) + '</td><td>' + fmtPct(r.m4) + '</td>' +
            '<td style="color:' + DIM + '">' + (fin(r.z26) ? r.z26.toFixed(1) : '—') + '</td>' +
            '<td><b>' + fmt(r.last) + '</b> <span style="color:' + DIM + ';font-size:10px">' + esc(r.unit || '') + '</span></td>' +
            '<td>' + spark(r.spark || [], 90, 24, kind === 'bt' ? UP : DOWN) + '</td>' +
            '<td class="l" style="font-family:inherit">' + stockChips(r.stocks) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    function rHunt() {
      body('hunt').innerHTML =
        '<div class="ag-card" style="margin-bottom:12px"><div style="font-size:12.5px;font-weight:800;margin-bottom:8px;color:' + UP + '">🎯 bottom_turn — 역사적 바닥권에서 반등 시작</div>' + sigTable(data.signals.bt || [], 'bt') + '</div>' +
        '<div class="ag-card"><div style="font-size:12.5px;font-weight:800;margin-bottom:8px;color:' + DOWN + '">⚠ peak_warn — 역사적 고점권에서 하락 전환</div>' + sigTable(data.signals.pw || [], 'pw') + '</div>';
    }

    /* ── ③ 스프레드 차트 ── */
    function rSpread() {
      var rows = data.spread.series.filter(function (r) { return r.cat === ST.cat; });
      if (!rows.length) { body('spread').innerHTML = '<div class="ag-empty">카테고리 데이터 없음</div>'; return; }
      rows = rows.slice().sort(function (a, b) {
        var ha = a.hunt && a.hunt.length ? 1 : 0, hb = b.hunt && b.hunt.length ? 1 : 0;
        return hb - ha;
      });
      var shown = rows.slice(0, ST.spLimit);
      body('spread').innerHTML = '<div class="ag-grid">' + shown.map(function (r, i) {
        var col = r.hunt && r.hunt.indexOf('bottom_turn') >= 0 ? UP : (r.hunt && r.hunt.indexOf('peak_warn') >= 0 ? DOWN : PAL[i % PAL.length]);
        return '<div class="ag-ccard"><div class="h"><span class="t">' + esc(r.name) + '</span><span class="u">' + esc(r.unit || '') + '</span>' +
          (fin(r.pos) ? '<span class="ag-badge" style="color:' + posColor(r.pos) + ';border:1px solid ' + posColor(r.pos) + '">pos ' + r.pos.toFixed(0) + '</span>' : '') +
          huntBadges(r.hunt) +
          '<span class="lv">' + fmt(r.last) + ' <span style="font-weight:500;color:' + DIM + '">' + (fin(r.m4) ? '' : '') + '</span></span></div>' +
          chart(data.axes.wk, [{ name: r.name, v: r.v, col: col, hunt: r.hunt }], { h: 150, unit: r.unit }) + '</div>';
      }).join('') + '</div>' +
        (rows.length > ST.spLimit ? '<div class="ag-more"><button class="ag-chip" data-act="spmore">▼ ' + (rows.length - ST.spLimit) + '개 더 보기</button></div>' :
          (ST.spLimit > 24 ? '<div class="ag-more"><button class="ag-chip" data-act="spless">▲ 접기</button></div>' : ''));
      bindHover(body('spread'));
      var mb = body('spread').querySelector('[data-act]');
      if (mb) mb.onclick = function () { ST.spLimit = mb.dataset.act === 'spmore' ? 999 : 24; rSpread(); };
    }

    /* ── ④ 태양광 ── */
    function rSolar() {
      var ss = data.solar.series || [];
      if (!ss.length) { body('solar').innerHTML = '<div class="ag-empty">태양광 데이터 없음</div>'; return; }
      var ORDER = [['poly', '폴리실리콘'], ['wafer', '웨이퍼'], ['cell', '셀'], ['module', '모듈']];
      var mains = ORDER.map(function (o) {
        return (ss.filter(function (r) { return r.stage === o[0] && r.main; })[0]) || null;
      });
      var flow = '<div class="ag-flow">' + ORDER.map(function (o, i) {
        var r = mains[i];
        var cell = r ? '<div class="ag-stage"><div class="sn">' + o[1].toUpperCase() + '</div><div class="pn">' + esc(r.name) + '</div>' +
          '<div class="pv" style="color:' + posColor(r.pos) + '">' + fmt(r.last) + ' <span class="pu">' + esc(r.unit || '') + '</span></div>' +
          '<div class="pm">WoW ' + fmtPct(r.m1) + ' · 4W ' + fmtPct(r.m4) + (fin(r.pos) ? ' · pos <b style="color:' + posColor(r.pos) + '">' + r.pos.toFixed(0) + '</b>' : '') + '</div>' +
          '<div style="margin-top:6px">' + spark((r.v || []).slice(-104).filter(function (_, j) { return true; }), 150, 30, posColor(r.pos)) + '</div>' +
          '<div class="ag-hbadges" style="margin-top:6px">' + huntBadges(r.hunt) + '</div></div>'
          : '<div class="ag-stage"><div class="sn">' + o[1] + '</div><div class="ag-empty">—</div></div>';
        return cell + (i < ORDER.length - 1 ? '<div class="ag-arrow">➜</div>' : '');
      }).join('') + '</div>';
      var mainRows = mains.filter(Boolean).map(function (r, i) {
        return { name: r.name, v: r.v, col: PAL[i], hunt: r.hunt };
      });
      var modRows = ss.filter(function (r) { return r.stage === 'module'; }).slice(0, 6).map(function (r, i) {
        return { name: r.name, v: r.v, col: PAL[(i + 4) % PAL.length], hunt: r.hunt };
      });
      body('solar').innerHTML = flow +
        '<div class="ag-grid2" style="margin-top:12px">' +
        '<div class="ag-card"><div style="font-size:12px;font-weight:750;margin-bottom:6px">단계별 가격 지수 (5년, 시작=100)</div>' +
        chart(data.axes.sol, mainRows, { h: 200, idx: true }) +
        '<div class="ag-lgd">' + mainRows.map(function (r) { return '<span><i style="background:' + r.col + '"></i>' + esc(r.name) + '</span>'; }).join('') + '</div></div>' +
        '<div class="ag-card"><div style="font-size:12px;font-weight:750;margin-bottom:6px">모듈 가격 (USD/W)</div>' +
        chart(data.axes.sol, modRows, { h: 200, unit: 'USD/W' }) +
        '<div class="ag-lgd">' + modRows.map(function (r) { return '<span><i style="background:' + r.col + '"></i>' + esc(r.name) + '</span>'; }).join('') + '</div></div></div>';
      bindHover(body('solar'));
    }

    /* ── ⑤ 유가 데크 ── */
    function oilFrom() {
      var ax = data.axes.oil, n = ax.length;
      if (ST.oilRange === 'all') return 0;
      var yrs = ST.oilRange === '10y' ? 10 : ST.oilRange === '5y' ? 5 : 1;
      return Math.max(0, n - yrs * 52 - 1);
    }
    function rOil() {
      var ss = data.oil.series || [];
      if (!ss.length) { body('oil').innerHTML = '<div class="ag-empty">유가 데이터 없음</div>'; return; }
      var crude = ss.filter(function (r) { return r.grp === 'crude'; });
      var crack = ss.filter(function (r) { return r.grp === 'crack'; });
      var from = oilFrom();
      var kpi = '<div class="ag-oilkpis">' + crude.concat(crack.slice(0, 2)).map(function (r) {
        return '<div class="ag-oilk"><div class="l">' + esc(r.name) + '</div><div class="v">' + fmt(r.last) +
          ' <span style="font-size:10px;color:' + DIM + '">' + esc(r.unit || '') + '</span></div><div class="w">WoW ' + fmtPct(r.wow) +
          (fin(r.pos) ? ' · pos <b style="color:' + posColor(r.pos) + '">' + r.pos.toFixed(0) + '</b>' : '') + '</div></div>';
      }).join('') + '</div>';
      var crudeRows = crude.map(function (r, i) { return { name: r.name, v: r.v, col: [ACC, '#4ea1ff', '#f6c85f', '#b892ff'][i % 4], hunt: r.hunt }; });
      var crackRows = crack.map(function (r, i) { return { name: r.name, v: r.v, col: PAL[i % PAL.length], hunt: r.hunt }; });
      body('oil').innerHTML = kpi +
        '<div class="ag-grid2">' +
        '<div class="ag-card"><div style="font-size:12px;font-weight:750;margin-bottom:6px">원유 ($/bbl)</div>' +
        chart(data.axes.oil, crudeRows, { h: 210, unit: '$/bbl', from: from }) +
        '<div class="ag-lgd">' + crudeRows.map(function (r) { return '<span><i style="background:' + r.col + '"></i>' + esc(r.name) + '</span>'; }).join('') + '</div></div>' +
        '<div class="ag-card"><div style="font-size:12px;font-weight:750;margin-bottom:6px">정제 스프레드 — 제품-두바이 ($/bbl)</div>' +
        chart(data.axes.oil, crackRows, { h: 210, unit: '$/bbl', from: from }) +
        '<div class="ag-lgd">' + crackRows.map(function (r) { return '<span><i style="background:' + r.col + '"></i>' + esc(r.name) + '</span>'; }).join('') + '</div></div></div>';
      bindHover(body('oil'));
    }

    /* 칩 이벤트 (위임) */
    W.addEventListener('click', function (ev) {
      var b = ev.target.closest('.ag-chip'); if (!b) return;
      var row = b.closest('[data-ck]'); if (!row) return;
      var key = row.dataset.ck, val = b.dataset.cv;
      if (val == null || ST[key] === val) return;
      ST[key] = val;
      row.querySelectorAll('.ag-chip').forEach(function (c) { c.classList.toggle('on', c === b); });
      if (key === 'cat') { ST.spLimit = 24; rSpread(); }
      else if (key === 'oilRange') rOil();
    });

    rBoard(); rHunt(); rSpread(); rSolar(); rOil();
  };
})();
