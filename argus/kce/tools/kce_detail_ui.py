"""신규 건설사 현장 상세·공시 추적 UI. 계산값과 공시 관측을 분리한다."""
CSS = r'''
.site-open{border:0;background:none;color:var(--a);font:inherit;text-align:left;cursor:pointer;padding:2px 0;max-width:100%}
.site-open:hover{text-decoration:underline}.site-open:focus-visible,button:focus-visible,select:focus-visible{outline:2px solid var(--a);outline-offset:3px}
.detail-top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.detail-top h2{margin:0}.detail-top button{background:var(--pn2);border:1px solid var(--ln);border-radius:6px;color:var(--tx2);padding:5px 10px;cursor:pointer}
.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:14px}
.detail-meta{color:var(--tx2);font-size:12px;margin:10px 0}.detail-hint{color:var(--tx2);font-size:11px;line-height:1.8;margin-top:10px}
.detail-grid .chart{height:220px}.detail-select{color:var(--tx);background:var(--pn2);border:1px solid var(--ln);padding:5px;border-radius:5px;font:inherit}
#siteDetail[hidden]{display:none}#siteDetail{scroll-margin-top:95px;animation:detail-in .16s ease-out}
@keyframes detail-in{from{opacity:.5;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
.source-links{display:flex;gap:10px;flex-wrap:wrap}.source-caption{font-size:11px;color:var(--tx2);margin-bottom:10px}
.report-ok{color:var(--up)}.report-wait{color:var(--wn)}details.source-more{margin-top:14px}details.source-more summary{cursor:pointer;color:var(--tx2);padding:5px 0}
.detail-kpi{display:flex;gap:24px;flex-wrap:wrap;padding:10px 0;border-bottom:1px solid var(--ln)}.detail-kpi b{font-size:18px;font-weight:600}.detail-kpi span{display:block;font-size:11px;color:var(--tx3)}
.source-table td.l{max-width:250px}.source-table a{font-size:11px}.detail-empty{color:var(--tx2);padding:18px 0}
@media(max-width:700px){.detail-grid{grid-template-columns:1fr}.detail-top h2{font-size:14px}.detail-kpi{gap:16px}}
@media(prefers-reduced-motion:reduce){#siteDetail{animation:none}*{scroll-behavior:auto!important}}
'''

