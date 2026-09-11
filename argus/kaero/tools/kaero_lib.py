#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kaero_lib — 한국우주항공(argus/kaero) 파이프라인 공용 유틸.

DART 수집·표 파서·KIND 모집단은 `argus/kce/tools` 의 것을, 페이지 셸·차트·표 JS는
`argus/kship/tools` 의 것을 **그대로 import** 한다(COMMON.md §1). 복사하지 않는다 —
무키 3단 경로·프로세스 간 요청 게이트·EUC-KR 판정·머리행 평탄화는 산업과 무관한 층이고,
두 벌로 갈라지면 한쪽만 고쳐지는 날이 온다.

여기서 새로 만드는 것은 **이 산업의 축**뿐이다:
  · 통화 — 수주표가 USD 표와 원화 표로 **나뉘어 온다**(FINDINGS §1). 환산하지 않는다.
    기준 단위는 '통화별 백만'(USD 표는 백만달러, KRW 표는 백만원)이고 표기만 갈린다.
  · 영역 — 민수 기체구조물 · 항공엔진/부품(RSP) · MRO/창정비 · 방산 항공 · 우주
  · 계약 성격 — RSP · LTA · PBL · 개발 · 양산 · MRO
  · 고객 계층 — OEM 직납 · Tier-1 하도 · 국내 체계업체 · 정부/기관

