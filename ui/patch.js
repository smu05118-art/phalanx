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
      if(i>=14){ var cur=(a[i]||0)+(a[i-1]||0)+(a[i-2]||0), prv=(a[i-12]||0)+(a[i-13]||0)+(a[i-14]||0);
        if(prv>0&&cur>0){ var y=cur/prv-1; if(isFinite(y)) movers.push([c,y]); } } });
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

/* ---------- 초기 문구 정리 (P0-07) + 헤더 (P1-17) ---------- */
safe('inittext',function(){
  var lm=document.querySelector('#main .load-msg'); if(lm&&/Loading/i.test(lm.textContent)) lm.textContent='대시보드 준비 중…';
  var sub=document.getElementById('sub'); if(sub&&/^loading/i.test(sub.textContent)) sub.textContent='불러오는 중…';
  var h1=document.querySelector('header h1'); if(h1) h1.innerHTML='Phalanx <em>·</em> 무역·기업 실적 나우캐스트';
});

/* ---------- 이미 렌더된 화면이 있으면 새 UI로 재도장 ---------- */
safe('repaint',function(){ if(P.companies&&P.companies.length){ buildCurRow(); render(); } });
})();
