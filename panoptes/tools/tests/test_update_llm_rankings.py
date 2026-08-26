# -*- coding: utf-8 -*-
"""update_llm_rankings.py 순수 함수 단위 테스트 (네트워크 없음, fixture 기반)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import update_llm_rankings as m  # noqa: E402


class SeriesPackTest(unittest.TestCase):
    def test_pack_sorts_dates_and_fills_missing_with_zero(self):
        rows = [
            {"x": "2026-08-02", "ys": {"a/x": 20, "b/y": 5}},
            {"x": "2026-08-01", "ys": {"a/x": 10}},
        ]
        p = m.series_pack(rows)
        self.assertEqual(p["dates"], ["2026-08-01", "2026-08-02"])
        self.assertEqual(p["series"]["a/x"], [10, 20])
        self.assertEqual(p["series"]["b/y"], [0, 5])  # 결측=0

    def test_pack_empty(self):
        p = m.series_pack([])
        self.assertEqual(p, {"dates": [], "series": {}})

    def test_pack_rounds_floats(self):
        p = m.series_pack([{"x": "2026-08-01", "ys": {"a/x": 1533707645333.3335}}])
        self.assertEqual(p["series"]["a/x"], [1533707645333])


class AggLeaderboardTest(unittest.TestCase):
    def rows(self):
        return [
            {"date": "2026-08-24", "model_permaslug": "a/x", "variant": "standard",
             "total_prompt_tokens": 100, "total_completion_tokens": 10, "count": 3, "change": 0.5},
            {"date": "2026-08-23", "model_permaslug": "a/x", "variant": "standard",
             "total_prompt_tokens": 200, "total_completion_tokens": 20, "count": 4, "change": None},
            {"date": "2026-08-24", "model_permaslug": "a/x", "variant": "free",
             "total_prompt_tokens": 5000, "total_completion_tokens": 0, "count": 1, "change": None},
        ]

    def test_variant_ranked_separately_and_summed(self):
        out = m.agg_leaderboard(self.rows())
        self.assertEqual(out[0]["m"], "a/x")
        self.assertEqual(out[0]["v"], "free")       # 토큰 최대가 1위
        self.assertEqual(out[0]["tok"], 5000)
        std = out[1]
        self.assertEqual((std["pt"], std["ct"], std["rq"], std["tok"]), (300, 30, 7, 330))
        self.assertEqual(std["ch"], 0.5)            # None이 마지막 값을 지우지 않음

    def test_empty(self):
        self.assertEqual(m.agg_leaderboard([]), [])


class FailClosedConstantsTest(unittest.TestCase):
    def test_fetch_source_is_pinned_to_openrouter_https(self):
        self.assertTrue(m.BASE.startswith("https://openrouter.ai/"))

    def test_thresholds_exist(self):
        self.assertGreater(m.MAX_RESP_BYTES, 1024 * 1024)
        self.assertGreaterEqual(m.MAX_WARNINGS, 1)


if __name__ == "__main__":
    unittest.main()
