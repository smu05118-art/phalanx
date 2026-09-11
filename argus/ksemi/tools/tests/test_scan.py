# -*- coding: utf-8 -*-
"""계약: 승격 규칙(COMMON.md §4 「승격 규칙(있다면)」).

`assets/scan.json` 은 판정에 쓴 규칙을 `rule` 문자열로 같이 싣는다 —
  "반도체 낱말 ≥8 · 타산업 낱말 < 2.5배 · 소자·팹리스 점수 < 장비×1.2 ·
   소재 점수 < 장비×1.0 · 장비 점수 ≥12 → 편입(≥4 보류)"

화면에 실린 이 문장이 곧 계약이다. 그래서 테스트는
1. **저장된 문장에서 숫자를 다시 읽어** 코드 상수와 맞는지 보고,
2. 그 숫자로 경계값을 만들어 편입/보류/배제가 문장대로 갈리는지 보고,
3. scan.json 의 **저장된 판정 전부**를 저장된 점수로 다시 판정해 같은지 본다
   (= 화면에 실린 판정이 규칙으로 재현된다).

DART 를 치지 않는다 — `judge` 는 점수 dict 만 받는 순수 함수다.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C                                          # noqa: E402

import ksemi_scan as S                                       # noqa: E402

SCAN_JSON = "scan.json"


def measured(equip=0, material=0, device=0, dist=0, semi=20, other=None):
    """`measure()` 가 내는 모양의 최소 입력. 판정은 점수만 본다."""
    return {"strong": [{"key": "etch", "stage": "etch", "strength": 2,
                        "term": "식각", "n": 3, "at": (0, 2)}],
            "weak": [],
            "scores": {"equip": equip, "material": material, "device": device,
                       "dist": dist, "semi": semi, "other": other or {}},
            "material_terms": {"포토레지스트": 1}, "device_terms": {"파운드리": 1},
            "dist_terms": {"유통": 1},
            "at": {"material": (0, 6), "device": (0, 4), "dist": (0, 2)}}


def verdict(**kw):
    return S.judge(measured(**kw), "반도체 웨이퍼 식각 장비를 제조한다.")[0]


class TestRuleString(unittest.TestCase):
    """화면·JSON 에 실린 규칙 문장과 코드 상수가 같은가."""

    def test_rule_is_built_from_the_constants(self):
        self.assertIn("≥%d" % S.SEMI_MIN, S.RULE)
        self.assertIn("≥%d" % S.EQUIP_IN, S.RULE)
        self.assertIn("(≥%d 보류)" % S.EQUIP_HOLD, S.RULE)

    @unittest.skipUnless(C.has_asset(SCAN_JSON), "assets/scan.json 없음")
    def test_stored_rule_matches_the_code(self):
        self.assertEqual(C.asset(SCAN_JSON)["rule"], S.RULE)

    @unittest.skipUnless(C.has_asset(SCAN_JSON), "assets/scan.json 없음")
    def test_numbers_read_back_from_the_stored_rule(self):
        """저장된 문장에서 숫자를 되읽어 상수와 대조한다(문장만 고치는 사고 방지)."""
        rule = C.asset(SCAN_JSON)["rule"]
        ge = [int(x) for x in re.findall(r"≥(\d+)", rule)]
        self.assertEqual(ge, [S.SEMI_MIN, S.EQUIP_IN, S.EQUIP_HOLD])
        self.assertEqual(float(re.search(r"<\s*([\d.]+)배", rule).group(1)),
                         S.OTHER_RATIO)
        margins = [float(x) for x in re.findall(r"장비×([\d.]+)", rule)]
        self.assertEqual(margins, [S.DEVICE_MARGIN, S.MATERIAL_MARGIN])


class TestVerdictBoundaries(unittest.TestCase):
    """경계값 — 규칙 문장 그대로."""

    def test_equip_score_boundaries(self):
        self.assertEqual(verdict(equip=S.EQUIP_IN), "편입")
        self.assertEqual(verdict(equip=S.EQUIP_IN + 1), "편입")
        self.assertEqual(verdict(equip=S.EQUIP_IN - 1), "보류")
        self.assertEqual(verdict(equip=S.EQUIP_HOLD), "보류")
        self.assertEqual(verdict(equip=S.EQUIP_HOLD - 1), "배제")
        self.assertEqual(verdict(equip=0), "배제")

    def test_semiconductor_context_is_required_first(self):
        """반도체 낱말이 모자라면 장비 점수가 아무리 높아도 배제다."""
        self.assertEqual(verdict(equip=99, semi=S.SEMI_MIN - 1), "배제")
        self.assertEqual(verdict(equip=99, semi=S.SEMI_MIN), "편입")

    def test_other_industry_ratio(self):
        semi = 10
        edge = int(semi * S.OTHER_RATIO)                 # 25 — 같은 값은 배제 아님
        self.assertEqual(verdict(equip=40, semi=semi, other={"자동차": edge}), "편입")
        self.assertEqual(verdict(equip=40, semi=semi, other={"자동차": edge + 1}), "배제")

    def test_device_margin(self):
        """소자·팹리스 점수가 장비×1.2 를 넘으면 고객 업종이다."""
        self.assertEqual(verdict(equip=10, device=12), "보류")      # 12 == 10×1.2
        self.assertEqual(verdict(equip=10, device=13), "배제")
        self.assertEqual(verdict(equip=10, device=3), "보류")       # 4 미만은 보지 않는다

    def test_material_margin(self):
        self.assertEqual(verdict(equip=10, material=10), "보류")    # 10 == 10×1.0
        self.assertEqual(verdict(equip=10, material=11), "배제")
        self.assertEqual(verdict(equip=10, material=3), "보류")

    def test_distributor_rule_needs_a_low_equip_score(self):
        self.assertEqual(verdict(equip=S.EQUIP_HOLD - 1, dist=4), "배제")
        self.assertEqual(verdict(equip=S.EQUIP_HOLD, dist=99), "보류")

    def test_reason_is_never_empty(self):
        for kw in ({"equip": 20}, {"equip": 5}, {"equip": 0},
                   {"equip": 99, "semi": 0}, {"equip": 10, "device": 40}):
            v, reason, _q = S.judge(measured(**kw), "반도체 장비")
            self.assertIn(v, ("편입", "보류", "배제"))
            self.assertTrue(reason.strip(), kw)


@unittest.skipUnless(C.has_asset(SCAN_JSON), "assets/scan.json 없음")
class TestStoredVerdictsAreReproducible(unittest.TestCase):
    """저장된 점수 → 저장된 판정. 화면에 실린 판정이 규칙으로 재현되어야 한다."""

    @classmethod
    def setUpClass(cls):
        cls.d = C.asset(SCAN_JSON)

    def test_every_row_reproduces(self):
        bad, n = [], 0
        for r in self.d["rows"]:
            if not r.get("ok") or not r.get("scores"):
                continue
            n += 1
            m = {"strong": [], "weak": [], "scores": r["scores"],
                 "material_terms": {}, "device_terms": {}, "dist_terms": {},
                 "at": {"material": None, "device": None, "dist": None}}
            got = S.judge(m, "")[0]
            # 지정(SEED) 종목은 판정하지 않고 편입한다 — 규칙 결과는 따로 남아 있다.
            want = (r.get("judge_if_scanned") if r.get("source") == "지정"
                    else r["verdict"])
            if got != want:
                bad.append((r["stock"], r["name"], want, got, r["scores"]))
        self.assertGreater(n, 100, "검증 대상 행이 너무 적다")
        self.assertEqual(bad, [])

    def test_seed_rows_are_admitted_without_being_judged(self):
        seeds = [r for r in self.d["rows"] if r.get("source") == "지정"]
        self.assertTrue(seeds)
        for r in seeds:
            self.assertEqual(r["verdict"], "편입", r["stock"])
            self.assertIn("지정", r["reason"])

    def test_distribution_matches_the_rows(self):
        got = {}
        for r in self.d["rows"]:
            got[r["verdict"]] = got.get(r["verdict"], 0) + 1
        self.assertEqual(got, self.d["dist"])
        self.assertEqual(len(self.d["rows"]), self.d["n"])

    def test_every_verdict_has_a_reason(self):
        bad = [r["stock"] for r in self.d["rows"] if not (r.get("reason") or "").strip()]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
