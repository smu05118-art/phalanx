# -*- coding: utf-8 -*-
"""계약: 핵심 표 1종의 원문 대조 + 합계/소계 판정(COMMON.md §2 · §4).

대조 기준은 PROGRESS.md §1 3행(원익IPS 2026 반기 II-4 다. 수주상황):
단위 백만원 · 행 `반도체/Display 장비` · 수주총액 1,197,393 / 기납품 562,803 /
잔고 634,590. 이 세 숫자가 화면 KPI(잔고·수주)의 출처다.

합계 행은 **버리지 않고** `total=True` 로 남긴다(COMMON §2 — 합계 셀이 깨진 원문이
실제로 있다). 남기되 품목 행과 **같이 더하면 안 된다** — 원익IPS·한미반도체 두 원문
모두 합계가 유일한 품목 행과 같은 값이라 두 배가 된다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C                                          # noqa: E402

import ksemi_parse as P                                      # noqa: E402

# 원익IPS 2026 반기 수주상황 — 원문 숫자(백만원)
WONIK_ITEM = "반도체/Display 장비"
WONIK_AMT, WONIK_CMP, WONIK_BAL = 1197393, 562803, 634590
# 원익IPS 2026 반기 II-4 가. 매출실적 (2) 별도기준 합계 행 (백만원, 제11기 반기)
WONIK_EXPORT, WONIK_DOMESTIC, WONIK_TOTAL = 100875, 280520, 381395


class TestIsTotal(unittest.TestCase):
    def test_sum_labels(self):
        for s in ("합계", "합 계", "소계", "소 계", "총계", "계", "부문합계"):
            self.assertTrue(P.is_total(s), s)

    def test_item_labels_are_not_totals(self):
        for s in (WONIK_ITEM, "합계액", "A사", "PE-CVD외", ""):
            self.assertFalse(P.is_total(s), s)


class TestWonikOrders(unittest.TestCase):
    """원익IPS 총액형 수주상황표 — 원문 대조."""

    def setUp(self):
        self.o = P.orders(C.fixture(C.II4_WONIK))

    def test_unit_is_million_won_from_the_caption(self):
        self.assertTrue(self.o["unit_seen"])
        self.assertEqual(len(self.o["tables"]), 1)
        unit = self.o["tables"][0]["unit"]
        self.assertEqual(unit["scale"], 1.0)
        self.assertEqual(unit["raw"], "백만원")

    def test_item_row_matches_source(self):
        rows = [r for r in self.o["tables"][0]["rows"] if not r["total"]]
        self.assertEqual(len(rows), 1, rows)
        r = rows[0]
        self.assertEqual(r["nm"], WONIK_ITEM)
        self.assertEqual(r["sd"], "2026년 반기")
        self.assertEqual((r["amt"], r["cmp"], r["bal"]),
                         (WONIK_AMT, WONIK_CMP, WONIK_BAL))

    def test_total_row_is_kept_not_dropped(self):
        totals = [r for r in self.o["tables"][0]["rows"] if r["total"]]
        self.assertEqual(len(totals), 1, "합계 행이 사라졌다")
        self.assertEqual((totals[0]["amt"], totals[0]["cmp"], totals[0]["bal"]),
                         (WONIK_AMT, WONIK_CMP, WONIK_BAL))

    def test_headline_is_not_double_counted(self):
        """합계 행 + 품목 행을 같이 더하면 두 배가 된다 — 합계 행을 신뢰한다."""
        self.assertEqual(self.o["order_amt"], WONIK_AMT)
        self.assertEqual(self.o["delivered"], WONIK_CMP)
        self.assertEqual(self.o["backlog"], WONIK_BAL)
        self.assertNotEqual(self.o["backlog"], WONIK_BAL * 2)
        self.assertIsNone(self.o["recon"], "합계와 품목합이 어긋나면 recon 에 남는다")

    def test_disclosed_and_grain(self):
        self.assertTrue(self.o["disclosed"])
        self.assertEqual(self.o["grain"], "item")
        self.assertEqual(self.o["unknown_headers"], [])

    def test_backlog_in_eok(self):
        """화면 표기(억원)까지 내려가도 원문과 같다 — 634,590 백만원 = 6,346억."""
        from ksemi_lib import fmt_eok
        self.assertEqual(fmt_eok(self.o["backlog"]), "6,346")


class TestHanmiOrders(unittest.TestCase):
    """한미반도체 단일계약형 — 같은 절인데 표 모양이 전혀 다르다(PROGRESS §1-5)."""

    def setUp(self):
        self.html = C.fixture(C.II4_HANMI)
        self.o = P.orders(self.html)

    def test_single_contract_row(self):
        rows = [r for tb in self.o["tables"] for r in tb["rows"] if not r["total"]]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sd"], "2026-06-08")
        self.assertEqual(rows[0]["ed"], "2026-09-02")
        self.assertEqual(rows[0]["amt"], 44200)

    def test_total_row_kept_and_not_added_twice(self):
        totals = [r for tb in self.o["tables"] for r in tb["rows"] if r["total"]]
        self.assertEqual(len(totals), 1, "합계 행이 사라졌다")
        self.assertEqual(totals[0]["amt"], 44200)
        # 실사고: 합계 행을 품목 행으로 세어 44,200 → 88,400 이 된 적이 있다.
        self.assertEqual(self.o["order_amt"], 44200)
        self.assertNotEqual(self.o["order_amt"], 88400)

    def test_undisclosed_columns_stay_empty(self):
        """기납품·잔고 칸이 `-` 다 — 0 으로 채우지 않는다(미공시는 빈칸)."""
        self.assertIsNone(self.o["backlog"])
        self.assertIsNone(self.o["delivered"])

    def test_source_quote_for_non_disclosure_exists(self):
        """미공시 사유는 지어내지 않고 원문 문구가 실재해야 한다."""
        self.assertIn("고객의 투자 정보 등이 노출될 수 있어", self.html)


class TestWonikSales(unittest.TestCase):
    """II-4 가. 매출실적 — 수출/내수(별도기준, 백만원). 원문 합계 행과 대조."""

    def setUp(self):
        self.s = P.sales(C.fixture(C.II4_WONIK))

    def test_export_domestic_match_source(self):
        self.assertTrue(self.s["unit_seen"])
        self.assertEqual(self.s["channel_kind"], "수출내수")
        self.assertEqual(self.s["period_label"], "제11기 반기")
        self.assertEqual(self.s["export"], WONIK_EXPORT)
        self.assertEqual(self.s["domestic"], WONIK_DOMESTIC)
        self.assertEqual(self.s["total"], WONIK_TOTAL)
        self.assertEqual(self.s["export"] + self.s["domestic"], WONIK_TOTAL)
        self.assertIsNone(self.s["recon"])

    def test_all_unit_captions_were_read(self):
        """연결(천원) · 별도(백만원) 두 벌이 같이 온다 — 표마다 단위를 읽는다."""
        scales = sorted({tb["unit"]["scale"] for tb in self.s["tables"]})
        self.assertEqual(scales, [0.001, 1.0])
        self.assertTrue(all(tb["unit"]["seen"] for tb in self.s["tables"]))

    def test_export_share(self):
        from ksemi_lib import pct
        self.assertEqual(round(pct(self.s["export"], self.s["total"]), 1), 26.4)


if __name__ == "__main__":
    unittest.main()
