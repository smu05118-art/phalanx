# -*- coding: utf-8 -*-
"""생산능력·생산실적·가동률 파서 계약 — 실제 DART 원문 fixture(2026Q2 반기·2025Q4 사업보고서) 8건."""
import glob
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import kcap_capacity as C          # noqa: E402
from kcap_lib import unit_of       # noqa: E402

FX = os.path.join(HERE, "fixtures")


def parsed(stock, q):
    with open(os.path.join(FX, "cap_%s_%s.html" % (stock, q)), encoding="utf-8") as f:
        return C.parse_section(f.read(), q)


def row(p, product, entity=None, site=None):
    for r in p["products"]:
        if r["product_raw"] == product and (entity is None or entity in r["entity"]) and (site is None or r["site"] == site):
            return r
    raise AssertionError("row not found: %s %s %s" % (product, entity, site))


class TestUnits(unittest.TestCase):
    def test_unit_of(self):
        self.assertEqual(unit_of("(단위 : 톤, 매)")[1], 1.0)
        self.assertEqual(unit_of("(단위 : M/T")[1], 1.0)              # 닫는 괄호가 잘린 캡션
        self.assertEqual(unit_of("(단위 : 천톤)")[1], 1000.0)
        self.assertEqual(unit_of("(단위 : 1,000MT)")[1], 1000.0)        # DL — 천단위 쉼표를 항목 구분자로 자르지 않는다
        self.assertEqual(unit_of("(단위 : 천MT)")[1], 1000.0)           # 금호
        self.assertEqual(unit_of("(단위 : 수량(1,000kg)")[1], 1.0)      # 대한화섬
        self.assertIsNone(unit_of("(단위 : kg)")[1])
        self.assertIsNone(unit_of("(단위 : MT/일)")[1])
        self.assertIsNone(unit_of("(단위 : 식, ton)")[1])
        self.assertEqual(unit_of("(단위 : 이차전지소재 톤 | 화학 톤)")[1], 1.0)
        self.assertEqual(unit_of("(단위 : 톤/년)")[1], 1.0)
        self.assertIsNone(unit_of("(단위 : T/H)")[1])
        self.assertIsNone(unit_of("(단위 : 천배럴)")[1])
        self.assertIsNone(unit_of("(단위 : 백만원)")[1])


class TestLotteChem(unittest.TestCase):
    def test_half_year_prorated(self):
        p = parsed("011170", "2026Q2")
        self.assertEqual(len(p["products"]), 18)
        nc = row(p, "NC", entity="롯데케미칼(주)")
        self.assertEqual(nc["capacity_period"], 1760500.0)
        self.assertEqual(nc["capacity_ton_annual"], 3521000.0)
        self.assertEqual(nc["util_pct"], 60.7)
        self.assertTrue(nc["basis"].startswith("기간비례"))
        self.assertEqual(nc["prev_annual_ton"], 3521000.0)
        self.assertEqual(row(p, "NC", entity="LC TITAN")["capacity_ton_annual"], 1299000.0)
        self.assertTrue(all(r["is_ton"] for r in p["products"]))

    def test_annual_report(self):
        p = parsed("011170", "2025Q4")
        nc = row(p, "NC", entity="롯데케미칼(주)")
        self.assertEqual(nc["capacity_ton_annual"], 3521000.0)
        self.assertEqual(nc["util_pct"], 73.0)
        self.assertTrue(nc["basis"].startswith("연간 명판"))
        self.assertEqual(row(p, "MEG", entity="LC USA")["output_period"], 605894.0)


class TestKoreaPetrochemical(unittest.TestCase):
    def test_separate_tables_and_aggregate_util(self):
        p = parsed("006650", "2026Q2")
        self.assertEqual(row(p, "Ethylene")["capacity_ton_annual"], 900000.0)
        self.assertEqual(row(p, "HDPE")["capacity_ton_annual"], 650000.0)
        self.assertIsNone(row(p, "Propylene")["util_pct"])
        agg = row(p, "기초유분 및모노머")
        self.assertTrue(agg["aggregate"])
        self.assertEqual(agg["util_pct"], 70.63)
        self.assertEqual(agg["output_period"], 756128.0)


class TestKumho(unittest.TestCase):
    def test_unit_column_and_subsidiaries(self):
        p = parsed("011780", "2026Q2")
        r = row(p, "합성고무")
        self.assertEqual(r["capacity_ton_annual"], 913000.0)
        self.assertTrue(r["basis"].startswith("연간 명판"))
        self.assertEqual(r["util_pct"], 85.4)            # 반기 생산실적 390 ÷ (연간 913 × 6/12) — 연간 명판 분모를 기간에 맞춘다
        self.assertEqual(r["util_src"], "computed(6개월 분모)")
        self.assertEqual(row(p, "BD")["util_pct"], 13.5)
        self.assertEqual(row(p, "CUMENE")["capacity_ton_annual"], 900000.0)
        self.assertEqual(row(p, "EPDM")["capacity_ton_annual"], 310000.0)
        self.assertEqual(row(p, "EPDM")["util_pct"], 63.9)   # 99/(310×6/12)


class TestOthers(unittest.TestCase):
    def test_huchems_single_header_row(self):
        p = parsed("069260", "2026Q2")
        self.assertEqual(len(p["products"]), 2)      # 유형자산(백만원) 표는 제품이 아니다
        self.assertEqual(row(p, "NT계열")["capacity_ton_annual"], 984000.0)
        self.assertEqual(row(p, "NT계열")["util_pct"], 85.0)

    def test_lotte_fine_dedup(self):
        p = parsed("004000", "2026Q2")
        rows = [r for r in p["products"] if r["product_raw"] == "가성소다(50%)"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["capacity_ton_annual"], 747928.0)
        self.assertEqual(rows[0]["util_pct"], 102.4)
        self.assertEqual(rows[0]["site"], "본사")

    def test_soil_nameplate_and_nonton(self):
        p = parsed("010950", "2026Q2")
        poly = row(p, "Polymer")
        self.assertEqual(poly["capacity_ton_annual"], 540000.0)
        self.assertEqual(poly["nameplate_ton"], 765000.0)
        self.assertEqual(poly["util_pct"], 76.2)
        ref = row(p, "정유부문")
        self.assertFalse(ref["is_ton"])
        self.assertEqual(ref["util_pct"], 87.4)
        self.assertEqual(ref["output_period"], 98008.0)

    def test_skc(self):
        p = parsed("011790", "2026Q2")
        self.assertEqual(row(p, "SM")["capacity_ton_annual"], 394000.0)
        self.assertEqual(row(p, "SM")["util_pct"], 95.1)
        self.assertEqual(row(p, "POD")["capacity_ton_annual"], 496000.0)

    def test_all_fixtures_parse_without_exception(self):
        for f in glob.glob(os.path.join(FX, "cap_*.html")):
            q = os.path.basename(f).split("_")[2].split(".")[0]
            with open(f, encoding="utf-8") as fh:
                p = C.parse_section(fh.read(), q)
            self.assertGreater(p["tables"], 0, f)


if __name__ == "__main__":
    unittest.main()
