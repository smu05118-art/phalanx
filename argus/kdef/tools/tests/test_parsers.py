#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국방산 파서 계약(contract) 테스트 — 형식이 아니라 **화면에 실리는 값**을 지킨다.

fixture 는 실제 DART 원문에서 뽑은 표·공시다(tests/fixtures/). 여기서 검증하는 것:

  · 단위 정규화 — 억원 표의 값이 백만원으로 들어오는가, 단위 캡션이 **앞 표**에 있어도 읽는가
  · 합계/소계 판정 — 부문 합계와 전체 합계를 함께 더해 두 배가 되지 않는가
  · 핵심 표 1종 원문 대조 — KAI 2026 반기 수주표(국내방산 109,868억)가 화면 값과 같은가
  · 분류 사전 교차참조 — 부품 소분류의 영역이 SVG 에 있고, 영역의 소분류가 실재하는가
  · 계약 공시 두 양식(유가·코스닥) — 계약명·금액·상대 갈래
  · ④ 탐색 승격 규칙

    python3 -m unittest discover -s tests
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import build_dicts                                                   # noqa: E402
import kdef_contracts as KC                                          # noqa: E402
import kdef_reports as KR                                            # noqa: E402
import kdef_scan as KS                                               # noqa: E402
import kdef_suppliers as KSup                                        # noqa: E402
from kdef_lib import load_asset                                      # noqa: E402

FIX = os.path.join(HERE, "fixtures")


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


class TestOrdersTable(unittest.TestCase):
    """KAI 2026 반기 「나. 수주상황」 — 두 줄 머리행 · 억원 · 지배회사 표 고르기."""

    def setUp(self):
        self.tables = KR._headered(KR._carry_units(fixture("kai_2026Q2_orders.json")["tables"]))
        self.parsed = [o for o in (KR.parse_orders_table(t) for t in self.tables) if o]

    def test_two_row_header_recovered(self):
        """머리행이 두 줄이면 이어 붙여 `기 초(…) 금액` 열을 만든다(안 하면 표가 통째로 버려진다)."""
        o = KR._pick_orders(self.parsed)
        self.assertIsNotNone(o, "수주표를 한 장도 못 읽었다")
        self.assertEqual(o["shape"], "openclose")
        self.assertTrue(any("금액" in c for c in o["cols"]))

    def test_unit_is_eok_scaled_to_million(self):
        """단위가 (단위 : 억원) 이므로 109,868 은 10,986,800 백만원이어야 한다."""
        o = KR._pick_orders(self.parsed)
        self.assertTrue(o["unit_seen"])
        row = [r for r in o["rows"] if r["seg"].startswith("국내방산")][0]
        self.assertEqual(row["opening"], 10986800)
        self.assertEqual(row["closing"], 10235500)

    def test_total_row_marked_and_matches_segments(self):
        """합계 행은 total 로 표시되고, 부문 합과 1% 안에서 맞아야 한다."""
        o = KR._pick_orders(self.parsed)
        tot = [r for r in o["rows"] if r["total"]]
        segs = [r for r in o["rows"] if not r["total"]]
        self.assertEqual(len(tot), 1)
        self.assertAlmostEqual(tot[0]["closing"],
                               sum(r["closing"] for r in segs if r["closing"] is not None),
                               delta=0.01 * tot[0]["closing"])

    def test_backlog_matches_screen_value(self):
        """화면(회사 페이지 KPI)에 실리는 잔고 = 25조 7,502억."""
        o = KR._pick_orders(self.parsed)
        tot = [r for r in o["rows"] if r["total"]][0]
        self.assertEqual(tot["closing"], 25750200)

    def test_segment_defense_classified(self):
        """국내방산·완제기수출은 방산(def)으로 판정돼야 방산 잔고가 산다."""
        o = KR._pick_orders(self.parsed)
        kinds = {r["seg"]: r["kind"] for r in o["rows"]}
        self.assertEqual(kinds["국내방산"], "def")
        self.assertEqual(kinds["완제기수출"], "def")


