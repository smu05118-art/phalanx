// Panoptes — 국제분쟁 지도 (독자 시스템, MapLibre GL)
const TYPES = {
  armed_clash:  {label:'무력 충돌', color:'#ff6b6b'},
  airstrike:    {label:'공습',      color:'#ff8a3d'},
  shelling:     {label:'포격',      color:'#ffab3d'},
  terrorism:    {label:'테러',      color:'#c45cff'},
  naval:        {label:'해상',      color:'#26c6da'},
  cyber:        {label:'사이버',    color:'#59d0a8'},
  protest:      {label:'시위·소요', color:'#ffd23d'},
  border_tension:{label:'국경 긴장',color:'#4ea1ff'},
  political:    {label:'정치·외교', color:'#8a93a3'},
};
const SEV = {1:'#4ea1ff',2:'#59d0a8',3:'#ffd23d',4:'#ff8a3d',5:'#ff4d5e'};
const ST = { typeOff:{}, sevOff:{}, q:'', timePct:0, sel:null };
let MAP=null, EVENTS=[], DATES=[];

function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function daysAgo(d){const t=Date.parse(d); if(isNaN(t))return null; return Math.round((Date.now()-t)/864e5);}

async function boot(){
  const [world, events] = await Promise.all([
    fetch('data/world.min.geojson').then(r=>r.json()),
    fetch('data/events.json').then(r=>r.ok?r.json():[]).catch(()=>[])
  ]);
  EVENTS = (Array.isArray(events)?events:(events.events||[])).filter(e=>e.lat!=null&&e.lon!=null);
  EVENTS.forEach((e,i)=>{e._id=e.id||('ev'+i); e._sev=Math.max(1,Math.min(5,+e.severity||1));});
  DATES = EVENTS.map(e=>Date.parse(e.date)).filter(x=>!isNaN(x)).sort((a,b)=>a-b);

  const CARTO=['a','b','c','d'].map(s=>`https://${s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png`);
  MAP = new maplibregl.Map({
    container:'map',
    style:{version:8,
      sources:{
        carto:{type:'raster',tiles:CARTO,tileSize:256,attribution:'© OpenStreetMap · © CARTO'},
      },
      layers:[
        {id:'bg',type:'background',paint:{'background-color':'#080b12'}},
        {id:'carto',type:'raster',source:'carto',paint:{'raster-opacity':0.92,'raster-saturation':-0.25,'raster-contrast':0.05}},
      ]},
    center:[27,20], zoom:2.1, minZoom:1.3, maxZoom:12, renderWorldCopies:true, attributionControl:false
  });
  MAP.addControl(new maplibregl.NavigationControl({showCompass:false}),'bottom-right');
  MAP.addControl(new maplibregl.AttributionControl({compact:true}),'bottom-left');

  MAP.on('load', ()=>{
    // 국가 상호작용용(투명 fill + 은은한 accent 경계 + hover 하이라이트)
    MAP.addSource('world',{type:'geojson',data:world,promoteId:'name'});
    MAP.addLayer({id:'country-hover',type:'fill',source:'world',
      paint:{'fill-color':'#2bc0d4','fill-opacity':['case',['boolean',['feature-state','hover'],false],0.10,0]}});
    MAP.addLayer({id:'country-line',type:'line',source:'world',paint:{'line-color':'#2b3a4d','line-width':0.4,'line-opacity':0.5}});
    let hov=null;
    MAP.on('mousemove','country-hover',e=>{const f=e.features[0];if(hov!==null)MAP.setFeatureState({source:'world',id:hov},{hover:false});hov=f.id;MAP.setFeatureState({source:'world',id:hov},{hover:true});});
    MAP.on('mouseleave','country-hover',()=>{if(hov!==null)MAP.setFeatureState({source:'world',id:hov},{hover:false});hov=null;});

    MAP.addSource('events',{type:'geojson',data:geo()});
    // 펄스(고심각도) → glow → dot → 코어 하이라이트
    MAP.addLayer({id:'ev-pulse',type:'circle',source:'events',filter:['>=',['get','sev'],4],paint:{
      'circle-radius':['*',['get','sev'],3],'circle-color':['get','color'],'circle-opacity':0.4,'circle-blur':0.6}});
    MAP.addLayer({id:'ev-glow',type:'circle',source:'events',paint:{
      'circle-radius':['+',['*',['get','sev'],3],5],'circle-color':['get','color'],'circle-blur':1,'circle-opacity':0.28}});
    MAP.addLayer({id:'ev-dot',type:'circle',source:'events',paint:{
      'circle-radius':['+',['*',['get','sev'],1.7],3],'circle-color':['get','color'],
      'circle-stroke-color':'#fff','circle-stroke-width':1,'circle-stroke-opacity':0.5,'circle-opacity':0.95}});
    MAP.addLayer({id:'ev-core',type:'circle',source:'events',paint:{
      'circle-radius':1.6,'circle-color':'#fff','circle-opacity':0.9}});
    MAP.on('click','ev-dot',e=>{const id=e.features[0].properties.id; select(id,true);});
    MAP.on('mouseenter','ev-dot',()=>MAP.getCanvas().style.cursor='pointer');
    MAP.on('mouseleave','ev-dot',()=>MAP.getCanvas().style.cursor='');
    buildFilters(); buildRegions(); refresh(); pulse();
  });

  document.getElementById('search').oninput=e=>{ST.q=e.target.value.toLowerCase().trim();refresh();};
  const sl=document.getElementById('timeSlider');
  sl.oninput=e=>{ST.timePct=+e.target.value;refresh();};
  document.getElementById('stEvents').textContent=EVENTS.length;
  const latest=EVENTS.map(e=>e.date).filter(Boolean).sort().pop();
  document.getElementById('stUpdated').textContent=latest||'—';
  if(DATES.length){document.getElementById('tlMin').textContent=new Date(DATES[0]).toISOString().slice(0,10);}
}

