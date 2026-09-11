#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kdef_lib — 한국방산(argus/kdef) 파이프라인 공용 유틸.

한국건설(argus/kce/tools)의 DART 수집·표 파서·KIND 모집단 도구를 **그대로 import** 한다.
복사하지 않는다 — DART 무키 3단 경로·재시도·프로세스 간 요청 게이트·머리행 정규화는
산업과 무관한 층이고, 두 벌로 갈라지면 한쪽만 고쳐지는 날이 온다.
페이지 셸·차트 기본값·표 JS는 kship_lib 의 것을 그대로 쓰되 CSS 경로만 kdef 로 바꾼다.

산업 특성(계통·계약유형·잔고 커버리지·방산비중·부품 계통)만 여기서 새로 만든다.

규약(COMMON.md): stdlib 전용 · fail-closed · 원자적 쓰기 · 정규화 출력 · API 키 없음.
"""
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # argus/kdef/tools
KDEF = os.path.dirname(HERE)                                # argus/kdef
ARGUS = os.path.dirname(KDEF)                               # argus
KCE_TOOLS = os.path.join(ARGUS, "kce", "tools")
KSHIP_TOOLS = os.path.join(ARGUS, "kship", "tools")
ASSETS = os.path.join(HERE, "assets")

for _p in (KCE_TOOLS, KSHIP_TOOLS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 산업 무관 층 — kce에서 가져온다.
from kce_lib import (atomic_write, json_for_html, latest_quarter, norm_col,   # noqa: E402,F401
                     num_of, q_next, q_of, q_range, report_kind)
from kce_fetch import (fetch_section, find_sections, pick_report,             # noqa: E402,F401
                       search_reports, toc, _get)
from kce_parse import parse_tables                                           # noqa: E402,F401
from kce_probe import report_window                                          # noqa: E402,F401
from kce_universe import KIND_URL, parse_kind                                # noqa: E402,F401
# 단위 캡션·합계 판정은 조선 탭이 이미 통화까지 읽도록 고쳐 둔 것을 쓴다.
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


# ── 색 ─────────────────────────────────────────────────────
# 계통(domain) 색은 슬롯에 **고정**한다(필터로 줄어도 재배색 금지). 조선 탭이 다크
# 표면(#171a21)에서 검증한 8슬롯 팔레트를 그대로 쓴다.
PALETTE = [
    {"slot": 1, "hex": "#4e93f0"},
    {"slot": 2, "hex": "#1fa97a"},
    {"slot": 3, "hex": "#9b8cf2"},
    {"slot": 4, "hex": "#d99000"},
    {"slot": 5, "hex": "#e0608c"},
    {"slot": 6, "hex": "#3bb8bd"},
    {"slot": 7, "hex": "#8fae3f"},
    {"slot": 8, "hex": "#c2705a"},
]


def slot_color(slot):
    for s in PALETTE:
        if s["slot"] == slot:
            return s["hex"]
    raise KeyError(slot)


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
    """공용 셸. depth=0 은 kdef 루트, 1 은 회사 디렉터리.

    kship_lib.page 와 같은 구조지만 CSS 는 assets/kdef.css, 꼬리말은 방산 출처다.
    외부 스크립트(Chart.js)는 **본문보다 먼저** 둔다 — 본문의 인라인 차트 코드가 그
    전역을 즉시 쓰기 때문이다(꼬리에 두면 `Chart is not defined`).
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
            "<title>%s</title>\n<link rel=\"stylesheet\" href=\"%sassets/kdef.css\">\n%s</head>\n"
            "<body>\n<header class=\"top\"><div class=\"hd\"><h1>%s</h1>%s<span class=\"sp\">%s</span></div>%s</header>\n%s"
            "<main>%s%s</main>\n"
            "<footer>출처 DART 정기보고서(사업의 내용·주석)·수시공시「단일판매ㆍ공급계약체결」, KRX KIND 상장법인목록. "
            "단위 백만원 · 표기는 억원. 방산 계약은 진행기준 수익인식이 많아 수주·인도·매출 시점이 다릅니다. "
            "참고용 · 투자조언 아님.</footer>\n</body></html>\n"
            % (E(title), r, head_extra, E(h1 or title), tagh, navh, crumbh, sh,
               ('<p class="lead">%s</p>' % lead) if lead else "", body))
