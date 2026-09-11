#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kgrid_lib — 한국전력기기(argus/kgrid) 파이프라인 공용 유틸.

COMMON.md §1 대로 산업과 무관한 층은 **가져다 쓴다**(복사하지 않는다):
  · DART 무키 3단 경로·재시도·프로세스 간 요청 게이트·EUC-KR 판정 — `kce_fetch`
  · 표 추출·머리행 평탄화·정규화 — `kce_parse`
  · KIND 상장법인목록 — `kce_universe`
  · 단위 캡션의 **통화**·합계 판정 — `kship_parse`(일진전기 `천USD` 때문에 이 층을 고쳤다,
    FINDINGS §5). 두 벌로 갈라지면 한쪽만 고쳐지는 날이 온다.
  · 페이지 셸의 구조·차트 기본값·표 JS — `kship_lib`

전력기기 특성만 여기서 새로 만든다: 제품군 8갈래 색 · 잔고 성격(장납기/회전) 판정 ·
통화가 섞인 값의 표기(환산하지 않는다) · 근거 등급.

규약(COMMON.md): stdlib 전용 · fail-closed · 원자적 쓰기 · 정규화 출력 · API 키 없음.
"""
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # argus/kgrid/tools
KGRID = os.path.dirname(HERE)                               # argus/kgrid
ARGUS = os.path.dirname(KGRID)                              # argus
KCE_TOOLS = os.path.join(ARGUS, "kce", "tools")
KSHIP_TOOLS = os.path.join(ARGUS, "kship", "tools")
ASSETS = os.path.join(HERE, "assets")

for _p in (KCE_TOOLS, KSHIP_TOOLS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

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


# ── 제품군 색 ───────────────────────────────────────────────
# 색은 **제품군 슬롯에 고정**한다(필터로 시리즈가 줄어도 재배색 금지).
# 값은 kgrid.css 의 --s1..--s8 과 **같아야 한다** — 칩은 CSS 변수, 차트는 이 헥사를 쓴다.
# 슬롯 순서는 전력이 흐르는 순서다: 초고압(송전) → 배전 → 개폐·보호 → 부자재.
PRODUCT_SLOTS = [
    ("ehv", 1, "초고압 변압기", "#3987e5"),
    ("dist_tr", 2, "배전용 변압기", "#d95926"),
    ("breaker", 3, "고압 차단기(GIS·VCB)", "#199e70"),
    ("switchgear", 4, "배전반·수배전", "#c98500"),
    ("switch", 5, "개폐기", "#d55181"),
    ("converter", 6, "전력변환(인버터·PCS)", "#008300"),
    ("cable", 7, "전선·케이블", "#9085e9"),
    ("relay", 8, "계전기·보호제어", "#e66767"),
    ("fitting", 0, "금구류·부자재", "#5d6675"),
]
PRODUCT_LABEL = {k: lab for k, _s, lab, _h in PRODUCT_SLOTS}
PRODUCT_COLOR = {k: hx for k, _s, _lab, hx in PRODUCT_SLOTS}
PRODUCT_ORDER = [k for k, _s, _lab, _h in PRODUCT_SLOTS]

# 수요처(발주처 성격) — 스펙 §분류. 원문 매출처·계약상대 문구로 판정한다.
DEMAND_LABEL = {
    "na_utility": "북미 유틸리티",
    "me_utility": "중동 전력청",
    "kepco": "국내 한전·공기업",
    "datacenter": "데이터센터",
    "renewable": "신재생 연계",
    "industrial": "산업 플랜트",
}
DEMAND_ORDER = ["na_utility", "me_utility", "kepco", "datacenter", "renewable", "industrial"]

REGION_LABEL = {"dom": "내수", "na": "북미", "me": "중동", "asia": "아시아", "eu": "유럽",
                "etc": "기타"}
REGION_ORDER = ["dom", "na", "me", "asia", "eu", "etc"]

# 근거 등급 — 매출처 행이 무엇인지. 실명만 '고객'이다(FINDINGS §3).
EVIDENCE_LABEL = {"named": "실명", "anon": "익명", "category": "고객분류", "rel": "관계회사"}


def product_color(key):
    return PRODUCT_COLOR.get(key, "#5d6675")


# ── 잔고 성격 ───────────────────────────────────────────────
# 스펙 §3·§분류: 배수(잔고÷연매출) 1년이 갈림길이다. 초고압 변압기는 백로그 산업(장납기),
# 배전기기는 회전 산업. 배수를 모르면 **추정하지 않는다** — 화면에서 '미상'으로 남는다.
LONG_THRESHOLD = 1.0


def backlog_kind(mult):
    if mult is None:
        return "unknown"
    return "long" if mult >= LONG_THRESHOLD else "rotating"


BACKLOG_LABEL = {"long": "장납기", "rotating": "회전", "unknown": "미상"}


# ── 숫자 표기 ───────────────────────────────────────────────

def fmt_eok(v):
    """백만원 → 억원 문자열. 통화가 원이 아닌 값에는 쓰지 마라(fmt_money 를 쓴다)."""
    if v is None:
        return "—"
    return format(round(v / 100), ",d")


def fmt_money(v, cur="KRW"):
    """통화를 잃지 않는 표기. 원은 억원, 외화는 **백만 단위 그대로** 보인다.

    환율을 원문에서 얻지 못하므로 환산하지 않는다(FINDINGS §2-2, COMMON §0-1).
    """
    if v is None:
        return "—"
    if cur == "KRW":
        return "%s억" % format(round(v / 100), ",d")
    sym = {"USD": "$", "EUR": "€"}.get(cur, cur + " ")
    if abs(v) >= 1000:
        return "%s%.2fbn" % (sym, v / 1000.0)
    return "%s%sm" % (sym, format(round(v), ",d"))


def fmt_n(v):
    if v is None:
        return "—"
    return format(v, ",d") if float(v).is_integer() else format(v, ",.1f")


def fmt_x(v, digits=1):
    """배수(년·배). None이면 —."""
    if v is None:
        return "—"
    return ("%%.%df" % digits) % v


def fmt_pct(v, digits=1):
    if v is None:
        return "—"
    return ("%%.%df%%%%" % digits) % v


def pct(a, b):
    if a is None or not b:
        return None
    return 100.0 * a / b


def coverage(bal, rev_year, bal_cur="KRW", rev_cur="KRW"):
    """잔고 커버리지(년) = 수주잔고 ÷ 연매출.

    **통화가 다르면 계산하지 않는다**(None). 일진전기는 잔고가 천USD·매출이 백만원이라
    환율 없이는 배수를 만들 수 없다 — 조용히 나눠 1000배 틀린 값을 싣는 것이 최악이다.
    """
    if bal is None or not rev_year or bal_cur != rev_cur:
        return None
    return bal / rev_year


# ── 페이지 셸 ───────────────────────────────────────────────

def _rel(depth):
    return "../" * depth


def page(title, body, depth=0, head_extra="", scripts=(), h1=None, crumbs=(), tags=(),
         nav=(), lead=""):
    """공용 셸. depth=0 은 kgrid 루트, 1 은 회사 디렉터리.

    외부 스크립트(Chart.js)는 **본문보다 먼저** 둔다 — 본문의 인라인 차트 코드가 그 전역을
    즉시 쓰기 때문이다(꼬리에 두면 `Chart is not defined`).
    """
    r = _rel(depth)
    tagh = "".join('<span class="tag">%s</span>' % E(t) for t in tags if t)
    navh = "".join('<a href="%s"%s>%s</a>'
                   % (E(href),
                      (' target="_blank" rel="noopener noreferrer"' if href.startswith("http") else ""),
                      E(label))
                   for label, href in nav)
    crumbh = ""
    if crumbs:
        parts = []
        for label, href in crumbs:
            parts.append('<a href="%s">%s</a>' % (E(href), E(label)) if href
                         else "<span>%s</span>" % E(label))
        crumbh = '<div class="crumb">%s</div>' % " › ".join(parts)
    sh = "".join('<script src="%s"></script>' % E(s) for s in scripts)
    return ("<!doctype html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            "<title>%s</title>\n<link rel=\"stylesheet\" href=\"%sassets/kgrid.css\">\n%s</head>\n"
            "<body>\n<header class=\"top\"><div class=\"hd\"><h1>%s</h1>%s"
            "<span class=\"sp\">%s</span></div>%s</header>\n%s"
            "<main>%s%s</main>\n"
            "<footer>출처 DART 정기보고서「II. 사업의 내용」(매출실적·주요매출처·수주상황)·"
            "수시공시「단일판매ㆍ공급계약체결」, KRX KIND 상장법인목록. "
            "단위 백만원 · 표기는 억원. 외화로 공시한 표는 <b>환산하지 않고</b> 통화를 함께 적습니다. "
            "수주잔고 표는 회사에 따라 한 행이 계약이 아니라 <b>사업부문 합계</b>입니다 — 입도를 함께 봅니다. "
            "참고용 · 투자조언 아님.</footer>\n</body></html>\n"
            % (E(title), r, head_extra, E(h1 or title), tagh, navh, crumbh, sh,
               ('<p class="lead">%s</p>' % lead) if lead else "", body))
