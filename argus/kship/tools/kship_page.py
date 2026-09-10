#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_page — 한국조선 탭의 페이지를 만든다.

  index.html              허브 — 조선사 카드(수주잔고·선종 구성·헤지) + 기자재 진입 + 인포그래픽 진입
  coverage.html           모집단 41종목의 역할·수록 상태·근거
  <조선사>/index.html      선종별 수주(척·금액) · 선표(인도 스케줄) · 부문 롤포워드 · 매출 · 환노출/헤지 ·
                          반복건조(시리즈) · 이 조선사에 납품하는 기자재사(역방향)
  parts.html              선박 단면 인포그래픽 — 부품 영역 클릭 → 담당 기자재사 → 회사 페이지
  <기자재사>/index.html    부품 분류 · 납품 조선사(근거 등급) · 제품·매출 · 같은 부품 다른 회사

원칙(건설 탭과 같다): 원문이 지지하는 것만 싣고, 추정은 `est`·근거 등급으로 화면에 표시한다.
척당 계약 공시의 계약상대는 대부분 익명이며, 기자재사→조선사 연결은 '본문 언급' 수준이 많다 —
그 한계를 숨기지 않는다. 스크립트 안전: 임베드 JSON은 json_for_html 로만 넣는다.

    python3 kship_page.py --all
