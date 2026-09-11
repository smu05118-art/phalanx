#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kgrid_page — 한국전력기기 탭의 페이지를 만든다.

  index.html            허브 — 장납기/회전 이분 · 제품군별 잔고 · 수요 낱말 · 회사 카드
  grid.html             전력망 단선도 — 영역(승압·송전·변전·배전·수용가) 클릭 → 제품군 → 회사
  coverage.html         모집단 전수와 편입 근거 · 수록 상태(빠진 것도 이유와 함께)
  <종목코드>/index.html  회사 — 잔고 롤포워드 · 부문/지역 매출 · 커버리지 · 매출처(근거 등급) ·
                        계약 공시 목록 · 원문 표 되짚기

축이 조선·방산과 다른 이유는 원문에 있다(FINDINGS):
  · **잔고가 짧다.** 배수 중앙값이 1년 안팎이라 '잔고가 크다'는 말이 회사마다 뜻이 다르다.
    그래서 이 탭의 1차 축은 잔고 액수가 아니라 **장납기(배수 ≥1년) / 회전(배수 <1년) 이분**이다.
    초고압 변압기는 백로그 산업, 배전기기는 회전 산업 — 한 화면에서 갈라 보이는 게 이 탭의 값어치다.
  · **고객이 전력회사 실명**이다(NextEra Energy·사우디 전력청·한국전력공사). 다만 같은 표에
    고객 분류·관계회사가 섞이므로 근거 등급을 배지로 보인다.
  · **표의 한 행이 계약이 아니라 부문**이다. 입도(segment/project)와 최대 행 비중을 같이 적어
    '잔고 롤포워드'를 계약 원장으로 오해하지 않게 한다.
  · **통화가 섞인다.** 외화로 공시한 회사는 환산하지 않고 통화를 붙여 보이며, 원화 합계에서 뺀다.

    python3 kgrid_page.py --all
