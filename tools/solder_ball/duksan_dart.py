#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""duksan_dart — 덕산하이메탈(077360) 정기보고서 「II. 사업의 내용」 → 솔더볼 묶음 JSON.

솔더볼 묶음(codex_tasks/ensemble_substrate_solder.md)의 sales·supply·price 축 원천이다.
2024 1분기보고서부터 최신 정기보고서까지, 보고서마다 세 절을 읽는다:

| 절 | 뽑는 것 | 출력 키 |
|---|---|---|
| II-2 주요 제품 및 서비스 | 제품별 매출(금액·비중) · 주요 제품 가격변동추이 | product_sales · prices |
| II-3 원재료 및 생산설비 | 주요 원재료 매입·가격변동 · 생산능력·생산실적·가동률 | materials · capacity |
| II-4 매출 및 수주상황 | 매출실적(품목별 · 수출/내수) | sales |

## 원문이 실제로 적는 것 (2024Q1~2026H1 10건 전수 확인, 2026-10-22)

· II-2 「주요제품등의 현황(연결기준)」은 **법인별** 한 줄씩이다 — 덕산하이메탈(주) `솔더볼 外`,
  덕산넵코어스(주) `항법솔루션 外`, 덕산에테르씨티(주) `고압가스용기 外`, 기타(내부거래 제거), 계.
  SB/MSB/CSB/P&F 제품선 분해는 **정기보고서에 없다**(IR 자료에만 있다). 금액 셀은
  `100,342<BR/>(62.93%)` 또는 `126,318<BR/>53.43%` 꼴로 금액과 비중이 한 칸에 들어 있다.
