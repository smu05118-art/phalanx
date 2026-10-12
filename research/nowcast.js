/* Phalanx 리서치 — 세관 프록시 분기 나우캐스트 공용 엔진
   각 research/<id>/index.html이 manifest.js·data_jp.js·data_jp_country.js(크론 산출물)와 이 파일을 로드하고,
   같은 폴더의 inputs.json(가이던스·컨센·예측 로그·시차·결산월)만 수동으로 관리한다. 단위: 억엔. */
(function(){
'use strict';
const $=id=>document.getElementById(id), css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const f1=x=>x==null||isNaN(x)?'—':(Math.round(x*10)/10).toLocaleString('ko-KR',{maximumFractionDigits:1});
const pc=x=>x==null||isNaN(x)||!isFinite(x)?'—':(x>0?'+':'')+(Math.round(x*1000)/10)+'%';
const pm=x=>pc(x).replace('+','');
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function fail(msg){ $('app').innerHTML='<p class="err">'+esc(msg)+'</p>'; $('stamp').textContent='로딩 실패'; }
fetch('inputs.json',{cache:'no-store'}).then(r=>{ if(!r.ok) throw new Error('inputs.json '+r.status); return r.json(); })
.then(run).catch(e=>fail('데이터를 불러오지 못했습니다: '+e.message));

function qOf(ym){ return +ym.slice(0,4)+'Q'+Math.ceil(+ym.slice(5,7)/3); }
function qMonths(q){ const y=+q.slice(0,4), n=+q.slice(5); return [0,1,2].map(k=>y+'-'+String(3*n-2+k).padStart(2,'0')); }
function qAdd(q,d){ let y=+q.slice(0,4), n=+q.slice(5)+d; while(n>4){n-=4;y++;} while(n<1){n+=4;y--;} return y+'Q'+n; }
function kv(k,v){ return '<div class="kv"><span class="k">'+k+'</span><span class="v num">'+v+'</span></div>'; }

function run(IN){
  const PMv=(typeof PM!=='undefined')?PM:null, JP=(window.PSH||{}).JP, JPC=(window.PSHC||{}).JP;
  if(!PMv||!JP) return fail('manifest.js 또는 data_jp.js가 없습니다.');
  const lag=IN.lag||0, fyStart=((IN.fy_end_month||12)%12)+1;
  const months=PMv.months, idx={}; months.forEach((m,i)=>idx[m]=i);
  const co=JP.companies.find(c=>c.id===IN.company); if(!co) return fail('data_jp.js에 '+IN.company+' 카드가 없습니다.');
  const C=JPC&&JPC.country&&JPC.country[co.core_set];
  const ports=(IN.ports&&IN.ports.length)?IN.ports:(co.main_ports||[]);
  const px={};
  if(IN.ports&&IN.ports.length){            /* 항만 부분집합: 국가별 shard를 항만×국가 합산해 재구성 */
    if(!C) return fail('항만 지정(ports)에는 data_jp_country.js가 필요합니다.');
    months.forEach((m,i)=>{ let v=0; ports.forEach(p=>C.order.forEach(ct=>{ v+=(((C.loc[p]||{})[ct]||[])[i]||0); })); if(v) px[m]=v/1e5; });
  } else months.forEach((m,i)=>{ const v=co.revenue[i]; if(v) px[m]=v/1e5; });
  const pxMonths=Object.keys(px).sort(), lastPx=pxMonths[pxMonths.length-1];
  const fin={}; (JP.fin[IN.company]||{q:[]}).q.forEach(([ym,r,o])=>{ fin[qOf(ym)]={rev:r/1e5,op:o/1e5}; });
  const finQs=Object.keys(fin).sort(), lastQ=finQs[finQs.length-1];
  const qSum=q=>{ const ms=qMonths(q); return ms.some(m=>px[m]==null)?null:ms.reduce((a,m)=>a+px[m],0); };
  // OLS: 매출(q) ~ 프록시(q−lag)
  const pts=finQs.filter(q=>q>='2021Q2'&&qSum(qAdd(q,-lag))!=null).map(q=>({q,x:qSum(qAdd(q,-lag)),y:fin[q].rev}));
  const n=pts.length, mx=pts.reduce((a,p)=>a+p.x,0)/n, my=pts.reduce((a,p)=>a+p.y,0)/n;
  const sxy=pts.reduce((a,p)=>a+(p.x-mx)*(p.y-my),0), sxx=pts.reduce((a,p)=>a+(p.x-mx)**2,0), syy=pts.reduce((a,p)=>a+(p.y-my)**2,0);
  const b=sxy/sxx, a=my-b*mx, r=sxy/Math.sqrt(sxx*syy), fit=x=>a+b*x, xMax=Math.max(...pts.map(p=>p.x));
  pts.forEach(p=>p.res=p.y/fit(p.x)-1);
  function shareOf(m){ const mm=m.slice(5), y=+m.slice(0,4), ss=[]; for(let k=1;k<=5;k++){ const s=qSum(qOf((y-k)+'-'+mm)); if(s) ss.push(px[(y-k)+'-'+mm]/s); } return ss; }
  const avg3=v=>{ const s=v.slice(0,3); return s.reduce((x,y)=>x+y,0)/s.length; };
  function priorFiscal(T){ const out=[]; if(+qMonths(T)[0].slice(5)===fyStart) return out;
    for(let k=1;k<=3;k++){ const q=qAdd(T,-k); out.push(q); if(+qMonths(q)[0].slice(5)===fyStart) break; } return out; }
  const L=(IN.forecast_log||[]).find(f=>f.q===lastQ);
  const beat=(L&&L.implied_rev&&fin[lastQ])?(fin[lastQ].op/fin[lastQ].rev - L.implied_op/L.implied_rev):null;
  // 목표 분기들: 다음 분기 + (시차가 있으면) 그다음 분기
  const targets=[];
  for(let k=1;k<=1+lag;k++){
    const T=qAdd(lastQ,k), P=qAdd(T,-lag), Pm=qMonths(P), seen=Pm.filter(m=>px[m]!=null), miss=Pm.filter(m=>px[m]==null);
    if(!seen.length) continue;
    const seenSum=seen.reduce((s,m)=>s+px[m],0);
    const fill=pick=>{ if(!miss.length) return seenSum; const t=miss.map(m=>pick(shareOf(m))).reduce((x,y)=>x+y,0); return seenSum/(1-t); };
    const scen={ bear:miss.reduce((s,m)=>s+(px[(+m.slice(0,4)-1)+m.slice(4)]||0),seenSum), base:fill(avg3), bull:fill(v=>Math.max(...v.slice(0,5))) };
    if(!miss.length){ const sd=Math.sqrt(pts.reduce((s,p)=>s+p.res**2,0)/n); scen.bear=scen.base; scen.bull=scen.base; scen._sd=sd; }
    const sameQ=pts.filter(p=>p.q.slice(5)===T.slice(5)), use=sameQ.filter(p=>!(IN.resid_exclude||[]).includes(p.q)).slice(-3);
    const resMean=use.length?use.reduce((s,p)=>s+p.res,0)/use.length:0;
    const resMin=use.length?Math.min(...use.map(p=>p.res)):0, resMax=sameQ.length?Math.max(...sameQ.map(p=>p.res)):0;
    // 회사 암시 (회계연도 누계 가이던스 − 같은 회계연도 직전 실적)
    const G=(IN.guidance||[]).filter(g=>g.through===T).sort((x,y)=>x.date<y.date?-1:1).pop();
    const prior=priorFiscal(T), have=prior.every(q=>fin[q]);
    let impl=null;
    if(G&&have){ impl={rev:G.rev-prior.reduce((s,q)=>s+fin[q].rev,0), op:G.op-prior.reduce((s,q)=>s+fin[q].op,0), label:G.label||''}; impl.opm=impl.op/impl.rev; }
    const lastOpm=fin[lastQ].op/fin[lastQ].rev;
    const opmBase=impl?impl.opm+(beat||0):lastOpm;
    const opm={bear:impl?(impl.opm+opmBase)/2:opmBase-0.03, base:opmBase, bull:opmBase+0.02};
    const est={};
    ['bear','base','bull'].forEach(kk=>{ let rres=kk==='bear'?resMin:kk==='base'?resMean:resMax;
      const rev=fit(scen[kk])*(1+rres); est[kk]={px:scen[kk],pyoy:qSum(qAdd(P,-4))?scen[kk]/qSum(qAdd(P,-4))-1:null,ols:fit(scen[kk]),res:rres,rev,op:rev*opm[kk],opm:opm[kk]}; });
    targets.push({T,P,seen,miss,seenSum,est,impl,use,ly:fin[qAdd(T,-4)],extrap:scen.base>xMax*1.05});
  }
  const lastGdate=(IN.guidance||[]).map(g=>g.date).sort().pop()||'', gStale=lastGdate.slice(0,7)<=qMonths(lastQ)[2];
  $('stamp').innerHTML='세관 '+esc(lastPx)+'까지 · 실적 '+esc(lastQ)+'까지 · 빌드 '+esc(PMv.built||PMv.updated||'')+' <span class="badge live">LIVE</span>';
  if(!targets.length) return fail('목표 분기의 세관 데이터가 아직 없습니다.');
  let h='';
  const T0=targets[0], B=T0.est.base;
  h+='<div class="hero"><div><div class="eyebrow">'+esc(T0.T)+' 매출분기 추정 (Base) · 프록시 '+esc(T0.P)+(lag?' (시차 '+lag+'분기)':'')+' · 세관 '+T0.seen.length+'/3개월 실측</div>';
  h+='<div class="big"><div><div class="v num">'+f1(B.rev)+'<span style="font-size:17px;color:var(--ink2)"> 억엔</span></div><div class="d">매출 · <span class="up">'+pc(T0.ly?B.rev/T0.ly.rev-1:null)+' YoY</span> · QoQ '+pc(B.rev/fin[lastQ].rev-1)+'</div></div>';
  h+='<div><div class="v num">'+f1(B.op)+'<span style="font-size:17px;color:var(--ink2)"> 억엔</span></div><div class="d">영업이익 · OPM '+pm(B.opm)+(T0.ly?' · <span class="up">'+pc(B.op/T0.ly.op-1)+' YoY</span>':'')+'</div></div></div>';
  h+='<p class="sub" style="margin-top:10px">세관 '+esc(T0.seen.map(m=>m.slice(2)).join('·'))+' 합 '+f1(T0.seenSum)+'억'+(T0.miss.length?' + '+esc(T0.miss.map(m=>m.slice(2)).join('·'))+' 보간':'')+' → 분기 프록시 '+f1(B.px)+'억('+pc(B.pyoy)+' YoY) → OLS '+f1(B.ols)+'억 × (1'+(B.res<0?'−':'+')+Math.abs(Math.round(B.res*1000)/10)+'% 같은분기 잔차) = <b>'+f1(B.rev)+'억</b>.</p></div><div>';
  if(T0.impl) h+=kv('회사 가이던스 암시 '+T0.T, f1(T0.impl.rev)+' · OP '+f1(T0.impl.op)+' ('+pm(T0.impl.opm)+')');
  h+=kv('Base vs 회사 암시', T0.impl?pc(B.rev/T0.impl.rev-1)+' / OP '+pc(B.op/T0.impl.op-1):'—');
  h+=kv('레인지 (Bear–Bull)', f1(T0.est.bear.rev)+'~'+f1(T0.est.bull.rev)+' · OP '+f1(T0.est.bear.op)+'~'+f1(T0.est.bull.op));
  h+=kv('OLS (n='+n+', 시차 '+lag+')', 'a='+f1(a)+' · b='+(Math.round(b*1000)/1000)+' · r='+(Math.round(r*1000)/1000));
  if(IN.consensus) h+=kv('컨센 '+esc(IN.consensus.fy_label||('FY'+IN.consensus.fy))+' ('+esc(IN.consensus.date)+')', f1(IN.consensus.rev)+' / OP '+f1(IN.consensus.op));
  h+=kv('다음 실적 발표', esc(IN.earn_next||'—'));
  h+='</div></div>';
  if(IN.consensus&&IN.consensus.note) h+='<p class="footnote">컨센서스 메모 ('+esc(IN.consensus.source||'')+' '+esc(IN.consensus.date||'')+'): '+esc(IN.consensus.note)+'</p>';
  if(IN.quality_note) h+='<div class="callout"><b>프록시 품질 주의</b> — '+esc(IN.quality_note)+' (현재 OLS r='+(Math.round(r*100)/100)+')</div>';
  if(gStale) h+='<div class="callout"><b>가이던스 갱신 필요</b> — 실적은 '+esc(lastQ)+'까지인데 inputs.json 가이던스 최신 공시일은 '+esc(lastGdate)+'입니다.</div>';
  targets.forEach(t=>{
    h+='<section class="tgt"><div class="sechead"><h2>'+esc(t.T)+' 매출분기 시나리오</h2><span class="k">프록시 '+esc(t.P)+' · 세관 '+t.seen.length+'/3개월 실측'+(t.miss.length?' · '+esc(t.miss.map(m=>m.slice(2)).join('·'))+' 보간':' · 보간 없음')+'</span></div>';
    if(t.extrap) h+='<div class="callout"><b>외삽 경고</b> — 분기 프록시 '+f1(t.est.base.px)+'억이 학습 구간 최대('+f1(xMax)+'억)를 넘어 OLS 바깥을 외삽합니다. 회사 암시와 함께 보세요.</div>';
    h+='<div class="tblwrap"><table><thead><tr><th>시나리오</th><th>분기 프록시</th><th>프록시 YoY</th><th>OLS 매출</th><th>잔차</th><th>매출</th><th>매출 YoY</th><th>OPM</th><th>영업이익</th></tr></thead><tbody>';
    if(t.impl) h+='<tr><td>회사 가이던스 암시</td><td>—</td><td>—</td><td>—</td><td>—</td><td class="num">'+f1(t.impl.rev)+'</td><td class="num">'+pc(t.ly?t.impl.rev/t.ly.rev-1:null)+'</td><td class="num">'+pm(t.impl.opm)+'</td><td class="num">'+f1(t.impl.op)+'</td></tr>';
    [['bear','Bear'+(t.miss.length?' · 미공표월 전년동월':'')+' · 최저 잔차'],['base','Base'+(t.miss.length?' · 3년 평균 월비중':'')+' · 평균 잔차'],['bull','Bull'+(t.miss.length?' · 최대 월비중':'')+' · 최대 잔차']].forEach(([k,lab])=>{ const e=t.est[k];
      h+='<tr'+(k==='base'?' class="hl"':'')+'><td>'+lab+'</td><td class="num">'+f1(e.px)+'</td><td class="num">'+pc(e.pyoy)+'</td><td class="num">'+f1(e.ols)+'</td><td class="num">'+pc(e.res)+'</td><td class="num"><b>'+f1(e.rev)+'</b></td><td class="num">'+pc(t.ly?e.rev/t.ly.rev-1:null)+'</td><td class="num">'+pm(e.opm)+'</td><td class="num"><b>'+f1(e.op)+'</b></td></tr>'; });
    h+='</tbody></table></div><p class="footnote">잔차 = 같은 분기 실적/OLS적합−1, 최근 3개('+t.use.map(p=>p.q+' '+pc(p.res)).join(', ')+')'+((IN.resid_exclude||[]).length?' · 제외 '+esc(IN.resid_exclude.join(', '))+(IN.resid_exclude_note?' ('+esc(IN.resid_exclude_note)+')':''):'')+'.</p></section>';
  });
  h+='<p class="footnote">마진 규칙: '+esc(IN.margin_rule||'')+' — 직전 비트폭 '+(beat==null?'없음(forecast_log에 직전분기 회사 암시 미기록 → 회사 암시 OPM 그대로)':pc(beat))+'.</p>';
  h+='<section><div class="sechead"><h2>예측 채점</h2><span class="k">forecast_log 예측을 실적 반영 즉시 자동 채점</span></div><div class="tblwrap"><table><thead><tr><th>분기</th><th>예측일</th><th>예측 매출 / OP</th><th>회사 암시 매출 / OP</th><th>실제 매출 / OP</th><th>매출 오차 (예측/실제−1)</th><th>OP 오차</th></tr></thead><tbody>';
  (IN.forecast_log||[]).forEach(fq=>{ const A=fin[fq.q];
    h+='<tr><td>'+esc(fq.q)+'</td><td>'+esc(fq.date)+'</td><td class="num">'+f1(fq.rev)+' / '+f1(fq.op)+'</td><td class="num">'+f1(fq.implied_rev)+' / '+f1(fq.implied_op)+'</td>'+(A?'<td class="num">'+f1(A.rev)+' / '+f1(A.op)+'</td><td class="num">'+pc(fq.rev/A.rev-1)+'</td><td class="num">'+pc(fq.op/A.op-1)+'</td>':'<td colspan="3" class="small">발표 대기</td>')+'</tr>'; });
  if(!(IN.forecast_log||[]).length) h+='<tr><td colspan="7" class="small">기록된 예측 없음</td></tr>';
  h+='</tbody></table></div></section>';
  h+='<section><div class="sechead"><h2>세관 프록시와 실적</h2><span class="k">팔랑크스 data_jp.js · 항만 '+esc(ports.join('·'))+'</span></div>';
  h+='<div class="card"><div class="ct">월별 세관 프록시 수출액 <span class="small">(억엔)</span></div><div class="cs">'+esc(IN.proxy_label||'')+' · 최근 44개월</div><div class="chart" id="chM"></div></div>';
  h+='<div class="card"><div class="ct">분기 매출: 실적 vs OLS 적합 <span class="small">(억엔'+(lag?', 프록시 '+lag+'분기 선행':'')+')</span></div><div class="legend"><span><i class="sw" style="background:var(--mjc)"></i>실적</span><span><i class="sw" style="background:var(--proxy-lt)"></i>OLS 적합</span><span><i class="sw" style="background:var(--proxy)"></i>추정 Base</span></div><div class="chart" id="chQ"></div></div></section>';
  h+='<section><div class="sechead"><h2>국가 lane</h2><span class="k">모멘텀 판독용</span></div><div class="tblwrap"><table id="laneT"></table></div>'+(IN.lane_note?'<p class="footnote">'+esc(IN.lane_note)+'</p>':'')+'</section>';
  $('app').innerHTML=h;
  const lastM=pxMonths.slice(-44); lineChart($('chM'),lastM,lastM.map(m=>px[m]));
  const tq={}; targets.forEach(t=>tq[t.T]=t.est.base.rev);
  const qs=finQs.filter(q=>q>='2023Q1').concat(targets.map(t=>t.T));
  barChart($('chQ'),qs,[{name:'실적',color:css('--mjc'),v:qs.map(q=>fin[q]?fin[q].rev:null)},{name:'OLS 적합',color:css('--proxy-lt'),v:qs.map(q=>fin[q]&&qSum(qAdd(q,-lag))!=null?fit(qSum(qAdd(q,-lag))):null)},{name:'추정 Base',color:css('--proxy'),v:qs.map(q=>tq[q]==null?null:tq[q])}]);
  if(C){ const loc=C.loc, lane=(ct,m)=>ports.reduce((s,p)=>s+(((loc[p]||{})[ct]||[])[idx[m]]||0),0);
    const cmp=pxMonths.slice(-3).filter(m=>qOf(m)===qOf(lastPx)); const cm=cmp.length?cmp:pxMonths.slice(-1);
    const prev=cm.map(m=>(+m.slice(0,4)-1)+m.slice(4)), tot=C.order.reduce((s,ct)=>s+cm.reduce((x,m)=>x+lane(ct,m),0),0);
    let t='<thead><tr><th>국가</th><th>'+esc(cm[0].slice(2)+(cm.length>1?'~'+cm[cm.length-1].slice(5):''))+' (억엔)</th><th>전년 동기</th><th>YoY</th><th>믹스</th></tr></thead><tbody>';
    C.order.forEach(ct=>{ const v=cm.reduce((x,m)=>x+lane(ct,m),0)/1e5, p=prev.reduce((x,m)=>x+lane(ct,m),0)/1e5;
      t+='<tr><td>'+esc(ct)+'</td><td class="num">'+f1(v)+'</td><td class="num">'+f1(p)+'</td><td class="num '+(p&&v>p?'up':'dn')+'">'+(p?pc(v/p-1):'—')+'</td><td class="num">'+(tot?Math.round(v*1e5/tot*100)+'%':'—')+'</td></tr>'; });
    $('laneT').innerHTML=t+'</tbody>';
  } else $('laneT').innerHTML='<tr><td class="small">국가 데이터 없음</td></tr>';
}
function S(t,at,p){const e=document.createElementNS('http://www.w3.org/2000/svg',t);for(const k in at)e.setAttribute(k,at[k]);if(p)p.appendChild(e);return e;}
function ticks(min,max,n){const st0=(max-min)/n,mag=Math.pow(10,Math.floor(Math.log10(st0)));let st=mag;for(const m of[1,2,2.5,5,10]){if(st0<=m*mag){st=m*mag;break}}const t=[];for(let v=Math.floor(min/st)*st;v<=Math.ceil(max/st)*st+1e-9;v+=st)t.push(Math.round(v*100)/100);return t;}
function tipOf(el){const t=document.createElement('div');t.className='tip';el.appendChild(t);return t;}
function axes(svg,tk,Y,W,Lp,R){tk.forEach(t=>{S('line',{x1:Lp,x2:W-R,y1:Y(t),y2:Y(t),stroke:css('--grid')},svg);S('text',{x:Lp-6,y:Y(t)+4,'text-anchor':'end',fill:css('--muted'),'font-size':11},svg).textContent=t;});}
function lineChart(el,lab,v){const W=1000,H=300,Lp=44,R=12,T=14,Bm=30,svg=S('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':'월별 세관 프록시'});el.appendChild(svg);
  const tk=ticks(0,Math.max(...v)*1.1,5),X=i=>Lp+(W-Lp-R)*i/(lab.length-1),Y=y=>T+(H-T-Bm)*(1-y/tk[tk.length-1]);axes(svg,tk,Y,W,Lp,R);
  lab.forEach((m,i)=>{if(m.endsWith('-01'))S('text',{x:X(i),y:H-8,'text-anchor':'middle',fill:css('--muted'),'font-size':11},svg).textContent=m.slice(0,4);});
  let d='';v.forEach((y,i)=>d+=(i?'L':'M')+X(i)+' '+Y(y));S('path',{d:d+`L${X(v.length-1)} ${Y(0)}L${X(0)} ${Y(0)}Z`,fill:css('--proxy'),'fill-opacity':.08},svg);S('path',{d,fill:'none',stroke:css('--proxy'),'stroke-width':2},svg);
  const li=v.length-1;S('circle',{cx:X(li),cy:Y(v[li]),r:4.5,fill:css('--proxy'),stroke:css('--surface'),'stroke-width':2},svg);
  S('text',{x:X(li)-8,y:Y(v[li])-10,'text-anchor':'end',fill:css('--ink'),'font-size':12,'font-weight':700},svg).textContent=lab[li]+' '+f1(v[li])+'억';
  const tp=tipOf(el);svg.addEventListener('mousemove',ev=>{const r=svg.getBoundingClientRect();let i=Math.round(((ev.clientX-r.left)*W/r.width-Lp)/(W-Lp-R)*(lab.length-1));i=Math.max(0,Math.min(li,i));
    const pv=i>=12?v[i-12]:null;tp.innerHTML='<b>'+lab[i]+'</b> '+f1(v[i])+'억'+(pv?' · YoY '+pc(v[i]/pv-1):'');tp.style.left=X(i)*r.width/W+'px';tp.style.top=Y(v[i])*r.height/H+'px';tp.style.opacity=1;});
  svg.addEventListener('mouseleave',()=>tp.style.opacity=0);}
function barChart(el,lab,ser){const W=1000,H=300,Lp=44,R=12,T=14,Bm=30,svg=S('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':'분기 매출 실적과 적합'});el.appendChild(svg);
  const all=ser.flatMap(s=>s.v).filter(x=>x!=null),tk=ticks(0,Math.max(...all)*1.1,5),Y=y=>T+(H-T-Bm)*(1-y/tk[tk.length-1]);axes(svg,tk,Y,W,Lp,R);
  const slot=(W-Lp-R)/lab.length,bw=Math.min(18,(slot-6)/2),tp=tipOf(el);
  lab.forEach((q,i)=>{const cx=Lp+slot*i+slot/2;S('text',{x:cx,y:H-8,'text-anchor':'middle',fill:css('--muted'),'font-size':10.5},svg).textContent=q.slice(2);
    const vis=ser.filter(s=>s.v[i]!=null);vis.forEach((s,k)=>{const x=cx-(vis.length*bw+(vis.length-1)*2)/2+k*(bw+2),y0=Y(s.v[i]);
      const rc=S('rect',{x,y:y0,width:bw,height:Math.max(1,Y(0)-y0),rx:3,fill:s.color},svg);
      rc.addEventListener('mousemove',()=>{const r=svg.getBoundingClientRect();tp.innerHTML='<b>'+q+'</b> '+s.name+' '+f1(s.v[i])+'억';tp.style.left=(x+bw/2)*r.width/W+'px';tp.style.top=y0*r.height/H+'px';tp.style.opacity=1;});
      rc.addEventListener('mouseleave',()=>tp.style.opacity=0);});});}
})();
