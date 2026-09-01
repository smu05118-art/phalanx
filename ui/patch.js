/* ============================================================
   Phalanx UI Patch v1 — 2026-08-26 UX 감사(확정 47건) 반영 프론트 패치 레이어
   -------------------------------------------------------------
   index.html은 로컬 빌더 산출물이라 직접 수정하면 크론이 되돌린다.
   이 파일은 index.html 로드 후 전역 함수를 오버라이드하는 방식으로
   UI 개선을 적용한다. 각 모듈은 try/catch로 격리 — 실패 시 원본 동작 유지.
   빌더 템플릿에 병합되면 해당 모듈을 이 파일에서 제거하면 된다.
   페어 파일: ui/patch.css · 문서: ui/README.md
   ============================================================ */
(function(){
'use strict';
if(window.__PHX_PATCH__) return; window.__PHX_PATCH__='v1';
if(typeof ST==='undefined'||typeof render!=='function'||typeof regionObj!=='function'){
  console.warn('[ui-patch] 필수 전역 없음 — 패치 중단'); return;
}
function safe(name,fn){ try{ return fn(); }catch(e){ console.warn('[ui-patch]',name,e); } }
function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function stripTags(s){ return String(s||'').replace(/<[^>]+>/g,''); }

/* ---------- 공용 상수 (P0-06 · P1-03: 리전 공개용 문구/이름) ---------- */
var SRC_SHORT={
  JP:'출처: 일본 재무성 무역통계(세관×품목×국가)', TH:'출처: 태국 관세청 수출입',
  KR:'출처: 한국 관세청(확정) + TRASS 잠정', TW:'출처: 대만 증권거래소 월매출 공시(TWSE MOPS)',
  TWX:'출처: 대만 전상장 테크 월매출 공시(MOPS 전수)', TWI:'출처: 대만 상장 산업재 월매출 공시(MOPS)',
  TWC:'출처: 대만 상장 소비·서비스 월매출 공시(MOPS)', JPC:'출처: 일본 상장 소비기업 월차 공시',
  JPT:'출처: 일본 상장 테크 월차 공시', JPI:'출처: 일본 상장 산업재 월차 공시',
  US:'출처: 미국 수출입 통계', TWT:'출처: UN Comtrade 대만 미러 통계', CN:'출처: 중국 수출입 통계',
  ALT:'출처: 대체데이터 종합', ENT:'출처: K-엔터 레이블 지표', TC:'출처: 관세청 TRASS 기업수출(소비재)',
  TB:'출처: 관세청 TRASS 기업수출(산업재)', COS:'출처: 화장품 밸류체인 종합'};
var REG_NAME={ TW:'기업매출 · 핵심', TWX:'기업매출 · 테크 전수', TWI:'기업매출 · 산업재',
  TWC:'기업매출 · 소비/서비스', TWT:'수출입 (관세 미러)', JP:'수출입 (세관 프록시)',
  JPT:'기업매출 · 테크 월차', JPI:'기업매출 · 산업재 월차', JPC:'기업매출 · 소비/서비스',
  KR:'수출입 (관세)', TC:'기업수출 · 소비재 (TRASS)', TB:'기업수출 · 산업재 (TRASS)',
  ENT:'K-엔터 레이블', COS:'화장품 허브', US:'미국 수출입', CN:'중국 수출입', TH:'태국 수출입', ALT:'Alt-Data'};
var REG_COLS=[ ['🇹🇼 대만',['TW','TWX','TWI','TWC','TWT']], ['🗾 일본',['JP','JPT','JPI','JPC']],
  ['🇰🇷 한국',['KR','TC','TB','COS','ENT']], ['🌏 기타·글로벌',['US','CN','TH','ALT']] ];

function subYM(ym){ return ym?String(ym).slice(0,4)+'.'+String(ym).slice(5,7):''; }
function koLabel(s){ return s==='All'?'전체':s; }
var _lpCache={};
function lastPubYM(){                                   /* P1-08: 리전별 실제 마지막 공표월 */
  var reg=ST.region; if(_lpCache[reg]) return _lpCache[reg];
  var lb=regionObj().last_pub;                          /* 빌더 주입값 우선 (있으면) */
  if(lb) return _lpCache[reg]=lb;
  var last=-1;
  safe('lp:detail',function(){ if(window.PSH&&window.PSH[reg]&&typeof ncLastIdx==='function')
    last=Math.max(last,ncLastIdx(reg)); });               /* PSH 선행 가드 — _NCFIX 캐시 오염 방지 */
  safe('lp:rev',function(){ (P.companies||[]).forEach(function(c){ if((c.region||'JP')!==reg) return;
    var a=c.revenue||[]; for(var i=a.length-1;i>last;i--){ if(a[i]){ last=i; break; } } }); });
  if(last<0||!MONTHS[last]) return null;                  /* 미로드·실패 리전 — 캐시하지 않고 다음 렌더에 재계산 */
  return _lpCache[reg]=MONTHS[last];
}

/* ---------- 모듈 0. 캔버스 DPR 상한 (R2-32) ----------
   216포인트 밀집 막대차트는 막대 폭이 1~2px라 DPR 2의 이점이 거의 없는데
   인스턴스 60개분 래스터 비용을 그대로 낸다. 1.5로 캡하면 백킹 픽셀 44% 감소.
   축 라벨이 8~9px이므로 1.5 미만으로 내리면 눈금이 뭉개진다. */
/* 전역 Chart.defaults에 걸면 근거 없는 타 탭 대형 차트까지 흐려진다 →
   모듈 11e 플러그인이 카드·상세 캔버스에만 적용한다. */

/* ---------- 최근 본 기업 (P2-01) ---------- */
var RKEY='phx_recent_v1';
function getRecent(){ try{ return JSON.parse(localStorage.getItem(RKEY))||[]; }catch(e){ return []; } }
function pushRecent(id){ try{ var a=getRecent().filter(function(x){return x!==id;});
  a.unshift(id); localStorage.setItem(RKEY,JSON.stringify(a.slice(0,6))); }catch(e){} }
document.addEventListener('click',function(e){
  var t=e.target; if(!t||!t.closest) return;
  if(t.closest('#main .card.co')) ST._ovScroll=window.scrollY;  /* 복귀 스크롤용 — 방문 기록은 render 래퍼가 뷰 전환 감지로 수행(별표·차트 클릭 오기록 방지) */
},true);

/* ---------- 접근성 헬퍼 (P1-14) ---------- */
var A11Y_SEL='.tab,.pill,.regbtn,.regsel,.regitem,.catgrp,.catchip,.catco,.phx-chip';
function a11y(root){ safe('a11y',function(){ (root||document).querySelectorAll(A11Y_SEL).forEach(function(el){
  if(el.tabIndex<0||!el.hasAttribute('tabindex')) el.tabIndex=0;
  if(!el.getAttribute('role')) el.setAttribute('role','button'); }); }); }
document.addEventListener('keydown',function(e){
  if((e.key==='Enter'||e.key===' ')&&e.target&&e.target.matches&&e.target.matches(A11Y_SEL)){
    e.preventDefault(); e.target.click(); } });

/* ============================================================
   모듈 1. 탭 재편 — 4그룹 + 한글 라벨 + 전 탭 툴팁 (P1-02/10/11 · P0-01)
   ============================================================ */
var TAB_LOADER={lux:'loadLux',mem:'loadMem',rack:'loadRack',dc:'loadDC',tech:'loadTech',bio:'loadBio',
  ecal:'loadEcal',tmap:'loadTmap',ppi:'loadPpi',game:'loadGame',app:'loadApparel',ops:'loadOps',
  plat:'loadPlat',kpi:'loadKpi',comm:'loadComm',ai:'loadAI',ins:'loadIns'};
var TAB_DEFS=[
 ['기업',[
   ['dash','대시보드','현재 리전의 기업 카드·차트 일람'],
   ['ecal','📅 실적 캘린더','실적 발표 일정 캘린더'],
   ['nowcast','🔮 선행 랭킹','세관·월매출 프록시로 분기 실적을 발표 전에 추정한 기업 랭킹'],
   ['watch','★ 관심기업','별표한 기업 모음 · 신규 기업 등록']]],
 ['AI 인프라',[
   ['mem','메모리','DRAM·NAND·HBM 밸류체인 프록시'],
   ['rack','서버·랙','AI 서버 랙 밸류체인'],
   ['dc','데이터센터','데이터센터 전력·설비·프로젝트 맵'],
   ['ai','AI·클라우드','AI 캐펙스·클라우드 지표'],
   ['tmap','공급망 지도','AI 인프라 공급망 그래프'],
   ['tech','테크 지도','AI 인프라 밸류체인 × 프록시 모멘텀']]],
 ['소비',[
   ['lux','럭셔리','글로벌 럭셔리 실적·프록시'],
   ['game','게임','게임사 대체데이터 나우캐스트'],
   ['app','의류','브랜드×ODM 의류 밸류체인 (대만 월매출이 1~2개월 선행)'],
   ['plat','플랫폼','플랫폼 기업 지표']]],
 ['매크로·도구',[
   ['ppi','생산자물가','산업별 생산자물가(PPI)'],
   ['comm','원자재','원자재 가격 보드'],
   ['kpi','산업KPI','산업 지표 대시보드'],
   ['bio','바이오 지도','바이오 밸류체인 지도'],
   ['ins','인사이트','크로스데이터 인사이트 노트'],
   ['ops','🩺 상태','데이터 파이프라인 수집 상태']]]];
safe('tabs',function(){
  var tb=document.getElementById('tabs'); if(!tb) return;
  var known={}; tb.querySelectorAll('.tab').forEach(function(t){ known[t.dataset.tab]=t.textContent; });
  var h='';
  TAB_DEFS.forEach(function(g){
    h+='<span class="tabgrp-l">'+esc(g[0])+'</span>';
    g[1].forEach(function(t){ if(!(t[0] in known)) return;              /* 빌더에 없는 탭은 생략 */
      if(TAB_LOADER[t[0]]&&typeof window[TAB_LOADER[t[0]]]!=='function'){ /* 렌더러 미구현 탭(현재 ecal·tmap·ppi)은 숨김 — 클릭 시 크래시 방지, 빌더 복원 시 자동 재노출 */
        delete known[t[0]]; return; }
      delete known[t[0]];
      h+='<span class="tab'+(ST.tab===t[0]?' on':'')+'" data-tab="'+t[0]+'" title="'+esc(t[2])+'">'+esc(t[1])+'</span>'; });
  });
  Object.keys(known).forEach(function(id){                              /* 빌더가 새로 추가한 미지의 탭 보존 */
    h+='<span class="tab'+(ST.tab===id?' on':'')+'" data-tab="'+id+'">'+esc(known[id])+'</span>'; });
  tb.innerHTML=h;
  tb.querySelectorAll('.tab').forEach(function(t){ t.onclick=function(){
    if(window.__phxCancelSearch) window.__phxCancelSearch();
    ST.tab=t.dataset.tab; ST.view='overview'; ST.company=null; ST.q=''; ST._ovScroll=0;
    var q=document.getElementById('q'); if(q) q.value=''; render(); window.scrollTo(0,0); }; });
});

/* ============================================================
   모듈 2. 리전 드롭다운 (P1-01 · P1-03 · P1-13 · P0-10/15)
   ============================================================ */
safe('regions',function(){
  window.renderRegions=function(){
    var rr=document.getElementById('regionRow'); if(!rr) return;
    rr.style.display=(ST.view==='overview')?'flex':'none';
    var cur=regionObj();
    var n=(P.companies||[]).filter(function(c){return (c.region||'JP')===ST.region&&!c.hid;}).length||cur.n||0;
    rr.innerHTML='<button class="regsel" id="regSel" title="데이터셋 전환 — '+esc(stripTags(cur.source||''))+'">'
      +'<span class="rf">'+(cur.flag||'')+'</span>'+esc(cur.label)
      +(n?'<span class="rn">'+n+'사</span>':'')+'<i>▾</i></button>'
      +'<div class="regmenu" id="regMenu" hidden></div>'
      +'<span class="phx-fresh" id="phxFresh"></span>';
    var menu=rr.querySelector('#regMenu');
    menu.innerHTML=REG_COLS.map(function(col){
      var items=col[1].map(function(id){
        var r=REGIONS.find(function(x){return x.id===id;}); if(!r) return '';
        return '<span class="regitem'+(r.id===ST.region?' on':'')+'" data-r="'+r.id+'" '
          +'title="'+esc(stripTags(r.source||''))+'">'
          +'<span class="bz'+(r.biz==='B2C'?' c':'')+'"></span>'+esc(REG_NAME[r.id]||r.label)
          +(r.n?' <small>'+r.n+'사</small>':'')
          +(r.loaded===false?' <small>⏳ 대기</small>':'')+'</span>';
      }).join('');
      if(col[0].indexOf('한국')>=0)
        items+='<span class="regitem ext" data-ext="krtrade" title="관세청 HS6 상세 — 총괄·분류·급등락·기업 확정치">수출입 상세 (관세청 HS6) ↗</span>';
      return '<div class="regcol"><b>'+col[0]+'</b>'+items+'</div>';
    }).join('');
    var missing=REGIONS.filter(function(r){ return !REG_COLS.some(function(c){return c[1].indexOf(r.id)>=0;}); });
    if(missing.length)                                                   /* 빌더가 새 리전 추가 시 자동 노출 */
      menu.innerHTML+='<div class="regcol"><b>기타</b>'+missing.map(function(r){
        return '<span class="regitem'+(r.id===ST.region?' on':'')+'" data-r="'+r.id+'">'
          +'<span class="bz'+(r.biz==='B2C'?' c':'')+'"></span>'+esc(r.label)+'</span>'; }).join('')+'</div>';
    rr.querySelector('#regSel').onclick=function(){ menu.hidden=!menu.hidden; };
    menu.querySelectorAll('[data-r]').forEach(function(el){ el.onclick=function(){
      var id=el.dataset.r; menu.hidden=true;
      if(ST.region===id){ if(ST.tab!=='dash'){ ST.tab='dash'; render(); } return; }
      el.classList.add('busy');
      window.__phxRegionSwitch=true;                       /* 로딩 문구는 드롭다운 리전 전환에서만 */
      loadRegion(id,function(){ ST.region=id; ST.cat='all'; ST.company=null; ST.view='overview';
        ST.q=''; ST.tab='dash'; ST._ovScroll=0;
        var q=document.getElementById('q'); if(q) q.value='';
        applyRegion(); buildCurRow(); render(); window.scrollTo(0,0); }); }; });
    var ext=menu.querySelector('[data-ext="krtrade"]');
    if(ext) ext.onclick=function(){ menu.hidden=true;
      var b=document.getElementById('krTradeBtn'); if(b) b.click(); };
    a11y(rr);
  };
  document.addEventListener('click',function(e){
    var menu=document.getElementById('regMenu');
    if(menu&&!menu.hidden&&e.target&&e.target.closest&&!e.target.closest('#regionRow')) menu.hidden=true; });
});

/* ---------- 리전 전환 로딩 피드백 (P0-15) ---------- */
safe('loadmsg',function(){
  var _lr=window.loadRegion;
  window.loadRegion=function(id,cb){
    safe('loadmsg:show',function(){
      /* __phxRegionSwitch 플래그가 있을 때만 #main을 덮음 — 의류 탭 순차 로드 진행 UI·나우캐스트 행 클릭 경로 보호 */
      if(window.__phxRegionSwitch&&!(window.PSH&&window.PSH[id])){
        var r=REGIONS.find(function(x){return x.id===id;});
        if(r&&r.file){ var m=document.getElementById('main');
          if(m) m.innerHTML='<div class="load-msg">⏳ '+esc(r.label||id)+' 데이터 불러오는 중…</div>'; } }
      window.__phxRegionSwitch=false; });
    return _lr(id,cb); };
});

/* ============================================================
   모듈 3. 통화 pill 재배치 (P0-11)
   ============================================================ */
safe('cur',function(){
  window.buildCurRow=function(){ var row=document.getElementById('curRow'); if(!row) return;
    row.querySelectorAll('.pill.cur').forEach(function(p){ p.remove(); });
    Object.keys(CUR).forEach(function(k){ var el=document.createElement('span');
      el.className='pill cur'+(k===ST.cur?' on':''); el.dataset.cur=k;
      el.textContent=CUR[k].sym+' '+k; el.onclick=function(){ ST.cur=k; render(); };
      row.appendChild(el); });
    var pills=row.querySelectorAll('.pill.cur');           /* 세그먼트 캡 — :first-of-type은 라벨 span에 막혀 매칭 불가 */
    if(pills.length){ pills[0].classList.add('seg-first'); pills[pills.length-1].classList.add('seg-last'); }
    a11y(row);
  };
  var q=document.getElementById('q'); if(q){ try{ q.type='search'; }catch(e){} }
});

/* ============================================================
   모듈 4. 산업분류 재설계 (P1-04/05 · P0-03) — 요약 1행 + 다열 + 부분 리렌더
   ============================================================ */
safe('catdrill',function(){
  window.catDrill=function(){
    var cos=companiesIn(ST.cat).filter(function(c){return !c.is_hub&&!c._custom;});
    if(!cos.length) return '';
    var cats=regionObj().cats||M.categories;
    var clabel=function(id){ var c=cats.find(function(x){return x.id===id;}); return c?c.label:(id||'기타'); };
    var byCat={};
    cos.forEach(function(c){ var ck=c.category||'기타', sk=c.subcategory||'기타';
      var b=byCat[ck]=byCat[ck]||{n:0,subs:{}}; b.n++; (b.subs[sk]=b.subs[sk]||[]).push(c); });
    var catEnts=Object.entries(byCat).sort(function(a,b){return b[1].n-a[1].n;});
    var totalSubs=new Set(cos.map(function(c){return c.subcategory||'기타';})).size;
    var single=ST.cat!=='all'&&String(ST.cat).slice(0,2)!=='g:';
    if(ST.cat==='all'? totalSubs<4 : totalSubs<2) return '';
    ST.catOpen=ST.catOpen||{}; ST.grpOpen=ST.grpOpen||{};
    if(ST.cat==='all'&&!ST.drillOpen)                                    /* P1-04①: 기본은 요약 1행 */
      return '<div class="catwrap"><div class="catgrp sum" data-drill-open="1" title="대분류 ▸ 세부분류 ▸ 기업으로 찾아보기">'
        +'🗂 <b>산업 분류로 찾아보기</b><em>'+catEnts.length+'대분류 · '+totalSubs+'세부분류</em><i>▸</i></div></div>';
    var secs=catEnts.map(function(ent){ var ck=ent[0], b=ent[1];
      var open=single||ST.grpOpen[ck];
      var subEnts=Object.entries(b.subs).sort(function(a,b){return b[1].length-a[1].length;});
      var head=single?'':'<div class="catgrp '+(open?'on':'')+'" data-grp="'+esc(ck)+'"><b>'+esc(clabel(ck))
        +'</b><em>'+b.n+'사 · '+subEnts.length+'분류</em><i>'+(open?'▾':'▸')+'</i></div>';
      if(!open) return head;
      var chips=subEnts.map(function(se){ return '<span class="catchip '+(ST.catOpen[se[0]]?'on':'')
        +'" data-cat="'+esc(se[0])+'">'+esc(se[0])+'<em>'+se[1].length+'</em></span>'; }).join('');
      var boxes=subEnts.filter(function(se){return ST.catOpen[se[0]];}).map(function(se){
        var rows=se[1].slice(0,80).map(function(c){ return '<span class="catco" data-cid="'+esc(c.id)+'">'
          +esc(c.name)+'<i>'+esc((c.ticker||'').split(' ')[0])+'</i></span>'; }).join('');
        return '<div class="catbox"><b>'+esc(se[0])+'</b> <span style="color:var(--dim);font-size:11px">'
          +se[1].length+'사'+(se[1].length>80?' (상위 80 표시)':'')+'</span><div class="catlist">'+rows+'</div></div>'; }).join('');
      return head+'<div class="catchips">'+chips+'</div>'+boxes;
    }).join('');
    var fold=(ST.cat==='all')?' <span class="cl" data-cd-close style="cursor:pointer">▴ 접기</span>':'';
    return '<div class="catwrap"><div class="cattitle">산업 분류 <span>— 대분류 ▸ 세부분류 ▸ 기업 ('
      +catEnts.length+'대분류 · '+totalSubs+'세부분류)</span>'+fold+'</div><div class="catsecs">'+secs+'</div></div>';
  };
  window.bindCatDrill=function(root){
    var redraw=function(){ var w=document.getElementById('cdWrap'); if(!w) return render();
      w.innerHTML=catDrill(); bindCatDrill(w); a11y(w); };               /* P1-05: 차트 파괴 없는 부분 리렌더 */
    var op=root.querySelector('[data-drill-open]'); if(op) op.onclick=function(){ ST.drillOpen=true; redraw(); };
    var cl=root.querySelector('[data-cd-close]'); if(cl) cl.onclick=function(){ ST.drillOpen=false; redraw(); };
    root.querySelectorAll('.catgrp[data-grp]').forEach(function(el){ el.onclick=function(){
      var k=el.dataset.grp; ST.grpOpen=ST.grpOpen||{}; ST.grpOpen[k]=!ST.grpOpen[k]; redraw(); }; });
    root.querySelectorAll('.catchip').forEach(function(el){ el.onclick=function(){
      var k=el.dataset.cat; ST.catOpen[k]=!ST.catOpen[k]; redraw(); }; });
    root.querySelectorAll('.catco').forEach(function(el){ el.onclick=function(){
      var c=(P.companies||[]).find(function(x){return x.id===el.dataset.cid;});
      if(c){ ST._ovScroll=window.scrollY; ST.company=c.id; ST.view='detail';
        render(); window.scrollTo(0,0); } }; });
  };
});

/* ============================================================
   모듈 5. 개요 화면 (P0-02/07/08/09 · P1-09/12 · P2-01/02)
   ============================================================ */
safe('overview',function(){
  window.renderOverview=function(){
    destroyAll();
    document.getElementById('catRow').style.display='';
    var qEl=document.getElementById('q');
    if(qEl) qEl.placeholder=regionObj().label+' 내 기업·티커 검색…';        /* P0-09 */
    var nAll=companiesIn('all').length;
    var crumb=document.getElementById('crumb');                            /* P1-12: 클릭 가능한 위치 표시 */
    crumb.innerHTML='<b class="cl" data-go="reg">'+(regionObj().flag||'')+' '+esc(regionObj().label)+'</b>'
      +'<span class="sep">›</span><span class="'+(ST.cat!=='all'?'cl':'')+'" data-go="all">전체 '+nAll+'사</span>'
      +(ST.cat!=='all'?'<span class="sep">›</span><b>'+esc(catLabel(ST.cat))+' '+companiesIn(ST.cat).length+'사</b>':'');
    crumb.querySelectorAll('[data-go]').forEach(function(el){ el.onclick=function(){
      if(el.dataset.go==='reg'){ var s=document.getElementById('regSel'); if(s) s.click(); }
      else if(ST.cat!=='all'){ ST.cat='all'; ST.ovN=30; render(); } }; });
    var cr=document.getElementById('catRow'); cr.innerHTML='';
    var _cats=regionObj().cats||M.categories;
    var _grps=(M.catgroups||[]).filter(function(g){ return _cats.some(function(c){return c.grp===g.id;}); });
    var _mk=function(label,count,on,fn,title){ var el=document.createElement('span');
      el.className='pill'+(on?' on':'');
      el.innerHTML=esc(label)+(count?' <em class="pn">'+count+'사</em>':'');   /* P0-08: 단위 통일 */
      if(title) el.title=title; el.onclick=fn; cr.appendChild(el); return el; };
    if(!_grps.length){                                                     /* 자체 cats 리전: 평면 pill */
      _cats.forEach(function(c){ var n=companiesIn(c.id).length;
        if(n===0&&c.id!=='all'&&c.id!=='watch') return;                    /* P0-02: 빈 pill 제거 */
        _mk(koLabel(c.label),(c.id==='all'?nAll:n),c.id===ST.cat,function(){ST.cat=c.id;ST.ovN=30;render();},
          (c.id==='all'?'전체':c.label)+' — 기업 '+(c.id==='all'?nAll:n)+'곳'); });
    } else {                                                               /* 전역 분류 리전: 대그룹 ▸ 세부 */
      var _isG=String(ST.cat||'').slice(0,2)==='g:';
      var _curGrp=_isG?String(ST.cat).slice(2):((_cats.find(function(c){return c.id===ST.cat;})||{}).grp||null);
      _mk('전체',nAll,ST.cat==='all',function(){ST.cat='all';ST.ovN=30;render();},'현재 리전 전체 기업');
      _grps.forEach(function(g){ var n=companiesIn('g:'+g.id).length;
        if(n===0) return;                                                  /* P0-02: 빈 그룹 제거 */
        _mk(g.label,n,_isG&&_curGrp===g.id,function(){ST.cat='g:'+g.id;ST.ovN=30;render();},
          g.label+' — 기업 '+n+'곳'); });
      _cats.filter(function(c){return !c.grp&&c.id!=='all';}).forEach(function(c){
        var n=companiesIn(c.id).length; if(n===0&&c.id!=='watch') return;
        _mk(c.label,n,c.id===ST.cat,function(){ST.cat=c.id;ST.ovN=30;render();}); });
      if(_curGrp){ var br=document.createElement('span'); br.style.flexBasis='100%'; br.style.height='0'; cr.appendChild(br);
        _cats.filter(function(c){return c.grp===_curGrp;}).forEach(function(c){ var n=companiesIn(c.id).length; if(!n) return;
          _mk('· '+c.label,n,c.id===ST.cat,function(){ST.cat=c.id;ST.ovN=30;render();}); }); }
    }
    a11y(cr); updCatFade();
    var q=ST.q.toLowerCase();
    var list=companiesIn(ST.cat).filter(function(c){ return !q||c.name.toLowerCase().includes(q)
      ||(c.name_jp||'').includes(ST.q)||(c.subcategory||'').includes(ST.q)
      ||(c.ticker||'').toLowerCase().includes(q)||(c.note||'').toLowerCase().includes(q); });
    var total=list.length;
    document.getElementById('cnt').textContent='기업 '+total+'개사 · '+koLabel(catLabel(ST.cat));  /* P0-07 */
    var main=document.getElementById('main'); main.innerHTML='';
    if(ST.cat==='all'&&!q){ introCard(main); heroStrip(main); }            /* P2-02 · P2-01 */
    var _cd=catDrill();
    if(_cd){ var w=document.createElement('div'); w.id='cdWrap'; w.innerHTML=_cd;
      main.appendChild(w); bindCatDrill(w); a11y(w); }
    if(!list.length){                                                      /* P1-09 · P0-02: 빈 상태 분리 */
      var em=document.createElement('div'); em.className='empty-msg';
      if(q){
        var hits=(P.companies||[]).filter(function(c){ return (c.region||'JP')!==ST.region
          &&(c.name.toLowerCase().includes(q)||(c.ticker||'').toLowerCase().includes(q)); });
        em.innerHTML='‘'+esc(ST.q)+'’ — 현재 <b>'+esc(regionObj().label)+'</b>에서 결과가 없습니다.'
          +(hits.length?'<br>로드된 다른 리전에 '+hits.length+'건 있습니다. 상단 리전 버튼으로 전환해 보세요.':'')
          +(ST.cat!=='all'?'<br><span class="pill" style="margin-top:10px;display:inline-block" data-reall>전체에서 재검색</span>':'');
      } else if(ST.cat==='watch'){
        em.innerHTML='아직 관심 기업이 없습니다. 카드의 ★ 를 누르거나 “★ 관심기업” 탭에서 등록하세요.';
      } else {
        em.innerHTML='이 분류에는 아직 데이터가 없습니다.<br>'
          +'<span class="pill" style="margin-top:10px;display:inline-block" data-reall>← 전체 기업 보기</span>';
      }
      main.appendChild(em);
      var ra=em.querySelector('[data-reall]'); if(ra) ra.onclick=function(){ ST.cat='all'; ST.ovN=30; render(); };
      return;
    }
    var _ovRest;
    if(total>60){
      var li=function(a){ for(var i=a.length-1;i>=0;i--) if(a[i]>0) return i; return -1; };
      list=list.slice().sort(function(a,b){ var x=li(a.revenue||[]),y=li(b.revenue||[]);
        return (y>=0?(b.revenue||[])[y]:0)-(x>=0?(a.revenue||[])[x]:0); });
      var lim=ST.ovN||30;
      if(total>lim){ _ovRest=total-lim; list=list.slice(0,lim); }
    }
    var g=document.createElement('div'); g.className='ov-grid'; g.dataset.q=q; main.appendChild(g);
    renderCards(list,g);
    if(_ovRest>0){
      var mb=document.createElement('div'); mb.className='empty-msg';
      mb.style.cursor='pointer'; mb.style.marginTop='12px';
      mb.textContent='▼ 더 보기 (+'+Math.min(30,_ovRest)+' / 남은 '+_ovRest+'곳 — 매출순)';
      mb.onclick=function(){ ST.ovN=(ST.ovN||30)+30; renderOverview(); };
      main.appendChild(mb);
    }
  };

  /* --- P2-02: 1회성 소개 카드 --- */
  function introCard(main){ safe('intro',function(){
    if(localStorage.getItem('phx_intro_v1')) return;
    var d=document.createElement('div'); d.className='phx-intro';
    d.innerHTML='💡 <span><b>Phalanx</b>는 세관 수출입·월매출 공시로 기업 실적을 <b>발표 1~2개월 전에</b> 추적합니다. '
      +'상단 <b>리전 버튼</b>=데이터셋 전환, <b>탭</b>=테마 뷰, 카드 클릭=기업 상세.</span>'
      +'<span class="x" role="button" tabindex="0">알겠어요 ✕</span>';
    d.querySelector('.x').onclick=function(){ try{localStorage.setItem('phx_intro_v1','1');}catch(e){} d.remove(); };
    main.appendChild(d);
  }); }

  /* --- P2-01: 오늘의 변화 히어로 스트립 --- */
  function heroStrip(main){ safe('hero',function(){
    var reg=ST.region, rows=[];
    var pool=(P.companies||[]).filter(function(c){ return (c.region||'JP')===reg&&!c.hid&&!c.is_hub&&(c.revenue||[]).length; });
    var movers=[];
    pool.forEach(function(c){ var a=c.revenue, i=-1;             /* 3개월 합 YoY — 단월 저기저 노이즈 완화 */
      for(var k=a.length-1;k>=0;k--){ if(a[k]){ i=k; break; } }
      if(i<14) return;
      var cur=(a[i]||0)+(a[i-1]||0)+(a[i-2]||0), prv=(a[i-12]||0)+(a[i-13]||0)+(a[i-14]||0);
      if(!(prv>0&&cur>0)) return;
      var mx=0;                                                  /* 자기 이력 최대 3M — 기저효과 배제용 */
      for(var j=2;j<=i;j++){ var s3=(a[j]||0)+(a[j-1]||0)+(a[j-2]||0); if(s3>mx) mx=s3; }
      if(prv<mx*0.05) return;      /* 전년 동기가 자기 최대의 5% 미만 = 사실상 0에서 출발 → 제외 */
      var y=cur/prv-1; if(isFinite(y)&&y>-1&&y<20) movers.push([c,y]);
    });
    if(movers.length>=4){
      movers.sort(function(a,b){ return b[1]-a[1]; });
      var up=movers.slice(0,4).filter(function(m){return m[1]>0;});
      var dn=movers.slice(-2).filter(function(m){return m[1]<0;}).reverse();
      var mk=function(m){ return '<span class="phx-chip" data-co="'+esc(m[0].id)+'" '
        +'title="최근 3개월 합의 전년동기 대비">'+esc(m[0].name)
        +' <span class="'+(m[1]>=0?'up':'dn')+'">'+(m[1]>=0?'+':'')+(m[1]*100).toFixed(1)+'%</span></span>'; };
      if(up.length) rows.push(['📈 YoY 급등 (3M)',up.map(mk).join('')]);
      if(dn.length) rows.push(['📉 YoY 급락 (3M)',dn.map(mk).join('')]);
    }
    safe('hero:earn',function(){ var soon=[];
      (P.companies||[]).forEach(function(c){ if((c.region||'JP')!==reg||!c.earn||c.earn==='TBD') return;
        var dt=new Date(c.earn+'T00:00:00'); if(isNaN(dt)) return;
        var days=Math.round((dt-new Date())/86400000);
        if(days>=0&&days<=7) soon.push([c,days]); });
      if(soon.length){ soon.sort(function(a,b){return a[1]-b[1];});
        rows.push(['📅 실적 임박',soon.slice(0,5).map(function(s){
          return '<span class="phx-chip" data-co="'+esc(s[0].id)+'">'+esc(s[0].name)
            +' <span class="dd">D-'+s[1]+'</span></span>'; }).join('')]); } });
    safe('hero:recent',function(){ var rec=getRecent()
      .map(function(id){ return (P.companies||[]).find(function(c){return c.id===id&&(c.region||'JP')===reg;}); })
      .filter(Boolean);
      if(rec.length) rows.push(['🕘 최근 본 기업',rec.map(function(c){
        return '<span class="phx-chip" data-co="'+esc(c.id)+'">'+esc(c.name)+'</span>'; }).join('')]); });
    if(!rows.length) return;
    var d=document.createElement('div'); d.className='phx-hero';
    d.innerHTML=rows.map(function(r){ return '<div class="hrow"><span class="hlab">'+r[0]+'</span>'+r[1]+'</div>'; }).join('');
    d.querySelectorAll('[data-co]').forEach(function(el){ el.onclick=function(){
      var c=(P.companies||[]).find(function(x){return x.id===el.dataset.co;}); if(!c) return;
      ST._ovScroll=window.scrollY;
      ST.view='detail'; ST.company=c.id; ST.flow=c.rev_flow||'exp'; ST.q='';
      var q=document.getElementById('q'); if(q) q.value='';
      render(); window.scrollTo(0,0); }; });
    main.appendChild(d); a11y(d);
  }); }

  /* --- 검색 필터 (P0-07 · P1-09: 0건 시 안내로 위임) --- */
  window.filterOverview=function(){
    if(companiesIn(ST.cat).length>60){ ST.ovN=30; return renderOverview(); }
    var grid=document.querySelector('#main .ov-grid');
    if(!grid) return renderOverview();
    if((grid.dataset.q||'')!=='') { ST.ovN=30; return renderOverview(); }  /* 부분집합 그리드 고착 방지 — 전체 재구축 */
    var q=ST.q.toLowerCase(), vis=0;
    grid.querySelectorAll('.card').forEach(function(card){
      var id=card.dataset.co, co=id&&P.companies.find(function(c){return c.id===id;});
      var show=!q||(co&&(co.name.toLowerCase().includes(q)||(co.name_jp||'').includes(ST.q)
        ||(co.subcategory||'').includes(ST.q)||(co.ticker||'').toLowerCase().includes(q)
        ||(co.note||'').toLowerCase().includes(q)));
      card.style.display=show?'':'none'; if(show) vis++;
    });
    document.getElementById('cnt').textContent='기업 '+vis+'개사 · '+koLabel(catLabel(ST.cat));
    if(vis===0&&q){ ST.ovN=30; return renderOverview(); }
  };
});

/* ============================================================
   모듈 6. 카테고리 행 오버플로 페이드 (P0-13)
   ============================================================ */
var updCatFade=function(){};
safe('catfade',function(){
  var cr=document.getElementById('catRow'); if(!cr) return;
  var cw=document.createElement('div'); cw.className='cats-wrap';
  cr.parentNode.insertBefore(cw,cr); cw.appendChild(cr);
  updCatFade=function(){ safe('catfade:upd',function(){
    cw.style.display=(cr.style.display==='none')?'none':'';
    cw.classList.toggle('more-l',cr.scrollLeft>4);
    cw.classList.toggle('more-r',cr.scrollLeft+cr.clientWidth<cr.scrollWidth-4); }); };
  cr.addEventListener('scroll',updCatFade,{passive:true});
  if(window.ResizeObserver) new ResizeObserver(updCatFade).observe(cr);
});

/* ============================================================
   모듈 7. render 후처리 — sub 정비(P0-05/06)·신선도(P1-08)·로고(P1-17)·
            스크롤 복원(P0-14)·활성 탭 센터링·a11y 재적용
   ============================================================ */
safe('renderwrap',function(){
  var _render=window.render, prevView=null;
  window.render=function(){
    var was=prevView;
    try{ _render(); }
    catch(e){ console.warn('[ui-patch] render 실패 — 대시보드 폴백',e);
      if(ST.tab!=='dash'){ ST.tab='dash'; try{ _render(); }catch(e2){} } }
    prevView=ST.view;
    safe('recent',function(){                              /* 방문 기록: 실제 상세 진입에서만 (오기록 방지) */
      if(ST.view==='detail'&&ST.company&&window.__phxLastCo!==ST.company){
        window.__phxLastCo=ST.company; pushRecent(ST.company); }
      if(ST.view!=='detail') window.__phxLastCo=null; });
    safe('crumb2',function(){                              /* 비-dash 탭: dash의 클릭형 crumb 잔류 제거 */
      if(ST.view==='overview'&&ST.tab!=='dash'){
        var on=document.querySelector('#tabs .tab.on'), cb=document.getElementById('crumb');
        if(cb&&on) cb.innerHTML='<b>'+esc(on.textContent.trim())+'</b>'; } });
    safe('sub',function(){
      var r=regionObj(), el=document.getElementById('sub'); if(!el) return;
      var lp=lastPubYM();
      el.textContent='월간 · '+(lp?subYM(MONTHS[0])+' – '+subYM(lp):'데이터 로딩 중')+' · '+(r.source_short||SRC_SHORT[r.id]||stripTags(r.source||M.source||''));
      el.title=stripTags(r.source||'');
      var f=document.getElementById('phxFresh');
      if(f){ f.style.display=(lp&&ST.tab==='dash'&&ST.view==='overview')?'':'none';  /* 크로스샤드 탭에선 오독 방지 위해 숨김 */
        if(lp){ var now=new Date();
          var lag=(now.getFullYear()*12+now.getMonth()+1)-(parseInt(lp.slice(0,4),10)*12+parseInt(lp.slice(5,7),10));
          var bt='매일 갱신';                              /* M.built(빌더 주입)로 실제 갱신 시점 표시 */
          safe('built',function(){ if(M.built){
            var bd=new Date(String(M.built).slice(0,10)+'T00:00:00');
            var days=Math.floor((new Date(now.getFullYear(),now.getMonth(),now.getDate())-bd)/86400000);
            bt=days<=0?'오늘 갱신':days+'일 전 갱신';
            if(days>=2) f.classList.add('stale'); } });
          f.textContent='데이터 최신 '+subYM(lp)+' · '+bt;
          f.classList.toggle('stale',lag>3||f.classList.contains('stale'));
          f.title='이 리전의 마지막 공표월 기준'+(M.built?' · 마지막 빌드 '+M.built:''); } }
    });
    safe('logo',function(){ var lg=document.querySelector('header .logo');
      if(lg) lg.textContent=regionObj().flag||'Φ'; });
    safe('tabon',function(){ document.querySelectorAll('#tabs .tab').forEach(function(t){
      t.classList.toggle('on',t.dataset.tab===ST.tab); });
      var on=document.querySelector('#tabs .tab.on');
      if(on&&on.scrollIntoView){ var tb=document.getElementById('tabs');
        if(tb&&tb.scrollWidth>tb.clientWidth+8) on.scrollIntoView({inline:'center',block:'nearest'}); } });
    safe('scroll',function(){
      if(was==='detail'&&ST.view==='overview'&&ST._ovScroll){
        var y=ST._ovScroll; ST._ovScroll=0;
        setTimeout(function(){ window.scrollTo(0,y); },0); } });
    updCatFade(); a11y(document);
  };
});

/* ============================================================
   모듈 9. 기업 카드 후처리 (2라운드 감사 R2-1/3/4/7)
   -------------------------------------------------------------
   companyCard가 만든 DOM을 후처리한다(템플릿 복제 금지 — 빌더가 카드를 바꿔도 따라감).
   ============================================================ */
safe('card-post',function(){
  var _cc=window.companyCard; if(typeof _cc!=='function') return;
  window.companyCard=function(co){
    var d=_cc(co);
    /* R2-1: 좌측 'Category · X'가 우측 .cat-tag와 완전히 같은 문자열 → 중복 제거.
       h3의 <small>이 이미 name_jp·ticker(또는 HS)를 보여주므로 여기선 그 아래 단계인
       세부분류만 남긴다. kre 기업은 <small>이 HS로 대체돼 티커가 사라지므로 보완한다. */
    safe('card:hd',function(){
      var cc=d.querySelector('.co-cat'); if(!cc) return;
      var sub=[];
      if(co.subcategory) sub.push(esc(co.subcategory));
      if(co.kre&&co.kre.hs&&co.ticker) sub.push(esc(co.ticker));
      if(sub.length) cc.innerHTML=sub.join(' · ');
      else cc.style.display='none';
    });
    /* R2-5 보강: 접기를 '차트 생성 시점'이 아니라 '카드 생성 시점'에 적용한다.
       지연 렌더 대기 카드가 빈 190px 상자를 띄웠다가 그려질 때 줄어드는 누적 시프트 방지. */
    safe('card:yrhide',function(){
      var b=d.querySelector('.ch-yr'), t=d.querySelector('.sub-ttl');
      if(b) b.style.display='none';
      if(t) t.style.visibility='hidden';
    });
    /* R2-3: 상관계수는 증감이 아니다 — 하락 빨강(#ff5c5c)에서 분리 */
    safe('card:corr',function(){
      d.querySelectorAll('.headline .chg').forEach(function(el){
        var lab=(el.parentNode&&el.parentNode.textContent)||'';
        if(!/Correl/i.test(lab)) return;
        el.style.color=''; el.classList.add('phx-corr');
        if(Math.abs(parseFloat(el.textContent)||0)>=0.7) el.classList.add('s3');
      });
    });
    /* R2-4: note 2줄 클램프 + 더보기 (최장 746자가 차트를 화면 밖으로 밀어냄) */
    safe('card:note',function(){
      var n=d.querySelector('.co-note'); if(!n) return;
      if(stripTags(n.innerHTML).length<=90) return;
      n.innerHTML='<div class="nt">'+n.innerHTML+'</div>'
        +'<span class="nx" role="button" tabindex="0">＋ 프록시 정의 더보기</span>';
      var x=n.querySelector('.nx');
      var tog=function(e){ e.stopPropagation();      /* 카드 클릭(상세 이동)과 분리 */
        var o=n.classList.toggle('open');
        x.textContent=o?'− 접기':'＋ 프록시 정의 더보기'; };
      x.onclick=tog;
      x.onkeydown=function(e){ if(e.key==='Enter'||e.key===' ') tog(e); };
    });
    return d;
  };
});

/* ============================================================
   모듈 9b. 카드 차트 — 연도별 차트 접기 + 색 충돌 해소 (R2-5/6)
   -------------------------------------------------------------
   'YoY by Year'(190px)는 메인 차트의 YoY 점선과 같은 배열을 달별로 접은 것이라
   개요 단계에서 상시 노출할 값이 낮은데 카드 높이의 1/3과 Chart 인스턴스 1개를 쓴다.
   → 기본 접힘, 제목을 누를 때 생성한다(인스턴스도 그때 만들어짐).
   또 잠정 라인과 YoY 라인이 둘 다 #ffbe2e라 구분이 안 되고, 기업색이 #ffbe2e·#c45cff인
   카드는 매출 바와 파생 라인이 같은 색이 된다 → 파생 라인을 무채색으로 옮긴다.
   ※ 모듈 10(card-grid)보다 먼저 설치해야 한다.
   ============================================================ */
safe('card-charts',function(){
  var _rcc=window.renderCompanyCharts; if(typeof _rcc!=='function') return;
  /* 캔버스를 떼면 원본이 new Chart(undefined)를 호출해 Chart.js가 콘솔 에러를 찍는다.
     그 한 번의 호출 동안만 생성자를 감싸 빈 대상이면 조용히 더미를 돌려준다. */
  function withNullChartGuard(fn){
    var R=window.Chart;
    if(typeof R!=='function') return fn();
    var G=function(el,cfg){
      if(!el) return {destroy:function(){},update:function(){},resize:function(){},
                      data:{datasets:[]},options:{}};
      return new R(el,cfg);
    };
    try{ Object.setPrototypeOf(G,R); }catch(_){}   /* Chart.defaults 등 정적 참조 승계 */
    G.prototype=R.prototype;
    window.Chart=G;
    try{ return fn(); } finally { window.Chart=R; }
  }
  window.renderCompanyCharts=function(div,co){
    var cs=div.querySelectorAll('canvas');
    var box=div.querySelector('.ch-yr'), ttl=div.querySelector('.sub-ttl');
    var c2=(cs.length>1&&box&&ttl)?cs[1]:null;
    if(c2) c2.remove();                    /* 2번째 캔버스를 떼면 원본은 메인 차트만 만든다 */
    try{ withNullChartGuard(function(){ _rcc(div,co); }); }catch(e){}

    safe('card:col',function(){            /* R2-6: 파생 라인 색을 기업색과 분리 */
      var ch=charts&&charts[co.id+'_m']; if(!ch||!ch.data) return;
      var hasProv=false;
      ch.data.datasets.forEach(function(s){
        if(s.label==='YoY%'){ s.borderColor='#e8e8f4'; s.borderWidth=1.6; }
        else if(s.label==='MoM%'){ s.borderColor='#9a9ec4'; s.borderWidth=1.1; }
        else if(s.label==='잠정'){ hasProv=true; s.borderColor='#ff8a3d';
          s.pointBackgroundColor='#ff8a3d'; s.pointBorderColor='#ff8a3d'; }
      });
      ch.update('none');
      var lg=div.querySelector('.legend');
      if(lg) lg.innerHTML=
        '<span><i class="bar" style="background:'+esc(co.color||'#3d8bfd')+'99"></i>월 프록시 매출</span>'
       +(hasProv?'<span><i style="border-color:#ff8a3d;border-top-style:dashed"></i>잠정(미확정월)</span>':'')
       +'<span><i style="border-color:#e8e8f4;border-top-style:dashed"></i>YoY</span>'
       +'<span><i style="border-color:#9a9ec4;border-top-style:dashed"></i>MoM</span>';
    });

    if(!c2) return;
    box.appendChild(c2); box.style.display='none';       /* R2-5: 기본 접힘 */
    var open=false, built=false;
    var setTtl=function(){ ttl.innerHTML=(open?'▾':'▸')+' 연도별 YoY 겹쳐보기 <em>(계절성)</em>'; };
    ttl.className='sub-ttl phx-fold'; ttl.setAttribute('role','button'); ttl.tabIndex=0;
    ttl.style.visibility=''; setTtl();      /* 토글이 준비된 시점에 제목을 되살린다 */
    var tog=function(e){ if(e) e.stopPropagation();
      open=!open; box.style.display=open?'':'none'; setTtl();
      if(!open||built) return;
      built=true;
      safe('card:yr',function(){          /* 펼칠 때 비로소 연도별 인스턴스를 만든다.
           원본은 두 캔버스를 함께 그리므로, 메인 인스턴스를 먼저 해제해
           캔버스를 비워야 재호출이 깨지지 않는다(Chart.js: canvas already in use). */
        var mk=co.id+'_m';
        if(charts&&charts[mk]){ try{ charts[mk].destroy(); }catch(_){} delete charts[mk]; }
        _rcc(div,co);
        safe('card:yr:col',function(){    /* 재생성된 메인 차트에 색 규칙 재적용 */
          var ch=charts&&charts[mk]; if(!ch||!ch.data) return;
          ch.data.datasets.forEach(function(s){
            if(s.label==='YoY%'){ s.borderColor='#e8e8f4'; s.borderWidth=1.6; }
            else if(s.label==='MoM%'){ s.borderColor='#9a9ec4'; s.borderWidth=1.1; }
            else if(s.label==='잠정'){ s.borderColor='#ff8a3d';
              s.pointBackgroundColor='#ff8a3d'; s.pointBorderColor='#ff8a3d'; }
          });
          ch.update('none');
        });
      });
    };
    ttl.onclick=tog;
    ttl.onkeydown=function(e){ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); tog(e); } };
  };
});

