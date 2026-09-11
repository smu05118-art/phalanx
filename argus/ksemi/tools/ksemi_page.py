#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ksemi_page — 한국반도체장비 탭의 페이지를 만든다.

  index.html            허브 — 잔고 상위 카드(잔고·잔고/매출 배수·인식기준·최대고객 비중),
                        공정단계별 회사 수·잔고 합, 최근 대형 수주
  coverage.html         모집단 154종목 전수와 편입 근거, ④ 승격/제외, 수주표 미공시 사유
  <종목코드>/index.html  잔고 롤포워드(8분기) · 제품별 매출 · 수출/내수 · 매출인식 기준(원문 인용) ·
                        주요 고객 · 계약 공시 · 공정 단계 태그 · 같은 단계 부품사 역참조

이 탭의 축은 **수주잔고와 매출인식 시점의 시차**다(스펙 「산업 특성」 1·2). 잔고를 공시하지
않는 회사가 실제로 있고(한미반도체 잔고 칸 `-`), 인식기준 주석은 사업보고서에만 있다 —
둘 다 **'미공시'·'원문에서 확인 못 함'으로 남긴다. 지어내지 않는다**(COMMON §0-1).

reports.json 이 아직 없거나 일부 종목만 들어 있어도 돌아간다(수집과 렌더가 분리돼 있다).

    python3 ksemi_page.py --all
