#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_watch 감지 로직 테스트 (네트워크 없이).

새 분기 판정과 검색 창 계산만 검증한다 — DART 조회는 Action이 실제로 수행하므로
여기서는 네트워크를 타지 않는다.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
KCE = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

import kce_watch as KW  # noqa: E402
from kce_lib import CORP, extract_data, q_next  # noqa: E402


class TestNextQuarter(unittest.TestCase):

    def test_next_quarter_follows_data(self):
        """감지 대상 분기는 각 회사 DATA의 마지막 분기 다음이어야 한다."""
        for co in CORP:
            D = extract_data(os.path.join(KCE, co, "index.html"))
            self.assertEqual(KW.next_quarter(co), q_next(D["fq"][-1]), co)

    def test_search_window_covers_filing_deadline(self):
        """검색 창이 법정 제출기한을 포함해야 한다.
        분기·반기는 분기말 +45일, 사업보고서는 +90일."""
        cases = {
            "2026Q1": ("20260301", "20260628"),
            "2026Q2": ("20260601", "20260928"),
            "2026Q3": ("20260901", "20261228"),
            "2026Q4": ("20261201", "20270428"),   # 사업보고서는 이듬해 3월말 접수
        }
        for q, want in cases.items():
            self.assertEqual(KW._window(q), want, q)


class TestRunShape(unittest.TestCase):
    """run()이 네트워크 실패를 회사 단위로 격리하는지(다른 회사를 막지 않는지)."""

    def test_search_failure_is_isolated(self):
        orig = KW.search_reports

        def boom(*a, **k):
            raise RuntimeError("네트워크 차단")
        KW.search_reports = boom
        try:
            res = KW.run(["sct", "hec"], apply=False)
        finally:
            KW.search_reports = orig
        self.assertEqual(len(res["failed"]), 2)
        self.assertEqual(res["updated"], [])
        # 두 회사 모두 시도됐다 — 첫 실패에서 멈추지 않는다
        self.assertEqual({f["co"] for f in res["failed"]}, {"sct", "hec"})


if __name__ == "__main__":
    unittest.main()
