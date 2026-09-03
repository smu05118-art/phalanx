#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_build 멱등성(재적재 재현) 테스트.

실제 DART 원문 fixture(2026Q2 반기보고서)로 이미 수록된 분기를 다시 빌드했을 때,
임베드 DATA의 실측값·집계가 그대로 재현되어야 한다(원 빌더와의 로직 동치 증명).
"""
import copy
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
KCE = os.path.dirname(TOOLS)
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, TOOLS)

from kce_lib import extract_data  # noqa: E402
import kce_build as KB  # noqa: E402

K, Q = 18, "2026Q2"


def _rep():
    return {"events": 0, "p8_cells": 0, "fcst_cells": 0, "agg_rows": [],
            "created": [], "disappeared": [], "p8_unmatched": []}


class TestRebuildIdempotence(unittest.TestCase):

    def _rebuild(self, co, ii4_fx, p8_fx):
        orig = extract_data(os.path.join(KCE, co, "index.html"))
        D = copy.deepcopy(orig)
        rep = _rep()
        with open(os.path.join(FIX, ii4_fx), encoding="utf-8") as f:
            parsed = KB.parse_ii4(f.read())
        self.assertEqual(parsed["unknown_headers"], [])
        KB._apply_ii4(D, parsed, K, Q, rep)
        if p8_fx:
            with open(os.path.join(FIX, p8_fx), encoding="utf-8") as f:
                pp = KB.parse_p8(f.read())
            self.assertEqual(pp["unknown_headers"], [])
            KB._apply_p8(D, pp, K, rep)
        KB._recompute(D, K)
        return orig, D, rep

    def _assert_same(self, co, orig, D, rep):
        self.assertEqual(rep["created"], [], co)          # 전 행이 기존 사업장에 매칭
        for so, sn in zip(orig["sites"], D["sites"]):
            for f in ("amt", "cmp", "bal", "pr"):
                self.assertEqual(so["s"][f][K], sn["s"][f][K], (co, so["id"], f))
            if so.get("rev"):
                self.assertEqual(so["rev"]["diff"][K], sn["rev"]["diff"][K],
                                 (co, so["id"]))
            for basis in ("별도", "연결"):
                bo = (so.get("p8") or {}).get(basis)
                bn = (sn.get("p8") or {}).get(basis)
                self.assertEqual(bo and bo["tot"][K], bn and bn["tot"][K],
                                 (co, so["id"], basis))
        self.assertEqual(orig["revSummary"]["total"][K], D["revSummary"]["total"][K], co)

    def test_sct(self):
        orig, D, rep = self._rebuild("sct", "sct_상세표_건설수주.html",
                                     "sct_기타재무_진행률수주.html")
        self._assert_same("sct", orig, D, rep)
        # sct는 src='명시+기타(계산)' — summary도 재계산으로 완전 재현
        self.assertEqual(orig["summary"]["total"][K], D["summary"]["total"][K])
        self.assertEqual(rep["p8_unmatched"], [])

    def test_hec(self):
        orig, D, rep = self._rebuild("hec", "hec_수주상황.html",
                                     "hec_기타재무_진행률수주.html")
        self._assert_same("hec", orig, D, rep)
        # hec는 src='공시총계' — summary.rows는 재계산하지 않고 보존
        self.assertEqual(orig["summary"]["rows"]["현대건설"][K],
                         D["summary"]["rows"]["현대건설"][K])


if __name__ == "__main__":
    unittest.main()