"""
import argparse
import collections
import json
import os
import re
import sys

from ksemi_lib import (ASSETS, CHART_DEFAULTS_JS, E, KSEMI, TABLE_JS,
                       atomic_write, fmt_eok, fmt_n, fmt_x, json_for_html,
                       load_asset, page, stage_color)

DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=%s"

# 매출인식 기준 키 → 화면 표기. 스펙 「산업 특성 2」의 세 갈래.
BASIS_KO = {
    "sat": "설치·검수 완료(SAT)",
    "delivery": "인도",
    "progress": "진행기준",
    "shipment": "선적",
    "acceptance": "고객 검수",
}


def basis_ko(key):
    return BASIS_KO.get(key, key or "")


def china_exposure(contracts):
    """중국 노출(스펙 「산업 특성 6」) — **공시된 단일계약의 공급지역 칸**으로만 센다.

    지역별 매출은 II-4 매출실적이 수출/내수까지만 나누는 회사가 대부분이라 원문에 없다.
    반면 「단일판매ㆍ공급계약체결」에는 `4. 판매ㆍ공급지역` 칸이 있고, 주성엔지니어링
    `20240710900488` 은 거기에 **중국**이라 적혀 있다(PROGRESS §1-1). 그래서 이 지표는
    **매출 비중이 아니라 '공시된 계약 금액 중 중국향 비중'** 이다 — 화면에도 그렇게 적는다.

    금액 칸을 못 읽은 계약(`amt_mkrw` 없음)은 금액 분모·분자에서 빼고 건수만 센다.
    분모가 0이면 `share=None`(fail-closed — 0%로 적지 않는다).
    """
    cn = [c for c in contracts if c.get("region_cn")]
    known = [c for c in contracts if c.get("amt_mkrw")]
    cn_amt = sum(c["amt_mkrw"] for c in cn if c.get("amt_mkrw"))
    all_amt = sum(c["amt_mkrw"] for c in known)
    return {"n": len(cn), "n_all": len(contracts), "amt": cn_amt,
            "share": (100.0 * cn_amt / all_amt) if all_amt else None,
            "regions": sorted({(c.get("region") or "").strip() for c in cn} - {""})}


# ── 데이터 ─────────────────────────────────────────────────

def _opt(name, default=None):
    p = os.path.join(ASSETS, name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_all():
    uni = load_asset("universe.json")
    stages = load_asset("stages.json")
    tags = load_asset("stage_tags.json")
    scan = _opt("scan.json", {"rows": []})
    contracts = _opt("contracts.json", {"rows": []})
    reports = _opt("reports.json", {"rows": [], "quarters": []})
    peers = _opt("peers.json", {"rows": [], "_by_target": {}})
    expo = _opt("exposure.json", {"rows": []})
    return {
        "uni": uni["rows"],
        "stages": stages,
        "stage_by_key": {s["key"]: s for s in stages["stages"]},
        "tags": {r["stock"]: r for r in tags["rows"]},
        "per_stage": tags.get("per_stage", {}),
        "scan": {r["stock"]: r for r in scan.get("rows", [])},
        "scan_meta": scan,
        "contracts": contracts.get("rows", []),
        "peers": {r["stock"]: r for r in peers.get("rows", [])},
        "peers_rev": peers.get("_by_target", {}),
        "exposure": {r["stock"]: r for r in expo.get("rows", [])},
        "exposure_meta": expo,
        "peers_meta": peers,
        "reports": {r["stock"]: r for r in reports.get("rows", [])},
        "report_meta": reports,
    }


def members(data):
    """탭 구성원 = ④ 본문 탐색 '편입' ∪ 스펙 지정. 보류·배제는 커버리지에만 나온다."""
    out = []
    for r in data["uni"]:
        v = (data["scan"].get(r["stock"]) or {}).get("verdict")
        if v == "편입" or r.get("source") == "지정":
            out.append(r)
    return out


def part_keys(data, stock):
    """그 회사가 만드는 **부품** 키. stage_tags 의 근거 낱말을 부품 사전에 맞춰 본다.

    stage_tags 는 단계까지만 배정한다 — 부품 알갱이는 여기서 낱말로 되짚는다.
    낱말이 안 걸리면 빈 목록이다(부품명을 추정하지 않는다).
    """
    t = data["tags"].get(stock) or {}
    words = {w.lower() for s in t.get("stages", []) for w in (s.get("words") or [])}
    ev = (t.get("evidence") or "").lower()
    out = []
    for st in data["stages"]["stages"]:
        for p in st.get("parts", []):
            if any(w in words for w in [x.lower() for x in p["words"]]) or \
               any(x.lower() in ev for x in p["words"]):
                if p["key"] not in [o["key"] for o in out]:
                    out.append(p)
    return out


def summary(data, rec):
    """회사 한 곳의 화면용 묶음. reports.json 에 없으면 quarters 가 빈다."""
    st = rec["stock"]
    rep = data["reports"].get(st) or {}
    qs = sorted((rep.get("quarters") or {}).keys())
    roll = []
    for q in qs:
        d = (rep["quarters"][q] or {})
        o = d.get("orders") or {}
        s = d.get("sales") or {}
        roll.append({
            "q": q, "rcp": d.get("rcpNo"), "missing": d.get("missing"),
            "backlog": o.get("backlog"), "order_amt": o.get("order_amt"),
            "delivered": o.get("delivered"), "disclosed": o.get("disclosed"),
            "unit_seen": o.get("unit_seen"), "unit_raw": o.get("unit_raw"),
            "grain": o.get("grain"), "note": o.get("note") or "",
            "items": o.get("items") or [],
            "sales_total": s.get("total"), "export": s.get("export"),
            "domestic": s.get("domestic"), "sales_items": s.get("items") or [],
            "sales_unit_seen": s.get("unit_seen"),
            "sales_period": s.get("period_label"),
        })
    cons = sorted([c for c in data["contracts"] if c["stock"] == st],
                  key=lambda c: c.get("signed") or c.get("filed") or "",
                  reverse=True)
    return {"rec": rec, "stock": st, "rep": rep, "roll": roll,
            "kpi": rep.get("kpi") or {}, "basis": rep.get("basis"),
            "customers": rep.get("customers"), "contracts": cons,
            "tags": data["tags"].get(st) or {}, "parts": part_keys(data, st),
            "scan": data["scan"].get(st) or {},
            "peers": (data["peers"].get(st) or {}).get("mentions") or [],
            "peers_rev": data["peers_rev"].get(st) or [],
            "exposure": data["exposure"].get(st) or {}}


# ── 조각 ───────────────────────────────────────────────────

def chip(label, color=None, n=None, href=None):
    sw = '<i class="sw" style="background:%s"></i>' % E(color) if color else ""
    nn = ' <span class="n">%s</span>' % E(str(n)) if n is not None else ""
    inner = "%s%s%s" % (sw, E(label), nn)
    if href:
        return '<a class="chip" href="%s">%s</a>' % (E(href), inner)
    return '<span class="chip">%s</span>' % inner


def stage_chips(data, s, href_base=""):
    out = []
    for x in (s["tags"].get("stages") or []):
        k = x["key"]
        lab = (data["stage_by_key"].get(k) or {}).get("label", k)
        href = (href_base + "parts.html#" + k) if href_base is not None else None
        out.append(chip(lab, stage_color(k), href=href))
    return "".join(out) or '<span class="chip mut">공정 단계 미배정</span>'


def unit_flag(row):
    """fail-closed 표시 — 단위 캡션을 못 읽은 표는 값 옆에 경고를 단다(COMMON §0-2)."""
    if row.get("backlog") is None:
        return ""
    if row.get("unit_seen"):
        return ""
    return ' <span class="pill wn" title="표에서 단위 캡션을 읽지 못했습니다">단위 미확인</span>'


# ── 회사 페이지 ─────────────────────────────────────────────

def company_html(data, s):
    rec, roll, k = s["rec"], s["roll"], s["kpi"]
    name = rec["name"]
    latest = None
    for r in reversed(roll):
        if r["backlog"] is not None:
            latest = r
            break
    prev = None
    if latest:
        i = roll.index(latest)
        for r in reversed(roll[:i]):
            if r["backlog"] is not None:
                prev = r
                break
    delta = (latest["backlog"] - prev["backlog"]) if (latest and prev) else None

    # ── KPI
    kp = []
    if latest:
        kp.append('<div class="hero"><b>%s<small>억</small></b><span>수주잔고 (%s · 정기보고서 II-4)</span>%s%s</div>'
                  % (fmt_eok(latest["backlog"]), E(latest["q"]),
                     ('<i class="%s">%s%s억 직전 관측 대비</i>'
                      % ("up" if delta >= 0 else "dn", "+" if delta >= 0 else "−",
                         fmt_eok(abs(delta)))) if delta is not None else '<i class="mut">직전 관측 없음</i>',
                     unit_flag(latest)))
    else:
        why = "수주상황 표에 잔고 칸이 없거나 회사가 기재하지 않았습니다"
        if not roll:
            why = "정기보고서를 아직 수집하지 않았습니다"
        kp.append('<div class="hero"><b class="mut">미공시</b><span>수주잔고</span><i class="mut">%s</i></div>' % E(why))
    kp.append('<div><b>%s</b><span>잔고 / 연매출 배수%s</span>%s</div>'
              % (fmt_x(k.get("bal_rev_x")),
                 (" · 연매출 %s억" % fmt_eok(k.get("annual_revenue"))) if k.get("annual_revenue") else "",
                 '' if k.get("bal_rev_x") is not None else '<i class="mut">사업보고서 연매출이 있어야 계산합니다</i>'))
    if s["basis"] and s["basis"].get("primary"):
        kp.append('<div><b>%s</b><span>매출인식 시점 (주석 「수익」)</span><i class="mut">%s</i></div>'
                  % (E(basis_ko(s["basis"]["primary"])), E(s["basis"].get("quarter") or "")))
    else:
        kp.append('<div><b class="mut">—</b><span>매출인식 시점</span><i class="mut">원문에서 확인 못 함</i></div>')
    if k.get("top_customer_share") is not None:
        cu = s["customers"] or {}
        kp.append('<div><b>%.1f<small>%%</small></b><span>최대 고객 비중 (%s)</span><i class="mut">%s</i></div>'
                  % (k["top_customer_share"], E(k.get("top_customer") or ""),
                     "익명 표기" if cu.get("anonymous") else "실명 표기"))
    else:
        kp.append('<div><b class="mut">—</b><span>최대 고객 비중</span><i class="mut">주요고객 주석을 찾지 못함</i></div>')
    if k.get("export_share") is not None:
        kp.append('<div><b>%.1f<small>%%</small></b><span>수출 비중 (II-4 매출실적)</span></div>' % k["export_share"])
    if s["contracts"]:
        amt = sum(c.get("amt_mkrw") or 0 for c in s["contracts"])
        kp.append('<div><b>%s<small>억</small></b><span>공시 단일계약 누적 · %d건</span></div>'
                  % (fmt_eok(amt), len(s["contracts"])))
        cn = china_exposure(s["contracts"])
        if cn["n"]:
            kp.append('<div><b>%s</b><span>중국향 공시계약 · %d건</span>'
                      '<i class="mut">계약 금액 기준 · 매출 비중이 아닙니다%s</i></div>'
                      % (("%.0f%%" % cn["share"]) if cn["share"] is not None
                         else "%d건" % cn["n"], cn["n"],
                         (" · " + E(" · ".join(cn["regions"]))) if cn["regions"] else ""))
        else:
            kp.append('<div><b class="mut">0<small>건</small></b><span>중국향 공시계약</span>'
                      '<i class="mut">공급지역 칸에 중국이 적힌 계약이 없습니다</i></div>')

    # ── 잔고 롤포워드
    rr = []
    for r in roll:
        if r["missing"]:
            rr.append('<tr><td class="l">%s</td><td colspan="5" class="l mut">%s</td><td class="l mut">—</td></tr>'
                      % (E(r["q"]), E(r["missing"])))
            continue
        note = r["note"][:90]
        if r["disclosed"] is False:
            note = note or "수주상황 표 미공시"
        rr.append('<tr><td class="l">%s</td><td>%s</td><td>%s</td><td><b>%s</b>%s</td>'
                  '<td class="l mut">%s</td><td class="l mut">%s</td>'
                  '<td class="l"><a href="%s" target="_blank" rel="noopener noreferrer">원문</a></td></tr>'
                  % (E(r["q"]), fmt_eok(r["order_amt"]), fmt_eok(r["delivered"]),
                     fmt_eok(r["backlog"]), unit_flag(r), E(r["grain"] or ""),
                     E(note), E(DART % (r["rcp"] or "")) if r["rcp"] else "#"))
    roll_tbl = ('<div class="wrap"><table><thead><tr><th class="l">분기</th><th>수주총액</th>'
                '<th>기납품</th><th>수주잔고</th><th class="l">표 알갱이</th><th class="l">비고</th>'
                '<th class="l">출처</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(rr))

    # ── 품목별 수주(가장 최근 공시 분기)
    item_tbl = ""
    src = latest or (roll[-1] if roll else None)
    if src and src["items"]:
        ir = "".join('<tr><td class="l">%s</td><td class="l mut">%s</td><td class="l mut">%s</td>'
                     '<td>%s</td><td>%s</td><td><b>%s</b></td></tr>'
                     % (E(it.get("nm") or ""), E(it.get("sd") or ""), E(it.get("ed") or ""),
                        fmt_eok(it.get("amt")), fmt_eok(it.get("cmp")), fmt_eok(it.get("bal")))
                     for it in src["items"][:30])
        item_tbl = ('<section class="card"><h2>품목별 수주 <em>%s 수주상황 표 원문 행 · 억원</em></h2>'
                    '<div class="wrap"><table data-sortable><thead><tr><th class="l">품목</th>'
                    '<th class="l">수주일</th><th class="l">납기</th><th>수주총액</th><th>기납품</th>'
                    '<th>잔고</th></tr></thead><tbody>%s</tbody></table></div></section>'
                    % (E(src["q"]), ir))

    # ── 매출: 제품별 · 수출/내수
    sales_html = ""
    srow = None
    for r in reversed(roll):
        if r["sales_total"] or r["sales_items"]:
            srow = r
            break
    if srow:
        ch = ""
        if srow["export"] is not None or srow["domestic"] is not None:
            ch = ('<div class="grid2"><div class="panel"><h3>수출 / 내수 <em>%s</em></h3><ul>'
                  '<li><span>수출</span><b>%s억</b></li><li><span>내수</span><b>%s억</b></li>'
                  '<li><span>합계</span><b>%s억</b></li></ul></div>'
                  % (E(srow["sales_period"] or srow["q"]), fmt_eok(srow["export"]),
                     fmt_eok(srow["domestic"]), fmt_eok(srow["sales_total"])))
            pr = "".join('<li><span>%s</span><b>%s억</b></li>'
                         % (E(" · ".join(it.get("labels") or [])[:46]), fmt_eok(it.get("amt")))
                         for it in srow["sales_items"][:12])
            ch += ('<div class="panel"><h3>제품별 매출 <em>II-4 매출실적</em></h3><ul>%s</ul></div></div>'
                   % (pr or '<li><span class="mut">품목 행을 찾지 못했습니다</span></li>'))
        sales_html = ('<section class="card"><h2>매출실적 <em>정기보고서 II-4 · 억원%s</em></h2>%s</section>'
                      % ("" if srow["sales_unit_seen"] else " · <b class=\"wn\">단위 캡션 미확인</b>", ch))

    # ── 매출인식 기준(원문 인용)
    b = s["basis"] or {}
    if b.get("found") and b.get("bases"):
        quotes = "".join('<blockquote class="quote">%s<cite>%s · %s</cite></blockquote>'
                         % (E(x.get("quote") or ""), E(basis_ko(x.get("key"))),
                            E(b.get("node") or "주석 「수익」"))
                         for x in b["bases"][:2])
        basis_html = ('<section class="card"><h2>매출인식 기준 <em>%s 사업보고서 주석 — 원문 인용</em></h2>'
                      '<p class="mut" style="font-size:12px">장비는 ① 인도 ② 설치·검수(SAT) ③ 진행기준 중 하나로 인식합니다. '
                      '수주잔고가 매출로 바뀌는 <b>시차</b>가 여기서 갈립니다.</p>%s'
                      '<p class="mut" style="font-size:12px">출처 <a href="%s" target="_blank" rel="noopener noreferrer">DART 원문</a></p></section>'
                      % (E(b.get("quarter") or ""), quotes, E(DART % (b.get("rcpNo") or ""))))
    else:
        basis_html = ('<section class="card"><h2>매출인식 기준</h2>'
                      '<div class="note warn">주석 「수익」에서 인식 시점 문구를 <b>확인하지 못했습니다</b>. '
                      '반기·분기보고서에는 이 주석이 축약돼 실리지 않고, 사업보고서 주석 제목도 회사마다 다릅니다. '
                      '추정해 적지 않습니다.</div></section>')

    # ── 주요 고객
    cu = s["customers"] or {}
    if cu.get("found") and cu.get("rows"):
        den = (s["rep"].get("segment_total") or {}).get("total")
        cr = "".join('<tr><td class="l">%s%s</td><td>%s</td><td>%s</td></tr>'
                     % (E(r["label"]), ' <span class="pill">익명</span>' if r.get("anonymous") else "",
                        fmt_eok(r["amount"]),
                        ("%.1f%%" % (100.0 * r["amount"] / den)) if den else "—")
                     for r in sorted(cu["rows"], key=lambda r: -r["amount"]))
        cust_html = ('<section class="card"><h2>주요 고객 <em>매출 10%% 이상 · %s · 억원</em></h2>'
                     '<div class="wrap"><table data-sortable><thead><tr><th class="l">고객</th>'
                     '<th>매출</th><th>부문매출 대비</th></tr></thead><tbody>%s</tbody></table></div>'
                     '<p class="mut" style="font-size:12px">%s</p></section>'
                     % (E(cu.get("period") or "당기"), cr,
                        "공시가 고객을 익명(A사·거래처A)으로 적어 실제 고객명은 알 수 없습니다."
                        if cu.get("anonymous") else "공시에 적힌 표기 그대로입니다."))
    else:
        cust_html = ('<section class="card"><h2>주요 고객</h2>'
                     '<div class="note warn">「주요 고객에 대한 정보」 주석을 찾지 못했습니다 — 고객 집중도를 계산하지 않습니다.</div></section>')

    # ── 계약 공시
    con_html = ""
    if s["contracts"]:
        cr = []
        for c in s["contracts"]:
            cr.append('<tr><td class="l">%s</td><td class="l">%s</td><td data-v="%.0f">%s%s</td>'
                      '<td class="l">%s%s</td><td class="l">%s</td><td class="l">%s</td>'
                      '<td class="l"><a href="%s" target="_blank" rel="noopener noreferrer">원문</a></td></tr>'
                      % (E(c.get("signed") or c.get("filed") or ""), E((c.get("content") or "")[:52]),
                         c.get("amt_mkrw") or 0, fmt_eok(c.get("amt_mkrw")),
                         "" if c.get("unit_seen") else ' <span class="pill wn">단위 미확인</span>',
                         E(c.get("party") or "—"),
                         ' <span class="pill">익명</span>' if c.get("party_anon") else "",
                         E(c.get("region") or "—"), E(c.get("end") or "—"),
                         E(DART % c["rcp"])))
        con_html = ('<section class="card"><h2>단일판매ㆍ공급계약 공시 <em>%d건 · 억원</em></h2>'
                    '<div class="ctl"><input data-filter="#ct" type="search" placeholder="내용·상대·지역 검색"></div>'
                    '<div class="wrap tall"><table id="ct" data-sortable><thead><tr><th class="l">계약일</th>'
                    '<th class="l">계약 내용</th><th>금액(억)</th><th class="l">상대</th><th class="l">지역</th>'
                    '<th class="l">종료(납기)</th><th class="l">출처</th></tr></thead><tbody>%s</tbody></table></div></section>'
                    % (len(s["contracts"]), "".join(cr)))

    # ── 같은 공정 단계의 부품·부분품사 (역참조)
    rel_html = ""
    mykeys = {x["key"] for x in (s["tags"].get("stages") or [])}
    if mykeys and mykeys - {"parts", "service"}:
        want = set()
        for kk in mykeys:
            for p in (data["stage_by_key"].get(kk) or {}).get("parts", []):
                want.add(p["key"])
        rows = []
        for st2, t2 in data["tags"].items():
            if st2 == s["stock"]:
                continue
            if not ({x["key"] for x in (t2.get("stages") or [])} & {"parts", "service"}):
                continue
            pk = part_keys(data, st2)
            hit = [p for p in pk if p["key"] in want]
            if not hit:
                continue
            rows.append((t2, hit))
        if rows:
            tr = "".join('<tr><td class="l"><a href="../%s/index.html">%s</a></td>'
                         '<td class="l">%s</td><td class="l mut">%s</td></tr>'
                         % (E(t2["stock"]), E(t2["name"]),
                            "".join(chip(p["label"]) for p in hit[:6]),
                            E((t2.get("evidence") or "")[:60]))
                         for t2, hit in sorted(rows, key=lambda x: x[0]["name"]))
            rel_html = ('<section class="card"><h2>같은 공정의 부품·부분품사 <em>%d사</em></h2>'
                        '<div class="note info">이 회사가 만드는 장비 단계에 쓰이는 부품을 만드는 상장사입니다. '
                        '<b>납품 관계가 원문에서 확인된 것이 아니라</b> 공정 단계–부품 사전으로 이은 것입니다.</div>'
                        '<div class="wrap"><table data-sortable><thead><tr><th class="l">회사</th>'
                        '<th class="l">부품</th><th class="l">근거 문구(KIND 주요제품)</th></tr></thead>'
                        '<tbody>%s</tbody></table></div></section>' % (len(rows), tr))

    # ── 원문에 이름이 나오는 상장사 (ksemi_peers)
    peer_html = ""
    if s["peers"] or s["peers_rev"]:
        pr = []
        for m in s["peers"]:
            pr.append('<tr><td class="l">우리 본문 →</td>'
                      '<td class="l"><a href="../%s/index.html">%s</a></td>'
                      '<td class="l">%s</td><td>%d</td><td class="l mut">%s</td>'
                      '<td class="qt">%s</td></tr>'
                      % (E(m["stock"]), E(m["name"]), chip(m["kind"]), m["n"],
                         E(m.get("cue") or "—"), E(m["quote"])))
        for m in s["peers_rev"]:
            # 방향이 있는 관계는 뒤집어 적는다 — 코스텍시스템이 「주요 고객사로는 … 원익IPS」
            # 라고 쓴 것은 **원익IPS가 코스텍시스템의 고객**이라는 뜻이다.
            rev = {"고객": "우리가 그 회사의 고객"}.get(m["kind"], m["kind"])
            pr.append('<tr><td class="l">→ 우리를 적었다</td>'
                      '<td class="l"><a href="../%s/index.html">%s</a></td>'
                      '<td class="l">%s</td><td>%d</td><td class="l mut">—</td>'
                      '<td class="qt">%s</td></tr>'
                      % (E(m["stock"]), E(m["name"]), chip(rev), m["n"],
                         E(m["quote"])))
        peer_html = ('<section class="card"><h2>원문에 이름이 나오는 상장사 '
                     '<em>%d건 · 정기보고서 II절</em></h2>'
                     '<div class="note info">이 탭의 다른 회사 이름이 <b>본문에 실제로 적힌</b> 것만 '
                     '모았습니다. 관계는 문장의 단서 낱말로 나눕니다 — <b>계열·경쟁·고객</b>은 그렇게 적혀 '
                     '있다는 뜻이고, <b>업체나열</b>은 같은 목록에 있지만 경쟁사인지 전방 장비사인지 원문이 '
                     '말하지 않는 경우입니다(예: 뉴파워프라즈마의 RF 제너레이터는 그 목록의 장비에 들어갑니다). '
                     '<b>납품 계약이 아닙니다.</b></div>'
                     '<div class="wrap tall"><table data-sortable><thead><tr><th class="l">방향</th>'
                     '<th class="l">회사</th><th class="l">관계</th><th>언급</th><th class="l">단서</th>'
                     '<th class="l">원문</th></tr></thead><tbody>%s</tbody></table></div></section>'
                     % (len(s["peers"]) + len(s["peers_rev"]), "".join(pr)))

    # ── 메모리 / 비메모리·파운드리 (ksemi_exposure — 낱말이지 비중이 아니다)
    ex = s["exposure"] or {}
    expo_html = ""
    if ex.get("mem", {}).get("n") or ex.get("fnd", {}).get("n"):
        qs = []
        for side, ko in (("mem", "메모리"), ("fnd", "비메모리·파운드리")):
            for q in (ex.get(side) or {}).get("quotes", []):
                qs.append('<blockquote class="quote">%s<cite>%s · %s 「%s」</cite></blockquote>'
                          % (E(q["quote"]), E(ko), E(q.get("sec_ko") or ""), E(q.get("word") or "")))
        expo_html = ('<section class="card"><h2>메모리 · 비메모리 노출 '
                     '<em>%s II-2 주요제품 · II-4 매출실적 원문 낱말</em></h2>'
                     '<div class="chips" style="margin-bottom:10px">%s%s</div>'
                     '<div class="note info">회사가 <b>메모리 매출 비중을 공시하지는 않습니다</b>. '
                     '여기 있는 것은 그 회사의 <b>제품·매출 칸에 적힌 낱말</b>과 그 원문입니다. '
                     '산업 전망 문단(사업의 개요·기타)의 「메모리 반도체 시장은…」 같은 문장은 '
                     '그 회사의 노출이 아니므로 세지 않았습니다.</div>%s</section>'
                     % (E(ex.get("quarter") or ""),
                        chip("메모리 %d회" % ex["mem"]["n"]) if ex["mem"]["n"] else "",
                        chip("비메모리·파운드리 %d회" % ex["fnd"]["n"]) if ex["fnd"]["n"] else "",
                        "".join(qs)))

    chart = {"roll": [{"q": r["q"], "bal": r["backlog"], "amt": r["order_amt"],
                       "cmp": r["delivered"]} for r in roll]}
    dart_href = DART % (latest["rcp"] if latest and latest["rcp"]
                        else (s["rep"].get("annual_rcp") or ""))
    body = """
