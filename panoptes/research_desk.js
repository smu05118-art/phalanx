/* Shared research navigation, calendar and browser-local saved views. */
(function (root) {
  'use strict';
  var VIEW_KEY = 'phx:research-desk:views:v1', PENDING_KEY = 'phx:research-desk:restore:v1';
  var MAIN_KEYS = ['r','tab','v','cat','co','port','cur','g','luxview','luxbrand','luxticker','luxcompany','dcv','dcco','dcp','dcq','dcst','dcs','dcn','dcgr','dcgb','dcgm'];
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
      return path + (['search','calendar','views'].includes(desk) ? '?desk='+desk : '') + (hash ? '#'+hash : '');
    } catch (_) { return null; }
  }
  function calendarState(v) {
    v = v && typeof v === 'object' ? v : {};
    return {q: typeof v.q === 'string' ? v.q.slice(0,120) : '', kind:['all','earnings','macro'].includes(v.kind)?v.kind:'all',
      range:['7','30','all','tbd'].includes(v.range)?v.range:'7', phx:v.phx === true,
      date:/^\d{4}-\d{2}-\d{2}$/.test(v.date || '') && !isNaN(Date.parse(v.date)) && new Date(v.date).toISOString().slice(0,10)===v.date ? v.date : ''};
  }
  function cleanViews(raw, base) {
    if (!Array.isArray(raw)) return [];
    return raw.slice(0,20).flatMap(function(v) {
      if (!v || typeof v.id !== 'string' || !/^[a-z0-9-]{1,60}$/.test(v.id) || typeof v.name !== 'string' || !v.name.trim()) return [];
      var url = safeLocation(v.url,base); if (url == null) return [];
      return [{id:v.id,name:v.name.trim().slice(0,60),url:url,saved:typeof v.saved==='string'?v.saved.slice(0,30):'',
        calendar:calendarState(v.calendar), panel:['search','calendar','views'].includes(v.panel)?v.panel:'search',
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
  var core={safeLocation:safeLocation,cleanViews:cleanViews,cleanEvidence:cleanEvidence,calendarState:calendarState,filterEvents:filterEvents,rankMatches:rankMatches};
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
      ['메모리 가격','index.html#tab=mem','.mem'],['실적 캘린더','index.html#tab=ecal','.ecal'],['ARGUS 사이클','argus/','.argus'],['ARGUS 품목 맵','argus/map.html','.series'],['데이터 연결·원문','argus/connections.html','.sources']
    ].map(function(a){return {name:a[0],url:a[1],command:a[2],search:a.join(' '),type:'바로가기',ticker:''};});
    renderSearch();
    var companies=scriptLoad('search_index.js','SIDX').then(function(rows){if(!Array.isArray(rows))throw new Error('색인 형식');rows.forEach(function(r){if(!Array.isArray(r)||!r[0]||!r[4])return;searchItems.push({name:String(r[1]||r[0]),ticker:String(r[3]||''),type:'기업',search:r.slice(0,6).concat(r[7]).join(' '),url:'index.html#'+new URLSearchParams({r:r[4],tab:r[5]||'dash',v:'detail',co:r[0]}).toString()});});}).catch(function(){searchErrors.push('기업 검색 자료를 불러오지 못했습니다.');}).then(renderSearch);
    var series=scriptLoad('argus/data_map.js','ARGUS_MAP').then(function(data){if(!Array.isArray(data.items))throw new Error('색인 형식');data.items.forEach(function(r){if(!r.id)return;searchItems.push({name:String(r.name||r.id),ticker:String(r.sid||''),type:'품목',search:[r.name,r.sid,r.category,r.chain,r.source].concat(r.aliases||[]).join(' '),url:'argus/map.html#series='+encodeURIComponent(r.id)});});}).catch(function(){searchErrors.push('ARGUS 품목 검색 자료를 불러오지 못했습니다.');}).then(renderSearch);
    var calendar=Promise.allSettled([scriptLoad('data_ecal.js','ECAL'),jsonLoad('panoptes/data/fed/fed_calendar.json'),scriptLoad('panoptes/research_calendar.js','PHXCalendar')]).then(function(r){
      if(r[0].status==='rejected')calErrors.push('실적 일정을 불러오지 못했습니다.');if(r[1].status==='rejected')calErrors.push('시장 일정을 불러오지 못했습니다.');
      if(r[2].status==='fulfilled')cal=r[2].value.build(r[0].status==='fulfilled'?r[0].value:null,r[1].status==='fulfilled'?r[1].value:null);else calErrors.push('통합 일정 화면을 불러오지 못했습니다.');renderCalendar();
    });
    loading=Promise.allSettled([companies,series,calendar]).then(function(){renderSearch();renderCalendar();});return loading;
  }
  function renderSearch(){if(!dialog)return;var input=dialog.querySelector('[data-rd-search]'), box=dialog.querySelector('[data-rd-results]'), hits=rankMatches(searchItems,input.value), limited=hits.slice(0,60);
    box.innerHTML=searchErrors.map(function(s){return '<p class="rd-warning">'+esc(s)+'</p>';}).join('')+'<p class="rd-muted">'+hits.length+'개 목적지'+(hits.length>60?' · 상위 60개 표시':'')+'</p>'+limited.map(function(i){return '<a class="rd-result" href="'+esc(url(i.url))+'"><span class="rd-tag">'+esc(i.type)+'</span><strong>'+esc(i.name)+'</strong><span>'+esc(i.ticker||i.command||'')+'</span></a>';}).join('')+(!limited.length?'<p>일치하는 항목이 없습니다.</p>':'');
  }
  function renderCalendar(){if(!dialog)return;var box=dialog.querySelector('[data-rd-events]');if(!cal){box.innerHTML='<p role="status">'+esc(calErrors.join(' ')||'실적·시장 일정을 읽고 있습니다…')+'</p>';return;}
    var rows=filterEvents(cal.events,cs,today()), days={};rows.forEach(function(e){var k=e.date||'미정';(days[k]||(days[k]=[])).push(e);});
    var notices=calErrors.slice();if(cal.issues&&cal.issues.length)notices.push('입력 점검 '+cal.issues.length+'건 · 날짜 오류 등은 정상 일정으로 바꾸지 않았습니다.');
    box.innerHTML=notices.map(function(s){return '<p class="rd-warning">'+esc(s)+'</p>';}).join('')+'<p class="rd-muted">'+rows.length+'건 / '+cal.events.length+'건 · 표시 날짜 기준</p>'+Object.keys(days).sort().map(function(day){return '<section class="rd-day"><h3>'+esc(day)+'</h3>'+days[day].map(function(e){var source=e.sourceUrl?'<a href="'+esc(e.sourceUrl)+'" target="_blank" rel="noopener noreferrer">'+esc(e.sourceLabel||'원문')+' ↗</a>':esc(e.sourceLabel||'출처 미제공')+' · 원문 URL 미제공';
      return '<article class="rd-event"><div class="rd-time">'+esc(e.timeLabel)+'<small>'+esc(e.timezoneLabel)+'</small></div><div><div class="rd-event-title"><span class="rd-tag">'+(e.kind==='earnings'?'실적':'시장')+'</span><strong>'+esc(e.title)+'</strong>'+ (e.ticker?' <span class="rd-muted">'+esc(e.ticker)+'</span>':'')+'</div><div class="rd-muted">'+esc(e.statusLabel)+'</div><div class="rd-source">'+source+(e.detailUrl?' · <a href="'+esc(url(e.detailUrl))+'">관련 화면 →</a>':'')+'</div></div></article>';}).join('')+'</section>';}).join('')+(!rows.length?'<p>조건에 맞는 일정이 없습니다. 기간 또는 종류를 바꿔 보세요.</p>':'');
    var meta=dialog.querySelector('[data-rd-calmeta]');meta.textContent=(cal.sources||[]).map(function(s){return (s.id==='earnings'?'실적 자료':'시장 자료')+' 갱신 '+(s.updatedLabel||'미상')+' · '+s.eventCount+'건';}).join(' · ');
  }
  function renderViews(){if(!dialog)return;dialog.querySelector('[data-rd-views]').innerHTML=views.map(function(v){return '<article class="rd-view"><div><strong>'+esc(v.name)+'</strong><p class="rd-muted">'+esc(v.url||'Phalanx')+'</p><small>'+esc(v.saved.slice(0,10))+'</small></div>'+button('열기','restore','data-rd-id="'+esc(v.id)+'"')+button('삭제','remove','data-rd-id="'+esc(v.id)+'" aria-label="'+esc(v.name)+' 저장 삭제"')+'</article>';}).join('')+(!views.length?'<p class="rd-muted">저장한 조사 화면이 없습니다.</p>':'')+(sessionViews?'<p class="rd-warning">브라우저 저장소를 사용할 수 없어 현재 화면에서만 유지됩니다.</p>':'');}
  function showPanel(which){if(which==='search'||which==='calendar')lastPanel=which;panel=['search','calendar','views'].includes(which)?which:'search';dialog.querySelectorAll('[data-rd-panel]').forEach(function(e){e.hidden=e.dataset.rdPanel!==panel;});dialog.querySelectorAll('[data-rd-tab]').forEach(function(e){e.setAttribute('aria-selected',String(e.dataset.rdTab===panel));});if(panel==='views'){dialog.querySelector('[data-rd-name]').value=activeTitle();renderViews();}if(panel==='calendar')syncFilters();}
  function syncFilters(){['q','kind','range','date'].forEach(function(k){var e=dialog.querySelector('[data-rd-cal="'+k+'"]');e.value=cs[k]||(k==='date'?today():'');});dialog.querySelector('[data-rd-cal="phx"]').checked=cs.phx;renderCalendar();}
  function open(which){if(!sessionViews)readViews();opener=document.activeElement;showPanel(which||'search');if(!dialog.open)dialog.showModal();loadData();var target=dialog.querySelector(panel==='search'?'[data-rd-search]':panel==='calendar'?'[data-rd-cal="q"]':'[data-rd-name]');target.focus();}
  function close(){dialog.close();if(opener&&opener.focus)opener.focus();}
  function boot(){
    var style=document.createElement('style');style.textContent=CSS;document.head.appendChild(style);
    var launch=document.createElement('button');launch.className='rd-launch';launch.type='button';launch.textContent='연구 데스크';launch.title='통합 일정 · 검색 · 저장한 화면 (Alt+K)';launch.setAttribute('aria-haspopup','dialog');launch.onclick=function(){open('search');};
    (document.querySelector('header')||document.body).appendChild(launch);
    var detailHead=document.querySelector('#detailDialog .detail-head');if(detailHead){var detailLaunch=launch.cloneNode(true);detailLaunch.textContent='화면 저장';detailLaunch.title='이 품목의 화면 위치 저장';detailLaunch.onclick=function(){open('views');};detailHead.appendChild(detailLaunch);}
    dialog=document.createElement('dialog');dialog.className='rd-dialog';dialog.setAttribute('aria-labelledby','rd-title');
    dialog.innerHTML='<div class="rd-head"><div><h2 id="rd-title">연구 데스크</h2><p>기업 · 시장 · 원문을 이어서 살펴보세요.</p></div>'+button('닫기 ×','close')+'</div><div class="rd-tabs" role="tablist" aria-label="연구 도구">'+['search','calendar','views'].map(function(k,i){return '<button type="button" role="tab" aria-controls="rd-'+k+'" data-rd-tab="'+k+'">'+['빠른 이동','통합 일정','저장한 화면'][i]+'</button>';}).join('')+'</div><div class="rd-content">'+
      '<section id="rd-search" data-rd-panel="search" role="tabpanel"><label class="rd-label">기업·티커·품목·화면<input data-rd-search type="search" placeholder="예: Kioxia, 구리, .flow, .mem" autocomplete="off"></label><p class="rd-muted">현재 Phalanx 기업과 ARGUS 품목에서 검색합니다. Enter로 첫 결과를 엽니다.</p><div data-rd-results></div></section>'+
      '<section id="rd-calendar" data-rd-panel="calendar" role="tabpanel" hidden><div class="rd-filters"><label>종류<select data-rd-cal="kind"><option value="all">전체</option><option value="earnings">실적</option><option value="macro">시장·연준</option></select></label><label>기간<select data-rd-cal="range"><option value="7">7일</option><option value="30">30일</option><option value="all">전체 기록</option><option value="tbd">날짜 미정</option></select></label><label class="rd-date">시작일<input type="date" data-rd-cal="date"></label><label class="rd-grow">기업·일정 검색<input type="search" data-rd-cal="q" placeholder="예: Adobe, FOMC"></label><label class="rd-check"><input type="checkbox" data-rd-cal="phx"> PHX 커버 실적</label></div><p class="rd-muted">실적은 미국·일본 현지 날짜, 시장 일정은 KST입니다. 시각 미정은 임의로 환산하지 않습니다. 원문 연결은 확인 완료를 뜻하지 않습니다.</p><p class="rd-muted" data-rd-calmeta></p><div data-rd-events></div></section>'+
      '<section id="rd-views" data-rd-panel="views" role="tabpanel" hidden><p>현재 화면 위치와 시장 근거의 선택값을 이름 붙여 저장합니다. 이 브라우저에 저장되며 다른 기기로 동기화하지 않습니다.</p><form class="rd-save"><label class="rd-grow">화면 이름<input maxlength="60" data-rd-name required placeholder="예: 반도체 수급 조사"></label><button type="submit">현재 화면 저장</button></form><p class="rd-muted">같은 이름으로 저장하면 갱신합니다. 다른 차트·검색 필터는 저장하지 않습니다. 최대 20개 · 저장 시점의 데이터 복사본은 보관하지 않습니다.</p><div data-rd-views></div></section></div><p data-rd-message class="rd-message" role="status" aria-live="polite"></p>';
    document.body.appendChild(dialog);readViews();
    dialog.addEventListener('click',function(ev){var a=ev.target.closest('a');if(a&&!ev.ctrlKey&&!ev.metaKey&&!ev.shiftKey&&!ev.altKey&&a.target!=='_blank'&&safeLocation(a.href,base.href)!==null){close();return;}var el=ev.target.closest('button');if(!el)return;if(el.dataset.rdTab){showPanel(el.dataset.rdTab);return;}var act=el.dataset.rdAct;if(act==='close')close();if(act==='restore')restoreView(el.dataset.rdId);if(act==='remove'){if(!sessionViews)readViews();views=views.filter(function(v){return v.id!==el.dataset.rdId;});var ok=writeViews();renderViews();setMessage(ok?'저장한 화면을 삭제했습니다.':'현재 화면에서 삭제했습니다. 브라우저 저장소에는 반영하지 못했습니다.');}});
    dialog.addEventListener('cancel',function(ev){ev.preventDefault();close();});
    dialog.querySelector('.rd-save').addEventListener('submit',function(ev){ev.preventDefault();saveView();});
    dialog.querySelector('[data-rd-search]').addEventListener('input',renderSearch);
    dialog.querySelector('[data-rd-search]').addEventListener('keydown',function(ev){if(ev.key==='Enter'){ev.preventDefault();var first=dialog.querySelector('.rd-result');if(first)first.click();}});
    dialog.querySelectorAll('[data-rd-cal]').forEach(function(e){e.addEventListener(e.type==='search'?'input':'change',function(){cs[e.dataset.rdCal]=e.type==='checkbox'?e.checked:e.value;cs=calendarState(cs);renderCalendar();});});
    dialog.querySelector('.rd-tabs').addEventListener('keydown',function(ev){if(!['ArrowLeft','ArrowRight','Home','End'].includes(ev.key))return;ev.preventDefault();var bs=Array.from(dialog.querySelectorAll('[data-rd-tab]')),i=bs.indexOf(ev.target);i=ev.key==='Home'?0:ev.key==='End'?2:(i+(ev.key==='ArrowRight'?1:2))%3;showPanel(bs[i].dataset.rdTab);bs[i].focus();});
    document.addEventListener('keydown',function(ev){if(ev.altKey&&!ev.ctrlKey&&!ev.metaKey&&ev.key.toLowerCase()==='k'){ev.preventDefault();dialog.open?close():open('search');}});
    var restored=false;
    try{var r=JSON.parse(sessionStorage.getItem(PENDING_KEY)||'null');sessionStorage.removeItem(PENDING_KEY);if(r&&r.version===1&&r.expires>Date.now()&&r.expires<Date.now()+310000&&safeLocation(r.url,base.href)===safeLocation(location.href,base.href)){cs=calendarState(r.calendar);pendingEvidence=cleanEvidence(r.evidence);open(r.panel==='calendar'?'calendar':'search');restored=true;}}catch(_){}
    if(!restored){var requested=new URLSearchParams(location.search).get('desk');if(['search','calendar','views'].includes(requested))open(requested);}
    applyEvidence();var tries=0,timer=setInterval(function(){applyEvidence();if(!pendingEvidence||++tries>40)clearInterval(timer);},250);
    root.PHXResearchDesk={open:open,close:close};
  }
  var CSS='.rd-launch{font:600 11px system-ui!important;color:#9ce4df!important;background:#143334!important;border:1px solid #327071!important;border-radius:8px;padding:8px 11px;cursor:pointer;white-space:nowrap;flex-shrink:0;margin-left:auto}.rd-dialog{box-sizing:border-box;width:min(1100px,94vw);height:min(850px,90dvh);max-height:90dvh;margin:auto;padding:0;color:#e7edf4;background:#0d1620;border:1px solid #385365;border-radius:16px;box-shadow:0 30px 100px #0009;font:13px/1.5 system-ui;overflow:hidden}.rd-dialog[open]{display:flex;flex-direction:column}.rd-dialog::backdrop{background:#050c17bb;backdrop-filter:blur(3px)}.rd-dialog *{box-sizing:border-box}.rd-dialog [hidden]{display:none!important}.rd-head{display:flex;gap:18px;align-items:center;justify-content:space-between;padding:20px 24px 14px;border-bottom:1px solid #263846}.rd-head h2{font-size:22px;letter-spacing:-.5px;margin:0}.rd-head p{color:#a8b9c9;margin:3px 0 0}.rd-dialog button,.rd-dialog input,.rd-dialog select{font:inherit;color:inherit;background:#142430;border:1px solid #3c5467;border-radius:7px;padding:8px 10px}.rd-dialog button{cursor:pointer}.rd-dialog button:hover,.rd-dialog a:hover{background:#1b3541;color:#b3fff4}.rd-dialog :focus-visible{outline:2px solid #71dcc9;outline-offset:2px}.rd-tabs{display:flex;gap:8px;padding:12px 24px}.rd-tabs [aria-selected=true]{background:#194841;color:#b5fff0;border-color:#49988a}.rd-content{overflow:auto;flex:1;min-height:0;padding:6px 24px 18px;overscroll-behavior:contain}.rd-dialog h3{font-size:14px;margin:12px 0 8px;color:#a8e5db}.rd-dialog p{margin:7px 0}.rd-label{display:block;font-weight:600}.rd-label input{display:block;width:100%;margin-top:7px;font-size:16px}.rd-muted{font-size:11px;color:#9eb2c4;line-height:1.6}.rd-warning{color:#f3cf84;font-size:12px}.rd-tag{font-size:10px;display:inline-block;padding:2px 6px;border-radius:4px;background:#263a47;color:#acd9e0;white-space:nowrap}.rd-result{display:flex;align-items:center;gap:12px;padding:12px 8px;border-bottom:1px solid #243642;color:#e7edf4;text-decoration:none}.rd-result>span:last-child{margin-left:auto;color:#9eb2c4;font-size:11px}.rd-filters{display:flex;gap:10px;align-items:end;flex-wrap:wrap}.rd-dialog label{font-size:12px}.rd-filters label:not(.rd-check)>input,.rd-filters select,.rd-save input{display:block;margin-top:4px;width:100%}.rd-grow{flex:1;min-width:170px}.rd-check{display:flex;align-items:center;gap:5px;min-height:38px}.rd-event{display:grid;grid-template-columns:145px 1fr;gap:12px;padding:12px 0;border-bottom:1px solid #243642}.rd-time{color:#c1d4df;font-size:12px}.rd-time small{display:block;font-size:10px;color:#9eb2c4}.rd-event-title{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}.rd-source{font-size:11px;margin-top:3px;color:#9eb2c4}.rd-dialog a{color:#86dccc;text-decoration:none}.rd-dialog a:hover{text-decoration:underline}.rd-save{display:flex;gap:10px;align-items:end;margin:16px 0}.rd-view{display:flex;gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid #263846}.rd-view>div{flex:1;min-width:0;overflow-wrap:anywhere}.rd-view small{color:#9eb2c4}.rd-message{min-height:25px;padding:4px 24px 12px!important;color:#9be0cb;margin:0!important}.rd-day{margin-top:18px}@media(max-width:600px){.rd-launch{font-size:10px!important;padding:6px 8px}.rd-dialog{width:96vw;height:94dvh;max-height:94dvh;border-radius:10px}.rd-head{padding:14px}.rd-head h2{font-size:19px}.rd-content{padding:4px 14px 14px}.rd-tabs{padding:10px 14px;gap:6px}.rd-tabs button{font-size:12px;flex:1;padding:8px 4px}.rd-event{grid-template-columns:90px 1fr;gap:8px}.rd-filters>label{flex:1;min-width:100px}.rd-filters>.rd-grow{flex-basis:100%}.rd-filters>.rd-date{min-width:155px}.rd-save{flex-wrap:wrap}.rd-view{gap:6px}.rd-view button{padding:7px}.rd-result{gap:8px}.rd-result strong{min-width:0;overflow-wrap:anywhere}}';
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})(typeof window!=='undefined'?window:globalThis);
