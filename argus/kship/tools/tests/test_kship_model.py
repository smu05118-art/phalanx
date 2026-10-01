#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_model 계약 테스트 — 실적 모델 엔진.

실행: cd argus/kship/tools && python3 -m unittest tests.test_kship_model
합성 fin/sls 로 규칙(단위 변환·항등식·EPS·세율 클립·추세 감쇠·체인링크·선표 동결·잔고 소진)을 검사하고,
실제 assets(fin/010140·075580)가 있으면 산출물 불변식(2026Q2 실적 = fin, 추정 10분기+연간 3년, EPS 규모, 결정론)도 본다.
라운드 3(스펙 5-3): forecast_panel 신규수주(매출조선신규 행·base 합산·보수/낙관 scenarios) · sls cohort_mode/backlog_cap_applied 읽기 ·
고객 연동 OOS 선택(동결 la−4분기, WAPE_link ≤ WAPE_trend × 1.10) · 동결 전 합병은 체인링크 없이.
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

import kship_model as M                                              # noqa: E402

SHARES = 10_000_000


def synth_fin(stock="999999", name="합성", quarters=None, rev0=100_000.0, g_q=0.02, scope="cons", tax=0.22, minority=0.1,
              shares=SHARES, dps=100, no_shares=False):
    """백만원 단위 fin json(스펙 2-1 필수 부분). 매출 rev0×(1+g)^i, 원가 70%, 판관 10%, 금융손익 −500, 기타영업외 +100."""
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
        for sc in ("cons", "sep"):
            fin[sc]["is"][q], fin[sc]["bs"][q], fin[sc]["cf"][q] = dict(is_), dict(bs), dict(cf)
        if not no_shares:
            fin["shares"][q] = {"as_of": q, "issued": shares, "treasury": 0, "outstanding": shares, "common_issued": shares, "common_outstanding": shares}
        if q.endswith("Q4"):
            fin["dividend"][q] = {"dps_common": dps, "payout_pct": None}
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
        ctx = FakeCtx(fins={"999999": synth_fin(tax=0.45)}, roles={"999999": "equip"})
        m = M.build_model("999999", ctx)
        self.assertAlmostEqual(m["assumptions"]["tax_rate"], 0.27)

    def test_determinism(self):
        m2 = M.build_model("999999", FakeCtx(fins={"999999": synth_fin()}, roles={"999999": "equip"},
                                             prices={"999999": {"close": 20000, "as_of": "20260928", "shares_outstanding": SHARES}}))
        m1 = M.build_model("999999", FakeCtx(fins={"999999": synth_fin()}, roles={"999999": "equip"},
                                             prices={"999999": {"close": 20000, "as_of": "20260928", "shares_outstanding": SHARES}}))
        self.assertEqual(json.dumps(m1, ensure_ascii=False, sort_keys=True), json.dumps(m2, ensure_ascii=False, sort_keys=True))


def sejin_ctx(vary=False):
    """세진 + 고객 2사 + 종속 2사 합성 컨텍스트(TestSupplierLink·TestVerifierFixes 공용)."""
    return TestSupplierLink._ctx(None, vary)


class TestSupplierLink(unittest.TestCase):
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
        self.assertEqual(m["status"], "partial")
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


class TestYard(unittest.TestCase):
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


class TestVerifierFixes(unittest.TestCase):
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


class TestLinkGrid(unittest.TestCase):
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


def synth_panel(stock="010140", fq=None, base_per_q=200.0, scale=(0.5, 1.0, 1.5), none=False):
    """forecast_panel companies[] 한 회사(스펙 5-3 이 읽는 부분만): scenarios.{conservative,base,optimistic}.quarterly[].new_order_revenue(KRW_million).
    분기별 base = base_per_q × (i+1) 백만원 → 보수/낙관은 scale 배. none=True 면 한화오션·HJ 처럼 값이 전부 None."""
    fq = fq or M.q_range("2026Q3", "2028Q4")
    sc = {}
    for name, k in zip(M.PANEL_SCENARIOS, scale):
        sc[name] = {"quarterly": [{"quarter": q, "horizon": i + 1, "value": None if none else 1_000_000.0, "existing_backlog_revenue": None,
                                   "new_order_revenue": None if none else base_per_q * (i + 1) * k} for i, q in enumerate(fq)],
                    "annual": []}
    return {"stock": stock, "company_name": "합성", "status": "partial", "reason_codes": ["book_value_only"], "origin": "2026Q2", "scenarios": sc}


