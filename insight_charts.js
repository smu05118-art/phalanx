/*
 * insight_charts.js — 💡 인사이트 레이어 렌더러
 *
 *   window.renderInsight(el, data, quotes)
 *     el     : 마운트할 DOM 엘리먼트(또는 CSS 셀렉터 문자열)
 *     data   : insights.json 파싱 객체  (또는 {insights, quotes} 래퍼)
 *     quotes : quotes.json 파싱 객체(선택). 생략 시 data.quotes / window.INSIGHT_QUOTES 탐색
 *
 * 설계 메모
 *  · 의존성 0 — 스파크라인은 인라인 SVG로 직접 그린다. Chart.js가 있으면 써도 되지만 없어도 항상 렌더.
 *  · 상단   : 오늘의 종합 판독(교차확인 상위 3) + 유형별 카드 수.
 *  · 중단   : 카드 그리드. 유형색 = 교차확인 초록 / 모순 주황 / 임계근접 빨강 / 컨센갭 파랑.
 *             각 카드에 근거 수치 칩 · 미니 스파크라인 · 신뢰도 배지 · 연결고리.
 *  · 하단   : 인용 갤러리. 태그 필터 · 출처 링크 · 연결 지표 배지.
 *  · 빌더·panoptes·app.js는 건드리지 않는다. 전역 함수 하나만 노출.
 *  · 근거 수치는 전부 insights.json / quotes.json 실측값. 렌더러는 창작하지 않는다.
 */
