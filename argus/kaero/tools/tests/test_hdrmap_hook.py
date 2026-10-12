#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""머리행 지도 훅 스모크(2026-10-12) — 공용 엔진 argus/kce/tools/hdrmap.py 에 붙인 kaero(collect_one — 통화별 다중 채택) 훅이
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

import kaero_reports as R                                    # noqa: E402
import kaero_universe as U                                   # noqa: E402
import hdrmap                                                # noqa: E402

# *_lib 이 argus/kce/tools·kship/tools 를 sys.path 앞에 넣는다 — 이 탭 tools 를 다시 맨 앞에(같은 이름 모듈 충돌 방지)
sys.path.remove(TOOLS)
sys.path.insert(0, TOOLS)

KRW = {"shape": "item", "cols": ["품목", "수주총액", "수주잔고"], "lead": "(단위 : 백만원)", "cur": "KRW",
       "unit_seen": True, "rows": [{"closing": 1}]}
USD = {"shape": "item", "cols": ["품목", "수주총액(USD)", "수주잔고(USD)"], "lead": "(단위 : 천USD)", "cur": "USD",
       "unit_seen": True, "rows": [{"closing": 2}, {"closing": 3}]}
NOUNIT = {"shape": "gross", "cols": ["구분", "수주총액", "수주잔고"], "lead": "", "cur": None, "unit_seen": False,
          "rows": [{"closing": 9}]}
OUT = {"stock": "047810", "name": "한국항공우주", "quarter": "2026Q2", "rcp": "20260814000001"}


class TestHdrmapHook(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kaero_hdr_")
        R.HDR_ROOT = self.tmp

    def tearDown(self):
        R.HDR_ROOT = None
        hdrmap.discard("kaero")
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stage_smoke_multi_pick(self):
        orders = [KRW, NOUNIT, USD]
        # group_orders 가 돌려주는 꼴 — 채택은 복사본({통화: dict(best)}), 단위 미확인은 rejected 로 빠진다
        picked = {"KRW": dict(KRW, scope="parent", n_tables=1), "USD": dict(USD, scope="unknown", n_tables=1)}
        rejected = [{"cur": None, "note": "단위 미확인", "lead": "", "cols": NOUNIT["cols"]}]
        R._hdr_record(dict(OUT), orders, picked, rejected)
        ent = hdrmap.load_map("kaero", self.tmp)["companies"]["047810"]["roles"]["orders"]["2026Q2"]
        # 통화마다 한 장씩 채택(cur 기록), 단위 미확인 표는 pick False·reason unit_unknown
        self.assertEqual([(e["pick"], e["cur"], e["reason"]) for e in ent],
                         [(True, "KRW", "picked"), (True, "USD", "picked"), (False, None, "unit_unknown")])

    def test_engine_failure_is_advisory(self):
        err = io.StringIO()
        with mock.patch.object(hdrmap, "record", side_effect=RuntimeError("엔진 고장")), redirect_stderr(err):
            R._hdr_record(dict(OUT), [KRW], {"KRW": dict(KRW)}, [])
        self.assertIn("hdrmap kaero 047810", err.getvalue())

    def test_onboard(self):
        new = U._onboard([{"stock": "047810"}], [{"stock": "047810"}, {"stock": "999990"}], root=self.tmp)
        self.assertEqual([r["stock"] for r in new], ["999990"])


if __name__ == "__main__":
    unittest.main()