class TestYardNewOrders(unittest.TestCase):
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
        # origin 회계연도의 실적 분기는 정의상 0 → FY2026 합계가 partial 이 아니다
        self.assertEqual(r1["매출조선신규"]["q"]["2026Q1"]["v"], 0.0)
        self.assertEqual(r1["매출조선신규"]["q"]["2026Q1"]["kind"], "actual")
        self.assertAlmostEqual(r1["매출조선신규"]["a"]["2026"]["v"], (200.0 + 400.0) / 100, places=2)
        self.assertEqual(r1["매출조선신규"]["a"]["2026"]["kind"], "mixed")
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
        self.assertTrue(any("신규수주 매출 미포함" in w and "new_order_revenue 값 없음" in w for w in m1["quality"]["warnings"]))
        self.assertIn("미포함", m1["segments"][0]["driver"]["basis"])
        self.assertTrue(any("신규수주 매출 미포함" in w and "forecast_panel 에 010140 없음" in w for w in m0["quality"]["warnings"]))
        self.assertEqual(m0["driver_type"], "sls_marine_plus_uncovered_backlog_runoff")

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


class TestSlsR3Info(unittest.TestCase):
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


class TestLinkOOS(unittest.TestCase):
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
        self.assertEqual(m["status"], "partial")
        s = M.summary_row(m)["link"]
        self.assertFalse(s["adopted"])
        self.assertEqual(s["rejected_by"], "oos")
        self.assertEqual(s["wape_trend"], oos["wape_trend"])
        # 동결 모델도 같은 규칙(2024Q2 동결)으로 기각 → 백테스트 드라이버는 추세
        self.assertEqual(m["backtest"]["driver_at_freeze"], "trend_seasonal")
        self.assertFalse(m["backtest"]["selection_oos_at_freeze"]["adopted"])

    def test_significance_rejection_skips_oos(self):
        ctx, _ = self._ctx(0.03, lambda i, q, x: 10_000.0 + 3_000.0 * (1 if i % 2 else -1))
        m = M.build_model("222222", ctx)
        rj = m["segments"][0]["driver"]["customer_link_rejected"]
        self.assertEqual(rj["rejected_by"], "corr")
        self.assertFalse(rj["selection_oos"]["adopted"])
        self.assertIsNone(rj["selection_oos"]["wape_link"])
        self.assertIn("OOS 비교 전 기각", rj["selection_oos"]["note"])

    def test_link_oos_insufficient_history(self):
        # 동결 이전 실적 < 8분기면 비교 불가 → adopted True + note
        y = {q: 100.0 * (1.02 ** i) for i, q in enumerate(M.q_range("2024Q1", "2026Q2"))}
        ctx, _ = self._ctx(0.03, lambda i, q, x: 15_000.0)
        cands = M._customer_weight_candidates("222222", ctx)
        oos = M._link_oos(y, cands, ctx, "2026Q2")
        self.assertTrue(oos["adopted"])
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
        est = [q for q in self.m["periods"]["quarters"] if q > self.m["periods"]["last_actual"]]
        self.assertGreaterEqual(len(est), 10)
        self.assertEqual(est[-1], "2028Q4")
        for y in ("2026", "2027", "2028"):
            self.assertIsNotNone(self.rm["매출액"]["a"][y]["v"])
            self.assertIsNotNone(self.rm["EPS"]["a"][y]["v"])
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
                self.assertTrue(o["adopted"])
                if o["wape_link"] is not None and o["wape_trend"] is not None:
                    self.assertLessEqual(o["wape_link"], o["wape_trend"] * M.OOS_WORSE_TOL)
            elif (d.get("customer_link_rejected") or {}).get("rejected_by") == "oos":
                n_oos += 1
                o = d["customer_link_rejected"]["selection_oos"]
                self.assertGreater(o["wape_link"], o["wape_trend"] * M.OOS_WORSE_TOL)
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
        for q in M.q_range("2026Q3", "2028Q4"):
            tot = rm["매출조선기자재"]["q"][q]["v"] + rm["매출종속사"]["q"][q]["v"] + rm["매출연결조정"]["q"][q]["v"]
            self.assertAlmostEqual(tot, rm["매출액"]["q"][q]["v"], delta=0.06)
        if d["type"] == "customer_yard_revenue_weighted":
            self.assertIn("격자", rm["매출조선기자재"]["q"]["2026Q3"]["basis"])
            self.assertIn("2025Q4", rm["매출조선기자재"]["q"]["2026Q3"]["basis"])


if __name__ == "__main__":
    unittest.main()
