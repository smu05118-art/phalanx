#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_parse — DART viewer.do 절 HTML에서 수주 관련 표를 추출한다.

파서 규칙(원 사이트 headers.html '파서 머리행 지도'에서 역산 — LOGIC.md §4, UPDATE.md §3):
  1. 열명은 정규화(공백·괄호주석·단위프리픽스·가운뎃점 제거) 후 별칭 사전으로 매칭
  2. 한 절에서 복수 표 수집이 기본(법인·관급/민간/해외·연결/별도 분할)
  3. 다층 머리행은 부모 프리픽스로 평탄화(colspan/rowspan 전개)
  4. 표 식별은 머리행 완전일치가 아니라 핵심 필드 집합 포함 여부 + 행수 기준 상세표 우선
  5. 미지 헤더 등장 시 조용히 스킵하지 않고 unknown_headers로 보고(fail-closed는 호출측)
stdlib 전용.
"""
import re
from html.parser import HTMLParser

from kce_lib import norm_col, num_of, COL_ALIAS


class _TableParser(HTMLParser):
    """HTML 전체에서 <table>들을 (직전 문맥 텍스트와 함께) 수집."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []          # {'lead', 'grid':[[(text,rs,cs,is_th)]]}
        self._lead = []           # 표 밖 텍스트 버퍼(최근 600자 유지)
        self._t = None            # 현재 테이블 grid
        self._row = None
        self._cell = None         # [text파편, rowspan, colspan, is_th]
        self._depth = 0           # 중첩 테이블 방지(원문은 비중첩)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        a = dict(attrs)
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._t = {"lead": "".join(self._lead)[-600:].strip(), "grid": []}
        elif self._depth == 1 and tag == "tr":
            self._row = []
        elif self._depth == 1 and tag in ("td", "th") and self._row is not None:
            self._cell = [[], int(a.get("rowspan") or 1),
                          int(a.get("colspan") or 1), tag == "th"]

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "table":
            if self._depth == 1 and self._t is not None:
                if self._t["grid"]:
                    self.tables.append(self._t)
                    cells = sum(len(r) for r in self._t["grid"])
                    if cells <= 3:
                        # 단위·기준일 캡션은 별도의 1셀짜리 표로 들어온다
                        # (예: <TD align='RIGHT'>(단위 : 백만원)</TD>).
                        # 이때 lead를 **교체하면 안 된다** — 바로 앞 <P>의
                        # '1) 진행률 적용 수주계약 현황(별도)' 같은 소절 라벨이 지워져
                        # 연결/별도 판정이 통째로 뒤집힌다(HDC현산 20셀 오배정 실사례).
                        txt = " ".join(c[0] for r in self._t["grid"] for c in r)
                        self._lead.append(" " + txt)
                    else:
                        self._lead = []
                else:
                    self._lead = []
                self._t = None
            self._depth = max(0, self._depth - 1)
        elif self._depth == 1 and tag == "tr" and self._row is not None:
            if self._row:
                self._t["grid"].append(self._row)
            self._row = None
        elif self._depth == 1 and tag in ("td", "th") and self._cell is not None:
            txt = re.sub(r"\s+", " ", "".join(self._cell[0])).strip()
            self._row.append((txt, self._cell[1], self._cell[2], self._cell[3]))
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell[0].append(data)
        elif self._depth == 0:
            self._lead.append(data)


def _expand_grid(grid):
    """rowspan/colspan을 전개해 직사각 행렬 [[(text,is_th)]]로 변환."""
    out = []
    pending = {}  # col -> (text, is_th, 남은 행수)
    for row in grid:
        cur, col = [], 0
        for txt, rs, cs, th in row:
            while col in pending:
                t2, th2, left = pending[col]
                cur.append((t2, th2))
                if left > 1:
                    pending[col] = (t2, th2, left - 1)
                else:
                    del pending[col]
                col += 1
            for _ in range(cs):
                cur.append((txt, th))
                if rs > 1:
                    pending[col] = (txt, th, rs - 1)
                col += 1
        while col in pending:
            t2, th2, left = pending[col]
            cur.append((t2, th2))
            if left > 1:
                pending[col] = (t2, th2, left - 1)
            else:
                del pending[col]
            col += 1
        out.append(cur)
    return out


