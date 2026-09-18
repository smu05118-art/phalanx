#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kdef_page — 한국방산 탭의 페이지를 만든다.

  index.html            허브 — 체계업체 카드(잔고·커버리지·방산비중·수출비중) · 계통 구성 · 최근 대형 계약
  coverage.html         모집단 전수(네 겹)와 편입 근거 · ④ 본문 탐색 승격/제외
  <종목코드>/index.html  회사 — 잔고 추이/롤포워드 · 부문매출(방산·민수, 내수·수출) · 커버리지 ·
                        계약 목록(사업명·계통·유형·금액·기간·상대) · 계약유형 구성 ·
                        납품 관계(체계업체 ↔ 부품사, 근거 등급) · 원가·수익인식 각주

축이 조선과 다른 이유는 원문에 있다(FINDINGS):
  · 계약상대가 **공개**다 — 방위사업청·체계업체·해외 정부. 익명은 1건뿐이었다(조선은 81%).
  · 잔고표는 **보안 때문에 얇다** — 잔액 한 줄만 적는 회사가 있다. 그래서 1차 축은
    잔고 그 자체가 아니라 **커버리지(잔고 ÷ 연매출, 년)** 이고, 인도 스케줄은 계약 공시로 만든다.
  · 계약명에 **유형**(체계개발·최초양산·후속양산·성능개량·PBL)이 그대로 적힌다 — 이익 성격의 축.

    python3 kdef_page.py --all
