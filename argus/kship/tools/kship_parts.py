#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_parts — 선박 단면 인포그래픽(parts.html)과 기자재사 페이지(<종목>/index.html).

인포그래픽: 선종을 고르면 그 선종에 관련된 부품 영역이 강조되고(관련도 0~3, 근거 등급 A/B/C),
영역을 누르면 그 영역의 소분류 → 그 부품을 만드는 상장 기자재사 → 납품 조선사(근거 등급)가
오른쪽 패널에 열린다. 회사 이름을 누르면 회사 페이지로 간다. 기관실은 2차 확대(엔진부품 6영역).

원칙: 분류는 원문 제품 문구의 키워드 규칙이고(est 표시), 납품 관계는 정기보고서 본문 언급
수준이 많다 — 근거 등급을 항상 같이 보여 준다. 임베드 JSON은 json_for_html 로만 넣는다.

    python3 kship_parts.py --all
"""
import argparse
import collections
import os
import sys

from kship_lib import (E, KSHIP, TABLE_JS, atomic_write, fmt_eok, json_for_html, load_asset, page)

YARD_LABEL = {"329180": "HD현대중공업", "010140": "삼성중공업", "042660": "한화오션", "010620": "HD현대미포(합병)",
              "HSHI": "HD현대삼호(비상장)", "009540": "HD한국조선해양", "439260": "대한조선", "097230": "HJ중공업",
              "KSOE_GRP": "HD현대 그룹(모호)"}
YARD_PAGE = {"329180", "010140", "042660", "439260", "097230"}
BASIS_KO = {"ifrs8": "주요고객 주석", "contract": "계약 공시", "related": "특수관계자", "text": "본문 언급",
            "manual": "수동 확인", "kind": "KIND 문구", "report": "정기보고서 제품표", "seed": "지정 사유"}


def idx_cat2co(data):
    out = collections.defaultdict(list)
    for co in data["suppliers"].get("cos", []):
        yards = [y["yard"] for y in co.get("yards", [])]
        for c in co["cats"]:
            if c["cat"] == "UNCL":
                continue
            if any(x["stock"] == co["stock"] for x in out[c["cat"]]):
                continue
            out[c["cat"]].append({"stock": co["stock"], "nm": co["nm"], "prod": c["prod"][:40], "share": c.get("share"),
                                  "est": c.get("est", False), "basis": c.get("basis", ""), "yards": yards[:4], "confirmed": co.get("confirmed", False)})
    return out


def parts_html(data):
    tax, svg, types = data["tax"], data["svg"], data["types"]
    idx = idx_cat2co(data)
    groups = tax["groups"]
    cats = tax["cats"]
    tm = {t["id"]: t for t in types["types"]}
    palette_slots = {t["id"]: t.get("color_slot") for t in types["types"]}
    from kship_lib import slot_color
    type_colors = {tid: slot_color(s) for tid, s in palette_slots.items() if s}
    n_co = sum(1 for _ in data["suppliers"].get("cos", []))
    n_cat_with = sum(1 for c in cats if idx.get(c["id"]))

    # ── SVG 정적 부분: 바다·선체 실루엣·흘수선·라벨은 서버에서, 영역 폴리곤은 클라이언트가 variant 로 그린다
    hull = ("M 45,335 L 60,306 L 920,306 L 955,330 L 880,360 L 125,360 Z")
    static_svg = """
<svg id="ship" viewBox="0 0 1000 400" role="img" aria-label="선박 측면 단면 — 부품 영역을 눌러 담당 기자재사를 봅니다" preserveAspectRatio="xMidYMid meet">
 <rect class="sea" x="0" y="300" width="1000" height="100"/>
 <line class="wl" x1="0" y1="300" x2="1000" y2="300"/>
 <path class="hull" d="%s"/>
 <g id="regions"></g>
 <g id="labels" aria-hidden="true"></g>
</svg>
<svg id="engine" viewBox="0 0 1000 400" role="img" aria-label="주기관 단면 — 엔진 부품 영역" preserveAspectRatio="xMidYMid meet" hidden>
 <rect x="300" y="20" width="400" height="350" rx="10" fill="rgba(255,255,255,.03)" stroke="rgba(255,255,255,.25)"/>
 <g id="eregions"></g><g id="elabels" aria-hidden="true"></g>