/* ============================================================
   모듈 10. 카드 그리드 — 뷰포트 지연 렌더 + 키보드 접근 (R2-27/7)
   카드 30장 × Chart 2개를 동기 생성하던 것을, 화면에 들어올 때만 그린다.
   .ch-main/.ch-yr 높이가 CSS 고정이라 레이아웃 시프트는 0.
   ============================================================ */
safe('card-grid',function(){
  var _rc=window.renderCards; if(typeof _rc!=='function') return;
  var _rcc=function(el,co){ return window.renderCompanyCharts(el,co); };  /* 호출 시점 해석 —
     뒤에서 renderCompanyCharts를 감싸는 모듈(연도별 차트 접기 등)이 반드시 반영되도록 */
  var EAGER=6;                                   /* 첫 화면 몫은 항상 즉시 렌더 */
  var ioFired=false;
  function draw(el){ var co=el.__phxCo; if(!co) return;
    el.__phxCo=null; if(io) io.unobserve(el);
    safe('card-grid:draw',function(){ _rcc(el,co); }); }
  var io=(window.IntersectionObserver&&typeof window.renderCompanyCharts==='function')
    ? new IntersectionObserver(function(es){
        ioFired=true;
        es.forEach(function(en){ if(en.isIntersecting) draw(en.target); });
      },{rootMargin:'600px 0px'})
    : null;
  /* 안전망: IO가 동작하지 않는 환경(뷰포트 높이 0, 프리렌더 등)에서 카드가
     영영 빈 채로 남는 것을 막는다. 일정 시간 내 IO 콜백이 한 번도 없으면 전부 렌더. */
  function safetyNet(){ setTimeout(function(){ safe('card-grid:net',function(){
    if(ioFired&&window.innerHeight>0) return;
    document.querySelectorAll('#main .card.co').forEach(draw);
  }); },2500); }

  window.renderCards=function(list,g){
    var idx=0;
    list.forEach(function(co){
      if(co._custom){ g.appendChild(stubCard(co)); return; }
      var card=companyCard(co); g.appendChild(card);
      var eager=(idx++<EAGER)||!io;
      if(eager) safe('card-grid:sync',function(){ _rcc(card,co); });
      else { card.__phxCo=co; io.observe(card); }         /* 나머지는 지연 렌더 */
      var sb=card.querySelector('[data-star]');
      if(sb){ sb.setAttribute('aria-label','관심 등록/해제');
        sb.onclick=function(e){ e.stopPropagation(); toggleStar(co.id);
          sb.classList.toggle('on',isStar(co.id));
          if(ST.cat==='watch'||ST.tab==='watch') render(); };
        sb.onkeydown=function(e){ e.stopPropagation(); }; }
      card.onclick=function(){ if(window.__phxCancelSearch) window.__phxCancelSearch();
        ST._ovScroll=window.scrollY;
        ST.view='detail'; ST.company=co.id; ST.flow=co.rev_flow||'exp'; ST.q='';
        var q=document.getElementById('q'); if(q) q.value='';
        render(); window.scrollTo(0,0); };
      /* R2-7: 카드가 role/tabindex 없는 div라 키보드로 상세 진입 불가였음 */
      card.setAttribute('role','link'); card.tabIndex=0;
      card.setAttribute('aria-label',(co.name||co.id)+' 상세 보기');
      card.onkeydown=function(e){ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); card.click(); } };
    });
    if(io) safetyNet();
  };
  if(io){                                                /* 뷰 전환 시 대기 카드 관찰 해제 */
    var _da=window.destroyAll;
    window.destroyAll=function(){
      safe('card-grid:reset',function(){
        document.querySelectorAll('#main .card.co').forEach(function(el){
          if(el.__phxCo){ io.unobserve(el); el.__phxCo=null; } });
      });
      return _da();
    };
  }
});

