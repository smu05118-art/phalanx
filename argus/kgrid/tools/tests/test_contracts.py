#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kgrid_contracts 계약 테스트 — **원문 조각(fixtures/*.html)이 기준**이다.

형식이 아니라 계약을 본다(COMMON §4): 원문에 적힌 값과 파서가 뽑은 값이 같은가.
fixture 는 DART 수시공시 본문 HTML을 그대로 잘라 넣은 것이고, 각 테스트의 주석에
원문 문구를 인용해 둔다 — 파서를 고칠 때 무엇을 지켜야 하는지 알 수 있게.

    cd argus/kgrid/tools && python3 -m unittest discover -s tests
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import kgrid_contracts as C          # noqa: E402

FIX = os.path.join(HERE, "fixtures")


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class KospiForm(unittest.TestCase):
    """유가증권 양식 — HD현대일렉트릭 267260 / 20260507800238.

    원문:
      - 체결계약명            765KV 초고압 변압기 및 리액터
        계약금액(원)          173,000,000,000
        계약상대              HD Hyundai Electric America Corporation (회사와의 관계 `자회사`)
        기타 …               「계약액 USD 117,639,663를 원화환산하여 기재하였음」
                             「미국 MISO·SPP 권역의 765kV급 송전망 기반 대형 유틸리티 기업로부터
                               수주받은 후 당사로 재 발주한 공급계약임」
    """

    @classmethod
    def setUpClass(cls):
        cls.r = C.parse_contract(fixture("267260_20260507800238.html"),
                                 "20260507800238", "단일판매ㆍ공급계약체결", "267260")

    def test_name_and_amount(self):
        self.assertEqual(self.r["name"], "765KV 초고압 변압기 및 리액터")
        self.assertEqual(self.r["amt_krw_m"], 173000.0)          # 원 → 백만원
        self.assertEqual(self.r["rev_ratio"], 4.24)

    def test_currency_from_note(self):
        # 금액 칸은 원화지만 계약 통화는 USD다. 환산하지 않고 원통화를 함께 남긴다.
        self.assertEqual(self.r["cur"], "USD")
        self.assertEqual(self.r["amt"], 117639663.0)
        # 내재환율 = 173,000,000,000 / 117,639,663 ≒ 1,470.6 (원문 적용환율 1,470.50)
        self.assertAlmostEqual(self.r["fx"], 1470.59, places=1)

    def test_dates(self):
        self.assertEqual(self.r["signed"], "2026-05-06")
        self.assertEqual(self.r["start"], "2026-05-06")
        self.assertEqual(self.r["end"], "2029-08-31")
        self.assertEqual(self.r["years"], 3.3)

    def test_affiliate_reorder_finds_end_customer(self):
        # 계약상대가 자회사(재발주)라 상대 이름으로는 수요처를 알 수 없다 — 주석을 먼저 본다.
        self.assertTrue(self.r["affiliate"])
        self.assertEqual(self.r["demand"], "na_utility")
        self.assertEqual(self.r["demand_src"], "note")

    def test_product(self):
        self.assertEqual(self.r["product"], "ehv")               # 765KV 초고압 변압기

    def test_not_withheld(self):
        self.assertFalse(self.r["withheld"])                     # 유보사유·유보기한 모두 `-`


class KosdaqForm(unittest.TestCase):
    """코스닥 양식 — 제룡전기 033100 / 20251222900254. 라벨이 통째로 다르다.

    원문:
      1. 판매ㆍ공급계약 내용   미국 PUBLIC SERVICE ELECTRIC AND GAS COMPANY (이하 PSE&G사)
                             배전 변압기 공급 계약 체결
      2. 계약내역 계약금액 총액(원)  44,115,781,328   (확정 계약금액과 같음)
      3. 계약상대방            Public Service Electric and Gas Company
      기타 …                  「상기 계약금액은 USD29,852,335.45이며 … 1USD=1,477.80원」
    """

    @classmethod
    def setUpClass(cls):
        cls.r = C.parse_contract(fixture("033100_20251222900254.html"),
                                 "20251222900254", "단일판매ㆍ공급계약체결", "033100")

    def test_name_comes_from_kosdaq_label(self):
        # 유가증권의 `- 체결계약명` 라벨이 없다. 이 양식을 안 보면 계약명이 빈칸이 된다.
        self.assertIn("PUBLIC SERVICE ELECTRIC AND GAS COMPANY", self.r["name"])

    def test_amount_total_label(self):
        self.assertEqual(self.r["amt_krw_m"], 44115.781)
        self.assertEqual(self.r["cur"], "USD")
        self.assertEqual(self.r["amt"], 29852335.45)

    def test_counterparty_and_demand(self):
        self.assertEqual(self.r["party"], "Public Service Electric and Gas Company")
        self.assertFalse(self.r["affiliate"])
        self.assertEqual(self.r["demand"], "na_utility")         # 계약상대 실명으로 판정
        self.assertEqual(self.r["demand_src"], "party")

    def test_product_is_distribution_transformer(self):
        self.assertEqual(self.r["product"], "dist_tr")           # `배전 변압기`


