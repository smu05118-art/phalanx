/*
 * ai_charts.js — LLM·클라우드 허브 렌더러
 *
 *   window.renderAICloud(el, data, derived)
 *     el      : 마운트할 DOM 엘리먼트(또는 CSS 셀렉터 문자열)
 *     data    : ai_cloud.json 파싱 객체
 *     derived : ai_cloud_derived.json 파싱 객체(선택). 생략 시 data.derived / data._derived 탐색
 *
 * 설계 메모
 *  · 의존성 0 — 인라인 SVG로 직접 그린다. Chart.js가 없어도 항상 렌더된다.
 *  · 이 허브의 핵심은 "회사마다 공시 수준이 다르다"는 사실을 시각적으로 드러내는 것.
 *      absolute(금액 공시)  → 실선
 *      growth_only(성장률만) → 점선
 *      embedded/qualitative → 배지 처리, 시계열은 역산 추정으로만
 *      derived(역산 추정)   → 주황 점선 + "추정" 배지 + 상/하한 밴드
 *  · 빌더·app.js는 건드리지 않는다. 전역 함수 하나만 노출.
 */
(function () {
  'use strict';

  var C = {
    bg: '#0b0f14',
    panel: '#111820',
    panel2: '#0e141b',
    grid: '#1e2833',
    axis: '#2b3947',
    text: '#c8d3de',
    muted: '#7b8a99',
    dim: '#55636f',
    derived: '#ff8c2b',
    good: '#35d0ba',
    bad: '#e0607e'
  };

  var SERIES_COLORS = [
    '#4ea1ff', '#35d0ba', '#f2c14e', '#e0607e',
    '#a78bfa', '#7ddf64', '#ff9f45', '#5cc8ff',
    '#c0a3ff', '#ffd166'
  ];

  var DISCLOSURE_LABEL = {
    absolute: '공시(금액)',
    growth_only: '성장률만',
    qualitative: '정성 코멘트만',
    embedded: '타 세그 포함',
    none: '해당 없음'
  };

  var DISCLOSURE_STYLE = {
    absolute: 'solid',
    growth_only: 'dash',
    qualitative: 'dot',
    embedded: 'dot',
    none: 'dot'
  };

  var CONF_LABEL = { high: '확신', med: '재확인 필요', low: '미검증' };

  /* ------------------------------------------------------------------ DOM */

  function el(tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (txt !== undefined && txt !== null) { n.textContent = String(txt); }
    return n;
  }

  function svgEl(tag, attrs) {
    var n = document.createElementNS('http://www.w3.org/2000/svg', tag);
    if (attrs) {
      for (var k in attrs) {
        if (Object.prototype.hasOwnProperty.call(attrs, k)) {
          n.setAttribute(k, String(attrs[k]));
        }
      }
    }
    return n;
  }

  function injectStyle() {
    if (document.getElementById('ai-cloud-style')) { return; }
    var s = el('style');
    s.id = 'ai-cloud-style';
    s.textContent = [
      '.aic{background:', C.bg, ';color:', C.text, ';font:13px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;padding:18px}',
      '.aic *{box-sizing:border-box}',
      '.aic h2{font-size:17px;margin:26px 0 4px;font-weight:650;letter-spacing:-.2px}',
      '.aic h3{font-size:13px;margin:16px 0 6px;font-weight:600;color:', C.muted, '}',
      '.aic .sub{color:', C.muted, ';font-size:11.5px;margin:0 0 12px}',
      '.aic .card{background:', C.panel, ';border:1px solid ', C.grid, ';border-radius:10px;padding:14px 16px;margin:10px 0}',
      '.aic .row{display:flex;flex-wrap:wrap;gap:10px}',
      '.aic .row>.card{flex:1 1 340px;min-width:0}',
      '.aic table{border-collapse:collapse;width:100%;font-size:12px}',
      '.aic th,.aic td{padding:5px 8px;text-align:right;border-bottom:1px solid ', C.grid, ';white-space:nowrap}',
      '.aic th{color:', C.muted, ';font-weight:600;text-align:right;font-size:11px;letter-spacing:.3px}',
      '.aic th:first-child,.aic td:first-child{text-align:left}',
      '.aic td.l,.aic th.l{text-align:left}',
      '.aic .badge{display:inline-block;padding:1px 6px;border-radius:999px;font-size:10px;line-height:16px;border:1px solid;margin-left:4px;vertical-align:1px}',
      '.aic .b-abs{color:#4ea1ff;border-color:#24455f;background:#0e1c26}',
      '.aic .b-grw{color:#f2c14e;border-color:#5a4a1c;background:#211c0e}',
      '.aic .b-emb{color:#a78bfa;border-color:#3d2f63;background:#181233}',
      '.aic .b-qua{color:#7b8a99;border-color:#31404d;background:#111820}',
      '.aic .b-non{color:#55636f;border-color:#232e39;background:#0e141b}',
      '.aic .b-der{color:', C.derived, ';border-color:#6b3c10;background:#241405}',
      '.aic .b-unl{color:#e0607e;border-color:#5c2634;background:#221016}',
      '.aic .b-low{color:#e0607e;border-color:#5c2634;background:#221016}',
      '.aic .b-med{color:#f2c14e;border-color:#5a4a1c;background:#211c0e}',
      '.aic .b-high{color:#35d0ba;border-color:#1c5049;background:#0c211f}',
      '.aic .legend{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin:8px 0 2px;font-size:11.5px;color:', C.muted, '}',
      '.aic .legend .k{display:inline-flex;align-items:center;gap:6px}',
      '.aic .warn{border-left:3px solid ', C.derived, ';background:#1a1208;color:#ffcf9e;padding:9px 12px;border-radius:0 6px 6px 0;font-size:11.5px;margin:8px 0}',
      '.aic .muted{color:', C.muted, '}',
      '.aic .num{font-variant-numeric:tabular-nums}',
      '.aic svg{display:block;width:100%;height:auto;overflow:visible}',
      '.aic .empty{color:', C.dim, ';font-size:11.5px;padding:16px 0;text-align:center}'
    ].join('');
    document.head.appendChild(s);
  }

  /* ---------------------------------------------------------------- utils */

  function qsort(a, b) {
    return qrank(a) - qrank(b);
  }

  function qrank(k) {
    var parts = String(k).split('-');
    var y = parseInt(parts[0], 10);
    if (isNaN(y)) { return 1e9; }
    var order = { Q1: 1, '1H': 2, Q2: 2, Q3: 3, Q4: 4, FY: 5 };
    var o = order[parts[1]] || 0;
    return y * 10 + o;
  }

  function isFiniteNum(v) {
    return typeof v === 'number' && isFinite(v);
  }

  function fmt(v, digits) {
    if (!isFiniteNum(v)) { return '–'; }
    var d = digits === undefined ? 0 : digits;
    var s = Math.abs(v) >= 1000 ? Math.round(v).toLocaleString('en-US')
                                : v.toFixed(d);
    return s;
  }

  function companies(data, section) {
    var box = data && data[section];
    return (box && box.companies) || {};
  }

  function llmGroup(data, side) {
    return (data && data.llm && data.llm[side]) || {};
  }

  function metricSeries(co, name) {
    var m = co.metrics || {};
    var raw = m[name];
    if (!raw || typeof raw !== 'object') { return []; }
    // 기간 키는 '2025-Q3' / '2024-FY' / '2025-1H' / '2024'(연간) 를 모두 허용한다
    var keys = Object.keys(raw).filter(function (k) {
      return isFiniteNum(raw[k]) && /^\d{4}(-|$)/.test(k);
    }).sort(qsort);
    return keys.map(function (k) { return { x: k, y: raw[k] }; });
  }

  function confOf(co, name) {
    return (co.conf || {})[name] || null;
  }

  function badge(text, cls) {
    var b = el('span', 'badge ' + cls, text);
    return b;
  }

  function disclosureBadge(d) {
    var map = {
      absolute: 'b-abs', growth_only: 'b-grw', embedded: 'b-emb',
      qualitative: 'b-qua', none: 'b-non'
    };
    return badge(DISCLOSURE_LABEL[d] || d, map[d] || 'b-non');
  }

  function confBadge(c) {
    if (!c) { return null; }
    return badge(CONF_LABEL[c] || c, 'b-' + c);
  }

  /* --------------------------------------------------------------- charts */

  /* 다중 시리즈 라인 차트.
   * series: [{label, color, style:'solid'|'dash'|'derived', points:[{x,y}], band:[{x,lo,hi}]}]
   */
  function lineChart(series, opts) {
    opts = opts || {};
    var W = 860, H = opts.height || 300;
    var padL = 54, padR = 14, padT = 14, padB = 46;

    var xs = [];
    series.forEach(function (s) {
      (s.points || []).forEach(function (p) {
        if (xs.indexOf(p.x) < 0) { xs.push(p.x); }
      });
      (s.band || []).forEach(function (p) {
        if (xs.indexOf(p.x) < 0) { xs.push(p.x); }
      });
    });
    xs.sort(qsort);

    if (!xs.length) {
      var e = el('div', 'empty', '표시할 시계열 없음');
      return e;
    }

    var lo = Infinity, hi = -Infinity;
    series.forEach(function (s) {
      (s.points || []).forEach(function (p) {
        if (p.y < lo) { lo = p.y; }
        if (p.y > hi) { hi = p.y; }
      });
      (s.band || []).forEach(function (p) {
        if (p.lo < lo) { lo = p.lo; }
        if (p.hi > hi) { hi = p.hi; }
      });
    });
    if (lo === Infinity) { lo = 0; hi = 1; }
    if (lo === hi) { hi = lo + 1; }
    var span = hi - lo;
    lo -= span * 0.12;
    hi += span * 0.12;
    if (opts.zeroBase && lo > 0) { lo = 0; }

    function X(k) {
      var i = xs.indexOf(k);
      if (xs.length === 1) { return padL + (W - padL - padR) / 2; }
      return padL + (W - padL - padR) * (i / (xs.length - 1));
    }
    function Y(v) {
      return padT + (H - padT - padB) * (1 - (v - lo) / (hi - lo));
    }

    var svg = svgEl('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img' });

    // y 그리드 + 눈금
    var ticks = 5, i, gy, val;
    for (i = 0; i <= ticks; i++) {
      val = lo + (hi - lo) * (i / ticks);
      gy = Y(val);
      svg.appendChild(svgEl('line', {
        x1: padL, y1: gy, x2: W - padR, y2: gy,
        stroke: (Math.abs(val) < 1e-9 || (val <= 0 && lo < 0 && i === 0)) ? C.axis : C.grid,
        'stroke-width': 1
      }));
      var t = svgEl('text', {
        x: padL - 8, y: gy + 3.5, fill: C.muted, 'font-size': 10, 'text-anchor': 'end'
      });
      t.textContent = fmt(val, span < 10 ? 1 : 0) + (opts.suffix || '');
      svg.appendChild(t);
    }

    // 0선 강조
    if (lo < 0 && hi > 0) {
      svg.appendChild(svgEl('line', {
        x1: padL, y1: Y(0), x2: W - padR, y2: Y(0),
        stroke: C.axis, 'stroke-width': 1.5
      }));
    }

    // x 라벨(과밀 방지로 간격 조절)
    var step = Math.ceil(xs.length / 12);
    xs.forEach(function (k, idx) {
      if (idx % step !== 0 && idx !== xs.length - 1) { return; }
      var tx = svgEl('text', {
        x: X(k), y: H - padB + 16, fill: C.muted, 'font-size': 10,
        'text-anchor': 'middle', transform: 'rotate(-38 ' + X(k) + ' ' + (H - padB + 16) + ')'
      });
      tx.textContent = k;
      svg.appendChild(tx);
    });

    // 밴드(역산 추정 상/하한) 먼저 깔고
    series.forEach(function (s) {
      if (!s.band || !s.band.length) { return; }
      var b = s.band.slice().sort(function (p, q) { return qsort(p.x, q.x); });
      var up = b.map(function (p) { return X(p.x) + ',' + Y(p.hi); });
      var dn = b.slice().reverse().map(function (p) { return X(p.x) + ',' + Y(p.lo); });
      svg.appendChild(svgEl('polygon', {
        points: up.concat(dn).join(' '),
        fill: s.color || C.derived, 'fill-opacity': 0.13, stroke: 'none'
      }));
    });

    // 라인
    series.forEach(function (s) {
      var pts = (s.points || []).slice().sort(function (p, q) { return qsort(p.x, q.x); });
      if (!pts.length) { return; }
      var color = s.color || C.derived;
      var dash = '';
      if (s.style === 'dash') { dash = '7 4'; }
      else if (s.style === 'derived') { dash = '5 4'; }
      else if (s.style === 'dot') { dash = '2 4'; }

      var d = pts.map(function (p, idx) {
        return (idx === 0 ? 'M' : 'L') + X(p.x) + ' ' + Y(p.y);
      }).join(' ');
      var path = svgEl('path', {
        d: d, fill: 'none', stroke: color,
        'stroke-width': s.style === 'derived' ? 2.4 : 2,
        'stroke-linejoin': 'round', 'stroke-linecap': 'round'
      });
      if (dash) { path.setAttribute('stroke-dasharray', dash); }
      svg.appendChild(path);

      pts.forEach(function (p) {
        var c = svgEl('circle', {
          cx: X(p.x), cy: Y(p.y), r: 2.6, fill: color,
          stroke: C.panel, 'stroke-width': 1
        });
        var ttl = svgEl('title');
        ttl.textContent = s.label + ' · ' + p.x + ' · ' +
          fmt(p.y, 1) + (opts.suffix || '');
        c.appendChild(ttl);
        svg.appendChild(c);
      });
    });

    return svg;
  }

  /* 스택 막대. groups: [{x, parts:[{label,color,v}]}] */
  function stackedBars(groups, opts) {
    opts = opts || {};
    var W = 860, H = opts.height || 280;
    var padL = 60, padR = 14, padT = 14, padB = 46;

    groups = groups.filter(function (g) { return g.parts.length; });
    if (!groups.length) { return el('div', 'empty', '표시할 capex 데이터 없음'); }

    var hi = 0;
    groups.forEach(function (g) {
      var sum = 0;
      g.parts.forEach(function (p) { sum += p.v; });
      if (sum > hi) { hi = sum; }
    });
    if (hi <= 0) { hi = 1; }
    hi *= 1.1;

    var svg = svgEl('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img' });
    var plotW = W - padL - padR, plotH = H - padT - padB;
    var bw = Math.min(46, (plotW / groups.length) * 0.62);

    var i, gy, val;
    for (i = 0; i <= 4; i++) {
      val = hi * (i / 4);
      gy = padT + plotH * (1 - i / 4);
      svg.appendChild(svgEl('line', {
        x1: padL, y1: gy, x2: W - padR, y2: gy, stroke: C.grid, 'stroke-width': 1
      }));
      var t = svgEl('text', {
        x: padL - 8, y: gy + 3.5, fill: C.muted, 'font-size': 10, 'text-anchor': 'end'
      });
      t.textContent = fmt(val, 0);
      svg.appendChild(t);
    }

    groups.forEach(function (g, idx) {
      var cx = padL + plotW * ((idx + 0.5) / groups.length);
      var acc = 0;
      g.parts.forEach(function (p) {
        var y0 = padT + plotH * (1 - (acc + p.v) / hi);
        var y1 = padT + plotH * (1 - acc / hi);
        var r = svgEl('rect', {
          x: cx - bw / 2, y: y0, width: bw, height: Math.max(0.5, y1 - y0),
          fill: p.color, 'fill-opacity': 0.9
        });
        var ttl = svgEl('title');
        ttl.textContent = p.label + ' · ' + g.x + ' · ' + fmt(p.v, 0) +
          (opts.suffix || '');
        r.appendChild(ttl);
        svg.appendChild(r);
        acc += p.v;
      });
      var tx = svgEl('text', {
        x: cx, y: H - padB + 16, fill: C.muted, 'font-size': 10,
        'text-anchor': 'middle',
        transform: 'rotate(-38 ' + cx + ' ' + (H - padB + 16) + ')'
      });
      tx.textContent = g.x;
      svg.appendChild(tx);
    });

    return svg;
  }

  /* 가로 막대(백로그·용량 랭킹). items: [{label, v, color, note}] */
  function hbars(items, opts) {
    opts = opts || {};
    items = items.filter(function (d) { return isFiniteNum(d.v); });
    if (!items.length) { return el('div', 'empty', opts.emptyText || '데이터 없음'); }
    items.sort(function (a, b) { return b.v - a.v; });

    var rowH = 26, padL = 108, padR = 62, W = 860;
    var H = items.length * rowH + 14;
    var hi = items[0].v * 1.05 || 1;
    var svg = svgEl('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img' });

    items.forEach(function (d, i) {
      var y = i * rowH + 7;
      var w = Math.max(1, (W - padL - padR) * (d.v / hi));
      var lab = svgEl('text', {
        x: padL - 10, y: y + 12, fill: C.text, 'font-size': 11, 'text-anchor': 'end'
      });
      lab.textContent = d.label;
      svg.appendChild(lab);

      var r = svgEl('rect', {
        x: padL, y: y, width: w, height: rowH - 12,
        fill: d.color || SERIES_COLORS[i % SERIES_COLORS.length],
        'fill-opacity': 0.85, rx: 2
      });
      if (d.note) {
        var ttl = svgEl('title');
        ttl.textContent = d.note;
        r.appendChild(ttl);
      }
      svg.appendChild(r);

      var v = svgEl('text', {
        x: padL + w + 8, y: y + 12, fill: C.muted, 'font-size': 11
      });
      v.textContent = fmt(d.v, d.v < 10 ? 1 : 0) + (opts.suffix || '');
      svg.appendChild(v);
    });
    return svg;
  }

  /* --------------------------------------------------------------- legend */

  function legendSwatch(color, style) {
    var s = svgEl('svg', { width: 26, height: 10, viewBox: '0 0 26 10' });
    var p = svgEl('line', {
      x1: 0, y1: 5, x2: 26, y2: 5, stroke: color, 'stroke-width': 2.2,
      'stroke-linecap': 'round'
    });
    if (style === 'dash') { p.setAttribute('stroke-dasharray', '7 4'); }
    if (style === 'derived') { p.setAttribute('stroke-dasharray', '5 4'); }
    if (style === 'dot') { p.setAttribute('stroke-dasharray', '2 4'); }
    s.appendChild(p);
    return s;
  }

  function disclosureLegend() {
    var box = el('div', 'legend');
    [
      ['#4ea1ff', 'solid', '공시(absolute) — 금액 그대로'],
      ['#f2c14e', 'dash', '성장률만(growth_only) — 금액 비공개'],
      ['#a78bfa', 'dot', '타 세그 포함(embedded) / 정성 코멘트만'],
      [C.derived, 'derived', '역산 추정(derived) — 밴드 표시, 추정 배지']
    ].forEach(function (row) {
      var k = el('div', 'k');
      k.appendChild(legendSwatch(row[0], row[1]));
      k.appendChild(el('span', null, row[2]));
      box.appendChild(k);
    });
    return box;
  }

  /* ------------------------------------------------------------- sections */

  function sectionTitle(parent, title, sub) {
    parent.appendChild(el('h2', null, title));
    if (sub) { parent.appendChild(el('p', 'sub', sub)); }
  }

  /* 공시 특성 분류표 — 이 허브의 출발점 */
  function disclosureTable(root, data) {
    var card = el('div', 'card');
    card.appendChild(el('h3', null, '사별 공시 특성 분류 (disclosure)'));

    var tbl = el('table');
    var thead = el('thead');
    var hr = el('tr');
    ['회사', '구분', '공시 등급', '지표 수', '최신 기간', '검증 대기', '비고']
      .forEach(function (h, i) {
        var th = el('th', i === 0 || i === 6 ? 'l' : null, h);
        hr.appendChild(th);
      });
    thead.appendChild(hr);
    tbl.appendChild(thead);

    var tb = el('tbody');
    var rows = [];
    [['west', '서방'], ['china', '중화권']].forEach(function (sec) {
      var cs = companies(data, sec[0]);
      Object.keys(cs).forEach(function (tk) {
        rows.push({ tk: tk, co: cs[tk], region: sec[1] });
      });
    });

    rows.sort(function (a, b) {
      if (a.region !== b.region) { return a.region < b.region ? -1 : 1; }
      return countPoints(b.co) - countPoints(a.co);
    });

    rows.forEach(function (r) {
      var co = r.co;
      var tr = el('tr');

      var c0 = el('td', 'l');
      c0.appendChild(el('span', null, co.name || r.tk));
      if (co.unlisted) { c0.appendChild(badge('비상장', 'b-unl')); }
      tr.appendChild(c0);

      tr.appendChild(el('td', null, r.region));

      var c2 = el('td');
      c2.appendChild(disclosureBadge(co.disclosure));
      tr.appendChild(c2);

      tr.appendChild(el('td', 'num', String(countPoints(co))));
      tr.appendChild(el('td', 'num', latestPeriod(co) || '–'));
      tr.appendChild(el('td', 'num', String((co.pending || []).length)));

      var c6 = el('td', 'l muted');
      c6.textContent = (co.disclosure_note || (co.notes || [])[0] || '').slice(0, 78);
      tr.appendChild(c6);

      tb.appendChild(tr);
    });
    tbl.appendChild(tb);
    card.appendChild(tbl);
    root.appendChild(card);
  }

  function countPoints(co) {
    var n = 0, m = co.metrics || {}, k;
    for (k in m) {
      if (!Object.prototype.hasOwnProperty.call(m, k)) { continue; }
      var v = m[k];
      if (v && typeof v === 'object' && !(v instanceof Array)) {
        for (var q in v) {
          if (Object.prototype.hasOwnProperty.call(v, q) && v[q] !== null) { n++; }
        }
      }
    }
    ['models', 'pricing', 'contracts', 'guidance', 'funding'].forEach(function (key) {
      if (co[key] instanceof Array) { n += co[key].length; }
    });
    return n;
  }

  function latestPeriod(co) {
    var ks = [], m = co.metrics || {}, k;
    for (k in m) {
      if (!Object.prototype.hasOwnProperty.call(m, k)) { continue; }
      var v = m[k];
      if (v && typeof v === 'object' && !(v instanceof Array)) {
        for (var q in v) {
          if (Object.prototype.hasOwnProperty.call(v, q) && v[q] !== null &&
              /^\d{4}(-|$)/.test(q)) {
            ks.push(q);
          }
        }
      }
    }
    if (!ks.length) { return null; }
    ks.sort(qsort);
    return ks[ks.length - 1];
  }

  /* ① 클라우드 성장률 비교(서방/중화권 공용) */
  function growthSection(root, data, section, derivedIndex, opts) {
    opts = opts || {};
    var cs = companies(data, section);
    var series = [], ci = 0;

    Object.keys(cs).forEach(function (tk) {
      var co = cs[tk];
      if (opts.only && opts.only.indexOf(co.category) < 0) { return; }
      var pts = metricSeries(co, 'cloud_growth_pct');
      if (!pts.length) { return; }
      series.push({
        label: (co.name || tk),
        color: SERIES_COLORS[ci++ % SERIES_COLORS.length],
        style: DISCLOSURE_STYLE[co.disclosure] || 'solid',
        points: pts,
        disclosure: co.disclosure,
        conf: confOf(co, 'cloud_growth_pct')
      });
    });

    // 역산 추정 시리즈(주황 점선 + 밴드) 주입
    Object.keys(derivedIndex).forEach(function (key) {
      var parts = key.split('|');
      var ent = parts[0], metric = parts[1];
      if (metric !== 'cloud_growth_pct') { return; }
      if (!cs[ent]) { return; }
      var items = derivedIndex[key];
      series.push({
        label: (cs[ent].name || ent) + ' (추정)',
        color: C.derived,
        style: 'derived',
        derived: true,
        conf: items[0] && items[0].confidence,
        points: items.map(function (d) { return { x: d.period, y: d.value_mid }; }),
        band: items.map(function (d) {
          return { x: d.period, lo: d.value_lo, hi: d.value_hi };
        })
      });
    });

    var card = el('div', 'card');
    card.appendChild(lineChart(series, { height: 310, suffix: '%' }));

    var lg = el('div', 'legend');
    series.forEach(function (s) {
      var k = el('div', 'k');
      k.appendChild(legendSwatch(s.color, s.style));
      k.appendChild(el('span', null, s.label));
      if (s.derived) { k.appendChild(badge('추정', 'b-der')); }
      else if (s.disclosure) { k.appendChild(disclosureBadge(s.disclosure)); }
      if (s.conf) { k.appendChild(confBadge(s.conf)); }
      lg.appendChild(k);
    });
    card.appendChild(lg);
    root.appendChild(card);
  }

  /* ② capex 추이(스택) */
  function capexSection(root, data) {
    var quarters = {}, annuals = {}, colorOf = {}, ci = 0;

    [['west', companies(data, 'west')], ['china', companies(data, 'china')]]
      .forEach(function (pair) {
        var cs = pair[1];
        Object.keys(cs).forEach(function (tk) {
          var co = cs[tk];
          var q = metricSeries(co, 'capex');
          var a = metricSeries(co, 'capex_annual');
          if (!q.length && !a.length) { return; }
          if (!colorOf[tk]) {
            colorOf[tk] = SERIES_COLORS[ci++ % SERIES_COLORS.length];
          }
          q.forEach(function (p) {
            (quarters[p.x] = quarters[p.x] || []).push({
              label: co.name || tk, color: colorOf[tk], v: p.y
            });
          });
          a.forEach(function (p) {
            (annuals[p.x] = annuals[p.x] || []).push({
              label: co.name || tk, color: colorOf[tk], v: p.y
            });
          });
        });
      });

    function toGroups(obj) {
      return Object.keys(obj).sort(qsort).map(function (k) {
        return { x: k, parts: obj[k] };
      });
    }

    var wrap = el('div', 'row');

    var c1 = el('div', 'card');
    c1.appendChild(el('h3', null, '분기 capex 스택 (현지통화 백만, 통화 혼재 주의)'));
    c1.appendChild(stackedBars(toGroups(quarters), { height: 260 }));
    wrap.appendChild(c1);

    var c2 = el('div', 'card');
    c2.appendChild(el('h3', null, '연간 capex 스택'));
    c2.appendChild(stackedBars(toGroups(annuals), { height: 260 }));
    wrap.appendChild(c2);

    root.appendChild(wrap);

    var note = el('div', 'warn');
    note.textContent = 'capex 정의는 회사마다 다르다(금융리스 포함 여부 등). ' +
      '통화도 USD/CNY가 섞여 있으므로 스택 높이의 절대 비교는 금지하고 추세만 볼 것. ' +
      '정의는 각 사 metric_defs 참조.';
    root.appendChild(note);

    // 가이던스 표
    var rows = [];
    [['west', companies(data, 'west')], ['china', companies(data, 'china')]]
      .forEach(function (pair) {
        var cs = pair[1];
        Object.keys(cs).forEach(function (tk) {
          var g = (cs[tk].metrics || {}).capex_guidance ||
                  (cs[tk].metrics || {}).capex_plan;
          if (!g || typeof g !== 'object') { return; }
          Object.keys(g).forEach(function (period) {
            rows.push({ name: cs[tk].name || tk, period: period, text: g[period] });
          });
        });
      });
    if (rows.length) {
      var card = el('div', 'card');
      card.appendChild(el('h3', null, 'capex 가이던스 / 투자계획 (미제시도 신호다)'));
      var tbl = el('table');
      var hr = el('tr');
      ['회사', '기간', '내용'].forEach(function (h, i) {
        hr.appendChild(el('th', i === 2 ? 'l' : null, h));
      });
      var th = el('thead'); th.appendChild(hr); tbl.appendChild(th);
      var tb = el('tbody');
      rows.forEach(function (r) {
        var tr = el('tr');
        tr.appendChild(el('td', 'l', r.name));
        tr.appendChild(el('td', null, r.period));
        tr.appendChild(el('td', 'l', typeof r.text === 'number'
          ? fmt(r.text, 0) : String(r.text)));
        tb.appendChild(tr);
      });
      tbl.appendChild(tb);
      card.appendChild(tbl);
      root.appendChild(card);
    }
  }

  /* ③ 네오클라우드 백로그·MW */
  function neocloudSection(root, data) {
    var cs = companies(data, 'west');
    var backlog = [], mw = [], gw = [], rows = [], ci = 0;

    Object.keys(cs).forEach(function (tk) {
      var co = cs[tk];
      if (co.category !== 'neocloud') { return; }
      var color = SERIES_COLORS[ci++ % SERIES_COLORS.length];

      function last(name) {
        var s = metricSeries(co, name);
        return s.length ? s[s.length - 1] : null;
      }
      var b = last('rpo_backlog_busd');
      var a = last('power_mw_active');
      var g = last('power_gw_contracted');
      var gp = last('gpu_count');
      var ar = last('arr_musd');
      var rv = last('revenue');

      if (b) { backlog.push({ label: co.name || tk, v: b.y, color: color, note: b.x }); }
      if (a) { mw.push({ label: co.name || tk, v: a.y, color: color, note: a.x }); }
      if (g) { gw.push({ label: co.name || tk, v: g.y, color: color, note: g.x }); }

      rows.push({
        name: co.name || tk, tk: tk, unlisted: !!co.unlisted,
        disclosure: co.disclosure,
        rev: rv, backlog: b, mw: a, gw: g, gpu: gp, arr: ar,
        contracts: (co.contracts || []).length,
        conf: confOf(co, 'rpo_backlog_busd') || confOf(co, 'revenue')
      });
    });

    if (!rows.length) {
      root.appendChild(el('div', 'empty', '네오클라우드 데이터 없음'));
      return;
    }

    var wrap = el('div', 'row');
    var c1 = el('div', 'card');
    c1.appendChild(el('h3', null, '백로그 / RPO (최신 분기, $B)'));
    c1.appendChild(hbars(backlog, { suffix: 'B', emptyText: '백로그 데이터 없음' }));
    wrap.appendChild(c1);

    var c2 = el('div', 'card');
    c2.appendChild(el('h3', null, '계약 확보 전력 (GW)'));
    c2.appendChild(hbars(gw, { suffix: 'GW', emptyText: '전력 데이터 없음' }));
    wrap.appendChild(c2);
    root.appendChild(wrap);

    if (mw.length) {
      var c3 = el('div', 'card');
      c3.appendChild(el('h3', null, '가동(energized) 전력 (MW)'));
      c3.appendChild(hbars(mw, { suffix: 'MW' }));
      root.appendChild(c3);
    }

    var card = el('div', 'card');
    card.appendChild(el('h3', null, '네오클라우드 KPI 요약 — 매출보다 백로그·전력·GPU가 선행지표'));
    var tbl = el('table');
    var hr = el('tr');
    ['회사', '공시', '최신 매출', '백로그($B)', '가동MW', '계약GW', 'GPU', 'ARR($M)', '계약건', '신뢰도']
      .forEach(function (h, i) {
        hr.appendChild(el('th', i === 0 ? 'l' : null, h));
      });
    var th = el('thead'); th.appendChild(hr); tbl.appendChild(th);
    var tb = el('tbody');
    rows.sort(function (a, b) {
      return (b.backlog ? b.backlog.y : -1) - (a.backlog ? a.backlog.y : -1);
    });
    rows.forEach(function (r) {
      var tr = el('tr');
      var c0 = el('td', 'l');
      c0.appendChild(el('span', null, r.name));
      if (r.unlisted) { c0.appendChild(badge('비상장', 'b-unl')); }
      tr.appendChild(c0);
      var cd = el('td');
      cd.appendChild(disclosureBadge(r.disclosure));
      tr.appendChild(cd);
      tr.appendChild(el('td', 'num', r.rev ? fmt(r.rev.y, 1) + ' (' + r.rev.x + ')' : '–'));
      tr.appendChild(el('td', 'num', r.backlog ? fmt(r.backlog.y, 1) : '–'));
      tr.appendChild(el('td', 'num', r.mw ? fmt(r.mw.y, 0) : '–'));
      tr.appendChild(el('td', 'num', r.gw ? fmt(r.gw.y, 1) : '–'));
      tr.appendChild(el('td', 'num', r.gpu ? fmt(r.gpu.y, 0) : '–'));
      tr.appendChild(el('td', 'num', r.arr ? fmt(r.arr.y, 0) : '–'));
      tr.appendChild(el('td', 'num', String(r.contracts)));
      var cc = el('td');
      var cb = confBadge(r.conf);
      if (cb) { cc.appendChild(cb); }
      tr.appendChild(cc);
      tb.appendChild(tr);
    });
    tbl.appendChild(tb);
    card.appendChild(tbl);
    root.appendChild(card);

    // 계약 목록
    var clist = [];
    Object.keys(cs).forEach(function (tk) {
      var co = cs[tk];
      if (co.category !== 'neocloud') { return; }
      (co.contracts || []).forEach(function (k) {
        clist.push({ who: co.name || tk, c: k });
      });
    });
    if (clist.length) {
      var cc2 = el('div', 'card');
      cc2.appendChild(el('h3', null, '주요 AI 계약 (백로그의 실체)'));
      var t2 = el('table');
      var h2 = el('tr');
      ['사업자', '상대방', '규모($B)', '발표', '비고'].forEach(function (h, i) {
        h2.appendChild(el('th', (i === 0 || i === 1 || i === 4) ? 'l' : null, h));
      });
      var th2 = el('thead'); th2.appendChild(h2); t2.appendChild(th2);
      var tb2 = el('tbody');
      clist.sort(function (a, b) {
        return (b.c.value_busd || 0) - (a.c.value_busd || 0);
      });
      clist.slice(0, 24).forEach(function (r) {
        var tr = el('tr');
        tr.appendChild(el('td', 'l', r.who));
        tr.appendChild(el('td', 'l', r.c.counterparty || '–'));
        tr.appendChild(el('td', 'num', isFiniteNum(r.c.value_busd)
          ? fmt(r.c.value_busd, 1) : '–'));
        tr.appendChild(el('td', null, r.c.announced || '–'));
        var tdn = el('td', 'l muted', (r.c.note || '').slice(0, 92));
        if (r.c.conf) { tdn.appendChild(confBadge(r.c.conf)); }
        tr.appendChild(tdn);
        tb2.appendChild(tr);
      });
      t2.appendChild(tb2);
      cc2.appendChild(t2);
      root.appendChild(cc2);
    }
  }

  /* ⑤ LLM 섹션 */
  function llmSection(root, data) {
    [['west', '서방 LLM/모델'], ['china', '중화권 LLM/모델']].forEach(function (pair) {
      var group = llmGroup(data, pair[0]);
      var keys = Object.keys(group);
      if (!keys.length) { return; }

      var card = el('div', 'card');
      card.appendChild(el('h3', null, pair[1] + ' — 비상장이 다수라 재무 대신 모델·가격·파트너십으로 추적'));

      var tbl = el('table');
      var hr = el('tr');
      ['개발사', '상장', '공시', '모델 수', '최신 모델', '가격 항목', '입력 $/Mtok', '출력 $/Mtok']
        .forEach(function (h, i) {
          hr.appendChild(el('th', (i === 0 || i === 4) ? 'l' : null, h));
        });
      var th = el('thead'); th.appendChild(hr); tbl.appendChild(th);
      var tb = el('tbody');

      keys.forEach(function (k) {
        var d = group[k];
        var models = d.models || [];
        var prices = d.pricing || [];
        var latest = models.length ? models[0] : null;
        var p0 = null, i;
        for (i = 0; i < prices.length; i++) {
          if (isFiniteNum(prices[i].in_per_mtok)) { p0 = prices[i]; break; }
        }
        var pc = null;
        for (i = 0; i < prices.length; i++) {
          if (isFiniteNum(prices[i].in_per_mtok_cny)) { pc = prices[i]; break; }
        }

        var tr = el('tr');
        var c0 = el('td', 'l');
        c0.appendChild(el('span', null, d.name || k));
        if (d.parent) { c0.appendChild(badge(d.parent, 'b-emb')); }
        tr.appendChild(c0);

        var c1 = el('td');
        c1.appendChild(d.unlisted ? badge('비상장', 'b-unl') : badge('상장', 'b-high'));
        tr.appendChild(c1);

        var c2 = el('td');
        c2.appendChild(disclosureBadge(d.disclosure));
        tr.appendChild(c2);

        tr.appendChild(el('td', 'num', String(models.length)));

        var c4 = el('td', 'l');
        if (latest) {
          c4.appendChild(el('span', null, latest.model +
            (latest.released ? ' (' + latest.released + ')' : '')));
          if (latest.conf) { c4.appendChild(confBadge(latest.conf)); }
        } else {
          c4.textContent = '–';
        }
        tr.appendChild(c4);

        tr.appendChild(el('td', 'num', String(prices.length)));
        if (p0) {
          tr.appendChild(el('td', 'num', '$' + p0.in_per_mtok));
          tr.appendChild(el('td', 'num', '$' + p0.out_per_mtok));
        } else if (pc) {
          tr.appendChild(el('td', 'num', '¥' + pc.in_per_mtok_cny));
          tr.appendChild(el('td', 'num', '¥' + pc.out_per_mtok_cny));
        } else {
          tr.appendChild(el('td', 'num', '–'));
          tr.appendChild(el('td', 'num', '–'));
        }
        tb.appendChild(tr);
      });
      tbl.appendChild(tb);
      card.appendChild(tbl);
      root.appendChild(card);

      // 모델 출시 타임라인
      var events = [];
      keys.forEach(function (k) {
        var d = group[k];
        (d.models || []).forEach(function (m) {
          if (!m.released) { return; }
          events.push({ dev: d.name || k, model: m.model, at: m.released, conf: m.conf });
        });
      });
      if (events.length) {
        events.sort(function (a, b) { return a.at < b.at ? 1 : -1; });
        var tcard = el('div', 'card');
        tcard.appendChild(el('h3', null, pair[1] + ' 모델 출시 타임라인 (최근 20건)'));
        var t2 = el('table');
        var h2 = el('tr');
        ['출시일', '개발사', '모델', '신뢰도'].forEach(function (h, i) {
          h2.appendChild(el('th', i === 3 ? null : 'l', h));
        });
        var th2 = el('thead'); th2.appendChild(h2); t2.appendChild(th2);
        var tb2 = el('tbody');
        events.slice(0, 20).forEach(function (e) {
          var tr = el('tr');
          tr.appendChild(el('td', 'l num', e.at));
          tr.appendChild(el('td', 'l', e.dev));
          tr.appendChild(el('td', 'l', e.model));
          var c = el('td');
          var b = confBadge(e.conf);
          if (b) { c.appendChild(b); }
          tr.appendChild(c);
          tb2.appendChild(tr);
        });
        t2.appendChild(tb2);
        tcard.appendChild(t2);
        root.appendChild(tcard);
      }

      // 토큰 단가 비교(USD 기준만)
      var priced = [];
      keys.forEach(function (k) {
        var d = group[k];
        (d.pricing || []).forEach(function (p) {
          if (!isFiniteNum(p.out_per_mtok)) { return; }
          priced.push({
            label: (p.model || d.name), v: p.out_per_mtok,
            note: (d.name || k) + ' · 출력 $' + p.out_per_mtok +
                  ' / 입력 $' + (p.in_per_mtok === undefined ? '?' : p.in_per_mtok) +
                  ' (' + (p.asof || '?') + ')'
          });
        });
      });
      if (priced.length) {
        var pc2 = el('div', 'card');
        pc2.appendChild(el('h3', null, '출력 토큰 단가 비교 ($/Mtok, USD 표기 모델만)'));
        pc2.appendChild(hbars(priced.slice(0, 18), { suffix: '' }));
        root.appendChild(pc2);
      }
    });
  }

  /* 역산 추정 상세 */
  function derivedSection(root, derived) {
    var items = (derived && derived.items) || [];
    if (!items.length) { return; }

    var card = el('div', 'card');
    card.appendChild(el('h3', null, '역산 추정 상세 — 방법·밴드·신뢰도 (공시값과 절대 섞지 않음)'));

    var tbl = el('table');
    var hr = el('tr');
    ['대상', '지표', '기간', '하한', '중앙', '상한', '단위', '신뢰도', '방법']
      .forEach(function (h, i) {
        hr.appendChild(el('th', (i === 0 || i === 8) ? 'l' : null, h));
      });
    var th = el('thead'); th.appendChild(hr); tbl.appendChild(th);
    var tb = el('tbody');

    items.forEach(function (d) {
      var tr = el('tr');
      var c0 = el('td', 'l');
      c0.appendChild(el('span', null, d.entity_name || d.entity));
      c0.appendChild(badge('추정', 'b-der'));
      tr.appendChild(c0);
      tr.appendChild(el('td', 'l', d.metric));
      tr.appendChild(el('td', null, d.period));
      tr.appendChild(el('td', 'num', fmt(d.value_lo, 1)));
      tr.appendChild(el('td', 'num', fmt(d.value_mid, 1)));
      tr.appendChild(el('td', 'num', fmt(d.value_hi, 1)));
      tr.appendChild(el('td', null, d.unit || ''));
      var cc = el('td');
      var b = confBadge(d.confidence);
      if (b) { cc.appendChild(b); }
      tr.appendChild(cc);
      var cm = el('td', 'l muted', (d.method || '').slice(0, 60));
      tr.appendChild(cm);
      tb.appendChild(tr);
    });
    tbl.appendChild(tb);
    card.appendChild(tbl);

    var meta = (derived && derived._meta) || {};
    if (meta.caveat) {
      var w = el('div', 'warn', meta.caveat);
      card.appendChild(w);
    }
    root.appendChild(card);
  }

  /* ------------------------------------------------------------ index/entry */

  function indexDerived(derived) {
    var idx = {};
    ((derived && derived.items) || []).forEach(function (d) {
      var key = d.entity + '|' + d.metric;
      (idx[key] = idx[key] || []).push(d);
    });
    Object.keys(idx).forEach(function (k) {
      idx[k].sort(function (a, b) { return qsort(a.period, b.period); });
    });
    return idx;
  }

  function renderAICloud(target, data, derived) {
    var host = typeof target === 'string' ? document.querySelector(target) : target;
    if (!host) { return null; }
    if (!data) {
      host.appendChild(el('div', 'empty', 'ai_cloud.json 데이터가 없습니다'));
      return host;
    }
    injectStyle();

    var d = derived || data.derived || data._derived || null;
    var didx = indexDerived(d);

    var root = el('div', 'aic');
    host.innerHTML = '';
    host.appendChild(root);

    var meta = data._meta || {};

    root.appendChild(el('h2', null, 'AI — LLM·클라우드 허브'));
    root.appendChild(el('p', 'sub',
      '서방/중화권 분리. 회사마다 공시 수준이 다르다는 점을 데이터 구조와 차트 표기에 반영했다. ' +
      (meta.generated ? '생성 ' + meta.generated + ' · ' : '') +
      'west ' + Object.keys(companies(data, 'west')).length +
      ' · china ' + Object.keys(companies(data, 'china')).length +
      ' · llm ' + (Object.keys(llmGroup(data, 'west')).length +
                   Object.keys(llmGroup(data, 'china')).length) +
      ' · derived ' + ((d && d.items && d.items.length) || 0)));

    if (meta.caveat) {
      root.appendChild(el('div', 'warn', meta.caveat));
    }
    root.appendChild(disclosureLegend());

    disclosureTable(root, data);

    sectionTitle(root, '① 서방 클라우드 성장률 비교',
      '실선=금액 공시, 점선=성장률만 공시. 같은 "성장률"이라도 검증 가능성이 다르다. ' +
      '네오클라우드는 성장률 자릿수가 달라(세 자리) 축을 왜곡하므로 ③에서 따로 본다.');
    growthSection(root, data, 'west', didx, { only: ['hyperscaler'] });

    sectionTitle(root, '② CAPEX 추이',
      'AI 인프라 투자 강도. 가이던스 미제시 자체가 신호이므로 표에 함께 싣는다.');
    capexSection(root, data);

    sectionTitle(root, '③ 네오클라우드 — 백로그·전력·GPU',
      '매출은 후행지표다. 계약 백로그와 확보 전력(MW/GW)이 진짜 선행지표.');
    neocloudSection(root, data);

    sectionTitle(root, '④ 중화권 클라우드',
      '알리바바만 absolute, 텐센트는 FBS 세그에 embedded(별도 공시 없음) → 주황 점선 추정 밴드로 표기.');
    growthSection(root, data, 'china', didx, null);

    sectionTitle(root, '⑤ LLM — 모델·가격·순위',
      '대부분 비상장이라 재무가 없다. 모델 출시·토큰 단가·파트너십으로 대체 추적.');
    llmSection(root, data);

    sectionTitle(root, '⑥ 역산 추정 (derived)',
      '정량 미공시 + 정성 코멘트만 있는 경우에 한해 역산. 단일값 금지, 반드시 밴드.');
    derivedSection(root, d);

    return root;
  }

  window.renderAICloud = renderAICloud;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { renderAICloud: renderAICloud };
  }
}());