"""
import argparse
import collections
import json
import os
import re
import sys

from kdef_lib import (E, KDEF, CHART_DEFAULTS_JS, TABLE_JS, atomic_write, fmt_eok,
                      fmt_x, json_for_html, load_asset, page, pct, slot_color)
from kdef_universe import load as load_universe
import kdef_contracts
import kdef_reports
import kdef_suppliers

DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=%s"
ROLE_KO = {"prime": "체계업체", "part": "부품", "material": "소재", "service": "용역", "holding": "지주"}
PARTY_KO = {"GOV": "방위사업청·정부기관", "PRIME": "체계업체", "G2G": "해외 정부(G2G·FMS)",
            "FOREIGN": "해외 기업", "DOMESTIC": "국내 기업", "ANON": "익명", "UNKNOWN": "미상"}


def load_all():
    uni = load_universe()
    doms = load_asset("domains.json")["domains"]
    ctypes = load_asset("contract_types.json")["types"]
    reports = kdef_reports.load()
    return {
        "uni": uni,
        "by_stock": {r["stock"]: r for r in uni},
        "doms": {d["id"]: d for d in doms},
        "dom_order": [d["id"] for d in doms],
        "ctypes": {c["id"]: c for c in ctypes},
        "ctype_order": [c["id"] for c in ctypes] + ["UNKNOWN"],
        "contracts": kdef_contracts.load(),
        "reports": reports.get("companies", {}),
        "quarters": reports.get("quarters", []),
        "sup": {c["stock"]: c for c in kdef_suppliers.load().get("cos", [])},
        "tax": load_asset("parts_taxonomy.json"),
        "probe": load_asset("universe_probe.json") if os.path.exists(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets",
                         "universe_probe.json")) else {},
    }


def dom_meta(data, did):
    d = data["doms"].get(did)
    if not d:
        return {"id": "UNKNOWN", "ko": "미상", "color": "#5d6675"}
    return {"id": d["id"], "ko": d["ko"], "color": slot_color(d["slot"])}


def ctype_meta(data, cid):
    c = data["ctypes"].get(cid)
    if not c:
        return {"id": "UNKNOWN", "ko": "미상", "color": "#5d6675"}
    return {"id": c["id"], "ko": c["ko"], "color": slot_color(c["slot"])}


# ── 회사 집계 ───────────────────────────────────────────────

def summary(stock, data):
    rec = data["by_stock"][stock]
    comp = data["reports"].get(stock) or {}
    qs = [q for q in sorted((comp.get("quarters") or {})) if comp["quarters"][q].get("ok")]
    latest = comp["quarters"][qs[-1]] if qs else None
    cons = [c for c in data["contracts"] if c["stock"] == stock]
    defc = [c for c in cons if not c["civil"]]
    backlog = latest.get("backlog") if latest else None
    fy = latest.get("revenue_fy") if latest else None
    cov = (backlog / fy) if (backlog and fy) else None
    dom_amt = collections.Counter()
    dom_n = collections.Counter()
    for c in cons:
        did = c["domain"] or "UNKNOWN"
        dom_amt[did] += (c["amt_krw_m"] or 0)
        dom_n[did] += 1
    ct_amt = collections.Counter()
    ct_n = collections.Counter()
    for c in defc:
        ct_amt[c["ctype"]] += (c["amt_krw_m"] or 0)
        ct_n[c["ctype"]] += 1
    exp = latest.get("revenue_export") if latest else None
    dom_rev = latest.get("revenue_domestic") if latest else None
    # 연결 모회사의 수주표에는 자회사 체계업체가 **행으로** 들어 있다(한화에어로의 수주표에
    # 한화시스템·한화오션 행이 있다). 잔고를 그냥 더하면 33조가 두 번 세어진다.
    kids = set()
    for seg in (latest or {}).get("segments") or []:
        for ps, pat in kdef_contracts.PRIME_NAMES.items():
            if ps != stock and re.search(pat, seg.get("label") or ""):
                kids.add(ps)
    return {
        "stock": stock, "rec": rec, "comp": comp, "qs": qs, "latest_q": qs[-1] if qs else None,
        "latest": latest, "contracts": cons, "def_contracts": defc,
        "backlog": backlog, "backlog_def": latest.get("backlog_def") if latest else None,
        "fy": fy, "coverage": cov,
        "def_share": pct(latest.get("sales_def"), latest.get("sales_all")) if latest else None,
        "exp_share": pct(exp, (exp or 0) + (dom_rev or 0)) if latest else None,
        "dom_amt": dom_amt, "dom_n": dom_n, "ct_amt": ct_amt, "ct_n": ct_n,
        "amt_total": sum(c["amt_krw_m"] or 0 for c in defc),
        "sup": data["sup"].get(stock) or {},
        "consolidates": sorted(kids),
        "security": bool(latest.get("security_note")) if latest else False,
    }


def has_page(s):
    """페이지를 만들 만한 회사인가 — 정기보고서 분기 기록이나 계약 공시가 있어야 한다."""
    return bool(s["qs"] or s["contracts"] or s["sup"].get("cats") or s["sup"].get("primes"))


# ── 조각 ───────────────────────────────────────────────────

def _chip(label, color=None, n=None, href=None, on=False, title=""):
    sw = '<i class="sw" style="background:%s"></i>' % E(color) if color else ""
    nn = ' <span class="n">%s</span>' % E(str(n)) if n is not None else ""
    inner = "%s%s%s" % (sw, E(label), nn)
    tt = ' title="%s"' % E(title) if title else ""
    if href:
        return '<a class="chip%s" href="%s"%s>%s</a>' % (" on" if on else "", E(href), tt, inner)
    return '<span class="chip%s"%s>%s</span>' % (" on" if on else "", tt, inner)


def _sw(color):
    return ('<i class="sw" style="display:inline-block;width:9px;height:9px;border-radius:3px;'
            'background:%s;margin-right:6px;vertical-align:-1px"></i>' % E(color))


def _grade_pill(p):
    cls = {1: "up", 2: "", 3: "mut", 4: "mut"}.get(p["grade"], "mut")
    return '<span class="pill %s" title="%s">%s</span>' % (cls, E(p.get("detail", "")), E(p["basis_ko"]))


def contracts_table(rows, data, tid="ct", show_company=False, by_stock=None, rel="../"):
    tr = []
    for c in sorted(rows, key=lambda c: (c["signed"] or c["start"] or ""), reverse=True):
        dm = dom_meta(data, c["domain"]) if c["domain"] else {"ko": "미상", "color": "#5d6675"}
        cm = ctype_meta(data, c["ctype"])
        amt = c["amt_krw_m"]
        who = ""
        if show_company:
            nm = (by_stock or {}).get(c["stock"], {}).get("name", c["stock"])
            who = '<td class="l"><a href="%s%s/index.html">%s</a></td>' % (rel, E(c["stock"]), E(nm))
        nm = (c["name"] or "").strip()
        if nm in ("", "-"):
            # 계약명이 비어 있는 건은 대개 **공시유보**다 — 빈칸이 아니라 유보라고 적는다.
            w = (c.get("withheld") or "").strip("- ")
            nm = ('<span class="pill">공시유보</span> %s%s'
                  % (E(w or "사유 미기재"),
                     (" · 기한 %s" % E(c["withheld_until"])) if (c.get("withheld_until") or "").strip("- ") else "")) \
                if (w or (c.get("withheld_until") or "").strip("- ")) else "—"
        else:
            nm = E(nm[:70])
        party = E(c["party"] or "—")
        if c["party_prime"]:
            party = '<a href="%s%s/index.html">%s</a>' % (rel, E(c["party_prime"]), party)
        tr.append(
            '<tr><td class="l">%s</td>%s<td class="l">%s%s</td><td class="l">%s</td>'
            '<td class="l">%s</td><td data-v="%.0f">%s</td><td data-v="%s">%s</td>'
            '<td class="l">%s<br><span class="mut">%s</span></td><td class="l mut">%s</td>'
            '<td class="l"><a href="%s" target="_blank" rel="noopener noreferrer">원문</a>%s</td></tr>'
            % (E(c["signed"] or c["start"] or "—"), who, _sw(dm["color"]), E(dm["ko"]),
               E(cm["ko"]), nm,
               (amt or 0), fmt_eok(amt), (c["years"] if c["years"] is not None else -1),
               fmt_x(c["years"]) if c["years"] is not None else "—",
               party, E(PARTY_KO.get(c["party_kind"], c["party_kind"]))
               + ((" · " + E(c["region"])) if (c.get("region") or "").strip("- ") else ""),
               E((c["start"] or "—") + " ~ " + (c["end"] or "—")),
               E(DART % c["rcp"]),
               ' <span class="pill">정정</span>' if c.get("corrected") else ""))
    head = ('<tr><th class="l">수주일</th>%s<th class="l">계통</th><th class="l">유형</th>'
            '<th class="l">사업명(체결계약명)</th><th>금액(억)</th><th>기간(년)</th>'
            '<th class="l">계약상대 · 공급지역</th><th class="l">계약기간</th><th class="l">출처</th></tr>'
            % ('<th class="l">회사</th>' if show_company else ""))
    return ('<div class="ctl"><input data-filter="#%s" type="search" placeholder="사업명·계통·유형·상대 검색"></div>'
            '<div class="wrap tall"><table id="%s" data-sortable><thead>%s</thead><tbody>%s</tbody></table></div>'
            % (tid, tid, head, "".join(tr)))


# ── 회사 페이지 ─────────────────────────────────────────────

def company_html(s, data):
    rec, latest = s["rec"], s["latest"]
    is_prime = rec["role"] == "prime"
    kpi = []
    if s["backlog"] is not None:
        kpi.append('<div class="hero"><b>%s<small>억</small></b><span>수주잔고 · 정기보고서 %s</span>%s</div>'
                   % (fmt_eok(s["backlog"]), E(s["latest_q"] or "—"),
                      '<i class="mut">방산분 %s억</i>' % fmt_eok(s["backlog_def"])
                      if s["backlog_def"] else ""))
    elif latest and latest.get("unit_note"):
        kpi.append('<div class="hero"><b class="mut">—</b><span>수주잔고</span><i class="dn">%s</i></div>'
                   % E(latest["unit_note"]))
    else:
        kpi.append('<div class="hero"><b class="mut">—</b><span>수주잔고</span>'
                   '<i class="mut">정기보고서 II-4 수주표를 찾지 못함</i></div>')
    if s["coverage"] is not None:
        kpi.append('<div><b>%s<small>년</small></b><span>잔고 커버리지 = 잔고 ÷ 연매출</span>'
                   '<i class="mut">분모 %s억(%s)</i></div>'
                   % (fmt_x(s["coverage"]), fmt_eok(s["fy"]),
                      E((latest or {}).get("revenue_fy_col") or "직전 사업연도")))
    else:
        kpi.append('<div><b class="mut">—</b><span>잔고 커버리지</span>'
                   '<i class="mut">잔고 또는 연매출 열을 못 읽음</i></div>')
    if s["def_share"] is not None:
        kpi.append('<div><b>%.0f<small>%%</small></b><span>방산 비중(부문매출)</span>'
                   '<i class="mut">%s 기준</i></div>'
                   % (s["def_share"], E({"revenue": "매출실적 부문×내수/수출",
                                         "segment_sales": "사업부문별 매출"}.get(
                       (latest or {}).get("sales_mix_src"), "부문표"))))
    if s["exp_share"] is not None:
        kpi.append('<div><b>%.0f<small>%%</small></b><span>수출 비중(내수/수출 표)</span></div>'
                   % s["exp_share"])
    kpi.append('<div><b>%d<small>건</small></b><span>방산 계약 공시 · %s억</span>'
               '<i class="mut">민수 %d건은 따로 셈</i></div>'
               % (len(s["def_contracts"]), fmt_eok(s["amt_total"]),
                  len(s["contracts"]) - len(s["def_contracts"])))

    # 잔고 롤포워드 표
    roll = []
    for q in s["qs"]:
        v = s["comp"]["quarters"][q]
        note = v.get("unit_note") or ""
        shape_ko = {"roll": "기초+신규−기납품", "openclose": "기초·기말만(보안)",
                    "gross": "총액−기납품", "item": "품목별", "balance": "잔액 한 줄(보안)"}.get(
            v.get("shape"), v.get("shape") or "—")
        roll.append('<tr><td class="l">%s</td><td>%s</td><td>%s</td><td>%s</td><td><b>%s</b></td>'
                    '<td class="l mut">%s</td><td class="l mut">%s</td>'
                    '<td class="l"><a href="%s" target="_blank" rel="noopener noreferrer">원문</a></td></tr>'
                    % (E(q), fmt_eok(v.get("opening")), fmt_eok(v.get("gross")),
                       fmt_eok(v.get("delivered")), fmt_eok(v.get("backlog")),
                       E(shape_ko), E(note), E(DART % (v.get("rcp") or ""))))
    roll_html = ('<div class="wrap"><table><thead><tr><th class="l">분기</th><th>기초</th>'
                 '<th>수주총액</th><th>기납품액</th><th>수주잔고</th><th class="l">표 모양</th>'
                 '<th class="l">비고</th><th class="l">출처</th></tr></thead><tbody>%s</tbody></table></div>'
                 % "".join(roll)) if roll else \
        '<p class="mut">이 회사의 정기보고서에서 수주표를 찾지 못했습니다.</p>'

    # 부문 매출
    seg_html = ""
    if latest and (latest.get("revenue_segments") or latest.get("sales_segments")):
        rows = []
        for r in latest.get("revenue_segments") or []:
            k = {"def": "방산", "civil": "민수", "mixed": "혼재"}.get(r["segkind"], "미판정")
            rows.append('<tr><td class="l">%s</td><td class="l mut">%s</td><td class="l">%s</td>'
                        '<td class="l">%s</td><td data-v="%.0f">%s</td></tr>'
                        % (E(r["seg"] or "(부문 표기 없음)"), E((r["item"] or "")[:40]), E(k), E(r["kind"]),
                           r["val"] or 0, fmt_eok(r["val"])))
        for r in latest.get("sales_segments") or []:
            k = {"def": "방산", "civil": "민수", "mixed": "혼재"}.get(r["segkind"], "미판정")
            rows.append('<tr><td class="l">%s</td><td class="l mut">%s</td><td class="l">%s</td>'
                        '<td class="l">%s</td><td data-v="%.0f">%s</td></tr>'
                        % (E(r["seg"] or "(부문 표기 없음)"), E((r["item"] or "")[:40]), E(k),
                           ("비중 %.1f%%" % r["pct"]) if r.get("pct") else "—",
                           r["val"] or 0, fmt_eok(r["val"])))
        seg_html = ('<section class="card"><h2>부문 매출 <em>%s · 억원 · 부문 이름은 원문 그대로, '
                    '방산/민수 판정은 이름에서 — 한쪽으로 못 가르면 <b>혼재</b></em></h2>'
                    '<div class="wrap"><table data-sortable><thead><tr><th class="l">부문(원문)</th>'
                    '<th class="l">품목</th><th class="l">판정</th><th class="l">구분</th>'
                    '<th>금액(억)</th></tr></thead><tbody>%s</tbody></table></div></section>'
                    % (E(s["latest_q"] or ""), "".join(rows)))

    # 계통·유형 구성
    dom_rows = [(d, s["dom_amt"][d], s["dom_n"][d]) for d in data["dom_order"] + ["UNKNOWN"]
                if s["dom_n"].get(d)]
    ct_rows = [(c, s["ct_amt"][c], s["ct_n"][c]) for c in data["ctype_order"] if s["ct_n"].get(c)]

    # 납품 관계
    sup = s["sup"]
    rel_html = ""
    if is_prime:
        rows = []
        for st, co in sorted(data["sup"].items(), key=lambda kv: kv[1]["nm"]):
            hit = [p for p in co["primes"] if p["stock"] == s["stock"]]
            if not hit:
                continue
            p = hit[0]
            cats = [h for h in co["cats"]]
            rows.append('<tr><td class="l"><a href="../%s/index.html">%s</a></td>'
                        '<td class="l">%s</td><td class="l">%s</td><td class="l mut">%s</td>'
                        '<td class="l mut">%s</td></tr>'
                        % (E(st), E(co["nm"]),
                           " ".join(_chip(cat_ko(data, h["cat"]), None) for h in cats[:5]) or "—",
                           _grade_pill(p), E(p.get("detail", "")), E(co["prod_raw"][:60])))
        if rows:
            rel_html = ('<section class="card"><h2>이 체계업체에 납품하는 상장사 <em>근거 등급: '
                        '주요고객 주석 &gt; 계약공시 상대 &gt; 본문 언급</em></h2><div class="wrap">'
                        '<table data-sortable><thead><tr><th class="l">회사</th><th class="l">부품</th>'
                        '<th class="l">근거</th><th class="l">근거 내용</th><th class="l">주요제품(KIND)</th>'
                        '</tr></thead><tbody>%s</tbody></table></div></section>' % "".join(rows))
    elif sup.get("primes"):
        rows = "".join('<tr><td class="l"><a href="../%s/index.html">%s</a></td><td class="l">%s</td>'
                       '<td class="l mut">%s</td></tr>'
                       % (E(p["stock"]), E(p["nm"]), _grade_pill(p), E(p.get("detail", "")))
                       for p in sup["primes"])
        rel_html = ('<section class="card"><h2>납품처(체계업체) <em>근거 등급과 근거 문장을 함께 싣습니다</em></h2>'
                    '<div class="wrap"><table><thead><tr><th class="l">체계업체</th><th class="l">근거</th>'
                    '<th class="l">내용</th></tr></thead><tbody>%s</tbody></table></div></section>' % rows)

    parts_html = ""
    if sup.get("cats"):
        chips = " ".join(_chip(cat_ko(data, h["cat"]), None, href="../parts.html#" + h["cat"],
                               title="근거: %s 「%s」" % ({"contract": "계약명", "report": "정기보고서 제품 절",
                                                        "body": "II절 본문",
                                                        "kind": "KIND 주요제품"}.get(h["src"], h["src"]),
                                                       h["kw"]))
                         for h in sup["cats"])
        parts_html = ('<section class="card"><h2>부품 분류 <em>계약명·정기보고서 본문·KIND 주요제품 문구에서 '
                      '읽은 낱말 — 칩에 근거가 붙어 있습니다</em></h2><div class="chips">%s</div></section>'
                      % chips)

    # 각주
    notes = []
    if s["security"]:
        notes.append("이 회사는 정기보고서에 <b>보안 관계상 수주 상세를 생략한다</b>고 적었습니다 — "
                     "잔고는 요약치(잔액·기말)만 공시됩니다.")
    if any(c["def_payrule"] for c in s["def_contracts"]):
        notes.append("계약 공시의 대금지급 조건에 <b>방위사업청 원가·대가 규정</b>이 언급된 계약이 있습니다 — "
                     "내수 방산은 원가기반 계약이라 이익률이 규정으로 제한됩니다(수치는 공시되지 않습니다).")
    notes.append("방산 계약은 <b>진행기준</b> 수익인식이 많아 수주·인도·매출 시점이 다릅니다. "
                 "잔고 커버리지는 '몇 년치 일감'을 보는 값이지 연도별 매출 예측이 아닙니다.")

    chart = {
        "roll": [{"q": q, "backlog": s["comp"]["quarters"][q].get("backlog"),
                  "def": s["comp"]["quarters"][q].get("backlog_def")} for q in s["qs"]],
        "doms": [{"ko": dom_meta(data, d)["ko"], "color": dom_meta(data, d)["color"],
                  "amt": a, "n": n} for d, a, n in dom_rows],
        "ctypes": [{"ko": ctype_meta(data, c)["ko"], "color": ctype_meta(data, c)["color"],
                    "amt": a, "n": n} for c, a, n in ct_rows],
    }
    body = """
