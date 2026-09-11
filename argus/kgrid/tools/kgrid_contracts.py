#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kgrid_contracts — 계약 단위 원장을 수시공시 「단일판매ㆍ공급계약체결」(I001)에서 만든다.

**왜 필요한가.** 이 산업의 정기보고서 수주표는 한 행이 계약이 아니라 사업부문 합계다
(FINDINGS §2: 엘에스일렉트릭 T&D 1행이 잔고의 98.4%, HD현대일렉트릭은 부문 1행).
누가 발주했는지·무엇을 파는지·얼마나 긴 계약인지는 **이 공시에만** 있다.

원문에서 확인한 이 산업 고유의 세 가지(코드를 쓰기 전에 원문 4건을 직접 열어 봤다):

1. **양식이 둘이다.** 유가증권은 「1. 판매ㆍ공급계약 구분」 + 「- 체결계약명」,
   코스닥은 「1. 판매ㆍ공급계약 내용」이 계약명 자리다(제룡전기 033100/20251222900254).
   코스닥 양식은 금액 라벨도 `확정 계약금액`·`계약금액 총액(원)`으로 다르다.
   한쪽만 보면 계약명이 통째로 빈칸이 된다 — kdef_contracts 가 겪은 것과 같다.

2. **금액 칸은 언제나 원화다. 원통화는 주석에 있다.** 전력기기는 수출계약이 많아
   공시 본문이 이렇게 적는다(실측):
     · 산일전기 20260820800341 「상기 계약 금액은 USD 36,284,748 이며, … 매매기준율 \\1,411.00/USD」
     · HD현대일렉트릭 20260507800238 「계약액 USD 117,639,663를 원화환산하여 기재하였음」
     · 제룡전기 20251222900254 「상기 계약금액은 USD29,852,335.45이며 … 1USD=1,477.80원」
   그래서 `계약금액(원)`만 저장하면 통화를 잃는다. 주석에서 외화 금액을 뽑아 `amt`·`cur` 로
   같이 남긴다(환산은 우리가 하지 않는다 — 회사가 적은 원화값을 `amt_krw_m` 으로 따로 둔다).
   **오독 방어**: 같은 주석에 `1 USD = 1,470.50원` 같은 환율이 함께 있어 `USD` 뒤 숫자를
   그냥 잡으면 `1,470.50`을 금액으로 읽는다. 그래서 후보를 모두 모은 뒤
   **내재환율(원화금액÷외화금액)이 그 통화의 상식 범위에 드는 것만** 인정한다(fail-closed).

3. **계약상대가 전력회사 실명이다.** 정기보고서 매출처 표와 같은 축(FINDINGS §3)이
   계약 단위로도 선다 — `Public Service Electric and Gas Company`(북미 유틸리티),
   `한국수력원자력 주식회사`(국내 공기업). 다만 **관계회사를 거친 재발주**가 흔하다
   (HD현대일렉트릭 → `HD Hyundai Electric America Corporation`, 회사와의 관계 `자회사`).
   이때 최종 수요처는 주석에만 있다(「미국 MISO·SPP 권역의 765kV급 송전망 기반 대형 유틸리티」).
   그래서 수요처 판정은 계약상대 → (관계사면) 주석 → 공급지역 순으로 본다.

캐시: `assets/contracts/<종목코드>.json` — 공시별 원문 (라벨,값) 전부 보존(`kv`).
분류는 **빌드 때 캐시에서 다시** 한다(사전이 자라도 재수집이 필요 없게, COMMON §0-4).

    python3 kgrid_contracts.py --collect [--only 267260] [--years 3]
    python3 kgrid_contracts.py --build
