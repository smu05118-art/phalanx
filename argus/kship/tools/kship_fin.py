#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_fin — DART 정기보고서의 재무제표를 FnGuide 계정명으로 정리한다 (MODEL_SPEC §2-1).

읽는 절(뷰어 viewer.do 절 HTML, 캐시 `assets/fin_cache/<stock>/<quarter>_{cons|sep|shares|div}.html`):
  · `2. 연결재무제표` — 연결 재무상태표·손익계산서·포괄손익계산서·자본변동표·현금흐름표가 한 절에 다 있다
  · `4. 재무제표`     — 별도(연결이 없는 회사는 `2. 재무제표` 하나만)
  · `주식의 총수 등`   — 발행·자기·유통주식수(보통주/우선주/합계)
  · `배당에 관한 사항` — 주당 현금배당금·배당성향(사업보고서만)
  · 주석 **하위 노드**(§5-1, `<quarter>_note_{fin|borrowings|other}.html`) — `3. 연결재무제표 주석` 아래 `금융수익과 금융원가`·
    `차입금 및 사채`·`기타수익과 비용` 노드만(회사·분기당 목차 1 + 표 ≤4 요청; 주석 절 전체는 받지 않는다). 매핑된 계정
    (이자수익·이자비용·외환차익·외환차손·외화환산이익·외화환산손실·파생상품이익·파생상품손실·배당금수익 / 단기차입금·유동성장기부채·
    장기차입금·사채)은 **face 에 없을 때만** is/bs 에 올리고 `src_notes[q]` 에 출처를 적는다. face 가 '단기금융부채' 한 줄로 뭉친 회사
    (세진)는 주석 분해 합이 덩어리와 맞을 때만 갈라 넣는다. 원 표는 `notes.{fin,borrowings,other}[q]` 에 남긴다(raw 포함).
  · 주석 **부모 절 폴백**(`--notes-parent-fallback`, `<quarter>_note_parent_{cons|sep}.html`) — 하위 노드가 없는 보고서는
    `3. 연결재무제표 주석` 절 하나를 받아 번호 머리(`32. 금융수익 및 금융비용`)로 블록을 자르고 같은 규칙으로 고른 블록만 파싱한다.
    출처는 `note_parent:fin(3m)`·`note_parent:borrowings` 처럼 접두로 구분한다.

표 식별은 **표 제목**으로 한다 — DART XBRL 뷰어는 재무제표마다 `연결 재무상태표 / 제 53 기 반기말 … /
(단위 : 원)` 네 줄짜리 캡션 표를 먼저 두고 바로 뒤에 데이터 표를 둔다. 캡션에서 종류와 단위를 읽고 그
다음 숫자 표에 붙인다. 열은 머리행의 `제 N 기`·`3개월`·`누적`으로 당기/전기 × 3개월/누적을 가른다
(사업보고서는 연간 2~3열). 값은 전부 **백만원**으로 환산해 둔다(FnGuide 시트·골든과 같은 단위).

계정명은 MODEL_SPEC 0-2 의 FnGuide 이름을 그대로 쓴다. DART 라벨 → 계정 매핑은 `ACCOUNT_MAP`(정규식,
정규화 라벨 기준)이고, 매핑되지 않은 라벨은 버리지 않고 `raw_labels` 에 남긴다. 합성 계정(총차입금·순차입금·
이자발생자산·금융손익·이자손익·기타영업외손익…)은 구성 계정이 있을 때만 만든다 — 없는 숫자를 만들지 않는다.

분기화: Q1~Q3 손익은 3개월 열, Q4 는 사업보고서 연간 − 그 해 3Q 누적(3Q 누적이 없으면 다음 해 3Q 보고서의
전기 누적 열) — `derivation` 에 어느 길로 왔는지 적는다. 현금흐름은 누적→차분. 누적 정합(is_ytd 차분 == is)과
자산=부채+자본 항등식을 `checks` 에 남긴다. FnGuide 방식 누적차분은 `is_ytd_diff` 로 **항상 병기**하고, `is` 와 1백만원 초과로
다른 계정은 `restated[q]` 에 {is, ytd_diff, diff} 로 남긴다(§5-1 결정 ⓐ — 모델은 `is`, 레퍼런스 xlsx 패치는 `is_ytd_diff`).

부호·구조 정규화(2026-09-30 검증에서 추가): ① face 가 비용을 괄호(음수)로 찍는 표(성광벤드 FY2024~ 등 9사)는 비용 계정을
양수로 뒤집는다(`issues.expense_sign_negative`) — 안 하면 매출−원가≠GP 이고 Q4 = 연간(−) − 9M(+) 로 두 배 어긋난다.
② '…의 귀속' 블록의 계속·중단영업이익(지배주주분)은 총액으로 쓰지 않고, 총액 줄이 없으면 당기순이익 − 중단사업이익.
③ 중단영업이 연간에만 있으면 Q4 중단사업이익 = 연간값(9M 은 0). ④ 매출총이익~영업이익 사이의 매핑 안 된 영업비용 줄
(물류비·대손상각비)은 잔차가 그 줄들로 설명될 때만 판관비에 더한다(`issues.sga_absorbed_op_lines`, FnGuide 판관비 = GP − OP).

DART 는 **프로세스 하나**만 두드린다(kce_fetch._pace 파일락). 수집은 캐시가 있으면 건너뛰는 체크포인트다.

    python3 kship_fin.py --collect --build --stocks 075580,010140 [--quarters 2021Q4..2026Q2] [--force]
    python3 kship_fin.py --collect --build --all         # 모집단 전체(백그라운드 1개로)
    python3 kship_fin.py --build --stocks 010140         # 캐시만으로 assets/fin/<stock>.json
    python3 kship_fin.py --golden [--stocks ...]         # 레퍼런스 xlsx FnGuide 값과 대조
    python3 kship_fin.py --collect-notes --all           # 주석 하위 노드 캐시(백그라운드 1개, 체크포인트) → 완주 후 --build --all --golden
    python3 kship_fin.py --collect-notes --all --notes-parent-fallback   # 하위 노드 없는 분기는 부모 주석 절 1개(`<q>_note_parent_{cons|sep}.html`)
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys
import unicodedata
from html import unescape as html_unescape
try:
    import fcntl                                   # 수집 단일 프로세스 잠금(POSIX)
except ImportError:                              # pragma: no cover
    fcntl = None

from kship_lib import (ASSETS, KSHIP, atomic_write, fetch_section, load_asset, num_of,
                       parse_tables, pick_report, q_next, q_range, report_kind,
                       search_reports, toc)

HERE = os.path.dirname(os.path.abspath(__file__))
FIN_CACHE = os.path.join(ASSETS, "fin_cache")
FIN_DIR = os.path.join(ASSETS, "fin")
LOG_PATH = os.path.join(ASSETS, "fin_collect.log")
GOLDEN_PATH = os.path.join(HERE, "tests", "fixtures", "fin", "golden_fnguide.json")
SEARCH_START = "20220101"                        # 2021Q4 사업보고서(2022-03 접수)부터
DEFAULT_Q0, DEFAULT_Q1 = "2021Q4", "2026Q2"
GOLDEN_TOL = 3.0                                 # 백만원


def today():
    return datetime.date.today().strftime("%Y-%m-%d")


def helper_quarters(quarters):
    """Q4 도출에 필요한 같은 해 3Q 가 목록에 없으면 보조 분기로 붙인다(2021Q4 → 2021Q3).
    다음 해 3Q 보고서의 '전기 누적' 열은 재분류·정정으로 그 해 사업보고서와 어긋날 수 있다
    (동방선기 2021: 유형자산 취득 6,904 vs 연간 1,693 → Q4 음수). 같은 해 보고서로 맞추는 쪽이 FnGuide 와도 같다."""
    out = []
    for q in quarters:
        if q.endswith("Q4"):
            pq = "%sQ3" % q[:4]
            if pq not in quarters and pq not in out:
                out.append(pq)
    return out


def search_start_for(quarters):
    """검색 시작일 — 가장 이른 분기의 분기말 다음 달 1일(정기보고서는 분기말 +45일 뒤 접수)."""
    q0 = min(quarters)
    y, n = int(q0[:4]), int(q0[5])
    m = n * 3 + 1
    return "%d%02d01" % (y + (m > 12), (m - 1) % 12 + 1)


# ── 라벨 정규화 ──────────────────────────────────────────────────────────────
_WS = re.compile(r"[\s　\xa0]+")
_NOTE = re.compile(r"\((?:주|주석)\s*\d*(?:[,\s]*\d+)*\)|\(단위\s*:[^)]*\)|\[[^\]]*\]")
_ALT = re.compile(r"\((?:손실|이익|손익|수익|비용|결손금|환급|납부|부담액|감소|증가|자산)\)")
_XREF = re.compile(r"\([IVX\-\s·,]+\)")                       # (Ⅱ-Ⅲ) 류 참조 — NFKC 뒤엔 ASCII
_LEAD_NUM = re.compile(r"^(?:[IVX]+\.?|\d+\.|\(\d+\)|[가-힣]\.|\d+\))\s*")


def norm_label(s):
    """DART 계정 라벨 정규화 — 전각→반각(NFKC), 공백 전부 제거, (주N)·(단위)·(Ⅱ-Ⅲ) 제거,
    `Ⅰ.`·`1.`·`가.` 접두 제거, `(손실)`·`(수익)`·`(결손금)` 같은 괄호 대안 제거.
    '영업이익(손실)'→'영업이익', '이익잉여금(결손금)'→'이익잉여금', 'Ⅳ. 발행주식의 총수 (Ⅱ-Ⅲ)'→'발행주식의총수'."""
    t = unicodedata.normalize("NFKC", s or "")
    t = _NOTE.sub("", t)
    t = _WS.sub("", t)
    t = _XREF.sub("", t)
    t = _LEAD_NUM.sub("", t)
    t = _ALT.sub("", t)
    return t.strip("*·:-_ ")


# ── 단위 ────────────────────────────────────────────────────────────────────
_UNIT_RE = re.compile(r"단위\s*[:：]?\s*([^)\]]{1,16})")
_UNIT_MUL = [("십억원", 1000.0), ("백만원", 1.0), ("억원", 100.0), ("천원", 0.001), ("만원", 0.01), ("원", 1e-6)]


def unit_mul_of(text):
    """'(단위 : 원|천원|백만원)' → 백만원 환산 배수. 못 읽으면 None(호출측이 원 가정 + issue)."""
    m = _UNIT_RE.findall(text or "")
    if not m:
        return None
    t = m[-1].replace(" ", "")
    for name, mul in _UNIT_MUL:
        if name in t:
            return mul
    return None


def to_million(raw, mul, nd=2):
    """셀 문자열 → 백만원 float. 괄호 음수 '(3,034,382)' 는 num_of 가 처리한다."""
    v = num_of(raw)
    if v is None:
        return None
    return round(v * mul, nd)


