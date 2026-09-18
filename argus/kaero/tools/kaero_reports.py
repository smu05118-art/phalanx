#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kaero_reports — 정기보고서 「II-4 매출 및 수주상황」에서 우주항공 회사의 분기 지표를 읽는다.

이 산업이 조선·방산과 **다른 점 셋**(FINDINGS 에서 원문으로 확인한 것):

  1. **통화가 표마다 다르다.** 아스트는 `1) 국외수주현황 (단위 : USD )` 와
     `2) 국내수주현황 (단위 : 원)` 두 표를 나란히 싣는다. 표를 하나만 고르면(kdef 방식)
     27억달러짜리 회사가 2.7억원짜리가 된다(scout 가 실제로 그렇게 적었다).
     → 수주표를 **통화별로 모아** `orders[cur]` 로 싣는다. **환산하지 않는다.**
  2. **계약 원장이 별도 목차에 있다.** 한화에어로 본문 수주표는 품목이 전부 `상세내역 참조`이고
     진짜는 「4. 수주상황(상세)」(XII. 상세표)에 계약 한 줄씩 수주일자·납기와 함께 있다.
     여기서 RSP·PBL·체계개발과 GE·P&W·RR 이 **품목 문자열로** 읽힌다.
  3. **겸업사의 수주표는 다른 탭과 중복 계상된다.** 한화에어로 요약표 7행에는 한화오션 해양
     34.5조(kship)와 한화시스템 방산 9.3조(kdef)가 들어 있다. 사업 열로 **부문 필터**를 걸고
     빠진 부문이 어느 탭 것인지 이름으로 남긴다(`dup_segments`).

원문 표(cols·rows·lead)를 캐시에 그대로 남긴다 — 파서가 자라면 재수집 없이 다시 뽑는다(COMMON §0-4).

    python3 kaero_reports.py --collect [--quarter 2026Q2] [--only 067390] [--n 6]
    python3 kaero_reports.py --build
