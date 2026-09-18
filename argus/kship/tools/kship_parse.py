#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_parse — 조선사·기자재사 수주 표를 산업 특성에 맞게 읽는다.

kce_parse.parse_tables(표 추출·머리행 평탄화·정규화)는 그대로 쓴다. 그 위의 레코드 추출만
조선용으로 다시 쓴다 — 건설용 `_records`를 그대로 쓰면 실측으로 확인된 세 가지가 깨진다:

  1. **수량(척) 열이 버려진다.** 건설은 '수주총액 수량'이 개수라 일부러 매핑하지 않는데,
     조선은 척수가 핵심 지표다(선종별 잔량 N척). `qty`로 살린다.
  2. **합계 행이 파싱 단계에서 사라진다.** 조선사 수주표는 선종별 소계+합계 구조라 합계 행이
     '원문이 스스로 밝힌 총계'다. 버리지 않고 `total=True`로 표시해 대조에 쓴다.
  3. **`(단위: 백만달러)`가 백만원(1.0)으로 조용히 읽힌다.** 조선 수주는 달러 계약이 기본이라
     통화를 잃으면 환율 축이 통째로 사라진다. 단위 캡션에서 통화를 읽어 `cur`에 싣고, 금액은
     그 통화의 **백만 단위**로 정규화한다(백만원 / 백만달러). 원화 환산은 빌더가 분기말 환율로 한다.