</svg>""" % hull

    type_chips = "".join('<button class="chip" data-type="%s" aria-pressed="false"><i class="sw" style="background:%s"></i>%s</button>'
                         % (E(t["id"]), E(type_colors.get(t["id"], "#5d6675")), E(t["ko"])) for t in types["types"])
    mod_chips = "".join('<button class="chip" data-mod="%s" aria-pressed="false">%s</button>' % (E(m["id"]), E(m["ko"])) for m in types.get("mods", []))
    group_chips = "".join('<button class="chip" data-group="%s" aria-pressed="false">%s <span class="n">%d</span></button>'
                          % (E(g["id"]), E(g["ko"]), sum(len(idx.get(c["id"], [])) for c in cats if c["p"] == g["id"]))
                          for g in groups if g["id"] != "UNCL")

    embed = {
        "regions": svg["regions"], "z": svg["z"], "engine": svg["engine_zoom"],
        "cats": [{"id": c["id"], "p": c["p"], "ko": c["ko"], "en": c["en"], "region": c["region"]} for c in cats],
        "groups": {g["id"]: g["ko"] for g in groups},
        "types": [{"id": t["id"], "ko": t["ko"], "variant": t.get("variant", "default"), "color": type_colors.get(t["id"], "#5d6675")} for t in types["types"]],
        "mods": types.get("mods", []),
        "rel": types["rel"],
        "idx": idx,
        "yards": YARD_LABEL, "yardPage": sorted(YARD_PAGE), "basis": BASIS_KO,
    }
    body = """
<div class="kpi">
 <div><b>%d</b><span>부품 소분류 · 회사가 연결된 소분류 %d</span></div>
 <div><b>%d</b><span>상장 기자재사(모집단)</span></div>
 <div><b>%d</b><span>선종 · 관련도는 근거 등급 A/B/C</span></div>
 <div><b>%d</b><span>인포그래픽 영역 · 기관실 확대 %d</span></div>
</div>
<section class="card"><h2>선종을 고르면 관련 부품이 강조됩니다 <em>관련도 3 핵심 · 2 중요 · 1 공통 · 0 없음 — 부품 영역을 누르면 담당 회사</em><span class="right"><button class="chip" id="reset">전체 보기</button></span></h2>
 <div class="ctl"><div class="chips" id="types">%s</div><span class="mut" style="font-size:10.5px">수식어</span><div class="chips" id="mods">%s</div></div>
 <div class="ig">
  <div class="ship">%s<div class="legend"><span><i style="background:rgba(96,165,250,.26)"></i>핵심(3)</span><span><i style="background:rgba(96,165,250,.14)"></i>중요(2)</span><span><i style="background:rgba(96,165,250,.06)"></i>공통(1)</span><span><i style="background:rgba(255,255,255,.015)"></i>해당 없음(0)</span><span><i style="border-style:dashed"></i>상장 기자재사 없음</span><span id="zoomhint" class="mut"></span></div></div>
  <div class="panel" id="panel"><h3>부품 영역을 누르세요 <em>또는 아래 대분류 칩</em></h3><p class="mut" style="font-size:12px">영역 → 소분류 → 그 부품을 만드는 상장 기자재사 → 납품 조선사(근거). 회사 이름을 누르면 회사 페이지로 갑니다.</p></div>
 </div>
