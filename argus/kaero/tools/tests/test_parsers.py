#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kaero 파서 계약 검증 — 형식이 아니라 **화면에 실린 값이 원문과 같은가**(COMMON §4).

fixture 는 DART 원문 절을 `parse_tables` 한 그대로다(`*_raw.json` 은 표 복구 **전**).
숫자는 원문에서 눈으로 읽은 값을 그대로 적는다 — 파서가 바뀌어도 이 숫자는 안 바뀐다.

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

import build_dicts                                            # noqa: E402
import kaero_reports as R                                     # noqa: E402
import kaero_scan as SC                                       # noqa: E402
from kaero_lib import cur_unit, fmt_money, load_asset         # noqa: E402
from kaero_suppliers import match_cats                        # noqa: E402


def fx(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return json.load(f)["tables"]


def repaired(name):
    return R._headered(R._carry_units(fx(name)))


class TestCurrency(unittest.TestCase):
    """§1 통화 — 표마다 다르고, 환산하지 않는다."""

    def test_usd_caption_is_usd_million(self):
        """`(단위 : USD )` → USD, 배수 1e-06(기준 단위는 백만달러)."""
        t = {"lead": "1) 국외수주현황 (기준일 :2025년 12월 31일) (단위 : USD )", "cols": []}
        cur, mul, seen, note = R.table_currency(t)
        self.assertEqual((cur, seen), ("USD", True))
        self.assertAlmostEqual(mul, 1e-06)
        self.assertEqual(note, "")

    def test_won_caption_is_krw_million(self):
        t = {"lead": "2) 국내수주현황 (단위 : 원)", "cols": []}
        cur, mul, seen, _ = R.table_currency(t)
        self.assertEqual((cur, seen), ("KRW", True))
        self.assertAlmostEqual(mul, 1e-06)

    def test_mixed_caption_is_rejected(self):
        """켄코아 `(단위 : USD, 천원)` — 한 통화로 읽을 수 없으면 금액으로 싣지 않는다."""
        t = {"lead": "가. 매출 실적 (단위 : USD, 천원)", "cols": []}
        cur, mul, seen, note = R.table_currency(t)
        self.assertEqual(cur, "MIXED")
        self.assertIsNone(mul)
        self.assertFalse(seen)
        self.assertIn("통화가 둘 이상", note)

    def test_no_caption_is_not_money(self):
        cur, mul, seen, note = R.table_currency({"lead": "나. 수주상황", "cols": []})
        self.assertFalse(seen)
        self.assertIn("못 읽음", note)

    def test_scaled_refuses_without_multiplier(self):
        """배수를 못 정했으면 값을 만들지 않는다 — 1로 가정하면 763억이 76.4백만달러가 된다."""
        self.assertIsNone(R._scaled("76,394,213", None))
        self.assertEqual(R._scaled("76,394,213", 0.001), 76394.213)

    def test_display_units(self):
        self.assertEqual(cur_unit("KRW"), "억원")
        self.assertEqual(cur_unit("USD"), "백만달러")
        self.assertEqual(fmt_money(2688.832, "USD"), "2,689")     # 26.9억달러
        self.assertEqual(fmt_money(254386.381, "KRW"), "2,544")   # 2,544억원


class TestAstOrders(unittest.TestCase):
    """§1·§2 아스트 — 두 통화 표가 나뉘고, 품목 열이 발주처다."""

    @classmethod
    def setUpClass(cls):
        cls.tables = repaired("ast_2025Q4.json")
        cls.orders = [o for o in (R.parse_orders_table(t) for t in cls.tables) if o]
        cls.picked, cls.rejected = R.group_orders(cls.orders)

    def test_two_currencies_kept_apart(self):
        self.assertEqual(sorted(self.picked), ["KRW", "USD"])

    def test_usd_backlog_matches_source(self):
        """원문 합계 행: 수주잔고 2,688,832,423.74 USD → 2,688.832 백만달러."""
        self.assertAlmostEqual(R._closing(self.picked["USD"]), 2688.832423, places=4)

    def test_krw_backlog_matches_source(self):
        """원문 합계 행: 271,598,729 원 → 271.598729 백만원(= 2.7억)."""
        self.assertAlmostEqual(R._closing(self.picked["KRW"]), 271.598729, places=5)

    def test_not_summed_across_currencies(self):
        """두 통화를 더한 값이 어디에도 없어야 한다."""
        self.assertNotIn(2688.832423 + 271.598729,
                         [R._closing(o) for o in self.picked.values()])

    def test_shape_is_item_ledger(self):
        self.assertEqual(self.picked["USD"]["shape"], "item")

    def test_item_column_is_the_customer(self):
        """SPIRIT·EMBRAER·BOMBARDIER·IAI·RUAG 가 고객으로 읽혀야 한다."""
        got = {c["name"] for r in self.picked["USD"]["rows"] for c in r["customers"]}
        for want in ("Spirit", "Embraer", "Bombardier", "IAI", "RUAG"):
            self.assertIn(want, got)

    def test_embraer_row_values(self):
        """원문 한 줄 그대로: EMBRAER 2019~2038 · 총액 1,760,168,200 · 잔고 1,479,298,728.45."""
        row = [r for r in self.picked["USD"]["rows"] if r["seg"] == "EMBRAER"][0]
        self.assertAlmostEqual(row["gross"], 1760.1682, places=4)
        self.assertAlmostEqual(row["closing"], 1479.29872845, places=6)
        self.assertEqual((row["order_year"], row["due_year"]), (2019, 2038))
        self.assertEqual(row["nature"], "LTA")          # 19년짜리 — 장기공급

    def test_quantity_due_is_not_a_year(self):
        """STEA 납기 칸은 `400대` 다 — 연도로 읽지 않는다(fail-closed)."""
        row = [r for r in self.picked["USD"]["rows"] if r["seg"] == "STEA"][0]
        self.assertEqual(row["due"], "400대")
        self.assertIsNone(row["due_year"])
        self.assertEqual(row["nature"], "BATCH")

    def test_total_row_flagged(self):
        self.assertTrue(any(r["total"] for r in self.picked["USD"]["rows"]))


class TestAstRevenue(unittest.TestCase):
    """합계가 **세 벌** 오는 표 — 다 더하면 매출이 두 배가 된다."""

    @classmethod
    def setUpClass(cls):
        cls.tables = repaired("ast_2025Q4.json")

    def test_duplicate_header_is_repaired(self):
        """`매출유형 | 품 목 | 품 목 | 제25기…` — 중복 이름을 갈라야 표가 산다."""
        hit = [t for t in self.tables if "매출유형" in (t["cols"] or [])]
        self.assertTrue(hit, "매출실적 표가 통째로 버려졌다")
        self.assertEqual(len(set(hit[0]["cols"])), len(hit[0]["cols"]))

    def test_fy_revenue_uses_last_total_group(self):
        """`합 계` 255,562,284 · `내부제거` · `총합계` 254,386,381(천원) 중 총합계만 쓴다."""
        rv = [x for x in (R.parse_revenue_table(t) for t in self.tables) if x]
        self.assertTrue(rv)
        val, col = R._fy_revenue(max(rv, key=lambda r: len(r["rows"])))
        self.assertAlmostEqual(val, 254386.381, places=3)       # 백만원 = 2,544억
        self.assertEqual(col, "제25기")

    def test_export_share_from_total_row(self):
        rv = max([x for x in (R.parse_revenue_table(t) for t in self.tables) if x],
                 key=lambda r: len(r["rows"]))
        self.assertAlmostEqual(R._sum_rev_kind(rv["rows"], "수출"), 235270.898, places=3)
        self.assertAlmostEqual(R._sum_rev_kind(rv["rows"], "내수"), 19115.483, places=3)

    def test_domain_from_product_names(self):
        """Section48·Bulkhead·Fuselage·U/L Deck → 기체구조물."""
        for name in ("Section48", "Bulkhead", "Fuselage", "U/L Deck", "Stringer"):
            self.assertEqual(R.domain_of(name), "struct", name)


class TestHaizeCarryUnits(unittest.TestCase):
    """§5 단위 캡션이 **옆 표에** 있다 — 물려주지 않으면 1.16조가 사라진다."""

    def test_data_table_has_no_caption_of_its_own(self):
        raw = fx("haize_raw.json")
        data = [t for t in raw if "수주잔고(주1) 금액" in (t["cols"] or [])]
        self.assertTrue(data, "하이즈 수주표를 fixture 에서 못 찾음")
        self.assertNotIn("단위", data[0].get("lead") or "")

    def test_carry_units_recovers_backlog(self):
        tables = R._headered(R._carry_units(fx("haize_raw.json")))
        orders = [o for o in (R.parse_orders_table(t) for t in tables) if o]
        picked, _ = R.group_orders(orders)
        self.assertIn("KRW", picked)
        self.assertTrue(picked["KRW"]["unit_seen"])
        # 원문 합계 행: 수주잔고 1,162,538 백만원
        self.assertAlmostEqual(R._closing(picked["KRW"]), 1162538.0, places=1)

    def test_customer_table_names(self):
        tables = R._headered(R._carry_units(fx("haize_raw.json")))
        cs = [c for c in (R.parse_customers(t) for t in tables) if c]
        self.assertTrue(cs)
        names = {r["name"] for c in cs for r in c["rows"]}
        # 구분 열(`국내`·`수출`)이나 머리행이 고객으로 실리면 안 된다
        self.assertNotIn("국내", names)
        self.assertNotIn("수출", names)
        self.assertNotIn("합계", names)
        self.assertTrue({"대한항공", "한국항공"} & names, names)

    def test_boeing_abbreviation_from_footnote(self):
        """각주가 `BOE(Boeing Commercial Airplanes)` 로 풀어 둔다 — OEM으로 읽는다."""
        got = {c["name"] for c in R.customers_in("BOE(Boeing Commercial Airplanes)")}
        self.assertIn("Boeing", got)


class TestKencoaMixed(unittest.TestCase):
    """§6 한 표 안에 통화가 섞인 회사 — 금액으로 싣지 않되 **행 이름은 남긴다**."""

    def test_segment_sales_has_names_but_no_money(self):
        tables = R._headered(R._carry_units(fx("kencoa_raw.json")))
        ss = [x for x in (R.parse_segment_sales(t) for t in tables) if x]
        self.assertTrue(ss, "켄코아 매출실적 표가 통째로 버려졌다")
        s = ss[0]
        self.assertFalse(s["unit_seen"])
        self.assertIn("통화가 둘 이상", s["unit_note"])
        self.assertTrue(any(r["seg"] == "항공기 부품" for r in s["rows"]))
        self.assertTrue(all(r["val"] is None for r in s["rows"]))

    def test_fy_revenue_not_made(self):
        tables = R._headered(R._carry_units(fx("kencoa_raw.json")))
        ss = [x for x in (R.parse_segment_sales(t) for t in tables) if x]
        self.assertEqual(R._fy_segsales(ss[0]), (None, None))


class TestSegmentSplit(unittest.TestCase):
    """§4 겸업사 — 부문 열은 **머리행이 아니라 값으로** 찾는다."""

    def test_seg_tab_mapping(self):
        self.assertEqual(R.seg_tab("항공"), "kaero")
        self.assertEqual(R.seg_tab("항공우주"), "kaero")
        self.assertEqual(R.seg_tab("해양"), "kship")
        self.assertEqual(R.seg_tab("방산"), "kdef")
        self.assertEqual(R.seg_tab("IT서비스 등"), "other")
        self.assertIsNone(R.seg_tab("한화에어로스페이스㈜ 및해외 종속회사"))

    def test_business_col_is_not_the_company_col(self):
        """머리행 `부문 | 사업 | 품목` 에서 `부문` 칸에는 회사 이름이 들어 있다."""
        rows = [["한화에어로스페이스㈜ 및해외 종속회사", "항공", "추진기관"],
                ["한화오션㈜ 및종속회사", "해양", "상선"],
                ["한화시스템㈜및 종속회사", "방산", "군수장비"]]
        self.assertEqual(R._business_col(rows, [0, 1, 2]), 1)

    def test_no_business_col_when_nothing_classifies(self):
        rows = [["SPIRIT"], ["EMBRAER"], ["BOMBARDIER"]]
        self.assertIsNone(R._business_col(rows, [0]))


class TestDomainAndNature(unittest.TestCase):
    """영역·계약성격 — 원문 문구에서 읽는다. 순서가 뜻을 가른다."""

    def test_domain_priority(self):
        self.assertEqual(R.domain_of("PBL-KUH 상륙기동 엔진"), "mro")      # PBL 이 엔진을 이긴다
        self.assertEqual(R.domain_of("KF-X 엔진/APU 체계개발"), "engine")  # 엔진이 방산을 이긴다
        self.assertEqual(R.domain_of("다목적 실용위성 탑재체"), "space")
        self.assertEqual(R.domain_of("해군조립"), "defav")                 # `조립` 단독은 구조물이 아니다
        self.assertEqual(R.domain_of("상세내역 참조"), "other")

    def test_nature_from_text(self):
        self.assertEqual(R.nature_of("한화테크윈(주), 국제공동개발사업 계약 (PW GTF RSP)"), "RSP")
        self.assertEqual(R.nature_of("GE GEnx RSP"), "RSP")
        self.assertEqual(R.nature_of("PBL-GEM42"), "PBL")
        self.assertEqual(R.nature_of("KF-X 엔진/APU 체계개발"), "DEV")
        self.assertEqual(R.nature_of("LM6000 LPT모듈 공급계약"), "LTA")

    def test_nature_from_duration_when_text_is_silent(self):
        self.assertEqual(R.nature_of("추진기관", "2014.01", "2029.12"), "LTA")   # 15년
        self.assertEqual(R.nature_of("추진기관", "2024.01", "2026.12"), "BATCH")  # 2년

    def test_abbreviation_is_marked_as_guess(self):
        got = {c["name"]: c["grade"] for c in R.customers_in("KAL")}
        self.assertEqual(got.get("대한항공"), "C")
        got2 = {c["name"]: c["grade"] for c in R.customers_in("한국항공우주산업")}
        self.assertEqual(got2.get("한국항공우주"), "B")


class TestCustomerName(unittest.TestCase):
    """매출처 표의 이름 칸 — 구분어·기간·머리행을 고객으로 싣지 않는다."""

    def test_kind_word_is_not_a_customer(self):
        self.assertEqual(R.customer_name(["방위사업청 등", "내수", "1,072,101", "48.24%"], set()),
                         ("방위사업청 등", False))

    def test_item_col_before_name(self):
        self.assertEqual(R.customer_name(["제품", "국내", "P사", "6,030"], set()), ("P사", True))

    def test_period_header_rejected(self):
        self.assertEqual(R.customer_name(["매출처", "구분", "2026년 반기(제28기)"], set()),
                         (None, False))

    def test_total_rejected(self):
        self.assertEqual(R.customer_name(["총 매출액", "2,360,785", "100.00%"], set()),
                         (None, False))


class TestDicts(unittest.TestCase):
    """분류 사전 교차참조 — 생성 시점에 검증되고, 여기서 한 번 더 본다."""

    def test_build_dicts_cross_refs(self):
        doms, natures, tiers, groups, cats, sil, regions = build_dicts.build()
        cids = {c["id"] for c in cats}
        rids = {r["id"] for r in regions}
        for c in cats:
            self.assertIn(c["group"], {g["id"] for g in groups})
            for r in c["regions"]:
                self.assertIn(r, rids)
        for r in regions:
            self.assertIn(r["silhouette"], {s["id"] for s in sil})
            self.assertTrue(r["cats"])
            for c in r["cats"]:
                self.assertIn(c, cids)

    def test_domain_ids_match_lib(self):
        from kaero_lib import DOMAINS
        self.assertEqual([d["id"] for d in load_asset("domains.json")["domains"]],
                         [d["id"] for d in DOMAINS])

    def test_nature_ids_match_reports(self):
        self.assertEqual([n["id"] for n in load_asset("natures.json")["natures"]],
                         [n[0] for n in R.NATURES])

    def test_every_nature_has_its_own_colour(self):
        """계약 성격 색은 영역 색과 겹치면 안 된다 — 한 화면에 같이 나온다."""
        import kaero_page as P
        from kaero_lib import DOMAINS
        for n in load_asset("natures.json")["natures"]:
            self.assertIn(n["id"], P.NATURE_HEX, n["id"])
        self.assertFalse(set(P.NATURE_HEX.values()) & {d["hex"] for d in DOMAINS})

    def test_part_keywords_need_aero_context(self):
        """`단조품` 만으로는 항공 부품사가 아니다 — 문맥어가 가까이 있어야 채택한다."""
        tax = load_asset("parts_taxonomy.json")
        auto = match_cats(tax, [("kind", "자동차,중장비 부품(크랭크샤프트), 단조품")])
        self.assertNotIn("MAT.ALLOY", [h["cat"] for h in auto])
        aero = match_cats(tax, [("kind", "항공기 엔진용 티타늄 단조품")])
        self.assertIn("MAT.ALLOY", [h["cat"] for h in aero])

    def test_part_keywords_hit_real_product(self):
        tax = load_asset("parts_taxonomy.json")
        got = [h["cat"] for h in match_cats(tax, [("item", "B787 날개구조물 · 항공기 주익 Spar")])]
        self.assertIn("STRUCT.WING", got)


class TestPromotionRule(unittest.TestCase):
    """④ 탐색 승격 — 표 근거가 문구 근거를 이긴다."""

    def test_table_evidence_beats_transport_words(self):
        """대한항공: 운송 낱말 99 > 항공·우주 낱말 36 이지만 표에 `2. 항공우주사업` 이 있다."""
        row = {"ok": True, "hits": 36, "struct": 1, "transport": 99, "oem": {"Boeing": 1},
               "seg_aero": ["2. 항공우주사업", "군용기MROU", "무인기"]}
        self.assertTrue(SC.judge(row))

    def test_text_only_false_positive_is_rejected(self):
        """반도체 회사 본문의 "항공기 관련 LiDAR" + 다른 맥락의 Lockheed — 승격하지 않는다."""
        row = {"ok": True, "hits": 6, "struct": 0, "transport": 0,
               "oem": {"Boeing": 1, "Lockheed": 1}, "seg_aero": []}
        self.assertFalse(SC.judge(row))

    def test_carrier_without_table_evidence_is_rejected(self):
        row = {"ok": True, "hits": 3, "struct": 0, "transport": 68, "oem": {"Airbus": 1},
               "seg_aero": []}
        self.assertFalse(SC.judge(row))

    def test_unreadable_is_never_promoted(self):
        self.assertFalse(SC.judge({"ok": False, "hits": 999, "struct": 9,
                                   "seg_aero": ["항공우주"]}))


class TestUniverseRules(unittest.TestCase):
    """모집단 ② — 짧은 낱말이 만든 실측 오탐을 막는다."""

    def setUp(self):
        import kaero_universe as U
        self.U = U

    def _pick(self, product, industry="전자부품 제조업"):
        return bool(self.U._AERO.search(product)) and not bool(self.U._NOT_AERO.search(product))

    def test_broadcast_satellite_is_not_aerospace(self):
        self.assertFalse(self._pick("위성방송서비스"))
        self.assertFalse(self._pick("이동통신중계기, 위성방송(DMB)중계기(Gap-Filler)"))

    def test_gas_separation_membrane_is_not_airframe(self):
        """`기체분리막`의 기체는 gas 다."""
        self.assertFalse(self._pick("기체분리막 모듈 및 시스템"))

    def test_car_engine_parts_are_not_aero(self):
        self.assertFalse(self._pick("자동차엔진부품(ARM류,C/MBR류),자동차부품 제조"))
        self.assertFalse(self._pick("선박엔진부품"))

    def test_real_aero_products_are_picked(self):
        self.assertTrue(self._pick("위성탑재체, 위성운용국, 항공전자 등"))
        self.assertTrue(self._pick("항공기용 부품 제조 및 동체 조립"))
        self.assertTrue(self._pick("소형발사체, 로켓추진기관, 과학로켓"))
        self.assertTrue(self._pick("지상국 시스템 엔지니어링 솔루션, 위성영상"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
