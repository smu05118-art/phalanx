#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""knuke_lib — 한국원전·발전기자재(argus/knuke) 파이프라인 공용 유틸.

한국건설(kce)·한국조선(kship) 탭의 DART 수집·표 파서·페이지 셸을 **그대로 import** 한다
(COMMON §1). 복사하지 않는다 — DART 무키 3단 경로·프로세스 간 요청 게이트·머리행 정규화·
단위/통화 인식은 산업과 무관한 층이다. 산업 특성(발전원·공급계층·발주처 집중도·잔고
커버리지·호기 타임라인)만 여기서 새로 만든다.

규약(COMMON.md): stdlib 전용 · fail-closed · 원자적 쓰기 · 정규화 출력 · API 키 없음.
"""
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # argus/knuke/tools
KNUKE = os.path.dirname(HERE)                               # argus/knuke
ARGUS = os.path.dirname(KNUKE)                              # argus
KCE_TOOLS = os.path.join(ARGUS, "kce", "tools")
KSHIP_TOOLS = os.path.join(ARGUS, "kship", "tools")
ASSETS = os.path.join(HERE, "assets")

for _p in (KCE_TOOLS, KSHIP_TOOLS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 산업 무관 층 — kce/kship 에서 가져온다.
from kce_lib import (atomic_write, json_for_html, latest_quarter, norm_col,     # noqa: E402,F401
                     num_of, q_next, q_of, q_range, report_kind)
from kce_fetch import (fetch_section, find_sections, pick_report,               # noqa: E402,F401
                       search_reports, toc, _get)
from kce_parse import parse_tables                                             # noqa: E402,F401
from kce_probe import report_window                                            # noqa: E402,F401
from kce_universe import KIND_URL, parse_kind                                  # noqa: E402,F401
# 단위·통화·합계 판정은 조선 탭이 통화까지 읽도록 고쳐 둔 것을 쓴다.
from kship_parse import unit_of, is_total                                      # noqa: E402,F401
from kship_lib import CHART_DEFAULTS_JS, TABLE_JS                              # noqa: E402,F401

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


# ── 색 ─────────────────────────────────────────────────────
# 발전원(domain)·공급계층(tier) 색은 슬롯에 **고정**한다(필터로 줄어도 재배색 금지).
# 조선 탭이 다크 표면(#171a21)에서 검증한 8슬롯 팔레트를 그대로 쓴다. 값은 knuke.css 의
# --s1..--s8 과 **같아야 한다**(칩은 CSS 변수, 차트는 이 헥사를 쓴다).
PALETTE = [
    {"slot": 1, "hex": "#3987e5"},   # 원자력
    {"slot": 2, "hex": "#d95926"},   # 화력
    {"slot": 3, "hex": "#199e70"},   # 신재생
    {"slot": 4, "hex": "#c98500"},   # 송변전
    {"slot": 5, "hex": "#d55181"},   # 주기기 / 기타
    {"slot": 6, "hex": "#008300"},   # 정비·O&M
    {"slot": 7, "hex": "#9085e9"},   # 계측제어 / 설계
    {"slot": 8, "hex": "#e66767"},   # 검사·해체
    {"slot": 0, "hex": "#5d6675"},   # 기타·미상 — 회색
]


def slot_color(slot):
    for s in PALETTE:
        if s["slot"] == slot:
            return s["hex"]
    return "#5d6675"


# ── 숫자 표기 ───────────────────────────────────────────────

def fmt_eok(v):
    """백만원 → 억원 문자열."""
    if v is None:
        return "—"
    return format(round(v / 100), ",d")


def fmt_n(v):
    if v is None:
        return "—"
    return format(v, ",d") if float(v).is_integer() else format(v, ",.1f")


def fmt_x(v, digits=1):
    """배수(년·배). None이면 —."""
    if v is None:
        return "—"
    return ("%%.%df" % digits) % v


def pct(a, b):
    if not a or not b:
        return None
    return 100.0 * a / b


# ── 페이지 셸 ───────────────────────────────────────────────

def _rel(depth):
    return "../" * depth


def page(title, body, depth=0, head_extra="", scripts=(), h1=None, crumbs=(), tags=(),
         nav=(), lead=""):
    """공용 셸. depth=0 은 knuke 루트, 1 은 회사 디렉터리.

    kship_lib.page 와 같은 구조지만 CSS 는 assets/knuke.css, 꼬리말은 원전 출처다.
    외부 스크립트(Chart.js)는 **본문보다 먼저** 둔다 — 본문 인라인 차트가 그 전역을 즉시 쓴다.
    """
    r = _rel(depth)
    tagh = "".join('<span class="tag">%s</span>' % E(t) for t in tags if t)
    navh = "".join('<a href="%s"%s>%s</a>'
                   % (E(href), (' target="_blank" rel="noopener noreferrer"' if href.startswith("http") else ""), E(label))
                   for label, href in nav)
    crumbh = ""
    if crumbs:
        parts = []
        for label, href in crumbs:
            parts.append('<a href="%s">%s</a>' % (E(href), E(label)) if href else "<span>%s</span>" % E(label))
        crumbh = '<div class="crumb">%s</div>' % " › ".join(parts)
    sh = "".join('<script src="%s"></script>' % E(s) for s in scripts)
    return ("<!doctype html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            "<title>%s</title>\n<link rel=\"stylesheet\" href=\"%sassets/knuke.css\">\n%s</head>\n"
            "<body>\n<header class=\"top\"><div class=\"hd\"><h1>%s</h1>%s<span class=\"sp\">%s</span></div>%s</header>\n%s"
            "<main>%s%s</main>\n"
            "<footer>출처 DART 정기보고서(사업의 내용 II-4 매출·수주상황·부문 매출)·수시공시「단일판매ㆍ공급계약체결」, "
            "KRX KIND 상장법인목록. 단위 백만원 · 표기는 억원. 원전·발전 주기기는 진행기준 수익인식이 많아 "
            "수주·완성·매출 시점이 다릅니다. 참고용 · 투자조언 아님.</footer>\n</body></html>\n"
            % (E(title), r, head_extra, E(h1 or title), tagh, navh, crumbh, sh,
               ('<p class="lead">%s</p>' % lead) if lead else "", body))