# ── 계정 매핑 ────────────────────────────────────────────────────────────────
# (재무제표, BS 구역, 정규식(정규화 라벨 전체일치), 대상 계정들, 옵션)
#   재무제표: bs / is / cf.  BS 구역: ca 유동자산 · nca 비유동자산 · cl 유동부채 · ncl 비유동부채 · eq 자본 · None 무관
#   옵션 abs=True 는 현금흐름 증가·감소 계정처럼 부호를 떼고 크기만 두는 것(FnGuide 관행).
# 한 DART 라벨이 여러 FnGuide 계정에 동시에 들어가는 경우(단기금융상품 → 단기금융상품·단기금융자산)는 대상을
# 여러 개 둔다. 대상 계정에 이미 값이 있으면 **더한다**(매입채무+미지급금+미지급비용 → 매입채무및기타채무).
ACCOUNT_MAP = [
    # ── 재무상태표: 합계 ─────────────────────────────────────
    ("bs", None, r"^유동자산(합계)?$", ["유동자산"], {}),
    ("bs", None, r"^비유동자산(합계)?$", ["비유동자산"], {}),
    ("bs", None, r"^자산(총계|합계)$", ["자산총계"], {}),
    ("bs", None, r"^유동부채(합계)?$", ["유동부채"], {}),
    ("bs", None, r"^비유동부채(합계)?$", ["비유동부채"], {}),
    ("bs", None, r"^부채(총계|합계)$", ["부채총계"], {}),
    ("bs", None, r"^(자본총계|자본합계|기말자본|자본)$", ["자본총계"], {}),
    ("bs", None, r"^(부채와자본총계|자본과부채총계|부채및자본총계|부채와자본의총계|자본및부채총계|부채총계및자본총계)$", ["부채와자본총계"], {}),
    # ── 유동자산 ────────────────────────────────────────────
    # FnGuide 관행(레퍼런스 골든으로 실측): 단기금융자산 = 단기금융상품 + 파생자산 + 확정계약자산(+대여금);
    # 당기손익/기타포괄-공정가치 금융자산·기타유동금융자산은 **넣지 않는다**(세진·삼성重 골든에서 확인).
    ("bs", "ca", r"^현금및현금성자산$", ["현금및현금성자산"], {}),
    ("bs", "ca", r"^(단기금융상품|유동금융상품|단기금융자산|단기예금|정기예금)$", ["단기금융상품", "단기금융자산"], {}),
    ("bs", "ca", r"^(유동|단기)?(당기손익|기타포괄손익)-?공정가치(측정)?금융자산$", ["단기투자자산(공정가치)"], {}),
    ("bs", "ca", r"^(유동|단기)?당기손익인식금융자산$", ["단기투자자산(공정가치)"], {}),
    ("bs", "ca", r"^(유동|단기)?(매도가능금융자산|단기투자자산|단기투자증권)$", ["단기투자자산(공정가치)"], {}),
    ("bs", "ca", r"^(유동|단기)?(상각후원가(측정)?금융자산|만기보유금융자산)$", ["단기금융자산"], {}),
    ("bs", "ca", r"^(유동)?파생(금융)?(상품)?자산$", ["유동파생상품자산", "단기금융자산"], {}),
    ("bs", "ca", r"^(유동)?확정계약자산$", ["유동확정계약자산", "단기금융자산"], {}),
    ("bs", "ca", r"^기타(유동)?금융자산$", ["기타유동금융자산"], {}),
    ("bs", "ca", r"^(단기)?대여금$", ["단기대여금", "단기금융자산"], {}),
    ("bs", "ca", r"^(매출채권|매출채권및기타(유동)?채권|매출채권및기타수취채권|매출채권및기타유동수취채권|매출채권및미수금|외상매출금|받을어음|매출채권및기타유동금융자산)$", ["매출채권및기타채권"], {}),
    ("bs", "ca", r"^(미수금|미수수익|(유동)?기타채권|기타(유동)?수취채권|기타유동채권|미수금및기타채권|유동성장기미수금|기타(유동)?금융채권)$", ["매출채권및기타채권"], {}),
    ("bs", "ca", r"^(계약자산|유동계약자산|미청구공사)$", ["계약자산"], {}),
    ("bs", "ca", r"^(유동)?재고자산$", ["재고자산"], {}),
    ("bs", "ca", r"^((당기|유동)?법인세자산|선급법인세|당기법인세자산|미수법인세환급액)$", ["당기법인세자산(선급법인세)"], {}),
    ("bs", "ca", r"^(선급금|유동선급금)$", ["선급금", "선급금등", "기타유동자산"], {}),
    ("bs", "ca", r"^(선급비용|선급공사원가|유동선급비용)$", ["기타유동자산"], {}),
    ("bs", "ca", r"^(기타유동자산|기타유동비금융자산|유동기타자산)$", ["기타유동자산"], {}),
    ("bs", "ca", r"^(매각예정(비유동)?자산(집단)?|매각예정(으로)?분류된(비유동)?자산(또는처분자산집단)?|매각예정처분자산집단)$", ["매각예정비유동자산및처분자산"], {}),
    # ── 비유동자산 ──────────────────────────────────────────
    ("bs", "nca", r"^유형자산$", ["유형자산"], {}),
    ("bs", "nca", r"^토지$", ["토지"], {}),
    ("bs", "nca", r"^(건물|구축물|기계장치|설비자산|차량운반구|공구와기구|비품|선박)$", ["설비자산"], {}),
    ("bs", "nca", r"^건설중인자산$", ["건설중인자산"], {}),
    ("bs", "nca", r"^사용권자산$", ["사용권자산", "기타비유동자산"], {}),       # FnGuide 는 사용권자산을 기타비유동자산에 둔다(삼성重·미포 골든)
    ("bs", "nca", r"^(무형자산|영업권이외의무형자산|영업권|기타무형자산|영업권및기타무형자산)$", ["무형자산"], {}),
    ("bs", "nca", r"^투자부동산$", ["투자부동산"], {}),
    ("bs", "nca", r"^(장기금융자산|장기금융상품|장기투자자산|장기투자증권|비유동금융자산|장기예금)$", ["장기금융자산", "투자자산"], {}),
    ("bs", "nca", r"^(비유동|장기)?(당기손익|기타포괄손익)-?공정가치(측정)?금융자산$", ["장기금융자산", "투자자산"], {}),
    ("bs", "nca", r"^(비유동|장기)?당기손익인식금융자산$", ["장기금융자산", "투자자산"], {}),
    ("bs", "nca", r"^(비유동|장기)?(상각후원가(측정)?금융자산|매도가능금융자산|만기보유금융자산)$", ["장기금융자산", "투자자산"], {}),
    ("bs", "nca", r"^기타(비유동|장기)금융자산$", ["장기금융자산", "투자자산"], {}),
    ("bs", "nca", r"^(비유동|장기)?파생(금융)?(상품)?자산$", ["비유동파생상품자산", "투자자산"], {}),
    ("bs", "nca", r"^(비유동)?확정계약자산$", ["비유동확정계약자산", "투자자산"], {}),
    ("bs", "nca", r"^(종속기업|관계기업|공동기업|조인트벤처)[가-힣,]*(투자|주식|투자자산|투자주식|에대한투자|에대한투자자산)*$", ["종속기업및관계기업투자", "투자자산"], {}),
    ("bs", "nca", r"^(지분법적용투자주식|관계기업등투자|관계기업투자주식|종속기업투자주식|지분법적용투자|관계기업및공동기업투자)$", ["종속기업및관계기업투자", "투자자산"], {}),
    ("bs", "nca", r"^(장기대여금|장기대여금및수취채권)$", ["장기대여금", "투자자산"], {}),
    ("bs", "nca", r"^이연법인세자산$", ["이연법인세자산"], {}),
    ("bs", "nca", r"^(장기매출채권(및기타(비유동)?채권)?|매출채권및기타비유동채권|비유동기타채권|장기미수금|기타비유동채권|장기(성)?매출채권|비유동매출채권|장기미수수익|비유동매출채권및기타채권|장기기타채권|장기매출채권및기타비유동수취채권)$", ["장기매출채권및기타채권"], {}),
    ("bs", "nca", r"^(기타비유동자산|기타비유동비금융자산|비유동기타자산|장기선급비용|장기선급금|(순)?확정급여자산|보증금|임차보증금|장기보증금|기타보증금)$", ["기타비유동자산"], {}),
    ("bs", "nca", r"^(장기|비유동)당기법인세자산$", ["장기당기법인세자산"], {}),
    # ── 유동부채 ────────────────────────────────────────────
    # face 라벨 '단기금융부채'는 차입금이다(세진·미포) — FnGuide 는 이를 단기차입금(+유동성장기부채, 주석으로 분해)에 둔다.
    # FnGuide 의 '단기금융부채' 는 파생상품부채+확정계약부채+리스부채+기타금융부채(차입 제외) — 삼성重 2023.09 골든과 1원 단위로 맞는다.
    ("bs", "cl", r"^단기차입금$", ["단기차입금"], {}),
    ("bs", "cl", r"^(단기사채|유동성사채|단기전자단기사채|전자단기사채)$", ["단기사채"], {}),
    ("bs", "cl", r"^(유동성장기부채|유동성장기차입금|유동장기부채|유동성장기차입부채|유동성장기금융부채|유동성사채및장기차입금|유동성장기차입금및사채|유동사채및차입금|유동성전환사채|유동성신주인수권부사채|유동성장기차입금및사채)$", ["유동성장기부채"], {}),
    ("bs", "cl", r"^(단기금융부채|유동금융부채|유동차입금|유동성차입금|차입금|단기차입부채)$", ["단기차입금", "단기금융부채(face)"], {}),
    ("bs", "cl", r"^(유동|단기)?파생(금융)?(상품)?부채$", ["단기파생상품부채", "단기금융부채"], {}),
    ("bs", "cl", r"^(유동)?확정계약부채$", ["단기파생상품부채", "단기금융부채"], {}),
    ("bs", "cl", r"^기타(유동)?금융부채$", ["기타유동금융부채", "단기금융부채"], {}),
    ("bs", "cl", r"^(유동)?당기손익인식금융부채$", ["기타유동금융부채", "단기금융부채"], {}),
    ("bs", "cl", r"^(유동|단기)?리스부채$", ["유동리스부채", "리스부채", "단기금융부채"], {}),
    ("bs", "cl", r"^(매입채무|매입채무및기타(유동)?채무|매입채무및기타지급채무|매입채무및기타유동채무|외상매입금|지급어음)$", ["매입채무및기타채무"], {}),
    ("bs", "cl", r"^(미지급금|미지급비용|(유동)?기타채무|기타(유동)?지급채무|기타유동채무|미지급금및기타채무|미지급배당금|예수금|유동성장기미지급금)$", ["매입채무및기타채무"], {}),
    ("bs", "cl", r"^(계약부채|유동계약부채|초과청구공사)$", ["계약부채"], {}),
    ("bs", "cl", r"^(선수금|유동선수금)$", ["선수금", "기타유동부채"], {}),
    ("bs", "cl", r"^(선수수익|유동선수수익|정부보조금|기타유동부채|기타유동비금융부채|유동기타부채|유동이연수익)$", ["기타유동부채"], {}),
    ("bs", "cl", r"^(유동종업원급여충당부채|유동종업원급여부채|단기종업원급여부채)$", ["유동종업원급여충당부채", "단기충당부채"], {}),
    ("bs", "cl", r"^(?!.*종업원급여).*충당부채$", ["단기충당부채"], {}),                  # 공사손실·하자보수·기타유동·품질보증… 전부
    ("bs", "cl", r"^((당기|유동)?법인세부채|미지급법인세|당기법인세부채)$", ["당기법인세부채(미지급법인세)"], {}),
    ("bs", "cl", r"^(매각예정(비유동)?자산(집단)?에?(직접)?관련된부채|매각예정처분자산집단(에포함된)?부채|매각예정(으로)?분류된처분자산집단에포함된부채)$", ["매각예정부채"], {}),
    # ── 비유동부채 ──────────────────────────────────────────
    ("bs", "ncl", r"^(사채|장기사채|전환사채|신주인수권부사채|교환사채|비유동사채)$", ["사채"], {}),
    ("bs", "ncl", r"^(장기차입금|비유동차입금|장기차입부채)$", ["장기차입금"], {}),
    ("bs", "ncl", r"^(장기금융부채|비유동금융부채)$", ["장기차입금", "장기금융부채(face)"], {}),
    ("bs", "ncl", r"^(비유동|장기)?파생(금융)?(상품)?부채$", ["장기파생상품부채", "장기금융부채"], {}),
    ("bs", "ncl", r"^(비유동)?확정계약부채$", ["장기파생상품부채", "장기금융부채"], {}),
    ("bs", "ncl", r"^기타(비유동|장기)금융부채$", ["기타비유동금융부채", "장기금융부채"], {}),
    ("bs", "ncl", r"^(비유동)?당기손익인식금융부채$", ["기타비유동금융부채", "장기금융부채"], {}),
    ("bs", "ncl", r"^(비유동|장기)리스부채$", ["비유동리스부채", "리스부채", "장기금융부채"], {}),
    ("bs", "ncl", r"^(장기매입채무및기타(비유동)?채무|장기매입채무|장기미지급금|장기미지급비용|기타비유동채무|비유동기타채무|장기기타채무|비유동매입채무및기타채무|장기매입채무및기타채무)$", ["장기매입채무및기타채무"], {}),
    ("bs", "ncl", r"^((순)?확정급여(채무|부채)|퇴직급여(채무|부채)|(비유동)?종업원급여(충당)?부채|장기종업원급여(충당)?부채|기타장기종업원급여부채|순확정급여부채)$", ["확정급여부채"], {}),
    ("bs", "ncl", r"^(?!.*종업원급여).*충당부채$", ["장기충당부채"], {}),                 # 기타비유동충당부채(삼성重 2022) 포함
    ("bs", "ncl", r"^이연법인세부채$", ["이연법인세부채"], {}),
    ("bs", "ncl", r"^(장기선수금|비유동선수금)$", ["장기선수금"], {}),
    ("bs", "ncl", r"^(장기선수수익|비유동선수수익|비유동이연수익)$", ["장기선수수익", "기타비유동부채"], {}),
    ("bs", "ncl", r"^(기타비유동부채|비유동기타부채|기타비유동비금융부채|장기기타부채|정부보조금|비유동정부보조금|장기예수보증금|임대보증금|장기임대보증금)$", ["기타비유동부채"], {}),
    ("bs", "ncl", r"^(장기|비유동)당기법인세부채$", ["장기당기법인세부채(미지급법인세)"], {}),
    ("bs", "ncl", r"^(비유동)?계약부채$", ["비유동계약부채"], {}),
    # ── 자본 ────────────────────────────────────────────────
    ("bs", "eq", r"^(지배기업(의)?소유주(지분|귀속지분|에게귀속되는자본|에게귀속되는지분|귀속자본|지분합계)|지배기업소유주지분|지배기업소유지분|지배기업의소유지분|지배기업지분|지배주주지분|지배기업소유주에게귀속되는자본)$", ["지배주주지분"], {}),
    ("bs", "eq", r"^(자본금|납입자본)$", ["자본금"], {}),
    ("bs", "eq", r"^(보통주자본금)$", ["보통주자본금"], {}),
    ("bs", "eq", r"^(우선주자본금)$", ["우선주자본금"], {}),
    ("bs", "eq", r"^(자본잉여금|주식발행초과금|기타불입자본|기타납입자본|자본준비금|주식발행초과금및기타자본잉여금)$", ["자본잉여금"], {}),
    ("bs", "eq", r"^(기타자본(항목|구성요소|잉여금|조정)?|자기주식|자본조정|기타자본요소|기타포괄손익누계액외기타자본|신종자본증권|자기주식처분손실|주식선택권|기타자본구성요소)$", ["기타자본"], {}),
    ("bs", "eq", r"^(기타포괄손익누계액|기타포괄손익누적액|기타포괄이익누계액|기타포괄손익)$", ["기타포괄이익누계액"], {}),
    ("bs", "eq", r"^(이익잉여금|결손금|미처분이익잉여금|이익잉여금또는결손금|이익잉여금\(결손금\))$", ["이익잉여금"], {}),
    ("bs", "eq", r"^(비지배지분|비지배주주지분|비지배주주에게귀속되는자본|비지배지분에귀속되는자본)$", ["비지배주주지분"], {}),
    # ── 손익계산서 ──────────────────────────────────────────
    ("is", None, r"^(매출액|수익|매출|영업수익|매출액\(수익\)|수익\(매출액\)|매출및지분법적용투자주식수익|매출수익|총매출액|순매출액|매출액및기타영업수익)$", ["매출액(수익)"], {}),
    ("is", None, r"^(매출원가|영업비용|매출원가등)$", ["매출원가"], {}),
    ("is", None, r"^매출총이익$", ["매출총이익"], {}),
    ("is", None, r"^(판매비와관리비|판매비및관리비|판매및일반관리비|판매비와일반관리비|판관비|판매관리비|판매비및일반관리비)$", ["판관비"], {}),
    ("is", None, r"^(영업이익|영업손익)$", ["영업이익"], {}),
    ("is", None, r"^(기타영업수익)$", ["기타영업수익"], {}),
    ("is", None, r"^(기타영업비용)$", ["기타영업비용"], {}),
    ("is", None, r"^(기타영업손익)$", ["기타영업손익"], {}),
    ("is", None, r"^(기타수익|기타이익|기타영업외수익|영업외수익|기타영업외이익)$", ["기타영업외수익"], {}),
    ("is", None, r"^(기타비용|기타손실|기타영업외비용|영업외비용|기타영업외손실)$", ["기타영업외비용"], {}),
    ("is", None, r"^(기타손익|기타영업외손익|영업외손익|기타이익\(손실\)|기타순손익)$", ["기타영업외손익"], {}),
    ("is", None, r"^(금융수익|금융이익|이자수익등금융수익)$", ["금융수익"], {}),
    ("is", None, r"^(금융원가|금융비용|금융손실)$", ["금융비용"], {}),
    ("is", None, r"^(금융손익|순금융손익|순금융수익|순금융비용|순금융원가|금융수익\(비용\))$", ["금융손익"], {}),
    ("is", None, r"^이자수익$", ["이자수익"], {}),
    ("is", None, r"^이자비용$", ["이자비용"], {}),
    ("is", None, r"^배당금수익$", ["배당금수익"], {}),
    ("is", None, r"^외환차익$", ["외환차익"], {}),
    ("is", None, r"^외환차손$", ["외환차손"], {}),
    ("is", None, r"^외화환산이익$", ["외화환산이익"], {}),
    ("is", None, r"^외화환산손실$", ["외화환산손실"], {}),
    ("is", None, r"^(파생상품(평가|거래)?이익|파생상품평가및거래이익)$", ["파생상품이익"], {}),
    ("is", None, r"^(파생상품(평가|거래)?손실|파생상품평가및거래손실)$", ["파생상품손실"], {}),
    ("is", None, r"^(지분법(이익|손실|손익|평가손익|평가이익|평가손실|투자손익|이익\(손실\))|지분법적용투자(주식)?손익|지분법적용투자주식관련손익|공동기업(과|및)관계기업(의)?지분법손익|지분법적용관계기업투자손익|관계기업및공동기업지분법손익)$",
     ["종속기업,공동지배기업및관계기업관련손익", "지분법관련손익"], {}),
    ("is", None, r"^(관계기업(및공동기업)?(투자)?(주식)?(관련)?손익|관계기업투자(이익|손실)|공동기업및관계기업투자손익|관계기업및공동기업투자손익|관계기업투자주식관련손익|종속기업[,·]?공동(지배)?기업및관계기업관련손익|종속기업및관계기업(투자)?(관련)?손익|관계기업손익)$",
     ["종속기업,공동지배기업및관계기업관련손익"], {}),
    ("is", None, r"^(법인세비용차감전(순)?(이익|손실|손익|계속사업이익|계속영업이익)?|법인세차감전(순)?(이익|손실|손익)|법인세비용차감전계속영업(이익|손익)|법인세비용차감전계속사업(이익|손익)|계속영업법인세비용차감전순이익|법인세비용차감전이익|법인세비용차감전순손익)$",
     ["법인세비용차감전계속사업이익"], {}),
    ("is", None, r"^(법인세비용|법인세|계속영업법인세비용|법인세비용\(수익\)|법인세수익)$", ["법인세비용"], {}),
    # '계속영업반기순이익(손실)'·'중단영업분기순이익'(KCC 2026Q2) 처럼 (당|반|분)기 가 끼는 라벨도 같은 계정이다
    ("is", None, r"^(계속(영업|사업)((당|반|분)기)?(순)?(이익|손익))$", ["계속사업이익"], {"cont_disc": True}),
    ("is", None, r"^(중단(영업|사업)((당|반|분)기)?(순)?(이익|손익))$", ["중단사업이익"], {"cont_disc": True}),
    ("is", None, r"^((당|반|분)기순(이익|손익)|연결(당|반|분)기순(이익|손익)|(당|반|분)기순이익\(손실\)|당기순이익\(손실\)|순이익)$", ["당기순이익"], {}),
    ("is", None, r"^(지배기업(의)?소유주(지분|귀속|귀속분|지분순이익|에게귀속되는(당|반|분)기순(이익|손익)|에귀속되는(당|반|분)기순(이익|손익))?|지배기업소유주지분|지배기업지분|지배주주지분(순이익)?|지배기업의소유주에게귀속되는(당|반|분)기순(이익|손익)|지배기업소유주(당|반|분)기순(이익|손익)|지배기업의소유주지분|지배기업소유주에게귀속되는(당|반|분)기순(이익|손익)|지배기업소유지분)$",
     ["(지배주주지분)당기순이익"], {"attrib": True}),
    ("is", None, r"^(비지배(지분|주주지분)(순이익)?(에게?귀속되는(당|반|분)기순(이익|손익))?|비지배지분(당|반|분)기순(이익|손익)|비지배지분순이익)$", ["(비지배주주지분)당기순이익"], {"attrib": True}),
    ("is", None, r"^((총)?포괄(손익|이익)|(당|반|분)기(총)?포괄(이익|손익)|총포괄손익|포괄손익합계|총포괄이익\(손실\))$", ["총포괄손익"], {}),
    ("is", None, r"^((기본)?주당(순)?(이익|손실|손익)|보통주(기본)?주당(반|분|당)?기순(이익|손실)|기본및희석주당(순)?이익|(기본)?주당(당|반|분)기순(이익|손실)|보통주기본주당이익|기본주당순손익|보통주기본주당순이익\(손실\))$", ["기본주당순이익(원)"], {"eps": True}),
    # ── 현금흐름표 ──────────────────────────────────────────
    ("cf", None, r"^(영업활동(으로인한|으로부터의|으로부터)?(순)?현금흐름|영업활동순현금흐름|영업활동으로인한현금흐름|영업활동현금흐름)$", ["영업활동으로인한현금흐름"], {}),
    ("cf", None, r"^(투자활동(으로인한|으로부터의|으로부터)?(순)?현금흐름|투자활동순현금흐름)$", ["투자활동으로인한현금흐름"], {}),
    ("cf", None, r"^(재무활동(으로인한|으로부터의|으로부터)?(순)?현금흐름|재무활동순현금흐름)$", ["재무활동으로인한현금흐름"], {}),
    ("cf", None, r"^(유형자산의(취득|증가|매입)|유형자산의취득으로인한현금유출|유형자산취득|유형자산의구입)$", ["유형자산의증가", "CAPEX"], {"abs": True}),
    ("cf", None, r"^(유형자산의(처분|감소|매각)|유형자산의처분으로인한현금유입|유형자산처분)$", ["유형자산의감소"], {"abs": True}),
    ("cf", None, r"^((영업권이외의)?무형자산의(취득|증가|매입)|무형자산의취득으로인한현금유출|무형자산취득)$", ["무형자산의증가", "CAPEX"], {"abs": True}),
    ("cf", None, r"^(무형자산의(처분|감소|매각))$", ["무형자산의감소"], {"abs": True}),
    ("cf", None, r"^(감가상각비|유형자산감가상각비|감가상각비및무형자산상각비|감가상각)$", ["감가상각비"], {}),
    ("cf", None, r"^(사용권자산감가상각비|사용권자산상각비)$", ["감가상각비"], {}),
    ("cf", None, r"^(무형자산상각비|기타무형자산상각비|개발비상각)$", ["무형자산상각비"], {}),
    ("cf", None, r"^(단기차입금의(증가|차입|순증가)|단기차입금의차입)$", ["단기차입금의증가"], {"abs": True}),
    ("cf", None, r"^(단기차입금의(감소|상환|순감소))$", ["단기차입금의감소"], {"abs": True}),
    ("cf", None, r"^(장기차입금의(증가|차입))$", ["장기차입금의증가"], {"abs": True}),
    ("cf", None, r"^(장기차입금의(감소|상환))$", ["장기차입금의감소"], {"abs": True}),
    ("cf", None, r"^(차입금의(차입|증가|순증가)|차입금의증가)$", ["차입금의증가"], {"abs": True}),
    ("cf", None, r"^(차입금의(상환|감소|순감소))$", ["차입금의감소"], {"abs": True}),
    ("cf", None, r"^(사채의(발행|증가))$", ["사채의증가"], {"abs": True}),
    ("cf", None, r"^(사채의(상환|감소))$", ["사채의감소"], {"abs": True}),
    ("cf", None, r"^(유동성장기부채의(상환|감소)|유동장기부채의상환|유동성장기차입금의(상환|감소)|유동성사채의상환)$", ["유동성장기부채의감소"], {"abs": True}),
    ("cf", None, r"^(리스부채의(상환|지급|감소)|(유동)?리스부채의상환|리스료의지급|금융리스부채의상환)$", ["리스부채의상환"], {"abs": True}),
    ("cf", None, r"^(배당금(의)?지급|현금배당금의지급|배당금지급)$", ["배당금지급"], {"abs": True}),
    ("cf", None, r"^(자기주식의취득|자기주식취득)$", ["자기주식의취득"], {"abs": True}),
    ("cf", None, r"^(이자(의)?수취|이자수취|이자의수입|이자수입)$", ["이자수취(CF)"], {}),
    # 이자·법인세 현금흐름은 부호를 그대로 둔다(음수=지급). 환급이 있으면 누적 부호가 바뀌어 절대값 차분이 깨진다(실측).
    ("cf", None, r"^(이자(의)?지급|이자지급|이자비용의지급)$", ["이자지급(CF)"], {}),
    ("cf", None, r"^(배당금(의)?(수취|수입)|배당금수취|배당금수취\(영업\)|배당금수입)$", ["배당금수취(CF)"], {}),
    ("cf", None, r"^(법인세(의)?(납부|환급|부담액|납부액|지급)(\(환급\)|\(납부\))?|법인세환급액\(부담액\)|법인세환급|법인세납부|법인세의납부|법인세환급액|법인세부담액)$", ["법인세납부(CF)"], {}),
    ("cf", None, r"^((기말|반기말|분기말|당기말)(의)?현금및현금성자산|기말현금및현금성자산|현금및현금성자산의기말잔액)$", ["기말현금및현금성자산"], {}),
    ("cf", None, r"^(현금및현금성자산의(순)?증감|현금및현금성자산의(순)?증가|현금및현금성자산의순증가\(감소\)|현금및현금성자산의증가|현금의증감|현금및현금성자산의순증감|환율변동효과(반영)?(전|후)(의)?현금및현금성자산의순증가)$", ["현금및현금성자산의증감"], {}),
]
_COMPILED = [(st, sec, re.compile(rx), tg, opt) for st, sec, rx, tg, opt in ACCOUNT_MAP]