"""
import argparse
import collections
import datetime
import html
import json
import os
import re
import sys

from kgrid_lib import (BACKLOG_LABEL, DEMAND_LABEL, DEMAND_ORDER, E, EVIDENCE_LABEL, KGRID,
                       PRODUCT_LABEL, PRODUCT_ORDER, REGION_LABEL, REGION_ORDER,
                       CHART_DEFAULTS_JS, TABLE_JS, atomic_write, backlog_kind, fmt_eok,
                       fmt_money, fmt_n, fmt_pct, fmt_x, has_asset, json_for_html, load_asset,
                       page, pct, product_color)
from kgrid_universe import load as load_universe
import kgrid_dicts
import kgrid_reports

DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=%s"
ROLE_KO = {"maker": "전력기기 제조", "cable": "전선·케이블", "part": "부품·소재",
           "epc": "전기공사·정비", "holding": "지주"}
DEMAND_EXTRA = {"aging_grid": "노후 전력망 교체", "ultra_hv": "초고압(154·345·765kV)",
                "hvdc": "HVDC(초고압직류)", "ai_power": "AI 전력수요"}


def _demand_ko(key):
    return DEMAND_LABEL.get(key) or DEMAND_EXTRA.get(key) or key


_DIGITS = re.compile(r"[\d,]{3,}")
# 표가 문장으로 뽑혔다는 표지 — 단위 캡션·표 머리행·주석 기호는 문장에 안 나온다.
_TABLEISH = re.compile(r"단위\s*:|매출처명|비\s*율|※|^\S{0,4};")


def clean_quote(s):
    """인용문 다듬기. 못 쓸 조각이면 빈 문자열.

    `&nbsp;` 가 남아 있으면 화면에 `&amp;nbsp;` 로 두 번 이스케이프돼 나온다. 그리고 같은 절에
    표가 섞여 있어 표 덤프(`매출처명 금액 비율 NextEra Energy 347,203 15.9%`)가 문장으로
    뽑히는 일이 있다 — 단위 캡션·표 머리행 표지가 있거나 숫자 덩어리가 많으면 버린다. 수집기도 같은 판정을 하지만, 이미 받아 둔
    캐시를 다시 긁지 않고 화면에서 걸러 낸다(DART 요청을 아낀다)."""
    s = html.unescape(s or "").replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) < 24 or len(_DIGITS.findall(s)) > 3 or _TABLEISH.search(s):
        return ""
    return s


def load_all():
    reports = kgrid_reports.load()
    contracts = {"companies": {}, "rows": []}
    for name in ("contracts.json",):
        if has_asset(name):
            try:
                contracts = load_asset(name)
            except Exception as e:
                sys.stderr.write("[warn] %s 를 읽지 못했다: %s\n" % (name, e))
    probe = load_asset("universe_probe.json") if has_asset("universe_probe.json") else {}
    uni = load_universe()
    return {
        "uni": uni,
        "by_stock": {r["stock"]: r for r in uni},
        "products": load_asset("products.json")["rows"],
        "demand": load_asset("demand.json")["rows"],
        "regions": load_asset("grid_regions.json"),
        "reports": reports.get("companies", {}),
        "quarters": reports.get("quarters", []),
        "contracts": contracts,
        "probe": probe,
    }


# ── 계약 공시 붙이기 ────────────────────────────────────────
# `kgrid_contracts.py` 가 만든 `assets/contracts.json` 의 행을 그대로 읽는다.
# 스키마가 없거나 달라도 페이지가 죽지 않게 **있는 것만** 읽는다(없으면 구획을 그리지 않는다).
#   name 계약명 · party 계약상대 · amt/cur 원문 통화 금액 · amt_krw_m 원화 환산(백만원, 공시가
#   환율을 적은 경우) · rev_ratio 최근 매출액 대비 % · demand 수요처 · region 지역 ·
#   product 제품군 · signed 계약일 · start/end/years 기간 · withheld 공시유보 · canceled 해지

def contracts_of(data, stock, include_canceled=False):
    c = data["contracts"]
    rows = None
    if isinstance(c.get("companies"), dict):
        v = c["companies"].get(stock)
        if isinstance(v, dict):
            rows = v.get("rows") or v.get("contracts")
        elif isinstance(v, list):
            rows = v
    if rows is None:
        rows = [r for r in (c.get("rows") or c.get("contracts") or [])
                if isinstance(r, dict) and r.get("stock") == stock]
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if r.get("superseded") or r.get("superseded_by"):
            continue
        if r.get("canceled") and not include_canceled:
            continue
        out.append(r)
    out.sort(key=lambda r: (str(r.get("signed") or ""), str(r.get("rcp") or "")), reverse=True)
    return out


def _cf(r, *keys, **kw):
    for k in keys:
        if r.get(k) not in (None, ""):
            return r[k]
    return kw.get("default")


def contract_amount_cell(r):
    """계약금액 칸. 원화 환산값이 있으면 억원으로, 원문 통화가 다르면 배지로 함께 보인다.

    환산은 **우리가 한 것이 아니다** — 공시가 "SGD 131,918,500을 원화환산하여 기재"처럼
    환율을 적은 경우 그 값을 쓴다(`fx_src` 에 그 문구가 남아 있다). 환산 근거가 없으면
    원문 통화 그대로 보이고 원화 합계에서 뺀다."""
    krw_m = r.get("amt_krw_m")
    cur = r.get("cur") or "KRW"
    if krw_m is not None:
        # 원문이 외화인 계약은 '원문 SGD' 라고 적는다 — 통화 코드만 붙이면 그 숫자가 외화인 줄
        # 오해한다(값은 공시가 적은 환율로 원화 환산된 것이다).
        badge = ('' if cur == "KRW"
                 else '<span class="cur">원문 %s</span>' % E(cur))
        return '<td data-v="%.3f">%s억%s</td>' % (krw_m, E(fmt_eok(krw_m)), badge)
    amt = r.get("amt")
    if amt is None:
        return '<td class="mut">%s</td>' % ("유보" if r.get("withheld") else "—")
    return '<td>%s %s</td>' % (E(format(int(amt), ",d")), E(cur))


# ── 회사 집계 ───────────────────────────────────────────────

def latest_q(data, stock):
    c = data["reports"].get(stock)
    if not c:
        return None, None
    for q in reversed(data["quarters"]):
        v = c["quarters"].get(q)
        if v and v.get("ok"):
            return q, v
    return None, None


def product_keys(data, stock):
    """이 회사가 만드는 제품군. 근거는 세 곳 — KIND 주요제품 · 수주표 품목 · 제품군별 매출 행.

    확신이 없으면 빈 목록이다(추정 금지). 근거 문구도 함께 돌려줘 화면에서 되짚을 수 있게 한다."""
    rec = data["by_stock"].get(stock) or {}
    _q, v = latest_q(data, stock)
    src = []
    if rec.get("product"):
        src.append(("KIND 주요제품", rec["product"]))
    if v:
        for s in v.get("segments") or []:
            txt = " ".join(x for x in (s.get("item"), s.get("seg")) if x)
            if txt:
                src.append(("수주표 품목", txt))
        for s in v.get("sales_segments") or []:
            if s.get("seg") and not s.get("total"):
                src.append(("제품군별 매출", " ".join(x for x in (s["seg"], s.get("item")) if x)))
    keys, why = [], []
    for label, txt in src:
        for k in kgrid_dicts.classify_all(txt, data["products"], limit=3):
            if k not in keys:
                keys.append(k)
                why.append({"key": k, "src": label, "text": txt[:80]})
    keys.sort(key=lambda k: PRODUCT_ORDER.index(k))
    return keys, why


def summary(data, stock):
    rec = data["by_stock"][stock]
    q, v = latest_q(data, stock)
    keys, why = product_keys(data, stock)
    cs = contracts_of(data, stock)
    s = {
        "stock": stock, "name": rec["name"], "role": rec.get("role"),
        "market": rec.get("market", ""), "source": rec.get("source"),
        "reason": rec.get("reason", ""), "product": rec.get("product", ""),
        "industry": rec.get("industry", ""),
        "quarter": q, "products": keys, "product_why": why,
        "n_contracts": len(cs),
        "backlog": None, "cur": "KRW", "coverage": None, "kind": "unknown",
        "export_share": None, "top_customer": None, "grain": None, "top_share": None,
        "shape": None, "unit_note": "", "note": "",
    }
    if not v:
        c = data["reports"].get(stock)
        if c:
            last = [x for x in c["quarters"].values() if not x.get("ok")]
            s["note"] = (last[-1].get("note") if last else "") or "정기보고서에서 표를 못 읽음"
        else:
            s["note"] = "정기보고서 수집 안 됨"
        return s
    s["backlog"] = v.get("backlog")
    s["cur"] = v.get("cur") or "KRW"
    s["coverage"] = v.get("coverage_years")
    s["kind"] = backlog_kind(v.get("coverage_years"))
    s["revenue_fy"] = v.get("revenue_fy")
    s["revenue_fy_col"] = v.get("revenue_fy_col")
    s["revenue_basis"] = v.get("revenue_basis")
    s["grain"] = v.get("grain")
    s["top_share"] = v.get("top_share")
    s["shape"] = v.get("shape")
    s["entity"] = v.get("entity", "")
    s["unit_note"] = v.get("unit_note", "")
    s["coverage_note"] = v.get("coverage_note", "")
    s["total_mismatch"] = v.get("total_mismatch")
    dom, exp = v.get("revenue_domestic"), v.get("revenue_export")
    if dom is not None or exp is not None:
        s["export_share"] = pct(exp or 0, (dom or 0) + (exp or 0))
    if v.get("backlog_dom") is not None or v.get("backlog_ovs") is not None:
        s["backlog_ovs_share"] = pct(v.get("backlog_ovs") or 0,
                                     (v.get("backlog_dom") or 0) + (v.get("backlog_ovs") or 0))
    s["top_customer"] = v.get("top_customer")
    s["demand"] = v.get("demand") or {}
    return s


def all_summaries(data):
    return [summary(data, r["stock"]) for r in data["uni"]]


# ── 조각 ───────────────────────────────────────────────────

def kpi(items):
    return '<div class="kpi">%s</div>' % "".join(
        '<div%s><b>%s%s</b><span>%s</span></div>'
        % (' class="hero"' if it.get("hero") else "", E(str(it["value"])),
           ('<small>%s</small>' % E(it["unit"])) if it.get("unit") else "",
           E(it["label"]))
        for it in items)


def dual_bar(long_v, rot_v, unk_v, labels=("장납기", "회전", "미상")):
    """장납기 : 회전 이분 막대. 값이 0인 갈래는 그리지 않는다(0% 조각은 읽을 수 없다)."""
    tot = (long_v or 0) + (rot_v or 0) + (unk_v or 0)
    if not tot:
        return '<p class="mut">배수를 만들 수 있는 회사가 없어 이분할 수 없습니다.</p>'
    parts = []
    for cls, v, lab in (("lng", long_v, labels[0]), ("rot", rot_v, labels[1]),
                        ("unk", unk_v, labels[2])):
        if not v:
            continue
        p = 100.0 * v / tot
        parts.append('<div class="%s" style="flex:0 0 %.2f%%" title="%s %s">%s</div>'
                     % (cls, p, E(lab), fmt_pct(p), (("%s %s" % (lab, fmt_pct(p, 0)))
                                                     if p >= 12 else "")))
    lg = " · ".join("%s %s억" % (lab, fmt_eok(v))
                    for v, lab in ((long_v, labels[0]), (rot_v, labels[1]), (unk_v, labels[2])) if v)
    return ('<div class="dual">%s</div><div class="duall"><span>%s</span>'
            '<span class="mut">기준 배수 1.0년</span></div>' % ("".join(parts), E(lg)))


def ev_badge(ev):
    if not ev:
        return ""
    return '<span class="ev %s">%s</span>' % (E(ev), E(EVIDENCE_LABEL.get(ev, ev)))


def cur_badge(cur):
    return '' if (cur or "KRW") == "KRW" else '<span class="cur">%s</span>' % E(cur)


def grain_badge(grain, top_share=None):
    if not grain:
        return ""
    ko = {"segment": "부문 합계", "project": "품목별"}.get(grain, grain)
    t = ko + (" · 최대행 %s" % fmt_pct(top_share, 0) if top_share else "")
    return '<span class="grain %s">%s</span>' % (E(grain), E(t))


def money_cell(v, cur):
    """정렬 가능한 금액 칸. 외화는 원화와 **섞어 정렬하지 않는다**(data-v 를 비운다)."""
    if v is None:
        return '<td class="mut">—</td>'
    if (cur or "KRW") == "KRW":
        return '<td data-v="%.3f">%s</td>' % (v, E(fmt_eok(v)))
    return '<td>%s%s</td>' % (E(fmt_money(v, cur)), cur_badge(cur))


# ── 허브 ───────────────────────────────────────────────────

def hub(data):
    ss = [s for s in all_summaries(data) if s["role"] != "holding"]
    hold = [s for s in all_summaries(data) if s["role"] == "holding"]
    krw = [s for s in ss if s["backlog"] is not None and s["cur"] == "KRW"]
    fx = [s for s in ss if s["backlog"] is not None and s["cur"] != "KRW"]
    covs = sorted(s["coverage"] for s in ss if s["coverage"] is not None)
    med = (covs[len(covs) // 2] if len(covs) % 2 else
           (covs[len(covs) // 2 - 1] + covs[len(covs) // 2]) / 2.0) if covs else None
    long_n = sum(1 for s in ss if s["kind"] == "long")
    rot_n = sum(1 for s in ss if s["kind"] == "rotating")
    unk_n = sum(1 for s in ss if s["kind"] == "unknown")
    long_v = sum(s["backlog"] for s in krw if s["kind"] == "long")
    rot_v = sum(s["backlog"] for s in krw if s["kind"] == "rotating")
    unk_v = sum(s["backlog"] for s in krw if s["kind"] == "unknown")

    body = [kpi([
        {"value": len(ss), "unit": "사", "label": "모집단(지주 %d사 제외)" % len(hold)},
        {"value": len(krw) + len(fx), "unit": "사", "label": "수주잔고를 공시", "hero": True},
        {"value": fmt_eok(sum(s["backlog"] for s in krw)), "unit": "억원",
         "label": "원화 공시 잔고 합계(%d사)" % len(krw)},
        {"value": fmt_x(med, 2) if med else "—", "unit": "년", "label": "잔고 커버리지 중앙값"},
        {"value": "%d : %d" % (long_n, rot_n), "unit": "사", "label": "장납기 : 회전"},
        {"value": len(fx), "unit": "사", "label": "외화로 공시(환산 안 함)"},
    ])]

    body.append(
        '<section class="card"><h2>장납기 · 회전 <em>잔고 커버리지(잔고 ÷ 직전 사업연도 매출)로 가른다</em>'
        '</h2><p class="note info">이 산업은 <b>잔고가 짧은 것이 특징</b>입니다. 초고압 변압기는 '
        '수년치 일감을 쌓아 두는 <b>백로그 산업</b>이고 배전기기는 받아서 바로 내보내는 '
        '<b>회전 산업</b>입니다 — 같은 "수주잔고"라는 말의 뜻이 다릅니다. 막대는 원화로 공시한 '
        '회사의 잔고를 배수 1.0년으로 갈라 쌓은 것입니다.</p>%s</section>'
        % dual_bar(long_v, rot_v, unk_v))

    # 제품군별 잔고 — 회사의 제품군이 여럿이면 **나누지 않고** 각 제품군에 회사 수로만 센다.
    # 잔고를 제품군에 배분하려면 제품군별 잔고 공시가 있어야 하는데 이 산업엔 없다(추정 금지).
    prod_rows = []
    for k in PRODUCT_ORDER:
        cos = [s for s in ss if k in s["products"]]
        bl = [s for s in cos if s["backlog"] is not None and s["cur"] == "KRW"]
        prod_rows.append({"key": k, "label": PRODUCT_LABEL[k], "color": product_color(k),
                          "n": len(cos), "n_bal": len(bl),
                          "backlog": sum(s["backlog"] for s in bl) if bl else 0,
                          "names": [s["name"] for s in cos]})
    body.append(
        '<section class="card"><h2>제품군 <em>회사가 만드는 것으로 분류 — 잔고를 제품군에 '
        '쪼개지는 않습니다(제품군별 잔고 공시가 없습니다)</em></h2>'
        '<div class="chart tall"><canvas id="cprod"></canvas></div>'
        '<p class="mut" style="margin-top:8px">막대는 그 제품군을 만드는 회사들의 <b>원화 잔고 합계</b>이고, '
        '한 회사가 여러 제품군에 들어가므로 막대를 더하면 총합보다 큽니다. '
        '분류 근거는 <a href="coverage.html">커버리지</a>와 회사 페이지에 있습니다.</p></section>')

    # 수요 낱말 — 본문에 나온 회사 수로 센다(빈도는 회사마다 편차가 커 순위가 뒤집힌다).
    dem = collections.Counter()
    for s in ss:
        for k in (s.get("demand") or {}):
            dem[k] += 1
    if dem:
        rows = "".join(
            '<tr><td class="l">%s</td><td data-v="%d">%d</td>'
            '<td class="l mut">%s</td></tr>'
            % (E(_demand_ko(k)), n, n,
               E(", ".join(x["name"] for x in ss if k in (x.get("demand") or {}))[:70]))
            for k, n in dem.most_common())
        body.append(
            '<section class="card"><h2>수요 축 <em>II절 본문에 그 낱말이 나온 회사 수 — '
            '추정이 아니라 원문 인용입니다</em></h2><div class="wrap"><table data-sortable>'
            '<thead><tr><th class="l sort">수요 낱말</th><th class="sort">회사</th>'
            '<th class="l">회사(앞부분)</th></tr></thead><tbody>%s</tbody></table></div>'
            '<p class="mut" style="margin-top:8px">낱말이 나온 <b>문장</b>은 회사 페이지에 그대로 '
            '인용해 두었습니다.</p></section>' % rows)

    # 계약 공시로 본 발주처·지역 — 수요 축을 **계약 단위**로 받치는 유일한 원천이다.
    allc = [r for st in (x["stock"] for x in ss) for r in contracts_of(data, st)]
    if allc:
        def agg(field, labeller):
            c = collections.Counter()
            amt = collections.Counter()
            for r in allc:
                k = r.get(field)
                c[k] += 1
                if r.get("amt_krw_m") is not None:
                    amt[k] += r["amt_krw_m"]
            rows = []
            for k, n in c.most_common():
                rows.append('<tr><td class="l">%s</td><td data-v="%d">%d</td>'
                            '<td data-v="%.1f">%s</td></tr>'
                            % (E(labeller(k) if k else "판정 못 함"), n, n,
                               amt.get(k, 0), E(fmt_eok(amt[k]) if amt.get(k) else "—")))
            return "".join(rows)
        util = sum(1 for r in allc if r.get("utility"))
        body.append(
            '<section class="card"><h2>계약 공시로 본 발주처 <em>%d건 — 수주표가 부문 합계인 '
            '이 산업에서 계약 단위 근거</em><span class="right">전력회사 상대 %d건</span></h2>'
            '<div class="grid2">'
            '<div><h2>수요처</h2><div class="wrap"><table data-sortable><thead><tr>'
            '<th class="l sort">수요처</th><th class="sort">건</th><th class="sort">금액(억)</th>'
            '</tr></thead><tbody>%s</tbody></table></div></div>'
            '<div><h2>지역</h2><div class="wrap"><table data-sortable><thead><tr>'
            '<th class="l sort">지역</th><th class="sort">건</th><th class="sort">금액(억)</th>'
            '</tr></thead><tbody>%s</tbody></table></div></div></div>'
            '<p class="mut" style="margin-top:8px">금액은 <b>공시가 환율을 적은 계약</b>만 '
            '원화로 더했습니다(우리가 환산하지 않습니다). 해지 공시는 뺐습니다.</p></section>'
            % (len(allc), util, agg("demand", _demand_ko),
               agg("region", lambda k: REGION_LABEL.get(k, k))))

    # 회사 표
    trs = []
    for s in sorted(ss, key=lambda x: (-(x["backlog"] or 0) if x["cur"] == "KRW" else 0,
                                       x["name"])):
        trs.append(
            '<tr><td class="l"><a href="%s/index.html">%s</a> <span class="basis">%s</span></td>'
            '<td class="l mut">%s</td>%s<td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
            '<td class="l">%s</td></tr>'
            % (E(s["stock"]), E(s["name"]), E(s["stock"]), E(ROLE_KO.get(s["role"], "")),
               money_cell(s["backlog"], s["cur"]),
               E(fmt_x(s["coverage"], 2)),
               '<span class="pill">%s</span>' % E(BACKLOG_LABEL[s["kind"]]),
               E(fmt_pct(s.get("export_share"), 0)),
               E(fmt_pct((s["top_customer"] or {}).get("share_pct"), 1))
               + ev_badge((s["top_customer"] or {}).get("evidence")),
               grain_badge(s["grain"], s["top_share"])
               or ('<span class="mut">%s</span>' % E(s["note"] or "—"))))
    body.append(
        '<section class="card"><h2>회사 <em>%d사 — 잔고 큰 순</em>'
        '<span class="right">외화 공시는 원화와 섞어 정렬하지 않습니다</span></h2>'
        '<div class="ctl"><input data-filter="#tco" placeholder="회사·역할 검색"></div>'
        '<div class="wrap tall"><table id="tco" data-sortable><thead><tr>'
        '<th class="l sort">회사</th><th class="l sort">역할</th><th class="sort">수주잔고</th>'
        '<th class="sort">커버리지(년)</th><th class="sort">성격</th><th class="sort">수출비중</th>'
        '<th class="sort">최대고객</th><th class="l">잔고 입도</th>'
        '</tr></thead><tbody>%s</tbody></table></div></section>'
        % (len(ss), "".join(trs)))

    # 카드
    cards = []
    for s in sorted(ss, key=lambda x: (-(x["backlog"] or 0) if x["cur"] == "KRW" else 0,
                                       x["name"]))[:12]:
        cards.append(
            '<a class="cardlink" href="%s/index.html"><div class="t"><b>%s</b>'
            '<span class="code">%s</span></div><p>%s</p>'
            '<div class="stat"><div><b>%s</b><span>수주잔고</span></div>'
            '<div><b>%s</b><span>커버리지(년)</span></div>'
            '<div><b>%s</b><span>수출비중</span></div></div>'
            '<div class="go">%s%s</div></a>'
            % (E(s["stock"]), E(s["name"]), E(s["stock"]),
               E(", ".join(PRODUCT_LABEL[k] for k in s["products"][:3]) or s["product"][:60]
                 or "제품군 미분류"),
               E(fmt_money(s["backlog"], s["cur"])), E(fmt_x(s["coverage"], 2)),
               E(fmt_pct(s.get("export_share"), 0)),
               E(BACKLOG_LABEL[s["kind"]]),
               E(" · 최대고객 %s" % ((s["top_customer"] or {}).get("name") or "")[:24]
                 if s["top_customer"] else "")))
    body.append('<h2 class="sec">잔고 상위 회사 <span>카드를 누르면 회사 페이지</span></h2>'
                '<div class="cards">%s</div>' % "".join(cards))

    scr = ("<script>%s\n%s\n" % (CHART_DEFAULTS_JS, TABLE_JS)
           + "var PROD=%s;\n" % json_for_html(prod_rows)
           + r"""