/* ============================================================
   모듈 11. 상세뷰·국가뷰 후처리 (R2-10/12/13)
   ※ 모듈 8(지연 로드)보다 먼저 설치해야 한다 — 모듈 8이 이 래퍼를 감싸서
      지연 로드 완료 후에 후처리가 돌게 된다.
   ============================================================ */
safe('detail-post',function(){
  function cube(){ try{ var sk=setKey();
    return !!((P.country||{})[sk]||(P.country_i||{})[sk]); }catch(e){ return false; } }

  /* R2-13: 매출형 리전(대만 MOPS·일본 월차 등)은 국가 큐브가 빈 껍데기라
     포트 카드를 누르면 국가뷰가 반쪽만 그려진 채 멈춘다(라이브 재현 확인).
     → 깨진 화면 대신 이유를 설명하고 상세뷰로 되돌린다. */
  var _rcv=window.renderCountry;
  if(typeof _rcv==='function') window.renderCountry=function(){
    if(cube()) return _rcv();
    var main=document.getElementById('main'); if(!main) return _rcv();
    main.innerHTML='<div class="phx-nocube"><b>이 데이터셋은 국가별 분해를 제공하지 않습니다.</b><br>'
      +esc(regionObj().label)+'은(는) 기업이 공시하는 월매출 총액이라 '
      +'세관 신고 기반의 국가별·품목별 내역이 없습니다.<br>'
      +'<span class="pill" data-back="1" role="button" tabindex="0">← 기업 상세로 돌아가기</span></div>';
    var b=main.querySelector('[data-back]');
    if(b) b.onclick=function(){ ST.view='detail'; ST.port=null; render(); };
    safe('nocube:crumb',function(){
      var c=document.getElementById('crumb');
      if(c) c.innerHTML='<b>'+esc(regionObj().label)+'</b><span class="sep">›</span>'
        +'<span>'+esc((compObj()||{}).name||'')+'</span><span class="sep">›</span><b>국가별 분해 없음</b>';
    });
  };

  var _rd=window.renderDetail;
  if(typeof _rd==='function') window.renderDetail=function(){
    var v=_rd();
    /* R2-12: 분해=국가별이면 지표·보기·Flow·실적 pill 11~12개가 조용히 무력화된다 */
    safe('detail:dead',function(){
      if(!ST.split) return;
      var cnt=document.getElementById('cnt'); if(!cnt) return;
      cnt.querySelectorAll('[data-mt],[data-rp],[data-fn],[data-d]').forEach(function(e){
        e.classList.add('phx-dead');
        e.title='국가별 분해 모드에서는 적용되지 않습니다 — 누르면 합계 보기로 돌아갑니다';
        e.addEventListener('click',function(){ ST.split=false; },true);
      });
      var n=cnt.querySelector('.split-note');
      if(n&&!/적용되지/.test(n.textContent)) n.insertAdjacentHTML('beforeend',
        ' · <span style="color:var(--dim);font-weight:500">이 모드에서는 지표·보기·Flow·실적 설정이 적용되지 않습니다</span>');
    });
    /* R2-13(2): 국가 큐브가 없는 데이터셋(공시 월매출)에서 분해를 켜면 빈 차트가 된다.
       이 래퍼는 모듈 8의 지연 로드가 끝난 뒤에 실행되므로 이 시점의 cube()는 확정적이다. */
    safe('detail:nosplit',function(){
      if(!ST.split||cube()) return;
      var cnt=document.getElementById('cnt'); if(cnt)
        cnt.querySelectorAll('[data-sp="1"]').forEach(function(e){
          e.classList.add('phx-dead');
          e.title='이 데이터셋(공시 월매출)은 국가별 분해를 제공하지 않습니다'; });
      var hero=document.getElementById('hero');
      if(hero&&!hero.querySelector('.phx-nocube'))
        hero.innerHTML='<div class="phx-nocube"><b>이 데이터셋은 국가별 분해를 제공하지 않습니다.</b><br>'
          +esc(regionObj().label)+'은(는) 공시 월매출 총액이라 국가별 내역이 없습니다.<br>'
          +'<span class="pill" data-sp0="1" role="button" tabindex="0">← 합계 보기로</span></div>';
      var b=hero&&hero.querySelector('[data-sp0]');
      if(b) b.onclick=function(){ ST.split=false; renderDetail(); };
    });
    return v;
  };

  /* R2-10: 상세뷰 진입 첫 화면을 리전 전체 HS표 30행(약 1000px)이 점령 → 기본 접힘 */
  var _rh=window.renderHsInfo;
  if(typeof _rh==='function') window.renderHsInfo=function(){
    _rh();
    safe('hsfold',function(){
      var el=document.getElementById('hsinfo'); if(!el||!el.innerHTML) return;
      var hs=(typeof REGHS!=='undefined'&&REGHS[ST.region])||[]; if(!hs.length) return;
      var co=null; try{ co=ST.company?compObj():null; }catch(e){}
      var lab=''; if(co&&co.hs_label) lab=String((co.hs_label.core||'')+' '+(co.hs_label.broad||''));
      var mine=hs.filter(function(h){ return h.code&&lab.indexOf(h.code)>=0; });
      if(!ST._hsOpen){
        el.innerHTML='<div class="hdr phx-hsum" role="button" tabindex="0">HS 코드 매핑 '+hs.length+'건'
          +(mine.length?' · <b>이 기업 '+mine.length+'건</b>':'')+'<i>▸ 펼치기</i></div>';
        el.querySelector('.phx-hsum').onclick=function(){ ST._hsOpen=1; renderHsInfo(); };
      } else {
        var hd=el.querySelector('.hdr');
        if(hd){ hd.classList.add('phx-hsum'); hd.setAttribute('role','button'); hd.tabIndex=0;
          hd.innerHTML='HS 코드 매핑 '+hs.length+'건<i>▾ 접기</i>';
          hd.onclick=function(){ ST._hsOpen=0; renderHsInfo(); }; }
        var tb=el.querySelector('tbody');
        if(tb) el.querySelectorAll('tbody tr').forEach(function(tr,i){
          if(mine.indexOf(hs[i])>=0){ tr.classList.add('phx-hshit'); tb.prepend(tr); } });
      }
    });
  };
});

