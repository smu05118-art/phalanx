#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_model — 한국조선 56사 실적 모델 엔진(MODEL_SPEC 2-5): fin·fx·prices·sls → assets/models/<stock>.json + summary.json.

레퍼런스(사용자 subQ 모델 3개)의 계산 사슬(0-1)을 역할별 전략으로 옮겼다. 실적 구간은 fin(DART 정기보고서)의 값을
**그대로**(kind actual + src) 쓰고, 추정 구간(T+1~2028Q4)은 전부 kind estimate + basis 를 갖는다. 출처 없는 숫자는 없다.

  yard      매출조선 = SLS 해양 원화(assets/sls, 헤지 적용) + 원장 밖 잔고 소진분. 원장(2024~ 척당 계약 공시)은 공시 잔고의
            일부만 덮으므로 (공시 해양 잔고 − 원장 잔여) 를 최근 4분기 '원장 밖 매출'(부문 매출 − SLS) 중위 속도로 소진시킨다.
            공시 잔고를 상한으로 삼아 SLS 모양 증폭(화해 배율 1/ratio 4.8배 같은 것)을 피한다 — 배율 대안값은 driver 에 같이 적는다.
            OPM = SLS 타겟(코호트 표) + 회사 캘리브레이션(최근 4분기 실측 OPM − 타겟 중위). 기타 부문 = 총매출 − 조선 부문 추세.
  holding   (009540) 매출 = HD현대重(329180) 모델 매출 × 실측 연결/자회사 비율(합병 후 분기), OPM = 자회사 OPM + 실측 차이.
  equip·engine·steel  매출 = f(Σ 고객 조선사 매출_(t−lag) × 비중) — 격자 탐색(가중치 후보 × 시차 0~4 × 창 8/12/19 × 변환 수준·YoY·4Q합)에서
            상관 최대 조합을 원점 회귀로 채택(≥0.30), 미달·고객 연결 없음이면 매출 추세 + 계절성(전년동기 × (1+g), g 감쇠). 후보표·유의 임계·
            과적합 경고는 driver.grid 에 남긴다. 세진(075580)은 레퍼런스 `연간예상` 의 weighted(미포 0.9·현중 0.2 계열) 가중치를 후보로 넣고
            종속사 일승·동방선기 모델로 연결을 재구성하며, 풍력/플랜트·LPG·LNG-Fuel 은 modules(레퍼런스 가정, 합산 안 함)로 둔다.
            HD현대미포(010620)는 2025Q4 HD현대重 합병으로 fin 이 끊겨 체인링크로 잇고 그 규칙을 driver.merger_rule 에 적는다.
  공통      판관비율(4분기 중위) · 이자손익(평균 잔액 × CF 실측 이자율) · 환관련손익(공시 외화 순노출 × Δ기말환율, 없으면 0 표기) ·
            법인세율(12분기 유효세율 5~27% 클립) · 비지배 비중(8분기 실측) · 자본 롤(+NI −배당) · EPS/BPS · PER/PBR(과거 밴드) ·
            백테스트(freeze 2025Q2, 4분기 WAPE — 고객·선표도 freeze 시점 정보로 다시 만들고, 실측(kind actual) 분기만 짝을 짓는다).
  보충·표기  연결 손익이 없는 분기는 별도로 보충(quality.sep_filled, 셀 src 표기) · 부문 없는 회사는 '전사' 세그먼트에 드라이버를 남긴다 ·
            비영업손익 급등 분기는 assumptions.one_offs_detected + 경고('일회성 의심', 숫자는 바꾸지 않음).

    python3 kship_model.py --build --stocks 010140 075580     # 두 회사
    python3 kship_model.py --build --all [--xlsx]              # 모집단 57 (fin 없는 회사는 summary 에 no_fin 만)
    python3 kship_model.py --report 010140                     # 만든 모델 요약 출력
