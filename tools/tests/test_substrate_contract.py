#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data/ensemble/substrate.json 계약 테스트 — 앙상블 기판 섹터의 공개 데이터.

생성기(맥스튜디오 composite_preview)가 이 파일만 읽어 기판 섹터를 그릴 수 있도록
요청서(codex_tasks/ensemble_substrate_*.md)의 계약을 지키는지 본다.
"""
import json
import os
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PATH = os.path.join(ROOT, "data", "ensemble", "substrate.json")
AXES = ("orders", "sales", "supply", "price", "inventory", "capacity")


class SubstrateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(PATH, encoding="utf-8") as f:
            cls.raw = f.read()
        cls.d = json.loads(cls.raw)

    def test_normalized_bytes(self):
        self.assertEqual(self.raw, json.dumps(self.d, ensure_ascii=False, sort_keys=True, indent=1) + "\n")

    def test_header(self):
        self.assertEqual(self.d["schema_version"], 2)
        self.assertEqual(self.d["sector"]["id"], "substrate")

    def test_companies(self):
        bundles = {b["id"] for b in self.d["bundles"]}
        ids = [c["id"] for c in self.d["companies"]]
        self.assertEqual(len(ids), len(set(ids)), "회사 id 중복")
        for c in self.d["companies"]:
            self.assertIn(c["bundle"], bundles)
            self.assertIn(c["observability"], ("monthly", "quarterly", "semiannual", "none"))
            self.assertEqual(set(c["axes"]), set(AXES), c["id"])
            for k, a in c["axes"].items():
                self.assertIn(a["status"], ("measured", "qualitative", "none"), (c["id"], k))
                if a["status"] == "measured":
                    self.assertIsInstance(a["value"], (int, float), (c["id"], k))
                    self.assertTrue(a["source_url"].startswith("https://") or a["source_url"].startswith("http://"), (c["id"], k))
                if a["status"] == "none":
                    self.assertNotIn("value", a, "미관측 축에 값이 있으면 안 된다: %s.%s" % (c["id"], k))
            if c["aggregate"]:
                self.assertEqual(c["bundle"], "solder_ball", "묶음 합계는 솔더볼 순수 볼 행만")

    def test_edges_public_grades_only(self):
        for e in self.d["edges"]:
            self.assertIn(e["grade"], ("A", "B"), "공개 산출물에는 A·B 엣지만")
            self.assertTrue(e["source_urls"], e["id"])

    def test_capex_and_events_sourced(self):
        for c in self.d["capex"]:
            self.assertTrue(c["source_url"].startswith("http"), c)
        for e in self.d["events"]:
            self.assertTrue(e["source_url"].startswith("http"), e)


if __name__ == "__main__":
    unittest.main()