</section>
<section class="card"><h2>대분류로 진입 <em>분산 시스템(전장·배관·도장·안전)은 특정 위치가 없어 여기서 들어갑니다 · 숫자는 연결된 회사 수</em></h2><div class="chips" id="groups">%s</div></section>
<div class="note info">부품 분류는 정기보고서 「주요 제품」·KIND 주요제품 문구의 키워드 규칙이고, 납품 조선사는 사업의 내용 본문에서 이름이 언급된 것을 근거로 합니다(주요고객 비중이 적힌 경우만 %%). 근거가 약한 항목은 <span class="pill est">추정</span>으로 표시합니다. 선종별 관련도 등급 C는 업계 통념에 기댄 추정입니다.</div>
<script>const P=%s;</script>
<script>%s</script>
<script>
(function(){
  var S={type:null,mods:{},sel:null,group:null,zoom:false};
  var svg=document.getElementById('ship'),G=document.getElementById('regions'),L=document.getElementById('labels');
  var esvg=document.getElementById('engine'),EG=document.getElementById('eregions'),EL=document.getElementById('elabels');
  var catById={}; P.cats.forEach(function(c){catById[c.id]=c;});
  var regById={}; P.regions.forEach(function(r){regById[r.id]=r;});
  function variant(){ var t=P.types.filter(function(t){return t.id===S.type})[0]; return t?t.variant:'default'; }
  function relOf(cat){ if(!S.type) return null; var v=(P.rel[S.type]||{})[cat]; var r=v?v[0]:0; Object.keys(S.mods).forEach(function(m){ if(!S.mods[m]) return; var md=P.mods.filter(function(x){return x.id===m})[0]; if(md&&md.plus&&md.plus[cat]) r=Math.min(3,r+md.plus[cat]); }); return r; }
  function gradeOf(cat){ if(!S.type) return ''; var v=(P.rel[S.type]||{})[cat]; return v?v[1]:''; }
  function regionRel(r){ if(!S.type||!r.cats.length) return null; return Math.max.apply(null,r.cats.map(relOf)); }
  function hasCo(r){ return r.cats.some(function(c){return (P.idx[c]||[]).length}); }
  function centroid(pts){ var x=0,y=0; pts.forEach(function(p){x+=p[0];y+=p[1]}); return [x/pts.length,y/pts.length]; }
  function shapeEl(v){ var el; if(v&&v.circle){ el=document.createElementNS('http://www.w3.org/2000/svg','circle'); el.setAttribute('cx',v.circle[0]); el.setAttribute('cy',v.circle[1]); el.setAttribute('r',v.circle[2]); } else { el=document.createElementNS('http://www.w3.org/2000/svg','polygon'); el.setAttribute('points',v.map(function(p){return p.join(',')}).join(' ')); } return el; }
  function draw(){
    var vr=variant(); G.textContent=''; L.textContent='';
    P.z.forEach(function(id){ var r=regById[id]; if(!r) return; var v=r.variants[vr]; if(!v||(Array.isArray(v)&&!v.length)) return;
      var el=shapeEl(v); el.setAttribute('class','rg'); el.setAttribute('data-id',r.id); el.setAttribute('tabindex','0'); el.setAttribute('role','button');
      var t=document.createElementNS('http://www.w3.org/2000/svg','title'); t.textContent=r.ko+(r.cats.length?' — '+r.cats.map(function(c){return catById[c]?catById[c].ko:c}).join(', '):''); el.appendChild(t);
      var rel=regionRel(r); if(rel!==null) el.classList.add('rel'+rel); if(!hasCo(r)) el.classList.add('none'); if(S.sel===r.id) el.classList.add('sel');
      el.addEventListener('click',function(){select(r.id)}); el.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();select(r.id)}});
      G.appendChild(el);
      var big=['R_CARGO_1','R_CARGO_2','R_CARGO_3','R_CARGO_4','R_DECKHOUSE','R_MAIN_ENGINE','R_BOW','R_FUNNEL','R_BRIDGE','R_TOPSIDE_1','R_TOPSIDE_2','R_TOPSIDE_3','R_TOPSIDE_4','R_DECK_CARGO','R_TURRET'];
      if(big.indexOf(r.id)>=0){ var c=v.circle?[v.circle[0],v.circle[1]]:centroid(v); var tx=document.createElementNS('http://www.w3.org/2000/svg','text'); tx.setAttribute('x',c[0]); tx.setAttribute('y',c[1]+4); tx.setAttribute('text-anchor','middle'); tx.textContent=r.ko.replace(/ \\d$/,''); L.appendChild(tx); }
    });
    document.getElementById('zoomhint').textContent=S.type?('선종: '+P.types.filter(function(t){return t.id===S.type})[0].ko+' · 주기관을 누르면 엔진 부품 확대'):'주기관을 누르면 엔진 부품 확대';
  }
  function drawEngine(){ EG.textContent=''; EL.textContent=''; P.engine.regions.forEach(function(r){ var el=shapeEl(r.poly); el.setAttribute('class','rg'+(S.sel==='E:'+r.id?' sel':'')); el.setAttribute('tabindex','0'); el.setAttribute('role','button');
      var rel=S.type?Math.max.apply(null,r.cats.map(relOf)):null; if(rel!==null) el.classList.add('rel'+rel); if(!r.cats.some(function(c){return (P.idx[c]||[]).length})) el.classList.add('none');
      el.addEventListener('click',function(){selectCats(r.cats,r.ko,'E:'+r.id)}); EG.appendChild(el);
      var c=centroid(r.poly); var tx=document.createElementNS('http://www.w3.org/2000/svg','text'); tx.setAttribute('x',c[0]); tx.setAttribute('y',c[1]+4); tx.setAttribute('text-anchor','middle'); tx.textContent=r.ko; EL.appendChild(tx); }); }
  function select(id){ var r=regById[id]; if(!r) return; if(r.zoom==='engine'){ S.zoom=!S.zoom; esvg.hidden=!S.zoom; if(S.zoom){drawEngine();} }
    S.sel=id; draw(); selectCats(r.cats,r.ko,id); }
  function el(tag,cls,text){ var e=document.createElement(tag); if(cls) e.className=cls; if(text!=null) e.textContent=text; return e; }
  function selectCats(catIds,title,selId){
    S.sel=selId; var pan=document.getElementById('panel'); pan.textContent='';
    var h=el('h3',null,title); var em=el('em',null,S.type?('관련도 기준 선종: '+P.types.filter(function(t){return t.id===S.type})[0].ko):'선종 미선택'); h.appendChild(em); pan.appendChild(h);
    if(!catIds.length){ pan.appendChild(el('p','mut','이 영역은 묶음 영역입니다 — 안쪽 영역을 누르세요.')); return; }
    catIds.slice().sort(function(a,b){ return (relOf(b)||0)-(relOf(a)||0); }).forEach(function(cid){
      var c=catById[cid]; if(!c) return; var rel=relOf(cid), gr=gradeOf(cid);
      var head=el('div',null); head.style.cssText='margin-top:10px;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap';
      var b=el('b',null,c.ko); head.appendChild(b); var s=el('span','mut',(P.groups[c.p]||c.p)+' · '+c.id); s.style.fontSize='10.5px'; head.appendChild(s);
      if(rel!==null){ var pill=el('span','pill','관련도 '+rel+(gr?' · 근거 '+gr:'')); if(gr==='C') pill.className='pill est'; head.appendChild(pill); }
      pan.appendChild(head);
      var cos=P.idx[cid]||[]; if(!cos.length){ pan.appendChild(el('p','mut','이 부품을 주력으로 하는 상장사가 모집단에 없거나 아직 원문 확인 전입니다.')); return; }
      var ul=el('ul'); cos.slice().sort(function(a,b){return (b.confirmed?1:0)-(a.confirmed?1:0)}).forEach(function(co){
        var li=el('li'); var a=el('a',null,co.nm); a.href=co.stock+'/index.html'; li.appendChild(a);
        var right=el('span'); if(co.share!=null){ right.appendChild(el('span','y','매출비중 '+co.share+'%% ')); }
        if(co.est){ right.appendChild(el('span','pill est','추정')); }
        (co.yards||[]).forEach(function(y){ var t=el('span','yardtag',P.yards[y]||y); right.appendChild(t); });
        if(!(co.yards||[]).length) right.appendChild(el('span','y','납품처 언급 없음'));
        li.appendChild(right); ul.appendChild(li); });
      pan.appendChild(ul); });
  }
  document.querySelectorAll('#types .chip').forEach(function(b){ b.addEventListener('click',function(){ var t=b.dataset.type; S.type=(S.type===t?null:t); document.querySelectorAll('#types .chip').forEach(function(x){x.setAttribute('aria-pressed',String(x.dataset.type===S.type))}); draw(); if(S.zoom) drawEngine(); if(S.sel){ var r=regById[S.sel]; if(r) selectCats(r.cats,r.ko,S.sel); } }); });
  document.querySelectorAll('#mods .chip').forEach(function(b){ b.addEventListener('click',function(){ var m=b.dataset.mod; S.mods[m]=!S.mods[m]; b.setAttribute('aria-pressed',String(!!S.mods[m])); draw(); if(S.zoom) drawEngine(); }); });
  document.querySelectorAll('#groups .chip').forEach(function(b){ b.addEventListener('click',function(){ var g=b.dataset.group; document.querySelectorAll('#groups .chip').forEach(function(x){x.setAttribute('aria-pressed',String(x===b))}); selectCats(P.cats.filter(function(c){return c.p===g}).map(function(c){return c.id}),(P.groups[g]||g)+' — 대분류 전체','G:'+g); S.sel=null; draw(); }); });
  document.getElementById('reset').addEventListener('click',function(){ S.type=null; S.mods={}; S.sel=null; S.zoom=false; esvg.hidden=true; document.querySelectorAll('.chip[aria-pressed]').forEach(function(x){x.setAttribute('aria-pressed','false')}); draw(); document.getElementById('panel').innerHTML=''; document.getElementById('panel').appendChild(el('h3',null,'부품 영역을 누르세요')); });
  if(location.hash){ var g=location.hash.slice(1); var btn=document.querySelector('#groups .chip[data-group="'+g+'"]'); if(btn) btn.click(); }
  draw();
})();
</script>
""" % (len(cats), n_cat_with, n_co, len(types["types"]), len(svg["regions"]), len(svg["engine_zoom"]["regions"]),
       type_chips, mod_chips, static_svg, group_chips, json_for_html(embed), TABLE_JS)
    return page("선박 단면 인포그래픽 — 부품 · 기자재사 · 조선사", body, depth=0, h1="⚓ 선박 단면 인포그래픽",
                nav=(("허브", "index.html"), ("커버리지", "coverage.html"), ("← ARGUS", "../index.html")),
                crumbs=(("ARGUS", "../index.html"), ("한국조선", "index.html"), ("인포그래픽", None)),
                lead="선박을 부품 영역으로 나누고, 각 영역에 그 부품을 만드는 국내 상장 기자재사와 납품 조선사를 연결했습니다. 선종을 고르면 관련도가 영역 농도로 표시됩니다.")


def supplier_html(co, data):
    tax = {c["id"]: c for c in data["tax"]["cats"]}
    groups = {g["id"]: g["ko"] for g in data["tax"]["groups"]}
    idx = idx_cat2co(data)
    cats = [c for c in co["cats"] if c["cat"] != "UNCL"]
    uncl = [c for c in co["cats"] if c["cat"] == "UNCL"]
    yards = co.get("yards", [])
    dart = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=%s" % co["rcp"] if co.get("rcp") else "https://dart.fss.or.kr"
    kpi = ['<div><b>%d</b><span>부품 소분류(분류됨) · 미분류 %d</span></div>' % (len({c["cat"] for c in cats}), len(uncl)),
           '<div><b>%d</b><span>납품 조선사(원문 언급)</span></div>' % len(yards),
           '<div><b>%s</b><span>원문</span><i class="mut">%s</i></div>' % (E(co.get("quarter") or "미수집"), "정기보고서 II 절" if co.get("seen") else "KIND 문구만 — DART 원문 확인 대기")]
    rows = "".join("<tr><td class=\"l\"><b>%s</b><span class=\"mut\" style=\"font-size:10.5px;margin-left:6px\">%s</span></td><td class=\"l\">%s</td><td>%s</td><td class=\"l\">%s%s</td></tr>" % (
        E(tax[c["cat"]]["ko"]) if c["cat"] in tax else E(c["cat"]), E(groups.get(c["cat"].split(".")[0], "")), E(c["prod"][:80]),
        ("%.1f%%" % c["share"]) if c.get("share") is not None else "—", E(BASIS_KO.get(c.get("basis", ""), c.get("basis", ""))),
        ' <span class="pill est">추정</span>' if c.get("est") else "") for c in cats)
    urows = "".join("<tr><td class=\"l mut\">%s</td></tr>" % E(c["prod"][:90]) for c in uncl)
    yrows = "".join("<tr><td class=\"l\">%s</td><td class=\"l\">%s</td><td>%s</td><td>%s</td></tr>" % (
        ('<a href="../%s/index.html">%s</a>' % (E(y["yard"]), E(YARD_LABEL.get(y["yard"], y["yard"])))) if y["yard"] in YARD_PAGE else E(YARD_LABEL.get(y["yard"], y["yard"])),
        E(BASIS_KO.get(y.get("basis", ""), y.get("basis", ""))), (str(y["mentions"]) + "회") if y.get("mentions") else "—", ("%.1f%%" % y["share"]) if y.get("share") else "—") for y in yards)
    peers = collections.OrderedDict()
    for c in cats:
        for o in idx.get(c["cat"], []):
            if o["stock"] != co["stock"]:
                peers.setdefault(c["cat"], []).append(o)
    prow = "".join("<tr><td class=\"l\">%s</td><td class=\"l\">%s</td></tr>" % (E(tax[k]["ko"] if k in tax else k), " · ".join('<a href="../%s/index.html">%s</a>' % (E(o["stock"]), E(o["nm"])) for o in v[:8])) for k, v in peers.items())
    body = """
