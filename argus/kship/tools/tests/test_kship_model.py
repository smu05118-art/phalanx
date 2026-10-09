#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_model 계약 테스트 — 실적 모델 엔진.

실행: cd argus/kship/tools && python3 -m unittest tests.test_kship_model
합성 fin/sls 로 규칙(단위 변환·항등식·EPS·세율 클립·추세 감쇠·체인링크·선표 동결·잔고 소진)을 검사하고,
실제 assets(fin/010140·075580)가 있으면 산출물 불변식(2026Q2 실적 = fin, 추정 10분기+연간 3년, EPS 규모, 결정론)도 본다.
라운드 3(스펙 5-3): forecast_panel 신규수주(매출조선신규 행·base 합산·보수/낙관 scenarios) · sls cohort_mode/backlog_cap_applied 읽기 ·
고객 연동 OOS 선택(동결 la−4분기, WAPE_link ≤ WAPE_trend × 1.10) · 동결 전 합병은 체인링크 없이.
T4: 금융손익 세부(이자·외환·파생·기타금융 잔차) 행 · 주석 이자수익/비용 실측 연율(4분기 미만이면 CF 폴백) · None 전파.
T6(T3 적대 검토 D1~D10): origin 이후 공시 수주의 신규수주 이중계산 제외 · 음(−)세율 폴백 · 등급 없는 비중 실측 중위 채움 · 세진 연결조정 비율 ·
OOS 반올림 전 비교·현재 조합 시험·undetermined · 금융손익 단절 경고 · status/driver_fallback 분리 · 정의상 0 = estimate · 시나리오 OPM 원값 · 캡 배율 null.
V4(2026-10-05 검증 레인): 조정EPS 행(일회성 의심 회사만) · 음수 부문 매출 분기 제외 · FCF 근사(NI + 감가 − CAPEX) BS 롤 · status_rule/status_reasons ·
동결 모델이 동결 이후 fin 에 둔감한지(누출 프로브) · 실제 자산(KCC 2026Q2 조정EPS · HJ重 2022Q4).
라운드 7 (j)(2026-10-08): 주식수 사건 — fin 안 정수비 병합/무상증자 자동 감지·SHARE_EVENTS 수동·aik 분기말 후 사건(split/issuance/irregular)·과거 EPS/BPS/DPS 환산·
eps_reported 교차검증·동결 모델·selfcheck r1 호환 자릿수 · 실제 자산(KS인더스트리 101000·케이앤에스아이앤씨 487400·엔케이·인화정공).
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

import kship_model as M                                              # noqa: E402

SHARES = 10_000_000


def synth_fin(stock="999999", name="합성", quarters=None, rev0=100_000.0, g_q=0.02, scope="cons", tax=0.22, minority=0.1,
              shares=SHARES, dps=100, no_shares=False, no_cf_interest=False, cf_interest_upto=None, shares_by_q=None, treasury=0, eps_reported=None):
    """백만원 단위 fin json(스펙 2-1 필수 부분). 매출 rev0×(1+g)^i, 원가 70%, 판관 10%, 금융손익 −500, 기타영업외 +100. no_cf_interest 면 CF 이자수취·이자지급 키 없음,
    cf_interest_upto 는 그 분기까지만 CF 이자 키를 둔다(CF 창을 주석 창보다 오래되게).
    shares_by_q {분기: 발행주식수} 로 분기별 주식수(병합/분할 사건), treasury 는 자기주식(유통 = 발행 − 자기), eps_reported {분기: {cur_q, cur_ytd, prev_q, prev_ytd}} 는 보고 EPS 비교표시."""
    quarters = quarters or M.q_range("2023Q1", "2026Q2")
    fin = {"stock": stock, "name": name, "unit": "KRW_million", "quarters": list(quarters), "reports": {},
           "cons": {"bs": {}, "is": {}, "cf": {}, "is_ytd": {}}, "sep": {"bs": {}, "is": {}, "cf": {}, "is_ytd": {}},
           "shares": {}, "dividend": {}, "derivation": {}, "checks": [], "issues": [], "golden": {}}
    eq, ctrl = 500_000.0, 450_000.0
    for i, q in enumerate(quarters):
        rev = rev0 * (1 + g_q) ** i
        cogs, sga = rev * 0.7, rev * 0.1
        gp = rev - cogs
        op = gp - sga
        fin_pl, oth = -500.0, 100.0
        pretax = op + fin_pl + oth
        tx = pretax * tax
        ni = pretax - tx
        nci = ni * minority
        eq += ni
        ctrl += ni - nci
        is_ = {"매출액(수익)": rev, "매출원가": cogs, "매출총이익": gp, "판관비": sga, "영업이익": op, "금융손익": fin_pl, "기타영업외손익": oth,
               "법인세비용차감전계속사업이익": pretax, "법인세비용": tx, "당기순이익": ni, "(지배주주지분)당기순이익": ni - nci, "(비지배주주지분)당기순이익": nci}
        bs = {"자산총계": eq + 300_000.0, "부채총계": 300_000.0, "자본총계": eq, "지배주주지분": ctrl, "총차입금": 120_000.0, "순차입금": 20_000.0,
              "이자발생자산": 100_000.0, "현금및현금성자산": 60_000.0}
        cf = {"이자수취(CF)": 750.0, "이자지급(CF)": -1200.0, "CAPEX": 3000.0, "영업활동으로인한현금흐름": ni + 3000.0}
        if no_cf_interest or (cf_interest_upto and q > cf_interest_upto):
            cf = {k: v for k, v in cf.items() if "이자" not in k}
        for sc in ("cons", "sep"):
            fin[sc]["is"][q], fin[sc]["bs"][q], fin[sc]["cf"][q] = dict(is_), dict(bs), dict(cf)
        if not no_shares:
            n = (shares_by_q or {}).get(q, shares)
            fin["shares"][q] = {"as_of": q, "issued": n, "treasury": treasury, "outstanding": n - treasury, "common_issued": n, "common_treasury": treasury, "common_outstanding": n - treasury}
        if q.endswith("Q4"):
            fin["dividend"][q] = {"dps_common": dps, "payout_pct": None}
    if eps_reported:
        fin["cons"]["eps_reported"], fin["sep"]["eps_reported"] = dict(eps_reported), dict(eps_reported)
    if scope == "sep":
        fin["cons"] = {"bs": {}, "is": {}, "cf": {}, "is_ytd": {}}
    return fin


class FakeCtx(M.Ctx):
    """assets 를 읽지 않는 컨텍스트 — fin/sls/prices 를 dict 로 주입."""

    def __init__(self, fins=None, slss=None, prices=None, roles=None, suppliers=None, fx=None):
        self.today = "2026-09-30"
        self.fx = fx or {"quarters": {"2026Q2": {"USDKRW_end": 1500.0, "USDKRW_avg": 1480.0, "partial": False}},
                         "forward": {"note": "합성 flat", "2026Q3": {"USDKRW_end": 1400.0, "USDKRW_avg": 1450.0}}}
        self.prices = {"rows": prices or {}}
        self.suppliers = suppliers or {"cos": []}
        self.universe = []
        self.panel = {}
        self._fin = dict(fins or {})
        self._sls = dict(slss or {})
        self._models, self._building = {}, set()
        self.roles = dict(roles or {})
        self.names = {k: v.get("name") for k, v in self._fin.items()}

    def fin(self, stock):
        return self._fin.get(stock)

    def sls(self, stock):
        return self._sls.get(stock)


def rows_of(model):
    return {r["key"]: r for r in model["rows"]}


FIXTURE_ASSETS = os.path.join(HERE, "fixtures")                 # 합성 테스트가 보는 assets 루트 — contracts.json 없음 → _sejin_modules 원장 행 없음
FIXTURE_YARDS = os.path.join(FIXTURE_ASSETS, "yards_cache")     # 010140/2025Q2.json 하나 — 백테스트 freeze 2025Q2 의 _yard_backlog_at 입력


class SyntheticAssets:
    """합성 테스트는 운영 assets/yards_cache·contracts.json 을 읽지 않는다(§14-6 ⑦, 2026-10-08).
    FakeCtx 는 fin/sls/prices 만 주입하고 _yard_backlog_at·_fx_exposure_usd_m·_sejin_modules 는 모듈 함수라 경로 상수 패치가 최소 변경 —
    운영 yards_cache 가 다음 분기 수집으로 바뀌어도 합성 결과가 흔들리지 않는다."""

    def setUp(self):
        for name, path in (("YARDS_CACHE", FIXTURE_YARDS), ("ASSETS", FIXTURE_ASSETS)):
            p = mock.patch.object(M, name, path)
            p.start()
            self.addCleanup(p.stop)
        self.assertEqual(M.YARDS_CACHE, FIXTURE_YARDS)
        self.assertNotIn("tools/assets", M.YARDS_CACHE.replace(os.sep, "/"))          # 회귀 가드 — 운영 경로가 아니다


class TestHelpers(unittest.TestCase):
    def test_q_add_and_end_date(self):
        self.assertEqual(M.q_add("2026Q2", 1), "2026Q3")
        self.assertEqual(M.q_add("2026Q4", 1), "2027Q1")
        self.assertEqual(M.q_add("2026Q1", -1), "2025Q4")
        self.assertEqual(M.q_add("2026Q2", 10), "2028Q4")
        self.assertEqual(M.q_end_date("2025Q2").isoformat(), "2025-06-30")

    def test_wape(self):
        self.assertEqual(M.wape([(110, 100), (90, 100)]), 10.0)
        self.assertIsNone(M.wape([]))
        self.assertIsNone(M.wape([(1, 0)]))
        self.assertEqual(M.wape([(None, 100), (120, 100)]), 20.0)

    def test_trend_seasonal_clip_and_damping(self):
        # 전년 대비 2배 성장 → g 는 +50% 클립, 2년차 25%, 계절 패턴(Q4 큼) 유지
        act = {}
        for y in (2024, 2025):
            for k, base in zip(range(1, 5), (100, 100, 100, 200)):
                act["%dQ%d" % (y, k)] = base * (2 if y == 2025 else 1)
        fq = M.q_range("2026Q1", "2027Q4")
        out, basis, g = M.trend_seasonal(act, fq)
        self.assertAlmostEqual(g, 0.5)
        self.assertAlmostEqual(out["2026Q1"], 200 * 1.5)
        self.assertAlmostEqual(out["2026Q4"], 400 * 1.5)                # 계절성 보존
        self.assertAlmostEqual(out["2027Q1"], out["2026Q1"] * 1.25)      # 감쇠
        self.assertIn("클립", basis["2026Q1"])

    def test_pearson_and_clip(self):
        self.assertAlmostEqual(M.pearson([1, 2, 3], [2, 4, 6]), 1.0)
        self.assertIsNone(M.pearson([1, 1, 1], [1, 2, 3]))
        self.assertEqual(M.clip(0.9, 0.05, 0.27), 0.27)
        self.assertIsNone(M.clip(None, 0, 1))

    def test_r4_weights_sum_exactly_one(self):
        # 2026-10-05 통합 회귀: suppliers.json ifrs8 비중(현대힘스 HSHI 55.21 + 329180 41.06 + 010620 0.22, 009540 share 0.0 → mentions 1)
        # 원값 합 1.0 이지만 원소별 4자리 반올림 합이 1.0001 — 저장값은 잔차를 최대 가중치에 얹어 정확히 1 이어야 한다
        raw = {"009540": 0.5765719560980613, "010620": 0.0022566417068417273, "329180": 0.4211714021950969}
        self.assertAlmostEqual(sum(raw.values()), 1.0, places=12)
        self.assertEqual(round(sum(round(v, 4) for v in raw.values()), 4), 1.0001)
        w = M.r4_weights(raw)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=9)
        self.assertEqual(w, {"009540": 0.5765, "010620": 0.0023, "329180": 0.4212})
        for k in raw:                                                   # 원값과 1e-4 안
            self.assertLess(abs(w[k] - raw[k]), 1e-4 + 1e-12)
        # 잔차가 없는 경우·합이 1 이 아닌 dict(정규화 전)·빈 dict 는 원소별 반올림 그대로
        self.assertEqual(M.r4_weights({"a": 0.5, "b": 0.25, "c": 0.25}), {"a": 0.5, "b": 0.25, "c": 0.25})
        self.assertEqual(M.r4_weights({"a": 12.0, "b": 9.0}), {"a": 12.0, "b": 9.0})
        self.assertEqual(M.r4_weights({}), {})
        # 결정론: 같은 값이면 키 순으로 큰 쪽에 얹는다
        self.assertEqual(M.r4_weights({"x": 1 / 3, "y": 1 / 3, "z": 1 / 3}), {"x": 0.3333, "y": 0.3333, "z": 0.3334})


class TestFin(unittest.TestCase):
    def test_unit_and_scope(self):
        f = M.Fin(synth_fin())
        self.assertEqual(f.scope, "cons")
        self.assertAlmostEqual(f.val("is", "2023Q1", "매출액(수익)"), 1000.0)         # 백만원 100,000 → 억원 1,000
        self.assertEqual(f.last, "2026Q2")
        self.assertEqual(M.Fin(synth_fin(), upto="2025Q2").last, "2025Q2")
        self.assertEqual(M.Fin(synth_fin(scope="sep")).scope, "sep")
        self.assertEqual(f.last_shares(), (SHARES, "2026Q2"))
        self.assertEqual(f.dps_series(), {2023: 100, 2024: 100, 2025: 100})


class TestBuildSynthetic(unittest.TestCase):
    def setUp(self):
        self.ctx = FakeCtx(fins={"999999": synth_fin()}, roles={"999999": "equip"},
                           prices={"999999": {"close": 20000, "as_of": "20260928", "shares_outstanding": SHARES,
                                              "history_quarterly": {q: {"avg": 20000, "close_end": 20000} for q in M.q_range("2023Q1", "2026Q2")}}})
        self.m = M.build_model("999999", self.ctx)
        self.rm = rows_of(self.m)

    def test_periods_and_actual_cells(self):
        p = self.m["periods"]
        self.assertEqual(p["last_actual"], "2026Q2")
        self.assertEqual(p["quarters"][0], "2023Q1")
        self.assertEqual(p["quarters"][-1], "2028Q4")
        self.assertEqual(len([q for q in p["quarters"] if q > "2026Q2"]), 10)
        c = self.rm["매출액"]["q"]["2026Q2"]
        self.assertEqual(c["kind"], "actual")
        self.assertEqual(c["src"], "fin.cons.is.매출액(수익)")
        self.assertAlmostEqual(c["v"], round(100_000.0 * 1.02 ** 13 / 100, 2))
        self.assertEqual(self.m["role"], "equip")
        self.assertEqual(self.m["unit"], "KRW_100M(억원)")

    def test_estimates_have_basis_and_identities_hold(self):
        for key in ("매출액", "영업이익", "세전이익", "당기순이익", "지배주주순이익", "EPS", "BPS", "자산총계"):
            for q in M.q_range("2026Q3", "2028Q4"):
                c = self.rm[key]["q"][q]
                self.assertEqual(c["kind"], "estimate", (key, q))
                self.assertTrue(c.get("basis"), (key, q))
        self.assertTrue(self.m["quality"]["identities_ok"], self.m["quality"]["identity_mismatches"])
        self.assertEqual(self.m["quality"]["identity_checks"]["estimate_fail"], 0)
        q = "2027Q1"
        v = lambda k: self.rm[k]["q"][q]["v"]
        self.assertAlmostEqual(v("매출액") - v("매출원가"), v("매출총이익"), places=1)
        self.assertAlmostEqual(v("매출총이익") - v("판관비"), v("영업이익"), places=1)
        self.assertAlmostEqual(v("세전이익") - v("법인세비용"), v("당기순이익"), places=1)
        self.assertAlmostEqual(v("부채총계") + v("자본총계"), v("자산총계"), places=1)

    def test_eps_bps_and_tax_minority(self):
        q = "2026Q2"
        ni_c = self.rm["지배주주순이익"]["q"][q]["v"]
        self.assertAlmostEqual(self.rm["EPS"]["q"][q]["v"], round(ni_c * 1e8 / SHARES, 1), places=1)
        eq_c = self.rm["지배주주지분"]["q"][q]["v"]
        self.assertAlmostEqual(self.rm["BPS"]["q"][q]["v"], round(eq_c * 1e8 / SHARES, 1), places=1)
        a = self.m["assumptions"]
        self.assertAlmostEqual(a["tax_rate"], 0.22, places=3)
        self.assertAlmostEqual(a["minority_share"], 0.1, places=3)
        self.assertAlmostEqual(a["sga_ratio"], 0.1, places=3)
        self.assertAlmostEqual(a["interest_rate_asset"], 750 * 4 / 100_000, places=4)      # CF 이자수취 연율 / 이자발생자산
        self.assertEqual(a["dps_assumed"], 100)
        # 배당은 Q2 에 지급: 자본총계 2027Q2 = 2027Q1 + NI − DPS×주식수
        eq1, eq2 = self.rm["자본총계"]["q"]["2027Q1"]["v"], self.rm["자본총계"]["q"]["2027Q2"]["v"]
        ni2 = self.rm["당기순이익"]["q"]["2027Q2"]["v"]
        self.assertAlmostEqual(eq2, eq1 + ni2 - 100 * SHARES / 1e8, places=1)

    def test_annual_aggregation_and_views(self):
        a = self.rm["매출액"]["a"]
        self.assertEqual(a["2025"]["kind"], "actual")
        self.assertEqual(a["2026"]["kind"], "mixed")
        self.assertEqual(a["2028"]["kind"], "estimate")
        self.assertAlmostEqual(a["2027"]["v"], round(sum(self.rm["매출액"]["q"]["2027Q%d" % k]["v"] for k in range(1, 5)), 2), places=1)
        self.assertEqual(self.rm["자본총계"]["a"]["2027"]["v"], self.rm["자본총계"]["q"]["2027Q4"]["v"])   # 시점 항목은 Q4
        self.assertAlmostEqual(self.rm["OPM"]["a"]["2027"]["v"], self.rm["영업이익"]["a"]["2027"]["v"] / self.rm["매출액"]["a"]["2027"]["v"], places=3)
        v = self.m["views"]
        self.assertEqual(v["분기"][0][0], "항목")
        self.assertEqual(len(v["분기"][0]) - 1, 8 + 10)
        self.assertIn("매출액", [r[0] for r in v["연간예상"]])
        self.assertEqual(v["보고서로"][0][:2], ["FY", "2025A"])

    def test_valuation_and_backtest(self):
        val = self.m["valuation"]
        self.assertEqual(val["price"]["close"], 20000)
        self.assertAlmostEqual(val["eps_fwd12m"], round(sum(self.rm["EPS"]["q"][q]["v"] for q in M.q_range("2026Q3", "2027Q2")), 1), places=1)
        self.assertAlmostEqual(val["per_now"], round(20000 / val["eps_fwd12m"], 2), places=2)
        self.assertEqual(val["note"], M.NOTE_NO_TP)
        self.assertIn(val["per_band"]["basis"].split("(")[0], ("hist_quarterly", "sector_default"))
        bt = self.m["backtest"]
        self.assertEqual(bt["freeze"], "2025Q2")
        self.assertEqual(bt["n"], 4)
        self.assertIsNotNone(bt["revenue_wape_pct"])
        self.assertEqual(len(bt["detail"]), 4)
        self.assertEqual(bt["detail"][0]["q"], "2025Q3")

    def test_status_and_summary_row(self):
        self.assertIn(self.m["status"], ("full", "partial"))
        row = M.summary_row(self.m)
        self.assertEqual(row["stock"], "999999")
        self.assertIn("2026E", row["fy"])
        self.assertIn("2025A", row["fy"])
        self.assertEqual(row["fy"]["2026E"]["rev"], self.rm["매출액"]["a"]["2026"]["v"])

    def test_no_fin_and_shares_fallback(self):
        m = M.build_model("000001", FakeCtx())
        self.assertEqual(m["status"], "no_fin")
        self.assertEqual(m["rows"], [])
        ctx = FakeCtx(fins={"999999": synth_fin(no_shares=True)}, roles={"999999": "equip"},
                      prices={"999999": {"close": 20000, "as_of": "20260928", "shares_outstanding": 5_000_000}})
        m2 = M.build_model("999999", ctx)
        rm2 = rows_of(m2)
        self.assertAlmostEqual(rm2["EPS"]["q"]["2026Q2"]["v"], rm2["지배주주순이익"]["q"]["2026Q2"]["v"] * 1e8 / 5_000_000, delta=0.3)   # 셀 v 반올림
        self.assertTrue(any("aikstockdata" in w for w in m2["quality"]["warnings"]))

    def test_tax_clip_high(self):
        # T6 D2: 클립 밖(45%)은 클립하지 않는다 → 세전 > 0 분기 중위(45%)도 5~27% 밖 → 법정세율 근사 22%
        ctx = FakeCtx(fins={"999999": synth_fin(tax=0.45)}, roles={"999999": "equip"})
        m = M.build_model("999999", ctx)
        self.assertAlmostEqual(m["assumptions"]["tax_rate"], M.TAX_DEFAULT)
        self.assertEqual(m["assumptions"]["tax_path"], "default")
        self.assertIn("5~27% 밖", m["assumptions"]["tax_basis"])

    def test_determinism(self):
        m2 = M.build_model("999999", FakeCtx(fins={"999999": synth_fin()}, roles={"999999": "equip"},
                                             prices={"999999": {"close": 20000, "as_of": "20260928", "shares_outstanding": SHARES}}))
        m1 = M.build_model("999999", FakeCtx(fins={"999999": synth_fin()}, roles={"999999": "equip"},
                                             prices={"999999": {"close": 20000, "as_of": "20260928", "shares_outstanding": SHARES}}))
        self.assertEqual(json.dumps(m1, ensure_ascii=False, sort_keys=True), json.dumps(m2, ensure_ascii=False, sort_keys=True))


def sejin_ctx(vary=False):
    """세진 + 고객 2사 + 종속 2사 합성 컨텍스트(TestSupplierLink·TestVerifierFixes 공용)."""
    return TestSupplierLink._ctx(None, vary)


class TestSupplierLink(SyntheticAssets, unittest.TestCase):
    def _ctx(self, vary=False):
        # 고객 2사: 미포(010620, 2025Q3 까지) · 현중(329180, 전 구간; 2025Q4 부터 미포를 흡수해 매출이 그만큼 커짐)
        # vary=True 면 두 고객 매출이 분기마다 달라(회귀가 잡히게), False 면 일정(체인링크 무단절 검사용)
        qs = M.q_range("2022Q1", "2026Q2")
        path_m = {q: 100_000.0 * ((1.03 ** i) if vary else 1.0) for i, q in enumerate(qs)}
        path_h = {q: 300_000.0 * ((0.99 ** i) if vary else 1.0) for i, q in enumerate(qs)}
        mipo = synth_fin("010620", "미포", quarters=[q for q in qs if q <= "2025Q3"], rev0=100_000.0, g_q=0.0)
        hhi = synth_fin("329180", "현중", quarters=qs, rev0=300_000.0, g_q=0.0)
        for q in qs:
            for sc in ("cons", "sep"):
                hhi[sc]["is"][q]["매출액(수익)"] = path_h[q] + (path_m[q] if q >= "2025Q4" else 0.0)    # 흡수합병
                if q <= "2025Q3":
                    mipo[sc]["is"][q]["매출액(수익)"] = path_m[q]
        # 공급사: 매출 = 0.1 × (0.9×미포 + 0.2×현중)_(t−1) 정확히 → 회귀가 잡혀야 한다
        sup = synth_fin("075580", "세진", quarters=qs, rev0=1.0, g_q=0.0)
        for i, q in enumerate(qs):
            pq = qs[i - 1] if i else q
            for sc in ("cons", "sep"):
                sup[sc]["is"][q]["매출액(수익)"] = 0.1 * (0.9 * path_m[pq] + 0.2 * path_h[pq])
        subs = {c: synth_fin(c, n, quarters=qs, rev0=10_000.0, g_q=0.0) for c, n in M.SEJIN_SUBS}
        fins = {"010620": mipo, "329180": hhi, "075580": sup}
        fins.update(subs)
        roles = {"010620": "yard", "329180": "yard", "075580": "equip", "333430": "equip", "099410": "equip"}
        return FakeCtx(fins=fins, roles=roles)

    def test_customer_index_chainlink_has_no_break(self):
        ctx = self._ctx()
        w = {"010620": 0.9 / 1.1, "329180": 0.2 / 1.1}
        idx, note, used = M._customer_index(w, ctx, None, lag=1)
        self.assertIn("체인링크", note)
        pre = idx["2025Q4"]           # = idx(2025Q3) 시점 값(lag 1)
        post = idx["2026Q1"]          # = 합병 후 2025Q4 매출 × k
        self.assertAlmostEqual(pre, post, places=6)     # 합병 전후 비중이 같으니 지수는 끊기지 않는다
        self.assertTrue(all(q in idx for q in M.q_range("2026Q3", "2028Q4")))

    def test_sejin_strategy_builds_consolidation(self):
        ctx = self._ctx(vary=True)
        m = M.build_model("075580", ctx)
        self.assertEqual(m["driver_type"], "customer_yard_revenue_weighted")
        rm = rows_of(m)
        for k in ("매출조선기자재", "OP조선기자재", "매출종속사", "매출연결조정"):
            self.assertIn(k, rm, k)
        seg_keys = [s["key"] for s in m["segments"]]
        self.assertEqual(seg_keys, ["조선기자재", "종속사", "연결조정"])
        q = "2027Q1"
        tot = rm["매출조선기자재"]["q"][q]["v"] + rm["매출종속사"]["q"][q]["v"] + rm["매출연결조정"]["q"][q]["v"]
        self.assertAlmostEqual(tot, rm["매출액"]["q"][q]["v"], places=1)
        self.assertEqual(m["consolidation"]["method"], "separate_plus_subsidiaries_plus_residual")
        self.assertTrue(any(mod["key"] == "wind" for mod in m["modules"]))
        # 레퍼런스 풍력 표는 합산되지 않는다(매출과 별개 모듈)
        self.assertTrue(all("합산 안 함" in r["label"] or r["key"] != "wind_ref" for mod in m["modules"] for r in mod["rows"]))

    def test_supplier_without_link_falls_back(self):
        ctx = FakeCtx(fins={"111111": synth_fin("111111")}, roles={"111111": "equip"})
        m = M.build_model("111111", ctx)
        self.assertEqual(m["driver_type"], "trend_seasonal")
        # T6 D7: status 는 데이터 완전성만 — 폴백은 driver_fallback
        self.assertEqual(m["status"], "full")
        self.assertEqual(m["driver_fallback"], "no_link")
        self.assertEqual(M.summary_row(m)["driver_fallback"], "no_link")
        self.assertTrue(any("폴백" in w for w in m["quality"]["warnings"]))


def synth_sls(stock="010140", origin="2026Q2"):
    """계약 2건(하나는 freeze 뒤 체결) + by_quarter/reconcile/reconcile_summary — 스펙 2-4 필수 부분."""
    qs = M.q_range("2024Q1", "2028Q4")
    c1 = {"rcp": "a", "type": "LNGC", "ships": 2, "amt_krw_m": 400_000.0, "amt_usd_m": 300.0, "signed": "2024-06-30", "start": "2024-06-30", "end": "2026-12-31",
          "cohort": "④호황", "counted": True, "schedule": {q: 30.0 for q in M.q_range("2024Q3", "2026Q4")}}
    c2 = {"rcp": "b", "type": "VLCC", "ships": 2, "amt_krw_m": 200_000.0, "amt_usd_m": 150.0, "signed": "2025-09-30", "start": "2025-09-30", "end": "2027-12-31",
          "cohort": "②BEP", "counted": True, "schedule": {q: 15.0 for q in M.q_range("2025Q4", "2027Q4")}}
    bq, rec, topm = {}, {}, {}
    for q in qs:
        usd = (c1["schedule"].get(q, 0) + c2["schedule"].get(q, 0))
        bq[q] = {"usd_m": usd, "marine_usd_m": usd, "hedged_krw_m": usd * 1400, "marine_hedged_krw_m": usd * 1400, "hedge_ratio": 0.7, "hedge_rate": 1400, "applied_rate": 1400}
        if q <= origin:
            rec[q] = {"sls_krw_m": usd * 1400, "reported_segment_rev_m": 150_000.0, "segments": ["조선해양"], "ratio": usd * 1400 / 150_000.0}
        topm[q] = {"opm": 0.08, "basis": "합성"}
    return {"stock": stock, "origin": origin, "contracts": [c1, c2], "by_quarter": bq, "reconcile": rec, "target_opm": topm,
            "cohort_opm_table": {"①적자": -0.05, "②BEP": 0.0, "③중마진": 0.05, "④호황": 0.10, "⑤초호황": 0.15},
            "reconcile_summary": {"median_ratio_4q": 0.42, "backlog_coverage_at_origin": 0.5, "reported_marine_backlog_krw_m": 1_200_000.0,
                                  "remaining_marine_krw_m_at_origin": 500_000.0},
            "hedge": {"hedge_ratio": 0.7, "hedge_rate": 1400, "kind": "estimate", "basis": "합성"}, "warnings": []}


class TestYard(SyntheticAssets, unittest.TestCase):
    def test_sls_frozen_excludes_later_contracts(self):
        krw, remain, topm = M._sls_frozen(synth_sls(), "2025Q2")
        # c2(2025-09-30 체결)는 제외: 2025Q4 원화 = c1 만 = 400,000 × (30/300) / 100 = 133.33억
        self.assertAlmostEqual(krw["2025Q4"], 400_000.0 * (30 / 300.0) / 100, places=3)
        self.assertAlmostEqual(remain, 400_000.0 * (6 / 10.0) / 100, places=3)          # 2025Q3~2026Q4 6분기 잔여
        self.assertAlmostEqual(topm["2025Q4"], 0.10)                                      # ④호황만

    def test_yard_runoff_bounded_by_uncovered_backlog(self):
        fin = synth_fin("010140", "삼성", quarters=M.q_range("2023Q1", "2026Q2"), rev0=200_000.0, g_q=0.0)
        ctx = FakeCtx(fins={"010140": fin}, slss={"010140": synth_sls()}, roles={"010140": "yard"})
        m = M.build_model("010140", ctx)
        self.assertEqual(m["driver_type"], "sls_marine_plus_uncovered_backlog_runoff")
        rm = rows_of(m)
        d = m["segments"][0]["driver"]
        self.assertAlmostEqual(d["uncovered_backlog_at_origin"], (1_200_000.0 - 500_000.0) / 100, places=2)
        est_q = [q for q in rm["매출조선"]["q"] if q > "2026Q2"]
        sls_krw = {q: ((45.0 if q <= "2026Q4" else 15.0) * 1400 / 100) for q in est_q}
        runoff = [rm["매출조선"]["q"][q]["v"] - sls_krw[q] for q in est_q if q <= "2027Q4"]
        self.assertTrue(all(r >= -0.01 for r in runoff))
        self.assertLessEqual(sum(runoff), d["uncovered_backlog_at_origin"] + 0.05)      # 공시 잔고를 넘어 소진하지 않는다
        self.assertAlmostEqual(runoff[0], d["runoff_per_q"], places=1)
        # 매출 = 매출조선 + 매출기타
        q = "2026Q3"
        self.assertAlmostEqual(rm["매출액"]["q"][q]["v"], rm["매출조선"]["q"][q]["v"] + rm["매출기타"]["q"][q]["v"], places=1)
        # OPM = 타겟 8% + 캘리브레이션(실측 OPM 20% − 8%) = 실측 수준
        self.assertAlmostEqual(rm["OPM"]["q"][q]["v"], 0.20, places=2)
        self.assertEqual(m["backtest"]["n"], 4)
        self.assertEqual(m["backtest"]["driver_at_freeze"], "sls_marine_plus_uncovered_backlog_runoff")

    def test_yard_without_sls_falls_back(self):
        ctx = FakeCtx(fins={"439260": synth_fin("439260")}, roles={"439260": "yard"})
        m = M.build_model("439260", ctx)
        self.assertEqual(m["driver_type"], "trend_seasonal")

    def test_segment_row_labels_are_per_model_not_process_global(self):
        # 같은 프로세스에서 삼성重('조선해양') 뒤에 한화오션('조선·해양플랜트')을 만들어도 각자 자기 부문 라벨 — 전역 ROW_META 는 오염되지 않는다
        # (예전엔 ROW_META.setdefault 로 먼저 만든 회사 라벨이 뒤 회사 행에 새어 들어가 빌드 순서에 따라 바이트가 달라졌다)
        qs = M.q_range("2023Q1", "2026Q2")
        s1, s2 = synth_sls("010140"), synth_sls("042660")
        for q in s2["reconcile"]:
            s2["reconcile"][q]["segments"] = ["조선·해양플랜트"]
        ctx = FakeCtx(fins={"010140": synth_fin("010140", "삼성", quarters=qs, rev0=200_000.0, g_q=0.0), "042660": synth_fin("042660", "한화", quarters=qs, rev0=200_000.0, g_q=0.0)},
                      slss={"010140": s1, "042660": s2}, roles={"010140": "yard", "042660": "yard"})
        m1 = M.build_model("010140", ctx)
        m2 = M.build_model("042660", ctx)
        self.assertEqual(rows_of(m1)["매출조선"]["label"], "매출 조선·해양(조선해양)")
        self.assertEqual(rows_of(m2)["매출조선"]["label"], "매출 조선·해양(조선·해양플랜트)")
        self.assertEqual(rows_of(m2)["OP조선"]["label"], "OP 조선·해양(조선·해양플랜트)")
        self.assertNotIn("매출조선", M.ROW_META)
        # 순서를 바꿔도 같은 바이트
        ctx2 = FakeCtx(fins=dict(ctx._fin), slss=dict(ctx._sls), roles=dict(ctx.roles))
        m2b = M.build_model("042660", ctx2)
        self.assertEqual(json.dumps(m2b, ensure_ascii=False, sort_keys=True), json.dumps(m2, ensure_ascii=False, sort_keys=True))

    def test_freeze_backlog_fixture_is_load_bearing(self):
        # 음성 통제(§14-6 ⑦): 픽스처 폴더를 비우면 freeze 2025Q2 의 _yard_backlog_at → None → 동결 모델이 추세 폴백으로 떨어진다 —
        # test_yard_runoff_bounded_by_uncovered_backlog 의 driver_at_freeze 단언이 픽스처 하나에 걸려 있음을 적어 둔다.
        fin = synth_fin("010140", "삼성", quarters=M.q_range("2023Q1", "2026Q2"), rev0=200_000.0, g_q=0.0)
        ctx = FakeCtx(fins={"010140": fin}, slss={"010140": synth_sls()}, roles={"010140": "yard"})
        self.assertEqual(M._yard_backlog_at("010140", "2025Q2", ["조선해양"]), 1_200_000.0)
        self.assertIsNone(M._fx_exposure_usd_m("010140", "2026Q2", ctx))                      # 픽스처엔 fx 표 없음 → 결정론적으로 None
        with tempfile.TemporaryDirectory() as td, mock.patch.object(M, "YARDS_CACHE", td):
            self.assertIsNone(M._yard_backlog_at("010140", "2025Q2", ["조선해양"]))
            self.assertEqual(M.build_model("010140", ctx)["backtest"]["driver_at_freeze"], "trend_seasonal")


