#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_model — 한국조선 56사 실적 모델 엔진(MODEL_SPEC 2-5): fin·fx·prices·sls → assets/models/<stock>.json + summary.json.

레퍼런스(사용자 subQ 모델 3개)의 계산 사슬(0-1)을 역할별 전략으로 옮겼다. 실적 구간은 fin(DART 정기보고서)의 값을
**그대로**(kind actual + src) 쓰고, 추정 구간(T+1~2028Q4)은 전부 kind estimate + basis 를 갖는다. 출처 없는 숫자는 없다.

  yard      매출조선 = SLS 해양 원화(assets/sls, 헤지 적용) + 원장 밖 잔고 소진분 + 신규수주 매출(결정 ⓓ, 2026-09-30: forecast_panel base
            시나리오의 new_order_revenue — 미보정 book-value proxy, `매출조선신규` 행으로 따로 보이고 매출조선·매출액에 포함; 보수/낙관은
            scenarios 블록에만, 합산 안 함; 한화오션·HJ 는 패널이 전범위 new_order_revenue 를 비워(데이터 충분성) 같은 엔진의
            covered_scope_new_revenue(모델 대상 부문만) 로 폴백 — 저신뢰 표기·공시 체결 속도 대조는 driver.new_orders). 원장(2024~ 척당 계약 공시)은 공시 잔고의
            일부만 덮으므로 (공시 해양 잔고 − 원장 잔여) 를 최근 4분기 '원장 밖 매출'(부문 매출 − SLS) 중위 속도로 소진시킨다.
            공시 잔고를 상한으로 삼아 SLS 모양 증폭(화해 배율 1/ratio 4.8배 같은 것)을 피한다 — 배율 대안값은 driver 에 같이 적는다.
            OPM = SLS 타겟(코호트 표) + 회사 캘리브레이션(최근 4분기 실측 OPM − 타겟 중위); 신규분에도 같은 타겟. 기타 부문 = 총매출 − 조선 부문 추세.
            sls 의 cohort_mode·backlog_cap_applied(R3) 는 있으면 읽어 basis 에 적고, 없으면 '정보 없음' 으로 동작한다.
  holding   (009540) 매출 = HD현대重(329180) 모델 매출 × 실측 연결/자회사 비율(합병 후 분기), OPM = 자회사 OPM + 실측 차이.
  equip·engine·steel  매출 = f(Σ 고객 조선사 매출_(t−lag) × 비중) — 격자 탐색(가중치 후보 × 시차 0~4 × 창 8/12/19 × 변환 수준·YoY·4Q합)에서
            상관 최대 조합을 원점 회귀로 채택(후보 자격(라운드 7 L5): related 만이면 Σshare ≥ 5% · 4Q합 유효 표본 n−3 ≥ 4 · ≥0.30 · 단일 검정 5% 유의 · **OOS 규칙(결정 ⓘ)**: 마지막 실적 4분기 전에 동결해 연동·추세 둘을
            같은 4분기에 대고 WAPE_link > WAPE_trend × 1.10 이면 기각 → driver.selection_oos), 미달·고객 연결 없음이면 매출 추세 + 계절성
            (전년동기 × (1+g), g 감쇠). 후보표·유의 임계·과적합 경고는 driver.grid 에 남긴다. 격자 다중비교는 통계 보정 대신 이 OOS 규칙으로 막는다. 세진(075580)은 레퍼런스 `연간예상` 의 weighted(미포 0.9·현중 0.2 계열) 가중치를 후보로 넣고
            종속사 일승·동방선기 모델로 연결을 재구성하며, 풍력/플랜트·LPG·LNG-Fuel 은 modules(레퍼런스 가정, 합산 안 함)로 둔다.
            HD현대미포(010620)는 2025Q4 HD현대重 합병으로 fin 이 끊겨 체인링크로 잇고 그 규칙을 driver.merger_rule 에 적는다.
  공통      판관비율(4분기 중위) · 이자손익(평균 잔액 × 실측 이자율 — 주석 이자수익/비용 4분기 이상이면 그것, 아니면 CF) ·
            금융손익 세부(이자·외환·파생·기타금융 잔차 — 주석 계정이 있는 분기만 실적; 추정 외환·파생 0, 기타금융 4분기 중위) ·
            환관련손익(공시 외화 순노출 × Δ기말환율, 없으면 0 표기) ·
            법인세율(12분기 유효세율이 5~27% 안이면 그것, 밖·음수면 8분기 양(+)세전 분기 중위, 없으면 22% — 클립 안 함; 단 양(+)세전 중위·최근 4분기 중위가
            모두 5% 미만이면 이월결손 경로 carryforward_ramp — 저세율을 origin 회계연도 말까지 유지 → FY_LAST 말 22% 선형 수렴, assumptions.tax_schedule) ·
            비지배 비중(8분기 실측) · 자본 롤(+NI −배당) · EPS/BPS · PER/PBR(과거 밴드) ·
            주식수 사건(라운드 7 (j), 2026-10-08): 병합·분할·무상증자(fin 주식수 정수비 자동 감지 + SHARE_EVENTS 수동표 + aik 상장주식수(= 발행주식수) 로 분기말 후 사건)는
            사건 전 실적 분기의 주식수·EPS/BPS/DPS 를 비율 환산(IAS 33.64 비교표시·네이버 수정주가 이력과 정합, 셀 kind estimate), 추정 분기·PER/PBR now·EV 는 최신 유통주식수;
            증자/IPO/소각은 환산 없이 최신 주식수만(assumptions.shares) ·
            백테스트(freeze 2025Q2, 4분기 WAPE — 고객·선표도 freeze 시점 정보로 다시 만들고, 실측(kind actual) 분기만 짝을 짓는다).
  보충·표기  연결 손익이 없는 분기는 별도로 보충(quality.sep_filled, 셀 src 표기) · 부문 없는 회사는 '전사' 세그먼트에 드라이버를 남긴다 ·
            비영업손익 급등 분기는 assumptions.one_offs_detected + 경고('일회성 의심', 보고 EPS 숫자는 바꾸지 않음) + **조정EPS 행**(의심 회사만:
            초과 비영업손익을 그 분기 유효세율·지배 비중으로 세후화해 지배NI 에서 뺀 EPS, kind estimate — KCC 2026Q2 처분이익 류의 FY EPS 왜곡 표시).
  BS 롤     자본·지배지분 = 전분기 + NI − 배당; 순차입금·이자발생자산 = 전분기 ∓ FCF 근사(NI + 감가 − CAPEX, 둘 다 4분기 중위; 감가 없으면 NI,
            CAPEX≈감가 가정) — assumptions.bs_roll. EBITDA 는 CF face 감가상각비가 있는 회사만(quality.ebitda — 2026-10 기준 12/58; 나머지는 주석에만 있어 공란).
  status    quality.status_rule(STATUS_RULE)·status_reasons — full 은 데이터 완전성만, 드라이버 폴백은 driver_fallback.
  조선사 부문 음수 분기(부문표 누계 정정 차분)는 실적 셀·소진 창에서 제외하고 driver.segment_actual_dropped 에 남긴다.

    python3 kship_model.py --build --stocks 010140 075580     # 두 회사
    python3 kship_model.py --build --all [--xlsx]              # 모집단 57 (fin 없는 회사는 summary 에 no_fin 만)
    python3 kship_model.py --report 010140                     # 만든 모델 요약 출력