"""
import argparse
import collections
import datetime
import json
import os
import re
import sys

from kship_lib import (ASSETS, CHART_DEFAULTS_JS, E, KSHIP, TABLE_JS, atomic_write, fmt_eok,
                       fmt_musd, fmt_n, json_for_html, load_asset, page, palette, q_next,
                       slot_color)
from kship_universe import load as load_universe

YARDS_CACHE = os.path.join(ASSETS, "yards_cache")
TYPE_ORDER = ["CONT", "LNGC", "VLCC", "PC", "VLGC", "OFFSH", "NAVAL", "BULK", "PCTC", "OTHER"]


# ── 데이터 로드 ─────────────────────────────────────────────

def load_all():
    uni = load_universe()
    types = load_asset("ship_types.json")
    tax = load_asset("parts_taxonomy.json")
    svg = load_asset("svg_regions.json")
    contracts = load_asset("contracts.json")["rows"] if os.path.exists(os.path.join(ASSETS, "contracts.json")) else []
    suppliers = load_asset("suppliers.json") if os.path.exists(os.path.join(ASSETS, "suppliers.json")) else {"cos": []}
    yards = {}
    for r in uni:
        if r["role"] != "yard":
            continue
        d = os.path.join(YARDS_CACHE, r["stock"])
        qs = {}
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    x = json.load(fh)
                if x.get("ok"):
                    qs[x["quarter"]] = x
        yards[r["stock"]] = {"rec": r, "q": qs}
    return {"uni": uni, "types": types, "tax": tax, "svg": svg, "contracts": contracts,
            "suppliers": suppliers, "yards": yards}


def type_meta(types):
    m = {}
    for t in types["types"]:
        m[t["id"]] = dict(t, color=slot_color(t["color_slot"]))
    m["OTHER"] = {"id": "OTHER", "ko": "비조선(공사·기자재)", "color": "#5d6675", "color_slot": None}
    return m


# ── 조선사 집계 ─────────────────────────────────────────────

def _q_of_date(s):
    m = re.match(r"(\d{4})-(\d{2})", s or "")
    if not m:
        return None
    return "%sQ%d" % (m.group(1), (int(m.group(2)) - 1) // 3 + 1)


def series_groups(cons):
    """반복건조 추정: 같은 조선사·선종·상대 표기·지역이고 수주일이 180일 안이면 한 시리즈.
    공시에 시리즈 정보가 없으므로 **추정**이다(est=True). 옵션 언급이 있으면 표시."""
    groups = []
    for c in sorted(cons, key=lambda c: (c["stock"], c["type"] or "", c["party"], c["signed"])):
        if c["type"] in (None, "OTHER"):
            continue
        d = datetime.date.fromisoformat(c["signed"][:10]) if re.match(r"\d{4}-\d{2}-\d{2}", c["signed"] or "") else None
        placed = False
        for g in groups:
            if g["stock"] == c["stock"] and g["type"] == c["type"] and g["party"] == c["party"] and g["region"] == c["region"] and d and g["last"] and (d - g["last"]).days <= 180:
                g["items"].append(c["rcp"]); g["ships"] += (c["ships"] or 0); g["amt"] += (c["amt_krw_m"] or 0)
                g["last"] = d; g["option"] = g["option"] or c.get("option_hint", False); placed = True
                break
        if not placed:
            groups.append({"stock": c["stock"], "type": c["type"], "party": c["party"], "region": c["region"],
                           "items": [c["rcp"]], "ships": c["ships"] or 0, "amt": c["amt_krw_m"] or 0,
                           "first": d, "last": d, "option": c.get("option_hint", False)})
    return [g for g in groups if len(g["items"]) >= 2 or g["ships"] >= 4]


def yard_summary(stock, data):
    y = data["yards"][stock]
    qs = sorted(y["q"])
    latest = y["q"][qs[-1]] if qs else None
    cons = [c for c in data["contracts"] if c["stock"] == stock]
    ships = [c for c in cons if c["type"] not in (None, "OTHER")]
    by_type = collections.OrderedDict()
    for t in TYPE_ORDER:
        rows = [c for c in ships if c["type"] == t]
        if rows:
            by_type[t] = {"n": len(rows), "ships": sum(c["ships"] or 0 for c in rows),
                          "amt": sum(c["amt_krw_m"] or 0 for c in rows)}
    # 선표: 계약기간 종료일(마지막 호선 인도 예정)을 분기로
    deliv = collections.Counter()
    deliv_amt = collections.Counter()
    for c in ships:
        q = _q_of_date(c["end"])
        if q:
            deliv[(q, c["type"])] += (c["ships"] or 0)
            deliv_amt[(q, c["type"])] += (c["amt_krw_m"] or 0)
    roll = []
    for q in qs:
        o = y["q"][q]["orders"]
        tot = [r for r in o["rows"] if r["total"]]
        row = tot[0] if tot else None
        segs = [r for r in o["rows"] if not r["total"]]
        roll.append({"q": q, "closing": (row["closing"] if row else sum((r["closing"] or 0) for r in segs)),
                     "new": (row["new"] if row else None), "delivered": (row["delivered"] if row else None),
                     "opening": (row["opening"] if row else None), "cur": o["cur"],
                     "segs": [{"seg": r["seg"], "closing": r["closing"], "new": r["new"], "delivered": r["delivered"]} for r in segs],
                     "rcp": y["q"][q]["rcp"]})
    hedge = (latest or {}).get("hedge") or None
    fx = (latest or {}).get("fx") or None
    rev = (latest or {}).get("revenue") or None
    return {"stock": stock, "rec": y["rec"], "latest_q": (qs[-1] if qs else None), "roll": roll,
            "by_type": by_type, "contracts": ships, "other": [c for c in cons if c["type"] == "OTHER"],
            "unresolved": [c for c in cons if c["type"] is None],
            "deliv": deliv, "deliv_amt": deliv_amt, "series": series_groups(ships),
            "hedge": hedge, "fx": fx, "revenue": rev,
            "anon_ratio": (sum(1 for c in ships if c["party_anon"]) / len(ships) if ships else None)}


# ── 화면 조각 ───────────────────────────────────────────────

def _chip(label, color=None, n=None, href=None, on=False):
    sw = '<i class="sw" style="background:%s"></i>' % E(color) if color else ""
    nn = ' <span class="n">%s</span>' % E(str(n)) if n is not None else ""
    inner = "%s%s%s" % (sw, E(label), nn)
    if href:
        return '<a class="chip%s" href="%s">%s</a>' % (" on" if on else "", E(href), inner)
    return '<span class="chip%s">%s</span>' % (" on" if on else "", inner)


def yard_html(s, data):
    tm = type_meta(data["types"])
    rec, roll = s["rec"], s["roll"]
    latest = roll[-1] if roll else None
    closing = latest["closing"] if latest else None
    prev = roll[-2]["closing"] if len(roll) > 1 else None
    delta = (closing - prev) if (closing is not None and prev is not None) else None
    ships_total = sum(v["ships"] for v in s["by_type"].values())
    amt_total = sum(v["amt"] for v in s["by_type"].values())
    hedge = s["hedge"]
    usd_sell = hedge.get("usd_sell_m") if hedge else None
    rate = (hedge or {}).get("avg_rate")
    # 헤지 비율: 통화선도 매도(USD) ÷ 수주잔고(원화)를 그 회사 공시 평균약정환율로 나눈 값.
    # 환율이 공시에 없으면 계산하지 않는다(다른 회사 환율을 빌리면 추정이 된다).
    hedge_ratio = None
    if usd_sell and closing and rate:
        hedge_ratio = 100.0 * usd_sell / (closing / rate)
    dart = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=%s" % latest["rcp"] if latest else "https://dart.fss.or.kr"

    kpi = ['<div class="hero"><b>%s<small>억</small></b><span>수주잔고(원화, 정기보고서 %s)</span>%s</div>' % (
        fmt_eok(closing), E(s["latest_q"] or "—"),
        ('<i class="%s">%s%s억 전분기 대비</i>' % ("up" if delta >= 0 else "dn", "+" if delta >= 0 else "−", fmt_eok(abs(delta)))) if delta is not None else '<i class="mut">직전 관측 없음</i>')]
    kpi.append('<div><b>%s<small>척</small></b><span>척당 계약 공시 누적(2024~) · %d건</span></div>' % (fmt_n(ships_total), len(s["contracts"])))
    kpi.append('<div><b>%s<small>억</small></b><span>척당 계약 금액 합(원화 공시)</span></div>' % fmt_eok(amt_total))
    if latest and latest.get("new") is not None:
        kpi.append('<div><b>%s<small>억</small></b><span>신규증감(반기·환율효과 포함)</span></div>' % fmt_eok(latest["new"]))
    if latest and latest.get("delivered") is not None:
        kpi.append('<div><b>%s<small>억</small></b><span>기납품(매출인식)</span></div>' % fmt_eok(latest["delivered"]))
    if usd_sell:
        kpi.append('<div><b>%s<small>M$</small></b><span>통화선도 매도 명목액%s</span>%s</div>' % (
            fmt_musd(usd_sell), " · 평균약정 %s원" % fmt_n(rate) if rate else "",
            ('<i class="mut">잔고 대비 약 %.0f%%</i>' % hedge_ratio) if hedge_ratio else '<i class="mut">환율 미공시 — 비율 미계산</i>'))
    else:
        kpi.append('<div><b class="mut">—</b><span>통화선도 명목액</span><i class="mut">헤지 공시를 찾지 못함</i></div>')
    if s["anon_ratio"] is not None:
        kpi.append('<div><b>%.0f<small>%%</small></b><span>계약상대 익명 비율(척당 공시)</span></div>' % (100 * s["anon_ratio"]))

    # 선종 구성(척·금액) 표 + 막대
    tr = []
    for t, v in s["by_type"].items():
        m = tm.get(t, tm["OTHER"])
        tr.append('<tr><td class="l"><i class="sw" style="display:inline-block;width:10px;height:10px;border-radius:3px;background:%s;margin-right:7px;vertical-align:-1px"></i>%s</td>'
                  '<td data-v="%d">%d</td><td data-v="%d">%d</td><td data-v="%.0f">%s</td><td data-v="%.0f">%s</td></tr>'
                  % (m["color"], E(m["ko"]), v["n"], v["n"], v["ships"], v["ships"], v["amt"], fmt_eok(v["amt"]),
                     (v["amt"] / v["ships"] if v["ships"] else 0), fmt_eok(v["amt"] / v["ships"]) if v["ships"] else "—"))
    type_table = ('<div class="wrap"><table data-sortable><thead><tr><th class="l">선종</th><th>계약</th><th>척</th>'
                  '<th>금액(억)</th><th>척당(억)</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(tr))

    # 선표(인도 스케줄) 타임라인: 분기 × 선종 척수
    qs = sorted({q for (q, _) in s["deliv"]})
    tl = ""
    if qs:
        q0 = qs[0]
        qs_all = [q0]
        while qs_all[-1] < qs[-1] and len(qs_all) < 40:
            qs_all.append(q_next(qs_all[-1]))
        head = "".join('<span style="left:%.2f%%">%s</span>' % (100.0 * (i + 0.5) / len(qs_all), E(q)) for i, q in enumerate(qs_all) if q.endswith("Q1") or len(qs_all) <= 12)
        rows = []
        for t in TYPE_ORDER:
            cells = [(q, s["deliv"].get((q, t), 0)) for q in qs_all]
            if not any(n for _, n in cells):
                continue
            m = tm.get(t, tm["OTHER"])
            bars = ""
            for i, (q, n) in enumerate(cells):
                if not n:
                    continue
                left = 100.0 * i / len(qs_all)
                w = 100.0 / len(qs_all)
                bars += ('<div class="bar2" style="left:%.2f%%;width:%.2f%%;background:%s" title="%s %s %d척 · %s억" data-q="%s" data-t="%s"></div>'
                         '<span style="position:absolute;left:%.2f%%;top:5px;font-size:10px;color:var(--tx)">%d</span>'
                         % (left, w - 0.3, m["color"], E(q), E(m["ko"]), n, fmt_eok(s["deliv_amt"].get((q, t), 0)), E(q), E(t), left + 0.4, n))
            rows.append('<div class="row"><div class="lbl">%s</div><div class="lane">%s</div></div>' % (E(m["ko"]), bars))
        now_q = _q_of_date(datetime.date.today().isoformat())
        now_pos = ""
        if now_q in qs_all:
            now_pos = '<div class="tick now" style="left:%.2f%%"></div>' % (100.0 * qs_all.index(now_q) / len(qs_all))
        tl = ('<div class="tl"><div class="head"><div></div><div class="lane" style="position:relative">%s</div></div>%s</div>'
              '<div class="legend"><span>막대의 숫자 = 그 분기 인도 예정 척수(계약기간 종료일 기준 — 시리즈 계약은 마지막 호선 기준이라 실제 인도는 앞당겨 분포한다)</span></div>'
              % (head, "".join(rows)))
    else:
        tl = '<p class="mut">척당 계약 공시에서 인도 예정일을 찾지 못했습니다.</p>'

    # 부문 롤포워드 표
    rr = []
    for r in roll:
        rr.append("<tr><td class=\"l\">%s</td><td>%s</td><td>%s</td><td>%s</td><td><b>%s</b></td><td class=\"l mut\">%s</td>"
                  "<td class=\"l\"><a href=\"https://dart.fss.or.kr/dsaf001/main.do?rcpNo=%s\" target=\"_blank\" rel=\"noopener noreferrer\">원문</a></td></tr>"
                  % (E(r["q"]), fmt_eok(r["opening"]), fmt_eok(r["new"]), fmt_eok(r["delivered"]), fmt_eok(r["closing"]),
                     E(" · ".join("%s %s" % (x["seg"], fmt_eok(x["closing"])) for x in r["segs"])), E(r["rcp"])))
    roll_table = ('<div class="wrap"><table><thead><tr><th class="l">분기</th><th>기초</th><th>신규증감</th><th>기납품</th><th>기말잔고</th>'
                  '<th class="l">부문별 기말(억)</th><th class="l">출처</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(rr))

    # 매출
    rev_html = ""
    if s["revenue"]:
        rv = s["revenue"]
        rows = "".join("<tr><td class=\"l\">%s</td><td class=\"l\">%s</td>%s</tr>" % (E(r["seg"] or ""), E(r["kind"]), "".join("<td>%s</td>" % fmt_eok(v) for v in r["vals"])) for r in rv["rows"])
        rev_html = ('<section class="card"><h2>매출실적 <em>사업부문 × 수출/내수 · 억원 · 정기보고서 II-4</em></h2><div class="wrap"><table><thead><tr><th class="l">부문</th><th class="l">구분</th>%s</tr></thead><tbody>%s</tbody></table></div></section>'
                    % ("".join("<th>%s</th>" % E(c) for c in rv["period_cols"]), rows))

    # 환노출·헤지
    fx_html = ""
    if s["fx"] or hedge:
        parts = []
        if s["fx"] and s["fx"].get("contract_asset"):
            ca = s["fx"]["contract_asset"]
            parts.append('<li><span>USD 계약자산(헤지 전 노출)</span><b>%s억</b></li>' % fmt_eok(ca[0]))
        if s["fx"] and s["fx"].get("assets"):
            parts.append('<li><span>외화 자산계(USD열)</span><b>%s억</b></li>' % fmt_eok(s["fx"]["assets"][0]))
        if s["fx"] and s["fx"].get("liabilities"):
            parts.append('<li><span>외화 부채계(USD열)</span><b>%s억</b></li>' % fmt_eok(s["fx"]["liabilities"][0]))
        if hedge:
            for it in hedge.get("items", [])[:8]:
                parts.append('<li><span>%s %s%s%s</span><b>%s M</b></li>' % (E(it["ccy"]), E(it["side"]), (" · " + E(it["hedge"])) if it["hedge"] else "", (" · " + E(it["instr"])) if it["instr"] != "선도" else "", fmt_musd(it["amt_m"])))
            if hedge.get("avg_maturity"):
                parts.append('<li><span>평균만기</span><b>%s</b></li>' % E(", ".join(hedge["avg_maturity"][:3])))
            if hedge.get("contracts"):
                parts.append('<li><span>계약건수</span><b>%s</b></li>' % E(", ".join(str(int(c)) for c in hedge["contracts"] if c)))
        fx_html = ('<section class="card"><h2>환율·환헤지 <em>「위험관리 및 파생거래」·「파생금융상품」 주석 · 헤지 전 노출과 통화선도 명목액</em></h2>'
                   '<div class="grid2"><div class="panel"><h3>원문 수치 <em>%s</em></h3><ul>%s</ul></div>'
                   '<div class="panel"><h3>읽는 법</h3><p style="font-size:12px;color:var(--tx2);line-height:1.7">조선 계약은 달러 표시가 기본이라 수주잔고(원화 환산)는 환율에 따라 흔들립니다 — 롤포워드의 신규증감에는 환율변동 효과가 섞여 있습니다. '
                   '통화선도 <b>매도</b> 명목액이 달러 수취 예정액을 얼마나 덮는지가 헤지 비율입니다. 비율은 <b>그 회사가 공시한 평균약정환율이 있을 때만</b> 계산합니다 — 없는 회사는 명목액만 보입니다.%s</p></div></div></section>'
                   % (E(hedge.get("where", "") if hedge else "위험관리 절"), "".join(parts),
                      (" <b>%s는 헤지 공시(통화선도 표)를 찾지 못했습니다</b> — 공시가 없거나 파서가 아직 그 회사 표 모양을 모릅니다." % E(rec["name"])) if not hedge else ""))

    # 반복건조(시리즈) 추정
    ser_html = ""
    if s["series"]:
        rows = "".join("<tr><td class=\"l\">%s</td><td class=\"l\">%s</td><td class=\"l\">%s</td><td>%d</td><td>%d</td><td>%s</td><td class=\"l\">%s</td></tr>" % (
            E(tm.get(g["type"], tm["OTHER"])["ko"]), E(g["party"] or "—"), E(g["region"] or "—"), len(g["items"]), g["ships"], fmt_eok(g["amt"]),
            ("옵션 언급" if g["option"] else "") + ' <span class="pill est">추정</span>') for g in s["series"])
        ser_html = ('<section class="card"><h2>반복건조(시리즈) 추정 <em>같은 선종·같은 상대 표기·같은 지역, 수주일 180일 이내 — 공시에 시리즈 표시가 없어 <b>추정</b>입니다</em></h2>'
                    '<div class="wrap"><table data-sortable><thead><tr><th class="l">선종</th><th class="l">상대(공시 표기)</th><th class="l">지역</th><th>계약</th><th>척</th><th>금액(억)</th><th class="l">단서</th></tr></thead><tbody>%s</tbody></table></div></section>' % rows)

    # 척당 계약 표
    cr = []
    for c in sorted(s["contracts"], key=lambda c: c["signed"] or "", reverse=True):
        m = tm.get(c["type"], tm["OTHER"])
        cr.append("<tr><td class=\"l\">%s</td><td class=\"l\"><i class=\"sw\" style=\"display:inline-block;width:9px;height:9px;border-radius:3px;background:%s;margin-right:6px\"></i>%s</td><td class=\"l\">%s</td><td data-v=\"%s\">%s</td><td data-v=\"%.0f\">%s</td><td class=\"l\">%s%s</td><td class=\"l\">%s</td><td class=\"l\">%s</td><td class=\"l\">%s</td><td class=\"l\"><a href=\"https://dart.fss.or.kr/dsaf001/main.do?rcpNo=%s\" target=\"_blank\" rel=\"noopener noreferrer\">원문</a></td></tr>"
                  % (E(c["signed"]), m["color"], E(m["ko"]), E(c["name"]), c["ships"] or 0, c["ships"] or "—", c["amt_krw_m"] or 0, fmt_eok(c["amt_krw_m"]),
                     E(c["party"] or "—"), ' <span class="pill">익명</span>' if c["party_anon"] else "", E(c["region"] or "—"), E(c["end"] or "—"),
                     E(c["payterm"] or "") + (" · 선급금 " + E(c["advance"]) if c["advance"] else ""), E(c["rcp"])))
    con_table = ('<div class="ctl"><input data-filter="#ct" type="search" placeholder="선종·상대·지역 검색"></div><div class="wrap tall"><table id="ct" data-sortable><thead><tr><th class="l">수주일</th><th class="l">선종</th><th class="l">계약명</th><th>척</th><th>금액(억)</th><th class="l">상대</th><th class="l">지역</th><th class="l">인도(종료일)</th><th class="l">대금조건</th><th class="l">출처</th></tr></thead><tbody>%s</tbody></table></div>'
                 % "".join(cr))
    other_note = ""
    if s["other"] or s["unresolved"]:
        other_note = ('<div class="note info">비조선 계약 %d건(공사·엔진·블록 납품)과 선종 미판정 %d건은 척수·선종 집계에서 제외했습니다. 미판정은 계약명이 비었거나(정정공시 표 형식) 선종 별칭 사전에 없는 표기입니다.</div>'
                      % (len(s["other"]), len(s["unresolved"])))

    # 역방향: 이 조선사에 납품하는 기자재사
    sup_rows = []
    for co in data["suppliers"].get("cos", []):
        hit = [y for y in co.get("yards", []) if y.get("yard") == s["stock"]]
        if not hit:
            continue
        cats = sorted({c["cat"] for c in co["cats"] if c["cat"] != "UNCL"})
        sup_rows.append((co, hit[0], cats))
    sup_html = ""
    if sup_rows:
        rows = "".join("<tr><td class=\"l\"><a href=\"../%s/index.html\">%s</a></td><td class=\"l\">%s</td><td class=\"l\">%s</td><td class=\"l\">%s</td></tr>" % (
            E(co["stock"]), E(co["nm"]), " ".join(_chip(c, None) for c in cats[:6]), E(h.get("basis", "")) + (" · 언급 %d회" % h["mentions"] if h.get("mentions") else "") + ((" · 비중 %.1f%%" % h["share"]) if h.get("share") else ""), E(co["prod_raw"][:60])) for co, h, cats in sup_rows)
        sup_html = ('<section class="card"><h2>이 조선사에 납품하는 기자재사 <em>정기보고서 사업의 내용에서 조선사 이름이 언급된 회사 · 근거 등급 표시</em></h2>'
                    '<div class="wrap"><table data-sortable><thead><tr><th class="l">기자재사</th><th class="l">부품 분류</th><th class="l">근거</th><th class="l">주요제품(KIND)</th></tr></thead><tbody>%s</tbody></table></div></section>' % rows)

    # 차트 데이터: 롤포워드 잔고(부문 누적) + 선종별 척당 계약 금액
    chart = {"roll": [{"q": r["q"], "segs": r["segs"], "closing": r["closing"]} for r in roll],
             "types": [{"id": t, "ko": tm.get(t, tm["OTHER"])["ko"], "color": tm.get(t, tm["OTHER"])["color"], "amt": v["amt"], "ships": v["ships"]} for t, v in s["by_type"].items()]}
    seg_colors = ["#3987e5", "#199e70", "#9085e9", "#c98500", "#d55181", "#008300"]
    body = """
