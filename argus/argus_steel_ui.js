/* ARGUS steel observatory. Pure SVG; no network, storage or third-party dependencies.
 * PHXSteelUI.mount(host, payload). Data validation and model calculation belong to the builder.
 * Missing points stay missing. Source estimates are distinct from our conditional forecasts.
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.PHXSteelUI = api;
}(typeof window !== 'undefined' ? window : this, function () {
  'use strict';
  var DAY = 86400000;
  var COLORS = ['#58aaff', '#64d6b0', '#f2c86b', '#c49aff', '#ee8b82', '#64ccd8'];
  var HOSTS = ['www.eia.gov','eia.gov','api.eia.gov','fred.stlouisfed.org','www.stlouisfed.org',
    'bakerhughesrigcount.gcs-web.com','rigcount.bakerhughes.com','www.bakerhughes.com',
    'ir.tenaris.com','www.tenaris.com','dart.fss.or.kr','kind.krx.co.kr','www.nexteel.com',
    'www.husteel.com','www.husteel.co.kr','www.seahsteel.co.kr','www.seahsteel.com',
    'www.seahsteelholdings.com','www.seah.co.kr','www.spglobal.com','www.argusmedia.com',
    'prestonpipe.com','www.prestonpipe.com','www.bls.gov','api.bls.gov',
    'www.cmegroup.com','www.dallasfed.org','www.federalreserve.gov','www.trade.gov','www.aogr.com','www.sec.gov','steelbenchmarker.com','www.steelbenchmarker.com','efracs.primaryvision.co','primaryvision.co','www.primaryvision.co'];
  var STATUS = {actual:'실측·공시',derived:'공시 기반 계산',estimate:'추정',provider_estimate:'원기관 추정',forecast:'조건부 추정',user_reported:'사용자 제시 · 미검증',missing:'미확인'};
  var CSS = `
  .ast-root{color:var(--ink,#e6edf3);font:13px/1.6 var(--sans,system-ui,sans-serif);min-width:0;margin-bottom:28px;--ast-line:#29394c;--ast-dim:#a2b2c4}
  .ast-root *{box-sizing:border-box}.ast-root h3,.ast-root h4,.ast-root p{margin:0}.ast-root button,.ast-root select{font:inherit}
  .ast-root a{color:#7dd9dd;text-underline-offset:3px;overflow-wrap:anywhere}.ast-root button:focus-visible,.ast-root select:focus-visible,.ast-root summary:focus-visible,.ast-root [tabindex]:focus-visible{outline:3px solid #64ccd8;outline-offset:3px}
  .ast-hero{display:block;position:relative;top:auto;z-index:auto;padding:22px;border:1px solid #315166;border-radius:14px;background:linear-gradient(125deg,#142b35,#121c2a 70%);margin-bottom:20px}
  .ast-kpis{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:14px 0}.ast-kpi{padding:16px 18px;border:1px solid #365167;border-radius:10px;background:#132535;min-width:0}.ast-kpi-label{font-size:11px;color:#adc1d4}.ast-kpi-value{display:block;font:700 25px/1.4 ui-monospace,monospace;font-variant-numeric:tabular-nums;overflow-wrap:anywhere;margin-top:5px}.ast-kpi small{color:#9bb3c9;font-size:10px}.ast-capacity{margin:12px 0}.ast-capacity-row{margin:12px 0}.ast-capacity-row div:first-child{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;font-size:11px}.ast-capacity-track{height:10px;background:#223144;border-radius:3px;overflow:hidden;margin-top:5px}.ast-capacity-track i{display:block;height:100%;border-radius:3px;background:#67aef2}.ast-capacity-track.q i{background:#64d6b0}
  .ast-eyebrow{font-size:10px;letter-spacing:.12em;color:#7dd9dd;font-weight:700}.ast-hero h3{font-size:23px;letter-spacing:-.04em;margin:5px 0 10px}.ast-note{font-size:11px;color:var(--ast-dim);line-height:1.75;overflow-wrap:anywhere}
  .ast-toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:16px 0}.ast-toolbar h4{font-size:16px;flex:1}.ast-range{display:flex;gap:5px;flex-wrap:wrap}.ast-range button{cursor:pointer;border:1px solid var(--ast-line);border-radius:6px;color:var(--ast-dim);background:#101926;padding:5px 12px;font-size:11px}.ast-range button[aria-pressed=true]{border-color:#5a9db3;color:#b3edf1;background:#16313a}
  .ast-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.ast-card{min-width:0;border:1px solid var(--ast-line);border-radius:12px;background:var(--panel,#111721);padding:17px}.ast-card h4{font-size:14px}.ast-card-head{display:flex;align-items:start;gap:10px;justify-content:space-between;margin-bottom:13px}.ast-card-no{color:#6a8ea6;font:11px ui-monospace,monospace;letter-spacing:.1em}
  .ast-chart{min-width:0;margin-top:14px}.ast-chart-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:5px}.ast-chart-title{font-size:12px;font-weight:650}.ast-latest{font:600 15px ui-monospace,monospace;font-variant-numeric:tabular-nums}.ast-latest small{font:10px system-ui;color:var(--ast-dim);margin-left:5px}.ast-unit{color:var(--ast-dim);font-size:10px;margin-bottom:4px}
  .ast-plot{position:relative;width:100%;min-width:0;border-radius:7px;touch-action:pan-y}.ast-plot svg{display:block;width:100%;height:auto;overflow:visible}.ast-plot line,.ast-plot path{vector-effect:non-scaling-stroke}.ast-plot .ast-hit{cursor:crosshair}.ast-tip{min-height:40px;font-size:11px;color:#c9d7e4;line-height:1.65;padding:7px 0 2px;overflow-wrap:anywhere}
  .ast-legend{display:flex;gap:8px 15px;flex-wrap:wrap;color:var(--ast-dim);font-size:10px;margin:7px 0}.ast-legend span{display:inline-flex;align-items:center;gap:6px}.ast-swatch{width:21px;border-top:2px solid #78b9ee;display:inline-block}.ast-swatch.dashed{border-top-style:dashed}.ast-swatch.band{height:8px;border:0;background:rgba(120,185,238,.24)}.ast-swatch.point{width:6px;height:6px;border:1px solid #f2c86b;transform:rotate(45deg)}
  .ast-method{padding:16px 18px;border:1px solid #35475b;border-radius:10px;background:#14212c;margin-bottom:20px}.ast-method h4{font-size:14px;margin-bottom:5px}.ast-method summary{font-size:12px}.ast-breakdown{margin:14px 0}.ast-static svg{display:block;width:100%;height:auto}.ast-static text{font-family:var(--sans,system-ui,sans-serif)}.ast-static{min-width:0;margin-top:12px}.ast-static svg [tabindex]:focus{outline:none;stroke:#f3d47a;stroke-width:2}.ast-model-warning{padding:10px;border-left:3px solid #c8a86a;background:#302a1c;color:#e6d6ae;font-size:11px;margin:10px 0}.ast-validation{padding:12px 14px;margin:14px 0;border-left:3px solid #829bb1;background:#14212c}.ast-validation strong{font-size:12px}.ast-breakdown .ast-note{margin-top:5px}.ast-empty{padding:22px 12px;border:1px dashed #324457;border-radius:8px;color:var(--ast-dim);font-size:12px;margin:12px 0}.ast-table-wrap{overflow:auto;max-height:310px;max-width:100%;margin-top:9px;overscroll-behavior:contain}.ast-root table{width:100%;min-width:600px;border-collapse:collapse;font-size:11px;font-variant-numeric:tabular-nums}.ast-root th,.ast-root td{padding:8px 10px;border-bottom:1px solid #253243;text-align:right;white-space:nowrap}.ast-root thead th{position:sticky;top:0;background:#152130;color:#aec1d3;font-size:10px}.ast-root th:first-child,.ast-root td:first-child{text-align:left}.ast-root td.ast-text{white-space:normal;min-width:180px;max-width:400px;text-align:left;line-height:1.6}.ast-root caption{text-align:left;padding:6px 0;color:var(--ast-dim)}
  .ast-root details{margin-top:12px;border-top:1px solid #253243;padding-top:10px}.ast-root summary{cursor:pointer;font-size:11px;color:#b2c4d4;max-width:100%;overflow-wrap:anywhere}.ast-root ul{padding-left:18px;margin:8px 0}.ast-root li{margin:5px 0;overflow-wrap:anywhere}.ast-company{scroll-margin-top:105px;margin-top:28px;padding-top:22px;border-top:1px solid #354355}.ast-company-select{display:flex;gap:8px;align-items:center;font-size:12px;min-width:0}.ast-company-select select{color:#e7eff7;background:#172432;border:1px solid #435a6f;border-radius:7px;padding:8px 28px 8px 10px;max-width:100%;min-width:0}.ast-company-intro{padding:14px 16px;background:#111f2b;border-left:3px solid #64ccd8;border-radius:6px;margin-bottom:14px}.ast-company-intro strong{font-size:16px}.ast-assumptions{margin-top:14px;padding:15px 18px;border:1px solid #344458;border-radius:10px;font-size:12px}.ast-insights{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr));gap:10px;margin:14px 0}.ast-insight{padding:14px 16px;background:#14212c;border-radius:9px;border-left:2px solid #4d91b0;min-width:0}.ast-insight strong{font-size:12px;display:block;margin-bottom:5px}.ast-source{padding:9px 0;border-bottom:1px solid #253243;overflow-wrap:anywhere}.ast-source small{display:block;color:var(--ast-dim);margin-top:3px}.ast-scope{color:#b9cddc;font-size:11px}.ast-model-tag{font-size:10px;color:#f2d799;border:1px solid #61593d;border-radius:4px;padding:2px 6px;white-space:nowrap}
  @media(max-width:800px){.ast-kpi{padding:14px}.ast-kpi-value{font-size:20px}.ast-grid{grid-template-columns:minmax(0,1fr)}.ast-hero{padding:18px}.ast-hero h3{font-size:21px}.ast-card{padding:14px}.ast-toolbar{align-items:flex-start}.ast-company-select{width:100%;flex-wrap:wrap}.ast-company-select select{flex:1}.ast-latest{font-size:14px}.ast-tip{min-height:48px}}
  `;
  function esc(v) { return String(v == null ? '' : v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];}); }
  function finite(v) { return typeof v === 'number' && Number.isFinite(v); }
  function fmt(v) { if(Object.is(v,-0))v=0;return finite(v) ? v.toLocaleString('en-US',{maximumFractionDigits:Math.abs(v)<1?3:2}) : '—'; }
  function displayScale(s){
    var n=Math.max.apply(null,(s.points||[]).map(function(p){return Math.abs(finite(p.value)?p.value:finite(p.base)?p.base:0);}));
    if(s.unit==='KRW'&&n>=1e8)return {divisor:1e8,unit:'억 원'};
    if(s.unit==='USD'&&n>=1e6)return {divisor:1e6,unit:'백만 USD'};
    if(s.unit==='KRW/t'&&n>=1e4)return {divisor:1e4,unit:'만원/톤'};
    if(s.unit==='t'&&n>=1e3)return {divisor:1e3,unit:'천 톤'};
    return {divisor:1,unit:s.unit||'단위 미확인'};
  }
  function safeURL(v) {
    if (typeof v !== 'string' || /[\s\\\u0000-\u001f]/.test(v)) return null;
    try { var u=new URL(v); if(u.protocol!=='https:' || u.username || u.password || u.hash || (u.port&&u.port!=='443') || HOSTS.indexOf(u.hostname)===-1) return null;
      if(u.search && !((u.hostname==='dart.fss.or.kr' && Array.from(u.searchParams).every(function(kv){return /^(rcpNo|dcmNo|eleId|offset|length)$/.test(kv[0])&&/^\d+$/.test(kv[1])||kv[0]==='dtd'&&/^dart\d+\.xsd$/.test(kv[1]);})) || (u.hostname==='www.eia.gov'&&Array.from(u.searchParams).every(function(kv){return kv[0]==='id'&&/^\d+$/.test(kv[1]);})))) return null;
      return u.href;
    } catch (_) { return null; }
  }
  function link(v,label) { var u=safeURL(v); return u?'<a href="'+esc(u)+'" target="_blank" rel="noopener noreferrer">'+esc(label||'원문')+'</a>':esc(label||'원문 URL 미확인'); }
  function periodInfo(v) {
    if(typeof v!=='string')return null;
    var m=/^(\d{4})-?Q([1-4])$/.exec(v); if(m){var y=+m[1],q=+m[2];if(y<1900||y>2200)return null;return {time:Date.UTC(y,(q-1)*3,1),index:y*4+q-1,kind:'quarter',label:y+'Q'+q};}
    m=/^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(v);if(!m)return null;
    var yy=+m[1],mm=+m[2],dd=m[3]?+m[3]:1,t=Date.UTC(yy,mm-1,dd),d=new Date(t);
    if(yy<1900||yy>2200||d.getUTCFullYear()!==yy||d.getUTCMonth()!==mm-1||d.getUTCDate()!==dd)return null;
    return {time:t,index:yy*12+mm-1,kind:m[3]?'day':'month',label:v};
  }
  function normalizeSeries(s) {
    s=s||{};var issues=[],seen=new Set();
    var points=(Array.isArray(s.points)?s.points:[]).map(function(p,i){
      var info=periodInfo(p.period||p.date);if(!info){issues.push('invalid_period:'+i);return null;}
      var key=String(p.period||p.date);if(seen.has(key))issues.push('duplicate_period:'+key);seen.add(key);
      var status=Object.prototype.hasOwnProperty.call(STATUS,p.status)?p.status:'missing';
      var value=finite(p.value)?p.value:status==='forecast'&&finite(p.base)?p.base:null;
      var low=finite(p.low)?p.low:null,high=finite(p.high)?p.high:null;
      if(low!==null&&high!==null&&(low>high||(value!==null&&(value<low||value>high)))){issues.push('invalid_band:'+key);low=null;high=null;}
      return Object.assign({},p,{period:key,time:info.time,periodInfo:info,value:value,low:low,high:high,status:status});
    }).filter(Boolean).sort(function(a,b){return a.time-b.time;});
    var collisions={};points.forEach(function(p){collisions[p.time]=(collisions[p.time]||0)+1;});
    points.forEach(function(p){p.conflict=collisions[p.time]>1;});
    return Object.assign({},s,{id:String(s.id||''),name:s.name||s.label||s.id||'지표',points:points,issues:issues});
  }
  function continuous(a,b,s) {
    if(!a||!b||s.connect===false||a.connect===false||b.connect===false||s.date_basis==='publication_snapshot'||a.date_basis==='publication_snapshot'||b.date_basis==='publication_snapshot'||s.frequency==='publication_snapshot'||b.break_before===true||a.conflict||b.conflict||!finite(a.value)||!finite(b.value)||b.time<=a.time)return false;
    var f=s.frequency||a.periodInfo.kind;
    if(f==='quarterly'||f==='quarter'||f==='quarter_end')return a.periodInfo.kind==='quarter'&&b.periodInfo.kind==='quarter'&&b.periodInfo.index-a.periodInfo.index===1;
    if(f==='monthly'||f==='month')return b.periodInfo.index-a.periodInfo.index===1;
    if(f==='annual'||f==='yearly')return new Date(b.time).getUTCFullYear()-new Date(a.time).getUTCFullYear()===1;
    var max=finite(s.max_gap_days)&&s.max_gap_days>0?s.max_gap_days:f==='biweekly'?18:f==='weekly'||f==='week'?10:5;
    return (b.time-a.time)/DAY<=max;
  }
  function statusClass(p){return p.status==='actual'?'actual':p.status==='forecast'?'forecast':p.status==='derived'?'derived':p.status==='estimate'||p.status==='provider_estimate'?'estimate':'point';}
  function lineSegments(s) {
    var out=[];
    s.points.forEach(function(p,i){var a=s.points[i-1];if(!continuous(a,p,s))return;var ca=statusClass(a),cb=statusClass(p);
      if(ca==='point'||cb==='point')return;
      var factual=(ca==='actual'||ca==='derived')&&(cb==='actual'||cb==='derived');
      if(ca!==cb && !factual && !((ca==='actual'||ca==='derived'||ca==='estimate')&&cb==='forecast'))return;
      out.push({a:a,b:p,status:factual&&(ca==='derived'||cb==='derived')?'derived':cb});
    });return out;
  }
  function chartDomain(series, start, end) {
    var ts=[];series.forEach(function(s){s.points.forEach(function(p){ts.push(p.time);});});
    if(!ts.length)return null;
    var lo=finite(start)?start:Math.min.apply(null,ts),hi=finite(end)?end:Math.max.apply(null,ts);
    if(hi<=lo)hi=lo+30*DAY;
    return [lo,hi];
  }
  function filterSeries(s,domain){return Object.assign({},s,{points:s.points.filter(function(p){return p.time>=domain[0]&&p.time<=domain[1];})});}
  function ticks(domain,quarterly) {
    var vals=[],lo=new Date(domain[0]),hi=new Date(domain[1]),span=(domain[1]-domain[0])/DAY;
    var step=quarterly?(span>900?6:3):span>2600?24:span>1300?12:span>620?6:span>180?3:1;
    var t=Date.UTC(lo.getUTCFullYear(),lo.getUTCMonth(),1);while(t<domain[0]){var d=new Date(t);t=Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,1);}
    while(t<=domain[1]){var dt=new Date(t),month=dt.getUTCMonth();if(month%step===0 || step>=12&&month===0&&dt.getUTCFullYear()%(step/12)===0)vals.push({time:t,label:quarterly?dt.getUTCFullYear()+'Q'+(Math.floor(month/3)+1):step>=12?String(dt.getUTCFullYear()):String(dt.getUTCFullYear()).slice(2)+'.'+String(month+1).padStart(2,'0')});t=Date.UTC(dt.getUTCFullYear(),month+1,1);}
    if(vals.length>6)vals=vals.filter(function(_,i){return i%Math.ceil(vals.length/6)===0;});
    if(!vals.length)vals=[{time:domain[0],label:new Date(domain[0]).toISOString().slice(0,7)},{time:domain[1],label:hi.toISOString().slice(0,7)}];
    return vals;
  }
  function sourceMap(payload){var map={};[].concat(payload.sources||[],payload.market&&payload.market.sources||[]).forEach(function(s){if(s&&s.id)map[s.id]=s;});(payload.companies||[]).forEach(function(c){(c.sources||[]).forEach(function(s){if(s&&s.id)map[s.id]=s;});});return map;}
  function sourceFor(p,s,sources){return sources[p.source_id]||sources[(p.source_ids||[])[0]]||sources[(s.source_ids||[])[0]]||{};}
  function pointText(p,s) {
    var parts=[p.period,s.name+': '+fmt(p.value)+' '+(s.unit||''),STATUS[p.status]||'미확인'];
    if(p.status==='forecast')parts.push('하단 '+fmt(p.low)+' / 기준 '+fmt(p.value)+' / 상단 '+fmt(p.high));
    if(p.date_basis==='publication_snapshot'||s.date_basis==='publication_snapshot'||s.frequency==='publication_snapshot')parts.push('게시일 기준 · 집계일 미확인');
    if(p.contract)parts.push('계약 '+p.contract+(p.contract_month?' / '+p.contract_month:''));
    if(p.published_at)parts.push('발표 '+p.published_at);
    if(p.break_before===true)parts.push('비교 단절 · 이전 관측과 연결하지 않음');
    if(p.note)parts.push(p.note);
    return parts.join(' · ');
  }
  function valueTable(s,sources) {
    return '<details class="ast-data"><summary>수치·기준·원문 '+s.points.length+'개 관측 펼치기</summary><div class="ast-table-wrap" tabindex="0" role="region" aria-label="'+esc(s.name)+' 수치 표"><table><caption>'+esc(s.name)+' · '+esc(s.unit||'단위 미확인')+' · 빈값 — · 추정 범위는 신뢰구간이 아닙니다.</caption><thead><tr><th scope="col">기간</th><th scope="col">값 / 기준</th><th scope="col">하단</th><th scope="col">상단</th><th scope="col">성격</th><th scope="col">발표일</th><th scope="col">근거</th></tr></thead><tbody>'+s.points.slice().reverse().map(function(p){var src=sourceFor(p,s,sources);return '<tr><th scope="row">'+esc(p.period)+'</th><td>'+esc(fmt(p.value))+'</td><td>'+esc(fmt(p.low))+'</td><td>'+esc(fmt(p.high))+'</td><td>'+esc(STATUS[p.status])+'</td><td>'+esc(p.published_at||src.published_at||src.published_date||'미확인')+'</td><td class="ast-text">'+((p.source_ids||[]).length?(p.source_ids||[]).map(function(id){var cited=sources[id]||{};return link(cited.url||cited.source_url,cited.name||cited.label||id);}).join('<br>'):link(p.source_url||src.url||src.source_url||s.source_url,src.name||src.label||p.source_id||'원문'))+(p.note?'<br>'+esc(p.note):'')+'</td></tr>';}).join('')+'</tbody></table></div></details>';
  }
  function chart(s, opts, sources, registry) {
    opts=opts||{};var domain=opts.domain||chartDomain([s]),ss=domain?filterSeries(s,domain):s;
    var good=ss.points.filter(function(p){return finite(p.value);}),last=good[good.length-1],key=String(registry.length),color=opts.color||COLORS[0];
    if(!domain||!good.length)return '<section class="ast-chart"><h4>'+esc(s.name)+'</h4><div class="ast-empty">선택 기간에 확인된 시계열이 없습니다. '+esc(s.note||s.limitation||'빈 기간은 보간하지 않습니다.')+'</div>'+valueTable(ss,sources)+'</section>';
    var W=finite(opts.width)?Math.max(260,Math.min(800,opts.width)):560,H=190,L=56,R=26,T=18,B=34,values=[],scale=displayScale(ss);
    good.forEach(function(p){values.push(p.value);if(p.status==='forecast'){if(finite(p.low))values.push(p.low);if(finite(p.high))values.push(p.high);}});
    // Levels should show their observed range by default.  A source can still
    // request a zero reference explicitly, and mixed-sign series always retain it.
    var zeroAxis=typeof opts.zeroAxis==='boolean'?opts.zeroAxis:s.zero_axis===true;
    var ymin=Math.min.apply(null,values),ymax=Math.max.apply(null,values);
    // A negative series needs a zero reference even when it is otherwise a
    // range-focused chart: losing money versus breaking even is meaningful.
    if(ymin<0)zeroAxis=true;
    if(zeroAxis){ymin=Math.min(0,ymin);ymax=Math.max(0,ymax);}
    var pad=(ymax-ymin)*.09||(Math.abs(ymax)*.1)||1;ymin=!zeroAxis||ymin<0?ymin-pad:ymin;ymax+=pad;
    var x=function(t){return L+(t-domain[0])/(domain[1]-domain[0])*(W-L-R);},y=function(v){return T+(ymax-v)/(ymax-ymin)*(H-T-B);};
    var svg='<svg viewBox="0 0 '+W+' '+H+'" data-y-min="'+ymin+'" data-y-max="'+ymax+'" role="img" aria-label="'+esc(s.name+' · '+(s.unit||'')+' · '+ss.points[0].period+'부터 '+ss.points[ss.points.length-1].period)+'">';
    for(var k=0;k<=4;k++){var val=ymin+(ymax-ymin)*k/4,yy=y(val);svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+yy+'" y2="'+yy+'" stroke="#263749"/><text x="'+(L-8)+'" y="'+(yy+4)+'" text-anchor="end" fill="#a2b2c4" font-size="11">'+esc(fmt(val/scale.divisor))+'</text>';}
    if(ymin<0&&ymax>0)svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y(0)+'" y2="'+y(0)+'" stroke="#71889d" stroke-dasharray="3 3"/>';
    var xticks=ticks(domain,/quarter/.test(s.frequency||'')||ss.points.some(function(p){return p.periodInfo.kind==='quarter';}));if(W<380&&xticks.length>4)xticks=xticks.filter(function(_,i){return i%2===0;});
    xticks.forEach(function(t){svg+='<text x="'+x(t.time)+'" y="'+(H-10)+'" text-anchor="middle" fill="#a2b2c4" font-size="11">'+esc(t.label)+'</text>';});
    var forecast=good.filter(function(p){return p.status==='forecast';});
    if(forecast.length){var fx=x(forecast[0].time);svg+='<rect x="'+fx+'" y="'+T+'" width="'+Math.max(0,W-R-fx)+'" height="'+(H-T-B)+'" fill="#6585b4" fill-opacity=".04"/><line x1="'+fx+'" x2="'+fx+'" y1="'+T+'" y2="'+(H-B)+'" stroke="#61778d" stroke-dasharray="3 4"/><text x="'+Math.min(fx+6,W-80)+'" y="'+(T+10)+'" fill="#c1cddc" font-size="10">조건부 추정</text>';}
    lineSegments(ss).forEach(function(seg){var a=seg.a,b=seg.b;if(seg.status==='forecast'&&a.status==='forecast'&&[a.low,a.high,b.low,b.high].every(finite))svg+='<path class="ast-band" d="M'+x(a.time)+','+y(a.low)+' L'+x(b.time)+','+y(b.low)+' L'+x(b.time)+','+y(b.high)+' L'+x(a.time)+','+y(a.high)+' Z" fill="'+color+'" fill-opacity=".18" stroke="none"/>';});
    // One path per contiguous run. Values are joined only when the source cadence permits it.
    var runs=[];lineSegments(ss).forEach(function(seg){var prev=runs[runs.length-1];if(prev&&prev.status===seg.status&&prev.last===seg.a){prev.path+=' L'+x(seg.b.time)+','+y(seg.b.value);prev.last=seg.b;}else runs.push({status:seg.status,path:'M'+x(seg.a.time)+','+y(seg.a.value)+' L'+x(seg.b.time)+','+y(seg.b.value),last:seg.b});});
    runs.forEach(function(r){svg+='<path data-line-status="'+r.status+'" d="'+r.path+'" stroke="'+color+'" stroke-width="2" fill="none"'+(r.status!=='actual'?' stroke-dasharray="'+(r.status==='forecast'?'6 4':'2 3')+'"':'')+'/>';});
    good.forEach(function(p,i){if(good.length>90&&p.status!=='user_reported'&&i!==good.length-1)return;
      var xx=x(p.time),yy=y(p.value);svg+=p.status==='user_reported'?'<path data-observation="user_reported" d="M'+xx+','+(yy-5)+' l5,5 -5,5 -5,-5 Z" fill="#111721" stroke="#f2c86b" stroke-width="1.5"><title>'+esc(pointText(p,s))+'</title></path>':'<circle data-observation="'+p.status+'" cx="'+xx+'" cy="'+yy+'" r="'+(p.status==='forecast'?3.2:2.5)+'" fill="'+(p.status==='actual'?color:'#111721')+'" stroke="'+color+'" stroke-width="1.6"><title>'+esc(pointText(p,s))+'</title></circle>';});
    svg+='<line class="ast-cursor" x1="0" x2="0" y1="'+T+'" y2="'+(H-B)+'" stroke="#91adc5" stroke-dasharray="3 3" visibility="hidden"/><rect class="ast-hit" x="'+L+'" y="'+T+'" width="'+(W-L-R)+'" height="'+(H-T-B)+'" fill="transparent"/></svg>';
    registry.push({series:ss,domain:domain,width:W,left:L,right:R,latest:pointText(last,s),sources:sources});
    var kinds={};good.forEach(function(p){kinds[p.status]=true;});var legend='<div class="ast-legend">';
    var pointOnly=s.connect===false||s.frequency==='publication_snapshot'||s.date_basis==='publication_snapshot';
    if(pointOnly)legend+='<span><i class="ast-swatch point" style="border-color:'+color+';border-radius:50%;transform:none"></i>'+(s.frequency==='publication_snapshot'||s.date_basis==='publication_snapshot'?'게시일 기준 관측':'기간별 관측')+' · 선 연결 없음</span>';
    if(kinds.actual&&!pointOnly)legend+='<span><i class="ast-swatch" style="border-color:'+color+'"></i>실측·공시</span>';
    if(kinds.derived)legend+='<span><i class="ast-swatch dashed" style="border-color:'+color+'"></i>공시 기반 계산</span>';
    if((kinds.estimate||kinds.provider_estimate)&&!pointOnly)legend+='<span><i class="ast-swatch dashed" style="border-color:'+color+'"></i>'+(kinds.estimate?'추정':'원기관 추정')+'</span>';
    if(kinds.forecast)legend+='<span><i class="ast-swatch dashed" style="border-color:'+color+'"></i>기준 추정</span><span><i class="ast-swatch band" style="background:'+color+'33"></i>하단–상단 가정 범위</span>';
    if(kinds.user_reported)legend+='<span><i class="ast-swatch point"></i>사용자 제시 · 미검증</span>';
    legend+='</div>';
    var freq={daily:'일별',weekly:'주별',biweekly:'격주 관측',publication_snapshot:'게시일 스냅샷',reporting_period:'공시 누적기간',quarter_end:'분기말 잔액',monthly:'월별',quarterly:'분기별',annual:'연간',selected_assessments:'선별 관측'};
    return '<section class="ast-chart"><div class="ast-chart-head"><span class="ast-chart-title">'+esc(s.name)+'</span><span class="ast-latest" style="color:'+color+'">'+esc(fmt(last.value/scale.divisor))+'<small>'+esc(last.period)+'</small></span></div><div class="ast-unit">'+esc(scale.unit)+(s.frequency?' · '+esc(freq[s.frequency]||s.frequency):'')+(scale.divisor!==1?' · 표·툴팁은 원단위':'')+(!zeroAxis?' · 관측범위 확대축(0 시작 아님)':'')+'</div><div class="ast-plot" data-ast-chart="'+key+'" tabindex="0" role="group" aria-label="'+esc(s.name+' 시계열. 좌우 방향키로 관측 탐색')+'">'+svg+'</div>'+legend+'<div class="ast-tip" data-ast-tip="'+key+'">'+esc(pointText(last,s))+'</div><p class="ast-note">'+esc(s.basis||s.price_basis||'')+(s.note?' · '+esc(s.note):'')+'</p>'+valueTable(ss,sources)+'</section>';
  }
  function strings(items) { return (Array.isArray(items)?items:items?[items]:[]).map(function(v){if(typeof v==='string')return v;return v.text||v.note||v.summary||v.description||(v.label&&v.value!==undefined?v.label+': '+v.value:'');}).filter(Boolean); }
  function list(items){var a=strings(items);return a.length?'<ul>'+a.map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul>':'';}
  function sourceList(sources){return (sources||[]).map(function(s){return '<div class="ast-source">'+link(s.url||s.source_url,s.name||s.label||s.id||'원문')+'<small>'+esc(s.publisher||'')+(s.published_at||s.published_date?' · 발표 '+esc(s.published_at||s.published_date):'')+(s.observation_period?' · 관측기간 '+esc(s.observation_period):'')+(s.retrieved_at?' · 확인 '+esc(s.retrieved_at):'')+'</small>'+(s.note?'<p class="ast-note">'+esc(s.note)+'</p>':'')+'</div>';}).join('');}
  function insights(items) { return (items||[]).filter(function(x){return typeof x==='string'||x.title||x.label||x.reading||x.text||x.note||x.summary||x.interpretation;}).map(function(x){if(typeof x==='string')return '<article class="ast-insight"><p>'+esc(x)+'</p></article>';return '<article class="ast-insight"><strong>'+esc(x.title||x.label||x.period||'관측 해석')+'</strong>'+(x.signal?'<p class="ast-note">관측 · '+esc(x.signal)+'</p>':'')+'<p class="ast-note">'+esc(x.reading||x.text||x.note||x.summary||x.interpretation||'')+'</p>'+(x.evidence?'<div class="ast-note">근거'+list(x.evidence)+'</div>':'')+(x.invalidation?'<p class="ast-note">다시 확인할 조건 · '+esc(x.invalidation)+'</p>':'')+(x.limitation?'<p class="ast-note">한계 · '+esc(x.limitation)+'</p>':'')+(x.source_url?'<p>'+link(x.source_url,'근거')+'</p>':'')+'</article>';}).join(''); }
  function lensHTML(items,persona){persona=persona||{};return '<section class="ast-assumptions" data-ast-lens style="scroll-margin-top:105px"><strong>'+esc(persona.label||'관측에서 해석으로')+'</strong>'+(persona.basis?'<p class="ast-note">'+esc(persona.basis)+'</p>':'')+(persona.disclaimer?'<p class="ast-note">'+esc(persona.disclaimer)+'</p>':'')+'<div class="ast-insights">'+insights(items)+'</div></section>';}
  function priceReferenceHTML(payload,width){
    var sources=sourceMap(payload||{}), market=(payload&&payload.market)||{}, rows=(market.series||[]).map(normalizeSeries), octg=rows.find(function(s){return s.id==='octg_p110_55_fob_user';}), hrb=rows.find(function(s){return s.id==='steelbenchmarker_us_hrb_net_ton';});
    if(!octg||!hrb||!octg.points.length||!hrb.points.length)return '<section class="ast-card" data-ast-price-reference><h4>북미 OCTG · 열연 참조</h4><div class="ast-empty">OCTG 기준점 또는 공개 열연 시계열이 없어 차트를 보류합니다.</div></section>';
    var domain=chartDomain([octg,hrb]), W=Math.max(300,Math.min(760,width||640)), H=270,L=62,R=62,T=28,B=42, octgValues=octg.points.filter(function(p){return finite(p.value);}).map(function(p){return p.value;}), hrbValues=hrb.points.filter(function(p){return finite(p.value);}).map(function(p){return p.value;});
    if(!domain||!octgValues.length||!hrbValues.length)return '<section class="ast-card" data-ast-price-reference><h4>북미 OCTG · 열연 참조</h4><div class="ast-empty">유효한 관측값이 없어 차트를 보류합니다.</div></section>';
    function extent(vals){var lo=Math.min.apply(null,vals),hi=Math.max.apply(null,vals),pad=(hi-lo)*.10||Math.abs(hi)*.10||1;return [lo-pad,hi+pad];}
    var oe=extent(octgValues),he=extent(hrbValues),x=function(t){return L+(t-domain[0])/(domain[1]-domain[0])*(W-L-R);},yo=function(v){return T+(oe[1]-v)/(oe[1]-oe[0])*(H-T-B);},yh=function(v){return T+(he[1]-v)/(he[1]-he[0])*(H-T-B);};
    var svg='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="북미 OCTG 기준점과 미국 열연 HRB 공개 시계열. 두 축은 서로 다른 제품과 거래조건이며 스프레드가 아닙니다." data-ast-price-reference>';
    for(var i=0;i<=4;i++){var yy=T+(H-T-B)*i/4,ov=oe[1]-(oe[1]-oe[0])*i/4,hv=he[1]-(he[1]-he[0])*i/4;svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+yy+'" y2="'+yy+'" stroke="#263749"/><text x="'+(L-8)+'" y="'+(yy+4)+'" text-anchor="end" fill="#f2c86b" font-size="10">'+esc(fmt(ov))+'</text><text x="'+(W-R+8)+'" y="'+(yy+4)+'" fill="#64d6b0" font-size="10">'+esc(fmt(hv))+'</text>';}
    var xt=ticks(domain,false);if(W<420&&xt.length>4)xt=xt.filter(function(_,i){return i%2===0;});xt.forEach(function(t){svg+='<text x="'+x(t.time)+'" y="'+(H-14)+'" text-anchor="middle" fill="#a2b2c4" font-size="10">'+esc(t.label)+'</text>';});
    lineSegments(hrb).forEach(function(seg){svg+='<path data-ast-price-hrb-line d="M'+x(seg.a.time)+','+yh(seg.a.value)+' L'+x(seg.b.time)+','+yh(seg.b.value)+'" fill="none" stroke="#64d6b0" stroke-width="2.2"/>';});
    hrb.points.forEach(function(p){if(finite(p.value))svg+='<circle cx="'+x(p.time)+'" cy="'+yh(p.value)+'" r="2.3" fill="#64d6b0"><title>'+esc(pointText(p,hrb))+'</title></circle>';});
    octg.points.forEach(function(p){if(finite(p.value)){var px=x(p.time),py=yo(p.value);svg+='<path data-ast-price-octg-point d="M'+px+','+(py-6)+' l6,6 -6,6 -6,-6 Z" fill="#111721" stroke="#f2c86b" stroke-width="2"><title>'+esc(pointText(p,octg))+'</title></path>';}});
    svg+='</svg>';
    return '<section class="ast-card" data-ast-price-reference><div class="ast-card-head"><div><h4>북미 OCTG · 열연 참조</h4><p class="ast-note">이미지형 시장 차트 · OCTG는 확인된 단일 기준점만 표시하고, 공개 열연은 별도 우측축으로 표시합니다.</p></div><span class="ast-card-no">MARKET</span></div><div class="ast-unit"><span style="color:#f2c86b">좌축 OCTG P110 5.5인치 · USD/short ton</span> <span aria-hidden="true">·</span> <span style="color:#64d6b0">우축 미국 열연 HRB · USD/net ton</span></div><div class="ast-static">'+svg+'</div><div class="ast-legend"><span><i class="ast-swatch point"></i>OCTG · 사용자 제시 1점 · 선 연결 없음</span><span><i class="ast-swatch" style="border-color:#64d6b0"></i>SteelBenchmarker 미국 열연 HRB · 공개 시계열</span></div><p class="ast-note">두 계열은 제품 사양·거래조건·출처 범위가 달라 차액 또는 HR Spread로 계산하지 않습니다. OCTG 연속 시계열이 확보되기 전에는 이미지의 연속 OCTG 선을 재현하지 않습니다.</p><details><summary>OCTG·열연 관측값과 출처 펼치기</summary>'+valueTable(octg,sources)+valueTable(hrb,sources)+'</details></section>';
  }
  function capacityHTML(co){
    var c=co.capacity;if(!c||typeof c!=='object')return '';
    var total=finite(c.annual_tonnes)?c.annual_tonnes:null,rows=Array.isArray(c.components)?c.components:[];
    var q=finite(c.baseline_annualized_q_tonnes)?c.baseline_annualized_q_tonnes:null,max=Math.max(total||0,q||0);
    var h='<div class="ast-assumptions"><strong>CAPA · '+(total!==null?esc(fmt(total))+' 톤/년':'제조능력 합계 미확인')+'</strong><p class="ast-note">'+esc(c.basis||'')+(c.as_of||c.period?' · 기준 '+esc(c.as_of||c.period):'')+'</p>';
    if(max>0)h+='<div class="ast-capacity" role="img" aria-label="'+esc('연간 제조능력 '+fmt(total)+' 톤, 기준 분기 Q 연율 '+fmt(q)+' 톤')+'">'+[{label:'연간 제조능력',value:total,cls:''},{label:'기준 분기 Q × 4 · 연율',value:q,cls:' q'}].map(function(r){return '<div class="ast-capacity-row"><div><span>'+esc(r.label)+'</span><b>'+esc(fmt(r.value))+' 톤</b></div><div class="ast-capacity-track'+r.cls+'">'+(r.value!==null?'<i style="width:'+Math.max(0,r.value/max*100).toFixed(2)+'%"></i>':'')+'</div></div>';}).join('')+'</div>';
    h+='<p class="ast-note">'+esc(c.comparison_note||'두 값의 제품·연결 범위를 확인해야 합니다. 연율 Q는 가동률을 의미하지 않습니다.')+'</p><p class="ast-note">설비능력 스냅샷입니다. 과거 CAPA 시계열이 없으면 같은 값을 이전 분기로 늘려 그리지 않습니다. 제조·열처리·후공정은 원문 범위대로 구분합니다.</p>';
    if(rows.length)h+='<details><summary>CAPA 설비별 내역·범위</summary><div class="ast-table-wrap" tabindex="0" role="region" aria-label="CAPA 구성"><table><thead><tr><th>설비·범위</th><th>톤/년</th><th>성격</th><th>비고·근거</th></tr></thead><tbody>'+rows.map(function(r){return '<tr><th scope="row">'+esc(r.name||r.label||r.scope||r.id||'설비')+'</th><td>'+esc(fmt(finite(r.annual_tonnes)?r.annual_tonnes:r.value))+'</td><td>'+esc(r.kind||r.type||r.basis||'미확인')+'</td><td class="ast-text">'+esc(r.note||'')+(r.source_url?' · '+link(r.source_url,'원문'):'')+'</td></tr>';}).join('')+'</tbody></table></div></details>';
    return h+list(c.notes||c.note||co.capacity_notes)+'</div>';
  }

  function methodologyHTML(m){
    if(!m||typeof m!=='object')return '';
    function section(title,rows){return Array.isArray(rows)&&rows.length?'<h4>'+esc(title)+'</h4><div class="ast-insights">'+insights(rows)+'</div>':'';}
    return '<section class="ast-method" data-ast-methodology><h4>'+esc(m.title||'계산 방법과 검증 범위')+'</h4><p class="ast-note">'+esc(m.summary||'')+'</p><details><summary>계산 순서 · 검증 범위 · 남은 자료 공백 펼치기</summary>'+section('계산 순서',m.steps)+section('검증 범위',m.validation)+section('자료 공백',m.gaps)+'</details></section>';
  }
  function approximately(a,b){return finite(a)&&finite(b)&&Math.abs(a-b)<=Math.max(1,Math.abs(a),Math.abs(b))*1e-8;}
  function bridgeGeometry(bridge){
    var rows=bridge&&Array.isArray(bridge.rows)?bridge.rows:[],issues=[],acc=null;
    if(rows.length<2||rows[0].kind!=='total'||rows[rows.length-1].kind!=='total')issues.push('total_endpoints_required');
    var out=rows.map(function(r,i){
      if(!finite(r.value)||['total','change'].indexOf(r.kind)<0){issues.push('invalid_row:'+i);return Object.assign({},r,{start:null,end:null});}
      var start,end;if(r.kind==='total'){start=0;end=r.value;if(i>0&&!approximately(acc,end))issues.push('total_mismatch:'+i);acc=end;}
      else if(!finite(acc)){issues.push('missing_prior_total:'+i);start=null;end=null;}else{start=acc;end=acc+r.value;acc=end;}
      return Object.assign({},r,{start:start,end:end});
    });return {rows:out,issues:issues};
  }
  function svgLabel(label,x,y,width){var n=Math.max(7,Math.floor(width/8)),chunks=String(label||'').match(new RegExp('.{1,'+n+'}','g'))||[''];return '<text x="'+x+'" y="'+y+'" fill="#bdccda" font-size="10">'+chunks.slice(0,2).map(function(t,i){return '<tspan x="'+x+'" dy="'+(i?'12':'0')+'">'+esc(t)+'</tspan>';}).join('')+'</text>';}
  function svgAxis(lo,hi,x,width,top,bottom){var h='';for(var i=0;i<4;i++){var v=lo+(hi-lo)*i/3,xx=x(v);h+='<line x1="'+xx+'" x2="'+xx+'" y1="'+top+'" y2="'+bottom+'" stroke="#273a4b"/><text x="'+xx+'" y="'+(top-8)+'" text-anchor="middle" fill="#a2b2c4" font-size="10">'+esc(fmt(v))+'</text>';}if(lo<=0&&hi>=0)h+='<line data-zero-reference="true" x1="'+x(0)+'" x2="'+x(0)+'" y1="'+top+'" y2="'+bottom+'" stroke="#7c93a8" stroke-dasharray="3 4"/>';return h;}
  function bridgeHTML(bridge,width){
    if(!bridge||!Array.isArray(bridge.rows)||!bridge.rows.length)return '';
    var g=bridgeGeometry(bridge),W=Math.max(280,Math.min(640,width||560)),L=W<380?94:128,R=69,T=34,rowH=44,H=T+g.rows.length*rowH+8;
    var h='<article class="ast-card" data-ast-bridge><h4>영업이익 변화의 구성 · '+esc(bridge.period||'기간 미확인')+'</h4><p class="ast-note">'+esc(bridge.unit||'단위 미확인')+' · 기준 영업이익 + 각 변화 = 비교 분기 기준 추정</p>';
    if(g.issues.length)h+='<div class="ast-model-warning">변화 합계 또는 입력이 일치하지 않아 차트를 보류합니다. 원행은 아래 표에서 확인하세요.</div>';
    else{
      var vals=[0];g.rows.forEach(function(r){vals.push(r.start,r.end);});var lo=Math.min.apply(null,vals),hi=Math.max.apply(null,vals),pad=(hi-lo)*.07||1;lo-=pad;hi+=pad;
      var x=function(v){return L+(v-lo)/(hi-lo)*(W-L-R);};
      h+='<div class="ast-static"><svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+esc('영업이익 변화 '+(bridge.period||'')+' · '+(bridge.unit||''))+'">'+svgAxis(lo,hi,x,W,T,H-8);
      g.rows.forEach(function(r,i){var y=T+i*rowH+8,color=r.kind==='total'?'#76b8ee':r.value>=0?'#64d6b0':'#ee8b82',xa=x(r.start),xb=x(r.end),title=r.label+' · '+fmt(r.value)+' '+(bridge.unit||'')+' · 누적 '+fmt(r.end);
        h+=svgLabel(r.label,0,y+9,L-12);if(i&&r.kind==='change')h+='<line x1="'+xa+'" x2="'+xa+'" y1="'+(y-rowH+20)+'" y2="'+y+'" stroke="#7791a6" stroke-dasharray="2 3"/>';
        h+='<rect data-bridge-kind="'+esc(r.kind)+'" data-start="'+r.start+'" data-end="'+r.end+'" x="'+Math.min(xa,xb)+'" y="'+y+'" width="'+Math.max(1,Math.abs(xb-xa))+'" height="18" fill="'+color+'" opacity=".86" tabindex="0" role="img" aria-label="'+esc(title)+'"><title>'+esc(title)+'</title></rect><text x="'+(W-2)+'" y="'+(y+13)+'" text-anchor="end" fill="'+color+'" font-size="10">'+esc((r.kind==='change'&&r.value>0?'+':'')+fmt(r.value))+'</text>';
      });h+='</svg></div><div class="ast-legend"><span>청색 · 영업이익 수준</span><span>녹색 · 이익 증가</span><span>적색 · 이익 감소</span></div>';
    }
    return h+'<p class="ast-note">'+esc(bridge.note||'')+'</p><details><summary>이익 변화 수치·누적 표</summary><div class="ast-table-wrap" tabindex="0" role="region" aria-label="영업이익 변화 표"><table><thead><tr><th>항목</th><th>성격</th><th>'+esc(bridge.unit||'값')+'</th><th>누적 영업이익</th></tr></thead><tbody>'+g.rows.map(function(r){return '<tr><th scope="row">'+esc(r.label)+'</th><td>'+esc(r.kind==='total'?'수준':'변화')+'</td><td>'+esc(fmt(r.value))+'</td><td>'+esc(fmt(r.end))+'</td></tr>';}).join('')+'</tbody></table></div></details></article>';
  }
  function sensitivityGeometry(s){var rows=s&&Array.isArray(s.rows)?s.rows:[],issues=[],base=rows.length?rows[0].base:null;rows.forEach(function(r,i){if(![r.low,r.base,r.high].every(finite)||r.low>r.base||r.base>r.high)issues.push('invalid_range:'+i);else if(!approximately(base,r.base))issues.push('different_base:'+i);});return {base:base,rows:rows.slice().sort(function(a,b){return (b.high-b.low)-(a.high-a.low);}),issues:issues};}
  function sensitivityHTML(s,width){
    if(!s||!Array.isArray(s.rows)||!s.rows.length)return '';
    var g=sensitivityGeometry(s),W=Math.max(280,Math.min(640,width||560)),L=W<380?105:150,R=18,T=44,rowH=48,H=T+g.rows.length*rowH+8;
    var h='<article class="ast-card" data-ast-sensitivity><h4>한 변수씩 바꾼 영업이익 범위</h4><p class="ast-note">'+esc(s.unit||'단위 미확인')+' · 선은 공통 기준 OP '+esc(fmt(g.base))+' · 범위가 큰 순서 · 합산 금지</p>';
    if(g.issues.length)h+='<div class="ast-model-warning">동일 기준값 또는 범위 조건을 충족하지 않아 공통축 차트를 보류합니다.</div>';
    else{
      var vals=[];g.rows.forEach(function(r){vals.push(r.low,r.high);});var lo=Math.min.apply(null,vals),hi=Math.max.apply(null,vals),pad=(hi-lo)*.07||1;lo-=pad;hi+=pad;var x=function(v){return L+(v-lo)/(hi-lo)*(W-L-R);};
      h+='<div class="ast-static"><svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="한 변수 변경 영업이익 민감도 · '+esc(s.unit||'')+'" data-sensitivity-base="'+g.base+'">'+svgAxis(lo,hi,x,W,T,H-8)+'<line x1="'+x(g.base)+'" x2="'+x(g.base)+'" y1="'+(T-4)+'" y2="'+(H-8)+'" stroke="#e5d7af" stroke-dasharray="4 3"/>';
      g.rows.forEach(function(r,i){var y=T+i*rowH+12,title=r.label+' · 하단 '+fmt(r.low)+' / 기준 '+fmt(r.base)+' / 상단 '+fmt(r.high)+' '+(s.unit||'')+' · '+(r.note||'');h+=svgLabel(r.label,0,y+5,L-12)+'<g tabindex="0" role="img" aria-label="'+esc(title)+'"><title>'+esc(title)+'</title><rect data-sensitivity-low="'+r.low+'" x="'+x(r.low)+'" y="'+y+'" width="'+Math.max(1,x(r.base)-x(r.low))+'" height="13" fill="#ee8b82" fill-opacity=".8"/><rect data-sensitivity-high="'+r.high+'" x="'+x(r.base)+'" y="'+y+'" width="'+Math.max(1,x(r.high)-x(r.base))+'" height="13" fill="#64d6b0" fill-opacity=".8"/><circle cx="'+x(r.base)+'" cy="'+(y+6.5)+'" r="3" fill="#f2ddb1"/></g><text x="'+((L+W-R)/2)+'" y="'+(y+27)+'" text-anchor="middle" fill="#b5c6d5" font-size="10">'+esc(fmt(r.low)+' – '+fmt(r.high))+'</text>';});h+='</svg></div>';
    }
    return h+'<p class="ast-note">'+esc(s.note||'한 변수 변경 결과는 합산할 수 없으며 확률구간이 아닙니다.')+'</p><details><summary>민감도 수치·변경 조건 '+g.rows.length+'개</summary><div class="ast-table-wrap" tabindex="0" role="region" aria-label="민감도 표"><table><thead><tr><th>변경 변수</th><th>하단</th><th>기준</th><th>상단</th><th>조건</th></tr></thead><tbody>'+g.rows.map(function(r){return '<tr><th scope="row">'+esc(r.label)+'</th><td>'+esc(fmt(r.low))+'</td><td>'+esc(fmt(r.base))+'</td><td>'+esc(fmt(r.high))+'</td><td class="ast-text">'+esc(r.note||'')+'</td></tr>';}).join('')+'</tbody></table></div></details></article>';
  }
  function validationHTML(v){return v&&typeof v==='object'?'<aside class="ast-validation" data-ast-validation><strong>'+esc(v.title||'검증 범위')+'</strong><p class="ast-note">'+esc(v.text||'')+'</p></aside>':'';}

  function evidenceHTML(co,state,sources,registry){
    var ss=(co.operating_evidence||[]).map(normalizeSeries);
    if(!ss.length)return '';
    function cards(rows){return '<div class="ast-grid">'+rows.map(function(s,i){return '<article class="ast-card">'+chart(s,{domain:chartDomain([s]),width:state.chartWidth,color:COLORS[(i+1)%COLORS.length]},sources,registry)+'</article>';}).join('')+'</div>';}
    var extra=ss.filter(function(s){return s.display_default===false;});
    return '<section data-ast-operating-evidence><div class="ast-toolbar"><h4>공시로 확인한 생산·단가·재고</h4><span class="ast-model-tag">원표의 기간·범위 유지</span></div><p class="ast-note">생산량은 판매량과 다릅니다. 누적 평균단가는 해당 누적기간의 값이며, 분기 단가로 바꾸거나 전망선에 이어 붙이지 않습니다. 각 차트의 범위와 계산식을 확인하세요.</p>'+cards(ss.filter(function(s){return s.display_default!==false;}))+(extra.length?'<details><summary>내수·수출·해외법인 및 조건부 계산 '+extra.length+'개 펼치기</summary>'+cards(extra)+'</details>':'')+'</section>';
  }
  function evaluationHTML(v,state,sources,registry){
    if(!v||v.status!=='descriptive_latest_vintage')return '';
    var ms=v.metrics||[],ss=(v.series||[]).map(normalizeSeries);
    var groups={};ss.forEach(function(s){var key=s.id.indexOf('_operating_profit_')>=0?'영업이익':'매출';(groups[key]||(groups[key]=[])).push(s);});
    return '<section data-ast-evaluation><div class="ast-toolbar"><h4>'+esc(v.title||'단순 기준선과 과거 실적 비교')+'</h4></div><p class="ast-model-warning">'+esc(v.note||'현재 공시 빈티지로 재계산한 단순 기준선 오차입니다. 본 전망 모델의 예측 성과가 아닙니다.')+'</p><div class="ast-grid">'+Object.keys(groups).map(function(k){return comparisonHTML(k,groups[k],state);}).join('')+'</div><div class="ast-kpis">'+ms.map(function(m){return '<article class="ast-kpi"><span class="ast-kpi-label">'+esc(m.label)+'</span><b class="ast-kpi-value">'+esc(fmt(m.value))+' <small>'+esc(m.unit)+'</small></b><small>비교 '+esc(m.n)+'분기'+(m.period_start?' · '+esc(m.period_start)+'~'+esc(m.period_end):'')+'</small><p class="ast-note">'+esc(m.note||'')+'</p></article>';}).join('')+'</div>'+(ss.length?'<details><summary>기준선·실적 수치와 원문 '+ss.length+'개 계열</summary>'+ss.map(function(s){return valueTable(s,sources);}).join('')+'</details>':'')+'<div class="ast-insights">'+insights(v.gates||[])+'</div></section>';
  }
  function comparisonHTML(title,ss,state){
    var domain=chartDomain(ss),values=[];ss.forEach(function(s){s.points.forEach(function(p){if(finite(p.value))values.push(p.value);});});
    if(!domain||!values.length)return '';
    var W=Math.max(260,Math.min(800,state.chartWidth||560)),H=220,L=58,R=22,T=20,B=34;
    var lo=Math.min(0,Math.min.apply(null,values)),hi=Math.max(0,Math.max.apply(null,values));
    var pad=(hi-lo)*.08||1;hi+=pad;if(lo<0)lo-=pad;
    var x=function(t){return L+(t-domain[0])/(domain[1]-domain[0])*(W-L-R);};
    var y=function(v){return T+(hi-v)/(hi-lo)*(H-T-B);};
    var svg='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+esc(title+' 실적과 두 단순 기준선 · '+ss[0].unit)+'">';
    for(var i=0;i<=4;i++){var v=lo+(hi-lo)*i/4;svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y(v)+'" y2="'+y(v)+'" stroke="#263749"/><text x="'+(L-8)+'" y="'+(y(v)+4)+'" text-anchor="end" fill="#a2b2c4" font-size="11">'+esc(fmt(v))+'</text>';}
    var tx=ticks(domain,true);if(W<380&&tx.length>4)tx=tx.filter(function(_,i){return i%2===0;});
    tx.forEach(function(t){svg+='<text x="'+x(t.time)+'" y="'+(H-10)+'" text-anchor="middle" fill="#a2b2c4" font-size="11">'+esc(t.label)+'</text>';});
    ss.forEach(function(s,i){var color=COLORS[i%COLORS.length],actual=s.id.indexOf('_actual_')>=0;
      lineSegments(s).forEach(function(seg){svg+='<path data-ast-comparison-line="'+esc(s.id)+'" d="M'+x(seg.a.time)+','+y(seg.a.value)+' L'+x(seg.b.time)+','+y(seg.b.value)+'" fill="none" stroke="'+color+'" stroke-width="2.2"'+(!actual?' stroke-dasharray="5 4"':'')+'/>';});
      s.points.forEach(function(p){if(finite(p.value))svg+='<circle cx="'+x(p.time)+'" cy="'+y(p.value)+'" r="3" fill="'+(actual?color:'#111721')+'" stroke="'+color+'" stroke-width="1.5"><title>'+esc(pointText(p,s))+'</title></circle>';});
    });
    svg+='</svg>';
    return '<article class="ast-card"><h4>'+esc(title)+' · 실적과 기준선</h4><div class="ast-unit">'+esc(ss[0].unit)+' · 동일 세로축</div>'+svg+'<div class="ast-legend">'+ss.map(function(s,i){return '<span><i class="ast-swatch '+(s.id.indexOf('_actual_')<0?'dashed':'')+'" style="border-color:'+COLORS[i%COLORS.length]+'"></i>'+esc(s.name)+'</span>';}).join('')+'</div><p class="ast-note">실선은 공시 기반 실적, 점선은 과거 단순 기준선입니다. 현재 전망 모델의 예측 성적이 아닙니다. 각 점에 마우스를 올리면 원값을 확인할 수 있습니다.</p></article>';
  }
  var PANELS=[{title:'탄소강관 가격 · 월간·분기 변화',note:'같은 BLS 지수의 수준·MoM·YoY·QoQ. 누락된 달과 미완성 분기는 계산에서 제외합니다. 2026-09-10 수정본이며 잠정치가 포함됩니다.',ids:['carbon_pipe_ppi','carbon_pipe_ppi_mom_pct','carbon_pipe_ppi_yoy_pct','carbon_pipe_ppi_qoq_pct']},{title:'유가와 미국 원유 리그',note:'가격과 가동 리그의 관측일을 같은 가로축으로 비교합니다. 선행·후행은 인과관계의 증명이 아닙니다.',ids:['wti_spot','us_oil_rigs']},{title:'천연가스와 미국 가스 리그',note:'Henry Hub 가격과 미국 가스 리그. 서로 다른 세로축 단위를 확인하세요.',ids:['henry_hub_spot','us_gas_rigs']},{title:'강관 가격과 원가 관련 지수',note:'OCTG와 HRC는 제품·인도조건·단위가 일치할 때만 차액을 비교할 수 있습니다. 강관·고철 PPI는 가격지수이며 USD/톤 또는 HRC 실가격을 대신하지 않습니다.',ids:['octg_p110_55_fob_user','hrc','hrc_spot','hrc_midwest','octg_hrc_spread','steel_scrap_ppi','steel_pipe_ppi']},{title:'열연·스크랩 원가 관측',note:'열연은 USD/net ton(미국 short ton), 스크랩은 USD/gross ton 기준입니다. 중량·품질·거래조건이 달라 직접 차감하거나 같은 값 축에 합치지 않습니다. 각 지표는 독립 세로축입니다.',ids:['steelbenchmarker_us_hrb_net_ton','steelbenchmarker_us_shredded_scrap','steelbenchmarker_us_busheling_scrap']},{title:'미완결 유정과 시추·완결·프랙',note:'DUC는 잔량(stock), 시추·완결은 기간 내 흐름(flow), Frac Spread는 가동 펌핑팀 지표입니다. 합산하지 않습니다. Frac 공개 뉴스는 집계 주말이 미확인이라 게시일 위치의 점만 표시합니다.',ids:['duc_stock','new_wells_drilled','new_wells_completed','us_frac_spread_public_news']}];
  function latestSeriesPoint(payload,id){
    var row=((payload.market||{}).series||[]).filter(function(s){return s.id===id;})[0];
    if(!row)return null;var pts=normalizeSeries(row).points.filter(function(p){return finite(p.value);});return pts.length?pts[pts.length-1]:null;
  }
  function changeLabel(payload,id){
    var row=((payload.market||{}).series||[]).filter(function(s){return s.id===id;})[0];
    if(!row)return '이전 관측 미확인';var pts=normalizeSeries(row).points.filter(function(p){return finite(p.value);});
    if(pts.length<2)return '이전 관측 미확인';var d=pts[pts.length-1].value-pts[pts.length-2].value;return (d>0?'+':'')+fmt(d)+' 전 관측 대비';
  }
  function marketSnapshotHTML(payload){
    var oil=latestSeriesPoint(payload,'us_oil_rigs'),gas=latestSeriesPoint(payload,'us_gas_rigs'),octg=latestSeriesPoint(payload,'octg_p110_55_fob_user'),duc=latestSeriesPoint(payload,'duc_stock');
    function kpi(label,p,unit,note){return '<article class="ast-kpi"><span class="ast-kpi-label">'+esc(label)+'</span><b class="ast-kpi-value">'+esc(fmt(p&&p.value))+' <small>'+esc(unit)+'</small></b><small>'+esc(p?p.period:'미확인')+' · '+esc(note)+'</small></article>';}
    var read=(oil&&gas&&octg)?'리그는 원유 중심으로 반등했지만, 가스는 둔화했습니다. OCTG 기준점은 강보합이라는 사용자 제시 관측입니다. Q 개선 가설은 시추·완결·DUC와 함께 확인하고, P는 단일 현물점으로 확정하지 않습니다.':'공개·사용자 제시 관측 중 일부가 없어 변곡점 판단을 보류합니다.';
    return '<section data-ast-market-snapshot><div class="ast-toolbar"><h4>북미 OCTG 업황 현황</h4><span class="ast-model-tag">관측 기준 '+esc((oil&&oil.period)||(gas&&gas.period)||(octg&&octg.period)||'미확인')+'</span></div><div class="ast-kpis">'+kpi('미국 원유 리그',oil,'개',changeLabel(payload,'us_oil_rigs'))+kpi('미국 천연가스 리그',gas,'개',changeLabel(payload,'us_gas_rigs'))+kpi('OCTG P110 5.5인치 FOB',octg,'USD/short ton',octg&&octg.status==='user_reported'?'사용자 제시 · 미검증':'공개 관측')+kpi('DUC 재고',duc,'개',duc?((duc.status==='estimate'?'원기관 추정 · ':'')+'시추·완결과 분리'):'미확인')+'</div><div class="ast-insights"><article class="ast-insight"><strong>CL Prince 관찰 틀 · 현재 판독</strong><p class="ast-note">'+esc(read)+'</p></article></div></section>';
  }
  function companyOverviewHTML(payload){
    var cs=payload.companies||[];
    if(!cs.length)return '';
    function forecast(co,id){var s=(co.series||[]).filter(function(x){return x.id===id;})[0],n=s&&normalizeSeries(s),p=n&&n.points.filter(function(x){return x.status==='forecast'&&finite(x.value);})[0];return {series:n,point:p};}
    return '<section data-ast-company-overview><div class="ast-toolbar"><h4>회사별 CAPA · Q · P · 분기 손익</h4><span class="ast-model-tag">각 회사의 첫 조건부 추정 분기</span></div><div class="ast-grid">'+cs.map(function(co){var q=forecast(co,'q'),p=forecast(co,'p'),rev=forecast(co,'revenue'),op=forecast(co,'operating_profit'),cap=co.capacity||{},period=(q.point||p.point||rev.point||op.point||{}).period||'미확인';var rscale=rev.series?displayScale(rev.series):{divisor:1,unit:'단위 미확인'},oscale=op.series?displayScale(op.series):{divisor:1,unit:'단위 미확인'};return '<article class="ast-card" data-ast-company-overview-card="'+esc(co.id)+'"><div class="ast-card-head"><h4>'+esc(co.name)+'</h4><button type="button" data-ast-company-select="'+esc(co.id)+'">상세 보기</button></div><div class="ast-unit">'+esc(period)+' · 조건부 추정</div><div class="ast-kpis">'+kpiValue('CAPA',finite(cap.annual_tonnes)?fmt(cap.annual_tonnes/1000):'—','천 톤/년',cap.basis||'범위 확인')+kpiValue('Q',q.point?fmt(q.point.value/1000):'—','천 톤',q.series&&q.series.basis||'판매/출하 범위 확인')+kpiValue('P',p.point?fmt(p.point.value):'—',p.series&&p.series.unit||'단위 미확인',p.series&&p.series.basis||'')+kpiValue('영업이익',op.point?fmt(op.point.value/oscale.divisor):'—',oscale.unit,rev.point?'매출 '+fmt(rev.point.value/rscale.divisor)+' '+rscale.unit:'매출 미확인')+'</div></article>';}).join('')+'</div><p class="ast-note">지주사와 자회사는 중복 합산하지 않습니다. 회사별 제품·지역·판매량 범위가 달라 Q·P를 단순 비교하거나 총합으로 해석할 수 없습니다.</p></section>';
  }
  function kpiValue(label,value,unit,note){return '<div class="ast-kpi"><span class="ast-kpi-label">'+esc(label)+'</span><b class="ast-kpi-value">'+esc(value)+'</b><small>'+esc(unit)+(note?' · '+esc(note):'')+'</small></div>';}
  function marketHTML(payload,state,sources,registry) {
    var market=payload.market||{},series=(market.series||[]).filter(function(s){return s.display_default!==false;}).map(normalizeSeries),whole=chartDomain(series),domain=whole;
    if(whole&&state.years)domain=[Math.max(whole[0],Date.UTC(new Date(whole[1]).getUTCFullYear()-state.years,new Date(whole[1]).getUTCMonth(),new Date(whole[1]).getUTCDate())),whole[1]];
    var used=new Set(),panels=PANELS.map(function(p){var rows=series.filter(function(s){return p.ids.indexOf(s.id)>=0;});rows.forEach(function(s){used.add(s.id);});return Object.assign({},p,{rows:rows});});
    var extra=series.filter(function(s){return !used.has(s.id);});if(extra.length)panels.push({title:'추가 공개 시장 시계열',note:'원천의 단위와 범위를 유지합니다.',rows:extra});
    return '<div class="ast-toolbar"><h4>01 · 시장의 순서와 변곡점</h4><div class="ast-range" aria-label="시장 차트 기간">'+[2,5,0].map(function(n){return '<button type="button" data-ast-years="'+n+'" aria-pressed="'+(state.years===n)+'">'+(n?n+'년':'전체')+'</button>';}).join('')+'</div></div><div class="ast-grid">'+panels.map(function(p,i){return '<article class="ast-card"><div class="ast-card-head"><h4>'+esc(p.title)+'</h4><span class="ast-card-no">'+String(i+1).padStart(2,'0')+'</span></div><p class="ast-note">'+esc(p.note)+'</p>'+(p.rows.length?p.rows.map(function(s,j){return chart(s,{domain:domain,width:state.chartWidth,zeroAxis:false,color:COLORS[j%COLORS.length]},sources,registry);}).join(''):'<div class="ast-empty">공개 시계열 확보 대기. 확인되지 않은 값을 채우지 않습니다.</div>')+'</article>';}).join('')+'</div><div class="ast-insights">'+insights(market.findings)+'</div>'+(strings(market.limitations).length?'<details><summary>시장 자료의 비교 한계</summary>'+list(market.limitations)+'</details>':'');
  }
  function companyHTML(payload,state,sources,registry) {
    var cs=payload.companies||[],co=cs.find(function(c){return c.id===state.companyId;})||cs[0];
    if(!co)return '<section class="ast-company"><h4>02 · 회사별 분기 전망</h4><div class="ast-empty">회사별 비교 가능한 실적·조건부 모델이 아직 제공되지 않았습니다.</div></section>';
    var order=['revenue','operating_profit','q','p','utilization'];
    var ss=(co.series||[]).map(normalizeSeries).sort(function(a,b){var ai=order.indexOf(a.id),bi=order.indexOf(b.id);return (ai<0?99:ai)-(bi<0?99:bi);}),domain=chartDomain(ss),notes=strings(co.limitations);
    var html='<section class="ast-company">'+companyOverviewHTML(payload)+'<div class="ast-toolbar"><h4>02 · 회사별 분기 경로</h4><label class="ast-company-select">회사 <select data-ast-company>'+cs.map(function(c){return '<option value="'+esc(c.id)+'"'+(c.id===co.id?' selected':'')+'>'+esc(c.name)+(c.ticker?' · '+esc(c.ticker):'')+'</option>';}).join('')+'</select></label><span class="ast-model-tag">조건부 추정 · 검증 전 가정</span></div><div class="ast-company-intro"><strong>'+esc(co.name)+'</strong><p class="ast-note">'+esc(co.scope||co.scope_note||co.basis||'')+'</p><p class="ast-note">실선: 공시 실적 · 점선: 조건부 기준 추정 · 음영: 하단–상단 가정 범위. 확률·신뢰구간 또는 증권사 컨센서스가 아닙니다.</p></div>';
    html+='<div class="ast-kpis">'+ss.filter(function(s){return s.id==='revenue'||s.id==='operating_profit';}).map(function(s){var p=s.points.filter(function(p){return p.status==='forecast'&&finite(p.value);})[0],scale=displayScale(s);return '<div class="ast-kpi"><span class="ast-kpi-label">'+esc(s.name)+' · '+(p?esc(p.period):'미확인')+' 기준 추정</span><b class="ast-kpi-value">'+esc(fmt(p?p.value/scale.divisor:null))+'</b><small>'+esc(scale.unit)+(p?' · 하단 '+esc(fmt(p.low===null?null:p.low/scale.divisor))+' – 상단 '+esc(fmt(p.high===null?null:p.high/scale.divisor)):'')+'</small></div>';}).join('')+'</div>';
    html+=validationHTML(co.validation);
    html+='<div class="ast-grid ast-breakdown">'+bridgeHTML(co.bridge,state.chartWidth)+sensitivityHTML(co.sensitivity,state.chartWidth)+'</div>';
    html+=capacityHTML(co);
    html+='<div class="ast-grid">'+ss.map(function(s,i){return '<article class="ast-card">'+chart(s,{domain:domain,width:state.chartWidth,color:COLORS[i%COLORS.length]},sources,registry)+'</article>';}).join('')+'</div>';
    if(!ss.length)html+='<div class="ast-empty">동일 범위의 분기 실적 또는 추정 기준값이 미확인입니다. 미확인 구간을 0으로 표시하지 않습니다.</div>';
    html+=evidenceHTML(co,state,sources,registry);
    html+=evaluationHTML(co.evaluation,state,sources,registry);
    if(co.wind_bridge&&Array.isArray(co.wind_bridge.points))html+='<article class="ast-card" style="margin-top:14px"><strong>Wind 추가 민감도 · 위 영업이익에 미포함</strong>'+chart(normalizeSeries(Object.assign({id:'wind_bridge',frequency:'quarterly'},co.wind_bridge)),{domain:domain,width:Math.min(800,state.chartWidth||560),color:COLORS[5]},sources,registry)+'<p class="ast-note">'+esc(co.wind_bridge.note||'별도 민감도이며 기존 영업이익에 합산하지 않습니다.')+'</p>'+list(co.wind_bridge.assumptions&&co.wind_bridge.assumptions.note)+'</article>';
    html+='<div class="ast-assumptions"><strong>가정과 범위</strong>'+list(co.assumptions)+(co.formula?'<p class="ast-note">'+esc(co.formula)+'</p>':'')+(notes.length?list(notes):'')+'</div><div class="ast-insights">'+insights(co.findings||co.interpretation)+'</div>';
    if(co.sources&&co.sources.length)html+='<details><summary>회사 공시·모델 근거 '+co.sources.length+'개</summary>'+sourceList(co.sources)+'</details>';
    return html+'</section>';
  }
  function driversHTML(payload,state,sources,registry){var rows=(payload.driver_series||[]).map(normalizeSeries);if(!rows.length)return '';var domain=chartDomain(rows);return '<details><summary>분기 추정의 시장 입력·가정 '+rows.length+'개</summary><p class="ast-note">시장 실측에 가중치·기준값·전가율을 적용한 분석 가정입니다. 지수 경로와 회사별 적용 범위는 별도로 확인해야 합니다.</p><div class="ast-grid">'+rows.map(function(s,i){return '<article class="ast-card">'+chart(s,{domain:domain,width:state.chartWidth,color:COLORS[i%COLORS.length]},sources,registry)+'</article>';}).join('')+'</div></details>';}
  function bindCharts(host,registry) {
    host.querySelectorAll('[data-ast-chart]').forEach(function(el){var key=+el.dataset.astChart,r=registry[key],good=r.series.points.filter(function(p){return finite(p.value);}),at=good.length-1,tip=host.querySelector('[data-ast-tip="'+key+'"]'),cursor=el.querySelector('.ast-cursor');
      function show(i){at=Math.max(0,Math.min(good.length-1,i));var p=good[at];tip.textContent=pointText(p,r.series);var x=r.left+(p.time-r.domain[0])/(r.domain[1]-r.domain[0])*(r.width-r.left-r.right);cursor.setAttribute('x1',x);cursor.setAttribute('x2',x);cursor.setAttribute('visibility','visible');}
      el.addEventListener('pointermove',function(e){var box=el.getBoundingClientRect(),x=(e.clientX-box.left)/box.width*r.width,t=r.domain[0]+(x-r.left)/(r.width-r.left-r.right)*(r.domain[1]-r.domain[0]),lo=0,hi=good.length-1;while(lo<hi){var mid=Math.floor((lo+hi)/2);if(good[mid].time<t)lo=mid+1;else hi=mid;}var idx=lo;if(idx>0&&Math.abs(good[idx-1].time-t)<Math.abs(good[idx].time-t))idx--;show(idx);});
      el.addEventListener('keydown',function(e){if(e.key==='ArrowLeft'||e.key==='ArrowRight'||e.key==='Home'||e.key==='End'){e.preventDefault();show(e.key==='Home'?0:e.key==='End'?good.length-1:at+(e.key==='ArrowLeft'?-1:1));}});
      el.addEventListener('pointerleave',function(){cursor.setAttribute('visibility','hidden');});
    });
  }
  function mount(host,payload) {
    if(!host||!host.ownerDocument)return null;
    var doc=host.ownerDocument;if(!doc.getElementById('ast-style')){var st=doc.createElement('style');st.id='ast-style';st.textContent=CSS;(doc.head||doc.documentElement).appendChild(st);}
    if(typeof host._astCleanup==='function')host._astCleanup();
    payload=payload||{};var state={years:5,companyId:(payload.companies||[])[0]&&payload.companies[0].id},sources=sourceMap(payload);
    function measure(){var w=host.clientWidth||600;return Math.round(Math.max(260,Math.min(640,w<=800?w-30:(w-14)/2-36)));}
    state.chartWidth=measure();
    function render(){var registry=[];host.innerHTML='<div class="ast-root"><header class="ast-hero"><div class="ast-eyebrow">ARGUS / STEEL RESEARCH</div><h3>에너지 수요 → 강관 수익 경로</h3><p class="ast-scope">시장 관측과 회사 공시를 분리해 연결합니다. '+(payload.as_of?'자료 확인 '+esc(payload.as_of):'')+'</p><p class="ast-note">가격·리그·시추·완결의 시차를 살피고, CAPA·출하량(Q)·단가(P)가 매출과 이익에 미치는 조건을 비교하세요. 각 점의 관측일과 출처는 수치 표에 표시합니다.</p><div class="ast-range" style="margin-top:12px"><button type="button" data-ast-jump="company">회사별 분기 전망 ↓</button><button type="button" data-ast-jump="lens">변곡점 해석 ↓</button></div></header>'+marketSnapshotHTML(payload)+methodologyHTML(payload.methodology)+'<div data-ast-market>'+marketHTML(payload,state,sources,registry)+'</div><div data-ast-company-panel>'+companyHTML(payload,state,sources,registry)+'</div>'+driversHTML(payload,state,sources,registry)+lensHTML(payload.interpretation,payload.persona)+'<details><summary>시장·공통 출처와 자료 범위</summary>'+sourceList([].concat(payload.sources||[],payload.market&&payload.market.sources||[]))+list(payload.limitations)+'</details></div>';bindCharts(host,registry);
      host.querySelectorAll('[data-ast-jump]').forEach(function(btn){btn.addEventListener('click',function(){var target=btn.dataset.astJump==='company'?host.querySelector('.ast-company'):host.querySelector('[data-ast-lens]');if(target)target.scrollIntoView({block:'start'});});});
      host.querySelectorAll('[data-ast-years]').forEach(function(btn){btn.addEventListener('click',function(){state.years=+btn.dataset.astYears;render();var active=host.querySelector('[data-ast-years="'+state.years+'"]');if(active)active.focus({preventScroll:true});});});
      function selectCompany(id,focus){if(!(payload.companies||[]).some(function(c){return c.id===id;}))return;state.companyId=id;render();var next=host.querySelector('[data-ast-company]');if(focus&&next)next.focus({preventScroll:true});if(typeof host.dispatchEvent==='function'&&doc.defaultView)host.dispatchEvent(new doc.defaultView.CustomEvent('phx-steel-company',{bubbles:true,detail:{companyId:state.companyId}}));}
      var select=host.querySelector('[data-ast-company]');if(select)select.addEventListener('change',function(){selectCompany(select.value,true);});
      host.querySelectorAll('[data-ast-company-select]').forEach(function(btn){btn.addEventListener('click',function(){selectCompany(btn.dataset.astCompanySelect,true);var target=host.querySelector('.ast-company-intro');if(target)target.scrollIntoView({block:'start'});});});
    }
    render();var observer=null,frame=null;if(doc.defaultView&&doc.defaultView.ResizeObserver){observer=new doc.defaultView.ResizeObserver(function(){if(frame!==null)return;frame=doc.defaultView.requestAnimationFrame(function(){frame=null;var w=measure();if(w!==state.chartWidth){state.chartWidth=w;render();}});});observer.observe(host);}host._astCleanup=function(){if(observer)observer.disconnect();if(frame!==null&&doc.defaultView)doc.defaultView.cancelAnimationFrame(frame);};
    return {setCompany:function(id){if((payload.companies||[]).some(function(c){return c.id===id;})){state.companyId=id;render();}},getState:function(){return Object.assign({},state);},destroy:host._astCleanup};
  }
  function mountLens(host,items,persona){if(!host||!host.ownerDocument)return;var doc=host.ownerDocument;if(!doc.getElementById('ast-style')){var st=doc.createElement('style');st.id='ast-style';st.textContent=CSS;(doc.head||doc.documentElement).appendChild(st);}host.innerHTML='<div class="ast-root">'+lensHTML(items,persona)+'</div>';}
  return {mount:mount,mountLens:mountLens,normalizeSeries:normalizeSeries,periodInfo:periodInfo,lineSegments:lineSegments,continuous:continuous,chartDomain:chartDomain,ticks:ticks,safeURL:safeURL,escape:esc,format:fmt,displayScale:displayScale,chart:chart,marketSnapshotHTML:marketSnapshotHTML,companyOverviewHTML:companyOverviewHTML,marketHTML:marketHTML,companyHTML:companyHTML,sourceList:sourceList,lensHTML:lensHTML,priceReferenceHTML:priceReferenceHTML,capacityHTML:capacityHTML,methodologyHTML:methodologyHTML,bridgeGeometry:bridgeGeometry,bridgeHTML:bridgeHTML,sensitivityGeometry:sensitivityGeometry,sensitivityHTML:sensitivityHTML,validationHTML:validationHTML,evidenceHTML:evidenceHTML,evaluationHTML:evaluationHTML,CSS:CSS};
}));