/* ============================================================
   모듈 11b. 상세뷰 보강 (R2-14/11/17/16)
   ※ 모듈 8(지연 로드)보다 앞 — 로드 완료 후에 후처리가 돌아야 한다.
   ============================================================ */
safe('detail-more',function(){
  var _rd=window.renderDetail; if(typeof _rd!=='function') return;
  window.renderDetail=function(){
    var v=_rd();
    var co=null; try{ co=compObj(); }catch(e){}
    if(!co) return v;

    /* R2-14: 카드가 갖고 있던 요약(실적 D-day·나우캐스트·상관계수·주석)이
       상세뷰에서 전부 사라져 깊이 들어갈수록 정보가 줄던 문제 */
    safe('det:sum',function(){
      var h=document.getElementById('hero');
      if(!h||h.querySelector('.phx-detsum')) return;
      var bits='';
      safe('s1',function(){ if(typeof earnChip==='function') bits+=earnChip(co); });
      safe('s2',function(){ if(typeof ncBadge==='function'){ var b=ncBadge(co); if(b) bits+=b; } });
      safe('s3',function(){ if(typeof corrInfo!=='function') return;
        var ci=corrInfo(co); if(!ci||ci.r==null) return;
        bits+='<span class="phx-pb"><b>'+(ci.r>=0?'+':'')+(+ci.r).toFixed(2)+'</b>'
          +'<em>세관↔매출 상관'+(ci.n?' '+ci.n+'Q':'')+'</em></span>'; });
      var note=co.note?'<div class="co-note phx-detnote-body">'+co.note+'</div>':'';
      if(!bits&&!note) return;
      h.insertAdjacentHTML('afterbegin','<div class="phx-detsum">'
        +(bits?'<div class="phx-detbits">'+bits+'</div>':'')+note+'</div>');
      safe('det:sum:clamp',function(){       /* 카드와 같은 2줄 클램프 규칙 */
        var n=h.querySelector('.phx-detnote-body'); if(!n) return;
        if(stripTags(n.innerHTML).length<=140) return;
        n.innerHTML='<div class="nt">'+n.innerHTML+'</div>'
          +'<span class="nx" role="button" tabindex="0">＋ 프록시 정의 더보기</span>';
        var x=n.querySelector('.nx');
        x.onclick=function(e){ e.stopPropagation(); var o=n.classList.toggle('open');
          x.textContent=o?'− 접기':'＋ 프록시 정의 더보기'; };
      });
    });

    /* R2-11: 라디오(단일 선택)와 토글(다중)이 마크업·색이 같아 구분 불가.
       + core_set===broad_set인 기업(JP 79%·KR/TW 100%)은 HS pill이 완전한 no-op */
    safe('det:aff',function(){
      var cnt=document.getElementById('cnt'); if(!cnt) return;
      cnt.querySelectorAll('[data-mt],[data-rp],[data-fn]').forEach(function(e){
        e.classList.add('phx-multi'); if(!e.title) e.title='여러 개를 함께 켤 수 있습니다'; });
      cnt.querySelectorAll('[data-d],[data-sp],[data-g]').forEach(function(e){
        e.classList.add('phx-radio'); if(!e.title) e.title='하나만 선택됩니다'; });
      if(co.core_set&&co.broad_set&&co.core_set===co.broad_set)
        cnt.querySelectorAll('[data-d="mode"]').forEach(function(e){   /* HS pill의 실제 속성 */
          e.classList.add('phx-dead');
          e.title='이 기업은 core와 broad의 HS 집합이 같아 결과가 바뀌지 않습니다'; });
    });

    /* R2-17: 발표 실적(분기 합계)이 월별 프록시와 같은 축에 얹히는데 설명이 없어
       프록시가 실적을 크게 밑도는 것처럼 오독된다 */
    safe('det:fin',function(){
      if(typeof finOf!=='function'||!finOf(co)) return;
      var on=ST.fin&&(ST.fin.rev||ST.fin.op||ST.fin.seg); if(!on) return;
      if(ST.gran!=='M') return;
      var h=document.getElementById('hero'); if(!h||h.querySelector('.phx-finnote')) return;
      h.insertAdjacentHTML('afterbegin','<div class="phx-finnote">⚠️ <b>발표 실적은 분기 합계</b>라 '
        +'월별 프록시 막대와 같은 축에서 약 3배 높게 찍힙니다. 같은 기준으로 보려면 '
        +'<span class="pill" data-gq="1" role="button" tabindex="0">기간단위를 분기로</span> 바꾸세요.</div>');
      var b=h.querySelector('[data-gq]');
      if(b) b.onclick=function(){ ST.gran='Q'; safe('fin:prefs',function(){ if(typeof savePrefs==='function') savePrefs(); }); render(); };
    });

    /* R2-16: 세관 카드가 등록 순서대로 나열되고 비중 표시가 없어
       매출의 대부분을 차지하는 세관이 아래쪽에 묻힌다 → 12개월 비중순 정렬 + 배지 */
    safe('det:rank',function(){
      if(ST.split) return;
      var g=document.getElementById('grid'); if(!g||!g.children.length) return;
      if(typeof dseries!=='function'||typeof cflow!=='function') return;
      var fl=cflow();
      var arr=[].slice.call(g.children).map(function(c){
        var t=0; safe('rank:s',function(){ var s=dseries(c.dataset.code), a=(s[fl]||{}).v||[];
          for(var i=Math.max(0,a.length-12);i<a.length;i++) t+=(a[i]||0); });
        return [t,c]; });
      var sum=arr.reduce(function(a,x){ return a+x[0]; },0); if(sum<=0) return;
      /* order는 grid item에도 적용되므로 display를 바꾸지 않는다(바꾸면 반응형 열이 깨짐) */
      arr.sort(function(a,b){ return b[0]-a[0]; }).forEach(function(p,i){
        p[1].style.order=i;
        var m=p[1].querySelector('.metrics');
        if(m&&!m.querySelector('.phx-share'))
          m.insertAdjacentHTML('beforeend','<div class="metric phx-share"><span class="val">'
            +(p[0]/sum*100).toFixed(1)+'%</span><div class="lbl">최근 12개월 비중</div></div>');
      });
    });
    return v;
  };
});