# BS 구역 전환 라벨(정규화 후). 라벨 자체가 구역 머리이면서 합계인 경우가 많다(유동자산 = 머리 + 합계).
_SECTION_OF = [
    ("ca", re.compile(r"^유동자산(합계)?$|^자산$")),
    ("nca", re.compile(r"^비유동자산(합계)?$")),
    ("cl", re.compile(r"^유동부채(합계)?$|^부채$")),
    ("ncl", re.compile(r"^비유동부채(합계)?$")),
    ("eq", re.compile(r"^자본$|^자본총계$|^자본금$|^납입자본$|^지배기업")),
]

# 손익계산서에서 '비용' 인 계정 — DART XBRL 뷰어가 비용을 괄호(음수)로 찍는 회사(성광벤드 FY2024~, 금강공업 2024Q1~,
# STX엔진 2024Q2~, 한국카본 FY2024~, 동성화인텍·인화정공 FY2025~, 현대리바트 사업보고서, 원일티엔아이 전 분기 — 9사 실측)는
# 매출원가·판관비·기타비용·금융비용·법인세비용이 전부 음수로 들어와 매출−원가≠GP 가 되고, Q4 = 연간(−) − 9M(+) 로 두 배 어긋난다.
# 매출액 > 0 이면서 매출원가 < 0 이면 그 표(열)는 음수 표기 관행으로 보고 이 계정들의 부호를 뒤집는다(비용은 양수가 우리 규약).
EXPENSE_KEYS = ("매출원가", "판관비", "기타영업비용", "기타영업외비용", "금융비용", "이자비용",
                "외환차손", "외화환산손실", "파생상품손실", "법인세비용")

# 현금흐름표에서 크기만 두는(절대값) 계정 — 누적 차분이 음수면 재분류·정정이 섞인 것이라 값을 버린다
CF_ABS_KEYS = {"유형자산의증가", "유형자산의감소", "무형자산의증가", "무형자산의감소", "CAPEX", "단기차입금의증가",
               "단기차입금의감소", "장기차입금의증가", "장기차입금의감소", "사채의증가", "사채의감소", "유동성장기부채의감소",
               "리스부채의상환", "배당금지급", "자기주식의취득", "차입금의증가", "차입금의감소"}

# 합성 계정 정의(화면·문서에 그대로 보인다)
SYNTH_BASIS = {
    "총차입금": "단기차입금+단기사채+유동성장기부채+장기차입금+사채 (face 라벨 '단기/장기금융부채' 는 차입금으로 보아 단기/장기차입금에 넣음 — issues 표기; 리스부채는 별도 키)",
    "순차입금": "총차입금 − 현금및현금성자산 − 단기금융자산",
    "이자발생자산": "현금및현금성자산 + 단기금융자산 + 장기금융자산",
    "금융손익": "금융수익 − 금융비용 (face 에 있으면 그 값)",
    "이자손익": "이자수익 − 이자비용 (둘 다 face 에 있을 때만)",
    "기타영업외손익": "기타영업외수익 − 기타영업외비용 (face 에 있으면 그 값)",
    "기타영업손익": "기타영업수익 − 기타영업비용",
    "매출총이익": "매출액(수익) − 매출원가 (face 에 없을 때)",
    "판관비": "face 판관비 + 매출총이익~영업이익 사이의 매핑 안 된 영업비용 줄(물류비·대손상각비 — 잔차가 그 줄 합과 맞을 때만; issues.sga_absorbed_op_lines)",
    "계속사업이익": "face 총액 줄; 없으면 당기순이익 − 중단사업이익(귀속 블록의 지배주주분 계속영업이익은 쓰지 않음)",
    "매출원가·판관비·기타영업외비용·금융비용·법인세비용 부호": "face 가 비용을 괄호(음수)로 찍는 표는 양수로 정규화(issues.expense_sign_negative) — 비용은 항상 양수",
    "지배주주지분": "비지배지분 라인이 없으면 자본총계",
    "(지배주주지분)당기순이익": "비지배 라인이 없으면 당기순이익",
    "CAPEX": "유형자산의증가 + 무형자산의증가 (현금흐름표 취득액, 절대값)",
    "유동자산": "자산총계 − 비유동자산 (face 에 없을 때)",
    "비유동자산": "자산총계 − 유동자산 (face 에 없을 때)",
    "유동부채": "부채총계 − 비유동부채 (face 에 없을 때)",
    "비유동부채": "부채총계 − 유동부채 (face 에 없을 때)",
    "is_ytd_diff": "FnGuide 방식 누적차분 — Q1 = 누적, Qn = 누적 − 직전 누적, Q4 = 연간 − 3Q 누적. `is`(보고서 3개월 열)와 1백만원 초과로 다른 계정은 restated[q] (모델은 is, 레퍼런스 xlsx 패치는 is_ytd_diff)",
}


def _add(acc, key, v):
    if v is None:
        return
    acc[key] = round((acc.get(key) or 0.0) + v, 2)


def _sub(a, b):
    if a is None or b is None:
        return None
    return round(a - b, 2)


def _sum(*xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs), 2) if xs else None


# ── 표 → 재무제표 ─────────────────────────────────────────────────────────
_STMT_KIND = [("cf", re.compile(r"현금흐름표")), ("sce", re.compile(r"자본변동표")),
              ("cis", re.compile(r"포괄손익계산서")), ("is", re.compile(r"손익계산서")),
              ("bs", re.compile(r"재무상태표|대차대조표"))]
_TERM = re.compile(r"제\s*(\d+)\s*기")
_HDR_HINT = re.compile(r"제\s*\d+\s*기|3개월|누적|당\s*기|전\s*기|기\s*말|당\s*분\s*기|당\s*반\s*기")   # 세진 2023Q4 주석 머리 `당 기`


def _kind_of(text):
    for k, rx in _STMT_KIND:
        if rx.search(text or ""):
            return k
    return None


def _is_caption(t):
    """숫자 값이 하나도 없는 표 — 캡션(제목·기간·단위)류. 종류는 셀 또는 lead 에서, 단위는 셀 또는 lead 에서 읽는다.
    세진 2023Q3 처럼 제목이 <P> 에 있고 표에는 기간·단위만 있는 문서도 있다."""
    cells = [c for r in t["rows"] for c in r]
    if not cells:
        return False
    return not any(num_of(c) is not None and len(c) > 4 for c in cells)


def _split_hdr(t):
    """cols 가 비어 있으면(THEAD 없는 옛 문서) 머리행을 rows 앞에서 떼어 평탄화한다."""
    cols, rows = t["cols"], t["rows"]
    if cols:
        return cols, rows
    nh = 0
    while nh < min(3, len(rows)):
        r = rows[nh]
        if all(num_of(c) is None or len(c) <= 4 for c in r[1:]) and any(_HDR_HINT.search(c) for c in r):
            nh += 1
        else:
            break
    if nh == 0:
        return [], rows
    width = max(len(r) for r in rows[:nh])
    out = []
    for j in range(width):
        parts = []
        for i in range(nh):
            c = rows[i][j] if j < len(rows[i]) else ""
            if c and (not parts or parts[-1] != c):
                parts.append(c)
        out.append(" ".join(parts))
    return out, rows[nh:]


def tag_cols(cols, kind):
    """머리 열 → 태그. BS: cur/prev/prev2. IS·CF: cur_q/cur_ytd/cur_full/prev_q/…
    기수(`제 N 기`)가 큰 쪽이 당기. 기수를 못 읽으면 왼쪽부터 당기·전기 순으로 본다."""
    terms = []
    for c in cols[1:]:
        m = _TERM.search(c)
        terms.append(int(m.group(1)) if m else None)
    order = sorted({t for t in terms if t is not None}, reverse=True)
    names = ["cur", "prev", "prev2", "prev3"]
    tags = []
    seen_seq = {}
    for i, c in enumerate(cols[1:]):
        t = terms[i]
        if t is not None and t in order:
            base = names[min(order.index(t), 3)]
        else:
            # 기수 없음 — 등장 순서로 (같은 텍스트 반복은 같은 기)
            key = re.sub(r"3개월|누적|당기|전기", "", c).strip()
            if key not in seen_seq:
                seen_seq[key] = len(seen_seq)
            base = names[min(seen_seq[key], 3)]
        if kind == "bs":
            tags.append(base)
            continue
        if "3개월" in c:
            tags.append(base + "_q")
        elif "누적" in c:
            tags.append(base + "_ytd")
        else:
            tags.append(base + "_full")
    # 같은 태그가 두 번이면(3개월·누적 라벨이 없는 2열) 왼쪽 3개월·오른쫃 누적으로 본다 — 드물다
    return tags


def statements_of(html):
    """절 HTML → {'bs': {...}, 'is': {...}, 'cis': {...}, 'cf': {...}, 'sce': {...}}
    각 값: {'title','unit_mul','unit_assumed','cols','tags','rows':[[label, v1, v2, ...](백만원)]}"""
    out = {}
    pending = None                                    # (kind, unit_mul, title)
    last_kind = None
    for t in parse_tables(html):
        if _is_caption(t):
            text = " ".join(c for r in t["rows"] for c in r)
            kind = _kind_of(text) or _kind_of(t.get("lead"))
            mul = unit_mul_of(text) or unit_mul_of(t.get("lead"))
            if kind or mul:
                pending = (kind or (pending[0] if pending else None),
                           mul or (pending[1] if pending and kind is None else None) or mul,
                           (text or t.get("lead") or "")[:80])
            continue
        cols, rows = _split_hdr(t)
        numeric = [r for r in rows if any(num_of(c) is not None for c in r[1:])]
        if not numeric:
            continue
        kind = None
        mul = None
        title = ""
        if pending:
            kind, mul, title = pending
            pending = None
        if not kind:
            kind = _kind_of(t.get("lead"))
            mul = unit_mul_of(t.get("lead"))
            title = (t.get("lead") or "")[-80:]
        if not kind:
            # 캡션 없는 이어지는 표 — 직전 재무제표의 연속(열 수 같을 때)
            if last_kind and out.get(last_kind) and len(cols) == len(out[last_kind]["cols"]):
                kind = last_kind
                mul = out[last_kind]["unit_mul"]
            else:
                continue
        assumed = mul is None
        mul = 1e-6 if mul is None else mul
        conv, rawrows = [], []
        for r in rows:
            lab = (r[0] if r else "").strip()
            vals = [to_million(c, mul) for c in r[1:]]
            conv.append([lab] + vals)
            rawrows.append([lab] + [num_of(c) for c in r[1:]])   # 주당 값(원)은 환산 전 숫자가 필요하다
        tags = tag_cols(cols, "bs" if kind == "bs" else "is") if cols else []
        if kind in out and out[kind]["cols"] == cols:
            out[kind]["rows"].extend(conv)              # 같은 표가 둘로 나뉜 경우
            out[kind]["raw_rows"].extend(rawrows)
        elif kind in out:
            # 같은 종류가 다시 나오면(예: 별도 절에 연결 표가 섞임) 먼저 나온 것을 지킨다
            continue
        else:
            out[kind] = {"title": title, "unit_mul": mul, "unit_assumed": assumed,
                         "cols": cols, "tags": tags, "rows": conv, "raw_rows": rawrows}
        last_kind = kind
    return out


# ── 재무제표 → 계정 ──────────────────────────────────────────────────────
def _entries_for(stmt, section, label):
    """정규화 라벨에 맞는 ACCOUNT_MAP 항목 — BS 는 현재 구역 항목을 먼저, 구역 무관 항목을 그 다음."""
    hits = []
    for st, sec, rx, tg, opt in _COMPILED:
        if st != stmt or not rx.match(label):
            continue
        if stmt == "bs":
            if sec is None:
                hits.append((1, tg, opt))
            elif sec == section:
                hits.append((0, tg, opt))
            elif section is None:
                hits.append((2, tg, opt))            # 구역을 아직 못 정했으면 첫 매치를 쓴다
        else:
            hits.append((0, tg, opt))
    if not hits:
        return None
    hits.sort(key=lambda h: h[0])
    return hits[0][1], hits[0][2]


def map_statement(stmt, table):
    """{'tags','rows'} → (태그별 {계정: 값}, raw_labels[[라벨, 당기값]], eps 태그별 값)"""
    tags = table["tags"]
    acc = {tg: {} for tg in tags}
    raw = []
    eps = {}
    dups = []
    seen_bs = {}                                     # (구역, 라벨) → 태그별 값 — 같은 구역 반복 라벨은 마지막 값으로
    section = None
    ctx = "pl"                                       # IS: 'pl'(순이익 귀속) / 'ci'(포괄이익 귀속)
    in_attr = False                                  # IS: '…의 귀속' 블록 안(지배/비지배별 계속·중단영업이익 — 총액이 아니다)
    op_zone, op_raw = False, []                      # IS: 매출총이익~영업이익 사이의 매핑 안 된 줄(태그별 값) — 판관비 잔차 보정용
    for ri, r in enumerate(table["rows"]):
        label, vals = r[0], r[1:]
        nl = norm_label(label)
        if not nl:
            continue
        if stmt == "bs":
            for sec, rx in _SECTION_OF:
                if rx.match(nl):
                    section = sec
                    break
        if stmt == "is":
            if re.search(r"귀속$", nl):
                in_attr = True                        # '당기순이익의 귀속'·'포괄손익의 귀속' 이후 줄들은 귀속 분해
                ctx = "ci" if "포괄" in nl else "pl"   # 어느 귀속인지 — 순이익 귀속만 (지배주주지분)당기순이익 으로 잡는다
            elif re.search(r"포괄(손익|이익)", nl):
                ctx = "ci"
                in_attr = False
            elif re.match(r"^((당|반|분)기순(이익|손익)|연결(당|반|분)기순(이익|손익))$", nl):
                ctx = "pl"
        if all(v is None for v in vals):
            continue                                  # 구역 머리(자산·부채·자본) 등 값 없는 줄
        hit = _entries_for(stmt, section, nl)
        if hit is None:
            raw.append([label, vals[0] if vals else None])
            if stmt == "is" and op_zone:
                op_raw.append([label] + list(vals))   # 매출총이익~영업이익 사이의 매핑 안 된 줄(금강공업 '물류비', 영흥 '대손상각비')
            continue
        if stmt == "is" and "매출총이익" in hit[0]:
            op_zone = True                            # 매출총이익 줄 이후 ~ 영업이익 줄 이전 = 영업비용 구간
        targets, opt = hit
        if opt.get("attrib"):
            in_attr = True                            # '지배기업 소유주지분' 줄 자체가 귀속 시작(세진 FY2023 은 '…의 귀속' 머리 없이 바로 시작)
            if ctx == "ci":
                continue                              # 포괄이익의 지배/비지배 귀속 — 순이익 귀속이 아니다
        if opt.get("cont_disc") and in_attr:
            continue                                  # 귀속 블록의 '계속영업이익'(세진 FY2023: 지배주주분 17,757 ≠ 총액) — 총액은 synth 로
        if stmt == "is" and "영업이익" in targets:
            op_zone = False                           # 영업이익 줄 이후는 영업외
        if opt.get("eps"):
            rawv = table.get("raw_rows", [[None]])[ri][1:] if ri < len(table.get("raw_rows", [])) else vals
            for tg, v in zip(tags, rawv):
                if v is not None and tg not in eps:
                    eps[tg] = v                                  # 주당 값(원) — 환산하지 않는다
            continue
        if stmt == "bs":
            k2 = (section, nl)
            if k2 in seen_bs:
                dups.append(label)
                for tg, old_v in seen_bs[k2].items():
                    for key in targets:
                        if key in acc[tg] and old_v is not None:
                            acc[tg][key] = round(acc[tg][key] - old_v, 2)
            seen_bs[k2] = dict(zip(tags, vals))
        for tg, v in zip(tags, vals):
            if v is None:
                continue
            if opt.get("abs"):
                v = abs(v)
            for key in targets:
                # 손익계산서는 같은 계정이 두 번 나오면(귀속 블록의 '계속영업이익' 반복, '반기순이익' 머리 재등장) 처음 값을 지킨다.
                # BS·CF 는 더한다(매입채무+미지급금+미지급비용 → 매입채무및기타채무, 유형+사용권 감가상각비 등).
                if key in acc[tg] and (stmt == "is" or key in ("자산총계", "부채총계", "자본총계")):
                    continue
                _add(acc[tg], key, v)
    return acc, raw, eps, dups, op_raw


def absorb_op_zone(acc, tags, op_raw):
    """매출총이익 − 판관비 − 영업이익 잔차가 영업비용 구간의 매핑 안 된 줄 합과 맞으면 그 줄들을 판관비에 더한다
    (FnGuide 판관비 = 매출총이익 − 영업이익 관행; 금강공업 '물류비' 5,633·영흥 '대손상각비' 417 실측).
    맞지 않으면 손대지 않는다 — 항등식 불일치가 checks 에 그대로 남는다. 반환: [(태그, 잔차, 라벨들)]."""
    done = []
    if not op_raw:
        return done
    for i, tg in enumerate(tags):
        a = acc.get(tg) or {}
        gp, sga, op = a.get("매출총이익"), a.get("판관비"), a.get("영업이익")
        if None in (gp, sga, op) or a.get("기타영업비용") is not None or a.get("기타영업수익") is not None:
            continue
        resid = round(gp - sga - op, 2)
        if abs(resid) <= 1.0:
            continue
        vals = [r[1 + i] for r in op_raw if 1 + i < len(r) and r[1 + i] is not None]
        if not vals or len(vals) > 8 or not _signs_explain(vals, resid):
            continue
        a["판관비"] = round(sga + resid, 2)
        done.append((tg, resid, [r[0] for r in op_raw]))
    return done


def _signs_explain(vals, target, tol=1.0):
    """±부호 조합으로 vals 의 합이 target 이 되는가 — '대손상각비환입(대손상각비)' 처럼 환입(수익)을 양수로 적은 줄은
    빼야 맞는다(금강공업 2022Q3: 물류비 4,300 − 환입 935 = 잔차 3,365). 줄 수 ≤ 8 이라 전수(2^n) 로 본다."""
    n = len(vals)
    for mask in range(1 << n):
        s = sum(v if mask >> k & 1 else -v for k, v in enumerate(vals))
        if abs(s - target) <= tol:
            return True
    return False


