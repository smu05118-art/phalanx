#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""머리행 지도 훅 스모크(2026-10-12) — 공용 엔진 argus/kce/tools/hdrmap.py 에 붙인 ksemi(collect_one — unknown_headers 를 큐로) 훅이
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
import json                                                  # noqa: E402

import ksemi_reports as R                                    # noqa: E402
import hdrmap                                                # noqa: E402

# ksemi_lib 이 argus/kce/tools 를 sys.path 앞에 넣는다 — 이 탭 tools 를 다시 맨 앞에(같은 이름 모듈 충돌 방지)
sys.path.remove(TOOLS)
sys.path.insert(0, TOOLS)

REC = {"stock": "042700", "name": "한미반도체"}
O = {"tables": [{"lead": "(단위 : 백만원)", "cols": ["품목", "수주일자", "납기", "수주총액", "기납품액", "수주잔고"],
                 "unit": {"seen": True}, "rows": [{"nm": "A", "bal": 1}, {"nm": "합계", "bal": 1, "total": True}]}],
     "unknown_headers": [{"cols": ["구분", "수주금액", "수주잔고"], "n": 4}]}


class TestHdrmapHook(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ksemi_hdr_")
        R.HDR_ROOT = self.tmp

    def tearDown(self):
        R.HDR_ROOT = None
        hdrmap.discard("ksemi")
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stage_smoke(self):
        R._hdr_stage(REC, "2026Q2", "20260814000001", O)
        R._hdr_commit(REC)
        ent = hdrmap.load_map("ksemi", self.tmp)["companies"]["042700"]["roles"]["orders"]["2026Q2"]
        self.assertEqual([(e["pick"], e["reason"]) for e in ent], [(True, "picked"), (False, "near_miss")])
        self.assertEqual(ent[0]["unit_seen"], True)
        self.assertEqual((ent[1]["n"], ent[1]["n_rec"]), (None, 4))       # 본문 행 수는 n 이 아니라 n_rec
        q = hdrmap.load_queue("ksemi", self.tmp)
        self.assertEqual([(i["kind"], i["key"], i["grade"]) for i in q], [("unknown", "042700", "B")])
        self.assertTrue(q[0]["need_missing"])

    def test_engine_failure_is_advisory(self):
        err = io.StringIO()
        with mock.patch.object(hdrmap, "record", side_effect=RuntimeError("엔진 고장")), redirect_stderr(err):
            R._hdr_stage(REC, "2026Q2", "r", O)
        with mock.patch.object(hdrmap, "write", side_effect=OSError("디스크")), redirect_stderr(err):
            R._hdr_commit(REC)
        self.assertEqual(err.getvalue().count("hdrmap ksemi 042700"), 2)

    def test_onboard_against_previous_reports(self):
        prev = os.path.join(self.tmp, "reports.json")
        with open(prev, "w", encoding="utf-8") as f:
            json.dump({"rows": [{"stock": "042700"}]}, f)
        new = R._onboard([REC, {"stock": "999990", "name": "신규"}], prev_path=prev, root=self.tmp)
        self.assertEqual([r["stock"] for r in new], ["999990"])
        self.assertEqual(R._onboard([REC], prev_path=os.path.join(self.tmp, "없음.json"), root=self.tmp), [])


if __name__ == "__main__":
    unittest.main()
