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

  MAP = new maplibregl.Map({
    container:'map', attributionControl:false,
    style:{version:8, sources:{}, layers:[{id:'bg',type:'background',paint:{'background-color':'#0a0e14'}}]},
    center:[27,20], zoom:1.9, minZoom:1, maxZoom:9, renderWorldCopies:true
  });
  MAP.addControl(new maplibregl.NavigationControl({showCompass:false}),'bottom-right');

  MAP.on('load', ()=>{
    MAP.addSource('world',{type:'geojson',data:world});
    MAP.addLayer({id:'country-fill',type:'fill',source:'world',paint:{'fill-color':'#141c27','fill-opacity':1}});
    MAP.addLayer({id:'country-line',type:'line',source:'world',paint:{'line-color':'#243040','line-width':0.6}});
    MAP.addSource('events',{type:'geojson',data:geo()});
    MAP.addLayer({id:'ev-glow',type:'circle',source:'events',paint:{
      'circle-radius':['+',['*',['get','sev'],3],6],
      'circle-color':['get','color'],'circle-blur':1,'circle-opacity':0.35}});
    MAP.addLayer({id:'ev-dot',type:'circle',source:'events',paint:{
      'circle-radius':['+',['*',['get','sev'],1.6],3.5],
      'circle-color':['get','color'],'circle-stroke-color':'#0a0e14','circle-stroke-width':1.2,'circle-opacity':0.95}});
    MAP.on('click','ev-dot',e=>{const id=e.features[0].properties.id; select(id,true);});
    MAP.on('mouseenter','ev-dot',()=>MAP.getCanvas().style.cursor='pointer');
    MAP.on('mouseleave','ev-dot',()=>MAP.getCanvas().style.cursor='');
    buildFilters(); refresh();
  });

  document.getElementById('search').oninput=e=>{ST.q=e.target.value.toLowerCase().trim();refresh();};
  const sl=document.getElementById('timeSlider');
  sl.oninput=e=>{ST.timePct=+e.target.value;refresh();};
  document.getElementById('stEvents').textContent=EVENTS.length;
  const latest=EVENTS.map(e=>e.date).filter(Boolean).sort().pop();
  document.getElementById('stUpdated').textContent=latest||'—';
  if(DATES.length){document.getElementById('tlMin').textContent=new Date(DATES[0]).toISOString().slice(0,10);}
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

boot();
