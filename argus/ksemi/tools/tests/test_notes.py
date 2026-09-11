# -*- coding: utf-8 -*-
"""계약: 매출인식 기준 · 주요 고객(당기 전용) — III 주석 원문 대조.

대조 기준은 PROGRESS.md §1 4행(원익IPS 2025 사업보고서, rcpNo 20260316001453):
- ① 주석 3-18 「고객과의 계약에서 생기는 수익」 → 인식기준 **설치완료(SAT)**,
  원문 인용은 **fixture 안에 실재하는 문자열**이어야 한다(지어내지 않는다).
- ② 주석 6 영업부문 「주요 고객에 대한 공시」 → 익명 A사 당기 445,603,489천원,
  부문합계 909,795,691천원 → 최대고객 **49.0%**.

CRITICAL(COMMON.md §2): 주석 표는 **당기·전기 비교표가 나란히** 온다. 전기 표를
더하면 값이 두 배가 된다(삼성중공업 헤지 사고와 같은 종류). 이 fixture 의 전기 A사는
360,414,012천원이라, 더해지면 445,603.489 → 806,017.501 이 된다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C                                          # noqa: E402

import ksemi_parse as P                                      # noqa: E402
import ksemi_reports as R                                    # noqa: E402

# 원문 인용 — fixture 에 그대로 들어 있는 문자열(테스트가 먼저 실재를 확인한다).
QUOTE = "자산에 대한 통제가 고객에게 이전되는 시점인 설치완료 시점에 인식됩니다"

# 주석 6 주요 고객(천원) → 백만원
CUR = {"A사": 445603.489, "B사": 101278.112, "C사": 95623.918}
PRIOR_A = 360414.012                       # 전기 A사 — 더해지면 안 되는 값
SEGMENT_TOTAL = 909795.691                 # 부문합계(기업 전체 총계 합계)
TOP_SHARE = 49.0


class TestRevenueBasis(unittest.TestCase):
    def setUp(self):
        self.html = C.fixture(C.ACC_WONIK)
        self.b = P.revenue_basis(self.html)

    def test_quote_exists_in_the_source(self):
        """인용은 원문에 실재하는 문자열이어야 한다 — 먼저 fixture 에서 확인한다."""
        self.assertIn(QUOTE, self.html)
        self.assertIn("고객과의 계약에서 생기는 수익", self.html)

    def test_primary_basis_is_installation_complete(self):
        self.assertTrue(self.b["found"])
        self.assertTrue(self.b["scoped"], "수익 주석 앵커를 못 찾으면 문단이 엉뚱해진다")
        self.assertEqual(self.b["primary"], "설치완료")

    def test_basis_carries_the_source_quote(self):
        top = self.b["bases"][0]
        self.assertEqual(top["key"], "설치완료")
        self.assertIn(QUOTE, top["quote"])
        # 인용은 원문(태그 제거·공백 정규화)에 실재하는 문장이다.
        flat = P._txt(__import__("re").sub(r"<[^>]+>", " ", self.html))
        self.assertIn(top["quote"], flat)

    def test_no_basis_is_not_guessed(self):
        """어느 낱말도 안 걸리면 추정하지 않는다(빈칸으로 남긴다)."""
        b = P.revenue_basis("<p>해당 사항 없음</p>")
        self.assertFalse(b["found"])
        self.assertIsNone(b["primary"])
        self.assertEqual(b["bases"], [])


class TestCustomers(unittest.TestCase):
    """익명 고객 · 당기 전용."""

    def _check(self, name):
        c = P.customers(C.fixture(name))
        self.assertTrue(c["found"], name)
        self.assertTrue(c["unit_seen"], name)
        self.assertEqual(c["period"], "당기", name)
        self.assertTrue(c["anonymous"], "A사·B사·C사 — 익명이면 익명이라 적는다")
        got = {r["label"]: r["amount"] for r in c["rows"]}
        self.assertEqual(got, CUR, name)
        return c

    def test_separate_statement_note(self):
        self._check(C.SEG_WONIK)

    def test_consolidated_statement_note(self):
        self._check(C.SEG_WONIK_CONN)

    def test_prior_period_is_not_summed(self):
        """전기 표가 같은 절에 실재하는데도 당기 값만 나와야 한다."""
        html = C.fixture(C.SEG_WONIK)
        self.assertIn("360,414,012", html, "전기 표가 fixture 에 없으면 이 계약이 아니다")
        c = P.customers(html)
        a = [r for r in c["rows"] if r["label"] == "A사"][0]
        self.assertEqual(a["amount"], CUR["A사"])
        self.assertNotEqual(a["amount"], PRIOR_A)
        self.assertNotEqual(a["amount"], CUR["A사"] + PRIOR_A)   # 806,017.501
        self.assertEqual(len(c["rows"]), 3, "전기 표까지 담으면 행이 6개가 된다")

    def test_prior_period_table_first_is_skipped(self):
        """전기 표가 **먼저** 오는 원문 배치에서도 당기만 쓴다."""
        html = _CUSTOMER_TABLES_PRIOR_FIRST
        c = P.customers(html)
        self.assertTrue(c["found"])
        self.assertEqual(c["period"], "당기")
        self.assertGreaterEqual(c["skipped_prior"], 1, "전기 표를 건너뛴 기록이 없다")
        self.assertEqual({r["label"]: r["amount"] for r in c["rows"]}, CUR)


class TestSegmentTotal(unittest.TestCase):
    def test_consolidated_note_gives_the_denominator(self):
        st = P.segment_revenue(C.fixture(C.SEG_WONIK_CONN))
        self.assertEqual(st["total"], SEGMENT_TOTAL)
        self.assertIn("합계", st["quote"])

    def test_customer_table_is_never_mistaken_for_a_segment_table(self):
        """별도 주석은 부문 표가 없다 — 마지막 고객(C사)을 전체 매출로 읽으면 안 된다."""
        st = P.segment_revenue(C.fixture(C.SEG_WONIK))
        self.assertIsNone(st["total"], "분모를 추정하지 않는다(비중을 안 쓴다)")
        self.assertNotEqual(st["total"], CUR["C사"])


class TestTopCustomerShare(unittest.TestCase):
    """화면 KPI 까지 내려간 값이 원문과 같은가 — 최대고객 49.0%."""

    def test_kpi_top_customer_share(self):
        c = P.customers(C.fixture(C.SEG_WONIK_CONN))
        st = P.segment_revenue(C.fixture(C.SEG_WONIK_CONN))
        rec = {"quarters": {}, "customers": {"rows": c["rows"]},
               "segment_total": st}
        k = R.kpi(rec)
        self.assertEqual(k["top_customer"], "A사")
        self.assertEqual(k["top_customer_share"], TOP_SHARE)

    def test_share_would_double_if_prior_were_summed(self):
        """회귀 방지: 전기를 더하면 88.6% 가 되어 한눈에 틀린 값이 된다."""
        rec = {"quarters": {},
               "customers": {"rows": [{"label": "A사",
                                       "amount": CUR["A사"] + PRIOR_A}]},
               "segment_total": {"total": SEGMENT_TOTAL}}
        self.assertNotEqual(R.kpi(rec)["top_customer_share"], TOP_SHARE)


# 전기 표가 먼저 오는 배치(원문 숫자 그대로). 회사에 따라 순서가 뒤집힌다.
_CUSTOMER_TABLES_PRIOR_FIRST = u"""
<p>6. 영업부문 주요 고객에 대한 공시 전기 (단위 : 천원)</p>
<table><tr><th></th><th>A사</th><th>B사</th><th>C사</th></tr>
<tr><td>수익(매출액)</td><td>360,414,012</td><td>98,932,573</td><td></td></tr></table>
<p>주요 고객에 대한 공시 당기 (단위 : 천원)</p>
<table><tr><th></th><th>A사</th><th>B사</th><th>C사</th></tr>
<tr><td>수익(매출액)</td><td>445,603,489</td><td>101,278,112</td><td>95,623,918</td></tr></table>
"""


if __name__ == "__main__":
    unittest.main()