<div class="kpi">%s</div>
<div class="grid2" style="margin-top:20px">
 <section class="card" style="margin-top:0"><h2>수주잔고 추이 <em>정기보고서 II-4 · 억원</em></h2>
  <div class="chart"><canvas id="cRoll"></canvas></div></section>
 <section class="card" style="margin-top:0"><h2>계통 구성 <em>계약 공시 금액 기준 · 억원</em></h2>
  <div class="chart"><canvas id="cDom"></canvas></div></section>
</div>
<section class="card"><h2>수주 롤포워드 <em>회사마다 표 모양이 다릅니다 — 원문 모양을 같이 적습니다</em></h2>%s</section>
%s
<div class="grid2">
 <section class="card"><h2>계약 유형 구성 <em>계약명에서 읽은 유형 · 이익 성격이 다릅니다</em></h2>
  <div class="chart"><canvas id="cType"></canvas></div>
  <p class="mut" style="font-size:12px;margin-top:10px">탐색·체계개발은 원가보상 성격, 최초양산은 초기 원가,
   후속양산은 원가절감분이 이익, 성능개량·후속군수지원(PBL)은 장기 매출입니다. 계약명에서 못 읽으면 '미상'입니다.</p></section>
 <section class="card"><h2>계약 상대 <em>방산은 상대가 공개입니다</em></h2>%s</section>