class DomesticKrw(unittest.TestCase):
    """원화 계약 — 선도전기 007610 / 20250319800230.

    원문: 계약상대 `한국수력원자력 주식회사`, 공급지역 `국내`,
          기타 「상기 계약금액은 공급가액이 \\51,818,200,000원이며 부가세(10%) 포함 금액입니다」
    주석에 원화 금액이 또 적혀 있지만 통화 토큰이 없다 — USD로 오독하면 안 된다.
    """

    @classmethod
    def setUpClass(cls):
        cls.r = C.parse_contract(fixture("007610_20250319800230.html"),
                                 "20250319800230", "단일판매ㆍ공급계약체결", "007610")

    def test_krw_kept(self):
        self.assertEqual(self.r["cur"], "KRW")
        self.assertEqual(self.r["amt"], 57000020000)
        self.assertIsNone(self.r["fx"])

    def test_demand_is_kepco_family(self):
        self.assertEqual(self.r["party"], "한국수력원자력 주식회사")
        self.assertEqual(self.r["demand"], "kepco")

    def test_product_switchgear(self):
        self.assertEqual(self.r["product"], "switchgear")        # `480V 전동기 제어반`


class CurrencyGuard(unittest.TestCase):
    """통화 오독 방어 — 같은 주석에 **적용환율**이 함께 적힌다(전력기기 수출계약의 상례).

    내재환율(원화금액÷외화금액)이 상식 범위에 들어야만 금액으로 인정한다(fail-closed).
    """

    def test_rate_number_is_not_taken_as_amount(self):
        note = ("상기 계약금액은 계약액 USD 117,639,663를 원화환산하여 기재하였음. "
                "(적용환율 : 계약일자 KEB하나은행 최초고시 매매기준환율 1 USD = 1,470,50원)")
        amt, cur, fx, _ = C.currency_amount(note, 173000000000)
        self.assertEqual((amt, cur), (117639663.0, "USD"))
        self.assertTrue(1400 < fx < 1550)

    def test_rate_only_note_yields_nothing(self):
        # 환율만 있고 계약금액이 외화로 적히지 않은 주석 — 통화를 만들어내지 않는다.
        note = "환율은 1 USD = 1,411.00원을 적용하였습니다."
        self.assertEqual(C.currency_amount(note, 51197779428)[:2], (None, None))

    def test_krw_note_is_not_usd(self):
        note = "상기 계약금액은 공급가액이 \\51,818,200,000원이며 부가세(10%) 포함 금액입니다."
        self.assertEqual(C.currency_amount(note, 57000020000)[:2], (None, None))

    def test_no_note_no_currency(self):
        self.assertEqual(C.currency_amount("", 1000)[:2], (None, None))