/* ============================================================
   모듈 11c. 국가뷰 어휘·안내 정정 (R2-19) + 범례 터치 토글 (R2-25)
   ============================================================ */
safe('country-copy',function(){
  var _rc=window.renderCountry;
  if(typeof _rc==='function') window.renderCountry=function(){
    var v=_rc();
    safe('cc',function(){
      var CM={value:'값(누적)',share:'비중%',yoy:'국가별 YoY%',unit:'국가별 단가'};
      document.querySelectorAll('#main .card-hd small').forEach(function(s){
        var t=s.textContent||''; Object.keys(CM).forEach(function(k){
          if(t.indexOf('· '+k)>=0) s.textContent=t.replace('· '+k,'· '+CM[k]); }); });
      /* 'top 9개국 + 기타'는 실제 큐브(order 7개)와 불일치 — 실제 개수로 정정 */
      safe('cc:n',function(){
        var n=0; try{ var cd=countrySrc(); n=(cd&&cd.order&&cd.order.length)||0; }catch(e){}
        if(!n) return;
        document.querySelectorAll('#main .split-note, #main .sub-ttl').forEach(function(e){
          e.innerHTML=e.innerHTML.replace(/top\s*9개국\s*\+\s*기타/g,'상위 '+(n-1)+'개국 + 기타')
                                 .replace(/top9\+기타/g,'상위 '+(n-1)+'개국+기타'); });
      });
    });
    return v;
  };
  /* 터치 기기에서는 범례 개별 토글이 Shift/⌘를 요구해 사실상 불가능하다 */
  safe('legend-touch',function(){
    if(!window.matchMedia||!matchMedia('(pointer:coarse)').matches) return;
    var _cvo=window.countryViewOpts; if(typeof _cvo!=='function') return;
    window.countryViewOpts=function(kind){
      var o=_cvo(kind), lg=o&&o.plugins&&o.plugins.legend; if(!lg) return o;
      lg.onClick=function(e,item,legend){                 /* 탭 = 개별 토글 */
        var ci=legend.chart, i=item.datasetIndex;
        ci.setDatasetVisibility(i,!ci.isDatasetVisible(i)); ci.update();
      };
      if(lg.labels) lg.labels.boxWidth=14, lg.labels.padding=12;
      return o;
    };
  });
});

