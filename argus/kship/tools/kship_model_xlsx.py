#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_model_xlsx — 모델 json(MODEL_SPEC 2-5) → 애널리스트 subQ 형 xlsx(MODEL_SPEC 2-6).

레퍼런스(사용자 subQ 모델 3개)의 골격을 그대로 따른다.
  README   시트 안내·단위·색 규약·출처
  변수      가정 시계열 — 환율 8행(fx.json) · 추정 드라이버(모델값에서 역산, 노란 셀) · 밸류에이션 스칼라
  BS연결    FnGuide 계정명 × 기간 덤프(백만원). fin json(2-1)이 있으면 전 계정, 없으면 모델 행이 매핑되는 계정만
  BS별도    같은 구조(별도). fin 없으면 헤더만
  subQ     분기 서브모델(억원). 확정치는 `=IFERROR(VLOOKUP($D행,BS연결,MATCH(E$1,BS연결H,0),0)/100,"")`
           진짜 수식, 추정치는 `변수` 가정 셀을 참조하는 수식(매출 = 전년동기 × (1+성장률) 등)
  SLS      선표 매출인식(sls json 2-4 가 있을 때만)
  분기·연간예상  subQ 를 이름으로 VLOOKUP 한 보고서 표
  TP       PER 밴드·PBR(ROE/COE) 적정가치 구간 — 모델 산출값, 목표주가·추천 아님
  외화      환율 QoQ · 외화 순노출 × Δ기말환율 → 환관련손익 추정

헤더 규약: 행1 분기 라벨('4Q21','1Q22',… 연간은 2022 숫자), 행4 'YYYY.MM'/'YYYY.12A', 데이터는 E열부터,
4분기 뒤 연간 1열. 이름정의 SUBQH·BS연결H·BS별도H·변수H(행1), BS연결·BS별도(계정명 열 C 부터 전체), 환율.
추정 열은 연노랑 배경, 실적/추정 경계는 굵은 테두리, 숫자 서식 #,##0. 추정 셀 메모 = 모델 json 의 basis.
확정 셀은 BS 시트에 그 기간 값이 있을 때만 VLOOKUP(빈 셀 VLOOKUP 은 0 으로 보이므로), 없으면 모델값 직접 + 메모, 둘 다 없으면 빈 칸.
결정론: 같은 모델·fin·fx·prices 면 바이트 동일 — BS 행3 UPDATE 스탬프·문서 속성·zip 엔트리 시각 전부 모델 built_at 날짜로 고정.

원칙: 출처 없는 숫자를 만들지 않는다 — 추정 드라이버 값은 전부 모델 json 의 v 에서 역산(implied)하고
그 사실을 셀 메모에 적는다. 사용자가 노란 셀을 바꾸면 subQ·분기·연간예상·TP 가 재계산된다.

    python3 kship_model_xlsx.py --model assets/models/010140.json --verify
    python3 kship_model_xlsx.py --all                 # assets/models/*.json → ../models/<stock>_model.xlsx
    python3 kship_model_xlsx.py --sample --verify     # tests/fixtures/model_sample.json 으로 개발·점검
