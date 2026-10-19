#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_xi1 — 정기보고서 XI-1 「공시내용 진행 및 변경사항」의 **나. 단일판매ㆍ공급계약 진행 현황** 표.

2024Q4 부터 반기·사업보고서에 실린다(분기보고서는 대개 없음 — '표 없음'이 정상). 이 모듈은 **최소 구현**이다
(설계 C·U3): 절 원문 → 표 파싱 → 머리행 지도(rep['headers']['xinb'], tag '나')·원문 캐시
(assets/xi1_cache/<co>/<q>.json)·미지 머리행 대기열. DATA.xip 갱신(_apply_xi1: 사업장 매칭·mt 판정)은
하지 않는다 — 원본 7사 실측상 이름 자동 정확일치가 25% 뿐이고 63% 가 사람 판정이라, 매칭 규칙과 사람 입력
파일 형식을 정하기 전에 데이터에 섞지 않는다.

왜 전역 사전(kce_lib.COL_ALIAS)을 쓰지 않는가: `_HDR_VOCAB = set(COL_ALIAS)` 라 XI 어휘를 전역에 넣으면
6개 탭의 머리행 감지가 함께 바뀌고, '계약명'·'계약상대방'·'구분'은 II-4/III-8 에서 다른 필드다.
그래서 XI 사전·어휘·머리행 상한(4줄)은 전부 이 모듈 안에서만 쓴다.

원문 방언(2026Q2 14사 실측):
  · 머리행 2~4단(`계약내역 | 계약명`, `판매ㆍ공급금액 | 당기 | 누적`), 대부분 td 머리행.
  · 단위: lead 백만원 9사 / 억원 금호·코오롱 / 원 삼성E&A. 삼성물산·대우는 `계약금액총액(원)` 열만 원이고
    나머지 열은 백만원 → **열 단위가 표 단위보다 앞선다**.
  · 계약내역 한 칸에 `계약명 : … 계약상대방 : … 계약기간 : …` 을 담는 회사 9사(줄바꿈이 지워져 라벨이
    앞 값에 붙기도 한다 — DL이앤씨·계룡·HS화성).
  · 외화 계약금액 `2,663,571,150 (USD)` → 금액 None + cur.
  · 삼성E&A 는 한 계약금액 칸(rowspan)에 계약명 2줄 — 금액이 위에서 흘러내린 줄은 앞 계약에 이름만 덧붙인다.