# 헤더 어휘(정규화 후) — th 태그가 없는 표의 머리행 감지용
_HDR_VOCAB = set(COL_ALIAS) | {"비고", "구분", "합계", "신고일자", "품목", "회사명"}


def _looks_header(row):
    """행이 머리행처럼 보이는가: 셀 전부 비수치이고 절반 이상이 헤더 어휘."""
    cells = [c for c, _ in row]
    if not cells or any(num_of(c) is not None for c in cells):
        return False
    hits = sum(1 for c in cells if norm_col(c) in _HDR_VOCAB)
    return hits >= max(2, len(cells) // 2)


def _split_header(mat):
    """행렬 → (평탄화 헤더 목록, 데이터 행들).
    헤더 = 선두의 th-포함 행 묶음(없으면 어휘 기반 감지). 다층이면 부모 프리픽스로 결합."""
    nh = 0
    for r in mat:
        if any(th for _, th in r):
            nh += 1
        else:
            break
    if nh == 0:
        # DART 표 상당수가 th 없이 td 머리행 — 어휘로 감지(연속 최대 2행)
        while nh < min(2, len(mat)) and _looks_header(mat[nh]):
            nh += 1
    if nh == 0:
        return [], [[c for c, _ in r] for r in mat]
    width = max(len(r) for r in mat[:nh])
    cols = []
    for j in range(width):
        parts = []
        for i in range(nh):
            t = mat[i][j][0] if j < len(mat[i]) else ""
            if t and (not parts or parts[-1] != t):
                parts.append(t)
        cols.append(" ".join(parts))
    return cols, [[c for c, _ in r] for r in mat[nh:]]


def parse_tables(html):
    """절 HTML → [{'lead','cols'(원문),'ncols'(정규화),'fields'(별칭 매핑),'rows'}]"""
    p = _TableParser()
    p.feed(html)
    out = []
    for t in p.tables:
        mat = _expand_grid(t["grid"])
        cols, rows = _split_header(mat)
        ncols = [norm_col(c) for c in cols]
        fields = [COL_ALIAS.get(c) for c in ncols]
        out.append({"lead": t["lead"], "cols": cols, "ncols": ncols,
                    "fields": fields, "rows": rows, "inherited": False})
    # 머리행 계승: 헤더 없는 표가 직전 헤더 표와 열수가 같으면 연속 표로 간주
    # ('(2) 별도 기준'처럼 머리행을 반복하지 않는 DART 관행 흡수)
    last = None
    for t in out:
        if t["cols"]:
            last = t
        elif last and t["rows"]:
            w = max(len(r) for r in t["rows"])
            if w == len(last["cols"]):
                t["cols"], t["ncols"] = last["cols"], last["ncols"]
                t["fields"], t["inherited"] = last["fields"], True
    return out


# ── 절별 추출기 ──────────────────────────────────────────────

_II4_NEED = {"nm", "amt", "cmp", "bal"}       # 상세표 판별 핵심 필드
_P8_NEED = {"amt", "pr", "ub", "rc"}          # III-8 표 판별


# 단위 캡션 → 백만원 환산 배수. 회사마다 표 단위가 다르다(삼성E&A는 억원).
_UNIT_SCALE = [("십억원", 1000.0), ("백만원", 1.0), ("억원", 100.0),
               ("천원", 0.001), ("만원", 0.01), ("원", 1e-6)]
_UNIT_RE = re.compile(r"단위\s*:?\s*([^)\]]{1,12})")


def unit_scale(lead):
    """표 앞 문맥의 '(단위 : xxx)' → 백만원 기준 배수. 없으면 1.0(백만원 가정)."""
    m = _UNIT_RE.findall(lead or "")
    if not m:
        return 1.0
    txt = m[-1].replace(" ", "")
    for name, mul in _UNIT_SCALE:      # 긴 단위부터 매칭(십억원 > 억원 > 원)
        if name in txt:
            return mul
    return 1.0


_BASIS_MARK = re.compile(r"[(（]\s*\d+\s*[)）]\s*(연결|별도)\s*기준")


def _basis_of(lead):
    """III-8 표가 연결 기준인지 별도 기준인지 판정.

    '(1) 연결 기준' / '(2) 별도 기준' 소절 표지를 최우선으로 본다 — 본문에
    '연결회사는 …' 같은 서술이 섞여 있어 단순 포함 검사로는 오판한다(삼성물산 실사례).
    표지가 없으면 문맥 끝에 더 가까운 낱말을 택한다.
    """
    tail = (lead or "")[-300:]
    marks = _BASIS_MARK.findall(tail)
    if marks:
        return marks[-1]
    i_con, i_sep = tail.rfind("연결"), tail.rfind("별도")
    if i_con < 0 and i_sep < 0:
        return None
    return "연결" if i_con > i_sep else "별도"


# 원문이 명시하는 국내/해외 신호. 회사마다 형태가 다르다:
#   GS건설  — 표가 [국내공사]/[해외공사]로 분할된다(lead에 표지)
#   삼성물산 — 발주처 열에 `(카타르)`·`(한국)` 국가 접두가 붙는다
#   HDC현산 — 신호 없음(관급/민간 분할). 원본도 해외를 분리하지 않는다
_CORP_PAREN = {"주", "유", "재", "사", "합", "자", "㈜",
               "주식회사", "유한회사", "재단법인", "사단법인"}
_SEC_OVS = re.compile(r"\[\s*해외\s*(공사|부문|사업)?\s*\]")
_SEC_DOM = re.compile(r"\[\s*국내\s*(공사|부문|사업)?\s*\]")
_CL_COUNTRY = re.compile(r"^\s*[\(（]\s*([^)）]{1,14})\s*[\)）]")


def region_of(lead, cl):
    """그 분기 원문이 명시하는 국내/해외. 신호가 없으면 None(정적 reg로 폴백).

    lead는 꼬리 200자만 본다 — DL이앤씨 상세표의 '가. 지배회사 및 해외종속회사'처럼
    대괄호 없는 '해외'가 본문에 흔해서, 넓게 보면 전량 해외로 오판한다.
    """
    tail = (lead or "")[-200:]
    io, idm = _SEC_OVS.search(tail), _SEC_DOM.search(tail)
    if io or idm:
        return "해외" if (io and (not idm or io.end() > idm.end())) else "국내"
    m = _CL_COUNTRY.match(cl or "")
    if m:
        c = m.group(1).strip()
        if c not in _CORP_PAREN:      # (주)·(유) 등 법인격 괄호는 국가가 아니다
            return "국내" if c == "한국" else "해외"
    return None


def _near_miss(t, need):
    """핵심 필드의 절반 이상이 매칭됐는데 완성되지 않은 표 = 파서가 놓쳤을 가능성이 큰 표."""
    got = {f for f in t["fields"] if f}
    return len(need & got) >= max(2, len(need) // 2) and len(t["rows"]) >= 3


# 같은 표준 필드로 매핑되는 열이 여럿일 때의 우선순위(정규화 열명 기준).
# 예: 삼성물산 상세표는 품목(='건설사업')과 공사명이 공존 — 공사명이 정답.
_PREF = {
    "nm": ["공사명", "프로젝트명", "구분", "품목"],
    "sd": ["계약일(공사착공일)", "공사착공일", "공사시작일", "계약시작일",
           "계약일", "계약일(착공예정일)", "계약착공일"],
}


def _distinct_ratio(rows, i):
    """i번 열의 고유값 비율. 공사명 열은 1에 가깝고, '국내민간' 같은 분류 열은 낮다."""
    vals = [r[i].strip() for r in rows if i < len(r) and r[i].strip()]
    return (len(set(vals)) / len(vals)) if vals else 0.0


def _records(t, need):
    """필드 매핑된 표 → 레코드 dict 목록.

    같은 표준 필드로 매핑되는 열이 여럿이면 이름 우선순위(_PREF)로 고르되,
    `nm`은 **값의 고유도**를 함께 본다 — 삼성E&A 표는 `구분`이 국내관급/국내민간/해외
    3종 분류이고 실제 공사명은 `품목` 열에 있어서, 이름 순위만으로는 분류 열을 잡는다.
    """
    idx = {}
    for i, f in enumerate(t["fields"]):
        if not f:
            continue
        if f in idx:
            pref = _PREF.get(f)
            if pref:
                old = t["ncols"][idx[f]]
                new = t["ncols"][i]
                oi = pref.index(old) if old in pref else 99
                ni = pref.index(new) if new in pref else 99
                if ni < oi:
                    idx[f] = i
            continue
        idx[f] = i
    if "nm" in idx and len(t["rows"]) >= 5:
        cur = _distinct_ratio(t["rows"], idx["nm"])
        if cur < 0.5:                       # 분류 열을 잡았다 — 더 고유한 후보로 교체
            for i, f in enumerate(t["fields"]):
                if f == "nm" and i != idx["nm"]:
                    if _distinct_ratio(t["rows"], i) > cur:
                        idx["nm"] = i
                        cur = _distinct_ratio(t["rows"], i)
    if not need.issubset(idx):
        return None
    money = ("amt", "cmp", "bal", "ub", "ubimp", "rc", "allw", "xi_amt",
             "xi_supCur", "xi_supCum", "xi_recvCur", "xi_recvCum")
    scale = unit_scale(t.get("lead"))     # 표 단위를 백만원으로 정규화
    recs = []
    for r in t["rows"]:
        rec = {}
        for f, i in idx.items():
            v = r[i] if i < len(r) else ""
            if f in money:
                x = num_of(v)
                if x is not None and scale != 1.0:
                    if scale >= 1 and float(scale).is_integer():
                        x = x * int(scale)          # 억원→백만원 등: 정수배(오차 없음)
                    else:
                        x = round(x * scale, 6)     # 천원→백만원 등: 나눗셈 오차 절단
                    if float(x).is_integer():
                        x = int(x)
                rec[f] = x
            elif f == "pr":
                rec[f] = num_of(v)
            else:
                rec[f] = v.strip()
        # 합계·소계·빈 행 제외
        name = (rec.get("nm") or "")
        if name in ("합계", "합 계", "총계", "소계", "계", "") and rec.get("cl", "") == "":
            continue
        recs.append(rec)
    return recs


def parse_ii4(html):
    """II-4 수주상황(또는 XII 상세표) 절 → 사업장 행 목록 + 진단.
    복수 표(법인·관급/민간/해외 분할)를 전부 수집하며, 각 표의 lead를 tag로 보존."""
    tables = parse_tables(html)
    picked, unknown = [], []
    for t in tables:
        recs = _records(t, _II4_NEED)
        if recs is None:
            # 핵심 필드의 **절반 이상**이 매칭되는데 완성되지 않은 표만 경보한다.
            # (매출실적·시공실적 표처럼 '구분' 하나만 걸리는 표까지 경보하면
            #  정상 갱신이 오탐으로 막힌다)
            if _near_miss(t, _II4_NEED):
                unknown.append({"cols": t["cols"], "n": len(t["rows"])})
            continue
        picked.append({"lead": t["lead"], "cols": t["cols"],
                       "n": len(recs), "rows": recs})
    return {"tables": picked, "unknown_headers": unknown}


def parse_p8(html):
    """III-8 진행률적용 수주계약 절 → 연결/별도 표 목록.
    구분은 lead 문맥의 '연결'/'별도' 앵커(없으면 등장 순서: 연결→별도가 관례)."""
    tables = parse_tables(html)
    picked, unknown = [], []
    for t in tables:
        recs = _records(t, _P8_NEED)
        if recs is None:
            if sum(1 for f in t["fields"] if f) >= 3 and len(t["rows"]) >= 3:
                unknown.append({"cols": t["cols"], "n": len(t["rows"])})
            continue
        # III-8의 '계약상 완성기한'은 II-4에서 ed로 매핑되므로 여기서 p8_dl로 옮겨 받는다
        for rec in recs:
            if not rec.get("p8_dl") and rec.get("ed"):
                rec["p8_dl"] = rec["ed"]
        lead = t["lead"]
        picked.append({"basis": _basis_of(lead), "lead": lead, "cols": t["cols"],
                       "n": len(recs), "rows": recs})
    # lead에서 구분을 못 읽은 표가 2개면 관례(연결 먼저)를 적용한다.
    # 표가 하나뿐일 때는 단정하지 않고 None으로 남긴다 — 회사마다 다르다
    # (HDC현산은 2023Q4부터 연결만 공시한다). 호출측이 직전 분기 연속성으로 판정한다.
    unlabeled = [t for t in picked if t["basis"] is None]
    if len(unlabeled) == 2:
        unlabeled[0]["basis"], unlabeled[1]["basis"] = "연결", "별도"
    return {"tables": picked, "unknown_headers": unknown}
