#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""머리행 지도 훅 스모크(2026-10-12) — 공용 엔진 argus/kce/tools/hdrmap.py 에 붙인 kgrid(collect_one·reparse_one) 훅이
(1) 수주표 후보·채택을 지도에 기록·커밋하고 (2) 엔진이 터져도 수집을 멈추지 않으며(advisory)
(3) 모집단 신규 종목을 큐(new_company)에 올리는지. 임시 디렉터리에만 쓴다(DART 0)."""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import kgrid_reports as R                                    # noqa: E402
import kgrid_universe as U                                   # noqa: E402
import hdrmap                                                # noqa: E402

# *_lib 이 argus/kce/tools·kship/tools 를 sys.path 앞에 넣는다 — 이 탭 tools 를 다시 맨 앞에(같은 이름 모듈 충돌 방지)
sys.path.remove(TOOLS)
sys.path.insert(0, TOOLS)

ORDERS = [
    {"shape": "item", "cols": ["품목", "수주총액", "수주잔고"], "lead": "[LS메탈] (단위 : 억원)", "entity": "LS메탈",
     "rows": [{"closing": 1}], "cur": "KRW", "unit_seen": True},
    {"shape": "item", "cols": ["품목", "수주총액", "수주잔고"], "lead": "[LS ELECTRIC] (단위 : 억원)",
     "entity": "LS ELECTRIC", "rows": [{"closing": 5}, {"closing": 6}], "cur": "KRW", "unit_seen": True},
]
OUT = {"stock": "010120", "name": "LS ELECTRIC", "quarter": "2026Q2", "rcp": "20260814000001",
       "orders": dict(ORDERS[1], picked_of=2)}


class TestHdrmapHook(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kgrid_hdr_")
        R.HDR_ROOT = self.tmp

    def tearDown(self):
        R.HDR_ROOT = None
        hdrmap.discard("kgrid")
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stage_smoke(self):
        R._hdr_record(dict(OUT), ORDERS)
        ent = hdrmap.load_map("kgrid", self.tmp)["companies"]["010120"]["roles"]["orders"]["2026Q2"]
        self.assertEqual([e["pick"] for e in ent], [False, True])          # 채택 = _pick_orders 의 표(복사본도 짚는다)
        self.assertEqual([e["ent"] for e in ent], ["LS메탈", "LS ELECTRIC"])  # ent ← 대괄호 법인 라벨
        self.assertEqual([e["tag"] for e in ent], ["item", "item"])
        self.assertEqual([e["n_rec"] for e in ent], [1, 2])
        self.assertEqual(hdrmap.staged("kgrid"), {})

    def test_engine_failure_is_advisory(self):
        err = io.StringIO()
        with mock.patch.object(hdrmap, "record", side_effect=RuntimeError("엔진 고장")), redirect_stderr(err):
            R._hdr_record(dict(OUT), ORDERS)                                 # 예외가 밖으로 나오지 않는다
        self.assertIn("hdrmap kgrid 010120", err.getvalue())

    def test_onboard(self):
        new = U._onboard([{"stock": "010120"}], [{"stock": "010120"}, {"stock": "999990", "slug": "newco"}],
                         root=self.tmp)
        self.assertEqual([r["stock"] for r in new], ["999990"])
        q = hdrmap.load_queue("kgrid", self.tmp)
        self.assertEqual([(i["kind"], i["key"]) for i in q], [("new_company", "999990")])   # 키 = 종목코드(slug 아님)
        self.assertEqual(U._onboard([], [{"stock": "1"}], root=self.tmp), [])


if __name__ == "__main__":
    unittest.main()