/* ============================================================
   모듈 11d. 기간 브러시 — 조작 단서·읽기값·터치 타깃 (R2-15/21)
   ============================================================ */
safe('brush-ux',function(){
  var br=document.getElementById('brush'); if(!br) return;
  if(!br.querySelector('.phx-bhint'))
    br.insertAdjacentHTML('beforeend','<span class="phx-bhint">드래그하거나 눌러서 기간 선택</span>');
  var lab=document.getElementById('phxBLab');
  if(!lab){ lab=document.createElement('div'); lab.className='phx-blab'; lab.id='phxBLab';
    br.parentNode.insertBefore(lab,br.nextSibling); }
  function ym(i){ var s=MONTHS[i]||''; return s.replace('-','.'); }
  function upd(){ safe('blab',function(){
    var l=document.getElementById('phxBLab'), b=document.getElementById('brush'); if(!l) return;
    /* 브러시는 상세·국가뷰에서만 표시된다 — 라벨도 같이 숨겨야 개요에 유령 문구가 남지 않는다 */
    var vis=b&&b.style.display!=='none';
    l.style.display=vis?'':'none';
    if(!vis) return;
    l.textContent='표시 구간 '+ym(ST.r0)+' – '+ym(ST.r1)
      +(ST.range==='custom'?' (직접 선택)':'');
  }); }
  ['positionBrush','updateRangeUI','render'].forEach(function(n){   /* render도 — 뷰 전환 시 라벨 표시/숨김 동기화 */
    var f=window[n]; if(typeof f!=='function') return;
    window[n]=function(){ var r=f.apply(null,arguments); upd(); return r; };
  });
  /* 트랙(빈 곳)을 눌러도 구간이 이동하도록 — 3M 프리셋에서 창이 4px라 잡을 수 없었다 */
  safe('brush-tap',function(){
    if(typeof _idx!=='function') return;
    br.addEventListener('pointerdown',function(e){
      if(e.target&&e.target.closest&&e.target.closest('.brush-win')) return;  /* 창·핸들은 원래 핸들러 */
      var N=MONTHS.length-1, len=ST.r1-ST.r0, c=_idx(e.clientX);
      var r0=Math.max(0,Math.min(c-Math.round(len/2),N-len));
      ST.r0=r0; ST.r1=r0+len; ST.range='custom';
      safe('bt:apply',function(){ if(typeof applyRange==='function') applyRange();
        if(typeof positionBrush==='function') positionBrush();
        if(typeof updateRangeUI==='function') updateRangeUI(); });
    });
  });
  upd();
});