def synth_bs(a, issues=None, quarter=None, scope=None):
    """BS 합성 계정. 없는 구성요소는 0 이 아니라 None — 구성요소가 하나도 없으면 만들지 않는다."""
    if "지배주주지분" not in a and "자본총계" in a and "비지배주주지분" not in a:
        a["지배주주지분"] = a["자본총계"]
    if "유동자산" not in a and "자산총계" in a and "비유동자산" in a:
        a["유동자산"] = _sub(a["자산총계"], a["비유동자산"])
    if "비유동자산" not in a and "자산총계" in a and "유동자산" in a:
        a["비유동자산"] = _sub(a["자산총계"], a["유동자산"])
    if "유동부채" not in a and "부채총계" in a and "비유동부채" in a:
        a["유동부채"] = _sub(a["부채총계"], a["비유동부채"])
    if "비유동부채" not in a and "부채총계" in a and "유동부채" in a:
        a["비유동부채"] = _sub(a["부채총계"], a["유동부채"])
    tot = _sum(*[a.get(k) for k in ("단기차입금", "단기사채", "유동성장기부채", "장기차입금", "사채")])
    if tot is not None:
        a["총차입금"] = tot
        if a.get("현금및현금성자산") is not None:
            a["순차입금"] = round(tot - (a.get("현금및현금성자산") or 0) - (a.get("단기금융자산") or 0), 2)
    face = [k for k in ("단기금융부채(face)", "장기금융부채(face)") if a.get(k) is not None]
    if face and issues is not None:
        issues.append({"quarter": quarter, "scope": scope, "code": "borrowings_face_label",
                       "detail": "face 라벨 %s 를 차입금으로 봄(FnGuide 관행) — 단기차입금/유동성장기부채 분리는 주석 필요" % "·".join(face)})
    ia = _sum(a.get("현금및현금성자산"), a.get("단기금융자산"), a.get("장기금융자산"))
    if ia is not None:
        a["이자발생자산"] = ia
    return a


def normalize_expense_signs(a):
    """비용 음수 표기(괄호) 관행 정규화 — 매출액 > 0 이고 매출원가 < 0(원가가 없으면 판관비 < 0)이면 EXPENSE_KEYS 부호를 뒤집는다.
    표(열) 단위로 판정한다 — 같은 회사라도 분기보고서는 양수·사업보고서는 음수인 경우(현대리바트 2025)가 있다. 뒤집었으면 True."""
    rev = a.get("매출액(수익)")
    if rev is None or rev <= 0:
        return False
    cogs, sga = a.get("매출원가"), a.get("판관비")
    neg = (cogs is not None and cogs < 0) or (cogs is None and sga is not None and sga < 0)
    if not neg:
        return False
    for k in EXPENSE_KEYS:
        if a.get(k) is not None:
            a[k] = round(-a[k], 2)
    return True


def synth_is(a, flags=None):
    """IS 합성 계정 + 법인세 부호 검증. '법인세비용(수익)' 라벨에 양수로 적힌 법인세수익(미포 2022)은
    세전 − 법인세 = 계속사업이익(없으면 당기순이익) 항등식으로 잡아 부호를 뒤집고 flags 에 남긴다.
    계속사업이익 총액 줄이 없으면(세진 FY2023 — 귀속 블록에만 있음) 당기순이익 − 중단사업이익 으로 만든다."""
    if "계속사업이익" not in a and a.get("당기순이익") is not None and a.get("중단사업이익") is not None:
        a["계속사업이익"] = _sub(a["당기순이익"], a["중단사업이익"])
    pre, tax = a.get("법인세비용차감전계속사업이익"), a.get("법인세비용")
    ni = a.get("계속사업이익") if a.get("계속사업이익") is not None and "중단사업이익" in a else a.get("당기순이익")
    if pre is not None and tax is not None and ni is not None:
        if abs(pre - tax - ni) > 1.0 and abs(pre + tax - ni) <= 1.0:
            a["법인세비용"] = -tax
            if flags is not None:
                flags.append(("tax_sign_flipped", "법인세비용 %s → %s (세전−법인세=순이익 항등식)" % (tax, -tax)))
    if "매출총이익" not in a and a.get("매출액(수익)") is not None and a.get("매출원가") is not None:
        a["매출총이익"] = _sub(a["매출액(수익)"], a["매출원가"])
    if "금융손익" not in a and (a.get("금융수익") is not None or a.get("금융비용") is not None):
        a["금융손익"] = round((a.get("금융수익") or 0) - (a.get("금융비용") or 0), 2)
    if "이자손익" not in a and a.get("이자수익") is not None and a.get("이자비용") is not None:
        a["이자손익"] = _sub(a["이자수익"], a["이자비용"])
    if "기타영업외손익" not in a and (a.get("기타영업외수익") is not None or a.get("기타영업외비용") is not None):
        a["기타영업외손익"] = round((a.get("기타영업외수익") or 0) - (a.get("기타영업외비용") or 0), 2)
    if "기타영업손익" not in a and (a.get("기타영업수익") is not None or a.get("기타영업비용") is not None):
        a["기타영업손익"] = round((a.get("기타영업수익") or 0) - (a.get("기타영업비용") or 0), 2)
    if "(지배주주지분)당기순이익" not in a and a.get("당기순이익") is not None and "(비지배주주지분)당기순이익" not in a:
        a["(지배주주지분)당기순이익"] = a["당기순이익"]
    if "계속사업이익" not in a and a.get("당기순이익") is not None and "중단사업이익" not in a:
        a["계속사업이익"] = a["당기순이익"]
    return a


def parse_fin_section(html):
    """연결(또는 별도) 절 HTML 전체 → {'found','bs':{tag:{}},'is':{tag:{}},'cf':{tag:{}},'raw_labels',
    'eps','unit_assumed','has_bs'}. IS 는 손익계산서가 없으면 포괄손익계산서에서 읽는다(단일 포괄손익계산서 회사)."""
    st = statements_of(html)
    out = {"found": sorted(st), "bs": {}, "is": {}, "cf": {}, "raw_labels": {}, "eps": {}, "dups": [], "flags": [],
           "unit_assumed": any(v["unit_assumed"] for v in st.values()), "has_bs": "bs" in st}
    if "bs" in st:
        acc, raw, _, dups, _ = map_statement("bs", st["bs"])
        out["bs"] = {tg: synth_bs(v) for tg, v in acc.items()}
        out["raw_labels"]["bs"] = raw
        out["dups"] = dups
    is_src = st.get("is") or st.get("cis")
    if is_src:
        acc, raw, eps, _, op_raw = map_statement("is", is_src)
        flags = []
        flipped = [tg for tg, v in acc.items() if normalize_expense_signs(v)]     # synth 보다 먼저 — 합성 계정이 부호를 물려받는다
        if any(tg.startswith("cur") for tg in flipped):
            flags.append(("expense_sign_negative", "face 가 비용을 괄호(음수)로 표기 — %s 를 양수로 뒤집음(열 %s)"
                          % ("·".join(k for k in EXPENSE_KEYS if any(k in acc[tg] for tg in flipped)), ",".join(flipped))))
        for tg, resid, labels in absorb_op_zone(acc, is_src["tags"], op_raw):
            if tg.startswith("cur"):
                flags.append(("sga_absorbed_op_lines", "판관비 += %s (매출총이익−판관비−영업이익 잔차 = 영업비용 구간 줄 %s, 열 %s)"
                              % (resid, "·".join(labels), tg)))
        out["is"] = {tg: synth_is(v, flags if tg.startswith("cur") else None) for tg, v in acc.items()}
        out["flags"] = flags
        out["raw_labels"]["is"] = raw
        out["eps"] = eps
        if "is" in st and "cis" in st:
            # 총포괄손익은 포괄손익계산서에서 보충한다
            acc2, _, _, _, _ = map_statement("is", st["cis"])
            for tg, v in acc2.items():
                if "총포괄손익" in v and tg in out["is"]:
                    out["is"][tg].setdefault("총포괄손익", v["총포괄손익"])
    if "cf" in st:
        acc, raw, _, _, _ = map_statement("cf", st["cf"])
        out["cf"] = acc
        out["raw_labels"]["cf"] = raw
    return out


# ── 주식의 총수 · 배당 ────────────────────────────────────────────────────
_BASE_DATE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")


def parse_shares(html):
    """'주식의 총수 현황' 표 → {'as_of','issued','treasury','outstanding','common_issued','common_treasury',
    'common_outstanding','pref_issued'} (주). 표를 못 찾으면 None."""
    as_of = None
    for t in parse_tables(html):
        text = " ".join(c for r in t["rows"] for c in r) + " " + " ".join(t["cols"])
        m = _BASE_DATE.search(text) or _BASE_DATE.search(t.get("lead") or "")
        if m and as_of is None:
            as_of = "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
        cols = [norm_label(c) for c in t["cols"]]
        if not cols:
            continue
        idx = {}
        col_basis = "header"
        for i, c in enumerate(cols):
            # KCC·현대리바트·한국선재는 '보통주/우선주' 대신 '의결권 있는 주식/의결권 없는 주식' 으로 적는다(각주 "상기 의결권 있는 주식은 보통주입니다")
            for key, pat in (("common", r"보통주|의결권있는"), ("pref", r"우선주|의결권없는|종류주"), ("total", r"합계")):
                if re.search(pat, c) and key not in idx:
                    idx[key] = i
        if "common" not in idx and "total" in idx and idx["total"] >= 3:
            # 종류 머리가 '-' 로 비어 있는 표(한신기계 2022Q1 '주식의 종류 -') — 합계 왼쪽 두 열을 보통주·우선주 순으로 본다(공시서식 순서)
            ti = idx["total"]
            if all(re.sub(r"주식의종류", "", cols[j]) in ("", "-") for j in (ti - 2, ti - 1)):
                idx["common"], idx["pref"], col_basis = ti - 2, ti - 1, "positional"
        if "common" not in idx:
            continue
        rows = {}
        for r in t["rows"]:
            nl = norm_label(r[0] if r else "")
            if not nl and len(r) > 1:
                nl = norm_label(r[1])
            key = None
            if re.match(r"^발행주식의총수", nl) or re.match(r"^발행주식(총)?수$", nl):
                key = "issued"
            elif re.match(r"^자기주식(수)?$", nl):
                key = "treasury"
            elif re.match(r"^유통주식(수)?$", nl):
                key = "outstanding"
            elif re.match(r"^현재까지발행한주식의총수", nl):
                key = "issued_cum"
            if not key or key in rows:
                continue

            def cell(k):
                i = idx.get(k)
                if i is None or i >= len(r):
                    return None
                v = num_of(r[i])
                return int(v) if v is not None else (0 if r[i].strip() in ("-", "—", "–") else None)
            rows[key] = {"common": cell("common"), "pref": cell("pref"), "total": cell("total")}
        if "issued" not in rows and "issued_cum" in rows:
            rows["issued"] = rows["issued_cum"]
        if "issued" not in rows:
            continue

        def tot(k):
            d = rows.get(k) or {}
            if d.get("total") is not None:
                return d["total"]
            return _sum(d.get("common"), d.get("pref"))
        issued, treas, outs = tot("issued"), tot("treasury"), tot("outstanding")
        treas = 0 if treas is None else treas
        if outs is None and issued is not None:
            outs = issued - treas
        ci = (rows["issued"] or {}).get("common")
        ct = (rows.get("treasury") or {}).get("common") or 0
        co = (rows.get("outstanding") or {}).get("common")
        if co is None and ci is not None:
            co = ci - ct
        out = {"as_of": as_of, "issued": int(issued) if issued is not None else None, "treasury": int(treas),
               "outstanding": int(outs) if outs is not None else None,
               "common_issued": ci, "common_treasury": ct, "common_outstanding": co,
               "pref_issued": (rows["issued"] or {}).get("pref") or 0}
        if col_basis != "header":
            out["col_basis"] = col_basis
        return out
    return None


# '변동사항이 없으며 … 사업보고서를 참고'(금강공업·오리엔탈정공 1·3분기), '작성을 생략합니다'(오리엔탈정공 2026Q1) 도 생략이다
_SHARES_OMITTED = re.compile(r"기재하지\s*(않|아니)|기재(를|는)?\s*생략|생략하였|작성하지\s*(않|아니)|아니할\s*수|작성을\s*생략|변동\s*사항이\s*없")


def shares_omitted(html):
    """분기보고서 '주식의 총수 등' 기재 생략 문구인가 — 표가 없을 때만 부른다.
    '해당사항 없습니다' 는 자기주식 신탁·종류주식 소절의 상투어라 생략 판정에 쓰지 않는다(KCC 전 분기 오판 실측)."""
    return bool(_SHARES_OMITTED.search(re.sub(r"<[^>]+>", " ", html or "")))


def parse_dividend(html):
    """'최근 3사업연도 배당에 관한 사항' 표 → {'dps_common','payout_pct','cash_div_total_m','term'} (당기 열).
    주당 현금배당금이 '-' 이면 0(무배당). 표를 못 찾으면 None."""
    for t in parse_tables(html):
        cols = [norm_label(c) for c in t["cols"]]
        labels = [norm_label(r[0]) for r in t["rows"] if r]
        if not any(re.match(r"^주당현금배당금", l) for l in labels):
            continue
        ci = None
        for i, c in enumerate(cols):
            if "당기" in c and "전기" not in c and "전전기" not in c:
                ci = i
                break
        if ci is None:
            ci = 2 if len(cols) >= 4 else 1
        term = None
        if ci < len(t["cols"]):
            m = re.search(r"제\s*(\d+)\s*기", t["cols"][ci])
            term = int(m.group(1)) if m else None
        out = {"dps_common": None, "payout_pct": None, "cash_div_total_m": None, "term": term, "dps_row_kind": None}

        def val(r):
            if ci >= len(r):
                return None
            s_ = r[ci].strip()
            v = num_of(s_)
            if v is None and s_ in ("-", "—", "–", ""):
                return 0
            return v
        dps_rows = []
        for r in t["rows"]:
            nl = norm_label(r[0])
            kind = norm_label(r[1]) if len(r) > 1 else ""
            if re.match(r"^주당현금배당금", nl):
                dps_rows.append((kind if kind != nl else "", val(r)))
            elif re.match(r"^\(?연결\)?현금배당성향", nl) or nl == "현금배당성향":
                out["payout_pct"] = val(r)
            elif re.match(r"^현금배당금총액", nl):
                out["cash_div_total_m"] = val(r)
        # 보통주 행 숫자 → 없으면 숫자 있는 첫 행(회사가 종류 칸을 비우거나 '우선주' 칸에 적는 경우) → 없으면 0
        pick = [x for x in dps_rows if x[0] in ("보통주", "보통주식") and x[1]]
        if not pick:
            pick = [x for x in dps_rows if x[1]]
        if pick:
            out["dps_row_kind"], out["dps_common"] = pick[0][0] or "-", pick[0][1]
        elif dps_rows:
            out["dps_row_kind"], out["dps_common"] = dps_rows[0][0] or "-", 0
        if out["dps_common"] and out["cash_div_total_m"] == 0:
            out["cash_div_total_m"] = None
        return out
    return None


# ── 주석 표 파서(MODEL_SPEC §5-1) ─────────────────────────────────────────────
# 회사마다 형식이 다르다(2026Q2 실측):
#   · 삼성重 `18. 금융수익과 금융원가` — 캡션 표(`금융수익과 금융원가 / 당반기 / (단위 : 천원)`) 뒤 데이터 표, 머리
#     `장부금액 공시금액 3개월 | 누적`, 행 라벨 이자수익·외환차익·파생상품평가이익·파생상품거래이익·금융수익 합계…; 전반기 블록이 뒤따른다
#   · 세진 `29. 금융수익과 금융비용` — 라벨 열이 둘(구분·항목: `금융수익 | 이자수익`), 항목에 `(금융수익)`·`(금융원가)` 꼬리,
#     구분 합계 줄(`금융수익 | 금융수익`)과 순액 줄(`금융수익(비용)`)이 섞여 있다
#   · 차입금: 한라IMS 는 `단기차입금/유동성장기차입금/장기차입금` 세 줄, 세진은 은행별 열 그리드 + `합계` 열에 XBRL 표준 라벨
#     (`유동 차입금(사채 포함)`·`비유동차입금(사채 포함)의 유동성 대체 부분`·`비유동 차입금(사채 포함)의 비유동성 부분`), 삼성重은
#     기초·차입·상환·기말 증감표만(분해 없음 → raw 에만 남고 face 를 건드리지 않는다)
# 표 제목·행 라벨 정규식으로 잡고, 못 잡은 줄은 raw 로 남긴다. 기간(당/전)은 머리 열에 있으면 그것, 없으면 캡션(lead 끝)에서.
_NOTE_SFX = re.compile(r"\((금융수익|금융원가|금융비용|기타수익|기타비용|영업외수익|영업외비용|금융|기타)\)$")
_NOTE_PERIOD = re.compile(r"(당|전전|전)\s*(반|분)?\s*기(말)?")
_NOTE_LABEL_HDR = re.compile(r"^(구분|계정과목|과목|항목|내역|종류|계정|구성내역)?$")
_NOTE_SKIP_ROW = re.compile(r"이자율|만기|기술$|성격|명칭$|비고")
_NOTE_NET = re.compile(r"금융수익\((비용|원가)\)|순금융|금융손익|순기타손익|기타손익|순액|기타수익\(비용\)")
NOTE_SUM_KEYS = {"파생상품이익", "파생상품손실"}                  # 평가+거래 두 줄을 더한다 — 나머지는 표 안 첫 줄이 이긴다
NOTE_MAPS = {
    "fin": [
        (r"^이자수익$", "이자수익"), (r"^배당금수익$", "배당금수익"),
        (r"^외환차익$", "외환차익"), (r"^외화환산이익$", "외화환산이익"),
        (r"^(파생(금융)?상품(평가|거래)?이익|파생상품평가및거래이익|파생상품관련이익)$", "파생상품이익"),
        (r"^이자비용$", "이자비용"),
        (r"^외환차손$", "외환차손"), (r"^외화환산손실$", "외화환산손실"),
        (r"^(파생(금융)?상품(평가|거래)?손실|파생상품평가및거래손실|파생상품관련손실)$", "파생상품손실"),
        (r"^금융수익(합계|계|소계)?$", "금융수익합계"),
        (r"^금융(원가|비용)(합계|계|소계)?$", "금융비용합계"),
    ],
    "other": [
        (r"^외환차익$", "외환차익"), (r"^외화환산이익$", "외화환산이익"),
        (r"^(파생(금융)?상품(평가|거래)?이익|파생상품평가및거래이익)$", "파생상품이익"),
        (r"^외환차손$", "외환차손"), (r"^외화환산손실$", "외화환산손실"),
        (r"^(파생(금융)?상품(평가|거래)?손실|파생상품평가및거래손실)$", "파생상품손실"),
        (r"^기타(영업외)?수익(합계|계|소계)?$", "기타수익합계"),
        (r"^기타(영업외)?비용(합계|계|소계)?$", "기타비용합계"),
    ],
    "borrowings": [
        (r"^(단기차입금(소계|합계)?|유동차입금(\(사채포함\))?|단기차입부채|유동차입부채)$", "단기차입금"),   # 세진 `단기차입금 소 계`
        (r"^(유동성장기차입금|유동성장기부채|비유동차입금(\(사채포함\))?의유동성대체부분|유동성사채|유동성장기차입금및사채|유동성장기차입부채"
         r"|유동성장기(부채|차입금)대체|유동성대체(액)?|유동성장기차입금(소계|합계))$", "유동성장기부채"),     # 한일철강 장기차입금 표 `유동성 장기부채 대체 (20,494,000,000)`
        (r"^(장기차입금|비유동차입금(\(사채포함\))?의비유동성부분|비유동차입금|장기차입부채|비유동차입부채|장기차입금잔액)$", "장기차입금"),
        (r"^(사채|비유동사채|장기사채|전환사채|신주인수권부사채|교환사채)$", "사채"),
        (r"^(단기사채|전자단기사채)$", "단기사채"),
        (r"^(유동|단기)리스부채$", "리스부채(유동)"), (r"^(비유동|장기)리스부채$", "리스부채(비유동)"),
    ],
}
_NOTE_MAPS_C = {k: [(re.compile(rx), acct) for rx, acct in v] for k, v in NOTE_MAPS.items()}
NOTE_TOTAL_KEYS = {"금융수익합계", "금융비용합계", "기타수익합계", "기타비용합계", "순액"}
# is/bs 로 올릴 수 있는 계정(face 에 없을 때만) — MODEL_SPEC §5-1
NOTE_PROMOTE_IS = ("이자수익", "배당금수익", "이자비용", "외환차익", "외환차손", "외화환산이익", "외화환산손실", "파생상품이익", "파생상품손실")
NOTE_PROMOTE_BS = ("단기차입금", "유동성장기부채", "장기차입금", "사채")