· 「가격변동 추이」·II-3 「원재료」·「생산능력」은 **표 없이 서술만** 있다("정확한 가격 변동을
  책정하기에는 많은 어려움", "대당 생산능력을 정확하게 추정하기는 어렵습니다"). 표가 없으면
  지어내지 않고 그 서술을 `notes` 에 인용으로 남긴다.
· II-3 「생산실적」은 법인별 **제조원가 금액(백만원)**, 「가동률」은 법인별 가동가능/실제 시간과 %.
· II-4 「매출실적」은 법인별 × 수출/내수/합계(천원) — 덕산하이메탈(주) 줄이 IR 의 별도 매출과 일치한다.

## 네트워크 (DART 규칙 — 반드시 지킨다)

dart.fss.or.kr 는 **공인 IP 단위**로 막는다. 요청은 `argus/kce/tools/kce_fetch._get`(allowlist·
페이싱·프로세스 간 게이트) 위의 `argus/ksemi/tools/ksemi_fetch`(검색·목차·절·디코딩)만 쓰고,
**한 프로세스에서 순차**로만 보낸다 — `kce_fetch.parallel` 을 쓰지 않는다. 뷰어 페이지는 공개라
API 키가 필요 없다(찾지도 않는다). 보고서 하나당 요청은 검색 1~3 + 목차 1 + 절 3 이고, 절 원문은
`cache/sec_<rcpNo>_<key>.html` 에 그대로 남겨 다시 받지 않는다. 출력 JSON 에 이미 있는 보고서는
`--refresh` 가 없으면 검색조차 하지 않는다(캐시 원문이 있으면 다시 파싱만 한다).

## 범위(scope) — 연결·별도를 섞지 않는다

연결 실체에는 덕산넵코어스(방산)·덕산에테르씨티(가스용기)가 들어 있어, 행마다 범위를 적는다:
`별도` / `연결` / `하이메탈 부문` / 못 읽으면 `미상`. 표 범위는 표 앞 문맥(lead)의 표지와 단위 캡션으로,
표지가 없으면 행 라벨에 자회사 품목이 섞였는지로만 정한다. 연결 표 안의 `덕산하이메탈(주)` 줄은
`하이메탈 부문`(내부거래 제거 전 부문값 — IR 별도 매출과 같은 값)으로 따로 적는다. 다른 범위를 더하지 않는다.

## 단위 — fail-closed

금액(product_sales)은 표 캡션·열 캡션(`ksemi_parse.unit_of`)으로 백만원으로 환산한다. 단위를
어디서도 못 읽으면 **원문 셀 문자열을 그대로** 두고 `unit_seen=false` 로 표시한다(조용히 1.0 배 금지).
가격·원재료·생산실적·가동률 표는 환산하지 않고 캡션 단위 문자열(`백만원`, `시간`, `원/kg` …)을 그대로 적는다.

사용:
    python3 tools/solder_ball/duksan_dart.py --root .            # 수집·파싱·기록
    python3 tools/solder_ball/duksan_dart.py --root . --refresh  # 이미 있는 보고서도 재검색·재수집
    python3 tools/solder_ball/duksan_dart.py --root . --dump     # 캐시 원문의 표 목록만 보여 준다(무접속)

규약(AGENTS.md): stdlib 전용 · fail-closed(product_sales 0행이면 쓰지 않고 비정상 종료) ·
원자적 쓰기 · 정규화 JSON(sort_keys·indent=1·개행 고정) · 테스트는 tests/ 에 fixture 기반.
"""
import argparse
import html as _htmlmod
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))              # tools/solder_ball
REPO = os.path.dirname(os.path.dirname(HERE))                  # 레포 루트(코드 위치 기준)

for _p in (os.path.join(REPO, "argus", "kce", "tools"),
           os.path.join(REPO, "argus", "ksemi", "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ksemi_parse as P                                        # noqa: E402
from ksemi_fetch import search_reports, toc, fetch_section     # noqa: E402  (테스트가 바꿔 끼운다)
from kce_fetch import pick_report                              # noqa: E402
from kce_lib import atomic_write, norm_col, num_of, q_range, report_kind   # noqa: E402
from kce_parse import parse_tables, _UNIT_RE                   # noqa: E402
from report_refresh import window, candidates, latest_candidate            # noqa: E402

STOCK = "077360"
NAME = "덕산하이메탈"
FIRST_QUARTER = "2024Q1"
REL_OUT = os.path.join("data", "solder_ball", "077360.json")
REL_CACHE = os.path.join("tools", "solder_ball", "cache")
KINDS = ("A003", "A002", "A001")             # 분기 · 반기 · 사업
KST = timezone(timedelta(hours=9))

# 목차에서 찾을 절 — (키, 제목 부분문자열 묶음들(우선순위), 배제 낱말)
SECTION_SPECS = [
    ("ii2", (("주요 제품", "주요제품", "주요 상품", "주요상품"),), ("가격변동",)),
    ("ii3", (("원재료", "생산설비", "생산 설비"),), ()),
    ("ii4", (("매출 및 수주상황", "매출및수주상황"), ("수주상황",), ("매출실적",)), ()),
]
CHAPTER_KEY = "ii"                           # 하위 절이 목차에 없을 때 장 전체로 폴백
CHAPTER_PATS = ("사업의 내용", "사업의내용")
SECTION_TITLES = {"ii2": "II-2 주요 제품 및 서비스", "ii3": "II-3 원재료 및 생산설비",
                  "ii4": "II-4 매출 및 수주상황"}
ROW_KEYS = ("product_sales", "prices", "materials", "capacity", "sales", "notes")


# ── 기간·보고서 ──────────────────────────────────────────────

def period_of(quarter):
    """'2026Q2' → '2026-H1' (Q1→Q1, Q3→Q3, Q4→FY). 반기·사업보고서 표는 누계다."""
    y, n = quarter[:4], quarter[5]
    return "%s-%s" % (y, {"1": "Q1", "2": "H1", "3": "Q3", "4": "FY"}[n])


def filed_of(rcp_no):
    """접수번호 앞 8자리 = 접수일."""
    return "%s-%s-%s" % (rcp_no[:4], rcp_no[4:6], rcp_no[6:8])


def find_report(quarter):
    """그 분기 정기보고서 후보를 **적합한 순서로**. 없으면 [](미공시 — 추정하지 않는다).

    종목코드는 DART 검색의 정확일치 키다(kce_probe 와 같다). 기대 종류(분기/반기/사업)부터 두드리고
    비면 나머지 종류를 본다(ksemi_lib.find_periodic 과 같은 이유 — 결산월이 다른 회사 대비). 제목의
    기준월이 분기말과 맞는 것만 남기고(candidates), 원본 → [첨부정정] 순으로 정렬한다(pick_report).
    """
    start, end = window(quarter)
    want = report_kind(quarter)
    for kind in (want,) + tuple(k for k in KINDS if k != want):
        reps = candidates(search_reports(STOCK, start, end, kind), quarter)
        if reps:
            return pick_report(reps, quarter)
    return []


def pick_nodes(nodes):
    """목차 노드 → {key: node}. 절마다 첫 후보 하나(우선순위 묶음 순). 장 노드는 CHAPTER_KEY 로."""
    out = {}
    for key, groups, exclude in SECTION_SPECS:
        for pats in groups:
            for n in nodes:
                t = n.get("text") or ""
                if any(p in t for p in pats) and not any(x in t for x in exclude):
                    out[key] = n
                    break
            if key in out:
                break
    for n in nodes:
        t = n.get("text") or ""
        if any(p in t for p in CHAPTER_PATS):
            out[CHAPTER_KEY] = n
            break
    return out


# ── 캐시 ─────────────────────────────────────────────────────

class Cache(object):
    """절 원문 HTML + 조회 색인(어느 분기가 어느 rcpNo·노드였나). 실패는 캐시하지 않는다."""

    def __init__(self, root):
        self.dir = os.path.join(root, REL_CACHE)
        self.index_path = os.path.join(self.dir, "reports_index.json")
        self.index = {}
        if os.path.exists(self.index_path):
            with open(self.index_path, encoding="utf-8") as f:
                self.index = json.load(f)

    def section_path(self, rcp, key):
        return os.path.join(self.dir, "sec_%s_%s.html" % (rcp, key))

    def read_section(self, rcp, key):
        p = self.section_path(rcp, key)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return f.read()
        return None

    def write_section(self, rcp, key, html):
        os.makedirs(self.dir, exist_ok=True)
        atomic_write(self.section_path(rcp, key), html)

    def save_index(self):
        os.makedirs(self.dir, exist_ok=True)
        atomic_write(self.index_path, json.dumps(self.index, ensure_ascii=False,
                                                 indent=1, sort_keys=True) + "\n")


def section_html(cache, node, key, fetched):
    """절 HTML(캐시 우선). 새로 받으면 fetched 카운터를 올린다. 200바이트 미만은 실패로 본다."""
    h = cache.read_section(node["rcpNo"], key)
    if h is not None:
        return h
    h = fetch_section(node)
    if not h or len(h) < 200:
        raise RuntimeError("절 HTML이 %d바이트 — 받지 못했다 (%s %s)" % (len(h or ""), node["rcpNo"], key))
    cache.write_section(node["rcpNo"], key, h)
    fetched[0] += 1
    return h


# ── 표 공통 ──────────────────────────────────────────────────

_SUBSIDIARY_WORDS = ("넵코어스", "에테르씨티", "방산", "가스용기", "항재밍", "항법")
_PARENT_RX = re.compile(r"덕산하이메탈")
_SCOPE_RULES = (
    ("연결", re.compile(r"연결\s*(?:기준|재무제표|회사|실체|대상)?|[\[(（]\s*연결\s*[\])）]")),
    ("별도", re.compile(r"별도\s*(?:기준|재무제표)?|[\[(（]\s*별도\s*[\])）]|개별\s*(?:기준|재무제표)")),
    ("하이메탈 부문", re.compile(r"하이메탈\s*(?:부문|사업부문|사업부|단독)|반도체\s*소재\s*(?:부문|사업부문|사업)"
                                 r"|솔더볼\s*(?:부문|사업부문|사업)")),
)
_SUM_WORDS = ("합계", "합 계", "총계", "총 계", "소계", "계")
_NUMERIC_HDR = re.compile(r"매출|금액|비율|비중|가격|단가|능력|실적|시간|가동|수량|매입|제\s*\d+\s*기|당기|전기|(?:19|20)\d{2}")
_LABEL_HDR = re.compile(r"품\s*목|제품|구\s*분|용도|상표|부문|유형|사업소|비\s*고|회사")
# 금액과 비중이 한 칸: `100,342 (62.93%)` · `126,318<BR/>53.43%`(→ `126,31853.43%`) · `(122)(-0.19%)`
_MIX_CELL = re.compile(
    r"^\s*(?:(\(?-?[\d,]+(?:\.\d+)?\)?)\s*[\(（]\s*(-?\d+(?:\.\d+)?)\s*%?\s*[\)）]"
    r"|(\(?-?\d{1,3}(?:,\d{3})*\)?)\s*(-?\d+(?:\.\d+)?)\s*%)\s*$")
_PCT_CELL = re.compile(r"^\s*\(?-?[\d,]+(?:\.\d+)?\)?\s*%\s*$")
_HDR_VOCAB = re.compile(r"품\s*목|구\s*분|매\s*출|비\s*율|비\s*중|금\s*액|수\s*량|가격|단가|제\s*\d+\s*기|당기|전기|당\s*반기"
                        r"|수\s*출|내\s*수|합\s*계|단위|부문|유형|용도|상표|비\s*고|가동|시간|능력|실적|기간|회사")


def lead_tail(lead, n=260):
    return P._txt(lead)[-n:]


def split_mix(cell):
    """'100,342 (62.93%)' → ('100,342', 62.93). 섞인 칸이 아니면 (원문, None)."""
    t = P._txt(cell)
    m = _MIX_CELL.match(t)
    if not m:
        return t, None
    amt = m.group(1) or m.group(3)
    share = num_of(m.group(2) or m.group(4))
    return amt, share


def is_header_row(cells):
    """머리행의 이어지는 줄인가 — **숫자·섞인 칸이 하나라도 있으면 아니다**, 어휘가 절반 이상이어야 한다.

    `ksemi_parse.is_header_row` 는 숫자가 없으면 머리행 어휘 하나로 머리행으로 보는데, 덕산 II-2 표의
    데이터 행은 금액이 `100,342<BR/>(62.93%)` 로 섞여 있어 `num_of` 가 None 이고 `제품 등` 에 '제품'이
    걸린다 — 법인 네 줄이 머리행으로 흡수돼 열 이름이 `사업부문 덕산하이메탈(주) 덕산에스지(주) …` 가
    됐다(2026-10-22 실측, 10건 중 8건). 그래서 여기서는 섞인 칸을 숫자로 보고 어휘 비율을 요구한다.
    """
    vals = [P._txt(c) for c in cells if P._txt(c)]
    if not vals:
        return False
    if any(num_of(v) is not None or _MIX_CELL.match(v) or _PCT_CELL.match(v) for v in vals):
        return False
    hits = sum(1 for v in vals if _HDR_VOCAB.search(v))
    return hits * 2 >= len(vals)


def resolve(t):
    """parse_tables 한 장 → (cols, rows). cols 가 비면 첫 행을 올리고, 이어지는 머리행만 세로로 합친다."""
    cols = [P._txt(c) for c in (t.get("cols") or [])]
    rows = [[P._txt(c) for c in r] for r in (t.get("rows") or [])]
    if not cols and rows:
        cols = rows.pop(0)
    while rows and len(rows) > 1 and is_header_row(rows[0]):
        head = rows.pop(0)
        n = max(len(cols), len(head))
        merged = []
        for i in range(n):
            parts, uniq = [x for x in ((cols[i] if i < len(cols) else ""), (head[i] if i < len(head) else "")) if x], []
            for p in parts:
                if norm_col(p) not in [norm_col(u) for u in uniq]:
                    uniq.append(p)
            merged.append(" ".join(uniq).strip())
        cols = merged
    return cols, rows


def tables(html):
    for t in parse_tables(html):
        cols, rows = resolve(t)
        if not rows or len(cols) < 2:
            continue
        yield t, cols, rows


def table_scope(lead, row_labels=()):
    """표 범위 — lead 꼬리의 **가장 뒤** 표지가 이 표의 것이다(앞 표지는 앞 표의 것일 수 있다).

    표지가 없고 행 라벨에 자회사 품목(넵코어스·에테르씨티·방산·가스용기)이 섞였으면 연결로 본다.
    그 밖에는 `미상` — 추정하지 않는다.
    """
    tail = lead_tail(lead)
    hits = []
    for name, rx in _SCOPE_RULES:
        for m in rx.finditer(tail):
            hits.append((m.end(), name))
    if hits:
        return max(hits)[1]
    joined = " ".join(row_labels)
    if any(w in joined for w in _SUBSIDIARY_WORDS):
        return "연결"
    return "미상"


_NOT_HIMETAL = _SUBSIDIARY_WORDS + ("MYANMAR", "에스지", "시리우스", "연결조정", "내부거래")


def is_himetal_row(labels, total=False):
    """덕산하이메탈(주) 법인 줄인가 — 합계·자회사·조정 낱말이 하나라도 있으면 아니다."""
    joined = " ".join(x or "" for x in labels)
    return (not total and bool(_PARENT_RX.search(joined))
            and not any(w in joined for w in _NOT_HIMETAL))


def row_scope(tscope, labels, total=False):
    """연결 표 안의 덕산하이메탈(주) 줄은 `하이메탈 부문`(부문값·내부거래 제거 전). 합계 줄은 표 범위 그대로.

    표 범위가 lead 서술 때문에 `하이메탈 부문` 으로 잡혀도 행이 하이메탈 법인 줄이 아니면(자회사·합계)
    `미상` 으로 내린다 — 표 하나를 통째로 부문값으로 오인하지 않게.
    """
    if tscope in ("연결", "미상", "하이메탈 부문") and is_himetal_row(labels, total):
        return "하이메탈 부문"
    if tscope == "하이메탈 부문":
        return "미상"
    return tscope


# 과거 호환 별칭(테스트·외부 호출)
scope_of = table_scope


def unit_raw(lead, cols=()):
    """'(단위 : 원/kg)' → '원/kg'. lead 꼬리 → 열 이름 순. 없으면 None."""
    m = _UNIT_RE.findall(P._txt(lead))
    if m:
        return m[-1].strip().rstrip(",")
    for c in cols:
        m = _UNIT_RE.findall(c or "")
        if m:
            return m[-1].strip().rstrip(",")
    return None


def is_total_label(s):
    return norm_col(s) in [norm_col(w) for w in _SUM_WORDS]


def numeric_cols(cols, rows):
    """값 열 = 머리행이 값 어휘(라벨 어휘 제외)이거나, 비어 있지 않은 셀의 절반 이상이 숫자인 열."""
    out = []
    for i, c in enumerate(cols):
        vals = [P._txt(r[i]) for r in rows if i < len(r) and P._txt(r[i]) and P._txt(r[i]) not in ("-", "–", "—")]
        nnum = sum(1 for v in vals if num_of(v) is not None or _MIX_CELL.match(v) or _PCT_CELL.match(v))
        by_hdr = bool(_NUMERIC_HDR.search(c or "")) and not _LABEL_HDR.search(c or "")
        if by_hdr or (vals and nnum * 2 >= len(vals)):
            out.append(i)
    return out


def label_cells(row, idx):
    """라벨 셀들(중복 제거 — 병합 셀 전개로 같은 글자가 반복된다)."""
    out = []
    for i in idx:
        v = P._txt(row[i]) if i < len(row) else ""
        if v and v not in out:
            out.append(v)
    return out


def cell_value(v):
    """셀 → 숫자(num_of) 또는 원문 문자열. 빈 칸·'-' 는 None."""
    t = P._txt(v)
    if not t or t in ("-", "–", "—"):
        return None
    x = num_of(t)
    return x if x is not None else t


def classify(lead, cols, kinds):
    """lead 꼬리에서 **가장 뒤에** 나오는 절 낱말로 표 종류를 정한다. 없으면 열 이름으로 폴백."""
    tail = lead_tail(lead)
    hits = [(tail.rfind(w), k) for w, k in kinds if tail.rfind(w) >= 0]
    if hits:
        return max(hits)[1]
    joined = " ".join(cols)
    for w, k in kinds:
        if w in joined:
            return k
    return None


def section_text(html):
    """절 HTML → 공백 접은 본문(표 포함). 서술만 있는 절의 인용에 쓴다."""
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return P._txt(_htmlmod.unescape(s))


_ENTITY_TAG = "[덕산하이메탈(주)]"
# 다음 소제목 — ' (2) ' · ' 나. ' · ' 2) '. 공백을 앞뒤로 요구해 본문의 '주1)' 같은 각주 표기에는 걸리지 않게 한다.
_SUBHEAD = re.compile(r"\s(?:\(\d\)|[가-하]\.|\d\))\s")


def narrative(text, headings, n=320):
    """표가 없는 소절의 서술 인용 — 소제목부터 **다음 소제목 전까지**만 본다.

    그 안에 `[덕산하이메탈(주)]` 문단이 있으면 그 문단(다음 법인 괄호 전까지), 없으면 소제목 바로 뒤 서술.
    범위를 다음 소제목에서 끊지 않으면 「생산능력 및 산출근거」 인용이 뒤의 「다. 생산설비의 현황」 문단을
    집어 온다(2026-10-22 실측).
    """
    for h in headings:
        i = text.find(h)
        if i < 0:
            continue
        seg = text[i + len(h):i + 2000]
        m = _SUBHEAD.search(seg)
        if m:
            seg = seg[:m.start()]
        j = seg.find(_ENTITY_TAG)
        q = seg[j + len(_ENTITY_TAG):] if j >= 0 else seg
        e = q.find("[")
        if e > 0:
            q = q[:e]
        q = q.strip(" :.-")
        if q:
            return q[:n]
    return None


# ── II-2 주요 제품 및 서비스 ─────────────────────────────────

_II2_KINDS = (("가격변동", "price"), ("가격 변동", "price"), ("판매가격", "price"), ("가격추이", "price"),
              ("매출", "product_sales"), ("제품", "product_sales"))
_AMT_HDR = re.compile(r"매출액|매\s*출|금\s*액|실적")
_SHARE_HDR = re.compile(r"비\s*율|비\s*중|%")
_PRODUCT_HDR = re.compile(r"품\s*목|제품명|제\s*품|상품")
_ENTITY_HDR = re.compile(r"사업\s*부문|부\s*문|회사|법인|구\s*분")
_NOTE_HDR = re.compile(r"비\s*고|용도|상표|유형")


def product_sales(html, period, rcp, section="II-2"):
    """II-2 「제품별 매출」 표 → product_sales 행. 금액은 백만원(단위 미확인이면 원문 문자열·unit_seen=false)."""
    out = []
    for t, cols, rows in tables(html):
        lead = P._txt(t.get("lead"))
        if classify(lead, cols, _II2_KINDS) != "product_sales":
            continue
        amt_idx = [i for i, c in enumerate(cols) if _AMT_HDR.search(c) and not _SHARE_HDR.search(c) and not _LABEL_HDR.search(c)]
        mix_idx = [i for i, c in enumerate(cols) if _AMT_HDR.search(c) and _SHARE_HDR.search(c)]
        share_idx = [i for i, c in enumerate(cols) if _SHARE_HDR.search(c) and not _AMT_HDR.search(c)]
        if not amt_idx and not mix_idx:
            amt_idx = [i for i, c in enumerate(cols) if P._PERIOD.search(c)]
        if not amt_idx and not mix_idx:
            continue
        unit = P.unit_of(t, cols)
        value_idx = set(amt_idx) | set(mix_idx) | set(share_idx) | set(numeric_cols(cols, rows))
        label_idx = [i for i in range(len(cols)) if i not in value_idx and not _NOTE_HDR.search(cols[i])]
        prod_idx = [i for i in label_idx if _PRODUCT_HDR.search(cols[i])]
        ent_idx = [i for i in label_idx if _ENTITY_HDR.search(cols[i]) and i not in prod_idx]
        tscope = table_scope(lead, [" ".join(label_cells(r, label_idx)) for r in rows])
        ai = (amt_idx or mix_idx)[0]
        for r in rows:
            labels = label_cells(r, label_idx)
            if not labels:
                continue
            raw, share = split_mix(r[ai] if ai < len(r) else "")
            if share is None and share_idx:
                si = share_idx[0]
                share = num_of(P._txt(r[si])) if si < len(r) else None
            if share is None and mix_idx and ai not in mix_idx:
                mi = mix_idx[0]
                share = split_mix(r[mi] if mi < len(r) else "")[1]
            amount = P._money(raw, ai, unit)
            seen = amount is not None
            if amount is None and num_of(raw) is not None:
                amount = raw                      # 단위를 못 읽었다 — 원문 그대로, 환산하지 않는다
            if amount is None and share is None:
                continue
            total = any(is_total_label(x) for x in labels)
            product = (P._txt(r[prod_idx[0]]) if prod_idx and prod_idx[0] < len(r) else "") or " / ".join(labels)
            entity = (P._txt(r[ent_idx[0]]) if ent_idx and ent_idx[0] < len(r) else None)
            if total:
                product = labels[0]
            out.append({"period": period, "scope": row_scope(tscope, labels, total), "product": product,
                        "entity": entity, "labels": labels, "amount": amount,
                        "unit": "백만원" if seen else None, "unit_seen": seen, "share_pct": share,
                        "total": total, "col_label": cols[ai], "source_rcp": rcp, "source_section": section,
                        "table_lead": lead_tail(lead, 160)})
    return out


_FOOTNOTE_RX = re.compile(r"^\s*(?:※|주\s*\d+\s*\))")


def value_table_rows(html, period, rcp, kinds, want, kind_label):
    """'품목 × 기간(또는 값 열)' 표 → [{period,scope,item,unit,unit_seen,values,…}] (환산 없음)."""
    out = []
    for t, cols, rows in tables(html):
        lead = P._txt(t.get("lead"))
        if classify(lead, cols, kinds) != want:
            continue
        vidx = numeric_cols(cols, rows)
        if not vidx:
            continue
        label_idx = [i for i in range(len(cols)) if i not in vidx and not re.search(r"비\s*고", cols[i])]
        if not label_idx:
            label_idx = [0]
            vidx = [i for i in vidx if i != 0]
        unit = unit_raw(lead, cols)
        tscope = table_scope(lead, [" ".join(label_cells(r, label_idx)) for r in rows])
        for r in rows:
            labels = label_cells(r, label_idx)
            if labels and _FOOTNOTE_RX.match(labels[0]):
                continue                          # ※·주1) 각주 줄 — 값이 아니다
            vals = {}
            for i in vidx:
                v = cell_value(r[i] if i < len(r) else "")
                if v is None:
                    continue
                vals[cols[i] or "col%d" % i] = v if unit is not None else P._txt(r[i])
            if not labels or not vals:
                continue
            total = any(is_total_label(x) for x in labels)
            c0 = vidx[0]                          # 첫 값 열 = 당기(공시 관례). 비었으면 None — 전기 값으로 대신하지 않는다
            cur = cell_value(r[c0] if c0 < len(r) else "")
            out.append({"period": period, "scope": row_scope(tscope, labels, total), "item": " / ".join(labels),
                        "kind": kind_label, "unit": unit, "unit_seen": unit is not None, "values": vals,
                        "current_col": cols[c0] or "col%d" % c0, "current": cur if unit is not None else (P._txt(r[c0]) if cur is not None else None),
                        "total": total, "source_rcp": rcp, "table_lead": lead_tail(lead, 160)})
    return out


def prices(html, period, rcp):
    return value_table_rows(html, period, rcp, _II2_KINDS, "price", "제품가격")


# ── II-3 원재료 및 생산설비 ─────────────────────────────────

_II3_KINDS = (("가동률", "util"), ("가동율", "util"), ("생산실적", "output"), ("생산 실적", "output"),
              ("생산능력", "capacity"), ("생산 능력", "capacity"),
              ("가격변동", "mat_price"), ("가격 변동", "mat_price"), ("매입", "mat_purchase"),
              ("원재료", "mat_purchase"))


def materials(html, period, rcp):
    rows = value_table_rows(html, period, rcp, _II3_KINDS, "mat_purchase", "원재료매입")
    rows += value_table_rows(html, period, rcp, _II3_KINDS, "mat_price", "원재료가격")
    return rows


def capacity(html, period, rcp):
    """생산능력·생산실적·가동률 표 → 품목(법인)별 한 행. 같은 (범위, 품목) 끼리만 합친다."""
    merged, order = {}, []
    basis = "제조원가 금액 기준" if "제조원가" in section_text(html) else None

    def slot(scope, item):
        k = (scope, norm_col(item))
        if k not in merged:
            merged[k] = {"period": period, "scope": scope, "item": item, "capacity": None, "output": None,
                         "output_basis": None, "utilization_pct": None, "unit": None, "unit_seen": False,
                         "col_label": None, "util_detail": None, "source_rcp": rcp, "table_lead": None}
            order.append(k)
        return merged[k]

    for kind in ("capacity", "output"):
        for r in value_table_rows(html, period, rcp, _II3_KINDS, kind, kind):
            col, val = r["current_col"], r["current"]   # 당기 열만 — '-' 면 None(전기 값으로 메우지 않는다)
            if val is None and not r["values"]:
                continue
            s = slot(r["scope"], r["item"])
            s[kind] = val
            if kind == "output":
                s["output_basis"] = basis
            s["unit"] = s["unit"] or r["unit"]
            s["unit_seen"] = s["unit_seen"] or r["unit_seen"]
            s["col_label"] = s["col_label"] or col
            s["table_lead"] = s["table_lead"] or r["table_lead"]
    for r in value_table_rows(html, period, rcp, _II3_KINDS, "util", "util"):
        util, detail = None, {}
        for col, v in r["values"].items():
            if re.search(r"가동률|가동율|비\s*율", col):
                x = num_of(str(v))
                util = x if x is not None else v
            else:
                detail[col] = v
        s = slot(r["scope"], r["item"])
        s["utilization_pct"] = util
        s["util_detail"] = detail or None
        s["table_lead"] = s["table_lead"] or r["table_lead"]
    return [merged[k] for k in order]


# ── II-4 매출 및 수주상황 ───────────────────────────────────

def sales(html, period, rcp):
    """ksemi_parse.sales 를 먼저 쓰고, 표가 하나도 안 걸리면 parse_tables 로 폴백한다."""
    s = P.sales(html)
    out_tables = []
    for tb in s["tables"]:
        lead = tb["lead"]
        tscope = table_scope(lead, [" ".join(r["labels"]) for r in tb["rows"]])
        rows = [{"labels": r["labels"], "channel": r["channel"], "channel_label": r["channel_label"],
                 "total": r["total"], "vals": r["vals"], "scope": row_scope(tscope, r["labels"], r["total"])}
                for r in tb["rows"]]
        out_tables.append({"scope": tscope, "lead": lead_tail(lead, 160), "cols": tb["cols"],
                           "periods": tb["periods"], "unit": tb["unit"]["raw"], "unit_seen": bool(tb["unit"]["seen"]),
                           "unit_scale_to_mn": tb["unit"]["scale"], "amount_unit": "백만원" if tb["unit"]["seen"] else None,
                           "rows": rows, "fallback": False})
    if not out_tables:
        for t, cols, rows in tables(html):
            lead = P._txt(t.get("lead"))
            if "매출" not in lead_tail(lead) and not any("매출" in c for c in cols):
                continue
            vidx = numeric_cols(cols, rows)
            if not vidx:
                continue
            label_idx = [i for i in range(len(cols)) if i not in vidx]
            recs = []
            for r in rows:
                vals = {cols[i]: cell_value(r[i] if i < len(r) else "") for i in vidx}
                vals = {k: v for k, v in vals.items() if v is not None}
                if not vals:
                    continue
                labels = label_cells(r, label_idx)
                kind, ch, chlabel = P._channel([r[i] for i in label_idx if i < len(r)])
                recs.append({"labels": labels, "channel": ch, "channel_label": chlabel,
                             "total": any(is_total_label(x) for x in labels if x != chlabel), "vals": vals})
            if recs:
                tscope = table_scope(lead, [" ".join(r["labels"]) for r in recs])
                for r in recs:
                    r["scope"] = row_scope(tscope, r["labels"], r["total"])
                u = unit_raw(lead, cols)
                out_tables.append({"scope": tscope, "lead": lead_tail(lead, 160), "cols": cols,
                                   "periods": [cols[i] for i in vidx], "unit": u, "unit_seen": u is not None,
                                   "unit_scale_to_mn": None, "amount_unit": u, "rows": recs, "fallback": True})
    # ksemi_parse.sales 의 최상위 export·domestic·total 은 범위 없는 연결 합(연결조정 이중 차감이 있다)이라 싣지 않는다.
    # 하이메탈 부문 값은 tables[].rows 의 scope 로만 읽는다.
    return {"period": period, "source_rcp": rcp, "channel_kind": s["channel_kind"], "period_label": s["period_label"],
            "unit_seen": bool(s["unit_seen"]), "tables": out_tables}


def product_sales_from_ii4(sales_rec):
    """II-2 가 비었을 때 II-4 매출실적의 품목 행(합계·수출/내수 분해 제외)으로 product_sales 를 만든다."""
    out = []
    for tb in sales_rec["tables"]:
        if not tb["periods"]:
            continue
        p = tb["periods"][0]
        for r in tb["rows"]:
            if r["total"] or r["channel"] in ("exp", "dom"):
                continue
            v = r["vals"].get(p)
            if v is None:
                continue
            seen = bool(tb["unit_seen"]) and not tb["fallback"]
            labels = [x for x in r["labels"] if x != r["channel_label"]]
            out.append({"period": sales_rec["period"], "scope": r["scope"], "product": labels[-1] if labels else "미상",
                        "entity": labels[0] if len(labels) > 1 else None, "labels": labels,
                        "amount": v, "unit": "백만원" if seen else None, "unit_seen": seen, "share_pct": None,
                        "total": False, "col_label": p, "source_rcp": sales_rec["source_rcp"],
                        "source_section": "II-4", "table_lead": tb["lead"]})
    return out


# ── 보고서 한 건 ─────────────────────────────────────────────

# 표가 없을 때 서술을 인용할 소절 — (절 키, notes.kind, 소제목 후보)
NOTE_SPECS = (
    ("ii2", "가격변동추이", ("가격변동 추이", "가격변동추이", "가격 변동 추이", "가격변동")),
    ("ii3", "원재료", ("가. 원재료", "원재료 및 생산설비", "원재료")),
    ("ii3", "생산능력", ("생산능력 및 산출근거", "생산능력의 산출근거", "생산능력")),
)


def parse_report(htmls, period, rcp):
    """{key: html} → 이 보고서 몫의 행들. 비어 있는 절은 issues 로 남긴다."""
    res = {k: [] for k in ROW_KEYS}
    res.update({"issues": [], "sections": []})
    h2 = htmls.get("ii2") or htmls.get(CHAPTER_KEY)
    h3 = htmls.get("ii3") or htmls.get(CHAPTER_KEY)
    h4 = htmls.get("ii4") or htmls.get(CHAPTER_KEY)
    if h2:
        res["product_sales"] = product_sales(h2, period, rcp)
        res["prices"] = prices(h2, period, rcp)
        if res["product_sales"] or res["prices"]:
            res["sections"].append("ii2")
    if h3:
        res["materials"] = materials(h3, period, rcp)
        res["capacity"] = capacity(h3, period, rcp)
        if res["materials"] or res["capacity"]:
            res["sections"].append("ii3")
    if h4:
        s = sales(h4, period, rcp)
        if s["tables"]:
            res["sales"] = [s]
            res["sections"].append("ii4")
            if not res["product_sales"]:
                res["product_sales"] = product_sales_from_ii4(s)
                if res["product_sales"]:
                    res["issues"].append("%s %s: II-2 제품별 매출 표를 못 읽어 II-4 매출실적 품목 행으로 대신함" % (period, rcp))
    # 표 없는 소절의 서술 인용 — 가격변동(II-2)·원재료·생산능력(II-3). 표가 있으면 인용하지 않는다.
    texts = {"ii2": section_text(h2) if h2 else "", "ii3": section_text(h3) if h3 else ""}
    for key, kind, heads in NOTE_SPECS:
        has_table = {"가격변동추이": bool(res["prices"]),
                     "원재료": any(r["kind"] == "원재료매입" or r["kind"] == "원재료가격" for r in res["materials"]),
                     "생산능력": any(r["capacity"] is not None for r in res["capacity"])}[kind]
        if has_table or not texts[key]:
            continue
        q = narrative(texts[key], heads)
        if q:
            res["notes"].append({"period": period, "source_rcp": rcp, "section": SECTION_TITLES[key],
                                 "kind": kind, "quote": q, "table": False})
    for key in ("ii2", "ii3", "ii4"):
        if not (htmls.get(key) or htmls.get(CHAPTER_KEY)):
            res["issues"].append("%s %s: %s 절이 목차에 없음" % (period, rcp, SECTION_TITLES[key]))
        elif key not in res["sections"]:
            res["issues"].append("%s %s: %s 절에서 표를 하나도 못 읽음" % (period, rcp, SECTION_TITLES[key]))
    if not res["sections"]:
        res["issues"].append("%s %s: 세 절 모두 빈 결과 — 기록하지 않음(지어내지 않는다)" % (period, rcp))
    return res


def collect_report(quarter, cache, fetched, log):
    """분기 → (meta, htmls). 후보 보고서를 순서대로 열어 세 절 중 하나라도 있는 첫 문서를 쓴다."""
    reps = find_report(quarter)
    if not reps:
        return None, {}
    tried = []
    for rcp, title in reps[:4]:
        nodes = toc(rcp)
        picked = pick_nodes(nodes)
        if not any(k in picked for k in ("ii2", "ii3", "ii4", CHAPTER_KEY)):
            tried.append("%s(목차에 II절 없음)" % rcp)
            continue
        htmls = {}
        for key in ("ii2", "ii3", "ii4"):
            if key in picked:
                htmls[key] = section_html(cache, picked[key], key, fetched)
        if len(htmls) < 3 and CHAPTER_KEY in picked:
            htmls[CHAPTER_KEY] = section_html(cache, picked[CHAPTER_KEY], CHAPTER_KEY, fetched)
        meta = {"rcp_no": rcp, "title": title, "period": period_of(quarter), "filed": filed_of(rcp),
                "sections_in_toc": sorted(k for k in picked if k != CHAPTER_KEY),
                "chapter_fallback": CHAPTER_KEY in htmls}
        cache.index[quarter] = {"rcp_no": rcp, "title": title, "nodes": picked,
                                "checked_on": datetime.now(KST).date().isoformat()}
        log("  %s %s %s 절=%s" % (quarter, rcp, title, ",".join(sorted(htmls))))
        return meta, htmls
    raise RuntimeError("%s: 후보 보고서에 II절이 없음 (%s)" % (quarter, "; ".join(tried)))


# ── 조립·기록 ────────────────────────────────────────────────

def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dumps(data):
    return json.dumps(data, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def same_content(a, b):
    """generated 만 다른 두 결과는 같은 데이터다 — 매주 타임스탬프만 바뀐 커밋을 만들지 않는다."""
    if a is None or b is None:
        return False
    ka = {k: v for k, v in a.items() if k != "generated" and not k.startswith("_")}
    kb = {k: v for k, v in b.items() if k != "generated" and not k.startswith("_")}
    return dumps(ka) == dumps(kb)


def quarters_to_scan(today=None):
    return q_range(FIRST_QUARTER, latest_candidate(today))


def _append(data, res):
    for k in ROW_KEYS:
        data[k].extend(res[k])


def build(root, refresh=False, log=None, today=None, quarters=None):
    """수집·파싱 → (data, fetched_count, prev). 네트워크는 여기서만, **순차로만** 일어난다."""
    log = log or (lambda s: sys.stderr.write(s + "\n"))
    out_path = os.path.join(root, REL_OUT)
    prev = load_json(out_path)
    prev_by_period = {}
    for r in (prev or {}).get("reports", []):
        prev_by_period.setdefault(r.get("period"), r)
    prev_rows = {k: {} for k in ROW_KEYS}
    for k in ROW_KEYS:
        for row in (prev or {}).get(k, []):
            prev_rows[k].setdefault(row.get("source_rcp"), []).append(row)
    cache = Cache(root)
    fetched = [0]
    data = {"company": {"stock": STOCK, "name": NAME}, "reports": [], "issues": [], "_failures": []}
    for k in ROW_KEYS:
        data[k] = []
    for q in (quarters or quarters_to_scan(today)):
        period = period_of(q)
        held = prev_by_period.get(period)
        if held and not refresh:
            # 이미 수록된 보고서 — 다시 받지 않는다. 캐시 원문이 있으면 다시 파싱(파서 개선 반영), 없으면 기존 행 유지.
            meta = dict(held)
            rcp = meta["rcp_no"]
            htmls = {k: cache.read_section(rcp, k) for k in ("ii2", "ii3", "ii4", CHAPTER_KEY)}
            htmls = {k: v for k, v in htmls.items() if v}
            res = parse_report(htmls, period, rcp) if htmls else None
            if res is not None and res["sections"]:
                data["issues"].extend(res["issues"])
                data["reports"].append(meta)
                _append(data, res)
            else:
                # 캐시 원문이 없거나(CI 첫 실행 등) 다시 읽어도 빈 결과 — 기존 행을 그대로 둔다(fail-closed).
                # 캐시 없음은 일시 상태라 issues 에 싣지 않고 로그로만 남긴다(커밋이 오락가락하지 않게).
                data["reports"].append(meta)
                for k in ROW_KEYS:
                    data[k].extend(prev_rows[k].get(rcp, []))
                log("  %s %s: %s — 기존 JSON 행 유지" % (period, rcp, "캐시 원문 없음" if not htmls else "재파싱 빈 결과"))
                if htmls:
                    data["issues"].append("%s %s: 캐시 원문 재파싱이 비어 기존 행을 유지함" % (period, rcp))
            continue
        try:
            meta, htmls = collect_report(q, cache, fetched, log)
        except Exception as e:                                   # noqa: BLE001 — 분기별로 담는다
            # 수집 실패(IP 차단·응답 이상)는 일시 장애다 — issues 에 싣지 않고 failures 로 넘겨 기록을 막는다.
            data["_failures"].append("%s: 수집 실패 %s: %s" % (period, type(e).__name__, e))
            if held:                                             # 재수집 실패 — 기존 행 보존
                data["reports"].append(held)
                for k in ROW_KEYS:
                    data[k].extend(prev_rows[k].get(held["rcp_no"], []))
            continue
        if meta is None or not htmls:
            if held:                                             # --refresh 인데 검색이 비었다 — 기존 행 보존
                data["reports"].append(held)
                for k in ROW_KEYS:
                    data[k].extend(prev_rows[k].get(held["rcp_no"], []))
                data["issues"].append("%s: 재검색 결과 없음 — 기존 행 유지" % period)
            else:
                data["issues"].append("%s: 정기보고서 검색 결과 없음(미공시)" % period)
            continue
        res = parse_report(htmls, period, meta["rcp_no"])
        data["issues"].extend(res["issues"])
        if not res["sections"]:
            if held:
                data["reports"].append(held)
                for k in ROW_KEYS:
                    data[k].extend(prev_rows[k].get(held["rcp_no"], []))
            continue
        data["reports"].append(meta)
        _append(data, res)
    cache.save_index()
    data["reports"].sort(key=lambda r: (r["period"], r["rcp_no"]))
    data["quarterly"] = quarterly(data)
    data["generated"] = datetime.now(KST).isoformat(timespec="seconds")
    return data, fetched[0], prev


# ── 분기 단독값(누계 차분) ───────────────────────────────────

_CUM_ORDER = {"Q1": 1, "H1": 2, "Q3": 3, "FY": 4}
_HIMETAL = "하이메탈 부문"


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def cumulative_by_period(data):
    """하이메탈 부문 누계값 {period: {revenue, export, domestic, production_cost, avail_hours, actual_hours}}.

    정기보고서 표는 회계연도 누계다(1분기·반기·3분기·사업). 백만원으로 환산된 값만 쓴다.
    """
    cum, seen, bad = {}, {}, set()
    issues = data.setdefault("issues", [])

    def put(period, key, v):
        """한 (기간, 키)에 하이메탈 줄은 하나여야 한다. 다른 값이 두 번 나오면 그 키를 버린다."""
        if (period, key) in seen and seen[(period, key)] != v:
            bad.add((period, key))
        seen[(period, key)] = v
        cum.setdefault(period, {})[key] = v

    for r in data["product_sales"]:
        if (r["scope"] == _HIMETAL and is_himetal_row(r.get("labels") or [r.get("product", "")], r.get("total"))
                and r["unit"] == "백만원" and _num(r["amount"]) is not None):
            put(r["period"], "revenue", r["amount"])
    for s in data["sales"]:
        for tb in s["tables"]:
            if tb["amount_unit"] != "백만원" or not tb["periods"]:
                continue
            p0 = tb["periods"][0]                 # 첫 값 열 = 당기 누계(공시 관례)
            for r in tb["rows"]:
                key = {"exp": "export", "dom": "domestic"}.get(r["channel"])
                v = _num(r["vals"].get(p0))
                labels = [x for x in r["labels"] if x != r.get("channel_label")]
                if r["scope"] == _HIMETAL and is_himetal_row(labels, r["total"]) and key and v is not None:
                    put(s["period"], key, v)
    for r in data["capacity"]:
        if r["scope"] != _HIMETAL or not is_himetal_row([r["item"]]):
            continue
        if r["unit"] == "백만원" and _num(r["output"]) is not None:
            put(r["period"], "production_cost", r["output"])
        det = r.get("util_detail") or {}
        for src, key in (("가동가능시간", "avail_hours"), ("실제가동시간", "actual_hours")):
            v = _num(det.get(src))
            if v is not None:
                put(r["period"], key, v)
    for period, key in sorted(bad):
        cum[period].pop(key, None)
        issues.append("%s: 하이메탈 줄이 %s 에 둘 이상 — 값을 버림" % (period, key))
    # 수출+내수 = 매출(±1%) 대조. 어긋나면 수출·내수를 버린다(범위 오인 방지).
    for period, d in cum.items():
        rev, ex, dm = d.get("revenue"), d.get("export"), d.get("domestic")
        if rev and ex is not None and dm is not None and abs(ex + dm - rev) / rev > 0.01:
            d.pop("export"), d.pop("domestic")
            issues.append("%s: 수출+내수 %.0f ≠ 매출 %.0f(±1%%) — 수출·내수를 버림" % (period, ex + dm, rev))
    return cum


def quarterly(data):
    """누계 → 분기 단독값. 같은 회계연도의 직전 누계가 없으면 그 분기는 비운다(추정하지 않는다).

    가동률은 시간 차분으로 다시 계산한다: (실제시간 차분) ÷ (가동가능시간 차분). 가동가능시간
    = 장비대수 × 일평균가동시간 × 기간일수(원문 각주)라 분기 가동가능시간의 증가는 설비 증설 신호다.
    """
    cum = cumulative_by_period(data)
    out = []
    for period in sorted(cum, key=lambda p: (p[:4], _CUM_ORDER.get(p[5:], 9))):
        y, tag = period[:4], period[5:]
        k = _CUM_ORDER.get(tag)
        if k is None:
            continue
        cur = cum[period]
        prev = None
        if k > 1:
            prev_tag = {v: t for t, v in _CUM_ORDER.items()}[k - 1]
            prev = cum.get("%s-%s" % (y, prev_tag))
            if prev is None:
                continue
        row = {"quarter": "%sQ%d" % (y, k), "basis": "누계" if k == 1 else "누계 차분",
               "source_period": period}
        for key in ("revenue", "export", "domestic", "production_cost", "avail_hours", "actual_hours"):
            a = cur.get(key)
            b = 0 if prev is None else prev.get(key)
            row[key] = None if a is None or b is None else round(a - b, 3)
        ah, av = row["actual_hours"], row["avail_hours"]
        row["util_pct"] = round(ah / av * 100, 1) if ah is not None and av else None
        out.append(row)
    return out


def write_output(root, data, prev):
    """fail-closed: product_sales 0행이면 쓰지 않는다. 내용이 같으면(generated 제외) 건드리지 않는다."""
    if not data.get("product_sales"):
        raise SystemExit("product_sales 0행 — 기록하지 않고 종료(fail-closed)")
    if data.get("_failures"):
        raise SystemExit("수집 실패 %d건 — 기록하지 않고 종료(fail-closed):\n  %s" % (len(data["_failures"]), "\n  ".join(data["_failures"])))
    if prev:
        lost_p = {r.get("period") for r in prev.get("reports", [])} - {r["period"] for r in data["reports"]}
        lost_q = {r.get("quarter") for r in prev.get("quarterly", [])} - {r["quarter"] for r in data.get("quarterly", [])}
        if lost_p or lost_q:
            raise SystemExit("이전 결과보다 줄었다(보고서 %s · 분기 %s) — 기록하지 않고 종료(fail-closed)"
                             % (sorted(lost_p), sorted(lost_q)))
    data = {k: v for k, v in data.items() if not k.startswith("_")}
    out_path = os.path.join(root, REL_OUT)
    if same_content(data, prev):
        return False
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    atomic_write(out_path, dumps(data))
    return True


def dump_tables(root, log):
    """캐시 원문의 표 목록(무접속) — 파서를 다듬을 때 본다."""
    cache = Cache(root)
    if not os.path.isdir(cache.dir):
        log("캐시 없음: %s" % cache.dir)
        return
    for name in sorted(os.listdir(cache.dir)):
        if not name.startswith("sec_"):
            continue
        with open(os.path.join(cache.dir, name), encoding="utf-8") as f:
            html = f.read()
        log("=== %s (%d bytes)" % (name, len(html)))
        for i, (t, cols, rows) in enumerate(tables(html)):
            log("  [%d] lead…%s" % (i, lead_tail(t.get("lead"), 140)))
            log("      cols=%s" % cols)
            for r in rows[:4]:
                log("      row=%s" % r)
            if len(rows) > 4:
                log("      … %d행" % len(rows))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=REPO, help="레포 루트(출력 data/solder_ball·캐시 tools/solder_ball/cache 의 기준)")
    ap.add_argument("--refresh", action="store_true", help="JSON 에 이미 있는 보고서도 재검색·재수집")
    ap.add_argument("--dump", action="store_true", help="캐시 원문의 표 목록만 출력(무접속)")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    log = lambda s: sys.stderr.write(s + "\n")          # noqa: E731
    if a.dump:
        dump_tables(root, log)
        return 0
    t0 = time.time()
    data, fetched, prev = build(root, refresh=a.refresh, log=log)
    n = {k: len(data[k]) for k in ROW_KEYS}
    log("보고서 %d건 · 행 %s · 요청(절) %d · %.0fs" % (len(data["reports"]), n, fetched, time.time() - t0))
    for s in data["issues"] + data["_failures"]:
        log("  ! " + s)
    changed = write_output(root, data, prev)
    log("→ %s (%s)" % (os.path.join(root, REL_OUT), "기록" if changed else "변경 없음"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
