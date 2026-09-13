/* Shared, source-preserving industry → process/part → company explorer. */
(function () {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  function node(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function button(text, cls, fn) {
    const b = node('button', cls, text);
    b.type = 'button'; b.addEventListener('click', fn); return b;
  }
  function unique(rows) { return [...new Map(rows.map(c => [c.stock, c])).values()]; }
  let data = null, state = null;
  const labels = {ksemi:'반도체', kship:'조선', kdef:'방산', knuke:'원전·발전', kaero:'우주항공'};
  const industry = location.pathname.split('/').find(p => labels[p]) || 'ksemi';
  function setup(p) {
    data = p; document.body.classList.add('industry-explorer');
    const host = $('.ig');
    const guide = node('div', 'ix-guide');
    ['공정·영역 선택', '하위 스텝·부품', '연결 기업'].forEach((text, i) => {
      const s = node('span', 'ix-guide-step');
      s.append(node('b', '', String(i + 1).padStart(2, '0')), node('span', '', text));
      guide.append(s); if (i < 2) guide.append(node('span', 'ix-guide-arrow', '→'));
    });
    host.before(guide);
    const nav = node('nav', 'ix-industries'); nav.setAttribute('aria-label', '산업 인포그래픽');
    Object.entries(labels).forEach(([id, label]) => {
      const a = node('a', id === industry ? 'active' : '', label);
      a.href = '../' + id + '/parts.html';
      if (id === industry) a.setAttribute('aria-current', 'page');
      nav.append(a);
    });
    const kpi = $('.kpi'); kpi.before(nav);
    $('#panel').removeAttribute('aria-live');
    $('#panel').setAttribute('aria-label', '하위 공정 및 기업 탐색');
    // Give small map regions a usable keyboard focus target and a clear tooltip.
    document.querySelectorAll('.ig svg').forEach(svg => svg.setAttribute('role', 'group'));
    intro();
  }
  function progress(level) {
    document.querySelectorAll('.ix-guide-step').forEach((s, i) => {
      s.classList.toggle('current', i === level); s.classList.toggle('done', i < level);
      if (i === level) s.setAttribute('aria-current', 'step'); else s.removeAttribute('aria-current');
    });
  }
  function intro() {
    state = null; progress(0);
    const panel = $('#panel'); panel.replaceChildren();
    const empty = node('div', 'ix-welcome ix-enter');
    empty.append(node('span', 'ix-eyebrow', 'EXPLORE THE INDUSTRY'),
      node('h3', '', '큰 흐름에서, 기업까지.'),
      node('p', '', '위 그림의 공정이나 영역을 선택하세요. 하위 스텝·부품을 펼친 뒤 연결 기업과 근거를 확인할 수 있습니다.'));
    panel.append(empty);
  }
  function categories(ids, meta) {
    return ids.map(id => {
      const c = data.cats.find(c => c.id === id);
      if (!c) return null;
      return {id, label:c.ko, subtitle:data.groups[c.g || c.p] || '', rows:data.idx[id] || [], ...(meta ? meta(id) : {})};
    }).filter(Boolean);
  }
  function show(options) {
    state = {...options, child: options.selected || null}; render(true);
    const panel = $('#panel');
    if (panel.getBoundingClientRect().top > innerHeight - 220) {
      panel.scrollIntoView({block:'start', behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
    }
  }
  function render(focus) {
    const panel = $('#panel'); panel.replaceChildren();
    const content = node('div', 'ix-content ix-enter');
    const child = state.children.find(c => c.id === state.child);
    progress(child ? 2 : 1);
    const path = node('nav', 'ix-path'); path.setAttribute('aria-label', '탐색 경로');
    path.append(node('span', '', labels[industry]), node('span', 'ix-separator', '/'));
    if (child) {
      path.append(button(state.title, '', () => {state.child = null; render(true);}), node('span', 'ix-separator', '/'), node('span', 'active', child.label));
    } else path.append(node('span', 'active', state.title));
    content.append(path);
    const head = node('div', 'ix-heading');
    const title = node('div');
    title.append(node('span', 'ix-eyebrow', child ? '03 / COMPANIES' : '02 / PROCESSES & PARTS'));
    const h = node('h3', 'ix-title', child ? child.label : state.title); h.tabIndex = -1;
    title.append(h, node('p', 'ix-description', child ? (child.description || '원문과 기존 분류에 연결된 기업입니다. 기업명을 누르면 상세 페이지로 이동합니다.') : (state.description || '하위 스텝·부품을 선택해 연결 기업을 확인하세요.')));
    head.append(title);
    const allRows = unique(state.children.flatMap(c => c.rows));
    head.append(node('span', 'ix-total', child ? unique(child.rows).length + '개 기업' : state.children.length + '개 세부 항목 · ' + allRows.length + '개 기업'));
    content.append(head);
    if (child) {
      content.append(button('← 세부 항목으로', 'ix-back', () => {state.child = null; render(true);}));
      const tools = node('div', 'ix-tools');
      const searchLabel = node('label', 'ix-search');
      searchLabel.append(node('span', '', '기업 검색'));
      const search = node('input'); search.type = 'search'; search.placeholder = '기업명 또는 종목코드';
      searchLabel.append(search); tools.append(searchLabel);
      const count = node('span', 'ix-result-count'); count.setAttribute('role', 'status'); tools.append(count);
      content.append(tools);
      const grid = node('div', 'ix-companies'); content.append(grid);
      const rows = unique(child.rows);
      let limit = 12;
      function filter() {
        const query = search.value.trim().toLocaleLowerCase();
        const visible = rows.filter(c => (c.nm + ' ' + c.stock).toLocaleLowerCase().includes(query));
        count.textContent = Math.min(limit, visible.length) + ' / ' + visible.length + '개 기업 표시'; grid.replaceChildren();
        visible.slice(0, limit).forEach(c => grid.append(company(c)));
        if (visible.length > limit) {
          grid.append(button('기업 더 보기 · ' + (visible.length - limit) + '개 남음', 'ix-more', () => {
            const firstNew = limit; limit += 12; filter();
            const next = grid.children[firstNew];
            if (next) {next.tabIndex = -1; next.focus({preventScroll:true});}
          }));
        }
        if (!visible.length) grid.append(node('p', 'ix-empty', rows.length ? '검색 결과가 없습니다. 다른 기업명이나 종목코드를 입력하세요.' : '이 세부 항목에 연결할 기업을 원문에서 확인하지 못했습니다. 미확인은 0개로 유지합니다.'));
      }
      search.addEventListener('input', () => {limit = 12; filter();}); filter();
      if (child.meta) content.append(node('p', 'ix-footnote', child.meta));
    } else {
      const groups = [...new Set(state.children.map(c => c.section || '세부 항목'))];
      groups.forEach(section => {
        const children = state.children.filter(c => (c.section || '세부 항목') === section);
        if (groups.length > 1) content.append(node('h4', 'ix-section-title', section));
        const grid = node('div', 'ix-children');
        if (children.length === 5) grid.classList.add('ix-five');
        children.forEach((c, i) => {
          const n = unique(c.rows).length;
          const b = button('', 'ix-child' + (n ? '' : ' ix-unverified') + (c.dim ? ' ix-dim' : ''), () => {state.child = c.id; render(true);});
          b.dataset.child = c.id;
          const top = node('div', 'ix-child-top');
          top.append(node('span', 'ix-child-index', String(i + 1).padStart(2, '0')), node('span', 'ix-child-arrow', '↗'));
          b.append(top, node('strong', '', c.label), node('span', 'ix-child-subtitle', c.subtitle || c.meta || '원문 근거별 연결'));
          const bottom = node('span', 'ix-child-bottom');
          bottom.append(node('b', '', n ? n + '개 기업' : '기업 미확인'), node('span', '', '살펴보기 →')); b.append(bottom);
          if (c.meta && c.subtitle) b.append(node('span', 'ix-child-meta', c.meta));
          grid.append(b);
        }); content.append(grid);
      });
      if (!state.children.length) content.append(node('p', 'ix-empty', '이 영역에는 등록된 세부 항목이 없습니다. 그림의 안쪽 영역이나 부품 대분류를 선택하세요.'));
    }
    if (state.note) content.append(node('p', 'ix-footnote', state.note));
    panel.append(content);
    if (focus) h.focus({preventScroll:true});
  }
  function company(c) {
    const card = node('article', 'ix-company');
    const header = node('div', 'ix-company-head');
    const linked = /^[A-Za-z0-9_-]+$/.test(c.stock) && (!data.pages || data.pages.includes(c.stock));
    const name = node(linked ? 'a' : 'strong', 'ix-company-name', c.nm);
    if (linked) name.href = c.stock + '/index.html';
    header.append(name, node('span', 'ix-stock', c.stock)); card.append(header);
    const badges = node('div', 'ix-badges');
    const source = (data.srcKo || data.src || data.basis || {})[c.src || c.basis] || c.src || c.basis;
    if (source) badges.append(node('span', 'ix-badge', source));
    if (c.est) badges.append(node('span', 'ix-badge ix-est', '추정'));
    if (c.role) badges.append(node('span', 'ix-badge', c.role));
    if (c.fb) badges.append(node('span', 'ix-badge', c.fb));
    if (c.primary) badges.append(node('span', 'ix-badge', '주단계'));
    if (!linked) badges.append(node('span', 'ix-badge', '상세 페이지 미수록'));
    card.append(badges);
    const keywords = c.kw || (c.words || []).join(' · ');
    if (keywords) card.append(node('p', 'ix-keywords', '연결 낱말 · ' + keywords));
    if (c.blf != null || c.share != null) card.append(node('p', 'ix-metric', c.blf != null ? '수주잔고 ' + c.blf + '억' + (c.blq ? ' · ' + c.blq : '') : '매출비중 ' + c.share + '%'));
    const partners = c.custs || c.primes || (c.yards || []).map(id => ({nm:(data.yards || {})[id] || id, basis:'본문 언급'}));
    if (partners && partners.length) card.append(node('p', 'ix-partners', '고객·납품처 언급 · ' + partners.map(p => p.nm + (p.basis ? ' (' + p.basis + (p.est ? ' · 추정' : '') + ')' : '')).join(' · ')));
    const evidence = [];
    if (c.ev) evidence.push({label:source || '분류 근거', text:c.ev});
    if (c.prod) evidence.push({label:'제품 문구', text:c.prod});
    (Array.isArray(c.scan) ? c.scan : c.scan ? [c.scan] : []).forEach(s => {
      if (s.quote) evidence.push({label:(s.src === '주요제품' ? '정기보고서 II-2 주요제품' : '정기보고서 II절 본문') + (s.term ? ' · ' + s.term : '') + (s.n ? ' · ' + s.n + '회' : ''), text:s.quote});
    });
    if (evidence.length) {
      const details = node('details', 'ix-evidence');
      details.append(node('summary', '', '분류 근거 보기'));
      evidence.forEach(e => {
        details.append(node('span', 'ix-evidence-label', e.label), node('blockquote', '', e.text));
      }); card.append(details);
    }
    return card;
  }
  /* Match only words already accepted by the source classifier; never scan arbitrary
     prose again or promote an equipment user's part mention to a part manufacturer. */
  const processes = {
    photo:[['코팅·현상','코터|디벨로퍼|트랙'],['노광','노광|euv|스테퍼'],['마스크·레티클','레티클|블랭크마스크|포토마스크|마스크']],
    etch:[['건식 식각','dry etch'],['폴리 식각','poly etch']],
    depo:[['CVD · 화학기상증착','cvd'],['ALD · 원자층증착','ald'],['PVD · 물리기상증착','pvd|스퍼터'],['에피 · 결정 성장','에피|epi']],
    thermal:[['급속 열처리','rtp|급속열처리'],['어닐링','어닐|anneal|annealing'],['확산·퍼니스','확산|퍼니스|furnace'],['산화','산화']],
    clean:[['습식 세정','습식세정'],['건식 세정','건식세정|드라이클리닝'],['스트립·애싱','스트립|애싱|애셔|descum']],
    metro:[['오버레이 측정','오버레이|overlay'],['CD·전자현미경','cd-sem|현미경'],['광학·비전 검사','비전검사|광학검사'],['X-ray 검사','x-ray|엑스레이'],['결함 검사','결함|defect']],
    handling:[['웨이퍼 이송','이송|반송|oht|스토커|로드포트|foup|카세트|웨이퍼 캐리어|efem|lpm'],['진공 시스템','진공|진공펌프'],['온도·환경 제어','칠러|클린룸|드라이룸'],['약액·가스 공급','ccss|c.c.s.s|약액|가스공급|가스 공급|chemical 공급|중앙공급|배관|유량계|유량 제어'],['배기·정화','스크러버|scrubber|트랩']],
    test:[['웨이퍼 프로빙','프로브|probe|프로브카드|probe card'],['소켓·인터페이스','검사용 소켓|소켓|socket|change over kit|c.o.k'],['테스트 핸들링','핸들러'],['번인·신뢰성','번인|burn-in|burn in|신뢰성']],
    pkg:[['본딩·접합','본더|본딩|다이본더|tc bonder|플립칩'],['다이싱·절단','다이싱|소잉|쏘잉'],['몰딩·성형','몰딩|금형'],['범핑·TSV','범핑|범프|tsv'],['박막화','백그라인딩'],['리플로','리플로|reflow']],
    service:[['세정 서비스','부품 세정|부품세정|제조 및 세정'],['코팅 서비스','세정 및 코팅|보호코팅|코팅'],['재생·리퍼브','리퍼브|리퍼비시|부품재생|재생']]
  };
  function semi(p) {
    setup(p);
    const flow = node('div', 'ix-flow-map'); flow.id = 'fab';
    flow.setAttribute('aria-label', '팹 공정 흐름');
    const top = node('div', 'ix-flow-caption');
    top.append(node('span', 'ix-eyebrow', 'FAB PROCESS'), node('span', '', '웨이퍼 투입 → 전공정 → 후공정 → 출하'));
    flow.append(top);
    const ordered = node('ol', 'ix-flow-steps');
    const common = node('div', 'ix-flow-common');
    p.stages.forEach(st => {
      const b = node('button', 'node ix-flow-node'); b.type = 'button'; b.dataset.stage = st.key;
      b.style.setProperty('--stage', st.color);
      const row = node('span', 'ix-flow-node-top');
      row.append(node('span', '', st.flow ? String(st.flow).padStart(2, '0') : '공통'), node('span', '', st.flow ? '→' : '↗'));
      b.append(row, node('strong', '', st.label.split('(')[0]));
      const detail = st.label.includes('(') ? st.label.split('(')[1].replace(/\)$/, '') : st.fb;
      b.append(node('span', 'ix-flow-detail', detail));
      const count = node('span', 'ix-flow-count'); count.dataset.cnt = ''; b.append(count);
      if (st.flow) {const li = node('li'); li.append(b); ordered.append(li);} else common.append(b);
    });
    flow.append(ordered, node('p', 'ix-flow-common-label', '전 공정에 연결되는 부품·서비스'), common);
    $('#fab').replaceWith(flow);
    $('.fab .legend').hidden = true;
    let selected = null, fb = 'all';
    function allowed(v) {return fb === 'all' || !v || /공통|겸업/.test(v) || (fb === 'front' ? v === '전공정' : v === '후공정');}
    function paint() {
      document.querySelectorAll('#fab .node').forEach(g => {
        const st = p.stages.find(s => s.key === g.dataset.stage);
        g.classList.toggle('sel', st.key === selected); g.classList.toggle('off', !allowed(st.fb));
        g.setAttribute('aria-expanded', String(st.key === selected));
        g.setAttribute('aria-label', st.label + ' · 하위 공정과 부품 보기');
        const count = $('[data-cnt]', g); if (count) count.textContent = p.agg[st.key][fb].n + '사';
      });
    }
    function open(key, save = true) {
      const st = p.stages.find(s => s.key === key); if (!st) return;
      selected = key; paint();
      const rows = (p.cos[key] || []).filter(c => allowed(c.fb));
      const assigned = new Set();
      const children = (processes[key] || []).map(([label, terms], i) => {
        const accepted = terms.split('|');
        const matching = rows.filter(c => (c.words || []).some(w => accepted.includes(w.toLowerCase())));
        matching.forEach(c => assigned.add(c.stock));
        return {id:'step-' + i, label, subtitle:'기존 분류 낱말 기준', section:'하위 공정·스텝', rows:matching,
          description:'기존 분류에서 이 세부 공정 낱말이 확인된 기업입니다. 본문 언급에는 공정 설명이 포함될 수 있으므로 분류 근거를 함께 확인하세요.'};
      });
      const other = rows.filter(c => !assigned.has(c.stock));
      if (other.length || !children.length) children.push({id:'unspecified', label:children.length ? '세부 공정 미확인' : st.label.split('(')[0] + ' · 단계 연결', subtitle:'세부 기술을 임의로 배정하지 않습니다', section:'하위 공정·스텝', rows:other});
      (st.parts || []).forEach(part => children.push({id:'part-' + part.key, label:part.label, subtitle:'부품·공정서비스사 원문 근거', section:'장비를 구성하는 부품', rows:(p.partcos[key] || {})[part.key] || []}));
      if (key === 'parts' && p.unspec.length) children.push({id:'part-unspecified', label:'부품 종류 미확인', subtitle:'원문에서 종류를 특정하지 못한 기업', section:'장비를 구성하는 부품', rows:p.unspec});
      show({title:st.label, children, description:'세부 공정 또는 구성 부품을 골라 연결 기업을 살펴보세요.',
        note:'같은 기업이 여러 항목에 포함될 수 있습니다. 단계 연결은 기존 분류 기준이며, 세부 공정은 확인된 분류 낱말로만 나눕니다. 부품 연결은 별도의 원문 기준을 따릅니다.'});
      if (save) history.replaceState(null, '', '#' + key);
    }
    document.querySelectorAll('#fab .node').forEach(g => {
      g.addEventListener('click', () => open(g.dataset.stage));
    });
    document.querySelectorAll('#fbseg button').forEach(b => b.addEventListener('click', () => {
      fb = b.dataset.fb;
      document.querySelectorAll('#fbseg button').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.fb === fb)));
      if (selected) open(selected); else paint();
    }));
    $('#reset').addEventListener('click', () => {
      fb = 'all'; selected = null; history.replaceState(null, '', location.pathname + location.search);
      document.querySelectorAll('#fbseg button').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.fb === 'all')));
      paint(); intro();
    });
    window.addEventListener('hashchange', () => {if (location.hash) open(location.hash.slice(1), false); else {selected = null; paint(); intro();}});
    paint(); if (location.hash) open(location.hash.slice(1), false);
  }
  window.IndustryExplorer = {setup, intro, categories, show, semi};
})();