def norm_note_label(s):
    """주석 행 라벨 정규화 — norm_label 뒤 `(금융수익)`·`(금융원가)`·`(기타비용)` 같은 구분 꼬리를 뗀다(세진)."""
    return _NOTE_SFX.sub("", norm_label(s))


def _period_of(text):
    """'당반기·당분기·당기(말)' → cur, '전반기·전기(말)' → prev, '전전기' → prev2 — 마지막 등장을 쓴다(캡션 끝이 표에 가장 가깝다)."""
    last = None
    for m in _NOTE_PERIOD.finditer(unicodedata.normalize("NFKC", text or "")):
        last = m
    if not last:
        return None
    return {"당": "cur", "전": "prev", "전전": "prev2"}[last.group(1)]


def tag_note_cols(cols, lead, prefer_total=False):
    """주석 표 머리 → (라벨 열 수, [(열 index, 태그)]). 태그 cur_q/cur_ytd/cur_full/prev_…: 기간은 머리 열에 있으면 그것, 없으면
    캡션(lead 끝 60자)에서; 3개월/누적 표기가 없으면 _full(분기보고서면 누적, 사업보고서면 연간 — 호출측이 face 태그에 맞춘다).
    prefer_total(차입금 그리드): 같은 기간의 열이 여럿이면 머리에 '합계' 가 든 마지막 열만 남긴다(세진 은행별 열)."""
    ncols = [re.sub(r"\s+", " ", unicodedata.normalize("NFKC", c or "")).strip() for c in cols]
    nlab = 0
    while nlab < len(ncols) and _NOTE_LABEL_HDR.match(ncols[nlab].replace(" ", "")):
        nlab += 1
    nlab = max(1, nlab)
    lead_p = _period_of((lead or "")[-60:])
    tags = []
    for i in range(nlab, len(ncols)):
        c = ncols[i]
        p = _period_of(c) or lead_p
        if p is None:
            continue
        sfx = "_q" if "3개월" in c else ("_ytd" if "누적" in c else "_full")
        tags.append((i, p + sfx))
    if prefer_total and tags:
        by = {}
        for i, tg in tags:
            by.setdefault(tg, []).append(i)
        picked = []
        for tg, idxs in by.items():
            tot = [i for i in idxs if "합계" in ncols[i]]
            picked.append(((tot or idxs)[-1], tg))
        tags = sorted(picked)
    return nlab, tags


def _map_note_label(key, raw_label):
    nl0 = re.sub(r"\s+", "", unicodedata.normalize("NFKC", raw_label or ""))
    if key in ("fin", "other") and _NOTE_NET.search(nl0):
        return "순액"                                     # '금융수익(비용)'·'순기타손익' — 합계와 섞이면 안 된다
    nl = norm_note_label(raw_label)
    for rx, acct in _NOTE_MAPS_C[key]:
        if rx.match(nl):
            return acct
    return None


def parse_note_section(html, key):
    """주석 절 HTML → {'found', 'acc': {태그: {계정: 백만원}}, 'raw': [[라벨, {태그: 값}], …], 'unit_assumed'}.
    key: fin / other / borrowings (NOTE_MAPS). 표 안에서는 NOTE_SUM_KEYS 만 더하고 나머지는 첫 줄이 이긴다;
    표 사이에서는 (태그, 계정) 첫 표가 이긴다(범주별 손익표처럼 같은 라벨이 다른 표에 다시 나와도 두 배로 세지 않는다)."""
    out = {"found": False, "acc": {}, "raw": [], "unit_assumed": False}
    last_mul = None
    for t in parse_tables(html):
        if _is_caption(t):
            m = unit_mul_of(" ".join(c for r in t["rows"] for c in r)) or unit_mul_of(t.get("lead"))
            if m:
                last_mul = m
            continue
        cols, rows = _split_hdr(t)
        if not cols:
            continue
        nlab, tags = tag_note_cols(cols, t.get("lead"), prefer_total=(key == "borrowings"))
        if not tags:
            continue
        mul = unit_mul_of(t.get("lead")) or unit_mul_of(" ".join(cols)) or last_mul
        if mul is None:
            out["unit_assumed"] = True
            mul = 1e-6
        last_mul = mul
        tacc = {}
        for r in rows:
            labs = [c.strip() for c in r[:nlab]]
            item = next((l for l in reversed(labs) if l), "")
            if not item or _NOTE_SKIP_ROW.search(re.sub(r"\s+", "", item)):
                continue
            vals = {}
            for i, tg in tags:
                if i < len(r):
                    v = to_million(r[i], mul)
                    if v is not None:
                        vals.setdefault(tg, v)
            if not vals:
                continue
            out["found"] = True
            acct = _map_note_label(key, item)
            if acct is None:
                if len(out["raw"]) < 60:
                    out["raw"].append([item, vals])
                continue
            for tg, v in vals.items():
                if key == "borrowings":
                    v = abs(v)                              # 세진: 장기표의 '유동성 대체 부분' 이 (85,480,000) 차감 표기
                d = tacc.setdefault(tg, {})
                if acct in NOTE_SUM_KEYS and acct in d:
                    d[acct] = round(d[acct] + v, 2)
                else:
                    d.setdefault(acct, v)
        for tg, d in tacc.items():
            dst = out["acc"].setdefault(tg, {})
            for acct, v in d.items():
                dst.setdefault(acct, v)
    return out


def merge_note_parts(parts):
    """같은 키의 주석이 둘로 갈린 경우(fin·fin2) 합친다 — (태그, 계정) 첫 것이 이기고 raw 는 이어 붙인다."""
    out = {"found": False, "acc": {}, "raw": [], "unit_assumed": False}
    for p in parts:
        if not p:
            continue
        out["found"] = out["found"] or p["found"]
        out["unit_assumed"] = out["unit_assumed"] or p["unit_assumed"]
        out["raw"].extend(p["raw"])
        for tg, d in p["acc"].items():
            dst = out["acc"].setdefault(tg, {})
            for acct, v in d.items():
                dst.setdefault(acct, v)
    return out


def _face_tag_for(note_tag, face_tags):
    """주석 태그를 face 손익 태그에 맞춘다 — 주석 `cur_full`(3개월/누적 표기 없음)은 분기보고서면 face `cur_ytd`, 사업보고서면 `cur_full`."""
    if note_tag in face_tags:
        return note_tag
    base, sfx = note_tag.rsplit("_", 1)
    if sfx == "full" and base + "_ytd" in face_tags:
        return base + "_ytd"
    if sfx == "ytd" and base + "_full" in face_tags:
        return base + "_full"
    return None


def inject_note_is(p, note, src):
    """금융수익 주석의 계정을 face 손익 태그 dict 에 **face 에 없을 때만** 넣고 합성 계정을 다시 만든다.
    face 에 없는 태그는 만들지 않는다(3개월 열이 없는 회사에 주석만으로 3m_column 을 만들면 안 된다).
    3개월 열(cur_q)로 들어간 계정만 여기서 src 에 적는다 — 누적으로만 온 계정의 3개월 값은 분기화 뒤 finalize_notes 가
    is_ytd_diff 에서 채우며 그때 `note:fin(ytd_diff)` 로 적는다."""
    isd = p.get("is") or {}
    if not isd or not note or not note.get("acc"):
        return
    for ntag, d in note["acc"].items():
        ftag = _face_tag_for(ntag, isd)
        if not ftag:
            continue
        tgt = isd[ftag]
        added = False
        for acct in NOTE_PROMOTE_IS:
            if d.get(acct) is not None and tgt.get(acct) is None:
                tgt[acct] = d[acct]
                added = True
                if ftag == "cur_q":
                    src.setdefault(acct, "note:fin(3m)")
        if added:
            synth_is(tgt)                                  # 이자손익 등 재합성(idempotent)


def inject_note_bs(b, note, src, issues, quarter, scope):
    """차입금 주석 → face BS(cur). ① face 에 없는 계정(단기차입금·유동성장기부채·장기차입금·사채)은 그대로 채운다.
    ② face 가 '단기금융부채'·'장기금융부채' 한 줄로 뭉친 회사(세진·미포 — `단기금융부채(face)` 키)는 주석 분해(단기차입금+유동성장기부채
    (+단기사채) / 장기차입금+사채)의 합이 그 덩어리와 맞을 때(±max(3백만원, 0.5%))만 갈라 넣고 (face) 키를 지운다 —
    안 맞으면(리스부채가 섞인 회사 등) 손대지 않고 `borrowings_note_unreconciled`. 분해가 없는 주석(삼성重 증감표)은 아무것도 안 한다."""
    if not b or not note:
        return
    acc = note.get("acc") or {}
    d = acc.get("cur_full") or acc.get("cur_ytd") or {}
    if not d:
        return
    blocked = set()                                        # 못 가른 덩어리의 구성 계정 — 따로 채우면 덩어리와 이중계산이다
    for lump, parts in (("단기금융부채(face)", ("단기차입금", "유동성장기부채", "단기사채")),
                        ("장기금융부채(face)", ("장기차입금", "사채"))):
        face_v = b.get(lump)
        if face_v is None:
            continue
        have = {k: d[k] for k in parts if d.get(k) is not None}
        if not have:
            blocked.update(parts)
            continue
        tot = round(sum(have.values()), 2)
        if abs(tot - face_v) <= max(3.0, abs(face_v) * 0.005):
            main = parts[0]                                # 덩어리가 들어가 있던 계정(단기차입금/장기차입금)에서 덩어리를 빼고 분해를 더한다
            b[main] = round((b.get(main) or 0.0) - face_v, 2)
            for k, v in have.items():
                b[k] = round((b.get(k) or 0.0) + v, 2)
                src[k] = "note:borrowings(split of face %s)" % lump[:-6]
            if abs(b[main]) < 0.01:
                b[main] = 0.0
            del b[lump]
        else:
            blocked.update(parts)
            issues.append({"quarter": quarter, "scope": scope, "code": "borrowings_note_unreconciled",
                           "detail": "%s %s vs 주석 분해 합 %s %s — 차이 %s, face 그대로" % (lump, face_v, tot, have, round(tot - face_v, 2))})
    for acct in NOTE_PROMOTE_BS:
        if acct in blocked:
            continue
        if d.get(acct) is not None and b.get(acct) is None:
            b[acct] = d[acct]
            src[acct] = "note:borrowings"


NOTE_FIN_ACCTS = ("이자수익", "배당금수익", "외환차익", "외화환산이익", "파생상품이익", "이자비용", "외환차손", "외화환산손실", "파생상품손실")
NOTE_BS_ACCTS = ("단기차입금", "유동성장기부채", "장기차입금", "사채", "단기사채", "리스부채(유동)", "리스부채(비유동)")


def finalize_notes(sc, notes_raw, src_notes, scope):
    """분기화 뒤 — `notes.{fin,borrowings,other}[q]`(MODEL_SPEC §5-1 모양) 를 만들고, 주석에서만 온 손익 계정의 3개월 값이
    face 3개월 열에 없으면 누적차분(is_ytd_diff)에서 `is` 로 채운다(`src_notes[q][계정] = note:fin(ytd_diff)`).
    fin/other 항목 값은 3개월(3개월 열 → 없으면 누적차분 → 없으면 null), `ytd` 에 누적(연간) 원값, `raw` 에 매핑 안 된 줄."""
    notes = {"fin": {}, "borrowings": {}, "other": {}}
    for q, parts in sorted(notes_raw.items()):
        src = src_notes.setdefault(q, {})
        i3, yd = sc["is"].get(q), sc["is_ytd_diff"].get(q)
        for key in ("fin", "other"):
            n = parts.get(key)
            if not n or not n.get("found"):
                continue
            acc = n["acc"]
            cur_q = acc.get("cur_q") or {}
            cur_y = acc.get("cur_ytd") or acc.get("cur_full") or {}
            entry = {}
            for acct in NOTE_FIN_ACCTS:
                v = cur_q.get(acct)
                if v is None and key == "fin" and yd and acct in cur_y:
                    v = yd.get(acct)                       # 3개월 열이 없으면 누적차분
                entry[acct] = v
            entry["ytd"] = {k: v for k, v in cur_y.items() if k not in NOTE_TOTAL_KEYS}
            entry["totals"] = {k: v for k, v in cur_y.items() if k in NOTE_TOTAL_KEYS}
            entry["basis"] = "3m_column" if cur_q else ("ytd_diff" if yd else "ytd_only")
            entry["raw"] = [[lab, vals.get("cur_q"), vals.get("cur_ytd", vals.get("cur_full"))] for lab, vals in n["raw"]]
            if n.get("unit_assumed"):
                entry["unit_assumed"] = True
            notes[key][q] = entry
            if key == "fin" and i3 is not None and yd:
                filled = False
                for acct in NOTE_PROMOTE_IS:
                    if i3.get(acct) is None and yd.get(acct) is not None and acct in cur_y:
                        i3[acct] = yd[acct]
                        src[acct] = "note:fin(ytd_diff)"
                        filled = True
                if filled:
                    synth_is(i3)
        n = parts.get("borrowings")
        if n and n.get("found"):
            acc = n["acc"]
            cur = acc.get("cur_full") or acc.get("cur_ytd") or {}
            entry = {k: cur.get(k) for k in NOTE_BS_ACCTS}
            entry["raw"] = [[lab, vals.get("cur_full", vals.get("cur_ytd"))] for lab, vals in n["raw"]]
            if n.get("unit_assumed"):
                entry["unit_assumed"] = True
            notes["borrowings"][q] = entry
    sc["notes"] = notes
    sc["src_notes"] = {q: s for q, s in sorted(src_notes.items()) if s}


# ── 주석 부모 절 폴백(하위 노드가 없는 보고서) ─────────────────────────────────
# 2025Q3 이전·중소형 보고서는 목차에 `3. 연결재무제표 주석` 부모만 있고 하위 노드가 없다(--collect-notes --all 999 중 786).
# 그 부모 절 하나(150~400KB)를 받아 **주석 블록**으로 자른 뒤 블록 제목을 하위 노드 제목처럼 NOTE_RX 로 판정하고, 고른 블록
# HTML 만 잘라 기존 parse_note_section 에 넘긴다. 한일철강 2023Q4 실측: 블록 머리는 `<P>` 안 텍스트 줄 `32. 금융수익 및 금융비용`·
# `22. 차입금`·`33. 기타수익 및 기타비용`(최상위 번호 1~39 가 차례로), 회계정책 소절 `3.15 금융부채`·`3.9 차입원가` 는 하위 번호라
# 블록이 아니다. `7. 범주별 금융상품` 블록에도 `이자수익(비용)` 순액 줄이 있어 fin 후보가 둘이 되므로 제목 순위와 행 검사로 가른다.
# ① 블록: 표 밖 텍스트 줄 중 `^\d{1,2}\.\s*제목`(소수 번호 제외)이 번호 순서(직전+1~+3)로 이어지는 것. 3개 미만이면
#    ② 캡션 모드 — 표 하나하나를 블록으로 보고(직전 표 끝 ~ 이 표 끝) 표 앞 글을 제목으로 쓴다.
# 순위: fin 은 금융수익·금융원가·금융비용(0) > 금융손익(1) > 금융상품(2, 행 라벨이 정확히 `이자수익`/`이자비용` 일 때만 —
# `이자수익(비용)` 순액 줄은 안 되고, 범주별 열 그리드·계정 반복·음수 비용 표도 안 된다 — _instruments_block_ok).
# borrowings 는 `차입` 제목(0) > 사채만(1) > `금융부채`(2, 세진 2023~ — 단기·장기차입금 줄이 있을 때만). 행 검사: fin 은
# `이자수익|이자비용` 줄, borrowings 는 `단기차입금|장기차입금|사채|유동성` 줄이 있는 블록만. 가장 좋은 순위의 블록만
# (fin ≤2, 나머지 1) 쓰므로 같은 숫자를 두 블록에서 세지 않는다.
PARENT_MIN_BLOCKS = 3
_PARENT_HEAD = re.compile(r"^(\d{1,2})\.(?!\d)\s*([^\d\s].{0,58})$")
_PARENT_FIN_RANK = ((re.compile(r"금융수익|금융원가|금융비용"), 0), (re.compile(r"금융손익"), 1), (re.compile(r"금융상품"), 2))
_PARENT_ROW_OK = {"fin": re.compile(r"이자수익|이자비용"),
                  "borrowings": re.compile(r"단기차입금|장기차입금|사채|유동성")}
_PARENT_FIN_STRICT = re.compile(r"^이자(수익|비용)$")
_TABLE_SPAN = re.compile(r"<table\b.*?</table\s*>", re.I | re.S)
_TEXT_NODE = re.compile(r">([^<]+)<")
_LINE_END = re.compile(r"<\s*(br|/p|p|table|/td|td|/div|div|/tr|tr)\b", re.I)          # 머리 줄이 끝나는 블록 경계
_CAP_ACCT = re.compile(r"단기차입금|장기차입금|(?<![가-힣])사채|유동성")
_TOTAL_ROW = re.compile(r"^(합계|계|총계|소계)$")


