#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kcap_lib — 한국화학 캐파(argus/kcap) 파이프라인 공용 유틸.

한국건설(kce)의 DART 무키 수집·표 파서·KIND 모집단과 한국조선(kship)의 페이지 셸·표 JS·재무제표 파서를
**그대로 import** 한다(COMMON.md §1). 산업 특성(생산능력·가동률·제품→스프레드 매핑·분기 마진 프록시)만 여기서 만든다.

규약: stdlib 전용(3.9) · fail-closed · 원자적 쓰기 · 정규화 JSON · 원문 캐시 보존 · API 키 없음.
"""
import datetime
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # argus/kcap/tools
KCAP = os.path.dirname(HERE)                                # argus/kcap
ARGUS = os.path.dirname(KCAP)                               # argus
REPO = os.path.dirname(ARGUS)
ASSETS = os.path.join(HERE, "assets")
CACHE = os.path.join(ASSETS, "cache")                       # 원문 HTML 캐시 (.gitignore: argus/*/tools/assets/cache/)
DATA_DIR = os.path.join(KCAP, "data")
KCE_TOOLS = os.path.join(ARGUS, "kce", "tools")
KSHIP_TOOLS = os.path.join(ARGUS, "kship", "tools")
KCHEM_TOOLS = os.path.join(ARGUS, "kchem", "tools")
for _p in (KCE_TOOLS, KSHIP_TOOLS, KCHEM_TOOLS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from kce_lib import atomic_write, json_for_html, latest_quarter, num_of, q_next, q_of, q_range, report_kind  # noqa: E402,F401
from kce_fetch import fetch_section, find_sections, pick_report, search_reports, toc            # noqa: E402,F401
from kce_parse import parse_tables                                                                 # noqa: E402,F401
from kship_lib import TABLE_JS                                                                     # noqa: E402,F401

E = html.escape


# ── 파일 ───────────────────────────────────────────────────

def load_asset(name, default=None):
    path = os.path.join(ASSETS, name)
    if not os.path.isfile(path):
        if default is not None:
            return default
        raise FileNotFoundError(path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(data):
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def write_asset(name, data):
    path = os.path.join(ASSETS, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write(path, dump_json(data))


def cache_path(stock, name):
    return os.path.join(CACHE, stock, name)


def read_cache(stock, name):
    p = cache_path(stock, name)
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return f.read()
    return None


def write_cache(stock, name, text):
    p = cache_path(stock, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    atomic_write(p, text)


# ── 분기·기간 ─────────────────────────────────────────────

def quarter_end(q):
    y, n = int(q[:4]), int(q[5])
    m = n * 3
    return datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)


def quarter_months(q):
    """보고서가 커버하는 누적 개월: Q1 3 · Q2(반기) 6 · Q3 9 · Q4(사업) 12."""
    return int(q[5]) * 3


def search_window(q):
    """정기보고서 검색 창 — 분기말 다음 달 1일부터 분기말 + 150일."""
    end = quarter_end(q)
    start = end + datetime.timedelta(days=1)
    return start.strftime("%Y%m%d"), (end + datetime.timedelta(days=150)).strftime("%Y%m%d")


def q_prev(q):
    y, n = int(q[:4]), int(q[5])
    return "%dQ%d" % ((y - 1, 4) if n == 1 else (y, n - 1))


# ── 숫자·단위 ─────────────────────────────────────────────

_NUM = re.compile(r"[-−(]?\s*\d[\d,]*(?:\.\d+)?\s*\)?")


def to_float(s):
    """'1,760,500' · '70.63%' · '(12.3)' · '-' → float 또는 None."""
    if s is None:
        return None
    t = str(s).strip().replace("−", "-").replace("%", "").replace("，", ",")
    if t in ("", "-", "—", "–", "n/a", "N/A", "해당없음", "해당 없음"):
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").replace(",", "").strip()
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


UNIT_TON = {"톤": 1.0, "ton": 1.0, "tons": 1.0, "t": 1.0, "mt": 1.0, "m/t": 1.0, "톤/년": 1.0, "ton/년": 1.0, "ton/year": 1.0, "ton/yr": 1.0,
            "mt/년": 1.0, "mt/y": 1.0, "천톤": 1000.0, "천 톤": 1000.0, "천ton": 1000.0, "천톤/년": 1000.0, "kt": 1000.0, "kta": 1000.0,
            "ktpa": 1000.0, "kt/년": 1000.0, "만톤": 10000.0, "만톤/년": 10000.0, "백만톤": 1e6}


# 숫자·한글 접두(1,000MT · 천MT · 만톤 · 1,000kg)와 연간 접미(/년·/yr)를 일반화 — UNIT_TON 에 없는 조합용
_TON_PREFIX = {"": 1.0, "천": 1e3, "1000": 1e3, "1,000": 1e3, "k": 1e3, "만": 1e4, "10000": 1e4, "10,000": 1e4,
               "백만": 1e6, "1000000": 1e6, "1,000,000": 1e6, "m": None}
_TON_RX = re.compile(r"^(천|만|백만|1,?000,?000|10,?000|1,?000|k)?(톤|tons?|t|mt|m/t|kgs?)(/년|/연|/y|/yr|/year|/a|pa|a)?$")


def ton_mul_of(key):
    """정규화한 단위 낱말('1,000mt', '천mt', '톤/년') → 톤 배수. 톤 계열이 아니면 None."""
    if key in UNIT_TON:
        return UNIT_TON[key]
    m = _TON_RX.match(key)
    if not m:
        return None
    pre, base = m.group(1) or "", m.group(2)
    mul = _TON_PREFIX.get(pre)
    if mul is None:
        return None
    if base.startswith("kg"):
        mul *= 1e-3                      # 1,000kg = 1톤(대한화섬)
        if pre == "":
            return None                  # 'kg' 하나만은 톤 단위 표가 아니다
    return mul


def unit_of(text):
    """캡션 '(단위 : 천톤)' → ('천톤', 1000.0). 톤 계열이 아니면 (원문, None)."""
    m = re.search(r"\(\s*단위\s*[:：]\s*([^)\n]*)\)?", text or "")
    raw = (m.group(1) if m else "").strip()
    if not raw:
        return "", None
    first = re.split(r"(?<!\d),|,(?!\d{3})|，|\|", raw)[0].strip()    # '톤, 매' → '톤' / '이차전지소재 톤 | 화학 톤' → 첫 항목 ('M/T'·'톤/년'·'1,000MT' 의 천단위 쉼표는 자르지 않는다)
    key = re.sub(r"\s+", "", first.lower())
    key = re.sub(r"^[가-힣a-z]+\(", "", key)                     # '수량(1,000kg' → '1,000kg'
    key = re.sub(r"^[가-힣a-z]+?(?=톤$|ton$)", "", key) if key.endswith(("톤", "ton")) and key not in UNIT_TON and ton_mul_of(key) is None else key
    return raw, ton_mul_of(key)


# ── 페이지 셸 (kship_lib.page 복사 — CSS 경로·꼬리말만 kcap) ─────

def _rel(depth):
    return "../" * depth


FOOTER = ("출처 DART 정기보고서(II. 사업의 내용 — 원재료 및 생산설비)·거래소 수시공시(신규시설투자등·생산중단·영업정지)·"
          "KRX KIND 상장법인목록 · 스프레드는 ARGUS 원장(argus/kchem 레지스트리, 역산 추정). 단위 톤/년(연환산)·억원. "
          "추정은 전부 '추정' 표시. 참고용 · 투자조언 아님.")


def page(title, body, depth=0, head_extra="", scripts=(), h1=None, crumbs=(), tags=(), nav=(), lead=""):
    r = _rel(depth)
    tagh = "".join('<span class="tag">%s</span>' % E(t) for t in tags if t)
    navh = "".join('<a href="%s"%s>%s</a>' % (E(href), (' target="_blank" rel="noopener noreferrer"' if href.startswith("http") else ""), E(label))
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
            "<title>%s</title>\n<link rel=\"stylesheet\" href=\"%sassets/kcap.css\">\n%s</head>\n"
            "<body>\n<header class=\"top\"><div class=\"hd\"><h1>%s</h1>%s<span class=\"sp\">%s</span></div>%s</header>\n%s"
            "<main>%s%s</main>\n"
            "<footer>%s</footer>\n</body></html>\n"
            % (E(title), r, head_extra, E(h1 or title), tagh, navh, crumbh, sh,
               ('<p class="lead">%s</p>' % lead) if lead else "", body, E(FOOTER)))


def fmt(v, digits=0):
    if v is None:
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if digits == 0:
        return format(round(v), ",d").replace("-", "−")
    return (("%%.%df" % digits) % v).replace("-", "−")


def fmt_kt(v_ton):
    """톤 → 천톤 표기."""
    if v_ton is None:
        return "—"
    return fmt(v_ton / 1000.0, 0 if abs(v_ton) >= 100000 else 1)
