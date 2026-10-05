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
  ⑧ 네이버 일봉 응답 파싱·aik close 대조·요약, 이력 이어붙임(carry_history)
  ⑨ (2026-10-05 V2) 네이버 5년 일봉 → 이력: 무거래일(거래량 0·시고저 0) 제외, 거래정지 분기는 비움, listed 전 구간 표기
  ⑩ (V2) 종가 정본 규칙 apply_close_rule: 네이버 최신 거래일로 as_of 전진·aik 원값 보존·시총 재계산·네이버 없으면 aik 유지
  ⑪ (V2) ECB 캐시: 지난 연도 응답이 비거나 짧으면 완결 구간으로 기록하지 않음(영구 결손 방지) · --only 병합 뒤 요약 재계산
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

    def test_update_cache_does_not_mark_empty_or_short_past_year_done(self):
        """지난 연도 응답이 비거나(HTTP 200·rates 없음) 짧으면 ranges 에 적지 않아 다음 실행이 다시 받는다 — 적어 두면 그 해가 영구히 빈다.
        정상(≥200일) 연도는 기록한다."""
        def fake(start, end):
            y = start[:4]
            if y == "2024":
                return {}                                                     # 빈 응답
            if y == "2025":
                return {"2025-01-%02d" % d: _day(1400.0) for d in range(2, 12)}   # 10일만
            return {"%s-%02d-%02d" % (y, m, d): _day(1300.0) for m in range(1, 13) for d in range(1, 22)}  # 252일
        cache = {"ranges": [], "days": {}}
        logs = []
        with mock.patch.object(FX, "fetch_range", side_effect=fake), mock.patch.object(FX, "FIRST_YEAR", 2023), \
                mock.patch.object(FX.time, "sleep", lambda *_: None):
            FX.update_cache(cache, datetime.date(2026, 10, 5), log=logs.append)
        self.assertEqual([tuple(r[:2]) for r in cache["ranges"]], [("2023-01-01", "2023-12-31")])
        self.assertTrue(any("2024-01-01..2024-12-31 응답 0일" in s for s in logs))
        self.assertTrue(any("2025-01-01..2025-12-31 응답 10일" in s for s in logs))
        self.assertIn("2025-01-02", cache["days"])                              # 받은 날은 버리지 않는다
        # 다음 실행: 2023 은 건너뛰고 2024·2025 는 다시 요청한다
        calls = []
        with mock.patch.object(FX, "fetch_range", side_effect=lambda s, e: calls.append((s, e)) or {}), \
                mock.patch.object(FX, "FIRST_YEAR", 2023), mock.patch.object(FX.time, "sleep", lambda *_: None):
            FX.update_cache(cache, datetime.date(2026, 10, 5), log=lambda *_: None)
        self.assertEqual([c[0][:4] for c in calls], ["2024", "2025", "2026"])


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
        # end= 를 주면 기준일 뒤(최신 거래일 탐지용)까지 받는다
        with mock.patch.object(PR, "_get", return_value=text.encode("utf-8")) as g:
            PR.fetch_naver_daily("010140", "20260928", end=datetime.date(2026, 10, 5))
        self.assertIn("startTime=20260914&endTime=20261005", g.call_args[0][0])

    # ── ⑨ 네이버 5년 일봉 → 이력 ──
    NV_5Y = ("[['날짜', '시가', '고가', '저가', '종가', '거래량', '외국인소진율'],\n"
             '["20210701", 6342, 6380, 6229, 6305, 5370046, 14.19],\n'
             '["20210723", 0, 0, 0, 6173, 0, 13.78],\n'                       # 거래정지 자리표시(시고저 0, 종가 전일 복사)
             '["20210726", 0, 0, 0, 6173, 0, 13.79],\n'
             '["20210927", 6100, 6150, 6050, 6120, 1000000, 14.0],\n'
             '["20210930", 6200, 6250, 6000, 6180, 1200000, 14.0],\n'
             '["20211012", 1880, 1880, 1880, 1880, 0, 1.87],\n'              # 무거래일(전일 종가 복사, 거래량 0) — 분기 유일 행
             '["20220103", 7000, 7300, 6900, 7200, 900000, 15.0],\n'
             '["bad", 1, 2, 3, 4, 5, 6],\n'
             '["20220104", "x", 7300, 6900, 7200, 900000, 15.0]]\n')         # 숫자 아닌 값 — 건너뜀

    def test_parse_naver_rows_and_no_trade_filter(self):
        rows = PR.parse_naver_rows(self.NV_5Y)
        self.assertEqual([r["date"] for r in rows], ["20210701", "20210723", "20210726", "20210927", "20210930", "20211012", "20220103"])
        self.assertEqual(rows[0], {"date": "20210701", "open": 6342, "high": 6380, "low": 6229, "close": 6305, "volume": 5370046})
        self.assertTrue(PR.is_no_trade(rows[1]) and PR.is_no_trade(rows[5]))
        self.assertFalse(PR.is_no_trade(rows[0]))
        self.assertTrue(PR.is_no_trade({"date": "20210101", "high": 0, "low": 0, "close": 1, "volume": None}))   # 거래량 없는 응답
        cands, dropped = PR.naver_candles(rows)
        self.assertEqual(dropped, 3)
        self.assertEqual([c["timestamp"] for c in cands], ["2021-07-01", "2021-09-27", "2021-09-30", "2022-01-03"])
        self.assertEqual(PR.parse_naver_daily(self.NV_5Y)["20210723"], 6173)       # 종가 지도는 무거래일 포함(aik 도 같은 값을 싣는다)

    def test_history_from_rows_drops_suspended_quarter_and_flags_pre_listed(self):
        """무거래일만 있는 분기(2021Q4)는 비운다 — 토스 이력처럼 764원 × 62일짜리 가짜 평균가를 만들지 않는다.
        2021Q3 는 거래정지 2일을 뺀 3일·고 6380·저 6000·기말 6180. listed(2022-01-03) 전 분기는 pre_listed_quarters 로 표기만."""
        rows = PR.parse_naver_rows(self.NV_5Y)
        hist, meta = PR.history_from_rows(rows, datetime.date(2022, 2, 1), listed="2022-01-03")
        self.assertEqual(sorted(hist), ["2021Q3", "2022Q1"])                    # 2021Q4 없음(무거래 1행만)
        q3 = hist["2021Q3"]
        self.assertEqual((q3["close_end"], q3["high"], q3["low"], q3["days"], q3["end_date"]), (6180, 6380, 6000, 3, "2021-09-30"))
        self.assertEqual(q3["avg"], round((6305 + 6120 + 6180) / 3, 1))
        self.assertFalse(q3.get("partial"))
        self.assertTrue(hist["2022Q1"]["partial"])
        self.assertEqual((meta["rows"], meta["no_trade_dropped"], meta["from"], meta["to"]), (7, 3, "20210701", "20220103"))
        self.assertEqual(meta["pre_listed_quarters"], ["2021Q3"])
        self.assertEqual(meta["listed"], "2022-01-03")
        self.assertEqual(meta["window_from"], "2017-01-01")
        # 전부 무거래면 이력 없음 + 사유
        hist, meta = PR.history_from_rows(PR.parse_naver_rows(self.NV_5Y)[1:3], datetime.date(2022, 2, 1))
        self.assertIsNone(hist)
        self.assertIn("무거래", meta["error"])
        self.assertIsNone(PR.history_from_rows([], datetime.date(2022, 2, 1))[0])

    def test_fetch_naver_history_url_window(self):
        """5년 창 시작(분기 첫날) ~ 오늘 한 요청 — 2026-10-05 기준 20211001..20261005."""
        with mock.patch.object(PR, "_get", return_value=self.NV_5Y.encode("utf-8")) as g:
            rows = PR.fetch_naver_history("010140", datetime.date(2026, 10, 5))
        self.assertIn("symbol=010140&requestType=1&startTime=20211001&endTime=20261005&timeframe=day", g.call_args[0][0])
        self.assertEqual(len(rows), 7)

    # ── ⑩ 종가 정본 규칙 ──
    def _row(self):
        return {"close": 19720, "as_of": "20261001", "open": 19720, "high": 19810, "low": 19350, "volume": 2004100,
                "shares_outstanding": 880000000, "market_cap_krw": 17353600000000, "trading_status": "traded"}

    def _nv(self):
        return PR.parse_naver_rows(
            "[['날짜', '시가', '고가', '저가', '종가', '거래량', '외국인소진율'],\n"
            '["20260930", 19750, 20200, 19650, 19840, 3449094, 27.76],\n'
            '["20261001", 19720, 19810, 19350, 19740, 2004100, 27.73],\n'
            '["20261002", 19760, 19980, 19640, 19920, 1922545, 27.73],\n'
            '["20261006", 1, 1, 1, 1, 1, 1]]\n')                                      # 미래 행(오늘 뒤) — 무시

    def test_close_rule_advances_to_naver_latest(self):
        """실측(2026-10-04 러너): aik as_of 10/1 19,720 · 네이버 10/1 19,740 · 10/2 19,920 → close 19,920 · as_of 20261002 · aik 원값 보존."""
        r = PR.apply_close_rule(self._row(), self._nv(), datetime.date(2026, 10, 5))
        self.assertEqual((r["close"], r["as_of"], r["close_source"]), (19920, "20261002", "naver_regular_close"))
        self.assertTrue(r["as_of_source"].startswith("naver_latest"))
        self.assertIn("1거래일", r["as_of_source"])
        self.assertEqual((r["aik_close"], r["aik_as_of"]), (19720, "20261001"))
        self.assertEqual(r["aik_quote"]["high"], 19810)
        self.assertEqual((r["open"], r["high"], r["low"], r["volume"], r["trading_status"]), (19760, 19980, 19640, 1922545, "traded"))
        self.assertEqual(r["market_cap_krw"], 19920 * 880000000)
        self.assertEqual(r["market_cap_krw_aik"], 17353600000000)
        self.assertEqual((r["naver_check"]["date"], r["naver_check"]["naver_close"], r["naver_check"]["diff_pct"]), ("20261001", 19740, -0.101))

    def test_close_rule_same_day_and_missing(self):
        # 네이버 최신 = aik 기준일 → 전진 없음, close 만 네이버로
        r = PR.apply_close_rule(self._row(), self._nv()[:2], datetime.date(2026, 10, 1))
        self.assertEqual((r["close"], r["as_of"], r["as_of_source"], r["aik_close"]), (19740, "20261001", "aik_same_day", 19720))
        self.assertNotIn("aik_quote", r)
        self.assertEqual(r["high"], 19810)                                              # aik 시고저 유지
        # 오늘(10/1)까지만 본다 — 10/2 행이 있어도 today 가 10/1 이면 전진하지 않는다
        r = PR.apply_close_rule(self._row(), self._nv(), datetime.date(2026, 10, 1))
        self.assertEqual(r["as_of"], "20261001")
        # 네이버 없음 → aik 유지
        r = PR.apply_close_rule(self._row(), None, datetime.date(2026, 10, 5))
        self.assertEqual((r["close"], r["as_of"], r["as_of_source"]), (19720, "20261001", "aik"))
        self.assertTrue(r["close_source"].startswith("aik_close"))
        self.assertNotIn("aik_close", r)
        # 네이버가 aik 기준일 행은 없고 더 최신만 있을 때(aik 기준일이 네이버 휴장 처리) — 대조 None, 전진은 한다
        r = PR.apply_close_rule(self._row(), self._nv()[2:], datetime.date(2026, 10, 5))
        self.assertIsNone(r["naver_check"]["diff_pct"])
        self.assertEqual((r["close"], r["as_of"]), (19920, "20261002"))
        # 거래정지 종목: 네이버 최신 행이 무거래(거래량 0)면 trading_status no_trade, 종가는 복사된 전일 종가
        susp = PR.parse_naver_rows("[['날짜','시가','고가','저가','종가','거래량','외국인소진율'],\n"
                                   '["20261001", 0, 0, 0, 764, 0, 0.33],\n["20261002", 0, 0, 0, 764, 0, 0.33]]')
        r = PR.apply_close_rule(dict(self._row(), close=764, shares_outstanding=1000), susp, datetime.date(2026, 10, 5))
        self.assertEqual((r["close"], r["as_of"], r["trading_status"], r["market_cap_krw"]), (764, "20261002", "no_trade", 764000))
        self.assertEqual((r["open"], r["high"], r["low"]), (None, None, None))

    def test_in_progress_day_guard(self):
        """장중(10:40 KST)에는 오늘 행을 종가·이력에 넣지 않는다 — 15:40 KST 이후나 과거 --today 는 넣는다. 오늘 뒤 행은 항상 뺀다."""
        rows = PR.parse_naver_rows("[['날짜','시가','고가','저가','종가','거래량','외국인소진율'],\n"
                                   '["20261002", 19760, 19980, 19640, 19920, 1922545, 27.73],\n'
                                   '["20261005", 20000, 20300, 19900, 20250, 500000, 27.7],\n'
                                   '["20261006", 1, 1, 1, 1, 1, 1]]')
        today = datetime.date(2026, 10, 5)
        self.assertEqual([r["date"] for r in PR.drop_in_progress_day(rows, today, False)], ["20261002"])
        self.assertEqual([r["date"] for r in PR.drop_in_progress_day(rows, today, True)], ["20261002", "20261005"])
        self.assertEqual(PR.drop_in_progress_day(None, today, True), [])
        mk = lambda h, mi: datetime.datetime(2026, 10, 5, h, mi, tzinfo=PR.KST)                           # noqa: E731
        self.assertFalse(PR.include_today_closes(today, now=mk(10, 40)))                                 # 러너 시각
        self.assertFalse(PR.include_today_closes(today, now=mk(15, 39)))
        self.assertTrue(PR.include_today_closes(today, now=mk(15, 40)))
        self.assertTrue(PR.include_today_closes(datetime.date(2026, 10, 2), now=mk(10, 40)))             # 과거 --today
        # collect 에서 include_today=False 면 오늘 행이 있어도 as_of 는 전 거래일
        aik = {"name_ko": "x", "quote": {"close": 19720, "as_of": "20261001", "shares_outstanding": 10}, "valuation": {}}
        nv = ("[['날짜','시가','고가','저가','종가','거래량','외국인소진율'],\n"
              '["20261001", 19720, 19810, 19350, 19740, 2004100, 27.73],\n'
              '["20261002", 19760, 19980, 19640, 19920, 1922545, 27.73],\n'
              '["20261005", 20000, 20300, 19900, 20250, 500000, 27.7]]')
        fake = lambda url, *a, **k: json.dumps(aik).encode("utf-8") if "aikstockdata" in url else nv.encode("utf-8")  # noqa: E731
        with mock.patch.object(PR, "_get", side_effect=fake), mock.patch.object(PR.time, "sleep", lambda *_: None):
            out = PR.collect(["010140"], {"010140": {"name": "x", "role": "yard"}}, today, log=lambda *_: None, include_today=False)
            r = out["rows"]["010140"]
            self.assertEqual((r["close"], r["as_of"], r["history_quarterly"]["2026Q4"]["close_end"], r["history_quarterly"]["2026Q4"]["days"]),
                             (19920, "20261002", 19920, 2))
            self.assertEqual(out["run"], {"today": "2026-10-05", "include_today_closes": False, "note": out["run"]["note"]})
            out = PR.collect(["010140"], {"010140": {"name": "x", "role": "yard"}}, today, log=lambda *_: None, include_today=True)
            r = out["rows"]["010140"]
            self.assertEqual((r["close"], r["as_of"], r["history_quarterly"]["2026Q4"]["days"]), (20250, "20261005", 3))

    def test_naver_summary_counts_sources_and_refresh_counts(self):
        rows = {"A": {"close_source": "naver_regular_close", "as_of_source": "naver_latest(aik 기준일 20261001 보다 1거래일 최신)", "as_of": "20261002",
                      "naver_check": {"diff_pct": -0.1}},
                "B": {"close_source": "naver_regular_close", "as_of_source": "aik_same_day", "as_of": "20261001", "naver_check": {"diff_pct": 0.0}},
                "C": {"close_source": "aik_close(네이버 기준일 종가 없음)", "as_of_source": "aik", "as_of": "20261001", "naver_check": {"diff_pct": None}},
                "D": {"error": "404"}}
        sm = PR.naver_summary(rows)
        self.assertEqual(sm["close_source_n"], {"naver_regular_close": 2, "aik_close(네이버 기준일 종가 없음)": 1})
        self.assertEqual((sm["as_of_advanced_n"], sm["as_of_n"], sm["checked_n"], sm["equal_n"]), (1, {"20261002": 1, "20261001": 2}, 2, 1))
        out = {"rows": rows}
        PR.refresh_counts(out)
        self.assertEqual((out["roster_n"], out["ok_n"], out["error_n"], out["errors"]), (4, 3, 1, ["D"]))
        self.assertEqual(out["naver_check"]["as_of_advanced_n"], 1)
        PR.refresh_counts(out, naver=False)
        self.assertTrue(out["naver_check"]["skipped"])

    def test_collect_uses_one_naver_request_per_stock(self):
        """aik 1 + 네이버 5년 일봉 1 요청으로 이력·종가 규칙·대조를 모두 만든다(토스 없음)."""
        aik = {"name_ko": "삼성중공업", "license": {"id": "x"}, "citation": "c",
               "quote": {"close": 19720, "as_of": "20261001", "open": 19720, "high": 19810, "low": 19350, "volume": 2004100,
                         "shares_outstanding": 880000000, "market_cap_krw": 17353600000000}, "valuation": {}}
        nv = ("[['날짜','시가','고가','저가','종가','거래량','외국인소진율'],\n"
              '["20260630", 24600, 24800, 23300, 23300, 4048562, 28.76],\n'
              '["20260930", 19750, 20200, 19650, 19840, 3449094, 27.76],\n'
              '["20261001", 19720, 19810, 19350, 19740, 2004100, 27.73],\n'
              '["20261002", 19760, 19980, 19640, 19920, 1922545, 27.73]]')
        urls = []

        def fake_get(url, *a, **k):
            urls.append(url)
            return json.dumps(aik).encode("utf-8") if "aikstockdata" in url else nv.encode("utf-8")
        with mock.patch.object(PR, "_get", side_effect=fake_get), mock.patch.object(PR.time, "sleep", lambda *_: None):
            out = PR.collect(["010140"], {"010140": {"name": "삼성중공업", "role": "yard", "listed": "1994-01-28"}},
                             datetime.date(2026, 10, 5), log=lambda *_: None)
        self.assertEqual(len(urls), 2)
        self.assertIn("startTime=20211001&endTime=20261005", urls[1])
        r = out["rows"]["010140"]
        self.assertEqual((r["close"], r["as_of"], r["aik_close"], r["close_source"]), (19920, "20261002", 19720, "naver_regular_close"))
        self.assertEqual(sorted(r["history_quarterly"]), ["2026Q2", "2026Q3", "2026Q4"])
        self.assertEqual(r["history_quarterly"]["2026Q2"]["close_end"], 23300)
        self.assertEqual(r["history_meta"]["source"], PR.HISTORY_SOURCE)
        self.assertNotIn("pre_listed_quarters", r["history_meta"])
        self.assertEqual((out["history"]["attempted"], out["history"]["available_n"], out["ok_n"]), (True, 1, 1))
        self.assertEqual(out["naver_check"]["as_of_advanced_n"], 1)
        self.assertEqual(out["close_rule"], PR.CLOSE_RULE)
        # 네이버 실패 → aik 값 유지 + naver_error, 이력 없음(이어붙임은 호출자)
        def fail_get(url, *a, **k):
            if "aikstockdata" in url:
                return json.dumps(aik).encode("utf-8")
            raise RuntimeError("timeout")
        with mock.patch.object(PR, "_get", side_effect=fail_get), mock.patch.object(PR.time, "sleep", lambda *_: None):
            out = PR.collect(["010140"], {"010140": {"name": "삼성중공업", "role": "yard"}}, datetime.date(2026, 10, 5), log=lambda *_: None)
        r = out["rows"]["010140"]
        self.assertEqual((r["close"], r["as_of"], r["as_of_source"]), (19720, "20261001", "aik"))
        self.assertTrue(r["history_unavailable"])
        self.assertIn("timeout", r["naver_error"])
        self.assertEqual(out["history"]["failed_n"], 1)

    def test_carry_history_from_previous_file(self):
        """이력을 못 만든 행(--no-history·네이버 실패)에는 기존 prices.json 의 history_quarterly 를 이어 붙인다 — error 행·이미 있는 행은 건너뜀."""
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
