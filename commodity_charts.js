/* commodity_charts.js — 원자재 탭 렌더러 (Chartr 스타일)
 * 전역: window.renderComm(el, data)
 * 의존성 0 (Chart.js는 팔랑크스 빌더가 로드) — 없으면 SVG 스파크라인으로 폴백.
 * data = commodity_fetch.py 산출 commodity.json
 */
(function () {
  'use strict';

  var UP = '#ff5b5b';      // 상승 = 빨강
  var DOWN = '#4c8dff';    // 하락 = 파랑
  var FLAT = '#8b98a9';
  var CSS_ID = 'comm-css';

  /* ---------------------------------------------------------------- style */
  var CSS = [
    '.comm{color:var(--fg,#e6ebf2);font-size:13px}',
    '.comm *{box-sizing:border-box}',
    '.comm-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin:0 0 10px}',
    '.comm-head h2{font-size:16px;margin:0;font-weight:650}',
    '.comm-sub{color:var(--dim,#8b98a9);font-size:11px;font-family:var(--mono,ui-monospace,SFMono-Regular,Menlo,monospace)}',
    '.comm-panel{background:var(--panel,#12161c);border:1px solid var(--line,#232a34);border-radius:10px;padding:12px;margin:0 0 14px}',
    '.comm-panel h3{font-size:13px;margin:0 0 8px;font-weight:650}',
    '.comm-panel h3 .comm-note{font-weight:400;color:var(--dim,#8b98a9);font-size:11px;margin-left:6px}',
    '.comm-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 10px}',
    '.comm-tabs{display:flex;gap:4px;flex-wrap:wrap}',
    '.comm-tab{border:1px solid var(--line,#232a34);background:transparent;color:var(--dim,#8b98a9);border-radius:999px;padding:4px 11px;font-size:12px;cursor:pointer;line-height:1.5}',
    '.comm-tab:hover{color:var(--fg,#e6ebf2)}',
    '.comm-tab.on{background:var(--fg,#e6ebf2);color:var(--panel,#12161c);border-color:var(--fg,#e6ebf2);font-weight:600}',
    '.comm-search{margin-left:auto;background:var(--panel,#12161c);border:1px solid var(--line,#232a34);color:var(--fg,#e6ebf2);border-radius:999px;padding:5px 12px;font-size:12px;min-width:190px;outline:none}',
    '.comm-search:focus{border-color:var(--dim,#8b98a9)}',
    '.comm-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}',
    '.comm-card{background:var(--panel,#12161c);border:1px solid var(--line,#232a34);border-radius:10px;padding:10px 12px 8px;min-height:196px}',
    '.comm-card .ct{display:flex;align-items:flex-start;gap:8px}',
    '.comm-card .nm{font-size:12.5px;font-weight:600;line-height:1.3}',
    '.comm-card .id{font-size:10px;color:var(--dim,#8b98a9);font-family:var(--mono,ui-monospace,Menlo,monospace);margin-top:2px}',
    '.comm-card .rt{margin-left:auto;text-align:right;white-space:nowrap}',
    '.comm-card .vv{font-size:14px;font-weight:700;font-family:var(--mono,ui-monospace,Menlo,monospace)}',
    '.comm-badge{display:inline-block;font-size:10.5px;font-weight:700;border-radius:5px;padding:1px 5px;margin-top:3px;font-family:var(--mono,ui-monospace,Menlo,monospace)}',
    '.comm-cv{position:relative;height:118px;margin:6px 0 2px}',
    '.comm-chips{display:flex;gap:3px}',
    '.comm-chip{border:1px solid var(--line,#232a34);background:transparent;color:var(--dim,#8b98a9);border-radius:5px;padding:1px 6px;font-size:10px;cursor:pointer;font-family:var(--mono,ui-monospace,Menlo,monospace)}',
    '.comm-chip.on{color:var(--fg,#e6ebf2);border-color:var(--dim,#8b98a9)}',
    '.comm-foot{display:flex;align-items:center;gap:8px;color:var(--dim,#8b98a9);font-size:10px;font-family:var(--mono,ui-monospace,Menlo,monospace)}',
    '.comm-foot .sp{margin-left:auto}',
    '.comm-pair{background:var(--panel,#12161c);border:1px solid var(--line,#232a34);border-radius:10px;padding:12px}',
    '.comm-pair .pv{position:relative;height:230px;margin-top:6px}',
    '.comm-pairs{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:12px}',
    '.comm-lg{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:var(--dim,#8b98a9);margin-top:4px}',
    '.comm-lg i{display:inline-block;width:9px;height:2px;vertical-align:middle;margin-right:5px}',
    '.comm-tbl-wrap{max-height:340px;overflow:auto}',
    '.comm-tbl{width:100%;border-collapse:collapse;font-size:11.5px}',
    '.comm-tbl th{position:sticky;top:0;background:var(--panel,#12161c);text-align:right;color:var(--dim,#8b98a9);font-weight:600;padding:5px 7px;border-bottom:1px solid var(--line,#232a34);cursor:pointer;white-space:nowrap;z-index:1}',
    '.comm-tbl th.l,.comm-tbl td.l{text-align:left}',
    '.comm-tbl th.on{color:var(--fg,#e6ebf2)}',
    '.comm-tbl td{padding:4px 7px;border-bottom:1px solid var(--line,#232a34);text-align:right;font-family:var(--mono,ui-monospace,Menlo,monospace);white-space:nowrap}',
    '.comm-tbl td.l{font-family:inherit;max-width:280px;overflow:hidden;text-overflow:ellipsis}',
    '.comm-tbl tr:hover td{background:rgba(255,255,255,.03)}',
    '.comm-tbl .cat{color:var(--dim,#8b98a9);font-size:10px}',
    '.comm-more{display:block;margin:12px auto 0;border:1px solid var(--line,#232a34);background:transparent;color:var(--dim,#8b98a9);border-radius:8px;padding:6px 18px;font-size:12px;cursor:pointer}',
    '.comm-more:hover{color:var(--fg,#e6ebf2)}',
    '.comm-empty{color:var(--dim,#8b98a9);padding:18px;text-align:center}'
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

  function keysOf(s) {
    if (s._k) return s._k;
    var k = Object.keys(s.m || {});
    k.sort();
    s._k = k;
    return k;
  }

  function shiftMonth(key, n) {
    var y = +key.slice(0, 4), m = +key.slice(5, 7) + n;
    y += Math.floor((m - 1) / 12);
    m = ((m - 1) % 12 + 12) % 12 + 1;
    return y + '-' + (m < 10 ? '0' + m : '' + m);
  }

  /* 기준월 이하의 가장 가까운 관측치(월 결측 대비, 최대 3개월 소급) */
  function valAt(s, key) {
    for (var i = 0; i < 4; i++) {
      var k = shiftMonth(key, -i);
      if (s.m[k] != null) return s.m[k];
    }
    return null;
  }

  function pct(a, b) {
    if (a == null || b == null || a === 0) return null;
    return (b / a - 1) * 100;
  }

  function chg(s, months) {
    var ks = keysOf(s);
    if (!ks.length) return null;
    var last = ks[ks.length - 1];
    return pct(valAt(s, shiftMonth(last, -months)), s.m[last]);
  }

  function num(v) {
    var a = Math.abs(v);
    if (a >= 10000) return Math.round(v).toLocaleString('en-US');
    if (a >= 1000) return v.toFixed(0);
    if (a >= 100) return v.toFixed(1);
    if (a >= 10) return v.toFixed(2);
    if (a >= 1) return v.toFixed(2);
    if (a >= 0.01) return v.toFixed(3);
    return v.toPrecision(3);
  }

  function fmtVal(v, unit) {
    if (v == null) return '—';
    var u = unit || '';
    if (u.charAt(0) === '$') return '$' + num(v) + u.slice(1);
    if (u.charAt(0) === '¢') return num(v) + '¢' + u.slice(1);
    if (!u || u.indexOf('idx') === 0) return num(v);
    return num(v) + ' ' + u;
  }

  function fmtPct(p, dp) {
    if (p == null || !isFinite(p)) return '—';
    return (p >= 0 ? '+' : '') + p.toFixed(dp == null ? 1 : dp) + '%';
  }

  function pctColor(p) {
    if (p == null || !isFinite(p)) return FLAT;
    if (p > 0.05) return UP;
    if (p < -0.05) return DOWN;
    return FLAT;
  }

  function heatBG(p, span) {
    if (p == null || !isFinite(p) || Math.abs(p) < 0.05) return '';
    var a = Math.min(0.42, Math.abs(p) / span * 0.42 + 0.05);
    return p > 0 ? 'rgba(255,91,91,' + a.toFixed(3) + ')'
                 : 'rgba(76,141,255,' + a.toFixed(3) + ')';
  }

  function ymLabel(k) {  // '2026-01' → "Jan '26"
    var MN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return MN[(+k.slice(5, 7)) - 1] + " '" + k.slice(2, 4);
  }

  function rangeKeys(s, years) {
    var ks = keysOf(s);
    if (!years || !ks.length) return ks;
    var cut = shiftMonth(ks[ks.length - 1], -12 * years);
    var out = [];
    for (var i = 0; i < ks.length; i++) if (ks[i] >= cut) out.push(ks[i]);
    return out.length > 1 ? out : ks;
  }

  function hasChart() {
    return typeof window !== 'undefined' && typeof window.Chart === 'function';
  }

  function cssVar(name, fb) {
    try {
      var v = getComputedStyle(document.documentElement).getPropertyValue(name);
      return (v && v.trim()) || fb;
    } catch (e) { return fb; }
  }

  /* ------------------------------------------------- 끝점 라벨 그리기 플러그인 */
  function drawEndLabel(ctx, x, y, text, color, area) {
    ctx.save();
    ctx.font = '700 11px ' + cssVar('--mono', 'ui-monospace, Menlo, monospace');
    var w = ctx.measureText(text).width + 10, h = 16;
    var lx = x + 7, ly = Math.max(area.top + h / 2, Math.min(area.bottom - h / 2, y));
    if (lx + w > area.right + 52) lx = x - 7 - w;
    ctx.fillStyle = color;
    if (ctx.roundRect) {
      ctx.beginPath();
      ctx.roundRect(lx, ly - h / 2, w, h, 4);
      ctx.fill();
    } else {
      ctx.fillRect(lx, ly - h / 2, w, h);
    }
    ctx.fillStyle = '#0b0e12';
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    ctx.fillText(text, lx + 5, ly + 0.5);
    ctx.beginPath();
    ctx.arc(x, y, 3.1, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = cssVar('--panel', '#12161c');
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.restore();
  }

  var endLabelPlugin = {
    id: 'commEndLabel',
    afterDatasetsDraw: function (chart) {
      var ctx = chart.ctx, area = chart.chartArea;
      if (!area) return;
      chart.data.datasets.forEach(function (ds, di) {
        if (ds.commLabel === false) return;
        var meta = chart.getDatasetMeta(di);
        if (meta.hidden || !meta.data || !meta.data.length) return;
        var pt = null, i;
        for (i = meta.data.length - 1; i >= 0; i--) {
          if (ds.data[i] != null) { pt = meta.data[i]; break; }
        }
        if (!pt) return;
        drawEndLabel(ctx, pt.x, pt.y, ds.commText || '', ds.borderColor, area);
      });
    }
  };

  /* 페어차트 변화율 주석(예: +29% Jan-Dec '25) */
  var annPlugin = {
    id: 'commAnn',
    afterDatasetsDraw: function (chart) {
      var anns = chart.options.plugins && chart.options.plugins.commAnn &&
                 chart.options.plugins.commAnn.items;
      if (!anns || !anns.length || !chart.chartArea) return;
      var ctx = chart.ctx, area = chart.chartArea;
      anns.forEach(function (a) {
        var meta = chart.getDatasetMeta(a.ds);
        if (!meta || !meta.data || !meta.data[a.i0] || !meta.data[a.i1]) return;
        var p0 = meta.data[a.i0], p1 = meta.data[a.i1];
        var y = Math.min(p0.y, p1.y) - 20;
        y = Math.max(area.top + 12, y);
        ctx.save();
        ctx.strokeStyle = a.color;
        ctx.fillStyle = a.color;
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(p0.x, y); ctx.lineTo(p1.x, y);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.beginPath();  // 화살촉
        var d = p1.x >= p0.x ? 1 : -1;
        ctx.moveTo(p1.x, y); ctx.lineTo(p1.x - 5 * d, y - 3.2);
        ctx.lineTo(p1.x - 5 * d, y + 3.2); ctx.closePath(); ctx.fill();
        ctx.beginPath();
        ctx.moveTo(p0.x, y - 3.5); ctx.lineTo(p0.x, y + 3.5); ctx.stroke();
        ctx.font = '700 10.5px ' + cssVar('--mono', 'ui-monospace, Menlo, monospace');
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        var mx = (p0.x + p1.x) / 2, tw = ctx.measureText(a.text).width;
        mx = Math.max(area.left + tw / 2, Math.min(area.right - tw / 2, mx));
        ctx.fillText(a.text, mx, y - 3);
        ctx.restore();
      });
    }
  };

  var pluginsReady = false;
  function ensurePlugins() {
    if (pluginsReady || !hasChart()) return;
    try {
      window.Chart.register(endLabelPlugin, annPlugin);
    } catch (e) { /* v2 등 register 없음 — 폴백 */ }
    pluginsReady = true;
  }

  /* --------------------------------------------------------------- charts */
  function baseOptions(opt) {
    var line = cssVar('--line', '#232a34'), dim = cssVar('--dim', '#8b98a9');
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      layout: { padding: { right: opt.padRight || 56, top: opt.padTop || 8, left: 2, bottom: 0 } },
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          grid: { display: false, drawBorder: false },
          border: { display: false },
          ticks: {
            color: dim, font: { size: 9 }, maxRotation: 0, autoSkip: true,
            maxTicksLimit: opt.xTicks || 4,
            callback: function (v, i, ticks) {
              var l = this.getLabelForValue(v);
              return typeof l === 'string' ? ymLabel(l) : l;
            }
          }
        },
        y: {
          position: 'right',
          grid: { color: line, drawBorder: false, drawTicks: false },
          border: { display: false },
          ticks: {
            color: dim, font: { size: 9 }, maxTicksLimit: opt.yTicks || 4,
            padding: 4,
            callback: function (v) { return num(v); }
          }
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: cssVar('--panel', '#12161c'),
          borderColor: line, borderWidth: 1,
          titleColor: dim, bodyColor: cssVar('--fg', '#e6ebf2'),
          titleFont: { size: 10 }, bodyFont: { size: 11 },
          displayColors: true, padding: 8,
          callbacks: {
            title: function (its) { return its.length ? ymLabel(its[0].label) : ''; },
            label: function (it) {
              var u = (it.dataset.commUnit) || '';
              return ' ' + it.dataset.label + '  ' + fmtVal(it.parsed.y, u);
            }
          }
        }
      }
    };
  }

  function sparkFallback(node, ks, vals, color) {
    // Chart.js 부재 시 SVG 스파크라인
    var w = node.clientWidth || 300, h = node.clientHeight || 110;
    var mn = Infinity, mx = -Infinity, i;
    for (i = 0; i < vals.length; i++) {
      if (vals[i] == null) continue;
      if (vals[i] < mn) mn = vals[i];
      if (vals[i] > mx) mx = vals[i];
    }
    if (!isFinite(mn)) return;
    var rng = (mx - mn) || 1, d = '', pw = w - 58;
    for (i = 0; i < vals.length; i++) {
      if (vals[i] == null) continue;
      var x = 2 + (i / Math.max(1, vals.length - 1)) * pw;
      var y = h - 12 - ((vals[i] - mn) / rng) * (h - 26);
      d += (d ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
    }
    var NS = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', h);
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    var p = document.createElementNS(NS, 'path');
    p.setAttribute('d', d);
    p.setAttribute('fill', 'none');
    p.setAttribute('stroke', color);
    p.setAttribute('stroke-width', '1.6');
    svg.appendChild(p);
    node.appendChild(svg);
  }

  function makeLineChart(canvas, ks, sets, opt) {
    ensurePlugins();
    if (!hasChart()) {
      sparkFallback(canvas.parentNode, ks, sets[0].data, sets[0].color);
      canvas.style.display = 'none';
      return null;
    }
    var ds = sets.map(function (s) {
      return {
        label: s.label,
        data: s.data,
        borderColor: s.color,
        backgroundColor: s.fill || 'transparent',
        fill: !!s.fill,
        borderWidth: s.width || 1.7,
        pointRadius: 0,
        pointHoverRadius: 3,
        pointHoverBackgroundColor: s.color,
        tension: 0.22,
        spanGaps: true,
        commText: s.endText,
        commUnit: s.unit,
        commLabel: s.endText !== undefined
      };
    });
    var o = baseOptions(opt || {});
    if (opt && opt.ann) o.plugins.commAnn = { items: opt.ann };
    if (opt && opt.y2) {
      o.scales.y1 = {
        position: 'left',
        grid: { display: false, drawBorder: false },
        border: { display: false },
        ticks: { color: sets[1].color, font: { size: 9 }, maxTicksLimit: 4,
                 callback: function (v) { return num(v); } }
      };
      ds[1].yAxisID = 'y1';
    }
    return new window.Chart(canvas.getContext('2d'), { type: 'line', data: { labels: ks, datasets: ds }, options: o });
  }

  /* ----------------------------------------------------------- 시리즈 카드 */
  function seriesCard(sid, s, catLabel) {
    var card = el('div', 'comm-card');
    var top = el('div', 'ct');
    var lt = el('div');
    lt.appendChild(el('div', 'nm', s.name));
    lt.appendChild(el('div', 'id', sid + ' · ' + catLabel));
    top.appendChild(lt);

    var ks = keysOf(s);
    var last = ks[ks.length - 1];
    var lastV = last != null ? s.m[last] : null;
    var yoy = chg(s, 12);

    var rt = el('div', 'rt');
    var vv = el('div', 'vv', fmtVal(lastV, s.unit));
    rt.appendChild(vv);
    var bd = el('span', 'comm-badge', 'YoY ' + fmtPct(yoy));
    bd.style.color = pctColor(yoy);
    bd.style.background = heatBG(yoy, 60) || 'transparent';
    rt.appendChild(bd);
    top.appendChild(rt);
    card.appendChild(top);

    var cv = el('div', 'comm-cv');
    var canvas = el('canvas');
    cv.appendChild(canvas);
    card.appendChild(cv);

    var foot = el('div', 'comm-foot');
    var wt = (last || '');
    if (s.native_freq && s.native_freq !== 'M') {
      wt += ' · ' + s.native_freq + '→M avg';
      if (s.last_native) {
        wt += ' · 최신 ' + s.last_native.d + ' ' + fmtVal(s.last_native.v, s.unit);
      }
    }
    foot.appendChild(el('span', null, wt));
    var chips = el('div', 'comm-chips sp');
    foot.appendChild(chips);
    card.appendChild(foot);

    var chart = null;
    var built = false;
    function draw(years, btn) {
      var kk = rangeKeys(s, years);
      var data = kk.map(function (k) { return s.m[k] == null ? null : s.m[k]; });
      var first = null, i;
      for (i = 0; i < data.length; i++) if (data[i] != null) { first = data[i]; break; }
      var lv = data[data.length - 1];
      var col = pctColor(pct(first, lv));
      if (chart) { chart.destroy(); chart = null; }
      cv.innerHTML = '';
      canvas = el('canvas');
      cv.appendChild(canvas);
      chart = makeLineChart(canvas, kk, [{
        label: s.name, data: data, color: col, unit: s.unit,
        endText: fmtVal(lv, s.unit)
      }], { padRight: 62, xTicks: 3, yTicks: 3 });
      Array.prototype.forEach.call(chips.children, function (c) { c.classList.remove('on'); });
      if (btn) btn.classList.add('on');
    }

    [['1Y', 1], ['3Y', 3], ['5Y', 5], ['ALL', 0]].forEach(function (r, i) {
      var b = el('button', 'comm-chip' + (i === 2 ? ' on' : ''), r[0]);
      b.type = 'button';
      b.addEventListener('click', function () { draw(r[1], b); });
      chips.appendChild(b);
    });

    card._build = function () {
      if (built) return;
      built = true;
      draw(5, chips.children[2]);
    };
    return card;
  }

  /* ------------------------------------------------------------- 페어 차트 */
  function pairCard(p, byid) {
    var us = byid[p.us_retail], gl = byid[p['global']];
    if (!us || !gl) return null;
    var box = el('div', 'comm-pair');
    var h = el('h3', null, p.label + ' — 미국 소매가 vs 글로벌 원자재');
    h.appendChild(el('span', 'comm-note', p.note || ''));
    box.appendChild(h);

    var usS = p.us_scale || 1, glS = p.global_scale || 1;
    var same = !!p.same_axis;

    // 공통 기간(최근 10년) — 두 시리즈 모두 값이 있는 월
    var ka = keysOf(us), kb = keysOf(gl);
    if (!ka.length || !kb.length) return null;
    var lastK = ka[ka.length - 1] < kb[kb.length - 1] ? ka[ka.length - 1] : kb[kb.length - 1];
    var cut = shiftMonth(lastK, -120);
    var ks = [];
    for (var i = 0; i < ka.length; i++) {
      if (ka[i] >= cut && ka[i] <= lastK) ks.push(ka[i]);
    }
    if (ks.length < 6) return null;

    var du = ks.map(function (k) { return us.m[k] == null ? null : us.m[k] * usS; });
    var dg = ks.map(function (k) { return gl.m[k] == null ? null : gl.m[k] * glS; });

    // 지정 구간 변화율 주석: 최근 완결 연도(Jan→Dec), 없으면 최근 12M
    function findIdx(key) { return ks.indexOf(key); }
    var anns = [];
    var yr = +lastK.slice(0, 4);
    var y0 = (lastK.slice(5, 7) === '12') ? yr : yr - 1;
    var a0 = findIdx(y0 + '-01'), a1 = findIdx(y0 + '-12');
    var spanTxt = "Jan-Dec '" + String(y0).slice(2);
    if (a0 < 0 || a1 < 0) {
      a1 = ks.length - 1;
      a0 = Math.max(0, a1 - 12);
      spanTxt = ymLabel(ks[a0]) + '-' + ymLabel(ks[a1]);
    }
    [[0, du, UP], [1, dg, '#f0b429']].forEach(function (t) {
      var d = t[1];
      if (d[a0] == null || d[a1] == null) return;
      var c = pct(d[a0], d[a1]);
      if (c == null) return;
      anns.push({ ds: t[0], i0: a0, i1: a1, color: t[2],
                  text: fmtPct(c, 0) + ' ' + spanTxt });
    });

    var cv = el('div', 'pv');
    var canvas = el('canvas');
    cv.appendChild(canvas);
    box.appendChild(cv);

    var uUnit = same ? (p.unit || '$/lb') : (p.us_unit || us.unit);
    var gUnit = same ? (p.unit || '$/lb') : (p.global_unit || gl.unit);
    var lg = el('div', 'comm-lg');
    [[UP, '美 소매 · ' + us.name + ' (' + uUnit + ')'],
     ['#f0b429', '글로벌 · ' + gl.name + ' (' + gUnit + ')']].forEach(function (t) {
      var s = el('span', null, '');
      var ic = el('i');
      ic.style.background = t[0];
      s.appendChild(ic);
      s.appendChild(document.createTextNode(t[1]));
      lg.appendChild(s);
    });
    box.appendChild(lg);

    box._build = function () {
      if (box._done) return;
      box._done = true;
      makeLineChart(canvas, ks, [
        { label: '美 소매', data: du, color: UP, unit: uUnit, width: 2,
          endText: fmtVal(du[du.length - 1], uUnit) },
        { label: '글로벌', data: dg, color: '#f0b429', unit: gUnit, width: 2,
          endText: fmtVal(dg[dg.length - 1], gUnit) }
      ], { padRight: 74, padTop: 26, xTicks: 6, yTicks: 5, ann: anns, y2: !same });
    };
    return box;
  }

  /* ------------------------------------------------------- 랭킹/히트맵 표 */
  function rankTable(rows) {
    var wrap = el('div', 'comm-tbl-wrap');
    var tbl = el('table', 'comm-tbl');
    var thead = el('thead'), tr = el('tr');
    var cols = [
      { k: 'name', t: '시리즈', l: true },
      { k: 'last', t: '최신값' },
      { k: 'c1', t: '1M' },
      { k: 'c3', t: '3M' },
      { k: 'c12', t: '12M' }
    ];
    var sortKey = 'c12', desc = true;
    cols.forEach(function (c) {
      var th = el('th', c.l ? 'l' : '', c.t);
      th.dataset.k = c.k;
      th.addEventListener('click', function () {
        if (sortKey === c.k) desc = !desc; else { sortKey = c.k; desc = true; }
        render();
      });
      tr.appendChild(th);
    });
    thead.appendChild(tr);
    tbl.appendChild(thead);
    var tb = el('tbody');
    tbl.appendChild(tb);
    wrap.appendChild(tbl);

    function render() {
      Array.prototype.forEach.call(thead.querySelectorAll('th'), function (th) {
        th.classList.toggle('on', th.dataset.k === sortKey);
        var base = cols.filter(function (c) { return c.k === th.dataset.k; })[0].t;
        th.textContent = th.dataset.k === sortKey ? base + (desc ? ' ▼' : ' ▲') : base;
      });
      var rs = rows.slice();
      rs.sort(function (a, b) {
        var x = a[sortKey], y = b[sortKey];
        if (typeof x === 'string') return desc ? (y < x ? -1 : 1) : (x < y ? -1 : 1);
        if (x == null || !isFinite(x)) return 1;
        if (y == null || !isFinite(y)) return -1;
        return desc ? y - x : x - y;
      });
      tb.innerHTML = '';
      rs.forEach(function (r) {
        var t = el('tr');
        var td0 = el('td', 'l');
        td0.appendChild(document.createTextNode(r.name + ' '));
        td0.appendChild(el('span', 'cat', r.cat));
        t.appendChild(td0);
        t.appendChild(el('td', null, fmtVal(r.last, r.unit)));
        [r.c1, r.c3, r.c12].forEach(function (v, i) {
          var td = el('td', null, fmtPct(v));
          td.style.color = pctColor(v);
          td.style.background = heatBG(v, [12, 25, 45][i]);
          t.appendChild(td);
        });
        tb.appendChild(t);
      });
    }
    render();
    return wrap;
  }

  /* -------------------------------------------------------------- 렌더 본체 */
  window.renderComm = function renderComm(root, data) {
    if (!root) return;
    injectCSS(root.ownerDocument || document);
    root.innerHTML = '';
    root.classList.add('comm');
    if (!data || !data.cats) {
      root.appendChild(el('div', 'comm-empty', 'commodity.json 로드 실패'));
      return;
    }

    var cats = data.cats, meta = data._meta || {};
    var catKeys = Object.keys(cats);
    var byid = {}, rows = [], all = [];
    catKeys.forEach(function (ck) {
      var c = cats[ck];
      Object.keys(c.series).forEach(function (sid) {
        var s = c.series[sid];
        byid[sid] = s;
        var ks = keysOf(s);
        if (!ks.length) return;
        var item = { sid: sid, s: s, cat: ck, catLabel: c.label,
                     q: (sid + ' ' + s.name + ' ' + (s.src_title || '')).toLowerCase() };
        all.push(item);
      });
    });

    // 최신성 판정: 전체 최신월 기준 6개월 이내만 랭킹에 포함
    var maxK = '';
    all.forEach(function (it) {
      var ks = keysOf(it.s);
      var l = ks[ks.length - 1];
      if (l > maxK) maxK = l;
    });
    var freshCut = shiftMonth(maxK, -6);
    all.forEach(function (it) {
      var ks = keysOf(it.s), l = ks[ks.length - 1];
      it.fresh = l >= freshCut;
      if (!it.fresh) return;
      rows.push({
        name: it.s.name, cat: it.catLabel, unit: it.s.unit, last: it.s.m[l],
        c1: chg(it.s, 1), c3: chg(it.s, 3), c12: chg(it.s, 12)
      });
    });

    /* head */
    var head = el('div', 'comm-head');
    head.appendChild(el('h2', null, '원자재 · 소매가 (FRED)'));
    head.appendChild(el('div', 'comm-sub',
      'series=' + all.length + ' · cats=' + catKeys.length +
      ' · pairs=' + ((data.pairs || []).length) +
      ' · 최신 ' + maxK + ' · fetched ' + (meta.fetched || '').slice(0, 10)));
    root.appendChild(head);

    /* 1) 랭킹/히트맵 */
    var rp = el('div', 'comm-panel');
    var rh = el('h3', null, '변화율 랭킹');
    rh.appendChild(el('span', 'comm-note',
      '상승 빨강 · 하락 파랑 / 헤더 클릭 정렬 · 최신 6개월 내 갱신분 ' + rows.length + '개'));
    rp.appendChild(rh);
    rp.appendChild(rankTable(rows));
    root.appendChild(rp);

    /* 2) 페어 차트 */
    var pairs = data.pairs || [];
    if (pairs.length) {
      var pp = el('div', 'comm-panel');
      var ph = el('h3', null, '미국 소매가 vs 글로벌 원자재');
      ph.appendChild(el('span', 'comm-note', '각 선 끝 값 라벨 · 구간 변화율 주석'));
      pp.appendChild(ph);
      var pg = el('div', 'comm-pairs');
      var pcards = [];
      pairs.forEach(function (p) {
        var c = pairCard(p, byid);
        if (c) { pg.appendChild(c); pcards.push(c); }
      });
      pp.appendChild(pg);
      root.appendChild(pp);
      pcards.forEach(function (c) { observe(c); });
    }

    /* 3) 카테고리 탭 + 검색 + 카드 그리드 */
    var bar = el('div', 'comm-bar');
    var tabs = el('div', 'comm-tabs');
    bar.appendChild(tabs);
    var search = el('input', 'comm-search');
    search.type = 'search';
    search.placeholder = '검색 (품목·FRED ID)';
    bar.appendChild(search);
    root.appendChild(bar);

    var grid = el('div', 'comm-grid');
    root.appendChild(grid);
    var moreBtn = el('button', 'comm-more', '더 보기');
    moreBtn.type = 'button';
    root.appendChild(moreBtn);

    var curCat = catKeys[0], shown = 0, PAGE = 24, list = [];
    catKeys.forEach(function (ck, i) {
      var b = el('button', 'comm-tab' + (i === 0 ? ' on' : ''),
                 cats[ck].label + ' ' + Object.keys(cats[ck].series).length);
      b.type = 'button';
      b.addEventListener('click', function () {
        curCat = ck;
        Array.prototype.forEach.call(tabs.children, function (t) { t.classList.remove('on'); });
        b.classList.add('on');
        rebuild();
      });
      tabs.appendChild(b);
    });

    function filtered() {
      var q = search.value.trim().toLowerCase();
      return all.filter(function (it) {
        if (q) return it.q.indexOf(q) >= 0;
        return it.cat === curCat;
      }).sort(function (a, b) {
        if (a.fresh !== b.fresh) return a.fresh ? -1 : 1;
        return a.s.name < b.s.name ? -1 : 1;
      });
    }

    function page() {
      var slice = list.slice(shown, shown + PAGE);
      slice.forEach(function (it) {
        var c = seriesCard(it.sid, it.s, it.catLabel);
        grid.appendChild(c);
        observe(c);
      });
      shown += slice.length;
      moreBtn.style.display = shown < list.length ? '' : 'none';
      moreBtn.textContent = '더 보기 (' + shown + '/' + list.length + ')';
    }

    function rebuild() {
      grid.innerHTML = '';
      shown = 0;
      list = filtered();
      if (!list.length) {
        grid.appendChild(el('div', 'comm-empty', '해당 시리즈 없음'));
        moreBtn.style.display = 'none';
        return;
      }
      page();
    }

    moreBtn.addEventListener('click', page);
    var tmr = null;
    search.addEventListener('input', function () {
      if (tmr) clearTimeout(tmr);
      tmr = setTimeout(rebuild, 160);
    });
    rebuild();
  };

  /* 화면에 들어올 때만 차트 생성 (수백 개 시리즈 대비) */
  var io = null;
  function observe(node) {
    if (!node || !node._build) return;
    if (typeof IntersectionObserver === 'undefined') { node._build(); return; }
    if (!io) {
      io = new IntersectionObserver(function (ents) {
        ents.forEach(function (e) {
          if (e.isIntersecting) {
            io.unobserve(e.target);
            if (e.target._build) e.target._build();
          }
        });
      }, { rootMargin: '160px 0px' });
    }
    io.observe(node);
  }
})();