<div class="kpi">%s</div>
%s
<div class="grid2" style="margin-top:20px">
 <section class="card" style="margin-top:0"><h2>부문별 수주잔고 추이 <em>정기보고서 롤포워드 · 억원</em></h2><div class="chart"><canvas id="cRoll"></canvas></div></section>
 <section class="card" style="margin-top:0"><h2>선종 구성 <em>척당 계약 공시 누적(2024~) · 계약금액 기준</em></h2><div class="chart"><canvas id="cType"></canvas></div>%s</section>
</div>
<section class="card"><h2>선표(인도 스케줄) <em>척당 계약의 계약기간 종료일 → 분기 · 척수</em></h2>%s</section>
<section class="card"><h2>수주 롤포워드 <em>기초 + 신규증감 − 기납품 = 기말 · 억원 · 부문별</em></h2>%s</section>
%s
%s
%s
<section class="card"><h2>척당 계약 공시 <em>단일판매ㆍ공급계약체결 · %d건</em></h2>%s</section>
%s
<script>const DATA=%s;const SEGC=%s;</script>
<script>%s</script>
<script>
(function(){
  var ds=[]; var segs={}; DATA.roll.forEach(function(r){ r.segs.forEach(function(s){ segs[s.seg]=1; }); });
  Object.keys(segs).forEach(function(seg,i){ ds.push({label:seg,backgroundColor:SEGC[i%%SEGC.length],data:DATA.roll.map(function(r){var x=r.segs.filter(function(s){return s.seg===seg})[0];return x&&x.closing!=null?Math.round(x.closing/100):null;})}); });
  new Chart(document.getElementById('cRoll'),{type:'bar',data:{labels:DATA.roll.map(function(r){return r.q}),datasets:ds},options:{scales:{x:{stacked:true,grid:{display:false}},y:{stacked:true,ticks:{callback:function(v){return v.toLocaleString()}}}},plugins:{tooltip:{callbacks:{label:function(c){return c.dataset.label+': '+(c.parsed.y||0).toLocaleString()+'억'}}}}}});
  new Chart(document.getElementById('cType'),{type:'bar',data:{labels:DATA.types.map(function(t){return t.ko}),datasets:[{label:'계약금액(억)',data:DATA.types.map(function(t){return Math.round(t.amt/100)}),backgroundColor:DATA.types.map(function(t){return t.color})}]},options:{indexAxis:'y',plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){var t=DATA.types[c.dataIndex];return (c.parsed.x||0).toLocaleString()+'억 · '+t.ships+'척'}}}},scales:{x:{ticks:{callback:function(v){return v.toLocaleString()}}},y:{grid:{display:false}}}}});
})();
</script>
<script>%s</script>
""" % ("".join(kpi), other_note, type_table, tl, roll_table, rev_html, fx_html, ser_html, len(s["contracts"]), con_table, sup_html,
       json_for_html(chart), json.dumps(seg_colors), CHART_DEFAULTS_JS, TABLE_JS)
    return page("%s 조선 수주" % rec["name"], body, depth=1, h1="%s" % rec["name"],
                tags=(rec["stock"], rec["market"], rec["industry"]),
                nav=(("허브", "../index.html"), ("인포그래픽", "../parts.html"), ("커버리지", "../coverage.html"), ("DART 원문 ↗", dart)),
                crumbs=(("ARGUS", "../../index.html"), ("한국조선", "../index.html"), (rec["name"], None)),
                scripts=("../vendor/chart.umd.min.js",),
                lead="정기보고서 수주표는 사업부문 롤포워드(원화)라 선종·척수·인도시점이 없습니다. 그 셋은 척당 계약 공시(단일판매ㆍ공급계약체결)에서, 환헤지는 위험관리·파생금융상품 주석에서 읽었습니다. 추정 항목은 표시합니다.")


# ── 허브·커버리지 ───────────────────────────────────────────

def hub_html(data, summaries):
    tm = type_meta(data["types"])
    cards = []
    for s in sorted(summaries, key=lambda s: -((s["roll"][-1]["closing"] if s["roll"] else 0) or 0)):
        rec = s["rec"]
        closing = s["roll"][-1]["closing"] if s["roll"] else None
        ships = sum(v["ships"] for v in s["by_type"].values())
        top = sorted(s["by_type"].items(), key=lambda kv: -kv[1]["amt"])[:3]
        chips = "".join(_chip(tm.get(t, tm["OTHER"])["ko"], tm.get(t, tm["OTHER"])["color"], v["ships"]) for t, v in top)
        hedge = s["hedge"]
        cards.append('<a class="cardlink" href="%s/index.html"><div class="t"><b>%s</b><span class="code">%s</span></div>'
                     '<p>%s</p><div class="chips" style="margin-top:8px">%s</div>'
                     '<div class="stat"><div><b>%s</b><span>수주잔고(억, %s)</span></div><div><b>%s</b><span>척당 계약 척수(2024~)</span></div><div><b>%s</b><span>통화선도 매도(M$)</span></div></div>'
                     '<div class="go">조선사 데이터 →</div></a>'
                     % (E(rec["stock"]), E(rec["name"]), E(rec["stock"]), E(rec["product"][:70]), chips,
                        fmt_eok(closing), E(s["latest_q"] or "—"), fmt_n(ships), fmt_musd(hedge.get("usd_sell_m")) if hedge and hedge.get("usd_sell_m") else "—"))
    sup = data["suppliers"].get("cos", [])
    n_conf = sum(1 for c in sup if c.get("confirmed"))
    cats = collections.Counter(c["cat"].split(".")[0] for co in sup for c in co["cats"] if c["cat"] != "UNCL")
    groups = {g["id"]: g for g in data["tax"]["groups"]}
    gchips = "".join(_chip(groups[g]["ko"], None, n, href="parts.html#" + g) for g, n in cats.most_common(13) if g in groups)
    body = """