"""
import json
import os
import re

import hdrmap
from kce_lib import atomic_write, norm_col, num_of
import kce_parse as KP

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "assets", "xi1_cache")

XI_ALIAS = {
    "신고일자": "xi_dt", "신고일자(최초)": "xi_dt", "신고일자(최근)": "xi_dt", "신고일자(최종)": "xi_dt",
    "신고일자(정정)": "xi_dt", "공시일자": "xi_dt",
    "계약내역": "xi_nm", "계약내역계약명": "xi_nm", "계약내역(공사명)": "xi_nm", "계약명": "xi_nm",
    "계약내역계약상대방": "xi_cl", "계약상대방": "xi_cl",
    "계약내역계약시작월": "xi_sd", "계약내역계약기간시작일": "xi_sd",
    "계약내역계약종료월": "xi_ed", "계약내역계약기간종료일": "xi_ed", "계약내역계약만기": "xi_ed",
    "계약내역계약기간": "xi_period",
    "계약금액총액": "xi_amt", "계약금액총액(원)": "xi_amt", "계약금액총액(부가세포함)": "xi_amt",
    "계약금액": "xi_amt", "계약내역계약금액총액": "xi_amt",
    "판매공급금액당기": "xi_supCur", "판매공급금액누적": "xi_supCum",
    "판매공급금액(백만원)당기": "xi_supCur", "판매공급금액(백만원)누적": "xi_supCum",
    "판매공급금액(매출액)당기": "xi_supCur", "판매공급금액(매출액)누적": "xi_supCum",
    "대금수령금액당기": "xi_recvCur", "대금수령금액누적": "xi_recvCum",
    "대금수령금액(백만원)당기": "xi_recvCur", "대금수령금액(백만원)누적": "xi_recvCum",
    "대금수령당기": "xi_recvCur", "대금수령누적": "xi_recvCum",
    "비고": "xi_note", "대금미수령사유": "xi_note", "향후추진계획": "xi_note",
    "대금미수령사유및향후추진계획": "xi_note", "향후추진계획판매공급이행": "xi_note",
    "향후추진계획대금수령": "xi_note", "변동가능성": "xi_note",
    "계약내역기타사항": "xi_etc", "계약내역주요계약조건": "xi_etc", "계약내역조건부계약금액": "xi_etc",
    "계약내역계약금선급금유무": "xi_etc", "계약내역대금지급조건등": "xi_etc",
    "구분": "xi_kind",
}
# 다단 머리행의 부모 줄 낱말 — 이것만으로 된 줄도 머리행으로 본다(지역 어휘, 전역 불변).
_XI_PARENT = {"계약내역", "판매공급금액", "대금수령금액", "계약금액총액", "판매공급금액(백만원)",
              "대금수령금액(백만원)", "판매공급금액(매출액)", "계약금액총액(원)", "향후추진계획", "계약기간",
              "계약상대방", "계약명", "계약시작월", "계약종료월", "기타사항", "주요계약조건", "조건부계약금액",
              "계약금선급금유무", "대금지급조건등", "계약만기", "공시일자", "시작일", "종료일", "당기", "누적"}
XI_VOCAB = set(KP._HDR_VOCAB) | set(XI_ALIAS) | _XI_PARENT
# 대금수령 열이 없는 회사가 있다(`판매.공급금액 당반기|누적금액` 만) — 계약·금액·판매공급 누적이 서면 읽는다.
# 이름 칸 없이 계약상대방으로 계약을 가리키는 표도 있다(상대방을 이름으로 쓴다).
NEED = {"xi_nm", "xi_amt", "xi_supCum"}
# 파서 판 — 해석 규칙이 바뀌면 올린다. 섹터 탭(xi1_sector)은 판이 다른 해석 결과를 로컬 원문으로 다시 만든다.
PARSER_REV = "2026-10-19c"
MONEY = ("xi_amt", "xi_supCur", "xi_supCum", "xi_recvCur", "xi_recvCum")
# 판매공급·대금수령 문구가 머리행에 있는데 NEED 가 안 서면 '읽어야 할 표를 못 읽은 것'(미지).
# 가 표(신고일자|제목|신고내용|진행상황)·사유 부표는 이 문구가 없어 경보하지 않는다.
_XI_HINT = re.compile(r"판매.?공급|대금\s*수령")

_COL_UNIT = re.compile(r"\((원|천원|백만원|억원)\)")
_UNIT_MUL = {"원": 1e-6, "천원": 1e-3, "백만원": 1.0, "억원": 100.0, "조원": 1e6}
_CUR = re.compile(r"\(([A-Z]{3})\)|\b([A-Z]{3})\s*[\d,]")
_LBL = (r"(?:체결\s*계\s*약\s*명|계\s*약\s*명|계\s*약\s*상\s*대(?:\s*방|\s*자)?|계\s*약\s*기\s*간|계약\s*\(수주\)\s*일자|주요\s*계약\s*조건|"
        r"계약금[ㆍ·,]\s*선급금\s*유무|대금\s*지급\s*조건\s*등?|조건부\s*계약금액|기타(?:\s*투자판단과\s*관련한\s*중요사항)?)")
# 라벨은 앞 값에 붙어 올 수 있다(줄바꿈이 지워진 원문) — 경계를 요구하지 않고, 글머리 `1) `만 공백 뒤에서 본다.
# 글머리: `-`·`●`·`ㅇ계약명 :`(한전기술)·`1.계약명: … 2.계약상대:`(제룡전기) — 한글 자모 ㅇ·마침표는 가-힣 경계 밖이라
# 따로 두고, 번호 `2.` 는 앞 값의 꼬리로 남지 않게 경계로 먹는다.
_SPLIT = re.compile(r"(?:\s*\d{1,2}\.\s*|^|\s|[-●•ㅇ○◦▪■□▶.]|(?:^|\s)\d\)\s*|(?<=[가-힣A-Za-z0-9)\]]))(" + _LBL + r")\s*[:：]\s*")
# 꼬리: 글머리 기호와, 줄바꿈이 지워져 다음 항목 번호가 붙은 `검사장비2.`(다음 줄 `2. 계약상대`)의 `2.`.
_TRAIL = re.compile(r"(?:[\s\-●•ㅇ○]+|(?<=[가-힣A-Za-z)])\s*\d{1,2}\.)+$")
# 머리: `1. 판매공급계약 내용 -ELECTRICAL …`·`1. 내용 : SMART WINDOW …` — 번호와 '내용' 라벨은 이름이 아니다.
_HEAD = re.compile(r"^\s*(?:\d{1,2}[.)]\s*)?(?:(?:판매\s*[ㆍ·.]?\s*공급\s*)?(?:계약\s*)?내용\s*[:：\-–]\s*)?")
_DATE = re.compile(r"((?:19|20)\d{2}|['`’]?\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")


# ── 낱말 규칙 해석기(2026-10-16, 6개 수주 섹터 304사 실측) ─────────────────────────────
# 정확 일치 사전(XI_ALIAS)만으로는 회사마다 다른 꼴을 못 따라간다 — 조선·방산·원전·전력·항공·반도체 304사 2026Q2
# 반기보고서에서 머리행 변형이 20종 넘게 나왔다: `판매ㆍ공급금액(원) 당기(2026.01.01~06.30)`·`판매.공급금액 당반기`·
# `대금수령액 누적`·`계약내용 체결계약명`·`계약금액총액 통화`·`계약금액 총액(V.A.T 제외)`·`판매공급금액(매출인식)` 등.
# 괄호(날짜·단위·각주·부연)와 구분 기호를 걷어낸 뒤 **의미 낱말**로 판정한다. 순서가 중요하다 — 서술 열(향후 추진계획·
# 사유)을 먼저 빼고, 금액·상대방·기간을 이름(계약내역)보다 먼저 본다(`계약내역 계약금액총액`은 이름이 아니라 금액).
_PAREN_ANY = re.compile(r"\([^)]*\)?|（[^）]*）")
_SEP = re.compile(r"[\s.,·ㆍ/\-_:*※]+")


def _bare(ncol):
    return _SEP.sub("", _PAREN_ANY.sub("", ncol or "")).lower()


def _rule(ncol):
    s = _bare(ncol)
    if not s:
        return None
    if re.search(r"향후추진|추진계획|사유|변동가능|비고|진행상황|진행사항|이행$|^이행|판매공급이행", s):
        return "xi_note"
    if re.search(r"공급계약내용|계약내용$", s):
        return "xi_nm"
    if "판매공급" in s or "공급금액" in s:
        if "누적" in s:
            return "xi_supCum"
        if re.search(r"당기|당반기|당분기", s):
            return "xi_supCur"
        return None
    if "대금수령" in s or "수령금액" in s or "수령액" in s:
        if "누적" in s:
            return "xi_recvCum"
        if re.search(r"당기|당반기|당분기", s):
            return "xi_recvCur"
        return None
    if re.search(r"신고일|공시일", s):
        return "xi_dt"
    if re.search(r"조건부|주요계약조건|기타사항|선급금|지급조건", s):
        return "xi_etc"
    if re.search(r"계[약액]금액|계약금총액|계약총액|수주금액", s):       # `계액금액 총액`(한화엔진 2025Q4 오기)
        return "xi_cur" if s.endswith("통화") else "xi_amt"
    if s == "통화":
        return "xi_cur"
    if "계약명" in s:                 # `계약명계약상대방계약기간` 한 칸 — 이름이 먼저(셀 분리는 split_detail)
        return "xi_nm"
    if "계약상대" in s:
        return "xi_cl"
    if re.search(r"시작일|개시일|착공|계약일$", s):
        return "xi_sd"
    if re.search(r"종료일|납기|만기|완료일|종료월", s):
        return "xi_ed"
    if "계약기간" in s:
        return "xi_period"
    if re.search(r"계약내역|계약내용|신고내용|공시내용|공사명|사업명", s):
        return "xi_nm"
    if s == "단위":
        return "xi_unit"
    if s in ("번호", "no", "구분", "순번"):
        return "xi_kind"
    return None


def field_of(ncol):
    return XI_ALIAS.get(ncol) or _rule(ncol)


class _Vocab:
    """머리행 감지 어휘 — 정확 집합 + 낱말 규칙(부모 줄 `판매공급금액`·`당기`·`누적` 포함). kce_parse 가 `in` 만 쓴다."""
    _PARENT = re.compile(r"^(판매공급금액|판매공급|대금수령금액|대금수령액|대금수령|계약내역|계약내용|당기|당반기|누적|금액|통화|"
                         r"계약금액|체결계약명|계약상대방|시작일|종료일)$")

    def __contains__(self, ncol):
        if ncol in XI_VOCAB:
            return True
        b = _bare(ncol)
        # 머리행 낱말은 짧다. '가' 표 본문 칸(`신고내용 싱가폴 Tekong … 계약금액: 508,837…`)이 규칙 낱말을 품어
        # 머리행으로 빨려 들어가지 않게 길이·숫자로 거른다(현대건설 2026Q2 회귀).
        if len(b) > 28 or re.search(r"\d{3,}", b):
            return False
        return bool(_rule(ncol)) or bool(self._PARENT.match(b))


_VOCAB = _Vocab()
_COL_UNIT2 = re.compile(r"[(（][^)）]*?(백만원|천원|억원|원)")


def col_unit(col):
    """열 이름 안의 단위 — `(원)`·`(원, VAT 포함)`·`(억원, 외화 별도)`·`(단위: 백만원)`."""
    m = _COL_UNIT2.search(col or "")
    return _UNIT_MUL[m.group(1)] if m else None


def split_detail(cell):
    """계약내역 셀 → {'계약명','계약상대방','계약기간',…}. 라벨이 없으면 셀 전체가 계약명."""
    cell = (cell or "").strip()
    parts = _SPLIT.split(cell)
    if len(parts) < 3:
        return {"계약명": _clean_nm(cell)}
    out = {}
    for i in range(1, len(parts) - 1, 2):
        lab = re.sub(r"[\sㆍ·]", "", parts[i])
        val = _TRAIL.sub("", parts[i + 1].strip())
        if "계약명" in lab:
            out.setdefault("계약명", _clean_nm(val))
        elif lab.startswith("계약상대"):
            out.setdefault("계약상대방", val)
        elif lab.startswith("계약기간"):
            out.setdefault("계약기간", val)
        elif lab.startswith("계약(수주)일자"):
            out.setdefault("계약일자", val)
        else:
            out["기타"] = (out.get("기타", "") + " " + lab + ":" + val).strip()
    if "계약명" not in out:
        out["계약명"] = _clean_nm(parts[0])
    return out


def _clean_nm(v):
    v = _HEAD.sub("", (v or "").strip().lstrip("-ㅇ○").strip())
    return _TRAIL.sub("", v).strip()


def norm_dt(s):
    """신고일자 → YYYY.MM.DD. `26.06.25(변경계약)`처럼 2자리 연도는 20YY. 못 읽으면 None."""
    m = _DATE.search(s or "")
    if not m:
        return None
    y, mo, d = m.groups()
    y = int("20" + y[-2:]) if len(y.lstrip("'`’")) == 2 else int(y)      # `26.06.25`·`25.1.13`(세명전기)
    mo, d = int(mo), int(d)
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return "%04d.%02d.%02d" % (y, mo, d)


def _scaled(v, mul):
    if v is None:
        return None
    x = v * mul
    return int(x) if float(x).is_integer() else round(x, 6)


# ── 금액 칸 안의 단위·통화(2026-10-16, 섹터 304사 2026Q2 실측 150행) ─────────────────────
# 숫자만 있는 칸은 열·표 단위를 따른다(num_of). 그 밖의 꼴:
#   `676억원`·`20,472백만원`·`21,749,000,000원`       → 칸 안 단위가 열 단위보다 앞선다
#   `$15,544,340.00(19,251,665,090원)`               → 외화 + 원화 괄호 — 원화가 계약금액, 외화는 참고
#   `2,755,800(USD2,000,000)`·`3,787,412(USD 2,690,000.)` → 앞의 맨숫자 = 원화(열 단위), 괄호 외화
#   `USD 9,036,204(KRW 11,980,199,051)`·`KRW 2,770,000,000` → KRW 표시 숫자 = 원화(열 단위)
#   `USD56,784천`·`(천외화,백만원)` 열의 `USD 3,365,400`   → 외화 천 단위
#   `3,117,058.50(총액)`                              → 숫자 없는 괄호 주석은 걷어낸다
#   `유보`·`공시유보`                                  → 금액 없음 + withheld
_INL = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)\s*(조원|억원|백만원|천원|원)(?![가-힣])")
_KRW = re.compile(r"(?:KRW|￦|₩)\s*(-?\d[\d,]*(?:\.\d+)?)")
# 통화가 앞(`USD 9,036,204`)인 꼴을 먼저 찾는다 — 뒤 꼴(`187,674,868.5(USD)`)을 한 정규식에 섞으면
# `3,787,412(USD 2,690,000.)` 의 원화 맨숫자를 외화로 잡는다.
_FXA = re.compile(r"(?:\b(?!KRW)([A-Z]{3})|([$€¥£]))\s*(-?\d[\d,]*(?:\.\d+)?)\s*(천|백만)?")
_FXB = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)\s*(천|백만)?\s*[(（]?\s*(?!KRW)([A-Z]{3})\b")
_SYM = {"$": "USD", "€": "EUR", "¥": "JPY", "£": "GBP"}
_HOLD = re.compile(r"유보|비공개|영업\s*비밀")
_NOTE_PAREN = re.compile(r"\([^)\d]*[가-힣][^)\d]*\)")       # `(총액)`·`(VAT 포함)` — `(USD)` 는 통화라 남긴다


def _f(x):
    return float(x.replace(",", "").rstrip("."))


def money_cell(raw, mul, fx_mul=1):
    """금액 칸 → (원화 백만원|None, 통화|None, 외화 금액|None, 유보 여부)."""
    s = (raw or "").strip()
    if "%" in s:
        return None, None, None, False      # `60%`·`100%` — 금액 칸에 비율을 적은 회사(넥스틴 대금수령). 금액으로 읽지 않는다
    v = num_of(s)
    if v is None and s:
        v = num_of(_NOTE_PAREN.sub("", s))
    if v is not None:
        return _scaled(v, mul), None, None, False
    if not s or s in ("-", "–", "—"):
        return None, None, None, False
    if not re.search(r"\d", s):
        return None, None, None, bool(_HOLD.search(s))
    krw = None
    m = _INL.search(s)
    if m:
        krw = _scaled(_f(m.group(1)), _UNIT_MUL[m.group(2)])
    elif _KRW.search(s):
        krw = _scaled(_f(_KRW.search(s).group(1)), mul)
    cur = fx = None
    mf, mb = _FXA.search(s), None
    if not mf:
        mb = _FXB.search(s)
    if mf or mb:
        cur, num, k = ((mf.group(1) or _SYM[mf.group(2)], mf.group(3), mf.group(4)) if mf
                       else (mb.group(3), mb.group(1), mb.group(2)))
        fx = _f(num) * {"천": 1e3, "백만": 1e6}.get(k, fx_mul)
        fx = int(fx) if float(fx).is_integer() else round(fx, 2)
        if krw is None:
            m0 = re.match(r"^\s*(-?\d[\d,]*(?:\.\d+)?)\s*[(（]", s)
            if m0 and m0.group(1) != num:       # 맨숫자(원화) + 괄호 외화
                krw = _scaled(_f(m0.group(1)), mul)
    return krw, cur, fx, False


def _records(t, idx):
    scale = KP.unit_scale(t.get("lead"), t.get("cols"))
    units = {f: (col_unit(t["cols"][i]) or scale) for f, i in idx.items() if f in MONEY}
    rsp = t.get("rspan") or []
    out = []
    for ri, r in enumerate(t["rows"]):
        def g(f):
            i = idx.get(f)
            return (r[i] if i is not None and i < len(r) else "").strip()
        flags = rsp[ri] if ri < len(rsp) else []
        carried = (out and idx["xi_amt"] < len(flags) and flags[idx["xi_amt"]]
                   and idx["xi_supCum"] < len(flags) and flags[idx["xi_supCum"]])
        d = split_detail(g("xi_nm"))
        if carried:
            # 계약금액·판매공급이 위에서 흘러내린 줄 = 같은 계약의 둘째 이름(삼성E&A). 금액을 두 번 세지 않는다.
            if d.get("계약명"):
                out[-1].setdefault("nm_more", []).append(d["계약명"])
            continue
        amt_raw = g("xi_amt")
        ru = g("xi_unit")
        row_units = units
        mu = re.search(r"백만원|천원|억원|원", ru)
        if mu:      # 행마다 `단위` 칸을 두는 표(제룡전기) — 그 행 금액 전부에 적용
            row_units = {f: _UNIT_MUL[mu.group(0)] for f in units}
        fxm = {f: (1e3 if re.search(r"천\s*외화", t["cols"][i]) else 1) for f, i in idx.items() if f in MONEY}
        cells = {f: money_cell(g(f), row_units[f], fxm[f]) for f in MONEY if f in idx}
        vals = {f: c[0] for f, c in cells.items()}
        withheld = any(c[3] for c in cells.values())
        cur, amt_fx = (cells["xi_amt"][1], cells["xi_amt"][2]) if "xi_amt" in cells else (None, None)
        raw_amt = num_of(_NOTE_PAREN.sub("", amt_raw)) if amt_raw else None
        if not mu and re.fullmatch(r"[A-Za-z]{3}", ru or ""):
            vals = {f: None for f in vals}      # 행 단위가 외화(제룡전기 USD) — 그 행 금액은 원화로 셈하지 않는다
            if raw_amt is not None:
                cur, amt_fx = ru.upper(), raw_amt * fxm.get("xi_amt", 1)
        cc = (g("xi_cur") or (ru if re.fullmatch(r"[A-Za-z]{3}", ru or "") else "")).upper().replace("￦", "")
        if cc and cc not in ("KRW", "원", "-") and re.fullmatch(r"[A-Z]{3}", cc):
            cur, vals["xi_amt"] = cc, None          # 통화 열이 외화면 계약금액은 원화로 셈하지 않는다
            if raw_amt is not None:
                amt_fx = raw_amt * fxm.get("xi_amt", 1)
        if amt_fx is not None and float(amt_fx).is_integer():
            amt_fx = int(amt_fx)
        if vals.get("xi_amt") is None and amt_raw not in ("", "-") and not cur:
            m = _CUR.search(amt_raw)
            if m:
                cur = m.group(1) or m.group(2)
        nm = d.get("계약명") or ""
        dt = g("xi_dt")
        # 주석 줄(신고일자가 날짜가 아니고 금액이 전부 비었다)과 합계 줄은 계약이 아니다.
        if not nm and all(v is None for v in vals.values()):
            continue
        if re.sub(r"\s", "", nm) in ("합계", "계", "총계", "소계"):
            continue
        if dt and norm_dt(dt) is None and all(v is None for v in vals.values()):
            continue
        rec = {"nm": nm, "cl": d.get("계약상대방") or g("xi_cl") or None,
               "period": d.get("계약기간") or ((g("xi_sd") + " ~ " + g("xi_ed")).strip(" ~") or g("xi_period") or None),
               "dt": norm_dt(dt), "dt_raw": dt or None, "amt_raw": amt_raw or None, "cur": cur}
        rec.update({k.replace("xi_", ""): v for k, v in vals.items()})
        if amt_fx is not None:
            rec["amt_fx"] = amt_fx          # 외화 계약금액(원화 환산은 원장·환율로 — kce_xi1 은 하지 않는다)
        if cur:
            # 외화 계약 행의 공급·수령 칸 맨숫자(표 단위 미적용). 그 외화로 적은 회사(진성이엔지 행 통화 USD)와 원화로 적은
            # 회사(풍산)가 섞여 있어 여기서 판정하지 않는다 — xi1_sector.metrics 가 계약금액·원장 금액과 견줘 고른다.
            fxv = {f.replace("xi_", ""): num_of(_NOTE_PAREN.sub("", g(f))) for f in MONEY if f in idx and f != "xi_amt"}
            fxv = {k: v * fxm.get("xi_" + k, 1) for k, v in fxv.items() if v is not None}
            if fxv:
                rec["fx"] = {k: (int(v) if float(v).is_integer() else round(v, 2)) for k, v in fxv.items()}
        if withheld:
            rec["withheld"] = True          # `유보`·`공시유보` — 금액 비공개(경영상 비밀)
        out.append(rec)
    return out


def _rescale(rows, fields, k):
    m = 10 ** k
    for r in rows:
        for f in fields:
            if r.get(f) is not None:
                x = r[f] * m
                r[f] = int(x) if float(x).is_integer() else round(x, 6)


def _median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


def _unit_sanity(tab):
    """표 안 자릿수 점검. ① 계약금액과 판매공급 누적의 비가 1,000배 단위로 어긋나면 계약금액 열 단위가 틀린 것
    (SK오션플랜트: 머리행 `계약금액총액(원)` 인데 값은 백만원) — 판매공급 열에 맞춰 계약금액을 고친다(unit_fix).
    ② 그래도 계약금액 중앙값이 백만원 기준 5조를 넘으면 단위 캡션 없이 원·천원으로 적은 표일 가능성 — 고치지 않고
    unit_suspect 로 표시한다(원장 금액이 있으면 calibrate 가 맞춘다)."""
    import math
    rows = tab["rows"]
    lr = [math.log10(r["supCum"] / r["amt"]) for r in rows
          if r.get("amt") and r.get("supCum") and r["amt"] > 0 and r["supCum"] > 0]
    med = _median(lr)
    if med is not None and len(lr) >= 2:
        k = round(med / 3) * 3
        tight = sum(1 for x in lr if abs(x - k) < 0.5) >= max(2, int(len(lr) * 0.8))
        # 판매공급 누적이 계약금액의 1,000배를 넘는 것만 불가능 — 반대(누적이 훨씬 작다)는 갓 착공한 계약에서 실제로
        # 나온다(대한조선·SFA넥셀 오교정). 그래서 k > 0 일 때만, 그리고 비가 한 자리에 몰릴 때만 고친다.
        if k > 0 and tight:
            _rescale(rows, ["amt"], k)
            tab["unit_fix"] = "amt_vs_supply x1e%d" % k
    amts = [r["amt"] for r in rows if r.get("amt")]
    if amts and _median(amts) > 2e7:     # 백만원 기준 20조 — 한화 비스마야(14.7조)는 실제 금액이라 이 아래
        tab["unit_suspect"] = True
    # ③ 계약금액 중앙값이 백만원 기준 1 미만(100만원 미만)이면 머리행 `(원)` 인데 값은 백만원인 표(넥스틴 2026Q2 `10,606`).
    #    공시 대상 계약이 100만원 미만일 수는 없다 — 중앙값이 1억(100) 이상이 되는 가장 작은 10^3k 로 표 금액 전부를 옮긴다.
    elif amts and _median(amts) < 1:
        k = next(k for k in (3, 6, 9) if _median(amts) * 10 ** k >= 100 or k == 9)
        _rescale(rows, ["amt", "supCur", "supCum", "recvCur", "recvCum"], k)
        tab["unit_fix"] = (tab.get("unit_fix", "") + " amt_tiny x1e%d" % k).strip()


def calibrate(parsed, ref, sim=0.3):
    """원장(I001 단일판매ㆍ공급계약 공시) 금액으로 표 단위를 맞춘다. ref = [(계약명, 금액 백만원)].
    이름이 닮은 짝들의 금액 비 log10 중앙값이 3·6(또는 −3·−6)에 붙으면 표 금액 전체를 그만큼 옮긴다.
    짝이 둘 이상이고 그 짝들이 같은 방향일 때만(한 짝은 다른 계약일 수 있다). 반환: 고친 표 수."""
    import math
    fixed = 0
    for t in parsed["tables"]:
        lr = []
        for r in t["rows"]:
            if not r.get("amt"):
                continue
            best = max(ref, key=lambda c: _sim(r["nm"], c[0]), default=None)
            if best and best[1] and _sim(r["nm"], best[0]) >= sim:
                lr.append(math.log10(r["amt"] / best[1]))
        med = _median(lr)
        if med is None:
            continue
        k = round(med / 3) * 3
        agree = sum(1 for x in lr if abs(x - k) < 0.5)
        exact = sum(1 for x in lr if abs(x - k) < 0.005)     # 비가 정확히 10^k(±1%) — 짝 하나로도 단위 증거
        if k and (agree >= max(2, len(lr) // 2) or (exact >= 1 and agree == len(lr))):
            _rescale(t["rows"], ["amt", "supCur", "supCum", "recvCur", "recvCum"], -k)
            t["unit_fix"] = (t.get("unit_fix", "") + " ledger x1e%d" % -k).strip()
            t.pop("unit_suspect", None)
            fixed += 1
    return fixed


def raw_tables(html):
    """절 HTML → 머리행만 평탄화한 원문 표(라벨·값 문자열 그대로). 섹터 탭은 이것을 커밋해 두고 파서가 자라면 HTML 없이
    interpret() 만 다시 돈다(COMMON §0-4 원문 라벨·값 보존)."""
    return KP.parse_tables(html, max_header_rows=4, vocab=_VOCAB, keep_rowspan=True)


def parse_xi1(html):
    """절 HTML → {'tables':[{lead,cols,ncols,fields,n_raw,n_rec,unit,rows}], 'rejected', 'unknown_headers'}."""
    return interpret(raw_tables(html))


def interpret(tables):
    """raw_tables() 결과 → parse_xi1 과 같은 꼴. 표 순서(idx)는 원문 순서."""
    picked, rejected, unknown = [], [], []
    for i, t in enumerate(tables):
        fields = [field_of(c) for c in t["ncols"]]
        idx = {}
        for j, f in enumerate(fields):
            if f and f not in idx:
                idx[f] = j
            elif f == "xi_amt" and "총액" in _bare(t["cols"][j]) and "총액" not in _bare(t["cols"][idx[f]]):
                idx[f] = j        # `확정계약금액 | 조건부 계약금액 | 계약금액총액` — 총액이 계약금액이다(비에이치아이)
        base = {"idx": i, "lead": t.get("lead") or "", "cols": list(t["cols"]), "ncols": list(t["ncols"]),
                "fields": fields, "n": t.get("n_raw") or len(t["rows"])}
        if "xi_nm" not in idx and "xi_cl" in idx:
            idx["xi_nm"] = idx["xi_cl"]
        if NEED.issubset(idx):
            recs = _records(t, idx)
            tab = dict(base, n_raw=base["n"], n_rec=len(recs), rows=recs,
                       unit=KP.unit_scale(t.get("lead"), t.get("cols")))
            _unit_sanity(tab)
            picked.append(tab)
            continue
        # '향후 추진계획 판매ㆍ공급 이행' 같은 서술 열(xi_note)은 문구가 겹쳐도 금액 열이 아니다 — 3) 향후 추진계획
        # 부표(7사)가 미지로 올라오던 오탐. 서술 열을 뺀 나머지 머리행에서만 판매공급·대금수령을 찾는다.
        head = " ".join(c for c, f in zip(t["cols"], fields) if f != "xi_note")
        hint_cols = [j for j, (c, f) in enumerate(zip(t["cols"], fields)) if f != "xi_note" and _XI_HINT.search(c)]
        cells = [r[j] for r in t["rows"] for j in hint_cols if j < len(r) and r[j].strip() not in ("", "-")]
        narrative = bool(cells) and sum(1 for c in cells if num_of(c) is not None) < 0.3 * len(cells)
        if narrative:
            # 판매공급·대금수령 열에 숫자가 아니라 문장이 든 표('판매ㆍ공급 이행 | 대금수령' 계획 표) — 미지가 아니다.
            rejected.append(dict(base, reason="no_core"))
        elif t["cols"] and _XI_HINT.search(head) and t["rows"]:
            unknown.append({"cols": list(t["cols"]), "n": len(t["rows"])})
            rejected.append(dict(base, reason="near_miss", rows=t["rows"]))
        elif t["cols"] and any(fields):
            rejected.append(dict(base, reason="no_core"))
    return {"tables": picked, "rejected": rejected, "unknown_headers": unknown}


def headers_of(parsed):
    """rep['headers']['xinb'] 항목 — 상류 지도 관례대로 tag '나'(76표 전부), 채택표만 pick True."""
    items = ([(t["idx"], t, True) for t in parsed["tables"]]
             + [(r["idx"], r, False) for r in parsed.get("rejected") or []])
    out = []
    for _i, t, ok in sorted(items, key=lambda x: x[0]):
        out.append({"cols": t["cols"], "ncols": t["ncols"], "fields": t["fields"], "n": t["n"],
                    "n_rec": t.get("n_rec") if ok else None, "lead": KP.lead_tail(t.get("lead")),
                    "tag": "나" if ok else "", "pick": ok, "reason": "picked" if ok else t["reason"]})
    return out


def cache_path(co, q, root=None):
    base = os.path.join(root, "xi1_cache") if root else CACHE
    return os.path.join(base, co, "%s.json" % q)


def write_cache(co, q, parsed, rcp=None, root=None):
    doc = {"co": co, "quarter": q, "rcpNo": rcp,
           "tables": [{"cols": t["cols"], "n": t["n"], "n_rec": t["n_rec"], "unit": t["unit"],
                       "lead": KP.lead_tail(t.get("lead")), "rows": t["rows"]} for t in parsed["tables"]]}
    p = cache_path(co, q, root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    atomic_write(p, json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    return p


def apply(co, q, raw_dir, D, k, rep, hdr_root=None, queue=False, cache_root=None):
    """kce_build.update_quarter 의 XI-1 단계(fail-soft). 원문이 없으면 아무것도 적지 않는다(지도에 절 키 없음 =
    그 분기 기록 안 함). 표가 없으면 빈 목록('봤는데 표 없음'). 미지는 rep['xi1_status'] + 대기열 — 예외로
    II-4/III-8 갱신을 막지 않는다. D 가 주어지면 확정 매칭만 DATA.xip 에 쓰고 나머지는 검토 목록(apply 때)."""
    path = os.path.join(raw_dir, "%s_xi1.html" % co)
    if not os.path.exists(path):
        rep["xi1_status"] = "absent"
        return None
    with open(path, encoding="utf-8") as f:
        parsed = parse_xi1(f.read())
    rep["headers"]["xinb"] = headers_of(parsed)
    rep["xi1_rows"] = sum(t["n_rec"] for t in parsed["tables"])
    if parsed["unknown_headers"]:
        rep["xi1_status"] = "unknown_headers"
        if queue:
            from kce_lib import CORP
            for r in parsed["rejected"]:
                if r["reason"] != "near_miss":
                    continue
                hdrmap.enqueue("kce", {"kind": "unknown", "key": co, "role": "xi", "quarter": q,
                                       "cols_raw": r["cols"], "ncols": r["ncols"], "fields": r["fields"],
                                       "n": r["n"], "lead": KP.lead_tail(r.get("lead")),
                                       "name": CORP[co]["name"], "stock": CORP[co]["stock"]},
                               root=hdr_root, strict=False)
    else:
        rep["xi1_status"] = "ok" if parsed["tables"] else "no_table"
    if queue and parsed["tables"]:
        write_cache(co, q, parsed, root=cache_root)
    if D is not None and parsed["tables"]:
        rows = [r for t in parsed["tables"] for r in t["rows"]]
        m = match_rows(D, k, rows, load_fill(co))
        rep["xi1_matched"] = apply_data(D, k, rows, m)
        rep["xi1_review"] = sum(1 for x in m if not x[1])
        if queue:
            write_review(co, q, rows, m, D)
    return parsed


# ── DATA.xip 반영(2026-10-13) — 사업장 매칭 ─────────────────────────────────
# 정답지: 라이브 7사 DATA 에 원본 사이트가 사람 판정까지 끝낸 2026Q2 연결 320건이 있다. 아래 규칙을 그 정답지로
# 평가해 **오매칭 0** 일 때만 데이터에 쓴다(tests/test_xi1.py TestXi1Match).
#   · 이력(warm): 직전 분기들의 XI-1 계약명(xip.nm·xipFull.계약명)과 정규화 이름이 같고 그 사업장이 유일 → 매칭.
#     같은 계약이 분기마다 다시 실리는 표라 가장 강한 신호다(실측 255/259 자동, 오매칭 0).
#   · 금액(cold): 판매공급 누적 = 그 분기 II-4 완성공사액(**±1백만원**, 실측 154/178 이 정확히 같다)인 사업장이 유일하고,
#     이름이 조금이라도 닮았거나(바이그램 Jaccard ≥ 0.2) 계약금액이 도급액 ±15%(또는 부가세 1.1배) → 매칭.
#     ±0.1% 로 느슨하게 두면 다른 계약이 우연히 걸린다(DL이앤씨 Gas Chemical ↔ 아크로 베스티뉴, 차이 0.07%).
#   · 이름(cold): 정규화 이름이 사업장 이름·이름 이력·III-8 품목과 같거나(6자 이상) 포함 관계이고, 그중 금액(누적≈완성공사액
#     ±1% 또는 계약금액≈도급액)이 맞는 후보가 하나 → 매칭.
#   · 그 밖은 **데이터에 쓰지 않고** 검토 목록(tools/assets/xi1_review.csv)에 후보와 근거를 남긴다. 신규(-11-) 사업장은
#     자동으로 만들지 않는다 — 이름이 다른 기존 사업장일 수 있다(원본도 '검토필요'·'수동보정'이 37%).
#   · 사람 판정: tools/assets/xi1_fill.csv (co,xi_name,site_id) — site_id 가 SKIP 이면 쓰지 않음. 자동 판정보다 우선.
# xifill{pend,chk} 는 원본 빌더의 xi1_fill 작업 카운터라 데이터로 재현되지 않는다(실측 34/51) — 건드리지 않는다.

import csv

_NOTE = re.compile(r"\(\*\d*\)|\*\d+\)?|\(주\d+\)")
XIP_ARR = ("amt", "supCur", "supCum", "recvCur", "recvCum")
FILL = os.path.join(HERE, "assets", "xi1_fill.csv")
REVIEW = os.path.join(HERE, "assets", "xi1_review.csv")
_REVIEW_COLS = ["co", "quarter", "xi_name", "amt", "supCum", "suggest_site", "suggest_name", "reason"]


def nkey(s):
    return re.sub(r"[\s()（）\[\]·ㆍ,.\-*'\"]", "", _NOTE.sub("", s or "")).lower()


def _bigr(s):
    s = nkey(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _sim(a, b):
    A, B = _bigr(a), _bigr(b)
    return len(A & B) / max(1, len(A | B))


def _near(a, b, tol=0.01):
    return a is not None and b is not None and b != 0 and abs(a - b) <= abs(b) * tol


def _amt_ok(a, b):
    if not a or not b:
        return False
    r = a / b
    return abs(r - 1) <= 0.15 or abs(r - 1.1) <= 0.01


def _at(arr, k):
    return arr[k] if isinstance(arr, list) and k < len(arr) else None


def _site_names(s):
    out = [s.get("nm") or ""]
    out += [n[1] for n in (s.get("names") or []) if isinstance(n, list) and len(n) > 1 and isinstance(n[1], str)]
    pf = (s.get("p8Full") or {}).get("품목")
    if isinstance(pf, list):
        out += [x for x in pf if isinstance(x, str)]
    return [x for x in out if x]


def load_fill(co, path=None):
    p = path or FILL
    out = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("co") or "").strip() == co:
                    out[nkey(r.get("xi_name"))] = (r.get("site_id") or "").strip()
    return out


def match_rows(D, k, rows, fill=None):
    """XI-1 행 → [(site_id|None, mt|None, how, suggest_site)]. mt None = 데이터에 쓰지 않음(검토)."""
    fill = fill or {}
    sites = D["sites"]
    sid = {s["id"]: s for s in sites}
    idx, prev = {}, {}
    for s in sites:
        for n in _site_names(s):
            idx.setdefault(nkey(n), set()).add(s["id"])
        x = s.get("xip") or {}
        names = [x.get("nm")] + [v for v in (((s.get("xipFull") or {}).get("계약명")) or [])[:k] if isinstance(v, str)]
        for n in names:
            if n:
                prev.setdefault(nkey(n), set()).add(s["id"])
    cmpk = {s["id"]: _at(s["s"].get("cmp"), k) for s in sites}
    out = []
    for r in rows:
        key = nkey(r["nm"])
        names = [r["nm"]] + list(r.get("nm_more") or [])
        f = fill.get(key)
        if f:
            if f == "SKIP" or f not in sid:
                out.append((None, None, "fill_skip", None))
            else:
                out.append((f, "매칭(수동보정)", "fill", f))
            continue
        if key in prev and len(prev[key]) == 1:
            s = next(iter(prev[key]))
            out.append((s, (sid[s].get("xip") or {}).get("mt") or "매칭", "prev_xi", s))
            continue
        sc = r.get("supCum")
        mon = [s for s, c in cmpk.items() if sc and sc >= 100 and c and abs(sc - c) <= 1]
        if len(mon) == 1:
            s = mon[0]
            simv = max(_sim(a, b) for a in names for b in (_site_names(sid[s]) or [""]))
            if simv >= 0.2 or _amt_ok(r.get("amt"), _at(sid[s]["s"].get("amt"), k)):
                out.append((s, "매칭", "money+" + ("name" if simv >= 0.2 else "amt"), s))
            else:
                out.append((None, None, "money_only", s))
            continue
        cands = set()
        for n in names:
            cands |= idx.get(nkey(n), set())
        if not cands and len(key) >= 6:
            cands = {s for kk, ss in idx.items() if len(kk) >= 6 and (kk in key or key in kk) for s in ss}
        ok = [c for c in cands if _near(sc, cmpk[c]) or _amt_ok(r.get("amt"), _at(sid[c]["s"].get("amt"), k))]
        if len(ok) == 1:
            out.append((ok[0], "매칭", "name+money", ok[0]))
        elif cands:
            out.append((None, None, "name_ambiguous" if len(cands) > 1 else "name_no_money",
                        sorted(cands)[0] if len(cands) == 1 else None))
        else:
            out.append((None, None, "no_candidate", None))
    # 같은 사업장에 두 계약이 붙으면(묶음 계약·이름 충돌) 둘 다 검토로 — 한쪽 값으로 덮지 않는다.
    cnt = {}
    for s, mt, _h, _g in out:
        if mt:
            cnt[s] = cnt.get(s, 0) + 1
    return [(None, None, "dup_site", s) if mt and cnt[s] > 1 else (s, mt, h, g) for s, mt, h, g in out]


def _set_at(arr, k, n, v):
    if not isinstance(arr, list):
        arr = [None] * n
    if len(arr) < n:
        arr = arr + [None] * (n - len(arr))
    arr[k] = v
    return arr


def apply_data(D, k, rows, matches):
    """매칭된 행만 DATA 에 쓴다: xip 5배열[k]·cur·nm(비었을 때)·mt, xipFull[k], has[2]=1. 반환: 쓴 건수."""
    n = len(D["fqF"])
    sid = {s["id"]: s for s in D["sites"]}
    wrote = 0
    for r, (s_id, mt, _how, _g) in zip(rows, matches):
        if not mt:
            continue
        s = sid[s_id]
        x = s.setdefault("xip", {})
        for f in XIP_ARR:
            x[f] = _set_at(x.get(f), k, n, r.get(f))
        if r.get("cur"):
            x["cur"] = r["cur"]
        else:
            x.setdefault("cur", None)
        if not x.get("nm"):
            x["nm"] = r["nm"]
        x["mt"] = mt
        xf = s.setdefault("xipFull", {})
        per = r.get("period") or ""
        ds = re.findall(r"((?:19|20)\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})", per)
        fmt = lambda t: "%s-%02d-%02d" % (t[0], int(t[1]), int(t[2]))
        vals = {"계약명": r["nm"], "계약상대방": r.get("cl"),
                "계약시작일": fmt(ds[0]) if ds else None, "계약종료일": fmt(ds[1]) if len(ds) > 1 else None,
                "계약금액": r.get("amt") if r.get("amt") is not None else r.get("amt_raw")}
        for key, v in vals.items():
            xf[key] = _set_at(xf.get(key), k, n, v)
        has = s.get("has") or [0, 0, 0]
        has[2] = 1
        s["has"] = has
        wrote += 1
    return wrote


def write_review(co, q, rows, matches, D, path=None):
    """검토 목록 CSV — 이 회사·분기 줄만 교체하고 나머지는 보존(정렬·시각 없음)."""
    p = path or REVIEW
    keep = []
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            keep = [r for r in csv.DictReader(f) if not (r["co"] == co and r["quarter"] == q)]
    sid = {s["id"]: s for s in D["sites"]}
    for r, (_s, mt, how, g) in zip(rows, matches):
        if mt:
            continue
        keep.append({"co": co, "quarter": q, "xi_name": r["nm"], "amt": "" if r.get("amt") is None else r["amt"],
                     "supCum": "" if r.get("supCum") is None else r["supCum"], "suggest_site": g or "",
                     "suggest_name": (sid[g].get("nm") if g in sid else "") or "", "reason": how})
    keep.sort(key=lambda r: (r["co"], r["quarter"], r["xi_name"]))
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_REVIEW_COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(keep)
    atomic_write(p, buf.getvalue())
    return sum(1 for r in keep if r["co"] == co and r["quarter"] == q)