</div>
<section class="card"><h2>계약 공시 <em>단일판매ㆍ공급계약체결 · 방산 %d건 · 민수 %d건(계통 CIVIL 로 갈라 집계에서 뺐습니다)</em></h2>%s</section>
%s
%s
<div class="note info">%s</div>
<script>const DATA=%s;</script>
<script>%s</script>
<script>
(function(){
  if(DATA.roll.length){
    new Chart(document.getElementById('cRoll'),{type:'line',data:{labels:DATA.roll.map(function(r){return r.q}),
      datasets:[{label:'수주잔고(억)',data:DATA.roll.map(function(r){return r.backlog==null?null:Math.round(r.backlog/100)}),
        borderColor:'#3987e5',backgroundColor:'rgba(57,135,229,.18)',fill:true,tension:.25,spanGaps:true},
       {label:'방산분(억)',data:DATA.roll.map(function(r){return r.def==null?null:Math.round(r.def/100)}),
        borderColor:'#c98500',backgroundColor:'rgba(201,133,0,.14)',fill:true,tension:.25,spanGaps:true}]},
      options:{scales:{y:{ticks:{callback:function(v){return v.toLocaleString()}}},x:{grid:{display:false}}}}});
  }
  if(DATA.doms.length){
    new Chart(document.getElementById('cDom'),{type:'bar',data:{labels:DATA.doms.map(function(d){return d.ko}),
      datasets:[{label:'계약금액(억)',data:DATA.doms.map(function(d){return Math.round(d.amt/100)}),
        backgroundColor:DATA.doms.map(function(d){return d.color})}]},
      options:{indexAxis:'y',plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){
        var d=DATA.doms[c.dataIndex];return (c.parsed.x||0).toLocaleString()+'억 · '+d.n+'건'}}}},
        scales:{x:{ticks:{callback:function(v){return v.toLocaleString()}}},y:{grid:{display:false}}}}});
  }
  if(DATA.ctypes.length){
    new Chart(document.getElementById('cType'),{type:'doughnut',data:{labels:DATA.ctypes.map(function(d){return d.ko}),
      datasets:[{data:DATA.ctypes.map(function(d){return Math.round(d.amt/100)}),
        backgroundColor:DATA.ctypes.map(function(d){return d.color})}]},
      options:{plugins:{tooltip:{callbacks:{label:function(c){var d=DATA.ctypes[c.dataIndex];
        return d.ko+': '+(c.parsed||0).toLocaleString()+'억 · '+d.n+'건'}}}}}});
  }
})();
</script>
<script>%s</script>
""" % ("".join(kpi), roll_html, seg_html, party_html(s), len(s["def_contracts"]),
       len(s["contracts"]) - len(s["def_contracts"]),
       contracts_table(s["contracts"], data, tid="ct%s" % s["stock"]),
       parts_html, rel_html,
       " ".join("<p>%s</p>" % n for n in notes),
       json_for_html(chart), CHART_DEFAULTS_JS, TABLE_JS)
    tags = (rec["stock"], rec["market"], ROLE_KO.get(rec["role"], rec["role"]), rec["industry"])
    dart = DART % (latest.get("rcp") if latest and latest.get("rcp") else "")
    return page("%s — 방산 수주" % rec["name"], body, depth=1, h1=rec["name"], tags=tags,
                nav=(("허브", "../index.html"), ("인포그래픽", "../parts.html"),
                     ("커버리지", "../coverage.html"),
                     ("DART 원문 ↗", dart if latest else "https://dart.fss.or.kr")),
                crumbs=(("ARGUS", "../../index.html"), ("한국방산", "../index.html"),
                        (rec["name"], None)),
                scripts=("../vendor/chart.umd.min.js",),
                lead="수주잔고·부문매출은 정기보고서 II-4에서, 사업 단위 계약(사업명·계통·유형·금액·기간·상대)은 "
                     "수시공시 「단일판매ㆍ공급계약체결」에서 읽었습니다. 방산 수주표는 보안 때문에 요약만 "
                     "공시하는 회사가 있어, 잔고가 없으면 그 사실을 그대로 적습니다.")


def party_html(s):
    cnt = collections.Counter(c["party_kind"] for c in s["contracts"])
    amt = collections.Counter()
    for c in s["contracts"]:
        amt[c["party_kind"]] += (c["amt_krw_m"] or 0)
    if not cnt:
        return '<p class="mut">계약 공시가 없습니다.</p>'
    rows = "".join('<tr><td class="l">%s</td><td>%d</td><td data-v="%.0f">%s</td></tr>'
                   % (E(PARTY_KO.get(k, k)), n, amt[k], fmt_eok(amt[k]))
                   for k, n in cnt.most_common())
    return ('<div class="wrap"><table data-sortable><thead><tr><th class="l">상대</th><th>건수</th>'
            '<th>금액(억)</th></tr></thead><tbody>%s</tbody></table></div>' % rows)


def cat_ko(data, cid):
    for c in data["tax"]["cats"]:
        if c["id"] == cid:
            return c["ko"]
    return cid


# ── 허브 ───────────────────────────────────────────────────

def hub_html(data, sums):
    prime = [s for s in sums if s["rec"]["role"] == "prime"]
    # 연결로 다른 체계업체를 품은 회사(한화에어로 ⊃ 한화시스템·한화오션)의 자회사는 합계에서 뺀다.
    inside = {k for s in prime for k in s["consolidates"]}
    top_primes = [s for s in prime if s["stock"] not in inside]
    dupe_note = ("한화에어로스페이스의 수주표에 한화시스템·한화오션이 행으로 들어 있어 "
                 "합계에서는 자회사를 뺐습니다" if inside else "회사마다 공시 기준 분기가 다릅니다")
    cards = []
    for s in sorted(prime, key=lambda s: -(s["backlog"] or 0)):
        rec = s["rec"]
        top = sorted(s["dom_amt"].items(), key=lambda kv: -kv[1])[:3]
        chips = "".join(_chip(dom_meta(data, d)["ko"], dom_meta(data, d)["color"], s["dom_n"][d])
                        for d, a in top if s["dom_n"][d])
        cards.append('<a class="cardlink" href="%s/index.html"><div class="t"><b>%s</b>'
                     '<span class="code">%s</span></div><p>%s</p>'
                     '<div class="chips" style="margin-top:8px">%s</div>'
                     '<div class="stat"><div><b>%s</b><span>수주잔고(억, %s)</span></div>'
                     '<div><b>%s</b><span>커버리지(년)</span></div>'
                     '<div><b>%s</b><span>방산비중</span></div>'
                     '<div><b>%s</b><span>수출비중</span></div></div>'
                     '<div class="go">회사 데이터 →</div></a>'
                     % (E(rec["stock"]), E(rec["name"]), E(rec["stock"]),
                        E((rec["product"] or "")[:70]), chips,
                        fmt_eok(s["backlog"]), E(s["latest_q"] or "—"),
                        fmt_x(s["coverage"]) if s["coverage"] else "—",
                        ("%.0f%%" % s["def_share"]) if s["def_share"] is not None else "—",
                        ("%.0f%%" % s["exp_share"]) if s["exp_share"] is not None else "—"))
    cons = data["contracts"]
    defc = [c for c in cons if not c["civil"]]
    dom_amt = collections.Counter()
    dom_n = collections.Counter()
    for c in defc:
        did = c["domain"] or "UNKNOWN"
        dom_amt[did] += (c["amt_krw_m"] or 0)
        dom_n[did] += 1
    dchips = "".join(_chip(dom_meta(data, d)["ko"], dom_meta(data, d)["color"], n)
                     for d, n in dom_n.most_common() if d != "UNKNOWN")
    big = sorted([c for c in defc if c["amt_krw_m"]], key=lambda c: -c["amt_krw_m"])[:25]
    names = {r["stock"]: r for r in data["uni"]}
    ncat = sum(1 for c in data["sup"].values() if c["cats"])
    nlink = sum(1 for c in data["sup"].values() if c["primes"])
    body = """
