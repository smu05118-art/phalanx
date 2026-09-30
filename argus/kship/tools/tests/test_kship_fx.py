#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_fx · kship_price 집계 계약 테스트 — 네트워크 없이 합성 일별 자료로 검증한다.

실행: cd argus/kship/tools && python3 -m unittest tests.test_kship_fx
  ① 일별 → 분기 평균/기말(마지막 영업일)·일수, 분기 경계 분리
  ② 교차환율: 원/100엔 = 100 × KRW/JPY, 원/유로 = KRW/EUR, 원/위안 = KRW/CNY — 비율의 평균(평균의 비율 아님)
  ③ partial 판정: 진행 중 분기만 partial, 지난 분기의 ECB 휴장(성금요일)은 partial 아님
  ④ forward: 마지막 완결 분기 다음부터 2028Q4 까지 flat, 진행 중 분기 평균은 분기누적 실측
  ⑤ frankfurter 응답에서 구간 밖 날짜(직전 영업일 끼움) 제거
  ⑥ 시세 일봉 → 분기 기말/고/저/평균 집계(kship_price) — 창은 분기 경계 정렬, 늦게 시작한 분기는 truncated
  ⑦ forward 지평 가드(마지막 완결 분기가 2028Q4 이상이면 무한 루프 대신 빈 예측)
  ⑧ 네이버 일봉 응답 파싱·aik close 대조·요약, 토스 이력 이어붙임(carry_history)
