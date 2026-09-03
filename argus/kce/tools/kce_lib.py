#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_lib — 한국건설(argus/kce) 데이터 파이프라인 공용 유틸.

레포 규약(AGENTS.md): stdlib 전용 · fail-closed · 원자적 쓰기 · 정규화 출력.
데이터 계약은 argus/kce/LOGIC.md §2, 갱신 로직은 UPDATE.md 참조.
"""
import json
import os
import re
import tempfile

COMPANIES = ["sct", "hec", "sea", "dwe", "gse", "dle", "ipark"]

# 회사명·종목코드. corp_code(DART 고유번호 8자리)는 하드코딩하지 않는다 —
# OpenAPI 사용 시 corpCode.xml(키 필요)에서 stock 코드로 조회해 캐시하라(UPDATE.md §2).
# 무키 웹 경로(detailSearch.ax)는 회사명 검색이라 corp_code가 필요 없다.
CORP = {
    "sct":   {"name": "삼성물산",        "stock": "028260"},
    "hec":   {"name": "현대건설",        "stock": "000720"},
    "sea":   {"name": "삼성E&A",         "stock": "028050"},
    "dwe":   {"name": "대우건설",        "stock": "047040"},
    "gse":   {"name": "GS건설",          "stock": "006360"},
    "dle":   {"name": "DL이앤씨",        "stock": "375500"},
    "ipark": {"name": "HDC현대산업개발", "stock": "294870"},
}


# ── 분기 유틸 ────────────────────────────────────────────────

def q_of(y, m):
    """(연, 월) → 'YYYYQn'."""
    return "%dQ%d" % (y, (m - 1) // 3 + 1)


def q_next(q):
    y, n = int(q[:4]), int(q[5])
    return "%dQ%d" % (y + (n == 4), n % 4 + 1)


def q_range(q0, q1):
    """q0..q1 (포함) 분기 문자열 목록."""
    out, q = [], q0
    while True:
        out.append(q)
        if q == q1:
            return out
        q = q_next(q)


def report_kind(q):
    """분기 → 그 분기를 커버하는 정기보고서 종류(pblntf_detail_ty).
    Q1→분기(A003) Q2→반기(A002) Q3→분기(A003) Q4→사업(A001)."""
    n = int(q[5])
    return {1: "A003", 2: "A002", 3: "A003", 4: "A001"}[n]


# ── 헤더 정규화 (headers.html 카탈로그 기반 — LOGIC.md §4, UPDATE.md §3) ──

_PAREN_NOTE = re.compile(r"\((?:주\s*\d+|%)\)")          # (주1)·(%) 주석 접미
_UNIT_PREFIX = re.compile(r"\(단위\s*:[^)]*\)")            # (단위 : 백만원) 오염
_WS = re.compile(r"[\s 　]+")


def norm_col(s):
    """열 이름 정규화: 단위 프리픽스·괄호주석 제거 → 전 공백 제거.
    '계약일 (공사착공일)'→'계약일(공사착공일)', '완 공 예 정 일'→'완공예정일',
    '(단위 : 백만원) 신고일자'→'신고일자', '진행률 (%)'→'진행률'."""
    s = _UNIT_PREFIX.sub("", s or "")
    s = _PAREN_NOTE.sub("", s)
    s = _WS.sub("", s)
    # 가운뎃점 방언 통일: 판매ㆍ공급금액 / 판매·공급금액 / 판매/공급금액 / 판매공급금액
    s = s.replace("ㆍ", "").replace("·", "").replace("/", "")
    return s


# 정규화 후 열명 → 표준 필드 (회사·분기별 방언 흡수 사전)
COL_ALIAS = {
    # II-4 (수주상황 상세)
    "품목": "nm", "공사명": "nm", "프로젝트명": "nm", "구분": "nm", "현장명": "nm",
    "발주처": "cl",
    "계약일": "sd", "계약일(공사착공일)": "sd", "계약시작일": "sd",
    "공사착공일": "sd", "공사시작일": "sd", "계약착공일": "sd",
    "계약일(착공예정일)": "sd", "수주일자": "sd",
    "완공예정일": "ed", "준공예정일": "ed", "계약상완성기한": "ed", "완성기한": "ed",
    "기본도급액": "amt", "기본도급금액": "amt", "수주총액": "amt", "도급액": "amt",
    "완성공사액": "cmp", "기납품액": "cmp",
    "계약잔액": "bal", "수주잔고": "bal",
    "진행률": "pr",
    # III-8 (진행률 적용 수주계약)
    "회사명": "p8_ent",
    # 주의: `계약상완성기한`은 II-4에서 완공예정일(ed)로 이미 매핑돼 있다. 여기 다시 쓰면
    # dict 리터럴에서 뒤가 이겨 II-4의 ed가 통째로 사라진다(삼성E&A 실사례).
    # III-8의 공사기한은 `_records`가 p8 컨텍스트에서 ed→p8_dl로 옮겨 받는다.
    "공사기한": "p8_dl",
    "미청구공사총액": "ub", "계약자산총액": "ub",
    "미청구공사손상차손누계액": "ubimp", "계약자산손실충당금": "ubimp",
    "미청구공사대손충당금": "ubimp",
    "공사미수금총액": "rc", "매출채권총액": "rc",
    "공사미수금대손충당금": "allw", "공사미수금손실충당금": "allw",
    "매출채권대손충당금": "allw",
    # XI-1 (다층 헤더 평탄화 후, 가운뎃점·공백 제거 기준)
    "계약내역계약명": "xi_nm", "계약내역계약상대방": "xi_cl",
    "계약내역계약금액총액": "xi_amt", "계약금액총액": "xi_amt", "계약금액": "xi_amt",
    "계약금액총액(부가세포함)": "xi_amt",
    "판매공급금액당기": "xi_supCur", "판매공급금액누적": "xi_supCum",
    "대금수령당기": "xi_recvCur", "대금수령누적": "xi_recvCum",
}


def num_of(s):
    """공시 표 셀 → 숫자(백만원 단위 가정, 콤마·괄호음수·'-' 처리). 실패 시 None."""
    if s is None:
        return None
    t = _WS.sub("", str(s)).replace(",", "")
    if t.endswith("%"):
        t = t[:-1]
    if t in ("", "-", "–", "—", "."):
        return None
    neg = t.startswith("(") and t.endswith(")")
    if neg:
        t = t[1:-1]
    m = re.match(r"^-?\d+(\.\d+)?$", t)
    if not m:
        return None
    v = float(t)
    if v == int(v):
        v = int(v)
    return -v if neg else v


# ── DATA 블롭 추출·주입 (index.html의 const DATA) ─────────────

_DATA_RE = re.compile(r"const DATA\s*=\s*")


def _blob_span(html):
    m = _DATA_RE.search(html)
    if not m:
        raise ValueError("const DATA 를 찾지 못함")
    s = m.end()
    depth, i, instr, esc, q = 0, s, False, False, ""
    while i < len(html):
        ch = html[i]
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == q:
                instr = False
        else:
            if ch in "\"'":
                instr, q = True, ch
            elif ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
                if depth == 0:
                    return s, i + 1
        i += 1
    raise ValueError("DATA 블롭 괄호 불균형")


def extract_data(index_html_path):
    """회사 index.html에서 DATA dict를 파싱해 반환."""
    with open(index_html_path, encoding="utf-8") as f:
        html = f.read()
    s, e = _blob_span(html)
    return json.loads(html[s:e])


def json_for_html(data):
    """HTML `<script>` 안에 안전하게 넣을 수 있는 JSON 문자열.

    `json.dumps`는 `<`를 이스케이프하지 않는다. DART 셀 텍스트에 `</script>`가 섞이면
    (HTMLParser가 `&lt;/script&gt;`를 리터럴로 되돌리므로 실제로 도달 가능한 경로다)
    스크립트가 그 자리에서 끝나 DATA 전체가 미정의가 되고, 뒤 내용이 마크업으로 실행된다.
    `\\u003c`는 JSON 의미가 같으면서 HTML 파서에는 태그로 보이지 않는다.
    U+2028/2029도 JS 문자열 리터럴을 깨므로 함께 escape한다.
    """
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return (blob.replace("<", "\\u003c")
                .replace(" ", "\\u2028")
                .replace(" ", "\\u2029"))


def inject_data(index_html_path, data):
    """DATA를 교체해 원자적으로 재작성. 주입 전 재파싱 검증(fail-closed)."""
    with open(index_html_path, encoding="utf-8") as f:
        html = f.read()
    s, e = _blob_span(html)
    blob = json_for_html(data)
    json.loads(blob)  # round-trip 검증
    out = html[:s] + blob + html[e:]
    atomic_write(index_html_path, out)


def atomic_write(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".kce_tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
