#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kdef_reports — 정기보고서 「II. 사업의 내용」에서 방산 회사의 분기 지표를 읽는다.

방산은 **보안 때문에 수주표가 조선보다 빈약하다**(FINDINGS §5 — 이 탭의 가장 큰 제약).
실측한 표 모양이 세 갈래여서 하나의 파서로는 안 된다:

  (A) `gross`   총액−기납품=잔고 — 한화에어로(요약)·한화시스템·현대로템
                `수주총액 금액 | 기납품액 금액 | 수주잔고 금액`. **기초·신규 열이 없다** —
                조선의 롤포워드 파서(kship_yards.parse_orders_table)를 그대로 쓰면 실패한다.
  (B) `item`    품목별 개별 사업 — 현대로템 `나. 진행률적용 수주 상황`
                `품목 | 수주일자 | 납기 | 수주총액 | 기납품액 | 수주잔고`. 품목명은 `철도A`처럼
                익명화돼 있다(방산은 더 심하다).
  (C) `balance` 잔액 한 줄 — LIG "보안관계상 상세히 기재하지 아니하고 기말잔액을 표시"
  (D) `roll`    기초+신규−기납품=기말(조선형). 방산에서는 아직 못 봤지만 대비해 둔다.

그래서 이 탭의 1차 축은 **잔고 커버리지(수주잔고 ÷ 연매출, 년)** 다 — (C)형에서도 계산된다.
'몇 년치 일감'은 다년도 계약 산업의 선표 대용이며, 인도 스케줄은 계약 공시로만 만든다.

같이 읽는 것:
  · **부문 매출** — 방산/민수, 내수/수출. 부문 이름은 회사마다 다르다(FINDINGS §6).
    정규화(def/civil/mixed)하되 **원문 이름을 반드시 함께** 남긴다.
  · **주요 거래처** — 부품사→체계업체 연결의 최상급 근거(FINDINGS §7). LIG·KAI는 비중 %까지 적는다.
    한화에어로 `판매경로` 표의 매출처 열은 rowspan 복제로 오염돼 있어 **쓰지 않는다**.

원문 표(cols·rows·lead)를 캐시에 그대로 남긴다 — 파서가 자라면 재수집 없이 다시 뽑는다(COMMON §0-4).

머리행 지도(2026-10-12, 공용 엔진 argus/kce/tools/hdrmap.py): 수집·재파싱마다 표 역할 4개
(orders·revenue·segsales·customers)를 채택/비채택/미지로 기록하고, 못 읽은 수주형 표는 캐시의
`unknown_headers` 와 큐(assets/hdr_queue.json)에 남는다. 이 탭에서 지도는 **advisory** 다 —
엔진이 실패해도 수집은 멈추지 않는다(kce 정밀만 fail-closed). 지도·페이지는 kdef_headers.py.

    python3 kdef_reports.py --collect [--quarter 2026Q2] [--only 079550]
    python3 kdef_reports.py --reparse [--n 19]   # 파서를 고친 뒤 — DART 를 다시 긁지 않는다
    python3 kdef_reports.py --build