"""
import datetime
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

import kship_fx as FX                                     # noqa: E402
import kship_price as PR                                  # noqa: E402


def _day(krw, jpy=150.0, eur=0.9, cny=7.0):
    return {"KRW": krw, "JPY": jpy, "EUR": eur, "CNY": cny}


class TestCross(unittest.TestCase):
    def test_jpy100_and_others(self):
        c = FX.cross(_day(1500.0, jpy=150.0, eur=0.8, cny=7.5))
        self.assertAlmostEqual(c["USDKRW"], 1500.0)
        self.assertAlmostEqual(c["JPY100KRW"], 1000.0)        # 100 × 1500 / 150
        self.assertAlmostEqual(c["EURKRW"], 1875.0)           # 1500 / 0.8
        self.assertAlmostEqual(c["CNYKRW"], 200.0)            # 1500 / 7.5

    def test_ecb_2026_06_30_reference_point(self):
        """스펙 확인값: 2026-06-30 ECB USDKRW 1550.89, JPY 162.44 → 원/100엔 954.75."""
        c = FX.cross({"KRW": 1550.89, "JPY": 162.44, "EUR": 0.87765, "CNY": 6.7855})
        self.assertEqual(round(c["USDKRW"], 2), 1550.89)
        self.assertEqual(round(c["JPY100KRW"], 2), 954.75)


class TestQuarterize(unittest.TestCase):
    TODAY = datetime.date(2026, 9, 30)

    def _days(self):
        # 2026Q2 3일(평일) + 2026Q3 2일. 분기 경계에서 갈라져야 하고 기말은 마지막 영업일 값.
        return {"2026-06-26": _day(1500.0, jpy=150.0),
                "2026-06-29": _day(1540.0, jpy=154.0),
                "2026-06-30": _day(1550.0, jpy=155.0),
                "2026-07-01": _day(1400.0, jpy=140.0),
                "2026-07-02": _day(1300.0, jpy=130.0)}

    def test_avg_end_days(self):
        q = FX.quarterize(self._days(), today=self.TODAY)
        self.assertEqual(sorted(q), ["2026Q2", "2026Q3"])
        q2 = q["2026Q2"]
        self.assertEqual(q2["days"], 3)
        self.assertEqual(q2["USDKRW_avg"], round((1500 + 1540 + 1550) / 3, 2))
        self.assertEqual(q2["USDKRW_end"], 1550.0)
        self.assertEqual(q2["end_date"], "2026-06-30")
        self.assertFalse(q2["partial"])
        q3 = q["2026Q3"]
        self.assertEqual(q3["USDKRW_avg"], 1350.0)
        self.assertEqual(q3["USDKRW_end"], 1300.0)
        self.assertTrue(q3["partial"])                     # 9/30 값이 없고 오늘이 9/30

    def test_ratio_of_daily_not_ratio_of_avg(self):
        """원/100엔 평균은 일별 교차환율의 평균. KRW/JPY 가 매일 10.0 이면 정확히 1000."""
        q = FX.quarterize(self._days(), today=self.TODAY)
        self.assertEqual(q["2026Q2"]["JPY100KRW_avg"], 1000.0)
        self.assertEqual(q["2026Q2"]["JPY100KRW_end"], 1000.0)
        self.assertEqual(q["2026Q3"]["JPY100KRW_avg"], 1000.0)

    def test_past_quarter_missing_last_weekday_is_not_partial(self):
        """2024Q1 마지막 평일 3/29 는 성금요일(ECB 휴장) — 3/28 로 끝나도 partial 아님."""
        days = {"2024-03-27": _day(1350.0), "2024-03-28": _day(1348.0)}
        q = FX.quarterize(days, today=self.TODAY)
        self.assertEqual(q["2024Q1"]["end_date"], "2024-03-28")
        self.assertFalse(q["2024Q1"]["partial"])
        # 같은 자료라도 '오늘'이 2024-03-29 라면 아직 진행 중
        q = FX.quarterize(days, today=datetime.date(2024, 3, 29))
        self.assertTrue(q["2024Q1"]["partial"])

    def test_annualize(self):
        a = FX.annualize(self._days(), today=self.TODAY)
        self.assertEqual(sorted(a), ["2026"])
        self.assertEqual(a["2026"]["days"], 5)
        self.assertEqual(a["2026"]["USDKRW_end"], 1300.0)
        self.assertTrue(a["2026"]["partial"])

    def test_last_weekday(self):
        self.assertEqual(FX.last_weekday_of_quarter("2026Q2"), "2026-06-30")   # 화
        self.assertEqual(FX.last_weekday_of_quarter("2028Q4"), "2028-12-29")   # 12/31 일요일 → 금
        self.assertEqual(FX.last_weekday_of_quarter("2024Q1"), "2024-03-29")


class TestForward(unittest.TestCase):
    def test_flat_from_next_complete_with_partial_avg(self):
        quarters = {"2026Q2": {"USDKRW_avg": 1500.0, "USDKRW_end": 1550.0, "JPY100KRW_avg": 940.0, "JPY100KRW_end": 950.0,
                               "EURKRW_avg": 1700.0, "EURKRW_end": 1760.0, "CNYKRW_avg": 220.0, "CNYKRW_end": 228.0,
                               "days": 62, "end_date": "2026-06-30", "partial": False},
                    "2026Q3": {"USDKRW_avg": 1420.0, "USDKRW_end": 1353.0, "JPY100KRW_avg": 890.0, "JPY100KRW_end": 861.0,
                               "EURKRW_avg": 1633.0, "EURKRW_end": 1536.0, "CNYKRW_avg": 210.0, "CNYKRW_end": 201.0,
                               "days": 65, "end_date": "2026-09-29", "partial": True}}
        last = {"date": "2026-09-29", "USDKRW": 1353.36, "JPY100KRW": 861.35, "EURKRW": 1536.74, "CNYKRW": 201.89}
        f = FX.forward(quarters, last)
        qs = [k for k in f if k[:2] == "20"]
        self.assertEqual(qs[0], "2026Q3")
        self.assertEqual(qs[-1], "2028Q4")
        self.assertEqual(len(qs), 10)
        self.assertEqual(f["2026Q3"]["USDKRW_avg"], 1420.0)        # 분기누적 실측 평균
        self.assertEqual(f["2026Q3"]["USDKRW_end"], 1353.36)       # 기말은 마지막 관측치
        self.assertEqual(f["2027Q1"]["USDKRW_avg"], 1353.36)
        self.assertEqual(f["2028Q4"]["JPY100KRW_end"], 861.35)
        self.assertTrue(all(f[q]["kind"] == "estimate" and f[q]["basis"] for q in qs))
        self.assertEqual(f["method"], "flat_last_end")

    def test_horizon_guard_no_infinite_loop(self):
        """마지막 완결 분기가 지평(2028Q4)과 같거나 지나면 예측 분기 없이 끝나야 한다(예전 `while True` 는 영원히 돌았다)."""
        base = {"USDKRW_avg": 1.0, "USDKRW_end": 1.0, "JPY100KRW_avg": 1.0, "JPY100KRW_end": 1.0,
                "EURKRW_avg": 1.0, "EURKRW_end": 1.0, "CNYKRW_avg": 1.0, "CNYKRW_end": 1.0, "days": 60, "partial": False}
        last = {"date": "2029-03-30", "USDKRW": 1.0, "JPY100KRW": 1.0, "EURKRW": 1.0, "CNYKRW": 1.0}
        for lastq, end in (("2028Q4", "2028-12-29"), ("2029Q1", "2029-03-30")):
            f = FX.forward({lastq: dict(base, end_date=end)}, last)
            self.assertEqual([k for k in f if k[:2] == "20"], [], lastq)
            self.assertEqual(f["method"], "flat_last_end")
            self.assertIn("예측 분기 없음", f["note"])
        # 2028Q3 이 마지막 완결이면 2028Q4 한 분기만
        f = FX.forward({"2028Q3": dict(base, end_date="2028-09-29")}, last)
        self.assertEqual([k for k in f if k[:2] == "20"], ["2028Q4"])


class TestFetchRange(unittest.TestCase):
    def test_drops_out_of_range_leading_day(self):
        """frankfurter 가 2005-01-01 요청에 2004-12-31 을 끼워 주는 실측 응답 — 구간 밖은 버린다."""
        payload = {"amount": 1.0, "base": "USD", "start_date": "2004-12-31", "end_date": "2005-01-04",
                   "rates": {"2004-12-31": {"CNY": 8.277, "EUR": 0.73416, "JPY": 102.53, "KRW": 1035.2},
                             "2005-01-03": {"CNY": 8.277, "EUR": 0.74036, "JPY": 102.79, "KRW": 1038.1},
                             "2005-01-04": {"CNY": 8.277, "EUR": 0.7507, "JPY": 104.46, "KRW": 1045.0}}}
        with mock.patch.object(FX, "_get", return_value=json.dumps(payload).encode("utf-8")):
            got = FX.fetch_range("2005-01-01", "2005-01-04")
        self.assertEqual(sorted(got), ["2005-01-03", "2005-01-04"])
        self.assertEqual(got["2005-01-03"]["KRW"], 1038.1)

    def test_update_cache_skips_done_years(self):
        """지난 연도 완결 구간은 재요청하지 않고, 올해는 마지막 캐시일부터만 요청한다."""
        cache = {"ranges": [["2025-01-01", "2025-12-31", "2026-09-30"]],
                 "days": {"2025-12-31": _day(1444.0), "2026-09-26": _day(1350.0)}}
        calls = []

        def fake(start, end):
            calls.append((start, end))
            return {"2026-09-29": _day(1353.0)}
        with mock.patch.object(FX, "fetch_range", side_effect=fake), mock.patch.object(FX, "FIRST_YEAR", 2025), \
                mock.patch.object(FX.time, "sleep", lambda *_: None):
            FX.update_cache(cache, datetime.date(2026, 9, 30), log=lambda *_: None)
        self.assertEqual(calls, [("2026-09-26", "2026-09-30")])
        self.assertIn("2026-09-29", cache["days"])
        self.assertEqual(len(cache["ranges"]), 1)              # 올해는 완결 구간으로 기록하지 않는다


class TestPriceHistory(unittest.TestCase):
    def test_quarter_end_high_low_avg(self):
        today = datetime.date(2026, 9, 30)
        candles = [
            {"timestamp": "2026-06-29T00:00:00.000+09:00", "closePrice": "20000", "highPrice": "20500", "lowPrice": "19800"},
            {"timestamp": "2026-06-30T00:00:00.000+09:00", "closePrice": "21000", "highPrice": "21300", "lowPrice": "19900"},
            {"timestamp": "2026-07-01T00:00:00.000+09:00", "closePrice": "19000", "highPrice": "19500", "lowPrice": "18000"},
            {"timestamp": "2019-01-02T00:00:00.000+09:00", "closePrice": "1", "highPrice": "1", "lowPrice": "1"},  # 5년 밖
            {"timestamp": "bad", "closePrice": "x"},
        ]
        h = PR.aggregate_candles(candles, today)
        self.assertEqual(sorted(h), ["2026Q2", "2026Q3"])
        q2 = h["2026Q2"]
        self.assertEqual((q2["close_end"], q2["high"], q2["low"], q2["avg"], q2["days"]), (21000, 21300, 19800, 20500.0, 2))
        self.assertEqual(q2["end_date"], "2026-06-30")
        self.assertFalse(q2["partial"])
        self.assertTrue(h["2026Q3"]["partial"])

    def test_window_aligned_to_quarter_start(self):
        """5년 창은 '5년 전 날짜'가 아니라 그 날짜가 속한 분기의 첫날부터 — 첫 분기가 사흘짜리로 잘리지 않는다.
        실측: 2026-09-30 기준 예전 since=2021-09-27 → 48종목의 2021Q3 가 days=3 이었다."""
        today = datetime.date(2026, 9, 30)
        self.assertEqual(PR.history_since(today), "2021-07-01")
        self.assertEqual(PR.quarter_start("2021Q3"), "2021-07-01")
        self.assertEqual(PR.quarter_start("2026Q1"), "2026-01-01")
        candles = [{"timestamp": "%sT00:00:00.000+09:00" % d, "closePrice": "100", "highPrice": "110", "lowPrice": "90"}
                   for d in ("2021-06-30", "2021-07-01", "2021-08-02", "2021-09-27", "2021-09-28", "2021-09-30", "2021-10-01")]
        h = PR.aggregate_candles(candles, today)
        self.assertEqual(sorted(h), ["2021Q3", "2021Q4"])          # 2021Q2 는 창 밖, 2021Q3 는 7/1 부터 온전히
        self.assertEqual(h["2021Q3"]["days"], 5)
        self.assertNotIn("truncated", h["2021Q3"])
        self.assertNotIn("truncated", h["2021Q4"])                # 10/1 시작 — 정상

    def test_truncated_flag_for_late_start_quarter(self):
        """분기 첫 거래일이 분기 시작 +10일보다 늦으면(상장·자료 시작) truncated — 추석 연휴(+9일)는 아님."""
        today = datetime.date(2026, 9, 30)
        mk = lambda d: {"timestamp": d + "T00:00:00.000+09:00", "closePrice": "100", "highPrice": "100", "lowPrice": "100"}  # noqa: E731
        h = PR.aggregate_candles([mk("2025-12-19"), mk("2025-12-22"), mk("2026-01-02")], today)   # 12월 중순 상장
        self.assertTrue(h["2025Q4"]["truncated"])
        self.assertEqual(h["2025Q4"]["start_date"], "2025-12-19")
        self.assertNotIn("truncated", h["2026Q1"])
        h = PR.aggregate_candles([mk("2017-10-10"), mk("2017-10-11")], datetime.date(2018, 3, 1))  # 2017 추석 뒤 첫 거래일 10/10
        self.assertNotIn("truncated", h["2017Q4"])
        h = PR.aggregate_candles([mk("2017-10-12")], datetime.date(2018, 3, 1))
        self.assertTrue(h["2017Q4"]["truncated"])

    def test_row_of_keeps_spec_fields(self):
        d = {"name_ko": "삼성중공업", "market": "KOSPI", "as_of": "20260928",
             "quote": {"close": 20100, "as_of": "20260928", "shares_outstanding": 880000000, "market_cap_krw": 17688000000000},
             "valuation": {"pe_ttm": 31.8, "pb": 3.76, "basis": {"fs": "연결"}},
             "financials": {"period": "2026H1", "basis": "연결", "revenue": {"current": 1, "prior_year": 2, "yoy_pct": -50.0},
                            "operating_income": {"current": 3}, "net_income": {"current": 4}}}
        r = PR.row_of(d, {"role": "yard"})
        self.assertEqual((r["close"], r["as_of"], r["shares_outstanding"], r["market_cap_krw"]), (20100, "20260928", 880000000, 17688000000000))
        self.assertEqual((r["pe_ttm"], r["pb"], r["role"]), (31.8, 3.76, "yard"))
        self.assertEqual(r["financials_ref"]["period"], "2026H1")
        self.assertEqual((r["financials_ref"]["revenue"], r["financials_ref"]["operating_income"], r["financials_ref"]["net_income"]), (1, 3, 4))

    def test_parse_naver_daily_and_check(self):
        """fchart siseJson 은 작은따옴표 헤더의 JS 배열 — 실측 응답(삼성重 2026-09-28 종가 20,150 vs aik 20,100)."""
        text = ("\n [['날짜', '시가', '고가', '저가', '종가', '거래량', '외국인소진율'],\n"
                '["20260923", 20700, 20750, 20200, 20450, 2307429, 28.21],\n'
                '["20260928", 20400, 20550, 20050, 20150, 2066341, 28.11],\n'
                '["20260929", 20050, 20100, 19160, 19500, 5746198, 27.66]]\n')
        nv = PR.parse_naver_daily(text)
        self.assertEqual(nv, {"20260923": 20450, "20260928": 20150, "20260929": 19500})
        c = PR.naver_check_row(20100, "20260928", nv)
        self.assertEqual((c["aik"], c["naver_close"], c["diff_pct"]), (20100, 20150, -0.248))
        c = PR.naver_check_row(20100, "20260927", nv)                # 휴장일 — 기준일 행 없음
        self.assertIsNone(c["diff_pct"])
        self.assertIn("없음", c["note"])
        self.assertEqual(PR.parse_naver_daily(""), {})
        with mock.patch.object(PR, "_get", return_value=text.encode("utf-8")) as g:
            got = PR.fetch_naver_daily("010140", "20260928")
        self.assertEqual(got["20260928"], 20150)
        self.assertIn("startTime=20260914&endTime=20260928", g.call_args[0][0])
        rows = {"010140": {"naver_check": c}, "075580": {"naver_check": {"diff_pct": 0.0, "aik": 9990, "naver_close": 9990}},
                "133820": {"naver_check": {"diff_pct": -4.228, "aik": 974, "naver_close": 1017}}, "999999": {"error": "x"}}
        rows["010140"]["naver_check"] = PR.naver_check_row(20100, "20260928", nv)
        sm = PR.naver_summary(rows)
        self.assertEqual((sm["checked_n"], sm["equal_n"], sm["abs_gt_1pct_n"]), (3, 1, 1))
        self.assertEqual(sm["max_abs"]["stock"], "133820")

    def test_carry_history_from_previous_file(self):
        """토스 이력을 못 만든 행(--no-history·러너)에는 기존 prices.json 의 history_quarterly 를 이어 붙인다 — error 행·이미 있는 행은 건너뜀."""
        prev = {"as_of": "2026-09-30", "rows": {
            "010140": {"history_quarterly": {"2026Q2": {"close_end": 23450}}, "history_meta": {"source": "toss", "candles": 3}},
            "075580": {"history_quarterly": {"2026Q2": {"close_end": 13370}}, "history_meta": {"carried_from": "2026-09-20"}},
            "042660": {"history_unavailable": True}}}
        out = {"rows": {"010140": {"close": 19330, "history_unavailable": True, "history_error": "--no-history"},
                        "075580": {"close": 9700, "history_unavailable": True, "history_error": "--no-history"},
                        "042660": {"close": 80000, "history_unavailable": True, "history_error": "--no-history"},
                        "329180": {"close": 1, "history_quarterly": {"2026Q2": {"close_end": 1}}},
                        "009540": {"error": "404"}}, "history": {"attempted": False}}
        n = PR.carry_history(out, prev)
        self.assertEqual(n, 2)
        r = out["rows"]["010140"]
        self.assertEqual(r["history_quarterly"], {"2026Q2": {"close_end": 23450}})
        self.assertEqual(r["history_meta"]["carried_from"], "2026-09-30")
        self.assertEqual(r["history_meta"]["candles"], 3)
        self.assertTrue(r["history_carried"])
        self.assertNotIn("history_unavailable", r)
        self.assertEqual(out["rows"]["075580"]["history_meta"]["carried_from"], "2026-09-20")   # 기존 carried_from 유지
        self.assertTrue(out["rows"]["042660"]["history_unavailable"])                              # prev 에도 이력 없음
        self.assertEqual(out["rows"]["329180"]["history_quarterly"], {"2026Q2": {"close_end": 1}})  # 새 이력은 그대로
        self.assertNotIn("history_quarterly", out["rows"]["009540"])
        self.assertEqual(out["history"]["carried_n"], 2)
        self.assertEqual(PR.carry_history({"rows": {"010140": {"close": 1}}}, None), 0)

    def test_roster_has_56_folders_plus_holding(self):
        m = PR.roster()
        self.assertIn("009540", m)
        self.assertIn("075580", m)
        self.assertGreaterEqual(len(m), 57)
        self.assertTrue(all(len(k) == 6 and k.isdigit() for k in m))


if __name__ == "__main__":
    unittest.main()
