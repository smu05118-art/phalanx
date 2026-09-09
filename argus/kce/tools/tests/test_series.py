#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""신규 편입사 시계열 빌더(kce_series) 회귀 테스트."""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

import kce_series as KS                                   # noqa: E402


class TestTotalRow(unittest.TestCase):
    """소계 판별. 뚫리면 수주잔고가 몇 배로 부푼다(금호건설 9.5조 → 42.8조)."""

    def test_real_subtotal_labels(self):
        for nm in ("합계", "총 계", "소계", "국내합계(C=A+B)", "총계(E=C+D)",
                   "국내건축(관급+민간) 합계(B)", "국내토목 계(A)",
                   "국내건축 민간공사 계", "해외 소계", "누계", "합계 - 전체"):
            self.assertTrue(KS.is_total_row({"nm": nm}), nm)

    def test_project_names_are_not_subtotals(self):
        """'계'로 끝나는 실제 공사명을 소계로 오인하면 현장이 통째로 사라진다."""
        for nm in ("○○ 기본설계", "신안산선 실시설계", "부산항 신항 토목설계",
                   "의왕군포안산A1-1", "봉명3구역 주택재개발정비사업",
                   "평택~부여~익산 고속도로민자사업1단계", "월곶~판교 복선전철 제9공구",
                   "세계로교회 신축공사", "통계센터 리모델링",
                   "○○ 종합계획 수립용역", "강릉~제진 철도건설 제8공구 노반신설 기타",
                   "동교동 기린동산빌라 소규모재건축사업"):
            self.assertFalse(KS.is_total_row({"nm": nm}), nm)

    def test_remainder_rows_are_aggregate_not_subtotal(self):
        """'기타현장'은 중복이 아니라 **나머지**다 — 빼면 총계가 안 맞는다."""
        for nm in ("기타", "기타현장", "기타 프로젝트", "그 외", "그밖"):
            self.assertFalse(KS.is_total_row({"nm": nm}), nm)
            self.assertTrue(KS.is_agg_row({"nm": nm}), nm)
        for nm in ("기타 프로젝트 신축공사", "강릉~제진 철도 노반신설 기타"):
            self.assertFalse(KS.is_agg_row({"nm": nm}), nm)

    def test_empty_is_not_subtotal(self):
        self.assertFalse(KS.is_total_row({"nm": ""}))
        self.assertFalse(KS.is_total_row({}))


class TestNameKey(unittest.TestCase):
    def test_spacing_and_suffix_variants_match(self):
        a = KS.nm_key("힐스테이트 OO 신축공사")
        for v in ("힐스테이트 OO 신축 공사", "힐스테이트OO신축공사",
                  "힐스테이트 OO 신축공사 ", "힐스테이트·OO 신축공사"):
            self.assertEqual(KS.nm_key(v), a, v)

    def test_distinct_projects_stay_distinct(self):
        self.assertNotEqual(KS.nm_key("광명시흥 A2-5"), KS.nm_key("광명시흥 A1-1"))

    def test_all_suffix_name_survives(self):
        # 이름이 접미어뿐이면 빈 키가 되지 않아야 한다(현장이 서로 합쳐진다)
        self.assertTrue(KS.nm_key("공사"))


class TestNormDate(unittest.TestCase):
    def test_dialects(self):
        for raw, want in [("2019.12", "2019-12"), ("2019-12-01", "2019-12"),
                          ("201506", "2015-06"), ("24년12월", "2024-12"),
                          ("25.12", "2025-12"), ("2022.12", "2022-12"),
                          ("2024-03-26", "2024-03")]:
            self.assertEqual(KS._norm_date(raw), want, raw)

    def test_unparseable(self):
        for raw in ("", "-", "착공일로부터24개월", "미정"):
            self.assertIsNone(KS._norm_date(raw), raw)

    def test_month_is_clamped(self):
        self.assertEqual(KS._norm_date("2024.99"), "2024-12")