def _plain(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", html_unescape(s or ""))).strip()


def split_note_blocks(html):
    """부모 주석 절 HTML → [{'no', 'title', 'html'}] (문서 순서). 번호 머리가 3개 미만이면 표 단위 캡션 블록(no=None).
    블록 HTML 은 머리 텍스트부터 다음 머리 직전까지(캡션 모드는 직전 표 끝부터 이 표 끝까지) 원문 그대로 자른 것이다."""
    spans = [(m.start(), m.end()) for m in _TABLE_SPAN.finditer(html)]
    heads, last, si = [], 0, 0
    for m in _TEXT_NODE.finditer(html):
        pos = m.start(1)
        while si < len(spans) and spans[si][1] <= pos:
            si += 1
        if si < len(spans) and spans[si][0] <= pos:
            continue                                       # 표 안 텍스트는 머리가 아니다
        if not _plain(m.group(1))[:1].isdigit():
            continue
        e = _LINE_END.search(html, pos, pos + 600)
        t = _plain(re.sub(r"<[^>]+>", "", html[pos:e.start() if e else pos + 600]))   # `<SPAN>21. 차</SPAN><SPAN>입금</SPAN>` 처럼 쪼개진 머리
        h = _PARENT_HEAD.match(t)
        if not h or any(rx.search(t) for rx in _NOTES_PARENT.values()):
            continue                                       # `3. 연결재무제표 주석` 자기 제목은 건너뛴다
        n = int(h.group(1))
        if last < n <= last + 3:
            heads.append((pos, str(n), h.group(2).strip()))
            last = n
    if len(heads) >= PARENT_MIN_BLOCKS:
        out = []
        for i, (pos, no, title) in enumerate(heads):
            end = heads[i + 1][0] if i + 1 < len(heads) else len(html)
            out.append({"no": no, "title": title, "html": html[pos:end]})
        return out
    out, prev = [], 0
    for a, b in spans:
        gap = _plain(re.sub(r"<[^>]+>", " ", html[prev:a]))
        out.append({"no": None, "title": gap[-120:], "html": html[prev:b]})
        prev = b
    return out


def _block_labels(html):
    """블록 표들의 글자 셀(숫자 아닌 칸) — 공백 제거 NFKC. 행 검사용."""
    labs = []
    for t in parse_tables(html):
        _, rows = _split_hdr(t)
        for r in rows:
            for c in r:
                if c and num_of(c) is None:
                    labs.append(re.sub(r"\s+", "", unicodedata.normalize("NFKC", c)))
    return labs


def _instruments_block_ok(html):
    """금융상품(순위 2) 블록을 fin 으로 써도 되는가 — 범주별 순손익표는 대개 범주별 열 그리드(세진 `상각후원가…|FVPL|합계` — 첫 열만
    읽힌다)이거나 범주 소절마다 같은 계정이 다시 나오고(033500 외환차익 둘), 비용을 (음수)로 찍는다. 그래서 이자수익·이자비용 줄이
    있는 표가 ① 기간·구분 태그마다 열이 하나이고 ② 매핑 계정이 표 안에서 한 번씩만 나오며 ③ 비용 계정이 음수가 아닐 때만 쓴다."""
    seen_any = False
    for t in parse_tables(html):
        cols, rows = _split_hdr(t)
        if not cols:
            continue
        nlab, tags = tag_note_cols(cols, t.get("lead"))
        items = [next((c.strip() for c in reversed(r[:nlab]) if c.strip()), "") for r in rows]
        if not any(_PARENT_FIN_STRICT.match(re.sub(r"\s+", "", unicodedata.normalize("NFKC", it))) for it in items):
            continue
        seen_any = True
        if not tags or len({tg for _, tg in tags}) != len(tags):
            return False
        accts = [a for a in (_map_note_label("fin", it) for it in items if it) if a and a not in NOTE_TOTAL_KEYS]
        if any(accts.count(a) > 1 for a in set(accts) - NOTE_SUM_KEYS):
            return False
        for r, it in zip(rows, items):
            a = _map_note_label("fin", it) if it else None
            if a in ("이자비용", "외환차손", "외화환산손실", "파생상품손실"):
                if any((to_million(r[i], 1.0) or 0) < 0 for i, _ in tags if i < len(r)):
                    return False
    return seen_any


def _parent_rank(key, title):
    """블록 제목 → 이 키 후보 순위(작을수록 우선) 또는 None. 키 판정 순서는 find_note_nodes 와 같다(fin → borrowings → other)."""
    t = unicodedata.normalize("NFKC", title or "")
    for k in NOTE_KEYS:
        if NOTE_RX[k].search(t):
            if k != key:
                return None
            if key == "fin":
                return 0 if _PARENT_FIN_RANK[0][0].search(t) else 1
            if key == "borrowings":
                return 0 if "차입" in t else 1
            return 0
    if key == "fin" and _PARENT_FIN_RANK[2][0].search(t):
        return 2
    if key == "borrowings" and re.search(r"금융부채", t):
        return 2                                           # 세진 2023~ `16. 금융부채`(단기·장기금융부채 = 차입금) — 행 검사를 더 좁힌다
    return None


def _borrowings_caption_totals(html):
    """차입금 블록 보충 — 표 앞 글(마지막 `(n)` 뒤)이 단기차입금·장기차입금·사채 중 **하나만** 가리키고(유동성 언급 없음) 표 마지막
    줄이 `합계`(별도는 `소 계`)면 그 합계를 그 계정으로 본다. 단기차입금: 표 안에 매핑되는 줄이 하나도 없을 때만(한일철강 은행별 표).
    장기차입금·사채: 그 계정 줄은 없고 합계 앞에 `유동성 대체` 줄이 있을 때만 — 대체 뒤 합계가 비유동분이다(세진 `소계 191,745 /
    유동성 대체 (91,817) / 합계 99,928`; 한일철강 장기표는 마지막 줄이 `장기차입금 잔액` 이라 줄 매핑으로 잡힌다).
    중간 `소계` 는 보지 않는다(유동성 대체 전 금액). 반환 모양은 parse_note_section 과 같다."""
    out = {"found": False, "acc": {}, "raw": [], "unit_assumed": False}
    last_mul = None
    for t in parse_tables(html):
        lead = t.get("lead") or ""
        if _is_caption(t):
            last_mul = unit_mul_of(" ".join(c for r in t["rows"] for c in r)) or unit_mul_of(lead) or last_mul
            continue
        cols, rows = _split_hdr(t)
        if not cols:
            continue
        nlab, tags = tag_note_cols(cols, lead, prefer_total=True)
        mul = unit_mul_of(lead) or unit_mul_of(" ".join(cols)) or last_mul
        last_mul = mul or last_mul
        tail = re.sub(r"\s+", "", unicodedata.normalize("NFKC", re.split(r"\(\d+\)|[①-⑳]", lead)[-1]))
        accts = set(_CAP_ACCT.findall(tail))
        if not tags or len(accts) != 1 or "유동성" in accts:
            continue
        acct = {"단기차입금": "단기차입금", "장기차입금": "장기차입금", "사채": "사채"}[accts.pop()]
        items = [next((c.strip() for c in reversed(r[:nlab]) if c.strip()), "") for r in rows]
        mapped = [_map_note_label("borrowings", it) if it else None for it in items]
        if not rows or not _TOTAL_ROW.match(re.sub(r"\s+", "", items[-1])):
            continue                                       # 표 마지막 줄이 합계(별도는 `소 계`)일 때만
        if acct in mapped:
            continue                                       # 그 계정 줄이 표 안에 따로 있다(세진 `단기차입금 소계`) — 합계를 또 쓰면 이중계산
        if acct == "단기차입금" and (any(mapped) or any("유동성" in c for r in rows for c in r)):
            continue                                       # 단기 표에 다른 계정 줄·유동성분(세진 2022Q1 내역 `유동성장기차입금`)이 섞이면 합계는 단기차입금이 아니다
        if acct != "단기차입금" and "유동성장기부채" not in mapped[:-1]:
            continue                                       # 장기차입금·사채 합계는 `유동성 대체` 를 뺀 뒤일 때만(아니면 유동성분이 섞인 총액)
        for i, tg in tags:
            v = to_million(rows[-1][i], mul or 1e-6) if i < len(rows[-1]) else None
            if v is not None:
                out["acc"].setdefault(tg, {}).setdefault(acct, abs(v))
                out["found"] = True
        if mul is None:
            out["unit_assumed"] = True
    return out


def parse_note_parent(html):
    """부모 주석 절 → {'mode': heading|caption, 'blocks': n, 'picked': {key: [블록 제목]}, 'notes': {key: parse_note_section 결과}}.
    키마다 가장 좋은 순위의 블록 중 행 검사(fin: 이자수익|이자비용 줄, borrowings: 단기차입금|장기차입금|사채|유동성 줄)를 통과한
    것만(≤NOTE_MAX_PER) 고르고, 그 블록 HTML 에 parse_note_section 을 그대로 적용해 merge_note_parts 로 합친다.
    차입금은 _borrowings_caption_totals 로 빈 계정만 보충한다(줄 단위 결과가 이긴다). 못 고른 키는 notes 에 없다."""
    blocks = split_note_blocks(html)
    res = {"mode": "heading" if blocks and blocks[0]["no"] else "caption", "blocks": len(blocks), "picked": {}, "notes": {}}
    for key in NOTE_KEYS:
        cands = sorted(((r, i) for i, b in enumerate(blocks) for r in [_parent_rank(key, b["title"])] if r is not None))
        chosen, best = [], None
        for r, i in cands:
            if best is not None and r != best:
                break
            b = blocks[i]
            rx = _PARENT_ROW_OK.get(key)
            if rx:
                labs = _block_labels(b["html"])
                if r == 2 and key == "fin":
                    ok = any(_PARENT_FIN_STRICT.match(l) for l in labs) and _instruments_block_ok(b["html"])
                elif r == 2:
                    ok = any(re.search(r"단기차입금|장기차입금", l) for l in labs)    # `유동성` 만으로는 안 된다(유동성 리스부채)
                else:
                    ok = any(rx.search(l) for l in labs)
                if not ok:
                    continue
            best = r
            chosen.append(b)
            if len(chosen) >= NOTE_MAX_PER[key]:
                break
        if not chosen:
            continue
        parts = [parse_note_section(b["html"], key) for b in chosen]
        if key == "borrowings":
            parts += [_borrowings_caption_totals(b["html"]) for b in chosen]
        res["picked"][key] = [("%s. %s" % (b["no"], b["title"])) if b["no"] else b["title"] for b in chosen]
        res["notes"][key] = merge_note_parts(parts)
    return res


def _mark_parent_src(src):
    """부모 절에서 온 출처는 `note:` 대신 `note_parent:` 로 적는다(note_parent:fin(3m)·note_parent:borrowings …)."""
    for k, v in list((src or {}).items()):
        if isinstance(v, str) and v.startswith("note:"):
            src[k] = "note_parent:" + v[len("note:"):]


# ── 모집단·이름 ─────────────────────────────────────────────────────────────
_TITLE = re.compile(r"<title>([^<]*)</title>", re.I)


def company_names():
    """종목코드 → 이름. universe.json(41) + 회사 폴더 index.html <title>(56, 승격 16 포함) + 지주 009540."""
    names = {}
    try:
        for r in load_asset("universe.json")["rows"]:
            names[r["stock"]] = r["name"]
    except (OSError, KeyError, ValueError):
        pass
    for d in sorted(glob.glob(os.path.join(KSHIP, "[0-9]" * 6))):
        st = os.path.basename(d)
        if st in names:
            continue
        p = os.path.join(d, "index.html")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            head = f.read(4000)
        m = _TITLE.search(head)
        if not m:
            continue
        t = re.sub(r"\s+—.*$", "", m.group(1)).strip()
        t = re.sub(r"\s+조선\s*수주$", "", t).strip()
        if t:
            names[st] = t
    names.setdefault("009540", "HD한국조선해양")
    g = load_golden()
    for st, comp in (g or {}).get("companies", {}).items():
        names.setdefault(st, comp.get("name") or st)
    return names


def all_stocks():
    return sorted(company_names())


# ── 수집 ────────────────────────────────────────────────────────────────────
_REPORT_TITLE = re.compile(r"(사업|반기|분기)보고서\s*\((\d{4})\.(\d{2})\)")
SEC_RX = {
    "cons": re.compile(r"^\s*(?:[IVX]+\.\s*)?\d+\.\s*연결\s*재무제표\s*$"),
    "sep": re.compile(r"^\s*(?:[IVX]+\.\s*)?\d+\.\s*재무제표\s*$"),
    "shares": re.compile(r"주식의\s*총수"),
    "div": re.compile(r"배당에\s*관한\s*사항"),
}


def _log(line):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), line))


def _title_ok(title, quarter):
    y, qn = int(quarter[:4]), int(quarter[5])
    m = _REPORT_TITLE.search(title or "")
    return bool(m) and (m.group(2), m.group(3)) == (str(y), "%02d" % (qn * 3))


def find_fin_sections(nodes):
    """목차 노드 → {'cons': node, 'sep': node, 'shares': node, 'div': node}. 제목으로만 판정."""
    out = {}
    for key, rx in SEC_RX.items():
        for n in nodes:
            t = unicodedata.normalize("NFKC", n.get("text", ""))
            if rx.search(t) and "주석" not in t:
                out[key] = n
                break
    return out


def cache_paths(stock, quarter):
    d = os.path.join(FIN_CACHE, stock)
    return {"meta": os.path.join(d, quarter + "_meta.json"),
            "cons": os.path.join(d, quarter + "_cons.html"),
            "sep": os.path.join(d, quarter + "_sep.html"),
            "shares": os.path.join(d, quarter + "_shares.html"),
            "div": os.path.join(d, quarter + "_div.html")}


def _read_meta(stock, quarter):
    p = cache_paths(stock, quarter)["meta"]
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _cache_complete(stock, quarter):
    meta = _read_meta(stock, quarter)
    if not meta:
        return False
    if meta.get("rcp") is None:
        return True                                   # '보고서 없음' 도 확정 결과다(--force 로만 다시)
    paths = cache_paths(stock, quarter)
    return all(os.path.exists(paths[k]) for k in meta.get("sections", {}))


