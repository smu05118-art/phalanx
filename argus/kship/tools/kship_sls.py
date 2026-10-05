#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_sls — 조선사 선표 매출인식(SLS): 척당 계약 원장 → 분기 진행률 매출(백만$) → 헤지 적용 원화.

레퍼런스(HD현대미포·삼성重 subQ 의 `SLS` 시트)는 클락슨 선표를 Yard×선종×인도분기로 피벗해 매출$ 를 만들고,
헤지환율·건조시점환율을 HEDGE 70% / open 30% 로 섞어 원화 매출을 낸 뒤, 수주업황 코호트(①적자~⑤초호황)
비중으로 타겟 OPM 을 뽑는다. 우리는 클락슨이 없다 — **척당 계약 공시 원장**(assets/contracts.json)이 선표다.

  진행률   계약기간 시작~종료(종료 = 마지막 호선 인도)를 분기로 쪼개 일수 비례(linear, 옵션 s_curve)로 배분.
           종료일이 '-' 인 계약은 같은 선종의 계약기간 중위로 종료를 추정하고 end_estimated 로 표시한다.
  달러화   amt_usd_m = amt_krw_m ÷ 수주시점 환율. 환율 우선순위: 공시 본문의 "USD 1 = 1,383.70원" 고시환율 >
           assets/fx.json 분기 평균 > 그 회사 yards_cache 의 헤지 평균약정환율(약정환율, 현물 아님) > 상수 1350.
           어느 것을 썼는지 계약마다 fx_source 에 남긴다.
  헤지     applied_rate = hedge_ratio × hedge_rate + (1 − hedge_ratio) × spot(건조시점 환율 가정).
           hedge_ratio 는 최신 분기 통화선도 매도 명목액(usd_sell_m) ÷ (기말 수주잔고 원화 ÷ 평균약정환율) 로
           회사별 실측(kship_page.yard_summary 방식). 약정환율이 공시에 없으면 계산하지 않고 0.7 가정으로 표기한다.
           hedge_rate 는 회사 평균약정환율, 없으면 계약별 수주시점 환율(헤지는 보통 수주 무렵에 건다 — 가정).
  코호트   두 모드를 **모두** 계산해 저장한다(MODEL_SPEC §5-2, 결정 ⓔ). 기본 reference_anchor: 수주연도 → 등급 표
           COHORT_BY_ORDER_YEAR(레퍼런스 HD현대미포 SLS 의 매출연도별 코호트 비중을 건조기간 2~3년으로 수주연도에 되돌린 것:
           ≤2020 ③중마진 · 2021 ④호황 · 2022~ ⑤초호황; 출처 사용자 레퍼런스 모델, 클락슨 기반 판정). 외부 지수 파일
           assets/newbuild_index.json 이 있으면 그것을 우선한다(형식은 아래, 현재 없음). 대안 ledger_relative: 같은 선종·
           같은 수주연도 안에서 척당 금액(amt_usd_m/ships)의 중위 대비 위치 + 그 연도의 시장 수준(원장 안 추세만) → ①~⑤.
           기본 모드는 cohort/by_cohort/target_opm/calibration, 다른 모드는 cohort_alt/by_cohort_alt/target_opm_alt/calibration_alt.
           파일 최상위 cohort_mode·cohort_table·cohort_source 에 모드·표·출처를 적는다. --cohort-mode 로 기본을 바꿀 수 있다.
  잔고캡   origin 분기말까지 수주된 해양 계약의 원장 잔여 원화(수주시점 금액 × 미진행 비율)가 공시 해양 기말잔고를 넘으면
           (backlog_coverage_at_origin > 1 — 대한조선 2026Q2 1.164) 그 계약들의 origin 이후 분기 매출을 1/coverage 배로 줄인다
           (backlog_cap). origin 뒤 수주분(그 잔고에 없다)·비해양(OTHER)·과거 분기는 그대로. 원값은 by_quarter[q].backlog_cap.*_raw ·
           by_year[y].*_raw · counts.forecast_window.*_raw 에 보존하고 파일 최상위 backlog_cap_applied 로 표시한다.
  체결시점 by_quarter[q].marine_hedged_krw_m 를 origin 분기말까지 체결분(_signed_by_origin) 과 그 뒤 체결분(_post_origin) 으로도
           나눠 적는다(합 = marine_hedged_krw_m, 1자리 반올림 차). 모델은 신규수주(forecast_panel)를 더할 때 앞쪽만 '기존' 으로 쓴다
           (T6 D1 — origin 이후 공시 수주의 이중계산 방지). 최상위 post_origin 에 건수·금액·창 합계·rcp 목록.
  화해     분기 SLS 원화(해양 계약만) ÷ 정기보고서 부문 매출 3개월분(누계 차분; Q1 = 누계, Q4 = 연간 − 3Q 누계).
           매출표가 없는 회사는 기납품 누계 차분(HD현대重·대한조선·한화오션 방식), HJ 는 프로젝트 누계라 같은 해 차분만.
  타겟OPM  코호트 표(①−5% ②0 ③5 ④10 ⑤15 — 가정) × 매출 비중. 회사 실측 OPM 이 있으면(assets/fin) shift 를 잰다.
  OPM표    기본은 위 가정 표(assumed). --opm-table reference_calibrated 면 레퍼런스 HD현대미포 SLS 'ⓞ OPM 잡기' 블록(코호트×선종 셀마다
           애널리스트가 둔 OPM)을 코호트별로 매출가중한 유효 OPM(2023~27 창: ①−1.1% ②1.0 ③4.3 ④5.4 ⑤10.8)으로 타겟을 만든다.
           어느 표를 썼든 두 표·근거·연도별 괴리(가정 표는 레퍼런스 2024~26 보다 +3.8~5.1%p 높다)는 cohort_opm_calibration 에 항상 적는다.
  헤지참고 약정환율 미공시 회사(0.7 가정)는 공시 통화선도 매도 명목액(usd_sell_m)을 두 가지로 잔고 대비 환산한 참고치를 hedge 에 둔다 —
           ÷ (기말잔고 ÷ 기말 현물) = hedge_ratio_implied_spot, ÷ (기말잔고 ÷ 수주시점 평균환율) = hedge_ratio_implied_sign_rate
           (평균환율 = origin 분기말까지 체결된 counted 계약의 원화 합 ÷ 달러 합). 적용값은 아니다. 레퍼런스 SLS 시트의 HEDGE 행은
           미포 0.65 · 삼성重 1.00 (2008~2027 전 연도 상수) 이고 0.7 은 그 범위 안에 둔 가정이다(--hedge-default 로 바꿀 수 있다).
  재현     built_at 은 --today 로 고정할 수 있다(같은 입력 → 같은 바이트). spot_source·fx_source 는 fx.json 의 부분 분기(partial)를 표시한다.

한계를 숨기지 않는다: 원장은 2024~ 공시분이라 그 전에 수주한 물량(2024~26 매출의 대부분)이 없다 — 화해 ratio 는
낮고 시간이 갈수록 오른다. 절대 신조선가 수준(2021 이후 호황)은 원장 안에서 알 수 없어 코호트는 상대 등급이다.
HD한국조선해양(009540)이 「자회사의 주요경영사항」으로 낸 계약 중 HD현대重(329180) 자체 공시와 같은 계약은
(선종·척수·금액·수주일)로 짝을 찾아 두 쪽에 shared_with 를 적고, 지주 파일의 합계에서는 뺀다(합산 금지).

assets/newbuild_index.json (선택 — 있으면 reference_anchor 의 표보다 우선; 2026-09-30 현재 없음, 형식만 정의):
    {"source": "예: Clarksons Newbuilding Price Index 연평균", "as_of": "YYYY-MM-DD", "unit": "index",
     "by_year": {"2020": 127.0, "2021": 153.6, "2022": 162.0},                       # 수주연도 → 지수
     "grades": [[0, "①적자"], [110, "②BEP"], [125, "③중마진"], [145, "④호황"], [160, "⑤초호황"]],   # [지수 하한, 등급] 오름차순
     "cohort_by_year": {"2021": "④호황"}}                                             # (선택) 연도 직접 지정 — by_year×grades 보다 우선
    지수에 없는 연도는 COHORT_BY_ORDER_YEAR 표로 돌아가고 계약의 cohort_detail.rule 에 그렇게 적는다.

    python3 kship_sls.py --all [--curve linear|s_curve] [--spot 1350] [--cohort-mode reference_anchor|ledger_relative] [--report]
                         [--opm-table assumed|reference_calibrated] [--hedge-default 0.7] [--today YYYY-MM-DD]
    python3 kship_sls.py --stock 010140 --report
