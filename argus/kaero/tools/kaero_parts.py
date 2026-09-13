#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kaero_parts — 우주항공 부품 인포그래픽(parts.html).

실루엣 4종(여객기 평면도·터보팬 엔진 단면·인공위성·우주 발사체)을 **단순한 기하 도형**으로
직접 그린다(외부 이미지 금지). 그림을 고르고 부품 영역을 누르면 그 영역의 부품 소분류와
**그 부품을 만드는 상장사**가 오른쪽 패널에 열린다. 회사 이름을 누르면 회사 페이지로 간다.

이 산업에서는 회사 뒤에 **고객(OEM·Tier-1·체계업체)** 을 함께 보인다 — 부품보다 고객이
더 잘 공시되기 때문이다(FINDINGS §2: 아스트 수주표 품목 열이 곧 발주처다).

부품 분류는 규칙(공시 품목명·계약명·본문·KIND 문구의 낱말)이라 근거를 칩에 달아 둔다
— `공시 품목명 「Section48」` 처럼 무엇을 보고 넣었는지 화면에서 보이게 한다(COMMON §0-1).

회사 페이지의 부품 칩은 `parts.html#STRUCT.FUSELAGE` 로 들어온다 — 해시로 그 소분류를 연다.

    python3 kaero_parts.py
"""
import argparse
import collections
import os
import sys

from kaero_lib import E, KAERO, TABLE_JS, atomic_write, json_for_html, load_asset, page
from kaero_universe import load as load_universe
import kaero_suppliers

SRC_KO = kaero_suppliers.SRC_KO


def cat_index(sup):
    """소분류 → 그 부품을 만드는 회사 목록."""
    idx = collections.defaultdict(list)
    for co in sup.get("cos", []):
        for h in co["cats"]:
            idx[h["cat"]].append({
                "stock": co["stock"], "nm": co["nm"], "role": co["role"],
                "src": h["src"], "kw": h["kw"], "prod": (co["prod_raw"] or "")[:50],
                "custs": [{"nm": c["name"], "stock": c.get("stock"), "basis": c["basis_ko"],
                           "est": c.get("evidence") == "C"}
                          for c in (co.get("customers") or [])[:3]]})
    rank = {k: i for i, k in enumerate(kaero_suppliers._SRC_RANK)}
    for v in idx.values():
        v.sort(key=lambda c: (rank.get(c["src"], 9), c["nm"]))
    return idx


def build(data):
    tax, svg = data["tax"], data["svg"]
    idx = cat_index(data["sup"])
    cats = tax["cats"]
    groups = tax["groups"]
    n_linked = sum(1 for c in cats if idx.get(c["id"]))
    n_co = len({co["stock"] for co in data["sup"]["cos"] if co["cats"]})

    sil_chips = "".join(
        '<button class="chip" data-sil="%s" aria-pressed="false">%s</button>'
        % (E(s["id"]), E(s["ko"])) for s in svg["silhouettes"])
    group_chips = "".join(
        '<button class="chip" data-group="%s" aria-pressed="false">%s <span class="n">%d</span></button>'
        % (E(g["id"]), E(g["ko"]),
           sum(len(idx.get(c["id"], [])) for c in cats if c["group"] == g["id"]))
        for g in groups)

    embed = {
        "viewBox": svg["viewBox"],
        "sils": svg["silhouettes"],
        "regions": svg["regions"],
        "cats": [{"id": c["id"], "g": c["group"], "ko": c["ko"]} for c in cats],
        "groups": {g["id"]: g["ko"] for g in groups},
        "idx": idx,
        "srcKo": SRC_KO,
    }
    body = """
<div class="kpi">
 <div><b>%d</b><span>부품 소분류 · 회사가 붙은 소분류 %d</span></div>
 <div><b>%d</b><span>부품이 확인된 상장사</span></div>
 <div><b>%d</b><span>실루엣 · 영역 %d</span></div>
 <div><b>%d</b><span>부품 대분류</span></div>
</div>
<section class="card"><h2>그림을 고르고 부품 영역을 누르세요
 <em>영역 → 부품 소분류 → 그 부품을 만드는 상장사 → 그 회사의 고객</em>
 <span class="right"><button class="chip" id="reset">처음으로</button></span></h2>
 <div class="ctl"><div class="chips" id="sils">%s</div></div>
 <div class="ig">
  <div class="ship">
   <svg id="fig" viewBox="%s" role="img" aria-label="항공기·엔진·위성·발사체 모식도 — 부품 영역을 눌러 담당 상장사를 봅니다" preserveAspectRatio="xMidYMid meet">
    <g id="deco"></g><g id="regions"></g><g id="labels" aria-hidden="true"></g>
   </svg>
   <div class="legend">
    <span><i style="background:rgba(57,135,229,.30)"></i>상장사가 있는 영역</span>
    <span><i style="background:rgba(255,255,255,.04)"></i>상장사 미확인</span>
    <span class="mut">도형은 단순 기하도형으로 그린 모식도입니다(축척·형상 아님)</span>
   </div>
  </div>
  <div class="panel" id="panel"></div>
 </div>