<div class="kpi">%s</div>
<div class="chips" style="margin-top:14px">%s%s%s</div>
<section class="card"><h2>수주잔고 롤포워드 <em>정기보고서 II-4 수주상황 · 억원 · 8분기</em></h2>
 <div class="chart"><canvas id="cRoll"></canvas></div>%s</section>
%s
%s
%s
%s
%s
%s
%s
%s
<script>const DATA=%s;</script>
<script>%s</script>
<script>
(function(){
  var el=document.getElementById('cRoll'); if(!el||!window.Chart) return;
  var R=DATA.roll.filter(function(r){return r.bal!=null||r.amt!=null;});
  if(!R.length){ el.parentNode.innerHTML='<p class="mut">수주상황 표에서 잔고를 읽지 못했습니다 — 표가 없거나 회사가 기재하지 않았습니다.</p>'; return; }
  new Chart(el,{type:'bar',data:{labels:R.map(function(r){return r.q}),datasets:[
    {label:'수주잔고',backgroundColor:'%s',data:R.map(function(r){return r.bal==null?null:Math.round(r.bal/100)})},
    {label:'기납품(누계)',backgroundColor:'%s',data:R.map(function(r){return r.cmp==null?null:Math.round(r.cmp/100)})}
  ]},options:{scales:{x:{grid:{display:false}},y:{ticks:{callback:function(v){return v.toLocaleString()}}}},
    plugins:{tooltip:{callbacks:{label:function(c){return c.dataset.label+': '+(c.parsed.y==null?'—':c.parsed.y.toLocaleString()+'억')}}}}}});
})();
</script>
<script>%s</script>
""" % ("".join(kp), stage_chips(data, s, "../"),
       chip(s["tags"].get("front_back") or "전/후공정 미판정"),
       chip(ex.get("verdict") if ex.get("verdict") and ex["verdict"] != "미확인"
            else "메모리/비메모리 미확인"),
       roll_tbl, item_tbl, sales_html, expo_html, basis_html, cust_html, con_html,
       peer_html, rel_html,
       json_for_html(chart), CHART_DEFAULTS_JS,
       stage_color(s["tags"].get("primary") or "parts"), "#5d6675", TABLE_JS)
    return page("%s 수주잔고·매출인식" % name, body, depth=1, h1=name,
                tags=(rec["stock"], rec["market"], rec["industry"]),
                nav=(("허브", "../index.html"), ("공정 흐름", "../parts.html"),
                     ("커버리지", "../coverage.html"), ("DART 원문 ↗", dart_href)),
                crumbs=(("ARGUS", "../../index.html"), ("한국반도체장비", "../index.html"),
                        (name, None)),
                scripts=("../vendor/chart.umd.min.js",),
                lead="장비사의 수주잔고는 전방 팹 CAPEX의 선행 지표입니다. 다만 잔고가 매출로 바뀌는 시점은 "
                     "회사마다 다릅니다 — 인도·설치검수(SAT)·진행기준 중 무엇인지를 주석 「수익」 원문에서 읽어 함께 싣습니다. "
                     "수주표를 공시하지 않는 회사는 '미공시'로 남깁니다.")


# ── 허브 ───────────────────────────────────────────────────

def hub_html(data, sums):
    with_bal = [s for s in sums if s["kpi"].get("backlog") is not None]
    with_bal.sort(key=lambda s: -s["kpi"]["backlog"])
    cards = []
    for s in with_bal[:24]:
        k, rec = s["kpi"], s["rec"]
        cards.append(
            '<a class="cardlink" href="%s/index.html"><div class="t"><b>%s</b><span class="code">%s</span></div>'
            '<p>%s</p><div class="chips" style="margin-top:8px">%s</div>'
            '<div class="stat"><div><b>%s</b><span>잔고(억, %s)</span></div>'
            '<div><b>%s</b><span>잔고/매출 배수</span></div>'
            '<div><b>%s</b><span>최대고객 비중</span></div></div>'
            '<div class="go">%s →</div></a>'
            % (E(rec["stock"]), E(rec["name"]), E(rec["stock"]),
               E((rec.get("product") or "")[:70]), stage_chips(data, s, ""),
               fmt_eok(k["backlog"]), E(k.get("backlog_quarter") or "—"),
               fmt_x(k.get("bal_rev_x")),
               ("%.0f%%" % k["top_customer_share"]) if k.get("top_customer_share") is not None else "—",
               E(basis_ko(k.get("basis")) or "인식기준 미확인")))

    # 공정 단계별 회사 수·잔고 합
    st_rows = []
    for stg in sorted(data["stages"]["stages"],
                      key=lambda x: (x["flow_order"] is None, x["flow_order"] or 99)):
        mem = [s for s in sums
               if stg["key"] in {x["key"] for x in (s["tags"].get("stages") or [])}]
        bals = [s["kpi"]["backlog"] for s in mem if s["kpi"].get("backlog") is not None]
        st_rows.append({"key": stg["key"], "label": stg["label"],
                        "fb": stg["front_back"], "n": len(mem),
                        "nb": len(bals), "sum": sum(bals) if bals else None,
                        "color": stage_color(stg["key"])})
    sr = "".join('<tr><td class="l"><i class="sw" style="display:inline-block;width:10px;height:10px;'
                 'border-radius:3px;background:%s;margin-right:7px;vertical-align:-1px"></i>'
                 '<a href="parts.html#%s">%s</a></td><td class="l mut">%s</td>'
                 '<td data-v="%d">%d</td><td data-v="%d">%d</td><td data-v="%.0f">%s</td></tr>'
                 % (r["color"], E(r["key"]), E(r["label"]), E(r["fb"]), r["n"], r["n"],
                    r["nb"], r["nb"], r["sum"] or 0, fmt_eok(r["sum"]))
                 for r in st_rows)
    stage_tbl = ('<div class="wrap"><table data-sortable><thead><tr><th class="l">공정 단계</th>'
                 '<th class="l">전/후공정</th><th>회사</th><th>잔고 공시</th><th>잔고 합(억)</th>'
                 '</tr></thead><tbody>%s</tbody></table></div>' % sr)

    # 최근 대형 수주
    mem_stocks = {s["stock"] for s in sums}
    big = sorted([c for c in data["contracts"]
                  if c["stock"] in mem_stocks and c.get("amt_mkrw")],
                 key=lambda c: (c.get("signed") or c.get("filed") or ""), reverse=True)[:20]
    br = "".join('<tr><td class="l">%s</td><td class="l"><a href="%s/index.html">%s</a></td>'
                 '<td class="l">%s</td><td data-v="%.0f">%s</td><td class="l">%s%s</td>'
                 '<td class="l">%s</td><td class="l"><a href="%s" target="_blank" rel="noopener noreferrer">원문</a></td></tr>'
                 % (E(c.get("signed") or c.get("filed") or ""), E(c["stock"]), E(c["name"]),
                    E((c.get("content") or "")[:44]), c.get("amt_mkrw") or 0,
                    fmt_eok(c.get("amt_mkrw")), E(c.get("party") or "—"),
                    ' <span class="pill">익명</span>' if c.get("party_anon") else "",
                    E(c.get("region") or "—"), E(DART % c["rcp"]))
                 for c in big)
    big_tbl = ('<div class="wrap"><table data-sortable><thead><tr><th class="l">계약일</th>'
               '<th class="l">회사</th><th class="l">내용</th><th>금액(억)</th><th class="l">상대</th>'
               '<th class="l">지역</th><th class="l">출처</th></tr></thead><tbody>%s</tbody></table></div>'
               % br)

    n_basis = sum(1 for s in sums if (s["basis"] or {}).get("primary"))
    n_cust = sum(1 for s in sums if s["kpi"].get("top_customer_share") is not None)
    bsum = sum(s["kpi"]["backlog"] for s in with_bal)
    basis_mix = collections.Counter(s["kpi"].get("basis") for s in sums
                                    if s["kpi"].get("basis"))
    bchips = "".join(chip(basis_ko(kk), None, n) for kk, n in basis_mix.most_common())
    expo_mix = collections.Counter((s["exposure"] or {}).get("verdict") or "미확인"
                                   for s in sums)
    echips = "".join(chip(kk, None, n) for kk, n in
                     sorted(expo_mix.items(), key=lambda x: (x[0] == "미확인", -x[1])))
    pending = len(sums) - len(data["reports"])
    note = ""
    if pending > 0:
        note = ('<div class="note info">%d개 종목은 정기보고서를 아직 수집하지 않았습니다 — '
                '수집이 끝나면 카드와 합계가 늘어납니다.</div>' % pending)

    body = """