class TestUnitRules(unittest.TestCase):
    def test_unit_carried_from_previous_table(self):
        """단위 캡션이 **앞의 한 줄짜리 표**에 있으면 뒤 표가 물려받는다(한화에어로 양식)."""
        tables = [{"cols": [], "rows": [["", "(단위 : 백만원)"]], "lead": "다. 수주상황(요약)"},
                  {"cols": ["구분", "수주총액 금액", "수주잔고 금액"],
                   "rows": [["방산", "1,000", "400"]], "lead": ""}]
        out = KR._carry_units(tables)
        self.assertTrue(out[1].get("unit_from_prev"))
        o = KR.parse_orders_table(out[1])
        self.assertTrue(o["unit_seen"])
        self.assertEqual(o["rows"][0]["closing"], 400)

    def test_quantity_unit_is_not_money(self):
        """단위가 M/T 면 금액이 아니다 — 값을 돈으로 싣지 않는다(풍산 종속회사 표)."""
        t = {"cols": ["품목", "수주총액", "수주잔고"], "rows": [["신관", "70,516", "50,002"]],
             "lead": "주요 종속회사의 수주상황은 아래와 같습니다. (단위 : M/T)"}
        o = KR.parse_orders_table(t)
        self.assertTrue(o["qty_unit"])
        self.assertFalse(o["unit_seen"])

    def test_money_table_beats_quantity_table(self):
        """금액 표와 수량 표가 함께 오면 금액 표를 고른다."""
        qty = KR.parse_orders_table(
            {"cols": ["품목", "수주잔고"], "rows": [["신관", "50,002"]],
             "lead": "(단위 : M/T)"})
        money = KR.parse_orders_table(
            {"cols": ["품목", "수주잔고 금액"], "rows": [["신관", "1,789,040"]],
             "lead": "(단위 : 백만원)"})
        self.assertEqual(KR._pick_orders([qty, money])["rows"][0]["closing"], 1789040)


class TestTotalsNotDoubleCounted(unittest.TestCase):
    """부문 합계와 전체 합계가 함께 오는 표(한화에어로 매출실적)를 두 배로 세지 않는다."""

    def _rev(self):
        cols = ["사업부문", "품목", "구분", "2026년 반기", "2025년"]
        rows = [["항공", "엔진", "수출", "596,377", "1,170,700"],
                ["항공", "엔진", "내수", "745,622", "1,112,586"],
                ["항공", "엔진", "합계", "1,341,999", "2,283,286"],
                ["방산", "자주포", "수출", "1,948,317", "4,672,473"],
                ["방산", "자주포", "내수", "2,281,554", "5,209,142"],
                ["방산", "자주포", "합계", "4,229,871", "9,881,615"],
                ["합 계", "합 계", "합계", "5,571,870", "12,164,901"]]
        return KR.parse_revenue_table({"cols": cols, "rows": rows,
                                       "lead": "가. 매출실적 (단위 : 백만원)"})

    def test_fy_revenue_uses_grand_total_only(self):
        rv = self._rev()
        val, col = KR._fy_revenue(rv)
        self.assertEqual(col, "2025년")
        self.assertEqual(val, 12164901)          # 부문 합계까지 더하면 24,329,802 가 된다

    def test_fy_column_is_a_full_year(self):
        self.assertTrue(KR._is_fy("2025년(제27기) 금액"))
        self.assertTrue(KR._is_fy("제26기"))
        self.assertFalse(KR._is_fy("2026년 반기"))
        self.assertFalse(KR._is_fy("2025년(제27기) 비중"))

    def test_sales_route_table_is_not_revenue(self):
        """`판매경로·판매방법` 표는 매출표가 아니다(비중 100 을 매출로 읽으면 안 된다)."""
        t = {"cols": ["사업부문", "시장구분", "판매경로(비중)", "판매방법", "판매전략"],
             "rows": [["방산", "내수", "100", "직판", "-"]], "lead": "판매경로 및 판매방법"}
        self.assertIsNone(KR.parse_revenue_table(t))


