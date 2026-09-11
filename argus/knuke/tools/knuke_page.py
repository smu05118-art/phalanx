#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""knuke_page — 원전·발전기자재 탭의 페이지를 만든다.

  index.html            허브 — 회사 카드(잔고·커버리지·발주처 집중도·수출비중) · 발전원별 잔고/계약 구성 ·
                        호기별 타임라인(계약기간이 있는 회사) · 최근 대형 계약
  coverage.html         모집단 전수(네 겹)와 편입 근거 · ③ 본문 탐색 승격/제외
  <종목코드>/index.html  회사 — 수주잔고 추이 · 발전원별 잔고 · 롤포워드 · 계약 목록(발주처·사업명·기간·
                        기본도급액·완성공사액·계약잔액) · 호기 타임라인 · 부문매출 · 발주처 집중도 ·
                        공급계층 구성 · 계약 공시 · 부품/납품 관계

축이 조선·방산과 다른 이유는 원문에 있다(스펙 §왜수주기반):
  · 수주표에 **발주처 실명·사업명·계약기간**이 행마다 있다 — 호기 타임라인·발주처 집중도를 만든다.
  · 주기기(두산·신규 착공)와 정비/O&M(한전KPS·가동 호기)은 다른 장사다 — 한 화면에서 갈라 본다.
  · 국내 발주(한수원)와 해외 수주(체코·루마니아)는 리드타임이 다르다.

    python3 knuke_page.py --all