let _pt=0;
function pulse(){
  _pt=(_pt+1)%90; const p=_pt/90;
  if(MAP&&MAP.getLayer('ev-pulse')){
    MAP.setPaintProperty('ev-pulse','circle-radius',['*',['get','sev'],3+p*6]);
    MAP.setPaintProperty('ev-pulse','circle-opacity',0.45*(1-p));
  }
  requestAnimationFrame(pulse);
}
const REGIONS=[
  ['전체',[27,20],1.9],['우크라이나',[33,48.5],4.3],['중동·가자',[37,31],4.2],
  ['수단·사헬',[20,14],3.4],['홍해',[42,15],4.2],['동아시아',[122,26],3.6],['미얀마',[96,21],4.3]
];
function buildRegions(){
  const el=document.getElementById('regionJump'); if(!el)return;
  el.innerHTML=REGIONS.map((r,i)=>`<span class="rchip" data-i="${i}">${r[0]}</span>`).join('');
  el.querySelectorAll('.rchip').forEach(c=>c.onclick=()=>{const r=REGIONS[+c.dataset.i];MAP.flyTo({center:r[1],zoom:r[2],speed:0.9});});
}
function geo(){
  return {type:'FeatureCollection',features:visible().map(e=>({
    type:'Feature',geometry:{type:'Point',coordinates:[+e.lon,+e.lat]},
    properties:{id:e._id,sev:e._sev,color:(TYPES[e.type]||{}).color||'#8a93a3'}}))};
}
function passType(e){return !ST.typeOff[e.type];}
function passSev(e){return !ST.sevOff[e._sev];}
function passTime(e){ if(!ST.timePct||!DATES.length)return true; const cut=DATES[0]+(DATES[DATES.length-1]-DATES[0])*(ST.timePct/100); const t=Date.parse(e.date); return isNaN(t)||t>=cut; }
function passQ(e){ if(!ST.q)return true; return ((e.title||'')+(e.country||'')+(e.region||'')+(e.summary||'')).toLowerCase().includes(ST.q); }
function visible(){return EVENTS.filter(e=>passType(e)&&passSev(e)&&passTime(e)&&passQ(e));}