class TestBuildAllTmp(unittest.TestCase):
    def test_build_all_writes_models_and_summary(self):
        ctx = FakeCtx(fins={"999999": synth_fin()}, roles={"999999": "equip", "888888": "equip"})
        old = M.MODELS_DIR
        with tempfile.TemporaryDirectory() as td:
            M.MODELS_DIR = td
            try:
                summary, built, xl = M.build_all(["999999", "888888"], ctx, write=True, xlsx=False)
            finally:
                M.MODELS_DIR = old
            self.assertEqual(sorted(built), ["999999"])
            self.assertTrue(os.path.isfile(os.path.join(td, "summary.json")))
            self.assertEqual(summary["counts"]["no_fin"], 1)
            self.assertEqual([r["stock"] for r in summary["rows"]], ["888888", "999999"])
            with open(os.path.join(td, "999999.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["stock"], "999999")


class TestVerifierFixes(SyntheticAssets, unittest.TestCase):
    """V4 검증에서 찾은 결함의 회귀 테스트 — 백테스트 실측만·실제 분기 라벨, 연결 공백 별도 보충, 전사 세그먼트 드라이버, 일회성 의심 표시, 세진 OP연결조정 실적."""

    def test_backtest_pairs_actual_only_with_correct_labels(self):
        # 실적이 2025Q4 까지만 → 짝은 2025Q3·Q4 두 개(2026Q1·Q2 는 추정 vs 추정 — 세지 않는다)
        m = M.build_model("999999", FakeCtx(fins={"999999": synth_fin(quarters=M.q_range("2023Q1", "2025Q4"))}, roles={"999999": "equip"}))
        bt = m["backtest"]
        self.assertEqual(bt["n"], 2)
        self.assertEqual([d["q"] for d in bt["detail"]], ["2025Q3", "2025Q4"])
        self.assertIn("실측 2분기만", bt["note"])
        self.assertIn("frozen_inputs", bt)
        # 중간 분기(2025Q3·Q4) 손익이 비면 라벨은 실제 분기(2026Q1·Q2)여야 한다(예전엔 enumerate 순번으로 2025Q3·Q4 라 적혔다)
        fin2 = synth_fin()
        for q in ("2025Q3", "2025Q4"):
            for sc in ("cons", "sep"):
                fin2[sc]["is"].pop(q)
        m2 = M.build_model("999999", FakeCtx(fins={"999999": fin2}, roles={"999999": "equip"}))
        self.assertEqual([d["q"] for d in m2["backtest"]["detail"]], ["2026Q1", "2026Q2"])
        rm2 = rows_of(m2)
        self.assertAlmostEqual(m2["backtest"]["detail"][0]["rev_act"], rm2["매출액"]["q"]["2026Q1"]["v"], places=1)
        self.assertEqual(rm2["매출액"]["q"]["2026Q1"]["kind"], "actual")

    def test_sep_fill_when_cons_missing(self):
        fin = synth_fin()
        gap = ["2024Q3", "2024Q4", "2025Q1"]
        for q in gap:
            for kind in ("is", "bs", "cf"):
                fin["cons"][kind].pop(q)
        f = M.Fin(fin)
        self.assertEqual(f.scope, "cons")
        self.assertEqual(f.sep_fill, gap)
        self.assertEqual(f.scope_of("2024Q4"), "sep")
        self.assertEqual(f.scope_of("2025Q2"), "cons")
        self.assertAlmostEqual(f.val("is", "2024Q4", "매출액(수익)"), fin["sep"]["is"]["2024Q4"]["매출액(수익)"] / 100)
        self.assertIsNone(M.Fin(synth_fin()).sep_fill or None)
        m = M.build_model("999999", FakeCtx(fins={"999999": fin}, roles={"999999": "equip"}))
        rm = rows_of(m)
        c = rm["매출액"]["q"]["2024Q4"]
        self.assertEqual(c["kind"], "actual")
        self.assertTrue(c["src"].startswith("fin.sep.is.매출액(수익)"), c["src"])
        self.assertIn("별도 보충", c["src"])
        self.assertEqual(rm["매출액"]["q"]["2025Q2"]["src"], "fin.cons.is.매출액(수익)")
        self.assertEqual(rm["자산총계"]["q"]["2024Q4"]["src"].split(" ")[0], "fin.sep.bs.자산총계")
        self.assertEqual(m["quality"]["sep_filled"], gap)
        self.assertTrue(any("별도 재무제표로 보충" in w for w in m["quality"]["warnings"]))
        self.assertEqual(m["status"], "partial")
        self.assertIsNotNone(rm["매출액"]["a"]["2024"]["v"])          # 연간 합이 다시 만들어진다
        self.assertIn("2024Q4", rm["EPS"]["q"])                          # 지배NI 도 보충된다

    def test_default_segment_carries_driver(self):
        # 고객 연결 없음 → 전사 세그먼트에 trend_seasonal 드라이버, 전사 행 = 매출액·영업이익
        m = M.build_model("111111", FakeCtx(fins={"111111": synth_fin("111111")}, roles={"111111": "equip"}))
        self.assertEqual([s["key"] for s in m["segments"]], ["전사"])
        self.assertEqual(m["segments"][0]["driver"]["type"], "trend_seasonal")
        self.assertEqual(len(m["segments"][0]["opm_path"]), 10)
        rm = rows_of(m)
        for q in ("2026Q2", "2027Q1"):
            self.assertAlmostEqual(rm["매출전사"]["q"][q]["v"], rm["매출액"]["q"][q]["v"], places=1)
            self.assertAlmostEqual(rm["OP전사"]["q"][q]["v"], rm["영업이익"]["q"][q]["v"], places=1)
        self.assertEqual(rm["매출전사"]["q"]["2027Q1"]["kind"], "estimate")
        self.assertNotIn("매출전사", [r[0] for r in m["views"]["분기"]])
        # 고객 연결 있음 → weights 합 1(모델 없는 고객은 제외 후 재정규화) · 격자가 고른 lag·변환·창 · corr · n · 비례계수 가 파일에 남는다
        # 조선사 매출은 기하급수 + 주기 5 의사잡음(기하급수만이면 모든 시차가 상관 1 이라 시차를 식별할 수 없다)
        qs = M.q_range("2022Q1", "2026Q2")
        yard = noisy_yard_fin("329180", "현중", qs)
        sup = synth_fin("222222", "공급사", quarters=qs, rev0=15_000.0, g_q=0.03)
        for i, q in enumerate(qs):
            pq = qs[i - 1] if i else q
            for sc in ("cons", "sep"):
                sup[sc]["is"][q]["매출액(수익)"] = 0.05 * yard["cons"]["is"][pq]["매출액(수익)"]
        ctx = FakeCtx(fins={"329180": yard, "222222": sup}, roles={"329180": "yard", "222222": "equip"},
                      suppliers={"cos": [{"stock": "222222", "nm": "공급사", "role": "equip",
                                          "yards": [{"yard": "329180", "mentions": 3}, {"yard": "HSHI", "mentions": 1}]}]})
        m2 = M.build_model("222222", ctx)
        self.assertEqual(m2["driver_type"], "customer_yard_revenue_weighted")
        self.assertEqual(m2["segments"][0]["key"], "전사")
        d = m2["segments"][0]["driver"]
        self.assertEqual(d["type"], "customer_yard_revenue_weighted")
        self.assertAlmostEqual(sum(d["weights"].values()), 1.0, places=6)
        self.assertEqual(set(d["weights"]), {"329180"})
        self.assertEqual(d["weights_key"], "suppliers_mentions")
        self.assertEqual((d["lag_q"], d["transform"]), (1, "level"))          # 정확히 t−1 수준 비례 → 상관 1.0, 가장 긴 창(19 → 짝 17)
        self.assertEqual((d["window_q"], d["n"]), (19, 17))
        self.assertAlmostEqual(d["corr"], 1.0, places=4)
        self.assertAlmostEqual(d["ratio_used"], 0.05, places=4)
        self.assertIn("009540 모델 없음", d["basis"])
        self.assertEqual(d["grid"]["n_candidates"], 45)                        # 가중치 1 × 시차 5 × 변환 3 × 창 3
        self.assertEqual(d["grid"]["top"][0]["corr"], d["corr"])
        self.assertIn("과적합", d["grid"]["overfit_note"])
        self.assertTrue(d["significance"]["significant_p05_uncorrected"])

    def test_one_off_detection_flags_spike_only(self):
        base = M.build_model("999999", FakeCtx(fins={"999999": synth_fin()}, roles={"999999": "equip"}))
        self.assertEqual(base["assumptions"]["one_offs_detected"], [])
        self.assertFalse(any("일회성 의심" in w for w in base["quality"]["warnings"]))
        fin = synth_fin()
        q = "2026Q2"
        for sc in ("cons", "sep"):
            is_ = fin[sc]["is"][q]
            spike = 50 * abs(is_["영업이익"])
            for k in ("금융손익", "법인세비용차감전계속사업이익", "당기순이익", "(지배주주지분)당기순이익"):
                is_[k] += spike
        m = M.build_model("999999", FakeCtx(fins={"999999": fin}, roles={"999999": "equip"}))
        det = m["assumptions"]["one_offs_detected"]
        self.assertEqual([d["q"] for d in det], [q])
        self.assertGreater(det[0]["nonop"], 0)
        self.assertTrue(any("일회성 의심 2026Q2" in w for w in m["quality"]["warnings"]))
        # 숫자는 바꾸지 않는다 — 실적 셀은 fin 그대로, 12M fwd EPS 는 추정 4분기만
        rm = rows_of(m)
        self.assertAlmostEqual(rm["당기순이익"]["q"][q]["v"], round(fin["cons"]["is"][q]["당기순이익"] / 100, 2), places=2)
        self.assertEqual(m["valuation"]["eps_fwd_quarters"], M.q_range("2026Q3", "2027Q2"))

    def test_sejin_op_adjustment_actual_filled(self):
        m = M.build_model("075580", sejin_ctx(vary=True))
        rm = rows_of(m)
        q = "2026Q2"
        c = rm["OP연결조정"]["q"][q]
        self.assertEqual(c["kind"], "actual")
        self.assertAlmostEqual(c["v"], rm["영업이익"]["q"][q]["v"] - rm["OP조선기자재"]["q"][q]["v"] - rm["OP종속사"]["q"][q]["v"], places=1)
        self.assertEqual(rm["OP연결조정"]["q"]["2027Q1"]["kind"], "estimate")


def noisy_yard_fin(stock, name, qs, rev0=300_000.0, g_q=0.03):
    """기하급수 × 주기 5 의사잡음(0.85~1.15) 조선사 매출 — 시차·변환이 식별되게(순수 기하급수는 모든 시차 상관 1)."""
    fin = synth_fin(stock, name, quarters=qs, rev0=rev0, g_q=g_q)
    for i, q in enumerate(qs):
        v = rev0 * (1 + g_q) ** i * (1 + 0.15 * (((i * 7) % 5) - 2) / 2)
        for sc in ("cons", "sep"):
            fin[sc]["is"][q]["매출액(수익)"] = v
    return fin


class TestLinkGrid(SyntheticAssets, unittest.TestCase):
    """F2 — 고객 연동 격자 탐색(시차 0~4 × 창 8/12/19 × 수준·YoY·4Q합): 식별·폴백·후보표·변환별 예측식·합병 규칙."""

    QS = M.q_range("2022Q1", "2026Q2")

    def _ctx(self, sup_fn, stock="222222", noisy=True):
        yard = noisy_yard_fin("329180", "현중", self.QS) if noisy else synth_fin("329180", "현중", quarters=self.QS, rev0=300_000.0, g_q=0.03)
        x = {q: yard["cons"]["is"][q]["매출액(수익)"] for q in self.QS}
        sup = synth_fin(stock, "공급사", quarters=self.QS, rev0=15_000.0, g_q=0.0)
        for i, q in enumerate(self.QS):
            v = sup_fn(i, q, x)
            for sc in ("cons", "sep"):
                sup[sc]["is"][q]["매출액(수익)"] = v
        return FakeCtx(fins={"329180": yard, stock: sup}, roles={"329180": "yard", stock: "equip"},
                       suppliers={"cos": [{"stock": stock, "nm": "공급사", "role": "equip", "yards": [{"yard": "329180", "mentions": 2}]}]}), x

    def test_transforms_and_seasonal_share(self):
        s = {"2024Q1": 100.0, "2024Q2": 100.0, "2024Q3": 100.0, "2024Q4": 200.0, "2025Q1": 110.0, "2025Q2": 110.0, "2025Q3": 110.0, "2025Q4": 220.0}
        self.assertAlmostEqual(M._t_yoy(s)["2025Q4"], 0.1)
        self.assertNotIn("2024Q4", M._t_yoy(s))
        self.assertEqual(M._t_ma4(s)["2025Q4"], 550.0)
        self.assertNotIn("2024Q3", M._t_ma4(s))
        share, basis = M._seasonal_share(s)
        self.assertAlmostEqual(share[4], 0.4)
        self.assertAlmostEqual(sum(share.values()), 1.0)
        self.assertIn("2025, 2024", basis)
        share0, basis0 = M._seasonal_share({"2025Q1": 1.0})
        self.assertEqual(share0, {1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25})
        self.assertIn("균등", basis0)

    def test_r_crit(self):
        self.assertIsNone(M._r_crit_p05(3))
        self.assertAlmostEqual(M._r_crit_p05(8), 0.7067, places=4)
        self.assertAlmostEqual(M._r_crit_p05(12), 0.576, places=3)
        self.assertLess(M._r_crit_p05(19), M._r_crit_p05(8))

    def test_grid_identifies_lag2_level(self):
        # 매출 = 0.05 × 고객(t−2) 정확히 → 시차 2·수준·상관 1.0, 첫 추정분기 = 0.05 × 고객 2026Q1 실적
        ctx, x = self._ctx(lambda i, q, x: 0.05 * x[self.QS[max(i - 2, 0)]])
        m = M.build_model("222222", ctx)
        d = m["segments"][0]["driver"]
        self.assertEqual(m["driver_type"], "customer_yard_revenue_weighted")
        self.assertEqual((d["lag_q"], d["transform"]), (2, "level"))
        self.assertAlmostEqual(d["corr"], 1.0, places=4)
        self.assertAlmostEqual(d["ratio_used"], 0.05, places=4)
        rm = rows_of(m)
        self.assertAlmostEqual(rm["매출액"]["q"]["2026Q3"]["v"], 0.05 * x["2026Q1"] / 100, places=1)
        self.assertIn("t−2", rm["매출액"]["q"]["2026Q3"]["basis"])
        self.assertEqual(d["grid"]["best_by_transform"]["level"]["lag_q"], 2)
        self.assertEqual(len(d["grid"]["table"]), 45)
        self.assertTrue(all(len(v) == 3 for v in d["grid"]["table"].values()))

    def test_grid_identifies_yoy(self):
        # 매출 = 계절계수(Q1 0.6·Q2 0.9·Q3 1.1·Q4 1.4) × 고객(t−1) → 수준은 계절성 때문에 상관 < 1, YoY 는 정확히 고객 YoY(t−1) → β 1.0
        season = {1: 0.6, 2: 0.9, 3: 1.1, 4: 1.4}
        ctx, x = self._ctx(lambda i, q, x: 0.05 * season[int(q[5])] * x[self.QS[max(i - 1, 0)]])
        m = M.build_model("222222", ctx)
        d = m["segments"][0]["driver"]
        self.assertEqual((d["lag_q"], d["transform"]), (1, "yoy"))
        self.assertAlmostEqual(d["corr"], 1.0, places=4)
        self.assertAlmostEqual(d["ratio_used"], 1.0, places=4)
        self.assertIn("beta_yoy", d["coef_kind"])
        rm = rows_of(m)
        y_prev = rm["매출액"]["q"]["2025Q3"]["v"]
        g = x["2026Q2"] / x["2025Q2"] - 1                                   # 고객지수 YoY(t−1) at 2026Q3
        self.assertAlmostEqual(rm["매출액"]["q"]["2026Q3"]["v"], y_prev * (1 + M.clip(g, *M.GROWTH_CLIP)), places=1)
        self.assertIn("전년동기", rm["매출액"]["q"]["2026Q3"]["basis"])
        self.assertLess(d["grid"]["best_by_transform"]["level"]["corr"], 0.999)

    def test_grid_rejects_below_threshold_with_table(self):
        # 고객(순수 기하급수)과 무관한 교대 패턴 → 수준 상관 |r| ≈ 0.07, YoY·4Q합은 분산 0 → 격자 최대 < 0.30 → 추세 폴백 + 기각 기록(후보표·유의 임계·최선 조합)
        # (의사잡음 고객 매출로 하면 45 후보 중 하나가 우연히 0.30 을 넘는다 — 다중비교 효과 그 자체)
        ctx, _ = self._ctx(lambda i, q, x: 10_000.0 + 3_000.0 * (1 if i % 2 else -1), noisy=False)
        m = M.build_model("222222", ctx)
        self.assertEqual(m["driver_type"], "trend_seasonal")
        d = m["segments"][0]["driver"]
        rj = d["customer_link_rejected"]
        self.assertLess(rj["corr"], M.CORR_MIN)
        self.assertEqual(rj["transform"], "level")
        self.assertIn("grid", rj)
        self.assertGreaterEqual(rj["grid"]["n_with_corr"], 1)
        self.assertLess(rj["grid"]["n_with_corr"], rj["grid"]["n_candidates"])           # YoY·4Q합 은 분산 0 → 상관 없음
        self.assertIn("r_crit_p05_two_sided", rj["significance"])
        self.assertFalse(rj["significance"]["significant_p05_uncorrected"])
        self.assertIn("격자 최대 상관", d["basis"])
        self.assertTrue(any("폴백" in w for w in m["quality"]["warnings"]))
        # 자사 매출이 상수면 모든 후보의 상관이 정의되지 않는다 → 사유는 '분산 0'(덮지 못함이 아니다)
        ctx0, _ = self._ctx(lambda i, q, x: 10_000.0, noisy=False)
        m0 = M.build_model("222222", ctx0)
        self.assertEqual(m0["driver_type"], "trend_seasonal")
        self.assertIn("분산 0", m0["segments"][0]["driver"]["basis"])

    def test_link_forecast_ma4_uses_seasonal_share(self):
        X = {"2026Q3": 1000.0, "2026Q4": 1100.0}
        best = {"transform": "ma4", "lag": 1, "coef": 0.2, "n": 8, "corr": 0.9, "window": 8}
        share = ({1: 0.2, 2: 0.2, 3: 0.2, 4: 0.4}, "합성 계절비중")
        out = M._link_forecast(best, X, {}, ["2026Q3", "2026Q4"], share)
        self.assertAlmostEqual(out["2026Q3"][0], 0.2 * 1000.0 * 0.2)
        self.assertAlmostEqual(out["2026Q4"][0], 0.2 * 1100.0 * 0.4)
        self.assertIn("계절비중 Q4 0.400", out["2026Q4"][1])
        self.assertIn("4분기 이동합(t−1)", out["2026Q4"][1])

    def test_weight_candidates_and_merger_rule(self):
        # 세진 그룹은 suppliers 언급이 없어도 레퍼런스 계열 4개가 후보, 일반 기자재는 suppliers 언급만
        ctx = TestSupplierLink()._ctx(vary=True)
        keys = [c[0] for c in M._customer_weight_candidates("075580", ctx)]
        self.assertEqual(keys, ["ref_base", "ref_deckhouse", "ref_deckhouse_alt", "ref_upperdeck"])
        for _, w, _ in M._customer_weight_candidates("333430", ctx):
            self.assertAlmostEqual(sum(w.values()), 1.0, places=9)
        self.assertEqual(M._customer_weight_candidates("111111", ctx), [])
        w0, b0 = M._customer_weights("075580", ctx)
        self.assertAlmostEqual(w0["010620"], 0.9 / 1.1)
        self.assertIn("HMsb 0.9", b0)
        # 미포(2025Q3 까지) → HD현대重 체인링크 규칙이 detail 과 driver.merger_rule 에 남는다
        det = {}
        idx, note, used = M._customer_index(w0, ctx, None, lag=1, detail=det)
        self.assertEqual(det["mergers"][0]["merged"], "010620")
        self.assertEqual(det["mergers"][0]["into"], "329180")
        self.assertEqual(det["mergers"][0]["from"], "2025Q4")
        self.assertEqual(det["sources"]["010620"]["last_actual"], "2025Q3")
        self.assertEqual(det["sources"]["010620"]["estimates_from"], "2025Q4")
        m = M.build_model("075580", ctx)
        d = m["segments"][0]["driver"]
        self.assertEqual(d["type"], "customer_yard_revenue_weighted")
        self.assertTrue(any("2025Q4 부터 010620" in r for r in d["merger_rule"]))
        self.assertEqual(d["weights_key"], "ref_base")
        self.assertIn("2025Q4", rows_of(m)["매출조선기자재"]["q"]["2027Q1"]["basis"])
        link = M.summary_row(m)["link"]
        self.assertTrue(link["adopted"])
        self.assertEqual(link["weights_key"], "ref_base")
        self.assertEqual((link["lag_q"], link["transform"], link["corr"]), (d["lag_q"], d["transform"], d["corr"]))

    def test_grid_determinism(self):
        ctx, _ = self._ctx(lambda i, q, x: 0.05 * x[self.QS[max(i - 2, 0)]])
        a = json.dumps(M.build_model("222222", ctx), ensure_ascii=False, sort_keys=True)
        ctx2, _ = self._ctx(lambda i, q, x: 0.05 * x[self.QS[max(i - 2, 0)]])
        b = json.dumps(M.build_model("222222", ctx2), ensure_ascii=False, sort_keys=True)
        self.assertEqual(a, b)

    def test_n_eff_filters_short_ma4(self):
        # 라운드 7 L5: 4분기 이동합은 인접 점이 3분기를 공유 → 유효 표본 n−3. 공급사 실적 8분기면 ma4 는 n 5(n_eff 2 < 4) 로 격자에서 빠지고 수준·YoY 만 남는다
        self.assertEqual((M._n_eff("ma4", 8), M._n_eff("level", 8), M._n_eff("yoy", 8)), (5, 8, 8))
        yard = noisy_yard_fin("329180", "현중", self.QS)
        x = {q: yard["cons"]["is"][q]["매출액(수익)"] for q in self.QS}
        keep = M.q_range("2024Q3", "2026Q2")
        sup = synth_fin("222222", "공급사", quarters=keep, rev0=15_000.0, g_q=0.0)
        for q in keep:
            for sc in ("cons", "sep"):
                sup[sc]["is"][q]["매출액(수익)"] = 0.05 * x[M.q_add(q, -2)]
        ctx = FakeCtx(fins={"329180": yard, "222222": sup}, roles={"329180": "yard", "222222": "equip"},
                      suppliers={"cos": [{"stock": "222222", "nm": "공급사", "role": "equip", "yards": [{"yard": "329180", "mentions": 2}]}]})
        m = M.build_model("222222", ctx)
        d = m["segments"][0]["driver"]
        grid = d["grid"] if d["type"] == "customer_yard_revenue_weighted" else d["customer_link_rejected"]["grid"]
        keys = list(grid["table"])
        self.assertEqual([k for k in keys if "|ma4|" in k], [])
        self.assertTrue(any("|level|" in k for k in keys))
        self.assertTrue(all(len(v) == 3 for v in grid["table"].values()))
        self.assertTrue(all("n_eff" in r and r["n_eff"] >= M.LINK_MIN_N for r in grid["top"]))
        self.assertIn("n_eff = n − 3", grid["overfit_note"])

    def test_significance_reports_n_eff_and_switch(self):
        # 라운드 7 L5: n_eff 기준 임계 r 은 기록만(r_crit_p05_neff·significant_p05_neff), 게이트는 LINK_SIG_USE_NEFF(기본 False → n 기준)
        best = {"transform": "ma4", "n": 8, "corr": 0.85, "n_eff": 5}
        sig = M._link_significance(best)
        self.assertEqual((sig["n_eff"], sig["r_crit_p05_neff"], sig["r_crit_p05_two_sided"]), (5, 0.8783, 0.7067))
        self.assertFalse(sig["significant_p05_neff"])
        self.assertTrue(sig["significant_p05_uncorrected"])
        self.assertEqual(sig["gate"], "n")
        with mock.patch.object(M, "LINK_SIG_USE_NEFF", True):
            sig2 = M._link_significance(best)
            self.assertFalse(sig2["significant_p05_uncorrected"])
            self.assertEqual(sig2["gate"], "n_eff")
        self.assertEqual(M._link_significance({"transform": "ma4", "n": 8, "corr": 0.85})["n_eff"], 5)       # n_eff 없는 입력은 변환에서 계산
        self.assertEqual(M._link_significance({"transform": "level", "n": 8, "corr": 0.85})["n_eff"], 8)


class TestLinkEligibility(SyntheticAssets, unittest.TestCase):
    """라운드 7 L5 — 고객 연동 후보 자격: suppliers yards 가 related 만이고 Σshare(%) < RELATED_SHARE_MIN 이면 격자·OOS 전 기각(driver_fallback 'eligibility').
    ifrs8·contract·text(basis 없는 레거시 포함)가 하나라도 있거나 Σrelated ≥ 문턱이면 통과하고 가중치는 바꾸지 않는다."""

    QS = M.q_range("2022Q1", "2026Q2")
    STOCK = "222222"

    def _ctx(self, yards):
        # 공급사 매출 = 0.05 × 현중(t−2) 정확히(격자가 반드시 채택하는 신호) — 자격 규칙만이 결과를 가른다. 삼성重 은 현중과 같은 잡음 모양(스케일만 다름)
        yard = noisy_yard_fin("329180", "현중", self.QS)
        x = {q: yard["cons"]["is"][q]["매출액(수익)"] for q in self.QS}
        sup = synth_fin(self.STOCK, "공급사", quarters=self.QS, rev0=15_000.0, g_q=0.0)
        for i, q in enumerate(self.QS):
            for sc in ("cons", "sep"):
                sup[sc]["is"][q]["매출액(수익)"] = 0.05 * x[self.QS[max(i - 2, 0)]]
        fins = {"329180": yard, self.STOCK: sup, "010140": noisy_yard_fin("010140", "삼성重", self.QS, rev0=200_000.0)}
        roles = {"329180": "yard", "010140": "yard", self.STOCK: "equip"}
        return FakeCtx(fins=fins, roles=roles, suppliers={"cos": [{"stock": self.STOCK, "nm": "공급사", "role": "equip", "yards": yards}]})

    @staticmethod
    def _related(share, yard="329180"):
        return {"yard": yard, "basis": "related", "share": share, "share_est": True, "mentions": None}

    def test_related_tiny_share_rejected_as_eligibility(self):
        ctx = self._ctx([self._related(0.03)])                                                     # 한화시스템 272210 형태
        m = M.build_model(self.STOCK, ctx)
        self.assertEqual((m["driver_type"], m["driver_fallback"]), ("trend_seasonal", "eligibility"))
        d = m["segments"][0]["driver"]
        rj = d["customer_link_rejected"]
        self.assertEqual(rj["rejected_by"], "eligibility")
        self.assertIs(rj["eligibility"]["eligible"], False)
        self.assertEqual((rj["eligibility"]["related_share_sum"], rj["eligibility"]["bases"]), (0.03, ["related"]))
        self.assertEqual((rj["weights"], rj["weights_key"]), ({"329180": 1.0}, "suppliers_mentions"))
        self.assertIs(rj["selection_oos"]["adopted"], False)
        self.assertIn("자격", rj["selection_oos"]["note"])
        self.assertTrue(all(rj[k] is None for k in ("corr", "n", "n_eff", "transform", "lag_q", "window_q", "grid", "significance")))
        self.assertIn("자격 미달", d["basis"])
        self.assertIn("0.03%", d["basis"])
        link = M.summary_row(m)["link"]
        self.assertEqual((link["adopted"], link["rejected_by"], link["corr"], link["n"], link["weights_key"], link["oos_decision"]),
                         (False, "eligibility", None, None, "suppliers_mentions", "rejected"))
        self.assertEqual(M.summary_row(m)["driver_fallback"], "eligibility")
        self.assertTrue(any("폴백" in w for w in m["quality"]["warnings"]))
        self.assertFalse([r for r in m["quality"]["status_reasons"] if "폴백" in r or "자격" in r])    # T6 D7: 폴백은 status 와 무관(합성 fin 의 항등식 사유만)

    def test_related_share_threshold_boundary(self):
        self.assertEqual(M.RELATED_SHARE_MIN, 5.0)
        ok = M.build_model(self.STOCK, self._ctx([self._related(5.0)]))
        self.assertEqual(ok["driver_type"], "customer_yard_revenue_weighted")
        self.assertEqual(ok["segments"][0]["driver"]["eligibility"]["related_share_sum"], 5.0)
        no = M.build_model(self.STOCK, self._ctx([self._related(4.99)]))
        self.assertEqual((no["driver_type"], no["driver_fallback"]), ("trend_seasonal", "eligibility"))
        ctx2 = self._ctx([self._related(3.0), self._related(2.5, yard="010140")])                 # 합 5.5 로 판정(yard 단위가 아니다)
        two = M.build_model(self.STOCK, ctx2)
        self.assertEqual(two["driver_type"], "customer_yard_revenue_weighted")
        d = two["segments"][0]["driver"]
        self.assertEqual((d["eligibility"]["related_share_sum"], d["eligibility"]["eligible"]), (5.5, True))
        self.assertEqual(d["weights"], M.r4_weights(M._suppliers_weights(self.STOCK, ctx2)))
        self.assertEqual(sorted(d["weights"]), ["010140", "329180"])

    def test_ifrs8_without_share_is_eligible(self):
        ctx = self._ctx([{"yard": "329180", "basis": "ifrs8", "share": None, "mentions": None}])  # 한라IMS 092460 형태(주요고객 이름만, 금액 없음)
        d = M.build_model(self.STOCK, ctx)["segments"][0]["driver"]
        self.assertEqual((d["type"], d["weights"]), ("customer_yard_revenue_weighted", {"329180": 1.0}))
        self.assertEqual((d["eligibility"]["eligible"], d["eligibility"]["bases"], d["eligibility"]["related_share_sum"]), (True, ["ifrs8"], None))
        self.assertIn("ifrs8", d["eligibility"]["reason"])
        self.assertEqual(d["n_eff"], M._n_eff(d["transform"], d["n"]))
        self.assertEqual(d["significance"]["n_eff"], d["n_eff"])

    def test_related_plus_text_keeps_weights(self):
        ctx = self._ctx([self._related(0.5), {"yard": "010140", "basis": "text", "share": None, "mentions": 2}])
        elig = M._link_eligibility(self.STOCK, ctx)
        self.assertEqual((elig["eligible"], elig["bases"], elig["related_share_sum"]), (True, ["related", "text"], None))
        d = M.build_model(self.STOCK, ctx)["segments"][0]["driver"]
        self.assertEqual(d["type"], "customer_yard_revenue_weighted")
        self.assertEqual(d["weights"], M.r4_weights(M._suppliers_weights(self.STOCK, ctx)))      # 자격 규칙은 가중치를 바꾸지 않는다(share 만 — text 는 0.0)
        self.assertEqual(d["weights"]["329180"], 1.0)

    def test_legacy_yards_without_basis_eligible(self):
        d = M.build_model(self.STOCK, self._ctx([{"yard": "329180", "mentions": 2}]))["segments"][0]["driver"]   # 구버전 형식(basis 없음 → text)
        self.assertEqual(d["type"], "customer_yard_revenue_weighted")
        self.assertEqual((d["eligibility"]["eligible"], d["eligibility"]["bases"]), (True, ["text"]))

    def test_sejin_group_not_gated(self):
        ctx = TestSupplierLink()._ctx(vary=True)                                                  # suppliers yards 없음 → 레퍼런스 가중치 경로
        elig = M._link_eligibility("075580", ctx)
        self.assertEqual((elig["eligible"], elig["yards"]), (True, []))
        self.assertIn("연결 없음", elig["reason"])
        m = M.build_model("075580", ctx)
        self.assertEqual(m["driver_type"], "customer_yard_revenue_weighted")
        self.assertTrue(m["segments"][0]["driver"]["eligibility"]["eligible"])

    def test_eligibility_determinism(self):
        a = json.dumps(M.build_model(self.STOCK, self._ctx([self._related(0.03)])), ensure_ascii=False, sort_keys=True)
        b = json.dumps(M.build_model(self.STOCK, self._ctx([self._related(0.03)])), ensure_ascii=False, sort_keys=True)
        self.assertEqual(a, b)


def synth_panel(stock="010140", fq=None, base_per_q=200.0, scale=(0.5, 1.0, 1.5), none=False, rev_field="new_order_revenue", new_orders=50_000.0):
    """forecast_panel companies[] 한 회사(스펙 5-3 이 읽는 부분만): scenarios.{conservative,base,optimistic}.quarterly[].new_order_revenue(KRW_million).
    분기별 base = base_per_q × (i+1) 백만원 → 보수/낙관은 scale 배. none=True 면 값이 전부 None(필드 둘 다).
    rev_field="covered_scope_new_revenue" 면 한화오션·HJ 처럼 전범위 new_order_revenue 는 None 이고 모델 대상 부문만의 covered_scope_new_revenue 가 값을 가진다.
    new_orders = 분기 신규수주(KRW_million, base 만 의미 — 공시 체결 대비 비율·post-origin 제외 비율의 근거)."""
    fq = fq or M.q_range("2026Q3", "2028Q4")
    sc = {}
    for name, k in zip(M.PANEL_SCENARIOS, scale):
        rows = []
        for i, q in enumerate(fq):
            v = None if none else base_per_q * (i + 1) * k
            rows.append({"quarter": q, "horizon": i + 1, "value": None if none else 1_000_000.0, "existing_backlog_revenue": None,
                         "new_order_revenue": v if rev_field == "new_order_revenue" else None,
                         "covered_scope_new_revenue": v if rev_field == "covered_scope_new_revenue" else None,
                         "new_orders": None if none else new_orders})
        sc[name] = {"quarterly": rows, "annual": [],
                    "assumptions": {"order_basis": "positive_part_of_empirical_net_replenishment", "new_order_arrival": "quarter_end; first_recognition_next_quarter",
                                    "progress_curve": "R1_smoothstep_unfitted", "calibrated": False}}
    out = {"stock": stock, "company_name": "합성", "status": "partial", "reason_codes": ["book_value_only"], "origin": "2026Q2", "scenarios": sc,
           "industry_axes": {"schedule_exclusions": {"not_known_at_origin": 3}}}
    if rev_field != "new_order_revenue":
        out["status"], out["reason_codes"] = "insufficient_data", ["segment_gap"]
        out["coverage"] = {"modeled_segments": ["상선"], "excluded_segments": ["특수선"], "reported_backlog": 900_000.0, "modeled_backlog": 600_000.0}
    return out


class TestYardNewOrders(SyntheticAssets, unittest.TestCase):
    """결정 ⓓ — forecast_panel base 신규수주 매출을 매출조선신규 행으로 넣고 매출조선·매출액에 포함, 보수/낙관은 scenarios 블록에만."""

    def _pair(self, panel):
        qs = M.q_range("2023Q1", "2026Q2")
        fin = synth_fin("010140", "삼성", quarters=qs, rev0=200_000.0, g_q=0.0)
        ctx0 = FakeCtx(fins={"010140": fin}, slss={"010140": synth_sls()}, roles={"010140": "yard"})
        ctx1 = FakeCtx(fins={"010140": fin}, slss={"010140": synth_sls()}, roles={"010140": "yard"})
        ctx1.panel = {"010140": panel}
        return M.build_model("010140", ctx0), M.build_model("010140", ctx1), ctx1

    def test_base_included_and_scenarios_separate(self):
        m0, m1, ctx1 = self._pair(synth_panel())
        r0, r1 = rows_of(m0), rows_of(m1)
        fq = [q for q in m1["periods"]["quarters"] if q > "2026Q2"]
        d = m1["segments"][0]["driver"]
        self.assertTrue(d["new_orders_included"])
        self.assertTrue(m1["new_orders_included"])
        self.assertFalse(m0["new_orders_included"])
        self.assertIn("매출조선신규", r1)
        self.assertIn("OP조선신규", r1)
        self.assertNotIn("매출조선신규", r0)
        self.assertIn("매출조선에 포함", r1["매출조선신규"]["label"])
        for i, q in enumerate(fq):
            new = 200.0 * (i + 1) / 100                                        # 백만원 → 억원
            self.assertAlmostEqual(r1["매출조선신규"]["q"][q]["v"], new, places=2)
            self.assertEqual(r1["매출조선신규"]["q"][q]["kind"], "estimate")
            self.assertIn("forecast_panel", r1["매출조선신규"]["q"][q]["basis"])
            self.assertIn("calibrated=false", r1["매출조선신규"]["q"][q]["basis"])
            # 매출조선 = 기존(패널 없는 모델과 같음) + 신규, 매출액 = 매출조선 + 매출기타, OP조선신규 = 신규 × OPM
            self.assertAlmostEqual(r1["매출조선"]["q"][q]["v"] - r0["매출조선"]["q"][q]["v"], new, places=1)
            self.assertAlmostEqual(r1["매출액"]["q"][q]["v"], r1["매출조선"]["q"][q]["v"] + r1["매출기타"]["q"][q]["v"], places=1)
            self.assertAlmostEqual(r1["OP조선신규"]["q"][q]["v"], new * r1["OPM"]["q"][q]["v"], places=1)
            self.assertIn("신규수주", r1["매출조선"]["q"][q]["basis"])
            self.assertIn("신규수주", r1["OPM"]["q"][q]["basis"])
        # origin 회계연도의 실적 분기는 정의상 0 → FY2026 합계가 partial 이 아니다. T6 D8: fin 값이 아니므로 kind estimate + basis '정의상 0'
        for k in ("매출조선신규", "OP조선신규"):
            for q in ("2026Q1", "2026Q2"):
                c = r1[k]["q"][q]
                self.assertEqual((c["v"], c["kind"]), (0.0, "estimate"), (k, q))
                self.assertIn("정의상 0", c["basis"])
                self.assertNotIn("src", c)
        self.assertAlmostEqual(r1["매출조선신규"]["a"]["2026"]["v"], (200.0 + 400.0) / 100, places=2)
        self.assertEqual(r1["매출조선신규"]["a"]["2026"]["kind"], "estimate")
        # 시나리오 블록: base = 행과 동일, existing_only = 패널 없는 모델, 보수 < base < 낙관, OP 는 행 OP ± 델타 × OPM
        sc = m1["scenarios"]
        self.assertEqual(sc["meta"]["in_rows"], "base")
        self.assertFalse(sc["meta"]["calibrated"])
        for y in ("2026", "2027", "2028"):
            self.assertAlmostEqual(sc["base"]["annual"][y]["rev"], r1["매출액"]["a"][y]["v"], places=2)
            self.assertAlmostEqual(sc["base"]["annual"][y]["op"], r1["영업이익"]["a"][y]["v"], places=2)
            self.assertAlmostEqual(sc["existing_only"]["annual"][y]["rev"], r0["매출액"]["a"][y]["v"], places=1)
            self.assertLess(sc["conservative"]["annual"][y]["rev"], sc["base"]["annual"][y]["rev"])
            self.assertLess(sc["base"]["annual"][y]["rev"], sc["optimistic"]["annual"][y]["rev"])
            self.assertEqual(sc["conservative"]["annual"][y]["new_order_revenue"], r2(sc["base"]["annual"][y]["new_order_revenue"] * 0.5))
        self.assertTrue(sc["base"]["in_rows"])
        self.assertFalse(sc["optimistic"]["in_rows"])
        q = "2027Q1"
        delta = sc["optimistic"]["quarterly"][q]["new_order_revenue"] - sc["base"]["quarterly"][q]["new_order_revenue"]
        self.assertAlmostEqual(sc["optimistic"]["quarterly"][q]["op"] - r1["영업이익"]["q"][q]["v"], delta * r1["OPM"]["q"][q]["v"], places=1)
        self.assertEqual(sc["base"]["annual"]["2026"]["kind"], "mixed")
        # 항등식은 그대로, 상태는 full
        self.assertTrue(m1["quality"]["identities_ok"], m1["quality"]["identity_mismatches"])
        self.assertTrue(any("신규수주 매출" in w and "합산 안 함" in w for w in m1["quality"]["warnings"]))
        # 패널 모듈 라벨은 '반영됨'
        pm = next(mod for mod in m1["modules"] if mod["key"] == "forecast_panel")
        self.assertTrue(any("반영됨" in r["label"] for r in pm["rows"] if r["key"] == "panel_new_order_revenue"))
        # summary_row
        s = M.summary_row(m1)
        self.assertTrue(s["new_orders_included"])
        self.assertAlmostEqual(s["scenarios"]["2027E"]["base"]["rev"], r1["매출액"]["a"]["2027"]["v"], places=2)
        self.assertEqual(set(s["scenarios"]["2028E"]), {"existing_only", "conservative", "base", "optimistic"})
        self.assertIsNone(M.summary_row(m0)["scenarios"])
        # 백테스트(동결 2025Q2)는 패널을 쓰지 않는다 — 동결 모델엔 신규 행이 없고 성적도 같다
        bm = ctx1.model("010140", origin="2025Q2")
        self.assertNotIn("매출조선신규", rows_of(bm))
        self.assertFalse(bm["segments"][0]["driver"]["new_orders_included"])
        self.assertEqual(m1["backtest"]["revenue_wape_pct"], m0["backtest"]["revenue_wape_pct"])
        self.assertEqual(m1["backtest"]["n"], 4)

    def test_panel_all_none_or_missing_falls_back_with_warning(self):
        m0, m1, _ = self._pair(synth_panel(none=True))
        self.assertFalse(m1["new_orders_included"])
        self.assertNotIn("매출조선신규", rows_of(m1))
        self.assertIsNone(m1["scenarios"])
        self.assertEqual(rows_of(m1)["매출액"]["a"]["2028"]["v"], rows_of(m0)["매출액"]["a"]["2028"]["v"])
        self.assertTrue(any("신규수주 매출 미포함" in w and "covered_scope_new_revenue 값 없음" in w for w in m1["quality"]["warnings"]))
        self.assertIn("미포함", m1["segments"][0]["driver"]["basis"])
        self.assertTrue(any("신규수주 매출 미포함" in w and "forecast_panel 에 010140 없음" in w for w in m0["quality"]["warnings"]))
        self.assertEqual(m0["driver_type"], "sls_marine_plus_uncovered_backlog_runoff")

    def test_covered_scope_fallback_included_and_flagged(self):
        """한화오션·HJ 형 패널(전범위 new_order_revenue None, covered_scope_new_revenue 있음) → 같은 행·같은 시나리오로 포함하되 폴백·저신뢰로 표기."""
        m0, mf, _ = self._pair(synth_panel(rev_field="covered_scope_new_revenue"))
        _, mn, _ = self._pair(synth_panel())                                      # 같은 숫자를 new_order_revenue 로 준 기준
        self.assertTrue(mf["new_orders_included"])
        self.assertIn("매출조선신규", rows_of(mf))
        for y in ("2026", "2027", "2028"):                                         # 필드만 다르고 값·인식은 같다
            self.assertAlmostEqual(rows_of(mf)["매출액"]["a"][y]["v"], rows_of(mn)["매출액"]["a"][y]["v"], places=6)
        self.assertGreater(rows_of(mf)["매출액"]["a"]["2028"]["v"], rows_of(m0)["매출액"]["a"]["2028"]["v"])
        no = mf["segments"][0]["driver"]["new_orders"]
        self.assertEqual((no["source_field"], no["fallback"], no["confidence"]), ("covered_scope_new_revenue", True, "low"))
        self.assertEqual(no["panel_scope"]["modeled_segments"], ["상선"])
        self.assertEqual(no["panel_scope"]["excluded_segments"], ["특수선"])
        self.assertEqual(no["panel_scope"]["modeled_backlog_eok"], 6000.0)
        self.assertIn("특수선", no["fallback_note"])
        self.assertIn("제외 부문(특수선)의 신규분은 반영되지 않는다", no["fallback_note"])
        meta = mf["scenarios"]["meta"]
        self.assertEqual((meta["source_field"], meta["fallback"], meta["confidence"]), ("covered_scope_new_revenue", True, "low"))
        self.assertTrue(any(w.startswith("신규수주 폴백(저신뢰)") for w in mf["quality"]["warnings"]))
        self.assertIn("covered_scope_new_revenue", mf["segments"][0]["driver"]["basis"])
        # 전범위 필드가 있으면 그것을 쓰고 폴백이 아니다
        nn = mn["segments"][0]["driver"]["new_orders"]
        self.assertEqual((nn["source_field"], nn["fallback"], nn["confidence"]), ("new_order_revenue", False, "panel_default"))
        self.assertIsNone(nn["fallback_note"])
        self.assertIsNone(nn["ledger_crosscheck"])
        # 폴백 라벨: 패널 모듈 행에도 '모델 대상 부문만·폴백·저신뢰'
        pm = next(mod for mod in mf["modules"] if mod["key"] == "forecast_panel")
        self.assertTrue(any("폴백·저신뢰" in r["label"] for r in pm["rows"] if r["key"] == "panel_new_order_revenue"))

    def test_fallback_verdict_follows_ledger_ratio(self):
        """폴백 문구는 패널 ÷ 공시 체결 비율로 갈린다: 0.5~1.5 대체로 같은 규모 · >1.5 상향 편향 가능. <0.5 는 라운드 7부터 ledger_signing_rate 전환(아래)."""
        cases = ((50_000.0, 1.0, "대체로 같은 규모"), (200_000.0, 4.0, "상향 편향 가능"))
        for mn_orders, ratio, text in cases:
            _, m, _ = self._pair(synth_panel(rev_field="covered_scope_new_revenue", new_orders=mn_orders))
            no = m["segments"][0]["driver"]["new_orders"]
            cc = no["ledger_crosscheck"]
            self.assertAlmostEqual(cc["panel_to_ledger_ratio"], ratio, places=3, msg=mn_orders)
            self.assertIn(text, no["fallback_note"], msg=mn_orders)
            self.assertNotIn("과소 가능", no["fallback_note"])
            self.assertIn("%.0f%%" % (ratio * 100), no["fallback_note"])
            self.assertEqual((no["source_field"], no["ledger_rate"]), ("covered_scope_new_revenue", None), msg=mn_orders)
            self.assertEqual((cc["ledger_min_per_q_eok"], cc["ledger_max_per_q_eok"], cc["n_quarters_used"]), (0.0, 2000.0, 4))
        # ratio 0.2 < 0.5 이지만 원장 창 4분기(2025Q3 2,000억 · 0 · 0 · 0) 중 체결 > 0 은 1분기 < LEDGER_RATE_MIN_QUARTERS → 전환 안 함(2026-10-09:
        # 0 분기가 min/median 을 0 으로 끌어내리던 경로 폐쇄), 폴백 문구는 '과소 가능'
        _, m, _ = self._pair(synth_panel(rev_field="covered_scope_new_revenue", new_orders=10_000.0))
        no = m["segments"][0]["driver"]["new_orders"]
        self.assertAlmostEqual(no["ledger_crosscheck"]["panel_to_ledger_ratio"], 0.2, places=3)
        self.assertEqual((no["ledger_crosscheck"]["n_quarters_used"], no["ledger_crosscheck"]["n_quarters_positive"]), (4, 1))
        self.assertEqual((no["source_field"], no["fallback"], no["confidence"], no["ledger_rate"]), ("covered_scope_new_revenue", True, "low", None))
        self.assertIn("20% 수준", no["fallback_note"])
        self.assertIn("과소 가능", no["fallback_note"])

    def test_ledger_crosscheck_trims_leading_zero_quarters(self):
        """원장 첫 체결 분기 앞의 0 은 수주 없음이 아니라 원장이 닿지 않는 구간 → 평균에서 뺀다. synth_sls 체결: 2024Q2 4,000억(창 밖)·2025Q3 2,000억."""
        sls = synth_sls()
        no = {"new_orders_by_q": {"2026Q3": 250.0, "2026Q4": 250.0}}
        cc = M._ledger_signing_crosscheck(sls, no)
        self.assertEqual(cc["quarters"], M.q_range("2025Q3", "2026Q2"))           # 8분기 창이 2024Q3 부터지만 첫 체결 분기(2025Q3)부터
        self.assertEqual(cc["ledger_signed_by_q_eok"]["2025Q3"], 2000.0)
        self.assertEqual(cc["ledger_mean_per_q_eok"], 500.0)                        # 2,000 ÷ 4분기 (트림 없으면 2,000 ÷ 8 = 250)
        self.assertEqual(cc["panel_base_new_orders_mean_per_q_eok"], 250.0)
        self.assertEqual(cc["panel_to_ledger_ratio"], 0.5)
        # 패널 신규수주 값이 없거나 원장이 비면 비율 None(대조 불가)
        self.assertIsNone(M._ledger_signing_crosscheck(sls, {})["panel_to_ledger_ratio"])
        self.assertIsNone(M._ledger_signing_crosscheck({"origin": "2026Q2", "contracts": []}, no)["panel_to_ledger_ratio"])
        self.assertIsNone(M._ledger_signing_crosscheck({"contracts": []}, no))     # origin 없음

    def test_panel_new_orders_helper(self):
        ctx = FakeCtx()
        ctx.panel = {"010140": synth_panel(fq=M.q_range("2026Q3", "2027Q4"))}
        fq = M.q_range("2026Q3", "2028Q4")
        no = M._panel_new_orders("010140", ctx, fq)
        self.assertTrue(no["available"])
        self.assertEqual(no["covered"], M.q_range("2026Q3", "2027Q4"))
        self.assertEqual(no["uncovered"], M.q_range("2028Q1", "2028Q4"))
        self.assertEqual(no["by_scenario"]["base"]["2028Q1"], 0.0)                 # 패널이 안 덮는 분기는 0
        self.assertIn("패널 미커버 분기 0", no["basis"])
        self.assertAlmostEqual(no["by_scenario"]["optimistic"]["2026Q3"], 200.0 * 1.5 / 100)
        self.assertFalse(M._panel_new_orders("999999", ctx, fq)["available"])

    def test_holding_inherits_new_orders_and_scenarios(self):
        qs = M.q_range("2023Q1", "2026Q2")
        core = synth_fin("329180", "현중", quarters=qs, rev0=200_000.0, g_q=0.0)
        hold = synth_fin("009540", "지주", quarters=qs, rev0=260_000.0, g_q=0.0)
        ctx = FakeCtx(fins={"329180": core, "009540": hold}, slss={"329180": synth_sls("329180")}, roles={"329180": "yard", "009540": "holding"})
        ctx.panel = {"329180": synth_panel("329180")}
        m = M.build_model("009540", ctx)
        self.assertEqual(m["driver_type"], "subsidiary_yard_scaled")
        self.assertTrue(m["new_orders_included"])
        self.assertIn("329180", m["new_orders"]["note"])
        cm = ctx.model("329180")
        ratio = m["segments"][0]["driver"]["ratio_used"]
        sc, csc = m["scenarios"], cm["scenarios"]
        self.assertIsNotNone(sc)
        for y in ("2027", "2028"):
            self.assertAlmostEqual(sc["base"]["annual"][y]["rev"], rows_of(m)["매출액"]["a"][y]["v"], places=2)
            self.assertAlmostEqual(sc["optimistic"]["annual"][y]["new_order_revenue"], csc["optimistic"]["annual"][y]["new_order_revenue"] * ratio, delta=0.5)
            self.assertLess(sc["conservative"]["annual"][y]["rev"], sc["optimistic"]["annual"][y]["rev"])


class TestSlsR3Info(SyntheticAssets, unittest.TestCase):
    """결정 ⓔ — sls 의 cohort_mode · backlog_cap_applied · target_opm_alt: 없으면 '정보 없음', 있으면 basis·driver·assumptions 에."""

    def test_helper_shapes(self):
        i = M._sls_r3_info({})
        self.assertIsNone(i["cohort_mode"])
        self.assertIsNone(i["backlog_cap_applied"])
        self.assertIn("정보 없음", i["cohort_text"])
        self.assertIn("정보 없음", i["cap_text"])
        self.assertFalse(i["target_opm_alt_available"])
        i = M._sls_r3_info({"cohort_mode": "reference_anchor", "backlog_cap_applied": {"applied": True, "scale": 0.8592, "coverage": 1.1638},
                            "target_opm_alt": {"2026Q3": {"opm": 0.05}, "2026Q4": {"opm": 0.07}}})
        self.assertEqual(i["cohort_mode"], "reference_anchor")
        self.assertTrue(i["backlog_cap_applied"])
        self.assertIn("× 0.859", i["cap_text"])
        self.assertIn("커버리지 1.164", i["cap_text"])
        self.assertTrue(i["target_opm_alt_available"])
        self.assertAlmostEqual(i["target_opm_alt_median"], 0.06)
        self.assertTrue(M._sls_r3_info({"backlog_cap_applied": True})["backlog_cap_applied"])
        self.assertFalse(M._sls_r3_info({"backlog_cap_applied": False})["backlog_cap_applied"])
        self.assertTrue(M._sls_r3_info({"backlog_cap_applied": 0.86})["backlog_cap_applied"])
        self.assertIn("배율 0.860", M._sls_r3_info({"backlog_cap_applied": 0.86})["cap_text"])
        self.assertIsNone(M._sls_r3_info({"backlog_cap_applied": "yes"})["backlog_cap_raw"])

    def test_yard_reads_r3_keys_or_reports_absence(self):
        qs = M.q_range("2023Q1", "2026Q2")
        fin = synth_fin("010140", "삼성", quarters=qs, rev0=200_000.0, g_q=0.0)
        s_old, s_new = synth_sls(), synth_sls()
        s_new.update({"cohort_mode": "reference_anchor", "backlog_cap_applied": {"applied": True, "scale": 0.9, "coverage": 1.11},
                      "target_opm_alt": {q: {"opm": 0.05} for q in s_new["target_opm"]}})
        m_old = M.build_model("010140", FakeCtx(fins={"010140": fin}, slss={"010140": s_old}, roles={"010140": "yard"}))
        m_new = M.build_model("010140", FakeCtx(fins={"010140": fin}, slss={"010140": s_new}, roles={"010140": "yard"}))
        d_old, d_new = m_old["segments"][0]["driver"], m_new["segments"][0]["driver"]
        self.assertIsNone(d_old["sls_cohort_mode"])
        self.assertIsNone(d_old["backlog_cap_applied"])
        self.assertIn("캡 정보 없음", d_old["basis"])
        self.assertIn("코호트 모드 정보 없음", rows_of(m_old)["OPM"]["q"]["2026Q3"]["basis"])
        self.assertEqual(d_new["sls_cohort_mode"], "reference_anchor")
        self.assertTrue(d_new["backlog_cap_applied"])
        self.assertEqual(d_new["backlog_cap_raw"]["scale"], 0.9)
        self.assertAlmostEqual(d_new["target_opm_alt_median"], 0.05)
        self.assertIn("reference_anchor", rows_of(m_new)["OPM"]["q"]["2026Q3"]["basis"])
        self.assertIn("캡 적용 × 0.900", d_new["basis"])
        self.assertTrue(any("선표 잔고 캡" in w for w in m_new["quality"]["warnings"]))
        self.assertFalse(any("선표 잔고 캡" in w and "R3" in w for w in m_old["quality"]["warnings"]))
        self.assertEqual(m_new["assumptions"]["sls"]["cohort_mode"], "reference_anchor")
        self.assertNotIn("backlog_cap_raw", m_new["assumptions"]["sls"])
        self.assertIsNone(m_old["assumptions"]["sls"]["cohort_mode"])
        # 숫자는 sls 값 그대로 — 키가 있어도 매출 경로는 by_quarter 를 그대로 쓴다(캡은 R3 가 값에 이미 반영)
        self.assertEqual(rows_of(m_new)["매출조선"]["q"]["2026Q3"]["v"], rows_of(m_old)["매출조선"]["q"]["2026Q3"]["v"])


class TestLinkOOS(SyntheticAssets, unittest.TestCase):
    """결정 ⓘ — 고객 연동 OOS 선택: la−4분기 동결, 연동·추세 4분기 매출 WAPE 비교, 연동 > 추세 × 1.10 이면 기각. 동결 전 합병은 체인링크 없이."""

    QS = M.q_range("2022Q1", "2026Q2")

    def _ctx(self, yard_g, sup_fn, noisy=False):
        yard = noisy_yard_fin("329180", "현중", self.QS) if noisy else synth_fin("329180", "현중", quarters=self.QS, rev0=300_000.0, g_q=yard_g)
        x = {q: yard["cons"]["is"][q]["매출액(수익)"] for q in self.QS}
        sup = synth_fin("222222", "공급사", quarters=self.QS, rev0=15_000.0, g_q=0.0)
        for i, q in enumerate(self.QS):
            v = sup_fn(i, q, x)
            for sc in ("cons", "sep"):
                sup[sc]["is"][q]["매출액(수익)"] = v
        return FakeCtx(fins={"329180": yard, "222222": sup}, roles={"329180": "yard", "222222": "equip"},
                       suppliers={"cos": [{"stock": "222222", "nm": "공급사", "role": "equip", "yards": [{"yard": "329180", "mentions": 2}]}]}), x

    def test_true_link_adopted_with_oos_record(self):
        # 매출 = 0.05 × 잡음 고객(t−2) 정확히 → 동결 시점 연동은 2025Q3·Q4 를 고객 실적으로 맞추고(시차 2) 자사 추세는 잡음을 못 맞춘다 → 채택 + selection_oos 기록
        # (완전 기하급수 고객이면 자사 추세 WAPE 가 0.0 이라 어떤 연동도 '≤ 0 × 1.10' 을 못 넘는 퇴화 사례 — 실데이터엔 없다)
        ctx, x = self._ctx(0.03, lambda i, q, x: 0.05 * x[self.QS[max(i - 2, 0)]], noisy=True)
        m = M.build_model("222222", ctx)
        d = m["segments"][0]["driver"]
        self.assertEqual(m["driver_type"], "customer_yard_revenue_weighted")
        oos = d["selection_oos"]
        self.assertEqual(oos["freeze"], "2025Q2")
        self.assertEqual(oos["n"], 4)
        self.assertTrue(oos["adopted"])
        self.assertIsNotNone(oos["wape_link"])
        self.assertLessEqual(oos["wape_link"], oos["wape_trend"] * M.OOS_WORSE_TOL)
        self.assertEqual(len(oos["detail"]), 4)
        self.assertEqual([r["q"] for r in oos["detail"]], M.q_range("2025Q3", "2026Q2"))
        self.assertIn("link_at_freeze", oos)
        self.assertIn(oos["link_at_freeze"]["transform"], M.LINK_TRANSFORMS)
        self.assertIsNone(d["new_orders_included"])
        self.assertEqual(d["new_orders"]["via"], "customer_models")
        self.assertIn("329180", d["new_orders"]["customers"])
        s = M.summary_row(m)["link"]
        self.assertTrue(s["adopted"])
        self.assertIsNone(s["rejected_by"])
        self.assertEqual((s["wape_link"], s["wape_trend"], s["oos_freeze"]), (oos["wape_link"], oos["wape_trend"], "2025Q2"))
        # 동결(백테스트) 모델 안에서는 자기 la−4 = 2024Q2 가 동결 → 현재 모델 backtest 에 요약이 남는다
        bt = m["backtest"]
        self.assertEqual(bt["selection_oos_at_freeze"]["freeze"], "2024Q2")
        self.assertIn("selection_oos_at_freeze", bt["frozen_inputs"])

    def test_spurious_link_rejected_by_oos(self):
        # 자사 3%/분기·고객 10%/분기 기하급수: 표본 안 수준 상관 ≈ 1(유의)이지만 동결 연동은 비례계수로 과대추정(WAPE 30%대), 자사 추세는 정확(0%) → OOS 기각
        ctx, _ = self._ctx(0.10, lambda i, q, x: 15_000.0 * (1.03 ** i))
        m = M.build_model("222222", ctx)
        self.assertEqual(m["driver_type"], "trend_seasonal")
        d = m["segments"][0]["driver"]
        rj = d["customer_link_rejected"]
        self.assertEqual(rj["rejected_by"], "oos")
        self.assertGreaterEqual(rj["corr"], M.CORR_MIN)
        self.assertTrue(rj["significance"]["significant_p05_uncorrected"])            # 유의성은 통과했다
        oos = rj["selection_oos"]
        self.assertIs(oos, d["selection_oos"])
        self.assertFalse(oos["adopted"])
        self.assertGreater(oos["wape_link"], oos["wape_trend"] * M.OOS_WORSE_TOL)
        self.assertIn("OOS 기각", d["basis"])
        self.assertIn("WAPE 연동", d["basis"])
        # T6 D7: status 는 데이터 완전성만(이 합성 fin 은 매출만 덮어써 실적 항등식이 깨진다 → partial), 기각 사유는 driver_fallback
        self.assertFalse(m["quality"]["identities_ok"])
        self.assertEqual(m["status"], "partial")
        self.assertEqual(m["driver_fallback"], "oos")
        # T6 D5(b): 시험한 것은 현재 채택 후보 조합(현재 데이터 격자 최선)을 동결 데이터로 재적합한 것 — 재선택 조합은 참고
        self.assertEqual(oos["tested"], "adopted_combo")
        lt = oos["link_tested"]
        self.assertEqual((lt["wkey"], lt["lag_q"], lt["transform"], lt["window_q"]), (rj["weights_key"], rj["lag_q"], rj["transform"], rj["window_q"]))
        self.assertIn("참고", oos["link_at_freeze"]["note"])
        self.assertEqual(oos["decision"], "rejected")
        s = M.summary_row(m)["link"]
        self.assertFalse(s["adopted"])
        self.assertEqual(s["rejected_by"], "oos")
        self.assertEqual(s["wape_trend"], oos["wape_trend"])
        # 동결 모델(la 2025Q2)의 채택 후보(4Q합·시차 4·창 8)는 2024Q2 동결 데이터로 재적합할 짝이 모자라다 → undetermined → 유의성만으로 채택(T6 D5c).
        # 재선택 조합(참고)은 연동이 추세보다 나쁘다는 것을 보여 주지만 판정에 쓰지 않는다 — 오너 결정 사항으로 NOTES_T6 에 기록
        bo = m["backtest"]["selection_oos_at_freeze"]
        self.assertEqual((bo["adopted"], bo["decision"]), ("undetermined", "undetermined"))
        self.assertIn("재적합할 수 없음", bo["note"])
        self.assertEqual(m["backtest"]["driver_at_freeze"], "customer_yard_revenue_weighted")

    def test_significance_rejection_skips_oos(self):
        ctx, _ = self._ctx(0.03, lambda i, q, x: 10_000.0 + 3_000.0 * (1 if i % 2 else -1))
        m = M.build_model("222222", ctx)
        rj = m["segments"][0]["driver"]["customer_link_rejected"]
        self.assertEqual(rj["rejected_by"], "corr")
        self.assertFalse(rj["selection_oos"]["adopted"])
        self.assertIsNone(rj["selection_oos"]["wape_link"])
        self.assertIn("OOS 비교 전 기각", rj["selection_oos"]["note"])

    def test_link_oos_insufficient_history(self):
        # 동결 이전 실적 < 8분기면 비교 불가 → T6 D5(c): adopted 대신 'undetermined'(유의성만으로 채택) + note
        y = {q: 100.0 * (1.02 ** i) for i, q in enumerate(M.q_range("2024Q1", "2026Q2"))}
        ctx, _ = self._ctx(0.03, lambda i, q, x: 15_000.0)
        cands = M._customer_weight_candidates("222222", ctx)
        oos = M._link_oos(y, cands, ctx, "2026Q2")
        self.assertEqual(oos["adopted"], "undetermined")
        self.assertEqual(oos["decision"], "undetermined")
        self.assertIsNone(oos["wape_link"])
        self.assertIn("비교 불가", oos["note"])
        self.assertEqual(oos["freeze"], "2025Q2")

    def test_merger_before_freeze_uses_both_frozen_models(self):
        # 세진 합성: 동결 2025Q2 < 합병 2025Q4 → 체인링크 없이 미포·현중 동결 모델 각자 비중(누출 없음); origin None 이면 기존 체인링크
        ctx = sejin_ctx(vary=True)
        w = {"010620": 0.9 / 1.1, "329180": 0.2 / 1.1}
        det = {}
        idx, note, used = M._customer_index(w, ctx, "2025Q2", lag=1, detail=det)
        self.assertIn("체인링크 없이", note)
        self.assertFalse(det["mergers"][0]["applied"])
        self.assertIsNone(det["mergers"][0]["chain_k"])
        mipo, hhi = ctx.model("010620", "2025Q2"), ctx.model("329180", "2025Q2")
        rm_m, rm_h = rows_of(mipo)["매출액"]["q"], rows_of(hhi)["매출액"]["q"]
        q = "2025Q4"                                                        # 합병 분기 — 두 동결 모델의 추정 셀
        self.assertEqual(rm_m[q]["kind"], "estimate")
        self.assertAlmostEqual(idx["2026Q1"], w["010620"] * rm_m[q]["v"] + w["329180"] * rm_h[q]["v"], places=4)
        det2 = {}
        idx2, note2, _ = M._customer_index(w, ctx, None, lag=1, detail=det2)
        self.assertIn("체인링크", note2)
        self.assertNotIn("체인링크 없이", note2)
        self.assertIsNotNone(det2["mergers"][0]["chain_k"])
        # 이 규칙 덕에 세진 합성(정확한 weighted 관계)은 OOS 를 통과해 연동이 채택된다
        m = M.build_model("075580", ctx)
        self.assertEqual(m["driver_type"], "customer_yard_revenue_weighted")
        self.assertTrue(m["segments"][0]["driver"]["selection_oos"]["adopted"])

    def test_oos_determinism(self):
        ctx, _ = self._ctx(0.10, lambda i, q, x: 15_000.0 * (1.03 ** i))
        a = json.dumps(M.build_model("222222", ctx), ensure_ascii=False, sort_keys=True)
        ctx2, _ = self._ctx(0.10, lambda i, q, x: 15_000.0 * (1.03 ** i))
        b = json.dumps(M.build_model("222222", ctx2), ensure_ascii=False, sort_keys=True)
        self.assertEqual(a, b)


def r2(v):
    return M.r2(v)


REAL_FIN = os.path.join(M.FIN_DIR, "010140.json")
REAL_SEJIN = os.path.join(M.FIN_DIR, "075580.json")


@unittest.skipUnless(os.path.isfile(REAL_FIN) and os.path.isfile(REAL_SEJIN), "assets/fin 실제 산출 없음")
class TestRealAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = M.Ctx(today="2026-09-30")
        cls.m = cls.ctx.model("010140")
        cls.rm = rows_of(cls.m)
        with open(REAL_FIN, encoding="utf-8") as f:
            cls.fin = json.load(f)

    def test_actual_matches_fin(self):
        q = self.fin["quarters"][-1]
        self.assertEqual(self.m["periods"]["last_actual"], q)
        self.assertAlmostEqual(self.rm["매출액"]["q"][q]["v"], round(self.fin["cons"]["is"][q]["매출액(수익)"] / 100, 2), places=2)
        self.assertAlmostEqual(self.rm["영업이익"]["q"][q]["v"], round(self.fin["cons"]["is"][q]["영업이익"] / 100, 2), places=2)
        self.assertAlmostEqual(self.rm["자산총계"]["q"][q]["v"], round(self.fin["cons"]["bs"][q]["자산총계"] / 100, 2), places=2)
        self.assertEqual(self.rm["매출액"]["q"][q]["kind"], "actual")

    def test_horizon_and_identities(self):
        la = self.m["periods"]["last_actual"]
        est = [q for q in self.m["periods"]["quarters"] if q > la]
        self.assertGreaterEqual(len(est), M.FWD_MIN)
        self.assertEqual(est[-1], M.HORIZON_END if la < M.HORIZON_END else M.q_add(la, M.FWD_MIN))   # origin 기준(2026Q2 → 2028Q4) — 새 분기 수집 뒤에도 유효
        for y in range(M.q_year(la), M.q_year(est[-1]) + 1):
            self.assertIsNotNone(self.rm["매출액"]["a"][str(y)]["v"])
            self.assertIsNotNone(self.rm["EPS"]["a"][str(y)]["v"])
        self.assertTrue(self.m["quality"]["identities_ok"], self.m["quality"]["identity_mismatches"])

    def test_eps_scale_vs_reported(self):
        q = self.fin["quarters"][-1]
        rep = (self.fin["cons"].get("eps_reported") or {}).get(q) or {}
        eps = self.rm["EPS"]["q"][q]["v"]
        self.assertGreater(eps, 0)
        if rep.get("cur_q"):
            self.assertLess(abs(eps - rep["cur_q"]), 10, (eps, rep))           # 3개월 지배NI ÷ 유통주식수 ≈ 보고서 EPS
        sejin = rows_of(self.ctx.model("075580"))
        with open(REAL_SEJIN, encoding="utf-8") as f:
            fs = json.load(f)
        rep2 = (fs["cons"].get("eps_reported") or {}).get(fs["quarters"][-1]) or {}
        if rep2.get("cur_q"):
            self.assertLess(abs(sejin["EPS"]["q"][fs["quarters"][-1]]["v"] - rep2["cur_q"]), 10)

    def test_yard_uses_sls_when_present(self):
        if os.path.isfile(os.path.join(M.SLS_DIR, "010140.json")):
            self.assertEqual(self.m["driver_type"], "sls_marine_plus_uncovered_backlog_runoff")
            self.assertIn("매출조선", self.rm)

    def test_determinism_real(self):
        a = json.dumps(self.m, ensure_ascii=False, sort_keys=True)
        b = json.dumps(M.Ctx(today="2026-09-30").model("010140"), ensure_ascii=False, sort_keys=True)
        self.assertEqual(a, b)

    def test_real_backtest_actual_only_sep_fill_one_off(self):
        # HD현대미포(실적 2025Q3 까지) 백테스트 짝 1개 · 한화엔진 연결 공백은 별도 보충 · KCC 2026Q2 처분이익 일회성 의심 표시
        if os.path.isfile(os.path.join(M.FIN_DIR, "010620.json")):
            m = self.ctx.model("010620")
            self.assertEqual(m["backtest"]["n"], 1)
            self.assertEqual(m["backtest"]["detail"][0]["q"], "2025Q3")
        if os.path.isfile(os.path.join(M.FIN_DIR, "082740.json")):
            rm2 = rows_of(self.ctx.model("082740"))
            for q in M.q_range("2023Q3", "2025Q4"):
                self.assertIn(q, rm2["매출액"]["q"], q)
            self.assertIn("별도 보충", rm2["매출액"]["q"]["2025Q3"]["src"])
            self.assertIsNotNone(rm2["매출액"]["a"]["2025"]["v"])
        if os.path.isfile(os.path.join(M.FIN_DIR, "002380.json")):
            m3 = self.ctx.model("002380")
            la3 = m3["periods"]["last_actual"]
            if "2026Q2" in M.q_range(M.q_add(la3, -3), la3):                                 # 일회성 창(최근 4분기) 안일 때만 — 새 분기 수집으로 창 밖이면 생략
                self.assertIn("2026Q2", [d["q"] for d in m3["assumptions"]["one_offs_detected"]])
                self.assertTrue(any("일회성 의심 2026Q2" in w for w in m3["quality"]["warnings"]))
        # 고객 연동 회사: 세그먼트 드라이버에 가중치 합 1 · 격자가 고른 lag/변환/창 · corr · 후보표 가 남는다
        for st in ("014940", "086670", "460930"):
            if os.path.isfile(os.path.join(M.FIN_DIR, st + ".json")):
                mm = self.ctx.model(st)
                if mm.get("driver_type") == "customer_yard_revenue_weighted":
                    d = mm["segments"][0]["driver"]
                    self.assertAlmostEqual(sum(d["weights"].values()), 1.0, places=6)
                    self.assertIn(d["lag_q"], M.LINK_LAGS)
                    self.assertIn(d["transform"], M.LINK_TRANSFORMS)
                    self.assertIn(d["window_q"], M.LINK_WINDOWS)
                    self.assertGreaterEqual(d["corr"], M.CORR_MIN)
                    self.assertEqual(d["grid"]["top"][0]["corr"], d["corr"])
                    self.assertEqual(len(d["grid"]["table"]), d["grid"]["n_candidates"])

    def test_real_new_orders_scenarios_and_oos(self):
        # 라운드 3: 패널 값이 있는 조선사는 매출조선신규 행 + scenarios(base = 행), 없는 조선사는 미포함 + 경고; 연동 채택 회사는 OOS 규칙을 만족
        for st in M.YARDS:
            if not os.path.isfile(os.path.join(M.FIN_DIR, st + ".json")):
                continue
            m = self.ctx.model(st)
            if m.get("driver_type") != "sls_marine_plus_uncovered_backlog_runoff":
                continue
            rm, d = rows_of(m), m["segments"][0]["driver"]
            self.assertIn("new_orders_included", d)
            self.assertIn("backlog_cap_applied", d)
            self.assertIn("sls_cohort_mode", d)
            self.assertIsNotNone(m["assumptions"]["sls"])
            if m["new_orders_included"]:
                self.assertIn("매출조선신규", rm)
                sc = m["scenarios"]
                for y in ("2026", "2027", "2028"):
                    self.assertAlmostEqual(sc["base"]["annual"][y]["rev"], rm["매출액"]["a"][y]["v"], places=2)
                    self.assertLessEqual(sc["conservative"]["annual"][y]["rev"], sc["base"]["annual"][y]["rev"])
                    self.assertLessEqual(sc["base"]["annual"][y]["rev"], sc["optimistic"]["annual"][y]["rev"])
                    self.assertLessEqual(sc["existing_only"]["annual"][y]["rev"], sc["base"]["annual"][y]["rev"])
                for q in M.q_range("2026Q3", "2028Q4"):
                    self.assertGreaterEqual(rm["매출조선"]["q"][q]["v"] - rm["매출조선신규"]["q"][q]["v"], -0.01)
                self.assertGreater(sc["base"]["annual"]["2028"]["rev"], sc["existing_only"]["annual"]["2028"]["rev"])
                self.assertEqual(M.summary_row(m)["scenarios"]["2028E"]["base"]["rev"], rm["매출액"]["a"]["2028"]["v"])
            else:
                self.assertNotIn("매출조선신규", rm)
                self.assertIsNone(m["scenarios"])
                self.assertTrue(any("신규수주 매출 미포함" in w for w in m["quality"]["warnings"]))
            # 백테스트 동결 모델은 패널을 쓰지 않는다
            bm = self.ctx.model(st, origin=M.FREEZE_Q)
            if bm and bm.get("rows"):
                self.assertNotIn("매출조선신규", rows_of(bm))
        hold = self.ctx.model(M.HOLDING)
        if hold.get("driver_type") == "subsidiary_yard_scaled":
            self.assertEqual(hold["new_orders_included"], self.ctx.model(M.HOLDING_CORE)["new_orders_included"])
        n_link = n_oos = 0
        for st in self.ctx.population():
            mm = self.ctx.model(st)
            if not mm.get("segments"):
                continue
            d = mm["segments"][0]["driver"]
            if d.get("type") == "customer_yard_revenue_weighted":
                n_link += 1
                o = d["selection_oos"]
                self.assertIn(o["adopted"], (True, "undetermined"))
                if o["adopted"] is True:
                    self.assertLessEqual(o["wape_link_raw"], o["wape_trend_raw"] * M.OOS_WORSE_TOL)       # 반올림 전 비교(T6 D5a)
                    self.assertEqual(o["tested"], "adopted_combo")
            elif (d.get("customer_link_rejected") or {}).get("rejected_by") == "oos":
                n_oos += 1
                o = d["customer_link_rejected"]["selection_oos"]
                self.assertGreater(o["wape_link_raw"], o["wape_trend_raw"] * M.OOS_WORSE_TOL)
                self.assertEqual(mm["driver_fallback"], "oos")
                self.assertEqual(mm["driver_type"], "trend_seasonal")
        self.assertGreater(n_link, 0)

    def test_real_sejin_link_grid_and_merger_rule(self):
        # 세진: 격자 결과(채택이든 기각이든)와 미포→HD현대重 합병 규칙이 파일에 남는다. 종속사 모델 합산 항등식은 그대로.
        m = self.ctx.model("075580")
        d = m["segments"][0]["driver"]
        info = d if d["type"] == "customer_yard_revenue_weighted" else d["customer_link_rejected"]
        self.assertIn(info["transform"], M.LINK_TRANSFORMS)
        self.assertIn(info["lag_q"], M.LINK_LAGS)
        self.assertGreaterEqual(info["grid"]["n_candidates"], 45)
        self.assertTrue(any("010620" in r and "329180" in r and "2025Q4" in r for r in info["merger_rule"]), info["merger_rule"])
        self.assertEqual(info["customer_sources"]["010620"]["last_actual"], "2025Q3")
        rm = rows_of(m)
        fq = [q for q in m["periods"]["quarters"] if q > m["periods"]["last_actual"]]          # origin 기준 추정 분기(2026Q2 → 2026Q3~2028Q4)
        for q in fq:
            tot = rm["매출조선기자재"]["q"][q]["v"] + rm["매출종속사"]["q"][q]["v"] + rm["매출연결조정"]["q"][q]["v"]
            self.assertAlmostEqual(tot, rm["매출액"]["q"][q]["v"], delta=0.06)
        if d["type"] == "customer_yard_revenue_weighted":
            self.assertIn("격자", rm["매출조선기자재"]["q"][fq[0]]["basis"])
            self.assertIn("2025Q4", rm["매출조선기자재"]["q"][fq[0]]["basis"])

    @staticmethod
    def _cf_low_from_fin(st, origin):
        """fin 에서 D2 감지를 독립 재계산: (클립한 양(+)세전 8분기 중위 또는 미감지면 None, k8). _tax_carryforward 와 같은 입력(Fin upto=origin)·같은 문턱."""
        with open(os.path.join(M.FIN_DIR, st + ".json"), encoding="utf-8") as f:
            fin = M.Fin(json.load(f), upto=origin)
        pretax, tax = fin.series("is", "법인세비용차감전계속사업이익"), fin.series("is", "법인세비용")
        k8 = [q for q in M.last_n(pretax, M.TAX_FALLBACK_Q) if pretax[q] > 0 and q in tax]
        rates = [tax[q] / pretax[q] for q in k8]
        if len(k8) < M.TAX_CF_MIN_POS_Q or not (M.med(rates) < M.TAX_CF_LOW_MAX and M.med(rates[-M.TAX_CF_RECENT_Q:]) < M.TAX_CF_LOW_MAX):
            return None, k8
        return M.clip(M.med(rates), 0.0, M.TAX_CF_LOW_MAX), k8

    def test_real_tax_carryforward_targets(self):
        # 라운드 7 D2(2026-10-08): 한화오션·HJ重 은 이월결손 경로(양(+)세전 분기 중위 0.68%·0.45%), 삼성重(최근 4분기 중위 24.3% 로 정상화)·한화엔진(5.2%) 은 default 유지
        if not all(os.path.isfile(os.path.join(M.FIN_DIR, s + ".json")) for s in ("042660", "097230", "082740")):
            self.skipTest("assets/fin 042660·097230·082740 없음")
        for st in ("042660", "097230"):                                                             # 2026Q2 수집본: 0.68%·0.45% — 기대값은 fin 에서 재계산(2026Q3 수집 뒤에도 유효)
            m = self.ctx.model(st)
            a, origin = m["assumptions"], m["periods"]["last_actual"]
            low, k8 = self._cf_low_from_fin(st, origin)
            if low is None:
                self.skipTest("%s 세율 정상화(양(+)세전 %d분기 중위 ≥ %.0f%%) — D2 감지 대상 아님" % (st, len(k8), M.TAX_CF_LOW_MAX * 100))
            self.assertEqual(a["tax_path"], M.TAX_CF_PATH, st)
            self.assertAlmostEqual(a["tax_rate"], M.r4(low), places=6, msg=st)                      # assumptions.tax_rate 는 r4
            self.assertTrue(0 <= a["tax_rate"] < M.TAX_CF_LOW_MAX, (st, a["tax_rate"]))
            self.assertEqual(a["tax_carryforward"]["quarters"], k8, st)
            self.assertEqual(a["tax_rate_terminal"], M.TAX_DEFAULT)
            cf = a["tax_carryforward"]
            self.assertEqual(cf["hold_until"], None if origin.endswith("Q4") else origin[:4] + "Q4", st)   # origin 이 Q4 면 유지 분기 없음
            self.assertEqual(a["tax_schedule"][cf["ramp_to"]], M.TAX_DEFAULT, st)                          # 램프 끝점(= 추정 마지막 분기) 22%
            self.assertEqual(cf["ramp_to"], m["periods"]["quarters"][-1], st)
            self.assertTrue(any("이월결손 경로" in w for w in m["quality"]["warnings"]))
        self.assertEqual(self.m["assumptions"]["tax_path"], "default")
        self.assertGreater(self.m["assumptions"]["nol_evidence"]["dta_eok"], 0)                    # 삼성重 DTA 4,308억(2026Q2) — 정보 필드만
        self.assertEqual(self.ctx.model("082740")["assumptions"]["tax_path"], "default")

    def test_real_eligibility_round7(self):
        # 라운드 7 L5(2026-10-08): 한화시스템(related 0.03% 하나) 자격 미달 → 추세 · 한라IMS(ifrs8 이름 명시) 유지 + n_eff 5 기록 · 현대힘스 가중치 불변 · HD현대마린솔루션 ma4 n6 탈락
        need = ("272210", "092460", "460930", "443060", "042660", "329180", "009540", "010620")
        if not all(os.path.isfile(os.path.join(M.FIN_DIR, s + ".json")) for s in need) or not os.path.isfile(os.path.join(M.ASSETS, "suppliers.json")):
            self.skipTest("assets/fin·suppliers.json 실제 산출 없음")
        ctx = M.Ctx(today="2026-10-08")
        hs = ctx.model("272210")
        rj = hs["segments"][0]["driver"]["customer_link_rejected"]
        self.assertEqual((hs["driver_type"], hs["driver_fallback"], rj["rejected_by"]), ("trend_seasonal", "eligibility", "eligibility"))
        self.assertEqual((rj["eligibility"]["related_share_sum"], rj["eligibility"]["bases"], rj["weights"]), (0.03, ["related"], {"042660": 1.0}))
        self.assertAlmostEqual(M.summary_row(hs)["fy"]["2026E"]["rev"], 49313.96, places=0)
        ims = ctx.model("092460")["segments"][0]["driver"]
        self.assertEqual((ims["type"], ims["weights"], ims["eligibility"]["bases"]), ("customer_yard_revenue_weighted", {"042660": 1.0}, ["ifrs8"]))
        self.assertEqual((ims["transform"], ims["n"], ims["n_eff"], ims["significance"]["r_crit_p05_neff"]), ("ma4", 8, 5, 0.8783))
        self.assertGreaterEqual(ims["corr"], ims["significance"]["r_crit_p05_neff"])
        self.assertTrue(ims["significance"]["significant_p05_neff"])
        self.assertEqual(ctx.model("460930")["segments"][0]["driver"]["weights"], {"009540": 0.5722, "010620": 0.0023, "329180": 0.4255})
        hms = ctx.model("443060")["segments"][0]["driver"]
        info = hms if hms["type"] == "customer_yard_revenue_weighted" else hms["customer_link_rejected"]
        self.assertTrue(info["transform"] != "ma4" or info["n"] >= M.LINK_MIN_N + M.LINK_NEFF_PENALTY["ma4"], (info["transform"], info["n"]))
        adopted = sorted(s for s in ctx.population() if ctx.model(s).get("driver_type") == "customer_yard_revenue_weighted")
        self.assertEqual(len(adopted), 17, adopted)


# ── 금융손익 세부(T4): 주석 이자·외환·파생 → 행 · 실측 연율 ──

NOTE_ACCTS = {"이자수익": 500.0, "이자비용": 1500.0, "외환차익": 300.0, "외환차손": 100.0, "외화환산이익": 50.0, "외화환산손실": 150.0,
              "파생상품이익": 20.0, "파생상품손실": 70.0}      # 백만원 — 이자 −10억, 외환 +1억, 파생 −0.5억, 금융손익 −5억 → 잔차 +4.5억


FX_ACCTS = ("외환차익", "외환차손", "외화환산이익", "외화환산손실")
OTHER_FX_NOTE = {"외환차익": 300.0, "외환차손": 100.0, "외화환산이익": 50.0, "외화환산손실": 150.0, "ytd": {}, "totals": {}, "basis": "3m_column"}


def synth_fin_notes(note_qs=None, drop=None, fin_pl=None, note_accts=None, other_fx_qs=None, **kw):
    """synth_fin + note_qs 분기의 cons/sep is 에 주석 계정. drop = {q: [계정]} 은 그 분기에서 뺀다. fin_pl 을 주면 금융손익 덮어쓰기(세전은 그대로).
    note_accts 는 NOTE_ACCTS 덮어쓰기(예 {"이자비용": 7000.0}). other_fx_qs 분기는 외환 4계정을 is 에 넣지 않고 notes.other 에 둔다(기타영업외 주석 패턴)."""
    fin = synth_fin(**kw)
    accts = dict(NOTE_ACCTS, **(note_accts or {}))
    note_qs = M.q_range("2025Q1", "2026Q2") if note_qs is None else note_qs
    other_fx_qs = set(other_fx_qs or [])
    for q in note_qs:
        for sc in ("cons", "sep"):
            d = {k: v for k, v in accts.items() if k not in (drop or {}).get(q, [])}
            if q in other_fx_qs:
                d = {k: v for k, v in d.items() if k not in FX_ACCTS}
                fin[sc].setdefault("notes", {"fin": {}, "borrowings": {}, "other": {}})["other"][q] = dict(OTHER_FX_NOTE)
            fin[sc]["is"][q].update(d)
            if fin_pl is not None:
                fin[sc]["is"][q]["금융손익"] = fin_pl
    return fin


class TestFinDetail(unittest.TestCase):
    def build(self, fin):
        return M.build_model("999999", FakeCtx(fins={"999999": fin}, roles={"999999": "equip"}))

    def test_four_rows_sum_to_fin_pl(self):
        m = self.build(synth_fin_notes())
        rm = rows_of(m)
        parts = ("이자손익", "외환손익", "파생상품손익", "기타금융손익")
        for q in M.q_range("2025Q1", "2026Q2"):
            cells = [rm[k]["q"][q] for k in parts]
            self.assertTrue(all(c["kind"] == "actual" for c in cells), q)
            self.assertLessEqual(abs(sum(c["v"] for c in cells) - rm["금융손익"]["q"][q]["v"]), 0.05, q)
        q = "2026Q2"
        self.assertAlmostEqual(rm["이자손익"]["q"][q]["v"], -10.0)
        self.assertAlmostEqual(rm["외환손익"]["q"][q]["v"], 1.0)
        self.assertAlmostEqual(rm["파생상품손익"]["q"][q]["v"], -0.5)
        self.assertAlmostEqual(rm["기타금융손익"]["q"][q]["v"], 4.5)
        self.assertEqual(rm["이자손익"]["q"][q]["src"], "fin.cons.is.이자수익 − fin.cons.is.이자비용")
        self.assertIn("fin.cons.is.외화환산손실", rm["외환손익"]["q"][q]["src"])
        self.assertIn("잔차", rm["기타금융손익"]["q"][q]["src"])
        # 추정 구간: 금융손익 = 이자(추) + 외환 0 + 파생 0 + 기타금융 중위, 세전 사슬 그대로
        for q in M.q_range("2026Q3", "2028Q4"):
            cells = [rm[k]["q"][q] for k in parts]
            self.assertTrue(all(c["kind"] == "estimate" and c.get("basis") for c in cells), q)
            self.assertEqual(rm["외환손익"]["q"][q]["v"], 0.0)
            self.assertEqual(rm["파생상품손익"]["q"][q]["v"], 0.0)
            self.assertAlmostEqual(rm["기타금융손익"]["q"][q]["v"], 4.5)
            self.assertLessEqual(abs(sum(c["v"] for c in cells) - rm["금융손익"]["q"][q]["v"]), 0.05, q)
        self.assertIn("환관련손익", rm["외환손익"]["q"]["2026Q3"]["basis"])
        self.assertTrue(m["quality"]["identities_ok"], m["quality"]["identity_mismatches"])
        # 주석 없는 분기(2023Q1~2024Q4)는 세부 행이 비어 있다(0 을 넣지 않음)
        self.assertNotIn("2024Q4", rm["이자손익"]["q"])
        self.assertNotIn("2024Q4", rm["기타금융손익"]["q"])

    def test_none_propagates(self):
        m = self.build(synth_fin_notes(drop={"2026Q1": ["외화환산손실"], "2025Q4": ["파생상품이익"]}))
        rm = rows_of(m)
        self.assertNotIn("2026Q1", rm["외환손익"]["q"])
        self.assertNotIn("2026Q1", rm["기타금융손익"]["q"])
        self.assertIn("2026Q1", rm["이자손익"]["q"])
        self.assertIn("2026Q1", rm["파생상품손익"]["q"])
        self.assertNotIn("2025Q4", rm["파생상품손익"]["q"])
        self.assertNotIn("2025Q4", rm["기타금융손익"]["q"])
        self.assertIn("2025Q4", rm["외환손익"]["q"])
        # 주석이 전혀 없는 회사: 세부 실적 행 없음, 이자손익 추정만(CF 연율), 금융손익 = 이자손익(추) (기존과 같은 값)
        m0 = self.build(synth_fin())
        rm0 = rows_of(m0)
        for k in ("외환손익", "파생상품손익", "기타금융손익"):
            self.assertNotIn(k, rm0)
        self.assertTrue(all(c["kind"] == "estimate" for c in rm0["이자손익"]["q"].values()))
        q = "2026Q3"
        self.assertAlmostEqual(rm0["금융손익"]["q"][q]["v"], rm0["이자손익"]["q"][q]["v"], places=2)
        self.assertAlmostEqual(rm0["이자손익"]["q"][q]["v"], (1000 * 0.03 - 1200 * 0.04) / 4, places=2)   # CF 이자수취 750·이자지급 1200 백만원/분기

    def test_rate_from_notes_or_cf_fallback(self):
        m = self.build(synth_fin_notes())                                     # 주석 6분기 → 주석 연율
        a = m["assumptions"]
        self.assertAlmostEqual(a["interest_rate_asset"], 0.02, places=4)     # 5억×4 ÷ 1000억
        self.assertAlmostEqual(a["interest_rate_debt"], 0.05, places=4)      # 15억×4 ÷ 1200억
        self.assertTrue(a["interest_rate_source"]["asset"].startswith("주석 이자수익"))
        self.assertTrue(a["interest_rate_source"]["debt"].startswith("주석 이자비용"))
        c = rows_of(m)["이자손익"]["q"]["2026Q3"]
        self.assertAlmostEqual(c["v"], (1000 * 0.02 - 1200 * 0.05) / 4, places=2)
        self.assertIn("주석 이자수익", c["basis"])
        m3 = self.build(synth_fin_notes(note_qs=M.q_range("2026Q1", "2026Q2") + ["2025Q4"]))   # 3분기 → CF 폴백
        a3 = m3["assumptions"]
        self.assertAlmostEqual(a3["interest_rate_asset"], 0.03, places=4)
        self.assertAlmostEqual(a3["interest_rate_debt"], 0.04, places=4)
        self.assertTrue(a3["interest_rate_source"]["asset"].startswith("CF 이자수취"))
        self.assertIn("< 4", a3["interest_rate_source"]["debt"])
        self.assertIn("CF 이자지급", rows_of(m3)["이자손익"]["q"]["2026Q3"]["basis"])
        # 잔차 3분기 < 4 → 기타금융 추정 0
        self.assertEqual(rows_of(m3)["기타금융손익"]["q"]["2026Q3"]["v"], 0.0)

    def test_other_fin_cap_warns(self):
        m = self.build(synth_fin_notes(fin_pl=2000.0))                       # 잔차 +29.5억 ≫ |이자손익 추정 −10억| × 50%
        rm = rows_of(m)
        self.assertAlmostEqual(rm["기타금융손익"]["q"]["2026Q2"]["v"], 29.5)
        c = rm["기타금융손익"]["q"]["2026Q3"]
        self.assertEqual(c["v"], 0.0)
        self.assertIn("경고", c["basis"])
        self.assertTrue(any("기타금융손익" in w for w in m["quality"]["warnings"]))
        self.assertAlmostEqual(rm["금융손익"]["q"]["2026Q3"]["v"], rm["이자손익"]["q"]["2026Q3"]["v"], places=2)

    # ── (g) 주석 이자율 이상 판정(2026-10-08): 주석/CF > INTEREST_NOTE_CF_MAX_RATIO 또는 > INTEREST_RATE_ABS_MAX 면 이상 — stale·절대상한 초과만 클립 ──
    def test_rate_note_ratio_ok_unchanged(self):
        m = self.build(synth_fin_notes())                                     # 주석 debt 5% vs CF 4% (1.25배) · asset 2% vs 3%
        a = m["assumptions"]
        self.assertAlmostEqual(a["interest_rate_debt"], 0.05, places=4)
        self.assertAlmostEqual(a["interest_rate_asset"], 0.02, places=4)
        chk = a["interest_rate_check"]
        self.assertEqual(chk["debt"], {"note": 0.05, "cf": 0.04, "ratio": 1.25, "note_last_q": "2026Q2", "cf_window": {"first": "2025Q3", "last": "2026Q2", "age_q": 0}, "action": "note", "reason": None})
        self.assertEqual(chk["asset"]["action"], "note")
        self.assertAlmostEqual(chk["asset"]["ratio"], 0.67)
        self.assertIn("2.0", chk["rule"])
        self.assertFalse(any("이자율" in w for w in m["quality"]["warnings"]))

    def test_rate_abs_cap_clips_to_cf(self):
        m = self.build(synth_fin_notes(note_accts={"이자비용": 7000.0}))     # 70억×4 ÷ 1200억 = 23.3% > 20% · 주석/CF 5.83배 → CF 4%
        a = m["assumptions"]
        self.assertAlmostEqual(a["interest_rate_debt"], 0.04, places=4)
        self.assertTrue(a["interest_rate_source"]["debt"].startswith("CF 이자지급"))
        self.assertIn("클립", a["interest_rate_source"]["debt"])
        d = a["interest_rate_check"]["debt"]
        self.assertEqual(d["action"], "clipped_cf")
        self.assertAlmostEqual(d["note"], 0.2333, places=4)
        self.assertAlmostEqual(d["ratio"], 5.83)
        self.assertIn("상한 20%", d["reason"])
        self.assertEqual(d["cf_window"], {"first": "2025Q3", "last": "2026Q2", "age_q": 0})
        self.assertIn("CF 창 2025Q3~2026Q2(= la)", d["reason"])
        self.assertTrue(any("총차입금 이자율" in w and "클립" in w and "CF 창 2025Q3~2026Q2" in w for w in m["quality"]["warnings"]))
        self.assertAlmostEqual(rows_of(m)["이자손익"]["q"]["2026Q3"]["v"], (1000 * 0.02 - 1200 * 0.04) / 4, places=2)   # −7.0
        self.assertEqual(a["interest_rate_check"]["asset"]["action"], "note")

    def test_rate_ratio_recent_kept_with_warning(self):
        m = self.build(synth_fin_notes(note_accts={"이자비용": 4000.0}))     # 13.33%, 주석/CF 3.33배, 주석 마지막 2026Q2 = la → 유지 + 경고
        a = m["assumptions"]
        self.assertAlmostEqual(a["interest_rate_debt"], 0.13333, places=4)
        self.assertTrue(a["interest_rate_source"]["debt"].startswith("주석 이자비용"))
        d = a["interest_rate_check"]["debt"]
        self.assertEqual((d["action"], d["note_last_q"], d["reason"]), ("kept_warn", "2026Q2", None))
        self.assertAlmostEqual(d["ratio"], 3.33)
        ws = [w for w in m["quality"]["warnings"] if "이자율" in w]
        self.assertEqual(len(ws), 1)
        self.assertIn("유지", ws[0])
        self.assertIn("3.3배", ws[0])
        self.assertAlmostEqual(rows_of(m)["이자손익"]["q"]["2026Q3"]["v"], (1000 * 0.02 - 1200 * 4000.0 * 4 / 120_000.0) / 4, places=2)   # −35.0

    def test_rate_ratio_stale_clips_to_cf(self):
        m = self.build(synth_fin_notes(note_accts={"이자비용": 4000.0}, note_qs=M.q_range("2024Q3", "2025Q2")))   # 주석 마지막 2025Q2 ≠ la 2026Q2
        a = m["assumptions"]
        self.assertAlmostEqual(a["interest_rate_debt"], 0.04, places=4)
        d = a["interest_rate_check"]["debt"]
        self.assertEqual((d["action"], d["note_last_q"]), ("clipped_cf", "2025Q2"))
        self.assertIn("2025Q2", d["reason"])
        self.assertIn("stale", d["reason"])
        self.assertIn("CF 창 2025Q3~2026Q2(= la)", d["reason"])
        self.assertEqual(d["cf_window"], {"first": "2025Q3", "last": "2026Q2", "age_q": 0})
        self.assertIn("stale", a["interest_rate_source"]["debt"])
        # asset 쪽은 비율 0.67 로 이상이 아니므로 stale 이어도 주석 유지
        self.assertAlmostEqual(a["interest_rate_asset"], 0.02, places=4)
        self.assertEqual(a["interest_rate_check"]["asset"]["action"], "note")
        self.assertTrue(any("총차입금 이자율" in w and "stale" in w for w in m["quality"]["warnings"]))

    def test_rate_abs_cap_without_cf(self):
        m = self.build(synth_fin_notes(note_accts={"이자비용": 7000.0}, no_cf_interest=True))   # CF 이자 키 없음 → 상한 20% 로 클립
        a = m["assumptions"]
        self.assertEqual(a["interest_rate_debt"], M.INTEREST_RATE_ABS_MAX)
        self.assertEqual(a["interest_rate_debt"], 0.20)
        d = a["interest_rate_check"]["debt"]
        self.assertEqual((d["action"], d["cf"], d["ratio"], d["cf_window"]), ("clipped_abs", None, None, None))
        self.assertIn("상한 20%", a["interest_rate_source"]["debt"])
        self.assertIn("CF 없음", a["interest_rate_source"]["debt"])
        self.assertTrue(any("총차입금 이자율" in w and "상한 20%" in w for w in m["quality"]["warnings"]))
        self.assertAlmostEqual(a["interest_rate_asset"], 0.02, places=4)
        self.assertEqual(a["interest_rate_check"]["asset"], {"note": 0.02, "cf": None, "ratio": None, "note_last_q": "2026Q2", "cf_window": None, "action": "note", "reason": None})

    # ── CF 창 신선도(2026-10-09 검증 수정): CF 교체는 CF 창이 주석 창 이상으로 최신일 때만 — 더 오래된 CF 로 바꾸면 신선도가 되레 떨어진다(KS인더스트리 101000) ──
    def test_rate_stale_note_fresh_cf_clips(self):
        m = self.build(synth_fin_notes(note_accts={"이자비용": 4000.0}, note_qs=M.q_range("2025Q1", "2026Q1")))   # 주석 1분기 늦음(~2026Q1), CF 창 ~2026Q2 = la → CF 교체 유지
        a = m["assumptions"]
        self.assertAlmostEqual(a["interest_rate_debt"], 0.04, places=4)
        d = a["interest_rate_check"]["debt"]
        self.assertEqual((d["action"], d["note_last_q"], d["cf_window"]), ("clipped_cf", "2026Q1", {"first": "2025Q3", "last": "2026Q2", "age_q": 0}))
        self.assertAlmostEqual(d["note"], 0.1333, places=4)
        self.assertIn("2026Q1 ≠ 마지막 실적 2026Q2(stale)", d["reason"])
        self.assertIn("CF 창 2025Q3~2026Q2(= la)", d["reason"])
        self.assertIn("CF 창 2025Q3~2026Q2(= la)", a["interest_rate_source"]["debt"])
        self.assertTrue(any("총차입금 이자율" in w and "CF 연율 4.0% 로 클립" in w and "CF 창 2025Q3~2026Q2" in w for w in m["quality"]["warnings"]))
        self.assertAlmostEqual(rows_of(m)["이자손익"]["q"]["2026Q3"]["v"], (1000 * 0.02 - 1200 * 0.04) / 4, places=2)   # −7.0

    def test_rate_stale_note_older_cf_kept(self):
        fin = synth_fin_notes(note_accts={"이자비용": 4000.0}, note_qs=M.q_range("2025Q1", "2026Q1"), cf_interest_upto="2024Q4")   # CF 창 2024Q1~2024Q4 < 주석 ~2026Q1
        m = self.build(fin)
        a = m["assumptions"]
        self.assertAlmostEqual(a["interest_rate_debt"], 0.13333, places=4)                                   # stale 이지만 CF 가 더 오래됨 → 주석 유지
        self.assertTrue(a["interest_rate_source"]["debt"].startswith("주석 이자비용"))
        self.assertIn("2025Q2~2026Q1", a["interest_rate_source"]["debt"])
        d = a["interest_rate_check"]["debt"]
        self.assertEqual((d["action"], d["note_last_q"], d["cf"], d["ratio"]), ("kept_warn", "2026Q1", 0.04, 3.33))
        self.assertEqual(d["cf_window"], {"first": "2024Q1", "last": "2024Q4", "age_q": 6})
        self.assertIn("stale", d["reason"])
        self.assertIn("CF 창 2024Q1~2024Q4(la −6분기) 가 주석 창(~2026Q1)보다 오래됨 → CF 로 교체 안 함", d["reason"])
        ws = [w for w in m["quality"]["warnings"] if "총차입금 이자율" in w]
        self.assertEqual(len(ws), 1)
        self.assertIn("더 오래된 CF 연율 4.0% 로 바꾸지 않고 주석 유지", ws[0])
        self.assertNotIn("클립", ws[0])
        self.assertAlmostEqual(rows_of(m)["이자손익"]["q"]["2026Q3"]["v"], (1000 * 0.02 - 1200 * 4000.0 * 4 / 120_000.0) / 4, places=2)   # −35.0
        # asset 쪽: 주석 2% vs CF 3%(같이 오래된 창) 비율 0.67 → 이상 아님, cf_window 만 기록
        self.assertEqual((a["interest_rate_check"]["asset"]["action"], a["interest_rate_check"]["asset"]["cf_window"]), ("note", {"first": "2024Q1", "last": "2024Q4", "age_q": 6}))

    def test_rate_abs_cap_older_cf_clips_to_abs(self):
        m = self.build(synth_fin_notes(note_accts={"이자비용": 7000.0}, cf_interest_upto="2026Q1"))   # 23.3% > 상한, 주석 ~2026Q2 최근, CF 창 2025Q2~2026Q1 1분기 오래됨
        a = m["assumptions"]
        self.assertEqual(a["interest_rate_debt"], M.INTEREST_RATE_ABS_MAX)                                # 더 오래된 CF 4% 가 아니라 상한 20%
        d = a["interest_rate_check"]["debt"]
        self.assertEqual((d["action"], d["cf"], d["ratio"], d["cf_window"]), ("clipped_abs", 0.04, 5.83, {"first": "2025Q2", "last": "2026Q1", "age_q": 1}))
        self.assertIn("주석 연율 23.3% > 상한 20%", d["reason"])
        self.assertIn("CF 창 2025Q2~2026Q1(la −1분기) 가 주석 창(~2026Q2)보다 오래됨", d["reason"])
        self.assertEqual(a["interest_rate_source"]["debt"], "주석 이자비용 연율 23.3% > 상한 20% → 상한으로 클립(CF 창 2025Q2~2026Q1(la −1분기) 가 주석보다 오래됨)")
        self.assertTrue(any("총차입금 이자율" in w and "상한 20% 로 클립" in w and "오래됨" in w for w in m["quality"]["warnings"]))
        self.assertAlmostEqual(rows_of(m)["이자손익"]["q"]["2026Q3"]["v"], (1000 * 0.02 - 1200 * 0.20) / 4, places=2)   # −55.0

    # ── (k') 외환이 기타영업외(other) 주석에만 있는 분기(2026-10-08): 외환손익 행 없이 기타금융손익 = 금융손익 − 이자 − 파생 ──
    def test_fx_in_other_nonop_residual(self):
        qs = M.q_range("2025Q1", "2026Q2")
        m = self.build(synth_fin_notes(other_fx_qs=qs, fin_pl=-850.0))       # 금융손익 −8.5 = 이자 −10 + 파생 −0.5 + 기타금융 +2.0 (외환 +1 은 기타영업외 안)
        rm = rows_of(m)
        self.assertNotIn("외환손익", rm)
        self.assertIn("파생상품손익", rm)
        self.assertIn("기타금융손익", rm)
        for q in qs:
            self.assertAlmostEqual(rm["기타금융손익"]["q"][q]["v"], 2.0, msg=q)
            self.assertEqual(rm["기타금융손익"]["q"][q]["src"], "fin.cons.is.금융손익 − 이자손익 − 파생상품손익(잔차) — 외환손익은 기타영업외 주석 → 금융 잔차에서 제외")
            s = sum(rm[k]["q"][q]["v"] for k in ("이자손익", "파생상품손익", "기타금융손익"))
            self.assertLessEqual(abs(s - rm["금융손익"]["q"][q]["v"]), 0.01, q)
        a = m["assumptions"]
        self.assertEqual(a["fx_in_other_nonop"]["quarters"], qs)
        self.assertEqual(a["fx_in_other_nonop"]["n"], 6)
        self.assertTrue(any("fx_in_other_nonop" in w and "2025Q1~2026Q2" in w for w in m["quality"]["warnings"]))
        # 추정: 기타금융 중위 2.0 (< 0.5 × |이자손익 추정 −10|) 채택, 금융손익 = 이자손익 + 2.0, basis 에 '외환손익 0' 없음, 캡 경고 없음
        q = "2026Q3"
        self.assertAlmostEqual(rm["기타금융손익"]["q"][q]["v"], 2.0)
        self.assertAlmostEqual(rm["금융손익"]["q"][q]["v"], rm["이자손익"]["q"][q]["v"] + 2.0, places=2)
        self.assertNotIn("외환손익 0", rm["금융손익"]["q"][q]["basis"])
        self.assertIn("파생상품손익 0", rm["금융손익"]["q"][q]["basis"])
        self.assertFalse(any("초과 → 추정 0" in w for w in m["quality"]["warnings"]))
        self.assertTrue(m["quality"]["identities_ok"], m["quality"]["identity_mismatches"])

    def test_fx_in_other_nonop_cap_label_drops_fx(self):
        qs = M.q_range("2025Q1", "2026Q2")
        m = self.build(synth_fin_notes(other_fx_qs=qs, fin_pl=2000.0))       # 잔차 +30.5 ≫ 50% × |−10| → 0 + 경고(문구에 '− 외환' 없음)
        ws = [w for w in m["quality"]["warnings"] if "초과 → 추정 0" in w]
        self.assertEqual(len(ws), 1)
        self.assertIn("금융손익 − 이자 − 파생 잔차", ws[0])
        self.assertNotIn("− 외환", ws[0])
        self.assertEqual(rows_of(m)["기타금융손익"]["q"]["2026Q3"]["v"], 0.0)

    def test_fx_in_both_buckets_unchanged(self):
        fin = synth_fin_notes()                                               # 삼성重 패턴: is(fin 주석) 외환 + other 주석에도 외환
        for q in M.q_range("2025Q1", "2026Q2"):
            for sc in ("cons", "sep"):
                fin[sc].setdefault("notes", {"fin": {}, "borrowings": {}, "other": {}})["other"][q] = dict(OTHER_FX_NOTE)
        m = self.build(fin)
        rm = rows_of(m)
        q = "2026Q2"
        self.assertAlmostEqual(rm["외환손익"]["q"][q]["v"], 1.0)
        self.assertAlmostEqual(rm["기타금융손익"]["q"][q]["v"], 4.5)
        self.assertEqual(rm["기타금융손익"]["q"][q]["src"], "fin.cons.is.금융손익 − 이자손익 − 외환손익 − 파생상품손익(잔차)")   # 기존 문구 그대로
        self.assertIsNone(m["assumptions"]["fx_in_other_nonop"])
        self.assertFalse(any("fx_in_other_nonop" in w for w in m["quality"]["warnings"]))
        self.assertIn("외환손익 0", rm["금융손익"]["q"]["2026Q3"]["basis"])

    def test_fx_other_without_interest_no_rows(self):
        qs = M.q_range("2025Q1", "2026Q2")
        m = self.build(synth_fin_notes(other_fx_qs=qs, drop={q: ["이자수익", "이자비용"] for q in qs}))
        rm = rows_of(m)
        self.assertNotIn("기타금융손익", rm)                                  # 이자손익 실적 없이는 잔차를 만들지 않는다
        self.assertNotIn("외환손익", rm)
        self.assertIn("파생상품손익", rm)
        self.assertTrue(all(c["kind"] == "estimate" for c in rm["이자손익"]["q"].values()))
        self.assertIsNone(m["assumptions"]["fx_in_other_nonop"])
        self.assertFalse(any("fx_in_other_nonop" in w for w in m["quality"]["warnings"]))

    def test_negative_stored_expense_not_flipped(self):
        """2026-10-05: kship_fin 이 비용을 양수로 통일해 저장하므로 모델은 더 이상 '과반 음수 → 반전' 휴리스틱을 쓰지 않는다.
        음수로 든 비용 계정은 환입(크기가 음수인 비용)으로 그대로 더한다 — 이자손익 = 이자수익 − (−이자비용) = 이자수익 + 이자비용."""
        fin = synth_fin_notes()
        for q in M.q_range("2025Q1", "2026Q2"):
            for sc in ("cons", "sep"):
                for k in ("이자비용", "외환차손", "외화환산손실", "파생상품손실"):
                    fin[sc]["is"][q][k] = -NOTE_ACCTS[k]
        m = self.build(fin)
        rm = rows_of(m)
        q = "2026Q1"
        exp = (NOTE_ACCTS["이자수익"] + NOTE_ACCTS["이자비용"]) / 100.0
        self.assertAlmostEqual(rm["이자손익"]["q"][q]["v"], round(exp, 2))
        self.assertNotIn("부호 반전", rm["이자손익"]["q"][q]["src"])
        self.assertFalse(any("부호 반전" in w for w in m["quality"]["warnings"]))

    @unittest.skipUnless(os.path.isfile(REAL_SEJIN), "assets/fin/075580.json 없음")
    def test_real_sejin_2026q2_detail(self):
        """세진 fin(2026-10 주석 수집본) 2026Q2: 이자수익 731.79 · 이자비용 2,239.90 · 외환차익 507.94 · 외환차손 16.19 ·
        외화환산이익 1,238.84 · 외화환산손실 14.61 백만원, 파생상품 계정 없음, 금융손익 6,121.02 — 주석 있는 분기는 2026Q2 하나."""
        with open(REAL_SEJIN, encoding="utf-8") as f:
            raw = json.load(f)
        m = M.build_model("075580", FakeCtx(fins={"075580": raw}, roles={"075580": "equip"}))
        rm = rows_of(m)
        q = "2026Q2"
        self.assertEqual(rm["이자손익"]["q"][q], {"v": -15.08, "kind": "actual", "src": "fin.cons.is.이자수익 − fin.cons.is.이자비용"})
        self.assertEqual(rm["외환손익"]["q"][q]["v"], 17.16)
        self.assertEqual(rm["금융손익"]["q"][q]["v"], 61.21)
        self.assertNotIn("파생상품손익", rm)                                  # 파생 계정 None → 행 없음
        self.assertNotIn("기타금융손익", rm)                                  # 잔차도 None
        # 주석 수집 범위에 따라 실적 분기 수가 달라진다(하위 노드만 → 1분기, 부모절 폴백 뒤 → 9분기) — 2026Q2 가 들어 있고,
        # 실적으로 찍힌 분기는 전부 fin 에 이자수익·이자비용이 있는 분기여야 한다(데이터 표류에 흔들리지 않는 단언).
        actual_qs = sorted(k for k, c in rm["이자손익"]["q"].items() if c["kind"] == "actual")
        self.assertIn(q, actual_qs)
        fin_is = raw["cons"]["is"]
        for k in actual_qs:
            self.assertIsNotNone(fin_is[k].get("이자수익"), k); self.assertIsNotNone(fin_is[k].get("이자비용"), k)
        n_note = sum(1 for k, v in fin_is.items() if v.get("이자수익") is not None)
        src = m["assumptions"]["interest_rate_source"]["asset"]
        if n_note >= 4:                                                    # 주석 실측 4분기 이상 → 주석 연율
            self.assertFalse(src.startswith("CF 이자수취"), src)
        else:                                                              # 그 미만 → CF 폴백
            self.assertTrue(src.startswith("CF 이자수취"), src)


def _mode(mode):
    """NEW_ORDERS_POST_ORIGIN_MODE 스위치 컨텍스트(라운드 7 L1). T6 D1 테스트는 exclude_sls 안에서 그대로 돈다."""
    return mock.patch.object(M, "NEW_ORDERS_POST_ORIGIN_MODE", mode)


def synth_sls_ledger(amts=None, base=None):
    """synth_sls(또는 base) + origin 이전 체결 counted 계약(체결 분기별 금액, 백만원; 일정 없음 → SLS 열·동결 재구성에는 안 들어가고 원장 체결 속도에만).
    기본 2025Q4 2,500억 · 2026Q1 2,000억 · 2026Q2 3,000억 — synth_sls 의 c2(2025Q3 2,000억)와 합쳐 창 2025Q3~2026Q2 = [2,000, 2,500, 2,000, 3,000]
    → min 2,000 / median 2,250 / max 3,000 (평균 2,375)."""
    s = base or synth_sls()
    amts = amts or {"2025Q4": 250_000.0, "2026Q1": 200_000.0, "2026Q2": 300_000.0}
    for i, (q, amt) in enumerate(sorted(amts.items())):
        d = M.q_end_date(q).isoformat()
        s["contracts"].append({"rcp": "L%d" % i, "type": "CONT", "ships": 1, "amt_krw_m": amt, "amt_usd_m": amt / 1400.0, "signed": d, "start": d,
                               "cohort": "③중마진", "counted": True, "signed_by_origin": True})
    return s


def synth_sls_post(keyed=True):
    """synth_sls + origin(2026Q2) 이후 체결 계약 c3(2026-08-01, LNGC, 2026Q3~2027Q4 분기 20백만$, 수주시점 1,400원 — 원화 1,680억).
    keyed=True 면 by_quarter 에 T6 키(_signed_by_origin/_post_origin), False 면 구버전 sls(키 없음 → contracts 재계산)."""
    s = synth_sls()
    c3 = {"rcp": "c", "type": "LNGC", "ships": 2, "amt_krw_m": 168_000.0, "amt_usd_m": 120.0, "signed": "2026-08-01", "start": "2026-08-01", "end": "2027-12-31",
          "cohort": "⑤초호황", "counted": True, "signed_by_origin": False, "fx_at_sign": 1400.0, "schedule": {q: 20.0 for q in M.q_range("2026Q3", "2027Q4")}}
    for c in s["contracts"]:
        c["signed_by_origin"] = True
    s["contracts"].append(c3)
    for q, b in s["by_quarter"].items():
        add = c3["schedule"].get(q, 0.0)
        b["spot_assumed"] = 1400.0
        if keyed:
            b["marine_hedged_krw_m_signed_by_origin"] = b["marine_hedged_krw_m"]
            b["marine_hedged_krw_m_post_origin"] = add * 1400
        for k in ("usd_m", "marine_usd_m"):
            b[k] += add
        for k in ("hedged_krw_m", "marine_hedged_krw_m"):
            b[k] += add * 1400
    return s


def add_post_contract(s, rcp, type_, signed, amt_krw_m, qs, usd_per_q):
    """synth_sls_post 류 keyed sls 에 origin 이후 체결 계약 하나 추가(일정 qs 분기별 usd_per_q 백만$, 환율 1,400) — by_quarter 합계·_post_origin 키도 맞춘다."""
    s["contracts"].append({"rcp": rcp, "type": type_, "ships": 1, "amt_krw_m": amt_krw_m, "amt_usd_m": amt_krw_m / 1400.0, "signed": signed, "start": signed,
                           "cohort": "③중마진", "counted": True, "signed_by_origin": False, "fx_at_sign": 1400.0, "schedule": {q: usd_per_q for q in qs}})
    for q in qs:
        b = s["by_quarter"][q]
        b["marine_hedged_krw_m_post_origin"] += usd_per_q * 1400
        for k in ("usd_m", "marine_usd_m"):
            b[k] += usd_per_q
        for k in ("hedged_krw_m", "marine_hedged_krw_m"):
            b[k] += usd_per_q * 1400
    return s


class TestT6Fixes(SyntheticAssets, unittest.TestCase):
    """T6 — T3 적대 검토 결함 D1~D10 회귀 테스트(합성 데이터)."""

    def _yard(self, sls, panel=None):
        fin = synth_fin("010140", "삼성", quarters=M.q_range("2023Q1", "2026Q2"), rev0=200_000.0, g_q=0.0)
        ctx = FakeCtx(fins={"010140": fin}, slss={"010140": sls}, roles={"010140": "yard"})
        if panel:
            ctx.panel = {"010140": panel}
        return M.build_model("010140", ctx)

    # D1 ── origin 이후 공시 수주는 패널 신규와 겹치므로 '기존' SLS 에서 뺀다
    def test_d1_post_origin_excluded_when_panel_included(self):
        with _mode("exclude_sls"):
            big = dict(new_orders=500_000.0)                             # 패널 분기 신규수주 5,000억 ≥ 공시 체결 1,680억 → 제외 비율 1(기존 규칙 그대로)
            ref = self._yard(synth_sls(), synth_panel(**big))            # c3 없는 선표 + 패널
            rr = rows_of(ref)
            for keyed in (True, False):
                m = self._yard(synth_sls_post(keyed), synth_panel(**big))
                rm, d = rows_of(m), m["segments"][0]["driver"]
                for q in M.q_range("2026Q3", "2028Q4"):
                    self.assertAlmostEqual(rm["매출조선"]["q"][q]["v"], rr["매출조선"]["q"][q]["v"], places=1, msg=(keyed, q))     # c3 SLS 가 다시 더해지지 않는다
                    self.assertAlmostEqual(rm["매출조선신규"]["q"][q]["v"], rr["매출조선신규"]["q"][q]["v"], places=2)
                px = d["post_origin_excluded"]
                self.assertEqual((px["n"], px["amt_krw_eok"], px["rcps"]), (1, 1680.0, ["c"]))
                self.assertAlmostEqual(px["sls_excluded_by_fy"]["2026"], 2 * 20 * 1400 / 100, places=1)
                self.assertAlmostEqual(px["sls_excluded_by_fy"]["2027"], 4 * 20 * 1400 / 100, places=1)
                self.assertIn("origin 이후 공시 수주 1건 1,680억은 패널 신규에 포함된 것으로 보아 기존 SLS 에서 제외", px["note"])
                self.assertIn("정의 불확실", px["definition_uncertainty"])
                self.assertIn("origin 이후 공시 3건을 제외", px["definition_uncertainty"])                 # 패널 industry_axes.schedule_exclusions
                self.assertIn("2026Q3 공시 수주 1,680억 vs 패널 base 신규수주", px["definition_uncertainty"])
                self.assertTrue(any(px["note"] in w and "정의 불확실" in w for w in m["quality"]["warnings"]))
                self.assertIn("기존 SLS 에서 제외", d["basis"])
                self.assertIn("공시 수주 SLS 280억 제외", rm["매출조선"]["q"]["2027Q1"]["basis"])
                self.assertIn("signed_by_origin", d["sls_source"])
                self.assertEqual(px["source"].startswith("sls.by_quarter"), keyed)
                # existing_only 도 같은 정의(origin 분기말까지 체결분) — c3 없는 선표의 existing_only 와 같다
                for y in ("2026", "2027", "2028"):
                    self.assertAlmostEqual(m["scenarios"]["existing_only"]["annual"][y]["rev"], ref["scenarios"]["existing_only"]["annual"][y]["rev"], places=1)
                self.assertIn("origin 이후 공시 수주 1건 제외", m["scenarios"]["meta"]["existing_revenue"])

    def test_d1_post_origin_kept_without_panel(self):
        ref, m = self._yard(synth_sls()), self._yard(synth_sls_post())
        rr, rm = rows_of(ref), rows_of(m)
        self.assertAlmostEqual(rm["매출조선"]["q"]["2027Q1"]["v"] - rr["매출조선"]["q"]["2027Q1"]["v"], 20 * 1400 / 100, places=1)
        self.assertIsNone(m["segments"][0]["driver"]["post_origin_excluded"])
        self.assertTrue(any("패널 신규 없음 → origin 이후 공시 수주 1건 1,680억은 선표(SLS)에 그대로 둠" in w for w in m["quality"]["warnings"]))

    def test_d1_post_origin_fraction_scales_with_panel_size(self):
        """패널 분기 신규수주가 공시 체결보다 작으면 공시 수주를 통째로 빼지 않는다 — 제외 비율 = min(1, 패널 ÷ 공시), 나머지는 SLS 에 둔다."""
        with _mode("exclude_sls"):
            ref = rows_of(self._yard(synth_sls(), synth_panel(new_orders=500_000.0)))
            for new_orders, frac in ((50_000.0, 500.0 / 1680.0), (500_000.0, 1.0)):    # 패널 500억 vs 공시 1,680억 / 5,000억 ≥ 1,680억
                m = self._yard(synth_sls_post(), synth_panel(new_orders=new_orders))
                rm, px = rows_of(m), m["segments"][0]["driver"]["post_origin_excluded"]
                self.assertAlmostEqual(px["included_fraction"], frac, places=3)
                kept = rm["매출조선"]["q"]["2027Q1"]["v"] - ref["매출조선"]["q"]["2027Q1"]["v"]
                self.assertAlmostEqual(kept, 20 * 1400 / 100 * (1.0 - frac), places=1)  # 2027Q1 공시 SLS 280억 × (1 − 제외 비율) 만 남는다
            m = self._yard(synth_sls_post(), synth_panel(new_orders=50_000.0))
            self.assertIn("중", m["segments"][0]["driver"]["post_origin_excluded"]["note"])
            self.assertTrue(any("규모만큼" in rm_["basis"] for rm_ in [rows_of(m)["매출조선"]["q"]["2027Q1"]]))

    def test_post_origin_panel_fraction_helper(self):
        post = {"by_sign_q": {"2026Q3": 1000.0, "2026Q4": 400.0}, "amt": 1400.0}
        self.assertEqual(M._post_origin_panel_fraction(post, {"new_orders_by_q": {"2026Q3": 2000.0, "2026Q4": 400.0}}), (1.0, {"2026Q3": 1.0, "2026Q4": 1.0}))
        f, by = M._post_origin_panel_fraction(post, {"new_orders_by_q": {"2026Q3": 500.0, "2026Q4": 400.0}})
        self.assertEqual(by, {"2026Q3": 0.5, "2026Q4": 1.0})
        self.assertAlmostEqual(f, (500.0 + 400.0) / 1400.0, places=9)
        f0, by0 = M._post_origin_panel_fraction(post, {"new_orders_by_q": {}})        # 패널이 그 분기 신규수주를 안 주면 제외 0
        self.assertEqual((f0, by0), (0.0, {"2026Q3": 0.0, "2026Q4": 0.0}))
        fu, _ = M._post_origin_panel_fraction({"by_sign_q": {"2026Q3": 1000.0}, "amt": 1500.0}, {"new_orders_by_q": {"2026Q3": 1000.0}})   # 날짜 없는 500억은 1 로 본다
        self.assertAlmostEqual(fu, 1.0, places=9)
        self.assertEqual(M._post_origin_panel_fraction({"by_sign_q": {}, "amt": 0.0}, {}), (1.0, {}))

    def test_d1_split_helper_keyed_vs_legacy_agree(self):
        fq = M.q_range("2026Q3", "2028Q4")
        a, b = M._sls_post_origin(synth_sls_post(True), fq), M._sls_post_origin(synth_sls_post(False), fq)
        for q in fq:
            self.assertAlmostEqual(a["post"][q], b["post"][q], places=6)
            self.assertAlmostEqual(a["existing"][q] + a["post"][q], (synth_sls_post()["by_quarter"][q]["marine_hedged_krw_m"]) / 100, places=6)
        self.assertEqual(dict(a["by_sign_q"]), {"2026Q3": 1680.0})

    # D2 ── 음(−)·클립 밖 유효세율은 클립하지 않고 8분기 양(+)세전 분기 중위 → 없으면 22%
    def test_d2_negative_effective_tax_falls_back_to_positive_median(self):
        fin = synth_fin(tax=0.24)
        qs = fin["quarters"]
        for q in qs[-8:-5]:                                          # 최근 8분기 중 3분기: 이연법인세 환입처럼 법인세 = −3 × 세전 → 12분기 합 음수
            for sc in ("cons", "sep"):
                fin[sc]["is"][q]["법인세비용"] = -3.0 * fin[sc]["is"][q]["법인세비용차감전계속사업이익"]
        m = M.build_model("999999", FakeCtx(fins={"999999": fin}, roles={"999999": "equip"}))
        a = m["assumptions"]
        self.assertAlmostEqual(a["tax_rate"], 0.24, places=4)
        self.assertEqual(a["tax_path"], "median_pos8")
        self.assertIn("클립 대신", a["tax_basis"])
        self.assertIn("5~27% 밖", a["tax_basis"])
        rm = rows_of(m)
        q = "2027Q1"
        self.assertAlmostEqual(rm["법인세비용"]["q"][q]["v"], rm["세전이익"]["q"][q]["v"] * 0.24, places=1)
        # 세전이 전부 음수 → 양(+) 분기 없음 → 22%
        fin2 = synth_fin()
        for q in fin2["quarters"]:
            for sc in ("cons", "sep"):
                fin2[sc]["is"][q]["법인세비용차감전계속사업이익"] = -1000.0
                fin2[sc]["is"][q]["법인세비용"] = 100.0
        a2 = M.build_model("999999", FakeCtx(fins={"999999": fin2}, roles={"999999": "equip"}))["assumptions"]
        self.assertEqual((a2["tax_rate"], a2["tax_path"]), (M.TAX_DEFAULT, "default"))
        self.assertIn("세전 > 0 분기 없음", a2["tax_basis"])
        # 정상 범위(22%)는 그대로
        self.assertEqual(M.build_model("999999", FakeCtx(fins={"999999": synth_fin()}, roles={"999999": "equip"}))["assumptions"]["tax_path"], "eff12")

    # D3 ── 등급 없는 비중을 실측 OPM 중위로 채워 타겟 가중, 코호트 경로 소멸 경고
    def test_d3_ungraded_share_filled_with_actual_median(self):
        s = synth_sls()
        for q, t in s["target_opm"].items():
            t["opm"], t["graded_share"] = 0.15, (0.5 if q <= "2026Q2" else 1.0)
        m = self._yard(s)
        rm, d = rows_of(m), m["segments"][0]["driver"]
        # 실측 OPM 20%: 과거 타겟 = 0.5×15% + 0.5×20% = 17.5% → 캘리브레이션 +2.5%p, 미래 타겟 15% → 17.5%
        self.assertAlmostEqual(d["calibrated_shift"], 0.025, places=4)
        self.assertAlmostEqual(rm["OPM"]["q"]["2027Q1"]["v"], 0.175, places=4)
        tp = d["target_path"]
        self.assertTrue(tp["cohort_path_absent"])
        self.assertAlmostEqual(tp["fill_opm_median_4q"], 0.20, places=4)
        self.assertIn("코호트 경로 없음 → 실측 중위 고정", rm["OPM"]["q"]["2027Q1"]["basis"])
        self.assertTrue(any("코호트 경로 없음 → 실측 중위 고정" in w for w in m["quality"]["warnings"]))
        # 타겟이 분기마다 다르면(코호트 경로 있음) 경고 없음, 등급 100% 면 예전 식 그대로(타겟 + 실측−타겟)
        s2 = synth_sls()
        for q, t in s2["target_opm"].items():
            t["opm"], t["graded_share"] = (0.10 if q <= "2026Q2" else 0.15), 1.0
        m2 = self._yard(s2)
        self.assertAlmostEqual(rows_of(m2)["OPM"]["q"]["2027Q1"]["v"], 0.25, places=4)
        self.assertFalse(m2["segments"][0]["driver"]["target_path"]["cohort_path_absent"])
        self.assertFalse(any("코호트 경로 없음" in w for w in m2["quality"]["warnings"]))

    # D4 ── 세진 연결조정 = 종속사 매출 × 잔차 비율(최근 4분기 중위)
    def test_d4_sejin_adjustment_scales_with_subsidiaries(self):
        ctx = sejin_ctx(vary=True)
        qs = M.q_range("2022Q1", "2026Q2")
        for c, n in M.SEJIN_SUBS:
            ctx._fin[c] = synth_fin(c, n, quarters=qs, rev0=10_000.0, g_q=0.04)                 # 종속사 성장
        sj = ctx._fin["075580"]
        for q in qs:
            sub = sum(ctx._fin[c]["cons"]["is"][q]["매출액(수익)"] for c, _ in M.SEJIN_SUBS)
            sj["cons"]["is"][q]["매출액(수익)"] = sj["sep"]["is"][q]["매출액(수익)"] + 0.4 * sub     # 잔차 = −0.6 × 종속사
        m = M.build_model("075580", ctx)
        rm = rows_of(m)
        fq = [q for q in m["periods"]["quarters"] if q > "2026Q2"]
        for q in fq:
            self.assertAlmostEqual(rm["매출연결조정"]["q"][q]["v"], -0.6 * rm["매출종속사"]["q"][q]["v"], delta=0.02)
            self.assertIn("잔차/종속사 매출", rm["매출연결조정"]["q"][q]["basis"])
        self.assertLess(rm["매출연결조정"]["q"][fq[-1]]["v"], rm["매출연결조정"]["q"][fq[0]]["v"])          # 상수가 아니다
        drv = next(sg for sg in m["segments"] if sg["key"] == "연결조정")["driver"]
        self.assertEqual(drv["type"], "residual_ratio_to_subsidiaries")
        self.assertAlmostEqual(drv["ratio_to_sub_rev"], -0.6, places=4)

    # D5 ── (a) 반올림 전 비교 (b) 현재 채택 조합 시험 (c) undetermined
    def test_d5a_oos_compares_unrounded(self):
        t = TestLinkOOS()
        ctx, _ = t._ctx(0.03, lambda i, q, x: 0.05 * x[t.QS[max(i - 2, 0)]], noisy=True)
        y = {q: ctx._fin["222222"]["cons"]["is"][q]["매출액(수익)"] / 100 for q in t.QS}
        cands = M._customer_weight_candidates("222222", ctx)
        from unittest import mock
        # 추세 11.94 · 연동 13.06: 반올림 뒤(13.1 > 11.9×1.1=13.09)면 기각이던 경계 — 반올림 전(13.06 ≤ 13.134)으로 채택
        with mock.patch.object(M, "wape_raw", side_effect=[11.94, 13.06, 13.06]):
            o = M._link_oos(y, cands, ctx, "2026Q2")
        self.assertIs(o["adopted"], True)
        self.assertEqual((o["wape_link"], o["wape_trend"]), (13.1, 11.9))
        self.assertGreater(o["wape_link"], o["wape_trend"] * M.OOS_WORSE_TOL)                       # 표시값만 보면 기각처럼 보인다
        self.assertEqual((o["wape_link_raw"], o["wape_trend_raw"]), (13.06, 11.94))
        self.assertEqual(M.wape([(110, 100), (90, 100)]), 10.0)
        self.assertAlmostEqual(M.wape_raw([(113.06, 100)]), 13.06, places=9)

    def test_d5b_adopted_combo_is_tested_and_c_undetermined(self):
        t = TestLinkOOS()
        ctx, _ = t._ctx(0.03, lambda i, q, x: 0.05 * x[t.QS[max(i - 2, 0)]], noisy=True)
        m = M.build_model("222222", ctx)
        d = m["segments"][0]["driver"]
        o = d["selection_oos"]
        self.assertEqual(o["tested"], "adopted_combo")
        lt = o["link_tested"]
        self.assertEqual((lt["wkey"], lt["lag_q"], lt["transform"], lt["window_q"]), (d["weights_key"], d["lag_q"], d["transform"], d["window_q"]))
        self.assertIn("재적합", lt["note"])
        self.assertIn("참고", o["link_at_freeze"]["note"])
        self.assertTrue(all("link_reselected" in r for r in o["detail"]))
        self.assertIn("유의성 + OOS", d["adoption_basis"])
        # 채택 조합을 동결 데이터로 재적합할 수 없으면 undetermined
        cands = M._customer_weight_candidates("222222", ctx)
        y = {q: ctx._fin["222222"]["cons"]["is"][q]["매출액(수익)"] / 100 for q in t.QS}
        o2 = M._link_oos(y, cands, ctx, "2026Q2", adopted={"wkey": "없는후보", "lag": 1, "transform": "level", "window": 8})
        self.assertEqual((o2["adopted"], o2["decision"]), ("undetermined", "undetermined"))
        self.assertIn("재적합할 수 없음", o2["note"])
        self.assertIsNotNone(o2["link_at_freeze"])                                                   # 재선택 결과는 참고로 남는다

    # D6 ── 금융손익 실적→추정 단절 경고(값 불변)
    def test_d6_fin_pl_gap_warning_value_unchanged(self):
        base = M.build_model("999999", FakeCtx(fins={"999999": synth_fin()}, roles={"999999": "equip"}))
        fin = synth_fin()
        for q in fin["quarters"]:
            for sc in ("cons", "sep"):
                fin[sc]["is"][q]["금융손익"] = -5000.0                                               # 실적 −50억/분기(평가손실 등)
        m = M.build_model("999999", FakeCtx(fins={"999999": fin}, roles={"999999": "equip"}))
        g = m["assumptions"]["fin_pl_gap"]
        self.assertTrue(g["flagged"])
        self.assertEqual(g["actual_median_4q"], -50.0)
        self.assertTrue(any("금융손익 실적→추정 단절" in w and "중위 -50억" in w for w in m["quality"]["warnings"]))
        self.assertEqual(rows_of(m)["금융손익"]["q"]["2026Q3"]["v"], rows_of(base)["금융손익"]["q"]["2026Q3"]["v"])     # 값은 바꾸지 않는다
        self.assertFalse(base["assumptions"]["fin_pl_gap"]["flagged"])                               # 실적 −5억 vs 추정 −4.5억 → 경고 없음
        self.assertFalse(any("금융손익 실적→추정 단절" in w for w in base["quality"]["warnings"]))

    # D7 ── status 는 데이터 완전성만, driver_fallback 별도
    def test_d7_status_data_only_and_driver_fallback(self):
        m = M.build_model("999999", FakeCtx(fins={"999999": synth_fin()}, roles={"999999": "equip"}))
        self.assertEqual((m["status"], m["driver_fallback"]), ("full", "no_link"))
        short = M.build_model("999999", FakeCtx(fins={"999999": synth_fin(quarters=M.q_range("2025Q1", "2026Q2"))}, roles={"999999": "equip"}))
        self.assertEqual(short["status"], "partial")                                                  # fin 6분기 < 8
        y = self._yard(synth_sls())
        self.assertEqual(y["driver_fallback"], "none")
        self.assertEqual(M.summary_row(y)["driver_fallback"], "none")
        self.assertEqual(set(M.DRIVER_FALLBACKS), {"corr", "significance", "n", "oos", "eligibility", "no_link", "none"})
        self.assertEqual(M._driver_fallback({"fallback": True, "driver": {"customer_link_rejected": {"rejected_by": "significance"}}}), "significance")

    # D9 ── 시나리오 OP 델타는 반올림 전 OPM
    def test_d9_scenario_op_uses_unrounded_opm(self):
        fq = ["2026Q3"]
        rows = {"매출액": {"2026Q3": {"v": 1000.0, "kind": "estimate"}}, "영업이익": {"2026Q3": {"v": 97.36, "kind": "estimate"}},
                "OPM": {"2026Q3": {"v": 0.0974, "kind": "estimate"}}}
        plan = {"opm": {"2026Q3": (0.097355, "")}, "scenarios_new": {"conservative": {"2026Q3": 0.0}, "base": {"2026Q3": 100.0}, "optimistic": {"2026Q3": 10_100.0}}}
        sc = M._build_scenarios(rows, plan, fq, "2026Q2")
        self.assertEqual(sc["optimistic"]["quarterly"]["2026Q3"]["op"], round(97.36 + 10_000.0 * 0.097355, 2))      # 1,070.91 (r4 OPM 이면 1,071.36)
        self.assertEqual(sc["base"]["quarterly"]["2026Q3"]["op"], 97.36)

    # D10 ── 캡 적용 sls 에서 1/backlog_coverage 는 null + 문구
    def test_d10_scale_alternative_null_when_capped(self):
        s = synth_sls()
        s["reconcile_summary"]["backlog_coverage_at_origin"] = 1.164
        s["backlog_cap_applied"] = True
        d = self._yard(s)["segments"][0]["driver"]
        self.assertIsNone(d["scale_alternatives"]["1/backlog_coverage"])
        self.assertIn("곱하지 말 것", d["scale_alternatives_note"])
        self.assertIn("0.8591", d["scale_alternatives_note"])
        d0 = self._yard(synth_sls())["segments"][0]["driver"]
        self.assertEqual(d0["scale_alternatives"]["1/backlog_coverage"], 2.0)                         # 캡 없음(커버리지 0.5) → 표시값 그대로


class TestD2Carryforward(SyntheticAssets, unittest.TestCase):
    """라운드 7 L2(2026-10-08 오너 결정) — 이월결손 세율 경로 carryforward_ramp. 감지: 최근 8분기 중 세전 > 0 분기 ≥ 4 · 그 (법인세/세전) 중위 < 5% ·
    최근 4분기 중위 < 5%(삼성重처럼 정상화된 회사 배제). 경로: 저세율(0~5% 클립)을 origin 회계연도 말까지 유지 → 다음 해부터 2028Q4 까지 선형 램프로 22%.
    분기별 tax_schedule 이 추정 법인세에 들어가고 조정EPS 의 '모델 세율' 폴백도 low 를 받는다. 비대상(eff12·median_pos8·45%·22%) 은 기존 테스트 그대로."""

    FQ = M.q_range("2026Q3", "2028Q4")

    @staticmethod
    def _build(fin):
        return M.build_model("999999", FakeCtx(fins={"999999": fin}, roles={"999999": "equip"}))

    @staticmethod
    def _retax(fin, qs, rate, pretax=None):
        """지정 분기의 법인세 = rate × 세전(pretax 를 주면 기타영업외로 세전도 바꿈)으로 두고 NI 사슬(지배 90%·비지배 10%)을 다시 맞춘다(항등식 유지)."""
        for q in qs:
            for sc in ("cons", "sep"):
                r = fin[sc]["is"][q]
                if pretax is not None:
                    r["기타영업외손익"] += pretax - r["법인세비용차감전계속사업이익"]
                    r["법인세비용차감전계속사업이익"] = pretax
                pt = r["법인세비용차감전계속사업이익"]
                r["법인세비용"] = pt * rate
                r["당기순이익"] = pt - r["법인세비용"]
                r["(지배주주지분)당기순이익"], r["(비지배주주지분)당기순이익"] = r["당기순이익"] * 0.9, r["당기순이익"] * 0.1
        return fin

    def test_d2_carryforward_detected_and_ramp(self):
        m = self._build(synth_fin(tax=0.01))                       # 전 분기 1% → eff12 1%·median_pos8 1% 모두 5~27% 밖 → default 자리에서 감지
        a, rm = m["assumptions"], rows_of(m)
        self.assertEqual(a["tax_path"], M.TAX_CF_PATH)
        self.assertAlmostEqual(a["tax_rate"], 0.01, places=4)
        self.assertEqual(a["tax_rate_terminal"], M.TAX_DEFAULT)
        s = a["tax_schedule"]
        self.assertEqual(sorted(s), self.FQ)
        self.assertAlmostEqual(s["2026Q3"], 0.01, places=4)
        self.assertAlmostEqual(s["2026Q4"], 0.01, places=4)
        self.assertAlmostEqual(s["2027Q1"], 0.01 + 0.21 / 8, delta=1e-4)
        self.assertEqual(s["2028Q4"], M.TAX_DEFAULT)
        for q0, q1 in zip(self.FQ, self.FQ[1:]):
            self.assertLessEqual(s[q0], s[q1])
        for q in self.FQ:
            pt, tx, ni = rm["세전이익"]["q"][q]["v"], rm["법인세비용"]["q"][q]["v"], rm["당기순이익"]["q"][q]["v"]
            self.assertAlmostEqual(tx, max(pt, 0.0) * s[q], places=1, msg=q)
            self.assertAlmostEqual(ni, pt - tx, places=1, msg=q)
        self.assertIn("이월결손 경로 유지", rm["법인세비용"]["q"]["2026Q4"]["basis"])
        self.assertIn("이월결손 경로 램프 1/8", rm["법인세비용"]["q"]["2027Q1"]["basis"])
        self.assertIn("램프 8/8", rm["법인세비용"]["q"]["2028Q4"]["basis"])
        self.assertIn("이월결손", a["tax_basis"])
        cf = a["tax_carryforward"]
        self.assertEqual((cf["n_pos8"], cf["hold_until"], cf["ramp_from"], cf["ramp_to"]), (8, "2026Q4", "2027Q1", "2028Q4"))
        self.assertAlmostEqual(cf["median_pos8"], 0.01, places=4)
        self.assertAlmostEqual(cf["median_recent4"], 0.01, places=4)
        self.assertTrue(any("이월결손 경로" in w for w in m["quality"]["warnings"]))
        self.assertTrue(m["quality"]["identities_ok"])
        ne = a["nol_evidence"]
        self.assertIsNone(ne["dta_eok"])                                                           # 합성 BS 에 이연법인세 없음 → 한도도 None
        self.assertIsNone(ne["nol_cap_eok"])
        self.assertIn("참고용", ne["note"])

    def test_d2_carryforward_not_when_recent_normalized(self):
        # 삼성重 패턴: 이전 9분기 −5%(이연법인세 인식) → 최근 3분기 22% 정상화. eff12 ≈ 1.8%·양(+)세전 중위 −5% 로 default 자리까지 오지만 최근 4분기 중위 22% → 경로 없음
        fin = self._retax(synth_fin(tax=-0.05), synth_fin()["quarters"][-3:], 0.22)
        a = self._build(fin)["assumptions"]
        self.assertEqual((a["tax_path"], a["tax_rate"]), ("default", M.TAX_DEFAULT))
        self.assertIsNone(a["tax_schedule"])
        self.assertIsNone(a["tax_rate_terminal"])
        self.assertIsNone(a["tax_carryforward"])
        self.assertNotIn("이월결손", a["tax_basis"])
        self.assertIsNotNone(a["nol_evidence"])                                                      # 정보 필드는 전 회사 공통

    def test_d2_carryforward_needs_min_pos_quarters(self):
        fin = self._retax(synth_fin(tax=0.01), synth_fin()["quarters"][-8:-3], 0.0, pretax=-1000.0)   # 최근 8분기 중 5분기 세전 −10억 → 세전 > 0 은 3분기 < 4
        a = self._build(fin)["assumptions"]
        self.assertEqual((a["tax_path"], a["tax_rate"]), ("default", M.TAX_DEFAULT))
        self.assertIsNone(a["tax_schedule"])

    def test_d2_carryforward_negative_median_floors_to_zero(self):
        m = self._build(synth_fin(tax=-0.3))                       # 법인세 = −0.3 × 세전(이연법인세 인식) → 중위 −30% < 5% → low 는 0 으로 클립
        a, rm = m["assumptions"], rows_of(m)
        self.assertEqual(a["tax_path"], M.TAX_CF_PATH)
        self.assertEqual(a["tax_rate"], 0.0)
        self.assertEqual(a["tax_schedule"]["2026Q3"], 0.0)
        self.assertAlmostEqual(a["tax_schedule"]["2027Q1"], M.TAX_DEFAULT / 8, places=4)
        self.assertEqual(a["tax_schedule"]["2028Q4"], M.TAX_DEFAULT)
        self.assertEqual(rm["법인세비용"]["q"]["2026Q3"]["v"], 0.0)
        self.assertAlmostEqual(rm["법인세비용"]["q"]["2028Q4"]["v"], rm["세전이익"]["q"]["2028Q4"]["v"] * M.TAX_DEFAULT, places=1)
        self.assertAlmostEqual(a["tax_carryforward"]["median_pos8"], -0.3, places=4)

    def test_d2_carryforward_schedule_deterministic(self):
        m1, m2 = self._build(synth_fin(tax=0.01)), self._build(synth_fin(tax=0.01))
        self.assertEqual(json.dumps(m1, ensure_ascii=False, sort_keys=True), json.dumps(m2, ensure_ascii=False, sort_keys=True))
        self.assertEqual(list(m1["assumptions"]["tax_schedule"]), self.FQ)                         # 삽입 순서 = 추정 분기 순

    def test_d2_carryforward_adjusted_eps_uses_low_rate(self):
        # 일회성 분기(2026Q2 비영업 +2,000억, 그 분기 세율 ~82% → 0~35% 밖) → 조정EPS 의 '모델 세율' 폴백 = low 1%(22% 아님)
        fin = _spike_quarter(synth_fin(tax=0.01), "2026Q2", 200_000.0, tax=0.9)
        m = self._build(fin)
        a = m["assumptions"]
        self.assertEqual(a["tax_path"], M.TAX_CF_PATH)                                              # 8분기 중 7분기 1% → 중위·최근 4분기 중위 1%
        o = a["one_offs_detected"][0]
        self.assertEqual(o["q"], "2026Q2")
        self.assertIn("모델 세율", o["tax_rate_source"])
        self.assertEqual(o["tax_rate_applied"], a["tax_rate"])
        self.assertAlmostEqual(o["tax_rate_applied"], 0.01, places=4)

    def test_d2_carryforward_hold_only_when_no_ramp_quarters(self):
        qs = M.q_range("2024Q3", "2026Q2")
        pretax, tax = {q: 100.0 for q in qs}, {q: 1.0 for q in qs}
        cf = M._tax_carryforward(pretax, tax, ["2026Q3", "2026Q4"], "2026Q2")                   # 추정 분기가 origin 회계연도 안에서 끝남 → 램프 없음, 전부 low
        self.assertEqual(cf["schedule"], {"2026Q3": 0.01, "2026Q4": 0.01})
        self.assertEqual((cf["hold_until"], cf["ramp_from"], cf["ramp_to"]), ("2026Q4", None, None))
        self.assertIn("램프 분기 없음", cf["basis"])
        cf2 = M._tax_carryforward(pretax, tax, M.q_range("2027Q1", "2028Q4"), "2026Q4")         # origin 이 Q4 → 유지 분기 없음, 첫 추정 분기부터 램프
        self.assertEqual((cf2["hold_until"], cf2["ramp_from"], cf2["ramp_to"]), (None, "2027Q1", "2028Q4"))
        self.assertAlmostEqual(cf2["schedule"]["2027Q1"], 0.01 + 0.21 / 8, places=6)
        self.assertEqual(cf2["stage"]["2027Q1"], "램프 1/8")
        self.assertIn("바로 시작", cf2["basis"])
        # 감지 경계: 중위 5% 는 '미만' 이 아니다 · 세전 > 0 분기 3개면 None · 최근 4분기만 22% 면 None
        self.assertIsNone(M._tax_carryforward(pretax, {q: 5.0 for q in qs}, ["2026Q3"], "2026Q2"))
        self.assertIsNone(M._tax_carryforward({q: 100.0 for q in qs[-3:]}, tax, ["2026Q3"], "2026Q2"))
        self.assertIsNone(M._tax_carryforward(pretax, dict(tax, **{q: 22.0 for q in qs[-4:]}), ["2026Q3"], "2026Q2"))


class TestR7NewOrders(SyntheticAssets, unittest.TestCase):
    """라운드 7 L1(2026-10-08 오너 결정) — ⓐ NEW_ORDERS_POST_ORIGIN_MODE net_panel(공시 SLS 유지 + 패널 코호트 상계, 역산 커널 재합성) ·
    ⓑ 폴백 사슬 3단 ledger_signing_rate(패널 ÷ 원장 체결 < 0.5 · 창 ≥ 2분기 → 원장 min/median/max 수준 × 패널 커널).
    synth_panel: new_orders 50,000 → N 500억, base rev(h) = 2h억 → k(lag) = 0.004 상수(lag 0..9; 보수 0.002 · 낙관 0.006). synth_sls_post: c3 1,680억 2026Q3 체결."""
    FQ = M.q_range("2026Q3", "2028Q4")

    def _yard(self, sls, panel=None):
        fin = synth_fin("010140", "삼성", quarters=M.q_range("2023Q1", "2026Q2"), rev0=200_000.0, g_q=0.0)
        ctx = FakeCtx(fins={"010140": fin}, slss={"010140": sls}, roles={"010140": "yard"})
        if panel:
            ctx.panel = {"010140": panel}
        return M.build_model("010140", ctx)

    def _assert_monotone(self, m):
        sc = m["scenarios"]
        for q in self.FQ:
            c, b, o = (sc[k]["quarterly"][q]["rev"] for k in ("conservative", "base", "optimistic"))
            self.assertLessEqual(c, b + 1e-9, q)
            self.assertLessEqual(b, o + 1e-9, q)
            self.assertLessEqual(sc["existing_only"]["quarterly"][q]["rev"], b + 1e-9, q)

    def test_panel_kernel_backsolve(self):
        co = M._panel_kernel(synth_panel(), self.FQ, "new_order_revenue")
        b = co["base"]
        self.assertEqual((b["kernel"], b["N_by_q"]["2026Q3"], sorted(b["k"])), ("backsolved", 500.0, list(range(0, 10))))
        for lag in range(0, 10):
            self.assertAlmostEqual(b["k"][lag], 0.004, places=12, msg=lag)
            self.assertAlmostEqual(co["conservative"]["k"][lag], 0.002, places=12)
            self.assertAlmostEqual(co["optimistic"]["k"][lag], 0.006, places=12)
        for h in range(1, 11):
            self.assertAlmostEqual(b["K"][h], 0.004 * h, places=12)
        flow = M._flow_from_cohorts(b, self.FQ)                                      # 상계 없음 → 재합성 = 패널 원값
        for i, q in enumerate(self.FQ):
            self.assertAlmostEqual(flow[q], 2.0 * (i + 1), places=9, msg=q)
        netted = M._flow_from_cohorts(b, self.FQ, disclosed={"2026Q3": 1680.0})      # 첫 코호트 전부 상계 → 2(h−1)
        for i, q in enumerate(self.FQ):
            self.assertAlmostEqual(netted[q], 2.0 * i, places=9, msg=q)
        # new_orders 가 분기마다 다르면 역산 불가 → aggregate_ratio(k None), 상계는 rev_raw × Σnet/ΣN
        p = synth_panel()
        p["scenarios"]["base"]["quarterly"][3]["new_orders"] = 60_000.0
        co2 = M._panel_kernel(p, self.FQ, "new_order_revenue")
        self.assertEqual((co2["base"]["kernel"], co2["base"]["k"], co2["optimistic"]["kernel"]), ("aggregate_ratio", None, "backsolved"))
        f2 = M._flow_from_cohorts(co2["base"], self.FQ, disclosed={"2026Q3": 250.0})
        self.assertAlmostEqual(f2["2026Q3"], 2.0 * 250 / 500, places=9)
        self.assertAlmostEqual(f2["2026Q4"], 4.0 * 750 / 1000, places=9)
        self.assertAlmostEqual(M._flow_from_cohorts(co2["base"], self.FQ)["2027Q1"], 6.0, places=9)

    def test_net_panel_default_keeps_sls_nets_panel(self):
        """기본 모드: 공시 c3 는 SLS 로 유지(ref = 패널 없는 모델과 같은 SLS), 패널 2026Q3 코호트는 공시 1,680억에 전부 상계(net 0) → 신규 = 2(h−1)."""
        self.assertEqual(M.NEW_ORDERS_POST_ORIGIN_MODE, "net_panel")
        ref = self._yard(synth_sls_post())
        m = self._yard(synth_sls_post(), synth_panel())
        rr, rm, d = rows_of(ref), rows_of(m), m["segments"][0]["driver"]
        for i, q in enumerate(self.FQ):
            self.assertAlmostEqual(rm["매출조선"]["q"][q]["v"] - rr["매출조선"]["q"][q]["v"], rm["매출조선신규"]["q"][q]["v"], places=1, msg=q)   # SLS 280억 유지
            self.assertAlmostEqual(rm["매출조선신규"]["q"][q]["v"], 2.0 * i, places=2, msg=q)
            self.assertAlmostEqual(m["scenarios"]["conservative"]["quarterly"][q]["new_order_revenue"], 1.0 * i, places=2)
            self.assertAlmostEqual(m["scenarios"]["optimistic"]["quarterly"][q]["new_order_revenue"], 3.0 * i, places=2)
            self.assertIn("SLS 280억 유지" if q <= "2027Q4" else "SLS 0억 유지", rm["매출조선"]["q"][q]["basis"])
        px = d["post_origin_excluded"]
        self.assertEqual((px["mode"], px["included_fraction"], px["n"], px["amt_krw_eok"]), ("net_panel", 0.0, 1, 1680.0))
        self.assertEqual(px["netted_by_sign_quarter"]["2026Q3"], {"panel_new_orders": 500.0, "source": "panel", "panel_raw_new_orders": 500.0, "disclosed": 1680.0,
                                                                  "disclosed_in_scope": 1680.0, "disclosed_out_of_scope": 0.0, "net": 0.0})
        self.assertEqual((px["by_sign_quarter_out_of_scope"], px["scope_excluded_types"]), ({}, []))   # 전범위 패널 — 범위 밖 선종 없음
        self.assertEqual(px["sls_excluded_by_fy"], {"2026": 0.0, "2027": 0.0, "2028": 0.0})
        self.assertEqual(px["sls_kept_by_fy"], {"2026": 560.0, "2027": 1120.0, "2028": 0.0})
        self.assertEqual(px["panel_revenue_removed_by_fy"], {"2026": 4.0, "2027": 8.0, "2028": 8.0})         # 500 × 0.004 × 분기 수
        self.assertEqual(px["undated_not_netted_eok"], 0.0)
        self.assertIn("SLS 일정으로 전부 유지", px["note"])
        self.assertIn("2026Q3 패널 500억 − 공시 1,680억 = 0억", px["note"])
        self.assertIn("SLS 유지 — 패널 신규수주와 체결 분기별 상계(net_panel)", d["sls_source"])
        self.assertIn("상계(net_panel: 2026Q3 패널 500억 − 공시 1,680억 = 0억)", rm["매출조선신규"]["q"]["2027Q1"]["basis"])
        meta = m["scenarios"]["meta"]
        self.assertEqual((meta["post_origin_mode"], meta["kernel_mode"], meta["source_chain"]), ("net_panel", "backsolved", list(M.NEW_ORDERS_SOURCE_CHAIN)))
        self.assertIn("origin 이후 공시 수주 1건 전부, SLS 일정", meta["existing_revenue"])
        self.assertIn("공시 수주 1건 전부(SLS 일정)", d["new_orders"]["existing_definition"])
        for y in ("2026", "2027", "2028"):                                                                   # existing_only = 패널 없는 모델(c3 포함)
            self.assertAlmostEqual(m["scenarios"]["existing_only"]["annual"][y]["rev"], rr["매출액"]["a"][y]["v"], places=1)
        self.assertEqual(rm["매출조선신규"]["label"], "매출 조선·해양(조선해양) 신규수주(forecast_panel base(공시 상계) — 매출조선에 포함)")
        pm = next(mod for mod in m["modules"] if mod["key"] == "forecast_panel")
        self.assertTrue(any("상계 전 패널 원값" in r["label"] for r in pm["rows"] if r["key"] == "panel_new_order_revenue"))
        self.assertEqual(M.summary_row(m)["post_origin_mode"], "net_panel")
        self._assert_monotone(m)
        # 공시 없는 선표에서는 상계도 없고 라벨은 라운드 6 그대로
        m0 = self._yard(synth_sls(), synth_panel())
        self.assertIsNone(m0["segments"][0]["driver"]["post_origin_excluded"])
        self.assertTrue(any("반영됨" in r["label"] for r in next(mod for mod in m0["modules"] if mod["key"] == "forecast_panel")["rows"]))

    def test_net_panel_partial_netting(self):
        """패널 N 5,000억 > 공시 1,680억 → net 3,320, k = 0.0004 → 신규(h) = 2h − 1,680 × 0.0004 = 2h − 0.672 (FY2027 = 36 − 2.688)."""
        m = self._yard(synth_sls_post(), synth_panel(new_orders=500_000.0))
        rm, px = rows_of(m), m["segments"][0]["driver"]["post_origin_excluded"]
        self.assertEqual(px["netted_by_sign_quarter"]["2026Q3"], {"panel_new_orders": 5000.0, "source": "panel", "panel_raw_new_orders": 5000.0, "disclosed": 1680.0,
                                                                  "disclosed_in_scope": 1680.0, "disclosed_out_of_scope": 0.0, "net": 3320.0})
        for i, q in enumerate(self.FQ):
            self.assertAlmostEqual(rm["매출조선신규"]["q"][q]["v"], 2.0 * (i + 1) - 0.672, places=2, msg=q)
        self.assertAlmostEqual(rm["매출조선신규"]["a"]["2027"]["v"], 33.312, delta=0.03)
        self.assertAlmostEqual(px["panel_revenue_removed_by_fy"]["2027"], 2.688, places=2)
        self._assert_monotone(m)

    def test_mode_switch_validation(self):
        with _mode("bogus"), self.assertRaises(ValueError):
            self._yard(synth_sls_post(), synth_panel())
        self.assertEqual(M.NEW_ORDERS_POST_ORIGIN_MODES, ("net_panel", "exclude_sls"))
        with _mode("exclude_sls"):                                     # 라운드 6 재현: post_frac 1, 공시 SLS 제외
            m = self._yard(synth_sls_post(), synth_panel(new_orders=500_000.0))
            px = m["segments"][0]["driver"]["post_origin_excluded"]
            self.assertEqual((px["mode"], px["included_fraction"]), ("exclude_sls", 1.0))
            self.assertEqual(m["scenarios"]["meta"]["post_origin_mode"], "exclude_sls")
            self.assertIn("기존 SLS 에서 제외", px["note"])

    def test_ledger_signing_rate_switch(self):
        """패널 N 100억 vs 원장 평균 2,375억(ratio 0.042) · 창 4분기 → 원장 min/median/max(2,000/2,250/3,000) × 패널 커널(k 0.01/0.02/0.03)."""
        import kship_model_section as SEC
        m = self._yard(synth_sls_ledger(), synth_panel(rev_field="covered_scope_new_revenue", new_orders=10_000.0))
        rm, d = rows_of(m), m["segments"][0]["driver"]
        no = d["new_orders"]
        self.assertEqual((no["source_field"], no["panel_field"], no["fallback"], no["confidence"]), ("ledger_signing_rate", "covered_scope_new_revenue", True, "low"))
        self.assertAlmostEqual(no["ledger_crosscheck"]["panel_to_ledger_ratio"], 100.0 / 2375.0, places=4)
        lr = no["ledger_rate"]
        self.assertEqual(lr["levels"], {"conservative": 2000.0, "base": 2250.0, "optimistic": 3000.0})
        self.assertEqual((lr["panel_fallback_base_per_q_eok"], lr["n_quarters_used"], lr["curve"], lr["kernel_mode"]), (100.0, 4, "panel_kernel", "backsolved"))
        self.assertEqual(lr["window_quarters"], M.q_range("2025Q3", "2026Q2"))
        for i, q in enumerate(self.FQ):
            h = i + 1
            self.assertAlmostEqual(rm["매출조선신규"]["q"][q]["v"], 2250 * 0.02 * h, places=2, msg=q)
            self.assertAlmostEqual(m["scenarios"]["conservative"]["quarterly"][q]["new_order_revenue"], 2000 * 0.01 * h, places=2)
            self.assertAlmostEqual(m["scenarios"]["optimistic"]["quarterly"][q]["new_order_revenue"], 3000 * 0.03 * h, places=2)
        # 선형 대안(감도 기록): T = 원장 계약 일정 길이 중위 round(9.5) = 10 → base 225(h−1) → FY 225 · 3,150 · 6,750
        self.assertEqual(lr["alt_linear_T"], 10)
        self.assertEqual(lr["alt_linear_FY_rev"], {"2026": 225.0, "2027": 3150.0, "2028": 6750.0})
        self.assertEqual(lr["alt_linear_FY_rev_pre_netting"], lr["alt_linear_FY_rev"])                  # 공시 없음 → 상계 전후 같은 축
        self.assertEqual(sorted(lr["alt_linear_k"]), list(range(1, 11)))
        self.assertEqual((lr["n_quarters_positive"], lr["panel_floor_applied"], lr["levels_ledger_raw"]), (4, [], lr["levels"]))
        self.assertNotIn("(공시 상계 후", no["fallback_note"])
        self.assertIn("폴백 사슬 new_order_revenue → covered_scope_new_revenue → ledger_signing_rate", no["fallback_note"])
        self.assertIn("4% < 50%", no["fallback_note"])
        self.assertIn("2,000/2,250/3,000억", no["fallback_note"])
        self.assertIn("ledger_signing_rate", rm["매출조선신규"]["q"]["2027Q1"]["basis"])
        self.assertEqual(rm["매출조선신규"]["label"], "매출 조선·해양(조선해양) 신규수주(원장 체결 속도(폴백) — 매출조선에 포함)")
        self.assertTrue(any(w.startswith("신규수주 ledger_signing_rate(저신뢰)") and "표본 4분기" in w for w in m["quality"]["warnings"]))
        meta = m["scenarios"]["meta"]
        self.assertEqual((meta["source_field"], meta["fallback"], meta["confidence"], meta["ledger_rate"]["levels"]["base"]), ("ledger_signing_rate", True, "low", 2250.0))
        self.assertIn("공시 계약 원장", meta["source"])
        pm = next(mod for mod in m["modules"] if mod["key"] == "forecast_panel")
        row = next(r for r in pm["rows"] if r["key"] == "panel_new_order_revenue")
        self.assertIn("원장 체결 속도로 대체됨", row["label"])
        self.assertAlmostEqual(row["q"]["2026Q3"]["v"], 2.0, places=6)                 # 패널 원값(covered_scope) 그대로 보인다
        self.assertEqual(M.summary_row(m)["new_orders_source"], "ledger_signing_rate")
        self.assertTrue(m["quality"]["identities_ok"], m["quality"]["identity_mismatches"])
        self._assert_monotone(m)
        # 섹션 라벨(kship_model_section.new_orders_state) — 원장 폴백 라벨 + 비율
        st, lab, det = SEC.new_orders_state(m)
        self.assertEqual((st, lab), ("included", SEC.NEW_ORDERS_LEDGER_LABEL))
        self.assertIn("폴백 ledger_signing_rate(패널 신규수주가 공시 체결 속도의 4% · 원장 표본 4분기)", det)
        self.assertNotEqual(SEC.NEW_ORDERS_LEDGER_LABEL, SEC.NEW_ORDERS_FALLBACK_LABEL)

    def test_ledger_rate_not_switched(self):
        # (i) 비율 ≥ 0.5(N 3,000 vs 2,375 → 1.26) → covered_scope 유지
        m = self._yard(synth_sls_ledger(), synth_panel(rev_field="covered_scope_new_revenue", new_orders=300_000.0))
        no = m["segments"][0]["driver"]["new_orders"]
        self.assertEqual((no["source_field"], no["ledger_rate"]), ("covered_scope_new_revenue", None))
        self.assertAlmostEqual(no["ledger_crosscheck"]["panel_to_ledger_ratio"], 3000.0 / 2375.0, places=4)
        # (ii) 원장 창 1분기 → LEDGER_RATE_MIN_QUARTERS 미달(헬퍼 직접)
        ctx = FakeCtx()
        ctx.panel = {"010140": synth_panel(rev_field="covered_scope_new_revenue", new_orders=10_000.0)}
        sls = synth_sls_ledger()
        no2 = M._panel_new_orders("010140", ctx, self.FQ)
        cc = M._ledger_signing_crosscheck(sls, no2)
        self.assertEqual((cc["n_quarters_used"], cc["n_quarters_positive"]), (4, 4))
        cc1 = dict(cc, n_quarters_positive=1)                                 # 게이트는 체결 > 0 분기 수(2026-10-09)
        no2 = M._ledger_rate_new_orders(no2, cc1, self.FQ, sls)
        self.assertEqual((no2["source_field"], no2["ledger_rate"]), ("covered_scope_new_revenue", None))
        self.assertEqual(no2["by_scenario"]["base"]["2026Q4"], 4.0)
        # (iii) FALLBACK_ONLY=True: 전범위 new_order_revenue 회사는 비율 0.04(원장 창 4분기 체결 > 0) 라도 유지(대조도 안 함); False 면 전환
        m3 = self._yard(synth_sls_ledger(), synth_panel(new_orders=10_000.0))
        no3 = m3["segments"][0]["driver"]["new_orders"]
        self.assertEqual((no3["source_field"], no3["fallback"], no3["ledger_crosscheck"], no3["ledger_rate"]), ("new_order_revenue", False, None, None))
        with mock.patch.object(M, "LEDGER_RATE_FALLBACK_ONLY", False):
            m4 = self._yard(synth_sls_ledger(), synth_panel(new_orders=10_000.0))
            no4 = m4["segments"][0]["driver"]["new_orders"]
            self.assertEqual((no4["source_field"], no4["panel_field"], no4["ledger_rate"]["fallback_only"]), ("ledger_signing_rate", "new_order_revenue", False))
            self.assertAlmostEqual(no4["ledger_crosscheck"]["panel_to_ledger_ratio"], 100.0 / 2375.0, places=4)
            self.assertEqual(no4["ledger_rate"]["panel_floor_applied"], [])                 # 패널 N 100 < 원장 min 2,000 — 하한 미발동

    def test_ledger_rate_with_net_panel(self):
        """원장 수준 2,250 과 공시 c3 1,680억(2026Q3) 상계 → net 570; 신규 base(h) = 0.02 × (570 + 2,250 × (h−1)). exclude_sls 스위치에선 post_frac min(1, 2,250/1,680) = 1."""
        m = self._yard(synth_sls_ledger(base=synth_sls_post()), synth_panel(rev_field="covered_scope_new_revenue", new_orders=10_000.0))
        rm, px = rows_of(m), m["segments"][0]["driver"]["post_origin_excluded"]
        no = m["segments"][0]["driver"]["new_orders"]
        self.assertEqual(no["source_field"], "ledger_signing_rate")
        self.assertEqual(px["netted_by_sign_quarter"]["2026Q3"], {"panel_new_orders": 2250.0, "source": "ledger", "panel_raw_new_orders": 100.0, "disclosed": 1680.0,
                                                                  "disclosed_in_scope": 1680.0, "disclosed_out_of_scope": 0.0, "net": 570.0})
        # ledger 모드 문구(2026-10-09): 코호트 N 은 원장 수준이고 패널 원값(100억)을 괄호로 — '패널 2,250억' 이라고 적지 않는다
        self.assertIn("2026Q3 원장 수준 2,250억(패널 100억) − 공시 1,680억 = 570억", px["note"])
        self.assertIn("원장 수준 신규수주에서 체결 분기별 상계", px["note"])
        self.assertIn("— 매출조선신규(원장 수준) −", px["note"])
        self.assertNotIn("패널 2,250억", px["note"] + px["definition_uncertainty"])
        self.assertIn("공시 수주 1,680억 vs 원장 수준 base 신규수주 2,250억(75%)", px["definition_uncertainty"])
        self.assertIn("FY 유지 SLS(공시) vs 매출조선신규(원장 수준)(상계 후)", px["definition_uncertainty"])
        self.assertIn("원장 수준 신규수주와 체결 분기별 상계(net_panel)", m["segments"][0]["driver"]["sls_source"])
        self.assertEqual(no["net_panel"]["source"], "ledger")
        # 선형 대안은 행과 같은 축(상계 후)으로 다시 재고 상계 전은 따로: T = median(10, 9, 6) = 9, 2026Q3 코호트 570 → 63.33/분기, 그 외 250/분기
        lr = no["ledger_rate"]
        self.assertEqual(lr["alt_linear_T"], 9)
        self.assertEqual(lr["alt_linear_FY_rev_pre_netting"], {"2026": 250.0, "2027": 3500.0, "2028": 7500.0})
        self.assertEqual(lr["alt_linear_FY_rev"], {"2026": 63.33, "2027": 2753.33, "2028": 6753.33})
        self.assertIn("base FY 매출 2026 63억 · 2027 2,753억 · 2028 6,753억(공시 상계 후 — 행과 같은 축; 상계 전 2026 250억 · 2027 3,500억 · 2028 7,500억)", no["fallback_note"])
        for i, q in enumerate(self.FQ):
            self.assertAlmostEqual(rm["매출조선신규"]["q"][q]["v"], 0.02 * (570 + 2250 * i), places=2, msg=q)
            self.assertAlmostEqual(m["scenarios"]["conservative"]["quarterly"][q]["new_order_revenue"], 0.01 * (320 + 2000 * i), places=2)
            self.assertAlmostEqual(m["scenarios"]["optimistic"]["quarterly"][q]["new_order_revenue"], 0.03 * (1320 + 3000 * i), places=2)
        self._assert_monotone(m)
        with _mode("exclude_sls"):
            m2 = self._yard(synth_sls_ledger(base=synth_sls_post()), synth_panel(rev_field="covered_scope_new_revenue", new_orders=10_000.0))
            px2 = m2["segments"][0]["driver"]["post_origin_excluded"]
            self.assertEqual((px2["mode"], px2["included_fraction"]), ("exclude_sls", 1.0))
            self.assertEqual(m2["segments"][0]["driver"]["new_orders"]["source_field"], "ledger_signing_rate")
            for i, q in enumerate(self.FQ):                                        # 상계 없음: 2,250 × 0.02 × h
                self.assertAlmostEqual(rows_of(m2)["매출조선신규"]["q"][q]["v"], 45.0 * (i + 1), places=2, msg=q)

    def test_ledger_rate_exclude_sls_wording(self):
        """2026-10-09: exclude_sls 스위치 + ledger 모드 — 원장 창 [2,000·1,000·1,200·1,500] → median 1,350 < 공시 1,680 → post_frac 1,350/1,680 = 0.8036.
        exclude_sls 문구(note·sls_source·existing_definition·셀 basis)도 코호트 N 출처를 따라 '원장 수준' 으로 적고 '패널 … 규모' 라고 적지 않는다; 패널 모드는 현행 '패널'."""
        amts = {"2025Q4": 100_000.0, "2026Q1": 120_000.0, "2026Q2": 150_000.0}
        with _mode("exclude_sls"):
            m = self._yard(synth_sls_ledger(amts=amts, base=synth_sls_post()), synth_panel(rev_field="covered_scope_new_revenue", new_orders=10_000.0))
            m_panel = self._yard(synth_sls_post(), synth_panel(new_orders=50_000.0))                      # 패널 500억 vs 공시 1,680억 → 30%
        rm, d = rows_of(m), m["segments"][0]["driver"]
        no, px = d["new_orders"], d["post_origin_excluded"]
        self.assertEqual((no["source_field"], no["ledger_rate"]["levels"], no["ledger_rate"]["panel_floor_applied"]),
                         ("ledger_signing_rate", {"conservative": 1000.0, "base": 1350.0, "optimistic": 2000.0}, []))
        self.assertAlmostEqual(no["ledger_crosscheck"]["panel_to_ledger_ratio"], 100.0 / 1425.0, places=4)
        self.assertEqual((px["mode"], px["included_fraction"], px["included_fraction_by_sign_quarter"]), ("exclude_sls", 0.8036, {"2026Q3": 0.8036}))
        self.assertIn("1건 1,680억 중 원장 수준 신규수주 규모(체결 분기별 한도)만큼 80% 만 기존 SLS 에서 제외 — 나머지 20% 는 선표에 유지"
                      "(원장 수준이 공시 체결 속도보다 작음: 2026Q3 원장 수준 1,350억 vs 공시 1,680억)", px["note"])
        self.assertIn("중 원장 수준 신규수주 규모만큼(80%) 제외 — 원장 수준 신규에 포함", d["sls_source"])
        self.assertIn("1건 중 원장 수준 신규수주 규모를 넘는 20%", no["existing_definition"])
        self.assertIn("80% 제외(원장 수준 신규수주 규모만큼)", m["scenarios"]["meta"]["existing_revenue"])
        self.assertIn("SLS 280억 중 225억 제외(원장 수준 신규수주 규모만큼, 80%)", rm["매출조선"]["q"]["2026Q4"]["basis"])
        self.assertNotIn("패널 신규수주 규모", px["note"] + d["sls_source"] + no["existing_definition"] + m["scenarios"]["meta"]["existing_revenue"])
        self.assertEqual(px["sls_excluded_by_fy"], {"2026": 450.0, "2027": 900.0, "2028": 0.0})            # 280 × 0.8036 × 분기 수
        self.assertAlmostEqual(rm["매출조선신규"]["q"]["2026Q4"]["v"], 1350 * 0.02 * 2, places=6)              # 상계 없음: 원장 수준 × k × h
        # 패널 모드 exclude_sls 문구는 현행 그대로
        px_p = m_panel["segments"][0]["driver"]["post_origin_excluded"]
        self.assertIn("중 패널 신규수주 규모(체결 분기별 한도)만큼 30% 만 기존 SLS 에서 제외", px_p["note"])
        self.assertIn("(패널이 공시 체결 속도보다 작음: 2026Q3 패널 500억 vs 공시 1,680억)", px_p["note"])
        self.assertIn("중 패널 신규수주 규모만큼(30%) 제외 — 패널 신규에 포함", m_panel["segments"][0]["driver"]["sls_source"])

    def test_panel_kernel_horizon_gap_falls_to_aggregate_ratio(self):
        """2026-10-09: 역산 항등식은 horizon 1..H 연속·전 horizon 매출 행이 있을 때만 — 내부 분기 1행 제거 → aggregate_ratio, 상계 없으면 재합성 == 패널 원값."""
        p = synth_panel()
        for scn in M.PANEL_SCENARIOS:
            del p["scenarios"][scn]["quarterly"][3]                                    # 2027Q2 행 제거(나머지 horizon 라벨 유지 → 1,2,3,5,…)
        co = M._panel_kernel(p, self.FQ, "new_order_revenue")
        b = co["base"]
        self.assertEqual((b["kernel"], b["k"], b["K"], b["contiguous"], b["gap"]), ("aggregate_ratio", None, None, False, ["2027Q2"]))
        self.assertNotIn("2027Q2", b["horizon"])
        flow = M._flow_from_cohorts(b, self.FQ)
        for i, q in enumerate(self.FQ):
            self.assertAlmostEqual(flow[q], 0.0 if q == "2027Q2" else 2.0 * (i + 1), places=9, msg=q)   # 재합성 == 패널 원값(미커버 분기 0)
        # horizon 오프셋(2..H+1) · 매출 행 결손(new_order_revenue None) 도 역산 불가 — 결손은 gap 에 분기로
        p2 = synth_panel()
        for r in p2["scenarios"]["base"]["quarterly"]:
            r["horizon"] += 1
        b2 = M._panel_kernel(p2, self.FQ, "new_order_revenue")["base"]
        self.assertEqual((b2["kernel"], b2["contiguous"], b2["gap"]), ("aggregate_ratio", False, []))
        p3 = synth_panel()
        p3["scenarios"]["base"]["quarterly"][5]["new_order_revenue"] = None
        b3 = M._panel_kernel(p3, self.FQ, "new_order_revenue")["base"]
        self.assertEqual((b3["kernel"], b3["gap"]), ("aggregate_ratio", ["2027Q4"]))
        self.assertEqual(M._panel_kernel(synth_panel(), self.FQ, "new_order_revenue")["base"]["contiguous"], True)
        # 빌드: net_panel 경고 채널에 결손 분기 — 상계는 집계 비율 근사(2026Q3 코호트 500 전부 상계 → 2026Q3 0, 2026Q4 4 × 500/1000)
        m = self._yard(synth_sls_post(), p)
        rm = rows_of(m)
        self.assertEqual(m["segments"][0]["driver"]["new_orders"]["kernel_mode"], "aggregate_ratio")
        self.assertTrue(any(w == "net_panel: 패널 horizon 결손 2027Q2 — 커널 역산 불가, 집계 비율 근사(kernel aggregate_ratio, 정확도 하락)" for w in m["quality"]["warnings"]),
                        m["quality"]["warnings"])
        self.assertFalse(any("상수가 아니라" in w for w in m["quality"]["warnings"]))
        self.assertEqual((rm["매출조선신규"]["q"]["2026Q3"]["v"], rm["매출조선신규"]["q"]["2026Q4"]["v"], rm["매출조선신규"]["q"]["2027Q2"]["v"]), (0.0, 2.0, 0.0))

    def test_ledger_rate_positive_quarters_and_panel_floor(self):
        """2026-10-09: 창 [2,000 · 50 · 0 · 3,000] — 수준 통계는 체결 > 0 인 3분기(min 50/median 2,000/max 3,000), 평균·비율은 창 전체(1,262.5),
        보수 50 은 패널 자체 N 100 을 하한으로 100. 체결 > 0 이 1분기면 LEDGER_RATE_MIN_QUARTERS 미달."""
        sls = synth_sls_ledger(amts={"2025Q4": 5_000.0, "2026Q2": 300_000.0})
        ctx = FakeCtx()
        ctx.panel = {"010140": synth_panel(rev_field="covered_scope_new_revenue", new_orders=10_000.0)}
        no = M._panel_new_orders("010140", ctx, self.FQ)
        cc = M._ledger_signing_crosscheck(sls, no)
        self.assertEqual(cc["quarters"], M.q_range("2025Q3", "2026Q2"))
        self.assertEqual((cc["n_quarters_used"], cc["n_quarters_positive"], cc["ledger_min_per_q_eok"], cc["ledger_mean_per_q_eok"]), (4, 3, 0.0, 1262.5))
        self.assertAlmostEqual(cc["panel_to_ledger_ratio"], 100.0 / 1262.5, places=4)
        no = M._ledger_rate_new_orders(no, cc, self.FQ, sls)
        lr = no["ledger_rate"]
        self.assertEqual(no["source_field"], "ledger_signing_rate")
        self.assertEqual(lr["levels_ledger_raw"], {"conservative": 50.0, "base": 2000.0, "optimistic": 3000.0})
        self.assertEqual(lr["levels"], {"conservative": 100.0, "base": 2000.0, "optimistic": 3000.0})
        self.assertEqual((lr["panel_floor_applied"], lr["panel_floor_per_q_eok"]["conservative"], lr["n_quarters_positive"]), (["conservative"], 100.0, 3))
        self.assertIn("수준 통계는 체결 > 0 인 3분기", lr["note"])
        self.assertIn("패널 자체 N 하한 적용 conservative 50→100억", lr["note"])
        self.assertIn("체결 > 0 인 3분기", no["basis"])
        self.assertAlmostEqual(no["by_scenario"]["conservative"]["2026Q4"], 100 * 0.01 * 2, places=9)          # 하한 100 × k_cons 0.01 × h
        self.assertAlmostEqual(no["by_scenario"]["base"]["2026Q4"], 2000 * 0.02 * 2, places=9)
        # 체결 > 0 이 1분기(synth_sls 2025Q3 2,000억만): 비율 0.2 < 0.5 라도 전환 안 함
        no1 = M._panel_new_orders("010140", ctx, self.FQ)
        cc1 = M._ledger_signing_crosscheck(synth_sls(), no1)
        self.assertEqual((cc1["n_quarters_used"], cc1["n_quarters_positive"]), (4, 1))
        self.assertEqual((M._ledger_rate_new_orders(no1, cc1, self.FQ, synth_sls())["source_field"], no1["ledger_rate"]), ("covered_scope_new_revenue", None))

    def test_scope_excluded_type_not_netted_for_fallback(self):
        """2026-10-09: covered_scope 폴백 회사(제외 부문 EP및특수선)의 NAVAL 공시는 패널 범위 밖 — 상계 D·원장 창에서 빼고 SLS 일정은 유지. OFFSH 는 상계에 두고 경고.
        패널 N 3,000(k 2/3,000) · 공시 2026Q3: LNGC 1,680 + NAVAL 1,000(제외) + OFFSH 300(불확실) → D 1,980, net 1,020 → 신규(h) = 2h − 1,980 × 2/3,000 = 2h − 1.32."""
        def _sls():
            s = synth_sls_ledger(base=synth_sls_post())
            add_post_contract(s, "n", "NAVAL", "2026-08-15", 100_000.0, M.q_range("2026Q4", "2027Q4"), 10.0)
            add_post_contract(s, "o", "OFFSH", "2026-09-10", 30_000.0, M.q_range("2026Q4", "2027Q1"), 5.0)
            s["contracts"].append({"rcp": "pn", "type": "NAVAL", "ships": 1, "amt_krw_m": 50_000.0, "amt_usd_m": 35.7, "signed": "2026-02-10", "start": "2026-02-10",
                                   "cohort": "③중마진", "counted": True, "signed_by_origin": True})       # origin 이전 NAVAL 500억 — 원장 창에서도 제외
            return s
        def _panel():
            p = synth_panel(rev_field="covered_scope_new_revenue", new_orders=300_000.0)
            p["coverage"]["excluded_segments"] = ["EP및특수선"]
            return p
        self.assertEqual(M._scope_excluded_types({"fallback": True, "coverage": {"excluded_segments": ["EP및특수선"]}}), (("NAVAL",), ("OFFSH",)))
        self.assertEqual(M._scope_excluded_types({"fallback": False, "coverage": {"excluded_segments": ["EP및특수선"]}}), ((), ()))
        self.assertEqual(M._scope_excluded_types({"fallback": True, "coverage": {"excluded_segments": ["수리"]}}), ((), ()))
        ref = self._yard(_sls())                                                       # 패널 없음 — SLS 전부(NAVAL 포함)
        m = self._yard(_sls(), _panel())
        rr, rm, d = rows_of(ref), rows_of(m), m["segments"][0]["driver"]
        no, px = d["new_orders"], d["post_origin_excluded"]
        self.assertEqual((no["source_field"], no["fallback"]), ("covered_scope_new_revenue", True))
        self.assertEqual((no["ledger_crosscheck"]["excluded_types"], no["ledger_crosscheck"]["excluded_signed_eok"]), (["NAVAL"], 500.0))
        self.assertAlmostEqual(no["ledger_crosscheck"]["panel_to_ledger_ratio"], 3000.0 / 2375.0, places=4)   # 창은 상선만(NAVAL 500 제외)
        self.assertEqual(px["netted_by_sign_quarter"]["2026Q3"], {"panel_new_orders": 3000.0, "source": "panel", "panel_raw_new_orders": 3000.0, "disclosed": 2980.0,
                                                                  "disclosed_in_scope": 1980.0, "disclosed_out_of_scope": 1000.0, "net": 1020.0})
        self.assertEqual((px["by_sign_quarter"], px["by_sign_quarter_out_of_scope"], px["scope_excluded_types"], px["n"], px["amt_krw_eok"]),
                         ({"2026Q3": 1980.0}, {"2026Q3": 1000.0}, ["NAVAL"], 3, 2980.0))
        self.assertEqual((no["net_panel"]["disclosed_out_of_scope_eok"], no["net_panel"]["scope_excluded_types"], px["undated_not_netted_eok"]), (1000.0, ["NAVAL"], 0.0))
        self.assertIn("2026Q3 패널 3,000억 − 공시 1,980억(범위 밖 1,000억 제외) = 1,020억", px["note"])
        self.assertIn("패널 범위 밖 NAVAL 1,000억은 상계 안 함", d["sls_source"])
        self.assertTrue(any(w.startswith("net_panel: 패널 범위 밖일 수 있는 type 상계 300억(과다 상계 가능) — OFFSH") for w in m["quality"]["warnings"]), m["quality"]["warnings"])
        for i, q in enumerate(self.FQ):
            self.assertAlmostEqual(rm["매출조선신규"]["q"][q]["v"], 2.0 * (i + 1) - 1.32, places=2, msg=q)
            self.assertAlmostEqual(rm["매출조선"]["q"][q]["v"] - rr["매출조선"]["q"][q]["v"], rm["매출조선신규"]["q"][q]["v"], places=1, msg=q)   # SLS(NAVAL 포함) 전부 유지
        self.assertEqual(px["sls_kept_by_fy"]["2027"], 1120.0 + 4 * 140.0 + 70.0)      # c3 + NAVAL 4분기 + OFFSH 2027Q1
        self._assert_monotone(m)
        # 전범위(new_order_revenue) 회사엔 제외 매핑이 없다 — NAVAL 도 상계
        m0 = self._yard(_sls(), synth_panel(new_orders=300_000.0))
        px0 = m0["segments"][0]["driver"]["post_origin_excluded"]
        self.assertEqual((px0["by_sign_quarter"], px0["by_sign_quarter_out_of_scope"], px0["netted_by_sign_quarter"]["2026Q3"]["net"]), ({"2026Q3": 2980.0}, {}, 20.0))
        # exclude_sls 스위치: 범위 밖 NAVAL 은 패널 신규에 없으니 SLS 에 유지(비율 0) → post_frac = 1,980/2,980
        with _mode("exclude_sls"):
            m2 = self._yard(_sls(), _panel())
            px2 = m2["segments"][0]["driver"]["post_origin_excluded"]
            self.assertEqual((px2["mode"], px2["included_fraction_by_sign_quarter"]), ("exclude_sls", {"2026Q3": 1.0}))
            self.assertAlmostEqual(px2["included_fraction"], 1980.0 / 2980.0, places=4)
            self.assertAlmostEqual(px2["sls_excluded_by_fy"]["2027"], (1120.0 + 560.0 + 70.0) * 1980.0 / 2980.0, places=1)


def _spike_quarter(fin, q, amt_m, tax=0.22, minority=0.1):
    """합성 fin 의 한 분기 기타영업외손익에 amt_m(백만원)을 더하고 세전→법인세→NI→지배/비지배 사슬을 같은 비율로 맞춘다(항등식 유지)."""
    for sc in ("cons", "sep"):
        r = fin[sc]["is"].get(q)
        if not r:
            continue
        r["기타영업외손익"] += amt_m
        r["법인세비용차감전계속사업이익"] += amt_m
        r["법인세비용"] += amt_m * tax
        ni = amt_m * (1 - tax)
        r["당기순이익"] += ni
        r["(지배주주지분)당기순이익"] += ni * (1 - minority)
        r["(비지배주주지분)당기순이익"] += ni * minority
    return fin


class TestV4Verifier(SyntheticAssets, unittest.TestCase):
    """V4(2026-10-05) 검증 레인 — 조정EPS 행 · 음수 부문 매출 제외 · FCF 근사 BS 롤 · status 사유 · 동결 누출 프로브."""

    QS = M.q_range("2023Q1", "2026Q2")

    def _equip(self, fin):
        return M.build_model(fin["stock"], FakeCtx(fins={fin["stock"]: fin}, roles={fin["stock"]: "equip"}))

    # ── 조정EPS: 일회성 의심 분기만 세후·지배 비중으로 차감, 다른 분기는 EPS 그대로, 의심 없는 회사는 행 없음 ──
    def test_adjusted_eps_row_only_for_one_off_companies(self):
        base = self._equip(synth_fin(quarters=self.QS))
        self.assertNotIn("조정EPS", rows_of(base))
        self.assertEqual(base["assumptions"]["one_offs_detected"], [])
        self.assertIsNone(M.summary_row(base)["fy"]["2026E"]["eps_adj"])
        self.assertEqual(M.summary_row(base)["one_offs_n"], 0)
        fin = _spike_quarter(synth_fin(quarters=self.QS), "2026Q2", 200_000.0)          # 비영업손익 +2,000억(영업이익 ~300억의 7배)
        m = self._equip(fin)
        rm = rows_of(m)
        offs = m["assumptions"]["one_offs_detected"]
        self.assertEqual([o["q"] for o in offs], ["2026Q2"])
        o = offs[0]
        q = "2026Q2"
        is_ = fin["cons"]["is"][q]
        nonop = (is_["법인세비용차감전계속사업이익"] - is_["영업이익"]) / 100
        self.assertAlmostEqual(o["nonop"], nonop, places=1)
        self.assertAlmostEqual(o["baseline_nonop_12q"], -4.0, places=2)                   # 다른 분기 비영업손익 = −500 + 100 = −400 백만원
        self.assertAlmostEqual(o["excess_nonop"], nonop + 4.0, places=1)
        self.assertAlmostEqual(o["tax_rate_applied"], 0.22, places=3)                      # 분기 유효세율 = 합성 22%
        self.assertIn("분기 유효세율", o["tax_rate_source"])
        self.assertAlmostEqual(o["ctrl_share_applied"], 0.9, places=3)                     # 그 분기 지배NI/NI
        ctrl = is_["(지배주주지분)당기순이익"] / 100
        ctrl_adj = ctrl - (nonop + 4.0) * 0.78 * 0.9
        self.assertAlmostEqual(o["ni_ctrl_adj"], ctrl_adj, places=1)
        eps_adj = round(ctrl_adj * 1e8 / SHARES, 1)
        self.assertAlmostEqual(o["eps_adj"], eps_adj, places=0)
        self.assertEqual(rm["조정EPS"]["q"][q]["kind"], "estimate")
        self.assertAlmostEqual(rm["조정EPS"]["q"][q]["v"], eps_adj, places=0)
        self.assertIn("12분기 기준선", rm["조정EPS"]["q"][q]["basis"])
        self.assertLess(rm["조정EPS"]["q"][q]["v"], rm["EPS"]["q"][q]["v"] * 0.5)
        self.assertEqual(rm["EPS"]["q"][q]["v"], o["eps_reported"])                        # 보고 EPS 행은 불변
        for k in ("2026Q1", "2025Q4"):                                                     # 다른 실적 분기 = EPS, actual
            self.assertEqual((rm["조정EPS"]["q"][k]["v"], rm["조정EPS"]["q"][k]["kind"]), (rm["EPS"]["q"][k]["v"], "actual"))
        for k in ("2026Q3", "2027Q4"):                                                     # 추정 구간 = EPS 복사
            self.assertEqual((rm["조정EPS"]["q"][k]["v"], rm["조정EPS"]["q"][k]["kind"]), (rm["EPS"]["q"][k]["v"], "estimate"))
        self.assertEqual(rm["조정EPS"]["a"]["2026"]["kind"], "mixed")
        self.assertAlmostEqual(rm["조정EPS"]["a"]["2026"]["v"], rm["EPS"]["a"]["2026"]["v"] - rm["EPS"]["q"][q]["v"] + eps_adj, places=0)
        sr = M.summary_row(m)
        self.assertAlmostEqual(sr["fy"]["2026E"]["eps_adj"], rm["조정EPS"]["a"]["2026"]["v"], places=1)
        self.assertEqual(sr["one_offs_n"], 1)
        self.assertTrue(any("조정EPS" in w and "보고 EPS" in w for w in m["quality"]["warnings"]))
        self.assertIn("조정EPS", [r[0] for r in m["views"]["보고서로"]])
        self.assertTrue(m["quality"]["identities_ok"], m["quality"]["identity_mismatches"])
        # 분기 유효세율이 범위 밖(세전 ≤ 0)이면 모델 세율로
        fin2 = _spike_quarter(synth_fin(quarters=self.QS), "2026Q2", 200_000.0)
        for sc in ("cons", "sep"):
            r = fin2[sc]["is"]["2026Q2"]
            r["법인세비용"] = -r["법인세비용"]                                                 # 법인세 환입 → 유효세율 음수
        m2 = self._equip(fin2)
        o2 = m2["assumptions"]["one_offs_detected"][0]
        self.assertIn("모델 세율", o2["tax_rate_source"])
        self.assertAlmostEqual(o2["tax_rate_applied"], m2["assumptions"]["tax_rate"], places=4)

    # ── 음수 부문 매출 분기(부문표 누계 정정 차분)는 실적 셀·소진 창에서 제외 ──
    def test_negative_segment_quarter_dropped(self):
        fin = synth_fin("010140", "삼성", quarters=self.QS, rev0=200_000.0, g_q=0.0)
        sls = synth_sls()
        sls["reconcile"]["2026Q1"]["reported_segment_rev_m"] = -841_100.0                 # HJ重 2022Q4 류
        m = M.build_model("010140", FakeCtx(fins={"010140": fin}, slss={"010140": sls}, roles={"010140": "yard"}))
        rm, d = rows_of(m), m["segments"][0]["driver"]
        self.assertNotIn("2026Q1", rm["매출조선"]["q"])
        self.assertNotIn("2026Q1", rm["매출기타"]["q"])
        self.assertIn("2025Q4", rm["매출조선"]["q"])
        self.assertEqual(d["segment_actual_dropped"]["quarters"], ["2026Q1"])
        self.assertEqual(d["segment_actual_dropped"]["values_eok"], {"2026Q1": -8411.0})
        self.assertEqual(d["runoff_quarters_used"], ["2025Q2", "2025Q3", "2025Q4", "2026Q2"])  # 창이 음수 분기를 건너뛴다
        self.assertTrue(any("조선 부문 매출 음수 분기 1개 제외" in w and "2026Q1 -8411억" in w for w in m["quality"]["warnings"]))
        ref = M.build_model("010140", FakeCtx(fins={"010140": fin}, slss={"010140": synth_sls()}, roles={"010140": "yard"}))
        self.assertIsNone(ref["segments"][0]["driver"]["segment_actual_dropped"])
        self.assertFalse(any("음수 분기" in w for w in ref["quality"]["warnings"]))
        # 음수 분기가 창 밖(2024Q1 — 합성 fin 매출은 2023Q1~ 이지만 sls reconcile 은 2024Q1~)이어도 실적 셀에서는 빠진다
        self.assertFalse(any(c["v"] < 0 for c in rm["매출조선"]["q"].values()))

    # ── BS 롤: FCF 근사 = NI + 감가 − CAPEX(둘 다 있을 때) · 없으면 NI(CAPEX≈감가 가정) ──
    def test_bs_roll_fcf_proxy(self):
        fin = synth_fin(quarters=self.QS)                                                  # CF: CAPEX 3,000 백만원 = 30억/분기, 감가상각비 없음
        m = self._equip(fin)
        rm, br = rows_of(m), m["assumptions"]["bs_roll"]
        self.assertFalse(br["fcf_full"])
        self.assertAlmostEqual(br["capex_avg"], 30.0, places=2)
        self.assertIsNone(br["da_avg"])
        self.assertIn("CAPEX≈감가 가정", br["fcf_proxy"])
        self.assertEqual(rm["CAPEX"]["q"]["2026Q3"]["v"], 30.0)
        self.assertIn("미반영", rm["CAPEX"]["q"]["2026Q3"]["basis"])
        la = "2026Q2"
        ni_q3 = rm["당기순이익"]["q"]["2026Q3"]["v"]
        self.assertAlmostEqual(rm["순차입금"]["q"]["2026Q3"]["v"], rm["순차입금"]["q"][la]["v"] - ni_q3, places=1)          # Q3 배당 0
        self.assertAlmostEqual(rm["이자발생자산"]["q"]["2026Q3"]["v"], rm["이자발생자산"]["q"][la]["v"] + ni_q3, places=1)
        self.assertNotIn("EBITDA", rm)
        self.assertFalse(m["quality"]["ebitda"]["available"])
        # 감가상각비(5,000 백만원 = 50억/분기)를 CF 에 넣으면 FCF = NI + 50 − 30
        fin2 = synth_fin(quarters=self.QS)
        for sc in ("cons", "sep"):
            for q in self.QS:
                fin2[sc]["cf"][q]["감가상각비"] = 5_000.0
        m2 = self._equip(fin2)
        rm2, br2 = rows_of(m2), m2["assumptions"]["bs_roll"]
        self.assertTrue(br2["fcf_full"])
        self.assertAlmostEqual(br2["da_avg"], 50.0, places=2)
        self.assertIn("감가상각비 50억 − CAPEX 30억", br2["fcf_proxy"])
        ni2 = rm2["당기순이익"]["q"]["2026Q3"]["v"]
        self.assertAlmostEqual(rm2["순차입금"]["q"]["2026Q3"]["v"], rm2["순차입금"]["q"][la]["v"] - (ni2 + 50.0 - 30.0), places=1)
        self.assertAlmostEqual(rm2["EBITDA"]["q"]["2026Q3"]["v"], rm2["영업이익"]["q"]["2026Q3"]["v"] + 50.0, places=1)
        self.assertIn("반영(FCF 근사)", rm2["CAPEX"]["q"]["2026Q3"]["basis"])
        self.assertTrue(m2["quality"]["ebitda"]["available"])
        self.assertIn("fin.cons.cf.감가상각비", m2["quality"]["ebitda"]["source"])
        # Q2 배당(DPS 100원 × 1,000만주 = 10억)은 두 롤 모두에서 빠진다
        div = 100 * SHARES / 1e8
        ni_q2 = rm2["당기순이익"]["q"]["2027Q2"]["v"]
        self.assertAlmostEqual(rm2["순차입금"]["q"]["2027Q2"]["v"], rm2["순차입금"]["q"]["2027Q1"]["v"] - (ni_q2 - div + 20.0), places=1)
        self.assertAlmostEqual(rm2["자본총계"]["q"]["2027Q2"]["v"], rm2["자본총계"]["q"]["2027Q1"]["v"] + ni_q2 - div, places=1)
        self.assertTrue(m2["quality"]["identities_ok"])

    # ── status 규칙 문서화: full 은 사유 없음, partial 은 어긋난 조건이 status_reasons 에 ──
    def test_status_rule_and_reasons(self):
        m = self._equip(synth_fin(quarters=self.QS))
        self.assertEqual((m["status"], m["quality"]["status_reasons"]), ("full", []))
        self.assertEqual(m["quality"]["status_rule"], M.STATUS_RULE)
        self.assertIn("full = fin 분기 ≥ 8", M.STATUS_RULE)
        self.assertIn("driver_fallback", M.STATUS_RULE)
        short = self._equip(synth_fin(quarters=M.q_range("2025Q2", "2026Q2")))
        self.assertEqual(short["status"], "partial")
        self.assertEqual(short["quality"]["status_reasons"], ["fin 분기 5 < 8"])
        self.assertEqual(M.summary_row(short)["status_reasons"], ["fin 분기 5 < 8"])
        # 연결 손익 공백 분기(별도 보충) → partial 사유
        fin = synth_fin(quarters=self.QS)
        del fin["cons"]["is"]["2026Q1"]
        sf = self._equip(fin)
        self.assertEqual(sf["status"], "partial")
        self.assertEqual(sf["quality"]["status_reasons"], ["연결 손익 공백 1분기 → 별도 보충"])
        # 드라이버 폴백은 status 에 영향 없음(D7)
        self.assertEqual((m["driver_fallback"], m["status"]), ("no_link", "full"))

    # ── 동결 모델은 동결 이후 fin 에 둔감(백테스트 누출 프로브) ──
    def test_frozen_model_insensitive_to_post_freeze_fin(self):
        a = synth_fin(quarters=self.QS)
        b = json.loads(json.dumps(a))
        for sc in ("cons", "sep"):
            for q in self.QS:
                if q > M.FREEZE_Q:
                    for k in b[sc]["is"][q]:
                        b[sc]["is"][q][k] *= 10.0                                          # 동결 뒤 분기만 10배
                    for k in b[sc]["bs"][q]:
                        b[sc]["bs"][q][k] *= 10.0
        ctx_a = FakeCtx(fins={"999999": a}, roles={"999999": "equip"})
        ctx_b = FakeCtx(fins={"999999": b}, roles={"999999": "equip"})
        fa, fb = ctx_a.model("999999", origin=M.FREEZE_Q), ctx_b.model("999999", origin=M.FREEZE_Q)
        self.assertEqual(json.dumps(fa["rows"], sort_keys=True), json.dumps(fb["rows"], sort_keys=True))
        self.assertEqual(json.dumps(fa["assumptions"], sort_keys=True), json.dumps(fb["assumptions"], sort_keys=True))
        self.assertEqual(fa["periods"]["last_actual"], M.FREEZE_Q)
        self.assertIsNone(fa["valuation"])
        self.assertFalse(fa.get("new_orders_included"))
        # 전체 모델의 백테스트는 당연히 달라진다(동결 뒤 실적이 다르니) — 프로브가 공허하지 않음을 확인
        ma, mb = ctx_a.model("999999"), ctx_b.model("999999")
        self.assertNotEqual(ma["backtest"]["revenue_wape_pct"], mb["backtest"]["revenue_wape_pct"])
        self.assertEqual(ma["backtest"]["n"], 4)


@unittest.skipUnless(os.path.exists(os.path.join(M.FIN_DIR, "002380.json")) and os.path.exists(os.path.join(M.SLS_DIR, "097230.json")),
                     "실제 assets(fin/002380·sls/097230) 없음")
class TestV4RealAssets(unittest.TestCase):
    """실제 자산 — KCC 2026Q2 처분이익 류 일회성의 조정EPS · HJ重 2022Q4 음수 부문 매출 제외 · bs_roll/status 필드."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = M.Ctx(today="2026-10-05")

    def test_kcc_adjusted_eps(self):
        m = self.ctx.model("002380")
        offs = m["assumptions"]["one_offs_detected"]
        if not any(o["q"] == "2026Q2" for o in offs):
            self.skipTest("KCC 2026Q2 가 일회성 창(최근 4분기) 밖으로 나감")
        rm = rows_of(m)
        o = next(o for o in offs if o["q"] == "2026Q2")
        self.assertGreater(o["nonop"], 30_000)                                             # 비영업손익 3.6조
        self.assertGreater(rm["EPS"]["q"]["2026Q2"]["v"], 300_000)
        self.assertLess(rm["조정EPS"]["q"]["2026Q2"]["v"], 50_000)
        self.assertLess(rm["조정EPS"]["a"]["2026"]["v"], rm["EPS"]["a"]["2026"]["v"] * 0.25)
        self.assertEqual(M.summary_row(m)["fy"]["2026E"]["eps_adj"], rm["조정EPS"]["a"]["2026"]["v"])
        self.assertTrue(any("조정EPS" in w for w in m["quality"]["warnings"]))

    def test_hj_negative_segment_dropped_and_fields(self):
        m = self.ctx.model("097230")
        rm = rows_of(m)
        if m["driver_type"] != "sls_marine_plus_uncovered_backlog_runoff":
            self.skipTest("HJ重 선표 드라이버 아님")
        self.assertFalse(any(c["kind"] == "actual" and c["v"] < 0 for c in rm["매출조선"]["q"].values()))
        d = m["segments"][0]["driver"]
        if d.get("segment_actual_dropped"):
            self.assertIn("2022Q4", d["segment_actual_dropped"]["quarters"])
        for st in ("097230", "010140"):
            mm = self.ctx.model(st)
            self.assertIn("bs_roll", mm["assumptions"])
            self.assertIn("status_rule", mm["quality"])
            self.assertIsInstance(mm["quality"]["status_reasons"], list)
            self.assertIn("ebitda", mm["quality"])


class TestLatestCompleteQuarter(unittest.TestCase):
    """최신 '완결' 분기는 달력이 아니라 정기보고서 제출기한(분기·반기 45일, 사업보고서 90일)으로 판정한다."""

    def _ctx(self, today):
        class C:  # noqa: D401 — 최소 컨텍스트
            pass
        c = C(); c.today = today
        c.fx = {"quarters": {q: {} for q in ("2025Q4", "2026Q1", "2026Q2", "2026Q3")}}
        c.fx["quarters"]["2026Q3"] = {"partial": False}
        return c

    def test_quarter_end_passed_but_deadline_not(self):
        self.assertEqual(M._latest_complete_quarter(self._ctx("2026-10-02"), "x"), "2026Q2")   # 2026Q3 보고서 기한 11/14
        self.assertEqual(M._latest_complete_quarter(self._ctx("2026-11-14"), "x"), "2026Q3")
        self.assertEqual(M._latest_complete_quarter(self._ctx("2026-11-13"), "x"), "2026Q2")

    def test_annual_report_90_days(self):
        c = self._ctx("2026-03-30"); c.fx["quarters"]["2025Q3"] = {}
        self.assertEqual(M._latest_complete_quarter(c, "x"), "2025Q3")          # 2025Q4 사업보고서 기한 3/31 → 3/30 엔 아직
        c = self._ctx("2026-03-31"); c.fx["quarters"]["2025Q3"] = {}
        self.assertEqual(M._latest_complete_quarter(c, "x"), "2025Q4")


# ── 라운드 7 (j): 주식수 사건 — 병합/분할/무상증자 환산 · 분기말 후 aik 사건 ──────────────────

def _shares_ctx(fin, px_shares=SHARES, close=20000, prices=True):
    """합성 fin + prices(분기 평균가 20,000 전 분기, 수정주가 가정) 컨텍스트. prices=False 면 시세 없음."""
    px = {"999999": {"close": close, "as_of": "20260928", "shares_outstanding": px_shares,
                     "history_quarterly": {q: {"avg": close, "close_end": close} for q in M.q_range("2023Q1", "2026Q2")}}} if prices else {}
    return FakeCtx(fins={"999999": fin}, roles={"999999": "equip"}, prices=px)


class TestShareEvents(SyntheticAssets, unittest.TestCase):
    """_share_events·_int_ratio: fin 안 정수비 사건은 사건 전 분기 주식수·EPS/BPS/DPS 환산(kind estimate), aik 분기말 후 사건은 split(환산)/issuance·irregular(최신 주식수만)."""
    QS = M.q_range("2023Q1", "2026Q2")

    @classmethod
    def _split_fin(cls, event_q="2026Q1", before=SHARES, after=SHARES // 4, **kw):
        return synth_fin(shares_by_q={q: (before if q < event_q else after) for q in cls.QS}, **kw)

    def setUp(self):
        super().setUp()
        self.base = M.build_model("999999", _shares_ctx(synth_fin()))
        self.brm = rows_of(self.base)

    def test_int_ratio_helper(self):
        self.assertEqual(M._int_ratio(0.25), 0.25)
        self.assertEqual(M._int_ratio(4.0), 4.0)
        self.assertEqual(M._int_ratio(4.9799), 5.0)                      # 인화정공 2026Q2 유통주식수 비율(이익소각 잡음 0.4%)
        self.assertIsNone(M._int_ratio(2.0215))                           # 한화오션 2023Q2 유상증자(2.15% — 정수비 아님)
        self.assertIsNone(M._int_ratio(1.3174))                           # 487400 IPO 신주
        self.assertAlmostEqual(M._int_ratio(0.0667), 1 / 15)              # 메디콕스 2025Q3
        self.assertIsNone(M._int_ratio(1.0))
        self.assertIsNone(M._int_ratio(0.0))
        self.assertIsNone(M._int_ratio(None))
        self.assertEqual(M._ratio_txt(0.25), "1/4")
        self.assertEqual(M._ratio_txt(5.0), "×5")
        self.assertEqual(M._ratio_txt(0.25 * 0.25), "1/16")
        self.assertEqual(M._ratio_txt(0.1 * 2.0), "1/5")

    def test_no_event_model_unchanged_and_schema(self):
        sh = self.base["assumptions"]["shares"]
        self.assertEqual((sh["events"], sh["post_event"], sh["restated_quarters"], sh["dps_restated"], sh["latest"]), ([], None, [], None, SHARES))
        self.assertIn("IAS 33.64", sh["rule"])
        self.assertEqual(self.brm["주식수"]["q"]["2026Q2"], {"v": 10.0, "kind": "actual", "src": "fin.shares.common_outstanding"})
        self.assertEqual(self.brm["주식수"]["q"]["2026Q3"]["v"], 10.0)
        self.assertEqual(self.brm["DPS"]["q"]["2025Q4"], {"v": 100.0, "kind": "actual", "src": "fin.dividend.dps_common(연간, Q4 에 표기)"})
        self.assertEqual(self.brm["DPS"]["q"]["2026Q4"]["basis"], "직전 결산 DPS 100원 유지")
        self.assertEqual(self.base["assumptions"]["dps_assumed"], 100)
        self.assertFalse(any("주식수 사건" in w or "분기말 후" in w for w in self.base["quality"]["warnings"]))

    def test_split_in_fin_history_restates_past(self):
        m = M.build_model("999999", _shares_ctx(self._split_fin(), px_shares=SHARES // 4))
        rm = rows_of(m)
        sh = m["assumptions"]["shares"]
        self.assertEqual([(e["q"], e["ratio"], e["kind"], e["eps_check"]) for e in sh["events"]], [("2026Q1", 0.25, "split", "unconfirmed")])
        self.assertIn("10,000,000→2,500,000", sh["events"][0]["src"])
        self.assertIsNone(sh["post_event"])
        self.assertEqual(sh["restated_quarters"], M.q_range("2023Q1", "2025Q4"))
        self.assertEqual(sh["latest"], SHARES // 4)
        c = rm["주식수"]["q"]["2025Q4"]
        self.assertEqual((c["v"], c["kind"]), (2.5, "estimate"))
        for s in ("환산", "10,000,000", "1/4", "2026Q1", "IAS 33.64"):
            self.assertIn(s, c["basis"])
        self.assertEqual(rm["주식수"]["q"]["2026Q1"], {"v": 2.5, "kind": "actual", "src": "fin.shares.common_outstanding"})
        self.assertEqual(rm["주식수"]["q"]["2026Q3"]["v"], 2.5)
        # EPS/BPS 사건 전 분기 = 기준 모델 × 4(당시 1,000만주 × 1/4), 셀 kind 는 actual(분모만 환산) · 사건 뒤 분기는 최신 주식수
        for q in ("2023Q1", "2025Q4"):
            self.assertAlmostEqual(rm["EPS"]["q"][q]["v"], 4 * self.brm["EPS"]["q"][q]["v"], delta=0.3, msg=q)
            self.assertAlmostEqual(rm["BPS"]["q"][q]["v"], 4 * self.brm["BPS"]["q"][q]["v"], delta=0.5, msg=q)
            self.assertEqual(rm["EPS"]["q"][q]["kind"], "actual")
        self.assertAlmostEqual(rm["BPS"]["q"]["2025Q4"]["v"], rm["지배주주지분"]["q"]["2025Q4"]["v"] * 1e8 / 2.5e6, delta=0.5)
        self.assertAlmostEqual(rm["EPS"]["q"]["2026Q1"]["v"], rm["지배주주순이익"]["q"]["2026Q1"]["v"] * 1e8 / 2.5e6, delta=0.3)
        # PBR 이력(수정주가 20,000 ÷ 환산 BPS)이 사건 경계에서 연속 — 환산 전엔 4배 불연속
        self.assertAlmostEqual(rm["PBR"]["q"]["2025Q4"]["v"] / rm["PBR"]["q"]["2026Q1"]["v"], 1.0, delta=0.05)
        self.assertGreater(self.brm["PBR"]["q"]["2025Q4"]["v"] / self.brm["PBR"]["q"]["2026Q1"]["v"], 0.9)        # 기준(사건 없음)도 연속
        # DPS: 결산 2023~2025(사건 전) 100원 → 400원(estimate), 추정 DPS·dps_assumed·배당 현금도 400원 기준
        d = rm["DPS"]["q"]["2025Q4"]
        self.assertEqual((d["v"], d["kind"]), (400.0, "estimate"))
        self.assertIn("100원 ÷ 1/4", d["basis"])
        self.assertEqual(rm["DPS"]["q"]["2026Q4"]["v"], 400.0)
        self.assertEqual(rm["DPS"]["q"]["2026Q4"]["basis"], "직전 결산 DPS 400원(fin 100원 ÷ 1/4 병합/분할 환산) 유지")
        self.assertEqual(m["assumptions"]["dps_assumed"], 400.0)
        self.assertEqual(m["assumptions"]["payout"], self.base["assumptions"]["payout"])                           # 400 × 250만 = 100 × 1,000만
        self.assertEqual(sorted(sh["dps_restated"]), ["2023", "2024", "2025"])
        self.assertEqual(sh["dps_restated"]["2025"], {"fin": 100, "restated": 400.0, "ratio": "1/4"})
        eq1, eq2 = rm["자본총계"]["q"]["2027Q1"]["v"], rm["자본총계"]["q"]["2027Q2"]["v"]
        self.assertAlmostEqual(eq2, eq1 + rm["당기순이익"]["q"]["2027Q2"]["v"] - 400 * 2.5e6 / 1e8, places=1)
        self.assertTrue(any("주식수 사건 환산: 2026Q1 1/4 병합" in w for w in m["quality"]["warnings"]))

    def test_post_fin_split_from_prices(self):
        fin = synth_fin(shares_by_q={q: 10_020_000 for q in self.QS}, treasury=20_000)        # 발행 1,002만 · 자기 2만 · 유통 1,000만
        base = M.build_model("999999", _shares_ctx(fin, px_shares=10_020_000))                # aik = fin 발행 → 사건 없음
        brm = rows_of(base)
        self.assertIsNone(base["assumptions"]["shares"]["post_event"])
        m = M.build_model("999999", _shares_ctx(fin, px_shares=2_505_000))                    # aik = 발행 ÷ 4 → 분기말 후 4:1 병합
        rm = rows_of(m)
        sh = m["assumptions"]["shares"]
        post = sh["post_event"]
        self.assertEqual((post["kind"], post["ratio"], post["latest"], post["treasury"], post["aik"], post["fin_issued"], post["fin_q"]),
                         ("split", 0.25, 2_500_000, 20_000, 2_505_000, 10_020_000, "2026Q2"))
        self.assertEqual((sh["latest"], sh["events"], sh["restated_quarters"]), (2_500_000, [], self.QS))
        self.assertIn("aik 상장 2,505,000 = fin 2026Q2 보통주 발행 10,020,000 × 1/4", sh["latest_src"])
        self.assertEqual(rm["주식수"]["q"]["2026Q3"]["v"], 2.5)
        self.assertEqual((rm["주식수"]["q"]["2026Q2"]["v"], rm["주식수"]["q"]["2026Q2"]["kind"]), (2.5, "estimate"))
        self.assertIn("분기말 후", rm["주식수"]["q"]["2026Q2"]["basis"])
        self.assertAlmostEqual(rm["EPS"]["q"]["2026Q2"]["v"], 4 * brm["EPS"]["q"]["2026Q2"]["v"], delta=0.3)
        self.assertAlmostEqual(rm["EPS"]["q"]["2026Q3"]["v"], rm["지배주주순이익"]["q"]["2026Q3"]["v"] * 1e8 / 2.5e6, delta=0.3)
        v, bv = m["valuation"], base["valuation"]
        self.assertAlmostEqual(v["eps_fwd12m"], 4 * bv["eps_fwd12m"], delta=0.5)
        self.assertAlmostEqual(v["bps_latest"], 4 * bv["bps_latest"], delta=0.5)
        self.assertEqual(v["pbr_now"], round(20000 / v["bps_latest"], 2))
        self.assertEqual(v["per_now"], round(20000 / v["eps_fwd12m"], 2))
        self.assertAlmostEqual(v["pbr_now"], bv["pbr_now"] / 4, delta=0.01)
        self.assertTrue(any("분기말 후 병합" in w and "2,500,000" in w for w in m["quality"]["warnings"]))
        self.assertEqual(m["assumptions"]["dps_assumed"], 400.0)                                                     # 직전 결산 DPS 도 환산

    def test_post_fin_issuance_from_prices(self):
        m = M.build_model("999999", _shares_ctx(synth_fin(), px_shares=13_000_000))               # 비율 1.3 비정수 > 1 → 증자/상장
        rm = rows_of(m)
        sh = m["assumptions"]["shares"]
        post = sh["post_event"]
        self.assertEqual((post["kind"], post["ratio"], post["latest"], post["new_shares"]), ("issuance", None, 13_000_000, 3_000_000))
        self.assertEqual((sh["latest"], sh["restated_quarters"], sh["dps_restated"]), (13_000_000, [], None))
        for k in ("주식수", "EPS", "BPS", "DPS"):
            for q in self.QS:
                self.assertEqual(rm[k]["q"].get(q), self.brm[k]["q"].get(q), (k, q))                             # 실적 셀 불변(환산 없음)
        self.assertEqual(rm["주식수"]["q"]["2026Q3"]["v"], 13.0)
        self.assertAlmostEqual(rm["EPS"]["q"]["2026Q3"]["v"], rm["지배주주순이익"]["q"]["2026Q3"]["v"] * 1e8 / 1.3e7, delta=0.3)
        self.assertNotEqual(rm["EPS"]["q"]["2026Q3"]["v"], self.brm["EPS"]["q"]["2026Q3"]["v"])
        self.assertEqual(m["valuation"]["bps_latest"], self.brm["BPS"]["q"]["2026Q2"]["v"])                        # 마지막 실적 BPS 그대로
        self.assertEqual(m["assumptions"]["dps_assumed"], 100)
        self.assertTrue(any("분기말 후 증자" in w and "납입자본" in w and "3,000,000" in w for w in m["quality"]["warnings"]))

    def test_small_gap_and_missing_price_ignored(self):
        m = M.build_model("999999", _shares_ctx(synth_fin(), px_shares=10_050_000))                # 0.5% < SHARES_GAP_MIN
        self.assertIsNone(m["assumptions"]["shares"]["post_event"])
        self.assertEqual(m["assumptions"]["shares"]["latest"], SHARES)
        self.assertEqual(json.dumps(m["rows"], sort_keys=True), json.dumps(self.base["rows"], sort_keys=True))
        m2 = M.build_model("999999", _shares_ctx(synth_fin(), prices=False))
        self.assertEqual((m2["assumptions"]["shares"]["post_event"], m2["assumptions"]["shares"]["latest"]), (None, SHARES))
        self.assertEqual(rows_of(m2)["주식수"]["q"], self.brm["주식수"]["q"])

    def test_irregular_decrease_warns_no_restatement(self):
        m = M.build_model("999999", _shares_ctx(synth_fin(), px_shares=7_000_000))                 # 0.7 비정수 감소
        rm = rows_of(m)
        post = m["assumptions"]["shares"]["post_event"]
        self.assertEqual((post["kind"], post["ratio"], post["latest"]), ("irregular", None, 7_000_000))
        self.assertEqual(m["assumptions"]["shares"]["restated_quarters"], [])
        for k in ("주식수", "EPS", "BPS"):
            self.assertEqual(rm[k]["q"]["2026Q2"], self.brm[k]["q"]["2026Q2"])
        self.assertEqual(rm["주식수"]["q"]["2026Q3"]["v"], 7.0)
        self.assertTrue(any("SHARE_EVENTS" in w and "0.7000" in w for w in m["quality"]["warnings"]))

    def test_manual_share_events_override(self):
        with mock.patch.dict(M.SHARE_EVENTS, {"999999": [("2026Q1", 0.5, "test")]}):
            m = M.build_model("999999", _shares_ctx(synth_fin()))
            rm = rows_of(m)
            ev = m["assumptions"]["shares"]["events"]
            self.assertEqual([(e["q"], e["ratio"], e["kind"], e["src"]) for e in ev], [("2026Q1", 0.5, "manual", "SHARE_EVENTS: test")])
            self.assertEqual(rm["주식수"]["q"]["2025Q4"]["v"], 5.0)                                               # 1,000만 × 1/2
            self.assertEqual(rm["주식수"]["q"]["2026Q1"], {"v": 10.0, "kind": "actual", "src": "fin.shares.common_outstanding"})
            self.assertEqual(m["assumptions"]["shares"]["restated_quarters"], M.q_range("2023Q1", "2025Q4"))
            self.assertAlmostEqual(rm["EPS"]["q"]["2025Q4"]["v"], 2 * self.brm["EPS"]["q"]["2025Q4"]["v"], delta=0.2)
            # 자동 감지(2026Q1 4:1)와 같은 분기 → 수동 1건만
            m2 = M.build_model("999999", _shares_ctx(self._split_fin(), px_shares=SHARES // 4))
            self.assertEqual([(e["q"], e["ratio"], e["kind"]) for e in m2["assumptions"]["shares"]["events"]], [("2026Q1", 0.5, "manual")])
            self.assertEqual(rows_of(m2)["주식수"]["q"]["2025Q4"]["v"], 5.0)
        self.assertNotIn("999999", M.SHARE_EVENTS)
        self.assertEqual(set(M.SHARE_EVENTS), {"012160", "012210", "054180"})                                     # 수동표 3건(영흥·삼미금속·메디콕스)

    def test_chained_events_multiply(self):
        by_q = {q: (160_000_000 if q < "2024Q1" else (40_000_000 if q < "2026Q1" else SHARES)) for q in self.QS}
        m = M.build_model("999999", _shares_ctx(synth_fin(shares_by_q=by_q)))
        rm = rows_of(m)
        self.assertEqual([(e["q"], e["ratio"]) for e in m["assumptions"]["shares"]["events"]], [("2024Q1", 0.25), ("2026Q1", 0.25)])
        for q in ("2023Q4", "2025Q4", "2026Q2"):
            self.assertEqual(rm["주식수"]["q"][q]["v"], 10.0, q)                                                  # 1.6억 × 1/16 · 4,000만 × 1/4 · 1,000만
        self.assertIn("× 1/16", rm["주식수"]["q"]["2023Q4"]["basis"])
        self.assertIn("2024Q1 1/4 병합 · 2026Q1 1/4 병합", rm["주식수"]["q"]["2023Q4"]["basis"])
        self.assertIn("× 1/4", rm["주식수"]["q"]["2025Q4"]["basis"])
        self.assertNotIn("1/16", rm["주식수"]["q"]["2025Q4"]["basis"])
        self.assertEqual(rm["주식수"]["q"]["2026Q2"]["kind"], "actual")
        self.assertEqual(m["assumptions"]["shares"]["restated_quarters"], M.q_range("2023Q1", "2025Q4"))
        for q in ("2023Q4", "2025Q4"):
            self.assertAlmostEqual(rm["EPS"]["q"][q]["v"], rm["지배주주순이익"]["q"][q]["v"] * 1e8 / SHARES, delta=0.3)
        self.assertEqual(rm["DPS"]["q"]["2023Q4"]["v"], 1600.0)                                                  # 100 ÷ 1/16
        self.assertEqual(rm["DPS"]["q"]["2025Q4"]["v"], 400.0)

    def test_carried_share_quarter_uses_source_factor(self):
        # fin 이 이월(kind estimate, carried_from)로 채운 분기는 원 분기의 비율 — 사건 뒤 분기를 사건 전 분기에서 이월했어도 두 번 곱하지 않는다
        fin = self._split_fin()
        fin["shares"]["2026Q2"] = dict(fin["shares"]["2026Q1"], kind="estimate", carried_from="2026Q1")
        m = M.build_model("999999", _shares_ctx(fin, px_shares=SHARES // 4))
        rm = rows_of(m)
        self.assertEqual([(e["q"], e["ratio"]) for e in m["assumptions"]["shares"]["events"]], [("2026Q1", 0.25)])
        self.assertEqual(rm["주식수"]["q"]["2026Q2"]["v"], 2.5)
        self.assertEqual(rm["주식수"]["q"]["2025Q4"]["v"], 2.5)
        # fin 에 주식수 자체가 없는 분기(모델이 이웃 분기에서 이월) — 이월 원 분기의 비율
        fin2 = self._split_fin()
        del fin2["shares"]["2025Q4"]
        rm2 = rows_of(M.build_model("999999", _shares_ctx(fin2, px_shares=SHARES // 4)))
        c = rm2["주식수"]["q"]["2025Q4"]
        self.assertEqual((c["v"], c["kind"]), (2.5, "estimate"))
        self.assertIn("2025Q3 값 이월 10,000,000주 × 1/4", c["basis"])

    def test_frozen_model_ignores_post_origin_split(self):
        ctx = _shares_ctx(self._split_fin(), px_shares=SHARES // 4)
        fm = ctx.model("999999", origin=M.FREEZE_Q)
        sh = fm["assumptions"]["shares"]
        self.assertEqual((sh["events"], sh["post_event"], sh["restated_quarters"], sh["latest"]), ([], None, [], SHARES))
        self.assertEqual(rows_of(fm)["주식수"]["q"]["2025Q2"], {"v": 10.0, "kind": "actual", "src": "fin.shares.common_outstanding"})
        self.assertEqual(ctx.model("999999")["assumptions"]["shares"]["restated_quarters"], M.q_range("2023Q1", "2025Q4"))
        # 동결 분기 이전 사건은 동결 모델도 환산한다(px 는 안 본다)
        fin2 = synth_fin(shares_by_q={q: (SHARES if q < "2025Q1" else SHARES // 4) for q in self.QS})
        fm2 = _shares_ctx(fin2, px_shares=SHARES // 16).model("999999", origin=M.FREEZE_Q)
        sh2 = fm2["assumptions"]["shares"]
        self.assertEqual(([(e["q"], e["ratio"]) for e in sh2["events"]], sh2["post_event"]), ([("2025Q1", 0.25)], None))
        self.assertEqual(rows_of(fm2)["주식수"]["q"]["2024Q4"]["v"], 2.5)

    def test_eps_reported_crosscheck_and_candidate_warning(self):
        er_ok = {"2025Q1": {"cur_q": 50, "cur_ytd": 50}, "2026Q1": {"cur_q": 200, "cur_ytd": 200, "prev_q": 200, "prev_ytd": 200}}     # 비교표시 ×4 = 1/0.25
        m = M.build_model("999999", _shares_ctx(self._split_fin(eps_reported=er_ok), px_shares=SHARES // 4))
        self.assertEqual(m["assumptions"]["shares"]["events"][0]["eps_check"], "confirmed")
        self.assertFalse(any("교차검증 불일치" in w for w in m["quality"]["warnings"]))
        er_bad = {"2025Q1": {"cur_q": 50, "cur_ytd": 50}, "2026Q1": {"cur_q": 200, "cur_ytd": 200, "prev_q": 50, "prev_ytd": 50}}     # 미환산 비교표시
        m2 = M.build_model("999999", _shares_ctx(self._split_fin(eps_reported=er_bad), px_shares=SHARES // 4))
        self.assertEqual(m2["assumptions"]["shares"]["events"][0]["eps_check"], "contradicted")
        self.assertTrue(any("교차검증 불일치" in w for w in m2["quality"]["warnings"]))
        self.assertEqual(rows_of(m2)["주식수"]["q"]["2025Q4"]["v"], 2.5)                                           # 경고용 — 환산은 적용
        m3 = M.build_model("999999", _shares_ctx(self._split_fin(), px_shares=SHARES // 4))
        self.assertEqual(m3["assumptions"]["shares"]["events"][0]["eps_check"], "unconfirmed")
        # 주식수 점프 없이 비교표시만 ×5(prev_q·prev_ytd 합치) → 미처리 후보 경고, 환산 없음
        er_cand = {"2025Q1": {"cur_q": 50, "cur_ytd": 50}, "2026Q1": {"cur_q": 60, "cur_ytd": 60, "prev_q": 250, "prev_ytd": 250}}
        m4 = M.build_model("999999", _shares_ctx(synth_fin(eps_reported=er_cand)))
        self.assertTrue(any("미처리 후보" in w and "×5" in w and "SHARE_EVENTS" in w for w in m4["quality"]["warnings"]))
        self.assertEqual(m4["assumptions"]["shares"]["restated_quarters"], [])
        self.assertEqual(rows_of(m4)["주식수"]["q"], self.brm["주식수"]["q"])
        # 단일 신호(prev_ytd 만 ×5)·|cur| < 10원 은 경고하지 않는다; 사건이 잡은 비교표시(−3~+1 분기)도 후보 아님
        er_one = {"2025Q1": {"cur_q": 50, "cur_ytd": 50}, "2026Q1": {"cur_q": 60, "cur_ytd": 60, "prev_q": 50, "prev_ytd": 250}}
        m5 = M.build_model("999999", _shares_ctx(synth_fin(eps_reported=er_one)))
        self.assertFalse(any("미처리 후보" in w for w in m5["quality"]["warnings"]))
        er_small = {"2025Q1": {"cur_q": 2, "cur_ytd": 2}, "2026Q1": {"cur_q": 60, "cur_ytd": 60, "prev_q": 10, "prev_ytd": 10}}
        m6 = M.build_model("999999", _shares_ctx(synth_fin(eps_reported=er_small)))
        self.assertFalse(any("미처리 후보" in w for w in m6["quality"]["warnings"]))
        self.assertFalse(any("미처리 후보" in w for w in m["quality"]["warnings"]))

    def test_restated_cells_match_selfcheck_tolerance(self):
        # 1/15 병합 뒤 주식수 658,436.2 — selfcheck 는 estimate 주식수 셀 v×1e6 으로 EPS/BPS 를 재계산(r1 = 0.05원)한다:
        # 환산 셀을 3자리(500주)·6자리(1주)로 반올림하면 BPS(수십만 원) 재계산이 깨지고, 반올림 없는 백만주 float 면 통과해야 한다
        before, after = 9_876_543, 658_436
        fin = synth_fin(shares_by_q={q: (before if q < "2026Q1" else after) for q in self.QS})
        m = M.build_model("999999", _shares_ctx(fin, px_shares=after))
        rm = rows_of(m)
        self.assertEqual([(e["q"], round(e["ratio"], 6)) for e in m["assumptions"]["shares"]["events"]], [("2026Q1", round(1 / 15, 6))])
        worst = {None: 0.0, 3: 0.0, 6: 0.0}
        for q in M.q_range("2023Q1", "2025Q4"):
            c = rm["주식수"]["q"][q]
            self.assertEqual((c["v"], c["kind"]), (before * (1 / 15) / 1e6, "estimate"), q)
            for key, acct, kind in (("EPS", "(지배주주지분)당기순이익", "is"), ("BPS", "지배주주지분", "bs")):
                base = fin["cons"][kind][q][acct] / M.UNIT_DIV                                                 # 반올림 전 값 — selfcheck base()
                for nd in worst:
                    v = c["v"] if nd is None else round(c["v"], nd)
                    worst[nd] = max(worst[nd], abs(rm[key]["q"][q]["v"] - base * 1e8 / (v * 1e6)))
        self.assertLessEqual(worst[None], 0.05 + 1e-7, worst)
        self.assertGreater(worst[3], 0.05, worst)                                                                 # 반올림하면 실패하는 케이스(검사가 공허하지 않음)
        self.assertGreater(worst[6], 0.05, worst)
        self.assertEqual(rm["주식수"]["q"]["2026Q1"]["v"], 0.658)                                                # 비환산 셀은 종전 3자리

    def test_determinism_with_events(self):
        mk = lambda: M.build_model("999999", _shares_ctx(self._split_fin(eps_reported={"2025Q1": {"cur_q": 50}, "2026Q1": {"prev_q": 200}}), px_shares=SHARES // 16))
        self.assertEqual(json.dumps(mk(), sort_keys=True, ensure_ascii=False), json.dumps(mk(), sort_keys=True, ensure_ascii=False))


REAL_SHARE_FINS = {s: os.path.join(M.FIN_DIR, "%s.json" % s) for s in ("101000", "487400", "085310", "101930", "010140", "075580")}


@unittest.skipUnless(all(os.path.isfile(p) for p in REAL_SHARE_FINS.values()) and os.path.isfile(os.path.join(M.ASSETS, "prices.json")), "assets/fin·prices 실제 산출 없음")
class TestRealShareEvents(unittest.TestCase):
    """실제 자산: KS인더스트리 101000(2023Q1 4:1 감자 + 2026-07 4:1 감자 aik 사후) · 케이앤에스아이앤씨 487400(2026-08-13 상장 신주) · 엔케이 085310(2026Q2 10:1) · 인화정공 101930(2026Q2 1:5 무상증자)."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = M.Ctx(today="2026-10-08")

    def _need(self, stock, last="2026Q2", aik=None):
        fin = self.ctx.fin(stock)
        if fin["quarters"][-1] != last:
            self.skipTest("%s fin 마지막 분기 %s ≠ %s(새 분기 수집 — 사건이 fin 안으로 들어옴)" % (stock, fin["quarters"][-1], last))
        px = self.ctx.price(stock) or {}
        if aik is not None and px.get("shares_outstanding") != aik:
            self.skipTest("%s prices shares_outstanding %s ≠ %s" % (stock, px.get("shares_outstanding"), aik))
        return self.ctx.model(stock), rows_of(self.ctx.model(stock)), px

    def test_ks_industry_post_split_and_history_split(self):
        m, rm, px = self._need("101000", aik=9_910_487)
        sh = m["assumptions"]["shares"]
        self.assertEqual([(e["q"], e["ratio"], e["kind"], e["eps_check"]) for e in sh["events"]], [("2023Q1", 0.25, "split", "confirmed")])
        self.assertEqual((sh["post_event"]["kind"], sh["post_event"]["ratio"], sh["post_event"]["fin_issued"], sh["post_event"]["treasury"]), ("split", 0.25, 39_641_948, 16_979))
        self.assertEqual(sh["latest"], 9_906_242)                                                                 # 9,910,487 − 16,979 × 1/4
        self.assertEqual(rm["주식수"]["q"]["2026Q3"]["v"], 9.906242)
        self.assertEqual((rm["주식수"]["q"]["2026Q2"]["v"], rm["주식수"]["q"]["2026Q2"]["kind"]), (39_624_969 * 0.25 / 1e6, "estimate"))   # 9.90624225 — 실적 셀은 당시 유통 × 1/4(단수주 그대로)
        self.assertEqual(rm["주식수"]["q"]["2022Q4"]["v"], 71_750_792 * 0.25 * 0.25 / 1e6)                        # 4.4844245 — 반올림 없음(selfcheck r1 재계산용)
        self.assertAlmostEqual(rm["EPS"]["q"]["2026Q2"]["v"], 254.2, delta=0.1)                                  # DART 2026Q2 cur_q 64 × 4 = 256 과 정합
        self.assertAlmostEqual(rm["EPS"]["q"]["2026Q1"]["v"], -103.6, delta=0.1)
        self.assertAlmostEqual(rm["EPS"]["a"]["2025"]["v"], -869.4, delta=0.2)
        self.assertAlmostEqual(rm["BPS"]["q"]["2026Q2"]["v"], 4499.7, delta=0.2)
        self.assertAlmostEqual(rm["EPS"]["q"]["2026Q3"]["v"], rm["지배주주순이익"]["q"]["2026Q3"]["v"] * 1e8 / 9_906_242, delta=0.3)
        v = m["valuation"]
        self.assertAlmostEqual(v["bps_latest"], 4499.7, delta=0.2)
        self.assertEqual(v["pbr_now"], round(px["close"] / v["bps_latest"], 2))
        self.assertLess(v["pbr_now"], 0.6)                                                                        # 환산 전 1.27(39.6M 주 기준) → 시총 ÷ 지배지분 ≈ 0.32
        self.assertLess(rm["PBR"]["q"]["2022Q4"]["v"] / rm["PBR"]["q"]["2023Q1"]["v"], 1.5)                       # 환산 전 45.27 vs 9.78 불연속 해소
        self.assertTrue(any("분기말 후 병합" in w for w in m["quality"]["warnings"]))

    def test_kns_inc_post_ipo_issuance(self):
        m, rm, px = self._need("487400", aik=10_260_882)
        sh = m["assumptions"]["shares"]
        self.assertEqual((sh["events"], sh["post_event"]["kind"], sh["post_event"]["new_shares"], sh["latest"]), ([], "issuance", 2_472_000, 10_260_882))
        self.assertEqual(rm["주식수"]["q"]["2026Q2"], {"v": 7.789, "kind": "actual", "src": "fin.shares.common_outstanding"})
        self.assertEqual(rm["주식수"]["q"]["2026Q3"]["v"], 10.260882)
        self.assertAlmostEqual(rm["EPS"]["q"]["2026Q2"]["v"], -197.3, delta=0.1)                                 # 실적 불변(DART cur_q −197)
        self.assertAlmostEqual(rm["EPS"]["q"]["2026Q3"]["v"], rm["지배주주순이익"]["q"]["2026Q3"]["v"] * 1e8 / 10_260_882, delta=0.3)
        self.assertTrue(any("납입자본" in w for w in m["quality"]["warnings"]))

    def test_nk_and_inhwa_history_events(self):
        m, rm, _ = self._need("085310")
        sh = m["assumptions"]["shares"]
        self.assertEqual([(e["q"], round(e["ratio"], 4), e["kind"], e["eps_check"]) for e in sh["events"]], [("2026Q2", 0.1, "split", "confirmed")])
        self.assertIsNone(sh["post_event"])
        self.assertTrue(m["valuation"]["per_band"]["basis"].startswith("hist_quarterly"))                           # 환산 전 sector_default(중위 36.1)
        self.assertEqual(m["valuation"]["per_band"]["mid"], 5.4)
        self.assertEqual((m["assumptions"]["dps_assumed"], rm["DPS"]["q"]["2025Q4"]["v"], rm["DPS"]["q"]["2025Q4"]["kind"]), (100.0, 100.0, "estimate"))
        self.assertAlmostEqual(rm["EPS"]["a"]["2025"]["v"], -597.0, delta=0.2)
        m2, rm2, _ = self._need("101930")
        sh2 = m2["assumptions"]["shares"]
        self.assertEqual([(e["q"], e["ratio"], e["kind"], e["eps_check"]) for e in sh2["events"]], [("2026Q2", 5.0, "bonus", "confirmed")])
        self.assertEqual((m2["assumptions"]["dps_assumed"], rm2["DPS"]["q"]["2025Q4"]["v"]), (150.0, 150.0))
        self.assertAlmostEqual(m2["assumptions"]["payout"], 0.2681, delta=0.001)                                   # 환산 전 1.3404
        self.assertAlmostEqual(rm2["EPS"]["a"]["2025"]["v"], 553.7, delta=0.2)
        self.assertEqual(sh2["dps_restated"]["2025"], {"fin": 750, "restated": 150.0, "ratio": "×5"})

    def test_reference_yards_untouched(self):
        for st in ("010140", "075580"):
            m = self.ctx.model(st)
            sh = m["assumptions"]["shares"]
            self.assertEqual((sh["events"], sh["post_event"], sh["restated_quarters"]), ([], None, []), st)
            rm = rows_of(m)
            la = m["periods"]["last_actual"]
            self.assertEqual(rm["주식수"]["q"][la]["kind"], "actual", st)
            self.assertEqual(rm["주식수"]["q"][la]["v"], round(sh["latest"] / 1e6, 3), st)


if __name__ == "__main__":
    unittest.main()