"""
import argparse
import collections
import datetime
import os
import sys

from knuke_lib import (E, KNUKE, CHART_DEFAULTS_JS, TABLE_JS, atomic_write, fmt_eok, fmt_n,
                       fmt_x, json_for_html, load_asset, page, pct, slot_color)
from knuke_universe import load as load_universe
import knuke_contracts
import knuke_reports
import knuke_suppliers

DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=%s"
ROLE_KO = {"main": "주기기", "eng": "설계·엔지니어링", "om": "정비·O&M", "part": "기자재·부품",
           "material": "소재·주단조", "holding": "지주"}
PARTY_KO = {"GOV": "관급(한수원·한전·발전사)", "PRIME": "주기기·설계·정비 대형사",
            "FOREIGN": "해외(발전사·EPC)", "DOMESTIC": "국내 기업",
            "ANON": "익명", "UNKNOWN": "미상"}


def load_all():
    uni = load_universe()
    doms = load_asset("domains.json")["domains"]
    tiers = load_asset("contract_types.json")["types"]
    reports = knuke_reports.load()
    return {
        "uni": uni,
        "by_stock": {r["stock"]: r for r in uni},
        "doms": {d["id"]: d for d in doms},
        "dom_order": [d["id"] for d in doms],
        "tiers": {c["id"]: c for c in tiers},
        "tier_order": [c["id"] for c in tiers] + ["UNKNOWN"],
        "contracts": knuke_contracts.load(),
        "reports": reports.get("companies", {}),
        "quarters": reports.get("quarters", []),
        "sup": {c["stock"]: c for c in knuke_suppliers.load().get("cos", [])},
        "tax": load_asset("parts_taxonomy.json"),
        "probe": load_asset("universe_probe.json") if os.path.exists(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets",
                         "universe_probe.json")) else {},
    }


def dom_meta(data, did):
    d = data["doms"].get(did)
    if not d:
        return {"id": "UNCL", "ko": "미상", "color": "#5d6675"}
    return {"id": d["id"], "ko": d["ko"], "color": slot_color(d["slot"])}


def tier_meta(data, cid):
    c = data["tiers"].get(cid)
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
    backlog = latest.get("backlog") if latest else None
    fy = latest.get("revenue_fy") if latest else None
    cov = (backlog / fy) if (backlog and fy) else None
    # 계약 공시 기준 발전원·공급계층 구성
    dom_amt, dom_n = collections.Counter(), collections.Counter()
    tier_amt, tier_n = collections.Counter(), collections.Counter()
    for c in cons:
        did = c["domain"] or "UNCL"
        dom_amt[did] += (c["amt_krw_m"] or 0)
        dom_n[did] += 1
        tier_amt[c["tier"]] += (c["amt_krw_m"] or 0)
        tier_n[c["tier"]] += 1
    # 발주처 집중도 — 정기보고서 award 표에서 한수원(관급) 비중
    client_bl = (latest or {}).get("client_backlog") or {}
    total_cl = sum(client_bl.values()) or None
    khnp = sum(v for k, v in client_bl.items()
               if any(w in k for w in ("한국수력원자력", "한수원", "KHNP")))
    khnp_share = (100.0 * khnp / total_cl) if total_cl else None
    top_client = max(client_bl.items(), key=lambda kv: kv[1]) if client_bl else None
    top_client_share = (100.0 * top_client[1] / total_cl) if (top_client and total_cl) else None
    exp = latest.get("revenue_export") if latest else None
    dom_rev = latest.get("revenue_domestic") if latest else None
    return {
        "stock": stock, "rec": rec, "comp": comp, "qs": qs, "latest_q": qs[-1] if qs else None,
        "latest": latest, "contracts": cons,
        "backlog": backlog, "fy": fy, "coverage": cov,
        "dom_backlog": (latest or {}).get("dom_backlog") or {},
        "client_backlog": client_bl, "khnp_share": khnp_share,
        "top_client": top_client[0] if top_client else None, "top_client_share": top_client_share,
        "timeline": (latest or {}).get("timeline") or [],
        "exp_share": pct(exp, (exp or 0) + (dom_rev or 0)) if latest else None,
        "dom_amt": dom_amt, "dom_n": dom_n, "tier_amt": tier_amt, "tier_n": tier_n,
        "amt_total": sum(c["amt_krw_m"] or 0 for c in cons),
        "sup": data["sup"].get(stock) or {},
        "security": bool(latest.get("security_note")) if latest else False,
    }


def has_page(s):
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
    cls = {2: "", 3: "mut", 4: "mut"}.get(p["grade"], "mut")
    return '<span class="pill %s" title="%s">%s</span>' % (cls, E(p.get("detail", "")), E(p["basis_ko"]))


def contracts_table(rows, data, tid="ct", show_company=False, by_stock=None, rel="../"):
    tr = []
    for c in sorted(rows, key=lambda c: (c["signed"] or c["start"] or ""), reverse=True):
        dm = dom_meta(data, c["domain"]) if c["domain"] else {"ko": "미상", "color": "#5d6675"}
        tm = tier_meta(data, c["tier"])
        amt = c["amt_krw_m"]
        who = ""
        if show_company:
            nm = (by_stock or {}).get(c["stock"], {}).get("name", c["stock"])
            who = '<td class="l"><a href="%s%s/index.html">%s</a></td>' % (rel, E(c["stock"]), E(nm))
        nm = (c["name"] or "").strip()
        if nm in ("", "-"):
            w = (c.get("withheld") or "").strip("- ")
            nm = ('<span class="pill">공시유보</span> %s' % E(w or "사유 미기재")) if w else "—"
        else:
            nm = E(nm[:70]) + (' <span class="pill">SMR</span>' if c.get("smr") else "")
        party = E(c["party"] or "—")
        if c["party_prime"]:
            party = '<a href="%s%s/index.html">%s</a>' % (rel, E(c["party_prime"]), party)
        tr.append(
            '<tr><td class="l">%s</td>%s<td class="l">%s%s</td><td class="l">%s</td>'
            '<td class="l">%s</td><td data-v="%.0f">%s</td><td data-v="%s">%s</td>'
            '<td class="l">%s<br><span class="mut">%s</span></td><td class="l mut">%s</td>'
            '<td class="l"><a href="%s" target="_blank" rel="noopener noreferrer">원문</a>%s</td></tr>'
            % (E(c["signed"] or c["start"] or "—"), who, _sw(dm["color"]), E(dm["ko"]),
               E(tm["ko"]), nm,
               (amt or 0), fmt_eok(amt), (c["years"] if c["years"] is not None else -1),
               fmt_x(c["years"]) if c["years"] is not None else "—",
               party, E(PARTY_KO.get(c["party_kind"], c["party_kind"])),
               E((c["start"] or "—") + " ~ " + (c["end"] or "—")),
               E(DART % c["rcp"]),
               ' <span class="pill">정정</span>' if c.get("corrected") else ""))
    head = ('<tr><th class="l">수주일</th>%s<th class="l">발전원</th><th class="l">공급계층</th>'
            '<th class="l">사업명(체결계약명)</th><th>금액(억)</th><th>기간(년)</th>'
            '<th class="l">계약상대</th><th class="l">계약기간</th><th class="l">출처</th></tr>'
            % ('<th class="l">회사</th>' if show_company else ""))
    return ('<div class="ctl"><input data-filter="#%s" type="search" placeholder="사업명·발전원·계층·상대 검색"></div>'
            '<div class="wrap tall"><table id="%s" data-sortable><thead>%s</thead><tbody>%s</tbody></table></div>'
            % (tid, tid, head, "".join(tr)))


def timeline_html(items, data, this_year=None):
    """계약기간(최초계약일~종료일)이 있는 award 행 → 막대 타임라인. 발전원 색으로."""
    rows = [x for x in items if x.get("start") and x.get("end") and x["end"] > x["start"]]
    if not rows:
        return ""
    this_year = this_year or datetime.date.today().year
    ys = [int(x["start"][:4]) for x in rows] + [int(x["end"][:4]) for x in rows]
    y0, y1 = min(ys), max(ys)
    span = max(1, y1 - y0)

    def frac(iso):
        y, m, d = int(iso[:4]), int(iso[5:7]), int(iso[8:10])
        return (y + (m - 1) / 12.0 - y0) / span

    rows.sort(key=lambda x: x["end"], reverse=True)
    rows = rows[:44]
    ticks = ""
    for yr in range(y0, y1 + 1):
        if span > 16 and (yr - y0) % 2:
            continue
        left = 100.0 * (yr - y0) / span
        ticks += '<span style="left:%.2f%%">%d</span>' % (left, yr)
    now_left = 100.0 * min(1.0, max(0.0, (this_year - y0) / span))
    bars = ""
    for x in rows:
        dm = dom_meta(data, x.get("domain")) if x.get("domain") else {"ko": "기타", "color": "#5d6675"}
        left = 100.0 * max(0.0, frac(x["start"]))
        width = 100.0 * max(0.01, frac(x["end"]) - frac(x["start"]))
        label = ((x.get("client") or "") + " " + (x.get("name") or "")).strip()[:40] or "(사업명 없음)"
        tip = "%s | %s~%s | 잔액 %s억" % (label, x["start"][:7], x["end"][:7], fmt_eok(x.get("closing")))
        bars += ('<div class="row"><div class="lbl" title="%s">%s</div><div class="lane">'
                 '<div class="tick now" style="left:%.2f%%"></div>'
                 '<div class="bar2" title="%s" style="left:%.2f%%;width:%.2f%%;background:%s"></div>'
                 '</div></div>'
                 % (E(tip), E(label), now_left, E(tip), left, width, E(dm["color"])))
    head = ('<div class="head"><div class="lbl"></div><div class="lane">%s'
            '<span class="now" style="left:%.2f%%;color:var(--tx2)">현재</span></div></div>'
            % (ticks, now_left))
    return '<div class="tl">%s%s</div>' % (head, bars)


# ── 회사 페이지 ─────────────────────────────────────────────

def company_html(s, data):
    rec, latest = s["rec"], s["latest"]
    kpi = []
    if s["backlog"] is not None:
        kpi.append('<div class="hero"><b>%s<small>억</small></b><span>수주잔고 · 정기보고서 %s</span></div>'
                   % (fmt_eok(s["backlog"]), E(s["latest_q"] or "—")))
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
    if s["khnp_share"] is not None:
        kpi.append('<div><b>%.0f<small>%%</small></b><span>발주처 집중도(한수원)</span>'
                   '<i class="mut">잔고 기준</i></div>' % s["khnp_share"])
    elif s["top_client_share"] is not None:
        kpi.append('<div><b>%.0f<small>%%</small></b><span>최대 발주처 집중도</span>'
                   '<i class="mut">%s</i></div>' % (s["top_client_share"], E((s["top_client"] or "")[:16])))
    if s["exp_share"] is not None:
        kpi.append('<div><b>%.0f<small>%%</small></b><span>수출 비중(내수/수출 표)</span></div>'
                   % s["exp_share"])
    kpi.append('<div><b>%d<small>건</small></b><span>계약 공시(단일판매ㆍ공급) · %s억</span></div>'
               % (len(s["contracts"]), fmt_eok(s["amt_total"])))

    # 잔고 롤포워드 표
    roll = []
    for q in s["qs"]:
        v = s["comp"]["quarters"][q]
        note = v.get("unit_note") or ""
        shape_ko = {"award": "발주처·사업명·계약기간", "roll": "기초+신규−기납품",
                    "openclose": "기초·기말만", "gross": "총액−기납품", "item": "품목별",
                    "balance": "잔액 한 줄"}.get(v.get("shape"), v.get("shape") or "—")
        roll.append('<tr><td class="l">%s</td><td>%s</td><td>%s</td><td>%s</td><td><b>%s</b></td>'
                    '<td class="l mut">%s</td><td class="l mut">%s</td>'
                    '<td class="l"><a href="%s" target="_blank" rel="noopener noreferrer">원문</a></td></tr>'
                    % (E(q), fmt_eok(v.get("opening")), fmt_eok(v.get("gross")),
                       fmt_eok(v.get("delivered")), fmt_eok(v.get("backlog")),
                       E(shape_ko), E(note), E(DART % (v.get("rcp") or ""))))
    roll_html = ('<div class="wrap"><table><thead><tr><th class="l">분기</th><th>기초</th>'
                 '<th>수주총액/도급</th><th>기납품/완성</th><th>수주잔고</th><th class="l">표 모양</th>'
                 '<th class="l">비고</th><th class="l">출처</th></tr></thead><tbody>%s</tbody></table></div>'
                 % "".join(roll)) if roll else \
        '<p class="mut">이 회사의 정기보고서에서 수주표를 찾지 못했습니다.</p>'

    # 정기보고서 수주표의 계약 목록(발주처·사업명·기간·기본도급액·완성공사액·계약잔액)
    seg_rows = (latest or {}).get("segments") or []
    award_rows = [r for r in seg_rows if r.get("client") or r.get("start") or r.get("end")]
    award_html = ""
    if award_rows and (latest or {}).get("has_client"):
        tr = []
        for r in sorted(award_rows, key=lambda r: -(r.get("closing") or 0)):
            dm = dom_meta(data, r.get("domain")) if r.get("domain") else {"ko": "—", "color": "#5d6675"}
            tr.append('<tr><td class="l">%s</td><td class="l">%s</td><td class="l">%s%s</td>'
                      '<td class="l mut">%s ~ %s</td><td data-v="%.0f">%s</td>'
                      '<td data-v="%.0f">%s</td><td data-v="%.0f"><b>%s</b></td></tr>'
                      % (E((r.get("client") or "—")[:24]), E((r.get("name") or "—")[:44]),
                         _sw(dm["color"]), E(dm["ko"]),
                         E((r.get("start") or r.get("start_raw") or "—")),
                         E((r.get("end") or r.get("end_raw") or "—")),
                         (r.get("gross") or 0), fmt_eok(r.get("gross")),
                         (r.get("delivered") or 0), fmt_eok(r.get("delivered")),
                         (r.get("closing") or 0), fmt_eok(r.get("closing"))))
        award_html = ('<section class="card"><h2>정기보고서 수주 목록 <em>II-4 수주상황 · 발주처·사업명·계약기간이 '
                      '행마다 공시됩니다 · 억원</em></h2><div class="wrap tall"><table data-sortable><thead><tr>'
                      '<th class="l">발주처</th><th class="l">사업명</th><th class="l">발전원</th>'
                      '<th class="l">계약기간</th><th>기본도급/수주총액</th><th>완성/기납품</th>'
                      '<th>계약잔액</th></tr></thead><tbody>%s</tbody></table></div></section>'
                      % "".join(tr))

    # 호기 타임라인
    tl = timeline_html(s["timeline"], data)
    tl_html = ('<section class="card"><h2>호기·사업 타임라인 <em>정기보고서 수주표의 계약기간 · 막대는 '
               '최초계약일~종료일, 색은 발전원</em></h2>%s</section>' % tl) if tl else ""

    # 부문 매출
    seg_html = ""
    if latest and (latest.get("revenue_segments") or latest.get("sales_segments")):
        rows = []
        for r in latest.get("revenue_segments") or []:
            dm = dom_meta(data, r["segdomain"]) if r["segdomain"] else {"ko": "미판정", "color": "#5d6675"}
            rows.append('<tr><td class="l">%s</td><td class="l mut">%s</td><td class="l">%s%s</td>'
                        '<td class="l">%s</td><td data-v="%.0f">%s</td></tr>'
                        % (E(r["seg"] or "(부문 표기 없음)"), E((r["item"] or "")[:40]),
                           _sw(dm["color"]), E(dm["ko"]), E(r["kind"]),
                           r["val"] or 0, fmt_eok(r["val"])))
        for r in latest.get("sales_segments") or []:
            dm = dom_meta(data, r["segdomain"]) if r["segdomain"] else {"ko": "미판정", "color": "#5d6675"}
            rows.append('<tr><td class="l">%s</td><td class="l mut">%s</td><td class="l">%s%s</td>'
                        '<td class="l">%s</td><td data-v="%.0f">%s</td></tr>'
                        % (E(r["seg"] or "(부문 표기 없음)"), E((r["item"] or "")[:40]),
                           _sw(dm["color"]), E(dm["ko"]),
                           ("비중 %.1f%%" % r["pct"]) if r.get("pct") else "—",
                           r["val"] or 0, fmt_eok(r["val"])))
        seg_html = ('<section class="card"><h2>부문 매출 <em>%s · 억원 · 부문 이름은 원문 그대로, '
                    '발전원 판정은 이름에서</em></h2>'
                    '<div class="wrap"><table data-sortable><thead><tr><th class="l">부문(원문)</th>'
                    '<th class="l">품목</th><th class="l">발전원</th><th class="l">구분</th>'
                    '<th>금액(억)</th></tr></thead><tbody>%s</tbody></table></div></section>'
                    % (E(s["latest_q"] or ""), "".join(rows)))

    # 계통·계층 구성 데이터
    dom_rows = [(d, s["dom_amt"][d], s["dom_n"][d]) for d in data["dom_order"] + ["UNCL"]
                if s["dom_n"].get(d)]
    tier_rows = [(c, s["tier_amt"][c], s["tier_n"][c]) for c in data["tier_order"] if s["tier_n"].get(c)]
    dom_bl = [(d, v) for d, v in sorted((s["dom_backlog"] or {}).items(), key=lambda kv: -kv[1])]

    # 납품 관계 / 부품
    sup = s["sup"]
    rel_html = ""
    if sup.get("primes"):
        rows = "".join('<tr><td class="l"><a href="../%s/index.html">%s</a></td><td class="l">%s</td>'
                       '<td class="l mut">%s</td></tr>'
                       % (E(p["stock"]), E(p["nm"]), _grade_pill(p), E(p.get("detail", "")))
                       for p in sup["primes"])
        rel_html = ('<section class="card"><h2>납품처(대형사) <em>계약공시 상대 &gt; 본문 언급 순 · 근거를 함께 싣습니다</em></h2>'
                    '<div class="wrap"><table><thead><tr><th class="l">주기기·설계·정비 대형사</th>'
                    '<th class="l">근거</th><th class="l">내용</th></tr></thead><tbody>%s</tbody></table></div></section>'
                    % rows)

    parts_html = ""
    if sup.get("cats"):
        chips = " ".join(_chip(cat_ko(data, h["cat"]), None, href="../parts.html#" + h["cat"],
                               title="근거: %s 「%s」" % ({"contract": "계약명", "body": "II절 본문",
                                                        "kind": "KIND 주요제품"}.get(h["src"], h["src"]),
                                                       h["kw"]))
                         for h in sup["cats"])
        parts_html = ('<section class="card"><h2>공급 계층·부품 <em>계약명·정기보고서 본문·KIND 주요제품 문구에서 '
                      '읽은 낱말 — 칩에 근거가 붙어 있습니다</em></h2><div class="chips">%s</div></section>'
                      % chips)

    notes = []
    if s["security"]:
        notes.append("이 회사는 정기보고서에 <b>보안 관계상 수주 상세를 생략</b>한다고 적었습니다 — "
                     "잔고는 요약치만 공시됩니다.")
    notes.append("원전·발전 주기기는 <b>진행기준</b> 수익인식이 많아 수주·완성·매출 시점이 다릅니다. "
                 "잔고 커버리지는 '몇 년치 일감'을 보는 값이지 연도별 매출 예측이 아닙니다.")
    notes.append("정비/O&M(경상·예방·계획예방정비)은 가동 호기 수와 계속운전에 붙고, 주기기·설계는 "
                 "신규 착공에 붙습니다 — 발주 성격이 다릅니다.")

    chart = {
        "roll": [{"q": q, "backlog": s["comp"]["quarters"][q].get("backlog")} for q in s["qs"]],
        "doms": [{"ko": dom_meta(data, d)["ko"], "color": dom_meta(data, d)["color"],
                  "amt": a, "n": n} for d, a, n in dom_rows],
        "tiers": [{"ko": tier_meta(data, c)["ko"], "color": tier_meta(data, c)["color"],
                   "amt": a, "n": n} for c, a, n in tier_rows],
        "dombl": [{"ko": dom_meta(data, d)["ko"], "color": dom_meta(data, d)["color"], "amt": v}
                  for d, v in dom_bl],
    }
    body = """
