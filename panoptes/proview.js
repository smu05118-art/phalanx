// Panoptes ProView 모듈 — 티커바 · 뉴스플로우 · 뉴스 지도레이어 · TTS · MY SIGNALS 덱
// 데이터: data/market.json (panoptes_market.py) · data/news.json (panoptes_news.py)
window.PV = (function () {
  let MK = null, NW = null, _mapLayerOn = true, _sigBuilt = false;
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const UP = '#ff5d6c', DN = '#4ea1ff', FLAT = '#8a93a3';          // 국내 관례: 상승 빨강·하락 파랑
  const cc = v => v > 0 ? UP : v < 0 ? DN : FLAT;
  const sign = v => (v > 0 ? '+' : '') + v;
  const fmt = (v, dp) => v == null ? '—' : Number(v).toLocaleString('en-US', {minimumFractionDigits: dp ?? 2, maximumFractionDigits: dp ?? 2});
  const ago = ts => { const m = Math.round((Date.now()/1000 - ts) / 60);
    return m < 1 ? '방금' : m < 60 ? m + '분 전' : m < 1440 ? Math.round(m/60) + '시간 전' : Math.round(m/1440) + '일 전'; };
  const LS = { get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } },
               set(k, v) { localStorage.setItem(k, JSON.stringify(v)); } };

  // ───────── 데이터 로드 ─────────
  async function boot() {
    const bust = '?t=' + Math.floor(Date.now() / 6e5);
    [MK, NW] = await Promise.all([
      fetch('data/market.json' + bust).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch('data/news.json' + bust).then(r => r.ok ? r.json() : null).catch(() => null),
    ]);
    if (MK) renderTicker();
    if (NW) { renderNewsFlow(); waitMap(); }
    wireRightSwitch();
  }

  // ───────── ① MARKET SIGNAL — 헤더 티커바 ─────────
  function tickerItems() {
    const pick = [];
    const g = MK.groups || {};
    (g.indices || []).forEach(x => pick.push(x));
    (g.fx || []).slice(0, 2).forEach(x => pick.push(x));
    (g.commod || []).forEach(x => pick.push(x));
    (g.rates || []).forEach(x => pick.push(x));
    (g.crypto || []).forEach(x => pick.push(x));
    return pick;
  }
  function renderTicker() {
    const bar = $('tickerbar'); if (!bar) return;
    const seq = tickerItems().map(x =>
      `<span class="tk" onclick="switchTab('sig')"><b>${esc(x.name)}</b> ${fmt(x.price, x.dp)} <i style="color:${cc(x.chg1d)};font-style:normal">${x.chg1d==null?'—':sign(x.chg1d)+'%'}</i></span>`
    ).join('<span class="tksep">·</span>');
    bar.innerHTML = `<div class="tkwrap">${seq}<span class="tksep">·</span>${seq}<span class="tksep">·</span></div>`;
    bar.hidden = false;
  }

  // ───────── ② NEWS FLOW — 우측 패널 ─────────
  function wireRightSwitch() {
    document.querySelectorAll('.rsw').forEach(el => el.onclick = () => {
      document.querySelectorAll('.rsw').forEach(x => x.classList.toggle('on', x === el));
      $('rpaneEv').hidden = el.dataset.r !== 'ev';
      $('rpaneNews').hidden = el.dataset.r !== 'news';
    });
    const tb = $('ttsNews'); if (tb) tb.onclick = speakNews;
  }
  function renderNewsFlow() {
    const box = $('rpaneNews'); if (!box) return;
    const now = Date.now() / 1000;
    const items = (NW.items || []).slice(0, 90);
    let lastDay = '';
    box.innerHTML = items.map((it, i) => {
      const d = new Date(it.ts * 1000);
      const day = d.toISOString().slice(5, 10).replace('-', '/');
      const hd = day !== lastDay ? `<div class="nfday">${day}</div>` : '';
      lastDay = day;
      const brk = now - it.ts < 7200 ? '<span class="nfbrk">속보</span>' : '';
      const geo = it.lat != null ? `<span class="nfgeo" data-i="${i}" title="지도에서 보기">📍</span>` : '';
      return `${hd}<div class="nfcard${now - it.ts < 7200 ? ' fresh' : ''}">
        <div class="nft">${brk}<a href="${esc(it.l)}" target="_blank" rel="noopener">${esc(it.t)}</a></div>
        <div class="nfm"><span class="nftopic">${esc(it.topic)}</span><span>${esc(it.src)}</span><span>${ago(it.ts)}</span>${geo}</div>
      </div>`;
    }).join('') || '<p class="hint">뉴스 데이터 준비 중…</p>';
    box.querySelectorAll('.nfgeo').forEach(el => el.onclick = () => flyNews(items[+el.dataset.i]));
    const upd = $('nfUpdated'); if (upd) upd.textContent = (NW.updated || '').slice(5, 16).replace('T', ' ');
  }
  function flyNews(it) {
    if (!window.MAP || it.lat == null) return;
    switchTab('map');
    MAP.flyTo({center: [it.lon, it.lat], zoom: Math.max(MAP.getZoom(), 3.6), speed: 0.9});
    new maplibregl.Popup({closeButton: true, offset: 10, maxWidth: '280px'})
      .setLngLat([it.lon, it.lat])
      .setHTML(`<b>${esc(it.t)}</b><br><a href="${esc(it.l)}" target="_blank" rel="noopener" style="color:var(--accent)">기사 열기 ↗</a>`)
      .addTo(MAP);
  }

  // ───────── ③ LIVE MAP — 지오태그 뉴스 레이어 ─────────
  function waitMap() {
    let tries = 0;
    const t = setInterval(() => {
      tries++;
      try {
        // 정상 경로: 이벤트 레이어 위에 얹기. 타일 로드가 늦으면 스타일만 준비돼도 추가.
        if (window.MAP && MAP.getSource &&
            (MAP.getSource('events') || (tries > 16 && MAP.isStyleLoaded()))) {
          clearInterval(t); addNewsLayer();
        }
      } catch (e) { /* 맵 스타일 로드 전 — 다음 틱 재시도 */ }
    }, 500);
  }
  let _geoItems = [];
  function newsGeo() {
    const now = Date.now() / 1000;
    _geoItems = (NW.items || []).filter(it => it.lat != null && now - it.ts < 86400);
    return {type: 'FeatureCollection', features: _geoItems
      .map((it, i) => ({type: 'Feature', geometry: {type: 'Point', coordinates: [it.lon, it.lat]},
        properties: {i, fresh: now - it.ts < 7200 ? 1 : 0}}))};
  }
  function addNewsLayer() {
    if (MAP.getSource('news')) return;
    const gj = newsGeo();
    MAP.addSource('news', {type: 'geojson', data: gj});
    MAP.addLayer({id: 'news-glow', type: 'circle', source: 'news', paint: {
      'circle-radius': ['case', ['==', ['get', 'fresh'], 1], 9, 6], 'circle-color': '#2bc0d4',
      'circle-blur': 1, 'circle-opacity': 0.35}});
    MAP.addLayer({id: 'news-dot', type: 'circle', source: 'news', paint: {
      'circle-radius': 3, 'circle-color': '#0a0e14', 'circle-stroke-color': '#2bc0d4',
      'circle-stroke-width': 1.6, 'circle-opacity': 0.9}});
    MAP.on('click', 'news-dot', e => {
      const it = _geoItems[e.features[0].properties.i];
      if (it) flyNews(it);
    });
    MAP.on('mouseenter', 'news-dot', () => MAP.getCanvas().style.cursor = 'pointer');
    MAP.on('mouseleave', 'news-dot', () => MAP.getCanvas().style.cursor = '');
    const n = gj.features.length;
    const cnt = $('newsLayerN'); if (cnt) cnt.textContent = n;
    const row = $('newsLayerToggle');
    if (row) row.onclick = () => {
      _mapLayerOn = !_mapLayerOn; row.classList.toggle('off', !_mapLayerOn);
      ['news-glow', 'news-dot'].forEach(l => MAP.setLayoutProperty(l, 'visibility', _mapLayerOn ? 'visible' : 'none'));
    };
  }

  // ───────── ④ TTS BRIEFING ─────────
  let _voice = null;
  function pickVoice() {
    const vs = speechSynthesis.getVoices();
    _voice = vs.find(v => v.lang === 'ko-KR' && /Yuna|유나/.test(v.name)) || vs.find(v => v.lang.startsWith('ko')) || null;
  }
  if ('speechSynthesis' in window) {
    pickVoice();
    speechSynthesis.onvoiceschanged = pickVoice;
  }
  function speak(text) {
    if (!('speechSynthesis' in window)) return alert('이 브라우저는 음성 합성을 지원하지 않습니다.');
    stopSpeak();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'ko-KR'; u.rate = 1.06; if (_voice) u.voice = _voice;
    u.onend = u.onerror = () => { const p = $('ttsPill'); if (p) p.hidden = true; };
    speechSynthesis.speak(u);
    let p = $('ttsPill');
    if (!p) {
      p = document.createElement('div'); p.id = 'ttsPill';
      p.innerHTML = '🔊 재생 중 — <b>정지</b>';
      p.onclick = stopSpeak;
      document.body.appendChild(p);
    }
    p.hidden = false;
  }
  function stopSpeak() {
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    const p = $('ttsPill'); if (p) p.hidden = true;
  }
  function speakEvent(id) {
    const e = (window.EVENTS || []).find(x => x._id === id); if (!e) return;
    speak(`${e.title}. ${e.country || ''}, 심각도 ${e._sev}. ${e.summary || ''}`);
  }
  function speakNews() {
    if (!NW) return;
    const tops = (NW.items || []).slice(0, 8).map((it, i) => `${i + 1}. ${it.t}`).join('. ');
    speak('파놉티스 뉴스 브리핑. ' + tops);
  }
  function speakBriefing() { speak(briefingText().join(' ')); }

  // ───────── ⑤ MY SIGNALS 덱 ─────────
  const WIDGETS = [
    ['brief', '📋 시그널 브리핑'], ['watch', '⭐ 관심종목'], ['cover', '🔁 연속보도'],
    ['kw', '🔥 키워드 트렌드'], ['mkt', '📈 시장·예측'], ['radar', '🛡 리스크 레이더'],
  ];
  function widgetOn() { return LS.get('pv_widgets', Object.fromEntries(WIDGETS.map(([k]) => [k, true]))); }

  function briefingText() {
    const out = [];
    if (MK) {
      const g = MK.groups || {};
      const all = [...(g.indices || []), ...(g.fx || []), ...(g.commod || []), ...(g.rates || [])].filter(x => x.chg1d != null);
      const movers = all.slice().sort((a, b) => Math.abs(b.chg1d) - Math.abs(a.chg1d)).slice(0, 3);
      if (movers.length) out.push('시장: ' + movers.map(x => `${x.name} ${sign(x.chg1d)}%`).join(', ') + '.');
      const krw = (g.fx || []).find(x => x.name === 'USD/KRW');
      if (krw) out.push(`원달러 ${fmt(krw.price, 1)}원.`);
    }
    const evs = (window.EVENTS || []);
    const now = Date.now();
    const hot = evs.filter(e => e._sev >= 4 && e.date && now - Date.parse(e.date) < 7 * 864e5);
    if (hot.length) {
      const top = hot.slice().sort((a, b) => b._sev - a._sev)[0];
      out.push(`지난 7일 고심각도 이벤트 ${hot.length}건. 최고: ${top.title}.`);
    }
    if (NW) {
      const kws = (NW.keywords || []).slice(0, 3).map(k => k.w);
      if (kws.length) out.push('급상승 키워드: ' + kws.join(', ') + '.');
      const v = (NW.velocity || [])[0];
      if (v) out.push(`보도 최다 토픽: ${v.topic}, 24시간 ${v.n24}건.`);
    }
    if (MK && (MK.predict || []).length) {
      const p = MK.predict[0];
      out.push(`예측시장: "${p.q}" 확률 ${p.yes}%${p.chg ? ` (${sign(p.chg)}%p)` : ''}.`);
    }
    return out.length ? out : ['데이터 수집 대기 중입니다.'];
  }

  function spark(vals, color, w, h) {
    if (!vals || vals.length < 2) return '';
    w = w || 110; h = h || 26;
    const mn = Math.min(...vals), mx = Math.max(...vals), rg = (mx - mn) || 1;
    const pts = vals.map((v, i) => `${(2 + (w - 4) * i / (vals.length - 1)).toFixed(1)},${(2 + (h - 4) * (1 - (v - mn) / rg)).toFixed(1)}`).join(' ');
    return `<svg viewBox="0 0 ${w} ${h}" style="width:${w}px;height:${h}px;flex:0 0 auto"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.4"/></svg>`;
  }

  function wBrief() {
    return `<div class="sigw" id="sw-brief"><div class="sigh"><b>📋 시그널 브리핑</b>
      <button class="ttsbtn" onclick="PV.speakBriefing()">🔊 듣기</button></div>
      ${briefingText().map(t => `<p class="sbp">${esc(t)}</p>`).join('')}
      <div class="sigfoot">규칙 기반 자동 요약 · 투자 판단 아님</div></div>`;
  }
  function wWatch() {
    const off = new Set(LS.get('pv_watch_off', []));
    const rows = (MK && MK.watch || []).map(x => {
      const hid = off.has(x.symbol);
      return `<div class="wrow${hid ? ' woff' : ''}" data-sym="${esc(x.symbol)}">
        <span class="wnm">${esc(x.name)}</span>
        ${spark(x.spark && x.spark.slice(-40), cc(x.chg1d))}
        <span class="wpx">${fmt(x.price, /\.(KS|KQ)$/.test(x.symbol) ? 0 : 2)}</span>
        <span class="wch" style="color:${cc(x.chg1d)}">${x.chg1d==null?'—':sign(x.chg1d)+'%'}</span>
      </div>`;
    }).join('');
    return `<div class="sigw" id="sw-watch"><div class="sigh"><b>⭐ 관심종목</b>
      <span class="sigedit" id="watchEdit">⚙ 편집</span></div>
      <div id="watchRows">${rows || '<p class="hint">market.json 대기 중</p>'}</div>
      <div class="sigfoot">종목 추가·삭제: <code>panoptes/data/watchlist.json</code> 편집 → 다음 수집 반영</div></div>`;
  }
  function wCover() {
    const rows = (NW && NW.velocity || []).map(v => {
      const mx = Math.max(...v.buckets, 1);
      const bars = v.buckets.map(b => `<i style="height:${Math.max(8, 100 * b / mx)}%"></i>`).join('');
      const tr = v.trend === 'up' ? ['▲ 가속', UP] : v.trend === 'down' ? ['▼ 둔화', DN] : ['― 유지', FLAT];
      return `<div class="cvrow"><span class="cvt">${esc(v.topic)}</span>
        <span class="cvbars">${bars}</span>
        <span class="cvn">${v.n24}건/24h</span>
        <span class="cvtr" style="color:${tr[1]}">${tr[0]}</span></div>`;
    }).join('');
    return `<div class="sigw" id="sw-cover"><div class="sigh"><b>🔁 연속보도</b></div>${rows || '<p class="hint">데이터 대기 중</p>'}
      <div class="sigfoot">토픽별 보도량(6시간 버킷×72h) · 24h vs 직전 평균</div></div>`;
  }
  function wKw() {
    const kws = NW && NW.keywords || [];
    const mx = Math.max(...kws.map(k => k.n), 1);
    const chips = kws.map(k =>
      `<span class="kwchip" style="font-size:${(11 + 7 * k.n / mx).toFixed(1)}px;border-color:${k.d > 2 ? UP + '66' : 'var(--line)'}">${esc(k.w)}<i>${k.n}${k.d > 0 ? ' ↑' : ''}</i></span>`).join('');
    return `<div class="sigw" id="sw-kw"><div class="sigh"><b>🔥 키워드 트렌드</b></div>
      <div class="kwcloud">${chips || '<p class="hint">데이터 대기 중</p>'}</div>
      <div class="sigfoot">최근 24시간 헤드라인 빈도 · ↑ = 직전 48시간 대비 급상승</div></div>`;
  }
  function wMkt() {
    const g = MK && MK.groups || {};
    const col = (title, arr) => `<div class="mkcol"><div class="mkh">${title}</div>` +
      (arr || []).map(x => `<div class="mkrow"><span>${esc(x.name)}</span><b>${fmt(x.price, x.dp)}</b>
        <i style="color:${cc(x.chg1d)}">${x.chg1d==null?'—':sign(x.chg1d)+'%'}</i></div>`).join('') + '</div>';
    const preds = (MK && MK.predict || []).slice(0, 8).map(p =>
      `<a class="pdrow" href="${esc(p.url)}" target="_blank" rel="noopener">
        <span class="pdq">${esc(p.q)}</span>
        <span class="pdbar"><i style="width:${Math.min(100, p.yes)}%"></i></span>
        <b>${p.yes}%</b><i class="pdchg" style="color:${cc(p.chg || 0)}">${p.chg==null?'':sign(p.chg)+'p'}</i></a>`).join('');
    return `<div class="sigw wide" id="sw-mkt"><div class="sigh"><b>📈 시장·예측</b>
      <span class="sigts">${esc((MK && MK.updated || '').slice(5, 16).replace('T', ' '))}</span></div>
      <div class="mkgrid">${col('지수', g.indices)}${col('환율·금리', [...(g.fx||[]), ...(g.rates||[])])}${col('원자재·크립토', [...(g.commod||[]), ...(g.crypto||[])])}</div>
      <div class="mkh" style="margin-top:12px">🎲 예측시장 (${esc((MK && MK.predict && MK.predict[0] || {}).src || '—')})</div>
      <div>${preds || '<p class="hint">예측시장 데이터 대기 중</p>'}</div></div>`;
  }
  const REGIONS_MAP = {
    '동유럽': ['Ukraine', 'Russia', 'Belarus', 'Moldova'],
    '중동': ['Israel', 'Palestine', 'Lebanon', 'Syria', 'Iran', 'Iraq', 'Yemen', 'Jordan', 'Saudi Arabia', 'Red Sea'],
    '동아시아': ['Taiwan', 'China', 'North Korea', 'South Korea', 'Japan', 'Philippines', 'South China Sea'],
    '남아시아': ['Myanmar', 'Pakistan', 'India', 'Afghanistan', 'Bangladesh', 'Kashmir'],
    '아프리카': ['Sudan', 'Mali', 'Niger', 'Burkina Faso', 'Nigeria', 'Somalia', 'Ethiopia', 'DR Congo', 'DRC', 'Libya', 'Chad', 'Kenya', 'Mozambique', 'Cameroon', 'Benin', 'Togo', 'South Sudan'],
    '중남미·기타': [],
  };
  function regionOf(country) {
    for (const [r, list] of Object.entries(REGIONS_MAP)) if (list.includes(country)) return r;
    return '중남미·기타';
  }
  function radarScores(maxAgeDays) {
    const now = Date.now();
    const sc = Object.fromEntries(Object.keys(REGIONS_MAP).map(r => [r, 0]));
    (window.EVENTS || []).forEach(e => {
      const t = Date.parse(e.date); if (isNaN(t)) return;
      const age = (now - t) / 864e5; if (age < 0 || age > 90) return;
      if (maxAgeDays != null && age < maxAgeDays) return;   // 최근 N일 제외본(전주 비교용)
      sc[regionOf(e.country)] += Math.pow(e._sev, 1.5) * Math.exp(-age / 30);
    });
    return sc;
  }
  function wRadar() {
    const cur = radarScores(null), prev = radarScores(7);
    const keys = Object.keys(REGIONS_MAP);
    const mx = Math.max(...keys.map(k => cur[k]), 1);
    const cx = 130, cy = 118, R = 88, n = keys.length;
    const pt = (i, f) => { const a = -Math.PI / 2 + i * 2 * Math.PI / n;
      return [cx + R * f * Math.cos(a), cy + R * f * Math.sin(a)]; };
    const grid = [0.33, 0.66, 1].map(f =>
      `<polygon points="${keys.map((_, i) => pt(i, f).map(v => v.toFixed(1)).join(',')).join(' ')}" fill="none" stroke="var(--line)" stroke-width="0.7"/>`).join('');
    const axes = keys.map((_, i) => { const [x, y] = pt(i, 1);
      return `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="var(--line)" stroke-width="0.6"/>`; }).join('');
    const poly = keys.map((k, i) => pt(i, Math.max(0.04, cur[k] / mx)).map(v => v.toFixed(1)).join(',')).join(' ');
    const labels = keys.map((k, i) => { const [x, y] = pt(i, 1.22);
      const d = cur[k] - prev[k];
      const arrow = d > mx * 0.06 ? `<tspan fill="${UP}"> ▲</tspan>` : d < -mx * 0.02 ? `<tspan fill="${DN}"> ▼</tspan>` : '';
      return `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="middle" font-size="10.5" fill="var(--dim)">${k}${arrow}</text>`; }).join('');
    const top = keys.map(k => [k, cur[k]]).sort((a, b) => b[1] - a[1]).slice(0, 3);
    const drivers = (window.EVENTS || []).filter(e => e._sev >= 4)
      .sort((a, b) => (b.date || '').localeCompare(a.date || '')).slice(0, 4)
      .map(e => `<div class="rddrv" onclick="switchTab('map');select('${e._id}',true)">S${e._sev} · ${esc(e.title)}</div>`).join('');
    return `<div class="sigw" id="sw-radar"><div class="sigh"><b>🛡 리스크 레이더</b></div>
      <svg viewBox="0 0 260 240" style="width:100%;max-width:300px;display:block;margin:0 auto">
        ${grid}${axes}<polygon points="${poly}" fill="rgba(255,93,108,.18)" stroke="${UP}" stroke-width="1.6"/>${labels}</svg>
      <div class="rdtop">${top.map(([k, v]) => `<span>${k} <b>${(100 * v / mx).toFixed(0)}</b></span>`).join('')}</div>
      ${drivers}
      <div class="sigfoot">이벤트 심각도^1.5 × 30일 반감 가중 합산 · ▲▼ = 최근 7일 기여</div></div>`;
  }

  function loadSignals(force) {
    const box = $('sigview'); if (!box) return;
    if (_sigBuilt && !force) return;
    _sigBuilt = true;
    const on = widgetOn();
    const chips = WIDGETS.map(([k, label]) =>
      `<span class="wchip${on[k] ? ' on' : ''}" data-w="${k}">${label}</span>`).join('');
    const R = { brief: wBrief, watch: wWatch, cover: wCover, kw: wKw, mkt: wMkt, radar: wRadar };
    const body = WIDGETS.filter(([k]) => on[k]).map(([k]) => { try { return R[k](); } catch (e) { console.warn('widget', k, e); return ''; } }).join('');
    box.innerHTML = `<div class="sightop"><h2>📡 MY SIGNALS</h2>
        <button class="ttsbtn" onclick="PV.speakBriefing()">🔊 브리핑 듣기</button>
        <span class="sigts">뉴스 ${esc((NW && NW.updated || '—').slice(5, 16).replace('T', ' '))} · 시세 ${esc((MK && MK.updated || '—').slice(5, 16).replace('T', ' '))}</span></div>
      <div class="wchips">${chips}</div>
      <div class="siggrid">${body || '<p class="hint">모든 위젯이 꺼져 있습니다. 위 칩을 눌러 켜세요.</p>'}</div>
      <p class="hint" style="margin-top:14px">위젯 구성은 이 브라우저에 저장됩니다 · 열람 이력 기반 자동 활성화 없음 (직접 선택)</p>`;
    box.querySelectorAll('.wchip').forEach(el => el.onclick = () => {
      const o = widgetOn(); o[el.dataset.w] = !o[el.dataset.w]; LS.set('pv_widgets', o); loadSignals(true);
    });
    const we = $('watchEdit');
    if (we) we.onclick = () => {
      box.querySelectorAll('#watchRows .wrow').forEach(r => {
        r.classList.add('editing');
        r.onclick = () => {
          const off = new Set(LS.get('pv_watch_off', []));
          const s = r.dataset.sym;
          off.has(s) ? off.delete(s) : off.add(s);
          LS.set('pv_watch_off', [...off]); loadSignals(true);
        };
      });
    };
  }

  boot();
  return { speak, stopSpeak, speakEvent, speakNews, speakBriefing, loadSignals };
})();
