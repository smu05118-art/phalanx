#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국조선 파이프라인 계약 테스트.

실행: cd argus/kship/tools && python3 -m unittest discover -s tests
원문 픽스처: HD현대중공업 2026 반기 수주상황(부문 롤포워드)·척당 계약 공시(LPGC 4척).
"""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, TOOLS)

import kship_lib as L                                     # noqa: E402
from kship_parse import parse_orders, unit_of, is_total   # noqa: E402
from kship_contracts import parse_contract, ship_type_of  # noqa: E402
from kship_yards import parse_orders_table, parse_revenue_table  # noqa: E402
from kship_suppliers import classify_product              # noqa: E402


def _fx(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class TestUnits(unittest.TestCase):
    def test_currency_and_scale(self):
        self.assertEqual(unit_of("(단위 : 백만달러, 척)"), ("USD", 1.0, True))
        self.assertEqual(unit_of("(단위 : 천달러)"), ("USD", 0.001, True))
        self.assertEqual(unit_of("(단위 : 억원)"), ("KRW", 100.0, True))
        self.assertEqual(unit_of("", ["(단위 : 천원) 품목"]), ("KRW", 0.001, True))
        self.assertEqual(unit_of("")[2], False)          # 단위를 못 읽으면 unit_seen=False

    def test_total_rows(self):
        for s in ("합 계", "합계", "총계", "소계"):
            self.assertTrue(is_total(s), s)
        for s in ("조 선", "LNG운반선", "기 타", "기본설계"):
            self.assertFalse(is_total(s), s)


class TestShipOrdersTable(unittest.TestCase):
    """조선 수주표 방언: 척수 열 보존 · 합계행 보존 · 달러 단위."""

    HTML = """<p>가. 수주상황</p><p>(단위 : 백만달러, 척)</p><table>