"""
import argparse
import collections
import datetime
import json
import os
import re
import statistics
import sys

from kship_lib import ASSETS, load_asset, write_asset, q_next, q_of, q_range
from kship_page import series_groups            # 반복건조(시리즈) 추정 — 정의를 한 곳에만 둔다

YARDS_CACHE = os.path.join(ASSETS, "yards_cache")
SLS_DIR = os.path.join(ASSETS, "sls")
YARDS = ["010140", "042660", "329180", "439260", "097230"]
HOLDING = "009540"
HOLDING_SHARES_WITH = "329180"
NAMES = {"010140": "삼성중공업", "042660": "한화오션", "329180": "HD현대중공업", "439260": "대한조선",
         "097230": "HJ중공업", "009540": "HD한국조선해양"}
FX_CONST = 1350.0
HEDGE_RATIO_DEFAULT = 0.7
FORECAST_WINDOW = ("2026Q3", "2028Q4")
COHORT_LABELS = {1: "①적자", 2: "②BEP", 3: "③중마진", 4: "④호황", 5: "⑤초호황"}
COHORT_OPM = {"①적자": -0.05, "②BEP": 0.0, "③중마진": 0.05, "④호황": 0.10, "⑤초호황": 0.15}
# ── 레퍼런스 실측값(2026-10-05 두 원본 xlsx 의 SLS 시트를 읽어 확인) ──
# HEDGE 행: 미포 `SLS`!E56:X56 = 0.65, 삼성重 `SLS`!E47:X47 = 1.0 — 2008~2027 전 연도 같은 상수. 우리 0.7 은 두 값 사이에 둔 가정이며 레퍼런스 값이 아니다.
REFERENCE_HEDGE = collections.OrderedDict([("HD현대미포 010620 SLS!HEDGE", 0.65), ("삼성중공업 010140 SLS!HEDGE", 1.0)])
# 코호트 OPM 표 선택(⑦): assumed = 위 COHORT_OPM, reference_calibrated = 레퍼런스 미포 SLS 의 코호트별 유효 OPM(아래). 기본은 assumed —
# 하류(kship_model `_sls_frozen`, 섹션 각주의 표 문구)가 가정 표를 전제하므로 바꾸는 것은 오너 결정. 어느 쪽이든 두 표를 파일에 같이 적는다.
OPM_TABLES = ("assumed", "reference_calibrated")
OPM_TABLE_DEFAULT = "assumed"
COHORT_CALIB_WINDOW = (2023, 2027)          # 레퍼런스에서 유효 OPM 을 모을 연도 — 우리 예측창(2026Q3~2028Q4)과 겹치는 레퍼런스 기간(2023~24 는 레퍼런스의 확정·잠정 연도)
# 레퍼런스 HD현대미포 subQ `SLS` 시트 'ⓞ OPM 잡기' 블록(행 79~129, 미포 울산 별도; AC 열 = 코호트 머리, AD 열 = 셀 OPM, AE..DF = 1Q08~4Q27 분기 매출 백만$)을
# 코호트×매출연도로 모은 유효 OPM(= Σ 셀매출×셀OPM ÷ Σ 셀매출)과 그 매출(백만$). 비나신 블록(행 131~)은 제외 — 시트의 SLSOPM미포별도(행 3)와 같은 범위.
# 검산: 2Q26 전체 가중 0.10290 = 행 3 `미포_OPM` 2Q26 셀값 0.102897 (2026-10-05 openpyxl data_only 로 읽음). 소수 4자리·1자리로 반올림해 실었다.
COHORT_REFERENCE_EFFECTIVE_OPM = collections.OrderedDict([
    ("①적자", collections.OrderedDict([(2022, (-0.0178, 774.2)), (2023, (-0.0112, 281.8)), (2024, (-0.0100, 157.2))])),
    ("②BEP", collections.OrderedDict([(2022, (0.0100, 199.0)), (2023, (0.0100, 82.4)), (2024, (0.0100, 4.1)), (2025, (0.0100, 84.0)), (2026, (0.0100, 269.8))])),
    ("③중마진", collections.OrderedDict([(2022, (0.0500, 960.2)), (2023, (0.0477, 1147.9)), (2024, (0.0305, 485.0))])),
    ("④호황", collections.OrderedDict([(2022, (0.0527, 81.9)), (2023, (0.0567, 660.1)), (2024, (0.0524, 1023.5)), (2025, (0.0500, 54.7))])),
    ("⑤초호황", collections.OrderedDict([(2022, (0.0675, 11.1)), (2023, (0.0902, 85.7)), (2024, (0.0826, 1314.1)), (2025, (0.1110, 2195.8)),
                                      (2026, (0.1108, 5785.4)), (2027, (0.1106, 4813.1))]))])
# 같은 시트 행 3 `SLSOPM미포별도`(미포_OPM) 분기값의 연 단순평균(0 인 미작성 분기 제외; 2027 은 1Q·2Q 만 0.1092) — 위 블록을 분기 가중한 결과와 같은 것
REF_MIPO_SLS_OPM_BY_YEAR = collections.OrderedDict([(2022, 0.0198), (2023, 0.0437), (2024, 0.0589), (2025, 0.1069), (2026, 0.1057), (2027, 0.1092)])
# 같은 시트 행 2 `실제 OPM` 은 1Q08~4Q13 만 값이 있다(그 시기 ④⑤ 노출 ≈ 0) — ④⑤ 캘리브레이션에 쓸 수 없어 범위만 적는다
REF_MIPO_ACTUAL_OPM_ROW = {"label": "SLS 행 2 '실제 OPM'", "coverage": "1Q08~4Q13", "usable": False,
                           "why": "2014 이후 비어 있고 2008~13 매출의 ④⑤ 비중이 0~5% 라 ④⑤ OPM 을 식별할 수 없다"}
COHORT_METHOD = ("척당 금액 = amt_usd_m ÷ ships. (1) 연도 시장 수준: 선종별로 표본 2건 이상인 연도의 척당 중위를 "
                 "그 선종의 첫 연도 중위로 나눈 비율의 선종 간 중위 = year_index(각 선종의 첫 표본 연도 = 1.0 이라 여러 연도가 1.0 일 수 있다). "
                 "year_index <0.90 → ②, 0.90~1.10 → ③, 1.10~1.25 → ④, ≥1.25 → ⑤ 가 연도 기본등급. "
                 "(2) 셀 위치: 같은 선종·같은 수주연도(표본 2건 이상) 중위 대비 <0.90 → −1, >1.10 → +1 (표본 부족이면 "
                 "선종 전체 중위 ÷ year_index 로 대체). 1~5 로 자름. 외부 신조선가 지수 없음 — 원장(2024~ 공시) 안의 "
                 "상대 등급이며 2021 이후 절대 호황 수준은 반영하지 못한다. 척수 없는 계약(공사·해양 EPC 등)은 등급 없음.")
# ── 코호트 모드(§5-2) ── 기본 reference_anchor, 대안 ledger_relative(위 COHORT_METHOD). 둘 다 계산해 저장한다.
COHORT_MODES = ("reference_anchor", "ledger_relative")
COHORT_MODE_DEFAULT = "reference_anchor"
# 레퍼런스(HD현대미포 subQ 'SLS' 시트) 매출연도별 코호트 비중(백만$) — 사용자 레퍼런스 모델, 클락슨 선표 기반 판정. 표는 그대로 파일에 싣는다.
COHORT_REFERENCE_MIX_USD_M = collections.OrderedDict([
    ("2024", collections.OrderedDict([("⑤초호황", 1647), ("④호황", 1305), ("③중마진", 485), ("①적자", 157), ("②BEP", 8)])),
    ("2025", collections.OrderedDict([("⑤초호황", 3018), ("④호황", 78), ("②BEP", 84)])),
    ("2026", collections.OrderedDict([("⑤초호황", 6522), ("②BEP", 270)])),
    ("2027", collections.OrderedDict([("⑤초호황", 5857)]))])
# 수주연도 → 등급 (하한 연도, 상한 연도, 등급; None = 열림). 매출연도를 건조기간 2~3년만큼 되돌린 것:
# 2024 매출(수주 2021~22 인도분) ⑤ 46%·④ 36%·③ 13% → 2022 수주 ⑤·2021 수주 ④·그 전(저가 수주 잔량) ③; 2025~27 매출(수주 2022~25) ⑤ 95~100%.
COHORT_BY_ORDER_YEAR = ((None, 2020, "③중마진"), (2021, 2021, "④호황"), (2022, None, "⑤초호황"))
COHORT_BUILD_LAG_YEARS = "2~3"
COHORT_SOURCE = ("사용자 레퍼런스 모델(HD현대미포 subQ 'SLS' 시트, 클락슨 선표 기반 코호트 판정)의 매출연도별 코호트 비중(백만$)을 "
                 "건조기간 2~3년으로 수주연도에 되돌린 표(가정). 외부 신조선가 지수 미보유 — assets/newbuild_index.json 이 있으면 그것을 우선")
COHORT_REFERENCE_METHOD = ("수주연도만으로 등급: ≤2020 ③중마진, 2021 ④호황, 2022 이후 ⑤초호황(COHORT_BY_ORDER_YEAR). 근거: 레퍼런스 미포 SLS 매출연도별 "
                           "코호트(백만$) 2024 ⑤1,647·④1,305·③485·①157·②8 / 2025 ⑤3,018·④78·②84 / 2026 ⑤6,522·②270 / 2027 ⑤5,857 을 건조 2~3년 "
                           "되돌림. 대상은 ledger_relative 와 같이 선종·척수 있는 신조 계약(공사·EPC·방산 체계개발 등 척수 없는 계약은 등급 없음). "
                           "assets/newbuild_index.json 이 있으면 그 지수(by_year × grades, cohort_by_year 직접 지정 우선)가 표보다 우선.")
NEWBUILD_INDEX = os.path.join(ASSETS, "newbuild_index.json")
# 정기보고서 II-4 기납품 열의 성격(kship_forecast.load_reports 와 같은 판정): HJ·삼성重 은 프로젝트 누계(같은 해 차분만),
# 나머지는 연초 누계(YTD). 삼성重 은 매출표가 있어 기납품을 쓰지 않는다.
DELIVERED_STYLE = {"097230": "project_cumulative", "010140": "project_cumulative"}
_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_NOTE_FX = re.compile(r"(?:USD|US\$)\s*1\s*=\s*([0-9,]+(?:\.\d+)?)\s*원")


# ── 날짜·분기 ───────────────────────────────────────────────

def _date(s):
    m = _DATE.match((s or "").strip())
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def q_of_date(d):
    return q_of(d.year, d.month)


def q_bounds(q):
    y, n = int(q[:4]), int(q[5])
    s = datetime.date(y, 3 * (n - 1) + 1, 1)
    m = 3 * n
    e = datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)
    return s, e


def q_prev(q):
    y, n = int(q[:4]), int(q[5])
    return "%dQ%d" % (y - (n == 1), 4 if n == 1 else n - 1)


# ── 진행률 스케줄 ───────────────────────────────────────────

def _smoothstep(t):
    return t * t * (3.0 - 2.0 * t)


def round_schedule(sched, amt, nd=3):
    """분기값을 nd 자리로 반올림하고 잔차를 마지막 분기에 얹어 합이 amt(반올림)와 정확히 같게 한다
    (93분기짜리 장기 공사에서 반올림 누적이 0.03 백만$ 까지 벌어진다)."""
    out = collections.OrderedDict((q, round(v, nd)) for q, v in sched.items())
    if out and amt is not None:
        last = next(reversed(out))
        out[last] = round(out[last] + (round(amt, nd) - sum(out.values())), nd)
    return out


def schedule(start, end, amt, curve="linear"):
    """start~end(둘 다 포함)를 분기로 쪼개 amt 를 배분한다. 합 = amt(부동소수 오차만).
    linear: 일수 비례. s_curve: 누적 진행률 F(t) = 3t² − 2t³ (초·후반 완만, 중반 집중 — 가정)."""
    if amt is None or start is None or end is None or end < start:
        return collections.OrderedDict()
    total = (end - start).days + 1
    out = collections.OrderedDict()
    for q in q_range(q_of_date(start), q_of_date(end)):
        qs, qe = q_bounds(q)
        a, b = max(qs, start), min(qe, end)
        t0 = (a - start).days / total
        t1 = ((b - start).days + 1) / total
        f = (t1 - t0) if curve == "linear" else (_smoothstep(t1) - _smoothstep(t0))
        out[q] = amt * f
    return out


# ── 원장 정리: 정정·공유 ────────────────────────────────────

def apply_supersedes(rows):
    """정정공시가 가리키는 원본(supersedes)이 원장에 남아 있으면 지운다 — 새 판만 남긴다.
    kship_contracts --build 가 이미 지웠으면 아무 일도 없다. 반환: (남은 행, 지운 rcp 목록)."""
    superseded = {r["supersedes"] for r in rows if r.get("supersedes")}
    present = {r["rcp"] for r in rows}
    kept = [r for r in rows if r["rcp"] not in superseded]
    return kept, sorted(superseded & present)


def _share_key(r):
    return (r.get("type"), r.get("ships"), round(r.get("amt_krw_m") or 0.0, 1), r.get("signed"))


def mark_shared(rows, holding=HOLDING, yard=HOLDING_SHARES_WITH):
    """지주(009540)가 「자회사의 주요경영사항」으로 낸 계약과 HD현대重(329180) 자체 공시가 같은 계약이면
    (선종·척수·금액·수주일)로 짝짓는다 — rcp 는 두 회사가 각각 접수해 서로 다르다. 두 쪽 다 shared_with 를 적고
    지주 쪽에는 shared_owner 를 둔다(합계에서 뺄 표지). 반환: [(지주 rcp, 조선사 rcp)] 정렬."""
    yard_rows = collections.defaultdict(list)
    for r in sorted(rows, key=lambda r: r["rcp"]):
        if r["stock"] == yard:
            yard_rows[_share_key(r)].append(r)
    pairs = []
    for r in sorted(rows, key=lambda r: r["rcp"]):
        if r["stock"] != holding:
            continue
        cands = yard_rows.get(_share_key(r)) or []
        if not cands:
            continue
        y = cands[0]
        r["shared_with"] = "%s:%s" % (yard, y["rcp"])
        r["shared_owner"] = yard
        y["shared_with"] = "%s:%s" % (holding, r["rcp"])
        pairs.append((r["rcp"], y["rcp"]))
    return sorted(pairs)


_SUB_YARD = re.compile(r"(현대삼호|현대미포|현대중공업)")
CONTRACTS_CACHE = os.path.join(ASSETS, "contracts")


def sub_yard_of(row):
    """지주 공시의 실제 건조 조선소. 공시 머리 '자회사인 에이치디현대삼호(주)의 주요경영사항신고' 가 원문 캐시
    (assets/contracts/<stock>/<rcp>.json, kv 첫 항목)에 남아 있다 — 그것을 먼저, 없으면 본문 note 의
    '최근매출액은 …(주)의' 를 읽는다(읽기만 한다). 없으면 None."""
    p = os.path.join(CONTRACTS_CACHE, row["stock"], "%s.json" % row["rcp"])
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                kv = json.load(f).get("kv") or []
        except (OSError, ValueError):
            kv = []
        for it in kv:
            lab = it[0] if isinstance(it, (list, tuple)) and it else ""
            if "자회사" in lab:
                m = _SUB_YARD.search(lab)
                if m:
                    return m.group(1)
    m = _SUB_YARD.search(row.get("note") or "")
    return m.group(1) if m else None


# ── 환율 ────────────────────────────────────────────────────

def load_fx():
    p = os.path.join(ASSETS, "fx.json")
    return load_asset("fx.json") if os.path.exists(p) else None


def fx_quarter(fx, q, const):
    """분기 USDKRW 평균: fx.json quarters(과거) → forward(미래) → daily_last → 상수. (값, 출처).
    const=None 이면 상수 폴백 없이 (None, None) — fx_at_sign 이 다음 우선순위(약정환율·상수)로 넘어가게 한다
    (전에는 '%g' % None 으로 죽었다: fx.json 에 없는 분기에 수주한 계약 하나가 빌드 전체를 멈춘다)."""
    if fx:
        qd = (fx.get("quarters") or {}).get(q) or {}
        v = qd.get("USDKRW_avg")
        if v:
            # 진행 중인 분기는 fx.json 이 partial 로 표시한다(며칠치 평균) — 어느 값을 썼는지 읽는 쪽이 알 수 있게 출처에 남긴다
            return float(v), ("fx.json quarters(partial %sd)" % qd.get("days", "?")) if qd.get("partial") else "fx.json quarters"
        v = ((fx.get("forward") or {}).get(q) or {}).get("USDKRW_avg")
        if v:
            return float(v), "fx.json forward"
        v = (fx.get("daily_last") or {}).get("USDKRW")
        if v:
            return float(v), "fx.json daily_last(flat)"
    if const is None:
        return None, None
    return const, "const_%g" % const


def fx_quarter_end(fx, q):
    """분기 기말 원/달러: fx.json quarters → forward → daily_last. 없으면 (None, None). 잔고(시점 값) 환산용."""
    if fx:
        for key, src in (("quarters", "fx.json quarters USDKRW_end"), ("forward", "fx.json forward USDKRW_end")):
            v = ((fx.get(key) or {}).get(q) or {}).get("USDKRW_end")
            if v:
                return float(v), src
        v = (fx.get("daily_last") or {}).get("USDKRW")
        if v:
            return float(v), "fx.json daily_last"
    return None, None


def fx_at_sign(row, fx, yq, const):
    """수주시점 환율. 공시 본문 고시환율 > fx.json > 회사 헤지 평균약정환율(약정, 현물 아님) > 상수."""
    m = _NOTE_FX.search(row.get("note") or "")
    if m:
        return float(m.group(1).replace(",", "")), "disclosure_note"
    d = _date(row.get("signed")) or _date(row.get("start"))
    q = q_of_date(d) if d else None
    if q and fx:
        v, src = fx_quarter(fx, q, None)
        if v:
            return v, src
    if q and q in yq:
        rate = ((yq[q].get("hedge") or {}).get("avg_rate"))
        if rate:
            return float(rate), "yards_cache hedge.avg_rate(약정환율)"
    return const, "const_%g" % const


# ── yards_cache 읽기 ────────────────────────────────────────

def load_yards():
    out = {}
    if not os.path.isdir(YARDS_CACHE):
        return out
    for stock in sorted(os.listdir(YARDS_CACHE)):
        d = os.path.join(YARDS_CACHE, stock)
        if not os.path.isdir(d):
            continue
        qs = {}
        for f in sorted(os.listdir(d)):
            if not f.endswith(".json"):
                continue
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                x = json.load(fh)
            if x.get("ok"):
                qs[x["quarter"]] = x
        out[stock] = qs
    return out


def closing_total(snapshot):
    """기말 수주잔고 합계(백만원). 합계 행이 부문합과 1% 넘게 어긋나면 부문합(kship_page.yard_summary 와 같은 판정)."""
    o = (snapshot or {}).get("orders") or {}
    rows = o.get("rows") or []
    tot = [r for r in rows if r.get("total")]
    segs = [r for r in rows if not r.get("total")]
    seg_sum = sum((r.get("closing") or 0) for r in segs) if any(r.get("closing") is not None for r in segs) else None
    closing = tot[0].get("closing") if tot else seg_sum
    if tot and seg_sum and closing is not None and abs(closing - seg_sum) > 0.01 * seg_sum:
        closing = seg_sum
    return closing


def hedge_params(stock, yq, default_ratio=HEDGE_RATIO_DEFAULT, fx=None):
    """헤지비율 실측: 최신 분기 usd_sell_m ÷ (기말잔고 원화 ÷ 평균약정환율). 약정환율이 없으면 가정 default_ratio(0.7).
    약정환율이 없어도 명목액이 공시돼 있으면 fx.json 기말 현물로 환산한 참고치를 hedge_ratio_implied_spot 에 둔다
    (적용값은 아니다 — 삼성重 은 이 참고치가 1.0 안팎, HD현대重 은 0.45 안팎으로 0.7 가정과 다르다는 것을 숨기지 않기 위해).
    수주시점 평균환율로 환산한 둘째 참고치(hedge_ratio_implied_sign_rate)는 계약이 필요해 build() 가 채운다.
    0.7 의 출처: 레퍼런스 SLS 시트 HEDGE 행은 미포 0.65 · 삼성重 1.00 (REFERENCE_HEDGE) — 0.7 은 그 사이에 둔 **가정**이지 레퍼런스 값이 아니다."""
    qs = sorted(yq)
    latest = yq[qs[-1]] if qs else None
    hedge = (latest or {}).get("hedge") or {}
    usd_sell, rate = hedge.get("usd_sell_m"), hedge.get("avg_rate")
    closing = closing_total(latest)
    base = {"quarter": qs[-1] if qs else None, "usd_sell_m": usd_sell, "backlog_krw_m": closing, "hedge_rate": rate,
            "hedge_ratio_implied_spot": None, "implied_spot_rate": None, "implied_basis": None,
            "hedge_ratio_implied_sign_rate": None, "implied_sign_rate": None, "implied_sign_n": None, "implied_sign_basis": None,
            "reference_hedge": collections.OrderedDict(REFERENCE_HEDGE),
            "reference_hedge_note": "레퍼런스 두 원본의 SLS!HEDGE 행(2008~2027 전 연도 상수) 실측값. 가정 %.2f 은 레퍼런스 값이 아니라 그 범위 안의 설정값(--hedge-default)" % default_ratio}
    if usd_sell and rate and closing:
        raw = usd_sell / (closing / rate)
        base.update(hedge_ratio=round(min(max(raw, 0.0), 1.0), 4), hedge_ratio_raw=round(raw, 4), kind="measured",
                    basis="usd_sell_m ÷ (기말 수주잔고 원화 ÷ 평균약정환율), %s 정기보고서 위험관리 절 — kship_page.yard_summary 방식" % qs[-1])
    else:
        why = "약정환율 미공시" if usd_sell else "통화선도 공시 없음"
        base.update(hedge_ratio=default_ratio, hedge_ratio_raw=None, kind="estimate",
                    basis="%s → HEDGE %.0f%% 가정(레퍼런스 SLS 시트 HEDGE 행은 미포 65%%·삼성重 100%% — 그 사이에 둔 설정값). hedge_rate 는 계약별 수주시점 환율로 대체"
                          % (why, default_ratio * 100))
        if usd_sell and closing and qs:
            spot_end, spot_src = fx_quarter_end(fx, qs[-1])
            if spot_end:
                base.update(hedge_ratio_implied_spot=round(usd_sell / (closing / spot_end), 4), implied_spot_rate=spot_end,
                            implied_basis=("usd_sell_m ÷ (기말 수주잔고 원화 ÷ %s 기말 원/달러 %.2f, %s) — 약정환율이 아닌 현물 환산 "
                                           "참고치(kind estimate). 적용 hedge_ratio 는 %.2f 가정 그대로" % (qs[-1], spot_end, spot_src, default_ratio)))
    return base


def hedge_implied_sign_rate(hedge, cands):
    """⑦ 둘째 참고치: usd_sell_m ÷ (기말 수주잔고 원화 ÷ 수주시점 평균환율). 평균환율 = origin 분기말까지 체결된 counted 계약(cands)의
    원화 합 ÷ 달러 합(금액가중 조화평균 — 잔고가 장부에 실린 환율에 가장 가깝다). 약정환율 공시가 없는 회사(kind estimate)에서만 채우고
    적용값(hedge_ratio)은 바꾸지 않는다. 계약·명목액·잔고 중 하나라도 없으면 그대로 둔다. hedge 를 제자리에서 고치고 돌려준다."""
    if hedge.get("kind") != "estimate" or not hedge.get("usd_sell_m") or not hedge.get("backlog_krw_m"):
        return hedge
    krw = sum((c.get("amt_krw_m") or 0.0) for c in cands)
    usd = sum((c.get("amt_usd_m") or 0.0) for c in cands)
    if not usd or not krw:
        return hedge
    rate = krw / usd
    hedge["implied_sign_rate"] = round(rate, 2)
    hedge["implied_sign_n"] = len(cands)
    hedge["hedge_ratio_implied_sign_rate"] = round(hedge["usd_sell_m"] / (hedge["backlog_krw_m"] / rate), 4)
    hedge["implied_sign_basis"] = ("usd_sell_m ÷ (기말 수주잔고 원화 ÷ 수주시점 평균환율 %.2f = origin 까지 체결 counted 계약 %d건의 원화 합 ÷ 달러 합) — "
                                   "잔고가 장부에 실린 환율 기준의 참고치(kind estimate). 적용 hedge_ratio 는 %.2f 가정 그대로" % (rate, len(cands), hedge["hedge_ratio"]))
    return hedge


def _norm_seg(s):
    return re.sub(r"\s+|\(\*\)|\*", "", s or "")


def _marine_pred(stock):
    if stock == "010140":
        return lambda s: s == "조선해양"
    if stock == "042660":
        return lambda s: s.startswith("상선") or "특수선" in s
    if stock == "329180":
        return lambda s: s in ("조선", "해양플랜트")
    if stock == "439260":
        return lambda s: s == "선박"
    if stock == "097230":
        return lambda s: s in ("특수선", "상선", "신조선", "방산")
    return lambda s: s and not any(k in s for k in ("기타", "토건", "합계", "엔진", "건설", "플랜트"))


def reported_marine_3m(stock, yq):
    """정기보고서 부문 매출의 **3개월분**(백만원): 매출표(첫 열 = 당해 누계)가 있으면 그것을, 없으면 기납품 누계를
    쓴다. 누계 → Q1 은 그대로, 그 외는 직전 분기 누계와의 차분(Q4 = 연간 − 3Q 누계). 프로젝트 누계(HJ)는 같은 해
    차분만 쓰고 Q1 은 비운다(kship_forecast.recognition 과 같은 규칙). 반환 {q: {"value", "source", "segments"}}."""
    pred = _marine_pred(stock)
    style = DELIVERED_STYLE.get(stock, "ytd")
    cum = {}
    for q in sorted(yq):
        j = yq[q]
        rev = j.get("revenue") or {}
        val, segs, src = None, [], None
        if rev.get("rows") and (rev.get("cur") or "KRW") == "KRW":
            groups = collections.defaultdict(list)
            for r in rev["rows"]:
                groups[_norm_seg(r.get("seg"))].append(r)
            tot, ok = 0.0, False
            for seg in sorted(groups):
                if not seg or seg == "합계" or not pred(seg):
                    continue
                rs = groups[seg]
                t = [r for r in rs if r.get("kind") == "합계" and r.get("vals") and r["vals"][0] is not None]
                if t:
                    v = t[0]["vals"][0]
                else:
                    ch = [r["vals"][0] for r in rs if r.get("kind") != "합계" and r.get("vals") and r["vals"][0] is not None]
                    v = sum(ch) if ch else None
                if v is not None:
                    tot, ok = tot + v, True
                    segs.append(seg)
            if ok:
                val, src = tot, "revenue_table_ytd"
        if val is None:
            o = j.get("orders") or {}
            rows = [r for r in (o.get("rows") or []) if not r.get("total")]
            if rows and (o.get("cur") or "KRW") == "KRW":
                tot, ok = 0.0, False
                for r in sorted(rows, key=lambda r: _norm_seg(r.get("seg"))):
                    seg = _norm_seg(r.get("seg"))
                    if pred(seg) and r.get("delivered") is not None:
                        tot, ok = tot + r["delivered"], True
                        segs.append(seg)
                if ok:
                    val, src = tot, ("delivered_%s" % style)
        if val is not None:
            cum[q] = {"cum": val, "source": src, "segments": segs}
    out = {}
    for q in sorted(cum):
        c = cum[q]
        p = cum.get(q_prev(q))
        same_year = p is not None and q_prev(q)[:4] == q[:4]
        if c["source"] == "delivered_project_cumulative":
            v = (c["cum"] - p["cum"]) if same_year else None
        elif q.endswith("Q1"):
            v = c["cum"]
        else:
            v = (c["cum"] - p["cum"]) if same_year else None
        if v is not None:
            out[q] = {"value": round(v, 1), "source": c["source"], "segments": c["segments"], "cum": c["cum"]}
    return out


# ── 코호트 ──────────────────────────────────────────────────

def _median(xs):
    return statistics.median(xs) if xs else None


def cohorts(contracts):
    """원장 전체(공유 중복 제외)에서 척당 금액으로 ①~⑤ 를 매긴다. 반환 {rcp: {"cohort", ...근거}}, year_index."""
    elig = [c for c in contracts if c.get("type") not in (None, "OTHER") and c.get("ships") and c.get("amt_usd_m")
            and c.get("year") and not c.get("shared_owner")]
    cell = collections.defaultdict(list)
    type_all = collections.defaultdict(list)
    for c in elig:
        ps = c["amt_usd_m"] / c["ships"]
        cell[(c["type"], c["year"])].append(ps)
        type_all[c["type"]].append(ps)
    ratios = collections.defaultdict(list)
    for t in sorted(type_all):
        years = sorted(y for (tt, y) in cell if tt == t and len(cell[(tt, y)]) >= 2)
        if len(years) < 2:
            continue
        base = _median(cell[(t, years[0])])
        for y in years:
            ratios[y].append(_median(cell[(t, y)]) / base)
    year_index = {y: round(_median(ratios[y]), 4) for y in sorted(ratios)}
    out = {}
    for c in elig:
        t, y = c["type"], c["year"]
        ps = c["amt_usd_m"] / c["ships"]
        level = year_index.get(y, 1.0)
        base_grade = 2 if level < 0.90 else 3 if level < 1.10 else 4 if level < 1.25 else 5
        cell_n = len(cell[(t, y)])
        if cell_n >= 2:
            ref, ref_kind = _median(cell[(t, y)]), "type_year_median"
            rel = ps / ref
        else:
            ref, ref_kind = _median(type_all[t]), "type_all_median/year_index"
            rel = ps / ref / level if ref else 1.0
        adj = -1 if rel < 0.90 else 1 if rel > 1.10 else 0
        g = min(5, max(1, base_grade + adj))
        out[c["rcp"]] = {"cohort": COHORT_LABELS[g], "per_ship_usd_m": round(ps, 2), "ref_usd_m": round(ref, 2),
                         "ref_kind": ref_kind, "cell_n": cell_n, "rel": round(rel, 3), "year_index": level}
    return out, year_index


def load_newbuild_index(path=NEWBUILD_INDEX):
    """assets/newbuild_index.json(선택; 형식은 모듈 docstring). 없거나 by_year·cohort_by_year 가 모두 없으면 None — 표로 간다."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            x = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(x, dict) or not (x.get("by_year") or x.get("cohort_by_year")):
        return None
    return x