class Classify(unittest.TestCase):
    """분류 축 — 어휘는 실제 수집한 계약명·계약상대에서 뽑았다(FINDINGS §7)."""

    def test_product_order_matters(self):
        # `가스절연개폐장치(GIS)`는 개폐기가 아니라 차단기 갈래다(스펙 §분류).
        self.assertEqual(C.product_of("22.9kV 가스절연개폐장치(GIS) 공급"), "breaker")
        self.assertEqual(C.product_of("자동부하개폐기 공급계약"), "switch")
        # 초고압이 일반 변압기보다 먼저다.
        self.assertEqual(C.product_of("765kV 변압기"), "ehv")
        self.assertEqual(C.product_of("주상변압기 구매"), "dist_tr")

    def test_product_unknown_stays_empty(self):
        # `리액터`는 초고압 분로리액터인지 인버터용인지 원문으로 못 가른다 — 비운다.
        self.assertIsNone(C.product_of("리액터 공급"))
        self.assertIsNone(C.product_of(""))

    def test_demand_unknown_stays_none(self):
        self.assertEqual(C.demand_of("A사", "", "", ""), (None, ""))

    def test_country_alone_is_not_a_demand(self):
        # 나라 이름은 수요처가 아니다 — 이집트 계약이라도 발주처가 터널청이면 중동 전력청이
        # 아니다(엘에스일렉트릭 20251017800268 실측). 지역은 지역 축으로만 싣는다.
        self.assertEqual(C.demand_of("Bombardier Transportation (BT)", "-",
                                     "본 계약은 이집트터널청(NAT)에서 발주하여 진행하는 "
                                     "모노레일 라인 구축의 E&M 과업 계약자인 BT에 당사가 "
                                     "전력공급 및 배전 시스템을 공급하는 사업임",
                                     "delivery of Power Supply Monorail"), (None, ""))
        self.assertEqual(C.region_of("이집트"), "me")
        self.assertEqual(C.region_of("국내"), "dom")
        self.assertEqual(C.region_of("미국"), "na")
        self.assertIsNone(C.region_of("신청주 변전소"))

    def test_note_carries_the_end_customer(self):
        # 관계사 재발주 건은 주석에만 최종 수요처가 있다(위 KospiForm 과 같은 근거).
        key, src = C.demand_of("LS ELECTRIC AMERICA Inc.", "자회사",
                               "- 본 계약은 미국 Big Tech Data Center 에 공급하는 PJT로서, "
                               "Power Supply System을 수주한 LS ELECTRIC AMERICA Inc.에 "
                               "당사가 전력공급 및 배전 시스템을 공급하는 사업임",
                               "Big Tech Data Center PJT")
        self.assertEqual((key, src), ("datacenter", "note"))

    def test_generic_construction_is_not_industrial(self):
        # 계약상대가 건설사여도 물건이 공동주택 수배전반이면 '산업 플랜트'가 아니다(광명전기 실측).
        self.assertEqual(C.demand_of("주식회사 주성산업개발", "-", "",
                                     "전주시 효자동 본아르떼 공동주택 신축공사"), (None, ""))
        # 반면 원문이 반도체 팹을 이름으로 말하면 산업 플랜트다.
        self.assertEqual(C.demand_of("에스케이하이닉스(주)", "-", "",
                                     "M15X Ph-3 Project_저압 Panel 제작 및 설치")[0], "industrial")


class DictCrossRef(unittest.TestCase):
    """분류 사전 교차참조 — 파서가 쓰는 키가 kgrid_lib 의 축과 같아야 한다(COMMON §4).

    한쪽만 고치면 화면에서 라벨 없는 칩이 생긴다.
    """

    def test_keys_are_known(self):
        import kgrid_lib
        self.assertTrue(set(k for k, _ in C._PRODUCT_RULES) <= set(kgrid_lib.PRODUCT_ORDER))
        self.assertTrue(set(k for k, _ in C._DEMAND_RULES) <= set(kgrid_lib.DEMAND_ORDER))
        self.assertTrue(set(k for _, k in C._REGION_RULES) <= set(kgrid_lib.REGION_ORDER))

    def test_every_demand_key_has_a_rule(self):
        # 스펙이 세운 6갈래 모두에 판정 어휘가 있어야 한다 — 빈 갈래는 화면에서 영원히 0이다.
        import kgrid_lib
        self.assertEqual(set(k for k, _ in C._DEMAND_RULES), set(kgrid_lib.DEMAND_ORDER))


class Dedup(unittest.TestCase):
    """정정공시 — 같은 계약의 최신본만 집계에 쓰고 원본은 supersedes 로 문다."""

    def test_key_groups_correction_with_original(self):
        a = {"stock": "017040", "rcp": "20250313800415", "name": "수배전반 공급",
             "signed": "2025-03-13", "party": "한국전력공사"}
        b = {"stock": "017040", "rcp": "20250319801152", "name": "수배전반  공급",
             "signed": "2025-03-13", "party": "한국전력공사"}
        self.assertEqual(C._dedup_key(a), C._dedup_key(b))       # 공백 차이는 같은 계약

    def test_key_falls_back_to_party_when_name_is_boilerplate(self):
        a = {"stock": "062040", "rcp": "1", "name": "기타 판매ㆍ공급계약",
             "signed": "2026-01-02", "party": "TMEIC USA"}
        self.assertIn("TMEIC", C._dedup_key(a)[1])


if __name__ == "__main__":
    unittest.main()