<div class="kpi">
 <div><b>%d</b><span>조선사(정기보고서 롤포워드 수록)</span></div>
 <div><b>%d</b><span>척당 계약 공시(2024~) · %s척</span></div>
 <div><b>%d</b><span>기자재사 · 조선사 언급 확인 %d</span></div>
 <div><b>%d</b><span>부품 소분류(인포그래픽 영역 %d)</span></div>
</div>
<h2 class="sec">조선사<span>수주잔고 순 · 선종 칩은 척당 계약 상위 3종(척)</span></h2>
<div class="cards">%s</div>
<h2 class="sec">기자재 — 부품별 진입<span>선박 단면 인포그래픽에서 부품을 누르면 담당 회사로</span></h2>
<div class="cards">
 <a class="cardlink" href="parts.html"><div class="t"><b>⚓ 선박 단면 인포그래픽</b></div><p>선종을 고르면 관련 부품이 강조되고, 부품 영역을 누르면 그 부품을 만드는 상장 기자재사와 납품 조선사가 열립니다.</p><div class="chips" style="margin-top:8px">%s</div><div class="go">인포그래픽 →</div></a>
 <a class="cardlink" href="coverage.html"><div class="t"><b>커버리지</b></div><p>모집단 %d종목의 역할(조선사·지주·엔진·기자재·강재)과 수록 상태, 어떤 근거로 들어왔는지.</p><div class="go">커버리지 →</div></a>
