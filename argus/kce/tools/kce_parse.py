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
    """rowspan/colspan을 전개해 직사각 행렬 [[(text,is_th,colspan,from_rowspan)]]로 변환.

    전개하면서 **원 셀의 colspan을 셀마다 남긴다.** 전개가 끝나면
    `<TD colspan='5'>합 계</TD>`(라벨 구역 전체를 한 칸으로 묶은 줄)와 다섯 열에
    실제로 같은 글자가 들어간 줄이 구분되지 않는데, 합계 줄 판별에 그 차이가 필요하다
    (_merged_label 참조). 값 자체는 예전과 똑같이 복제한다 — 복제를 멈추면
    합계 줄의 발주처가 빈칸이 되어 _records의 기존 배제 규칙에 걸려
    원문 총계가 통째로 사라진다.

    넷째 값(from_rowspan)은 **위 줄의 rowspan 이 흘러내려 복제된 칸**인지 표시한다(원 셀은 False).
    값 복제는 그대로 두고 출처만 남긴다 — XI-1 진행 현황(삼성E&A)은 한 계약을 두 줄
    (당기/누적)로 rowspan 해 적어서, 복제된 칸과 원 칸을 가르지 못하면 계약 21줄이 19계약으로
    합쳐지지 않는다(설계 C·U3). 기존 소비자는 [0]~[2] 만 읽으므로 동작은 같다.
    """
    out = []
    pending = {}  # col -> (text, is_th, colspan, 남은 행수)
    for row in grid:
        cur, col = [], 0
        for txt, rs, cs, th in row:
            while col in pending:
                t2, th2, cs2, left = pending[col]
                cur.append((t2, th2, cs2, True))
                if left > 1:
                    pending[col] = (t2, th2, cs2, left - 1)
                else:
                    del pending[col]
                col += 1
            for _ in range(cs):
                cur.append((txt, th, cs, False))
                if rs > 1:
                    pending[col] = (txt, th, cs, rs - 1)
                col += 1
        while col in pending:
            t2, th2, cs2, left = pending[col]
            cur.append((t2, th2, cs2, True))
            if left > 1:
                pending[col] = (t2, th2, cs2, left - 1)
            else:
                del pending[col]
            col += 1
        out.append(cur)
    return out


# 헤더 어휘(정규화 후) — th 태그가 없는 표의 머리행 감지용
_UNIT_ONLY = re.compile(r"\(?\s*단위\s*[:：][^)]*\)?")
_HDR_VOCAB = set(COL_ALIAS) | {"비고", "구분", "합계", "신고일자", "품목", "회사명"}
# 둘째 머리행에만 오는 하위 어휘 — '기본도급액|금액', '미청구공사|총액·손상차손누계액', '수주총액|별도·연결'.
_SUB_VOCAB = {"금액", "수량", "총액", "당기", "누적", "손상차손누계액", "대손충당금", "손실충당금",
              "계약자산", "별도", "연결"}

# 계룡건설 II-4는 공종 소제목('건축'·'토목')을 머리행 둘째 줄로 끼워 넣어 평탄화하면
# '현장명 건축'·'총 도급금액 건축'이 된다(머리행 지도 2023Q4~ 22표). 접미를 벗겨 사전에 다시 묻는다.
_SUFFIX_KIND = re.compile(r"^(.+?)-?(건축|토목|주택|플랜트|환경|기타)$")


_KIND_ROW = re.compile(r"^-\s*(건축|토목|주택|플랜트|환경|기타)$")


def _kind_row(row):
    """'- 건축' 공종 소제목 줄인가 — 빈 칸을 뺀 글자가 전부 같은 '- 공종' 하나(병합 전개면 열마다 같은 글자)."""
    vals = {c[0].strip() for c in row if c[0].strip()}
    return len(vals) == 1 and bool(_KIND_ROW.match(next(iter(vals))))


