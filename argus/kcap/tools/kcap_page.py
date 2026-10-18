#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kcap_page — 한국화학 캐파 탭 페이지 생성기.

입력: assets/universe.json · capacity/<stock>.json · ledger.json · model.json · events/<stock>.json(있으면)
출력(argus/kcap/):
  index.html            허브 — 모집단·편입 KPI, 회사 카드(캐파·매핑 커버리지·다음 분기 추정), 최근 캐파 변동·이벤트
  products.html         제품 → 회사별 생산능력 → 연결된 스프레드(매트릭스)
  changes.html          캐파 변동(연간 열 비교)·수시공시 이벤트(신규시설투자·생산중단·영업정지) 타임라인
  coverage.html         모집단 전수와 편입·제외 근거, 미매핑 품목, 금액 기준 회사
  <종목코드>/index.html  회사 — 제품별 생산능력·가동률 이력·변동, 매핑, 분기 프록시 vs 보고 영업이익, 다음 분기 추정
규칙: 원문이 지지하는 값만 '값', 나머지는 전부 '추정' 표시. 빌드 시각은 쓰지 않는다.
"""
import json
import os
import sys

from kcap_lib import ASSETS, DATA_DIR, E, KCAP, TABLE_JS, atomic_write, fmt, fmt_kt, json_for_html, load_asset, page

NAV = (("← ARGUS", "../index.html"), ("🧪 한국화학", "../kchem/index.html"), ("제품", "products.html"), ("변동·이벤트", "changes.html"), ("커버리지", "coverage.html"))

CHART_JS = r"""
(function(){
  function el(t,a){var e=document.createElementNS('http://www.w3.org/2000/svg',t);for(var k in a){e.setAttribute(k,a[k]);}return e;}
  function fin(v){return typeof v==='number'&&isFinite(v);}
  function fmt(v){if(!fin(v))return '—';var s=Math.abs(v)>=1000?Math.round(v).toLocaleString('en-US'):v.toFixed(1);return s.replace('-','−');}
  /* 프록시(막대) vs 보고 영업이익(선) vs 보정 추정(점선) — data-rows 는 JSON [{q,proxy,op,fit,lo,hi,status}] */
  function draw(box){
    var rows=JSON.parse(box.dataset.rows||'[]'); box.textContent=''; if(!rows.length){box.textContent='데이터 없음';return;}
    var W=Math.max(360,box.clientWidth||720),H=260,L=58,R=14,T=16,B=30,n=rows.length;
    var vals=[]; rows.forEach(function(r){['proxy','op','fit','lo','hi'].forEach(function(k){if(fin(r[k]))vals.push(r[k]);});});
    var lo=Math.min.apply(null,vals.concat([0])),hi=Math.max.apply(null,vals.concat([0])); var pad=(hi-lo)*0.08||1; lo-=pad; hi+=pad;
    var svg=el('svg',{viewBox:'0 0 '+W+' '+H,'class':'kchart',role:'img'}); box.appendChild(svg);
    var x=function(i){return L+(W-L-R)*(i+0.5)/n;}, y=function(v){return T+(H-T-B)*(1-(v-lo)/(hi-lo));}, bw=Math.max(4,(W-L-R)/n*0.55);
    for(var t=0;t<=4;t++){var v=lo+(hi-lo)*t/4;svg.appendChild(el('line',{x1:L,x2:W-R,y1:y(v),y2:y(v),'class':'grid'}));var tx=el('text',{x:L-6,y:y(v)+3.5,'class':'tk','text-anchor':'end'});tx.textContent=fmt(v);svg.appendChild(tx);}
    if(lo<0&&hi>0){svg.appendChild(el('line',{x1:L,x2:W-R,y1:y(0),y2:y(0),'class':'zero'}));}
    rows.forEach(function(r,i){
      if(fin(r.proxy)){var h=Math.abs(y(r.proxy)-y(0)); svg.appendChild(el('rect',{x:x(i)-bw/2,y:Math.min(y(r.proxy),y(0)),width:bw,height:h,fill:r.status==='추정'?'#fbbf24':'#3987e5',opacity:r.status==='추정'?0.55:0.85,rx:2}));}
      if(fin(r.lo)&&fin(r.hi)){svg.appendChild(el('line',{x1:x(i)+bw*0.35,x2:x(i)+bw*0.35,y1:y(r.lo),y2:y(r.hi),stroke:'#fbbf24','stroke-width':2,'stroke-dasharray':'3 2'}));}
      if(i%Math.max(1,Math.floor(n/8))===0||i===n-1){var tt=el('text',{x:x(i),y:H-9,'class':'tk','text-anchor':'middle'});tt.textContent=r.q;svg.appendChild(tt);}
    });
    var dOp='',dFit=''; rows.forEach(function(r,i){ if(fin(r.op)){dOp+=(dOp?'L':'M')+x(i).toFixed(1)+' '+y(r.op).toFixed(1);} if(fin(r.fit)){dFit+=(dFit?'L':'M')+x(i).toFixed(1)+' '+y(r.fit).toFixed(1);} });
    if(dFit){svg.appendChild(el('path',{d:dFit,'class':'ln',stroke:'#fbbf24','stroke-dasharray':'4 3'}));}
    if(dOp){svg.appendChild(el('path',{d:dOp,'class':'ln',stroke:'#4ade80','stroke-width':2.2}));}
    rows.forEach(function(r,i){ if(fin(r.op)){svg.appendChild(el('circle',{cx:x(i),cy:y(r.op),r:3,fill:'#4ade80'}));} });
    var lg=document.createElement('div'); lg.className='legend';
    [['#3987e5','스프레드 마진 프록시(억원, 추정)'],['#fbbf24','추정 분기 프록시 · 보정 추정(점선·범위)'],['#4ade80','보고 영업이익(연결, 억원)']].forEach(function(p){var s=document.createElement('span');var i=document.createElement('i');i.style.background=p[0];s.appendChild(i);s.appendChild(document.createTextNode(' '+p[1]));lg.appendChild(s);});
    box.appendChild(lg);
    svg.addEventListener('mousemove',function(ev){var rect=svg.getBoundingClientRect();var px=(ev.clientX-rect.left)*W/rect.width;var i=Math.min(n-1,Math.max(0,Math.floor((px-L)/(W-L-R)*n)));var r=rows[i];
      var lines=[{label:r.q+' ('+r.status+')',value:''},{label:'프록시',value:fmt(r.proxy)+' 억원',color:'#3987e5'}];
      if(fin(r.op))lines.push({label:'보고 영업이익',value:fmt(r.op)+' 억원',color:'#4ade80'}); if(fin(r.fit))lines.push({label:'보정 추정',value:fmt(r.fit)+(fin(r.lo)?' ('+fmt(r.lo)+'~'+fmt(r.hi)+')':''),color:'#fbbf24'});
      if(window.KSTIP)window.KSTIP.show(ev.clientX,ev.clientY,lines);});
    svg.addEventListener('mouseleave',function(){if(window.KSTIP)window.KSTIP.hide();});
  }
  function boot(){document.querySelectorAll('.kchart-box[data-rows]').forEach(draw);}
  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',boot);}else{boot();}
})();
"""


HUB_MIN_CHANGE_TON = 5000.0     # 허브 "최근 변동" 은 5 kt 미만(CNT 0.2→0.4 kt 같은 소규모)을 생략 — 변동 페이지는 전부

def est_chip(txt="추정"):
    return '<span class="est">%s</span>' % E(txt)


def kind_chip(kind):
    return '<span class="kind %s">%s</span>' % (E(kind), E(kind))


def load_events(stock):
    p = os.path.join(ASSETS, "events", "%s.json" % stock)
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("events") or []


def cov_bar(pct):
    if pct is None:
        return "—"
    return '<span class="cov"><b style="width:%d%%"></b></span> <span class="mono">%s%%</span>' % (max(0, min(100, round(pct))), fmt(pct, 1))


# ── 허브 ───────────────────────────────────────────────────

def index_html(uni, ledger, model, events_by_stock):
    s = model["summary"]
    n_cand = sum(1 for r in uni["rows"] if not r["excluded"])
    body = ('<div class="kpi">'
            '<div><b>%d</b><span>후보(KIND 업종·어휘·시드) · 제외 %d</span></div>'
            '<div><b>%d</b><span>정기보고서 수집(생산설비 절)</span></div>'
            '<div><b>%d</b><span>편입 — 톤 단위 생산능력이 스프레드에 매핑됨</span></div>'
            '<div><b>%s<small>kt</small></b><span>매핑된 연간 생산능력 · 미매핑 %s kt</span></div>'
            '<div><b>%d</b><span>캐파 변동(연간 열 비교, ±5%%↑) · 이벤트 공시 %d</span></div>'
            '<div><b>%d</b><span>보정된 회사(보고 영업이익 ≥4분기) · 다음 분기 추정 %d</span></div>'
            '</div>' % (n_cand, uni["n_excluded"], ledger["n_companies"], s["promoted"], fmt(s["mapped_capacity_ton"] / 1000),
                        fmt(s["unmapped_capacity_ton"] / 1000), ledger["n_changes"], sum(len(v) for v in events_by_stock.values()), s["with_fit"], s["with_estimate"]))
    body += ('<div class="notice info"><div class="sym">ℹ</div><div><p>생산능력·생산실적·가동률은 DART 정기보고서 「원재료 및 생산설비」 절의 표를 그대로 읽은 값입니다(연환산 근거는 행마다 표시). '
             '제품→스프레드 연결과 바스켓 구성비, 가동률 폴백, 보정 계수는 전부 <b>추정</b>입니다. 스프레드 원장은 2026-08-24 이후 멈춰 있어 그 뒤 분기는 최근 13주 평균 가정입니다.</p></div></div>')
    # 회사 카드
    cards = []
    cos = sorted(model["companies"].items(), key=lambda x: -(x[1].get("mapped_capacity_ton") or 0))
    for st, c in cos:
        if not c["promoted"]:
            continue
        est = c["estimates"][0] if c["estimates"] else None
        fit = c.get("fit")
        toks = []
        for mp in c["mapped"]:
            for cc in mp["components"]:
                if cc["token"] not in toks:
                    toks.append(cc["token"])
        cards.append(
            '<a class="cardlink" href="%s/index.html"><div class="t"><b>%s</b><span class="code">%s</span></div>'
            '<p class="mut">%s</p>'
            '<div class="stat"><div><b>%s</b><span>매핑 캐파 kt/년</span></div><div><b>%s</b><span>커버리지</span></div>'
            '<div><b>%s</b><span>%s 프록시 억원</span></div><div><b>%s</b><span>보정 추정 억원%s</span></div></div>'
            '<div class="go">회사 →</div></a>'
            % (E(st), E(c["name"]), E(st), E(" · ".join(toks[:8])),
               fmt(c["mapped_capacity_ton"] / 1000), cov_bar(c.get("coverage_pct")),
               fmt(est["proxy_eok"]) if est else "—", E(est["q"]) if est else "다음 분기",
               (fmt(est.get("op_fit_eok")) if (est and est.get("op_fit_eok") is not None and c.get("fit_ok")) else "—"),
               (" (R² %s)" % fmt(fit["r2"], 2)) if (fit and c.get("fit_ok")) else (" (보정 참고만)" if fit else " (보정 없음)")))
    body += '<h2 class="sec">편입 회사 %d<span>매핑된 생산능력 순 · 추정은 전부 참고용</span></h2><div class="cards">%s</div>' % (len(cards), "".join(cards))
    # 최근 변동·이벤트
    rows = []
    for st, meta in ledger["companies"].items():
        if not (model["companies"].get(st) or {}).get("promoted"):
            continue
        co = load_asset("capacity/%s.json" % st)
        for p in co["products"]:
            for ch in [c for c in p["changes"] if abs(c["to"] - c["from"]) >= HUB_MIN_CHANGE_TON][-2:]:
                rows.append((ch["to_year"], st, co["name"], p["product_raw"], p["entity"], ch))
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    trs = "".join('<tr><td class="l">%s→%s</td><td class="l"><a href="%s/index.html">%s</a></td><td class="l">%s <small class="mut">%s</small></td>'
                  '<td class="num">%s</td><td class="num">%s</td><td class="delta %s">%s%%</td><td>%s</td></tr>'
                  % (E(r[5]["from_year"]), E(r[5]["to_year"]), E(r[1]), E(r[2]), E(r[3]), E(r[4][:14]), fmt_kt(r[5]["from"]), fmt_kt(r[5]["to"]),
                     "up" if r[5]["pct"] > 0 else "dn", fmt(r[5]["pct"], 1), kind_chip(r[5]["kind"])) for r in rows[:25])
    body += ('<h2 class="sec">최근 캐파 변동 <span>연간 생산능력 열 비교(±5%% 이상) · 전체는 변동·이벤트 페이지</span></h2>'
             '<div class="wrap"><table data-sortable><thead><tr><th class="l">연도</th><th class="l">회사</th><th class="l">품목</th><th>전(kt)</th><th>후(kt)</th><th>변화</th><th>구분</th></tr></thead><tbody>%s</tbody></table></div>' % trs)
    ev = []
    for st, evs in events_by_stock.items():
        for e in evs:
            ev.append((e.get("filed") or "", st, ledger["companies"].get(st, {}).get("name", st), e))
    ev.sort(key=lambda x: x[0], reverse=True)
    etrs = "".join('<tr><td class="l">%s</td><td class="l"><a href="%s/index.html">%s</a></td><td>%s%s</td><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td></tr>'
                   % (E(x[0]), E(x[1]), E(x[2]), kind_chip(x[3].get("type") or "?"), " <small class=\"mut\">자회사</small>" if x[3].get("subsidiary") else "",
                      E((x[3].get("fields") or {}).get("scope") or (x[3].get("fields") or {}).get("purpose") or ""),
                      E(str((x[3].get("fields") or {}).get("halt_date") or (x[3].get("fields") or {}).get("period_end") or "")),
                      E(str((x[3].get("fields") or {}).get("capa_text") or ""))) for x in ev[:20])
    body += ('<h2 class="sec">최근 이벤트 공시 <span>신규시설투자등·생산중단·영업정지(거래소 수시공시)</span></h2>'
             '<div class="wrap"><table data-sortable><thead><tr><th class="l">접수</th><th class="l">회사</th><th>유형</th><th class="l">대상</th><th class="l">일자</th><th class="l">캐파 언급</th></tr></thead><tbody>%s</tbody></table></div>'
             % (etrs or '<tr><td colspan="6" class="mut">수집된 이벤트 공시 없음</td></tr>'))
    body += '<script>%s</script>' % TABLE_JS
    return page("한국화학 캐파 — 생산능력·가동률·스프레드 매핑·다음 분기 추정", body, depth=0, h1="🏭 한국화학 캐파", nav=NAV,
                lead="국내 상장 화학사의 생산능력(톤/년)을 정기보고서에서 전수 수집하고, 품목을 ARGUS 스프레드에 연결해 분기 마진 프록시와 다음 분기 추정을 만듭니다. 캐파 증설·축소는 연간 열 비교와 수시공시로 자동 갱신됩니다.")


# ── 회사 ───────────────────────────────────────────────────

def company_html(stock, co, mc, events):
    name = co["name"]
    body = ""
    if mc.get("promoted"):
        est = mc["estimates"]
        fit = mc.get("fit")
        body += '<div class="kpi"><div><b>%s<small>kt</small></b><span>매핑된 연간 생산능력 · 커버리지 %s%%</span></div>' % (fmt(mc["mapped_capacity_ton"] / 1000), fmt(mc.get("coverage_pct"), 1))
        body += '<div><b>%s</b><span>스프레드 매핑 제품 · 미매핑 %d</span></div>' % (len(mc["mapped"]), len(mc["unmapped"]))
        body += '<div><b>%s</b><span>마지막 보고 분기(영업이익) · 보정 %s</span></div>' % (E(mc.get("last_fin_q") or "—"), ("n=%d R²=%s" % (fit["n"], fmt(fit["r2"], 2) if fit.get("r2") is not None else "-")) if fit else "없음")
        body += '<div><b>%d<small>주</small></b><span>스프레드 원장 정지(마지막 %s)</span></div></div>' % (mc.get("stale_weeks") or 0, E(mc.get("spread_last") or "—"))
        if est:
            e0 = est[0]
            body += ('<div class="estbox"><div><b class="big">%s</b> <span class="mut">억원 · %s 스프레드 마진 프록시</span> %s</div>'
                     % (fmt(e0["proxy_eok"]), E(e0["q"]), est_chip("추정")))
            if e0.get("op_fit_eok") is not None and mc.get("fit_ok"):
                body += '<div style="margin-top:6px"><b class="big">%s</b> <span class="mut">억원 · 보정 영업이익 추정</span> <span class="rng">범위 %s ~ %s (±1.64σ)</span></div>' % (fmt(e0["op_fit_eok"]), fmt(e0.get("op_fit_lo")), fmt(e0.get("op_fit_hi")))
            elif e0.get("op_fit_eok") is not None:
                body += '<div class="mut" style="margin-top:6px">보정 추정 %s 억원(범위 %s ~ %s)은 <b>참고만</b> — %s</div>' % (fmt(e0["op_fit_eok"]), fmt(e0.get("op_fit_lo")), fmt(e0.get("op_fit_hi")), E("; ".join((fit or {}).get("why") or [])))
            else:
                body += '<div class="mut" style="margin-top:6px">보고 영업이익과의 보정이 없어(분기 쌍 부족) 프록시 방향만 참고</div>'
            if len(est) > 1:
                body += '<div class="mut" style="margin-top:4px">그다음 분기 %s: 프록시 %s 억원%s</div>' % (E(est[1]["q"]), fmt(est[1]["proxy_eok"]), (" · 보정 %s" % fmt(est[1].get("op_fit_eok"))) if est[1].get("op_fit_eok") is not None else "")
            body += '<div class="mut" style="margin-top:6px">가정: %s</div></div>' % E(", ".join(e0["assumed"]) or "없음")
        if mc.get("caveats"):
            body += '<div class="notice"><div class="sym">⚠</div><div><p>%s</p></div></div>' % "<br>".join(E(c) for c in mc["caveats"])
        # 차트
        rows_js = [{"q": r["q"], "proxy": r["proxy_eok"], "op": r["op_eok"], "fit": r.get("op_fit_eok"), "lo": r.get("op_fit_lo"), "hi": r.get("op_fit_hi"), "status": r["status"]} for r in mc["quarters"]]
        body += '<h2 class="sec">분기 프록시 vs 보고 영업이익<span>프록시 = Σ 캐파/4 × 가동률 × 스프레드 × 환율 · 보정 = a + b×프록시</span></h2>'
        body += '<div class="kchart-box" data-rows="%s"></div>' % E(json.dumps(rows_js, ensure_ascii=False))
        # 분기 표
        qtrs = "".join('<tr><td class="l">%s</td><td class="l">%s</td><td class="num">%s</td><td class="num">%s</td><td class="num">%s</td><td class="l mut">%s</td></tr>'
                       % (E(r["q"]), E(r["status"]), fmt(r["proxy_eok"]), fmt(r["op_eok"]) if r["op_eok"] is not None else "—",
                          (fmt(r["op_fit_eok"]) + (" (%s~%s)" % (fmt(r.get("op_fit_lo")), fmt(r.get("op_fit_hi"))) if r.get("op_fit_lo") is not None else "")) if r.get("op_fit_eok") is not None else "—",
                          E(", ".join(r["assumed"]))) for r in mc["quarters"])
        body += ('<div class="wrap"><table data-sortable><thead><tr><th class="l">분기</th><th class="l">상태</th><th>프록시(억원)</th><th>보고 영업이익</th><th>보정 추정</th><th class="l">가정</th></tr></thead><tbody>%s</tbody></table></div>' % qtrs)
        # 매핑 표
        mrows = []
        for mp in mc["mapped"]:
            comps = "; ".join("%s×%s → %s" % (E(cc["token"]), fmt(cc["share"], 2), ", ".join('<a href="../kchem/connections.html#%s">%s</a>' % (E(s["sid"]), E(s["name"])) for s in cc["spreads"]) or "<i class=\"unmapped\">스프레드 없음</i>")
                              for cc in mp["components"])
            lu = mp["util"].get(mc["last_fin_q"]) if mc.get("last_fin_q") else None
            mrows.append('<tr><td class="l">%s <small class="mut">%s</small></td><td class="num">%s</td><td class="l mut">%s</td><td class="num">%s</td><td class="l">%s</td></tr>'
                         % (E(mp["product_raw"]), E(mp["entity"][:14]), fmt_kt(mp["capacity_ton_annual"]), E(mp["basis"][:28]),
                            (fmt(lu[0], 1) + "%" + " <small class=\"mut\">" + E(lu[1]) + "</small>") if lu else "—", comps))
        for u in mc["unmapped"]:
            mrows.append('<tr><td class="l unmapped">%s <small>%s</small></td><td class="num">%s</td><td class="l mut">%s</td><td class="num">—</td><td class="l unmapped">%s</td></tr>'
                         % (E(u["product_raw"]), E(u["entity"][:14]), fmt_kt(u["capacity_ton_annual"]), "비화학(커버리지 제외)" if u.get("non_product") else "미매핑",
                            E(u.get("note") or ("유틸리티·비화학 품목" if u.get("non_product") else "품목 사전에 없음 — product_map.json"))))
        body += ('<h2 class="sec">제품 → 스프레드 매핑<span>구성비·바스켓은 추정(product_map.json)</span></h2>'
                 '<div class="wrap"><table data-sortable><thead><tr><th class="l">품목(회사)</th><th>캐파 kt/년</th><th class="l">연환산 근거</th><th>가동률(마지막 보고 분기)</th><th class="l">스프레드</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(mrows))
    else:
        body += '<div class="notice"><div class="sym">⛔</div><div><p><b>미편입</b> — %s. 아래 원문 표 값은 그대로 보입니다.</p></div></div>' % E(mc.get("why") or "스프레드 매핑 불가")
    # 생산능력 이력 표(전 제품)
    years = sorted({y for p in co["products"] for y in p["annual"]}, key=int)
    yrs_h = "".join("<th>%s</th>" % E(y) for y in years)
    prows = []
    for p in co["products"]:
        if not p["is_ton"]:
            continue
        cells = "".join('<td class="num">%s</td>' % (fmt_kt(p["annual"][y]) if y in p["annual"] else "·") for y in years)
        lat = p.get("latest") or {}
        ch = "".join('<span class="delta %s">%s→%s %s%%</span> ' % ("up" if c["pct"] > 0 else "dn", E(c["from_year"][2:]), E(c["to_year"][2:]), fmt(c["pct"], 1)) for c in p["changes"])
        lva = p.get("latest_vs_annual")
        if lva:
            ch += '<span class="est" title="%s">%s 연환산 %s%% vs %s</span>' % (E(lva["note"]), E(lva["est_year"]), fmt(lva["pct"], 1), E(lva["annual_year"]))
        prows.append('<tr><td class="l">%s <small class="mut">%s%s</small></td>%s<td class="num">%s</td><td class="num">%s</td><td class="l mut">%s</td><td class="l">%s</td></tr>'
                     % (E(p["product_raw"]), E(p["entity"][:14]), (" · " + E(p["site"][:8])) if p["site"] else "", cells,
                        fmt_kt(lat.get("capacity_ton_annual")), (fmt(lat.get("util_pct"), 1) + "%") if lat.get("util_pct") is not None else "—",
                        E((lat.get("basis") or "")[:30]), ch or "—"))
    body += ('<h2 class="sec">생산능력 이력 <span>연간 열(kt/년) · 마지막 열은 최신 보고서 당기(연환산)·가동률</span></h2>'
             '<div class="wrap tall"><table data-sortable><thead><tr><th class="l">품목</th>%s<th>최신 연환산</th><th>가동률</th><th class="l">근거</th><th class="l">변동</th></tr></thead><tbody>%s</tbody></table></div>' % (yrs_h, "".join(prows)))
    # 이벤트
    if events:
        etr = "".join('<tr><td class="l">%s</td><td>%s%s</td><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td><td class="l"><a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=%s" target="_blank" rel="noopener noreferrer">원문</a></td></tr>'
                      % (E(e.get("filed") or ""), kind_chip(e.get("type") or "?"), " <small class=\"mut\">자회사 %s</small>" % E(e.get("subsidiary_name") or "") if e.get("subsidiary") else "",
                         E((e.get("fields") or {}).get("scope") or (e.get("fields") or {}).get("purpose") or ""), E(str((e.get("fields") or {}).get("halt_date") or (e.get("fields") or {}).get("period_end") or "")),
                         E(str((e.get("fields") or {}).get("restart_date") or "")), E(str((e.get("fields") or {}).get("capa_text") or "")), E(e.get("rcp") or "")) for e in sorted(events, key=lambda e: e.get("filed") or "", reverse=True))
        body += ('<h2 class="sec">이벤트 공시 <span>신규시설투자등·생산중단·영업정지 — 정정은 뒤 접수가 앞을 덮음</span></h2>'
                 '<div class="wrap"><table data-sortable><thead><tr><th class="l">접수</th><th>유형</th><th class="l">대상·목적</th><th class="l">일자</th><th class="l">재개 예정</th><th class="l">캐파 언급</th><th class="l">원문</th></tr></thead><tbody>%s</tbody></table></div>' % etr)
    # 보고서 목록
    rep = "".join('<tr><td class="l">%s</td><td class="l">%s</td><td class="l"><a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=%s" target="_blank" rel="noopener noreferrer">%s</a></td><td class="num">%s</td><td class="num">%s</td><td class="l mut">%s</td></tr>'
                  % (E(q), E(v.get("node") or ""), E(v.get("rcp") or ""), E(v.get("title") or v.get("rcp") or ""), v.get("tables", "-"), v.get("n_ton", "-"), E(v.get("error") or "")) for q, v in sorted(co["reports"].items()))
    body += ('<h2 class="sec">읽은 보고서 <span>DART 정기보고서 「원재료 및 생산설비」 절</span></h2>'
             '<div class="wrap"><table><thead><tr><th class="l">분기</th><th class="l">절</th><th class="l">보고서</th><th>표</th><th>톤 제품</th><th class="l">오류</th></tr></thead><tbody>%s</tbody></table></div>' % rep)
    body += '<script>%s</script><script>%s</script>' % (TABLE_JS, CHART_JS)
    return page("%s — 생산능력·스프레드·추정" % name, body, depth=1, h1=name, tags=(stock,),
                nav=(("← 한국화학 캐파", "../index.html"), ("제품", "../products.html"), ("변동", "../changes.html")),
                crumbs=(("한국화학 캐파", "../index.html"), (name, "")),
                lead="정기보고서 생산능력(톤/년)·가동률 이력, 품목→스프레드 매핑, 분기 마진 프록시와 보고 영업이익 보정, 다음 분기 추정.")


# ── 제품 ───────────────────────────────────────────────────

def products_html(model, ledger):
    by_tok = {}
    for st, c in model["companies"].items():
        if not c["promoted"]:
            continue
        for mp in c["mapped"]:
            for cc in mp["components"]:
                row = by_tok.setdefault(cc["token"], {"companies": [], "spreads": {}})
                row["companies"].append((st, c["name"], mp["product_raw"], mp["entity"], mp["capacity_ton_annual"] * cc["share"], cc["share"]))
                for s in cc["spreads"]:
                    row["spreads"][s["sid"]] = s
    sections = []
    for tok in sorted(by_tok, key=lambda t: -sum(x[4] for x in by_tok[t]["companies"])):
        r = by_tok[tok]
        total = sum(x[4] for x in r["companies"])
        trs = "".join('<tr><td class="l"><a href="%s/index.html">%s</a></td><td class="l">%s <small class="mut">%s</small></td><td class="num">%s</td><td class="num">%s</td><td class="bar-h%s"><i style="width:%d%%"></i></td></tr>'
                      % (E(x[0]), E(x[1]), E(x[2]), E(x[3][:12]), fmt_kt(x[4]), fmt(x[5], 2), " est" if x[5] < 1 else "", max(2, round(100 * x[4] / total)) if total else 0)
                      for x in sorted(r["companies"], key=lambda x: -x[4]))
        sp = ", ".join('<a href="../kchem/connections.html#%s">%s</a>%s' % (E(sid), E(s["name"]), "" if s.get("reproduced") else " " + est_chip("미재현")) for sid, s in r["spreads"].items()) or '<i class="unmapped">스프레드 없음</i>'
        sections.append('<section class="card"><h2>%s <em>%s kt/년 · %d사</em></h2><p class="note">스프레드: %s</p>'
                        '<div class="wrap"><table><thead><tr><th class="l">회사</th><th class="l">품목(원문)</th><th>귀속 캐파 kt</th><th>구성비</th><th class="l">비중</th></tr></thead><tbody>%s</tbody></table></div></section>'
                        % (E(tok), fmt(total / 1000), len({x[0] for x in r["companies"]}), sp, trs))
    body = ('<div class="notice info"><div class="sym">ℹ</div><div><p>제품 토큰은 kchem 스프레드 레지스트리의 제품명입니다. 귀속 캐파 = 회사 생산능력 × 바스켓 구성비(추정). '
            '같은 톤이 여러 제품에 나뉘어 보일 수 있고(NC → 에틸렌·프로필렌), 종속회사 캐파가 모회사 보고서에도 실려 중복될 수 있습니다(롯데정밀화학 가성소다).</p></div></div>')
    body += "".join(sections)
    body += '<script>%s</script>' % TABLE_JS
    return page("한국화학 캐파 — 제품별", body, depth=0, h1="제품 → 회사 → 스프레드", nav=NAV, crumbs=(("한국화학 캐파", "index.html"), ("제품", "")),
                lead="스프레드 제품 토큰별로 누가 얼마나 만드는지, 어느 스프레드에 연결되는지.")


# ── 변동·이벤트 ─────────────────────────────────────────────

def changes_html(ledger, events_by_stock):
    rows = []
    lva = []
    for st, meta in ledger["companies"].items():
        co = load_asset("capacity/%s.json" % st)
        for p in co["products"]:
            for ch in p["changes"]:
                rows.append((st, co["name"], p, ch))
            if p.get("latest_vs_annual"):
                lva.append((st, co["name"], p, p["latest_vs_annual"]))
    rows.sort(key=lambda r: (r[3]["to_year"], r[0]), reverse=True)
    trs = "".join('<tr><td class="l">%s→%s</td><td class="l"><a href="%s/index.html">%s</a></td><td class="l">%s <small class="mut">%s</small></td><td class="num">%s</td><td class="num">%s</td><td class="delta %s">%s%%</td><td>%s</td><td class="l mut">%s</td></tr>'
                  % (E(ch["from_year"]), E(ch["to_year"]), E(st), E(nm), E(p["product_raw"]), E(p["entity"][:14]), fmt_kt(ch["from"]), fmt_kt(ch["to"]),
                     "up" if ch["pct"] > 0 else "dn", fmt(ch["pct"], 1), kind_chip(ch["kind"]), E(" / ".join(x or "" for x in ch["src"])[:80])) for st, nm, p, ch in rows)
    body = ('<h2 class="sec">연간 생산능력 변동 %d<span>연간 열끼리 비교 · ±5%% 이상 · 원문 두 값 그대로</span></h2>'
            '<div class="wrap tall"><table data-sortable><thead><tr><th class="l">연도</th><th class="l">회사</th><th class="l">품목</th><th>전 kt</th><th>후 kt</th><th>변화</th><th>구분</th><th class="l">근거</th></tr></thead><tbody>%s</tbody></table></div>' % (len(rows), trs))
    ltrs = "".join('<tr><td class="l"><a href="%s/index.html">%s</a></td><td class="l">%s <small class="mut">%s</small></td><td class="l">%s</td><td class="num">%s</td><td class="l">%s</td><td class="num">%s</td><td class="delta %s">%s%%</td></tr>'
                   % (E(st), E(nm), E(p["product_raw"]), E(p["entity"][:14]), E(x["annual_year"]), fmt_kt(x["annual"]), E(x["est_year"]), fmt_kt(x["est"]), "up" if x["pct"] > 0 else "dn", fmt(x["pct"], 1))
                   for st, nm, p, x in sorted(lva, key=lambda r: -abs(r[3]["pct"])))
    body += ('<h2 class="sec">올해 연환산 vs 마지막 연간 열 %d<span>%s</span></h2>'
             '<div class="wrap tall"><table data-sortable><thead><tr><th class="l">회사</th><th class="l">품목</th><th class="l">연간</th><th>kt</th><th class="l">연환산</th><th>kt</th><th>차이</th></tr></thead><tbody>%s</tbody></table></div>'
             % (len(lva), E("기간 비례 추정이라 신뢰 낮음 — 분기 보고서의 일수 비례·정기보수 반영 가능성, 사업보고서로 확인 전까지 참고"), ltrs))
    ev = []
    for st, evs in events_by_stock.items():
        for e in evs:
            ev.append((e.get("filed") or "", st, ledger["companies"].get(st, {}).get("name", st), e))
    ev.sort(key=lambda x: x[0], reverse=True)
    etrs = "".join('<tr><td class="l">%s</td><td class="l"><a href="%s/index.html">%s</a></td><td>%s%s</td><td class="l">%s</td><td class="num">%s</td><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td><td class="l"><a href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=%s" target="_blank" rel="noopener noreferrer">원문</a></td></tr>'
                   % (E(x[0]), E(x[1]), E(x[2]), kind_chip(x[3].get("type") or "?"), " <small class=\"mut\">자회사</small>" if x[3].get("subsidiary") else "",
                      E((x[3].get("fields") or {}).get("scope") or (x[3].get("fields") or {}).get("purpose") or ""),
                      fmt(((x[3].get("fields") or {}).get("amount_krw") or 0) / 1e8) if (x[3].get("fields") or {}).get("amount_krw") else "—",
                      E(str((x[3].get("fields") or {}).get("halt_date") or (x[3].get("fields") or {}).get("period_end") or "")),
                      E(str((x[3].get("fields") or {}).get("restart_date") or "")), E(str((x[3].get("fields") or {}).get("capa_text") or "")), E(x[3].get("rcp") or "")) for x in ev)
    body += ('<h2 class="sec">이벤트 공시 %d<span>신규시설투자등 · 생산중단 · 영업정지 · 생산재개 · 유형자산 양도</span></h2>'
             '<div class="wrap tall"><table data-sortable><thead><tr><th class="l">접수</th><th class="l">회사</th><th>유형</th><th class="l">대상·목적</th><th>금액 억원</th><th class="l">일자</th><th class="l">재개 예정</th><th class="l">캐파 언급</th><th class="l">원문</th></tr></thead><tbody>%s</tbody></table></div>'
             % (len(ev), etrs or '<tr><td colspan="9" class="mut">수집된 이벤트 공시 없음</td></tr>'))
    body += '<script>%s</script>' % TABLE_JS
    return page("한국화학 캐파 — 변동·이벤트", body, depth=0, h1="캐파 변동 · 이벤트", nav=NAV, crumbs=(("한국화학 캐파", "index.html"), ("변동·이벤트", "")),
                lead="연간 생산능력 열 비교로 잡은 증설·축소와, 거래소 수시공시(신규시설투자등·생산중단·영업정지)로 잡은 이벤트. 매일 재수집되어 자동 갱신됩니다.")


# ── 커버리지 ─────────────────────────────────────────────────

def coverage_html(uni, ledger, model):
    trs = []
    for r in sorted(uni["rows"], key=lambda r: (r["excluded"] is not None, r["stock"] not in model["companies"], r["name"])):
        st = r["stock"]
        mc = model["companies"].get(st)
        led = ledger["companies"].get(st)
        if r["excluded"]:
            status, why = "제외", r["excluded"]
        elif not led:
            status, why = "미수집", "정기보고서 없음 또는 생산설비 절 없음"
        elif mc and mc["promoted"]:
            status, why = "편입", "톤 제품 %d · 커버리지 %s%%" % (len(mc["mapped"]), fmt(mc.get("coverage_pct"), 1))
        else:
            status, why = "검토·제외", (mc or {}).get("why") or ("톤 제품 %d" % led["n_ton_products"])
        trs.append('<tr><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td><td class="l mut">%s</td><td class="l mut">%s</td></tr>'
                   % (E(status), ('<a href="%s/index.html">%s</a>' % (E(st), E(r["name"]))) if led else E(r["name"]), E(st), E(r["industry"]), E(" ; ".join(r["why"])[:60]), E(why), E((r.get("product") or "")[:40])))
    body = ('<div class="kpi"><div><b>%d</b><span>KIND 상장사 전수</span></div><div><b>%d</b><span>후보(업종·어휘·시드)</span></div><div><b>%d</b><span>제외(어휘·사유 기록)</span></div>'
            '<div><b>%d</b><span>수집(생산설비 절)</span></div><div><b>%d</b><span>편입(스프레드 매핑)</span></div></div>' % (uni["n_kind"], uni["n_candidates"], uni["n_excluded"], ledger["n_companies"], model["summary"]["promoted"]))
    body += ('<p class="note">편입 = 정기보고서의 톤 단위 생산능력 중 하나 이상이 ARGUS 스프레드 제품에 매핑된 회사. 금액 기준(백만원)으로만 공시하는 회사(LG화학 석유화학·효성화학·코오롱인더)와 품목을 뭉뚱그린 회사(SK이노베이션 "화학제품", 태광 "석유화학제품")는 '
             '톤 분해가 원문에 없어 검토·제외 또는 부분 편입이며, 운영자가 근거를 적어 product_map.json 의 company_overrides 에 넣으면 추정으로 반영됩니다.</p>')
    body += ('<div class="ctl"><input data-filter="#cv" type="search" placeholder="회사·업종·상태 검색"></div><div class="wrap tall"><table id="cv" data-sortable><thead><tr><th class="l">상태</th><th class="l">회사</th><th class="l">코드</th><th class="l">업종</th><th class="l">후보 근거</th><th class="l">판정</th><th class="l">KIND 주요제품</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(trs))
    # 미매핑 품목 전수
    um = []
    for st, c in model["companies"].items():
        for u in c.get("unmapped", []):
            um.append((u["capacity_ton_annual"], st, c["name"], u))
    um.sort(key=lambda x: (-(x[0] or 0), x[1], x[3]["product_raw"]))
    utrs = "".join('<tr><td class="l"><a href="%s/index.html">%s</a></td><td class="l">%s <small class="mut">%s</small></td><td class="num">%s</td><td class="l mut">%s</td></tr>'
                   % (E(st), E(nm), E(u["product_raw"]), E(u["entity"][:14]), fmt_kt(cap), E(u.get("note") or "품목 사전에 없음")) for cap, st, nm, u in um)
    body += ('<h2 class="sec">미매핑 톤 품목 %d<span>캐파 큰 순 — 사전(product_map.json) 보강 대상</span></h2>'
             '<div class="wrap tall"><table data-sortable><thead><tr><th class="l">회사</th><th class="l">품목</th><th>kt/년</th><th class="l">사유</th></tr></thead><tbody>%s</tbody></table></div>' % (len(um), utrs))
    body += '<script>%s</script>' % TABLE_JS
    return page("한국화학 캐파 — 커버리지", body, depth=0, h1="커버리지", nav=NAV, crumbs=(("한국화학 캐파", "index.html"), ("커버리지", "")),
                lead="모집단 전수(후보·제외·수집·편입)와 그 근거, 미매핑 품목. 빠진 것도 이유와 함께 보입니다.")


# ── 빌드 ───────────────────────────────────────────────────

def build(write=True):
    uni = load_asset("universe.json")
    ledger = load_asset("ledger.json")
    model = load_asset("model.json")
    events_by_stock = {st: load_events(st) for st in ledger["companies"]}
    outputs = {
        os.path.join(KCAP, "index.html"): index_html(uni, ledger, model, events_by_stock),
        os.path.join(KCAP, "products.html"): products_html(model, ledger),
        os.path.join(KCAP, "changes.html"): changes_html(ledger, events_by_stock),
        os.path.join(KCAP, "coverage.html"): coverage_html(uni, ledger, model),
    }
    for st in ledger["companies"]:
        co = load_asset("capacity/%s.json" % st)
        mc = model["companies"].get(st) or {"promoted": False, "why": "모델 없음"}
        outputs[os.path.join(KCAP, st, "index.html")] = company_html(st, co, mc, events_by_stock.get(st, []))
    for path, text in outputs.items():
        if len(text.encode("utf-8")) > 5 * 1024 * 1024:
            raise RuntimeError("5MB 초과: %s" % path)
        if write:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            atomic_write(path, text)
    return outputs


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    out = build(write="--dry-run" not in argv)
    print("kcap pages %d%s" % (len(out), " (dry-run)" if "--dry-run" in argv else ""))


if __name__ == "__main__":
    main()
