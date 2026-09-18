(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const state = { data: null, selected: null, product: null, historyGroups: [], historyPeriods: [] };
  const colors = { ssd: 'var(--ssd)', hdd: 'var(--hdd)', dram: 'var(--dram)' };
  const brandColors = ['#71bca8', '#86aee0', '#b699d6', '#d5af75', '#da979f', '#89b5b9', '#9caa7c', '#b2aabf', '#bc9b88', '#869db6'];
  const number = (value, digits = 2) => Number.isFinite(value) ? value.toLocaleString('ko-KR', { maximumFractionDigits: digits, minimumFractionDigits: digits }) : '—';
  const percent = (value) => Number.isFinite(value) ? `${(value * 100).toLocaleString('ko-KR', { maximumFractionDigits: 4 })}%` : '—';
  const won = (value) => Number.isFinite(value) ? `${value.toLocaleString('ko-KR', { maximumFractionDigits: 0 })}원` : '미확보';
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (s) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[s]));
  const array = (value) => Array.isArray(value) ? value : [];
  const notes = (value) => Array.isArray(value) ? value : typeof value === 'string' && value ? [value] : [];
  const text = (id, value) => { $(id).textContent = value ?? '—'; };
  const signed = (value) => Number.isFinite(value) ? `${value > 0 ? '+' : ''}${number(value)}%` : '—';
  function safeUrl(value) {
    try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; } catch { return null; }
  }
  function sourceLink(value, label = '원문 ↗') {
    const url = safeUrl(value);
    return url ? `<a class="source-link" href="${escape(url)}" target="_blank" rel="noopener noreferrer">${escape(label)}</a>` : '<span class="missing">원문 미확보</span>';
  }
  function list(id, values) { $(id).innerHTML = array(values).map((v) => `<li>${escape(v)}</li>`).join(''); }
  function dateTime(value) {
    const date = new Date(value);
    if (!value || !Number.isFinite(date.getTime())) return '미확보';
    return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(date) + ' KST';
  }
  function dayTime(value) {
    if (!/^\d{4}-\d{2}(?:-\d{2})?$/.test(String(value))) return null;
    const result = Date.parse(value.length === 7 ? `${value}-01T00:00:00Z` : `${value}T00:00:00Z`);
    return Number.isFinite(result) ? result : null;
  }
  function staleDays(value) {
    const timestamp = dayTime(value);
    return timestamp === null ? null : Math.floor((Date.now() - timestamp) / 86400000);
  }
  function isGap(before, after, frequency) {
    if (frequency === 'mixed') {
      if (after.bridge_from === before.date && before.frequency === 'monthly' && after.frequency === 'daily') return false;
      if (before.frequency !== after.frequency || before.basis !== after.basis) return true;
      return isGap(before, after, after.frequency || 'daily');
    }
    if (frequency === 'monthly') {
      const month = (v) => Number(v.slice(0, 4)) * 12 + Number(v.slice(5, 7));
      return month(after.date) - month(before.date) > 1;
    }
    const threshold = frequency === 'weekly' ? 8 : 1.1;
    return (after.time - before.time) / 86400000 > threshold;
  }
  function chart(host, values, options = {}) {
    const { field = 'value', color = 'var(--accent)', unit = '지수', frequency = 'daily', miniature = false, baseline = null, title = '가격 관측 시계열', formatter = (v) => number(v), bars = false } = options;
    const points = array(values).map((p) => ({ ...p, time: dayTime(p.date), plotted: p[field] })).filter((p) => p.time !== null).sort((a, b) => a.time - b.time);
    const valid = points.filter((p) => Number.isFinite(p.plotted));
    if (!valid.length) {
      host.innerHTML = miniature ? '<div class="empty-chart">관측 대기</div>' : '<div class="empty-chart"><strong>표시할 관측값이 없습니다</strong><span>확보되지 않은 가격이나 지수는 추정하지 않습니다.</span></div>';
      return;
    }
    const width = miniature ? 340 : Math.max(270, Math.round(host.getBoundingClientRect().width || window.innerWidth - 80));
    const height = miniature ? 65 : bars ? 150 : width < 500 ? 260 : 290;
    const margin = miniature ? { l: 4, r: 4, t: 8, b: 7 } : { l: unit === '원' ? 85 : 61, r: 27, t: 29, b: 39 };
    let min = Math.min(...valid.map((p) => p.plotted));
    let max = Math.max(...valid.map((p) => p.plotted));
    if (bars) { min = Math.min(0, min); max = Math.max(0, max); }
    let padding = max === min ? Math.max(Math.abs(max) * 0.025, unit === '원' ? 1000 : 1) : (max - min) * 0.14;
    min -= padding; max += padding;
    if (min < 0 && valid.every((p) => p.plotted >= 0)) min = 0;
    const first = points[0].time, last = points[points.length - 1].time;
    const plotWidth = width - margin.l - margin.r;
    const plotHeight = height - margin.t - margin.b;
    const x = (p) => margin.l + (last === first ? plotWidth / 2 : (p.time - first) / (last - first) * plotWidth);
    const y = (value) => margin.t + (max - value) / (max - min) * plotHeight;
    const tickLabel = (value) => {
      if (unit === '원') return Math.round(value).toLocaleString('ko-KR');
      const decimals = max - min < 10 ? 1 : 0;
      return value.toLocaleString('ko-KR', { maximumFractionDigits: decimals });
    };
    let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escape(title)}"><title>${escape(title)}</title>`;
    if (!miniature) {
      svg += `<text x="${margin.l}" y="13" class="chart-label">${escape(unit)}</text>`;
      const tickCount = bars ? 2 : 4;
      for (let i = 0; i <= tickCount; i++) {
        const value = min + (max - min) * i / tickCount;
        svg += `<line x1="${margin.l}" y1="${y(value)}" x2="${width - margin.r}" y2="${y(value)}" class="grid-line"/><text x="${margin.l - 11}" y="${y(value) + 3}" text-anchor="end" class="chart-label">${escape(tickLabel(value))}</text>`;
      }
      const step = Math.max(1, Math.ceil((points.length - 1) / Math.max(1, Math.floor(plotWidth / 115))));
      const labels = points.filter((p, i) => i === 0 || i === points.length - 1 || i % step === 0);
      let lastLabelX = -Infinity;
      for (let i = 0; i < labels.length; i++) {
        const p = labels[i];
        const endpoint = points[points.length - 1];
        if (p !== endpoint && labels.length > 1 && x(endpoint) - x(p) < 90) continue;
        if (x(p) - lastLabelX < 90 && labels.length > 1) continue;
        lastLabelX = x(p);
        svg += `<text x="${x(p)}" y="${height - 15}" text-anchor="middle" class="chart-label">${escape(p.date)}</text>`;
      }
      if (Number.isFinite(baseline) && baseline >= min && baseline <= max) svg += `<line x1="${margin.l}" y1="${y(baseline)}" x2="${width - margin.r}" y2="${y(baseline)}" class="baseline"/>`;
    }
    if (bars) {
      const barWidth = Math.min(38, plotWidth / Math.max(points.length * 1.8, 1));
      valid.forEach((p) => {
        const tooltip = `${p.date}\n${formatter(p.plotted)}`;
        svg += `<rect x="${x(p) - barWidth / 2}" y="${Math.min(y(p.plotted), y(0))}" width="${barWidth}" height="${Math.max(1, Math.abs(y(p.plotted) - y(0)))}" rx="2" fill="${color}" opacity=".7" tabindex="0" role="img" aria-label="${escape(tooltip)}" data-tip="${escape(tooltip)}"><title>${escape(tooltip)}</title></rect>`;
      });
    } else {
      const mixed = frequency === 'mixed';
      const pointKind = (p) => mixed && p.basis === 'historical_reconstruction' ? 'historical' : 'live';
      let segments = [], current = [], previous = null, currentKind = null;
      const flush = () => { if (current.length) segments.push({ points: current, kind: currentKind }); current = []; };
      for (const p of points) {
        if (!Number.isFinite(p.plotted)) { flush(); previous = null; continue; }
        const gap = previous && isGap(previous, p, frequency);
        const edgeKind = previous && mixed && p.bridge_from === previous.date && previous.frequency === 'monthly' && p.frequency === 'daily' ? 'bridge' : pointKind(p);
        if (!previous || gap) { flush(); current = [p]; currentKind = pointKind(p); }
        else if (edgeKind !== currentKind) { flush(); current = [previous, p]; currentKind = edgeKind; }
        else current.push(p);
        previous = p;
      }
      flush();
      for (const segment of segments) {
        if (segment.points.length > 1) svg += `<path d="${segment.points.map((p, i) => `${i ? 'L' : 'M'}${x(p).toFixed(2)},${y(p.plotted).toFixed(2)}`).join(' ')}" class="data-line ${mixed ? `${segment.kind}-line` : ''}" data-segment="${escape(segment.kind)}" fill="none" stroke="${color}" stroke-width="${miniature ? 2.4 : 2.6}"/>`;
      }
      valid.forEach((p) => {
        const kind = pointKind(p);
        const label = mixed ? kind === 'historical' ? '월간 과거 재구성' : '일간 직접 관측' : '';
        const tooltip = `${p.date}${label ? ` · ${label}` : ''}\n${formatter(p.plotted)}${unit === '지수' ? ' pt' : ''}${Number.isFinite(p.coverage_count) ? `\n포함 제품 ${p.coverage_count}개` : ''}${Number.isFinite(p.coverage_weight) ? `\n${mixed && kind === 'historical' ? '최초 비중 확보율' : '비중 커버리지'} ${percent(p.coverage_weight)}` : ''}${mixed && p.bridge_from ? `\n${p.bridge_from} 월간 값에서 일간으로 연결` : ''}`;
        svg += `<circle class="data-point" data-basis="${escape(p.basis || '')}" data-date="${escape(p.date)}" cx="${x(p)}" cy="${y(p.plotted)}" r="${miniature ? 2.8 : 3.7}" fill="${kind === 'historical' ? 'var(--surface)' : color}"${kind === 'historical' ? ` style="stroke:${color}"` : ''}${miniature ? '' : ` tabindex="0" role="img" aria-label="${escape(tooltip)}" data-tip="${escape(tooltip)}"`}><title>${escape(tooltip)}</title></circle>`;
      });
    }
    svg += '</svg>';
    host.innerHTML = svg;
    if (!miniature) {
      const tooltip = document.createElement('div');
      tooltip.className = 'chart-tooltip'; tooltip.hidden = true; tooltip.setAttribute('role', 'status');
      host.append(tooltip);
      host.querySelectorAll('[data-tip]').forEach((point) => {
        const show = () => {
          tooltip.textContent = point.dataset.tip;
          tooltip.hidden = false;
          const p = point.getBoundingClientRect(), h = host.getBoundingClientRect();
          const half = tooltip.offsetWidth / 2 + 6;
          tooltip.style.left = `${Math.max(half, Math.min(h.width - half, p.left + p.width / 2 - h.left))}px`;
          tooltip.style.top = `${p.top - h.top - 9}px`;
        };
        point.addEventListener('pointerenter', show); point.addEventListener('focus', show);
        point.addEventListener('pointerleave', () => { tooltip.hidden = true; }); point.addEventListener('blur', () => { tooltip.hidden = true; });
      });
    }
  }
  function renderCards() {
    $('index-cards').innerHTML = state.data.indices.map((index, ordinal) => {
      const level = Number.isFinite(index.value) ? number(index.value) : '—';
      const change = Number.isFinite(index.value) ? `<span class="change">${signed(index.value - 100)}</span> ${String(index.base_date).length === 7 ? '기준월' : '기준일'} 대비` : '산출 조건 확인 중';
      return `<button type="button" class="index-card" data-id="${escape(index.id)}" data-index="${ordinal}" aria-pressed="false" aria-controls="index-detail"><span class="card-top"><span class="card-label">${escape(String(index.id).toUpperCase())}</span><span class="card-arrow" aria-hidden="true">↗</span></span><span class="card-subtitle">${escape(index.name)}</span><span class="card-number">${level}</span><span class="card-change">${change}</span><span class="mini-chart" id="spark-${ordinal}" aria-hidden="true"></span><span class="card-footer"><span>${escape(index.as_of || '관측일 미확보')}</span><span>${escape(index.coverage_count ?? 0)} / ${escape(index.basket_count ?? 0)}개 · ${percent(index.coverage_weight)}</span></span></button>`;
    }).join('');
    state.data.indices.forEach((index, i) => chart($(`spark-${i}`), index.series, { miniature: true, frequency: 'mixed', color: colors[index.id] || 'var(--accent)' }));
    $('index-cards').querySelectorAll('button').forEach((button) => button.addEventListener('click', () => {
      const index = state.data.indices[Number(button.dataset.index)];
      if (index) { history.pushState(null, '', `#${encodeURIComponent(index.id)}`); navigateFromHash(); }
    }));
  }
  function navigateFromHash() {
    let hash;
    try { hash = decodeURIComponent(location.hash.slice(1)).toLowerCase(); } catch { return; }
    let target;
    const ordinal = state.data.indices.findIndex((index) => index.id === hash);
    if (ordinal >= 0) { selectIndex(ordinal); target = $('index-detail'); }
    else if (hash === 'germany') target = $('germany');
    if (target) {
      target.focus({ preventScroll: true });
      target.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
    }
  }
  function renderBrandWeights(index) {
    const brands = new Map();
    for (const item of array(index.constituents)) {
      const name = item.brand || '브랜드 미확보';
      if (Number.isFinite(item.weight)) brands.set(name, (brands.get(name) || 0) + item.weight);
    }
    const entries = [...brands].sort((a, b) => b[1] - a[1]);
    $('brand-weights').innerHTML = `<div class="brand-bar" aria-hidden="true">${entries.map(([name, weight], i) => `<span style="width:${Math.max(0, Math.min(100, weight * 100))}%;background:${brandColors[i % brandColors.length]}" title="${escape(name)} ${percent(weight)}"></span>`).join('')}</div><div class="brand-legend">${entries.map(([name, weight], i) => `<span><i style="background:${brandColors[i % brandColors.length]}" aria-hidden="true"></i>${escape(name)} <strong>${percent(weight)}</strong></span>`).join('')}</div>`;
  }
  function selectIndex(ordinal) {
    const index = state.data.indices[ordinal];
    if (!index) return;
    state.selected = index;
    $('index-cards').querySelectorAll('button').forEach((button) => button.setAttribute('aria-pressed', String(Number(button.dataset.index) === ordinal)));
    text('detail-eyebrow', `${String(index.id).toUpperCase()} / BASKET DETAIL`);
    text('detail-heading', index.name);
    const complete = index.status === 'ok' && Number.isFinite(index.value);
    text('detail-status', complete ? '관측 완료' : '산출 조건 미충족');
    $('detail-status').className = `pill ${complete ? 'ok' : 'warning'}`;
    const meta = [['바스켓', index.basket_id || '미확보'], [String(index.base_date).length === 7 ? '기준월' : '기준일', index.base_date || '미확보'], ['최근 관측', index.as_of || '미확보'], ['현재 비중 커버리지', percent(index.coverage_weight)], ['현재 제품 커버리지', `${index.coverage_count ?? 0} / ${index.basket_count ?? 0}개`]];
    $('detail-meta').innerHTML = meta.map(([key, value]) => `<span>${escape(key)}<strong>${escape(value)}</strong></span>`).join('');
    const warnings = [];
    if (!complete) warnings.push('현재 지수는 산출 조건을 충족하지 않아 공표되지 않았습니다. 확보한 제품 관측은 아래에서 확인할 수 있습니다.');
    if (Number.isFinite(index.coverage_weight) && index.coverage_weight < 1 - 1e-9) warnings.push(`미확보 비중 ${percent(1 - index.coverage_weight)}. 결측 가격을 0원으로 대체하지 않습니다.`);
    const age = staleDays(index.as_of);
    if (age !== null && age >= 2) warnings.push(`최근 관측일로부터 ${age}일 경과했습니다. 현재 시점의 가격으로 해석하지 마세요.`);
    if (age === null) warnings.push('최근 관측일을 확인할 수 없습니다.');
    $('index-notice').hidden = !warnings.length; $('index-notice').className = 'notice warning'; text('index-notice', warnings.join(' '));
    text('index-base', index.base_date ? `${index.base_date} = 100` : '기준일 미확보');
    renderIndexChart(index);
    renderHistoricalCoverage(index);
    renderBrandWeights(index);
    const rebalance = index.rebalance || {};
    const rebalanceStatus = { initial: '최초 바스켓 · 관측 축적 중', deferred: '검토 보류', completed: '검토 완료', pending: '검토 대기', applied: '새 바스켓 적용' };
    $('rebalance').innerHTML = `<p class="rebalance-date">${escape(rebalance.next_review || '일정 미확보')}</p><p>${escape(rebalanceStatus[rebalance.status] || rebalance.status || '')}</p>${notes(rebalance.notes).map((note) => `<p>${escape(note)}</p>`).join('')}`;
    $('product-search').value = '';
    renderConstituents();
  }
  function renderIndexChart(index) {
    chart($('index-chart'), index.series, { frequency: 'mixed', color: colors[index.id] || 'var(--accent)', baseline: 100, title: `${index.name} 월간 과거 재구성과 일간 직접 관측 지수` });
  }
  function renderHistoricalCoverage(index) {
    const historyData = index.history || {};
    const monthly = array(historyData.series);
    $('history-coverage').hidden = !monthly.length;
    $('history-intro').hidden = !monthly.length;
    $('history-coverage').open = false;
    text('index-history-caption', monthly.length ? `${historyData.base_date || index.base_date}~${historyData.last_month || '미확보'}: 월간 과거 재구성 · ${historyData.daily_start_date || '미확보'}부터: 일간 직접 관측. 명시된 월간→일간 연결 구간 외의 결측은 연결하지 않습니다. 월간 점 사이의 선은 일간 관측을 뜻하지 않습니다.` : '확보된 가격 관측을 표시합니다. 결측 구간은 선을 연결하지 않습니다.');
    if (!monthly.length) { state.historyPeriods = []; return; }
    const count = historyData.initial_coverage_count ?? monthly[0].coverage_count;
    const weight = historyData.initial_coverage_weight ?? monthly[0].coverage_weight;
    $('history-intro').className = `notice ${Number.isFinite(weight) && weight < 1 - 1e-9 ? 'warning' : ''}`;
    $('history-intro').innerHTML = `<strong>과거 시작월 ${escape(historyData.base_date || index.base_date)}: ${escape(count ?? '—')} / ${escape(index.basket_count ?? '—')}개 · 최초 바스켓 비중 ${percent(weight)} 확보</strong><p>${escape(historyData.note || '최초 선정 바스켓의 비중으로 과거를 재구성했습니다. 당시의 판매 구성비를 재현한 지수가 아니며, 확보되지 않은 가격을 보간하지 않습니다.')}</p><p>과거 부분 표본은 확보 제품 사이에서 비중을 다시 나누므로, 구간 적용 비중이 현재 24개 바스켓의 SKU·브랜드 상한을 초과할 수 있습니다.</p>`;
    state.historyPeriods = monthly.map((point, i) => ({ ...point, from_date: point.from_date || (i ? monthly[i - 1].date : null), kind: i ? '월간 연결' : '시작월' }));
    if (historyData.bridge) {
      const bridge = historyData.bridge;
      const point = array(index.series).find((p) => p.date === bridge.date && p.bridge_from === bridge.from_date);
      state.historyPeriods.push({ ...bridge, value: bridge.value ?? point?.value, kind: '월간 → 일간 연결' });
    }
    $('history-periods').innerHTML = state.historyPeriods.map((period, i) => `<tr><td><button class="period-button" type="button" data-history-period="${i}" aria-controls="history-members">${escape(period.date)}</button></td><td class="numeric">${number(period.value)}</td><td class="numeric">${escape(period.coverage_count ?? '—')} / ${escape(index.basket_count ?? '—')}</td><td class="numeric">${percent(period.coverage_weight)}</td><td class="period-kind">${escape(period.kind)}</td></tr>`).join('');
    $('history-month').innerHTML = state.historyPeriods.map((period, i) => `<option value="${i}">${escape(period.date)} · ${escape(period.kind)}</option>`).join('');
    $('history-periods').querySelectorAll('[data-history-period]').forEach((button) => button.addEventListener('click', () => {
      $('history-month').value = button.dataset.historyPeriod;
      renderHistoricalMembers();
      $('history-month').focus({ preventScroll: true });
      $('history-match-summary').scrollIntoView({ block: 'nearest' });
    }));
    renderHistoricalMembers();
  }
  function renderHistoricalMembers() {
    const period = state.historyPeriods[Number($('history-month').value)];
    if (!period) return;
    const members = array(period.constituents).slice().sort((a, b) => (b.weight || 0) - (a.weight || 0));
    text('history-match-summary', `${period.from_date ? `${period.from_date} → ` : ''}${period.date} · ${period.kind} · ${period.coverage_count ?? members.length}개 · 최초 바스켓 비중 ${percent(period.coverage_weight)} 확보. 구간 적용 비중은 포함 제품의 최초 비중을 합계 100%로 다시 나눈 값입니다.`);
    $('history-members').innerHTML = members.length ? members.map((item) => `<tr><td>${escape(item.name)}<span class="product-subline">상품 ID ${escape(item.id)}</span></td><td class="numeric">${percent(item.weight)}</td><td class="numeric">${percent(item.initial_weight)}</td><td>${sourceLink(item.source_url)}</td></tr>`).join('') : '<tr><td colspan="4" class="missing">구성 제품이 확보되지 않았습니다.</td></tr>';
    $('history-periods').querySelectorAll('[data-history-period]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.historyPeriod === $('history-month').value)));
  }
  function renderConstituents() {
    const query = $('product-search').value.trim().toLocaleLowerCase('ko-KR');
    const all = array(state.selected?.constituents);
    const visible = all.map((item, i) => ({ item, i })).filter(({ item }) => `${item.name || ''} ${item.brand || ''} ${item.family || ''} ${item.generation || ''} ${item.stratum || ''}`.toLocaleLowerCase('ko-KR').includes(query)).sort((a, b) => (b.item.weight || 0) - (a.item.weight || 0));
    text('constituent-count', query ? `${visible.length} / ${all.length}개` : `${all.length}개`);
    const maxWeight = Math.max(...all.map((item) => Number.isFinite(item.weight) ? item.weight : 0), 0.01);
    $('constituents').innerHTML = visible.length ? visible.map(({ item, i }) => `<tr><td><button class="product-button" type="button" data-product="${i}" aria-haspopup="dialog">${escape(item.name)}<span class="product-subline">${escape([item.brand, item.family].filter(Boolean).join(' · '))}</span></button></td><td>${escape(item.generation || '미확보')}<span class="product-subline">${Number.isFinite(item.capacity_gb) ? `${escape(item.capacity_gb)} GB` : '용량 미확보'}${item.stratum ? ` · ${escape(item.stratum)}` : ''}</span></td><td class="numeric weight-cell"><strong>${percent(item.weight)}</strong><div class="weight-track" aria-hidden="true"><span style="width:${Math.max(0, Math.min(100, (item.weight || 0) / maxWeight * 100))}%"></span></div></td><td class="numeric ${Number.isFinite(item.current_price) ? '' : 'missing'}">${won(item.current_price)}</td><td class="numeric">${Number.isFinite(item.rank) ? `${escape(item.rank)}위` : '<span class="missing">미확보</span>'}</td><td class="numeric">${Number.isFinite(item.seller_count) ? `${escape(item.seller_count)}개` : '<span class="missing">미확보</span>'}</td><td>${sourceLink(item.source_url)}</td></tr>`).join('') : '<tr><td colspan="7" class="missing">검색 결과가 없습니다.</td></tr>';
    $('constituents').querySelectorAll('[data-product]').forEach((button) => button.addEventListener('click', () => openProduct(all[Number(button.dataset.product)])));
  }
  function historyLabel(frequency, basis, windowMonths) {
    const frequencies = { daily: '일간', weekly: '주간', monthly: '월간' };
    const bases = { live_lowest: '직접 관측 최저가', danawa_chart: '다나와 원문 차트' };
    return `${bases[basis] || basis || '가격 기준 미확보'} · ${frequencies[frequency] || frequency || '주기 미확보'}${Number.isFinite(windowMonths) ? ` · ${windowMonths}개월 창` : ''}`;
  }
  function openProduct(item) {
    state.product = item;
    text('product-eyebrow', `${String(state.selected.id).toUpperCase()} / PRODUCT DETAIL`);
    text('product-title', item.name);
    text('product-meta', [item.brand, item.family, item.generation, Number.isFinite(item.capacity_gb) ? `${item.capacity_gb} GB` : null, item.stratum, item.id ? `상품 ID ${item.id}` : null].filter(Boolean).join(' · '));
    $('product-stats').innerHTML = [['바스켓 비중', percent(item.weight)], ['최근 관측 최저가', won(item.current_price)], ['인기순위', Number.isFinite(item.rank) ? `${item.rank}위` : '미확보']].map(([key, value]) => `<div class="product-stat"><span>${escape(key)}</span><strong>${escape(value)}</strong></div>`).join('');
    text('product-reason', item.selection_reason ? `선정 근거: ${item.selection_reason}` : '제품 선정 근거 미확보');
    const anomalyNotes = array(item.price_anomalies).map((a) => `${a.date}: ${a.status === 'source_cross_checked' ? '급변 가격 교차 확인' : '급변 가격 미확인'} (${won(a.previous_price)} → ${won(a.quoted_price)})`);
    text('product-quality-note', [item.source_observed_at ? `실제 가격 조회: ${dateTime(item.source_observed_at)}` : '', ...anomalyNotes].filter(Boolean).join(' · '));
    const groups = new Map();
    for (const point of array(item.price_history)) {
      const key = `${point.basis || ''}|${point.frequency || ''}|${point.window_months || ''}`;
      if (!groups.has(key)) groups.set(key, { frequency: point.frequency, basis: point.basis, windowMonths: point.window_months, points: [] });
      groups.get(key).points.push(point);
    }
    const priority = (group) => (group.points.filter((p) => Number.isFinite(p.price)).length > 1 ? 10000 : 0) + (group.basis === 'danawa_chart' ? group.frequency === 'monthly' ? 3000 : 2000 : 1000) + (group.windowMonths || 0);
    state.historyGroups = [...groups.values()].sort((a, b) => priority(b) - priority(a));
    $('history-series').innerHTML = state.historyGroups.length ? state.historyGroups.map((group, i) => `<option value="${i}">${escape(historyLabel(group.frequency, group.basis, group.windowMonths))}</option>`).join('') : '<option value="0">관측 계열 없음</option>';
    $('history-series').disabled = state.historyGroups.length < 2;
    $('product-link').innerHTML = `${sourceLink(item.source_url, '다나와 제품 원문에서 보기 ↗')}<p class="small muted">관측 최저가와 원문 현재가는 수집 시각·판매처·배송 조건에 따라 다를 수 있습니다.</p>`;
    $('product-dialog').showModal();
    renderProductHistory();
  }
  function renderProductHistory() {
    const group = state.historyGroups[Number($('history-series').value)];
    chart($('product-chart'), group?.points || [], { field: 'price', unit: '원', color: colors[state.selected.id] || 'var(--accent)', frequency: group?.frequency || 'daily', title: `${state.product.name} ${group ? historyLabel(group.frequency, group.basis, group.windowMonths) : '가격 흐름'}`, formatter: won });
    const note = group?.basis === 'danawa_chart' ? '다나와 원문 차트의 제품별 과거 가격입니다. 월간 원문 가격은 과거 지수 재구성에 사용하며, 월간·주간 값은 해당 주기의 관측으로 표시합니다.' : '직접 관측한 제품별 최저가입니다. 관측 시점의 제품 가격이며, 지수 자체의 수익률이나 제품 판매량을 뜻하지 않습니다.';
    text('product-history-note', `${group ? `${historyLabel(group.frequency, group.basis, group.windowMonths)} · ${array(group.points).filter((p) => Number.isFinite(p.price)).length}개 가격 관측. ` : ''}${note} 서로 다른 조회 창은 혼합하지 않습니다. 결측 기간은 선을 연결하지 않습니다.`);
  }
  function renderGermany() {
    const data = state.data.germany || {};
    const valid = array(data.series).filter((p) => Number.isFinite(p.value)).sort((a, b) => String(a.date).localeCompare(String(b.date)));
    const latest = valid[valid.length - 1];
    text('germany-title', `${data.title || '독일 DDR5 소매가격'}${data.version ? ` · ${data.version}` : ''}`);
    text('germany-value', latest ? number(latest.value, Number.isInteger(latest.value) ? 0 : 2) : '—');
    text('germany-change', latest ? `${signed(latest.value - 100)} · 기준 대비` : '관측 미확보');
    text('germany-base', data.base_label || '기준 미확보');
    $('germany-source').innerHTML = sourceLink(data.source_url, '원문 보고서 ↗');
    $('germany-meta').innerHTML = `<div>최근 기간<strong>${escape(latest?.date || '미확보')}</strong></div><div>발행일<strong>${escape(data.published_at || '미확보')}</strong></div><div>가격 관측일<strong>${escape(data.observed_at || '미확보')}</strong></div>${data.retrieved_at ? `<div>자료 확인<strong>${escape(dateTime(data.retrieved_at))}</strong></div>` : ''}`;
    chart($('germany-chart'), data.series, { color: 'var(--germany)', frequency: 'monthly', baseline: 100, title: `${data.title || '독일 DDR5 소매가격'} — ${data.base_label || '지수'}` });
    chart($('germany-mom-chart'), data.series, { field: 'reported_mom_pct', color: 'var(--germany)', frequency: 'monthly', unit: '%', formatter: (v) => signed(v), bars: true, title: '독일 DDR5 원문 보고 전월 변동률' });
    text('germany-method', data.method || '산출 방법 미확보');
    $('germany-notes').innerHTML = `<ul>${array(data.notes).map((note) => `<li>${escape(note)}</li>`).join('')}</ul>`;
    $('germany-revision').hidden = !data.revision_note;
    $('germany-revision').innerHTML = data.revision_note ? `<strong>원문 개정 안내</strong><p>${escape(data.revision_note)} ${sourceLink(data.revision_source_url, '개정 원문 ↗')}</p>` : '';
    const anomalies = array(data.source_anomalies);
    $('germany-anomalies').hidden = !anomalies.length;
    $('germany-anomalies').innerHTML = anomalies.length ? `<strong>원문 기간 표기 불일치</strong>${anomalies.map((item) => `<p>월 제목 ${escape(item.period || '미확보')} · 관측일 원문 “${escape(item.source_date_literal || '미확보')}”<br>${escape(item.action === 'index mapped by header; date not used' ? '지수는 표 머리글의 월에 배정하고, 불일치한 원문 날짜는 관측일로 사용하지 않았습니다.' : item.action || '원문 불일치를 기록했습니다.')}</p>`).join('')}` : '';
    const buckets = array(data.buckets);
    $('germany-bucket-section').hidden = !buckets.length;
    if (buckets.length) {
      const dates = [...new Set(buckets.flatMap((bucket) => Object.keys(bucket.prices || {})))].sort();
      $('germany-buckets').innerHTML = `<table><thead><tr><th>제품군</th><th class="numeric">비중</th>${dates.map((date) => `<th class="numeric">${escape(date)} · EUR</th>`).join('')}<th>원문</th></tr></thead><tbody>${buckets.map((bucket) => `<tr><td>${escape(bucket.name)}</td><td class="numeric">${percent(bucket.weight)}</td>${dates.map((date) => `<td class="numeric">${Number.isFinite(bucket.prices?.[date]) ? number(bucket.prices[date]) : '—'}</td>`).join('')}<td>${sourceLink(bucket.source_url)}</td></tr>`).join('')}</tbody></table>`;
    }
  }
  function renderMethodology() {
    const data = state.data.methodology || {};
    text('method-version', data.version || '버전 미확보');
    text('method-summary', data.summary);
    text('method-formula', data.formula);
    text('price-basis', data.price_basis);
    list('selection-rules', data.selection_rules);
    list('rebalance-rules', data.rebalance_rules);
    list('method-limitations', data.limitations);
  }
  function initTheme() {
    let theme;
    try { theme = localStorage.getItem('phx:retail-memory:theme'); } catch { /* Storage is optional. */ }
    if (!['light', 'dark'].includes(theme)) theme = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    const apply = (value) => {
      document.documentElement.dataset.theme = value;
      $('theme-toggle').setAttribute('aria-label', value === 'dark' ? '밝은 테마로 전환' : '어두운 테마로 전환');
      $('theme-toggle').innerHTML = `${value === 'dark' ? '☀' : '☾'}<span class="theme-word">테마</span>`;
    };
    apply(theme);
    $('theme-toggle').addEventListener('click', () => {
      const value = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      apply(value); try { localStorage.setItem('phx:retail-memory:theme', value); } catch { /* Storage is optional. */ }
    });
  }
  async function start() {
    initTheme();
    $('product-search').addEventListener('input', renderConstituents);
    $('history-month').addEventListener('change', renderHistoricalMembers);
    $('dialog-close').addEventListener('click', () => $('product-dialog').close());
    $('product-dialog').addEventListener('click', (event) => {
      if (event.target !== $('product-dialog')) return;
      const bounds = $('product-dialog').getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) $('product-dialog').close();
    });
    $('history-series').addEventListener('change', renderProductHistory);
    try {
      const response = await fetch('data.json', { cache: 'no-cache' });
      if (!response.ok) throw new Error(`데이터 응답 ${response.status}`);
      const data = await response.json();
      if (data.schema_version !== 1 || !Array.isArray(data.indices)) throw new Error('지원되지 않는 데이터 형식');
      state.data = data;
      $('dashboard').hidden = false;
      text('updated-at', dateTime(data.updated_at));
      text('dataset-version', `${data.methodology?.name || '소매가격 지수'} · ${data.methodology?.version || '버전 미확보'}`);
      renderCards();
      selectIndex(0);
      if (!data.indices.length) $('index-detail').hidden = true;
      renderGermany(); renderMethodology();
      navigateFromHash();
      window.addEventListener('hashchange', navigateFromHash);
      window.addEventListener('popstate', navigateFromHash);
      let resizeTimer;
      window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
          if (state.selected) renderIndexChart(state.selected);
          renderGermany();
          if ($('product-dialog').open) renderProductHistory();
        }, 120);
      });
      const updated = Date.parse(data.updated_at);
      const age = Number.isFinite(updated) ? Math.floor((Date.now() - updated) / 86400000) : null;
      if (age !== null && age >= 2) {
        $('load-status').className = 'notice warning';
        text('load-status', `데이터가 마지막으로 갱신된 지 ${age}일 경과했습니다. 아래 최근 관측일과 가격 커버리지를 확인하세요.`);
      } else if (!Number.isFinite(updated)) {
        $('load-status').className = 'notice warning';
        text('load-status', '데이터 갱신 시각을 확인할 수 없습니다. 각 지수의 최근 관측일을 확인하세요.');
      } else $('load-status').hidden = true;
    } catch (error) {
      text('updated-at', '불러오기 실패');
      $('load-status').className = 'notice warning';
      text('load-status', '관측 데이터를 불러오지 못했습니다. 잠시 후 새로고침해 주세요. 데이터가 없을 때 예시 가격이나 추정 지수를 표시하지 않습니다.');
      console.error('Retail memory dashboard:', error);
    }
  }
  start();
})();