"""
import argparse
import collections
import datetime
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
# 양측 5% t 임계값(df = n−2) → r_crit = t/√(df+t²). 표본 4~19 에 해당하는 df 2~17.
T_CRIT_P05 = {2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201,
              12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086}
N_ACTUAL_VIEW, N_EST_VIEW = 8, 10
EST_TOL = 0.05                        # 추정 항등식 허용(억원; 셀 2자리 반올림 3개 합)
PER_BAND_SANE = (3.0, 40.0)           # 과거 PER 중위가 이 밖이면(턴어라운드 왜곡) sector_default
PER_BAND_CAP = (5.0, 30.0)     # 과거 PER 밴드 상·하한 캡(2026-09-30) — 원값은 valuation.per_band.hist_band_raw 에 보존

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
    ("BPS", "BPS", "주당", "원", None),
    ("DPS", "DPS(보통주)", "주당", "원", None),
    ("PER", "PER", "주당", "배", None),
    ("PBR", "PBR", "주당", "배", None),
]
ROW_META = {k: (label, group, unit) for k, label, group, unit, _ in ROW_DEFS}
SRC_DEF = {k: src for k, _, _, _, src in ROW_DEFS if src}          # 행 key → (fin kind, 계정명)
ONE_OFF_MIN_RATIO = 4.0               # 비영업손익 |x| 가 12분기 중위의 4배 이상이고 …
ONE_OFF_TTM_OP_SHARE = 0.5            # … 최근 4분기 |영업이익| 합의 절반 이상이면 '일회성 의심' 표시(숫자는 바꾸지 않음)
FLOW_KEYS = {"매출액", "매출원가", "매출총이익", "판관비", "기타영업손익", "영업이익", "금융손익", "기타영업외손익", "지분법손익",
             "환관련손익", "세전이익", "법인세비용", "당기순이익", "지배주주순이익", "중단사업이익", "감가상각비", "EBITDA", "CAPEX", "영업활동현금흐름", "EPS", "DPS"}
STOCK_KEYS = {"자산총계", "부채총계", "자본총계", "지배주주지분", "총차입금", "순차입금", "이자발생자산", "현금및현금성자산", "주식수", "BPS"}
VIEW_KEYS = ["매출액", "매출원가", "매출총이익", "판관비", "영업이익", "OPM", "금융손익", "기타영업외손익", "세전이익", "법인세비용",
             "당기순이익", "지배주주순이익", "EPS", "BPS", "DPS", "PER", "PBR", "자산총계", "부채총계", "자본총계", "지배주주지분", "총차입금", "순차입금"]
REPORT_KEYS = ["매출액", "영업이익", "OPM", "지배주주순이익", "EPS", "BPS", "DPS", "PER", "PBR"]
NOTE_NO_TP = "모델 산출값 — 목표주가·추천 아님"


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


def wape(pairs):
    """Σ|pred−act| / Σ|act| × 100. pairs = [(pred, act)]."""
    pairs = [(p, a) for p, a in pairs if _num(p) and _num(a)]
    den = sum(abs(a) for _, a in pairs)
    if not pairs or den == 0:
        return None
    return round(sum(abs(p - a) for p, a in pairs) / den * 100, 1)


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


def _panel_module(stock, ctx, fq):
    """forecast_panel(기존 Y+2 수주 추정) 을 참고 모듈로 — 매출 모델을 대체하지 않는다(스펙 1)."""
    c = ctx.panel.get(stock)
    if not c or not (c.get("scenarios") or {}).get("base"):
        return None
    rows = []
    for key, label in (("value", "forecast_panel 매출 추정(base, 참고·합산 안 함)"), ("new_orders", "forecast_panel 신규수주(base)"),
                       ("new_order_revenue", "forecast_panel 신규수주 매출(base)")):
        cells = {}
        for row in c["scenarios"]["base"].get("quarterly") or []:
            q = row.get("quarter")
            if q in fq and _num(row.get(key)):
                cells[q] = est(row[key] / UNIT_DIV, "forecast_panel.json.gz base 시나리오(status %s) — 참고" % c.get("status"))
        if cells:
            rows.append({"key": "panel_" + key, "label": label, "unit": "억원", "q": cells})
    return {"key": "forecast_panel", "label": "기존 Y+2 수주 추정(forecast_panel) — 나란히 표시", "rows": rows} if rows else None


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


def _sls_frozen(sls, freeze):
    """freeze 분기말까지 체결된 해양 계약만으로 SLS 를 다시 만든다(백테스트용). 원화 = 계약금액(수주시점) × 진행 비율(환산 없음).
    반환 (krw_by_q {q: 억원}, remaining_krw_after_freeze 억원, target_opm {q: opm})."""
    fdate = q_end_date(freeze)
    tab = sls.get("cohort_opm_table") or {}
    krw, remain, wsum, wopm = collections.defaultdict(float), 0.0, collections.defaultdict(float), collections.defaultdict(float)
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
            wopm[q] += v * (tab.get(c.get("cohort")) or 0.0)
    topm = {q: (wopm[q] / wsum[q]) for q in wsum if wsum[q] > 0}
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
    for q in seg_act:
        if seg_act[q] > S["매출액"][q] * 1.001:
            p["warnings"].append("%s 조선 부문 매출(%.0f억) > 연결 매출(%.0f억) — 부문표/파서 문제(yards 레인 확인)" % (q, seg_act[q], S["매출액"][q]))
    other_act = {q: max(S["매출액"][q] - seg_act[q], 0.0) for q in seg_act}
    if freeze:
        krw, remaining, topm = _sls_frozen(sls, la)
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
        sls_fwd = {q: ((bq.get(q) or {}).get("marine_hedged_krw_m") or 0.0) / UNIT_DIV for q in fq}
        topm = {q: t.get("opm") for q, t in (sls.get("target_opm") or {}).items() if _num(t.get("opm"))}
        src_note = "sls.by_quarter.marine_hedged_krw_m(헤지 %.0f%% 적용)" % (((bq.get(fq[0]) or {}).get("hedge_ratio") or 0.7) * 100)
    ks = last_n(seg_act, 4)
    if len(ks) < 2 or uncovered is None:
        return strat_trend(stock, S, fq, ctx, origin, reason="부문 매출 실적 %d분기·잔고 %s" % (len(ks), "없음" if uncovered is None else "있음"))
    runoff_rate = med([max(seg_act[q] - sls_hist.get(q, 0.0), 0.0) for q in ks]) or 0.0
    if uncovered <= 0:
        p["warnings"].append("원장 잔여가 공시 잔고를 넘음(커버리지 > 1) → 원장 밖 소진분 0 (sls warnings 참고)")
    remaining_u, seg_est = uncovered, {}
    for q in fq:
        r = min(runoff_rate, remaining_u)
        remaining_u -= r
        seg_est[q] = (sls_fwd[q] + r, "SLS 해양 원화 %.0f억(%s) + 원장 밖 잔고 소진 %.0f억(최근 %d분기 '부문매출−SLS' 중위 %.0f억/분기, 잔여 %.0f억)"
                      % (sls_fwd[q], src_note, r, len(ks), runoff_rate, remaining_u))
    # 기타 부문(총매출 − 조선): 부문표 차분 잡음(반기 누계 정정 등)이 커서 추세 대신 최근 4분기 중위 유지
    oth_med = med([other_act[q] for q in ks]) or 0.0
    oth_rev = {q: oth_med for q in fq}
    oth_basis = {q: "기타 부문(연결 − 조선 부문) 최근 %d분기 중위 %.0f억 유지" % (len(ks), oth_med) for q in fq}
    # OPM: 코호트 타겟 + 회사 캘리브레이션(최근 4분기 실측 OPM − 타겟 중위). 부문 OP 미공시 → 두 부문 같은 OPM.
    opm_act = opm_series(S["매출액"], S["영업이익"])
    diffs = [opm_act[q] - topm[q] for q in last_n(opm_act, 4) if q in topm]
    shift = med(diffs) if diffs else None
    if shift is None:
        shift = 0.0
        p["warnings"].append("SLS 타겟 OPM 과 겹치는 실측 분기 없음 → 캘리브레이션 0")
    last_t = topm.get(max(topm)) if topm else 0.0
    opm_path = {}
    for q in fq:
        t = topm.get(q, last_t) or 0.0
        opm_path[q] = clip(t + shift, *OPM_CLIP)
        p["opm"][q] = (opm_path[q], "SLS 코호트 타겟 %.1f%% + 회사 캘리브레이션 %+.1f%%p(최근 %d분기 실측−타겟 중위)" % (t * 100, shift * 100, len(diffs)))
    rev = {}
    for q in fq:
        rev[q] = (seg_est[q][0] + oth_rev[q], "매출조선 + 매출기타")
    p["rev"] = rev
    rs = sls.get("reconcile_summary") or {}
    p["driver"] = {"type": "sls_marine_plus_uncovered_backlog_runoff", "sls_source": src_note,
                   "uncovered_backlog_at_origin": r2(uncovered), "runoff_per_q": r2(runoff_rate), "runoff_quarters_used": ks,
                   "reconcile_ratio": rs.get("median_ratio_4q"), "backlog_coverage_at_origin": rs.get("backlog_coverage_at_origin"),
                   "scale_alternatives": {"1/median_ratio_4q": r4(1 / rs["median_ratio_4q"]) if _num(rs.get("median_ratio_4q")) and rs["median_ratio_4q"] > 0 else None,
                                          "1/backlog_coverage": r4(1 / rs["backlog_coverage_at_origin"]) if _num(rs.get("backlog_coverage_at_origin")) and rs["backlog_coverage_at_origin"] > 0 else None},
                   "calibrated_shift": r4(shift), "lag_q": 0,
                   "basis": "공시 해양 잔고(%s억) 를 상한으로 원장 밖 잔고를 최근 속도로 소진 — 화해 배율(1/ratio) 곱셈은 원장 커버리지 상승을 성장으로 오독하므로 쓰지 않음" % (format(round((rs.get("reported_marine_backlog_krw_m") or 0) / UNIT_DIV), ",d"))}
    seg_label = "조선·해양(%s)" % "·".join(seg_names) if seg_names else "조선·해양"
    seg_rows = {"매출조선": {}, "OP조선": {}, "매출기타": {}, "OP기타": {}}
    for q in seg_act:
        seg_rows["매출조선"][q] = act(seg_act[q], "sls.reconcile.reported_segment_rev_m ← yards_cache 부문표(3개월분)")
        seg_rows["매출기타"][q] = act(other_act[q], "연결 매출 − 조선 부문(파생)")
    for q in fq:
        seg_rows["매출조선"][q] = est(seg_est[q][0], seg_est[q][1])
        seg_rows["매출기타"][q] = est(oth_rev[q], oth_basis[q])
        seg_rows["OP조선"][q] = est(seg_est[q][0] * opm_path[q], "매출조선 × 타겟 OPM(부문 OP 미공시 → 회사 OPM 적용)")
        seg_rows["OP기타"][q] = est(oth_rev[q] * opm_path[q], "매출기타 × 회사 OPM(부문 OP 미공시)")
    p["segments"] = [
        {"key": "조선", "label": seg_label, "driver": p["driver"], "opm_path": {q: r4(v) for q, v in opm_path.items()}},
        {"key": "기타", "label": "기타 부문(총매출 − 조선)", "driver": {"type": "median_flat", "basis": "연결 매출 − 조선 부문 실적의 최근 4분기 중위 유지"},
         "opm_path": {q: r4(v) for q, v in opm_path.items()}},
    ]
    p["extra_rows"] = seg_rows
    pm = _panel_module(stock, ctx, fq)
    if pm:
        p["modules"].append(pm)
    p["warnings"].append("추정 매출은 %s 기준 잔고 소진분만 — 이후 신규 수주 매출 미포함(2028 감소는 이 한계). forecast_panel 모듈 참고" % la)
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
    p["driver"] = {"type": "subsidiary_yard_scaled", "core": HOLDING_CORE, "ratio_used": r4(ratio), "quarters_used": use, "opm_shift": r4(shift),
                   "basis": "종속 조선사 합산(비상장 삼호 포함) − 내부거래 를 실측 연결/HD현대重 비율 하나로 대신함(합병 후 분기만)"}
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
    w = collections.defaultdict(float)
    for y in (co or {}).get("yards") or []:
        code = YARD_ALIAS.get(y.get("yard"), y.get("yard"))
        if code and re.fullmatch(r"\d{6}", code):
            w[code] += float(y.get("share") or y.get("mentions") or 1)
    tot = sum(w.values())
    return {k: v / tot for k, v in sorted(w.items())} if tot else {}


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
                      "estimates_from": q_next(la) if la else None, "driver": m.get("driver_type")}
    if not used:
        if detail is not None:
            detail.update({"sources": srcs, "mergers": []})
        return {}, "; ".join(notes) or "고객 없음", {}
    tot = sum(used.values())
    used = {k: v / tot for k, v in used.items()}
    idx = collections.defaultdict(float)
    handled, mergers = set(), []
    for code, w in used.items():
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
                    if len(qs) < LINK_MIN_N:
                        continue
                    xs, ys = [X[q] for q in qs], [Y[q] for q in qs]
                    sxx = sum(x * x for x in xs)
                    coef = (sum(x * y for x, y in zip(xs, ys)) / sxx) if sxx > 0 else None
                    corr = pearson(xs, ys)
                    rows.append({"wkey": wkey, "lag": lag, "transform": t, "window": win, "n": len(qs), "corr": r4(corr), "coef": r4(coef) if coef is not None else None,
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
        return {"wkey": r["wkey"], "lag_q": r["lag"], "transform": r["transform"], "window_q": r["window"], "n": r["n"], "corr": r["corr"], "coef": r["coef"], "covers_fq": r["covers_fq"]}
    ranked = sorted([r for r in rows if r["corr"] is not None], key=lambda r: (-r["corr"], -r["n"], abs(r["lag"] - 1)))
    by_t, by_w = {}, {}
    for r in ranked:
        by_t.setdefault(r["transform"], _short(r))
        by_w.setdefault(r["wkey"], _short(r))
    return {"lags": list(LINK_LAGS), "windows": list(LINK_WINDOWS), "transforms": list(LINK_TRANSFORMS),
            "weight_candidates": {k: {"weights": {c: r4(v) for c, v in w.items()}, "basis": b} for k, w, b in cands},
            "n_candidates": len(rows), "n_with_corr": len(ranked),
            "selection": "상관 최대(4자리) → n 큼 → |시차−1| 작음 → 수준>YoY>4Q합 → 가중치 후보 순 → 창 작음; 추정 구간을 다 덮는 조합만",
            "top": [_short(r) for r in ranked[:12]], "best_by_transform": by_t, "best_by_weights": by_w,
            "table": {"%s|lag%d|%s|w%d" % (r["wkey"], r["lag"], r["transform"], r["window"]): [r["corr"], r["n"], r["coef"]] for r in rows},
            "overfit_note": "후보 %d개 중 최대 상관을 골랐다(다중비교 보정 없음) · 표본 %s분기 · 4분기 이동합은 평활로 상관이 부풀고 공통 추세를 잡기 쉽다 — 과적합 경고"
                            % (len(rows), ("%d" % best["n"]) if best else "8~19")}


def _link_significance(best):
    rc = _r_crit_p05(best["n"])
    return {"r_crit_p05_two_sided": rc, "significant_p05_uncorrected": (rc is not None and best["corr"] is not None and abs(best["corr"]) >= rc),
            "note": "단일 검정 기준 임계 r(df=n−2, 양측 5%) — 격자 후보 수만큼 보정하면 임계는 더 높다"}


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
    rejected_base = {"weights": {k: r4(v) for k, v in used.items()}, "weights_key": best["wkey"], "corr": best["corr"], "b": best["coef"], "n": best["n"],
                     "lag_q": best["lag"], "transform": best["transform"], "window_q": best["window"]}
    # 채택 조건(2026-09-30 오너 결정): 상관 ≥ CORR_MIN 만으로는 격자 45~180 후보 중 최대값이 표본 8~19 에서
    # 위로 치우쳐 비유의 연동(현대리바트 r .53 n8 등)까지 채택됐다 → 단일 검정 5% 유의(r ≥ r_crit(df=n−2))와
    # n ≥ LINK_MIN_N 을 함께 요구한다. 다중비교 보정은 하지 않되 overfit_note 로 남긴다.
    sig = _link_significance(best)
    if best["corr"] < CORR_MIN or not sig["significant_p05_uncorrected"] or best["n"] < LINK_MIN_N:
        why = ("최대 상관 %.2f < %.2f" % (best["corr"], CORR_MIN)) if best["corr"] < CORR_MIN else \
              ("상관 %.2f 가 단일 검정 5%% 임계 r %.2f 미달(n=%d)" % (best["corr"], sig["r_crit_p05_two_sided"] or 0.0, best["n"])) if not sig["significant_p05_uncorrected"] else \
              ("짝 n=%d < %d" % (best["n"], LINK_MIN_N))
        p = fb("고객 연동 격자 %s (%s·시차 %d·%s·창 %d)" % (why, best["wkey"], best["lag"], LINK_TRANSFORM_KO[best["transform"]], best["window"]))
        p["driver"]["customer_link_rejected"] = dict(rejected_base, grid=grid, significance=sig,
                                                     merger_rule=[m["rule"] for m in det.get("mergers") or []], customer_sources=det.get("sources") or {})
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
    p["driver"] = {"type": "customer_yard_revenue_weighted", "weights": {k: r4(v) for k, v in used.items()}, "weights_key": best["wkey"], "weights_basis": pc["basis"],
                   "lag_q": best["lag"], "transform": best["transform"], "transform_ko": LINK_TRANSFORM_KO[best["transform"]], "window_q": best["window"],
                   "ratio_used": best["coef"], "coef_kind": "beta_yoy(고객지수 YoY → 자사 YoY, 원점회귀)" if best["transform"] == "yoy" else "b(원점회귀 비례계수)",
                   "corr": best["corr"], "n": best["n"], "quarters_used": best["quarters"],
                   "seasonal_share": ({str(k): r4(v) for k, v in share_info[0].items()} if share_info else None),
                   "seasonal_basis": (share_info[1] if share_info else None),
                   "significance": _link_significance(best), "grid": grid,
                   "customer_sources": det.get("sources") or {}, "merger_rule": [m["rule"] for m in det.get("mergers") or []],
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
        rows["매출연결조정"][q] = est(resid_med, "최근 %d분기 잔차 중위(내부거래·베트남)" % len(rk))
        tot = sep_est[q] + sub_rev.get(q, 0.0) + resid_med
        p["rev"][q] = (tot, "별도(조선기자재) %.0f + 종속사 %.0f + 연결조정 %.0f" % (sep_est[q], sub_rev.get(q, 0.0), resid_med))
        op_tot = tot * opm_cons
        rows["OP연결조정"][q] = est(op_tot - sep_est[q] * sep_opm - sub_op.get(q, 0.0), "연결 OP − 별도 OP − 종속사 OP(잔차)")
    opm_path = {q: r4(sep_opm) for q in fq}
    p["segments"] = [
        {"key": "조선기자재", "label": "조선기자재(별도 매출 — 풍력·플랜트 부문 미분리)", "driver": dict(p["driver"], target="별도 매출"), "opm_path": opm_path},
        {"key": "종속사", "label": "종속사 일승·동방선기", "driver": {"type": "subsidiary_models", "basis": "각 회사 모델(assets/models) 합산"},
         "opm_path": {q: r4(sub_op.get(q, 0.0) / sub_rev[q]) if sub_rev.get(q) else None for q in fq}},
        {"key": "연결조정", "label": "연결조정(세진베트남·내부거래 잔차)", "driver": {"type": "residual", "basis": "연결 − 별도 − 종속사 최근 4분기 중위"},
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
    S["last_actual"] = fin.last
    return S


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
        second = sorted(others, reverse=True)[1] if len(others) > 1 else 0.0     # 같은 크기가 되풀이되면(이자수익 수준 이동) 일회성이 아니다
        if x > max(1.0, 2 * abs(S["영업이익"][q]), 0.05 * abs(S["매출액"][q]), ONE_OFF_TTM_OP_SHARE * ttm_op) \
                and x > ONE_OFF_MIN_RATIO * max(medo, 1.0) and x > 2 * second:
            out.append({"q": q, "nonop": r2(nonop[q]), "op": r2(S["영업이익"][q]), "fin_pl": r2(S["금융손익"].get(q)), "other_nonop": r2(S["기타영업외손익"].get(q)),
                        "median_abs_nonop_12q": r2(medo), "ttm_abs_op": r2(ttm_op), "ni_ctrl": r2(S["지배주주순이익"].get(q)),
                        "note": "비영업손익 급등 — 처분이익 등 일회성 여부는 주석 확인(face 만으로 분리 불가). 이 분기 지배NI·EPS·FY 합계·TTM PER 에 그대로 포함, 12M fwd EPS 에는 미포함"})
    return out


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
    if S["_derived"].get("지배주주순이익"):
        warnings.append("지배주주순이익 face 누락 분기는 당기순이익 − 비지배 로 파생: %s" % ", ".join(S["_derived"]["지배주주순이익"]))
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
    for key in rows:
        if key in S and isinstance(S[key], dict) and key in SRC_DEF:
            kind_, acct = SRC_DEF[key]
            for q, v in S[key].items():
                rows[key][q] = act(v, fin.src(kind_, acct, q=q))
    # 파생 실적: OPM · EBITDA · 주식수 · EPS · BPS · DPS  (fin 주식수 없으면 prices 폴백 — 아래 shares 결정과 같은 값)
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
        sh_kind, sh_src = "actual", "fin.shares.common_outstanding"
        if not sh:
            near = [k for k in fin.quarters if fin.shares_outstanding(k)]
            prev = [k for k in near if k < q]
            nxt = [k for k in near if k > q]
            if prev or nxt:
                k = prev[-1] if prev else nxt[0]
                sh, sh_kind, sh_src = fin.shares_outstanding(k), "estimate", "주식의 총수 기재 없는 분기 → %s 값 이월" % k
            elif shares_fb:
                sh, sh_kind, sh_src = shares_fb, "estimate", "prices.json shares_outstanding(aikstockdata) — fin 주식의 총수 없음"
        if sh:
            rows["주식수"][q] = {"v": round(sh / 1e6, 3), "kind": sh_kind, ("src" if sh_kind == "actual" else "basis"): sh_src}
            ni_c = S["지배주주순이익"].get(q)
            if ni_c is not None:
                rows["EPS"][q] = {"v": round(ni_c * 1e8 / sh, 1), "kind": "actual", "src": "지배주주순이익 ÷ 유통주식수(파생)"}
            eq_c = S["지배주주지분"].get(q)
            if eq_c is not None:
                rows["BPS"][q] = {"v": round(eq_c * 1e8 / sh, 1), "kind": "actual", "src": "지배주주지분 ÷ 유통주식수(파생)"}
    dps = fin.dps_series()
    for y, v in dps.items():
        if "%dQ4" % y in all_q:
            rows["DPS"]["%dQ4" % y] = {"v": float(v), "kind": "actual", "src": "fin.dividend.dps_common(연간, Q4 에 표기)"}

    # ── 공통 가정 ──
    rev_a, op_a = S["매출액"], S["영업이익"]
    k4 = last_n(rev_a, 4)
    sga_ratio = med([S["판관비"][q] / rev_a[q] for q in k4 if q in S["판관비"] and rev_a[q]]) or 0.0
    k12 = last_n(S["세전이익"], 12)
    sum_pt = sum(S["세전이익"][q] for q in k12)
    sum_tax = sum(S["법인세비용"].get(q, 0.0) for q in k12)
    if sum_pt > 0 and k12:
        tax_rate, tax_basis = clip(sum_tax / sum_pt, *TAX_CLIP), "최근 %d분기 유효세율 %.1f%% → 5~27%% 클립" % (len(k12), sum_tax / sum_pt * 100)
    else:
        tax_rate, tax_basis = TAX_DEFAULT, "세전 합 ≤ 0 → 법정세율 근사 22% 가정"
    k8 = last_n(S["당기순이익"], 8)
    ni8 = sum(S["당기순이익"][q] for q in k8)
    nci8 = sum(S["비지배순이익"].get(q, 0.0) for q in k8)
    minority = clip(nci8 / ni8, 0.0, 0.6) if (ni8 > 0 and S["비지배순이익"]) else 0.0
    # 이자율(CF 실측): Σ이자수취/평균 이자발생자산, Σ|이자지급|/평균 총차입금
    def _rate(flow, bal):
        ks = [q for q in last_n(flow, 4) if q in bal]
        if len(ks) < 2:
            return None
        avg = sum(bal[q] for q in ks) / len(ks)
        return (sum(abs(flow[q]) for q in ks) / avg * 4 / len(ks)) if avg > 0 else None
    r_asset = _rate(S["이자수취"], S["이자발생자산"])
    r_debt = _rate(S["이자지급"], S["총차입금"])
    fin_med = med([S["금융손익"][q] for q in last_n(S["금융손익"], 4)])
    eq_med = med([S["지분법손익"][q] for q in last_n(S["지분법손익"], 4)]) if S["지분법손익"] else None
    shares, shares_q = fin.last_shares()
    shares_src = "fin.shares.common_outstanding(%s)" % shares_q
    if not shares:
        px = ctx.price(stock) if not freeze else None
        if _num((px or {}).get("shares_outstanding")) and px["shares_outstanding"] > 0:
            shares, shares_q, shares_src = px["shares_outstanding"], (px.get("as_of") or "prices"), "prices.json shares_outstanding(aikstockdata; fin 주식의 총수 없음)"
            warnings.append("fin 주식의 총수 없음 → 유통주식수는 aikstockdata shares_outstanding %s 사용(추정 구간·EPS/BPS 실적 파생 모두)" % format(shares, ",d"))
        else:
            warnings.append("유통주식수 없음 → EPS·BPS 미산출")
    last_dps = dps[max(dps)] if dps else 0.0
    payout = None
    if dps and shares:
        y = max(dps)
        ni_y = sum(S["지배주주순이익"].get("%dQ%d" % (y, k), 0.0) for k in range(1, 5))
        payout = r4(dps[y] * shares / 1e8 / ni_y) if ni_y > 0 else None
    da_avg = med([S["감가상각비"][q] for q in last_n(S["감가상각비"], 4)]) if S["감가상각비"] else None
    if da_avg is None:
        warnings.append("감가상각비가 face·CF 에 없음(주석 미파싱) → EBITDA·EV/EBITDA 미산출")
    one_offs_detected = _detect_one_offs(S, all_q)
    for o in one_offs_detected:
        ratio_txt = ("영업이익 %s억의 %.0f배" % (format(round(o["op"]), ",d"), abs(o["nonop"]) / abs(o["op"]))) if o["op"] else "영업이익 0"
        warnings.append("일회성 의심 %s: 비영업손익 %+s억(%s, 12분기 중위 %s억) → 지배NI %s억·EPS·FY%s 합계·TTM PER 에 그대로 포함 — 처분이익 등 일회성 여부는 주석 확인 전까지 미확정(12M fwd EPS 에는 미포함)"
                        % (o["q"], format(round(o["nonop"]), ",d"), ratio_txt, format(round(o["median_abs_nonop_12q"]), ",d"),
                           format(round(o["ni_ctrl"]), ",d") if _num(o["ni_ctrl"]) else "—", o["q"][:4]))
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
        if r_asset is not None or r_debt is not None:
            ia_avg = ia_prev if ia_prev is not None else 0.0
            fin_v = (ia_avg * (r_asset or 0.0) - (debt_prev or 0.0) * (r_debt or 0.0)) / 4
            fin_b = "이자손익 = 이자발생자산 %.0f억 × %.2f%% − 총차입금 %.0f억 × %.2f%% (연율, CF 실측) ÷ 4; 환·평가손익 0 가정" % (
                ia_avg, (r_asset or 0.0) * 100, debt_prev or 0.0, (r_debt or 0.0) * 100)
        else:
            fin_v, fin_b = (fin_med or 0.0), "이자 CF 없음 → 최근 4분기 금융손익 중위 유지"
        rows["금융손익"][q] = est(fin_v, fin_b)
        rows["기타영업외손익"][q] = est(0.0, "일회성 미가정 → 0")
        eqm = 0.0
        if S["지분법손익"]:
            eqm = eq_med or 0.0
            rows["지분법손익"][q] = est(eqm, "최근 4분기 중위")
        fxv = fx_by_q.get(q, 0.0) if fx_by_q else 0.0
        if fx_by_q:
            rows["환관련손익"][q] = est(fxv, "외화 순노출 %.0f백만$ × Δ기말 원/달러(%s)" % (exposure, fx_assump["basis"]))
        pretax = op + fin_v + 0.0 + eqm + fxv
        tax = max(pretax, 0.0) * tax_rate
        ni = pretax - tax
        ctrl = ni * (1 - minority)
        rows["세전이익"][q] = est(pretax, "영업이익 + 금융손익 + 기타영업외 + 지분법 + 환관련(항등식)")
        rows["법인세비용"][q] = est(tax, "max(세전, 0) × 세율 %.1f%%(%s)" % (tax_rate * 100, tax_basis))
        rows["당기순이익"][q] = est(ni, "세전이익 − 법인세비용(항등식)")
        rows["지배주주순이익"][q] = est(ctrl, "당기순이익 × (1 − 비지배 비중 %.1f%%, 최근 8분기 실측)" % (minority * 100))
        if da_avg is not None:
            rows["감가상각비"][q] = est(da_avg, "최근 4분기 감가상각비 중위 유지")
            rows["EBITDA"][q] = est(op + da_avg, "영업이익 + 감가상각비")
        # 배당(Q2 지급 가정) · 자본 롤
        div = (last_dps * shares / 1e8) if (shares and q.endswith("Q2")) else 0.0
        if shares:
            rows["주식수"][q] = {"v": round(shares / 1e6, 3), "kind": "estimate", "basis": "유통주식수 유지 — %s" % shares_src}
            rows["EPS"][q] = {"v": round(ctrl * 1e8 / shares, 1), "kind": "estimate", "basis": "지배주주순이익 ÷ 유통주식수"}
            if q.endswith("Q4"):
                rows["DPS"][q] = {"v": float(last_dps), "kind": "estimate", "basis": "직전 결산 DPS %s원 유지" % format(last_dps, ",.0f")}
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
            nd_t = nd_t - (ni - div)
            rows["순차입금"][q] = est(nd_t, "전분기 − (순이익 − 배당): 순이익 = 순현금 증가 가정(CAPEX≈감가, 운전자본 불변)")
        if ia_t is not None:
            ia_t = ia_t + (ni - div)
            rows["이자발생자산"][q] = est(ia_t, "전분기 + (순이익 − 배당) — 순차입금 롤과 같은 가정")
            ia_prev = ia_t
    for key, cells in plan.get("extra_rows", {}).items():
        rows[key] = cells
    # 사업부 행 라벨은 이 모델의 세그먼트 라벨로 — 모듈 전역 ROW_META 를 고치면 한 프로세스에서 먼저 만든 회사의 라벨(삼성重 '조선해양')이
    # 같은 key 를 쓰는 다음 회사(한화오션 '조선·해양플랜트')에 새어 들어가 빌드 순서에 따라 바이트가 달라진다 → 모델별 사본
    row_meta = dict(ROW_META)
    for seg in plan["segments"]:
        for pre in ("매출", "OP"):
            k = pre + seg["key"]
            row_meta.setdefault(k, ("%s %s" % (pre, seg["label"]), "사업부", "억원"))

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
            backtest.update({"revenue_wape_pct": wape([(p[1], p[2]) for p in pairs]), "op_wape_pct": wape([(p[3], p[4]) for p in pairs]), "n": len(pairs),
                             "driver_at_freeze": (bm.get("segments") or [{}])[0].get("driver", {}).get("type") if bm.get("segments") else (bm.get("driver_type")),
                             "frozen_inputs": "fin(연결/별도)·고객 조선사 모델·지주 자회사 모델은 %s 까지의 분기만; 선표는 체결일 ≤ %s 말일 계약(원장 최신 금액·코호트 등급, 환산 없음); "
                                              "잔고는 yards_cache %s; 시세·환율 forward·prices 미사용. 고객 가중치(suppliers.json 언급 비중)와 합병 체인링크는 현재 지식" % (FREEZE_Q, FREEZE_Q, FREEZE_Q),
                             "detail": [{"q": q, "rev_pred": r2(pr), "rev_act": r2(ar), "op_pred": r2(po), "op_act": r2(ao)} for q, pr, ar, po, ao in pairs]})
            if len(pairs) < BACKTEST_H:
                backtest["note"] = "실측 %d분기만 비교(나머지는 실적 없음 — 추정 vs 추정은 세지 않음) · 단일 회사 — 통계 아님" % len(pairs)
    elif not freeze:
        backtest["note"] = "freeze %s 이후 실적 분기 없음 → 백테스트 없음" % FREEZE_Q

    # ── 요약·품질 ──
    n_est_rev = sum(1 for q in fq if q in rm["매출액"]["q"])
    stale = (not freeze) and la < _latest_complete_quarter(ctx, la)
    status = "full"
    if plan["fallback"] or len(fin.quarters) < 8 or not identities_ok or n_est_rev < FWD_MIN or fin.sep_fill:
        status = "partial"
    if stale:
        status = "partial"
        if stock in MERGERS:
            warnings.append("%s 부터 정기보고서 없음(%s 에 합병) — 참고용 모델, 시세 없음" % (MERGERS[stock][1], MERGERS[stock][0]))
        else:
            warnings.append("마지막 fin 분기 %s < 최신 완결 분기 %s — 최신 보고서 미수집(no_report) 상태의 모델" % (la, _latest_complete_quarter(ctx, la)))
    quality = {"fin_quarters": len(fin.quarters), "scope": fin.scope, "sep_filled": fin.sep_fill, "missing": missing + ident["missing_rows"], "identities_ok": identities_ok,
               "identity_checks": {k: v for k, v in ident.items() if k != "mismatches" and k != "missing_rows"},
               "identity_mismatches": ident["mismatches"][:20], "warnings": warnings, "status": status}
    views = None if freeze else _views(rm, all_q, fq, la, annual_years)
    model = collections.OrderedDict([
        ("stock", stock), ("name", name), ("role", role_eff), ("origin", la), ("unit", "KRW_100M(억원)"), ("built_at", ctx.today),
        ("status", status),
        ("periods", {"quarters": quarters, "annual": annual_years, "last_actual": la}),
        ("rows", out_rows),
        ("segments", plan["segments"]),
        ("driver_type", plan["driver"].get("type")),
        ("assumptions", {"fx": fx_assump, "hedge": _hedge_assump(ctx.sls(stock)) if stock in YARDS else None,
                         "tax_rate": r4(tax_rate), "tax_basis": tax_basis, "sga_ratio": r4(sga_ratio),
                         "interest_rate_debt": r4(r_debt), "interest_rate_asset": r4(r_asset), "minority_share": r4(minority),
                         "payout": payout, "dps_assumed": last_dps, "opm_source": plan["driver"].get("type"), "one_offs": [],
                         "one_offs_note": "fin face 에서 일회성 분리 불가(주석 미파싱) → 가정 없음; 레퍼런스 일회성 표는 사례",
                         "one_offs_detected": one_offs_detected}),
        ("fx_pnl", fx_pnl),
        ("valuation", valuation),
        ("consolidation", plan["consolidation"] or {"method": "consolidated_direct" if fin.scope == "cons" else "separate_only", "subsidiaries": []}),
        ("modules", plan["modules"]),
        ("backtest", backtest),
        ("views", views),
        ("quality", quality),
    ])
    return model


def _latest_complete_quarter(ctx, default):
    """fx.json 의 마지막 완결 분기 — '오늘 기준 최신 분기' 대용(네트워크 없음)."""
    qs = [q for q, d in (ctx.fx.get("quarters") or {}).items() if not d.get("partial")]
    return max(qs) if qs else default


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
                       "per": a("PER"), "pbr": a("PBR"), "dps": a("DPS")}
    bt = model.get("backtest") or {}
    seg0 = ((model.get("segments") or [{}])[0].get("driver") or {}) if model.get("segments") else {}
    link = None
    if seg0.get("type") == "customer_yard_revenue_weighted":
        link = {"adopted": True, "weights_key": seg0.get("weights_key"), "lag_q": seg0.get("lag_q"), "transform": seg0.get("transform"),
                "window_q": seg0.get("window_q"), "corr": seg0.get("corr"), "n": seg0.get("n")}
    elif seg0.get("customer_link_rejected"):
        rj = seg0["customer_link_rejected"]
        link = {"adopted": False, "weights_key": rj.get("weights_key"), "lag_q": rj.get("lag_q"), "transform": rj.get("transform"),
                "window_q": rj.get("window_q"), "corr": rj.get("corr"), "n": rj.get("n")}
    return {"stock": model["stock"], "name": model.get("name"), "role": model.get("role"), "status": model.get("status"),
            "last_actual": la, "fin_quarters": (model.get("quality") or {}).get("fin_quarters"), "driver": model.get("driver_type"), "link": link,
            "fy": fy, "per_now": (model.get("valuation") or {}).get("per_now"), "pbr_now": (model.get("valuation") or {}).get("pbr_now"),
            "backtest": {"revenue_wape_pct": bt.get("revenue_wape_pct"), "op_wape_pct": bt.get("op_wape_pct"), "n": bt.get("n")},
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
    for k in ("매출액", "영업이익", "OPM", "지배주주순이익", "EPS", "BPS", "PER", "PBR"):
        r = rm.get(k)
        if not r:
            continue
        a = r.get("a") or {}
        print("  %-10s " % k + " ".join("%s:%s" % (y, a[y].get("v")) for y in sorted(a) if int(y) >= 2025))
    bt = model.get("backtest") or {}
    print("  backtest freeze=%s n=%s rev_wape=%s op_wape=%s" % (bt.get("freeze"), bt.get("n"), bt.get("revenue_wape_pct"), bt.get("op_wape_pct")))
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
            print("  %s %-12s %-7s %-7s la=%s rev26E=%s op26E=%s eps26E=%s bt=%s/%s" % (
                r["stock"], (r["name"] or "")[:12], r["role"], r["status"], r["last_actual"], f26.get("rev"), f26.get("op"), f26.get("eps"),
                r["backtest"]["revenue_wape_pct"], r["backtest"]["op_wape_pct"]))
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