(function(){
  var el=document.getElementById('cprod'); if(!el||!window.Chart) return;
  var rows=PROD.filter(function(r){return r.n>0;});
  new Chart(el,{type:'bar',data:{labels:rows.map(function(r){return r.label;}),
    datasets:[{label:'원화 잔고 합계(억원)',data:rows.map(function(r){return Math.round(r.backlog/100);}),
      backgroundColor:rows.map(function(r){return r.color;})}]},
    options:{indexAxis:'y',plugins:{legend:{display:false},tooltip:{callbacks:{afterLabel:function(c){
      var r=rows[c.dataIndex]; return r.n+'사(잔고 공시 '+r.n_bal+'사)';}}}},
      scales:{x:{beginAtZero:true,ticks:{callback:function(v){return v.toLocaleString();}}}}}});
})();
</script>""")
    return page("⚡ 한국전력기기 — 전력기기·전력망",
                "".join(body), depth=0, scripts=("vendor/chart.umd.min.js",),
                h1="⚡ 한국전력기기",
                tags=["DART 정기보고서·수시공시", "모집단 %d사" % len(data["uni"])],
                nav=[("전력망 계통도", "grid.html"), ("커버리지", "coverage.html"),
                     ("ARGUS", "../index.html")],
                lead="전력기기·전력망 상장사를 <b>수주기반</b>으로 봅니다. 이 산업은 잔고가 짧아 "
                     "액수보다 <b>커버리지(잔고 ÷ 연매출)</b>가 뜻이 있고, 고객이 전력회사 실명으로 "
                     "나옵니다. 외화로 공시한 표는 환율을 원문에서 얻을 수 없어 <b>환산하지 "
                     "않습니다</b>.",
                head_extra=scr)


# ── 전력망 단선도 ───────────────────────────────────────────

def grid_page(data):
    ss = [s for s in all_summaries(data) if s["role"] != "holding"]
    reg = data["regions"]
    per_prod = {}
    for k in PRODUCT_ORDER:
        per_prod[k] = [{"stock": s["stock"], "name": s["name"],
                        "backlog": s["backlog"] if s["cur"] == "KRW" else None,
                        "cur": s["cur"], "cov": s["coverage"], "kind": s["kind"]}
                       for s in ss if k in s["products"]]
    shapes, labels = [], []
    for r in reg["regions"]:
        n = sum(len(per_prod[p]) for p in r["products"])
        cls = "rg" + ("" if r["products"] else " rel0")
        shapes.append(
            '<rect class="%s" id="rg-%s" data-region="%s" x="%d" y="%d" width="%d" height="%d" '
            'rx="10" tabindex="%s" role="button" aria-label="%s"></rect>'
            % (cls, E(r["id"]), E(r["id"]), r["x"], r["y"], r["w"], r["h"],
               "0" if r["products"] else "-1", E(r["ko"])))
        labels.append(
            '<text x="%d" y="%d" text-anchor="middle">%s</text>'
            '<text class="sm" x="%d" y="%d" text-anchor="middle">%s</text>'
            % (r["x"] + r["w"] // 2, r["y"] - 8, E(r["ko"]),
               r["x"] + r["w"] // 2, r["y"] + r["h"] + 15,
               E("%d사" % n if r["products"] else "모집단 아님")))
    # 계통 선 — 영역 사이를 잇는 도선. 전압이 낮아질수록 선을 얇게 그린다.
    lines = []
    rs = reg["regions"]
    for a, b, w in zip(rs, rs[1:], (3.0, 2.4, 2.4, 1.8, 1.4)):
        y = 134
        lines.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="rgba(147,197,253,.55)" '
                     'stroke-width="%.1f"></line>'
                     % (a["x"] + a["w"], y, b["x"], y, w))
    svg = ('<div class="ship"><svg viewBox="%s" role="img" aria-label="전력망 단선도">'
           '%s%s%s</svg><div class="legend">'
           '<span><i style="background:rgba(96,165,250,.26)"></i>회사가 있는 자리</span>'
           '<span><i style="background:rgba(255,255,255,.015)"></i>모집단이 아닌 자리</span>'
           '<span>선 굵기 = 전압 계급(왼쪽이 높다)</span></div></div>'
           % (E(reg["viewBox"]), "".join(lines), "".join(shapes), "".join(labels)))

    panel = ('<div class="panel" id="pan"><h3>영역을 누르세요 <em>제품군 → 회사</em></h3>'
             '<p class="mut">전기가 흐르는 순서대로 왼쪽부터 놓았습니다. '
             '발전소는 이 탭의 모집단이 아니라 시작점으로만 그렸습니다.</p></div>')

    body = ['<section class="card"><h2>전력망 단선도 <em>발전 → 승압 → 송전 → 변전 → 배전 → 수용가'
            '</em></h2><div class="ig">%s%s</div></section>' % (svg, panel)]

    rows = []
    for r in reg["regions"]:
        rows.append('<tr><td class="l"><b>%s</b> <span class="basis">%s</span></td>'
                    '<td class="l">%s</td><td class="l mut">%s</td></tr>'
                    % (E(r["ko"]), E(r["en"]),
                       E(", ".join(PRODUCT_LABEL[p] for p in r["products"]) or "—"),
                       E(r["note"])))
    body.append('<section class="card"><h2>영역과 제품군 <em>왜 그 자리인가</em></h2>'
                '<div class="wrap"><table><thead><tr><th class="l">영역</th>'
                '<th class="l">제품군</th><th class="l">근거·뜻</th></tr></thead>'
                '<tbody>%s</tbody></table></div></section>' % "".join(rows))

    scr = ("<script>%s\n" % TABLE_JS
           + "var REG=%s;\nvar PER=%s;\nvar PLAB=%s;\n"
           % (json_for_html(reg["regions"]), json_for_html(per_prod),
              json_for_html(PRODUCT_LABEL))
           + r"""