"""
import argparse
import json
import os
import re
import sys

from kaero_lib import (ASSETS, CUR_ORDER, atomic_write, clean, fetch_section, is_total,
                       latest_quarter, load_asset, num_of, open_sections, parse_tables,
                       text_of, unit_of, write_asset)
from kaero_universe import load as load_universe

CACHE = os.path.join(ASSETS, "reports_cache")

SECTIONS = [
    ("sales", ["매출 및 수주상황", "수주상황", "매출실적"]),
    # 상세표 — 한화에어로처럼 본문이 `상세내역 참조`로 갈음하는 회사의 진짜 계약 원장.
    ("orders_detail", ["수주상황(상세)", "수주상황 (상세)", "수주현황(상세)"]),
    ("products", ["주요 제품 및 서비스", "주요 제품", "주요제품"]),
    ("overview", ["사업의 개요"]),
]

_SECURITY = re.compile(r"보안\s*관계상|보안상|군사기밀|보안\s*유지|영업비밀")


# ══ 표 복구 ═══════════════════════════════════════════════════════════════
# 아래 셋은 kdef_reports 가 방산 원문에서 찾아낸 것과 같은 복구다. 우주항공 원문에서도
# 그대로 필요했다(FINDINGS §5 하이즈항공 — 캡션이 옆 표에 있다). kdef 안의 사본을 import
# 하지 않는 이유는 kdef 파이프라인(kdef_universe·kdef_lib)까지 끌려오기 때문이다.
# 공용 층(kce_parse)으로 올리는 일은 HANDOFF 에 남긴다.

def _headered(tables):
    """머리행을 못 잡은 표(`cols=[]`)를 살린다. 첫 행이 모두 비숫자면 머리행으로 쓴다."""
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
        if not any(num_of(c) is not None for r in rows[1:] for c in r):
            continue
        cols = list(rows[0])
        if len({clean(c) for c in cols}) != len(cols):
            # 머리행이 두 줄인 표(`기 초|기 초` + `수량|금액`)가 먼저다.
            d = _two_row_header(t)
            if d:
                out.append(d)
                continue
            # 두 줄이 아니라면 rowspan/colspan 평탄화가 만든 **중복 이름**이다. 아스트
            # 매출실적이 `매출유형|품 목|품 목|제25기|…` 로 온다 — 그대로 버리면 매출이
            # 통째로 사라지고 커버리지(년)를 못 만든다. 뒤에 번호를 붙여 갈라 준다
            # (열 선택은 부분 문자열로 하므로 번호가 붙어도 판정이 달라지지 않는다).
            seen_c, uniq = {}, []
            for c in cols:
                k = clean(c)
                seen_c[k] = seen_c.get(k, 0) + 1
                uniq.append(c if seen_c[k] == 1 else "%s#%d" % (c, seen_c[k]))
            cols = uniq
        d = dict(t)
        d["cols"], d["rows"] = cols, rows[1:]
        d["header_synth"] = True
        out.append(d)
    return out


def _two_row_header(t):
    """머리행이 **두 줄**인 표(rowspan/colspan 평탄화 결과)를 살린다.

    `기 초 | 기 초 | 기 말 | 기 말` + `수량 | 금액 | 수량 | 금액` → `기 초 수량`·`기 초 금액`.
    fail-closed — 두 줄 다 비숫자이고 서로 다르며 셋째 행부터 숫자가 있어야 한다."""
    rows = t["rows"]
    if len(rows) < 3 or len(rows[0]) < 3 or len(rows[1]) != len(rows[0]):
        return None
    if any(num_of(c) is not None for c in rows[0] + rows[1]):
        return None
    if [clean(c) for c in rows[0]] == [clean(c) for c in rows[1]]:
        return None
    if not any(num_of(c) is not None for r in rows[2:] for c in r):
        return None
    cols = []
    for a, b in zip(rows[0], rows[1]):
        a, b = (a or "").strip(), (b or "").strip()
        cols.append(a if clean(a) == clean(b) or not b else (a + " " + b).strip())
    if len({clean(c) for c in cols}) != len(cols):
        return None
    d = dict(t)
    d["cols"], d["rows"] = cols, rows[2:]
    d["header_synth"] = "2row"
    return d


_UNIT_CAP = re.compile(r"단위\s*:?\s*[^)\]]{1,24}")
# 금액이 아닌 단위 — 이 산업은 `대`(항공기 대수)·`shipset`·`기`(엔진 기) 가 온다.
_UNIT_QTY = re.compile(r"M\s*/\s*T|톤|kg|개\b|대\b|기\b|척|set|shipset|쉽셋", re.I)
# 통화 토큰 — 캡션 안에 둘 이상이면 표 전체를 한 통화로 읽을 수 없다(FINDINGS §6).
_CUR_TOK = re.compile(r"백만달러|백만불|천달러|천불|USD|달러|EUR|유로|십억원|백만원|억원|천원|만원|원", re.I)


def _carry_units(tables):
    """자기 lead 에 없는 것을 **직전 표에서 물려준다** — 단위 캡션과 제목 둘 다.

    하이즈항공은 `(기준일 : …) (단위 : 백만원)` 한 줄짜리 표를 먼저 싣고 데이터 표의 lead 를
    비워 둔다. 캡션을 안 물려주면 1.16조가 '단위 미확인'이 되고(FINDINGS §5), **제목**을
    안 물려주면 「2. 주요 매출처 등 현황」이 매출처 표로 인식되지 않는다(고객 축이 통째로
    빈다). 캡션 표의 lead 가 바로 그 제목이므로 둘을 함께 물려준다."""
    out, last_cap, last_lead = [], None, ""
    for t in tables:
        lead = t.get("lead") or ""
        blob = " ".join([lead] + list(t["cols"]) + [" ".join(r) for r in t["rows"][:2]])
        caps = _UNIT_CAP.findall(blob)
        d = dict(t)
        new_lead = lead
        if not lead.strip() and last_lead.strip():
            new_lead = last_lead
            d["lead_from_prev"] = True
        if caps:
            last_cap = caps[-1]
        elif last_cap:
            new_lead = new_lead + " (%s)" % last_cap
            d["unit_from_prev"] = True
        d["lead"] = new_lead
        out.append(d)
        last_lead = lead if lead.strip() else last_lead
    return out


def _scaled(v, mul):
    """숫자 × 단위배수. **배수를 못 정했으면(mul=None) 값을 만들지 않는다** —
    통화가 섞인 표(FINDINGS §6)에서 배수를 1로 가정하면 763억원이 76.4백만달러가 된다."""
    x = num_of(v)
    if x is None or mul is None:
        return None
    x = x * mul
    # 자릿수를 넉넉히 남긴다 — 백만 단위로 줄인 뒤 3자리에서 끊으면 원(달러는 1,000달러)
    # 아래가 날아가 원문 합계와 어긋난다(아스트 USD 잔고에서 423달러가 틀렸다).
    return int(x) if float(x).is_integer() else round(x, 6)


# ══ 통화 ══════════════════════════════════════════════════════════════════

def table_currency(t):
    """표의 통화 → (cur, mul, seen, note).

    캡션에 통화 토큰이 **둘 이상**이면(`(단위 : USD, 천원)` — 켄코아) 한 통화로 읽을 수 없다.
    `MIXED` 로 두고 금액으로 싣지 않는다(fail-closed, FINDINGS §6)."""
    lead, cols = t.get("lead") or "", t.get("cols")
    caps = _UNIT_CAP.findall(lead) or _UNIT_CAP.findall(" ".join(cols or []))
    cap = caps[-1] if caps else ""
    toks = {m.group(0).upper().replace("불", "달러") for m in _CUR_TOK.finditer(cap)}
    # `백만원`은 `원`도 함께 잡힌다 — 통화(KRW/USD/EUR)가 몇 종인지로 센다.
    kinds = set()
    for tok in toks:
        kinds.add("USD" if ("USD" in tok or "달러" in tok)
                  else ("EUR" in tok or "유로" in tok) and "EUR" or "KRW")
    kinds = {k for k in kinds if k in ("KRW", "USD", "EUR")}
    if len(kinds) > 1:
        return "MIXED", None, False, "단위 캡션에 통화가 둘 이상(%s) — 금액으로 싣지 않음" % cap.strip()
    cur, mul, seen = unit_of(lead, cols)
    if not seen:
        return cur, mul, False, "단위 캡션을 못 읽음 — 금액으로 싣지 않음"
    if cap and _UNIT_QTY.search(cap) and not _CUR_TOK.search(cap):
        return cur, mul, False, "수주표 단위가 금액이 아님(%s) — 금액으로 싣지 않음" % cap.strip()
    return cur, mul, True, ""


# ══ 영역·계약성격·고객 ════════════════════════════════════════════════════
# 원문 문구(품목·사업·부문 이름)에서 읽는다. 근거 등급은 C(문구 분류) — 화면에 그대로 적는다.

_D_SPACE = re.compile(r"발사체|로켓|누리호|위성|탑재체|지상국|우주|KSLV|초소형\s*군집|궤도", re.I)
_D_MRO = re.compile(r"창정비|정비|MRO|오버홀|PBL|성과기반군수|수리|검사정비", re.I)
_D_ENGINE = re.compile(r"엔진|터빈|RSP|GTF|GEnx|LEAP|HPT|LPT|디스크|블레이드|케이스|APU|"
                       r"추진기관|연소기|노즐|압축기", re.I)
_D_STRUCT = re.compile(r"동체|기체|주익|날개|구조물|구조체|벌크헤드|스트링거|나셀|파일런|"
                       r"스킨|판넬|패널|Fuselage|Section\s*\d|Bulkhead|Stringer|Deck|Nacelle|"
                       r"Pylon|Wing|Spar|Rib|가공품|조립품", re.I)
_D_DEFAV = re.compile(r"방산|국방|군용|군수|해군|공군|육군|무장|전투기|훈련기|헬기|회전익|"
                      r"수리온|KUH|LAH|KF-?X|KF-?21|T-50|FA-50|KT-1|무인기|완제기|방위사업", re.I)


def domain_of(text):
    """품목·사업 문구 → 영역 id. 우선순위는 **더 좁은 뜻이 이긴다**.

    우주 > MRO > 엔진 > 기체구조물 > 방산항공. `PBL-KUH 상륙기동 엔진`은 엔진이 아니라
    성과기반군수(MRO)이고, `KF-X 엔진/APU 체계개발`은 방산이 아니라 엔진이다 —
    이 순서가 원문 실측(FINDINGS §3)과 맞는다.
    `조립` 단독은 기체구조물로 보지 않는다(`해군조립`은 방산이다)."""
    s = text or ""
    if _D_SPACE.search(s):
        return "space"
    if _D_MRO.search(s):
        return "mro"
    if _D_ENGINE.search(s):
        return "engine"
    if _D_STRUCT.search(s):
        return "struct"
    if _D_DEFAV.search(s):
        return "defav"
    return "other"


_N_RSP = re.compile(r"RSP|Risk\s*&?\s*Revenue|수익\s*분배|국제공동개발", re.I)
_N_PBL = re.compile(r"PBL|성과기반군수", re.I)
_N_DEV = re.compile(r"체계개발|개발\s*계약|시제|연구개발|R&D|탐색개발", re.I)
_N_MRO = re.compile(r"창정비|정비|오버홀|수리", re.I)
_N_LTA = re.compile(r"장기\s*공급|LTA|공급\s*계약|LONG\s*TERM", re.I)

NATURES = [
    ("RSP", "RSP(수익분배)", "개발비를 분담하고 엔진 인도 수십 년에 걸쳐 회수한다 — 일반 수주와 성격이 다르다"),
    ("PBL", "PBL(성과기반군수)", "가동률을 보장하고 대가를 받는 장기 정비계약"),
    ("DEV", "개발(R&D)", "체계개발·시제 — 양산 물량이 아니다"),
    ("MRO", "정비·창정비", "인도물이 아니라 서비스다"),
    ("LTA", "장기공급(LTA)", "프로그램 전체 물량을 한 번에 잡는다 — 잔고 배수가 길어지는 이유"),
    ("BATCH", "양산·단발", "위 어느 것도 문구에서 확인되지 않음"),
]
NATURE_LABEL = {n[0]: n[1] for n in NATURES}


def nature_of(text, order_date="", due=""):
    """계약 성격. 문구가 우선이고, 문구가 없으면 **수주~납기 10년 이상**을 LTA 로 본다."""
    s = text or ""
    if _N_RSP.search(s):
        return "RSP"
    if _N_PBL.search(s):
        return "PBL"
    if _N_DEV.search(s):
        return "DEV"
    if _N_MRO.search(s):
        return "MRO"
    if _N_LTA.search(s):
        return "LTA"
    y0, y1 = _year(order_date), _year(due)
    if y0 and y1 and y1 - y0 >= 10:
        return "LTA"
    return "BATCH"


_YEAR = re.compile(r"(19|20)\d{2}")


def _year(s):
    """`2015.05`·`2028`·`400대` → 연도 또는 None. 연도가 아닌 납기(수량)는 받지 않는다."""
    m = _YEAR.search(s or "")
    return int(m.group(0)) if m else None


# 고객 — OEM·Tier-1 실명. kaero_scan 의 사전을 그대로 쓴다(두 벌로 갈라지지 않게).
from kaero_scan import OEM, PRIME                                       # noqa: E402

TIERS = [("oem", "OEM 직납", ("Boeing", "Airbus", "Embraer", "Bombardier", "Lockheed",
                              "Gulfstream", "GE Aerospace", "Pratt & Whitney", "Rolls-Royce",
                              "Safran", "Leonardo", "Mitsubishi Heavy", "SAMC")),
         ("tier1", "Tier-1 하도", ("Spirit", "Honeywell", "Collins", "IAI", "TAI", "RUAG")),
         ]
_TIER_OF = {n: t for t, _, names in TIERS for n in names}


# 약칭만 나오는 고객 — 원문에 풀어 쓴 곳이 없으면 **추정(등급 C)** 이다. 아스트 수주표의
# `KAL`, 하이즈항공 매출처의 `ACM`·`BTC` 가 그렇다. 이름을 단정하지 않고 약칭 그대로 싣되
# 아는 약칭만 이름을 덧붙인다. `BOE` 는 하이즈 각주가 Boeing 이라 풀어 두었으므로 OEM 쪽이다.
ABBREV = {
    "KAL": ("대한항공", "prime"),
    "KAI": ("한국항공우주", "prime"),
    # 하이즈항공 매출처 표는 `BOE(주4)` 로 적고 각주에서 `BOE(Boeing Commercial Airplanes)`
    # 라고 풀어 준다. 각주 표를 아직 이름과 잇지 못하므로(HANDOFF ③-4) 여기서는 **추정**으로
    # 편다. 이 사전은 우주항공 모집단 안에서만 쓰인다(디스플레이 회사 BOE와 겹치지 않는다).
    "BOE": ("Boeing", "oem"),
}
ABBREV_STOCK = {"KAL": "003490", "KAI": "047810"}
PRIME_NAME = {"047810": "한국항공우주", "012450": "한화에어로스페이스", "003490": "대한항공",
              "272210": "한화시스템", "079550": "LIG디펜스앤에어로스페이스", "099320": "쎄트렉아이",
              "한국항공우주연구원": "한국항공우주연구원"}


def customers_in(text):
    """문구에서 읽은 고객 → [{name, tier, grade, stock}].

    등급 B = 원문에 이름·풀이가 그대로 있다. 등급 C = 약칭만 있어 사전으로 편 것(추정)."""
    s = text or ""
    out, seen = [], set()

    def add(name, tier, grade, stock=None):
        if name in seen:
            return
        seen.add(name)
        out.append({"name": name, "tier": tier, "grade": grade, "stock": stock})
    for name, pat in OEM.items():
        if re.search(pat, s, re.I):
            add(name, _TIER_OF.get(name, "tier1"), "B", None)
    for stock, pat in PRIME.items():
        if re.search(pat, s, re.I):
            add(PRIME_NAME.get(stock, stock), "prime", "B", stock if stock.isdigit() else None)
    for ab, (name, tier) in ABBREV.items():
        if re.search(r"\b%s\b" % ab, s) and name not in seen:
            add(name, tier, "C", ABBREV_STOCK.get(ab))
    return out


# ══ 수주표 ════════════════════════════════════════════════════════════════
# 부문(사업) 열의 값 → 어느 탭 것인가. 겸업사 중복 계상을 화면에 적기 위한 것이다(FINDINGS §4).
SEG_TAB = [
    ("kaero", re.compile(r"^항공$|항공우주|우주|항공기|기체", re.I)),
    ("kship", re.compile(r"해양|조선|선박|특수선|함정", re.I)),
    ("kdef", re.compile(r"방산|방위|지상|유도|디펜스", re.I)),
    ("other", re.compile(r"IT\s*서비스|ICT|철도|건설|플랜트|신동|기타", re.I)),
]


def seg_tab(name):
    """부문 이름 → 'kaero'|'kship'|'kdef'|'other'|None(판정 못 함)."""
    n = clean(name)
    if not n:
        return None
    for tab, pat in SEG_TAB:
        if pat.search(n):
            return tab
    return None


def _business_col(rows, name_idx):
    """이름 열 중 **사업부문 열**이 어느 것인지 데이터로 고른다.

    머리행 이름을 믿으면 틀린다 — 한화에어로 「수주상황(상세)」의 머리행은 `부문 | 사업 | 품목`
    인데 `부문` 열에 들어 있는 것은 **회사 이름**(한화오션㈜ 및종속회사)이고 사업부문은
    `사업` 열이다(FINDINGS §4). 부문을 잘못 잡으면 한화오션 해양 26.7조가 이 탭 잔고로
    들어온다(실측에서 실제로 그랬다).

    그래서 `seg_tab` 이 판정할 수 있는 값의 비율이 가장 높은 열을 고른다. 절반도 못 가르면
    부문 열이 없는 회사로 보고 None(전체가 이 탭 것)."""
    best, best_rate = None, 0.0
    for i in name_idx:
        vals = [r[i].strip() for r in rows if i < len(r) and r[i].strip()]
        if not vals:
            continue
        rate = sum(1 for v in vals if seg_tab(v)) / float(len(vals))
        # 같은 비율이면 앞 열을 쓴다(부문 열이 대개 앞에 온다)
        if rate > best_rate:
            best, best_rate = i, rate
    return best if best_rate >= 0.5 else None


def parse_orders_table(t):
    """수주표 한 장 → {shape, cur, unit_seen, rows}. 네 모양을 한 함수로 가른다.

    roll  기초+신규−기납품=기말 / openclose 기초·기말만 / gross 총액−기납품=잔고 /
    item  품목별 개별 계약(수주일자·납기 있음 — 이 산업의 계약 원장) / balance 잔액 한 줄."""
    cols = [clean(c) for c in t["cols"]]
    cur, mul, seen, unit_note = table_currency(t)

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

    i_open = first(col("기초", "금액"), col("기초"))
    i_new = first(col("신규", "금액"), col("신규"))
    i_done = first(col("기납품", "금액"), col("기납품"))
    i_gross = first(col("수주총액", "금액"), col("수주총액"), col("계약금액"), col("수주금액"))
    i_close = first(col("수주잔고", "금액"), col("수주잔고"), col("수주잔액"),
                    col("기말", "금액"), col("기말"), col("잔액"))
    i_date = first(col("수주일자"), col("계약일자"), col("수주일"))
    i_due = first(col("납기"), col("인도예정"), col("완공예정"), col("납품기한"))
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
    i_seg = _business_col(t["rows"], name_idx)
    rows = []
    for r in t["rows"]:
        labels = [r[i].strip() for i in name_idx if i < len(r) and r[i].strip()]
        labels = list(dict.fromkeys(labels))
        if not labels:
            continue

        def g(i):
            return _scaled(r[i], mul) if (i is not None and i < len(r) and mul is not None) else None
        biz = (r[i_seg].strip() if (i_seg is not None and i_seg < len(r)) else "")
        seg = biz or labels[0]
        item = " · ".join([x for x in labels if x != seg])
        label = " · ".join(labels)
        date = r[i_date].strip() if (i_date is not None and i_date < len(r)) else ""
        due = r[i_due].strip() if (i_due is not None and i_due < len(r)) else ""
        rec = {"label": label, "total": is_total(label), "seg": seg, "item": item,
               "opening": g(i_open), "new": g(i_new), "delivered": g(i_done),
               "gross": g(i_gross), "closing": g(i_close),
               "order_date": date, "due": due,
               "due_year": _year(due), "order_year": _year(date)}
        if rec["closing"] is None and rec["gross"] is None and rec["opening"] is None:
            continue
        if rec["delivered"] is not None and rec["delivered"] < 0:
            rec["delivered"] = -rec["delivered"]
        blob = label + " " + seg
        rec["domain"] = domain_of(blob)
        rec["nature"] = nature_of(blob, date, due)
        rec["tab"] = seg_tab(seg)
        rec["customers"] = customers_in(blob)
        rows.append(rec)
    if not rows:
        return None
    return {"shape": shape, "cur": cur, "unit_seen": seen, "unit_note": unit_note, "rows": rows,
            "unit_from_prev": bool(t.get("unit_from_prev")),
            "cols": t["cols"], "lead": (t.get("lead") or "")[-220:],
            "security_note": bool(_SECURITY.search(t.get("lead") or ""))}


_PARENT = re.compile(r"지배회사의\s*내용|지배회사\s*기준|당사의\s*수주")
_SUB = re.compile(r"종속회사의\s*내용")


def _orders_total(o):
    tot = [r for r in o["rows"] if r["total"]]
    if tot and tot[0].get("closing") is not None:
        return tot[0]["closing"]
    vals = [r["closing"] for r in o["rows"] if not r["total"] and r.get("closing") is not None]
    return sum(vals) if vals else 0


def _aero_score(o):
    """표 안에 항공·우주 행이 몇 줄인가 — 영역이 판정되거나 부문이 kaero 인 행."""
    return sum(1 for r in o["rows"] if not r["total"]
               and (r.get("domain") != "other" or r.get("tab") == "kaero"))


def group_orders(orders):
    """수주표들을 **통화별로** 모아 통화마다 본체 표 하나를 고른다(FINDINGS §1).

    같은 통화 표가 여럿이면(지배회사/종속회사) `[지배회사의 내용]` 표시 → 잔고 크기 →
    행 수 순으로 고른다. 금액이 아닌 표(MIXED·단위 미확인·수량 단위)는 `rejected` 로 뺀다."""
    by_cur, rejected = {}, []
    for o in orders:
        if not o.get("unit_seen"):
            rejected.append({"cur": o.get("cur"), "note": o.get("unit_note") or "단위 미확인",
                             "lead": o.get("lead", "")[-120:], "cols": o.get("cols")})
            continue
        by_cur.setdefault(o["cur"], []).append(o)
    picked = {}
    for cur, os_ in by_cur.items():
        def key(o):
            lead = o.get("lead") or ""
            mark = 1 if (_PARENT.search(lead) and not _SUB.search(lead)) else (-1 if _SUB.search(lead) else 0)
            # 겸업사는 같은 통화로 수주표를 여럿 싣는다 — 대한항공은 항공우주(`항공기체·
            # 군용기MRO·무인기`) 말고도 항공운수보조·지상조업·IT 표를 낸다. 크기로 고르면
            # 운송 표가 이긴다. **항공·우주 행이 있는 표를 먼저** 고른다.
            return (_aero_score(o) > 0, mark, o["shape"] != "balance",
                    _orders_total(o), len(o["rows"]))
        best = dict(max(os_, key=key))
        lead = best.get("lead") or ""
        best["scope"] = "parent" if _PARENT.search(lead) else ("sub" if _SUB.search(lead) else "unknown")
        best["n_tables"] = len(os_)
        picked[cur] = best
    return picked, rejected


# ══ 매출실적 ══════════════════════════════════════════════════════════════

_KIND_WORDS = {"수출": "수출", "해외": "수출", "국내": "내수", "내수": "내수", "합계": "합계",
               "계": "합계", "소계": "합계"}
_KIND_REAL = ("수출", "해외", "국내", "내수")
_CUST_COL = re.compile(r"매출처|거래처|고객|발주처|업체")
# 켄코아처럼 셀 안에 `$` 를 붙여 행마다 통화를 밝히는 표가 있다(FINDINGS §6).
_DOLLAR = re.compile(r"^\s*[\$＄]")


def parse_revenue_table(t):
    """내수/수출이 갈린 매출 표 → {basis, cur, rows}. `수출/내수`가 **셀 값으로** 오는 열을 찾는다."""
    cur, mul, seen, unit_note = table_currency(t)
    votes = {}
    for r in t["rows"]:
        for i, c in enumerate(r[:5]):
            if clean(c) in _KIND_REAL:
                votes[i] = votes.get(i, 0) + 1
    if not votes:
        return None
    i_kind = max(votes, key=lambda i: votes[i])
    rows = []
    for r in t["rows"]:
        if i_kind >= len(r):
            continue
        k = _KIND_WORDS.get(clean(r[i_kind]))
        if not k:
            continue
        labels = [c.strip() for c in r[:i_kind] if c.strip()]
        if not labels:
            labels = [c.strip() for c in r[i_kind + 1:i_kind + 2]
                      if c.strip() and num_of(c) is None]
        vals = [_scaled(v, mul) for v in r[i_kind + 1:]
                if num_of(v) is not None or v.strip() in ("", "-")]
        nums = [v for v in vals if v is not None]
        if not nums:
            continue
        seg = labels[0] if labels else ""
        rows.append({"seg": seg, "item": " ".join(labels[1:]), "kind": k,
                     "val": nums[0], "vals": vals,
                     "domain": domain_of(" ".join(labels)),
                     "tab": seg_tab(seg)})
    if not rows:
        return None
    if re.search(r"판매경로|판매방법|판매전략", " ".join(t["cols"])):
        return None
    head = " ".join(t["cols"][:max(1, i_kind + 1)])
    basis = "customer" if (_CUST_COL.search(head) or _CUST_COL.search((t.get("lead") or "")[-120:])) \
        else "segment"
    return {"basis": basis, "cur": cur, "unit_seen": seen, "unit_note": unit_note,
            "i_kind": i_kind, "rows": rows, "period_cols": t["cols"][i_kind + 1:],
            "cols": t["cols"], "lead": (t.get("lead") or "")[-220:]}


_SALES_LEAD = re.compile(r"매출\s*실적|매출에\s*관한\s*사항|부문별\s*매출|매출\s*현황|매출\s*구성")


def parse_segment_sales(t):
    """내수/수출이 없는 **매출실적** 표 → 부문별 금액. 켄코아처럼 행마다 통화가 다르면
    `$` 접두를 읽어 행 통화를 남기고, 갈리지 않으면 금액으로 싣지 않는다(FINDINGS §6)."""
    cols = [clean(c) for c in t["cols"]]
    lead = t.get("lead") or ""
    if not (_SALES_LEAD.search(lead) or any("매출" in c for c in cols)):
        return None
    if any(clean(c) in _KIND_REAL for r in t["rows"][:8] for c in r[:4]):
        return None
    if _CUST_COL.search(" ".join(cols[:2])):
        return None
    cur, mul, seen, unit_note = table_currency(t)
    i_amt = next((i for i, c in enumerate(cols)
                  if i >= 1 and "비중" not in c and "비율" not in c
                  and sum(1 for r in t["rows"] if i < len(r) and num_of(r[i]) is not None) >= 2), None)
    if i_amt is None:
        return None
    i_pct = next((i for i, c in enumerate(cols)
                  if i > i_amt and ("비중" in c or "비율" in c)), None)
    val_idx = [i for i in range(i_amt, len(cols)) if "비중" not in cols[i] and "비율" not in cols[i]]
    rows, dollar_rows = [], 0
    for r in t["rows"]:
        if i_amt >= len(r):
            continue
        raw = r[i_amt]
        if num_of(raw) is None:
            continue
        # 통화가 섞여 배수를 못 정한 표(mul=None)도 **행 이름은 남긴다** — 금액은 비우되
        # 품목 이름(`항공기 부품`·`우주항공원소재`)이 영역 판정과 부품 분류의 재료가 된다.
        v = _scaled(raw, mul)
        if v is None and mul is not None:
            continue
        is_usd = bool(_DOLLAR.search(raw))
        if is_usd:
            dollar_rows += 1
        labels = [c.strip() for c in r[:i_amt] if c.strip() and num_of(c) is None]
        seg = labels[0] if labels else ""
        if not seg:
            continue
        item = " ".join(dict.fromkeys(labels[1:]))
        rows.append({"seg": seg, "item": item, "val": v,
                     "total": is_total(seg) or is_total(item),
                     "row_cur": "USD" if is_usd else None,
                     "vals": [_scaled(r[i], mul) if i < len(r) else None for i in val_idx],
                     "pct": (num_of(r[i_pct]) if i_pct is not None and i_pct < len(r) else None),
                     "domain": domain_of(" ".join(labels)),
                     "tab": seg_tab(seg)})
    if not rows:
        return None
    if dollar_rows:
        seen = False
        unit_note = ("행마다 통화가 다름(`$` 붙은 행 %d개) — 금액으로 싣지 않음" % dollar_rows)
    return {"cur": cur, "unit_seen": seen, "unit_note": unit_note, "rows": rows,
            "cols": t["cols"], "period_cols": [t["cols"][i] for i in val_idx],
            "dollar_rows": dollar_rows, "lead": (t.get("lead") or "")[-220:]}


# ══ 매출처 ════════════════════════════════════════════════════════════════

_CUST_LEAD = re.compile(r"주요\s*거래처|주요\s*매출처|매출처\s*현황|주요\s*고객|매출처별|거래처별")
_CUST_BAD = re.compile(r"판매경로|판매방법|판매조직")
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
# 이름 칸에 오지만 **고객이 아닌** 말들. 매출처 표는 `매출처|구분|금액|비중` 처럼 구분 열이
# 함께 오고(방위사업청 등 | 내수 | 1,072,101), 품목 열이 앞에 오기도 한다(제품 | 국내 | P사).
# 이 말들을 지우고 남는 마지막 칸이 이름이다 — 그냥 첫 칸이나 끝 칸을 쓰면 `내수`가 고객이 된다.
_NOT_NAME = re.compile(r"^(내\s*수|수\s*출|국\s*내|해\s*외|제\s*품|상\s*품|용\s*역|기\s*타|"
                       r"합\s*계|소\s*계|총\s*계|총\s*매출액|매출액|매출처|거래처|고객|구\s*분|"
                       r"품\s*목|업\s*체|비\s*중|비\s*율|금\s*액|결제조건|[-—]|)$")
# 기간·단위 머리행이 본문 행으로 되풀이되는 표가 있다 — `2026년 반기(제28기)` 를 고객으로 싣지 않는다.
_PERIOD = re.compile(r"제\s*\d+\s*기|20\d\d\s*년|단위\s*:|기준일|분기|반기")
# 수주표를 매출처 표로 오인하지 않게 — 열 이름이 수주표면 여기서 손대지 않는다.
_ORDER_COLS = re.compile(r"수주총액|수주잔고|기납품|수주일자|납기")
# 익명 표기 — 공시가 이름을 가린 것이다. 지우지 말고 **익명이라 적는다**(COMMON §0-6).
_ANON_NAME = re.compile(r"^([A-Z]\s*사|고객\s*\d+|업체\s*\d+|[○ㅇ]{2,}|[A-Z]{1,2})$")


def customer_name(cells, heads):
    """매출처 표의 한 행 → (이름, 익명여부) 또는 (None, False).

    이름은 **첫 숫자 칸 앞**에 있다(`국내 | 한국항공 | 13,842 | … | 현금`). 뒤까지 보면
    결제조건 칸의 `현금`이 고객이 된다(실측). 그 앞 칸들에서 머리행·구분어(내수/수출/제품…)·
    기간 문구를 지우고 **남는 마지막 칸**을 이름으로 본다."""
    head_cells = []
    for c in cells:
        if num_of(c) is not None:
            break
        head_cells.append(c)
    names = []
    for c in (head_cells or cells):
        c = (c or "").strip()
        if not c or num_of(c) is not None:
            continue
        if clean(c) in heads or _NOT_NAME.match(clean(c)) or _PERIOD.search(c):
            continue
        if is_total(c):
            continue
        names.append(c)
    if not names:
        return None, False
    # 각주 표시(`ACM(주1)`)는 이름이 아니다 — 떼고 싣는다(각주 본문은 본문 문구로 따로 읽힌다).
    name = re.sub(r"\s*\(\s*주\s*\d+\s*\)\s*$", "", names[-1]).strip()
    if not name:
        return None, False
    return name, bool(_ANON_NAME.match(clean(name)))


def parse_customers(t):
    """매출처 표 → 이름·금액·비중. 이 산업에서 **고객 축의 1급 근거**다(FINDINGS §2).

    케이피항공산업처럼 수주표가 없는 회사도 이 표는 있다. 하이즈항공은 국내/수출 구분 열이
    앞에 오고 각주에 `BOE(Boeing Commercial Airplanes)` 로 약칭을 풀어 둔다."""
    lead = t.get("lead") or ""
    good = max((m.end() for m in _CUST_LEAD.finditer(lead)), default=-1)
    bad = max((m.end() for m in _CUST_BAD.finditer(lead)), default=-1)
    if good < 0 and any(_CUST_LEAD.search(c or "") for c in t["cols"]):
        good = 0
    if good < 0 or bad > good:
        return None
    if _ORDER_COLS.search(" ".join(t["cols"])):
        return None            # 수주표다 — 매출처 표가 아니다(이노스페이스 실측)
    cur, mul, seen, _ = table_currency(t)
    heads = {clean(c) for c in t["cols"]}
    out = []
    for r in t["rows"]:
        cells = [c.strip() for c in r if c and c.strip()]
        if len(cells) < 2:
            continue
        name, anon = customer_name(cells, heads)
        if not name:
            continue
        kind = next((clean(c) for c in cells if clean(c) in ("국내", "수출", "내수", "해외")), "")
        share = None
        for c in cells[1:]:
            m = _PCT.search(c)
            if m:
                share = float(m.group(1))
                break
        amt = next((_scaled(c, mul) for c in cells if num_of(c) is not None), None)
        out.append({"name": name, "anon": anon, "kind": _KIND_WORDS.get(kind, ""),
                    "amount": amt if seen else None, "share_pct": share,
                    "customers": ([] if anon else customers_in(name)), "raw": cells[:4]})
    return {"cur": cur, "unit_seen": seen, "rows": out, "lead": lead[-200:],
            "cols": t["cols"]} if out else None


# ══ 수집 ══════════════════════════════════════════════════════════════════

def _keep(t):
    blob = " ".join(t["cols"]) + " " + (t.get("lead") or "")[-220:]
    return bool(re.search(r"수주|매출|거래처|매출처|고객|납기|잔고|잔액", blob))


def _tables_of(node):
    return _headered(_carry_units(parse_tables(fetch_section(node))))


def collect_one(rec, quarter, force=False, log=sys.stderr):
    st = rec["stock"]
    path = os.path.join(CACHE, st, quarter + ".json")
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    out = {"stock": st, "name": rec.get("name", ""), "quarter": quarter, "ok": False, "note": ""}
    try:
        rcp, title, found, tried = open_sections(st, quarter, SECTIONS, "sales")
    except Exception as e:
        out["note"] = "검색 실패: %s" % e
        return out
    if not rcp:
        out["note"] = ("매출·수주 절 없음" if tried else "정기보고서 없음")
        out["tried"] = [{"rcp": r, "title": t, "why": w} for r, t, w in tried]
        return out
    out["rcp"], out["title"] = rcp, title
    out["tried"] = [{"rcp": r, "title": t, "why": w} for r, t, w in tried]
    section_html = fetch_section(found["sales"])
    tables = _headered(_carry_units(parse_tables(section_html)))
    parsed = [(t, parse_orders_table(t)) for t in tables]
    orders = [o for _, o in parsed if o]
    rest = [t for t, o in parsed if not o]
    # 상세표 — 계약 원장. 본문 수주표가 `상세내역 참조`로 갈음할 때 여기 진짜가 있다.
    detail = []
    if "orders_detail" in found:
        try:
            dts = _tables_of(found["orders_detail"])
            detail = [o for o in (parse_orders_table(t) for t in dts) if o]
        except Exception as e:
            out["detail_note"] = "상세표 읽기 실패: %s" % e
    revenue = [x for x in (parse_revenue_table(t) for t in rest) if x]
    segsales = [x for x in (parse_segment_sales(t) for t in rest) if x]
    customers = [x for x in (parse_customers(t) for t in tables) if x]

    picked, rejected = group_orders(orders)
    dpicked, drejected = group_orders(detail)
    out["orders"] = picked
    out["orders_rejected"] = rejected
    out["orders_detail"] = dpicked
    out["orders_detail_rejected"] = drejected
    out["n_order_tables"] = len(orders)
    seg_rev = [r for r in revenue if r["basis"] == "segment"]
    out["revenue"] = max(seg_rev or revenue, key=lambda r: len(r["rows"])) if revenue else None
    out["revenue_all"] = revenue or []
    out["segment_sales"] = max(segsales, key=lambda r: len(r["rows"])) if segsales else None
    out["customers"] = max(customers, key=lambda c: len(c["rows"])) if customers else None
    out["customers_all"] = customers or []
    out["raw_tables"] = [{"cols": t["cols"], "rows": t["rows"], "lead": (t.get("lead") or "")[-220:]}
                         for t in tables if _keep(t)]
    txt = text_of(section_html)
    out["security_note"] = bool(_SECURITY.search(txt))
    # 본문 문구 근거 — RSP·LTA·OEM 실명(FINDINGS §3). 인용을 그대로 남긴다.
    out["quotes"] = _quotes(txt)
    out["text_customers"] = customers_in(txt)
    out["ok"] = bool(picked or dpicked or out["revenue"] or out["segment_sales"] or out["customers"])
    if not out["ok"]:
        out["note"] = "수주·매출·매출처 표 인식 실패 — 머리행 %s" % [t["cols"] for t in tables][:3]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write(path, json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    log.write("%s %s %s cur=%s%s\n"
              % (st, quarter, "ok" if out["ok"] else "FAIL", ",".join(sorted(picked)) or "-",
                 (" detail=%s" % ",".join(sorted(dpicked))) if dpicked else ""))
    log.flush()
    return out


_QUOTE_PAT = [("RSP", _N_RSP), ("LTA", _N_LTA), ("PBL", _N_PBL)]


def _quotes(txt):
    """본문에서 RSP·장기공급·PBL 문구를 한 토막씩 인용한다(근거 등급 B)."""
    out = []
    s = re.sub(r"\s+", " ", txt)
    for key, pat in _QUOTE_PAT:
        m = pat.search(s)
        if m:
            out.append({"key": key, "text": s[max(0, m.start() - 90):m.start() + 150].strip()})
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
    for rec in rows:
        for q in qs:
            try:
                collect_one(rec, q, force)
            except Exception as e:
                sys.stderr.write("[warn] %s %s %s\n" % (rec["stock"], q, e))


# ══ 집계 ══════════════════════════════════════════════════════════════════

def _sum(rows, field, pred=None):
    vals = [r[field] for r in rows
            if not r["total"] and r.get(field) is not None and (pred is None or pred(r))]
    return sum(vals) if vals else None


def _closing(o, pred=None):
    """표의 잔고 합. 합계 행이 있으면 그것을(필터가 없을 때만), 없으면 낱 행을 더한다."""
    rows = o["rows"]
    if pred is None:
        tot = [r for r in rows if r["total"]]
        if tot and tot[0].get("closing") is not None:
            return tot[0]["closing"]
    return _sum(rows, "closing", pred)


_FY_COL = re.compile(r"20\d\d년|제\d+기")
_PART_YEAR = re.compile(r"반기|분기|누적|개월|기중|비중|비율")


def _is_fy(col):
    c = clean(col)
    return bool(_FY_COL.search(c)) and not _PART_YEAR.search(c)


def _last_total_group(rows):
    """합계 행이 **여러 벌** 오는 표에서 마지막 한 벌만 남긴다.

    아스트 매출실적은 `합 계`(단순합) · `내부제거`(음수) · `총합계`(연결) 세 벌을 싣는다.
    `is_total` 은 셋 다 합계로 읽으므로 그대로 더하면 매출이 정확히 두 배가 된다(실측:
    5,099억 ← 실제 2,544억). 표에 **나중에 나오는 벌**이 연결 기준이므로 그것만 쓴다."""
    segs = [clean(r["seg"]) for r in rows]
    if not segs:
        return rows
    last = segs[-1]
    return [r for r in rows if clean(r["seg"]) == last]


def _fy_revenue(rv, tab=None):
    """매출 표에서 **온전한 1년** 열 → (값, 열 이름). 반기 누계를 두 배로 늘리지 않는다.

    `tab` 을 주면 그 탭 몫의 부문 행만 더한다 — 겸업사의 커버리지 분모를 만들 때 쓴다
    (한화에어로 항공 잔고를 **전사 매출**로 나누면 14년이 1.2년으로 줄어든다)."""
    if not rv or not rv.get("unit_seen"):
        return None, None
    cols = rv.get("period_cols") or []
    rows = [r for r in (rv.get("rows") or []) if tab is None or r.get("tab") == tab]

    def ok(r):
        return len(r.get("vals") or []) == len(cols)
    for i in (i for i, c in enumerate(cols) if _is_fy(c)):
        grand = _last_total_group([r for r in rows
                                   if r["kind"] == "합계" and is_total(r["seg"]) and ok(r)])
        per_seg = [r for r in rows if r["kind"] == "합계" and not is_total(r["seg"]) and ok(r)]
        use = grand or per_seg or [r for r in rows if r["kind"] in ("내수", "수출") and ok(r)]
        vals = [r["vals"][i] for r in use if r["vals"][i] is not None]
        if vals:
            return sum(vals), cols[i]
    return None, None


def _fy_segsales(ss, tab=None):
    if not ss or not ss.get("unit_seen"):
        return None, None
    cols = ss.get("period_cols") or []
    rows = [r for r in (ss.get("rows") or []) if len(r.get("vals") or []) == len(cols)
            and (tab is None or r.get("tab") == tab)]
    for i in (i for i, c in enumerate(cols) if _is_fy(c)):
        grand = _last_total_group([r for r in rows if is_total(r["seg"])])
        sub = [r for r in rows if r.get("total") and not is_total(r["seg"])]
        base = [r for r in rows if not r.get("total")]
        for use in (grand, sub, base):
            vals = [r["vals"][i] for r in use if r["vals"][i] is not None]
            if vals:
                return sum(vals), cols[i]
    return None, None


def _sum_rev_kind(rrows, kind):
    """내수·수출 합. 합계 행이 있으면 **그 행만** 쓴다 — 낱 품목과 함께 더하면 두 배가 된다."""
    tot = _last_total_group([r for r in rrows if r["kind"] == kind and is_total(r["seg"])])
    use = tot or [r for r in rrows if r["kind"] == kind and not is_total(r["seg"])]
    vals = [(r["vals"] or [None])[0] for r in use]
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def _aero_rows(o):
    """이 탭에 실을 행 — 부문이 kaero 이거나 판정이 안 되는 행(부문 열이 없는 회사).

    **부문 열이 있는데 kship·kdef 로 판정된 행은 뺀다**(FINDINGS §4 중복 계상)."""
    has_tab = any(r.get("tab") for r in o["rows"] if not r["total"])
    if not has_tab:
        return None            # 부문 구분이 없는 회사 — 전체가 이 탭 것이다
    return lambda r: r.get("tab") in (None, "kaero")


def build(rows, qs):
    """캐시 → reports.json. 회사 × 분기의 **통화별** 잔고·영역 구성·고객·커버리지."""
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
            per_q[q] = _build_quarter(d)
        if per_q:
            out[st] = {"stock": st, "name": rec.get("name", ""), "role": rec.get("role"),
                       "market": rec.get("market", ""), "quarters": per_q}
    write_asset("reports.json", {"n": len(out), "quarters": qs, "companies": out})
    return out


def _build_quarter(d):
    # 계약 원장이 있으면(상세표) 그것을 1순위로 — 본문 요약표는 품목이 `상세내역 참조`다.
    detail = d.get("orders_detail") or {}
    summary = d.get("orders") or {}
    src = "detail" if detail else "summary"
    orders = detail or summary
    backlog, backlog_all, dup, domains, natures, custs = {}, {}, [], {}, {}, {}
    dup_ix = {}
    shapes, scopes, notes = {}, {}, []
    for cur, o in sorted(orders.items()):
        pred = _aero_rows(o)
        backlog[cur] = _closing(o, pred)
        backlog_all[cur] = _closing(o)
        shapes[cur] = o["shape"]
        scopes[cur] = o.get("scope")
        if o.get("security_note"):
            notes.append("%s 표에 보안·영업비밀로 상세를 생략한다는 문구가 있다" % cur)
        for r in o["rows"]:
            if r["total"]:
                continue
            if r.get("tab") in ("kship", "kdef", "other") and r.get("closing") is not None:
                # 계약 한 줄씩이 아니라 **부문 단위로** 모은다 — 화면에는 "어느 탭 몫이
                # 얼마나 빠졌는가"만 있으면 된다(한화에어로는 32행이 세 부문에 걸린다).
                k = (r["tab"], r["seg"], cur)
                hit = dup_ix.get(k)
                if not hit:
                    hit = {"tab": r["tab"], "seg": r["seg"], "cur": cur, "closing": 0, "n": 0}
                    dup_ix[k] = hit
                    dup.append(hit)
                hit["closing"] += r["closing"]
                hit["n"] += 1
                continue
            if pred and not pred(r):
                continue
            v = r.get("closing")
            if v is None:
                continue
            domains.setdefault(r["domain"], {}).setdefault(cur, 0)
            domains[r["domain"]][cur] += v
            natures.setdefault(r["nature"], {}).setdefault(cur, 0)
            natures[r["nature"]][cur] += v
            for c in r.get("customers") or []:
                k = c["name"]
                custs.setdefault(k, {"name": k, "tier": c["tier"], "grade": c["grade"],
                                     "backlog": {}, "src": "수주표"})
                custs[k]["backlog"].setdefault(cur, 0)
                custs[k]["backlog"][cur] += v
    for rej in (d.get("orders_rejected") or []):
        notes.append(rej.get("note") or "수주표 하나를 금액으로 싣지 못함")

    rv = d.get("revenue") or {}
    rrows = rv.get("rows") or []
    ss = d.get("segment_sales") or {}
    srows = [r for r in (ss.get("rows") or []) if not r["total"]]
    fy, fy_col = _fy_revenue(rv)
    if fy is None:
        fy, fy_col = _fy_segsales(ss)
    rev_cur = rv.get("cur") if rv.get("unit_seen") else (ss.get("cur") if ss.get("unit_seen") else None)
    if ss.get("unit_note") and not ss.get("unit_seen"):
        notes.append(ss["unit_note"])

    # 영역 — 수주표 품목이 영역을 말하지 않는 회사가 있다. 아스트 수주표의 품목 열은
    # **고객 이름**(SPIRIT·EMBRAER)이라 영역이 전부 `other` 가 된다(FINDINGS §2).
    # 그럴 때만 매출실적 품목(`Section48`·`Bulkhead`·`Fuselage`)에서 영역을 읽고
    # 출처를 `매출품목`으로 남긴다 — 잔고 구성이 아니라 **매출 구성**이라는 뜻이다.
    dom_src = "수주표"
    if not domains or set(domains) == {"other"}:
        rev_dom = {}
        for r in (rrows or srows):
            if is_total(r.get("seg") or "") or r.get("val") is None:
                continue
            if r.get("kind") == "합계":
                continue
            rev_dom.setdefault(r["domain"], 0)
            rev_dom[r["domain"]] += r["val"]
        if rev_dom and set(rev_dom) != {"other"}:
            cur0 = rev_cur or "KRW"
            domains = {k: {cur0: v} for k, v in rev_dom.items()}
            dom_src = "매출품목"

    # 매출처 — 이 산업의 고객 축. 수주표에서 읽은 것과 합친다(출처를 각각 남긴다).
    # 이름 판정은 **빌드 때 캐시에서 다시** 한다 — 사전·규칙이 자라도 재수집이 필요 없게
    # 원문 셀(`raw`)을 남겨 뒀다(COMMON §0-4). 옛 캐시의 잘못 잡힌 이름(`내수`·`비중`)도
    # 여기서 걸러진다.
    cust_rows = []
    ct = d.get("customers") or {}
    if ct and not _ORDER_COLS.search(" ".join(ct.get("cols") or [])):
        heads = {clean(c) for c in (ct.get("cols") or [])}
        for c in ct.get("rows") or []:
            raw = c.get("raw") or [c.get("name") or ""]
            name, anon = customer_name(raw, heads)
            if not name:
                continue
            cust_rows.append({"name": name, "anon": anon, "kind": c.get("kind", ""),
                              "amount": c.get("amount"), "share_pct": c.get("share_pct"),
                              "matched": ([] if anon else customers_in(name)), "src": "매출처표"})
    # 커버리지(년) — 잔고 ÷ 연매출. **통화가 같을 때만** 만든다(환산 금지).
    # ── 커버리지(년) = 잔고 ÷ 연매출 ─────────────────────────────────────
    # 분자와 분모의 **범위가 같아야** 한다. 겸업사는 잔고를 항공·우주 부문으로 걸렀으므로
    # 분모도 그 부문 매출이어야 한다 — 한화에어로 항공 잔고 32.3조를 전사 매출 26.7조로
    # 나누면 1.2년이지만, 항공 부문 매출 2.3조로 나누면 14년이다(이쪽이 맞는 값이다).
    cover, cover_note = None, ""
    cover_fy, cover_fy_col, cover_scope = fy, fy_col, "전사"
    # 범위가 어긋나는 두 경우: ① 부문 필터로 행을 뺐다 ② 같은 통화 표가 여럿인데 그중
    # 항공·우주 표 하나만 골랐다(대한항공 — 항공운수보조·지상조업·IT 표가 따로 있다).
    partial = bool(dup) or any((o.get("n_tables") or 1) > 1 for o in orders.values())
    if partial:
        a_fy, a_col = _fy_revenue(rv, tab="kaero")
        if a_fy is None:
            a_fy, a_col = _fy_segsales(ss, tab="kaero")
        if a_fy:
            cover_fy, cover_fy_col, cover_scope = a_fy, a_col, "항공·우주 부문"
        else:
            cover_fy, cover_fy_col, cover_scope = None, None, "부문 매출 못 읽음"
            cover_note = ("수주잔고는 항공·우주 부문만 실었는데 그에 맞는 부문 매출을 못 읽어 "
                          "커버리지를 만들지 않았다 — 전사 매출로 나누면 범위가 어긋난다")
    if cover_fy and rev_cur and rev_cur in backlog and backlog[rev_cur]:
        cover = backlog[rev_cur] / cover_fy
        other = {c: v for c, v in backlog.items() if c != rev_cur and v}
        if other:
            # 아스트가 그렇다 — 잔고는 27억달러인데 매출표는 원화뿐이다. 원화 잔고만으로
            # 낸 커버리지는 0.001년이 되어 **뜻이 없다**. 값을 만들지 않고 사실을 적는다.
            cover = None
            cover_note = ("수주잔고가 %s 로도 있는데 매출표는 %s 뿐이다 — 환산하지 않으므로 "
                          "커버리지를 만들지 않았다(%s 잔고만으로 내면 뜻이 없다)"
                          % ("·".join(sorted(other)), rev_cur, rev_cur))
    elif cover_fy and backlog and rev_cur:
        cover_note = cover_note or (
            "매출 통화(%s)와 같은 통화의 수주잔고가 없어 커버리지를 만들지 않았다" % rev_cur)
    return {
        "ok": True, "rcp": d.get("rcp"), "title": d.get("title"),
        "orders_src": src, "shapes": shapes, "scopes": scopes,
        "backlog": backlog, "backlog_all": backlog_all,
        # 롤포워드의 기초·총액·기납품도 **잔고와 같은 필터**를 쓴다 — 안 그러면 한화에어로가
        # 수주총액 162조(전 부문)에 잔고 32조(항공만)로 찍혀 표가 말이 안 된다.
        "opening": {c: _closing_field(o, "opening", _aero_rows(o)) for c, o in orders.items()},
        "delivered": {c: _closing_field(o, "delivered", _aero_rows(o)) for c, o in orders.items()},
        "gross": {c: _closing_field(o, "gross", _aero_rows(o)) for c, o in orders.items()},
        "dup_segments": dup,
        "domains": domains, "domains_src": dom_src, "natures": natures,
        "order_customers": sorted(custs.values(), key=lambda c: -sum(c["backlog"].values())),
        "contracts": _contract_rows(orders),
        "revenue_cur": rev_cur, "revenue_fy": fy, "revenue_fy_col": fy_col,
        "revenue_basis": rv.get("basis"),
        "revenue_domestic": _sum_rev_kind(rrows, "내수"),
        "revenue_export": _sum_rev_kind(rrows, "수출"),
        "revenue_segments": [{"seg": r["seg"], "item": r["item"], "kind": r["kind"],
                              "domain": r["domain"], "tab": r["tab"], "val": r["val"]}
                             for r in rrows],
        "sales_segments": [{"seg": r["seg"], "item": r["item"], "domain": r["domain"],
                            "tab": r["tab"], "val": r["val"], "pct": r.get("pct"),
                            "row_cur": r.get("row_cur")} for r in srows],
        "customers": cust_rows,
        "text_customers": d.get("text_customers") or [],
        "quotes": d.get("quotes") or [],
        "coverage_years": cover, "coverage_note": cover_note,
        "coverage_fy": cover_fy, "coverage_fy_col": cover_fy_col, "coverage_scope": cover_scope,
        # 부문 잔고 ÷ 부문 매출은 **추정**이다 — 수주표의 부문 구분과 매출표의 부문 구분이
        # 정확히 같지 않다(KAI 수주표는 `국내방산|완제기수출|기체부품`, 매출표는
        # `방산 및 완제기수출|기체부품 및 민수`). 화면에 '추정'이라 적는다.
        "coverage_est": cover_scope != "전사",
        "security_note": d.get("security_note", False),
        "notes": notes,
    }


def _closing_field(o, field, pred=None):
    """합계 행이 있으면 그것을(필터가 없을 때만), 없으면 낱 행을 더한다."""
    if pred is None:
        tot = [r for r in o["rows"] if r["total"]]
        if tot and tot[0].get(field) is not None:
            return tot[0][field]
    return _sum(o["rows"], field, pred)


def _contract_rows(orders, aero_only=True):
    """계약 원장 — `item` 모양 표의 낱 행(수주일자·납기가 있는 행)만.

    이 산업의 화면 뼈대다(아스트 8건·한화에어로 수십 건). 수량은 싣지 않는다(스펙 ⑥).
    `aero_only` 면 부문이 kship·kdef 로 판정된 행은 뺀다 — 잔고 집계와 **같은 필터**를
    써야 화면의 합이 맞는다(한화에어로 해양 26.7조가 계약 원장에만 남으면 안 된다)."""
    out = []
    for cur, o in sorted(orders.items()):
        if o["shape"] != "item":
            continue
        for r in o["rows"]:
            if r["total"] or r.get("closing") is None:
                continue
            if aero_only and r.get("tab") in ("kship", "kdef", "other"):
                continue
            out.append({"cur": cur, "label": r["label"], "seg": r["seg"],
                        "domain": r["domain"], "nature": r["nature"], "tab": r.get("tab"),
                        "order_date": r["order_date"], "due": r["due"],
                        "order_year": r.get("order_year"), "due_year": r.get("due_year"),
                        "gross": r.get("gross"), "delivered": r.get("delivered"),
                        "closing": r["closing"],
                        "customers": r.get("customers") or []})
    out.sort(key=lambda r: -(r["closing"] or 0))
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
        ok = sum(1 for c in res.values() for q in c["quarters"].values() if q.get("ok"))
        print("회사 %d · 분기레코드 %d" % (len(res), ok))
        for st, c in res.items():
            last = [q for q in qs if q in c["quarters"] and c["quarters"][q].get("ok")]
            if not last:
                continue
            v = c["quarters"][last[-1]]
            bl = " ".join("%s=%s" % (k, format(int(x), ",d")) for k, x in
                          sorted((v["backlog"] or {}).items()) if x is not None) or "—"
            print("  %s %-16s %s 잔고 %s | 영역 %s | 계약 %d | 중복 %d"
                  % (st, c["name"][:16], last[-1], bl, ",".join(sorted(v["domains"])) or "-",
                     len(v["contracts"]), len(v["dup_segments"])))


if __name__ == "__main__":
    sys.exit(main())
