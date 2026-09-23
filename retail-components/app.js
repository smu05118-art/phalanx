(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const arr = (value) => Array.isArray(value) ? value : [];
  const finite = (value) => typeof value === 'number' && Number.isFinite(value);
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  const fmt = (value, digits = 2) => finite(value) ? value.toLocaleString('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits }) : '—';
  const pct = (value, digits = 2) => finite(value) ? `${fmt(value * 100, digits)}%` : '미확보';
  const money = (value) => finite(value) && value > 0 ? `${value.toLocaleString('ko-KR', { maximumFractionDigits: 2 })}원` : '미확보';
  const signed = (value) => finite(value) ? `${value > 0 ? '+' : ''}${fmt(value)}%` : '전일 실측 대기';
  const movement = (value) => finite(value) ? value > 0 ? 'up' : value < 0 ? 'down' : 'flat' : 'muted';
  const setText = (id, value) => { $(id).textContent = value ?? '—'; };
  const strings = (value) => Array.isArray(value) ? value.map(readable) : value == null || value === '' ? [] : [readable(value)];
  const colors = { power_analog: 'var(--accent)', compute_logic: 'var(--blue)', passives: 'var(--violet)' };
  const labels = { power_analog: 'POWER / ANALOG', compute_logic: 'COMPUTE / LOGIC', passives: 'PASSIVES' };
  const brandColors = ['var(--accent)', 'var(--blue)', 'var(--violet)', '#c29b7b', '#85998e', '#b09eb5', '#879cac', '#bdb388', '#bc9196'];
  const DAY = 86400000;
  const state = { data: null, selected: null, product: null, range: 'all', lastFocus: null, bodyOverflow: '' };

  function readable(value) {
    if (value == null || value === '') return '미확보';
    if (typeof value === 'number') return Number.isFinite(value) ? value.toLocaleString('ko-KR') : '미확보';
    if (typeof value === 'string') return value;
    if (Array.isArray(value)) return value.map(readable).join(' · ');
    if (typeof value === 'object') return Object.entries(value).filter(([, item]) => item != null && item !== '').map(([key, item]) => `${key}: ${readable(item)}`).join(' · ') || '미확보';
    return String(value);
  }
  function safeUrl(value) {
    try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null; } catch { return null; }
  }
  function sourceLink(value, label = '원문 ↗') {
    const url = safeUrl(value);
    return url ? `<a class="source-link" href="${escape(url)}" target="_blank" rel="noopener noreferrer">${escape(label)}</a>` : '<span class="missing">원문 미확보</span>';
  }
  function dateTime(value) {
    const date = new Date(value);
    if (!value || !Number.isFinite(date.getTime())) return '미확보';
    return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(date) + ' KST';
  }
  function dayTime(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value))) return null;
    const time = Date.parse(`${value}T00:00:00Z`);
    return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value ? time : null;
  }
  function priorDay(value) {
    const time = dayTime(value);
    return time === null ? null : new Date(time - DAY).toISOString().slice(0, 10);
  }
  function complete(point, basketCount) {
    return Boolean(point && finite(point.value) && point.value > 0 && finite(point.coverage_weight) && point.coverage_weight >= 1 - 1e-9 && point.coverage_count === basketCount);
  }
  function indexDod(index, point = index) {
    const date = point.date || point.as_of;
    const previous = arr(index.series).find((entry) => entry.date === priorDay(date));
    // Never turn a server-side null or a skipped calendar date into a zero change.
    return complete(point, index.basket_count) && complete(previous, index.basket_count) && finite(point.dod_pct) ? point.dod_pct : null;
  }
  function productDod(item) {
    const date = state.selected?.as_of;
    const current = arr(item.price_history).find((entry) => entry.date === date);
    const previous = arr(item.price_history).find((entry) => entry.date === priorDay(date));
    return current && previous && finite(current.price) && finite(previous.price) && current.price > 0 && previous.price > 0 ? (current.price / previous.price - 1) * 100 : null;
  }
  function list(id, values) {
    $(id).innerHTML = strings(values).map((value) => `<li>${escape(value)}</li>`).join('') || '<li>규칙 미확보</li>';
  }
  function chart(host, values, options = {}) {
    const { field = 'value', color = 'var(--accent)', miniature = false, unit = '지수', title = '일간 가격 관측', baseline = null } = options;
    const points = arr(values).map((item) => ({ ...item, time: dayTime(item.date), plotted: item[field] })).filter((item) => item.time !== null).sort((a, b) => a.time - b.time);
    const valid = points.filter((item) => finite(item.plotted) && item.plotted > 0);
    if (!valid.length) {
      host.innerHTML = miniature ? '<div class="empty-chart">관측 대기</div>' : '<div class="empty-chart"><strong>표시할 실제 관측값이 없습니다</strong><span>미확보 가격은 공백으로 남깁니다.</span></div>';
      return;
    }
    const width = miniature ? 330 : Math.max(265, Math.round(host.getBoundingClientRect().width || 800));
    const height = miniature ? 48 : width < 500 ? 245 : 285;
    const margin = miniature ? { l: 4, r: 4, t: 6, b: 6 } : { l: unit === '원' ? 74 : 58, r: 27, t: 26, b: 35 };
    const first = points[0].time, last = points[points.length - 1].time;
    let low = Math.min(...valid.map((item) => item.plotted)), high = Math.max(...valid.map((item) => item.plotted));
    const padding = low === high ? Math.max(Math.abs(high) * .035, .05) : (high - low) * .15;
    low = Math.max(0, low - padding); high += padding;
    const plotWidth = width - margin.l - margin.r, plotHeight = height - margin.t - margin.b;
    const x = (point) => margin.l + (first === last ? plotWidth / 2 : (point.time - first) / (last - first) * plotWidth);
    const y = (value) => margin.t + (high - value) / (high - low) * plotHeight;
    const axis = (value) => value.toLocaleString('ko-KR', { maximumFractionDigits: high - low < 2 ? 2 : high - low < 10 ? 1 : 0 });
    let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escape(title)}"><title>${escape(title)}. 실제 관측 ${valid.length}개. 결측 날짜는 연결하지 않습니다.</title>`;
    if (!miniature) {
      svg += `<text x="${margin.l}" y="12" class="chart-label">${escape(unit)}</text>`;
      for (let index = 0; index < 5; index++) {
        const level = low + (high - low) * index / 4;
        svg += `<line x1="${margin.l}" y1="${y(level)}" x2="${width - margin.r}" y2="${y(level)}" class="grid-line"/><text x="${margin.l - 10}" y="${y(level) + 4}" text-anchor="end" class="chart-label">${escape(axis(level))}</text>`;
      }
      if (finite(baseline) && baseline >= low && baseline <= high) svg += `<line x1="${margin.l}" y1="${y(baseline)}" x2="${width - margin.r}" y2="${y(baseline)}" class="baseline"/>`;
      const labelCount = Math.max(2, Math.floor(plotWidth / 110));
      const indices = new Set([0, points.length - 1]);
      for (let index = 1; index < labelCount - 1; index++) indices.add(Math.round((points.length - 1) * index / (labelCount - 1)));
      let previousX = -Infinity;
      for (const index of [...indices].sort((a, b) => a - b)) {
        const point = points[index];
        if (index !== points.length - 1 && indices.size > 1 && x(points[points.length - 1]) - x(point) < 90) continue;
        if (x(point) - previousX < 85) continue;
        previousX = x(point);
        svg += `<text x="${x(point)}" y="${height - 12}" text-anchor="middle" class="chart-label">${escape(point.date)}</text>`;
      }
    }
    const segments = [];
    let segment = [], previous = null;
    const flush = () => { if (segment.length) segments.push(segment); segment = []; };
    for (const point of points) {
      if (!finite(point.plotted) || point.plotted <= 0) { flush(); previous = null; continue; }
      if (previous && point.time - previous.time !== DAY) flush();
      segment.push(point); previous = point;
    }
    flush();
    for (const part of segments) {
      if (part.length < 2) continue;
      svg += `<path class="data-line" data-point-count="${part.length}" d="${part.map((point, index) => `${index ? 'L' : 'M'}${x(point).toFixed(2)},${y(point.plotted).toFixed(2)}`).join(' ')}" fill="none" stroke="${color}" stroke-width="${miniature ? 2 : 2.5}"/>`;
    }
    valid.forEach((point) => {
      const tooltip = `${point.date}\n${unit === '원' ? money(point.plotted) : `${fmt(point.plotted)} pt`}${finite(point.coverage_count) ? `\n제품 커버리지 ${point.coverage_count}개` : ''}${finite(point.coverage_weight) ? ` · ${pct(point.coverage_weight, 1)}` : ''}`;
      svg += `<circle class="data-point" data-date="${escape(point.date)}" cx="${x(point)}" cy="${y(point.plotted)}" r="${miniature ? 3 : 4}" fill="${color}"${miniature ? '' : ` tabindex="0" role="img" aria-label="${escape(tooltip)}" data-tip="${escape(tooltip)}"`}><title>${escape(tooltip)}</title></circle>`;
    });
    host.innerHTML = svg + '</svg>';
    if (!miniature) {
      const tooltip = document.createElement('div'); tooltip.className = 'chart-tooltip'; tooltip.hidden = true; host.append(tooltip);
      host.querySelectorAll('[data-tip]').forEach((point) => {
        const show = () => {
          tooltip.textContent = point.dataset.tip; tooltip.hidden = false;
          const bounds = point.getBoundingClientRect(), parent = host.getBoundingClientRect();
          const half = tooltip.offsetWidth / 2 + 3;
          tooltip.style.left = `${Math.max(half, Math.min(parent.width - half, bounds.left + bounds.width / 2 - parent.left))}px`;
          tooltip.style.top = `${bounds.top - parent.top - 9}px`;
        };
        point.addEventListener('pointerenter', show); point.addEventListener('focus', show);
        point.addEventListener('pointerleave', () => { tooltip.hidden = true; }); point.addEventListener('blur', () => { tooltip.hidden = true; });
      });
    }
  }
  function renderCards() {
    $('index-cards').innerHTML = state.data.indices.map((index, ordinal) => {
      const dod = indexDod(index);
      const started = arr(index.series).filter((point) => finite(point.value)).length === 1;
      return `<button type="button" class="index-card" style="--card-accent:${colors[index.id] || 'var(--accent)'}" data-index="${ordinal}" aria-pressed="false" aria-controls="index-detail"><span class="card-top"><span class="card-label">${escape(labels[index.id] || index.id)}</span><span class="card-arrow" aria-hidden="true">↗</span></span><span class="card-title">${escape(index.name)}</span><span class="card-value">${fmt(index.value)}<span class="unit">pt</span></span><span class="card-change ${movement(dod)}">${finite(dod) ? `${signed(dod)} · 전일 대비` : started ? '누적 시작 · 전일 실측 대기' : '전일 실측 대기'}</span><span class="mini-chart" id="spark-${ordinal}" aria-hidden="true"></span><span class="card-footer"><span>${escape(index.as_of || '관측 대기')}</span><span>${escape(index.coverage_count ?? 0)} / ${escape(index.basket_count ?? 0)}개 · ${pct(index.coverage_weight, 1)}</span></span></button>`;
    }).join('');
    state.data.indices.forEach((index, ordinal) => chart($(`spark-${ordinal}`), index.series, { miniature: true, color: colors[index.id] || 'var(--accent)' }));
    $('index-cards').querySelectorAll('button').forEach((button) => button.addEventListener('click', () => {
      const index = state.data.indices[Number(button.dataset.index)];
      if (index) { history.pushState(null, '', `#${encodeURIComponent(index.id)}`); selectIndex(index, true); }
    }));
  }
  function renderDistribution(index) {
    const brands = new Map(), strata = new Map(), brandNames = new Map();
    for (const item of arr(index.constituents)) {
      if (!finite(item.weight) || item.weight < 0) continue;
      const brand = item.brand_group || item.brand || '브랜드 미확보', stratum = item.stratum_label || item.stratum || '용도 미확보';
      if (!brandNames.has(brand)) brandNames.set(brand, item.brand || brand);
      brands.set(brand, (brands.get(brand) || 0) + item.weight); strata.set(stratum, (strata.get(stratum) || 0) + item.weight);
    }
    $('stratum-weights').innerHTML = [...strata].sort((a, b) => b[1] - a[1]).map(([name, weight]) => `<div class="distribution-row"><span>${escape(name)}</span><span class="distribution-track" aria-hidden="true"><i style="width:${Math.max(0, Math.min(100, weight * 100))}%"></i></span><strong>${pct(weight)}</strong></div>`).join('');
    const entries = [...brands].sort((a, b) => b[1] - a[1]).map(([key, weight]) => [brandNames.get(key), weight]);
    $('brand-weights').innerHTML = `<div class="brand-bar" aria-hidden="true">${entries.map(([, weight], ordinal) => `<span style="width:${Math.max(0, Math.min(100, weight * 100))}%;background:${brandColors[ordinal % brandColors.length]}"></span>`).join('')}</div><div class="brand-legend">${entries.map(([name, weight], ordinal) => `<span><i style="background:${brandColors[ordinal % brandColors.length]}" aria-hidden="true"></i>${escape(name)} <strong>${pct(weight)}</strong></span>`).join('')}</div>`;
  }
  function renderIndexChart() {
    if (!state.selected) return;
    const index = state.selected;
    let series = arr(index.series);
    const times = series.map((point) => dayTime(point.date)).filter((time) => time !== null);
    if (state.range !== 'all' && times.length) {
      const cut = Math.max(...times) - (Number(state.range) - 1) * DAY;
      series = series.filter((point) => dayTime(point.date) !== null && dayTime(point.date) >= cut);
    }
    chart($('index-chart'), series, { color: colors[index.id] || 'var(--accent)', baseline: 100, title: `${index.name} 일간 지수` });
    const count = series.filter((point) => finite(point.value)).length;
    setText('index-chart-note', count === 1 ? '누적 시작: 첫 관측값 1개를 표시합니다. 전일 실측이 확보되면 일간 변화율을 표시합니다. 과거 가격은 생성하지 않습니다.' : `${count}개 실제 지수 관측. 직전 달력 날짜의 관측이 없거나 구성 가격이 빠진 날은 전일 대비를 표시하지 않으며, 결측 구간의 선은 연결하지 않습니다.`);
  }
  function selectIndex(index, scroll = false) {
    state.selected = index;
    $('index-cards').querySelectorAll('button').forEach((button) => button.setAttribute('aria-pressed', String(state.data.indices[Number(button.dataset.index)]?.id === index.id)));
    setText('detail-eyebrow', `${labels[index.id] || index.id} / BASKET DETAIL`);
    setText('detail-heading', index.name);
    const ready = complete(index, index.basket_count);
    const count = arr(index.series).filter((point) => finite(point.value)).length;
    setText('detail-status', ready ? count === 1 ? '누적 시작' : '관측 완료' : '부분 관측');
    $('detail-status').className = `pill${ready ? '' : ' warning'}`;
    const meta = [['기준일', index.base_date || '미확보'], ['최근 관측일', index.as_of || '미확보'], ['제품 커버리지', `${index.coverage_count ?? 0} / ${index.basket_count ?? 0}개`], ['비중 커버리지', pct(index.coverage_weight, 1)]];
    $('detail-meta').innerHTML = meta.map(([key, value]) => `<span>${escape(key)}<strong>${escape(value)}</strong></span>`).join('');
    const warnings = [];
    if (!ready) warnings.push('필수 구성 가격을 모두 확보하지 못해 지수 산출 조건을 충족하지 않았습니다. 확보된 개별 관측은 아래에서 확인할 수 있습니다.');
    if (finite(index.coverage_weight) && index.coverage_weight < 1 - 1e-9) warnings.push(`미확보 비중 ${pct(1 - index.coverage_weight)}. 빠진 제품의 비중을 다른 제품에 배분하지 않습니다.`);
    const observation = dayTime(index.as_of);
    const nowKst = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
    const age = observation === null || dayTime(nowKst) === null ? null : Math.floor((dayTime(nowKst) - observation) / DAY);
    if (age !== null && age >= 2) warnings.push(`최근 관측일로부터 ${age}일 경과했습니다. 현재 시점의 가격으로 해석하지 마세요.`);
    $('index-notice').hidden = warnings.length === 0; $('index-notice').className = 'notice warning'; setText('index-notice', warnings.join(' '));
    setText('index-base', index.base_date ? `${index.base_date} = 100 · 일간 직접 관측` : '기준일 미확보');
    renderIndexChart(); renderDistribution(index);
    $('index-observations').innerHTML = arr(index.series).slice().sort((a, b) => String(b.date).localeCompare(String(a.date))).map((point) => `<tr><td>${escape(point.date)}</td><td class="numeric">${fmt(point.value)}</td><td class="numeric ${movement(indexDod(index, point))}">${finite(indexDod(index, point)) ? signed(indexDod(index, point)) : '—'}</td><td class="numeric">${escape(point.coverage_count ?? '—')} / ${escape(index.basket_count ?? '—')}</td><td class="numeric">${pct(point.coverage_weight, 1)}</td></tr>`).join('') || '<tr><td class="empty-row" colspan="5">관측 대기</td></tr>';
    const rebalance = index.rebalance || {};
    const statuses = { initial: '최초 바스켓 · 관측 축적 중', deferred: '요건 확인 중 · 기존 바스켓 유지', completed: '검토 완료', pending: '검토 대기', applied: '새 바스켓 적용', not_due: '현재 바스켓 유지' };
    $('rebalance').innerHTML = `<p class="rebalance-date">${escape(rebalance.next_review || '일정 미확보')}</p><p>${escape(statuses[rebalance.status] || rebalance.status || '상태 미확보')}</p>${strings(rebalance.notes).map((note) => `<p>${escape(note)}</p>`).join('')}`;
    $('product-search').value = ''; renderConstituents();
    if (scroll) { $('index-detail').focus({ preventScroll: true }); $('index-detail').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' }); }
  }
  function renderConstituents() {
    if (!state.selected) return;
    const query = $('product-search').value.trim().toLocaleLowerCase('ko-KR');
    const all = arr(state.selected.constituents);
    const items = all.map((item, ordinal) => ({ item, ordinal })).filter(({ item }) => `${item.name || ''} ${item.brand || ''} ${item.stratum_label || ''} ${item.id || ''}`.toLocaleLowerCase('ko-KR').includes(query)).sort((a, b) => (b.item.weight || 0) - (a.item.weight || 0));
    setText('constituent-count', query ? `${items.length} / ${all.length}` : `${all.length}`);
    setText('search-summary', `${all.length}개 제품 중 ${items.length}개 표시`);
    $('constituents').innerHTML = items.map(({ item, ordinal }) => {
      const dod = productDod(item);
      return `<tr><td><button class="product-button" type="button" data-product="${ordinal}" aria-haspopup="dialog">${escape(item.name)}<span class="product-subline">${escape(item.brand || '브랜드 미확보')} · ${escape(item.id)}</span></button></td><td class="stratum-cell">${escape(item.stratum_label || item.stratum || '미확보')}</td><td class="numeric weight-cell"><strong>${pct(item.weight)}</strong><div class="weight-track" aria-hidden="true"><span style="width:${finite(item.weight) ? Math.max(0, Math.min(100, item.weight * 100 / .1)) : 0}%"></span></div></td><td class="numeric">${money(item.current_price)}</td><td class="numeric ${movement(dod)}">${finite(dod) ? signed(dod) : '—'}</td><td class="numeric">${escape(readable(item.moq))} / ${escape(readable(item.mpq))}</td><td>${sourceLink(item.source_url)}</td></tr>`;
    }).join('') || '<tr><td colspan="7" class="empty-row">검색 조건에 맞는 제품이 없습니다.</td></tr>';
    $('constituents').querySelectorAll('[data-product]').forEach((button) => button.addEventListener('click', () => { const item = all[Number(button.dataset.product)]; if (item) openProduct(item, button); }));
  }
  function renderProductChart() {
    if (!state.product) return;
    chart($('product-chart'), state.product.price_history, { field: 'price', color: colors[state.selected?.id] || 'var(--accent)', unit: '원', title: `${state.product.name} 실제 관측 단가` });
    const count = arr(state.product.price_history).filter((point) => finite(point.price) && point.price > 0).length;
    setText('product-chart-note', count === 1 ? '누적 시작 · 가격 관측 1개. 전일 실측 대기 중이며 과거 이력은 추정하지 않습니다.' : `${count}개 실제 가격 관측. 동일 SKU와 고정된 최소 주문 수량·주문 배수의 단가입니다. 미확보 날짜는 선으로 연결하지 않습니다.`);
  }
  function openProduct(item, trigger) {
    state.product = item; state.lastFocus = trigger || document.activeElement;
    setText('product-eyebrow', `${labels[state.selected.id] || state.selected.id} / PRODUCT`);
    setText('product-title', item.name);
    setText('product-meta', `${item.brand || '브랜드 미확보'} · ${item.stratum_label || item.stratum || '용도 미확보'} · 상품 ID ${item.id}`);
    const dod = productDod(item);
    $('product-stats').innerHTML = [['바스켓 비중', pct(item.weight, 4), ''], ['관측 단가', money(item.current_price), ''], ['전일 대비', finite(dod) ? signed(dod) : '실측 대기', movement(dod)]].map(([key, value, cls]) => `<div class="product-stat"><span>${escape(key)}</span><strong class="${cls}">${escape(value)}</strong></div>`).join('');
    const conditions = [['최소 주문 수량 (MOQ)', readable(item.moq)], ['주문 배수 (MPQ)', readable(item.mpq)], ['원문 재고', readable(item.stock)], ['원문 납기', readable(item.lead_time)], ['판매처 내 순위', finite(item.rank) ? `${fmt(item.rank, 0)}위` : '미확보'], ['가격 기준', '원화 단가 · 부가세 / 배송비 제외']];
    if (item.unit_contract?.description) conditions.push(['고정 판매단위·규격 설명', item.unit_contract.description]);
    $('product-conditions').innerHTML = conditions.map(([key, value]) => `<div class="condition">${escape(key)}<strong>${escape(value)}</strong></div>`).join('');
    setText('product-reason', `선정 근거: ${strings(item.selection_reason).join(' · ') || '미확보'}`);
    setText('product-observed', `실제 가격 조회: ${dateTime(item.source_observed_at)}`);
    $('product-source').innerHTML = sourceLink(item.source_url, '판매처 제품 원문에서 보기 ↗');
    $('product-evidence').innerHTML = `<dt>원문 조회 시각</dt><dd>${escape(item.source_observed_at || '미확보')}</dd><dt>원문 SHA-256</dt><dd>${escape(item.source_sha256 || '미확보')}</dd>`;
    $('product-observations').innerHTML = arr(item.price_history).slice().sort((a, b) => String(b.date).localeCompare(String(a.date))).map((point) => `<tr><td>${escape(point.date)}</td><td class="numeric">${money(point.price)}</td><td>${escape(readable(point.stock))}</td></tr>`).join('') || '<tr><td colspan="3" class="empty-row">관측 대기</td></tr>';
    $('product-dialog').querySelectorAll('details').forEach((detail) => { detail.open = false; });
    state.bodyOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden';
    $('product-dialog').showModal(); $('product-dialog').scrollTop = 0; renderProductChart(); $('dialog-close').focus();
  }
  function renderSources() {
    const statuses = { active: '수집 사용', selected: '수집 사용', verified: '원문 확인', accessible: '접근 확인', available: '접근 확인', fallback: '보조 후보', candidate: '검토 후보', blocked: '접근 제한', forbidden: '접근 제한', auth_required: '인증 필요', credentials_required: '인증 필요', not_selected: '미채택', unsupported: '기준 미충족', unavailable: '수집 불가', timeout: '조회 시간 초과' };
    $('source-list').innerHTML = arr(state.data.sources).map((source) => `<article class="source-item"><header><h3>${escape(source.name)}</h3><span class="pill ${['active', 'selected', 'verified', 'accessible', 'available'].includes(source.status) ? '' : 'neutral'}">${escape(statuses[source.status] || source.status || '상태 미확보')}</span></header>${strings(source.notes).map((note) => `<p>${escape(note)}</p>`).join('')}${sourceLink(source.url, '소스 확인 ↗')}</article>`).join('') || '<p class="small muted">소스 정보 미확보</p>';
  }
  function renderMethodology() {
    const method = state.data.methodology || {};
    setText('method-summary', readable(method.summary)); setText('method-formula', readable(method.formula)); setText('price-basis', readable(method.price_basis));
    list('selection-rules', method.selection_rules); list('rebalance-rules', method.rebalance_rules); list('method-limitations', method.limitations);
  }
  function navigate(scroll = true) {
    if (!state.data) return;
    let hash = ''; try { hash = decodeURIComponent(location.hash.slice(1)); } catch { /* Ignore malformed external fragments. */ }
    selectIndex(state.data.indices.find((index) => index.id === hash) || state.data.indices[0], scroll && Boolean(hash));
  }
  function applyTheme(value) {
    document.documentElement.dataset.theme = value === 'light' ? 'light' : 'dark';
    $('theme-toggle').textContent = value === 'light' ? '☾' : '☀';
    $('theme-toggle').setAttribute('aria-label', value === 'light' ? '어두운 테마로 전환' : '밝은 테마로 전환');
  }
  try { applyTheme(localStorage.getItem('phalanx-retail-theme') || 'dark'); } catch { applyTheme('dark'); }
  $('theme-toggle').addEventListener('click', () => {
    const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; applyTheme(theme);
    try { localStorage.setItem('phalanx-retail-theme', theme); } catch { /* Theme still works when storage is unavailable. */ }
  });
  $('product-search').addEventListener('input', renderConstituents);
  $('index-range').querySelectorAll('button').forEach((button) => button.addEventListener('click', () => {
    state.range = button.dataset.days; $('index-range').querySelectorAll('button').forEach((item) => item.setAttribute('aria-pressed', String(item === button))); renderIndexChart();
  }));
  $('dialog-close').addEventListener('click', () => $('product-dialog').close());
  $('product-dialog').addEventListener('click', (event) => {
    if (event.target !== $('product-dialog')) return;
    const rect = $('product-dialog').getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) $('product-dialog').close();
  });
  $('product-dialog').addEventListener('close', () => { document.body.style.overflow = state.bodyOverflow; state.product = null; if (state.lastFocus?.isConnected) state.lastFocus.focus({ preventScroll: true }); });
  window.addEventListener('hashchange', () => navigate(true));
  let resizeFrame;
  window.addEventListener('resize', () => { cancelAnimationFrame(resizeFrame); resizeFrame = requestAnimationFrame(() => { renderIndexChart(); if ($('product-dialog').open) renderProductChart(); }); });
  async function load() {
    try {
      const response = await fetch('data.json', { cache: 'no-store', credentials: 'omit' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (data.schema_version !== 1 || !Array.isArray(data.indices) || !data.indices.length || data.indices.some((index) => !index || typeof index.id !== 'string')) throw new Error('지원하지 않는 데이터 형식');
      state.data = data;
      setText('updated-at', dateTime(data.updated_at));
      const statuses = { ok: '수집 완료', complete: '수집 완료', success: '수집 완료', partial: '부분 수집 · 커버리지 확인', failed: '수집 실패 · 이전 관측 확인' };
      setText('run-status', statuses[data.run_status] || readable(data.run_status));
      $('load-status').hidden = true; $('dashboard').hidden = false;
      renderCards(); renderSources(); renderMethodology(); navigate(false);
    } catch (error) {
      $('dashboard').hidden = true; $('load-status').hidden = false; $('load-status').className = 'notice warning';
      $('load-status').innerHTML = `관측 데이터를 불러오지 못했습니다. ${escape(error.message)} <button id="retry-load" type="button">다시 불러오기</button>`;
      setText('updated-at', '조회 실패'); $('retry-load').addEventListener('click', load);
    }
  }
  load();
})();