<div class="kpi">%s</div>
<div class="grid2" style="margin-top:20px">
 <section class="card" style="margin-top:0"><h2>수주잔고 추이 <em>정기보고서 II-4 · 억원</em></h2>
  <div class="chart"><canvas id="cRoll"></canvas></div></section>
 <section class="card" style="margin-top:0"><h2>%s <em>%s · 억원</em></h2>
  <div class="chart"><canvas id="cDom"></canvas></div></section>
</div>
%s
<section class="card"><h2>수주 롤포워드 <em>회사마다 표 모양이 다릅니다 — 원문 모양을 같이 적습니다</em></h2>%s</section>
%s
%s
<div class="grid2">
 <section class="card"><h2>공급 계층 구성 <em>계약 공시 금액 기준 · 억원</em></h2>
  <div class="chart"><canvas id="cTier"></canvas></div></section>
 <section class="card"><h2>계약 상대 <em>원전·발전은 발주처가 관급으로 공개됩니다</em></h2>%s</section>
</div>
<section class="card"><h2>계약 공시 <em>단일판매ㆍ공급계약체결 · %d건</em></h2>%s</section>
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
        borderColor:'#3987e5',backgroundColor:'rgba(57,135,229,.18)',fill:true,tension:.25,spanGaps:true}]},
      options:{plugins:{legend:{display:false}},scales:{y:{ticks:{callback:function(v){return v.toLocaleString()}}},x:{grid:{display:false}}}}});
  }
  var dd=DATA.dombl.length?DATA.dombl:DATA.doms;
  if(dd.length){
    new Chart(document.getElementById('cDom'),{type:'bar',data:{labels:dd.map(function(d){return d.ko}),
      datasets:[{label:'억원',data:dd.map(function(d){return Math.round(d.amt/100)}),
        backgroundColor:dd.map(function(d){return d.color})}]},
      options:{indexAxis:'y',plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){
        var d=dd[c.dataIndex];return (c.parsed.x||0).toLocaleString()+'억'+(d.n?(' · '+d.n+'건'):'')}}}},
        scales:{x:{ticks:{callback:function(v){return v.toLocaleString()}}},y:{grid:{display:false}}}}});
  }
  if(DATA.tiers.length){
    new Chart(document.getElementById('cTier'),{type:'doughnut',data:{labels:DATA.tiers.map(function(d){return d.ko}),
      datasets:[{data:DATA.tiers.map(function(d){return Math.round(d.amt/100)}),
        backgroundColor:DATA.tiers.map(function(d){return d.color})}]},
      options:{plugins:{tooltip:{callbacks:{label:function(c){var d=DATA.tiers[c.dataIndex];
        return d.ko+': '+(c.parsed||0).toLocaleString()+'억 · '+d.n+'건'}}}}}});
  }
})();
</script>
<script>%s</script>
""" % ("".join(kpi),
       ("발전원별 잔고 구성" if dom_bl else "발전원별 계약 금액"),
       ("정기보고서 수주표 · 계약잔액 기준" if dom_bl else "계약 공시 금액 기준"),
       tl_html, roll_html, award_html, seg_html, party_html(s),
       len(s["contracts"]), contracts_table(s["contracts"], data, tid="ct%s" % s["stock"]),
       parts_html, rel_html,
       " ".join("<p>%s</p>" % n for n in notes),
       json_for_html(chart), CHART_DEFAULTS_JS, TABLE_JS)
    tags = (rec["stock"], rec["market"], ROLE_KO.get(rec["role"], rec["role"]), rec["industry"])
    dart = DART % (latest.get("rcp") if latest and latest.get("rcp") else "")
    return page("%s — 원전·발전 수주" % rec["name"], body, depth=1, h1=rec["name"], tags=tags,
                nav=(("허브", "../index.html"), ("인포그래픽", "../parts.html"),
                     ("커버리지", "../coverage.html"),
                     ("DART 원문 ↗", dart if latest else "https://dart.fss.or.kr")),
                crumbs=(("ARGUS", "../../index.html"), ("한국원전·발전기자재", "../index.html"),
                        (rec["name"], None)),
                scripts=("../vendor/chart.umd.min.js",),
                lead="수주잔고·부문매출은 정기보고서 II-4에서, 사업 단위 계약(발주처·사업명·계약기간·금액)은 "
                     "II-4 수주표와 수시공시 「단일판매ㆍ공급계약체결」에서 읽었습니다. 원전·발전 수주표는 "
                     "발주처가 실명(한국수력원자력 등)으로 공시되는 것이 이 산업의 특징입니다.")


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
    have = [s for s in sums if has_page(s) and (s["backlog"] is not None or s["contracts"])]
    cards = []
    for s in sorted(have, key=lambda s: -(s["backlog"] or 0)):
        rec = s["rec"]
        top = sorted(s["dom_amt"].items(), key=lambda kv: -kv[1])[:3]
        chips = "".join(_chip(dom_meta(data, d)["ko"], dom_meta(data, d)["color"], s["dom_n"][d])
                        for d, a in top if s["dom_n"][d])
        conc = s["khnp_share"] if s["khnp_share"] is not None else s["top_client_share"]
        conc_lbl = "한수원 비중" if s["khnp_share"] is not None else "최대발주처"
        cards.append('<a class="cardlink" href="%s/index.html"><div class="t"><b>%s</b>'
                     '<span class="code">%s</span></div><p>%s</p>'
                     '<div class="chips" style="margin-top:8px">%s</div>'
                     '<div class="stat"><div><b>%s</b><span>수주잔고(억, %s)</span></div>'
                     '<div><b>%s</b><span>커버리지(년)</span></div>'
                     '<div><b>%s</b><span>%s</span></div>'
                     '<div><b>%s</b><span>수출비중</span></div></div>'
                     '<div class="go">회사 데이터 →</div></a>'
                     % (E(rec["stock"]), E(rec["name"]), E(rec["stock"]),
                        E((rec["product"] or "")[:70]), chips,
                        fmt_eok(s["backlog"]), E(s["latest_q"] or "—"),
                        fmt_x(s["coverage"]) if s["coverage"] else "—",
                        ("%.0f%%" % conc) if conc is not None else "—", conc_lbl,
                        ("%.0f%%" % s["exp_share"]) if s["exp_share"] is not None else "—"))

    cons = data["contracts"]
    dom_amt, dom_n = collections.Counter(), collections.Counter()
    for c in cons:
        did = c["domain"] or "UNCL"
        dom_amt[did] += (c["amt_krw_m"] or 0)
        dom_n[did] += 1
    dchips = "".join(_chip(dom_meta(data, d)["ko"], dom_meta(data, d)["color"], n)
                     for d, n in dom_n.most_common() if d != "UNCL")
    # 발전원별 잔고 구성 — 회사별 award 표 계약잔액 합산
    dom_bl = collections.Counter()
    for s in have:
        for d, v in (s["dom_backlog"] or {}).items():
            dom_bl[d] += v
    # 호기 타임라인 — 모든 회사의 계약기간 있는 행 합쳐 상위
    tl_items = []
    for s in have:
        for x in s["timeline"]:
            y = dict(x)
            y["name"] = (s["rec"]["name"][:8] + " · " + (x.get("name") or "")) if x.get("name") else s["rec"]["name"]
            tl_items.append(y)
    big = sorted([c for c in cons if c["amt_krw_m"]], key=lambda c: -c["amt_krw_m"])[:25]
    names = {r["stock"]: r for r in data["uni"]}
    ncat = sum(1 for c in data["sup"].values() if c["cats"])
    nlink = sum(1 for c in data["sup"].values() if c["primes"])
    tl_hub = timeline_html(tl_items, data)
    tl_section = ('<section class="card"><h2>호기·사업 타임라인 <em>정기보고서 수주표에 계약기간이 있는 회사 · '
                  '막대는 최초계약일~종료일, 색은 발전원 — 신한울처럼 2030년대까지 뻗습니다</em></h2>%s</section>'
                  % tl_hub) if tl_hub else ""
    body = """
