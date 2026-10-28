/* Common-contract renderer. Source adapters belong upstream; no network requests. */
(function (root) {
  'use strict';
  const finite = v => typeof v === 'number' && Number.isFinite(v);
  const exact = p => p.comparable!==false && ['reported','eq','='].includes(p.value_relation||'reported');
  const relation = p => ({lower_bound:' 초과 하한',gt:' 초과 하한',ge:' 이상 하한',low:' 구간 하한',high:' 구간 상한'}[p.value_relation]||'');
  const statusLabel = status => ({available:'완전 연결',partial:'부분 연결',missing:'결측 · 자료/검증 부족',blocked:'결측 · 공개 대체자료 없음'}[status]||status);
  const esc = s => String(s ?? '미확인').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function fiscal(p) {
    const m = /^(?:FY)?(\d{4})\s*Q([1-4])$/.exec(p.period || '');
    return m ? Number(m[1]) * 4 + Number(m[2]) - 1 : null;
  }
  function derivable(s, mode) {
    if (mode === 'raw') return true;
    if (s.points.some(p=>!exact(p))) return false;
    if (mode === 'index') return true;
    if (s.frequency !== 'quarterly' || s.kind !== 'actual' || s.points.some(p => fiscal(p) === null)) return false;
    if (new Set(s.points.map(p=>/^FY/.test(p.period)?'fiscal':'calendar')).size!==1) return false;
    if (new Set(s.points.map(fiscal)).size !== s.points.length) return false;
    // Explicit comparable, discrete basis prevents summing YTD/stock fields or changing fiscal definitions.
    return s.period_basis === 'discrete' && Boolean(s.comparable_basis) && (mode !== 'ttm' || s.measure_type === 'flow');
  }
  function transform(s, mode) {
    const by = new Map(s.points.map(p => [fiscal(p), p]));
    const baseline = s.points.find(p => finite(p.value));
    return s.points.map(p => {
      let value = p.value, evidence = [p];
      if (mode === 'index') {
        evidence = baseline ? [p, baseline] : [p];
        value = derivable(s,mode) && finite(value) && baseline?.value > 0 ? value / baseline.value * 100 : null;
      } else if (mode !== 'raw') {
        if (!derivable(s, mode)) value = null;
        else if (mode === 'ttm') {
          evidence = [3,2,1,0].map(offset => by.get(fiscal(p)-offset));
          value = evidence.every(q => q && finite(q.value)) ? evidence.reduce((v,q)=>v+q.value,0) : null;
        } else {
          const previous = by.get(fiscal(p) - (mode === 'yoy' ? 4 : 1));
          evidence = [p, previous];
          value = finite(p.value) && previous && finite(previous.value) && previous.value > 0 ? (p.value/previous.value-1)*100 : null;
        }
      }
      return {...p, value:finite(value)?value:null, evidence:evidence.filter(Boolean), unit:mode==='index'?'기준=100':mode==='yoy'||mode==='qoq'?'%':s.unit};
    });
  }
  function cutoff(asof, range) {
    if (range==='all') return '';
    const d = new Date(asof+'T00:00:00Z');
    const day=d.getUTCDate(); d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()-Number(range));
    const last=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,0)).getUTCDate();d.setUTCDate(Math.min(day,last));
    return d.toISOString().slice(0,10);
  }
  function view(panel, state, asof) {
    if(['blocked','missing'].includes(panel.status)) return [];
    let series = panel.series.filter(s => (state.metric==='all'||s.metric===state.metric) && (state.entity==='all'||s.entity===state.entity));
    const from=cutoff(asof,state.range);
    series = series.map(s=>({...s, points:s.points.filter(p=>p.date<=asof || s.kind!=='actual')}));
    if(state.mode==='index') series=series.map(s=>({...s,points:s.points.filter(p=>p.date>=from)}));
    if(state.compare==='aligned' && ['raw','index'].includes(state.mode)) {
      // Exact common observed dates only; no interpolation or partial-basket mean.
      const common=series.length ? series[0].points.filter(p=>finite(p.value)).map(p=>p.date).filter(d=>series.every(s=>s.points.some(p=>p.date===d&&finite(p.value)))) : [];
      series=series.map(s=>({...s,points:s.points.filter(p=>common.includes(p.date))}));
    }
    return series.map(s=>({...s,points:transform(s,state.mode).filter(p=>p.date>=from)}));
  }
  function cashBridge(series) {
    const selected=['ocf','capex','ppe_proceeds'].map(metric=>series.filter(s=>s.entity==='AMZN'&&s.metric===metric&&s.kind==='actual'&&s.unit==='USD B'));
    if(selected.some(s=>s.length!==1))return null;
    const [ocf,capex,proceeds]=selected.map(s=>s[0]);
    if(ocf.basis!=='cash_ppe'||capex.basis!=='cash_ppe'||selected.some(([s])=>s.frequency!=='quarterly'||s.period_basis!=='discrete'))return null;
    for(const a of [...ocf.points].sort((a,b)=>b.date.localeCompare(a.date))) {
      const matches=[capex,proceeds].map(s=>s.points.filter(p=>p.date===a.date&&p.period===a.period));
      if(matches.some(p=>p.length!==1))continue;
      const evidence=[a,...matches.map(p=>p[0])];
      if(evidence.some(p=>!finite(p.value)||!exact(p)||p.unit&&p.unit!=='USD B'||p.source_url!==a.source_url))continue;
      const simple=a.value-evidence[1].value,net=simple+evidence[2].value;
      return {date:a.date,period:a.period,unit:'USD B',evidence,
        values:[a.value,-evidence[1].value,simple,evidence[2].value,net],
        measures:['absolute','relative','total','relative','total'],
        labels:['영업현금흐름','현금 PP&E 취득','단순 FCF','매각·인센티브','순투자 차감 현금흐름']};
    }
    return null;
  }
  function chartPoints(s) {
    const out=[];let previous=null;
    for(const p of s.points) {
      if(previous&&s.frequency==='quarterly'&&fiscal(p)!==null&&fiscal(previous)!==null&&fiscal(p)-fiscal(previous)!==1)
        out.push({date:null,value:null,evidence:[],note:'Missing quarter: visual break only, not an observation'});
      out.push(p);previous=p;
    }
    return out;
  }
  function singleDateRange(traces) {
    const dates=Array.from(new Set(traces.flatMap(s=>s.x).filter(Boolean)));
    if(dates.length!==1)return undefined;
    const date=Date.parse(dates[0]+'T00:00:00Z');
    if(!Number.isFinite(date))return undefined;
    return [-15,15].map(days=>new Date(date+days*86400000).toISOString().slice(0,10));
  }
  const API={fiscal,derivable,transform,cutoff,view,cashBridge,chartPoints,singleDateRange,statusLabel};
  if(typeof module!=='undefined'&&module.exports) module.exports=API;
  root.AICycle=API;
  if(typeof document==='undefined') return;
  const $=id=>document.getElementById(id);
  const D=JSON.parse($('ai-cycle-payload').textContent), release=JSON.parse($('ai-cycle-release').textContent);
  const panels={...D.panels}, states=new Map(), rendered=new Set(), errors=[], pending=new Map();
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const missing='원문 URL·관측일·회계기간·단위가 확인된 공개 자료가 필요합니다. 인과관계나 전망을 추론하지 않습니다.';
  const reason='검증된 공개 기저 또는 비교 가능한 정의가 없습니다.';
  const labels={raw:'원자료',yoy:'전년 동기 대비',qoq:'직전 분기 대비',ttm:'최근 네 분기 합계',index:'선택 구간 첫 관측=100'};
  function link(url,label) {
    const a=node('a',label);
    try {const u=new URL(url);if(!['https:','http:'].includes(u.protocol)||u.username||u.password)throw Error();a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';}
    catch {a.removeAttribute('href');a.textContent='출처 URL 미확인';}return a;
  }
  function summary(p) {
    const count=p.series.reduce((n,s)=>n+s.points.filter(q=>finite(q.value)).length,0);
    return `${D.asof} 기준 · ${statusLabel(p.status)} · 검증 수치 ${count}개. ${p.status==='blocked'||p.status==='missing' ? (p.reason||missing) : (p.reading||'공개 관측값만 표시합니다. 방향성과 인과관계는 추가 근거 없이 판단하지 않습니다.')} ${(p.warnings||[]).join(' · ')}`;
  }
  function evidenceText(p,s,panel) {
    return `관측 ${p.date} · 회계 ${p.period||'미확인'} · 발표 ${p.published_at||'미확인'} · 확인 ${p.verified_at||'미확인'} · ${s.kind}${relation(p)} · ${statusLabel(panel.status)} · ${s.unit} · ${p.source_pipeline||p.source_system||'미확인'} · ${p.source_url||'미확인'} · ${p.note||''}`;
  }
  function tableFor(series,panel) {
    const wrap=node('div',undefined,'table-scroll'), table=node('table');
    const caption=node('caption','관측·회계기간·출처 및 계산에 사용한 모든 근거');table.append(caption);
    const head=node('thead'), row=node('tr');['계열','관측일 / 회계기간','표시값 / 단위','상태 / 종류','근거'].forEach(x=>row.append(node('th',x)));head.append(row);table.append(head);
    const body=node('tbody');
    for(const s of series) for(const p of s.points) {
      const tr=node('tr');[s.name,`${p.date} / ${p.period||'미확인'}`,`${finite(p.value)?p.value.toLocaleString('ko-KR',{maximumFractionDigits:6}):'결측'} ${p.unit||s.unit}${relation(p)}`,`${statusLabel(panel.status)} / ${s.kind}`].forEach(x=>tr.append(node('td',x)));
      const cell=node('td');for(const e of p.evidence||[p]) {const line=node('p',evidenceText(e,s,panel));line.append(' ',link(e.source_url,'원문'));cell.append(line);}tr.append(cell);body.append(tr);
    }
    table.append(body);wrap.append(table);return wrap;
  }
  function selectControl(id,key,options,parent) {
    const label=node('label',({metric:'지표',mode:'계산',range:'조회 기간',entity:'기업',compare:'비교'})[key]+' '), sel=node('select');
    sel.dataset.stateKey=key;sel.dataset.panel=id;
    for(const [value,text,disabled] of options) {const o=node('option',text);o.value=value;o.disabled=Boolean(disabled);sel.append(o);}
    sel.value=states.get(id)[key];label.append(sel);parent.append(label);
    sel.addEventListener('change',()=>{states.get(id)[key]=sel.value;syncControls(id);render(id,true);});return sel;
  }
  function syncControls(id) {
    const p=panels[id], state=states.get(id), series=p.series.filter(s=>(state.metric==='all'||s.metric===state.metric)&&(state.entity==='all'||s.entity===state.entity));
    const allowed=mode=>series.length>0&&series.every(s=>derivable(s,mode))&&series.some(s=>transform(s,mode).some(p=>finite(p.value)));
    if(!allowed(state.mode))state.mode='raw';
    if(!['raw','index'].includes(state.mode))state.compare='independent';
    document.querySelectorAll('select[data-panel]').forEach(sel=>{
      if(sel.dataset.panel!==id)return;const key=sel.dataset.stateKey;sel.value=state[key];
      if(key==='mode')for(const o of sel.options){o.disabled=!allowed(o.value);o.textContent=labels[o.value]+(o.disabled?' · 비교 가능한 관측/명시적 분기 기준 부족':'');}
      sel.disabled=!series.length||['missing','blocked'].includes(p.status);
      if(key==='compare') sel.disabled=sel.disabled||series.length<2||!['raw','index'].includes(state.mode);
      sel.title=sel.disabled?reason:'공개 데이터 기준 선택';
    });
  }
  function setup(id,p) {
    const plot=$(id);if(!plot)return;
    const state={metric:'all',mode:'raw',range:'all',entity:'all',compare:'independent'};states.set(id,state);
    const note=node('p',summary(p),'live-reading');plot.before(note);
    const controls=node('div',undefined,'controls live-controls');plot.before(controls);
    selectControl(id,'metric',[['all','모든 지표'],...Array.from(new Set(p.series.map(s=>s.metric))).map(x=>[x,x])],controls);
    selectControl(id,'mode',Object.entries(labels),controls);
    selectControl(id,'range',[['all','전체'],['12','최근 12개월'],['36','최근 36개월'],['60','최근 60개월']],controls);
    selectControl(id,'entity',[['all','모든 기업'],...Array.from(new Set(p.series.map(s=>s.entity))).map(x=>[x,x])],controls);
    selectControl(id,'compare',[['independent','각 실제 관측일'],['aligned','공통 실제 관측일만']],controls);
    controls.append(node('small','YoY·QoQ: 양수 기준값과 연속 회계분기 정의 필요. TTM: 명시적 독립 분기 flow만 합산. 지수: 양수 시작값 필요. 날짜 정렬 비교는 합산하지 않습니다.'));
    const exp=node('button','확대 ↗','btn');exp.dataset.expand=id;controls.append(exp);
    const evidence=node('details',undefined,'evidence');evidence.append(node('summary','전체 관측과 출처 보기'));const target=node('div');evidence.append(target);plot.after(evidence);
    evidence.addEventListener('toggle',()=>{if(evidence.open)target.replaceChildren(tableFor(view(p,state,D.asof),p));});
    plot._evidence=target;
    syncControls(id);
  }
  // Enhancement placement is explicit; never silently move unrelated material into another chapter.
  for(const e of D.enhancements||[]) {
    const inferred=e.id==='cloud-rpo'?'big4':/capex|cash/.test(e.id)?'capex':/gpu|rental/.test(e.id)?'recovery':/hardware|memory/.test(e.id)?'hardware':'verdict';
    const chapter=$(e.chapter||inferred);if(!chapter) {errors.push('Unknown enhancement chapter: '+e.id);continue;}
    const article=node('article',undefined,'panel enhancement');article.append(node('h3',e.title));const plot=node('div',undefined,'plot');plot.id=e.id;plot.setAttribute('role','img');plot.setAttribute('aria-label',e.title+' · '+e.status);article.append(plot);chapter.append(article);panels[e.id]=e;
  }
  for(const [id,p] of Object.entries(panels))setup(id,p);
  for(const el of document.querySelectorAll('[data-reading-for]')) {const p=panels[el.dataset.readingFor];if(p) { // Preserve nested visual structure and inventory IDs.
    const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);const texts=[];while(walker.nextNode())texts.push(walker.currentNode);
    const text=el.classList.contains('reading')?summary(p):`${D.asof} 기준 · ${p.status} · ${p.series.length}개 계열 · 관측·출처·미확인 범위는 아래에서 확인`;
    texts.forEach((n,i)=>{n.textContent=i===0?text:'';});
  }}
  // Existing controls retain IDs and position. Known semantics are wired; everything else explains its disabled state.
  for(const sel of document.querySelectorAll('select[data-targets]')) {
    const ids=sel.dataset.targets.split(' ').filter(id=>panels[id]);const id=ids.length===1?ids[0]:null;
    const key=/-(range|period)$/.test(sel.id)||sel.id.startsWith('hist-range-')?'range':/^(hist|fwd|cash)-mode-/.test(sel.id)?'metric':null;
    if(id&&key) {
      const twin=Array.from(document.querySelectorAll('select[data-panel]')).find(x=>x.dataset.panel===id&&x.dataset.stateKey===key);
      if(twin){sel.replaceChildren(...Array.from(twin.options).map(o=>o.cloneNode(true)));sel.disabled=twin.disabled;sel.dataset.panel=id;sel.dataset.stateKey=key;sel.value=states.get(id)[key];sel.addEventListener('change',()=>{states.get(id)[key]=sel.value;syncControls(id);render(id,true);});}
    } else sel.disabled=true;
    const why=node('small',sel.disabled?'사용 불가: '+reason:'현재 공개 자료에서 선택합니다.','control-reason');sel.after(why);sel.title=why.textContent;
  }
  for(const input of document.querySelectorAll('input:disabled')) input.after(node('small','시나리오 비활성: 공개 기저·공식·가정 단위의 어댑터가 필요합니다.','control-reason'));
  async function draw(plot,p,series) {
    if(root.Plotly)plot.querySelectorAll('.unit-plot').forEach(p=>root.Plotly.purge(p));
    plot.replaceChildren();
    if(['blocked','missing'].includes(p.status)||!series.some(s=>s.points.some(q=>finite(q.value)))) {plot.append(node('p',(p.reason||'선택 조건에 비교 가능한 관측값이 없습니다.')+' '+missing,'missing-state'));return;}
    if(!root.Plotly) {plot.append(node('p','로컬 vendor/plotly-3.3.1.min.js가 없습니다. 아래 근거 표와 JSON에서 자료를 확인하세요.','missing-state'));return;}
    const bridge=p.visualization==='cash_bridge'&&cashBridge(series);
    if(bridge) {
      plot.append(node('p',`${bridge.period} · ${bridge.date} · 같은 분기·출처의 최신 완전 관측. 순투자 차감 = OCF − 현금 PP&E 취득 + 매각·인센티브. 회사 발표 TTM FCF 또는 AI 프로젝트 회수액이 아닙니다.`,'note'));
      const facet=node('div',undefined,'unit-plot');plot.append(facet);
      await root.Plotly.newPlot(facet,[{type:'waterfall',x:bridge.labels,y:bridge.values,measure:bridge.measures,
        text:bridge.values.map(v=>v.toFixed(3)),textposition:'outside',connector:{line:{color:'#64748b'}},
        increasing:{marker:{color:'#6ee7b7'}},decreasing:{marker:{color:'#f59e83'}},totals:{marker:{color:'#5bb8ff'}},
        hovertemplate:'%{x}<br>%{y:.3f} USD B<extra>AMZN · '+esc(bridge.period)+'</extra>'}],
        {autosize:true,paper_bgcolor:'#111929',plot_bgcolor:'#111929',font:{color:'#b8cde3'},margin:{l:70,r:25,t:30,b:95},yaxis:{title:{text:'USD B'},gridcolor:'#29394d'}},
        {responsive:true,displaylogo:false});
      return;
    }
    const units=Array.from(new Set(series.map(s=>s.points[0]?.unit||s.unit)));
    plot.classList.toggle('multi-unit',units.length>1);
    for(const unit of units) {
      const facet=node('div',undefined,'unit-plot');plot.append(facet);
      const traces=series.filter(s=>(s.points[0]?.unit||s.unit)===unit).map(s=>{const points=chartPoints(s);return {type:'scatter',mode:s.frequency==='event'||s.points.some(q=>!exact(q))?'markers':'lines+markers',marker:{size:8,symbol:points.map(q=>exact(q)?'circle':'triangle-up')},name:esc(s.name+' · '+s.kind),x:points.map(p=>p.date),y:points.map(p=>p.value),connectgaps:false,customdata:points.map(q=>[esc(q.unit||s.unit),esc((q.evidence||[q]).map(e=>evidenceText(e,s,p)).join('\n')),q]),hovertemplate:'%{x}<br>%{y} %{customdata[0]}<br>%{customdata[1]}<extra>%{fullData.name}</extra>'};});
      const dateRange=singleDateRange(traces),singleValue=new Set(traces.flatMap(t=>t.y).filter(finite)).size===1;
      await root.Plotly.newPlot(facet,traces,{autosize:true,paper_bgcolor:'#111929',plot_bgcolor:'#111929',font:{color:'#b8cde3'},margin:{l:70,r:20,t:30,b:85},xaxis:{type:'date',range:dateRange,tickformat:dateRange?'%Y-%m-%d':undefined,title:{text:'관측일 / 회계 종료일'}},yaxis:{title:{text:esc(unit)},gridcolor:'#29394d',rangemode:singleValue?'tozero':'normal'},legend:{orientation:'h'},hovermode:'closest',colorway:['#6ee7b7','#5bb8ff','#f5c061','#b09bed']},{responsive:true,displaylogo:false,toImageButtonOptions:{format:'png',filename:'ai-cycle-'+D.asof}});
      facet.on('plotly_click',event=>{const point=event.points[0];const selected=series.find(s=>esc(s.name+' · '+s.kind)===point.data.name);if(selected)openEvidence(p,{...selected,points:[point.customdata[2]]});});
    }
  }
  async function render(id,force=false) {
    if(pending.has(id)) {await pending.get(id);return render(id,force);}
    const task=renderNow(id,force);pending.set(id,task);try{return await task;}finally{pending.delete(id);}
  }
  async function renderNow(id,force=false) {
    const plot=$(id);if(!plot||!states.has(id)||(!force&&(!plot.getClientRects().length||plot.closest('details:not([open])'))))return;
    try {const series=view(panels[id],states.get(id),D.asof);await draw(plot,panels[id],series);rendered.add(id);if(plot._evidence?.parentElement.open)plot._evidence.replaceChildren(tableFor(series,panels[id]));}
    catch(e){errors.push(id+': '+e.message);plot.replaceChildren(node('p','표시 실패: '+e.message));}
  }
  const modal=node('dialog',undefined,'live-modal');modal.id='live-modal';const close=node('button','닫기','btn'),modalBody=node('div');modal.append(close,modalBody);document.body.append(modal);close.addEventListener('click',()=>modal.close());
  function openEvidence(p,s){modalBody.replaceChildren(node('h3',p.title),tableFor([s],p));modal.showModal();}
  document.addEventListener('click',async e=>{
    const b=e.target.closest('[data-expand]');if(!b||!panels[b.dataset.expand])return;
    const id=b.dataset.expand,p=panels[id],series=view(p,states.get(id),D.asof),chart=node('div',undefined,'plot expanded-plot');
    modalBody.replaceChildren(node('h3',p.title),node('p',summary(p)),chart,tableFor(series,p));if(!modal.open)modal.showModal();await draw(chart,p,series);
  });
  modal.addEventListener('close',()=>{if(root.Plotly)modal.querySelectorAll('.unit-plot').forEach(p=>root.Plotly.purge(p));modalBody.replaceChildren();});
  const coverage=node('details',undefined,'coverage-drawer');coverage.id='coverage-drawer';coverage.append(node('summary',`연결 현황 · ${D.coverage.total}개 영역 중 ${D.coverage.available}개 완전 연결 · ${D.coverage.partial}개 부분 연결 · ${D.coverage.missing+D.coverage.blocked}개 결측 (공개 대체자료 없음 ${D.coverage.blocked} · 자료/검증 부족 ${D.coverage.missing})`));
  if(D.source_policy?.description)coverage.append(node('p',D.source_policy.description,'source-policy'));
  coverage.append(node('p',`기준일 ${D.asof} · 생성 ${D.generated_at} · 릴리스 ${release.release_sha256}`));
  for(const [id,p] of Object.entries(panels)){const row=node('p');const a=node('a',`${p.title} · ${statusLabel(p.status)}`);a.href='#'+id;a.onclick=()=>{let parent=$(id)?.parentElement;while(parent){if(parent.tagName==='DETAILS')parent.open=true;parent=parent.parentElement;}};row.append(a,' · '+(p.reason||summary(p)));coverage.append(row);}
  for(const issue of D.issues||[])coverage.append(node('p',typeof issue==='string'?issue:JSON.stringify(issue)));
  document.querySelector('.hero')?.after(coverage);
  const coverageLink=document.querySelector('a[href="#coverage-drawer"]:not(.brand)');
  if(coverageLink&&!coverageLink.querySelector('img'))coverageLink.textContent=`출처·연결 현황 · ${D.coverage.partial}/${D.coverage.total} 부분 연결`;
  // Preserve financial KPI meanings; only exact, source-bound basket calculations qualify.
  const heroLabels=['반도체 지수 변화','하드웨어 매출 성장 기업 비중','대형 클라우드 CAPEX 증가율','현금 회수 시점 근거'];
  document.querySelectorAll('.metric').forEach((m,i)=>{const b=m.querySelector('b');if(b)b.textContent='미확인';const small=m.querySelector('small');if(small)small.textContent=heroLabels[i]||'공개 금융 지표';const span=m.querySelector('span');if(span)span.textContent=D.asof+' · 고정 구성·기간·정의가 확인된 지표 매핑 필요';});
  const heroMetrics=document.querySelectorAll('.metric');
  const hardware=['NVDA','AVGO','DELL','AMD','MU','ANET','HPE','TSM'];
  const growth=hardware.map(entity=>{
    const s=D.panels['hist-'+entity]?.series.find(s=>s.metric==='revenue'&&derivable(s,'yoy'));
    const last=s&&transform(s,'yoy').at(-1);return last&&finite(last.value)?{entity,...last}:null;
  }).filter(Boolean);
  if(growth.length&&heroMetrics[1]){
    heroMetrics[1].querySelector('b').textContent=`${growth.filter(p=>p.value>0).length} / ${growth.length} 증가`;
    heroMetrics[1].querySelector('span').textContent=`고정 HW 8사 중 ${growth.length}사만 비교 가능 · ${8-growth.length}사 미확인. 기업별 최신 회계분기 기준이며 같은 분기 합산 아님.`;
  }
  const capexGrowth=D.panels['capex-history']?.derived?.find(s=>s.entity==='BIG4'&&s.metric==='capex_yoy');
  const capexLast=capexGrowth?.points.at(-1);
  if(heroMetrics[2]&&capexLast&&finite(capexLast.value)){
    heroMetrics[2].querySelector('b').textContent=`${capexLast.value>=0?'+':''}${capexLast.value.toFixed(1)}%`;
    heroMetrics[2].querySelector('span').textContent=`${capexLast.period} 전년 동기 대비 · 고정 4사 동일 달력분기 현금 PP&E 합계. 리스 포함 투자·전망과 다름.`;
  }
  if(heroMetrics[3]){heroMetrics[3].querySelector('b').textContent='매출 ≠ 회수';heroMetrics[3].querySelector('span').textContent='전사 FCF와 프로젝트 투자금 회수는 다른 개념. 미래 회수 시점은 검증되지 않았습니다.';}
  const arrLabels={'arr-kpi-total':'OpenAI·Anthropic 합산 런레이트','arr-kpi-anthropic':'Anthropic 런레이트','arr-kpi-openai':'OpenAI 런레이트','arr-kpi-forecast':'공개 전망 근거'};
  for(const [id,label] of Object.entries(arrLabels)){const n=$(id);if(!n)continue;n.textContent='미확인';const box=n.closest('.arr-kpi');const title=box?.querySelector('.arr-kpi-label');if(title)title.textContent=label;const note=box?.querySelector('.arr-kpi-note');if(note)note.textContent='기간·정의·공개 출처가 일치하는 지표 매핑 필요';}
  for(const entity of ['OPENAI','ANTHROPIC']) {
    const series=D.panels['arr-main']?.series.find(s=>s.entity===entity&&s.metric==='arr');
    const p=series?.points.filter(q=>finite(q.value)).at(-1),n=$('arr-kpi-'+entity.toLowerCase());
    if(p&&n){n.textContent=`$${p.value}B${exact(p)?'':' 초과'}`;const note=n.closest('.arr-kpi')?.querySelector('.arr-kpi-note');if(note)note.textContent=`${p.observed_period||p.period||p.date} · ${p.date_basis||'공개일 기준'} · 연환산 매출, 분기 매출과 다름`;}
  }
  function download(data,name,type) {const url=URL.createObjectURL(new Blob([data],{type}));const a=node('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  $('download')?.addEventListener('click',()=>download(JSON.stringify(D,null,2),'ai-cycle-'+D.asof+'.json','application/json'));
  $('expand-all')?.addEventListener('click',()=>{const ds=Array.from(document.querySelectorAll('details.fold'));const open=ds.some(d=>!d.open);ds.forEach(d=>d.open=open);$('expand-all').textContent=open?'상세 모두 접기':'상세 모두 펼치기';});
  $('credit-reset')?.addEventListener('click',()=>{for(const id of states.keys())if(id.startsWith('credit-')){states.set(id,{metric:'all',mode:'raw',range:'all',entity:'all',compare:'independent'});syncControls(id);render(id,true);}});
  $('modal-close')?.addEventListener('click',()=>$('modal')?.close());
  const formula=node('p','계산 정의: YoY = (현재 / 전년 동기 − 1) × 100, QoQ = (현재 / 직전 분기 − 1) × 100, TTM = 최근 네 개 독립 분기 합계. FCF = OCF − CAPEX는 현금 기준과 리스 처리 등 정의가 일치할 때만 비교합니다. 시나리오는 관측 사실이 아닙니다.','note');$('capex')?.append(formula);
  const print=node('button','전체 차트 인쇄','btn');document.querySelector('.top-actions')?.append(print);
  print.addEventListener('click',async()=>{for(const d of document.querySelectorAll('details.fold'))d.open=true;for(const id of states.keys())await render(id,true);root.print();});
  if('IntersectionObserver' in root){const observer=new IntersectionObserver(entries=>entries.forEach(e=>{if(e.isIntersecting&&!rendered.has(e.target.id))render(e.target.id);}),{rootMargin:'200px'});for(const id of states.keys())observer.observe($(id));}
  else for(const id of states.keys())render(id);
  document.querySelectorAll('details.fold').forEach(d=>d.addEventListener('toggle',()=>{if(d.open)d.querySelectorAll('.plot').forEach(p=>render(p.id));}));
  root.addEventListener('resize',()=>{document.querySelectorAll('.unit-plot').forEach(p=>{if(p.getClientRects().length&&root.Plotly)root.Plotly.Plots.resize(p);});});
  root.addEventListener('scroll',()=>{const den=document.documentElement.scrollHeight-root.innerHeight;if($('progress'))$('progress').style.width=(den?root.scrollY/den*100:0)+'%';},{passive:true});
  root.__aiCycle={payload:D,release,states,errors,render,renderAll:async()=>{for(const d of document.querySelectorAll('details.fold'))d.open=true;for(const id of states.keys())await render(id,true);return{panels:states.size,errors};}};
})(typeof window==='undefined'?globalThis:window);