def cohort_by_order_year(year, index=None):
    """수주연도 → (등급, 규칙 문장). index(newbuild_index.json 내용)가 있으면 우선: cohort_by_year 직접 지정 > by_year 지수 × grades 문턱.
    지수에 없는 연도·지수 없음 → COHORT_BY_ORDER_YEAR 표. 연도 없음 → (None, '연도 없음')."""
    if year is None:
        return None, "연도 없음"
    if index:
        direct = (index.get("cohort_by_year") or {}).get(str(year))
        if direct in COHORT_OPM:
            return direct, "newbuild_index.cohort_by_year %s" % year
        v = (index.get("by_year") or {}).get(str(year))
        grades = index.get("grades") or []
        if v is not None and grades:
            label = None
            for g in sorted(grades, key=lambda g: float(g[0])):
                if float(v) >= float(g[0]) and g[1] in COHORT_OPM:
                    label = g[1]
            if label:
                return label, "newbuild_index.by_year %s=%g × grades" % (year, float(v))
    for lo, hi, label in COHORT_BY_ORDER_YEAR:
        if (lo is None or year >= lo) and (hi is None or year <= hi):
            return label, "COHORT_BY_ORDER_YEAR %s~%s → %s" % (lo if lo is not None else "", hi if hi is not None else "", label)
    return None, "표 밖"


