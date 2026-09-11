#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kdef_parts — 무기체계 인포그래픽(parts.html).

실루엣 4종(전차·전투기·함정·유도탄)을 **단순한 기하 도형**으로 직접 그린다(외부 이미지 금지).
계통을 고르면 그 계통의 실루엣이 열리고, 부품 영역을 누르면 그 영역의 부품 소분류와
**그 부품을 만드는 상장사**가 오른쪽 패널에 열린다. 회사 이름을 누르면 회사 페이지로 간다.

부품 분류는 규칙(계약명·정기보고서 본문·KIND 문구의 낱말)이라 근거를 칩에 달아 둔다 —
`계약명 「변속기」` 처럼 무엇을 보고 넣었는지 화면에서 바로 보이게 한다(COMMON §0-1).

회사 페이지의 부품 칩은 `parts.html#PROP.TRANS` 로 들어온다 — 해시로 그 소분류를 연다.

    python3 kdef_parts.py
"""
import argparse
import collections
import os
import sys

from kdef_lib import (E, KDEF, TABLE_JS, atomic_write, json_for_html, load_asset, page)
from kdef_universe import load as load_universe
import kdef_suppliers

SRC_KO = {"contract": "계약명", "body": "정기보고서 본문", "kind": "KIND 주요제품"}


def cat_index(sup):
    """소분류 → 그 부품을 만드는 회사 목록."""
    idx = collections.defaultdict(list)
    for co in sup.get("cos", []):
        for h in co["cats"]:
            idx[h["cat"]].append({
                "stock": co["stock"], "nm": co["nm"], "role": co["role"],
                "src": h["src"], "kw": h["kw"], "prod": (co["prod_raw"] or "")[:50],
                "primes": [{"nm": p["nm"], "stock": p["stock"], "basis": p["basis_ko"]}
                           for p in co["primes"][:3]]})
    for v in idx.values():
        v.sort(key=lambda c: ({"contract": 0, "body": 1, "kind": 2}[c["src"]], c["nm"]))
    return idx


def build(data):
    tax, svg = data["tax"], data["svg"]
    idx = cat_index(data["sup"])
    cats = tax["cats"]
    groups = [g for g in tax["groups"] if g["id"] != "UNCL"]
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
        "cats": [{"id": c["id"], "g": c["group"], "ko": c["ko"], "en": c["en"]} for c in cats],
        "groups": {g["id"]: g["ko"] for g in groups},
        "idx": idx,
        "srcKo": SRC_KO,
    }
    body = """
<div class="kpi">
 <div><b>%d</b><span>부품 소분류 · 회사가 붙은 소분류 %d</span></div>
 <div><b>%d</b><span>부품이 확인된 상장사</span></div>
 <div><b>%d</b><span>무기체계 실루엣 · 영역 %d</span></div>
 <div><b>%d</b><span>부품 대분류</span></div>
</div>
<section class="card"><h2>무기체계를 고르고 부품 영역을 누르세요
 <em>영역 → 부품 소분류 → 그 부품을 만드는 상장사 → 납품처(체계업체)</em>
 <span class="right"><button class="chip" id="reset">처음으로</button></span></h2>
 <div class="ctl"><div class="chips" id="sils">%s</div></div>
 <div class="ig">
  <div class="ship">
   <svg id="fig" viewBox="%s" role="img" aria-label="무기체계 단면 — 부품 영역을 눌러 담당 상장사를 봅니다" preserveAspectRatio="xMidYMid meet">
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
<section class="card"><h2>부품 대분류로 진입 <em>위치가 없는 분류(소재·시험/정비)도 여기서 들어갑니다 · 숫자는 연결된 회사 수</em></h2>
 <div class="chips" id="groups">%s</div></section>