class TestBuild(unittest.TestCase):
    """캐시 → DATA. 소계 분리·분기 연결·집계를 합성 데이터로 검증."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._old, KS.CACHE = KS.CACHE, self.tmp
        self.rec = {"stock": "999999", "name": "테스트건설", "slug": "999999",
                    "market": "유가", "industry": "토목 건설업"}

    def tearDown(self):
        KS.CACHE = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _put(self, quarter, rows, ok=True, tables=None):
        p = KS.cache_path("999999", quarter)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        rec = {"stock": "999999", "quarter": quarter, "ok": ok,
               "note": "", "rcpNo": "2026" + "0" * 10, "rows": rows,
               "grain": "project"}
        if tables is not None:
            rec["tables"] = tables
            rec["rows"] = [r for t in tables for r in t["rows"]]
        with open(p, "w", encoding="utf-8") as f:
            json.dump(rec, f)

    def _row(self, nm, amt, cmp_, bal, cl="발주처", sd="2024.01", ed="2027.12"):
        return {"nm": nm, "cl": cl, "sd": sd, "ed": ed,
                "amt": amt, "cmp": cmp_, "bal": bal}

    def test_remainder_row_kept_in_total_but_flagged(self):
        """묶음 행은 집계에 남기고 현장으로는 세지 않는다 — 총계가 맞아야 한다."""
        self._put("2026Q1", [
            self._row("가현장", 1000, 400, 600),
            self._row("기타현장", 2000, 500, 1500),
            self._row("합 계", 3000, 900, 2100, cl="합 계"),
        ])
        D = KS.build(self.rec, ["2026Q1"])
        self.assertEqual(D["summary"]["bal"][0], D["declared"][0], "총계가 안 맞는다")
        flags = {s["nm"]: s["agg"] for s in D["sites"]}
        self.assertEqual(flags, {"가현장": False, "기타현장": True})

    def test_disjoint_tables_sum_their_own_totals(self):
        """`1) 공공부문`·`2) 민간부문`처럼 겹치지 않는 표는 총계를 **더해야** 한다.

        표를 한 덩어리로 합치면 표마다 있는 `기타`가 이름으로 병합돼 하나만 남고,
        총계는 최댓값 하나만 잡혀 잔고가 어긋난다(한신공영 123% 실사례).
        """
        self._put("2026Q1", None, tables=[
            {"lead": "1) 공공부문", "rows": [
                self._row("공공가현장", 1000, 400, 600),
                self._row("기타", 900, 300, 600),
                self._row("합계", 1900, 700, 1200, cl="합계")]},
            {"lead": "2) 민간부문", "rows": [
                self._row("민간가현장", 3000, 1000, 2000),
                self._row("기타", 1500, 500, 1000),
                self._row("합계", 4500, 1500, 3000, cl="합계")]},
        ])
        D = KS.build(self.rec, ["2026Q1"])
        self.assertEqual(D["declared"][0], 4200, "표별 총계를 더하지 않았다")
        self.assertEqual(D["summary"]["bal"][0], 4200, "표별 기타가 병합됐다")
        self.assertEqual(D["reconOver"], [])
        # 표마다의 `기타`는 서로 다른 행으로 남아야 한다
        aggs = [s for s in D["sites"] if s["agg"]]
        self.assertEqual(len(aggs), 2, "표별 묶음 행이 하나로 합쳐졌다")

    def test_same_name_within_one_table_is_deduped(self):
        """한 표 안의 같은 이름은 연결/별도 중복 게재다 — 큰 쪽만 남긴다."""
        self._put("2026Q1", None, tables=[
            {"lead": "표", "rows": [
                self._row("가현장", 1000, 300, 700),
                self._row("가현장", 900, 280, 620)]},
        ])
        D = KS.build(self.rec, ["2026Q1"])
        self.assertEqual(len(D["sites"]), 1)
        self.assertEqual(D["summary"]["bal"][0], 700)

    def test_legacy_cache_without_tables_still_builds(self):
        """표 경계가 없는 옛 캐시도 한 표로 보고 그대로 처리한다."""
        self._put("2026Q1", [self._row("가현장", 1000, 300, 700)])
        D = KS.build(self.rec, ["2026Q1"])
        self.assertEqual(D["summary"]["bal"][0], 700)

    def test_division_subtotals_excluded(self):
        """태영건설 `토목본부-국내` 류는 개별 현장을 다 적고도 함께 실린 소계다."""
        for nm in ("토목본부-전체", "토목본부-국내", "건축본부-해외",
                   "플랜트사업부 - 합계", "건축부문-국내"):
            self.assertTrue(KS.is_total_row({"nm": nm}), nm)
        for nm in ("본부이전 신축공사", "국내 물류센터 신축"):
            self.assertFalse(KS.is_total_row({"nm": nm}), nm)

    def test_threshold_bucket_is_aggregate(self):
        for nm in ("계약잔액 50억 미만", "100억 미만 현장"):
            self.assertTrue(KS.is_agg_row({"nm": nm}), nm)

    def test_reconciliation_flags_overcount(self):
        """수록 합이 공시 총계를 넘으면 중복 계상이다 — 조용히 넘어가면 안 된다."""
        # 소계를 현장으로 오인한 상황을 흉내 낸다: 총계 2100인데 합이 4200
        self._put("2026Q1", [
            self._row("가현장", 1000, 400, 600),
            self._row("나현장", 2000, 500, 1500),
            self._row("국내소계 위장", 3000, 900, 2100),      # 소계로 안 잡히는 이름
            self._row("합계", 3000, 900, 2100, cl="합계"),
        ])
        D = KS.build(self.rec, ["2026Q1"])
        self.assertEqual(D["reconOver"], ["2026Q1"])
        self.assertGreater(D["recon"][0], 102.0)

    def test_reconciliation_ok_when_detail_is_partial(self):
        """상세표에 일부만 실린 건 정상이다 — 경고를 내면 안 된다."""
        self._put("2026Q1", [
            self._row("가현장", 1000, 400, 600),
            self._row("합계", 5000, 1500, 3500, cl="합계"),
        ])
        D = KS.build(self.rec, ["2026Q1"])
        self.assertEqual(D["reconOver"], [])
        self.assertLess(D["recon"][0], 100.0)

    def test_subtotal_excluded_and_kept_as_declared(self):
        self._put("2026Q1", [
            self._row("가현장", 1000, 400, 600),
            self._row("나현장", 2000, 500, 1500),
            self._row("합계", 3000, 900, 2100, cl="합계"),
        ])
        D = KS.build(self.rec, ["2026Q1"])
        self.assertEqual(len(D["sites"]), 2, "소계가 현장으로 섞였다")
        self.assertEqual(D["summary"]["bal"][0], 2100)
        self.assertEqual(D["declared"][0], 2100)

    def test_sites_linked_across_quarters(self):
        self._put("2026Q1", [self._row("가 현장 신축공사", 1000, 300, 700)])
        self._put("2026Q2", [self._row("가현장 신축 공사", 1000, 450, 550)])
        D = KS.build(self.rec, ["2026Q1", "2026Q2"])
        self.assertEqual(len(D["sites"]), 1, "같은 현장이 분기마다 새로 생겼다")
        self.assertEqual(D["sites"][0]["s"]["bal"], [700, 550])
        self.assertEqual(D["sites"][0]["s"]["cmp"], [300, 450])

    def test_duplicate_name_in_quarter_takes_larger(self):
        """연결·별도 표를 함께 실으면 같은 현장이 두 번 나온다 — 합산하면 두 배가 된다."""
        self._put("2026Q1", [self._row("가현장", 1000, 300, 700),
                             self._row("가현장", 900, 280, 620)])
        D = KS.build(self.rec, ["2026Q1"])
        self.assertEqual(len(D["sites"]), 1)
        self.assertEqual(D["summary"]["bal"][0], 700)

    def test_progress_derived_when_absent(self):
        self._put("2026Q1", [self._row("가현장", 1000, 250, 750)])
        D = KS.build(self.rec, ["2026Q1"])
        self.assertAlmostEqual(D["sites"][0]["s"]["pr"][0], 25.0, places=1)

    def test_missing_quarter_is_skipped_not_padded(self):
        self._put("2026Q1", [self._row("가현장", 1000, 300, 700)])
        self._put("2026Q2", [], ok=False)
        D = KS.build(self.rec, ["2026Q1", "2026Q2"])
        self.assertEqual(D["fq"], ["2026Q1"])

    def test_no_data_is_fail_closed(self):
        with self.assertRaises(RuntimeError):
            KS.build(self.rec, ["2026Q1"])

    def test_region_split(self):
        self._put("2026Q1", [self._row("국내 도로공사", 1000, 300, 700),
                             self._row("해외 플랜트 EPC", 2000, 500, 1500)])
        D = KS.build(self.rec, ["2026Q1"])
        self.assertEqual(D["dom"][0], 700)
        self.assertEqual(D["ovs"][0], 1500)

    def test_series_length_matches_axis(self):
        self._put("2026Q1", [self._row("가현장", 1000, 300, 700)])
        self._put("2026Q2", [self._row("나현장", 500, 100, 400)])
        D = KS.build(self.rec, ["2026Q1", "2026Q2"])
        n = len(D["fq"])
        for s in D["sites"]:
            for f in ("amt", "cmp", "bal", "pr"):
                self.assertEqual(len(s["s"][f]), n, (s["id"], f))
        for f in ("amt", "cmp", "bal"):
            self.assertEqual(len(D["summary"][f]), n)
        for g in D["segList"]:
            self.assertEqual(len(D["seg"][g]), n)


class TestGeneratedPages(unittest.TestCase):
    """생성된 신규사 페이지의 계약 — 데이터가 있을 때만."""

    KCE = os.path.dirname(TOOLS)

    def test_pages_have_data_and_no_raw_script_break(self):
        import kce_lib
        base = os.path.join(TOOLS, "assets", "series_cache")
        if not os.path.isdir(base):
            self.skipTest("시계열 캐시 없음")
        checked = 0
        for stock in sorted(os.listdir(base)):
            p = os.path.join(self.KCE, stock, "index.html")
            if not os.path.exists(p):
                continue
            D = kce_lib.extract_data(p)
            self.assertEqual(D["stock"], stock)
            self.assertTrue(D["fq"], stock)
            n = len(D["fq"])
            for s in D["sites"]:
                self.assertEqual(len(s["s"]["bal"]), n, (stock, s["id"]))
            with open(p, encoding="utf-8") as f:
                html = f.read()
            # DATA 블롭 안의 `</script>`는 페이지를 통째로 깨뜨린다
            head = html[:html.index("</script>", html.index("const DATA"))]
            self.assertNotIn("</script", head[head.index("const DATA"):])
            checked += 1
        if not checked:
            self.skipTest("생성된 신규사 페이지 없음")


if __name__ == "__main__":
    unittest.main()


class TestLatestQuarter(unittest.TestCase):
    """정기보고서 접수 지연을 감안한 최신 분기. 너무 앞서면 전 종목이 '보고서 없음'."""

    def test_known_dates(self):
        import datetime
        from kce_lib import latest_quarter
        for day, want in [("2026-09-10", "2026Q2"),   # Q2말 +50일 지남
                          ("2026-08-20", "2026Q2"),   # 경계 직후
                          ("2026-08-18", "2026Q1"),   # 경계 직전 — 앞서 나가지 않는다
                          ("2026-05-25", "2026Q1"),
                          ("2026-04-01", "2025Q3"),   # Q4는 +95일이라 아직 이르다
                          ("2027-04-10", "2026Q4")]:
            self.assertEqual(latest_quarter(datetime.date.fromisoformat(day)),
                             want, day)


class TestParallel(unittest.TestCase):
    """레인 유틸 — 순서 보존과 예외 격리가 깨지면 데이터가 뒤섞인다."""

    def test_order_preserved(self):
        import kce_fetch
        import random
        import time as _t

        def slow(x):
            _t.sleep(random.random() * 0.02)
            return x * 2

        items = list(range(40))
        self.assertEqual(kce_fetch.parallel(items, slow, lanes=8),
                         [x * 2 for x in items])

    def test_failure_is_isolated_not_fatal(self):
        import kce_fetch

        def maybe(x):
            if x % 3 == 0:
                raise ValueError("boom %d" % x)
            return x

        out = kce_fetch.parallel(list(range(9)), maybe, lanes=4)
        self.assertEqual([type(o).__name__ for o in out],
                         ["ValueError", "int", "int"] * 3)

    def test_single_lane_matches_parallel(self):
        import kce_fetch
        f = lambda x: x + 1                                   # noqa: E731
        self.assertEqual(kce_fetch.parallel(list(range(20)), f, lanes=1),
                         kce_fetch.parallel(list(range(20)), f, lanes=8))

    def test_global_rate_gate_holds_under_lanes(self):
        """레인을 늘려도 **총 요청률**은 1/MIN_GAP를 넘지 않아야 한다."""
        import kce_fetch
        import time as _t
        old, kce_fetch.MIN_GAP = kce_fetch.MIN_GAP, 0.02
        kce_fetch._last_call[0] = 0.0
        try:
            n = 30
            t0 = _t.monotonic()
            kce_fetch.parallel(list(range(n)), lambda _x: kce_fetch._pace(), lanes=10)
            dt = _t.monotonic() - t0
        finally:
            kce_fetch.MIN_GAP = old
        self.assertGreaterEqual(dt, (n - 1) * 0.02 * 0.8,
                                "레인이 전역 요청률 상한을 뚫었다")