"""
import argparse
import collections
import datetime
import fractions
import gzip
import json
import math
import os
import re
import statistics
import sys

from kship_lib import ASSETS, KSHIP, atomic_write, q_next, q_range

FIN_DIR = os.path.join(ASSETS, "fin")
SLS_DIR = os.path.join(ASSETS, "sls")
MODELS_DIR = os.path.join(ASSETS, "models")
YARDS_CACHE = os.path.join(ASSETS, "yards_cache")

UNIT_DIV = 100.0                      # 백만원 → 억원
HORIZON_END = "2028Q4"                # 추정 마지막 분기(FY2028E)
FWD_MIN = 10                          # 최소 T+10
FY_FIRST, FY_LAST = 2021, 2028
FREEZE_Q = "2025Q2"                   # 백테스트 동결 분기
BACKTEST_H = 4
COE = 0.09                            # 레퍼런스 TP_BPS 의 COE
SECTOR_PER_BAND = (10.0, 15.0, 20.0)  # 레퍼런스 TP_PE PB 예시 밴드(과거 밴드가 없을 때)
TAX_CLIP, TAX_DEFAULT = (0.05, 0.27), 0.22
TAX_FALLBACK_Q = 8                    # 유효세율이 음수·클립 밖이면 최근 8분기 중 세전이익 > 0 인 분기의 (법인세/세전) 중위(T6 D2)
# 이월결손 세율 경로(라운드 7 D2, 2026-10-08 오너 결정): default 폴백 앞 단계로 상시 적용, 감지는 세율 시계열만(BS 증거 게이트 없음).
# 근거: 한화오션 양(+)세전 7분기 중위 0.7%·HJ重 0.45%(2026Q2) — 삼성重 선례는 저세율 6분기 뒤 22~26% 로 정상화(최근 4분기 중위 24.3% 로 배제).
TAX_CF_MIN_POS_Q = 4                  # 최근 TAX_FALLBACK_Q 분기 중 세전 > 0 분기 최소 개수(나노 n=3 배제)
TAX_CF_RECENT_Q = 4                   # 그 중 최근 4분기의 중위도 문턱 아래여야 함(삼성重 24.3%·한화엔진 5.2% 배제 — 한화엔진은 경계값)
TAX_CF_LOW_MAX = TAX_CLIP[0]          # 감지 문턱 = 저세율 상한 5%(관찰 중위를 0~5% 로 클립해 유지)
TAX_CF_PATH = "carryforward_ramp"
GROWTH_CLIP = (-0.30, 0.50)
OPM_CLIP = (-0.20, 0.40)
CORR_MIN = 0.30                       # 고객 연동 회귀를 채택하는 최소 상관
# 고객 연동 격자 탐색(F2): 시차 0~4분기 × 회귀 창 8/12/19분기 × 변환(수준·YoY·4분기 이동합) — 상관 최대를 고르고 CORR_MIN 이상이면 채택.
# 후보가 많고 표본이 8~19 라 최대 상관은 위로 치우친다(다중비교·과적합) — 선택 경로·후보표·p<0.05 임계 r 을 driver 에 그대로 남긴다.
LINK_LAGS = (0, 1, 2, 3, 4)
LINK_WINDOWS = (8, 12, 19)
LINK_TRANSFORMS = ("level", "yoy", "ma4")
LINK_TRANSFORM_KO = {"level": "수준", "yoy": "YoY", "ma4": "4분기 이동합"}
LINK_MIN_N = 4                        # 회귀에 필요한 최소 짝
# 고객 연동 후보 자격(라운드 7 L5, 2026-10-08 오너 결정) — 통계 전에 사업 관계로 후보를 고른다(§14-6 ④: 한화시스템 related 0.03% 하나가 100% 가중치).
RELATED_SHARE_MIN = 5.0               # basis=related 만 있는 회사의 Σshare(%, suppliers.json share 단위 = 100×sales_m/rev_ytd_m) 자격 문턱 — 현 자료 (0.03, 8.60] 어디나 같은 결과, IFRS 8 주요고객 10% 보다 느슨한 추측값
LINK_ELIGIBLE_BASES = ("ifrs8", "contract", "text")   # 이 등급이 하나라도 있으면 자격 통과(basis 없는 레거시 yards 는 text 로 본다); 가중치·후보 목록은 바꾸지 않는다
LINK_NEFF_PENALTY = {"level": 0, "yoy": 0, "ma4": 3}  # 4분기 이동합은 인접 점이 3분기를 공유 → 유효 표본 n_eff = n − 3(격자·OOS 재적합 공통 필터 n_eff ≥ LINK_MIN_N)
LINK_SIG_USE_NEFF = False             # True 면 유의성 임계 r 을 df=n_eff−2 로(대창솔루션·일승 기각, 18→16) — 기록만 하고 게이트는 끔(오너 결정 스위치)
# 양측 5% t 임계값(df = n−2) → r_crit = t/√(df+t²). 표본 4~19 에 해당하는 df 2~17.
T_CRIT_P05 = {2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201,
              12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086}
N_ACTUAL_VIEW, N_EST_VIEW = 8, 10
EST_TOL = 0.05                        # 추정 항등식 허용(억원; 셀 2자리 반올림 3개 합)
PER_BAND_SANE = (3.0, 40.0)           # 과거 PER 중위가 이 밖이면(턴어라운드 왜곡) sector_default
PER_BAND_CAP = (5.0, 30.0)     # 과거 PER 밴드 상·하한 캡(2026-09-30) — 원값은 valuation.per_band.hist_band_raw 에 보존
OOS_WORSE_TOL = 1.10           # 고객 연동 OOS 채택(결정 ⓘ, 2026-09-30): 동결 4분기 매출 WAPE_link ≤ WAPE_trend × 1.10 이어야 채택
PANEL_SCENARIOS = ("conservative", "base", "optimistic")
PANEL_BASE = "base"            # 매출조선·매출액에 합산하는 forecast_panel 시나리오(결정 ⓓ) — 보수/낙관은 scenarios 블록에만
PANEL_REV_KEYS = ("new_order_revenue", "covered_scope_new_revenue")   # 우선 전범위, 없으면 모델 대상 부문만(한화오션·HJ — 2026-10-08 결정)
# 라운드 7 L1(2026-10-08 오너 결정) — 신규수주 두 스위치.
# ⓐ origin 이후 공시 수주의 처리: net_panel = 공시 계약은 SLS 일정(계약별 기간·헤지환율)으로 전부 유지하고 패널 신규수주에서 체결 분기별 공시 금액을
#    상계(net_s = max(0, N_s − D_s)) 뒤 패널 역산 커널로 재합성 | exclude_sls = 라운드 6(공시 SLS 를 패널 신규에 포함으로 보아 post_frac 만큼 제외).
#    기본 net_panel — 더 정확한 공시 일정을 덜 정확한 미보정 smoothstep 으로 대체하는 쪽이 거꾸로이고, 공시가 쌓이면 공시 장부로 단조 수렴한다.
NEW_ORDERS_POST_ORIGIN_MODE = "net_panel"
NEW_ORDERS_POST_ORIGIN_MODES = ("net_panel", "exclude_sls")
# ⓑ 폴백 사슬: 전범위 → 모델 대상 부문 → 공시 계약 원장 체결 속도(패널 신규수주가 원장 체결 속도의 LEDGER_RATE_MAX_PANEL_RATIO 미만이고 원장 창이
#    LEDGER_RATE_MIN_QUARTERS 이상이면 원장 체결 분기 min/median/max 를 보수/base/낙관 분기 신규수주로, 인식은 패널 역산 커널 — HJ重 110억 vs 3,572억).
#    FALLBACK_ONLY=True: covered_scope 폴백 회사만(대한조선 ratio 0.4578 은 창 4분기 분산 4,157~15,626 으로 2028E +48% 튀어 제외).
NEW_ORDERS_SOURCE_CHAIN = PANEL_REV_KEYS + ("ledger_signing_rate",)
LEDGER_RATE_MAX_PANEL_RATIO = 0.5
LEDGER_RATE_MIN_QUARTERS = 2
LEDGER_RATE_LEVELS = {"conservative": "min", "base": "median", "optimistic": "max"}   # 중위: 초대형 단일 분기(삼성重 2026Q2 99,815억 류)에 강건
LEDGER_RATE_FALLBACK_ONLY = True
LEDGER_RATE_CURVE = "panel_kernel"   # 대안 "linear_ledger_median"(다음 분기부터 원장 계약 일정 길이 중위 T 에 걸쳐 선형) — 감도는 ledger_rate.alt_linear 에 기록
PANEL_N_CONST_TOL = 1e-6             # 패널 new_orders 가 전 분기 상수일 때만 커널 역산(K(h)=rev(h)/N, k(lag)=K(lag+1)−K(lag)); 아니면 집계 비율 근사
# 2026-10-09 검증 수정 — 폴백(covered_scope) 회사의 패널 범위 밖 선종: coverage.excluded_segments → SLS type. 확실한 매핑만 상계 D·원장 창에서 제외(한화오션 EP및특수선 → NAVAL);
# OFFSH 는 WTIV 등 상선 가능성이 있어 제외하지 않고 D 에 섞이면 경고만(오너 확인 전). 제외분은 SLS 일정에 그대로 남는다.
SEGMENT_TYPE_EXCLUDE = {"EP및특수선": ("NAVAL",)}
SEGMENT_TYPE_UNCERTAIN = {"EP및특수선": ("OFFSH",)}

YARDS = ["010140", "042660", "329180", "439260", "097230"]
HOLDING, HOLDING_CORE = "009540", "329180"
SEJIN, SEJIN_SUBS = "075580", [("333430", "일승"), ("099410", "동방선기")]
SEJIN_REF_WEIGHTS = {"010620": 0.9, "329180": 0.2}      # 레퍼런스 `연간예상` r19~26 (HMsb 0.9 · HHI 0.2)
# 레퍼런스 §4-1 가중치 계열 — 기본(0.9·0.2) · 데크하우스(HMsb 1.0 · HHI 0.3→0.4) · 어퍼데크(HMsb 0.7 · HHI 0). 세진 그룹(세진·일승·동방선기)에만 후보.
SEJIN_REF_WEIGHT_FAMILY = [
    ("ref_base", {"010620": 0.9, "329180": 0.2}, "레퍼런스 `연간예상` HMsb 0.9 · HHI 0.2"),
    ("ref_deckhouse", {"010620": 1.0, "329180": 0.3}, "레퍼런스 데크하우스 HMsb 1.0 · HHI 0.3"),
    ("ref_deckhouse_alt", {"010620": 1.0, "329180": 0.4}, "레퍼런스 데크하우스 HMsb 1.0 · HHI 0.4"),
    ("ref_upperdeck", {"010620": 0.7}, "레퍼런스 어퍼데크 HMsb 0.7 · HHI 0"),
]
SEJIN_GROUP = {"075580", "333430", "099410"}
MERGERS = {"010620": ("329180", "2025Q4")}               # 피합병(2025Q4~ 보고서 없음) → 합병사
YARD_ALIAS = {"KSOE_GRP": "009540", "HSHI": "009540"}   # suppliers.json 의 그룹 표기 → 지주
ROLE_KO = {"yard": "조선사", "holding": "지주", "engine": "엔진", "equip": "기자재", "steel": "강재"}

# 행 정의: key, label, group, unit, fin 원천(kind, 계정명) — 원천 None 은 파생/추정 전용
ROW_DEFS = [
    ("매출액", "매출액", "손익", "억원", ("is", "매출액(수익)")),
    ("매출원가", "매출원가", "손익", "억원", ("is", "매출원가")),
    ("매출총이익", "매출총이익", "손익", "억원", ("is", "매출총이익")),
    ("판관비", "판매비와관리비", "손익", "억원", ("is", "판관비")),
    ("기타영업손익", "기타영업손익", "손익", "억원", ("is", "기타영업손익")),
    ("영업이익", "영업이익", "손익", "억원", ("is", "영업이익")),
    ("OPM", "영업이익률", "손익", "%", None),
    ("금융손익", "금융손익(이자·환 포함)", "손익", "억원", ("is", "금융손익")),
    # 금융손익 세부(T4): 주석(notes.fin → is) 계정이 있는 분기만 실적. 이자+외환+파생+기타금융 = 금융손익(잔차 정의)
    ("이자손익", "이자손익(이자수익 − 이자비용)", "손익", "억원", None),
    ("외환손익", "외환손익(실적만; 추정 환효과는 환관련손익)", "손익", "억원", None),
    ("파생상품손익", "파생상품손익", "손익", "억원", None),
    ("기타금융손익", "기타금융손익(금융손익 잔차)", "손익", "억원", None),
    ("기타영업외손익", "기타영업외손익", "손익", "억원", ("is", "기타영업외손익")),
    ("지분법손익", "지분법손익", "손익", "억원", ("is", "종속기업,공동지배기업및관계기업관련손익")),
    ("환관련손익", "환관련손익(모델 추정분)", "손익", "억원", None),
    ("세전이익", "법인세비용차감전이익", "손익", "억원", ("is", "법인세비용차감전계속사업이익")),
    ("법인세비용", "법인세비용", "손익", "억원", ("is", "법인세비용")),
    ("당기순이익", "당기순이익", "손익", "억원", ("is", "당기순이익")),
    ("지배주주순이익", "지배주주순이익", "손익", "억원", ("is", "(지배주주지분)당기순이익")),
    ("중단사업이익", "중단사업이익(실적만)", "손익", "억원", ("is", "중단사업이익")),
    ("감가상각비", "감가상각비", "손익", "억원", ("cf", "감가상각비")),
    ("EBITDA", "EBITDA", "손익", "억원", None),
    ("자산총계", "자산총계", "재무상태", "억원", ("bs", "자산총계")),
    ("부채총계", "부채총계", "재무상태", "억원", ("bs", "부채총계")),
    ("자본총계", "자본총계", "재무상태", "억원", ("bs", "자본총계")),
    ("지배주주지분", "지배주주지분", "재무상태", "억원", ("bs", "지배주주지분")),
    ("총차입금", "총차입금", "재무상태", "억원", ("bs", "총차입금")),
    ("순차입금", "순차입금", "재무상태", "억원", ("bs", "순차입금")),
    ("이자발생자산", "이자발생자산", "재무상태", "억원", ("bs", "이자발생자산")),
    ("현금및현금성자산", "현금및현금성자산", "재무상태", "억원", ("bs", "현금및현금성자산")),
    ("CAPEX", "CAPEX", "현금흐름", "억원", ("cf", "CAPEX")),
    ("영업활동현금흐름", "영업활동현금흐름", "현금흐름", "억원", ("cf", "영업활동으로인한현금흐름")),
    ("주식수", "유통주식수", "주당", "백만주", None),
    ("EPS", "EPS", "주당", "원", None),
    ("조정EPS", "조정 EPS(일회성 의심 분기의 초과 비영업손익 세후 차감 — 모델 추정)", "주당", "원", None),
    ("BPS", "BPS", "주당", "원", None),
    ("DPS", "DPS(보통주)", "주당", "원", None),
    ("PER", "PER", "주당", "배", None),
    ("PBR", "PBR", "주당", "배", None),
]
ROW_META = {k: (label, group, unit) for k, label, group, unit, _ in ROW_DEFS}
SRC_DEF = {k: src for k, _, _, _, src in ROW_DEFS if src}          # 행 key → (fin kind, 계정명)
ONE_OFF_MIN_RATIO = 4.0               # 비영업손익 |x| 가 12분기 중위의 4배 이상이고 …
ONE_OFF_TAX_Q_MAX = 0.35              # 조정EPS: 일회성 분기의 유효세율(법인세/세전)이 0~35% 안이면 그것, 아니면 모델 세율(tax_rate)
# 주식수 사건(라운드 7 (j), 2026-10-08 오너 결정): 병합·분할·무상증자는 사건 전 실적 EPS/BPS/DPS 를 비율 환산해 최신 주식수 기준으로 맞춘다(IAS 33.64 — DART 비교표시·
# FnGuide 수정주가 관행; prices.history_quarterly 가 네이버 수정주가라 환산 없이는 사건 전 PER/PBR 이력이 4~15배 틀어짐). 스위치 없이 상시 적용 — 비사건 회사는 바이트 불변.
SHARES_SPLIT_TOL = 0.005              # 정수비(n 또는 1/n) 자동 감지 상대 허용 — 단수주·소각 잡음(인화정공 유통 4.9799 포함, 한화오션 2023Q2 유상증자 2.0215 배제)
SHARES_SPLIT_N_MAX = 50               # 감지하는 최대 병합/분할 배수
SHARES_GAP_MIN = 0.01                 # fin 최신 보통주 발행주식수 vs prices.json shares_outstanding(aik 상장주식수 = 발행주식수, 58사 중 55 정확 일치) 1% 초과만 분기말 후 사건
SHARES_EPS_CHECK_TOL = 0.10           # fin eps_reported 비교표시 비율(prev ÷ 4분기 전 cur)이 1/사건비율 의 ±10% 안이면 교차검증 confirmed
SHARES_EPS_MIN_WON = 10               # 교차검증에 쓰는 |보고 EPS| 하한(원) — 0 근처 비율 잡음 배제
# 환산(사건 반영) 주식수 셀은 백만주 float 를 반올림하지 않는다 — selfcheck 가 estimate 주식수 셀 v×1e6 으로 EPS/BPS 를 재계산(r1 = 0.05원)하므로 3자리(500주)는 EPS 3.045원(메디콕스),
# 6자리(1주)도 BPS 0.056원(메디콕스 2021Q4, 1/75 환산) 초과 실측. 비사건 셀은 종전대로 3자리.
# 주식수 비율이 정수가 아닌 복합 사건(병합 + 증자/소각 동시)은 자동 감지 불가 → 수동. stock: [(사건 분기 q, 비율 r = 신/구, 근거)] — r 은 q 미만 분기의 주식수에 곱한다.
SHARE_EVENTS = {
    "012160": [("2026Q2", 0.2, "2026-06-16 액면병합 5:1(2026Q2 note_borrowings) + 자기주식 소각 → 주식수 비율 비정수(발행 0.154); eps_reported 2026Q2 prev_q/2025Q2 cur_q = 4.995")],
    "012210": [("2025Q2", 0.5, "2025-04-05 액면병합 500→1,000원(2025Q2 shares 주1) + 유상증자 3,933,333주; eps_reported 2025Q4 prev_full/2024Q4 cur_full = 2.01")],
    "054180": [("2022Q4", 2.0, "2022-12-09 무상증자 1:1(2022Q4 주석) + CB 전환 → 비정수 2.111; eps_reported 2023Q1 prev_q/2022Q1 cur_q = 5.059 = 10 × 1/2")],
}
# status 판정 규칙(T6 D7 뒤 데이터 완전성만) — quality.status_rule 로 모델에도 적는다. 드라이버 폴백은 driver_fallback 에 따로.
STATUS_RULE = ("full = fin 분기 ≥ 8 · 항등식 통과(추정 0건·실적 major 0건) · 추정 매출 ≥ %d분기 · 연결 손익 공백(별도 보충) 분기 없음 · "
               "마지막 fin 분기 = 최신 완결 분기(정기보고서 제출기한 45/90일 기준); 하나라도 어긋나면 partial(사유 status_reasons) · fin 없음 no_fin. "
               "드라이버 폴백(추세·OOS 기각 등)은 status 와 무관 — driver_fallback 필드" % FWD_MIN)
ONE_OFF_TTM_OP_SHARE = 0.5            # … 최근 4분기 |영업이익| 합의 절반 이상이면 '일회성 의심' 표시(숫자는 바꾸지 않음)
FLOW_KEYS = {"매출액", "매출원가", "매출총이익", "판관비", "기타영업손익", "영업이익", "금융손익", "이자손익", "외환손익", "파생상품손익", "기타금융손익",
             "기타영업외손익", "지분법손익",
             "환관련손익", "세전이익", "법인세비용", "당기순이익", "지배주주순이익", "중단사업이익", "감가상각비", "EBITDA", "CAPEX", "영업활동현금흐름", "EPS", "조정EPS", "DPS"}
STOCK_KEYS = {"자산총계", "부채총계", "자본총계", "지배주주지분", "총차입금", "순차입금", "이자발생자산", "현금및현금성자산", "주식수", "BPS"}
VIEW_KEYS = ["매출액", "매출원가", "매출총이익", "판관비", "영업이익", "OPM", "금융손익", "기타영업외손익", "세전이익", "법인세비용",
             "당기순이익", "지배주주순이익", "EPS", "BPS", "DPS", "PER", "PBR", "자산총계", "부채총계", "자본총계", "지배주주지분", "총차입금", "순차입금"]
REPORT_KEYS = ["매출액", "영업이익", "OPM", "지배주주순이익", "EPS", "조정EPS", "BPS", "DPS", "PER", "PBR"]   # 조정EPS 는 일회성 의심 회사에만 행이 있다
NOTE_NO_TP = "모델 산출값 — 목표주가·추천 아님"
# 금융손익 세부(T4): 행 key → ((fin is 계정명, 부호), …). 계정 하나라도 없으면 그 분기 그 행은 None(0 으로 채우지 않음)
FIN_DETAIL = [
    ("이자손익", (("이자수익", 1), ("이자비용", -1))),
    ("외환손익", (("외환차익", 1), ("외환차손", -1), ("외화환산이익", 1), ("외화환산손실", -1))),
    ("파생상품손익", (("파생상품이익", 1), ("파생상품손실", -1))),
]
RATE_NOTES_MIN_Q = 4                  # 주석 이자수익/이자비용이 최근 4분기(잔액 짝) 이상 있으면 CF 대신 그 연율
INTEREST_NOTE_CF_MAX_RATIO = 2.0      # 주석 연율 ÷ CF 연율 이 넘으면 이상 → 경고(stale 또는 절대상한 초과일 때만 클립). 2026-10-08 오너 결정: debt 24사 비율 분포가 1.75→2.75 로 비어 K∈[1.8,2.7] 동일 집합
INTEREST_RATE_ABS_MAX = 0.20          # 주석 연율 절대 상한 — 초과면 CF 연율(없으면 이 값)로 클립. 2026-10-08: 12% 안 씀 — HD 2사 13~14% 는 4분기 연속 안정(CV 0.12/0.15)이라 CF 로 바꾸면 실적 중위에서 더 멀어짐
FIN_OTHER_MIN_Q = 4                   # 기타금융손익 중위에 필요한 잔차 분기 수
FIN_OTHER_CAP = 0.5                   # |기타금융 중위| > |이자손익 추정| × 0.5 면 추정 0 + 경고


# ── 작은 도구 ─────────────────────────────────────────────────

def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def q_add(q, n):
    """'2026Q2' + n 분기."""
    y, k = int(q[:4]), int(q[5])
    i = y * 4 + (k - 1) + n
    return "%dQ%d" % (i // 4, i % 4 + 1)


def q_year(q):
    return int(q[:4])


def q_end_date(q):
    y, k = int(q[:4]), int(q[5])
    m = k * 3
    d = {3: 31, 6: 30, 9: 30, 12: 31}[m]
    return datetime.date(y, m, d)


def med(xs):
    xs = [x for x in xs if _num(x)]
    return statistics.median(xs) if xs else None


def clip(v, lo, hi):
    return None if not _num(v) else max(lo, min(hi, v))


def r2(v):
    return None if not _num(v) else round(v, 2)


def r4(v):
    return None if not _num(v) else round(v, 4)


def r4_weights(w):
    """가중치 dict 의 저장용 4자리 반올림 — 원값 합이 1 이면 반올림 잔차를 가장 큰 가중치에 얹어 저장값 합도 정확히 1 로 둔다.
    계산은 항상 원값(used)으로 하고 여기 결과는 표시·검사용이다(2026-10-05 통합: 현대힘스 0.57657/0.00226/0.42117 → 0.5766+0.0023+0.4212 = 1.0001 회귀)."""
    out = {k: r4(v) for k, v in w.items()}
    vals = [v for v in out.values() if _num(v)]
    if vals and len(vals) == len(out) and abs(sum(w.values()) - 1.0) < 1e-9:
        kmax = max(out, key=lambda k: (out[k], k))
        out[kmax] = r4(out[kmax] + (1.0 - sum(vals)))
    return out


def act(v, src):
    return {"v": r2(v), "kind": "actual", "src": src}


def est(v, basis):
    return {"v": r2(v), "kind": "estimate", "basis": basis}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_optional(path):
    try:
        return load_json(path)
    except (OSError, ValueError):
        return None


def dump_json(path, data):
    """정규화 JSON(키 순서 보존·들여쓰기 1) — 같은 데이터는 같은 바이트."""
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sxx * syy)


def wape_raw(pairs):
    """Σ|pred−act| / Σ|act| × 100 (반올림 전 — 규칙 비교용). pairs = [(pred, act)]."""
    pairs = [(p, a) for p, a in pairs if _num(p) and _num(a)]
    den = sum(abs(a) for _, a in pairs)
    if not pairs or den == 0:
        return None
    return sum(abs(p - a) for p, a in pairs) / den * 100


def wape(pairs):
    """Σ|pred−act| / Σ|act| × 100, 표시용 1자리 반올림. 임계 비교는 wape_raw 로(T6 D5a)."""
    w = wape_raw(pairs)
    return None if w is None else round(w, 1)


def _int_ratio(r):
    """r 이 정수 n 또는 1/n(n = 2..SHARES_SPLIT_N_MAX)에 상대 SHARES_SPLIT_TOL 안이면 그 비율(float), 아니면 None — 병합/분할/무상증자 판정(라운드 7 (j))."""
    if not _num(r) or r <= 0:
        return None
    for n in range(2, SHARES_SPLIT_N_MAX + 1):
        if abs(r - n) <= SHARES_SPLIT_TOL * n:
            return float(n)
        if abs(r - 1.0 / n) <= SHARES_SPLIT_TOL / n:
            return 1.0 / n
    return None


def _ratio_txt(r):
    """비율 표기 — 0.25 → '1/4' · 5.0 → '×5' · 0.25×0.25 → '1/16' · 2/15 → '2/15'."""
    fr = fractions.Fraction(r).limit_denominator(1000)
    return ("×%d" % fr.numerator) if fr.denominator == 1 else "%d/%d" % (fr.numerator, fr.denominator)


# ── fin 접근자(백만원 → 억원) ──────────────────────────────────

class Fin:
    """assets/fin/<stock>.json 을 분기 상한(origin) 으로 잘라 억원 단위로 읽는다. 연결이 없으면 별도."""

    def __init__(self, raw, upto=None):
        self.raw = raw
        self.stock = raw["stock"]
        self.name = raw.get("name")
        self.scope = "cons" if (raw.get("cons") or {}).get("is") else "sep"
        qs = [q for q in raw.get("quarters") or [] if not upto or q <= upto]
        self.quarters = sorted(qs)
        self.first, self.last = (self.quarters[0], self.quarters[-1]) if self.quarters else (None, None)
        # 연결 손익이 없는 분기(연결 미작성 분기보고서·Q4 3개월 도출 불가 등 — fin issues no_cons_statements/no_prior_ytd)에
        # 별도 손익이 있으면 그 분기는 별도로 보충한다(BS·CF 도 같은 분기는 별도). 셀 src 에 표기, 모델 quality.sep_filled 에 목록.
        self.sep_fill = [q for q in self.quarters if self.scope == "cons"
                         and self._get("cons", "is", q, "매출액(수익)") is None and self._get("sep", "is", q, "매출액(수익)") is not None]
        self._sep_fill = set(self.sep_fill)

    def _get(self, scope, kind, q, key):
        v = (((self.raw.get(scope) or {}).get(kind) or {}).get(q) or {}).get(key)
        return v if _num(v) else None

    def scope_of(self, q):
        """분기별 실제 사용 스코프 — 연결 공백 분기는 sep."""
        return "sep" if q in self._sep_fill else self.scope

    def val(self, kind, q, key, scope=None):
        """억원(주식수·EPS 아님). kind ∈ is|bs|cf|is_ytd|cf_ytd. scope 를 안 주면 분기별 scope_of(q)."""
        v = self._get(scope or self.scope_of(q), kind, q, key)
        return None if v is None else v / UNIT_DIV

    def series(self, kind, key, scope=None):
        out = {}
        for q in self.quarters:
            v = self.val(kind, q, key, scope)
            if v is not None:
                out[q] = v
        return out

    def src(self, kind, key, scope=None, q=None):
        """셀 src 문구. q 를 주면 그 분기의 실제 스코프(별도 보충이면 표기)."""
        sc = scope or (self.scope_of(q) if q else self.scope)
        s = "fin.%s.%s.%s" % (sc, kind, key)
        return s + " (연결 손익 없는 분기 → 별도 보충)" if (q in self._sep_fill and not scope) else s

    def shares_outstanding(self, q):
        """보통주 유통주식수(주). 분기 기재 생략은 fin 이 이월값(kind estimate)으로 채웠다."""
        s = (self.raw.get("shares") or {}).get(q) or {}
        v = s.get("common_outstanding") or s.get("outstanding")
        return v if _num(v) and v > 0 else None

    def last_shares(self):
        for q in reversed(self.quarters):
            v = self.shares_outstanding(q)
            if v:
                return v, q
        return None, None

    def other_note_accts(self, q):
        """기타영업외(other) 주석에 값이 있는 외환·파생 계정 집합(3개월 열 또는 누적) — 외환·파생이 금융 밖(기타영업외)에 있는지 판정용."""
        n = (((self.raw.get(self.scope_of(q)) or {}).get("notes") or {}).get("other") or {}).get(q) or {}
        y = n.get("ytd") or {}
        return {a for a in ("외환차익", "외환차손", "외화환산이익", "외화환산손실", "파생상품이익", "파생상품손실") if _num(n.get(a)) or _num(y.get(a))}

    def dps_series(self):
        """{연도: 보통주 DPS(원)} — fin.dividend 는 Q4 키."""
        out = {}
        for q, d in (self.raw.get("dividend") or {}).items():
            if q <= (self.last or "9999Q4") and _num(d.get("dps_common")):
                out[q_year(q)] = d["dps_common"]
        return out


# ── 컨텍스트(공용 자산·캐시) ──────────────────────────────────

class Ctx:
    def __init__(self, today=None):
        self.today = today or datetime.date.today().isoformat()
        self.fx = load_optional(os.path.join(ASSETS, "fx.json")) or {}
        self.prices = load_optional(os.path.join(ASSETS, "prices.json")) or {}
        self.suppliers = load_optional(os.path.join(ASSETS, "suppliers.json")) or {}
        self.universe = (load_optional(os.path.join(ASSETS, "universe.json")) or {}).get("rows") or []
        self.panel = self._load_panel()
        self._fin, self._sls, self._models, self._building = {}, {}, {}, set()
        self.roles, self.names = {}, {}
        for r in self.universe:
            self.roles[r["stock"]] = r.get("role")
            self.names[r["stock"]] = r.get("name")
        for c in self.suppliers.get("cos") or []:
            self.roles.setdefault(c["stock"], c.get("role"))
            self.names.setdefault(c["stock"], c.get("nm"))
        self.roles.setdefault(HOLDING, "holding")
        self.roles.setdefault("010620", "yard")       # HD현대미포 — 레퍼런스 3사, universe 밖(합병 소멸)
        for st, row in (self.prices.get("rows") or {}).items():
            self.names.setdefault(st, row.get("name"))
            if row.get("role"):
                self.roles.setdefault(st, row.get("role"))

    @staticmethod
    def _load_panel():
        p = os.path.join(ASSETS, "forecast_panel.json.gz")
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return {}
        return {c["stock"]: c for c in d.get("companies") or [] if c.get("stock")}

    def population(self):
        """57 = universe(41) ∪ suppliers ∪ 회사 폴더(56) ∪ 지주. 종목코드 정렬."""
        s = set(self.roles) | {HOLDING}
        for d in os.listdir(KSHIP):
            if re.fullmatch(r"\d{6}", d) and os.path.isdir(os.path.join(KSHIP, d)):
                s.add(d)
        if os.path.isdir(FIN_DIR):                      # fin 만 있는 회사(HD현대미포 010620 — 합병 소멸, 폴더 없음)도 모델은 만든다
            for f in os.listdir(FIN_DIR):
                if re.fullmatch(r"\d{6}\.json", f):
                    s.add(f[:6])
        return sorted(s)

    def fin(self, stock):
        if stock not in self._fin:
            self._fin[stock] = load_optional(os.path.join(FIN_DIR, stock + ".json"))
        return self._fin[stock]

    def sls(self, stock):
        if stock not in self._sls:
            self._sls[stock] = load_optional(os.path.join(SLS_DIR, stock + ".json"))
        return self._sls[stock]

    def price(self, stock):
        return (self.prices.get("rows") or {}).get(stock)

    def role(self, stock):
        return self.roles.get(stock) or ("yard" if stock in YARDS else None)

    def name(self, stock):
        fin = self.fin(stock)
        return self.names.get(stock) or (fin or {}).get("name") or stock

    def model(self, stock, origin=None):
        """(stock, origin) 캐시. 순환 참조는 None."""
        key = (stock, origin)
        if key in self._models:
            return self._models[key]
        if key in self._building:
            return None
        self._building.add(key)
        try:
            m = build_model(stock, self, origin=origin, freeze=origin is not None)
        finally:
            self._building.discard(key)
        self._models[key] = m
        return m

    def fx_q(self, q, key):
        """분기 환율: 완결 실측 > forward(추정). (값, kind)."""
        qd = (self.fx.get("quarters") or {}).get(q)
        if qd and _num(qd.get(key)) and not qd.get("partial"):
            return qd[key], "actual"
        fd = (self.fx.get("forward") or {}).get(q)
        if fd and _num(fd.get(key)):
            return fd[key], "estimate"
        if qd and _num(qd.get(key)):
            return qd[key], "estimate"
        return None, None


# ── 시계열 도구 ───────────────────────────────────────────────

def merged_rev(row):
    """행의 q 셀 → {q: v} (실적+추정)."""
    return {q: c["v"] for q, c in (row.get("q") or {}).items() if isinstance(c, dict) and _num(c.get("v"))}


def trend_seasonal(actual, fq):
    """전년동기 × (1+g). g = 최근 4분기 합 YoY(클립), 2년차 g/2 · 3년차 g/4 감쇠(가정). 계절성은 전년동기 기준으로 보존.
    반환 ({q: v}, {q: basis}, g)."""
    qs = sorted(actual)
    g = 0.0
    if len(qs) >= 8:
        ttm, prev = sum(actual[q] for q in qs[-4:]), sum(actual[q] for q in qs[-8:-4])
        g = clip((ttm / prev - 1) if prev > 0 else 0.0, *GROWTH_CLIP)
    avg4 = (sum(actual[q] for q in qs[-4:]) / min(4, len(qs))) if qs else None
    comb, out, basis = dict(actual), {}, {}
    for i, q in enumerate(fq):
        gk = g / (2 ** (i // 4))
        base = comb.get(q_add(q, -4))
        if base is None:
            base = avg4
            note = "최근 4분기 평균(전년동기 없음)"
        else:
            note = "전년동기"
        v = (base or 0.0) * (1 + gk)
        comb[q] = v
        out[q] = v
        basis[q] = "%s × (1+%.1f%%) — g=최근 4분기 합 YoY %.1f%% 클립(−30~+50%%), 연차별 절반 감쇠(가정)" % (note, gk * 100, g * 100)
    return out, basis, g


def opm_series(rev, op):
    return {q: op[q] / rev[q] for q in rev if q in op and rev[q]}


def last_n(d, n, upto=None):
    ks = sorted(k for k in d if (upto is None or k <= upto))
    return ks[-n:]


# ── 역할별 전략 ───────────────────────────────────────────────
# 전략은 (S: 실적 시계열 dict, fq: 추정 분기 목록, ctx, origin) → Plan(dict) 를 돌려준다.
#   Plan.rev {q: (v, basis)}, Plan.opm {q: (v, basis)}, Plan.segments [{key,label,driver,opm_path, rows:{rowkey:{q:cell}}}],
#   Plan.driver, Plan.warnings, Plan.modules, Plan.consolidation, Plan.fallback(bool), Plan.extra_rows {rowkey: {q: cell}}

def _plan(**kw):
    p = {"rev": {}, "opm": {}, "segments": [], "driver": {}, "warnings": [], "modules": [], "consolidation": None,
         "fallback": False, "extra_rows": {}}
    p.update(kw)
    return p


def _opm_hist(S, n=8):
    o = opm_series(S["매출액"], S["영업이익"])
    ks = last_n(o, n)
    return med([o[k] for k in ks]), ks


def strat_trend(stock, S, fq, ctx, origin, reason="고객 연결 없음", series=None):
    """폴백: 매출 추세+계절성, OPM = 최근 8분기 중위(클립). series 를 주면 그 시계열(세진 별도 매출)로 추세를 만든다."""
    rev, basis, g = trend_seasonal(series if series else S["매출액"], fq)
    opm, ks = _opm_hist(S)
    opm = clip(opm if opm is not None else 0.0, *OPM_CLIP)
    p = _plan(fallback=True)
    p["rev"] = {q: (rev[q], basis[q]) for q in fq}
    p["opm"] = {q: (opm, "최근 %d분기 OPM 중위 %.1f%% 유지(클립 −20~40%%)" % (len(ks), opm * 100)) for q in fq}
    p["driver"] = {"type": "trend_seasonal", "growth_yoy": r4(g), "opm_hist_median": r4(opm), "basis": "%s → 매출 추세+계절성" % reason}
    p["warnings"].append("매출 드라이버 폴백(%s): 전년동기 × (1+g) 추세" % reason)
    return p


def _panel_module(stock, ctx, fq, included=False, rev_key="new_order_revenue", netted=False, panel_key=None):
    """forecast_panel(기존 Y+2 수주 추정) 을 참고 모듈로 — 패널의 총매출 추정은 우리 매출 모델을 대체하지 않는다(스펙 1).
    included=True 면 신규수주 매출(base) 이 `매출조선신규` 행으로 모델에 들어갔다는 뜻(라벨만 바뀐다). rev_key 는 그 행의 출처 필드
    (한화오션은 covered_scope_new_revenue — 모델 대상 부문만; ledger_signing_rate 면 패널 필드 panel_key 의 원값을 보이고 '대체됨' 라벨).
    netted=True 면 행이 공시 상계 후 값이라 패널 행은 '상계 전 원값' 으로 적는다."""
    c = ctx.panel.get(stock)
    if not c or not (c.get("scenarios") or {}).get("base"):
        return None
    rows = []
    ledger = rev_key == "ledger_signing_rate"
    pkey = panel_key or (rev_key if not ledger else PANEL_REV_KEYS[1])
    rev_tag = "" if pkey == PANEL_REV_KEYS[0] else "(모델 대상 부문만·폴백·저신뢰)"
    if included and ledger:
        rev_label = "forecast_panel 신규수주 매출%s(base, 패널 원값) — 매출조선신규 행은 공시 계약 원장 체결 속도로 대체됨" % rev_tag
    elif included and netted:
        rev_label = "forecast_panel 신규수주 매출%s(base, 상계 전 패널 원값) — 매출조선신규 행은 공시 상계 후" % rev_tag
    elif included:
        rev_label = "forecast_panel 신규수주 매출%s(base) — 매출조선신규 행에 반영됨" % rev_tag
    else:
        rev_label = "forecast_panel 신규수주 매출%s(base, 참고·합산 안 함)" % rev_tag
    for key, label in (("value", "forecast_panel 매출 추정(base, 참고·합산 안 함)"), ("new_orders", "forecast_panel 신규수주(base)"), (pkey, rev_label)):
        cells = {}
        for row in c["scenarios"]["base"].get("quarterly") or []:
            q = row.get("quarter")
            if q in fq and _num(row.get(key)):
                cells[q] = est(row[key] / UNIT_DIV, "forecast_panel.json.gz base 시나리오(status %s) — 참고" % c.get("status"))
        if cells:
            rows.append({"key": "panel_" + ("new_order_revenue" if key == pkey else key), "label": label, "unit": "억원", "q": cells})
    return {"key": "forecast_panel", "label": "기존 Y+2 수주 추정(forecast_panel) — 나란히 표시", "rows": rows} if rows else None


def _panel_rev_key(c, fq):
    """base 시나리오에서 fq 안에 숫자가 있는 첫 신규 매출 필드. 전범위 new_order_revenue 가 우선이고, 패널이 데이터 충분성 때문에 그것을 비운
    회사(한화오션·HJ)는 같은 엔진·같은 R1 인식·같은 시나리오 정의의 covered_scope_new_revenue(모델 대상 부문만) 로 폴백한다. 없으면 None."""
    rows = (((c.get("scenarios") or {}).get(PANEL_BASE) or {}).get("quarterly")) or []
    for key in PANEL_REV_KEYS:
        if any(row.get("quarter") in fq and _num(row.get(key)) for row in rows):
            return key
    return None


def _panel_kernel(c, fq, key):
    """패널 시나리오별 코호트 입력 — 패널은 분기 신규수주(new_orders)와 그 매출 흐름(key)만 주고 인식 커널을 주지 않으므로 역산한다(라운드 7 L1).
    new_orders 가 전 분기 상수(N)면 rev(h) = N × Σ_{lag≤h−1} k(lag) 이라 K(h) = rev(h)/N, k(lag) = K(lag+1) − K(lag)(K(0)=0; lag 0..H−1) 로 정확히 풀린다
    — k(0) = K(1) 은 도착 분기 인식분(실제 패널은 분기말 도착·다음 분기 첫 인식이라 5사 모두 0). 5사 실측: k ≥ 0, 재합성 차 0.0억; 커널은 수주 수준에
    약하게 의존(삼성重 시나리오 간 |ΔK| ≤ 0.022)해 시나리오별로 따로 역산.
    상수가 아니면 k=None·kernel 'aggregate_ratio'(집계 비율 근사). 항등식은 horizon 이 1..H 연속이고 모든 horizon 에 매출 행이 있을 때만 정확하므로
    (2026-10-09 검증 수정) 내부 분기 결손·horizon 오프셋도 aggregate_ratio 로 떨어뜨리고 결손 분기를 gap 에 적는다(_net_panel_new_orders 가 경고).
    분기 축은 패널 quarter 라벨·horizon(패널 origin 기준) — 코호트는 패널 전 분기, 출력은 모델 fq 와 교집합만(HANDOFF 패널/origin 어긋남 대비).
    반환 {scn: {N_by_q, rev_raw, k, K, horizon, kernel, contiguous, gap}}(억원)."""
    out = {}
    for scn in PANEL_SCENARIOS:
        rows = [r for r in ((c.get("scenarios") or {}).get(scn) or {}).get("quarterly") or [] if r.get("quarter")]
        rows.sort(key=lambda r: r["quarter"])
        hz = {r["quarter"]: int(r["horizon"]) if _num(r.get("horizon")) else i + 1 for i, r in enumerate(rows)}
        N = {r["quarter"]: r["new_orders"] / UNIT_DIV for r in rows if _num(r.get("new_orders"))}
        rev = {r["quarter"]: r[key] / UNIT_DIV for r in rows if _num(r.get(key))}
        ns = list(N.values())
        gap = ([q for q in q_range(rows[0]["quarter"], rows[-1]["quarter"]) if q not in hz] if rows else []) + [q for q in hz if q not in rev]
        contiguous = sorted(hz.values()) == list(range(1, len(hz) + 1)) and not gap
        const = bool(ns) and max(ns) > 0 and (max(ns) - min(ns)) / max(ns) < PANEL_N_CONST_TOL and set(N) == set(hz) and contiguous
        k = K = None
        if const:
            n0 = ns[0]
            K = {hz[q]: rev[q] / n0 for q in hz}
            K[0] = 0.0
            H = max(K)
            k = {lag: K[lag + 1] - K[lag] for lag in range(0, H)}
        out[scn] = {"N_by_q": N, "rev_raw": rev, "k": k, "K": K, "horizon": hz, "kernel": "backsolved" if const else "aggregate_ratio",
                    "contiguous": contiguous, "gap": gap}
    return out


def _flow_from_cohorts(cohort, fq, disclosed=None):
    """코호트 → 분기 매출(억원): 매출(q) = Σ_{s: h_s ≤ h_q} max(0, N_s − D_s) × k(h_q − h_s). k 가 없으면(aggregate_ratio) rev_raw(q) × Σ_{s≤q} net_s / Σ_{s≤q} N_s.
    패널이 안 덮는 분기(horizon 없음)는 0 — _panel_new_orders 의 '미커버 분기 0' 과 같은 규칙."""
    D = disclosed or {}
    hz, N, k, raw = cohort["horizon"], cohort["N_by_q"], cohort.get("k"), cohort.get("rev_raw") or {}
    net = {s: max(0.0, n - D.get(s, 0.0)) for s, n in N.items()}
    out = {}
    for q in fq:
        hq = hz.get(q)
        if hq is None:
            out[q] = 0.0
        elif k is not None:
            out[q] = sum(net[s] * k[hq - hz[s]] for s in N if 0 <= hq - hz[s] and (hq - hz[s]) in k)
        else:
            tot = sum(N[s] for s in N if hz[s] <= hq)
            out[q] = raw.get(q, 0.0) * ((sum(net[s] for s in N if hz[s] <= hq) / tot) if tot > 0 else 1.0)
    return out


def _panel_new_orders(stock, ctx, fq):
    """forecast_panel.json.gz 의 시나리오별 신규수주 매출(new_order_revenue, 없으면 covered_scope_new_revenue; KRW_million → 억원 ÷100). 반환 dict:
    available(base 가 fq 안에 숫자를 하나라도 갖는가) · source_field · fallback(covered_scope 폴백 여부) · by_scenario {scn: {q: 억원}}(패널이 안 덮는 분기는 0) ·
    status·reason_codes · coverage(모델 대상·제외 부문, 잔고 억원) · covered/uncovered 분기 · basis(셀 basis 문구) · note. 패널이 없거나 두 필드 다
    비면 available False. 라운드 7: cohorts(시나리오별 역산 커널·코호트) · new_orders_by_scenario {scn:{q:N}} · by_scenario_raw(상계 전 원값) · kernel_mode ·
    panel_field(패널 필드 — source_field 가 ledger_signing_rate 로 바뀌어도 유지) · ledger_rate/net_panel(strat_yard 의 두 헬퍼가 채움)."""
    c = ctx.panel.get(stock)
    out = {"available": False, "by_scenario": {}, "status": (c or {}).get("status"), "reason_codes": (c or {}).get("reason_codes") or [],
           "panel_origin": (c or {}).get("origin"), "covered": [], "uncovered": list(fq), "basis": "", "note": "",
           "source_field": PANEL_REV_KEYS[0], "panel_field": PANEL_REV_KEYS[0], "fallback": False, "coverage": None,
           "source_chain": list(NEW_ORDERS_SOURCE_CHAIN), "ledger_rate": None, "net_panel": None}
    if not c:
        out["note"] = "forecast_panel 에 %s 없음" % stock
        return out
    scn = c.get("scenarios") or {}
    key = _panel_rev_key(c, fq)
    if key:
        out["source_field"], out["panel_field"], out["fallback"] = key, key, key != PANEL_REV_KEYS[0]
    cov = c.get("coverage") or {}
    if cov:
        out["coverage"] = {"modeled_segments": cov.get("modeled_segments"), "excluded_segments": cov.get("excluded_segments"),
                           "reported_backlog_eok": r2(cov["reported_backlog"] / UNIT_DIV) if _num(cov.get("reported_backlog")) else None,
                           "modeled_backlog_eok": r2(cov["modeled_backlog"] / UNIT_DIV) if _num(cov.get("modeled_backlog")) else None}
    for name in PANEL_SCENARIOS:
        d = {}
        for row in (scn.get(name) or {}).get("quarterly") or []:
            q, v = row.get("quarter"), row.get(out["source_field"])
            if q in fq and _num(v):
                d[q] = v / UNIT_DIV
        out["by_scenario"][name] = {q: d.get(q, 0.0) for q in fq}
        if name == PANEL_BASE:
            out["covered"] = sorted(d)
            out["uncovered"] = [q for q in fq if q not in d]
    out["available"] = bool(out["covered"])
    # 패널 신규수주의 정의(T6 D1) — 공시 계약을 개별로 반영하는지 판단하는 근거(assumptions·제외 건수·분기 신규수주 금액)
    base = scn.get(PANEL_BASE) or {}
    asm = base.get("assumptions") or {}
    out["definition"] = {k: asm.get(k) for k in ("order_basis", "new_order_arrival", "progress_curve", "calibrated") if k in asm}
    out["new_orders_by_q"] = {row["quarter"]: row["new_orders"] / UNIT_DIV for row in base.get("quarterly") or []
                              if row.get("quarter") in fq and _num(row.get("new_orders"))}
    exc = ((c.get("industry_axes") or {}).get("schedule_exclusions")) or c.get("industry_axes_schedule_exclusions") or {}   # 패널 원본 · 발췌(평탄화) 둘 다
    out["not_known_at_origin"] = exc.get("not_known_at_origin") if _num(exc.get("not_known_at_origin")) else None
    if not out["available"]:
        out["note"] = "forecast_panel %s status %s(%s) — %s 값 없음" % (stock, out["status"], ", ".join(out["reason_codes"]) or "-", " · ".join(PANEL_REV_KEYS))
        return out
    out["cohorts"] = _panel_kernel(c, fq, out["source_field"])
    out["new_orders_by_scenario"] = {scn: dict(out["cohorts"][scn]["N_by_q"]) for scn in PANEL_SCENARIOS}
    out["by_scenario_raw"] = {scn: dict(d) for scn, d in out["by_scenario"].items()}
    out["kernel_mode"] = out["cohorts"][PANEL_BASE]["kernel"]
    cv = out["coverage"] or {}
    out["basis"] = "forecast_panel.json.gz scenarios.%s %s(KRW_million÷100), status %s, calibrated=false, book-value proxy%s%s; 출처 사슬 %s" % (
        PANEL_BASE, out["source_field"], out["status"], ("; 패널 미커버 분기 0: " + ", ".join(out["uncovered"])) if out["uncovered"] else "",
        ("; ※폴백 — 패널이 전범위 new_order_revenue 를 비워(%s) 모델 대상 부문(%s%s)만 덮는 covered_scope_new_revenue 사용 · 저신뢰"
         % (", ".join(out["reason_codes"]) or "-", "·".join(cv.get("modeled_segments") or []) or "—",
            (", 제외 " + "·".join(cv["excluded_segments"])) if cv.get("excluded_segments") else "")) if out["fallback"] else "",
        "→".join(NEW_ORDERS_SOURCE_CHAIN))
    return out


def _scope_excluded_types(no):
    """폴백(covered_scope) 회사의 패널 범위 밖 선종 — coverage.excluded_segments 를 SEGMENT_TYPE_EXCLUDE(확실) · SEGMENT_TYPE_UNCERTAIN(경고만)으로 매핑.
    반환 (제외 type 튜플, 불확실 type 튜플); 폴백이 아니거나 제외 부문이 없으면 둘 다 빈 튜플(2026-10-09 검증 수정)."""
    if not (no and no.get("fallback")):
        return (), ()
    segs = ((no.get("coverage") or {}).get("excluded_segments")) or []
    return (tuple(t for s in segs for t in SEGMENT_TYPE_EXCLUDE.get(s, ())), tuple(t for s in segs for t in SEGMENT_TYPE_UNCERTAIN.get(s, ())))


def _post_origin_panel_fraction(post, no):
    """origin 이후 공시 수주 중 패널 신규수주 흐름이 담았다고 볼 수 있는 비율(0~1, T6 D1 의 '패널 신규에 포함' 가정을 패널 규모로 한정).
    체결 분기마다 min(1, 패널 base 그 분기 신규수주 ÷ 그 분기 공시 수주) — 패널이 공시 체결 속도보다 훨씬 작으면(HJ重 패널 110억/분기 vs 공시 6,790억)
    공시 수주를 통째로 빼면 실제 수주가 사라진다. 패널이 공시 수주 이상이면 1(기존 규칙 그대로 — 삼성重·HD현대重·대한조선은 전부 1).
    날짜 없는 공시 수주는 1 로 본다(기존 규칙). 패널 범위 밖 선종(post.by_sign_q_excluded — SEGMENT_TYPE_EXCLUDE)은 패널 신규에 없으니 0(SLS 유지).
    반환 (비율, {체결 분기: 비율})."""
    amts, tot = post["by_sign_q"], post["amt"]
    if tot <= 0:
        return 1.0, {}
    pn = no.get("new_orders_by_q") or {}
    by = {sq: (min(1.0, pn[sq] / a) if (sq in pn and a > 0) else 0.0) for sq, a in amts.items()}
    excluded = sum((post.get("by_sign_q_excluded") or {}).values())
    undated = max(tot - sum(amts.values()) - excluded, 0.0)
    if undated <= 1e-9 and excluded <= 1e-9 and all(v >= 1.0 for v in by.values()):
        return 1.0, by
    return (sum(by[sq] * amts[sq] for sq in amts) + undated) / tot, by


def _ledger_signing_crosscheck(sls, no, n_quarters=8, exclude_types=()):
    """공시 계약 원장의 체결 분기별 금액(해양·counted·origin 분기말까지, 억원) 과 패널 base 신규수주를 나란히 — 패널 신규수주가 공시 체결 속도와
    얼마나 떨어져 있는지(폴백 저신뢰 근거). 원장은 공시 대상 계약만이라 전체 수주의 하한 성격이다. exclude_types(패널 범위 밖 선종, SEGMENT_TYPE_EXCLUDE)
    는 창에서 빼고 excluded_signed_eok 에만 적는다. n_quarters_positive = 창 안 체결 > 0 분기 수(ledger 수준 통계·게이트의 표본 — 2026-10-09 검증 수정)."""
    origin = sls.get("origin")
    if not origin:
        return None
    oend = q_end_date(origin)
    by, exq = collections.defaultdict(float), collections.defaultdict(float)
    for c in sls.get("contracts") or []:
        if not c.get("counted", True) or c.get("type") == "OTHER" or not _num(c.get("amt_krw_m")):
            continue
        try:
            d = datetime.date.fromisoformat(c.get("signed") or c.get("start"))
        except (TypeError, ValueError):
            continue
        if d <= oend:
            (exq if c.get("type") in exclude_types else by)["%dQ%d" % (d.year, (d.month - 1) // 3 + 1)] += c["amt_krw_m"] / UNIT_DIV
    qs = q_range(q_add(origin, 1 - n_quarters), origin)
    first = next((i for i, q in enumerate(qs) if by.get(q, 0.0) > 0), None)
    if first:                                   # 원장 첫 체결 분기 앞의 0 은 '수주 없음' 이 아니라 원장이 닿지 않는 구간 — 평균을 깎지 않게 뺀다
        qs = qs[first:]
    vals = [by.get(q, 0.0) for q in qs]
    excluded = sum(exq.get(q, 0.0) for q in qs)
    pn = [v for v in (no.get("new_orders_by_q") or {}).values() if _num(v)]
    led_mean = sum(vals) / len(vals)
    pn_mean = sum(pn) / len(pn) if pn else None
    return {"quarters": qs, "ledger_signed_by_q_eok": {q: r2(by.get(q, 0.0)) for q in qs}, "ledger_mean_per_q_eok": r2(led_mean),
            "ledger_median_per_q_eok": r2(med(vals)), "ledger_min_per_q_eok": r2(min(vals)), "ledger_max_per_q_eok": r2(max(vals)), "n_quarters_used": len(qs),
            "n_quarters_positive": sum(1 for v in vals if v > 0),
            "excluded_types": list(exclude_types), "excluded_signed_eok": r2(excluded),
            "panel_base_new_orders_mean_per_q_eok": r2(pn_mean) if pn_mean is not None else None,
            "panel_to_ledger_ratio": r4(pn_mean / led_mean) if (pn_mean is not None and led_mean > 0) else None,
            "note": "공시 계약 원장(대형 단일 계약만 — 하한, 첫 체결 분기부터 최대 8분기) 체결 평균 대비 패널 base 신규수주 평균. 비율 <0.5 이면 패널이 공시 체결 속도를 못 따라간 것(과소), >1.5 이면 순보충(FX 취소 미분리) 기반이라 상향 편향 가능"}


def _fy_sum(d, fq):
    out = collections.OrderedDict()
    for q in fq:
        out[q[:4]] = out.get(q[:4], 0.0) + d.get(q, 0.0)
    return out


def _ledger_rate_new_orders(no, led_cc, fq, sls):
    """폴백 사슬 3단(라운드 7 L1 ⓑ): 패널 신규수주가 공시 계약 원장 체결 속도의 LEDGER_RATE_MAX_PANEL_RATIO 미만(HJ重 110억 vs 분기 평균 3,640억 = 3%)이고
    원장 창이 LEDGER_RATE_MIN_QUARTERS 이상이면 원장 체결 분기 금액의 min/median/max 를 보수/base/낙관 분기 신규수주로 쓴다(LEDGER_RATE_LEVELS).
    인식 커브는 그 시나리오의 패널 역산 커널(LEDGER_RATE_CURVE panel_kernel; 커널 없으면 선형 T=원장 계약 일정 길이 중위). no 를 제자리에서 바꾸고 돌려준다 —
    바꿨으면 no['ledger_rate'] 에 수준·창·비율·커브·선형 대안 FY 매출(감도)을 적고 source_field='ledger_signing_rate'·fallback·저신뢰. 조건 미달이면 그대로.
    2026-10-09 검증 수정: 수준 통계·LEDGER_RATE_MIN_QUARTERS 게이트는 체결 > 0 분기만(창 안 0 분기가 min/median 을 0 으로 끌어내리지 않게; 평균·비율은 창 전체 그대로),
    시나리오 수준은 패널 자체의 그 시나리오 N 을 하한(패널이 너무 낮아 바꾸는 경로라 패널보다 낮아질 수 없다). 선형 대안 커널은 alt_linear_k 에 두고
    alt_linear_FY_rev 는 상계 전 값으로 시작 — net_panel 이 상계 후(행과 같은 축)로 덮어쓰고 상계 전은 alt_linear_FY_rev_pre_netting 에 남긴다."""
    ratio = (led_cc or {}).get("panel_to_ledger_ratio")
    if not (no and no.get("available") and no.get("cohorts")) or ratio is None or ratio >= LEDGER_RATE_MAX_PANEL_RATIO \
            or (led_cc.get("n_quarters_positive") or 0) < LEDGER_RATE_MIN_QUARTERS or (LEDGER_RATE_FALLBACK_ONLY and not no["fallback"]):
        return no
    pos = [v for v in led_cc["ledger_signed_by_q_eok"].values() if v > 0]
    lv = {"min": min(pos), "median": med(pos), "max": max(pos)}
    panel_n_scn = {scn: max(no["cohorts"][scn]["N_by_q"].values(), default=0.0) for scn in PANEL_SCENARIOS}
    levels_raw = {scn: lv[LEDGER_RATE_LEVELS[scn]] for scn in PANEL_SCENARIOS}
    levels = {scn: max(levels_raw[scn], panel_n_scn[scn]) for scn in PANEL_SCENARIOS}
    lens = [len(c["schedule"]) for c in sls.get("contracts") or [] if c.get("counted", True) and c.get("type") != "OTHER" and c.get("schedule")]
    T = int(round(med(lens))) if lens else None
    kern_ok = all(no["cohorts"][scn].get("k") for scn in PANEL_SCENARIOS)
    curve = "panel_kernel" if (LEDGER_RATE_CURVE == "panel_kernel" and kern_ok) else "linear_ledger_median"
    if curve == "linear_ledger_median" and not T:
        return no
    lin = {lag: 1.0 / T for lag in range(1, T + 1)} if T else None     # 선형 대안: 다음 분기부터(lag 0 없음) T 분기 균등
    alt = None
    for scn in PANEL_SCENARIOS:
        co = no["cohorts"][scn]
        co["N_panel_by_q"] = dict(co["N_by_q"])                             # 패널 원값 N(ledger 모드 문구의 '패널 N억')
        co["N_by_q"] = {s: levels[scn] for s in co["horizon"]}
        if curve == "linear_ledger_median":
            co["k"], co["kernel"] = lin, "linear_ledger_median"
        no["by_scenario"][scn] = _flow_from_cohorts(co, fq)
        no["new_orders_by_scenario"][scn] = dict(co["N_by_q"])
        if scn == PANEL_BASE and lin:
            alt = _fy_sum(_flow_from_cohorts(dict(co, k=lin), fq), fq)
    hz = no["cohorts"][PANEL_BASE]["horizon"]
    panel_n = led_cc.get("panel_base_new_orders_mean_per_q_eok")
    no["new_orders_by_q"] = {q: levels[PANEL_BASE] for q in fq if q in hz}
    no["source_field"], no["fallback"], no["kernel_mode"] = "ledger_signing_rate", True, no["cohorts"][PANEL_BASE]["kernel"]
    no["ledger_rate"] = {"levels": {scn: r2(v) for scn, v in levels.items()}, "level_rule": dict(LEDGER_RATE_LEVELS),
                         "levels_ledger_raw": {scn: r2(v) for scn, v in levels_raw.items()}, "panel_floor_per_q_eok": {scn: r2(v) for scn, v in panel_n_scn.items()},
                         "panel_floor_applied": [scn for scn in PANEL_SCENARIOS if levels[scn] > levels_raw[scn]],
                         "window_quarters": led_cc["quarters"], "ledger_signed_by_q_eok": led_cc["ledger_signed_by_q_eok"], "n_quarters_used": led_cc["n_quarters_used"],
                         "n_quarters_positive": len(pos), "excluded_types": led_cc.get("excluded_types") or [],
                         "panel_to_ledger_ratio": ratio, "max_panel_ratio": LEDGER_RATE_MAX_PANEL_RATIO, "panel_fallback_base_per_q_eok": panel_n,
                         "panel_field": no["panel_field"], "curve": curve, "kernel_mode": no["kernel_mode"], "alt_linear_T": T, "alt_linear_k": lin,
                         "alt_linear_FY_rev": ({y: r2(v) for y, v in alt.items()} if alt else None),
                         "alt_linear_FY_rev_pre_netting": ({y: r2(v) for y, v in alt.items()} if alt else None), "fallback_only": LEDGER_RATE_FALLBACK_ONLY,
                         "note": "원장은 공시 대상 대형 계약만 잡는 하한 · 표본 %d분기(%s; 수준 통계는 체결 > 0 인 %d분기) — 보수~낙관 폭이 좁아 불확실성을 과소표시할 수 있음(저신뢰)%s"
                                 % (led_cc["n_quarters_used"], " · ".join("%s %s억" % (q, format(round(v), ",d")) for q, v in led_cc["ledger_signed_by_q_eok"].items()), len(pos),
                                    ("; 패널 자체 N 하한 적용 %s" % "·".join("%s %s→%s억" % (scn, format(round(levels_raw[scn]), ",d"), format(round(levels[scn]), ",d"))
                                                                     for scn in PANEL_SCENARIOS if levels[scn] > levels_raw[scn])) if any(levels[s] > levels_raw[s] for s in PANEL_SCENARIOS) else "")}
    no["basis"] = ("폴백 사슬 %s: 패널 신규수주(분기 %s억)가 공시 체결 속도(분기 평균 %s억)의 %.0f%% → 원장 체결 분기(체결 > 0 인 %d분기) min/median/max(%s/%s/%s억, 창 %d분기 %s~%s)를 "
                   "보수/base/낙관 신규수주로(패널 자체 N 하한), 인식은 %s · 저신뢰"
                   % (" → ".join(NEW_ORDERS_SOURCE_CHAIN), format(round(panel_n or 0.0), ",d"), format(round(led_cc["ledger_mean_per_q_eok"]), ",d"), ratio * 100, len(pos),
                      format(round(levels["conservative"]), ",d"), format(round(levels[PANEL_BASE]), ",d"), format(round(levels["optimistic"]), ",d"),
                      led_cc["n_quarters_used"], led_cc["quarters"][0], led_cc["quarters"][-1],
                      "패널 역산 커널(%s)" % no["panel_field"] if curve == "panel_kernel" else "선형(다음 분기부터 원장 계약 일정 길이 중위 %d분기)" % T))
    return no


def _net_panel_new_orders(no, post, fq, sls_origin=None, uncertain_types=()):
    """net_panel(라운드 7 L1 ⓐ): origin 이후 공시 수주 D(체결 분기별·패널 범위 안, 억원)를 패널(또는 원장 수준) 신규수주 코호트에서 상계 — net_s = max(0, N_s − D_s) — 하고
    그 시나리오의 커널로 재합성해 by_scenario 를 덮어쓴다. 날짜 없는 공시(by_sign_q 미포함)는 상계 못 하므로 SLS 에 두고 경고. no 를 제자리에서 바꾸고 돌려준다;
    기록은 no['net_panel'](체결 분기별 패널/공시(범위 안·밖)/net · base 패널 매출 제거분 FY · 상계 안 된 금액 · 커널 모드 · 경고).
    2026-10-09 검증 수정: netted 항목에 source(ledger|panel)·panel_raw_new_orders(패널 원값 N) 를 적고 ledger 모드 문구는 '원장 수준 N억(패널 n억)';
    패널 범위 밖(SEGMENT_TYPE_EXCLUDE) 공시는 _sls_post_origin 이 by_sign_q_excluded 로 갈라 둔 것을 disclosed_out_of_scope 로만 기록(상계 안 함, SLS 유지);
    uncertain_types(OFFSH 등 매핑 불확실 선종)가 D 에 섞이면 과다 상계 가능 경고; ledger 모드의 선형 대안 FY 매출은 상계 후로 다시 잰다(행과 같은 축)."""
    D, Dx = dict(post["by_sign_q"]), dict(post["by_sign_q_excluded"])
    hz = no["cohorts"][PANEL_BASE]["horizon"]
    ledger = no.get("source_field") == "ledger_signing_rate"
    lab = "원장 수준" if ledger else "패널"
    warns = []
    base_co = no["cohorts"][PANEL_BASE]
    if no["kernel_mode"] == "aggregate_ratio" and not base_co.get("contiguous", True):
        warns.append("net_panel: 패널 horizon 결손 %s — 커널 역산 불가, 집계 비율 근사(kernel aggregate_ratio, 정확도 하락)"
                     % (", ".join(base_co.get("gap") or []) or "horizon " + "·".join(str(h) for h in sorted(base_co["horizon"].values()))))
    elif no["kernel_mode"] == "aggregate_ratio":
        warns.append("net_panel: 패널 new_orders 가 상수가 아니라 커널 역산 불가 → 집계 비율 근사(kernel aggregate_ratio 근사, 정확도 하락)")
    undated = post["undated_amt"]
    if undated > 1e-9:
        warns.append("net_panel: 날짜 없는 공시 수주 %.0f억은 체결 분기를 몰라 상계 못 함 — SLS 에 그대로 유지(패널 신규와 이중계산 가능)" % undated)
    if sls_origin and no.get("panel_origin") and no["panel_origin"] != sls_origin:
        warns.append("net_panel: 패널 origin %s ≠ sls origin %s — 상계 D 는 패널 origin 이후 체결 전부여야 하고 분기 축은 패널 quarter 라벨(확인 필요)"
                     % (no["panel_origin"], sls_origin))
    outside = sorted(sq for sq in D if sq not in hz)
    if outside:
        warns.append("net_panel: 공시 체결 분기 %s 는 패널 코호트 밖 — 상계 안 됨(SLS 유지)" % ", ".join(outside))
    unc_amt = sum(v for by_t in post["by_sign_q_type"].values() for t, v in by_t.items() if t in uncertain_types)
    if unc_amt > 1e-9:
        warns.append("net_panel: 패널 범위 밖일 수 있는 type 상계 %s억(과다 상계 가능) — %s 는 패널 제외 부문(%s) 매핑이 불확실해 상계에 둠(오너 확인)"
                     % (format(round(unc_amt), ",d"), "·".join(t for t in uncertain_types), "·".join((no.get("coverage") or {}).get("excluded_segments") or [])))
    pre_base = _flow_from_cohorts(base_co, fq)
    for scn in PANEL_SCENARIOS:
        no["by_scenario"][scn] = _flow_from_cohorts(no["cohorts"][scn], fq, disclosed=D)
    Nb, Nraw = base_co["N_by_q"], base_co.get("N_panel_by_q") or base_co["N_by_q"]
    netted = collections.OrderedDict()
    for sq in sorted(set(D) | set(Dx)):
        a, x = D.get(sq, 0.0), Dx.get(sq, 0.0)
        netted[sq] = {"panel_new_orders": r2(Nb.get(sq, 0.0)), "source": "ledger" if ledger else "panel", "panel_raw_new_orders": r2(Nraw.get(sq, 0.0)),
                      "disclosed": r2(a + x), "disclosed_in_scope": r2(a), "disclosed_out_of_scope": r2(x), "net": r2(max(0.0, Nb.get(sq, 0.0) - a))}
    pre_fy, post_fy = _fy_sum(pre_base, fq), _fy_sum(no["by_scenario"][PANEL_BASE], fq)
    removed = collections.OrderedDict((y, r2(pre_fy[y] - post_fy[y])) for y in pre_fy)
    def _one(sq, v):
        n_txt = ("%s 원장 수준 %s억(패널 %s억)" % (sq, format(round(v["panel_new_orders"]), ",d"), format(round(v["panel_raw_new_orders"]), ",d"))) if ledger else \
                ("%s 패널 %s억" % (sq, format(round(v["panel_new_orders"]), ",d")))
        x_txt = ("(범위 밖 %s억 제외)" % format(round(v["disclosed_out_of_scope"]), ",d")) if v["disclosed_out_of_scope"] > 0 else ""
        return "%s − 공시 %s억%s = %s억" % (n_txt, format(round(v["disclosed_in_scope"]), ",d"), x_txt, format(round(v["net"]), ",d"))
    no["net_panel"] = {"netted_by_sign_quarter": netted, "panel_revenue_removed_by_fy": removed, "undated_not_netted_eok": r2(undated),
                       "scope_excluded_types": list(post["scope_excluded_types"]), "disclosed_out_of_scope_eok": r2(sum(Dx.values())),
                       "source": "ledger" if ledger else "panel", "kernel_mode": no["kernel_mode"], "warnings": warns,
                       "text": " · ".join(_one(sq, v) for sq, v in netted.items())}
    lr = no.get("ledger_rate")
    if ledger and lr and lr.get("alt_linear_k"):
        alt = _fy_sum(_flow_from_cohorts(dict(base_co, k=lr["alt_linear_k"]), fq, disclosed=D), fq)
        lr["alt_linear_FY_rev"] = {y: r2(v) for y, v in alt.items()}
    no["basis"] += "; origin 이후 공시 수주 체결 분기별 상계(net_panel: %s)" % no["net_panel"]["text"]
    return no


def _sls_r3_info(sls):
    """sls(R3 라운드 3) 의 cohort_mode · backlog_cap_applied · target_opm_alt 를 읽는다 — 키가 없으면 '정보 없음' 으로 동작(구버전 sls 호환).
    backlog_cap_applied 는 dict(applied/scale/coverage) · bool · 배율(숫자) 어느 형태든 받는다."""
    sls = sls or {}
    mode = sls.get("cohort_mode")
    cap = sls.get("backlog_cap_applied")
    if isinstance(cap, dict):
        applied = cap.get("applied")
        if applied is None:
            applied = bool(cap)
        scale = next((cap[k] for k in ("scale", "factor", "multiplier", "ratio") if _num(cap.get(k))), None)
        cov = next((cap[k] for k in ("coverage", "backlog_coverage", "coverage_before", "backlog_coverage_at_origin") if _num(cap.get(k))), None)
        cap_text = "선표 잔고 캡 %s%s%s" % ("적용" if applied else "미적용", (" × %.3f" % scale) if _num(scale) else "", (" (커버리지 %.3f)" % cov) if _num(cov) else "")
    elif isinstance(cap, bool):
        applied, cap_text = cap, "선표 잔고 캡 %s" % ("적용" if cap else "미적용")
    elif _num(cap):
        applied, cap_text = cap != 1, "선표 잔고 캡 배율 %.3f" % cap
    else:
        applied, cap_text = None, "선표 잔고 캡 정보 없음(sls 에 backlog_cap_applied 없음)"
    mode_text = ("코호트 모드 %s" % mode) if mode else "코호트 모드 정보 없음(sls 에 cohort_mode 없음 → 원장 상대 등급)"
    alt = sls.get("target_opm_alt")
    alt_vals = [t.get("opm") for t in alt.values() if isinstance(t, dict) and _num(t.get("opm"))] if isinstance(alt, dict) else []
    return {"cohort_mode": mode, "cohort_text": mode_text, "backlog_cap_applied": applied,
            "backlog_cap_raw": cap if isinstance(cap, (dict, bool, int, float)) else None, "cap_text": cap_text,
            "target_opm_alt_available": bool(alt_vals), "target_opm_alt_median": r4(med(alt_vals)) if alt_vals else None}


def _sls_post_origin(sls, fq, exclude_types=()):
    """선표 해양 원화를 origin 분기말까지 체결분과 그 뒤 체결분으로 나눈다(T6 D1). 반환 dict(억원):
    existing {q} · post {q} · n · amt(공시 원화 합, 전 선종) · by_sign_q {체결 분기: 억원}(패널 범위 안 — 상계 D) · by_sign_q_excluded(exclude_types 선종, 상계 안 함) ·
    by_sign_q_type {체결 분기: {type: 억원}}(범위 안) · undated_amt(날짜 없는 공시) · scope_excluded_types · rcps · source.
    exclude_types(SEGMENT_TYPE_EXCLUDE — 2026-10-09 검증 수정)는 D 에서만 빠지고 post {q}(SLS 일정)에는 그대로 남는다.
    sls(T6 이후)의 by_quarter[q].marine_hedged_krw_m_signed_by_origin/_post_origin 이 있으면 그 값, 없으면(구버전 sls) contracts 의
    schedule(백만$) × (hedge_ratio × (hedge_rate 또는 수주시점 환율) + (1 − hedge_ratio) × spot_assumed) 로 다시 잰다 — origin 이후 계약은
    잔고 캡 대상이 아니므로 kship_sls 집계식과 같다(스케줄 3자리 반올림 차만)."""
    bq = sls.get("by_quarter") or {}
    oend = q_end_date(sls["origin"]) if sls.get("origin") else None
    hedge = sls.get("hedge") or {}
    out = {"existing": {}, "post": {}, "n": 0, "amt": 0.0, "by_sign_q": collections.defaultdict(float), "by_sign_q_excluded": collections.defaultdict(float),
           "by_sign_q_type": collections.defaultdict(lambda: collections.defaultdict(float)), "undated_amt": 0.0,
           "scope_excluded_types": list(exclude_types), "rcps": [], "source": None}
    posts = []
    for c in sls.get("contracts") or []:
        if not c.get("counted", True) or c.get("type") == "OTHER":
            continue
        sbo = c.get("signed_by_origin")
        try:
            d = datetime.date.fromisoformat(c.get("signed") or c.get("start"))
        except (TypeError, ValueError):
            d = None
        if sbo is None:
            if d is None or oend is None:
                continue
            sbo = d <= oend
        if sbo:
            continue
        posts.append(c)
        out["n"] += 1
        amt = (c.get("amt_krw_m") or 0.0) / UNIT_DIV
        out["amt"] += amt
        if d is None:
            out["undated_amt"] += amt
        elif c.get("type") in exclude_types:
            out["by_sign_q_excluded"]["%dQ%d" % (d.year, (d.month - 1) // 3 + 1)] += amt
        else:
            sq = "%dQ%d" % (d.year, (d.month - 1) // 3 + 1)
            out["by_sign_q"][sq] += amt
            out["by_sign_q_type"][sq][c.get("type") or "?"] += amt
        out["rcps"].append(c.get("rcp"))
    keyed = any("marine_hedged_krw_m_post_origin" in (bq.get(q) or {}) for q in fq)
    for q in fq:
        b = bq.get(q) or {}
        tot = (b.get("marine_hedged_krw_m") or 0.0) / UNIT_DIV
        if keyed:
            post = (b.get("marine_hedged_krw_m_post_origin") or 0.0) / UNIT_DIV
            ex = b.get("marine_hedged_krw_m_signed_by_origin")
            ex = ex / UNIT_DIV if _num(ex) else tot - post
        else:
            hr = b.get("hedge_ratio") if _num(b.get("hedge_ratio")) else (hedge.get("hedge_ratio") if _num(hedge.get("hedge_ratio")) else 0.7)
            sp = b.get("spot_assumed") if _num(b.get("spot_assumed")) else b.get("applied_rate")
            post = 0.0
            for c in posts:
                usd = (c.get("schedule") or {}).get(q)
                if not _num(usd) or not _num(sp):
                    continue
                hrate = hedge.get("hedge_rate") or c.get("fx_at_sign") or sp
                post += usd * (hr * hrate + (1.0 - hr) * sp) / UNIT_DIV
            post = min(post, tot)
            ex = tot - post
        out["post"][q], out["existing"][q] = post, ex
    out["source"] = ("sls.by_quarter.marine_hedged_krw_m_signed_by_origin/_post_origin" if keyed
                     else "sls.contracts 재계산(구버전 sls — schedule × 헤지 적용 환율)")
    out["by_sign_q"] = dict(sorted(out["by_sign_q"].items()))
    out["by_sign_q_excluded"] = dict(sorted(out["by_sign_q_excluded"].items()))
    out["by_sign_q_type"] = {sq: dict(sorted(t.items())) for sq, t in sorted(out["by_sign_q_type"].items())}
    return out


def _yard_backlog_at(stock, q, seg_names):
    """yards_cache/<stock>/<q>.json 의 수주잔고(closing) — 해양 부문명이 맞으면 그 합, 아니면 합계행."""
    d = load_optional(os.path.join(YARDS_CACHE, stock, q + ".json"))
    rows = ((d or {}).get("orders") or {}).get("rows") or []
    norm = lambda s: re.sub(r"\s+", "", s or "")
    names = {norm(s) for s in seg_names}
    hit = [r["closing"] for r in rows if not r.get("total") and norm(r.get("seg")) in names and _num(r.get("closing"))]
    if hit:
        return sum(hit)
    tot = [r["closing"] for r in rows if r.get("total") and _num(r.get("closing"))]
    return tot[0] if tot else None


def _sls_frozen(sls, freeze, share_out=None):
    """freeze 분기말까지 체결된 해양 계약만으로 SLS 를 다시 만든다(백테스트용). 원화 = 계약금액(수주시점) × 진행 비율(환산 없음).
    반환 (krw_by_q {q: 억원}, remaining_krw_after_freeze 억원, target_opm {q: opm}). target_opm 은 등급 있는 계약만으로 가중하고
    (sls._target_opm 과 같은 정의 — T6 D3 전에는 등급 없는 계약을 OPM 0 으로 셌다), share_out(dict) 을 주면 등급 있는 비중 {q: 0~1} 을 채운다."""
    fdate = q_end_date(freeze)
    tab = sls.get("cohort_opm_table") or {}
    krw, remain, wsum, wopm = collections.defaultdict(float), 0.0, collections.defaultdict(float), collections.defaultdict(float)
    wgr = collections.defaultdict(float)
    for c in sls.get("contracts") or []:
        if not c.get("counted", True) or c.get("type") == "OTHER" or not c.get("schedule") or not _num(c.get("amt_krw_m")):
            continue
        try:
            signed = datetime.date.fromisoformat(c.get("signed") or c.get("start"))
        except (TypeError, ValueError):
            continue
        if signed > fdate:
            continue
        tot = sum(c["schedule"].values())
        if tot <= 0:
            continue
        for q, u in c["schedule"].items():
            share = u / tot
            v = c["amt_krw_m"] * share / UNIT_DIV
            krw[q] += v
            if q > freeze:
                remain += v
            wsum[q] += v
            if _num(tab.get(c.get("cohort"))):
                wgr[q] += v
                wopm[q] += v * tab[c["cohort"]]
    topm = {q: (wopm[q] / wgr[q]) for q in wgr if wgr[q] > 0}
    if share_out is not None:
        share_out.update({q: wgr[q] / wsum[q] for q in topm if wsum[q] > 0})
    return dict(krw), remain, topm


def strat_yard(stock, S, fq, ctx, origin):
    sls = ctx.sls(stock)
    if not sls or not sls.get("by_quarter"):
        return strat_trend(stock, S, fq, ctx, origin, reason="선표(assets/sls) 없음")
    la = S["last_actual"]
    freeze = la < (sls.get("origin") or la)
    rec = sls.get("reconcile") or {}
    seg_names = []
    for q in sorted(rec):
        for s in rec[q].get("segments") or []:
            if s not in seg_names:
                seg_names.append(s)
    # 부문 실적(3개월분, 백만원) — L3 가 정기보고서 부문표/기납품 차분으로 만든 값
    seg_act = {q: rec[q]["reported_segment_rev_m"] / UNIT_DIV for q in S["매출액"] if q in rec and _num(rec[q].get("reported_segment_rev_m"))}
    p = _plan()
    # 3개월 부문 매출이 음수인 분기(yards_cache 부문표 반기 누계 정정의 차분 — HJ重 2022Q4 −8,411억)는 실적 셀·기타 부문·소진 속도 창에서 뺀다.
    # 값을 고치지 않고 제외만 하며 driver.segment_actual_dropped 에 원값을 남긴다(원인은 sls/yards 레인).
    seg_neg = {q: r2(seg_act[q]) for q in sorted(seg_act) if seg_act[q] < 0}
    for q in seg_neg:
        del seg_act[q]
    if seg_neg:
        p["warnings"].append("조선 부문 매출 음수 분기 %d개 제외(부문표 누계 정정 차분 — sls.reconcile.reported_segment_rev_m; yards 레인 확인): %s"
                             % (len(seg_neg), ", ".join("%s %.0f억" % (q, v) for q, v in seg_neg.items())))
    for q in seg_act:
        if seg_act[q] > S["매출액"][q] * 1.001:
            p["warnings"].append("%s 조선 부문 매출(%.0f억) > 연결 매출(%.0f억) — 부문표/파서 문제(yards 레인 확인)" % (q, seg_act[q], S["매출액"][q]))
    other_act = {q: max(S["매출액"][q] - seg_act[q], 0.0) for q in seg_act}
    # 신규수주 매출(결정 ⓓ): forecast_panel base 시나리오의 new_order_revenue 를 매출조선·매출액에 포함. 보수/낙관은 scenarios 블록에만(합산 안 함).
    # 백테스트 동결(freeze)에서는 패널을 쓰지 않는다 — 패널(origin 2026Q2)은 동결 이후 정보라 누출이고, 동결 창(2025Q3~2026Q2)을 덮지도 않는다.
    # 패널 여부를 '기존' SLS 정의보다 먼저 정한다 — origin 이후 공시 수주의 처리는 NEW_ORDERS_POST_ORIGIN_MODE(라운드 7: net_panel 기본 | exclude_sls = T6 D1).
    mode = NEW_ORDERS_POST_ORIGIN_MODE
    if mode not in NEW_ORDERS_POST_ORIGIN_MODES:
        raise ValueError("NEW_ORDERS_POST_ORIGIN_MODE %r — 허용 %s" % (mode, NEW_ORDERS_POST_ORIGIN_MODES))
    no = None if freeze else _panel_new_orders(stock, ctx, fq)
    use_panel = bool(no and no["available"])
    # 폴백 회사의 패널 범위 밖 선종(한화오션 EP및특수선 → NAVAL)은 원장 창·상계 D 에서 뺀다 — 공시 일정(SLS)은 유지(2026-10-09 검증 수정)
    ex_types, unc_types = _scope_excluded_types(no) if use_panel else ((), ())
    # 라운드 7 ⓑ: 공시 체결 속도 대조(폴백 회사; FALLBACK_ONLY=False 면 전부) → 비율 < 0.5·체결 분기 ≥ 2 면 원장 체결 속도가 신규수주 입력(ledger_signing_rate)
    led_cc = _ledger_signing_crosscheck(sls, no, exclude_types=ex_types) if (use_panel and (no["fallback"] or not LEDGER_RATE_FALLBACK_ONLY)) else None
    if led_cc:
        no = _ledger_rate_new_orders(no, led_cc, fq, sls)
    lab = "원장 수준" if (use_panel and no["source_field"] == "ledger_signing_rate") else "패널"      # 상계 문구의 코호트 N 출처
    post = None
    post_frac, post_frac_by_sq = 1.0, {}
    share = {}
    if freeze:
        krw, remaining, topm = _sls_frozen(sls, la, share_out=share)
        sls_hist = {q: krw.get(q, 0.0) for q in seg_act}
        backlog = _yard_backlog_at(stock, la, seg_names)
        uncovered = max((backlog / UNIT_DIV - remaining), 0.0) if _num(backlog) else None
        sls_fwd = {q: krw.get(q, 0.0) for q in fq}
        src_note = "freeze %s 까지 체결 계약 재구성(계약금액 × 진행비율, 환산 없음)" % la
    else:
        bq = sls["by_quarter"]
        sls_hist = {q: (rec[q].get("sls_krw_m") or 0.0) / UNIT_DIV for q in seg_act}
        rs = sls.get("reconcile_summary") or {}
        rep_bl, rem = rs.get("reported_marine_backlog_krw_m"), rs.get("remaining_marine_krw_m_at_origin")
        uncovered = max((rep_bl - rem) / UNIT_DIV, 0.0) if (_num(rep_bl) and _num(rem)) else None
        hr_txt = "헤지 %.0f%% 적용" % (((bq.get(fq[0]) or {}).get("hedge_ratio") or 0.7) * 100)
        post = _sls_post_origin(sls, fq, exclude_types=ex_types)
        if use_panel and post["n"] and mode == "net_panel":
            # 라운드 7 ⓐ net_panel: 공시 계약은 SLS 일정(계약별 기간·헤지환율)으로 전부 유지, 패널(또는 원장 수준) 신규수주에서 체결 분기별 공시 금액을 상계.
            no = _net_panel_new_orders(no, post, fq, sls.get("origin"), uncertain_types=unc_types)
            post_frac, post_frac_by_sq = 0.0, {sq: 0.0 for sq in post["by_sign_q"]}
            sls_fwd = {q: post["existing"][q] + post["post"][q] for q in fq}
            src_note = ("sls.by_quarter.marine_hedged_krw_m(%s; origin %s 이후 체결 %d건 SLS 유지 — %s 신규수주와 체결 분기별 상계(net_panel)%s)"
                        % (hr_txt, sls.get("origin"), post["n"], lab,
                           (", 패널 범위 밖 %s %s억은 상계 안 함" % ("·".join(ex_types), format(round(sum(post["by_sign_q_excluded"].values())), ",d")))
                           if post["by_sign_q_excluded"] else ""))
        elif use_panel and post["n"]:
            # T6 D1(exclude_sls): origin 이후 체결 계약은 패널 신규(origin 이후 수주의 매출)에 포함된 것으로 본다 → '기존' 은 origin 분기말까지 체결분만.
            # 백테스트 _sls_frozen(체결일 ≤ 동결 분기말)과 같은 규칙. 패널이 없으면 공시 수주가 유일한 신규 정보라 그대로 둔다.
            # 단 패널이 담는 몫은 체결 분기별 패널 신규수주 규모까지만(post_frac) — 패널이 공시 체결 속도보다 작은 한화오션·HJ 에서 실제 수주가 사라지지 않게.
            post_frac, post_frac_by_sq = _post_origin_panel_fraction(post, no)
            sls_fwd = {q: post["existing"][q] + post["post"][q] * (1.0 - post_frac) for q in fq}
            src_note = ("sls.by_quarter.marine_hedged_krw_m_signed_by_origin(%s; origin %s 이후 체결 %d건 %s — %s 신규에 포함)"
                        % (hr_txt, sls.get("origin"), post["n"], "제외" if post_frac >= 1.0 else "중 %s 신규수주 규모만큼(%.0f%%) 제외" % (lab, post_frac * 100), lab))
        else:
            sls_fwd = {q: ((bq.get(q) or {}).get("marine_hedged_krw_m") or 0.0) / UNIT_DIV for q in fq}
            src_note = "sls.by_quarter.marine_hedged_krw_m(%s)" % hr_txt
        tq = sls.get("target_opm") or {}
        topm = {q: t.get("opm") for q, t in tq.items() if _num(t.get("opm"))}
        share = {q: (tq[q]["graded_share"] if _num(tq[q].get("graded_share")) else 1.0) for q in topm}
    ks = last_n(seg_act, 4)
    if len(ks) < 2 or uncovered is None:
        return strat_trend(stock, S, fq, ctx, origin, reason="부문 매출 실적 %d분기·잔고 %s" % (len(ks), "없음" if uncovered is None else "있음"))
    runoff_rate = med([max(seg_act[q] - sls_hist.get(q, 0.0), 0.0) for q in ks]) or 0.0
    if uncovered <= 0:
        p["warnings"].append("원장 잔여가 공시 잔고를 넘음(커버리지 > 1) → 원장 밖 소진분 0 (sls warnings 참고)")
    remaining_u, seg_est, exist_est = uncovered, {}, {}
    for q in fq:
        r = min(runoff_rate, remaining_u)
        remaining_u -= r
        exist_est[q] = sls_fwd[q] + r
        seg_est[q] = (exist_est[q], "SLS 해양 원화 %.0f억(%s) + 원장 밖 잔고 소진 %.0f억(최근 %d분기 '부문매출−SLS' 중위 %.0f억/분기, 잔여 %.0f억)"
                      % (sls_fwd[q], src_note, r, len(ks), runoff_rate, remaining_u))
    new_base = {}
    if use_panel:
        new_base = no["by_scenario"][PANEL_BASE]
        for q in fq:
            n = new_base.get(q, 0.0)
            seg_est[q] = (exist_est[q] + n, seg_est[q][1] + " + 신규수주 매출 %.0f억(%s)" % (n, no["basis"]))
    # T6 D1: 기존에서 뺀 origin 이후 공시 수주 — 건수·금액·추정 창 SLS 를 수치로(basis·경고·driver)
    post_excl = None
    np_ = (no or {}).get("net_panel") or {}
    if new_base and post and post["n"]:
        fy_ex = _fy_sum({q: post["post"][q] * post_frac for q in fq}, fq)
        fy_keep = _fy_sum({q: post["post"][q] * (1.0 - post_frac) for q in fq}, fq)
        fy_new = _fy_sum(new_base, fq)
        cmp_q = [(q, v, no["new_orders_by_q"].get(q)) for q, v in post["by_sign_q"].items() if q in no["new_orders_by_q"]]
        dfn = no.get("definition") or {}
        unc = ("패널 new_order_revenue 정의 불확실 — order_basis=%s(경험적 순보충 분위의 통계 흐름, 공시 계약을 개별 반영하지 않음) · "
               "new_order_arrival=%s · progress_curve=%s%s%s. 공시 수주의 인식 시점·진행률(선형, 체결 분기부터)은 패널 가정과 다르다(calibrated=false) — %s"
               % (dfn.get("order_basis") or "—", dfn.get("new_order_arrival") or "—", dfn.get("progress_curve") or "—",
                  ("; 패널 기존잔고는 origin 이후 공시 %d건을 제외(industry_axes.schedule_exclusions.not_known_at_origin)" % no["not_known_at_origin"])
                  if no.get("not_known_at_origin") is not None else "",
                  "".join("; %s 공시 수주 %s억 vs %s base 신규수주 %s억(%.0f%%)" % (q, format(round(v), ",d"), lab, format(round(pn), ",d"), v / pn * 100)
                          for q, v, pn in cmp_q if pn),
                  ("FY 유지 SLS(공시) vs %s(상계 후): %s" % ("매출조선신규(원장 수준)" if lab == "원장 수준" else "패널 base 신규 매출",
                                                        " · ".join("%s %s억 vs %s억" % (y, format(round(fy_keep[y]), ",d"), format(round(fy_new.get(y, 0.0)), ",d")) for y in fy_keep)))
                  if mode == "net_panel" else
                  ("FY 제외 SLS vs 패널 base 신규 매출: %s" % " · ".join("%s %s억 vs %s억" % (y, format(round(fy_ex[y]), ",d"), format(round(fy_new.get(y, 0.0)), ",d")) for y in fy_ex))))
        if mode == "net_panel":
            removed = np_.get("panel_revenue_removed_by_fy") or {}
            note = ("origin 이후 공시 수주 %d건 %s억은 SLS 일정으로 전부 유지, %s 신규수주에서 체결 분기별 상계(%s) — %s −%s억(%s)"
                    % (post["n"], format(round(post["amt"]), ",d"), lab, np_.get("text") or "—",
                       "매출조선신규(원장 수준)" if lab == "원장 수준" else "패널 base 신규 매출", format(round(sum(removed.values())), ",d"),
                       " · ".join("%s %s억" % (y, format(round(v), ",d")) for y, v in removed.items())))
        else:
            note = (("origin 이후 공시 수주 %d건 %s억은 %s 신규에 포함된 것으로 보아 기존 SLS 에서 제외" % (post["n"], format(round(post["amt"]), ",d"), lab)
                     if post_frac >= 1.0 else
                     "origin 이후 공시 수주 %d건 %s억 중 %s 신규수주 규모(체결 분기별 한도)만큼 %.0f%% 만 기존 SLS 에서 제외 — 나머지 %.0f%% 는 선표에 유지(%s이 공시 체결 속도보다 작음: %s)"
                     % (post["n"], format(round(post["amt"]), ",d"), lab, post_frac * 100, (1 - post_frac) * 100, lab,
                        " · ".join("%s %s %s억 vs 공시 %s억" % (sq, lab, format(round(no["new_orders_by_q"].get(sq, 0.0)), ",d"), format(round(a), ",d"))
                                   for sq, a in post["by_sign_q"].items())))
                    + " — 추정 창 SLS −%s억(%s)" % (format(round(sum(fy_ex.values())), ",d"), " · ".join("%s %s억" % (y, format(round(v), ",d")) for y, v in fy_ex.items())))
        post_excl = {"n": post["n"], "amt_krw_eok": r2(post["amt"]), "by_sign_quarter": {q: r2(v) for q, v in post["by_sign_q"].items()}, "mode": mode,
                     "by_sign_quarter_out_of_scope": {q: r2(v) for q, v in post["by_sign_q_excluded"].items()}, "scope_excluded_types": post["scope_excluded_types"],
                     "included_fraction": r4(post_frac), "included_fraction_by_sign_quarter": {q: r4(v) for q, v in post_frac_by_sq.items()},
                     "sls_excluded_by_fy": {y: r2(v) for y, v in fy_ex.items()}, "sls_kept_by_fy": {y: r2(v) for y, v in fy_keep.items()},
                     "panel_new_revenue_by_fy": {y: r2(v) for y, v in fy_new.items()},
                     "sls_excluded_by_q": {q: r2(post["post"][q] * post_frac) for q in fq}, "rcps": post["rcps"], "source": post["source"],
                     "netted_by_sign_quarter": np_.get("netted_by_sign_quarter"), "panel_revenue_removed_by_fy": np_.get("panel_revenue_removed_by_fy"),
                     "undated_not_netted_eok": np_.get("undated_not_netted_eok"), "kernel_mode": no.get("kernel_mode"),
                     "definition_uncertainty": unc, "note": note}
        for q in fq:
            seg_est[q] = (seg_est[q][0], seg_est[q][1] + (" · origin 이후 공시 수주 SLS %.0f억 유지(%s 신규수주 체결 분기별 상계, net_panel)" % (post["post"][q], lab) if mode == "net_panel" else
                                                          " · origin 이후 공시 수주 SLS %.0f억 제외(%s 신규에 포함으로 봄)" % (post["post"][q] * post_frac, lab) if post_frac >= 1.0 else
                                                          " · origin 이후 공시 수주 SLS %.0f억 중 %.0f억 제외(%s 신규수주 규모만큼, %.0f%%)" % (post["post"][q], post["post"][q] * post_frac, lab, post_frac * 100)))
    r3 = _sls_r3_info(sls)
    ledger = bool(new_base and no.get("ledger_rate"))
    fb_note = ""
    if ledger:
        lr = no["ledger_rate"]
        fb_note = ("폴백 사슬 %s(저신뢰): 패널 covered_scope 신규수주(분기 %s억)가 공시 체결 속도(분기 평균 %s억)의 %.0f%% < %.0f%% · 원장 창 %d분기(%s~%s) → "
                   "원장 체결 분기 min/median/max %s/%s/%s억을 보수/base/낙관 분기 신규수주로, 인식 %s%s"
                   % (" → ".join(NEW_ORDERS_SOURCE_CHAIN), format(round(lr["panel_fallback_base_per_q_eok"] or 0.0), ",d"), format(round(led_cc["ledger_mean_per_q_eok"]), ",d"),
                      lr["panel_to_ledger_ratio"] * 100, LEDGER_RATE_MAX_PANEL_RATIO * 100, lr["n_quarters_used"], lr["window_quarters"][0], lr["window_quarters"][-1],
                      format(round(lr["levels"]["conservative"]), ",d"), format(round(lr["levels"][PANEL_BASE]), ",d"), format(round(lr["levels"]["optimistic"]), ",d"),
                      "패널 역산 커널(%s)" % lr["panel_field"] if lr["curve"] == "panel_kernel" else "선형 T=%s분기" % lr["alt_linear_T"],
                      ("; 선형 대안(T=%d분기, 원장 계약 일정 길이 중위) base FY 매출 %s%s"
                       % (lr["alt_linear_T"], " · ".join("%s %s억" % (y, format(round(v), ",d")) for y, v in lr["alt_linear_FY_rev"].items()),
                          ("(공시 상계 후 — 행과 같은 축; 상계 전 %s)" % " · ".join("%s %s억" % (y, format(round(v), ",d")) for y, v in lr["alt_linear_FY_rev_pre_netting"].items()))
                          if lr["alt_linear_FY_rev"] != lr["alt_linear_FY_rev_pre_netting"] else ""))
                      if lr.get("alt_linear_FY_rev") else ""))
    elif new_base and no["fallback"]:
        cv = no.get("coverage") or {}
        ratio = (led_cc or {}).get("panel_to_ledger_ratio")
        if ratio is None:
            cmp_txt = "공시 체결 속도와 대조 불가"
        else:
            verdict = ("신규 매출 과소 가능 — 낙관 시나리오가 더 가깝다" if ratio < 0.5 else
                       "대체로 같은 규모" if ratio <= 1.5 else
                       "원장은 대형 단일 계약만 잡은 하한이라 초과만으로 과대 단정은 못 하나, 패널은 FX 취소를 못 가른 순보충 기반이라 상향 편향 가능 — 보수 시나리오 병행 확인")
            cmp_txt = ("패널 신규수주는 공시 체결 속도 대비 %.0f%% 수준(분기 평균 %s억 vs 공시 체결 %s억 — %s)"
                       % (ratio * 100, format(round(led_cc["panel_base_new_orders_mean_per_q_eok"]), ",d"), format(round(led_cc["ledger_mean_per_q_eok"]), ",d"), verdict))
        fb_note = ("폴백(저신뢰): 패널이 전범위 new_order_revenue 를 비웠다(%s) → 같은 엔진·같은 R1 인식·같은 시나리오 정의의 covered_scope_new_revenue 사용. "
                   "모델 대상 부문 %s%s만 덮고%s, %s"
                   % (", ".join(no["reason_codes"]) or "-", "·".join(cv.get("modeled_segments") or []) or "—",
                      (" (제외 %s)" % "·".join(cv["excluded_segments"])) if cv.get("excluded_segments") else "",
                      (" 제외 부문(%s)의 신규분은 반영되지 않는다" % "·".join(cv["excluded_segments"])) if cv.get("excluded_segments") else "",
                      cmp_txt))
    # 기타 부문(총매출 − 조선): 부문표 차분 잡음(반기 누계 정정 등)이 커서 추세 대신 최근 4분기 중위 유지
    oth_med = med([other_act[q] for q in ks]) or 0.0
    oth_rev = {q: oth_med for q in fq}
    oth_basis = {q: "기타 부문(연결 − 조선 부문) 최근 %d분기 중위 %.0f억 유지" % (len(ks), oth_med) for q in fq}
    # OPM: 코호트 타겟 + 회사 캘리브레이션(최근 4분기 실측 OPM − 타겟 중위). 부문 OP 미공시 → 두 부문 같은 OPM.
    opm_act = opm_series(S["매출액"], S["영업이익"])
    # T6 D3: 코호트 타겟은 '등급 있는 계약' 만으로 가중된다(sls._target_opm). 등급 없는 매출 비중(1 − graded_share)은 최근 4분기 실측 OPM
    # 중위로 채워 타겟 경로를 만든다 — 등급 비중이 바뀌는 만큼만 경로가 움직이고, 그 밖의 값은 그대로(가중 보완만).
    ka = last_n(opm_act, 4)
    opm_med4 = med([opm_act[q] for q in ka])
    fill = opm_med4 if opm_med4 is not None else 0.0
    teff = {q: share.get(q, 1.0) * t + (1.0 - share.get(q, 1.0)) * fill for q, t in topm.items()}
    diffs = [opm_act[q] - teff[q] for q in ka if q in teff]
    shift = med(diffs) if diffs else None
    if shift is None:
        shift = 0.0
        p["warnings"].append("SLS 타겟 OPM 과 겹치는 실측 분기 없음 → 캘리브레이션 0")
    last_q = max(teff) if teff else None
    opm_path, tpath = {}, {}
    for q in fq:
        tq_ = q if q in teff else last_q
        t = teff[tq_] if tq_ else 0.0
        tpath[q] = t
        opm_path[q] = clip(t + shift, *OPM_CLIP)
    # 코호트 경로 소멸 감지: 원 타겟(등급 있는 계약만)이 sls 전 분기 같은 값(또는 없음)이면 코호트가 경로를 만들지 못한다 → OPM 은 사실상
    # 실측 중위 고정이고, 남는 움직임은 등급 없는 비중 채움에서만 나온다(삼성重 reference_anchor 2022Q1~2030Q3 전부 15%)
    no_path = len({round(v, 4) for v in topm.values()}) <= 1
    path_txt = ("코호트 경로 없음 → 실측 중위 고정(원 타겟 %s; 경로 변화는 등급 없는 비중의 실측 중위 %.1f%% 채움에서만, 추정 구간 타겟 %.2f%%→%.2f%%)"
                % (("전 분기 %.1f%% 상수(%s)" % (next(iter(topm.values())) * 100, r3["cohort_text"])) if topm else "없음",
                   fill * 100, tpath[fq[0]] * 100, tpath[fq[-1]] * 100)) if no_path else ""
    for q in fq:
        g = share.get(q if q in teff else last_q, 1.0) if teff else 1.0
        p["opm"][q] = (opm_path[q], "SLS 코호트 타겟 %.1f%%(%s; 등급 비중 %.0f%% × 코호트 %.1f%% + 등급없음 %.0f%% × 최근 %d분기 실측 OPM 중위 %.1f%%) "
                                    "+ 회사 캘리브레이션 %+.1f%%p(최근 %d분기 실측−타겟 중위)%s%s"
                       % (tpath[q] * 100, r3["cohort_text"], g * 100, (topm.get(q if q in topm else last_q) or 0.0) * 100, (1 - g) * 100, len(ka), fill * 100,
                          shift * 100, len(diffs), " — 신규수주 매출에도 같은 타겟" if new_base else "", (" — " + path_txt) if path_txt else ""))
    if path_txt:
        p["warnings"].append("OPM 경로: " + path_txt)
    rev = {}
    for q in fq:
        rev[q] = (seg_est[q][0] + oth_rev[q], "매출조선 + 매출기타")
    p["rev"] = rev
    rs = sls.get("reconcile_summary") or {}
    # T6 D10: 잔고 캡이 적용된 sls 에서는 1/backlog_coverage 가 캡 배율 그 자체 — '대안 배율' 로 보이면 이중 곱셈으로 오독된다 → null + 문구
    cov = rs.get("backlog_coverage_at_origin")
    capped = r3["backlog_cap_applied"] is True          # 정보 없음(구버전 sls)은 캡 미적용으로 본다 — 그때 1/coverage 는 진짜 대안 배율
    if post_excl and mode == "net_panel":
        ex_def = ("origin 분기말까지 체결 계약(sls signed_by_origin) + origin 이후 공시 수주 %d건 전부(SLS 일정) + 원장 밖 잔고 소진 — %s 신규수주는 체결 분기별 공시 금액을 상계(net_panel)"
                  % (post_excl["n"], lab))
        ex_rev = ("SLS 해양 원화(origin %s 분기말까지 체결분 + origin 이후 공시 수주 %d건 전부, SLS 일정) + 원장 밖 잔고 소진 + 기타 부문(신규수주 제외) — %s 신규수주는 체결 분기별 공시 상계(net_panel)"
                  % (sls.get("origin") or la, post_excl["n"], lab))
    elif post_excl and post_excl["included_fraction"] >= 1.0:
        ex_def = "origin 분기말까지 체결 계약(sls signed_by_origin) + 원장 밖 잔고 소진 — origin 이후 공시 수주 %d건은 %s 신규에 포함으로 보아 제외" % (post_excl["n"], lab)
        ex_rev = "SLS 해양 원화(origin %s 분기말까지 체결분 — origin 이후 공시 수주 %d건 제외, %s 신규에 포함으로 봄) + 원장 밖 잔고 소진 + 기타 부문(신규수주 제외)" % (sls.get("origin") or la, post_excl["n"], lab)
    elif post_excl:
        ex_def = ("origin 분기말까지 체결 계약(sls signed_by_origin) + 원장 밖 잔고 소진 + origin 이후 공시 수주 %d건 중 %s 신규수주 규모를 넘는 %.0f%%"
                  % (post_excl["n"], lab, (1 - post_excl["included_fraction"]) * 100))
        ex_rev = ("SLS 해양 원화(origin %s 분기말까지 체결분 — origin 이후 공시 수주 %d건 중 %.0f%% 제외(%s 신규수주 규모만큼), 나머지 선표 유지) + 원장 밖 잔고 소진 + 기타 부문(신규수주 제외)"
                  % (sls.get("origin") or la, post_excl["n"], post_excl["included_fraction"] * 100, lab))
    else:
        ex_def = "선표 전체(origin 이후 체결 공시 수주 없음) + 원장 밖 잔고 소진"
        ex_rev = "SLS 해양 원화(origin %s 분기말까지 체결분) + 원장 밖 잔고 소진 + 기타 부문(신규수주 제외)" % (sls.get("origin") or la)
    src_txt = ("ledger_signing_rate(공시 계약 원장 체결 속도 × forecast_panel 역산 커널 %s)" % (no or {}).get("panel_field")) if ledger else \
              ("forecast_panel %s %s" % (PANEL_BASE, (no or {}).get("source_field")))
    np_meta = {k: v for k, v in np_.items() if k != "warnings"} or None
    p["driver"] = {"type": "sls_marine_plus_uncovered_backlog_runoff", "sls_source": src_note,
                   "uncovered_backlog_at_origin": r2(uncovered), "runoff_per_q": r2(runoff_rate), "runoff_quarters_used": ks,
                   "reconcile_ratio": rs.get("median_ratio_4q"), "backlog_coverage_at_origin": cov,
                   "scale_alternatives": {"1/median_ratio_4q": r4(1 / rs["median_ratio_4q"]) if _num(rs.get("median_ratio_4q")) and rs["median_ratio_4q"] > 0 else None,
                                          "1/backlog_coverage": None if capped else (r4(1 / cov) if _num(cov) and cov > 0 else None)},
                   "scale_alternatives_note": ("1/backlog_coverage = null — sls 가 이미 1/coverage 캡(%s)을 적용했다(backlog_cap). 추가 배율 아님, 곱하지 말 것"
                                               % (("× %.4f" % (1 / cov)) if _num(cov) and cov > 0 else r3["cap_text"])) if capped
                                              else "표시만 — 모델은 어느 배율도 곱하지 않는다(공시 잔고 상한 소진 방식)",
                   "post_origin_excluded": post_excl,
                   "segment_actual_dropped": ({"quarters": sorted(seg_neg), "values_eok": seg_neg,
                                               "reason": "3개월 부문 매출 음수(sls.reconcile ← yards_cache 부문표 누계 정정 차분) → 실적 셀·소진 창 제외, 값 불변"} if seg_neg else None),
                   "target_path": {"cohort_raw": {q: r4(topm[q]) for q in fq if q in topm}, "graded_share": {q: r4(share[q]) for q in fq if q in share},
                                   "fill_opm_median_4q": r4(fill), "fill_quarters": ka, "target_effective": {q: r4(v) for q, v in tpath.items()},
                                   "cohort_path_absent": no_path,
                                   "basis": "타겟 = 등급 비중 × 코호트 타겟 + (1 − 등급 비중) × 최근 4분기 실측 OPM 중위(T6 D3)" + ((" — " + path_txt) if path_txt else "")},
                   "calibrated_shift": r4(shift), "lag_q": 0,
                   # 결정 ⓓ·ⓔ(2026-09-30): 신규수주 포함 여부·출처, sls R3 의 코호트 모드·잔고 캡(없으면 '정보 없음')
                   "new_orders_included": bool(new_base),
                   "new_orders": ({"source": "sls.contracts 체결 속도 × forecast_panel.json.gz 역산 커널" if ledger else "forecast_panel.json.gz",
                                   "scenario_in_rows": PANEL_BASE, "scenarios": list(PANEL_SCENARIOS), "calibrated": False,
                                   "panel_status": no["status"], "panel_reason_codes": no["reason_codes"], "panel_origin": no["panel_origin"],
                                   "covered_quarters": no["covered"], "uncovered_quarters_zero": no["uncovered"],
                                   "base_total_fq": r2(sum(new_base.values())),
                                   "panel_definition": no.get("definition") or {},
                                   "existing_definition": ex_def,
                                   "source_field": no["source_field"], "panel_field": no["panel_field"], "source_chain": no["source_chain"], "fallback": no["fallback"],
                                   "confidence": "low" if no["fallback"] else "panel_default",
                                   "post_origin_mode": mode, "kernel_mode": no.get("kernel_mode"), "ledger_rate": no.get("ledger_rate"), "net_panel": np_meta,
                                   "panel_scope": no.get("coverage"), "ledger_crosscheck": led_cc, "fallback_note": fb_note or None,
                                   "note": "%s 는 미보정 book-value proxy(value_semantics) — 보수/낙관은 scenarios 블록에만, 행에는 base 만%s"
                                           % ("원장 체결 속도 × 패널 커널" if ledger else "패널 %s" % no["source_field"], (" · " + fb_note) if fb_note else "")}
                                  if new_base else
                                  {"source": "forecast_panel.json.gz", "calibrated": False, "panel_status": (no or {}).get("status"),
                                   "panel_reason_codes": (no or {}).get("reason_codes"),
                                   "note": ("백테스트 동결 — 패널(동결 이후 정보) 미사용" if freeze else (no or {}).get("note") or "패널 없음") + " → 잔고 소진분만"}),
                   "sls_cohort_mode": r3["cohort_mode"], "backlog_cap_applied": r3["backlog_cap_applied"], "backlog_cap_raw": r3["backlog_cap_raw"],
                   "target_opm_alt_median": r3["target_opm_alt_median"],
                   "basis": "공시 해양 잔고(%s억) 를 상한으로 원장 밖 잔고를 최근 속도로 소진 — 화해 배율(1/ratio) 곱셈은 원장 커버리지 상승을 성장으로 오독하므로 쓰지 않음 · 신규수주: %s · %s · %s"
                            % (format(round((rs.get("reported_marine_backlog_krw_m") or 0) / UNIT_DIV), ",d"),
                               ("%s 포함(미보정)%s%s" % (src_txt, ("; " + fb_note) if fb_note else "", ("; " + post_excl["note"]) if post_excl else "")) if new_base else ("미포함(%s)" % ("백테스트 동결" if freeze else (no or {}).get("note") or "패널 없음")),
                               r3["cap_text"], r3["cohort_text"])}
    seg_label = "조선·해양(%s)" % "·".join(seg_names) if seg_names else "조선·해양"
    seg_rows = {"매출조선": {}, "OP조선": {}, "매출기타": {}, "OP기타": {}}
    if new_base:
        seg_rows = {"매출조선": {}, "매출조선신규": {}, "OP조선": {}, "OP조선신규": {}, "매출기타": {}, "OP기타": {}}
    for q in seg_act:
        seg_rows["매출조선"][q] = act(seg_act[q], "sls.reconcile.reported_segment_rev_m ← yards_cache 부문표(3개월분)")
        seg_rows["매출기타"][q] = act(other_act[q], "연결 매출 − 조선 부문(파생)")
    for q in fq:
        seg_rows["매출조선"][q] = est(seg_est[q][0], seg_est[q][1])
        seg_rows["매출기타"][q] = est(oth_rev[q], oth_basis[q])
        seg_rows["OP조선"][q] = est(seg_est[q][0] * opm_path[q], "매출조선 × 타겟 OPM(부문 OP 미공시 → 회사 OPM 적용%s)" % ("; 신규수주분 포함" if new_base else ""))
        seg_rows["OP기타"][q] = est(oth_rev[q] * opm_path[q], "매출기타 × 회사 OPM(부문 OP 미공시)")
        if new_base:
            seg_rows["매출조선신규"][q] = est(new_base.get(q, 0.0), "%s — 매출조선에 포함(합산 금지)" % no["basis"])
            seg_rows["OP조선신규"][q] = est(new_base.get(q, 0.0) * opm_path[q], "매출조선신규 × 타겟 OPM(신규분에도 같은 타겟) — OP조선에 포함")
    if new_base:
        # origin 이 속한 회계연도의 실적 분기는 정의상 0(origin 이후 수주분) — FY 합계가 'partial' 로 비지 않게 채운다
        for q in S["매출액"]:
            if q_year(q) == q_year(la) and q <= la:
                # T6 D8: fin 값이 아니므로 actual 이 아니다(actual = fin 그대로 규약) → estimate + '정의상 0'
                seg_rows["매출조선신규"][q] = est(0.0, "정의상 0 — origin %s 이전 실적 분기, origin 이후 신규수주 매출(fin 값 아님)" % la)
                seg_rows["OP조선신규"][q] = est(0.0, "정의상 0 — origin %s 이전 실적 분기(fin 값 아님)" % la)
    p["segments"] = [
        {"key": "조선", "label": seg_label, "driver": p["driver"], "opm_path": {q: r4(v) for q, v in opm_path.items()}},
        {"key": "기타", "label": "기타 부문(총매출 − 조선)", "driver": {"type": "median_flat", "basis": "연결 매출 − 조선 부문 실적의 최근 4분기 중위 유지"},
         "opm_path": {q: r4(v) for q, v in opm_path.items()}},
    ]
    p["extra_rows"] = seg_rows
    if new_base:
        p["row_labels"] = {"매출조선신규": ("매출 %s 신규수주(%s — 매출조선에 포함)" % (seg_label, "원장 체결 속도(폴백)" if ledger else
                                                                           "forecast_panel base(공시 상계)" if mode == "net_panel" else "forecast_panel base"), "사업부", "억원"),
                           "OP조선신규": ("OP %s 신규수주(매출조선신규 × OPM — OP조선에 포함)" % seg_label, "사업부", "억원")}
        p["scenarios_new"] = no["by_scenario"]
        p["scenarios_meta"] = {"source": ("공시 계약 원장(sls.contracts) 체결 분기 min/median/max × forecast_panel 역산 커널(%s) (억원)" % no["panel_field"]) if ledger else
                                         "forecast_panel.json.gz scenarios.{conservative,base,optimistic}.quarterly[].%s (KRW_million → 억원 ÷100)%s"
                                         % (no["source_field"], " — 공시 수주 체결 분기별 상계 후(net_panel)" if (post_excl and mode == "net_panel") else ""),
                               "source_field": no["source_field"], "panel_field": no["panel_field"], "source_chain": no["source_chain"],
                               "fallback": no["fallback"], "confidence": "low" if no["fallback"] else "panel_default",
                               "post_origin_mode": mode, "kernel_mode": no.get("kernel_mode"), "ledger_rate": no.get("ledger_rate"), "net_panel": np_meta,
                               "fallback_note": fb_note or None, "panel_scope": no.get("coverage"), "ledger_crosscheck": led_cc,
                               "panel_status": no["status"], "panel_reason_codes": no["reason_codes"], "panel_origin": no["panel_origin"], "calibrated": False,
                               "in_rows": PANEL_BASE,
                               "existing_revenue": ex_rev,
                               "post_origin_excluded": post_excl}
    pm = _panel_module(stock, ctx, fq, included=bool(new_base), rev_key=(no or {}).get("source_field") or PANEL_REV_KEYS[0],
                       netted=bool(post_excl and mode == "net_panel"), panel_key=(no or {}).get("panel_field"))
    if pm:
        p["modules"].append(pm)
    if new_base:
        p["warnings"].append("추정 매출조선 = %s 기준 잔고 소진분 + %s 신규수주 매출(미보정 book-value proxy, status %s; FY합 %s억) — 보수/낙관은 scenarios 블록(합산 안 함)"
                             % (la, src_txt, no["status"], format(round(sum(new_base.values())), ",d")))
        if fb_note:
            p["warnings"].append("신규수주 " + fb_note)
        if ledger:
            p["warnings"].append("신규수주 ledger_signing_rate(저신뢰): " + no["ledger_rate"]["note"])
        if post_excl:
            p["warnings"].append(post_excl["note"] + " · " + post_excl["definition_uncertainty"])
        p["warnings"].extend(np_.get("warnings") or [])
    elif freeze:
        p["warnings"].append("백테스트 동결 — 신규수주 매출 미포함(패널은 동결 이후 정보)")
    else:
        p["warnings"].append("추정 매출은 %s 기준 잔고 소진분만 — 신규수주 매출 미포함(%s; 2028 감소는 이 한계). forecast_panel 모듈 참고"
                             % (la, (no or {}).get("note") or "패널 없음"))
        if post and post["n"]:
            p["warnings"].append("패널 신규 없음 → origin 이후 공시 수주 %d건 %s억은 선표(SLS)에 그대로 둠(유일한 신규수주 정보 — 제외하지 않음)"
                                 % (post["n"], format(round(post["amt"]), ",d")))
    if r3["backlog_cap_applied"]:
        p["warnings"].append("SLS %s — 원장 잔여가 공시 잔고를 넘어 R3 가 줄인 값(sls.backlog_cap_applied)" % r3["cap_text"])
    return p


def strat_holding(stock, S, fq, ctx, origin):
    core = ctx.model(HOLDING_CORE, origin)
    if not core or core.get("status") == "no_fin" or not core.get("rows"):
        return strat_trend(stock, S, fq, ctx, origin, reason="자회사 %s 모델 없음" % HOLDING_CORE)
    rm = {r["key"]: r for r in core["rows"]}
    crev, cop = merged_rev(rm["매출액"]), merged_rev(rm["영업이익"])
    merge_q = MERGERS.get("010620", (None, "2025Q4"))[1]
    common = [q for q in last_n(S["매출액"], 4) if q in crev and crev[q]]
    post = [q for q in common if q >= merge_q]
    use = post if len(post) >= 2 else common
    if len(use) < 2:
        return strat_trend(stock, S, fq, ctx, origin, reason="자회사와 겹치는 실적 분기 부족")
    if not all(q in crev and crev[q] for q in fq):
        return strat_trend(stock, S, fq, ctx, origin, reason="자회사 모델이 추정 구간을 다 덮지 못함")
    ratio = med([S["매출액"][q] / crev[q] for q in use])
    o_h, o_c = opm_series(S["매출액"], S["영업이익"]), opm_series(crev, cop)
    shift = med([o_h[q] - o_c[q] for q in use if q in o_h and q in o_c]) or 0.0
    p = _plan()
    for q in fq:
        if q not in crev:
            continue
        p["rev"][q] = (crev[q] * ratio, "HD현대重 모델 매출 %.0f억 × 연결/자회사 비율 %.3f(%s 실측 중위; 삼호·기타 자회사·내부거래 포함)" % (crev[q], ratio, "·".join(use)))
        c_opm = (cop.get(q) or 0.0) / crev[q] if crev[q] else 0.0
        v = clip(c_opm + shift, *OPM_CLIP)
        p["opm"][q] = (v, "자회사 OPM %.1f%% + 실측 차이 %+.1f%%p" % (c_opm * 100, shift * 100))
    core_drv = ((core.get("segments") or [{}])[0].get("driver") or {}) if core.get("segments") else {}
    p["driver"] = {"type": "subsidiary_yard_scaled", "core": HOLDING_CORE, "ratio_used": r4(ratio), "quarters_used": use, "opm_shift": r4(shift),
                   # 결정 ⓓ: 신규수주는 HD현대重 모델 매출(신규 포함) × 비율로 자동 반영 — 시나리오도 같은 비율로 옮긴다
                   "new_orders_included": bool(core_drv.get("new_orders_included")),
                   "new_orders": {"via": HOLDING_CORE, "note": "HD현대重(%s) 모델 매출(forecast_panel base 신규수주 %s) × 연결/자회사 비율 %.3f 로 자동 반영"
                                  % (HOLDING_CORE, "포함" if core_drv.get("new_orders_included") else "미포함", ratio)},
                   "basis": "종속 조선사 합산(비상장 삼호 포함) − 내부거래 를 실측 연결/HD현대重 비율 하나로 대신함(합병 후 분기만)"}
    core_sc = core.get("scenarios") or {}
    if core_sc.get(PANEL_BASE):
        new_core = {}
        for scn in PANEL_SCENARIOS:
            qd = (core_sc.get(scn) or {}).get("quarterly") or {}
            new_core[scn] = {q: ((qd.get(q) or {}).get("new_order_revenue") or 0.0) * ratio for q in fq}
        if any(new_core[PANEL_BASE].values()):
            p["scenarios_new"] = new_core
            p["scenarios_meta"] = {"source": "HD현대重(%s) 모델 scenarios 의 new_order_revenue × 연결/자회사 비율 %.3f" % (HOLDING_CORE, ratio),
                                   "calibrated": False, "in_rows": PANEL_BASE, "existing_revenue": "HD현대重 모델 매출(신규 제외) × 비율"}
    p["consolidation"] = {"method": "core_subsidiary_ratio", "subsidiaries": [
        {"stock": "329180", "name": "HD현대중공업", "stake": None, "from": "2021", "note": "2025Q4 HD현대미포 흡수합병"},
        {"stock": "010620", "name": "HD현대미포", "stake": None, "from": "2021", "to": "2025Q3", "note": "합병 소멸"},
        {"stock": None, "name": "HD현대삼호(비상장)", "stake": None, "note": "공시 fin 없음 → 비율에 포함"}]}
    pm = _panel_module(stock, ctx, fq)
    if pm:
        p["modules"].append(pm)
    return p


def _suppliers_weights(stock, ctx):
    """suppliers.json 의 고객 조선사 언급 → 비중(합 1). 없으면 {}."""
    co = next((c for c in ctx.suppliers.get("cos") or [] if c.get("stock") == stock), None)
    # 비중(ifrs8 매출비중 %)과 언급 횟수를 한 합에 섞지 않는다(2026-10-05 selfcheck): share 가 하나라도 적힌 회사는 share 만 쓰고
    # (0.0 도 '비중 0' 으로 유효), share 가 전혀 없으면 mentions(없으면 1) 로 정규화한다. 예전 `share or mentions or 1` 은 share 0.0 을
    # 거짓으로 보아 mentions 1 을 더해 백분율과 건수가 섞였다(현대힘스 009540 0.5765 = (55.21+1)/97.49).
    yards = [(YARD_ALIAS.get(y.get("yard"), y.get("yard")), y) for y in (co or {}).get("yards") or []]
    yards = [(code, y) for code, y in yards if code and re.fullmatch(r"\d{6}", code)]
    use_share = any(y.get("share") is not None for _, y in yards)
    w = collections.defaultdict(float)
    for code, y in yards:
        if use_share:
            w[code] += float(y.get("share") or 0.0)
        else:
            w[code] += float(y.get("mentions") or 1)
    tot = sum(w.values())
    return {k: v / tot for k, v in sorted(w.items())} if tot else {}


def _link_eligibility(stock, ctx):
    """고객 연동 후보 자격(라운드 7 L5, 2026-10-08): suppliers.json yards(_suppliers_weights 와 같은 필터)가 전부 basis=related 이고 Σshare < RELATED_SHARE_MIN(%)
    이면 격자에 들어가지 못한다(한화시스템 — 특수관계자 매출 0.03% 하나가 100% 가중치). ifrs8·contract·text(basis 없는 레거시 포함)가 하나라도 있거나
    Σrelated ≥ 문턱이면 통과. 가중치·후보 목록은 건드리지 않는다(yard 단위로 지우면 현대힘스·HD현대마린솔루션 가중치가 흔들려 격자 pick 이 바뀜).
    yards 없음(세진 레퍼런스 경로)도 통과. 반환 {eligible, rule, related_share_sum, bases, yards, reason} — yards 순서 유지(결정론)."""
    co = next((c for c in ctx.suppliers.get("cos") or [] if c.get("stock") == stock), None)
    yards = [(YARD_ALIAS.get(y.get("yard"), y.get("yard")), y) for y in (co or {}).get("yards") or []]
    yards = [(code, y) for code, y in yards if code and re.fullmatch(r"\d{6}", code)]
    bases = [y.get("basis") or "text" for _, y in yards]
    out = {"eligible": True, "rule": "related 만이면 Σshare ≥ %.1f%% · ifrs8/contract/text(basis 없음 포함) 있으면 통과 · 가중치는 바꾸지 않음" % RELATED_SHARE_MIN,
           "related_share_sum": None, "bases": sorted(set(bases)),
           "yards": [{"yard": code, "basis": y.get("basis"), "share": y.get("share")} for code, y in yards], "reason": None}
    if not yards:
        out["reason"] = "suppliers 연결 없음(레퍼런스 가중치 경로)"
    elif any(b in LINK_ELIGIBLE_BASES for b in bases):
        out["reason"] = "근거 등급 %s 있음 → 자격 통과" % "/".join(out["bases"])
    elif all(b == "related" for b in bases):
        s = sum(float(y.get("share") or 0.0) for _, y in yards)
        out["related_share_sum"] = r4(s)
        out["eligible"] = s >= RELATED_SHARE_MIN
        out["reason"] = ("특수관계자 매출(related) 비중 합 %.2f%% ≥ %.1f%% → 자격 통과" if out["eligible"] else
                         "고객 링크가 특수관계자 매출(related) 만이고 비중 합 %.2f%% < %.1f%% — 고객 연동 자격 미달") % (s, RELATED_SHARE_MIN)
    else:
        out["reason"] = "알 수 없는 근거 등급 %s → 자격 통과(규칙 밖)" % "/".join(out["bases"])
    return out


def _customer_weight_candidates(stock, ctx):
    """격자 탐색의 가중치 후보 [(key, weights(합 1), basis)] — suppliers.json 언급 비중 + (세진 그룹만) 레퍼런스 §4-1 계열. 순서 고정(결정론)."""
    out = []
    w = _suppliers_weights(stock, ctx)
    if w:
        out.append(("suppliers_mentions", w, "suppliers.json 정기보고서 언급 횟수 비중(근거 등급 text)"))
    if stock in SEJIN_GROUP:
        for key, ws, basis in SEJIN_REF_WEIGHT_FAMILY:
            tot = sum(ws.values())
            out.append((key, {k: v / tot for k, v in sorted(ws.items())}, basis + " 정규화"))
    return out


def _customer_weights(stock, ctx):
    """첫 가중치 후보 (weights, basis) — 세진은 레퍼런스 기본, 그 외는 suppliers.json. 없으면 ({}, basis)."""
    cands = _customer_weight_candidates(stock, ctx)
    if stock == SEJIN:
        ref = next((c for c in cands if c[0] == "ref_base"), None)
        return (ref[1], ref[2]) if ref else ({}, "레퍼런스 가중치 없음")
    return (cands[0][1], cands[0][2]) if cands else ({}, "suppliers.json 정기보고서 언급 횟수 비중(근거 등급 text)")


def _customer_index(weights, ctx, origin, lag=1, detail=None):
    """Σ w × 고객 매출(t−lag). 피합병 고객은 합병 분기부터 합병사 매출 × 체인링크 계수로 잇는다. 반환 ({q: v}, note, used).
    detail(dict) 을 주면 sources(고객 모델·last_actual·추정 시작)·mergers(체인링크 규칙) 을 채운다 — driver.merger_rule 의 출처."""
    revs, used, notes = {}, {}, []
    srcs = {}
    for code, w in weights.items():
        m = ctx.model(code, origin)
        if not m or m.get("status") == "no_fin" or not m.get("rows"):
            notes.append("%s 모델 없음(제외)" % code)
            continue
        revs[code] = merged_rev({r["key"]: r for r in m["rows"]}["매출액"])
        used[code] = w
        la = (m.get("periods") or {}).get("last_actual")
        srcs[code] = {"name": m.get("name"), "model": "assets/models/%s.json" % code, "last_actual": la,
                      "estimates_from": q_next(la) if la else None, "driver": m.get("driver_type"), "new_orders_included": m.get("new_orders_included")}
    if not used:
        if detail is not None:
            detail.update({"sources": srcs, "mergers": []})
        return {}, "; ".join(notes) or "고객 없음", {}
    tot = sum(used.values())
    used = {k: v / tot for k, v in used.items()}
    idx = collections.defaultdict(float)
    handled, mergers = set(), []
    for code, w in used.items():
        if code in MERGERS and MERGERS[code][0] in revs and origin is not None and origin < MERGERS[code][1]:
            # 동결(origin)이 합병 분기보다 앞이면 합병은 '동결 이후 정보' — 피합병사 동결 모델도 자기 추정을 내므로 체인링크 없이 두 회사를 각자
            # 비중대로 쓴다(누출 없음). 그렇지 않으면 합병사 동결 모델(자기 매출만 추정)에 k 를 곱해 지수가 합병 분기부터 꺼진다(OOS 창 안 구조 단절).
            acq, mq = MERGERS[code]
            for q, v in revs[code].items():
                idx[q] += w * v
            handled.add(code)
            notes.append("%s 합병(%s)은 동결 %s 이후 → 체인링크 없이 %s·%s 동결 모델 각자 추정" % (code, mq, origin, code, acq))
            mergers.append({"merged": code, "into": acq, "from": mq, "chain_k": None, "applied": False, "weight_merged": r4(w), "weight_acquirer": r4(used.get(acq, 0.0)),
                            "merged_last_actual": srcs[code]["last_actual"],
                            "rule": "동결 %s < 합병 %s: %s(%s)·%s(%s) 동결 모델 추정을 각자 비중(%.3f·%.3f)으로 합산(체인링크 미적용 — 합병은 동결 이후 정보)"
                                    % (origin, mq, code, srcs[code]["name"], acq, srcs[acq]["name"], w, used.get(acq, 0.0))})
            continue
        if code in MERGERS and MERGERS[code][0] in revs:
            acq, mq = MERGERS[code]
            pre = [q_add(mq, -k) for k in range(1, 5)]
            s_idx = sum(w * revs[code].get(q, 0.0) + used.get(acq, 0.0) * revs[acq].get(q, 0.0) for q in pre)
            s_sum = sum(revs[code].get(q, 0.0) + revs[acq].get(q, 0.0) for q in pre)
            k = s_idx / s_sum if s_sum else (w + used.get(acq, 0.0))
            for q in revs[code]:
                if q < mq:
                    idx[q] += w * revs[code][q]
            for q in revs[acq]:
                if q >= mq:
                    idx[q] += k * revs[acq][q]
                elif acq not in handled:
                    idx[q] += used.get(acq, 0.0) * revs[acq][q]
            handled.add(acq)
            notes.append("%s 는 %s 부터 %s 매출 × 체인링크 %.3f(합병 전 4분기 비중)" % (code, mq, acq, k))
            mergers.append({"merged": code, "into": acq, "from": mq, "chain_k": r4(k), "weight_merged": r4(w), "weight_acquirer": r4(used.get(acq, 0.0)),
                            "merged_last_actual": srcs[code]["last_actual"],
                            "rule": "%s(%s) fin 은 %s 까지(%s %s 에 흡수합병, 이후 보고서 없음) → %s 부터 %s 비중 %.3f 은 %s(%s) 모델 매출 × 체인링크 k=%.3f 로 대체"
                                    "(k = 합병 전 4분기 [w·%s + w·%s 매출] ÷ 두 회사 매출 합). 미래 고객 매출은 %s 추정(kind estimate) 을 쓴다"
                                    % (code, srcs[code]["name"], srcs[code]["last_actual"], mq, acq, mq, code, w, acq, srcs[acq]["name"], k, code, acq,
                                       srcs[acq]["model"])})
        elif code not in handled:
            for q, v in revs[code].items():
                idx[q] += w * v
            handled.add(code)
    if detail is not None:
        detail.update({"sources": srcs, "mergers": mergers})
    shifted = {q_add(q, lag): v for q, v in idx.items()}
    return shifted, "; ".join(notes), used


# ── 고객 연동 격자 탐색(F2) ─────────────────────────────────

def _t_yoy(s):
    """전년동기 대비 증감률 {q: s_q/s_{q−4} − 1} (분모 > 0 인 분기만)."""
    return {q: s[q] / s[q_add(q, -4)] - 1 for q in s if q_add(q, -4) in s and s[q_add(q, -4)] > 0}


def _t_ma4(s):
    """4분기 이동합 {q: Σ_{k=0..3} s_{q−k}} (4개가 다 있는 분기만)."""
    return {q: sum(s[q_add(q, -k)] for k in range(4)) for q in s if all(q_add(q, -k) in s for k in range(4))}


def _transform(s, t):
    return dict(s) if t == "level" else (_t_yoy(s) if t == "yoy" else _t_ma4(s))


def _seasonal_share(y, years=3):
    """분기 계절비중 {1..4: share} — 4분기가 다 있는 최근 `years` 개 연도의 분기/연간 비중 평균(subQ r440~442 방식). 없으면 0.25 균등."""
    ys = sorted({q_year(q) for q in y}, reverse=True)
    rows = []
    for yr in ys:
        ks = ["%dQ%d" % (yr, k) for k in range(1, 5)]
        if all(k in y for k in ks) and sum(y[k] for k in ks) > 0:
            tot = sum(y[k] for k in ks)
            rows.append([y[k] / tot for k in ks])
        if len(rows) >= years:
            break
    if not rows:
        return {k: 0.25 for k in range(1, 5)}, "계절비중 — 4분기 완결 연도 없음 → 0.25 균등"
    share = {k + 1: sum(r[k] for r in rows) / len(rows) for k in range(4)}
    return share, "계절비중 — 최근 %d개 연도(%s) 분기/연간 비중 평균" % (len(rows), ", ".join(str(yy) for yy in ys[:len(rows)]))


def _r_crit_p05(n):
    """양측 5% 유의 상관 임계값(df=n−2). 표 밖(df>20)은 df 20 값으로 근사."""
    df = n - 2
    if df < 2:
        return None
    t = T_CRIT_P05.get(df) or T_CRIT_P05[20]
    return round(t / math.sqrt(df + t * t), 4)


def _n_eff(t, n):
    """유효 표본(라운드 7 L5): 4분기 이동합은 인접 점이 3분기를 공유하므로 n − 3, 수준·YoY 는 n."""
    return n - LINK_NEFF_PENALTY.get(t, 0)


def _link_grid(y_series, cands, ctx, origin, fq):
    """가중치 후보 × 시차 × 변환 × 창 격자에서 상관표를 만든다. 반환 (rows, per_cand) —
    rows: [{wkey, lag, transform, window, n, corr, coef, covers_fq, quarters}] (계산 가능한 조합만),
    per_cand: {wkey: {"idx0": 시차 0 지수, "note", "used", "detail"}}.
    coef 는 원점회귀 Σxy/Σx² — level·ma4 는 비례계수 b, yoy 는 β(고객지수 YoY → 자사 YoY)."""
    rows, per_cand = [], {}
    for wkey, w, wbasis in cands:
        det = {}
        idx0, note, used = _customer_index(w, ctx, origin, lag=0, detail=det)
        per_cand[wkey] = {"idx0": idx0, "note": note, "used": used, "detail": det, "basis": wbasis}
        if not used:
            continue
        for lag in LINK_LAGS:
            shifted = {q_add(q, lag): v for q, v in idx0.items()}
            for t in LINK_TRANSFORMS:
                X, Y = _transform(shifted, t), _transform(y_series, t)
                covers = all(q in X for q in fq)
                for win in LINK_WINDOWS:
                    qs = [q for q in last_n(Y, win) if q in X and (t == "yoy" or X[q] > 0)]
                    n_eff = _n_eff(t, len(qs))
                    if n_eff < LINK_MIN_N:
                        continue
                    xs, ys = [X[q] for q in qs], [Y[q] for q in qs]
                    sxx = sum(x * x for x in xs)
                    coef = (sum(x * y for x, y in zip(xs, ys)) / sxx) if sxx > 0 else None
                    corr = pearson(xs, ys)
                    rows.append({"wkey": wkey, "lag": lag, "transform": t, "window": win, "n": len(qs), "n_eff": n_eff, "corr": r4(corr), "coef": r4(coef) if coef is not None else None,
                                 "covers_fq": covers, "quarters": qs})
    return rows, per_cand


def _grid_pick(rows, cand_order):
    """채택 순서: 상관 최대(4자리) → 짝 n 큼 → |시차−1| 작음 → 변환 수준>YoY>4Q합 → 가중치 후보 순 → 창 작음. 추정 구간을 다 덮는 조합만."""
    ok = [r for r in rows if r["covers_fq"] and r["corr"] is not None and r["coef"] is not None]
    if not ok:
        return None
    rank = {k: i for i, k in enumerate(cand_order)}
    ok.sort(key=lambda r: (-r["corr"], -r["n"], abs(r["lag"] - 1), LINK_TRANSFORMS.index(r["transform"]), rank.get(r["wkey"], 99), r["window"]))
    return ok[0]


def _grid_summary(rows, best, cands):
    """driver 에 남길 후보 상관표 — 전 조합 표(compact) + 상위 12 + 변환별·가중치별 최대."""
    def _short(r):
        return {"wkey": r["wkey"], "lag_q": r["lag"], "transform": r["transform"], "window_q": r["window"], "n": r["n"], "n_eff": r.get("n_eff"), "corr": r["corr"], "coef": r["coef"], "covers_fq": r["covers_fq"]}
    ranked = sorted([r for r in rows if r["corr"] is not None], key=lambda r: (-r["corr"], -r["n"], abs(r["lag"] - 1)))
    by_t, by_w = {}, {}
    for r in ranked:
        by_t.setdefault(r["transform"], _short(r))
        by_w.setdefault(r["wkey"], _short(r))
    return {"lags": list(LINK_LAGS), "windows": list(LINK_WINDOWS), "transforms": list(LINK_TRANSFORMS),
            "weight_candidates": {k: {"weights": r4_weights(w), "basis": b} for k, w, b in cands},
            "n_candidates": len(rows), "n_with_corr": len(ranked),
            "selection": "상관 최대(4자리) → n 큼 → |시차−1| 작음 → 수준>YoY>4Q합 → 가중치 후보 순 → 창 작음; 추정 구간을 다 덮는 조합만",
            "top": [_short(r) for r in ranked[:12]], "best_by_transform": by_t, "best_by_weights": by_w,
            "table": {"%s|lag%d|%s|w%d" % (r["wkey"], r["lag"], r["transform"], r["window"]): [r["corr"], r["n"], r["coef"]] for r in rows},
            "overfit_note": "후보 %d개 중 최대 상관을 골랐다(다중비교 보정 없음) · 표본 %s분기 · 4분기 이동합은 평활로 상관이 부풀고 공통 추세를 잡기 쉽다 — 과적합 경고 · "
                            "4분기 이동합 유효 표본 n_eff = n − 3(채택 조합 %s)"
                            % (len(rows), ("%d" % best["n"]) if best else "8~19", ("%d" % best["n_eff"]) if best and best.get("n_eff") is not None else "—")}


def _link_significance(best):
    """단일 검정 5% 유의(df=n−2) + 유효 표본 n_eff(4Q합 n−3) 기준 임계도 기록(라운드 7 L5). 게이트(significant_p05_uncorrected)는 LINK_SIG_USE_NEFF 가 고른다."""
    n_eff = best.get("n_eff", _n_eff(best["transform"], best["n"]))
    rc, rc_eff = _r_crit_p05(best["n"]), _r_crit_p05(n_eff)
    corr = best["corr"]
    sig_raw = rc is not None and corr is not None and abs(corr) >= rc
    sig_eff = rc_eff is not None and corr is not None and abs(corr) >= rc_eff
    return {"r_crit_p05_two_sided": rc, "n_eff": n_eff, "r_crit_p05_neff": rc_eff, "significant_p05_neff": sig_eff,
            "significant_p05_uncorrected": sig_eff if LINK_SIG_USE_NEFF else sig_raw, "gate": "n_eff" if LINK_SIG_USE_NEFF else "n",
            "note": "단일 검정 기준 임계 r(df=n−2, 양측 5%) — 격자 후보 수만큼 보정하면 임계는 더 높다 · 4분기 이동합 유효 표본 n_eff=n−3 기준 임계는 r_crit_p05_neff(기록만, 게이트는 gate)"}


def _link_forecast(best, X, y_series, fq, share_info):
    """채택 조합으로 추정 구간 매출을 만든다. 반환 {q: (v, basis)}.
    level: y = b·X(t−lag) · yoy: y = y(t−4) × (1 + clip(β·X_yoy(t−lag))) · ma4: y = b·X_ma4(t−lag) × 계절비중(분기)."""
    t, lag, b, n, corr, win = best["transform"], best["lag"], best["coef"], best["n"], best["corr"], best["window"]
    tag = "격자 lag0~4×창8/12/19×수준·YoY·4Q합 중 최대 r=%.2f, n=%d, 창 %d" % (corr, n, win)
    out = {}
    if t == "level":
        for q in fq:
            out[q] = (b * X[q], "고객 매출 가중지수(t−%d) %.0f억 × 비례계수 %.4f(원점회귀; %s)" % (lag, X[q], b, tag))
        return out
    if t == "yoy":
        comb = dict(y_series)
        for q in fq:
            base = comb.get(q_add(q, -4))
            if base is None:
                continue
            g = clip(b * X[q], *GROWTH_CLIP)
            v = base * (1 + g)
            comb[q] = v
            out[q] = (v, "전년동기 %.0f억 × (1 + β %.3f × 고객지수 YoY(t−%d) %+.1f%% = %+.1f%%, 클립 −30~+50%%; %s)" % (base, b, lag, X[q] * 100, g * 100, tag))
        return out
    share, share_basis = share_info
    for q in fq:
        k = int(q[5])
        out[q] = (b * X[q] * share[k], "고객지수 4분기 이동합(t−%d) %.0f억 × 비례계수 %.4f × 계절비중 Q%d %.3f(%s; %s)" % (lag, X[q], b, k, share[k], share_basis, tag))
    return out


def _link_oos(y_series, cands, ctx, la, adopted=None):
    """고객 연동 OOS 선택(결정 ⓘ): 마지막 실적(la) 4분기 전에 동결하고, 동결 데이터만으로 (a) 연동 (b) 추세+계절성 을 만들어
    동결 이후 4분기 실측 매출과 WAPE 로 비교한다. 고객 지수는 동결 고객 모델(ctx.model(code, freeze)) 이다.
    T6 D5: (b) adopted(현재 채택 조합 — wkey·lag·transform·window)를 주면 **그 조합**을 동결 데이터로 재적합(비례계수·계절비중 다시 추정)해 시험하고,
    동결 시점에 격자를 다시 고른 결과는 link_at_freeze 에 참고로만 둔다(adopted 를 안 주면 예전처럼 재선택 조합을 시험).
    (a) 비교는 반올림 전 WAPE(wape_*_raw)로, 표시는 1자리. (c) 비교 불가(실적 부족·조합 재적합 불가·WAPE 계산 불가)면 adopted = "undetermined"
    — 채택은 유의성 조건만으로 하되 decision·note 에 남긴다.
    누출: fin·고객 모델·시세는 동결되지만 가중치 후보(suppliers.json 언급 비중)·선표 원장의 최신 금액·정정은 현재 지식이다(백테스트 frozen_inputs 와 같음).
    반환 {freeze, horizon, n, wape_link, wape_trend, wape_link_raw, wape_trend_raw, adopted(True|False|"undetermined"), decision, tested,
    link_tested, link_at_freeze, detail, rule, note}."""
    fz = q_add(la, -BACKTEST_H)
    fq_bt = [q_add(fz, i) for i in range(1, BACKTEST_H + 1)]
    y_frozen = {q: v for q, v in y_series.items() if q <= fz}
    actual = {q: y_series[q] for q in fq_bt if q in y_series}
    out = {"freeze": fz, "horizon": BACKTEST_H, "n": len(actual), "wape_link": None, "wape_trend": None, "wape_link_raw": None, "wape_trend_raw": None,
           "adopted": "undetermined", "decision": "undetermined", "tested": "adopted_combo" if adopted else "reselected_at_freeze",
           "link_tested": None, "link_at_freeze": None,
           "rule": "동결 %s 이후 %d분기 매출 WAPE(반올림 전): 연동 ≤ 추세 × %.2f 이면 채택, 아니면 추세+계절성 폴백(격자 다중비교 방어 — 통계 보정 대신). "
                   "시험 대상 = %s; 비교 불가면 undetermined(유의성만으로 채택)"
                   % (fz, BACKTEST_H, OOS_WORSE_TOL, "현재 채택 조합을 동결 데이터로 재적합" if adopted else "동결 시점 재선택 조합")}
    if len(y_frozen) < 8 or not actual:
        out["note"] = "동결 %s 이전 실적 %d분기(<8) 또는 이후 실측 %d분기 → OOS 비교 불가(undetermined), 유의성 조건만으로 채택" % (fz, len(y_frozen), len(actual))
        return out
    tr, _, _ = trend_seasonal(y_frozen, fq_bt)
    wt = wape_raw([(tr[q], actual[q]) for q in actual])
    out["wape_trend_raw"], out["wape_trend"] = r4(wt), (round(wt, 1) if wt is not None else None)
    rows, per_cand = _link_grid(y_frozen, cands, ctx, fz, fq_bt)

    def _pred(r):
        pc = per_cand[r["wkey"]]
        shifted = {q_add(q, r["lag"]): v for q, v in pc["idx0"].items()}
        X = _transform(shifted, r["transform"])
        share = _seasonal_share(y_frozen) if r["transform"] == "ma4" else None
        return _link_forecast(r, X, y_frozen, fq_bt, share)

    def _short(r, note):
        return {"wkey": r["wkey"], "lag_q": r["lag"], "transform": r["transform"], "window_q": r["window"], "n": r["n"],
                "corr": r["corr"], "coef": r["coef"], "significant_p05_uncorrected": _link_significance(r)["significant_p05_uncorrected"], "note": note}
    best = _grid_pick(rows, [c[0] for c in cands])
    pred_re = _pred(best) if best else {}
    if best:
        w_re = wape_raw([(pred_re[q][0], actual[q]) for q in actual if q in pred_re])
        out["link_at_freeze"] = dict(_short(best, "동결 데이터로 다시 고른 격자 최선 조합 — %s" % ("참고(판정은 현재 채택 조합)" if adopted else "이 조합으로 판정")),
                                     wape=(round(w_re, 1) if w_re is not None else None), wape_raw=r4(w_re))
    if adopted:
        hit = next((r for r in rows if (r["wkey"], r["lag"], r["transform"], r["window"]) == (adopted["wkey"], adopted["lag"], adopted["transform"], adopted["window"])
                    and r["covers_fq"] and r["coef"] is not None), None)
        tested, pred = hit, (_pred(hit) if hit else {})
        if hit:
            out["link_tested"] = _short(hit, "현재 채택 조합(%s·시차 %d·%s·창 %d)을 동결 %s 데이터로 재적합" % (hit["wkey"], hit["lag"], LINK_TRANSFORM_KO[hit["transform"]], hit["window"], fz))
    else:
        tested, pred = best, pred_re
        if best:
            out["link_tested"] = out["link_at_freeze"]
    out["detail"] = [{"q": q, "actual": r2(actual[q]), "link": r2(pred[q][0]) if q in pred else None,
                      "link_reselected": r2(pred_re[q][0]) if q in pred_re else None, "trend": r2(tr[q])} for q in actual]
    if tested is None:
        out["note"] = ("현재 채택 조합(%s·시차 %d·%s·창 %d)을 동결 데이터로 재적합할 수 없음(짝·고객 모델 부족)" % (adopted["wkey"], adopted["lag"], adopted["transform"], adopted["window"])
                       if adopted else "동결 시점 고객 연동 조합 없음(고객 모델·짝 부족)") + " → 연동 WAPE 없음, undetermined(유의성 조건만으로 채택)"
        return out
    wl = wape_raw([(pred[q][0], actual[q]) for q in actual if q in pred])
    out["wape_link_raw"], out["wape_link"] = r4(wl), (round(wl, 1) if wl is not None else None)
    if wl is not None and wt is not None:
        out["adopted"] = wl <= wt * OOS_WORSE_TOL
        out["decision"] = "adopted" if out["adopted"] else "rejected"
    else:
        out["note"] = "WAPE 계산 불가(실측 합 0 등) → undetermined(유의성 조건만으로 채택)"
    return out


def strat_supplier(stock, S, fq, ctx, origin):
    """기자재·엔진·강재: 고객 조선사 매출 가중지수 격자 탐색(시차·창·변환) 회귀. 세진은 별도 매출을 맞추고 _sejin_wrap 으로 연결을 재구성한다(폴백이어도)."""
    sejin = stock == SEJIN and bool(S.get("매출별도"))
    y_series = S["매출별도"] if sejin else S["매출액"]
    p = _supplier_link(stock, S, fq, ctx, origin, y_series)
    if sejin:
        opm, _ = _opm_hist(S)
        p = _sejin_wrap(p, S, fq, ctx, origin, clip(opm if opm is not None else 0.0, *OPM_CLIP))
    return p


def _supplier_link(stock, S, fq, ctx, origin, y_series):
    """고객 연동 격자 탐색: 가중치 후보(suppliers.json 언급 비중 · 세진 그룹은 레퍼런스 §4-1 계열도) × 시차 0~4 × 창 8/12/19 × 변환(수준·YoY·4Q합)
    에서 상관 최대 조합을 고르고 CORR_MIN 이상이면 채택, 미달이면 추세+계절성 폴백. 선택 경로·후보표·유의 임계·합병 규칙은 driver 에 남긴다."""
    cands = _customer_weight_candidates(stock, ctx)
    fb = lambda reason: strat_trend(stock, S, fq, ctx, origin, reason=reason, series=y_series if y_series is not S["매출액"] else None)
    if not cands:
        return fb("고객 조선사 연결 없음(suppliers.json)")
    # 후보 자격(라운드 7 L5, 2026-10-08): 통계 전에 사업 관계로 거른다 — related 만이고 Σshare < RELATED_SHARE_MIN 이면 격자·OOS 전 기각(가중치는 안 바꿈).
    elig = _link_eligibility(stock, ctx)
    if not elig["eligible"]:
        p = fb("고객 연동 자격 미달 — %s" % elig["reason"])
        oos_skip = {"adopted": False, "decision": "rejected", "wape_link": None, "wape_trend": None, "note": "자격 미달 → 격자·OOS 전 기각"}
        p["driver"]["customer_link_rejected"] = {"rejected_by": "eligibility", "eligibility": elig, "weights": r4_weights(cands[0][1]), "weights_key": cands[0][0],
                                                 "corr": None, "b": None, "n": None, "n_eff": None, "lag_q": None, "transform": None, "window_q": None,
                                                 "selection_oos": oos_skip, "grid": None, "significance": None}
        p["driver"]["selection_oos"] = oos_skip
        return p
    rows, per_cand = _link_grid(y_series, cands, ctx, origin, fq)
    cand_order = [c[0] for c in cands]
    if not rows:
        notes = "; ".join(v["note"] for v in per_cand.values() if v["note"])
        usable = [k for k, v in per_cand.items() if v["used"]]
        if not usable:
            return fb("고객 모델 없음(%s)" % (notes or "후보 전부 모델 없음"))
        return fb("고객 지수와 겹치는 실적 분기 <%d %s" % (LINK_MIN_N, notes))
    best = _grid_pick(rows, cand_order)
    if best is None:
        notes = "; ".join(v["note"] for v in per_cand.values() if v["note"])
        if not any(r["corr"] is not None for r in rows):
            return fb("고객 연동 상관 계산 불가(자사 매출 또는 고객지수 분산 0; %s)" % (notes or "후보 %d" % len(rows)))
        return fb("고객 지수가 추정 구간을 다 덮지 못함(%s)" % notes)
    grid = _grid_summary(rows, best, cands)
    pc = per_cand[best["wkey"]]
    used, note, det = pc["used"], pc["note"], pc["detail"]
    rejected_base = {"weights": r4_weights(used), "weights_key": best["wkey"], "corr": best["corr"], "b": best["coef"], "n": best["n"], "n_eff": best["n_eff"],
                     "lag_q": best["lag"], "transform": best["transform"], "window_q": best["window"], "eligibility": elig}
    # 채택 조건(2026-09-30 오너 결정): 상관 ≥ CORR_MIN 만으로는 격자 45~180 후보 중 최대값이 표본 8~19 에서
    # 위로 치우쳐 비유의 연동(현대리바트 r .53 n8 등)까지 채택됐다 → 단일 검정 5% 유의(r ≥ r_crit(df=n−2))와
    # n ≥ LINK_MIN_N 을 함께 요구한다. 다중비교 보정은 하지 않되 overfit_note 로 남긴다.
    sig = _link_significance(best)
    if best["corr"] < CORR_MIN or not sig["significant_p05_uncorrected"] or best["n_eff"] < LINK_MIN_N:
        why = ("최대 상관 %.2f < %.2f" % (best["corr"], CORR_MIN)) if best["corr"] < CORR_MIN else \
              ("상관 %.2f 가 단일 검정 5%% 임계 r %.2f 미달(n=%d, n_eff=%d)" % (best["corr"], sig["r_crit_p05_neff" if LINK_SIG_USE_NEFF else "r_crit_p05_two_sided"] or 0.0,
                                                               best["n"], best["n_eff"])) if not sig["significant_p05_uncorrected"] else \
              ("유효 짝 n_eff=%d < %d" % (best["n_eff"], LINK_MIN_N))
        p = fb("고객 연동 격자 %s (%s·시차 %d·%s·창 %d)" % (why, best["wkey"], best["lag"], LINK_TRANSFORM_KO[best["transform"]], best["window"]))
        oos_skip = {"adopted": False, "decision": "rejected", "wape_link": None, "wape_trend": None, "note": "유의성 조건 미달 → OOS 비교 전 기각"}
        p["driver"]["customer_link_rejected"] = dict(rejected_base, grid=grid, significance=sig, selection_oos=oos_skip,
                                                     rejected_by=("corr" if best["corr"] < CORR_MIN else ("significance" if not sig["significant_p05_uncorrected"] else "n")),
                                                     merger_rule=[m["rule"] for m in det.get("mergers") or []], customer_sources=det.get("sources") or {})
        p["driver"]["selection_oos"] = oos_skip
        return p
    # OOS 선택(결정 ⓘ, 2026-09-30): 유의해도 동결 백테스트(la−4분기 동결, 4분기 매출 WAPE)에서 추세+계절성보다 OOS_WORSE_TOL 넘게 나쁘면 채택하지 않는다.
    # 격자 후보 45~180 개 중 최대 상관은 위로 치우친다(다중비교) — Bonferroni 류 보정 대신 이 OOS 규칙을 방어로 삼는다(스펙 5-3).
    oos = _link_oos(y_series, cands, ctx, S["last_actual"], adopted=best)
    if oos["adopted"] is False:
        pct = lambda v: ("%.1f%%" % v) if v is not None else "—"     # WAPE 가 None 인 기각 경로(향후 undetermined→기각)에서 TypeError 방지
        p = fb("고객 연동 OOS 기각 — 동결 %s 이후 %d분기 매출 WAPE 연동 %s > 추세 %s × %.2f (%s·시차 %d·%s·창 %d, r=%.2f 유의)"
               % (oos["freeze"], oos["n"], pct(oos["wape_link"]), pct(oos["wape_trend"]), OOS_WORSE_TOL, best["wkey"], best["lag"], LINK_TRANSFORM_KO[best["transform"]], best["window"], best["corr"]))
        p["driver"]["customer_link_rejected"] = dict(rejected_base, grid=grid, significance=sig, selection_oos=oos, rejected_by="oos",
                                                     merger_rule=[m["rule"] for m in det.get("mergers") or []], customer_sources=det.get("sources") or {})
        p["driver"]["selection_oos"] = oos
        return p
    shifted = {q_add(q, best["lag"]): v for q, v in pc["idx0"].items()}
    X = _transform(shifted, best["transform"])
    share_info = _seasonal_share(y_series) if best["transform"] == "ma4" else None
    rev = _link_forecast(best, X, y_series, fq, share_info)
    if not all(q in rev for q in fq):
        return fb("채택 조합(%s)이 추정 구간 매출을 다 내지 못함" % best["transform"])
    p = _plan()
    p["rev"] = rev
    opm, ks = _opm_hist(S)
    opm = clip(opm if opm is not None else 0.0, *OPM_CLIP)
    p["opm"] = {q: (opm, "최근 %d분기 OPM 중위 %.1f%% 유지" % (len(ks), opm * 100)) for q in fq}
    p["driver"] = {"type": "customer_yard_revenue_weighted", "weights": r4_weights(used), "weights_key": best["wkey"], "weights_basis": pc["basis"],
                   "lag_q": best["lag"], "transform": best["transform"], "transform_ko": LINK_TRANSFORM_KO[best["transform"]], "window_q": best["window"],
                   "ratio_used": best["coef"], "coef_kind": "beta_yoy(고객지수 YoY → 자사 YoY, 원점회귀)" if best["transform"] == "yoy" else "b(원점회귀 비례계수)",
                   "corr": best["corr"], "n": best["n"], "n_eff": best["n_eff"], "quarters_used": best["quarters"],
                   "seasonal_share": ({str(k): r4(v) for k, v in share_info[0].items()} if share_info else None),
                   "seasonal_basis": (share_info[1] if share_info else None),
                   "significance": sig, "eligibility": elig, "selection_oos": oos, "grid": grid,
                   "adoption_basis": ("유의성 + OOS(현재 조합 재적합 WAPE 연동 %.2f ≤ 추세 %.2f × %.2f)" % (oos["wape_link_raw"], oos["wape_trend_raw"], OOS_WORSE_TOL))
                                     if oos["adopted"] is True else "유의성만 — OOS undetermined(%s)" % (oos.get("note") or "비교 불가"),
                   "customer_sources": det.get("sources") or {}, "merger_rule": [m["rule"] for m in det.get("mergers") or []],
                   "new_orders_included": None,
                   "new_orders": {"via": "customer_models", "customers": {c: s.get("new_orders_included") for c, s in sorted((det.get("sources") or {}).items())},
                                  "note": "고객 조선사 모델 매출(신규수주 포함 여부는 고객별) 경유 — 이 회사 행에 직접 더한 신규수주는 없음"},
                   "basis": note or "고객 모델 매출 사용"}
    return p


def _sejin_wrap(p, S, fq, ctx, origin, opm_cons):
    """세진: 별도(조선기자재+풍력·플랜트 미분리) 회귀 → 연결 = 별도 + 일승 + 동방선기 + 연결조정(잔차). 모듈은 레퍼런스 가정."""
    sep_rev, sep_op = S["매출별도"], S.get("OP별도") or {}
    subs = {}
    for code, nm in SEJIN_SUBS:
        m = ctx.model(code, origin)
        if m and m.get("rows"):
            rm = {r["key"]: r for r in m["rows"]}
            subs[code] = (nm, merged_rev(rm["매출액"]), merged_rev(rm["영업이익"]))
        else:
            p["warnings"].append("종속사 %s(%s) 모델 없음 → 연결 잔차에 포함" % (nm, code))
    sub_rev = {q: sum(s[1].get(q, 0.0) for s in subs.values()) for q in set().union(*[set(s[1]) for s in subs.values()]) if subs} if subs else {}
    sub_op = {q: sum(s[2].get(q, 0.0) for s in subs.values()) for q in sub_rev}
    resid = {q: S["매출액"][q] - sep_rev[q] - sub_rev.get(q, 0.0) for q in S["매출액"] if q in sep_rev}
    rk = last_n(resid, 4)
    resid_med = med([resid[q] for q in rk]) or 0.0
    # T6 D4: 잔차(내부거래·베트남)는 종속사 매출과 함께 커진다(2025Q3~26Q2 잔차/종속사 −0.61·−0.71·−0.57·−0.64) — 절대값 상수 대신
    # 최근 4분기 '잔차 ÷ 종속사 매출' 중위 × 종속사 추정 매출. 종속사 매출이 없는 분기만 남으면 예전대로 절대값 중위.
    rq = [q for q in rk if sub_rev.get(q)]
    resid_ratio = med([resid[q] / sub_rev[q] for q in rq]) if rq else None
    sep_opm = clip(med([sep_op[q] / sep_rev[q] for q in last_n(sep_rev, 8) if q in sep_op and sep_rev[q]]) or 0.0, *OPM_CLIP)
    rows = {"매출조선기자재": {}, "OP조선기자재": {}, "매출종속사": {}, "OP종속사": {}, "매출연결조정": {}, "OP연결조정": {}}
    for q in sep_rev:
        rows["매출조선기자재"][q] = act(sep_rev[q], "fin.sep.is.매출액(수익) — 별도(조선기자재+풍력·플랜트 미분리)")
        if q in sep_op:
            rows["OP조선기자재"][q] = act(sep_op[q], "fin.sep.is.영업이익")
        if q in sub_rev:
            rows["매출종속사"][q] = act(sub_rev[q], "일승·동방선기 fin 매출 합")
            rows["OP종속사"][q] = act(sub_op[q], "일승·동방선기 fin 영업이익 합")
        rows["매출연결조정"][q] = act(resid[q], "연결 − 별도 − 종속사(베트남 종속·내부거래 잔차)")
        if q in sep_op and q in sub_op and q in S["영업이익"]:
            rows["OP연결조정"][q] = act(S["영업이익"][q] - sep_op[q] - sub_op[q], "연결 OP − 별도 OP − 종속사 OP(잔차)")
    sep_est = {}
    d = p["driver"]
    linked = d.get("type") == "customer_yard_revenue_weighted"
    if linked:
        link_txt = "weighted 고객 매출(%s: %s, t−%d, %s, 창 %d분기, r=%.2f) — 레퍼런스 `연간예상` 방식을 격자 탐색으로 일반화; %s" % (
            d.get("weights_key"), " · ".join("%s %.2f" % (ctx.name(k), v) for k, v in sorted((d.get("weights") or {}).items())),
            d.get("lag_q") or 0, LINK_TRANSFORM_KO.get(d.get("transform"), d.get("transform")), d.get("window_q") or 0, d.get("corr") or 0.0,
            "; ".join(d.get("merger_rule") or []) or "합병 규칙 없음")
    for q in fq:
        if q not in p["rev"]:
            continue
        sep_est[q] = p["rev"][q][0]
        rows["매출조선기자재"][q] = est(sep_est[q], ("%s — %s" % (link_txt, p["rev"][q][1])) if linked
                                     else "별도 매출 추세+계절성(폴백: %s)" % p["rev"][q][1])
        rows["OP조선기자재"][q] = est(sep_est[q] * sep_opm, "별도 매출 × 별도 OPM 8분기 중위 %.1f%%" % (sep_opm * 100))
        rows["매출종속사"][q] = est(sub_rev.get(q, 0.0), "일승·동방선기 모델 매출 합")
        rows["OP종속사"][q] = est(sub_op.get(q, 0.0), "일승·동방선기 모델 영업이익 합")
        if resid_ratio is not None and sub_rev.get(q):
            adj = resid_ratio * sub_rev[q]
            adj_b = "종속사 매출 %.0f억 × 잔차/종속사 매출 최근 %d분기(%s~%s) 중위 %.4f(내부거래·베트남)" % (sub_rev[q], len(rq), rq[0], rq[-1], resid_ratio)
        else:
            adj = resid_med
            adj_b = "최근 %d분기 잔차 중위(내부거래·베트남; 종속사 매출 없음 → 절대값)" % len(rk)
        rows["매출연결조정"][q] = est(adj, adj_b)
        tot = sep_est[q] + sub_rev.get(q, 0.0) + adj
        p["rev"][q] = (tot, "별도(조선기자재) %.0f + 종속사 %.0f + 연결조정 %.0f" % (sep_est[q], sub_rev.get(q, 0.0), adj))
        op_tot = tot * opm_cons
        rows["OP연결조정"][q] = est(op_tot - sep_est[q] * sep_opm - sub_op.get(q, 0.0), "연결 OP − 별도 OP − 종속사 OP(잔차)")
    opm_path = {q: r4(sep_opm) for q in fq}
    p["segments"] = [
        {"key": "조선기자재", "label": "조선기자재(별도 매출 — 풍력·플랜트 부문 미분리)", "driver": dict(p["driver"], target="별도 매출"), "opm_path": opm_path},
        {"key": "종속사", "label": "종속사 일승·동방선기", "driver": {"type": "subsidiary_models", "basis": "각 회사 모델(assets/models) 합산"},
         "opm_path": {q: r4(sub_op.get(q, 0.0) / sub_rev[q]) if sub_rev.get(q) else None for q in fq}},
        {"key": "연결조정", "label": "연결조정(세진베트남·내부거래 잔차)",
         "driver": {"type": "residual_ratio_to_subsidiaries" if resid_ratio is not None else "residual",
                    "ratio_to_sub_rev": r4(resid_ratio), "ratio_quarters": rq, "abs_median": r2(resid_med),
                    "basis": ("(연결 − 별도 − 종속사) ÷ 종속사 매출 최근 %d분기 중위 × 종속사 추정 매출(T6 D4)" % len(rq)) if resid_ratio is not None
                             else "연결 − 별도 − 종속사 최근 4분기 중위"},
         "opm_path": {}},
    ]
    p["extra_rows"] = rows
    p["consolidation"] = {"method": "separate_plus_subsidiaries_plus_residual",
                          "subsidiaries": [{"stock": c, "name": n, "stake": None, "from": ("2021" if c == "333430" else "2022"),
                                            "note": "지분율은 fin face 에 없음(주석 미파싱)"} for c, n in SEJIN_SUBS]
                          + [{"stock": None, "name": "세진베트남(비상장)", "stake": None, "note": "미공시 → 연결조정 잔차"}]}
    p["modules"] = _sejin_modules(ctx, fq)
    p["warnings"].append("풍력/플랜트 부문 실적은 fin face 에서 분리 불가 → 별도 매출 전체를 조선기자재 지수로 추정. 풍력 레퍼런스 표는 모듈(합산 안 함)")
    return p


def _sejin_modules(ctx, fq):
    """레퍼런스(사용자 애널리스트 모델, 2024 초) 가정 표 — 화면·xlsx 에 '레퍼런스 가정' 으로만. 매출에 더하지 않는다."""
    yrs = sorted({q[:4] for q in fq})
    wind = {"2026": 900.0, "2027": 2400.0, "2028": 4200.0}
    wind_rows = [{"key": "wind_ref", "label": "매출추풍력 — 레퍼런스 가정(가이던스 대비 50% 할인, 합산 안 함)", "unit": "억원/년",
                  "q": {y + "Q4": est(v, "레퍼런스 `풍력e`·`연간예상` 합계(2024 초 가정) — 실적 부문 분리 불가로 재정렬 못 함") for y, v in wind.items() if y in yrs}},
                 {"key": "wind_capa", "label": "풍력 건조 캐파 — 레퍼런스 가정", "unit": "억원/년",
                  "q": {y + "Q4": est(2667.0, "Floater 12~13기/년 × 200억(UnitASP) = 2,667억/년, 상한 1.5조") for y in yrs}}]
    lng = [{"key": "lng_fuel_ref", "label": "LNG-Fuel 연료탱크 — 레퍼런스 가정", "unit": "억원/년",
            "q": {y + "Q4": est(45.0, "대당 8~10억 × 연 5척 = 40~50억/년(레퍼런스 r109~113)") for y in yrs}}]
    lpg_rows = []
    cs = load_optional(os.path.join(ASSETS, "contracts.json")) or {}
    cnt = collections.defaultdict(float)
    for r in cs.get("rows") or []:
        if r.get("stock") in ("329180", "010620", "009540") and r.get("type") == "VLGC" and _num(r.get("ships")) and r.get("end") and r["end"][:4] in yrs and not r.get("supersedes"):
            cnt[r["end"][:4]] += r["ships"]
    if cnt:
        lpg_rows.append({"key": "lpg_ships", "label": "HD현대그룹 LPG·암모니아선 인도 척수(원장, 지주 공시 포함 — 중복 가능)", "unit": "척",
                         "q": {y + "Q4": est(v, "contracts.json VLGC 계약 종료연도 기준(정정 미반영·지주/현중 중복 가능) — 레퍼런스 LPG탱커 척수식의 대체 입력") for y, v in sorted(cnt.items())}})
    return [{"key": "wind", "label": "풍력/플랜트(레퍼런스 가정)", "rows": wind_rows},
            {"key": "lng_lpg", "label": "LNG-Fuel · LPG 탱커(레퍼런스 가정·원장)", "rows": lng + lpg_rows}]


STRATEGIES = {"yard": strat_yard, "holding": strat_holding, "engine": strat_supplier, "equip": strat_supplier, "steel": strat_supplier}


# ── 모델 조립 ─────────────────────────────────────────────────

def _actual_series(fin):
    """행 key → {q: 억원}. 지배주주순이익이 없고 비지배가 있으면 차감 파생."""
    S = {}
    for key, _, _, _, src in ROW_DEFS:
        if src:
            S[key] = fin.series(src[0], src[1])
    S["_src"] = {key: fin.src(src[0], src[1]) for key, _, _, _, src in ROW_DEFS if src}
    S["_derived"] = {}
    ni, ctrl = S["당기순이익"], S["지배주주순이익"]
    nci = fin.series("is", "(비지배주주지분)당기순이익")
    for q in ni:
        if q not in ctrl and q in nci:
            ctrl[q] = ni[q] - nci[q]
            S["_derived"].setdefault("지배주주순이익", []).append(q)
    if fin.scope == "sep":
        for q in ni:
            ctrl.setdefault(q, ni[q])
    for q in fin.sep_fill:                       # 별도 보충 분기: 비지배 없음 → 지배 = 전체
        if q in ni:
            ctrl.setdefault(q, ni[q])
        if q in S["자본총계"]:
            S["지배주주지분"].setdefault(q, S["자본총계"][q])
    S["매출별도"] = fin.series("is", "매출액(수익)", scope="sep") if fin.scope == "cons" else {}
    S["OP별도"] = fin.series("is", "영업이익", scope="sep") if fin.scope == "cons" else {}
    S["비지배순이익"] = nci
    S["이자수취"] = fin.series("cf", "이자수취(CF)")
    S["이자지급"] = fin.series("cf", "이자지급(CF)")
    S["이자수익"] = fin.series("is", "이자수익")
    S["이자비용"] = fin.series("is", "이자비용")
    detail, S["_detail_src"], S["_detail_flips"], S["_fx_in_other_nonop"] = _fin_detail(fin, S["금융손익"])
    S.update(detail)
    S["last_actual"] = fin.last
    return S


def _fin_detail(fin, fin_pl):
    """금융손익 세부 실적(T4) → ({행 key: {q: 억원}}, {행 key: {q: src}}, flips, fx_other). 주석 계정(is 의 이자수익·외환차익 …)이 모두 있는 분기만 값.
    기타금융손익 = 금융손익 − 이자 − 외환 − 파생 (2자리 반올림 값끼리 빼서 네 행 합 = 금융손익 셀이 정확히 맞게) — 셋 중 하나라도 없으면 None.
    예외(2026-10-08 (k')): 외환(·파생) 계정이 is 에는 하나도 없고 기타영업외(other) 주석에 하나라도 있으면 그 금액은 face 기타영업외손익 안이므로
    그 행은 만들지 않고(만들면 세전 사슬 이중 계상) 잔차 = 금융손익 − 존재하는 세부 행 합 으로 만든다. fx_other = 외환이 그렇게 빠진 잔차 분기 목록.
    '하나라도' 인 이유: 동성화인텍 2022Q1 처럼 환산손실 줄 자체가 없는 분기(3/4 계정)·인화정공처럼 환산 계정만 있는 회사가 있다."""
    out = {k: {} for k, _ in FIN_DETAIL}
    out["기타금융손익"] = {}
    srcs = {k: {} for k in out}
    fx_other = []
    # 비용 계정 부호: kship_fin 이 2026-10-05 부터 face·주석의 비용을 '양수(크기)' 로 통일해 저장한다(V1 — normalize_expense_signs_table·
    # normalize_note_expense_signs). 예전의 '0 아닌 분기 과반이 음수면 뒤집기' 휴리스틱은 그 뒤로 진짜 환입(3개월 열 음수 — 삼영이엔씨·대한조선
    # 외화환산손실 등)만 잡아 외환손익 부호를 거꾸로 만들었으므로 뺐다. 남은 음수는 전부 환입이라 그대로 더한다.
    flips = []
    for q in fin.quarters:
        sc = fin.scope_of(q)
        note = " (연결 손익 없는 분기 → 별도 보충)" if q in fin._sep_fill else ""
        outside = set()
        for key, terms in FIN_DETAIL:
            vals = [fin.val("is", q, acct) for acct, _ in terms]
            if any(v is None for v in vals):
                if key != "이자손익" and all(v is None for v in vals) and {acct for acct, _ in terms} & fin.other_note_accts(q):
                    outside.add(key)
                continue
            vals = [-v if acct in flips else v for (acct, _), v in zip(terms, vals)]
            out[key][q] = r2(sum(sg * v for (_, sg), v in zip(terms, vals)))
            expr = ""
            for i, (acct, sg) in enumerate(terms):
                expr += ("" if i == 0 else (" + " if sg > 0 else " − ")) + "fin.%s.is.%s" % (sc, acct) + ("(음수 저장 → 부호 반전)" if acct in flips else "")
            srcs[key][q] = expr + note
        if q in fin_pl and q in out["이자손익"] and all(q in out[k] or k in outside for k, _ in FIN_DETAIL):
            present = [k for k, _ in FIN_DETAIL if q in out[k]]
            out["기타금융손익"][q] = r2(r2(fin_pl[q]) - sum(out[k][q] for k in present))
            excl = [k for k, _ in FIN_DETAIL if k in outside]          # 꼬리 주석은 ' — ' 뒤에 — selfcheck 의 src 파서가 ' — ' 이후를 잘라 식만 재계산한다
            srcs["기타금융손익"][q] = "fin.%s.is.금융손익 − %s(잔차)%s%s" % (sc, " − ".join(present), (" — %s은 기타영업외 주석 → 금융 잔차에서 제외" % "·".join(excl)) if excl else "", note)
            if "외환손익" in outside:
                fx_other.append(q)
    return out, srcs, flips, fx_other


def _detect_one_offs(S, all_q):
    """비영업손익(세전 − 영업이익) 급등 분기 — 최근 4분기 창에서 |x| 가 12분기 중위의 ONE_OFF_MIN_RATIO 배 이상, 다른 분기 2위의 2배 초과,
    max(2×|영업이익|, 매출 5%, 최근 4분기 |영업이익| 합 × ONE_OFF_TTM_OP_SHARE) 초과이면 '일회성 의심' 으로 표시한다.
    face 만으로 처분이익 등을 분리할 수 없어 숫자는 바꾸지 않고(실적은 실적) 표기·경고만 남긴다(KCC 2026Q2 3.6조 금융손익 같은 경우)."""
    aq = [q for q in all_q if q in S["매출액"] and q in S["영업이익"] and q in S["세전이익"]]
    nonop = {q: S["세전이익"][q] - S["영업이익"][q] for q in aq}
    win, hist = aq[-4:], aq[-12:]
    ttm_op = sum(abs(S["영업이익"][q]) for q in win)
    out = []
    for q in win:
        others = [abs(nonop[k]) for k in hist if k != q]
        if len(others) < 4:
            continue
        x, medo = abs(nonop[q]), statistics.median(others)
        base_signed = statistics.median([nonop[k] for k in hist if k != q])        # 조정EPS 의 '평상 비영업손익' 기준선(부호 있음)
        second = sorted(others, reverse=True)[1] if len(others) > 1 else 0.0     # 같은 크기가 되풀이되면(이자수익 수준 이동) 일회성이 아니다
        if x > max(1.0, 2 * abs(S["영업이익"][q]), 0.05 * abs(S["매출액"][q]), ONE_OFF_TTM_OP_SHARE * ttm_op) \
                and x > ONE_OFF_MIN_RATIO * max(medo, 1.0) and x > 2 * second:
            out.append({"q": q, "nonop": r2(nonop[q]), "op": r2(S["영업이익"][q]), "fin_pl": r2(S["금융손익"].get(q)), "other_nonop": r2(S["기타영업외손익"].get(q)),
                        "median_abs_nonop_12q": r2(medo), "baseline_nonop_12q": r2(base_signed), "ttm_abs_op": r2(ttm_op), "ni_ctrl": r2(S["지배주주순이익"].get(q)),
                        "note": "비영업손익 급등 — 처분이익 등 일회성 여부는 주석 확인(face 만으로 분리 불가). 이 분기 지배NI·EPS·FY 합계·TTM PER 에 그대로 포함, 12M fwd EPS 에는 미포함"})
    return out


def _adjusted_eps(one_offs, S, rows, all_q, tax_rate, minority):
    """조정EPS 행(일회성 의심 회사만). 의심 분기: 초과 비영업손익 = 비영업손익 − 12분기 기준선(부호 있는 중위, 그 분기 제외) 을
    그 분기 유효세율(법인세/세전, 0~35% 밖이면 모델 세율)로 세후화하고 지배 비중(그 분기 지배NI/NI, 0~1 밖이면 1−비지배 비중)을 곱해 지배NI 에서 뺀다
    → ÷ 그 분기 유통주식수. 다른 실적 분기는 EPS 그대로(kind actual, '= EPS'). 추정 분기는 호출자가 EPS 를 복사한다.
    보고 EPS 행은 바꾸지 않는다(실적은 실적) — one_offs 항목에 산식 필드를 더해 돌려준다."""
    if not one_offs or not rows.get("EPS"):
        return
    flagged = {o["q"]: o for o in one_offs}
    for q in all_q:
        e = rows["EPS"].get(q)
        if not e or not _num(e.get("v")):
            continue
        o = flagged.get(q)
        sh_cell = rows["주식수"].get(q)
        if o is None or not sh_cell or not _num(sh_cell.get("v")) or sh_cell["v"] <= 0:
            rows["조정EPS"][q] = {"v": e["v"], "kind": "actual", "src": "= EPS(일회성 의심 없음)" if o is None else "= EPS(유통주식수 없어 조정 불가)"}
            continue
        shares = sh_cell["v"] * 1e6
        base = o.get("baseline_nonop_12q")
        base = base if _num(base) else 0.0
        excess = o["nonop"] - base
        pt, tx = S["세전이익"].get(q), S["법인세비용"].get(q)
        if _num(pt) and pt > 0 and _num(tx) and 0.0 <= tx / pt <= ONE_OFF_TAX_Q_MAX:
            t_q, t_src = tx / pt, "분기 유효세율(법인세 %.0f억 ÷ 세전 %.0f억)" % (tx, pt)
        else:
            t_q, t_src = tax_rate, "모델 세율(분기 유효세율이 0~%d%% 밖·세전 ≤ 0)" % (ONE_OFF_TAX_Q_MAX * 100)
        ni_q, ctrl_q = S["당기순이익"].get(q), S["지배주주순이익"].get(q)
        if _num(ni_q) and ni_q != 0 and _num(ctrl_q) and 0.0 < ctrl_q / ni_q <= 1.0:
            share, share_src = ctrl_q / ni_q, "그 분기 지배NI/NI"
        else:
            share, share_src = 1.0 - minority, "1 − 비지배 비중(8분기 실측)"
        excess_at = excess * (1.0 - t_q)
        ctrl_adj = (ctrl_q if _num(ctrl_q) else 0.0) - excess_at * share
        eps_adj = round(ctrl_adj * 1e8 / shares, 1)
        o.update({"excess_nonop": r2(excess), "tax_rate_applied": r4(t_q), "tax_rate_source": t_src, "excess_after_tax": r2(excess_at),
                  "ctrl_share_applied": r4(share), "ctrl_share_source": share_src, "ni_ctrl_adj": r2(ctrl_adj), "eps_reported": e["v"], "eps_adj": eps_adj})
        rows["조정EPS"][q] = {"v": eps_adj, "kind": "estimate",
                            "basis": "지배NI %.0f억 − (비영업손익 %.0f억 − 12분기 기준선 %.0f억) × (1 − %.1f%%, %s) × 지배 비중 %.2f(%s) = %.0f억 ÷ 유통주식수 — "
                                     "일회성 여부·세효과는 주석 미확인(모델 추정); 보고 EPS %s원"
                                     % (ctrl_q if _num(ctrl_q) else 0.0, o["nonop"], base, t_q * 100, t_src, share, share_src, ctrl_adj, format(e["v"], ",.1f"))}


def _fx_exposure_usd_m(stock, q, ctx):
    """yards_cache fx 표의 '순 노출' USD(백만원) → 백만$ (기말 환율). 없으면 None."""
    d = load_optional(os.path.join(YARDS_CACHE, stock, q + ".json"))
    fx = (d or {}).get("fx") or {}
    cols = [re.sub(r"\s|\(.*?\)", "", c) for c in fx.get("cols") or []]
    if "USD" not in cols:
        return None
    i = cols.index("USD")
    for r in fx.get("rows") or []:
        if re.sub(r"\s", "", r.get("label") or "") == "순노출":
            vals = r.get("vals") or []
            if i < len(vals) and _num(vals[i]):
                rate, _ = ctx.fx_q(q, "USDKRW_end")
                return (vals[i] / rate) if rate else None
    return None


def _tax_rate(pretax, tax, k12, sum_pt, sum_tax):
    """추정 법인세율(T6 D2). 반환 (rate, basis, path).
    ① 최근 12분기 유효세율(Σ법인세/Σ세전)이 TAX_CLIP(5~27%) 안이면 그대로 — path 'eff12'
    ② 음수·클립 밖·세전 합 ≤ 0 이면 클립하지 않고(이연법인세 인식 등으로 음의 세율이 하한 5% 로 잘려 EPS 를 부풀렸다 — 삼성重 −65.5%)
       최근 8분기 중 세전 > 0 인 분기의 (법인세/세전) 중위 — 그 중위가 TAX_CLIP 안일 때만 — path 'median_pos8'
    ③ 그것도 없거나 범위 밖이면 TAX_DEFAULT(법정세율 근사 22%) — path 'default'."""
    eff = (sum_tax / sum_pt) if (sum_pt > 0 and k12) else None
    if eff is not None and TAX_CLIP[0] <= eff <= TAX_CLIP[1]:
        return eff, "최근 %d분기 유효세율 %.1f%%(5~27%% 안 — 그대로)" % (len(k12), eff * 100), "eff12"
    why = ("최근 %d분기 유효세율 %.1f%% 가 5~27%% 밖" % (len(k12), eff * 100)) if eff is not None else "최근 %d분기 세전 합 ≤ 0" % len(k12)
    k8 = [q for q in last_n(pretax, TAX_FALLBACK_Q) if pretax[q] > 0 and q in tax]
    rates = [tax[q] / pretax[q] for q in k8]
    m = med(rates)
    if m is not None and TAX_CLIP[0] <= m <= TAX_CLIP[1]:
        return m, "%s → 클립 대신 최근 %d분기 중 세전 > 0 인 %d분기(%s~%s)의 법인세/세전 중위 %.1f%%" % (why, TAX_FALLBACK_Q, len(k8), k8[0], k8[-1], m * 100), "median_pos8"
    why2 = ("; 세전 > 0 분기 중위 %.1f%% 도 5~27%% 밖" % (m * 100)) if m is not None else "; 최근 %d분기에 세전 > 0 분기 없음" % TAX_FALLBACK_Q
    return TAX_DEFAULT, "%s%s → 법정세율 근사 %.0f%% 가정" % (why, why2, TAX_DEFAULT * 100), "default"


def _tax_carryforward(pretax, tax, fq, origin):
    """이월결손 세율 경로(라운드 7 D2, 2026-10-08 오너 결정) — _tax_rate 가 'default' 로 떨어진 회사만 본다. 반환 dict 또는 None.
    감지(세율 시계열만): 최근 TAX_FALLBACK_Q 분기 중 세전 > 0 분기가 TAX_CF_MIN_POS_Q 이상이고, 그 (법인세/세전) 중위와 최근 TAX_CF_RECENT_Q 분기 중위가
    모두 TAX_CF_LOW_MAX 미만 — 삼성重처럼 최근 4분기가 정상화된 회사는 걸리지 않는다. 세율이 정상화되면 다음 빌드에서 감지가 자연히 꺼진다.
    경로: 관찰 저세율(중위, 0~TAX_CF_LOW_MAX 클립)을 origin 회계연도 말까지 유지(H1'26 ETR 한화 −1.5%·HJ ~1% — 회사 스스로 연간 ETR≈0 으로 보는 IAS 34 추정)
    → 다음 연도 첫 분기부터 추정 마지막 분기(FY_LAST Q4)까지 선형 램프로 TAX_DEFAULT 수렴. 2027E 이후 세율은 실측 근거 없는 가정.
    인식된 이연법인세자산÷22% 는 저세율 지속의 상한이 아니라(삼성重 DTA 7,780억 피크 뒤 6분기 만에 정상화·DTA 역전) 수렴 시점에 쓰지 않는다 — assumptions.nol_evidence 에 수치만."""
    k8 = [q for q in last_n(pretax, TAX_FALLBACK_Q) if pretax[q] > 0 and q in tax]
    if len(k8) < TAX_CF_MIN_POS_Q:
        return None
    rates = [tax[q] / pretax[q] for q in k8]
    recent = rates[-TAX_CF_RECENT_Q:]
    m8, m4 = med(rates), med(recent)
    if not (m8 < TAX_CF_LOW_MAX and m4 < TAX_CF_LOW_MAX):
        return None
    low = clip(m8, 0.0, TAX_CF_LOW_MAX)
    oy = q_year(origin)
    hold = [q for q in fq if q_year(q) == oy]
    ramp = [q for q in fq if q_year(q) > oy]
    n = len(ramp)
    schedule = {q: low for q in hold}
    schedule.update({q: low + (TAX_DEFAULT - low) * (i + 1) / n for i, q in enumerate(ramp)})
    stage = {q: "유지" for q in hold}
    stage.update({q: "램프 %d/%d" % (i + 1, n) for i, q in enumerate(ramp)})
    hold_txt = ("%.1f%% 를 %s 까지 유지" % (low * 100, hold[-1])) if hold else "%.1f%% 에서 바로 시작" % (low * 100)
    ramp_txt = ("%s~%s 선형 램프로 법정세율 근사 %.0f%% 수렴" % (ramp[0], ramp[-1], TAX_DEFAULT * 100)) if ramp else "램프 분기 없음(추정 전 구간 유지)"
    basis = ("최근 %d분기 중 세전 > 0 인 %d분기(%s~%s) 법인세/세전 중위 %.1f%%·최근 %d분기 중위 %.1f%% 가 모두 %.0f%% 미만 → 이월결손 공제 중으로 보고 %s, %s"
             % (TAX_FALLBACK_Q, len(k8), k8[0], k8[-1], m8 * 100, len(recent), m4 * 100, TAX_CF_LOW_MAX * 100, hold_txt, ramp_txt))
    warning = ("법인세율 이월결손 경로: 최근 양(+)세전 %d분기 유효세율 중위 %.1f%% → %s, %s — 결손 잔액·만기는 주석 미파싱(추정)"
               % (len(k8), m8 * 100, hold_txt, ramp_txt))
    return {"rate": low, "schedule": schedule, "stage": stage, "basis": basis, "path": TAX_CF_PATH, "warning": warning,
            "detect": {"median_pos8": r4(m8), "median_recent4": r4(m4), "n_pos8": len(k8), "quarters": k8},
            "hold_until": hold[-1] if hold else None, "ramp_from": ramp[0] if ramp else None, "ramp_to": ramp[-1] if ramp else None}


SHARE_KIND_KO = {"split": "병합", "bonus": "무상증자", "manual": "수동(복합 사건)"}


def _share_events(stock, fin, px):
    """주식수 사건(라운드 7 (j), 2026-10-08 오너 결정). 반환 {"events", "post", "factors", "latest", "latest_src", "warnings", "factor_at", "why_at"}.
    ① fin.shares 기재 분기(이월 estimate 제외) 인접 짝의 보통주 발행주식수 비율(안 잡히면 유통주식수)이 정수 n 또는 1/n(_int_ratio)이면 병합(split, r<1)·무상증자(bonus, r>1).
    ② SHARE_EVENTS 수동 사건(비정수 복합 사건) — 같은 분기의 자동 감지보다 우선. ①② 모두 사건 분기 ≤ fin.last 만(동결 모델은 origin 뒤 사건을 모른다).
    ③ post(분기말 후 사건, px 있을 때만): fin 최신 보통주 발행주식수 ci 와 aik 상장주식수(= 발행주식수)의 비율 r 이 1 과 SHARES_GAP_MIN 넘게 다르면
       정수비 → split/bonus(최신 유통 = aik − 자기주식 × 비율, factors 에 한 번만 곱함), r > 1 비정수 → issuance(증자/IPO — IAS 33 공정가치 발행은 미환산, 최신 유통 = aik − 자기주식),
       r < 1 비정수 → irregular(환산 없이 최신 주식수만 + 경고). 다음 분기 fin 에 새 주식수가 들어오면 ① 이 잡고 post 는 사라져 두 번 적용되지 않는다.
    ④ factor_at(q) = Π{사건 비율 : 사건 분기 > q} × post 비율 — 그 분기 주식수에 곱하면 최신 기준 주식수(과거 EPS·BPS·DPS 는 ÷ 비율 = IAS 33.64 비교표시·수정주가 이력과 정합).
       이월(carried_from) 분기는 원 분기의 비율. factors 는 fin.quarters 의 값.
    ⑤ eps_check: fin eps_reported 비교표시(사건 분기~+3 의 prev_q·prev_ytd·prev_full ÷ 4분기 전 cur_*)가 1/비율 의 ±SHARES_EPS_CHECK_TOL 안이면 confirmed,
       전부 ≈1 이면 contradicted(경고 — 회사가 비교표시를 안 한 사례(대창 2026Q2)가 있어 경고용), 자료 없으면 unconfirmed.
    ⑥ 안전망: 비교표시 prev_q·prev_ytd 가 같은 정수 n(2..N_MAX, ±5%) 배인데 그 분기 −3~+1 에 사건이 없으면 미처리 후보 경고(환산하지 않음)."""
    sh = fin.raw.get("shares") or {}
    last = fin.last or "9999Q4"

    def co(q):
        s = sh.get(q) or {}
        v = s.get("common_outstanding") or s.get("outstanding")
        return v if _num(v) and v > 0 else None

    def ci(q):
        s = sh.get(q) or {}
        v = s.get("common_issued") or s.get("issued")
        return v if _num(v) and v > 0 else co(q)

    qs = [q for q in sorted(sh) if q <= last and co(q)]
    real = [q for q in qs if (sh[q].get("kind") or "actual") != "estimate"]
    warnings, ev_by_q = [], {}
    for a, b in zip(real, real[1:]):
        for lab, fn in (("발행", ci), ("유통", co)):
            raw_r = fn(b) / fn(a)
            r = _int_ratio(raw_r)
            if r is not None:
                ev_by_q[b] = {"q": b, "ratio": r, "kind": "split" if r < 1 else "bonus",
                              "src": "fin.shares %s→%s 보통주 %s주식수 %s→%s(비율 %.6f ≈ %s, 자동 감지 ±%.1f%%)"
                                     % (a, b, lab, format(int(fn(a)), ",d"), format(int(fn(b)), ",d"), raw_r, _ratio_txt(r), SHARES_SPLIT_TOL * 100)}
                break
    for q, r, why in SHARE_EVENTS.get(stock) or []:
        if q <= last:
            ev_by_q[q] = {"q": q, "ratio": float(r), "kind": "manual", "src": "SHARE_EVENTS: " + why}
    events = [ev_by_q[q] for q in sorted(ev_by_q)]
    # ⑤ eps_reported 교차검증(비교표시 prev ÷ 4분기 전 cur)
    er = (fin.raw.get(fin.scope) or {}).get("eps_reported") or {}

    def cmp_ratios(qp):
        cur, base = er.get(qp) or {}, er.get(q_add(qp, -4)) or {}
        out = []
        for pk, ck in (("prev_q", "cur_q"), ("prev_ytd", "cur_ytd"), ("prev_full", "cur_full")):
            p, c = cur.get(pk), base.get(ck)
            if _num(p) and _num(c) and abs(c) >= SHARES_EPS_MIN_WON:
                out.append((p / c, pk))
        return out

    for e in events:
        exp = 1.0 / e["ratio"]
        ratios = [r for i in range(4) if q_add(e["q"], i) <= last for r, _ in cmp_ratios(q_add(e["q"], i))]
        if any(abs(r / exp - 1.0) <= SHARES_EPS_CHECK_TOL for r in ratios):
            e["eps_check"] = "confirmed"
        elif any(abs(r - 1.0) <= SHARES_EPS_CHECK_TOL for r in ratios):
            e["eps_check"] = "contradicted"
            warnings.append("주식수 사건 교차검증 불일치: %s %s %s 인데 fin eps_reported 비교표시 비율이 ≈1(%s) — 회사가 비교표시를 환산하지 않았거나 사건 오탐 → 주석 확인(환산은 적용)"
                            % (e["q"], _ratio_txt(e["ratio"]), SHARE_KIND_KO[e["kind"]], ", ".join("%.3f" % r for r in ratios)))
        else:
            e["eps_check"] = "unconfirmed"
    # ⑥ 미처리 후보 — 비교표시 prev_q·prev_ytd 가 같은 정수배인데 −3~+1 분기에 사건이 없다
    for qp in sorted(er):
        if qp > last:
            continue
        rs = {k: r for r, k in cmp_ratios(qp)}
        if "prev_q" not in rs or "prev_ytd" not in rs:
            continue
        n = round(rs["prev_q"])
        if not (2 <= n <= SHARES_SPLIT_N_MAX) or abs(rs["prev_q"] - n) > 0.05 * n or abs(rs["prev_ytd"] - n) > 0.05 * n:
            continue
        if any(q_add(qp, -3) <= e["q"] <= q_add(qp, 1) for e in events):
            continue
        warnings.append("주식수 사건 미처리 후보: fin eps_reported %s 비교표시가 전년 보고의 ×%d(prev_q %.2f·prev_ytd %.2f)인데 주식수 사건 없음 — 주식수 비율 비정수(병합+증자/소각 동시?) → SHARE_EVENTS 확인; 환산하지 않음"
                        % (qp, n, rs["prev_q"], rs["prev_ytd"]))
    # ③ 분기말 후 사건(aik 상장주식수 vs fin 최신 발행주식수)
    post, latest, latest_src = None, None, None
    aik = (px or {}).get("shares_outstanding")
    if qs and _num(aik) and aik > 0:
        lq = qs[-1]
        c_i = ci(lq)
        tr = sh[lq].get("common_treasury") if _num(sh[lq].get("common_treasury")) else (sh[lq].get("treasury") or 0)
        r = aik / c_i
        if abs(r - 1.0) > SHARES_GAP_MIN:
            ir = _int_ratio(r)
            base = {"aik": int(aik), "fin_q": lq, "fin_issued": int(c_i), "treasury": int(tr), "ratio_raw": round(r, 6)}
            a_s, c_s, t_s = format(int(aik), ",d"), format(int(c_i), ",d"), format(int(tr), ",d")
            if ir is not None:
                latest = int(round(aik - tr * ir))
                kind = "split" if ir < 1 else "bonus"
                post = dict(base, kind=kind, ratio=ir, latest=latest,
                            src="aik 상장주식수 %s = fin %s 보통주 발행 %s × %s → 분기말 후 %s; 최신 유통 = aik − 자기주식 %s × %s = %s"
                                % (a_s, lq, c_s, _ratio_txt(ir), SHARE_KIND_KO[kind], t_s, _ratio_txt(ir), format(latest, ",d")))
                latest_src = "prices.json shares_outstanding(aik 상장 %s = fin %s 보통주 발행 %s × %s — 분기말 후 %s) − 자기주식 %s × %s" % (
                    a_s, lq, c_s, _ratio_txt(ir), SHARE_KIND_KO[kind], t_s, _ratio_txt(ir))
                warnings.append("분기말 후 %s: aik 상장주식수 %s = fin %s 보통주 발행 %s × %s → 최신 유통주식수 %s(자기주식 %s × %s 차감) — 실적 분기 주식수·EPS·BPS·DPS 를 %s 로 환산"
                                "(IAS 33.64 비교표시·수정주가 이력과 정합), 추정 분기·PER/PBR now·EV 는 최신 주식수. 효력일·단수주 처리는 정기보고서 캐시 밖(주요사항보고서 미수집)"
                                % (SHARE_KIND_KO[kind], a_s, lq, c_s, _ratio_txt(ir), format(latest, ",d"), t_s, _ratio_txt(ir), _ratio_txt(ir)))
            else:
                latest = int(round(aik - tr))
                if r > 1:
                    new = int(round(aik - c_i))
                    post = dict(base, kind="issuance", ratio=None, latest=latest, new_shares=new,
                                src="aik 상장주식수 %s = fin %s 보통주 발행 %s + 신주 %s(비율 %.4f 비정수 → 증자/상장, 환산 없음); 최신 유통 = aik − 자기주식 %s = %s"
                                    % (a_s, lq, c_s, format(new, ",d"), r, t_s, format(latest, ",d")))
                    latest_src = "prices.json shares_outstanding(aik 상장 %s = fin %s 보통주 발행 %s + 신주 %s — 분기말 후 증자/상장, 비율 %.4f 비정수) − 자기주식 %s" % (
                        a_s, lq, c_s, format(new, ",d"), r, t_s)
                    warnings.append("분기말 후 증자/상장: aik 상장주식수 %s − fin %s 보통주 발행 %s = 신주 %s(비율 %.4f; aik−fin 산술, 공시 미확인) → 추정 분기만 신주식수 %s, "
                                    "실적 EPS·BPS 불변(IAS 33 공정가치 발행 미환산), 납입자본은 BS 롤에 미반영(공모가·납입액 미확인) → 추정 BPS 과소"
                                    % (a_s, lq, c_s, format(new, ",d"), r, format(latest, ",d")))
                else:
                    post = dict(base, kind="irregular", ratio=None, latest=latest,
                                src="aik 상장주식수 %s / fin %s 보통주 발행 %s = %.4f 비정수 감소(병합/소각 미확인, 환산 없음); 최신 유통 = aik − 자기주식 %s = %s"
                                    % (a_s, lq, c_s, r, t_s, format(latest, ",d")))
                    latest_src = "prices.json shares_outstanding(aik 상장 %s vs fin %s 보통주 발행 %s, 비율 %.4f 비정수 감소 — 병합/소각 미확인) − 자기주식 %s" % (a_s, lq, c_s, r, t_s)
                    warnings.append("분기말 후 주식수 감소 비정수: aik 상장주식수 %s / fin %s 보통주 발행 %s = %.4f — 병합+소각 복합 가능 → SHARE_EVENTS 수동 확인; 최신 주식수만 %s 로 바꾸고 실적은 환산하지 않음"
                                    % (a_s, lq, c_s, r, format(latest, ",d")))
    post_r = (post or {}).get("ratio") or 1.0

    def src_q(q):
        s = sh.get(q) or {}
        return s["carried_from"] if (s.get("kind") == "estimate" and s.get("carried_from")) else q

    def factor_at(q):
        q = src_q(q)
        f = post_r
        for e in events:
            if e["q"] > q:
                f *= e["ratio"]
        return f

    def why_at(q):
        q = src_q(q)
        parts = ["%s %s %s" % (e["q"], _ratio_txt(e["ratio"]), SHARE_KIND_KO[e["kind"]]) for e in events if e["q"] > q]
        if post_r != 1.0:
            parts.append("%s 분기말 후 %s(aik 상장주식수)" % (post["fin_q"], _ratio_txt(post_r)))
        return " · ".join(parts)

    factors = {q: factor_at(q) for q in fin.quarters}
    if events:
        warnings.append("주식수 사건 환산: %s → 사건 전 실적 %d분기의 주식수·EPS·BPS·DPS 를 비율 환산(IAS 33.64; 셀 kind estimate, basis 에 원주식수·비율)"
                        % (" · ".join("%s %s %s(eps_reported 교차검증 %s)" % (e["q"], _ratio_txt(e["ratio"]), SHARE_KIND_KO[e["kind"]], e["eps_check"]) for e in events),
                           sum(1 for f in factors.values() if f != 1.0)))
    return {"events": events, "post": post, "factors": factors, "latest": latest, "latest_src": latest_src, "warnings": warnings,
            "factor_at": factor_at, "why_at": why_at}


def build_model(stock, ctx, origin=None, freeze=False):
    """모델 json(스펙 2-5). origin 을 주면 그 분기까지의 fin 만 쓴다(백테스트·고객 모델 동결)."""
    raw = ctx.fin(stock)
    role = ctx.role(stock)
    name = ctx.name(stock)
    if not raw:
        return {"stock": stock, "name": name, "role": role, "status": "no_fin", "origin": origin, "rows": [],
                "quality": {"fin_quarters": 0, "missing": [], "identities_ok": None, "warnings": ["assets/fin/%s.json 없음 — 수집 후 재실행" % stock], "status": "no_fin"}}
    fin = Fin(raw, upto=origin)
    if not fin.quarters:
        return {"stock": stock, "name": name, "role": role, "status": "no_fin", "origin": origin, "rows": [],
                "quality": {"fin_quarters": 0, "missing": [], "identities_ok": None, "warnings": ["origin %s 이전 fin 분기 없음" % origin], "status": "no_fin"}}
    S = _actual_series(fin)
    la = fin.last
    all_q = q_range(fin.first, la)
    n_fwd = max(FWD_MIN, len(q_range(q_next(la), HORIZON_END)) if la < HORIZON_END else FWD_MIN)
    fq = [q_add(la, i) for i in range(1, n_fwd + 1)]
    quarters = all_q + fq
    warnings, missing = [], [q for q in all_q if q not in fin.quarters]
    if missing:
        warnings.append("fin 미수집 분기 %d개(no_report 등): %s" % (len(missing), ", ".join(missing[:6])))
    role_eff = role if role in STRATEGIES else "equip"
    if role not in STRATEGIES:
        warnings.append("역할 미지정(universe·suppliers 에 없음) → equip 규칙 적용")
    if S["_detail_flips"]:
        warnings.append("fin 주석 비용 계정을 음수로 저장(0 아닌 분기 과반) → 금융손익 세부 계산에서 부호 반전: %s — kship_fin 부호 규약 확인 필요" % ", ".join(S["_detail_flips"]))
    if S["_derived"].get("지배주주순이익"):
        warnings.append("지배주주순이익 face 누락 분기는 당기순이익 − 비지배 로 파생: %s" % ", ".join(S["_derived"]["지배주주순이익"]))
    if S["_fx_in_other_nonop"]:
        warnings.append("외환차손익이 기타영업외 주석에 있음(%d분기, %s~%s) → 외환손익 행 없음, 기타금융손익 = 금융손익 − 이자 − 파생(fx_in_other_nonop)"
                        % (len(S["_fx_in_other_nonop"]), S["_fx_in_other_nonop"][0], S["_fx_in_other_nonop"][-1]))
    plan = STRATEGIES[role_eff](stock, S, fq, ctx, origin)
    if not plan["rev"]:
        plan = strat_trend(stock, S, fq, ctx, origin, reason="전략이 매출을 내지 못함")
    warnings += plan["warnings"]
    if not plan["segments"]:
        # 부문 분리가 없는 회사(기자재·엔진·강재·지주·선표 없는 조선사): 드라이버(가중치·시차·상관·비례계수·기각 사유)를 스펙 2-5 대로
        # segments[0].driver 에 남기고, 전사 행(매출전사·OP전사 = 매출액·영업이익)을 사업부 행처럼 둔다 — 화면 사업부 차트·드라이버 문구가 여기서 나온다.
        seg_rows = {"매출전사": {}, "OP전사": {}}
        for q in S["매출액"]:
            seg_rows["매출전사"][q] = act(S["매출액"][q], "= 매출액(부문 미분리)")
            if q in S["영업이익"]:
                seg_rows["OP전사"][q] = act(S["영업이익"][q], "= 영업이익(부문 미분리)")
        for q in fq:
            if q in plan["rev"] and q in plan["opm"]:
                seg_rows["매출전사"][q] = est(plan["rev"][q][0], "= 매출액 추정(부문 미분리)")
                seg_rows["OP전사"][q] = est(plan["rev"][q][0] * plan["opm"][q][0], "= 매출액 × OPM(부문 미분리)")
        plan["segments"] = [{"key": "전사", "label": "전사(부문 미분리)", "driver": plan["driver"],
                             "opm_path": {q: r4(plan["opm"][q][0]) for q in fq if q in plan["opm"]}}]
        plan["extra_rows"] = dict(plan.get("extra_rows") or {}, **seg_rows)
    if fin.sep_fill:
        ov = [q for q in fin.quarters if q not in fin._sep_fill and fin._get("sep", "is", q, "매출액(수익)")]
        diff_txt = ""
        if ov:
            qo = ov[-1]
            c, sp = fin._get("cons", "is", qo, "매출액(수익)"), fin._get("sep", "is", qo, "매출액(수익)")
            if c and sp:
                diff_txt = "; 겹치는 마지막 분기 %s 연결/별도 매출 %+.1f%%" % (qo, (c / sp - 1) * 100)
        warnings.append("연결 손익 없는 분기 %d개는 별도 재무제표로 보충(셀 src 표기; fin issues no_cons_statements·no_prior_ytd%s): %s"
                        % (len(fin.sep_fill), diff_txt, ", ".join(fin.sep_fill[:12]) + ("…" if len(fin.sep_fill) > 12 else "")))

    rows = collections.OrderedDict((k, {}) for k, *_ in ROW_DEFS)
    derived_ctrl = set(S["_derived"].get("지배주주순이익") or [])
    for key in rows:
        if key in S and isinstance(S[key], dict) and key in SRC_DEF:
            kind_, acct = SRC_DEF[key]
            for q, v in S[key].items():
                if key == "지배주주순이익" and q in derived_ctrl:
                    # face 에 지배주주 줄이 없는 분기 — 값은 당기순이익 − 비지배 파생이므로 src 도 그렇게 적는다(selfcheck fin_model_mislabel 2026-10-05)
                    sc = fin.scope_of(q)
                    rows[key][q] = act(v, "fin.%s.is.당기순이익 − fin.%s.is.(비지배주주지분)당기순이익(파생)" % (sc, sc))
                else:
                    rows[key][q] = act(v, fin.src(kind_, acct, q=q))
    for key, srcs in S["_detail_src"].items():          # 금융손익 세부(주석 계정 파생 실적)
        for q, v in S[key].items():
            rows[key][q] = act(v, srcs[q])
    # 파생 실적: OPM · EBITDA · 주식수 · EPS · BPS · DPS  (fin 주식수 없으면 prices 폴백 — 아래 shares 결정과 같은 값)
    # 주식수 사건(라운드 7 (j)): 병합·분할·무상증자(fin 안 자동 감지·SHARE_EVENTS·aik 분기말 후) 전 분기의 주식수에 비율을 곱해 최신 기준으로 환산 → EPS/BPS 분모도 같이
    ev = _share_events(stock, fin, None if freeze else ctx.price(stock))
    warnings.extend(ev["warnings"])
    shares_fb = None
    if not fin.last_shares()[0] and not freeze:
        px0 = ctx.price(stock) or {}
        shares_fb = px0.get("shares_outstanding") if (_num(px0.get("shares_outstanding")) and px0["shares_outstanding"] > 0) else None
    for q in all_q:
        rv, op = S["매출액"].get(q), S["영업이익"].get(q)
        if rv and op is not None:
            rows["OPM"][q] = {"v": r4(op / rv), "kind": "actual", "src": "영업이익 ÷ 매출액(파생)"}
        da = S["감가상각비"].get(q)
        if op is not None and da is not None:
            rows["EBITDA"][q] = act(op + da, "영업이익 + 감가상각비(CF)")
        sh = fin.shares_outstanding(q)
        sh_kind, sh_src, sh_q = "actual", "fin.shares.common_outstanding", q
        if not sh:
            near = [k for k in fin.quarters if fin.shares_outstanding(k)]
            prev = [k for k in near if k < q]
            nxt = [k for k in near if k > q]
            if prev or nxt:
                k = prev[-1] if prev else nxt[0]
                sh, sh_kind, sh_src, sh_q = fin.shares_outstanding(k), "estimate", "주식의 총수 기재 없는 분기 → %s 값 이월" % k, k
            elif shares_fb:
                sh, sh_kind, sh_src = shares_fb, "estimate", "prices.json shares_outstanding(aik 발행(상장)주식수 — 자기주식 미차감) — fin 주식의 총수 없음"
        if sh:
            f = ev["factors"].get(sh_q, 1.0)
            if f != 1.0:                                  # 사건 전 분기 → 환산(kind estimate; selfcheck 는 estimate 주식수 셀 v 로 EPS/BPS 를 재계산한다)
                sh_src = "%s %s주 × %s(환산 — %s; IAS 33.64 비교표시·수정주가 이력과 정합)" % (sh_src, format(int(round(sh)), ",d"), _ratio_txt(f), ev["why_at"](sh_q))
                sh, sh_kind = sh * f, "estimate"
            rows["주식수"][q] = {"v": (sh / 1e6 if f != 1.0 else round(sh / 1e6, 3)), "kind": sh_kind, ("src" if sh_kind == "actual" else "basis"): sh_src}
            ni_c = S["지배주주순이익"].get(q)
            if ni_c is not None:
                rows["EPS"][q] = {"v": round(ni_c * 1e8 / sh, 1), "kind": "actual", "src": "지배주주순이익 ÷ 유통주식수(파생)"}
            eq_c = S["지배주주지분"].get(q)
            if eq_c is not None:
                rows["BPS"][q] = {"v": round(eq_c * 1e8 / sh, 1), "kind": "actual", "src": "지배주주지분 ÷ 유통주식수(파생)"}
    dps = fin.dps_series()
    dps_f = {y: (ev["factor_at"]("%dQ4" % y) if dps[y] else 1.0) for y in dps}   # 결산연도 Q4 뒤 사건만 DPS 환산(Q4 사건은 그 해 DPS 가 이미 신주식수 기준); DPS 0 은 환산 무의미
    for y, v in dps.items():
        if "%dQ4" % y in all_q:
            if dps_f[y] != 1.0:
                rows["DPS"]["%dQ4" % y] = {"v": round(v / dps_f[y], 2), "kind": "estimate",
                                           "basis": "fin.dividend.dps_common %s원 ÷ %s(병합/분할 환산 — %s)" % (format(v, ",.0f"), _ratio_txt(dps_f[y]), ev["why_at"]("%dQ4" % y))}
            else:
                rows["DPS"]["%dQ4" % y] = {"v": float(v), "kind": "actual", "src": "fin.dividend.dps_common(연간, Q4 에 표기)"}

    # ── 공통 가정 ──
    rev_a, op_a = S["매출액"], S["영업이익"]
    k4 = last_n(rev_a, 4)
    sga_ratio = med([S["판관비"][q] / rev_a[q] for q in k4 if q in S["판관비"] and rev_a[q]]) or 0.0
    k12 = last_n(S["세전이익"], 12)
    sum_pt = sum(S["세전이익"][q] for q in k12)
    sum_tax = sum(S["법인세비용"].get(q, 0.0) for q in k12)
    tax_rate, tax_basis, tax_path = _tax_rate(S["세전이익"], S["법인세비용"], k12, sum_pt, sum_tax)
    tax_cf = _tax_carryforward(S["세전이익"], S["법인세비용"], fq, la) if tax_path == "default" else None   # ①eff12·②median_pos8 가 잡은 회사는 그대로
    tax_sched = {}
    if tax_cf:
        tax_rate, tax_basis, tax_path, tax_sched = tax_cf["rate"], tax_cf["basis"], tax_cf["path"], tax_cf["schedule"]
        warnings.append(tax_cf["warning"])
    dta = fin.val("bs", la, "이연법인세자산")
    nol_evidence = {"dta_eok": r2(dta), "dtl_eok": r2(fin.val("bs", la, "이연법인세부채")), "retained_earnings_eok": r2(fin.val("bs", la, "이익잉여금")),
                    "nol_cap_eok": r2(dta / TAX_DEFAULT) if dta else None,
                    "note": "참고용 — 인식된 DTA 의 이용은 법인세비용을 올리므로 저세율 지속 상한으로 쓰지 않음(삼성重 선례); 주석 이월결손금 표 미파싱"}
    k8 = last_n(S["당기순이익"], 8)
    ni8 = sum(S["당기순이익"][q] for q in k8)
    nci8 = sum(S["비지배순이익"].get(q, 0.0) for q in k8)
    minority = clip(nci8 / ni8, 0.0, 0.6) if (ni8 > 0 and S["비지배순이익"]) else 0.0
    # 이자율: 주석 이자수익/이자비용(is)이 최근 4분기 이상이면 그것 ÷ 평균 잔액, 아니면 CF 실측(Σ이자수취/평균 이자발생자산, Σ|이자지급|/평균 총차입금)
    def _rate(flow, bal, min_n=2):
        ks = [q for q in last_n(flow, 4) if q in bal]
        if len(ks) < min_n:
            return None, ks
        avg = sum(bal[q] for q in ks) / len(ks)
        return ((sum(abs(flow[q]) for q in ks) / avg * 4 / len(ks)) if avg > 0 else None), ks

    def _pick_rate(note_flow, note_ko, cf_flow, cf_ko, bal, bal_ko):
        """(연율, 출처 문구, interest_rate_check). 주석 연율이 기본. 주석/CF > INTEREST_NOTE_CF_MAX_RATIO 또는 주석 > INTEREST_RATE_ABS_MAX 면 이상 —
        주석이 stale(마지막 주석 분기 ≠ 마지막 실적 la) 이거나 절대상한 초과면 CF 연율로 클립(CF 없으면 상한값), 최근 4분기 연속 주석이면 유지 + 경고
        (HD한국조선해양·HD현대중공업 13~14% 는 차입금 외 이자가 구조적으로 들어 있어 IS 이자비용 예측엔 CF 연율보다 낫다 — 2026-10-08).
        CF 교체는 CF 창이 주석 창 이상으로 최신일 때만(ksc[-1] >= ksn[-1]) — 더 오래된 CF 연율로 바꾸면 신선도가 되레 떨어진다(KS인더스트리 주석 ~2026Q1 vs CF ~2024Q1).
        CF 창이 더 오래되면 상한 초과만 상한으로 클립(clipped_abs), 그 외는 주석 유지 + 경고(kept_warn, reason 기록) — 2026-10-09 검증 수정."""
        rn, ksn = _rate(note_flow, bal, RATE_NOTES_MIN_Q)
        rc, ksc = _rate(cf_flow, bal)
        cf_win = {"first": ksc[0], "last": ksc[-1], "age_q": len(q_range(ksc[-1], la)) - 1} if rc is not None else None   # age_q = 마지막 실적 la 대비 CF 창 끝의 분기 차
        check = {"note": r4(rn), "cf": r4(rc), "ratio": None, "note_last_q": ksn[-1] if ksn else None, "cf_window": cf_win, "action": None, "reason": None}
        if rn is None:
            why = "주석 %s %d분기 < %d" % (note_ko, len([q for q in note_flow if q in bal]), RATE_NOTES_MIN_Q)
            check["action"] = "cf" if rc is not None else None
            return rc, ("CF %s ÷ 평균 %s(%s~%s; %s)" % (cf_ko, bal_ko, ksc[0], ksc[-1], why) if rc is not None else None), check
        ratio = rn / rc if (rc is not None and rc > 0) else None
        check["ratio"] = r2(ratio)
        over_abs = rn > INTEREST_RATE_ABS_MAX
        anomaly = over_abs or (ratio is not None and ratio > INTEREST_NOTE_CF_MAX_RATIO)
        if anomaly and (over_abs or ksn[-1] != la):
            reason = ("주석 연율 %.1f%% > 상한 %.0f%%" % (rn * 100, INTEREST_RATE_ABS_MAX * 100) if over_abs
                      else "주석 마지막 분기 %s ≠ 마지막 실적 %s(stale)" % (ksn[-1], la))
            check["reason"] = reason + (" · 주석/CF %.2f배" % ratio if ratio is not None else "")
            if rc is None:                                   # ratio 없음 → 이상은 절대상한 초과뿐
                check["action"] = "clipped_abs"
                return INTEREST_RATE_ABS_MAX, "주석 %s 연율 %.1f%% > 상한 %.0f%% → 상한으로 클립(CF 없음)" % (note_ko, rn * 100, INTEREST_RATE_ABS_MAX * 100), check
            cf_txt = "CF 창 %s~%s(%s)" % (ksc[0], ksc[-1], "= la" if cf_win["age_q"] == 0 else "la −%d분기" % cf_win["age_q"])
            if ksc[-1] >= ksn[-1]:                           # CF 창이 주석 창 이상으로 최신 → CF 연율로 교체
                check["reason"] += " · " + cf_txt
                check["action"] = "clipped_cf"
                return rc, "CF %s ÷ 평균 %s(%s~%s; 주석 %s 연율 %.1f%% 클립 — %s)" % (cf_ko, bal_ko, ksc[0], ksc[-1], note_ko, rn * 100, check["reason"]), check
            check["reason"] += " · %s 가 주석 창(~%s)보다 오래됨 → CF 로 교체 안 함" % (cf_txt, ksn[-1])
            if over_abs:                                     # 더 오래된 CF 대신 상한으로
                check["action"] = "clipped_abs"
                return INTEREST_RATE_ABS_MAX, "주석 %s 연율 %.1f%% > 상한 %.0f%% → 상한으로 클립(%s 가 주석보다 오래됨)" % (note_ko, rn * 100, INTEREST_RATE_ABS_MAX * 100, cf_txt), check
            check["action"] = "kept_warn"
            return rn, "주석 %s ÷ 평균 %s(%s~%s)" % (note_ko, bal_ko, ksn[0], ksn[-1]), check
        check["action"] = "kept_warn" if anomaly else "note"
        return rn, "주석 %s ÷ 평균 %s(%s~%s)" % (note_ko, bal_ko, ksn[0], ksn[-1]), check
    r_asset, r_asset_src, r_asset_chk = _pick_rate(S["이자수익"], "이자수익", S["이자수취"], "이자수취", S["이자발생자산"], "이자발생자산")
    r_debt, r_debt_src, r_debt_chk = _pick_rate(S["이자비용"], "이자비용", S["이자지급"], "이자지급", S["총차입금"], "총차입금")
    for side_ko, chk in (("이자발생자산", r_asset_chk), ("총차입금", r_debt_chk)):
        if chk["action"] in ("clipped_cf", "clipped_abs"):
            warnings.append("%s 이자율: 주석 연율 %.1f%% 이상(%s) → %s 로 클립(assumptions.interest_rate_check)" % (
                side_ko, chk["note"] * 100, chk["reason"],
                ("CF 연율 %.1f%%" % (chk["cf"] * 100)) if chk["action"] == "clipped_cf" else ("상한 %.0f%%" % (INTEREST_RATE_ABS_MAX * 100))))
        elif chk["action"] == "kept_warn" and chk["reason"]:   # stale 이지만 CF 창이 주석 창보다 오래됨 → 주석 유지
            warnings.append("%s 이자율: 주석 연율 %.1f%% 이상(%s) — 더 오래된 CF 연율 %.1f%% 로 바꾸지 않고 주석 유지(assumptions.interest_rate_check)" % (
                side_ko, chk["note"] * 100, chk["reason"], chk["cf"] * 100))
        elif chk["action"] == "kept_warn":
            warnings.append("%s 이자율: 주석 연율 %.1f%% 가 CF 연율 %.1f%% 의 %.1f배 — 최근 4분기 연속 주석이라 유지(차입금 외 이자 포함 가능 — 주석 확인). 클립 조건: stale 또는 > %.0f%%" % (
                side_ko, chk["note"] * 100, chk["cf"] * 100, chk["ratio"], INTEREST_RATE_ABS_MAX * 100))
    fin_med = med([S["금융손익"][q] for q in last_n(S["금융손익"], 4)])
    # 기타금융손익(잔차) 추정: 최근 4분기 중위 — |중위| 가 첫 추정 분기 이자손익의 50% 를 넘으면 0 + 경고(평가손익·재분류가 섞인 잔차를 이어 붙이지 않음)
    oth_ks = last_n(S["기타금융손익"], FIN_OTHER_MIN_Q)
    oth_med = med([S["기타금융손익"][q] for q in oth_ks]) if len(oth_ks) >= FIN_OTHER_MIN_Q else None
    eq_med = med([S["지분법손익"][q] for q in last_n(S["지분법손익"], 4)]) if S["지분법손익"] else None
    shares, shares_q = fin.last_shares()
    shares_src = "fin.shares.common_outstanding(%s)" % shares_q
    if ev["post"]:                                        # 분기말 후 병합/분할·증자(aik 상장주식수) — 추정 분기·PER/PBR now·EV 는 사건 반영 최신 유통주식수
        shares, shares_q, shares_src = ev["latest"], ((ctx.price(stock) or {}).get("as_of") or "prices"), ev["latest_src"]
    if not shares:
        px = ctx.price(stock) if not freeze else None
        if _num((px or {}).get("shares_outstanding")) and px["shares_outstanding"] > 0:
            shares, shares_q, shares_src = px["shares_outstanding"], (px.get("as_of") or "prices"), "prices.json shares_outstanding(aik 발행(상장)주식수 — 자기주식 미차감; fin 주식의 총수 없음)"
            warnings.append("fin 주식의 총수 없음 → 주식수는 aikstockdata shares_outstanding %s 사용(발행(상장)주식수 — 자기주식 미차감; 추정 구간·EPS/BPS 실적 파생 모두)" % format(shares, ",d"))
        else:
            warnings.append("유통주식수 없음 → EPS·BPS 미산출")
    # 직전 결산 DPS — 사건 환산값(DPS 행·추정 DPS·배당 현금·payout 에 같은 값); 비사건이면 fin 원값 그대로(int)
    y_d = max(dps) if dps else None
    last_dps = (dps[y_d] if dps_f[y_d] == 1.0 else round(dps[y_d] / dps_f[y_d], 2)) if dps else 0.0
    last_dps_txt = ("%s원" % format(last_dps, ",.0f")) if (not dps or dps_f[y_d] == 1.0) else "%s원(fin %s원 ÷ %s 병합/분할 환산)" % (format(last_dps, ",.0f"), format(dps[y_d], ",.0f"), _ratio_txt(dps_f[y_d]))
    payout = None
    if dps and shares:
        ni_y = sum(S["지배주주순이익"].get("%dQ%d" % (y_d, k), 0.0) for k in range(1, 5))
        payout = r4(last_dps * shares / 1e8 / ni_y) if ni_y > 0 else None
    da_avg = med([S["감가상각비"][q] for q in last_n(S["감가상각비"], 4)]) if S["감가상각비"] else None
    if da_avg is None:
        warnings.append("감가상각비가 face·CF 에 없음(주석 미파싱) → EBITDA·EV/EBITDA 미산출")
    one_offs_detected = _detect_one_offs(S, all_q)
    _adjusted_eps(one_offs_detected, S, rows, all_q, tax_rate, minority)          # 조정EPS 행(의심 회사만) + 산식 필드
    for o in one_offs_detected:
        ratio_txt = ("영업이익 %s억의 %.0f배" % (format(round(o["op"]), ",d"), abs(o["nonop"]) / abs(o["op"]))) if o["op"] else "영업이익 0"
        adj_txt = (" · 조정EPS %s원(보고 %s원; 초과 비영업손익 %s억 × (1 − 세율 %.1f%%) × 지배 비중 %.2f = %s억 차감 — 추정, 조정EPS 행)"
                   % (format(o["eps_adj"], ",.1f"), format(o["eps_reported"], ",.1f"), format(round(o["excess_nonop"]), ",d"), o["tax_rate_applied"] * 100,
                      o["ctrl_share_applied"], format(round(o["excess_after_tax"] * o["ctrl_share_applied"]), ",d"))) if _num(o.get("eps_adj")) else " · 조정EPS 미산출(유통주식수 없음)"
        warnings.append("일회성 의심 %s: 비영업손익 %+s억(%s, 12분기 중위 %s억·기준선 %+s억) → 지배NI %s억·보고 EPS·FY%s 합계·TTM PER 에 그대로 포함 — 처분이익 등 일회성 여부는 주석 확인 전까지 미확정(12M fwd EPS 에는 미포함)%s"
                        % (o["q"], format(round(o["nonop"]), ",d"), ratio_txt, format(round(o["median_abs_nonop_12q"]), ",d"), format(round(o.get("baseline_nonop_12q") or 0.0), ",d"),
                           format(round(o["ni_ctrl"]), ",d") if _num(o["ni_ctrl"]) else "—", o["q"][:4], adj_txt))
    # BS 롤의 현금 근사: FCF ≈ 순이익 + 감가상각비 − CAPEX(둘 다 최근 4분기 중위) — 감가상각비가 없으면 CAPEX≈감가 가정으로 순이익만
    capex_ks = last_n(S["CAPEX"], 4) if S.get("CAPEX") else []
    capex_avg = abs(med([S["CAPEX"][q] for q in capex_ks])) if capex_ks else None
    fcf_full = da_avg is not None and capex_avg is not None
    fcf_txt = ("순이익 + 감가상각비 %.0f억 − CAPEX %.0f억(각 최근 4분기 중위) − 배당" % (da_avg, capex_avg)) if fcf_full else \
              ("순이익 − 배당(감가상각비 없음 → CAPEX≈감가 가정%s)" % ((", CAPEX 중위 %.0f억은 행에만" % capex_avg) if capex_avg is not None else ""))
    # 환관련손익: 공시 외화 순노출(yards_cache fx) × Δ기말환율
    exposure = _fx_exposure_usd_m(stock, la, ctx) if stock in YARDS else None
    fx_by_q = {}
    fx_assump = {"USDKRW_avg": {}, "USDKRW_end": {}, "basis": (ctx.fx.get("forward") or {}).get("note") or "fx.json forward(flat_last_end)"}
    for q in fq:
        a, _ = ctx.fx_q(q, "USDKRW_avg")
        e, _ = ctx.fx_q(q, "USDKRW_end")
        if a is not None:
            fx_assump["USDKRW_avg"][q] = a
        if e is not None:
            fx_assump["USDKRW_end"][q] = e
    if exposure is not None and not freeze:
        prev_e, _ = ctx.fx_q(la, "USDKRW_end")
        for q in fq:
            e = fx_assump["USDKRW_end"].get(q)
            fx_by_q[q] = r2(exposure * (e - prev_e) / 100.0) if (e is not None and prev_e is not None) else 0.0   # 백만$ × 원 = 백만원 → 억원
            prev_e = e if e is not None else prev_e
    fx_pnl = {"net_usd_exposure_m": r2(exposure), "method": "외화 순노출 × Δ기말환율 (외화 시트 방식)", "by_q": fx_by_q,
              "note": ("정기보고서 환위험 표 '순 노출' USD(%s) 기준 — 헤지회계(OCI) 반영분은 알 수 없어 전액 손익 가정" % la) if exposure is not None
              else "외화 순노출 미공시(face) → 0 + 표기"}

    # ── 추정 구간(순차) ──
    eq_t, ctrl_t = S["자본총계"].get(la), S["지배주주지분"].get(la)
    liab_t, debt_t = S["부채총계"].get(la), S["총차입금"].get(la)
    nd_t, ia_t = S["순차입금"].get(la), S["이자발생자산"].get(la)
    ia_prev, debt_prev = ia_t, debt_t
    has_rate = r_asset is not None or r_debt is not None
    oth_v, oth_b = 0.0, "잔차 실측 %d분기 < %d → 0" % (len(S["기타금융손익"]), FIN_OTHER_MIN_Q)
    if has_rate and oth_med is not None:
        int0 = ((ia_t or 0.0) * (r_asset or 0.0) - (debt_t or 0.0) * (r_debt or 0.0)) / 4
        if abs(oth_med) > FIN_OTHER_CAP * abs(int0):
            oth_b = "최근 %d분기 중위 %+.2f억이 이자손익 추정 %+.2f억의 %d%% 초과 → 0(경고)" % (len(oth_ks), oth_med, int0, FIN_OTHER_CAP * 100)
            warnings.append("기타금융손익(금융손익 − 이자%s − 파생 잔차) 최근 %d분기 중위 %+.1f억이 이자손익 추정 %+.1f억의 %d%% 초과 → 추정 0 — 평가손익·재분류 여부는 주석 확인"
                            % ("" if S["_fx_in_other_nonop"] else " − 외환", len(oth_ks), oth_med, int0, FIN_OTHER_CAP * 100))
        else:
            oth_v, oth_b = oth_med, "최근 %d분기(%s~%s) 잔차 중위" % (len(oth_ks), oth_ks[0], oth_ks[-1])
    for q in fq:
        if q not in plan["rev"]:
            continue
        rev, rev_b = plan["rev"][q]
        opm, opm_b = plan["opm"][q]
        op = rev * opm
        sga = rev * sga_ratio
        oth_op = 0.0
        gp = op + sga + oth_op
        rows["매출액"][q] = est(rev, rev_b)
        rows["OPM"][q] = {"v": r4(opm), "kind": "estimate", "basis": opm_b}
        rows["영업이익"][q] = est(op, "매출액 × OPM(%s)" % opm_b)
        rows["판관비"][q] = est(sga, "매출액 × 판관비율 %.2f%%(최근 %d분기 중위)" % (sga_ratio * 100, len(k4)))
        if S["기타영업손익"]:
            rows["기타영업손익"][q] = est(0.0, "기타영업손익 0 가정")
        rows["매출총이익"][q] = est(gp, "영업이익 + 판관비 − 기타영업손익(항등식)")
        rows["매출원가"][q] = est(rev - gp, "매출액 − 매출총이익(항등식)")
        # 영업외
        if has_rate:
            ia_avg = ia_prev if ia_prev is not None else 0.0
            int_v = (ia_avg * (r_asset or 0.0) - (debt_prev or 0.0) * (r_debt or 0.0)) / 4
            int_b = "이자발생자산 %.0f억 × %.2f%%(%s) − 총차입금 %.0f억 × %.2f%%(%s) (연율) ÷ 4" % (
                ia_avg, (r_asset or 0.0) * 100, r_asset_src or "없음", debt_prev or 0.0, (r_debt or 0.0) * 100, r_debt_src or "없음")
            rows["이자손익"][q] = est(int_v, int_b)
            if S["외환손익"]:
                rows["외환손익"][q] = est(0.0, "외환차손익·외화환산손익 0 가정 — 추정 구간 환율 효과는 조선사 환관련손익 행(공시 노출 × Δ기말환율)에만 둔다(이중 계상 방지)")
            if S["파생상품손익"]:
                rows["파생상품손익"][q] = est(0.0, "파생상품 평가·거래손익 0 가정")
            if S["기타금융손익"]:
                rows["기타금융손익"][q] = est(oth_v, oth_b)
            fin_v = int_v + oth_v          # 반올림 전 합 — 셀 반올림 차 ≤0.01억(허용 0.05), 주석 없는 회사는 기존 값과 바이트 동일
            fin_b = "이자손익 + %s파생상품손익 0 + 기타금융손익 %+.2f억(%s) (항등식); 이자손익 = %s; 환율 효과는 환관련손익 행 별도" % (
                "" if (S["_fx_in_other_nonop"] and not S["외환손익"]) else "외환손익 0 + ", oth_v, oth_b, int_b)
        else:
            fin_v, fin_b = (fin_med or 0.0), "이자 주석·CF 없음 → 최근 4분기 금융손익 중위 유지"
        rows["금융손익"][q] = est(fin_v, fin_b)
        rows["기타영업외손익"][q] = est(0.0, "일회성 미가정 → 0")
        eqm = 0.0
        if S["지분법손익"]:
            eqm = eq_med or 0.0
            rows["지분법손익"][q] = est(eqm, "최근 4분기 중위")
        fxv = fx_by_q.get(q, 0.0) if fx_by_q else 0.0
        if fx_by_q:
            rows["환관련손익"][q] = est(fxv, "외화 순노출 %.0f백만$ × Δ기말 원/달러(%s) — 실적 외환손익(금융손익 안)과 별개, 추정 외환손익은 0" % (exposure, fx_assump["basis"]))
        pretax = op + fin_v + 0.0 + eqm + fxv
        rate_q = tax_sched.get(q, tax_rate)
        tax = max(pretax, 0.0) * rate_q
        ni = pretax - tax
        ctrl = ni * (1 - minority)
        rows["세전이익"][q] = est(pretax, "영업이익 + 금융손익 + 기타영업외 + 지분법 + 환관련(항등식)")
        rows["법인세비용"][q] = est(tax, ("max(세전, 0) × 세율 %.1f%%(이월결손 경로 %s — %s)" % (rate_q * 100, tax_cf["stage"][q], tax_basis)) if tax_cf
                                    else "max(세전, 0) × 세율 %.1f%%(%s)" % (tax_rate * 100, tax_basis))
        rows["당기순이익"][q] = est(ni, "세전이익 − 법인세비용(항등식)")
        rows["지배주주순이익"][q] = est(ctrl, "당기순이익 × (1 − 비지배 비중 %.1f%%, 최근 8분기 실측)" % (minority * 100))
        if da_avg is not None:
            rows["감가상각비"][q] = est(da_avg, "최근 4분기 감가상각비 중위 유지")
            rows["EBITDA"][q] = est(op + da_avg, "영업이익 + 감가상각비")
        if capex_avg is not None:
            rows["CAPEX"][q] = est(capex_avg, "최근 %d분기(%s~%s) CAPEX 중위 유지 — 순차입금 롤에 %s" % (
                len(capex_ks), capex_ks[0], capex_ks[-1], "반영(FCF 근사)" if fcf_full else "미반영(감가상각비 없음 → CAPEX≈감가 가정)"))
        # 배당(Q2 지급 가정) · 자본 롤
        div = (last_dps * shares / 1e8) if (shares and q.endswith("Q2")) else 0.0
        cash_delta = ni - div + ((da_avg - capex_avg) if fcf_full else 0.0)        # FCF 근사(운전자본 불변)
        if shares:
            rows["주식수"][q] = {"v": (shares / 1e6 if ev["post"] else round(shares / 1e6, 3)), "kind": "estimate", "basis": "유통주식수 유지 — %s" % shares_src}
            rows["EPS"][q] = {"v": round(ctrl * 1e8 / shares, 1), "kind": "estimate", "basis": "지배주주순이익 ÷ 유통주식수"}
            if q.endswith("Q4"):
                rows["DPS"][q] = {"v": float(last_dps), "kind": "estimate", "basis": "직전 결산 DPS %s 유지" % last_dps_txt}
        if eq_t is not None:
            eq_t = eq_t + ni - div
            rows["자본총계"][q] = est(eq_t, "전분기 + 당기순이익 − 배당(Q2 지급 가정)")
        if ctrl_t is not None:
            ctrl_t = ctrl_t + ctrl - div
            rows["지배주주지분"][q] = est(ctrl_t, "전분기 + 지배주주순이익 − 배당")
            if shares:
                rows["BPS"][q] = {"v": round(ctrl_t * 1e8 / shares, 1), "kind": "estimate", "basis": "지배주주지분 ÷ 유통주식수"}
        if liab_t is not None:
            rows["부채총계"][q] = est(liab_t, "마지막 실적 유지(가정)")
            if eq_t is not None:
                rows["자산총계"][q] = est(liab_t + eq_t, "부채총계 + 자본총계(항등식)")
        if debt_t is not None:
            rows["총차입금"][q] = est(debt_t, "마지막 실적 유지(가정)")
        if nd_t is not None:
            nd_t = nd_t - cash_delta
            rows["순차입금"][q] = est(nd_t, "전분기 − FCF 근사[%s] (운전자본 불변·총차입금 유지 가정 → 변동은 전부 현금)" % fcf_txt)
        if ia_t is not None:
            ia_t = ia_t + cash_delta
            rows["이자발생자산"][q] = est(ia_t, "전분기 + FCF 근사 — 순차입금 롤과 같은 가정")
            ia_prev = ia_t
    if rows["조정EPS"]:                                   # 일회성 의심 회사만 행이 있다 — 추정 구간은 일회성 미가정이라 EPS 와 같다
        for q in fq:
            if q in rows["EPS"]:
                rows["조정EPS"][q] = est(rows["EPS"][q]["v"], "= EPS(추정 구간은 일회성 미가정)")
    # T6 D6: 추정 금융손익(이자 + 기타금융, 외환·파생 0 가정)이 최근 4분기 실적 중위와 크게 다르면(|차| > 50%) 단절을 수치로 경고 — 값은 바꾸지 않는다.
    # T4 세부 행(이자·외환·파생·기타금융)은 그대로 두고, 그 합인 금융손익 행만 실적 중위와 비교한다.
    fin_gap = None
    fin_ks = last_n(S["금융손익"], 4)
    fin_est = [(q, rows["금융손익"][q]["v"]) for q in fq if q in rows["금융손익"] and _num(rows["금융손익"][q].get("v"))]
    if fin_med is not None and fin_est and abs(fin_med) > 0:
        q0, v0 = fin_est[0]
        gap = v0 - fin_med
        fin_gap = {"actual_median_4q": r2(fin_med), "actual_quarters": fin_ks, "actual_values": {q: r2(S["금융손익"][q]) for q in fin_ks},
                   "first_estimate_q": q0, "first_estimate": r2(v0), "diff": r2(gap), "diff_pct": r2(gap / abs(fin_med) * 100),
                   "flagged": abs(gap) > 0.5 * abs(fin_med),
                   "basis": "추정 금융손익(첫 추정 분기) − 최근 %d분기 실적 중위; |차| > 실적 중위의 50%% 면 경고(값 불변)" % len(fin_ks)}
        if fin_gap["flagged"]:
            warnings.append("금융손익 실적→추정 단절: 최근 %d분기 실적 %s(중위 %+.0f억) → 추정 %s %+.0f억(차 %+.0f억, %+.0f%%) — 추정은 이자손익 + 기타금융 중위, "
                            "외환·파생 평가손익 0 가정(환율 효과는 환관련손익 행). 값은 바꾸지 않음 — 지배NI·EPS 해석 시 참고"
                            % (len(fin_ks), "/".join("%+.0f" % S["금융손익"][q] for q in fin_ks), fin_med, q0, v0, gap, gap / abs(fin_med) * 100))
    for key, cells in plan.get("extra_rows", {}).items():
        rows[key] = cells
    # 사업부 행 라벨은 이 모델의 세그먼트 라벨로 — 모듈 전역 ROW_META 를 고치면 한 프로세스에서 먼저 만든 회사의 라벨(삼성重 '조선해양')이
    # 같은 key 를 쓰는 다음 회사(한화오션 '조선·해양플랜트')에 새어 들어가 빌드 순서에 따라 바이트가 달라진다 → 모델별 사본
    row_meta = dict(ROW_META)
    for seg in plan["segments"]:
        for pre in ("매출", "OP"):
            k = pre + seg["key"]
            row_meta.setdefault(k, ("%s %s" % (pre, seg["label"]), "사업부", "억원"))
    for k, meta in (plan.get("row_labels") or {}).items():          # 세그먼트가 아닌 보조 행(매출조선신규 등) 라벨
        row_meta.setdefault(k, tuple(meta))
    # ── 시나리오(결정 ⓓ): 보수/기준/낙관 신규수주 매출을 행(base 포함)과 별도로 매출액·영업이익 분기·FY 로 — 합산은 base 만 ──
    scenarios = _build_scenarios(rows, plan, fq, la) if plan.get("scenarios_new") else None

    # ── 시세·PER/PBR ──
    price = ctx.price(stock) if not freeze else None
    close = (price or {}).get("close")
    hist = (price or {}).get("history_quarterly") or {}
    eps_q = {q: c["v"] for q, c in rows["EPS"].items() if _num(c.get("v"))}
    ttm = {}
    for q in quarters:
        ks = [q_add(q, -i) for i in range(4)]
        if all(k in eps_q for k in ks):
            ttm[q] = sum(eps_q[k] for k in ks)
    for q in quarters:
        bps = (rows["BPS"].get(q) or {}).get("v")
        is_act = q <= la
        px = (hist.get(q) or {}).get("avg") if is_act else close
        if not _num(px):
            continue
        src = "토스 일봉 분기 평균 ÷ TTM EPS" if is_act else "현재 종가 ÷ TTM EPS(추정 포함)"
        if _num(ttm.get(q)) and ttm[q] > 0:
            rows["PER"][q] = {"v": round(px / ttm[q], 2), "kind": "actual" if is_act else "estimate", ("src" if is_act else "basis"): src}
        if _num(bps) and bps > 0:
            rows["PBR"][q] = {"v": round(px / bps, 2), "kind": "actual" if is_act else "estimate", ("src" if is_act else "basis"): src.replace("TTM EPS", "BPS")}

    # ── 연간 ──
    annual_years = [str(y) for y in range(max(FY_FIRST, q_year(fin.first)), FY_LAST + 1)]
    out_rows = []
    for key in list(rows):
        cells = rows[key]
        if not cells:
            continue
        label, group, unit = row_meta.get(key, (key, "기타", "억원"))
        a = {}
        for y in annual_years:
            ks = ["%sQ%d" % (y, k) for k in range(1, 5)]
            have = [k for k in ks if k in cells and _num(cells[k].get("v"))]
            kinds = {cells[k]["kind"] for k in have}
            kind = "actual" if kinds == {"actual"} else ("estimate" if kinds == {"estimate"} else "mixed")
            if key in ("OPM",):
                rv, op = rows["매출액"], rows["영업이익"]
                if all(k in rv and k in op for k in ks):
                    sr, so = sum(rv[k]["v"] for k in ks), sum(op[k]["v"] for k in ks)
                    a[y] = {"v": r4(so / sr) if sr else None, "kind": kind}
            elif key in ("PER", "PBR"):
                den = rows["EPS" if key == "PER" else "BPS"]
                if key == "PER":
                    dv = sum(den[k]["v"] for k in ks) if all(k in den for k in ks) else None
                else:
                    dv = den.get(ks[-1], {}).get("v")
                px = (hist.get(ks[-1]) or {}).get("close_end") if int(y) < q_year(la) or (int(y) == q_year(la) and la.endswith("Q4")) else close
                if _num(dv) and dv > 0 and _num(px):
                    a[y] = {"v": round(px / dv, 2), "kind": "actual" if int(y) < q_year(la) else "estimate"}
            elif key in STOCK_KEYS or group == "재무상태":
                if ks[-1] in cells:
                    a[y] = {"v": cells[ks[-1]]["v"], "kind": cells[ks[-1]]["kind"]}
            elif key == "DPS":
                if ks[-1] in cells:
                    a[y] = {"v": cells[ks[-1]]["v"], "kind": cells[ks[-1]]["kind"]}
            else:
                if len(have) == 4:
                    a[y] = {"v": r2(sum(cells[k]["v"] for k in ks)), "kind": kind}
                elif have:
                    a[y] = {"v": None, "kind": "partial", "note": "%d분기만 있음" % len(have)}
        out_rows.append({"key": key, "label": label, "group": group, "unit": unit, "q": dict(sorted(cells.items())), "a": a})
    rm = {r["key"]: r for r in out_rows}

    # ── 항등식 검사 ──
    ident = _check_identities(rm, all_q, fq)
    identities_ok = ident["estimate_fail"] == 0 and ident["actual_fail_major"] == 0
    if ident["actual_fail"]:
        warnings.append("실적 구간 항등식 불일치 %d건(허용 1억 초과; face 재분류·반올림): %s" % (
            ident["actual_fail"], "; ".join("%s %s Δ%.1f" % (x["q"], x["rule"], x["diff"]) for x in ident["mismatches"][:4])))

    # ── 밸류에이션 ──
    valuation = None if freeze else _valuation(rm, price, close, hist, la, fq, shares, da_avg)

    # ── 백테스트 ──
    backtest = {"freeze": FREEZE_Q, "horizon": BACKTEST_H, "revenue_wape_pct": None, "op_wape_pct": None, "n": 0,
                "note": "단일 회사 4분기 — 통계 아님"}
    if not freeze and la > FREEZE_Q and FREEZE_Q in fin.quarters:
        bm = ctx.model(stock, origin=FREEZE_Q)
        if bm and bm.get("rows"):
            brm = {r["key"]: r for r in bm["rows"]}
            pairs = []      # (q, rev_pred, rev_act, op_pred, op_act) — 실측(kind actual) 셀만. 추정 vs 추정은 비교가 아니다
            for i in range(1, BACKTEST_H + 1):
                q = q_add(FREEZE_Q, i)
                ca, co = rm["매출액"]["q"].get(q) or {}, rm["영업이익"]["q"].get(q) or {}
                pr, po = (brm["매출액"]["q"].get(q) or {}).get("v"), (brm["영업이익"]["q"].get(q) or {}).get("v")
                if _num(pr) and ca.get("kind") == "actual" and _num(ca.get("v")):
                    pairs.append((q, pr, ca["v"], po, co.get("v") if co.get("kind") == "actual" else None))
            bdrv = ((bm.get("segments") or [{}])[0].get("driver") or {}) if bm.get("segments") else {}
            boos = bdrv.get("selection_oos")
            backtest.update({"revenue_wape_pct": wape([(p[1], p[2]) for p in pairs]), "op_wape_pct": wape([(p[3], p[4]) for p in pairs]), "n": len(pairs),
                             "driver_at_freeze": bdrv.get("type") or bm.get("driver_type"),
                             "selection_oos_at_freeze": ({k: boos.get(k) for k in ("freeze", "n", "wape_link", "wape_trend", "adopted", "decision", "note") if k in boos} if boos else None),
                             "frozen_inputs": "fin(연결/별도)·고객 조선사 모델·지주 자회사 모델은 %s 까지의 분기만; 선표는 체결일 ≤ %s 말일 계약(원장 최신 금액·코호트 등급, 환산 없음); "
                                              "잔고는 yards_cache %s; 시세·환율 forward·prices·forecast_panel 신규수주 미사용. 고객 가중치(suppliers.json 언급 비중)와 합병 체인링크는 현재 지식; "
                                              "고객 연동 채택은 동결 모델 안에서도 자기 la−4분기 OOS 규칙(selection_oos_at_freeze)" % (FREEZE_Q, FREEZE_Q, FREEZE_Q),
                             "detail": [{"q": q, "rev_pred": r2(pr), "rev_act": r2(ar), "op_pred": r2(po), "op_act": r2(ao)} for q, pr, ar, po, ao in pairs]})
            if len(pairs) < BACKTEST_H:
                backtest["note"] = "실측 %d분기만 비교(나머지는 실적 없음 — 추정 vs 추정은 세지 않음) · 단일 회사 — 통계 아님" % len(pairs)
    elif not freeze:
        backtest["note"] = "freeze %s 이후 실적 분기 없음 → 백테스트 없음" % FREEZE_Q

    # ── 요약·품질 ──
    n_est_rev = sum(1 for q in fq if q in rm["매출액"]["q"])
    stale = (not freeze) and la < _latest_complete_quarter(ctx, la)
    # T6 D7: status 는 데이터 완전성(fin 분기·항등식·추정 분기 수·별도 보충·최신 분기)으로만 — 드라이버 폴백은 driver_fallback 으로 따로
    status_reasons = []                      # STATUS_RULE 의 조건 중 어긋난 것 — 비어 있으면 full
    if len(fin.quarters) < 8:
        status_reasons.append("fin 분기 %d < 8" % len(fin.quarters))
    if not identities_ok:
        status_reasons.append("항등식 불일치(추정 %d건·실적 major %d건)" % (ident["estimate_fail"], ident["actual_fail_major"]))
    if n_est_rev < FWD_MIN:
        status_reasons.append("추정 매출 분기 %d < %d" % (n_est_rev, FWD_MIN))
    if fin.sep_fill:
        status_reasons.append("연결 손익 공백 %d분기 → 별도 보충" % len(fin.sep_fill))
    driver_fallback = _driver_fallback(plan)
    if stale:
        if stock in MERGERS:
            status_reasons.append("%s 부터 정기보고서 없음(%s 에 합병)" % (MERGERS[stock][1], MERGERS[stock][0]))
            warnings.append("%s 부터 정기보고서 없음(%s 에 합병) — 참고용 모델, 시세 없음" % (MERGERS[stock][1], MERGERS[stock][0]))
        else:
            status_reasons.append("마지막 fin 분기 %s < 최신 완결 분기 %s" % (la, _latest_complete_quarter(ctx, la)))
            warnings.append("마지막 fin 분기 %s < 최신 완결 분기 %s — 최신 보고서 미수집(no_report) 상태의 모델" % (la, _latest_complete_quarter(ctx, la)))
    status = "full" if not status_reasons else "partial"
    ebitda_q = {"available": da_avg is not None,
                "source": ("fin.%s.cf.감가상각비(영업활동 현금흐름 조정 face)" % fin.scope) if da_avg is not None else None,
                "note": ("EBITDA = 영업이익 + 감가상각비(CF face); 무형자산상각비는 더하지 않음(스펙 2-5)" if da_avg is not None else
                         "CF face 에 감가상각비 줄 없음(간접법 '조정' 합계만 → 주석 '현금의 유출이 없는 비용' 표) → EBITDA·EV/EBITDA 미산출; fin 주석 파싱 전까지 공란")}
    quality = {"fin_quarters": len(fin.quarters), "scope": fin.scope, "sep_filled": fin.sep_fill, "missing": missing + ident["missing_rows"], "identities_ok": identities_ok,
               "identity_checks": {k: v for k, v in ident.items() if k != "mismatches" and k != "missing_rows"},
               "identity_mismatches": ident["mismatches"][:20], "warnings": warnings, "status": status,
               "status_rule": STATUS_RULE, "status_reasons": status_reasons, "ebitda": ebitda_q}
    views = None if freeze else _views(rm, all_q, fq, la, annual_years)
    model = collections.OrderedDict([
        ("stock", stock), ("name", name), ("role", role_eff), ("origin", la), ("unit", "KRW_100M(억원)"), ("built_at", ctx.today),
        ("status", status),
        ("driver_fallback", driver_fallback),
        ("periods", {"quarters": quarters, "annual": annual_years, "last_actual": la}),
        ("rows", out_rows),
        ("segments", plan["segments"]),
        ("driver_type", plan["driver"].get("type")),
        ("assumptions", {"fx": fx_assump, "hedge": _hedge_assump(ctx.sls(stock)) if stock in YARDS else None,
                         "sls": ({k: v for k, v in _sls_r3_info(ctx.sls(stock)).items() if k != "backlog_cap_raw"} if (stock in YARDS and ctx.sls(stock)) else None),
                         "tax_rate": r4(tax_rate), "tax_basis": tax_basis, "tax_path": tax_path,
                         "tax_rate_terminal": TAX_DEFAULT if tax_cf else None,
                         "tax_schedule": {q: r4(v) for q, v in tax_sched.items()} if tax_cf else None,
                         "tax_carryforward": dict(tax_cf["detect"], hold_until=tax_cf["hold_until"], ramp_from=tax_cf["ramp_from"], ramp_to=tax_cf["ramp_to"]) if tax_cf else None,
                         "nol_evidence": nol_evidence, "sga_ratio": r4(sga_ratio),
                         "fin_pl_gap": fin_gap,
                         "interest_rate_debt": r4(r_debt), "interest_rate_asset": r4(r_asset),
                         "interest_rate_source": {"asset": r_asset_src, "debt": r_debt_src},
                         "interest_rate_check": {"asset": r_asset_chk, "debt": r_debt_chk,
                                                 "rule": "주석/CF > %.1f 이면 경고; stale(주석 마지막 분기 ≠ 마지막 실적) 또는 주석 > %.0f%% 이면 CF 연율로 클립 — CF 창(cf_window)이 주석 창 이상으로 최신일 때만, 더 오래되면 상한 초과만 상한으로 클립·그 외 주석 유지(CF 없으면 상한)"
                                                         % (INTEREST_NOTE_CF_MAX_RATIO, INTEREST_RATE_ABS_MAX * 100)},
                         "fx_in_other_nonop": ({"quarters": list(S["_fx_in_other_nonop"]), "n": len(S["_fx_in_other_nonop"]),
                                                "note": "외환차손익은 face 기타영업외손익 안 — 금융 잔차·추정 외환손익 0 가정에서 제외"} if S["_fx_in_other_nonop"] else None),
                         "minority_share": r4(minority),
                         "payout": payout, "dps_assumed": last_dps, "opm_source": plan["driver"].get("type"), "one_offs": [],
                         "bs_roll": {"equity": "자본총계 = 전분기 + 당기순이익 − 배당(Q2 지급 가정); 지배주주지분 = 전분기 + 지배NI − 배당",
                                     "net_debt": "순차입금 = 전분기 − FCF 근사; 이자발생자산 = 전분기 + FCF 근사(총차입금·부채총계는 마지막 실적 유지)",
                                     "fcf_proxy": fcf_txt, "fcf_full": fcf_full, "da_avg": r2(da_avg), "capex_avg": r2(capex_avg), "capex_quarters": capex_ks,
                                     "note": "운전자본(선수금·매출채권) 변동은 모델에 없다 — 조선사 선수금 사이클은 반영 안 됨"},
                         "one_offs_note": "fin face 에서 일회성 분리 불가(주석 미파싱) → 가정 없음; 레퍼런스 일회성 표는 사례",
                         "one_offs_detected": one_offs_detected,
                         "shares": {"latest": shares, "latest_q": shares_q, "latest_src": shares_src, "events": ev["events"], "post_event": ev["post"],
                                    "restated_quarters": [q for q, f in ev["factors"].items() if f != 1.0],
                                    "dps_restated": ({str(y): {"fin": dps[y], "restated": round(dps[y] / dps_f[y], 2), "ratio": _ratio_txt(dps_f[y])} for y in sorted(dps) if dps_f[y] != 1.0} or None),
                                    "rule": "실적 분기 주식수·EPS/BPS/DPS 는 당시 주식수 × 이후 병합·분할·무상증자 비율 누적곱(IAS 33.64 비교표시, 네이버 수정주가 이력과 정합; 셀 kind estimate); "
                                            "추정 분기·PER/PBR now·EV 는 사건 반영 최신 유통주식수(aik 상장주식수 = 발행주식수 − 자기주식); 증자·IPO·소각은 환산 없이 최신 주식수만. "
                                            "prices.history_quarterly 가 수정주가(close_rule)인 동안만 옳다"}}),
        ("fx_pnl", fx_pnl),
        ("valuation", valuation),
        ("consolidation", plan["consolidation"] or {"method": "consolidated_direct" if fin.scope == "cons" else "separate_only", "subsidiaries": []}),
        ("modules", plan["modules"]),
        ("new_orders_included", plan["driver"].get("new_orders_included")),
        ("new_orders", plan["driver"].get("new_orders")),
        ("scenarios", scenarios),
        ("backtest", backtest),
        ("views", views),
        ("quality", quality),
    ])
    return model


DRIVER_FALLBACKS = ("corr", "significance", "n", "oos", "eligibility", "no_link", "none")


def _driver_fallback(plan):
    """드라이버 폴백 사유(T6 D7): 고객 연동 기각 사유(corr|significance|n|oos|eligibility — 라운드 7 L5 후보 자격 미달) · 그 밖의 추세 폴백(no_link — 고객 연결·선표·자회사 없음 등) · none."""
    if not plan.get("fallback"):
        return "none"
    rb = ((plan.get("driver") or {}).get("customer_link_rejected") or {}).get("rejected_by")
    return rb if rb in DRIVER_FALLBACKS else "no_link"


def _build_scenarios(rows, plan, fq, la):
    """시나리오 블록(결정 ⓓ): plan.scenarios_new = {scn: {q: 신규수주 매출 억원}}(base 포함). 각 시나리오 매출 = 행 매출액(base 포함) − base 신규 + 그 시나리오 신규,
    영업이익 = 행 영업이익 + (시나리오 신규 − base 신규) × 반올림 전 OPM(plan.opm — 타겟 경로; 신규분에도 같은 타겟). existing_only 는 신규 0. FY 는 실적 분기(actual) + 추정 분기 합 — 4분기가 다 있어야 값.
    행(rows)에는 base 만 들어 있고 보수/낙관은 여기에만 있다(합산 안 함)."""
    new = plan["scenarios_new"]
    base_new = new.get(PANEL_BASE) or {}
    rev_q = {q: rows["매출액"][q]["v"] for q in fq if q in rows["매출액"] and _num(rows["매출액"][q].get("v"))}
    op_q = {q: rows["영업이익"][q]["v"] for q in fq if q in rows["영업이익"] and _num(rows["영업이익"][q].get("v"))}
    # T6 D9: 시나리오 OP 델타는 반올림 전 OPM(plan.opm) — 행 OPM 셀(4자리 반올림)을 쓰면 보수·낙관 OP 가 약 2억 어긋난다
    opm_q = {q: plan["opm"][q][0] for q in fq if q in plan.get("opm", {}) and _num(plan["opm"][q][0])}
    years = [y for y in sorted({q_year(q) for q in fq} | {q_year(la)}) if y <= FY_LAST]
    out = collections.OrderedDict()
    out["meta"] = dict(plan.get("scenarios_meta") or {}, unit="KRW_100M(억원)", fiscal_years=[str(y) for y in years],
                       cases=["existing_only"] + list(PANEL_SCENARIOS), in_rows=PANEL_BASE,
                       note="매출 = 기존(선표+잔고 소진+기타) + 시나리오 신규수주 매출; 영업이익 = 행 영업이익 + (시나리오 신규 − base 신규) × base OPM 경로. "
                            "보수/낙관·existing_only 는 행에 합산하지 않음(base 는 행과 동일). %s" % NOTE_NO_TP)
    for scn in ["existing_only"] + list(PANEL_SCENARIOS):
        ns = {} if scn == "existing_only" else (new.get(scn) or {})
        qd = collections.OrderedDict()
        for q in fq:
            if q not in rev_q or q not in opm_q or q not in op_q:
                continue
            n_s, n_b = ns.get(q, 0.0), base_new.get(q, 0.0)
            rv = rev_q[q] - n_b + n_s
            qd[q] = {"rev": r2(rv), "op": r2(op_q[q] + (n_s - n_b) * opm_q[q]), "new_order_revenue": r2(n_s), "kind": "estimate"}
        ann = collections.OrderedDict()
        for y in years:
            ks = ["%dQ%d" % (y, k) for k in range(1, 5)]
            rv = op = no = 0.0
            ok, kinds = True, set()
            for k in ks:
                if k in qd:
                    rv += qd[k]["rev"]
                    op += qd[k]["op"]
                    no += qd[k]["new_order_revenue"]
                    kinds.add("estimate")
                elif k in rows["매출액"] and k in rows["영업이익"] and rows["매출액"][k].get("kind") == "actual" and _num(rows["매출액"][k].get("v")) and _num(rows["영업이익"][k].get("v")):
                    rv += rows["매출액"][k]["v"]
                    op += rows["영업이익"][k]["v"]
                    kinds.add("actual")
                else:
                    ok = False
            if ok:
                ann[str(y)] = {"rev": r2(rv), "op": r2(op), "opm": r4(op / rv) if rv else None, "new_order_revenue": r2(no),
                               "kind": "estimate" if kinds == {"estimate"} else "mixed"}
        out[scn] = {"in_rows": scn == PANEL_BASE, "quarterly": qd, "annual": ann}
    return out


REPORT_LAG_DAYS = {1: 45, 2: 45, 3: 45, 4: 90}   # 분기·반기보고서 45일, 사업보고서 90일(자본시장법 제출기한) — 그 전엔 '미수집'이 아니다


def _latest_complete_quarter(ctx, default):
    """정기보고서가 **제출기한을 지나** 나와 있어야 할 최신 분기 — fx.json 의 완결 분기 중 분기말 + 제출기한(45/90일)이 기준일을 넘지 않은 것.

    2026-10-02 기준이면 2026Q3 는 분기가 끝났어도 보고서 기한(11/14)이 안 됐으니 2026Q2 가 답이다. 전에는 '달력상 끝난 분기'를 썼고
    10/1 이후 58사 전부가 '최신 보고서 미수집' partial 로 바뀌었다(T6 통합 때 발견)."""
    today = getattr(ctx, "today", None)
    try:
        tday = datetime.date.fromisoformat(str(today)[:10]) if today else datetime.date.today()
    except ValueError:
        tday = datetime.date.today()
    best = None
    for q, d in (ctx.fx.get("quarters") or {}).items():
        if d.get("partial"):
            continue
        y, n = int(q[:4]), int(q[5])
        qend = datetime.date(y + (n == 4), 1 if n == 4 else n * 3 + 1, 1) - datetime.timedelta(days=1)
        if qend + datetime.timedelta(days=REPORT_LAG_DAYS[n]) <= tday and (best is None or q > best):
            best = q
    return best or default


def _hedge_assump(sls):
    if not sls:
        return None
    h = sls.get("hedge") or {}
    return {"ratio": h.get("hedge_ratio"), "rate": h.get("hedge_rate"), "kind": h.get("kind"), "basis": h.get("basis")}


def _check_identities(rm, all_q, fq):
    """매출−원가=GP · GP−판관+기타영업=OP · OP+금융+기타영업외+지분법+환=세전 · 세전−법인세(+중단사업)=NI · 자산=부채+자본.
    추정 구간은 0.05억(셀 값 2자리 반올림), 실적 구간은 1억(face 재분류·반올림) 허용; 실적 불일치가 매출의 1% 를 넘으면 major."""
    def v(k, q):
        return ((rm.get(k) or {}).get("q") or {}).get(q, {}).get("v")
    rules = [
        ("rev-cogs=gp", lambda q: (v("매출액", q), v("매출원가", q), v("매출총이익", q)), lambda a, b, c: a - b - c),
        ("gp-sga+oth=op", lambda q: (v("매출총이익", q), v("판관비", q), v("영업이익", q)), lambda a, b, c, q=None: a - b - c),
        ("pretax-tax=ni", lambda q: (v("세전이익", q), v("법인세비용", q), v("당기순이익", q)), lambda a, b, c: a - b - c),   # 실적은 +중단사업이익
        ("assets=liab+eq", lambda q: (v("자산총계", q), v("부채총계", q), v("자본총계", q)), lambda a, b, c: a - b - c),
    ]
    out = {"estimate_checked": 0, "estimate_fail": 0, "actual_checked": 0, "actual_fail": 0, "actual_fail_major": 0, "mismatches": [], "missing_rows": []}
    for q in all_q + fq:
        is_est = q in fq
        for name, get, f in rules:
            a, b, c = get(q)
            if not all(_num(x) for x in (a, b, c)):
                continue
            d = f(a, b, c)
            if name == "gp-sga+oth=op":
                d += (v("기타영업손익", q) or 0.0)
            if name == "pretax-tax=ni" and not is_est:
                d += (v("중단사업이익", q) or 0.0)
            tol = EST_TOL if is_est else 1.0
            out["estimate_checked" if is_est else "actual_checked"] += 1
            if abs(d) > tol:
                out["estimate_fail" if is_est else "actual_fail"] += 1
                rev = v("매출액", q) or 0.0
                if not is_est and abs(d) > max(1.0, abs(rev) * 0.01):
                    out["actual_fail_major"] += 1
                out["mismatches"].append({"q": q, "rule": name, "diff": round(d, 2), "kind": "estimate" if is_est else "actual"})
        # 세전 사슬(추정 구간만 — 실적 face 는 기타 항목이 더 있다)
        if is_est:
            parts = [v("영업이익", q), v("금융손익", q), v("기타영업외손익", q), v("지분법손익", q) or 0.0, v("환관련손익", q) or 0.0]
            pt = v("세전이익", q)
            if all(_num(x) for x in parts[:3]) and _num(pt):
                d = sum(parts) - pt
                out["estimate_checked"] += 1
                if abs(d) > EST_TOL:
                    out["estimate_fail"] += 1
                    out["mismatches"].append({"q": q, "rule": "op+nonop=pretax", "diff": round(d, 2), "kind": "estimate"})
    for k in ("매출액", "영업이익", "당기순이익", "자산총계"):
        if not (rm.get(k) or {}).get("q"):
            out["missing_rows"].append(k)
    return out


def _valuation(rm, price, close, hist, la, fq, shares, da_avg):
    def v(k, q):
        return ((rm.get(k) or {}).get("q") or {}).get(q, {}).get("v")
    eps_f = [v("EPS", q) for q in fq[:4]]
    eps_fwd = round(sum(eps_f), 1) if all(_num(x) for x in eps_f) else None
    bps = v("BPS", la)
    # 과거 PER 밴드: 분기 평균가 ÷ TTM EPS(>0) 의 25/50/75 백분위
    pers = []
    for q in sorted(hist):
        if q > la:
            continue
        px = hist[q].get("avg")
        ks = [q_add(q, -i) for i in range(4)]
        e = [v("EPS", k) for k in ks]
        if _num(px) and all(_num(x) for x in e) and sum(e) > 0:
            pers.append(px / sum(e))
    hist_raw = None
    if len(pers) >= 4:
        s = sorted(pers)
        lo, mid, hi = s[len(s) // 4], statistics.median(s), s[(3 * len(s)) // 4]
        hist_raw = {"lo": round(lo, 1), "mid": round(mid, 1), "hi": round(hi, 1), "n": len(pers)}
    if hist_raw and PER_BAND_SANE[0] <= hist_raw["mid"] <= PER_BAND_SANE[1]:
        band = dict(hist_raw, basis="hist_quarterly(분기 평균가 ÷ TTM EPS, %d분기, 25/50/75 백분위)" % len(pers))
        # 밴드 상·하한 캡(2026-09-30 오너 결정): 턴어라운드 초기의 TTM EPS 가 작아 분기 PER 30~58배가 찍히면
        # 중위가 sane 구간(3~40) 안이어도 적정가치 구간이 종가의 2~3배로 벌어진다(HD현대重 765,200~1,435,600 vs 442,000).
        # 밴드 값을 PER_BAND_CAP 안으로 자르고 원값은 hist_band_raw 에 남긴다 — 밸류에이션은 어차피 추천이 아니다.
        capped = {k: min(max(band[k], PER_BAND_CAP[0]), PER_BAND_CAP[1]) for k in ("lo", "mid", "hi")}
        if not (PER_BAND_CAP[0] < hist_raw["mid"] < PER_BAND_CAP[1]):
            # 중위까지 캡 밖이면 밴드가 한 점으로 퇴화한다(HD현대重 30/30/30) → 레퍼런스 예시 밴드로 대체하고 원값을 남긴다.
            band = {"lo": SECTOR_PER_BAND[0], "mid": SECTOR_PER_BAND[1], "hi": SECTOR_PER_BAND[2], "band_capped": True, "hist_band_raw": hist_raw,
                    "basis": "sector_default(레퍼런스 TP_PE PB 예시 10/15/20배; 과거 PER 중위 %.1f배가 캡 %g~%g 밖 — 턴어라운드 초기 TTM EPS 왜곡)"
                             % (hist_raw["mid"], PER_BAND_CAP[0], PER_BAND_CAP[1])}
        elif any(capped[k] != band[k] for k in capped):
            band = dict(band, **capped, band_capped=True, hist_band_raw=hist_raw,
                        basis=band["basis"] + " · 캡 %g~%g배 적용(원값 %s/%s/%s)" % (PER_BAND_CAP[0], PER_BAND_CAP[1], hist_raw["lo"], hist_raw["mid"], hist_raw["hi"]))
    else:
        why = ("과거 PER 중위 %.1f배가 %g~%g 밖(턴어라운드 왜곡)" % (hist_raw["mid"], *PER_BAND_SANE)) if hist_raw else ("과거 양(+)EPS 분기 %d개 < 4" % len(pers))
        band = {"lo": SECTOR_PER_BAND[0], "mid": SECTOR_PER_BAND[1], "hi": SECTOR_PER_BAND[2],
                "basis": "sector_default(레퍼런스 TP_PE PB 예시 10/15/20배; %s)" % why, "hist_band_raw": hist_raw}
    per_now = round(close / eps_fwd, 2) if (_num(close) and _num(eps_fwd) and eps_fwd > 0) else None
    pbr_now = round(close / bps, 2) if (_num(close) and _num(bps) and bps > 0) else None
    roe = (eps_fwd / bps) if (_num(eps_fwd) and _num(bps) and bps > 0) else None
    fair_pbr = round(roe / COE, 2) if (_num(roe) and roe > 0) else None
    fv_per = {k: (round(band[k] * eps_fwd, -2) if (_num(eps_fwd) and eps_fwd > 0) else None) for k in ("lo", "mid", "hi")}
    fv_pbr = round(bps * fair_pbr, -2) if (_num(fair_pbr) and _num(bps)) else None
    ev_ebitda = None
    if da_avg is not None and _num(close) and shares:
        eb = [v("EBITDA", q) for q in fq[:4]]
        nd = v("순차입금", la)
        if all(_num(x) for x in eb) and sum(eb) > 0 and _num(nd):
            ev_ebitda = round((close * shares / 1e8 + nd) / sum(eb), 2)
    src = (price or {}).get("close_source")
    src_ko = ("네이버 정규장 종가(aik 확정종가 대조 · aik %s원)" % format((price or {}).get("aik_close"), ",")) if src == "naver_regular_close" and _num((price or {}).get("aik_close")) \
        else ((price or {}).get("source") or "aikstockdata.com(금융위 확정종가 T+1)")
    return {"price": {"close": close, "as_of": (price or {}).get("as_of"), "source": src_ko, "close_source": src},
            "eps_fwd12m": eps_fwd, "eps_fwd_quarters": fq[:4], "bps_latest": bps, "per_now": per_now, "pbr_now": pbr_now, "per_band": band,
            "roe_fwd": r4(roe), "coe": COE, "fair_pbr": fair_pbr, "fair_value_per": fv_per, "fair_value_pbr": fv_pbr, "ev_ebitda": ev_ebitda,
            "note": NOTE_NO_TP, "price_missing": close is None}


def _views(rm, all_q, fq, la, annual_years):
    def cellv(k, q, kind="q"):
        c = ((rm.get(k) or {}).get(kind) or {}).get(q) or {}
        return c.get("v")
    qcols = all_q[-N_ACTUAL_VIEW:] + fq[:N_EST_VIEW]
    keys = [k for k in VIEW_KEYS if k in rm] + [k for k in rm if k.startswith(("매출", "OP")) and k not in VIEW_KEYS
                                                 and k not in ("매출원가", "매출총이익", "OPM", "매출전사", "OP전사")]   # 전사 행은 매출액·영업이익과 중복
    quarterly = [["항목"] + ["%s%s" % (q, "E" if q in fq else "A") for q in qcols]]
    for k in keys:
        quarterly.append([k] + [cellv(k, q) for q in qcols])
    yrs = [y for y in annual_years if int(y) >= 2022]
    annual = [["항목"] + ["%s%s" % (y, "E" if int(y) >= q_year(la) else "A") for y in yrs]]
    for k in keys:
        annual.append([k] + [cellv(k, y, "a") for y in yrs])
    fy = [str(y) for y in range(q_year(la) - 1, FY_LAST + 1)]
    report = [["FY"] + ["%s%s" % (y, "E" if int(y) >= q_year(la) else "A") for y in fy]]
    for k in REPORT_KEYS:
        if k in rm:
            report.append([k] + [cellv(k, y, "a") for y in fy])
    return {"분기": quarterly, "연간예상": annual, "보고서로": report}


# ── summary ──────────────────────────────────────────────────

def summary_row(model):
    rm = {r["key"]: r for r in model.get("rows") or []}
    la = (model.get("periods") or {}).get("last_actual")
    fy = {}
    if la:
        for y in range(q_year(la) - 1, FY_LAST + 1):
            tag = "%d%s" % (y, "E" if y >= q_year(la) else "A")
            def a(k):
                return (((rm.get(k) or {}).get("a") or {}).get(str(y)) or {}).get("v")
            fy[tag] = {"rev": a("매출액"), "op": a("영업이익"), "opm": a("OPM"), "ni_ctrl": a("지배주주순이익"), "eps": a("EPS"), "bps": a("BPS"),
                       "per": a("PER"), "pbr": a("PBR"), "dps": a("DPS"), "eps_adj": a("조정EPS")}
    bt = model.get("backtest") or {}
    seg0 = ((model.get("segments") or [{}])[0].get("driver") or {}) if model.get("segments") else {}
    link = None

    def _oos(d):
        o = d.get("selection_oos") or {}
        return {"wape_link": o.get("wape_link"), "wape_trend": o.get("wape_trend"), "oos_adopted": o.get("adopted"), "oos_decision": o.get("decision"),
                "oos_freeze": o.get("freeze"), "oos_n": o.get("n")}
    if seg0.get("type") == "customer_yard_revenue_weighted":
        link = dict({"adopted": True, "rejected_by": None, "weights_key": seg0.get("weights_key"), "lag_q": seg0.get("lag_q"), "transform": seg0.get("transform"),
                     "window_q": seg0.get("window_q"), "corr": seg0.get("corr"), "n": seg0.get("n")}, **_oos(seg0))
    elif seg0.get("customer_link_rejected"):
        rj = seg0["customer_link_rejected"]
        link = dict({"adopted": False, "rejected_by": rj.get("rejected_by"), "weights_key": rj.get("weights_key"), "lag_q": rj.get("lag_q"), "transform": rj.get("transform"),
                     "window_q": rj.get("window_q"), "corr": rj.get("corr"), "n": rj.get("n")}, **_oos(rj))
    # 시나리오(결정 ⓓ): FY2026E~28E 매출·영업이익 보수/기준/낙관(+existing_only) — 조선사(패널 있음)·지주만, 나머지 None
    sc = model.get("scenarios") or {}
    scen = None
    if sc.get(PANEL_BASE):
        scen = {}
        for y in (sc.get("meta") or {}).get("fiscal_years") or []:
            if la and int(y) >= q_year(la):
                scen["%sE" % y] = {k: {"rev": ((sc.get(k) or {}).get("annual") or {}).get(y, {}).get("rev"),
                                       "op": ((sc.get(k) or {}).get("annual") or {}).get(y, {}).get("op")} for k in ["existing_only"] + list(PANEL_SCENARIOS)}
    return {"stock": model["stock"], "name": model.get("name"), "role": model.get("role"), "status": model.get("status"),
            "status_reasons": (model.get("quality") or {}).get("status_reasons"),
            "one_offs_n": len((model.get("assumptions") or {}).get("one_offs_detected") or []),
            "last_actual": la, "fin_quarters": (model.get("quality") or {}).get("fin_quarters"), "driver": model.get("driver_type"),
            "driver_fallback": model.get("driver_fallback"), "link": link,
            "fy": fy, "per_now": (model.get("valuation") or {}).get("per_now"), "pbr_now": (model.get("valuation") or {}).get("pbr_now"),
            "new_orders_included": model.get("new_orders_included"), "scenarios": scen,
            "new_orders_source": (model.get("new_orders") or {}).get("source_field") if isinstance(model.get("new_orders"), dict) else None,
            "post_origin_mode": ((sc.get("meta") or {}).get("post_origin_mode")),
            "backtest": {"revenue_wape_pct": bt.get("revenue_wape_pct"), "op_wape_pct": bt.get("op_wape_pct"), "n": bt.get("n"),
                         "driver_at_freeze": bt.get("driver_at_freeze")},
            "identities_ok": (model.get("quality") or {}).get("identities_ok"), "warnings_n": len((model.get("quality") or {}).get("warnings") or [])}


def build_all(stocks, ctx, write=True, xlsx=False):
    """의존 순서: 조선사 → 지주 → 나머지(종속사 → 세진). ctx 캐시가 고객 모델을 이어 준다."""
    order = [s for s in YARDS if s in stocks] + ([HOLDING] if HOLDING in stocks else []) + \
            [s for s in stocks if s not in YARDS and s != HOLDING and s != SEJIN] + ([SEJIN] if SEJIN in stocks else [])
    rows, built = [], {}
    for st in order:
        m = ctx.model(st)
        rows.append(summary_row(m))
        if m.get("status") != "no_fin" and write:
            path = os.path.join(MODELS_DIR, st + ".json")
            dump_json(path, m)
            built[st] = path
    rows.sort(key=lambda r: r["stock"])
    counts = collections.Counter(r["status"] for r in rows)
    summary = {"built_at": ctx.today, "origin": max((r["last_actual"] or "") for r in rows) or None, "n": len(rows),
               "counts": {k: counts.get(k, 0) for k in ("full", "partial", "no_fin")}, "unit": "KRW_100M(억원) · EPS/BPS/DPS 원 · PER/PBR 배",
               "note": NOTE_NO_TP, "rows": rows}
    if write:
        os.makedirs(MODELS_DIR, exist_ok=True)
        dump_json(os.path.join(MODELS_DIR, "summary.json"), summary)
    xl = {}
    if xlsx and built:
        import kship_model_xlsx as X      # L5 의 함수 — 시그니처 build_one(model_path, out_path=None, ...)
        for st, path in sorted(built.items()):
            try:
                xl[st] = X.build_one(path)
            except Exception as e:      # noqa: BLE001 — 한 회사 실패가 전체를 막지 않게, 사유는 보고
                xl[st] = {"error": "%s: %s" % (type(e).__name__, e)}
    return summary, built, xl


def report(model):
    rm = {r["key"]: r for r in model.get("rows") or []}
    la = (model.get("periods") or {}).get("last_actual")
    print("%s %s [%s] status=%s last_actual=%s driver=%s" % (model["stock"], model.get("name"), model.get("role"), model.get("status"), la, model.get("driver_type")))
    for k in ("매출액", "영업이익", "OPM", "지배주주순이익", "EPS", "조정EPS", "BPS", "PER", "PBR"):     # 조정EPS 는 일회성 의심 회사만 행이 있다
        r = rm.get(k)
        if not r:
            continue
        a = r.get("a") or {}
        print("  %-10s " % k + " ".join("%s:%s" % (y, a[y].get("v")) for y in sorted(a) if int(y) >= 2025))
    bt = model.get("backtest") or {}
    print("  backtest freeze=%s n=%s rev_wape=%s op_wape=%s driver_at_freeze=%s" % (bt.get("freeze"), bt.get("n"), bt.get("revenue_wape_pct"), bt.get("op_wape_pct"), bt.get("driver_at_freeze")))
    # 결정 ⓓ·ⓘ: 신규수주 포함 여부·시나리오 FY 매출, 고객 연동 OOS 선택
    print("  new_orders_included=%s" % model.get("new_orders_included"), end="")
    no = model.get("new_orders") or {}
    print("  (%s)" % (no.get("note") or no.get("source") or "-"))
    sc = model.get("scenarios") or {}
    if sc.get(PANEL_BASE):
        for scn in ["existing_only"] + list(PANEL_SCENARIOS):
            ann = (sc.get(scn) or {}).get("annual") or {}
            print("  scenario %-13s " % scn + " ".join("%s: rev %s op %s" % (y, ann[y].get("rev"), ann[y].get("op")) for y in sorted(ann)))
    if "매출조선신규" in rm:
        a = rm["매출조선신규"].get("a") or {}
        print("  매출조선신규(FY) " + " ".join("%s:%s" % (y, a[y].get("v")) for y in sorted(a) if a[y].get("v") is not None))
    seg0 = ((model.get("segments") or [{}])[0].get("driver") or {}) if model.get("segments") else {}
    oos = seg0.get("selection_oos") or (seg0.get("customer_link_rejected") or {}).get("selection_oos")
    if oos:
        print("  selection_oos freeze=%s n=%s wape_link=%s wape_trend=%s adopted=%s%s" % (oos.get("freeze"), oos.get("n"), oos.get("wape_link"), oos.get("wape_trend"), oos.get("adopted"),
                                                                                       (" — " + oos["note"]) if oos.get("note") else ""))
    if bt.get("selection_oos_at_freeze"):
        print("  selection_oos_at_freeze=%s" % json.dumps(bt["selection_oos_at_freeze"], ensure_ascii=False))
    q = model.get("quality") or {}
    print("  identities_ok=%s fin_quarters=%s warnings=%d" % (q.get("identities_ok"), q.get("fin_quarters"), len(q.get("warnings") or [])))
    for w in q.get("warnings") or []:
        print("   - " + w)


def main(argv=None):
    ap = argparse.ArgumentParser(description="한국조선 실적 모델 엔진(MODEL_SPEC 2-5)")
    ap.add_argument("--build", action="store_true", help="모델 json 생성(assets/models/<stock>.json + summary.json)")
    ap.add_argument("--stocks", nargs="*", help="대상 종목(기본 --all)")
    ap.add_argument("--all", action="store_true", help="모집단 57 전부(fin 없는 회사는 summary 에 no_fin)")
    ap.add_argument("--xlsx", action="store_true", help="kship_model_xlsx.build_one 으로 models/<stock>_model.xlsx 도 생성")
    ap.add_argument("--report", nargs="*", help="만든 모델 요약 출력(종목)")
    ap.add_argument("--today", help="built_at 고정(YYYY-MM-DD)")
    a = ap.parse_args(argv)
    ctx = Ctx(today=a.today)
    if a.build:
        stocks = a.stocks if (a.stocks and not a.all) else ctx.population()
        summary, built, xl = build_all(stocks, ctx, write=True, xlsx=a.xlsx)
        print("models: %d built · counts %s · summary %s" % (len(built), summary["counts"], os.path.join(MODELS_DIR, "summary.json")))
        for r in summary["rows"]:
            f26 = (r["fy"] or {}).get("2026E") or {}
            lk = r.get("link") or {}
            print("  %s %-12s %-7s %-7s la=%s rev26E=%s op26E=%s eps26E=%s bt=%s/%s new=%s%s" % (
                r["stock"], (r["name"] or "")[:12], r["role"], r["status"], r["last_actual"], f26.get("rev"), f26.get("op"), f26.get("eps"),
                r["backtest"]["revenue_wape_pct"], r["backtest"]["op_wape_pct"], r.get("new_orders_included"),
                (" oos=%s/%s→%s" % (lk.get("wape_link"), lk.get("wape_trend"), "채택" if lk.get("adopted") else "기각(%s)" % lk.get("rejected_by"))) if lk else ""))
        for st, rep in xl.items():
            print("  xlsx %s: %s" % (st, rep.get("error") or "%s %d bytes" % (rep.get("out"), rep.get("size_bytes") or 0)))
        return 0
    if a.report is not None:
        for st in a.report or ctx.population():
            m = load_optional(os.path.join(MODELS_DIR, st + ".json"))
            if m:
                report(m)
            else:
                print("%s: 모델 없음" % st)
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
