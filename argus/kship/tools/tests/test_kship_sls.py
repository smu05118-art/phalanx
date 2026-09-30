#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_sls 계약 테스트 — 선표 매출인식.

실행: cd argus/kship/tools && python3 -m unittest tests.test_kship_sls
합성 원장으로 규칙을 검사하고, 실제 assets 가 있으면 산출물 불변식(스케줄 합 = 계약금액, 공유 계약 미합산)도 본다.
"""
import collections
import datetime
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

import kship_sls as S                                                # noqa: E402

D = datetime.date


def _row(rcp, stock, typ="LNGC", ships=2, amt=700000.0, signed="2025-03-01", start=None, end="2028-06-30",
         supersedes=None, note=""):
    return {"rcp": rcp, "stock": stock, "title": "", "corrected": bool(supersedes), "name": "%s %s척" % (typ, ships),
            "type": typ, "ships": ships, "amt_krw_m": amt, "rev_ratio": None, "party": "선주", "region": "유럽",
            "start": start or signed, "end": end, "signed": signed, "advance": "유", "payterm": "", "withheld": "-",
            "note": note, "option_hint": False, "party_anon": True, "supersedes": supersedes}


class TestSchedule(unittest.TestCase):
    def test_linear_sum_equals_amount_and_inclusive_bounds(self):
        s = S.schedule(D(2025, 3, 1), D(2028, 6, 30), 1000.0)
        self.assertEqual(list(s)[0], "2025Q1")
        self.assertEqual(list(s)[-1], "2028Q2")          # 종료 분기 = 인도
        self.assertAlmostEqual(sum(s.values()), 1000.0, places=9)
        # 2025Q1 은 3/1~3/31 = 31일, 2025Q2 는 91일: 일수 비례
        self.assertAlmostEqual(s["2025Q2"] / s["2025Q1"], 91 / 31, places=9)

    def test_s_curve_sum_equals_amount_and_is_mid_heavy(self):
        s = S.schedule(D(2025, 1, 1), D(2026, 12, 31), 800.0, curve="s_curve")
        self.assertAlmostEqual(sum(s.values()), 800.0, places=9)
        vals = list(s.values())
        self.assertGreater(vals[3], vals[0])             # 중반 > 초반
        self.assertGreater(vals[4], vals[-1])            # 중반 > 후반

    def test_single_day_and_invalid(self):
        s = S.schedule(D(2025, 5, 5), D(2025, 5, 5), 10.0)
        self.assertEqual(dict(s), {"2025Q2": 10.0})
        self.assertEqual(S.schedule(D(2025, 5, 5), D(2025, 1, 1), 10.0), {})
        self.assertEqual(S.schedule(None, D(2025, 1, 1), 10.0), {})
        self.assertEqual(S.schedule(D(2025, 1, 1), D(2025, 9, 1), None), {})

    def test_round_schedule_residual_to_last_quarter(self):
        raw = S.schedule(D(2026, 2, 27), D(2049, 5, 31), 55.63)   # HJ 93분기 공사
        r = S.round_schedule(raw, 55.63)
        self.assertEqual(round(sum(r.values()), 3), 55.63)
        self.assertEqual(len(r), len(raw))


class TestLedgerRules(unittest.TestCase):
    def test_supersedes_drops_original_when_present(self):
        rows = [_row("A1", "010140", amt=700000.0), _row("A2", "010140", amt=720000.0, supersedes="A1"),
                _row("B1", "010140", amt=100000.0, supersedes="ZZ")]          # 원본이 이미 없는 정정
        kept, dropped = S.apply_supersedes(rows)
        self.assertEqual(dropped, ["A1"])
        self.assertEqual(sorted(r["rcp"] for r in kept), ["A2", "B1"])
        self.assertEqual([r["amt_krw_m"] for r in kept if r["rcp"] == "A2"], [720000.0])

    def test_shared_holding_yard_pairs_marked_both_sides(self):
        rows = [_row("H1", "009540", "CONT", 6, 372400.0, "2026-02-26"),
                _row("Y1", "329180", "CONT", 6, 372400.0, "2026-02-26"),
                _row("H2", "009540", "VLGC", 2, 340200.0, "2026-03-09"),     # 삼호 — 짝 없음
                _row("Y2", "329180", "LNGC", 4, 1487200.0, "2026-03-04")]
        pairs = S.mark_shared(rows)
        self.assertEqual(pairs, [("H1", "Y1")])
        by = {r["rcp"]: r for r in rows}
        self.assertEqual(by["H1"]["shared_owner"], "329180")
        self.assertEqual(by["H1"]["shared_with"], "329180:Y1")
        self.assertEqual(by["Y1"]["shared_with"], "009540:H1")
        self.assertNotIn("shared_owner", by["Y1"])
        self.assertNotIn("shared_with", by["H2"])

    def test_holding_build_excludes_shared_from_totals(self):
        rows = [_row("H1", "009540", "CONT", 6, 372400.0, "2026-02-26"),
                _row("Y1", "329180", "CONT", 6, 372400.0, "2026-02-26"),
                _row("H2", "009540", "VLGC", 2, 340200.0, "2026-03-09")]
        S.mark_shared(rows)
        cons = S.prepare_contracts(rows, {}, None, 1350.0)
        cm, yi = S.cohorts(cons)
        h = S.build("009540", cons, cm, yi, {}, None, "linear", 1350.0, "2026Q2")
        y = S.build("329180", cons, cm, yi, {}, None, "linear", 1350.0, "2026Q2")
        self.assertEqual(h["counts"]["shared_excluded"], 1)
        self.assertEqual(h["counts"]["counted"], 1)
        self.assertAlmostEqual(sum(b["usd_m"] for b in h["by_quarter"].values()), 340200.0 / 1350.0, places=2)
        self.assertAlmostEqual(sum(b["usd_m"] for b in y["by_quarter"].values()), 372400.0 / 1350.0, places=2)
        # 공유 계약은 지주 파일에도 남되(추적) counted=False
        h1 = [c for c in h["contracts"] if c["rcp"] == "H1"][0]
        self.assertFalse(h1["counted"])
        self.assertTrue(any("합산 금지" in w for w in h["warnings"]))

    def test_fx_at_sign_prefers_disclosure_note(self):
        r = _row("N1", "329180", note="3) 상기 계약금액은 계약일 최초 고시환율인 USD 1 = 1,383.70원을 적용하여 계산한 금액임.")
        self.assertEqual(S.fx_at_sign(r, None, {}, 1350.0), (1383.7, "disclosure_note"))
        r2 = _row("N2", "329180")
        self.assertEqual(S.fx_at_sign(r2, None, {}, 1350.0), (1350.0, "const_1350"))
        fx = {"quarters": {"2025Q1": {"USDKRW_avg": 1452.3}}}
        self.assertEqual(S.fx_at_sign(r2, fx, {}, 1350.0), (1452.3, "fx.json quarters"))
        # fx.json 은 있지만 그 분기가 없다(quarters·forward·daily_last 모두) → 약정환율 → 상수. 전에는 TypeError 로 빌드가 죽었다
        r3 = _row("N3", "329180", signed="2019-06-01")
        self.assertEqual(S.fx_at_sign(r3, fx, {"2019Q2": {"hedge": {"avg_rate": 1180.5}}}, 1350.0), (1180.5, "yards_cache hedge.avg_rate(약정환율)"))
        self.assertEqual(S.fx_at_sign(r3, fx, {}, 1350.0), (1350.0, "const_1350"))
        self.assertEqual(S.fx_quarter(fx, "2019Q2", None), (None, None))

    def test_end_estimated_from_type_median(self):
        rows = [_row("E1", "010140", "VLCC", 2, 260000.0, "2025-01-10", end="2027-01-09"),   # 730일
                _row("E2", "010140", "VLCC", 2, 262000.0, "2025-02-10", end="2027-02-09"),
                _row("E3", "010140", "VLCC", 1, 130000.0, "2025-03-01", end="-")]
        cons = S.prepare_contracts(rows, {}, None, 1350.0)
        e3 = [c for c in cons if c["rcp"] == "E3"][0]
        self.assertTrue(e3["end_estimated"])
        self.assertEqual(e3["end"], "2027-02-28")            # 2025-03-01 + 730일


class TestReported3M(unittest.TestCase):
    def _snap(self, q, ytd, prev_years=(9310000, 7433900)):
        return {"quarter": q, "ok": True, "orders": {"cur": "KRW", "rows": []},
                "revenue": {"cur": "KRW", "period_cols": ["당기", "전기", "전전기"],
                            "rows": [{"seg": "조선해양", "kind": "수출", "vals": [ytd - 100, prev_years[0], prev_years[1]]},
                                     {"seg": "조선해양", "kind": "국내", "vals": [100, 0, 0]},
                                     {"seg": "조선해양", "kind": "합계", "vals": [ytd, prev_years[0], prev_years[1]]},
                                     {"seg": "토건", "kind": "국내", "vals": [500, 0, 0]},
                                     {"seg": "합 계", "kind": "합계", "vals": [ytd + 500, 0, 0]}]}}

    def test_ytd_to_three_months(self):
        yq = {"2025Q1": self._snap("2025Q1", 2398800), "2025Q2": self._snap("2025Q2", 5549700),
              "2025Q3": self._snap("2025Q3", 7657700), "2025Q4": self._snap("2025Q4", 10436300),
              "2026Q1": self._snap("2026Q1", 2809700)}
        r = S.reported_marine_3m("010140", yq)
        self.assertEqual(r["2025Q1"]["value"], 2398800)                  # Q1 = 누계
        self.assertEqual(r["2025Q2"]["value"], 5549700 - 2398800)
        self.assertEqual(r["2025Q4"]["value"], 10436300 - 7657700)        # Q4 = 연간 − 3Q 누계
        self.assertEqual(r["2026Q1"]["value"], 2809700)
        self.assertEqual(r["2025Q2"]["segments"], ["조선해양"])            # 토건·합계 제외
        self.assertEqual(r["2025Q2"]["source"], "revenue_table_ytd")

    def test_delivered_ytd_proxy_and_project_cumulative(self):
        def snap(q, delivered):
            return {"quarter": q, "ok": True, "revenue": None,
                    "orders": {"cur": "KRW", "rows": [{"seg": "선박", "total": False, "opening": 1, "new": 1, "delivered": delivered, "closing": 1},
                                                      {"seg": "합계", "total": True, "opening": 1, "new": 1, "delivered": delivered, "closing": 1}]}}
        yq = {"2025Q3": snap("2025Q3", 871187), "2025Q4": snap("2025Q4", 1219336), "2026Q1": snap("2026Q1", 306216)}
        r = S.reported_marine_3m("439260", yq)
        self.assertEqual(r["2025Q4"]["value"], 1219336 - 871187)
        self.assertEqual(r["2026Q1"]["value"], 306216)
        self.assertNotIn("2025Q3", r)                                     # 직전 분기 없음 → 차분 불가
        # HJ: 프로젝트 누계 — Q1 은 절대 쓰지 않는다
        def hj(q, delivered):
            return {"quarter": q, "ok": True, "revenue": None,
                    "orders": {"cur": "KRW", "rows": [{"seg": "상선", "total": False, "opening": None, "gross": 1, "new": None, "delivered": delivered, "closing": 1}]}}
        r2 = S.reported_marine_3m("097230", {"2025Q4": hj("2025Q4", 800), "2026Q1": hj("2026Q1", 900), "2026Q2": hj("2026Q2", 950)})
        self.assertNotIn("2026Q1", r2)
        self.assertEqual(r2["2026Q2"]["value"], 50)
        self.assertEqual(r2["2026Q2"]["source"], "delivered_project_cumulative")


class TestCohortAndHedge(unittest.TestCase):
    def test_cohort_relative_position(self):
        rows = [_row("C%d" % i, "010140", "LNGC", 1, a, "2025-0%d-01" % (i % 9 + 1)) for i, a in
                enumerate([300000.0, 330000.0, 340000.0, 350000.0, 420000.0])]
        cons = S.prepare_contracts(rows, {}, None, 1000.0)
        cm, yi = S.cohorts(cons)
        grades = {c["rcp"]: cm[c["rcp"]]["cohort"] for c in cons}
        self.assertEqual(grades["C0"], "②BEP")           # 300/340 = 0.88 < 0.90 → −1
        self.assertEqual(grades["C2"], "③중마진")         # 중위
        self.assertEqual(grades["C4"], "④호황")           # 420/340 = 1.24 > 1.10 → +1
        self.assertEqual(cm["C2"]["cell_n"], 5)

    def test_hedge_ratio_measured_or_assumed(self):
        snap = {"quarter": "2026Q2", "orders": {"rows": [{"seg": "상선", "total": False, "closing": 20000000},
                                                         {"seg": "합계", "total": True, "closing": 20000000}]},
                "hedge": {"usd_sell_m": 3000.0, "avg_rate": 1400.0}}
        h = S.hedge_params("042660", {"2026Q2": snap})
        self.assertEqual(h["kind"], "measured")
        self.assertAlmostEqual(h["hedge_ratio"], 3000.0 / (20000000 / 1400.0), places=4)
        snap2 = dict(snap, hedge={"usd_sell_m": 3000.0, "avg_rate": None})
        h2 = S.hedge_params("010140", {"2026Q2": snap2})
        self.assertEqual((h2["kind"], h2["hedge_ratio"]), ("estimate", 0.7))

    def test_applied_rate_mix(self):
        rows = [_row("A1", "042660", "LNGC", 2, 1400000.0, "2025-03-01", end="2025-06-30")]
        snap = {"quarter": "2025Q1", "ok": True, "orders": {"cur": "KRW", "rows": [{"seg": "상선", "total": False, "closing": 1400000}]},
                "hedge": {"usd_sell_m": 500.0, "avg_rate": 1400.0}, "revenue": None}
        yards = {"042660": {"2025Q1": snap}}
        cons = S.prepare_contracts(rows, yards, None, 1400.0)
        cm, yi = S.cohorts(cons)
        o = S.build("042660", cons, cm, yi, yards, None, "linear", 1300.0, "2025Q1")
        hr = o["hedge"]["hedge_ratio"]                    # 500 / (1400000/1400) = 0.5
        self.assertAlmostEqual(hr, 0.5, places=6)
        # applied = 0.5×1400 + 0.5×1300(spot 상수) = 1350
        for b in o["by_quarter"].values():
            self.assertAlmostEqual(b["applied_rate"], 1350.0, places=1)
            self.assertAlmostEqual(b["hedged_krw_m"], b["usd_m"] * 1350.0, delta=1.0)   # usd_m 3자리 반올림 × 환율


class TestDiagnostics(unittest.TestCase):
    """검증자 추가 — 적용값은 바꾸지 않고 한계를 파일에 적는 진단들."""

    @staticmethod
    def _yards(stock, rows, q="2026Q2", hedge=None):
        return {stock: {q: {"quarter": q, "ok": True, "revenue": None, "hedge": hedge or {},
                            "orders": {"cur": "KRW", "rows": rows}}}}

    def test_hedge_implied_spot_is_reference_only(self):
        snap = {"quarter": "2026Q2", "orders": {"rows": [{"seg": "조선해양", "total": False, "closing": 20000000}]},
                "hedge": {"usd_sell_m": 10000.0, "avg_rate": None}}
        fx = {"quarters": {"2026Q2": {"USDKRW_avg": 1500.0, "USDKRW_end": 1600.0}}}
        h = S.hedge_params("010140", {"2026Q2": snap}, fx=fx)
        self.assertEqual((h["kind"], h["hedge_ratio"]), ("estimate", 0.7))                 # 적용값은 가정 그대로
        self.assertAlmostEqual(h["hedge_ratio_implied_spot"], 10000.0 / (20000000 / 1600.0), places=4)   # 기말 환율로 환산
        self.assertEqual(h["implied_spot_rate"], 1600.0)
        self.assertIn("약정환율이 아닌", h["implied_basis"])
        self.assertIsNone(S.hedge_params("010140", {"2026Q2": snap})["hedge_ratio_implied_spot"])       # fx 없으면 없음
        measured = S.hedge_params("042660", {"2026Q2": dict(snap, hedge={"usd_sell_m": 3000.0, "avg_rate": 1400.0})}, fx=fx)
        self.assertEqual(measured["kind"], "measured")
        self.assertIsNone(measured["hedge_ratio_implied_spot"])

    def test_hedge_gap_warning_when_implied_far_from_assumption(self):
        rows = [_row("A1", "010140", "LNGC", 2, 1400000.0, "2025-03-01", end="2027-06-30")]
        yards = self._yards("010140", [{"seg": "조선해양", "total": False, "closing": 14000000}],
                            hedge={"usd_sell_m": 10000.0, "avg_rate": None})
        fx = {"quarters": {"2026Q2": {"USDKRW_avg": 1400.0, "USDKRW_end": 1400.0}}}
        cons = S.prepare_contracts(rows, yards, fx, 1350.0)
        cm, yi = S.cohorts(cons)
        o = S.build("010140", cons, cm, yi, yards, fx, "linear", 1350.0, "2026Q2")
        self.assertEqual(o["hedge"]["hedge_ratio"], 0.7)
        self.assertAlmostEqual(o["hedge"]["hedge_ratio_implied_spot"], 1.0, places=4)       # 10000 ÷ (14,000,000 ÷ 1400)
        self.assertTrue(any("hedge_ratio_implied_spot" in w and "적용하지 않음" in w for w in o["warnings"]))
        for b in o["by_quarter"].values():                                                  # 적용환율은 0.7 가정 그대로
            self.assertEqual(b["hedge_ratio"], 0.7)

    def test_cohort_direction_vs_reference_stated_in_warnings(self):
        rows = [_row("C%d" % i, "010140", "LNGC", 1, a, "2025-0%d-01" % (i + 1)) for i, a in enumerate([300000.0, 330000.0, 340000.0])]
        cons = S.prepare_contracts(rows, {}, None, 1000.0)
        cm, yi = S.cohorts(cons)
        o = S.build("010140", cons, cm, yi, {}, None, "linear", 1350.0, "2026Q2")
        w = [x for x in o["warnings"] if "상대 등급" in x]
        self.assertEqual(len(w), 1)
        for token in ("레퍼런스", "⑤초호황", "③중마진", "절대 호황 수준 미반영"):
            self.assertIn(token, w[0])
        # 2025~ 등급 있는 수주가 없어도 한계 문장은 남는다
        old = [_row("O1", "010140", "LNGC", 1, 300000.0, "2023-01-01", end="2025-01-01")]
        cons2 = S.prepare_contracts(old, {}, None, 1000.0)
        o2 = S.build("010140", cons2, *S.cohorts(cons2), {}, None, "linear", 1350.0, "2026Q2")
        self.assertTrue(any("상대 등급" in x and "직접 비교 불가" in x for x in o2["warnings"]))

    def test_all_segment_coverage_scope_warning(self):
        rows = [_row("M1", "097230", "CONT", 2, 300000.0, "2026-01-10", end="2028-06-30"),
                _row("W1", "097230", "OTHER", None, 5000000.0, "2026-02-01", end="2035-12-31")]     # 공사 — 수주표 밖
        yards = self._yards("097230", [{"seg": "상선", "total": False, "closing": 1000000, "delivered": None},
                                       {"seg": "합계", "total": True, "closing": 1000000, "delivered": None}])
        cons = S.prepare_contracts(rows, yards, None, 1350.0)
        cm, yi = S.cohorts(cons)
        o = S.build("097230", cons, cm, yi, yards, None, "linear", 1350.0, "2026Q2")
        rs = o["reconcile_summary"]
        self.assertLess(rs["backlog_coverage_at_origin"], 1.0)
        self.assertGreater(rs["backlog_coverage_all_segments"], 1.0)
        self.assertEqual(rs["reported_backlog_segments"], ["상선"])
        self.assertTrue(any("수주표는 조선 부문 범위(상선)" in w for w in o["warnings"]))
        self.assertFalse(any("배율 1 을 상한" in w for w in o["warnings"]))                # 해양 커버리지는 1 미만

    def test_ledger_vs_reported_new_diagnostic(self):
        rows = [_row("N1", "439260", "VLCC", 2, 250000.0, "2026-01-13", end="2028-11-30"),
                _row("N2", "439260", "VLCC", 2, 250000.0, "2026-03-20", end="2029-06-30"),
                _row("N3", "439260", "VLCC", 2, 250000.0, "2026-07-24", end="2029-12-31")]        # 2026Q3 수주 → 연초 누계 밖
        yards = self._yards("439260", [{"seg": "선박", "total": False, "opening": 1000000, "new": 250000, "delivered": 100000, "closing": 1150000}])
        cons = S.prepare_contracts(rows, yards, None, 1350.0)
        cm, yi = S.cohorts(cons)
        o = S.build("439260", cons, cm, yi, yards, None, "linear", 1350.0, "2026Q2")
        lv = o["reconcile_summary"]["ledger_vs_reported_new"]
        self.assertEqual((lv["quarter"], lv["ledger_new_krw_m"], lv["reported_new_krw_m"]), ("2026Q2", 500000.0, 250000.0))
        self.assertAlmostEqual(lv["ratio"], 2.0, places=4)
        self.assertTrue(any("수주표 신규증감" in w and "1.52" not in w for w in o["warnings"]))
        # new 열이 없는 회사(총액−기납품 형식)는 진단 없음
        yards2 = self._yards("010140", [{"seg": "조선해양", "total": False, "opening": None, "new": None, "delivered": 5, "closing": 100}])
        o2 = S.build("010140", cons, cm, yi, yards2, None, "linear", 1350.0, "2026Q2")
        self.assertIsNone(o2["reconcile_summary"]["ledger_vs_reported_new"])

    def test_reconcile_flags_segment_over_consolidated(self):
        # fin 을 흉내내 calibration/교차검사 경로만 본다 — 부문 3개월분이 연결 매출을 1% 넘게 웃돌면 표시, ratio 는 유지
        rows = [_row("A1", "010140", "LNGC", 2, 1400000.0, "2025-01-01", end="2026-12-31")]
        snap = lambda q, ytd: {"quarter": q, "ok": True, "hedge": {}, "orders": {"cur": "KRW", "rows": []},
                               "revenue": {"cur": "KRW", "period_cols": ["당기"], "rows": [{"seg": "조선해양", "kind": "합계", "vals": [ytd]}]}}
        yards = {"010140": {"2025Q1": snap("2025Q1", 1000.0), "2025Q2": snap("2025Q2", 2500.0)}}
        cons = S.prepare_contracts(rows, yards, None, 1350.0)
        cm, yi = S.cohorts(cons)
        real = S._fin_is
        try:
            S._fin_is = lambda stock: {"2025Q1": {"매출액(수익)": 1200.0, "영업이익": 60.0}, "2025Q2": {"매출액(수익)": 1400.0, "영업이익": 70.0}}
            o = S.build("010140", cons, cm, yi, yards, None, "linear", 1350.0, "2025Q2")
        finally:
            S._fin_is = real
        r1, r2 = o["reconcile"]["2025Q1"], o["reconcile"]["2025Q2"]
        self.assertEqual((r1["consolidated_rev_m"], r1["exceeds_consolidated_pct"]), (1200.0, None))       # 1000 ≤ 1200
        self.assertEqual(r2["consolidated_rev_m"], 1400.0)
        self.assertAlmostEqual(r2["exceeds_consolidated_pct"], (1500.0 / 1400.0 - 1) * 100, places=2)      # 2500−1000 = 1500 > 1400
        self.assertIsNotNone(r2["ratio"])                                                                  # ratio 는 그대로 계산
        self.assertTrue(any("부문 매출 3개월분 > 연결 매출" in w and "2025Q2" in w for w in o["warnings"]))
        self.assertIn("회사 전체 — 부문 아님", o["calibration"]["basis"])


@unittest.skipUnless(os.path.exists(os.path.join(S.ASSETS, "contracts.json")) and os.path.isdir(S.YARDS_CACHE),
                     "실제 assets 없음")
class TestRealAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outs = S.run(S.YARDS + [S.HOLDING], write=False)

    def test_every_schedule_sums_to_contract(self):
        n = 0
        for o in self.outs.values():
            for c in o["contracts"]:
                if c["schedule"]:
                    self.assertAlmostEqual(sum(c["schedule"].values()), c["amt_usd_m"], places=3, msg=c["rcp"])
                    n += 1
        self.assertGreater(n, 200)

    def test_shared_contracts_not_double_counted(self):
        h, y = self.outs[S.HOLDING], self.outs[S.HOLDING_SHARES_WITH]
        shared_h = [c for c in h["contracts"] if c.get("shared_owner")]
        shared_y = [c for c in y["contracts"] if c.get("shared_with")]
        self.assertEqual(len(shared_h), len(shared_y))
        self.assertGreaterEqual(len(shared_h), 20)
        self.assertTrue(all(c["counted"] is False for c in shared_h))
        counted_usd = sum(c["amt_usd_m"] for c in h["contracts"] if c.get("counted"))
        self.assertAlmostEqual(sum(b["usd_m"] for b in h["by_quarter"].values()), counted_usd, delta=0.5)
        # 지주 파일의 합에는 공유 계약 금액이 없다
        self.assertLess(sum(b["usd_m"] for b in h["by_quarter"].values()),
                        sum(c["amt_usd_m"] or 0 for c in h["contracts"]) - sum(c["amt_usd_m"] for c in shared_h) + 0.5)

    def test_by_quarter_consistency_and_window(self):
        for o in self.outs.values():
            for q, b in o["by_quarter"].items():
                self.assertAlmostEqual(sum(b["by_type"].values()), b["usd_m"], places=2)
                self.assertAlmostEqual(sum(b["by_cohort"].values()), b["usd_m"], places=2)
                self.assertEqual(b["kind"], "estimate")
            w = o["counts"]["forecast_window"]
            self.assertEqual((w["from"], w["to"]), ("2026Q3", "2028Q4"))
        self.assertTrue(all(o["counts"]["counted"] > 0 for o in self.outs.values()))

    def test_real_files_state_limits(self):
        for o in self.outs.values():
            w = o["warnings"]
            self.assertTrue(any("상대 등급" in x and "⑤초호황" in x for x in w), o["stock"])          # 코호트 방향 한계
            self.assertIn("회사 전체 — 부문 아님", o["calibration"]["basis"], o["stock"])           # 캘리브레이션 근거
            h = o["hedge"]
            if h["kind"] == "estimate":
                self.assertTrue(any("헤지비율 0.7 은 가정" in x for x in w), o["stock"])
                if h.get("hedge_ratio_implied_spot") is not None and abs(h["hedge_ratio_implied_spot"] - 0.7) > 0.15:
                    self.assertTrue(any("hedge_ratio_implied_spot" in x for x in w), o["stock"])
            else:
                self.assertIn("kship_page.yard_summary 방식", h["basis"])
            rs = o["reconcile_summary"]
            if (rs.get("backlog_coverage_at_origin") or 0) > 1.0:
                self.assertTrue(any("배율 1 을 상한" in x for x in w), o["stock"])
            if (rs.get("backlog_coverage_all_segments") or 0) > 1.0 >= (rs.get("backlog_coverage_at_origin") or 0):
                self.assertTrue(any("backlog_coverage_all_segments 는 배율로 쓰지 말 것" in x for x in w), o["stock"])
            for q, r in o["reconcile"].items():
                if r.get("consolidated_rev_m") and r["reported_segment_rev_m"] > r["consolidated_rev_m"] * 1.01:
                    self.assertIsNotNone(r["exceeds_consolidated_pct"], (o["stock"], q))
        # 한화오션은 약정환율 공시 → 실측 0.1717 (usd_sell 3,850.75 ÷ (33,008,410 ÷ 1,472.04))
        h = self.outs["042660"]["hedge"]
        if h["kind"] == "measured" and h["quarter"] == "2026Q2":
            self.assertAlmostEqual(h["hedge_ratio"], 3850.75 / (33008410 / 1472.04), places=4)


if __name__ == "__main__":
    unittest.main()
