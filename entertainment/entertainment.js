(function (global) {
  'use strict';
  const EMPTY = { companies: [], labels: [], artists: [], albums: [], observations: [], sources: [] };
  const KEYS = { company: 'ec', label: 'el', artist: 'ea', album: 'eb', metric: 'em', query: 'eq', view: 'ev' };
  const cache = new Map();
  const runs = new WeakMap();
  const METRICS = { first_week_album_sales: '앨범 초동 판매량', album_sales_total: '앨범 총판매량', youtube_views: 'YouTube 조회수', spotify_monthly_listeners: 'Spotify 월간 청취자', spotify_streams: 'Spotify 스트리밍', spotify_followers: 'Spotify 팔로워', tiktok_views: 'TikTok 조회수', tiktok_posts: 'TikTok 게시물', instagram_followers: 'Instagram 팔로워', concert_attendance: '공연 관객', revenue: '매출' };
  Object.assign(METRICS, {album_shipments_circle:'써클차트 음반 출고량',album_export_value:'음반 수출액',china_group_purchase:'중국 공동구매',album_sales_ex_china_group_purchase:'중국 공동구매 제외 판매량',social_platform_followers_cagr:'소셜 플랫폼 팔로워 연평균 성장률',album_sales_cagr_average:'음반 판매 평균 연평균 성장률',fandom_cagr_average:'팬덤 평균 연평균 성장률',album_revenue_change:'음반 매출 증감',merchandise_licensing_revenue_change:'MD·라이선싱 매출 증감',high_margin_revenue_change:'고마진 부문 매출 증감',high_margin_relative_metric_change:'고마진 관련 지표 증감'});
  Object.assign(METRICS, {album_export_value_yoy_label:'음반 수출액 전년 대비 증감 (표시값)',album_export_value_ytd_yoy:'음반 수출액 누계 전년 대비 증감',retail_discount_as_displayed:'상품 예시 할인율',retail_product_price_as_displayed:'상품 예시 표시 가격',spotify_chart_percentage_label:'Spotify 차트 비율 (원문 정의)'});
  const metricName = value => METRICS[value] || value || '지표 미지정';
  const escape = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const arr = value => Array.isArray(value) ? value : [];
  const name = item => item && (item.name || item.title || item.id) || '미지정';
  const number = value => typeof value === 'number' && Number.isFinite(value) ? new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 4 }).format(value) : '—';
  function href(value) {
    if (!value || typeof value !== 'string') return '';
    try { const url = new URL(value, global.location.href); return ['http:', 'https:'].includes(url.protocol) ? url.href : ''; } catch (_) { return ''; }
  }
  function normalized(data) {
    const result = { ...EMPTY, ...(data || {}), meta: data && data.meta || {} };
    Object.keys(EMPTY).forEach(key => { result[key] = arr(result[key]); });
    return result;
  }
  function readFilters(params) {
    const out = {};
    Object.entries(KEYS).forEach(([key, param]) => { out[key] = String(params.get(param) || '').slice(0, key === 'query' ? 300 : 180); });
    out.view = out.view === 'sources' ? 'sources' : 'observations';
    return out;
  }
  function writeFilters(params, filters) {
    Object.entries(KEYS).forEach(([key, param]) => { params.delete(param); if (filters && filters[key]) params.set(param, filters[key]); });
    return params;
  }
  function paths(data) {
    const companies = new Map(data.companies.map(x => [String(x.id), x]));
    const labels = new Map(data.labels.map(x => [String(x.id), x]));
    const artists = new Map(data.artists.map(x => [String(x.id), x]));
    const albums = new Map(data.albums.map(x => [String(x.id), x]));
    const artistPath = a => { const label = a && labels.get(String(a.label_id)); return { artist: a && String(a.id), label: label && String(label.id), company: label && label.company_id && String(label.company_id) || a && a.company_id && String(a.company_id) }; };
    const entity = (type, id) => {
      id = String(id || '');
      if (type === 'company') return { company: companies.has(id) ? id : null };
      if (type === 'label') { const l = labels.get(id); return { label: l && id, company: l && l.company_id && String(l.company_id) }; }
      if (type === 'artist') return artistPath(artists.get(id));
      if (type === 'album') { const a = albums.get(id); return { ...artistPath(a && artists.get(String(a.artist_id))), album: a && id }; }
      return {};
    };
    return { companies, labels, artists, albums, entity };
  }
  function scoped(path, filters) {
    return ['company', 'label', 'artist', 'album'].every(key => !filters[key] || (filters[key] === '__unassigned__' ? !path[key] : path[key] === filters[key]));
  }
  function entityName(index, observation) {
    const key = { company: 'companies', label: 'labels', artist: 'artists', album: 'albums' }[observation.entity_type];
    return key ? name(index[key].get(String(observation.entity_id))) : (observation.entity_name || '미지정');
  }
  function status(value) {
    const labels = { verified: '검증 완료', reviewed: '검토 완료', source_verified: '원문 대조', extracted: '추출값', unverified: '미검증', pending: '검토 대기', pending_review: '검토 대기', ocr: 'OCR 추출', uncertain: '귀속 미확정', unresolved: '미확정', missing: '미수집', partial: '일부 수집', complete: '수집 완료', IN_PROGRESS: '수집 진행 중', COMPLETE: '수집 완료', PARTIAL: '일부 수집', CAPTION_TRANSCRIBED: '캡션 전사', OCR_TRANSCRIBED: 'OCR 전사', IMAGE_REVIEWED: '이미지 대조', IMAGE_TRANSCRIBED:'이미지 전사',IMAGE_VISUALLY_REVIEWED:'이미지 대조',UNCERTAIN_IMAGE_FIELDS:'이미지 판독 미확정',UNCERTAIN_IMAGE_GLYPH:'숫자 판독 미확정',ESTIMATE: '추정치 E', REPORTED: '원문 발표값' };
    return labels[value] || value || '미검증';
  }
  function filterData(data, filters) {
    const index = paths(data), sourceMap = new Map(data.sources.map(s => [String(s.id), s]));
    const query = (filters.query || '').trim().toLocaleLowerCase();
    const structural = data.observations.filter(o => scoped(index.entity(o.entity_type, o.entity_id), filters));
    const observations = structural.filter(o => {
      if (filters.metric && (o.metric || o.metric_type || '') !== filters.metric) return false;
      const source = sourceMap.get(String(o.source_id)) || {};
      const artist = index.artists.get(String(o.artist_id || (o.entity_type === 'artist' ? o.entity_id : '')));
      return !query || [entityName(index, o), artist && artist.name, artist && arr(artist.aliases).join(' '), artist && arr(artist.archive_aliases).join(' '), o.original_entity_id, o.metric, metricName(o.metric), o.metric_type, o.original_text, o.period, o.as_of, source.title, source.summary, source.excerpt].join(' ').toLocaleLowerCase().includes(query);
    });
    const ids = new Set(observations.map(o => String(o.source_id)));
    const isScoped = ['company', 'label', 'artist', 'album', 'metric'].some(k => !!filters[k]);
    const sources = data.sources.filter(s => {
      const sourcePath = s.entity_type ? index.entity(s.entity_type, s.entity_id) : s.album_id ? index.entity('album', s.album_id) : s.artist_id ? index.entity('artist', s.artist_id) : s.label_id ? index.entity('label', s.label_id) : s.company_id ? index.entity('company', s.company_id) : {};
      if (isScoped && !ids.has(String(s.id)) && (filters.metric || !scoped(sourcePath, filters))) return false;
      return !query || ids.has(String(s.id)) || [s.summary, s.excerpt, s.title, s.date].join(' ').toLocaleLowerCase().includes(query);
    });
    return { index, observations, structural, sources, sourceMap };
  }
  function coverage(data) {
    const m = data.meta;
    const fields = [
      ['수집 범위', m.coverage || m.coverage_status || m.archive_status || m.completeness || m.status],
      ['기간', [m.first_date || m.period_start, m.last_date || m.period_end].filter(Boolean).join(' ~ ')],
      ['채널', m.channel || m.source_channel],
      ['갱신', m.updated_at || m.generated_at || m.as_of],
    ].filter(x => x[1]);
    const count = data.observations.filter(x => ['independently_verified', 'OFFICIAL_CROSSCHECKED'].includes(x.verification_status || x.status)).length;
    return '<section class="ent-coverage" aria-label="수집 범위와 검증 상태"><div>' + fields.map(([k, v]) => '<span><b>' + escape(k) + '</b> ' + escape(status(v)) + '</span>').join('') + '</div>' +
      '<p>RENOVA 발표값 · E는 추정치 · 수치마다 원문과 검증 상태를 확인할 수 있습니다.</p><details><summary>수집·검증 기준 보기</summary><p>' + escape(m.coverage_note || m.note || arr(m.notes).join(' ') || '아카이브 수집 범위와 수치 검증 상태는 별도로 관리합니다.') + '</p></details>' +
      '<small>공개 출처 ' + number(data.sources.length) + '건 · 관측값 ' + number(data.observations.length) + '건 · 수치 독립 대조 ' + number(count) + '건 · 모순·앨범 식별 검토 ' + number(arr(data.conflicts).length || m.conflict_count || 0) + '건. 서로 다른 지표·단위·기간을 합산하지 않습니다.</small></section>';
  }
  function hierarchy(data, filters, index) {
    const items = [
      ['company', '상장 엔터사', data.companies],
      ['label', '레이블', data.labels.filter(x => scoped(index.entity('label', x.id), { company: filters.company }))],
      ['artist', '아티스트', data.artists.filter(x => scoped(index.entity('artist', x.id), { company: filters.company, label: filters.label }))],
      ['album', '앨범', data.albums.filter(x => scoped(index.entity('album', x.id), { company: filters.company, label: filters.label, artist: filters.artist }))],
    ];
    return '<nav class="ent-hierarchy" aria-label="회사에서 앨범까지 이동">' + items.map(([key, title, rows], i) => {
      const uncertain = key === 'company' ? rows.filter(x => x.listing_status === 'UNVERIFIED_ARCHIVE_COMPANY_LABEL') : [];
      const regular = uncertain.length ? rows.filter(x => !uncertain.includes(x)) : rows;
      const option = x => '<option value="' + escape(x.id) + '"' + (filters[key] === String(x.id) ? ' selected' : '') + '>' + escape(name(x)) + (x.ticker ? ' · ' + escape(x.ticker) : '') + (x.status === 'uncertain' ? ' (미확정)' : '') + '</option>';
      const button = x => '<button class="' + (filters[key] === String(x.id) ? 'selected' : '') + '" data-pick="' + key + '" data-id="' + escape(x.id) + '" title="' + escape(name(x)) + '">' + escape(name(x)) + '</button>';
      return '<section><div class="ent-level"><span>' + (i + 1) + '</span><h3>' + title + '</h3><small>' + regular.length + '</small></div><select data-filter="' + key + '" aria-label="' + title + ' 선택"><option value="">전체 ' + title + '</option><option value="__unassigned__"' + (filters[key] === '__unassigned__' ? ' selected' : '') + '>미지정 / 귀속 미확정</option>' + regular.map(option).join('') + (uncertain.length ? '<optgroup label="미확인 회사 · 상장/법인 미대조">' + uncertain.map(option).join('') + '</optgroup>' : '') + '</select><div class="ent-options">' + regular.slice(0, 12).map(button).join('') + (regular.length > 12 ? '<small>나머지 ' + (regular.length - 12) + '개는 선택 메뉴에서 확인</small>' : '') + (rows.length ? '' : '<small>해당 단계의 명부가 아직 없습니다.</small>') + '</div>' + (uncertain.length ? '<details class="ent-unknown-companies"><summary>별도 버킷 · 회사 미확인 ' + uncertain.length + '</summary><p>원문 표기만 확인했으며 상장사 명부에 포함하지 않았습니다.</p><div class="ent-options">' + uncertain.map(button).join('') + '</div></details>' : '') + '</section>';
    }).join('') + '</nav>';
  }
  function breadcrumb(filters, index) {
    return '<nav class="ent-crumb" aria-label="선택 경로"><button data-reset>엔터 전체</button>' + ['company', 'label', 'artist', 'album'].filter(k => filters[k]).map(key => {
      const map = index[{ company: 'companies', label: 'labels', artist: 'artists', album: 'albums' }[key]];
      return '<span aria-hidden="true">›</span><button data-crumb="' + key + '">' + escape(filters[key] === '__unassigned__' ? '미지정' : name(map.get(filters[key]))) + '</button>';
    }).join('') + '</nav>';
  }
  function entityDetail(data, filters, index) {
    const type = ['album', 'artist', 'label', 'company'].find(k => filters[k] && filters[k] !== '__unassigned__');
    if (!type) return '';
    const entity = index[{company:'companies',label:'labels',artist:'artists',album:'albums'}[type]].get(filters[type]);
    if (!entity) return '';
    const official = new Map(arr(data.entity_sources).map(s => [s.id,s]));
    const links = arr(entity.source_ids).map(id => official.get(id)).filter(Boolean).map(s => sourceLink(s,s.id));
    const candidate = entity.candidate_label_id && index.labels.get(entity.candidate_label_id);
    let note = entity.explanation || (type === 'album' ? '동일 이름의 재발매·판본은 원문 근거가 확인될 때 구분합니다.' : '현재 공식 명부의 탐색 경로입니다. 과거 계약·지분·실적 귀속을 뜻하지 않습니다.');
    if (entity.listing_status === 'UNVERIFIED_ARCHIVE_COMPANY_LABEL') note = 'RENOVA 표에 적힌 회사명입니다. 정확한 법인·종목코드·상장 상태는 아직 대조하지 않았습니다.';
    if (entity.status === 'uncertain') note = (type === 'album' ? '제목·발매일·판본에 확인이 필요한 항목입니다. ' : '소속 또는 명칭이 미확정인 항목입니다. ') + (candidate ? ' 공식 명부의 후보 레이블: ' + name(candidate) + '. ' : ' ') + note;
    if (entity.release_date_review_note) note = entity.release_date_review_note + ' ' + note;
    const release = type === 'album' ? '<p>발매일: ' + escape(entity.release_date || '공식 일자 미확정') + (entity.release_date_verification === 'RENOVA_IMAGE_ONLY' ? ' <span class="ent-status">RENOVA 이미지 표기</span>' : '') + '</p>' : '';
    const related = arr(entity.related_album_ids).map(id => index.albums.get(id)).filter(Boolean).map(a => '<button data-pick="album" data-id="' + escape(a.id) + '">' + escape(name(a) + ' · ' + (a.release_date || '날짜 미확정')) + '</button>').join('');
    return '<aside class="ent-detail"><h3>' + escape(name(entity)) + (entity.ticker ? ' <small>' + escape(entity.ticker) + '</small>' : '') + '</h3>' + release + '<p>' + escape(note) + '</p>' + (related ? '<p>다른 날짜의 동일명 자료</p><div class="ent-options">' + related + '</div>' : '') + (links.length ? '<div class="ent-entity-links">공식 근거 · ' + links.join(' · ') + '</div>' : '') + '</aside>';
  }
  function sourceLink(source, id) {
    const url = source && href(source.url || source.source_url);
    return url ? '<a href="' + escape(url) + '" target="_blank" rel="noopener noreferrer">' + escape(source.title || id || '원문') + ' ↗</a>' : '<span>' + escape(id || '출처 미지정') + '</span>';
  }
  function observationContext(o) {
    const scope = o.series_variant || o.product_title_raw || '';
    const warning = o.metric === 'spotify_chart_percentage_label' ? '분모·시계열 정의 미확정. 시장점유율로 확정하지 않습니다.' : /^retail_/.test(o.metric) ? '소매 상품 예시입니다. 회사 실현 ASP·판매량·매출과 다릅니다.' : o.metric === 'social_platform_followers_cagr' ? '플랫폼 합산 팔로워 기반입니다. 고유 팬 수와 다릅니다.' : '';
    return (scope ? '<small class="ent-role">' + escape(scope) + '</small>' : '') + (warning ? '<small class="ent-role">' + escape(warning) + '</small>' : '') + (o.forecast_raw ? '<small class="ent-warning">원문 조건값 ' + escape(o.forecast_raw) + ' · 실적 미관측</small>' : '') + (o.partial_period_sales_raw ? '<small class="ent-warning">' + escape(o.partial_period_days_observed || '') + '일차 원문값 ' + escape(o.partial_period_sales_raw) + ' · 완성 초동 미관측</small>' : '') + (o.release_date_review ? '<small class="ent-warning">동일명 앨범 발매일 검토 필요</small>' : '') + (o.note ? '<details><summary>정의·주의사항</summary><p>' + escape(o.note) + '</p></details>' : '');
  }
  function observationsTable(rows, index, sourceMap, limit) {
    if (!rows.length) return '<div class="ent-empty">선택한 범위에 공개된 관측값이 없습니다. 미지정 항목 또는 원문 목록을 확인하세요.</div>';
    const sorted = rows.slice().sort((a, b) => String(b.as_of || b.period || '').localeCompare(String(a.as_of || a.period || '')));
    return '<div class="ent-table-wrap"><table><caption class="ent-sr">선택 범위 관측값과 출처</caption><thead><tr><th>기간 / 기준일</th><th>대상</th><th>지표</th><th class="num">수치</th><th>단위</th><th>검증</th><th>출처</th></tr></thead><tbody>' + sorted.slice(0, limit).map(o => '<tr' + (o.conflict ? ' class="ent-conflict"' : '') + '><td>' + escape(o.period || o.as_of || '기간 미상') + (!o.period && o.as_of ? '<br><small>게시일 기준</small>' : '') + '</td><td>' + escape(entityName(index, o)) + '</td><td>' + escape(metricName(o.metric || o.metric_type)) + observationContext(o) + (o.comparison_role ? '<small class="ent-role">' + escape(o.comparison_role === 'previous' ? '비교 이전' : o.comparison_role === 'current' ? '비교 현재' : o.comparison_role) + '</small>' : '') + (o.original_text ? '<details><summary>원문 표현</summary><p>' + escape(o.original_text) + '</p><small>' + escape(o.extraction_method || '') + '</small></details>' : '') + '</td><td class="num">' + (o.value_relation === 'GT' ? '&gt; ' : o.value_relation === 'GE' ? '≥ ' : '') + number(o.value) + (o.status === 'ESTIMATE' ? '<small class="ent-estimate">E · 추정</small>' : '') + '</td><td>' + escape(o.unit || '단위 미상') + '</td><td><span class="ent-status">' + escape(status(o.verification_status || o.status)) + '</span>' + (o.conflict ? '<small class="ent-warning">원문 내 모순</small>' : '') + '</td><td>' + sourceLink(o.source_url ? { ...(sourceMap.get(String(o.source_id)) || {}), url: o.source_url } : sourceMap.get(String(o.source_id)), o.source_id) + '</td></tr>').join('') + '</tbody></table></div>' + (rows.length > limit ? '<button class="ent-more" data-more>다음 100개 · ' + (rows.length - limit) + '개 남음</button>' : '');
  }
  function timeline(rows, limit) {
    if (!rows.length) return '<div class="ent-empty">선택한 범위의 출처가 없습니다.</div>';
    return '<div class="ent-timeline">' + rows.slice().sort((a, b) => String(b.date || '').localeCompare(String(a.date || ''))).slice(0, limit).map(s => '<article><time>' + escape(s.date || '날짜 미상') + '</time><div><h3>' + sourceLink(s, s.id) + '</h3><p>' + escape(s.summary || s.excerpt || '요약 미작성 · 원문 링크에서 확인') + '</p><small>' + escape(s.publisher || 'RENOVA') + ' · 첨부 ' + number(s.media_count == null ? arr(s.media).length : s.media_count) + '개' + (s.local_source_id ? ' · 아카이브 ' + escape(s.local_source_id) : '') + '</small></div></article>').join('') + '</div>' + (rows.length > limit ? '<button class="ent-more" data-more>다음 100개 · ' + (rows.length - limit) + '개 남음</button>' : '');
  }
  function chart(rows, filters, index) {
    if (!filters.metric || !(filters.artist || filters.album || filters.company || filters.label)) return '';
    const series = new Map();
    rows.forEach(o => {
      if (typeof o.value !== 'number' || !Number.isFinite(o.value) || !o.period || !/^\d{4}(?:[AE]|-\d{2}(?:-\d{2})?)$/.test(o.period)) return;
      const key = [o.entity_type, o.entity_id, o.metric || o.metric_type, o.unit].join('|');
      if (!series.has(key)) series.set(key, []); series.get(key).push(o);
    });
    if (series.size !== 1) return '';
    const points = [...series.values()][0].sort((a, b) => a.period.localeCompare(b.period));
    if (points.length < 2 || new Set(points.map(x => x.period)).size !== points.length) return '';
    const min = Math.min(...points.map(x => x.value)), max = Math.max(...points.map(x => x.value));
    const x = i => 30 + i * 940 / (points.length - 1), y = v => 135 - (v - min) * 110 / (max - min || 1);
    return '<section class="ent-chart"><h3>' + escape(entityName(index, points[0])) + ' · ' + escape(filters.metric) + '</h3><small>단위 ' + escape(points[0].unit || '미상') + ' · 관측일 순서, 원값 표시 · ' + escape(points[0].period) + ' ~ ' + escape(points[points.length - 1].period) + '</small><svg viewBox="0 0 1000 160" role="img" aria-label="' + escape(filters.metric) + ' 관측 시계열"><line x1="30" y1="140" x2="970" y2="140" class="ent-axis"/><polyline points="' + points.map((p, i) => x(i) + ',' + y(p.value)).join(' ') + '"/><g>' + points.map((p, i) => '<circle cx="' + x(i) + '" cy="' + y(p.value) + '" r="3"><title>' + escape(p.period) + ': ' + number(p.value) + ' ' + escape(p.unit) + '</title></circle>').join('') + '</g></svg><div class="ent-chart-range"><span>최솟값 ' + number(min) + '</span><span>최댓값 ' + number(max) + '</span></div></section>';
  }
  async function mount(root, options) {
    if (!root) return;
    options = options || {};
    const token = {};
    runs.set(root, token);
    root.innerHTML = '<div class="ent-root"><div class="ent-empty" role="status">엔터 아카이브를 불러오는 중입니다…</div></div>';
    let data;
    try {
      if (options.data) data = normalized(options.data);
      else {
        const url = String(options.dataUrl || new URL('entertainment/data.json', options.base || global.location.href));
        if (!cache.has(url)) cache.set(url, fetch(url, { credentials: 'same-origin' }).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }).then(normalized).catch(e => { cache.delete(url); throw e; }));
        data = await cache.get(url);
      }
    } catch (_) {
      if (runs.get(root) === token) root.innerHTML = '<div class="ent-root"><div class="ent-empty" role="alert">엔터 데이터를 불러오지 못했습니다. 연결과 데이터 파일을 확인한 뒤 다시 시도하세요.</div></div>';
      return;
    }
    if (runs.get(root) !== token) return;
    let filters = { view: 'observations', ...(options.filters || {}) }, limit = 100;
    function update(key, value) {
      const levels = ['company', 'label', 'artist', 'album'];
      filters[key] = value;
      const pos = levels.indexOf(key);
      if (pos >= 0) levels.slice(pos + 1).forEach(k => { filters[k] = ''; });
      if (pos >= 0) filters.metric = '';
      limit = 100;
      if (options.onChange) options.onChange({ ...filters });
      draw();
    }
    function draw() {
      if (runs.get(root) !== token) return;
      const view = filterData(data, filters), metricList = [...new Set(view.structural.map(o => o.metric || o.metric_type || '').filter(Boolean))].sort();
      const workbook = href(data.meta.workbook_url || data.meta.excel_url || '');
      root.innerHTML = '<div class="ent-root"><header class="ent-header"><div><span class="ent-eyebrow">PHALANX · ENTERTAINMENT</span><h2>엔터 아카이브</h2><p>상장사에서 앨범까지, 출처와 수치를 함께 확인합니다.</p></div>' + (workbook ? '<a class="ent-download" href="' + escape(workbook) + '" download>엑셀 다운로드 ↓</a>' : '<button class="ent-download" data-csv>선택 수치 CSV ↓</button>') + '</header>' + coverage(data) + breadcrumb(filters, view.index) + hierarchy(data, filters, view.index) + entityDetail(data,filters,view.index) +
        '<div class="ent-toolbar"><div role="group" aria-label="보기"><button data-view="observations" class="' + (filters.view !== 'sources' ? 'selected' : '') + '">관측값 ' + number(view.observations.length) + '</button><button data-view="sources" class="' + (filters.view === 'sources' ? 'selected' : '') + '">출처 타임라인 ' + number(view.sources.length) + '</button></div><label><span class="ent-sr">지표</span><select data-filter="metric"><option value="">모든 지표</option>' + metricList.map(x => '<option' + (filters.metric === x ? ' selected' : '') + ' value="' + escape(x) + '">' + escape(metricName(x)) + '</option>').join('') + '</select></label><form class="ent-search"><label><span class="ent-sr">아카이브 검색</span><input name="query" placeholder="아티스트·지표·출처 검색" value="' + escape(filters.query || '') + '"></label><button type="submit">검색</button></form></div>' +
        (filters.view === 'sources' ? timeline(view.sources, limit) : chart(view.observations, filters, view.index) + observationsTable(view.observations, view.index, view.sourceMap, limit)) +
        '<footer class="ent-note">이미지 원본과 전문은 개인 아카이브에 보관합니다. 이 화면은 출처 링크·요약·구조화한 관측값을 제공합니다. 미검증 수치는 확정 실적으로 취급하지 않습니다.</footer></div>';
      root.querySelectorAll('[data-filter]').forEach(el => el.addEventListener('change', () => update(el.dataset.filter, el.value)));
      root.querySelectorAll('[data-pick]').forEach(el => el.addEventListener('click', () => update(el.dataset.pick, el.dataset.id)));
      root.querySelectorAll('[data-view]').forEach(el => el.addEventListener('click', () => update('view', el.dataset.view)));
      root.querySelectorAll('[data-crumb]').forEach(el => el.addEventListener('click', () => update(el.dataset.crumb, filters[el.dataset.crumb])));
      root.querySelector('[data-reset]').addEventListener('click', () => { filters = { view: filters.view }; update('query', ''); });
      root.querySelector('form').addEventListener('submit', event => { event.preventDefault(); update('query', root.querySelector('input[name="query"]').value); });
      const more = root.querySelector('[data-more]'); if (more) more.addEventListener('click', () => { limit += 100; draw(); });
      const csv = root.querySelector('[data-csv]'); if (csv) csv.addEventListener('click', () => {
        const fields = ['id', 'entity_type', 'entity_id', 'metric', 'value', 'value_relation', 'unit', 'period', 'as_of', 'comparison_role', 'status', 'verification_status', 'conflict', 'source_id', 'original_text'];
        const cell = value => { let s = value == null ? '' : String(value); if (typeof value === 'string' && /^[\s]*[=+@-]/.test(s)) s = "'" + s; return '"' + s.replace(/"/g, '""') + '"'; };
        const text = '\ufeff' + [fields.join(','), ...view.observations.map(o => fields.map(k => cell(o[k])).join(','))].join('\r\n');
        const url = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }));
        const a = document.createElement('a'); a.href = url; a.download = 'phalanx-entertainment-observations.csv'; a.hidden = true; document.body.appendChild(a); a.click(); setTimeout(() => { a.remove(); URL.revokeObjectURL(url); }, 1000);
      });
    }
    draw();
  }
  const api = { mount, cancel: root => { if (root) runs.delete(root); }, readFilters, writeFilters, filterData, normalized, paths };
  global.PHXEntertainment = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
