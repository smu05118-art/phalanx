#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_sls 계약 테스트 — 선표 매출인식.

실행: cd argus/kship/tools && python3 -m unittest tests.test_kship_sls
합성 원장으로 규칙을 검사하고, 실제 assets 가 있으면 산출물 불변식(스케줄 합 = 계약금액, 공유 계약 미합산)도 본다.
T6 D1: by_quarter[q].marine_hedged_krw_m_signed_by_origin / _post_origin 분해(합 = marine_hedged_krw_m) · post_origin 요약 블록.
"""
import collections
import datetime
import json
import os
import statistics
import sys
import unittest
from unittest import mock

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


class NoFinAssets:
    """합성 테스트는 assets/fin/*.json 을 읽지 않는다(§14-6 ⑦, 2026-10-08) — S._fin_is(회사·레퍼런스 010620 모두)를 None 으로.
    build()·calibration()·cohort_opm_calibration() 이 모두 이 함수로 fin 을 읽는다. 실자산은 TestRealAssets 만."""

    def setUp(self):
        p = mock.patch.object(S, "_fin_is", lambda stock: None)
        p.start()
        self.addCleanup(p.stop)


class TestSchedule(NoFinAssets, unittest.TestCase):
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


class TestLedgerRules(NoFinAssets, unittest.TestCase):
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


class TestReported3M(NoFinAssets, unittest.TestCase):
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


class TestCohortAndHedge(NoFinAssets, unittest.TestCase):
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


class TestDiagnostics(NoFinAssets, unittest.TestCase):
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
        with mock.patch.object(S, "_fin_is", lambda stock: {"2025Q1": {"매출액(수익)": 1200.0, "영업이익": 60.0}, "2025Q2": {"매출액(수익)": 1400.0, "영업이익": 70.0}}):
            o = S.build("010140", cons, cm, yi, yards, None, "linear", 1350.0, "2025Q2")
        r1, r2 = o["reconcile"]["2025Q1"], o["reconcile"]["2025Q2"]
        self.assertEqual((r1["consolidated_rev_m"], r1["exceeds_consolidated_pct"]), (1200.0, None))       # 1000 ≤ 1200
        self.assertEqual(r2["consolidated_rev_m"], 1400.0)
        self.assertAlmostEqual(r2["exceeds_consolidated_pct"], (1500.0 / 1400.0 - 1) * 100, places=2)      # 2500−1000 = 1500 > 1400
        self.assertIsNotNone(r2["ratio"])                                                                  # ratio 는 그대로 계산
        self.assertTrue(any("부문 매출 3개월분 > 연결 매출" in w and "2025Q2" in w for w in o["warnings"]))
        self.assertIn("회사 전체 — 부문 아님", o["calibration"]["basis"])

    def test_no_fin_assets_in_synthetic_build(self):
        # NoFinAssets 가 걸린 합성 build — 회사(010140)·레퍼런스(010620) fin 을 읽지 않았다는 증명: 캘리브레이션 보류 · 미포 실측 대조 빈 사전
        rows = [_row("C1", "010140", "LNGC", 1, 340000.0, "2025-02-01", end="2027-12-31")]
        cons = S.prepare_contracts(rows, {}, None, 1000.0)
        o = S.build("010140", cons, *S.cohorts(cons), {}, None, "linear", 1350.0, "2026Q2")
        self.assertIsNone(o["calibration"]["calibrated_shift"])
        self.assertTrue(o["calibration"]["basis"].startswith("fin 미수집"), o["calibration"]["basis"])
        self.assertEqual(o["cohort_opm_calibration"]["actual_opm_fin_010620_by_year"], {})


class TestReferenceAnchorAndCap(NoFinAssets, unittest.TestCase):
    """MODEL_SPEC §5-2 — 코호트 기본 reference_anchor(수주연도 표), 대안 ledger_relative(*_alt), 잔고 캡 1/coverage."""

    @staticmethod
    def _yards(stock, rows, q="2026Q2"):
        return {stock: {q: {"quarter": q, "ok": True, "revenue": None, "hedge": {}, "orders": {"cur": "KRW", "rows": rows}}}}

    @staticmethod
    def _mixed_rows():
        # 2021 수주 1건(④) + 2025 수주 3건(⑤; 원장 상대등급은 ②·③·④) + 공사 1건(등급 없음)
        return [_row("O1", "010140", "LNGC", 1, 300000.0, "2021-06-01", end="2026-09-30"),
                _row("C0", "010140", "LNGC", 1, 300000.0, "2025-01-01", end="2027-12-31"),
                _row("C1", "010140", "LNGC", 1, 340000.0, "2025-02-01", end="2027-12-31"),
                _row("C2", "010140", "LNGC", 1, 420000.0, "2025-03-01", end="2027-12-31"),
                _row("W1", "010140", "OTHER", None, 100000.0, "2025-04-01", end="2027-12-31")]

    def test_cohort_by_order_year_table(self):
        self.assertEqual([S.cohort_by_order_year(y)[0] for y in (2018, 2020, 2021, 2022, 2026)],
                         ["③중마진", "③중마진", "④호황", "⑤초호황", "⑤초호황"])
        self.assertEqual(S.cohort_by_order_year(None), (None, "연도 없음"))
        self.assertIn("COHORT_BY_ORDER_YEAR", S.cohort_by_order_year(2021)[1])
        # 레퍼런스 매출연도 표(백만$)와 되돌림 근거가 파일 표에 그대로 실린다 — 전부 가정
        t = S.cohort_table()
        self.assertEqual(t["kind"], "estimate")
        self.assertEqual(t["reference_revenue_year_mix_usd_m"]["2024"]["⑤초호황"], 1647)
        self.assertEqual(dict(t["reference_revenue_year_mix_usd_m"]["2027"]), {"⑤초호황": 5857})
        self.assertAlmostEqual(t["reference_revenue_year_share"]["2025"]["⑤초호황"], 3018 / 3180, places=3)
        self.assertEqual([dict(x) for x in t["by_order_year"]],
                         [{"from": None, "to": 2020, "cohort": "③중마진"}, {"from": 2021, "to": 2021, "cohort": "④호황"}, {"from": 2022, "to": None, "cohort": "⑤초호황"}])
        self.assertFalse(t["newbuild_index"]["present"])
        self.assertEqual(t["opm_table"], S.COHORT_OPM)

    def test_newbuild_index_takes_priority_with_table_fallback(self):
        idx = {"source": "test index", "as_of": "2026-09-30", "by_year": {"2021": 120.0, "2025": 170.0},
               "grades": [[160, "⑤초호황"], [0, "①적자"], [110, "②BEP"], [125, "③중마진"], [145, "④호황"]],   # 순서 무관
               "cohort_by_year": {"2025": "④호황"}}
        self.assertEqual(S.cohort_by_order_year(2021, idx), ("②BEP", "newbuild_index.by_year 2021=120 × grades"))
        self.assertEqual(S.cohort_by_order_year(2025, idx)[0], "④호황")          # 직접 지정이 지수보다 우선
        self.assertEqual(S.cohort_by_order_year(2026, idx)[0], "⑤초호황")        # 지수에 없는 연도 → 표
        self.assertIn("COHORT_BY_ORDER_YEAR", S.cohort_by_order_year(2026, idx)[1])
        self.assertIsNone(S.load_newbuild_index(os.path.join(HERE, "no_such_newbuild_index.json")))
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "newbuild_index.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write('{"source": "x"}')                                          # by_year·cohort_by_year 없음 → 무시
            self.assertIsNone(S.load_newbuild_index(p))
            with open(p, "w", encoding="utf-8") as f:
                f.write('{"source": "x", "cohort_by_year": {"2021": "④호황"}}')
            self.assertEqual(S.load_newbuild_index(p)["source"], "x")
        # build 에 지수를 주면 cohort_source·cohort_table·계약 근거에 지수 우선이 적힌다
        cons = S.prepare_contracts(self._mixed_rows(), {}, None, 1000.0)
        cm, yi = S.cohorts(cons)
        o = S.build("010140", cons, cm, yi, {}, None, "linear", 1350.0, "2026Q2", newbuild_index=idx)
        by = {c["rcp"]: c for c in o["contracts"]}
        self.assertEqual(by["O1"]["cohort"], "②BEP")                                  # 2021 지수 120 → ②
        self.assertEqual(by["C0"]["cohort"], "④호황")                                  # 2025 직접 지정
        self.assertEqual(by["C0"]["cohort_detail"]["source"], "assets/newbuild_index.json")
        self.assertTrue(o["cohort_table"]["newbuild_index"]["present"])
        self.assertIn("newbuild_index.json", o["cohort_source"])
        self.assertTrue(any("newbuild_index.json 우선 적용" in w for w in o["warnings"]))

    def test_reference_anchor_default_and_ledger_alt(self):
        cons = S.prepare_contracts(self._mixed_rows(), {}, None, 1000.0)
        cm, yi = S.cohorts(cons)
        o = S.build("010140", cons, cm, yi, {}, None, "linear", 1350.0, "2026Q2")
        self.assertEqual((o["cohort_mode"], o["cohort_mode_alt"]), ("reference_anchor", "ledger_relative"))
        self.assertEqual(o["cohort_opm_table_source"], "reference_calibrated")            # 2026-10-08 오너 결정: 기본 표 = 레퍼런스 실측 캘리브레이션
        t = o["cohort_opm_table"]
        by = {c["rcp"]: c for c in o["contracts"]}
        self.assertEqual(by["O1"]["cohort"], "④호황")                                   # 2021 수주
        self.assertEqual([by[r]["cohort"] for r in ("C0", "C1", "C2")], ["⑤초호황"] * 3)   # 2025 수주
        self.assertEqual((by["C0"]["cohort_alt"], by["C1"]["cohort_alt"], by["C2"]["cohort_alt"]), ("②BEP", "③중마진", "④호황"))
        self.assertEqual((by["W1"]["cohort"], by["W1"]["cohort_alt"]), (None, None))     # 공사 — 두 모드 다 등급 없음
        self.assertIn("레퍼런스", by["C0"]["cohort_basis"])
        self.assertEqual(by["C0"]["cohort_detail"]["order_year"], 2025)
        q = o["by_quarter"]["2027Q1"]                                                    # O1 은 2026Q3 인도 → 2025 수주 3건 + 공사
        sch = {r: by[r]["schedule"]["2027Q1"] for r in ("C0", "C1", "C2", "W1")}          # 분기 믹스는 계약기간 비례(시작일이 다르다)
        self.assertAlmostEqual(q["target_opm"], t["⑤초호황"], places=6)
        self.assertAlmostEqual(q["target_opm_alt"], (t["②BEP"] * sch["C0"] + t["③중마진"] * sch["C1"] + t["④호황"] * sch["C2"]) / (sch["C0"] + sch["C1"] + sch["C2"]), places=4)
        self.assertAlmostEqual(sum(q["by_cohort_alt"].values()), q["usd_m"], places=2)
        self.assertAlmostEqual(q["by_cohort"]["⑤초호황"], sum(v for k, v in q["by_cohort_alt"].items() if k != "등급없음"), places=2)
        self.assertAlmostEqual(q["by_cohort"]["등급없음"], sch["W1"], places=2)
        self.assertEqual(q["graded_share"], q["graded_share_alt"])                       # 등급 대상은 같다
        self.assertAlmostEqual(o["by_quarter"]["2026Q3"]["by_cohort"]["④호황"], by["O1"]["schedule"]["2026Q3"], delta=0.05)   # 마지막 분기 반올림 잔차
        self.assertEqual((o["target_opm"]["2027Q1"]["mode"], o["target_opm_alt"]["2027Q1"]["mode"]), ("reference_anchor", "ledger_relative"))
        self.assertEqual((o["calibration"]["mode"], o["calibration_alt"]["mode"]), ("reference_anchor", "ledger_relative"))
        self.assertIn("클락슨", o["cohort_source"])
        self.assertEqual(o["cohort_table"]["kind"], "estimate")
        self.assertAlmostEqual(o["by_year"]["2027"]["by_cohort_alt"]["④호황"],
                               sum(v for k, v in by["C2"]["schedule"].items() if k.startswith("2027")), delta=0.05)   # 인도 분기 반올림 잔차
        self.assertFalse(o["backlog_cap_applied"])
        w = [x for x in o["warnings"] if "코호트 기본 모드" in x]
        self.assertEqual(len(w), 1)
        self.assertIn("⑤초호황 100%", w[0])                                             # 기본 모드 2025~ 판정
        self.assertIn("상대 등급", w[0])

    def test_cohort_mode_switch_swaps_primary_and_alt(self):
        cons = S.prepare_contracts(self._mixed_rows(), {}, None, 1000.0)
        cm, yi = S.cohorts(cons)
        o = S.build("010140", cons, cm, yi, {}, None, "linear", 1350.0, "2026Q2")
        o2 = S.build("010140", cons, cm, yi, {}, None, "linear", 1350.0, "2026Q2", mode="ledger_relative")
        self.assertEqual((o2["cohort_mode"], o2["cohort_mode_alt"]), ("ledger_relative", "reference_anchor"))
        by2 = {c["rcp"]: c for c in o2["contracts"]}
        self.assertEqual((by2["C0"]["cohort"], by2["C0"]["cohort_alt"]), ("②BEP", "⑤초호황"))
        for q in o["by_quarter"]:
            self.assertEqual(o2["by_quarter"][q]["target_opm"], o["by_quarter"][q]["target_opm_alt"])
            self.assertEqual(o2["by_quarter"][q]["by_cohort"], o["by_quarter"][q]["by_cohort_alt"])
            self.assertEqual(o2["by_quarter"][q]["usd_m"], o["by_quarter"][q]["usd_m"])
        self.assertEqual(o2["target_opm"]["2027Q1"]["mode"], "ledger_relative")
        with self.assertRaises(ValueError):
            S.build("010140", cons, cm, yi, {}, None, "linear", 1350.0, "2026Q2", mode="bogus")

    def test_calibration_measured_against_primary_mode(self):
        rows = [_row("C0", "010140", "LNGC", 1, 300000.0, "2025-01-01", end="2027-12-31"),
                _row("C1", "010140", "LNGC", 1, 340000.0, "2025-02-01", end="2027-12-31"),
                _row("C2", "010140", "LNGC", 1, 420000.0, "2025-03-01", end="2027-12-31")]
        cons = S.prepare_contracts(rows, {}, None, 1000.0)
        cm, yi = S.cohorts(cons)
        with mock.patch.object(S, "_fin_is", lambda stock: {"2026Q1": {"매출액(수익)": 1000.0, "영업이익": 100.0}, "2026Q2": {"매출액(수익)": 1000.0, "영업이익": 100.0}}):
            o = S.build("010140", cons, cm, yi, {}, None, "linear", 1350.0, "2026Q2")
        alt_t = statistics.median(o["target_opm_alt"][q]["opm"] for q in ("2026Q1", "2026Q2"))
        self.assertAlmostEqual(o["calibration"]["calibrated_shift"], 0.10 - o["cohort_opm_table"]["⑤초호황"], places=4)   # 기본 모드: 타겟 ⑤ 표 값 → 실측과의 차
        self.assertAlmostEqual(o["calibration_alt"]["calibrated_shift"], 0.10 - alt_t, places=4)
        self.assertLess(alt_t, 0.10)                                                                # 원장 상대등급 ②·③·④ 믹스(캘리브레이션 표 1.0~5.4%)
        self.assertEqual(o["calibration"]["quarters_used"], ["2026Q1", "2026Q2"])
        self.assertIn("회사 전체 — 부문 아님", o["calibration"]["basis"])
        self.assertTrue(any("음수일 수 있다" in w for w in o["warnings"]))

    def _cap_rows(self):
        return [_row("P1", "439260", "VLCC", 2, 250000.0, "2025-09-19", end="2028-09-30"),      # origin 전 수주 → 캡 대상
                _row("P2", "439260", "VLCC", 2, 250000.0, "2026-01-13", end="2028-11-30"),
                _row("N3", "439260", "VLCC", 2, 250000.0, "2026-07-24", end="2029-12-31"),      # origin 뒤 수주 → 그 잔고에 없다, 캡 안 함
                _row("W1", "439260", "OTHER", None, 100000.0, "2026-01-01", end="2028-12-31")]   # 비해양 → 캡 안 함

    def test_backlog_cap_scales_only_pre_origin_marine_future(self):
        rows = self._cap_rows()
        seg = {"seg": "선박", "total": False, "opening": 1, "new": 1, "delivered": 1}
        yards = self._yards("439260", [dict(seg, closing=300000)])
        yards0 = self._yards("439260", [dict(seg, closing=30000000)])                          # 커버리지 ≪ 1 → 캡 없음(원값 대조용)
        cons = S.prepare_contracts(rows, yards, None, 1000.0)
        cm, yi = S.cohorts(cons)
        o = S.build("439260", cons, cm, yi, yards, None, "linear", 1000.0, "2026Q2")
        o0 = S.build("439260", cons, cm, yi, yards0, None, "linear", 1000.0, "2026Q2")
        rs, cap = o["reconcile_summary"], o["backlog_cap"]
        cov = rs["backlog_coverage_at_origin"]
        self.assertGreater(cov, 1.0)
        self.assertTrue(o["backlog_cap_applied"] and cap["applied"])
        self.assertAlmostEqual(cap["factor"], 1.0 / cov, places=4)
        self.assertAlmostEqual(rs["backlog_coverage_after_cap"], 1.0, places=3)
        self.assertEqual(cap["kind"], "estimate")
        self.assertAlmostEqual(cap["remaining_marine_krw_m_at_origin_capped"], cap["reported_marine_backlog_krw_m"], delta=1.0)
        by = {c["rcp"]: c for c in o["contracts"]}
        self.assertEqual([by[r]["backlog_cap_applied"] for r in ("P1", "P2", "N3", "W1")], [True, True, False, False])
        self.assertEqual(by["N3"]["signed_by_origin"], False)
        # 과거 분기(≤ origin)와 계약별 스케줄은 그대로
        for q in o["by_quarter"]:
            if q <= "2026Q2":
                self.assertNotIn("backlog_cap", o["by_quarter"][q])
                self.assertEqual(o["by_quarter"][q]["usd_m"], o0["by_quarter"][q]["usd_m"])
        self.assertEqual(by["P1"]["schedule"], {c["rcp"]: c for c in o0["contracts"]}["P1"]["schedule"])
        # 미래 분기: (P1+P2) × 배율 + N3 + W1 원값
        q, f = "2027Q1", cap["factor"]
        b, b0 = o["by_quarter"][q], o0["by_quarter"][q]
        sch = {r: by[r]["schedule"][q] for r in ("P1", "P2", "N3", "W1")}
        self.assertAlmostEqual(b["usd_m"], (sch["P1"] + sch["P2"]) * f + sch["N3"] + sch["W1"], places=2)
        self.assertAlmostEqual(b["backlog_cap"]["usd_m_raw"], b0["usd_m"], places=2)
        self.assertAlmostEqual(b["backlog_cap"]["hedged_krw_m_raw"], b0["hedged_krw_m"], places=0)
        self.assertAlmostEqual(b["by_type"]["OTHER"], sch["W1"], places=2)
        self.assertAlmostEqual(sum(b["by_type"].values()), b["usd_m"], places=2)
        self.assertAlmostEqual(sum(b["by_cohort"].values()), b["usd_m"], places=2)
        self.assertAlmostEqual(sum(b["by_cohort_alt"].values()), b["usd_m"], places=2)
        self.assertAlmostEqual(b["hedged_krw_m"], b["usd_m"] * 1000.0, delta=2.0)               # 상수 1000 = 헤지·spot → applied 1000
        self.assertAlmostEqual(b["marine_usd_m"], b["usd_m"] - sch["W1"], places=2)
        self.assertIn("backlog_cap", b["basis"])
        self.assertEqual(b["kind"], "estimate")
        # 창·연도 합계는 캡 값, 원값은 *_raw
        w = o["counts"]["forecast_window"]
        self.assertGreater(w["hedged_krw_m_raw"], w["hedged_krw_m"])
        self.assertAlmostEqual(w["hedged_krw_m_raw"], o0["counts"]["forecast_window"]["hedged_krw_m"], places=0)
        self.assertEqual(w["hedged_krw_m_raw"], cap["window_hedged_krw_m_raw"])
        y = o["by_year"]["2027"]
        self.assertGreater(y["hedged_krw_m_raw"], y["hedged_krw_m"])
        self.assertAlmostEqual(y["marine_hedged_krw_m_raw"], o0["by_year"]["2027"]["marine_hedged_krw_m"], places=0)
        self.assertLess(cap["future_marine_hedged_krw_m"], cap["future_marine_hedged_krw_m_raw"])
        self.assertTrue(any("1/coverage" in x and "배율 1 을 상한" in x for x in o["warnings"]))
        self.assertIn("겹쳐 곱하지 말 것", rs["warning"])

    def test_backlog_cap_not_applied_when_coverage_under_one(self):
        rows = self._cap_rows()
        yards = self._yards("439260", [{"seg": "선박", "total": False, "opening": 1, "new": 1, "delivered": 1, "closing": 30000000}])
        cons = S.prepare_contracts(rows, yards, None, 1000.0)
        cm, yi = S.cohorts(cons)
        o = S.build("439260", cons, cm, yi, yards, None, "linear", 1000.0, "2026Q2")
        rs, cap = o["reconcile_summary"], o["backlog_cap"]
        self.assertLess(rs["backlog_coverage_at_origin"], 1.0)
        self.assertEqual(rs["backlog_coverage_after_cap"], rs["backlog_coverage_at_origin"])
        self.assertFalse(o["backlog_cap_applied"] or cap["applied"])
        self.assertEqual(cap["factor"], 1.0)
        self.assertFalse(any("backlog_cap" in b for b in o["by_quarter"].values()))
        self.assertFalse(any(c["backlog_cap_applied"] for c in o["contracts"]))
        w = o["counts"]["forecast_window"]
        self.assertEqual((w["hedged_krw_m_raw"], w["usd_m_raw"]), (w["hedged_krw_m"], w["usd_m"]))
        self.assertEqual(cap["future_marine_hedged_krw_m_raw"], cap["future_marine_hedged_krw_m"])
        self.assertFalse(any("1/coverage" in x for x in o["warnings"]))
        # 잔고 없음(지주처럼 marine_closing None) → 커버리지 None, 캡 없음
        o2 = S.build("439260", cons, cm, yi, {}, None, "linear", 1000.0, "2026Q2")
        self.assertIsNone(o2["reconcile_summary"]["backlog_coverage_at_origin"])
        self.assertFalse(o2["backlog_cap_applied"])

    def test_post_origin_split_keys(self):
        # T6 D1: marine_hedged_krw_m = origin 분기말까지 체결분(캡 적용) + origin 이후 체결분(N3, 캡 없음). 비해양(W1)은 어느 쪽에도 없다. 기존 키는 그대로
        rows = self._cap_rows()
        seg = {"seg": "선박", "total": False, "opening": 1, "new": 1, "delivered": 1}
        for closing in (300000, 30000000):                                                       # 캡 적용 / 미적용 둘 다
            yards = self._yards("439260", [dict(seg, closing=closing)])
            cons = S.prepare_contracts(rows, yards, None, 1000.0)
            cm, yi = S.cohorts(cons)
            o = S.build("439260", cons, cm, yi, yards, None, "linear", 1000.0, "2026Q2")
            by = {c["rcp"]: c for c in o["contracts"]}
            for q, b in o["by_quarter"].items():
                self.assertAlmostEqual(b["marine_hedged_krw_m_signed_by_origin"] + b["marine_hedged_krw_m_post_origin"], b["marine_hedged_krw_m"], delta=0.11)
                self.assertAlmostEqual(b["marine_hedged_krw_m_post_origin"], by["N3"]["schedule"].get(q, 0.0) * 1000.0, delta=5.0)   # applied 1000; 마지막 분기 round_schedule 잔차 ≤ 0.005$
                if q <= "2026Q2":
                    self.assertEqual(b["marine_hedged_krw_m_post_origin"], 0.0)
            po = o["post_origin"]
            self.assertEqual((po["n"], po["amt_krw_m"], po["rcps"]), (1, 250000.0, ["N3"]))
            self.assertAlmostEqual(po["future_marine_hedged_krw_m"],
                                   sum(b["marine_hedged_krw_m_post_origin"] for q, b in o["by_quarter"].items() if q > "2026Q2"), delta=1.0)
            self.assertIn("marine_hedged_krw_m", o["by_quarter"]["2027Q1"])                       # 기존 키 불변
            if o["backlog_cap_applied"]:
                b = o["by_quarter"]["2027Q1"]
                f = o["backlog_cap"]["factor"]
                self.assertAlmostEqual(b["marine_hedged_krw_m_signed_by_origin"], (by["P1"]["schedule"]["2027Q1"] + by["P2"]["schedule"]["2027Q1"]) * f * 1000.0, delta=1.0)

    def test_summary_carries_mode_and_cap(self):
        rows = self._cap_rows()
        yards = self._yards("439260", [{"seg": "선박", "total": False, "opening": 1, "new": 1, "delivered": 1, "closing": 300000}])
        cons = S.prepare_contracts(rows, yards, None, 1000.0)
        cm, yi = S.cohorts(cons)
        outs = {"439260": S.build("439260", cons, cm, yi, yards, None, "linear", 1000.0, "2026Q2")}
        s = S.summary(outs, "2026Q2", "linear", 1000.0, [], [])
        self.assertEqual((s["cohort_mode"], s["cohort_mode_alt"], s["next_q"]), ("reference_anchor", "ledger_relative", "2026Q3"))
        r = s["rows"][0]
        self.assertTrue(r["backlog_cap_applied"])
        self.assertLess(r["backlog_cap_factor"], 1.0)
        self.assertGreater(r["window_hedged_krw_m_raw"], r["window_hedged_krw_m"])
        self.assertAlmostEqual(r["target_opm_next_q"], outs["439260"]["cohort_opm_table"]["⑤초호황"], places=6)
        self.assertLess(r["target_opm_alt_next_q"], r["target_opm_next_q"])
        self.assertIn("calibrated_shift_alt", r)


class TestUpgradesR5(NoFinAssets, unittest.TestCase):
    """5차(2026-10-05, V3 sls 검증) — fx 부분 분기 표시 · 헤지 참고치(수주시점 평균환율) · 레퍼런스 HEDGE 실측값(미포 0.65 · 삼성重 1.00) ·
    코호트 OPM 표 캘리브레이션(--opm-table) · built_at 고정(--today)."""

    def test_fx_quarter_marks_partial(self):
        fx = {"quarters": {"2026Q3": {"USDKRW_avg": 1400.0}, "2026Q4": {"USDKRW_avg": 1354.78, "partial": True, "days": 2}},
              "forward": {"2027Q1": {"USDKRW_avg": 1348.28}}, "daily_last": {"USDKRW": 1348.28}}
        self.assertEqual(S.fx_quarter(fx, "2026Q3", 1350.0), (1400.0, "fx.json quarters"))
        self.assertEqual(S.fx_quarter(fx, "2026Q4", 1350.0), (1354.78, "fx.json quarters(partial 2d)"))
        self.assertEqual(S.fx_quarter(fx, "2027Q1", 1350.0), (1348.28, "fx.json forward"))
        self.assertEqual(S.fx_quarter(fx, "2030Q1", 1350.0), (1348.28, "fx.json daily_last(flat)"))
        # 수주시점 환율 출처에도 그대로 남는다(2026-10-02 체결 LNGC 2척이 2026Q4 이틀 평균을 쓴다는 것이 보이게)
        self.assertEqual(S.fx_at_sign(_row("P1", "010140", signed="2026-10-02"), fx, {}, 1350.0), (1354.78, "fx.json quarters(partial 2d)"))

    def test_hedge_reference_values_and_default_override(self):
        snap = {"quarter": "2026Q2", "orders": {"rows": [{"seg": "조선해양", "total": False, "closing": 20000000}]},
                "hedge": {"usd_sell_m": 10000.0, "avg_rate": None}}
        h = S.hedge_params("010140", {"2026Q2": snap})
        self.assertEqual(dict(h["reference_hedge"]), {"HD현대미포 010620 SLS!HEDGE": 0.65, "삼성중공업 010140 SLS!HEDGE": 1.0})
        self.assertIn("미포 65%", h["basis"])
        self.assertIn("삼성重 100%", h["basis"])
        self.assertNotIn("레퍼런스 SLS 시트의 HEDGE 70%", h["basis"])            # 전 문구 — 레퍼런스 어디에도 70% 는 없다(실측 2026-10-05)
        h2 = S.hedge_params("010140", {"2026Q2": snap}, default_ratio=0.65)
        self.assertEqual((h2["kind"], h2["hedge_ratio"]), ("estimate", 0.65))
        self.assertIn("HEDGE 65% 가정", h2["basis"])
        # build 에 hedge_default 를 주면 적용환율이 그 비율로 섞인다
        rows = [_row("A1", "010140", "LNGC", 2, 1400000.0, "2025-03-01", end="2025-06-30")]
        yards = {"010140": {"2025Q1": {"quarter": "2025Q1", "ok": True, "revenue": None, "hedge": {},
                                       "orders": {"cur": "KRW", "rows": [{"seg": "조선해양", "total": False, "closing": 1400000}]}}}}
        cons = S.prepare_contracts(rows, yards, None, 1400.0)                    # 수주시점 환율 = 상수 1400
        cm, yi = S.cohorts(cons)
        o = S.build("010140", cons, cm, yi, yards, None, "linear", 1300.0, "2025Q1", hedge_default=1.0)
        for b in o["by_quarter"].values():
            self.assertEqual(b["hedge_ratio"], 1.0)
            self.assertAlmostEqual(b["applied_rate"], 1400.0, places=1)         # 100% 헤지 → spot 1300 은 섞이지 않는다
        self.assertTrue(any("헤지비율 1 은 가정" in w for w in o["warnings"]))

    def test_hedge_implied_sign_rate_reference(self):
        # 수주시점 환율 1000(상수) 계약 1,400,000백만원 → 평균환율 1000 · 잔고 14,000,000백만원 = 14,000백만$ · 명목 7,000 → 0.50
        rows = [_row("A1", "010140", "LNGC", 2, 1400000.0, "2025-03-01", end="2027-06-30"),
                _row("N1", "010140", "LNGC", 1, 700000.0, "2026-08-01", end="2028-06-30")]       # origin 뒤 체결 → 평균환율·잔고 대상 아님
        yards = {"010140": {"2026Q2": {"quarter": "2026Q2", "ok": True, "revenue": None,
                                       "hedge": {"usd_sell_m": 7000.0, "avg_rate": None},
                                       "orders": {"cur": "KRW", "rows": [{"seg": "조선해양", "total": False, "closing": 14000000}]}}}}
        fx = {"quarters": {"2026Q2": {"USDKRW_avg": 1400.0, "USDKRW_end": 1400.0}}}            # 체결 분기는 없다 → 상수 1000
        cons = S.prepare_contracts(rows, yards, fx, 1000.0)
        cm, yi = S.cohorts(cons)
        o = S.build("010140", cons, cm, yi, yards, fx, "linear", 1000.0, "2026Q2")
        h = o["hedge"]
        self.assertEqual(h["kind"], "estimate")
        self.assertEqual(h["implied_sign_n"], 1)                                                 # A1 만(origin 분기말까지 체결)
        self.assertEqual(h["implied_sign_rate"], 1000.0)
        self.assertAlmostEqual(h["hedge_ratio_implied_sign_rate"], 7000.0 / (14000000 / 1000.0), places=4)   # 0.50
        self.assertAlmostEqual(h["hedge_ratio_implied_spot"], 7000.0 / (14000000 / 1400.0), places=4)        # 0.70 — 현물 기준은 가정과 같다
        self.assertIn("수주시점 평균환율", h["implied_sign_basis"])
        self.assertEqual(h["hedge_ratio"], 0.7)                                                               # 적용값 불변
        w = [x for x in o["warnings"] if "hedge_ratio_implied_sign_rate" in x]
        self.assertEqual(len(w), 1)                                              # 현물 기준 0.70 이지만 평균환율 기준 0.50 이 0.15 넘게 달라 경고
        self.assertIn("적용하지 않음", w[0])
        self.assertIn("1000.00원", w[0])
        # 실측(약정환율 공시) 회사·잔고 없는 회사는 비운다
        yards_m = {"010140": {"2026Q2": dict(yards["010140"]["2026Q2"], hedge={"usd_sell_m": 7000.0, "avg_rate": 1000.0})}}
        om = S.build("010140", cons, cm, yi, yards_m, fx, "linear", 1000.0, "2026Q2")
        self.assertEqual(om["hedge"]["kind"], "measured")
        self.assertIsNone(om["hedge"]["hedge_ratio_implied_sign_rate"])
        self.assertIsNone(S.build("010140", cons, cm, yi, {}, fx, "linear", 1000.0, "2026Q2")["hedge"]["hedge_ratio_implied_sign_rate"])

    def test_cohort_opm_calibration_table_and_block(self):
        table, block = S.cohort_opm_calibration(fin_is={})                      # fin 없음 → 실측 대조 비움
        self.assertEqual(list(table), ["①적자", "②BEP", "③중마진", "④호황", "⑤초호황"])
        # ⑤ = (85.7×0.0902 + 1314.1×0.0826 + 2195.8×0.111 + 5785.4×0.1108 + 4813.1×0.1106) ÷ 14194.1
        self.assertAlmostEqual(table["⑤초호황"], 0.1080, places=3)
        self.assertAlmostEqual(table["④호황"], 0.0540, places=3)
        self.assertAlmostEqual(table["③중마진"], 0.0426, places=3)
        self.assertAlmostEqual(table["②BEP"], 0.0100, places=4)
        self.assertAlmostEqual(table["①적자"], -0.0108, places=3)
        vals = [table[k] for k in table]
        self.assertEqual(vals, sorted(vals))                                     # 단조 ① < ② < ③ < ④ < ⑤
        self.assertEqual(block["kind"], "estimate")
        self.assertEqual(block["table_assumed"]["⑤초호황"], 0.15)
        self.assertEqual(block["table_reference_calibrated"], table)
        y26 = block["by_year"]["2026"]
        self.assertAlmostEqual(y26["reference_cells"], 0.1063, places=3)        # (269.8×0.01 + 5785.4×0.1108) ÷ 6055.2
        self.assertAlmostEqual(y26["assumed_table"], 0.1433, places=3)          # (269.8×0 + 5785.4×0.15) ÷ 6055.2
        self.assertEqual(y26["reference_sls_row"], 0.1057)
        self.assertGreater(y26["gap_assumed_minus_reference"], 0.035)
        self.assertLess(abs(y26["gap_calibrated_minus_reference"]), 0.005)
        self.assertFalse(block["reference_actual_opm_row"]["usable"])
        self.assertEqual(block["actual_opm_fin_010620_by_year"], {})
        # 실측 대조: fin 흉내 — 2024 두 분기 OPM 2% → reference_sls_minus_actual = 레퍼런스 셀 가중 − 실측
        fin = {"2024Q1": {"매출액(수익)": 1000.0, "영업이익": 20.0}, "2024Q2": {"매출액(수익)": 1000.0, "영업이익": 20.0}}
        _, b2 = S.cohort_opm_calibration(fin_is=fin)
        a = b2["actual_opm_fin_010620_by_year"]["2024"]
        self.assertEqual((a["opm"], a["quarters"]), (0.02, 2))
        self.assertAlmostEqual(a["reference_sls_minus_actual"], b2["by_year"]["2024"]["reference_cells"] - 0.02, places=4)
        # 창을 바꾸면 표가 바뀐다(2025~27 → ⑤ 11.1% 안팎); 자료 없는 코호트는 가정 표로 돌아가고 표시한다
        t2, b3 = S.cohort_opm_calibration(window=(2025, 2027), fin_is={})
        self.assertAlmostEqual(t2["⑤초호황"], 0.1108, places=3)
        self.assertEqual(t2["③중마진"], 0.05)
        self.assertTrue(b3["table_used_years"]["③중마진"]["fallback_assumed"])
        self.assertFalse(block["table_used_years"]["③중마진"]["fallback_assumed"])

    def test_opm_table_switch_changes_targets_and_shift(self):
        rows = [_row("C0", "010140", "LNGC", 1, 300000.0, "2025-01-01", end="2027-12-31"),
                _row("C1", "010140", "LNGC", 1, 340000.0, "2025-02-01", end="2027-12-31")]
        cons = S.prepare_contracts(rows, {}, None, 1000.0)
        cm, yi = S.cohorts(cons)
        with mock.patch.object(S, "_fin_is", lambda stock: {"2026Q1": {"매출액(수익)": 1000.0, "영업이익": 100.0}, "2026Q2": {"매출액(수익)": 1000.0, "영업이익": 100.0}}):
            o = S.build("010140", cons, cm, yi, {}, None, "linear", 1350.0, "2026Q2", opm_table="assumed")
            oc = S.build("010140", cons, cm, yi, {}, None, "linear", 1350.0, "2026Q2")                     # 기본 = reference_calibrated
            oc2 = S.build("010140", cons, cm, yi, {}, None, "linear", 1350.0, "2026Q2", opm_table="reference_calibrated")
        self.assertEqual(S.OPM_TABLE_DEFAULT, "reference_calibrated")
        self.assertEqual(json.dumps(oc, ensure_ascii=False, sort_keys=True), json.dumps(oc2, ensure_ascii=False, sort_keys=True))   # 기본값 == 명시값
        self.assertEqual((o["cohort_opm_table_source"], oc["cohort_opm_table_source"]), ("assumed", "reference_calibrated"))
        self.assertEqual(o["cohort_opm_table"], o["cohort_opm_table_assumed"])
        self.assertEqual(oc["cohort_opm_table"], o["cohort_opm_calibration"]["table_reference_calibrated"])
        self.assertEqual(oc["cohort_opm_table_assumed"], o["cohort_opm_table"])
        self.assertEqual(o["cohort_table"]["opm_table"], S.COHORT_OPM)
        self.assertEqual(oc["cohort_table"]["opm_table"], oc["cohort_opm_table"])
        cal5 = oc["cohort_opm_table"]["⑤초호황"]
        for q in o["by_quarter"]:                                                # 2025 수주 2건 = 전부 ⑤ → 타겟 = 표의 ⑤ 값
            self.assertAlmostEqual(o["by_quarter"][q]["target_opm"], 0.15, places=6)
            self.assertAlmostEqual(oc["by_quarter"][q]["target_opm"], cal5, places=6)
            self.assertEqual(o["by_quarter"][q]["usd_m"], oc["by_quarter"][q]["usd_m"])            # 매출·환산은 표와 무관
            self.assertEqual(o["by_quarter"][q]["hedged_krw_m"], oc["by_quarter"][q]["hedged_krw_m"])
        self.assertIn("assumed(①-5% ②0% ③5% ④10% ⑤15% — 가정)", o["target_opm"]["2026Q3"]["basis"])
        self.assertIn("reference_calibrated(", oc["target_opm"]["2026Q3"]["basis"])
        # calibrated_shift(실측 − 타겟)는 표 차이만큼 반대로 움직인다 — 실측 수준은 같다
        self.assertAlmostEqual(o["calibration"]["calibrated_shift"], 0.10 - 0.15, places=4)
        self.assertAlmostEqual(oc["calibration"]["calibrated_shift"], 0.10 - cal5, places=4)
        tf = o["cohort_opm_calibration"]["this_file"]
        self.assertEqual(tf["applied_table"], "assumed")
        self.assertAlmostEqual(tf["target_opm_next_q"]["assumed"], 0.15, places=6)
        self.assertAlmostEqual(tf["target_opm_next_q"]["reference_calibrated"], cal5, places=6)
        self.assertEqual(oc["cohort_opm_calibration"]["this_file"]["applied_table"], "reference_calibrated")
        self.assertTrue(any("코호트 OPM 표 assumed 적용" in w and "--opm-table reference_calibrated" in w for w in o["warnings"]))
        self.assertTrue(any("코호트 OPM 표 reference_calibrated 적용" in w and "--opm-table assumed" in w for w in oc["warnings"]))
        # 대안 모드(ledger_relative) 타겟도 같은 표로 계산된다
        q = "2027Q1"
        by = {c["rcp"]: c for c in oc["contracts"]}
        a, b = by["C0"]["schedule"][q], by["C1"]["schedule"][q]
        t = oc["cohort_opm_table"]
        self.assertAlmostEqual(oc["by_quarter"][q]["target_opm_alt"], (t[by["C0"]["cohort_alt"]] * a + t[by["C1"]["cohort_alt"]] * b) / (a + b), places=4)
        with self.assertRaises(ValueError):
            S.build("010140", cons, cm, yi, {}, None, "linear", 1350.0, "2026Q2", opm_table="bogus")

    def test_built_at_today_summary_fields_and_cli_guards(self):
        rows = [_row("C0", "010140", "LNGC", 1, 300000.0, "2025-01-01", end="2027-12-31")]
        cons = S.prepare_contracts(rows, {}, None, 1000.0)
        cm, yi = S.cohorts(cons)
        o = S.build("010140", cons, cm, yi, {}, None, "linear", 1350.0, "2026Q2", today="2026-10-05")
        self.assertEqual(o["built_at"], "2026-10-05")
        self.assertEqual(S.build("010140", cons, cm, yi, {}, None, "linear", 1350.0, "2026Q2")["built_at"], datetime.date.today().isoformat())
        s = S.summary({"010140": o}, "2026Q2", "linear", 1350.0, [], [], today="2026-10-05", hedge_default=0.7)
        self.assertEqual((s["built_at"], s["opm_table"], s["hedge_ratio_default"]), ("2026-10-05", "reference_calibrated", 0.7))
        r = s["rows"][0]
        self.assertEqual(r["opm_table"], "reference_calibrated")
        self.assertAlmostEqual(r["target_opm_next_q_by_table"]["assumed"], 0.15, places=6)
        self.assertAlmostEqual(r["target_opm_next_q_by_table"]["reference_calibrated"], o["cohort_opm_table_assumed"]["⑤초호황"] - 0.042, places=2)
        self.assertIn("hedge_ratio_implied_sign_rate", r)
        self.assertIn("hedge_ratio_implied_spot", r)
        for bad in (["--stock", "010140", "--dry-run", "--today", "2026/10/05"],
                    ["--stock", "010140", "--dry-run", "--hedge-default", "1.5"],
                    ["--stock", "010140", "--dry-run", "--opm-table", "bogus"]):
            with self.assertRaises(SystemExit):                                   # argparse 가 run() 전에 멈춘다 — assets 불필요
                S.main(bad)


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
                self.assertAlmostEqual(sum(b["by_cohort_alt"].values()), b["usd_m"], places=2)
                self.assertEqual(b["kind"], "estimate")
            w = o["counts"]["forecast_window"]
            self.assertEqual((w["from"], w["to"]), ("2026Q3", "2028Q4"))
            # T6 D1: 체결시점 분해 합 = marine_hedged_krw_m, origin 이전 분기엔 origin 이후 체결분 없음
            for q, b in o["by_quarter"].items():
                self.assertAlmostEqual(b["marine_hedged_krw_m_signed_by_origin"] + b["marine_hedged_krw_m_post_origin"], b["marine_hedged_krw_m"], delta=0.11)
                if q <= o["origin"]:
                    self.assertEqual(b["marine_hedged_krw_m_post_origin"], 0.0)
            n_post = sum(1 for c in o["contracts"] if c.get("counted") and c["type"] != "OTHER" and not c["signed_by_origin"])
            self.assertEqual(o["post_origin"]["n"], n_post)
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

    def test_real_reference_anchor_default_and_backlog_cap(self):
        """§5-2: 기본 모드 reference_anchor·대안 ledger_relative 둘 다 저장, 커버리지 > 1 인 회사만 캡(2026Q2 기준 대한조선 1.164)."""
        for o in self.outs.values():
            self.assertEqual((o["cohort_mode"], o["cohort_mode_alt"]), ("reference_anchor", "ledger_relative"), o["stock"])
            self.assertEqual(o["cohort_table"]["kind"], "estimate")
            self.assertIn("클락슨", o["cohort_source"])
            self.assertEqual(o["calibration"]["mode"], "reference_anchor")
            self.assertEqual(o["calibration_alt"]["mode"], "ledger_relative")
            self.assertEqual(o["backlog_cap"]["kind"], "estimate")
            for c in o["contracts"]:
                if c.get("cohort"):
                    self.assertEqual(c["cohort"], S.cohort_by_order_year(c["year"])[0], c["rcp"])       # 수주연도 표 그대로
                    self.assertIsNotNone(c["cohort_alt"], c["rcp"])                                     # 대상 집합은 두 모드가 같다
                else:
                    self.assertIsNone(c["cohort_alt"], c["rcp"])
            for q, b in o["by_quarter"].items():
                if q > o["origin"] and b["target_opm"] is not None:
                    self.assertGreaterEqual(b["target_opm"], 0.05)                                       # ≤2020 ③ 이 하한
                    self.assertLessEqual(b["target_opm"], 0.15)
            rs, cap = o["reconcile_summary"], o["backlog_cap"]
            cov = rs.get("backlog_coverage_at_origin")
            if cov is not None and cov > 1.0:
                self.assertTrue(o["backlog_cap_applied"], o["stock"])
                self.assertAlmostEqual(cap["factor"], 1.0 / cov, places=4)
                self.assertAlmostEqual(rs["backlog_coverage_after_cap"], 1.0, places=3)
                self.assertLess(o["counts"]["forecast_window"]["hedged_krw_m"], o["counts"]["forecast_window"]["hedged_krw_m_raw"])
                self.assertTrue(any("1/coverage" in w and "배율 1 을 상한" in w for w in o["warnings"]), o["stock"])
                for q, b in o["by_quarter"].items():
                    self.assertEqual("backlog_cap" in b, q > o["origin"], (o["stock"], q))
            else:
                self.assertFalse(o["backlog_cap_applied"], o["stock"])
                self.assertEqual(cap["factor"], 1.0)
                self.assertEqual(o["counts"]["forecast_window"]["hedged_krw_m"], o["counts"]["forecast_window"]["hedged_krw_m_raw"])
                # 캡이 없으면 분기 합 = counted 계약 금액 합(달러) — 캡이 있으면 원값(_raw)이 그 역할
                self.assertAlmostEqual(sum(b["usd_m"] for b in o["by_quarter"].values()),
                                       sum(c["amt_usd_m"] for c in o["contracts"] if c.get("counted")), delta=0.5, msg=o["stock"])
        d = self.outs["439260"]
        if d["origin"] == "2026Q2" and (d["reconcile_summary"]["backlog_coverage_at_origin"] or 0) > 1.0:
            self.assertTrue(d["backlog_cap_applied"])
        s = S.summary(self.outs, "2026Q2", "linear", 1350.0, [], [])
        self.assertEqual(s["cohort_mode"], "reference_anchor")
        self.assertEqual({r["stock"] for r in s["rows"] if r["backlog_cap_applied"]},
                         {o["stock"] for o in self.outs.values() if o["backlog_cap_applied"]})

    def test_ledger_rcps_all_scheduled_and_r5_keys(self):
        """⑥ 원장(contracts.json, 정정 정리 뒤)의 모든 rcp 가 그 회사 파일에 있고(봇이 뒤에 추가한 계약 포함) 금액 있는 counted 계약은 스케줄이 있다.
        5차 키(cohort_opm_table_source·cohort_opm_calibration·hedge 참고치·reference_hedge)가 전 파일에 있다."""
        ledger, _ = S.apply_supersedes([dict(r) for r in S.load_asset("contracts.json")["rows"]])
        for o in self.outs.values():
            want = sorted(r["rcp"] for r in ledger if r["stock"] == o["stock"])
            self.assertEqual(sorted(c["rcp"] for c in o["contracts"]), want, o["stock"])
            for c in o["contracts"]:
                if c.get("counted") and c["amt_usd_m"] and c["start"] and c["end"]:
                    self.assertTrue(c["schedule"], c["rcp"])
            self.assertEqual(o["cohort_opm_table_source"], "reference_calibrated")
            cb = o["cohort_opm_calibration"]
            self.assertEqual(o["cohort_opm_table"], cb["table_reference_calibrated"])
            self.assertEqual(o["cohort_opm_table_assumed"], {k: S.COHORT_OPM[k] for k in S.COHORT_LABELS.values()})
            self.assertEqual(cb["this_file"]["applied_table"], "reference_calibrated")
            self.assertAlmostEqual(cb["table_reference_calibrated"]["⑤초호황"], 0.108, places=3)
            h = o["hedge"]
            self.assertEqual(h["reference_hedge"]["삼성중공업 010140 SLS!HEDGE"], 1.0)
            if h["kind"] == "estimate" and h.get("usd_sell_m") and h.get("backlog_krw_m"):
                self.assertIsNotNone(h["hedge_ratio_implied_sign_rate"], o["stock"])
                self.assertGreater(h["implied_sign_n"], 0, o["stock"])
            else:
                self.assertIsNone(h["hedge_ratio_implied_sign_rate"], o["stock"])
            self.assertTrue(any("코호트 OPM 표 reference_calibrated 적용" in w and "--opm-table assumed" in w for w in o["warnings"]), o["stock"])

    def test_opm_table_switch_real_and_determinism(self):
        """--opm-table assumed(이전 기본) 는 타겟·shift 만 바꾸고 매출·환산은 그대로. 같은 입력·today 면 두 번 빌드가 같은 JSON(바이트 결정론)."""
        outs2 = S.run(S.YARDS + [S.HOLDING], write=False, opm_table="assumed", today="2026-10-05")
        for stock, o in self.outs.items():
            oa = outs2[stock]
            self.assertEqual(oa["cohort_opm_table_source"], "assumed")
            self.assertEqual(oa["cohort_opm_table"], oa["cohort_opm_table_assumed"])
            for q, b in o["by_quarter"].items():
                self.assertEqual(oa["by_quarter"][q]["hedged_krw_m"], b["hedged_krw_m"], (stock, q))
                if b["target_opm"] is not None:                                   # reference_anchor 등급(③④⑤)은 전부 캘리브레이션 표가 가정 표보다 낮다
                    self.assertGreater(oa["by_quarter"][q]["target_opm"], b["target_opm"], (stock, q))
        a = S.run(S.YARDS + [S.HOLDING], write=False, today="2026-10-05")
        b = S.run(S.YARDS + [S.HOLDING], write=False, today="2026-10-05")
        for stock in a:
            self.assertEqual(json.dumps(a[stock], ensure_ascii=False), json.dumps(b[stock], ensure_ascii=False), stock)
        self.assertEqual(json.dumps(S.summary(a, "2026Q2", "linear", 1350.0, [], [], today="2026-10-05"), ensure_ascii=False),
                         json.dumps(S.summary(b, "2026Q2", "linear", 1350.0, [], [], today="2026-10-05"), ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