class TestContracts(unittest.TestCase):
    def test_kosdaq_form_contract_name_and_amount(self):
        """코스닥 양식은 계약명이 「1. 판매ㆍ공급계약 내용」에 있다(유가는 「- 체결계약명」)."""
        fx = fixture("speco_contract_kosdaq.json")
        rec = KC._fields_from_kv(KC._kv_from_raw(fx["kv"]))
        self.assertEqual(rec["name"], "해군함정용 조타기 공급")
        self.assertEqual(rec["amt_krw_m"], 4100)          # 41억원 → 백만원
        self.assertEqual(rec["party"], "현대중공업(주)")
        self.assertEqual(rec["domain"], "NAVAL")
        self.assertEqual(rec["start"], "2023-05-11")
        self.assertEqual(rec["end"], "2027-11-03")

    def test_merged_correction_row_is_not_money(self):
        """정정공시에 라벨과 값이 뭉쳐 온 행(값에 숫자 3개)을 금액으로 읽지 않는다.

        실측: 빅텍 `20260320900593` — 그대로 읽으면 868억짜리 계약이 8.7×10^24 원이 된다."""
        fx = fixture("merged_row_correction.json")
        rec = KC._fields_from_kv(KC._kv_from_raw(fx["kv"]))
        self.assertEqual(rec["amt_krw_m"], 86764.475)
        self.assertEqual(rec["party"], "국방과학연구소")
        self.assertEqual(KC.party_kind(rec["party"])[0], "GOV")

    def test_find_ignores_spaces_in_needle(self):
        """라벨은 공백이 지워져 있으므로 `계약금액 총액(원)` 같은 검색어도 찾아야 한다."""
        kv = KC._kv_from_raw([["2. 계약내역 계약금액 총액(원)", "1,000"]])
        self.assertEqual(KC._find(kv, "계약금액 총액(원)"), "1,000")

    def test_party_kinds(self):
        cases = [("방위사업청", "GOV"), ("대한무역투자진흥공사(KOTRA)", "GOV"),
                 ("노르웨이 국방물자청(NDMA)", "G2G"), ("폴란드 군비청", "G2G"),
                 ("한화에어로스페이스(주)", "PRIME"), ("해외 완제기 업체", "ANON"),
                 ("Hanwha WB Advanced System sp.z o.o.", "FOREIGN")]
        for party, want in cases:
            self.assertEqual(KC.party_kind(party)[0], want, party)

    def test_prime_party_resolves_to_stock(self):
        self.assertEqual(KC.party_kind("한화시스템 주식회사")[1], "272210")

    def test_domain_system_name_beats_generic_word(self):
        """`천궁Ⅱ 다기능레이다`의 계통은 레이다(감시정찰)가 아니라 천궁(유도무기)이다."""
        self.assertEqual(KC.domain_of("천궁Ⅱ 다기능레이다 수출"), "MISSILE")
        self.assertEqual(KC.domain_of("K9자주포 후속양산"), "GROUND")
        self.assertEqual(KC.domain_of("LNG 운반선 1척"), "CIVIL")
        self.assertEqual(KC.domain_of("우즈베키스탄 고속전철 공급 및 유지보수 사업"), "CIVIL")

    def test_contract_types(self):
        self.assertEqual(KC.ctype_of("K9자주포 4차 양산"), "FOLLOW")
        self.assertEqual(KC.ctype_of("L-SAM 최초양산 물품공급계약"), "FIRST")
        self.assertEqual(KC.ctype_of("전자전기(Block-I) 체계개발"), "RND")
        self.assertEqual(KC.ctype_of("KF-16 성능개량"), "UPGRADE")
        self.assertEqual(KC.ctype_of("함정 창정비 용역"), "PBL")
        self.assertEqual(KC.ctype_of("이름 없는 무엇"), "UNKNOWN")


class TestDicts(unittest.TestCase):
    def test_dicts_cross_reference(self):
        """소분류의 영역이 SVG 에 있고, 모든 영역이 최소 1개 소분류를 갖는다(build_dicts 의 검증)."""
        parts = build_dicts.build_parts()
        svg = build_dicts.build_svg()
        build_dicts.check(parts, svg)                      # 어긋나면 예외
        rid = {r["id"] for r in svg["regions"]}
        for c in parts["cats"]:
            for r in c["regions"]:
                self.assertIn(r, rid, c["id"])

    def test_domain_slots_match_palette(self):
        """계통 색 슬롯은 팔레트에 있어야 한다 — 없으면 차트가 죽는다."""
        from kdef_lib import slot_color
        for d in load_asset("domains.json")["domains"]:
            self.assertTrue(slot_color(d["slot"]).startswith("#"))


class TestSuppliers(unittest.TestCase):
    def test_short_acronym_needs_nearby_defence_context(self):
        """`자동차용 센서(APS, TPS…)`를 능동방호(APS)로 세면 안 된다."""
        tax = load_asset("parts_taxonomy.json")
        hits = KSup.match_cats(tax, [("kind", "자동차용 센서(APS, TPS, IAPS, SLS)")])
        self.assertNotIn("ARMOR.APS", [h["cat"] for h in hits])
        hits2 = KSup.match_cats(tax, [("kind", "전차 능동방호체계(APS) 구성품")])
        self.assertIn("ARMOR.APS", [h["cat"] for h in hits2])

    def test_evidence_grades_ordered(self):
        """근거 등급은 주요고객 주석 > 계약공시 상대 > 본문 언급 순이어야 한다."""
        g = {k: v[0] for k, v in KSup.BASIS.items()}
        self.assertLess(g["customer"], g["contract"])
        self.assertLess(g["contract"], g["body"])


class TestScanRule(unittest.TestCase):
    def test_promotion_needs_evidence(self):
        """④ 탐색: 낱말이 모자라면 승격하지 않는다(fail-closed)."""
        weak = {"ok": True, "hits": 2, "gov": 0, "mentions": {}, "terms": {"방산": 2}}
        strong = {"ok": True, "hits": 12, "gov": 1, "mentions": {}, "terms": {"방산": 12}}
        linked = {"ok": True, "hits": 5, "gov": 0, "mentions": {"012450": 3}, "terms": {}}
        self.assertFalse(KS.judge(weak))
        self.assertTrue(KS.judge(strong))
        self.assertTrue(KS.judge(linked))


if __name__ == "__main__":
    unittest.main()