"""
import argparse
import datetime
import json
import os
import re
import sys

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

from kship_lib import ASSETS, KSHIP

MODELS_DIR = os.path.join(ASSETS, "models")
FIN_DIR = os.path.join(ASSETS, "fin")
SLS_DIR = os.path.join(ASSETS, "sls")
OUT_DIR = os.path.join(KSHIP, "models")
SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "fixtures", "model_sample.json")

FIRST_COL = 5            # E — 데이터 첫 열(모든 시계열 시트 공통)
HEADER_ROW, DATE_ROW, DATA_ROW = 1, 4, 5
SIZE_LIMIT = 20 * 1024 * 1024

# 모델 행 key → FnGuide 계정명(BS 시트 VLOOKUP 키). 없는 key 는 수식 파생 또는 값 직접 기입.
ROW_ACCOUNT = {
    "매출액": "매출액(수익)", "매출원가": "매출원가", "매출총이익": "매출총이익", "판관비": "판관비",
    "영업이익": "영업이익", "기타영업손익": "기타영업손익", "금융손익": "금융손익", "금융수익": "금융수익",
    "금융비용": "금융비용", "이자수익": "이자수익", "이자비용": "이자비용", "이자손익": "이자손익",
    "기타영업외손익": "기타영업외손익", "지분법손익": "종속기업,공동지배기업및관계기업관련손익",
    "세전이익": "법인세비용차감전계속사업이익", "법인세비용": "법인세비용", "당기순이익": "당기순이익",
    "지배주주순이익": "(지배주주지분)당기순이익", "비지배주주순이익": "(비지배주주지분)당기순이익",
    "자산총계": "자산총계", "부채총계": "부채총계", "자본총계": "자본총계", "지배주주지분": "지배주주지분",
    "비지배주주지분": "비지배주주지분", "총차입금": "총차입금", "순차입금": "순차입금",
    "현금및현금성자산": "현금및현금성자산", "단기금융자산": "단기금융자산", "이자발생자산": "이자발생자산",
    "감가상각비": "감가상각비", "CAPEX": "CAPEX", "재고자산": "재고자산", "충당부채": "충당부채",
    "매출채권": "매출채권및기타채권", "매입채무": "매입채무및기타채무", "선수금": "선수금",
    "자본금": "자본금", "이익잉여금": "이익잉여금",
}
# 시점(BS) 성격 — 연간 열은 4Q 값, 추정 기본 드라이버는 QoQ
STOCK_KEYS = {"자산총계", "부채총계", "자본총계", "지배주주지분", "비지배주주지분", "총차입금", "순차입금",
              "현금및현금성자산", "단기금융자산", "이자발생자산", "재고자산", "충당부채", "매출채권", "매입채무",
              "선수금", "자본금", "이익잉여금", "BPS", "주식수"}
STOCK_GROUPS = {"재무상태", "BS", "자본"}
# 부호가 흔들려 비율 역산이 무의미한 행 — 절대값 가정
ABS_KEYS = {"금융손익", "기타영업외손익", "기타영업손익", "지분법손익", "이자손익", "일회성", "환관련손익", "파생상품손익"}
# 억원이 아닌 행
PER_SHARE_KEYS = {"EPS", "BPS", "DPS"}

FX_ROWS = [("USDKRW_avg", " 원/달러(평균)"), ("USDKRW_end", " 원/달러(기말)"),
           ("JPY100KRW_avg", " 원/100Y(평균)"), ("JPY100KRW_end", " 원/100Y(기말)"),
           ("EURKRW_avg", " W/Euro(평균)"), ("EURKRW_end", " W/Euro(기말)"),
           ("CNYKRW_avg", " 원/중국원(평균)"), ("CNYKRW_end", " 원/중국원(기말)")]
PRICE_ROWS = [("close_end", "종가(기말)"), ("high", "종가(최고)"), ("low", "종가(최저)"), ("avg", "종가(평균)")]

# ── 스타일 ───────────────────────────────────────────────────
F_BOLD = Font(bold=True)
F_HEAD = Font(bold=True, color="FFFFFF")
F_NOTE = Font(italic=True, color="666666", size=9)
F_KEY = Font(color="1F4E79")
FILL_HEAD = PatternFill("solid", fgColor="44546A")
FILL_EST = PatternFill("solid", fgColor="FFF9DB")       # 추정 열 연노랑
FILL_ANNUAL = PatternFill("solid", fgColor="EDEDED")    # 연간 열 회색
FILL_INPUT = PatternFill("solid", fgColor="FFF2AB")     # 사용자 가정 입력 셀
THIN, MED = Side(style="thin", color="999999"), Side(style="medium", color="000000")
NF_INT, NF_1, NF_PCT, NF_FX = "#,##0", "#,##0.0", "0.0%", "#,##0.00"


# ── 기간 헬퍼 ───────────────────────────────────────────────

def qlabel(q):
    """'2021Q4' → '4Q21' (레퍼런스 행1 규약)."""
    return "%sQ%s" % (q[5], q[2:4])


def qdate(q):
    """'2021Q4' → '2021.12' (레퍼런스 행4 규약, FnGuide 열키)."""
    return "%s.%02d" % (q[:4], int(q[5]) * 3)


def build_columns(quarters, annual):
    """분기 뒤에 그 해의 연간 열을 끼운 열 배치. 각 항목 {kind,key,label,date,col}."""
    annual = [str(a) for a in (annual or [])]
    cols, c = [], FIRST_COL
    years_seen = []
    for q in quarters:
        cols.append({"kind": "q", "key": q, "label": qlabel(q), "date": qdate(q), "col": c})
        c += 1
        y = q[:4]
        if q.endswith("Q4") or q == quarters[-1]:
            if y in annual and y not in years_seen:
                cols.append({"kind": "a", "key": y, "label": int(y), "date": y + ".12A", "col": c})
                years_seen.append(y)
                c += 1
    for y in annual:              # 분기가 하나도 없는 해(드묾)는 뒤에 붙인다
        if y not in years_seen:
            cols.append({"kind": "a", "key": y, "label": int(y), "date": y + ".12A", "col": c})
            years_seen.append(y)
            c += 1
    return cols


class Layout:
    """열 배치 + 실적/추정 경계. 모든 시계열 시트가 같은 열 위치를 쓴다(변수!E5 ↔ subQ!E5)."""

    def __init__(self, model):
        p = model["periods"]
        self.quarters = list(p["quarters"])
        self.annual = [str(a) for a in p.get("annual", [])]
        self.last_actual = p["last_actual"]
        self.cols = build_columns(self.quarters, self.annual)
        self.by_key = {c["key"]: c for c in self.cols}
        self.last_col = self.cols[-1]["col"] if self.cols else FIRST_COL
        self.qcols = [c for c in self.cols if c["kind"] == "q"]
        self.acols = [c for c in self.cols if c["kind"] == "a"]
        self.boundary_col = self.by_key[self.last_actual]["col"] if self.last_actual in self.by_key else None
        self.last_year = int(self.last_actual[:4])

    def col_of(self, key):
        return self.by_key[key]["col"]

    def letter(self, key):
        return get_column_letter(self.col_of(key))

    def is_est(self, c):
        """추정 음영 대상: last_actual 이후 분기, last_actual 연도 이후(포함) 연간."""
        if c["kind"] == "q":
            return c["key"] > self.last_actual
        return int(c["key"]) >= self.last_year

    def prev_q(self, q):
        i = self.quarters.index(q)
        return self.quarters[i - 1] if i > 0 else None

    def prev_year_q(self, q):
        py = "%d%s" % (int(q[:4]) - 1, q[4:])
        return py if py in self.by_key else None

    def year_quarters(self, y):
        return [q for q in self.quarters if q[:4] == y]


# ── 모델 접근 ───────────────────────────────────────────────

def cell_of(row, q):
    return (row.get("q") or {}).get(q) or {}


def val_of(row, q):
    return cell_of(row, q).get("v")


def is_stock(row):
    return row["key"] in STOCK_KEYS or row.get("group") in STOCK_GROUPS


def bs_sheet_for(row, q=None):
    src = (cell_of(row, q).get("src") if q else None) or row.get("src") or ""
    return "BS별도" if ".sep." in str(src) or str(src).startswith("sep") else "BS연결"


# ── 추정 드라이버 계획 ───────────────────────────────────────

def plan_drivers(rows):
    """행마다 추정 수식 종류를 정한다. 반환 {key: {"type", "base", ...}}.
    identity 행은 다른 subQ 행으로만 계산(가정 셀 없음), 나머지는 `변수` 드라이버 행을 하나씩 가진다."""
    keys = {r["key"] for r in rows}
    has = keys.__contains__
    plan = {}
    for r in rows:
        k = r["key"]
        if k == "매출액":
            d = {"type": "yoy", "label": "매출액 YoY"}
        elif k == "영업이익" and has("매출액"):
            d = {"type": "ratio", "base": "매출액", "label": "영업이익률(OPM)"}
        elif k == "판관비" and has("매출액"):
            d = {"type": "ratio", "base": "매출액", "label": "판관비율(/매출)"}
        elif k == "매출총이익" and has("영업이익") and has("판관비"):
            d = {"type": "identity", "expr": [("+", "영업이익"), ("+", "판관비")] + ([("-", "기타영업손익")] if has("기타영업손익") else []),
                 "note": "매출총이익 = 영업이익 + 판관비" + (" − 기타영업손익" if has("기타영업손익") else "")}
        elif k == "매출원가" and has("매출액") and has("매출총이익"):
            d = {"type": "identity", "expr": [("+", "매출액"), ("-", "매출총이익")], "note": "매출원가 = 매출액 − 매출총이익"}
        elif k == "세전이익" and has("영업이익"):
            # 모델(kship_model.py) basis 와 같은 순서 — 환관련손익(yard 외화 순노출 × Δ환율) 을 빼면 법인세→NI→EPS→BPS 까지 연쇄로 어긋난다
            parts = [("+", "영업이익")] + [("+", x) for x in ("금융손익", "기타영업외손익", "지분법손익", "환관련손익") if has(x)]
            d = {"type": "identity", "expr": parts, "note": "세전이익 = " + " + ".join(x for _, x in parts)}
        elif k == "법인세비용" and has("세전이익"):
            d = {"type": "ratio", "base": "세전이익", "label": "법인세율(/세전)"}
        elif k == "당기순이익" and has("세전이익") and has("법인세비용"):
            d = {"type": "identity", "expr": [("+", "세전이익"), ("-", "법인세비용")], "note": "당기순이익 = 세전이익 − 법인세비용"}
        elif k == "지배주주순이익" and has("당기순이익"):
            d = {"type": "ratio", "base": "당기순이익", "label": "지배주주 비중(/당기순이익)"}
        elif k == "EPS" and has("지배주주순이익") and has("주식수"):
            d = {"type": "per_share", "num": "지배주주순이익", "den": "주식수", "note": "EPS = 지배주주순이익(억원)×100 / 유통주식수(백만주)"}
        elif k == "BPS" and has("지배주주지분") and has("주식수"):
            d = {"type": "per_share", "num": "지배주주지분", "den": "주식수", "note": "BPS = 지배주주지분(억원)×100 / 유통주식수(백만주)"}
        elif k == "자본총계" and has("당기순이익"):
            d = {"type": "roll", "flow": "당기순이익", "label": "자본총계 기타변동(배당 등, 억원)"}
        elif k == "지배주주지분" and has("지배주주순이익"):
            d = {"type": "roll", "flow": "지배주주순이익", "label": "지배주주지분 기타변동(배당 등, 억원)"}
        elif k == "자산총계" and has("부채총계") and has("자본총계"):
            d = {"type": "identity", "expr": [("+", "부채총계"), ("+", "자본총계")], "note": "자산총계 = 부채총계 + 자본총계"}
        elif k.startswith("매출") and k not in ("매출액", "매출원가", "매출총이익", "매출채권") and has("매출액"):
            d = {"type": "ratio", "base": "매출액", "label": "%s 비중(/매출액)" % k}
        elif k.startswith("OP") and has("매출" + k[2:]):
            d = {"type": "ratio", "base": "매출" + k[2:], "label": "%s 마진(/매출%s)" % (k, k[2:])}
        elif k in ABS_KEYS:
            d = {"type": "abs", "label": "%s (가정, %s)" % (k, r.get("unit") or "억원")}
        elif is_stock(r):
            d = {"type": "qoq", "label": "%s QoQ" % k}
        else:
            d = {"type": "yoy", "label": "%s YoY" % k}
        plan[k] = d
    return plan


def implied_param(row, q, drv, rows_by_key, lay, base_of=None):
    """추정 셀의 가정값을 모델 v 에서 역산. 기준값이 없으면 None(→ 값 직접 기입 폴백).
    base_of(row, q) 는 기준 셀이 시트에서 실제로 갖게 될 값 — 확정 구간 VLOOKUP 이면 BS 값/100(반올림 전).
    모델 v 는 0.01 억원 반올림이라 기준이 0 에 가까운 행(순차입금 부호 전환 등)은 QoQ 역산이 크게 흔들린다."""
    base_of = base_of or val_of
    v = val_of(row, q)
    if v is None:
        return None
    t = drv["type"]
    if t == "abs":
        return v
    if t == "yoy":
        pq = lay.prev_year_q(q)
        b = base_of(row, pq) if pq else None
        return (v / b - 1) if b else None
    if t == "qoq":
        pq = lay.prev_q(q)
        b = base_of(row, pq) if pq else None
        return (v / b - 1) if b else None
    if t == "ratio":
        b = val_of(rows_by_key[drv["base"]], q)
        return (v / b) if b else None
    if t == "roll":
        pq = lay.prev_q(q)
        b = base_of(row, pq) if pq else None
        f = val_of(rows_by_key[drv["flow"]], q)
        return (b + f - v) if (b is not None and f is not None) else None
    return None


# ── 워크북 조립 ─────────────────────────────────────────────

class Builder:
    def __init__(self, model, fin=None, sls=None, fx=None, prices=None):
        self.m = model
        self.fin = fin
        self.sls = sls or model.get("sls")
        self.fx = fx
        self.prices = prices
        self.lay = Layout(model)
        self.rows = list(model["rows"])
        self.rows_by_key = {r["key"]: r for r in self.rows}
        self.plan = plan_drivers(self.rows)
        self.subq_row = {}       # key → subQ 행 번호
        self.bs_vals = {}        # 시트명 → {계정명: {열키: 백만원}} — 확정 셀을 VLOOKUP 으로 쓸지(값이 있을 때만) 판단
        self.drv_row = {}        # key → 변수 드라이버 행 번호
        self.scalar_row = {}     # 스칼라 가정 이름 → 변수 행 번호
        self.wb = Workbook()
        self.wb.remove(self.wb.active)
        self.stats = {}

    # 공통 헤더(행1 라벨·행3 인덱스·행4 기간) — 시계열 시트 공용
    def _header(self, ws, name_label, cols=None, unit_note=None):
        """행1 라벨('4Q21'/2021 숫자)·행3 인덱스·행4 'YYYY.MM'/'YYYY.12A'. cols 의 col 번호를 그대로 쓴다."""
        cols = cols if cols is not None else self.lay.cols
        ws.cell(HEADER_ROW, 3, name_label).font = F_NOTE
        if unit_note:
            ws.cell(HEADER_ROW, 2, unit_note).font = F_NOTE
        for i, c in enumerate(cols):
            col = c["col"]
            h = ws.cell(HEADER_ROW, col, c["label"])
            h.font = F_HEAD
            h.fill = FILL_HEAD
            h.alignment = Alignment(horizontal="center")
            ws.cell(3, col, i + 1).font = F_NOTE
            d = ws.cell(DATE_ROW, col, c["date"])
            d.font = F_NOTE
            d.alignment = Alignment(horizontal="center")
            ws.column_dimensions[get_column_letter(col)].width = 11
        ws.column_dimensions["A"].width = 18
        ws.column_dimensions["B"].width = 9
        ws.column_dimensions["C"].width = 26
        ws.column_dimensions["D"].width = 30
        ws.freeze_panes = ws.cell(DATA_ROW, FIRST_COL)

    def _shade(self, ws, last_row, cols=None):
        """추정 열 연노랑·연간 열 회색·경계 굵은 테두리(행1~last_row)."""
        cols = cols if cols is not None else self.lay.cols
        for c in cols:
            fill = FILL_EST if self.lay.is_est(c) else (FILL_ANNUAL if c["kind"] == "a" else None)
            for r in range(DATA_ROW, last_row + 1):
                cell = ws.cell(r, c["col"])
                if fill is not None and cell.fill.fgColor.rgb in (None, "00000000"):
                    cell.fill = fill
                if c["kind"] == "a":
                    cell.font = F_BOLD
        if self.lay.boundary_col:
            for r in range(HEADER_ROW, last_row + 1):
                cell = ws.cell(r, self.lay.boundary_col)
                cell.border = Border(right=MED, left=cell.border.left, top=cell.border.top, bottom=cell.border.bottom)

    def _name(self, name, ref):
        self.wb.defined_names[name] = DefinedName(name, attr_text=ref)

    def built_date(self):
        """모델 built_at 의 날짜 — BS 시트 UPDATE 스탬프·문서 속성·zip 시각을 이 날짜로 고정(같은 입력 → 같은 바이트)."""
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(self.m.get("built_at") or ""))
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else datetime.date(2026, 1, 1)

    def _bs_get(self, sheet, acct, key):
        """BS 시트에 (계정, 열키) 값이 있으면 백만원 값, 없으면 None."""
        return ((self.bs_vals.get(sheet) or {}).get(acct) or {}).get(key)

    def _sheet_base(self, row, q):
        """역산 기준값 = 그 셀이 시트에서 실제로 계산할 값. 확정 구간 VLOOKUP 셀이면 BS 값/100(반올림 전), 아니면 모델 v."""
        acct = ROW_ACCOUNT.get(row["key"])
        mc = cell_of(row, q)
        if q <= self.lay.last_actual and acct and (mc.get("kind") == "actual" or not mc):
            v = self._bs_get(bs_sheet_for(row, q), acct, q)
            if v is not None:
                return v / 100
        return val_of(row, q)

    # ── README ──
    def sheet_readme(self):
        ws = self.wb.create_sheet("README")
        m = self.m
        lines = [
            ("%s(%s) 실적 모델 — ARGUS 한국조선" % (m.get("name", ""), m.get("stock", "")), F_BOLD),
            ("기준 분기 %s · 마지막 실적 %s · 생성 %s" % (m.get("origin", ""), m["periods"]["last_actual"], m.get("built_at", "")), None),
            ("", None),
            ("시트", F_BOLD),
            ("변수      가정 시계열. 환율 8행(ECB via frankfurter — L2 fx.json), 추정 드라이버(노란 셀 = 모델값에서 역산한 가정, 바꾸면 재계산), 밸류에이션 스칼라", None),
            ("BS연결/BS별도  FnGuide 계정명 × 기간 값 덤프(백만원). 행1 분기라벨, 행4 YYYY.MM / YYYY.12A. 이름정의 BS연결H·BS연결(계정명 C열부터)", None),
            ("subQ      분기 서브모델(억원 = 백만원/100). 확정 행: =IFERROR(VLOOKUP($D행,BS연결,MATCH(E$1,BS연결H,0),0)/100,\"\")  추정 행: 변수 시트 가정 셀 참조 수식", None),
            ("SLS       선표 매출인식(백만$)·헤지 적용 원화·코호트(조선사만, sls json 있을 때)", None),
            ("분기/연간예상  subQ 를 이름(A열 key)으로 VLOOKUP 한 보고서 표(억원)", None),
            ("TP        PER 밴드 × 12M fwd EPS, PBR = ROE/COE × BPS — 모델 산출값 구간, 목표주가·추천 아님", None),
            ("외화      환율 QoQ, 외화 순노출 × Δ기말환율 → 환관련손익 추정", None),
            ("", None),
            ("규약", F_BOLD),
            ("· 데이터는 E열부터, 4분기 뒤 연간 1열(라벨은 숫자 연도). 실적/추정 경계 = 굵은 세로선, 추정 열 = 연노랑, 연간 열 = 회색", None),
            ("· 숫자 서식 #,##0(억원) · EPS/BPS 원 · 주식수 백만주 · 환율 원", None),
            ("· 추정 셀 메모 = 모델 json 의 basis. 변수 시트 노란 셀 메모 = 역산 방법. 출처 없는 숫자는 없다 — 가정이면 가정이라고 적었다", None),
            ("· BS 시트에 값이 없는 기간의 VLOOKUP 은 0 으로 보일 수 있다(엑셀 VLOOKUP 빈 셀 규칙). fin(L1) 수집 후 재생성", None),
            ("", None),
            ("출처: DART 정기보고서(연결/별도 재무제표), FnGuide 계정명 규약, ECB 환율(api.frankfurter.app), aikstockdata.com(금융위 확정종가 T+1, 출처표기·비영리)", None),
            ("재현: cd argus/kship/tools && python3 kship_model_xlsx.py --model assets/models/%s.json --verify   "
             "(모델 json 부터: kship_model.py --build --all --xlsx · xlsx 58사 일괄: kship_model_xlsx.py --all --verify)" % m.get("stock", "<stock>"), None),
            ("한계: 모델 quality.warnings — " + " / ".join((m.get("quality") or {}).get("warnings") or ["(없음)"]), None),
            ("백테스트: " + json.dumps(m.get("backtest") or {}, ensure_ascii=False), None),
        ]
        for i, (t, f) in enumerate(lines, 1):
            c = ws.cell(i, 1, t)
            if f:
                c.font = f
        ws.column_dimensions["A"].width = 160
        self.stats["README"] = (len(lines), 1)

    # ── 변수 ──
    def sheet_vars(self):
        ws = self.wb.create_sheet("변수")
        lay = self.lay
        self._header(ws, "이름: 변수H")
        ws.cell(2, 1, "가정 시계열 — 노란 셀은 추정 가정(모델값에서 역산). 바꾸면 subQ·분기·연간예상·TP 가 재계산됩니다.").font = F_NOTE
        r = DATA_ROW
        # 1. 환율
        ws.cell(r, 2, "1. FX").font = F_BOLD
        ws.cell(r, 3, "이름: 환율").font = F_NOTE
        fx_model = ((self.m.get("assumptions") or {}).get("fx") or {})
        fxq = (self.fx or {}).get("quarters") or {}
        fxf = (self.fx or {}).get("forward") or {}
        fxa = (self.fx or {}).get("annual") or {}
        fx_first = r + 1
        for metric, label in FX_ROWS:
            r += 1
            ws.cell(r, 1, metric).font = F_KEY
            ws.cell(r, 3, label)
            for c in lay.cols:
                v, note = None, None
                if c["kind"] == "q":
                    q = c["key"]
                    if isinstance(fx_model.get(metric), dict) and fx_model[metric].get(q) is not None:
                        v, note = fx_model[metric][q], "모델 assumptions.fx — " + str(fx_model.get("basis") or "")
                    elif q in fxq and fxq[q].get(metric) is not None:
                        v = fxq[q][metric]
                    elif isinstance(fxf.get(q), dict) and fxf[q].get(metric) is not None:
                        v, note = fxf[q][metric], "fx.json forward(%s) — 가정" % fxf.get("method", "")
                else:
                    a = fxa.get(c["key"]) or {}
                    v = a.get(metric)
                if v is None:
                    continue
                cell = ws.cell(r, c["col"], v)
                cell.number_format = NF_FX
                if lay.is_est(c):
                    cell.fill = FILL_INPUT
                if note:
                    cell.comment = Comment(note, "kship")
        fx_last = r
        # 1b. 종가 4행(prices.json history_quarterly) — 레퍼런스 PER 4종(기말/고/저/평균)용
        if self.prices and self.prices.get("history_quarterly"):
            r += 1
            ws.cell(r, 2, "1b. 종가").font = F_BOLD
            hist = self.prices["history_quarterly"]
            for metric, label in PRICE_ROWS:
                r += 1
                ws.cell(r, 1, "price_" + metric).font = F_KEY
                ws.cell(r, 3, label)
                for c in lay.qcols:
                    h = hist.get(c["key"]) or {}
                    if h.get(metric) is not None:
                        cell = ws.cell(r, c["col"], h[metric])
                        cell.number_format = NF_INT
                        if h.get("partial"):
                            cell.comment = Comment("분기 진행 중(partial) — aikstockdata/토스 일봉", "kship")
        # 2. 추정 드라이버
        r += 2
        ws.cell(r, 2, "2. 추정 드라이버").font = F_BOLD
        ws.cell(r, 3, "실적 열 = subQ 실현값(수식), 추정 열 = 가정(노란, 모델값 역산)").font = F_NOTE
        self.vars_ws = ws
        self.drv_first = r + 1
        for row in self.rows:
            d = self.plan[row["key"]]
            if d["type"] in ("identity", "per_share"):
                continue
            r += 1
            self.drv_row[row["key"]] = r
            ws.cell(r, 1, "drv:" + row["key"]).font = F_KEY
            ws.cell(r, 2, d["type"]).font = F_NOTE
            ws.cell(r, 3, d["label"])
        self.drv_last = r
        # 3. 밸류에이션·스칼라 가정
        r += 2
        ws.cell(r, 2, "3. 밸류에이션·스칼라").font = F_BOLD
        val = self.m.get("valuation") or {}
        price = val.get("price") or {}
        band = val.get("per_band") or {}
        asm = self.m.get("assumptions") or {}
        scalars = [
            ("종가", price.get("close"), "원 — %s" % (price.get("src") or "aikstockdata(금융위 T+1)"), NF_INT),
            ("기준일", price.get("as_of"), "종가 기준일", None),
            ("COE", val.get("coe"), "자기자본비용(가정)", NF_PCT),
            ("PER_lo", band.get("lo"), "PER 밴드 하단(배) — %s" % (band.get("basis") or ""), NF_1),
            ("PER_mid", band.get("mid"), "PER 밴드 중단(배)", NF_1),
            ("PER_hi", band.get("hi"), "PER 밴드 상단(배)", NF_1),
            ("EPS_Y1가중", 0.5, "12M fwd EPS = FY(last_actual연도)E × w + FY+1E × (1−w) — 기준 분기 2Q 이면 0.5(가정)", NF_PCT),
            ("세율", asm.get("tax_rate"), "법인세율 가정(참고 — 추정 수식은 드라이버 행 참조)", NF_PCT),
            ("판관비율", asm.get("sga_ratio"), "판관비율 가정(참고)", NF_PCT),
            ("배당성향", asm.get("payout"), "배당성향 가정(참고)", NF_PCT),
            ("외화순노출_백만$", (self.m.get("fx_pnl") or {}).get("net_usd_exposure_m"), (self.m.get("fx_pnl") or {}).get("method"), NF_1),
        ]
        for name, v, note, nf in scalars:
            r += 1
            self.scalar_row[name] = r
            ws.cell(r, 1, "sc:" + name).font = F_KEY
            ws.cell(r, 3, name)
            cell = ws.cell(r, 4, v)
            cell.fill = FILL_INPUT
            if nf:
                cell.number_format = nf
            ws.cell(r, 5, note).font = F_NOTE
        self.vars_last = r
        last = get_column_letter(lay.last_col)
        self._name("변수H", "변수!$C$%d:$%s$%d" % (HEADER_ROW, last, HEADER_ROW))
        self._name("환율", "변수!$C$%d:$%s$%d" % (fx_first, last, fx_last))
        self.stats["변수"] = (r, lay.last_col)

    def fill_driver_cells(self):
        """subQ 행 번호가 정해진 뒤 — 드라이버 행의 실적 열(실현값 수식)·추정 열(역산 가정값)을 채운다."""
        ws = self.vars_ws
        lay = self.lay
        for row in self.rows:
            k = row["key"]
            if k not in self.drv_row:
                continue
            d, r, sr = self.plan[k], self.drv_row[k], self.subq_row[k]
            nf = NF_PCT if d["type"] in ("yoy", "qoq", "ratio") else NF_1
            for c in lay.cols:
                L = get_column_letter(c["col"])
                cell = ws.cell(r, c["col"])
                cell.number_format = nf
                if c["kind"] == "q" and lay.is_est(c):
                    p = implied_param(row, c["key"], d, self.rows_by_key, lay, self._sheet_base)
                    if p is None:
                        continue
                    cell.value = round(p, 6)
                    cell.fill = FILL_INPUT
                    cell.comment = Comment("모델값 역산(implied): %s\n%s" % (
                        {"yoy": "v / 전년동기 − 1", "qoq": "v / 전분기 − 1", "ratio": "v / %s" % d.get("base"),
                         "abs": "모델 v 그대로", "roll": "전분기 + %s − v" % d.get("flow")}[d["type"]],
                        cell_of(row, c["key"]).get("basis") or ""), "kship")
                    continue
                # 실적(또는 연간) 열 — subQ 실현값
                f = None
                if d["type"] == "ratio":
                    br = self.subq_row.get(d["base"])
                    if br:
                        f = '=IFERROR(subQ!%s%d/subQ!%s%d,"")' % (L, sr, L, br)
                elif d["type"] == "yoy" and c["kind"] == "q":
                    pq = lay.prev_year_q(c["key"])
                    if pq:
                        f = '=IFERROR(subQ!%s%d/subQ!%s%d-1,"")' % (L, sr, lay.letter(pq), sr)
                elif d["type"] == "qoq" and c["kind"] == "q":
                    pq = lay.prev_q(c["key"])
                    if pq:
                        f = '=IFERROR(subQ!%s%d/subQ!%s%d-1,"")' % (L, sr, lay.letter(pq), sr)
                elif d["type"] == "abs":
                    f = "=subQ!%s%d" % (L, sr)
                elif d["type"] == "roll" and c["kind"] == "q":
                    pq = lay.prev_q(c["key"])
                    fr = self.subq_row.get(d["flow"])
                    if pq and fr:
                        f = '=IFERROR(subQ!%s%d+subQ!%s%d-subQ!%s%d,"")' % (lay.letter(pq), sr, L, fr, L, sr)
                if f:
                    cell.value = f
        self._shade(ws, self.vars_last)

    # ── BS연결 / BS별도 ──
    def _bs_values(self, scope):
        """{계정명: {열키: 값(백만원)}} — fin json 우선, 없으면 모델 실적 행(억원×100)."""
        lay = self.lay
        out = {}
        fin = (self.fin or {}).get(scope)
        if fin:
            for stmt in ("bs", "is", "cf"):
                data = fin.get(stmt) or {}
                accts = []
                for q in lay.quarters:
                    for a in (data.get(q) or {}):
                        if a not in accts:
                            accts.append(a)
                for a in accts:
                    d = out.setdefault(a, {})
                    for q in lay.quarters:
                        v = (data.get(q) or {}).get(a)
                        if v is not None:
                            d[q] = v
                    for y in lay.annual:
                        qs = lay.year_quarters(y)
                        if stmt == "bs":
                            q4 = y + "Q4"
                            if q4 in d:
                                d[y] = d[q4]
                        elif len(qs) == 4 and all(q in d for q in qs):
                            d[y] = round(sum(d[q] for q in qs), 2)
            return out
        if scope != "cons":
            return out
        for row in self.rows:
            acct = ROW_ACCOUNT.get(row["key"])
            if not acct or bs_sheet_for(row) != "BS연결":
                continue
            d = out.setdefault(acct, {})
            for q in lay.quarters:
                c = cell_of(row, q)
                if c.get("kind") == "actual" and c.get("v") is not None:
                    d[q] = round(c["v"] * 100, 2)
            for y, a in (row.get("a") or {}).items():
                if str(y) in lay.annual and a.get("kind") == "actual" and a.get("v") is not None:
                    d[str(y)] = round(a["v"] * 100, 2)
        return out

    def sheet_bs(self, scope):
        name = "BS연결" if scope == "cons" else "BS별도"
        ws = self.wb.create_sheet(name)
        lay = self.lay
        self._header(ws, "이름: %sH" % name, unit_note="(백만원)")
        ws.cell(2, 2, "연결" if scope == "cons" else "별도")
        ws.cell(3, 2, "%s(%s)" % (self.m.get("name", ""), "연" if scope == "cons" else "별"))
        stamp = self.built_date().strftime("%y-%m-%d")      # 레퍼런스 행3 규약 'UPDATE: yy-mm-dd' — 실행일이 아니라 모델 built_at(결정론)
        ws.cell(3, 3, "UPDATE: " + stamp).font = F_NOTE
        ws.cell(DATE_ROW, 2, "Account Code").font = F_NOTE
        ws.cell(DATE_ROW, 3, "AccountNAME").font = F_NOTE
        values = self._bs_values(scope)
        self.bs_vals[name] = values
        src = "fin json(kship_fin.py)" if (self.fin or {}).get(scope) else (
            "모델 실적 행(억원×100) — fin json 없음, 매핑 계정만" if scope == "cons" else "별도 fin 없음 — L1 kship_fin.py 산출 후 재생성")
        ws.cell(2, 4, src).font = F_NOTE
        r = DATA_ROW - 1
        for acct, d in values.items():
            r += 1
            ws.cell(r, 1, 1)
            ws.cell(r, 3, acct)
            for c in lay.cols:
                v = d.get(c["key"])
                if v is not None:
                    cell = ws.cell(r, c["col"], v)
                    cell.number_format = NF_INT
        last_row = max(r, DATA_ROW)
        last = get_column_letter(lay.last_col)
        self._name(name + "H", "%s!$C$%d:$%s$%d" % (name, HEADER_ROW, last, HEADER_ROW))
        self._name(name, "%s!$C$%d:$%s$%d" % (name, DATA_ROW, last, last_row))
        self._shade(ws, last_row)
        self.stats[name] = (last_row, lay.last_col)
        return values

    # ── subQ ──
    def sheet_subq(self):
        ws = self.wb.create_sheet("subQ")
        lay = self.lay
        self._header(ws, "subQ 분기 서브모델(억원, U=100)")
        ws.cell(HEADER_ROW, 1, "YQ").font = F_BOLD
        ws.cell(2, 1, "A=이름(key) B=그룹 C=단위 D=FnGuide 계정명(VLOOKUP 키). 확정=VLOOKUP(BS), 추정=변수 가정 참조").font = F_NOTE
        r = DATA_ROW - 1
        for row in self.rows:
            r += 1
            self.subq_row[row["key"]] = r
        for row in self.rows:
            r = self.subq_row[row["key"]]
            ws.cell(r, 1, row["key"]).font = F_KEY
            ws.cell(r, 2, row.get("group") or "")
            ws.cell(r, 3, row.get("unit") or "억원")
            acct = ROW_ACCOUNT.get(row["key"])
            ws.cell(r, 4, acct or row.get("label") or row["key"])
            nf = NF_1 if row["key"] == "주식수" else NF_INT
            for c in lay.cols:
                cell = ws.cell(r, c["col"])
                cell.number_format = nf
                if c["kind"] == "q":
                    self._subq_quarter(ws, row, c, acct)
                else:
                    self._subq_annual(ws, row, c, acct)
        last_row = r
        # 비율 행(참고) — 이름으로 분기·연간예상에서 끌어감
        ratios = [("OPM", "영업이익", "매출액"), ("NPM", "지배주주순이익", "매출액"), ("매출원가율", "매출원가", "매출액"), ("판관비율", "판관비", "매출액")]
        r += 1
        ws.cell(r, 2, "비율(참고)").font = F_NOTE
        for name, num, den in ratios:
            if num not in self.subq_row or den not in self.subq_row:
                continue
            r += 1
            self.subq_row[name] = r
            ws.cell(r, 1, name).font = F_KEY
            ws.cell(r, 3, "%")
            ws.cell(r, 4, "%s / %s" % (num, den))
            for c in lay.cols:
                L = get_column_letter(c["col"])
                cell = ws.cell(r, c["col"], '=IFERROR(%s%d/%s%d,"")' % (L, self.subq_row[num], L, self.subq_row[den]))
                cell.number_format = NF_PCT
        last_row = r
        last = get_column_letter(lay.last_col)
        self._name("SUBQH", "subQ!$A$%d:$%s$%d" % (HEADER_ROW, last, HEADER_ROW))
        self._name("subQ", "subQ!$A$%d:$%s$%d" % (DATA_ROW, last, last_row))
        self._shade(ws, last_row)
        self.stats["subQ"] = (last_row, lay.last_col)

    def _vlookup(self, row, q_or_y, acct, L):
        sheet = bs_sheet_for(row, q_or_y if isinstance(q_or_y, str) and "Q" in q_or_y else None)
        return '=IFERROR(VLOOKUP($D%d,%s,MATCH(%s$1,%sH,0),0)/100,"")' % (self.subq_row[row["key"]], sheet, L, sheet)

    def _identity_formula(self, drv, L):
        parts = []
        for sign, k in drv["expr"]:
            if k not in self.subq_row:
                return None
            parts.append("%s%s%d" % (sign if parts or sign == "-" else "", L, self.subq_row[k]))
        return '=IFERROR(%s,"")' % "".join(parts)

    def _subq_quarter(self, ws, row, c, acct):
        lay = self.lay
        q, L, r = c["key"], get_column_letter(c["col"]), self.subq_row[row["key"]]
        cell = ws.cell(r, c["col"])
        mc = cell_of(row, q)
        drv = self.plan[row["key"]]
        if q <= lay.last_actual:
            # 확정 구간 — BS 시트에 값이 있는 실측은 VLOOKUP, BS 에 없으면 모델값 직접(메모), 둘 다 없으면 빈 칸(0 표시 금지), 갭필 추정은 값 + 메모
            if mc.get("kind") == "actual" or not mc:
                sheet = bs_sheet_for(row, q)
                if acct and self._bs_get(sheet, acct, q) is not None:
                    cell.value = self._vlookup(row, q, acct, L)
                elif drv["type"] == "per_share" and mc.get("v") is not None:
                    cell.value = '=IFERROR(%s%d*100/%s%d,"")' % (L, self.subq_row[drv["num"]], L, self.subq_row[drv["den"]])
                elif mc.get("v") is not None:
                    cell.value = mc["v"]
                    cell.comment = Comment("실측(%s — 모델값 직접) — %s" % (
                        ("%s 시트에 %s %s 값 없음" % (sheet, acct, qdate(q))) if acct else "계정 매핑 없음", mc.get("src") or ""), "kship")
            else:
                if mc.get("v") is not None:
                    cell.value = mc["v"]
                    cell.fill = FILL_EST
                    cell.comment = Comment("추정(실적 구간 갭필): " + str(mc.get("basis") or ""), "kship")
            return
        # 추정 구간 — 가정 셀 참조 수식
        f = None
        t = drv["type"]
        if t == "identity":
            f = self._identity_formula(drv, L)
        elif t == "per_share":
            f = '=IFERROR(%s%d*100/%s%d,"")' % (L, self.subq_row[drv["num"]], L, self.subq_row[drv["den"]])
        else:
            dr = self.drv_row.get(row["key"])
            p = implied_param(row, q, drv, self.rows_by_key, lay, self._sheet_base)
            if dr and p is not None:
                if t == "yoy":
                    f = '=IFERROR(%s%d*(1+변수!%s%d),"")' % (lay.letter(lay.prev_year_q(q)), r, L, dr)
                elif t == "qoq":
                    f = '=IFERROR(%s%d*(1+변수!%s%d),"")' % (lay.letter(lay.prev_q(q)), r, L, dr)
                elif t == "ratio":
                    f = '=IFERROR(%s%d*변수!%s%d,"")' % (L, self.subq_row[drv["base"]], L, dr)
                elif t == "abs":
                    f = "=변수!%s%d" % (L, dr)
                elif t == "roll":
                    f = '=IFERROR(%s%d+%s%d-변수!%s%d,"")' % (lay.letter(lay.prev_q(q)), r, L, self.subq_row[drv["flow"]], L, dr)
        if f:
            cell.value = f
            if mc.get("basis") or mc.get("kind"):
                cell.comment = Comment("추정: %s\n[%s]" % (mc.get("basis") or drv.get("note") or "", t), "kship")
        elif mc.get("v") is not None:
            cell.value = mc["v"]
            cell.comment = Comment("추정(가정 셀 참조 불가 — 기준값 없음, 모델값 직접): " + str(mc.get("basis") or ""), "kship")

    def _subq_annual(self, ws, row, c, acct):
        lay = self.lay
        y, L, r = c["key"], get_column_letter(c["col"]), self.subq_row[row["key"]]
        cell = ws.cell(r, c["col"])
        a = (row.get("a") or {}).get(y) or {}
        qs = lay.year_quarters(y)
        stock = is_stock(row)
        if a.get("kind") == "actual" and acct and not lay.is_est(c):
            if self._bs_get(bs_sheet_for(row), acct, y) is not None:
                cell.value = self._vlookup(row, y, acct, L)
                return
            if len(qs) < 4 and a.get("v") is not None:       # BS 에 연간 값이 없고 분기도 미완 → 모델 연간값 직접
                cell.value = a["v"]
                cell.comment = Comment("연간 실측(BS 시트에 %s 없음 — 모델 a 값 직접)" % (y + ".12A"), "kship")
                return
        if len(qs) == 4:
            if stock:
                cell.value = "=%s%d" % (lay.letter(qs[-1]), r)
            elif self.plan[row["key"]]["type"] == "per_share" and row["key"] == "BPS":
                cell.value = "=%s%d" % (lay.letter(qs[-1]), r)
            else:
                cell.value = "=SUM(%s%d:%s%d)" % (lay.letter(qs[0]), r, lay.letter(qs[-1]), r)
            return
        if stock and qs:
            cell.value = "=%s%d" % (lay.letter(qs[-1]), r)
        elif a.get("v") is not None:
            cell.value = a["v"]
            cell.comment = Comment("연간(%s) — 분기 미완 연도, 모델 a 값 직접" % a.get("kind"), "kship")

    # ── SLS ──
    def sheet_sls(self):
        s = self.sls
        if not s:
            return
        ws = self.wb.create_sheet("SLS")
        byq = s.get("by_quarter") or {}
        byy = s.get("by_year") or {}
        qs = sorted(k for k in byq if re.fullmatch(r"\d{4}Q[1-4]", k))
        ys = sorted(k for k in byy if re.fullmatch(r"\d{4}", k))
        cols = [{"kind": "q", "key": q, "label": qlabel(q), "date": qdate(q), "col": FIRST_COL + i} for i, q in enumerate(qs)]
        cols += [{"kind": "a", "key": y, "label": int(y), "date": y + ".12A", "col": FIRST_COL + len(qs) + i} for i, y in enumerate(ys)]
        self._header(ws, "이름: SLS_H · 선표 매출인식(백만$) — sls json origin %s" % s.get("origin", ""), cols=cols)
        ws.cell(2, 1, "코호트 표(가정): ①적자 −5% ②BEP 0% ③중마진 5% ④호황 10% ⑤초호황 15% — 회사별 캘리브레이션은 target_opm.basis 참조").font = F_NOTE
        types, cohorts = [], []
        for d in list(byq.values()) + list(byy.values()):
            for t in (d.get("by_type") or {}):
                if t not in types:
                    types.append(t)
            for t in (d.get("by_cohort") or {}):
                if t not in cohorts:
                    cohorts.append(t)
        specs = [("usd_m", "매출인식 합계(백만$)", NF_1)] + [("type:" + t, "선종 " + t, NF_1) for t in types] + \
                [("cohort:" + t, "코호트 " + t, NF_1) for t in cohorts] + \
                [("hedge_ratio", "헤지비율", NF_PCT), ("hedge_rate", "헤지환율", NF_FX), ("spot_assumed", "건조시점 환율(가정)", NF_FX),
                 ("applied_rate", "적용환율", NF_FX), ("hedged_krw_m", "헤지적용 원화매출(백만원)", NF_INT), ("target_opm", "타겟 OPM(코호트)", NF_PCT)]
        topm = s.get("target_opm") or {}
        r = DATA_ROW - 1
        for key, label, nf in specs:
            r += 1
            ws.cell(r, 1, key).font = F_KEY
            ws.cell(r, 4, label)
            for c in cols:
                d = (byq if c["kind"] == "q" else byy).get(c["key"]) or {}
                if key.startswith("type:"):
                    v = (d.get("by_type") or {}).get(key[5:])
                elif key.startswith("cohort:"):
                    v = (d.get("by_cohort") or {}).get(key[7:])
                elif key == "target_opm":
                    v = (topm.get(c["key"]) or {}).get("opm")
                else:
                    v = d.get(key)
                if v is not None:
                    cell = ws.cell(r, c["col"], v)
                    cell.number_format = nf
        r += 2
        ws.cell(r, 1, "계약 원장(contracts.json 기반)").font = F_BOLD
        heads = ["rcp", "type", "ships", "amt_krw_m", "amt_usd_m", "fx_at_sign", "signed", "start", "end", "cohort", "curve", "estimated_series"]
        r += 1
        for i, h in enumerate(heads):
            ws.cell(r, 1 + i, h).font = F_BOLD
        for ct in s.get("contracts") or []:
            r += 1
            for i, h in enumerate(heads):
                v = ct.get(h)
                ws.cell(r, 1 + i, v if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False))
        for w in s.get("warnings") or []:
            r += 1
            ws.cell(r, 1, "⚠ " + w).font = F_NOTE
        if cols:
            self._name("SLS_H", "SLS!$A$1:$%s$1" % get_column_letter(cols[-1]["col"]))
        self.stats["SLS"] = (r, (cols[-1]["col"] if cols else FIRST_COL))

    # ── 분기 / 연간예상 ──
    def _view_keys(self, view):
        v = (self.m.get("views") or {}).get(view)
        keys = None
        if isinstance(v, list) and v and isinstance(v[0], list) and all(isinstance(x, str) for x in v[0]):
            keys = [k for k in v[0] if k in self.subq_row]
        if not keys:
            keys = [r["key"] for r in self.rows]
        return keys + [k for k in ("OPM", "NPM") if k in self.subq_row]

    def sheet_view(self, name, kind):
        ws = self.wb.create_sheet(name)
        lay = self.lay
        cols = [dict(c, col=FIRST_COL + i) for i, c in enumerate(lay.qcols if kind == "q" else lay.acols)]
        self._header(ws, "이름: %sH — subQ 를 이름으로 VLOOKUP(억원)" % name, cols=cols)
        price = (self.m.get("valuation") or {}).get("price") or {}
        ws.cell(2, 3, "종가:")
        ws.cell(2, 4, "=변수!D%d" % self.scalar_row["종가"]).number_format = NF_INT
        ws.cell(3, 3, "기준일:")
        ws.cell(3, 4, price.get("as_of"))
        r = DATA_ROW - 1
        for k in self._view_keys(name):
            r += 1
            row = self.rows_by_key.get(k) or {"key": k, "label": k, "unit": "%"}
            ws.cell(r, 1, k).font = F_KEY
            ws.cell(r, 4, row.get("label") or k)
            nf = NF_PCT if k in ("OPM", "NPM") else (NF_1 if k == "주식수" else NF_INT)
            for c in cols:
                L = get_column_letter(c["col"])
                cell = ws.cell(r, c["col"], '=IFERROR(VLOOKUP($A%d,subQ,MATCH(%s$1,SUBQH,0),0),"")' % (r, L))
                cell.number_format = nf
        # YoY 행(매출액·영업이익)
        for k in ("매출액", "영업이익", "지배주주순이익"):
            if k not in self.subq_row:
                continue
            r += 1
            ws.cell(r, 1, k + " YoY").font = F_KEY
            ws.cell(r, 4, k + " YoY")
            base_r = [rr for rr in range(DATA_ROW, r) if ws.cell(rr, 1).value == k][0]
            step = 4 if kind == "q" else 1
            for i, c in enumerate(cols):
                if i < step:
                    continue
                L, LP = get_column_letter(c["col"]), get_column_letter(cols[i - step]["col"])
                cell = ws.cell(r, c["col"], '=IFERROR(%s%d/%s%d-1,"")' % (L, base_r, LP, base_r))
                cell.number_format = NF_PCT
        # 음영(열 배치가 다르므로 직접)
        for c in cols:
            if lay.is_est(c):
                for rr in range(DATA_ROW, r + 1):
                    ws.cell(rr, c["col"]).fill = FILL_EST
            elif c["kind"] == "q" and c["key"] == lay.last_actual or (c["kind"] == "a" and int(c["key"]) == lay.last_year - 1):
                for rr in range(HEADER_ROW, r + 1):
                    cell = ws.cell(rr, c["col"])
                    cell.border = Border(right=MED)
        self.stats[name] = (r, cols[-1]["col"] if cols else FIRST_COL)

    # ── TP ──
    def sheet_tp(self):
        ws = self.wb.create_sheet("TP")
        lay = self.lay
        sc = self.scalar_row
        ws.cell(1, 2, "종가").font = F_BOLD
        ws.cell(1, 3, "=변수!D%d" % sc["종가"]).number_format = NF_INT
        ws.cell(2, 2, "기준일").font = F_BOLD
        ws.cell(2, 3, "=변수!D%d" % sc["기준일"])
        ws.cell(3, 2, "모델 산출값 — 목표주가·추천 아님. 밴드·COE 는 변수 시트 3절의 가정").font = F_NOTE
        y0 = lay.last_year
        years = [str(y) for y in (y0 - 1, y0, y0 + 1, y0 + 2) if str(y) in lay.annual]
        ws.cell(5, 3, "FY").font = F_BOLD
        for i, y in enumerate(years):
            c = ws.cell(5, 4 + i, int(y))
            c.font = F_HEAD
            c.fill = FILL_HEAD
            ws.cell(6, 4 + i, ("A" if int(y) < y0 else "E")).font = F_NOTE
        rows = [("EPS", "EPS(원)", NF_INT), ("BPS", "BPS(원)", NF_INT), ("지배주주순이익", "지배주주순이익(억원)", NF_INT), ("영업이익", "영업이익(억원)", NF_INT)]
        r = 6
        tp_row = {}
        for key, label, nf in rows:
            if key not in self.subq_row:
                continue
            r += 1
            tp_row[key] = r
            ws.cell(r, 3, label)
            for i, y in enumerate(years):
                L = get_column_letter(4 + i)
                ws.cell(r, 4 + i, '=IFERROR(VLOOKUP("%s",subQ,MATCH(%s$5,SUBQH,0),0),"")' % (key, L)).number_format = nf
        if "EPS" in tp_row and "BPS" in tp_row:
            r += 1
            ws.cell(r, 3, "ROE(EPS/기초BPS)")
            for i in range(1, len(years)):
                L, LP = get_column_letter(4 + i), get_column_letter(3 + i)
                ws.cell(r, 4 + i, '=IFERROR(%s%d/%s%d,"")' % (L, tp_row["EPS"], LP, tp_row["BPS"])).number_format = NF_PCT
        # 12M fwd EPS = FY(y0)E × w + FY(y0+1)E × (1−w)
        iy0 = years.index(str(y0)) if str(y0) in years else None
        r += 2
        ws.cell(r, 2, "PER").font = F_BOLD
        r += 1
        ws.cell(r, 3, "12M fwd EPS")
        if iy0 is not None and iy0 + 1 < len(years) and "EPS" in tp_row:
            L0, L1 = get_column_letter(4 + iy0), get_column_letter(5 + iy0)
            ws.cell(r, 4, '=IFERROR(%s%d*변수!D%d+%s%d*(1-변수!D%d),"")' % (L0, tp_row["EPS"], sc["EPS_Y1가중"], L1, tp_row["EPS"], sc["EPS_Y1가중"])).number_format = NF_INT
        eps_r = r
        for band in ("PER_lo", "PER_mid", "PER_hi"):
            r += 1
            ws.cell(r, 3, "적정가치 @%s" % band)
            ws.cell(r, 4, "=변수!D%d" % sc[band]).number_format = NF_1
            ws.cell(r, 5, '=IFERROR(ROUND($D$%d*D%d,-2),"")' % (eps_r, r)).number_format = NF_INT
            ws.cell(r, 6, '=IFERROR(E%d/$C$1-1,"")' % r).number_format = NF_PCT
            ws.cell(r, 7, "배 · 원 · 종가 대비").font = F_NOTE
        r += 1
        ws.cell(r, 3, "현재 PER(종가/12M fwd EPS)")
        ws.cell(r, 4, '=IFERROR($C$1/$D$%d,"")' % eps_r).number_format = NF_1
        r += 2
        ws.cell(r, 2, "PBR").font = F_BOLD
        r += 1
        ws.cell(r, 3, "최근 BPS(마지막 실적 분기)")
        ws.cell(r, 4, '=IFERROR(VLOOKUP("BPS",subQ,MATCH("%s",SUBQH,0),0),"")' % qlabel(lay.last_actual)).number_format = NF_INT
        bps_r = r
        r += 1
        ws.cell(r, 3, "ROE fwd(12M fwd EPS / BPS)")
        ws.cell(r, 4, '=IFERROR($D$%d/$D$%d,"")' % (eps_r, bps_r)).number_format = NF_PCT
        roe_r = r
        r += 1
        ws.cell(r, 3, "COE")
        ws.cell(r, 4, "=변수!D%d" % sc["COE"]).number_format = NF_PCT
        coe_r = r
        r += 1
        ws.cell(r, 3, "적정 PBR = ROE/COE")
        ws.cell(r, 4, '=IFERROR(D%d/D%d,"")' % (roe_r, coe_r)).number_format = NF_FX
        fpbr_r = r
        r += 1
        ws.cell(r, 3, "적정가치(PBR) = BPS × 적정PBR")
        ws.cell(r, 4, '=IFERROR(ROUND(D%d*D%d,-2),"")' % (bps_r, fpbr_r)).number_format = NF_INT
        ws.cell(r, 5, '=IFERROR(D%d/$C$1-1,"")' % r).number_format = NF_PCT
        r += 1
        ws.cell(r, 3, "현재 PBR(종가/BPS)")
        ws.cell(r, 4, '=IFERROR($C$1/D%d,"")' % bps_r).number_format = NF_FX
        val = self.m.get("valuation") or {}
        r += 2
        ws.cell(r, 2, "모델 json valuation(참고)").font = F_NOTE
        for k in ("eps_fwd12m", "bps_latest", "per_now", "pbr_now", "roe_fwd", "fair_pbr", "fair_value_pbr", "ev_ebitda", "note"):
            r += 1
            ws.cell(r, 3, k).font = F_NOTE
            v = val.get(k)
            ws.cell(r, 4, v if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False))
        ws.column_dimensions["C"].width = 34
        self.stats["TP"] = (r, 7)

    # ── 외화 ──
    def sheet_fx(self):
        ws = self.wb.create_sheet("외화")
        lay = self.lay
        cols = [dict(c, col=FIRST_COL + i) for i, c in enumerate(lay.qcols)]
        self._header(ws, "이름: 외화QH — 환율 QoQ · 외화 순노출 × Δ기말환율", cols=cols)
        fxp = self.m.get("fx_pnl") or {}
        specs = [(" 원/달러(평균)", True), (" 원/달러(기말)", True), (" W/Euro(평균)", True), (" W/Euro(기말)", True), (" 원/100Y(기말)", True)]
        r = DATA_ROW - 1
        end_r = None
        for label, _ in specs:
            r += 1
            ws.cell(r, 4, label)
            for c in cols:
                L = get_column_letter(c["col"])
                ws.cell(r, c["col"], '=IFERROR(VLOOKUP($D%d,환율,MATCH(%s$1,변수H,0),0),"")' % (r, L)).number_format = NF_FX
            if label == " 원/달러(기말)":
                end_r = r
            r += 1
            ws.cell(r, 1, label.strip() + " QoQ").font = F_KEY
            for i, c in enumerate(cols[1:], 1):
                L, LP = get_column_letter(c["col"]), get_column_letter(cols[i - 1]["col"])
                ws.cell(r, c["col"], '=IFERROR(%s%d/%s%d-1,"")' % (L, r - 1, LP, r - 1)).number_format = NF_PCT
        r += 2
        ws.cell(r, 1, "외화순노출").font = F_KEY
        ws.cell(r, 3, "외화 순노출(백만$)")
        ws.cell(r, 4, "=변수!D%d" % self.scalar_row["외화순노출_백만$"]).number_format = NF_1
        ws.cell(r, 5, fxp.get("method") or "").font = F_NOTE
        exp_r = r
        r += 1
        ws.cell(r, 1, "환관련손익추정").font = F_KEY
        ws.cell(r, 3, "환관련손익 추정(억원) = 순노출 × Δ원/달러(기말) / 100")
        for i, c in enumerate(cols[1:], 1):
            L, LP = get_column_letter(c["col"]), get_column_letter(cols[i - 1]["col"])
            ws.cell(r, c["col"], '=IFERROR($D$%d*(%s%d-%s%d)/100,"")' % (exp_r, L, end_r, LP, end_r)).number_format = NF_INT
        r += 1
        ws.cell(r, 1, "fx_pnl.by_q").font = F_KEY
        ws.cell(r, 3, "모델 fx_pnl.by_q(억원, 참고)")
        for c in cols:
            v = (fxp.get("by_q") or {}).get(c["key"])
            if isinstance(v, dict):
                v = v.get("v")
            if v is not None:
                ws.cell(r, c["col"], v).number_format = NF_INT
        if fxp.get("note"):
            r += 1
            ws.cell(r, 3, fxp["note"]).font = F_NOTE
        for c in cols:
            if lay.is_est(c):
                for rr in range(DATA_ROW, r + 1):
                    ws.cell(rr, c["col"]).fill = FILL_EST
        self.stats["외화"] = (r, cols[-1]["col"] if cols else FIRST_COL)

    def build(self):
        self.sheet_readme()
        self.sheet_vars()
        self.sheet_bs("cons")
        self.sheet_bs("sep")
        self.sheet_subq()
        self.fill_driver_cells()
        self.sheet_sls()
        self.sheet_view("분기", "q")
        self.sheet_view("연간예상", "a")
        self.sheet_tp()
        self.sheet_fx()
        # 결정론: 문서 속성 시각을 모델 built_at 날짜로 고정. openpyxl 은 save 때 modified 를 now 로 덮고 zip 엔트리 시각도
        # 실행 시각을 쓰므로 save_atomic 이 created 기준으로 다시 정규화한다(같은 입력 → 같은 바이트)
        d = self.built_date()
        dt = datetime.datetime(d.year, d.month, d.day)
        self.wb.properties.created = dt
        self.wb.properties.modified = dt
        self.wb.properties.creator = "kship_model_xlsx"
        self.wb.calculation.fullCalcOnLoad = True
        return self.wb


# ── 저장·검증 ───────────────────────────────────────────────

def _normalize_zip(src, dst, dt):
    """openpyxl 산출 zip 을 결정론적으로 다시 쓴다 — 모든 엔트리 시각 = dt, docProps/core.xml 의 dcterms:modified = created.
    (openpyxl writer 는 save 시 properties.modified 를 now 로 덮고 ZipInfo 시각에 실행 시각을 넣는다.)"""
    import zipfile
    stamp = (dt.year, dt.month, dt.day, 0, 0, 0)
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "docProps/core.xml":
                text = data.decode("utf-8")
                m = re.search(r"<dcterms:created[^>]*>([^<]*)</dcterms:created>", text)
                if m:
                    text = re.sub(r"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)", lambda mm: mm.group(1) + m.group(1) + mm.group(2), text)
                data = text.encode("utf-8")
            zi = zipfile.ZipInfo(info.filename, date_time=stamp)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = info.external_attr
            zout.writestr(zi, data)


def save_atomic(wb, path):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, ".kship_tmp_" + os.path.basename(path))
    raw = tmp + ".raw"
    wb.save(raw)
    try:
        _normalize_zip(raw, tmp, wb.properties.created or datetime.datetime(2026, 1, 1))
    finally:
        os.remove(raw)
    os.replace(tmp, path)
    return os.path.getsize(path)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_optional(path):
    return load_json(path) if path and os.path.exists(path) else None


class XlError(Exception):
    """엑셀 오류값(#N/A·#DIV/0! …) — IFERROR 가 잡는다."""


class Emulator:
    """생성 파일 검증용 초소형 수식 계산기(LibreOffice 없음).
    지원: 숫자·문자열·셀/범위 참조(시트!·$)·이름정의·+ - * / ^ & 비교·IFERROR·IF·VLOOKUP(정확일치)·
    MATCH(0)·SUM·ROUND·ABS·MIN·MAX. 그 밖은 XlError."""

    TOK = re.compile(r"""\s*(?:(?P<num>\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)|(?P<str>"(?:[^"]|"")*")|
        (?P<ref>(?:'[^']+'|[^\s!(),:;+\-*/^&<>=]+)!\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?|\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)|
        (?P<name>[^\s!(),:;+\-*/^&<>="']+)|(?P<op><>|<=|>=|[-+*/^&<>=(),:]))""", re.X)

    def __init__(self, wb):
        self.wb = wb
        self.names = {n: dn.attr_text for n, dn in wb.defined_names.items()}
        self.memo = {}
        self.stack = set()

    # 참조 해석
    def _split_ref(self, ref, cur_sheet):
        if "!" in ref:
            sh, rng = ref.rsplit("!", 1)
            sh = sh.strip("'")
        else:
            sh, rng = cur_sheet, ref
        rng = rng.replace("$", "")
        return sh, rng

    def _range_cells(self, sheet, rng):
        ws = self.wb[sheet]
        if ":" in rng:
            a, b = rng.split(":")
            c0, r0 = self._coord(a)
            c1, r1 = self._coord(b)
            return [[(sheet, get_column_letter(c) + str(r)) for c in range(c0, c1 + 1)] for r in range(r0, r1 + 1)]
        return [[(sheet, rng)]]

    @staticmethod
    def _coord(a):
        m = re.fullmatch(r"([A-Z]{1,3})(\d+)", a)
        col = 0
        for ch in m.group(1):
            col = col * 26 + ord(ch) - 64
        return col, int(m.group(2))

    def value(self, sheet, coord):
        key = (sheet, coord)
        if key in self.memo:
            return self.memo[key]
        if key in self.stack:
            raise XlError("circular %s!%s" % key)
        v = self.wb[sheet][coord].value
        if isinstance(v, str) and v.startswith("="):
            # 중첩 평가 — 바깥 파서 상태(toks·i·sheet)를 보존한다
            saved = (getattr(self, "toks", None), getattr(self, "i", 0), getattr(self, "sheet", None))
            self.stack.add(key)
            try:
                v = self.eval(v[1:], sheet)
            finally:
                self.stack.discard(key)
                self.toks, self.i, self.sheet = saved
        self.memo[key] = v
        return v

    # 파서(재귀 하강)
    def eval(self, text, sheet):
        self.toks = [(m.lastgroup, m.group(m.lastgroup)) for m in self.TOK.finditer(text) if m.lastgroup]
        self.i = 0
        self.sheet = sheet
        v = self._cmp()
        return v

    def _peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def _next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def _cmp(self):
        a = self._concat()
        while self._peek() == ("op", "=") or self._peek()[1] in ("<>", "<", ">", "<=", ">=") and self._peek()[0] == "op":
            op = self._next()[1]
            b = self._concat()
            a = {"=": a == b, "<>": a != b, "<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]
        return a

    def _concat(self):
        a = self._add()
        while self._peek() == ("op", "&"):
            self._next()
            a = str(a) + str(self._add())
        return a

    def _add(self):
        a = self._mul()
        while self._peek()[0] == "op" and self._peek()[1] in "+-":
            op = self._next()[1]
            b = self._mul()
            a = self._n(a) + self._n(b) if op == "+" else self._n(a) - self._n(b)
        return a

    def _mul(self):
        a = self._pow()
        while self._peek()[0] == "op" and self._peek()[1] in "*/":
            op = self._next()[1]
            b = self._pow()
            if op == "*":
                a = self._n(a) * self._n(b)
            else:
                if self._n(b) == 0:
                    raise XlError("#DIV/0!")
                a = self._n(a) / self._n(b)
        return a

    def _pow(self):
        a = self._unary()
        while self._peek() == ("op", "^"):
            self._next()
            a = self._n(a) ** self._n(self._unary())
        return a

    def _unary(self):
        if self._peek() == ("op", "-"):
            self._next()
            return -self._n(self._unary())
        if self._peek() == ("op", "+"):
            self._next()
            return self._unary()
        return self._atom()

    @staticmethod
    def _n(v):
        if v is None or v == "":
            return 0
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, str):
            raise XlError("#VALUE!")
        return v

    def _atom(self):
        kind, tok = self._next()
        if kind == "num":
            return float(tok) if ("." in tok or "e" in tok.lower()) else int(tok)
        if kind == "str":
            return tok[1:-1].replace('""', '"')
        if kind == "op" and tok == "(":
            v = self._cmp()
            assert self._next() == ("op", ")")
            return v
        if kind == "ref":
            sh, rng = self._split_ref(tok, self.sheet)
            if ":" in rng:
                return ("range", sh, rng)
            return self.value(sh, rng)
        if kind == "name":
            if self._peek() == ("op", "("):
                self._next()
                args = []
                if self._peek() != ("op", ")"):
                    args.append(self._cmp_or_range())
                    while self._peek() == ("op", ","):
                        self._next()
                        args.append(self._cmp_or_range())
                assert self._next() == ("op", ")")
                return self._call(tok.upper(), args)
            if tok in self.names:
                sh, rng = self._split_ref(self.names[tok], self.sheet)
                return ("range", sh, rng) if ":" in rng else self.value(sh, rng)
            raise XlError("#NAME? " + tok)
        raise XlError("parse " + str(tok))

    def _cmp_or_range(self):
        # IFERROR 는 첫 인자 오류를 잡아야 하므로 지연 평가 대신 예외를 값으로 돌린다
        save = self.i
        try:
            return self._cmp()
        except XlError as e:
            # 인자 끝까지 토큰을 소비
            depth = 0
            self.i = save
            while self.i < len(self.toks):
                k, t = self.toks[self.i]
                if k == "op" and t == "(":
                    depth += 1
                elif k == "op" and t == ")":
                    if depth == 0:
                        break
                    depth -= 1
                elif k == "op" and t == "," and depth == 0:
                    break
                self.i += 1
            return e

    def _cells(self, arg):
        if isinstance(arg, tuple) and arg[0] == "range":
            return self._range_cells(arg[1], arg[2])
        raise XlError("#VALUE! range expected")

    def _call(self, fn, args):
        if fn == "IFERROR":
            return args[1] if isinstance(args[0], XlError) else args[0]
        for a in args:
            if isinstance(a, XlError):
                raise a
        if fn == "IF":
            return args[1] if args[0] else (args[2] if len(args) > 2 else False)
        if fn == "SUM":
            s = 0
            for a in args:
                if isinstance(a, tuple):
                    for rowc in self._cells(a):
                        for sh, co in rowc:
                            v = self.value(sh, co)
                            if isinstance(v, (int, float)) and not isinstance(v, bool):
                                s += v
                else:
                    s += self._n(a)
            return s
        if fn == "ROUND":
            return round(self._n(args[0]), int(args[1]))
        if fn == "ABS":
            return abs(self._n(args[0]))
        if fn == "MIN":
            return min(self._n(a) for a in args)
        if fn == "MAX":
            return max(self._n(a) for a in args)
        if fn == "MATCH":
            look, rng = args[0], args[1]
            cells = self._cells(rng)
            flat = [c for rowc in cells for c in rowc]
            for i, (sh, co) in enumerate(flat, 1):
                if self._eq(self.value(sh, co), look):
                    return i
            raise XlError("#N/A MATCH %r" % (look,))
        if fn == "VLOOKUP":
            look, rng, idx = args[0], args[1], int(self._n(args[2]))
            for rowc in self._cells(rng):
                sh, co = rowc[0]
                if self._eq(self.value(sh, co), look):
                    sh2, co2 = rowc[idx - 1]
                    v = self.value(sh2, co2)
                    return 0 if v is None else v          # 엑셀: 빈 셀 → 0
            raise XlError("#N/A VLOOKUP %r" % (look,))
        raise XlError("#NAME? " + fn)

    @staticmethod
    def _eq(a, b):
        if isinstance(a, str) and isinstance(b, str):
            return a.strip().lower() == b.strip().lower()
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return float(a) == float(b)
        return a == b


def verify(path, model, keys=("매출액", "영업이익", "지배주주순이익", "자산총계"), quarters_after=2):
    """재오픈 → 시트·이름정의·수식 개수, VLOOKUP 흉내(마지막 실적 분기), 추정 T+1 열 재계산 대조."""
    wb = load_workbook(path, data_only=False)
    rep = {"file": path, "size_bytes": os.path.getsize(path), "sheets": {}, "defined_names": {}, "formulas_total": 0,
           "checks": []}
    for ws in wb.worksheets:
        nf = sum(1 for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("="))
        ncomment = sum(1 for row in ws.iter_rows() for c in row if c.comment is not None)
        rep["sheets"][ws.title] = {"rows": ws.max_row, "cols": ws.max_column, "formulas": nf, "comments": ncomment}
        rep["formulas_total"] += nf
    for n, dn in wb.defined_names.items():
        rep["defined_names"][n] = dn.attr_text
    em = Emulator(wb)
    lay = Layout(model)
    ws = wb["subQ"]
    rows_by_key = {r["key"]: r for r in model["rows"]}
    # subQ 행 번호 찾기
    subq_row = {}
    for r in range(DATA_ROW, ws.max_row + 1):
        k = ws.cell(r, 1).value
        if k:
            subq_row[k] = r
    la = lay.last_actual
    for k in keys:
        if k not in subq_row:
            continue
        r = subq_row[k]
        coord = "%s%d" % (lay.letter(la), r)
        f = ws[coord].value
        model_v = val_of(rows_by_key[k], la)
        chk = {"cell": "subQ!" + coord, "quarter": la, "formula": f, "model_v": model_v}
        try:
            got = em.value("subQ", coord)
            chk["emulated"] = got
            if model_v is None:
                # 모델에 값이 없는 확정 셀 — 시트도 비어 있어야 한다(VLOOKUP 0 표시 금지)
                chk["ok"] = got in (None, "")
                chk["no_model_value"] = True
            else:
                chk["ok"] = isinstance(got, (int, float)) and abs(got - model_v) < 0.01
            # f 는 VLOOKUP 수식이거나(BS 에 값 있음) 모델값 직접(숫자) — 숫자면 추적 생략
            m = re.search(r"VLOOKUP\(\$D(\d+),(BS[^,]+),MATCH\(([A-Z]+)\$1,(BS[^,]+)H,0\),0\)", f if isinstance(f, str) else "")
            if m:
                acct = ws.cell(int(m.group(1)), 4).value
                bs = wb[m.group(2)]
                hdr = {bs.cell(1, c).value: c for c in range(3, bs.max_column + 1)}
                col = hdr.get(ws.cell(1, ws[coord].column).value)
                acct_row = next((rr for rr in range(DATA_ROW, bs.max_row + 1) if bs.cell(rr, 3).value == acct), None)
                chk["vlookup_trace"] = {"acct": acct, "bs_sheet": m.group(2), "bs_col": get_column_letter(col) if col else None,
                                        "bs_row": acct_row, "bs_value_million": bs.cell(acct_row, col).value if (col and acct_row) else None}
        except Exception as e:  # noqa: BLE001
            chk["error"] = repr(e)
            chk["ok"] = False
        rep["checks"].append(chk)
    # 추정 열 재계산 — last_actual 다음 분기부터 quarters_after 개
    est_q = [q for q in lay.quarters if q > la][:quarters_after]
    est = {"quarters": est_q, "rows": 0, "match": 0, "mismatch": []}
    for q in est_q:
        L = lay.letter(q)
        for k, r in subq_row.items():
            if k not in rows_by_key:
                continue
            mv = val_of(rows_by_key[k], q)
            if mv is None:
                continue
            est["rows"] += 1
            try:
                got = em.value("subQ", "%s%d" % (L, r))
            except Exception as e:  # noqa: BLE001
                got = repr(e)
            # 억원 행: 0.05 또는 1e-4 상대. 주당 행(EPS·BPS·DPS, 원): 모델이 0.1 원 반올림이고 입력 NI 의 0.01 억원 반올림이
            # ×100/주식수(백만주) 로 증폭되므로 0.5 원 또는 1e-3 상대 — 그 이상 벌어지면 수식이 틀린 것
            tol = max(0.5, abs(mv) * 1e-3) if k in PER_SHARE_KEYS else max(0.05, abs(mv) * 1e-4)
            if isinstance(got, (int, float)) and abs(got - mv) <= tol:
                est["match"] += 1
            else:
                est["mismatch"].append({"key": k, "q": q, "model": mv, "emulated": got})
    rep["estimate_recalc"] = est
    rep["size_ok"] = rep["size_bytes"] <= SIZE_LIMIT
    return rep


def build_one(model_path, out_path=None, fin_path=None, sls_path=None, fx_path=None, prices_path=None, do_verify=False):
    model = load_json(model_path)
    stock = model["stock"]
    fin = load_optional(fin_path or os.path.join(FIN_DIR, stock + ".json"))
    sls = load_optional(sls_path or os.path.join(SLS_DIR, stock + ".json"))
    fx = load_optional(fx_path or os.path.join(ASSETS, "fx.json"))
    prices_all = load_optional(prices_path or os.path.join(ASSETS, "prices.json"))
    prices = ((prices_all or {}).get("rows") or {}).get(stock)
    out_path = out_path or os.path.join(OUT_DIR, "%s_model.xlsx" % stock)
    b = Builder(model, fin=fin, sls=sls, fx=fx, prices=prices)
    wb = b.build()
    size = save_atomic(wb, out_path)
    rep = {"out": out_path, "size_bytes": size, "sheet_dims": b.stats, "fin": bool(fin), "sls": bool(sls), "fx": bool(fx), "prices": bool(prices)}
    if size > SIZE_LIMIT:
        rep["error"] = "size > 20MB"
    if do_verify:
        rep["verify"] = verify(out_path, model)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="모델 json → subQ 형 xlsx")
    ap.add_argument("--model", help="모델 json 경로(스펙 2-5)")
    ap.add_argument("--sample", action="store_true", help="tests/fixtures/model_sample.json 사용")
    ap.add_argument("--all", action="store_true", help="assets/models/*.json 전부")
    ap.add_argument("--out", help="출력 xlsx 경로(기본 argus/kship/models/<stock>_model.xlsx)")
    ap.add_argument("--fin", help="fin json(2-1) 경로 — 기본 assets/fin/<stock>.json 이 있으면 사용")
    ap.add_argument("--sls", help="sls json(2-4) 경로")
    ap.add_argument("--fx", help="fx.json 경로")
    ap.add_argument("--prices", help="prices.json 경로")
    ap.add_argument("--verify", action="store_true", help="재오픈 검증(수식·이름정의·VLOOKUP 흉내·추정 재계산)")
    a = ap.parse_args(argv)
    targets = []
    if a.sample:
        targets.append(SAMPLE)
    if a.model:
        targets.append(a.model)
    if a.all:
        targets += sorted(os.path.join(MODELS_DIR, f) for f in os.listdir(MODELS_DIR) if f.endswith(".json") and f != "summary.json") if os.path.isdir(MODELS_DIR) else []
    if not targets:
        ap.error("--model / --sample / --all 중 하나")
    reps = []
    for t in targets:
        rep = build_one(t, out_path=a.out if len(targets) == 1 else None, fin_path=a.fin, sls_path=a.sls, fx_path=a.fx,
                        prices_path=a.prices, do_verify=a.verify)
        reps.append(rep)
    print(json.dumps(reps if len(reps) > 1 else reps[0], ensure_ascii=False, indent=1, default=str))
    return 0 if all("error" not in r for r in reps) else 1


if __name__ == "__main__":
    sys.exit(main())
