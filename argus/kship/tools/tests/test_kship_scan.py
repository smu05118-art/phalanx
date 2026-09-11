# -*- coding: utf-8 -*-
"""kship_scan — 후보 풀·승격 규칙은 순수 함수라 DART 없이 검증한다."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kship_scan as S  # noqa: E402


class TestPool(unittest.TestCase):
    def test_pool_filters_by_product_and_industry(self):
        recs = [
            {"stock": "187790", "name": "나노", "industry": "기초 화학물질 제조업", "product": "SCR촉매"},          # EXTRA
            {"stock": "044490", "name": "태웅", "industry": "기타 금속 가공제품 제조업", "product": "자유형단조품"},  # 어휘 '단조'
            {"stock": "090080", "name": "평화산업", "industry": "자동차 신품 부품 제조업", "product": "호스류"},     # 업종 제외
            {"stock": "064820", "name": "케이프", "industry": "선박 및 보트 건조업", "product": "실린더라이너"},     # 이미 모집단
            {"stock": "000001", "name": "무관", "industry": "특수 목적용 기계 제조업", "product": "공작기계"},
        ]
        got = {r["stock"] for r in S.pool(recs, [{"stock": "064820"}])}
        self.assertEqual(got, {"187790", "044490"})

    def test_promotion_rule_is_fail_closed(self):
        ok = lambda d: bool(d.get("ok") and (sum((d.get("mentions") or {}).values()) >= S.PROMOTE_MENTIONS
                                             or d.get("marine_hits", 0) >= S.PROMOTE_HITS))
        self.assertTrue(ok({"ok": True, "mentions": {"042660": 3}, "marine_hits": 6}))
        self.assertTrue(ok({"ok": True, "mentions": {}, "marine_hits": 40}))
        self.assertFalse(ok({"ok": True, "mentions": {"329180": 1}, "marine_hits": 7}))
        self.assertFalse(ok({"ok": False, "mentions": {"329180": 9}, "marine_hits": 99}))   # II 절을 못 읽으면 승격 없음

    def test_role_for(self):
        self.assertEqual(S.role_for({"industry": "1차 철강 제조업", "product": "후판"}, {}), "steel")
        self.assertEqual(S.role_for({"industry": "일반 목적용 기계 제조업", "product": "선박용 엔진"}, {"marine_terms": {"박용": 3}}), "engine")
        self.assertEqual(S.role_for({"industry": "기초 화학물질 제조업", "product": "SCR촉매"}, {"marine_terms": {"선박": 9}}), "equip")


if __name__ == "__main__":
    unittest.main()