<div class="kpi">
 <div class="hero"><b>%s<small>억</small></b><span>체계업체 %d사 수주잔고 합(최근 분기)</span>
  <i class="mut">%s</i></div>
 <div><b>%d</b><span>방산 계약 공시(2020~) · %s억</span><i class="mut">민수 %d건은 갈라 뒀습니다</i></div>
 <div><b>%d</b><span>모집단 종목(네 겹 전수)</span><i class="mut">부품 분류 %d · 체계업체 연결 %d</i></div>
 <div><b>%d</b><span>계통(무기체계 계열)</span><i class="mut">계약명에서 판정</i></div>
</div>
<h2 class="sec">체계업체<span>수주잔고 순 · 칩은 계약 공시 상위 계통(건수)</span></h2>
<div class="cards">%s</div>
<div class="grid2">
 <section class="card"><h2>계통별 계약 금액 <em>수주잔고는 계통별로 공시되지 않습니다 — 계통 구성은 계약 공시 금액으로 봅니다 · 억원</em></h2>
  <div class="chart"><canvas id="cDom"></canvas></div>
  <div class="chips" style="margin-top:10px">%s</div></section>
 <section class="card"><h2>계약 유형별 금액 <em>이익 성격이 유형마다 다릅니다</em></h2>
  <div class="chart"><canvas id="cType"></canvas></div></section>