</div>
""" % (len(summaries), len(data["contracts"]), fmt_n(sum(c["ships"] or 0 for c in data["contracts"] if c["type"] not in (None, "OTHER"))),
       len(sup), n_conf, len(data["tax"]["cats"]), len(data["svg"]["regions"]), "".join(cards), gchips, len(data["uni"]))
    return page("한국조선 — 수주·선표·환헤지·기자재", body, depth=0, h1="⚓ 한국조선",
                nav=(("← ARGUS", "../index.html"), ("🏗 한국건설", "../kce/index.html")),
                lead="국내 상장 조선사의 수주를 산업 특성대로 읽습니다 — 선종·척수·인도시점(척당 계약 공시), 부문 롤포워드와 매출인식(정기보고서), 환노출·통화선도 헤지(파생금융상품 주석), 반복건조 추정. 기자재사는 부품 분류로 조선사와 연결합니다.")


def coverage_html(data, summaries):
    role_ko = {"yard": "조선사", "holding": "지주", "engine": "엔진", "equip": "기자재", "steel": "강재"}
    sup = {c["stock"]: c for c in data["suppliers"].get("cos", [])}
    ys = {s["stock"]: s for s in summaries}
    rows = []
    for r in data["uni"]:
        st = r["stock"]
        if r["role"] == "yard":
            s = ys.get(st)
            status = ("수록 · %s분기 · 계약 %d건" % (len(s["roll"]), len(s["contracts"])) if s and s["roll"] else "정기보고서 수주표 미수록")
            link = '<a href="%s/index.html">%s</a>' % (E(st), E(r["name"])) if s and s["roll"] else E(r["name"])
            cls = "up" if s and s["roll"] else "tx3"
        else:
            c = sup.get(st)
            if c and c.get("seen"):
                status = "원문 확인 · 조선사 언급 %s · 부품 %d" % ("있음" if c["confirmed"] else "없음", len([x for x in c["cats"] if x["cat"] != "UNCL"]))
                cls = "up" if c["confirmed"] else "wn"
                link = '<a href="%s/index.html">%s</a>' % (E(st), E(r["name"]))
            else:
                status = "원문 미확인(수집 대기) · KIND 문구 기준 분류"
                cls = "tx3"
                link = '<a href="%s/index.html">%s</a>' % (E(st), E(r["name"])) if c else E(r["name"])
        rows.append("<tr><td class=\"l\">%s</td><td class=\"mut\">%s</td><td class=\"l\">%s</td><td class=\"l mut\">%s</td><td class=\"l\"><b class=\"%s\">%s</b></td><td class=\"l mut\">%s</td><td class=\"l mut\">%s</td></tr>"
                    % (link, E(st), E(role_ko[r["role"]]), E(r["industry"][:22]), cls, E(status), E(r["source"]), E((r.get("reason") or r["product"])[:60])))
    body = """