def cohorts_reference(contracts, index=None):
    """reference_anchor 모드: 수주연도만으로 ①~⑤(표 COHORT_BY_ORDER_YEAR, 지수 파일 있으면 우선). 대상은 cohorts()(ledger_relative)와
    **같은 집합** — 선종·척수·금액·연도 있는 신조 계약, 지주의 공유 계약(shared_owner) 제외. 공사·EPC·방산 체계개발 등 척수 없는 계약은
    신조선가 코호트가 아니라 등급 없음. 반환 {rcp: {...}}."""
    out = {}
    for c in contracts:
        if (c.get("type") in (None, "OTHER") or not c.get("ships") or not c.get("amt_usd_m") or not c.get("year")
                or c.get("shared_owner")):
            continue
        label, rule = cohort_by_order_year(c["year"], index)
        if label:
            out[c["rcp"]] = {"cohort": label, "order_year": c["year"], "rule": rule,
                             "source": "assets/newbuild_index.json" if rule.startswith("newbuild_index") else "reference_anchor(사용자 레퍼런스 모델, 클락슨 기반 판정)"}
    return out


def cohort_table(index=None, opm_table=COHORT_OPM):
    """파일 최상위 cohort_table — 수주연도 표·레퍼런스 매출연도 비중(백만$ 와 비중)·OPM 표(실제 적용 표)·지수 파일 유무. 전부 가정(kind estimate)."""
    share = collections.OrderedDict()
    for y, mix in COHORT_REFERENCE_MIX_USD_M.items():
        tot = float(sum(mix.values()))
        share[y] = collections.OrderedDict((k, round(v / tot, 3)) for k, v in mix.items())
    return collections.OrderedDict([
        ("kind", "estimate"),
        ("by_order_year", [collections.OrderedDict([("from", lo), ("to", hi), ("cohort", lab)]) for lo, hi, lab in COHORT_BY_ORDER_YEAR]),
        ("build_lag_years", COHORT_BUILD_LAG_YEARS),
        ("reference_revenue_year_mix_usd_m", COHORT_REFERENCE_MIX_USD_M),
        ("reference_revenue_year_share", share),
        ("opm_table", opm_table),
        ("newbuild_index", collections.OrderedDict([("path", "assets/newbuild_index.json"), ("present", bool(index)),
                                                    ("source", (index or {}).get("source")), ("as_of", (index or {}).get("as_of"))])),
        ("basis", "레퍼런스 매출연도 코호트 비중을 건조기간 2~3년으로 수주연도에 되돌림 — 2024 매출(수주 2021~22) ⑤ 46%·④ 36%·③ 13% → 2022 수주 ⑤·"
                  "2021 수주 ④·그 전 ③(저가 수주 잔량); 2025~27 매출(수주 2022~25) ⑤ 95~100%. 가정이며 외부 신조선가 지수 미보유")])


def _target_opm(mix, usd_m, table=COHORT_OPM):
    """코호트별 매출$ 믹스 → (타겟 OPM, 등급 있는 비중). '등급없음' 은 분모에서 뺀다. table 은 적용 OPM 표(가정 또는 레퍼런스 캘리브레이션)."""
    graded = {k: v for k, v in mix.items() if k in table}
    gsum = sum(graded.values())
    return (round(sum(v * table[k] for k, v in graded.items()) / gsum, 4) if gsum else None,
            round(gsum / usd_m, 4) if usd_m else None)


def _opm_table_text(table):
    return " ".join("%s%s%%" % (k[0], ("%+.1f" % (table[k] * 100)).rstrip("0").rstrip(".").replace("+", "") if table[k] != 0 else "0")
                    for k in COHORT_LABELS.values() if k in table)


def cohort_opm_calibration(window=COHORT_CALIB_WINDOW, fin_is=None):
    """⑦ 코호트 ①~⑤ OPM 표를 레퍼런스 HD현대미포 SLS 로 캘리브레이션한다. 반환 (표, 근거 블록).
    표 = COHORT_REFERENCE_EFFECTIVE_OPM(레퍼런스 'ⓞ OPM 잡기' 셀 OPM 을 코호트×연도로 매출가중한 유효 OPM)을 window 연도 안에서 다시 매출가중한 값.
    블록에는 두 표, 연도별 괴리(레퍼런스 셀 가중 vs 가정 표 vs 캘리브레이션 표), 레퍼런스 SLS OPM 행, 미포 실측 OPM(assets/fin/010620.json 이 있으면)
    대조, '실제 OPM' 행이 못 쓰이는 이유를 적는다. 전부 kind estimate — 레퍼런스 모델 안의 가정을 모은 것이고 실측이 아니다."""
    lo, hi = window
    table = collections.OrderedDict()
    used = collections.OrderedDict()
    for coh in COHORT_LABELS.values():
        items = [(y, o, r) for y, (o, r) in COHORT_REFERENCE_EFFECTIVE_OPM.get(coh, {}).items() if lo <= y <= hi and r]
        den = sum(r for _, _, r in items)
        table[coh] = round(sum(o * r for _, o, r in items) / den, 4) if den else COHORT_OPM[coh]
        used[coh] = {"years": [y for y, _, _ in items], "usd_m": round(den, 1), "fallback_assumed": not den}
    years = sorted({y for m in COHORT_REFERENCE_EFFECTIVE_OPM.values() for y in m})
    by_year = collections.OrderedDict()
    for y in years:
        cells = [(coh, o, r) for coh, m in COHORT_REFERENCE_EFFECTIVE_OPM.items() for yy, (o, r) in m.items() if yy == y and r]
        den = sum(r for _, _, r in cells)
        if not den:
            continue
        ref = sum(o * r for _, o, r in cells) / den
        asm = sum(COHORT_OPM[c] * r for c, _, r in cells) / den
        cal = sum(table[c] * r for c, _, r in cells) / den
        by_year[str(y)] = collections.OrderedDict([
            ("usd_m", round(den, 1)), ("reference_cells", round(ref, 4)), ("reference_sls_row", REF_MIPO_SLS_OPM_BY_YEAR.get(y)),
            ("assumed_table", round(asm, 4)), ("calibrated_table", round(cal, 4)),
            ("gap_assumed_minus_reference", round(asm - ref, 4)), ("gap_calibrated_minus_reference", round(cal - ref, 4)),
            ("share", collections.OrderedDict((c, round(r / den, 4)) for c, _, r in cells))])
    actual = collections.OrderedDict()
    is_ = fin_is if fin_is is not None else _fin_is("010620")
    if is_:
        agg = collections.defaultdict(lambda: [0.0, 0.0, 0])
        for q in sorted(is_):
            rev, op = is_[q].get("매출액(수익)"), is_[q].get("영업이익")
            if rev and op is not None:
                a = agg[q[:4]]
                a[0] += rev
                a[1] += op
                a[2] += 1
        for y, (rev, op, n) in sorted(agg.items()):
            if y in by_year and n:
                actual[y] = collections.OrderedDict([("opm", round(op / rev, 4)), ("quarters", n),
                                                     ("reference_sls_minus_actual", round(by_year[y]["reference_cells"] - op / rev, 4))])
    block = collections.OrderedDict([
        ("kind", "estimate"),
        ("source", "사용자 레퍼런스 모델 HD현대미포 010620 subQ `SLS` 시트 'ⓞ OPM 잡기' 블록(행 79~129, 미포 울산 별도 — AC 코호트 머리 · AD 셀 OPM · AE..DF 분기 매출 백만$). "
                   "셀 OPM 은 애널리스트가 둔 가정이고 실측이 아니다. 비나신 블록(행 131~)은 제외"),
        ("method", "코호트별 유효 OPM = Σ 셀매출×셀OPM ÷ Σ 셀매출 (연도별) → window 연도 안에서 다시 매출가중. 검산: 2Q26 전체 가중 0.10290 = 시트 행 3 `미포_OPM` 2Q26 셀값"),
        ("window", {"from": lo, "to": hi, "why": "우리 예측창 2026Q3~2028Q4 와 겹치는 레퍼런스 기간(2023~24 는 레퍼런스의 확정·잠정 연도)"}),
        ("table_assumed", collections.OrderedDict((k, COHORT_OPM[k]) for k in COHORT_LABELS.values())),
        ("table_reference_calibrated", table),
        ("table_used_years", used),
        ("reference_effective_opm_by_cohort_year", collections.OrderedDict(
            (coh, collections.OrderedDict((str(y), {"opm": o, "usd_m": r}) for y, (o, r) in m.items())) for coh, m in COHORT_REFERENCE_EFFECTIVE_OPM.items())),
        ("by_year", by_year),
        ("reference_sls_opm_row", {"label": "SLS 행 3 `SLSOPM미포별도`(미포_OPM) 연 단순평균", "values": collections.OrderedDict((str(y), v) for y, v in REF_MIPO_SLS_OPM_BY_YEAR.items())}),
        ("reference_actual_opm_row", REF_MIPO_ACTUAL_OPM_ROW),
        ("actual_opm_fin_010620_by_year", actual),
        ("limits", ["레퍼런스 코호트 OPM 은 시대 의존 — 같은 ④호황 셀이 2016~20 매출에는 13~15%, 2022~25 매출에는 5% 안팎이라 단일 표는 단순화다",
                    "레퍼런스 SLS OPM 자체가 미포 실측(fin 연결)보다 높다(actual_opm_fin_010620_by_year.reference_sls_minus_actual) — 회사 실측과의 차는 calibration.calibrated_shift 가 담당",
                    "표를 바꿔도 등급(수주연도 → ①~⑤)은 그대로이므로 2022 이후 수주만 있는 회사의 타겟은 ⑤ 값(가정 15%% ↔ 캘리브레이션 %.1f%%) 상수가 된다" % (table["⑤초호황"] * 100)])])
    return table, block


def _cohort_basis(mode, detail):
    if not detail:
        return "척수 없음 또는 금액·연도 없음 → 등급 없음"
    if mode == "ledger_relative":
        return "amt_per_ship vs type-year median (contracts.json) × year_index; 신조선가 지수 미보유"
    return "수주연도 %s → %s (%s; 출처 %s — 레퍼런스 매출연도 코호트를 건조 2~3년 되돌림)" % (
        detail.get("order_year"), detail.get("cohort"), detail.get("rule"), detail.get("source"))


# ── 회사별 조립 ─────────────────────────────────────────────

def _duration_medians(rows):
    """선종별 계약기간(일) 중위 — 종료일 '-' 인 계약의 종료 추정에 쓴다."""
    d = collections.defaultdict(list)
    for r in rows:
        s, e = _date(r.get("start")) or _date(r.get("signed")), _date(r.get("end"))
        if s and e and e > s:
            d[r.get("type") or "OTHER"].append((e - s).days)
            d["_all"].append((e - s).days)
    return {k: int(_median(v)) for k, v in sorted(d.items())}


