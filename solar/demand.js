(function (global) {
  'use strict';
  const finite = n => typeof n === 'number' && Number.isFinite(n);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = (v, places = 2) => finite(v) ? v.toLocaleString('ko-KR', {maximumFractionDigits: places}) : '—';
  const COLORS = ['#d9ed8f', '#84b9ed', '#e6ba70', '#a8a0df'];
  const COUNTRY = {US:'미국',CA:'캐나다',MX:'멕시코'};
  const REASONS = {missing_source:'대응 원문 값 없음 / 기간 미완결',missing_model_period:'대응 모델 값 없음 / 기간 미완결',nonpositive_denominator:'이전 값이 0 이하',below_materiality:'이전 값이 비교 기준 미만',different_publication_vintages:'서로 다른 발표판 · 비교 보류',publisher_reported:'발행자 발표 성장률',beyond_installation_horizon:'모델 설치기간 밖',incomplete_period:'구성 월 미확인 / 기간 미완결',source_conflict:'원문 값 불일치',missing_installation_source:'설치 원문 값 없음',source_precision_difference:'원문 표 사이 정밀도 차이'};
  function reason(code) { return code ? (REASONS[code] || String(code)) : ''; }
  function safeURL(s) { try { const u=new URL(s); return u.protocol==='https:' && !u.username && !u.password && (!u.port || u.port==='443') ? u.href : null; } catch (_) { return null; } }
  function link(url, text, hosts) { const u=safeURL(url); return u && (!hosts || hosts.has(new URL(u).hostname)) ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>` : esc(text); }
  function csv(rows, columns) {
    const cell = v => { if(v==null) return ''; let s=String(v); if(typeof v!=='number' && /^[\s]*[=+@\-\t\r]/.test(s))s="'"+s; return /[",\n\r]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s; };
    return '\ufeff'+[columns.map(cell).join(','),...rows.map(r=>columns.map(k=>cell(r[k])).join(','))].join('\r\n')+'\r\n';
  }
  function shiftMonth(p,n) { if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(p) || !Number.isInteger(n))throw new Error('invalid month'); const a=p.split('-').map(Number),i=a[0]*12+a[1]-1+n;return `${Math.floor(i/12)}-${String((i%12+12)%12+1).padStart(2,'0')}`; }
  function procure(rows,lead,stock) {
    if(!Number.isInteger(lead)||lead<0||lead>6||!finite(stock)||stock<-.3||stock>.3)throw new Error('invalid assumptions');
    const index=new Map(rows.map(r=>[r.period,r]));
    if(index.size!==rows.length)throw new Error('duplicate period');
    return rows.map(r=>{ const p=shiftMonth(r.period,lead),next=index.get(p);return {...r,procurement:next&&finite(next.base)?next.base*(1+stock):null,procurement_reason:next&&finite(next.base)?null:'beyond_installation_horizon',installation_period_for_procurement:p,lead_months:lead,stock_adjustment_pct:stock*100}; });
  }
  function aggregateScenario(rows,frequency) {
    if(frequency==='month')return rows.map(r=>({...r}));
    if(!['quarter','year'].includes(frequency))throw new Error('invalid frequency');
    const groups=new Map();
    for(const r of rows){shiftMonth(r.period,0);const [y,m]=r.period.split('-').map(Number),p=frequency==='year'?String(y):`${y}-Q${Math.ceil(m/3)}`;if(!groups.has(p))groups.set(p,new Map());if(groups.get(p).has(m))throw new Error('duplicate month');groups.get(p).set(m,r);}
    return [...groups].sort((a,b)=>a[0].localeCompare(b[0])).map(([period,months])=>{
      const end=frequency==='year'?12:Number(period.slice(-1))*3,needed=Array.from({length:frequency==='year'?12:3},(_,i)=>end-(frequency==='year'?11:2)+i);
      const out={period,status:'modeled_timing_allocation',lead_months:rows[0]?.lead_months,stock_adjustment_pct:rows[0]?.stock_adjustment_pct};
      for(const key of ['low','base','high','procurement'])out[key]=needed.every(m=>finite(months.get(m)?.[key]))?needed.reduce((s,m)=>s+months.get(m)[key],0):null;
      out.procurement_reason=finite(out.procurement)?null:'incomplete_period';
      out.installation_period_for_procurement=needed.every(m=>months.has(m))?`${months.get(needed[0]).installation_period_for_procurement} ~ ${months.get(needed.at(-1)).installation_period_for_procurement}`:null;
      return out;
    });
  }
  function scenarioGrowth(rows,frequency) {
    const index=new Map(rows.map(r=>[r.period,r]));
    if(index.size!==rows.length)throw new Error('duplicate scenario period');
    const prior=(p,annual)=>{if(frequency==='month')return shiftMonth(p,annual?-12:-1);if(frequency==='year'&&/^\d{4}$/.test(p))return String(Number(p)-1);if(frequency==='quarter'&&/^\d{4}-Q[1-4]$/.test(p)){const y=Number(p.slice(0,4)),q=Number(p.at(-1));return annual?`${y-1}-Q${q}`:q===1?`${y-1}-Q4`:`${y}-Q${q-1}`;}throw new Error('invalid frequency or period');};
    const percent=(value,old)=>!finite(value)||!finite(old)?[null,'missing_model_period']:old<=0?[null,'nonpositive_denominator']:[100*(value/old-1),null];
    return rows.map(r=>{const out={...r,comparison_period:prior(r.period,false),yoy_period:prior(r.period,true)};for(const key of ['base','procurement'])for(const [suffix,period] of [['change',out.comparison_period],['yoy',out.yoy_period]]){const [v,why]=percent(r[key],index.get(period)?.[key]);out[`${key}_${suffix}_pct`]=v;out[`${key}_${suffix}_reason`]=why;}return out;});
  }
  function compareAnnual(series) {
    const ids=['us_new_installations','us_domestic_shipments_annual','us_domestic_shipments'];
    const maps=ids.map(id=>new Map((series.find(s=>s.id===id)?.tables?.year||[]).map(r=>[r.period,r.value])));
    const years=[...new Set(maps.flatMap(m=>[...m.keys()]))].sort();
    return years.map(period=>({period,installation:maps[0].get(period)??null,annual_shipments:maps[1].get(period)??null,monthly_sum_shipments:maps[2].get(period)??null}));
  }
  function validate(data) {
    if(!data || !Array.isArray(data.countries)||!Array.isArray(data.series)||!Array.isArray(data.sources)||!Array.isArray(data.coverage)||!Array.isArray(data.pipeline)||!Array.isArray(data.forecast?.annual)||!Array.isArray(data.forecast?.monthly))throw new Error('invalid payload');
    if(data.countries.length!==3||new Set(data.countries.map(c=>c.country)).size!==3||!['US','CA','MX'].every(c=>data.countries.some(r=>r.country===c)))throw new Error('incomplete countries');
    if(!finite(data.total_capacity)||!finite(data.total_installation)||data.total_capacity<=0||data.countries.some(c=>!finite(c.capacity)||c.capacity<0||!finite(c.installation)||c.installation<0))throw new Error('invalid country values');
    if(Math.abs(data.countries.reduce((s,c)=>s+c.capacity,0)-data.total_capacity)>1e-6||Math.abs(data.countries.reduce((s,c)=>s+c.installation,0)-data.total_installation)>1e-6)throw new Error('country sum mismatch');
    if(new Set(data.series.map(s=>s.id)).size!==data.series.length)throw new Error('duplicate series');
    for(const s of data.series){if(!s.id||!s.tables||typeof s.tables!=='object')throw new Error('invalid series');for(const [f,rows] of Object.entries(s.tables)){if(!['month','quarter','year'].includes(f)||!Array.isArray(rows)||new Set(rows.map(r=>r.period)).size!==rows.length)throw new Error('invalid series periods');const p=f==='month'?/^\d{4}-(0[1-9]|1[0-2])$/:f==='quarter'?/^\d{4}-Q[1-4]$/:/^\d{4}$/;for(const r of rows){if(!p.test(r.period)||['value','change_pct','yoy_pct'].some(k=>r[k]!=null&&!finite(r[k])))throw new Error('invalid series value');}}}
    for(const r of [...data.forecast.annual,...data.forecast.monthly])if(!['low','base','high'].every(k=>finite(r[k])&&r[k]>=0)||r.low>r.base||r.base>r.high)throw new Error('invalid scenario');
    if(new Set(data.forecast.monthly.map(r=>r.period)).size!==data.forecast.monthly.length)throw new Error('duplicate scenario month');
    return data;
  }
  function table(headers, rows, cls='') {return `<div class="table-scroll" tabindex="0" role="region" aria-label="데이터 표 · 가로 및 세로 스크롤"><table class="${esc(cls)}"><thead><tr>${headers.map((h,i)=>`<th scope="col"${i?' class="num"':''}>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map(r=>`<tr>${r.map((c,i)=>`<td${i?' class="num"':''}>${c}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${headers.length}" class="empty">확보한 값이 없습니다.</td></tr>`}</tbody></table></div>`;}
  const valCell = v => finite(v)?fmt(v):'<span class="unknown">미확인</span>';
  function percentCell(v,r) {return finite(v)?`<span class="${v>0?'up':v<0?'down':''}">${v>0?'+':''}${fmt(v,1)}%</span>${r?`<small>${esc(reason(r))}</small>`:''}`:`<span class="unknown">—</span><small>${esc(reason(r)||'미확인')}</small>`;}
  function plot(rows, specs, unit, title, band=false) {
    const values=rows.flatMap(r=>specs.map(s=>r[s.key]).concat(band?[r.low,r.high]:[])).filter(finite);
    if(!values.length)return '<div class="chart-panel empty">확보한 수치가 없어 차트를 그리지 않습니다. 결측 값은 아래 표에서 확인하세요.</div>';
    const W=1020,H=278,L=61,R=22,T=15,B=36,PW=W-L-R,PH=H-T-B;
    let min=Math.min(0,...values),max=Math.max(...values);if(max===min)max=min+1;const pad=(max-min)*.10;max+=pad;if(min<0)min-=pad;
    const x=i=>L+(rows.length===1?PW/2:PW*i/(rows.length-1)), y=v=>T+(max-v)/(max-min)*PH;
    const segs=(keys)=>{const out=[];let run=[];rows.forEach((r,i)=>{if(keys.every(k=>finite(r[k])))run.push([r,i]);else{if(run.length)out.push(run);run=[];}});if(run.length)out.push(run);return out;};
    let svg=`<svg class="chart-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}. 정확한 값은 이어지는 표에서 확인할 수 있습니다.">`;
    for(let i=0;i<5;i++){const v=min+(max-min)*i/4,yy=y(v);svg+=`<line class="grid" x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}"/><text x="${L-9}" y="${yy+4}" text-anchor="end">${esc(fmt(v,1))}</text>`;}
    if(min<0)svg+=`<line class="axis" x1="${L}" y1="${y(0)}" x2="${W-R}" y2="${y(0)}"/>`;
    if(band)for(const run of segs(['low','high'])){const points=run.map(([r,i])=>`${x(i)},${y(r.high)}`).concat([...run].reverse().map(([r,i])=>`${x(i)},${y(r.low)}`));svg+=`<polygon class="range" points="${points.join(' ')}"/>`;}
    specs.forEach((s,j)=>{for(const run of segs([s.key]))svg+=`<polyline class="line" stroke="${COLORS[j]}" points="${run.map(([r,i])=>`${x(i)},${y(r[s.key])}`).join(' ')}"/>`;rows.forEach((r,i)=>{if(finite(r[s.key]))svg+=`<circle class="point" cx="${x(i)}" cy="${y(r[s.key])}" r="${rows.length>50?2:3.5}" fill="${COLORS[j]}"><title>${esc(r.period)} · ${esc(s.name)} ${esc(fmt(r[s.key],3))} ${esc(unit)}</title></circle>`;});});
    const ticks=[...new Set(Array.from({length:Math.min(7,rows.length)},(_,i)=>Math.round(i*(rows.length-1)/Math.max(1,Math.min(7,rows.length)-1))))];
    for(const i of ticks)svg+=`<text x="${x(i)}" y="${H-10}" text-anchor="middle">${esc(rows[i].period)}</text>`;
    svg+='</svg>';
    return `<div class="chart-panel"><div class="legend">${specs.map((s,i)=>`<span><i style="background:${COLORS[i]}"></i>${esc(s.name)}</span>`).join('')}${band?'<span><i class="band"></i>가정 범위</span>':''}</div><div class="chart-unit">${esc(unit)}</div><div class="chart-scroll" tabindex="0" role="region" aria-label="차트 · 작은 화면에서 가로 스크롤">${svg}</div><p class="chart-note">결측 값은 0으로 표시하거나 선으로 연결하지 않습니다. 작은 화면에서는 차트를 가로로 밀어 확인할 수 있습니다.</p></div>`;
  }
  function download(name, text) {const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  function boot(data) {
    validate(data);const $=id=>document.getElementById(id);const hosts=new Set(data.sources.map(s=>safeURL(s.url||s.source_url)).filter(Boolean).map(u=>new URL(u).hostname));
    for(const s of [data.forecast.anchor_url,data.pipeline_source]){const u=safeURL(s);if(u)hosts.add(new URL(u).hostname);}
    const sourceIndex=new Map(data.sources.map(s=>[s.id,s]));
    const sourceLinks=ids=>(ids||[]).map(id=>{const s=sourceIndex.get(id);return s?link(s.url||s.source_url,s.name||id,hosts):esc(id);}).join(' · ');
    $('asof').textContent=data.asof||'미확인';
    $('capacity-content').innerHTML=`<div class="capacity-top"><div class="stat-card"><span>3개국 누적 PV 용량</span><div class="stat-value">${fmt(data.total_capacity)}<small>GWdc</small></div><p>2025년 말 · 발행자 추정</p></div><div class="stat-card"><span>3개국 2025년 신규 설치</span><div class="stat-value">${fmt(data.total_installation,1)}<small>GWdc</small></div><p>약 ${fmt(data.total_installation,1)} GWdc · 발행자 반올림 값의 합 ${fmt(data.total_installation)} GWdc</p></div></div><div class="country-grid">${data.countries.map(c=>`<article class="country-card"><div class="country-head"><h3>${esc(c.name)}</h3><span>${esc(c.country)}</span></div><div class="country-values"><strong>${fmt(c.capacity)}</strong><span>GWdc · 누적</span></div><div class="sharebar" role="img" aria-label="북미 누적용량 비중 ${esc(fmt(c.capacity/data.total_capacity*100,1))}%"><span style="width:${c.capacity/data.total_capacity*100}%"></span></div><p>북미 비중 ${fmt(c.capacity/data.total_capacity*100,1)}% · 신규 ${fmt(c.installation)} GWdc</p></article>`).join('')}</div><p class="capacity-note">${esc(data.capacity_basis)}<br>${esc(data.capacity_note)}</p>`;
    const comparison=compareAnnual(data.series);
    $('comparison-content').innerHTML=plot(comparison,[{key:'installation',name:'신규 설치 · PVPS'},{key:'annual_shipments',name:'미국 내 출하 · EIA 연간 조사'},{key:'monthly_sum_shipments',name:'미국 내 출하 · EIA 월별 표본 합계'}],'GWdc','미국 연간 설치와 출하')+table(['연도','신규 설치 · PVPS','출하 · 연간 조사','출하 · 월별 표본 합계'],comparison.map(r=>[esc(r.period),valCell(r.installation),valCell(r.annual_shipments),valCell(r.monthly_sum_shipments)]))+`<p class="capacity-note">EIA 연간 조사는 연간·월별 응답자를 포함하며 마지막 관측연도는 2022년입니다. 월별 표본 합계는 별도 범위이며, 12개월 중 비공개·미확인이 있으면 연간 합계를 표시하지 않습니다. 2024년 월별 자료는 9월까지입니다. 서로 다른 계열을 이어붙이지 않습니다.<br>설치 원문: ${sourceLinks(data.series.find(s=>s.id==='us_new_installations')?.source_ids)}<br>출하 원문: ${sourceLinks(data.series.find(s=>s.id==='us_domestic_shipments_annual')?.source_ids)}</p>`;
    const state={series:data.series.find(s=>s.id==='us_seia_quarter_installations')?.id||data.series[0]?.id,frequency:'quarter',forecastFrequency:'month',scenarioView:'level',lead:0,stock:0};
    $('series-select').innerHTML=data.series.map(s=>`<option value="${esc(s.id)}">${esc(s.name)} · ${esc(s.unit)}</option>`).join('');
    $('series-select').value=state.series;
    function history(){const s=data.series.find(s=>s.id===state.series);const fs=Object.keys(s.tables);if(!fs.includes(state.frequency))state.frequency=fs[0];for(const o of $('frequency-select').options)o.disabled=!fs.includes(o.value);$('frequency-select').value=state.frequency;const rows=s.tables[state.frequency]||[];const fName={month:'MoM',quarter:'QoQ',year:'YoY'}[state.frequency];$('series-note').textContent=s.note||'';$('history-content').innerHTML=`<p class="badge-line">${esc(s.unit)} · ${esc({stock:'기말 재고',flow:'기간 흐름',net_stock_change:'기말 재고 차이'}[s.measure]||s.measure)} · ${rows.length?`${esc(rows[0].period)} ~ ${esc(rows.at(-1).period)}`:'관측 없음'}</p>`+plot(rows,[{key:'value',name:s.name}],s.unit,s.name)+plot(rows,state.frequency==='year'?[{key:'yoy_pct',name:'YoY · 전년 대비'}]:[{key:'change_pct',name:fName+' · 이전 기간 대비'},{key:'yoy_pct',name:'YoY · 전년 동기 대비'}],'%',s.name+' 증감률')+table(['기간',`값 (${s.unit})`,`${fName} · 이전 기간 대비`,'YoY · 전년 동기 대비'],rows.slice().reverse().map(r=>[`${esc(r.period)}<small>비교 ${esc(r.comparison_period||'—')} / 전년 ${esc(r.yoy_period||'—')}</small>`,valCell(r.value),percentCell(r.change_pct,r.change_reason),percentCell(r.yoy_pct,r.yoy_reason)]))+`<p class="capacity-note">${sourceLinks(s.source_ids)}</p>`;}
    $('series-select').addEventListener('change',()=>{state.series=$('series-select').value;history();});$('frequency-select').addEventListener('change',()=>{state.frequency=$('frequency-select').value;history();});
    $('history-csv').addEventListener('click',()=>{const s=data.series.find(s=>s.id===state.series);const rows=s.tables[state.frequency].map(r=>({...r,series_id:s.id,name:s.name,unit:s.unit,measure:s.measure,frequency:state.frequency,note:s.note,source_ids:(s.source_ids||[]).join(';'),source_urls:(s.source_ids||[]).map(id=>safeURL(sourceIndex.get(id)?.url||sourceIndex.get(id)?.source_url)||'').join(';')}));download(`solar-${s.id}-${state.frequency}.csv`,csv(rows,['series_id','name','period','frequency','value','unit','measure','change_pct','change_reason','comparison_period','yoy_pct','yoy_reason','yoy_period','note','source_ids','source_urls']));});
    history();
    const forecast=data.forecast;
    $('forecast-annual').innerHTML=`<p class="section-note">미국은 공개된 연간 약 ${fmt(data.forecast.anchors.US)} GWdc를 각 연도에 동일하게 적용한 참고 가정입니다. 캐나다·멕시코는 2025년 설치량을 유지합니다. 발행자의 연도별 전망표가 아닙니다.</p><div class="anchors">${Object.entries(forecast.anchors||{}).map(([c,v])=>`<span>${esc(COUNTRY[c]||c)} 기준 ${fmt(v)} GWdc / 년</span>`).join('')}</div>`+plot(forecast.annual,[{key:'base',name:'설치 기준 시나리오'}],'GWdc','북미 연간 조건부 설치 시나리오',true)+table(['연도','하방','기준','상방','민감도 가정','국가별 기준'],forecast.annual.map(r=>[esc(r.period),fmt(r.low),fmt(r.base),fmt(r.high),`±${fmt(r.stress_pct)}%`,Object.entries(r.countries||{}).map(([c,v])=>`${esc(COUNTRY[c]||c)} ${fmt(v)}`).join(' / ')]),'annual-table');
    $('forecast-method').innerHTML=`<ul>${(forecast.notes||[]).map(n=>`<li>${esc(n)}</li>`).join('')}</ul><p>${link(forecast.anchor_url,'미국 기준값 공개 보도자료 · SEIA / Wood Mackenzie',hosts)}</p>`;
    function scenarioRows(){return scenarioGrowth(aggregateScenario(procure(forecast.monthly,state.lead,state.stock/100),state.forecastFrequency),state.forecastFrequency);}
    function scenario(){
      const rows=scenarioRows(),fName={month:'MoM',quarter:'QoQ',year:'YoY'}[state.forecastFrequency];
      $('scenario-equation').textContent=`사용자 가정: 조달 선행 ${state.lead}개월 · 추가 비축/재고 소진 ${state.stock>0?'+':''}${state.stock}%. 조달 필요량 = ${state.lead}개월 뒤 설치 기준값 × ${(1+state.stock/100).toFixed(2)}. 기본값은 0개월 · 0%입니다.`;
      let html;
      if(state.scenarioView==='level')html=plot(rows,[{key:'base',name:'설치 기준 시나리오'},{key:'procurement',name:'조건부 조달 필요량'}],'GWdc','북미 설치와 조건부 조달 시나리오')+table(['기간','설치 하방','설치 기준','설치 상방','조건부 조달','조달 대응 설치기간'],rows.map(r=>[esc(r.period),valCell(r.low),valCell(r.base),valCell(r.high),`${valCell(r.procurement)}${r.procurement_reason?`<small>${esc(reason(r.procurement_reason))}</small>`:''}`,esc(r.installation_period_for_procurement||'—')]));
      else {const suffix=state.scenarioView==='yoy'?'yoy':'change',label=suffix==='yoy'?'YoY':fName;html=`<p class="badge-line">모델 증감률 · ${esc(label)} · 실측 성장률이 아닙니다. 같은 모델의 정확한 대응 기간만 비교합니다.</p>`+plot(rows,[{key:`base_${suffix}_pct`,name:`설치 모델 ${label}`},{key:`procurement_${suffix}_pct`,name:`조건부 조달 모델 ${label}`}],'%','북미 조건부 시나리오 모델 증감률')+table(['기간',`설치 모델 ${label}`,`조달 모델 ${label}`,'비교 대상 기간'],rows.map(r=>[esc(r.period),percentCell(r[`base_${suffix}_pct`],r[`base_${suffix}_reason`]),percentCell(r[`procurement_${suffix}_pct`],r[`procurement_${suffix}_reason`]),esc(r[suffix==='yoy'?'yoy_period':'comparison_period'])]));}
      $('forecast-monthly').innerHTML=html+'<p class="capacity-note">분기·연간 값은 구성 월이 모두 있을 때만 합산합니다. 모델 증감률은 대응 값이 없거나 이전 값이 0 이하이면 미확인입니다. 2027년 YoY는 2026년 월별 모델이 없어 계산하지 않습니다. 평탄한 연간 가정·같은 월 배분 때문에 모델 YoY가 0%일 수 있으며 이는 관측 사실이 아닙니다. 위의 2026 전체연도 시나리오를 월별로 배분하지 않습니다.</p>';
    }
    $('scenario-view').addEventListener('change',()=>{state.scenarioView=$('scenario-view').value;scenario();});
    $('forecast-frequency').addEventListener('change',()=>{state.forecastFrequency=$('forecast-frequency').value;scenario();});$('lead-months').addEventListener('change',()=>{state.lead=Number($('lead-months').value);scenario();});
    $('stock-adjustment').addEventListener('input',()=>{const el=$('stock-adjustment'),v=Number(el.value);if(el.value.trim()!==''&&finite(v)&&v>=-30&&v<=30){el.setCustomValidity('');state.stock=v;scenario();}});
    $('stock-adjustment').addEventListener('change',()=>{const el=$('stock-adjustment'),v=Number(el.value);if(el.value.trim()===''||!finite(v)||v< -30||v>30){el.value=String(state.stock);el.setCustomValidity('-30%부터 30%까지 입력하세요.');el.reportValidity();return;}el.setCustomValidity('');state.stock=v;scenario();});
    $('scenario-reset').addEventListener('click',()=>{state.lead=0;state.stock=0;$('lead-months').value='0';$('stock-adjustment').value='0';$('stock-adjustment').setCustomValidity('');scenario();});
    $('forecast-csv').addEventListener('click',()=>download(`solar-conditional-scenario-${state.forecastFrequency}.csv`,csv(scenarioRows().map(r=>({...r,frequency:state.forecastFrequency,unit:'GWdc',status:'unvalidated_conditional_scenarios',formula:'procurement=installation_at_period_plus_lead*(1+stock_adjustment_pct/100)',anchor_url:safeURL(forecast.anchor_url),note:'Analyst assumptions; not measured orders/shipments; not a confidence interval'})),['period','frequency','unit','low','base','high','procurement','procurement_reason','installation_period_for_procurement','lead_months','stock_adjustment_pct','comparison_period','base_change_pct','base_change_reason','procurement_change_pct','procurement_change_reason','yoy_period','base_yoy_pct','base_yoy_reason','procurement_yoy_pct','procurement_yoy_reason','status','formula','anchor_url','note'])));
    scenario();
    const statusLabels={construction:'건설 중',construction_complete:'건설 완료 · 가동 예정',planned:'계획',out_of_service:'가동 중단'};
    const ps=[...new Set(data.pipeline.map(r=>r.status))],py=[...new Set(data.pipeline.map(r=>r.year))].sort();
    const pmax=Math.max(0,...py.map(y=>data.pipeline.filter(r=>r.year===y).reduce((s,r)=>s+(finite(r.capacity_ac_mw)?r.capacity_ac_mw:0),0)));
    const bars=py.map(y=>{const rows=data.pipeline.filter(r=>r.year===y),sum=rows.reduce((s,r)=>s+(finite(r.capacity_ac_mw)?r.capacity_ac_mw:0),0);return `<div class="pipeline-bar-row"><span>${esc(y)}</span><div class="pipeline-bar-track">${ps.map((s,i)=>{const v=rows.filter(r=>r.status===s).reduce((a,r)=>a+(finite(r.capacity_ac_mw)?r.capacity_ac_mw:0),0);return `<span style="width:${pmax?v/pmax*100:0}%;background:${COLORS[i%COLORS.length]}" title="${esc(statusLabels[s]||s)} ${fmt(v/1000)} GWac"></span>`;}).join('')}</div><b>${fmt(sum/1000)} GWac</b></div>`;}).join('');
    $('pipeline-content').innerHTML=`<div class="chart-panel"><div class="legend">${ps.map((s,i)=>`<span><i style="background:${COLORS[i%COLORS.length]}"></i>${esc(statusLabels[s]||s)}</span>`).join('')}</div>${bars||'<p class="empty">확보한 계획 물량이 없습니다.</p>'}</div>`+table(['계획 가동연도','상태','발전기 기록 수','용량 (GWac)','DC 용량 미확인 기록'],data.pipeline.map(r=>[esc(r.year),esc(statusLabels[r.status]||r.status),fmt(r.rows,0),finite(r.capacity_ac_mw)?fmt(r.capacity_ac_mw/1000):'미확인',fmt(r.missing_dc_rows,0)]))+`<p class="capacity-note">2026년은 8월 시점 원장에 남은 계획 물량이며 전체연도 신규 설치량이 아닙니다. 계획 발전기의 DC 용량은 미확인으로 보존하고 AC→DC 변환을 하지 않습니다.<br>${esc(data.pipeline_note)}<br>${link(data.pipeline_source,'EIA 860M 계획 발전기 원문',hosts)}</p>`;
    const text=v=>Array.isArray(v)?v.join(' · '):v||'미확인';
    $('coverage-content').innerHTML=data.coverage.map(c=>`<article class="coverage-card"><h3>${esc(COUNTRY[c.country]||c.country)}</h3><dl><dt>확보한 근거</dt><dd>${esc(text(c.resolved))}</dd><dt class="gap">남은 공백</dt><dd>${esc(text(c.gap))}</dd><dt>해석 범위</dt><dd>${esc(text(c.effect))}</dd></dl></article>`).join('');
    $('sources-content').innerHTML=data.sources.map(s=>`<div class="source-row">${link(s.url||s.source_url,s.name||s.id,hosts)}<small>발표일 ${esc(s.published_date||'미확인')}${s.source_date?` · 대상 기간/원문 표기 ${esc(s.source_date)}`:''}${s.updated_date?` · 갱신일 ${esc(s.updated_date)}`:''}${s.retrieved_at?` · 조회일 ${esc(s.retrieved_at)}`:''} · ${esc(s.id)}${s.public_reusable===false?' · 원문 재배포 제외 · 근거 링크만 제공':''}</small></div>`).join('');
    $('dashboard').hidden=false;$('load-state').hidden=true;
  }
  const api={finite,esc,fmt,safeURL,csv,shiftMonth,procure,aggregateScenario,scenarioGrowth,compareAnnual,validate,reason};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  if(global)global.PHXSolarDemand=api;
  if(typeof document!=='undefined'){
    const start=async()=>{try{const response=await fetch('demand-data.json',{credentials:'same-origin'});if(!response.ok)throw new Error('load failed');const text=await response.text();if(text.length>20*1024*1024)throw new Error('payload too large');boot(JSON.parse(text));}catch(_){const status=document.getElementById('load-state');status.textContent='자료를 표시하지 못했습니다. 새로고침 후 다시 확인해 주세요. 불완전한 데이터는 표시하지 않습니다.';status.setAttribute('role','alert');document.getElementById('dashboard').hidden=true;}};
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
  }
})(typeof window!=='undefined'?window:null);