(function(){
  var pan=document.getElementById('pan');
  function fmt(v){return v==null?'—':Math.round(v/100).toLocaleString()+'억';}
  function show(id){
    var r=REG.filter(function(x){return x.id===id;})[0]; if(!r) return;
    document.querySelectorAll('.rg').forEach(function(e){e.classList.toggle('sel',e.dataset.region===id);});
    pan.textContent='';
    var h=document.createElement('h3'); h.textContent=r.ko;
    var em=document.createElement('em'); em.textContent=r.en; h.appendChild(em); pan.appendChild(h);
    var p=document.createElement('p'); p.className='mut'; p.textContent=r.note; pan.appendChild(p);
    if(!r.products.length){ return; }
    r.products.forEach(function(k){
      var box=document.createElement('div'); box.className='catbox';
      var t=document.createElement('h3'); t.textContent=PLAB[k]||k;
      var e=document.createElement('em'); e.textContent=(PER[k]||[]).length+'사'; t.appendChild(e);
      box.appendChild(t);
      var ul=document.createElement('ul');
      (PER[k]||[]).forEach(function(c){
        var li=document.createElement('li');
        var a=document.createElement('a'); a.href=c.stock+'/index.html'; a.textContent=c.name;
        var y=document.createElement('span'); y.className='y';
        y.textContent=(c.cur==='KRW'?fmt(c.backlog):(c.cur+' 공시'))+(c.cov?(' · '+c.cov.toFixed(1)+'년'):'');
        li.appendChild(a); li.appendChild(y); ul.appendChild(li);
      });
      if(!(PER[k]||[]).length){ var li=document.createElement('li'); li.textContent='해당 회사 없음'; ul.appendChild(li); }
      box.appendChild(ul); pan.appendChild(box);
    });
  }
  document.querySelectorAll('.rg').forEach(function(e){
    if(e.classList.contains('rel0')) return;
    e.addEventListener('click',function(){show(e.dataset.region);});
    e.addEventListener('keydown',function(ev){if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();show(e.dataset.region);}});
  });
})();
</script>""")
    return page("전력망 단선도 — 한국전력기기", "".join(body), depth=0,
                h1="전력망 단선도", crumbs=[("⚡ 한국전력기기", "index.html"), ("단선도", None)],
                nav=[("허브", "index.html"), ("커버리지", "coverage.html")],
                lead="전력기기는 <b>전기가 흐르는 자리</b>로 나뉩니다. 승압 변전소의 초고압 변압기와 "
                     "배전 선로의 주상변압기는 같은 '변압기'라는 낱말을 쓰지만 납기와 잔고의 성격이 "
                     "다릅니다. 영역을 눌러 그 자리의 제품군과 회사를 봅니다.",
                head_extra=scr)


# ── 커버리지 ───────────────────────────────────────────────

def coverage_page(data):
    ss = all_summaries(data)
    by_src = collections.Counter(s["source"] for s in ss)
    withbal = sum(1 for s in ss if s["backlog"] is not None)
    body = [kpi([
        {"value": len(ss), "unit": "사", "label": "모집단 전수"},
        {"value": withbal, "unit": "사", "label": "수주잔고를 공시"},
        {"value": sum(1 for s in ss if s["quarter"]), "unit": "사", "label": "정기보고서를 읽음"},
        {"value": sum(1 for s in ss if s["products"]), "unit": "사", "label": "제품군 분류됨"},
    ])]
    body.append(
        '<section class="card"><h2>이 탭이 무엇을 싣고 무엇을 뺐는가</h2>'
        '<p class="note info">① <b>업종</b> — KIND 업종 네 갈래'
        '(<code>전동기, 발전기 및 전기 변환 · 공급 · 제어 장치 제조업</code>·'
        '<code>기타 전기장비 제조업</code>·<code>절연선 및 케이블 제조업</code>·'
        '<code>전기 및 통신 공사업</code>) 중 <b>주요제품 문구가 전력망을 말하는 것</b>. '
        '업종만으로는 모집단이 서지 않습니다 — 네 갈래 72종목의 절반이 2차전지 장비·전기차 '
        '충전기·휴대폰 부품입니다.<br>'
        '② <b>제품</b> — 업종 밖에서 제품 문구로 잡히는 것(금구류·절연유·부스웨이·계량기).<br>'
        '③ <b>지정</b> — 업종이 엉뚱한 실제 제조사(비츠로테크는 업종이 <code>기타 금융업</code>인데 '
        '본인이 차단기를 만듭니다).<br>'
        '④ <b>탐색</b> — 정기보고서 II절 본문 근거로 승격한 것.<br>'
        '<b>뺀 것</b>: <code>전기업</code>(한국전력공사 등 — 발주처입니다), 이차전지 제조·건전지'
        '(<code>ESS</code> 낱말이 겹칩니다), 지주회사(자회사와 이중계산되므로 갈라 둡니다).</p>'
        '<p class="mut">출처 구성: %s</p></section>'
        % E(" · ".join("%s %d사" % (k, v) for k, v in by_src.most_common())))

    body.append(
        '<section class="card"><h2>왜 배전기기 회사를 남겨 두는가 '
        '<em>회전 산업이라 잔고 화면의 뜻이 다르다</em></h2>'
        '<p class="note info">배전기기(수배전반·주상변압기·개폐기)는 <b>받아서 몇 달 안에 '
        '내보내는</b> 사업입니다. 잔고가 연매출의 절반이어도 정상이고, 잔고가 늘지 않아도 '
        '매출이 늘 수 있습니다. 반대로 초고압 변압기는 <b>몇 년치 일감을 쌓아 두는</b> 사업이라 '
        '잔고가 곧 미래 매출입니다. 두 부류를 같은 막대에 그려 놓고 "잔고가 작다"고 읽으면 '
        '틀립니다 — 그래서 이 탭은 배수 1.0년으로 갈라 <b>장납기 : 회전</b>으로 보여 주고, '
        '배수를 만들 수 없는 회사는 <b>미상</b>으로 남깁니다(추정하지 않습니다).</p></section>')

    trs = []
    for s in sorted(ss, key=lambda x: (x["role"], x["stock"])):
        state = ("수록" if s["backlog"] is not None else
                 ("잔고 없음(매출만)" if s["quarter"] else "정기보고서 미수집"))
        trs.append(
            '<tr><td class="l"><a href="%s/index.html">%s</a> <span class="basis">%s</span></td>'
            '<td class="l mut">%s</td><td class="l mut">%s</td><td class="l">%s</td>'
            '<td class="l">%s</td><td class="l mut">%s</td></tr>'
            % (E(s["stock"]), E(s["name"]), E(s["stock"]), E(ROLE_KO.get(s["role"], "")),
               E(s["source"] or ""), E(state),
               E(", ".join(PRODUCT_LABEL[k] for k in s["products"]) or "—"),
               E((s["reason"] or s["product"] or "")[:96])))
    body.append(
        '<section class="card"><h2>모집단 전수 <em>%d사 — 편입 근거와 수록 상태</em></h2>'
        '<div class="ctl"><input data-filter="#tcov" placeholder="회사·근거 검색"></div>'
        '<div class="wrap tall"><table id="tcov" data-sortable><thead><tr>'
        '<th class="l sort">회사</th><th class="l sort">역할</th><th class="l sort">출처</th>'
        '<th class="l sort">수록 상태</th><th class="l">제품군</th><th class="l">편입 근거</th>'
        '</tr></thead><tbody>%s</tbody></table></div></section>' % (len(ss), "".join(trs)))

    pr = data.get("probe") or {}
    if pr:
        prom = pr.get("promoted") or {}
        rej = pr.get("rejected") or []
        rows = "".join(
            '<tr><td class="l">%s</td><td class="l mut">%s</td><td class="l mut">%s</td></tr>'
            % (E(k), E(str((v or {}).get("role", ""))),
               E(str((v or {}).get("reason", ""))[:140]))
            for k, v in sorted(prom.items()))
        rrows = "".join(
            '<tr><td class="l">%s</td><td class="l mut">%s</td></tr>'
            % (E(str(r.get("stock") if isinstance(r, dict) else r)),
               E(str((r.get("reason") if isinstance(r, dict) else "") or "")[:140]))
            for r in rej[:80])
        body.append(
            '<section class="card"><h2>④ 본문 탐색 <em>후보 %s · 승격 %d · 제외 %d</em></h2>'
            '<div class="grid2"><div><h2>승격</h2><div class="wrap"><table><thead><tr>'
            '<th class="l">종목</th><th class="l">역할</th><th class="l">근거</th></tr></thead>'
            '<tbody>%s</tbody></table></div></div>'
            '<div><h2>제외</h2><div class="wrap tall"><table><thead><tr>'
            '<th class="l">종목</th><th class="l">이유</th></tr></thead><tbody>%s</tbody>'
            '</table></div></div></div></section>'
            % (E(str(pr.get("candidates", "—"))), len(prom), len(rej),
               rows or '<tr><td colspan="3" class="mut">없음</td></tr>',
               rrows or '<tr><td colspan="2" class="mut">없음</td></tr>'))

    body.append(
        '<section class="card"><h2>못 싣는 것 <em>fail-closed 로 비운 칸</em></h2>'
        '<p class="note">· <b>외화 공시 잔고의 배수</b> — 일진전기는 수주표가 '
        '<code>(단위 : 천USD )</code>인데 매출실적은 백만원입니다. 보고서에 <b>기말 현물환율이 '
        '없어</b>(통화선도 계약환율만 있습니다) 환산하지 않고 배수를 비웁니다.<br>'
        '· <b>제품군별 잔고</b> — 이 산업에는 제품군별 수주잔고 공시가 없습니다. 제품군은 '
        '회사 단위로만 붙입니다.<br>'
        '· <b>5% 미달 매출처</b> — "연결 매출의 5% 이상을 차지하는 매출처를 기재"라는 주석이 '
        '붙습니다. 최대고객 비중은 <b>하한</b>이며 고객 전체를 뜻하지 않습니다.<br>'
        '· <b>비밀유지로 생략한 매출처</b> — "주 고객과의 비밀유지계약 등에 따라 세부 매출처 및 '
        '매출비중 기재를 생략합니다"라고 적은 회사가 있습니다. 빈칸으로 둡니다.</p></section>')

    return page("커버리지 — 한국전력기기", "".join(body), depth=0,
                h1="커버리지", crumbs=[("⚡ 한국전력기기", "index.html"), ("커버리지", None)],
                nav=[("허브", "index.html"), ("전력망 계통도", "grid.html")],
                head_extra="<script>%s</script>" % TABLE_JS,
                lead="모집단을 어떻게 세웠고, 무엇을 못 실었는지 적습니다. 빠진 것도 이유와 함께 "
                     "보이는 것이 이 페이지의 목적입니다.")


# ── 회사 페이지 ─────────────────────────────────────────────

def company(data, stock):
    s = summary(data, stock)
    c = data["reports"].get(stock) or {"quarters": {}}
    qs = [q for q in data["quarters"] if q in c["quarters"] and c["quarters"][q].get("ok")]
    _q, v = latest_q(data, stock)
    body = []

    tiles = [
        {"value": fmt_money(s["backlog"], s["cur"]), "label": "수주잔고 (%s)" % (s["quarter"] or "—"),
         "hero": True},
        {"value": fmt_x(s["coverage"], 2), "unit": "년", "label": "커버리지(잔고÷연매출)"},
        {"value": BACKLOG_LABEL[s["kind"]], "label": "잔고 성격(기준 1.0년)"},
        {"value": fmt_money(s.get("revenue_fy"), (v or {}).get("revenue_cur", "KRW")),
         "label": "연매출 %s" % (s.get("revenue_fy_col") or "—")},
        {"value": fmt_pct(s.get("export_share"), 1), "label": "수출비중(매출실적)"},
        {"value": fmt_pct((s["top_customer"] or {}).get("share_pct"), 1),
         "label": "최대 외부고객 비중"},
    ]
    body.append(kpi(tiles))

    notes = []
    if s["role"] == "holding":
        notes.append("<b>지주회사</b>입니다 — 이 잔고·매출은 연결 종속회사의 표에서 읽은 것이라 "
                     "자회사 페이지와 <b>겹칩니다</b>. 허브의 합계·이분 막대에서는 뺐습니다.")
    if s.get("unit_note"):
        notes.append(s["unit_note"])
    if s.get("coverage_note"):
        notes.append(s["coverage_note"])
    if s.get("total_mismatch"):
        notes.append("수주표 낱 행의 합과 원문 총계가 1% 넘게 어긋납니다 — 원문 표를 확인하세요.")
    if s.get("entity"):
        notes.append("수주표는 <b>%s</b> 표에서 읽었습니다(보고서에 종속회사 표가 여러 벌 옵니다)."
                     % E(s["entity"]))
    if s.get("revenue_basis") == "entity":
        notes.append("커버리지의 분모는 <b>같은 주체</b>의 연매출입니다 — 종속회사 매출을 다 더해 "
                     "나누면 배수가 낮아집니다.")
    if s.get("grain") == "segment":
        notes.append("수주표의 한 행이 계약이 아니라 <b>사업부문 합계</b>입니다"
                     + (" (최대 행이 잔고의 %s)" % fmt_pct(s["top_share"], 1)
                        if s.get("top_share") else "") + ".")
    if notes:
        body.append('<p class="note" style="margin-top:14px">%s</p>'
                    % "<br>".join("· " + n for n in notes))

    # 잔고 추이·롤포워드
    if qs:
        series = [{"q": q, **{k: c["quarters"][q].get(k) for k in
                              ("backlog", "opening", "new", "delivered", "gross",
                               "coverage_years", "cur")}} for q in qs]
        roll = [x for x in series if x.get("new") is not None or x.get("delivered") is not None]
        body.append(
            '<section class="card"><h2>수주잔고 추이 <em>%s — 분기 %d개</em></h2>'
            '<div class="chart"><canvas id="cbal"></canvas></div>%s</section>'
            % (E(s["cur"]), len(qs),
               ('<p class="mut" style="margin-top:8px">신규수주·기납품액을 같이 공시하는 회사라 '
                '롤포워드(기초+신규−기납품=기말)를 그릴 수 있습니다.</p>' if roll else
                '<p class="mut" style="margin-top:8px">이 회사 수주표에는 신규수주·기납품액 열이 '
                '없어 잔고 수준만 그립니다.</p>')))
        if v and (v.get("segments") or []):
            trs = "".join(
                '<tr><td class="l">%s</td><td class="l mut">%s</td>%s%s%s%s'
                '<td class="l mut">%s</td><td class="l mut">%s</td></tr>'
                % (E(x.get("seg") or ""), E(x.get("item") or ""),
                   money_cell(x.get("opening"), s["cur"]),
                   money_cell(x.get("new") if x.get("new") is not None else x.get("gross"),
                              s["cur"]),
                   money_cell(x.get("delivered"), s["cur"]),
                   money_cell(x.get("closing"), s["cur"]),
                   E(x.get("order_date") or ""), E(x.get("due") or ""))
                for x in v["segments"])
            body.append(
                '<section class="card"><h2>수주표 행 <em>%s 원문 그대로</em>'
                '<span class="right">수주일자·납기가 기간 표기인 회사가 많습니다</span></h2>'
                '<div class="wrap"><table data-sortable><thead><tr>'
                '<th class="l sort">부문</th><th class="l sort">품목</th>'
                '<th class="sort">기초·이월</th><th class="sort">신규·총액</th>'
                '<th class="sort">기납품</th><th class="sort">잔고</th>'
                '<th class="l">수주일자</th><th class="l">납기</th>'
                '</tr></thead><tbody>%s</tbody></table></div></section>' % (E(s["quarter"]), trs))
        if v and (v.get("orders_other") or []):
            trs = "".join(
                '<tr><td class="l">%s</td><td class="l mut">%s</td>%s<td>%s</td></tr>'
                % (E(x.get("entity") or "(라벨 없음)"), E(x.get("shape") or ""),
                   money_cell(x.get("closing"), x.get("cur") or "KRW"), x.get("n_rows"))
                for x in v["orders_other"])
            body.append(
                '<section class="card"><h2>같은 보고서의 다른 수주표 '
                '<em>종속회사별로 표가 여러 벌 옵니다 — 본체가 아닌 것</em></h2>'
                '<div class="wrap"><table><thead><tr><th class="l">종속회사</th>'
                '<th class="l">표 모양</th><th>잔고</th><th>행</th></tr></thead>'
                '<tbody>%s</tbody></table></div>'
                '<p class="mut" style="margin-top:8px">위 KPI 의 잔고에는 <b>들어 있지 '
                '않습니다</b>. 전력망과 무관한 사업(동관·EV부품 등)이 섞여 있어 합치지 '
                '않습니다.</p></section>' % trs)

    # 부문·지역 매출
    if v and (v.get("revenue_segments") or v.get("regions") or v.get("sales_segments")):
        half = []
        if v.get("revenue_segments"):
            trs = "".join(
                '<tr><td class="l">%s</td><td class="l mut">%s</td><td class="l">%s</td>%s</tr>'
                % (E(x["seg"]), E(x.get("item") or ""), E(x["kind"]),
                   money_cell(x.get("val"), (v.get("revenue_cur") or "KRW")))
                for x in v["revenue_segments"])
            half.append('<div><h2>부문 × 내수/수출 <em>원문 이름 그대로</em></h2>'
                        '<div class="wrap tall"><table data-sortable><thead><tr>'
                        '<th class="l sort">부문</th><th class="l">품목</th>'
                        '<th class="l sort">구분</th><th class="sort">금액</th></tr></thead>'
                        '<tbody>%s</tbody></table></div></div>' % trs)
        if v.get("regions"):
            tot = sum(x["val"] for x in v["regions"] if x.get("val")) or None
            trs = "".join(
                '<tr><td class="l">%s</td><td class="l mut">%s</td>%s<td>%s</td></tr>'
                % (E(x["name"]), E(REGION_LABEL.get(x.get("region") or "", "")),
                   money_cell(x.get("val"), v.get("region_cur") or "KRW"),
                   E(fmt_pct(pct(x.get("val"), tot), 1)))
                for x in sorted(v["regions"], key=lambda r: -(r.get("val") or 0)))
            half.append('<div><h2>지역별 매출 <em>원문 「지역별 매출 현황」</em></h2>'
                        '<div class="wrap"><table data-sortable><thead><tr>'
                        '<th class="l sort">원문 지역</th><th class="l">정규화</th>'
                        '<th class="sort">금액</th><th class="sort">비중</th></tr></thead>'
                        '<tbody>%s</tbody></table></div></div>' % trs)
        if v.get("sales_segments"):
            trs = "".join(
                '<tr><td class="l">%s</td><td class="l mut">%s</td>%s<td>%s</td></tr>'
                % (E(x["seg"]), E(x.get("item") or ""),
                   money_cell(x.get("val"), "KRW"), E(fmt_pct(x.get("pct"), 1)))
                for x in v["sales_segments"] if not x.get("total"))
            if trs:
                half.append('<div><h2>제품군별 매출실적 <em>제품군 구성의 근거</em></h2>'
                            '<div class="wrap tall"><table data-sortable><thead><tr>'
                            '<th class="l sort">구분</th><th class="l">품목</th>'
                            '<th class="sort">금액</th><th class="sort">비중</th></tr></thead>'
                            '<tbody>%s</tbody></table></div></div>' % trs)
        if half:
            body.append('<section class="card"><h2>매출 구성 <em>%s</em></h2>'
                        '<div class="grid2">%s</div></section>'
                        % (E(s["quarter"] or ""), "".join(half)))

    # 매출처
    if v and (v.get("customers") or []):
        cust = v["customers"]
        trs = "".join(
            '<tr><td class="l">%s%s</td><td class="l mut">%s</td><td>%s</td>%s'
            '<td class="l mut">%s</td></tr>'
            % (E(x["name"]), ev_badge(x.get("evidence")), E(x.get("seg") or ""),
               E(fmt_pct(x.get("share_pct"), 1)),
               money_cell(x.get("amount"), x.get("cur") or "KRW"),
               E("표 %d" % (x.get("tbl", 0) + 1)))
            for x in cust)
        body.append(
            '<section class="card"><h2>주요 매출처 <em>%d행 · 표 %d장</em>'
            '<span class="right">실명 / 익명 / 고객분류 / 관계회사를 배지로 구분합니다</span></h2>'
            '<p class="note info">비중은 대개 <b>그 사업부문·종속회사 안에서의 비중</b>이며 '
            '회사 전체 매출 대비가 아닙니다. <b>표 1</b>이 본체 표입니다 — 뒤 표는 종속회사 것이라 '
            '비중이 커도 회사 전체로는 작습니다. 또 "연결 매출의 5%% 이상만 기재"라는 주석이 붙는 '
            '회사가 있어 최대고객 비중은 <b>하한</b>입니다.</p>'
            '<div class="ctl"><input data-filter="#tcu" placeholder="매출처 검색"></div>'
            '<div class="wrap tall"><table id="tcu" data-sortable><thead><tr>'
            '<th class="l sort">매출처</th><th class="l sort">부문</th><th class="sort">비중</th>'
            '<th class="sort">금액</th><th class="l sort">출처</th></tr></thead>'
            '<tbody>%s</tbody></table></div></section>'
            % (len(cust), (v.get("customer_tables") or 1), trs))

    # 계약 공시 — 이 산업에서 **계약 단위 원장**은 이것뿐이다(수주표는 부문 합계다).
    cs = contracts_of(data, stock, include_canceled=True)
    if cs:
        live = [r for r in cs if not r.get("canceled")]
        trs = []
        for r in cs[:200]:
            tags = []
            if r.get("canceled"):
                tags.append('<span class="pill">해지</span>')
            if r.get("withheld"):
                tags.append('<span class="pill est">공시유보</span>')
            if r.get("affiliate"):
                tags.append('<span class="ev rel">관계회사</span>')
            if r.get("anon"):
                tags.append('<span class="ev anon">익명</span>')
            if r.get("utility"):
                tags.append('<span class="ev named">전력회사</span>')
            period = " ~ ".join(x for x in (r.get("start"), r.get("end")) if x)
            if r.get("years"):
                period += " (%s년)" % fmt_x(r["years"], 1)
            trs.append(
                '<tr><td class="l" title="%s">%s</td><td class="l mut">%s%s</td>%s'
                '<td>%s</td><td class="l mut">%s</td><td class="l mut">%s</td>'
                '<td class="l mut">%s</td><td class="l">%s</td></tr>'
                % (E(str(r.get("name") or "")), E(str(r.get("name") or "")[:76]),
                   E(str(r.get("party") or ("유보" if r.get("withheld") else "—"))[:34]),
                   "".join(tags),
                   contract_amount_cell(r),
                   E(fmt_pct(r.get("rev_ratio"), 1)),
                   E(_demand_ko(r["demand"]) if r.get("demand") else ""),
                   E(REGION_LABEL.get(r.get("region") or "", "") or (r.get("region_raw") or "")),
                   E(str(r.get("signed") or "") + (" · " + period if period else "")),
                   ('<a href="%s" target="_blank" rel="noopener noreferrer">원문</a>'
                    % E(DART % r["rcp"]) if r.get("rcp") else "")))
        krw = [r["amt_krw_m"] for r in live if r.get("amt_krw_m") is not None]
        body.append(
            '<section class="card"><h2>계약 공시 <em>「단일판매ㆍ공급계약체결」 유효 %d건'
            '%s</em><span class="right">금액 합계 %s억(환산 근거가 있는 %d건)</span></h2>'
            '<p class="note info">이 산업의 수주표는 <b>사업부문 합계</b>라 계약 단위 원장은 '
            '이 공시뿐입니다. 다만 공시 의무 기준(최근 매출액 대비 비율)을 넘는 계약만 나오므로 '
            '<b>전부가 아닙니다</b>. 외화 계약의 원화 금액은 우리가 환산한 것이 아니라 '
            '<b>공시가 환율을 적은 경우</b> 그 값입니다 — 근거가 없으면 원문 통화로 둡니다.</p>'
            '<div class="ctl"><input data-filter="#tct" placeholder="계약명·상대 검색"></div>'
            '<div class="wrap tall"><table id="tct" data-sortable><thead><tr>'
            '<th class="l sort">계약명</th><th class="l sort">계약상대</th>'
            '<th class="sort">금액</th><th class="sort">매출액 대비</th>'
            '<th class="l sort">수요처</th><th class="l sort">지역</th>'
            '<th class="l sort">계약일·기간</th><th class="l">원문</th>'
            '</tr></thead><tbody>%s</tbody></table></div></section>'
            % (len(live), (" · 해지 %d건" % (len(cs) - len(live))) if len(cs) > len(live) else "",
               fmt_eok(sum(krw)) if krw else "—", len(krw), "".join(trs)))

    # 수요 낱말 인용
    if s.get("demand"):
        blocks = []
        for k, d in sorted(s["demand"].items(), key=lambda kv: -kv[1]["n"]):
            quotes = [q for q in (clean_quote(x) for x in (d.get("quotes") or [])) if q][:2]
            qs_ = "".join('<li>%s</li>' % E(x) for x in quotes)
            blocks.append('<div class="panel"><h3>%s <em>%d회</em></h3><ul>%s</ul></div>'
                          % (E(_demand_ko(k)), d["n"],
                             qs_ or '<li class="mut">낱말은 나오지만 문장으로 뽑을 조각이 '
                                    '표 안에 있었습니다 — 원문 보고서를 보세요</li>'))
        body.append('<section class="card"><h2>수요 축 — 원문 인용 <em>II절 본문</em>'
                    '<span class="right">%s</span></h2><div class="grid2">%s</div></section>'
                    % (E((v or {}).get("demand_scope") or ""), "".join(blocks)))

    # 되짚기
    meta = []
    if s.get("quarter"):
        vq = c["quarters"][s["quarter"]]
        if vq.get("rcp"):
            meta.append('<a href="%s" target="_blank" rel="noopener noreferrer">'
                        'DART 원문 보고서</a>' % E(DART % vq["rcp"]))
    meta.append("KIND 업종 <code>%s</code>" % E(s["industry"]))
    meta.append("편입 근거: %s" % E(s["reason"] or s["product"] or "—"))
    if s["products"]:
        meta.append("제품군 판정 근거: " + E(" / ".join(
            "%s ← %s「%s」" % (PRODUCT_LABEL[w["key"]], w["src"], w["text"][:36])
            for w in s["product_why"][:4])))
    body.append('<section class="card"><h2>되짚기 <em>이 숫자가 어디서 왔는가</em></h2>'
                '<p class="mut">%s</p></section>' % "<br>".join(meta))

    scr = ("<script>%s\n%s\n" % (CHART_DEFAULTS_JS, TABLE_JS)
           + "var SER=%s;\n" % json_for_html(
               [{"q": q, "backlog": c["quarters"][q].get("backlog"),
                 "new": c["quarters"][q].get("new"),
                 "delivered": c["quarters"][q].get("delivered"),
                 "cov": c["quarters"][q].get("coverage_years")} for q in qs])
           + r"""