<div class="kpi">
 <div class="hero"><b>%s<small>억</small></b><span>수주잔고 합 · %d사</span><i class="mut">II-4 수주상황을 공시한 회사만</i></div>
 <div><b>%d</b><span>탭 구성원(④ 편입 ∪ 지정)</span></div>
 <div><b>%d</b><span>매출인식 기준 원문 확인</span></div>
 <div><b>%d</b><span>주요고객 주석 확인</span></div>
 <div><b>%d</b><span>단일판매ㆍ공급계약 공시</span></div>
 <div><b>%d</b><span>중국향 계약을 공시한 회사</span><i class="mut">공급지역 칸 기준 · 매출 비중이 아닙니다</i></div>
</div>
%s
<div class="chips" style="margin-top:12px">%s</div>
<div class="chips" style="margin-top:8px">%s</div>
<p class="mut" style="font-size:12px;margin-top:6px">메모리·비메모리 표시는 II-2 주요제품·II-4 매출실적 절에 적힌 <b>낱말</b>입니다 — 매출 비중이 아닙니다(산업 전망 문단은 세지 않습니다).</p>
<h2 class="sec">수주잔고 상위<span>잔고 · 잔고/매출 배수 · 매출인식 기준 · 최대고객 비중</span></h2>
<div class="cards">%s</div>
<h2 class="sec">공정 단계<span>단계를 누르면 팹 공정 흐름 인포그래픽으로</span></h2>
%s
<h2 class="sec">최근 대형 수주<span>단일판매ㆍ공급계약체결 공시 최신 20건</span></h2>
%s
<div class="cards" style="margin-top:18px">
 <a class="cardlink" href="parts.html"><div class="t"><b>🔧 팹 공정 흐름</b></div><p>웨이퍼 투입부터 패키징까지 단계를 누르면 그 단계 장비를 만드는 상장사, 한 번 더 들어가면 부품과 부품사로 갑니다.</p><div class="go">인포그래픽 →</div></a>
 <a class="cardlink" href="coverage.html"><div class="t"><b>커버리지</b></div><p>모집단 %d종목 전수와 편입 근거, ④ 본문 탐색 승격·제외, 수주표 미공시 사유.</p><div class="go">커버리지 →</div></a>
