/* neocloud_charts.js — 네오클라우드 용량·단가 모델 + 클라우드 ASP 리비전룸 렌더러
 * 전역: window.renderNeocloud(el, data)
 *   data = { model: <neocloud_model.json>, asp: <cloud_asp_revision.json> }
 *   (또는 두 파일을 합친 객체 { _meta, companies, anchors, price_ladder, assumptions, providers, ranking })
 * 의존성 0 — Chart.js가 있으면 쓰고, 없으면 인라인 SVG로 폴백.
 * 팔랑크스 다크테마 CSS 변수(--fg/--dim/--panel/--line) 사용.
 */
(function () {
  'use strict';

  var CSS_ID = 'nc-css';

  /* 테마 토큰: 렌더 시점에 CSS 변수를 읽는다(다크=폴백). 토글 후 render() 재호출로 반영. */
  function cssVar(name, fb) {
    try {
      var v = getComputedStyle(document.documentElement).getPropertyValue(name);
      return (v && v.trim()) || fb;
    } catch (e) { return fb; }
  }
  var C = {
    get up() { return cssVar('--nc-red', '#ff5b5b'); },
    get down() { return cssVar('--nc-blue', '#4c8dff'); },
    get flat() { return cssVar('--nc-flat', '#8b98a9'); },
    get cons() { return cssVar('--nc-blue', '#4c8dff'); },   // 컨센 암시 ASP
    get recalc() { return cssVar('--nc-gold', '#ffb020'); }, // 재계산 ASP
    get gapPos() { return cssVar('--nc-good', '#3fd07a'); }, // 리비전룸 +
    get gapNeg() { return cssVar('--nc-red', '#ff5b5b'); },  // 리비전룸 -
    get tierLow() { return cssVar('--nc-blue', '#4c8dff'); },
    get tierMid() { return cssVar('--nc-gold', '#ffb020'); },
    get tierHigh() { return cssVar('--nc-red', '#ff5b5b'); },
    guide: 'rgba(255,176,32,.13)'
  };

  var CSS = [
    '.nc{color:var(--fg,#e6ebf2);font-size:13px}',
    '.nc *{box-sizing:border-box}',
    '.nc-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin:0 0 12px}',
    '.nc-head h2{font-size:16px;margin:0;font-weight:650}',
    '.nc-sub{color:var(--dim,#8b98a9);font-size:11px;font-family:var(--mono,ui-monospace,SFMono-Regular,Menlo,monospace)}',
    '.nc-panel{background:var(--panel,#12161c);border:1px solid var(--line,#232a34);border-radius:10px;padding:12px;margin:0 0 14px}',
    '.nc-panel h3{font-size:13.5px;margin:0 0 4px;font-weight:650;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}',
    '.nc-note{font-weight:400;color:var(--dim,#8b98a9);font-size:11px}',
    '.nc-desc{color:var(--dim,#8b98a9);font-size:11.5px;line-height:1.6;margin:0 0 10px}',
    '.nc-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 10px}',
    '.nc-tabs{display:flex;gap:4px;flex-wrap:wrap}',
    '.nc-tab{border:1px solid var(--line,#232a34);background:transparent;color:var(--dim,#8b98a9);border-radius:999px;padding:4px 11px;font-size:12px;cursor:pointer;line-height:1.5;font-family:inherit}',
    '.nc-tab:hover{color:var(--fg,#e6ebf2)}',
    '.nc-tab.on{background:var(--fg,#e6ebf2);color:var(--panel,#12161c);border-color:var(--fg,#e6ebf2);font-weight:600}',
    '.nc-lbl{color:var(--dim,#8b98a9);font-size:11px;margin-right:2px}',
    '.nc-tbl-wrap{overflow:auto;max-width:100%}',
    '.nc-tbl{width:100%;border-collapse:collapse;font-size:11.5px;white-space:nowrap}',
    '.nc-tbl th{position:sticky;top:0;background:var(--panel,#12161c);text-align:right;color:var(--dim,#8b98a9);font-weight:600;padding:5px 8px;border-bottom:1px solid var(--line,#232a34);z-index:1}',
    '.nc-tbl th.l,.nc-tbl td.l{text-align:left}',
    '.nc-tbl th.g{color:var(--nc-gold,#ffb020)}',
    '.nc-tbl td{padding:4px 8px;border-bottom:1px solid var(--line,#232a34);text-align:right;font-family:var(--mono,ui-monospace,Menlo,monospace)}',
    '.nc-tbl td.l{font-family:inherit}',
    '.nc-tbl td.g{background:rgba(255,176,32,.10)}',
    '.nc-tbl tr:hover td{background:var(--nc-wash,rgba(255,255,255,.03))}',
    '.nc-tbl tr.sect td{background:var(--nc-wash2,rgba(255,255,255,.045));font-weight:650;color:var(--fg,#e6ebf2);font-family:inherit}',
    '.nc-tbl td.dim{color:var(--dim,#8b98a9)}',
    '.nc-badge{display:inline-block;font-size:10px;font-weight:700;border-radius:5px;padding:1px 6px;margin-left:5px;font-family:var(--mono,ui-monospace,Menlo,monospace);vertical-align:middle}',
    '.nc-b-ok{background:rgba(63,208,122,.16);color:var(--nc-good,#3fd07a)}',
    '.nc-b-no{background:rgba(255,91,91,.16);color:var(--nc-red,#ff5b5b)}',
    '.nc-b-g{background:rgba(255,176,32,.16);color:var(--nc-gold,#ffb020)}',
    '.nc-b-n{background:rgba(139,152,169,.16);color:var(--dim,#8b98a9)}',
    '.nc-anch{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:10px}',
    '.nc-acard{border:1px solid var(--line,#232a34);border-radius:8px;padding:9px 11px;background:var(--nc-wash,rgba(255,255,255,.02))}',
    '.nc-acard .t{font-size:12px;font-weight:600;line-height:1.4;margin-bottom:4px}',
    '.nc-acard .v{font-family:var(--mono,ui-monospace,Menlo,monospace);font-size:12px;color:var(--nc-gold,#ffb020);margin-bottom:4px}',
    '.nc-acard .q{color:var(--dim,#8b98a9);font-size:11px;line-height:1.55;border-left:2px solid var(--line,#232a34);padding-left:7px;margin:5px 0;white-space:pre-wrap}',
    '.nc-acard .s{font-size:10px;color:var(--dim,#8b98a9);font-family:var(--mono,ui-monospace,Menlo,monospace);overflow:hidden;text-overflow:ellipsis}',
    '.nc-acard a{color:var(--nc-blue,#4c8dff);text-decoration:none}',
    '.nc-acard a:hover{text-decoration:underline}',
    '.nc-cv{position:relative;width:100%}',
    '.nc-lad{display:flex;flex-direction:column;gap:7px;margin:6px 0 2px}',
    '.nc-lrow{display:flex;align-items:center;gap:9px}',
    '.nc-lname{width:210px;min-width:150px;font-size:11.5px;line-height:1.35}',
    '.nc-lname .sm{display:block;color:var(--dim,#8b98a9);font-size:10px;font-family:var(--mono,ui-monospace,Menlo,monospace)}',
    '.nc-ltrack{position:relative;flex:1;height:20px;background:var(--nc-wash,rgba(255,255,255,.03));border-radius:4px}',
    '.nc-lfill{position:absolute;top:0;bottom:0;border-radius:4px;opacity:.85}',
    '.nc-lval{position:absolute;top:50%;transform:translateY(-50%);font-size:10.5px;font-family:var(--mono,ui-monospace,Menlo,monospace);white-space:nowrap;color:var(--fg,#e6ebf2)}',
    '.nc-lax{display:flex;justify-content:space-between;color:var(--dim,#8b98a9);font-size:10px;font-family:var(--mono,ui-monospace,Menlo,monospace);margin-left:219px}',
    '.nc-hm{border-collapse:collapse;font-size:11.5px}',
    '.nc-hm th{color:var(--dim,#8b98a9);font-weight:600;padding:4px 9px;font-size:11px;text-align:center}',
    '.nc-hm td{padding:6px 10px;text-align:center;border:1px solid var(--line,#232a34);font-family:var(--mono,ui-monospace,Menlo,monospace);min-width:82px}',
    '.nc-hm td .b{display:block;font-size:12px;font-weight:700}',
    '.nc-hm td .s{display:block;font-size:10px;opacity:.75}',
    '.nc-hm td.rh{background:var(--panel,#12161c);color:var(--dim,#8b98a9);border:none;text-align:right;font-size:11px;min-width:0}',
    '.nc-legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--dim,#8b98a9);margin-top:8px}',
    '.nc-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;vertical-align:-1px;margin-right:5px}',
    '.nc-notes{margin:8px 0 0;padding-left:16px;color:var(--dim,#8b98a9);font-size:11px;line-height:1.65}',
    '.nc-notes li{margin:2px 0}',
    '.nc-flex{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}',
    '.nc-empty{color:var(--dim,#8b98a9);padding:18px;text-align:center}',
    '.nc-src{font-size:10px;color:var(--dim,#8b98a9);font-family:var(--mono,ui-monospace,Menlo,monospace);margin-top:6px;word-break:break-all}',
    '.nc-src a{color:var(--nc-blue,#4c8dff);text-decoration:none}',
    '.nc-kpi{display:flex;gap:16px;flex-wrap:wrap;margin:2px 0 10px}',
    '.nc-kpi div{min-width:104px}',
    '.nc-kpi .k{color:var(--dim,#8b98a9);font-size:10.5px}',
    '.nc-kpi .v{font-size:16px;font-weight:700;font-family:var(--mono,ui-monospace,Menlo,monospace);line-height:1.3}',
    /* 라이트 테마 토큰(다크는 var() 폴백) — 텍스트 용도 상태색은 어두운 변형으로 AA 확보 */
    ':root[data-theme="light"]{--nc-gold:#8a6300;--nc-blue:#2266d0;--nc-good:#17714a;--nc-red:#c03830;',
    '--nc-flat:#565b80;--nc-grid:rgba(27,29,51,.12);--nc-svgval:#1b1d33;',
    '--nc-wash:rgba(27,29,51,.05);--nc-wash2:rgba(27,29,51,.07)}'
  ].join('\n');

  function injectCSS(doc) {
    if (!doc || doc.getElementById(CSS_ID)) return;
    var st = doc.createElement('style');
    st.id = CSS_ID;
    st.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(st);
  }

  /* ------------------------------------------------------------------ util */
  function el(tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }
  function isNum(v) { return typeof v === 'number' && isFinite(v); }
  function fmt(v, d) {
    if (!isNum(v)) return '–';
    var dd = d == null ? (Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2) : d;
    return v.toLocaleString('en-US', { minimumFractionDigits: dd, maximumFractionDigits: dd });
  }
  function fmtPct(v, d) {
    if (!isNum(v)) return '–';
    return (v > 0 ? '+' : '') + fmt(v, d == null ? 1 : d) + '%';
  }
  function pctColor(v) { return !isNum(v) ? C.flat : v > 0 ? C.up : v < 0 ? C.down : C.flat; }
  function sortQ(a, b) { return a < b ? -1 : a > b ? 1 : 0; }
  function qKeys(o) { return o ? Object.keys(o).filter(function (k) { return k.charAt(0) !== '_'; }).sort(sortQ) : []; }
  function prevQ(k) {
    var m = /^(\d{4})-Q([1-4])$/.exec(k || '');
    if (!m) return null;
    var y = +m[1], q = +m[2] - 1;
    if (q < 1) { q = 4; y -= 1; }
    return y + '-Q' + q;
  }
  function yoyQ(k) {
    var m = /^(\d{4})-Q([1-4])$/.exec(k || '');
    return m ? (+m[1] - 1) + '-Q' + m[2] : null;
  }
  function chg(cur, base) {
    if (!isNum(cur) || !isNum(base) || base === 0) return null;
    return (cur / base - 1) * 100;
  }
  function link(url, label) {
    if (!url) return el('span', null, '출처 없음');
    var a = el('a', null, label || String(url).replace(/^https?:\/\//, '').slice(0, 62));
    a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer';
    return a;
  }
  function tabs(items, cur, onPick) {
    var w = el('div', 'nc-tabs');
    items.forEach(function (it) {
      var id = typeof it === 'string' ? it : it.id;
      var lb = typeof it === 'string' ? it : it.label;
      var b = el('button', 'nc-tab' + (id === cur ? ' on' : ''), lb);
      b.type = 'button';
      b.onclick = function () {
        Array.prototype.forEach.call(w.children, function (c) { c.className = 'nc-tab'; });
        b.className = 'nc-tab on';
        onPick(id);
      };
      w.appendChild(b);
    });
    return w;
  }
  function panel(title, note) {
    var p = el('div', 'nc-panel');
    var h = el('h3', null, title);
    if (note) h.appendChild(el('span', 'nc-note', note));
    p.appendChild(h);
    return p;
  }
  function hasChart() { return typeof window !== 'undefined' && typeof window.Chart === 'function'; }

  /* --------------------------------------------------------- SVG mini chart */
  function svg(tag, attrs) {
    var n = document.createElementNS('http://www.w3.org/2000/svg', tag);
    if (attrs) Object.keys(attrs).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    return n;
  }
  /* 그룹 막대(SVG 폴백) — series=[{label,color,vals:[]}], labels=[] */
  function groupedBarSVG(labels, series, height, fmtV) {
    height = height || 260;
    var W = Math.max(360, labels.length * Math.max(90, series.length * 42) + 60), H = height;
    var padL = 44, padR = 10, padT = 16, padB = 40;
    var root = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, width: '100%', height: H, preserveAspectRatio: 'xMinYMid meet' });
    var max = 0;
    series.forEach(function (s) { s.vals.forEach(function (v) { if (isNum(v) && v > max) max = v; }); });
    if (max <= 0) max = 1;
    max *= 1.18;
    var iw = W - padL - padR, ih = H - padT - padB;
    var y = function (v) { return padT + ih - (v / max) * ih; };
    [0, .25, .5, .75, 1].forEach(function (f) {
      var yy = padT + ih - f * ih;
      root.appendChild(svg('line', { x1: padL, x2: W - padR, y1: yy, y2: yy, stroke: cssVar('--nc-grid', 'rgba(255,255,255,.07)'), 'stroke-width': 1 }));
      var t = svg('text', { x: padL - 6, y: yy + 3.5, fill: C.flat, 'font-size': 9.5, 'text-anchor': 'end' });
      t.textContent = fmt(max * f, 1);
      root.appendChild(t);
    });
    var gw = iw / labels.length, bw = Math.min(30, (gw * 0.66) / series.length);
    labels.forEach(function (lb, i) {
      var cx = padL + gw * i + gw / 2;
      var x0 = cx - (bw * series.length) / 2;
      series.forEach(function (s, si) {
        var v = s.vals[i];
        if (!isNum(v)) return;
        var bx = x0 + si * bw, by = y(v), bh = Math.max(1, padT + ih - by);
        root.appendChild(svg('rect', { x: bx + 1, y: by, width: bw - 2, height: bh, fill: s.color, rx: 2, opacity: .9 }));
        var t = svg('text', { x: bx + bw / 2, y: by - 4, fill: cssVar('--nc-svgval', '#c9d2de'), 'font-size': 9.5, 'text-anchor': 'middle' });
        t.textContent = (fmtV || fmt)(v, 1);
        root.appendChild(t);
      });
      var xt = svg('text', { x: cx, y: H - padB + 15, fill: C.flat, 'font-size': 10.5, 'text-anchor': 'middle' });
      xt.textContent = lb;
      root.appendChild(xt);
    });
    return root;
  }

  /* ============================================================ §1 용량 모델 */
  var ROWS = [
    { k: '_s1', label: '전력 용량 (MW)', sect: true },
    { k: 'active_mw', label: 'Total Active Power (MW)', d: 0 },
    { k: 'connected_mw', label: 'Connected Power (MW)', d: 0 },
    { k: 'contracted_mw', label: 'Contracted Power (MW)', d: 0 },
    { k: 'net_new_mw', label: 'Net New Active Power (MW)', d: 0, derive: 'netnew' },
    { k: '_s2', label: 'GPU', sect: true },
    { k: 'gpus', label: '설치 GPU 수', d: 0 },
    { k: '_mix', label: 'GPU 세대 믹스', mix: true },
    { k: '_s3', label: '매출 · 백로그 (US$ M)', sect: true },
    { k: 'arr_usd_m', label: 'ARR', d: 0 },
    { k: 'revenue_usd_m', label: '분기 매출', d: 0 },
    { k: 'rpo_usd_m', label: 'RPO / 백로그', d: 0 },
    { k: 'capex_usd_m', label: 'capex', d: 0 },
    { k: '_s4', label: '단가 (US$M per MW)', sect: true },
    { k: '_blend', label: 'blended $/MW = ARR ÷ connected MW', d: 2, calc: 'blend' },
    { k: 'gpu_hour_usd', label: '$/GPU-hour (공시분)', d: 2 }
  ];

  function cellVal(row, q) {
    if (!q) return null;
    if (row.calc === 'blend') {
      var mw = isNum(q.connected_mw) ? q.connected_mw : q.active_mw;
      if (!isNum(q.arr_usd_m) || !isNum(mw) || mw === 0) return null;
      return q.arr_usd_m / mw;
    }
    return isNum(q[row.k]) ? q[row.k] : null;
  }

  function capacityTable(co) {
    var qs = qKeys(co.quarterly || {});
    var wrap = el('div', 'nc-tbl-wrap');
    if (!qs.length) { wrap.appendChild(el('div', 'nc-empty', '분기 데이터 없음')); return wrap; }
    var t = el('table', 'nc-tbl');
    var thead = el('thead'), hr = el('tr');
    hr.appendChild(el('th', 'l', '지표'));
    qs.forEach(function (k) {
      var g = (co.quarterly[k] || {}).guidance === true;
      var th = el('th', g ? 'g' : null, k + (g ? ' G' : ''));
      hr.appendChild(th);
    });
    hr.appendChild(el('th', null, 'QoQ'));
    hr.appendChild(el('th', null, 'YoY'));
    thead.appendChild(hr); t.appendChild(thead);
    var tb = el('tbody');
    ROWS.forEach(function (row) {
      var tr = el('tr');
      if (row.sect) {
        tr.className = 'sect';
        var td = el('td', 'l', row.label);
        td.colSpan = qs.length + 3;
        tr.appendChild(td); tb.appendChild(tr); return;
      }
      var any = false, vals = [];
      qs.forEach(function (k) {
        var q = co.quarterly[k] || {};
        var v;
        if (row.mix) {
          var mx = q.gpu_mix;
          v = mx && Object.keys(mx).length
            ? Object.keys(mx).map(function (g) { return g + (isNum(mx[g]) ? ':' + fmt(mx[g], 0) : ''); }).join(' / ')
            : null;
        } else if (row.derive === 'netnew') {
          v = isNum(q.net_new_mw) ? q.net_new_mw : null;
          if (v == null) {
            var pk = prevQ(k), pv = pk && co.quarterly[pk];
            var cm = isNum(q.active_mw) ? q.active_mw : q.connected_mw;
            var pm = pv && (isNum(pv.active_mw) ? pv.active_mw : pv.connected_mw);
            if (isNum(cm) && isNum(pm)) v = cm - pm;
          }
        } else v = cellVal(row, q);
        vals.push(v);
        if (v != null) any = true;
      });
      if (!any) return;
      tr.appendChild(el('td', 'l', row.label));
      qs.forEach(function (k, i) {
        var g = (co.quarterly[k] || {}).guidance === true;
        var v = vals[i];
        var td = el('td', (g ? 'g' : '') + (row.mix ? ' dim' : ''),
          row.mix ? (v || '–') : fmt(v, row.d));
        if (row.mix) { td.style.fontSize = '10px'; td.style.textAlign = 'right'; }
        tr.appendChild(td);
      });
      var actual = [];
      qs.forEach(function (k, i) { if (!(co.quarterly[k] || {}).guidance) actual.push({ k: k, v: vals[i] }); });
      var last = actual.length ? actual[actual.length - 1] : null;
      var qq = null, yy = null;
      if (last && !row.mix) {
        var pk = prevQ(last.k), yk = yoyQ(last.k);
        var pi = qs.indexOf(pk), yi = qs.indexOf(yk);
        qq = pi >= 0 ? chg(last.v, vals[pi]) : null;
        yy = yi >= 0 ? chg(last.v, vals[yi]) : null;
      }
      [qq, yy].forEach(function (v) {
        var td = el('td', null, fmtPct(v));
        td.style.color = pctColor(v);
        tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    wrap.appendChild(t);
    return wrap;
  }

  function companySection(model) {
    var cos = model.companies || {};
    var keys = Object.keys(cos);
    var p = panel('① 네오클라우드 용량·단가 모델', 'MW · GPU · ARR · blended $/MW / ' + 'G 표시 = 회사 가이던스(주황)');
    if (!keys.length) { p.appendChild(el('div', 'nc-empty', 'companies 없음')); return p; }
    var bar = el('div', 'nc-bar');
    var body = el('div');
    var kpi = el('div', 'nc-kpi');
    var srcs = el('div', 'nc-src');

    function draw(tk) {
      var co = cos[tk] || {};
      body.innerHTML = ''; kpi.innerHTML = ''; srcs.innerHTML = '';
      var qs = qKeys(co.quarterly || {});
      var lastK = null;
      for (var i = qs.length - 1; i >= 0; i--) { if (!(co.quarterly[qs[i]] || {}).guidance) { lastK = qs[i]; break; } }
      var L = lastK ? co.quarterly[lastK] : {};
      var mw = isNum(L.connected_mw) ? L.connected_mw : L.active_mw;
      [['최신 분기', lastK || '–', C.flat],
       ['Connected MW', fmt(mw, 0), '#e6ebf2'],
       ['Contracted MW', fmt(L.contracted_mw, 0), '#e6ebf2'],
       ['GPU', fmt(L.gpus, 0), '#e6ebf2'],
       ['ARR ($M)', fmt(L.arr_usd_m, 0), '#e6ebf2'],
       ['RPO ($M)', fmt(L.rpo_usd_m, 0), '#e6ebf2'],
       ['blended $M/MW', (isNum(L.arr_usd_m) && isNum(mw) && mw ? fmt(L.arr_usd_m / mw, 2) : '–'), C.recalc]
      ].forEach(function (r) {
        var d = el('div');
        d.appendChild(el('div', 'k', r[0]));
        var v = el('div', 'v', r[1]); v.style.color = r[2];
        d.appendChild(v); kpi.appendChild(d);
      });
      if (co.name) {
        var nm = el('div', 'nc-desc');
        nm.textContent = co.name + (co.unlisted ? ' (비상장 — 공개분만)' : '') + (co.disclosure ? ' · 공시유형: ' + co.disclosure : '');
        body.appendChild(nm);
      }
      body.appendChild(capacityTable(co));
      if (co.guidance && Object.keys(co.guidance).length) {
        var gd = el('div', 'nc-desc');
        gd.style.marginTop = '8px';
        gd.innerHTML = '';
        gd.appendChild(el('b', null, '가이던스: '));
        gd.appendChild(document.createTextNode(
          Object.keys(co.guidance).filter(function (k) { return k !== 'src'; }).map(function (k) {
            var v = co.guidance[k];
            return k + '=' + (v && typeof v === 'object' ? JSON.stringify(v) : v);
          }).join(' · ')));
        body.appendChild(gd);
      }
      if (co.contracts && co.contracts.length) {
        var ct = el('div', 'nc-tbl-wrap'); ct.style.marginTop = '10px';
        var tt = el('table', 'nc-tbl');
        var th = el('tr');
        ['고객', '발표금액($B)', '기간(yr)', 'MW', '$M/MW(총)', '$M/MW-yr', '발표일'].forEach(function (h, i) {
          th.appendChild(el('th', i === 0 ? 'l' : null, h));
        });
        tt.appendChild(th);
        co.contracts.forEach(function (c) {
          var tr = el('tr');
          var td0 = el('td', 'l', c.customer || '–');
          if (c.src) { td0.appendChild(document.createTextNode(' ')); td0.appendChild(link(c.src, '↗')); }
          tr.appendChild(td0);
          tr.appendChild(el('td', null, fmt(c.announced_usd_b, 2)));
          tr.appendChild(el('td', null, fmt(c.term_yrs, 1)));
          tr.appendChild(el('td', null, fmt(c.mw, 0)));
          var tot = isNum(c.implied_usd_m_per_mw_total) ? c.implied_usd_m_per_mw_total
            : (isNum(c.announced_usd_b) && isNum(c.mw) && c.mw ? c.announced_usd_b * 1000 / c.mw : null);
          var pyr = isNum(c.implied_usd_m_per_mw_yr) ? c.implied_usd_m_per_mw_yr
            : (isNum(tot) && isNum(c.term_yrs) && c.term_yrs ? tot / c.term_yrs : null);
          var tdT = el('td', null, fmt(tot, 1)); tdT.style.color = C.recalc; tr.appendChild(tdT);
          var tdY = el('td', null, fmt(pyr, 2)); tdY.style.color = C.recalc; tr.appendChild(tdY);
          tr.appendChild(el('td', 'dim', c.date || '–'));
          tt.appendChild(tr);
        });
        ct.appendChild(tt);
        body.appendChild(el('div', 'nc-note', '주요 계약 — $M/MW(총) = 발표금액÷MW, $M/MW-yr = ÷계약기간'));
        body.appendChild(ct);
      }
      if (co.notes && co.notes.length) {
        var ul = el('ul', 'nc-notes');
        co.notes.forEach(function (n) { ul.appendChild(el('li', null, n)); });
        body.appendChild(ul);
      }
      var us = {};
      qs.forEach(function (k) { var s = (co.quarterly[k] || {}).src; if (s) us[s] = 1; });
      if (co.guidance && co.guidance.src) us[co.guidance.src] = 1;
      var ulist = Object.keys(us).slice(0, 6);
      if (ulist.length) {
        srcs.appendChild(document.createTextNode('src: '));
        ulist.forEach(function (u, i) {
          if (i) srcs.appendChild(document.createTextNode(' · '));
          srcs.appendChild(link(u));
        });
      }
    }
    bar.appendChild(el('span', 'nc-lbl', '기업'));
    bar.appendChild(tabs(keys.map(function (k) {
      return { id: k, label: k + (cos[k] && cos[k].unlisted ? '*' : '') };
    }), keys[0], draw));
    p.appendChild(bar);
    p.appendChild(kpi);
    p.appendChild(body);
    p.appendChild(srcs);
    draw(keys[0]);
    return p;
  }

  /* ------------------------------------------------ §1b 전사 요약(스냅샷) */
  function crossTable(model) {
    var cos = model.companies || {};
    var keys = Object.keys(cos);
    if (!keys.length) return null;
    var p = panel('①-b 네오클라우드 최신 분기 크로스섹션', 'blended $/MW = ARR ÷ connected(또는 active) MW');
    var w = el('div', 'nc-tbl-wrap');
    var t = el('table', 'nc-tbl');
    var hr = el('tr');
    ['기업', '분기', 'Active MW', 'Connected MW', 'Contracted MW', 'GPU', 'ARR($M)', '분기매출($M)', 'RPO($M)', 'blended $M/MW', 'RPO/ARR(x)']
      .forEach(function (h, i) { hr.appendChild(el('th', i < 2 ? 'l' : null, h)); });
    t.appendChild(hr);
    keys.forEach(function (k) {
      var co = cos[k], qs = qKeys(co.quarterly || {});
      var lastK = null;
      for (var i = qs.length - 1; i >= 0; i--) { if (!(co.quarterly[qs[i]] || {}).guidance) { lastK = qs[i]; break; } }
      if (!lastK) return;
      var q = co.quarterly[lastK];
      var mw = isNum(q.connected_mw) ? q.connected_mw : q.active_mw;
      var bl = isNum(q.arr_usd_m) && isNum(mw) && mw ? q.arr_usd_m / mw : null;
      var cov = isNum(q.rpo_usd_m) && isNum(q.arr_usd_m) && q.arr_usd_m ? q.rpo_usd_m / q.arr_usd_m : null;
      var tr = el('tr');
      var td0 = el('td', 'l', k + (co.unlisted ? '*' : ''));
      tr.appendChild(td0);
      tr.appendChild(el('td', 'l dim', lastK));
      [q.active_mw, q.connected_mw, q.contracted_mw, q.gpus, q.arr_usd_m, q.revenue_usd_m, q.rpo_usd_m]
        .forEach(function (v) { tr.appendChild(el('td', null, fmt(v, 0))); });
      var tb = el('td', null, fmt(bl, 2)); tb.style.color = C.recalc; tr.appendChild(tb);
      tr.appendChild(el('td', null, fmt(cov, 1)));
      t.appendChild(tr);
    });
    w.appendChild(t);
    p.appendChild(w);
    p.appendChild(el('div', 'nc-note', '* = 비상장(공개분만)'));
    return p;
  }

  /* ============================================================ §1c 앵커검증 */
  function anchorSection(model) {
    var a = model.anchors || [];
    if (!a.length) return null;
    var ok = a.filter(function (x) { return x.verified === true; }).length;
    var p = panel('①-c 검증 앵커', 'verified ' + ok + '/' + a.length + ' — 재현 안 되면 false로 표기(추정 금지)');
    var g = el('div', 'nc-anch');
    a.forEach(function (x) {
      var c = el('div', 'nc-acard');
      var t = el('div', 't');
      t.appendChild(document.createTextNode(x.claim || x.id || ''));
      t.appendChild(el('span', 'nc-badge ' + (x.verified === true ? 'nc-b-ok' : x.verified === false ? 'nc-b-no' : 'nc-b-n'),
        x.verified === true ? 'VERIFIED' : x.verified === false ? 'NOT VERIFIED' : 'PARTIAL'));
      c.appendChild(t);
      if (x.found_value) c.appendChild(el('div', 'v', x.found_value));
      if (x.quote_en) {
        var q = el('div', 'q', '"' + x.quote_en + '"');
        c.appendChild(q);
      }
      var meta = [];
      if (x.speaker) meta.push(x.speaker);
      if (x.event) meta.push(x.event);
      var s = el('div', 's');
      if (meta.length) s.appendChild(document.createTextNode(meta.join(' · ') + ' — '));
      s.appendChild(link(x.src));
      c.appendChild(s);
      g.appendChild(c);
    });
    p.appendChild(g);
    return p;
  }

  /* ============================================================ §2 단가 사다리 */
  function ladderSection(model) {
    var L = model.price_ladder || [];
    if (!L.length) return null;
    var p = panel('② $/MW 계약단가 사다리', 'US$M per MW · 계약 기간이 짧을수록 단가 급등');
    p.appendChild(el('div', 'nc-desc',
      '두 제품군 혼재: (a) GPU클라우드 = 연환산 $M/MW-yr(공급자 GPU 보유, 회수기간 유효), ' +
      '(b) 파워콜로 = 12–15년 총액 $M/MW(테넌트 GPU 보유, 연환산 시 ~1/10). 예: MSFT $17.4B÷300MW÷5yr=11.6/yr. ' +
      'NVDA "AI DC capex ≈ $50B/GW"(=$50M/MW) 기준 회수기간 = 50 ÷ 연환산단가 (GPU클라우드 행만, opex·감가 제외).'));
    var max = 0;
    L.forEach(function (r) { var h = isNum(r.hi) ? r.hi : r.lo; if (isNum(h) && h > max) max = h; });
    var nv = model.unit_econ && isNum(model.unit_econ.nvda_capex_usd_m_per_mw) ? model.unit_econ.nvda_capex_usd_m_per_mw : 50;
    if (nv > max) max = nv;
    max = max * 1.18 || 1;
    var box = el('div', 'nc-lad');
    L.forEach(function (r) {
      var row = el('div', 'nc-lrow');
      var nm = el('div', 'nc-lname');
      nm.appendChild(document.createTextNode(r.label || ''));
      var sm = el('span', 'sm', (r.term || '') + (r.verified === false ? ' · 미검증' : ''));
      nm.appendChild(sm);
      row.appendChild(nm);
      var tr = el('div', 'nc-ltrack');
      var lo = isNum(r.lo) ? r.lo : 0, hi = isNum(r.hi) ? r.hi : lo;
      var col = hi >= 30 ? C.tierHigh : hi >= 18 ? C.tierMid : C.tierLow;
      var f = el('div', 'nc-lfill');
      f.style.left = (lo === hi ? 0 : (lo / max * 100)) + '%';
      f.style.width = Math.max(1.2, ((hi - (lo === hi ? 0 : lo)) / max * 100)) + '%';
      f.style.background = col;
      tr.appendChild(f);
      var lab = el('div', 'nc-lval');
      lab.style.left = 'calc(' + (hi / max * 100) + '% + 7px)';
      var colo = (r.family === 'power_colo_total');
      var mid = (lo === hi) ? hi : (lo + hi) / 2;
      var pay = (!colo && nv && mid) ? (nv / mid) : null;
      lab.textContent = (lo === hi ? fmt(hi, 1) : fmt(lo, 0) + '–' + fmt(hi, 0))
        + (colo ? ' $M/MW 총' : ' $M/MW-yr')
        + (isNum(pay) ? '  (capex 회수 ' + fmt(pay, 1) + '년)' : (colo ? '  (총액·연환산≈1/10)' : ''));
      lab.style.color = col;
      tr.appendChild(lab);
      row.appendChild(tr);
      box.appendChild(row);
    });
    p.appendChild(box);
    var ax = el('div', 'nc-lax');
    [0, .25, .5, .75, 1].forEach(function (f) { ax.appendChild(el('span', null, fmt(max * f, 0))); });
    p.appendChild(ax);
    var lg = el('div', 'nc-legend');
    [['<18 $M/MW 장기·하이퍼스케일러', C.tierLow], ['18–30 중기(1–3y)', C.tierMid], ['>30 단기(≤6m)', C.tierHigh]]
      .forEach(function (r) {
        var s = el('span'); var i = el('i'); i.style.background = r[1];
        s.appendChild(i); s.appendChild(document.createTextNode(r[0])); lg.appendChild(s);
      });
    p.appendChild(lg);
    var ul = el('ul', 'nc-notes');
    L.forEach(function (r) {
      var li = el('li');
      li.appendChild(document.createTextNode((r.label || '') + (r.note ? ' — ' + r.note + ' ' : ' — ')));
      if (r.src) li.appendChild(link(r.src));
      ul.appendChild(li);
    });
    p.appendChild(ul);
    return p;
  }

  /* ==================================================== §3 컨센 vs 재계산 ASP */
  function aspCompare(asp, region) {
    var provs = asp.providers || {};
    var keys = Object.keys(provs).filter(function (k) {
      var r = (provs[k].region || 'global');
      return region === 'china' ? r === 'china' : r !== 'china';
    });
    if (!keys.length) return null;
    var fys = ['FY26', 'FY27', 'FY28'];
    var cases = ['cons', 'base', 'bull'];
    var caseLbl = { cons: '보수', base: '중립', bull: '공격' };
    var st = { fy: 'FY26', cs: 'base' };
    var p = panel((region === 'china' ? '⑥-a 중화권 ' : '③ ') + '컨센 암시 ASP vs 계약단가 재계산 ASP',
      '$B per GW · 갭 = 리비전룸');
    p.appendChild(el('div', 'nc-desc',
      '컨센 암시 ASP = 컨센 매출 ÷ 추정 GW. 재계산 ASP = 고단가×비중 + 저단가×(1−비중). ' +
      '리비전룸(%) = 재계산 ÷ 컨센 − 1, 리비전룸($B) = (재계산 − 컨센) × GW.'));
    var bar = el('div', 'nc-bar');
    var chartBox = el('div', 'nc-cv');
    var tblBox = el('div');

    function pick(o, fy) { return o && isNum(o[fy]) ? o[fy] : null; }

    function draw() {
      chartBox.innerHTML = ''; tblBox.innerHTML = '';
      var labels = [], consV = [], recV = [], rows = [];
      keys.forEach(function (k) {
        var pv = provs[k];
        var ca = pv.consensus || {}, rc = pv.recalc || {};
        var cAsp = pick(ca.implied_asp, st.fy);
        var gw = pick(ca.gw, st.fy);
        var rAsp = rc.cases && rc.cases[st.cs] ? pick(rc.cases[st.cs], st.fy) : pick(rc.blended_asp, st.fy);
        var roomPct = pick((pv.revision_room_pct || {})[st.cs] || pv.revision_room_pct, st.fy);
        if (!isNum(roomPct) && isNum(cAsp) && isNum(rAsp) && cAsp) roomPct = (rAsp / cAsp - 1) * 100;
        var roomUsd = pick((pv.revision_room_usd_b || {})[st.cs] || pv.revision_room_usd_b, st.fy);
        if (!isNum(roomUsd) && isNum(cAsp) && isNum(rAsp) && isNum(gw)) roomUsd = (rAsp - cAsp) * gw;
        labels.push(k); consV.push(cAsp); recV.push(rAsp);
        rows.push({ k: k, rev: pick(ca.rev, st.fy), gw: gw, cAsp: cAsp, rAsp: rAsp,
                    pct: roomPct, usd: roomUsd, vis: pv.visibility || {}, src: ca.src });
      });
      var series = [
        { label: '컨센 암시 ASP', color: C.cons, vals: consV },
        { label: '재계산 ASP (' + caseLbl[st.cs] + ')', color: C.recalc, vals: recV }
      ];
      chartBox.appendChild(groupedBarSVG(labels, series, 250));
      var lg = el('div', 'nc-legend');
      series.forEach(function (s) {
        var sp = el('span'); var i = el('i'); i.style.background = s.color;
        sp.appendChild(i); sp.appendChild(document.createTextNode(s.label)); lg.appendChild(sp);
      });
      chartBox.appendChild(lg);

      var w = el('div', 'nc-tbl-wrap');
      var t = el('table', 'nc-tbl');
      var hr = el('tr');
      ['사업자', '컨센매출($B)', 'GW', '컨센 ASP($B/GW)', '재계산 ASP', '리비전룸(%)', '리비전룸($B)', 'RPO커버리지', '출처']
        .forEach(function (h, i) { hr.appendChild(el('th', i === 0 || i === 8 ? 'l' : null, h)); });
      t.appendChild(hr);
      rows.forEach(function (r) {
        var tr = el('tr');
        tr.appendChild(el('td', 'l', r.k));
        tr.appendChild(el('td', null, fmt(r.rev, 0)));
        tr.appendChild(el('td', null, fmt(r.gw, 1)));
        var c1 = el('td', null, fmt(r.cAsp, 2)); c1.style.color = C.cons; tr.appendChild(c1);
        var c2 = el('td', null, fmt(r.rAsp, 2)); c2.style.color = C.recalc; tr.appendChild(c2);
        var c3 = el('td', null, fmtPct(r.pct, 1));
        c3.style.color = isNum(r.pct) ? (r.pct > 0 ? C.gapPos : C.gapNeg) : C.flat;
        c3.style.fontWeight = '700';
        tr.appendChild(c3);
        var c4 = el('td', null, isNum(r.usd) ? (r.usd > 0 ? '+' : '') + fmt(r.usd, 0) : '–');
        c4.style.color = isNum(r.usd) ? (r.usd > 0 ? C.gapPos : C.gapNeg) : C.flat;
        tr.appendChild(c4);
        tr.appendChild(el('td', null, isNum(r.vis.coverage) ? fmt(r.vis.coverage, 2) + 'x' : '–'));
        var ts = el('td', 'l'); ts.style.fontSize = '10px';
        ts.appendChild(link(r.src, r.src ? '출처↗' : null));
        tr.appendChild(ts);
        t.appendChild(tr);
      });
      w.appendChild(t);
      tblBox.appendChild(w);
    }

    bar.appendChild(el('span', 'nc-lbl', '연도'));
    bar.appendChild(tabs(fys, st.fy, function (v) { st.fy = v; draw(); }));
    bar.appendChild(el('span', 'nc-lbl', '케이스'));
    bar.appendChild(tabs(cases.map(function (c) { return { id: c, label: caseLbl[c] }; }), st.cs, function (v) { st.cs = v; draw(); }));
    p.appendChild(bar);
    p.appendChild(chartBox);
    p.appendChild(tblBox);
    draw();
    return p;
  }

  /* ============================================================ §3b 믹스 근거 */
  function mixSection(asp, region) {
    var provs = asp.providers || {};
    var keys = Object.keys(provs).filter(function (k) {
      var r = (provs[k].region || 'global');
      return region === 'china' ? r === 'china' : r !== 'china';
    });
    if (!keys.length) return null;
    var p = panel((region === 'china' ? '⑥-b ' : '③-b ') + '믹스 가정 근거', '고단가/저단가 비중과 그 근거 — 가정은 전부 명시');
    var w = el('div', 'nc-tbl-wrap');
    var t = el('table', 'nc-tbl');
    var hr = el('tr');
    ['사업자', '고단가 ASP', '비중', '근거', '저단가 ASP', '비중', '근거'].forEach(function (h, i) {
      hr.appendChild(el('th', (i === 0 || i === 3 || i === 6) ? 'l' : null, h));
    });
    t.appendChild(hr);
    keys.forEach(function (k) {
      var mx = ((provs[k].recalc || {}).mix) || {};
      var hi = mx.high || {}, lo = mx.low || {};
      var tr = el('tr');
      tr.appendChild(el('td', 'l', k));
      tr.appendChild(el('td', null, fmt(hi.asp, 1)));
      tr.appendChild(el('td', null, isNum(hi.share) ? fmt(hi.share * 100, 0) + '%' : '–'));
      var b1 = el('td', 'l', hi.basis || '–'); b1.style.whiteSpace = 'normal'; b1.style.fontFamily = 'inherit';
      b1.style.maxWidth = '260px'; b1.style.fontSize = '11px'; tr.appendChild(b1);
      tr.appendChild(el('td', null, fmt(lo.asp, 1)));
      tr.appendChild(el('td', null, isNum(lo.share) ? fmt(lo.share * 100, 0) + '%' : '–'));
      var b2 = el('td', 'l', lo.basis || '–'); b2.style.whiteSpace = 'normal'; b2.style.fontFamily = 'inherit';
      b2.style.maxWidth = '260px'; b2.style.fontSize = '11px'; tr.appendChild(b2);
      t.appendChild(tr);
    });
    w.appendChild(t);
    p.appendChild(w);
    return p;
  }

  /* ============================================================ §4 민감도 히트맵 */
  function heatSection(asp) {
    var A = asp.assumptions || {};
    var shares = A.high_share_grid || [0.2, 0.3, 0.4];
    var lows = A.low_asp_grid || [8, 10, 12];
    var provs = asp.providers || {};
    var keys = Object.keys(provs);
    if (!keys.length) return null;
    var st = { p: keys[0], fy: 'FY26' };
    var p = panel('④ 민감도 히트맵', '행 = 고단가 비중 · 열 = 저단가 ASP($B/GW) / 셀 = blended ASP & 리비전룸%');
    var bar = el('div', 'nc-bar');
    var box = el('div');

    function draw() {
      box.innerHTML = '';
      var pv = provs[st.p] || {};
      var hiAsp = (((pv.recalc || {}).mix || {}).high || {}).asp;
      var cAsp = ((pv.consensus || {}).implied_asp || {})[st.fy];
      var gw = ((pv.consensus || {}).gw || {})[st.fy];
      if (!isNum(hiAsp)) { box.appendChild(el('div', 'nc-empty', '고단가 ASP 미설정')); return; }
      var t = el('table', 'nc-hm');
      var hr = el('tr');
      hr.appendChild(el('th', null, '고단가 비중 \\ 저단가'));
      lows.forEach(function (l) { hr.appendChild(el('th', null, fmt(l, 0) + ' $B/GW')); });
      t.appendChild(hr);
      shares.forEach(function (s) {
        var tr = el('tr');
        var rh = el('td', 'rh', fmt(s * 100, 0) + '%');
        tr.appendChild(rh);
        lows.forEach(function (l) {
          var bl = hiAsp * s + l * (1 - s);
          var room = isNum(cAsp) && cAsp ? (bl / cAsp - 1) * 100 : null;
          var td = el('td');
          var b = el('span', 'b', fmt(bl, 2));
          var sm = el('span', 's', isNum(room) ? fmtPct(room, 0) + (isNum(gw) ? ' · ' + (bl - cAsp > 0 ? '+' : '') + fmt((bl - cAsp) * gw, 0) + '$B' : '') : '–');
          td.appendChild(b); td.appendChild(sm);
          if (isNum(room)) {
            var a = Math.min(1, Math.abs(room) / 40);
            td.style.background = (room > 0 ? 'rgba(63,208,122,' : 'rgba(255,91,91,') + (0.06 + a * 0.30) + ')';
            b.style.color = room > 0 ? C.gapPos : C.gapNeg;
          }
          tr.appendChild(td);
        });
        t.appendChild(tr);
      });
      box.appendChild(t);
      var d = el('div', 'nc-note');
      d.style.display = 'block'; d.style.marginTop = '8px';
      d.textContent = st.p + ' ' + st.fy + ' — 고단가 ASP ' + fmt(hiAsp, 1) + ' $B/GW 고정, 컨센 암시 ASP ' +
        fmt(cAsp, 2) + ' $B/GW, GW ' + fmt(gw, 1);
      box.appendChild(d);
    }
    bar.appendChild(el('span', 'nc-lbl', '사업자'));
    bar.appendChild(tabs(keys, st.p, function (v) { st.p = v; draw(); }));
    bar.appendChild(el('span', 'nc-lbl', '연도'));
    bar.appendChild(tabs(['FY26', 'FY27', 'FY28'], st.fy, function (v) { st.fy = v; draw(); }));
    p.appendChild(bar);
    p.appendChild(box);
    if (A.notes && A.notes.length) {
      var ul = el('ul', 'nc-notes');
      A.notes.forEach(function (n) { ul.appendChild(el('li', null, n)); });
      p.appendChild(ul);
    }
    return p;
  }

  /* ============================================================ §5 매력도 랭킹 */
  var AXES = [
    { k: 'revision_pct', label: '리비전룸(%)' },
    { k: 'revision_abs', label: '절대 리비전($B)' },
    { k: 'visibility', label: '확실성(RPO)' },
    { k: 'margin_leverage', label: '마진 레버리지' }
  ];
  function rankSection(asp, which, title) {
    var R = (asp.ranking || {})[which] || [];
    if (!R.length) return null;
    var p = panel(title, '4축 점수(0–100) 가중합 → 종합 스코어');
    var w = el('div', 'nc-tbl-wrap');
    var t = el('table', 'nc-tbl');
    var hr = el('tr');
    hr.appendChild(el('th', 'l', '#'));
    hr.appendChild(el('th', 'l', '사업자'));
    AXES.forEach(function (a) { hr.appendChild(el('th', null, a.label)); });
    hr.appendChild(el('th', null, '종합'));
    hr.appendChild(el('th', 'l', '드라이버'));
    t.appendChild(hr);
    R.forEach(function (r) {
      var tr = el('tr');
      tr.appendChild(el('td', 'l', String(r.rank == null ? '' : r.rank)));
      var nm = el('td', 'l', r.provider || '');
      nm.style.fontWeight = '650';
      tr.appendChild(nm);
      var sc = r.scores || {};
      AXES.forEach(function (a) {
        var v = sc[a.k];
        var td = el('td', null, fmt(v, 0));
        if (isNum(v)) {
          var al = Math.min(1, Math.max(0, v / 100));
          td.style.background = 'rgba(76,141,255,' + (0.05 + al * 0.26) + ')';
        }
        tr.appendChild(td);
      });
      var tot = el('td', null, fmt(r.score, 1));
      tot.style.fontWeight = '700'; tot.style.color = C.recalc;
      tr.appendChild(tot);
      var dr = el('td', 'l', Array.isArray(r.drivers) ? r.drivers.join(' · ') : (r.drivers || ''));
      dr.style.whiteSpace = 'normal'; dr.style.fontFamily = 'inherit';
      dr.style.fontSize = '11px'; dr.style.maxWidth = '380px';
      tr.appendChild(dr);
      t.appendChild(tr);
    });
    w.appendChild(t);
    p.appendChild(w);
    var wt = (asp.ranking || {}).weights;
    if (wt) {
      p.appendChild(el('div', 'nc-note', '가중치: ' + Object.keys(wt).map(function (k) {
        return k + ' ' + fmt(wt[k] * 100, 0) + '%';
      }).join(' · ')));
    }
    return p;
  }

  /* ============================================================ §6 중화권 노트 */
  function chinaNotes(asp) {
    var cn = (asp._china_notes || asp.china_notes);
    if (!cn || !cn.length) return null;
    var p = panel('⑥-c 중화권 구조적 차이', '가격구조·칩 제약 — 서방과 동일 잣대 적용 불가');
    var ul = el('ul', 'nc-notes');
    cn.forEach(function (n) {
      var li = el('li');
      if (typeof n === 'string') li.textContent = n;
      else {
        li.appendChild(document.createTextNode((n.text || '') + ' '));
        if (n.src) li.appendChild(link(n.src, '↗'));
      }
      ul.appendChild(li);
    });
    p.appendChild(ul);
    return p;
  }

  /* ------------------------------------------------------------- 방법론 패널 */
  function methodPanel(asp) {
    var A = asp.assumptions || {};
    var p = panel('방법론 · 가정', '모든 가정 명시 — 미확보 값은 null 유지(추정 채움 금지)');
    var ul = el('ul', 'nc-notes');
    [
      '① 컨센 암시 ASP($B/GW) = 컨센 매출 ÷ 추정 GW.',
      '② 재계산 ASP = 고단가 ASP × 비중 + 저단가 ASP × (1−비중).',
      '③ 리비전룸(%) = (재계산 ASP ÷ 컨센 암시 ASP − 1) × 100.',
      '④ 리비전룸($B) = (재계산 ASP − 컨센 암시 ASP) × GW.',
      '⑤ 케이스: 보수/중립/공격 = 저단가 축과 고단가 비중을 함께 이동.'
    ].forEach(function (s) { ul.appendChild(el('li', null, s)); });
    if (A.cases) {
      Object.keys(A.cases).forEach(function (k) {
        var c = A.cases[k];
        ul.appendChild(el('li', null, '케이스 ' + k + ': ' + (typeof c === 'string' ? c : JSON.stringify(c))));
      });
    }
    (A.notes || []).forEach(function (n) { ul.appendChild(el('li', null, n)); });
    p.appendChild(ul);
    return p;
  }

  /* -------------------------------------------------------------- 렌더 본체 */
  window.renderNeocloud = function renderNeocloud(root, data) {
    if (!root) return;
    injectCSS(root.ownerDocument || document);
    root.innerHTML = '';
    root.classList.add('nc');
    data = data || {};
    var model = data.model || (data.companies ? data : {});
    var asp = data.asp || (data.providers ? data : {});
    if (!model.companies && !asp.providers) {
      root.appendChild(el('div', 'nc-empty', 'neocloud_model.json / cloud_asp_revision.json 로드 실패'));
      return;
    }
    var meta = model._meta || asp._meta || {};
    var head = el('div', 'nc-head');
    head.appendChild(el('h2', null, '네오클라우드 용량·단가 모델 → 클라우드 탑라인 리비전룸'));
    var anc = model.anchors || [];
    head.appendChild(el('div', 'nc-sub',
      'neoclouds=' + Object.keys(model.companies || {}).length +
      ' · providers=' + Object.keys(asp.providers || {}).length +
      ' · anchors verified=' + anc.filter(function (a) { return a.verified === true; }).length + '/' + anc.length +
      (meta.built ? ' · built ' + String(meta.built).slice(0, 10) : '')));
    root.appendChild(head);

    [companySection(model), crossTable(model), anchorSection(model), ladderSection(model),
     aspCompare(asp, 'global'), mixSection(asp, 'global'), heatSection(asp),
     rankSection(asp, 'global', '⑤ 매력도 랭킹 (글로벌)'),
     el('div', 'nc-head'),
     aspCompare(asp, 'china'), mixSection(asp, 'china'),
     rankSection(asp, 'china', '⑥-d 매력도 랭킹 (중화권 별도)'),
     chinaNotes(asp), methodPanel(asp)
    ].forEach(function (n) { if (n) root.appendChild(n); });
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = { renderNeocloud: null };
})();
