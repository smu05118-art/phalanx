/* shipping_charts.js — 파놉테스 🚢 해운·탱커 탭 렌더러 (의존성 0, 순수 SVG)
 * 전역: window.renderShipping(el, data)   data = shipping.json 전체 객체
 * 로드 시 부작용 없음(함수 정의만). 외부 라이브러리·fetch 사용 안 함.
 * 문법 참고: tech_charts.js (다크테마·기간칩·호버·기준선·표시윈도 y도메인).
 */
(function () {
  'use strict';

  var PERIODS = [
    { k: '1M', d: 31, m: 12 }, { k: '3M', d: 92, m: 24 },
    { k: '6M', d: 184, m: 36 }, { k: '1Y', d: 366, m: 60 },
    { k: '2Y', d: 731, m: 120 }, { k: 'ALL', d: 1e9, m: 1e9 }
  ];
  var DEFAULT_PERIOD = '6M';

  var CATS = ['chokepoint', 'freight', 'fleet', 'trade', 'korea'];
  var CAT_ICON = { chokepoint: '⚓', freight: '💵', fleet: '🛢', trade: '📦', korea: '🇰🇷' };
  // 카테고리별 계열 색 팔레트
  var PAL = ['#4ea1ff', '#59d0a8', '#f6c85f', '#e07a5f', '#b892ff', '#2bc0d4', '#ff8a3d', '#7ec8e3'];
  var UP = '#59d0a8', DOWN = '#ff5e6c', DIM = '#8a93a3';

  // 요약 카드에 올릴 핵심 지표(cat, sid, 짧은라벨, "감소가 강세" 방향?)
  var SUMMARY = [
    ['chokepoint', 'cp_suez', '수에즈 통항', true],
    ['chokepoint', 'cp_cogh', '희망봉 우회', false],
    ['chokepoint', 'cp_bab', '홍해 통항', true],
    ['freight', 'ppi_deepsea', '원양운임 PPI', false],
    ['chokepoint', 'cp_malacca', '말라카 통항', false],
    ['freight', 'cass_ship', 'Cass 물동량', false]
  ];

  var W = 560, H = 188, PL = 10, PR = 48, PT = 16, PB = 22;
  var PW = W - PL - PR, PH = H - PT - PB;
  var MONO = 'var(--mono,ui-monospace,SFMono-Regular,Menlo,monospace)';

  var CSS = [
    '.sh-wrap{display:flex;flex-direction:column;gap:16px}',
    '.sh-head{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}',
    '.sh-title{font-size:15px;font-weight:800;letter-spacing:-.01em}',
    '.sh-sub{font-size:11px;color:' + DIM + ';font-weight:550;margin-top:2px}',
    '.sh-chips{display:flex;gap:6px;flex-wrap:wrap}',
    '.sh-chip{font:inherit;font-size:11.5px;line-height:1.5;padding:3px 9px;border:1px solid var(--line,#2a2f3a);',
    'border-radius:999px;background:transparent;color:' + DIM + ';cursor:pointer;transition:all .12s}',
    '.sh-chip:hover{border-color:rgba(43,192,212,.5);color:#2bc0d4}',
    '.sh-chip.on{background:rgba(43,192,212,.14);color:#2bc0d4;border-color:rgba(43,192,212,.45)}',
    '.sh-cards{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}',
    '@media (max-width:1100px){.sh-cards{grid-template-columns:repeat(3,1fr)}}',
    '@media (max-width:640px){.sh-cards{grid-template-columns:repeat(2,1fr)}}',
    '.sh-kpi{background:var(--panel,#12161d);border:1px solid var(--line,#2a2f3a);border-radius:12px;padding:11px 12px;min-width:0}',
    '.sh-kpi .lab{font-size:11px;color:' + DIM + ';font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.sh-kpi .val{font-family:' + MONO + ';font-size:17px;font-weight:800;margin-top:3px;letter-spacing:-.02em}',
    '.sh-kpi .dl{display:flex;gap:8px;margin-top:4px;font-family:' + MONO + ';font-size:10.5px}',
    '.sh-kpi .dl span em{font-style:normal;color:' + DIM + '}',
    '.sh-sec{display:flex;flex-direction:column;gap:11px}',
    '.sh-sech{display:flex;align-items:baseline;gap:8px}',
    '.sh-sech h3{font-size:13px;font-weight:750;margin:0}',
    '.sh-sech .cnt{font-size:11px;color:' + DIM + '}',
    '.sh-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}',
    '@media (max-width:920px){.sh-grid{grid-template-columns:1fr}}',
    '.sh-card{background:var(--panel,#12161d);border:1px solid var(--line,#2a2f3a);border-radius:13px;padding:13px 15px;min-width:0}',
    '.sh-ch{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:2px}',
    '.sh-ct{font-size:12px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.sh-ct em{font-style:normal;color:' + DIM + ';font-weight:550;font-size:11px}',
    '.sh-cv{font-family:' + MONO + ';font-size:12.5px;font-weight:750;white-space:nowrap}',
    '.sh-badge{display:inline-block;font-size:9.5px;font-weight:700;padding:1px 6px;border-radius:999px;margin-left:6px;vertical-align:1px}',
    '.sh-note{font-size:10px;color:' + DIM + ';margin-top:3px}',
    '.sh-plot{position:relative}',
    '.sh-plot svg{display:block;width:100%;height:auto;overflow:visible}',
    '.sh-guide{opacity:0}.sh-plot.on .sh-guide{opacity:1}',
    '.sh-tip{position:absolute;top:2px;transform:translateX(-50%);pointer-events:none;opacity:0;',
    'background:rgba(10,12,16,.92);border:1px solid var(--line,#2a2f3a);border-radius:6px;padding:3px 7px;',
    'font-family:' + MONO + ';font-size:10.5px;color:#e6e9ef;white-space:nowrap;z-index:3;transition:opacity .1s}',
    '.sh-plot.on .sh-tip{opacity:1}',
    '.sh-empty{font-size:11.5px;color:' + DIM + ';padding:10px 0}',
    '.sh-story{background:linear-gradient(180deg,rgba(43,192,212,.06),rgba(43,192,212,.02));',
    'border:1px solid rgba(43,192,212,.28);border-radius:13px;padding:14px 16px}',
    '.sh-story h3{margin:0 0 7px;font-size:13px;font-weight:750;color:#2bc0d4}',
    '.sh-story p{margin:0;font-size:12.5px;line-height:1.7;color:var(--text,#dfe4ec)}',
    '.sh-story b{color:#fff;font-weight:750}',
    '.sh-story .u{color:' + UP + '}.sh-story .d{color:' + DOWN + '}',
    '.sh-foot{font-size:10.5px;color:' + DIM + ';line-height:1.6}'
  ].join('');

  function ensureCss(doc) {
    if (!doc || doc.getElementById('shipChartsCss')) return;
    var s = doc.createElement('style');
    s.id = 'shipChartsCss';
    s.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(s);
  }

  /* ---------------- helpers ---------------- */
  function mnum(v) { return String(v).replace('-', '−'); }
  function compact(v) {
    var a = Math.abs(v), s;
    if (a >= 1e9) s = (v / 1e9).toFixed(2) + 'B';
    else if (a >= 1e6) s = (v / 1e6).toFixed(2) + 'M';
    else if (a >= 1e4) s = (v / 1e3).toFixed(0) + 'K';
    else if (a >= 1e3) s = (v / 1e3).toFixed(1) + 'K';
    else if (a >= 100) s = v.toFixed(0);
    else s = (Math.abs(v % 1) < 1e-9 ? v.toFixed(0) : v.toFixed(1));
    return mnum(s);
  }
  function fmtVal(v, unit) {
    if (v == null || isNaN(v)) return '—';
    if (unit === 'DWT') return compact(v);
    if (unit === '$/bbl') return mnum(v.toFixed(1));
    if (unit === '지수') return mnum(v.toFixed(1));
    if (unit === '천명') return mnum(v.toFixed(1));
    if (unit === '척/일') return mnum(Math.round(v).toString());
    return compact(v);
  }
  function tickTxt(v) {
    var a = Math.abs(v);
    if (a >= 1e4) return compact(v);
    return mnum(a % 1 < 0.05 ? v.toFixed(0) : v.toFixed(1));
  }
  function tail(a, n) { return a.length > n ? a.slice(a.length - n) : a.slice(); }
  function median(a) {
    if (!a.length) return null;
    var b = a.slice().sort(function (x, y) { return x - y; });
    var m = b.length >> 1;
    return b.length % 2 ? b[m] : (b[m - 1] + b[m]) / 2;
  }
  function mavg(vals, w) {
    if (w <= 1) return vals.slice();
    var out = [], sum = 0, q = [];
    for (var i = 0; i < vals.length; i++) {
      q.push(vals[i]); sum += vals[i];
      if (q.length > w) sum -= q.shift();
      out.push(sum / q.length);
    }
    return out;
  }
  function niceTicks(lo, hi, count) {
    var span = hi - lo;
    if (!(span > 0)) return [lo];
    for (var c = count; c >= 2; c--) {
      var raw = span / c;
      var mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
      var nrm = raw / mag;
      var step = (nrm <= 1 ? 1 : nrm <= 2 ? 2 : nrm <= 2.5 ? 2.5 : nrm <= 5 ? 5 : 10) * mag;
      var out = [];
      for (var v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step)
        out.push(Math.round(v * 1e6) / 1e6);
      if (out.length <= 5) return out;
    }
    return [];
  }
  function xAt(i, n) { return n < 2 ? PL + PW : PL + (i / (n - 1)) * PW; }

  /* series obj → {dates:[], vals:[]} sorted, windowed */
  function seriesArr(s, period) {
    var seq = s.d || s.m || {};
    var keys = Object.keys(seq).sort();
    var dates = [], vals = [];
    for (var i = 0; i < keys.length; i++) {
      var v = seq[keys[i]];
      if (v == null || isNaN(v)) continue;
      dates.push(keys[i]); vals.push(+v);
    }
    var pdef = PERIODS[2];
    for (var p = 0; p < PERIODS.length; p++) if (PERIODS[p].k === period) pdef = PERIODS[p];
    var take = (s.freq === 'M') ? pdef.m : pdef.d;
    return { dates: tail(dates, take), vals: tail(vals, take), full: { dates: dates, vals: vals } };
  }
  function deltaPct(vals, back) {
    var n = vals.length;
    if (n < 2) return null;
    var j = n - 1 - back;
    if (j < 0) j = 0;
    var a = vals[j], b = vals[n - 1];
    if (!a) return null;
    return (b - a) / Math.abs(a) * 100;
  }
  function deltaSpan(vals, dates, freq, back) {
    // 반환 {pct, lab}
    var lab = freq === 'M'
      ? (back === 1 ? 'Δ1M' : 'Δ' + back + 'M')
      : (back === 7 ? 'Δ1주' : back === 28 ? 'Δ4주' : 'Δ' + back + 'd');
    return { pct: deltaPct(vals, back), lab: lab };
  }

  /* ---------------- KPI 요약 카드 ---------------- */
  function kpiTile(doc, data, spec, period) {
    var cat = data.cats[spec[0]]; if (!cat) return null;
    var s = cat.series[spec[1]]; if (!s) return null;
    var A = seriesArr(s, period);
    var vals = A.full.vals, dates = A.full.dates;
    if (!vals.length) return null;
    var last = vals[vals.length - 1];
    var isM = s.freq === 'M';
    var d1 = deltaSpan(vals, dates, s.freq, isM ? 1 : 7);
    var d2 = deltaSpan(vals, dates, s.freq, isM ? 3 : 28);

    var tile = doc.createElement('div'); tile.className = 'sh-kpi';
    var lab = doc.createElement('div'); lab.className = 'lab'; lab.textContent = spec[2];
    var val = doc.createElement('div'); val.className = 'val';
    val.textContent = fmtVal(last, s.unit);
    var dl = doc.createElement('div'); dl.className = 'dl';
    [d1, d2].forEach(function (dd) {
      var sp = doc.createElement('span');
      if (dd.pct == null) { sp.innerHTML = '<em>' + dd.lab + '</em> —'; }
      else {
        var col = dd.pct >= 0 ? UP : DOWN;
        var arr = dd.pct >= 0 ? '▲' : '▼';
        sp.innerHTML = '<em>' + dd.lab + '</em> <b style="color:' + col + '">' +
          arr + mnum(Math.abs(dd.pct).toFixed(1)) + '%</b>';
      }
      dl.appendChild(sp);
    });
    tile.appendChild(lab); tile.appendChild(val); tile.appendChild(dl);
    return tile;
  }

  /* ---------------- 라인 차트 카드 ---------------- */
  function buildCard(doc, s, sid, color, period) {
    var A = seriesArr(s, period);
    var dates = A.dates, raw = A.vals, n = raw.length;
    var isD = s.freq !== 'M';
    var smooth = isD && n > 20;
    var vals = smooth ? mavg(raw, 7) : raw;

    var card = doc.createElement('div'); card.className = 'sh-card';
    var head = doc.createElement('div'); head.className = 'sh-ch';
    var t = doc.createElement('span'); t.className = 'sh-ct';
    t.innerHTML = s.name + ' <em>' + (isD ? '/일' : '월간') + (smooth ? ' ·7d MA' : '') + '</em>';
    head.appendChild(t);
    var cv = doc.createElement('span'); cv.className = 'sh-cv'; cv.style.color = color;
    head.appendChild(cv);
    card.appendChild(head);

    if (n < 2) {
      var e = doc.createElement('div'); e.className = 'sh-empty';
      e.textContent = '표시할 데이터가 없습니다.'; card.appendChild(e); return card;
    }
    var last = vals[n - 1], lastRaw = raw[n - 1];
    cv.textContent = fmtVal(lastRaw, s.unit);

    // 기준선: 초크포인트/선복/교역=2023 평균(base), 운임=표시구간 중앙값
    var baseV, baseLab;
    if (s.freq === 'M') { baseV = median(vals); baseLab = '기간 중앙값'; }
    else { baseV = (s.base != null ? s.base : median(vals)); baseLab = (s.base != null ? '2023 정상' : '중앙값'); }

    // 이탈 배지
    if (baseV) {
      var dev = (lastRaw - baseV) / Math.abs(baseV) * 100;
      if (Math.abs(dev) >= 12) {
        var up = dev >= 0;
        var b = doc.createElement('span'); b.className = 'sh-badge';
        b.style.background = (up ? 'rgba(89,208,168,.16)' : 'rgba(255,94,108,.16)');
        b.style.color = up ? UP : DOWN;
        b.textContent = (up ? '+' : '−') + Math.abs(dev).toFixed(0) + '% vs ' + baseLab;
        head.insertBefore(b, cv);
      }
    }

    var dmin = Math.min.apply(null, vals), dmax = Math.max.apply(null, vals);
    if (baseV != null) { dmin = Math.min(dmin, baseV); dmax = Math.max(dmax, baseV); }
    var pad = (dmax - dmin) * 0.06 || Math.abs(dmax) * 0.05 || 1;
    var lo = dmin - pad, hi = dmax + pad;
    function Y(v) { return PT + (1 - (v - lo) / (hi - lo)) * PH; }
    function X(i) { return xAt(i, n); }
    var lastY = Y(last);

    var out = [];
    out.push('<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + s.name + '">');

    var ticks = niceTicks(lo, hi, 4);
    for (var ti = 0; ti < ticks.length; ti++) {
      var ty = Y(ticks[ti]);
      out.push('<line x1="' + PL + '" y1="' + ty.toFixed(1) + '" x2="' + (PL + PW) + '" y2="' + ty.toFixed(1) +
        '" stroke="var(--line,#2a2f3a)" stroke-width="1" opacity=".5"/>');
      if (Math.abs(ty - lastY) > 9)
        out.push('<text x="' + (PL + PW + 5) + '" y="' + (ty + 3.2).toFixed(1) + '" fill="' + DIM +
          '" font-size="10" style="font-family:' + MONO + '">' + tickTxt(ticks[ti]) + '</text>');
    }
    // 기준선(점선)
    if (baseV != null && baseV > lo && baseV < hi) {
      var by = Y(baseV);
      out.push('<line x1="' + PL + '" y1="' + by.toFixed(1) + '" x2="' + (PL + PW) + '" y2="' + by.toFixed(1) +
        '" stroke="#f6c85f" stroke-width="1" stroke-dasharray="3 3" opacity=".8"/>');
      out.push('<text x="' + (PL + PW - 4) + '" y="' + (by - 3.5).toFixed(1) + '" text-anchor="end" fill="#f6c85f" ' +
        'font-size="9.5" opacity=".95">' + baseLab + ' ' + fmtVal(baseV, s.unit) + '</text>');
    }
    // 라인 + 옅은 면
    var dpath = '', area = '';
    for (var i = 0; i < n; i++) {
      var x = X(i).toFixed(2), y = Y(vals[i]).toFixed(2);
      dpath += (i ? 'L' : 'M') + x + ' ' + y;
      area += (i ? 'L' : 'M') + x + ' ' + y;
    }
    area += 'L' + X(n - 1).toFixed(2) + ' ' + (PT + PH) + 'L' + X(0).toFixed(2) + ' ' + (PT + PH) + 'Z';
    var gid = 'shg_' + sid;
    out.push('<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0" stop-color="' + color + '" stop-opacity=".18"/>' +
      '<stop offset="1" stop-color="' + color + '" stop-opacity="0"/></linearGradient></defs>');
    out.push('<path d="' + area + '" fill="url(#' + gid + ')"/>');
    out.push('<path d="' + dpath + '" fill="none" stroke="' + color +
      '" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round"/>');

    var xn = n >= 5 ? 5 : Math.max(2, n);
    for (var xi = 0; xi < xn; xi++) {
      var idx = Math.round(xi * (n - 1) / (xn - 1));
      var anc = xi === 0 ? 'start' : (xi === xn - 1 ? 'end' : 'middle');
      out.push('<text x="' + X(idx).toFixed(1) + '" y="' + (H - 5) + '" text-anchor="' + anc + '" fill="' + DIM +
        '" font-size="10" style="font-family:' + MONO + '">' + dates[idx].slice(0, 7) + '</text>');
    }
    out.push('<circle cx="' + X(n - 1).toFixed(2) + '" cy="' + lastY.toFixed(2) + '" r="3" fill="' + color + '"/>');
    out.push('<g class="sh-guide"><line class="sh-gl" x1="0" y1="' + PT + '" x2="0" y2="' + (PT + PH) +
      '" stroke="' + DIM + '" stroke-width="1" stroke-dasharray="2 2" opacity=".7"/>' +
      '<circle class="sh-gd" cx="0" cy="0" r="2.8" fill="' + color +
      '" stroke="var(--panel,#12161d)" stroke-width="1.2"/></g>');
    out.push('</svg>');

    var plot = doc.createElement('div'); plot.className = 'sh-plot';
    plot.innerHTML = out.join('');
    var tip = doc.createElement('div'); tip.className = 'sh-tip'; plot.appendChild(tip);
    card.appendChild(plot);

    if (s.note) {
      var nt = doc.createElement('div'); nt.className = 'sh-note'; nt.textContent = '⚠ ' + s.note;
      card.appendChild(nt);
    }

    var svg = plot.querySelector('svg');
    var gl = plot.querySelector('.sh-gl'), gd = plot.querySelector('.sh-gd');
    function move(ev) {
      var r = svg.getBoundingClientRect(); if (!r.width) return;
      var px = (ev.clientX - r.left) / r.width * W;
      var i = Math.round((px - PL) / PW * (n - 1));
      if (i < 0) i = 0; else if (i > n - 1) i = n - 1;
      var gx = X(i), gy = Y(vals[i]);
      gl.setAttribute('x1', gx); gl.setAttribute('x2', gx);
      gd.setAttribute('cx', gx); gd.setAttribute('cy', gy);
      tip.textContent = dates[i] + ' · ' + fmtVal(raw[i], s.unit);
      var lp = gx / W * r.width;
      tip.style.left = Math.max(34, Math.min(r.width - 34, lp)) + 'px';
      plot.className = 'sh-plot on';
    }
    function leave() { plot.className = 'sh-plot'; }
    svg.addEventListener('mousemove', move);
    svg.addEventListener('mouseleave', leave);
    plot.addEventListener('mouseleave', leave);
    return card;
  }

  /* ---------------- 해석(자동 서술) ---------------- */
  function latestOf(data, cat, sid) {
    var c = data.cats[cat]; if (!c) return null;
    var s = c.series[sid]; if (!s) return null;
    var seq = s.d || s.m || {}; var keys = Object.keys(seq).sort();
    if (!keys.length) return null;
    var last = seq[keys[keys.length - 1]];
    return { s: s, last: +last, base: s.base, date: keys[keys.length - 1] };
  }
  function pctVs(x) {
    if (!x || x.base == null || !x.base) return null;
    return (x.last - x.base) / Math.abs(x.base) * 100;
  }
  function buildStory(doc, data) {
    var suez = latestOf(data, 'chokepoint', 'cp_suez');
    var cogh = latestOf(data, 'chokepoint', 'cp_cogh');
    var bab = latestOf(data, 'chokepoint', 'cp_bab');
    var ppi = latestOf(data, 'freight', 'ppi_deepsea');
    if (!suez && !cogh) return null;

    var sd = pctVs(suez), cd = pctVs(cogh), bd = pctVs(bab);
    function span(x, cls) { return '<span class="' + cls + '">' + x + '</span>'; }
    function sgn(p) { return (p >= 0 ? '+' : '−') + Math.abs(p).toFixed(0) + '%'; }

    var parts = [];
    parts.push('<b>초크포인트 → 톤마일 → 운임 메커니즘.</b> ');
    if (suez && sd != null)
      parts.push('수에즈 통항은 최근 <b>' + Math.round(suez.last) + '척/일</b>로 2023 정상선 대비 ' +
        span(sgn(sd), sd < 0 ? 'd' : 'u') + '. ');
    if (bab && bd != null)
      parts.push('홍해(바브엘만데브)는 ' + span(sgn(bd), bd < 0 ? 'd' : 'u') + '. ');
    var reroute = cogh && cd != null && cd > 5;
    var suezDrop = suez && sd != null && sd < -5;
    if (cogh && cd != null)
      parts.push('반대로 희망봉 우회는 <b>' + Math.round(cogh.last) + '척/일</b>, 정상 대비 ' +
        span(sgn(cd), cd >= 0 ? 'u' : 'd') + '. ');
    if (suezDrop && reroute) {
      parts.push('수에즈 급감 + 희망봉 급증 = <b>홍해 회피·희망봉 우회</b> 국면. ' +
        '항해거리(톤마일)가 길어져 실효 선복이 조여지고 <b>탱커 운임에 상방 압력</b>. ');
    } else if (reroute) {
      parts.push('우회 항로 물동량이 정상 위 → 톤마일 확대가 운임을 지지. ');
    } else {
      parts.push('현재는 정상 항로 회복 국면에 가까워 톤마일 프리미엄은 완화 쪽. ');
    }
    if (ppi) {
      var pd = ppi.base != null && ppi.base ? (ppi.last - ppi.base) / Math.abs(ppi.base) * 100 : null;
      parts.push('실제 해상 원양운임 PPI는 <b>' + ppi.last.toFixed(1) + '</b>' +
        (pd != null ? ' (2023 대비 ' + span(sgn(pd), pd >= 0 ? 'u' : 'd') + ')' : '') +
        '로 이 메커니즘을 후행 확인.');
    }
    var box = doc.createElement('div'); box.className = 'sh-story';
    box.innerHTML = '<h3>🧭 해석 — 초크포인트가 운임을 움직이는 경로</h3><p>' + parts.join('') + '</p>';
    return box;
  }

  /* ---------------- 섹션 ---------------- */
  function buildSection(doc, data, catKey, period) {
    var cat = data.cats[catKey]; if (!cat) return null;
    var sids = Object.keys(cat.series || {});
    var sec = doc.createElement('div'); sec.className = 'sh-sec';
    var sh = doc.createElement('div'); sh.className = 'sh-sech';
    var h3 = doc.createElement('h3');
    h3.textContent = (CAT_ICON[catKey] || '') + ' ' + (cat.label || catKey);
    sh.appendChild(h3);
    var cnt = doc.createElement('span'); cnt.className = 'cnt';
    cnt.textContent = sids.length + '개 지표';
    sh.appendChild(cnt);
    sec.appendChild(sh);

    if (!sids.length) {
      var e = doc.createElement('div'); e.className = 'sh-empty';
      e.textContent = cat.note || '데이터 없음.';
      sec.appendChild(e); return sec;
    }
    var grid = doc.createElement('div'); grid.className = 'sh-grid';
    for (var i = 0; i < sids.length; i++) {
      var color = PAL[i % PAL.length];
      grid.appendChild(buildCard(doc, cat.series[sids[i]], catKey + '_' + sids[i], color, period));
    }
    sec.appendChild(grid);
    return sec;
  }

  /* ---------------- entry ---------------- */
  function renderShipping(el, data) {
    if (!el || !el.ownerDocument) return;
    var doc = el.ownerDocument;
    ensureCss(doc);
    while (el.firstChild) el.removeChild(el.firstChild);
    data = data || {};
    data.cats = data.cats || {};

    var wrap = doc.createElement('div'); wrap.className = 'sh-wrap';

    // head + chips
    var head = doc.createElement('div'); head.className = 'sh-head';
    var titleWrap = doc.createElement('div');
    var title = doc.createElement('div'); title.className = 'sh-title';
    title.textContent = '🚢 해운·탱커 모니터';
    var sub = doc.createElement('div'); sub.className = 'sh-sub';
    var fetched = (data._meta && data._meta.fetched) || '';
    sub.textContent = '원본: IMF PortWatch(초크포인트 일별) · FRED(해상운송 PPI·유가) · ' + fetched;
    titleWrap.appendChild(title); titleWrap.appendChild(sub);
    head.appendChild(titleWrap);

    var chips = doc.createElement('div'); chips.className = 'sh-chips';
    head.appendChild(chips);
    wrap.appendChild(head);

    var cardsRow = doc.createElement('div'); cardsRow.className = 'sh-cards';
    wrap.appendChild(cardsRow);

    var story = buildStory(doc, data);
    if (story) wrap.appendChild(story);

    var secWrap = doc.createElement('div');
    secWrap.style.display = 'flex';
    secWrap.style.flexDirection = 'column';
    secWrap.style.gap = '18px';
    wrap.appendChild(secWrap);

    var foot = doc.createElement('div'); foot.className = 'sh-foot';
    var blocked = (data._meta && data._meta.blocked) || {};
    var bl = Object.keys(blocked);
    foot.innerHTML = '기준선 = 초크포인트·선복·교역 2023 일평균 / 운임 기간중앙값. ' +
      (bl.length ? 'BLOCKED(유료·키필요, 미수집): ' + bl.join(', ') + '. ' : '') +
      '표시 전용 · 투자판단 근거 아님 · 원 출처 공식발표 우선.';

    var btns = [];
    function select(k) {
      for (var i = 0; i < btns.length; i++)
        btns[i].className = btns[i].getAttribute('data-k') === k ? 'sh-chip on' : 'sh-chip';
      // KPI
      while (cardsRow.firstChild) cardsRow.removeChild(cardsRow.firstChild);
      var anyKpi = false;
      for (var j = 0; j < SUMMARY.length; j++) {
        var tile = kpiTile(doc, data, SUMMARY[j], k);
        if (tile) { cardsRow.appendChild(tile); anyKpi = true; }
      }
      if (!anyKpi) cardsRow.style.display = 'none';
      // sections
      while (secWrap.firstChild) secWrap.removeChild(secWrap.firstChild);
      for (var c = 0; c < CATS.length; c++) {
        var sec = buildSection(doc, data, CATS[c], k);
        if (sec) secWrap.appendChild(sec);
      }
      secWrap.appendChild(foot);
    }
    for (var p = 0; p < PERIODS.length; p++) {
      (function (key) {
        var b = doc.createElement('button');
        b.type = 'button'; b.className = 'sh-chip';
        b.setAttribute('data-k', key); b.textContent = key;
        b.addEventListener('click', function () { select(key); });
        chips.appendChild(b); btns.push(b);
      })(PERIODS[p].k);
    }

    el.appendChild(wrap);
    select(DEFAULT_PERIOD);
    return el;
  }

  if (typeof window !== 'undefined') window.renderShipping = renderShipping;
  else if (typeof globalThis !== 'undefined') globalThis.renderShipping = renderShipping;
  if (typeof module !== 'undefined' && module.exports) module.exports = renderShipping;
})();
