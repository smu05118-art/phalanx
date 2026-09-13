/* 업체 관측 원장 · 브라우저/Node 공용 앙상블. 생성물은 수정하지 않는다. */
(function(root,factory){
  var api=factory();
  if(typeof module==='object'&&module.exports) module.exports=api;
  else root.PhxCloud=api;
})(typeof window==='undefined'?globalThis:window,function(){
'use strict';
var AXES={demand:'수요·매출',delivery:'가동·공급',contracts:'신규 계약',pricing:'단가·수익성',funding:'자금 부담'};
var WEIGHTS={demand:30,delivery:25,contracts:20,pricing:15,funding:10};
var GROUPS={hyperscaler:'하이퍼스케일러',neocloud:'GPU 클라우드',colo:'임대·호스팅',china:'중화권'};
var EVIDENCE={confirmed:'공식 확인',target:'회사 목표',external:'외부 관측',inference:'추론',unverified:'미검증'};
var DAY=86400000;
function stamp(x){return /^\d{4}-\d{2}-\d{2}$/.test(x||'')?Date.parse(x+'T00:00:00Z'):NaN;}
function finite(x){return typeof x==='number'&&Number.isFinite(x);}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function url(s){try{var u=new URL(s);return u.protocol==='https:'&&!u.username&&!u.password?s:null;}catch(e){return null;}}
function current(rows,asof){
  var end=stamp(asof), map=new Map();
  rows.forEach(function(s){
    if(!Number.isFinite(stamp(s.observed_at))||stamp(s.observed_at)>end) return;
    if(s.published_at&&stamp(s.published_at)>end) return;
    var p=map.get(s.key);
    if(!p||s.revision>p.revision)map.set(s.key,s);
  });
  return Array.from(map.values());
}
function excluded(s,asof){
  if(!s.verified)return '원자료 미검증';
  if(s.evidence!=='confirmed')return EVIDENCE[s.evidence]+' · 실적 점수 제외';
  if(!finite(s.direction)||![-1,0,1].includes(s.direction)||!s.rule)return '비교 기준·귀속범위 부족';
  if(!finite(s.value)||!url(s.source_url))return '관측값·출처 부족';
  var now=stamp(asof), pub=stamp(s.published_at), verified=stamp(s.verified_at), seen=stamp(s.observed_at), eff=stamp(s.effective_at);
  if(![now,pub,verified,seen,eff].every(Number.isFinite))return '일자 정보 부족';
  if(Math.max(pub,verified,seen,eff)>now)return '기준일 이후 정보';
  if((now-eff)/DAY>180)return '180일 초과 관측';
  if(!AXES[s.axis])return '미지원 축';
  return null;
}
function ensemble(rows,provider,asof){
  var available=current(rows,asof).filter(function(s){return s.provider===provider;});
  // 최신 판정이 미검증/목표/누락이면 과거 확정값으로 소급 대체하지 않는다.
  var last=new Map();
  available.forEach(function(s){var k=s.origin+':'+s.metric,p=last.get(k);
    if(!p||String(s.effective_at||s.period)>String(p.effective_at||p.period)||
      ((s.effective_at||s.period)===(p.effective_at||p.period)&&s.revision>p.revision))last.set(k,s);});
  var eligible=Array.from(last.values()).filter(function(s){return !excluded(s,asof);});
  var axes={}, numerator=0, denominator=0, coverage=0, sources=new Set(), used=[];
  Object.keys(AXES).forEach(function(axis){
    var a=eligible.filter(function(s){return s.axis===axis;}), groups=new Map();
    a.forEach(function(s){var k=s.correlation_group||s.source_url;if(!groups.has(k))groups.set(k,[]);groups.get(k).push(s);});
    if(!groups.size){axes[axis]=null;return;}
    var n=0,d=0;
    groups.forEach(function(g){var direction=g.reduce(function(v,s){return v+s.direction;},0)/g.length;
      var age=Math.max.apply(null,g.map(function(s){return (stamp(asof)-stamp(s.effective_at))/DAY;}));
      var freshness=Math.pow(0.5,age/90);n+=direction*freshness;d+=freshness;
      g.forEach(function(s){used.push(s.id);sources.add(s.source_url);});
    });
    var value=n/d, freshness=d/groups.size;
    axes[axis]={direction:value,freshness:freshness,groups:groups.size,ids:a.map(function(s){return s.id;})};
    coverage+=WEIGHTS[axis];numerator+=value*WEIGHTS[axis]*freshness;denominator+=WEIGHTS[axis]*freshness;
  });
  var count=Object.values(axes).filter(Boolean).length;
  var score=count>=2&&coverage>=40?Math.round(50+50*numerator/denominator):null;
  return {provider:provider,asof:asof,score:score,coverage:coverage,axis_count:count,axes:axes,
    source_count:sources.size,used_ids:used,
    conflict:eligible.some(function(s){return s.direction>0;})&&eligible.some(function(s){return s.direction<0;}),
    status:score===null?'관측 부족':(coverage<80?'부분 관측':'관측 충족'),
    method:'판정 규칙 기반 관측 방향 · 예측/투자수익 확률 아님 · 백테스트 미실시'};
}
function filtered(rows,state){return rows.filter(function(s){return (!state.provider||s.provider===state.provider)&&
  (!state.axis||s.axis===state.axis)&&(!state.evidence||s.evidence===state.evidence)&&
  (!state.search||[s.title,s.scope,s.note,s.provider,s.period].join(' ').toLowerCase().includes(state.search.toLowerCase()));});}
function csv(rows,columns){return '\uFEFF'+[columns].concat(rows.map(function(r){return columns.map(function(c){return r[c]==null?'':r[c];});})).map(function(row){
  return row.map(function(v){var s=String(v);if(/^[=+@\-\t\r]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';}).join(',');}).join('\r\n');}
function value(s){return finite(s.value)?new Intl.NumberFormat('ko-KR',{maximumFractionDigits:2}).format(s.value)+' '+s.unit:'미공개';}
function dir(v){return v>0?'개선':v<0?'부담':'중립';}
function tone(v){return v>0?'up':v<0?'down':'flat';}
function badge(s){return '<span class="cs-badge '+(s.verified&&s.evidence==='confirmed'?'checked':'')+'">'+esc(EVIDENCE[s.evidence]||s.evidence)+'</span>';}
var cached=null, pending=null, error='', displayLimit=30, filters={axis:'',evidence:'',search:''};
function load(){
  if(cached)return Promise.resolve(cached);
  if(pending)return pending;
  var controller=new AbortController(), timer=setTimeout(function(){controller.abort();},12000);
  pending=fetch('data/cloud_signals/ledger.json',{signal:controller.signal,cache:'no-cache'})
  .then(function(r){if(!r.ok)throw Error('HTTP '+r.status);return r.json();})
  .then(function(d){if(d.schema!=='cloud_signals/1'||!d.providers||!Array.isArray(d.signals))throw Error('원장 형식 오류');cached=d;error='';return d;})
  .finally(function(){clearTimeout(timer);pending=null;});return pending;
}
function state(){var q=new URLSearchParams(location.search);return {view:q.get('cloudView')||'ledger',provider:q.get('cloud')||'NBIS'};}
function navigate(view,provider){var u=new URL(location.href);u.searchParams.set('cloudView',view);u.searchParams.set('cloud',provider||'NBIS');
  history.pushState(null,'',u);displayLimit=30;window.render();}
function download(name,body,type){var blob=new Blob([body],{type:type}),u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(u);},1000);}
function companyButton(p,selected){return '<button type="button" class="cs-provider '+(selected===p.id?'active':'')+'" data-company="'+esc(p.id)+'" aria-pressed="'+(selected===p.id)+'"><b>'+esc(p.name)+'</b><span>'+esc(p.id)+' · '+esc(GROUPS[p.group]||p.group)+'</span></button>';}
function nav(view){return '<nav class="cs-nav" aria-label="AI 클라우드 보기">'+[['ledger','업체별 신호'],['ensemble','앙상블'],['integration','연동 점검'],['charts','기존 차트']].map(function(x){return '<button type="button" data-view="'+x[0]+'" '+(view===x[0]?'aria-current="page" class="active"':'')+'>'+x[1]+'</button>';}).join('')+'</nav>';}
function selectedLink(tab,co,project){var hash='#tab='+tab;if(tab==='dc'&&project)hash+='&dcv=map&dcp='+encodeURIComponent(project);return hash;}
function metrics(summary){return '<div class="cs-score"><span>관측 방향</span><strong>'+ (summary.score==null?'—':summary.score) +'</strong><small>'+summary.status+' · 충족률 '+summary.coverage+'%</small></div>';}
function axesBar(e){return '<div class="cs-axes">'+Object.keys(AXES).map(function(k){var a=e.axes[k];return '<div><span>'+AXES[k]+' <small>'+WEIGHTS[k]+'%</small></span><b class="'+(a?tone(a.direction):'')+'">'+(a?dir(a.direction):'미충족')+'</b></div>';}).join('')+'</div>';}
function ledgerView(d,s,asof){
  var p=d.providers[s.provider]||d.providers.NBIS||Object.values(d.providers)[0];s.provider=p.id;
  var rows=current(d.signals,asof).filter(function(x){return x.provider===p.id;});
  var e=ensemble(d.signals,p.id,asof), projects=(d.integration.projects||{})[p.id]||[];
  var pick=Object.assign({},filters,{provider:p.id});
  var shown=filtered(rows,pick).sort(function(a,b){return Number(b.verified)-Number(a.verified)||String(b.published_at||b.period).localeCompare(String(a.published_at||a.period));});
  var h='<div class="cs-layout"><aside class="cs-providers" aria-label="클라우드 업체">'+Object.values(d.providers).map(function(x){return companyButton(x,p.id);}).join('')+'</aside><div class="cs-detail">';
  h+='<section class="cs-panel cs-company"><div><span class="cs-kicker">'+esc(GROUPS[p.group])+' / '+esc(p.id)+'</span><h2>'+esc(p.name)+'</h2><p>'+rows.filter(function(x){return x.verified;}).length+'개 원문 대조 · '+rows.filter(function(x){return !x.verified;}).length+'개 미검증</p></div>'+metrics(e)+'</section>'+axesBar(e);
  h+='<div class="cs-note">'+(e.conflict?'개선 신호와 자금·수익성 부담이 함께 관측됩니다. ':'')+'점수는 '+e.axis_count+'/5축의 규칙 기반 요약입니다. '+e.source_count+'개 원문에 의존하며, 같은 실적발표의 여러 항목은 독립 증거가 아닙니다.</div>';
  h+='<div class="cs-toolbar"><label>신호 유형<select data-filter="axis"><option value="">전체</option>'+Object.keys(AXES).map(function(k){return '<option value="'+k+'" '+(filters.axis===k?'selected':'')+'>'+AXES[k]+'</option>';}).join('')+'</select></label><label>근거<select data-filter="evidence"><option value="">전체</option>'+Object.keys(EVIDENCE).map(function(k){return '<option value="'+k+'" '+(filters.evidence===k?'selected':'')+'>'+EVIDENCE[k]+'</option>';}).join('')+'</select></label><label class="cs-search">검색<input type="search" data-filter="search" placeholder="지표·기간·근거 검색" value="'+esc(filters.search)+'"></label><button type="button" data-export="csv">선택 신호 CSV</button></div>';
  h+='<div class="cs-count" aria-live="polite">'+shown.length+'개 관측 · '+asof+' 기준</div><div class="cs-ledger">';
  if(!shown.length)h+='<div class="cs-empty">조건에 맞는 관측이 없습니다. 아직 수집되지 않은 값은 0으로 채우지 않습니다.</div>';
  shown.slice(0,displayLimit).forEach(function(r){var reason=excluded(r,asof),source=url(r.source_url),history=d.signals.filter(function(x){return x.key===r.key;});
    h+='<article class="cs-record">'+badge(r)+' <span class="cs-meta">'+esc(AXES[r.axis])+' · '+esc(r.period)+'</span><h3>'+esc(r.title)+'</h3><div class="cs-value">'+(finite(r.previous_value)?esc(new Intl.NumberFormat('ko-KR').format(r.previous_value))+' → ':'')+esc(value(r))+'</div><p>'+esc(r.scope)+'</p><p class="cs-muted">'+esc(r.note)+'</p><details><summary>근거·발견 시점 · v'+r.revision+'</summary><dl><dt>공표일</dt><dd>'+esc(r.published_at||'미확보 — 기간으로 대체하지 않음')+'</dd><dt>대상일</dt><dd>'+esc(r.effective_at||'원본 분기만 제공')+'</dd><dt>최초 수집</dt><dd>'+esc(r.first_seen_at)+'</dd><dt>이번 버전 수집</dt><dd>'+esc(r.observed_at)+'</dd><dt>앙상블</dt><dd>'+esc(reason||r.rule)+'</dd><dt>출처</dt><dd>'+(source?'<a href="'+esc(source)+'" target="_blank" rel="noopener noreferrer">원문 확인 ↗</a>':'원문 URL 미확보')+' · '+esc(r.source_path)+'</dd></dl>';
    if(history.length>1)h+='<ul>'+history.map(function(v){return '<li>v'+v.revision+' · '+esc(v.observed_at)+' · '+esc(value(v))+'</li>';}).join('')+'</ul>';
    h+='</details></article>';
  });h+='</div>';
  if(shown.length>displayLimit)h+='<button type="button" class="cs-more" data-more>관측 더 보기 ('+(shown.length-displayLimit)+')</button>';
  h+='<section class="cs-panel"><h3>함께 볼 팔랑크스 데이터</h3><div class="cs-links">'+[['dc','데이터센터'],['rack','서버·랙'],['mem','메모리'],['tech','공급망'],['ins','인사이트']].map(function(x){return '<a data-related href="'+selectedLink(x[0],p.id)+'">'+x[1]+' →</a>';}).join('')+'</div>';
  h+='<p class="cs-muted">업체 별칭과 일치하는 프로젝트 '+projects.length+'개. 운영사와 고객 연결을 구분하며 MW는 합산하지 않습니다.</p>';
  h+=projects.map(function(x){return '<a class="cs-project" data-related href="'+selectedLink('dc',p.id,x.id)+'">'+esc(x.name)+' <span>'+ (x.relation==='operator'?'운영사':'고객')+' 연결 →</span></a>';}).join('');
  h+='</section><details class="cs-panel"><summary>업체 공시·확인 대기</summary><p>'+esc(p.definition||'개별 공시범위를 원문에서 확인해야 합니다.')+'</p><p>'+esc(p.fiscal_note)+'</p><p>기존 수집기의 확인 대기 항목 '+p.pending.length+'개</p>'+p.sources.map(function(x){return '<p><a target="_blank" rel="noopener noreferrer" href="'+esc(x)+'">공식 IR / 공시 출처 ↗</a></p>';}).join('')+'</details></div></div>';
  return {html:h,exportRows:shown};
}
function ensembleView(d,asof){
  var results=Object.keys(d.providers).map(function(k){return ensemble(d.signals,k,asof);});
  var h='<section class="cs-panel"><h2>클라우드 앙상블</h2><p>수요 30 · 가동 25 · 계약 20 · 단가·수익성 15 · 자금 10. 검증된 관측만 요약합니다.</p><p class="cs-muted">0은 부담, 50은 혼재/중립, 100은 개선 방향입니다. 매수 순위·실적 상회 확률이 아닙니다. 업체 간 동일한 지표 구성이 아니므로 충족률과 근거를 함께 보세요.</p><button type="button" data-export="ensemble">앙상블 JSON</button></section>';
  Object.keys(GROUPS).forEach(function(g){var list=results.filter(function(e){return d.providers[e.provider].group===g;}).sort(function(a,b){return (b.score==null?-1:b.score)-(a.score==null?-1:a.score);});if(!list.length)return;
    h+='<section class="cs-panel"><h3>'+GROUPS[g]+'</h3><div class="cs-table-wrap"><table><thead><tr><th>업체</th><th>방향 점수</th><th>충족률</th>'+Object.values(AXES).map(function(a){return '<th>'+a+'</th>';}).join('')+'<th>근거</th></tr></thead><tbody>';
    list.forEach(function(e){h+='<tr><th><button type="button" class="cs-text-button" data-company="'+esc(e.provider)+'">'+esc(d.providers[e.provider].name)+'</button></th><td><b>'+(e.score==null?'—':e.score)+'</b>'+ (e.conflict?'<span class="cs-badge">상충</span>':'')+'</td><td>'+e.coverage+'%<small>'+e.status+'</small></td>'+Object.keys(AXES).map(function(a){return '<td class="'+(e.axes[a]?tone(e.axes[a].direction):'')+'">'+(e.axes[a]?dir(e.axes[a].direction):'—')+'</td>';}).join('')+'<td>'+e.source_count+'개 원문</td></tr>';});
    h+='</tbody></table></div></section>';
  });
  h+='<details class="cs-panel"><summary>계산 방법과 제외 규칙</summary><p>축별 개선 +1 / 중립 0 / 부담 −1. 같은 근거 그룹 내 여러 지표는 평균하고, 최신 관측의 시점에 따라 90일 반감기로 가중합니다. 점수 = 50 + 50 × 가용축 가중평균. 결측축은 분모에서도 제외하며 충족률에만 반영합니다.</p><p>최소 2개 축·가중치 40% 이상을 충족해야 점수를 표시합니다. 대상일 180일 초과, 미검증, 목표·추론, 미래 정보, 비교 기준 없는 항목은 제외합니다. 동일 지표는 최신 관측을 사용하고 정정 전 버전은 이력에만 보관합니다.</p><p>최초 수집일 '+esc(d.tracking_started)+' 이전의 시점 검증은 불가능합니다. 현재 점수는 학습·홀드아웃으로 검증한 예측모형이 아닙니다.</p></details>';
  return {html:h,exportRows:results};
}
function integrationView(d){var a=d.integration;
  var h='<section class="cs-panel"><h2>팔랑크스 데이터 연동 점검</h2><p>공통 CAPEX는 '+(a.shared_capex_equal?'4개 탭 일치 확인':'불일치 확인')+' · 업체별 프로젝트 연결 포함</p><p class="cs-muted">구조 연결 가능 여부와 투자 예측의 유효성은 별도로 판단합니다. 아래 상태는 '+esc(d.updated)+' 원장 생성 시점 기준입니다.</p></section><div class="cs-integration">';
  a.checks.forEach(function(c){var status={ready:'구조 확인',conditional:'조건부 연결',research:'검증 필요',conflict:'불일치'}[c.status];h+='<section class="cs-panel"><span class="cs-badge '+(c.status==='ready'?'checked':'')+'">'+status+'</span><h3>'+esc(c.title)+'</h3><p>'+esc(c.detail)+'</p><p class="cs-muted">확인된 항목 '+c.count+'개 · 연결 기준: '+esc(c.key)+'</p><a data-related href="#tab='+c.tab+'">관련 화면 →</a></section>';});
  return {html:h+'</div><section class="cs-panel"><h3>중복 집계·정의 충돌</h3><ul>'+a.caveats.map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul><p>업체별 관측과 점수는 window.PhxCloud.ensemble 및 JSON 내보내기로 다른 화면에서 재사용할 수 있습니다. 기존 인사이트·나우캐스트 생성기의 자동 수신은 아직 연결하지 않았습니다.</p></section>',exportRows:[]};
}
function bind(root,d,s,body,asof){
  root.querySelectorAll('[data-view]').forEach(function(b){b.onclick=function(){navigate(b.dataset.view,s.provider);};});
  root.querySelectorAll('[data-company]').forEach(function(b){b.onclick=function(){filters={axis:'',evidence:'',search:''};navigate('ledger',b.dataset.company);};});
  root.querySelectorAll('[data-filter]').forEach(function(input){var event=input.dataset.filter==='search'?'onchange':'onchange';input[event]=function(){filters[input.dataset.filter]=input.value;displayLimit=30;renderAI2();};});
  var more=root.querySelector('[data-more]');if(more)more.onclick=function(){displayLimit+=30;renderAI2();};
  root.querySelectorAll('[data-related]').forEach(function(a){a.onclick=function(ev){if(ev.metaKey||ev.ctrlKey||ev.shiftKey||ev.altKey)return;ev.preventDefault();history.pushState(null,'',a.getAttribute('href'));applyHash();render();window.scrollTo(0,0);};});
  root.querySelectorAll('[data-export]').forEach(function(b){b.onclick=function(){if(b.dataset.export==='csv')download(s.provider+'-signals.csv',csv(body.exportRows,['id','provider','title','period','value','unit','evidence','verified','published_at','first_seen_at','observed_at','source_url','scope','note']),'text/csv;charset=utf-8');
    else download('cloud-ensemble-'+asof+'.json',JSON.stringify({schema:'cloud_ensemble/1',asof:asof,ledger_updated:d.updated,weights:WEIGHTS,companies:body.exportRows},null,2),'application/json');};});
}
function render(original){
  var s=state(), main=document.getElementById('main');if(!main)return;
  if(!['ledger','ensemble','integration','charts'].includes(s.view))s.view='ledger';
  if(s.view==='charts'){original();var n=document.createElement('div');n.className='phx-cloud';n.innerHTML=nav(s.view);main.prepend(n);bind(n,null,s,null,null);return;}
  document.getElementById('catRow').style.display='none';document.getElementById('cnt').textContent='';
  document.getElementById('crumb').textContent='AI·클라우드 — 업체별 관측 · 앙상블';
  main.innerHTML='';var root=document.createElement('section');root.className='phx-cloud';main.appendChild(root);
  if(!cached){root.innerHTML=nav(s.view)+'<div class="cs-panel" role="status">'+(error?'관측 원장을 불러오지 못했습니다. <button type="button" data-retry>다시 시도</button>':'업체 관측 원장을 불러오는 중…')+'</div>';bind(root,null,s,null,null);
    if(error){root.querySelector('[data-retry]').onclick=function(){error='';render(original);};return;}
    load().then(function(){if(typeof ST!=='undefined'&&ST.tab==='ai')render(original);}).catch(function(e){error=String(e);if(typeof ST!=='undefined'&&ST.tab==='ai')render(original);});return;
  }
  var asof=new Date().toISOString().slice(0,10), d=cached;
  var body=s.view==='ensemble'?ensembleView(d,asof):s.view==='integration'?integrationView(d):ledgerView(d,s,asof);
  var age=Math.floor((stamp(asof)-stamp(d.updated))/DAY);
  root.innerHTML=nav(s.view)+'<header class="cs-heading"><div><span class="cs-kicker">PHALANX / CLOUD SIGNALS</span><h1>클라우드 관측실</h1></div><span class="cs-meta">'+Object.keys(d.providers).length+'개 업체 · 원장 갱신 '+esc(d.updated)+'</span></header>'+(age>2?'<div class="cs-note">원장 갱신 후 '+age+'일 경과. 실시간 정보가 아닙니다.</div>':'')+body.html;
  bind(root,d,s,body,asof);
  var foot=document.getElementById('foot');if(foot)foot.textContent='공식 원자료와 기존 팔랑크스 관측을 구분합니다. 점수는 관측 방향의 요약이며 예측 확률이 아닙니다. 수집 이후 이력만 보존합니다.';
}
return {AXES:AXES,WEIGHTS:WEIGHTS,current:current,excluded:excluded,ensemble:ensemble,filtered:filtered,csv:csv,render:render};
});