/* ============================================================
   모듈 11e. 모바일 차트 압축 (R2-20)
   375px에서 오른쪽 축 3개가 폭의 43%, 범례 6행이 높이의 41%를 먹어
   실제 플롯이 167×141px(포트 카드는 175×65px)까지 줄어든다.
   Chart.js 전역 플러그인으로 카드·상세·국가뷰 캔버스만 한정해 손본다.
   ============================================================ */
safe('chart-mobile',function(){
  if(typeof Chart==='undefined'||!Chart.register) return;
  function scoped(ch){                    /* .ch-wrap은 KPI·게임·플랫폼 탭도 쓰는 범용 클래스라
       카드(.ch-main/.ch-yr)와 상세·국가뷰(#hero/#grid) 안쪽으로만 한정한다 */
    var cv=ch&&ch.canvas; if(!cv||!cv.closest) return null;
    return cv.closest('.ch-main,.ch-yr')||cv.closest('#hero,#grid');
  }
  function apply(ch){
    var host=scoped(ch); if(!host) return;
    var o=(ch.config&&ch.config.options)||ch.options; if(!o) return;
    if((window.devicePixelRatio||1)>1.5) o.devicePixelRatio=1.5;   /* 밀집 차트 래스터 절감 */
    if(window.innerWidth>680) return;
      o.plugins=o.plugins||{};
      var lg=o.plugins.legend=o.plugins.legend||{};
      lg.labels=lg.labels||{};
      lg.labels.boxWidth=8; lg.labels.padding=6;
      lg.labels.font=Object.assign({},lg.labels.font,{size:9});
      var sc=o.scales||{};
      ['yW','yU','yP'].forEach(function(k){                 /* 오른쪽 보조축은 눈금만 숨김 */
        if(sc[k]&&sc[k].position==='right'){ sc[k].ticks=Object.assign({},sc[k].ticks,{display:false});
          sc[k].title=Object.assign({},sc[k].title,{display:false}); } });
      if(sc.x&&sc.x.ticks){ sc.x.ticks.font=Object.assign({},sc.x.ticks.font,{size:10});
        sc.x.ticks.maxTicksLimit=Math.min(sc.x.ticks.maxTicksLimit||6,6);
        sc.x.ticks.maxRotation=0; sc.x.ticks.autoSkip=true; }
      if(sc.yV&&sc.yV.ticks){ sc.yV.ticks.font=Object.assign({},sc.yV.ticks.font,{size:10});
        sc.yV.ticks.maxTicksLimit=5; }
  }
  Chart.register({id:'phxMob',
    beforeInit:function(ch){ safe('phxMob',function(){ apply(ch); }); }});
});

/* ============================================================
   모듈 11f. 대형 리전 검색 코얼레싱 (R2-28)
   60사 초과 카테고리는 키 입력마다 카드 30장·차트 60개를 파괴·재생성한다.
   ============================================================ */
safe('search-coalesce',function(){
  var _fo=window.filterOverview; if(typeof _fo!=='function') return;
  var t=null;
  window.__phxCancelSearch=function(){ if(t){ clearTimeout(t); t=null; } };
  window.filterOverview=function(){
    var big=false; safe('sc:size',function(){ big=companiesIn(ST.cat).length>60; });
    if(!big) return _fo();                    /* 소형: DOM 숨김뿐 — 즉시 반응 유지 */
    clearTimeout(t);
    /* 발화 시점에 스케줄 당시 컨텍스트가 그대로인지 검증한다. 검증이 없으면
       타이머가 탭·상세뷰 전환 뒤에 터져 그 화면을 대시보드 개요로 덮어쓴다. */
    var k={tab:ST.tab, view:ST.view, region:ST.region, cat:ST.cat, q:ST.q};
    t=setTimeout(function(){ t=null; safe('sc:run',function(){
      if(ST.tab!==k.tab||ST.view!=='overview'||k.view!=='overview'
         ||ST.region!==k.region||ST.cat!==k.cat||ST.q!==k.q) return;
      _fo();
    }); },120);                               /* 입력 자체가 이미 180ms 디바운스 — 합계 300ms */
  };
});