</section>
<section class="card"><h2>부품 대분류로 진입 <em>위치가 애매한 분류(소재·정비/시험)도 여기서 들어갑니다 · 숫자는 연결된 회사 수</em></h2>
 <div class="chips" id="groups">%s</div></section>
<div class="note info">부품 분류는 <b>규칙</b>입니다 — 공시 품목명(수주표·매출표)·계약명·정기보고서 II절 본문·
KIND 주요제품 문구에서 부품 낱말을 찾습니다. 회사 칩에 근거를 달아 두었습니다.
항공·우주 밖에서도 흔한 낱말(단조품·정밀가공·안테나·열처리)은 <b>가까이에 항공·우주 문맥어가 있을 때만</b>
채택합니다 — 그러지 않으면 자동차 단조사와 통신 안테나사가 항공 부품사가 됩니다.
고객 연결의 근거 등급은 매출처 표 &gt; 수주표 품목 &gt; 계약공시 상대 &gt; 본문 언급 순이고,
약칭을 사전으로 편 이름은 <b>추정</b>으로 적습니다.</div>
<script>const P=%s;</script>
<script>
(function(){
 var S={sil:P.sils[0].id, sel:null, group:null};
 var fig=document.getElementById('fig'), RG=document.getElementById('regions'),
     LB=document.getElementById('labels'), DC=document.getElementById('deco'),
     panel=document.getElementById('panel');
 var NS='http://www.w3.org/2000/svg';
 function el(n,attrs){ var e=document.createElementNS(NS,n); for(var k in attrs) e.setAttribute(k,attrs[k]); return e; }
 function catById(id){ return P.cats.filter(function(c){return c.id===id})[0]; }
 function hasCo(r){ return r.cats.some(function(c){return (P.idx[c]||[]).length}); }
 // 알아보기 쉬우라고 얹는 단순 도형(기수 끝·축선·윙렛). 영역이 아니라 장식이다.
 var DECO={
  AIRLINER:[['polygon',{points:'28,100 40,96 40,104'}],
            ['rect',{x:224,y:24,width:6,height:14,rx:2}],
            ['rect',{x:224,y:162,width:6,height:14,rx:2}]],
  ENG:[['rect',{x:92,y:97,width:230,height:6,rx:3}],
       ['circle',{cx:66,cy:100,r:6}]],
  SAT:[['rect',{x:196,y:164,width:8,height:14,rx:2}],
       ['circle',{cx:200,cy:30,r:5}]],
  LV:[['polygon',{points:'16,100 30,93 30,107'}],
      ['rect',{x:198,y:56,width:6,height:12,rx:2}],
      ['rect',{x:198,y:132,width:6,height:12,rx:2}]]
 };
 function draw(){
  RG.textContent=''; LB.textContent=''; DC.textContent='';
  (DECO[S.sil]||[]).forEach(function(d){ var e=el(d[0],d[1]); e.setAttribute('class','deco'); DC.appendChild(e); });
  P.regions.filter(function(r){return r.silhouette===S.sil}).forEach(function(r){
   var g=el('polygon',{points:r.points});
   g.setAttribute('class','rg'+(hasCo(r)?' has':'')+(S.sel===r.id?' on':''));
   g.setAttribute('tabindex','0'); g.setAttribute('role','button');
   g.setAttribute('aria-label',r.ko);
   g.addEventListener('click',function(){ S.group=null; S.sel=r.id; draw(); showRegion(r); });
   g.addEventListener('keydown',function(e){ if(e.key==='Enter'||e.key===' '){e.preventDefault(); g.dispatchEvent(new Event('click'));} });
   RG.appendChild(g);
   var t=el('text',{x:r.label.x,y:r.label.y}); t.setAttribute('class','rlbl');
   t.setAttribute('text-anchor','middle'); t.textContent=r.ko; LB.appendChild(t);
  });
  Array.prototype.forEach.call(document.querySelectorAll('#sils .chip'),function(b){
   var on=b.getAttribute('data-sil')===S.sil; b.classList.toggle('on',on); b.setAttribute('aria-pressed',on);
  });
  Array.prototype.forEach.call(document.querySelectorAll('#groups .chip'),function(b){
   var on=b.getAttribute('data-group')===S.group; b.classList.toggle('on',on); b.setAttribute('aria-pressed',on);
  });
 }
 function coHtml(c){
  var cu=c.custs.map(function(p){
    var nm=p.stock?('<a href="'+p.stock+'/index.html">'+p.nm+'</a>'):p.nm;
    return nm+' <span class="mut">'+p.basis+(p.est?' · 추정':'')+'</span>';
  }).join(' · ');
  return '<li><a class="co" href="'+c.stock+'/index.html">'+c.nm+'</a>'
   +' <span class="pill" title="'+(P.srcKo[c.src]||c.src)+'에서 «'+c.kw+'»">'+(P.srcKo[c.src]||c.src)+' 「'+c.kw+'」</span>'
   +(cu?'<div class="mut" style="font-size:11px;margin-top:2px">고객 '+cu+'</div>':'')
   +(c.prod?'<div class="mut" style="font-size:11px">'+c.prod+'</div>':'')+'</li>';
 }
 function catBlock(cid){
  var c=catById(cid); if(!c) return '';
  var cos=P.idx[cid]||[];
  return '<div class="pblock"><h4 id="'+cid+'">'+c.ko+' <span class="mut">'+P.groups[c.g]+'</span>'
   +' <span class="n">'+cos.length+'</span></h4>'
   +(cos.length?'<ul class="colist">'+cos.map(coHtml).join('')+'</ul>'
    :'<p class="mut" style="font-size:12px">이 부품을 만드는 상장사를 원문에서 찾지 못했습니다 — 비상장이거나 공시 문구가 짧아 규칙에 안 걸립니다.</p>')
   +'</div>';
 }
 function showRegion(r){
  panel.innerHTML='<h3>'+r.ko+' <em>'+r.cats.length+'개 소분류</em></h3>'+r.cats.map(catBlock).join('');
 }
 function showGroup(gid){
  var cs=P.cats.filter(function(c){return c.g===gid});
  panel.innerHTML='<h3>'+P.groups[gid]+' <em>'+cs.length+'개 소분류</em></h3>'+cs.map(function(c){return catBlock(c.id)}).join('');
 }
 function showCat(cid){
  var c=catById(cid); if(!c) return false;
  var r=P.regions.filter(function(r){return r.cats.indexOf(cid)>=0})[0];
  if(r){ S.sil=r.silhouette; S.sel=r.id; }
  S.group=null; draw();
  panel.innerHTML='<h3>'+c.ko+' <em>'+P.groups[c.g]+'</em></h3>'+catBlock(cid)
   +(r?'<p class="mut" style="font-size:12px">위치: '+r.ko+'</p>':'');
  return true;
 }
 function intro(){
  panel.innerHTML='<h3>부품 영역을 누르세요 <em>또는 아래 대분류 칩</em></h3>'
   +'<p class="mut" style="font-size:12px">영역 → 부품 소분류 → 그 부품을 만드는 상장사 → 그 회사의 고객. '
   +'회사 이름을 누르면 그 회사의 수주·고객 페이지로 갑니다.</p>';
 }
 Array.prototype.forEach.call(document.querySelectorAll('#sils .chip'),function(b){
  b.addEventListener('click',function(){ S.sil=b.getAttribute('data-sil'); S.sel=null; S.group=null; draw(); intro(); });
 });
 Array.prototype.forEach.call(document.querySelectorAll('#groups .chip'),function(b){
  b.addEventListener('click',function(){ S.group=b.getAttribute('data-group'); S.sel=null; draw(); showGroup(S.group); });
 });
 document.getElementById('reset').addEventListener('click',function(){ S.sel=null; S.group=null; draw(); intro(); });
 window.addEventListener('hashchange',function(){ var h=location.hash.slice(1); if(h) showCat(h); });
 var h=location.hash.slice(1);
 draw();
 if(!(h&&showCat(h))) intro();
})();
</script>
<script>%s</script>
""" % (len(cats), n_linked, n_co, len(svg["silhouettes"]), len(svg["regions"]), len(groups),
       sil_chips, E(svg["viewBox"]), group_chips, json_for_html(embed), TABLE_JS)
    return page("한국우주항공 — 부품 인포그래픽", body, depth=0, h1="부품 인포그래픽",
                nav=(("허브", "index.html"), ("커버리지", "coverage.html"),
                     ("← ARGUS", "../index.html")),
                crumbs=(("ARGUS", "../index.html"), ("한국우주항공", "index.html"),
                        ("인포그래픽", None)),
                lead="여객기·터보팬 엔진·인공위성·우주 발사체를 단순 기하도형으로 그린 모식도입니다. "
                     "부품 영역을 누르면 그 부품의 소분류와, 원문(공시 품목명·계약명·본문·KIND 문구)에서 "
                     "그 부품을 만든다고 읽힌 상장사가 열립니다.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", default=True)
    ap.parse_args()
    data = {"tax": load_asset("parts_taxonomy.json"), "svg": load_asset("svg_regions.json"),
            "sup": kaero_suppliers.load(), "uni": load_universe()}
    atomic_write(os.path.join(KAERO, "parts.html"), build(data))
    idx = cat_index(data["sup"])
    print("parts.html · 소분류 %d(회사 붙은 것 %d) · 영역 %d"
          % (len(data["tax"]["cats"]), sum(1 for c in data["tax"]["cats"] if idx.get(c["id"])),
             len(data["svg"]["regions"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
