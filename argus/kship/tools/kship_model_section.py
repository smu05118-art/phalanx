#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_model_section — 실적 모델(assets/models/<stock>.json)을 회사 페이지 섹션과 허브 표로 그린다.

  render_model_section(entry, model, fin=None, price=None, sls=None) -> html
      <section class="card"> 묶음 8개: ① KPI 스트립(FY2026E~28E 매출·OP·OPM·EPS + 현재 PER/PBR)
      ② 분기 손익표(최근 8A + 10E, 추정 칸 음영·근거 툴팁, 억원) ③ 사업부 매출·OPM 차트
      ④ 조선사만: 선표 매출인식(백만$→헤지 원화)·수주업황 코호트 비중 차트(코호트 모드·잔고 캡 표기)
      ④' 신규수주 시나리오 카드(model.scenarios 가 있을 때만): FY2026E~28E 기존잔고만/보수/기준/낙관 매출·OP 막대+표
      ⑤ 가정 패널(환율·헤지·OPM·세율·판관비율 + 신규수주·코호트 모드·잔고 캡·드라이버 OOS 선택)
      ⑥ 밸류에이션 스트립(PER/PBR 밴드·적정가치 구간 — 모델 산출값, 목표주가·추천 아님)
      ⑦ xlsx 다운로드(models/<stock>_model.xlsx, 없으면 '준비 중') ⑧ 각주(출처·한계·백테스트·신규수주 메타·OOS 규칙)
  라운드 3(MODEL_SPEC §5-5): 손익표에 `매출조선신규`·`OP조선신규` 를 들여쓴 하위 행으로, 영업외 세부(이자·환·파생·기타·지분법·중단)는
  값이 있을 때만; 섹션 머리·KPI 에 '신규수주 포함(forecast_panel base, 미보정)' 라벨; 드라이버 표기에 OOS 선택 결과
  (`WAPE 연동 x% vs 추세 y%` → 채택/폴백); 허브 표에 신규수주 열.
  5차(V7, T6 D7): status(데이터 완전성)와 driver_fallback(드라이버 폴백 사유 corr|significance|n|oos|no_link|none)을 섞지 않고 따로 —
  섹션 머리·KPI 위 '모델 상태' 한 줄(partial 사유는 quality 필드로 되짚는다. 모델이 사유를 따로 적지 않으므로)·허브 '폴백 사유' 열·KPI 타일;
  허브 고정 각주(마지막 갱신은 입력 파일의 기록만 — 시계를 읽지 않는다 · 출처 · 단위 · 면책); 모집단 밖 모델(피합병 010620)도 허브 표에
  '모집단 외' 로 올린다(빠뜨리지 않음); 모바일(360px) — .grid2 는 min(360px,100%) · .wrap 가로 스크롤.
  라운드 7 (p): 조정EPS 행(kship_model.py one_offs_detected 회사만)이 있으면 KPI 'EPS x원 (조정 y원)'·허브 EPS 칸 data-adj+괄호(연도별 임계 이상 다를 때만),
  손익표에 EPS 바로 아래 들여쓴 하위 행, KPI PER 타일에 '모델 TTM PER a (조정 b)'(종가 ÷ Σ 마지막 4실적분기 — 외부 aik TTM 과 따로), 가정 패널에 의심 분기 항목.
  보고 EPS 가 1차 값(data-v·정렬·summary.fy.eps 불변) — '실적은 실적'. 'PER 현재' 는 12M fwd(추정 분기만)라 값 불변, 툴팁만.
  라운드 7 수정(2026-10-09): 손익표 하위 행 라벨은 모델 라벨(net_panel·원장 폴백 문구 포함) + '└ ' 접두 — 고정 문구로 덮지 않는다; 가정 패널 '법인세율' 은
  tax_path 분기(이월결손 램프는 '유지값 → 22%' + 유지/램프 분기, 툴팁에 tax_schedule); 허브 폴백 툴팁은 eligibility 의 Σshare 문장을 붙인다.
  section_for_stock(stock) -> html | ""   회사 페이지 훅(kship_page/kship_parts 의 _model_section)이 부른다.
                                          모델 json 이 없으면 빈 문자열 — 빈 칸으로 흉내 내지 않는다.
  build_models_hub(models_dir) -> html    argus/kship/models.html — 56사 표(역할·FY2026E~28E·PER/PBR·status), 정렬·검색.

원칙: 추정 칸은 항상 `kind:"estimate"` 를 화면(음영·E 표기)과 툴팁(basis)으로 드러낸다. 출처 없는 숫자를 만들지
않는다 — 모델이 주지 않은 값은 '—'. 스크립트 안전: 임베드 JSON 은 json_for_html 로만 넣고, 차트 변수는 IIFE 안에만
둔다(회사 페이지의 DATA/SEGC 전역과 충돌 금지). Chart.js 는 페이지에 이미 있으면 그대로 쓰고, 기자재 페이지처럼
없으면 vendor/chart.umd.min.js 를 한 번만 지연 로드한다. 다크 모드는 page() 셸의 CSS 변수(--pn·--tx2·--ln…)를 쓴다.

    python3 kship_model_section.py --hub                                  # models.html
    python3 kship_model_section.py --render 010140 --model tests/fixtures/model_mock_010140.json \
                                   --sls tests/fixtures/model_mock_sls_010140.json --out ./model-section-preview.html
    python3 kship_model_section.py --check ./model-section-preview.html  # 태그 균형 검사