stdlib 전용. 머리행 별칭은 조선 방언을 더한 뒤 건설 별칭(COL_ALIAS)으로 폴백한다.
"""
import contextlib
import re

from kship_lib import norm_col, num_of, parse_tables
from kce_lib import COL_ALIAS                           # noqa: E402
import kce_parse                                        # noqa: E402

# 조선 수주표 방언 → 표준 필드. 건설 별칭보다 먼저 본다.
SHIP_ALIAS = {
    # 이름·구분
    "선종": "type", "선종별": "type", "선박종류": "type", "선박명": "nm", "호선": "nm", "호선명": "nm",
    "선명": "nm", "프로젝트": "nm", "공사명": "nm", "품목": "nm", "구분": "nm", "사업부문": "seg",
    "선주": "cl", "발주처": "cl", "발주자": "cl", "계약상대방": "cl",
    # 날짜
    "계약일": "sd", "수주일자": "sd", "수주일": "sd", "계약일자": "sd",
    "인도예정일": "ed", "인도일": "ed", "납기": "ed", "인도시기": "ed", "인도예정": "ed",
    "완공예정일": "ed", "계약종료일": "ed",
    # 수량(척) — 건설이 버리는 열
    "척수": "qty", "수량": "qty", "수주총액수량": "qty", "수주잔고수량": "qty_bal",
    "기납품액수량": "qty_done", "인도척수": "qty_done", "잔량척수": "qty_bal", "잔여척수": "qty_bal",
    # 금액
    "수주총액": "amt", "수주총액금액": "amt", "계약금액": "amt", "수주금액": "amt", "총계약금액": "amt",
    "기납품액": "cmp", "기납품액금액": "cmp", "완성공사액": "cmp", "매출인식액": "cmp", "누적매출": "cmp",
    "수주잔고": "bal", "수주잔고금액": "bal", "수주잔량": "bal", "잔고": "bal", "계약잔액": "bal",
    "진행률": "pr", "공정률": "pr",
}

_II4_NEED = {"nm", "amt", "bal"}          # 조선 표 판별 핵심(cmp는 없는 회사가 있다)

# 단위 캡션 → (통화, 백만 단위 환산 배수)
_UNIT_RE = re.compile(r"단위\s*:?\s*([^)\]]{1,24})")
# **긴 이름이 먼저** 와야 한다(십억원 > 억원 > 원). 배수 접두사가 붙은 **영문 통화 코드**
# (`천USD`·`백만USD`)를 빼먹으면 짧은 `usd` 항목에 먼저 걸려 1000배 틀린다 — 일진전기 103590
# 수주표 캡션이 `(단위 : 천USD )`이고, 219,129천USD가 0.219백만USD로 읽혔다(kgrid FINDINGS §2).
_UNIT_TABLE = [
    ("백만달러", "USD", 1.0), ("백만불", "USD", 1.0), ("백만usd", "USD", 1.0),
    ("million usd", "USD", 1.0), ("mil.usd", "USD", 1.0),
    ("천달러", "USD", 0.001), ("천불", "USD", 0.001), ("천usd", "USD", 0.001),
    ("thousand usd", "USD", 0.001),
    ("usd", "USD", 1e-6), ("달러", "USD", 1e-6), ("us$", "USD", 1e-6),
    ("백만유로", "EUR", 1.0), ("백만eur", "EUR", 1.0),
    ("천유로", "EUR", 0.001), ("천eur", "EUR", 0.001), ("eur", "EUR", 1e-6), ("유로", "EUR", 1e-6),
    ("십억원", "KRW", 1000.0), ("백만원", "KRW", 1.0), ("억원", "KRW", 100.0),
    ("천원", "KRW", 0.001), ("만원", "KRW", 0.01), ("원", "KRW", 1e-6),
]


def unit_of(lead, cols=None):
    """표의 단위 캡션 → (통화, 배수). 통화를 못 읽으면 KRW·1.0으로 두되 `unit_seen=False`.

    '(단위: 백만달러, 척)'처럼 수량 단위가 함께 오는 경우가 많다 — 통화 토큰만 찾는다.
    """
    m = _UNIT_RE.findall(lead or "")
    if not m and cols:
        m = _UNIT_RE.findall(" ".join(cols))
    if not m:
        return "KRW", 1.0, False
    txt = m[-1].replace(" ", "").lower()
    hits = [(cur, mul) for name, cur, mul in _UNIT_TABLE if name.lower() in txt]
    if not hits:
        return "KRW", 1.0, False
    # 원화 단위가 **같이 적힌** 캡션은 원화 표다 — 외화는 괄호 병기일 뿐이고 표의 숫자는 원화다
    # (포메탈 119500 `[단위 : 백만원 (천USD)]`, 로체시스템즈 071280 `(단위 :천원, 천USD )`).
    # 이 갈래를 두지 않으면 멀쩡한 원화 표가 통째로 외화가 된다.
    krw = [h for h in hits if h[0] == "KRW"]
    cur, mul = (krw or hits)[0]
    return cur, mul, True


# 낱자 '계'는 앞이 공백·괄호일 때만 소계다 — '기본설계'·'실시설계'·'통합제어계'를 소계로
# 오인하면 사업장이 통째로 집계에서 빠진다(건설 탭에서 실제로 겪은 오류).
_TOTAL = re.compile(r"(?:합계|총계|소계|누계)(?![가-힣])")
_TOTAL_BARE = re.compile(r"(?:^|[\s)\]])계\s*$")


def is_total(nm):
    t = re.sub(r"[\s　]+", "", nm or "")
    return bool(t) and bool(_TOTAL.search(t) or _TOTAL_BARE.search(nm or ""))


def _fields(cols):
    out = []
    for c in cols:
        n = norm_col(c)
        out.append(SHIP_ALIAS.get(n) or COL_ALIAS.get(n))
    return out


@contextlib.contextmanager
def _ship_header_vocab():
    """머리행 감지 어휘를 조선 방언으로 잠시 넓힌다.

    kce_parse는 th 없는 표의 머리행을 '셀 절반 이상이 알려진 열 이름'으로 찾는데, 그 어휘가
    건설 별칭이라 `선종|수량|금액|인도예정` 2단 머리행을 데이터로 읽어 표 전체를 놓친다.
    전역을 영구히 바꾸지 않고(건설 경로의 바이트 동일 렌더 계약을 건드리지 않기 위해)
    이 파서가 도는 동안만 넓힌다.
    """
    vocab = kce_parse._HDR_VOCAB
    added = (set(SHIP_ALIAS) | {"수량", "금액", "척", "척수", "비고"}) - vocab
    vocab |= added
    try:
        yield
    finally:
        vocab -= added


def _records(t):
    fields = _fields(t["cols"])
    idx = {}
    for i, f in enumerate(fields):
        if f and f not in idx:
            idx[f] = i
    # 선종별 잔량표는 이름 열이 없고 `선종`이 행의 이름이다 — type 이 nm 을 대신한다.
    if "nm" not in idx and "type" in idx:
        idx["nm"] = idx["type"]
    if not _II4_NEED.issubset(idx):
        return None
    cur, mul, seen = unit_of(t.get("lead"), t.get("cols"))
    money = ("amt", "cmp", "bal")
    recs = []
    for r in t["rows"]:
        rec = {"cur": cur, "unit_seen": seen}
        for f, i in idx.items():
            v = r[i] if i < len(r) else ""
            if f in money:
                x = num_of(v)
                if x is not None and mul != 1.0:
                    x = x * mul
                    x = int(x) if float(x).is_integer() else round(x, 6)
                rec[f] = x
            elif f in ("qty", "qty_bal", "qty_done", "pr"):
                rec[f] = num_of(v)
            else:
                rec[f] = (v or "").strip()
        rec["total"] = is_total(rec.get("nm")) or is_total(rec.get("type"))
        # 이름이 비었는데 선종만 있는 표(선종별 잔량표)는 선종이 곧 행의 이름이다
        if not rec.get("nm") and rec.get("type"):
            rec["nm"] = rec["type"]
        if not rec.get("nm") and rec.get("amt") is None and rec.get("bal") is None:
            continue
        recs.append(rec)
    return recs


def parse_orders(html):
    """수주상황 절 HTML → {'tables':[{lead, cols, cur, n, rows}], 'unknown_headers':[]}.

    건설과 달리 합계 행을 **버리지 않는다**(`total=True`). 통화는 표마다 `cur`.
    """
    picked, unknown = [], []
    with _ship_header_vocab():
        tables = parse_tables(html)
    for t in tables:
        recs = _records(t)
        if recs is None:
            f = {x for x in _fields(t["cols"]) if x}
            if len(_II4_NEED & f) >= 2 and len(t["rows"]) >= 3:
                unknown.append({"cols": t["cols"], "n": len(t["rows"])})
            continue
        cur = recs[0]["cur"] if recs else "KRW"
        picked.append({"lead": (t.get("lead") or "")[-160:], "cols": t["cols"], "cur": cur,
                       "n": sum(1 for r in recs if not r["total"]), "rows": recs})
    return {"tables": picked, "unknown_headers": unknown}
