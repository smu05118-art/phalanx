# -*- coding: utf-8 -*-
"""계약: 분류 사전 교차참조(COMMON.md §4).

`assets/stages.json` 은 스스로 이렇게 선언한다 —
  "낱말은 ksemi_universe.EQUIP_WORDS 가 진실의 원천이고 이 파일은 단계 배정만 한다.
   낱말을 새로 쓰려면 EQUIP_WORDS 에 먼저 넣어라 (요청 목록은 unmatched.extra_words)."

그러므로 계약은 둘이다.
1. 단계 사전이 쓰는 낱말은 **EQUIP_WORDS 에 있거나, 없다면 `unmatched.extra_words`
   에 공개 요청으로 적혀 있어야 한다**. 어느 쪽도 아닌 낱말(=조용히 늘어난 어휘)은 0개.
2. `stage_tags.json` 이 쓰는 단계 키는 **stages.json 의 13단계 중 하나**여야 한다.

여기에 build_dicts 자신의 교차검증(`cross_check`)이 오류 0건인지도 확인한다
(팔레트 슬롯 ↔ 단계, 부품 낱말 ↔ 사전, 미배정 낱말의 사유 기재 — fail-closed).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C                                          # noqa: E402

from ksemi_universe import EQUIP_WORDS                       # noqa: E402

STAGES_JSON = "stages.json"
TAGS_JSON = "stage_tags.json"
N_STAGES = 13                     # 스펙 「산업 특성 4」 12단계 + service


def _norm(w):
    return (w or "").lower().strip()


@unittest.skipUnless(C.has_asset(STAGES_JSON), "assets/stages.json 없음")
class TestStagesDict(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = C.asset(STAGES_JSON)
        cls.keys = [s["key"] for s in cls.d["stages"]]
        cls.words = set()
        cls.part_words = set()
        for s in cls.d["stages"]:
            cls.words |= set(s["words"]["strong"]) | set(s["words"]["weak"])
            for p in s["parts"]:
                cls.part_words |= {_norm(w) for w in p["words"]}

    def test_thirteen_unique_stages(self):
        self.assertEqual(self.d["n"], N_STAGES)
        self.assertEqual(len(self.keys), N_STAGES)
        self.assertEqual(len(set(self.keys)), N_STAGES, "단계 키가 중복된다")
        flow = [s["flow_order"] for s in self.d["stages"]]
        self.assertEqual(len(flow), N_STAGES)

    def test_source_of_truth_is_declared(self):
        self.assertIn("EQUIP_WORDS", self.d["source_of_truth"])

    def test_every_stage_word_is_in_equip_words_or_declared_as_a_request(self):
        equip = {_norm(w) for w in EQUIP_WORDS}
        extra = {_norm(w) for w in self.d["unmatched"]["extra_words"]}
        orphan = sorted(w for w in self.words if w not in equip and w not in extra)
        self.assertEqual(orphan, [],
                         "EQUIP_WORDS 에도 없고 요청 목록에도 없는 낱말이 늘었다")

    def test_the_request_list_is_honest(self):
        """EQUIP_WORDS 에 없는 낱말은 **전부** extra_words 에 적혀 있어야 한다."""
        equip = {_norm(w) for w in EQUIP_WORDS}
        extra = {_norm(w) for w in self.d["unmatched"]["extra_words"]}
        missing = {w for w in self.words if w not in equip}
        self.assertTrue(missing, "요청 목록이 빈 상태라면 이 계약이 의미가 없다")
        self.assertEqual(sorted(missing - extra), [])
        # 요청 목록에 실제로 안 쓰는 낱말을 담아 두지 않는다(부품 이름으로만 쓰는 것도 쓰는 것이다).
        self.assertEqual(sorted(extra - self.words - self.part_words), [])

    def test_part_words_come_from_the_same_dictionary(self):
        """부품 낱말도 사전 한 벌에서 나온다 — 요청 목록(extra_words)에 실리면 그것도 사전이다."""
        known = ({_norm(w) for w in EQUIP_WORDS}
                 | {_norm(w) for w in self.d["unmatched"]["extra_words"]}
                 | self.words)
        bad = []
        for s in self.d["stages"]:
            for p in s["parts"]:
                bad += [(s["key"], p["key"], w) for w in p["words"]
                        if _norm(w) not in known]
        self.assertEqual(bad, [])

    def test_unassigned_equip_words_carry_a_reason(self):
        """어느 단계에도 안 붙인 EQUIP_WORDS 는 이유가 적혀 있어야 한다(fail-closed)."""
        un = self.d["unmatched"]["equip_unassigned"]
        why = self.d["unmatched"]["equip_unassigned_why"]
        self.assertEqual(sorted(un), sorted(why), "사유 없는 미배정 낱말이 있다")
        for w in un:
            self.assertTrue(why[w].strip(), w)


@unittest.skipUnless(C.has_asset(STAGES_JSON) and C.has_asset(TAGS_JSON),
                     "assets/stages.json·stage_tags.json 없음")
class TestStageTags(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stages = C.asset(STAGES_JSON)
        cls.tags = C.asset(TAGS_JSON)
        cls.keys = {s["key"] for s in cls.stages["stages"]}

    def test_per_stage_keys_are_known_stages(self):
        per = self.tags["per_stage"]
        self.assertEqual(set(per), self.keys,
                         "per_stage 가 stages.json 의 13단계와 다르다")
        self.assertEqual(len(per), N_STAGES)

    def test_row_stage_keys_and_primary_are_known_stages(self):
        bad = []
        for r in self.tags["rows"]:
            for s in r["stages"]:
                if s["key"] not in self.keys:
                    bad.append((r["stock"], s["key"]))
            if r["primary"] is not None and r["primary"] not in self.keys:
                bad.append((r["stock"], r["primary"]))
        self.assertEqual(bad, [])

    def test_primary_is_one_of_the_row_stages(self):
        bad = [r["stock"] for r in self.tags["rows"]
               if r["primary"] is not None
               and r["primary"] not in [s["key"] for s in r["stages"]]]
        self.assertEqual(bad, [])

    def test_per_stage_counts_match_the_rows(self):
        """요약(per_stage)과 행이 어긋나면 화면 숫자와 근거가 갈라진다."""
        got = dict.fromkeys(self.keys, 0)
        for r in self.tags["rows"]:
            for s in r["stages"]:
                got[s["key"]] += 1
        self.assertEqual(got, self.tags["per_stage"])

    def test_row_count_matches_n(self):
        self.assertEqual(len(self.tags["rows"]), self.tags["n"])

    def test_every_stage_word_on_a_row_belongs_to_that_stage(self):
        by_key = {s["key"]: set(s["words"]["strong"]) | set(s["words"]["weak"])
                  for s in self.stages["stages"]}
        bad = []
        for r in self.tags["rows"]:
            for s in r["stages"]:
                bad += [(r["stock"], s["key"], w) for w in s["words"]
                        if _norm(w) not in by_key[s["key"]]]
        self.assertEqual(bad, [])


class TestBuildDictsCrossCheck(unittest.TestCase):
    """build_dicts 자신의 교차검증 — 오류가 하나라도 있으면 사전을 쓰면 안 된다."""

    @unittest.skipUnless(C.has_asset("universe.json"), "assets/universe.json 없음")
    def test_cross_check_reports_no_errors(self):
        import build_dicts as B
        rep, errs = B.cross_check()
        self.assertEqual(errs, [])
        self.assertEqual(rep["n_stages"], N_STAGES)
        self.assertEqual(sorted(rep["palette_slots"]),
                         sorted(st["key"] for st in B.COMPILED),
                         "팔레트 슬롯이 단계를 다 덮지 않는다(색은 단계에 고정된다)")

    def test_classify_uses_context_for_weak_words(self):
        """약한 낱말은 반도체 문맥이 있을 때만 센다 — 「트랙터」가 포토로 가면 안 된다."""
        import build_dicts as B
        self.assertEqual(B.classify("경운기,트랙터,이앙기,바인더,수확기(콤바인)"), [])
        got = dict(B.classify("반도체 웨이퍼 포토 트랙 장비"))
        self.assertIn("photo", got)


if __name__ == "__main__":
    unittest.main()
