# -*- coding: utf-8 -*-
"""중국 노출(스펙 「산업 특성 6」) — 화면에 실리는 값이 원문 칸과 같은가.

이 지표는 **매출 비중이 아니다.** II-4 매출실적은 수출/내수까지만 나누는 회사가
대부분이라 지역별 매출이 원문에 없다. 대신 「단일판매ㆍ공급계약체결」의
`4. 판매ㆍ공급지역` 칸이 원문 근거다(주성엔지니어링 `20210204900782` = 중국).
그래서 화면 문구도 '공시 계약 금액 기준'이라 적는다 — 여기서 그 계약을 지킨다.

함정 둘:
  · 금액 칸을 못 읽은 계약을 분모에 0으로 넣으면 비중이 부풀거나 0%로 찍힌다
    → 분모가 0이면 `share=None`(fail-closed, COMMON §0-2).
  · 대만·말레이시아 같은 다른 해외 지역을 중국으로 세면 안 된다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C                                          # noqa: E402

from ksemi_page import china_exposure                        # noqa: E402


def con(region, amt=None, **kw):
    """계약 한 줄(ksemi_contracts 가 내는 모양 중 이 지표가 쓰는 칸만)."""
    import ksemi_contracts as K
    r = {"region": region, "amt_mkrw": amt}
    r["region_cn"] = bool(K._CN.search(region or ""))
    r.update(kw)
    return r


class TestChinaExposure(unittest.TestCase):

    def test_share_is_amount_weighted(self):
        e = china_exposure([con("중국", 300.0), con("한국", 100.0)])
        self.assertEqual(e["n"], 1)
        self.assertEqual(e["amt"], 300.0)
        self.assertAlmostEqual(e["share"], 75.0)

    def test_unreadable_amount_counts_as_case_only(self):
        # 금액을 못 읽은 중국 계약: 건수엔 들어가고 금액·분모엔 안 들어간다.
        e = china_exposure([con("중국", None), con("한국", 100.0)])
        self.assertEqual(e["n"], 1)
        self.assertEqual(e["amt"], 0)
        self.assertAlmostEqual(e["share"], 0.0)

    def test_no_known_amount_is_none_not_zero(self):
        e = china_exposure([con("중국", None)])
        self.assertEqual(e["n"], 1)
        self.assertIsNone(e["share"], "분모가 0이면 0%가 아니라 미산출이어야 한다")

    def test_empty(self):
        e = china_exposure([])
        self.assertEqual((e["n"], e["n_all"], e["amt"]), (0, 0, 0))
        self.assertIsNone(e["share"])

    def test_other_overseas_regions_are_not_china(self):
        for region in ("대만", "말레이시아", "태국", "베트남", "일본", "한국", "대한민국"):
            self.assertEqual(china_exposure([con(region, 10.0)])["n"], 0, region)

    def test_chinese_city_and_english_spellings(self):
        for region in ("중국", "中國 西安", "China", "PRC", "우시", "시안"):
            self.assertEqual(china_exposure([con(region, 10.0)])["n"], 1, region)

    def test_regions_are_deduped_and_sorted(self):
        e = china_exposure([con("중국", 1.0), con("중국", 2.0), con("China", 3.0)])
        self.assertEqual(e["regions"], ["China", "중국"])
        self.assertEqual(e["n"], 3)


class TestAgainstCollectedContracts(unittest.TestCase):
    """수집된 contracts.json 원문 칸과 대조(자산이 있을 때만)."""

    @classmethod
    def setUpClass(cls):
        if not C.has_asset("contracts.json"):
            raise unittest.SkipTest("contracts.json 이 없다 — ksemi_contracts.py --write 먼저")
        cls.rows = C.asset("contracts.json")["rows"]

    def test_flag_matches_region_text(self):
        # 저장된 region_cn 이 지역 칸 문구와 어긋나면 화면 숫자가 원문과 달라진다.
        import ksemi_contracts as K
        for r in self.rows:
            self.assertEqual(bool(r.get("region_cn")),
                             bool(K._CN.search(r.get("region") or "")),
                             "%s %s" % (r["rcp"], r.get("region")))

    def test_juseong_china_contract_is_counted(self):
        # 주성엔지니어링 20210204900782 — `4. 판매ㆍ공급지역`=중국 (PROGRESS §1-1 서식)
        mine = [r for r in self.rows if r["stock"] == "036930"]
        if not mine:
            self.skipTest("주성엔지니어링 계약이 아직 수집되지 않았다")
        e = china_exposure(mine)
        self.assertGreaterEqual(e["n"], 1)
        self.assertIn("중국", e["regions"])
        self.assertIsNotNone(e["share"])
        self.assertTrue(0 < e["share"] <= 100)

    def test_share_never_exceeds_100(self):
        by = {}
        for r in self.rows:
            by.setdefault(r["stock"], []).append(r)
        for stock, rows in by.items():
            e = china_exposure(rows)
            if e["share"] is not None:
                self.assertTrue(0 <= e["share"] <= 100, "%s %s" % (stock, e["share"]))


if __name__ == "__main__":
    unittest.main()
