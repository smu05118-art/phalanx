/* insight_charts.js — 💡 인사이트 탭 렌더러 (팔랑크스 다크테마)
 * 전역: window.renderInsight(el, data)
 *   data 는 아래 중 아무 형태나 받는다.
 *     1) insight_build.py 산출 insights.json 객체 (quotes 는 window.INSQ 에서 자동 탐색)
 *     2) { insights: <insights.json>, quotes: <quotes.json> }
 *     3) { data: <insights.json>, quotes: ... }
 * 의존성 0 — Chart.js 가 있으면 스파크라인에 쓰고, 없으면 인라인 SVG 로 폴백한다.
 */
(function () {
  'use strict';

  var CSS_ID = 'insight-css';

  /* 카드 유형별 색 — 교차확인 초록 / 모순 주황 / 임계근접 빨강 / 컨센갭 파랑 */
  var TYPES = {
    cross_confirm: { ko: '교차 확인', color: '#00e6b8', icon: '⊕' },
    contradiction: { ko: '모순 탐지', color: '#ffbe2e', icon: '⇄' },
    threshold: { ko: '임계 근접', color: '#ff5c5c', icon: '◉' },
    consensus_gap: { ko: '컨센 갭', color: '#3d8bfd', icon: '△' }
  };
  var TYPE_ORDER = ['cross_confirm', 'contradiction', 'threshold', 'consensus_gap'];

  var CONF = {
    high: { ko: '높음', color: '#00e6b8' },
    medium: { ko: '보통', color: '#ffbe2e' },
    low: { ko: '낮음', color: '#6a6a9a' }
  };

  /* ---------------------------------------------------------------- style */
  var CSS = [
    '.ins{color:var(--tx,#e8e8f4);font-size:13px;line-height:1.5}',
    '.ins *{box-sizing:border-box}',
    '.ins-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin:0 0 14px}',
    '.ins-head h2{font-size:17px;margin:0;font-weight:750;letter-spacing:-.2px}',
    '.ins-sub{color:var(--dim,#6a6a9a);font-size:10.5px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}',
    '.ins-sub b{color:var(--tx,#e8e8f4);font-weight:700}',

    '.ins-sec{margin:0 0 20px}',
    '.ins-sec>h3{font-size:11px;margin:0 0 9px;font-weight:800;color:var(--dim,#6a6a9a);text-transform:uppercase;letter-spacing:.7px}',
    '.ins-sec>h3 em{font-style:normal;color:var(--tx,#e8e8f4);text-transform:none;letter-spacing:0;font-weight:600;font-size:11px;margin-left:7px}',

    /* 오늘의 종합 판독 */
    '.ins-hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}',
    '.ins-hz{background:linear-gradient(160deg,rgba(0,230,184,.09),rgba(0,230,184,0) 62%),var(--s1,#0d0d1a);border:1px solid var(--bd,#28284a);border-left:3px solid #00e6b8;border-radius:11px;padding:13px 14px;display:flex;flex-direction:column;gap:8px}',
    '.ins-hz .hr{display:flex;align-items:center;gap:7px}',
    '.ins-hz .hn{font-family:ui-monospace,Menlo,monospace;font-size:19px;font-weight:800;color:#00e6b8;line-height:1}',
    '.ins-hz .ht{font-size:13px;font-weight:750;line-height:1.35;flex:1}',
    '.ins-hz .hv{font-size:12px;color:#c9d2e0;line-height:1.55}',

    /* 필터 */
    '.ins-bar{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin:0 0 11px}',
    '.ins-pill{border:1px solid var(--bd,#28284a);background:var(--s1,#0d0d1a);color:var(--dim,#6a6a9a);border-radius:999px;padding:4px 12px;font-size:11.5px;cursor:pointer;line-height:1.5;font-family:inherit;font-weight:600;white-space:nowrap;transition:.13s}',
    '.ins-pill:hover{color:var(--tx,#e8e8f4)}',
    '.ins-pill.on{color:#06060e;font-weight:750}',
    '.ins-pill i{font-style:normal;opacity:.65;margin-left:5px;font-size:10px}',
    '.ins-search{margin-left:auto;background:var(--s1,#0d0d1a);border:1px solid var(--bd,#28284a);color:var(--tx,#e8e8f4);border-radius:999px;padding:5px 13px;font-size:11.5px;min-width:180px;outline:none;font-family:inherit}',
    '.ins-search:focus{border-color:var(--dim,#6a6a9a)}',

    /* 카드 그리드 */
    '.ins-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px;align-items:start}',
    '.ins-card{background:var(--s1,#0d0d1a);border:1px solid var(--bd,#28284a);border-top:2px solid var(--ic,#6a6a9a);border-radius:11px;padding:12px 13px 11px;display:flex;flex-direction:column;gap:9px}',
    '.ins-card .cb{display:flex;align-items:center;gap:7px;flex-wrap:wrap}',
    '.ins-badge{font-size:9.5px;font-weight:800;letter-spacing:.4px;border-radius:5px;padding:2px 7px;color:#06060e;text-transform:uppercase;white-space:nowrap}',
    '.ins-conf{margin-left:auto;font-size:9.5px;font-weight:700;font-family:ui-monospace,Menlo,monospace;border:1px solid var(--bd,#28284a);border-radius:5px;padding:1px 6px;white-space:nowrap}',
    '.ins-card h4{font-size:13px;margin:0;font-weight:750;line-height:1.4;letter-spacing:-.1px}',
    '.ins-vd{font-size:12px;color:#c9d2e0;line-height:1.6;margin:0}',

    /* 근거 칩 */
    '.ins-chips{display:flex;flex-wrap:wrap;gap:5px}',
    '.ins-chip{border:1px solid var(--bd,#28284a);background:var(--s2,#141428);border-radius:7px;padding:4px 8px;font-size:10.5px;line-height:1.35;max-width:100%}',
    '.ins-chip .cl{color:var(--dim,#6a6a9a);display:block;font-size:9.5px;margin-bottom:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:190px}',
    '.ins-chip .cv{font-family:ui-monospace,Menlo,monospace;font-weight:750;font-size:11.5px}',
    '.ins-chip .cx{font-family:ui-monospace,Menlo,monospace;font-size:9.5px;margin-left:5px}',
    '.ins-chip .cs{color:var(--dim,#6a6a9a);font-size:9px;font-family:ui-monospace,Menlo,monospace;margin-left:5px}',
    '.ins-stale{color:#ffbe2e;font-size:9px;font-weight:700;margin-left:4px}',

    '.ins-cv{position:relative;height:74px;margin:1px 0 0}',
    '.ins-cvl{font-size:9px;color:var(--dim,#6a6a9a);font-family:ui-monospace,Menlo,monospace;display:flex;gap:8px;flex-wrap:wrap}',
    '.ins-cvl i{font-style:normal}',

    '.ins-link{font-size:11px;color:#9aa6bb;line-height:1.65;border-top:1px dashed var(--bd,#28284a);padding-top:8px;margin:0}',
    '.ins-link .lh{color:var(--dim,#6a6a9a);font-size:9.5px;font-weight:800;letter-spacing:.5px;text-transform:uppercase;display:block;margin-bottom:3px}',
    '.ins-more{background:none;border:0;color:var(--dim,#6a6a9a);font-size:10.5px;cursor:pointer;padding:0;font-family:inherit;text-decoration:underline;text-underline-offset:2px;align-self:flex-start}',
    '.ins-more:hover{color:var(--tx,#e8e8f4)}',
    '.ins-why{font-size:10px;color:var(--dim,#6a6a9a);line-height:1.55;font-family:ui-monospace,Menlo,monospace}',

    /* 임계 랭킹 표 */
    '.ins-rank{width:100%;border-collapse:collapse;font-size:11px;margin-top:2px}',
    '.ins-rank th{text-align:right;color:var(--dim,#6a6a9a);font-weight:700;padding:4px 6px;border-bottom:1px solid var(--bd,#28284a);font-size:9.5px;text-transform:uppercase;letter-spacing:.4px;white-space:nowrap}',
    '.ins-rank th.l,.ins-rank td.l{text-align:left}',
    '.ins-rank td{padding:4px 6px;border-bottom:1px solid rgba(40,40,74,.55);font-family:ui-monospace,Menlo,monospace;text-align:right;white-space:nowrap}',
    '.ins-rank td.l{font-family:inherit;max-width:230px;overflow:hidden;text-overflow:ellipsis}',
    '.ins-rank tr:hover td{background:rgba(255,255,255,.028)}',
    '.ins-gapbar{display:inline-block;height:4px;border-radius:2px;vertical-align:middle;margin-right:5px;min-width:2px}',
    '.ins-rwrap{max-height:290px;overflow:auto}',

    /* 인용 갤러리 */
    '.ins-qgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px;align-items:start}',
    '.ins-q{background:var(--s1,#0d0d1a);border:1px solid var(--bd,#28284a);border-radius:11px;padding:12px 13px;display:flex;flex-direction:column;gap:8px;position:relative}',
    '.ins-q:before{content:"\\201C";position:absolute;top:2px;right:12px;font-size:40px;line-height:1;color:rgba(196,92,255,.16);font-family:Georgia,serif}',
    '.ins-q .qt{font-size:12.5px;line-height:1.62;font-weight:520;color:#e8e8f4;margin:0;position:relative;z-index:1}',
    '.ins-q .qo{font-size:11px;line-height:1.6;color:#8f9ab0;margin:0;font-style:italic;border-left:2px solid var(--bd,#28284a);padding-left:9px}',
    '.ins-q .qw{display:flex;gap:6px;align-items:baseline;flex-wrap:wrap;font-size:10.5px}',
    '.ins-q .qwho{font-weight:750;color:#c9d2e0;font-size:11px}',
    '.ins-q .qwhen{color:var(--dim,#6a6a9a);font-family:ui-monospace,Menlo,monospace;font-size:10px}',
    '.ins-q .qsharp{font-size:11px;color:#c45cff;line-height:1.55;margin:0}',
    '.ins-q .qsharp b{color:#c45cff;font-weight:800;margin-right:4px}',
    '.ins-q .qf{display:flex;gap:6px;align-items:center;flex-wrap:wrap;border-top:1px dashed var(--bd,#28284a);padding-top:7px;margin-top:1px}',
    '.ins-tag{border:1px solid var(--bd,#28284a);color:var(--dim,#6a6a9a);border-radius:5px;padding:1px 6px;font-size:9.5px;font-family:ui-monospace,Menlo,monospace;cursor:pointer;background:none;line-height:1.6}',
    '.ins-tag:hover{color:var(--tx,#e8e8f4)}',
    '.ins-tag.on{background:#c45cff;border-color:#c45cff;color:#06060e;font-weight:750}',
    '.ins-src{color:#3d8bfd;text-decoration:none;font-size:10px;font-family:ui-monospace,Menlo,monospace;margin-left:auto;white-space:nowrap}',
    '.ins-src:hover{text-decoration:underline}',
    '.ins-dl{display:inline-flex;align-items:center;gap:5px;border:1px solid rgba(0,230,184,.35);background:rgba(0,230,184,.07);border-radius:6px;padding:2px 7px;font-size:10px;color:#00e6b8;font-family:ui-monospace,Menlo,monospace;max-width:100%}',
    '.ins-dl span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.ins-dl b{font-weight:800}',

    '.ins-empty{color:var(--dim,#6a6a9a);padding:22px;text-align:center;border:1px dashed var(--bd,#28284a);border-radius:10px;font-size:12px}',
    '.ins-foot{margin-top:18px;padding-top:11px;border-top:1px solid var(--bd,#28284a);font-size:9.5px;color:var(--dim,#6a6a9a);line-height:1.7;font-family:ui-monospace,Menlo,monospace}'
  ].join('\n');

  function injectCSS(doc) {
    if (doc.getElementById(CSS_ID)) return;
    var st = doc.createElement('style');
    st.id = CSS_ID;
    st.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(st);
  }

  /* ----------------------------------------------------------------- util */
  function el(tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }

  function num(v) {
    return typeof v === 'number' && isFinite(v);
  }

  function fmtNum(v, unit) {
    if (v == null) return '—';
    if (typeof v === 'string') return v;
    if (!num(v)) return '—';
    var a = Math.abs(v), d;
    if (a >= 1000) d = 0;
    else if (a >= 100) d = 1;
    else if (a >= 1) d = 2;
    else d = 3;
    var s = v.toFixed(d).replace(/\.?0+$/, '');
    if (s === '' || s === '-') s = '0';
    return s + (unit || '');
  }

  function signed(v, unit) {
    if (!num(v)) return '—';
    return (v > 0 ? '+' : '') + fmtNum(v, unit == null ? '%' : unit);
  }

  function hex2rgba(h, a) {
    h = String(h || '#6a6a9a').replace('#', '');
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
  }

  function esc(s) {
    return String(s == null ? '' : s);
  }

  /* --------------------------------------------------------- 스파크라인 */
  var CHARTS = [];

  function destroyCharts() {
    for (var i = 0; i < CHARTS.length; i++) {
      try { CHARTS[i].destroy(); } catch (e) { /* noop */ }
    }
    CHARTS = [];
  }

  function svgSpark(sp, color, w, h) {
    var vals = (sp.values || []).filter(num);
    if (vals.length < 2) return null;
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var refs = [];
    if (num(sp.threshold)) refs.push(sp.threshold);
    if (num(sp.baseline)) refs.push(sp.baseline);
    for (var r = 0; r < refs.length; r++) {
      lo = Math.min(lo, refs[r]); hi = Math.max(hi, refs[r]);
    }
    if (hi === lo) { hi += 1; lo -= 1; }
    var pad = (hi - lo) * 0.12; lo -= pad; hi += pad;
    var n = vals.length, x = function (i) { return (i / (n - 1)) * (w - 2) + 1; };
    var y = function (v) { return h - 3 - ((v - lo) / (hi - lo)) * (h - 6); };

    var ns = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', h);
    svg.setAttribute('preserveAspectRatio', 'none');

    function refLine(v, col, dash) {
      var ln = document.createElementNS(ns, 'line');
      ln.setAttribute('x1', 0); ln.setAttribute('x2', w);
      ln.setAttribute('y1', y(v)); ln.setAttribute('y2', y(v));
      ln.setAttribute('stroke', col); ln.setAttribute('stroke-width', '1');
      ln.setAttribute('stroke-dasharray', dash);
      svg.appendChild(ln);
    }
    if (num(sp.baseline)) refLine(sp.baseline, 'rgba(106,106,154,.55)', '2 3');
    if (num(sp.threshold)) refLine(sp.threshold, hex2rgba('#ff5c5c', .6), '4 3');

    var dPath = '', dArea = '';
    for (var i = 0; i < n; i++) {
      dPath += (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(vals[i]).toFixed(1) + ' ';
    }
    dArea = dPath + 'L' + x(n - 1).toFixed(1) + ' ' + h + ' L' + x(0).toFixed(1) + ' ' + h + ' Z';

    var ar = document.createElementNS(ns, 'path');
    ar.setAttribute('d', dArea); ar.setAttribute('fill', hex2rgba(color, .13));
    ar.setAttribute('stroke', 'none');
    svg.appendChild(ar);

    var pt = document.createElementNS(ns, 'path');
    pt.setAttribute('d', dPath); pt.setAttribute('fill', 'none');
    pt.setAttribute('stroke', color); pt.setAttribute('stroke-width', '1.6');
    pt.setAttribute('stroke-linejoin', 'round'); pt.setAttribute('stroke-linecap', 'round');
    svg.appendChild(pt);

    var dot = document.createElementNS(ns, 'circle');
    dot.setAttribute('cx', x(n - 1)); dot.setAttribute('cy', y(vals[n - 1]));
    dot.setAttribute('r', '2.4'); dot.setAttribute('fill', color);
    svg.appendChild(dot);
    return svg;
  }

  function drawSpark(host, sp, color) {
    if (!sp || !sp.values || sp.values.length < 2) return;
    var box = el('div', 'ins-cv');
    host.appendChild(box);

    var legend = el('div', 'ins-cvl');
    var lg = el('i', null, (sp.label || '') + ' · ' + (sp.labels[0] || '') + '→' + (sp.labels[sp.labels.length - 1] || ''));
    legend.appendChild(lg);
    if (num(sp.threshold)) legend.appendChild(el('i', null, '⋯ 임계 ' + fmtNum(sp.threshold)));
    if (num(sp.baseline)) legend.appendChild(el('i', null, '– 기준 ' + fmtNum(sp.baseline)));
    host.appendChild(legend);

    if (typeof window.Chart === 'function') {
      var cv = el('canvas');
      box.appendChild(cv);
      var ds = [{
        label: sp.label || '값',
        data: sp.values,
        borderColor: color,
        backgroundColor: hex2rgba(color, .13),
        borderWidth: 1.7,
        fill: true,
        tension: 0.28,
        pointRadius: 0,
        pointHoverRadius: 3
      }];
      function flat(v, col, dash) {
        return {
          label: dash ? '임계' : '기준',
          data: sp.values.map(function () { return v; }),
          borderColor: col, borderWidth: 1, borderDash: dash ? [4, 3] : [2, 3],
          pointRadius: 0, fill: false, tension: 0
        };
      }
      if (num(sp.baseline)) ds.push(flat(sp.baseline, 'rgba(106,106,154,.55)', false));
      if (num(sp.threshold)) ds.push(flat(sp.threshold, hex2rgba('#ff5c5c', .6), true));
      try {
        CHARTS.push(new window.Chart(cv, {
          type: 'line',
          data: { labels: sp.labels, datasets: ds },
          options: {
            responsive: true, maintainAspectRatio: false, animation: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
              legend: { display: false },
              tooltip: {
                displayColors: false,
                callbacks: {
                  label: function (c) { return c.dataset.label + ': ' + fmtNum(c.parsed.y); }
                }
              }
            },
            scales: {
              x: { display: false, grid: { display: false } },
              y: { display: false, grid: { display: false } }
            }
          }
        }));
        return;
      } catch (e) { /* Chart.js 실패 → SVG 폴백 */ }
    }
    var s = svgSpark(sp, color, 300, 74);
    if (s) box.appendChild(s); else box.remove();
  }

  /* ------------------------------------------------------------- 근거 칩 */
  function chip(ev, color) {
    var c = el('div', 'ins-chip');
    var lab = el('span', 'cl', ev.label || ev.signal || '');
    if (ev.src_file) lab.title = ev.src_file + ' :: ' + (ev.src || '');
    c.appendChild(lab);

    var row = el('div');
    var v = el('span', 'cv', fmtNum(ev.value, ev.unit === '%' ? '%' : ''));
    v.style.color = color;
    row.appendChild(v);
    if (ev.unit && ev.unit !== '%') {
      var u = el('span', 'cs', ev.unit);
      row.appendChild(u);
    }
    if (num(ev.gap_pct)) {
      var g = el('span', 'cx', (ev.gap_pct >= 0 ? '▲' : '▼') + ' 임계 ' + signed(ev.gap_pct));
      g.style.color = ev.gap_pct >= 0 ? '#00e6b8' : '#ff5c5c';
      g.title = '임계 ' + fmtNum(ev.threshold);
      row.appendChild(g);
    } else if (num(ev.vs_baseline_pct)) {
      var b = el('span', 'cx', '기준 ' + signed(ev.vs_baseline_pct));
      b.style.color = ev.vs_baseline_pct >= 0 ? '#00e6b8' : '#ff5c5c';
      b.title = '기준선 ' + fmtNum(ev.baseline);
      row.appendChild(b);
    }
    if (ev.asof) row.appendChild(el('span', 'cs', ev.asof));
    if (ev.stale) {
      var s = el('span', 'ins-stale', '⚠' + (ev.age_months ? ev.age_months + '개월' : '지연'));
      s.title = '최신 공시가 오래됨 — 신뢰도 차감';
      row.appendChild(s);
    }
    c.appendChild(row);
    if (ev.note) c.title = (c.title ? c.title + '\n' : '') + ev.note;
    return c;
  }

  /* ------------------------------------------------------------ 랭킹 표 */
  function rankTable(rows) {
    var wrap = el('div', 'ins-rwrap');
    var t = el('table', 'ins-rank');
    var thead = el('thead'), tr = el('tr');
    [['지표', 'l'], ['현재', ''], ['임계', ''], ['거리', ''], ['시점', '']].forEach(function (h) {
      var th = el('th', h[1], h[0]);
      tr.appendChild(th);
    });
    thead.appendChild(tr); t.appendChild(thead);

    var tb = el('tbody');
    var maxGap = 1;
    rows.forEach(function (r) { maxGap = Math.max(maxGap, Math.abs(r.gap_pct || 0)); });

    rows.forEach(function (r) {
      var row = el('tr');
      var c0 = el('td', 'l');
      c0.textContent = r.label;
      if (r.src_file) c0.title = r.src_file + ' :: ' + (r.src || '');
      if (r.stale) {
        var w = el('span', 'ins-stale', ' ⚠');
        c0.appendChild(w);
      }
      row.appendChild(c0);
      row.appendChild(el('td', null, fmtNum(r.value, r.unit === '%' ? '%' : '')));
      row.appendChild(el('td', null, fmtNum(r.threshold)));

      var c3 = el('td');
      var bar = el('span', 'ins-gapbar');
      var pct = Math.min(100, (Math.abs(r.gap_pct) / maxGap) * 100);
      bar.style.width = Math.max(2, pct * 0.42) + 'px';
      bar.style.background = r.above ? '#00e6b8' : '#ff5c5c';
      c3.appendChild(bar);
      var gv = el('span', null, signed(r.gap_pct));
      gv.style.color = r.above ? '#00e6b8' : '#ff5c5c';
      gv.style.fontWeight = '700';
      c3.appendChild(gv);
      row.appendChild(c3);

      var c4 = el('td', null, r.asof || '');
      c4.style.color = 'var(--dim,#6a6a9a)';
      row.appendChild(c4);
      tb.appendChild(row);
    });
    t.appendChild(tb);
    wrap.appendChild(t);
    return wrap;
  }

  /* --------------------------------------------------------------- 카드 */
  function cardNode(c) {
    var meta = TYPES[c.type] || { ko: c.type, color: '#6a6a9a', icon: '·' };
    var n = el('div', 'ins-card');
    n.style.setProperty('--ic', meta.color);

    var bar = el('div', 'cb');
    var b = el('span', 'ins-badge', meta.icon + ' ' + meta.ko);
    b.style.background = meta.color;
    bar.appendChild(b);

    var cf = (c.confidence || {});
    var cm = CONF[cf.level] || CONF.low;
    var cb = el('span', 'ins-conf', '신뢰 ' + cm.ko + (num(cf.score) ? ' ' + cf.score.toFixed(2) : ''));
    cb.style.color = cm.color;
    cb.style.borderColor = hex2rgba(cm.color, .4);
    if (cf.why) cb.title = cf.why;
    bar.appendChild(cb);
    n.appendChild(bar);

    n.appendChild(el('h4', null, c.title));
    if (c.verdict) n.appendChild(el('p', 'ins-vd', c.verdict));

    if (c.evidence && c.evidence.length) {
      var chips = el('div', 'ins-chips');
      c.evidence.forEach(function (e) { chips.appendChild(chip(e, meta.color)); });
      n.appendChild(chips);
    }

    if (c.spark) drawSpark(n, c.spark, meta.color);

    if (c.ranking && c.ranking.length) n.appendChild(rankTable(c.ranking));

    if (c.link) {
      var lk = el('p', 'ins-link');
      lk.appendChild(el('span', 'lh', '연결고리'));
      var short = c.link.length > 150 ? c.link.slice(0, 150) + '…' : c.link;
      var body = el('span', null, short);
      lk.appendChild(body);
      n.appendChild(lk);
      if (c.link.length > 150) {
        var mb = el('button', 'ins-more', '더 보기');
        var open = false;
        mb.addEventListener('click', function () {
          open = !open;
          body.textContent = open ? c.link : short;
          mb.textContent = open ? '접기' : '더 보기';
        });
        n.appendChild(mb);
      }
    }
    if (cf.why) n.appendChild(el('div', 'ins-why', '※ ' + cf.why));
    return n;
  }

  /* --------------------------------------------------------- 인용 카드 */
  function quoteNode(q, onTag) {
    var n = el('div', 'ins-q');

    var w = el('div', 'qw');
    w.appendChild(el('span', 'qwho', q.who || '—'));
    if (q.when) w.appendChild(el('span', 'qwhen', q.when));
    if (q.source_type) {
      var st = el('span', 'qwhen', '· ' + q.source_type);
      w.appendChild(st);
    }
    n.appendChild(w);

    if (q.ko) n.appendChild(el('p', 'qt', '“' + q.ko + '”'));
    if (q.original) {
      var o = el('p', 'qo', q.original);
      if (!q.ko) o.className = 'qt';
      n.appendChild(o);
    }
    if (q.why_sharp) {
      var s = el('p', 'qsharp');
      s.appendChild(el('b', null, '왜 날카로운가'));
      s.appendChild(document.createTextNode(q.why_sharp));
      n.appendChild(s);
    }

    var dl = q.our_data_link;
    if (dl && (dl.label || dl.signal)) {
      var d = el('div', 'ins-dl');
      d.appendChild(el('b', null, '↔'));
      var txt = dl.label || dl.signal;
      if (num(dl.value)) txt += ' ' + fmtNum(dl.value, dl.unit === '%' ? '%' : '') + (dl.asof ? ' (' + dl.asof + ')' : '');
      d.appendChild(el('span', null, txt));
      d.title = '우리 지표 연결' + (dl.auto ? ' (태그 자동매칭)' : ' (수동 지정)');
      n.appendChild(d);
    }

    var f = el('div', 'qf');
    (q.tags || []).slice(0, 5).forEach(function (t) {
      var tb = el('button', 'ins-tag', t);
      tb.addEventListener('click', function () { onTag(t); });
      f.appendChild(tb);
    });
    if (q.where) {
      var a = el('a', 'ins-src', '출처 ↗');
      a.href = q.where;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.title = q.where;
      f.appendChild(a);
    }
    n.appendChild(f);
    if (q.context_snippet) n.title = q.context_snippet;
    return n;
  }

  /* --------------------------------------------------------------- main */
  window.renderInsight = function (root, data) {
    if (!root) return;
    injectCSS(document);
    destroyCharts();
    root.innerHTML = '';

    data = data || {};
    var ins = data.cards ? data : (data.insights || data.data || {});
    var qdb = data.quotes || ins.quotes || window.INSQ || window.INSIGHT_QUOTES || {};
    if (Array.isArray(qdb)) qdb = { quotes: qdb };
    var quotes = (qdb && qdb.quotes) || [];
    var cards = ins.cards || [];

    var wrap = el('div', 'ins');
    root.appendChild(wrap);

    /* --- 헤더 */
    var head = el('div', 'ins-head');
    head.appendChild(el('h2', null, '💡 인사이트 — 데이터 종합 해석'));
    var sub = el('div', 'ins-sub');
    sub.innerHTML = '카드 <b>' + cards.length + '</b> · 시그널 <b>' + (ins.n_signals || Object.keys(ins.signals || {}).length) +
      '</b> · 인용 <b>' + quotes.length + '</b> · 생성 ' + esc(ins.generated || '—');
    head.appendChild(sub);
    wrap.appendChild(head);

    if (!cards.length && !quotes.length) {
      wrap.appendChild(el('div', 'ins-empty', '인사이트 데이터가 없습니다 — insight_build.py 를 먼저 실행하세요.'));
      return;
    }

    /* --- 오늘의 종합 판독: 교차확인 상위 3 */
    var byId = {};
    cards.forEach(function (c) { byId[c.id] = c; });
    var heroIds = (ins.top3 || []).slice(0, 3);
    if (!heroIds.length) {
      heroIds = cards.filter(function (c) { return c.type === 'cross_confirm'; })
        .sort(function (a, b) { return (b.strength || 0) - (a.strength || 0); })
        .slice(0, 3).map(function (c) { return c.id; });
    }
    var heroes = heroIds.map(function (i) { return byId[i]; }).filter(Boolean);

    if (heroes.length) {
      var hs = el('div', 'ins-sec');
      var hh = el('h3', null, '오늘의 종합 판독');
      hh.appendChild(el('em', null, '서로 다른 소스가 같은 방향을 가리키는 카드 상위 ' + heroes.length + '개'));
      hs.appendChild(hh);
      var hg = el('div', 'ins-hero');
      heroes.forEach(function (c, i) {
        var meta = TYPES[c.type] || TYPES.cross_confirm;
        var hz = el('div', 'ins-hz');
        hz.style.borderLeftColor = meta.color;
        hz.style.background = 'linear-gradient(160deg,' + hex2rgba(meta.color, .09) + ',' + hex2rgba(meta.color, 0) + ' 62%),var(--s1,#0d0d1a)';
        var hr = el('div', 'hr');
        var hn = el('span', 'hn', '0' + (i + 1));
        hn.style.color = meta.color;
        hr.appendChild(hn);
        hr.appendChild(el('span', 'ht', c.title));
        hz.appendChild(hr);
        hz.appendChild(el('div', 'hv', c.verdict || ''));
        var ch = el('div', 'ins-chips');
        (c.evidence || []).slice(0, 3).forEach(function (e) { ch.appendChild(chip(e, meta.color)); });
        hz.appendChild(ch);
        hg.appendChild(hz);
      });
      hs.appendChild(hg);
      wrap.appendChild(hs);
    }

    /* --- 카드 그리드 + 유형 필터 */
    var gs = el('div', 'ins-sec');
    var gh = el('h3', null, '해석 카드');
    gh.appendChild(el('em', null, '근거 수치는 모두 로컬 원본 파일 실측값'));
    gs.appendChild(gh);

    var bar = el('div', 'ins-bar');
    var grid = el('div', 'ins-grid');
    var curType = 'all', curQ = '';

    function paint() {
      grid.innerHTML = '';
      destroyCharts();
      var q = curQ.trim().toLowerCase();
      var list = cards.filter(function (c) {
        if (curType !== 'all' && c.type !== curType) return false;
        if (!q) return true;
        var hay = [c.title, c.verdict, c.link].join(' ').toLowerCase();
        (c.evidence || []).forEach(function (e) { hay += ' ' + (e.label || '').toLowerCase(); });
        return hay.indexOf(q) >= 0;
      });
      if (!list.length) {
        grid.appendChild(el('div', 'ins-empty', '조건에 맞는 카드가 없습니다.'));
        return;
      }
      list.forEach(function (c) { grid.appendChild(cardNode(c)); });
    }

    var counts = ins.counts || {};
    var pills = [['all', '전체', cards.length, '#e8e8f4']];
    TYPE_ORDER.forEach(function (t) {
      if (counts[t] || cards.some(function (c) { return c.type === t; })) {
        pills.push([t, TYPES[t].ko, counts[t] || cards.filter(function (c) { return c.type === t; }).length, TYPES[t].color]);
      }
    });
    var pillNodes = [];
    pills.forEach(function (p) {
      var b = el('button', 'ins-pill', p[1]);
      b.appendChild(el('i', null, String(p[2])));
      b.addEventListener('click', function () {
        curType = p[0];
        pillNodes.forEach(function (x) {
          x.node.className = 'ins-pill' + (x.key === curType ? ' on' : '');
          x.node.style.background = x.key === curType ? x.col : '';
          x.node.style.borderColor = x.key === curType ? x.col : '';
        });
        paint();
      });
      bar.appendChild(b);
      pillNodes.push({ key: p[0], node: b, col: p[3] });
    });
    pillNodes[0].node.className = 'ins-pill on';
    pillNodes[0].node.style.background = '#e8e8f4';
    pillNodes[0].node.style.borderColor = '#e8e8f4';

    var search = el('input', 'ins-search');
    search.type = 'search';
    search.placeholder = '카드 검색 (지표·문구)';
    var tmr = null;
    search.addEventListener('input', function () {
      curQ = search.value;
      if (tmr) clearTimeout(tmr);
      tmr = setTimeout(paint, 150);
    });
    bar.appendChild(search);

    gs.appendChild(bar);
    gs.appendChild(grid);
    wrap.appendChild(gs);
    paint();

    /* --- 인용 갤러리 */
    if (quotes.length) {
      var qs = el('div', 'ins-sec');
      var qh = el('h3', null, '기라성 — 인용 갤러리');
      qh.appendChild(el('em', null, '공개 소스에서 확인된 발언만 · 최신순'));
      qs.appendChild(qh);

      var qbar = el('div', 'ins-bar');
      var qgrid = el('div', 'ins-qgrid');
      var curTag = null, curQQ = '';

      function qpaint() {
        qgrid.innerHTML = '';
        var q2 = curQQ.trim().toLowerCase();
        var list = quotes.filter(function (x) {
          if (curTag && (x.tags || []).indexOf(curTag) < 0) return false;
          if (!q2) return true;
          var hay = [x.who, x.ko, x.original, x.why_sharp, (x.tags || []).join(' ')].join(' ').toLowerCase();
          return hay.indexOf(q2) >= 0;
        });
        if (!list.length) {
          qgrid.appendChild(el('div', 'ins-empty', '조건에 맞는 인용이 없습니다.'));
          return;
        }
        list.forEach(function (x) { qgrid.appendChild(quoteNode(x, setTag)); });
      }

      /* 빈도순 태그 */
      var freq = {};
      quotes.forEach(function (x) {
        (x.tags || []).forEach(function (t) { freq[t] = (freq[t] || 0) + 1; });
      });
      var tagList = Object.keys(freq).sort(function (a, b) { return freq[b] - freq[a] || a.localeCompare(b); });

      var tagNodes = [];
      function setTag(t) {
        curTag = (curTag === t) ? null : t;
        tagNodes.forEach(function (x) {
          x.node.className = 'ins-tag' + (x.key === curTag ? ' on' : '');
        });
        qpaint();
      }
      var allBtn = el('button', 'ins-tag on', '전체 ' + quotes.length);
      allBtn.addEventListener('click', function () { setTag(null); });
      qbar.appendChild(allBtn);
      tagNodes.push({ key: null, node: allBtn });

      tagList.slice(0, 22).forEach(function (t) {
        var b = el('button', 'ins-tag', t + ' ' + freq[t]);
        b.addEventListener('click', function () { setTag(t); });
        qbar.appendChild(b);
        tagNodes.push({ key: t, node: b });
      });

      var qsearch = el('input', 'ins-search');
      qsearch.type = 'search';
      qsearch.placeholder = '인용 검색 (인물·기업·문구)';
      var tmr2 = null;
      qsearch.addEventListener('input', function () {
        curQQ = qsearch.value;
        if (tmr2) clearTimeout(tmr2);
        tmr2 = setTimeout(qpaint, 150);
      });
      qbar.appendChild(qsearch);

      qs.appendChild(qbar);
      qs.appendChild(qgrid);
      wrap.appendChild(qs);
      qpaint();
    }

    /* --- 푸터 */
    var srcs = (ins.sources || []).filter(function (s) { return s.exists; });
    var foot = el('div', 'ins-foot');
    foot.appendChild(el('div', null, '데이터 소스 ' + srcs.length + '종 · ' +
      srcs.slice(0, 10).map(function (s) { return s.key; }).join(', ') + (srcs.length > 10 ? ' …' : '')));
    if (ins.policy) foot.appendChild(el('div', null, '원칙: ' + ins.policy));
    if (qdb.updated) foot.appendChild(el('div', null, '인용 갱신 ' + qdb.updated + ' · append 방식(중복 자동 제거)'));
    wrap.appendChild(foot);
  };

  window.renderInsight.destroy = destroyCharts;
})();
