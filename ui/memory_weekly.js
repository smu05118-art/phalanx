/* ============================================================
   ui/memory_weekly.js — Phalanx Memory 탭 · 주간 리서치 기록 모듈 (2026-09-21 발행분)
   -------------------------------------------------------------
   · 의존성 없음(Chart.js·외부 라이브러리 불사용). 공개 투영본만 읽는다:
       data/memory-weekly/2026-09-21.json  (mem_weekly_build.py 산출)
   · window.PHXMemoryWeekly.mount(main) — #main 의 소매가격 지수 섹션 뒤(스팟 보드 앞)에
     <section id="phxmw-2026-09-21"> 하나만 끼운다. 반복 호출해도 중복되지 않는다.
   · 비동기 응답이 돌아왔을 때 탭이 바뀌었거나(typeof ST, ST.tab!=='mem') 루트가 문서에서
     떨어져 있으면 그리지 않는다.
   · 모든 텍스트는 이스케이프하고 링크는 https 만 허용한다. 스타일은 .phxmw 아래로만 적용한다.
   · 발행일 2026-09-21 의 과거 기록이며 현재 가격이 아니다 — 화면에 날짜를 크게 밝힌다.
   ============================================================ */
(function(){
'use strict';
var VERSION='2026-09-21.1';
if(window.PHXMemoryWeekly&&window.PHXMemoryWeekly.version===VERSION) return;

var EXPECTED_DATE='2026-09-21';
var DATA_URL='data/memory-weekly/'+EXPECTED_DATE+'.json';
var SCHEMA_ID='phx.memory_weekly.public/1';
var ROOT_ID='phxmw-'+EXPECTED_DATE;
var STYLE_ID='phxmw-style';
var ANCHOR_SEL='section[aria-label="메모리 소매가격 지수"]';
var SPOT_HEAD_TEXT='메모리 스팟 보드';

var TABS=[
  {id:'prices', label:'가격 · RDIMM', secs:['spot_prices','rdimm']},
  {id:'supply', label:'공급 · CapEx', secs:['server_dram_supply_demand','capex_bit_model']},
  {id:'micron', label:'Micron · 환율 · PC', secs:['micron','fx','pc_memory']}
];
var FALLBACK_LABELS={
  screenshot_transcribed:'이용자 제공 스크린샷 전사 · 1차 출처 미확인',
  secondary_reported:'2차 보도·재인용 · 1차 출처 미확인',
  model_assumption:'예시 모델 가정 · 측정치 아님',
  primary_verified:'공개 1차 출처 확인',
  derived_explicit:'명시 수치에서 산출'
};

/* ---------- 스타일 (.phxmw 범위로만) ---------- */
var CSS=[
'.phxmw{margin:16px 0 22px;font-size:12.5px;line-height:1.5;color:inherit}',
'.phxmw *{box-sizing:border-box}',
'.phxmw .phxmw-head{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;margin:0 0 4px}',
'.phxmw .phxmw-title{font-size:14px;font-weight:750;margin:0}',
'.phxmw .phxmw-date{display:inline-block;font-family:ui-monospace,monospace;font-weight:750;font-size:13px;padding:3px 10px;border-radius:999px;border:1px solid #d9a441;color:#f3c768;background:rgba(217,164,65,.12);letter-spacing:.02em}',
'.phxmw .phxmw-hist{font-family:ui-monospace,monospace;font-size:10.5px;color:#8a90a8}',
'.phxmw .phxmw-sub{font-family:ui-monospace,monospace;font-size:10.5px;color:#8a90a8;margin:0 0 6px}',
'.phxmw .phxmw-tabs{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 4px;padding:0;list-style:none}',
'.phxmw .phxmw-tab{font:inherit;font-size:11.5px;line-height:1.3;padding:5px 12px;border:1px solid var(--line,#233038);border-radius:999px;background:transparent;color:#8a90a8;cursor:pointer}',
'.phxmw .phxmw-tab[aria-selected="true"]{color:#e9eef5;border-color:#2bc0d4;background:rgba(43,192,212,.12)}',
'.phxmw .phxmw-tab:focus-visible{outline:2px solid #2bc0d4;outline-offset:2px}',
'.phxmw .phxmw-panel[hidden]{display:none}',
'.phxmw .phxmw-card{background:var(--panel,#151d23);border:1px solid var(--line,#233038);border-radius:12px;padding:12px 14px;margin-top:10px}',
'.phxmw .phxmw-h{font-size:13px;font-weight:700;margin:0 0 2px;display:flex;flex-wrap:wrap;align-items:center;gap:4px 6px}',
'.phxmw .phxmw-tw{overflow-x:auto;border:1px solid var(--line,#233038);border-radius:10px;margin-top:6px}',
'.phxmw table{border-collapse:collapse;width:100%;font-size:11.5px}',
'.phxmw th,.phxmw td{padding:5px 8px;border-bottom:1px solid var(--line,#233038);text-align:left;white-space:nowrap;vertical-align:top}',
'.phxmw th{font-weight:600;color:#aab0c4;font-size:10.5px}',
'.phxmw tr:last-child td{border-bottom:none}',
'.phxmw .num{font-family:ui-monospace,monospace;text-align:right}',
'.phxmw .up{color:#2fae66}.phxmw .dn{color:#e06666}',
'.phxmw .grp td{color:#8a90a8;font-family:ui-monospace,monospace;font-size:10.5px;background:rgba(138,144,168,.06)}',
'.phxmw .phxmw-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-top:8px}',
'.phxmw .phxmw-tile{border:1px solid var(--line,#233038);border-radius:10px;padding:9px 11px;border-top:2px solid #5b8def;min-width:0}',
'.phxmw .phxmw-tile.c{border-top-color:#a78bfa}.phxmw .phxmw-tile.s{border-top-color:#f3c768}.phxmw .phxmw-tile.f{border-top-color:#26c6da}',
'.phxmw .phxmw-tile .d{font-family:ui-monospace,monospace;font-size:10.5px;color:#f3c768;font-weight:700}',
'.phxmw .phxmw-tile .k{font-size:11px;color:#aab0c4;margin-top:1px}',
'.phxmw .phxmw-tile .v{font-family:ui-monospace,monospace;font-size:17px;font-weight:750;margin-top:2px;word-break:break-all}',
'.phxmw .phxmw-tile .m{font-family:ui-monospace,monospace;font-size:10.5px;color:#8a90a8}',
'.phxmw .phxmw-badge{display:inline-block;font-family:ui-monospace,monospace;font-size:10px;font-weight:500;padding:1px 7px;border-radius:999px;border:1px solid var(--line,#233038);color:#8a90a8;white-space:nowrap}',
'.phxmw .phxmw-badge.warn{border-color:#d9a441;color:#f3c768}',
'.phxmw .phxmw-badge.ok{border-color:#2fae66;color:#2fae66}',
'.phxmw svg{width:100%;height:auto;display:block;max-width:560px;margin-top:6px}',
'.phxmw .phxmw-note{font-size:11.5px;color:#aab0c4;margin:6px 0 0}',
'.phxmw .phxmw-mono{font-family:ui-monospace,monospace}',
'.phxmw details{margin-top:12px;border:1px dashed var(--line,#233038);border-radius:10px;padding:8px 12px}',
'.phxmw summary{cursor:pointer;font-size:12px;font-weight:700}',
'.phxmw .phxmw-src{margin:8px 0 0;padding:0;list-style:none}',
'.phxmw .phxmw-src li{margin:0 0 8px;padding:0 0 8px;border-bottom:1px solid var(--line,#233038);font-size:11.5px}',
'.phxmw .phxmw-src li:last-child{border-bottom:none}',
'.phxmw .phxmw-src dl{margin:3px 0 0;display:grid;grid-template-columns:max-content 1fr;gap:1px 10px;font-family:ui-monospace,monospace;font-size:10.5px;color:#8a90a8}',
'.phxmw .phxmw-src dt,.phxmw .phxmw-src dd{margin:0}',
'.phxmw .phxmw-msg{padding:12px 14px;border:1px solid var(--line,#233038);border-radius:10px;font-size:12px;margin-top:8px}',
'.phxmw .phxmw-msg.err{border-color:#e06666}',
'.phxmw .phxmw-btn{font:inherit;font-size:11.5px;padding:4px 12px;border-radius:999px;border:1px solid #2bc0d4;color:#2bc0d4;background:transparent;cursor:pointer;margin-left:8px}',
'.phxmw .phxmw-btn:focus-visible{outline:2px solid #2bc0d4;outline-offset:2px}',
'.phxmw a{color:#5b8def}',
'.phxmw ul.phxmw-list{margin:4px 0 0;padding-left:18px}',
'.phxmw ul.phxmw-list li{margin:2px 0}',
'.phxmw .phxmw-cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}',
'@media (max-width:420px){.phxmw{font-size:12px}.phxmw .phxmw-card{padding:10px 11px}.phxmw th,.phxmw td{padding:4px 6px}.phxmw .phxmw-tiles{grid-template-columns:1fr 1fr}.phxmw .phxmw-tile .v{font-size:15px}.phxmw .phxmw-cols{grid-template-columns:1fr}.phxmw .phxmw-src dl{grid-template-columns:1fr}}'
].join('\n');

/* ---------- 유틸 ---------- */
function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
function isNum(v){ return typeof v==='number'&&isFinite(v); }
function fmtNum(v,maxd){ if(!isNum(v)) return '—'; try{ return v.toLocaleString('en-US',{maximumFractionDigits:maxd==null?3:maxd}); }catch(e){ return String(v); } }
function fmtPct(v){ if(!isNum(v)) return '—'; return (v>0?'+':'')+v.toFixed(2)+'%'; }
function sgn(v){ return isNum(v)?(v>0?'up':v<0?'dn':''):''; }
function safeUrl(u){ return (typeof u==='string'&&/^https:\/\/[^\s"'<>]+$/.test(u))?u:null; }
function link(u,text){ var s=safeUrl(u); return s?'<a href="'+esc(s)+'" target="_blank" rel="noopener noreferrer">'+esc(text)+' ↗</a>':esc(text); }
function onMemTab(){ return (typeof ST==='undefined')||!ST||ST.tab==='mem'; }
function alive(el){ return !!(el&&document.body&&document.body.contains(el)); }
function arr(v){ return Array.isArray(v)?v:[]; }
function obj(v){ return (v&&typeof v==='object'&&!Array.isArray(v))?v:{}; }
function badge(status,labels){
  var l=(labels&&labels[status])||FALLBACK_LABELS[status]||status||'상태 미기재';
  var c=status==='primary_verified'?'ok':(status==='model_assumption'||status==='derived_explicit')?'':'warn';
  return '<span class="phxmw-badge '+c+'" title="'+esc('근거 상태: '+l)+'">'+esc(l)+'</span>';
}
function svgText(x,y,t,fill,anchor,size,extra){ return '<text x="'+x+'" y="'+y+'" font-size="'+(size||8)+'" fill="'+fill+'"'+(anchor?' text-anchor="'+anchor+'"':'')+(extra||'')+'>'+esc(t)+'</text>'; }

/* ---------- 상태 ---------- */
var state={data:null,error:null,inflight:null,tab:TABS[0].id};

function fetchJson(url){
  if(typeof window.fetch==='function'){
    return window.fetch(url,{credentials:'same-origin',cache:'no-cache'}).then(function(r){
      if(!r.ok) throw new Error('HTTP '+r.status);
      return r.json();
    });
  }
  return new Promise(function(res,rej){
    try{
      var x=new XMLHttpRequest(); x.open('GET',url,true);
      x.onreadystatechange=function(){ if(x.readyState!==4) return;
        if(x.status>=200&&x.status<300){ try{ res(JSON.parse(x.responseText)); }catch(e){ rej(e); } }
        else rej(new Error('HTTP '+x.status)); };
      x.onerror=function(){ rej(new Error('network error')); };
      x.send();
    }catch(e){ rej(e); }
  });
}
function hasPrivateKey(node,depth){
  if(depth>4||!node||typeof node!=='object') return false;
  var ks=Object.keys(node);
  for(var i=0;i<ks.length;i++){
    if(/private/i.test(ks[i])) return true;
    if(hasPrivateKey(node[ks[i]],depth+1)) return true;
  }
  return false;
}
function validate(d){
  if(!d||typeof d!=='object') return '데이터 형식 오류';
  if(d.schema!==SCHEMA_ID) return '스키마 불일치: '+String(d.schema);
  if(d.visibility!=='public') return '공개본이 아닌 데이터 — 표시 거부';
  if(hasPrivateKey(d,0)) return '비공개 키가 포함된 데이터 — 표시 거부';
  if(d.publication_date!==EXPECTED_DATE) return '발행일 불일치: '+String(d.publication_date);
  if(!d.sections||typeof d.sections!=='object') return '섹션 없음';
  return null;
}
function load(force){
  if(state.data&&!force) return Promise.resolve(state.data);
  if(state.inflight) return state.inflight;
  state.error=null;
  state.inflight=fetchJson(DATA_URL).then(function(d){
    var v=validate(d); if(v) throw new Error(v);
    state.data=d; state.inflight=null; return d;
  },function(e){ state.inflight=null; state.error=e||new Error('unknown'); throw state.error; });
  return state.inflight;
}

/* ---------- 섹션 렌더 ---------- */
function secHead(sec,labels,extraBadge){
  return '<div class="phxmw-h">'+esc(sec.title_ko||sec.id||'')+badge(sec.evidence_status,labels)+(extraBadge||'')+'</div>';
}
function renderReconciliation(rec){
  if(!rec||!arr(rec.differences).length) return '';
  var rows=rec.differences.map(function(r){return '<tr><td>'+esc(r.product)+'</td><td>'+esc(r.observed)+'</td><td class="num">'+fmtNum(r.attachment_price)+'</td><td class="num">'+fmtNum(r.existing_price)+'</td></tr>';}).join('');
  return '<details class="phxmw-reconciliation"><summary>기존 데이터와 값 차이 '+arr(rec.differences).length+'건 · 원인 미확인</summary><p class="phxmw-note">'+esc(rec.note)+'</p><div class="phxmw-tw"><table><thead><tr><th>품목</th><th>관측일</th><th>첨부값 ($)</th><th>기존값 ($/chip)</th></tr></thead><tbody>'+rows+'</tbody></table></div><p class="phxmw-note">대조일 '+esc(rec.checked_date)+' · '+esc(rec.existing_source)+'</p></details>';
}
function renderSpot(sec,labels){
  var items=arr(sec.items); var vin=obj(sec.vintage);
  var groups=[['NAND',vin.observation_nand],['DRAM',vin.observation_dram]];
  var rows='';
  groups.forEach(function(g){
    var its=items.filter(function(it){ return it.category===g[0]; }); if(!its.length) return;
    var obsSet={}; its.forEach(function(it){ if(it.observed) obsSet[it.observed]=1; });
    var obs=Object.keys(obsSet).sort().join(', ')||g[1]||'—';
    rows+='<tr class="grp"><td colspan="5">'+esc(g[0])+' · 관측일 '+esc(obs)+'</td></tr>';
    its.forEach(function(it){
      rows+='<tr><td>'+esc(it.name||it.id)+(it.label_as_printed&&it.label_as_printed!==it.name?' <span class="phxmw-badge" title="첨부 표기">'+esc(it.label_as_printed)+'</span>':'')+'</td>'
        +'<td class="phxmw-mono">'+esc(it.observed||'—')+'</td>'
        +'<td class="num">'+fmtNum(it.price)+'</td>'
        +'<td class="num '+sgn(it.yoy_pct)+'">'+fmtPct(it.yoy_pct)+'</td>'
        +'<td class="num '+sgn(it.wow_pct)+'">'+fmtPct(it.wow_pct)+'</td></tr>';
    });
  });
  if(!rows) return '';
  return '<div class="phxmw-card">'+secHead(sec,labels)
    +'<p class="phxmw-sub">'+esc(obj(sec.source).label||'')+' · 단위 '+esc(sec.unit||'')+'</p>'
    +'<div class="phxmw-tw"><table><thead><tr><th>품목</th><th>관측일</th><th class="num">가격 ('+esc(sec.unit||'')+')</th><th class="num">YoY</th><th class="num">WoW</th></tr></thead><tbody>'+rows+'</tbody></table></div>'
    +'<p class="phxmw-note">NAND와 DRAM의 관측일이 다릅니다('+esc(vin.observation_nand||'—')+' / '+esc(vin.observation_dram||'—')+'). YoY·WoW는 첨부 인쇄값이며 재계산하지 않았습니다. WoW가 없는 품목은 첨부에 값이 없는 것입니다.</p>'
    +renderReconciliation(sec.reconciliation)+'</div>';
}
function renderRdimm(sec,labels){
  var spot=obj(sec.spot), con=obj(sec.contract), spr=obj(sec.spread), unit=sec.unit||'';
  var tiles='';
  arr(spot.items).forEach(function(it){
    tiles+='<div class="phxmw-tile"><div class="d">'+esc(spot.observed||'—')+' 스팟</div><div class="k">'+esc(it.name||it.id)+'</div>'
      +'<div class="v">'+fmtNum(it.price)+' <span class="m">'+esc(unit)+'</span></div>'
      +'<div class="m">WoW <span class="'+sgn(it.wow_pct)+'">'+fmtPct(it.wow_pct)+'</span></div></div>';
  });
  if(con.price!=null){
    tiles+='<div class="phxmw-tile c"><div class="d">'+esc(con.period||'—')+' 계약</div><div class="k">'+esc(con.item||'')+'</div>'
      +'<div class="v">'+fmtNum(con.price)+' <span class="m">'+esc(unit)+'</span></div><div class="m">'+esc(con.period_kind==='month'?'월간 계약가':'계약가')+'</div></div>';
  }
  if(spr.value!=null){
    tiles+='<div class="phxmw-tile s"><div class="d">'+esc(spr.observed||'—')+' 스프레드</div><div class="k">'+esc(spr.item||'')+' 스팟−계약</div>'
      +'<div class="v">'+fmtNum(spr.value)+' <span class="m">'+esc(unit)+'</span></div><div class="m">같은 기록일 기준 인쇄값</div></div>';
  }
  if(!tiles) return '';
  var rule=obj(sec.rules).note;
  return '<div class="phxmw-card">'+secHead(sec,labels)
    +'<p class="phxmw-sub">'+esc(obj(sec.source).label||'')+' · 단위 '+esc(unit)+'</p>'
    +'<div class="phxmw-tiles" role="list">'+tiles+'</div>'
    +'<p class="phxmw-note">타일마다 기준일이 다릅니다. '+(rule?esc(rule):'기록일이 다른 스팟과 계약의 차이는 스프레드가 아닙니다.')+'</p>'
    +'</div>';
}
function svgPairedBars(sec){
  var fcs=arr(sec.forecasts).filter(function(f){ return isNum(f.demand_pct)&&isNum(f.supply_pct_low)&&isNum(f.supply_pct_high); });
  if(!fcs.length) return '';
  var W=360,H=190,padL=34,padR=10,padT=30,padB=22;
  var maxv=0; fcs.forEach(function(f){ maxv=Math.max(maxv,f.demand_pct,f.supply_pct_high); });
  var ymax=Math.max(20,Math.ceil(maxv/20)*20);
  var gw=(W-padL-padR)/fcs.length, bw=Math.min(46,gw*0.28);
  var y=function(v){ return padT+(H-padT-padB)*(1-v/ymax); };
  var o='';
  for(var t=0;t<=ymax;t+=20){ o+='<line x1="'+padL+'" y1="'+y(t).toFixed(1)+'" x2="'+(W-padR)+'" y2="'+y(t).toFixed(1)+'" stroke="var(--line,#233038)" stroke-width=".7"/>'+svgText(padL-4,(y(t)+3).toFixed(1),t+'%','#8a90a8','end'); }
  var aria=[];
  fcs.forEach(function(f,i){
    var cx=padL+gw*(i+0.5), dx=cx-bw-3, sx=cx+3;
    o+='<rect x="'+dx.toFixed(1)+'" y="'+y(f.demand_pct).toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+(y(0)-y(f.demand_pct)).toFixed(1)+'" fill="#5b8def" fill-opacity=".85" stroke="#9db8ff" stroke-dasharray="3 2"/>';
    o+=svgText((dx+bw/2).toFixed(1),(y(f.demand_pct)-4).toFixed(1),'+'+f.demand_pct+'%','#9db8ff','middle',9,' font-weight="700"');
    o+='<rect x="'+sx.toFixed(1)+'" y="'+y(f.supply_pct_low).toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+(y(0)-y(f.supply_pct_low)).toFixed(1)+'" fill="#d9a441" fill-opacity=".85" stroke="#f3c768" stroke-dasharray="3 2"/>';
    var lab='+'+f.supply_pct_low+'%';
    if(f.supply_pct_high>f.supply_pct_low){
      o+='<rect x="'+sx.toFixed(1)+'" y="'+y(f.supply_pct_high).toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+(y(f.supply_pct_low)-y(f.supply_pct_high)).toFixed(1)+'" fill="#d9a441" fill-opacity=".3" stroke="#f3c768" stroke-dasharray="2 2"/>';
      lab='+'+f.supply_pct_low+'~'+f.supply_pct_high+'%';
    }
    o+=svgText((sx+bw/2).toFixed(1),(y(f.supply_pct_high)-4).toFixed(1),lab,'#f3c768','middle',9,' font-weight="700"');
    o+=svgText(cx.toFixed(1),H-6,f.period||'',"#8a90a8",'middle',9);
    aria.push((f.period||'')+' 수요 +'+f.demand_pct+'%, 공급 '+lab);
  });
  o+='<rect x="'+padL+'" y="6" width="9" height="9" fill="#5b8def"/>'+svgText(padL+13,14,'수요 증가율 전망','#aab0c4',null,9)
    +'<rect x="'+(padL+112)+'" y="6" width="9" height="9" fill="#d9a441"/>'+svgText(padL+125,14,'공급 증가율 전망 (범위는 연한 부분)','#aab0c4',null,9);
  return '<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+esc('서버 DRAM 비트 증가율 전망: '+aria.join('; ')+'. 전망치이며 관측치가 아님')+'">'+o+'</svg>';
}
function renderServer(sec,labels){
  var fcs=arr(sec.forecasts); if(!fcs.length) return '';
  var rows=fcs.map(function(f){
    var s=isNum(f.supply_pct_low)&&isNum(f.supply_pct_high)?(f.supply_pct_low===f.supply_pct_high?'+'+f.supply_pct_low+'%':'+'+f.supply_pct_low+'~'+f.supply_pct_high+'%'):'—';
    return '<tr><td class="phxmw-mono">'+esc(f.period||'')+'</td><td class="num">'+(isNum(f.demand_pct)?'+'+f.demand_pct+'%':'—')+'</td><td class="num">'+esc(s)+'</td></tr>';
  }).join('');
  var der=arr(sec.derived).map(function(d){
    return '<li>'+esc(d.period||'')+' 수요−공급 격차 <b class="phxmw-mono">'+fmtNum(d.value_low)+'~'+fmtNum(d.value_high)+' '+esc(d.unit==='percentage points'?'%p':(d.unit||''))+'</b> '+badge(d.evidence_status,labels)+(d.formula?' <span class="phxmw-mono" style="color:#8a90a8">'+esc(d.formula)+'</span>':'')+'</li>';
  }).join('');
  var src=obj(sec.source);
  return '<div class="phxmw-card">'+secHead(sec,labels,'<span class="phxmw-badge">전망치</span>')
    +'<p class="phxmw-sub">'+esc(src.label||'')+(obj(sec.vintage).forecast_issued?' · 전망 발표 '+esc(obj(sec.vintage).forecast_issued):'')+' · 단위 '+esc(sec.unit||'')+'</p>'
    +'<div class="phxmw-cols"><div>'+svgPairedBars(sec)+'</div>'
    +'<div><div class="phxmw-tw"><table><thead><tr><th>기간</th><th class="num">수요</th><th class="num">공급</th></tr></thead><tbody>'+rows+'</tbody></table></div>'
    +(der?'<ul class="phxmw-list">'+der+'</ul>':'')+'</div></div>'
    +(sec.note?'<p class="phxmw-note">'+esc(sec.note)+'</p>':'')
    +'</div>';
}
function svgRatio(sec){
  var s=arr(obj(sec.ratio).series).filter(function(p){ return isNum(p.value)&&p.year!=null; });
  if(!s.length) return '';
  var W=560,H=190,padL=30,padR=14,padT=22,padB=24;
  var max=0; s.forEach(function(p){ if(p.value>max) max=p.value; });
  var ymax=Math.max(1,Math.ceil(max)); var step=ymax>5?2:1;
  var x=function(i){ return padL+(W-padL-padR)*(s.length===1?0.5:i/(s.length-1)); };
  var y=function(v){ return padT+(H-padT-padB)*(1-v/ymax); };
  var o='';
  for(var t=0;t<=ymax;t+=step){ o+='<line x1="'+padL+'" y1="'+y(t).toFixed(1)+'" x2="'+(W-padR)+'" y2="'+y(t).toFixed(1)+'" stroke="var(--line,#233038)" stroke-width=".7"/>'+svgText(padL-4,(y(t)+3).toFixed(1),String(t),'#8a90a8','end'); }
  var pts=s.map(function(p,i){ return x(i).toFixed(1)+','+y(p.value).toFixed(1); }).join(' ');
  o+='<polyline points="'+pts+'" fill="none" stroke="#f3c768" stroke-width="1.6" stroke-dasharray="6 4"/>';
  s.forEach(function(p,i){
    o+='<circle cx="'+x(i).toFixed(1)+'" cy="'+y(p.value).toFixed(1)+'" r="3" fill="var(--panel,#151d23)" stroke="#f3c768" stroke-width="1.4"/>'
      +svgText(x(i).toFixed(1),(y(p.value)-7).toFixed(1),fmtNum(p.value,2),'#e9eef5','middle',8)
      +svgText(x(i).toFixed(1),H-7,String(p.year),'#8a90a8','middle',8);
  });
  o+='<line x1="'+padL+'" y1="9" x2="'+(padL+22)+'" y2="9" stroke="#f3c768" stroke-width="1.6" stroke-dasharray="6 4"/>'+svgText(padL+27,12,'예시 모델 비율 (점선) · 측정치 아님 · '+(obj(sec.ratio).unit||''),'#aab0c4',null,9);
  var aria=s.map(function(p){ return p.year+' '+fmtNum(p.value,2); }).join(', ');
  return '<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+esc('DRAM CapEx 대 모델 비트 증가율 비율(예시 모델, '+(obj(sec.ratio).unit||'')+'): '+aria)+'">'+o+'</svg>';
}
function renderCapex(sec,labels){
  var ratio=obj(sec.ratio), ref=obj(sec.capex_forecast_reference), mi=obj(sec.model_inputs_labelled), vin=obj(sec.vintage);
  var series=arr(ratio.series);
  if(!series.length&&!ref.values) return '';
  var cells=series.map(function(p){ return '<td class="num">'+fmtNum(p.value,2)+'</td>'; }).join('');
  var heads=series.map(function(p){ return '<th class="num">'+esc(String(p.year||''))+'</th>'; }).join('');
  var inputs='';
  var bg=obj(mi.bit_growth_pct), cx=obj(mi.capex_usd_bn);
  Object.keys(bg).sort().forEach(function(k){ if(isNum(bg[k])) inputs+='<li>'+esc(k)+' 모델 비트 증가율 가정 <b class="phxmw-mono">'+fmtNum(bg[k],2)+'%</b></li>'; });
  Object.keys(cx).sort().forEach(function(k){ if(isNum(cx[k])) inputs+='<li>'+esc(k)+' DRAM CapEx 가정 <b class="phxmw-mono">'+fmtNum(cx[k],2)+' USD bn</b></li>'; });
  var refHtml='';
  if(ref.publisher){
    var vals=obj(ref.values); var vtxt=Object.keys(vals).sort().map(function(k){ return k+' '+fmtNum(vals[k],2); }).join(' · ');
    refHtml='<p class="phxmw-note">CapEx 가정의 출처: '+link(ref.url,ref.publisher+' '+(ref.published||''))+' '+badge(ref.evidence_status,labels)
      +(vtxt?' — <span class="phxmw-mono">'+esc(vtxt)+' '+esc(ref.unit||'')+'</span>':'')
      +(ref.stated?'<br>'+esc(ref.stated):'')+(ref.vintage_note?'<br><span style="color:#8a90a8">'+esc(ref.vintage_note)+'</span>':'')+'</p>';
  }
  return '<div class="phxmw-card">'+secHead(sec,labels,vin.model_vintage?'<span class="phxmw-badge">모델 빈티지 '+esc(vin.model_vintage)+'</span>':'')
    +'<p class="phxmw-sub">'+esc(obj(sec.source).label||'')+(ratio.unit?' · 단위 '+esc(ratio.unit):'')+'</p>'
    +svgRatio(sec)
    +(series.length?'<div class="phxmw-tw"><table><thead><tr><th>연도</th>'+heads+'</tr></thead><tbody><tr><td>비율</td>'+cells+'</tr></tbody></table></div>':'')
    +(ratio.definition?'<p class="phxmw-note">'+esc(ratio.definition)+(ratio.caveat?' — '+esc(ratio.caveat):'')+'</p>':'')
    +(inputs?'<ul class="phxmw-list">'+inputs+'</ul>':'')
    +(mi.note?'<p class="phxmw-note">'+esc(mi.note)+'</p>':'')
    +refHtml+'</div>';
}
function renderMicron(sec,labels){
  var qs=arr(sec.quarters), nc=obj(sec.net_capex);
  if(!qs.length&&nc.value==null) return '';
  var rows=qs.map(function(q){ return '<tr><td class="phxmw-mono">'+esc(q.fq||'')+'</td><td>'+esc(q.dram_bit_qoq_label||'—')+'</td><td>'+esc(q.dram_asp_qoq_label||'—')+'</td></tr>'; }).join('');
  var src=obj(sec.source);
  return '<div class="phxmw-card">'+secHead(sec,labels)
    +'<p class="phxmw-sub">'+esc(src.label||'')+(sec.fiscal_note?' · '+esc(sec.fiscal_note):'')+'</p>'
    +'<div class="phxmw-cols"><div>'
    +(rows?'<div class="phxmw-tw"><table><thead><tr><th>회계분기</th><th>DRAM 비트 출하 QoQ (원문 표현)</th><th>DRAM ASP QoQ (원문 표현)</th></tr></thead><tbody>'+rows+'</tbody></table></div>':'')
    +(sec.label_basis?'<p class="phxmw-note">'+esc(sec.label_basis)+'</p>':'')
    +'</div><div>'
    +(nc.value!=null?'<div class="phxmw-tile f" style="margin-top:6px"><div class="d">'+esc(nc.fq||'')+(nc.quarter_end?' · 분기 종료 '+esc(nc.quarter_end):'')+'</div><div class="k">전사 순설비투자 (별도 항목)</div>'
      +'<div class="v">'+fmtNum(nc.value,3)+' <span class="m">'+esc(nc.unit||'')+'</span></div>'
      +(nc.scope?'<div class="m">'+esc(nc.scope)+'</div>':'')+(nc.note?'<div class="m">'+esc(nc.note)+'</div>':'')+'</div>':'')
    +'</div></div>'
    +(src.verification_note?'<p class="phxmw-note">'+esc(src.verification_note)+'</p>':'')
    +'</div>';
}
function renderFx(sec,labels){
  var obs=arr(sec.observations).filter(function(o){ return isNum(o.value); }); if(!obs.length) return '';
  var ch=obj(sec.change), unit=sec.unit||'';
  var tiles=obs.map(function(o){ return '<div class="phxmw-tile f"><div class="d">'+esc(o.date||'—')+'</div><div class="k">USD/KRW 기준환율</div><div class="v">'+fmtNum(o.value,2)+' <span class="m">'+esc(unit)+'</span></div></div>'; }).join('');
  if(isNum(ch.pct)) tiles+='<div class="phxmw-tile s"><div class="d">'+esc(ch.from||'')+' → '+esc(ch.to||'')+'</div><div class="k">변화 (첨부 인쇄값)</div><div class="v '+sgn(ch.pct)+'">'+fmtPct(ch.pct)+'</div>'+(ch.label_as_printed?'<div class="m">첨부 표기 '+esc(ch.label_as_printed)+'</div>':'')+'</div>';
  return '<div class="phxmw-card">'+secHead(sec,labels)
    +'<p class="phxmw-sub">'+esc(obj(sec.source).label||'')+' · 단위 '+esc(unit)+'</p>'
    +'<div class="phxmw-tiles">'+tiles+'</div>'
    +'<p class="phxmw-note">'+(sec.series_kind==='two_observations_only'?'두 관측치만 기록했습니다. 일별 시계열은 없으며 보간하지 않았습니다. ':'')+(ch.basis?esc(ch.basis):'')+'</p>'
    +'</div>';
}
function renderPc(sec,labels){
  var sts=arr(sec.statements); if(!sts.length) return '';
  var rows=sts.map(function(s){
    var rng=isNum(s.value_low_pct)&&isNum(s.value_high_pct)?' <span class="phxmw-mono">'+fmtNum(s.value_low_pct)+'~'+fmtNum(s.value_high_pct)+'%</span>':'';
    var kind=s.kind==='company_outlook_not_realized_price'?' <span class="phxmw-badge warn">회사 전망 · 실현 가격 아님</span>':(s.kind==='company_outlook'?' <span class="phxmw-badge">회사 전망</span>':'');
    return '<tr><td>'+esc(s.topic||'')+'</td><td><b>'+esc(s.label_ko||'')+'</b>'+rng+kind+'<div class="phxmw-mono" style="color:#8a90a8;font-size:10.5px">'+esc(s.label||'')+'</div></td></tr>';
  }).join('');
  var src=obj(sec.source), vin=obj(sec.vintage);
  return '<div class="phxmw-card">'+secHead(sec,labels,'<span class="phxmw-badge">경영진 발언</span>')
    +'<p class="phxmw-sub">'+esc(src.label||'')+(vin.statement?' · 발언 '+esc(vin.statement):'')+(vin.report?' · 보도 '+esc(vin.report):'')+'</p>'
    +'<div class="phxmw-tw"><table><thead><tr><th>항목</th><th>발언 내용</th></tr></thead><tbody>'+rows+'</tbody></table></div>'
    +(sec.divergence_note_ko?'<p class="phxmw-note">'+esc(sec.divergence_note_ko)+'</p>':'')
    +'</div>';
}
var RENDER={spot_prices:renderSpot,rdimm:renderRdimm,server_dram_supply_demand:renderServer,capex_bit_model:renderCapex,micron:renderMicron,fx:renderFx,pc_memory:renderPc};

function renderDetails(data){
  var secs=obj(data.sections), labels=obj(data.evidence_status_labels), ev=obj(data.evidence), wh=obj(data.withheld), gen=obj(data.generated_from);
  var li='';
  Object.keys(secs).forEach(function(id){
    var s=secs[id]; if(!s||typeof s!=='object') return;
    var src=obj(s.source), vin=obj(s.vintage);
    var dl='';
    Object.keys(vin).sort().forEach(function(k){ dl+='<dt>'+esc(k)+'</dt><dd>'+esc(vin[k])+'</dd>'; });
    if(src.attachment) dl+='<dt>첨부</dt><dd>'+esc(src.attachment)+' (스크린샷 원본은 공개하지 않음)</dd>';
    dl+='<dt>링크</dt><dd>'+(safeUrl(src.url)?link(src.url,'1차 출처'):esc(src.url_status==='not_supplied'?'URL 미제공 — 추측하지 않음':(src.url_status||'없음')))+'</dd>';
    var om=arr(s.omitted).map(function(o){ return '<li>'+esc(o)+'</li>'; }).join('');
    li+='<li><b>'+esc(s.title_ko||id)+'</b> '+badge(s.evidence_status,labels)+'<div>'+esc(src.label||'')+'</div><dl>'+dl+'</dl>'
      +(src.verification_note?'<div style="color:#8a90a8">'+esc(src.verification_note)+'</div>':'')
      +(om?'<div style="margin-top:3px;color:#8a90a8">전사하지 않은 것</div><ul class="phxmw-list">'+om+'</ul>':'')+'</li>';
  });
  var oms=arr(data.omissions).map(function(o){ return '<li>'+esc(o)+'</li>'; }).join('');
  return '<details><summary>데이터 출처 · 검증 상태 · 제외 항목</summary>'
    +'<p class="phxmw-note">'+esc(ev.note||'')+(ev.attachments_count!=null?' 첨부 '+esc(ev.attachments_count)+'장. ':' ')+(ev.independently_verified===false?'독립 검증되지 않은 자료입니다.':'')+'</p>'
    +(data.record_note?'<p class="phxmw-note">'+esc(data.record_note)+'</p>':'')
    +'<ul class="phxmw-src">'+li+'</ul>'
    +(wh.count?'<p class="phxmw-note"><b>공개 제외 '+esc(wh.count)+'건</b> — '+esc(wh.notice||'')+'</p>':'')
    +(oms?'<p class="phxmw-note" style="margin-bottom:0">전체 제외·미전사 목록</p><ul class="phxmw-list">'+oms+'</ul>':'')
    +'</details>';
}

function render(root,data){
  var secs=obj(data.sections), labels=obj(data.evidence_status_labels);
  var tabs=TABS.map(function(t){
    var html=t.secs.map(function(id){ var fn=RENDER[id]; var s=secs[id]; if(!fn||!s||typeof s!=='object') return ''; try{ return fn(s,labels)||''; }catch(e){ return '<div class="phxmw-msg err">'+esc(id)+' 섹션 렌더 오류</div>'; } }).join('');
    return {id:t.id,label:t.label,html:html};
  }).filter(function(t){ return t.html; });
  var head='<div class="phxmw-head"><p class="phxmw-title">📚 주간 리서치 기록 — '+esc(data.title||'메모리 주간 업데이트')+'</p>'
    +'<span class="phxmw-date" aria-label="발행일 '+esc(data.publication_date)+'">'+esc(data.publication_date)+' 발행</span>'
    +'<span class="phxmw-hist">과거 기록 · 발행 시점 값 그대로 · 현재 가격 아님</span></div>'
    +'<p class="phxmw-sub">출처 표기 '+esc(data.publisher_as_labelled||'—')+' · 이용자 제공 스크린샷 전사 · 1차 출처가 확인된 항목만 링크</p>';
  if(!tabs.length){ root.innerHTML=head+'<div class="phxmw-msg">표시할 섹션이 없습니다.</div>'; return; }
  if(!tabs.some(function(t){ return t.id===state.tab; })) state.tab=tabs[0].id;
  var tl='<div class="phxmw-tabs" role="tablist" aria-label="주간 리서치 기록 섹션">'+tabs.map(function(t){
    var on=t.id===state.tab;
    return '<button type="button" class="phxmw-tab" role="tab" id="'+ROOT_ID+'-tab-'+t.id+'" aria-controls="'+ROOT_ID+'-panel-'+t.id+'" aria-selected="'+(on?'true':'false')+'" tabindex="'+(on?'0':'-1')+'" data-phxmw-tab="'+t.id+'">'+esc(t.label)+'</button>';
  }).join('')+'</div>';
  var panels=tabs.map(function(t){
    return '<div class="phxmw-panel" role="tabpanel" id="'+ROOT_ID+'-panel-'+t.id+'" aria-labelledby="'+ROOT_ID+'-tab-'+t.id+'"'+(t.id===state.tab?'':' hidden')+'>'+t.html+'</div>';
  }).join('');
  root.innerHTML=head+tl+panels+renderDetails(data);
  var btns=Array.prototype.slice.call(root.querySelectorAll('[data-phxmw-tab]'));
  function select(id,focus){
    state.tab=id;
    btns.forEach(function(b){ var on=b.getAttribute('data-phxmw-tab')===id; b.setAttribute('aria-selected',on?'true':'false'); b.tabIndex=on?0:-1; if(on&&focus) b.focus(); });
    Array.prototype.forEach.call(root.querySelectorAll('.phxmw-panel'),function(p){ var on=p.id===ROOT_ID+'-panel-'+id; if(on) p.removeAttribute('hidden'); else p.setAttribute('hidden',''); });
  }
  btns.forEach(function(b,i){
    b.onclick=function(){ select(b.getAttribute('data-phxmw-tab'),false); };
    b.onkeydown=function(e){
      var k=e.key, j=null;
      if(k==='ArrowRight') j=(i+1)%btns.length; else if(k==='ArrowLeft') j=(i-1+btns.length)%btns.length;
      else if(k==='Home') j=0; else if(k==='End') j=btns.length-1; else return;
      e.preventDefault(); select(btns[j].getAttribute('data-phxmw-tab'),true);
    };
  });
}
function renderLoading(root){ root.innerHTML='<div class="phxmw-head"><p class="phxmw-title">📚 주간 리서치 기록</p><span class="phxmw-date">'+esc(EXPECTED_DATE)+' 발행</span></div><div class="phxmw-msg" role="status" aria-live="polite">⏳ 주간 기록 불러오는 중…</div>'; }
function renderError(root,err){
  var msg=(err&&err.message)?String(err.message):'알 수 없는 오류';
  root.innerHTML='<div class="phxmw-head"><p class="phxmw-title">📚 주간 리서치 기록</p><span class="phxmw-date">'+esc(EXPECTED_DATE)+' 발행</span></div>'
    +'<div class="phxmw-msg err" role="alert">주간 기록을 불러오지 못했습니다 <span class="phxmw-mono">('+esc(msg)+')</span>'
    +'<button type="button" class="phxmw-btn" data-phxmw-retry>다시 시도</button></div>';
  var b=root.querySelector('[data-phxmw-retry]');
  if(b) b.onclick=function(){ state.error=null; renderLoading(root); run(root,true); };
}
function run(root,force){
  load(force).then(function(d){ if(!alive(root)||!onMemTab()) return; render(root,d); },
                   function(e){ if(!alive(root)||!onMemTab()) return; renderError(root,e); });
}
function injectStyle(){
  if(document.getElementById(STYLE_ID)) return;
  var st=document.createElement('style'); st.id=STYLE_ID; st.textContent=CSS;
  (document.head||document.documentElement).appendChild(st);
}
function createRoot(main){
  var root=document.createElement('section');
  root.id=ROOT_ID; root.className='phxmw'; root.setAttribute('aria-label','주간 리서치 기록 '+EXPECTED_DATE);
  var anchor=main.querySelector(ANCHOR_SEL);
  if(anchor&&anchor.parentNode===main){ main.insertBefore(root,anchor.nextSibling); return root; }
  var ps=main.querySelectorAll('p');
  for(var i=0;i<ps.length;i++){ if(ps[i].parentNode===main&&(ps[i].textContent||'').indexOf(SPOT_HEAD_TEXT)>=0){ main.insertBefore(root,ps[i]); return root; } }
  main.appendChild(root);
  return root;
}
function mount(main){
  if(!main||!main.querySelector||!onMemTab()) return null;
  injectStyle();
  var root=main.querySelector('#'+ROOT_ID)||createRoot(main);
  if(state.data){ render(root,state.data); return root; }
  if(state.error&&!state.inflight){ renderError(root,state.error); return root; }
  renderLoading(root);
  run(root,false);
  return root;
}
function unmount(main){ var r=(main||document).querySelector('#'+ROOT_ID); if(r&&r.parentNode) r.parentNode.removeChild(r); }

window.PHXMemoryWeekly={version:VERSION,date:EXPECTED_DATE,dataUrl:DATA_URL,mount:mount,unmount:unmount,reload:function(){ state.data=null; state.error=null; return load(true); }};
})();
