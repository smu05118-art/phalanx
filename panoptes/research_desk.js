/* Shared research navigation, calendar and browser-local saved views. */
(function (root) {
  'use strict';
  var VIEW_KEY = 'phx:research-desk:views:v1', PENDING_KEY = 'phx:research-desk:restore:v1';
  var MAIN_KEYS = ['r','tab','v','cat','co','port','cur','g','luxview','luxbrand','luxticker','luxcompany','dcv','dcco','dcp','dcq','dcst','dcs','dcn','dcgr','dcgb','dcgm','ct_category','ct_metric','ct_source','ct_from','ct_to','ct_status','ct_series'];
  var PAN_TABS = ['map','sig','liq','human','tech','ship','fed','llm'];
  function esc(v) { return String(v == null ? '' : v).replace(/[&<>"']/g, function(c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function norm(v) { return String(v || '').toLocaleLowerCase('ko').replace(/\s+/g,' ').trim(); }
  function safeLocation(raw, base) {
    if (typeof raw !== 'string' || /[\x00-\x20\\]/.test(raw) || raw.length > 2400) return null;
    try {
      var b = new URL(base), u = new URL(raw, b);
      if (u.origin !== b.origin || u.username || u.password || !u.pathname.startsWith(b.pathname)) return null;
      var path = u.pathname.slice(b.pathname.length);
      if (!['','index.html','panoptes/','panoptes/index.html','argus/','argus/index.html','argus/map.html','argus/connections.html'].includes(path)) return null;
      var p = new URLSearchParams(), hash = u.hash.slice(1);
      if (path === '' || path === 'index.html') {
        new URLSearchParams(hash).forEach(function(v,k) { if (MAIN_KEYS.includes(k) && v.length <= 180 && !/[\x00-\x1f]/.test(v)) p.set(k,v); });
        hash = p.toString();
      } else if (path.startsWith('panoptes/')) {
        if (hash && !PAN_TABS.includes(hash)) return null;
      } else if (path === 'argus/map.html') {
        var sid = new URLSearchParams(hash).get('series');
        if (hash && (!sid || sid.length > 180 || /[\x00-\x1f]/.test(sid))) return null;
        hash = sid ? 'series=' + encodeURIComponent(sid) : '';
      } else { hash = ''; }
      var desk = u.searchParams.get('desk');
      return path + (RD_TABS.includes(desk) ? '?desk='+desk : '') + (hash ? '#'+hash : '');
    } catch (_) { return null; }
  }
  function calendarState(v) {
    v = v && typeof v === 'object' ? v : {};
    return {q: typeof v.q === 'string' ? v.q.slice(0,120) : '', kind:['all','earnings','macro','consumer'].includes(v.kind)?v.kind:'all',
      range:['7','30','all','tbd'].includes(v.range)?v.range:'7', phx:v.phx === true,
      date:/^\d{4}-\d{2}-\d{2}$/.test(v.date || '') && !isNaN(Date.parse(v.date)) && new Date(v.date).toISOString().slice(0,10)===v.date ? v.date : ''};
  }
  function cleanViews(raw, base) {
    if (!Array.isArray(raw)) return [];
    return raw.slice(0,20).flatMap(function(v) {
      if (!v || typeof v.id !== 'string' || !/^[a-z0-9-]{1,60}$/.test(v.id) || typeof v.name !== 'string' || !v.name.trim()) return [];
      var url = safeLocation(v.url,base); if (url == null) return [];
      return [{id:v.id,name:v.name.trim().slice(0,60),url:url,saved:typeof v.saved==='string'?v.saved.slice(0,30):'',
        calendar:calendarState(v.calendar), panel:RD_TABS.includes(v.panel)?v.panel:'search',
        evidence:cleanEvidence(v.evidence)}];
    });
  }
  function cleanEvidence(v) {
    var out = {}, rules = {flow:{ticker:['005930','000660'],investor:['foreign_net_shares','institution_net_shares','individual_net_shares'],mode:['daily','cumulative']},episodes:{index:['kospi','kosdaq','sp500','nasdaq'],horizon:['5','20','60']}};
    // The evidence module remains the final authority on accepted selections.
    Object.keys(rules).forEach(function(group) { if (!v || !v[group] || typeof v[group] !== 'object') return; var item={};
      Object.keys(rules[group]).forEach(function(k) { if (rules[group][k].includes(String(v[group][k]))) item[k]=String(v[group][k]); });
      if(Object.keys(item).length)out[group]=item;
    }); return out;
  }
  function filterEvents(events, s, today) {
    s=calendarState(s); var anchor=s.date||today, end=anchor;
    if (s.range==='7'||s.range==='30') { var d=new Date(anchor+'T00:00:00Z'); d.setUTCDate(d.getUTCDate()+Number(s.range)-1);end=d.toISOString().slice(0,10); }
    var q=norm(s.q);
    return events.filter(function(e) { return (s.kind==='all'||e.kind===s.kind) && (!s.phx || (e.kind==='earnings' && e.phx)) && (!q || norm(e.searchText||[e.title,e.ticker,e.sourceLabel].join(' ')).includes(q)) &&
      (s.range==='tbd' ? !e.date : s.range==='all' ? true : !!e.date && e.date>=anchor && e.date<=end); });
  }
  function rankMatches(items, q) {
    q=norm(q); if(!q)return items.filter(function(i){return i.type==='바로가기';});
    return items.map(function(i) {var n=norm(i.name),t=norm(i.ticker),hay=norm(i.search||i.name),c=norm(i.command);
      return {i:i,s:(q===t||q===n||q===c)?0:(n.startsWith(q)||t.startsWith(q)||c.startsWith(q))?1:hay.includes(q)?2:9};
    }).filter(function(x){return x.s<9;}).sort(function(a,b){return a.s-b.s||a.i.name.localeCompare(b.i.name,'ko');}).map(function(x){return x.i;});
  }
  // catalyst-ops-ui/1.0: labels are local; publisher data only reaches text nodes.
  var RD_TABS = ['search','calendar','research','views'];
  function tabIndex(key, index, length) {
    return key==='Home'?0:key==='End'?length-1:(index+(key==='ArrowRight'?1:length-1))%length;
  }
  function catalystClock(){return {basis:'actual_utc',now:Date.now()};}
  function object(v){return v!==null && typeof v==='object' && !Array.isArray(v);}
  function textValue(v){return typeof v==='string' && v.length<=40000;}
  function nonempty(v){return textValue(v) && v.trim().length>0;}
  function list(v,check){return Array.isArray(v) && v.length<=10000 && v.every(check);}
  function texts(v){return list(v,textValue);}
  function hash(v){return typeof v==='string' && /^[a-f0-9]{64}$/.test(v);}
  function ref(v,kind){return typeof v==='string' && new RegExp('^'+(kind||'[a-z_]+')+':[a-f0-9]{64}@[1-9][0-9]*$').test(v);}
  function utc(v){return typeof v==='string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$/.test(v) && dateOnly(v.slice(0,10)) && Number(v.slice(11,13))<24 && Number(v.slice(14,16))<60 && Number(v.slice(17,19))<60 && Number.isFinite(Date.parse(v));}
  function dateOnly(v){return typeof v==='string' && /^\d{4}-\d\d-\d\d$/.test(v) && !isNaN(Date.parse(v)) && new Date(v).toISOString().slice(0,10)===v;}
  function nullable(v,check){return v===null||check(v);}
  function count(v){return Number.isSafeInteger(v)&&v>=0;}
  function httpsURL(v){try{if(!nonempty(v)||/[\x00-\x20\x7f\\]/.test(v))return null;var u=new URL(v);return u.protocol==='https:'&&!u.username&&!u.password?u.href:null;}catch(_){return null;}}
  function jsonValue(v,depth){depth=depth||0;return depth<12&&(v===null||typeof v==='boolean'||textValue(v)||(typeof v==='number'&&Number.isFinite(v))||(Array.isArray(v)&&v.length<=1000&&v.every(function(x){return jsonValue(x,depth+1);}))||(object(v)&&Object.keys(v).length<=1000&&Object.values(v).every(function(x){return jsonValue(x,depth+1);})) );}
  function gate(v){return object(v)&&['pass','held','fail','not_evaluated'].includes(v.status)&&texts(v.reasons)&&list(v.evidence_refs,function(r){return ref(r);});}
  function history(v){return object(v)&&count(v.sequence)&&hash(v.sha256);}
  function bindings(v){return object(v)&&history(v.core_history)&&history(v.discovery_history)&&hash(v.config_sha256)&&hash(v.company_review_sha256)&&v.integration_version==='catalyst-ops/1.0'&&v.company_adapter_version==='company-adapter/1.0'&&nullable(v.latest_core_run_ref,function(r){return ref(r,'run');})&&nullable(v.latest_discovery_run_ref,function(r){return ref(r,'discovery_run');});}
  function sourceClock(v){return object(v)&&ref(v.source_ref,'source')&&['capture_at','first_seen_at','ingested_at','validated_at'].every(function(k){return utc(v[k]);})&&['recheck_due_at','publisher_declared_published_at','publisher_declared_modified_at','historical_public_available_at','effective_at'].every(function(k){return nullable(v[k],utc);})&&['published_on','observed_on'].every(function(k){return nullable(v[k],dateOnly);})&&nullable(v.effective_timezone,textValue)&&object(v.metric_observation_dates)&&Object.values(v.metric_observation_dates).every(function(x){return nullable(x,dateOnly);});}
  function currentCard(v){
    if(!object(v)||v.actionable!==false||!gate(v.watch_gate)||v.watch_gate.status!=='pass'||!gate(v.research_gate)||!object(v.core))return false;
    var c=v.core,d=c.card;
    return ref(c.decision_ref,'decision')&&hash(c.decision_sha256)&&ref(c.receipt_ref,'receipt')&&list(c.event_ids,function(r){return ref(r,'event');})&&c.event_ids.length>0&&list(c.evidence_ids,function(r){return ref(r);})&&c.event_ids.every(function(r){return c.evidence_ids.includes(r);})&&c.sector_key==='solar'&&c.state==='watch'&&utc(c.decision_cutoff)&&utc(c.decided_at)&&c.runtime_validation==='current_API_validation'&&c.market_priced_in==='unknown'&&gate(c.forecast_gate)&&c.forecast_gate.status==='held'&&gate(c.trade_gate)&&c.trade_gate.status==='held'&&texts(c.official_urls)&&object(d)&&nonempty(d.what_changed)&&nonempty(d.provenance)&&nonempty(d.numeric_status)&&d.priced_in===null&&['companies_and_mechanism','counterevidence','next_official_checks','unknowns'].every(function(k){return texts(d[k]);})&&list(d.clocks,sourceClock)&&d.clocks.length>0&&d.clocks.every(function(x){return c.evidence_ids.includes(x.source_ref);})&&list(d.numeric_claims,function(m){return object(m)&&m.approval==='reviewed_source_claim'&&nonempty(m.name)&&nonempty(m.unit)&&nonempty(m.basis)&&nonempty(m.claim_context)&&typeof m.value==='number'&&Number.isFinite(m.value)&&nullable(m.observed_on,dateOnly)&&ref(m.evidence_ref,'source')&&c.evidence_ids.includes(m.evidence_ref);});
  }
  function referenceBinding(b){return object(b)&&['source','event','decision'].every(function(k){return ref(b[k+'_ref'],k)&&hash(b[k+'_sha256']);})&&ref(b.receipt_ref,'receipt')&&hash(b.raw_sha256)&&['capture_at','first_seen_at','decided_at'].every(function(k){return utc(b[k]);})&&nonempty(b.reviewed_capture_at)&&!isNaN(Date.parse(b.reviewed_capture_at))&&textValue(b.url)&&b.provenance_class==='archival/current_reference';}
  var ISSUERS={'KRX:009830':'한화솔루션','KRX:010060':'OCI홀딩스','KRX:456040':'OCI'};
  var CLAIM_KINDS={approximate_actual:'근사 실적',capacity:'명목 생산능력 · 출하량 아님',disclosure:'발표 사실',identity:'검토된 연결 정보',management_plan:'경영진 계획 · 달성 미확인',market_reference:'시장 참고값',policy_reference:'정책 참고값',reported_actual:'보고 실적'};
  function companyBinding(b){
    return object(b)&&b.kind==='company-persistence/1.0'&&['source','field','entity','decision','receipt'].every(function(k){return ref(b[k+'_ref'],'company_'+(k==='source'?'evidence':k))&&hash(b[k+'_sha256']);})&&hash(b.raw_sha256)&&hash(b.claim_sha256)&&nonempty(b.entity_id)&&nonempty(b.claim_id)&&textValue(b.url)&&b.provenance_class==='archival/current_reference'&&b.historical_public_available_at===null&&b.original_review_at===null&&['capture_at','first_seen_at','ingested_at','approved_at','decided_at','readback_at'].every(function(k){return utc(b[k]);})&&!isNaN(Date.parse(b.reviewed_capture_at))&&Date.parse(b.reviewed_capture_at)<=Date.parse(b.capture_at)&&Date.parse(b.capture_at)<=Date.parse(b.ingested_at)&&Date.parse(b.first_seen_at)<=Date.parse(b.ingested_at)&&b.approved_at===b.ingested_at&&b.decided_at===b.ingested_at&&Date.parse(b.readback_at)>=Date.parse(b.decided_at);
  }
  function persistedCompany(c,env){
    if(!history(env.bindings.company_history)||!env.bindings.company_history.sequence||!object(c.source_contexts)||!Object.values(c.source_contexts).every(companyBinding)||!list(c.held_fields,function(x){return object(x)&&nonempty(x.field)&&nonempty(x.reason_ko);}))return false;
    var rows=c.reference_claims, identity={'KRX:009830':'h.identity','KRX:010060':'o.identity','KRX:456040':'c.identity'}[c.issuer_id];
    if(!list(rows,function(row){
      if(!object(row)||!object(row.claim)||!companyBinding(row.binding))return false;
      var v=row.claim,b=row.binding,context=c.source_contexts[v.claim_id];
      return ['claim_id','entity_id','field','unit','period','basis','source_id','locator','display_ko'].every(function(k){return nonempty(v[k]);})&&Object.hasOwn(CLAIM_KINDS,v.claim_kind)&&jsonValue(v.value)&&nullable(v.observed_on,dateOnly)&&hash(v.source_sha256)&&v.source_sha256===b.raw_sha256&&v.entity_id===b.entity_id&&v.claim_id===b.claim_id&&!!context&&Object.keys(b).every(function(k){return b[k]===context[k];})&&Date.parse(b.readback_at)<=Date.parse(env.state_recorded_at);
    })||new Set(rows.map(function(r){return r.claim.claim_id;})).size!==rows.length)return false;
    var id=rows.find(function(r){return r.claim.claim_id===identity&&r.claim.entity_id===c.issuer_id;});
    return id ? c.identity_status==='persisted_current_reference'&&c.canonical_issuer_ref===id.binding.entity_ref : c.identity_status==='reviewed_crosswalk_only'&&c.canonical_issuer_ref===null;
  }
  function sourceChecks(row,env,clock){
    if(!Object.hasOwn(env.bindings,'company_history'))return !Object.hasOwn(row,'source_checks');
    var clocks=row.core.card.clocks;
    return history(env.bindings.company_history)&&list(row.source_checks,function(x){
      var old=clocks.find(function(c){return c.source_ref===x.source_ref;});
      return object(x)&&!!old&&ref(x.source_ref,'source')&&hash(x.source_sha256)&&hash(x.raw_sha256)&&ref(x.check_ref,'run')&&hash(x.check_sha256)&&['checked_at','completed_at','valid_until'].every(function(k){return utc(x[k]);})&&Number.isFinite(x.ttl_seconds)&&x.ttl_seconds>0&&x.ttl_seconds*1000===Date.parse(old.recheck_due_at)-Date.parse(old.capture_at)&&Date.parse(x.checked_at)>=Date.parse(old.capture_at)&&Date.parse(x.checked_at)<=Date.parse(x.completed_at)&&Date.parse(x.completed_at)<=Date.parse(env.state_recorded_at)&&Date.parse(x.valid_until)===Date.parse(x.checked_at)+x.ttl_seconds*1000&&Date.parse(x.valid_until)>=Date.parse(env.valid_until)&&Date.parse(x.valid_until)>clock.now;
    })&&row.source_checks.length===clocks.length&&new Set(row.source_checks.map(function(x){return x.source_ref;})).size===clocks.length;
  }
  function companyRow(c,env){
    if(!object(c)||!Object.hasOwn(ISSUERS,c.issuer_id)||c.display_name_ko!==ISSUERS[c.issuer_id]||c.reviewed_entity_ref!=='entity:'+c.issuer_id+'@1'||!['reviewed_crosswalk_only','persisted_current_reference'].includes(c.identity_status)||c.transmission_status!=='held'||!nonempty(c.transmission_reason)||c.forecast_status!=='held'||c.market_priced_in!=='unknown'||c.actionable!==false||c.review_manifest_sha256!==env.bindings.company_review_sha256||!object(c.source_contexts)||!Object.values(c.source_contexts).every(function(b){return referenceBinding(b)||companyBinding(b);})||!object(c.unknowns)||!Object.values(c.unknowns).every(function(v){return object(v)&&v.value===null&&nonempty(v.reason_ko);})||!texts(c.counterevidence)||!texts(c.next_checks))return false;
    if(c.held_fields!==undefined)return list(c.held_claims,function(x){return object(x)&&nonempty(x.claim_id)&&nonempty(x.source_id)&&['persisted_current_reference_unavailable','reviewed_document_version_changed'].includes(x.reason_code);})&&persistedCompany(c,env);
    if(c.canonical_issuer_ref!==null||c.identity_status!=='reviewed_crosswalk_only')return false;
    return list(c.held_claims,function(x){return object(x)&&nonempty(x.claim_id)&&nonempty(x.source_id)&&['persisted_current_reference_unavailable','reviewed_document_version_changed'].includes(x.reason_code);})&&list(c.reference_claims,function(row){
      if(!object(row)||!object(row.claim)||!referenceBinding(row.binding))return false;
      var v=row.claim,b=row.binding,context=c.source_contexts[v.source_id],core=env.cards.map(function(x){return x.core;}).find(function(x){return x.decision_ref===b.decision_ref;});
      return ['claim_id','entity_id','field','unit','period','basis','source_id','locator','display_ko'].every(function(k){return nonempty(v[k]);})&&Object.hasOwn(CLAIM_KINDS,v.claim_kind)&&jsonValue(v.value)&&nullable(v.observed_on,dateOnly)&&hash(v.source_sha256)&&v.source_sha256===b.raw_sha256&&!!context&&Object.keys(b).every(function(k){return b[k]===context[k];})&&!!core&&core.decision_sha256===b.decision_sha256&&core.receipt_ref===b.receipt_ref&&core.event_ids.includes(b.event_ref)&&core.evidence_ids.includes(b.source_ref)&&core.official_urls.includes(b.url);
    });
  }
  function sourceHealth(s){return object(s)&&['anza','hanwha','oci_ko','oci_en','whitehouse'].includes(s.source_id)&&textValue(s.url)&&['unchecked','degraded','stale','archival_reference','partial','checked_bounded'].includes(s.status)&&['last_good_capture_at','next_check_at','last_checked_at','oldest_unreviewed_at'].every(function(k){return nullable(s[k],utc);})&&count(s.pending_review_count)&&typeof s.live_endpoint_verified==='boolean'&&s.complete_history_scanned===false&&s.delivery_status==='disabled'&&s.latency_status==='unknown'&&s.issue_to_discovery_latency_seconds===null&&nullable(s.last_attempt_ref,function(x){return ref(x);})&&list(s.failed_or_incomplete_attempts,function(x){return ref(x);})&&(s.frontier===null||(object(s.frontier)&&s.frontier.source_id===s.source_id&&typeof s.frontier.baseline==='boolean'&&typeof s.frontier.reached_prior_frontier==='boolean'&&texts(s.frontier.checked_pages)&&texts(s.frontier.unvisited_urls)&&texts(s.frontier.gaps)));}
  function healthShape(h){return object(h)&&h.schema_version==='catalyst-source-health/1.0'&&['actual_utc','injected_test_clock'].includes(h.clock_basis)&&['requires_attention','bounded_evidence_only'].includes(h.operational_status)&&list(h.sources,sourceHealth)&&new Set(h.sources.map(function(s){return s.source_id;})).size===h.sources.length&&['review_count','candidate_count','verified_core_card_count','displayable_core_card_count','temporary_file_count','pending_review_count'].every(function(k){return count(h[k]);})&&history(h.history_receipt)&&nullable(h.oldest_unreviewed_at,utc)&&typeof h.production_history==='boolean'&&h.complete_history_scanned===false&&h.forecast_status==='held'&&h.market_priced_in==='unknown'&&list(h.incomplete_runs,function(x){return ref(x);})&&list(h.retained_errors,function(x){return object(x)&&ref(x.attempt_ref)&&textValue(x.url)&&nonempty(x.error_code);});}
  function pendingDocument(d){return object(d)&&textValue(d.url)&&utc(d.first_seen_at)&&['baseline','newly_discovered_link'].includes(d.discovery_class)&&['offline_fixture','network_capture'].includes(d.origin)&&d.status==='document_review_required'&&['archival/current_reference','observed_link_only'].includes(d.provenance_class)&&texts(d.source_ids)&&texts(d.counterevidence)&&texts(d.missingness)&&texts(d.gaps)&&nonempty(d.next_check)&&d.numeric_status==='held'&&d.forecast_status==='held'&&d.market_priced_in==='unknown'&&Array.isArray(d.numeric_claims)&&d.numeric_claims.length===0&&list(d.evidence_ids,function(x){return ref(x);})&&object(d.archive)&&['not_fetched','success','failed','in_progress'].includes(d.archive.status)&&['html','pdf'].includes(d.archive.media)&&nullable(d.archive.sha256,hash)&&nullable(d.archive.document_ref,function(x){return ref(x);})&&nullable(d.archive.blocking_attempt_ref,function(x){return ref(x);})&&nullable(d.archive.capture_at,utc)&&nullable(d.archive.last_successful_capture_at,utc)&&object(d.clocks)&&utc(d.clocks.first_seen_at)&&['published_at','observed_at','historical_available_at','decided_at'].every(function(k){return d.clocks[k]===null;})&&list(d.provenance,function(p){return object(p)&&ref(p.index_ref)&&textValue(p.index_url)&&nonempty(p.source_id)&&utc(p.capture_at)&&hash(p.raw_sha256)&&texts(p.keyword_matches)&&list(p.contexts,function(x){return object(x)&&textValue(x.title)&&nullable(x.listing_date_raw,textValue)&&['unknown','listing_date_only','publisher_listing_datetime_unverified','registration_local_timezone_unknown'].includes(x.listing_date_basis);});});}
  function heldCard(c){return object(c)&&nonempty(c.decision_ref)&&nonempty(c.reason_code)&&(['decision_sha256','receipt_ref','event_ids','evidence_ids'].every(function(k){return !Object.hasOwn(c,k);})||(ref(c.decision_ref,'decision')&&hash(c.decision_sha256)&&ref(c.receipt_ref,'receipt')&&list(c.event_ids,function(x){return ref(x,'event');})&&list(c.evidence_ids,function(x){return ref(x);})));}
  function catalystState(e, clock){
    clock=clock||catalystClock();
    var invalid={ok:false,reason:'자료 형식 또는 영속 기록 연결을 확인할 수 없어 보류합니다.'};
    try{
      if(!object(e)||e.schema_version!=='catalyst-ops-ui/1.0'||!hash(e.projection_id)||e.mode!=='shadow'||e.actionable!==false||e.forecast_status!=='held'||e.market_priced_in!=='unknown'||e.delivery_status!=='disabled'||!['available','partial','held'].includes(e.status)||!texts(e.reason_codes)||!textValue(e.consumer_rule)||!Array.isArray(e.scenarios)||e.scenarios.length||!Array.isArray(e.cards)||!Array.isArray(e.companies)||!list(e.held_cards,heldCard)||!Array.isArray(e.documents)||!Array.isArray(e.review_queue))return invalid;
      if(e.clock_basis!==clock.basis)return {ok:false,reason:'운영 시계 자료가 아닙니다. 테스트 자료의 현재 주장은 표시하지 않습니다.'};
      if(!utc(e.valid_until)||!utc(e.state_recorded_at)||Date.parse(e.valid_until)<=clock.now||Date.parse(e.state_recorded_at)>clock.now)return {ok:false,reason:'자료가 없거나 유효기간이 지났습니다. 최신 영속 기록을 다시 확인해야 합니다.'};
      if(e.status==='held')return {ok:false,reason:'현재 주장은 보류 중입니다. '+e.reason_codes.map(reasonLabel).join(' · ')};
      if(!bindings(e.bindings)||!healthShape(e.health)||e.health.clock_basis!==e.clock_basis||e.health.displayable_core_card_count!==e.cards.length||!list(e.cards,currentCard)||!list(e.companies,function(c){return companyRow(c,e);})||!list(e.documents,pendingDocument)||!list(e.review_queue,function(r){return object(r)&&nonempty(r.review_id)&&textValue(r.url)&&r.status==='document_review_required'&&nonempty(r.reason)&&list(r.evidence_ids,function(x){return ref(x);});}))return invalid;
      if(!e.cards.every(function(r){return sourceChecks(r,e,clock);})||Date.parse(e.valid_until)>Date.parse(e.state_recorded_at)+93600000)return invalid;
      if(e.health.incomplete_runs.length&&e.cards.length)return invalid;
      return {ok:true,data:e};
    }catch(_){return invalid;}
  }
  var REASONS={snapshot_expired:'스냅샷 만료',source_or_history_requires_attention:'출처·기록 확인 필요',company_reference_records_incomplete:'회사 참조 기록 불완전',runtime_unavailable_or_invalid:'런타임 자료 확인 불가',source_check_failed_or_stale:'원문 확인 실패 또는 오래된 확인',core_review_required:'원문 변경 · 재검토 필요',core_stale:'핵심 근거 확인기한 경과',core_invalidated:'핵심 근거 무효화',core_or_discovery_validation_held:'영속 기록 검증 보류',persisted_current_reference_unavailable:'연결된 원문·영속 참조 없음',reviewed_document_version_changed:'검토된 문서 버전 변경',fetch_failed:'원문 가져오기 실패'};
  function provenanceLabel(s){return s.startsWith('archival/current_reference;')?'보관 자료 · 현재 참조':s.startsWith('prospective shadow research;')?'향후 관찰 · 전향적 shadow 조사':'참조 성격 미확인';}
  function reasonLabel(s){return Object.hasOwn(REASONS,s)?REASONS[s]+' ('+s+')':s;}
  function node(doc,tag,text,cls){var n=doc.createElement(tag);if(text!==undefined)n.textContent=String(text);if(cls)n.className=cls;return n;}
  function add(parent,tag,text,cls){var n=node(parent.ownerDocument,tag,text,cls);parent.appendChild(n);return n;}
  function pairs(parent,rows){var dl=add(parent,'dl',undefined,'rd-facts');rows.forEach(function(r){add(dl,'dt',r[0]);add(dl,'dd',r[1]===null?'미확인':r[1]);});return dl;}
  function bullets(parent,items){var ul=add(parent,'ul');items.forEach(function(x){add(ul,'li',x);});}
  function disclosure(parent,title){var d=add(parent,'details');add(d,'summary',title);return d;}
  function external(parent,url,label){var safe=httpsURL(url);if(!safe){add(parent,'span',(label||url)+' · 안전한 HTTPS 주소 미확인');return;}var a=add(parent,'a',label||url);a.href=safe;a.target='_blank';a.rel='noopener noreferrer';}
  function factsBinding(parent,b){pairs(parent,[['원문 기록',b.source_ref],['원문 기록 SHA',b.source_sha256],['원문 바이트 SHA',b.raw_sha256],['이벤트',b.event_ref],['이벤트 SHA',b.event_sha256],['결정',b.decision_ref],['결정 SHA',b.decision_sha256],['영속화 영수증',b.receipt_ref],['수집 시각 UTC',b.capture_at],['시스템 최초 관측 UTC',b.first_seen_at],['결정 시각 UTC',b.decided_at],['검토된 수집 시각',b.reviewed_capture_at]]);external(parent,b.url);}
  function renderSourceHealth(parent,h){
    add(parent,'p','출처별 검토 대기는 문서 URL 수이며, 전체 검토 대기에는 버전·실패·핵심 검토 항목이 포함됩니다.','rd-muted');
    pairs(parent,[['전체 검토 대기',h.pending_review_count],['가장 오래된 미검토 최초 관측 UTC',h.oldest_unreviewed_at],['발행→발견 지연','미확인 · 발행 버전 시각 없음'],['알림 전달','비활성'],['전체 과거 기록','조사 범위 밖']]);
    var grid=add(parent,'div',undefined,'rd-research-grid');
    var labels={unchecked:'미확인',degraded:'원문 확인 실패',stale:'확인기한 경과',archival_reference:'보관 자료 참조',partial:'일부만 확인',checked_bounded:'제한 범위 확인'};
    h.sources.forEach(function(s){var a=add(grid,'article',undefined,'rd-research-card');add(a,'h4',s.source_id+' · '+labels[s.status]);pairs(a,[['마지막 시도 UTC',s.last_checked_at],['마지막 정상 수집 UTC',s.last_good_capture_at],['다음 확인 UTC',s.next_check_at],['검토 대기 URL',s.pending_review_count],['가장 오래된 미검토 최초 관측 UTC',s.oldest_unreviewed_at],['실시간 원문 확인',s.live_endpoint_verified?'이 실행에서 확인':'확인하지 않음']]);
      var more=disclosure(a,'수집 범위·실패 기록');external(more,s.url);pairs(more,[['마지막 시도',s.last_attempt_ref]]);bullets(more,s.failed_or_incomplete_attempts);if(s.frontier){pairs(more,[['발견 기준',s.frontier.baseline?'첫 기준선 · 신규 발행 아님':'이전 탐색 이후'],['이전 경계 도달',s.frontier.reached_prior_frontier?'예':'아니오']]);bullets(more,s.frontier.gaps);add(more,'p','확인한 페이지');s.frontier.checked_pages.forEach(function(u){external(add(more,'p'),u);});add(more,'p','미방문 페이지');s.frontier.unvisited_urls.forEach(function(u){external(add(more,'p'),u);});}
    });
    h.retained_errors.forEach(function(e){var p=add(parent,'p',undefined,'rd-warning');add(p,'span',reasonLabel(e.error_code)+' · '+e.attempt_ref+' · ');external(p,e.url);});
    if(h.incomplete_runs.length){add(parent,'p','미완료 수집 실행','rd-warning');bullets(parent,h.incomplete_runs);}
  }
  function renderResearch(parent,state){
    parent.replaceChildren();
    if(!state.ok){add(parent,'p','조사 후보 · 표시 보류','rd-warning');add(parent,'p',state.reason);add(parent,'p','수치 전망 보류 · 시장 기대 반영 미확인');return;}
    var e=state.data;
    add(parent,'p','조사 후보 · '+(e.status==='partial'?'일부 근거 보류':'참조 가능'),'rd-research-status');
    add(parent,'p','각 카드의 보관 자료 · 현재 참조 또는 향후 관찰 구분을 확인하세요. 과거 실시간 탐지나 투자 실행 신호를 뜻하지 않습니다. 수치 전망 보류 · 시장 기대 반영 미확인.');
    pairs(parent,[['영속 상태 기록 UTC',e.state_recorded_at],['표시 유효기한 UTC',e.valid_until]]);
    add(parent,'p','정적 스냅샷은 새 배포 또는 유효기한 전까지 이후의 원문 실패를 알 수 없습니다.','rd-muted');
    if(e.reason_codes.length)bullets(parent,e.reason_codes.map(reasonLabel));
    add(parent,'h3','원문에 연결된 조사 후보 · '+e.cards.length+'건');
    if(!e.cards.length)add(parent,'p','표시 가능한 영속 결정이 없습니다.');
    var grid=add(parent,'div',undefined,'rd-research-grid');
    e.cards.forEach(function(row,index){var c=row.core,d=c.card,a=add(grid,'article',undefined,'rd-research-card');
      add(a,'span',provenanceLabel(d.provenance),'rd-tag');add(a,'h4','태양광 조사 후보 '+(index+1));add(a,'p',d.what_changed);add(a,'p','원문 승인 문구는 의미·수치 범위를 보존하기 위해 원어로 표시합니다.','rd-muted');
      add(a,'p','수치 전망 보류 · 시장 기대 반영 미확인','rd-warning');
      var nums=disclosure(a,'원문 관측값 · '+d.numeric_claims.length+'개');
      d.numeric_claims.forEach(function(m){var v=add(nums,'section',undefined,'rd-claim');add(v,'h5',m.name);pairs(v,[['원문 값',m.value],['단위',m.unit],['관측일',m.observed_on],['기준·범위',m.basis],['원문 문맥',m.claim_context],['근거',m.evidence_ref]]);});
      if(!d.numeric_claims.length)add(nums,'p','수치 주장은 승인되지 않았습니다.');
      var clock=disclosure(a,'출처별 시각 · 결정·영속 기록');pairs(clock,[['결정',c.decision_ref],['결정 SHA',c.decision_sha256],['영수증',c.receipt_ref],['결정 기준 UTC',c.decision_cutoff],['결정 시각 UTC',c.decided_at],['참조 성격',d.provenance]]);bullets(clock,c.event_ids);bullets(clock,c.evidence_ids);
      d.clocks.forEach(function(s){pairs(clock,[['원문',s.source_ref],['자료 관측일',s.observed_on],['발행일',s.published_on],['발행자가 표시한 발행 UTC',s.publisher_declared_published_at],['발행자가 표시한 수정 UTC',s.publisher_declared_modified_at],['수집 UTC',s.capture_at],['시스템 최초 관측 UTC',s.first_seen_at],['입력 UTC',s.ingested_at],['검증 UTC',s.validated_at],['과거 공개 시각 UTC',s.historical_public_available_at],['효력 시각 UTC',s.effective_at],['효력 시간대',s.effective_timezone],['재확인 기한 UTC',s.recheck_due_at]]);pairs(clock,Object.entries(s.metric_observation_dates).map(function(x){return ['항목 관측일 · '+x[0],x[1]];}));});c.official_urls.forEach(function(u){external(add(clock,'p'),u);});
      if(row.source_checks)row.source_checks.forEach(function(s){pairs(clock,[['현재 확인 기록',s.check_ref],['확인 기록 SHA',s.check_sha256],['현재 정상 확인 UTC',s.checked_at],['현재 출처 유효기한 UTC',s.valid_until]]);});
      var mechanism=disclosure(a,'회사 전달 경로 · 미확인·반증');bullets(mechanism,d.companies_and_mechanism);add(mechanism,'h5','미확인');bullets(mechanism,d.unknowns);add(mechanism,'h5','반증·상쇄 요인');bullets(mechanism,d.counterevidence);
      var next=disclosure(a,'향후 관찰 · 다음 공식 확인');bullets(next,d.next_official_checks);add(next,'p','다음 공식 확인일 TBD · 발행·실적 일정으로 추정하지 않습니다.');
      var gates=disclosure(a,'승인 범위와 보류 이유');[['관찰',row.watch_gate],['회사 연구',row.research_gate],['수치 전망',c.forecast_gate],['거래',c.trade_gate]].forEach(function(g){add(gates,'h5',g[0]+' · '+({pass:'통과',held:'보류',fail:'실패',not_evaluated:'미평가'}[g[1].status]));bullets(gates,g[1].reasons);bullets(gates,g[1].evidence_refs);});
    });
    var held=disclosure(parent,'현재 주장 표시 보류 · 고유 참조 '+new Set(e.held_cards.map(function(c){return c.decision_ref;})).size+'건');e.held_cards.forEach(function(c){var a=add(held,'article',undefined,'rd-claim');add(a,'p',reasonLabel(c.reason_code));pairs(a,[['보류 참조',c.decision_ref]]);if(c.receipt_ref){pairs(a,[['결정 SHA',c.decision_sha256],['영수증',c.receipt_ref]]);bullets(a,c.event_ids);bullets(a,c.evidence_ids);}});
    add(parent,'h3','회사별 근거와 보류 사항');
    e.companies.forEach(function(c){var d=disclosure(parent,c.display_name_ko+' · '+c.issuer_id+' · 회사 전파 보류');d.className='rd-company';add(d,'p',c.identity_status==='persisted_current_reference'?'원문과 항목별 승인·식별자·참조 결정·읽기 검증 영수증이 연결되어 있습니다. 보관 자료·현재 참조이며 회사 수혜나 전망을 승인하지 않습니다.':'검토된 식별자 대조표입니다. 발행사 영속 참조는 아직 없습니다.');pairs(d,[['종목',c.issuer_id],['검토 식별자',c.reviewed_entity_ref],['정식 발행사 참조',c.canonical_issuer_ref],['회사 전파 보류 사유',c.transmission_reason],['회사 검토 SHA',c.review_manifest_sha256]]);
      add(d,'h4','원문에 연결된 참고값 · '+c.reference_claims.length+'개');if(!c.reference_claims.length)add(d,'p','연결된 원문·영속 참조가 없어 참고값을 표시하지 않습니다.');
      c.reference_claims.forEach(function(row){var v=row.claim,a=add(d,'article',undefined,'rd-claim');add(a,'span',CLAIM_KINDS[v.claim_kind],'rd-tag');add(a,'h5',v.display_ko);pairs(a,[['원문 값',typeof v.value==='object'?JSON.stringify(v.value):String(v.value)],['단위',v.unit],['기간',v.period],['기준·범위',v.basis],['관측일',v.observed_on],['대상 식별자',v.entity_id],['원문 위치',v.locator]]);var refs=disclosure(a,'문서·항목·결정 연결');pairs(refs,[['주장 ID',v.claim_id],['필드',v.field],['검토 출처 ID',v.source_id],['검토 원문 SHA',v.source_sha256]]);if(row.binding.kind==='company-persistence/1.0'){pairs(refs,Object.entries(row.binding));external(refs,row.binding.url);}else factsBinding(refs,row.binding);});
      var missing=disclosure(d,'보류된 참고값 · '+c.held_claims.length+'개');c.held_claims.forEach(function(h){add(missing,'p',h.claim_id+' · '+h.source_id+' · '+reasonLabel(h.reason_code));});
      if(c.held_fields) c.held_fields.forEach(function(h){add(missing,'p',h.field+' · '+h.reason_ko);});
      var assumptions=disclosure(d,'시나리오 가정 · 계산 보류');add(assumptions,'p','필요한 재무 입력 가정이 없어 계산하지 않습니다. 기본 ASP·재가격 비율·환율·출하량은 설정하지 않았습니다.');pairs(assumptions,Object.entries(c.unknowns).map(function(x){return [x[0],'미확인 · '+x[1].reason_ko];}));add(assumptions,'p','IRA·AMPC가 보고 이익에 이미 포함된 경우 중복 가산하지 않습니다. 명목 생산능력은 출하량이 아니며 공정별 능력을 합산하지 않습니다.');
      add(d,'h4','반증·상쇄 요인');bullets(d,c.counterevidence);add(d,'h4','다음 공식 확인 · TBD');bullets(d,c.next_checks);
    });
    add(parent,'h3','출처 상태');renderSourceHealth(parent,e.health);
    var docs=disclosure(parent,'발견 문서 · '+e.documents.length+'건 · 검토 전');add(docs,'p','첫 기준선은 새 정책 발행이 아닙니다. 신규 링크 발견도 신규 발행을 증명하지 않습니다. OCI 등록일·PDF 경로 날짜로 정확한 발행 버전을 추정하지 않습니다.');
    e.documents.forEach(function(v){var titles=v.provenance.flatMap(function(p){return p.contexts.map(function(x){return x.title;});}).filter(Boolean),d=disclosure(docs,(v.discovery_class==='baseline'?'첫 기준선':'신규 발견 링크')+' · '+(titles[0]||v.url));external(d,v.url);pairs(d,[['최초 관측 UTC',v.first_seen_at],['발행 시각','미확인'],['수집 상태',v.archive.status],['문서 수집 UTC',v.archive.capture_at],['문서 마지막 정상 수집 UTC',v.archive.last_successful_capture_at],['문서 버전 SHA',v.archive.sha256],['문서 기록',v.archive.document_ref],['숫자 주장·전망','검토 보류'],['다음 확인',v.next_check]]);v.provenance.forEach(function(p){p.contexts.forEach(function(x){pairs(d,[['목록 제목',x.title],['목록 표기 날짜',x.listing_date_raw],['날짜의 범위',x.listing_date_basis]]);});pairs(d,[['목록 기록',p.index_ref],['목록 수집 UTC',p.capture_at],['목록 SHA',p.raw_sha256]]);});bullets(d,v.missingness);bullets(d,v.gaps);bullets(d,v.counterevidence);bullets(d,v.evidence_ids);});
    var queue=disclosure(parent,'검토 대기 항목 · '+e.review_queue.length+'건');e.review_queue.forEach(function(r){var d=disclosure(queue,r.reason);external(d,r.url);pairs(d,[['검토 ID',r.review_id]]);bullets(d,r.evidence_ids);});
    var bound=disclosure(parent,'스냅샷 버전과 영속 기록 연결');pairs(bound,[['스냅샷 SHA',e.projection_id],['핵심 기록 순번',e.bindings.core_history.sequence],['핵심 기록 SHA',e.bindings.core_history.sha256],['발견 기록 순번',e.bindings.discovery_history.sequence],['발견 기록 SHA',e.bindings.discovery_history.sha256],['설정 SHA',e.bindings.config_sha256],['회사 검토 SHA',e.bindings.company_review_sha256],['마지막 핵심 실행',e.bindings.latest_core_run_ref],['마지막 발견 실행',e.bindings.latest_discovery_run_ref]]);add(bound,'p','브라우저는 공개 스냅샷의 형식과 연결을 검사합니다. 비공개 원장을 다시 읽거나 이 SHA를 인증 서명으로 취급하지 않습니다.','rd-muted');
  }

  var core={catalystState:catalystState,renderResearch:renderResearch,healthShape:healthShape,renderSourceHealth:renderSourceHealth,tabIndex:tabIndex,httpsURL:httpsURL,safeLocation:safeLocation,cleanViews:cleanViews,cleanEvidence:cleanEvidence,calendarState:calendarState,filterEvents:filterEvents,rankMatches:rankMatches};
  if(typeof module==='object' && module.exports)module.exports=core;
  if(!root.document)return;
  if(root.PHXResearchDesk)return;
  var script=document.currentScript, base=new URL('../',script.src), dialog, opener, panel='search', lastPanel='search', searchItems=[], searchErrors=[], cal=null, calErrors=[], loading=null;
  var cs=calendarState({}), views=[], sessionViews=false, pendingEvidence=null;
  function url(path){return new URL(path,base).href;}
  function today(){return new Date(Date.now()+9*3600000).toISOString().slice(0,10);}
  function scriptLoad(path,key){ if(root[key])return Promise.resolve(root[key]); return new Promise(function(resolve,reject){
    var s=document.createElement('script'),timer=setTimeout(function(){reject(new Error('응답 시간 초과'));},15000);s.src=url(path);s.onload=function(){clearTimeout(timer);root[key]?resolve(root[key]):reject(new Error('자료 형식 확인 필요'));};s.onerror=function(){clearTimeout(timer);reject(new Error('불러오기 실패'));};document.head.appendChild(s);
  });}
  function jsonLoad(path){var controller=new AbortController(),timer=setTimeout(function(){controller.abort();},15000);return fetch(url(path),{signal:controller.signal}).then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}).finally(function(){clearTimeout(timer);});}
  function button(name,act,extra){return '<button type="button" data-rd-act="'+act+'" '+(extra||'')+'>'+name+'</button>';}
  function setMessage(s){dialog.querySelector('[data-rd-message]').textContent=s;}
  function readViews(){try{views=cleanViews(JSON.parse(localStorage.getItem(VIEW_KEY)||'[]'),base.href);}catch(_){/* Keep usable in-page saved views when storage becomes unavailable. */}}
  function writeViews(){try{localStorage.setItem(VIEW_KEY,JSON.stringify(views));sessionViews=false;return true;}catch(_){sessionViews=true;return false;}}
  function activeTitle(){var h=document.querySelector('#detailDialog[open] #detailName')||document.querySelector('#crumb b')||document.querySelector('.ptab.on')||document.querySelector('header h1');return (h?h.textContent:document.title).trim().slice(0,60);}
  function saveView(){
    if(!sessionViews)readViews();
    var name=dialog.querySelector('[data-rd-name]').value.trim().slice(0,60); if(!name){setMessage('저장할 화면의 이름을 입력하세요.');return;}
    var dest=safeLocation(location.href,base.href);if(dest==null){setMessage('이 화면은 저장 대상이 아닙니다.');return;}
    var prior=views.find(function(v){return v.name===name;});if(!prior&&views.length>=20){setMessage('화면은 20개까지 저장할 수 있습니다.');return;}
    var item={id:prior?prior.id:Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,8),name:name,url:dest,saved:new Date().toISOString(),calendar:calendarState(cs),panel:lastPanel,evidence:cleanEvidence(root.PHXEvidenceState?root.PHXEvidenceState.snapshot():{})};
    if(prior)views=views.map(function(v){return v.id===prior.id?item:v;});else views.unshift(item);
    var ok=writeViews();renderViews();setMessage(ok?'저장했습니다. 이 브라우저에서 다시 열 수 있습니다.':'브라우저 저장소를 사용할 수 없어 이번 화면에서만 유지됩니다.');
  }
  function restoreView(id){var v=views.find(function(x){return x.id===id;});if(!v)return;
    var safe=safeLocation(v.url,base.href);if(safe==null){setMessage('저장된 주소를 열 수 없습니다.');return;}
    var payload={version:1,expires:Date.now()+300000,url:safe,calendar:v.calendar,panel:v.panel,evidence:v.evidence};
    var target=new URL(url(safe));
    if(target.pathname===location.pathname && target.search===location.search){try{sessionStorage.removeItem(PENDING_KEY);}catch(_){}cs=calendarState(v.calendar);pendingEvidence=cleanEvidence(v.evidence);applyEvidence();renderCalendar();showPanel(v.panel);if(target.href!==location.href)location.assign(target.href);setMessage('저장한 화면과 선택을 복원했습니다.');return;}
    try{sessionStorage.setItem(PENDING_KEY,JSON.stringify(payload));}catch(_){setMessage('저장소를 사용할 수 없어 화면 주소만 복원합니다.');}
    location.assign(url(safe));
  }
  function applyEvidence(){if(pendingEvidence && root.PHXEvidenceState){root.PHXEvidenceState.restore(pendingEvidence);pendingEvidence=null;}}
  function loadData(){ if(loading)return loading;
    searchItems=[
      ['시장 수급','panoptes/#human','.flow'],['한국 신용·유동성','panoptes/#liq','.credit'],['지수 하락 에피소드','panoptes/#tech','.episodes'],['연준·시장 일정','panoptes/#fed','.fed'],['분쟁 지도','panoptes/#map','.map'],['시장 시그널','panoptes/#sig','.signals'],['해운','panoptes/#ship','.shipping'],
      ['소비 관측','index.html#tab=ct','.consumer'],['메모리 가격','index.html#tab=mem','.mem'],['실적 캘린더','index.html#tab=ecal','.ecal'],['ARGUS 사이클','argus/','.argus'],['ARGUS 품목 맵','argus/map.html','.series'],['데이터 연결·원문','argus/connections.html','.sources']
    ].map(function(a){return {name:a[0],url:a[1],command:a[2],search:a.join(' '),type:'바로가기',ticker:''};});
    renderSearch();
    var companies=scriptLoad('search_index.js','SIDX').then(function(rows){if(!Array.isArray(rows))throw new Error('색인 형식');rows.forEach(function(r){if(!Array.isArray(r)||!r[0]||!r[4])return;searchItems.push({name:String(r[1]||r[0]),ticker:String(r[3]||''),type:'기업',search:r.slice(0,6).concat(r[7]).join(' '),url:'index.html#'+new URLSearchParams({r:r[4],tab:r[5]||'dash',v:'detail',co:r[0]}).toString()});});}).catch(function(){searchErrors.push('기업 검색 자료를 불러오지 못했습니다.');}).then(renderSearch);
    var series=scriptLoad('argus/data_map.js','ARGUS_MAP').then(function(data){if(!Array.isArray(data.items))throw new Error('색인 형식');data.items.forEach(function(r){if(!r.id)return;searchItems.push({name:String(r.name||r.id),ticker:String(r.sid||''),type:'품목',search:[r.name,r.sid,r.category,r.chain,r.source].concat(r.aliases||[]).join(' '),url:'argus/map.html#series='+encodeURIComponent(r.id)});});}).catch(function(){searchErrors.push('ARGUS 품목 검색 자료를 불러오지 못했습니다.');}).then(renderSearch);
    var calendar=Promise.allSettled([scriptLoad('data_ecal.js','ECAL'),jsonLoad('panoptes/data/fed/fed_calendar.json'),scriptLoad('panoptes/research_calendar.js','PHXCalendar'),scriptLoad('consumer_tracking.js','PHXConsumer').then(function(client){return client.load(base).then(function(data){return {events:client.calendarEvents(data),publicCount:data.calendar.length};});})]).then(function(r){
      if(r[0].status==='rejected')calErrors.push('실적 일정을 불러오지 못했습니다.');if(r[1].status==='rejected')calErrors.push('시장 일정을 불러오지 못했습니다.');
      if(r[2].status==='fulfilled')cal=r[2].value.build(r[0].status==='fulfilled'?r[0].value:null,r[1].status==='fulfilled'?r[1].value:null);else calErrors.push('통합 일정 화면을 불러오지 못했습니다.');
      if(r[3].status==='fulfilled'&&cal){cal.events=cal.events.concat(r[3].value.events);cal.sources.push({id:'consumer',updatedLabel:null,eventCount:r[3].value.events.length});if(!r[3].value.events.length)calErrors.push('공개 가능한 소비 출시·공연 일정 0건 · 원문·권한 확인 필요');}
      else if(r[3].status==='rejected')calErrors.push('소비 일정을 불러오지 못했습니다. 기존 실적·시장 일정은 유지합니다.');
      renderCalendar();
    });
    loading=Promise.allSettled([companies,series,calendar]).then(function(){renderSearch();renderCalendar();});return loading;
  }
  var researchLoading=null,researchExpiry=null,researchData=null;
  function expireResearch(){
    if(!researchData)return;
    var state=catalystState(researchData);
    if(!state.ok){var restoreFocus=dialog.querySelector('[data-rd-research]').contains(document.activeElement);researchData=null;renderResearch(dialog.querySelector('[data-rd-research]'),state);if(restoreFocus)dialog.querySelector('[data-rd-act="research-refresh"]').focus();dialog.querySelector('[data-rd-research-message]').textContent='유효기간 경과 · 현재 주장 표시 보류';}
  }
  function loadResearch(){
    if(researchLoading)return researchLoading;
    clearTimeout(researchExpiry);researchData=null;
    var box=dialog.querySelector('[data-rd-research]'),message=dialog.querySelector('[data-rd-research-message]');
    box.replaceChildren();message.textContent='영속 기록 스냅샷을 확인하고 있습니다…';
    var controller=new AbortController(),timer=setTimeout(function(){controller.abort();},15000);
    researchLoading=fetch(url('panoptes/data/catalyst.json'),{signal:controller.signal,cache:'no-store',credentials:'same-origin',redirect:'error'}).then(function(r){
      if(!r.ok)throw new Error('response');
      if(Number(r.headers.get('content-length'))>8000000)throw new Error('size');
      return r.text();
    }).then(function(raw){if(raw.length>8000000)throw new Error('size');var value=JSON.parse(raw),state=catalystState(value);renderResearch(box,state);message.textContent=state.ok?'확인 완료 · 수치 전망 보류':'현재 주장 표시 보류';if(state.ok){researchData=value;researchExpiry=setTimeout(expireResearch,Math.min(2147483647,Math.max(1,Date.parse(value.valid_until)-catalystClock().now+1)));}}).catch(function(){researchData=null;renderResearch(box,{ok:false,reason:'공개 자료를 불러오지 못했습니다. 이전 주장은 지우고 보류합니다. 자료 다시 확인을 이용하세요.'});message.textContent='자료 연결 실패 · 표시 보류';}).finally(function(){clearTimeout(timer);researchLoading=null;});
    return researchLoading;
  }
  function renderSearch(){if(!dialog)return;var input=dialog.querySelector('[data-rd-search]'), box=dialog.querySelector('[data-rd-results]'), hits=rankMatches(searchItems,input.value), limited=hits.slice(0,60);
    box.innerHTML=searchErrors.map(function(s){return '<p class="rd-warning">'+esc(s)+'</p>';}).join('')+'<p class="rd-muted">'+hits.length+'개 목적지'+(hits.length>60?' · 상위 60개 표시':'')+'</p>'+limited.map(function(i){return '<a class="rd-result" href="'+esc(url(i.url))+'"><span class="rd-tag">'+esc(i.type)+'</span><strong>'+esc(i.name)+'</strong><span>'+esc(i.ticker||i.command||'')+'</span></a>';}).join('')+(!limited.length?'<p>일치하는 항목이 없습니다.</p>':'');
  }
  function renderCalendar(){if(!dialog)return;var box=dialog.querySelector('[data-rd-events]');if(!cal){box.innerHTML='<p role="status">'+esc(calErrors.join(' ')||'실적·시장 일정을 읽고 있습니다…')+'</p>';return;}
    var rows=filterEvents(cal.events,cs,today()), days={};rows.forEach(function(e){var k=e.date||'미정';(days[k]||(days[k]=[])).push(e);});
    var notices=calErrors.slice();if(cal.issues&&cal.issues.length)notices.push('입력 점검 '+cal.issues.length+'건 · 날짜 오류 등은 정상 일정으로 바꾸지 않았습니다.');
    box.innerHTML=notices.map(function(s){return '<p class="rd-warning">'+esc(s)+'</p>';}).join('')+'<p class="rd-muted">'+rows.length+'건 / '+cal.events.length+'건 · 표시 날짜 기준</p>'+Object.keys(days).sort().map(function(day){return '<section class="rd-day"><h3>'+esc(day)+'</h3>'+days[day].map(function(e){var source=e.sourceUrl?'<a href="'+esc(e.sourceUrl)+'" target="_blank" rel="noopener noreferrer">'+esc(e.sourceLabel||'원문')+' ↗</a>':esc(e.sourceLabel||'출처 미제공')+' · 원문 URL 미제공';
      return '<article class="rd-event"><div class="rd-time">'+esc(e.timeLabel)+'<small>'+esc(e.timezoneLabel)+'</small></div><div><div class="rd-event-title"><span class="rd-tag">'+(e.kind==='earnings'?'실적':e.kind==='consumer'?'소비 일정':'시장')+'</span><strong>'+esc(e.title)+'</strong>'+ (e.ticker?' <span class="rd-muted">'+esc(e.ticker)+'</span>':'')+'</div><div class="rd-muted">'+esc(e.statusLabel)+'</div><div class="rd-source">'+source+(e.detailUrl?' · <a href="'+esc(url(e.detailUrl))+'">관련 화면 →</a>':'')+'</div></div></article>';}).join('')+'</section>';}).join('')+(!rows.length?'<p>조건에 맞는 일정이 없습니다. 기간 또는 종류를 바꿔 보세요.</p>':'');
    var meta=dialog.querySelector('[data-rd-calmeta]');meta.textContent=(cal.sources||[]).map(function(s){return (s.id==='earnings'?'실적 자료':s.id==='consumer'?'소비 일정':'시장 자료')+' 갱신 '+(s.updatedLabel||'미상')+' · '+s.eventCount+'건';}).join(' · ');
  }
  function renderViews(){if(!dialog)return;dialog.querySelector('[data-rd-views]').innerHTML=views.map(function(v){return '<article class="rd-view"><div><strong>'+esc(v.name)+'</strong><p class="rd-muted">'+esc(v.url||'Phalanx')+'</p><small>'+esc(v.saved.slice(0,10))+'</small></div>'+button('열기','restore','data-rd-id="'+esc(v.id)+'"')+button('삭제','remove','data-rd-id="'+esc(v.id)+'" aria-label="'+esc(v.name)+' 저장 삭제"')+'</article>';}).join('')+(!views.length?'<p class="rd-muted">저장한 조사 화면이 없습니다.</p>':'')+(sessionViews?'<p class="rd-warning">브라우저 저장소를 사용할 수 없어 현재 화면에서만 유지됩니다.</p>':'');}
  function showPanel(which){if(['search','calendar','research'].includes(which))lastPanel=which;panel=RD_TABS.includes(which)?which:'search';dialog.querySelectorAll('[data-rd-panel]').forEach(function(e){e.hidden=e.dataset.rdPanel!==panel;});dialog.querySelectorAll('[data-rd-tab]').forEach(function(e){e.setAttribute('aria-selected',String(e.dataset.rdTab===panel));e.tabIndex=e.dataset.rdTab===panel?0:-1;});if(panel==='views'){dialog.querySelector('[data-rd-name]').value=activeTitle();renderViews();}if(panel==='calendar')syncFilters();if(panel==='research')loadResearch();}
  function syncFilters(){['q','kind','range','date'].forEach(function(k){var e=dialog.querySelector('[data-rd-cal="'+k+'"]');e.value=cs[k]||(k==='date'?today():'');});dialog.querySelector('[data-rd-cal="phx"]').checked=cs.phx;renderCalendar();}
  function open(which){if(!sessionViews)readViews();if(!dialog.open)opener=document.activeElement;showPanel(which||'search');if(!dialog.open)dialog.showModal();loadData();var target=dialog.querySelector(panel==='search'?'[data-rd-search]':panel==='calendar'?'[data-rd-cal="q"]':panel==='research'?'[data-rd-act="research-refresh"]':'[data-rd-name]');target.focus();}
  function close(){dialog.close();if(opener&&opener.focus)opener.focus();}
  function boot(){
    var style=document.createElement('style');style.textContent=CSS;document.head.appendChild(style);
    var launch=document.createElement('button');launch.className='rd-launch';launch.type='button';launch.textContent='연구 데스크';launch.title='통합 일정 · 검색 · 저장한 화면 (Alt+K)';launch.setAttribute('aria-haspopup','dialog');launch.onclick=function(){open('search');};
    (document.querySelector('header')||document.body).appendChild(launch);
    var detailHead=document.querySelector('#detailDialog .detail-head');if(detailHead){var detailLaunch=launch.cloneNode(true);detailLaunch.textContent='화면 저장';detailLaunch.title='이 품목의 화면 위치 저장';detailLaunch.onclick=function(){open('views');};detailHead.appendChild(detailLaunch);}
    dialog=document.createElement('dialog');dialog.className='rd-dialog';dialog.setAttribute('aria-labelledby','rd-title');
    dialog.innerHTML='<div class="rd-head"><div><h2 id="rd-title">연구 데스크</h2><p>기업 · 시장 · 원문을 이어서 살펴보세요.</p></div>'+button('닫기 ×','close')+'</div><div class="rd-tabs" role="tablist" aria-label="연구 도구">'+RD_TABS.map(function(k,i){return '<button type="button" role="tab" id="rd-tab-'+k+'" aria-controls="rd-'+k+'" data-rd-tab="'+k+'">'+['빠른 이동','통합 일정','조사 후보','저장한 화면'][i]+'</button>';}).join('')+'</div><div class="rd-content">'+
      '<section id="rd-search" data-rd-panel="search" role="tabpanel" aria-labelledby="rd-tab-search"><label class="rd-label">기업·티커·품목·화면<input data-rd-search type="search" placeholder="예: Kioxia, 구리, .flow, .mem" autocomplete="off"></label><p class="rd-muted">현재 Phalanx 기업과 ARGUS 품목에서 검색합니다. Enter로 첫 결과를 엽니다.</p><div data-rd-results></div></section>'+
      '<section id="rd-calendar" data-rd-panel="calendar" role="tabpanel" aria-labelledby="rd-tab-calendar" hidden><div class="rd-filters"><label>종류<select data-rd-cal="kind"><option value="all">전체</option><option value="earnings">실적</option><option value="macro">시장·연준</option><option value="consumer">소비 출시·공연</option></select></label><label>기간<select data-rd-cal="range"><option value="7">7일</option><option value="30">30일</option><option value="all">전체 기록</option><option value="tbd">날짜 미정</option></select></label><label class="rd-date">시작일<input type="date" data-rd-cal="date"></label><label class="rd-grow">기업·일정 검색<input type="search" data-rd-cal="q" placeholder="예: Adobe, FOMC"></label><label class="rd-check"><input type="checkbox" data-rd-cal="phx"> PHX 커버 실적</label></div><p class="rd-muted">실적은 미국·일본 현지 날짜, 시장 일정은 KST입니다. 시각 미정은 임의로 환산하지 않습니다. 원문 연결은 확인 완료를 뜻하지 않습니다.</p><p class="rd-muted" data-rd-calmeta></p><div data-rd-events></div></section>'+
      '<section id="rd-research" data-rd-panel="research" role="tabpanel" aria-labelledby="rd-tab-research" hidden><div class="rd-research-toolbar"><p>근거와 보류 사항을 함께 확인하세요.</p>'+button('자료 다시 확인','research-refresh')+'</div><p data-rd-research-message role="status" aria-live="polite"></p><div data-rd-research></div></section>'+
      '<section id="rd-views" data-rd-panel="views" role="tabpanel" aria-labelledby="rd-tab-views" hidden><p>현재 화면 위치와 시장 근거의 선택값을 이름 붙여 저장합니다. 이 브라우저에 저장되며 다른 기기로 동기화하지 않습니다.</p><form class="rd-save"><label class="rd-grow">화면 이름<input maxlength="60" data-rd-name required placeholder="예: 반도체 수급 조사"></label><button type="submit">현재 화면 저장</button></form><p class="rd-muted">같은 이름으로 저장하면 갱신합니다. 다른 차트·검색 필터는 저장하지 않습니다. 최대 20개 · 저장 시점의 데이터 복사본은 보관하지 않습니다.</p><div data-rd-views></div></section></div><p data-rd-message class="rd-message" role="status" aria-live="polite"></p>';
    document.body.appendChild(dialog);readViews();showPanel('search');
    dialog.addEventListener('click',function(ev){var a=ev.target.closest('a');if(a&&!ev.ctrlKey&&!ev.metaKey&&!ev.shiftKey&&!ev.altKey&&a.target!=='_blank'&&safeLocation(a.href,base.href)!==null){close();return;}var el=ev.target.closest('button');if(!el)return;if(el.dataset.rdTab){showPanel(el.dataset.rdTab);return;}var act=el.dataset.rdAct;if(act==='close')close();if(act==='research-refresh')loadResearch();if(act==='restore')restoreView(el.dataset.rdId);if(act==='remove'){if(!sessionViews)readViews();views=views.filter(function(v){return v.id!==el.dataset.rdId;});var ok=writeViews();renderViews();setMessage(ok?'저장한 화면을 삭제했습니다.':'현재 화면에서 삭제했습니다. 브라우저 저장소에는 반영하지 못했습니다.');}});
    dialog.addEventListener('cancel',function(ev){ev.preventDefault();close();});
    dialog.querySelector('.rd-save').addEventListener('submit',function(ev){ev.preventDefault();saveView();});
    dialog.querySelector('[data-rd-search]').addEventListener('input',renderSearch);
    dialog.querySelector('[data-rd-search]').addEventListener('keydown',function(ev){if(ev.key==='Enter'){ev.preventDefault();var first=dialog.querySelector('.rd-result');if(first)first.click();}});
    dialog.querySelectorAll('[data-rd-cal]').forEach(function(e){e.addEventListener(e.type==='search'?'input':'change',function(){cs[e.dataset.rdCal]=e.type==='checkbox'?e.checked:e.value;cs=calendarState(cs);renderCalendar();});});
    dialog.querySelector('.rd-tabs').addEventListener('keydown',function(ev){if(!['ArrowLeft','ArrowRight','Home','End'].includes(ev.key))return;ev.preventDefault();var bs=Array.from(dialog.querySelectorAll('[data-rd-tab]')),i=bs.indexOf(ev.target);if(i<0)return;i=tabIndex(ev.key,i,bs.length);showPanel(bs[i].dataset.rdTab);bs[i].focus();});
    dialog.addEventListener('keydown',function(ev){if(ev.key!=='Tab')return;var nodes=Array.from(dialog.querySelectorAll('button,input,select,a[href],summary,[tabindex]')).filter(function(n){return !n.disabled&&n.tabIndex>=0&&!n.closest('[hidden]')&&n.getClientRects().length>0;});var first=nodes[0],last=nodes[nodes.length-1];if(!first){ev.preventDefault();dialog.focus();return;}if(ev.shiftKey&&document.activeElement===first){ev.preventDefault();last.focus();}else if(!ev.shiftKey&&document.activeElement===last){ev.preventDefault();first.focus();}});
    document.addEventListener('visibilitychange',function(){if(!document.hidden&&dialog.open&&panel==='research')loadResearch();});
    document.addEventListener('keydown',function(ev){if(ev.altKey&&!ev.ctrlKey&&!ev.metaKey&&ev.key.toLowerCase()==='k'){ev.preventDefault();dialog.open?close():open('search');}});
    var restored=false;
    try{var r=JSON.parse(sessionStorage.getItem(PENDING_KEY)||'null');sessionStorage.removeItem(PENDING_KEY);if(r&&r.version===1&&r.expires>Date.now()&&r.expires<Date.now()+310000&&safeLocation(r.url,base.href)===safeLocation(location.href,base.href)){cs=calendarState(r.calendar);pendingEvidence=cleanEvidence(r.evidence);open(['calendar','research'].includes(r.panel)?r.panel:'search');restored=true;}}catch(_){}
    if(!restored){var requested=new URLSearchParams(location.search).get('desk');if(RD_TABS.includes(requested))open(requested);}
    applyEvidence();var tries=0,timer=setInterval(function(){applyEvidence();if(!pendingEvidence||++tries>40)clearInterval(timer);},250);
    root.PHXResearchDesk={open:open,close:close};
  }
  var CSS='.rd-launch{font:600 11px system-ui!important;color:#9ce4df!important;background:#143334!important;border:1px solid #327071!important;border-radius:8px;padding:8px 11px;cursor:pointer;white-space:nowrap;flex-shrink:0;margin-left:auto}.rd-dialog{box-sizing:border-box;width:min(1100px,94vw);height:min(850px,90dvh);max-height:90dvh;margin:auto;padding:0;color:#e7edf4;background:#0d1620;border:1px solid #385365;border-radius:16px;box-shadow:0 30px 100px #0009;font:13px/1.5 system-ui;overflow:hidden}.rd-dialog[open]{display:flex;flex-direction:column}.rd-dialog::backdrop{background:#050c17bb;backdrop-filter:blur(3px)}.rd-dialog *{box-sizing:border-box}.rd-dialog [hidden]{display:none!important}.rd-head{display:flex;gap:18px;align-items:center;justify-content:space-between;padding:20px 24px 14px;border-bottom:1px solid #263846}.rd-head h2{font-size:22px;letter-spacing:-.5px;margin:0}.rd-head p{color:#a8b9c9;margin:3px 0 0}.rd-dialog button,.rd-dialog input,.rd-dialog select{font:inherit;color:inherit;background:#142430;border:1px solid #3c5467;border-radius:7px;padding:8px 10px}.rd-dialog button{cursor:pointer}.rd-dialog button:hover,.rd-dialog a:hover{background:#1b3541;color:#b3fff4}.rd-dialog :focus-visible{outline:2px solid #71dcc9;outline-offset:2px}.rd-tabs{display:flex;gap:8px;padding:12px 24px}.rd-tabs [aria-selected=true]{background:#194841;color:#b5fff0;border-color:#49988a}.rd-content{overflow:auto;flex:1;min-height:0;padding:6px 24px 18px;overscroll-behavior:contain}.rd-dialog h3{font-size:14px;margin:12px 0 8px;color:#a8e5db}.rd-dialog p{margin:7px 0}.rd-label{display:block;font-weight:600}.rd-label input{display:block;width:100%;margin-top:7px;font-size:16px}.rd-muted{font-size:11px;color:#9eb2c4;line-height:1.6}.rd-warning{color:#f3cf84;font-size:12px}.rd-tag{font-size:10px;display:inline-block;padding:2px 6px;border-radius:4px;background:#263a47;color:#acd9e0;white-space:nowrap}.rd-result{display:flex;align-items:center;gap:12px;padding:12px 8px;border-bottom:1px solid #243642;color:#e7edf4;text-decoration:none}.rd-result>span:last-child{margin-left:auto;color:#9eb2c4;font-size:11px}.rd-filters{display:flex;gap:10px;align-items:end;flex-wrap:wrap}.rd-dialog label{font-size:12px}.rd-filters label:not(.rd-check)>input,.rd-filters select,.rd-save input{display:block;margin-top:4px;width:100%}.rd-grow{flex:1;min-width:170px}.rd-check{display:flex;align-items:center;gap:5px;min-height:38px}.rd-event{display:grid;grid-template-columns:145px 1fr;gap:12px;padding:12px 0;border-bottom:1px solid #243642}.rd-time{color:#c1d4df;font-size:12px}.rd-time small{display:block;font-size:10px;color:#9eb2c4}.rd-event-title{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}.rd-source{font-size:11px;margin-top:3px;color:#9eb2c4}.rd-dialog a{color:#86dccc;text-decoration:none}.rd-dialog a:hover{text-decoration:underline}.rd-save{display:flex;gap:10px;align-items:end;margin:16px 0}.rd-view{display:flex;gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #263846}.rd-view>div{flex:1;min-width:0;overflow-wrap:anywhere}.rd-view small{color:#9eb2c4}.rd-message{min-height:25px;padding:4px 24px 12px!important;color:#9be0cb;margin:0!important}.rd-day{margin-top:18px}@media(max-width:600px){.rd-launch{font-size:10px!important;padding:6px 8px}.rd-dialog{width:96vw;height:94dvh;max-height:94dvh;border-radius:10px}.rd-head{padding:14px}.rd-head h2{font-size:19px}.rd-content{padding:4px 14px 14px}.rd-tabs{padding:10px 14px;gap:6px}.rd-tabs button{font-size:12px;flex:1;padding:8px 4px}.rd-event{grid-template-columns:90px 1fr;gap:8px}.rd-filters>label{flex:1;min-width:100px}.rd-filters>.rd-grow{flex-basis:100%}.rd-filters>.rd-date{min-width:155px}.rd-save{flex-wrap:wrap}.rd-view{gap:6px}.rd-view button{padding:7px}.rd-result{gap:8px}.rd-result strong{min-width:0;overflow-wrap:anywhere}}';
  CSS += '.rd-research-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.rd-research-card,.rd-company{border:1px solid #314b59;border-radius:10px;padding:14px;min-width:0;background:#101e29}.rd-research-card h4,.rd-company h4{margin:8px 0;font-size:15px}.rd-research-card h5,.rd-company h5{font-size:13px;margin:10px 0}.rd-dialog details{margin:10px 0;border-top:1px solid #30434f;padding-top:9px;min-width:0}.rd-dialog summary{cursor:pointer;color:#b4e7dc;font-weight:600;padding:5px 0}.rd-facts{display:grid;grid-template-columns:minmax(85px,0.6fr) minmax(0,1.4fr);gap:5px 12px;font-size:12px;margin:10px 0}.rd-facts dt{color:#9eb2c4}.rd-facts dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}.rd-claim{border-bottom:1px solid #30434f;padding:8px 0}.rd-research-toolbar{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap}.rd-research-status{font-size:16px;font-weight:700;color:#b5fff0}.rd-dialog [data-rd-panel]{min-width:0;overflow-wrap:anywhere}.rd-dialog ul{padding-left:20px}.rd-dialog li{margin:6px 0}.rd-dialog .rd-event>div{min-width:0}.rd-dialog input,.rd-dialog select{max-width:100%;min-width:0}.rd-dialog [data-rd-panel=research] .rd-tag{white-space:normal}.rd-tabs button{min-width:0}.rd-content{overflow-x:hidden}@media(max-width:600px){.rd-research-grid{grid-template-columns:minmax(0,1fr)}.rd-facts{grid-template-columns:minmax(75px,0.65fr) minmax(0,1.35fr)}.rd-research-card{padding:12px}.rd-head{gap:10px}.rd-head>div{min-width:0}.rd-tabs button{line-height:1.3;min-height:44px}}@media(prefers-reduced-motion:reduce){.rd-dialog,.rd-dialog *{scroll-behavior:auto!important;animation:none!important;transition:none!important}}';
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})(typeof window!=='undefined'?window:globalThis);