<div class="note info">부품 분류는 <b>규칙</b>입니다 — 계약명·정기보고서 II절 본문·KIND 주요제품 문구에서 부품 낱말을 찾습니다.
회사 칩에 근거(무엇을 보고 넣었는지)를 달아 두었습니다. 민수 낱말과 겹치는 짧은 약어는 방산 문맥이 가까이 있을 때만 채택합니다.
납품처(체계업체) 연결의 근거 등급은 주요고객 주석 &gt; 계약공시 상대 &gt; 본문 언급 순입니다.</div>
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
 // 실루엣마다 알아보기 쉬우라고 얹는 단순 도형(포신·기수·물결·핀). 영역이 아니라 장식이다.
 var DECO={
  TANK:[['rect',{x:300,y:78,width:96,height:7,rx:3}],['circle',{cx:95,cy:151,r:13}],
        ['circle',{cx:150,cy:151,r:13}],['circle',{cx:205,cy:151,r:13}],
        ['circle',{cx:260,cy:151,r:13}],['circle',{cx:315,cy:151,r:13}]],
  JET:[['polygon',{points:'8,100 22,95 22,105'}],['polygon',{points:'300,60 340,30 352,32 322,66'}]],
  SHIP:[['rect',{x:20,y:150,width:360,height:3,rx:1}],['polygon',{points:'20,150 380,150 350,168 55,168'}]],
  MSL:[['polygon',{points:'10,100 40,88 40,112'}]]
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
  var primes=c.primes.map(function(p){return '<a href="'+p.stock+'/index.html">'+p.nm+'</a> <span class="mut">'+p.basis+'</span>'}).join(' · ');
  return '<li><a class="co" href="'+c.stock+'/index.html">'+c.nm+'</a>'
   +' <span class="pill" title="'+(P.srcKo[c.src]||c.src)+'에서 «'+c.kw+'»">'+(P.srcKo[c.src]||c.src)+' 「'+c.kw+'」</span>'
   +(primes?'<div class="mut" style="font-size:11px;margin-top:2px">납품처 '+primes+'</div>':'')
   +(c.prod?'<div class="mut" style="font-size:11px">'+c.prod+'</div>':'')+'</li>';
 }
 function catBlock(cid){
  var c=catById(cid); if(!c) return '';
  var cos=P.idx[cid]||[];
  return '<div class="pblock"><h4 id="'+cid+'">'+c.ko+' <span class="mut">'+P.groups[c.g]+' · '+c.en+'</span>'
   +' <span class="n">'+cos.length+'</span></h4>'
   +(cos.length?'<ul class="colist">'+cos.map(coHtml).join('')+'</ul>'
    :'<p class="mut" style="font-size:12px">이 부품을 만드는 상장사를 원문에서 찾지 못했습니다 — 비상장이거나 문구가 짧아 규칙에 안 걸립니다.</p>')
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
   +'<p class="mut" style="font-size:12px">영역 → 부품 소분류 → 그 부품을 만드는 상장사 → 납품처(체계업체). '
   +'회사 이름을 누르면 그 회사의 계약·부문매출 페이지로 갑니다.</p>';
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
    return page("한국방산 — 무기체계 인포그래픽", body, depth=0, h1="무기체계 인포그래픽",
                nav=(("허브", "index.html"), ("커버리지", "coverage.html"),
                     ("← ARGUS", "../index.html")),
                crumbs=(("ARGUS", "../index.html"), ("한국방산", "index.html"),
                        ("인포그래픽", None)),
                lead="전차·전투기·함정·유도탄을 단순 기하도형으로 그린 모식도입니다. 부품 영역을 누르면 "
                     "그 부품의 소분류와, 원문(계약명·정기보고서 본문·KIND 문구)에서 그 부품을 만든다고 "
                     "읽힌 상장사가 열립니다.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", default=True)
    ap.parse_args()
    data = {"tax": load_asset("parts_taxonomy.json"), "svg": load_asset("svg_regions.json"),
            "sup": kdef_suppliers.load(), "uni": load_universe()}
    atomic_write(os.path.join(KDEF, "parts.html"), build(data))
    idx = cat_index(data["sup"])
    print("parts.html · 소분류 %d(회사 붙은 것 %d) · 영역 %d"
          % (len(data["tax"]["cats"]), sum(1 for c in data["tax"]["cats"] if idx.get(c["id"])),
             len(data["svg"]["regions"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
