#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""7사 전수 재적재 충실도 회귀 테스트 (실제 DART 2026.06 반기보고서 fixture).

`tests/fixtures/`에 있는 회사(sct·hec)는 test_build.py가 사업장 단위로 엄밀 대조한다.
이 파일은 **파서 계약**을 회귀 방어한다 — 회사별 표 방언(단위 캡션·열 별칭·연결/별도
판정·분류 열 vs 공사명 열)을 놓치면 즉시 실패하도록 실측값을 못박아 둔다.

이 값들은 2026Q2 원문에서 실제로 관측된 것이며, 여기가 깨지면 파서가 표를 놓친 것이다.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, TOOLS)

from kce_parse import parse_ii4, parse_p8, unit_scale, _basis_of  # noqa: E402


def _fx(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class TestUnitScale(unittest.TestCase):
    """표 단위는 회사마다 다르다 — 삼성E&A는 억원, 나머지는 백만원."""

    def test_scale_table(self):
        self.assertEqual(unit_scale("(단위 : 백만원)"), 1.0)
        self.assertEqual(unit_scale("(단위 : 억원)"), 100.0)
        self.assertEqual(unit_scale("(단위:천원)"), 0.001)
        self.assertEqual(unit_scale("(단위 : 십억원)"), 1000.0)
        self.assertEqual(unit_scale(""), 1.0)          # 캡션 없으면 백만원 가정
        # '원'이 '백만원'보다 먼저 매칭돼선 안 된다
        self.assertEqual(unit_scale("기준일 2026-06-30 (단위 : 백만원)"), 1.0)


class TestBasisDetection(unittest.TestCase):
    """III-8 연결/별도 판정 — 본문 서술의 '연결회사는'에 낚이면 안 된다."""

    def test_marker_wins_over_prose(self):
        lead = "…연결회사는 발주처와 협의를 진행중입니다.\n\n(2) 별도 기준"
        self.assertEqual(_basis_of(lead), "별도")
        self.assertEqual(_basis_of("라. 수주계약 현황(1) 연결 기준"), "연결")
        self.assertIsNone(_basis_of("특이사항 없음"))

    def test_sct_two_tables(self):
        r = parse_p8(_fx("sct_기타재무_진행률수주.html"))
        self.assertEqual([t["basis"] for t in r["tables"]], ["연결", "별도"])


class TestII4Dialects(unittest.TestCase):
    """회사별 II-4 표 방언이 전부 파싱되는지."""

    def test_sct_detail_table(self):
        r = parse_ii4(_fx("sct_상세표_건설수주.html"))
        self.assertEqual(r["unknown_headers"], [])
        self.assertEqual(sum(t["n"] for t in r["tables"]), 84)
        # 품목('건설사업')이 아니라 공사명 열을 nm으로 잡아야 한다
        nms = {x["nm"] for t in r["tables"] for x in t["rows"]}
        self.assertNotIn("건설사업", nms)
        self.assertIn("카타르 Facility E IWPP", nms)

    def test_hec_multi_entity_tables(self):
        """현대건설은 법인별로 표가 나뉜다 — 하나만 잡으면 조용히 데이터가 사라진다."""
        r = parse_ii4(_fx("hec_수주상황.html"))
        self.assertEqual(r["unknown_headers"], [])
        self.assertGreaterEqual(len(r["tables"]), 4)
        self.assertEqual(sum(t["n"] for t in r["tables"]), 126)


if __name__ == "__main__":
    unittest.main()
