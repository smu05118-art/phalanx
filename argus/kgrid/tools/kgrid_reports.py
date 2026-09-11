#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kgrid_reports — 정기보고서 「II. 사업의 내용」에서 전력기기 회사의 분기 지표를 읽는다.

이 산업의 표는 조선·방산과 세 가지가 다르다(FINDINGS §2·§3 실측):

  1. **표가 종속회사별로 여러 벌** 온다. 엘에스일렉트릭 II-4 에는 수주표가 `[LS ELECTRIC]`,
     `[LS메탈]`, `[LS이모빌리티솔루션]` … 으로 줄줄이 붙는다. 대괄호 라벨을 읽어 `entity` 로
     붙이고, 본체 표를 골라 대표값으로 쓴다. 나머지는 버리지 않고 `orders_all` 에 남긴다
     (LS메탈은 STS관·동관이라 전력망이 아니다 — 화면에서 갈라 보인다).
  2. **통화가 섞인다.** 일진전기 수주표 캡션이 `(단위 : 천USD )`다. 환율을 원문에서 얻을 수
     없으므로 **환산하지 않는다** — 통화를 값과 함께 싣고, 커버리지(잔고÷연매출)는 통화가
     같을 때만 만든다(`kgrid_lib.coverage` 가 fail-closed 로 막는다).
  3. **매출처가 전력회사 실명**이다. 다만 같은 표에 실명·익명·고객분류·관계회사가 섞인다
     (HD현대일렉트릭 `NextEra Energy`·`사우디 전력청` vs 산일전기 `전력 산업`·`조선 산업`,
     엘에스일렉트릭 `LS ELECTRIC AMERICA 41.7%` = 자기 자회사). 근거 등급을 매겨 싣는다.

같이 읽는 것:
  · **매출실적**(부문 × 내수/수출) — 해외비중의 근거. 부문 이름은 회사마다 다르므로
    grid/other 로만 정규화하고 **원문 이름을 반드시 함께** 남긴다.
  · **지역별 매출** — 일진전기 「(2) 지역별 매출 현황」(국내·미주·유럽·아시아,호주·기타).
    스펙 §분류의 지역 축이 표로 서는 유일한 원천이다.
  · **수요 낱말** — II절 본문의 `데이터센터`·`신재생`·`북미`·`중동`·`노후 전력망` 출현.
    추정이 아니라 원문 인용이다(스펙 §5). HVDC 는 찾되 없으면 없다고 적는다(스펙 §6).

원문 표(cols·rows·lead)를 캐시에 그대로 남긴다 — 파서가 자라면 재수집 없이 다시 뽑는다(COMMON §0-4).

    python3 kgrid_reports.py --collect [--quarter 2026Q2] [--n 6] [--only 267260]
    python3 kgrid_reports.py --build