<section class="card" style="margin-top:0"><h2>모집단 규칙 <em>재현 가능한 세 겹</em></h2>
<p style="font-size:12px;color:var(--tx2);line-height:1.8">① KIND 업종 <b>선박 및 보트 건조업</b> 전 종목 · ② KIND 주요제품 문구에 선박·조선·해양·선용·marine 등 해상 어휘가 있는 종목(해운사·도매업 제외) · ③ 업종·문구 모두에 안 걸리지만 실질이 조선 공급망인 종목을 <b>사유와 함께 지정</b>(엔진·보냉재·피팅·케이블·항해장비). 여기까지는 후보이고, 납품 관계는 정기보고서 원문(사업의 내용)에서 조선사 언급을 확인해 근거 등급을 붙입니다. 이름으로 배제하지 않습니다.</p></section>
<section class="card"><h2>종목별 상태 <em>%d종목</em></h2><div class="wrap"><table data-sortable><thead><tr><th class="l">회사</th><th>종목코드</th><th class="l">역할</th><th class="l">업종</th><th class="l">상태</th><th class="l">편입 근거</th><th class="l">제품·사유</th></tr></thead><tbody>%s</tbody></table></div></section>
<div class="note info">HD현대미포·HD현대삼호는 상장법인목록에 없어(합병·비상장) HD한국조선해양 연결로만 보입니다. 척당 계약 공시의 계약상대는 대부분 '○○ 소재 선사'로 익명이며, 기자재사→조선사 연결은 본문 언급 수준이 많습니다 — 화면의 근거 등급이 그 한계입니다.</div>
<script>%s</script>
""" % (len(data["uni"]), "".join(rows), TABLE_JS)
    return page("한국조선 커버리지", body, depth=0, h1="커버리지",
                nav=(("허브", "index.html"), ("← ARGUS", "../index.html")),
                crumbs=(("ARGUS", "../index.html"), ("한국조선", "index.html"), ("커버리지", None)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    data = load_all()
    summaries = []
    for st, y in data["yards"].items():
        if a.only and st not in a.only.split(","):
            continue
        if not y["q"]:
            print("%s %s — 정기보고서 캐시 없음, 건너뜀" % (st, y["rec"]["name"]))
            continue
        s = yard_summary(st, data)
        summaries.append(s)
        d = os.path.join(KSHIP, st)
        os.makedirs(d, exist_ok=True)
        atomic_write(os.path.join(d, "index.html"), yard_html(s, data))
        print("%s %-10s 분기 %d · 계약 %d(선박 %d척) · 잔고 %s억 · 헤지 %s" % (
            st, y["rec"]["name"], len(s["roll"]), len(s["contracts"]), sum(v["ships"] for v in s["by_type"].values()),
            fmt_eok(s["roll"][-1]["closing"] if s["roll"] else None), (s["hedge"] or {}).get("usd_sell_m")))
    if a.all:
        atomic_write(os.path.join(KSHIP, "index.html"), hub_html(data, summaries))
        atomic_write(os.path.join(KSHIP, "coverage.html"), coverage_html(data, summaries))
        print("index.html · coverage.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
