(function (root) {
  'use strict';
  const PAGE_SIZE = 100;
  const MAX_SHARD_BYTES = 5 * 1024 * 1024;
  const SHARD_CONCURRENCY = 4;
  // Reviewed public source hosts only. Subdomains do not inherit permission.
  const HOSTS = new Set(['eia.gov','www.eia.gov','lbl.gov','www.lbl.gov','emp.lbl.gov','eta-publications.lbl.gov','gridtracker.lbl.gov','data.openei.org','openei.org','www.nrcan.gc.ca','nrcan.gc.ca','natural-resources.canada.ca','open.canada.ca','canada.ca','www.canada.ca','www150.statcan.gc.ca','www.statcan.gc.ca','statcan.gc.ca','www.ieso.ca','ieso.ca','www.aeso.ca','aeso.ca','www.hydroquebec.com','hydroquebec.com','www.bchydro.com','bchydro.com','www.cer-rec.gc.ca','cer-rec.gc.ca','www.cne.gob.mx','cne.gob.mx','www.gob.mx','gob.mx','datos.gob.mx','www.datos.gob.mx','api.datos.gob.mx','repodatos.atdt.gob.mx','datos.energia.gob.mx','www.cre.gob.mx','cre.gob.mx','www.sener.gob.mx','sener.gob.mx','www.inegi.org.mx','inegi.org.mx','raw.githubusercontent.com','globalenergymonitor.org','www.globalenergymonitor.org','gem.wiki','www.gem.wiki','saskpower.com','www.saskpower.com','www.nspower.ca','nspower.ca','www.princeedwardisland.ca','open.yukon.ca','fisherriver.ca','www.nbpower.com','www.gnb.ca','www.gov.nl.ca','climatechangenunavut.ca','toponymie.gouv.qc.ca','news.hydroquebec.com','www.summerside.ca','www.ntpc.com','yukon.ca','pannes.hydroquebec.com','publications.gc.ca','www.sec.gov']);
  const COUNTRY = {US:'미국',USA:'미국','United States':'미국',CA:'캐나다',CAN:'캐나다',Canada:'캐나다',MX:'멕시코',MEX:'멕시코',Mexico:'멕시코',PR:'푸에르토리코','Puerto Rico':'푸에르토리코',UNK:'소재국 미공표'};
  const CODES = {USA:'US','United States':'US',CAN:'CA',Canada:'CA',MEX:'MX',Mexico:'MX','Puerto Rico':'PR'};
  const STATUS = {operating:'운영',operational:'운영',out_of_service:'운영 중지',out_of_service_short:'운영 중지 · 복귀 예정',out_of_service_long:'운영 중지 · 장기',planned:'계획',planning:'계획',permitting:'인허가 대기',approved:'승인 · 미착공',construction:'건설 중',under_construction:'건설 중',construction_complete:'건설 완료 · 미가동',retired:'퇴역',canceled:'취소',cancelled:'취소',postponed:'연기',canceled_or_postponed:'취소 또는 연기',cancelled_or_postponed:'취소 또는 연기',withdrawn:'철회',active:'유효 / 진행',inactive:'비활성',queued:'접속 대기',queue:'접속 신청',permitted:'허가',contracted:'계약',unknown:'미확인',OP:'운영',OA:'운영 중지 · 내년 복귀 예상',OS:'운영 중지 · 내년 복귀 미예상',U:'건설 중 · 50% 이하',V:'건설 중 · 50% 초과',TS:'건설 완료 · 미가동',P:'계획 · 승인절차 미개시',L:'인허가 대기 · 미착공',T:'승인 · 미착공'};
  const TYPES = {project_phase:'프로젝트 단계',candidate_inventory:'보조 조사 원장',generator:'발전기',eia_generator:'발전기',facility:'시설',project:'프로젝트',queue:'접속 신청',queue_request:'접속 신청',interconnection_request:'접속 신청',interconnection:'접속 신청',permit:'허가',contract:'계약'};
  Object.assign(STATUS,{standby:'대기 설비',queue_active:'접속 신청 · 진행',queue_operational:'접속 신청 기록상 운영',queue_withdrawn:'접속 신청 · 철회',queue_suspended:'접속 신청 · 중단',queue_unknown:'접속 신청 · 상태 미확인',permit_operating:'허가 기록상 운영',permit_operating_partial:'허가 기록상 부분 운영',permit_construction:'허가 기록상 건설',permit_planned:'허가 기록상 계획',permit_terminated:'허가 종료',permit_revoked:'허가 취소',permit_expired:'허가 만료',permit_migrated:'허가 체계 이전'});
  Object.assign(STATUS,{contract_connected:'계약 기록상 계통 연결',project_planned:'사업 계획',permit_review:'환경심사 · 결정 검토 중',permit_determination_issued:'환경심사 · 결정서 발급',permit_additional_work_required:'환경영향평가서 · 추가 작업 요구',contract_operating:'계약 기록상 운영',contract_planned:'계약 기록상 계획',market_listed:'전력시장 목록 수록',queue_cluster:'접속 신청 · 클러스터',queue_assessment_complete:'접속 신청 · 평가 완료',queue_isd_under_review:'접속 신청 · 가동예정일 검토',queue_cancelled:'접속 신청 · 취소',queue_recently_energized:'접속 신청 기록상 최근 통전',candidate_operating:'GEM 기록상 운영',candidate_pre_construction:'GEM 기록상 착공 전',candidate_cancelled:'GEM 기록상 취소',candidate_construction:'GEM 기록상 건설',candidate_announced:'GEM 기록상 발표',candidate_cancelled_inferred_4_y:'GEM 추정 · 4년 미진행 취소',candidate_shelved_inferred_2_y:'GEM 추정 · 2년 미진행 보류',candidate_retired:'GEM 기록상 퇴역',candidate_shelved:'GEM 기록상 보류',candidate_mothballed:'GEM 기록상 가동 중단'});
  const DATE_KIND = {source_reported_actual_year:'원천 보고 실제 가동연도',source_reported_actual_month:'원천 보고 실제 가동월',actual_commissioning_month:'실제 준공·가동월',source_reported_start_year:'원문 시작연도 · 실제/예상 미확정',actual:'실제 가동일',operating:'실제 가동일',actual_operation:'실제 가동일',source_reported_actual:'원천 보고 실제 가동일',source_reported:'가동 관련일 · 실제/예정 미구분',planned:'예정 가동일',proposed:'제안 가동일',expected:'예상 가동일',target:'목표 가동일',contract:'계약상 가동일',unknown:'가동 관련일 · 성격 미확인'};
  const SOURCE_STATUS = {complete_source_extract:'확보한 원천 전체 추출',partial_source_extract:'원천 일부 추출',available:'자료 확보',unavailable:'자료 미확보',blocked:'자료 접근 불가',historical:'과거 관측 자료',corroboration_only:'별도 대조용 원천',rights_held:'재공개 권한 미확인 · 공개 제외','rights-held':'재공개 권한 미확인 · 공개 제외',extracted:'원천 추출 완료',access_blocked:'자료 접근 불가'};
  const text = value => value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  const esc = value => text(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const fmt = value => finite(value) ? value.toLocaleString('ko-KR',{maximumFractionDigits:3}) : 'TBD';
  const countryCode = value => CODES[text(value)] || text(value);
  const countryName = value => COUNTRY[text(value)] || text(value) || '국가 미확인';
  const typeLabel = value => TYPES[text(value)] || text(value) || '단위 미확인';
  const statusLabel = value => STATUS[text(value)] || text(value) || '미확인';
  const recordName = r => text(r.name || r.display_name || r.source_record_id || r.id) || '이름 미공개';
  const partySummary = r => [['운영·보고',r.operator],['개발',r.developer],[r.owner_role==='permit holder'?'허가 보유':'소유·권리',r.owner]].filter(([,v])=>v!=null && v!=='').map(([k,v])=>k+': '+text(v)).join(' · ') || '사업자 TBD';
  function safeURL(value) {
    if (typeof value !== 'string' || !value || /[\u0000-\u0020\u007f]/.test(value)) return null;
    try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password && !u.port && HOSTS.has(u.hostname) ? u.href : null; } catch (_) { return null; }
  }
  function safeAdditionalSources(value) {
    return Array.isArray(value) ? value.filter(v=>v&&typeof v==='object'&&!Array.isArray(v)).map(v=>({id:text(v.id),url:safeURL(v.url)})) : null;
  }
  function sourceDateKindLabel(value) {
    return ({reported_commissioning_month:'원문 준공·가동월',publication_date:'자료 공표일',undated_page:'공표일 미표기 페이지',latest_listed_decision_date:'원문에 열거된 최근 결정일',reported_completion_connection_event:'원문 완료·계통 연결 사건일'})[text(value)]||text(value)||null;
  }
  function historical(record) {
    return record.status === 'permit_migrated' || /(?:^|_)(retired|retirement|cancell?ed|postponed|withdrawn|decommissioned|terminated|revoked|expired|shelved)(?:$|_)/i.test(text(record.status)) || /^(retired|cancell?ed|withdrawn)$/i.test(text(record.record_type));
  }
  function validCoords(record) {
    return finite(record.latitude) && finite(record.longitude) && record.latitude >= -90 && record.latitude <= 90 && record.longitude >= -180 && record.longitude <= 180;
  }
  function project(record) {
    if (!validCoords(record) || record.longitude < -180 || record.longitude > -45 || record.latitude < 5 || record.latitude > 85) return null;
    return {x:45 + (record.longitude + 180) / 135 * 860, y:18 + (85 - record.latitude) / 80 * 352};
  }
  function outlinePaths(world) {
    if (!world || !Array.isArray(world.features)) return '';
    return world.features.filter(f=>f && f.properties && ['US','CA','MX'].includes(f.properties.iso)).map(f=>{
      const g=f.geometry||{}, polygons=g.type==='MultiPolygon'?g.coordinates:g.type==='Polygon'?[g.coordinates]:[];
      if(!Array.isArray(polygons))return '';
      let path='';
      for(const polygon of polygons) {
        if(!Array.isArray(polygon))continue;
        for(const ring of polygon) {
          if(!Array.isArray(ring) || ring.length<3 || ring.length>50000 || ring.some(p=>!Array.isArray(p)||!validCoords({longitude:p[0],latitude:p[1]})))continue;
          path+=ring.map((p,i)=>(i?'L':'M')+(45+(p[0]+180)/135*860).toFixed(2)+' '+(18+(85-p[1])/80*352).toFixed(2)).join(' ')+'Z';
        }
      }
      return path?'<path class="country-outline" d="'+path+'"><title>'+esc(countryName(f.properties.iso))+'</title></path>':'';
    }).join('');
  }
  function sourcesArray(value) {
    return Array.isArray(value) ? value : value && typeof value === 'object' ? Object.entries(value).map(([id,s]) => Object.assign({id},s)) : [];
  }
  function normalize(payload) {
    if (!payload || !Array.isArray(payload.records)) throw new Error('invalid_data');
    const sources = sourcesArray(payload.sources).filter(s => s && typeof s === 'object').map(s => Object.assign({},s,{id:text(s.id),country:countryCode(s.country)}));
    const records = payload.records.map((r,i) => {
      if (!r || typeof r !== 'object' || Array.isArray(r)) throw new Error('invalid_record');
      return Object.assign({},r,{_index:i,country:countryCode(r.country),source_id:text(r.source_id),_search:[r.name,r.display_name,r.owner,r.operator,r.developer,r.region,r.county,r.municipality,r.id,r.facility_id,r.generator_id,r.source_record_id,r.status,r.status_raw,r.technology,r.technology_raw,r.technology_type,r.technology_scope].map(text).join(' ').toLocaleLowerCase()});
    });
    return {sources,records,audience:payload.audience==='internal'?'internal':'public',as_of:payload.as_of,coverage:payload.coverage,summary:Array.isArray(payload.summary)?payload.summary:[],map_asset:payload.map_asset==='world.min.geojson'?payload.map_asset:null};
  }
  async function readPayload(doc, fetcher) {
    const inline=doc.getElementById('solar-inline-data');
    if (inline) {
      if (inline.getAttribute('type')!=='application/json') throw new Error('invalid_inline_type');
      return JSON.parse(inline.textContent);
    }
    const response=await fetcher('data.json',{credentials:'same-origin'});
    if (!response.ok) throw new Error('load_failed');
    return response.json();
  }
  async function loadData(payload, fetcher, cryptoImpl) {
    if (!payload || typeof payload !== 'object') throw new Error('invalid_manifest');
    if (Object.prototype.hasOwnProperty.call(payload,'records')) return normalize(payload);
    const shards=payload.record_shards;
    if (!Array.isArray(shards) || !shards.length || shards.length>128) throw new Error('invalid_shard_list');
    const urls=new Set();
    for (const s of shards) {
      if (!s || typeof s.url!=='string' || !/^records-[0-9]{3}\.json$/.test(s.url) || !Number.isSafeInteger(s.count) || s.count<0 || s.count>100000 || typeof s.sha256!=='string' || !/^[a-f0-9]{64}$/i.test(s.sha256) || urls.has(s.url)) throw new Error('invalid_shard');
      urls.add(s.url);
    }
    const fetchJSON=fetcher || root.fetch.bind(root), crypto=cryptoImpl || root.crypto;
    if (!crypto || !crypto.subtle) throw new Error('verification_unavailable');
    const parts=new Array(shards.length);let next=0,failed=false;
    async function worker() {
      while (!failed && next<shards.length) {
        const i=next++, shard=shards[i];
        try {
          const response=await fetchJSON(shard.url,{credentials:'same-origin'});
          if (!response.ok) throw new Error('shard_unavailable');
          const length=Number(response.headers && response.headers.get('content-length'));
          if (length>MAX_SHARD_BYTES) throw new Error('shard_too_large');
          const bytes=await response.arrayBuffer();
          if (bytes.byteLength>MAX_SHARD_BYTES) throw new Error('shard_too_large');
          const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
          if (digest!==shard.sha256.toLowerCase()) throw new Error('shard_hash_mismatch');
          const rows=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
          if (!Array.isArray(rows) || rows.length!==shard.count) throw new Error('shard_count_mismatch');
          parts[i]=rows;
        } catch (error) {failed=true;throw error;}
      }
    }
    await Promise.all(Array.from({length:Math.min(SHARD_CONCURRENCY,shards.length)},worker));
    return normalize(Object.assign({},payload,{records:parts.flat()}));
  }
  function filterRecords(records, state) {
    const q = text(state.search).trim().toLocaleLowerCase();
    const min = text(state.min).trim() === '' ? null : Number(state.min);
    return records.filter(r => (!state.country || r.country === state.country) && (!state.source || r.source_id === state.source) && (!state.status || text(r.status) === state.status) && (!state.region || text(r.region) === state.region) && (state.scope === 'all' || (state.scope === 'historical' ? historical(r) : !historical(r))) && (!q || (r._search || [r.name,r.owner,r.id,r.facility_id,r.generator_id].map(text).join(' ').toLocaleLowerCase()).includes(q)) && (min === null || (Number.isFinite(min) && min >= 0 && finite(r.capacity_mw) && r.capacity_mw >= min)));
  }
  function sortRecords(records, key) {
    const collator = new Intl.Collator('ko',{numeric:true,sensitivity:'base'});
    return records.slice().sort((a,b) => {
      let cmp = 0;
      if (key === 'capacity_desc' || key === 'capacity_asc') {
        if (finite(a.capacity_mw) !== finite(b.capacity_mw)) return finite(a.capacity_mw) ? -1 : 1;
        if (finite(a.capacity_mw)) cmp = (a.capacity_mw-b.capacity_mw) * (key === 'capacity_desc' ? -1 : 1);
      } else if (key === 'date_asc' || key === 'date_desc') {
        if (Boolean(a.online_date) !== Boolean(b.online_date)) return a.online_date ? -1 : 1;
        cmp = text(a.online_date).localeCompare(text(b.online_date)) * (key === 'date_desc' ? -1 : 1);
      } else if (key === 'source') cmp = collator.compare(text(a.source_id),text(b.source_id));
      return cmp || collator.compare(recordName(a),recordName(b)) || collator.compare(text(a.id),text(b.id)) || (a._index-b._index);
    });
  }
  function csvCell(value) {
    let s = text(value);
    if (typeof value !== 'number' && (/^[\s\uFEFF]*[=+@-]/u.test(s) || /^[\t\r\n]/.test(s))) s = "'" + s;
    return '"' + s.replace(/"/g,'""') + '"';
  }
  function toCSV(records,sources) {
    const map=new Map(sourcesArray(sources).map(s=>[s.id,s]));
    const fields = ['id','country','region','name','display_name','operator','developer','owner','owner_role','record_type','facility_id','generator_id','status','status_raw','capacity_mw','capacity_basis','capacity_dc_mw','storage_mw','battery_energy_mwh','latitude','longitude','online_date','online_date_kind','online_date_precision','queue_date','retired_date','operating_by_date','registration_date','determination_date','technology','technology_type','technology_scope','location_accuracy','rights_flags','public_reusable','source_id','source_record_id','source_sheet','source_row_ids','source_date','source_date_kind','source_url','source_record_url','coordinate_source_url','additional_source_urls','notes','source_name','source_license','source_attribution','source_notes'];
    return '\uFEFF' + fields.map(csvCell).join(',') + '\r\n' + records.map(r => {
      const s=map.get(r.source_id)||{},row=Object.assign({},r,{source_name:s.name,source_license:s.license,source_attribution:s.attribution,source_notes:s.notes,additional_source_urls:safeAdditionalSources(r.additional_source_urls)});
      return fields.map(k => csvCell((k === 'source_url'||k==='source_record_url'||k==='coordinate_source_url') ? safeURL(row[k]) : row[k])).join(',');
    }).join('\r\n');
  }
  function summaryRows(summary,state) {
    return state.country && state.source && Array.isArray(summary) ? summary.filter(r=>r && countryCode(r.country)===state.country && r.source_id===state.source) : [];
  }
  const API = {esc,safeURL,safeAdditionalSources,sourceDateKindLabel,historical,validCoords,project,outlinePaths,normalize,readPayload,loadData,filterRecords,sortRecords,csvCell,toCSV,recordName,partySummary,statusLabel,summaryRows,PAGE_SIZE};
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  if (!root.document) return;
  root.PHXSolar = API;
  const $ = id => document.getElementById(id);
  let data, sourceMap = new Map(), filtered = [], page = 0, mapDirty = true, lastFocus = null, outlines = '', mapPromise = null;
  const state = {country:'',source:'',scope:'current',status:'',region:'',search:'',min:'',sort:'capacity_desc'};
  const fieldIds = {country:'country',source:'source',scope:'scope',status:'status',region:'region',search:'search',min:'min-mw',sort:'sort'};
  const sourceName = id => text((sourceMap.get(id)||{}).name) || id || '원천 미확인';
  const valueHTML = value => value == null || value === '' || (Array.isArray(value) && !value.length) ? '<span class="tbd">TBD</span>' : Array.isArray(value) ? value.map(esc).join('<br>') : esc(value);
  const link = (url,label) => { const safe = safeURL(url); return safe ? '<a href="'+esc(safe)+'" target="_blank" rel="noopener noreferrer">'+esc(label)+' ↗</a>' : '<span class="muted">원문 링크 미제공·연결 미확인</span>'; };
  function options(id, values, placeholder, selected) {
    $(id).innerHTML = '<option value="">'+esc(placeholder)+'</option>' + values.map(([v,l])=>'<option value="'+esc(v)+'">'+esc(l)+'</option>').join('');
    $(id).value = selected;
    return $(id).value;
  }
  function refreshOptions() {
    const countries = [...new Set(data.records.map(r=>r.country).filter(Boolean))].sort();
    state.country = options('country',countries.map(c=>[c,countryName(c)]),'전체 국가',state.country);
    let pool = data.records.filter(r=>!state.country||r.country===state.country);
    const ids = [...new Set(pool.map(r=>r.source_id))].sort();
    state.source = options('source',ids.map(id=>[id,sourceName(id)]),'전체 원천',state.source);
    pool = pool.filter(r=>!state.source||r.source_id===state.source);
    state.status = options('status',[...new Set(pool.map(r=>text(r.status)))].filter(Boolean).sort().map(v=>[v,statusLabel(v)]),'전체 상태',state.status);
    state.region = options('region',[...new Set(pool.map(r=>text(r.region)))].filter(Boolean).sort().map(v=>[v,v]),'전체 지역',state.region);
  }
  function setDefault(all) {
    Object.assign(state,{country:all?'':'US',source:'',scope:all?'all':'current',status:'',region:'',search:'',min:'',sort:'capacity_desc'});
    if (!all) {
      const source = data.sources.find(s=>/eia/i.test(s.id+' '+text(s.name)) && data.records.some(r=>r.source_id===s.id && r.country==='US'));
      if (source) state.source=source.id;
    }
    refreshOptions();
    Object.entries(fieldIds).forEach(([k,id])=>{$(id).value=state[k];});
    page=0; render();
  }
  function coverageText(value) {
    if (value == null) return '';
    if (Array.isArray(value)) return value.map(coverageText).filter(Boolean).join(' · ');
    if (typeof value === 'object') return Object.entries(value).map(([k,v])=>k+': '+coverageText(v)).join(' · ');
    return text(value);
  }
  function renderCoverage() {
    const countries = ['US','CA','MX'];
    const count = new Map(); data.records.forEach(r=>{ const k=r.country+'|'+r.source_id; count.set(k,(count.get(k)||0)+1); });
    $('coverage').innerHTML=countries.map(c=>{
      const sources=data.sources.filter(s=>s.country===c || (Array.isArray(s.countries) && s.countries.map(countryCode).includes(c)) || data.records.some(r=>r.country===c&&r.source_id===s.id));
      const coverage = Array.isArray(data.coverage) ? data.coverage.filter(x=>countryCode(x.country)===c).map(x=>x.note||x.coverage||x.limitations).filter(Boolean) : data.coverage && (data.coverage[c] || data.coverage[Object.keys(CODES).find(k=>CODES[k]===c)]);
      return '<article class="country-card"><div class="country-head"><h3>'+esc(countryName(c))+'</h3><span>'+sources.length+'개 원천</span></div>'+sources.map(s=>'<details class="source-item"><summary><span class="source-name"><span>'+esc(s.name||s.id)+'</span><b>'+fmt(count.get(c+'|'+s.id)||0)+'행</b></span><span class="source-date">기준 '+esc(s.source_date||s.observation_period||'미확인')+'</span><span class="source-state">'+esc(s.status==='complete_source_extract'&&s.rights_withheld_records>0?'원천 전체 확보 · '+(data.audience==='internal'?'내부 연구용 포함':'공개 허용분 수록'):(SOURCE_STATUS[s.status]||s.status||'확보 상태 미공표'))+'</span></summary><p>'+esc(coverageText(s.coverage)||'세부 수록 범위 미공표')+'</p>'+link(s.source_url,'원천 자료')+'<p>이용 조건: '+esc(coverageText(s.license)||'미확인')+'</p><p>출처 표기: '+esc(coverageText(s.attribution||s.publisher||s.name))+'</p>'+(finite(s.rights_withheld_records)&&s.rights_withheld_records>0?'<p>원천 전체 공개 제외 '+fmt(s.rights_withheld_records)+'행</p>':'')+'<details><summary>수록 수 대조</summary><p>'+esc(coverageText(s.counts)||'원천별 집계 미제공')+'</p></details></details>').join('')+(!sources.length?'<p class="coverage-gap">현재 확보된 원천이 없습니다. 전체 커버리지는 미확인입니다.</p>':'')+(coverage?'<p class="coverage-gap">'+esc(coverageText(coverage))+'</p>':'')+'</article>';
    }).join('');
  }
  function dateLabel(r) { return DATE_KIND[text(r.online_date_kind)] || (r.online_date_kind ? '가동 관련일 · '+text(r.online_date_kind) : '가동 관련일 · 성격 미확인'); }
  function renderSummary() {
    const rows=summaryRows(data.summary,state);$('source-summary').hidden=!rows.length;
    if(!rows.length)return;
    $('summary-title').textContent=sourceName(state.source)+' · 원천 전체 상태 소계';
    $('summary-body').innerHTML='<p class="filter-note">선택한 국가·단일 원천의 전체 명부입니다. 과거 기록을 포함하며 상태·지역·검색어·최소 용량·현재/과거 필터는 이 표에 적용되지 않습니다. 각 행의 용량 기준과 기록 단위를 따로 보세요. 아래 행들을 합산하지 않습니다.</p><div class="table-scroll" tabindex="0" role="region" aria-label="원천 상태 소계"><table class="summary-table"><thead><tr><th>상태 · 기록 단위</th><th class="num">행 수 / 시설 수</th><th class="num">용량 공개 / 미공개</th><th class="num">해당 원천 행의 MW 합계</th><th>합계 해석</th></tr></thead><tbody>'+rows.map(r=>'<tr><td>'+esc(statusLabel(r.status))+'<small>'+esc(typeLabel(r.record_type))+'</small></td><td class="num">'+fmt(r.records)+' / '+fmt(r.facilities)+'</td><td class="num">'+fmt(r.capacity_known)+' / '+fmt(r.capacity_unknown)+'</td><td class="num">'+fmt(r.source_record_mw_sum)+'<small>'+esc(r.capacity_basis||'기준 미공표')+'</small></td><td>'+esc(r.sum_note||'합계 기준 미공표')+'</td></tr>').join('')+'</tbody></table></div>';
  }
  function render() {
    filtered=sortRecords(filterRecords(data.records,state),state.sort);
    const pages=Math.max(1,Math.ceil(filtered.length/PAGE_SIZE)); page=Math.max(0,Math.min(page,pages-1));
    const rows=filtered.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE);
    $('result-count').textContent=fmt(filtered.length)+'행 / 전체 '+fmt(data.records.length)+'행';
    const counts={};filtered.forEach(r=>{const k=typeLabel(r.record_type);counts[k]=(counts[k]||0)+1;});
    $('type-summary').textContent=Object.entries(counts).map(([k,n])=>k+' '+fmt(n)).join(' · ')+' · 원천 간 중복 가능';
    $('records').innerHTML=rows.length?rows.map(r=>'<tr><td><button class="record-open" type="button" data-record="'+r._index+'">'+esc(recordName(r))+'</button><small>'+esc(partySummary(r))+'</small><small>'+esc(typeLabel(r.record_type))+' · '+esc(r.source_record_id||r.id||'식별자 TBD')+'</small></td><td>'+esc(countryName(r.country))+'<small>'+esc(r.region||'지역 TBD')+'</small></td><td><span class="pill'+(historical(r)?' hist':'')+'">'+esc(statusLabel(r.status))+'</span></td><td class="num"><strong>'+fmt(r.capacity_mw)+'</strong><small>'+esc(r.capacity_basis||'기준 미공표')+'</small></td><td>'+esc(r.online_date||'TBD')+'<small>'+esc(dateLabel(r))+'</small></td><td>'+esc(sourceName(r.source_id))+'<small>기준 '+esc(r.source_date||(sourceMap.get(r.source_id)||{}).source_date||'미확인')+'</small></td></tr>').join(''):'<tr><td colspan="6" class="empty">조건에 맞는 기록이 없습니다. 원천·명부 범위 또는 검색어를 바꿔 주세요.</td></tr>';
    $('page-label').textContent=(page+1)+' / '+pages+' 페이지 · 100행씩';
    $('prev').disabled=page===0; $('next').disabled=page>=pages-1; $('export-csv').disabled=!filtered.length;
    const visible=filtered.filter(r=>project(r));
    const coordinates=filtered.filter(validCoords).length;
    $('map-count').textContent=fmt(visible.length)+'행 표시 / 좌표 공개 '+fmt(coordinates)+'행';
    renderSummary();
    mapDirty=true;if($('map-panel').open)renderMap();
  }
  function renderMap() {
    if(!mapDirty)return;mapDirty=false;
    let grid='';
    for(let lon=-180;lon<=-45;lon+=15){const x=45+(lon+180)/135*860;grid+='<line class="grid" x1="'+x+'" x2="'+x+'" y1="18" y2="370"/><text x="'+x+'" y="389" text-anchor="middle">'+Math.abs(lon)+'°W</text>';}
    for(let lat=5;lat<=85;lat+=10){const y=18+(85-lat)/80*352;grid+='<line class="grid" x1="45" x2="905" y1="'+y+'" y2="'+y+'"/><text x="37" y="'+(y+4)+'" text-anchor="end">'+lat+'°N</text>';}
    const points=filtered.map(r=>{const p=project(r);return p?'<circle class="map-point" cx="'+p.x.toFixed(2)+'" cy="'+p.y.toFixed(2)+'" r="2.3" data-record="'+r._index+'"><title>'+esc(recordName(r))+' · '+esc(typeLabel(r.record_type))+' · '+esc(r.latitude)+', '+esc(r.longitude)+'</title></circle>':'';}).join('');
    $('map').innerHTML='<svg class="map-svg" viewBox="0 0 930 405" role="img" aria-label="현재 필터의 공개 좌표 경위도 분포도. 같은 기록을 아래 표에서 키보드로 선택할 수 있습니다."><defs><clipPath id="map-bounds"><rect x="45" y="18" width="860" height="352"/></clipPath></defs><g clip-path="url(#map-bounds)">'+outlines+'</g>'+grid+points+'</svg>';
    if(data.map_asset && !mapPromise)mapPromise=fetch(data.map_asset,{credentials:'same-origin'}).then(async response=>{
      if(!response.ok)throw new Error('outline_unavailable');
      const bytes=await response.arrayBuffer();if(bytes.byteLength>512*1024)throw new Error('outline_too_large');
      outlines=outlinePaths(JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes)));mapDirty=true;renderMap();
    }).catch(()=>{ /* A missing outline does not replace or invent project coordinates. */ });
  }
  function detail(r) {
    lastFocus=document.activeElement;
    const s=sourceMap.get(r.source_id)||{};
    $('detail-title').textContent=recordName(r);$('detail-kind').textContent=countryName(r.country)+' · '+typeLabel(r.record_type);
    const raw=r.raw && typeof r.raw==='object'?r.raw:{};
    const fields=[['운영·보고 사업자',r.operator],['개발사',r.developer],['소유·권리 주체 (원문 역할)',r.owner],['소유·권리 주체의 원문 역할',r.owner_role],['국가 · 주·지역',[countryName(r.country),r.region].filter(Boolean).join(' · ')],['군·기초행정구역',r.county||r.municipality],['정규화 상태',statusLabel(r.status)],['원문 상태',r.status_raw],['시설 식별자 (Plant / Facility ID)',r.facility_id],['발전기 식별자 (Generator ID)',r.generator_id],['원천 기록 식별자',r.source_record_id],['기술',r.technology_type||r.technology||r.technology_raw],['원천의 기술 범위',r.technology_scope],['태양광 용량 (MW)',finite(r.capacity_mw)?fmt(r.capacity_mw):null],['용량 기준',r.capacity_basis],['용량 적용 범위',r.capacity_scope],['DC 용량 (MWdc)',finite(r.capacity_dc_mw)?fmt(r.capacity_dc_mw):null],['저장장치 출력 (MW)',finite(r.storage_mw)?fmt(r.storage_mw):null],['배터리 에너지량 (MWh)',finite(r.battery_energy_mwh)?fmt(r.battery_energy_mwh):null],[dateLabel(r),r.online_date],['가동 관련일의 정밀도',({day:'일',month:'월',year:'연도'})[r.online_date_precision]||r.online_date_precision],['해당 일자까지 운영 확인',r.operating_by_date],['등록일',r.registration_date],['심사 결정일',r.determination_date],['접속 신청일',r.queue_date],['접속 신청 철회일',r.withdrawn_date],['접속 계약일',r.interconnection_agreement_date],['퇴역일',r.retired_date],['예정 퇴역일',r.planned_retirement_date],['원문 좌표',validCoords(r)?r.latitude+', '+r.longitude:null],['좌표 근거',r.coordinate_method||r.location_accuracy],['원문 위치 정밀도',r.location_accuracy],['공개 이용 조건 표시',r.rights_flags],['자료 원천',s.name||r.source_id],['원천 기준일',r.source_date||s.source_date||s.observation_period],['원천 기준일의 성격',sourceDateKindLabel(r.source_date_kind||s.source_date_kind)],['원천 공표일',r.published_date||r.release_date||s.published_date||s.release_date||s.official_release_date],['자료 수집일',s.fetched_at||s.retrieved_at],['원천 확인일',s.verified_on||s.verified_at],['원문 시트·표',r.source_sheet||raw.sheet||raw.source_sheet],['원문 행번호',r.source_row_ids ? r.source_row_ids.join(', ') : r.source_row||raw.row||raw.row_number||raw.source_row],['원천 주의 표시',r.quality_flags&&r.quality_flags.length?r.quality_flags:null]];
    $('detail-body').innerHTML='<p class="detail-callout">'+esc(typeLabel(r.record_type))+' 단위 기록입니다. 원문에 없는 사업 관계·공급사를 추정하지 않습니다. 용량과 가동일은 표시된 기준으로만 해석하세요.</p><dl class="detail-grid">'+fields.map(([k,v])=>'<div><dt>'+esc(k)+'</dt><dd>'+valueHTML(v)+'</dd></div>').join('')+
      '<section class="detail-section"><h3>원문 확인·이용 조건</h3><p>'+link(r.source_url||s.source_url,'이 기록의 원천')+'</p>'+(r.source_record_url?'<p>'+link(r.source_record_url,'개별 기록 원문')+'</p>':'')+(r.coordinate_source_url?'<p>'+link(r.coordinate_source_url,'좌표 근거 원문')+'</p>':'')+(safeAdditionalSources(r.additional_source_urls)||[]).map(v=>'<p>'+link(v.url,'보조 근거'+(v.id?' · '+v.id:''))+'</p>').join('')+'<p>'+esc(coverageText(s.coverage))+'</p><p>이용 조건: '+esc(coverageText(s.license)||'미확인')+'</p><p>출처 표기: '+valueHTML(s.attribution||s.publisher||s.name)+'</p></section>'+
      '<section class="detail-section"><h3>원천 공통 주석</h3><p>'+valueHTML(s.notes)+'</p><h3>기록별 주석</h3><p>'+valueHTML(r.notes)+'</p></section>'+
      '<section class="detail-section"><h3>추가 사업 정보</h3><dl class="detail-grid">'+[['EPC',r.epc],['PPA · 구매자',r.ppa],['모듈 공급사',r.module_supplier],['인버터 공급사',r.inverter_supplier],['트래커 공급사',r.tracker_supplier]].map(([k,v])=>'<div><dt>'+k+'</dt><dd>'+valueHTML(v)+'</dd></div>').join('')+'</dl><p>TBD는 미확인 또는 미공개입니다. 해당 정보가 없다는 뜻이 아닙니다.</p></section>';
    $('detail').showModal();
  }
  async function start() {
    try {
      data=await loadData(await readPayload(document,root.fetch.bind(root)));sourceMap=new Map(data.sources.map(s=>[s.id,s]));
      if(data.audience==='internal'){
        $('audience-label').textContent='내부 연구용 · 공개 제외 자료 포함';
        $('audience-note').textContent='원천별 이용 조건에 따라 외부 재공개가 제한된 기록을 포함합니다. 공개용 사이트의 수록 범위와 다릅니다.';
        $('manifest-download').hidden=true;
      } else if($('solar-inline-data')) $('manifest-download').hidden=true;
      $('as-of').textContent=text(data.as_of)||'미공표';renderCoverage();setDefault(false);
      $('filters').addEventListener('submit',e=>e.preventDefault());
      Object.entries(fieldIds).forEach(([key,id])=>{$(id).addEventListener(key==='search'||key==='min'?'input':'change',()=>{state[key]=$(id).value;if(key==='country'){state.source='';state.region='';state.status='';}if(key==='source'){state.region='';state.status='';}if(key==='status'&&historical({status:state.status})){state.scope='all';$('scope').value='all';}if(key==='country'||key==='source')refreshOptions();page=0;render();});});
      $('reset').addEventListener('click',()=>setDefault(false));$('all-sources').addEventListener('click',()=>setDefault(true));
      $('prev').addEventListener('click',()=>{page--;render();});$('next').addEventListener('click',()=>{page++;render();});
      $('map-panel').addEventListener('toggle',()=>{if($('map-panel').open)renderMap();});
      ['records','map'].forEach(id=>{$(id).addEventListener('click',e=>{const el=e.target.closest('[data-record]');if(el){const index=Number(el.dataset.record);if(Number.isInteger(index)&&data.records[index])detail(data.records[index]);}});});
      $('export-csv').addEventListener('click',()=>{const blob=new Blob([toCSV(filtered,data.sources)],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='solar-na-filtered.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
      $('detail-close').addEventListener('click',()=>$('detail').close());
      $('detail').addEventListener('close',()=>{if(lastFocus&&lastFocus.isConnected)lastFocus.focus();});
    } catch (_) {
      $('as-of').textContent='확인 불가';$('coverage').innerHTML='<p class="muted">원천 정보를 불러오지 못했습니다.</p>';
      $('result-count').textContent='자료 로딩 실패';$('records').innerHTML='<tr><td colspan="6" class="empty">자료가 준비되지 않았거나 연결에 실패했습니다. 잠시 후 새로고침해 주세요.</td></tr>';
      $('load-error').hidden=false;$('load-error').textContent='확인된 데이터 파일을 불러오지 못해 명부를 표시할 수 없습니다.';
    }
  }
  start();
})(typeof window === 'undefined' ? globalThis : window);