function refresh(){
  if(MAP&&MAP.getSource('events'))MAP.getSource('events').setData(geo());
  const vis=visible();
  document.getElementById('stActive').textContent=vis.length;
  if(ST.timePct&&DATES.length){const cut=DATES[0]+(DATES[DATES.length-1]-DATES[0])*(ST.timePct/100);document.getElementById('tlCur').textContent='이후: '+new Date(cut).toISOString().slice(0,10);}
  else document.getElementById('tlCur').textContent='전체 기간';
  const list=document.getElementById('evlist');
  list.innerHTML=vis.slice().sort((a,b)=>(b.date||'').localeCompare(a.date||'')).slice(0,60).map(e=>{
    const c=(TYPES[e.type]||{}).color||'#8a93a3';const da=daysAgo(e.date);
    return `<div class="evcard" style="border-left-color:${c}" data-id="${e._id}">
      <div class="et">${esc(e.title)}</div>
      <div class="em"><span>${esc(e.country||e.region||'')}</span><span>${(TYPES[e.type]||{}).label||e.type}</span><span>S${e._sev}</span>${da!=null?`<span>${da==0?'오늘':da+'일 전'}</span>`:''}</div>
    </div>`;}).join('')||'<p class="hint">표시할 이벤트가 없습니다.</p>';
  list.querySelectorAll('.evcard').forEach(el=>el.onclick=()=>select(el.dataset.id,true));
}

function buildFilters(){
  const tc={};EVENTS.forEach(e=>tc[e.type]=(tc[e.type]||0)+1);
  document.getElementById('typeFilters').innerHTML=Object.entries(TYPES).filter(([k])=>tc[k]).map(([k,t])=>
    `<div class="frow" data-t="${k}"><span class="dot" style="background:${t.color}"></span>${t.label}<span class="n">${tc[k]||0}</span></div>`).join('');
  const sc={};EVENTS.forEach(e=>sc[e._sev]=(sc[e._sev]||0)+1);
  document.getElementById('sevFilters').innerHTML=[1,2,3,4,5].map(s=>
    `<div class="frow" data-s="${s}"><span class="dot" style="background:${SEV[s]}"></span>심각도 ${s}<span class="n">${sc[s]||0}</span></div>`).join('');
  document.querySelectorAll('[data-t]').forEach(el=>el.onclick=()=>{ST.typeOff[el.dataset.t]=!ST.typeOff[el.dataset.t];el.classList.toggle('off');refresh();});
  document.querySelectorAll('[data-s]').forEach(el=>el.onclick=()=>{const s=+el.dataset.s;ST.sevOff[s]=!ST.sevOff[s];el.classList.toggle('off');refresh();});
}

function select(id,fly){
  const e=EVENTS.find(x=>x._id===id);if(!e)return;ST.sel=id;
  const t=TYPES[e.type]||{};const da=daysAgo(e.date);
  document.getElementById('detail').innerHTML=`
    <div class="dt">${esc(e.title)}</div>
    <span class="badge" style="background:${t.color}22;color:${t.color}">${t.label||e.type}</span>
    <span class="badge" style="background:${SEV[e._sev]}22;color:${SEV[e._sev]}">심각도 ${e._sev}</span>
    <div class="meta"><b>${esc(e.country||'')}</b>${e.region?' · '+esc(e.region):''}<br>${esc(e.date||'')}${da!=null?` (${da==0?'오늘':da+'일 전'})`:''}<br>좌표 ${(+e.lat).toFixed(2)}, ${(+e.lon).toFixed(2)}</div>
    ${e.summary?`<p class="sum">${esc(e.summary)}</p>`:''}
    ${(e.actors&&e.actors.length)?`<div class="actors">${e.actors.map(a=>`<span>${esc(a)}</span>`).join('')}</div>`:''}
    ${e.source_url?`<a class="src" href="${esc(e.source_url)}" target="_blank" rel="noopener">출처: ${esc(e.source_name||'link')} ↗</a>`:''}`;
  if(fly&&MAP){MAP.flyTo({center:[+e.lon,+e.lat],zoom:Math.max(MAP.getZoom(),4),speed:0.8});
    new maplibregl.Popup({closeButton:false,offset:12}).setLngLat([+e.lon,+e.lat]).setHTML(`<b>${esc(e.title)}</b>`).addTo(MAP);}
}

