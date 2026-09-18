# -*- coding: utf-8 -*-
"""계약: II-2 「주요 제품 및 서비스」 절을 부품 근거로 쓸 때의 자물쇠(ksemi_parts).

문장은 2026 반기 정기보고서 원문에서 그대로 옮겼다. 부품사 본문에는 **자기가 만드는 부품**과
**그 부품이 들어가는 자리**가 같이 적혀 있어서, 자물쇠가 없으면 뒤엣것까지 「만든다」가 된다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C                                                    # noqa: E402,F401
import ksemi_parts as PA                                               # noqa: E402

# 엔투텍 — 매출 구성표의 품목 줄(금액·비율이 붙어 있다)
N2TEC = ("품목 주요제품 매출액 비중 용도 반도체 장비 부품 등 CHAMBER, GATE VALVE 외 "
         "14,849 54.07% 반도체 제조용 장비 부품 반도체 공정용 게이트 밸브")
# 비씨엔씨 — 자기 쿼츠 부품이 **들어가는 자리**를 설명한 문장. 챔버를 만들지 않는다.
BCNC = ("주로 Chamber 하부의 plasma 노출 부위 부품 또는 웨이퍼를 챔버 내부로 이송하는 "
        "Carrier 등 보조적인 역할을 주로 수행하고 있습니다.")
# 한솔아이원스 — 앞줄은 설명, 품목 줄은 뒤에 있다(같은 낱말이 두 번 나온다)
HANSOL = ("웨이퍼 분사하는 부품 외 78,366 76.16 정밀세정코팅부문 제품 Depo shield 류 외 "
          "다수 챔버 내벽 손상 보호를 위한 부품의 세정 및 코팅 20,819 20.23 합 계")


class TestListedRowLock(unittest.TestCase):

    def test_listed_row_with_a_figure_is_accepted(self):
        self.assertGreaterEqual(PA._first_listed(N2TEC, "밸브"), 0)

    def test_a_sentence_about_where_the_part_goes_is_rejected(self):
        self.assertEqual(PA._first_listed(BCNC, "챔버"), -1)

    def test_the_listed_row_wins_over_an_earlier_description(self):
        """설명 문장이 먼저 나와도 품목 줄 자리를 고른다 — 인용이 근거가 되어야 한다."""
        text = BCNC + " " + N2TEC
        at = PA._first_listed(text, "챔버")
        self.assertEqual(at, -1, "설명만 있으면 받지 않는다")
        at2 = PA._first_listed(text, "밸브")
        self.assertGreater(at2, len(BCNC) - 1)

    def test_figures_must_be_near_not_anywhere(self):
        far = "챔버 " + "가" * 200 + " 14,849 54.07%"
        self.assertEqual(PA._first_listed(far, "챔버"), -1)

    def test_the_lock_is_a_filter_not_a_proof(self):
        """자물쇠가 거르지 못하는 줄이 남는다 — 그래서 화면에 원문을 같이 싣는다.

        한솔아이원스 「… 78,366 76.16 정밀세정코팅부문 제품 Depo shield 류 외 다수 **챔버**
        내벽 손상 보호를 위한 부품의 세정 및 코팅 20,819 20.23」. 품목은 Depo shield 이고
        챔버는 그 부품이 보호하는 대상인데, 금액이 가까워 자물쇠는 통과한다. 사람이 가를 수
        있도록 **인용이 반드시 붙어야 한다**(test_every_mention_carries_a_quote 와 같은 이유).
        """
        at = PA._first_listed(HANSOL, "챔버")
        self.assertGreaterEqual(at, 0)
        self.assertIn("세정", HANSOL[at:at + 60])


@unittest.skipUnless(C.has_asset("scan.json"), "assets/scan.json 없음")
class TestProductsCache(unittest.TestCase):

    def test_missing_cache_returns_empty_not_an_error(self):
        """캐시가 없으면 받으러 가지 않는다(무접속) — 빈 문자열이다."""
        self.assertEqual(PA.products_text("000000", "1999Q1"), "")

    def test_cached_products_section_is_plain_text_and_bounded(self):
        t = PA.products_text("227950", "2026Q2")          # 엔투텍
        if not t:
            self.skipTest("엔투텍 절 캐시 없음")
        self.assertNotIn("<", t)
        self.assertLessEqual(len(t), PA.PROD_MAX)
        self.assertIn("GATE VALVE", t.upper())


if __name__ == "__main__":
    unittest.main()