</div>
<script>%s</script>
""" % (fmt_eok(bsum), len(with_bal), len(sums), n_basis, n_cust,
       len([c for c in data["contracts"] if c["stock"] in mem_stocks]),
       len({c["stock"] for c in data["contracts"]
            if c["stock"] in mem_stocks and c.get("region_cn")}),
       note, bchips, echips, "".join(cards), stage_tbl, big_tbl, len(data["uni"]), TABLE_JS)
    return page("한국반도체장비 — 수주잔고·매출인식·고객집중", body, depth=0,
                h1="🔧 한국반도체장비",
                nav=(("← ARGUS", "../index.html"), ("🏗 한국건설", "../kce/index.html"),
                     ("⚓ 한국조선", "../kship/index.html")),
                lead="장비사는 수주잔고를 공시하는 회사가 많습니다 — 잔고는 전방 팹 CAPEX의 선행 지표입니다. "
                     "여기서는 잔고와 함께 그 잔고가 매출로 바뀌는 시점(인도·설치검수·진행기준), 고객 집중도, "
                     "수출 노출을 정기보고서 원문에서 읽습니다. 공시하지 않는 회사는 '미공시'로 남깁니다.")


# ── 커버리지 ───────────────────────────────────────────────

def coverage_html(data, sums):
    by_stock = {s["stock"]: s for s in sums}
    rows = []
    for r in data["uni"]:
        st = r["stock"]
        sc = data["scan"].get(st) or {}
        v = sc.get("verdict") or ("지정" if r.get("source") == "지정" else "미판정")
        s = by_stock.get(st)
        if s is None:
            status, cls, link = "탭 제외", "tx3", E(r["name"])
        elif not s["roll"]:
            status, cls = "편입 · 정기보고서 미수집", "wn"
            link = E(r["name"])
        elif s["kpi"].get("backlog") is not None:
            status, cls = "수록 · 잔고 %s억 (%s)" % (fmt_eok(s["kpi"]["backlog"]),
                                                 s["kpi"].get("backlog_quarter") or ""), "up"
            link = '<a href="%s/index.html">%s</a>' % (E(st), E(r["name"]))
        else:
            why = "수주상황 표 미공시"
            dis = [x for x in s["roll"] if x["disclosed"]]
            if dis:
                why = "수주표는 있으나 잔고 칸 미기재"
            status, cls = "수록 · " + why, "wn"
            link = '<a href="%s/index.html">%s</a>' % (E(st), E(r["name"]))
        tg = data["tags"].get(st) or {}
        stg = " ".join((data["stage_by_key"].get(x["key"]) or {}).get("label", x["key"])
                       for x in (tg.get("stages") or [])[:3])
        rows.append('<tr><td class="l">%s</td><td class="mut">%s</td><td class="l mut">%s</td>'
                    '<td class="l">%s</td><td class="l"><b class="%s">%s</b></td>'
                    '<td class="l mut">%s</td><td class="l mut">%s</td></tr>'
                    % (link, E(st), E((r.get("industry") or "")[:22]), E(v), cls, E(status),
                       E(stg), E((sc.get("reason") or r.get("product") or "")[:70])))

    sm = data["scan_meta"]
    dist = sm.get("dist") or {}
    rej = [r for r in sm.get("rows", []) if r.get("verdict") in ("배제", "보류")]
    rej.sort(key=lambda r: -(r.get("scores") or {}).get("equip", 0))
    rj = "".join('<tr><td class="l">%s</td><td class="mut">%s</td><td class="l">%s</td>'
                 '<td class="l mut">%s</td><td>%d</td><td>%d</td><td>%d</td>'
                 '<td class="l mut">%s</td></tr>'
                 % (E(r["name"]), E(r["stock"]), E(r["verdict"]),
                    E((r.get("industry") or "")[:20]),
                    (r.get("scores") or {}).get("equip", 0),
                    (r.get("scores") or {}).get("device", 0),
                    (r.get("scores") or {}).get("material", 0),
                    E((r.get("reason") or "")[:80]))
                 for r in rej[:120])

    # 사람이 원문을 열고 다시 판정한 행(ksemi_scan.HOLD_CALLS)
    man = [r for r in sm.get("rows", []) if r.get("manual")]
    man.sort(key=lambda r: (r["verdict"], r["name"]))
    mn = "".join('<tr><td class="l">%s</td><td class="mut">%s</td><td class="l">%s</td>'
                 '<td class="l mut">%s</td><td class="l">%s</td><td class="qt">%s</td></tr>'
                 % (E(r["name"]), E(r["stock"]), E(r["verdict"]), E(r.get("rule_verdict") or ""),
                    E(re.sub(r"^재판정 — ", "", r.get("reason") or "")), E(r.get("quote") or ""))
                 for r in man)

    # ⑤ 원문 언급 지도(ksemi_peers)
    pm = data["peers_meta"]
    pe = []
    for r in pm.get("rows", []):
        for m in r["mentions"]:
            pe.append('<tr><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td>'
                      '<td>%d</td><td class="l mut">%s</td><td class="qt">%s</td></tr>'
                      % (E(r["name"]), E(m["name"]), chip(m["kind"]), m["n"],
                         E(m.get("cue") or "—"), E(m["quote"])))

    no_disc = [s for s in sums if s["roll"] and s["kpi"].get("backlog") is None]
    nd = "".join('<tr><td class="l"><a href="%s/index.html">%s</a></td><td class="mut">%s</td>'
                 '<td class="l mut">%s</td></tr>'
                 % (E(s["stock"]), E(s["rec"]["name"]), E(s["stock"]),
                    E((([x["note"] for x in s["roll"] if x["note"]] or
                        ["수주상황 표를 찾지 못했거나 회사가 잔고를 기재하지 않았습니다"])[0])[:100]))
                 for s in sorted(no_disc, key=lambda s: s["rec"]["name"]))

    body = """
