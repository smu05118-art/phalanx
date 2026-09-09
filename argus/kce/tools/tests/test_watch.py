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


class TestApiFallback(unittest.TestCase):
    """키가 있어도 OpenAPI가 실패하면 웹 검색으로 폴백해야 한다(조용히는 아니게)."""

    def test_falls_back_to_web_on_api_error(self):
        import kce_fetch as KF
        calls = {"api": 0, "web": 0}

        def api_boom(*a, **k):
            calls["api"] += 1
            raise RuntimeError("010 등록되지 않은 인증키입니다.")

        def web_ok(*a, **k):
            calls["web"] += 1
            return [("20260814002969", "반기보고서 (2026.06)")]

        o_key, o_api, o_web = KW.api_key, KW.api_reports, KW.search_reports
        KW.api_key = lambda: "DUMMY"
        KW.api_reports, KW.search_reports = api_boom, web_ok
        try:
            reports, via = KW.list_reports("sct", "2026Q2")
        finally:
            KW.api_key, KW.api_reports, KW.search_reports = o_key, o_api, o_web
        self.assertEqual(via, "web")
        self.assertEqual(calls, {"api": 1, "web": 1})
        self.assertEqual(reports[0][0], "20260814002969")

    def test_uses_api_when_key_works(self):
        def api_ok(*a, **k):
            return [("20260814002969", "반기보고서 (2026.06)")]

        def web_should_not_run(*a, **k):
            raise AssertionError("API가 성공했는데 웹 검색이 호출됐다")

        o_key, o_api, o_web = KW.api_key, KW.api_reports, KW.search_reports
        KW.api_key = lambda: "DUMMY"
        KW.api_reports, KW.search_reports = api_ok, web_should_not_run
        try:
            reports, via = KW.list_reports("sct", "2026Q2")
        finally:
            KW.api_key, KW.api_reports, KW.search_reports = o_key, o_api, o_web
        self.assertEqual(via, "api")
        self.assertEqual(reports[0][0], "20260814002969")


class TestLinkInjection(unittest.TestCase):
    """argus/index.html의 진입 링크는 크론이 덮어쓰므로 재주입이 멱등해야 한다."""

    def setUp(self):
        import inject_kce_link
        self.I = inject_kce_link

    def test_injects_after_mock_badge(self):
        html = ('<header>\n  <span id="mockBadge">MOCK DATA</span>\n'
                '  <span class="disc">참고용</span>\n</header>')
        out, changed = self.I.inject(html)
        self.assertTrue(changed)
        self.assertIn('href="kce/index.html"', out)
        self.assertLess(out.index("mockBadge"), out.index("kce/index.html"))
        self.assertLess(out.index("kce/index.html"), out.index('class="disc"'))

    def test_idempotent(self):
        html = '<header><span id="mockBadge">MOCK DATA</span></header>'
        once, _ = self.I.inject(html)
        twice, changed = self.I.inject(once)
        self.assertFalse(changed)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count("kce/index.html"), 1)

    def test_falls_back_to_disc_anchor(self):
        html = '<header><span class="disc">참고용</span></header>'
        out, changed = self.I.inject(html)
        self.assertTrue(changed)
        self.assertLess(out.index("kce/index.html"), out.index('class="disc"'))

    def test_raises_when_no_anchor(self):
        with self.assertRaises(RuntimeError):
            self.I.inject("<header><h1>ARGUS</h1></header>")

    def test_live_file_has_link(self):
        """실제 argus/index.html에 링크가 살아 있어야 한다(크론이 지웠으면 실패)."""
        with open(self.I.TARGET, encoding="utf-8") as f:
            self.assertTrue(self.I.has_link(f.read()),
                            "argus/index.html에 한국건설 링크가 없다 — "
                            "python3 inject_kce_link.py --apply 로 복구하라")


class TestRetry(unittest.TestCase):
    """DART는 연속 요청에 약하다 — 일시적 오류는 재시도로 흡수해야 한다.

    2026-09-06 스케줄 실행에서 7사 전부 `urlopen error timed out`으로 실패했다.
    """

    def setUp(self):
        import kce_fetch
        self.KF = kce_fetch
        self.orig_backoff = kce_fetch.BACKOFF
        self.orig_gap = kce_fetch.MIN_GAP
        kce_fetch.BACKOFF = (0, 0, 0)          # 테스트에서 실제로 기다리지 않는다
        kce_fetch.MIN_GAP = 0

    def tearDown(self):
        self.KF.BACKOFF = self.orig_backoff
        self.KF.MIN_GAP = self.orig_gap

    def test_retries_transient_error_then_succeeds(self):
        calls = {"n": 0}

        class FakeResp:
            def read(self, n):
                return b"OK"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def flaky(req, timeout=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise OSError("timed out")
            return FakeResp()

        orig = self.KF.urllib.request.urlopen
        self.KF.urllib.request.urlopen = flaky
        try:
            body = self.KF._get("https://dart.fss.or.kr/x")
        finally:
            self.KF.urllib.request.urlopen = orig
        self.assertEqual(body, b"OK")
        self.assertEqual(calls["n"], 3)          # 2번 실패 후 3번째 성공

    def test_gives_up_after_retries(self):
        def always_fail(req, timeout=None):
            raise OSError("timed out")

        orig = self.KF.urllib.request.urlopen
        self.KF.urllib.request.urlopen = always_fail
        try:
            with self.assertRaises(OSError):
                self.KF._get("https://dart.fss.or.kr/x")
        finally:
            self.KF.urllib.request.urlopen = orig

    def test_does_not_retry_allowlist_violation(self):
        with self.assertRaises(ValueError):
            self.KF._get("https://evil.example.com/x")


if __name__ == "__main__":
    unittest.main()