def prepare_contracts(rows, yards, fx, const):
    """원장 → 계약 레코드(달러화·기간 확정). 코호트·스케줄은 아직."""
    dur = _duration_medians(rows)
    out = []
    for r in sorted(rows, key=lambda r: (r["stock"], r["rcp"])):
        yq = yards.get(r["stock"]) or {}
        start = _date(r.get("start")) or _date(r.get("signed"))
        end = _date(r.get("end"))
        end_est = False
        if start and not end:
            days = dur.get(r.get("type") or "OTHER") or dur.get("_all")
            if days:
                end, end_est = start + datetime.timedelta(days=days), True
        rate, src = fx_at_sign(r, fx, yq, const)
        amt = r.get("amt_krw_m")
        signed = _date(r.get("signed")) or start
        c = {"rcp": r["rcp"], "stock": r["stock"], "name": r.get("name"), "type": r.get("type") or "OTHER",
             "ships": r.get("ships"), "amt_krw_m": amt, "fx_at_sign": round(rate, 2), "fx_source": src,
             "amt_usd_m": round(amt / rate, 3) if amt else None,
             "signed": r.get("signed"), "year": signed.year if signed else None,
             "start": start.isoformat() if start else None, "end": end.isoformat() if end else None,
             "end_estimated": end_est, "party_anon": bool(r.get("party_anon")), "party": r.get("party"),
             "option_hint": bool(r.get("option_hint")), "corrected": bool(r.get("corrected")),
             "supersedes": r.get("supersedes")}
        if r.get("shared_with"):
            c["shared_with"] = r["shared_with"]
        if r.get("shared_owner"):
            c["shared_owner"] = r["shared_owner"]
        if r["stock"] == HOLDING:
            c["sub_yard"] = sub_yard_of(r)
        out.append(c)
    # 반복건조(시리즈) 추정 표시 — kship_page.series_groups(est) 와 같은 묶음
    in_series = set()
    for g in series_groups([r for r in rows if r.get("type") not in (None, "OTHER")]):
        in_series.update(g["items"])
    for c in out:
        c["estimated_series"] = c["rcp"] in in_series or c["option_hint"]
    return out


