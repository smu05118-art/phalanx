/* Shared, read-only consumer view. Only the field-allowlisted public manifest is read. */
(function (root) {
  'use strict';
  const roles = ['series','observations','calendar','availability','freshness'];
  const keys = ['category','metric','source','from','to','status','series'];
  const cache = new Map();
  const labels = {exact:'정확 연결',context:'별도 맥락',excluded:'분모 제외',source_failed:'출처 실패 · 이전 관측',partial:'일부 측정',held:'보류',measured:'공개 관측',bounded:'범위 관측',late:'기대 기간 누락',fresh:'기대 기간 확보',not_due:'예정 전',freshness_unknown:'신선도 미확인'};
  const reasons = {
    publication_revoked:'공개 정책 철회',rights_display_scope_mismatch:'검토된 범주·주기 범위 변경',historical_availability_unverified:'당시 가용성 미확인',event_forecast_status_invalid:'일정의 예측 보류 계약 불일치',future_evidence_timestamp:'미래 시각의 근거 격리',future_evidence_date:'미래 일자의 근거 격리',observation_schema_mismatch:'출처·단위·기간 계약 불일치',
    public_rights_unverified:'시리즈·필드·기간별 공개 권한 근거 필요',event_public_rights_unverified:'일정 제목·기간의 공개 권한 근거 필요',
    admissible_mapping_missing:'정의에 맞는 원자료와 대상 연결 근거 필요',rights_expired:'공개 권한의 유효기간 재확인 필요',
    rights_identity_mismatch:'출처·정의 버전과 권한 범위 재대조 필요',outside_rights_period:'허용 기간 밖의 관측',
    source_failed_current_build:'최근 원자료 읽기 실패 · 이전 내부 이력 보존',public_source_url_unverified:'공개 가능한 원문 주소 확인 필요',
    source_unit_unverified:'원자료 단위 확인 필요',country_unverified:'국가·대상 식별 확인 필요',
    secondary_vendor_fiscal_scope_unverified:'2차 자료의 회계 범위·회계연도 대조 필요',
    source_basis_receipt_unverified:'가격 기준·원단위·관측 영수증 확인 필요',
    unit_source_and_rounding_unverified:'원응답 단위·배율·반올림 규칙 확인 필요',
    unit_scale_unverified:'단위와 배율 확인 필요',quote_currency_or_unit_missing:'통화·표시 단위 확인 필요',
    financial_basis_unverified:'회계 범위·기간 기준 확인 필요',source_definition_unverified:'출처 정의 확인 필요',
    value_missing:'값 미제공',not_provided:'원자료 결측',rounded_display:'반올림 표시 · 구간만 알려짐',censored:'공개 범위 밖 · 점값 미상',
    incomplete_topk_window:'Top K 창의 완전성 확인 필요',future_period_not_observation:'미래 기간은 실측으로 취급하지 않음',
    verified_expected_release_or_collection_plan_missing:'기대 공표·수집 계획이 없어 지연 여부 미확인',
    expected_period_present:'기대 기간이 원장에 존재',expected_release_not_due:'확인된 공표 예정일 전',expected_period_missing:'기대 기간 미확보'
  };
  function esc(v) { return String(v == null ? '' : v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function reason(v) { return reasons[v] || ('추가 근거 확인 필요 ('+String(v||'미상')+')'); }
  function count(v) { return Number.isSafeInteger(v) && v >= 0 ? v.toLocaleString('ko-KR') : '미상'; }
  function number(v) { return typeof v === 'number' && Number.isFinite(v); }
  function date(v) { return typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v) && Number.isFinite(Date.parse(v)) && new Date(v).toISOString().slice(0,10) === v; }
  function href(v) { try { const u = new URL(v); return u.protocol === 'https:' && !u.username && !u.password ? u.href : null; } catch (_) { return null; } }
  function cleanFilters(v) {
    const out = {};
    keys.forEach(k => { const x = v && v[k]; out[k] = typeof x === 'string' && x.length <= 100 && !/[\x00-\x1f]/.test(x) ? x : ''; });
    ['from','to'].forEach(k => { if (!date(out[k])) out[k]=''; });
    if (!['','measured','bounded','held','late','freshness_unknown'].includes(out.status)) out.status='';
    return out;
  }
  function readFilters(params) { const v={};keys.forEach(k=>{v[k]=params.get('ct_'+k);});return cleanFilters(v); }
  function writeFilters(params, v) { const f=cleanFilters(v);keys.forEach(k=>{params.delete('ct_'+k);if(f[k])params.set('ct_'+k,f[k]);});return params; }
  function validateManifest(m) {
    if (!m || m.schema_version!==1 || m.schema!=='consumer_tracking.v1' || m.forecast_status!=='forecast_held' || !/^[a-f0-9]{64}$/.test(m.revision) || !Array.isArray(m.files) || m.files.length>2500) throw Error('공개 계약 형식 오류');
    let total=0;const seen=new Set(), found=new Set();
    m.files.forEach(f=>{
      if (!roles.includes(f.role) || !/^[a-f0-9]{64}$/.test(f.sha256) || f.path!=='objects/'+f.sha256+'.json' || !Number.isInteger(f.bytes) || f.bytes<1 || f.bytes>4000000 || !Number.isInteger(f.count) || f.count<0 || seen.has(f.path)) throw Error('공개 객체 계약 오류');
      total+=f.bytes;seen.add(f.path);found.add(f.role);
    });
    if (total>64000000 || roles.some(r=>!found.has(r))) throw Error('공개 계약 크기 또는 역할 오류');
    return m;
  }
  async function boundedJSON(url, expected, signal) {
    const response=await root.fetch(url,{signal,redirect:'error',credentials:'omit',cache:'no-cache'});
    if (!response.ok || !response.body || !/application\/json/i.test(response.headers.get('content-type')||'')) throw Error('공개 자료 응답 오류');
    const reader=response.body.getReader(),chunks=[];let size=0;
    const cap=expected?expected.bytes:1000000;
    while(true) {const r=await reader.read();if(r.done)break;size+=r.value.byteLength;if(size>cap){await reader.cancel();throw Error('공개 자료 크기 오류');}chunks.push(r.value);}
    const bytes=new Uint8Array(size);let offset=0;chunks.forEach(b=>{bytes.set(b,offset);offset+=b.length;});
    if(expected){
      const hash=Array.from(new Uint8Array(await root.crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
      if(size!==expected.bytes||hash!==expected.sha256)throw Error('공개 자료 무결성 오류');
    }
    return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
  }
  async function load(base) {
    const u=new URL('consumer-tracking/',base);
    if (root.location && u.origin!==root.location.origin) throw Error('같은 사이트의 공개 자료만 지원합니다');
    if(cache.has(u.href))return cache.get(u.href);
    const pending=(async()=>{
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
      try{
        const m=validateManifest(await boundedJSON(new URL('manifest.json',u),null,controller.signal));
        const data={};roles.forEach(r=>{data[r]=[];});let next=0;
        // Four bounded workers. A failed shard fails the whole view, never partial success.
        await Promise.all(Array.from({length:Math.min(4,m.files.length)},async()=>{
          while(next<m.files.length){const f=m.files[next++],d=await boundedJSON(new URL(f.path,u),f,controller.signal);
            if(d.schema_version!==1||d.role!==f.role||!Array.isArray(d.items)||d.items.length!==f.count)throw Error('공개 객체 스키마 오류');
            data[f.role].push(...d.items);
          }
        }));
        data.revision=m.revision;validateData(data);return data;
      }finally{controller.abort();clearTimeout(timer);}
    })();
    cache.set(u.href,pending);try{return await pending;}catch(e){cache.delete(u.href);throw e;}
  }
  function validateData(d) {
    const a=d.availability[0];
    if(d.availability.length!==1 || !a || a.forecast_status!=='forecast_held' || !Array.isArray(a.categories) || a.categories.length!==35 || !Array.isArray(a.metrics)||a.metrics.length!==50||!Array.isArray(a.sources))throw Error('범위 계약 오류');
    const ids=new Set();d.series.forEach(s=>{if(!/^ct_[a-f0-9]{64}$/.test(s.series_id)||ids.has(s.series_id)||!Array.isArray(s.category_ids))throw Error('시리즈 식별 오류');ids.add(s.series_id);});
    const seen=new Set();d.observations.forEach(o=>{
      const k=[o.series_id,o.period_key,o.observation_slot_id||''].join('|');
      if(!ids.has(o.series_id)||!date(o.period_start)||!date(o.period_end)||o.period_start>o.period_end||seen.has(k)||(!number(o.value)&&o.value!==null)||o.forecast_status!=='forecast_held')throw Error('관측 계약 오류');
      if(o.bounds && (o.value!==null||!number(o.bounds.lower)||(o.bounds.upper!==null&&(!number(o.bounds.upper)||o.bounds.upper<o.bounds.lower))))throw Error('구간 계약 오류');
      seen.add(k);
    });
    const events=new Set();d.calendar.forEach(e=>{if(!/^ce_[a-f0-9]{64}$/.test(e.event_id)||events.has(e.event_id)||!date(e.date_start)||!date(e.date_end)||e.date_start>e.date_end||!['date','month'].includes(e.date_precision)||e.date_precision==='date'&&e.date_start!==e.date_end||typeof e.title!=='string'||!href(e.source_url)||!Array.isArray(e.category_ids)||e.status!=='scheduled_execution_unverified'||e.forecast_status!=='forecast_held')throw Error('일정 계약 오류');events.add(e.event_id);});
    const c=a.row_binding_counts;if(c && (c.total_rows!==84||c.eligible_rows!==84-c.excluded||['exact','partial','context','excluded','held'].reduce((n,k)=>n+c[k],0)!==84))throw Error('원문 분모 계약 오류');
    const sm=new Map(d.series.map(s=>[s.series_id,s]));d.observations.forEach(o=>{const x=sm.get(o.series_id);if(o.unit!==x.unit||o.source_id!==x.source_id||o.metric_id!==x.metric_id||!href(o.source_url))throw Error('출처·단위 계약 오류');});
    if(a.observed_scope){
      const numeric=d.series.filter(s=>s.metric_id!=='CM_MACRO'),expected={
        numeric_consumer_categories:new Set(numeric.flatMap(s=>s.category_ids)).size,
        numeric_consumer_contracts:new Set(numeric.map(s=>s.metric_id)).size,
        methodology_categories:35,methodology_contracts:50,schedule_categories:new Set(d.calendar.flatMap(e=>e.category_ids)).size,
        numeric_consumer_observations:d.observations.filter(o=>o.metric_id!=='CM_MACRO').length,
        macro_context_observations:d.observations.filter(o=>o.metric_id==='CM_MACRO').length,
        new_live_acquisitions:0,market_coverage_ratio:null};
      if(Object.keys(a.observed_scope).length!==Object.keys(expected).length||Object.keys(expected).some(k=>a.observed_scope[k]!==expected[k]))throw Error('소비 수치·방법론 분모 계약 오류');
    }
    return d;
  }
  function values(d, f, sid) { return d.observations.filter(o=>(!sid||o.series_id===sid)&&(!f.from||o.period_end>=f.from)&&(!f.to||o.period_start<=f.to)).sort((a,b)=>a.period_end.localeCompare(b.period_end)||a.period_start.localeCompare(b.period_start)||String(a.observation_slot_id).localeCompare(String(b.observation_slot_id))); }
  function series(d, f) {
    const fresh=new Map(d.freshness.map(x=>[x.series_id,x]));
    return d.series.filter(s=>{
      if((f.category&&!s.category_ids.includes(f.category))||(f.metric&&s.metric_id!==f.metric)||(f.source&&s.source_id!==f.source)||f.status==='held')return false;
      const rows=values(d,f,s.series_id);if(!rows.length)return false;
      if(f.status==='bounded'&&!rows.some(o=>o.bounds))return false;
      if(['late','freshness_unknown'].includes(f.status)&&(fresh.get(s.series_id)||{}).status!==f.status)return false;
      return true;
    }).sort((a,b)=>String(a.label).localeCompare(String(b.label),'ko'));
  }
  function displayValue(o) {
    if(number(o.value))return o.value.toLocaleString('ko-KR',{maximumSignificantDigits:14});
    if(o.bounds)return String(o.bounds.lower)+' ≤ 값'+(o.bounds.upper===null?'':(o.bounds.upper_inclusive?' ≤ ':' < ')+o.bounds.upper);
    return '결측 · '+reason(o.missing_reason);
  }
  function chart(rows,s) {
    const pts=rows.filter(o=>number(o.value));
    if(!pts.length)return '<p class="ct-warning">차트에 표시할 점값이 없습니다. 범위·결측은 아래 표에서 확인하세요.</p>';
    const xs=rows.map(o=>Date.parse(o.period_end)),xmin=Math.min(...xs),xmax=Math.max(...xs);
    const ys=pts.map(o=>o.value),min=Math.min(...ys),max=Math.max(...ys),rank=s.unit==='rank'||s.metric_id==='CM_RANK';
    const points=pts.map(o=>{const x=60+(Date.parse(o.period_end)-xmin)/(xmax-xmin||1)*590;const y=30+(rank?(o.value-min):(max-o.value))/(max-min||1)*150;
      return '<circle cx="'+x.toFixed(2)+'" cy="'+y.toFixed(2)+'" r="3"><title>'+esc(o.period_key+' · '+displayValue(o)+' '+s.unit)+'</title></circle>';}).join('');
    return '<svg class="ct-chart" viewBox="0 0 710 240" role="img" aria-label="'+esc(s.label+' 기간별 관측 · 표에 동일 값 제공')+'"><line x1="60" y1="190" x2="660" y2="190"/><text x="4" y="32">'+esc(rank?min:max)+'</text><text x="4" y="180">'+esc(rank?max:min)+'</text>'+points+'<text x="60" y="215">'+esc(rows[0].period_end)+'</text><text x="650" y="235" text-anchor="end">'+esc(rows[rows.length-1].period_end)+'</text></svg><p class="ct-note">기간 종료일 위치의 원값 · '+esc(s.unit)+' · 배율 '+esc(s.scale==null?'미상':s.scale)+' · 결측 사이 보간 없음'+(rank?' · 순위는 낮을수록 상위':'')+'</p>';
  }
  function options(items,key,name,selected) {return '<option value="">전체</option>'+items.map(x=>'<option value="'+esc(x[key])+'"'+(x[key]===selected?' selected':'')+'>'+esc(x[name])+'</option>').join('');}
  function catalog(d,f){
    const a=d.availability[0],source=a.sources.find(s=>s.source_id===f.source);
    const metrics=a.metrics.filter(m=>(!f.category||m.category_ids.includes(f.category))&&(!f.metric||m.metric_id===f.metric)&&(!source||source.metric_ids.includes(m.metric_id)));
    const cats=a.categories.filter(c=>!f.category||c.category_id===f.category);
    return '<details><summary>범주별 방법론 ('+cats.length+'범주)</summary>'+cats.map(c=>'<p><strong>'+esc(c.name)+'</strong> · '+count(c.public_observation_count)+'관측 / '+count(c.public_event_count)+'일정<br>'+esc(c.sector_specific_gap||'범주별 측정 조건은 지표 정의 참조')+'</p>').join('')+'</details><details><summary>정의·범위·보류 사유 ('+metrics.length+'개 계약)</summary><p>범주의 일부 관측은 범주 전체나 원문 대상의 운영 완료를 뜻하지 않습니다. 날짜 필터는 공개 관측에 적용됩니다.</p>'+metrics.map(m=>'<details><summary>'+esc(m.name)+' · '+esc(labels[m.status]||m.status)+' · 공개 '+count(m.public_observation_count)+'건</summary><p>'+esc(m.definition)+'</p><p>단위 '+esc(m.unit)+' · 측정 단위 '+esc(m.measurement_grain)+' · 주기 '+esc(m.cadence)+'</p><p class="ct-warning">'+esc((m.availability_reasons||[]).map(reason).join(' · ')||'공개 가능한 관측이 있습니다. 전체 시장·대상 범위는 확인되지 않았습니다.')+'</p></details>').join('')+'</details>';
  }
  function detail(d,s,rows,page){
    if(!s)return '<p class="ct-warning">조건에 맞는 공개 이력이 없습니다. 정의와 보류 사유에서 필요한 근거를 확인하세요.</p>';
    const a=d.availability[0],m=a.metrics.find(x=>x.metric_id===s.metric_id),fr=d.freshness.find(x=>x.series_id===s.series_id)||{},last=rows[rows.length-1];
    const shown=rows.slice().reverse().slice(page*50,page*50+50);
    return '<h3>'+esc(s.label)+'</h3><p>'+esc(m?m.definition:s.measure)+'</p><p>최근 기간 '+esc(last.period_key)+' · <strong>'+esc(displayValue(last))+'</strong> '+esc(s.unit)+' '+esc(s.currency||'')+'</p>'+chart(rows,s)+
      '<p>'+esc(labels[fr.status]||'신선도 미확인')+' · '+esc(reason(fr.reason))+' · 관측 경과 '+esc(fr.observation_age_days==null?'미상':fr.observation_age_days+'일')+' · 주기 점검 '+esc(fr.cadence_quality==='stale'?'오래된 관측':fr.cadence_quality==='within_cadence'?'주기 범위 내':'미상')+' (공식 발표 지연 판정과 별도)</p><p>정의 '+esc(s.definition_version)+' · 측정 '+esc(s.measure)+' · 국가 '+esc(s.country||'미상')+' · '+esc(s.accounting_basis||'회계범위 미제공')+' · '+esc(s.period_basis||'기간기준 미제공')+'</p>'+
      '<div class="ct-scroll"><table><thead><tr><th>원기간 / 값</th><th>공표·관측·취득 / 상태</th></tr></thead><tbody>'+shown.map(o=>'<tr><td>'+esc(o.period_key)+'<br><strong>'+esc(displayValue(o))+'</strong> '+esc(o.unit)+'<br>'+esc(o.period_start)+' ~ '+esc(o.period_end)+'</td><td>공표 '+esc(o.published_at||o.published_date||'미상')+(o.published_at_estimated?' (추정)':'')+'<br>관측 '+esc(o.observed_at||o.observed_date||'미상')+'<br>취득 '+esc(o.fetched_at||'미상')+(o.fetched_at_estimated?' (추정)':'')+'<br>당시 가용 '+esc(o.available_at||'미확인')+' · '+esc(o.release_status||'미상')+(o.supersedes?' · 정정판':'')+'<br>'+ (href(o.source_url)?'<a target="_blank" rel="noopener noreferrer" href="'+esc(href(o.source_url))+'">원문 확인</a>':'원문 주소 미제공')+'</td></tr>').join('')+'</tbody></table></div><p>'+count(rows.length)+'건 · '+(page+1)+'/'+Math.max(1,Math.ceil(rows.length/50))+'쪽 <button data-ct-page="-1"'+(page===0?' disabled':'')+'>이전</button> <button data-ct-page="1"'+((page+1)*50>=rows.length?' disabled':'')+'>다음</button></p>';
  }
  function view(d,f,base,page){
    const a=d.availability[0],list=series(d,f),s=list.find(x=>x.series_id===f.series)||list[0],rows=s?values(d,f,s.series_id):[];
    const contextCount=d.observations.filter(o=>o.metric_id==='CM_MACRO').length;
    const measuredCats=new Set(),measuredMetrics=new Set();d.series.filter(x=>x.metric_id!=='CM_MACRO').forEach(x=>{x.category_ids.forEach(c=>measuredCats.add(c));measuredMetrics.add(x.metric_id);});
    const rc=a.row_binding_counts||{exact:0,partial:0,context:0,excluded:0,held:84,eligible_rows:84};
    const audit=a.source_audit_scope;
    const auditNote=audit?'<p>원본 취득 '+count(audit.acquired_unique_types)+'/'+count(audit.requested_unique_types)+'종 · '+count(audit.worksheets)+'시트 · 역사 자료 감사 '+esc(audit.audit_date)+' · 운영 연결 추가 '+count(audit.live_bindings_added)+'건'+(audit.acquisition_known_by_evaluation?'':' · 평가일 이후 취득 자료')+'</p>':'';
    const schedules=d.calendar.filter(e=>(!f.category||e.category_ids.includes(f.category))&&(!f.metric||e.metric_id===f.metric)&&(!f.source||e.source_id===f.source)&&(!f.from||e.date_end>=f.from)&&(!f.to||e.date_start<=f.to));
    const link=(path,title)=>'<a href="'+esc(new URL(path,base).href)+'">'+title+'</a>';
    return '<div class="ct-view"><h2>소비 관측 · 근거와 이력</h2><p>예측 반영 보류 · 검색·순위·평점·표시 수량은 매출이나 설치 수가 아닙니다.</p><div class="ct-summary"><div>방법론 범위<strong>35범주 · 50계약</strong>원문 대응 84행</div><div>공개 소비 수치 범위<strong>'+measuredCats.size+'/35범주 · '+measuredMetrics.size+'/50계약</strong>시장 점유·지출 포괄률 미확인</div><div>허용된 공개 기록<strong>'+count(a.public_observations)+'건</strong>'+count(a.public_series)+'시리즈 · '+count(a.public_events)+'일정<br>소비 수치 '+count(a.public_observations-contextCount)+' · 거시 맥락 '+count(contextCount)+'</div><div>원문 대상 직접 연결<strong>'+count(rc.exact)+'/'+count(rc.eligible_rows)+'대상행</strong>부분 '+count(rc.partial)+' · 맥락 '+count(rc.context)+' · 보류 '+count(rc.held)+' · 제외 '+count(rc.excluded)+'행</div></div>'+
      auditNote+'<nav class="ct-links" aria-label="관련 연구 화면">'+link('index.html#tab=app','기업 공시')+link('index.html#tab=game','게임')+link('index.html#tab=plat','플랫폼')+link('argus/','가격·원가')+link('panoptes/#liq','거시')+link('panoptes/#fed','연준')+link('panoptes/?desk=calendar#fed','공유 연구달력')+'</nav>'+
      '<div class="ct-filters"><label>범주<select data-ct="category">'+options(a.categories,'category_id','name',f.category)+'</select></label><label>지표<select data-ct="metric">'+options(a.metrics,'metric_id','name',f.metric)+'</select></label><label>출처<select data-ct="source">'+options(a.sources,'source_id','name',f.source)+'</select></label><label>상태<select data-ct="status">'+options(['measured','bounded','held','late','freshness_unknown'].map(x=>({id:x,name:labels[x]})),'id','name',f.status)+'</select></label><label>시작일<input type="date" data-ct="from" value="'+esc(f.from)+'"></label><label>종료일<input type="date" data-ct="to" value="'+esc(f.to)+'"></label></div>'+
      (f.from&&f.to&&f.from>f.to?'<p role="alert">시작일이 종료일보다 늦습니다.</p>':'')+
      '<p role="status">현재 조건 '+list.length+'개 시리즈 · 위 범위 수치는 전체 공개 자료 기준입니다.</p><div class="ct-grid"><div><label>시리즈 선택<select data-ct="series" style="width:100%">'+list.map(x=>'<option value="'+esc(x.series_id)+'"'+(s&&s.series_id===x.series_id?' selected':'')+'>'+esc(x.label+' · '+x.unit)+'</option>').join('')+'</select></label><details open><summary>출처별 공개 상태</summary>'+a.sources.filter(x=>!f.source||f.source===x.source_id).map(x=>'<p><strong>'+esc(x.name)+'</strong> · '+count(x.public_observation_count)+'관측 / '+count(x.public_event_count)+'일정<br>'+esc(x.availability_reasons.map(reason).join(' · ')||'허용된 자료 표시 중')+'</p>').join('')+'</details></div><section>'+detail(d,s,rows,page)+'</section></div><details open><summary>공개 출시 예정 일정 ('+schedules.length+')</summary><p>Steam 플랫폼 일부 · 원자료 기재 예정일이며 실제 출시 확인과 별도입니다. 지나간 예정일도 실적으로 전환하지 않습니다.</p>'+schedules.map(e=>'<p>'+esc(e.date_precision==='date'?e.date_start:e.date_start+' ~ '+e.date_end)+' · <a target="_blank" rel="noopener noreferrer" href="'+esc(href(e.source_url))+'">'+esc(e.title)+'</a> · 예정 / 실행 미확인</p>').join('')+'</details>'+catalog(d,f)+'</div>';
  }
  async function mount(element,options){
    const opts=options||{},token={};element.__ctToken=token;
    element.innerHTML='<div class="ct-view" role="status">허용된 관측 이력을 읽고 있습니다…</div>';
    try{const data=opts.data||await load(opts.base);if(element.__ctToken!==token)return;
      let filters=cleanFilters(opts.filters),page=0;
      function paint(){if(element.__ctToken!==token)return;element.innerHTML=view(data,filters,opts.base,page);
        element.querySelectorAll('[data-ct]').forEach(control=>control.addEventListener('change',()=>{filters[control.dataset.ct]=control.value;if(control.dataset.ct!=='series')filters.series='';filters=cleanFilters(filters);page=0;if(opts.onChange)opts.onChange(filters);paint();}));
        element.querySelectorAll('[data-ct-page]').forEach(button=>button.addEventListener('click',()=>{page=Math.max(0,page+Number(button.dataset.ctPage));paint();}));
      }paint();
    }catch(_){if(element.__ctToken===token)element.innerHTML='<div class="ct-view"><p role="alert">공개 관측 자료를 확인하지 못했습니다. 잠시 후 다시 시도하세요. 비공개 자료로 대체하지 않습니다.</p><button type="button" data-ct-retry>다시 읽기</button></div>';const b=element.querySelector('[data-ct-retry]');if(b)b.onclick=()=>mount(element,opts);}
  }
  function calendarEvents(data){return data.calendar.filter(e=>e.source_id!=='fed_calendar'&&e.destination==='shared_research_desk').map(e=>({id:e.event_id,kind:'consumer',title:e.title,ticker:null,market:null,date:e.date_precision==='date'?e.date_start:null,timeLabel:'시각 미상',timezoneLabel:'원자료 날짜 · 시간대 미확인',statusLabel:(e.date_precision==='date'?'':'기간 '+e.date_start+' ~ '+e.date_end+' · ')+(e.status||'상태 미상')+' · 실제 출시·공연 확인과 별도',sourceUrl:href(e.source_url),sourceLabel:'소비 일정 원문',detailUrl:'index.html#tab=ct',searchText:[e.title,e.date_start,e.date_end].join(' ')}));}
  const api={cancel:el=>{if(el)el.__ctToken=null;},load,mount,cleanFilters,readFilters,writeFilters,validateManifest,validateData,series,values,displayValue,chart,view,calendarEvents};
  root.PHXConsumer=api;if(typeof module==='object'&&module.exports)module.exports=api;
})(typeof window==='object'?window:globalThis);
