/* Keep the overview visible; disclose its parts in place and filter the adjacent list. */
(function () {
  'use strict';
  let P, current;
  const $ = s => document.querySelector(s);
  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function btn(text, cls, onClick) {
    const b = el('button', cls, text); b.type = 'button'; b.addEventListener('click', onClick); return b;
  }
  function companies(rows) {
    const index = new Map();
    rows.forEach(row => {
      if (!index.has(row.stock)) index.set(row.stock, {...row, records:[]});
      index.get(row.stock).records.push(row);
    });
    return [...index.values()];
  }
  function setup(data) {
    P = data; document.body.classList.add('px-enhanced');
    const diagram = $('.ig > .fab') || $('.ig > .ship');
    const lens = el('div', 'px-lens'); lens.id = 'px-lens'; diagram.append(lens);
    document.querySelectorAll('.ig svg').forEach(svg => svg.setAttribute('role','group'));
    $('#panel').removeAttribute('aria-live');
    const announce = el('span', 'px-sr'); announce.setAttribute('role', 'status');
    diagram.append(announce);
  }
  function categories(ids, meta) {
    return ids.map(id => {
      const c = P.cats.find(c => c.id === id);
      return c ? {id, label:c.ko, rows:P.idx[id] || [], meta:meta ? meta(id) : ''} : null;
    }).filter(Boolean);
  }
  function show(options) {
    current = {...options, section:0, selected:null};
    if (options.selected) {
      current.section = Math.max(0, current.sections.findIndex(s => s.items.some(c => c.id === options.selected)));
      current.selected = options.selected;
    }
    $('.px-sr').textContent = options.title + ' 하위 항목이 그림 아래에 열렸습니다.';
    lens(); panel();
  }
  function clear() {
    current = null; $('.px-lens').replaceChildren(); $('.px-sr').textContent = '';
  }
  function labels(layer, selectedLabel) {
    const svg = layer.ownerSVGElement, bounds = svg.viewBox.baseVal;
    const placed = [];
    const overlaps = (a,b) => a.x < b.x+b.width+2 && a.x+a.width+2 > b.x && a.y < b.y+b.height+2 && a.y+a.height+2 > b.y;
    [...layer.querySelectorAll('text')].forEach(text => {
      text.classList.toggle('px-active-label', text.textContent === selectedLabel);
      const x = Number(text.getAttribute('x')), y = Number(text.getAttribute('y'));
      const original = text.getBBox();
      let box = original, moved = false;
      if (placed.some(other => overlaps(box,other))) {
        // Move only colliding labels; a leader keeps the original attachment explicit.
        const shifts = [];
        for (const distance of [12,24,36,48]) for (const [dx,dy] of [[0,-1],[0,1],[-1,0],[1,0],[-1,-1],[1,1]]) shifts.push([dx*distance,dy*distance]);
        for (const [dx,dy] of shifts) {
          const next = {x:original.x+dx,y:original.y+dy,width:original.width,height:original.height};
          if (next.x < bounds.x+4 || next.y < bounds.y+4 || next.x+next.width > bounds.x+bounds.width-4 || next.y+next.height > bounds.y+bounds.height-4) continue;
          if (placed.some(other => overlaps(next,other))) continue;
          text.setAttribute('x',x+dx);text.setAttribute('y',y+dy);
          box=next;moved=true;break;
        }
      }
      if (moved) {
        const line=document.createElementNS('http://www.w3.org/2000/svg','line');
        line.setAttribute('class','px-label-leader');
        line.setAttribute('x1',x);line.setAttribute('y1',y-3);
        line.setAttribute('x2',Number(text.getAttribute('x')));line.setAttribute('y2',Number(text.getAttribute('y'))-3);
        layer.insertBefore(line,layer.firstChild);
      }
      placed.push(box);
    });
  }
  function lens() {
    const host = $('.px-lens'); host.replaceChildren();
    if (!current) return;
    const head = el('div', 'px-lens-head');
    head.append(el('strong', 'px-parent', current.title));
    if (current.sections.length > 1) {
      const tabs = el('div', 'px-tabs'); tabs.setAttribute('aria-label', '하위 항목 종류');
      current.sections.forEach((s, i) => {
        const b = btn(s.label, '', () => {
          current.section = i; current.selected = null; lens(); panel();
          $('.px-tabs [aria-pressed=true]').focus({preventScroll:true});
        });
        b.setAttribute('aria-pressed', String(current.section === i)); tabs.append(b);
      }); head.append(tabs);
    } else head.append(el('span', 'px-type', current.sections[0].label));
    host.append(head);
    const branch = el('div', 'px-branch');
    const items = current.sections[current.section].items;
    items.forEach(item => {
      const b = btn('', 'px-leaf', () => {
        current.selected = item.id; lens(); panel();
        const replacement = [...document.querySelectorAll('.px-leaf')].find(e => e.dataset.child === item.id);
        if (replacement) replacement.focus({preventScroll:true});
        $('.px-sr').textContent = item.label + ' · 연결 기업 ' + companies(item.rows).length + '곳';
      });
      const count = companies(item.rows).length;
      b.dataset.child = item.id; b.setAttribute('aria-pressed', String(current.selected === item.id));
      if (!count) b.classList.add('px-unverified');
      b.append(el('span', '', item.label), el('small', '', count ? count + '사' : '미확인'));
      if (item.meta) b.title = item.meta;
      branch.append(b);
    });
    host.append(branch);
    if (!items.length) host.append(el('p', 'px-note', '세부 부품은 그림의 안쪽 영역에서 선택할 수 있습니다.'));
    else host.append(el('p', 'px-note', '하위 항목을 누르면 ' + (innerWidth > 900 ? '오른쪽' : '아래') + ' 기업 목록이 바뀝니다.'));
  }
  function panel() {
    const host = $('#panel'); host.replaceChildren();
    const selected = current.sections.flatMap(s => s.items).find(i => i.id === current.selected);
    const rows = selected ? selected.rows : ((current.section === 0 && current.rows) || current.sections[current.section].items.flatMap(i => i.rows));
    const list = companies(rows);
    const path = el('div', 'px-path');
    if (selected) {
      path.append(btn(current.title, '', () => {
        current.selected = null; lens(); panel();
        const first = $('.px-leaf'); if (first) first.focus({preventScroll:true});
      }), el('span', '', '›'), el('span', '', selected.label));
    } else path.append(el('span', '', current.title));
    host.append(path);
    const head = el('div', 'px-panel-head');
    head.append(el('h3', '', selected ? selected.label : '연결 기업'), el('span', 'px-count', list.length + '사'));
    host.append(head);
    const info = selected ? selected.meta : current.section === 0 ? current.meta : current.sections[current.section].label + ' 전체';
    if (info) host.append(el('p', 'px-note', info));
    if (!list.length) {
      host.append(el('p', 'px-empty', '원문에서 이 항목에 연결할 상장사를 확인하지 못했습니다.'));
      return;
    }
    const label = el('label', 'px-search');
    label.append(el('span', 'px-sr', '기업명 또는 종목코드 검색'));
    const search = el('input'); search.type = 'search'; search.placeholder = '기업명 · 종목코드 검색';
    label.append(search); host.append(label);
    const result = el('div', 'px-companies'); host.append(result);
    const status = el('span', 'px-sr'); status.setAttribute('role', 'status'); host.append(status);
    function filter() {
      const query = search.value.trim().toLowerCase();
      const visible = list.filter(c => (c.nm + ' ' + c.stock).toLowerCase().includes(query));
      result.replaceChildren(); visible.forEach(c => result.append(company(c)));
      status.textContent = visible.length + '사';
      if (!visible.length) result.append(el('p', 'px-empty', '검색 결과가 없습니다.'));
    }
    search.addEventListener('input', filter); filter();
    if (current.note) host.append(el('p', 'px-note px-foot', current.note));
  }
  function company(c) {
    const box = el('article', 'px-company');
    const top = el('div', 'px-co-head');
    const link = /^[A-Za-z0-9_-]+$/.test(c.stock) && (!P.pages || P.pages.includes(c.stock));
    const name = el(link ? 'a' : 'strong', '', c.nm);
    if (link) name.href = c.stock + '/index.html';
    top.append(name, el('span', 'px-stock', c.stock)); box.append(top);
    const proof = el('details', 'px-proof');
    const sourceLabel = r => (P.srcKo || P.src || P.basis || {})[r.src || r.basis] || r.src || r.basis || '';
    const badges = [...new Set(c.records.map(sourceLabel).filter(Boolean))];
    if (c.records.some(r => r.est)) badges.push('추정');
    const words = [...new Set(c.records.flatMap(r => r.kw ? [r.kw] : r.words || []))];
    const summary = el('summary');
    summary.append(el('span', '', badges.join(' · ') || '분류 근거'), el('span', 'px-disclosure', '근거 보기'));
    proof.append(summary);
    const seen = new Set();
    function evidence(label, text) {
      if (!text || seen.has(label + text)) return;
      seen.add(label + text); proof.append(el('small', '', label), el('blockquote', '', text));
    }
    if (words.length) proof.append(el('p', 'px-note', '연결 낱말: ' + words.join(' · ')));
    const context = [c.role,c.fb,c.primary ? '주단계' : ''].filter(Boolean).join(' · ');
    if (context) proof.append(el('p','px-note',context));
    c.records.forEach(r => {
      evidence(sourceLabel(r), r.ev || r.prod);
      (Array.isArray(r.scan) ? r.scan : r.scan ? [r.scan] : []).forEach(s => evidence(
        (s.src === '주요제품' ? '정기보고서 II-2 주요제품' : '정기보고서 II절 본문') + (s.term ? ' · ' + s.term : ''), s.quote));
      const customers = r.custs || r.primes || (r.yards || []).map(y => ({nm:(P.yards || {})[y] || y, basis:'본문 언급'}));
      (customers || []).forEach(p => evidence('고객·납품처 언급', p.nm + (p.basis ? ' · ' + p.basis : '') + (p.est ? ' · 추정' : '')));
    });
    box.append(proof);
    if (c.blf != null) box.append(el('div', 'px-metric', '수주잔고 ' + c.blf + '억' + (c.blq ? ' · ' + c.blq : '')));
    if (c.share != null) box.append(el('div', 'px-metric', '매출비중 ' + c.share + '%'));
    return box;
  }
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
    let stage = null, fb = 'all';
    const allowed = value => fb === 'all' || value === '공통' || value === '전후공정 겸업' || value === (fb === 'front' ? '전공정' : '후공정');
    function paint() {
      document.querySelectorAll('#fab .node').forEach(n => {
        const st = p.stages.find(s => s.key === n.dataset.stage);
        n.classList.toggle('sel', st.key === stage); n.classList.toggle('off', !allowed(st.fb));
        n.setAttribute('aria-expanded', String(st.key === stage));
        n.setAttribute('aria-controls','px-lens');
        const count = n.querySelector('[data-cnt]'); if (count) count.textContent = p.agg[st.key][fb].n + '사';
      });
    }
    function open(key, writeHash = true) {
      const st = p.stages.find(s => s.key === key); if (!st) return;
      stage = key; paint();
      const rows = (p.cos[key] || []).filter(c => allowed(c.fb));
      const seen = new Set();
      const steps = (processes[key] || []).map(([label, terms], i) => {
        const matching = rows.filter(c => (c.words || []).some(w => terms.split('|').includes(w.toLowerCase())));
        matching.forEach(c => seen.add(c.stock));
        return {id:'step-' + i, label, rows:matching, meta:'기존 분류 낱말에 따른 연결 · 본문 언급은 공정 설명일 수 있습니다.'};
      });
      const unspecified = rows.filter(c => !seen.has(c.stock));
      if (unspecified.length) steps.push({id:'step-unspecified', label:'세부 공정 미확인', rows:unspecified, meta:'단계 연결만 확인됐으며 세부 기술은 분류하지 않았습니다.'});
      const parts = (st.parts || []).map(part => ({id:'part-' + part.key, label:part.label, rows:(p.partcos[key] || {})[part.key] || [], meta:'부품·공정서비스사 원문 근거'}));
      if (key === 'parts' && p.unspec.length) parts.push({id:'part-unspecified',label:'부품 종류 미확인',rows:p.unspec});
      const sections = [];
      if (steps.length && key !== 'parts') sections.push({label:'세부 공정',items:steps});
      if (parts.length) sections.push({label:'구성 부품',items:parts});
      if (!sections.length) sections.push({label:'세부 공정',items:steps});
      show({title:st.label.split('(')[0], sections, rows, meta:st.fb + ' · 단계 전체', note:'분류는 원문 낱말 기준입니다. 세부 공정과 부품은 서로 다른 연결 기준을 사용합니다.'});
      if (writeHash) history.replaceState(null,'','#' + key);
    }
    document.querySelectorAll('#fab .node').forEach(n => {
      n.addEventListener('click', () => open(n.dataset.stage));
      n.addEventListener('keydown', e => {if (e.key === 'Enter' || e.key === ' ') {e.preventDefault();open(n.dataset.stage);}});
    });
    document.querySelectorAll('#fbseg button').forEach(b => b.addEventListener('click', () => {
      fb = b.dataset.fb;
      document.querySelectorAll('#fbseg button').forEach(x => x.setAttribute('aria-pressed',String(x.dataset.fb === fb)));
      if (stage) open(stage); else paint();
    }));
    function intro() {
      clear(); const panel = $('#panel'); panel.replaceChildren(el('h3','','공정 단계를 선택하세요'), el('p','px-note','전체 흐름을 보며 세부 공정·부품과 연결 기업을 탐색할 수 있습니다.'));
    }
    $('#reset').addEventListener('click', () => {
      stage = null; fb = 'all';
      document.querySelectorAll('#fbseg button').forEach(x => x.setAttribute('aria-pressed',String(x.dataset.fb === 'all')));
      history.replaceState(null,'',location.pathname + location.search); paint(); intro();
    });
    window.addEventListener('hashchange', () => {if(location.hash) open(location.hash.slice(1),false);else{stage=null;paint();intro();}});
    paint(); intro(); if(location.hash) open(location.hash.slice(1),false);
  }
  window.PartsExplorer = {setup,show,clear,categories,semi,labels};
})();