"""
import argparse
import collections
import json
import math
import os
import re
import sys
from html.parser import HTMLParser

from kship_lib import (ASSETS, CHART_DEFAULTS_JS, E, KSHIP, TABLE_JS, atomic_write, json_for_html, opm_table_text, page)

MODELS_DIR = os.path.join(ASSETS, "models")      # L4 산출(json)
SLS_DIR = os.path.join(ASSETS, "sls")            # L3 산출
FIN_DIR = os.path.join(ASSETS, "fin")            # L1 산출
PRICES_PATH = os.path.join(ASSETS, "prices.json")  # L2 산출
XLSX_DIR = os.path.join(KSHIP, "models")         # L5 산출(xlsx) — 링크만 건다

FY_EST = ("2026", "2027", "2028")
N_ACTUAL, N_EST = 8, 10
ROLE_KO = {"yard": "조선사", "holding": "지주", "engine": "엔진", "equip": "기자재", "steel": "강재"}
STATUS_KO = {"full": "완성", "partial": "부분", "no_fin": "재무 없음"}
SEG_COLORS = ["#3987e5", "#199e70", "#9085e9", "#c98500", "#d55181", "#008300"]
COHORT_ORDER = ["①적자", "②BEP", "③중마진", "④호황", "⑤초호황"]
COHORT_COLORS = {"①적자": "#e66767", "②BEP": "#9085e9", "③중마진": "#3987e5", "④호황": "#199e70", "⑤초호황": "#c98500"}
DISCLAIMER = "모델 산출값 — 목표주가·추천 아님"
AIK_CREDIT = "aikstockdata.com(금융위 확정종가 T+1) — 출처표기·비영리 이용"
# 매출 드라이버(kship_model.py STRATEGIES 의 type) → 화면 표기. 폴백은 폴백이라고 적는다(고객 연동으로 오해 금지).
DRIVER_KO = {
    "trend_seasonal": "추세+계절성 폴백",
    "customer_yard_revenue_weighted": "고객 조선사 매출 연동",
    "sls_marine_plus_uncovered_backlog_runoff": "선표(SLS)+미커버 잔고 소진",
    "subsidiary_yard_scaled": "종속 조선사 비율 합산",
    "subsidiary_models": "종속사 모델 합산",
    "median_flat": "최근 4분기 중위 유지",
    "residual": "연결−별도−종속사 잔차",
}
# 라운드 3(MODEL_SPEC §5-5) 라벨 — 값이 아니라 표기. 신규수주는 forecast_panel base 를 행에 더한 것이며 보정된 수주 예측이 아니다.
NEW_ORDERS_LABEL = "신규수주 포함(forecast_panel base, 미보정)"
NEW_ORDERS_FALLBACK_LABEL = "신규수주 포함(forecast_panel covered_scope 폴백, 미보정·저신뢰)"
# 라운드 7(2026-10-08): 폴백 사슬 3단 — 패널 신규수주가 공시 체결 속도의 50% 미만이면 공시 계약 원장 체결 분기 min/median/max 를 신규수주로(HJ重).
NEW_ORDERS_LEDGER_LABEL = "신규수주 포함(공시 계약 원장 체결 속도 폴백, 미보정·저신뢰)"
NEW_ORDERS_EXCL_LABEL = "신규수주 미포함(2026Q2 잔고 소진분만)"
COHORT_MODE_KO = {"reference_anchor": "레퍼런스 앵커(수주연도→등급)", "ledger_relative": "원장 상대등급"}
SCENARIO_KO = collections.OrderedDict([("existing_only", "기존 잔고만"), ("conservative", "보수"), ("base", "기준(base)"), ("optimistic", "낙관")])
SCENARIO_COLORS = {"existing_only": "#5d6675", "conservative": "#9085e9", "base": "#3987e5", "optimistic": "#199e70"}
# 영업외 세부 행 — 값(|v| ≥ 0.05억)이 한 칸이라도 있을 때만 손익표에 그린다(전부 0 인 '환관련손익(모델 추정분)' 로 표를 늘리지 않는다).
NONOP_DETAIL = ("이자손익", "외환손익", "파생상품손익", "기타금융손익", "환관련손익", "기타영업외손익", "지분법손익", "중단사업이익")
SUB_ROWS = set(NONOP_DETAIL) | {"매출조선신규", "OP조선신규", "조정EPS"}          # 들여쓴 하위 행
SUB_PREFIX = "└ "                     # 신규수주·조정EPS 하위 행 머리 — 라벨 앞에만 붙인다(라벨 본문은 모델 것)
# 모델이 label 을 비웠을 때만 쓰는 짧은 표기(접두 없음). 라운드 7(2026-10-09 검증 수정): 모델 라벨이 우선 — net_panel(공시 상계)·ledger_signing_rate(원장 체결 속도)
# 문구는 kship_model.py row_labels 가 적으므로 고정 문구로 덮으면 페이지가 폴백 사슬을 숨긴다.
ROW_LABEL_KO = {"매출조선신규": "신규수주 매출(매출조선에 포함)",
                "OP조선신규": "신규수주 OP(매출조선신규 × 타겟 OPM · OP조선에 포함)",
                "조정EPS": "조정 EPS(일회성 의심 분기 세후 차감 · 모델 추정)"}
# 세율 경로(kship_model.py _tax_rate ①eff12 ②median_pos8 ③default · _tax_carryforward carryforward_ramp) → 가정 패널 설명. 값·분기표는 모델 필드만 읽는다
# (2026-10-09 검증 수정 — '3년 유효세율 5~27% 클립' 고정 문구가 이월결손 램프 회사의 각주와 모순). 모르는 경로는 tax_basis 문장 그대로.
TAX_PATH_KO = {"eff12": "최근 12분기 유효세율(5~27% 안)", "median_pos8": "최근 8분기 양(+)세전 분기 중위",
               "default": "법정세율 근사 22%(유효세율 범위 밖)", "carryforward_ramp": "이월결손 경로"}
# 조정EPS 병기 임계(원). 조정EPS 행(kship_model.py one_offs_detected 가 있는 회사만) 자체가 게이트라 스위치는 없고, 연도·분기별로 보고 EPS 와
# 이 이상 다를 때만 괄호를 그린다(같은 값 두 번 쓰기 금지 · selfcheck_models 가 같은 값으로 쌍방 검사). 2026-10-08 오너 결정.
ADJ_EPS_MIN_DIFF_WON = 0.05
# T6 D7 — `status` 는 데이터 완전성, 드라이버 폴백 사유는 `driver_fallback`(kship_model.py DRIVER_FALLBACKS). 둘을 한 칸에 섞어 읽히지 않게 따로 표기한다.
# 코드는 모델 값 그대로(정렬·grep 용), 뜻은 한글. 뜻 문장은 kship_model.py 의 채택 조건(CORR_MIN 0.30 · 단일 검정 5% · LINK_MIN_N 4 · OOS ×1.10)을 옮긴 것.
DRIVER_FALLBACK_KO = collections.OrderedDict([
    ("none", "폴백 없음"), ("oos", "OOS 기각 → 추세 폴백"), ("significance", "유의성 미달 → 추세 폴백"),
    ("n", "표본 부족 → 추세 폴백"), ("corr", "상관 미달 → 추세 폴백"), ("eligibility", "연동 자격 미달 → 추세 폴백"),
    ("no_link", "고객 연결 없음 → 추세 폴백")])
DRIVER_FALLBACK_DESC = {
    "none": "계획한 드라이버(고객 연동·선표·종속사 합산)를 그대로 채택 — 폴백 아님",
    "oos": "고객 연동 후보가 유의성은 통과했지만 동결 백테스트(freeze 2025Q2 · 4분기 매출 WAPE)에서 추세+계절성 × 1.10 보다 나빠 기각(결정 ⓘ)",
    "significance": "고객 연동 후보의 상관이 단일 검정 5% 임계 r(df=n−2) 미달",
    "n": "고객 연동 회귀 짝 수 n 이 최소치 4 미달",
    "corr": "고객 연동 후보의 최대 상관이 0.30 미달",
    "eligibility": "고객 링크가 특수관계자 매출(related) 만이고 비중 합이 5% 미달 — 격자·OOS 전에 후보 자격에서 기각(라운드 7 L5)",
    "no_link": "고객 조선사 연결(suppliers.json)·선표·종속사가 없어 매출 추세+계절성으로 추정",
}
STATUS_RULE = "status 는 데이터 완전성만 — fin ≥ 8분기 · 항등식 · 추정 ≥ 10분기 · 별도 보충 없음 · 최신 완결 분기(T6 D7). 드라이버 폴백은 driver_fallback 으로 따로"
FIN_MIN_Q, FWD_MIN_Q = 8, 10          # kship_model.py 의 status 판정 임계(fin 분기 · 추정 분기) — 사유를 되짚을 때만 쓴다

# 섹션 전용 스타일. 공용 kship.css 는 건드리지 않고 .kmodel 로 범위를 묶는다(회사 페이지 표 규칙과 충돌 금지).
SECTION_CSS = """
.kmodel th.l,.kmodel td.l{text-align:left}
.kmodel table.pnl th.rowh{text-align:left;position:sticky;left:0;z-index:2;background:var(--pn,#171a21);color:var(--tx,#e6e8ec);font-weight:500;font-size:12px}
.kmodel table.pnl td.est,.kmodel table.pnl th.est{background:rgba(251,191,36,.07);color:var(--tx2,#98a1b0)}
.kmodel table.pnl td.est{border-bottom-style:dashed}
.kmodel table.pnl tr.grp td{text-align:left;color:var(--tx3,#5d6675);font-size:10.5px;background:var(--pn2,#1e222b);padding:7px 9px 4px}
.kmodel table.pnl tr.derived td,.kmodel table.pnl tr.derived th{color:var(--tx2,#98a1b0);font-style:italic}
.kmodel .assum{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}
.kmodel .assum>div{background:var(--pn2,#1e222b);border:1px solid var(--ln,#2a2f3a);border-radius:var(--r2,7px);padding:9px 11px;font-size:12px;min-width:0}
.kmodel .assum b{display:block;font-size:14px;font-variant-numeric:tabular-nums;font-weight:600;overflow-wrap:anywhere}
.kmodel .assum span{display:block;font-size:10.5px;color:var(--tx3,#5d6675);margin-top:3px}
.kmodel .assum i{font-style:normal;font-size:11px;color:var(--tx2,#98a1b0);font-variant-numeric:tabular-nums}
.kmodel .band{position:relative;height:10px;border-radius:5px;background:var(--pn3,#242935);margin:14px 0 6px}
.kmodel .band i{position:absolute;top:0;bottom:0;background:rgba(96,165,250,.35);border-radius:5px}
.kmodel .band b{position:absolute;top:-4px;width:2px;height:18px;background:var(--wn,#fbbf24)}
.kmodel .band em{position:absolute;top:-4px;width:2px;height:18px;background:var(--up,#4ade80)}
.kmodel .bandlbl{display:flex;justify-content:space-between;font-size:10.5px;color:var(--tx3,#5d6675)}
.kmodel .disclaim{display:inline-block;font-weight:700;color:var(--wn,#fbbf24);border:1px solid rgba(251,191,36,.35);border-radius:6px;padding:3px 9px;margin:6px 0 2px}
.kmodel .fn{font-size:11px;color:var(--tx2,#98a1b0);line-height:1.8}
.kmodel .fn li{margin-left:16px}
.kmodel .kpi .est b{color:var(--tx,#e6e8ec)}
.kmodel .kpi .est{border-style:dashed}
.kmodel .dl{display:inline-flex;align-items:center;gap:8px;font-size:12px;border:1px solid var(--ln,#2a2f3a);border-radius:8px;padding:7px 12px;background:var(--pn2,#1e222b)}
.kmodel .dl.off{color:var(--tx3,#5d6675);border-style:dashed}
.kmodel table.pnl tr.sub th.rowh{padding-left:18px;color:var(--tx2,#98a1b0);font-weight:400}
.kmodel .tag{display:inline-block;font-size:10.5px;font-weight:600;color:var(--wn,#fbbf24);border:1px dashed rgba(251,191,36,.45);border-radius:999px;padding:1px 8px;margin-left:6px;vertical-align:middle;letter-spacing:0}
.kmodel .tag.off{color:var(--tx3,#5d6675);border-color:var(--ln,#2a2f3a)}
.kmodel table.scn tr.base td,.kmodel table.scn tr.base th{background:rgba(57,135,229,.08)}
.kmodel table.scn th.rowh{white-space:nowrap}
.kmodel .status{font-size:11.5px;color:var(--tx2,#98a1b0);margin:-4px 0 12px;line-height:1.7;overflow-wrap:anywhere}
.kmodel .status b{font-weight:600;margin-right:6px}
.kmodel .grid2{grid-template-columns:repeat(auto-fit,minmax(min(360px,100%),1fr))}
.kmodel .grid2>*{min-width:0}
.kmodel .wrap{overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch}
.kmodel .fn,.kmodel .assum>div,.kmodel h2 em,.kmodel .bandlbl span{overflow-wrap:anywhere}
@media(max-width:480px){.kmodel section.card{padding:12px 11px}.kmodel .assum{grid-template-columns:1fr}.kmodel .kpi{grid-template-columns:repeat(auto-fit,minmax(140px,1fr))}}
"""


# ── 숫자 표기(모델 단위는 억원·원·배·%) ─────────────────────────

def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


_NEG_ZERO = re.compile(r"^-(0(?:\.0+)?)(%|배)?$")


def _nz(s):
    """반올림 잔재 '-0.0'·'-0'·'-0.0%' 는 부호를 뗀다 — 화면에서 음수로 읽히지 않게(값 자체는 바꾸지 않는다)."""
    return _NEG_ZERO.sub(lambda m: m.group(1) + (m.group(2) or ""), s)


def fmt_a(v):
    """억원. 절대값 10 미만은 소수 1자리, 그 밖은 정수 콤마. 음수는 '-1,234'."""
    if not _num(v):
        return "—"
    return _nz(format(v, ",.1f") if abs(v) < 10 else format(round(v), ",d"))


def fmt_won(v):
    if not _num(v):
        return "—"
    return _nz(format(round(v), ",d"))


def fmt_pct(v, d=1):
    return _nz(("%%.%df%%%%" % d) % (v * 100)) if _num(v) else "—"


def fmt_pct_r4(v):
    """r4 저장 비율을 소수 손실 없이(0.0045 → 0.45% · 0.22 → 22%). basis 문장은 미반올림 값을 %.1f 로 적어 1자리로 다시 반올림하면 0.4/0.5 처럼 어긋난다."""
    return _nz(("%.2f" % (v * 100)).rstrip("0").rstrip(".") + "%") if _num(v) else "—"


def fmt_pct100(v, d=1):
    """이미 % 단위인 값(백테스트 WAPE 등)."""
    return _nz(("%%.%df%%%%" % d) % v) if _num(v) else "—"


def fmt_x(v):
    return _nz("%.1f배" % v) if _num(v) else "—"


def fmt_rate(v):
    return _nz(format(v, ",.1f")) if _num(v) else "—"


def driver_label(t):
    """드라이버 type → 한글 표기(모르는 type 은 그대로)."""
    return DRIVER_KO.get(t) or (t or "—")


def model_driver(model):
    """(type, basis). type 은 L4 최상위 driver_type, 없으면 첫 사업부 driver.type. basis 는 매출액 행 첫 추정 칸의 근거."""
    t = model.get("driver_type")
    if not t:
        t = next((s["driver"].get("type") for s in (model.get("segments") or []) if isinstance(s.get("driver"), dict) and s["driver"].get("type")), None)
    _, est = window_quarters(model)
    c = cell(row_map(model).get("매출액"), est[0]) if est else None
    return t, ((c or {}).get("basis") or None)


def _ratio(a, b):
    return (a / b) if (_num(a) and _num(b) and b) else None


def _first_driver_with(model, *keys):
    """segments[].driver 중 keys 가 하나라도 있는 첫 dict(없으면 {})."""
    for s in model.get("segments") or []:
        d = s.get("driver")
        if isinstance(d, dict) and any(k in d for k in keys):
            return d
    return {}


def new_orders_state(model):
    """(state, label, detail). state: included | excluded | n/a.
    조선사·지주만 뜻이 있다(기자재는 고객 모델을 통해 간접 반영 → n/a, 라벨 없음). 라벨은 NEW_ORDERS_LABEL — 미보정임을 항상 적는다."""
    inc = model.get("new_orders_included")
    no = model.get("new_orders") if isinstance(model.get("new_orders"), dict) else {}
    if not no:
        no = _first_driver_with(model, "new_orders").get("new_orders") or {}
    if inc is True:
        det = []
        fb = bool(no.get("fallback"))
        ledger = no.get("source_field") == "ledger_signing_rate"
        if ledger:
            lr = no.get("ledger_rate") if isinstance(no.get("ledger_rate"), dict) else {}
            ratio = lr.get("panel_to_ledger_ratio") if _num(lr.get("panel_to_ledger_ratio")) else (no.get("ledger_crosscheck") or {}).get("panel_to_ledger_ratio")
            det.append("폴백 ledger_signing_rate(패널 신규수주가 공시 체결 속도의 %s%s)"
                       % (("%.0f%%" % (ratio * 100)) if _num(ratio) else "—", (" · 원장 표본 %s분기" % lr["n_quarters_used"]) if _num(lr.get("n_quarters_used")) else ""))
        elif fb:
            det.append("폴백 %s(전범위 new_order_revenue 없음)" % (no.get("source_field") or "covered_scope_new_revenue"))
        if no.get("via"):
            det.append("종속 %s 모델 경유" % no["via"])
        if no.get("scenario_in_rows"):
            det.append("행 반영 %s" % no["scenario_in_rows"])
        if no.get("panel_status"):
            det.append("패널 status %s" % no["panel_status"])
        if no.get("panel_reason_codes"):
            det.append(", ".join(str(x) for x in no["panel_reason_codes"]))
        if _num(no.get("base_total_fq")):
            det.append("FY합 %s억" % fmt_a(no["base_total_fq"]))
        if no.get("calibrated") is False:
            det.append("calibrated=false")
        if fb and no.get("fallback_note"):
            det.append(str(no["fallback_note"]))
        return "included", (NEW_ORDERS_LEDGER_LABEL if ledger else NEW_ORDERS_FALLBACK_LABEL if fb else NEW_ORDERS_LABEL), " · ".join(det) or (no.get("note") or "")
    if inc is False:
        return "excluded", NEW_ORDERS_EXCL_LABEL, (no.get("note") or "forecast_panel 값 없음")
    return "n/a", "", ""


def oos_text(d, short=False):
    """driver.selection_oos(결정 ⓘ) → 'OOS 동결 2025Q2 · 4분기 · WAPE 연동 12.0% vs 추세 12.3% → 연동 채택'. 기록이 없으면 ""."""
    o = (d or {}).get("selection_oos")
    if not isinstance(o, dict):
        return ""
    if not (_num(o.get("wape_link")) or _num(o.get("wape_trend"))):
        # WAPE 미산출(동결 전 실적 부족 → 유의성만으로 채택, 또는 유의성 미달로 OOS 전 기각) — 빈 판정 대신 기록의 note 를 그대로
        return ("OOS 비교 불가 — " + E(str(o["note"]))) if o.get("note") else ""
    core = "WAPE 연동 %s vs 추세 %s" % (fmt_pct100(o.get("wape_link")), fmt_pct100(o.get("wape_trend")))
    verdict = "연동 채택" if o.get("adopted") else "추세 폴백(연동 미채택)"
    if short:
        return "%s → %s" % (core, verdict)
    return "OOS 동결 %s · %s분기 · %s → %s" % (E(str(o.get("freeze") or "—")), E(str(o.get("n") or o.get("horizon") or "—")), core, verdict)


def model_oos(model, short=False):
    """첫 사업부 드라이버의 OOS 선택 결과(없으면 "")."""
    return oos_text(_first_driver_with(model, "selection_oos"), short=short)


def driver_fallback_info(model):
    """(code, 한글 뜻, 상세) — T6 D7 `driver_fallback`. 상세는 기각 블록(customer_link_rejected)의 상관·n·WAPE 를 붙인다.
    필드가 없거나 모르는 코드면(구버전·모의 모델) customer_link_rejected.rejected_by 라는 명시적 증거로만 판정하고, 그것도 없으면 (None, "", "") —
    드라이버 type 에서 사유를 추정하지 않는다(추세 폴백이라도 '왜' 는 모델만 안다)."""
    code = model.get("driver_fallback")
    rj = _first_driver_with(model, "customer_link_rejected").get("customer_link_rejected")
    rj = rj if isinstance(rj, dict) else {}
    if code not in DRIVER_FALLBACK_KO:
        code = rj.get("rejected_by") if rj.get("rejected_by") in DRIVER_FALLBACK_KO else None
    if not code:
        return None, "", ""
    det = [DRIVER_FALLBACK_DESC[code]]
    if code in ("corr", "significance", "n", "oos") and rj:
        if _num(rj.get("corr")):
            rc = (rj.get("significance") or {}).get("r_crit_p05_two_sided") if isinstance(rj.get("significance"), dict) else None
            det.append("상관 %.2f" % rj["corr"] + ((" (임계 r %.2f)" % rc) if (code == "significance" and _num(rc)) else ""))
        if _num(rj.get("n")):
            det.append("n=%d" % rj["n"])
        o = oos_text(rj, short=True)
        if o:
            det.append(o)
        if rj.get("note"):
            det.append(str(rj["note"]))
    elif code == "eligibility":
        el = rj.get("eligibility") if isinstance(rj.get("eligibility"), dict) else {}
        if el.get("reason"):
            det.append(str(el["reason"]))
    elif code == "no_link":
        d = _first_driver_with(model, "type")
        if d.get("basis"):
            det.append(str(d["basis"]))
    return code, DRIVER_FALLBACK_KO[code], " · ".join(det)


def status_reasons(model):
    """partial 사유 — kship_model.py 의 status 규칙(T6 D7)을 quality 필드로 되짚는다(모델은 사유를 따로 적지 않는다).
    fin < 8분기 · 항등식 불일치 · 추정 매출 < 10분기 · 별도 보충(sep_filled) · 누락 · 최신 완결 분기 미수집/합병 경고. 전부 통과면 []."""
    q = model.get("quality") or {}
    rs = []
    n = q.get("fin_quarters")
    if _num(n) and n < FIN_MIN_Q:
        rs.append("fin %d분기(< %d)" % (n, FIN_MIN_Q))
    if q.get("identities_ok") is False:
        rs.append("항등식 불일치")
    la = (model.get("periods") or {}).get("last_actual") or model.get("origin")
    rev = row_map(model).get("매출액")
    if rev and la:
        n_est = sum(1 for k in ((model.get("periods") or {}).get("quarters") or []) if k > la and cell(rev, k))
        if n_est < FWD_MIN_Q:
            rs.append("추정 매출 %d분기(< %d)" % (n_est, FWD_MIN_Q))
    sf = sorted(str(x) for x in (q.get("sep_filled") or []))
    if sf:
        rs.append("별도 보충 %d분기(%s~%s)" % (len(sf), sf[0], sf[-1]))
    if q.get("missing"):
        rs.append("누락 %d건: %s" % (len(q["missing"]), ", ".join(str(x) for x in q["missing"][:4])))
    rs += [str(w) for w in (q.get("warnings") or []) if ("최신 완결 분기" in str(w) or "합병" in str(w))]
    return rs


def status_line(model):
    """섹션 상단 한 줄 — 모델 상태 full/partial 과 그 사유(데이터 완전성), 그리고 드라이버 폴백(별도). 사유를 되짚을 수 없으면 '미기재' 라고 쓴다."""
    s = model_summary(model)
    st = s["status"] or "—"
    q = model.get("quality") or {}
    la = (model.get("periods") or {}).get("last_actual") or model.get("origin") or "—"
    cls = {"full": "up", "partial": "wn", "no_fin": "dn"}.get(st, "tx3")
    if st == "partial":
        why = "사유: " + " · ".join(E(x) for x in (status_reasons(model) or ["미기재 — quality.warnings 참조"]))
    elif st == "full":
        fq, idok = q.get("fin_quarters"), q.get("identities_ok")
        why = "데이터 완전 — fin %s분기 · 항등식 %s · 최신 분기 %s" % (("%d" % fq) if _num(fq) else "—",
                                                               "OK" if idok else ("미검사" if idok is None else "불일치"), E(str(la)))
    else:
        why = E(" · ".join(str(w) for w in (q.get("warnings") or [])[:2]) or "재무 없음")
    code, lab, det = driver_fallback_info(model)
    fb = (' · <span title="%s">드라이버 폴백 %s — %s</span>' % (E(det), E(code), E(lab))) if code else ""
    return '<p class="status"><b class="%s" title="%s">모델 상태 %s(%s)</b>%s%s</p>' % (cls, E(STATUS_RULE), E(STATUS_KO.get(st, st)), E(st), why, fb)


def sls_mode_info(model, sls):
    """코호트 모드(결정 ⓔ)·잔고 캡 — sls 가 정본, 없으면 모델 driver 에 복사된 sls_cohort_mode·backlog_cap_applied."""
    d = _first_driver_with(model, "sls_cohort_mode", "backlog_cap_applied", "target_opm_alt_median")
    s = sls if isinstance(sls, dict) else {}
    cap = s.get("backlog_cap") if isinstance(s.get("backlog_cap"), dict) else {}
    if "applied" in cap:
        applied = cap.get("applied")
    elif "backlog_cap_applied" in s:
        applied = s.get("backlog_cap_applied")
    else:
        applied = d.get("backlog_cap_applied")
    return {"mode": s.get("cohort_mode") or d.get("sls_cohort_mode"), "alt": s.get("cohort_mode_alt"),
            "cap_applied": applied if isinstance(applied, bool) else None, "cap": cap,
            "calibrated_shift": (s.get("calibration") or {}).get("calibrated_shift", d.get("calibrated_shift")),
            "calibrated_shift_alt": (s.get("calibration_alt") or {}).get("calibrated_shift"),
            "target_opm_alt_median": d.get("target_opm_alt_median")}


def _shift_txt(v):
    return ("%+.1f%%p" % (v * 100)) if _num(v) else "—"


def cohort_mode_text(info):
    """'reference_anchor(레퍼런스 앵커(수주연도→등급)) 기본 · 대안 ledger_relative(원장 상대등급) · 캘리브레이션 shift 기본 −5.3%p / 대안 +3.6%p'."""
    if not info.get("mode"):
        return ""
    parts = ["%s(%s) 기본" % (info["mode"], COHORT_MODE_KO.get(info["mode"], "모드 설명 없음"))]
    if info.get("alt"):
        alt = "대안 %s(%s)" % (info["alt"], COHORT_MODE_KO.get(info["alt"], "모드 설명 없음"))
        if _num(info.get("target_opm_alt_median")):
            alt += " 타겟 OPM 중위 %s" % fmt_pct(info["target_opm_alt_median"])
        parts.append(alt)
    if _num(info.get("calibrated_shift")) or _num(info.get("calibrated_shift_alt")):
        parts.append("캘리브레이션 shift 기본 %s / 대안 %s" % (_shift_txt(info.get("calibrated_shift")), _shift_txt(info.get("calibrated_shift_alt"))))
    return " · ".join(parts)


def backlog_cap_text(info):
    """잔고 캡(§5-2): '적용 ×0.859(원장 잔여/공시 해양 잔고 1.16 → 1.00 · 원값 보존)' | '미적용(원장 잔여/공시 해양 잔고 0.62)' | ''."""
    ap = info.get("cap_applied")
    if ap is None:
        return ""
    cap = info.get("cap") or {}
    cov = cap.get("coverage_at_origin")
    if ap:
        return "적용 ×%s(원장 잔여/공시 해양 잔고 %s → 1.00 · 원값 *_raw 보존)" % (
            ("%.3f" % cap["factor"]) if _num(cap.get("factor")) else "—", ("%.2f" % cov) if _num(cov) else "—")
    return "미적용" + ((" (원장 잔여/공시 해양 잔고 %.2f)" % cov) if _num(cov) else "")


def _is_est(kind):
    return kind in ("estimate", "mixed")


# ── 모델 접근자 ─────────────────────────────────────────────

def row_map(model):
    return {r["key"]: r for r in model.get("rows", [])}


def cell(row, q, kind="q"):
    """row[kind][q] → dict | None. 값이 숫자가 아니면 None(0 으로 바꾸지 않는다)."""
    if not row:
        return None
    c = (row.get(kind) or {}).get(q)
    return c if isinstance(c, dict) and _num(c.get("v")) else None


def window_quarters(model):
    """최근 8A + 10E. 모델의 periods.quarters 와 last_actual 로 자른다."""
    qs = list((model.get("periods") or {}).get("quarters") or [])
    la = (model.get("periods") or {}).get("last_actual") or model.get("origin")
    act = [q for q in qs if la and q <= la]
    est = [q for q in qs if not la or q > la]
    return act[-N_ACTUAL:], est[:N_EST]


def adj_differs(eps, eps_adj):
    """조정EPS 를 병기할 분기/연도인가 — 둘 다 숫자이고 차이가 ADJ_EPS_MIN_DIFF_WON 을 넘을 때만(같은 값을 두 번 쓰지 않는다)."""
    return bool(_num(eps) and _num(eps_adj) and abs(eps_adj - eps) > ADJ_EPS_MIN_DIFF_WON)


def ttm_per(model):
    """모델 TTM PER(보고·조정) — 마지막 4실적분기 Σ EPS·Σ 조정EPS 로 종가(valuation.price.close)를 나눈다.
    조정EPS 행이 없거나 4분기 셀이 모자라면 None. Σ ≤ 0 또는 종가 없음이면 per 는 None('—' — valuation.per_now 가 None 일 때와 같은 표기).
    외부 TTM(prices.json pe_ttm, aik 순이익 기준)과 출처를 섞지 않도록 따로 적는 값이다."""
    rm = row_map(model)
    if "조정EPS" not in rm or "EPS" not in rm:
        return None
    qs = list((model.get("periods") or {}).get("quarters") or [])
    la = (model.get("periods") or {}).get("last_actual") or model.get("origin")
    last4 = [q for q in qs if la and q <= la][-4:]
    cells = [(cell(rm["EPS"], q), cell(rm["조정EPS"], q)) for q in last4]
    if len(last4) < 4 or any(a is None or b is None for a, b in cells):
        return None
    eps_ttm, adj_ttm = sum(a["v"] for a, _ in cells), sum(b["v"] for _, b in cells)
    close = ((model.get("valuation") or {}).get("price") or {}).get("close")
    per = lambda s: (close / s) if (_num(close) and s > 0) else None     # noqa: E731
    return {"eps_ttm": eps_ttm, "eps_ttm_adj": adj_ttm, "per_ttm": per(eps_ttm), "per_ttm_adj": per(adj_ttm), "quarters": last4}


def model_summary(model):
    """허브 표·KPI 스트립 공용: FY별 매출/OP/OPM/EPS(+조정EPS)/PER/PBR + 현재 PER/PBR + status."""
    rm = row_map(model)
    out = {"fy": {}, "per_now": (model.get("valuation") or {}).get("per_now"),
           "pbr_now": (model.get("valuation") or {}).get("pbr_now"),
           "status": (model.get("quality") or {}).get("status") or model.get("status")}
    for y in ("2025",) + FY_EST:
        rev, op, eps = cell(rm.get("매출액"), y, "a"), cell(rm.get("영업이익"), y, "a"), cell(rm.get("EPS"), y, "a")
        per, pbr, adj = cell(rm.get("PER"), y, "a"), cell(rm.get("PBR"), y, "a"), cell(rm.get("조정EPS"), y, "a")
        out["fy"][y] = {"rev": rev["v"] if rev else None, "op": op["v"] if op else None,
                        "opm": _ratio(op["v"] if op else None, rev["v"] if rev else None),
                        "eps": eps["v"] if eps else None, "eps_adj": adj["v"] if adj else None,
                        "per": per["v"] if per else None, "pbr": pbr["v"] if pbr else None,
                        "kind": (rev or op or eps or {}).get("kind")}
    if not out["status"]:
        q = model.get("quality") or {}
        n = q.get("fin_quarters")
        out["status"] = "no_fin" if n == 0 else ("partial" if (q.get("missing") or not q.get("identities_ok", True)) else "full")
    out["new_orders"] = new_orders_state(model)[0]
    # 시나리오 FY 매출 범위(보수·낙관) — 허브 표 툴팁용. base 는 행과 같으므로 rev 그대로.
    sc = model.get("scenarios") if isinstance(model.get("scenarios"), dict) else {}
    out["scn"] = {}
    for y in FY_EST:
        lo = ((sc.get("conservative") or {}).get("annual") or {}).get(y) or {}
        hi = ((sc.get("optimistic") or {}).get("annual") or {}).get(y) or {}
        if _num(lo.get("rev")) or _num(hi.get("rev")):
            out["scn"][y] = {"cons": lo.get("rev"), "opt": hi.get("rev")}
    return out


# ── ① KPI 스트립 ────────────────────────────────────────────

def _kpi_strip(model, price):
    s = model_summary(model)
    tiles = []
    for y in FY_EST:
        f = s["fy"][y]
        # 조정EPS 병기 — 보고 EPS 가 1차 값, 조정은 괄호(일회성 의심 분기 세후 차감 · 모델 추정). 같은 값이면 괄호 없음.
        adj = (" (조정 %s원)" % fmt_won(f["eps_adj"])) if adj_differs(f["eps"], f["eps_adj"]) else ""
        tiles.append('<div class="est"><b>%s<small>억</small></b><span>FY%sE 매출 · %s</span>'
                     '<i>OP %s억 · OPM %s · EPS %s원%s</i></div>'
                     % (fmt_a(f["rev"]), E(y), "추정" if _is_est(f["kind"]) or f["kind"] is None else "실적",
                        fmt_a(f["op"]), fmt_pct(f["opm"]), fmt_won(f["eps"]), adj))
    v = model.get("valuation") or {}
    close = (v.get("price") or {}).get("close")
    as_of = (v.get("price") or {}).get("as_of") or ""
    ttm = ""
    if isinstance(price, dict) and (_num(price.get("pe_ttm")) or _num(price.get("pb"))):
        ttm = "TTM %s / %s(aikstockdata)" % (fmt_x(price.get("pe_ttm")), fmt_x(price.get("pb")))
    sub = E(ttm) if ttm else "종가 %s원 · %s" % (fmt_won(close), E(as_of))
    tp, per_title = ttm_per(model), ""
    if tp:
        # 모델 TTM PER(종가 ÷ Σ 마지막 4실적분기 EPS) — 외부 aik TTM(순이익 기준) 옆에 출처를 섞지 않고 따로. 조정은 Σ 가 다를 때만 괄호.
        sub += " · 모델 TTM PER %s%s" % (fmt_x(tp["per_ttm"]), (" (조정 %s)" % fmt_x(tp["per_ttm_adj"])) if adj_differs(tp["eps_ttm"], tp["eps_ttm_adj"]) else "")
        per_title = ' title="%s"' % E("모델 TTM PER = 종가 %s원 ÷ Σ EPS(%s~%s) %s원 · 조정 Σ %s원(일회성 의심 분기 세후 차감 · 모델 추정) · Σ ≤ 0 이면 — · aik TTM 은 외부값(기준 다름)"
                                      % (fmt_won(close), tp["quarters"][0], tp["quarters"][-1], fmt_won(tp["eps_ttm"]), fmt_won(tp["eps_ttm_adj"])))
    tiles.append('<div%s><b>%s</b><span>현재 PER(12M fwd EPS %s원)</span><i>%s</i></div>'
                 % (per_title, fmt_x(s["per_now"]), fmt_won(v.get("eps_fwd12m")), sub))
    tiles.append('<div><b>%s</b><span>현재 PBR(최근 BPS %s원)</span><i>%s</i></div>'
                 % (fmt_x(s["pbr_now"]), fmt_won(v.get("bps_latest")), "종가 %s원 · %s" % (fmt_won(close), E(as_of))))
    state, no_label, no_detail = new_orders_state(model)
    tag = ('<span class="tag%s" title="%s">%s</span>' % ("" if state == "included" else " off", E(no_detail), E(no_label))) if no_label else ""
    return ('<section class="card"><h2>실적 모델 KPI <em>FY2026E~28E · 억원 · 점선 칸은 추정 · 기준 %s · %s</em>%s</h2>'
            '<div class="kpi">%s</div></section>' % (E(model.get("origin") or "—"), E(DISCLAIMER), tag, "".join(tiles)))


# ── ② 분기 손익표 ───────────────────────────────────────────

# 손익 행 순서. 영업외 세부(NONOP_DETAIL)는 금융손익 뒤·세전이익 앞에 두고, 값이 있을 때만 그린다.
# 금융손익 아래 세부 4행(이자·외환·파생·기타금융 — T4, 합 = 금융손익)은 실적 분기만 값이 있고, 환관련손익(조선사 공시 노출 × Δ환율 추정)과는 별개다.
PNL_ORDER = ["매출액", "매출원가", "매출총이익", "판관비", "영업이익", "OPM", "EBITDA", "금융손익", "이자손익", "외환손익", "파생상품손익", "기타금융손익",
             "환관련손익", "기타영업외손익", "지분법손익", "세전이익", "법인세비용", "당기순이익", "중단사업이익", "지배주주순이익", "EPS", "조정EPS", "BPS"]


def _derived_opm_row(rm):
    rev, op = rm.get("매출액"), rm.get("영업이익")
    if not rev or not op:
        return None
    q = {}
    for k in (rev.get("q") or {}):
        a, b = cell(rev, k), cell(op, k)
        if a and b and a["v"]:
            kind = "estimate" if _is_est(a["kind"]) or _is_est(b["kind"]) else "actual"
            q[k] = {"v": b["v"] / a["v"], "kind": kind, "basis": "영업이익 ÷ 매출액(파생)", "src": "derived"}
    return {"key": "OPM", "label": "영업이익률", "group": "손익", "unit": "%", "q": q, "a": {}, "_derived": True}


def _pnl_table(model):
    rm = row_map(model)
    act, est = window_quarters(model)
    cols = act + est
    if "OPM" not in rm:
        d = _derived_opm_row(rm)
        if d:
            rm["OPM"] = d
    # 손익 → 사업부 → 주당 순. 모델 순서를 유지하되 손익은 PNL_ORDER 로 정렬한다.
    groups = collections.OrderedDict()
    for key in PNL_ORDER:
        if key in rm:
            groups.setdefault(rm[key].get("group") or "손익", []).append(rm[key])
    for r in model.get("rows", []):
        if r["key"] in PNL_ORDER or r["key"] in ("PER", "PBR"):
            continue
        groups.setdefault(r.get("group") or "기타", []).append(r)
    head = ['<th class="l rowh">항목</th><th class="l">단위</th>']
    for q in cols:
        e = q in est
        head.append('<th%s>%s<br>%s</th>' % (' class="est"' if e else "", E(q), "E" if e else "A"))
    body = []
    for g, rows in groups.items():
        body.append('<tr class="grp"><td colspan="%d">%s</td></tr>' % (len(cols) + 2, E(g)))
        for r in rows:
            key = r["key"]
            if key in NONOP_DETAIL and not any(abs(c["v"]) >= 0.05 for c in (cell(r, q) for q in cols) if c):
                continue          # 영업외 세부 행은 값이 있을 때만 — 전부 0·빈 칸이면 표를 늘리지 않는다
            unit = r.get("unit") or ""
            tds = []
            for q in cols:
                c = cell(r, q)
                if not c:
                    tds.append('<td class="mut%s">—</td>' % (" est" if q in est else ""))
                    continue
                e = _is_est(c.get("kind"))
                v = fmt_pct(c["v"]) if unit == "%" else (fmt_won(c["v"]) if unit in ("원",) else fmt_a(c["v"]))
                tip = ("추정 · " + (c.get("basis") or "basis 미기재")) if e else ("실적 · " + (c.get("src") or "출처 미기재"))
                tds.append('<td%s title="%s">%s</td>' % (' class="est"' if e else "", E(tip), v))
            cls = " ".join(x for x in ("derived" if r.get("_derived") else "", "sub" if key in SUB_ROWS else "") if x)
            full = r.get("label") or key
            label = (SUB_PREFIX + (r.get("label") or ROW_LABEL_KO[key])) if key in ROW_LABEL_KO else full
            body.append('<tr%s><th class="rowh" scope="row"%s>%s</th><td class="l mut">%s</td>%s</tr>'
                        % ((' class="%s"' % cls) if cls else "", (' title="%s"' % E(full)) if label != full else "", E(label), E(unit), "".join(tds)))
    return ('<section class="card"><h2>분기 손익 <em>최근 %d분기 실적(A) + %d분기 추정(E) · 억원(EPS·BPS 원) · 추정 칸은 음영, 칸에 마우스를 올리면 근거</em></h2>'
            '<div class="wrap"><table class="pnl"><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div></section>'
            % (len(act), len(est), "".join(head), "".join(body)))


# ── 차트 공용(지연 로드) ────────────────────────────────────

def _chart_script(uid, payload, draw_js, depth):
    """Chart.js 가 이미 있으면 바로, 없으면 vendor 를 한 번 지연 로드한 뒤 그린다. 전역을 만들지 않는다."""
    src = "../" * depth + "vendor/chart.umd.min.js"
    return ('<script>(function(){var D=%s;var SRC=%s;'
            'function defaults(){%s}'
            'function rgba(h,a){var n=parseInt(h.slice(1),16);return "rgba("+(n>>16&255)+","+(n>>8&255)+","+(n&255)+","+a+")";}'
            'function draw(){%s}'
            'function go(){try{defaults();draw();}catch(e){if(window.console)console.warn("%s",e);}}'
            'if(window.Chart){go();}else{var s=document.createElement("script");s.src=SRC;s.onload=go;document.head.appendChild(s);}'
            '})();</script>' % (json_for_html(payload), json.dumps(src), CHART_DEFAULTS_JS, draw_js, uid))


# ── ③ 사업부 매출·OPM 차트 ─────────────────────────────────

def _segment_chart(model, uid, depth):
    rm = row_map(model)
    act, est = window_quarters(model)
    cols = act + est
    segs = []
    for i, s in enumerate(model.get("segments") or []):
        rev, op = rm.get("매출" + s["key"]), rm.get("OP" + s["key"])
        if not rev:
            continue
        r = [cell(rev, q) for q in cols]
        o = [cell(op, q) for q in cols]
        segs.append({"label": s.get("label") or s["key"], "color": SEG_COLORS[i % len(SEG_COLORS)],
                     "rev": [round(c["v"]) if c else None for c in r],
                     "opm": [round(_ratio(b["v"], a["v"]) * 100, 2) if (a and b and a["v"]) else None for a, b in zip(r, o)]})
    dtype, dbasis = model_driver(model)
    fallback = False
    if not segs:
        # 부문 분리가 없는 회사(기자재 대부분) — 연결 매출·OPM 한 계열로 그린다. 빈 카드보다 낫고, 드라이버(폴백 여부)를 여기서 밝힌다.
        rev, op = rm.get("매출액"), rm.get("영업이익")
        if not rev:
            return ""
        r = [cell(rev, q) for q in cols]
        o = [cell(op, q) for q in cols]
        segs.append({"label": "연결 매출", "color": SEG_COLORS[0],
                     "rev": [round(c["v"]) if c else None for c in r],
                     "opm": [round(_ratio(b["v"], a["v"]) * 100, 2) if (a and b and a["v"]) else None for a, b in zip(r, o)]})
        fallback = True
    payload = {"labels": cols, "est": [q in est for q in cols], "segs": segs}
    draw = (
        'var el=document.getElementById("%s");if(!el)return;'
        'var ds=[];D.segs.forEach(function(s){ds.push({type:"bar",label:s.label+" 매출(억)",stack:"rev",yAxisID:"y",data:s.rev,'
        'backgroundColor:D.est.map(function(e){return rgba(s.color,e?0.45:0.9)})});});'
        'D.segs.forEach(function(s){ds.push({type:"line",label:s.label+" OPM(%%)",yAxisID:"y2",data:s.opm,borderColor:s.color,'
        'pointRadius:2,segment:{borderDash:function(c){return D.est[c.p1DataIndex]?[4,3]:undefined}}});});'
        'new Chart(el,{data:{labels:D.labels.map(function(q,i){return q+(D.est[i]?"E":"")}),datasets:ds},'
        'options:{responsive:true,maintainAspectRatio:false,scales:{x:{stacked:true,grid:{display:false}},y:{stacked:true,ticks:{callback:function(v){return v.toLocaleString()}}},'
        'y2:{position:"right",grid:{drawOnChartArea:false},ticks:{callback:function(v){return v+"%%"}}}},'
        'plugins:{tooltip:{callbacks:{label:function(c){return c.dataset.label+": "+(c.parsed.y==null?"—":c.parsed.y.toLocaleString())+(D.est[c.dataIndex]?" (추정)":"")}}}}}});'
        % (uid + "-seg"))
    oos = model_oos(model)
    drivers = '<li><b>매출 드라이버</b> — %s%s%s</li>' % (E(driver_label(dtype)), (" · " + oos) if oos else "", (" · " + E(dbasis)) if dbasis else "")
    drivers += "".join('<li><b>%s</b> — %s</li>' % (E(s.get("label") or s["key"]), E(_driver_text(s.get("driver") or {})))
                       for s in model.get("segments") or [])
    if fallback:
        title = ('매출·영업이익률 <em>부문 분리 없음(연결 한 계열) · 막대 = 매출(억, 추정 구간은 옅게) · 선 = OPM(%%, 추정 구간은 점선) · 드라이버 %s</em>'
                 % E(driver_label(dtype)))
    else:
        title = '사업부 매출·영업이익률 <em>막대 = 부문 매출(억, 추정 구간은 옅게) · 선 = 부문 OPM(%, 추정 구간은 점선)</em>'
    return ('<section class="card"><h2>%s</h2>'
            '<div class="chart tall"><canvas id="%s"></canvas></div><ul class="fn" style="margin-top:8px">%s</ul>%s</section>'
            % (title, uid + "-seg", drivers, _chart_script(uid + "-seg", payload, draw, depth)))


def _driver_text(d):
    t = d.get("type") or "—"
    parts = [("%s(%s)" % (driver_label(t), t)) if t in DRIVER_KO else t]
    if d.get("weights"):
        parts.append("고객 비중 " + ", ".join("%s %s" % (k, fmt_pct(v, 0)) for k, v in sorted(d["weights"].items())))
    if d.get("lag_q") is not None:
        parts.append("시차 %s분기" % d["lag_q"])
    if _num(d.get("ratio_used")):
        parts.append("비례계수 %.4f" % d["ratio_used"])
    if _num(d.get("reconcile_ratio")):
        parts.append("화해 비율 %.2f" % d["reconcile_ratio"])
    oos = oos_text(d, short=True)
    if oos:
        parts.append("OOS " + oos)
    if d.get("basis"):
        parts.append(d["basis"])
    return " · ".join(parts)


# ── ④ 조선사: 선표 매출인식·코호트 비중 ─────────────────────

def _sls_charts(model, sls, uid, depth):
    if (model.get("role") or "") not in ("yard", "holding"):
        return ""
    if not isinstance(sls, dict) or not sls.get("by_quarter"):
        return ('<section class="card"><h2>선표 매출인식 <em>척당 계약 → 분기 인도 매출(백만$) → 헤지 적용 원화</em></h2>'
                '<p class="mut">선표 데이터(assets/sls/%s.json)가 아직 없습니다 — 계약 원장 기반 스케줄이 생성되면 여기 그려집니다.</p></section>'
                % E(model.get("stock") or ""))
    bq = sls["by_quarter"]
    qs = sorted(bq)
    # 모델 지평(최근 8A ~ 10E)에 맞춰 자른다 — 선표 원장은 2030 이후까지 뻗지만 손익표와 같은 축이어야 읽힌다.
    act, est = window_quarters(model)
    if act or est:
        lo, hi = (act or est)[0], (est or act)[-1]
        qs = [q for q in qs if lo <= q <= hi] or qs
    la = (model.get("periods") or {}).get("last_actual") or sls.get("origin")
    est = [(bq[q].get("kind") == "estimate") if bq[q].get("kind") else (bool(la) and q > la) for q in qs]
    usd = [bq[q].get("usd_m") if _num(bq[q].get("usd_m")) else None for q in qs]
    krw = [round(bq[q]["hedged_krw_m"] / 100) if _num(bq[q].get("hedged_krw_m")) else None for q in qs]
    rate = [bq[q].get("applied_rate") if _num(bq[q].get("applied_rate")) else None for q in qs]
    cohorts = []
    for c in COHORT_ORDER:
        vals = []
        for q in qs:
            bc = bq[q].get("by_cohort") or {}
            tot = sum(v for v in bc.values() if _num(v))
            vals.append(round(bc[c] / tot * 100, 1) if (_num(bc.get(c)) and tot) else None)
        if any(v is not None for v in vals):
            cohorts.append({"label": c, "color": COHORT_COLORS[c], "share": vals})
    topm = sls.get("target_opm") or {}
    opm = [round(topm[q]["opm"] * 100, 2) if (q in topm and _num(topm[q].get("opm"))) else None for q in qs]
    info = sls_mode_info(model, sls)
    # 대안 코호트 모드(§5-2 결정 ⓔ): 타겟 OPM 을 회색 점선으로 함께, 코호트 비중은 툴팁에 글로
    talt = sls.get("target_opm_alt") or {}
    opm_alt = [round(talt[q]["opm"] * 100, 2) if (q in talt and _num(talt[q].get("opm"))) else None for q in qs]
    alt_mix = []
    for q in qs:
        bc = bq[q].get("by_cohort_alt") or {}
        tot = sum(v for v in bc.values() if _num(v))
        alt_mix.append(" · ".join("%s %d%%" % (c, round(bc[c] / tot * 100)) for c in COHORT_ORDER if _num(bc.get(c)) and tot) if tot else "")
    has_alt = any(v is not None for v in opm_alt)
    payload = {"labels": qs, "est": est, "usd": usd, "krw": krw, "rate": rate, "cohorts": cohorts, "opm": opm,
               "opm_alt": opm_alt if has_alt else None, "alt_label": "타겟 OPM 대안 %s(%%)" % (info.get("alt") or "—"),
               "alt_mix": alt_mix if has_alt else None, "mode": info.get("mode") or ""}
    draw = (
        'var a=document.getElementById("%s"),b=document.getElementById("%s");'
        'if(a){new Chart(a,{data:{labels:D.labels.map(function(q,i){return q+(D.est[i]?"E":"")}),datasets:['
        '{type:"bar",label:"선표 매출(백만$)",yAxisID:"y",data:D.usd,backgroundColor:D.est.map(function(e){return rgba("#3987e5",e?0.45:0.9)})},'
        '{type:"line",label:"헤지 적용 원화(억)",yAxisID:"y2",data:D.krw,borderColor:"#c98500",pointRadius:2,segment:{borderDash:function(c){return D.est[c.p1DataIndex]?[4,3]:undefined}}}]},'
        'options:{responsive:true,maintainAspectRatio:false,scales:{x:{grid:{display:false}},y:{ticks:{callback:function(v){return v.toLocaleString()}}},y2:{position:"right",grid:{drawOnChartArea:false},ticks:{callback:function(v){return v.toLocaleString()}}}},'
        'plugins:{tooltip:{callbacks:{afterBody:function(items){var i=items[0].dataIndex;return "적용환율 "+(D.rate[i]==null?"—":D.rate[i].toLocaleString())+(D.est[i]?" (추정)":"")}}}}}});}'
        'if(b){var ds=D.cohorts.map(function(c){return {type:"bar",label:c.label,stack:"c",yAxisID:"y",data:c.share,backgroundColor:D.est.map(function(e){return rgba(c.color,e?0.45:0.9)})}});'
        'ds.push({type:"line",label:"타겟 OPM(%%)"+(D.mode?" · "+D.mode:""),yAxisID:"y2",data:D.opm,borderColor:"#e6e8ec",pointRadius:2,segment:{borderDash:function(c){return D.est[c.p1DataIndex]?[4,3]:undefined}}});'
        'if(D.opm_alt){ds.push({type:"line",label:D.alt_label,yAxisID:"y2",data:D.opm_alt,borderColor:"#98a1b0",borderDash:[2,3],pointRadius:0,borderWidth:1.5});}'
        'new Chart(b,{data:{labels:D.labels.map(function(q,i){return q+(D.est[i]?"E":"")}),datasets:ds},'
        'options:{responsive:true,maintainAspectRatio:false,scales:{x:{stacked:true,grid:{display:false}},y:{stacked:true,max:100,ticks:{callback:function(v){return v+"%%"}}},y2:{position:"right",grid:{drawOnChartArea:false},ticks:{callback:function(v){return v+"%%"}}}},'
        'plugins:{tooltip:{callbacks:{label:function(c){return c.dataset.label+": "+(c.parsed.y==null?"—":c.parsed.y)+"%%"},'
        'afterBody:function(items){if(!D.alt_mix)return;var t=D.alt_mix[items[0].dataIndex];return t?"대안 모드 비중: "+t:undefined}}}}}});}'
        % (uid + "-sls", uid + "-coh"))
    first_est = next((q for q, e in zip(qs, est) if e), None)
    h = bq.get(first_est) or {}
    rec = sls.get("reconcile") or {}
    rec_last = rec[sorted(rec)[-1]] if rec else None
    note = ('<p class="fn" style="margin-top:8px">헤지 %s(헤지환율 %s) + 미헤지 %s(가정 현물 %s) → 적용환율 %s(%s). '
            '화해 비율 %s — %s %s.</p>'
            % (fmt_pct(h.get("hedge_ratio"), 0), fmt_rate(h.get("hedge_rate")),
               fmt_pct((1 - h["hedge_ratio"]) if _num(h.get("hedge_ratio")) else None, 0), fmt_rate(h.get("spot_assumed")),
               fmt_rate(h.get("applied_rate")), E(first_est or "—"),
               ("%.2f" % rec_last["ratio"]) if (rec_last and _num(rec_last.get("ratio"))) else "—",
               E((rec_last or {}).get("note") or "화해 기록 없음") + ".", E(opm_table_text(sls))))
    # 코호트 모드·잔고 캡(라운드 3) — sls 에 기록이 있을 때만 적는다(모의·구버전 sls 는 문장 없음)
    mode_txt, cap_txt = cohort_mode_text(info), backlog_cap_text(info)
    if mode_txt or cap_txt:
        note += ('<p class="fn" style="margin-top:4px">%s%s</p>' % (
            ('<b>코호트 모드</b> %s. ' % E(mode_txt)) if mode_txt else "",
            ('<b>선표 잔고 캡</b> %s.' % E(cap_txt)) if cap_txt else ""))
    return ('<section class="card"><h2>선표 매출인식 · 수주업황 코호트 <em>척당 계약 → 분기 인도 매출(백만$) → 헤지 적용 원화 · 코호트 비중(%%) → 타겟 OPM%s</em></h2>'
            '<div class="grid2"><div class="chart"><canvas id="%s"></canvas></div><div class="chart"><canvas id="%s"></canvas></div></div>%s%s</section>'
            % ((" · 코호트 모드 " + E(info["mode"])) if info.get("mode") else "", uid + "-sls", uid + "-coh", note, _chart_script(uid + "-sls", payload, draw, depth)))


# ── ④' 신규수주 시나리오(결정 ⓓ) ────────────────────────────────

def _scenario_card(model, uid, depth):
    """model.scenarios {meta, existing_only, conservative, base, optimistic} → FY 매출 막대 + 매출·OP·신규매출 표.
    base 만 손익표 행에 반영돼 있고 보수/낙관은 합산하지 않는다 — 카드 제목·각주에 그대로 적는다. 블록이 없으면 카드 없음."""
    sc = model.get("scenarios")
    if not isinstance(sc, dict):
        return ""
    meta = sc.get("meta") if isinstance(sc.get("meta"), dict) else {}
    cases = [c for c in (meta.get("cases") or list(SCENARIO_KO)) if isinstance(sc.get(c), dict) and isinstance(sc[c].get("annual"), dict)]
    years = [y for y in (meta.get("fiscal_years") or FY_EST) if any(y in sc[c]["annual"] for c in cases)]
    if not cases or not years:
        return ""
    state, no_label, no_detail = new_orders_state(model)
    tag = ('<span class="tag%s" title="%s">%s</span>' % ("" if state == "included" else " off", E(no_detail), E(no_label))) if no_label else ""
    head = ['<th class="l rowh">시나리오</th>'] + ["".join('<th class="est">FY%sE<br>%s</th>' % (E(y[2:]), t) for t in ("매출(억)", "OP(억)", "신규 매출(억)")) for y in years]
    trs, series = [], []
    for c in cases:
        ann = sc[c]["annual"]
        in_rows = bool(sc[c].get("in_rows")) or c == meta.get("in_rows")
        name = SCENARIO_KO.get(c, c) + ('<span class="pill">손익표 반영</span>' if in_rows else "")
        tds = []
        for y in years:
            a = ann.get(y) or {}
            for k in ("rev", "op", "new_order_revenue"):
                v = a.get(k)
                tds.append('<td class="est%s" title="%s">%s</td>' % ("" if _num(v) else " mut", E("%s · %s · kind %s" % (SCENARIO_KO.get(c, c), y, a.get("kind") or "estimate")), fmt_a(v)))
        trs.append('<tr%s><th class="rowh" scope="row">%s</th>%s</tr>' % (' class="base"' if in_rows else "", name, "".join(tds)))
        series.append({"key": c, "label": SCENARIO_KO.get(c, c), "color": SCENARIO_COLORS.get(c, SEG_COLORS[len(series) % len(SEG_COLORS)]),
                       "rev": [round(ann[y]["rev"]) if (y in ann and _num(ann[y].get("rev"))) else None for y in years],
                       "op": [round(ann[y]["op"]) if (y in ann and _num(ann[y].get("op"))) else None for y in years],
                       "nw": [round(ann[y]["new_order_revenue"]) if (y in ann and _num(ann[y].get("new_order_revenue"))) else None for y in years]})
    payload = {"years": ["FY%sE" % y for y in years], "cases": series}
    draw = (
        'var el=document.getElementById("%s");if(!el)return;'
        'var ds=D.cases.map(function(c){var b=(c.key==="base");return {type:"bar",label:c.label,data:c.rev,backgroundColor:rgba(c.color,b?0.9:0.55),borderColor:c.color,borderWidth:b?1.5:0}});'
        'new Chart(el,{data:{labels:D.years,datasets:ds},options:{responsive:true,maintainAspectRatio:false,scales:{x:{grid:{display:false}},y:{ticks:{callback:function(v){return v.toLocaleString()}}}},'
        'plugins:{tooltip:{callbacks:{label:function(c){var k=D.cases[c.datasetIndex],i=c.dataIndex;'
        'return k.label+" 매출 "+(c.parsed.y==null?"—":c.parsed.y.toLocaleString())+"억 · OP "+(k.op[i]==null?"—":k.op[i].toLocaleString())+"억 · 신규수주 매출 "+(k.nw[i]==null?"—":k.nw[i].toLocaleString())+"억"}}}}}});'
        % (uid + "-scn"))
    last = years[-1]
    lo = ((sc.get("conservative") or {}).get("annual") or {}).get(last) or {}
    hi = ((sc.get("optimistic") or {}).get("annual") or {}).get(last) or {}
    rng = (" · FY%sE 매출 보수 %s ~ 낙관 %s억" % (E(last), fmt_a(lo.get("rev")), fmt_a(hi.get("rev")))) if (_num(lo.get("rev")) and _num(hi.get("rev"))) else ""
    fn = []
    if meta.get("existing_revenue"):
        fn.append("기존 매출 = %s" % E(meta["existing_revenue"]))
    if meta.get("source"):
        fn.append("신규수주 매출 출처 %s" % E(meta["source"]))
    if meta.get("panel_status") or meta.get("panel_reason_codes"):
        fn.append("패널 status %s%s" % (E(str(meta.get("panel_status") or "—")), (" (%s)" % E(", ".join(str(x) for x in meta["panel_reason_codes"]))) if meta.get("panel_reason_codes") else ""))
    if meta.get("calibrated") is False:
        fn.append("calibrated=false — 장부가 대용치(book-value proxy), 보정된 수주 예측이 아님")
    if meta.get("note"):
        fn.append(E(meta["note"]))
    return ('<section class="card"><h2>신규수주 시나리오 <em>FY 매출·영업이익(억, 전부 추정) · 기존(선표+잔고 소진+기타) + forecast_panel 신규수주 매출 · '
            '기준(base)만 손익표 행에 반영 · 보수/낙관은 합산 안 함%s</em>%s</h2>'
            '<div class="grid2"><div class="chart"><canvas id="%s"></canvas></div>'
            '<div class="wrap"><table class="pnl scn"><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div></div>'
            '<p class="fn" style="margin-top:8px">%s</p>%s</section>'
            % (rng, tag, uid + "-scn", "".join(head), "".join(trs), " · ".join(fn) or "메타 없음", _chart_script(uid + "-scn", payload, draw, depth)))


# ── ⑤ 가정 패널 ─────────────────────────────────────────────

def _assumptions_panel(model, sls):
    a = model.get("assumptions") or {}
    _, est = window_quarters(model)
    pill = '<span class="pill est">가정</span>'
    items = []

    def item(title, value, sub="", tip=""):
        items.append('<div%s><b>%s%s</b><span>%s</span>%s</div>' % ((' title="%s"' % E(tip)) if tip else "", value, pill, E(title), ('<i>%s</i>' % sub) if sub else ""))

    dtype, dbasis = model_driver(model)
    oos = model_oos(model)
    item("매출 드라이버(추정 구간)", E(driver_label(dtype)), ((oos + " · ") if oos else "") + E(dbasis or dtype or "모델에 드라이버 기재 없음"))
    state, no_label, no_detail = new_orders_state(model)
    if state != "n/a":
        item("신규수주(origin 이후 수주분)", "포함(base)" if state == "included" else "미포함", E((no_label + " · " + no_detail) if no_detail else no_label))
    fx = (a.get("fx") or {}).get("USDKRW_avg") or {}
    fx_e = [(q, fx[q]) for q in est if _num(fx.get(q))][:4]
    if fx_e:
        item("환율 원/달러 평균(다음 4분기)", fmt_rate(fx_e[0][1]),
             " · ".join("%s %s" % (E(q), fmt_rate(v)) for q, v in fx_e) + (" · " + E((a.get("fx") or {}).get("basis")) if (a.get("fx") or {}).get("basis") else ""))
    else:
        item("환율 원/달러 평균", "—", "모델에 환율 가정 없음")
    hd = a.get("hedge")
    if not isinstance(hd, dict) and isinstance(sls, dict) and sls.get("by_quarter"):
        q0 = next((q for q in sorted(sls["by_quarter"]) if q in est), None)
        h = (sls["by_quarter"].get(q0) or {}) if q0 else {}
        hd = {"ratio": h.get("hedge_ratio"), "rate": h.get("hedge_rate"), "basis": "sls %s" % q0} if h else None
    if isinstance(hd, dict):
        item("환헤지 비율 · 헤지환율", "%s · %s" % (fmt_pct(hd.get("ratio"), 0), fmt_rate(hd.get("rate"))), E(hd.get("basis") or ""))
    info = sls_mode_info(model, sls)
    if info.get("mode"):
        item("코호트 모드(타겟 OPM 판정)", E(info["mode"]), E(cohort_mode_text(info)))
    if info.get("cap_applied") is not None:
        item("선표 잔고 캡", "적용" if info["cap_applied"] else "미적용", E(backlog_cap_text(info)))
    for s in model.get("segments") or []:
        op = s.get("opm_path") or {}
        ks = [q for q in est if _num(op.get(q))]
        if ks:
            item("타겟 OPM · %s" % (s.get("label") or s["key"]), fmt_pct(op[ks[0]]),
                 "%s %s → %s %s" % (E(ks[0]), fmt_pct(op[ks[0]]), E(ks[-1]), fmt_pct(op[ks[-1]])))
    item("법인세율", *tax_item(a))
    item("판관비율", fmt_pct(a.get("sga_ratio")), "최근 4분기 중위")
    if _num(a.get("interest_rate_debt")) or _num(a.get("interest_rate_asset")):
        item("이자율 차입 · 이자발생자산", "%s · %s" % (fmt_pct(a.get("interest_rate_debt")), fmt_pct(a.get("interest_rate_asset"))), "평균 잔액 × 실측 이자율")
    if _num(a.get("minority_share")):
        item("비지배주주 비중", fmt_pct(a.get("minority_share")), "실측 평균")
    if _num(a.get("payout")):
        item("배당성향", fmt_pct(a.get("payout"), 0), "자본 롤(+NI −배당)")
    fxp = model.get("fx_pnl") or {}
    if _num(fxp.get("net_usd_exposure_m")):
        item("외화 순노출(백만$)", format(round(fxp["net_usd_exposure_m"]), ",d"), E(fxp.get("method") or ""))
    one = [o for o in (a.get("one_offs") or []) if isinstance(o, dict)]
    if one:
        item("알려진 일회성 %d건" % len(one), fmt_a(sum(o.get("amt") or 0 for o in one)) + "억",
             " · ".join("%s %s억 %s" % (E(o.get("q") or ""), fmt_a(o.get("amt")), E((o.get("note") or "")[:40])) for o in one[:4]))
    # 모델이 face 만으로 탐지한 일회성 의심 분기(kship_model.py one_offs_detected) — 조정EPS 행의 근거. 주석 미확인이라 '의심'·'모델 추정' 을 뗄 수 없다.
    det = [o for o in (a.get("one_offs_detected") or []) if isinstance(o, dict) and _num(o.get("eps_adj"))]
    if det:
        item("일회성 의심 %d분기(모델 탐지 — 주석 미확인)" % len(det),
             " · ".join("%s 비영업손익 %s억" % (E(o.get("q") or ""), fmt_a(o.get("nonop"))) for o in det[:4]),
             " · ".join("%s 조정EPS %s원(보고 %s원) — 초과 %s억 × (1 − %s) × 지배 %s = 세후 %s억 차감" % (
                 E(o.get("q") or ""), fmt_won(o.get("eps_adj")), fmt_won(o.get("eps_reported")), fmt_a(o.get("excess_nonop")),
                 fmt_pct(o.get("tax_rate_applied")), ("%.2f" % o["ctrl_share_applied"]) if _num(o.get("ctrl_share_applied")) else "—",
                 fmt_a(o.get("excess_after_tax"))) for o in det[:4]))
    cons = model.get("consolidation") or {}
    subs = cons.get("subsidiaries") or []
    if subs:
        item("연결 방식 · 종속사 %d" % len(subs), E(cons.get("method") or "—"), " · ".join(_sub_text(s) for s in subs))
    mods = ""
    for m in model.get("modules") or []:
        rws = []
        for r in m.get("rows") or []:
            qv = [(q, c) for q, c in sorted((r.get("q") or {}).items()) if isinstance(c, dict) and _num(c.get("v"))][:6]
            rws.append('<tr><th class="l" scope="row">%s</th><td class="l mut">%s</td><td class="l">%s</td></tr>'
                       % (E(r.get("label") or r.get("key") or ""), E(r.get("unit") or ""),
                          " · ".join('<span%s title="%s">%s %s</span>' % (' class="est"' if _is_est(c.get("kind")) else "", E(c.get("basis") or c.get("src") or ""), E(q), fmt_a(c["v"])) for q, c in qv) or "—"))
        mods += ('<h3 style="font-size:12px;color:var(--tx2);margin:12px 0 6px">회사 특유 모듈 · %s%s</h3>'
                 '<div class="wrap"><table><tbody>%s</tbody></table></div>' % (E(m.get("label") or m.get("key") or ""), pill, "".join(rws)))
    return ('<section class="card"><h2>가정 <em>값은 전부 모델 가정 — 실적이 아니다 · 바꾸려면 xlsx 의 가정 셀</em></h2><div class="assum">%s</div>%s</section>'
            % ("".join(items), mods))


def tax_item(a):
    """가정 패널 '법인세율' (값, 설명, 툴팁) — assumptions.tax_path 로 분기. carryforward_ramp 는 '유지값 → 종착값' 과 유지/램프 분기(tax_carryforward),
    툴팁에 tax_basis + tax_schedule 분기별. 값 자릿수는 r4 저장값 그대로(fmt_pct_r4) — basis 의 %.1f 와 다시 반올림해 어긋나지 않게. 나머지 경로는 1자리(basis 와 같다)."""
    path = a.get("tax_path")
    basis = a.get("tax_basis") or ""
    if path == "carryforward_ramp":
        cf = a.get("tax_carryforward") if isinstance(a.get("tax_carryforward"), dict) else {}
        ramp = ("%s~%s 선형 램프" % (E(str(cf["ramp_from"])), E(str(cf["ramp_to"])))) if (cf.get("ramp_from") and cf.get("ramp_to")) else "램프 분기 없음(추정 전 구간 유지)"
        hold = ("%s 까지 유지, " % E(str(cf["hold_until"]))) if cf.get("hold_until") else "유지 없이 "
        sched = a.get("tax_schedule") if isinstance(a.get("tax_schedule"), dict) else {}
        by_q = " · ".join("%s %s" % (q, fmt_pct_r4(sched[q])) for q in sorted(sched) if _num(sched.get(q)))
        tip = " · ".join(x for x in (basis, ("분기별: " + by_q) if by_q else "") if x)
        return "%s → %s" % (fmt_pct_r4(a.get("tax_rate")), fmt_pct_r4(a.get("tax_rate_terminal"))), "%s — %s%s" % (TAX_PATH_KO[path], hold, ramp), tip
    return fmt_pct(a.get("tax_rate")), (TAX_PATH_KO.get(path) or E(basis or "세율 경로 미기재")), basis


def _sub_text(s):
    """종속사 한 줄: 이름(종목코드 지분%) — 종목코드·지분이 둘 다 없으면(비상장) 빈 괄호를 만들지 않고 note 를 쓴다."""
    name = E(s.get("name") or s.get("stock") or "")
    inner = " ".join(x for x in (E(s.get("stock") or ""), fmt_pct(s.get("stake"), 0) if _num(s.get("stake")) else "") if x)
    if inner:
        return "%s(%s)" % (name, inner)
    return name + ((" — " + E(s["note"])) if s.get("note") else "")


# ── ⑥ 밸류에이션 스트립 ─────────────────────────────────────

def _valuation_strip(model, price):
    v = model.get("valuation") or {}
    close = (v.get("price") or {}).get("close")
    as_of = (v.get("price") or {}).get("as_of") or ""
    band = v.get("per_band") or {}
    fv = v.get("fair_value_per") or {}
    fvp = v.get("fair_value_pbr")
    tiles = [
        '<div><b>%s</b><span>PER 밴드 lo/mid/hi</span><i>%s · %s · %s · %s</i></div>' % (
            fmt_x(band.get("mid")), fmt_x(band.get("lo")), fmt_x(band.get("mid")), fmt_x(band.get("hi")), E(band.get("basis") or "근거 미기재")),
        '<div><b>%s ~ %s</b><span>PER 기준 적정가치 구간(원)</span><i>mid %s · 12M fwd EPS %s원</i></div>' % (
            fmt_won(fv.get("lo")), fmt_won(fv.get("hi")), fmt_won(fv.get("mid")), fmt_won(v.get("eps_fwd12m"))),
        '<div><b>%s</b><span>PBR 기준 적정가치(원) = ROE/COE × BPS</span><i>ROE %s · COE %s · 적정 PBR %s</i></div>' % (
            fmt_won(fvp), fmt_pct(v.get("roe_fwd")), fmt_pct(v.get("coe")), fmt_x(v.get("fair_pbr"))),
        '<div><b>%s / %s</b><span>현재 PER / PBR(종가 %s원 · %s)</span><i>EV/EBITDA %s</i></div>' % (
            fmt_x(v.get("per_now")), fmt_x(v.get("pbr_now")), fmt_won(close), E(as_of), fmt_x(v.get("ev_ebitda"))),
    ]
    bandh = ""
    pts = [x for x in (fv.get("lo"), fv.get("hi"), fvp, close) if _num(x)]
    if pts and _num(fv.get("lo")) and _num(fv.get("hi")) and fv["hi"] > fv["lo"]:
        lo, hi = min(pts) * 0.9, max(pts) * 1.1
        pos = lambda x: max(0.0, min(100.0, (x - lo) / (hi - lo) * 100))
        bandh = ('<div class="band"><i style="left:%.1f%%;width:%.1f%%" title="PER 밴드 적정가치 %s~%s원"></i>%s%s</div>'
                 '<div class="bandlbl"><span>%s원</span><span>파랑 구간 = PER 밴드 · 노란 선 = 종가 %s원%s</span><span>%s원</span></div>'
                 % (pos(fv["lo"]), pos(fv["hi"]) - pos(fv["lo"]), fmt_won(fv["lo"]), fmt_won(fv["hi"]),
                    ('<b style="left:%.1f%%" title="종가 %s원"></b>' % (pos(close), fmt_won(close))) if _num(close) else "",
                    ('<em style="left:%.1f%%" title="PBR 기준 적정가치 %s원"></em>' % (pos(fvp), fmt_won(fvp))) if _num(fvp) else "",
                    fmt_won(lo), fmt_won(close), (" · 초록 선 = PBR 기준 %s원" % fmt_won(fvp)) if _num(fvp) else "", fmt_won(hi)))
    src = ""
    if isinstance(price, dict):
        src = '<p class="fn">시세 대조: aikstockdata 종가 %s원(%s) · TTM PER %s · PBR %s — %s</p>' % (
            fmt_won(price.get("close")), E(price.get("as_of") or ""), fmt_x(price.get("pe_ttm")), fmt_x(price.get("pb")), E(AIK_CREDIT))
    return ('<section class="card"><h2>밸류에이션 <em>PER 밴드 × 12M fwd EPS · PBR = ROE/COE × BPS · 배 표기</em></h2>'
            '<span class="disclaim">%s</span><div class="kpi" style="margin-top:8px">%s</div>%s%s</section>'
            % (E(v.get("note") or DISCLAIMER), "".join(tiles), bandh, src))


# ── ⑦ 다운로드 ⑧ 각주 ──────────────────────────────────────

def _download(model, depth):
    stock = model.get("stock") or ""
    fn = "%s_model.xlsx" % stock
    path = os.path.join(XLSX_DIR, fn)
    if os.path.isfile(path):
        kb = os.path.getsize(path) / 1024
        return ('<section class="card"><h2>모델 파일 <em>변수·BS연결·BS별도·subQ·분기·연간예상·TP·외화 시트 · 가정 셀을 바꾸면 재계산</em></h2>'
                '<a class="dl" href="%smodels/%s" download>⬇ %s <span class="mut">%.0f KB</span></a></section>'
                % ("../" * depth, E(fn), E(fn), kb))
    return ('<section class="card"><h2>모델 파일 <em>xlsx</em></h2><span class="dl off">%s — 준비 중</span></section>' % E(fn))


def _footnotes(model, fin, price, sls):
    q = model.get("quality") or {}
    bt = model.get("backtest") or {}
    lim = list(q.get("warnings") or [])
    if isinstance(sls, dict):
        lim += [w for w in (sls.get("warnings") or []) if w not in lim]
    if q.get("missing"):
        lim.append("누락 분기: " + ", ".join(str(x) for x in q["missing"]))
    if q.get("identities_ok") is False:
        lim.append("항등식 불일치 있음(모델 quality.identities_ok=false)")
    fin_txt = "DART 정기보고서(연결·별도 재무제표, 주식의 총수, 배당) — 분기 %s" % (
        ("%d개" % len(fin["quarters"])) if isinstance(fin, dict) and isinstance(fin.get("quarters"), list) else fmt_won(q.get("fin_quarters")))
    if isinstance(fin, dict) and fin.get("collected_at"):
        fin_txt += " · 수집 %s" % E(str(fin["collected_at"]))
    price_txt = E((price or {}).get("source") if isinstance(price, dict) and price.get("source") else AIK_CREDIT)
    bt_txt = ("freeze %s · %s분기 앞 · n=%s · 매출 WAPE %s · OP WAPE %s%s" % (
        E(str(bt.get("freeze") or "—")), E(str(bt.get("horizon") or "—")), E(str(bt.get("n") or "—")),
        fmt_pct100(bt.get("revenue_wape_pct")), fmt_pct100(bt.get("op_wape_pct")),
        (" — " + E(bt["note"])) if bt.get("note") else "")) if bt else "백테스트 기록 없음"
    extra = ""
    state, no_label, no_detail = new_orders_state(model)
    if state != "n/a":
        extra += '<li>신규수주: %s%s</li>' % (E(no_label), (" — " + E(no_detail)) if no_detail else "")
    o = _first_driver_with(model, "selection_oos").get("selection_oos")
    if isinstance(o, dict) and o.get("rule"):
        extra += '<li>드라이버 선택(OOS): %s — %s</li>' % (model_oos(model), E(str(o["rule"])))
    return ('<section class="card"><h2>각주 <em>출처 · 한계 · 백테스트</em></h2><ul class="fn">'
            '<li>출처: 재무 %s · 시세 %s · 환율 ECB(api.frankfurter.app, 네이버 대조) · 계약 원장 KIND 단일판매ㆍ공급계약체결 · 부문 롤포워드 정기보고서.</li>'
            '<li>단위: 표·차트 억원(백만원÷100), EPS·BPS 원, 달러 백만$. 손익은 3개월분(Q4 = 연간 − 3Q 누적). 기준 %s · 생성 %s.</li>'
            '<li>추정 규칙: 추정 칸은 음영·E 표기, 툴팁에 근거(basis). 가정은 가정 패널에 값과 함께 적었다. 출처 없는 숫자는 없다 — 모델이 주지 않은 값은 —.</li>'
            '%s<li>한계: %s</li><li>백테스트: %s</li><li><b>%s</b></li></ul></section>'
            % (fin_txt, price_txt, E(model.get("origin") or "—"), E(str(model.get("built_at") or "—")), extra,
               " · ".join(E(str(x)) for x in lim) if lim else "기재 없음", bt_txt, E(DISCLAIMER)))


# ── 조립 ────────────────────────────────────────────────────

def render_model_section(entry, model, fin=None, price=None, sls=None, depth=1):
    """회사 페이지에 붙일 실적 모델 섹션. entry.stock 과 model.stock 이 다르면 거부한다(다른 회사 값이 섞이는 사고 방지)."""
    stock = (entry or {}).get("stock")
    if not isinstance(stock, str) or not re.fullmatch(r"\d{6}", stock):
        raise ValueError("invalid stock identifier")
    if not isinstance(model, dict) or model.get("stock") != stock:
        raise ValueError("company_identity_conflict")
    if isinstance(sls, dict) and sls.get("stock") not in (None, stock):
        raise ValueError("sls_identity_conflict")
    name = (entry or {}).get("name") or model.get("name") or stock
    uid = "kship-model-" + stock
    s = model_summary(model)
    dtype, _ = model_driver(model)
    state, no_label, no_detail = new_orders_state(model)
    info = sls_mode_info(model, sls)
    oos = model_oos(model, short=True)
    tag = ('<span class="tag%s" title="%s">%s</span>' % ("" if state == "included" else " off", E(no_detail), E(no_label))) if no_label else ""
    # T6 D7: 드라이버 폴백 사유는 status 와 따로 — 머리에는 코드(뜻), 상세(상관·n·WAPE)는 상태 줄 툴팁
    fb_code, fb_label, _ = driver_fallback_info(model)
    fb_txt = "" if not fb_code else (" · 폴백 없음" if fb_code == "none" else " · 폴백 사유 %s(%s)" % (E(fb_code), E(fb_label)))
    parts = [
        '<div id="%s" class="kmodel" data-model-status="%s" data-model-origin="%s" data-model-driver="%s" data-model-driver-fallback="%s"'
        ' data-model-new-orders="%s" data-model-cohort-mode="%s" data-model-backlog-cap="%s"><style>%s</style>'
        % (uid, E(str(s["status"] or "")), E(model.get("origin") or ""), E(dtype or ""), E(fb_code or ""), state, E(info.get("mode") or ""),
           "" if info.get("cap_applied") is None else ("applied" if info["cap_applied"] else "not_applied"), SECTION_CSS),
        '<h2 class="sec">%s · 실적 모델%s<span>%s · 기준 %s · 드라이버 %s%s%s · %s</span></h2>'
        % (E(name), tag, E(ROLE_KO.get(model.get("role"), model.get("role") or "—")), E(model.get("origin") or "—"),
           E(driver_label(dtype)), (" (%s)" % oos) if oos else "", fb_txt, E(DISCLAIMER)),
        status_line(model),
        _kpi_strip(model, price),
        _pnl_table(model),
        _segment_chart(model, uid, depth),
        _sls_charts(model, sls, uid, depth),
        _scenario_card(model, uid, depth),
        _assumptions_panel(model, sls),
        _valuation_strip(model, price),
        _download(model, depth),
        _footnotes(model, fin, price, sls),
        "</div>",
    ]
    return "".join(parts)


def _load_json(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_model(stock, models_dir=None):
    return _load_json(os.path.join(models_dir or MODELS_DIR, "%s.json" % stock))


def _entry_for(stock, model):
    try:
        from kship_universe import load as load_universe
        for r in load_universe():
            if r.get("stock") == stock:
                return {"stock": stock, "name": r.get("name"), "role": r.get("role")}
    except Exception:
        pass
    return {"stock": stock, "name": model.get("name"), "role": model.get("role")}


def section_for_stock(stock, depth=1):
    """훅 진입점. 모델 json 이 없으면 "" — 섹션을 만들지 않는다."""
    model = load_model(stock)
    if not model:
        return ""
    fin = _load_json(os.path.join(FIN_DIR, "%s.json" % stock))
    prices = _load_json(PRICES_PATH) or {}
    price = (prices.get("rows") or {}).get(stock) if isinstance(prices, dict) else None
    if isinstance(price, dict) and not price.get("source") and prices.get("source"):
        price = dict(price, source=prices["source"])
    sls = _load_json(os.path.join(SLS_DIR, "%s.json" % stock))
    return render_model_section(_entry_for(stock, model), model, fin=fin, price=price, sls=sls, depth=depth)


# ── 태그 균형 검사(간단 파서) ────────────────────────────────

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Balance(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.problems = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if not self.stack:
            self.problems.append("닫는 태그만 있음: </%s>" % tag)
            return
        if self.stack[-1] == tag:
            self.stack.pop()
            return
        if tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.problems.append("안 닫힘: <%s> (</%s> 만남)" % (self.stack.pop(), tag))
            self.stack.pop()
        else:
            self.problems.append("짝 없는 닫는 태그: </%s>" % tag)


def check_tag_balance(html_text):
    """열고 닫힘이 맞지 않는 태그 목록(빈 리스트면 통과). <script>/<style> 안은 HTMLParser 가 CDATA 로 다룬다."""
    p = _Balance()
    p.feed(html_text)
    p.close()
    return p.problems + ["안 닫힘(끝): <%s>" % t for t in p.stack]


# ── 허브 models.html ─────────────────────────────────────────

RENDER_CHECK_MARK = "실적 모델(렌더 확인)"     # --render 출력의 <title>/<h1> 표식 — 회사 페이지가 아니다


def _is_company_page(path):
    """<stock>/index.html 이 진짜 회사 페이지인지. --render 확인 출력(제목에 '렌더 확인')은 회사 페이지로 치지 않는다."""
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(4000)
    except OSError:
        return False
    return RENDER_CHECK_MARK not in head


def _is_company_folder_target(path):
    """--out 이 argus/kship/<6자리>/index.html 을 가리키면 True — 회사 페이지 자리에 렌더 확인 출력을 쓰지 않는다."""
    ap = os.path.abspath(path)
    return bool(re.fullmatch(r"\d{6}", os.path.basename(os.path.dirname(ap)))) and os.path.basename(ap) == "index.html" \
        and os.path.dirname(os.path.dirname(ap)) == os.path.abspath(KSHIP)


def population():
    """56사 = universe.json(41) ∪ suppliers.json ∪ 회사 폴더(승격분은 페이지 <h1> 에서 이름). 정렬은 종목코드."""
    rows = collections.OrderedDict()
    try:
        from kship_universe import load as load_universe
        for r in load_universe():
            rows[r["stock"]] = {"stock": r["stock"], "name": r.get("name"), "role": r.get("role")}
    except Exception:
        pass
    sup = _load_json(os.path.join(ASSETS, "suppliers.json")) or {}
    for c in sup.get("cos") or []:
        rows.setdefault(c["stock"], {"stock": c["stock"], "name": c.get("nm"), "role": c.get("role")})
        if not rows[c["stock"]].get("role") and c.get("role"):
            rows[c["stock"]]["role"] = c["role"]
    for d in sorted(os.listdir(KSHIP)):
        if not re.fullmatch(r"\d{6}", d) or not _is_company_page(os.path.join(KSHIP, d, "index.html")):
            continue
        if d not in rows:
            name = None
            try:
                with open(os.path.join(KSHIP, d, "index.html"), encoding="utf-8") as f:
                    m = re.search(r"<h1>([^<]{1,60})</h1>", f.read(8000))
                name = m.group(1).strip() if m else None
            except OSError:
                pass
            rows[d] = {"stock": d, "name": name or d, "role": None}
        rows[d]["has_page"] = True
    for r in rows.values():
        r.setdefault("has_page", _is_company_page(os.path.join(KSHIP, r["stock"], "index.html")))
    return sorted(rows.values(), key=lambda r: r["stock"])


def _page_has_section(stock):
    """회사 페이지 index.html 에 이 회사의 모델 섹션(id=kship-model-<stock>)이 실제로 있는지."""
    try:
        with open(os.path.join(KSHIP, stock, "index.html"), encoding="utf-8") as f:
            return ('id="kship-model-%s"' % stock) in f.read()
    except OSError:
        return False


def _summary_status(summary, stock):
    """L4 summary.json 의 status 를 관대하게 읽는다(dict 키 또는 rows 리스트)."""
    if not isinstance(summary, dict):
        return None
    x = summary.get(stock) or (summary.get("rows") or {}).get(stock) if isinstance(summary.get("rows"), dict) else summary.get(stock)
    if x is None and isinstance(summary.get("rows"), list):
        x = next((r for r in summary["rows"] if isinstance(r, dict) and r.get("stock") == stock), None)
    if x is None and isinstance(summary.get("companies"), list):
        x = next((r for r in summary["companies"] if isinstance(r, dict) and r.get("stock") == stock), None)
    return x.get("status") if isinstance(x, dict) else None


def _peek_json_key(path, key, nbytes=4096):
    """큰 json(fin 수백 KB)의 머리만 읽어 최상위 문자열 키 하나를 꺼낸다 — 허브 각주의 수집 시각용. 전체 파싱은 하지 않는다."""
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(nbytes)
    except OSError:
        return None
    m = re.search(r'"%s"\s*:\s*"([^"]*)"' % re.escape(key), head)
    return m.group(1) if m else None


def _models_in_dir(models_dir):
    """<6자리>.json 종목 목록(정렬). summary.json 등은 제외."""
    try:
        names = os.listdir(models_dir)
    except OSError:
        return []
    return sorted(n[:6] for n in names if re.fullmatch(r"\d{6}\.json", n))


def _hub_footnote(models_dir, stocks, latest_built):
    """허브 고정 각주 — 마지막 갱신(입력 파일의 기록만, 시계를 읽지 않는다) · 출처 · 단위 · status/폴백 구분 · 추천 아님."""
    summary = _load_json(os.path.join(models_dir, "summary.json")) or {}
    prices = _load_json(PRICES_PATH) or {}
    fx = _load_json(os.path.join(ASSETS, "fx.json")) or {}
    fin_at, sls_at = set(), set()
    for st in stocks:
        v = _peek_json_key(os.path.join(FIN_DIR, "%s.json" % st), "collected_at")
        if v:
            fin_at.add(v)
        s = _load_json(os.path.join(SLS_DIR, "%s.json" % st)) if os.path.isfile(os.path.join(SLS_DIR, "%s.json" % st)) else None
        v = (s or {}).get("built_at") or (s or {}).get("as_of")
        if v:
            sls_at.add(str(v))

    def rng(xs):
        xs = sorted(xs)
        return "—" if not xs else (E(xs[0]) if xs[0] == xs[-1] else "%s~%s" % (E(xs[0]), E(xs[-1])))

    return ('<section class="card"><h2>각주 <em>마지막 갱신 · 출처 · 단위 · 면책 — 고정</em></h2><ul class="fn">'
            '<li>마지막 갱신: 모델 생성 %s(summary.json built_at %s · 기준 분기 %s) · 재무(fin) 수집 %s · 시세 as_of %s · 환율 as_of %s · 선표(sls) %s. '
            '이 페이지는 모델 json 에서 그대로 만들어지며 시계를 읽지 않는다 — 갱신 시각은 입력 파일의 기록이다.</li>'
            '<li>출처: 재무 DART 정기보고서(연결·별도 재무제표·주석, 키 없는 공개 열람) · 시세 %s · 환율 ECB(api.frankfurter.app, 네이버 대조) · '
            '계약 원장 KIND 단일판매ㆍ공급계약체결 · 신규수주 forecast_panel base(calibrated=false, 미보정).</li>'
            '<li>단위: 이 표는 억원(백만원÷100) · EPS 원 · PER/PBR 배. 페이지 꼬리의 공용 각주(백만원·백만달러)는 사이트 공통 문구다.</li>'
            '<li>상태·폴백: %s. \'폴백 사유\' 열은 driver_fallback — %s.</li>'
            '<li><b>%s</b> — 컨센서스·목표주가가 아니며 투자 판단의 근거로 쓰지 말 것. 참고용 · 투자조언 아님.</li></ul></section>'
            % (E(latest_built or "—"), E(str(summary.get("built_at") or "—")), E(str(summary.get("origin") or "—")), rng(fin_at),
               E(str(prices.get("as_of") or "—")), E(str(fx.get("as_of") or "—")), rng(sls_at),
               E(AIK_CREDIT), E(STATUS_RULE), " · ".join("%s=%s" % (k, E(v)) for k, v in DRIVER_FALLBACK_KO.items()), E(DISCLAIMER)))


def build_models_hub(models_dir=None, write=True):
    models_dir = models_dir or MODELS_DIR
    pop = population()
    pop_stocks = {r["stock"] for r in pop}
    # 모집단 밖 모델(universe·suppliers·회사 폴더 어디에도 없는 회사 — 피합병 HD현대미포 010620 같은 참고용 모델)도 표에 올린다. 빠뜨리면
    # 허브 '모델 생성 57' 과 summary.json 58행이 어긋난다. 종목코드 순으로 섞고 '모집단 외' 라고 적는다.
    outside = [{"stock": st, "name": None, "role": None, "has_page": False, "outside": True} for st in _models_in_dir(models_dir) if st not in pop_stocks]
    summary = _load_json(os.path.join(models_dir, "summary.json"))
    built, latest_built, origins = 0, "", collections.Counter()
    status_n = collections.Counter()
    no_n = collections.Counter()          # 신규수주 포함/미포함 회사 수
    fb_n = collections.Counter()          # 드라이버 폴백 사유(T6 D7) 회사 수
    n_out = 0
    with_model = []
    trs = []
    for r in sorted(pop + outside, key=lambda x: x["stock"]):
        st = r["stock"]
        model = load_model(st, models_dir)
        if r.get("outside") and not model:
            continue
        role = (model or {}).get("role") or r.get("role")
        name = r.get("name") or (model or {}).get("name") or st
        # 앵커는 회사 페이지에 섹션이 실제로 있을 때만 — 빌더가 아직 다시 그리지 않은 페이지(승격분 등)로는 앵커 없이 보낸다
        has_sec = r.get("has_page") and _page_has_section(st)
        link = ('<a href="%s/index.html%s">%s</a>' % (E(st), ("#kship-model-" + E(st)) if has_sec else "", E(name))) if r.get("has_page") else E(name)
        if r.get("outside"):
            n_out += 1
            link += ' <span class="mut" title="universe·suppliers·회사 폴더 어디에도 없는 회사 — 피합병 등 참고용 모델(회사 페이지·시세 없음)">모집단 외</span>'
        xlsx = os.path.isfile(os.path.join(XLSX_DIR, "%s_model.xlsx" % st))
        xl = ('<a href="models/%s_model.xlsx" download>xlsx</a>' % E(st)) if xlsx else '<span class="mut">—</span>'
        if not model:
            status_n["none"] += 1
            trs.append('<tr><td class="l">%s</td><td class="mut">%s</td><td class="l">%s</td>%s<td class="l"><b class="tx3">모델 없음</b></td><td>%s</td></tr>'
                       % (link, E(st), E(ROLE_KO.get(role, role or "—")), '<td class="mut">—</td>' * 17, xl))
            continue
        built += 1
        with_model.append(st)
        if r.get("has_page") and not has_sec:
            status_n["nosec"] += 1
            link += ' <span class="mut" title="회사 페이지 빌더(kship_page/kship_parts)가 이 회사를 다시 그리지 않아 섹션이 아직 없음">섹션 없음</span>'
        s = model_summary(model)
        status = _summary_status(summary, st) or s["status"] or "—"
        status_n[status] += 1
        latest_built = max(latest_built, str(model.get("built_at") or ""))
        origins[model.get("origin") or "—"] += 1
        dtype, _ = model_driver(model)
        oos = model_oos(model, short=True)
        cells = ['<td class="l" title="%s">%s%s</td>' % (E(dtype or ""), E(driver_label(dtype)), (' <span class="mut">%s</span>' % oos) if oos else "")]
        # 폴백 사유 열(T6 D7) — status 와 분리. 코드(driver_fallback 값 그대로) + 뜻, 툴팁에 상관·n·WAPE. 없으면 '—'(구버전 모델).
        fb_code, fb_label, fb_det = driver_fallback_info(model)
        fb_n[fb_code or "—"] += 1
        if fb_code == "none":
            fb_html = '<span class="mut">%s · %s</span>' % (E(fb_code), E(fb_label))
        elif fb_code:
            fb_html = '<b class="wn">%s</b> · %s' % (E(fb_code), E(fb_label))
        else:
            fb_html = '<span class="mut">—</span>'
        cells.append('<td class="l" data-v="%s" title="%s">%s</td>' % (E(fb_code or ""), E(fb_det or "driver_fallback 미기재(구버전 모델)"), fb_html))
        # 신규수주 열(결정 ⓓ): 조선사·지주만 포함/미포함, 기자재는 고객 모델 경유라 —. FY 매출이 base 신규수주를 품고 있는지 표에서 바로 보이게.
        no_state, no_label, no_detail = new_orders_state(model)
        no_n[no_state] += 1
        no_title = (no_label + " · " + no_detail) if no_detail else no_label
        cells.append('<td class="l" data-v="%s"%s>%s</td>' % (
            {"included": 2, "excluded": 1}.get(no_state, 0), (' title="%s"' % E(no_title)) if no_title else "",
            {"included": '<b class="wn">포함</b>' + ('<span class="mut"> 폴백</span>' if no_label in (NEW_ORDERS_FALLBACK_LABEL, NEW_ORDERS_LEDGER_LABEL) else ""),
             "excluded": '<span class="mut">미포함</span>'}.get(no_state, '<span class="mut">—</span>')))
        for y in FY_EST:
            f = s["fy"][y]
            rng = s["scn"].get(y)
            cells += ['<td class="est" data-v="%s"%s>%s</td>' % (f["rev"] if _num(f["rev"]) else "",
                                                             (' title="%s"' % E("신규수주 시나리오 보수 %s ~ 낙관 %s억(base 는 표 값)" % (fmt_a(rng["cons"]), fmt_a(rng["opt"])))) if rng else "",
                                                             fmt_a(f["rev"])),
                      '<td class="est" data-v="%s">%s</td>' % (f["op"] if _num(f["op"]) else "", fmt_a(f["op"])),
                      '<td class="est" data-v="%s">%s</td>' % (round(f["opm"] * 100, 2) if _num(f["opm"]) else "", fmt_pct(f["opm"])),
                      # EPS 칸: data-v·본문 1차 값은 보고 EPS(정렬·selfcheck 불변). 조정EPS 가 임계 이상 다르면 data-adj + 괄호 2차 값.
                      '<td class="est" data-v="%s"%s>%s%s</td>' % (
                          f["eps"] if _num(f["eps"]) else "",
                          (' data-adj="%s" title="%s"' % (f["eps_adj"], E("조정 EPS %s원 — 일회성 의심 분기 세후 차감(모델 추정) · 정렬·검사는 보고 EPS(data-v)" % fmt_won(f["eps_adj"])))) if adj_differs(f["eps"], f["eps_adj"]) else "",
                          fmt_won(f["eps"]), (' <span class="mut">(조정 %s)</span>' % fmt_won(f["eps_adj"])) if adj_differs(f["eps"], f["eps_adj"]) else "")]
        # 'PER 현재' = 종가 ÷ 12M fwd EPS(추정 분기만) — 실적 분기의 일회성 의심분이 들어가지 않으므로 값은 그대로, 뜻만 툴팁에.
        fq = (model.get("valuation") or {}).get("eps_fwd_quarters") or []
        per_title = (' title="%s"' % E("종가 ÷ 12M fwd EPS(%s~%s, 추정 분기만)%s" % (fq[0], fq[-1], " — 일회성 의심 분기 미포함(조정 불필요)" if "조정EPS" in row_map(model) else ""))) if fq else ""
        cells += ['<td data-v="%s"%s>%s</td>' % (s["per_now"] if _num(s["per_now"]) else "", per_title, fmt_x(s["per_now"])),
                  '<td data-v="%s">%s</td>' % (s["pbr_now"] if _num(s["pbr_now"]) else "", fmt_x(s["pbr_now"]))]
        cls = {"full": "up", "partial": "wn", "no_fin": "dn"}.get(status, "tx3")
        # 상태 칸 툴팁: 규칙 + partial 사유(되짚은 것). 사유를 못 되짚으면 '미기재' — 지어내지 않는다.
        st_title = STATUS_RULE
        if status == "partial":
            st_title += " — 사유: " + (" · ".join(status_reasons(model)) or "미기재(quality.warnings 참조)")
        trs.append('<tr><td class="l">%s</td><td class="mut">%s</td><td class="l">%s</td>%s<td class="l"><b class="%s" title="%s">%s</b></td><td>%s</td></tr>'
                   % (link, E(st), E(ROLE_KO.get(role, role or "—")), "".join(cells), cls, E(st_title), E(STATUS_KO.get(status, status)), xl))
    # 머리글은 **한 행** — 공용 TABLE_JS 는 thead th 의 평면 순번을 본문 열 번호로 쓰므로 rowspan/colspan 2행 머리글이면 정렬 열이 어긋난다.
    head = ('<tr><th class="l">회사</th><th>종목코드</th><th class="l">역할</th><th class="l">드라이버</th><th class="l">폴백<br>사유</th><th class="l">신규<br>수주</th>'
            + "".join('<th class="est">FY%sE<br>매출(억)</th><th class="est">FY%sE<br>OP(억)</th><th class="est">FY%sE<br>OPM</th><th class="est">FY%sE<br>EPS(원)</th>'
                      % ((y[2:],) * 4) for y in FY_EST)
            + '<th>PER<br>현재</th><th>PBR<br>현재</th><th class="l">상태</th><th>xlsx</th></tr>')
    origin_txt = ", ".join("%s %d" % (E(k), v) for k, v in sorted(origins.items())) or "—"
    fb_parts = ["%s %d" % (k, fb_n[k]) for k in DRIVER_FALLBACK_KO if k != "none" and fb_n[k]]
    if fb_n["—"]:
        fb_parts.append("미기재 %d" % fb_n["—"])
    fb_txt = " · ".join(fb_parts) or "없음"
    body = """
<div class="kmodel"><style>%s</style>
<div class="kpi">
 <div><b>%d<small>/ %d</small></b><span>모델 생성 · 모집단%s</span></div>
 <div><b>%d</b><span>완성(full) · 부분 %d · 재무 없음 %d · 페이지 섹션 없음 %d — status 는 데이터 완전성(T6 D7)</span></div>
 <div><b>%d<small>/ %d</small></b><span>드라이버 폴백 없음(none) · 폴백 — %s</span></div>
 <div><b>%d<small>/ %d</small></b><span>신규수주 포함 · 미포함(조선사·지주, forecast_panel base 미보정)</span></div>
 <div><b>%s</b><span>기준 분기</span></div>
 <div><b>%s</b><span>최근 생성</span></div>
</div>
<section class="card"><h2>실적 모델 — 섹터 표 <em>FY2026E~28E 매출·OP·OPM·EPS(전부 추정, 음영) · 현재 PER/PBR · 억원 · 머리글을 누르면 정렬 · 신규수주 '포함' 행의 FY 매출은 forecast_panel base(미보정)를 품음 — 매출 칸 툴팁에 보수~낙관 · '폴백 사유' 는 driver_fallback(status 와 별개), 상태 칸 툴팁에 partial 사유 · EPS 칸의 '(조정 …)' 은 조정EPS 행이 있는 회사만(일회성 의심 분기 세후 차감 · 모델 추정 · 정렬은 보고 EPS)</em>
<span class="right"><input data-filter="#mtab" placeholder="회사·종목코드 검색" aria-label="회사 검색" style="background:var(--pn2);border:1px solid var(--ln);border-radius:6px;color:var(--tx);font:12px var(--sans);padding:4px 9px"></span></h2>
<span class="disclaim">%s</span>
<div class="wrap tall"><table id="mtab" class="pnl" data-sortable><thead>%s</thead><tbody>%s</tbody></table></div>
</section>
<div class="note info">모델은 회사 페이지 하단 「실적 모델」 섹션에 분기 손익표·사업부 차트·가정·밸류에이션으로 펼쳐집니다. 출처 DART 정기보고서 · %s · 환율 ECB(api.frankfurter.app). 모델 없음은 아직 재무 수집·모델 생성이 닿지 않은 회사입니다 — 빈 칸으로 흉내 내지 않습니다.</div>
%s
</div>
<script>%s</script>
""" % (SECTION_CSS, built, len(pop), (" (모집단 외 %d 포함 — 피합병 참고용)" % n_out) if n_out else "",
       status_n.get("full", 0), status_n.get("partial", 0), status_n.get("no_fin", 0), status_n.get("nosec", 0),
       fb_n.get("none", 0), built - fb_n.get("none", 0), fb_txt,
       no_n.get("included", 0), no_n.get("excluded", 0),
       origin_txt, E(latest_built or "—"), E(DISCLAIMER), head, "".join(trs), E(AIK_CREDIT),
       _hub_footnote(models_dir, with_model, latest_built), TABLE_JS)
    html = page("한국조선 실적 모델 — %d사 FY2026E~28E" % len(trs), body, depth=0, h1="📈 실적 모델",
                nav=(("허브", "index.html"), ("커버리지", "coverage.html"), ("← ARGUS", "../index.html")),
                crumbs=(("ARGUS", "../index.html"), ("한국조선", "index.html"), ("실적 모델", None)),
                lead="조선사·지주·엔진·기자재·강재 모집단 전부에 같은 구조의 분기 실적 모델(subQ 방식)을 적용한 결과표입니다. 값은 전부 모델 추정이며 목표주가·추천이 아닙니다. 회사 이름을 누르면 회사 페이지의 모델 섹션으로 갑니다.")
    if write:
        atomic_write(os.path.join(KSHIP, "models.html"), html)
    return html


def main():
    ap = argparse.ArgumentParser(description="실적 모델 섹션 렌더러 · models.html 빌더")
    ap.add_argument("--hub", action="store_true", help="argus/kship/models.html 생성")
    ap.add_argument("--models-dir", default=None, help="모델 json 디렉터리(기본 assets/models)")
    ap.add_argument("--render", metavar="STOCK", help="한 회사 섹션을 렌더해 --out 에 쓴다(page 셸 포함)")
    ap.add_argument("--model", help="--render 용 모델 json 경로(기본 assets/models/<stock>.json)")
    ap.add_argument("--sls", help="--render 용 sls json 경로(선택)")
    ap.add_argument("--out", help="--render 출력 파일")
    ap.add_argument("--check", metavar="HTML", help="HTML 파일 태그 균형 검사")
    a = ap.parse_args()
    rc = 0
    if a.check:
        with open(a.check, encoding="utf-8") as f:
            probs = check_tag_balance(f.read())
        print("%s: %s" % (a.check, "태그 균형 OK" if not probs else "문제 %d건" % len(probs)))
        for p in probs[:20]:
            print("  -", p)
        rc |= 1 if probs else 0
    if a.render:
        if a.out and _is_company_folder_target(a.out):
            # 회사 페이지는 kship_page/kship_parts 가 만든다 — 렌더 확인 출력을 그 자리에 쓰면 가짜 회사 페이지가 생기고 허브가 링크한다
            print("거부: --out 이 회사 페이지 자리(%s)입니다. 렌더 확인 출력은 /tmp 등 다른 곳에 쓰세요." % a.out)
            return 2
        model = _load_json(a.model) if a.model else load_model(a.render, a.models_dir)
        if not model:
            print("모델 없음: %s" % a.render)
            return 2
        sls = _load_json(a.sls) if a.sls else _load_json(os.path.join(SLS_DIR, "%s.json" % a.render))
        frag = render_model_section({"stock": a.render, "name": model.get("name"), "role": model.get("role")}, model, sls=sls, depth=1)
        html = page("%s %s" % (model.get("name"), RENDER_CHECK_MARK), frag, depth=1, scripts=("../vendor/chart.umd.min.js",))
        probs = check_tag_balance(html)
        if a.out:
            atomic_write(a.out, html)
        print("%s %s: %d bytes · 섹션 %d · 태그 균형 %s" % (a.render, model.get("name"), len(html), frag.count('<section class="card">'),
                                                      "OK" if not probs else "문제 %d건" % len(probs)))
        rc |= 1 if probs else 0
    if a.hub:
        html = build_models_hub(a.models_dir)
        probs = check_tag_balance(html)
        print("models.html: %d chars · 행 %d · 태그 균형 %s" % (len(html), html.count("<tr>") - 1, "OK" if not probs else "문제 %d건" % len(probs)))
        rc |= 1 if probs else 0
    return rc


if __name__ == "__main__":
    sys.exit(main())
