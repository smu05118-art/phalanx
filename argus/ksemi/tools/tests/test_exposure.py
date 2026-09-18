# -*- coding: utf-8 -*-
"""메모리/비메모리 노출(스펙 「산업 특성 5」) — 무엇을 세고 무엇을 세지 않는가.

두 계약을 지킨다.
  ① **`비메모리` 안의 `메모리`를 메모리로 세지 않는다.** 리노공업 II-2 의
     *"반도체(메모리 및 비메모리) 테스트"* 는 메모리 1 · 비메모리 1이어야 한다.
  ② **산업 전망 문단을 세지 않는다.** 유니셈 *"최근 메모리 반도체의 세계적 공급 과잉…"*
     은 사업의 개요 절에 있는 시장 이야기지 그 회사의 노출이 아니다 — `products`·`sales`
     절만 센다(LOGIC §7 의 'II-2 근거는 매출 구성표의 품목 줄일 때만' 과 같은 규칙).

낱말이 없으면 `미확인`이다. 0%도, '메모리 아님'도 아니다(COMMON §0-1).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C                                          # noqa: E402

import ksemi_exposure as X                                   # noqa: E402

LEENO = "IC TEST SOCKET 류 반도체(메모리 및 비메모리) 테스트 PACKAGE용 장비의 소모성 부품"
UNISEM = ("최근 메모리 반도체의 세계적 공급 과잉과 기업간 가격 경쟁이 치열해짐에 따라 "
          "국내 장비업계의 경쟁력 제고필요성이 증대되고 있습니다.")
HANMI = "HBM4 제조용 'TC BONDER 4.5 GRIFFIN' 장비 2026-06-08 2026-09-02"


class TestWords(unittest.TestCase):

    def test_bi_memory_is_not_memory(self):
        self.assertEqual(X.MEM.findall("비메모리"), [])
        self.assertEqual(len(X.FND.findall("비메모리")), 1)

    def test_leeno_line_is_one_each(self):
        h = X.hits({"products": LEENO})
        self.assertEqual((h["mem"]["n"], h["fnd"]["n"]), (1, 1), LEENO)
        self.assertEqual(X.verdict_of(h["mem"]["n"], h["fnd"]["n"]), "양쪽")

    def test_memory_synonyms(self):
        for w in ("메모리", "DRAM", "디램", "D램", "낸드", "NAND", "HBM", "HBM4", "SSD"):
            self.assertEqual(X.hits({"products": "장비 %s 검사" % w})["mem"]["n"], 1, w)

    def test_foundry_synonyms(self):
        for w in ("파운드리", "Foundry", "비메모리", "시스템 반도체", "시스템LSI", "로직 반도체"):
            self.assertEqual(X.hits({"products": "%s 고객" % w})["fnd"]["n"], 1, w)

    def test_hanmi_order_row_counts(self):
        # 수주표 품목 줄(II-4)은 그 회사의 칸이다 — HBM4 장비 한 줄로 메모리가 잡혀야 한다.
        h = X.hits({"sales": HANMI})
        self.assertEqual(h["mem"]["n"], 1)
        self.assertEqual(h["mem"]["quotes"][0]["sec_ko"], "II-4 매출실적")


class TestSectionScope(unittest.TestCase):

    def test_industry_outlook_sections_are_ignored(self):
        for key in ("overview", "etc", "ii"):
            h = X.hits({key: UNISEM})
            self.assertEqual((h["mem"]["n"], h["fnd"]["n"]), (0, 0), key)

    def test_same_sentence_in_products_counts(self):
        # 같은 문장이라도 주요제품 절에 있으면 센다 — 절이 판정의 전부다.
        self.assertEqual(X.hits({"products": UNISEM})["mem"]["n"], 1)

    def test_verdict_none_is_unknown_not_zero(self):
        self.assertEqual(X.verdict_of(0, 0), "미확인")
        self.assertEqual(X.verdict_of(3, 0), "메모리")
        self.assertEqual(X.verdict_of(0, 2), "비메모리·파운드리")
        self.assertEqual(X.verdict_of(1, 1), "양쪽")


class TestQuotes(unittest.TestCase):

    def test_quotes_do_not_repeat_one_sentence(self):
        txt = "당사의 주요 제품은 크게 메모리컴포넌트테스터, 메모리모듈테스터, 고속번인테스터입니다."
        h = X.hits({"products": txt})
        self.assertEqual(h["mem"]["n"], 2, "낱말은 둘 다 센다")
        self.assertEqual(len(h["mem"]["quotes"]), 1, "인용은 한 문장만 싣는다")

    def test_quote_cap(self):
        txt = " ".join(["메모리 검사 장비." + "가" * X.QUOTE_GAP for _ in range(10)])
        self.assertEqual(len(X.hits({"products": txt})["mem"]["quotes"]), X.MAX_QUOTES)


class TestAgainstBuiltAsset(unittest.TestCase):
    """exposure.json 이 있으면 그 값이 지금 규칙과 같은지 본다(자산이 있을 때만)."""

    @classmethod
    def setUpClass(cls):
        if not C.has_asset("exposure.json"):
            raise unittest.SkipTest("exposure.json 이 없다 — ksemi_exposure.py --write 먼저")
        cls.d = C.asset("exposure.json")

    def test_verdict_matches_counts(self):
        for r in self.d["rows"]:
            self.assertEqual(r["verdict"], X.verdict_of(r["mem"]["n"], r["fnd"]["n"]),
                             r["stock"])

    def test_quotes_come_from_product_or_sales_sections(self):
        for r in self.d["rows"]:
            for side in ("mem", "fnd"):
                for q in r[side]["quotes"]:
                    self.assertIn(q["sec"], X.SECTIONS, "%s %s" % (r["stock"], q["sec"]))

    def test_quoted_word_is_in_quote(self):
        for r in self.d["rows"]:
            for side, rx in (("mem", X.MEM), ("fnd", X.FND)):
                for q in r[side]["quotes"]:
                    self.assertTrue(rx.search(q["quote"]),
                                    "%s %s 인용에 낱말이 없다" % (r["stock"], side))

    def test_unknown_rows_have_no_quotes(self):
        for r in self.d["rows"]:
            if r["verdict"] == "미확인":
                self.assertEqual(r["mem"]["quotes"] + r["fnd"]["quotes"], [], r["stock"])


if __name__ == "__main__":
    unittest.main()