규약(COMMON.md): stdlib 전용 · fail-closed · 원자적 쓰기 · 정규화 출력 · API 키 없음.
"""
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # argus/kaero/tools
KAERO = os.path.dirname(HERE)                               # argus/kaero
ARGUS = os.path.dirname(KAERO)                              # argus
KCE_TOOLS = os.path.join(ARGUS, "kce", "tools")
KSHIP_TOOLS = os.path.join(ARGUS, "kship", "tools")
ASSETS = os.path.join(HERE, "assets")

for _p in (KCE_TOOLS, KSHIP_TOOLS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 산업 무관 층 — kce/kship 에서 가져온다.
from kce_lib import (atomic_write, json_for_html, latest_quarter, norm_col,   # noqa: E402,F401
                     num_of, q_next, q_of, q_range, report_kind)
from kce_fetch import (fetch_section, find_sections, pick_report,             # noqa: E402,F401
                       search_reports, toc, _get)
from kce_parse import parse_tables                                           # noqa: E402,F401
from kce_probe import report_window                                          # noqa: E402,F401
from kce_universe import KIND_URL, parse_kind                                # noqa: E402,F401
from kship_parse import unit_of, is_total                                    # noqa: E402,F401
from kship_lib import CHART_DEFAULTS_JS, TABLE_JS                            # noqa: E402,F401

E = html.escape


def load_asset(name):
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return json.load(f)


def write_asset(name, data):
    """정규화 JSON(키 순서 보존·들여쓰기 1·개행 고정) — 같은 데이터는 같은 바이트."""
    os.makedirs(ASSETS, exist_ok=True)
    atomic_write(os.path.join(ASSETS, name),
                 json.dumps(data, ensure_ascii=False, indent=1) + "\n")


def asset_path(name):
    return os.path.join(ASSETS, name)


def has_asset(name):
    return os.path.exists(os.path.join(ASSETS, name))


def clean(s):
    return re.sub(r"[\s 　]+", "", s or "")


# ── 정기보고서 열기 ────────────────────────────────────────
# `[첨부정정] 사업보고서 (2025.12)` 는 제목의 기준월이 맞아 `pick_report` 가 1순위로 주지만
# 목차가 `정정 신고 (보고)`·`영 업 보 고 서` 두 줄뿐이라 II절이 없다(FINDINGS §0 — 표본 8사 중
# 2사가 여기 걸렸다). 후보를 **차례로 열어** 원하는 절이 나오는 첫 문서를 쓴다.
_AMEND = re.compile(r"첨부정정|기재정정|정정신고|정 정 신 고")


def report_candidates(stock, quarter, max_try=4):
    """그 분기의 정기보고서 후보를 순서대로. 정정본은 뒤로 민다(원본이 있으면 원본 먼저)."""
    start, end = report_window(quarter)
    reps = pick_report(search_reports(stock, start, end, report_kind(quarter)), quarter)
    plain = [r for r in reps if not _AMEND.search(r[1] or "")]
    amend = [r for r in reps if _AMEND.search(r[1] or "")]
    return (plain + amend)[:max_try]


def open_sections(stock, quarter, sections, need, max_try=4):
    """후보를 차례로 열어 `need` 절이 있는 첫 문서 → (rcp, title, found, tried).

    `sections` 는 find_sections 형식([(key, [제목후보…]), …]), `need` 는 반드시 있어야 할 key.
    끝까지 못 찾으면 (None, None, {}, tried) — 부르는 쪽이 fail-closed 로 적는다."""
    tried = []
    for rcp, title in report_candidates(stock, quarter, max_try):
        try:
            found = find_sections(toc(rcp), sections)
        except Exception as e:
            tried.append((rcp, title, "목차 실패: %s" % e))
            continue
        if need in found:
            return rcp, title, found, tried
        tried.append((rcp, title, "`%s` 절 없음(목차 %d절)" % (need, len(found))))
    return None, None, {}, tried


def text_of(page_html):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page_html, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"[ \t\xa0　]+", " ", s)


# ── 통화 ───────────────────────────────────────────────────
# 기준 단위는 **통화별 백만**이다(unit_of 가 그렇게 정규화한다). 절대 환산하지 않는다 —
# 환율은 날마다 바뀌고 공시 시점 환율이 없으므로 환산은 추정이 된다(FINDINGS §1).
CURRENCIES = {
    "KRW": {"label": "원", "unit": "억원", "div": 100.0, "digits": 0, "hex": "#3987e5"},
    "USD": {"label": "달러", "unit": "백만달러", "div": 1.0, "digits": 0, "hex": "#199e70"},
    "EUR": {"label": "유로", "unit": "백만유로", "div": 1.0, "digits": 0, "hex": "#9085e9"},
}
CUR_ORDER = ("KRW", "USD", "EUR")


def cur_unit(cur):
    return CURRENCIES.get(cur, {}).get("unit", "?")


def fmt_money(v, cur="KRW"):
    """통화별 표기. KRW는 억원, 외화는 백만 단위 그대로. 환산하지 않는다."""
    if v is None:
        return "—"
    c = CURRENCIES.get(cur)
    if not c:
        return format(round(v), ",d")
    x = v / c["div"]
    return format(round(x), ",d") if c["digits"] == 0 else ("%%.%df" % c["digits"]) % x


def fmt_money_u(v, cur="KRW"):
    """값 + 단위(`1,234 억원`)."""
    return "—" if v is None else "%s %s" % (fmt_money(v, cur), cur_unit(cur))


def fmt_eok(v):
    """백만원 → 억원 문자열(원화 전용)."""
    return fmt_money(v, "KRW")


def fmt_n(v):
    if v is None:
        return "—"
    return format(v, ",d") if float(v).is_integer() else format(v, ",.1f")


def fmt_x(v, digits=1):
    if v is None:
        return "—"
    return ("%%.%df" % digits) % v


def pct(a, b):
    if not a or not b:
        return None
    return 100.0 * a / b


# ── 영역(domain) ───────────────────────────────────────────
# 색은 슬롯에 **고정**한다(필터로 줄어도 재배색 금지). 값은 kaero.css 의 --s1..--s8 과
# 같아야 한다 — 두 벌이 어긋나면 같은 영역이 표와 차트에서 다른 색이 된다.
DOMAINS = [
    {"id": "struct", "slot": 1, "label": "민수 기체구조물", "hex": "#3987e5",
     "desc": "동체·날개·벌크헤드 등 구조물을 OEM·Tier-1에 납품"},
    {"id": "engine", "slot": 2, "label": "항공엔진·부품", "hex": "#d95926",
     "desc": "가스터빈 엔진·엔진부품. RSP(수익분배) 계약이 여기 있다"},
    {"id": "mro", "slot": 3, "label": "MRO·창정비", "hex": "#199e70",
     "desc": "정비·창정비·PBL(성과기반군수)"},
    {"id": "defav", "slot": 4, "label": "방산 항공", "hex": "#c98500",
     "desc": "완제기·군용기·군용 항공전자. kdef 탭과 겹친다"},
    {"id": "space", "slot": 5, "label": "우주", "hex": "#d55181",
     "desc": "발사체·위성 본체·탑재체·지상국"},
    {"id": "other", "slot": 0, "label": "기타·미상", "hex": "#5d6675",
     "desc": "원문 문구로 영역을 가르지 못한 것"},
]
DOMAIN_BY_ID = {d["id"]: d for d in DOMAINS}


def domain_color(did):
    return DOMAIN_BY_ID.get(did, DOMAIN_BY_ID["other"])["hex"]


def domain_label(did):
    return DOMAIN_BY_ID.get(did, DOMAIN_BY_ID["other"])["label"]


def slot_color(slot):
    for d in DOMAINS:
        if d["slot"] == slot:
            return d["hex"]
    raise KeyError(slot)


# ── 근거 등급 ───────────────────────────────────────────────
# 화면에 그대로 찍는다. 추정은 추정이라 적는다(COMMON §0-1).
GRADES = {
    "A": "공시 표에 그대로 적힌 값",
    "B": "공시 본문 문구에서 읽음",
    "C": "문구 분류(사전 매칭) — 추정",
}