<section class="card" style="margin-top:0"><h2>모집단 규칙 <em>네 겹 · 재현 가능</em></h2>
<p style="font-size:12px;color:var(--tx2);line-height:1.8">
① KIND 업종 — 스펙이 적은 <b>반도체 제조용 기계 제조업</b>은 KIND에 <b>없습니다</b>(2026-09-11 실측, 전체 2,759행).
KIND 업종은 그보다 굵어서 장비사는 <code>특수 목적용 기계 제조업</code>, 부품사는 <code>반도체 제조업</code>·
<code>전자부품 제조업</code>·<code>측정, 시험, 항해, 제어 및 기타 정밀기기 제조업</code>·<code>기타 비금속 광물제품 제조업</code> 등으로
흩어져 있습니다 — 업종 단독 필터는 불가능합니다. ②&nbsp;주요제품 문구의 장비·공정 어휘(증착·식각·세정·이온주입·계측·본더·핸들러·프로브·챔버·정전척·쿼츠…)
· ③&nbsp;스펙 <b>지정</b> 종목(종목코드는 KIND 조회로 확인) · ④&nbsp;정기보고서 II절 <b>본문 탐색</b>으로 승격/배제.
<br>④의 판정 기준: <b>%s</b>
<br>'반도체'는 너무 넓은 낱말이라 소자·설계(팹리스)·유통·소재는 점수로 걸러 냅니다 — 고객 업종(소자사 자신)은 이 탭의 대상이 아닙니다.</p>
<div class="chips">%s</div></section>