<div class="kpi">%s</div>
<section class="card"><h2>부품 분류 <em>정기보고서 「주요 제품」·KIND 주요제품 문구 → 키워드 규칙 · 매출비중은 원문에 있을 때만</em></h2>
<div class="wrap"><table data-sortable><thead><tr><th class="l">소분류</th><th class="l">원문 제품 표기</th><th>매출비중</th><th class="l">근거</th></tr></thead><tbody>%s</tbody></table></div>
%s</section>
<section class="card"><h2>납품 조선사 <em>사업의 내용 본문에서 조선사 이름이 언급된 횟수 · 비중은 원문에 적힌 경우만</em></h2>
%s</section>
<section class="card"><h2>같은 부품을 만드는 다른 상장사</h2>%s</section>
<div class="note info">KIND 주요제품: %s%s</div>
<script>%s</script>
""" % ("".join(kpi), rows,
       ('<p class="mut" style="font-size:11.5px;margin-top:8px">분류하지 못한 제품 표기 %d건 — 키워드 사전을 넓히거나 assets/parts_override.csv 로 지정하면 반영됩니다.</p><div class="wrap"><table><tbody>%s</tbody></table></div>' % (len(uncl), urows)) if uncl else "",
       ('<div class="wrap"><table data-sortable><thead><tr><th class="l">조선사</th><th class="l">근거</th><th>언급</th><th>비중</th></tr></thead><tbody>%s</tbody></table></div>' % yrows) if yards else '<p class="mut">원문에서 조선사 이름을 찾지 못했습니다 — 납품 관계를 주장하지 않습니다.</p>',
       ('<div class="wrap"><table><thead><tr><th class="l">소분류</th><th class="l">회사</th></tr></thead><tbody>%s</tbody></table></div>' % prow) if prow else '<p class="mut">없음</p>',
       E(co["prod_raw"]), (" · 지정 사유: " + E(co["reason"])) if co.get("reason") else "", TABLE_JS)
    return page("%s — 조선기자재" % co["nm"], body, depth=1, h1=co["nm"], tags=(co["stock"], co["mkt"], co["ind"]),
                nav=(("인포그래픽", "../parts.html"), ("허브", "../index.html"), ("DART 원문 ↗", dart)),
                crumbs=(("ARGUS", "../../index.html"), ("한국조선", "../index.html"), (co["nm"], None)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    from kship_page import load_all
    data = load_all()
    atomic_write(os.path.join(KSHIP, "parts.html"), parts_html(data))
    n = 0
    for co in data["suppliers"].get("cos", []):
        d = os.path.join(KSHIP, co["stock"])
        os.makedirs(d, exist_ok=True)
        atomic_write(os.path.join(d, "index.html"), supplier_html(co, data))
        n += 1
    print("parts.html · 기자재사 페이지 %d장" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