// ===== 탭 전환 =====
let _liqLoaded=false, _mapInit=false;
function switchTab(tab){
  document.querySelectorAll('.ptab').forEach(t=>t.classList.toggle('on',t.dataset.tab===tab));
  const isMap=tab==='map';
  document.getElementById('mapview').hidden=!isMap;
  document.getElementById('liqview').hidden=(tab!=='liq');
  document.getElementById('techview').hidden=(tab!=='tech');
  document.getElementById('shipview').hidden=(tab!=='ship');
  document.getElementById('headStat').style.display=isMap?'':'none';
  if(isMap && MAP){setTimeout(()=>MAP.resize(),50);}
  if(tab==='liq' && !_liqLoaded){ _liqLoaded=true; loadLiq(); }
  if(tab==='tech'){ loadTech2(); }
  if(tab==='ship'){ loadShip(); }
}
async function loadShip(){
  const box=document.getElementById('shipview');
  if(box.dataset.loaded) return; 
  box.innerHTML='<p class="hint" style="padding:20px">해운 데이터 로딩…</p>';
  try{ const d=await fetch('data/shipping.json').then(r=>r.json());
    box.innerHTML=''; renderShipping(box, d); box.dataset.loaded='1';
  }catch(e){ box.innerHTML='<p class="hint" style="padding:20px">해운 데이터 준비 중…</p>'; }
}
async function loadTech2(){
  const box=document.getElementById('techview');
  let d; try{ d=await fetch('data/tech_indicators.json').then(r=>r.json()); }
  catch(e){ box.innerHTML='<p class="hint" style="padding:20px">기술적 지표 수집 중…</p>'; return; }
  const IN={'^KS11':'KOSPI','^KQ11':'KOSDAQ','^GSPC':'S&P 500','^IXIC':'NASDAQ','kospi':'KOSPI','kosdaq':'KOSDAQ','sp500':'S&P 500','nasdaq':'NASDAQ'};
  const ORD=['kospi','nasdaq','kosdaq','sp500'];
  const keys=ORD.filter(k=>d[k]).concat(Object.keys(d).filter(k=>!k.startsWith('_')&&!ORD.includes(k)));
  const cards=keys.map(k=>[k,d[k]]).map(([k,v])=>{
    const nm=IN[k]||v.name||k; const disp=v.disparity||{};
    const rows=Object.entries(disp).map(([ma,o])=>{
      const now=o.now, pct=o.pct;
      const col=pct==null?'#8a93a3':pct>=90?'#ff4d5e':pct>=75?'#ff8a3d':pct<=10?'#4ea1ff':pct<=25?'#59d0a8':'#8a93a3';
      const w=Math.max(2,Math.min(100,pct||0));
      return `<div style="margin:7px 0"><div style="display:flex;justify-content:space-between;font-size:11.5px"><span style="color:var(--dim)">${ma.toUpperCase()} 이격도</span><b style="font-family:var(--mono)">${now!=null?now.toFixed(1):'—'} <span style="color:${col}">(${pct!=null?pct.toFixed(0):'—'}%ile)</span></b></div>
      <div style="height:5px;background:var(--panel2);border-radius:3px;margin-top:3px"><div style="width:${w}%;height:100%;border-radius:3px;background:${col}"></div></div></div>`;}).join('');
    const mddo=v.mdd; const mdd=(mddo&&typeof mddo==='object')?mddo.from_peak_pct:mddo;
    const VDK={overheat:'과열',depressed:'침체',oversold:'침체',neutral:'중립'};
    const vd=VDK[String(v.verdict||'').toLowerCase()]||v.verdict||'';
    return `<div style="background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:16px 18px">
      <div style="display:flex;justify-content:space-between;align-items:baseline"><b style="font-size:14px">${nm}</b>
      <span style="font-size:11px;font-weight:700;color:${/과열/.test(vd)?'#ff4d5e':/침체/.test(vd)?'#4ea1ff':'var(--dim)'}">${vd}</span></div>
      ${rows}
      ${mdd!=null?`<div style="font-size:11px;color:var(--dim);margin-top:8px">전고점 대비 <b style="font-family:var(--mono);color:${mdd<-10?'#ff8a3d':'var(--ink)'}">${Number(mdd).toFixed(1)}%</b>${(mddo&&mddo.peak_date)?` <span style="opacity:.7">(고점 ${mddo.peak_date})</span>`:''} · 10년 최악 ${mddo&&mddo.worst_10y_pct!=null?mddo.worst_10y_pct.toFixed(0)+'%':'—'}</div>`:''}
    </div>`;}).join('');
  box.innerHTML=`<p style="font-size:18px;font-weight:800;margin:0 0 4px">📐 기술적 — 이격도·MDD</p>
  <p class="hint" style="margin:0 0 16px">이격도 = 종가/이동평균×100 · %ile = 10년 백분위(90+ 과열 · 10- 침체) · 일간 자동갱신 ${String(d._updated||'').slice(0,10)}</p>
  <div id="techCharts" style="max-width:1180px;margin:0 0 18px"></div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:14px;max-width:1180px">${cards}</div>`;
  if(window.renderTechCharts){ try{ renderTechCharts(document.getElementById('techCharts'), d); }catch(e){ console.warn('techCharts', e); } }
  try{ const dv=await fetch('data/deriv_kr.json').then(r=>r.ok?r.json():null);
    if(dv && window.renderDeriv){ const el=document.createElement('div'); el.style.marginTop='20px'; box.appendChild(el); renderDeriv(el, dv); } }catch(e){ console.warn('deriv', e); }
}
document.querySelectorAll('.ptab').forEach(t=>t.onclick=()=>switchTab(t.dataset.tab));

