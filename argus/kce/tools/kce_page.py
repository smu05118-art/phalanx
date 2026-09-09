#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_page — 신규 편입사 페이지와 커버리지 지도를 생성한다.

원본 7사 페이지(encprojects 복제본)는 **건드리지 않는다** — 그쪽은 시드 데이터와
바이트 동일 렌더 계약이 걸려 있다(kce_render.py). 여기서 만드는 것은:

  · `<slug>/index.html`  신규사 현장 대시보드 (kce_series.build 결과를 임베드)
  · `coverage.html`      모집단 52사 전체의 수록 등급·사유 지도
  · `index.html`         회사 선택 화면 — 원본 7사 카드 + 신규사 카드

신규사 페이지에는 예측·백테스트·실적대비가 없다. 그 자산이 없기 때문이고,
없는 것을 빈 칸으로 흉내 내지 않는다(UPDATE.md §10).

사용:
    python3 kce_page.py --all                 # 신규사 전부 + coverage + index
    python3 kce_page.py --only 009410
"""
import argparse
import html
import json
import os
import sys
import time

from kce_lib import CORP, atomic_write, json_for_html, latest_quarter
from kce_universe import CONSTRUCTION_INDUSTRIES, load as load_universe
import kce_series

HERE = os.path.dirname(os.path.abspath(__file__))
KCE = os.path.dirname(HERE)
ASSETS = os.path.join(HERE, "assets")

E = html.escape

# 원본 7사 페이지와 같은 팔레트(argus/kce/index.html 기준)
CSS = """
:root{--bg:#0f1116;--pn:#171a21;--pn2:#1e222b;--ln:#2a2f3a;--tx:#e6e8ec;--tx2:#98a1b0;
 --tx3:#5d6675;--a:#60a5fa;--up:#4ade80;--dn:#f87171;--wn:#fbbf24}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font:13px/1.6 -apple-system,"Segoe UI","Malgun Gothic",sans-serif;padding:0 0 60px}
a{color:var(--a)}
header{position:sticky;top:0;z-index:9;background:rgba(15,17,22,.94);backdrop-filter:blur(8px);
 border-bottom:1px solid var(--ln);padding:12px clamp(12px,3vw,28px)}
.hd{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;max-width:1280px;margin:0 auto}
.hd h1{font-size:17px;font-weight:600;letter-spacing:-.3px}
.hd .code{font-size:11px;color:var(--tx3);font-variant-numeric:tabular-nums}
.hd .tag{font-size:10.5px;color:var(--tx2);border:1px solid var(--ln);border-radius:999px;padding:1px 8px}
.hd .sp{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap}
.hd .sp a{font-size:11px;text-decoration:none;border:1px solid var(--ln);border-radius:6px;padding:3px 9px}
.hd .sp a:hover{border-color:var(--a)}
main{max-width:1280px;margin:0 auto;padding:18px clamp(12px,3vw,28px)}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));gap:12px}
.kpi div{background:var(--pn);border:1px solid var(--ln);border-radius:9px;padding:12px 14px}
.kpi b{display:block;font-size:19px;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:-.5px}
.kpi span{display:block;font-size:10.5px;color:var(--tx3);margin-top:3px}
.kpi i{font-style:normal;font-size:11px;font-variant-numeric:tabular-nums}
.up{color:var(--up)}.dn{color:var(--dn)}
section{margin-top:22px;background:var(--pn);border:1px solid var(--ln);border-radius:10px;padding:14px 16px}
section h2{font-size:12.5px;font-weight:600;color:var(--tx2);margin-bottom:10px;
 display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
section h2 em{font-style:normal;font-size:10.5px;color:var(--tx3);font-weight:400}
.wrap{overflow-x:auto}
/* th{position:sticky;top:0}은 **세로로 스크롤되는 조상**이 있어야 성립한다. .wrap에
   높이 제약이 없으면 clientHeight==scrollHeight라 스크롤포트가 아니고, 머리행은 그냥
   페이지와 함께 흘러가 버렸다(태영건설 220현장 페이지에서 측정: 3138==3138).
   높이 제약은 화면이 넓을 때만 건다 — 좁은 화면에서 상자 안 세로 스크롤을 만들면
   페이지 스크롤과 이중이 되어 손가락이 무엇을 미는지 알 수 없게 된다. */
@media (min-width:768px){.wrap{max-height:70vh;overflow-y:auto}}
.chart{position:relative;height:260px}
table{border-collapse:collapse;width:100%;font-size:12px;font-variant-numeric:tabular-nums}
th,td{padding:5px 8px;border-bottom:1px solid var(--ln);text-align:right;white-space:nowrap}
/* border-collapse:collapse에서는 셀 테두리가 sticky 머리행을 따라오지 않는다 —
   밑줄은 box-shadow로 그려야 스크롤 중에도 남는다. z-index는 본문 셀 위로 띄우기 위함. */
th{color:var(--tx3);font-weight:500;font-size:10.5px;text-align:right;cursor:pointer;
 position:sticky;top:0;z-index:1;background:var(--pn);
 box-shadow:inset 0 -1px 0 var(--ln);user-select:none}
th:hover{color:var(--a)}
th.l,td.l{text-align:left}
td.l{max-width:340px;overflow:hidden;text-overflow:ellipsis}
tbody tr:hover{background:var(--pn2)}
.mut{color:var(--tx3)}
.bar{display:inline-block;height:5px;border-radius:3px;background:var(--a);vertical-align:middle}
.ctl{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.ctl input,.ctl select{background:var(--pn2);border:1px solid var(--ln);border-radius:6px;
 color:var(--tx);font:12px inherit;padding:4px 8px}
.ctl input{min-width:190px}
footer{max-width:1280px;margin:26px auto 0;padding:0 clamp(12px,3vw,28px);
 color:var(--tx3);font-size:10.5px;line-height:1.8}
.note{color:var(--wn);font-size:11px;background:rgba(251,191,36,.08);
 border:1px solid rgba(251,191,36,.25);border-radius:7px;padding:8px 11px;margin-top:14px}
"""


def newest_probe():
    """가장 최근 분기의 프로브 산출물. 분기가 넘어가면 파일명이 바뀐다."""
    got = sorted(f for f in os.listdir(ASSETS)
                 if f.startswith("probe_") and f.endswith(".json"))
    if not got:
        raise RuntimeError("assets/probe_*.json 없음 — kce_probe.py를 먼저 돌려라")
    return os.path.join(ASSETS, got[-1])


def fmt_eok(v):
    """백만원 → 억원 문자열."""
    if v is None:
        return "—"
    return format(round(v / 100), ",d")


def company_html(D):
    """신규사 대시보드 한 장. 입도(현장/부문)에 따라 라벨이 바뀐다 —
    부문 단위로만 공시하는 회사에 '현장별'이라고 쓰면 없는 정밀도를 주장하게 된다."""
    fq, sites = D["fq"], D["sites"]
    proj = D.get("grain") == "project"
    UNIT = "현장" if proj else "부문"
    KIND = "현장별" if proj else "부문별"
    k = len(fq) - 1
    bal = D["summary"]["bal"][k]
    has_prev = k > 0                 # 직전 '분기'가 존재하는가 (값의 유무와 별개다)
    prev = D["summary"]["bal"][k - 1] if has_prev else None
    # '기타현장' 같은 잔여 묶음은 개별 현장이 아니다 — 세지 않는다(집계에는 남는다)
    live = sum(1 for s in sites if s["s"]["bal"][k] and not s.get("agg"))
    n_site = sum(1 for s in sites if not s.get("agg"))
    dart = ("https://dart.fss.or.kr/dsaf001/main.do?rcpNo=%s" % D["src"][fq[-1]]
            if D["src"].get(fq[-1]) else "https://dart.fss.or.kr")
    # 상태는 셋인데 `if prev:` 하나로 묶으면 거짓을 적게 된다 — 잔고가 정확히 0인
    # 실재 분기도, 분기는 있는데 잔고를 못 읽은 경우도 '직전 분기 없음'으로 찍혔다.
    # '분기가 없다'와 '분기는 있는데 값이 없다'는 다른 사실이므로 갈라 쓴다.
    if not has_prev:
        chg = '<i class="mut">직전 분기 없음</i>'
    elif prev is None or bal is None:
        chg = '<i class="mut">%s 대비 —</i>' % E(fq[k - 1])
    else:
        d = bal - prev
        chg = '<i class="%s">%s%s억</i>' % ("up" if d >= 0 else "dn",
                                            "+" if d >= 0 else "\u2212", fmt_eok(abs(d)))

    # 원문이 스스로 적은 총계와 수록 현장 합의 차이 — 상세표에 없는 소규모 현장 몫이다.
    dec = (D.get("declared") or [None] * len(fq))[k]
    if dec and bal:
        cov = 100.0 * bal / dec
        decl = ('<div><b>%s<span style="font-size:12px;color:var(--tx3)"> 억</span></b>'
                '<span>공시 총계</span><i class="mut">수록분이 %.0f%%</i></div>'
                % (fmt_eok(dec), cov))
    elif dec:
        decl = ('<div><b>%s<span style="font-size:12px;color:var(--tx3)"> 억</span></b>'
                '<span>공시 총계</span></div>' % fmt_eok(dec))
    else:
        decl = ""

    # 입도 고지는 숫자보다 **먼저** 읽혀야 한다 — 부문 합계를 현장 실적으로 오독하면
    # 없는 정밀도를 주장하는 셈이 된다. 그래서 KPI 위에 통째로 얹는다.
    # (빈 문자열이면 <div>까지 통째로 사라지도록 마크업을 여기서 만든다)
    grainnote = ("" if proj else
                 '<div class="note">이 회사는 정기보고서에 <b>사업부문 단위로만</b> '
                 '수주를 공시합니다 — 개별 현장으로 쪼갤 수 없어 부문별 잔고 시계열만 '
                 '싣습니다. 아래 「부문」 행은 개별 공사 현장이 아니라 '
                 '사업부문 합계입니다.</div>')

    out = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{nm} {kind} 데이터</title>
<style>{css}</style></head><body>
<header><div class="hd">
 <h1>{nm} {kind} 데이터</h1>
 <span class="code">{stock}</span>
 <span class="tag">{market}</span>
 <span class="tag">{industry}</span>
 <span class="sp">
  <a href="../coverage.html">커버리지</a>
  <a href="../index.html">회사 선택</a>
  <a href="{dart}" rel="noopener noreferrer" target="_blank">DART 원문 ↗</a>
 </span>
</div></header>
<main>
{grainnote}
<div class="kpi">
 <div><b>{bal}<span style="font-size:12px;color:var(--tx3)"> 억</span></b><span>수주잔고 · {last}</span>{chg}</div>
 <div><b>{amt}<span style="font-size:12px;color:var(--tx3)"> 억</span></b><span>도급액 합계</span></div>
 <div><b>{live}</b><span>잔고 있는 {unit}</span></div>
 <div><b>{nsite}</b><span>수록 {unit}(누적)</span></div>
 <div><b>{nq}</b><span>수록 분기 · {span}</span></div>
 {decl}
</div>

<section>
 <h2>수주잔고 추이 <em>공종별 누적 · 억원</em></h2>
 <div class="chart"><canvas id="cBal"></canvas></div>
</section>

<section>
 <h2>{unit} 목록 <em>머리행을 누르면 정렬</em></h2>
 <div class="ctl">
  <input id="q" type="search" placeholder="{unit}·발주처 검색" aria-label="{unit} 검색">
  <select id="fSeg" aria-label="공종"><option value="">공종 전체</option></select>
  <select id="fReg" aria-label="지역"><option value="">지역 전체</option></select>
  <label style="font-size:11.5px;color:var(--tx2);display:flex;align-items:center;gap:5px">
   <input type="checkbox" id="onlyLive" checked style="min-width:0"> 잔고 있는 {unit}만</label>
 </div>
 <div class="wrap"><table id="tb">
  <thead><tr>
   <th class="l" data-k="nm">{unit}명</th><th class="l" data-k="cl">발주처</th>
   <th class="l" data-k="seg">공종</th><th class="l" data-k="reg">지역</th>
   <th data-k="sd">착공</th><th data-k="ed">완공예정</th>
   <th data-k="amt">도급액</th><th data-k="cmp">완성공사액</th>
   <th data-k="bal">계약잔액</th><th data-k="pr">진행률</th>
  </tr></thead><tbody></tbody>
 </table></div>
</section>

<section>
 <h2>분기 매트릭스 <em>{unit} × 분기 계약잔액(억) · 상위 60개</em></h2>
 <div class="wrap"><table id="mx"><thead></thead><tbody></tbody></table></div>
</section>

<div class="note">이 회사는 DART 정기보고서의 <b>수주상황 표를 분기마다 다시 읽어</b> 만든
실측 시계열입니다. 원본 7사 페이지와 달리 <b>예측(S-curve)·백테스트·실적 대비가 없습니다</b> —
그 자산은 복제 시드에서 온 것이라 신규 편입사에는 존재하지 않습니다.
현장은 이름으로 분기 간 연결하므로, 원문이 표기를 크게 바꾸면 다른 현장으로 잡힐 수 있습니다.
「공시 총계」가 있으면 원문이 직접 적은 수주잔고 합계입니다. <b>묶음</b> 표시가 붙은 행은
원문이 개별 기재를 생략하고 '기타현장'처럼 한 줄로 합쳐 적은 <b>나머지</b>이며,
합계를 맞추기 위해 집계에는 포함하되 현장 수에서는 빼고 셉니다.</div>
</main>
<footer>출처 DART 정기보고서 II. 사업의 내용 — 수주상황. 단위 억원(원문 백만원 환산).
{gen} 정기보고서 기준. 참고용 · 투자조언 아님.</footer>
<script src="../vendor/chart.umd.min.js"></script>
<script>const DATA={data};</script>
<script>{js}</script>
</body></html>""".format(
        css=CSS, js=COMPANY_JS, data=json_for_html(D),
        nm=E(D["co"]), stock=E(D["stock"]), market=E(D["market"]),
        kind=KIND, unit=UNIT, grainnote=grainnote,
        industry=E(D["industry"]), dart=E(dart), gen=E(D["codeGen"]),
        bal=fmt_eok(bal), amt=fmt_eok(D["summary"]["amt"][k]), chg=chg,
        live=live, nsite=n_site, nq=len(fq), last=E(fq[-1]), decl=decl,
        span=E("%s–%s" % (fq[0], fq[-1])))
    # fail-closed: str.format은 자리표시자가 없는 인자를 **조용히 버린다**. 실제로
    # 그렇게 grainnote가 통째로 빠진 채 부문사 5곳 페이지가 나갔다(고지 없이 부문
    # 합계를 현장처럼 보여준 셈). 렌더 결과에 실물이 있는지 확인하고 없으면 쓰지 않는다.
    if grainnote and grainnote not in out:
        raise RuntimeError("%s: 부문 단위 공시 고지문이 렌더에서 누락됐다" % D["stock"])
    return out


COMPANY_JS = r"""
(function(){
 var fq=DATA.fq, K=fq.length-1, S=DATA.sites;
 // 라벨은 입도에서 끌어온다 — 부문 공시 회사에 '현장'이라 쓰면 없는 정밀도를 주장한다
 var UNIT=(DATA.grain==='project')?'현장':'부문';
 var eok=function(v){return v==null?null:Math.round(v/100)};
 var fmt=function(v){return v==null?'—':v.toLocaleString('ko-KR')};

 // ── 차트: 공종별 누적 잔고 ────────────────────────────────
 // 차트는 **격리해서** 그린다. Chart.js가 못 뜨면(오프라인 스냅샷·벤더 파일 유실)
 // 예외가 같은 스코프의 표 렌더까지 죽여 페이지가 통째로 빈 화면이 된다.
 try{
  if(typeof Chart!=='function') throw new Error('Chart.js 로드 실패');
  var PAL=['#60a5fa','#4ade80','#fbbf24','#f87171','#a78bfa','#22d3ee','#fb923c'];
  var ds=DATA.segList.map(function(g,i){return{
    label:g, data:DATA.seg[g].map(eok), backgroundColor:PAL[i%PAL.length],
    borderWidth:0, stack:'s'};});
  new Chart(document.getElementById('cBal'),{type:'bar',data:{labels:fq,datasets:ds},
   options:{responsive:true,maintainAspectRatio:false,animation:false,
    interaction:{mode:'index',intersect:false},
    scales:{x:{stacked:true,grid:{display:false},ticks:{color:'#5d6675',font:{size:10}}},
      y:{stacked:true,grid:{color:'#2a2f3a'},ticks:{color:'#5d6675',font:{size:10},
        callback:function(v){return v.toLocaleString('ko-KR')}}}},
    plugins:{legend:{labels:{color:'#98a1b0',boxWidth:10,font:{size:10.5}}},
     tooltip:{callbacks:{label:function(c){return c.dataset.label+' '+
       (c.parsed.y==null?'—':c.parsed.y.toLocaleString('ko-KR'))+'억'}}}}}});
 }catch(err){
  var box=document.getElementById('cBal');
  if(box&&box.parentNode){box.parentNode.innerHTML=
    '<div style="color:#5d6675;font-size:11.5px;padding:22px;text-align:center">'+
    '차트를 그리지 못했습니다 ('+String(err&&err.message||err)+'). 아래 표는 정상입니다.</div>';}
 }

 // ── 현장 표 ──────────────────────────────────────────────
 try{
 var tb=document.querySelector('#tb tbody'), q=document.getElementById('q'),
     fSeg=document.getElementById('fSeg'), fReg=document.getElementById('fReg'),
     onlyLive=document.getElementById('onlyLive');
 [['seg',fSeg,DATA.segList],['reg',fReg,['국내','해외']]].forEach(function(x){
   x[2].forEach(function(v){var o=document.createElement('option');o.value=v;o.textContent=v;x[1].appendChild(o)})});
 var sortK='bal', sortD=-1, maxAmt=1;
 S.forEach(function(s){var a=s.s.amt[K]; if(a&&a>maxAmt)maxAmt=a});

 function rows(){
  var t=(q.value||'').trim().toLowerCase();
  return S.filter(function(s){
   if(onlyLive.checked && !s.s.bal[K]) return false;
   if(fSeg.value && s.seg!==fSeg.value) return false;
   if(fReg.value && s.reg!==fReg.value) return false;
   if(t && (s.nm+' '+s.cl).toLowerCase().indexOf(t)<0) return false;
   return true;
  }).sort(function(a,b){
   var x=key(a),y=key(b);
   if(x==null&&y==null)return 0; if(x==null)return 1; if(y==null)return -1;
   return x<y?-sortD:x>y?sortD:0;
  });
 }
 function key(s){
  if(sortK==='nm'||sortK==='cl'||sortK==='seg'||sortK==='reg')return s[sortK]||'';
  if(sortK==='sd'||sortK==='ed')return s[sortK]||null;
  return s.s[sortK]?s.s[sortK][K]:null;
 }
 function draw(){
  var r=rows(), h=[];
  r.forEach(function(s){
   var a=s.s.amt[K],c=s.s.cmp[K],b=s.s.bal[K],p=s.s.pr[K];
   h.push('<tr><td class="l" title="'+esc(s.nm)+'">'+esc(s.nm)+
    (s.agg?' <span class="mut" style="font-size:10px;border:1px solid var(--ln);border-radius:4px;padding:0 4px">묶음</span>':'')+'</td>'+
    '<td class="l mut">'+esc(s.cl||'—')+'</td><td class="l mut">'+esc(s.seg)+'</td>'+
    '<td class="l mut">'+esc(s.reg)+'</td>'+
    '<td class="mut">'+(s.sd||'—')+'</td><td class="mut">'+(s.ed||'—')+'</td>'+
    '<td>'+fmt(eok(a))+'</td><td>'+fmt(eok(c))+'</td><td>'+fmt(eok(b))+'</td>'+
    '<td>'+(p==null?'—':p.toFixed(0)+'%<span class="bar" style="width:'+
      Math.max(2,Math.min(38,p*.38))+'px;margin-left:5px"></span>')+'</td></tr>');
  });
  tb.innerHTML=h.join('')||'<tr><td colspan="10" class="mut" style="text-align:center;padding:18px">조건에 맞는 '+UNIT+'이 없습니다</td></tr>';
 }
 function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
   return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
 document.querySelectorAll('#tb th').forEach(function(th){
  th.addEventListener('click',function(){
   var k=th.dataset.k; sortD=(k===sortK)?-sortD:-1; sortK=k; draw();});
 });
 [q,fSeg,fReg,onlyLive].forEach(function(el){el.addEventListener('input',draw)});
 draw();
 }catch(err){document.querySelector('#tb tbody').innerHTML=
   '<tr><td colspan="10" style="color:#f87171;padding:16px">현장 표 렌더 실패: '+
   String(err&&err.message||err)+'</td></tr>';}

 // ── 분기 매트릭스 ────────────────────────────────────────
 try{
 var top=S.slice().sort(function(a,b){return (b.s.bal[K]||0)-(a.s.bal[K]||0)}).slice(0,60);
 document.querySelector('#mx thead').innerHTML='<tr><th class="l">'+UNIT+'</th>'+
   fq.map(function(f){return '<th>'+f+'</th>'}).join('')+'</tr>';
 var mb=top.map(function(s){
  return '<tr><td class="l" title="'+esc(s.nm)+'">'+esc(s.nm)+'</td>'+
   s.s.bal.map(function(v){return '<td'+(v==null?' class="mut"':'')+'>'+fmt(eok(v))+'</td>'}).join('')+'</tr>';
 }).join('');
 // 행이 0이면 머리행만 남는다 — 빈 표는 '데이터가 없다'인지 '렌더가 깨졌다'인지
 // 구별되지 않는다. 현장 표와 같이 사유를 적어 준다.
 document.querySelector('#mx tbody').innerHTML=mb||
   '<tr><td colspan="'+(fq.length+1)+'" class="mut" style="text-align:center;padding:18px">'+
   '표시할 '+UNIT+'이 없습니다</td></tr>';
 }catch(err){document.querySelector('#mx tbody').innerHTML=
   '<tr><td style="color:#f87171;padding:16px">매트릭스 렌더 실패: '+
   String(err&&err.message||err)+'</td></tr>';}
})();
"""


# ── 커버리지 지도 ────────────────────────────────────────────

TIER_LABEL = {
    "site": ("수록", "현장 단위 시계열", "up"),
    "segment": ("부분", "사업부문 단위만 공시", "wn"),
    "agg": ("미수록", "수주 표를 인식하지 못함", "tx3"),
    "none": ("미수록", "보고서에 수주 절 없음", "tx3"),
    "error": ("미수록", "보고서 접근 실패", "dn"),
}


def coverage_html(recs, probe, built):
    rows = []
    order = {"site": 0, "segment": 1, "agg": 2, "none": 3, "error": 4}
    for r in sorted(recs, key=lambda r: (order.get(probe.get(r["stock"], {}).get("tier"), 9),
                                         r["name"])):
        p = probe.get(r["stock"], {})
        tier = p.get("tier", "error")
        label, why, cls = TIER_LABEL[tier]
        b = built.get(r["stock"])
        link = ("<a href=\"%s/index.html\">%s</a>" % (E(r["slug"]), E(r["name"]))
                if (b or r["stock"] in {v["stock"] for v in CORP.values()})
                else E(r["name"]))
        rows.append(
            "<tr><td class=\"l\">%s</td><td class=\"mut\">%s</td><td class=\"l mut\">%s</td>"
            "<td class=\"l mut\">%s</td><td class=\"l\"><b class=\"%s\">%s</b></td>"
            "<td class=\"l mut\">%s</td><td>%s</td><td>%s</td></tr>"
            % (link, E(r["stock"]), E(r["market"]), E(r["industry"][:22]),
               cls, label, E(p.get("note") or why),
               (sum(1 for x in b["sites"] if not x.get("agg")) if b
                else (p.get("ii4_rows") or "—")),
               (b and len(b["fq"])) or "—"))
    tally = {}
    for r in recs:
        t = probe.get(r["stock"], {}).get("tier", "error")
        tally[t] = tally.get(t, 0) + 1
    return """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>커버리지 — 국내 상장 건설사</title>
<style>{css}
.tx3{{color:var(--tx3)}}.wn{{color:var(--wn)}}
</style></head><body>
<header><div class="hd">
 <h1>커버리지 지도</h1>
 <span class="tag">국내 상장 건설사 {n}종목</span>
 <span class="sp"><a href="index.html">회사 선택</a>
  <a href="../index.html">ARGUS</a></span>
</div></header>
<main>
<div class="kpi">
 <div><b class="up">{site}</b><span>현장 단위 수록</span></div>
 <div><b class="wn">{segment}</b><span>사업부문 단위만 공시</span></div>
 <div><b class="tx3">{rest}</b><span>수주 표 없음 · 미수록</span></div>
 <div><b>{n}</b><span>모집단 전체</span></div>
</div>
<section>
 <h2>모집단 규칙 <em>재현 가능한 기준만 쓴다</em></h2>
 <p style="font-size:12px;color:var(--tx2);line-height:1.8">
  KRX KIND 상장법인목록에서 <b>표준산업분류 건설업</b>({industries})에 속한 전 종목을
  모집단으로 삼고, 업종 밖이지만 건설 실질이 큰 <b>{seeds}</b>를 지정 추가합니다.
  이름으로 임의 배제하지 않습니다 — 배제는 <b>원문을 열어 수주 표가 없음을 확인한 경우</b>에만 합니다.
 </p>
</section>
<section>
 <h2>종목별 수록 상태 <em>{q} 정기보고서 기준 실측</em></h2>
 <div class="wrap"><table>
  <thead><tr><th class="l">회사</th><th>종목코드</th><th class="l">시장</th>
   <th class="l">업종</th><th class="l">등급</th><th class="l">근거</th>
   <th>현장·부문</th><th>분기</th></tr></thead>
  <tbody>{rows}</tbody></table></div>
</section>
<div class="note"><b>등급이 뜻하는 것</b> — <b>수록</b>: 착공일·완공예정일이 붙은 개별 현장 행이
파싱된다. <b>부분</b>: 수주표는 있으나 '건축부문/토목부문'처럼 사업부문 합계만 공시해
현장 단위로 쪼갤 수 없다. <b>미수록</b>: 정기보고서에 인식 가능한 수주 표가 없다.
등급은 추정이 아니라 매 분기 원문을 열어 다시 매깁니다.</div>
</main>
<footer>출처 KRX KIND 상장법인목록 · DART 정기보고서. 생성 {gen}. 참고용 · 투자조언 아님.</footer>
</body></html>""".format(
        css=CSS, rows="\n".join(rows), n=len(recs), q=E(next(iter(probe.values()), {}).get("quarter", "")),
        site=tally.get("site", 0), segment=tally.get("segment", 0),
        rest=tally.get("agg", 0) + tally.get("none", 0) + tally.get("error", 0),
        # 규칙 문구는 **코드에서 파생**시킨다. 업종 목록과 지정 종목을 화면에 손으로
        # 적어 두면 모집단 규칙이 바뀔 때 화면만 옛말을 하게 된다(자이에스앤디를
        # 지정에 넣었는데 문구는 2개사만 말하던 실제 사례).
        industries=E(" · ".join(CONSTRUCTION_INDUSTRIES)),
        seeds=E(" · ".join(r["name"] for r in sorted(recs, key=lambda r: r["stock"])
                           if r.get("source") == "지정")),
        gen=E(next(iter(probe.values()), {}).get("quarter", "") + " 기준"))


# ── 회사 선택 화면 ───────────────────────────────────────────

PICKER_BASE = os.path.join(HERE, "assets", "picker_base.html")


def picker_base(current):
    """원본 7사만 담긴 회사 선택 화면의 원형.

    생성기는 이 원형에서 **매번 새로 만든다** — 직전 산출물에 덧붙이면 재실행할 때마다
    신규 구획이 중복으로 쌓인다(Action이 매일 돈다). 원형이 없으면 지금 파일을
    원형으로 채택하되, 이미 생성된 산출물이면 거부한다.
    """
    if os.path.exists(PICKER_BASE):
        with open(PICKER_BASE, encoding="utf-8") as f:
            return f.read()
    if 'class="sec"' in current:
        raise RuntimeError("index.html이 이미 생성물이다 — assets/picker_base.html이 필요하다")
    atomic_write(PICKER_BASE, current)
    return current


def picker_html(recs, probe, built, old_html):
    """기존 index.html의 원본 7사 카드를 **그대로 보존**하고 신규사 카드를 덧붙인다.

    7사 카드에는 II-4/III-8/XI-1 건수처럼 이 도구가 다시 계산하지 않는 값이 박혀 있다.
    다시 만들면 그 값을 잃거나 틀리게 된다 — 손대지 않는 편이 정확하다.
    """
    import re as _re
    old_html = picker_base(old_html)
    legacy = _re.findall(r'<a class="card"[^>]*>.*?</a>', old_html, _re.S)
    # 원형 카드 수를 `len(CORP)`와 비교하면 안 된다 — CORP는 정밀 경로가 늘 때마다
    # 커지지만 원형은 그 시점에 고정된 파일이다. 7사 원형에 CORP 17을 요구해 예외가
    # 나면서 **신규 카드도 커버리지 링크도 붙지 않은 채** 화면이 방치됐다.
    # 지켜야 할 계약은 "원형의 카드를 하나도 잃지 않는다"이므로 원형 자신을 기준으로 센다.
    if not legacy:
        raise RuntimeError("원형(index.html/picker_base.html)에서 회사 카드를 찾지 못했다")

    cards = []
    def _bal(r):
        D = built.get(r["stock"])
        return -((D["summary"]["bal"][-1] or 0) if D else 0)

    for r in sorted(recs, key=_bal):
        D = built.get(r["stock"])
        if not D:
            continue
        proj = D.get("grain") == "project"
        unit, kind = ("현장", "현장별") if proj else ("부문", "부문별")
        k = len(D["fq"]) - 1
        live = sum(1 for s in D["sites"] if s["s"]["bal"][k] and not s.get("agg"))
        nsite = sum(1 for s in D["sites"] if not s.get("agg"))
        # 최근 분기에 잔고가 비면 마지막 관측 분기를 대신 보여준다 — '—'만 띄우면
        # 데이터가 아예 없는 회사처럼 보인다.
        bal, at = D["summary"]["bal"][k], D["fq"][k]
        if bal is None:
            for j in range(k, -1, -1):
                if D["summary"]["bal"][j] is not None:
                    bal, at = D["summary"]["bal"][j], D["fq"][j]
                    break
        cards.append(
            '<a class="card" href="{slug}/index.html"><div class="hd"><b>{nm}</b>'
            '<span class="code">{stock}</span></div>'
            '<p>{ind} · DART 수주상황(II-4)을 분기마다 다시 읽은 실측 시계열{seg}</p>'
            '<div class="stat"><div><b>{live}</b><span>진행 {unit}</span></div>'
            '<div><b>{nq}</b><span>분기</span></div>'
            '<div><b>{q0}<span class="dash">–</span>{q1}</b><span>수록 범위</span></div></div>'
            '<div class="src">수주잔고 {bal}억{at} · 수록 {unit} {nsite}</div>'
            '<div class="go">{kind} 데이터 →</div></a>'.format(
                slug=E(r["slug"]), nm=E(r["name"]), stock=E(r["stock"]),
                ind=E(r["industry"]), live=live, nq=len(D["fq"]),
                q0=E(D["fq"][0]), q1=E(D["fq"][-1]), unit=unit, kind=kind,
                seg="" if proj else " — 원문이 <b>사업부문 단위로만</b> 공시",
                bal=fmt_eok(bal), at="" if at == D["fq"][k] else "(%s)" % E(at),
                nsite=nsite))

    tally = {}
    for r in recs:
        t = probe.get(r["stock"], {}).get("tier", "error")
        tally[t] = tally.get(t, 0) + 1
    body = old_html
    # 신규 구획을 원본 격자 뒤, tools 앞에 끼워 넣는다
    block = ('\n<h2 class="sec">신규 편입 {n}사<span>수주상황(II-4) 실측만 — 예측·백테스트 없음</span></h2>\n'
             '<div class="grid">{cards}</div>\n').format(n=len(cards), cards="\n".join(cards))
    body = body.replace('<div class="tools">', block + '<div class="tools">', 1)
    # 구획 제목의 회사 수는 **원형 카드에서 센다.** '원본 7사'로 박아 두면 정밀 경로가
    # 늘 때 화면만 옛말을 한다(실제로 17사를 싣고 7사라고 적고 있었다).
    body = body.replace('<div class="grid">',
                        '<h2 class="sec">정밀 수록 %d사<span>II-4 · III-8 · XI-1 교차검증 · '
                        '예측·백테스트 포함</span></h2>\n<div class="grid">' % len(legacy), 1)
    # 커버리지 링크를 도구 칸 맨 앞에 추가
    cov = ('<a class="tool" href="coverage.html"><b>커버리지 지도</b>'
           '<span>국내 상장 건설사 {n}종목의 수록 등급과 그 근거. '
           '현장 단위 {site} · 부문 단위만 {seg} · 미수록 {rest}.</span></a>\n ').format(
        n=len(recs), site=tally.get("site", 0), seg=tally.get("segment", 0),
        rest=tally.get("agg", 0) + tally.get("none", 0) + tally.get("error", 0))
    body = body.replace('<div class="tools">\n ', '<div class="tools">\n ' + cov, 1)
    body = body.replace('<div class="sub">',
                        '<div class="sub">국내 상장 건설사 %d종목 중 현장 단위로 수록 가능한 %d사 · '
                        % (len(recs), tally.get("site", 0)), 1)
    # 구획 제목 스타일(없으면 추가)
    if ".sec{" not in body:
        body = body.replace("footer{", ".sec{width:100%;max-width:940px;margin:30px 0 -14px;"
                            "font-size:12px;font-weight:600;color:var(--tx2);display:flex;"
                            "align-items:baseline;gap:9px;flex-wrap:wrap}\n"
                            ".sec span{font-size:10.5px;color:var(--tx3);font-weight:400}\n"
                            "footer{", 1)
    # 사후 검증: 원형 카드가 하나라도 사라졌으면 쓰지 않는다. 신규 구획을 끼워 넣는
    # 문자열 치환이 어긋나면 기존 회사가 조용히 목록에서 빠질 수 있다(fail-closed).
    lost = [c for c in legacy if c not in body]
    if lost:
        raise RuntimeError("원형 카드 %d장이 산출물에서 사라졌다" % len(lost))
    if 'href="coverage.html"' not in body:
        raise RuntimeError("커버리지 링크 주입 실패 — tools 구획 마크업이 바뀌었다")
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only", help="종목코드 쉼표 구분")
    ap.add_argument("--from", dest="q0", default="2024Q3")
    ap.add_argument("--to", dest="q1", default=None)
    ap.add_argument("--probe", help="프로브 산출물 경로(기본: 최신 probe_*.json)")
    a = ap.parse_args()

    recs = load_universe()
    path = a.probe or newest_probe()
    with open(path, encoding="utf-8") as f:
        probe = {r["stock"]: r for r in json.load(f)["rows"]}
    from kce_lib import q_range
    quarters = q_range(a.q0, a.q1 or latest_quarter())
    legacy = {v["stock"] for v in CORP.values()}

    # `segment` 등급도 넣는다 — 현장 단위로 못 쪼갤 뿐, 부문별 수주잔고는 실데이터다.
    # 페이지는 입도에 맞춰 '부문별'로 라벨이 바뀐다(없는 정밀도를 주장하지 않는다).
    targets = [r for r in recs
               if r["stock"] not in legacy
               and probe.get(r["stock"], {}).get("tier") in ("site", "segment")]
    if a.only:
        sel = {s.strip() for s in a.only.split(",")}
        targets = [r for r in targets if r["stock"] in sel]

    built, failed, overcount = {}, [], []
    for r in targets:
        try:
            D = kce_series.build(r, quarters)
        except Exception as e:
            failed.append((r["stock"], r["name"], str(e)))
            continue
        built[r["stock"]] = D
        d = os.path.join(KCE, r["slug"])
        os.makedirs(d, exist_ok=True)
        atomic_write(os.path.join(d, "index.html"), company_html(D))
        rc = D["recon"][-1]
        over = D["reconOver"]
        if over:
            overcount.append((r["stock"], r["name"], over))
        print("%-6s %-16s 현장%4d 분기%2d 잔고 %9s억  대조 %s%s"
              % (r["stock"], r["name"][:16],
                 sum(1 for s in D["sites"] if not s.get("agg")), len(D["fq"]),
                 fmt_eok(D["summary"]["bal"][-1]),
                 ("%.0f%%" % rc) if rc is not None else "—",
                 ("  ← 중복 의심 %s" % ",".join(over)) if over else ""))
    for s, n, e in failed:
        print("%-6s %-16s 빌드 실패: %s" % (s, n[:16], e), file=sys.stderr)
    if overcount:
        # 조용히 넘기지 않는다 — 소계 행이 현장으로 섞이면 여기서만 드러난다.
        print("\n[경고] 수록 합이 공시 총계를 넘는 회사 %d곳 — 소계 오분류 의심:"
              % len(overcount), file=sys.stderr)
        for st, nm, qs in overcount:
            print("  %-6s %-16s %s" % (st, nm[:16], ", ".join(qs)), file=sys.stderr)

    if a.all:
        atomic_write(os.path.join(KCE, "coverage.html"),
                     coverage_html(recs, probe, built))
        print("coverage.html — %d종목" % len(recs))
        ip = os.path.join(KCE, "index.html")
        with open(ip, encoding="utf-8") as f:
            old = f.read()
        atomic_write(ip, picker_html(recs, probe, built, old))
        print("index.html — 원본 %d + 신규 %d" % (len(CORP), len(built)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