<tr><td rowspan=2>선종</td><td colspan=2>수주총액</td><td colspan=2>기납품액</td><td colspan=2>수주잔고</td><td rowspan=2>인도예정</td></tr>
<tr><td>수량</td><td>금액</td><td>수량</td><td>금액</td><td>수량</td><td>금액</td></tr>
<tr><td>LNG운반선</td><td>42</td><td>10,500.5</td><td>12</td><td>3,000</td><td>30</td><td>7,500.5</td><td>2026~2029</td></tr>
<tr><td>합 계</td><td>42</td><td>10,500.5</td><td>12</td><td>3,000</td><td>30</td><td>7,500.5</td><td>-</td></tr></table>"""

    def test_quantity_total_currency(self):
        r = parse_orders(self.HTML)
        self.assertEqual(r["unknown_headers"], [])
        t = r["tables"][0]
        self.assertEqual(t["cur"], "USD")
        rows = t["rows"]
        self.assertEqual(rows[0]["qty"], 42)
        self.assertEqual(rows[0]["qty_bal"], 30)
        self.assertAlmostEqual(rows[0]["bal"], 7500.5)
        self.assertTrue(rows[1]["total"])                 # 합계행이 사라지지 않는다
        self.assertEqual(t["n"], 1)


class TestYardRollforward(unittest.TestCase):
    """HD현대중공업 2026 반기 원문 — 부문 롤포워드와 매출실적."""

    def test_rollforward_from_fixture(self):
        from kship_lib import parse_tables
        tabs = parse_tables(_fx("hhi_orders_2026H1.html"))
        orders = [x for x in (parse_orders_table(t) for t in tabs if t["cols"]) if x and x["rows"]]
        self.assertTrue(orders)
        o = max(orders, key=lambda o: len(o["rows"]))
        tot = [r for r in o["rows"] if r["total"]][0]
        self.assertEqual(tot["closing"], 69514154)
        self.assertEqual(tot["opening"] + tot["new"] - tot["delivered"], tot["closing"])
        segs = {r["seg"].replace(" ", ""): r for r in o["rows"] if not r["total"]}
        self.assertEqual(segs["조선"]["closing"], 55573921)
        self.assertEqual(o["cur"], "KRW")

    def test_revenue_from_fixture(self):
        from kship_lib import parse_tables
        tabs = parse_tables(_fx("hhi_orders_2026H1.html"))
        rev = [x for x in (parse_revenue_table(t) for t in tabs if t["cols"]) if x]
        self.assertTrue(rev)
        rows = rev[0]["rows"]
        ship_export = [r for r in rows if r["seg"].replace(" ", "") == "조선" and r["kind"] == "수출"][0]
        self.assertEqual(ship_export["vals"][0], 8882303)


class TestContract(unittest.TestCase):
    def test_parse_contract_fixture(self):
        r = parse_contract(_fx("hhi_contract_20260824800122.html"), "20260824800122", "단일판매ㆍ공급계약체결", "329180")
        self.assertEqual(r["name"], "LPGC 4척")
        self.assertEqual(r["type"], "VLGC")
        self.assertEqual(r["ships"], 4)
        self.assertEqual(r["amt_krw_m"], 515400.0)
        self.assertEqual(r["end"], "2030-03-31")
        self.assertTrue(r["party_anon"])
        self.assertEqual(r["payterm"], "공사진척에 따른 수금")

    def test_new_krx_template_fields(self):
        """2025~ 신형 서식: 계약명이 '판매ㆍ공급계약 구분/세부내용'에, 수주일 라벨이 '계약(수주)일'."""
        from kship_contracts import _fields_from_kv, _kv_from_raw
        raw = [("1. 판매ㆍ공급계약 구분", "공사수주"), ("- 세부내용", "VLCC 2척"),
               ("2. 계약내역 계약금액(원)", "349,000,000,000"), ("3. 계약상대", "아시아 소재 선사"),
               ("4. 판매ㆍ공급지역", "아시아"), ("5. 계약기간 시작일", "2025-06-12"), ("5. 계약기간 종료일", "2027-08-31"),
               ("6. 주요 계약조건 계약금ㆍ선급금 유무", "유"), ("7. 계약(수주)일", "2025-06-12")]
        f = _fields_from_kv(_kv_from_raw(raw))
        self.assertEqual((f["name"], f["type"], f["ships"], f["amt_krw_m"], f["signed"], f["end"], f["region"]),
                         ("VLCC 2척", "VLCC", 2, 349000.0, "2025-06-12", "2027-08-31", "아시아"))
        # 정정공시: 앞에 붙는 정정 표의 '5. 계약기간 -종료일 2029-03-31'→'2028-11-30' 은 본표 값을 덮지 않는다
        raw2 = [("정정항목 정정전", "정정후"), ("5. 계약기간 -종료일 2029-03-31", "2028-11-30")] + raw
        self.assertEqual(_fields_from_kv(_kv_from_raw(raw2))["end"], "2027-08-31")

    def test_ship_type_tokens(self):
        cases = {"LPGC 4척": "VLGC", "LNG운반선 2척": "LNGC", "17,000TEU급 컨테이너선 6척": "CONT",
                 "VLCC 2척": "VLCC", "MR탱커 4척": "PC", "PCTC 4척": "PCTC", "KDDX 1척": "NAVAL",
                 "FPSO 1기": "OFFSH", "보령화력 1~8호기 저탄장 옥내화 공사": "OTHER",
                 "엔진발전기 공급": "OTHER", "다목적 화학방제함 1척 건조": "NAVAL",
                 "초대형 LPG/AMMONIA 운반선 1척": "VLGC", "부산 범천5구역 재개발정비사업": "OTHER",
                 "KSS-II 성능개량 체계개발사업": "NAVAL", "필리핀 따굼 홍수조절사업": "OTHER"}
        for name, want in cases.items():
            self.assertEqual(ship_type_of(name), want, name)


class TestHedgeNote(unittest.TestCase):
    """주석의 '당반기말' 표 뒤에 오는 '전기말' 비교표를 더하면 명목액이 두 배가 된다(삼성重 482억달러 오류의 원인)."""

    def test_hedge_note_skips_prior_period(self):
        from kship_yards import parse_hedge_any
        tbl = ("<table><tr><th></th><th>금융상품 파생상품 파생상품1 위험회피 매매 목적</th></tr>"
               "<tr><td>외화파생상품 매도금액, USD [USD, 천]</td><td>%s</td></tr></table>")
        html = ("<p>위험회피에 대한 세부 정보 공시 당반기말 (단위 : 천원)</p>" + tbl % "1,000,000"
                + "<p>전기말 (단위 : 천원)</p>" + tbl % "2,000,000")
        h = parse_hedge_any(html, "note")
        self.assertEqual(h["shape"], "note-label")
        self.assertEqual(h["usd_sell_m"], 1000.0)            # 천달러 → 백만달러, 전기 표 제외
        # 기간 표기가 없어도 같은 라벨 묶음이 반복되면 뒤 표는 비교표시다
        html2 = "<p>(단위 : 천원)</p>" + tbl % "1,000,000" + "<p>(단위 : 천원)</p>" + tbl % "2,000,000"
        self.assertEqual(parse_hedge_any(html2, "note")["usd_sell_m"], 1000.0)


class TestHedgeNoteColumns(unittest.TestCase):
    def test_hedge_note_uses_total_column(self):
        """사업보고서 주석: 멤버마다 목적별 3열 + 합계 열 — 합계 열만 세어야 두 배가 되지 않는다."""
        from kship_yards import parse_hedge_any
        html = ("<p>당기 (단위 : 천원)</p><table><tr><th></th><th>파생상품1 매매 목적</th><th>파생상품1 공정가치위험회피</th>"
                "<th>파생상품1 현금흐름위험회피</th><th>파생상품1 합계</th></tr>"
                "<tr><td>외화파생상품 매도금액, USD [USD, 천]</td><td>1,000</td><td>2,000</td><td>3,000</td><td>6,000</td></tr></table>")
        self.assertEqual(parse_hedge_any(html, "note")["usd_sell_m"], 6.0)
        # 멤버별 합계 열 + 총합계 열(삼성重 사업보고서): 총합계만
        html2 = ("<p>당기 (단위 : 천원)</p><table><tr><th></th><th>통화 관련 파생상품5 파생상품 목적의 지정 합계</th>"
                 "<th>통화 관련 파생상품15 파생상품 목적의 지정 합계</th><th>파생상품 계약 유형 합계</th></tr>"
                 "<tr><td>외화파생상품 매도금액, USD [USD, 천]</td><td>1,000</td><td>5,000</td><td>6,000</td></tr></table>")
        self.assertEqual(parse_hedge_any(html2, "note")["usd_sell_m"], 6.0)


class TestTaxonomy(unittest.TestCase):
    """정적 사전의 교차 참조가 깨지면 인포그래픽이 잘못된 회사를 보여 준다."""

    def test_rel_keys_match_categories(self):
        tax = L.load_asset("parts_taxonomy.json")
        st = L.load_asset("ship_types.json")
        cat_ids = {c["id"] for c in tax["cats"]}
        for tid, row in st["rel"].items():
            self.assertEqual(set(row), cat_ids, tid)

    def test_regions_reference_existing_categories(self):
        tax = L.load_asset("parts_taxonomy.json")
        svg = L.load_asset("svg_regions.json")
        cat_ids = {c["id"] for c in tax["cats"]}
        for r in svg["regions"] + svg["engine_zoom"]["regions"]:
            for c in r["cats"]:
                self.assertIn(c, cat_ids, r["id"])

    def test_classify_examples(self):
        self.assertIn("CARGO.LNG", classify_product("초저온 보냉재", True))
        self.assertIn("PIPE.FITTING", classify_product("관이음쇠", True))
        self.assertIn("ENG.PARTS", classify_product("선박엔진부품", False))
        self.assertIn("PROP.MAIN", classify_product("대형선박용엔진", False))
        self.assertEqual(classify_product("XML/SGML 관련 제품 및 솔루션", False), ["UNCL"])
        # 문맥 필요 낱말은 해상 문맥이 없으면 채택하지 않는다(육상 밸브·크레인 오탐 방지)
        self.assertEqual(classify_product("볼밸브", False), ["UNCL"])
        self.assertIn("PIPE.VALVE", classify_product("선박용 볼밸브", False))


class TestPageShell(unittest.TestCase):
    def test_external_scripts_precede_body(self):
        h = L.page("t", "<script>Chart.x</script>", depth=1, scripts=("../vendor/chart.umd.min.js",))
        self.assertLess(h.index("chart.umd.min.js"), h.index("Chart.x"))
        self.assertIn('href="../assets/kship.css"', h)

    def test_json_for_html_escapes_script_close(self):
        s = L.json_for_html({"nm": "악성</script><img>"})
        self.assertNotIn("</script>", s)


if __name__ == "__main__":
    unittest.main()