// ===== 💧 유동성 =====
const LIQC={green:'#59d0a8',yellow:'#ffd23d',orange:'#ff8a3d',red:'#ff4d5e',gray:'#8a93a3'};
const LIQLABEL={green:'초록',yellow:'노랑',orange:'주황',red:'빨강',gray:'—'};
function validTgaTarget(raw,asOf){
  return window.PanoptesTgaTarget
    ? window.PanoptesTgaTarget.validateConfig(raw,asOf)
    : null;
}
async function loadTgaTarget(){
  try{
    return await fetch('data/tga_target.json',{cache:'no-store'}).then(r=>r.ok?r.json():null);
  }catch(e){ console.warn('tgaTarget',e); return null; }
}
function attachTgaTarget(d,raw){
  if(!d) return d;
  const model=validTgaTarget(raw,d.updated);
  if(!model) return d;
  d.tga_targets=model; // 구형 fallback 렌더러도 같은 검증 모델 사용
  if(d.sections&&d.sections.funding){
    d.sections.funding.references=d.sections.funding.references||{};
    d.sections.funding.references.treasury_cash_balance_assumptions=model;
  }
  return d;
}
async function loadLiq(){
  const box=document.getElementById('liqview');
  box.innerHTML='<p class="hint" style="padding:20px">유동성 데이터 로딩…</p>';
  const tgaTarget=await loadTgaTarget();
  try{ const d2=await fetch('data/liquidity2.json').then(r=>r.ok?r.json():null);
    if(d2 && window.renderLiq2){ attachTgaTarget(d2,tgaTarget); renderLiq2(box, d2); liqHistStrip(box, d2); return; } }catch(e){ console.warn('liq2', e); }
  let d; try{ d=await fetch('data/liquidity.json').then(r=>r.json()); }
  catch(e){ box.innerHTML='<p class="hint" style="padding:20px">유동성 데이터 준비 중입니다.</p>'; return; }
  attachTgaTarget(d,tgaTarget);
  renderLiq(d);
}
function liqHistStrip(box, d){
  const H=d.hist||{}; const days=Object.keys(H).sort(); if(days.length<2) return;
  const LC={green:'#59d0a8',yellow:'#ffd23d',orange:'#ff8a3d',red:'#ff4d5e'};
  const keys=['repo','bank','tga','rrp','netliq','hy','curve','vix','dxy4w'];
  const rows=keys.map(k=>`<div style="display:flex;align-items:center;gap:6px"><span style="font-size:9.5px;color:var(--dim);width:44px;text-align:right">${k}</span>${days.map(dd=>`<span title="${dd} ${((H[dd]||{}).lights||{})[k]||''}" style="width:7px;height:7px;border-radius:2px;background:${LC[((H[dd]||{}).lights||{})[k]]||'#2a3140'}"></span>`).join('')}</div>`).join('');
  const ov=`<div style="display:flex;align-items:center;gap:6px;margin-top:3px"><span style="font-size:9.5px;font-weight:800;width:44px;text-align:right">종합</span>${days.map(dd=>`<span title="${dd} ${(H[dd]||{}).overall||''}" style="width:7px;height:9px;border-radius:2px;background:${LC[(H[dd]||{}).overall]||'#2a3140'}"></span>`).join('')}</div>`;
  const el=document.createElement('div');
  el.className='comment'; el.style.marginTop='14px';
  el.innerHTML=`<div style="font-size:12px;font-weight:700;margin-bottom:8px">🚦 신호등 히스토리 <span style="color:var(--dim);font-weight:400;font-size:10px">(${days[0]} ~ ${days[days.length-1]} · 일별 축적 중)</span></div><div style="display:flex;flex-direction:column;gap:3px;overflow-x:auto">${rows}${ov}</div>`;
  box.appendChild(el);
}
function liqSpark(series, opts){
  opts=opts||{}; const keys=Object.keys(series).sort(); const vals=keys.map(k=>series[k]);
  if(vals.length<2) return '<div class="hint">데이터 부족</div>';
  const W=opts.w||560,H=opts.h||120,pad=opts.pad||4;
  const refs=(opts.refs||[]).filter(r=>r&&Number.isFinite(Number(r.v)));
  if(opts.ref!=null&&Number.isFinite(Number(opts.ref))) refs.push({v:Number(opts.ref),c:opts.refColor||'#8a93a3'});
  const domain=vals.concat(refs.filter(r=>r.domain).map(r=>Number(r.v)));
  const mn=Math.min(...domain),mx=Math.max(...domain),rg=(mx-mn)||1;
  const x=i=>pad+(W-2*pad)*i/(vals.length-1), y=v=>pad+(H-2*pad)*(1-(v-mn)/rg);
  const pts=vals.map((v,i)=>`${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const col=opts.color||'#2bc0d4';
  const ref=refs.filter(r=>r.v>=mn&&r.v<=mx).map(r=>{const ry=y(r.v);return `<line x1="${pad}" y1="${ry}" x2="${W-pad}" y2="${ry}" stroke="${r.c||'#8a93a3'}" stroke-width="1" stroke-dasharray="4 3" opacity=".7"/>`;}).join('');
  const last=vals[vals.length-1];
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px">
    ${ref}<polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.8"/>
    <circle cx="${x(vals.length-1).toFixed(1)}" cy="${y(last).toFixed(1)}" r="3" fill="${col}"/></svg>`;
}
function renderLiq(d){
  const box=document.getElementById('liqview');
  const L=d.latest||{}, C=d.computed||{}, lights=d.lights||{}, ov=d.overall||'gray';
  const V=n=>((L[n]||{}).value);
  const tgaModel=d.tga_targets&&d.tga_targets.release?d.tga_targets:null;
  const tgaDisplays=tgaModel&&window.PanoptesTgaTarget
    ? window.PanoptesTgaTarget.displayModels(tgaModel)
    : [];
  const tgaRefs=[{v:900,c:'#ff8a3d'}];
  if(tgaModel&&tgaModel.next&&tgaDisplays[1]) tgaRefs.unshift({v:Number(tgaModel.next.value),c:'#8793a3',domain:true});
  if(tgaModel&&tgaModel.current&&tgaDisplays[0]) tgaRefs.unshift({v:Number(tgaModel.current.value),c:'#c6cfda',domain:true});
  const tgaRefLabel=tgaDisplays.length
    ? `${tgaDisplays.map(v=>v.legendLabel).join(' / ')} / 주황 점선 = Panoptes 내부 경계 900B`
    : '미 재무부 공식 분기말 가정 업데이트 대기 / 주황 점선 = Panoptes 내부 경계 900B';
  const card=(title,val,sub,light)=>`<div class="liqcard" style="border-top:3px solid ${LIQC[light||'gray']}">
    <div class="lqt">${title} ${light?`<span class="lqdot" style="background:${LIQC[light]}"></span>`:''}</div>
    <div class="lqv">${val}</div><div class="lqs">${sub||''}</div></div>`;
  const charts=[
    ['NETLIQ','Net Liquidity','#2bc0d4',[],'$'+(C.net_liquidity/1000).toFixed(2)+'T',''],
    ['TGA','TGA (재무부 현금)','#ff8a3d',tgaRefs,V('TGA').toFixed(0)+'B',tgaRefLabel],
    ['RRP','RRP (역레포)','#ffd23d',[],V('RRP').toFixed(1)+'B',''],
    ['SOFR','SOFR vs IORB','#ff4d5e',[{v:V('IORB'),c:'#8a93a3'}],V('SOFR').toFixed(2)+'%',`IORB ${V('IORB').toFixed(2)}`],
    ['EFFR','EFFR vs IORB','#4ea1ff',[{v:V('IORB'),c:'#8a93a3'}],V('EFFR').toFixed(2)+'%',`IORB ${V('IORB').toFixed(2)}`],
    ['RESERVES','지급준비금','#59d0a8',[],(V('RESERVES')/1000).toFixed(2)+'T',''],
  ].map(([k,t,c,refs,cur,refLabel])=>`<div class="liqchart"><div class="lct"><span>${t}</span><b style="color:${c}">${cur}</b>${refLabel?`<span class="lcref">— ${esc(refLabel)}</span>`:''}</div>
    ${liqSpark(d.series[k]||{},{color:c,refs:refs})}</div>`).join('');
  box.innerHTML=`<style>
    .liqhead{display:flex;align-items:center;gap:14px;margin-bottom:6px}
    .liqhead h2{font-size:20px;font-weight:800}
    .ovbadge{font-size:12px;font-weight:700;padding:4px 12px;border-radius:999px}
    .liqsub{color:var(--dim);font-size:12.5px;margin-bottom:20px}
    .lights{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:22px}
    .liqcard{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:13px 16px;min-width:150px;flex:1}
    .lqt{font-size:11px;color:var(--dim);font-weight:600;display:flex;align-items:center;gap:6px}
    .lqdot{width:9px;height:9px;border-radius:50%;display:inline-block}
    .lqv{font-family:var(--mono);font-size:21px;font-weight:750;margin-top:4px}
    .lqs{font-family:var(--mono);font-size:10.5px;color:var(--dim);margin-top:2px}
    .liqgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px;margin-bottom:26px}
    .liqchart{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
    .lct{display:flex;align-items:baseline;gap:8px;font-size:12.5px;font-weight:650;margin-bottom:8px;flex-wrap:wrap}
    .lct b{font-family:var(--mono);font-size:14px}
    .lcref{font-family:var(--mono);font-size:10px;color:var(--dim);margin-left:auto;text-align:right;overflow-wrap:anywhere}
    @media(max-width:600px){.lcref{flex-basis:100%;margin-left:0;text-align:left}}
    .comment{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px 24px;max-width:900px}
    .comment pre{font-family:var(--sans);font-size:13.5px;line-height:1.85;white-space:pre-wrap;color:#cdd6de;margin:0}
    .comment .cmeta{font-family:var(--mono);font-size:11px;color:var(--dim);margin-top:14px;border-top:1px solid var(--line);padding-top:10px}
  </style>
  <div class="liqhead"><h2>💧 유동성 대시보드</h2>
    <span class="ovbadge" style="background:${LIQC[ov]}22;color:${LIQC[ov]}">종합 ${LIQLABEL[ov]}불</span></div>
  <p class="liqsub">Net Liquidity = 연준 총자산 − TGA − RRP · FRED 실시간 · 매일 자동 갱신 · 업데이트 ${d.updated||'—'}</p>
  <div class="lights">
    ${card('레포 (SOFR−IORB)',(C.sofr_iorb>=0?'+':'')+C.sofr_iorb+'%p',C.sofr_iorb>0?'IORB 위 = 스트레스':'IORB 아래 = 안정',lights.repo)}
    ${card('은행 (EFFR−IORB)',(C.effr_iorb>=0?'+':'')+C.effr_iorb+'%p',C.effr_iorb<0?'IORB 아래 = 정상':'경계',lights.bank)}
    ${card('TGA 흡수압력',V('TGA').toFixed(0)+'B',lights.tga==='green'?'내부 기준 900B 미만':'내부 경계 초과·재축적 압력',lights.tga)}
    ${card('RRP 완충재',V('RRP').toFixed(1)+'B',V('RRP')<20?'사실상 고갈':'남아있음',lights.rrp)}
    ${card('Net Liq 방향','$'+(C.net_liquidity/1000).toFixed(2)+'T',(C.net_liquidity_chg_1w>=0?'+':'')+C.net_liquidity_chg_1w+'B / 1주',lights.netliq)}
  </div>
  <div class="liqgrid">${charts}</div>
  <div class="comment"><pre>${(d.commentary||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}</pre>
    <div class="cmeta">자동 생성 해석 — 실시간 FRED 수치 기반. 투자 조언 아님. #TGA #RRP #SOFR #IORB #EFFR #NetLiquidity</div></div>`;
}

boot();