</div>
<section class="card"><h2>최근 대형 계약 <em>금액 상위 25건 · 계약상대가 공개인 것이 방산의 특징입니다</em></h2>%s</section>
<h2 class="sec">더 보기<span>부품 인포그래픽과 모집단 근거</span></h2>
<div class="cards">
 <a class="cardlink" href="parts.html"><div class="t"><b>🛠 무기체계 인포그래픽</b></div>
  <p>전차·전투기·함정·유도탄 실루엣에서 부품 영역을 누르면 그 부품을 만드는 상장사로 갑니다.</p>
  <div class="go">인포그래픽 →</div></a>
 <a class="cardlink" href="coverage.html"><div class="t"><b>커버리지</b></div>
  <p>모집단 %d종목이 어떤 근거로 들어왔는지, ④ 본문 탐색에서 무엇이 승격·제외됐는지.</p>
  <div class="go">커버리지 →</div></a>
</div>
<script>const DATA=%s;</script>
<script>%s</script>
<script>
(function(){
 new Chart(document.getElementById('cDom'),{type:'bar',data:{labels:DATA.doms.map(function(d){return d.ko}),
  datasets:[{label:'억원',data:DATA.doms.map(function(d){return Math.round(d.amt/100)}),
   backgroundColor:DATA.doms.map(function(d){return d.color})}]},
  options:{indexAxis:'y',plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){
   var d=DATA.doms[c.dataIndex];return (c.parsed.x||0).toLocaleString()+'억 · '+d.n+'건'}}}},
   scales:{x:{ticks:{callback:function(v){return v.toLocaleString()}}},y:{grid:{display:false}}}}});
 new Chart(document.getElementById('cType'),{type:'bar',data:{labels:DATA.ctypes.map(function(d){return d.ko}),
  datasets:[{label:'억원',data:DATA.ctypes.map(function(d){return Math.round(d.amt/100)}),
   backgroundColor:DATA.ctypes.map(function(d){return d.color})}]},
  options:{plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){
   var d=DATA.ctypes[c.dataIndex];return (c.parsed.y||0).toLocaleString()+'억 · '+d.n+'건'}}}},
   scales:{y:{ticks:{callback:function(v){return v.toLocaleString()}}},x:{grid:{display:false}}}}});
})();
</script>
<script>%s</script>
""" % (fmt_eok(sum(s["backlog"] or 0 for s in top_primes)), len(top_primes), dupe_note,
       len(defc), fmt_eok(sum(c["amt_krw_m"] or 0 for c in defc)), len(cons) - len(defc),
       len(data["uni"]), ncat, nlink, len([d for d in data["dom_order"] if d != "CIVIL"]),
       "".join(cards), dchips,
       contracts_table(big, data, tid="cbig", show_company=True, by_stock=names, rel=""),
       len(data["uni"]),
       json_for_html({
           "doms": [{"ko": dom_meta(data, d)["ko"], "color": dom_meta(data, d)["color"],
                     "amt": dom_amt[d], "n": dom_n[d]}
                    for d, _ in dom_amt.most_common() if d != "UNKNOWN"],
           "ctypes": [{"ko": ctype_meta(data, c)["ko"], "color": ctype_meta(data, c)["color"],
                       "amt": sum(x["amt_krw_m"] or 0 for x in defc if x["ctype"] == c),
                       "n": sum(1 for x in defc if x["ctype"] == c)}
                      for c in data["ctype_order"]]}),
       CHART_DEFAULTS_JS, TABLE_JS)
    return page("한국방산 — 수주·계약·부품", body, depth=0, h1="🛡 한국방산",
                scripts=("vendor/chart.umd.min.js",),
                nav=(("← ARGUS", "../index.html"), ("🏗 한국건설", "../kce/index.html"),
                     ("⚓ 한국조선", "../kship/index.html")),
                lead="국내 상장 방산기업의 수주를 이 산업의 축으로 읽습니다 — 사업 단위 계약(계약상대가 공개입니다), "
                     "무기체계 계통, 계약 유형(체계개발·양산·성능개량·PBL), 방산/민수·내수/수출 부문 매출, "
                     "그리고 <b>잔고 커버리지(몇 년치 일감)</b>. 체계업체뿐 아니라 부품사까지 전수로 담습니다.")


# ── 커버리지 ───────────────────────────────────────────────

def coverage_html(data, sums):
    by = {s["stock"]: s for s in sums}
    rows = []
    for r in data["uni"]:
        s = by.get(r["stock"])
        st = r["stock"]
        bits = []
        if s and s["qs"]:
            bits.append("정기보고서 %d분기" % len(s["qs"]))
        if s and s["contracts"]:
            bits.append("계약 %d건" % len(s["contracts"]))
        if s and s["sup"].get("cats"):
            bits.append("부품 %d" % len(s["sup"]["cats"]))
        if s and s["sup"].get("primes"):
            bits.append("체계업체 연결 %d" % len(s["sup"]["primes"]))
        status = " · ".join(bits) or "원문에서 수치를 찾지 못함"
        cls = "up" if (s and (s["backlog"] is not None or s["contracts"])) else (
            "wn" if bits else "tx3")
        link = ('<a href="%s/index.html">%s</a>' % (E(st), E(r["name"]))
                if s and has_page(s) else E(r["name"]))
        rows.append('<tr><td class="l">%s</td><td class="mut">%s</td><td class="l">%s</td>'
                    '<td class="l mut">%s</td><td class="l"><b class="%s">%s</b></td>'
                    '<td class="l mut">%s</td><td class="l mut">%s</td></tr>'
                    % (link, E(st), E(ROLE_KO.get(r["role"], r["role"])),
                       E((r["industry"] or "")[:22]), cls, E(status), E(r["source"]),
                       E((r.get("reason") or r.get("product") or "")[:70])))
    probe = data.get("probe") or {}
    rej = probe.get("rejected") or []
    scan = ""
    if probe:
        rj = "".join('<tr><td class="l">%s</td><td>%s</td><td class="l">%s</td><td>%d</td>'
                     '<td class="l mut">%s</td><td class="l mut">%s</td></tr>'
                     % (E(x["name"]), E(x["stock"]), E((x.get("industry") or "")[:20]),
                        x.get("hits", 0),
                        E(", ".join("%s %d" % kv for kv in list((x.get("terms") or {}).items())[:4])),
                        E(json.dumps(x.get("mentions") or {}, ensure_ascii=False)
                          if x.get("mentions") else (x.get("product") or "")[:40]))
                     for x in sorted(rej, key=lambda x: -x.get("hits", 0))[:80])
        scan = ('<section class="card"><h2>④ 본문 탐색 <em>%s 정기보고서 · 후보 %d사 · 승격 %d · '
                '검토·제외 %d · 원문 못 읽음 %d</em></h2>'
                '<p style="font-size:12px;color:var(--tx2);line-height:1.8">기준: %s</p>'
                '<details><summary style="cursor:pointer;font-size:12px">검토·제외 상위 80사 '
                '(방산 낱말 많은 순)</summary><div class="wrap"><table data-sortable><thead><tr>'
                '<th class="l">회사</th><th>종목코드</th><th class="l">업종</th><th>방산 낱말</th>'
                '<th class="l">낱말</th><th class="l">체계업체 언급 · 제품</th></tr></thead>'
                '<tbody>%s</tbody></table></div></details>%s</section>'
                % (E(probe.get("quarter", "")), probe.get("n_cand", 0),
                   len(probe.get("promoted") or {}), len(rej), len(probe.get("failed") or []),
                   E(probe.get("rule", "")), rj,
                   ('<p class="mut" style="font-size:11.5px;margin-top:8px">원문을 못 읽어 판정하지 못한 회사'
                    '(승격하지 않는다): %s</p>'
                    % E(", ".join("%s(%s — %s)" % (x["name"], x["stock"], x.get("note", ""))
                                  for x in (probe.get("failed") or [])[:20])))
                   if probe.get("failed") else ""))
    body = """