def build(stock, contracts, cohort_map, year_index, yards, fx, curve, const, origin, mode=COHORT_MODE_DEFAULT, newbuild_index=None,
          opm_table=OPM_TABLE_DEFAULT, hedge_default=HEDGE_RATIO_DEFAULT, today=None):
    """한 회사의 sls json 을 만든다. contracts 는 prepare_contracts 결과 전체(모든 회사).
    cohort_map/year_index 는 ledger_relative 등급(cohorts()), reference_anchor 등급은 여기서 표(또는 newbuild_index)로 매긴다.
    mode 가 기본 모드(cohort·by_cohort·target_opm·calibration), 다른 모드는 *_alt 에 함께 저장한다(§5-2).
    opm_table 은 타겟 OPM 에 쓰는 표(assumed | reference_calibrated — ⑦), hedge_default 는 약정환율 미공시 회사의 헤지비율 가정,
    today 는 built_at(없으면 실행일). 잔고 캡(§5-2): 집계 전에 origin 커버리지를 재야 하므로 계약 루프를 두 번 돈다(스케줄·진행률 → 커버리지 → 집계)."""
    if mode not in COHORT_MODES:
        raise ValueError("cohort_mode %r — %s 중 하나" % (mode, "|".join(COHORT_MODES)))
    if opm_table not in OPM_TABLES:
        raise ValueError("opm_table %r — %s 중 하나" % (opm_table, "|".join(OPM_TABLES)))
    alt_mode = [m for m in COHORT_MODES if m != mode][0]
    maps = {"reference_anchor": cohorts_reference(contracts, newbuild_index), "ledger_relative": cohort_map}
    calib_table, calib_block = cohort_opm_calibration()
    table = COHORT_OPM if opm_table == "assumed" else calib_table
    table_text = "%s(%s — %s)" % (opm_table, _opm_table_text(table), "가정" if opm_table == "assumed" else "레퍼런스 미포 SLS 셀 OPM 매출가중")
    yq = yards.get(stock) or {}
    mine = [dict(c) for c in contracts if c["stock"] == stock]
    hedge = hedge_params(stock, yq, default_ratio=hedge_default, fx=fx)
    hr = hedge["hedge_ratio"]
    fx_cache = {}

    def spot(q):
        if q not in fx_cache:
            fx_cache[q] = fx_quarter(fx, q, const)
        return fx_cache[q]

    _, origin_end = q_bounds(origin)

    def _signed_by_origin(c):
        d = _date(c.get("signed")) or _date(c.get("start"))
        return d is not None and d <= origin_end

    # 1) 계약별 스케줄·코호트(두 모드)·origin 진행률
    scheds = {}
    warnings, skipped = [], []
    n_counted, n_shared_excluded = 0, 0
    for c in mine:
        s, e = _date(c["start"]), _date(c["end"])
        sched = schedule(s, e, c["amt_usd_m"], curve)
        scheds[c["rcp"]] = sched
        c["schedule"] = round_schedule(sched, c["amt_usd_m"])
        c["curve"] = "linear_progress" if curve == "linear" else "s_curve"
        pri, alt = maps[mode].get(c["rcp"]), maps[alt_mode].get(c["rcp"])
        c["cohort"] = pri["cohort"] if pri else None
        c["cohort_mode"] = mode
        c["cohort_detail"] = pri
        c["cohort_basis"] = _cohort_basis(mode, pri)
        c["cohort_alt"] = alt["cohort"] if alt else None
        c["cohort_alt_mode"] = alt_mode
        c["cohort_alt_detail"] = alt
        c["progress_at_origin"] = round(sum(v for q, v in sched.items() if q <= origin) / c["amt_usd_m"], 4) if sched and c["amt_usd_m"] else None
        c["remaining_usd_m_at_origin"] = round(sum(v for q, v in sched.items() if q > origin), 3) if sched else None
        c["signed_by_origin"] = _signed_by_origin(c)
        c["backlog_cap_applied"] = False
        if not sched:
            skipped.append({"rcp": c["rcp"], "why": "금액 없음" if not c["amt_usd_m"] else "기간 없음"})
            continue
        if c.get("shared_owner"):
            n_shared_excluded += 1
            c["counted"] = False
            continue
        c["counted"] = True
        n_counted += 1

    # 2) 잔고 커버리지 → 캡 배율(§5-2). origin 분기말까지 수주된 계약의 잔여 스케줄(해양) vs 그 분기 정기보고서 해양 부문 기말잔고.
    #    origin 뒤에 수주한 계약은 그 잔고에 없으므로 뺀다(대한조선 2026Q3 수주분이 2026Q2 잔고를 넘게 만들었다).
    latest_q = sorted(yq)[-1] if yq else None
    pred = _marine_pred(stock)
    segs = [r for r in ((yq[latest_q].get("orders") or {}).get("rows") or []) if not r.get("total")] if latest_q else []
    marine_vals = [r["closing"] for r in segs if pred(_norm_seg(r.get("seg"))) and r.get("closing") is not None]
    marine_closing = sum(marine_vals) if marine_vals else None
    closing = closing_total(yq[latest_q]) if latest_q else None
    reported_segs = [_norm_seg(r.get("seg")) for r in segs]

    def _remaining_krw(c):
        # 원장 원화 금액 × 미진행 비율 — 달러 왕복 환산(수주시점 환율 → 건조시점 spot)을 피해 공시 잔고와 같은 원화 장부 기준
        return (c["amt_krw_m"] or 0) * (1.0 - (c["progress_at_origin"] or 0))
    cands = [c for c in mine if c.get("counted") and c["signed_by_origin"]]
    hedge_implied_sign_rate(hedge, cands)          # ⑦ 둘째 참고치 — 적용값은 바꾸지 않는다
    remaining_marine_usd = sum(c["remaining_usd_m_at_origin"] or 0 for c in cands if c["type"] != "OTHER")
    remaining_all_usd = sum(c["remaining_usd_m_at_origin"] or 0 for c in cands)
    remaining_marine_krw = sum(_remaining_krw(c) for c in cands if c["type"] != "OTHER")
    remaining_all_krw = sum(_remaining_krw(c) for c in cands)
    backlog_cov = (remaining_marine_krw / marine_closing) if marine_closing else None
    backlog_cov_all = (remaining_all_krw / closing) if closing else None
    cap_factor = (1.0 / backlog_cov) if (backlog_cov is not None and backlog_cov > 1.0) else 1.0
    cap_applied = cap_factor < 1.0

    # 3) 분기 집계 — 캡은 (counted · 해양 · origin 분기말까지 수주) 계약의 origin 이후 분기에만. 원값은 _raw 에 같이 쌓는다.
    def _bucket():
        return {"usd_m": 0.0, "marine_usd_m": 0.0, "by_type": collections.defaultdict(float),
                "by_cohort": collections.defaultdict(float), "by_cohort_alt": collections.defaultdict(float),
                "hedged_krw_m": 0.0, "marine_hedged_krw_m": 0.0, "_rate_w": 0.0, "_hrate_w": 0.0, "n_active": 0,
                "marine_hedged_krw_m_signed_by_origin": 0.0, "marine_hedged_krw_m_post_origin": 0.0,
                "_raw": {"usd_m": 0.0, "marine_usd_m": 0.0, "hedged_krw_m": 0.0, "marine_hedged_krw_m": 0.0}}
    by_q = collections.defaultdict(_bucket)
    # origin 이후 체결(counted·해양) 계약 — 모델이 신규수주(forecast_panel)와 겹치지 않게 '기존' 에서 뺄 수 있도록 따로 센다(T6 D1)
    post_origin = {"n": 0, "amt_krw_m": 0.0, "amt_usd_m": 0.0, "rcps": []}
    for c in mine:
        if not c.get("counted"):
            continue
        hedge_rate_c = hedge["hedge_rate"] or c["fx_at_sign"]
        marine = c["type"] != "OTHER"
        capped = bool(cap_applied and marine and c["signed_by_origin"])
        c["backlog_cap_applied"] = capped
        split_key = "marine_hedged_krw_m_signed_by_origin" if c["signed_by_origin"] else "marine_hedged_krw_m_post_origin"
        if marine and not c["signed_by_origin"]:
            post_origin["n"] += 1
            post_origin["amt_krw_m"] += c["amt_krw_m"] or 0.0
            post_origin["amt_usd_m"] += c["amt_usd_m"] or 0.0
            post_origin["rcps"].append(c["rcp"])
        for q, usd in scheds[c["rcp"]].items():
            sp, _ = spot(q)
            applied = hr * hedge_rate_c + (1.0 - hr) * sp
            u = usd * cap_factor if (capped and q > origin) else usd
            b = by_q[q]
            b["usd_m"] += u
            b["by_type"][c["type"]] += u
            b["by_cohort"][c["cohort"] or "등급없음"] += u
            b["by_cohort_alt"][c["cohort_alt"] or "등급없음"] += u
            b["hedged_krw_m"] += u * applied
            b["_rate_w"] += u * applied
            b["_hrate_w"] += u * hedge_rate_c
            b["n_active"] += 1
            b["_raw"]["usd_m"] += usd
            b["_raw"]["hedged_krw_m"] += usd * applied
            if marine:
                b["marine_usd_m"] += u
                b["marine_hedged_krw_m"] += u * applied
                b[split_key] += u * applied
                b["_raw"]["marine_usd_m"] += usd
                b["_raw"]["marine_hedged_krw_m"] += usd * applied
    by_quarter = collections.OrderedDict()
    for q in sorted(by_q):
        b = by_q[q]
        sp, sp_src = spot(q)
        topm, gshare = _target_opm(b["by_cohort"], b["usd_m"], table)
        topm_alt, gshare_alt = _target_opm(b["by_cohort_alt"], b["usd_m"], table)
        cap_here = cap_applied and q > origin
        row = collections.OrderedDict([
            ("usd_m", round(b["usd_m"], 3)), ("marine_usd_m", round(b["marine_usd_m"], 3)),
            ("by_type", collections.OrderedDict((k, round(v, 3)) for k, v in sorted(b["by_type"].items()))),
            ("by_cohort", collections.OrderedDict((k, round(v, 3)) for k, v in sorted(b["by_cohort"].items()))),
            ("by_cohort_alt", collections.OrderedDict((k, round(v, 3)) for k, v in sorted(b["by_cohort_alt"].items()))),
            ("hedged_krw_m", round(b["hedged_krw_m"], 1)), ("marine_hedged_krw_m", round(b["marine_hedged_krw_m"], 1)),
            # marine_hedged_krw_m = origin 분기말까지 체결분 + origin 이후 체결분(캡은 앞쪽에만) — 모델은 신규수주 패널과 겹치지 않게 앞쪽만 '기존' 으로 쓴다
            ("marine_hedged_krw_m_signed_by_origin", round(b["marine_hedged_krw_m_signed_by_origin"], 1)),
            ("marine_hedged_krw_m_post_origin", round(b["marine_hedged_krw_m_post_origin"], 1)),
            ("applied_rate", round(b["_rate_w"] / b["usd_m"], 2) if b["usd_m"] else None),
            ("hedge_ratio", hr), ("hedge_rate", round(b["_hrate_w"] / b["usd_m"], 2) if b["usd_m"] else None),
            ("spot_assumed", round(sp, 2)), ("spot_source", sp_src), ("n_active", b["n_active"]),
            ("kind", "estimate"), ("past", q <= origin),
            ("basis", "공시 계약기간 안 %s 배분 × 헤지 적용 환율%s" % ("선형 진행률" if curve == "linear" else "S-커브 진행률",
                                                          (" × 잔고 캡 %.4f(backlog_cap — origin 전 수주 해양분만)" % cap_factor) if cap_here else "")),
            ("target_opm", topm), ("graded_share", gshare),
            ("target_opm_alt", topm_alt), ("graded_share_alt", gshare_alt)])
        if cap_here:
            row["backlog_cap"] = collections.OrderedDict([
                ("factor", round(cap_factor, 6)), ("usd_m_raw", round(b["_raw"]["usd_m"], 3)), ("marine_usd_m_raw", round(b["_raw"]["marine_usd_m"], 3)),
                ("hedged_krw_m_raw", round(b["_raw"]["hedged_krw_m"], 1)), ("marine_hedged_krw_m_raw", round(b["_raw"]["marine_hedged_krw_m"], 1))])
        by_quarter[q] = row
    by_year = collections.OrderedDict()
    for q, b in by_quarter.items():
        y = by_year.setdefault(q[:4], {"usd_m": 0.0, "marine_usd_m": 0.0, "hedged_krw_m": 0.0, "marine_hedged_krw_m": 0.0,
                                       "hedged_krw_m_raw": 0.0, "marine_hedged_krw_m_raw": 0.0,
                                       "by_type": collections.defaultdict(float), "by_cohort": collections.defaultdict(float),
                                       "by_cohort_alt": collections.defaultdict(float), "quarters": 0})
        for k in ("usd_m", "marine_usd_m", "hedged_krw_m", "marine_hedged_krw_m"):
            y[k] += b[k]
        raw = b.get("backlog_cap") or {}
        y["hedged_krw_m_raw"] += raw.get("hedged_krw_m_raw", b["hedged_krw_m"])
        y["marine_hedged_krw_m_raw"] += raw.get("marine_hedged_krw_m_raw", b["marine_hedged_krw_m"])
        for k, v in b["by_type"].items():
            y["by_type"][k] += v
        for k, v in b["by_cohort"].items():
            y["by_cohort"][k] += v
        for k, v in b["by_cohort_alt"].items():
            y["by_cohort_alt"][k] += v
        y["quarters"] += 1
    for y in by_year.values():
        for k in ("usd_m", "marine_usd_m"):
            y[k] = round(y[k], 3)
        for k in ("hedged_krw_m", "marine_hedged_krw_m", "hedged_krw_m_raw", "marine_hedged_krw_m_raw"):
            y[k] = round(y[k], 1)
        y["by_type"] = collections.OrderedDict((k, round(v, 3)) for k, v in sorted(y["by_type"].items()))
        y["by_cohort"] = collections.OrderedDict((k, round(v, 3)) for k, v in sorted(y["by_cohort"].items()))
        y["by_cohort_alt"] = collections.OrderedDict((k, round(v, 3)) for k, v in sorted(y["by_cohort_alt"].items()))

    # 화해: 분기 SLS 원화(해양) vs 정기보고서 부문 매출 3개월분 — 과거 분기(≤ origin)는 캡의 영향을 받지 않는다
    reported = reported_marine_3m(stock, yq)
    fin_is = _fin_is(stock)
    reconcile = collections.OrderedDict()
    for q in sorted(reported):
        if q > origin or q not in by_quarter:
            continue
        sls = by_quarter[q]["marine_hedged_krw_m"]
        rep = reported[q]["value"]
        # 교차검사: 부문 매출 3개월분이 연결 매출(fin)보다 1% 넘게 크면 부문표(내부거래 제거 전) 또는 파서 문제 — 표시만 하고 ratio 는 둔다
        cons_rev = ((fin_is or {}).get(q) or {}).get("매출액(수익)")
        exceeds = round((rep / cons_rev - 1.0) * 100, 2) if (cons_rev and rep > cons_rev * 1.01) else None
        issue = None
        if rep <= 0:
            issue = "보고 매출 3개월분이 0 이하(프로젝트 누계 차분에서 완료 계약이 표에서 빠진 경우) — 비교 불가"
        elif sls <= 0:
            issue = "그 분기에 진행 중인 원장 계약 없음 — 비교 불가"
        reconcile[q] = {"sls_krw_m": sls, "reported_segment_rev_m": rep, "reported_source": reported[q]["source"],
                        "segments": reported[q]["segments"],
                        "consolidated_rev_m": cons_rev, "exceeds_consolidated_pct": exceeds,
                        "ratio": round(sls / rep, 4) if issue is None else None, "issue": issue,
                        "note": "공시된 척당 계약(2024~)만 → 그 전 수주 물량·계약 미공시·반복건조·기타매출은 잔차"}
    used = [q for q in sorted(reconcile) if reconcile[q]["ratio"] is not None][-4:]
    med = _median([reconcile[q]["ratio"] for q in used]) if used else None
    # 원장 신규 vs 수주표 신규증감(연초 누계, 해양 부문): 두 공시의 계약 인식 기준(발효·선수금·환율·범위)이 같은지 보는 진단.
    # 대한조선은 원장 2025H2 1.41조 vs 수주표 FY2025 신규 0.69조 — 커버리지 > 1 의 배경이 여기 있다.
    ledger_vs_new = None
    if latest_q:
        new_vals = [r["new"] for r in segs if pred(_norm_seg(r.get("seg"))) and r.get("new") is not None]
        if new_vals and sum(new_vals) > 0:
            y0, (_, lq_end) = datetime.date(int(latest_q[:4]), 1, 1), q_bounds(latest_q)
            led_new = 0.0
            for c in mine:
                d = _date(c.get("signed")) or _date(c.get("start"))
                if c.get("counted") and c["type"] != "OTHER" and d and y0 <= d <= lq_end:
                    led_new += c["amt_krw_m"] or 0
            ledger_vs_new = {"quarter": latest_q, "ledger_new_krw_m": round(led_new, 1), "reported_new_krw_m": round(sum(new_vals), 1),
                             "ratio": round(led_new / sum(new_vals), 4),
                             "basis": "%s~%s 수주 해양 계약의 원장 원화 공시금액 ÷ 정기보고서 %s 해양 부문 신규증감(연초 누계, 환율효과 포함)"
                                      % (y0.isoformat(), lq_end.isoformat(), latest_q)}
    reconcile_summary = {
        "definition": "ratio = SLS 해양 원화(헤지 적용) ÷ 정기보고서 해양 부문 매출 3개월분. scale_to_reported = 1/ratio (모델: 매출조선 = SLS 원화 × scale)",
        "quarters_used": used, "median_ratio_4q": round(med, 4) if med else None,
        "median_scale_to_reported_4q": round(1.0 / med, 4) if med else None,
        "backlog_coverage_at_origin": round(backlog_cov, 4) if backlog_cov is not None else None,
        "backlog_coverage_basis": "%s 분기말까지 수주된 해양 계약의 원장 원화 금액 × 미진행 비율 ÷ 정기보고서 %s 해양 부문 기말잔고 원화 (환산 없음, 캡 전 원값)" % (origin, latest_q or "—"),
        "backlog_coverage_after_cap": round(backlog_cov * cap_factor, 4) if backlog_cov is not None else None,
        "backlog_cap_applied": cap_applied,
        "backlog_coverage_all_segments": round(backlog_cov_all, 4) if backlog_cov_all is not None else None,
        "remaining_usd_m_at_origin": round(remaining_all_usd, 3), "remaining_marine_usd_m_at_origin": round(remaining_marine_usd, 3),
        "remaining_krw_m_at_origin": round(remaining_all_krw, 1), "remaining_marine_krw_m_at_origin": round(remaining_marine_krw, 1),
        "reported_backlog_krw_m": closing, "reported_marine_backlog_krw_m": marine_closing,
        "reported_backlog_segments": reported_segs, "ledger_vs_reported_new": ledger_vs_new,
        "warning": "원장은 2024~ 공시분 — 과거 분기 ratio 는 그 전 수주 물량이 빠져 낮다. 미래 구간 배율은 backlog_coverage 쪽이 덜 편향된다. "
                   "커버리지 > 1 이면 이 파일이 이미 1/coverage 캡을 적용했다(backlog_cap) — 모델은 배율을 겹쳐 곱하지 말 것"}

    # 잔고 캡 블록(§5-2) — 적용 여부·배율·전후 합계. 캡 뒤에도 SLS 원화 합이 잔고를 넘을 수 있다(수주시점 환율 → 건조시점 환율 환산 차이) — 숨기지 않는다
    total_window = [q for q in q_range(*FORECAST_WINDOW) if q in by_quarter]
    future_qs = [q for q in by_quarter if q > origin]
    fut_raw = sum(by_q[q]["_raw"]["marine_hedged_krw_m"] for q in future_qs)
    fut_capped = sum(by_q[q]["marine_hedged_krw_m"] for q in future_qs)
    win_raw = sum(by_q[q]["_raw"]["hedged_krw_m"] for q in total_window)
    win_capped = sum(by_q[q]["hedged_krw_m"] for q in total_window)
    backlog_cap = collections.OrderedDict([
        ("applied", cap_applied), ("kind", "estimate"),
        ("coverage_at_origin", round(backlog_cov, 4) if backlog_cov is not None else None),
        ("factor", round(cap_factor, 6)),
        ("scope", "origin(%s) 분기말까지 수주된 해양 계약(counted)의 origin 이후 분기 — origin 뒤 수주분·비해양(OTHER)·과거 분기는 그대로" % origin),
        ("reported_marine_backlog_krw_m", marine_closing),
        ("remaining_marine_krw_m_at_origin_raw", round(remaining_marine_krw, 1)),
        ("remaining_marine_krw_m_at_origin_capped", round(remaining_marine_krw * cap_factor, 1)),
        ("future_marine_hedged_krw_m_raw", round(fut_raw, 1)), ("future_marine_hedged_krw_m", round(fut_capped, 1)),
        ("future_sls_vs_backlog_raw", round(fut_raw / marine_closing, 4) if marine_closing else None),
        ("future_sls_vs_backlog", round(fut_capped / marine_closing, 4) if marine_closing else None),
        ("window_hedged_krw_m_raw", round(win_raw, 1)), ("window_hedged_krw_m", round(win_capped, 1)),
        ("basis", "MODEL_SPEC §5-2 — 원장 잔여 원화(수주시점 금액 × 미진행 비율) > 공시 해양 기말잔고이면 배율 1/coverage 로 줄인다"
                  "(선형 진행 가정이 실제보다 느리거나 공시 잔고 범위·환율이 다른 경우). 원값은 by_quarter[q].backlog_cap.*_raw · by_year[y].*_raw · "
                  "counts.forecast_window.*_raw 에 보존. future_sls_vs_backlog 는 SLS 원화(건조시점 환율) 기준이라 캡 뒤에도 1 을 넘을 수 있다")])
    # origin 이후 체결 해양 계약 요약(T6 D1) — by_quarter[q].marine_hedged_krw_m_post_origin 의 출처. 모델이 '신규수주' 와의 겹침을 수치로 적는다
    post_block = collections.OrderedDict([
        ("n", post_origin["n"]), ("amt_krw_m", round(post_origin["amt_krw_m"], 1)), ("amt_usd_m", round(post_origin["amt_usd_m"], 3)),
        ("window_marine_hedged_krw_m", round(sum(by_q[q]["marine_hedged_krw_m_post_origin"] for q in total_window), 1)),
        ("future_marine_hedged_krw_m", round(sum(by_q[q]["marine_hedged_krw_m_post_origin"] for q in future_qs), 1)),
        ("rcps", post_origin["rcps"]),
        ("basis", "origin(%s) 분기말 뒤에 체결(signed, 없으면 start)된 counted 해양 계약 — 잔고 캡 대상 아님. "
                  "by_quarter[q].marine_hedged_krw_m = _signed_by_origin + _post_origin" % origin)])

    # 타겟 OPM(기본 모드) + 대안 모드, 캘리브레이션도 각각(실측 OPM 은 assets/fin 이 있어야 — 없으면 null)
    target_opm, target_opm_alt = collections.OrderedDict(), collections.OrderedDict()
    for q, b in by_quarter.items():
        if b["target_opm"] is not None:
            target_opm[q] = {"opm": b["target_opm"], "graded_share": b["graded_share"], "mode": mode,
                             "basis": "cohort mix(%s) × cohort OPM table %s" % (mode, table_text)}
        if b["target_opm_alt"] is not None:
            target_opm_alt[q] = {"opm": b["target_opm_alt"], "graded_share": b["graded_share_alt"], "mode": alt_mode,
                                 "basis": "cohort mix(%s) × cohort OPM table %s" % (alt_mode, table_text)}
    calib = calibration(stock, target_opm, origin, fin_is)
    calib["mode"] = mode
    calib_alt = calibration(stock, target_opm_alt, origin, fin_is)
    calib_alt["mode"] = alt_mode
    # ⑦ 이 파일의 타겟이 두 표에서 어떻게 다른지 — 다음 분기와 예측창 평균(기본 모드 믹스 기준). 적용 표는 opm_table 하나뿐이다
    next_q = FORECAST_WINDOW[0]

    def _targets(tbl):
        return {q: _target_opm(by_q[q]["by_cohort"], by_q[q]["usd_m"], tbl)[0] for q in by_quarter}
    t_asm, t_cal = _targets(COHORT_OPM), _targets(calib_table)
    win_qs = [q for q in total_window if t_asm.get(q) is not None]
    calib_block["this_file"] = collections.OrderedDict([
        ("applied_table", opm_table), ("cohort_mode", mode),
        ("target_opm_next_q", {"assumed": t_asm.get(next_q), "reference_calibrated": t_cal.get(next_q)}),
        ("target_opm_window_mean", {"assumed": round(_median([t_asm[q] for q in win_qs]), 4) if win_qs else None,
                                    "reference_calibrated": round(_median([t_cal[q] for q in win_qs]), 4) if win_qs else None,
                                    "stat": "median over %d quarters %s~%s" % (len(win_qs), FORECAST_WINDOW[0], FORECAST_WINDOW[1])}),
        ("note", "target_opm·target_opm_alt·calibration 은 applied_table 로 계산했다. 다른 표로 바꾸면 calibrated_shift(실측 − 타겟)가 그만큼 반대로 움직여 "
                 "실측 OPM 수준은 같고 타겟의 해석(가정 15% vs 레퍼런스 유효 10.8%)만 달라진다")])

    warnings.append("종료일 = 마지막 호선 인도 예정; 진행률 매출 분기는 계약기간 안에 선형 배분(가정)")
    if stock == HOLDING:
        warnings.append("HD한국조선해양과 HD현대重 동일 계약 %d건 — shared_owner=329180 로 표시하고 이 파일의 합계에서 제외(합산 금지)" % n_shared_excluded)
    if stock == HOLDING_SHARES_WITH:
        n_sh = sum(1 for c in mine if c.get("shared_with"))
        warnings.append("HD한국조선해양(009540) 공시와 동일 계약 %d건(shared_with) — 두 파일을 합산하지 말 것" % n_sh)
    if hedge["kind"] == "estimate":
        warnings.append("헤지비율 %g 은 가정(%s)" % (hr, hedge["basis"]))
        imp, imp2 = hedge.get("hedge_ratio_implied_spot"), hedge.get("hedge_ratio_implied_sign_rate")
        if (imp is not None and abs(imp - hr) > 0.15) or (imp2 is not None and abs(imp2 - hr) > 0.15):
            warnings.append("공시 통화선도 매도 명목액 %.0f백만$ 을 잔고 대비 환산하면 현물(%s 기말 %.2f원) 기준 %s · 수주시점 평균환율(%s원, 계약 %s건) 기준 %s — "
                            "가정 %.2f 과 다르다. 약정환율 미공시라 적용하지 않음(참고치 hedge.hedge_ratio_implied_spot·hedge_ratio_implied_sign_rate; 채택은 사용자 결정)"
                            % (hedge["usd_sell_m"], hedge["quarter"], hedge.get("implied_spot_rate") or 0.0,
                               ("%.2f(%+.2f)" % (imp, imp - hr)) if imp is not None else "—",
                               ("%.2f" % hedge["implied_sign_rate"]) if hedge.get("implied_sign_rate") else "—", hedge.get("implied_sign_n") or 0,
                               ("%.2f(%+.2f)" % (imp2, imp2 - hr)) if imp2 is not None else "—", hr))
    tf = calib_block["this_file"]
    warnings.append("코호트 OPM 표 %s 적용. 레퍼런스 미포 SLS 셀 OPM 을 %d~%d 매출가중한 유효 표는 %s(가정 표 %s 는 레퍼런스 2024~26 보다 +3.8~5.1%%p 높다 — "
                    "cohort_opm_calibration.by_year). 다음 분기 %s 타겟: 가정 %s vs 캘리브레이션 %s. 바꾸려면 --opm-table reference_calibrated(오너 결정 — "
                    "하류 섹션 각주·모델 백테스트가 cohort_opm_table 을 읽는다)"
                    % (opm_table, COHORT_CALIB_WINDOW[0], COHORT_CALIB_WINDOW[1], _opm_table_text(calib_table), _opm_table_text(COHORT_OPM), next_q,
                       ("%.2f%%" % (tf["target_opm_next_q"]["assumed"] * 100)) if tf["target_opm_next_q"]["assumed"] is not None else "—",
                       ("%.2f%%" % (tf["target_opm_next_q"]["reference_calibrated"] * 100)) if tf["target_opm_next_q"]["reference_calibrated"] is not None else "—"))
    # 코호트 — 기본 모드와 대안 모드의 2025~ 수주 판정을 나란히 적는다(레퍼런스 HD현대미포 SLS 는 2025~ 물량 100% ⑤초호황)
    recent, recent_alt = collections.Counter(), collections.Counter()
    for c in mine:
        if c.get("counted") and c.get("year") and c["year"] >= 2025:
            if c.get("cohort"):
                recent[c["cohort"]] += c["amt_usd_m"] or 0
            if c.get("cohort_alt"):
                recent_alt[c["cohort_alt"]] += c["amt_usd_m"] or 0

    def _mix(cnt):
        tot = sum(cnt.values())
        return ", ".join("%s %.0f%%" % (k, 100 * v / tot) for k, v in sorted(cnt.items())) if tot else "—"
    ledger_mix = recent_alt if mode == "reference_anchor" else recent
    if sum(recent.values()) or sum(recent_alt.values()):
        warnings.append("코호트 기본 모드 %s: 2025~ 수주 물량(백만$) 판정 %s. reference_anchor 는 수주연도 → 등급(≤2020 ③중마진 · 2021 ④호황 · 2022~ ⑤초호황; "
                        "출처 사용자 레퍼런스 모델 HD현대미포 SLS 의 클락슨 기반 판정을 건조기간 2~3년으로 되돌린 표 — 외부 신조선가 지수 미보유%s). "
                        "ledger_relative 는 원장 내부 상대 등급(2025~ 판정 %s; 2021 이후 절대 호황 수준 미반영). 대안 모드는 by_cohort_alt·target_opm_alt·"
                        "calibration_alt 에 함께 저장. 타겟 OPM 은 기본 모드 기준이며 calibrated_shift(실측 − 타겟)로 실측 OPM 에 맞춘다 — 음수일 수 있다"
                        % (mode, _mix(recent), " — assets/newbuild_index.json 우선 적용" if newbuild_index else "", _mix(ledger_mix)))
    else:
        warnings.append("코호트 기본 모드 %s — 2025~ 등급 있는 수주 없음. 레퍼런스 HD현대미포 SLS(2025~ 100%% ⑤초호황)와 직접 비교 불가; "
                        "ledger_relative 는 원장 내부 상대 등급(신조선가 지수 없음, 2021 이후 절대 호황 수준 미반영)" % mode)
    if not fx:
        warnings.append("assets/fx.json 없음 — 수주시점·건조시점 환율은 공시 고시환율/약정환율/상수 %g 로 대체(fx_source 참조)" % const)
    if skipped:
        warnings.append("스케줄 불가 %d건(금액·기간 없음) — contracts[].schedule 비움" % len(skipped))
    n_end_est = sum(1 for c in mine if c["end_estimated"])
    if n_end_est:
        warnings.append("종료일 '-' %d건은 같은 선종 계약기간 중위로 종료 추정(end_estimated)" % n_end_est)
    if not reconcile:
        warnings.append("정기보고서 부문 매출(3개월분)을 만들 수 없어 화해 없음")
    if backlog_cov is not None and backlog_cov > 1.0:
        warnings.append("원장 잔여(%.0f억) > 공시 해양 기말잔고(%.0f억), 커버리지 %.2f — 선형 진행 가정이 실제 진행보다 느리거나 "
                        "공시 잔고 범위(환율·취소·범위)가 다르다. origin 이후 해양 매출(origin 전 수주분)을 1/coverage = %.4f 배로 줄였다"
                        "(backlog_cap, 원값 *_raw 보존). 모델은 배율 1 을 상한으로 볼 것 — 추가 배율 금지"
                        % (remaining_marine_krw / 100, marine_closing / 100, backlog_cov, cap_factor))
    if backlog_cov_all is not None and backlog_cov_all > 1.0 and (backlog_cov is None or backlog_cov <= 1.0):
        warnings.append("비해양(OTHER: 공사·플랜트 등) 포함 원장 잔여 %.0f억 > 정기보고서 수주표 기말잔고 %.0f억(전부문 커버리지 %.2f) — "
                        "수주표는 조선 부문 범위(%s)만 담아 비교 범위가 다르다. backlog_coverage_all_segments 는 배율로 쓰지 말 것"
                        % (remaining_all_krw / 100, closing / 100, backlog_cov_all, "·".join(reported_segs) or "—"))
    over = [q for q in reconcile if reconcile[q]["exceeds_consolidated_pct"] is not None]
    if over:
        warnings.append("정기보고서 부문 매출 3개월분 > 연결 매출(fin) %d분기(%s; 최대 +%.1f%%) — 부문표가 내부거래 제거 전이거나 파서 문제(yards 레인). "
                        "reconcile[q].exceeds_consolidated_pct 에 표시, ratio 는 그대로"
                        % (len(over), ", ".join(over[-4:]), max(reconcile[q]["exceeds_consolidated_pct"] for q in over)))
    if ledger_vs_new and not (0.75 <= ledger_vs_new["ratio"] <= 1.25):
        warnings.append("원장 신규 %.0f억 vs 수주표 신규증감 %.0f억(%s 연초 누계) — 비율 %.2f: 두 공시의 계약 인식 기준(발효·선수금·환율·범위)이 "
                        "다르다. backlog_coverage 해석 시 참고(reconcile_summary.ledger_vs_reported_new)"
                        % (ledger_vs_new["ledger_new_krw_m"] / 100, ledger_vs_new["reported_new_krw_m"] / 100, ledger_vs_new["quarter"], ledger_vs_new["ratio"]))

    fx_sources = collections.Counter(c["fx_source"] for c in mine)
    cohort_source = COHORT_SOURCE
    if newbuild_index:
        cohort_source = "assets/newbuild_index.json(%s, as_of %s) 우선 적용 — 지수에 없는 연도는 표: %s" % (
            newbuild_index.get("source") or "출처 미기재", newbuild_index.get("as_of") or "—", COHORT_SOURCE)
    return collections.OrderedDict([
        ("stock", stock), ("name", NAMES.get(stock, stock)), ("origin", origin),
        ("unit", "USD_million | KRW_million"), ("curve", "linear_progress" if curve == "linear" else "s_curve"),
        ("built_at", today or datetime.date.today().isoformat()),
        ("counts", {"contracts": len(mine), "counted": n_counted, "shared_excluded": n_shared_excluded,
                    "skipped": len(skipped), "end_estimated": n_end_est,
                    "estimated_series": sum(1 for c in mine if c["estimated_series"]),
                    "schedule_quarters": len(by_quarter),
                    "forecast_window": {"from": FORECAST_WINDOW[0], "to": FORECAST_WINDOW[1], "quarters": len(total_window),
                                        "usd_m": round(sum(by_quarter[q]["usd_m"] for q in total_window), 3),
                                        "hedged_krw_m": round(win_capped, 1),
                                        "usd_m_raw": round(sum(by_q[q]["_raw"]["usd_m"] for q in total_window), 3),
                                        "hedged_krw_m_raw": round(win_raw, 1)}}),
        ("fx", {"source_counts": collections.OrderedDict(sorted(fx_sources.items())), "fx_json": bool(fx), "const": const,
                "spot_policy": "건조시점 환율 = fx.json quarters/forward, 없으면 상수(가정)"}),
        ("hedge", hedge),
        ("cohort_mode", mode), ("cohort_mode_alt", alt_mode),
        ("cohort_table", cohort_table(newbuild_index, table)), ("cohort_source", cohort_source),
        ("cohort_method", COHORT_METHOD),
        ("cohort_method_by_mode", collections.OrderedDict([("reference_anchor", COHORT_REFERENCE_METHOD), ("ledger_relative", COHORT_METHOD)])),
        # cohort_opm_table = 타겟에 실제로 쓴 표(하류 kship_model._sls_frozen 이 읽는다). 가정 표와 레퍼런스 캘리브레이션 근거는 그 옆에
        ("cohort_opm_table", collections.OrderedDict((k, table[k]) for k in COHORT_LABELS.values())),
        ("cohort_opm_table_source", opm_table),
        ("cohort_opm_table_assumed", collections.OrderedDict((k, COHORT_OPM[k]) for k in COHORT_LABELS.values())),
        ("cohort_opm_calibration", calib_block),
        ("year_index", year_index),
        ("backlog_cap_applied", cap_applied), ("backlog_cap", backlog_cap), ("post_origin", post_block),
        ("contracts", mine), ("by_quarter", by_quarter), ("by_year", by_year),
        ("reconcile", reconcile), ("reconcile_summary", reconcile_summary),
        ("target_opm", target_opm), ("target_opm_alt", target_opm_alt),
        ("calibration", calib), ("calibration_alt", calib_alt),
        ("skipped", skipped), ("warnings", warnings)])

