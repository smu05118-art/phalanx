#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""knuke_reports — 정기보고서 「II. 사업의 내용 · 4. 매출 및 수주상황」에서 분기 지표를 읽는다.

이 탭의 차별점이 여기 있다(스펙 §왜수주기반). 조선·방산과 달리 수주표에 **발주처 실명·사업명·
계약기간**이 행마다 있다(한전기술 23행 발주처=한국수력원자력, 한전KPS 요르단 IPP3 2039년까지).
그래서 세 가지를 읽는다:

  · 표 모양 네 갈래 —
      (award)   `구분|발주처|사업명|최초계약일|종료일|기본도급액|완성공사액|계약잔액` (한전기술·한전KPS)
                → 발주처·계약기간이 행마다. 호기 타임라인·발주처 집중도·발전원별 잔고 구성의 근거.
      (std)     `품목|수주일자|납기|수주총액|기납품액|수주잔고`
      (roll)    `기초|증감/신규|기납품/매출계상|기말`
      (balance) 잔액 한 줄
  · **부문 매출**(발전원 × 내수/수출) — 회사마다 부문명이 다르다. 정규화(발전원 id)하되 원문 이름을
    반드시 함께 남긴다(COMMON §0-1).
  · **잔고 커버리지**(수주잔고 ÷ 연매출, 년) — (balance)형에서도 계산된다.

원문 표(cols·rows·lead)를 캐시에 그대로 남긴다 — 파서가 자라면 재수집 없이 다시 뽑는다(COMMON §0-4).

    python3 knuke_reports.py --collect [--quarter 2026Q2] [--only 052690]
    python3 knuke_reports.py --build