<div class="kpi">
 <div class="hero"><b>%s<small>억</small></b><span>주요사 수주잔고 합(최근 분기)</span>
  <i class="mut">회사마다 공시 기준 분기가 다릅니다</i></div>
 <div><b>%d</b><span>계약 공시(2020~) · %s억</span></div>
 <div><b>%d</b><span>모집단 종목(네 겹 전수)</span><i class="mut">부품 분류 %d · 대형사 연결 %d</i></div>
 <div><b>%d</b><span>발전원</span><i class="mut">공급계층 %d</i></div>
</div>
<h2 class="sec">회사<span>수주잔고 순 · 칩은 계약 공시 상위 발전원(건수)</span></h2>
<div class="cards">%s</div>
%s
<div class="grid2">
 <section class="card"><h2>발전원별 잔고 구성 <em>정기보고서 수주표(계약잔액) 합산 · 억원</em></h2>
  <div class="chart"><canvas id="cBl"></canvas></div></section>
 <section class="card"><h2>발전원별 계약 금액 <em>계약 공시 금액 · 억원</em></h2>
  <div class="chart"><canvas id="cDom"></canvas></div>
  <div class="chips" style="margin-top:10px">%s</div></section>
</div>
<section class="card"><h2>최근 대형 계약 <em>금액 상위 25건 · 발주처가 공개인 것이 이 산업의 특징입니다</em></h2>%s</section>
<h2 class="sec">더 보기<span>발전소 인포그래픽과 모집단 근거</span></h2>
<div class="cards">
 <a class="cardlink" href="parts.html"><div class="t"><b>🏭 발전소 인포그래픽</b></div>
  <p>원전·화력 단면에서 부품 영역(원자로·증기발생기·터빈·보일러…)을 누르면 그 기자재를 만드는 상장사로 갑니다.</p>
  <div class="go">인포그래픽 →</div></a>
 <a class="cardlink" href="coverage.html"><div class="t"><b>커버리지</b></div>
  <p>모집단 %d종목이 어떤 근거로 들어왔는지, ③ 본문 탐색에서 무엇이 승격·제외됐는지.</p>
  <div class="go">커버리지 →</div></a>