(function () {
  'use strict';

  var C = {
    bg: '#0b0f14', panel: '#121a22', panel2: '#0e141b', head: '#0f1620',
    border: '#1e2833', line: '#26333f', text: '#c9d4df', sub: '#9aa8b6',
    muted: '#7b8a99', dim: '#55636f', chip: '#16212c', chipBorder: '#243342',
    good: '#3fb57a', warn: '#e8913c', bad: '#e0574e', info: '#4d8fd6', gold: '#d9a441'
  };

  var TYPE = {
    cross_confirm: { ko: '교차확인', color: C.good, wash: 'rgba(63,181,122,.10)' },
    contradiction: { ko: '모순', color: C.warn, wash: 'rgba(232,145,60,.10)' },
    threshold: { ko: '임계근접', color: C.bad, wash: 'rgba(224,87,78,.10)' },
    consensus_gap: { ko: '컨센갭', color: C.info, wash: 'rgba(77,143,214,.10)' }
  };
  var TYPE_ORDER = ['cross_confirm', 'contradiction', 'threshold', 'consensus_gap'];

  // ---------------------------------------------------------------- utils
  var SVGNS = 'http://www.w3.org/2000/svg';

  function h(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (!Object.prototype.hasOwnProperty.call(attrs, k)) { continue; }
        var v = attrs[k];
        if (v == null) { continue; }
        if (k === 'class') { e.className = v; }
        else if (k === 'text') { e.textContent = v; }
        else if (k === 'html') { e.innerHTML = v; }
        else if (k === 'style') { e.setAttribute('style', v); }
        else if (k.slice(0, 2) === 'on' && typeof v === 'function') {
          e.addEventListener(k.slice(2).toLowerCase(), v);
        } else { e.setAttribute(k, v); }
      }
    }
    kids = kids || [];
    for (var i = 0; i < kids.length; i++) {
      var c = kids[i];
      if (c == null || c === false) { continue; }
      e.appendChild(typeof c === 'object' ? c : document.createTextNode(String(c)));
    }
    return e;
  }

  function fnum(x) {
    if (x == null || (typeof x === 'number' && !isFinite(x))) { return '—'; }
    if (typeof x !== 'number') { return String(x); }
    var a = Math.abs(x);
    var d = a >= 100 ? 0 : (a >= 10 ? 1 : 2);
    var s = x.toFixed(d);
    return s.replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1');
  }

  function chipText(e) {
    // 근거 evidence -> "라벨 · 값 단위"
    var val = e.value != null ? fnum(e.value) + (e.unit ? '' + e.unit : '') : null;
    return e.label + (val != null ? '  ' + val : '');
  }

  function resolve(data, quotes) {
    var ins = data;
    if (typeof ins === 'string') { try { ins = JSON.parse(ins); } catch (err) { ins = {}; } }
    if (ins && ins.insights) { quotes = quotes || ins.quotes; ins = ins.insights; }
    if (!ins) {
      ins = (typeof window !== 'undefined' && (window.INSIGHTS_DATA || window.__INSIGHTS__)) || {};
    }
    var q = quotes;
    if (typeof q === 'string') { try { q = JSON.parse(q); } catch (err2) { q = null; } }
    if (!q) {
      q = (ins && ins.quotes) ||
          (typeof window !== 'undefined' && (window.INSIGHT_QUOTES || window.QUOTES_DATA || window.__QUOTES__)) ||
          { quotes: [] };
    }
    var arr = Array.isArray(q) ? q : (q.quotes || []);
    return { ins: ins, quotes: arr };
  }

  // ---------------------------------------------------------------- style
  function injectStyle(root) {
    if (document.getElementById('jem-insight-style')) { return; }
    var css = [
      '.jemi{background:' + C.bg + ';color:' + C.text + ';font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;padding:18px;box-sizing:border-box}',
      '.jemi *{box-sizing:border-box}',
      '.jemi h2{font-size:18px;margin:0 0 2px;color:#eef3f8;font-weight:700}',
      '.jemi h3{font-size:13px;margin:22px 0 10px;color:' + C.sub + ';font-weight:600;letter-spacing:.02em;text-transform:uppercase}',
      '.jemi a{color:' + C.info + ';text-decoration:none}',
      '.jemi a:hover{text-decoration:underline}',
      '.jemi-sub{color:' + C.muted + ';font-size:12px;margin:0 0 14px}',
      '.jemi-top{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-bottom:6px}',
      '.jemi-hero{background:linear-gradient(180deg,' + C.panel + ',' + C.panel2 + ');border:1px solid ' + C.border + ';border-left:3px solid ' + C.good + ';border-radius:10px;padding:13px 14px}',
      '.jemi-hero .rk{font-size:11px;color:' + C.good + ';font-weight:700;letter-spacing:.04em}',
      '.jemi-hero .tt{font-size:14px;font-weight:700;color:#eaf1f7;margin:3px 0 5px}',
      '.jemi-hero .vd{font-size:12.5px;color:' + C.sub + '}',
      '.jemi-counts{display:flex;flex-wrap:wrap;gap:8px;margin:2px 0 4px}',
      '.jemi-count{font-size:12px;padding:4px 10px;border-radius:999px;border:1px solid ' + C.chipBorder + ';background:' + C.chip + ';color:' + C.sub + '}',
      '.jemi-filters{display:flex;flex-wrap:wrap;gap:7px;margin:6px 0 4px}',
      '.jemi-fbtn{cursor:pointer;user-select:none;font-size:12px;padding:5px 12px;border-radius:999px;border:1px solid ' + C.chipBorder + ';background:' + C.chip + ';color:' + C.sub + ';transition:.12s}',
      '.jemi-fbtn.on{color:#0b0f14;font-weight:700}',
      '.jemi-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:13px}',
      '.jemi-card{background:' + C.panel + ';border:1px solid ' + C.border + ';border-left:3px solid ' + C.muted + ';border-radius:10px;padding:13px 14px;display:flex;flex-direction:column;gap:9px}',
      '.jemi-card .badge{font-size:10.5px;font-weight:700;letter-spacing:.03em;padding:2px 8px;border-radius:6px;display:inline-block}',
      '.jemi-card .ct-h{display:flex;align-items:center;gap:8px;flex-wrap:wrap}',
      '.jemi-card .tt{font-size:14px;font-weight:700;color:#eaf1f7;line-height:1.35}',
      '.jemi-card .vd{font-size:12.5px;color:' + C.sub + '}',
      '.jemi-chips{display:flex;flex-wrap:wrap;gap:6px}',
      '.jemi-chip{font-size:11.5px;padding:3px 8px;border-radius:6px;background:' + C.chip + ';border:1px solid ' + C.chipBorder + ';color:' + C.text + ';white-space:nowrap}',
      '.jemi-chip b{color:#eef3f8}',
      '.jemi-chip .g{color:' + C.muted + ';font-size:10.5px;margin-left:3px}',
      '.jemi-link{font-size:11.5px;color:' + C.muted + ';border-top:1px dashed ' + C.line + ';padding-top:8px;line-height:1.5}',
      '.jemi-conf{font-size:11px;color:' + C.dim + '}',
      '.jemi-conf b{color:' + C.sub + '}',
      '.jemi-spark{margin-top:2px}',
      '.jemi-see{font-size:11px;color:' + C.dim + '}',
      '.jemi-qwrap{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:13px}',
      '.jemi-q{background:' + C.panel2 + ';border:1px solid ' + C.border + ';border-radius:10px;padding:13px 14px;display:flex;flex-direction:column;gap:7px}',
      '.jemi-q .who{font-size:12.5px;font-weight:700;color:#eaf1f7}',
      '.jemi-q .meta{font-size:11px;color:' + C.muted + '}',
      '.jemi-q .orig{font-size:12.5px;color:' + C.text + ';font-style:italic;border-left:2px solid ' + C.line + ';padding-left:9px}',
      '.jemi-q .ko{font-size:12.5px;color:' + C.sub + '}',
      '.jemi-q .sharp{font-size:12px;color:' + C.gold + ';background:rgba(217,164,65,.08);border-radius:6px;padding:6px 9px}',
      '.jemi-q .foot{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:1px}',
      '.jemi-tag{font-size:10.5px;padding:2px 7px;border-radius:999px;background:' + C.chip + ';border:1px solid ' + C.chipBorder + ';color:' + C.muted + '}',
      '.jemi-dl{font-size:10.5px;padding:2px 8px;border-radius:6px;background:rgba(77,143,214,.12);border:1px solid rgba(77,143,214,.35);color:#a9cdf2}',
      '.jemi-src{font-size:11px;margin-left:auto}',
      '.jemi-empty{color:' + C.dim + ';font-size:12px;padding:18px 0}'
    ].join('\n');
    document.head.appendChild(h('style', { id: 'jem-insight-style', text: css }));
  }

  // ---------------------------------------------------------------- sparkline (inline SVG)
  function sparkline(spark, color, w, ht) {
    w = w || 300; ht = ht || 46;
    var vals = (spark && spark.values) || [];
    if (!vals.length) { return null; }
    var pad = 3;
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var refs = [];
    if (spark.threshold != null) { refs.push(spark.threshold); }
    if (spark.baseline != null) { refs.push(spark.baseline); }
    for (var r = 0; r < refs.length; r++) { lo = Math.min(lo, refs[r]); hi = Math.max(hi, refs[r]); }
    if (hi === lo) { hi = lo + 1; }
    var span = hi - lo;
    var X = function (i) { return pad + (w - 2 * pad) * (vals.length < 2 ? 0.5 : i / (vals.length - 1)); };
    var Y = function (v) { return pad + (ht - 2 * pad) * (1 - (v - lo) / span); };

    var svg = document.createElementNS(SVGNS, 'svg');
    svg.setAttribute('width', '100%');
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + ht);
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.setAttribute('class', 'jemi-spark');

    function refLine(v, col, dash) {
      var y = Y(v);
      var ln = document.createElementNS(SVGNS, 'line');
      ln.setAttribute('x1', pad); ln.setAttribute('x2', w - pad);
      ln.setAttribute('y1', y); ln.setAttribute('y2', y);
      ln.setAttribute('stroke', col); ln.setAttribute('stroke-width', '1');
      if (dash) { ln.setAttribute('stroke-dasharray', dash); }
      svg.appendChild(ln);
    }
    if (spark.baseline != null) { refLine(spark.baseline, C.line, null); }
    if (spark.threshold != null) { refLine(spark.threshold, 'rgba(224,87,78,.55)', '4 3'); }

    // area
    var dpts = [];
    for (var i = 0; i < vals.length; i++) { dpts.push(X(i).toFixed(1) + ',' + Y(vals[i]).toFixed(1)); }
    var area = document.createElementNS(SVGNS, 'polygon');
    area.setAttribute('points', X(0).toFixed(1) + ',' + (ht - pad) + ' ' + dpts.join(' ') + ' ' + X(vals.length - 1).toFixed(1) + ',' + (ht - pad));
    area.setAttribute('fill', color); area.setAttribute('opacity', '0.10');
    svg.appendChild(area);

    var pl = document.createElementNS(SVGNS, 'polyline');
    pl.setAttribute('points', dpts.join(' '));
    pl.setAttribute('fill', 'none'); pl.setAttribute('stroke', color);
    pl.setAttribute('stroke-width', '1.6'); pl.setAttribute('stroke-linejoin', 'round');
    pl.setAttribute('vector-effect', 'non-scaling-stroke');
    svg.appendChild(pl);

    var dot = document.createElementNS(SVGNS, 'circle');
    dot.setAttribute('cx', X(vals.length - 1)); dot.setAttribute('cy', Y(vals[vals.length - 1]));
    dot.setAttribute('r', '2.6'); dot.setAttribute('fill', color);
    svg.appendChild(dot);

    var title = document.createElementNS(SVGNS, 'title');
    title.textContent = (spark.label || '') + '  ' + (spark.labels ? spark.labels[0] + '→' + spark.labels[spark.labels.length - 1] : '') +
      '  (' + fnum(vals[0]) + ' → ' + fnum(vals[vals.length - 1]) + ')';
    svg.appendChild(title);
    return svg;
  }

  // ---------------------------------------------------------------- card
  function evidenceChip(e) {
    var kids = [h('b', null, [chipText(e)])];
    if (e.gap_pct != null && e.threshold != null) {
      kids.push(h('span', { class: 'g' }, ['임계까지 ' + fnum(Math.abs(e.gap_pct)) + '%']));
    } else if (e.vs_baseline_pct != null) {
      kids.push(h('span', { class: 'g' }, ['기준比 ' + (e.vs_baseline_pct >= 0 ? '+' : '') + fnum(e.vs_baseline_pct) + '%']));
    } else if (e.asof) {
      kids.push(h('span', { class: 'g' }, [e.asof]));
    }
    var attrs = { class: 'jemi-chip' };
    if (e.note) { attrs.title = e.note; }
    var node = h('span', attrs, kids);
    if (e.src && /^https?:/.test(e.src)) {
      return h('a', { href: e.src, target: '_blank', rel: 'noopener' }, [node]);
    }
    return node;
  }

  function card(c) {
    var meta = TYPE[c.type] || { ko: c.type, color: C.muted, wash: 'transparent' };
    var el = h('div', { class: 'jemi-card', 'data-type': c.type, style: 'border-left-color:' + meta.color });

    var head = h('div', { class: 'ct-h' }, [
      h('span', { class: 'badge', style: 'background:' + meta.wash + ';color:' + meta.color }, [meta.ko]),
      c.confidence ? h('span', { class: 'jemi-conf' }, [
        '신뢰 ', h('b', null, [c.confidence.level || '']),
        c.confidence.score != null ? ' · ' + fnum(c.confidence.score) : ''
      ]) : null
    ]);
    el.appendChild(head);
    el.appendChild(h('div', { class: 'tt' }, [c.title || '']));
    if (c.verdict) { el.appendChild(h('div', { class: 'vd' }, [c.verdict])); }

    var ev = c.evidence || [];
    if (ev.length) {
      var chips = h('div', { class: 'jemi-chips' }, []);
      for (var i = 0; i < ev.length && i < 6; i++) { chips.appendChild(evidenceChip(ev[i])); }
      el.appendChild(chips);
    }

    if (c.spark && c.spark.values && c.spark.values.length) {
      var sp = sparkline(c.spark, meta.color);
      if (sp) { el.appendChild(sp); }
    }

    if (c.link) { el.appendChild(h('div', { class: 'jemi-link' }, [c.link])); }

    if (c.see_also && c.see_also.length) {
      el.appendChild(h('div', { class: 'jemi-see' }, ['↔ 연계: ' + c.see_also.join(', ')]));
    }
    return el;
  }

  // ---------------------------------------------------------------- quote
  function quoteCard(q) {
    var el = h('div', { class: 'jemi-q' });
    el.appendChild(h('div', { class: 'who' }, [q.who || '']));
    var metaBits = [];
    if (q.when) { metaBits.push(q.when); }
    if (q.source_type) { metaBits.push(String(q.source_type).replace(/_/g, ' ')); }
    el.appendChild(h('div', { class: 'meta' }, [metaBits.join('  ·  ')]));
    if (q.original) { el.appendChild(h('div', { class: 'orig' }, ['“' + q.original + '”'])); }
    if (q.ko) { el.appendChild(h('div', { class: 'ko' }, [q.ko])); }
    if (q.why_sharp) { el.appendChild(h('div', { class: 'sharp' }, ['⟢ ' + q.why_sharp])); }

    var foot = h('div', { class: 'foot' }, []);
    var tags = q.tags || [];
    for (var i = 0; i < tags.length && i < 6; i++) { foot.appendChild(h('span', { class: 'jemi-tag' }, ['#' + tags[i]])); }
    var dl = q.our_data_link;
    if (dl && dl.label) {
      var dtxt = '🔗 ' + dl.label + (dl.value != null ? '  ' + fnum(dl.value) + (dl.unit || '') : '');
      foot.appendChild(h('span', { class: 'jemi-dl', title: dl.asof ? ('as of ' + dl.asof) : '' }, [dtxt]));
    }
    if (q.where && /^https?:/.test(q.where)) {
      foot.appendChild(h('a', { class: 'jemi-src', href: q.where, target: '_blank', rel: 'noopener' }, ['출처 ↗']));
    }
    el.appendChild(foot);
    return el;
  }

  // ---------------------------------------------------------------- main
  function renderInsight(target, data, quotes) {
    var root = typeof target === 'string' ? document.querySelector(target) : target;
    if (!root) { return; }
    var R = resolve(data, quotes);
    var ins = R.ins || {}, allQuotes = R.quotes || [];
    var cards = ins.cards || [];
    injectStyle(root);

    root.classList.add('jemi');
    root.innerHTML = '';

    // header
    var counts = ins.counts || {};
    var when = ins.generated ? String(ins.generated).slice(0, 16).replace('T', ' ') : '';
    root.appendChild(h('h2', null, ['💡 인사이트 — 데이터 종합 판독']));
    root.appendChild(h('div', { class: 'jemi-sub' }, [
      '교차확인·모순·임계근접·컨센갭 자동 카드 ' + cards.length + '장 · 핵심 인용 ' + allQuotes.length + '개' +
      (when ? '  ·  ' + when : '')
    ]));

    // top-3 cross-confirm read
    var byId = {};
    for (var i = 0; i < cards.length; i++) { byId[cards[i].id] = cards[i]; }
    var top = (ins.top3 || []).map(function (id) { return byId[id]; }).filter(Boolean);
    if (top.length) {
      root.appendChild(h('h3', null, ['오늘의 종합 판독 — 가장 강한 교차확인']));
      var topWrap = h('div', { class: 'jemi-top' }, []);
      for (var t = 0; t < top.length; t++) {
        var c = top[t];
        var m = TYPE[c.type] || { color: C.good };
        topWrap.appendChild(h('div', { class: 'jemi-hero', style: 'border-left-color:' + m.color }, [
          h('div', { class: 'rk' }, ['#' + (t + 1) + '  ' + (m.ko || '') + (c.strength != null ? '  · 강도 ' + fnum(c.strength) : '')]),
          h('div', { class: 'tt' }, [c.title || '']),
          h('div', { class: 'vd' }, [c.verdict || ''])
        ]));
      }
      root.appendChild(topWrap);
    }

    // counts row
    var countRow = h('div', { class: 'jemi-counts' }, []);
    for (var ti = 0; ti < TYPE_ORDER.length; ti++) {
      var ty = TYPE_ORDER[ti];
      countRow.appendChild(h('span', { class: 'jemi-count', style: 'border-color:' + TYPE[ty].color + '55' }, [
        TYPE[ty].ko + ' ' + (counts[ty] || 0)
      ]));
    }
    root.appendChild(countRow);

    // card grid + type filter
    root.appendChild(h('h3', null, ['자동 해석 카드']));
    var grid = h('div', { class: 'jemi-grid' }, []);
    var cardNodes = [];
    for (var ci = 0; ci < cards.length; ci++) {
      var node = card(cards[ci]);
      cardNodes.push({ type: cards[ci].type, node: node });
      grid.appendChild(node);
    }
    var typeFilter = h('div', { class: 'jemi-filters' }, []);
    var typeState = 'all';
    function applyType(sel) {
      typeState = sel;
      for (var x = 0; x < cardNodes.length; x++) {
        cardNodes[x].node.style.display = (sel === 'all' || cardNodes[x].type === sel) ? '' : 'none';
      }
      var btns = typeFilter.childNodes;
      for (var b = 0; b < btns.length; b++) {
        var on = btns[b].getAttribute('data-sel') === sel;
        btns[b].className = 'jemi-fbtn' + (on ? ' on' : '');
        btns[b].style.background = on ? (btns[b].getAttribute('data-color') || C.info) : C.chip;
        btns[b].style.borderColor = on ? (btns[b].getAttribute('data-color') || C.info) : C.chipBorder;
      }
    }
    typeFilter.appendChild(h('span', { class: 'jemi-fbtn on', 'data-sel': 'all', 'data-color': C.sub,
      onClick: function () { applyType('all'); } }, ['전체 ' + cards.length]));
    for (var tf = 0; tf < TYPE_ORDER.length; tf++) {
      (function (ty) {
        if (!counts[ty]) { return; }
        typeFilter.appendChild(h('span', { class: 'jemi-fbtn', 'data-sel': ty, 'data-color': TYPE[ty].color,
          onClick: function () { applyType(ty); } }, [TYPE[ty].ko + ' ' + counts[ty]]));
      })(TYPE_ORDER[tf]);
    }
    root.appendChild(typeFilter);
    root.appendChild(grid);
    applyType('all');

    // quote gallery + tag filter
    root.appendChild(h('h3', null, ['핵심 인용 갤러리 — 우리 커버리지 관련 압축 발언']));
    var tagCount = {};
    for (var qi = 0; qi < allQuotes.length; qi++) {
      var qt = allQuotes[qi].tags || [];
      for (var tg = 0; tg < qt.length; tg++) { tagCount[qt[tg]] = (tagCount[qt[tg]] || 0) + 1; }
    }
    var tagList = Object.keys(tagCount).sort(function (a, b) { return tagCount[b] - tagCount[a] || a.localeCompare(b); });

    var qwrap = h('div', { class: 'jemi-qwrap' }, []);
    var qNodes = [];
    for (var qj = 0; qj < allQuotes.length; qj++) {
      var qn = quoteCard(allQuotes[qj]);
      qNodes.push({ tags: allQuotes[qj].tags || [], node: qn });
      qwrap.appendChild(qn);
    }

    var tagFilter = h('div', { class: 'jemi-filters' }, []);
    var tagState = 'all';
    function applyTag(sel) {
      tagState = sel;
      var shown = 0;
      for (var y = 0; y < qNodes.length; y++) {
        var vis = sel === 'all' || qNodes[y].tags.indexOf(sel) !== -1;
        qNodes[y].node.style.display = vis ? '' : 'none';
        if (vis) { shown++; }
      }
      var tb = tagFilter.childNodes;
      for (var z = 0; z < tb.length; z++) {
        var onn = tb[z].getAttribute('data-tag') === sel;
        tb[z].className = 'jemi-fbtn' + (onn ? ' on' : '');
        tb[z].style.background = onn ? C.info : C.chip;
        tb[z].style.borderColor = onn ? C.info : C.chipBorder;
      }
      empty.style.display = shown ? 'none' : '';
    }
    tagFilter.appendChild(h('span', { class: 'jemi-fbtn on', 'data-tag': 'all',
      onClick: function () { applyTag('all'); } }, ['전체 ' + allQuotes.length]));
    for (var tl = 0; tl < tagList.length && tl < 28; tl++) {
      (function (tag) {
        tagFilter.appendChild(h('span', { class: 'jemi-fbtn', 'data-tag': tag,
          onClick: function () { applyTag(tag); } }, ['#' + tag + ' ' + tagCount[tag]]));
      })(tagList[tl]);
    }
    root.appendChild(tagFilter);
    var empty = h('div', { class: 'jemi-empty', style: 'display:none' }, ['해당 태그의 인용이 없습니다.']);
    root.appendChild(empty);
    root.appendChild(qwrap);
    if (!allQuotes.length) { empty.textContent = '인용 데이터가 없습니다.'; empty.style.display = ''; }

    return root;
  }

  if (typeof window !== 'undefined') { window.renderInsight = renderInsight; }
  if (typeof module !== 'undefined' && module.exports) { module.exports = { renderInsight: renderInsight }; }
})();
