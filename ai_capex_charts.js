/* ai_capex_charts.js — 빅테크·클라우드 분기 CAPEX·FCF 시계열 + 컨콜 트랜스크립트 해석
 * 전역: window.renderAICapex(el, data [, notes])
 *   data  = ai_capex_fcf.json 전체 객체  {_meta, companies:{ticker:{...}}}
 *   notes = ai_transcript_notes.json 전체 객체(선택).
 *           생략 시 data.transcript_notes → window.__aiTranscriptNotes 순으로 탐색.
 * 의존성 0 (순수 SVG). 로드 시 부작용 없음 — window.renderAICapex 정의만.
 * CSS는 첫 렌더에서 1회 주입.
 */
(function () {
  'use strict';

  /* ---------- 팔레트 (팔랑크스 다크) ---------- */
  var MONO = 'var(--mono,ui-monospace,SFMono-Regular,Menlo,monospace)';
  var CLR = {
    bar: '#3f6f9e',      // 평시 CAPEX
    hi: '#2bc0d4',       // 급증 구간
    pos: '#59d0a8',      // FCF +
    neg: '#ff4d5e',      // FCF −
    warn: '#ff8a3d',
    purple: '#c58aff',
    dim: '#8a93a3'
  };
  var SERIES = ['#2bc0d4', '#59d0a8', '#ffb545', '#c58aff', '#ff4d5e',
    '#4ea1ff', '#f078b0', '#7ed957', '#ff8a3d', '#8ab4ff', '#d4b483', '#6ee7e7'];

  /* 최근 급증 판정: 직전 4분기 중앙값 대비 배수 */
  var SURGE_X = 1.5;

  var PERIODS = [
    { k: '2Y', n: 8 }, { k: '3Y', n: 12 }, { k: '5Y', n: 20 }, { k: '전체', n: 0 }
  ];
  var DEFAULT_PERIOD = '3Y';

  /* ---------- CSS ---------- */
  var CSS = [
    '.acx{display:flex;flex-direction:column;gap:13px}',
    '.acx-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px;flex-wrap:wrap}',
    '.acx-title{font-size:14px;font-weight:750;letter-spacing:-.01em}',
    '.acx-asof{font-family:' + MONO + ';font-size:10.5px;color:var(--dim,#8a93a3);font-weight:600}',
    '.acx-chips{display:flex;gap:6px;flex-wrap:wrap}',
    '.acx-chip{font:inherit;font-size:11.5px;line-height:1.5;padding:3px 9px;border:1px solid var(--line,#2a2f3a);',
    'border-radius:999px;background:transparent;color:var(--dim,#8a93a3);cursor:pointer;transition:all .12s}',
    '.acx-chip:hover{border-color:rgba(43,192,212,.5);color:#2bc0d4}',
    '.acx-chip.on{background:rgba(43,192,212,.14);color:#2bc0d4;border-color:rgba(43,192,212,.45)}',
    '.acx-chip.sm{font-size:10.5px;padding:2px 8px}',
    '.acx-bar{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}',
    '.acx-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}',
    '@media (max-width:980px){.acx-grid{grid-template-columns:1fr}}',
    '.acx-card{background:var(--panel,#12161d);border:1px solid var(--line,#2a2f3a);border-radius:13px;padding:14px 16px;min-width:0}',
    '.acx-cardhead{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:2px}',
    '.acx-t{font-size:12px;font-weight:650}',
    '.acx-t em{font-style:normal;color:var(--dim,#8a93a3);font-weight:550}',
    '.acx-v{font-family:' + MONO + ';font-size:12.5px;font-weight:700}',
    '.acx-sub{font-size:10.5px;color:var(--dim,#8a93a3);font-family:' + MONO + ';margin-bottom:6px}',
    '.acx-plot svg{display:block;width:100%;height:auto;overflow:visible}',
    '.acx-empty{font-size:11.5px;color:var(--dim,#8a93a3);padding:14px 0;text-align:center}',
    '.acx-lgd{display:flex;gap:12px;flex-wrap:wrap;margin-top:7px}',
    '.acx-lg{display:flex;align-items:center;gap:5px;font-size:10.5px;color:var(--dim,#8a93a3)}',
    '.acx-sw{width:10px;height:10px;border-radius:3px;flex:none}',
    '.acx-sw.ln{height:3px;border-radius:2px;width:14px}',
    '.acx-badges{display:flex;gap:6px;flex-wrap:wrap;margin:2px 0 9px}',
    '.acx-badge{font-size:11px;font-weight:700;padding:3px 9px;border-radius:999px;border:1px solid;line-height:1.5;white-space:nowrap}',
    '.acx-key{background:var(--panel,#12161d);border:1px solid rgba(43,192,212,.35);border-radius:13px;padding:13px 16px}',
    '.acx-keyt{font-size:12px;font-weight:700;margin-bottom:8px;display:flex;align-items:center;gap:7px;flex-wrap:wrap}',
    '.acx-read{font-size:11.5px;line-height:1.75;color:var(--fg,#e6e9ef);margin:2px 0 10px;white-space:pre-line}',
    '.acx-q{border:1px solid var(--line,#2a2f3a);border-radius:10px;margin-top:7px;overflow:hidden}',
    '.acx-q>summary{cursor:pointer;list-style:none;padding:8px 11px;font-size:11.5px;line-height:1.55;',
    'display:flex;gap:8px;align-items:flex-start;background:rgba(255,255,255,.015)}',
    '.acx-q>summary::-webkit-details-marker{display:none}',
    '.acx-q>summary::before{content:"▸";color:var(--dim,#8a93a3);flex:none;transition:transform .12s;line-height:1.45}',
    '.acx-q[open]>summary::before{transform:rotate(90deg)}',
    '.acx-qwho{font-weight:700}',
    '.acx-qsig{font-size:10px;font-weight:700;padding:1px 6px;border-radius:999px;border:1px solid;margin-left:auto;flex:none;white-space:nowrap}',
    '.acx-qbody{padding:2px 12px 11px 30px;border-top:1px dashed var(--line,#2a2f3a)}',
    '.acx-en{font-size:11px;line-height:1.7;color:var(--fg,#e6e9ef);margin:8px 0 0;',
    'border-left:2px solid rgba(43,192,212,.45);padding-left:9px;font-style:italic}',
    '.acx-ko{font-size:11px;line-height:1.7;color:var(--dim,#8a93a3);margin:6px 0 0}',
    '.acx-src{font-size:10px;color:var(--dim,#8a93a3);font-family:' + MONO + ';margin-top:9px;word-break:break-all}',
    '.acx-src a{color:inherit;text-decoration:underline;text-underline-offset:2px}',
    '.acx-foot{font-size:10.5px;line-height:1.75;color:var(--dim,#8a93a3);margin-top:2px;',
    'border-top:1px dashed var(--line,#2a2f3a);padding-top:9px}',
    '.acx-tbl{width:100%;border-collapse:collapse;font-family:' + MONO + ';font-size:10.5px;margin-top:4px}',
    '.acx-tbl th{text-align:right;color:var(--dim,#8a93a3);font-weight:600;padding:3px 6px;border-bottom:1px solid var(--line,#2a2f3a)}',
    '.acx-tbl th:first-child,.acx-tbl td:first-child{text-align:left}',
    '.acx-tbl td{text-align:right;padding:3px 6px;border-bottom:1px solid rgba(42,47,58,.45)}'
  ].join('');

  function ensureCss(doc) {
    if (!doc || doc.getElementById('aiCapexCss')) return;
    var s = doc.createElement('style');
    s.id = 'aiCapexCss';
    s.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(s);
  }

  /* ---------- 유틸 ---------- */
  function el(doc, cls, tag) {
    var d = doc.createElement(tag || 'div');
    if (cls) d.className = cls;
    return d;
  }
  function mnum(s) { return String(s).replace(/-/g, '−'); }
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function comma(v) {
    var neg = v < 0, a = Math.abs(v);
    var s = (Math.round(a * 10) / 10).toString();
    var p = s.split('.');
    p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (neg ? '−' : '') + p.join('.');
  }
  function isNum(v) { return typeof v === 'number' && isFinite(v); }

  /* {"2018-Q1":v,...} → [{k,v}] 정렬(‘_’로 시작하는 메타키 제외) */
  function toSeries(obj) {
    var out = [];
    if (!obj || typeof obj !== 'object') return out;
    for (var k in obj) {
      if (!Object.prototype.hasOwnProperty.call(obj, k)) continue;
      if (k.charAt(0) === '_') continue;
      if (!/^\d{4}-Q[1-4]$/.test(k)) continue;
      if (!isNum(obj[k])) continue;
      out.push({ k: k, v: obj[k] });
    }
    out.sort(function (a, b) { return a.k < b.k ? -1 : a.k > b.k ? 1 : 0; });
    return out;
  }
  function qLabel(k) { return k.slice(2, 4) + "'" + k.slice(6); }  // 2026-Q2 → 26'2
  function prevYearKey(k) {
    return (parseInt(k.slice(0, 4), 10) - 1) + k.slice(4);
  }
  function median(a) {
    if (!a.length) return NaN;
    var s = a.slice().sort(function (x, y) { return x - y; });
    var m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }
  function tail(a, n) { return (!n || a.length <= n) ? a.slice() : a.slice(a.length - n); }

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
      if (out.length >= 3 && out.length <= 6) return out;
    }
    return [lo, hi];
  }

  /* 단위 자동 스케일: 원자료가 백만 단위 → 값이 크면 십억(=/1000)으로 표시 */
  function pickScale(maxAbs) {
    return maxAbs >= 20000 ? { d: 1000, sfx: '십억', dec: 1 }
      : maxAbs >= 2000 ? { d: 1000, sfx: '십억', dec: 1 }
        : { d: 1, sfx: '백만', dec: 0 };
  }
  function fmtScaled(v, sc) {
    var x = v / sc.d;
    var dec = sc.dec;
    if (sc.d === 1) return comma(Math.round(x));
    if (Math.abs(x) >= 100) dec = 0;
    return comma(Math.round(x * Math.pow(10, dec)) / Math.pow(10, dec));
  }

  /* ---------- 급증 구간 판정 ---------- */
  /* 직전 4분기 중앙값 대비 SURGE_X배 이상이면 급증 */
  function surgeFlags(ser) {
    var f = [], i;
    for (i = 0; i < ser.length; i++) {
      if (i < 4) { f.push(false); continue; }
      var base = median([ser[i - 4].v, ser[i - 3].v, ser[i - 2].v, ser[i - 1].v]);
      f.push(isFinite(base) && base > 0 && ser[i].v >= base * SURGE_X);
    }
    return f;
  }

  /* ---------- 막대차트(값 라벨 + 급증 강조 + 0선) ---------- */
  /* opts: {ser, flags, mode:'capex'|'fcf', sc, labelEvery} */
  function barSvg(ser, opts) {
    var W = 760, H = 236, PL = 46, PR = 10, PT = 26, PB = 26;
    var PW = W - PL - PR, PH = H - PT - PB;
    var n = ser.length;
    if (!n) return '';
    var sc = opts.sc, isFcf = opts.mode === 'fcf';

    var vals = ser.map(function (d) { return d.v; });
    var dmax = Math.max.apply(null, vals), dmin = Math.min.apply(null, vals);
    var hi = Math.max(dmax, 0), lo = Math.min(dmin, 0);
    if (hi === lo) hi = lo + 1;
    var pad = (hi - lo) * 0.14;
    hi += pad; if (lo < 0) lo -= pad * 0.9;

    var ticks = niceTicks(lo, hi, 4);
    if (ticks.length) {
      lo = Math.min(lo, ticks[0]);
      hi = Math.max(hi, ticks[ticks.length - 1]);
    }
    var y = function (v) { return PT + PH - ((v - lo) / (hi - lo)) * PH; };
    var y0 = y(0);

    var slot = PW / n;
    var bw = Math.max(3, Math.min(30, slot * 0.66));
    var s = [];

    // 그리드 + y축 라벨
    for (var t = 0; t < ticks.length; t++) {
      var yy = y(ticks[t]);
      var zero = Math.abs(ticks[t]) < 1e-9;
      s.push('<line x1="' + PL + '" y1="' + yy.toFixed(1) + '" x2="' + (PL + PW) +
        '" y2="' + yy.toFixed(1) + '" style="stroke:' + (zero ? 'var(--ch-zero,rgba(230,233,239,.42))' : 'var(--line,#2a2f3a)') +
        '" stroke-width="' + (zero ? 1.2 : 1) + '" opacity="' + (zero ? 1 : .5) + '"/>');
      s.push('<text x="' + (PL - 7) + '" y="' + (yy + 3.4).toFixed(1) +
        '" text-anchor="end" font-family="' + MONO + '" font-size="9.5" style="fill:var(--dim,#8a93a3)' +
        '">' + esc(mnum(fmtScaled(ticks[t], sc))) + '</text>');
    }

    // 급증 구간 배경 밴드
    if (!isFcf && opts.flags) {
      var runS = -1;
      for (var b = 0; b <= n; b++) {
        var on = b < n && opts.flags[b];
        if (on && runS < 0) runS = b;
        if (!on && runS >= 0) {
          var x1 = PL + runS * slot, x2 = PL + b * slot;
          s.push('<rect x="' + x1.toFixed(1) + '" y="' + PT + '" width="' + (x2 - x1).toFixed(1) +
            '" height="' + PH + '" fill="rgba(43,192,212,.09)" stroke="rgba(43,192,212,.28)" ' +
            'stroke-width="1" stroke-dasharray="3 3" rx="4"/>');
          s.push('<text x="' + ((x1 + x2) / 2).toFixed(1) + '" y="' + (PT - 10) +
            '" text-anchor="middle" font-size="9.5" font-weight="700" fill="' + CLR.hi +
            '">급증 구간</text>');
          runS = -1;
        }
      }
    }

    // 막대 + 값 라벨
    var every = opts.labelEvery || 1;
    for (var i = 0; i < n; i++) {
      var d = ser[i], v = d.v;
      var cx = PL + i * slot + slot / 2;
      var top = v >= 0 ? y(v) : y0;
      var h = Math.max(1, Math.abs(y(v) - y0));
      var col = isFcf ? (v < 0 ? CLR.neg : CLR.pos)
        : (opts.flags && opts.flags[i] ? CLR.hi : CLR.bar);
      s.push('<rect x="' + (cx - bw / 2).toFixed(1) + '" y="' + top.toFixed(1) +
        '" width="' + bw.toFixed(1) + '" height="' + h.toFixed(1) + '" rx="2" fill="' + col +
        '"><title>' + esc(d.k + ' · ' + mnum(fmtScaled(v, sc)) + ' ' + sc.sfx) + '</title></rect>');

      var showLab = (i % every === 0) || i === n - 1 || (opts.flags && opts.flags[i]);
      if (showLab && bw >= 7) {
        var ly = v >= 0 ? top - 4.5 : top + h + 9.5;
        s.push('<text x="' + cx.toFixed(1) + '" y="' + ly.toFixed(1) +
          '" text-anchor="middle" font-family="' + MONO + '" font-size="9" font-weight="700" style="fill:' +
          (isFcf && v < 0 ? CLR.neg : (opts.flags && opts.flags[i] ? CLR.hi : 'var(--fg,#e6e9ef)')) +
          '">' + esc(mnum(fmtScaled(v, sc))) + '</text>');
      }
      // x축 라벨
      if (i % every === 0 || i === n - 1) {
        s.push('<text x="' + cx.toFixed(1) + '" y="' + (H - 8) +
          '" text-anchor="middle" font-family="' + MONO + '" font-size="9" style="fill:var(--dim,#8a93a3)' +
          '">' + esc(qLabel(d.k)) + '</text>');
      }
    }
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img">' + s.join('') + '</svg>';
  }

  /* ---------- 라인차트(capex intensity 다사 비교) ---------- */
  /* lines: [{name,color,pts:[{k,v}]}] , keys: 정렬된 전체 분기키 */
  function lineSvg(lines, keys) {
    var W = 760, H = 226, PL = 40, PR = 12, PT = 14, PB = 26;
    var PW = W - PL - PR, PH = H - PT - PB;
    var n = keys.length;
    if (!n || !lines.length) return '';
    var idx = {}, i;
    for (i = 0; i < n; i++) idx[keys[i]] = i;

    var all = [];
    for (i = 0; i < lines.length; i++) {
      for (var j = 0; j < lines[i].pts.length; j++) all.push(lines[i].pts[j].v);
    }
    if (!all.length) return '';
    var lo = 0, hi = Math.max.apply(null, all) * 1.12;
    var ticks = niceTicks(lo, hi, 4);
    if (ticks.length) hi = Math.max(hi, ticks[ticks.length - 1]);
    var X = function (k) { return n < 2 ? PL + PW : PL + (idx[k] / (n - 1)) * PW; };
    var Y = function (v) { return PT + PH - ((v - lo) / (hi - lo)) * PH; };

    var s = [];
    for (var t = 0; t < ticks.length; t++) {
      var yy = Y(ticks[t]);
      s.push('<line x1="' + PL + '" y1="' + yy.toFixed(1) + '" x2="' + (PL + PW) + '" y2="' + yy.toFixed(1) +
        '" style="stroke:var(--line,#2a2f3a)" stroke-width="1" opacity=".5"/>');
      s.push('<text x="' + (PL - 6) + '" y="' + (yy + 3.4).toFixed(1) + '" text-anchor="end" font-family="' +
        MONO + '" font-size="9.5" style="fill:var(--dim,#8a93a3)">' + ticks[t].toFixed(0) + '%</text>');
    }
    var step = Math.max(1, Math.ceil(n / 12));
    for (i = 0; i < n; i += step) {
      s.push('<text x="' + X(keys[i]).toFixed(1) + '" y="' + (H - 8) + '" text-anchor="middle" font-family="' +
        MONO + '" font-size="9" style="fill:var(--dim,#8a93a3)">' + esc(qLabel(keys[i])) + '</text>');
    }

    for (i = 0; i < lines.length; i++) {
      var L = lines[i], dpath = '', k;
      for (var p = 0; p < L.pts.length; p++) {
        if (!(L.pts[p].k in idx)) continue;
        dpath += (dpath ? 'L' : 'M') + X(L.pts[p].k).toFixed(1) + ' ' + Y(L.pts[p].v).toFixed(1);
      }
      if (!dpath) continue;
      s.push('<path d="' + dpath + '" fill="none" stroke="' + L.color +
        '" stroke-width="1.9" stroke-linejoin="round" stroke-linecap="round" opacity=".95"/>');
      var last = L.pts[L.pts.length - 1];
      if (last && (last.k in idx)) {
        s.push('<circle cx="' + X(last.k).toFixed(1) + '" cy="' + Y(last.v).toFixed(1) +
          '" r="2.8" fill="' + L.color + '" style="stroke:var(--panel,#12161d)" stroke-width="1.2"><title>' +
          esc(L.name + ' ' + last.k + ' · ' + last.v.toFixed(1) + '%') + '</title></circle>');
      }
    }
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img">' + s.join('') + '</svg>';
  }

  /* ---------- 배지 ---------- */
  function badge(doc, txt, color) {
    var b = el(doc, 'acx-badge', 'span');
    b.textContent = txt;
    b.style.color = color;
    b.style.borderColor = color;
    b.style.background = 'color-mix(in srgb,' + color + ' 13%, transparent)';
    return b;
  }

  /* 자동 판정 */
  function judge(co, note) {
    var out = [];
    var capex = toSeries(co.q || co.capex);
    var fcf = toSeries(co.fcf);
    var i;

    // 🔥 CAPEX YoY
    if (capex.length) {
      var last = capex[capex.length - 1];
      var pk = prevYearKey(last.k), prev = null;
      for (i = 0; i < capex.length; i++) if (capex[i].k === pk) prev = capex[i];
      if (prev && prev.v > 0) {
        var yoy = (last.v / prev.v - 1) * 100;
        if (yoy >= 30) {
          out.push(['🔥 CAPEX YoY +' + Math.round(yoy) + '% (' + last.k + ')',
            yoy >= 100 ? CLR.neg : CLR.warn]);
        } else if (yoy <= -20) {
          out.push(['❄ CAPEX YoY ' + mnum(Math.round(yoy)) + '% (' + last.k + ')', CLR.dim]);
        }
      }
    }

    // ⛔ FCF 적자 전환
    if (fcf.length && fcf[fcf.length - 1].v < 0) {
      var cnt = 0;
      for (i = fcf.length - 2; i >= 0; i--) { if (fcf[i].v < 0) break; cnt++; }
      out.push(['⛔ FCF 적자 전환' + (cnt > 0 ? ' (' + cnt + '분기 만)' : ''), CLR.neg]);
    }

    // ⚠ 가이던스 미제시
    var g = co.guidance;
    var noGuide = (g === null || g === undefined) ||
      (typeof g === 'object' && !(g instanceof Array) &&
        (g.value === null || g.value === undefined) &&
        (g.provided === false || g.provided === undefined) &&
        !g.text) ||
      (g instanceof Array && !g.length);
    if (noGuide) out.push(['⚠ 연간 CAPEX 가이던스 미제시', CLR.warn]);
    else if (typeof g === 'object' && g.provided === false) out.push(['⚠ 연간 CAPEX 가이던스 미제시', CLR.warn]);

    // 🙅 애널리스트 질문 회피
    if (note) {
      var calls = note.calls || [], ev = 0, sup = 0;
      for (i = 0; i < calls.length; i++) {
        var qs = calls[i].quotes || [];
        for (var j = 0; j < qs.length; j++) {
          var q = qs[j];
          if (q.evaded === true || /회피/.test(q.signal || '')) ev++;
          if (/공급제약|capacity|supply/i.test(q.signal || '')) sup++;
        }
      }
      if (ev) out.push(['🙅 애널 질문 회피 ' + ev + '건', CLR.purple]);
      if (sup) out.push(['🚧 공급/전력 제약 언급', '#4ea1ff']);
    }
    return out;
  }

  /* ---------- 인용문 접기 ---------- */
  function quoteEl(doc, q) {
    var d = el(doc, 'acx-q', 'details');
    var sm = doc.createElement('summary');
    var who = el(doc, 'acx-qwho', 'span');
    who.textContent = (q.speaker || '—');
    who.style.color = q.role === 'analyst' ? CLR.purple : CLR.hi;
    sm.appendChild(who);
    var head = doc.createElement('span');
    head.style.color = 'var(--dim,#8a93a3)';
    head.style.minWidth = '0';
    head.style.overflow = 'hidden';
    head.style.textOverflow = 'ellipsis';
    head.style.whiteSpace = 'nowrap';
    head.textContent = ' ' + String(q.en || q.ko || '').slice(0, 78) + '…';
    sm.appendChild(head);
    if (q.signal) {
      var sg = el(doc, 'acx-qsig', 'span');
      sg.textContent = q.signal;
      var c = /회피/.test(q.signal) ? CLR.purple
        : /미제시|압박/.test(q.signal) ? CLR.warn
          : /FCF|악화|적자/.test(q.signal) ? CLR.neg : CLR.hi;
      sg.style.color = c; sg.style.borderColor = c;
      sm.appendChild(sg);
    }
    d.appendChild(sm);
    var body = el(doc, 'acx-qbody');
    if (q.en) { var p = el(doc, 'acx-en', 'p'); p.textContent = '“' + q.en + '”'; body.appendChild(p); }
    if (q.ko) { var k = el(doc, 'acx-ko', 'p'); k.textContent = '→ ' + q.ko; body.appendChild(k); }
    d.appendChild(body);
    return d;
  }

  /* ---------- 메인 ---------- */
  function renderAICapex(root, data, notes) {
    if (!root) return;
    var doc = root.ownerDocument || (typeof document !== 'undefined' ? document : null);
    if (!doc) return;
    ensureCss(doc);
    root.textContent = '';

    data = data || {};
    var COS = data.companies || data || {};
    notes = notes || data.transcript_notes || data.notes ||
      (typeof window !== 'undefined' ? window.__aiTranscriptNotes : null) || {};

    var tickers = [];
    for (var tk in COS) {
      if (!Object.prototype.hasOwnProperty.call(COS, tk)) continue;
      if (tk.charAt(0) === '_') continue;
      if (!COS[tk] || typeof COS[tk] !== 'object') continue;
      tickers.push(tk);
    }
    // CAPEX 최신값 큰 순 → 데이터 많은 순
    tickers.sort(function (a, b) {
      var sa = toSeries(COS[a].q || COS[a].capex), sb = toSeries(COS[b].q || COS[b].capex);
      return sb.length - sa.length;
    });

    var wrap = el(doc, 'acx');
    root.appendChild(wrap);

    if (!tickers.length) {
      var e0 = el(doc, 'acx-empty'); e0.textContent = '표시할 데이터가 없습니다.';
      wrap.appendChild(e0); return;
    }

    /* 헤더 */
    var head = el(doc, 'acx-head');
    var ttl = el(doc, 'acx-title', 'span');
    ttl.textContent = '빅테크·클라우드 분기 CAPEX · FCF';
    head.appendChild(ttl);
    var meta = data._meta || {};
    var asof = el(doc, 'acx-asof', 'span');
    asof.textContent = (meta.asof || meta.generated || '') +
      (meta.anchor_ok ? ' · 텐센트 앵커 정합 ✓' : '');
    head.appendChild(asof);
    wrap.appendChild(head);

    /* 상태 */
    var state = { co: tickers[0], per: DEFAULT_PERIOD };

    /* 회사 칩 */
    var chipbar = el(doc, 'acx-bar');
    var chips = el(doc, 'acx-chips');
    chipbar.appendChild(chips);
    var pchips = el(doc, 'acx-chips');
    chipbar.appendChild(pchips);
    wrap.appendChild(chipbar);

    var detail = el(doc, 'acx-grid');
    wrap.appendChild(detail);
    var panel = el(doc, 'acx-key');
    wrap.appendChild(panel);

    var coBtns = {}, perBtns = {};
    tickers.forEach(function (tk) {
      var b = el(doc, 'acx-chip', 'button');
      b.type = 'button';
      b.textContent = COS[tk].name || tk;
      b.addEventListener('click', function () { state.co = tk; paint(); });
      coBtns[tk] = b; chips.appendChild(b);
    });
    PERIODS.forEach(function (p) {
      var b = el(doc, 'acx-chip sm', 'button');
      b.type = 'button'; b.textContent = p.k;
      b.addEventListener('click', function () { state.per = p.k; paint(); });
      perBtns[p.k] = b; pchips.appendChild(b);
    });

    /* intensity 비교 (전체 사, 상태 무관) */
    var cmp = el(doc, 'acx-card');
    (function () {
      var ch = el(doc, 'acx-cardhead');
      var t = el(doc, 'acx-t', 'span');
      t.innerHTML = 'CAPEX intensity 다사 비교 <em>· 분기 CAPEX ÷ 분기 매출 (%)</em>';
      ch.appendChild(t);
      cmp.appendChild(ch);

      var lines = [], keyset = {}, ci = 0;
      tickers.forEach(function (tk) {
        var co = COS[tk];
        var cap = co.q || co.capex, rev = co.revenue;
        if (!cap || !rev) return;
        var pts = [], ser = toSeries(cap);
        for (var i = 0; i < ser.length; i++) {
          var r = rev[ser[i].k];
          if (!isNum(r) || r <= 0) continue;
          pts.push({ k: ser[i].k, v: (ser[i].v / r) * 100 });
          keyset[ser[i].k] = 1;
        }
        if (pts.length < 3) return;
        lines.push({ name: co.name || tk, color: SERIES[ci % SERIES.length], pts: pts, tk: tk });
        ci++;
      });
      var keys = Object.keys(keyset).sort();
      // 최근 24분기로 제한
      keys = tail(keys, 24);
      var kin = {}; keys.forEach(function (k) { kin[k] = 1; });
      lines.forEach(function (L) {
        L.pts = L.pts.filter(function (p) { return kin[p.k]; });
      });
      lines = lines.filter(function (L) { return L.pts.length >= 2; });

      if (!lines.length) {
        var e = el(doc, 'acx-empty'); e.textContent = '매출 데이터가 있는 회사가 부족합니다.';
        cmp.appendChild(e);
      } else {
        var plot = el(doc, 'acx-plot');
        plot.innerHTML = lineSvg(lines, keys);
        cmp.appendChild(plot);
        var lg = el(doc, 'acx-lgd');
        lines.forEach(function (L) {
          var g = el(doc, 'acx-lg', 'span');
          var sw = el(doc, 'acx-sw ln', 'i');
          sw.style.background = L.color;
          g.appendChild(sw);
          g.appendChild(doc.createTextNode(L.name));
          lg.appendChild(g);
        });
        cmp.appendChild(lg);
      }
    })();

    function paint() {
      tickers.forEach(function (tk) {
        coBtns[tk].className = 'acx-chip' + (tk === state.co ? ' on' : '');
      });
      PERIODS.forEach(function (p) {
        perBtns[p.k].className = 'acx-chip sm' + (p.k === state.per ? ' on' : '');
      });

      var tk = state.co, co = COS[tk] || {};
      var nWin = 12;
      for (var pi = 0; pi < PERIODS.length; pi++) if (PERIODS[pi].k === state.per) nWin = PERIODS[pi].n;

      var unit = co.unit || 'mil', ccy = co.ccy || '';
      var capexAll = toSeries(co.q || co.capex);
      var fcfAll = toSeries(co.fcf);
      var flagsAll = surgeFlags(capexAll);

      var capex = tail(capexAll, nWin);
      var flags = tail(flagsAll, nWin);
      var fcf = tail(fcfAll, nWin);

      detail.textContent = '';

      /* --- CAPEX 카드 --- */
      var c1 = el(doc, 'acx-card');
      var h1 = el(doc, 'acx-cardhead');
      var t1 = el(doc, 'acx-t', 'span');
      t1.innerHTML = esc(co.name || tk) + ' 분기 CAPEX';
      h1.appendChild(t1);
      var v1 = el(doc, 'acx-v', 'span');
      if (capexAll.length) {
        var lastC = capexAll[capexAll.length - 1];
        var scL = pickScale(Math.max.apply(null, capexAll.map(function (d) { return Math.abs(d.v); })));
        v1.textContent = lastC.k + ' ' + fmtScaled(lastC.v, scL) + ' ' + scL.sfx + ' ' + ccy;
        v1.style.color = CLR.hi;
      } else { v1.textContent = '—'; v1.style.color = CLR.dim; }
      h1.appendChild(v1);
      c1.appendChild(h1);
      var s1 = el(doc, 'acx-sub');
      s1.textContent = '정의: ' + (co.capex_def || '회사 공시 기준') +
        ' · 단위 ' + unit + ' ' + ccy + ' · ' + capexAll.length + '개 분기';
      c1.appendChild(s1);
      if (capex.length) {
        var sc1 = pickScale(Math.max.apply(null, capex.map(function (d) { return Math.abs(d.v); })));
        var p1 = el(doc, 'acx-plot');
        p1.innerHTML = barSvg(capex, {
          mode: 'capex', flags: flags, sc: sc1,
          labelEvery: capex.length > 16 ? 2 : 1
        });
        c1.appendChild(p1);
        var lg1 = el(doc, 'acx-lgd');
        [[CLR.bar, '분기 CAPEX'], [CLR.hi, '급증 구간(직전 4분기 중앙값 ×' + SURGE_X + ' 이상)']]
          .forEach(function (x) {
            var g = el(doc, 'acx-lg', 'span');
            var sw = el(doc, 'acx-sw', 'i'); sw.style.background = x[0];
            g.appendChild(sw); g.appendChild(doc.createTextNode(x[1])); lg1.appendChild(g);
          });
        c1.appendChild(lg1);
      } else {
        var e1 = el(doc, 'acx-empty'); e1.textContent = 'CAPEX 데이터 없음'; c1.appendChild(e1);
      }
      detail.appendChild(c1);

      /* --- FCF 카드 --- */
      var c2 = el(doc, 'acx-card');
      var h2 = el(doc, 'acx-cardhead');
      var t2 = el(doc, 'acx-t', 'span');
      var drv = co.fcf_reported === false || co.fcf_derived === true;
      t2.innerHTML = esc(co.name || tk) + ' 분기 FCF' +
        (drv ? ' <em>· 파생(OCF − CAPEX)</em>' : ' <em>· 회사 공시</em>');
      h2.appendChild(t2);
      var v2 = el(doc, 'acx-v', 'span');
      if (fcfAll.length) {
        var lastF = fcfAll[fcfAll.length - 1];
        var scF = pickScale(Math.max.apply(null, fcfAll.map(function (d) { return Math.abs(d.v); })));
        v2.textContent = lastF.k + ' ' + mnum(fmtScaled(lastF.v, scF)) + ' ' + scF.sfx + ' ' + ccy;
        v2.style.color = lastF.v < 0 ? CLR.neg : CLR.pos;
      } else { v2.textContent = '—'; v2.style.color = CLR.dim; }
      h2.appendChild(v2);
      c2.appendChild(h2);
      var s2 = el(doc, 'acx-sub');
      s2.textContent = (co.fcf_def || (drv ? 'FCF = 영업현금흐름 − CAPEX (자체 계산)' : '회사 공시 FCF')) +
        ' · ' + fcfAll.length + '개 분기';
      c2.appendChild(s2);
      if (fcf.length) {
        var sc2 = pickScale(Math.max.apply(null, fcf.map(function (d) { return Math.abs(d.v); })));
        var p2 = el(doc, 'acx-plot');
        p2.innerHTML = barSvg(fcf, { mode: 'fcf', sc: sc2, labelEvery: fcf.length > 16 ? 2 : 1 });
        c2.appendChild(p2);
        var lg2 = el(doc, 'acx-lgd');
        [[CLR.pos, 'FCF 플러스'], [CLR.neg, 'FCF 마이너스'], ['rgba(230,233,239,.42)', '0선']]
          .forEach(function (x) {
            var g = el(doc, 'acx-lg', 'span');
            var sw = el(doc, 'acx-sw', 'i'); sw.style.background = x[0];
            g.appendChild(sw); g.appendChild(doc.createTextNode(x[1])); lg2.appendChild(g);
          });
        c2.appendChild(lg2);
      } else {
        var e2 = el(doc, 'acx-empty');
        e2.textContent = co.fcf_note || 'FCF 데이터 없음(분기 현금흐름 미공시)';
        c2.appendChild(e2);
      }
      detail.appendChild(c2);

      /* --- 최근 분기 수치표 --- */
      if (capexAll.length) {
        var c3 = el(doc, 'acx-card');
        c3.style.gridColumn = '1 / -1';
        var h3 = el(doc, 'acx-cardhead');
        var t3 = el(doc, 'acx-t', 'span');
        t3.innerHTML = '최근 분기 수치 <em>· CAPEX / YoY / intensity / FCF / FCF마진</em>';
        h3.appendChild(t3);
        c3.appendChild(h3);

        var rows = tail(capexAll, 8);
        var scT = pickScale(Math.max.apply(null, rows.map(function (d) { return Math.abs(d.v); })));
        var tb = el(doc, 'acx-tbl', 'table');
        var thead = doc.createElement('thead');
        var trh = doc.createElement('tr');
        ['분기', 'CAPEX(' + scT.sfx + ' ' + ccy + ')', 'YoY', 'intensity', 'FCF', 'FCF마진']
          .forEach(function (x) {
            var th = doc.createElement('th'); th.textContent = x; trh.appendChild(th);
          });
        thead.appendChild(trh); tb.appendChild(thead);
        var tbody = doc.createElement('tbody');
        rows.forEach(function (d) {
          var tr = doc.createElement('tr');
          function td(txt, color) {
            var x = doc.createElement('td');
            x.textContent = txt;
            if (color) x.style.color = color;
            tr.appendChild(x);
          }
          td(d.k);
          td(fmtScaled(d.v, scT));
          var yv = (co.capex_yoy || {})[d.k];
          td(isNum(yv) ? mnum((yv > 0 ? '+' : '') + yv.toFixed(0)) + '%' : '—',
            isNum(yv) ? (yv >= 50 ? CLR.warn : yv < 0 ? CLR.dim : '') : '');
          var iv = (co.capex_intensity || {})[d.k];
          td(isNum(iv) ? iv.toFixed(1) + '%' : '—');
          var fv = (co.fcf || {})[d.k];
          td(isNum(fv) ? mnum(fmtScaled(fv, scT)) : '—',
            isNum(fv) ? (fv < 0 ? CLR.neg : CLR.pos) : '');
          var mv = (co.fcf_margin || {})[d.k];
          td(isNum(mv) ? mnum(mv.toFixed(1)) + '%' : '—',
            isNum(mv) ? (mv < 0 ? CLR.neg : '') : '');
          tbody.appendChild(tr);
        });
        tb.appendChild(tbody);
        c3.appendChild(tb);
        detail.appendChild(c3);
      }

      detail.appendChild(cmp);
      cmp.style.gridColumn = '1 / -1';

      /* --- 해석 패널 --- */
      panel.textContent = '';
      var note = notes[tk] || null;
      var kt = el(doc, 'acx-keyt');
      kt.appendChild(doc.createTextNode('해석 · ' + (co.name || tk) +
        (note && note.calls && note.calls.length ? ' — 컨콜 ' + note.calls.length + '개' : ' — 트랜스크립트 미확보')));
      panel.appendChild(kt);

      var bs = el(doc, 'acx-badges');
      var js = judge(co, note);
      if (!js.length) bs.appendChild(badge(doc, '· 특이 신호 없음', CLR.dim));
      js.forEach(function (x) { bs.appendChild(badge(doc, x[0], x[1])); });
      panel.appendChild(bs);

      if (note && note.reading) {
        var rd = el(doc, 'acx-read');
        rd.textContent = note.reading;
        panel.appendChild(rd);
      }
      if (co.guidance_note) {
        var gn = el(doc, 'acx-read');
        gn.textContent = '가이던스: ' + co.guidance_note;
        panel.appendChild(gn);
      }

      if (note && note.calls) {
        var shown = 0;
        for (var ci2 = 0; ci2 < note.calls.length && shown < 6; ci2++) {
          var call = note.calls[ci2], qs = call.quotes || [];
          for (var qi = 0; qi < qs.length && shown < 6; qi++) {
            panel.appendChild(quoteEl(doc, qs[qi]));
            shown++;
          }
          if (call.src) {
            var sr = el(doc, 'acx-src');
            var a = doc.createElement('a');
            a.href = call.src; a.target = '_blank'; a.rel = 'noopener noreferrer';
            a.textContent = (call.quarter || '') + ' 트랜스크립트: ' + call.src;
            sr.appendChild(a);
            panel.appendChild(sr);
          }
        }
      }

      var ft = el(doc, 'acx-foot');
      var srcs = (co.src || []).slice(0, 4);
      ft.textContent = '출처: ' + (srcs.length ? srcs.join('  ·  ') : '회사 IR 공시') +
        (co.notes ? '  |  ' + co.notes : '');
      panel.appendChild(ft);
    }

    paint();
  }

  if (typeof window !== 'undefined') window.renderAICapex = renderAICapex;
  else if (typeof globalThis !== 'undefined') globalThis.renderAICapex = renderAICapex;
})();