<section class="card" style="margin-top:0"><h2>모집단 규칙 <em>재현 가능한 네 겹 · 이름으로 넣지 않습니다</em></h2>
<p style="font-size:12px;color:var(--tx2);line-height:1.8">
① KIND 업종 <b>항공기·우주선 및 부품 제조업</b>·<b>무기 및 총포탄 제조업</b> 전 종목 ·
② KIND 주요제품 문구에 방산 어휘(방산·군용·함정·유도·탄약·전차·자주포·레이더·야시·항전·군수…) ·
③ 사유를 적은 지정(체계업체와 널리 알려진 부품사 — <b>종목코드는 KIND에서 이름으로 조회해 확인</b>했습니다) ·
④ 그래도 빠지는 회사를 <b>정기보고서 II절 본문 탐색</b>으로 찾습니다. 고객이 정부·공공기관인 업종은 제외합니다.
편입 근거(업종·제품·지정·탐색)를 종목마다 남깁니다.</p></section>
<section class="card"><h2>종목별 상태 <em>%d종목</em></h2><div class="wrap"><table data-sortable>
<thead><tr><th class="l">회사</th><th>종목코드</th><th class="l">역할</th><th class="l">업종</th>
<th class="l">수록 상태</th><th class="l">편입 근거</th><th class="l">사유·주요제품</th></tr></thead>
<tbody>%s</tbody></table></div></section>
%s
<div class="note info">방산은 <b>보안 관계상</b> 수주 상세를 생략하는 회사가 있습니다(잔액 한 줄·기초/기말만).
그런 회사는 잔고 추이 대신 공시된 값만 싣고, 못 읽은 것은 못 읽었다고 적습니다.
부품사→체계업체 연결은 근거 등급(주요고객 주석 &gt; 계약공시 상대 &gt; 본문 언급)을 화면에 함께 띄웁니다.</div>
<script>%s</script>
""" % (len(data["uni"]), "".join(rows), scan, TABLE_JS)
    return page("한국방산 커버리지", body, depth=0, h1="커버리지",
                nav=(("허브", "index.html"), ("← ARGUS", "../index.html")),
                crumbs=(("ARGUS", "../index.html"), ("한국방산", "index.html"), ("커버리지", None)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    data = load_all()
    want = set(a.only.split(",")) if a.only else None
    sums, made = [], 0
    for r in data["uni"]:
        s = summary(r["stock"], data)
        sums.append(s)
        if want and r["stock"] not in want:
            continue
        if not has_page(s):
            continue
        d = os.path.join(KDEF, r["stock"])
        os.makedirs(d, exist_ok=True)
        atomic_write(os.path.join(d, "index.html"), company_html(s, data))
        made += 1
    print("회사 페이지 %d개" % made)
    if a.all:
        atomic_write(os.path.join(KDEF, "index.html"), hub_html(data, sums))
        atomic_write(os.path.join(KDEF, "coverage.html"), coverage_html(data, sums))
        print("index.html · coverage.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
