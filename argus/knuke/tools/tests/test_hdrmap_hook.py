#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""머리행 지도 훅 스모크(2026-10-12) — 공용 엔진 argus/kce/tools/hdrmap.py 에 붙인 knuke(collect_one) 훅이
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

import knuke_reports as R                                    # noqa: E402
import knuke_universe as U                                   # noqa: E402
import hdrmap                                                # noqa: E402

# *_lib 이 argus/kce/tools·kship/tools 를 sys.path 앞에 넣는다 — 이 탭 tools 를 다시 맨 앞에(같은 이름 모듈 충돌 방지)
sys.path.remove(TOOLS)
sys.path.insert(0, TOOLS)

ORDERS = [
    {"shape": "award", "cols": ["구분", "발주처", "사업명", "최초계약일", "종료일", "기본도급액", "계약잔액"],
     "lead": "(단위 : 백만원)", "rows": [{"closing": 1}, {"closing": 2}], "cur": "KRW", "unit_seen": True,
     "has_client": True, "has_period": True},
    {"shape": "gross", "cols": ["구분", "수주총액", "수주잔고"], "lead": "(단위 : 백만원)",
     "rows": [{"closing": 1}], "cur": "KRW", "unit_seen": True, "has_client": False, "has_period": False},
]
OUT = {"stock": "052690", "name": "한전기술", "quarter": "2026Q2", "rcp": "20260814000001",
       "orders": dict(ORDERS[0])}


class TestHdrmapHook(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="knuke_hdr_")
        R.HDR_ROOT = self.tmp

    def tearDown(self):
        R.HDR_ROOT = None
        hdrmap.discard("knuke")
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stage_smoke(self):
        R._hdr_record(dict(OUT), ORDERS)
        ent = hdrmap.load_map("knuke", self.tmp)["companies"]["052690"]["roles"]["orders"]["2026Q2"]
        self.assertEqual([e["pick"] for e in ent], [True, False])
        self.assertEqual([e["tag"] for e in ent], ["award", "gross"])
        # award 모양 식별(발주처·기간 열 유무)을 shape 에 싣는다 — kdef 부품사의 같은 모양 표와 지도에서 맞대 본다
        self.assertEqual([e["shape"] for e in ent], ["award+발주처+기간", "gross"])

    def test_engine_failure_is_advisory(self):
        err = io.StringIO()
        with mock.patch.object(hdrmap, "write", side_effect=OSError("디스크")), redirect_stderr(err):
            R._hdr_record(dict(OUT), ORDERS)
        self.assertIn("hdrmap knuke 052690", err.getvalue())

    def test_onboard(self):
        new = U._onboard([{"stock": "052690"}], [{"stock": "052690"}, {"stock": "999990"}], root=self.tmp)
        self.assertEqual([r["stock"] for r in new], ["999990"])
        self.assertEqual([i["kind"] for i in hdrmap.load_queue("knuke", self.tmp)], ["new_company"])


if __name__ == "__main__":
    unittest.main()