"""
import argparse
import json
import os
import re
import sys

from knuke_lib import (ASSETS, atomic_write, fetch_section, find_sections, is_total,
                       latest_quarter, load_asset, num_of, parse_tables, pick_report,
                       report_kind, report_window, search_reports, toc, unit_of,
                       write_asset)
from knuke_universe import load as load_universe
import knuke_contracts

CACHE = os.path.join(ASSETS, "reports_cache")

SECTIONS = [
    ("sales", ["매출 및 수주상황", "수주상황", "수주 상황", "매출실적"]),
    ("products", ["주요 제품 및 서비스", "주요 제품", "주요제품"]),
    ("overview", ["사업의 개요"]),
]

_SECURITY = re.compile(r"보안\s*관계상|보안상|군사기밀|보안\s*유지")
# 익명화된 사업명('철도A'·'A사업'·'Project B')
_ANON = re.compile(r"^[\w가-힣]{0,6}\s*[A-Z]{1,3}\d*$")


def _clean(s):
    return re.sub(r"[\s　]+", "", s or "")


def _headered(tables):
    """머리행을 못 잡은 표를 살린다(첫 행이 비숫자면 머리행)."""
    out = []
    for t in tables:
        if t["cols"]:
            out.append(t)
            continue
        rows = t["rows"]
        if len(rows) < 2 or len(rows[0]) < 2:
            continue
        if any(num_of(c) is not None for c in rows[0]):
            continue
        if len({_clean(c) for c in rows[0]}) != len(rows[0]):
            d = _two_row_header(t)
            if d:
                out.append(d)
            continue
        if not any(num_of(c) is not None for r in rows[1:] for c in r):
            continue
        d = dict(t)
        d["cols"], d["rows"] = list(rows[0]), rows[1:]
        d["header_synth"] = True
        out.append(d)
    return out


_UNIT_CAP = re.compile(r"단위\s*:?\s*[^)\]]{1,24}")
_UNIT_QTY = re.compile(r"M\s*/\s*T|톤|kg|개|대\b|기\b|set", re.I)


def _carry_units(tables):
    """표마다 단위 캡션을 읽되, 자기 lead 에 없으면 직전에 본 캡션을 물려준다."""
    out, last = [], None
    for t in tables:
        blob = " ".join([t.get("lead") or ""] + list(t["cols"])
                        + [" ".join(r) for r in t["rows"][:2]])
        caps = _UNIT_CAP.findall(blob)
        d = dict(t)
        if caps:
            last = caps[-1]
        elif last:
            d["lead"] = (t.get("lead") or "") + " (%s)" % last
            d["unit_from_prev"] = True
        out.append(d)
    return out


def _two_row_header(t):
    """머리행이 두 줄인 표(rowspan/colspan 평탄화 결과)를 이어 붙인다."""
    rows = t["rows"]
    if len(rows) < 3 or len(rows[0]) < 3 or len(rows[1]) != len(rows[0]):
        return None
    if any(num_of(c) is not None for c in rows[0] + rows[1]):
        return None
    if [_clean(c) for c in rows[0]] == [_clean(c) for c in rows[1]]:
        return None
    if not any(num_of(c) is not None for r in rows[2:] for c in r):
        return None
    cols = []
    for a, b in zip(rows[0], rows[1]):
        a, b = (a or "").strip(), (b or "").strip()
        cols.append(a if _clean(a) == _clean(b) or not b else (a + " " + b).strip())
    if len({_clean(c) for c in cols}) != len(cols):
        return None
    d = dict(t)
    d["cols"], d["rows"] = cols, rows[2:]
    d["header_synth"] = "2row"
    return d


def _scaled(v, mul):
    x = num_of(v)
    if x is None:
        return None
    x = x * mul
    return int(x) if float(x).is_integer() else round(x, 3)


# ── 부문 이름 → 발전원 ──────────────────────────────────────

def seg_domain(name):
    """부문·사업명 원문 → 발전원 id(NUKE/THERMAL/RENEW/GRID/IND) 또는 None. 원문 이름은 따로 싣는다."""
    return knuke_contracts.domain_of(name)


# ── 수주표 ─────────────────────────────────────────────────

def parse_orders_table(t):
    """수주표 한 장 → {shape, cur, unit_seen, rows}. 네 모양을 한 함수로 가른다.

    award 모양이 이 탭의 핵심 — 발주처·사업명·계약기간 열을 행마다 읽어 낸다."""
    cols = [_clean(c) for c in t["cols"]]
    cur, mul, seen = unit_of(t.get("lead"), t.get("cols"))
    caps = _UNIT_CAP.findall(" ".join([t.get("lead") or ""] + list(t["cols"])))
    qty_unit = bool(caps and _UNIT_QTY.search(caps[-1]) and not seen)

    def col(*keys):
        cand = [i for i, c in enumerate(cols) if all(k in c for k in keys)]
        if not cand:
            return None
        amt = [i for i in cand if "금액" in cols[i]]
        return (amt or cand)[0]

    def first(*cands):
        for c in cands:
            if c is not None:
                return c
        return None

    i_client = first(col("발주처"), col("발주자"), col("계약상대"), col("수요처"), col("고객"), col("거래처"))
    i_name = first(col("사업명"), col("공사명"), col("계약명"), col("프로젝트"), col("주요계약명"),
                   col("사업내용"), col("품목"), col("공종"))
    i_open = first(col("기초", "금액"), col("기초"), col("전기이월"))
    i_new = first(col("신규", "금액"), col("신규"), col("증감"), col("당기수주"))
    i_done = first(col("완성공사액"), col("기납품", "금액"), col("기납품"), col("기성"),
                   col("매출계상"), col("완성"))
    i_gross = first(col("기본도급액"), col("수주총액", "금액"), col("수주총액"), col("도급액"),
                    col("계약금액"), col("수주금액"), col("수주액"))
    i_close = first(col("계약잔액"), col("수주잔고", "금액"), col("수주잔고"), col("수주잔액"),
                    col("잔여수주"), col("기말", "금액"), col("기말"), col("잔액"))
    i_start = first(col("최초계약일"), col("계약일"), col("수주일자"), col("수주일"), col("착수일"),
                    col("시작일"), col("계약체결일"))
    i_end = first(col("종료일"), col("납기"), col("완공"), col("준공"), col("인도예정"),
                  col("계약종료"), col("종료"))
    if i_close is None and i_gross is None:
        return None
    if i_client is not None and (i_start is not None or i_end is not None) \
            and (i_close is not None or i_gross is not None):
        shape = "award"
    elif i_open is not None and i_close is not None:
        shape = "roll" if (i_new is not None or i_done is not None) else "openclose"
    elif i_gross is not None and i_close is not None:
        shape = "item" if (i_start is not None or i_end is not None) else "gross"
    elif i_close is not None:
        shape = "balance"
    else:
        return None

    num_idx = {i for i in (i_open, i_new, i_done, i_gross, i_close, i_start, i_end, i_client, i_name)
               if i is not None}
    other_name = [i for i in range(len(cols)) if i not in num_idx
                  and not re.search(r"수량|금액|비중|비고|번호|순번|구분$", cols[i] or "")]
    rows = []
    for r in t["rows"]:
        def cell(i):
            return r[i].strip() if i is not None and i < len(r) else ""

        def g(i):
            return _scaled(r[i], mul) if i is not None and i < len(r) else None
        client = cell(i_client)
        name = cell(i_name)
        # 사업명 열이 따로 없으면 이름 아닌 앞쪽 열들을 이어 붙인다
        if not name:
            labs = [cell(i) for i in other_name if cell(i) and num_of(cell(i)) is None]
            name = " ".join(dict.fromkeys(labs))
        label = (client + " · " + name).strip(" ·") if client else name
        if not label and not any(g(i) is not None for i in (i_gross, i_close, i_open)):
            continue
        start = cell(i_start)
        end = cell(i_end)
        # 합계 행 판정 — 발주처·사업명뿐 아니라 앞쪽 '구분' 열('합계'·'소계')까지 본다.
        lead_cells = [client, name] + [(r[i] or "").strip() for i in range(min(3, len(r)))
                                       if i not in num_idx]
        is_tot = any(is_total(c) for c in lead_cells if c)
        rec = {"label": label, "total": is_tot,
               "client": client, "name": name,
               "opening": g(i_open), "new": g(i_new), "delivered": g(i_done),
               "gross": g(i_gross), "closing": g(i_close),
               "start": _date(start), "end": _date(end),
               "start_raw": start, "end_raw": end}
        if rec["closing"] is None and rec["gross"] is None and rec["opening"] is None:
            continue
        if rec["delivered"] is not None and rec["delivered"] < 0:
            rec["delivered"] = -rec["delivered"]
        rec["domain"] = seg_domain(name) or seg_domain(label)
        rows.append(rec)
    if not rows:
        return None
    return {"shape": shape, "cur": cur, "unit_seen": seen, "qty_unit": qty_unit, "rows": rows,
            "has_client": i_client is not None, "has_period": (i_start is not None or i_end is not None),
            "unit_from_prev": bool(t.get("unit_from_prev")),
            "cols": t["cols"], "lead": (t.get("lead") or "")[-200:],
            "security_note": bool(_SECURITY.search(t.get("lead") or ""))}


_DATE = re.compile(r"(\d{4})[-.\s/년]+\s*(\d{1,2})[-.\s/월]+\s*(\d{1,2})|(\d{4})[-.\s/년]+\s*(\d{1,2})")


def _date(s):
    """`2016.03.18`·`2033-10-31`·`2016년 3월` 을 ISO 로. 못 읽으면 None(fail-closed)."""
    s = (s or "").strip()
    if not s or "까지" in s and not re.search(r"\d{4}", s):
        return None
    m = _DATE.search(s)
    if not m:
        return None
    if m.group(1):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        y, mo, d = int(m.group(4)), int(m.group(5)), 1
    if not (1990 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return "%04d-%02d-%02d" % (y, mo, d)


# ── 매출실적(부문 × 내수/수출) ──────────────────────────────

_KIND_WORDS = {"수출": "수출", "해외": "수출", "국내": "내수", "내수": "내수", "합계": "합계",
               "계": "합계", "소계": "합계"}
_KIND_REAL = ("수출", "해외", "국내", "내수")


def parse_revenue_table(t):
    """내수/수출이 갈린 매출 표 → {cur, rows:[{seg, item, kind, val, vals, segdomain}]}."""
    cur, mul, seen = unit_of(t.get("lead"), t.get("cols"))
    votes = {}
    for r in t["rows"]:
        for i, c in enumerate(r[:5]):
            if _clean(c) in _KIND_REAL:
                votes[i] = votes.get(i, 0) + 1
    if not votes:
        return None
    i_kind = max(votes, key=lambda i: votes[i])
    rows = []
    for r in t["rows"]:
        if i_kind >= len(r):
            continue
        k = _KIND_WORDS.get(_clean(r[i_kind]))
        if not k:
            continue
        labels = [c.strip() for c in r[:i_kind] if c.strip()]
        if not labels:
            labels = [c.strip() for c in r[i_kind + 1:i_kind + 2] if c.strip() and num_of(c) is None]
        vals = [_scaled(v, mul) for v in r[i_kind + 1:] if num_of(v) is not None or v.strip() in ("", "-")]
        nums = [v for v in vals if v is not None]
        if not nums:
            continue
        seg = labels[0] if labels else ""
        rows.append({"seg": seg, "item": " ".join(labels[1:]), "kind": k,
                     "val": nums[0], "vals": vals,
                     "segdomain": seg_domain(seg) or seg_domain(" ".join(labels))})
    if not rows:
        return None
    if re.search(r"판매경로|판매방법|판매전략", " ".join(t["cols"])):
        return None
    return {"cur": cur, "unit_seen": seen, "i_kind": i_kind, "rows": rows,
            "period_cols": t["cols"][i_kind + 1:], "cols": t["cols"],
            "lead": (t.get("lead") or "")[-200:]}


_SALES_LEAD = re.compile(r"매출\s*실적|매출에\s*관한\s*사항|부문별\s*매출|매출\s*현황|매출\s*구성")


def parse_segment_sales(t):
    """내수/수출이 없는 매출실적 표 → 부문(발전원)별 금액·비중."""
    cols = [_clean(c) for c in t["cols"]]
    lead = t.get("lead") or ""
    if not (_SALES_LEAD.search(lead) or any("매출" in c for c in cols)):
        return None
    if any(_clean(c) in _KIND_REAL for r in t["rows"][:8] for c in r[:4]):
        return None
    cur, mul, seen = unit_of(lead, t.get("cols"))
    i_amt = next((i for i, c in enumerate(cols)
                  if i >= 1 and "비중" not in c and "비율" not in c
                  and sum(1 for r in t["rows"] if i < len(r) and num_of(r[i]) is not None) >= 2), None)
    if i_amt is None:
        return None
    i_pct = next((i for i, c in enumerate(cols) if i > i_amt and ("비중" in c or "비율" in c)), None)
    val_idx = [i for i in range(i_amt, len(cols)) if "비중" not in cols[i] and "비율" not in cols[i]]
    rows = []
    for r in t["rows"]:
        if i_amt >= len(r):
            continue
        v = _scaled(r[i_amt], mul)
        if v is None:
            continue
        labels = [c.strip() for c in r[:i_amt] if c.strip() and num_of(c) is None]
        seg = labels[0] if labels else ""
        if not seg:
            continue
        item = " ".join(dict.fromkeys(labels[1:]))
        rows.append({"seg": seg, "item": item,
                     "val": v, "total": is_total(seg) or is_total(item),
                     "vals": [_scaled(r[i], mul) if i < len(r) else None for i in val_idx],
                     "pct": (num_of(r[i_pct]) if i_pct is not None and i_pct < len(r) else None),
                     "segdomain": seg_domain(seg) or seg_domain(" ".join(labels))})
    if not rows:
        return None
    return {"cur": cur, "unit_seen": seen, "rows": rows, "cols": t["cols"],
            "period_cols": [t["cols"][i] for i in val_idx],
            "lead": (t.get("lead") or "")[-200:]}


# ── 수집 ───────────────────────────────────────────────────

_PARENT = re.compile(r"지배회사의\s*내용|지배회사\s*기준|당사의\s*수주|별도")
_SUB = re.compile(r"종속회사의\s*내용")


def _orders_total(o):
    tot = [r for r in o["rows"] if r["total"]]
    if tot and tot[0].get("closing") is not None:
        return tot[0]["closing"]
    vals = [r["closing"] for r in o["rows"] if not r["total"] and r.get("closing") is not None]
    return sum(vals) if vals else 0


def _pick_orders(orders):
    """여러 수주표 중 회사 본체(금액·행 많은 것)를 대표로. award 를 우대한다."""
    if not orders:
        return None

    def key(o):
        lead = o.get("lead") or ""
        mark = 1 if (_PARENT.search(lead) and not _SUB.search(lead)) else (-1 if _SUB.search(lead) else 0)
        money = bool(o.get("unit_seen")) and not o.get("qty_unit")
        award = o["shape"] == "award"
        return (money, award, mark, o["shape"] != "balance", _orders_total(o), len(o["rows"]))
    best = dict(max(orders, key=key))
    lead = best.get("lead") or ""
    best["scope"] = "parent" if _PARENT.search(lead) else ("sub" if _SUB.search(lead) else "unknown")
    return best


def _keep(t):
    blob = " ".join(t["cols"]) + " " + (t.get("lead") or "")[-200:]
    return bool(re.search(r"수주|매출|발주|거래처|매출처|고객|납기|잔고|잔액|계약", blob))


def collect_one(rec, quarter, force=False, log=sys.stderr):
    st = rec["stock"]
    path = os.path.join(CACHE, st, quarter + ".json")
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    out = {"stock": st, "name": rec.get("name", ""), "quarter": quarter, "ok": False, "note": ""}
    start, end = report_window(quarter)
    try:
        reports = pick_report(search_reports(st, start, end, report_kind(quarter)), quarter)
    except Exception as e:
        out["note"] = "검색 실패: %s" % e
        return out
    if not reports:
        out["note"] = "정기보고서 없음"
        return out
    rcp, title = reports[0]
    out["rcp"], out["title"] = rcp, title
    nodes = toc(rcp)
    found = find_sections(nodes, SECTIONS)
    if "sales" not in found:
        out["note"] = "매출·수주 절 없음"
        return out
    html = fetch_section(found["sales"])
    tables = _headered(_carry_units(parse_tables(html)))
    parsed = [(t, parse_orders_table(t)) for t in tables]
    orders = [o for _, o in parsed if o]
    rest = [t for t, o in parsed if not o]
    revenue = [x for x in (parse_revenue_table(t) for t in rest) if x]
    segsales = [x for x in (parse_segment_sales(t) for t in rest) if x]
    out["orders"] = _pick_orders(orders)
    out["orders_all"] = orders or []
    out["revenue"] = max(revenue, key=lambda r: len(r["rows"])) if revenue else None
    out["revenue_all"] = revenue or []
    out["segment_sales"] = max(segsales, key=lambda r: len(r["rows"])) if segsales else None
    out["raw_tables"] = [{"cols": t["cols"], "rows": t["rows"], "lead": (t.get("lead") or "")[-200:]}
                         for t in tables if _keep(t)]
    txt = re.sub(r"<[^>]+>", " ", html)
    out["security_note"] = bool(_SECURITY.search(txt))
    out["ok"] = bool(out["orders"] or out["revenue"] or out["segment_sales"])
    if not out["ok"]:
        out["note"] = "수주·매출표 인식 실패 — 머리행 %s" % [t["cols"] for t in tables][:3]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write(path, json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    log.write("%s %s %s %s\n" % (st, quarter, "ok" if out["ok"] else "FAIL",
                                 (out["orders"] or {}).get("shape", "-")))
    log.flush()
    return out


def quarters(latest, n=8):
    y, q = int(latest[:4]), int(latest[-1])
    out = []
    for _ in range(n):
        out.append("%dQ%d" % (y, q))
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return list(reversed(out))


def collect(rows, qs, force=False):
    for rec in rows:
        for q in qs:
            try:
                collect_one(rec, q, force)
            except Exception as e:
                sys.stderr.write("[warn] %s %s %s\n" % (rec["stock"], q, e))


def _sum_rows(rows, field, domains=None):
    vals = [r[field] for r in rows
            if not r["total"] and r.get(field) is not None and (domains is None or r.get("domain") in domains)]
    return sum(vals) if vals else None


_FY_COL = re.compile(r"20\d\d년|제\d+기")
_PART_YEAR = re.compile(r"반기|분기|누적|개월|기중|비중|비율")


def _is_fy(col):
    c = _clean(col)
    return bool(_FY_COL.search(c)) and not _PART_YEAR.search(c)


def _fy_from(rv):
    """매출 표에서 온전한 1년 열의 총매출 → (값, 열이름). 잔고 커버리지의 분모."""
    if not rv:
        return None, None
    cols = rv.get("period_cols") or []
    rows = rv.get("rows") or []
    idx = [i for i, c in enumerate(cols) if _is_fy(c)]

    def ok(r):
        return len(r.get("vals") or []) == len(cols)
    for i in idx:
        grand = [r for r in rows if r.get("kind") == "합계" and is_total(r.get("seg", "")) and ok(r)]
        per = [r for r in rows if r.get("kind") == "합계" and not is_total(r.get("seg", "")) and ok(r)]
        use = grand or per or [r for r in rows if r.get("kind") in ("내수", "수출") and ok(r)]
        vals = [r["vals"][i] for r in use if r["vals"][i] is not None]
        if vals:
            return sum(vals), cols[i]
    return None, None


def _fy_seg(ss):
    if not ss:
        return None, None
    cols = ss.get("period_cols") or []
    rows = [r for r in (ss.get("rows") or []) if len(r.get("vals") or []) == len(cols)]
    for i in (i for i, c in enumerate(cols) if _is_fy(c)):
        grand = [r for r in rows if is_total(r["seg"])]
        sub = [r for r in rows if r.get("total") and not is_total(r["seg"])]
        base = [r for r in rows if not r.get("total")]
        for use in (grand, sub, base):
            vals = [r["vals"][i] for r in use if r["vals"][i] is not None]
            if vals:
                return sum(vals), cols[i]
    return None, None


def _sum_rev(rrows, kind):
    vals = [(r["vals"] or [None])[0] for r in rrows if r["kind"] == kind]
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def build(rows, qs):
    """캐시 → reports.json. 회사 × 분기의 수주잔고·발주처 집중도·발전원별 잔고·부문매출."""
    out = {}
    for rec in rows:
        st = rec["stock"]
        per_q = {}
        for q in qs:
            path = os.path.join(CACHE, st, q + ".json")
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if not d.get("ok"):
                per_q[q] = {"ok": False, "note": d.get("note", "")}
                continue
            o = d.get("orders") or {}
            orows = o.get("rows") or []
            tot = [r for r in orows if r["total"]]
            money = bool(o.get("unit_seen")) and not o.get("qty_unit")
            backlog = (tot[0]["closing"] if tot and tot[0].get("closing") is not None
                       else _sum_rows(orows, "closing")) if money else None
            # 발전원별 잔고 — award 표의 행별 계약잔액을 발전원으로 묶는다(합계행 제외).
            dom_backlog = {}
            if money and o.get("shape") == "award":
                for r in orows:
                    if r["total"] or r.get("closing") is None:
                        continue
                    dom_backlog[r.get("domain") or "UNCL"] = \
                        dom_backlog.get(r.get("domain") or "UNCL", 0) + r["closing"]
            # 발주처 집중도 — 행별 계약잔액을 발주처로 묶는다.
            client_backlog = {}
            if money and o.get("has_client"):
                for r in orows:
                    if r["total"] or r.get("closing") is None or not r.get("client"):
                        continue
                    client_backlog[r["client"]] = client_backlog.get(r["client"], 0) + r["closing"]
            # 호기·사업 타임라인 — 계약기간이 있는 award 행만.
            timeline = [{"client": r["client"], "name": r["name"], "domain": r.get("domain"),
                         "start": r["start"], "end": r["end"], "closing": r.get("closing"),
                         "gross": r.get("gross")}
                        for r in orows if not r["total"] and (r.get("start") or r.get("end"))]
            rv = d.get("revenue") or {}
            rrows = rv.get("rows") or []
            dom = _sum_rev(rrows, "내수")
            exp = _sum_rev(rrows, "수출")
            ss = d.get("segment_sales") or {}
            srows = [r for r in (ss.get("rows") or []) if not r["total"]]
            per_q[q] = {
                "ok": True, "rcp": d.get("rcp"), "shape": o.get("shape"),
                "cur": o.get("cur"), "unit_seen": o.get("unit_seen"),
                "has_client": o.get("has_client", False), "has_period": o.get("has_period", False),
                "backlog": backlog,
                "opening": ((tot[0]["opening"] if tot and tot[0].get("opening") is not None
                             else _sum_rows(orows, "opening"))) if money else None,
                "delivered": _sum_rows(orows, "delivered") if money else None,
                "gross": _sum_rows(orows, "gross") if money else None,
                "unit_note": ("" if money else
                              ("수주표 단위가 금액이 아님(%s)" % (o.get("cur") or "미상") if o.get("qty_unit")
                               else "수주표 단위 캡션을 못 읽음") if o else ""),
                "unit_from_prev": bool(o.get("unit_from_prev")),
                "orders_scope": o.get("scope"),
                "dom_backlog": dom_backlog,
                "client_backlog": client_backlog,
                "timeline": timeline,
                "n_orders": len([r for r in orows if not r["total"]]),
                "segments": [{"label": r["label"], "client": r.get("client"), "name": r.get("name"),
                              "domain": r.get("domain"), "closing": r["closing"],
                              "gross": r.get("gross"), "delivered": r.get("delivered"),
                              "start": r.get("start"), "end": r.get("end"),
                              "start_raw": r.get("start_raw"), "end_raw": r.get("end_raw")}
                             for r in orows if not r["total"]],
                "revenue_fy": (_fy_from(rv)[0] or _fy_seg(ss)[0]),
                "revenue_fy_col": (_fy_from(rv)[1] or _fy_seg(ss)[1]),
                "revenue_domestic": dom, "revenue_export": exp,
                "revenue_segments": [{"seg": r["seg"], "item": r["item"], "kind": r["kind"],
                                      "segdomain": r["segdomain"], "val": r["val"]} for r in rrows],
                "sales_segments": [{"seg": r["seg"], "item": r["item"], "segdomain": r["segdomain"],
                                    "val": r["val"], "pct": r.get("pct")} for r in srows],
                "security_note": d.get("security_note", False),
            }
        if per_q:
            out[st] = {"stock": st, "name": rec.get("name", ""), "role": rec.get("role"),
                       "quarters": per_q}
    write_asset("reports.json", {"n": len(out), "quarters": qs, "companies": out})
    return out


def load():
    try:
        return load_asset("reports.json")
    except FileNotFoundError:
        return {"companies": {}, "quarters": []}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--quarter", default=None)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    rows = load_universe()
    if a.only:
        want = set(a.only.split(","))
        rows = [r for r in rows if r["stock"] in want]
    qs = quarters(a.quarter or latest_quarter(), a.n)
    if a.collect:
        collect(rows, qs, a.force)
    if a.build:
        res = build(rows, qs)
        ok = sum(1 for c in res.values() for q in c["quarters"].values() if q.get("ok"))
        print("회사 %d · 분기레코드 %d" % (len(res), ok))
        for st, c in list(res.items()):
            last = [q for q in qs if q in c["quarters"] and c["quarters"][q].get("ok")]
            if last:
                v = c["quarters"][last[-1]]
                print("  %s %-16s %s 잔고 %s (%s) 타임라인 %d 발주처 %d"
                      % (st, c["name"][:16], last[-1], v["backlog"], v["shape"],
                         len(v["timeline"]), len(v["client_backlog"])))


if __name__ == "__main__":
    sys.exit(main())
