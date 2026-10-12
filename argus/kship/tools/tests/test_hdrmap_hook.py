#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""머리행 지도 훅 스모크(2026-10-12) — 공용 엔진 argus/kce/tools/hdrmap.py 에 붙인 kship(kship_yards collect_one — 실패 return 앞) 훅이
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

import kship_yards as Y                                      # noqa: E402
import kship_universe as U                                   # noqa: E402
import hdrmap                                                # noqa: E402

# kship_lib 이 argus/kce/tools 를 sys.path 앞에 넣는다 — 이 탭 tools 를 다시 맨 앞에(같은 이름 모듈 충돌 방지)
sys.path.remove(TOOLS)
sys.path.insert(0, TOOLS)

REC = {"stock": "010140", "name": "삼성중공업", "role": "yard"}
GOOD = {"cols": ["구분", "기초 금액", "신규 금액", "기납품 금액", "기말 금액"], "lead": "(단위 : 억원)",
        "rows": [["상선", "1", "1", "1", "1"]]}
ODD = {"cols": ["선종", "수주잔량(척)", "수주잔량(CGT)"], "lead": "", "rows": [["LNG", "3", "100"]]}
OTHER = {"cols": ["구분", "매출액"], "lead": "", "rows": [["상선", "9"]]}


class TestHdrmapHook(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kship_hdr_")
        Y.HDR_ROOT = self.tmp

    def tearDown(self):
        Y.HDR_ROOT = None
        hdrmap.discard("kship")
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stage_smoke_failure_path(self):
        """수주표를 못 읽은 분기(캐시 안 됨) — 지도에 빈 채택 + 미지 표, 큐에 unknown(수주 낱말이 있는 표만)."""
        out = {"stock": "010140", "quarter": "2026Q2", "rcp": "r", "ok": False}
        Y._hdr_record(REC, out, [ODD, OTHER], [])
        ent = hdrmap.load_map("kship", self.tmp)["companies"]["010140"]["roles"]["orders"]["2026Q2"]
        self.assertEqual([(e["pick"], e["cols"][0]) for e in ent], [(False, "선종")])
        q = hdrmap.load_queue("kship", self.tmp)
        self.assertEqual([(i["kind"], i["key"]) for i in q], [("unknown", "010140")])
        Y._hdr_record(REC, out, [ODD, OTHER], [])                          # 매일 다시 시도돼도 같은 id 하나
        self.assertEqual(len(hdrmap.load_queue("kship", self.tmp)), 1)

    def test_stage_smoke_success(self):
        o = Y.parse_orders_table(GOOD)
        self.assertIsNotNone(o)
        out = {"stock": "010140", "quarter": "2026Q2", "rcp": "r", "orders": o}
        Y._hdr_record(REC, out, [GOOD, ODD], [o])
        ent = hdrmap.load_map("kship", self.tmp)["companies"]["010140"]["roles"]["orders"]["2026Q2"]
        self.assertEqual([e["pick"] for e in ent], [True, False])

    def test_engine_failure_is_advisory(self):
        err = io.StringIO()
        with mock.patch.object(hdrmap, "record", side_effect=RuntimeError("엔진 고장")), redirect_stderr(err):
            Y._hdr_record(REC, {"stock": "010140", "quarter": "2026Q2"}, [ODD], [])
        self.assertIn("hdrmap kship 010140", err.getvalue())

    def test_onboard_yards_only(self):
        """지도는 조선소만 기록한다 — 기자재사를 신규로 올리면 영영 닫히지 않는다."""
        new = U._onboard([{"stock": "010140"}], [{"stock": "010140", "role": "yard"},
                                                 {"stock": "999990", "role": "yard"},
                                                 {"stock": "999980", "role": "equip"}], root=self.tmp)
        self.assertEqual([r["stock"] for r in new], ["999990"])


if __name__ == "__main__":
    unittest.main()