"""
import argparse
import html
import json
import os
import re
import sys

from kgrid_lib import (ASSETS, atomic_write, coverage, fetch_section, find_sections, is_total,
                       latest_quarter, load_asset, num_of, parse_tables, pick_report, q_of,
                       report_kind, report_window, search_reports, toc, unit_of, write_asset)
from kgrid_universe import load as load_universe

CACHE = os.path.join(ASSETS, "reports_cache")

SECTIONS = [
    ("sales", ["매출 및 수주상황", "수주상황", "매출실적"]),
    ("products", ["주요 제품 및 서비스", "주요 제품", "주요제품"]),
    ("overview", ["사업의 개요"]),
    ("etc", ["기타 참고사항"]),
]


def _clean(s):
    return re.sub(r"[\s　]+", "", s or "")


# ── 표 다듬기(kdef 에서 검증된 층) ──────────────────────────

def _headered(tables):
    """머리행을 못 잡은 표를 살린다.

    HD현대일렉트릭 II-4 는 표가 **전부** `cols=[]` 로 온다(실측 — 매출실적·제품군별 매출·
    주요매출처·수주상황 네 장 모두). 그대로 버리면 이 회사가 통째로 사라진다.
    첫 행의 셀이 모두 비숫자면 그것을 머리행으로 쓴다(fail-closed: 아니면 버린다)."""
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
        dup = len({_clean(c) for c in rows[0]}) != len(rows[0])
        if dup:
            d = _two_row_header(t)
            if d:
                out.append(d)
                continue
            # 두 줄 머리행이 아닌데 첫 줄에 같은 이름이 두 번 나오는 표가 있다 —
            # HD현대일렉트릭 매출실적 `사업부문|매출유형|품 목|품 목|제10기…`(rowspan 평탄화).
            # 여기서 버리면 그 회사의 내수/수출이 통째로 사라진다(실측). 이름을 갈라서 살린다.
            if not any(num_of(c) is not None for r in rows[1:] for c in r):
                continue
            seen, cols = {}, []
            for c in rows[0]:
                k = _clean(c)
                seen[k] = seen.get(k, 0) + 1
                cols.append(c if seen[k] == 1 else "%s#%d" % (c, seen[k]))
            d = dict(t)
            d["cols"], d["rows"] = cols, rows[1:]
            d["header_synth"] = "dedup"
            out.append(d)
            continue
        if not any(num_of(c) is not None for r in rows[1:] for c in r):
            continue
        d = dict(t)
        d["cols"], d["rows"] = list(rows[0]), rows[1:]
        d["header_synth"] = True
        out.append(d)
    return out


def _two_row_header(t):
    """머리행이 **두 줄**인 표(rowspan/colspan 평탄화 결과)를 살린다.

    엘에스일렉트릭 수주표가 이 모양이 될 수 있다 —
    `이월 수주잔액|이월 수주잔액|당기 수주금액|…` + `수량|금액|수량|금액|…`.
    첫 줄만 쓰면 수량 열을 금액으로 읽는다."""
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


_UNIT_CAP = re.compile(r"단위\s*:?\s*[^)\]]{1,24}")
# 금액이 아닌 단위 — LS메탈 수주표는 `(단위 : 톤, 억원 )`이라 수량 열이 톤이다.
# 캡션에 금액 단위가 **같이** 있으면 금액 열은 살아 있다(그래서 unit_seen 이 True 면 통과).
_UNIT_QTY_ONLY = re.compile(r"^(?:단위\s*:?\s*)?(?:M\s*/\s*T|톤|kg|개|대|EA|set|세트|면|회선)\s*$", re.I)


def _carry_units(tables):
    """표마다 단위 캡션을 읽되, 자기 lead 에 없으면 **직전에 본 캡션**을 물려준다.

    이 산업에서 특히 중요하다 — 엘에스일렉트릭·HD현대일렉트릭 모두 단위 캡션이 **한 줄짜리
    껍데기 표**(`(기준일 : 2026.06.30) | (단위 : 억원 )`)로 따로 오고, 정작 수주표 자신의
    lead 에는 없다(실측). 그대로 두면 7조짜리 잔고가 '단위 미확인'으로 빠진다.
    다만 kce_parse 가 lead 에 앞 문맥을 길게 붙여 주므로 대개는 lead 안에 들어 있다 —
    물려준 경우에만 표시를 남긴다."""
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


def _scaled(v, mul):
    x = num_of(v)
    if x is None:
        return None
    x = x * mul
    return int(x) if float(x).is_integer() else round(x, 3)


# ── 종속회사 라벨 ───────────────────────────────────────────
# 엘에스일렉트릭은 표 앞에 `[LS ELECTRIC]`·`[LS메탈]` 을 달아 어느 회사 표인지 밝힌다.
# 이것을 못 읽으면 전력기기 잔고와 동관(LS메탈) 잔고가 한 덩어리가 된다.
_ENTITY = re.compile(r"[\[【]\s*([^\[\]【】]{2,40}?)\s*[\]】]\s*$")
_ENTITY_ANY = re.compile(r"[\[【]\s*([^\[\]【】]{2,40}?)\s*[\]】]")


def entity_of(lead):
    """표 바로 앞의 대괄호 라벨 → 종속회사 이름(없으면 "")."""
    tail = re.sub(r"\s+", " ", (lead or "")).strip()
    # 캡션 껍데기(`(기준일 : …) (단위 : 억원 )`)가 뒤에 붙어 있을 수 있으니 걷어 낸다.
    tail = re.sub(r"\((?:기준일|단위)[^)]*\)\s*$", "", tail).strip()
    m = _ENTITY.search(tail)
    if m:
        return m.group(1).strip()
    ms = _ENTITY_ANY.findall(tail[-160:])
    return ms[-1].strip() if ms else ""


# ── 부문 이름 정규화 ────────────────────────────────────────
# 전력망인가 아닌가만 가른다. 원문 이름은 언제나 함께 남긴다 — 정규화가 틀려도 되짚을 수 있게.
_SEG_GRID = re.compile(
    r"전력|전기전자|중전기|송전|배전|변전|T&D|수배전|개폐|차단|변압|전선|케이블|"
    r"인프라|전력시스템|전력기기|스마트그리드|계통", re.I)
_SEG_OTHER = re.compile(
    r"자동화|금속|동관|STS|신동|이모빌리티|e-?mobility|EV|2차전지|이차전지|자동차|"
    r"철도|건설|건축|중공업건설|IT\b|정보통신|통신케이블|광케이블|소재|기타부문", re.I)


def seg_kind(name):
    """부문 원문 이름 → 'grid'|'other'|None."""
    n = _clean(name)
    if not n:
        return None
    g, o = bool(_SEG_GRID.search(n)), bool(_SEG_OTHER.search(n))
    if g and not o:
        return "grid"
    if o and not g:
        return "other"
    return None      # 둘 다이거나 모르면 판정하지 않는다(화면에서 '미상')


# ── 수주표 ─────────────────────────────────────────────────

def parse_orders_table(t):
    """수주표 한 장 → {shape, cur, entity, rows}. 네 모양을 한 함수로 가른다.

    roll      기초(이월)+당기수주−기납품=기말 — 엘에스일렉트릭(12열)
    gross     수주총액−기납품=잔고 — HD현대일렉트릭(1행)·일진전기(국내/해외 분리)
    item      gross 인데 수주일자·납기가 있어 품목 단위로 읽히는 것
    balance   잔고 한 줄만
    """
    cols = [_clean(c) for c in t["cols"]]
    cur, mul, seen = unit_of(t.get("lead"), t.get("cols"))
    caps = _UNIT_CAP.findall(" ".join([t.get("lead") or ""] + list(t["cols"])))
    qty_only = bool(caps and _UNIT_QTY_ONLY.search(caps[-1].strip()) and not seen)

    def col(*keys):
        """keys 를 모두 품은 열. 금액 열을 수량 열보다 먼저 고른다(`수주잔고 수량|금액`).

        엘에스일렉트릭 표는 수량 열이 금액 열 **앞**에 오므로 이 우선순위가 없으면
        잔고 69,998억이 `-`(수량 빈칸)로 읽힌다."""
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

    i_open = first(col("이월", "금액"), col("이월"), col("기초", "금액"), col("기초"))
    i_new = first(col("당기수주", "금액"), col("당기수주"), col("신규", "금액"), col("신규"))
    i_done = first(col("기납품", "금액"), col("기납품"), col("매출인식"))
    i_gross = first(col("수주총액", "금액"), col("수주총액"), col("계약금액"), col("수주금액"))
    i_close = first(col("수주잔고", "금액"), col("수주잔고"), col("수주잔액"),
                    col("기말", "금액"), col("기말"), col("잔액"))
    i_date = first(col("수주일자"), col("계약일자"), col("수주일"))
    i_due = first(col("납기"), col("인도예정"), col("완공예정"), col("공사기간"))
    # `당기 수주금액` 열이 `수주금액` 으로도 잡혀 i_gross 와 겹칠 수 있다 — 겹치면 신규 쪽을 남긴다.
    if i_new is not None and i_gross == i_new:
        i_gross = None
    if i_close is None and i_gross is None:
        return None
    if i_open is not None and i_close is not None:
        shape = "roll" if (i_new is not None or i_done is not None) else "openclose"
    elif i_gross is not None and i_close is not None:
        shape = "item" if (i_date is not None or i_due is not None) else "gross"
    elif i_close is not None:
        shape = "balance"
    else:
        return None
    num_idx = {i for i in (i_open, i_new, i_done, i_gross, i_close, i_date, i_due) if i is not None}
    name_idx = [i for i in range(len(cols)) if i not in num_idx
                and not re.search(r"수량|금액|비고", cols[i] or "")]
    rows = []
    for r in t["rows"]:
        labels = [r[i].strip() for i in name_idx if i < len(r) and r[i].strip()]
        labels = [x for x in dict.fromkeys(labels)]
        if not labels:
            continue

        def g(i):
            return _scaled(r[i], mul) if i is not None and i < len(r) else None
        seg = labels[0]
        item = labels[-1] if len(labels) > 1 else ""
        label = (seg + (" · " + item[:40] if item else "")).strip()
        # 소계 판정 — 라벨 중 **하나라도** 계/합계면 소계다. 일진전기 수주표는
        # `전력선 등|계` 라는 품목 소계와 `합 계|계` 라는 총계가 같이 온다. `전력선 등|계` 를
        # 낱 행으로 두고 다 더하면 잔고가 정확히 두 배가 된다(실측).
        is_tot = any(is_total(x) for x in labels)
        all_tot = bool(labels) and all(is_total(x) for x in labels)
        rec = {"label": label, "seg": seg, "item": item,
               "total": is_tot, "grand": all_tot,
               "opening": g(i_open), "new": g(i_new), "delivered": g(i_done),
               "gross": g(i_gross), "closing": g(i_close),
               "order_date": (r[i_date].strip() if i_date is not None and i_date < len(r) else ""),
               "due": (r[i_due].strip() if i_due is not None and i_due < len(r) else "")}
        if rec["closing"] is None and rec["gross"] is None and rec["opening"] is None:
            continue
        if rec["delivered"] is not None and rec["delivered"] < 0:
            rec["delivered"] = -rec["delivered"]
        # 일진전기는 **행 자체가 국내/해외**다(`전력선 등|국내`). 소계 행(`계`)은 total 로 잡힌다.
        rec["area"] = ("dom" if re.search(r"^(국내|내수)$", _clean(item) or _clean(seg)) else
                       "ovs" if re.search(r"^(해외|수출)$", _clean(item) or _clean(seg)) else None)
        rec["kind"] = seg_kind(rec["seg"]) or seg_kind(rec["item"])
        rows.append(rec)
    if not rows:
        return None
    return {"shape": shape, "cur": cur, "unit_seen": seen, "qty_only": qty_only, "rows": rows,
            "entity": entity_of(t.get("lead")),
            "unit_from_prev": bool(t.get("unit_from_prev")),
            "cols": t["cols"], "lead": (t.get("lead") or "")[-240:]}


# ── 매출실적(부문 × 내수/수출) ──────────────────────────────

_KIND_WORDS = {"수출": "수출", "해외": "수출", "국내": "내수", "내수": "내수", "합계": "합계",
               "계": "합계", "소계": "합계"}
_KIND_REAL = ("수출", "해외", "국내", "내수")
_CUST_COL = re.compile(r"매출처|거래처|고객|발주처")


def parse_revenue_table(t):
    """내수/수출이 갈린 매출 표 → {rows:[{seg, item, kind, val, vals}]}.

    `수출/내수`가 **셀 값으로** 오는 열을 찾아 기준으로 삼는다 — 열 이름을 믿지 않는다
    (엘에스일렉트릭은 `품 목` 열이 두 번 나오고 그 두 번째가 수출/내수다).
    `판매경로 별 매출비중`(비중 %)은 매출실적이 아니다 — 100 을 매출로 읽으면 연매출이
    몇백원이 된다(엘에스일렉트릭 실측: `사업부문|구분|직판|관계회사|특약점|…|합계`)."""
    cur, mul, seen = unit_of(t.get("lead"), t.get("cols"))
    if re.search(r"판매경로|판매방법|판매전략|판매조직",
                 " ".join(t["cols"]) + " " + (t.get("lead") or "")[-120:]):
        return None
    votes = {}
    for r in t["rows"]:
        for i, c in enumerate(r[:6]):
            if _clean(c) in _KIND_REAL:
                votes[i] = votes.get(i, 0) + 1
    if not votes:
        return None
    i_kind = max(votes, key=lambda i: votes[i])
    # 기간 열에 **수량 열이 끼어 있는** 회사가 있다 — 제룡전기 매출실적은
    # `제41기 반기 수량|제41기 반기 금액|제40기 수량|제40기 금액|…` 이다(실측).
    # 첫 숫자를 값으로 집으면 4,912대가 매출이 되고 연매출이 2,500억 → 25백만원으로 줄어
    # 배수가 5,585년이 된다. 금액이 아닌 열은 **아예 뺀다**.
    val_idx = [i for i in range(i_kind + 1, len(t["cols"]))
               if not re.search(r"수량|비중|비율|비고|증감", _clean(t["cols"][i]))]
    if not val_idx:
        return None
    rows = []
    for r in t["rows"]:
        if i_kind >= len(r):
            continue
        k = _KIND_WORDS.get(_clean(r[i_kind]))
        if not k:
            continue
        labels = [c.strip() for c in r[:i_kind] if c.strip()]
        labels = [x for x in dict.fromkeys(labels)]
        vals = [_scaled(r[i], mul) if i < len(r) else None for i in val_idx]
        nums = [v for v in vals if v is not None]
        if not nums:
            continue
        seg = labels[0] if labels else ""
        rows.append({"seg": seg, "item": " ".join(labels[1:]), "kind": k,
                     "val": nums[0], "vals": vals,
                     "segkind": seg_kind(seg) or seg_kind(" ".join(labels))})
    if not rows:
        return None
    head = " ".join(t["cols"][:max(1, i_kind + 1)])
    basis = "customer" if (_CUST_COL.search(head) or _CUST_COL.search((t.get("lead") or "")[-120:])) \
        else "segment"
    return {"basis": basis, "cur": cur, "unit_seen": seen, "i_kind": i_kind, "rows": rows,
            "entity": entity_of(t.get("lead")),
            "period_cols": [t["cols"][i] for i in val_idx], "cols": t["cols"],
            "lead": (t.get("lead") or "")[-240:]}


_SALES_LEAD = re.compile(r"매출\s*실적|매출에\s*관한\s*사항|부문별\s*매출|매출\s*현황|매출\s*구성|"
                         r"제품군별\s*매출|매출유형별")


def parse_segment_sales(t):
    """내수/수출이 없는 **매출실적** 표 → 부문별 금액.

    HD현대일렉트릭 「(1) 주요 제품군별 매출실적」(전력기기·회전기기·배전기기 外)이 이것이다 —
    제품군별 잔고를 못 얻는 회사에서 **제품군 구성의 유일한 근거**가 된다."""
    cols = [_clean(c) for c in t["cols"]]
    lead = t.get("lead") or ""
    if not (_SALES_LEAD.search(lead) or any("매출" in c for c in cols)):
        return None
    if any(_clean(c) in _KIND_REAL for r in t["rows"][:8] for c in r[:4]):
        return None
    if _CUST_COL.search(" ".join(cols[:2])):
        return None
    if re.search(r"판매경로|판매방법|판매전략|판매조직", " ".join(cols) + " " + lead[-120:]):
        return None
    cur, mul, seen = unit_of(lead, t.get("cols"))
    i_amt = next((i for i, c in enumerate(cols)
                  if i >= 1 and not re.search(r"비중|비율|수량|증감", c)
                  and sum(1 for r in t["rows"] if i < len(r) and num_of(r[i]) is not None) >= 2), None)
    if i_amt is None:
        return None
    i_pct = next((i for i, c in enumerate(cols) if i > i_amt and ("비중" in c or "비율" in c)), None)
    val_idx = [i for i in range(i_amt, len(cols))
               if not re.search(r"비중|비율|수량|증감", cols[i])]
    rows = []
    for r in t["rows"]:
        if i_amt >= len(r):
            continue
        v = _scaled(r[i_amt], mul)
        if v is None:
            continue
        labels = [c.strip() for c in r[:i_amt] if c.strip() and num_of(c) is None]
        labels = [x for x in dict.fromkeys(labels)]
        seg = labels[0] if labels else ""
        if not seg:
            continue
        rows.append({"seg": seg, "item": " ".join(labels[1:]), "val": v,
                     "total": is_total(seg) or is_total(" ".join(labels)),
                     # 기간 열을 다 남긴다 — 커버리지의 분모(연매출)는 당기 누계가 아니라
                     # **직전 사업연도 열**에서 읽어야 추정이 되지 않는다.
                     "vals": [_scaled(r[i], mul) if i < len(r) else None for i in val_idx],
                     "pct": (num_of(r[i_pct]) if i_pct is not None and i_pct < len(r) else None),
                     "segkind": seg_kind(seg) or seg_kind(" ".join(labels))})
    if not rows:
        return None
    return {"cur": cur, "unit_seen": seen, "rows": rows, "cols": t["cols"],
            "entity": entity_of(lead),
            "period_cols": [t["cols"][i] for i in val_idx], "lead": lead[-240:]}


# ── 지역별 매출 ────────────────────────────────────────────

_REGION_LEAD = re.compile(r"지역별\s*매출|지역별\s*실적|매출\s*지역")
_REGION_MAP = [
    ("na", re.compile(r"미주|북미|미국|아메리카|USA|America|캐나다", re.I)),
    ("me", re.compile(r"중동|중근동|사우디|UAE|아랍|카타르|쿠웨이트|Middle\s*East", re.I)),
    ("eu", re.compile(r"유럽|구주|Europe|EU\b", re.I)),
    ("asia", re.compile(r"아시아|동남아|중국|일본|인도|베트남|호주|대양주|Asia", re.I)),
    ("dom", re.compile(r"국내|내수|한국|Korea", re.I)),
]


def region_of(name):
    n = (name or "").strip()
    for key, pat in _REGION_MAP:
        if pat.search(n):
            return key
    return "etc" if n else None


def parse_region_table(t):
    """「지역별 매출 현황」 표 → 지역 키와 금액. 스펙 §분류의 지역 축이 여기서만 표로 선다.

    일진전기 실측: `지역|제19기 반기|제18기 반기|제18기|제17기` ×
    (국내·미주·유럽·아시아,호주·기타·합계)."""
    lead = t.get("lead") or ""
    cols = [_clean(c) for c in t["cols"]]
    if not (_REGION_LEAD.search(lead) or (cols and cols[0] in ("지역", "지역별", "구분지역"))):
        return None
    if not cols or not re.search(r"지역", " ".join(cols[:1]) + lead[-80:]):
        return None
    cur, mul, seen = unit_of(lead, t.get("cols"))
    rows = []
    for r in t["rows"]:
        if not r or not r[0].strip():
            continue
        vals = [_scaled(v, mul) for v in r[1:]]
        nums = [v for v in vals if v is not None]
        if not nums:
            continue
        nm = r[0].strip()
        rows.append({"name": nm, "region": region_of(nm), "val": nums[0], "vals": vals,
                     "total": is_total(nm)})
    if not rows:
        return None
    return {"cur": cur, "unit_seen": seen, "rows": rows, "cols": t["cols"],
            "period_cols": t["cols"][1:], "lead": lead[-200:]}


# ── 주요 매출처 ────────────────────────────────────────────

_CUST_LEAD = re.compile(r"주요\s*매출처|주요\s*거래처|매출처\s*현황|주요\s*고객|매출처\s*및\s*매출비중")
_CUST_BAD = re.compile(r"판매경로|판매방법|판매조직|판매전략")
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")

# 매출처 행의 근거 등급(FINDINGS §3). 실명만 '고객'이다.
_ANON = re.compile(r"^[A-Z]사$|^[가-힣]\s*사$|^[A-Z]{1,2}$|익명|비공개|생략")
_CATEGORY = re.compile(r"산업$|업계$|제조회사|조선회사|대리점|특약점|상사|도매|유통|기타|"
                       r"^내수$|^수출$|^국내$|^해외$|고객사$|End\s*-?user", re.I)
# 관계회사 — 이름에 자기 그룹 상호가 들어간다. 연결 매출과 겹치므로 '최대 외부고객'에서 뺀다.
_REL_HINT = re.compile(r"관계회사|종속회사|계열")


def _evidence(name, group_hint=""):
    n = (name or "").strip()
    if not n:
        return None
    if _ANON.search(n):
        return "anon"
    if _CATEGORY.search(n):
        return "category"
    if group_hint and re.search(re.escape(group_hint), n, re.I):
        return "rel"
    return "named"


def parse_customers(t, group_hint=""):
    """주요 매출처 표 → 이름·비중·근거 등급.

    두 모양이 실측된다:
      (a) `매출처명|금액|비율` — HD현대일렉트릭(금액까지 적는다)
      (b) `사업부문|주요매출처|매출 비중` — 엘에스일렉트릭(종속회사별로 12벌)
    `판매경로 별 매출비중` 표가 같은 lead 에 섞여 오므로 표 **바로 앞** 제목으로 가른다."""
    lead = t.get("lead") or ""
    good = max((m.end() for m in _CUST_LEAD.finditer(lead)), default=-1)
    bad = max((m.end() for m in _CUST_BAD.finditer(lead)), default=-1)
    if good < 0 and any(_CUST_LEAD.search(c or "") for c in t["cols"]):
        good = 0
    if good < 0 or bad > good:
        return None
    cur, mul, _seen = unit_of(lead, t.get("cols"))
    cols = [_clean(c) for c in t["cols"]]
    i_name = next((i for i, c in enumerate(cols) if re.search(r"매출처|거래처|고객", c)), None)
    if i_name is None:
        i_name = 0
    i_pct = next((i for i, c in enumerate(cols) if re.search(r"비중|비율", c)), None)
    i_amt = next((i for i, c in enumerate(cols) if re.search(r"금액|매출액", c)), None)
    i_seg = next((i for i, c in enumerate(cols) if re.search(r"사업부문|부문|구분", c)), None)
    out = []
    heads = {_clean(c) for c in t["cols"]} | {"매출처", "매출처명", "거래처", "구분", "고객",
                                              "품목", "매출액", "주요매출처"}
    for r in t["rows"]:
        if i_name >= len(r):
            continue
        nm = (r[i_name] or "").strip()
        if not nm or _clean(nm) in heads or is_total(nm):
            continue
        share = None
        if i_pct is not None and i_pct < len(r):
            m = _PCT.search(r[i_pct] or "")
            share = float(m.group(1)) if m else num_of(r[i_pct])
        if share is None:
            for c in r[i_name + 1:]:
                m = _PCT.search(c or "")
                if m:
                    share = float(m.group(1))
                    break
        if share is not None and not (0 <= share <= 100):
            share = None
        amt = _scaled(r[i_amt], mul) if i_amt is not None and i_amt < len(r) else None
        seg = (r[i_seg].strip() if i_seg is not None and i_seg < len(r) and i_seg != i_name else "")
        out.append({"name": nm, "share_pct": share, "amount": amt, "seg": seg,
                    "evidence": _evidence(nm, group_hint), "raw": [c for c in r if c.strip()][:4]})
    if not out:
        return None
    return {"cur": cur, "rows": out, "entity": entity_of(lead), "lead": lead[-200:],
            "cols": t["cols"]}


# ── 수요 낱말(본문 인용) ────────────────────────────────────
# 스펙 §5: 수요 축이 본문에 있다. 추정하지 않고 **낱말이 나온 문장을 인용**한다.
DEMAND_WORDS = [
    ("datacenter", re.compile(r"데이터\s*센터|데이터센터|IDC|Data\s*Center", re.I)),
    ("renewable", re.compile(r"신재생|재생에너지|태양광|풍력|ESS\b", re.I)),
    ("na_utility", re.compile(r"북미|미주|미국\s*시장|NextEra|Xcel|Dominion|유틸리티", re.I)),
    ("me_utility", re.compile(r"중동|사우디|UAE|아랍|카타르|쿠웨이트|전력청", re.I)),
    ("aging_grid", re.compile(r"노후\s*(?:화|된)?\s*전력망|노후\s*설비|교체\s*수요|전력망\s*교체|"
                              r"그리드\s*투자|전력망\s*투자", re.I)),
    ("ultra_hv", re.compile(r"초고압|765\s*kV|345\s*kV|154\s*kV|UHV", re.I)),
    ("hvdc", re.compile(r"HVDC|초고압\s*직류", re.I)),
    ("ai_power", re.compile(r"AI\s*(?:데이터|전력|수요)|인공지능\s*(?:데이터|전력)", re.I)),
]


_DIGITS = re.compile(r"[\d,]{3,}")


def _readable(s):
    """인용할 만한 문장인가.

    같은 절에 표도 섞여 있어 그대로 뽑으면 `매출처명 금액 비율 NextEra Energy 347,203 15.9%`
    같은 **표 덤프**가 인용문으로 실린다(실측). 숫자 덩어리가 많은 조각은 문장이 아니다."""
    if len(s) < 24:
        return False
    return len(_DIGITS.findall(s)) <= 4


def demand_quotes(text, limit=3):
    """II절 본문에서 수요 낱말이 나온 문장을 뽑는다 → {키: {n, quotes[]}}.

    `&nbsp;` 같은 엔티티를 먼저 풀어 둔다 — 화면에 `&amp;nbsp;` 로 두 번 이스케이프돼 나온다."""
    flat = re.sub(r"<[^>]+>", " ", text or "")
    flat = html.unescape(flat).replace(" ", " ")
    flat = re.sub(r"\s+", " ", flat)
    sents = re.split(r"(?<=[.。])\s+|(?<=니다)\s+|(?<=됩니다)\s+|·{2,}", flat)
    out = {}
    for key, pat in DEMAND_WORDS:
        n = len(pat.findall(flat))
        if not n:
            continue
        qs = []
        for s in sents:
            s = s.strip()
            if not pat.search(s):
                continue
            if len(s) > 240:
                m = pat.search(s)
                s = s[max(0, m.start() - 100):m.start() + 140].strip()
            if not _readable(s) or s in qs:
                continue
            qs.append(s)
            if len(qs) >= limit:
                break
        out[key] = {"n": n, "quotes": qs}
    return out


# ── 수집 ───────────────────────────────────────────────────

_PARENT = re.compile(r"지배회사|당사\s*및\s*그\s*종속회사|및\s*그\s*종속회사")


def _grand_row(orows):
    """원문이 스스로 밝힌 **총계 행**. 없으면 None.

    소계와 총계가 섞여 온다(일진전기: 품목별 `계` 3벌 + `합 계|계` 1벌). 라벨이 **전부**
    합계인 행을 총계로 보고, 그런 행이 여럿이면 잔고가 가장 큰 것을 쓴다 — `합 계|국내`처럼
    총계 이름 밑에 갈래가 또 있는 표에서 첫 행을 집으면 절반만 실린다(실측)."""
    grand = [r for r in orows if r.get("grand") and r.get("closing") is not None]
    if grand:
        return max(grand, key=lambda r: r["closing"])
    return None


def _orders_total(o):
    g = _grand_row(o["rows"])
    if g is not None:
        return g["closing"]
    vals = [r["closing"] for r in o["rows"] if not r["total"] and r.get("closing") is not None]
    return sum(vals) if vals else 0


def _pick_orders(orders, name=""):
    """여러 수주표 중 **회사 본체**의 표를 고른다.

    엘에스일렉트릭 II-4 에는 수주표가 여러 장 온다 — `[LS ELECTRIC]`(7조),
    `[LS메탈]`(666억, 단위 `톤, 억원`), `[LS이모빌리티솔루션]` …
    잔고가 가장 큰 표를 고르되, ① 단위를 읽은 금액표를 ② 대괄호 라벨이 **회사 이름과 겹치는**
    표를 먼저 본다. 나머지는 버리지 않고 orders_all 에 남아 화면에서 갈라 보인다."""
    if not orders:
        return None
    key_name = _clean(name).replace("주식회사", "").replace("(주)", "")

    def key(o):
        money = bool(o.get("unit_seen")) and not o.get("qty_only")
        ent = _clean(o.get("entity") or "")
        same = 1 if (ent and key_name and (ent in key_name or key_name in ent
                                           or ent.replace(" ", "").lower()
                                           in key_name.replace(" ", "").lower())) else 0
        mark = 1 if _PARENT.search(o.get("lead") or "") else 0
        return (money, same, mark, o["shape"] != "balance", _orders_total(o), len(o["rows"]))
    best = dict(max(orders, key=key))
    best["picked_of"] = len(orders)
    return best


def _keep(t):
    """캐시에 남길 표인지 — 수주·매출·매출처 표만(정기보고서 전체를 담으면 캐시가 터진다)."""
    blob = " ".join(t["cols"]) + " " + (t.get("lead") or "")[-200:]
    return bool(re.search(r"수주|매출|거래처|매출처|고객|납기|잔고|잔액|지역", blob))


def collect_one(rec, quarter, force=False, log=sys.stderr, with_text=True):
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
    group_hint = re.sub(r"\s*(주식회사|\(주\)|홀딩스|그룹)\s*", "", rec.get("name", ""))[:4]
    # 수주표로 읽힌 표는 매출표 후보에서 뺀다 — 수주표의 품목 행이 매출실적으로 다시 읽히면
    # 연매출이 오염된다.
    parsed = [(t, parse_orders_table(t)) for t in tables]
    orders = [o for _, o in parsed if o]
    rest = [t for t, o in parsed if not o]
    revenue = [x for x in (parse_revenue_table(t) for t in rest) if x]
    segsales = [x for x in (parse_segment_sales(t) for t in rest) if x]
    regions = [x for x in (parse_region_table(t) for t in rest) if x]
    customers = [x for x in (parse_customers(t, group_hint) for t in tables) if x]
    out["orders"] = _pick_orders(orders, rec.get("name", ""))
    out["orders_all"] = orders or []
    seg_rev = [r for r in revenue if r["basis"] == "segment"]
    out["revenue"] = max(seg_rev or revenue, key=lambda r: len(r["rows"])) if revenue else None
    out["revenue_all"] = revenue or []
    out["segment_sales"] = max(segsales, key=lambda r: len(r["rows"])) if segsales else None
    out["segment_sales_all"] = segsales or []
    out["regions"] = max(regions, key=lambda r: len(r["rows"])) if regions else None
    # 매출처는 **한 장만 고르지 않는다** — 엘에스일렉트릭은 종속회사별로 12벌이고,
    # 본체 표만 남기면 북미 고객(LS ELECTRIC America)이 통째로 사라진다.
    out["customers_all"] = customers or []
    out["customers"] = (max(customers, key=lambda c: len(c["rows"])) if customers else None)
    out["raw_tables"] = [{"cols": t["cols"], "rows": t["rows"], "lead": (t.get("lead") or "")[-240:]}
                         for t in tables if _keep(t)]
    # 수요 낱말은 **최신 분기에서만** 읽는다. 시장 서술은 분기마다 거의 같은데 절을 3장 더
    # 받으면 요청이 두 배가 된다(DART는 IP 하나로 게이트가 걸려 벽시계 시간이 그대로 늘어난다).
    txt = html
    if with_text:
        for key in ("products", "overview", "etc"):
            if key in found:
                try:
                    txt += fetch_section(found[key])
                except Exception:
                    pass
    out["demand"] = demand_quotes(txt)
    out["demand_scope"] = "II절 전체" if with_text else "II-4 수주·매출 절만"
    out["ok"] = bool(out["orders"] or out["revenue"] or out["segment_sales"])
    if not out["ok"]:
        out["note"] = "수주·매출표 인식 실패 — 머리행 %s" % [t["cols"] for t in tables][:3]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write(path, json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    log.write("%s %s %s %s %s\n" % (st, quarter, "ok" if out["ok"] else "FAIL",
                                    (out["orders"] or {}).get("shape", "-"),
                                    (out["orders"] or {}).get("cur", "-")))
    log.flush()
    return out


def quarters(latest, n=6):
    y, q = int(latest[:4]), int(latest[-1])
    out = []
    for _ in range(n):
        out.append("%dQ%d" % (y, q))
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return list(reversed(out))


def collect(rows, qs, force=False):
    last = qs[-1] if qs else None
    for rec in rows:
        for q in qs:
            try:
                collect_one(rec, q, force, with_text=(q == last))
            except Exception as e:
                sys.stderr.write("[warn] %s %s %s\n" % (rec["stock"], q, e))


# ── 빌드 ───────────────────────────────────────────────────

def _sum_rows(rows, field, kinds=None):
    vals = [r[field] for r in rows
            if not r["total"] and r.get(field) is not None
            and (kinds is None or r.get("kind") in kinds)]
    return sum(vals) if vals else None


def _sum_rows_rev(rrows, kind):
    vals = [(r["vals"] or [None])[0] for r in rrows
            if r["kind"] == kind and not is_total(r["seg"])]
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


_FY_COL = re.compile(r"20\d\d년|제\d+기")
# 수량 열도 1년 열처럼 `제40기 수량` 으로 온다 — 여기서 막지 않으면 매출 대신 대수를 쓴다.
_PART_YEAR = re.compile(r"반기|분기|누적|개월|기중|비중|비율|수량|증감")


def _is_fy(col):
    """'제18기'·'2025년'은 1년 열, '제19기 반기'·'제10기 2분기(누적)'는 아니다."""
    c = _clean(col)
    return bool(_FY_COL.search(c)) and not _PART_YEAR.search(c)


def _norm_co(s):
    return re.sub(r"[\s().,·\-—'\"]|주식회사|\(주\)|CO|LTD|INC|CORP|유한공사", "",
                  (s or ""), flags=re.I).lower()


def _related_names(d, own_name):
    """이 보고서가 **스스로 밝힌** 종속회사 이름들. 관계회사 판정의 근거다.

    '엘에스일렉트릭' 과 'LS ELECTRIC AMERICA INC.' 는 글자가 하나도 겹치지 않아 이름만으로는
    못 잇는다. 그런데 같은 보고서의 수주표 라벨(`[LS ELECTRIC Vietnam]`)·매출실적 구분 열
    (`LS ELECTRICAmerica`)에 종속회사가 **다 적혀 있다** — 그것을 근거로 쓴다(추정 금지).
    최대 매출처가 자기 자회사인 회사가 실제로 있어(엘에스일렉트릭 전력-인프라 41.7%)
    '최대 외부고객'과 갈라 두지 않으면 화면이 거짓말을 한다."""
    names = {_norm_co(own_name)}
    for o in (d.get("orders_all") or []):
        if o.get("entity"):
            names.add(_norm_co(o["entity"]))
    for key in ("revenue_all", "segment_sales_all"):
        for t in (d.get(key) or []):
            if t.get("entity"):
                names.add(_norm_co(t["entity"]))
            for r in t.get("rows") or []:
                seg = _norm_co(r.get("seg"))
                if len(seg) >= 3 and not re.search(r"^(합계|소계|계|기타|제품|상품|용역)$", seg):
                    names.add(seg)
    return {n for n in names if len(n) >= 3}


def _is_related(name, rels):
    n = _norm_co(name)
    if len(n) < 3:
        return False
    return any(n.startswith(r) or r.startswith(n) for r in rels)


def _entity_subset(tbl, entity):
    """매출 표에서 **그 종속회사 행만** 남긴 복제본. 못 맞추면 None.

    `[LS ELECTRIC]`(수주표 라벨) ↔ `LSELECTRIC`(매출실적 구분 열)처럼 공백·대소문자만 다르다.
    느슨하게 맞추되 접두 일치까지만 본다 — `LS ELECTRIC` 이 `LS ELECTRIC America` 를
    끌어오면 해외법인 매출이 본체에 얹힌다."""
    if not tbl or not entity:
        return None
    key = re.sub(r"[\s()（）주식회사]", "", entity).lower()
    if not key:
        return None
    rows = []
    for r in tbl.get("rows") or []:
        seg = re.sub(r"[\s()（）주식회사]", "", r.get("seg") or "").lower()
        if seg and seg == key:
            rows.append(r)
    if not rows:
        return None
    d = dict(tbl)
    d["rows"] = rows
    return d


def _fy_from(tbl, kind_field=None):
    """매출 표에서 **온전한 1년** 열을 찾아 총매출을 만든다 → (값, 열 이름, 통화).

    커버리지(잔고 ÷ 연매출, 년)의 분모다. 반기 누계를 두 배로 늘리면 추정이 되므로
    공시에 실제로 적힌 직전 사업연도 열을 쓴다. 열과 값의 개수가 어긋나면 만들지 않는다.
    전체 합계 행과 부문 합계 행이 **둘 다** 오면 전체 합계만 쓴다(다 더하면 두 배가 된다)."""
    if not tbl:
        return None, None, None
    cols = tbl.get("period_cols") or []
    rows = [r for r in (tbl.get("rows") or []) if len(r.get("vals") or []) == len(cols)]
    if not rows:
        return None, None, None
    for i, c in enumerate(cols):
        if not _is_fy(c):
            continue
        if kind_field:          # 내수/수출 표 — 부문 '계' 행 > 전체 합계 > 낱 행
            grand = [r for r in rows if r["kind"] == "합계" and is_total(r["seg"])]
            per_seg = [r for r in rows if r["kind"] == "합계" and not is_total(r["seg"])]
            base = [r for r in rows if r["kind"] in ("내수", "수출") and not is_total(r["seg"])]
            groups = (grand, per_seg, base)
        else:
            grand = [r for r in rows if is_total(r["seg"])]
            sub = [r for r in rows if r.get("total") and not is_total(r["seg"])]
            base = [r for r in rows if not r.get("total")]
            groups = (grand, sub, base)
        for use in groups:
            vals = [r["vals"][i] for r in use if r["vals"][i] is not None]
            if vals:
                return sum(vals), cols[i], tbl.get("cur")
    return None, None, None


def build(rows, qs):
    """캐시 → reports.json. 회사 × 분기의 수주잔고·해외비중·커버리지·매출처·수요 낱말."""
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
            grand = _grand_row(orows)
            base = [r for r in orows if not r["total"]]
            # 단위를 못 읽었거나 금액이 아닌 단위(톤)면 **금액으로 싣지 않는다**(fail-closed).
            money = bool(o.get("unit_seen")) and not o.get("qty_only")
            backlog = ((grand["closing"] if grand is not None else _sum_rows(orows, "closing"))
                       if money else None)
            # 낱 행 합과 원문 총계가 어긋나면 조용히 넘기지 않고 표시한다(COMMON §2).
            base_sum = _sum_rows(orows, "closing")
            mismatch = (grand is not None and base_sum is not None and grand["closing"]
                        and abs(base_sum - grand["closing"]) > max(1.0, grand["closing"] * 0.01))
            rv = d.get("revenue") or {}
            rrows = rv.get("rows") or []
            ss = d.get("segment_sales") or {}
            srows = ss.get("rows") or []
            # 연매출은 **수주표와 같은 주체**의 것이어야 한다. 엘에스일렉트릭 매출실적 표는
            # 종속회사별 행(LSELECTRIC·LS메탈·LS이모빌리티…)인데 수주표는 `[LS ELECTRIC]`
            # 한 회사 것이다. 다 더한 매출(4.97조)로 나누면 배수가 1.4년, 같은 주체끼리 나누면
            # 2.0년이다 — 뒤가 맞다. 주체를 맞출 수 없으면 전체를 쓰고 그 사실을 남긴다.
            ent = o.get("entity") or ""
            fy = fy_col = fy_cur = None
            fy_basis = "all"
            if ent:
                sub = _entity_subset(rv, ent)
                if sub:
                    fy, fy_col, fy_cur = _fy_from(sub, kind_field=True)
                    if fy is not None:
                        fy_basis = "entity"
            if fy is None:
                fy, fy_col, fy_cur = _fy_from(rv, kind_field=True)
            if fy is None:
                fy, fy_col, fy_cur = _fy_from(ss)
            bal_cur = o.get("cur") or "KRW"
            cov = coverage(backlog, fy, bal_cur, fy_cur or "KRW")
            dom = _sum_rows_rev(rrows, "내수")
            exp = _sum_rows_rev(rrows, "수출")
            rg = d.get("regions") or {}
            region_rows = [r for r in (rg.get("rows") or []) if not r["total"]]
            # 매출처 — 여러 표를 합치고 근거 등급별로 갈라 둔다. '최대 외부고객'은 실명만 센다.
            rels = _related_names(d, rec.get("name", ""))
            cust = []
            for i, c in enumerate(d.get("customers_all") or []):
                for r in c["rows"]:
                    ev = r["evidence"]
                    if ev == "named" and _is_related(r["name"], rels):
                        ev = "rel"      # 자기 종속회사 — 연결 매출과 겹친다
                    cust.append(dict(r, evidence=ev, entity=c.get("entity", ""),
                                     cur=c.get("cur"), tbl=i))
            # **첫 표가 본체 표**다(문서 순서 — 종속회사 표는 뒤에 붙는다). 전체에서 최대 비중을
            # 고르면 베트남 자회사 고객(Thai Son Nam 60.9%)이 회사 대표값이 되어 버린다(실측).
            named = [c for c in cust
                     if c["evidence"] == "named" and c.get("share_pct") and c["tbl"] == 0]
            per_q[q] = {
                "ok": True, "rcp": d.get("rcp"), "shape": o.get("shape"),
                "cur": bal_cur, "unit_seen": o.get("unit_seen"),
                "entity": o.get("entity", ""), "orders_tables": o.get("picked_of", 0),
                # 입도 — 한 행이 계약인지 **사업부문 합계**인지. 행 수가 아니라 **서로 다른
                # 부문 이름의 수**로 센다. 일진전기는 부문 2개가 국내/해외로 갈려 4행이지만
                # 계약 단위가 아니다(스펙 §4: 열 모양은 계약 단위인데 내용은 부문 합계다).
                "grain": ("segment" if len({r["seg"] for r in base}) <= 3 else "project"),
                "top_share": (max((r["closing"] for r in base if r.get("closing") is not None),
                                  default=None) / backlog * 100.0
                              if backlog and base else None),
                "total_mismatch": bool(mismatch),
                "backlog": backlog,
                "backlog_grid": _sum_rows(orows, "closing", kinds=("grid",)) if money else None,
                # 국내/해외는 **낱 행에서만** 더한다. 일진전기 수주표에는 `합 계|국내` 라는
                # 총계 행이 또 있어 소계와 함께 더하면 국내 잔고가 두 배가 된다(실측).
                "backlog_dom": (sum(r["closing"] for r in base
                                    if r.get("area") == "dom" and r.get("closing") is not None)
                                or None) if money else None,
                "backlog_ovs": (sum(r["closing"] for r in base
                                    if r.get("area") == "ovs" and r.get("closing") is not None)
                                or None) if money else None,
                "opening": ((grand["opening"] if grand is not None
                             and grand.get("opening") is not None
                             else _sum_rows(orows, "opening")) if money else None),
                "new": _sum_rows(orows, "new") if money else None,
                "delivered": _sum_rows(orows, "delivered") if money else None,
                "gross": _sum_rows(orows, "gross") if money else None,
                "unit_note": ("" if money else
                              ("수주표 단위가 금액이 아님 — 금액으로 싣지 않음" if o.get("qty_only")
                               else "수주표 단위 캡션을 못 읽음 — 금액으로 싣지 않음") if o else ""),
                "unit_from_prev": bool(o.get("unit_from_prev")),
                "segments": [{"label": r["label"], "seg": r["seg"], "item": r["item"],
                              "kind": r.get("kind"), "area": r.get("area"),
                              "closing": r["closing"], "opening": r.get("opening"),
                              "new": r.get("new"), "gross": r.get("gross"),
                              "delivered": r.get("delivered"),
                              "due": r.get("due"), "order_date": r.get("order_date")}
                             for r in orows if not r["total"]],
                "orders_other": [{"entity": x.get("entity", ""), "cur": x.get("cur"),
                                  "unit_seen": x.get("unit_seen"), "shape": x.get("shape"),
                                  "closing": _orders_total(x), "n_rows": len(x["rows"])}
                                 for x in (d.get("orders_all") or [])
                                 if x is not o and x.get("entity") != o.get("entity")],
                "revenue_fy": fy, "revenue_fy_col": fy_col, "revenue_cur": fy_cur or "KRW",
                "revenue_basis": fy_basis,
                "revenue_domestic": dom, "revenue_export": exp,
                "coverage_years": cov,
                "coverage_note": ("" if cov is not None else
                                  ("잔고 통화(%s)와 매출 통화(%s)가 달라 배수를 만들지 않음"
                                   % (bal_cur, fy_cur or "KRW")) if backlog is not None and fy
                                  else ""),
                "revenue_segments": [{"seg": r["seg"], "item": r["item"], "kind": r["kind"],
                                      "segkind": r["segkind"], "val": r["val"]}
                                     for r in rrows],
                "sales_segments": [{"seg": r["seg"], "item": r["item"], "segkind": r["segkind"],
                                    "val": r["val"], "pct": r.get("pct"), "total": r["total"]}
                                   for r in srows],
                "regions": [{"name": r["name"], "region": r["region"], "val": r["val"]}
                            for r in region_rows],
                "region_cur": rg.get("cur"),
                "customers": cust,
                "top_customer": (max(named, key=lambda c: c["share_pct"]) if named else None),
                "customer_tables": len(d.get("customers_all") or []),
                "demand": d.get("demand") or {},
            }
        if per_q:
            out[st] = {"stock": st, "name": rec.get("name", ""), "role": rec.get("role"),
                       "market": rec.get("market", ""), "quarters": per_q}
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
    ap.add_argument("--n", type=int, default=6)
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
        ok = sum(1 for c in res.values() for v in c["quarters"].values() if v.get("ok"))
        print("회사 %d · 분기레코드 %d" % (len(res), ok))
        for st, c in res.items():
            last = [q for q in qs if q in c["quarters"] and c["quarters"][q].get("ok")]
            if not last:
                continue
            v = c["quarters"][last[-1]]
            print("  %s %-14s %s %-9s %-3s 잔고 %-12s 연매출 %-11s 배수 %s"
                  % (st, c["name"][:14], last[-1], v["shape"] or "-", v["cur"],
                     v["backlog"], v["revenue_fy"],
                     ("%.2f" % v["coverage_years"]) if v["coverage_years"] else "—"))


if __name__ == "__main__":
    sys.exit(main())
