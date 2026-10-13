/* Trader JB — Weekly Flow dashboard (UI contract v1).
 * Standalone: no framework, no network, no storage. Uses window.Chart if the host preloaded it.
 * Public API: window.TraderJB = { mount(root), render(root, report), validate(report), unmount(root) }.
 * All DOM is built with createElement/textContent; no innerHTML anywhere. */
(function () {
  'use strict';

  const MAX_BYTES = 5 * 1024 * 1024, MAX_ROWS = 200, MAX_REPORTS = 12, EOK = 1e8;
  const SANS = "'Pretendard','Apple SD Gothic Neo','Noto Sans KR',system-ui,sans-serif";
  const MONO = "'SF Mono','JetBrains Mono',ui-monospace,Menlo,Consolas,monospace";
  // Korean market convention: up = red, down = blue.
  const C = { navy: '#0b2443', blue: 'rgba(115,153,198,0.85)', up: 'rgba(176,55,43,0.72)', down: 'rgba(47,95,158,0.72)',
    upSoft: 'rgba(176,55,43,0.38)', downSoft: 'rgba(47,95,158,0.38)', grid: 'rgba(11,36,67,0.08)', muted: '#5b6b80' };
  const B64 = /^[A-Za-z0-9+/]+={0,2}$/;
  const STATUS = { candidate: '후보 · 잠정', confirmed: '연결 근거 충족 · 잠정' };
  const REL = { direct: '직접 근거', narrative: '서사적 연관' };
  const CMP = { no_history: '이력 없음', outside_prior_top100: '직전 Top100 미관측', matched: '비교 가능' };
  const FIXED_NOTES = [
    '거래대금 단위는 원(KRW)이며, 표·차트는 억원(1억 = 100,000,000원)으로 표시합니다.',
    '일간 등락(%)은 기준일 하루의 가격 변화이며 주간 수익률이 아닙니다.',
    '거래대금 변화(%)·증감은 같은 종목의 전주 랭킹 스냅샷 대비 값으로, 주가 수익률이나 순매수·자금 유입이 아닙니다.',
    '결측값은 0이 아니라 —로 표시하며, 정렬 시 방향과 무관하게 항상 마지막에 둡니다.'
  ];
  const FEATURES = [
    ['개요 카드', '총 거래대금, 상위 5 집중도, 동일종목 대금 변화, 관측 범위'],
    ['Flow 노트', '본문과 접이식 팩트 노트를 나란히 표시'],
    ['차트 3종', '섹터별 거래대금 · 변화×규모 버블 · 절대 증감 막대 (각각 표 제공)'],
    ['종목 탐색', '섹터·구분·ETF·검색 필터와 결측 후순위 정렬'],
    ['근거 · 테마', '종목별 근거와 참조 팩트 ID, 잠정 테마 후보'],
    ['ENEX 내보내기', '파이프라인이 미리 생성한 Evernote 노트 다운로드']
  ];

  const STATES = new WeakMap();
  let uid = 0;

  /* ---------- helpers ---------- */
  const isNum = v => typeof v === 'number' && Number.isFinite(v);
  const isObj = v => v !== null && typeof v === 'object' && !Array.isArray(v);
  const NF = {};
  const nf = d => NF[d] || (NF[d] = new Intl.NumberFormat('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d }));
  const fmtNum = (v, d, u) => (isNum(v) ? nf(d).format(v) + (u || '') : '—');
  const fmtSigned = (v, d, u) => (isNum(v) ? (v > 0 ? '+' : v < 0 ? '−' : '') + nf(d).format(Math.abs(v)) + (u || '') : '—');
  const fmtEok = v => (isNum(v) ? nf(1).format(v / EOK) : '—');
  const fmtEokSigned = v => (isNum(v) ? fmtSigned(v / EOK, 1, '') : '—');
  const fmtBig = v => (!isNum(v) ? '—' : v >= 1e12 ? nf(2).format(v / 1e12) + '조원' : nf(1).format(v / EOK) + '억원');
  const tone = v => (isNum(v) ? (v > 0 ? ' is-up' : v < 0 ? ' is-down' : '') : ' is-na');
  const short = v => { try { return String(JSON.stringify(v)).slice(0, 40); } catch (e) { return '?'; } };

  function fmtDate(s, withTime) {
    if (typeof s !== 'string' || !s) return '—';
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    const o = { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' };
    if (withTime) Object.assign(o, { hour: '2-digit', minute: '2-digit', hour12: false });
    return new Intl.DateTimeFormat('ko-KR', o).format(d) + (withTime ? ' KST' : '');
  }

  function safeUrl(u) {
    if (typeof u !== 'string' || u.length > 2048) return null;
    try {
      const x = new URL(u);
      return (x.protocol === 'https:' || x.protocol === 'http:') && !x.username && !x.password ? x.href : null;
    } catch (e) { return null; }
  }

  function h(tag, attrs, kids) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const k of Object.keys(attrs)) {
        const v = attrs[k];
        if (v == null || v === false) continue;
        if (k === 'class') el.className = v;
        else el.setAttribute(k, v === true ? '' : String(v));
      }
    }
    add(el, kids);
    return el;
  }
  function add(el, kids) {
    if (kids == null || kids === false) return;
    (Array.isArray(kids) ? kids : [kids]).forEach(c => {
      if (c == null || c === false) return;
      el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
    });
  }
  const dl = pairs => h('dl', { class: 'tjb-dl' }, pairs.flatMap(p => [h('dt', null, p[0]), h('dd', null, p[1])]));
  const secHead = (title, sub) => h('header', { class: 'tjb-sec-h' }, [h('h3', null, title), sub ? h('p', null, sub) : null]);

  const isETF = s => typeof s.security_type === 'string' && /ETF|ETN/i.test(s.security_type);
  const sectorOf = s => s.sector || '미분류';
  const roleOf = s => (isETF(s) ? 'ETF·ETN' : s.role || '미분류');
  const filtersActive = f => !!(f.sector || f.role || f.q.trim() || f.etf !== 'all');
  const firstWeek = r => r.coverage.previous_as_of == null || !isNum(r.coverage.comparison_days) ||
    (isNum(r.coverage.history_weeks) && r.coverage.history_weeks <= 1);

  /* ---------- validation ---------- */
  function validate(r) {
    const errs = [];
    const err = m => { if (errs.length < 40) errs.push(m); };
    if (!isObj(r)) return { ok: false, errors: ['최상위 값이 JSON 객체가 아닙니다.'] };
    const str = (v, p, req) => {
      if (v == null) { if (req) err(`${p}: 필수 문자열이 없습니다.`); }
      else if (typeof v !== 'string') err(`${p}: 문자열이어야 합니다.`);
      else if (v.length > 20000) err(`${p}: 문자열이 너무 깁니다.`);
    };
    const num = (v, p, req, nonneg) => {
      if (v == null) { if (req) err(`${p}: 필수 숫자가 없습니다 (0으로 대체하지 않습니다).`); return; }
      if (!isNum(v)) err(`${p}: 유한한 숫자 또는 null이어야 합니다 (현재 ${short(v)}).`);
      else if (nonneg && v < 0) err(`${p}: 음수일 수 없습니다.`);
    };
    const amt = (v, p) => num(v, p, true, true);
    const arr = (v, p) => {
      if (!Array.isArray(v)) { err(`${p}: 배열이어야 합니다.`); return []; }
      if (v.length > MAX_ROWS) { err(`${p}: 최대 ${MAX_ROWS}행까지 허용됩니다 (현재 ${v.length}).`); return []; }
      return v;
    };
    const strArr = (v, p) => {
      if (v == null) return;
      if (!Array.isArray(v) || v.some(x => typeof x !== 'string')) err(`${p}: 문자열 배열이어야 합니다.`);
      else if (v.length > 500) err(`${p}: 항목이 너무 많습니다.`);
    };
    const items = (list, p, fn) => list.forEach((it, i) => {
      if (!isObj(it)) err(`${p}[${i}]: 객체여야 합니다.`); else fn(it, `${p}[${i}]`);
    });

    if (r.schema_version !== 1) err(`schema_version은 1이어야 합니다 (현재 ${short(r.schema_version)}).`);
    str(r.id, 'id', true);
    if (typeof r.id === 'string' && (!r.id.trim() || r.id.length > 64)) err('id: 1~64자여야 합니다.');
    str(r.title, 'title', true); str(r.as_of, 'as_of', true); str(r.generated_at, 'generated_at');
    str(r.market, 'market'); str(r.currency, 'currency'); str(r.period, 'period');
    if(r.market !== 'KR' || r.currency !== 'KRW' || r.period !== '1w') err('KR / KRW / 1w 관측만 지원합니다.');
    if(!Number.isFinite(Date.parse(r.as_of))) err('as_of: 유효한 기준시각이 필요합니다.');
    if (r.status !== 'partial' && r.status !== 'ready') err(`status는 'partial' 또는 'ready'여야 합니다.`);
    if (r.private_only !== true) err('private_only가 true가 아닙니다 — 비공개 리포트만 불러올 수 있습니다.');

    if (!isObj(r.source)) err('source: 객체가 필요합니다.');
    else ['name', 'url', 'ranking_type', 'snapshot_sha256'].forEach(k => str(r.source[k], 'source.' + k));
    if (!isObj(r.coverage)) err('coverage: 객체가 필요합니다.');
    else {
      ['count', 'limit', 'matched_count', 'comparison_days', 'history_weeks'].forEach(k => num(r.coverage[k], 'coverage.' + k, false, true));
      str(r.coverage.previous_as_of, 'coverage.previous_as_of'); str(r.coverage.scope, 'coverage.scope');
    }
    if (!isObj(r.metrics)) err('metrics: 객체가 필요합니다.');
    else {
      amt(r.metrics.amount, 'metrics.amount');
      num(r.metrics.top5_share_pct, 'metrics.top5_share_pct'); num(r.metrics.matched_change_pct, 'metrics.matched_change_pct');
      num(r.metrics.theme_count, 'metrics.theme_count', false, true);
    }

    const seen = new Set();
    items(arr(r.stocks, 'stocks'), 'stocks', (s, p) => {
      str(s.symbol, p + '.symbol', true); str(s.name, p + '.name', true);
      if (typeof s.symbol === 'string') {
        if (!s.symbol.trim() || s.symbol.length > 24) err(`${p}.symbol: 1~24자여야 합니다.`);
        if (seen.has(s.symbol)) err(`${p}.symbol: 중복 종목코드 ${s.symbol}`);
        seen.add(s.symbol);
      }
      amt(s.amount, p + '.amount');
      ['rank', 'daily_price_change_pct', 'share_pct', 'previous_amount', 'delta_amount', 'amount_change_pct',
        'acceleration_pp', 'share_change_pp', 'rank_change'].forEach(k => num(s[k], `${p}.${k}`));
      ['security_type', 'sector', 'lane', 'role', 'fact_id', 'comparison_status'].forEach(k => str(s[k], `${p}.${k}`));
      strArr(s.themes, p + '.themes'); strArr(s.sector_ids, p + '.sector_ids');
    });
    items(arr(r.sectors, 'sectors'), 'sectors', (s, p) => {
      str(s.id, p + '.id', true); str(s.name, p + '.name', true); amt(s.amount, p + '.amount');
      num(s.member_count, p + '.member_count', false, true); num(s.share_pct, p + '.share_pct'); num(s.amount_change_pct, p + '.amount_change_pct');
      str(s.leader, p + '.leader'); str(s.lane, p + '.lane'); strArr(s.members, p + '.members');
    });
    items(arr(r.themes, 'themes'), 'themes', (t, p) => {
      str(t.id, p + '.id', true); str(t.name, p + '.name', true);
      if (t.status !== 'candidate' && t.status !== 'confirmed') err(`${p}.status: 'candidate' 또는 'confirmed'여야 합니다.`);
      ['lifecycle', 'first_seen', 'rationale'].forEach(k => str(t[k], `${p}.${k}`));
      amt(t.amount, p + '.amount'); num(t.member_count, p + '.member_count', false, true);
      strArr(t.members, p + '.members'); strArr(t.evidence_ids, p + '.evidence_ids');
    });
    items(arr(r.evidence, 'evidence'), 'evidence', (e, p) => {
      str(e.id, p + '.id', true);
      ['date', 'title', 'url', 'source', 'phrase', 'excerpt'].forEach(k => str(e[k], `${p}.${k}`));
      if (e.relation != null && e.relation !== 'direct' && e.relation !== 'narrative') err(`${p}.relation: 'direct' 또는 'narrative'여야 합니다.`);
      strArr(e.symbols, p + '.symbols');
    });
    items(arr(r.article, 'article'), 'article', (a, p) => {
      str(a.heading, p + '.heading'); strArr(a.paragraphs, p + '.paragraphs'); strArr(a.fact_ids, p + '.fact_ids');
    });
    if (!Array.isArray(r.caveats)) err('caveats: 배열이어야 합니다.'); else strArr(r.caveats, 'caveats');
    if (r.methodology != null) {
      if (!isObj(r.methodology)) err('methodology: 객체여야 합니다.');
      else { str(r.methodology.version, 'methodology.version'); str(r.methodology.classification, 'methodology.classification'); strArr(r.methodology.formulas, 'methodology.formulas'); }
    }
    if (r.export != null) {
      if (!isObj(r.export)) err('export: 객체여야 합니다.');
      else {
        str(r.export.enex_filename, 'export.enex_filename');
        const b = r.export.enex_base64;
        if (b != null) {
          const c = typeof b === 'string' ? b.replace(/\s+/g, '') : null;
          if (!c || c.length % 4 || !B64.test(c)) err('export.enex_base64: 올바른 base64 문자열이 아닙니다.');
        }
      }
    }
    return { ok: errs.length === 0, errors: errs };
  }

  /* ---------- lifecycle ---------- */
  function ensure(root) {
    if (!root || root.nodeType !== 1) throw new TypeError('TraderJB: root 요소가 필요합니다.');
    let st = STATES.get(root);
    if (st) return st;
    const ac = new AbortController(), fid = 'tjb-file-' + (++uid);
    st = { root, ac, alive: true, reports: new Map(), report: null, charts: [], filter: null, sort: { key: 'amount', dir: 'desc' },
      selected: null, timer: 0, fid, el: {} };
    STATES.set(root, st);
    const file = h('input', { id: fid, type: 'file', accept: '.json,application/json', multiple: true, class: 'tjb-sr', 'data-act': 'file' });
    const week = h('select', { class: 'tjb-select', 'data-act': 'week' });
    st.el = {
      week,
      weekWrap: h('label', { class: 'tjb-field tjb-week', hidden: true }, [h('span', { class: 'tjb-lbl' }, '주간 선택'), week]),
      exportBtn: h('button', { type: 'button', class: 'tjb-btn', 'data-act': 'export', disabled: true }, 'ENEX 내보내기'),
      meta: h('div', { class: 'tjb-meta' }),
      msg: h('div', { class: 'tjb-msg', hidden: true }),
      body: h('div', { class: 'tjb-body' })
    };
    const wrap = h('div', { class: 'tjb', lang: 'ko' }, [
      h('header', { class: 'tjb-mast' }, [
        h('div', { class: 'tjb-mast-top' }, [h('span', { class: 'tjb-kicker' }, 'TRADER JB'), h('span', { class: 'tjb-priv' }, '비공개 · 로컬 메모리 전용')]),
        h('h2', { class: 'tjb-title' }, 'Weekly Flow'),
        h('p', { class: 'tjb-dek' }, '거래대금 상위 관측집합으로 읽는 주간 흐름 — 정량 대시보드'),
        st.el.meta
      ]),
      h('div', { class: 'tjb-toolbar' }, [
        h('label', { class: 'tjb-btn tjb-btn-primary tjb-file', for: fid }, [file, h('span', null, '리포트 JSON 불러오기')]),
        st.el.weekWrap, st.el.exportBtn
      ]),
      st.el.msg, st.el.body
    ]);
    root.replaceChildren(wrap);
    const sig = { signal: ac.signal };
    wrap.addEventListener('change', e => onChange(st, e), sig);
    wrap.addEventListener('input', e => onInput(st, e), sig);
    wrap.addEventListener('click', e => onClick(st, e), sig);
    renderEmpty(st);
    readInline(st);
    return st;
  }

  function mount(root) { ensure(root); return root; }

  function unmount(root) {
    const st = STATES.get(root);
    if (!st) return;
    destroyCharts(st); clearTimeout(st.timer); st.ac.abort(); st.alive = false;
    STATES.delete(root); root.replaceChildren();
  }

  function render(root, report) {
    const st = ensure(root), v = validate(report);
    if (!v.ok) {
      showMsg(st, 'error', [...v.errors.slice(0, 8), st.report ? '현재 표시 중인 리포트는 그대로 유지됩니다.' : '파이프라인에서 리포트를 다시 생성한 뒤 불러오세요.']);
      return v;
    }
    if (!st.reports.has(report.id) && st.reports.size >= MAX_REPORTS) {
      showMsg(st, 'error', [`세션당 최대 ${MAX_REPORTS}개 주간 리포트까지 보관합니다. 페이지를 새로 고친 뒤 다시 불러오세요.`]);
      return { ok: false, errors: ['too many reports'] };
    }
    st.reports.set(report.id, report);
    showMsg(st, null, []);
    setReport(st, report.id);
    return v;
  }

  function readInline(st) {
    const node = st.root.ownerDocument.getElementById('trader-jb-report');
    if (!node || node.tagName !== 'SCRIPT') return;
    const txt = node.textContent || '';
    if (!txt.trim()) return;
    if (txt.length > MAX_BYTES) { showMsg(st, 'error', ['내장 리포트가 5MB를 초과하여 불러오지 않았습니다.']); return; }
    let data;
    try { data = JSON.parse(txt); } catch (e) { showMsg(st, 'error', ['내장 리포트 JSON 구문 오류입니다.']); return; }
    render(st.root, data);
  }

  async function loadFiles(st, files) {
    const list = Array.from(files || []);
    if (!list.length) return;
    if (list.length > MAX_REPORTS) { showMsg(st, 'error', [`한 번에 최대 ${MAX_REPORTS}개 파일까지 선택할 수 있습니다.`]); return; }
    const errs = [];
    let last = null, n = 0;
    for (const f of list) {
      const tag = String(f.name).slice(0, 80);
      if (f.size > MAX_BYTES) { errs.push(`${tag}: 5MB를 초과합니다.`); continue; }
      let data;
      try { data = JSON.parse(await f.text()); } catch (e) { errs.push(`${tag}: JSON 구문 오류 — 파이프라인 출력 파일인지 확인하세요.`); continue; }
      if (!st.alive) return;
      const v = validate(data);
      if (!v.ok) { errs.push(`${tag}: ${v.errors.slice(0, 4).join(' / ')}${v.errors.length > 4 ? ` 외 ${v.errors.length - 4}건` : ''}`); continue; }
      if (!st.reports.has(data.id) && st.reports.size >= MAX_REPORTS) { errs.push(`${tag}: 세션당 최대 ${MAX_REPORTS}개 리포트까지 보관합니다.`); continue; }
      st.reports.set(data.id, data);
      last = data; n++;
    }
    if (last) setReport(st, last.id);
    if (errs.length) showMsg(st, 'error', [...errs, st.report ? '현재 표시 중인 리포트는 그대로 유지됩니다.' : '스키마를 확인한 뒤 다시 선택하세요.']);
    else if (n) showMsg(st, 'info', [`${n}개 리포트를 이 탭의 메모리에 불러왔습니다. 업로드·저장되지 않습니다. (같은 ID는 새 파일로 대체)`]);
  }

  function setReport(st, id) {
    const r = st.reports.get(id);
    if (!r) return;
    st.report = r; st.selected = null;
    st.filter = { sector: '', role: '', etf: 'all', q: '' };
    st.sort = { key: 'amount', dir: 'desc' };
    buildIndex(st); syncWeeks(st); draw(st);
  }

  function buildIndex(st) {
    const r = st.report, F = new Map(), put = (k, v) => { if (k && !F.has(k)) F.set(k, v); };
    st.bySymbol = new Map(r.stocks.map(s => [s.symbol, s]));
    r.stocks.forEach(s => {
      const v = { kind: '종목', label: `${s.name} (${s.symbol})`, sym: s.symbol,
        detail: `거래대금 ${fmtEok(s.amount)}억원 · 대금 변화 ${fmtSigned(s.amount_change_pct, 1, '%')} · 일간 ${fmtSigned(s.daily_price_change_pct, 2, '%')}` };
      put(s.fact_id, v); put('stock:' + s.symbol, v);
    });
    r.sectors.forEach(x => put('sector:' + x.id, { kind: '섹터', label: x.name,
      detail: `거래대금 ${fmtEok(x.amount)}억원 · ${fmtNum(x.member_count, 0)}종목 · 비중 ${fmtNum(x.share_pct, 1, '%')}` }));
    r.themes.forEach(t => {
      const v = { kind: '테마', label: t.name, detail: `${STATUS[t.status]} · ${t.lifecycle || '—'} · ${fmtNum(t.member_count, 0)}종목` };
      put('theme:' + t.id, v); put(t.id, v);
    });
    r.evidence.forEach(e => {
      const v = { kind: '근거', label: e.title || e.id, detail: `${e.date || '날짜 없음'} · ${e.source || '출처 미상'}` };
      put('evidence:' + e.id, v); put(e.id, v);
    });
    st.facts = F;
  }

  function syncWeeks(st) {
    const ids = [...st.reports.keys()].sort().reverse();
    st.el.week.replaceChildren(...ids.map(id =>
      h('option', { value: id }, id + (st.reports.get(id).status === 'partial' ? ' (부분)' : ''))));
    st.el.week.value = st.report.id;
    st.el.weekWrap.hidden = ids.length < 2;
  }

  function destroyCharts(st) {
    st.charts.forEach(c => { try { c.destroy(); } catch (e) { /* ignore */ } });
    st.charts = [];
  }

  /* ---------- events ---------- */
  function onChange(st, e) {
    const t = e.target, act = t.getAttribute && t.getAttribute('data-act');
    if (act === 'file') { const files = Array.from(t.files || []); t.value = ''; loadFiles(st, files); }
    else if (act === 'week') { showMsg(st, null, []); setReport(st, t.value); }
    else if (act === 'f-sector' || act === 'f-role' || act === 'f-etf') { st.filter[act.slice(2)] = t.value; drawScoped(st); }
  }

  function onInput(st, e) {
    if (!e.target.getAttribute || e.target.getAttribute('data-act') !== 'f-q') return;
    st.filter.q = String(e.target.value).slice(0, 60);
    clearTimeout(st.timer);
    st.timer = setTimeout(() => { if (st.alive) drawScoped(st); }, 150);
  }

  function onClick(st, e) {
    const t = e.target instanceof Element ? e.target.closest('[data-act]') : null;
    if (!t || !st.root.contains(t)) return;
    const act = t.getAttribute('data-act');
    if (act === 'export') exportEnex(st);
    else if (act === 'dismiss') showMsg(st, null, []);
    else if (act === 'pick') select(st, t.getAttribute('data-symbol'), t.hasAttribute('data-jump'));
    else if (act === 'sort') {
      const k = t.getAttribute('data-key');
      st.sort = st.sort.key === k ? { key: k, dir: st.sort.dir === 'desc' ? 'asc' : 'desc' } : { key: k, dir: 'desc' };
      drawScoped(st, `[data-act="sort"][data-key="${k}"]`);
    } else if (act === 'reset') {
      st.filter = { sector: '', role: '', etf: 'all', q: '' };
      st.el.filters.querySelectorAll('[data-act^="f-"]').forEach(x => { x.value = x.getAttribute('data-act') === 'f-etf' ? 'all' : ''; });
      drawScoped(st);
    }
  }

  function select(st, sym, jump) {
    if (!st.report || !st.bySymbol.has(sym)) return;
    st.selected = sym;
    renderDetail(st);
    st.el.scoped.querySelectorAll('tr[data-row]').forEach(tr => {
      const on = tr.getAttribute('data-row') === sym, b = tr.querySelector('[data-act="pick"]');
      tr.classList.toggle('is-sel', on);
      if (b) b.setAttribute('aria-pressed', String(on));
    });
    if (jump && st.el.detail) {
      const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      st.el.detail.scrollIntoView({ block: 'nearest', behavior: reduce ? 'auto' : 'smooth' });
      const hd = st.el.detail.querySelector('.tjb-detail-h');
      if (hd) hd.focus({ preventScroll: true });
    }
  }

  function showMsg(st, kind, lines) {
    const m = st.el.msg;
    m.replaceChildren();
    m.hidden = !kind || !lines.length;
    if (m.hidden) return;
    m.className = 'tjb-msg is-' + kind;
    m.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    m.append(
      h('strong', null, kind === 'error' ? '처리하지 못한 항목이 있습니다' : '알림'),
      h('ul', null, lines.slice(0, 10).map(l => h('li', null, l))),
      h('button', { type: 'button', class: 'tjb-x', 'data-act': 'dismiss', 'aria-label': '알림 닫기' }, '×'));
  }

  /* ---------- export ---------- */
  function safeName(name, id) {
    let n = typeof name === 'string' ? name.split(/[\\/]/).pop() : '';
    n = n.replace(/[^A-Za-z0-9._-]/g, '_').replace(/^[._]+/, '').slice(0, 100);
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]*\.enex$/i.test(n)) n = 'trader-jb-' + String(id).replace(/[^A-Za-z0-9-]/g, '').slice(0, 40) + '.enex';
    return n;
  }

  function exportEnex(st) {
    const r = st.report, ex = r && isObj(r.export) ? r.export : null;
    if (!ex || typeof ex.enex_base64 !== 'string' || !ex.enex_base64) { showMsg(st, 'error', ['이 리포트에는 ENEX 내보내기 데이터가 없습니다.']); return; }
    let bytes;
    try {
      const b64 = ex.enex_base64.replace(/\s+/g, '');
      if (b64.length % 4 || !B64.test(b64)) throw new Error('b64');
      const bin = atob(b64);
      bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    } catch (e) {
      showMsg(st, 'error', ['ENEX 데이터(base64)를 해석할 수 없습니다. 파이프라인에서 리포트를 다시 생성하세요.']); return;
    }
    const head = new TextDecoder('utf-8').decode(bytes.subarray(0, 4096));
    if (!/<en-export[\s>]/.test(head)) { showMsg(st, 'error', ['ENEX 형식(<en-export>)이 아닙니다. 내보내기를 중단했습니다.']); return; }
    const name = safeName(ex.enex_filename, r.id);
    const url = URL.createObjectURL(new Blob([bytes], { type: 'application/xml' }));
    const a = h('a', { href: url, download: name, hidden: true });
    st.root.firstChild.appendChild(a);
    a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    showMsg(st, 'info', [`${name} 파일을 내려받았습니다. Evernote의 가져오기 기능으로 열 수 있습니다.`]);
  }

  /* ---------- views ---------- */
  function renderEmpty(st) {
    st.el.meta.replaceChildren(h('p', { class: 'tjb-rtitle tjb-muted' }, '불러온 리포트 없음'));
    st.el.body.replaceChildren(h('section', { class: 'tjb-empty' }, [
      h('h3', null, '주간 리포트 JSON을 선택하세요'),
      h('p', null, '수집 파이프라인이 만든 비공개 리포트(.json)를 불러오면 대시보드가 구성됩니다. 여러 주 파일을 함께 선택하면 주간을 전환할 수 있습니다.'),
      h('ul', { class: 'tjb-feat' }, FEATURES.map(f => h('li', null, [h('strong', null, f[0]), h('span', null, f[1])]))),
      h('label', { class: 'tjb-btn tjb-btn-primary', for: st.fid }, '파일 선택'),
      h('p', { class: 'tjb-privacy' }, '비공개 데이터: 파일은 이 탭의 메모리에서만 읽힙니다. 업로드·브라우저 저장·외부 전송이 없으며, 탭을 닫으면 사라집니다.')
    ]));
  }

  function renderMeta(st) {
    const r = st.report, mi = (k, v) => h('span', { class: 'tjb-mi' }, [h('span', { class: 'tjb-lbl' }, k), ' ', v]);
    st.el.meta.replaceChildren(
      h('p', { class: 'tjb-rtitle' }, r.title),
      h('div', { class: 'tjb-metarow' }, [
        h('span', { class: 'tjb-tag ' + (r.status === 'ready' ? 'is-ok' : 'is-cand') }, r.status === 'ready' ? '완료' : '부분 데이터'),
        mi('기준', fmtDate(r.as_of, true)), mi('수집', fmtDate(r.generated_at, true)),
        mi('시장', `${r.market || '—'} · ${r.period === '1w' ? '주간' : r.period || '—'}`), mi('ID', r.id)
      ]));
  }

  function draw(st) {
    destroyCharts(st);
    const r = st.report;
    renderMeta(st);
    st.el.exportBtn.disabled = !(isObj(r.export) && typeof r.export.enex_base64 === 'string' && r.export.enex_base64.length > 0);
    const banners = [];
    if (firstWeek(r)) banners.push(h('p', { class: 'tjb-banner' }, [h('strong', null, '첫 주 리포트 '),
      '— 비교할 전주 스냅샷이 없습니다. 증감·변화율·가속 지표는 0이 아닌 —(결측)으로 표시되며, 버블·증감 차트는 비어 있을 수 있습니다.']));
    if (r.status === 'partial') banners.push(h('p', { class: 'tjb-banner is-warn' }, [h('strong', null, '부분 리포트 '), '— 일부 데이터가 수집 중이거나 누락되었습니다. 결론 전에 유의사항을 확인하세요.']));
    st.el.scoped = h('div', { class: 'tjb-scoped' });
    st.el.filters = filterBar(st);
    st.el.body.replaceChildren(...[
      banners.length ? h('div', { class: 'tjb-banners' }, banners) : null,
      overview(r),
      h('section', { class: 'tjb-sec' }, [secHead('종목 탐색', '필터는 아래 차트·표·건수에만 적용됩니다'), st.el.filters, st.el.scoped]),
      articleSec(st),
      themesSec(st), notesSec(r)].filter(Boolean));
    drawScoped(st);
  }

  function overview(r) {
    const c = r.coverage, m = r.metrics, fw = firstWeek(r);
    const card = (k, v, sub, cls) => h('div', { class: 'tjb-card' + (cls || '') }, [h('div', { class: 'tjb-card-k' }, k), h('div', { class: 'tjb-card-v' }, v), h('div', { class: 'tjb-card-s' }, sub)]);
    return h('section', { class: 'tjb-sec' }, [secHead('개요', '전체 관측집합 기준 · 필터와 무관'), h('div', { class: 'tjb-cards' }, [
      card('총 거래대금', fmtBig(m.amount), `관측 ${fmtNum(c.count, 0)}종목 합계 · ${r.currency || 'KRW'}`, ' is-lead'),
      card('상위 5 집중도', fmtNum(m.top5_share_pct, 1, '%'), '관측 거래대금 중 상위 5종목 비중'),
      card('동일종목 대금 변화', fmtSigned(m.matched_change_pct, 1, '%'),
        isNum(m.matched_change_pct) ? `전주와 겹치는 ${fmtNum(c.matched_count, 0)}종목 · 순매수 아님` : '전주 비교 불가 (결측)', tone(m.matched_change_pct)),
      card('테마 후보', fmtNum(m.theme_count, 0, '개'), '휴리스틱 분류 · 확정 아님'),
      card('관측 범위', `${fmtNum(c.count, 0)} / ${fmtNum(c.limit, 0)}`, c.scope || '—'),
      card('비교 기준', c.previous_as_of ? fmtDate(c.previous_as_of) : '없음',
        (fw ? '첫 관측' : `${fmtNum(c.comparison_days, 0)}일 간격`) + ` · 계산에 사용한 관측 ${fmtNum(c.history_weeks, 0)}회`)
    ])]);
  }

  function factLi(st, id) {
    const f = st.facts.get(id);
    if (!f) return h('li', { class: 'tjb-fact is-miss' }, [h('code', null, id), h('div', { class: 'tjb-fact-d' }, '리포트에서 찾을 수 없는 팩트 ID')]);
    return h('li', { class: 'tjb-fact' }, [
      h('span', { class: 'tjb-tag' }, f.kind), ' ',
      f.sym ? h('button', { type: 'button', class: 'tjb-link', 'data-act': 'pick', 'data-symbol': f.sym, 'data-jump': true }, f.label) : h('strong', null, f.label),
      h('div', { class: 'tjb-fact-d' }, f.detail), h('code', null, id)]);
  }

  function articleSec(st) {
    const r = st.report;
    if (!r.article.length) return null;
    return h('section', { class: 'tjb-sec' }, [secHead('Flow 노트', '본문 옆(모바일: 아래)의 접이식 노트에서 근거 팩트를 확인하세요'), h('div', { class: 'tjb-article' }, [
      h('article', { class: 'tjb-prose' }, r.article.map((a, i) => h('section', { class: 'tjb-art' }, [
        h('h4', null, [h('span', { class: 'tjb-mark' }, i + 1), a.heading || `섹션 ${i + 1}`]),
        ...(a.paragraphs || []).map(p => h('p', null, p))]))),
      h('aside', { class: 'tjb-notes', 'aria-label': '팩트 노트' }, r.article.map((a, i) => {
        const ids = a.fact_ids || [];
        return h('details', { class: 'tjb-note', open: i === 0 }, [
          h('summary', null, [h('span', { class: 'tjb-mark' }, i + 1), a.heading || `섹션 ${i + 1}`, h('span', { class: 'tjb-cnt' }, `팩트 ${ids.length}`)]),
          ids.length ? h('ul', null, ids.map(id => factLi(st, id))) : h('p', { class: 'tjb-muted' }, '연결된 팩트 없음')]);
      }))])]);
  }

  function filterBar(st) {
    const r = st.report;
    const uniq = a => [...new Set(a)].sort((x, y) => x.localeCompare(y, 'ko'));
    const sel = (act, label, opts) => h('label', { class: 'tjb-field' }, [h('span', { class: 'tjb-lbl' }, label),
      h('select', { class: 'tjb-select', 'data-act': act }, opts.map(o => h('option', { value: o[0] }, o[1])))]);
    st.el.count = h('p', { class: 'tjb-count', 'aria-live': 'polite' });
    return h('div', { class: 'tjb-filters', role: 'search', 'aria-label': '종목 필터' }, [
      sel('f-sector', '섹터', [['', '전체 섹터'], ...uniq(r.stocks.map(sectorOf)).map(s => [s, s])]),
      sel('f-role', '구분', [['', '전체 구분'], ...uniq(r.stocks.map(roleOf)).map(s => [s, s])]),
      sel('f-etf', 'ETF·ETN', [['all', '포함'], ['exclude', '제외'], ['only', 'ETF·ETN만']]),
      h('label', { class: 'tjb-field tjb-grow' }, [h('span', { class: 'tjb-lbl' }, '검색'),
        h('input', { type: 'search', class: 'tjb-input', 'data-act': 'f-q', placeholder: '종목명 또는 코드', maxlength: 60, autocomplete: 'off' })]),
      h('button', { type: 'button', class: 'tjb-btn tjb-btn-ghost', 'data-act': 'reset' }, '필터 초기화'),
      st.el.count]);
  }

  function filtered(st) {
    const f = st.filter, q = f.q.trim().toLowerCase();
    return st.report.stocks.filter(s => (!f.sector || sectorOf(s) === f.sector) && (!f.role || roleOf(s) === f.role) &&
      (f.etf === 'all' || (f.etf === 'only') === isETF(s)) &&
      (!q || String(s.name).toLowerCase().includes(q) || s.symbol.toLowerCase().includes(q)));
  }

  function drawScoped(st, focusSel) {
    destroyCharts(st);
    const rows = filtered(st), total = st.report.stocks.length, jobs = [];
    st.el.count.textContent = filtersActive(st.filter) ? `필터 적용: ${rows.length} / 전체 ${total}종목` : `전체 ${total}종목`;
    st.el.scoped.replaceChildren(chartsBlock(st, rows, jobs), tableBlock(st, rows));
    jobs.forEach(fn => fn());
    if (focusSel) { const f = st.el.scoped.querySelector(focusSel); if (f) f.focus(); }
  }

  /* ---------- charts ---------- */
  function opts(xt, yt, x) {
    const ax = t => ({ title: { display: !!t, text: t, color: C.muted, font: { family: SANS, size: 11 } }, grid: { color: C.grid },
      border: { display: false }, ticks: { color: C.muted, font: { family: MONO, size: 10 } } });
    const o = { responsive: true, maintainAspectRatio: false, animation: false, indexAxis: x.indexAxis || 'x', onClick: x.onClick,
      plugins: { legend: { display: false }, tooltip: { backgroundColor: C.navy, titleFont: { family: SANS }, bodyFont: { family: MONO }, callbacks: { label: x.tip } } },
      scales: { x: ax(xt), y: ax(yt) } };
    if (o.indexAxis === 'y') o.scales.y.ticks.font.family = SANS;
    // Bar totals retain a zero baseline; scatter levels use their own live range.
    if (o.indexAxis === 'y') o.scales.x.beginAtZero = x.zeroBaseline === true;
    else o.scales.y.beginAtZero = x.zeroBaseline === true;
    return o;
  }

  function makeChart(st, canvas, cfg) {
    try { st.charts.push(new window.Chart(canvas, cfg)); }
    catch (e) { canvas.parentNode.replaceWith(h('p', { class: 'tjb-empty-chart' }, '차트를 그리지 못했습니다. 아래 표를 확인하세요.')); }
  }

  function simpleTable(caption, heads, rows, numCols) {
    const cls = i => (numCols.includes(i) ? 'tjb-n' : null);
    return h('div', { class: 'tjb-tscroll', tabindex: 0, role: 'region', 'aria-label': caption }, h('table', { class: 'tjb-table tjb-table-s' }, [
      h('caption', { class: 'tjb-sr' }, caption),
      h('thead', null, h('tr', null, heads.map((x, i) => h('th', { scope: 'col', class: cls(i) }, x)))),
      h('tbody', null, rows.length ? rows.map(r => h('tr', null, r.map((c, i) => h(i ? 'td' : 'th', { scope: i ? null : 'row', class: cls(i) }, c == null ? '—' : c))))
        : h('tr', null, h('td', { colspan: heads.length, class: 'tjb-muted' }, '표시할 데이터가 없습니다.')))]));
  }

  function panel(st, jobs, p) {
    const hasChart = typeof window.Chart === 'function', body = [];
    if (p.empty) body.push(h('p', { class: 'tjb-empty-chart' }, p.empty));
    else if (hasChart) {
      const cv = h('canvas', { role: 'img', 'aria-label': `${p.title} 차트. 같은 데이터가 아래 표에 있습니다.` });
      const box = h('div', { class: 'tjb-chart-box' }, cv);
      box.style.height = p.height + 'px';
      jobs.push(() => makeChart(st, cv, p.cfg()));
      body.push(box);
    }
    return h('section', { class: 'tjb-panel', 'aria-label': p.title }, [
      h('header', { class: 'tjb-panel-h' }, [h('h4', null, p.title), h('p', null, p.sub)]), ...body,
      h('details', { class: 'tjb-dt', open: !hasChart || !!p.empty }, [h('summary', null, '표로 보기'), p.table])]);
  }

  function sectorRows(st, rows) {
    if (!filtersActive(st.filter) && st.report.sectors.length) {
      return st.report.sectors.map(s => ({ name: s.name, amount: s.amount, n: s.member_count, share: s.share_pct, chg: s.amount_change_pct, leader: s.leader }))
        .sort((a, b) => b.amount - a.amount);
    }
    const m = new Map();
    rows.forEach(s => {
      const k = sectorOf(s), o = m.get(k) || { name: k, amount: 0, n: 0, share: null, chg: null, leader: null, top: -1 };
      o.amount += s.amount; o.n += 1;
      if (s.amount > o.top) { o.top = s.amount; o.leader = s.name; }
      m.set(k, o);
    });
    return [...m.values()].sort((a, b) => b.amount - a.amount);
  }

  function chartsBlock(st, rows, jobs) {
    const active = filtersActive(st.filter), none = '해당 조건의 종목이 없습니다.';
    const sec = sectorRows(st, rows), secTop = sec.slice(0, 15);
    const pts = rows.filter(s => isNum(s.amount_change_pct)), miss = rows.length - pts.length;
    const maxA = Math.max(1, ...pts.map(s => s.amount));
    const dRows = rows.filter(s => isNum(s.delta_amount)).sort((a, b) => Math.abs(b.delta_amount) - Math.abs(a.delta_amount));
    const dTop = dRows.slice(0, 20), dMiss = rows.length - dRows.length;
    const pick = list => (evt, els) => { if (els && els.length && list[els[0].index]) select(st, list[els[0].index].symbol, true); };
    const kids = [];
    if (typeof window.Chart !== 'function') kids.push(h('p', { class: 'tjb-banner is-warn tjb-span' }, '차트 라이브러리(Chart.js)를 찾을 수 없어 동일한 내용을 표로 표시합니다.'));
    kids.push(panel(st, jobs, {
      title: '섹터별 거래대금',
      sub: (active ? '필터 반영 · ' : '') + '종목당 주 섹터 1개 귀속 합산(중복 없음) · 단위 억원' + (sec.length > 15 ? ` · 상위 15개 (표: ${sec.length}개)` : ''),
      height: Math.max(160, secTop.length * 24 + 48), empty: sec.length ? null : none,
      table: simpleTable('섹터별 거래대금 표', ['섹터', '거래대금(억원)', '종목 수', '비중(%)', '대금 변화(%)', '대표 종목'],
        sec.map(s => [s.name, fmtEok(s.amount), fmtNum(s.n, 0), fmtNum(s.share, 1), fmtSigned(s.chg, 1), s.leader]), [1, 2, 3, 4]),
      cfg: () => ({ type: 'bar', data: { labels: secTop.map(s => s.name),
        datasets: [{ data: secTop.map(s => s.amount / EOK), backgroundColor: C.blue, hoverBackgroundColor: C.navy, borderRadius: 2, maxBarThickness: 16 }] },
        options: opts('거래대금 (억원)', '', { indexAxis: 'y', zeroBaseline: true, tip: c => ` ${fmtNum(c.parsed.x, 1)}억원` }) })
    }));
    kids.push(panel(st, jobs, {
      title: '거래대금 변화 × 규모',
      sub: `x = 전주 동일 종목 대비 거래대금 변화(%) · y = 거래대금(억원) · 원 면적 ∝ 거래대금 · 비교 불가 ${miss}종목 제외`,
      height: 320,
      empty: !rows.length ? none : pts.length ? null : `전주 비교값이 있는 종목이 없습니다 (${miss}종목 제외). 첫 주이거나 신규 진입 종목만 있는 경우이며, 다음 주 리포트부터 표시됩니다.`,
      table: simpleTable('거래대금 변화 표', ['종목', '대금 변화(%)', '거래대금(억원)'],
        pts.slice().sort((a, b) => b.amount_change_pct - a.amount_change_pct).map(s => [s.name, fmtSigned(s.amount_change_pct, 1), fmtEok(s.amount)]), [1, 2]),
      cfg: () => ({ type: 'bubble', data: { datasets: [{
        data: pts.map(s => ({ x: s.amount_change_pct, y: s.amount / EOK, r: 20 * Math.sqrt(s.amount / maxA), name: s.name })),
        backgroundColor: pts.map(s => (s.amount_change_pct < 0 ? C.downSoft : C.upSoft)),
        borderColor: pts.map(s => (s.amount_change_pct < 0 ? C.down : C.up)), borderWidth: 1 }] },
        options: opts('거래대금 변화 (%)', '거래대금 (억원)', { onClick: pick(pts),
          tip: c => ` ${c.raw.name} · ${fmtSigned(c.raw.x, 1, '%')} · ${fmtNum(c.raw.y, 1)}억원` }) })
    }));
    kids.push(panel(st, jobs, {
      title: '거래대금 절대 증감',
      sub: `전주 동일 종목 대비 · 단위 억원 · 순매수 아님 · 절대값 상위 ${dTop.length}개 · 비교 불가 ${dMiss}종목 제외`,
      height: Math.max(160, dTop.length * 22 + 48),
      empty: !rows.length ? none : dRows.length ? null : `전주 거래대금이 있는 종목이 없어 증감을 계산할 수 없습니다 (${dMiss}종목). 0으로 대체하지 않습니다.`,
      table: simpleTable('거래대금 증감 표', ['종목', '증감(억원)', '전주(억원)', '금주(억원)'],
        dRows.map(s => [s.name, fmtEokSigned(s.delta_amount), fmtEok(s.previous_amount), fmtEok(s.amount)]), [1, 2, 3]),
      cfg: () => ({ type: 'bar', data: { labels: dTop.map(s => s.name), datasets: [{
        data: dTop.map(s => s.delta_amount / EOK), backgroundColor: dTop.map(s => (s.delta_amount < 0 ? C.down : C.up)), borderRadius: 2, maxBarThickness: 14 }] },
        options: opts('증감 (억원)', '', { indexAxis: 'y', zeroBaseline: true, onClick: pick(dTop), tip: c => ` ${fmtSigned(c.parsed.x, 1, '억원')}` }) })
    }));
    return h('div', { class: 'tjb-charts' }, kids);
  }

  /* ---------- table + detail ---------- */
  const COLS = [
    { key: 'name', label: '종목' },
    { key: 'rank', label: '순위', n: 1, sort: 1, fmt: s => fmtNum(s.rank, 0) },
    { key: 'sector', label: '섹터', fmt: sectorOf },
    { key: 'role', label: '구분', fmt: roleOf },
    { key: 'amount', label: '거래대금', unit: '억원', n: 1, sort: 1, fmt: s => fmtEok(s.amount) },
    { key: 'share_pct', label: '비중', unit: '%', n: 1, sort: 1, fmt: s => fmtNum(s.share_pct, 2) },
    { key: 'delta_amount', label: '증감', unit: '억원', n: 1, sort: 1, sign: 1, fmt: s => fmtEokSigned(s.delta_amount) },
    { key: 'amount_change_pct', label: '대금 변화', unit: '%', n: 1, sort: 1, sign: 1, fmt: s => fmtSigned(s.amount_change_pct, 1) },
    { key: 'acceleration_pp', label: '가속', unit: '%p', n: 1, sort: 1, sign: 1, fmt: s => fmtSigned(s.acceleration_pp, 1) },
    { key: 'daily_price_change_pct', label: '일간 등락', unit: '%', n: 1, sort: 1, sign: 1, fmt: s => fmtSigned(s.daily_price_change_pct, 2) },
    { key: 'comparison_status', label: '비교', fmt: s => CMP[s.comparison_status] || s.comparison_status || '—' }
  ];

  function sortRows(rows, key, dir) {
    return rows.slice().sort((a, b) => {
      const x = a[key], y = b[key], xn = isNum(x), yn = isNum(y);
      if (!xn || !yn) return xn === yn ? 0 : xn ? -1 : 1; // nulls last regardless of direction
      return dir === 'asc' ? x - y : y - x;
    });
  }

  function tableBlock(st, rows) {
    const s0 = st.sort;
    const head = COLS.map(c => {
      const on = s0.key === c.key, lbl = [c.label, c.unit ? h('span', { class: 'tjb-unit' }, c.unit) : null];
      return h('th', { scope: 'col', class: (c.n ? 'tjb-n' : '') + (c.key === 'name' ? ' tjb-stick' : ''),
        'aria-sort': c.sort ? (on ? (s0.dir === 'asc' ? 'ascending' : 'descending') : 'none') : null },
      c.sort ? h('button', { type: 'button', class: 'tjb-sort' + (on ? ' is-on' : ''), 'data-act': 'sort', 'data-key': c.key },
        [...lbl, h('span', { class: 'tjb-arrow', 'aria-hidden': 'true' }, on ? (s0.dir === 'asc' ? '▲' : '▼') : '↕')]) : lbl);
    });
    const body = sortRows(rows, s0.key, s0.dir).map(s => h('tr', { 'data-row': s.symbol, class: s.symbol === st.selected ? 'is-sel' : null },
      COLS.map(c => c.key === 'name'
        ? h('th', { scope: 'row', class: 'tjb-stick' }, h('button', { type: 'button', class: 'tjb-pick', 'data-act': 'pick', 'data-symbol': s.symbol,
          'aria-pressed': String(s.symbol === st.selected) }, [h('span', { class: 'tjb-pname' }, s.name), h('span', { class: 'tjb-code' }, s.symbol),
          isETF(s) ? h('span', { class: 'tjb-tag is-etf' }, 'ETF·ETN') : null]))
        : h('td', { class: c.n ? 'tjb-n' + (c.sign ? tone(s[c.key]) : '') : null }, c.fmt(s)))));
    st.el.detail = h('aside', { class: 'tjb-detail', 'aria-live': 'polite', 'aria-label': '선택 종목 상세' });
    renderDetail(st);
    return h('div', { class: 'tjb-explore' }, [
      h('div', { class: 'tjb-tablewrap' }, [
        h('div', { class: 'tjb-tscroll tjb-tmain', tabindex: 0, role: 'region', 'aria-label': '종목 표 (가로 스크롤 가능)' }, h('table', { class: 'tjb-table' }, [
          h('caption', { class: 'tjb-sr' }, '종목별 거래대금 표. 열 머리글 버튼으로 정렬하며 결측값은 항상 마지막입니다. 종목명 버튼을 누르면 상세가 표시됩니다.'),
          h('thead', null, h('tr', null, head)),
          h('tbody', null, body.length ? body : h('tr', null, h('td', { colspan: COLS.length, class: 'tjb-muted' }, '조건에 맞는 종목이 없습니다.')))])),
        h('p', { class: 'tjb-legend' }, '거래대금·증감 단위 억원 · 대금 변화는 전주 동일 종목 대비(순매수 아님) · 일간 등락은 하루 기준 · — = 결측')]),
      st.el.detail]);
  }

  function evItem(ev) {
    const u = safeUrl(ev.url);
    return h('li', { class: 'tjb-ev' }, [
      h('div', { class: 'tjb-ev-meta' }, [h('span', { class: 'tjb-tag ' + (ev.relation === 'direct' ? 'is-ok' : 'is-cand') }, REL[ev.relation] || '관계 미상'),
        ' ', ev.date || '날짜 없음', ev.source ? ' · ' + ev.source : null]),
      h('div', { class: 'tjb-ev-title' }, u
        ? h('a', { href: u, target: '_blank', rel: 'noopener noreferrer', referrerpolicy: 'no-referrer' },
          [ev.title || u, h('span', { class: 'tjb-sr' }, ' (외부 사이트, 새 창)'), h('span', { 'aria-hidden': 'true' }, ' ↗')])
        : [ev.title || '제목 없음', ev.url ? h('span', { class: 'tjb-muted' }, ' (허용되지 않은 링크 형식)') : null]),
      ev.phrase ? h('div', { class: 'tjb-ev-phrase' }, ev.phrase) : null,
      ev.excerpt ? h('blockquote', { class: 'tjb-ev-ex' }, ev.excerpt) : null,
      h('code', { class: 'tjb-ev-id' }, ev.id)]);
  }

  function renderDetail(st) {
    const box = st.el.detail;
    if (!box) return;
    const s = st.selected ? st.bySymbol.get(st.selected) : null;
    if (!s) { box.replaceChildren(h('p', { class: 'tjb-muted' }, '표의 종목명이나 차트 요소를 선택하면 근거 자료와 참조 팩트 ID가 여기에 표시됩니다.')); return; }
    const ev = st.report.evidence.filter(e => Array.isArray(e.symbols) && e.symbols.includes(s.symbol));
    const withU = (v, u) => (v === '—' ? v : v + u);
    box.replaceChildren(
      h('h4', { class: 'tjb-detail-h', tabindex: -1 }, [s.name, ' ', h('span', { class: 'tjb-code' }, s.symbol)]),
      dl([
        ['참조 팩트 ID', h('code', null, s.fact_id || '—')], ['증권 유형', s.security_type || '—'], ['섹터', sectorOf(s)],
        ['레인', s.lane || '—'], ['구분', roleOf(s)], ['테마', s.themes && s.themes.length ? s.themes.join(', ') : '—'],
        ['거래대금', withU(fmtEok(s.amount), '억원')], ['전주 거래대금', withU(fmtEok(s.previous_amount), '억원')],
        ['증감', withU(fmtEokSigned(s.delta_amount), '억원')], ['대금 변화', fmtSigned(s.amount_change_pct, 1, '%')],
        ['가속', fmtSigned(s.acceleration_pp, 1, '%p')], ['비중', fmtNum(s.share_pct, 2, '%')], ['비중 변화', fmtSigned(s.share_change_pp, 2, '%p')],
        ['순위 변화(원자료)', fmtSigned(s.rank_change, 0, '')], ['일간 등락', withU(fmtSigned(s.daily_price_change_pct, 2, '%'), ' (하루 기준)')],
        ['비교 상태', CMP[s.comparison_status] || s.comparison_status || '—']
      ]),
      isETF(s) ? h('p', { class: 'tjb-note-s' }, 'ETF·ETN은 Alpha 후보 분류에서 제외하며 원자료의 역할 표기도 사용하지 않습니다.') : null,
      s.comparison_status === 'outside_prior_top100' ? h('p', { class: 'tjb-note-s' }, '상위100 신규 진입은 관측집합 변화일 뿐, 새로운 경제 테마를 뜻하지 않습니다.') : null,
      h('h5', null, `근거 ${ev.length}건`),
      ev.length ? h('ul', { class: 'tjb-evlist' }, ev.map(evItem)) : h('p', { class: 'tjb-muted' }, '이 종목에 연결된 근거가 없습니다.'));
  }

  /* ---------- themes + notes ---------- */
  function themesSec(st) {
    const r = st.report, evm = new Map(r.evidence.map(e => [e.id, e]));
    return h('section', { class: 'tjb-sec' }, [secHead('테마', '후보는 잠정 분류입니다 · 상위100 신규 진입 ≠ 새로운 경제 테마'),
      r.themes.length ? h('div', { class: 'tjb-themes' }, r.themes.map(t => {
        const ids = t.evidence_ids || [], ev = ids.map(id => evm.get(id)).filter(Boolean), lost = ids.length - ev.length;
        return h('article', { class: 'tjb-theme' + (t.status === 'confirmed' ? ' is-conf' : '') }, [
          h('header', null, [h('h4', null, t.name), h('span', { class: 'tjb-tag ' + (t.status === 'confirmed' ? 'is-ok' : 'is-cand') }, STATUS[t.status])]),
          dl([['단계', t.lifecycle || '—'], ['최초 관측', t.first_seen || '—'], ['거래대금', fmtEok(t.amount) + '억원'], ['종목 수', fmtNum(t.member_count, 0)]]),
          (t.members || []).length ? h('div', { class: 'tjb-members' }, t.members.map(sym => {
            const s = st.bySymbol.get(sym);
            return s ? h('button', { type: 'button', class: 'tjb-chip', 'data-act': 'pick', 'data-symbol': sym, 'data-jump': true }, s.name) : h('code', { class: 'tjb-chip' }, sym);
          })) : null,
          t.rationale ? h('p', { class: 'tjb-theme-r' }, t.rationale) : null,
          h('details', { class: 'tjb-dt' }, [h('summary', null, `근거 ${ev.length}건` + (lost ? ` · 찾을 수 없는 ID ${lost}건` : '')),
            ev.length ? h('ul', { class: 'tjb-evlist' }, ev.map(evItem)) : h('p', { class: 'tjb-muted' }, '연결된 근거 없음 — 확인 전까지 후보로만 보세요.')])]);
      })) : h('p', { class: 'tjb-muted' }, '이번 리포트에는 테마 후보가 없습니다.')]);
  }

  function notesSec(r) {
    const src = r.source, su = safeUrl(src.url), m = isObj(r.methodology) ? r.methodology : {};
    return h('section', { class: 'tjb-sec tjb-fine' }, [secHead('유의사항 · 방법론', '해석 전에 확인하세요'), h('div', { class: 'tjb-cols' }, [
      h('div', null, [h('h4', null, '유의사항'), r.caveats.length ? h('ul', { class: 'tjb-caveats' }, r.caveats.map(c => h('li', null, c))) : h('p', { class: 'tjb-muted' }, '리포트에 기재된 유의사항 없음'),
        h('h4', null, '단위 · 표기'), h('ul', { class: 'tjb-caveats' }, FIXED_NOTES.map(c => h('li', null, c)))]),
      h('div', null, [h('h4', null, '방법론'), dl([['버전', m.version || '—'], ['분류', m.classification || '—']]),
        (m.formulas || []).length ? h('ul', { class: 'tjb-formulas' }, m.formulas.map(f => h('li', null, h('code', null, f)))) : null]),
      h('div', null, [h('h4', null, '데이터 출처'), dl([
        ['출처', su ? h('a', { href: su, target: '_blank', rel: 'noopener noreferrer', referrerpolicy: 'no-referrer' }, [src.name || su, h('span', { 'aria-hidden': 'true' }, ' ↗')]) : src.name || '—'],
        ['랭킹 유형', src.ranking_type || '—'], ['스냅샷 SHA-256', h('code', { class: 'tjb-hash' }, src.snapshot_sha256 || '—')],
        ['시장 · 통화', `${r.market || '—'} · ${r.currency || '—'}`], ['범위', r.coverage.scope || '—']])])])]);
  }

  window.TraderJB = Object.freeze({ mount, render, validate, unmount });
})();