/* ============================================================
   모듈 12. 기간 프리셋 칩 — 선택 항목 가시화 (R2-23)
   기본 'all'이 8개 중 마지막이라 모바일에서 화면 밖에 있었다.
   ============================================================ */
safe('range-center',function(){
  function center(){ safe('range-center:go',function(){
    var rr=document.getElementById('rangeRow'); if(!rr) return;
    if(rr.scrollWidth<=rr.clientWidth+8) return;
    var on=rr.querySelector('.pill.r.on'); if(!on) return;
    rr.scrollLeft=Math.max(0,on.offsetLeft-(rr.clientWidth-on.offsetWidth)/2);
  }); }
  ['updateRangeUI','positionBrush'].forEach(function(n){
    var f=window[n]; if(typeof f!=='function') return;
    window[n]=function(){ var r=f.apply(null,arguments); center(); return r; };
  });
});

/* ============================================================
   모듈 8. 국가 큐브 지연 로드 + topc 사용 (첫 로드 페이로드 감축)
   -------------------------------------------------------------
   실측: data_jp.js gzip 4.12MB 중 country+country_i가 78%(11.6MB raw)인데
   실사용처는 카드의 상위 수출국 칩(coTopC)과 국가 드릴다운(countrySrc) 둘뿐이다.
   빌더 계약(맥스튜디오 작업):
     · company.topc = {idx, grouped?, top:[{name,share}]}  ← coTopC 결과 사전계산
     · manifest region.cfile = "data_jp_country.js"        ← {country,country_i}를 PSHC[reg]로
   이 모듈은 3가지 상태 모두에서 동작한다:
     (a) 빌더 미적용(현재) — 전부 폴백, 동작 변화 없음
     (b) 1단계(추가만)     — topc 사용, 국가 큐브는 메인 샤드에 아직 있어 지연로드 불필요
     (c) 2단계(country 제거) — 국가뷰 진입 시에만 cfile 지연 로드
   ============================================================ */
safe('country-lazy',function(){
  var _cLoaded={}, _cQueue={};
  function mergeCountry(reg){                       /* PSHC → P 로 병합하면 기존 코드가 그대로 동작 */
    var c=window.PSHC&&window.PSHC[reg]; if(!c) return false;
    if(c.country)   P.country  =Object.assign(P.country  ||{}, c.country);
    if(c.country_i) P.country_i=Object.assign(P.country_i||{}, c.country_i);
    _cLoaded[reg]=true; return true;
  }
  function haveCountry(){                           /* 현재 선택 세트의 국가 큐브가 메모리에 있나 */
    var sk=null; try{ sk=setKey(); }catch(e){ return true; }   /* 판단 불가 → 통과(폴백) */
    if(!sk) return true;
    return !!((P.country||{})[sk]||(P.country_i||{})[sk]);
  }
  function loadCountry(cb){
    var reg=ST.region, r=regionObj();
    if(_cLoaded[reg]||mergeCountry(reg)) return cb();
    if(!r.cfile) return cb();                       /* 빌더 미적용 — 메인 샤드에 이미 있음 */
    if(_cQueue[reg]){ _cQueue[reg].push(cb); return; }
    _cQueue[reg]=[cb];
    var m=document.getElementById('main');
    if(m) m.innerHTML='<div class="load-msg">⏳ 국가별 데이터 불러오는 중…</div>';
    var sc=document.createElement('script'); sc.src=r.cfile;
    sc.onload=sc.onerror=function(){ mergeCountry(reg); markOwned(reg); evictOthers(reg);
      var q=_cQueue[reg]||[]; _cQueue[reg]=null; q.forEach(function(f){ safe('country-cb',f); }); };
    document.head.appendChild(sc);
  }

  /* R2-29: 리전 전환 시 이전 리전의 국가 큐브를 축출한다(해제 경로가 아예 없었다).
     단 메인 샤드에 country가 남아 있는 동안(빌더 2단계 전)은 축출해도 재수신 비용만
     커지므로, cfile로 다시 받을 수 있는 리전만 대상으로 한다. */
  var _own={}, _owner={};                 /* _owner[key]=reg — 리전 간 core_set 이름이 겹친다 */
  function markOwned(reg){
    var c=(window.PSHC&&window.PSHC[reg])||{};
    var ck=Object.keys(c.country||{}), ik=Object.keys(c.country_i||{});
    ck.forEach(function(k){ _owner['c:'+k]=reg; });
    ik.forEach(function(k){ _owner['i:'+k]=reg; });
    _own[reg]={c:ck, i:ik};
  }
  function evictOthers(cur){ safe('evict',function(){
    Object.keys(_own).forEach(function(reg){
      if(reg===cur) return;
      var sh=window.PSH&&window.PSH[reg];
      if(sh&&sh.country&&Object.keys(sh.country).length) return;   /* 메인 샤드에 있음 — 축출 무의미 */
      (_own[reg].c||[]).forEach(function(k){                     /* 현재 리전이 다시 소유한 키는 건드리지 않는다 */
        if(_owner['c:'+k]===reg&&P.country) delete P.country[k]; });
      (_own[reg].i||[]).forEach(function(k){
        if(_owner['i:'+k]===reg&&P.country_i) delete P.country_i[k]; });
      if(window.PSHC) delete window.PSHC[reg];
      delete _own[reg]; _cLoaded[reg]=false;                       /* 재진입 시 다시 받도록 */
    });
  }); }

  /* 카드·상세 패널의 상위 수출국: 빌더 사전계산값이 있으면 국가 큐브 없이 렌더 */
  var _ctc=window.coTopC;
  if(typeof _ctc==='function') window.coTopC=function(co,topn){
    if(co&&co.topc&&co.topc.top&&co.topc.top.length){
      return { idx:co.topc.idx, grouped:!!co.topc.grouped,
        top:co.topc.top.slice(0,topn).map(function(t,i){
          return {name:t.name, share:t.share, col:CCOL[i%CCOL.length]}; }) };
    }
    return _ctc(co,topn);
  };

  /* 국가 큐브가 필요한 두 화면을 지연 로드로 감싼다:
       · 국가뷰(renderCountry) — 항상 필요
       · 상세뷰(renderDetail) — '수출국별' 분해 토글(ST.split) 켰을 때만 (dDatasets 760행)
     분해 토글 핸들러(3640행 re())는 이 전역들을 호출 시점에 참조하므로 함께 커버된다. */
  function wrapNeedsCountry(name, needs){
    var orig=window[name]; if(typeof orig!=='function') return;
    window[name]=function(){
      if(needs()&&!haveCountry()&&regionObj().cfile&&!_cLoaded[ST.region])
        return loadCountry(function(){ orig(); });
      return orig();
    };
  }
  wrapNeedsCountry('renderCountry', function(){ return true; });
  wrapNeedsCountry('renderDetail',  function(){ return !!ST.split; });
});

/* ============================================================
   모듈 14. 상세뷰 상태 초기화 + 복귀 동선 (R2-18)
   ※ 모듈 8보다 **뒤**에 설치해야 한다 — ST.split 초기화가 국가 큐브
      지연 로드 판정(needs()=ST.split)보다 먼저 걸려야 하기 때문.
   ============================================================ */
safe('det-state',function(){
  document.addEventListener('click',function(){          /* 상세 진입 직전 위치 기억 */
    if(ST.view!=='detail'&&ST.view!=='country') ST._from={tab:ST.tab,cat:ST.cat};
  },true);
  var _rd=window.renderDetail; if(typeof _rd!=='function') return;
  window.renderDetail=function(){
    safe('ds:reset',function(){
      if(ST._detCo===ST.company) return;
      ST._detCo=ST.company;
      var co=(P.companies||[]).find(function(c){ return c.id===ST.company; });
      if(!co) return;
      ST.split=false;                                    /* A사에서 켠 분해가 B사로 새지 않게 */
      ST.flow=co.rev_flow||'exp';                        /* 랭킹·딥링크 진입은 Flow를 안 맞춰 빈 차트가 됐다 */
      ST.mode='core';
    });
    var v=_rd();
    safe('ds:back',function(){                           /* '← 개요로'가 진입 경로를 무시하고 항상 대시보드로 튕김 */
      var f=ST._from; if(!f||f.tab==='dash') return;
      var c=document.getElementById('crumb'); if(!c) return;
      var b=c.querySelector('.back[data-go="ov"]'); if(!b) return;   /* crumb에 [data-go=ov]가 3개
         (리전 라벨·섹터·← 개요로) — 첫 번째를 잡으면 리전 이름을 덮어쓴다 */
      var lab=(document.querySelector('#tabs .tab[data-tab="'+f.tab+'"]')||{}).textContent||'이전 화면';
      b.textContent='← '+lab.trim()+'(으)로';
      b.onclick=function(){ ST.tab=f.tab; ST.cat=f.cat||'all'; ST.view='overview';
        ST.company=null; render(); window.scrollTo(0,0); };
    });
    return v;
  };
});

/* ---------- KR 부분월: 확정월을 '잠정'이라 표기하던 문제 (R2-8) ---------- */
safe('kre-label',function(){
  var _cc=window.companyCard; if(typeof _cc!=='function') return;
  window.companyCard=function(co){
    var d=_cc(co);
    safe('kre',function(){
      var k=co&&co.kre; if(!k||!k.hs||!k.partial) return;   /* partial일 때만 헤드라인이 확정월을 가리킨다 */
      var pi=MONTHS.indexOf(k.prov); if(pi<=0) return;
      d.querySelectorAll('.headline b').forEach(function(b){
        if((b.textContent||'').trim()!=='잠정') return;
        b.textContent='확정';
        b.style.color='var(--dim)';
        b.title='헤드라인 값은 잠정월('+subYM(k.prov)+') 직전의 확정월 수치입니다';
      });
    });
    return d;
  };
});

/* ---------- 초기 문구 정리 (P0-07) + 헤더 (P1-17) ---------- */
safe('inittext',function(){
  var lm=document.querySelector('#main .load-msg'); if(lm&&/Loading/i.test(lm.textContent)) lm.textContent='대시보드 준비 중…';
  var sub=document.getElementById('sub'); if(sub&&/^loading/i.test(sub.textContent)) sub.textContent='불러오는 중…';
  var h1=document.querySelector('header h1'); if(h1) h1.innerHTML='Phalanx <em>·</em> 무역·기업 실적 나우캐스트';
});

/* ---------- 이미 렌더된 화면이 있으면 새 UI로 재도장 ---------- */
safe('repaint',function(){ if(P.companies&&P.companies.length){ buildCurRow(); render(); } });
})();