<section class="card"><h2>종목별 상태 <em>모집단 %d종목 전수</em></h2>
<div class="ctl"><input data-filter="#cv" type="search" placeholder="회사·업종·사유 검색"></div>
<div class="wrap tall"><table id="cv" data-sortable><thead><tr><th class="l">회사</th><th>종목코드</th>
<th class="l">업종</th><th class="l">판정</th><th class="l">수록 상태</th><th class="l">공정 단계</th>
<th class="l">사유·제품</th></tr></thead><tbody>%s</tbody></table></div></section>

<section class="card"><h2>수주표 미공시 <em>%d사 — 편입했지만 잔고를 싣지 못한 회사</em></h2>
<div class="note info">잔고가 없다고 빼지 않습니다. 한미반도체처럼 <i>"계약 내용은 고객의 투자 정보 등이 노출될 수 있어
공시된 내용 외에 기재하지 않았습니다"</i> 라고 적고 공시된 단일계약만 싣는 회사가 실제로 있습니다 — 그 사실 자체가 정보입니다.</div>
<div class="wrap"><table data-sortable><thead><tr><th class="l">회사</th><th>종목코드</th>
<th class="l">원문 사유</th></tr></thead><tbody>%s</tbody></table></div></section>

<section class="card"><h2>④ 본문 탐색 — 배제·보류 <em>후보 %d사 중 상위 %d사</em></h2>
<p style="font-size:12px;color:var(--tx2)">제외한 회사도 근거를 남깁니다. 점수는 정기보고서 II절 본문의 낱말 횟수입니다 —
장비 점수가 소자·소재 점수에 눌리면 배제합니다. 경계에 걸려 <b>보류</b>가 된 회사는 아래 ④-1에서 원문을 열어
다시 판정했습니다 — 지금 보류로 남은 회사는 없습니다.</p>
<details><summary style="cursor:pointer;font-size:12px">배제·보류 목록 펼치기</summary>
<div class="wrap tall"><table data-sortable><thead><tr><th class="l">회사</th><th>종목코드</th>
<th class="l">판정</th><th class="l">업종</th><th>장비</th><th>소자</th><th>소재</th>
<th class="l">사유</th></tr></thead><tbody>%s</tbody></table></div></details></section>