def _fin_is(stock):
    """assets/fin/<stock>.json 의 손익(3개월분, 백만원) — 연결 우선, 없으면 별도. 파일이 없거나 못 읽으면 None."""
    p = os.path.join(ASSETS, "fin", "%s.json" % stock)
    if not os.path.exists(p):
        return None
    try:
        fin = load_asset(os.path.join("fin", "%s.json" % stock))
    except (OSError, ValueError):
        return None
    return ((fin.get("cons") or {}).get("is")) or ((fin.get("sep") or {}).get("is")) or {}


def calibration(stock, target_opm, origin, is_=None):
    """회사 실측 OPM(assets/fin/<stock>.json cons.is 영업이익/매출액, **회사 전체 — 부문 아님**) − 타겟 OPM 의 최근 4분기 중위
    = calibrated_shift. fin 이 아직 없으면 null 로 자리만 둔다(yards_cache 에는 부문 영업이익이 없다)."""
    out = {"calibrated_shift": None, "actual_opm": {}, "basis": "fin 미수집 — yards_cache 에 부문 OP 없음 → 캘리브레이션 보류"}
    if is_ is None:
        is_ = _fin_is(stock)
    if is_ is None:
        return out
    diffs = []
    for q in sorted(is_):
        rev, op = is_[q].get("매출액(수익)"), is_[q].get("영업이익")
        if rev and op is not None and q <= origin:
            a = op / rev
            out["actual_opm"][q] = round(a, 4)
            if q in target_opm:
                diffs.append((q, a - target_opm[q]["opm"]))
    used = diffs[-4:]
    if used:
        out["calibrated_shift"] = round(_median([d for _, d in used]), 4)
        out["quarters_used"] = [q for q, _ in used]
        out["basis"] = "실측 OPM(fin cons.is 영업이익/매출액, 회사 전체 — 부문 아님) − 타겟 OPM, 최근 %d분기 중위" % len(used)
    else:
        out["basis"] = "fin 있음, 겹치는 분기 없음"
    return out