"""
import argparse
import json
import os
import re
import sys

from kdef_lib import (ASSETS, atomic_write, fetch_section, find_sections, is_total,
                      latest_quarter, load_asset, norm_col, num_of, parse_tables, pick_report,
                      q_of, report_kind, report_window, search_reports, toc, unit_of,
                      write_asset)
from kdef_universe import load as load_universe
import hdrmap                                   # kdef_lib 가 argus/kce/tools 를 sys.path 에 넣는다

CACHE = os.path.join(ASSETS, "reports_cache")
HDR_TAB = "kdef"
HDR_ROOT = None          # 엔진 root(기본 argus/) — 테스트가 임시 디렉터리로 바꾼다

SECTIONS = [
    ("sales", ["매출 및 수주상황", "수주상황", "매출실적"]),
    ("products", ["주요 제품 및 서비스", "주요 제품", "주요제품"]),
    ("overview", ["사업의 개요"]),
]

# 보안 때문에 상세를 생략한다는 원문 문구 — 화면에 그대로 인용한다(추정이 아니라 공시다).
_SECURITY = re.compile(r"보안\s*관계상|보안상|군사기밀|보안\s*유지")


def _clean(s):
    return re.sub(r"[\s　]+", "", s or "")


def _headered(tables, dropped=None):
    """머리행을 못 잡은 표를 살린다.

    한화시스템 `가. 사업부문별 매출` 표는 kce_parse 가 머리행을 인식하지 못해 `cols=[]` 로
    온다(첫 행이 `사업부문|매출유형|제27기 2분기|…`). 그대로 버리면 방산비중이 통째로
    사라진다 — 첫 행의 셀이 모두 비숫자면 그것을 머리행으로 쓴다(fail-closed: 아니면 버린다).

    머리행을 잡았어도 **부머리행이 본문 첫 줄로 떨어진** 표(`수주총액|수주총액` 아래 `수량|금액`)는
    _merge_subrow 가 두 줄을 잇는다. dropped(목록)를 주면 살리지 못하고 버린 표를 거기에 담는다
    — 캐시의 `머리행 []` 실패 33건은 이 버려진 표가 어디에도 안 남아 사유를 알 수 없었다."""
    out = []

    def drop(t):
        if dropped is not None:
            dropped.append(t)

    for t in tables:
        if t["cols"]:
            out.append(_merge_subrow(t) or t)
            continue
        rows = t["rows"]
        if len(rows) < 2 or len(rows[0]) < 2:
            drop(t)
            continue
        if any(num_of(c) is not None for c in rows[0]):
            drop(t)
            continue
        if len({_clean(c) for c in rows[0]}) != len(rows[0]):
            d = _two_row_header(t)      # `기 초 | 기 초`(수량·금액) — 부머리행이 따로 있다
            if d:
                out.append(d)
            else:
                drop(t)
            continue
        if not any(num_of(c) is not None for r in rows[1:] for c in r):
            drop(t)
            continue
        d = dict(t)
        d["cols"], d["rows"] = list(rows[0]), rows[1:]
        d["header_synth"] = True
        d["cols_raw"] = []              # 원문에는 머리행이 없었다(지도에 cols_raw·cols 를 병기한다)
        out.append(d)
    return out


# 부머리행 어휘 — 두 줄 머리행의 아랫줄에 오는 낱말. 금액이 아닌 것(수량·중량·판매량)이 섞여 있어
# 병합하지 않으면 parse_orders_table 이 같은 이름의 **첫 열(수량)** 을 금액으로 읽는다.
_SUBROW = re.compile(r"^(수량|금액|중량|판매량|단가|대수|척수|건수|외화|원화)$")


def _merge_subrow(t):
    """머리행 아래 **부머리행이 본문 첫 줄로 떨어진** 표의 두 줄을 잇는다. 아니면 None.

    한화(000880) 13분기·SK오션플랜트·센서뷰·에스비비테크·풍산 종속회사 표가 이 모양이다(캐시 실측):
        부문 | 사업 | 품목 | 수주일자 | 납기 | 수주총액 | 수주총액 | 기납품액 | 기납품액 | 수주잔고 | 수주잔고
        부문 | 사업 | 품목 | 수주일자 | 납기 |   수량   |   금액   |   수량   |   금액   |   수량   |   금액     ← rows[0]
    parse_tables 는 첫 줄만 머리행으로 잡는다. 그대로 두면 `수주총액` 두 열 중 앞(수량, '-')을 읽어
    행이 전부 빠지거나(한화 — 표 통째 누락), 수량이 금액 자리에 들어간다(풍산 종속 — `판매량` 열).
    fail-closed — 같은 이름이 **이웃해** 겹치는 열이 있고, rows[0] 이 전부 비숫자이며, 겹친 자리의
    rows[0] 이 부머리행 어휘이고 서로 다르며, 이어 붙인 이름이 모두 갈라지고, 본문에 숫자가 있어야 한다."""
    cols, rows = t["cols"], t["rows"]
    if len(rows) < 2 or len(rows[0]) != len(cols):
        return None
    cc = [_clean(c) for c in cols]
    dup = [i for i in range(1, len(cc)) if cc[i] and cc[i] == cc[i - 1]]
    if not dup:
        return None
    sub = [_clean(c) for c in rows[0]]
    if any(num_of(c) is not None for c in rows[0] if (c or "").strip()):
        return None
    for i in dup:
        if sub[i] == sub[i - 1] or not _SUBROW.match(sub[i]) or not _SUBROW.match(sub[i - 1]):
            return None
    if not any(num_of(c) is not None for r in rows[1:] for c in r):
        return None
    merged = []
    for a, b in zip(cols, rows[0]):
        a, b = (a or "").strip(), (b or "").strip()
        merged.append(a if _clean(a) == _clean(b) or not b else (a + " " + b).strip())
    if len({_clean(c) for c in merged}) != len(merged):
        return None
    d = dict(t)
    d["cols"], d["rows"] = merged, rows[1:]
    d["header_synth"] = "2row"
    d["cols_raw"] = list(cols)
    return d


_UNIT_CAP = re.compile(r"단위\s*:?\s*[^)\]]{1,24}")
# 금액이 아닌 단위 — 풍산 「수주상황」은 **M/T(톤)** 이다. 돈으로 실으면 600억짜리 회사가 된다.
_UNIT_QTY = re.compile(r"M\s*/\s*T|톤|kg|개|대\b|척|セット|set", re.I)


def _carry_units(tables):
    """표마다 단위 캡션을 읽되, 자기 lead 에 없으면 **직전에 본 캡션**을 물려준다.

    한화에어로 「다. 수주상황(요약)」은 단위가 바로 앞 한 줄짜리 표 안에 들어 있고
    (`(기준일 : … ) (단위 : 백만원)`) 정작 수주표의 lead 는 비어 있다 — 그대로 두면
    unit_seen=False 로 114조가 '단위 미확인'이 된다(실측). 물려준 단위는 표시를 남긴다."""
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
    """머리행이 **두 줄**인 표(rowspan/colspan 평탄화 결과)를 살린다.

    KAI 2026 반기 「나. 수주상황」이 이 모양이다(원문 실측):
        구 분 | 기 초(2026.01.01) | 기 초(2026.01.01) | 기 말(2026.06.30) | 기 말(2026.06.30) | 비 고
        구 분 |       수량        |       금액        |       수량        |       금액        | 비 고
        국내방산 | - | 109,868 | - | 102,355 | -
    첫 줄만 머리행으로 쓰면 `기초 금액`과 `기초 수량`을 못 가른다(잔고가 통째로 빠진다).
    두 줄을 이어 붙여 `기 초(2026.01.01) 금액` 으로 만든다. fail-closed —
    두 줄 다 비숫자이고, 둘째 줄이 첫 줄과 다르며, 셋째 행부터 숫자가 있어야 한다."""
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
        return None                     # 이어 붙여도 안 갈라지면 손대지 않는다
    d = dict(t)
    d["cols"], d["rows"] = cols, rows[2:]
    d["header_synth"] = "2row"
    d["cols_raw"] = list(t["cols"])     # 원문 머리행([] — parse_tables 가 못 잡았다)
    return d


def _scaled(v, mul):
    x = num_of(v)
    if x is None:
        return None
    x = x * mul
    return int(x) if float(x).is_integer() else round(x, 3)


# ── 부문 이름 정규화 ────────────────────────────────────────
# 원문 이름은 회사마다 다르다(FINDINGS §6). 판정은 def/civil/mixed 셋이고, 원문 이름은
# 언제나 함께 남긴다 — 정규화가 틀려도 원문으로 되짚을 수 있어야 한다.
_SEG_DEF = re.compile(r"방산|방위|디펜스|Defen[cs]e|군수|무기|특수선|완제기|AD&RH|지상|유도|"
                      r"PGM|ISR|AEW|C4I|감시정찰|전술|항공우주|우주", re.I)
_SEG_CIVIL = re.compile(r"철도|전동차|RS부문|EP부문|에코플랜트|플랜트|ICT|IT서비스|신동|민수|"
                        r"상용차|승용|건설|화학|소재사업|레저|반도체|디스플레이", re.I)
# 한쪽으로 못 가르는 이름 — 한화에어로 `항공`(군수엔진+민항엔진 RSP), KAI `기체부품 및 민수, 수출 기타`
_SEG_MIXED = re.compile(r"^항공$|항공엔진|기체부품|엔진사업|기타$|기타등$|합계", re.I)


def seg_kind(name):
    """부문 원문 이름 → 'def'|'civil'|'mixed'|None. 판정과 원문 이름을 **둘 다** 싣는다."""
    n = _clean(name)
    if not n:
        return None
    if _SEG_MIXED.search(n) and not _SEG_DEF.search(n):
        return "mixed"
    d, c = bool(_SEG_DEF.search(n)), bool(_SEG_CIVIL.search(n))
    if d and not c:
        return "def"
    if c and not d:
        return "civil"
    if d and c:
        return "mixed"
    return None


# ── 수주표 ─────────────────────────────────────────────────

# 금액이 아닌 열 — 두 줄 머리행을 이은 `수주총액 수량`·`수주총액 중량`(풍산)·`수주총액 판매량`(풍산 종속).
# 금액 열이 따로 없는데 이런 열만 있으면 **그 역할을 비운다**(수량이 백만원으로 집계되면 안 된다).
_QTY_COL = re.compile(r"수량|중량|판매량")
# 판별 결과의 열 역할(parse_orders_table 반환 matched 의 키 — 앞 7개가 값 열, 뒤 3개는 award 모양 식별용)
MATCH_KEYS = ("open", "new", "done", "gross", "close", "date", "due")
_AWARD_KEYS = ("client", "name", "period")


def _match_cols(cols):
    """머리행 → 역할별 열 번호(없으면 None) + qty_only(금액 열 없이 수량 열만 있던 역할).

    parse_orders_table 과 미지 표 진단(orders_unknown)이 **같은 판정**을 쓴다 — 두 벌이면 '왜 못 읽었나'의
    설명이 실제 판정과 갈라진다. 어휘(2026-10-12 보강, 캐시 실측):
      · 잔고 단독 — 대한항공 종속 한진정보통신 `사업명|사업기간|수주금액|매출금액|잔고` 18분기
      · 수주잔량 — 에스비비테크 `수주 잔량 수량|금액` 4분기
      · 납품금액·매출금액(기납품 동의어) — 대한항공 `수주금액|납품금액`, 한진정보통신 `매출금액`
        (수주금액 42 − 매출금액 41 = 잔고 1 — 누계 기납품이다)
      · 수주년 — 파이버프로 `수주년|납기년`(납기년은 `납기` 가 이미 잡는다)
      · 중량·판매량 — 수량 동의어(_QTY_COL)
    새 어휘는 같은 역할의 **기존 어휘 뒤**에 둔다 — 지금 읽히는 표의 열 선택이 바뀌지 않게."""
    cols = [_clean(c) for c in cols]
    qty_hit = set()

    def col(*keys):
        """keys 를 모두 품은 열. 금액 열을 먼저, 그다음 수량이 아닌 열. 수량 열뿐이면 None."""
        cand = [i for i, c in enumerate(cols) if all(k in c for k in keys)]
        if not cand:
            return None
        amt = [i for i in cand if "금액" in cols[i]]
        money = [i for i in cand if not _QTY_COL.search(cols[i])]
        if amt or money:
            return (amt or money)[0]
        qty_hit.add(keys[0])
        return None

    def first(*cands):
        """열 번호 0 이 거짓으로 읽히면 첫 열이 통째로 사라진다 — `or` 대신 None 검사."""
        for c in cands:
            if c is not None:
                return c
        return None

    m = {
        "open": first(col("기초", "금액"), col("기초")),
        "new": first(col("신규", "금액"), col("신규")),
        "done": first(col("기납품", "금액"), col("기납품"), col("납품금액"), col("매출금액")),
        "gross": first(col("수주총액", "금액"), col("수주총액"), col("계약금액"), col("수주금액")),
        "close": first(col("수주잔고", "금액"), col("수주잔고"), col("수주잔액"),
                       col("수주잔량", "금액"), col("수주잔량"),
                       col("기말", "금액"), col("기말"), col("잔액"), col("잔고")),
        "date": first(col("수주일자"), col("계약일자"), col("수주일"), col("수주년")),
        "due": first(col("납기"), col("인도예정"), col("완공예정")),
        # award 모양(knuke `발주처|사업명|계약기간|계약금액`) — 값에는 안 쓰고 지도·진단에서 식별만 한다
        "client": first(col("발주처"), col("발주자"), col("계약상대"), col("수요처"), col("고객"), col("거래처")),
        "name": first(col("사업명"), col("공사명"), col("계약명"), col("프로젝트")),
        "period": first(col("계약기간"), col("사업기간"), col("계약일"), col("착수일"), col("종료일")),
    }
    qty_only = []
    for k, words in (("gross", ("수주총액",)), ("close", ("수주잔고", "수주잔량", "기말"))):
        if m[k] is None and any(w in qty_hit for w in words):
            qty_only.append(k)
    m["qty_only"] = qty_only
    return m


def parse_orders_table(t):
    """수주표 한 장 → {shape, cur, unit_seen, rows, matched, header_synth}. 네 모양을 한 함수로 가른다.

    matched = 판별에 쓴 열 번호 {open,new,done,gross,close,date,due}(없으면 None) — 머리행 지도의 fields 와
    '어느 열을 무엇으로 읽었나'의 근거. header_synth = None|True(첫 행 승격)|'2row'(두 줄 병합)."""
    cols = [_clean(c) for c in t["cols"]]
    cur, mul, seen = unit_of(t.get("lead"), t.get("cols"))
    caps = _UNIT_CAP.findall(" ".join([t.get("lead") or ""] + list(t["cols"])))
    qty_unit = bool(caps and _UNIT_QTY.search(caps[-1]) and not seen)

    m = _match_cols(t["cols"])
    i_open, i_new, i_done, i_gross, i_close, i_date, i_due = (m[k] for k in MATCH_KEYS)
    if i_close is None and i_gross is None:
        return None
    if i_open is not None and i_close is not None:
        # 기초·기말만 있고 신규·기납품이 없는 표(KAI — 보안관계상 순증감만 적는다)는
        # 롤포워드가 아니다. 화면에서 '신규 −' 로 비워야 하므로 모양을 따로 부른다.
        shape = "roll" if (i_new is not None or i_done is not None) else "openclose"
    elif i_gross is not None and i_close is not None:
        shape = "item" if i_date is not None or i_due is not None else "gross"
    elif i_close is not None:
        shape = "balance"
    else:
        return None
    # 이름 열 = 금액·수량이 아닌 앞쪽 열 전부(사업부문·해당회사·품목이 나뉘어 온다)
    num_idx = {i for i in (i_open, i_new, i_done, i_gross, i_close, i_date, i_due) if i is not None}
    name_idx = [i for i in range(len(cols)) if i not in num_idx
                and not re.search(r"수량|금액|비고", cols[i] or "")]
    rows = []
    for r in t["rows"]:
        labels = [r[i].strip() for i in name_idx if i < len(r) and r[i].strip()]
        label = " ".join(dict.fromkeys(labels))
        if not label:
            continue

        def g(i):
            return _scaled(r[i], mul) if i is not None and i < len(r) else None
        seg = labels[0] if labels else ""
        item = labels[-1] if len(labels) > 1 else ""
        # 가운데 라벨(`해당회사` 열의 연결자회사 목록)은 버린다 — 한화시스템 '기타' 행이
        # 자회사 8개 이름을 통째로 달고 온다.
        label = (seg + (" · " + item[:40] if item else "")).strip()
        rec = {"label": label, "total": is_total(label), "seg": seg, "item": item,
               "opening": g(i_open), "new": g(i_new), "delivered": g(i_done),
               "gross": g(i_gross), "closing": g(i_close),
               "order_date": (r[i_date].strip() if i_date is not None and i_date < len(r) else ""),
               "due": (r[i_due].strip() if i_due is not None and i_due < len(r) else "")}
        if rec["closing"] is None and rec["gross"] is None and rec["opening"] is None:
            continue
        if rec["delivered"] is not None and rec["delivered"] < 0:
            rec["delivered"] = -rec["delivered"]        # 기납품액을 (음수)로 적는 회사가 있다
        rec["kind"] = seg_kind(rec["seg"]) or seg_kind(rec["label"])
        rows.append(rec)
    if not rows:
        return None
    out = {"shape": shape, "cur": cur, "unit_seen": seen, "qty_unit": qty_unit, "rows": rows,
           "unit_from_prev": bool(t.get("unit_from_prev")),
           "cols": t["cols"], "lead": (t.get("lead") or "")[-200:],
           "security_note": bool(_SECURITY.search(t.get("lead") or "")),
           "matched": {k: m[k] for k in MATCH_KEYS},
           "header_synth": t.get("header_synth")}
    if t.get("header_synth"):
        out["cols_raw"] = list(t.get("cols_raw") or [])
    return out


def orders_unknown(t):
    """수주표 어휘(총액·잔고)가 보이는데 parse_orders_table 이 못 읽은 표 → {cols, lead, reason}.
    수주표가 아니면 None. reason(지도 tag·큐 판단의 근거):
      award     발주처·계약명·계약기간·계약금액만 있는 공시 계약 목록(비츠로넥스텍 `가-1. 공시된 계약 현황`)
                — 잔고 열이 없어 잔고로 싣지 않는다(계약 공시 원장과 겹친다). 사람이 판단한다.
      no_close  총액은 있는데 잔고가 없다(대한항공 종속 한국공항 `수주금액|납품금액` — '매출실적을 기재').
      qty_only  금액 열 없이 수량·중량 열만 있다.
      no_rows   열은 읽었는데 숫자 행이 없다(전부 '-', `USD 12,510,000` 같은 통화 접두 값 — 통화 혼재 표)."""
    if not t.get("cols"):
        return None
    m = _match_cols(t["cols"])
    if m["gross"] is None and m["close"] is None:
        if not m["qty_only"]:
            return None
        reason = "qty_only"
    elif m["close"] is None:
        award = m["client"] is not None and (m["period"] is not None or m["date"] is not None
                                             or m["due"] is not None)
        reason = "award" if award else "no_close"
    else:
        reason = "no_rows"
    return {"cols": list(t["cols"]), "lead": (t.get("lead") or "")[-120:], "reason": reason,
            "n_rows": len(t.get("rows") or [])}


_ORDERS_WORDS = re.compile(r"수주|잔고|잔액|기납품|납품")


def headerless_unknown(t):
    """머리행을 못 살려 버린 표 중 수주형 낱말이 첫 두 줄에 있는 것 → {cols: [], first, lead, reason: no_header}."""
    rows = t.get("rows") or []
    head = " ".join(" ".join(r) for r in rows[:2])
    if not _ORDERS_WORDS.search(head):
        return None
    return {"cols": [], "first": [c for c in (rows[0] if rows else [])][:10],
            "lead": (t.get("lead") or "")[-120:], "reason": "no_header", "n_rows": len(rows)}


# ── 매출실적(부문 × 내수/수출) ──────────────────────────────

_KIND_WORDS = {"수출": "수출", "해외": "수출", "국내": "내수", "내수": "내수", "합계": "합계",
               "계": "합계", "소계": "합계"}
_KIND_REAL = ("수출", "해외", "국내", "내수")       # 합계만 있는 표는 매출실적이 아니다
_CUST_COL = re.compile(r"매출처|거래처|고객|발주처")


def parse_revenue_table(t):
    """내수/수출이 갈린 매출 표 → {basis, cur, rows:[{seg, item, kind, val, vals}]}.

    회사마다 열 구성이 다르다(부문|매출유형|품목|수출/내수|당반기|전기…). `수출/내수`가
    **셀 값으로** 오는 열을 찾아 기준으로 삼는다 — 열 이름을 믿지 않는다.
    `합계`만 있는 표는 수주표의 합계 행이 걸린 것이므로 받지 않는다(한화시스템 실측).

    basis: `segment`(사업부문별) | `customer`(매출처별 — KAI `주요 매출처 현황`).
    방산비중은 segment 근거로만 만들고, 수출비중은 둘 다 쓸 수 있다."""
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
        # 매출처 표는 구분 열이 앞에 오고 이름이 뒤에 오기도 한다(KAI `매출유형|품목`)
        if not labels:
            labels = [c.strip() for c in r[i_kind + 1:i_kind + 2] if c.strip() and num_of(c) is None]
        vals = [_scaled(v, mul) for v in r[i_kind + 1:] if num_of(v) is not None or v.strip() in ("", "-")]
        nums = [v for v in vals if v is not None]
        if not nums:
            continue
        seg = labels[0] if labels else ""
        rows.append({"seg": seg, "item": " ".join(labels[1:]), "kind": k,
                     "val": nums[0], "vals": vals,
                     "segkind": seg_kind(seg) or seg_kind(" ".join(labels))})
    if not rows:
        return None
    # `판매경로·판매방법·판매전략` 표는 매출실적이 아니라 영업방식 설명이다 —
    # 시장구분 열에 내수/수출이 적혀 있어 매출표로 오인된다(한화시스템 실측: 비중 100 을
    # 매출로 읽어 연매출이 1억원이 된다).
    if re.search(r"판매경로|판매방법|판매전략", " ".join(t["cols"])):
        return None
    head = " ".join(t["cols"][:max(1, i_kind + 1)])
    basis = "customer" if (_CUST_COL.search(head) or _CUST_COL.search((t.get("lead") or "")[-120:])) \
        else "segment"
    return {"basis": basis, "cur": cur, "unit_seen": seen, "i_kind": i_kind, "rows": rows,
            "period_cols": t["cols"][i_kind + 1:], "cols": t["cols"],
            "lead": (t.get("lead") or "")[-200:]}


_SALES_LEAD = re.compile(r"매출\s*실적|매출에\s*관한\s*사항|부문별\s*매출|매출\s*현황|매출\s*구성")


def parse_segment_sales(t):
    """내수/수출이 없는 **매출실적** 표 → 부문별 금액·비중(KAI `매출유형|품목|금액|비중`).

    방산비중의 근거가 여기 있다 — KAI 는 `방산 및 완제기수출` / `방산 기타 등` /
    `기체부품 및 민수, 수출 기타` 로 나눠 적는다(FINDINGS §6)."""
    cols = [_clean(c) for c in t["cols"]]
    lead = t.get("lead") or ""
    if not (_SALES_LEAD.search(lead) or any("매출" in c for c in cols)):
        return None
    if any(_clean(c) in _KIND_REAL for r in t["rows"][:8] for c in r[:4]):
        return None                       # 내수/수출 표는 parse_revenue_table 의 몫
    if _CUST_COL.search(" ".join(cols[:2])):
        return None                       # 매출처 표는 parse_customers 의 몫
    cur, mul, seen = unit_of(lead, t.get("cols"))
    # 금액 열의 이름이 회사마다 다르다 — `금액`(KAI)·`제27기 2분기`(한화시스템)·`당반기`.
    # 이름을 믿지 말고 **숫자가 처음 서는 열**을 값 열로 본다(앞쪽은 이름 열).
    i_amt = next((i for i, c in enumerate(cols)
                  if i >= 1 and "비중" not in c and "비율" not in c
                  and sum(1 for r in t["rows"] if i < len(r) and num_of(r[i]) is not None) >= 2), None)
    if i_amt is None:
        return None
    i_pct = next((i for i, c in enumerate(cols)
                  if i > i_amt and ("비중" in c or "비율" in c)), None)
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
                     # 부문 안의 `소 계`(한화시스템 상품/제품/용역/기타 → 소계)도 합계다.
                     "val": v, "total": is_total(seg) or is_total(item),
                     # 기간 열을 다 남긴다 — 잔고 커버리지의 분모(연매출)는 당기 누계가
                     # 아니라 **직전 사업연도 열**에서 읽어야 추정이 되지 않는다.
                     "vals": [_scaled(r[i], mul) if i < len(r) else None for i in val_idx],
                     "pct": (num_of(r[i_pct]) if i_pct is not None and i_pct < len(r) else None),
                     "segkind": seg_kind(seg) or seg_kind(" ".join(labels))})
    if not rows:
        return None
    return {"cur": cur, "unit_seen": seen, "rows": rows, "cols": t["cols"],
            "period_cols": [t["cols"][i] for i in val_idx],
            "lead": (t.get("lead") or "")[-200:]}


# ── 주요 거래처 ────────────────────────────────────────────

_CUST_LEAD = re.compile(r"주요\s*거래처|주요\s*매출처|매출처\s*현황|주요\s*고객")
# rowspan 복제로 오염된 표(FINDINGS §7 한화에어로 `판매방법 및 판매경로`)는 쓰지 않는다.
_CUST_BAD = re.compile(r"판매경로|판매방법|판매조직")
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
# 이름 열이 **사업부문** 인 표 — 행의 첫 칸이 거래처가 아니라 부문 이름이다. 한화시스템 `사업부문|해당 회사|…|
# 주요 매출처(비중)` 17분기가 거래처를 `방산·ICT·기타`로 실었고(6/7행이 부문명), 한화(000880) 8분기는
# `화약제조업` 등을 실었다(캐시 실측). 열 이름으로 거른다 — 이름 값으로 거르면(seg_kind) 진짜 거래처인
# 방위사업청·LIG디펜스앤에어로스페이스·한국항공우주산업이 '방산' 낱말에 걸려 같이 버려진다.
_CUST_SEGCOL = re.compile(r"^(사업)?부문(명|구분)?$")
# 거래처가 아니라 '몇 곳인가'를 적은 행 — 한화오션 `10% 이상 차지하는 주요 고객수`(19분기 전부 이 한 행).
_CUST_COUNT = re.compile(r"고객\s*수|거래처\s*수|매출처\s*수")


def parse_customers(t):
    """주요 거래처·매출처 표 → 이름과 비중. 부품사→체계업체 연결의 최상급 근거(FINDINGS §7).

    `판매경로`(rowspan 복제로 오염된 표)와 `주요 매출처 현황`이 **같은 lead 안에** 들어오는
    회사가 있다(KAI). 어느 쪽이 뒤에 오는지로 가른다 — 표 바로 앞의 제목이 그 표의 제목이다."""
    lead = t.get("lead") or ""
    good = max((m.end() for m in _CUST_LEAD.finditer(lead)), default=-1)
    bad = max((m.end() for m in _CUST_BAD.finditer(lead)), default=-1)
    if good < 0 and any(_CUST_LEAD.search(c or "") for c in t["cols"]):
        good = 0
    if good < 0 or bad > good:
        return None
    if t["cols"] and _CUST_SEGCOL.match(_clean(t["cols"][0])):
        return None
    cur, mul, _ = unit_of(lead, t.get("cols"))
    out = []
    # 두 모양: (a) 거래처가 행 (b) 거래처가 열(LIG 처럼 한 줄에 나란히)
    for r in t["rows"]:
        cells = [c.strip() for c in r if c and c.strip()]
        if not cells:
            continue
        if len(cells) >= 2 and not num_of(cells[0]):
            share = None
            for c in cells[1:]:
                m = _PCT.search(c)
                if m:
                    share = float(m.group(1))
                    break
            if share is None and len(cells) >= 2:
                v = num_of(cells[-1])
                share = v if v is not None and 0 < v <= 100 else None
            out.append({"name": cells[0], "share_pct": share,
                        "raw": cells[1:4]})
    for i, c in enumerate(t["cols"]):
        m = _PCT.search(c or "")
        if m and _clean(c):
            out.append({"name": re.sub(r"\(.*?\)|\d+(?:\.\d+)?\s*%", "", c).strip(),
                        "share_pct": float(m.group(1)), "raw": [c]})
    # 머리행이 본문 행으로 되풀이되는 표가 있다(KAI — `매출처 | 구분 | 금액 | 비중` 3줄).
    heads = {_clean(c) for c in t["cols"]} | {"매출처", "거래처", "구분", "고객", "품목", "매출액"}
    out = [o for o in out if o["name"] and not is_total(o["name"]) and _clean(o["name"]) not in heads
           and not _CUST_COUNT.search(o["name"])]
    return {"cur": cur, "rows": out, "lead": lead[-160:], "cols": t["cols"]} if out else None


# ── 수집 ───────────────────────────────────────────────────

_PARENT = re.compile(r"지배회사의\s*내용|지배회사\s*기준|당사의\s*수주")
_SUB = re.compile(r"종속회사의\s*내용")


def _orders_total(o):
    tot = [r for r in o["rows"] if r["total"]]
    if tot and tot[0].get("closing") is not None:
        return tot[0]["closing"]
    vals = [r["closing"] for r in o["rows"] if not r["total"] and r.get("closing") is not None]
    return sum(vals) if vals else 0


def _scope(lead):
    lead = lead or ""
    return "parent" if _PARENT.search(lead) else ("sub" if _SUB.search(lead) else "unknown")


def _pick_index(orders):
    """_pick_orders 가 고르는 표의 **번호**(없으면 None). max 는 같은 키면 앞 것을 돌려주므로
    번호로 골라도 _pick_orders 와 같은 표다 — 지도의 pick 플래그가 화면 값의 표와 어긋나지 않는다."""
    if not orders:
        return None

    def key(i):
        o = orders[i]
        lead = o.get("lead") or ""
        mark = 1 if (_PARENT.search(lead) and not _SUB.search(lead)) else (-1 if _SUB.search(lead) else 0)
        money = bool(o.get("unit_seen")) and not o.get("qty_unit")
        return (money, mark, o["shape"] != "balance", _orders_total(o), len(o["rows"]))
    return max(range(len(orders)), key=key)


def _pick_orders(orders):
    """여러 수주표 중 **회사 본체**의 표를 고른다.

    KAI 2026 반기에는 수주표가 5장 온다 — 지배회사(억원, 25.8조)와 종속회사 4곳(백만원,
    수백억~1천억). 행 수로 고르면 자회사 에스앤케이항공(5행)이 이겨 KAI 수주잔고가
    8,233억으로 실려 버린다(실측). 앞선 문장의 `[지배회사의 내용]` 표시를 1순위로,
    표시가 없으면 잔고가 가장 큰 표를 고른다(잔액형은 뒤로 민다). 나머지는 orders_all 에 남는다."""
    i = _pick_index(orders)
    if i is None:
        return None
    best = dict(orders[i])
    best["scope"] = _scope(best.get("lead"))
    return best


def _keep(t):
    """캐시에 남길 표인지 — 수주·매출·거래처 표만(정기보고서 전체를 담으면 캐시가 터진다)."""
    blob = " ".join(t["cols"]) + " " + (t.get("lead") or "")[-200:]
    return bool(re.search(r"수주|매출|거래처|매출처|고객|납기|잔고|잔액", blob))


def _raw_entry(t):
    """raw_tables 한 칸 — 원문 cols·rows·lead 에 합성 머리행 표지(header_synth·cols_raw)를 덧붙인다.
    표지를 남겨야 --reparse·지도 재생이 '이 머리행은 우리가 만든 것'을 안다(이전 캐시에는 없다)."""
    e = {"cols": t["cols"], "rows": t["rows"], "lead": (t.get("lead") or "")[-200:]}
    if t.get("header_synth"):
        e["header_synth"] = t["header_synth"]
        e["cols_raw"] = list(t.get("cols_raw") or [])
    return e


def parse_sales(tables, dropped=(), carry=()):
    """표 묶음(_headered 뒤) → 수주·매출·부문·거래처. collect_one·reparse_one·kdef_headers(지도 재생)가 이
    한 함수를 쓴다 — kgrid 처럼 collect_one 과 reparse_one 에 같은 줄을 두 벌 두면 한쪽만 고쳐지는 날이 온다.

    carry = 원문 표가 캐시에 없어 다시 뽑을 수 없는 **이미 읽은 수주표**(reparse_dict 가 넘긴다 — 아래 참고).
    반환 키 중 `_` 로 시작하는 것(후보 전부·채택 번호)은 지도 기록용이고 캐시에는 쓰지 않는다."""
    # 수주표로 읽힌 표는 매출표 후보에서 뺀다 — 현대로템 `진행률적용 수주 상황`(품목 45행)이
    # 매출실적으로 다시 읽히면 방산비중이 통째로 오염된다(실측).
    parsed = [(t, parse_orders_table(t)) for t in tables]
    orders = [o for _, o in parsed if o] + [dict(o) for o in carry]
    rest = [t for t, o in parsed if not o]
    revenue = [(t, x) for t, x in ((t, parse_revenue_table(t)) for t in rest) if x]
    segsales = [(t, x) for t, x in ((t, parse_segment_sales(t)) for t in rest) if x]
    customers = [(t, x) for t, x in ((t, parse_customers(t)) for t in tables) if x]
    rev = [x for _, x in revenue]
    seg_rev = [r for r in rev if r["basis"] == "segment"]
    pick_rev = max(seg_rev or rev, key=lambda r: len(r["rows"])) if rev else None
    pick_ss = max((x for _, x in segsales), key=lambda r: len(r["rows"])) if segsales else None
    pick_cu = max((x for _, x in customers), key=lambda c: len(c["rows"])) if customers else None
    unknown = [u for u in (orders_unknown(t) for t in rest) if u]
    unknown += [u for u in (headerless_unknown(t) for t in dropped) if u]
    return {"orders": _pick_orders(orders), "orders_all": orders,
            "revenue": pick_rev, "revenue_all": rev,
            "segment_sales": pick_ss, "customers": pick_cu,
            "unknown_headers": unknown,
            "_pick": _pick_index(orders), "_revenue": revenue, "_segsales": segsales,
            "_customers": customers, "_orders_ids": {id(t) for t, o in parsed if o},
            "_picked": {"revenue": pick_rev, "segsales": pick_ss, "customers": pick_cu}}


def fail_kind(d):
    """ok=False 캐시의 실패 갈래 — 캐시 1,125파일 중 실패 45건이 셋으로 갈린다(2026-10-12 실측):
      no_tables        절에 남은 표가 없다(raw_tables 비어 있음 — 옵트론텍 16·한일단조 15·대한항공 1·
                       파이버프로 1 = 33). 원문을 다시 받지 않고는 사유를 모른다. 이번 변경 뒤 수집분은
                       버린 무머리행 표를 unknown_headers(no_header)로 남기므로 no_header 로 갈린다.
      no_orders_table  표는 있는데 수주·매출표가 아니다(기가레인 `판매경로` 표만 10분기).
      award            공시 계약 목록만 있다(비츠로넥스텍 2분기 — orders_unknown 참고).
      unknown          그 밖의 수주형 미지 표.
    ok 면 None."""
    if d.get("ok"):
        return None
    unk = d.get("unknown_headers") or []
    if any(u.get("reason") == "award" for u in unk):
        return "award"
    if any(u.get("reason") not in ("no_header", "no_tables") for u in unk):
        return "unknown"
    if not d.get("raw_tables"):
        return "no_header" if any(u.get("reason") == "no_header" for u in unk) else "no_tables"
    return "no_orders_table"


def _apply_parsed(d, res, tables):
    """parse_sales 결과를 캐시 dict 에 싣는다(collect_one·reparse_one 공용 — 키와 순서가 같아야 한다)."""
    for k in ("orders", "orders_all", "revenue", "revenue_all", "segment_sales", "customers",
              "unknown_headers"):
        d[k] = res[k]
    d["ok"] = bool(d["orders"] or d["revenue"] or d["segment_sales"])
    if not d["ok"]:
        d["note"] = "수주·매출표 인식 실패 — 머리행 %s" % [t["cols"] for t in tables][:3]
        d["fail_kind"] = fail_kind(d)
    else:
        d.pop("fail_kind", None)
    return d


# ── 머리행 지도(hdrmap) — advisory ──────────────────────────
# 표 역할 4개를 매 (회사, 분기) 기록한다. 이 탭에서는 엔진이 실패해도 수집이 멈추지 않는다 —
# 엔진 안의 오류는 엔진이 stderr + 큐 engine_error 로 남기고, 여기서 나는 오류(어댑터)도 같은 꼴로 남긴다.
_ORDERS_NEED = ["close"]        # 미지 수주표의 '빠진 것' — 잔고 열(이 탭 1차 축이 잔고 커버리지다)


def _fields(n, pairs):
    f = [None] * n
    for k, i in pairs:
        if i is not None and 0 <= i < n:
            f[i] = k
    return f


def order_fields(cols, m=None):
    """수주형 표의 열마다 **이 탭이 읽은 뜻** — 값 열은 matched 역할(open…due), 그 밖은 client·name·period(award
    식별)·qty(수량 열)·label(이름·비고). 빈칸을 남기지 않는 이유: 엔진의 A/B 판정은 빈 칸을 kce 건설 사전(COL_ALIAS)
    으로 다시 읽어 보는데, 방산 표의 `구분`·`품목` 이 건설 별칭(다의 열)에 걸려 사유가 `ambiguous:구분` 처럼
    엉뚱하게 적힌다 — 이 탭의 사유는 `need_missing:close`(잔고 열 없음)·`records_none`(숫자 행 없음)이어야 한다."""
    m = m or _match_cols(cols)
    f = _fields(len(cols), [(k, m.get(k)) for k in _AWARD_KEYS] + [(k, m.get(k)) for k in MATCH_KEYS])
    for i, c in enumerate(cols):
        if f[i] is None:
            f[i] = "qty" if _QTY_COL.search(_clean(c)) else "label"
    return f


def hdr_records(d, res):
    """캐시 한 건 + parse_sales 결과 → hdrmap.record 인자 4벌(orders·revenue·segsales·customers).

    orders  = orders_all 전부(채택 1장 = _pick_orders 의 표, ent ← scope, tag ← shape, synth ← header_synth)
              + 미지 수주형 표(pick False, tag ← 미지 사유) — 미지는 엔진이 큐(unknown)에 올린다.
    revenue = revenue_all(tag ← basis), segsales·customers = 후보 전부. 채택 = 화면에 실리는 한 장.
    n 은 머리행 포함 원행수라 이 탭 캐시로는 알 수 없다(parse_tables 가 몇 줄을 머리행으로 먹었는지 안 남는다)
    — 적지 않고, n_rec(레코드 수)만 적는다(엔진 규약: 추정 금지)."""
    st, q = d["stock"], d["quarter"]
    meta = {"name": d.get("name") or "", "stock": st, "rcpNo": d.get("rcp")}
    otabs = []
    for o in res["orders_all"]:
        otabs.append({"cols": o["cols"], "cols_raw": o.get("cols_raw") if o.get("header_synth") else None,
                      "fields": order_fields(o["cols"]), "n_rec": len(o["rows"]),
                      "lead": o.get("lead") or "", "ent": _scope(o.get("lead")), "tag": o["shape"],
                      "shape": o["shape"], "synth": o.get("header_synth"), "cur": o.get("cur"),
                      "unit_seen": o.get("unit_seen")})
    unknown = []
    for u in res["unknown_headers"]:
        if not u["cols"]:
            continue                    # 무머리행 표 — 열이 없어 지도 항목이 못 된다(fail_kind·큐 no_tables 로 간다)
        it = {"cols": u["cols"], "fields": order_fields(u["cols"]),
              "n_rec": 0, "lead": u.get("lead") or "", "tag": "미지:" + u["reason"], "reason": "near_miss",
              "need": list(_ORDERS_NEED)}
        if u["reason"] == "no_rows":
            it["checks"] = {"records": False}       # 열은 맞는데 숫자 행이 없다 — 큐 사유 records_none
        unknown.append(it)
    out = [{"key": st, "q": q, "role": "orders", "tables": otabs,
            "picks": () if res["_pick"] is None else (res["_pick"],), "unknown": unknown, "meta": meta}]
    for role, pairs, tagk in (("revenue", res["_revenue"], "basis"), ("segsales", res["_segsales"], None),
                              ("customers", res["_customers"], None)):
        tabs, picks = [], ()
        for i, (t, x) in enumerate(pairs):
            if x is res["_picked"][role]:
                picks = (i,)
            pr = [("kind", x.get("i_kind"))] if role == "revenue" else []
            tabs.append({"cols": x.get("cols") or t["cols"],
                         "cols_raw": t.get("cols_raw") if t.get("header_synth") else None,
                         "fields": _fields(len(x.get("cols") or t["cols"]), pr),
                         "n_rec": len(x["rows"]), "lead": (t.get("lead") or "")[-120:],
                         "tag": (x.get(tagk) or "") if tagk else "", "synth": t.get("header_synth"),
                         "cur": x.get("cur"), "unit_seen": x.get("unit_seen")})
        out.append({"key": st, "q": q, "role": role, "tables": tabs, "picks": picks, "meta": meta})
    return out


def _picked_entry(rec):
    """record 인자(orders) 중 채택 표 dict(없으면 None)."""
    for i in rec["picks"]:
        return rec["tables"][i]
    return None


def prev_pick(M, st, q):
    """지도 dict M 에서 q 바로 앞(기록된 분기 중) 수주 채택 표의 (분기, 마스킹 열) — 없으면 None."""
    co = (M.get("companies") or {}).get(st) or {}
    by_q = (co.get("roles") or {}).get("orders") or {}
    for pq in sorted((x for x in by_q if x < q), reverse=True):
        picked = [e for e in by_q[pq] if e.get("pick")]
        if picked:
            return pq, hdrmap.mask_cols(picked[0].get("ncols") or picked[0].get("cols"))
        return None                     # 직전 기록 분기에 채택이 없으면 대조하지 않는다(바뀜이 아니라 소실이다)
    return None


def _supersede(st, q, kind, root=None):
    """(st, orders) 의 열린 kind 항목 중 q 보다 **앞 분기에 열린** 것을 닫는다(resolved_in=q). 반환 닫은 수.
    엔진은 changed 를 '같은 머리행이 뒤 분기에 다시 채택될 때'만 닫는다 — 머리행이 또 바뀌면 앞 바뀜은 영영
    열린 채 남는다(아스트 2023Q4·2024Q1, 한화시스템 2025Q4 실측). 새 바뀜이 앞 바뀜을 대신한다.
    no_tables 는 엔진이 '수주 채택이 생긴 분기'에만 닫는데, 기가레인처럼 수주표 없이 매출표로 정상화된 회사는
    영영 열린 채 남는다 — 실패가 아닌 분기(ok)가 오면 닫는다."""
    n = 0
    for it in hdrmap.open_items(HDR_TAB, root, kind=kind):
        if it["key"] == st and it["role"] == "orders" and (it.get("quarter_first") or "") < q:
            n += hdrmap.resolve_clean(HDR_TAB, st, "orders", q, ncols=it.get("ncols") or [], root=root) or 0
    return n


def hdr_stage(d, res, prev=None, root=None, queue=True):
    """한 (회사, 분기)를 스테이지에 올리고 큐 항목을 더한다. 쓰기(커밋)는 호출측 몫(hdrmap.write).

    queue=False 면 지도만 — 미지 표도 pick False 항목(tag 미지:사유)으로만 남고 큐에는 아무것도 올리지 않는다.
    kdef_headers 재생은 회사마다 **최신 분기만** queue=True 로 돈다: 큐는 '지금 사람이 볼 것'이고, 과거 분기의
    미지·바뀜을 다 올리면 다시는 닫히지 않는 항목이 쌓인다(2026-10-12 시험 재생: 열린 20건 중 13건이 과거 분기).
    큐(엔진 record 가 미지 수주형 표를 unknown 으로 올리는 것에 더해):
      no_tables  ok=False 인데 미지 수주형 표도 없음 — 사유 = fail_kind(no_tables|no_header|no_orders_table).
      synth      채택 수주표의 머리행이 합성(2row·첫 행 승격) — 사람이 한 번 본다(엔진 B 등급).
      changed    채택 수주표의 마스킹 머리행이 직전 기록 분기의 채택 표와 다르다(prev = prev_pick 결과).
                 다음 분기에 같은 머리행이 다시 채택되면 엔진이 닫고, 또 바뀌면 새 항목이 앞 항목을 대신한다.
    반환: 기록한 record 인자 목록."""
    recs = hdr_records(d, res)
    for r in recs:
        unk = r.get("unknown") or ()
        hdrmap.record(HDR_TAB, r["key"], r["q"], r["role"], r["tables"], r["picks"],
                      unknown=unk if queue else (), rejected=() if queue else unk, meta=r["meta"], root=root)
    if not queue:
        return recs
    st, q, meta = d["stock"], d["quarter"], recs[0]["meta"]
    base = {"key": st, "stock": st, "name": meta["name"], "role": "orders", "quarter": q, "rcpNo": meta["rcpNo"]}
    fk = d.get("fail_kind") or fail_kind(d)
    if fk in ("no_tables", "no_header", "no_orders_table"):
        hdrmap.enqueue(HDR_TAB, dict(base, kind="no_tables", reason=fk), root=root, strict=False)
    elif d.get("ok"):
        _supersede(st, q, "no_tables", root)
    pk = _picked_entry(recs[0])
    if pk and pk.get("synth"):
        hdrmap.enqueue(HDR_TAB, dict(base, kind="synth", cols_raw=pk["cols"], lead=pk["lead"],
                                     reason="synth:%s" % pk["synth"]), root=root, strict=False)
    if pk and prev:
        now = hdrmap.mask_cols([norm_col(c) for c in pk["cols"]])
        if now != prev[1]:
            _supersede(st, q, "changed", root)
            hdrmap.enqueue(HDR_TAB, dict(base, kind="changed", cols_raw=pk["cols"], lead=pk["lead"],
                                         reason="%s 대비: %s" % (prev[0], "|".join(prev[1]))[:200]),
                           root=root, strict=False)
    return recs


def _hdr_collect(d, res, log=sys.stderr):
    """collect_one·reparse_one 의 훅 — 캐시 쓰기가 끝난 뒤 그 (회사, 분기)만 기록·커밋. 수집을 멈추지 않는다."""
    st = d.get("stock")
    try:
        M = hdrmap.load_map(HDR_TAB, HDR_ROOT)
        hdr_stage(d, res, prev=prev_pick(M, st, d["quarter"]), root=HDR_ROOT)
        hdrmap.write(HDR_TAB, key=st, root=HDR_ROOT)
    except Exception as e:                       # 어댑터 오류 — 엔진과 같은 꼴로 흔적을 남긴다
        hdrmap.discard(HDR_TAB, st)
        log.write("hdrmap kdef %s %s: %s: %s\n" % (st, d.get("quarter"), type(e).__name__, e))
        try:
            hdrmap.enqueue(HDR_TAB, {"kind": "engine_error", "key": st or "", "stock": st,
                                     "quarter": d.get("quarter") or "",
                                     "reason": "kdef_reports %s: %s" % (type(e).__name__, str(e)[:200])},
                           root=HDR_ROOT, strict=False)
        except Exception:
            pass


import report_refresh as RF

def collect_one(rec, quarter, force=False, log=sys.stderr):
    st = rec["stock"]
    path = os.path.join(CACHE, st, quarter + ".json")
    cached = RF.read(path)
    if cached is not None and not force and not RF.due(cached, quarter):
        return cached
    out = {"stock": st, "name": rec.get("name", ""), "quarter": quarter, "ok": False, "note": ""}
    start, end = RF.window(quarter)
    try:
        reports = RF.candidates(search_reports(st, start, end, report_kind(quarter)), quarter)
    except Exception as e:
        out["note"] = "검색 실패: %s" % e
        return out
    if not reports:
        out["note"] = "정기보고서 없음"
        return out
    for rcp, title in reports[:3]:
        if cached and cached.get("ok") and not force and RF.receipt(cached) == rcp:
            return RF.checked(path, cached)
        nodes = toc(rcp)
        found = find_sections(nodes, SECTIONS)
        if "sales" in found:
            break
    else:
        out["note"] = "매출·수주 절 없음"
        return out
    out["rcp"], out["title"] = rcp, title
    html = fetch_section(found["sales"])
    dropped = []
    tables = _headered(_carry_units(parse_tables(html)), dropped)
    res = parse_sales(tables, dropped)
    _apply_parsed(out, res, tables)
    # 수주표로 읽힌 표는 낱말이 없어도 남긴다 — KAI 종속회사 수주표 4장은 lead 가 `[ 종속회사의 내용 ]
    # (주)에비오시스 테크놀러지스 (단위 : 백만원)` 뿐이라 _keep 에 걸리지 않아 원문이 캐시에 없다(재파싱 불가).
    out["raw_tables"] = [_raw_entry(t) for t in tables if _keep(t) or id(t) in res["_orders_ids"]]
    txt = re.sub(r"<[^>]+>", " ", html)
    out["security_note"] = bool(_SECURITY.search(txt))
    if not out["ok"]:
        out["fail_kind"] = fail_kind(out)        # raw_tables 를 채운 뒤 다시 가른다(no_tables 판정)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    RF.save(path, out)
    log.write("%s %s %s %s\n" % (st, quarter, "ok" if out["ok"] else "FAIL",
                                 (out["orders"] or {}).get("shape", "-")))
    log.flush()
    _hdr_collect(out, res, log)
    return out


def reparse_dict(d):
    """캐시 dict → (다시 뽑은 dict, parse_sales 결과). **메모리에서만** — 파일을 쓰지 않는다(kdef_headers 재생용).
    raw_tables 가 없으면 값은 그대로 두고 실패 갈래만 적는다(res 는 빈 표 묶음의 결과)."""
    d = json.loads(json.dumps(d))
    if not d.get("raw_tables"):
        if not d.get("ok"):
            d.setdefault("unknown_headers", [])
            d["fail_kind"] = fail_kind(d)
        return d, parse_sales([], carry=d.get("orders_all") or ())
    # 원문 표가 raw_tables 에 없는 수주표(_keep 에 안 걸린 KAI 종속회사 4장 등 — 2026-10-12 이전 수집분 37파일)는
    # 다시 뽑을 수 없으니 **이미 읽은 결과 그대로** 후보에 남긴다. 버리면 orders_all 이 줄고(KAI 5장→1장)
    # 지도에서 종속회사 표가 사라진다. 원문이 있는 표는 (cols, lead) 가 같으므로 새 파서가 다시 읽는다.
    raw_keys = {(tuple(t.get("cols") or []), (t.get("lead") or "")[-200:]) for t in d["raw_tables"]}
    carry = [o for o in d.get("orders_all") or []
             if (tuple(o.get("cols") or []), (o.get("lead") or "")[-200:]) not in raw_keys]
    tables = _headered(_carry_units(d["raw_tables"]))
    res = parse_sales(tables, carry=carry)
    _apply_parsed(d, res, tables)
    d["reparsed"] = True
    return d, res


def reparse_one(path, log=sys.stderr, write=True):
    """캐시의 `raw_tables`(원문 cols·rows·lead)만으로 파싱 결과를 **다시 만든다** — kgrid_reparse_one 이식.

    COMMON §0-4 가 원문 캐시를 남기라고 한 이유가 이것이다 — 파서를 고쳤을 때 DART 를 다시 긁지 않는다.
    lead 는 캐시에 200자로 잘려 있어 아주 긴 앞 문맥에 캡션이 있던 표는 unit_seen=False 가 될 수 있다 —
    그러면 금액으로 싣지 않는다(fail-closed, 값이 줄어드는 방향). security_note 는 절 본문 전체에서 읽은
    값이라 그대로 둔다. raw_tables 가 없는 캐시(실패 33건 '머리행 []')는 다시 뽑을 것이 없다 — 값은 그대로
    두고 실패 갈래만 no_tables 로 적는다. 내용이 같으면 파일을 다시 쓰지 않는다(멱등)."""
    with open(path, encoding="utf-8") as f:
        before = f.read()
    d, res = reparse_dict(json.loads(before))
    text = json.dumps(d, ensure_ascii=False, indent=1) + "\n"
    if write and text != before:
        atomic_write(path, text)
    log.write("%s %s reparse %s %s\n" % (d.get("stock"), d.get("quarter"),
                                         "ok" if d.get("ok") else "FAIL:%s" % d.get("fail_kind"),
                                         (d.get("orders") or {}).get("shape", "-")))
    if write:
        _hdr_collect(d, res, log)
    return d


def reparse(rows, qs):
    want = {r["stock"] for r in rows}
    n = 0
    for st in sorted(want):
        for q in qs:
            p = os.path.join(CACHE, st, q + ".json")
            if os.path.exists(p):
                reparse_one(p)
                n += 1
    return n


def quarters(latest, n=8):
    """최근 n개 분기(오래된 것부터). 정기보고서가 없는 분기는 수집 때 걸러진다."""
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


def _sum_rows(rows, field, kinds=None):
    vals = [r[field] for r in rows
            if not r["total"] and r.get(field) is not None and (kinds is None or r.get("kind") in kinds)]
    return sum(vals) if vals else None


_FY_COL = re.compile(r"20\d\d년|제\d+기")
_PART_YEAR = re.compile(r"반기|분기|누적|개월|기중|비중|비율")


def _is_fy(col):
    """'2025년(제27기) 금액'·'제26기' 는 1년 열, '2026년 반기'·'비중' 은 아니다."""
    c = _clean(col)
    return bool(_FY_COL.search(c)) and not _PART_YEAR.search(c)


def _fy_revenue(rv):
    """매출 표에서 **온전한 1년** 열을 찾아 총매출을 만든다 → (값, 열 이름).

    잔고 커버리지(잔고 ÷ 연매출, 년)의 분모다. 반기 누계를 두 배로 늘리면 추정이 되므로
    공시에 실제로 적힌 직전 사업연도 열을 쓴다. 열과 값의 개수가 어긋나면 만들지 않는다."""
    if not rv:
        return None, None
    cols = rv.get("period_cols") or []
    rows = rv.get("rows") or []
    idx = [i for i, c in enumerate(cols) if _is_fy(c)]
    def ok(r):
        return len(r.get("vals") or []) == len(cols)

    for i in idx:
        # 부문별 `합계` 행과 전체 `합 계` 행이 **둘 다** 오는 표가 있다(한화에어로) —
        # 다 더하면 매출이 정확히 두 배가 된다. 전체 합계가 있으면 그것만 쓴다.
        grand = [r for r in rows if r["kind"] == "합계" and is_total(r["seg"]) and ok(r)]
        per_seg = [r for r in rows if r["kind"] == "합계" and not is_total(r["seg"]) and ok(r)]
        use = grand or per_seg or [r for r in rows if r["kind"] in ("내수", "수출") and ok(r)]
        vals = [r["vals"][i] for r in use if r["vals"][i] is not None]
        if vals:
            return sum(vals), cols[i]
    return None, None


def _fy_segsales(ss):
    """부문별 매출 표에서 연매출 → (값, 열 이름). 내수/수출 표가 없는 회사(한화시스템)용.

    전체 `합 계` 행이 있으면 그것만, 없으면 부문 `소 계` 행들을, 그것도 없으면 낱 행을 더한다
    (소계와 낱 행을 함께 더하면 두 배가 된다)."""
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


def build(rows, qs):
    """캐시 → reports.json. 회사 × 분기의 수주잔고·방산비중·수출비중·커버리지."""
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
            # 단위를 못 읽었거나(캡션 없음) 금액이 아닌 단위(풍산 M/T)면 **금액으로 싣지 않는다**.
            money = bool(o.get("unit_seen")) and not o.get("qty_unit")
            backlog = (tot[0]["closing"] if tot and tot[0].get("closing") is not None
                       else _sum_rows(orows, "closing")) if money else None
            backlog_def = _sum_rows(orows, "closing", kinds=("def",)) if money else None
            rv = d.get("revenue") or {}
            rrows = rv.get("rows") or []
            dom = _sum_rows_rev(rrows, "내수")
            exp = _sum_rows_rev(rrows, "수출")
            ss = d.get("segment_sales") or {}
            srows = [r for r in (ss.get("rows") or []) if not r["total"]]
            # 방산비중 — 내수/수출 표(부문 근거)와 매출실적 표 중 부문 판정이 되는 쪽에서.
            mix_src = ("revenue" if (rv.get("basis") == "segment"
                                     and any(r["segkind"] for r in rrows)) else
                       ("segment_sales" if any(r["segkind"] for r in srows) else None))
            # 전체 `합 계` 행과 부문 `합계` 행이 같이 오는 표(한화에어로)에서 둘 다 더하면
            # 매출이 두 배가 되고 방산비중이 반토막 난다(13.8% ← 실제 27%). 전체 합계 행은
            # 분모로만 쓰고, 부문 판정은 **부문 행**에서 한다.
            if mix_src == "revenue":
                seg_tot = [r for r in rrows if r["kind"] == "합계" and not is_total(r["seg"])]
                real = [r for r in rrows if r["kind"] in ("내수", "수출") and not is_total(r["seg"])]
                mix_rows = seg_tot or real or rrows
            else:
                seg_tot = [r for r in srows if r.get("total") and not is_total(r["seg"])]
                mix_rows = seg_tot or [r for r in srows if not r.get("total")] or srows
            def_sales = sum(r["val"] for r in mix_rows
                            if r.get("segkind") == "def" and r.get("val") is not None) or None
            all_sales = sum(r["val"] for r in mix_rows if r.get("val") is not None) or None
            per_q[q] = {
                "ok": True, "rcp": d.get("rcp"), "shape": o.get("shape"),
                "cur": o.get("cur"), "unit_seen": o.get("unit_seen"),
                "backlog": backlog, "backlog_def": backlog_def,
                "opening": ((tot[0]["opening"] if tot and tot[0].get("opening") is not None
                             else _sum_rows(orows, "opening"))) if money else None,
                "delivered": _sum_rows(orows, "delivered") if money else None,
                "gross": _sum_rows(orows, "gross") if money else None,
                "unit_note": ("" if money else
                              ("수주표 단위가 금액이 아님(%s) — 금액으로 싣지 않음"
                               % (o.get("cur") or "미상") if o.get("qty_unit")
                               else "수주표 단위 캡션을 못 읽음 — 금액으로 싣지 않음") if o else ""),
                "unit_from_prev": bool(o.get("unit_from_prev")),
                "orders_scope": o.get("scope"),
                "segments": [{"label": r["label"], "kind": r.get("kind"), "closing": r["closing"],
                              "gross": r.get("gross"), "delivered": r.get("delivered"),
                              "due": r.get("due"), "order_date": r.get("order_date")}
                             for r in orows if not r["total"]],
                "revenue_basis": rv.get("basis"),
                "revenue_fy": (_fy_revenue(rv)[0] or _fy_segsales(ss)[0]),
                "revenue_fy_col": (_fy_revenue(rv)[1] or _fy_segsales(ss)[1]),
                "revenue_cols": rv.get("period_cols") or [],
                "revenue_domestic": dom, "revenue_export": exp,
                "revenue_segments": [{"seg": r["seg"], "item": r["item"], "kind": r["kind"],
                                      "segkind": r["segkind"], "val": r["val"]} for r in rrows],
                "sales_mix_src": mix_src,
                "sales_def": def_sales, "sales_all": all_sales,
                "sales_segments": [{"seg": r["seg"], "item": r["item"], "segkind": r["segkind"],
                                    "val": r["val"], "pct": r.get("pct")} for r in srows],
                "customers": (d.get("customers") or {}).get("rows") or [],
                "security_note": d.get("security_note", False),
            }
        if per_q:
            out[st] = {"stock": st, "name": rec.get("name", ""), "role": rec.get("role"),
                       "quarters": per_q}
    write_asset("reports.json", {"n": len(out), "quarters": qs, "companies": out})
    return out


def _sum_rows_rev(rrows, kind):
    vals = [(r["vals"] or [None])[0] for r in rrows if r["kind"] == kind]
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def load():
    try:
        return load_asset("reports.json")
    except FileNotFoundError:
        return {"companies": {}, "quarters": []}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--reparse", action="store_true",
                    help="DART 를 다시 긁지 않고 캐시의 원문 표(raw_tables)만으로 파싱 결과를 다시 만든다")
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
    qs = quarters(a.quarter or RF.latest_candidate(), a.n)
    if a.collect:
        collect(rows, qs, a.force)
    if a.reparse:
        print("재파싱 %d건" % reparse(rows, qs), file=sys.stderr)
    if a.build:
        res = build(rows, qs)
        ok = sum(1 for c in res.values() for q in c["quarters"].values() if q.get("ok"))
        print("회사 %d · 분기레코드 %d" % (len(res), ok))
        for st, c in list(res.items())[:8]:
            last = [q for q in qs if q in c["quarters"] and c["quarters"][q].get("ok")]
            if last:
                v = c["quarters"][last[-1]]
                print("  %s %-16s %s 잔고 %s (%s) 수출 %s"
                      % (st, c["name"][:16], last[-1], v["backlog"], v["shape"], v["revenue_export"]))


if __name__ == "__main__":
    sys.exit(main())