def collect_quarter(stock, name, quarter, reports_by_kind, force=False):
    """한 회사·한 분기: 후보 보고서(기준월 일치) 순회 → 목차 → 절 4종 캐시. 캐시가 완전하면 건너뛴다."""
    paths = cache_paths(stock, quarter)
    if not force and _cache_complete(stock, quarter):
        meta = _read_meta(stock, quarter)
        _log("%s %s %s rcp=%s skip(cached) %s" % (stock, name, quarter, meta.get("rcp"), ",".join(meta.get("sections", {}))))
        return meta
    kind = report_kind(quarter)
    cands = [(r, t) for r, t in pick_report(reports_by_kind.get(kind, []), quarter) if _title_ok(t, quarter)]
    os.makedirs(os.path.dirname(paths["meta"]), exist_ok=True)
    if not cands:
        meta = {"stock": stock, "quarter": quarter, "rcp": None, "title": None, "kind": kind,
                "sections": {}, "note": "no_report", "collected_at": today()}
        atomic_write(paths["meta"], json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
        _log("%s %s %s rcp=None no_report" % (stock, name, quarter))
        return meta
    tried = []
    for rcp, title in cands[:3]:
        nodes = toc(rcp)
        found = find_fin_sections(nodes)
        if "cons" in found or "sep" in found:
            break
        tried.append((rcp, "재무제표 절 없음"))
        found = None
    if not found:
        meta = {"stock": stock, "quarter": quarter, "rcp": cands[0][0], "title": cands[0][1], "kind": kind,
                "sections": {}, "note": "no_fin_section %s" % tried, "collected_at": today()}
        atomic_write(paths["meta"], json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
        _log("%s %s %s rcp=%s no_fin_section" % (stock, name, quarter, cands[0][0]))
        return meta
    want = ["cons", "sep", "shares"] + (["div"] if kind == "A001" else [])
    sections = {}
    for key in want:
        n = found.get(key)
        if not n:
            continue
        if os.path.exists(paths[key]) and not force:
            sections[key] = {"text": n.get("text"), "path": os.path.relpath(paths[key], ASSETS)}
            continue
        html = fetch_section(n)
        atomic_write(paths[key], html)
        sections[key] = {"text": n.get("text"), "path": os.path.relpath(paths[key], ASSETS), "bytes": len(html)}
    meta = {"stock": stock, "quarter": quarter, "rcp": rcp, "title": title, "kind": kind,
            "sections": sections, "note": "", "collected_at": today()}
    atomic_write(paths["meta"], json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
    _log("%s %s %s rcp=%s ok %s" % (stock, name, quarter, rcp, ",".join(sections)))
    return meta


def collect_company(stock, name, quarters, force=False):
    """회사 하나: search_reports 3회(A001/A002/A003, 가장 이른 분기 다음 달~오늘) → 분기별 수집(보조 3Q 포함)."""
    end = datetime.date.today().strftime("%Y%m%d")
    quarters = sorted(set(quarters) | set(helper_quarters(quarters)))
    start = search_start_for(quarters)
    reports = {}
    for kind in ("A001", "A002", "A003"):
        try:
            reports[kind] = search_reports(stock, start, end, kind)
        except Exception as e:                          # 네트워크 — 이 회사만 건너뛰고 로그에 남긴다
            _log("%s %s search %s FAIL %s" % (stock, name, kind, e))
            reports[kind] = []
    _log("%s %s search A001=%d A002=%d A003=%d" % (stock, name, len(reports["A001"]), len(reports["A002"]), len(reports["A003"])))
    out = []
    for q in quarters:
        try:
            out.append(collect_quarter(stock, name, q, reports, force))
        except Exception as e:
            _log("%s %s %s FAIL %s: %s" % (stock, name, q, type(e).__name__, e))
            out.append({"stock": stock, "quarter": q, "rcp": None, "error": str(e)})
    return out


# ── 주석 수집(MODEL_SPEC §5-1 — 선택이던 것을 착수) ─────────────────────────────
# DART 목차는 주석을 `3. 연결재무제표 주석` 부모 아래 `18. 금융수익과 금융원가 (연결)`·`12. 차입금 및 사채 (연결)`·
# `17. 기타수익과 비용 (연결)` 처럼 **주석 번호별 하위 노드**로 나눈다(삼성重·세진·한라IMS 2026Q2 실측). 부모 절 전체(1.6MB)는
# 받지 않고 이 하위 노드만 골라 받는다 — 회사·분기당 목차 1 + 표 ≤4 요청. 하위 노드가 없는 회사(주석이 한 덩어리)나
# 해당 주석이 없는 회사(한라IMS 는 금융수익 주석이 없다)는 그 키를 비우고 build 가 issues 로 남긴다.
NOTE_KEYS = ("fin", "borrowings", "other")
NOTE_RX = {
    "fin": re.compile(r"금융수익|금융원가|금융비용|금융손익"),
    "borrowings": re.compile(r"차입금|차입부채|사채"),
    "other": re.compile(r"기타수익|기타비용|기타영업외"),
}
NOTE_MAX_PER = {"fin": 2, "borrowings": 1, "other": 1}      # 금융수익·금융원가를 두 주석으로 가르는 회사가 있어 fin 만 2
NOTE_MAX_REQ = 4
_NOTES_PARENT = {"cons": re.compile(r"연결\s*재무제표\s*주석"),
                 "sep": re.compile(r"^(?!.*연결).*재무제표\s*주석")}


def find_note_parent(nodes, scope):
    """목차 → 주석 부모 노드(`n. 연결재무제표 주석` / `n. 재무제표 주석`) 또는 None."""
    for n in nodes:
        if _NOTES_PARENT[scope].search(unicodedata.normalize("NFKC", n.get("text", ""))):
            return n
    return None


def find_note_nodes(nodes, scope):
    """목차 → 주석 부모(`n. 연결재무제표 주석` / `n. 재무제표 주석`)의 하위 노드(offset 이 부모 범위 안) 중 NOTE_RX 에 맞는 것.
    반환 {"fin": [node, ...], "borrowings": [node], "other": [node]} — 부모가 없거나 하위 노드가 없으면 {}.
    차입금 후보가 여럿이면(전환사채 주석이 따로 있는 회사) '차입' 이 들어간 제목을 앞에 둔다."""
    parent = find_note_parent(nodes, scope)
    if not parent:
        return {}
    try:
        po, pl = int(parent.get("offset") or 0), int(parent.get("length") or 0)
    except ValueError:
        return {}
    cands = {k: [] for k in NOTE_KEYS}
    for n in nodes:
        if n is parent:
            continue
        try:
            o = int(n.get("offset") or -1)
        except ValueError:
            continue
        if not (po <= o < po + pl):
            continue
        t = unicodedata.normalize("NFKC", n.get("text", ""))
        for key in NOTE_KEYS:
            if NOTE_RX[key].search(t):
                cands[key].append(n)
                break
    cands["borrowings"].sort(key=lambda n: 0 if "차입" in unicodedata.normalize("NFKC", n.get("text", "")) else 1)
    out = {k: v[:NOTE_MAX_PER[k]] for k, v in cands.items() if v}
    return out


def note_cache_path(stock, quarter, key):
    return os.path.join(FIN_CACHE, stock, "%s_note_%s.html" % (quarter, key))


def note_parent_cache_path(stock, quarter, scope):
    return os.path.join(FIN_CACHE, stock, "%s_note_parent_%s.html" % (quarter, scope))


def _has_table(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return re.search(r"<table", f.read(), re.I) is not None
    except OSError:
        return False


def collect_note_parent(stock, quarter, meta, nodes=None, force=False):
    """하위 노드가 없던 분기의 부모 주석 절 1개 — 연결 절(표가 있는)이 있으면 연결 주석, 없으면 별도 주석.
    연결 주석 절이 표 하나 없는 빈 절(`<P>-</P>` — 연결 재무제표 절도 비어 있는 회사, 2026-10-02 캐시 786 중 161)이면 별도로 넘어간다.
    캐시 `fin_cache/<stock>/<q>_note_parent_{cons|sep}.html` 가 표를 담고 있으면 재사용(요청 0). 아니면 목차(nodes 를 안 받았을
    때만 1) + 부모 절 1요청(빈 연결 절을 새로 받았으면 별도 1요청 더). 반환 ({'scope', 'cached', 'note', …}, 요청 수)."""
    cons_path = cache_paths(stock, quarter)["cons"]
    scopes = ["cons", "sep"] if "cons" in meta.get("sections", {}) and _has_table(cons_path) else ["sep"]
    if not force:
        for sc in scopes:
            path = note_parent_cache_path(stock, quarter, sc)
            if _has_table(path):
                return {"scope": sc, "cached": os.path.relpath(path, ASSETS), "note": "", "collected_at": today()}, 0
    nreq, empty = 0, []
    for sc in scopes:
        path = note_parent_cache_path(stock, quarter, sc)
        if os.path.exists(path) and not force:
            empty.append(sc)                               # 받아 둔 빈 절 — 다시 받아도 같다
            continue
        if nodes is None:
            nodes = toc(meta["rcp"])
            nreq += 1
        n = find_note_parent(nodes, sc)
        if not n:
            continue
        html = fetch_section(n)
        nreq += 1
        atomic_write(path, html)
        if not re.search(r"<table", html, re.I):
            empty.append(sc)
            continue
        return {"scope": sc, "cached": os.path.relpath(path, ASSETS), "note": "", "text": n.get("text"),
                "bytes": len(html), "collected_at": today()}, nreq
    return {"scope": None, "cached": None, "note": "empty_parent:%s" % ",".join(empty) if empty else "no_parent_node",
            "collected_at": today()}, nreq


def collect_notes_quarter(stock, name, quarter, force=False, parent_fallback=False):
    """한 회사·한 분기 주석 표 수집 — meta 의 rcp 로 목차를 받아(1요청) 하위 노드 ≤NOTE_MAX_REQ 개를 캐시한다.
    `meta["notes"]` 가 있으면 체크포인트(건너뜀; 하위 노드가 없었다는 결과도 확정이다 — --force 로만 다시).
    연결 절이 있으면 연결 주석, 없거나 연결 주석에 하위 노드가 없으면 별도 주석. 캐시 `fin_cache/<stock>/<q>_note_<key>.html`.
    parent_fallback(--notes-parent-fallback): 하위 노드가 없으면(note == no_note_subnodes) 부모 주석 절 1개를 캐시하고
    `meta.notes.parent` 를 적는다 — 이미 no_note_subnodes 로 체크포인트된 분기도 parent 가 없으면 이것만 한다."""
    meta = _read_meta(stock, quarter)
    if not meta or not meta.get("rcp"):
        return None                                        # 정기보고서 자체가 없는 분기
    if meta.get("notes") is not None and not force:
        nt = meta["notes"]
        if parent_fallback and nt.get("note") == "no_note_subnodes" and nt.get("parent") is None:
            nt["parent"], preq = collect_note_parent(stock, quarter, meta)
            atomic_write(cache_paths(stock, quarter)["meta"], json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
            _log("%s %s %s rcp=%s notes parent %s req=%d %s" % (stock, name, quarter, meta["rcp"], nt["parent"]["scope"] or "-",
                                                               preq, nt["parent"]["cached"] or nt["parent"]["note"]))
            return nt
        _log("%s %s %s rcp=%s notes skip(cached) %s" % (stock, name, quarter, meta["rcp"],
                                                        ",".join(nt.get("items", {})) or nt.get("note")))
        return nt
    nodes = toc(meta["rcp"])
    scopes = ["cons", "sep"] if "cons" in meta.get("sections", {}) else ["sep"]
    found, scope = {}, None
    for sc in scopes:
        found = find_note_nodes(nodes, sc)
        if found:
            scope = sc
            break
    items, nreq = {}, 0
    for key in NOTE_KEYS:
        for i, n in enumerate(found.get(key, [])):
            if nreq >= NOTE_MAX_REQ:
                break
            k = key if i == 0 else "%s%d" % (key, i + 1)
            path = note_cache_path(stock, quarter, k)
            if os.path.exists(path) and not force:
                items[k] = {"text": n.get("text"), "path": os.path.relpath(path, ASSETS)}
                continue
            html = fetch_section(n)
            nreq += 1
            atomic_write(path, html)
            items[k] = {"text": n.get("text"), "path": os.path.relpath(path, ASSETS), "bytes": len(html)}
    meta["notes"] = {"scope": scope, "items": items, "note": "" if found else "no_note_subnodes",
                     "collected_at": today()}
    if parent_fallback and not found:
        meta["notes"]["parent"], preq = collect_note_parent(stock, quarter, meta, nodes, force)
        nreq += preq
    atomic_write(cache_paths(stock, quarter)["meta"], json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
    _log("%s %s %s rcp=%s notes %s req=%d %s" % (stock, name, quarter, meta["rcp"], scope or "-", nreq,
                                                 ",".join(items) or meta["notes"]["note"] +
                                                 (" parent=%s" % (meta["notes"]["parent"]["cached"] or meta["notes"]["parent"]["note"])
                                                  if "parent" in meta["notes"] else "")))
    return meta["notes"]


def collect_notes_company(stock, name, quarters, force=False, parent_fallback=False):
    """회사 하나의 주석 수집 — 분기별 collect_notes_quarter(보조 분기는 필요 없다). 실패는 그 분기만 로그로 남기고 계속."""
    out = []
    for q in quarters:
        try:
            out.append(collect_notes_quarter(stock, name, q, force, parent_fallback))
        except Exception as e:                          # 네트워크 — 이 분기만 건너뛴다
            _log("%s %s %s notes FAIL %s: %s" % (stock, name, q, type(e).__name__, e))
            out.append({"error": str(e)})
    return out


class _SingleProcess:
    """수집기는 한 번에 하나 — 락을 못 잡으면 바로 물러난다(DART IP 차단 예방)."""

    def __init__(self):
        self.fd = None

    def __enter__(self):
        if fcntl is None:
            return self
        os.makedirs(FIN_CACHE, exist_ok=True)
        self.fd = os.open(os.path.join(FIN_CACHE, ".collect.lock"), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self.fd)
            self.fd = None
            raise SystemExit("다른 kship_fin --collect 프로세스가 돌고 있다 — 하나만 띄운다")
        os.write(self.fd, str(os.getpid()).encode())
        return self

    def __exit__(self, *a):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)


# ── 빌드(캐시 → fin json) ─────────────────────────────────────────────────
def _q_prev(q):
    y, n = int(q[:4]), int(q[5])
    return "%dQ%d" % (y - (n == 1), (n - 2) % 4 + 1)


def _diff_map(a, b):
    """두 계정 dict 차분(누적→3개월). 한쪽에만 있는 계정은 뺀다 — 절대값 계정도 누적이라 차분이 맞다."""
    out = {}
    for k, v in a.items():
        if v is None:
            continue
        if k in b and b[k] is not None:
            out[k] = round(v - b[k], 2)
    return out


def _scope_quarterize(scope, per_q, quarters):
    """per_q[q] = parse_fin_section 결과. → bs/is/is_ytd/cf/cf_ytd/derivation/checks/issues.

    · 손익 3개월: 3개월 열 → 없으면 (Q1) 누적 → (Q2·Q3) 누적 − 직전 분기 누적 → (Q4) 연간 − 3Q 누적
    · 3Q 누적이 없으면 다음 해 3Q 보고서의 **전기 누적** 열로 대신한다(2021Q4 가 이 길로 온다)
    · 현금흐름은 항상 누적 → 차분
    · `is_ytd_diff`(FnGuide 방식 누적차분 — Q1 = 누적, Qn = 누적 − 직전 누적, Q4 = 연간 − 3Q 누적)는 3개월 열이 있어도
      **항상 병기**한다. 둘이 1백만원 초과로 다른 계정은 `restated[q][계정] = {is, ytd_diff, diff}` — 후속 보고서가 전기를
      재작성한 흔적이다(MODEL_SPEC §5-1 결정 ⓐ: 모델은 `is`, 레퍼런스 xlsx 패치는 `is_ytd_diff`).
    """
    bs, is3, isy, isyd, cf3, cfy = {}, {}, {}, {}, {}, {}
    deriv, checks, issues, restated = {}, [], [], {}
    ytd_is, ytd_cf = {}, {}                   # (q) → 누적 dict — 당기 열
    ytd_is_prev, ytd_cf_prev = {}, {}         # (q) → 누적 dict — 다음 해 보고서의 전기 열
    for q in quarters:
        p = per_q.get(q)
        if not p:
            continue
        y = int(q[:4])
        isd, cfd = p.get("is") or {}, p.get("cf") or {}
        if p.get("bs", {}).get("cur"):
            bs[q] = p["bs"]["cur"]
        cur_y = isd.get("cur_ytd") or isd.get("cur_full")
        if cur_y:
            ytd_is[q] = cur_y
        pv = isd.get("prev_ytd") or isd.get("prev_full")
        if pv:
            ytd_is_prev["%dQ%s" % (y - 1, q[5])] = pv
        cy = cfd.get("cur_ytd") or cfd.get("cur_full") or cfd.get("cur_q")
        if cy:
            ytd_cf[q] = cy
        pc = cfd.get("prev_ytd") or cfd.get("prev_full") or cfd.get("prev_q")
        if pc:
            ytd_cf_prev["%dQ%s" % (y - 1, q[5])] = pc
    for q in quarters:
        p = per_q.get(q)
        if not p:
            continue
        n = int(q[5])
        isd, cfd = p.get("is") or {}, p.get("cf") or {}
        d = {}
        # ── 손익 ──
        if q in ytd_is:
            isy[q] = ytd_is[q]
        # FnGuide 방식 누적차분 — 3개월 열이 있든 없든 한 번 만든다(is_ytd_diff). 3개월 열이 없으면 이것이 곧 `is`.
        ydiff, how = None, None
        if q in ytd_is:
            pq = _q_prev(q)
            if n == 1:
                ydiff, how = dict(ytd_is[q]), "ytd_as_3m(Q1)"
            else:
                if n == 4:
                    base = ytd_is.get(pq)
                    how = "annual_minus_9M"
                    if not base:
                        base = ytd_is_prev.get(pq)
                        how = "annual_minus_9M(prior_year_col_of_%dQ3)" % (int(q[:4]) + 1)
                else:
                    base = ytd_is.get(pq) or ytd_is_prev.get(pq)
                    how = "ytd_minus_prev_ytd"
                if base:
                    dif = _diff_map(ytd_is[q], base)
                    if ytd_is[q].get("중단사업이익") is not None and base.get("중단사업이익") is None:
                        # 중단영업이 연간(사업보고서)에서 처음 분류된 경우(한화시스템·인화정공·영흥·HD현대마린엔진·금강공업 실측) —
                        # 9M 에 그 줄이 없으면 0 이지 '모름' 이 아니다. 빼먹으면 Q4 순이익 ≠ 계속 + 중단 이 된다.
                        dif["중단사업이익"] = ytd_is[q]["중단사업이익"]
                        how += "+disc_ops_annual_only"
                    ydiff = synth_is(dif)
            if ydiff is not None:
                isyd[q] = ydiff
        if isd.get("cur_q"):
            is3[q] = isd["cur_q"]
            d["is"] = "3m_column"
            if ydiff is not None and n > 1:
                for k in ("매출액(수익)", "영업이익", "당기순이익"):
                    if k in ydiff and k in is3[q]:
                        checks.append({"quarter": q, "scope": scope, "rule": "ytd_diff==3m:%s" % k,
                                       "ok": abs(ydiff[k] - is3[q][k]) <= 1.0, "diff": round(ydiff[k] - is3[q][k], 2)})
                # 전 계정 대조 — 1백만원 초과 차이는 후속 보고서의 전기 재작성(재분류·정정)이다. 어느 쪽도 버리지 않는다.
                rs = {}
                for k, v in ydiff.items():
                    ov = is3[q].get(k)
                    if v is None or ov is None:
                        continue
                    if abs(v - ov) > 1.0:
                        rs[k] = {"is": ov, "ytd_diff": v, "diff": round(v - ov, 2)}
                if rs:
                    restated[q] = rs
        elif ydiff is not None:
            is3[q] = dict(ydiff)
            d["is"] = how
        elif q in ytd_is:
            issues.append({"quarter": q, "scope": scope, "code": "no_prior_ytd",
                           "detail": "3개월 손익 도출용 직전 누적(%s) 없음" % _q_prev(q)})
        # ── 현금흐름 ──
        if q in ytd_cf:
            cfy[q] = ytd_cf[q]
            if n == 1:
                cf3[q] = dict(ytd_cf[q])
                d["cf"] = "ytd_as_3m(Q1)"
            else:
                pq = _q_prev(q)
                base = ytd_cf.get(pq)
                how = "annual_minus_9M" if n == 4 else "ytd_minus_prev_ytd"
                if not base:
                    base = ytd_cf_prev.get(pq)
                    how += "(prior_year_col)" if base else ""
                if base:
                    cf3[q] = _diff_map(ytd_cf[q], base)
                    for k in sorted(CF_ABS_KEYS & set(cf3[q])):
                        if cf3[q][k] < -1.0:
                            checks.append({"quarter": q, "scope": scope, "rule": "cf_abs_nonneg:%s" % k, "ok": False, "diff": cf3[q][k]})
                            del cf3[q][k]
                    if "CAPEX" not in cf3[q]:
                        cap = _sum(cf3[q].get("유형자산의증가"), cf3[q].get("무형자산의증가"))
                        if cap is not None:
                            cf3[q]["CAPEX"] = cap
                    d["cf"] = how
                else:
                    issues.append({"quarter": q, "scope": scope, "code": "no_prior_ytd_cf",
                                   "detail": "3개월 현금흐름 도출용 직전 누적(%s) 없음" % pq})
        if d:
            deriv[q] = d
        # ── 항등식 ──
        i3 = is3.get(q)
        if i3 and i3.get("법인세비용차감전계속사업이익") is not None and i3.get("법인세비용") is not None:
            ni = i3.get("계속사업이익") if "중단사업이익" in i3 else i3.get("당기순이익")
            if ni is not None:
                dd = round(i3["법인세비용차감전계속사업이익"] - i3["법인세비용"] - ni, 2)
                checks.append({"quarter": q, "scope": scope, "rule": "pretax-tax=ni", "ok": abs(dd) <= 1.0, "diff": dd})
        b = bs.get(q)
        if b and b.get("자산총계") is not None and b.get("부채총계") is not None and b.get("자본총계") is not None:
            diff = round(b["자산총계"] - b["부채총계"] - b["자본총계"], 2)
            checks.append({"quarter": q, "scope": scope, "rule": "assets=liab+equity", "ok": abs(diff) <= 1.0, "diff": diff})
        if p.get("unit_assumed"):
            issues.append({"quarter": q, "scope": scope, "code": "unit_assumed", "detail": "단위 캡션 없음 — 원 가정"})
    return {"bs": bs, "is": is3, "is_ytd": isy, "is_ytd_diff": isyd, "restated": restated, "cf": cf3, "cf_ytd": cfy,
            "derivation": deriv, "checks": checks, "issues": issues}


def build_company(stock, quarters=None, name=None, golden=None):
    """캐시(fin_cache/<stock>) → assets/fin/<stock>.json (MODEL_SPEC 2-1)."""
    names = company_names()
    name = name or names.get(stock, stock)
    quarters = quarters or q_range(DEFAULT_Q0, DEFAULT_Q1)
    helpers = helper_quarters(quarters)
    reports, per = {}, {"cons": {}, "sep": {}}
    shares, dividend, issues, raw = {}, {}, [], {"cons": {}, "sep": {}}
    eps = {"cons": {}, "sep": {}}
    notes_raw, src_notes = {"cons": {}, "sep": {}}, {"cons": {}, "sep": {}}      # 주석(§5-1): q → {key: parse_note_section 결과}
    parent_qs = {"cons": set(), "sep": set()}                                      # 부모 절 폴백으로 주석을 읽은 분기
    for q in sorted(set(quarters) | set(helpers)):
        is_helper = q not in quarters
        meta = _read_meta(stock, q)
        if not meta:
            if not is_helper:
                issues.append({"quarter": q, "code": "not_collected", "detail": "캐시 없음"})
            continue
        if not meta.get("rcp"):
            if not is_helper:
                issues.append({"quarter": q, "code": "no_report", "detail": meta.get("note") or "정기보고서 없음"})
            continue
        paths = cache_paths(stock, q)
        rep = {"rcp": meta["rcp"], "title": meta.get("title"), "kind": meta.get("kind"),
               "has_cons": False, "has_sep": False, "sections": {}}
        for key in ("cons", "sep", "shares", "div"):
            if key in meta.get("sections", {}) and os.path.exists(paths[key]):
                rep["sections"][key] = os.path.relpath(paths[key], ASSETS)
        for scope in ("cons", "sep"):
            if scope not in rep["sections"]:
                continue
            with open(paths[scope], encoding="utf-8", errors="replace") as f:
                html = f.read()
            p = parse_fin_section(html)
            if not p["has_bs"]:
                issues.append({"quarter": q, "scope": scope, "code": "no_%s_statements" % scope,
                               "detail": "절은 있으나 재무상태표 표 없음(연결 해당없음 등)"})
                continue
            rep["has_" + scope] = True
            per[scope][q] = p
            if is_helper:
                continue                                  # 보조 분기는 도출에만 쓴다 — 산출물에는 넣지 않는다
            raw[scope][q] = p["raw_labels"]
            if p.get("eps"):
                eps[scope][q] = p["eps"]
            for d in p.get("dups", []):
                issues.append({"quarter": q, "scope": scope, "code": "duplicate_label",
                               "detail": "같은 구역에 같은 라벨 반복 — 마지막 값 채택: %s" % d})
            for fl in p.get("flags", []):
                issues.append({"quarter": q, "scope": scope, "code": fl[0], "detail": fl[1]})
        if is_helper:
            continue
        nt = meta.get("notes")
        pt = (nt or {}).get("parent") or {}
        ppath = os.path.join(ASSETS, pt["cached"]) if pt.get("cached") else None
        if nt is not None and not nt.get("items") and ppath and os.path.exists(ppath):
            nsc = pt.get("scope")                             # 부모 절 폴백 — 블록을 골라 같은 파서·같은 주입 규칙으로
            if nsc not in per or q not in per[nsc]:
                issues.append({"quarter": q, "scope": nsc, "code": "notes_scope_missing", "detail": "주석(부모 절)은 %s 인데 그 재무제표가 없음" % nsc})
            else:
                with open(ppath, encoding="utf-8", errors="replace") as f:
                    pr = parse_note_parent(f.read())
                merged = pr["notes"]
                for key in NOTE_KEYS:
                    if key not in merged:
                        issues.append({"quarter": q, "scope": nsc, "code": "note_parent_missing:%s" % key,
                                       "detail": "부모 주석 절(%s 블록 %d개)에서 %s 블록을 못 찾음" % (pr["mode"], pr["blocks"], key)})
                    elif not merged[key]["acc"]:
                        issues.append({"quarter": q, "scope": nsc, "code": "note_unmapped:%s" % key,
                                       "detail": "부모 절 블록 %s 은 골랐으나 매핑된 계정 없음 — raw %d줄" % (" / ".join(pr["picked"][key]), len(merged[key]["raw"]))})
                notes_raw[nsc][q] = merged
                parent_qs[nsc].add(q)
                src = src_notes[nsc].setdefault(q, {})
                if merged.get("fin"):
                    inject_note_is(per[nsc][q], merged["fin"], src)
                if merged.get("borrowings"):
                    inject_note_bs(per[nsc][q].get("bs", {}).get("cur"), merged["borrowings"], src, issues, q, nsc)
                _mark_parent_src(src)
                rep["notes"] = {"scope": nsc, "items": {}, "parent": {"path": pt["cached"], "mode": pr["mode"],
                                                                      "blocks": pr["blocks"], "picked": pr["picked"]}}
        elif nt is not None:                                  # 주석 수집이 끝난 분기만 — 안 받은 분기는 조용히(issues 소음 방지)
            nsc = nt.get("scope")
            if not nt.get("items"):
                issues.append({"quarter": q, "code": "notes_no_subnodes", "detail": "목차에 주석 하위 노드 없음(주석이 한 덩어리) — 금융수익 세부·차입금 분해 없음"})
            elif nsc not in per or q not in per[nsc]:
                issues.append({"quarter": q, "scope": nsc, "code": "notes_scope_missing", "detail": "주석은 %s 인데 그 재무제표가 없음" % nsc})
            else:
                parsed = {}
                for key, item in nt["items"].items():
                    path = os.path.join(ASSETS, item.get("path") or "")
                    if not item.get("path") or not os.path.exists(path):
                        continue
                    with open(path, encoding="utf-8", errors="replace") as f:
                        parsed.setdefault(key.rstrip("0123456789"), []).append(parse_note_section(f.read(), key.rstrip("0123456789")))
                merged = {key: merge_note_parts(v) for key, v in parsed.items()}
                for key in NOTE_KEYS:
                    if key not in merged:
                        issues.append({"quarter": q, "scope": nsc, "code": "note_missing:%s" % key,
                                       "detail": "목차에 해당 주석 없음 — %s" % {"fin": "이자수익·외환차익 등 세부 null", "borrowings": "차입금 분해 없음", "other": "기타수익 세부 없음"}[key]})
                    elif not merged[key]["acc"]:
                        issues.append({"quarter": q, "scope": nsc, "code": "note_unmapped:%s" % key,
                                       "detail": "주석 표는 받았으나 매핑된 계정 없음 — raw %d줄" % len(merged[key]["raw"])})
                notes_raw[nsc][q] = merged
                src = src_notes[nsc].setdefault(q, {})
                if merged.get("fin"):
                    inject_note_is(per[nsc][q], merged["fin"], src)
                if merged.get("borrowings"):
                    inject_note_bs(per[nsc][q].get("bs", {}).get("cur"), merged["borrowings"], src, issues, q, nsc)
                rep["notes"] = {"scope": nsc, "items": {k: v.get("path") for k, v in nt["items"].items()}}
        if "shares" in rep["sections"]:
            with open(paths["shares"], encoding="utf-8", errors="replace") as f:
                sh_html = f.read()
            sh = parse_shares(sh_html)
            if sh:
                shares[q] = sh
            else:
                omitted = shares_omitted(sh_html)
                prev = [k for k in shares if k < q]
                if omitted and prev:
                    base = shares[max(prev)]
                    shares[q] = dict(base, carried_from=max(prev), kind="estimate",
                                     basis="분기보고서 주식의 총수 기재 생략 — 직전 보고서 값 이월")
                issues.append({"quarter": q, "code": "shares_omitted_quarterly" if omitted else "shares_table_not_found",
                               "detail": "분기보고서 기재 생략(직전 값 이월)" if omitted else "주식의 총수 표 인식 실패"})
        if "div" in rep["sections"]:
            with open(paths["div"], encoding="utf-8", errors="replace") as f:
                dv = parse_dividend(f.read())
            if dv:
                dividend[q] = dv
            else:
                issues.append({"quarter": q, "code": "dividend_table_not_found", "detail": "배당 표 인식 실패"})
        reports[q] = rep
    out = {"stock": stock, "name": name, "unit": "KRW_million", "collected_at": today(),
           "quarters": [q for q in quarters if q in reports], "reports": reports}
    checks, deriv = [], {}
    qs = set(quarters)
    for scope in ("cons", "sep"):
        r = _scope_quarterize(scope, per[scope], sorted(set(quarters) | set(helpers)))
        keep = lambda d: {q: v for q, v in d.items() if q in qs}          # noqa: E731 — 보조 분기 제거
        for q, b in keep(r["bs"]).items():
            synth_bs(b, issues, q, scope)                                    # face 차입금 라벨 등 합성 issue
        out[scope] = {"bs": keep(r["bs"]), "is": keep(r["is"]), "is_ytd": keep(r["is_ytd"]),
                      "is_ytd_diff": keep(r["is_ytd_diff"]), "restated": keep(r["restated"]),
                      "cf": keep(r["cf"]), "cf_ytd": keep(r["cf_ytd"]),
                      "eps_reported": eps[scope], "raw_labels": raw[scope]}
        finalize_notes(out[scope], notes_raw[scope], src_notes[scope], scope)
        for q in parent_qs[scope]:
            _mark_parent_src(out[scope]["src_notes"].get(q))                 # finalize 가 적은 note:fin(ytd_diff) 도
        checks.extend(c for c in r["checks"] if c["quarter"] in qs)
        issues.extend(i for i in r["issues"] if i["quarter"] in qs)
        for q, d in keep(r["derivation"]).items():
            deriv.setdefault(q, {})[scope] = d
    out["shares"] = shares
    out["dividend"] = {q: {"dps_common": d["dps_common"], "payout_pct": d["payout_pct"],
                           "cash_div_total_m": d["cash_div_total_m"], "dps_row_kind": d.get("dps_row_kind")}
                       for q, d in dividend.items()}
    out["derivation"] = deriv
    out["checks"] = checks
    out["synth_basis"] = SYNTH_BASIS
    out["issues"] = issues
    g = golden if golden is not None else load_golden()
    if g:
        cmp_ = compare_golden(out, g)
        if cmp_:
            out["golden"] = cmp_
    return out


def write_fin(fin):
    os.makedirs(FIN_DIR, exist_ok=True)
    atomic_write(os.path.join(FIN_DIR, fin["stock"] + ".json"), json.dumps(fin, ensure_ascii=False, indent=1) + "\n")


# ── 골든 대조 ────────────────────────────────────────────────────────────────
def load_golden(path=GOLDEN_PATH):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def golden_sheets_for(stock, golden, names=None):
    """이 종목에 해당하는 골든 시트 목록 [(scope, values_by_period)].
    'BS연결'→cons, 'BS별도'→sep, 'BS<이름>(별도)'→그 이름 회사(세진 종속사 일승·동방선기)의 sep."""
    names = names or company_names()
    out = []
    for gst, comp in golden.get("companies", {}).items():
        for sheet, d in comp.get("sheets", {}).items():
            if sheet == "BS연결" and gst == stock:
                out.append(("cons", d))
            elif sheet == "BS별도" and gst == stock:
                out.append(("sep", d))
            else:
                m = re.match(r"^BS(.+?)\((별도|연결)\)$", sheet)
                if m and names.get(stock) == m.group(1):
                    out.append(("sep" if m.group(2) == "별도" else "cons", d))
    return out


def _period_to_q(p):
    m = re.match(r"^(\d{4})\.(\d{2})(A?)$", p)
    if not m:
        return None, False
    return "%sQ%d" % (m.group(1), int(m.group(2)) // 3), bool(m.group(3))


def compare_golden(fin, golden, tol=GOLDEN_TOL):
    """fin json vs golden_fnguide.json — 겹치는 모든 기간. 반환 {period_key: {compared, match, mismatch[], missing[]}}.
    FnGuide 가 0.0 으로 채운 계정은 우리가 없으면 비교하지 않는다(부재를 0 으로 적는 관행)."""
    sheets = golden_sheets_for(fin["stock"], golden)
    if not sheets:
        return None
    out = {}
    for scope, d in sheets:
        sc = fin.get(scope) or {}
        for period, vals in d.get("values", {}).items():
            q, annual = _period_to_q(period)
            if not q or q not in fin.get("quarters", []):
                continue
            ours = {}
            ours.update(sc.get("bs", {}).get(q, {}))
            if annual:
                ours.update({k: v for k, v in sc.get("is_ytd", {}).get(q, {}).items()})
                ours.update({k: v for k, v in sc.get("cf_ytd", {}).get(q, {}).items()})
            else:
                ours.update(sc.get("is", {}).get(q, {}))
                ours.update(sc.get("cf", {}).get(q, {}))
            sh = fin.get("shares", {}).get(q)
            raw_shares = {}                                   # 주 단위 원값 — 종속사 시트(BS일승 등)는 백만주가 아니라 주로 적혀 있다
            if sh:
                for acct, key in (("기말발행주식수(백만주)", "issued"), ("보통주기말발행주식수", "common_issued"),
                                  ("보통주기말자기주식수", "common_treasury"), ("우선주기말발행주식수", "pref_issued")):
                    if sh.get(key) is not None:
                        ours[acct] = round(sh[key] / 1e6, 3)
                        raw_shares[acct] = sh[key]
            dv = fin.get("dividend", {}).get(q)
            if dv and dv.get("dps_common") is not None and q.endswith("Q4"):
                ours["수정DPS(보통주, 기말현금)"] = dv["dps_common"]
            compared, match, mism, missing = 0, 0, [], []
            for acct, gv in vals.items():
                if gv is None:
                    continue
                ov = ours.get(acct)
                if ov is None:
                    if gv != 0:
                        missing.append(acct)
                    continue
                compared += 1
                t = tol
                if "주식수" in acct:
                    t = 0.001
                    if abs(gv) > 1e5 and acct in raw_shares:   # 종속사 시트(BS일승 등)는 백만주가 아니라 주 단위
                        ov, t = raw_shares[acct], 1.0
                if abs(ov - gv) <= t:
                    match += 1
                else:
                    mism.append({"acct": acct, "ours": ov, "fnguide": gv, "diff": round(ov - gv, 2)})
            key = "%s:%s" % (scope, period)
            out[key] = {"quarter": q, "compared": compared, "match": match,
                        "match_pct": round(100.0 * match / compared, 1) if compared else None,
                        "mismatch": sorted(mism, key=lambda x: -abs(x["diff"])), "missing": sorted(missing)}
    return out or None


def print_golden(fin):
    g = fin.get("golden")
    if not g:
        print("%s %s: 골든 시트 없음" % (fin["stock"], fin["name"]))
        return
    print("== %s %s — 골든 대조(±%.0f 백만원)" % (fin["stock"], fin["name"], GOLDEN_TOL))
    print("%-16s %8s %6s %6s  %s" % ("기간", "compared", "match", "pct", "대표 불일치(ours / fnguide)"))
    for key in sorted(g):
        r = g[key]
        top = "; ".join("%s %s/%s" % (m["acct"], m["ours"], m["fnguide"]) for m in r["mismatch"][:3])
        print("%-16s %8d %6d %5s%%  %s" % (key, r["compared"], r["match"], r["match_pct"], top))


# ── CLI ─────────────────────────────────────────────────────────────────────
def _parse_quarters(spec):
    if not spec:
        return q_range(DEFAULT_Q0, DEFAULT_Q1)
    if ".." in spec:
        a, b = spec.split("..", 1)
        return q_range(a.strip(), b.strip())
    return [s.strip() for s in spec.split(",") if s.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--collect", action="store_true", help="DART 에서 절 HTML 캐시(체크포인트, 단일 프로세스)")
    ap.add_argument("--collect-notes", action="store_true",
                    help="주석 하위 노드(금융수익·차입금·기타수익) 캐시 — 회사·분기당 목차 1 + 표 ≤4 요청, 체크포인트, 단일 프로세스")
    ap.add_argument("--notes-parent-fallback", action="store_true",
                    help="--collect-notes 에서 하위 노드가 없는 분기(no_note_subnodes)는 부모 주석 절 1개를 캐시(이미 있으면 재사용)")
    ap.add_argument("--build", action="store_true", help="캐시 → assets/fin/<stock>.json")
    ap.add_argument("--golden", action="store_true", help="fin json 을 golden_fnguide.json 과 대조하고 표로 출력")
    ap.add_argument("--stocks", help="쉼표 구분 종목코드(기본: 레퍼런스 3사 + 세진 종속 2사)")
    ap.add_argument("--all", action="store_true", help="모집단 전체(universe + 회사 폴더 + 009540)")
    ap.add_argument("--quarters", help="예 2021Q4..2026Q2 또는 2025Q4,2026Q1")
    ap.add_argument("--force", action="store_true", help="캐시가 있어도 다시 받는다")
    a = ap.parse_args(argv)
    quarters = _parse_quarters(a.quarters)
    names = company_names()
    if a.all:
        stocks = all_stocks()
    elif a.stocks:
        stocks = [s.strip() for s in a.stocks.split(",") if s.strip()]
    else:
        stocks = ["075580", "010140", "010620", "333430", "099410"]
    if a.collect or a.collect_notes:
        with _SingleProcess():
            for st in stocks:
                name = names.get(st, st)
                if a.collect:
                    _log("%s %s collect start quarters=%s..%s" % (st, name, quarters[0], quarters[-1]))
                    res = collect_company(st, name, quarters, a.force)
                    ok = sum(1 for r in res if r.get("rcp") and not r.get("error"))
                    _log("%s %s collect done ok=%d/%d" % (st, name, ok, len(res)))
                    print("%s %-12s 수집 %d/%d 분기" % (st, name, ok, len(res)))
                if a.collect_notes:
                    _log("%s %s collect-notes start quarters=%s..%s" % (st, name, quarters[0], quarters[-1]))
                    res = collect_notes_company(st, name, quarters, a.force, a.notes_parent_fallback)
                    ok = sum(1 for r in res if r and (r.get("items") or (r.get("parent") or {}).get("cached")))
                    _log("%s %s collect-notes done ok=%d/%d" % (st, name, ok, len(res)))
                    print("%s %-12s 주석 %d/%d 분기" % (st, name, ok, len(res)))
                if a.build:
                    fin = build_company(st, quarters, name)
                    write_fin(fin)
                    _log("%s %s build quarters=%d issues=%d" % (st, name, len(fin["quarters"]), len(fin["issues"])))
    elif a.build:
        for st in stocks:
            fin = build_company(st, quarters, names.get(st, st))
            write_fin(fin)
            nq = len(fin["quarters"])
            ok = sum(1 for c in fin["checks"] if c["ok"])
            print("%s %-12s 분기 %d · checks %d/%d ok · issues %d → %s" % (
                st, fin["name"], nq, ok, len(fin["checks"]), len(fin["issues"]),
                os.path.relpath(os.path.join(FIN_DIR, st + ".json"), KSHIP)))
    if a.golden:
        g = load_golden()
        if not g:
            print("골든 파일 없음:", GOLDEN_PATH)
            return 1
        for st in stocks:
            p = os.path.join(FIN_DIR, st + ".json")
            if not os.path.exists(p):
                print("%s fin json 없음(먼저 --build)" % st)
                continue
            with open(p, encoding="utf-8") as f:
                fin = json.load(f)
            cmp_ = compare_golden(fin, g)
            if cmp_:
                fin["golden"] = cmp_
                write_fin(fin)
            print_golden(fin)
    return 0


if __name__ == "__main__":
    sys.exit(main())
