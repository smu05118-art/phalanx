(function () {
  'use strict';
  if (window.PHXEvidence) return;
  var script = document.currentScript;
  var scriptURL = new URL(script && script.src || 'panoptes/market_evidence.js', document.baseURI);
  var dataURL = new URL('data/market_evidence.json', scriptURL);
  var links = {
    argus: new URL('../argus/', scriptURL).href,
    human: new URL('./#human', scriptURL).href,
    liq: new URL('./#liq', scriptURL).href,
    tech: new URL('./#tech', scriptURL).href
  };
  var data = null, failed = false, observers = new Map(), liveMounts = new Map();
  // Widget kinds are stable across parent replacement and across app pages.
  // Only these selection values enter storage or the research-desk snapshot API.
  var storageKey = 'phx:market-evidence:state:v1';
  var stateRules = {
    flow: { ticker: ['005930', '000660'], investor: ['foreign_net_shares', 'institution_net_shares', 'individual_net_shares'], mode: ['daily', 'cumulative'] },
    episodes: { index: ['kospi', 'kosdaq', 'sp500', 'nasdaq'], horizon: ['5', '20', '60'] }
  };
  var widgetStates = {
    flow: { ticker: '005930', investor: 'foreign_net_shares', mode: 'daily' },
    episodes: { index: 'kospi', horizon: '20' }
  };
  function plainObject(value) {
    try { if (!value || typeof value !== 'object') return false; var proto = Object.getPrototypeOf(value); return proto === Object.prototype || proto === null; }
    catch (_) { return false; }
  }
  function ownValue(value, key) {
    try { var descriptor = value && Object.getOwnPropertyDescriptor(value, key); return descriptor && Object.prototype.hasOwnProperty.call(descriptor, 'value') ? descriptor.value : undefined; }
    catch (_) { return undefined; }
  }
  function safeStatePatch(input) {
    var result = {};
    if (!plainObject(input)) return result;
    Object.keys(stateRules).forEach(function (kind) {
      var candidate = ownValue(input, kind);
      if (!plainObject(candidate)) return;
      Object.keys(stateRules[kind]).forEach(function (key) {
        var value = ownValue(candidate, key);
        if (typeof value !== 'string' || stateRules[kind][key].indexOf(value) < 0) return;
        if (!result[kind]) result[kind] = {};
        result[kind][key] = value;
      });
    });
    return result;
  }
  function snapshotState() {
    var result = {};
    Object.keys(stateRules).forEach(function (kind) {
      result[kind] = {};
      Object.keys(stateRules[kind]).forEach(function (key) { result[kind][key] = widgetStates[kind][key]; });
    });
    return result;
  }
  function applyStatePatch(input) {
    var patch = safeStatePatch(input), changed = false;
    Object.keys(patch).forEach(function (kind) {
      Object.keys(patch[kind]).forEach(function (key) {
        if (widgetStates[kind][key] !== patch[kind][key]) { widgetStates[kind][key] = patch[kind][key]; changed = true; }
      });
    });
    return changed;
  }
  function persistState(kinds) {
    // Separate keys prevent an older page changing one widget from resetting another.
    kinds.forEach(function (kind) {
      try { window.localStorage.setItem(storageKey + ':' + kind, JSON.stringify({ version: 1, state: snapshotState()[kind] })); }
      catch (_) { /* Blocked storage or quota failure leaves in-page controls usable. */ }
    });
  }
  function loadState() {
    Object.keys(stateRules).forEach(function (kind) {
      var key = storageKey + ':' + kind, stored;
      try { stored = window.localStorage.getItem(key); } catch (_) { return; }
      if (stored == null) return;
      try {
        if (typeof stored !== 'string' || stored.length > 10000) throw new Error('state-size');
        var envelope = JSON.parse(stored);
        if (!plainObject(envelope) || ownValue(envelope, 'version') !== 1 || !plainObject(ownValue(envelope, 'state'))) throw new Error('state-schema');
        var input = {}; input[kind] = ownValue(envelope, 'state'); applyStatePatch(input);
      } catch (_) {
        try { window.localStorage.removeItem(key); } catch (_) { /* Defaults are still available. */ }
      }
    });
  }
  function stateFor(kind) { return widgetStates[kind] || {}; }
  function repaintMounts(kind) {
    liveMounts.forEach(function (mountedKind, section) {
      if (!section.isConnected) { liveMounts.delete(section); return; }
      if (kind === mountedKind || !kind && Object.prototype.hasOwnProperty.call(stateRules, mountedKind)) paint(section, mountedKind, stateFor(mountedKind));
    });
  }
  function restoreState(input) {
    var patch = safeStatePatch(input);
    if (applyStatePatch(patch)) { persistState(Object.keys(patch)); repaintMounts(); }
    return snapshotState();
  }
  loadState();
  var number = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 2 });
  function valid(v) { return typeof v === 'number' && Number.isFinite(v); }
  function esc(v) { return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]; }); }
  function fmt(v, digits) { return valid(v) ? v.toLocaleString('ko-KR', { minimumFractionDigits: digits == null ? 0 : digits, maximumFractionDigits: digits == null ? 2 : digits }) : '미확인'; }
  function signed(v, digits, suffix) { return valid(v) ? (v > 0 ? '+' : '') + fmt(v, digits == null ? 2 : digits) + (suffix || '') : '미확인'; }
  function date(v) { return typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : '미확인'; }
  function external(url, label) {
    try { var u = new URL(url); if (u.protocol !== 'https:' || u.username || u.password) return ''; return '<a href="' + esc(u.href) + '" target="_blank" rel="noopener noreferrer">' + esc(label) + ' ↗</a>'; }
    catch (_) { return ''; }
  }
  function internal(key, label) { return '<a href="' + esc(links[key]) + '">' + esc(label) + ' →</a>'; }
  function asof(component) { return component && (component.as_of || component.asof) || null; }
  function badge(key, observed) {
    var errors = data && data.errors || {};
    if (Object.prototype.hasOwnProperty.call(errors, key) && errors[key]) return '<span class="me-badge me-warning">갱신 확인 필요 · 이전 관측</span>';
    var ms = typeof observed === 'string' ? Date.parse(observed + 'T00:00:00+09:00') : NaN;
    var age = Number.isFinite(ms) ? Math.floor((Date.now() - ms) / 86400000) : null;
    return age != null && age > 7 ? '<span class="me-badge me-warning">기준일 ' + esc(age) + '일 전</span>' : '';
  }
  function head(title, subtitle, key, observed) {
    return '<div class="me-heading"><div><h3>' + esc(title) + '</h3>' + (subtitle ? '<p class="me-note">' + esc(subtitle) + '</p>' : '') + '</div>' + badge(key, observed) + '</div>';
  }
  function metric(label, value, note) { return '<div class="me-metric"><span>' + esc(label) + '</span><strong>' + esc(value) + '</strong>' + (note ? '<small>' + esc(note) + '</small>' : '') + '</div>'; }
  function empty(message) { return '<p class="me-empty" role="status">' + esc(message || '원자료를 확인한 뒤 표시합니다.') + '</p>'; }
  function latest(rows) { return rows && rows.length ? rows[rows.length - 1] : {}; }
  function ordered(rows) { return Array.isArray(rows) ? rows.filter(function (r) { return r && date(r.date) !== '미확인'; }).slice().sort(function (a, b) { return a.date.localeCompare(b.date); }) : []; }
  function spark(points, title, unit, height) {
    points = (points || []).slice(0, 5000);
    var finite = points.filter(function (p) { return valid(p.value); });
    if (finite.length < 2) return empty('차트를 그릴 관측값이 부족합니다.');
    var values = finite.map(function (p) { return p.value; });
    var lo = Math.min.apply(null, values), hi = Math.max.apply(null, values), span = hi - lo || Math.abs(hi) * 0.02 || 1;
    var h = height || 160, w = 760, pad = 18, chartH = h - pad * 2;
    var parts = [], active = false;
    points.forEach(function (p, i) {
      if (!valid(p.value)) { active = false; return; }
      var x = pad + i / Math.max(1, points.length - 1) * (w - 2 * pad);
      var y = h - pad - (p.value - lo) / span * chartH;
      parts.push((active ? 'L' : 'M') + x.toFixed(2) + ',' + y.toFixed(2)); active = true;
    });
    var zero = lo < 0 && hi > 0 ? '<line x1="18" x2="742" y1="' + (h - pad - (0 - lo) / span * chartH).toFixed(2) + '" y2="' + (h - pad - (0 - lo) / span * chartH).toFixed(2) + '" class="me-zero"/>' : '';
    var desc = title + ', ' + points.length + '개 관측, 최저 ' + fmt(lo) + ' ' + unit + ', 최고 ' + fmt(hi) + ' ' + unit;
    return '<figure class="me-chart"><figcaption><b>' + esc(title) + '</b><span>' + esc(fmt(lo)) + ' ~ ' + esc(fmt(hi)) + ' ' + esc(unit) + '</span></figcaption><svg role="img" aria-label="' + esc(desc) + '" viewBox="0 0 760 ' + h + '" preserveAspectRatio="none"><title>' + esc(desc) + '</title>' + zero + '<path d="' + parts.join(' ') + '" class="me-path"/></svg><div class="me-chart-dates"><span>' + esc(points[0].date || '') + '</span><span>' + esc(points[points.length - 1].date || '') + '</span></div></figure>';
  }
  function installStyle() {
    if (document.getElementById('phx-market-evidence-style')) return;
    var style = document.createElement('style'); style.id = 'phx-market-evidence-style';
    style.textContent = '.me-wrap{box-sizing:border-box;max-width:1180px;margin:22px 0;padding:20px;border:1px solid var(--line,rgba(127,140,160,.3));border-radius:14px;background:var(--panel,var(--card,transparent));color:inherit;font-family:inherit;font-size:13px;line-height:1.55;overflow:hidden}.me-wrap *{box-sizing:border-box}.me-wrap h3{margin:0;font-size:17px;font-weight:750;line-height:1.4}.me-wrap p{margin:0}.me-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:16px}.me-note,.me-meta,.me-chart-dates,.me-metric>span,.me-metric small{color:var(--dim,var(--muted,#8b95a2));font-size:12px}.me-note{margin-top:4px!important}.me-meta{display:flex;gap:8px 16px;flex-wrap:wrap;margin-top:12px}.me-wrap a{color:var(--accent,#329eb3);text-decoration:none}.me-wrap a:hover{text-decoration:underline}.me-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px}.me-metric{min-width:0;padding:13px;background:var(--panel2,rgba(127,140,160,.045));border-radius:9px}.me-metric>span,.me-metric strong,.me-metric small{display:block}.me-metric strong{font-size:19px;font-variant-numeric:tabular-nums;line-height:1.45;overflow-wrap:anywhere}.me-metric small{margin-top:3px}.me-badge{font-size:11px;padding:3px 9px;border:1px solid var(--line,rgba(127,140,160,.3));border-radius:20px;white-space:nowrap}.me-warning{color:var(--s4,#c78b35)}.me-state{display:inline-flex;gap:8px;align-items:center;font-weight:650;margin:10px 0}.me-detail{margin-top:14px;border-top:1px solid var(--line,rgba(127,140,160,.2));padding-top:8px}.me-detail>summary,.me-episode>summary{cursor:pointer;min-height:40px;padding:9px 0;color:inherit;font-weight:600}.me-detail[open]>summary{margin-bottom:7px}.me-detail p+p{margin-top:7px}.me-chart{margin:16px 0 5px;min-width:0}.me-chart figcaption{display:flex;justify-content:space-between;gap:12px;font-size:12px;margin-bottom:5px}.me-chart figcaption span{color:var(--dim,var(--muted,#8b95a2));font-variant-numeric:tabular-nums}.me-chart svg{display:block;width:100%;height:145px;overflow:visible}.me-path{fill:none;stroke:var(--accent,#329eb3);stroke-width:2;vector-effect:non-scaling-stroke;stroke-linejoin:round}.me-zero{stroke:var(--dim,#8b95a2);stroke-width:1;stroke-dasharray:4 4;opacity:.4}.me-chart-dates{display:flex;justify-content:space-between;font-size:11px}.me-controls{display:flex;align-items:flex-end;gap:10px;flex-wrap:wrap;margin:13px 0}.me-controls label{display:flex;flex-direction:column;gap:4px;font-size:11px;color:var(--dim,var(--muted,#8b95a2))}.me-controls select{font:inherit;font-size:12px;min-height:38px;border:1px solid var(--line,rgba(127,140,160,.3));border-radius:8px;padding:6px 30px 6px 10px;color:inherit;background:var(--panel2,var(--panel,transparent));min-width:110px}.me-controls option{background:var(--panel,#fff);color:var(--ink,#222)}.me-wrap :focus-visible{outline:2px solid var(--accent,#329eb3);outline-offset:3px}.me-table-wrap{overflow-x:auto;margin:12px 0}.me-table{border-collapse:collapse;width:100%;font-size:12px;white-space:nowrap}.me-table th,.me-table td{padding:10px 9px;border-bottom:1px solid var(--line,rgba(127,140,160,.2));text-align:right;font-variant-numeric:tabular-nums}.me-table th:first-child,.me-table td:first-child{text-align:left}.me-table th{color:var(--dim,var(--muted,#8b95a2));font-weight:500}.me-empty{padding:14px 0;color:var(--dim,var(--muted,#8b95a2))}.me-short{padding:11px 13px;margin-top:13px;border:1px dashed var(--line,rgba(127,140,160,.3));border-radius:8px;font-size:12px}.me-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.me-episodes{margin-top:15px}.me-episode{border-top:1px solid var(--line,rgba(127,140,160,.2))}.me-episode>summary{font-size:12px}.me-episode .me-chart svg{height:105px}.me-episode-grid{display:flex;gap:12px 24px;flex-wrap:wrap;font-size:12px;color:var(--dim,var(--muted,#8b95a2));margin:4px 0}.me-compact{padding:14px 18px}.me-compact>.me-detail{margin-top:0;border:0;padding:0}.me-compact>.me-detail>summary{font-size:13px}.me-muted{color:var(--dim,var(--muted,#8b95a2))}@media(max-width:650px){.me-wrap{padding:15px;margin:16px 0}.me-heading{flex-direction:column;gap:7px}.me-wrap h3{font-size:16px}.me-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.me-metric{padding:11px}.me-metric strong{font-size:17px}.me-columns{grid-template-columns:1fr;gap:8px}.me-chart figcaption{flex-direction:column;gap:0}.me-chart svg{height:120px}.me-controls{gap:7px}.me-controls select{min-width:90px}.me-table th,.me-table td{padding:9px 6px}.me-compact{padding:12px}}';
    document.head.appendChild(style);
  }
  var ready = (async function () {
    var controller = new AbortController(), timer = setTimeout(function () { controller.abort(); }, 15000);
    try {
      var response = await fetch(dataURL.href, { signal: controller.signal, credentials: 'same-origin' });
      if (!response.ok) throw new Error('unavailable');
      var text = await response.text(); if (text.length > 6000000) throw new Error('oversized');
      data = JSON.parse(text); if (!data || data.schema_version !== 1) throw new Error('schema');
      return data;
    } catch (_) { failed = true; data = null; return null; }
    finally { clearTimeout(timer); }
  }());
  function memoryHTML(compact) {
    var m = data && data.memory;
    if (!m || !valid(m.value)) return empty('DDR5 원자료를 확인한 뒤 표시합니다.');
    var c = m.coverage || {};
    var html = head('DDR5 근거', m.name || '메모리 현물 가격', 'memory', asof(m));
    html += '<div class="me-grid">' + metric('현물 가격', fmt(m.value, 3), '달러/칩') + metric('1주 변화', signed(m.weekly_change_pct, 2, '%'), '직전 7일 기준') + metric('변화율 차이', signed(m.change_delta_pp, 2, '%p'), '지난주 변화율과 비교') + metric('관측기간 고점 대비', signed(m.observed_drawdown_pct, 2, '%'), date(c.start) + '부터') + '</div>';
    html += '<div class="me-state">' + esc(m.state || '방향 판단 보류') + '</div><p class="me-note">52주 고점 대비 ' + (valid(m.drawdown_52w_pct) ? esc(signed(m.drawdown_52w_pct, 2, '%')) : '미확인 · 이력 부족') + '</p>';
    html += '<div class="me-meta"><span>관측일 ' + esc(date(asof(m))) + '</span>' + external(m.source_url, m.source_name || '가격 원문') + (!compact ? internal('argus', '반도체 가치사슬') + internal('human', '수급 확인') + internal('liq', '신용·유동성') : '') + '</div>';
    html += '<details class="me-detail"><summary>계산 기준·관측 범위</summary><p class="me-note">' + esc(m.method || '같은 규격의 현물 가격을 비교합니다.') + '</p><p class="me-note">' + esc(date(c.start)) + ' ~ ' + esc(date(c.end)) + ' · 이력 ' + esc(fmt(c.observations, 0)) + '건 · 원문 직접 대조 ' + esc(fmt(c.verified_quote_observations, 0)) + '건</p>';
    if (m.comparisons) html += '<p class="me-note">비교일 ' + esc(date(m.comparisons.current)) + ' / ' + esc(date(m.comparisons.week_ago)) + ' / ' + esc(date(m.comparisons.two_weeks_ago)) + '</p>';
    html += '<p class="me-note">현물 가격과 HBM 계약가격·기업 이익은 구분합니다.</p>';
    if (!compact) html += spark(ordered(m.history).map(function (r) { return { date: r.date, value: r.value }; }), 'DDR5 관측 가격', '달러/칩');
    html += '</details>';
    return html;
  }
  function creditHTML() {
    var c = data && data.korea_credit, rows = ordered(c && c.records).filter(function (r) { return !asof(c) || r.date <= asof(c); }), last = c && c.latest || latest(rows), metrics = c && c.metrics || {};
    if (!c || !rows.length) return head('국내 신용·예탁금', '', 'korea_credit', asof(c)) + empty();
    var html = head('국내 신용·예탁금', '잔고·증감·비율을 각각 확인합니다.', 'korea_credit', asof(c));
    html += '<div class="me-grid">' + metric('신용융자 잔고', valid(last.credit_krw) ? fmt(last.credit_krw / 1e12, 2) + '조원' : '미확인', '결제일 기준 · ETF 포함') + metric('투자자예탁금', valid(last.deposits_krw) ? fmt(last.deposits_krw / 1e12, 2) + '조원' : '미확인', '장내파생 거래예수금 제외') + metric('신용 / 예탁금', valid(metrics.ratio_pct) ? fmt(metrics.ratio_pct, 2) + '%' : '미확인', '같은 관측일 비교') + metric('신용융자 20공표일 변화', signed(metrics.credit_change_20d_pct, 2, '%'), valid(metrics.observations_20d) ? '비교 관측 ' + fmt(metrics.observations_20d, 0) + '건' : '비교 이력 확인 중') + '</div>';
    html += '<div class="me-meta"><span>공표자료 기준일 ' + esc(date(asof(c))) + '</span>' + external(c.source && c.source.url, c.source && c.source.name || '금융투자협회') + '</div>';
    var percentiles = metrics.percentiles || {};
    if (percentiles.ratio_pct || percentiles.credit_change_20d_pct) {
      html += '<div class="me-grid" style="margin-top:12px">' + [['ratio_pct', '신용 / 예탁금'], ['credit_change_20d_pct', '20공표일 신용 변화']].map(function (entry) {
        var p = percentiles[entry[0]] || {};
        return metric(entry[1] + ' · 3년 관측 백분위', valid(p.value_pct) ? fmt(p.value_pct, 1) + '%ile' : '미확인', valid(p.sample_size) ? '관측 ' + fmt(p.sample_size, 0) + '건' : '최소 252개 관측 필요');
      }).join('') + '</div>';
    }
    var since = new Date((asof(c) || last.date) + 'T00:00:00Z'); since.setUTCFullYear(since.getUTCFullYear() - 3);
    var cutoff = Number.isFinite(since.getTime()) ? since.toISOString().slice(0, 10) : '';
    var history = rows.filter(function (r) { return r.date >= cutoff; });
    html += '<div class="me-columns">' + spark(history.map(function (r) { return { date: r.date, value: valid(r.credit_krw) ? r.credit_krw / 1e12 : null }; }), '최근 3년 신용융자 잔고', '조원') + spark(history.map(function (r) { return { date: r.date, value: valid(r.deposits_krw) ? r.deposits_krw / 1e12 : null }; }), '최근 3년 투자자예탁금', '조원') + '</div>';
    html += '<details class="me-detail"><summary>원자료·관측 범위</summary><p class="me-note">공표된 날짜만 연결합니다. 두 차트는 각각의 실제 금액 범위를 사용합니다.</p><p class="me-note">' + esc(date(rows[0].date)) + ' ~ ' + esc(date(last.date)) + ' · ' + esc(fmt(rows.length, 0)) + '개 관측</p><p class="me-note">20공표일 비교: ' + esc(date(metrics.from_date)) + ' ~ ' + esc(date(metrics.to_date)) + '</p><p class="me-note">백분위는 최근 3년의 최소 252개 관측으로 계산하며, 같은 값은 절반을 반영합니다. 각 지표의 위치를 따로 읽습니다.</p>';
    [['ratio_pct', '신용 / 예탁금 백분위'], ['credit_change_20d_pct', '20공표일 변화 백분위']].forEach(function (entry) { var p = percentiles[entry[0]]; if (p) html += '<p class="me-note">' + esc(entry[1]) + ': ' + esc(date(p.from_date)) + ' ~ ' + esc(date(p.to_date)) + '</p>'; });
    html += '<div class="me-meta">' + external(c.source && c.source.services && c.source.services.credit && c.source.services.credit.url, '신용융자 원자료') + external(c.source && c.source.services && c.source.services.deposits && c.source.services.deposits.url, '예탁금 원자료') + '</div></details>';
    return html;
  }
  function select(label, key, options, chosen) {
    return '<label>' + esc(label) + '<select aria-label="' + esc(label) + '" data-me-control="' + esc(key) + '">' + options.map(function (o) { return '<option value="' + esc(o[0]) + '"' + (String(o[0]) === String(chosen) ? ' selected' : '') + '>' + esc(o[1]) + '</option>'; }).join('') + '</select></label>';
  }
  var investorNames = [['foreign_net_shares', '외국인'], ['institution_net_shares', '기관'], ['individual_net_shares', '개인']];
  function shortHTML(short) {
    short = short || {}; var turnover = short.turnover || {}, balance = short.balance || {};
    if (!valid(turnover.shares) && !valid(turnover.krw) && !valid(balance.shares) && !valid(balance.krw)) return '<div class="me-short">공매도 원천 미확인 <span class="me-muted">· 거래·잔고 값과 기준일을 확인한 뒤 표시합니다.</span></div>';
    return '<div class="me-short"><b>공매도</b><div>거래: ' + esc(valid(turnover.shares) ? fmt(turnover.shares, 0) + '주' : '수량 미확인') + (valid(turnover.krw) ? ' · ' + esc(fmt(turnover.krw, 0)) + '원' : '') + ' · 거래일 ' + esc(date(turnover.as_of)) + '</div><div>순보유잔고: ' + esc(valid(balance.shares) ? fmt(balance.shares, 0) + '주' : '수량 미확인') + (valid(balance.krw) ? ' · ' + esc(fmt(balance.krw, 0)) + '원' : '') + ' · 잔고 기준일 ' + esc(date(balance.as_of)) + '</div>' + external(short.source_url, 'KRX 원자료') + '</div>';
  }
  function flowHTML(state, compact) {
    var component = data && data.semiconductor, stocks = component && component.stocks || {}, codes = ['005930', '000660'].filter(function (c) { return stocks[c]; });
    if (!codes.length) return head('반도체 연속 수급', '', 'semiconductor', null) + empty();
    var ticker = codes.indexOf(state.ticker) >= 0 ? state.ticker : codes[0], stock = stocks[ticker], rows = ordered(stock.records), last = latest(rows);
    var html = head('반도체 연속 수급', '순매수 주식수 · 외국인·기관·개인', 'semiconductor', asof(stock));
    html += '<div class="me-controls">' + select('종목', 'ticker', codes.map(function (code) { return [code, stocks[code].name || code]; }), ticker) + '</div>';
    html += '<div class="me-table-wrap"><table class="me-table"><thead><tr><th>투자자</th><th>5거래일 순매수(주)</th><th>20거래일 순매수(주)</th></tr></thead><tbody>';
    investorNames.forEach(function (inv) {
      html += '<tr><td>' + esc(inv[1]) + '</td>' + ['5d', '20d'].map(function (key) { var w = stock.windows && stock.windows[key]; return '<td>' + esc(w && w.status === 'ok' ? signed(w[inv[0]], 0) : '미확인') + '</td>'; }).join('') + '</tr>';
    });
    html += '</tbody></table></div><div class="me-meta"><span>수급 기준일 ' + esc(date(asof(stock))) + '</span><span>외국인 보유비율 ' + esc(valid(last.foreign_ownership_pct) ? fmt(last.foreign_ownership_pct, 2) + '%' : '미확인') + '</span>' + external(last.source_url, '네이버 수급 원자료') + '</div>';
    if (!compact) {
      html += '<div class="me-controls">' + select('투자자', 'investor', investorNames, state.investor) + select('차트', 'mode', [['daily', '일별 순매수'], ['cumulative', '표시기간 누계']], state.mode) + '</div>';
      var investor = investorNames.some(function (v) { return v[0] === state.investor; }) ? state.investor : investorNames[0][0], total = 0, complete = true;
      var points = rows.slice(-60).map(function (r) {
        if (state.mode !== 'cumulative') return { date: r.date, value: r[investor] };
        if (!valid(r[investor])) complete = false;
        if (complete) total += r[investor];
        return { date: r.date, value: complete ? total : null };
      });
      var invName = investorNames.filter(function (v) { return v[0] === investor; })[0][1];
      var missingDates = stock.calendar && stock.calendar.missing_flow_dates || [];
      html += state.mode === 'cumulative' && missingDates.some(function (d) { return points.length && d >= points[0].date && d <= points[points.length - 1].date; }) ? empty('표시기간에 빠진 거래일이 있어 누계는 표시하지 않습니다.') : spark(points, invName + ' ' + (state.mode === 'cumulative' ? '표시기간 누계' : '일별 순매수'), '주');
      html += shortHTML(stock.short);
      html += '<details class="me-detail"><summary>기간·단위·일별 원자료</summary><p class="me-note">당일 관측은 제외합니다. 가격 이력의 거래일과 수급 날짜를 대조하며, 빠진 값은 채우지 않습니다. 순매수 수량을 종가로 곱해 금액으로 표시하지 않습니다.</p>';
      ['5d', '20d'].forEach(function (key) { var w = stock.windows && stock.windows[key] || {}; html += '<p class="me-note">' + esc(key === '5d' ? '5거래일' : '20거래일') + ': ' + esc(date(w.from_date)) + ' ~ ' + esc(date(w.to_date)) + ' · ' + esc(w.status === 'ok' ? '기간 확인' : '필요 관측 미확인') + '</p>'; });
      html += '<p class="me-note">개인·기관·외국인 외 투자자 분류가 있어 세 합계는 0과 다를 수 있습니다. 차트 누계는 표시기간 첫 관측부터 시작합니다.</p><div class="me-table-wrap"><table class="me-table"><thead><tr><th>거래일</th><th>외국인(주)</th><th>기관(주)</th><th>개인(주)</th><th>외국인 보유율</th></tr></thead><tbody>' + rows.slice(-60).reverse().map(function (r) { return '<tr><td>' + esc(date(r.date)) + '</td>' + investorNames.map(function (v) { return '<td>' + esc(signed(r[v[0]], 0)) + '</td>'; }).join('') + '<td>' + esc(valid(r.foreign_ownership_pct) ? fmt(r.foreign_ownership_pct, 2) + '%' : '미확인') + '</td></tr>'; }).join('') + '</tbody></table></div></details>';
    }
    return html;
  }
  var indexLabels = { kospi: 'KOSPI', kosdaq: 'KOSDAQ', sp500: 'S&P 500', nasdaq: 'NASDAQ', '^KS11': 'KOSPI', '^KQ11': 'KOSDAQ', '^GSPC': 'S&P 500', '^IXIC': 'NASDAQ' };
  function episodesHTML(state) {
    var component = data && data.episodes, indices = component && component.indices || {}, keys = Object.keys(indices);
    if (!keys.length) return head('과거 낙폭 사례', '직전 252거래일 고점에서 -10%를 처음 하향 통과한 관측', 'episodes', null) + empty('비교할 과거 사례를 확인한 뒤 표시합니다.');
    var key = keys.indexOf(state.index) >= 0 ? state.index : keys[0], index = indices[key];
    var horizon = ['5', '20', '60'].indexOf(String(state.horizon)) >= 0 ? String(state.horizon) : '20';
    var sum = index.summary && index.summary[horizon] || {};
    var html = head('과거 낙폭 사례', '직전 252거래일 고점에서 -10%를 처음 하향 통과한 관측', 'episodes', asof(index));
    html += '<div class="me-controls">' + select('지수', 'index', keys.map(function (k) { return [k, indexLabels[k] || indices[k].name || k]; }), key) + select('관찰 기간', 'horizon', [['5', '5거래일 후'], ['20', '20거래일 후'], ['60', '60거래일 후']], horizon) + '</div>';
    html += '<div class="me-grid">' + metric('완료 사례', fmt(sum.n_completed, 0) + (valid(sum.n_completed) ? '건' : ''), '진행 중 ' + fmt(sum.n_ongoing, 0) + (valid(sum.n_ongoing) ? '건' : '')) + metric('이후 종가 수익률 중앙값', signed(sum.median_return_pct, 2, '%'), horizon + '거래일 완료 사례') + metric('추가 종가 낙폭 중앙값', signed(sum.median_min_close_return_pct, 2, '%'), '사례 시작일 종가 대비') + metric('과거 상승 사례 비율', valid(sum.past_positive_rate_pct) ? fmt(sum.past_positive_rate_pct, 1) + '%' : '미확인', '과거 완료 사례 중 비율') + '</div>';
    html += '<p class="me-note">과거 관측의 요약입니다. 미래 상승 확률이나 매수 시점을 뜻하지 않습니다.</p><div class="me-meta"><span>관측 기준일 ' + esc(date(asof(index))) + '</span>' + external(index.source && index.source.url, '지수 가격 원자료') + '</div>';
    var cases = Array.isArray(index.episodes) ? index.episodes.slice().reverse() : [];
    html += '<div class="me-episodes">' + (cases.length ? cases.map(function (episode) {
      var o = episode.outcomes && episode.outcomes[horizon] || {}, done = o.status === 'completed';
      var ret = done ? o.close_return_pct : o.observed_return_pct, drop = done ? o.min_close_return_pct : o.observed_min_close_return_pct;
      var label = done ? horizon + '거래일 완료' : '진행 중 · ' + fmt(o.observed_days, 0) + '거래일 관측';
      var path = (Array.isArray(episode.path) ? episode.path : []).filter(function (r) { return valid(r.day) && r.day <= Number(horizon); }).map(function (r) { return { date: r.date, value: r.return_pct }; });
      return '<details class="me-episode"><summary>' + esc(date(episode.entry_date)) + ' · ' + esc(label) + ' · ' + esc(done ? '종가 ' : '현재까지 ') + esc(signed(ret, 2, '%')) + '</summary><div class="me-episode-grid"><span>시작 종가 ' + esc(fmt(episode.entry_close)) + '</span><span>추가 종가 낙폭 ' + esc(signed(drop, 2, '%')) + '</span><span>마지막 관측 ' + esc(date(o.end_date)) + '</span></div>' + spark(path, '사례 시작일 종가 대비 변화', '%', 115) + '</details>';
    }).join('') : empty('이 관측기간에는 조건을 충족한 사례가 없습니다.')) + '</div>';
    var history = index.history || {};
    html += '<details class="me-detail"><summary>사례 선정·기간·제외 기준</summary><p class="me-note">시작일을 제외한 직전 252개 거래일 최고 종가를 기준으로, 전 관측은 -10% 이상이고 현재 관측이 -10% 미만인 첫 날짜를 선택합니다.</p><p class="me-note">사례가 시작되면 최소 60거래일이 지나고 낙폭이 -10% 이상으로 회복한 뒤 새로 하향 통과해야 다음 사례로 셉니다. 처음 253개 관측은 기준을 준비하는 기간입니다.</p><p class="me-note">종가 기준으로 계산하며 배당·수수료·장중 저가를 포함하지 않습니다. 완료되지 않은 사례는 중앙값과 과거 상승 비율에서 제외합니다.</p><p class="me-note">관측기간 ' + esc(date(history.start)) + ' ~ ' + esc(date(history.end)) + ' · ' + esc(fmt(history.n_observations, 0)) + '개 관측</p></details>';
    return html;
  }
  function argusHTML(state) {
    var m = data && data.memory, stocks = data && data.semiconductor && data.semiconductor.stocks || {};
    var brief = valid(m && m.value) ? 'DDR5 ' + fmt(m.value, 3) + '달러 · ' + (m.state || '') : 'DDR5·국내 반도체 수급';
    var html = '<details class="me-detail"><summary>반도체 관측 근거 <span class="me-muted">· ' + esc(brief) + '</span> ' + badge('memory', asof(m)) + ' ' + badge('semiconductor', asof(stocks['005930'])) + '</summary><p class="me-note">회사·공시를 검토할 때 함께 확인할 가격과 수급입니다.</p><div class="me-columns"><div>' + memoryHTML(true) + '</div><div>';
    ['005930', '000660'].forEach(function (code) {
      var s = stocks[code]; if (!s) return;
      var w = s.windows && s.windows['20d'] || {};
      html += '<div class="me-metric"><span>' + esc(s.name || code) + ' · 외국인 20거래일 순매수</span><strong>' + esc(w.status === 'ok' ? signed(w.foreign_net_shares, 0, '주') : '미확인') + '</strong><small>기준일 ' + esc(date(asof(s))) + '</small>' + badge('semiconductor', asof(s)) + '</div>';
    });
    html += '<div class="me-meta">' + internal('human', '수급 상세') + internal('liq', '신용·유동성') + internal('tech', '과거 낙폭 사례') + '</div></div></div></details>';
    return html;
  }
  var renderers = { memory: function () { return memoryHTML(false); }, credit: creditHTML, flow: function (state) { return flowHTML(state, false); }, episodes: episodesHTML, argus: argusHTML };
  function findParent(parent) { return typeof parent === 'string' ? document.querySelector(parent) : parent; }
  function paint(section, kind, state) {
    section.innerHTML = failed ? empty('관측 근거를 불러오지 못했습니다. 잠시 후 다시 확인해 주세요.') : renderers[kind](state);
    section.querySelectorAll('select[data-me-control]').forEach(function (selectEl) {
      selectEl.addEventListener('change', function () {
        var key = selectEl.dataset.meControl, patch = {};
        // Controls and external saved views pass through the same whitelist.
        if (Object.prototype.hasOwnProperty.call(stateRules, kind) && Object.prototype.hasOwnProperty.call(stateRules[kind], key)) {
          patch[kind] = {}; patch[kind][key] = selectEl.value;
        }
        if (applyStatePatch(patch)) { persistState([kind]); repaintMounts(kind); }
        else paint(section, kind, stateFor(kind));
        var fresh = section.querySelector('select[data-me-control="' + key + '"]'); if (fresh) fresh.focus();
      });
    });
  }
  async function mount(parent, kind) {
    parent = findParent(parent); if (!parent || !parent.appendChild) return null;
    installStyle(); await ready;
    var existing = Array.prototype.find.call(parent.children, function (child) { return child.dataset && child.dataset.phxEvidence === kind; });
    if (existing) return existing;
    var section = document.createElement('section'); section.className = 'me-wrap' + (kind === 'argus' ? ' me-compact' : ''); section.dataset.phxEvidence = kind;
    section.setAttribute('aria-label', ({ memory: 'DDR5 근거', credit: '국내 신용·예탁금', flow: '반도체 연속 수급', episodes: '과거 낙폭 사례', argus: '반도체 관측 근거' })[kind]);
    // Drop detached sections when the host recreates a tab or card.
    liveMounts.forEach(function (_, mounted) { if (!mounted.isConnected) liveMounts.delete(mounted); });
    paint(section, kind, stateFor(kind)); parent.prepend(section); liveMounts.set(section, kind); return section;
  }
  function watch(id, kind) {
    var parent = document.getElementById(id); if (!parent || observers.has(parent)) return;
    var pending = false;
    var observer = new MutationObserver(function () {
      if (pending || Array.prototype.some.call(parent.children, function (child) { return child.dataset && child.dataset.phxEvidence === kind; })) return;
      pending = true; requestAnimationFrame(function () { pending = false; if (parent.isConnected) mount(parent, kind); });
    });
    observer.observe(parent, { childList: true }); observers.set(parent, observer); mount(parent, kind);
  }
  function boot() {
    installStyle(); watch('liqview', 'credit'); watch('humanview', 'flow'); watch('techview', 'episodes'); watch('argusRoot', 'argus');
  }
  window.PHXEvidence = { ready: ready, mountMemory: function (p) { return mount(p, 'memory'); }, mountCredit: function (p) { return mount(p, 'credit'); }, mountFlow: function (p) { return mount(p, 'flow'); }, mountEpisodes: function (p) { return mount(p, 'episodes'); }, mountArgus: function (p) { return mount(p, 'argus'); }, boot: boot };
  window.PHXEvidenceState = { snapshot: snapshotState, restore: restoreState };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true }); else boot();
}());