<section class="card"><h2>④-1 보류 재판정 <em>%d사 — 사람이 원문을 열고 내린 판정</em></h2>
<div class="note info">낱말 점수가 경계에 걸린 회사는 규칙으로 가르지 않고 <b>II-2 주요제품 매출 구성표</b>를 직접 읽어
판정했습니다. 규칙이 뭐라고 했는지(<b>규칙 판정</b>)를 지우지 않고 같이 싣습니다 — 규칙과 사람이 어긋나는 곳이
다음에 고칠 곳입니다. 표는 <code>tools/ksemi_scan.py</code> 의 <code>HOLD_CALLS</code> 에 있습니다.</div>
<div class="wrap"><table data-sortable><thead><tr><th class="l">회사</th><th>종목코드</th>
<th class="l">재판정</th><th class="l">규칙 판정</th><th class="l">사유</th><th class="l">원문</th></tr></thead>
<tbody>%s</tbody></table></div></section>

<section class="card"><h2>⑤ 원문 언급 지도 <em>%d사 · %d간선 — 정기보고서 II절</em></h2>
<div class="note info">회사들이 <b>서로의 이름을 본문에 적은 것</b>만 모았습니다(<code>tools/ksemi_peers.py</code>).
관계는 문장의 단서 낱말로 나눕니다 — <b>업체나열</b>은 같은 목록에 있지만 경쟁사인지 전방 장비사인지 원문이 말하지
않는 경우입니다. <b>납품 계약이 아닙니다.</b> DART를 다시 두드리지 않고 스캔 캐시만 읽으므로 언제든 다시 만들 수 있습니다.</div>
<div class="ctl"><input data-filter="#pm" type="search" placeholder="회사·관계·원문 검색"></div>
<div class="wrap tall"><table id="pm" data-sortable><thead><tr><th class="l">적은 회사</th>
<th class="l">적힌 회사</th><th class="l">관계</th><th>언급</th><th class="l">단서</th>
<th class="l">원문</th></tr></thead><tbody>%s</tbody></table></div></section>
<script>%s</script>
""" % (E(sm.get("rule", "")),
       "".join(chip(k, None, v) for k, v in sorted(dist.items(), key=lambda kv: -kv[1])),
       len(data["uni"]), "".join(rows), len(no_disc),
       nd or '<tr><td colspan="3" class="l mut">해당 없음</td></tr>',
       sm.get("n", 0), min(120, len(rej)), rj,
       len(man), mn or '<tr><td colspan="6" class="l mut">해당 없음</td></tr>',
       pm.get("n", 0), pm.get("n_edges", 0),
       "".join(pe) or '<tr><td colspan="6" class="l mut">언급 없음</td></tr>', TABLE_JS)
    return page("한국반도체장비 커버리지", body, depth=0, h1="커버리지",
                nav=(("허브", "index.html"), ("공정 흐름", "parts.html"),
                     ("← ARGUS", "../index.html")),
                crumbs=(("ARGUS", "../index.html"), ("한국반도체장비", "index.html"),
                        ("커버리지", None)))


# ── 실행 ───────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="허브·커버리지까지")
    ap.add_argument("--only", help="종목코드 쉼표 구분")
    a = ap.parse_args()
    data = load_all()
    sums = [summary(data, r) for r in members(data)]
    only = set(a.only.split(",")) if a.only else None
    n = 0
    for s in sums:
        if only and s["stock"] not in only:
            continue
        d = os.path.join(KSEMI, s["stock"])
        os.makedirs(d, exist_ok=True)
        atomic_write(os.path.join(d, "index.html"), company_html(data, s))
        n += 1
        print("%s %-16s 분기 %d · 잔고 %s · 계약 %d · 인식 %s"
              % (s["stock"], s["rec"]["name"][:16], len(s["roll"]),
                 fmt_eok(s["kpi"].get("backlog")), len(s["contracts"]),
                 basis_ko((s["basis"] or {}).get("primary")) or "—"))
    if a.all:
        atomic_write(os.path.join(KSEMI, "index.html"), hub_html(data, sums))
        atomic_write(os.path.join(KSEMI, "coverage.html"), coverage_html(data, sums))
        print("index.html · coverage.html")
    print("— 회사 페이지 %d · 잔고 수록 %d · 정기보고서 수집 %d/%d"
          % (n, sum(1 for s in sums if s["kpi"].get("backlog") is not None),
             len(data["reports"]), len(sums)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