HTML = r'''
<section id="siteDetail" hidden aria-labelledby="detailTitle">
 <div class="detail-top"><h2 id="detailTitle" tabindex="-1">현장 상세</h2><button id="detailClose" type="button">닫기</button></div>
 <p class="detail-meta" id="detailMeta"></p><div id="detailKpi" class="detail-kpi"></div>
 <div class="ctl" style="margin-top:12px"><label>공시 기준 <select id="detailBasis" class="detail-select" aria-label="현장 공시 기준"></select></label></div>
 <div class="detail-grid">
  <div><h2 id="detailBalanceTitle">수주잔고·완성공사액 <em>II-4 · 억원</em></h2><div class="chart"><canvas id="detailBalance"></canvas></div></div>
  <div><h2>미청구·계약자산·공사미수금 <em>III-8·계약 주석 · 억원</em></h2><div class="chart"><canvas id="detailReceivable"></canvas></div></div>
 </div>
 <p class="detail-hint">미청구공사와 공사미수금은 해당 계약의 공시값입니다. 서로 다른 회계 범위를 합산하지 않습니다. 빈 구간은 연결 가능한 공시값이 없습니다.</p>
 <h2 style="margin-top:18px">분기별 원문 대조 <em>금액 억원 · 진행률 %</em></h2>
 <div class="wrap"><table id="detailQuarter" class="source-table"><thead><tr><th class="l">분기·원문</th><th>도급액</th><th>계약잔액</th><th>완성공사액 차분</th><th>II-4 진행률¹</th><th>공시 진행률</th><th>미청구·계약자산</th><th>공사미수금</th><th>손상누계</th><th>대손충당금</th><th>계약부채</th></tr></thead><tbody></tbody></table></div>
 <p class="detail-hint">¹ II-4에서 진행률을 공시한 경우 그 값을 표시하고, 없으면 완성공사액 ÷ 도급액으로 계산합니다. 완성공사액 차분은 인접 분기 누계의 차이이며 회사의 분기 매출액이 아닙니다. 음수는 계약 변경·조정 가능성을 포함해 그대로 표시합니다.</p>
 <details class="source-more"><summary>계약명·발주처·일정·도급액 변경 이력 <span id="eventCount"></span></summary><div class="wrap"><table id="detailEvents"><thead><tr><th class="l">관측 분기</th><th class="l">항목</th><th class="l">이전 원문</th><th class="l">이번 원문</th></tr></thead><tbody></tbody></table></div></details>
 <details class="source-more"><summary>선택 현장의 공시 행 전체 <span id="detailObsCount"></span></summary><div class="wrap"><table id="detailObs" class="source-table"><thead><tr><th class="l">분기·기준</th><th class="l">원문 회사명·현장</th><th>공시 수주총액</th><th>진행률</th><th>미청구·계약자산</th><th>공사미수금</th><th class="l">완성기한</th><th class="l">원문·단위</th></tr></thead><tbody></tbody></table></div></details>
</section>
<section id="sourceCoverage">
 <h2>원문 연결 현황 <em>분기별 수집·매칭 상태</em></h2>
 <p class="source-caption" id="sourceSummary"></p>
 <div class="wrap"><table id="sourceLedger" class="source-table"><thead><tr><th class="l">분기</th><th class="l">공식 원문</th><th>계약 관측</th><th>현장 연결</th><th>연결 대기</th><th class="l">확인 상태</th></tr></thead><tbody></tbody></table></div>
 <details class="source-more"><summary>아직 현장과 연결되지 않은 공시 행 <span id="unmatchedCount"></span></summary>
  <p class="detail-hint">이름·계약 식별 근거가 부족하거나 II-4 표에 없는 행입니다. 같은 현장으로 단정하거나 기존 잔고에 더하지 않습니다. 원문의 회사명 열에는 보고 법인뿐 아니라 원청사·발주처·현장명이 기재되기도 합니다.</p>
  <label>분기 <select id="unmatchedQuarter" class="detail-select" aria-label="미연결 공시 분기"></select></label>
  <div class="wrap"><table id="unmatchedRows" class="source-table"><thead><tr><th class="l">기준</th><th class="l">원문 회사명·현장</th><th>공시 수주총액</th><th>진행률</th><th class="l">원문</th></tr></thead><tbody></tbody></table></div>
 </details>
</section>
'''