</div>
<script>const DATA=%s;</script>
<script>%s</script>
<script>
(function(){
 if(DATA.dombl.length){
  new Chart(document.getElementById('cBl'),{type:'bar',data:{labels:DATA.dombl.map(function(d){return d.ko}),
   datasets:[{label:'억원',data:DATA.dombl.map(function(d){return Math.round(d.amt/100)}),
    backgroundColor:DATA.dombl.map(function(d){return d.color})}]},
   options:{indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{ticks:{callback:function(v){return v.toLocaleString()}}},y:{grid:{display:false}}}}});
 }
 new Chart(document.getElementById('cDom'),{type:'bar',data:{labels:DATA.doms.map(function(d){return d.ko}),
  datasets:[{label:'억원',data:DATA.doms.map(function(d){return Math.round(d.amt/100)}),
   backgroundColor:DATA.doms.map(function(d){return d.color})}]},
  options:{indexAxis:'y',plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){
   var d=DATA.doms[c.dataIndex];return (c.parsed.x||0).toLocaleString()+'억 · '+d.n+'건'}}}},
   scales:{x:{ticks:{callback:function(v){return v.toLocaleString()}}},y:{grid:{display:false}}}}});
})();
</script>
<script>%s</script>
""" % (fmt_eok(sum(s["backlog"] or 0 for s in have)),
       len(cons), fmt_eok(sum(c["amt_krw_m"] or 0 for c in cons)),
       len(data["uni"]), ncat, nlink,
       len([d for d in data["dom_order"]]), len(data["tier_order"]) - 1,
       "".join(cards), tl_section, dchips,
       contracts_table(big, data, tid="cbig", show_company=True, by_stock=names, rel=""),
       len(data["uni"]),
       json_for_html({
           "doms": [{"ko": dom_meta(data, d)["ko"], "color": dom_meta(data, d)["color"],
                     "amt": dom_amt[d], "n": dom_n[d]}
                    for d, _ in dom_amt.most_common() if d != "UNCL"],
           "dombl": [{"ko": dom_meta(data, d)["ko"], "color": dom_meta(data, d)["color"], "amt": v}
                     for d, v in dom_bl.most_common()]}),
       CHART_DEFAULTS_JS, TABLE_JS)
    return page("한국원전·발전기자재 — 수주·계약·부품", body, depth=0, h1="☢ 한국원전·발전기자재",
                scripts=("vendor/chart.umd.min.js",),
                nav=(("← ARGUS", "../index.html"), ("🏗 한국건설", "../kce/index.html"),
                     ("⚓ 한국조선", "../kship/index.html"), ("🛡 한국방산", "../kdef/index.html")),
                lead="국내 상장 원전·발전기자재 기업의 수주를 이 산업의 축으로 읽습니다 — 발주처가 실명(한국수력원자력 등)인 "
                     "사업 단위 계약, 발전원(원자력·화력·신재생·송변전), 공급 계층(주기기·보조기기·계측제어·설계·정비 O&M·"
                     "검사·해체), 그리고 <b>계약기간이 2030년대까지 뻗는 호기별 타임라인</b>. 체계업체뿐 아니라 부품사까지 전수로 담습니다.")


# ── 커버리지 ───────────────────────────────────────────────

def coverage_html(data, sums):
    import json as _json
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
            bits.append("대형사 연결 %d" % len(s["sup"]["primes"]))
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
                     '<td class="l mut">%s</td></tr>'
                     % (E(x["name"]), E(x["stock"]), E((x.get("industry") or "")[:20]),
                        x.get("hits", 0),
                        E(", ".join("%s %d" % kv for kv in list((x.get("terms") or {}).items())[:5])))
                     for x in sorted(rej, key=lambda x: -x.get("hits", 0))[:80])
        scan = ('<section class="card"><h2>③ 본문 탐색 <em>%s 정기보고서 · 후보 %d사 · 승격 %d · '
                '검토·제외 %d · 원문 못 읽음 %d</em></h2>'
                '<p style="font-size:12px;color:var(--tx2);line-height:1.8">기준: %s</p>'
                '<details><summary style="cursor:pointer;font-size:12px">검토·제외 상위 80사 '
                '(원전·발전 낱말 많은 순)</summary><div class="wrap"><table data-sortable><thead><tr>'
                '<th class="l">회사</th><th>종목코드</th><th class="l">업종</th><th>원전·발전 낱말</th>'
                '<th class="l">낱말</th></tr></thead><tbody>%s</tbody></table></div></details></section>'
                % (E(probe.get("quarter", "")), probe.get("n_cand", 0),
                   len(probe.get("promoted") or {}), len(rej), len(probe.get("failed") or []),
                   E(probe.get("rule", "")), rj))
    body = """