# ── 실행 ────────────────────────────────────────────────────

def run(stocks, curve="linear", const=FX_CONST, origin=None, write=True, mode=COHORT_MODE_DEFAULT,
        opm_table=OPM_TABLE_DEFAULT, hedge_default=HEDGE_RATIO_DEFAULT, today=None):
    ledger = load_asset("contracts.json")["rows"]
    rows, dropped = apply_supersedes([dict(r) for r in ledger])
    pairs = mark_shared(rows)
    yards = load_yards()
    fx = load_fx()
    index = load_newbuild_index()
    origin = origin or max((max(qs) for qs in yards.values() if qs), default="2026Q2")
    contracts = prepare_contracts(rows, yards, fx, const)
    cohort_map, year_index = cohorts(contracts)
    outs = {}
    for stock in stocks:
        o = build(stock, contracts, cohort_map, year_index, yards, fx, curve, const, origin, mode=mode, newbuild_index=index,
                  opm_table=opm_table, hedge_default=hedge_default, today=today)
        o["dropped_superseded"] = dropped
        if stock in (HOLDING, HOLDING_SHARES_WITH):
            o["shared_pairs"] = [{"holding_rcp": a, "yard_rcp": b} for a, b in pairs]
        outs[stock] = o
        if write:
            os.makedirs(SLS_DIR, exist_ok=True)
            write_asset(os.path.join("sls", "%s.json" % stock), o)
    if write:
        write_asset(os.path.join("sls", "summary.json"), summary(outs, origin, curve, const, dropped, pairs, mode=mode, newbuild_index=bool(index),
                                                                 opm_table=opm_table, hedge_default=hedge_default, today=today))
    return outs


def summary(outs, origin, curve, const, dropped, pairs, mode=COHORT_MODE_DEFAULT, newbuild_index=False,
            opm_table=OPM_TABLE_DEFAULT, hedge_default=HEDGE_RATIO_DEFAULT, today=None):
    next_q = FORECAST_WINDOW[0]
    rows = []
    for stock in sorted(outs):
        o = outs[stock]
        rs, cap, h = o["reconcile_summary"], o["backlog_cap"], o["hedge"]
        tf = (o.get("cohort_opm_calibration") or {}).get("this_file") or {}
        rows.append(collections.OrderedDict([
            ("stock", stock), ("name", o["name"]), ("contracts", o["counts"]["contracts"]), ("counted", o["counts"]["counted"]),
            ("shared_excluded", o["counts"]["shared_excluded"]), ("schedule_quarters", o["counts"]["schedule_quarters"]),
            ("window_usd_m", o["counts"]["forecast_window"]["usd_m"]), ("window_hedged_krw_m", o["counts"]["forecast_window"]["hedged_krw_m"]),
            ("window_hedged_krw_m_raw", o["counts"]["forecast_window"]["hedged_krw_m_raw"]),
            ("median_ratio_4q", rs["median_ratio_4q"]), ("backlog_coverage_at_origin", rs["backlog_coverage_at_origin"]),
            ("backlog_cap_applied", cap["applied"]), ("backlog_cap_factor", cap["factor"]),
            ("hedge_ratio", h["hedge_ratio"]), ("hedge_kind", h["kind"]),
            ("hedge_ratio_implied_spot", h.get("hedge_ratio_implied_spot")), ("hedge_ratio_implied_sign_rate", h.get("hedge_ratio_implied_sign_rate")),
            ("cohort_mode", o["cohort_mode"]), ("opm_table", o.get("cohort_opm_table_source", "assumed")),
            ("target_opm_next_q", (o["target_opm"].get(next_q) or {}).get("opm")),
            ("target_opm_alt_next_q", (o["target_opm_alt"].get(next_q) or {}).get("opm")),
            ("target_opm_next_q_by_table", tf.get("target_opm_next_q")),
            ("calibrated_shift", o["calibration"]["calibrated_shift"]),
            ("calibrated_shift_alt", o["calibration_alt"]["calibrated_shift"])]))
    alt_mode = [m for m in COHORT_MODES if m != mode][0]
    return collections.OrderedDict([("origin", origin), ("curve", curve), ("fx_const", const), ("window", list(FORECAST_WINDOW)),
                                    ("next_q", next_q), ("cohort_mode", mode), ("cohort_mode_alt", alt_mode),
                                    ("opm_table", opm_table), ("hedge_ratio_default", hedge_default),
                                    ("built_at", today or datetime.date.today().isoformat()),
                                    ("newbuild_index_present", newbuild_index),
                                    ("dropped_superseded", dropped), ("shared_pairs_n", len(pairs)), ("rows", rows)])


def report(outs):
    nq = FORECAST_WINDOW[0]

    def pct(v):
        return ("%.2f%%" % (v * 100)) if v is not None else "—"
    print("%-7s %-10s %4s %4s %4s %5s %12s %14s %8s %8s %6s | %s tOPM %8s %8s  shift %8s %8s  cap" % (
        "stock", "name", "n", "cnt", "shr", "nQ", "%s-%s M$" % (nq[2:], FORECAST_WINDOW[1][2:]), "원화(백만)", "ratio4q", "bklgcov", "hedge",
        nq, "기본", "대안", "기본", "대안"))
    for stock in sorted(outs):
        o = outs[stock]
        w, rs, cap = o["counts"]["forecast_window"], o["reconcile_summary"], o["backlog_cap"]
        print("%-7s %-10s %4d %4d %4d %5d %12.1f %14.0f %8s %8s %6s | %s      %8s %8s        %8s %8s  %s" % (
            stock, o["name"], o["counts"]["contracts"], o["counts"]["counted"], o["counts"]["shared_excluded"],
            o["counts"]["schedule_quarters"], w["usd_m"], w["hedged_krw_m"],
            ("%.3f" % rs["median_ratio_4q"]) if rs["median_ratio_4q"] is not None else "—",
            ("%.3f" % rs["backlog_coverage_at_origin"]) if rs["backlog_coverage_at_origin"] is not None else "—",
            "%.2f%s" % (o["hedge"]["hedge_ratio"], "m" if o["hedge"]["kind"] == "measured" else "e"),
            o["cohort_mode"][:3], pct((o["target_opm"].get(nq) or {}).get("opm")), pct((o["target_opm_alt"].get(nq) or {}).get("opm")),
            pct(o["calibration"]["calibrated_shift"]), pct(o["calibration_alt"]["calibrated_shift"]),
            ("%.4f" % cap["factor"]) if cap["applied"] else "—"))
        if cap["applied"]:
            print("    잔고 캡: 커버리지 %.4f → 배율 %.4f · 창 원화 %.0f → %.0f 백만원 · origin 이후 해양 원화 %.0f → %.0f (공시 해양 잔고 %.0f; SLS/잔고 %.3f → %.3f)"
                  % (cap["coverage_at_origin"], cap["factor"], cap["window_hedged_krw_m_raw"], cap["window_hedged_krw_m"],
                     cap["future_marine_hedged_krw_m_raw"], cap["future_marine_hedged_krw_m"], cap["reported_marine_backlog_krw_m"] or 0,
                     cap["future_sls_vs_backlog_raw"] or 0, cap["future_sls_vs_backlog"] or 0))
        h, tf = o["hedge"], (o.get("cohort_opm_calibration") or {}).get("this_file") or {}
        if h["kind"] == "estimate" and (h.get("hedge_ratio_implied_spot") is not None or h.get("hedge_ratio_implied_sign_rate") is not None):
            print("    헤지 참고치(적용 아님): 명목 %.0f백만$ ÷ 잔고 — 현물 기준 %s · 수주시점 평균환율(%s원) 기준 %s; 레퍼런스 HEDGE 미포 0.65 · 삼성重 1.00"
                  % (h["usd_sell_m"] or 0, pct(h.get("hedge_ratio_implied_spot")), ("%.2f" % h["implied_sign_rate"]) if h.get("implied_sign_rate") else "—",
                     pct(h.get("hedge_ratio_implied_sign_rate"))))
        tq = tf.get("target_opm_next_q") or {}
        print("    코호트 OPM 표 %s — %s 타겟 가정 %s vs 레퍼런스 캘리브레이션 %s" % (o.get("cohort_opm_table_source"), nq, pct(tq.get("assumed")), pct(tq.get("reference_calibrated"))))
        for q in sorted(o["reconcile"]):
            r = o["reconcile"][q]
            print("    %s sls %10.0f  reported %10.0f  ratio %s  (%s)" % (q, r["sls_krw_m"], r["reported_segment_rev_m"],
                  ("%.3f" % r["ratio"]) if r["ratio"] is not None else "—", r["reported_source"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="조선사 5 + 지주 1")
    ap.add_argument("--stock", action="append", default=[])
    ap.add_argument("--curve", choices=("linear", "s_curve"), default="linear")
    ap.add_argument("--spot", type=float, default=FX_CONST, help="fx.json 이 없을 때 쓰는 원/달러 상수")
    ap.add_argument("--origin", default=None, help="기준 분기(기본: yards_cache 최신)")
    ap.add_argument("--cohort-mode", choices=COHORT_MODES, default=COHORT_MODE_DEFAULT,
                    help="기본 코호트 모드(§5-2). 다른 모드는 항상 *_alt 에 함께 저장된다")
    ap.add_argument("--opm-table", choices=OPM_TABLES, default=OPM_TABLE_DEFAULT,
                    help="타겟 OPM 표(⑦): assumed = ①−5%% ②0 ③5 ④10 ⑤15 가정, reference_calibrated = 레퍼런스 미포 SLS 셀 OPM 매출가중(①−1.1 ②1.0 ③4.3 ④5.4 ⑤10.8). 두 표는 항상 함께 저장")
    ap.add_argument("--hedge-default", type=float, default=HEDGE_RATIO_DEFAULT,
                    help="약정환율 미공시 회사의 헤지비율 가정(기본 0.7; 레퍼런스 SLS HEDGE 행은 미포 0.65 · 삼성重 1.00)")
    ap.add_argument("--today", default=None, help="built_at 고정(YYYY-MM-DD) — 같은 입력이면 바이트 동일")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않는다")
    a = ap.parse_args(argv)
    if a.today and not _date(a.today):
        ap.error("--today 는 YYYY-MM-DD")
    if not (0.0 <= a.hedge_default <= 1.0):
        ap.error("--hedge-default 는 0~1")
    stocks = a.stock or (YARDS + [HOLDING] if a.all else [])
    if not stocks:
        ap.error("--all 또는 --stock")
    outs = run(stocks, curve=a.curve, const=a.spot, origin=a.origin, write=not a.dry_run, mode=a.cohort_mode,
               opm_table=a.opm_table, hedge_default=a.hedge_default, today=a.today)
    if a.report:
        report(outs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
