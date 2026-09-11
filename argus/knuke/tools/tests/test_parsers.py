#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국원전·발전기자재 파서 계약(contract) 테스트 — 형식이 아니라 **화면에 실리는 값**을 지킨다.

검증하는 것(COMMON §4):
  · 단위 정규화 — 백만원 캡션 표의 값이 그대로, 억원이면 100배로 들어오는가
  · 합계/소계 판정 — 도급형 수주표의 '합계' 행이 잔고를 두 번 세지 않는가
  · 핵심 표 1종 원문 대조 — 한전기술 도급형 수주표(발주처·사업명·계약기간·계약잔액)
  · 분류 사전 교차참조 — 부품 소분류의 영역이 SVG 에 있고, 영역의 소분류가 실재하는가
  · 발전원·공급계층·계약상대 판정
  · ③ 탐색 승격 규칙

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
import knuke_contracts as KC                                         # noqa: E402
import knuke_reports as KR                                           # noqa: E402
import knuke_scan as KS                                              # noqa: E402

FIX = os.path.join(HERE, "fixtures")


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


class TestAwardOrders(unittest.TestCase):
    """한전기술 도급형 수주표 — 발주처·사업명·계약기간을 행마다 읽고 잔고를 정규화한다."""

    def setUp(self):
        tabs = KR._headered(KR._carry_units(fixture("hantech_award_orders.json")["tables"]))
        self.parsed = [o for o in (KR.parse_orders_table(t) for t in tabs) if o]
        self.o = KR._pick_orders(self.parsed)

    def test_shape_is_award(self):
        self.assertIsNotNone(self.o, "수주표를 못 읽었다")
        self.assertEqual(self.o["shape"], "award")
        self.assertTrue(self.o["has_client"])
        self.assertTrue(self.o["has_period"])

    def test_unit_million_won(self):
        """(단위 : 백만원) 이므로 계약잔액 730,000 은 730000 백만원 그대로여야 한다."""
        self.assertTrue(self.o["unit_seen"])
        row = [r for r in self.o["rows"] if "신한울" in (r["name"] or "")][0]
        self.assertEqual(row["closing"], 730000)
        self.assertEqual(row["gross"], 1050000)
        self.assertEqual(row["delivered"], 320000)

    def test_client_and_period_and_domain(self):
        row = [r for r in self.o["rows"] if "신한울" in (r["name"] or "")][0]
        self.assertEqual(row["client"], "한국수력원자력")
        self.assertEqual(row["start"], "2016-03-18")
        self.assertEqual(row["end"], "2033-10-31")
        self.assertEqual(row["domain"], "NUKE")   # 신한울 → 원자력

    def test_total_row_not_double_counted(self):
        """'합계' 행이 total 로 잡혀야 잔고 합이 두 배가 되지 않는다."""
        tot = [r for r in self.o["rows"] if r["total"]]
        self.assertEqual(len(tot), 1)
        self.assertEqual(tot[0]["closing"], 1280000)
        nonsum = sum(r["closing"] for r in self.o["rows"]
                     if not r["total"] and r["closing"] is not None)
        self.assertEqual(nonsum, 1280000)          # 730000+500000+50000

    def test_timeline_and_client_concentration(self):
        """build 이 award 행에서 발전원별 잔고·발주처 집중도·타임라인을 만든다."""
        d = {"stock": "052690", "name": "한전기술", "quarter": "2026Q2", "ok": True,
             "rcp": "X", "orders": self.o, "revenue": None, "segment_sales": None,
             "orders_all": [self.o], "raw_tables": [], "security_note": False}
        os.makedirs(os.path.join(KR.CACHE, "052690"), exist_ok=True)
        path = os.path.join(KR.CACHE, "052690", "TEST.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        try:
            res = KR.build([{"stock": "052690", "name": "한전기술", "role": "eng"}], ["TEST"])
        finally:
            os.remove(path)
        v = res["052690"]["quarters"]["TEST"]
        self.assertEqual(v["backlog"], 1280000)
        self.assertGreaterEqual(v["dom_backlog"].get("NUKE", 0), 1230000)  # 신한울+새울
        self.assertGreaterEqual(v["client_backlog"].get("한국수력원자력", 0), 1230000)
        self.assertTrue(any(t["start"] and t["end"] for t in v["timeline"]))


class TestDomainTierParty(unittest.TestCase):
    """발전원·공급계층·계약상대 판정 — 사전 로드 후."""

    def test_domain_of(self):
        self.assertEqual(KC.domain_of("신한울 3,4호기 종합설계용역"), "NUKE")
        self.assertEqual(KC.domain_of("삼척화력 1,2호기 보일러"), "THERMAL")
        self.assertEqual(KC.domain_of("서남해 해상풍력 하부구조물"), "RENEW")
        self.assertEqual(KC.domain_of("동해안변환소 HVDC 변압기"), "GRID")
        self.assertIsNone(KC.domain_of("반도체 장비 부품"))

    def test_tier_of(self):
        self.assertEqual(KC.ctype_of("신한울 원자로설비 공급"), "MAIN")
        self.assertEqual(KC.ctype_of("고리 3호기 계획예방정비공사"), "OM")
        self.assertEqual(KC.ctype_of("신한울 종합설계용역"), "ENG")
        self.assertEqual(KC.ctype_of("가동중검사 용역"), "INSP")
        self.assertEqual(KC.ctype_of("원전 해체 제염 사업"), "DECOM")

    def test_party_kind(self):
        self.assertEqual(KC.party_kind("한국수력원자력(주)")[0], "GOV")
        self.assertEqual(KC.party_kind("한국전력공사")[0], "GOV")
        self.assertEqual(KC.party_kind("두산에너빌리티(주)"), ("PRIME", "034020"))
        self.assertEqual(KC.party_kind("Westinghouse Electric Company")[0], "FOREIGN")
        self.assertEqual(KC.party_kind("공시유보")[0], "ANON")
        self.assertEqual(KC.party_kind("")[0], "UNKNOWN")

    def test_smr_tag(self):
        f = KC._fields_from_kv({"체결계약명": "i-SMR 표준설계 용역", "계약상대": "한국수력원자력"})
        self.assertTrue(f["smr"])
        self.assertEqual(f["domain"], "NUKE")


class TestDicts(unittest.TestCase):
    def test_cross_reference(self):
        dom, typ = build_dicts.build_domains(), build_dicts.build_types()
        parts, svg = build_dicts.build_parts(), build_dicts.build_svg()
        self.assertEqual(build_dicts.check(parts, svg), [])
        self.assertTrue(dom["n"] >= 5 and typ["n"] >= 8)


class TestScanPromotion(unittest.TestCase):
    def test_judge(self):
        self.assertTrue(KS.judge({"ok": True, "hits": 10, "khnp": 0, "kepco": 0}))
        self.assertTrue(KS.judge({"ok": True, "hits": 4, "khnp": 1, "kepco": 0}))
        self.assertFalse(KS.judge({"ok": True, "hits": 3, "khnp": 0, "kepco": 0}))
        self.assertFalse(KS.judge({"ok": False, "hits": 99, "khnp": 9, "kepco": 9}))  # 못 읽으면 승격 안 함


if __name__ == "__main__":
    unittest.main()