def _field_of(ncol):
    f = COL_ALIAS.get(ncol)
    if f:
        return f
    m = _SUFFIX_KIND.match(ncol)
    if m and COL_ALIAS.get(m.group(1)):
        return COL_ALIAS[m.group(1)]
    return None


def _looks_header(row, vocab=None):
    """행이 머리행처럼 보이는가: 셀 전부 비수치이고 절반 이상이 헤더 어휘.

    vocab 을 주지 않으면 **호출 시점의** 모듈 전역 `_HDR_VOCAB` 을 읽는다 — kship_parse 가 그
    집합을 제자리에서 넓혔다 되돌리는 방식(_ship_header_vocab)을 그대로 살린다. XI-1(kce_xi1)처럼
    다른 어휘가 필요한 파서는 전역을 건드리지 말고 인자로 넘긴다(설계 C: XI 어휘는 지역)."""
    cells = [c[0] for c in row]
    if not cells or any(num_of(c) is not None for c in cells):
        return False
    v = _HDR_VOCAB if vocab is None else vocab
    hits = sum(1 for c in cells if norm_col(c) in v or norm_col(c) in _SUB_VOCAB)
    return hits >= max(2, len(cells) // 2)


def _split_header(mat, max_rows=2, vocab=None, upstream=False):
    """행렬 → (평탄화 헤더 목록, 데이터 행들, 데이터 행별 colspan, 캡션, 데이터 위 줄 수).
    헤더 = 선두의 th-포함 행 묶음(없으면 어휘 기반 감지). 다층이면 부모 프리픽스로 결합.
    colspan은 데이터 행에서만 쓰므로 헤더 행 몫은 잘라내고 같은 길이로 돌려준다.

    max_rows: 어휘로 감지하는 머리행의 최대 줄 수(기본 2 — 종전 동작). th 머리행 아래에 이어 붙는
    td 머리행은 max_rows-1 줄까지(기본 1줄 — 종전 동작). XI-1 진행 현황은 3~4단 머리행이라
    kce_xi1 이 4 로 부른다. 다섯째 값 = 단위 캡션 줄 + 머리행 줄 수(원행수 n 을 만드는 재료).

    upstream=True 는 **상류 headers.html 이 열 이름을 만든 방식**으로 평탄화한다 — 지도용 열 이름(cols_up)
    전용이고, 파서가 레코드를 읽는 열 이름·데이터 행은 언제나 upstream=False 결과다(parse_tables 참조):
      · th 로 된 단위 캡션 줄은 걷어내지 않고 머리행 첫 줄로 둔다 — 금호건설 III-8 은 상류 지도 27분기
        전부 '(단위: 백만원) 구분'… 꼴이다. td 캡션 줄(KCC건설 상세표 `(단위:원)` × 7열)은 종전대로 걷는다.
      · th 머리행 바로 밑 '- 건축' 공종 소제목 줄을 머리행 둘째 줄로(_kind_row)."""
    # 첫 행이 단위 캡션만 반복하는 표가 있다(KCC건설 상세표: `(단위:원)` × 7열).
    # 그 행을 머리행 후보로 보면 어휘 감지가 실패해 표 전체가 버려진다 — 캡션 행은 걷어낸다.
    skip = 0
    while skip < len(mat) - 1:
        cells = [c[0].strip() for c in mat[skip]]
        uniq = {c for c in cells if c}
        if uniq and len(uniq) == 1 and _UNIT_ONLY.fullmatch(next(iter(uniq))):
            skip += 1
        else:
            break
    caption = ""
    if skip:
        caption = " ".join(dict.fromkeys(c[0].strip() for c in mat[0] if c[0].strip()))
        if upstream and all(any(c[1] for c in r) for r in mat[:skip]):
            # th 캡션 줄은 머리행으로 남긴다(열 이름 '(단위: 백만원) 구분' — 상류 지도 관례). 캡션 글자는
            # 위에서 그대로 lead 에 붙는다 — lead 가 같아야 unit_scale(lead 우선)이 종전과 같은 단위를 읽는다.
            skip = 0
        else:
            mat = mat[skip:]
    nh = 0
    for r in mat:
        if any(c[1] for c in r):
            nh += 1
        else:
            break
    if nh == 0:
        # DART 표 상당수가 th 없이 td 머리행 — 어휘로 감지(연속 최대 max_rows 행, 기본 2)
        while nh < min(max_rows, len(mat)) and _looks_header(mat[nh], vocab):
            nh += 1
    else:
        # th 머리행 아래에 td 로 이어지는 둘째 머리행 — 동부건설 III-8(기본도급액|금액, 미청구공사|총액·
        # 손상차손누계액). th 만 세면 둘째 줄이 데이터로 떨어져 열 이름에 부모만 남고(미청구공사·공사미수금)
        # ub·rc 가 사라져 표 전체가 미지 헤더가 된다(2026Q2 원문 실측). 어휘로 한 줄 더 본다
        # (기본 max_rows=2 → 정확히 한 줄 — 종전 동작).
        extra = 0
        while extra < max(1, max_rows - 1) and nh < len(mat) and _looks_header(mat[nh], vocab):
            nh += 1
            extra += 1
        if upstream and nh < len(mat) and _kind_row(mat[nh]):
            # th 머리행 바로 밑 '- 건축' 줄(계룡건설 II-4 2023Q4~)은 머리행 둘째 줄로 평탄화한다 —
            # 상류 지도 D 가 그렇게 읽어 열 이름이 '현장명 - 건축'(병합 칸이면 여섯 열 전부 '… - 건축')이다.
            # 데이터 줄로 두면 레코드는 같지만(공종 소제목 줄은 _records 가 어차피 거른다) 열 이름이 상류와
            # 갈라져 지도가 매 분기 「바뀜」을 띄운다(2026Q2 원문 실측 — kre 137·44행 표 둘 다).
            # 접미는 _SUFFIX_KIND 가 벗기므로 필드 매핑은 그대로다. 대시 꼴만 본다(본문 '건축' 줄 오인 방지).
            nh += 1
    txt = [[c[0] for c in r] for r in mat[nh:]]
    spans = [[c[2] for c in r] for r in mat[nh:]]
    if nh == 0:
        return [], txt, spans, caption, skip
    width = max(len(r) for r in mat[:nh])
    cols = []
    for j in range(width):
        parts = []
        for i in range(nh):
            t = mat[i][j][0] if j < len(mat[i]) else ""
            if t and (not parts or parts[-1] != t):
                parts.append(t)
        cols.append(" ".join(parts))
    return cols, txt, spans, caption, skip + nh


def parse_tables(html, max_header_rows=2, vocab=None, keep_rowspan=False, upstream_hdr=False):
    """절 HTML → [{'lead','cols'(원문),'ncols'(정규화),'fields'(별칭 매핑),'rows','spans','inherited',
    'hdr_rows','n_raw'(, 'cols_up', 'rspan')}]

    hdr_rows = 데이터 위 줄 수(단위 캡션 줄 + 머리행 줄), n_raw = 표의 **원행수**(머리행 포함, 전개 후
    행렬 줄 수). 상류 headers.html 의 n 이 이 값이다 — 2026Q2 픽스처 실측: 현대건설 II-4 [62,43,21,4]·
    동부 ii4x [103,66]·동부 III-8 [51,47,9]·금호 III-8 35(캡션 1+머리행 2+데이터 32)·계룡 [137,44]가
    전부 n_raw 와 같고, 레코드 수(합계·소계·공종 소제목 제외)와는 다르다. 지도 엔진은 n 을 추정하지
    않으므로(hdrmap docstring) 호출측이 이 값을 그대로 실어 보낸다.

    max_header_rows·vocab 은 머리행 감지 인자(_split_header) — 기본값이면 종전과 바이트 같은 결과다.
    keep_rowspan=True 면 데이터 행별 'rspan'([bool] — 위 줄 rowspan 이 흘러내린 칸)을 함께 싣는다(XI-1).
    upstream_hdr=True 면 'cols_up' — 상류 headers.html 관례로 평탄화한 열 이름(같은 열 수)을 **덧붙인다**.
    cols·rows·레코드는 바뀌지 않는다: 그 관례를 cols 에 직접 적용하면 금호 III-8 열이 '(단위: 백만원) 계약금액'
    이 되어 기존 계약(test_kumho)을 깨고, 계룡 '- 건축' 줄이 데이터에서 빠져 원행 구성이 달라진다. 지도에
    적는 열 이름만 상류와 이어지면 된다(설계: 다분기 대조가 가짜 「바뀜」을 내지 않게)."""
    p = _TableParser()
    p.feed(html)
    out = []
    for t in p.tables:
        mat = _expand_grid(t["grid"])
        cols, rows, spans, caption, top = _split_header(mat, max_header_rows, vocab)
        ncols = [norm_col(c) for c in cols]
        fields = [_field_of(c) for c in ncols]
        lead = ((t["lead"] or "") + " " + caption).strip() if caption else t["lead"]
        d = {"lead": lead, "cols": cols, "ncols": ncols,
             "fields": fields, "rows": rows, "spans": spans,
             "inherited": False, "hdr_rows": top, "n_raw": len(mat)}
        if keep_rowspan:
            d["rspan"] = [[bool(c[3]) for c in r] for r in mat[top:]]
        if upstream_hdr:
            up = _split_header(mat, max_header_rows, vocab, True)[0]
            d["cols_up"] = up if len(up) == len(cols) else list(cols)   # 열 수가 갈리면 쓰지 않는다
        out.append(d)
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
                if "cols_up" in last:
                    t["cols_up"] = last["cols_up"]
    return out


# ── 절별 추출기 ──────────────────────────────────────────────

_II4_NEED = {"nm", "amt", "cmp", "bal"}       # 상세표 판별 핵심 필드
_P8_NEED = {"amt", "pr", "ub", "rc"}          # III-8 표 판별


# 단위 캡션 → 백만원 환산 배수. 회사마다 표 단위가 다르다(삼성E&A는 억원).
_UNIT_SCALE = [("십억원", 1000.0), ("백만원", 1.0), ("억원", 100.0),
               ("천원", 0.001), ("만원", 0.01), ("원", 1e-6)]
_UNIT_RE = re.compile(r"단위\s*:?\s*([^)\]]{1,12})")


def unit_scale(lead, cols=None):
    """표의 '(단위 : xxx)' → 백만원 기준 배수. 없으면 1.0(백만원 가정).

    단위 캡션이 표 앞 문맥이 아니라 **머리행 셀 안**에 들어가는 회사가 있다
    (동신건설: `(단위 : 천원) 품목`). lead만 보면 천원을 백만원으로 읽어 값이
    1000배가 된다 — 실제로 수주잔고가 256조로 부풀었다. lead에 없으면 열명도 본다.
    """
    m = _UNIT_RE.findall(lead or "")
    if not m and cols:
        m = _UNIT_RE.findall(" ".join(cols))
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


# 관급/민간(·국내/해외) 꼬리 표지 — 머리행 지도 tag 의 원천. 상류 headers.html 은 GS건설·HDC현산
# 표를 '[관급공사]'·'[민간공사]'·'[국내공사]'·'[해외공사]' 표지로 갈라 tag 를 달았는데(D 127표:
# gse 89 + ipark 38), 우리 코드에는 관급/민간 판정이 아예 없었다(region_of 는 국내/해외만).
# 표지는 lead 꼬리에 오므로 **마지막** 표지를 쓴다 — GS건설 lead 에는 본문 '[BTO/BTL]' 이 앞서 섞인다.
# '[공공부문]' 은 관급과 같은 뜻이라 관급으로 접는다(상류 tag 어휘는 관급/민간/국내/해외 넷뿐).
_SEC_TAG = re.compile(r"\[\s*(관급|민간|공공|해외|국내)\s*(?:공사|부문|사업)?\s*\]")
# HDC현산 2021Q4 는 표지 대신 절 제목에 붙였다: '4. 수주상황_민간공사(상세)'.
_SEC_TAG_TITLE = re.compile(r"_(관급|민간)공사")


def sector_of(lead):
    """표 앞 문맥 꼬리의 관급/민간/국내/해외 표지 → 그 낱말, 없으면 None.

    region_of 와 같이 꼬리 200자만 본다(본문 서술 속 '해외' 오인 방지). 상류 지도 D 의
    gse·ipark 127표 lead 로 전부 재현된다(tests.test_headers_render.test_sector_of_126_127)."""
    tail = (lead or "")[-200:]
    m = _SEC_TAG.findall(tail)
    if m:
        return "관급" if m[-1] == "공공" else m[-1]
    m = _SEC_TAG_TITLE.findall(tail)
    return m[-1] if m else None


def lead_tail(lead, n=120):
    """지도·대기열에 적는 표 앞 문맥 — 공백 뭉치를 한 칸으로 접은 **꼬리** n 자(상류 지도 D 의 lead 꼴).
    원문 lead 는 줄바꿈·연속 공백이 섞여 같은 문맥이 분기마다 다른 글자로 적힌다. 판정(sector_of·_tag_ent)은
    종전대로 원문 lead 로 한다 — 이 함수는 기록용이다."""
    return re.sub(r"\s+", " ", lead or "").strip()[-n:]


def _near_miss(t, need):
    """핵심 필드의 절반 이상이 매칭됐는데 완성되지 않은 표 = 파서가 놓쳤을 가능성이 큰 표."""
    got = {f for f in t["fields"] if f}
    return len(need & got) >= max(2, len(need) // 2) and len(t["rows"]) >= 3


# 같은 표준 필드로 매핑되는 열이 여럿일 때의 우선순위(정규화 열명 기준).
# 예: 삼성물산 상세표는 품목(='건설사업')과 공사명이 공존 — 공사명이 정답.
_PREF = {
    # 구체적인 이름일수록 앞. `구분`은 건축/토목 같은 분류 열인 경우가 많아 뒤로 민다
    # (태영건설은 `구분`=공종 · `수주내용`=현장명, 계룡건설은 `현장명`이 정답).
    "nm": ["공사명", "계약명", "프로젝트명", "수주내용", "현장명", "구분", "품목"],
    "sd": ["계약일(공사착공일)", "공사착공일", "공사시작일", "계약시작일",
           "계약일", "계약일(착공예정일)", "계약착공일"],
}


# 그 줄 전체가 합계임을 알리는 라벨(정확히 이 글자일 때만).
_SUM_LABEL = ("합계", "합 계", "총계", "소계", "계")
_MONEY_ANY = ("amt", "cmp", "bal", "ub", "rc", "xi_amt")   # 이 중 하나는 있어야 사업장 줄이다


def _merged_label(spans, ri, ni):
    """행 ri의 이름 칸이 **앞쪽 여러 열을 하나로 병합한 라벨 칸**인가.

    `<TD colspan='5'>합 계</TD>`는 품목·일자·납기·계약명·발주처를 통째로 덮는
    '그 줄의 라벨'이지 열별 값이 아니다. rowspan으로 흘러든 칸은 colspan이 1이라
    걸리지 않으므로, 이 판정은 가로로 진짜 병합된 칸만 잡는다.
    """
    if ni is None or ri >= len(spans):
        return False
    row = spans[ri]
    return bool(row) and row[0] >= 2 and ni < row[0]


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
    scale = unit_scale(t.get("lead"), t.get("cols"))   # 표 단위를 백만원으로 정규화
    spans = t.get("spans") or []
    recs = []
    block = None      # 진행 중인 병합 라벨 합계 블록의 라벨(빈 이어짐 줄이 물려받는다)
    for ri, r in enumerate(t["rows"]):
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
        merged = _merged_label(spans, ri, idx.get("nm"))
        cont = False
        if merged and name in _SUM_LABEL:
            block = name                      # 여기서부터 합계 블록
        elif (merged and not name and block
              and any(rec.get(f) is not None for f in ("amt", "cmp", "bal"))):
            # 라벨 칸이 **빈 채로** 합계 줄 바로 아래 이어지고 금액만 있는 줄 —
            # 같은 합계 블록의 둘째 줄이다. 대명에너지 2026Q1이 그렇다: 위 '합 계'
            # 줄은 전 분기 총액(545,096,433천원)이 남은 낡은 줄이고, 진짜 총계
            # (409,379,048 / 193,176,718 / 216,202,330천원)는 라벨 없는 이 줄에 있다.
            # 이름이 없다고 버리면 원문 총계가 통째로 사라져 대조 분모가 낡은 줄의
            # 155,355천원이 되고 recon이 139,066%로 튄다. 이름을 물려줘 호출측의
            # 합계 판별(kce_series.is_total_row)이 두 줄 다 보게 한다.
            rec["nm"] = name = block
            cont = True
        else:
            block = None
        if not cont and (name in _SUM_LABEL or not name) \
                and rec.get("cl", "") == "":
            continue
        # 공종 소제목 줄('건축'·'토목') — 계룡건설 II-4가 표 안에 끼워 넣는다. 한 칸으로 병합돼
        # 있으면(전개된 칸마다 같은 글자가 들어가 날짜 칸까지 '건축'이 된다) 금액이 하나도 없는 것으로,
        # 병합이 아니면 이름 밖의 칸이 전부 빈 것으로 가려낸다. 사업장으로 세면 금액 없는 가짜 현장이 생긴다.
        if not cont and name not in _SUM_LABEL and (
                (merged and all(rec.get(f) is None for f in _MONEY_ANY))
                or all(rec.get(f) in (None, "") for f in idx if f != "nm")):
            continue
        recs.append(rec)
    return recs


# 진행률형 수주표 — 도급액·완성공사액·잔액 세 열 대신 **계약금액과 진행률(%)** 로 적는 회사가 있다.
# 2026Q2 원문 실측: 특수건설 `나. 수주현황`(현장명·구분·계약금액·계약일·종료예정일·진행률(%)·미청구공사…),
# 엄지하우스(현장명·수주일자·납기·진행률(%)·수주잔고 금액·공사미수금). 기존 `_II4_NEED` 로는 통째로 버려져
# 두 회사가 '미수록'으로 남아 있었다. 완성공사액·잔액은 **유도값**이므로 표시로 남긴다(원문 값이 아니다).
_PR_NEED = {"nm", "pr"}


def _progress_records(t):
    """진행률형 표 → II-4 레코드. amt(계약금액) 또는 bal(수주잔고) 중 하나는 있어야 한다."""
    recs = _records(t, _PR_NEED)
    if not recs:
        return None
    out = []
    for r in recs:
        pr = r.get("pr")
        amt = r.get("amt")
        if amt is None:
            amt = r.get("xi_amt")          # '계약금액' 은 XI-1 별칭으로 먼저 잡힌다
        bal = r.get("bal")
        if pr is None or (amt is None and bal is None):
            continue
        p = pr / 100.0 if pr > 1 else pr
        if not (0.0 <= p <= 1.0):
            continue
        if amt is None and bal is not None and p < 1.0:
            amt = round(bal / (1.0 - p), 6) if p < 1.0 else None   # 잔고·진행률 → 도급액(유도)
            r["_derived"] = "amt"
        if amt is None:
            continue
        r["amt"] = amt
        if r.get("cmp") is None:
            r["cmp"] = round(amt * p, 6)
            r["_derived"] = (r.get("_derived") + "+cmp") if r.get("_derived") else "cmp"
        if r.get("bal") is None:
            r["bal"] = round(amt - r["cmp"], 6)
            r["_derived"] = (r.get("_derived") or "") + "+bal"
        out.append(r)
    return out or None


def _hdr_meta(t, i):
    """표 하나의 머리행 지도 재료 — 지도 엔진(hdrmap)의 entry 키 이름 그대로. 행은 호출측이 덧붙인다
    (채택 표 = 레코드, 비채택 후보 = A/B 판정용 원문 행 — 어느 쪽도 지도에는 저장되지 않는다).

    idx 는 절 안 표 순번(채택·비채택을 원문 순서로 다시 엮는 데 쓴다), n 은 **원행수**(n_raw)."""
    return {"idx": i, "lead": t["lead"], "cols": t["cols"], "cols_up": t.get("cols_up") or t["cols"],
            "ncols": t["ncols"], "fields": t["fields"],
            "inherited": t["inherited"], "n": t["n_raw"], "hdr_rows": t["hdr_rows"]}


def _core(t, need):
    return need & {f for f in t["fields"] if f}


def parse_ii4(html):
    """II-4 수주상황(또는 XII 상세표) 절 → 사업장 행 목록 + 진단.
    복수 표(법인·관급/민간/해외 분할)를 전부 수집하며, 각 표의 lead를 tag로 보존.

    반환 {tables, unknown_headers, rejected}:
      tables   채택 표 — 종전 키(lead·cols·n=레코드 수·rows)에 지도 재료(idx·ncols·fields·inherited·
               n_raw=원행수·n_rec=레코드 수·hdr_rows)를 더했다. n 의 뜻(레코드 수)은 바꾸지 않는다 —
               kce_build·kce_series·kce_probe 가 절 선택(행수 큰 쪽)과 등급에 n 을 합산한다.
      unknown_headers  종전 그대로({cols, n}) — fail-closed 판정 대상.
      rejected 채택되지 않은 **후보** 표 {idx, cols, ncols, fields, n(원행수), lead, inherited, reason,
               rows·spans(A/B 판정 재료 — 지도에는 저장되지 않는다)}. reason: near_miss(=unknown_headers 와
               같은 표) | no_core(핵심 필드 둘 이상이 걸렸지만 레코드가 서지 않음 — 행 부족 등).
               핵심 필드가 하나 이하인 표(판매조직·수주전략·매출실적처럼 '구분' 하나만 걸리는 표)는 후보가
               아니다 — 상류 지도 D 의 비채택 91표도 전부 핵심 4필드를 갖춘 표였다(2026Q2 스냅샷 실측).
    각 항목의 cols_up = 상류 지도식 열 이름(지도 기록용 — parse_tables upstream_hdr)."""
    tables = parse_tables(html, upstream_hdr=True)
    picked, unknown, rejected = [], [], []
    for i, t in enumerate(tables):
        recs = _records(t, _II4_NEED)
        if recs is None and re.search(r"수주", (t.get("lead") or "") + " ".join(t.get("cols") or [])):
            recs = _progress_records(t)    # 진행률형 — 수주 문맥에서만 시도한다(매출실적 표 오인 방지)
        if recs is None:
            # 핵심 필드의 **절반 이상**이 매칭되는데 완성되지 않은 표만 경보한다.
            # (매출실적·시공실적 표처럼 '구분' 하나만 걸리는 표까지 경보하면
            #  정상 갱신이 오탐으로 막힌다)
            if _near_miss(t, _II4_NEED):
                unknown.append({"cols": t["cols"], "n": len(t["rows"])})
                reason = "near_miss"
            elif len(_core(t, _II4_NEED)) >= 2:
                reason = "no_core"
            else:
                continue
            r = _hdr_meta(t, i)
            r.update(reason=reason, rows=t["rows"], spans=t["spans"])
            rejected.append(r)
            continue
        d = _hdr_meta(t, i)
        d.update(n=len(recs), rows=recs, n_raw=t["n_raw"], n_rec=len(recs))
        picked.append(d)
    return {"tables": picked, "unknown_headers": unknown, "rejected": rejected}


_P8_RECV_HINT = re.compile(r"미청구|계약자산|미수금|매출채권")


def _promote(t, src, dst):
    """표의 필드 매핑에서 src 를 dst 로 올린다(dst 가 이미 있으면 그대로). 원 표는 바꾸지 않는다."""
    if dst in t["fields"] or src not in t["fields"]:
        return t
    t2 = dict(t)
    t2["fields"] = [dst if f == src else f for f in t["fields"]]
    return t2


def parse_p8(html):
    """III-8 진행률적용 수주계약 절 → 연결/별도 표 목록.
    구분은 lead 문맥의 '연결'/'별도' 앵커(없으면 등장 순서: 연결→별도가 관례).
    반환·후보(rejected)·머리행 평탄화 규약은 parse_ii4 와 같다(reason: meta_p8|near_miss|few_fields)."""
    tables = parse_tables(html, upstream_hdr=True)
    picked, unknown, rejected = [], [], []
    for i, t in enumerate(tables):
        # 금호건설 III-8은 수주총액을 '계약금액'으로 적는다 — XI-1 별칭(xi_amt)으로 먼저 잡히므로
        # amt 열이 따로 없을 때만 amt 로 올린다.
        t = _promote(t, "xi_amt", "amt")
        recs = _records(t, _P8_NEED)
        if recs is None:
            got = {f for f in t["fields"] if f}
            if {"amt", "pr"} <= got and not _P8_RECV_HINT.search(" ".join(t["cols"])):
                # 금호건설형 메타표(구분·공사명·발주처·진행률·계약금액·계약일·공사기한) — 미청구·미수금
                # 열 자체가 없다. 금액표는 같은 절에 따로 있으므로 미지 헤더가 아니라 그냥 지나간다.
                reason = "meta_p8"
            elif sum(1 for f in t["fields"] if f) >= 3 and len(t["rows"]) >= 3:
                unknown.append({"cols": t["cols"], "n": len(t["rows"])})
                reason = "near_miss"
            elif len(_core(t, _P8_NEED)) >= 2:
                reason = "few_fields"          # 핵심 필드는 걸렸지만 필드<3 또는 행<3 — 조용히 지나가던 표
            else:
                continue                       # 대손충당금·공정가치 표 등 '구분' 하나만 걸리는 표 — 후보 아님
            r = _hdr_meta(t, i)
            r.update(reason=reason, rows=t["rows"], spans=t["spans"])
            rejected.append(r)
            continue
        # III-8의 '계약상 완성기한'은 II-4에서 ed로 매핑되므로 여기서 p8_dl로 옮겨 받는다
        for rec in recs:
            if not rec.get("p8_dl") and rec.get("ed"):
                rec["p8_dl"] = rec["ed"]
        lead = t["lead"]
        d = _hdr_meta(t, i)
        d.update(basis=_basis_of(lead), n=len(recs), rows=recs, n_raw=t["n_raw"], n_rec=len(recs))
        picked.append(d)
    # lead에서 구분을 못 읽은 표가 2개면 관례(연결 먼저)를 적용한다.
    # 표가 하나뿐일 때는 단정하지 않고 None으로 남긴다 — 회사마다 다르다
    # (HDC현산은 2023Q4부터 연결만 공시한다). 호출측이 직전 분기 연속성으로 판정한다.
    unlabeled = [t for t in picked if t["basis"] is None]
    if len(unlabeled) == 2:
        unlabeled[0]["basis"], unlabeled[1]["basis"] = "연결", "별도"
    return {"tables": picked, "unknown_headers": unknown, "rejected": rejected}