JS = r'''
;(function(){
 'use strict';
 const detail=DATA.detail||{ledger:[],observations:[],unmatched:[]}, S=DATA.sites, fq=DATA.fq;
 const byId=new Map(S.concat(detail.disclosure_sites||[]).map(s=>[s.id,s])); let selected=null,lastTrigger=null,charts=[];
 const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const val=v=>v==null?'—':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2});
 const money=v=>v==null?'—':val(v/100);
 const pct=v=>v==null?'—':val(v)+'%';
 const eok=v=>v==null?null:v/100;
 function link(url,label){try{const u=new URL(url);if(u.protocol!=='https:'||u.hostname!=='dart.fss.or.kr')return '—';return '<a href="'+esc(u.href)+'" target="_blank" rel="noopener noreferrer">'+esc(label)+' ↗</a>';}catch(e){return '—';}}
 function report(q){return 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+DATA.src[q];}
 function empty(n,text){return '<tr><td colspan="'+n+'" class="detail-empty">'+esc(text)+'</td></tr>';}
 function chart(id, datasets, percent){
  const cv=document.getElementById(id);if(typeof Chart!=='function')return;
  charts.push(new Chart(cv,{type:'line',data:{labels:fq,datasets:datasets},options:{responsive:true,maintainAspectRatio:false,
   animation:false,spanGaps:false,interaction:{mode:'index',intersect:false},
   scales:{x:{grid:{display:false},ticks:{color:'#98a1b0',font:{size:10}}},y:{grid:{color:'#2a2f3a'},ticks:{color:'#98a1b0'}}},
   plugins:{legend:{labels:{color:'#98a1b0',boxWidth:10}},tooltip:{callbacks:{label:c=>c.dataset.label+' '+(percent?pct(c.parsed.y):money(c.parsed.y==null?null:c.parsed.y*100)+'억')}}}}}));
 }
 function series(label,values,color){return {label:label,data:values.map(eok),borderColor:color,backgroundColor:color,borderWidth:2,pointRadius:2,tension:0,spanGaps:false};}
 function unique(rows){
  if(!rows.length)return null;
  const keys=['amt','pr','ub','ubimp','rc','allw','contract_liability','p8_ent'];
  const signatures=new Set(rows.map(r=>JSON.stringify(keys.map(k=>r[k]))));
  return signatures.size===1?rows[0]:null;
 }
 function renderDetail(){
  const s=selected;if(!s)return;
  const basis=document.getElementById('detailBasis').value;
  const obs=(s.detail||[]).map(i=>detail.observations[i]);
  const byQ=fq.map(q=>unique(obs.filter(r=>r.quarter===q&&r.basis===basis)));
  charts.forEach(c=>c.destroy());charts=[];
  document.getElementById('detailBalanceTitle').textContent=s.source_only?'공시 진행률 · %':'수주잔고·완성공사액 · II-4 · 억원';
  try{if(s.source_only){chart('detailBalance',[{label:'공시 진행률',data:byQ.map(r=>r?r.pr:null),borderColor:'#60a5fa',borderWidth:2,pointRadius:2,spanGaps:false}],true);}
   else{chart('detailBalance',[series('계약잔액',s.s.bal,'#60a5fa'),series('누적 완성공사액',s.s.cmp,'#a78bfa')]);}
   chart('detailReceivable',[series('미청구·계약자산',byQ.map(r=>r?r.ub:null),'#fbbf24'),series('공사미수금',byQ.map(r=>r?r.rc:null),'#22d3ee')]);}catch(e){console.error(e);}
  document.querySelector('#detailQuarter tbody').innerHTML=fq.map((q,k)=>{
   const r=byQ[k],ob=(s.observations||[])[k],ledger=(detail.ledger||[]).find(x=>x.quarter===q);
   return '<tr><td class="l">'+link((ledger||{}).ii4_url||report(q),q)+'</td><td>'+money(s.s.amt[k])+'</td><td>'+money(s.s.bal[k])+'</td><td>'+money((s.cmp_delta||[])[k])+'</td><td>'+pct(s.s.pr[k])+(ob&&ob.progress_basis==='cmp_div_amt'?' <span class="mut">계산</span>':'')+'</td><td>'+pct(r&&r.pr)+'</td><td>'+money(r&&r.ub)+'</td><td>'+money(r&&r.rc)+'</td><td>'+money(r&&r.ubimp)+'</td><td>'+money(r&&r.allw)+'</td><td>'+money(r&&r.contract_liability)+'</td></tr>';
  }).join('');
  document.getElementById('detailObsCount').textContent='('+obs.length+')';
  document.querySelector('#detailObs tbody').innerHTML=obs.slice().reverse().map(r=>'<tr><td class="l">'+esc(r.quarter+' · '+r.basis)+'</td><td class="l" title="'+esc(r.nm)+'">'+esc((r.p8_ent||'')+' · '+r.nm)+'</td><td>'+money(r.amt)+'</td><td>'+pct(r.pr)+'</td><td>'+money(r.ub)+'</td><td>'+money(r.rc)+'</td><td class="l">'+esc(r.p8_dl||'—')+'</td><td class="l">'+link(r.url,r.source_title)+'<br><span class="mut">'+esc(r.source_unit||'금액 단위 미확인')+' · 표 '+esc(r.table_id)+' · 행 '+r.source_row+'</span></td></tr>').join('')||empty(8,'이 현장에 정확히 연결된 진행률 공시 행이 없습니다.');
 }
 function openSite(id,trigger){
  const s=byId.get(id);if(!s)return;selected=s;lastTrigger=trigger;
  const box=document.getElementById('siteDetail');box.hidden=false;
  document.getElementById('detailTitle').textContent=s.nm;
  document.getElementById('detailMeta').textContent=(s.source_only?'III-8·주석 전용 관측 · II-4 잔고 합계에 미포함 | ':'')+[s.cl||'발주처 미기재',s.seg,s.reg,s.sd||'착공 미기재',s.ed||'완공예정 미기재'].join(' · ');
  const k=fq.length-1;
  document.getElementById('detailKpi').innerHTML='<div><b>'+money(s.s.bal[k])+'</b><span>'+fq[k]+' 계약잔액 · 억원</span></div><div><b>'+money(s.s.amt[k])+'</b><span>도급액 · 억원</span></div><div><b>'+(s.detail||[]).length+'</b><span>연결된 공시 관측</span></div>';
  const bs=Array.from(new Set((s.detail||[]).map(i=>detail.observations[i].basis))).sort((a,b)=>['별도','연결','미확인'].indexOf(a)-['별도','연결','미확인'].indexOf(b));
  const select=document.getElementById('detailBasis');select.innerHTML=(bs.length?bs:['연결된 공시 없음']).map(b=>'<option>'+esc(b)+'</option>').join('');select.disabled=!bs.length;
  const fields={nm:'현장명',cl:'발주처',sd:'착공·계약일',ed:'완공예정',amt:'도급액(백만원)'};
  document.getElementById('eventCount').textContent='('+(s.events||[]).length+')';
  document.querySelector('#detailEvents tbody').innerHTML=(s.events||[]).slice().reverse().map(e=>'<tr><td class="l">'+link(report(e.quarter),e.quarter)+'</td><td class="l">'+fields[e.field]+'</td><td class="l">'+esc(e.before)+'</td><td class="l">'+esc(e.after)+'</td></tr>').join('')||empty(4,'관측된 변경이 없습니다.');
  renderDetail();document.getElementById('detailTitle').focus({preventScroll:true});
  box.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});
 }
 document.querySelector('#tb tbody').addEventListener('click',e=>{const b=e.target.closest('[data-site]');if(b)openSite(b.dataset.site,b);});
 document.querySelector('#unmatchedRows tbody').addEventListener('click',e=>{const b=e.target.closest('[data-site]');if(b)openSite(b.dataset.site,b);});
 document.getElementById('detailBasis').addEventListener('change',renderDetail);
 document.getElementById('detailClose').addEventListener('click',()=>{document.getElementById('siteDetail').hidden=true;if(lastTrigger&&lastTrigger.isConnected)lastTrigger.focus();});
 const status={checked:'원문 확인',not_collected:'미수집',report_changed:'정정 재확인',section_not_found:'절 미발견'};
 const led=detail.ledger||[],rows=detail.observations||[];
 document.getElementById('sourceSummary').textContent='확인 '+led.filter(x=>x.status==='checked').length+'/'+fq.length+'분기 · 계약 관측 '+rows.length+'행 · 현장 연결 '+rows.filter(x=>x.site_id).length+'행. 연결·별도 각각의 관측 수이며 현장 수가 아닙니다.';
 document.querySelector('#sourceLedger tbody').innerHTML=led.slice().reverse().map(r=>'<tr><td class="l">'+esc(r.quarter)+'</td><td class="l"><div class="source-links">'+(r.sources||[]).map(s=>link(s.url,s.title)).join('')+'</div></td><td>'+val(r.rows)+'</td><td>'+val(r.matched)+'</td><td>'+val(r.unmatched)+'</td><td class="l">'+esc(status[r.status]||r.status)+(r.status==='checked'&&!r.rows?' · 인식된 개별 진행률 표 없음':'')+(r.unknown_unit?' · 단위 확인 필요 '+r.unknown_unit+'행':'')+(r.unknown_basis?' · 연결/별도 미확인 '+r.unknown_basis+'행':'')+'</td></tr>').join('')||empty(6,'추가 원문 수집 전입니다.');
 document.getElementById('unmatchedCount').textContent='('+(detail.unmatched||[]).length+')';
 const uq=document.getElementById('unmatchedQuarter');uq.innerHTML=fq.slice().reverse().map(q=>'<option>'+q+'</option>').join('');
 function unmatched(){document.querySelector('#unmatchedRows tbody').innerHTML=(detail.unmatched||[]).map(i=>rows[i]).filter(r=>r.quarter===uq.value).map(r=>'<tr><td class="l">'+esc(r.basis)+'</td><td class="l" title="'+esc(r.nm)+'"><button class="site-open" type="button" data-site="'+esc(r.disclosure_id)+'">'+esc((r.p8_ent||'')+' · '+r.nm)+'</button></td><td>'+money(r.amt)+'</td><td>'+pct(r.pr)+'</td><td class="l">'+link(r.url,'원문 확인')+'</td></tr>').join('')||empty(5,'이 분기에 미연결 공시 행이 없습니다.');}
 uq.addEventListener('change',unmatched);unmatched();
})();
'''