"""
import argparse
import json
import os
import re
import sys
import time

from kgrid_lib import (ASSETS, DEMAND_ORDER, PRODUCT_ORDER, atomic_write, fetch_section,
                       load_asset, num_of, parse_tables, search_reports, toc, write_asset)
import kgrid_universe

CACHE = os.path.join(ASSETS, "contracts")

# ── 제목 판정 ───────────────────────────────────────────────
# 가운뎃점이 `ㆍ`(U+318D)·`·`(U+00B7)·공백으로 흔들린다 — 낱말만 본다(scout_contracts 와 같은 규칙).
_SUPPLY = re.compile(r"단일\s*판매.{0,3}공급\s*계약|공급계약\s*체결")
_FIX = re.compile(r"\[기재정정\]|\[첨부정정\]|정정신고|\[정정\]")
_CANCEL = re.compile(r"해지|해제|취소")


# ── 계약금액의 통화 ─────────────────────────────────────────
# 통화 토큰 → (코드, 내재환율 상식 범위). 범위는 "원화금액 ÷ 외화금액" 이 이 안에 들어야
# 그 숫자를 계약금액으로 인정한다는 뜻이다. 넓게 잡되 환율 숫자 자체(1,400 등)와는
# 겹치지 않을 만큼만 넓힌다.
_CUR_BANDS = {
    "USD": (700.0, 2200.0),
    "EUR": (900.0, 2600.0),
    "JPY": (5.0, 20.0),
    "CNY": (100.0, 300.0),
    "GBP": (1100.0, 3000.0),
    "SAR": (180.0, 600.0),
    "AED": (180.0, 600.0),
    "INR": (8.0, 40.0),
    "AUD": (500.0, 1500.0),
    "CAD": (500.0, 1600.0),
    "SGD": (600.0, 1600.0),
}
# 원문 표기 방언. `미화`·`달러`·`유로`·`엔` 같은 한국어 표기도 실제로 쓰인다.
_CUR_ALIAS = [
    (r"US\s*\$|USD|미화|미\s*달러|달러|불", "USD"),
    (r"EUR|€|유로", "EUR"),
    (r"JPY|엔화|일본\s*엔", "JPY"),
    (r"CNY|RMB|위안", "CNY"),
    (r"GBP|파운드", "GBP"),
    (r"SAR|리얄|리알", "SAR"),
    (r"AED|디르함", "AED"),
    (r"INR|루피", "INR"),
    (r"AUD|호주\s*달러", "AUD"),
    (r"CAD|캐나다\s*달러", "CAD"),
    (r"SGD|싱가포르\s*달러", "SGD"),
]
_NUM = r"\d[\d,]*(?:\.\d+)?"
# 통화가 앞에 오는 꼴(`USD 36,284,748`, `USD29,852,335.45`)과 뒤에 오는 꼴(`36,284,748 달러`)
_CUR_BEFORE = [(re.compile(r"(?:%s)\s*(%s)" % (pat, _NUM), re.I), code) for pat, code in _CUR_ALIAS]
_CUR_AFTER = [(re.compile(r"(%s)\s*(?:%s)" % (_NUM, pat), re.I), code) for pat, code in _CUR_ALIAS]


def _n(s):
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


def currency_amount(note, amt_krw):
    """주석 문구 + 원화 계약금액 → (외화금액, 통화, 내재환율, 근거문구). 못 읽으면 (None,…).

    회사가 스스로 원화로 환산해 적었으므로 **내재환율이 상식 범위에 드는 후보만** 금액으로 본다.
    이 검증이 없으면 같은 문장에 있는 적용환율(`1 USD = 1,470.50원`)을 금액으로 읽는다(실측).
    """
    if not note or not amt_krw:
        return None, None, None, ""
    best = None
    for rxs in (_CUR_BEFORE, _CUR_AFTER):
        for rx, code in rxs:
            band = _CUR_BANDS.get(code)
            for m in rx.finditer(note):
                v = _n(m.group(1))
                if not v or v <= 0:
                    continue
                rate = amt_krw / v
                if not (band[0] <= rate <= band[1]):
                    continue
                # 상식 범위를 통과한 후보가 여럿이면 **가장 큰 금액**을 쓴다(부분금액·수량이
                # 함께 적힌 주석이 있다). 환율 숫자는 애초에 범위를 통과하지 못한다.
                snip = note[max(0, m.start() - 24):m.end() + 12]
                if best is None or v > best[0]:
                    best = (v, code, rate, snip)
    if best is None:
        return None, None, None, ""
    v, code, rate, snip = best
    return v, code, round(rate, 2), re.sub(r"\s+", " ", snip).strip()


# ── 수요처(발주처) 분류 ─────────────────────────────────────
# **수집한 계약상대 문구를 실제로 세어 보고** 만든 어휘다(FINDINGS §7에 분포를 적었다).
# 상상해서 넣은 낱말은 없다. 판정 못 하면 None — 추측하지 않는다(COMMON §0-1).
#
# 순서가 뜻을 가진다: 데이터센터·신재생은 발주처의 **용도**라 유틸리티 이름보다 먼저 본다.
_DEMAND_RULES = [
    # 데이터센터 — 계약명·주석에 낱말이 그대로 나온다(스펙 §5, FINDINGS §4).
    ("datacenter", r"데이터\s*센터|데이터센타|IDC\b|하이퍼스케일|Data\s*Cent(?:er|re)|"
                   r"아마존|Amazon|AWS\b|마이크로소프트|Microsoft|구글|Google|메타플랫폼|Meta\s*Platform"),
    # 신재생 연계 — 태양광·풍력 발전단지, PCS·ESS 계통연계.
    ("renewable", r"태양광|풍력|해상풍력|신재생|재생에너지|발전단지|Solar|Wind\s*(?:Farm|Power)|"
                  r"NextEra|넥스트에라|에너지저장|ESS\s*(?:연계|사업)|수소연료전지|연료전지"),
    # 국내 한전·공기업 — 발주처다(모집단에서는 제외했지만 계약상대로는 자주 나온다).
    # 발전 공기업(남동·남부·동서·서부·중부발전)은 한전 자회사다 — **신재생이 아니다**.
    # 하동 화력 7,8호기 고압차단기(선도전기 20260310800257)가 신재생으로 가던 것을 여기서 막았다.
    ("kepco", r"한국전력공사|한전\s*KDN|한전KPS|한국전력|KEPCO|한국수력원자력|한수원|"
              r"한국남동발전|한국남부발전|한국동서발전|한국서부발전|한국중부발전|발전\s*공기업|"
              r"한국가스공사|한국철도공사|국가철도공단|한국도로공사|한국토지주택공사|LH공사|"
              r"서울교통공사|부산교통공사|인천교통공사|한국공항공사|인천국제공항공사|"
              r"조달청|국방부|방위사업청"),
    # 중동 전력청 — 사우디 SEC·아람코, UAE·쿠웨이트·카타르 전력수전청.
    ("me_utility", r"사우디\s*전력청|Saudi\s*Electric|SEC\b|아람코|Aramco|"
                   r"두바이\s*수전력청|DEWA|아부다비|ADNOC|TRANSCO|EWEC|ADDC|AADC|"
                   r"쿠웨이트|Kuwait|카타르|Qatar|오만|Oman|바레인|Bahrain|"
                   r"이라크|Iraq|요르단|Jordan|이집트|Egypt|사우디|Saudi|UAE|Emirates"),
    # 북미 유틸리티 — 실명 전력회사와 미국/캐나다 공급지역.
    ("na_utility", r"Electric\s*(?:and|&)\s*Gas|Public\s*Service\s*Electric|PSE&G|"
                   r"Power\s*(?:and|&)\s*Light|Energy\s*Corp|Electric\s*Power|Utilit|"
                   r"Xcel|Dominion|Duke\s*Energy|Southern\s*Company|Entergy|Exelon|"
                   r"American\s*Electric|Consolidated\s*Edison|Con\s*Edison|PG&E|"
                   r"Pacific\s*Gas|Georgia\s*Power|Florida\s*Power|Oncor|CenterPoint|"
                   r"Hydro[\s-]?(?:One|Qu)|BC\s*Hydro|TVA\b|MISO|SPP\b|ERCOT|PJM\b|"
                   r"전력청|전력회사|유틸리티"),
    # 산업 플랜트 — 제철·석유화학·조선·반도체 공장, EPC.
    ("industrial", r"제철|포스코|현대제철|석유화학|정유|화학\s*플랜트|플랜트|정제|LNG|"
                   r"조선소|중공업|엔지니어링|건설|E&C|EPC|반도체\s*(?:공장|라인)|"
                   r"삼성전자|SK하이닉스|삼성물산|현대건설|대우건설|GS건설|DL이앤씨|"
                   r"현대엔지니어링|삼성E&A|SK에코플랜트|두산에너빌리티"),
]
_DEMAND_RX = [(k, re.compile(p, re.I)) for k, p in _DEMAND_RULES]

# 공급지역만으로 내리는 **약한** 판정 — 계약상대에서 아무 것도 못 읽었을 때만 쓴다.
# 지역은 수요처가 아니다(미국 계약이라고 다 유틸리티는 아니다). 그래서 근거 등급을 낮춰
# `demand_src="region"` 으로 남기고, 화면에서 구분할 수 있게 한다.
_REGION_DEMAND = [
    ("me_utility", r"사우디|UAE|아랍|중동|쿠웨이트|카타르|오만|바레인|이라크|요르단|이집트"),
]
_REGION_RX = [(k, re.compile(p, re.I)) for k, p in _REGION_DEMAND]

# 관계회사 재발주 — 계약상대가 자회사면 그 이름으로는 수요처를 알 수 없다(실측:
# HD현대일렉트릭 → HD Hyundai Electric America). 주석의 최종 수요처 문구를 대신 본다.
_REL_AFFIL = re.compile(r"자회사|계열회사|계열사|종속회사|모회사|관계회사|최대주주")


def demand_of(party, rel, note, name, region):
    """(수요처 키, 근거) — 계약상대 → 계약명 → (상대를 모를 때만) 주석 → 공급지역 순.

    **주석은 함부로 보지 않는다.** 주석은 「계약금액 및 계약기간은 공사진행 상황에 따라
    변경될 수 있습니다」 같은 상투구가 대부분이라, 통째로 훑으면 상투구의 낱말로 수요처가
    정해진다(실측: 선도전기 에스케이하이닉스 건이 주석 문구 때문에 산업 플랜트로 갔다).
    그래서 계약상대가 **관계회사이거나 비어 있을 때만** 주석을 본다 — 그때는 최종 수요처가
    주석에만 있기 때문이다(HD현대일렉트릭 재발주 건, 위 §3).

    판정 못 하면 (None, ""). 스펙의 6갈래 밖으로 나가지 않는다.
    """
    affil = bool(_REL_AFFIL.search(rel or "")) or _blank(party)
    order = [("party", party), ("name", name)]
    if affil:
        order = [("note", note)] + order
    for src, text in order:
        if not text:
            continue
        for key, rx in _DEMAND_RX:
            if rx.search(text):
                return key, src
    for key, rx in _REGION_RX:
        if rx.search(region or ""):
            return key, "region"
    return None, ""


# ── 제품군 분류 ─────────────────────────────────────────────
# 계약명 문구로만 판정한다(FINDINGS §6의 품목 어휘). 확신이 없으면 **비운다**.
# 순서가 중요하다: `가스절연개폐장치(GIS)`는 차단기 갈래지 개폐기가 아니고(스펙 §분류),
# `초고압 변압기`가 `변압기`보다 먼저다.
_PRODUCT_RULES = [
    ("ehv", r"초고압|765\s*[kK][vV]|345\s*[kK][vV]|154\s*[kK][vV]|"
            r"(?:超|초)고압\s*변압기|대형\s*변압기|전력용\s*변압기|주변압기|Main\s*Transformer"),
    ("breaker", r"차단기|가스절연|GIS\s*(?:차단기|개폐장치)?|GCB|VCB|ACB|MCCB|"
                r"가스절연개폐장치|SF6|진공차단기|초고압\s*개폐장치"),
    ("switchgear", r"수배전|배전반|분전반|배전\s*설비|MCC|전동기\s*제어반|제어반|큐비클|"
                   r"스위치기어|Switchgear|배전\s*센터|전기실"),
    ("dist_tr", r"배전\s*변압기|주상\s*변압기|패드\s*변압기|몰드\s*변압기|유입\s*변압기|"
                r"건식\s*변압기|Pad[\s-]?Mount|변압기"),
    ("switch", r"개폐기|부하개폐기|리클로저|Recloser|단로기|Disconnect"),
    ("converter", r"인버터|Inverter|PCS\b|전력변환|컨버터|Converter|ESS\b|에너지저장|"
                  r"충전기|정류기|UPS\b"),
    ("cable", r"전력선|전력\s*케이블|케이블|전선|가공송전선|절연선|Cable"),
    ("relay", r"계전기|보호제어|배전자동화|원방감시|SCADA|전력량계|원격검침|감시제어"),
    ("fitting", r"금구류|애자|절연유|부스덕트|부스웨이|Busway|송배전\s*자재|배전\s*자재|"
                r"전주|철탑|가공\s*배전"),
]
_PRODUCT_RX = [(k, re.compile(p)) for k, p in _PRODUCT_RULES]
assert set(k for k, _ in _PRODUCT_RULES) <= set(PRODUCT_ORDER)
assert set(k for k, _ in _DEMAND_RULES) <= set(DEMAND_ORDER)


def product_of(name):
    """계약명 → 제품군 키. 못 읽으면 None(비운다).

    `리액터`처럼 어느 갈래인지 원문으로 못 가르는 낱말은 일부러 넣지 않았다
    (산일전기 `리액터 공급`은 인버터용 수동소자이고, 초고압 분로리액터도 같은 이름이다).
    """
    t = name or ""
    for key, rx in _PRODUCT_RX:
        if rx.search(t):
            return key
    return None


# ── 공시 본문 → 필드 ───────────────────────────────────────

def _norm_key(key):
    return re.sub(r"^\s*[\d]+\.\s*|^\s*-\s*|[\s　ㆍ·]", "", key)


_SECT = re.compile(r"^\s*\d+\.\s")


def _kv(html):
    """(항목, 세부항목, 값) 표 → (정규화 사전, 원문 (라벨,값) 목록).

    **전폭(colspan) 행을 살려야 한다.** 「기타 투자판단과 관련한 중요사항」의 본문은 한 행이
    통째로 한 칸이라 모든 셀이 같은 문자열로 펼쳐진다 — 라벨/값을 가르는 규칙만 쓰면
    이 행이 통째로 버려지고, 그러면 **계약금액의 원통화가 사라진다**(위 §2). 그래서
    전폭 행은 절 제목(`9. 기타 …`)과 본문으로 나눠 앞선 제목에 붙인다.
    """
    kv, raw, pending = {}, [], ""
    for t in parse_tables(html):
        for row in t["rows"]:
            cells = [c.strip() for c in row]
            if not cells:
                continue
            first = cells[0]
            # 전폭 행: 모든 칸이 같거나(colspan 펼침), 긴 본문이 앞머리를 공유하며 반복되는 꼴
            wide = len(set(cells)) == 1 or (
                len(first) > 120
                and all(c.startswith(first[:60]) or first.startswith(c[:60]) for c in cells))
            if wide:
                text = max(cells, key=len)
                if not text:
                    continue
                if _SECT.match(text) and len(text) <= 40:  # 절 제목
                    pending = text
                    continue
                key = pending or "본문"
                raw.append((key, text))
                kv.setdefault(_norm_key(key), text)
                continue
            if len(cells) < 2:
                continue
            val = cells[-1]
            labels = [c for c in cells[:-1] if c and c != val]
            key = " ".join(dict.fromkeys(labels))
            if not key:
                continue
            raw.append((key, val))
            kv.setdefault(_norm_key(key), val)
    return kv, raw


def _kv_from_raw(raw):
    kv = {}
    for k, v in raw:
        kv.setdefault(_norm_key(k), v)
    return kv


def _find(kv, *needles):
    """needle 을 모두 품은 라벨 중 **가장 짧은** 라벨의 값 — 정정공시의 정정 표(긴 라벨)보다
    본표(짧은 라벨)가 이긴다."""
    hits = [(len(k), i, v) for i, (k, v) in enumerate(kv.items()) if all(n in k for n in needles)]
    return min(hits)[2] if hits else None


_DATE = re.compile(r"(\d{4})[-.\s/]*(\d{1,2})[-.\s/]*(\d{1,2})")


def _date(s):
    """`2026-08-17` 꼴만 날짜로 본다. 문구가 들어온 칸은 None(fail-closed)."""
    m = _DATE.search(s or "")
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    if not (1990 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return "%04d-%02d-%02d" % (y, mo, d)


def _years(start, end):
    if not start or not end or end <= start:
        return None
    import datetime
    a = datetime.date(*(int(x) for x in start.split("-")))
    b = datetime.date(*(int(x) for x in end.split("-")))
    return round((b - a).days / 365.25, 1)


def _blank(v):
    return (v or "").strip() in ("", "-", "–", "—")


def _fields_from_kv(kv):
    # 양식 두 갈래 — 유가증권 「- 체결계약명」, 코스닥 「1. 판매ㆍ공급계약 내용」.
    name = (_find(kv, "체결계약명") or _find(kv, "계약명")
            or _find(kv, "판매", "공급계약", "내용") or _find(kv, "공급계약내용") or "")
    if _blank(name):
        # 유가증권 양식에서 계약명이 비면 계약 '구분'(상품공급·기타 판매ㆍ공급계약)이라도 남긴다.
        name = _find(kv, "판매", "공급계약", "구분") or name or ""
    # 금액 라벨도 양식마다 다르다(코스닥: 확정/조건부/총액).
    amt_krw = num_of(_find(kv, "계약금액총액(원)") or _find(kv, "계약금액(원)")
                     or _find(kv, "확정계약금액") or _find(kv, "계약금액") or "")
    rev = num_of(_find(kv, "최근매출액(원)") or _find(kv, "최근매출액") or "")
    party = (_find(kv, "계약상대방") or _find(kv, "계약상대") or "").strip()
    rel = (_find(kv, "회사와의관계") or "").strip()
    region = (_find(kv, "판매", "공급지역") or "").strip()
    note = (_find(kv, "기타", "중요") or _find(kv, "기타", "참고") or _find(kv, "기타") or "").strip()
    start = _date(_find(kv, "계약기간", "시작") or _find(kv, "시작일") or "")
    end = _date(_find(kv, "계약기간", "종료") or _find(kv, "종료일") or "")
    signed = _date(_find(kv, "계약(수주)일자") or _find(kv, "수주", "일자") or "")
    withheld_why = (_find(kv, "공시유보", "유보사유") or _find(kv, "유보사유") or "").strip()
    withheld_until = (_find(kv, "공시유보", "유보기한") or _find(kv, "유보기한") or "").strip()
    # 공시유보 — 계약상대·금액을 영업비밀로 유보한 건. `유보사유`에 문구가 있거나,
    # 계약상대·금액이 비었는데 유보 칸이 채워진 경우다. 추정하지 않고 '유보'라고 적는다.
    withheld = (not _blank(withheld_why)) or (not _blank(withheld_until))
    amt, cur, fx, fx_src = currency_amount(note, amt_krw)
    if amt is None:
        amt, cur = amt_krw, ("KRW" if amt_krw is not None else None)
    dem, dem_src = demand_of(party, rel, note, name, region)
    return {
        "name": name,
        "product": product_of(name),
        "amt": amt,                                                    # 원통화 그대로
        "cur": cur,                                                    # KRW/USD/…
        "fx": fx,                                                      # 회사가 적용한 내재환율
        "fx_src": fx_src,                                              # 그 근거 문구
        "amt_krw_m": (round(amt_krw / 1e6, 3) if amt_krw is not None else None),   # 백만원
        "rev_krw_m": (round(rev / 1e6, 3) if rev is not None else None),
        "rev_ratio": num_of(_find(kv, "매출액대비(%)") or _find(kv, "매출액대비") or ""),
        "party": party,
        "party_rel": rel,
        "affiliate": bool(_REL_AFFIL.search(rel or "")),
        "demand": dem,
        "demand_src": dem_src,
        "region_raw": region,
        "start": start or "",
        "end": end or "",
        "years": _years(start, end),
        "signed": signed or "",
        "advance": (_find(kv, "계약금", "선급금") or "").strip(),
        "payterm": (_find(kv, "대금지급") or "").strip(),
        "withheld": withheld,
        "withheld_why": withheld_why if not _blank(withheld_why) else "",
        "withheld_until": withheld_until if not _blank(withheld_until) else "",
        "note": note[:400],
    }


def parse_contract(html, rcp, title, stock):
    kv, raw = _kv(html)
    rec = {"rcp": rcp, "stock": stock, "title": title,
           "corrected": bool(_FIX.search(title or "")),
           "canceled": bool(_CANCEL.search(title or ""))}
    rec.update(_fields_from_kv(kv))
    rec["kv"] = raw
    return rec


# ── 수집 ────────────────────────────────────────────────────

def _cache_path(stock):
    return os.path.join(CACHE, "%s.json" % stock)


def _load_cache(stock):
    try:
        with open(_cache_path(stock), encoding="utf-8") as f:
            return json.load(f)
    except (IOError, OSError, ValueError):
        return {"stock": stock, "docs": {}}


def _save_cache(stock, cache):
    os.makedirs(CACHE, exist_ok=True)
    docs = cache.get("docs", {})
    out = {"stock": stock, "n": len(docs),
           "docs": {k: docs[k] for k in sorted(docs)}}
    atomic_write(_cache_path(stock), json.dumps(out, ensure_ascii=False, indent=1) + "\n")


def _search_years(stock, years, end, log):
    """검색 상한(maxResults=100)에 닿지 않도록 **연 단위로 쪼개** 검색한다.

    한 번에 3년을 긁으면 계약이 잦은 회사(효성중공업·산일전기)는 100건 상한에 걸려
    오래된 계약이 조용히 빠진다 — 빠진 줄도 모르는 것이 최악이다(COMMON §0-2).
    """
    end_y = int(end[:4])
    seen, capped = {}, False
    for y in range(end_y - years + 1, end_y + 1):
        s, e = "%d0101" % y, min("%d1231" % y, end)
        try:
            lst = search_reports(stock, s, e, "I001")
        except Exception as exc:
            log.write("[warn] %s %d 검색 실패 %s\n" % (stock, y, exc))
            continue
        if len(lst) >= 100:
            capped = True
            log.write("[warn] %s %d 검색이 100건 상한에 닿았다 — 누락 가능\n" % (stock, y))
        for rcp, title in lst:
            seen[rcp] = title
    return seen, capped


def collect(stocks, years=3, end=None, force=False, log=sys.stderr):
    end = end or time.strftime("%Y%m%d")
    for st in stocks:
        found, capped = _search_years(st, years, end, log)
        cons = {r: t for r, t in found.items() if _SUPPLY.search(t or "")}
        cache = _load_cache(st)
        docs = cache.setdefault("docs", {})
        got, new = 0, 0
        for rcp in sorted(cons):
            if rcp in docs and not force:
                got += 1
                continue
            try:
                nodes = toc(rcp)
                if not nodes:
                    continue
                rec = parse_contract(fetch_section(nodes[0]), rcp, cons[rcp], st)
            except Exception as exc:          # 일시 실패는 캐시하지 않는다(다시 돌리면 받는다)
                log.write("[warn] %s %s %s\n" % (st, rcp, exc))
                continue
            docs[rcp] = rec
            got += 1
            new += 1
        cache["capped"] = capped
        cache["window"] = {"years": years, "end": end}
        if docs:
            _save_cache(st, cache)
        log.write("%s 계약공시 %d건 · 캐시 %d건(신규 %d)%s\n"
                  % (st, len(cons), got, new, " [상한주의]" if capped else ""))
        log.flush()


# ── 빌드 ────────────────────────────────────────────────────

def _dedup_key(rec):
    """정정공시를 원본과 잇는 열쇠. 계약명·수주일이 같으면 같은 계약으로 본다.

    정정공시는 금액·기간이 바뀌므로 금액을 열쇠에 넣지 않는다. 계약명이 빈 건(유보)은
    계약상대·수주일로 잇는다.
    """
    name = re.sub(r"\s+", "", rec.get("name") or "")
    if not name or name in ("-", "기타판매ㆍ공급계약", "상품공급"):
        name = re.sub(r"\s+", "", rec.get("party") or "") or rec["rcp"]
    return (rec["stock"], name, rec.get("signed") or rec.get("start") or "")


def build(stocks=None):
    """캐시 → assets/contracts.json. 최신 정정본만 집계에 쓰고 원본은 `supersedes` 로 문다."""
    out = []
    files = sorted(f for f in os.listdir(CACHE) if f.endswith(".json")) \
        if os.path.isdir(CACHE) else []
    for f in files:
        st = f[:-5]
        if stocks and st not in stocks:
            continue
        with open(os.path.join(CACHE, f), encoding="utf-8") as fh:
            cache = json.load(fh)
        recs = list(cache.get("docs", {}).values())
        by = {}
        for r in sorted(recs, key=lambda r: r["rcp"]):   # rcp 오름차순 → 뒤(정정)가 덮는다
            if r.get("kv"):                              # 분류는 캐시에서 **다시** 한다
                r.update(_fields_from_kv(_kv_from_raw(r["kv"])))
            key = _dedup_key(r)
            if key in by:
                prev = by[key]
                r["supersedes"] = (prev.get("supersedes") or []) + [prev["rcp"]]
            by[key] = r
        out.extend(by.values())
    out.sort(key=lambda r: (r["stock"], r.get("signed") or r.get("start") or "", r["rcp"]))
    for r in out:
        r.pop("kv", None)
    write_asset("contracts.json", {"n": len(out), "rows": out})
    return out


def load():
    try:
        return load_asset("contracts.json")["rows"]
    except (IOError, OSError, KeyError):
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--years", type=int, default=3)
    ap.add_argument("--to", dest="end", default=time.strftime("%Y%m%d"))
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    stocks = [r["stock"] for r in kgrid_universe.load()]
    if a.only:
        stocks = a.only.split(",")
    if a.collect:
        collect(stocks, a.years, a.end, a.force)
    if a.build:
        from collections import Counter
        rows = build(set(stocks) if a.only else None)
        print("계약 %d건 · 회사 %d사" % (len(rows), len(set(r["stock"] for r in rows))))
        print("  통화 %s" % dict(Counter(r["cur"] for r in rows)))
        print("  수요처 %s" % dict(Counter(r["demand"] for r in rows)))
        print("  제품군 %s" % dict(Counter(r["product"] for r in rows)))
        print("  유보 %d건 · 정정 %d건 · 해지 %d건"
              % (sum(1 for r in rows if r["withheld"]),
                 sum(1 for r in rows if r.get("supersedes")),
                 sum(1 for r in rows if r.get("canceled"))))


if __name__ == "__main__":
    sys.exit(main())