<section class="card" style="margin-top:0"><h2>모집단 규칙 <em>재현 가능한 네 겹 · 이름으로 넣지 않습니다</em></h2>
<p style="font-size:12px;color:var(--tx2);line-height:1.8">
① KIND 업종(기계·구조용 금속·1차 철강·금속 가공·측정,시험·전기장비·기타 과학기술·엔지니어링) 중
주요제품에 원전·발전 어휘(원자력·원전·원자로·핵연료·방사선·발전설비·발전용·보일러·터빈·주단조·압력용기·열교환기) ·
② 사유를 적은 지정(두산에너빌리티·한전기술·한전KPS·비에이치아이·우진·오르비텍 등 — <b>종목코드는 scout 표본에서 확인</b>) ·
③ 그래도 빠지는 회사를 <b>정기보고서 II절 본문 탐색</b>(한국수력원자력·원전·발전소 언급)으로 찾습니다 ·
④ 리츠·부동산·금융·소프트웨어·의약·화장품·식품, 그리고 발전 <b>사업자</b>(한전·발전 5사 — 발주처이지 기자재사가 아님)는 제외.
편입 근거(KIND·지정·탐색)를 종목마다 남깁니다.</p></section>
<section class="card"><h2>종목별 상태 <em>%d종목</em></h2><div class="wrap"><table data-sortable>
<thead><tr><th class="l">회사</th><th>종목코드</th><th class="l">역할</th><th class="l">업종</th>
<th class="l">수록 상태</th><th class="l">편입 근거</th><th class="l">사유·주요제품</th></tr></thead>
<tbody>%s</tbody></table></div></section>
%s
<div class="note info">원전·발전 수주표는 회사마다 모양이 다릅니다 — 발주처·사업명·계약기간이 행마다 있는
<b>도급형</b>(한전기술·한전KPS)부터 잔액 한 줄까지. 못 읽은 것은 못 읽었다고 적습니다.
부품사→대형사(두산에너빌리티·한전기술·한전KPS) 연결은 근거 등급(계약공시 상대 &gt; 본문 언급)을 함께 띄웁니다.</div>
<script>%s</script>
""" % (len(data["uni"]), "".join(rows), scan, TABLE_JS)
    return page("한국원전·발전기자재 커버리지", body, depth=0, h1="커버리지",
                nav=(("허브", "index.html"), ("← ARGUS", "../index.html")),
                crumbs=(("ARGUS", "../index.html"), ("한국원전·발전기자재", "index.html"), ("커버리지", None)))


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
        d = os.path.join(KNUKE, r["stock"])
        os.makedirs(d, exist_ok=True)
        atomic_write(os.path.join(d, "index.html"), company_html(s, data))
        made += 1
    print("회사 페이지 %d개" % made)
    if a.all:
        atomic_write(os.path.join(KNUKE, "index.html"), hub_html(data, sums))
        atomic_write(os.path.join(KNUKE, "coverage.html"), coverage_html(data, sums))
        print("index.html · coverage.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