(function(){
  var el=document.getElementById('cbal'); if(!el||!window.Chart||!SER.length) return;
  var css=getComputedStyle(document.documentElement);
  var s1=css.getPropertyValue('--s1').trim(), s3=css.getPropertyValue('--s3').trim(),
      s2=css.getPropertyValue('--s2').trim();
  var ds=[{type:'bar',label:'수주잔고',data:SER.map(function(r){return r.backlog;}),backgroundColor:s1,order:3}];
  if(SER.some(function(r){return r['new']!=null;}))
    ds.push({type:'line',label:'당기 신규수주',data:SER.map(function(r){return r['new'];}),borderColor:s3,order:1});
  if(SER.some(function(r){return r.delivered!=null;}))
    ds.push({type:'line',label:'기납품액',data:SER.map(function(r){return r.delivered;}),borderColor:s2,order:2});
  new Chart(el,{data:{labels:SER.map(function(r){return r.q;}),datasets:ds},
    options:{scales:{y:{beginAtZero:true,ticks:{callback:function(v){return (v/100).toLocaleString();}},
      title:{display:true,text:'억원(원화 공시) · 외화는 백만 단위'}}}}});
})();
</script>""")
    return page("%s — 한국전력기기" % s["name"], "".join(body), depth=1,
                scripts=("../vendor/chart.umd.min.js",),
                h1=s["name"],
                tags=[s["stock"], ROLE_KO.get(s["role"], ""), s["market"],
                      BACKLOG_LABEL[s["kind"]]],
                crumbs=[("⚡ 한국전력기기", "../index.html"), ("회사", None), (s["name"], None)],
                nav=[("허브", "../index.html"), ("단선도", "../grid.html"),
                     ("커버리지", "../coverage.html")],
                head_extra=scr,
                lead=E(", ".join(PRODUCT_LABEL[k] for k in s["products"])
                       or s["product"][:80] or "제품군 미분류")
                     + (" — " + E(s["reason"][:120]) if s["reason"] else ""))


# ── 쓰기 ───────────────────────────────────────────────────

def write(path, html):
    full = os.path.join(KGRID, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    atomic_write(full, html)
    return len(html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    data = load_all()
    n = 0
    if a.only:
        for st in a.only.split(","):
            write("%s/index.html" % st, company(data, st))
            n += 1
        print("회사 %d쪽" % n)
        return
    write("index.html", hub(data))
    write("grid.html", grid_page(data))
    write("coverage.html", coverage_page(data))
    for r in data["uni"]:
        write("%s/index.html" % r["stock"], company(data, r["stock"]))
        n += 1
    print("허브·단선도·커버리지 + 회사 %d쪽" % n)


if __name__ == "__main__":
    sys.exit(main())
