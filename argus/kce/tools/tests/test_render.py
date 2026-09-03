#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_render 로직 동치 테스트.

matrix.html의 프리렌더 tbody와 trace.html의 SITES 배열을 index.html의 DATA만으로 재생성했을 때
**현재 저장된 원본과 완전히 동일**해야 한다. 7사 전부 통과 = 렌더 규칙이 원 빌더와 동치라는 증명.
(matrix: 2,235 사업장 × 23분기 셀의 값·클래스·툴팁·data 속성까지 바이트 일치)
"""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
KCE = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

from kce_lib import extract_data  # noqa: E402
from kce_render import (render_matrix_body, render_trace_sites,  # noqa: E402
                        _TB, _TRACE)

COS = ["sct", "hec", "sea", "dwe", "gse", "dle", "ipark"]


class TestRenderEquivalence(unittest.TestCase):

    def test_matrix_byte_identical(self):
        for co in COS:
            D = extract_data(os.path.join(KCE, co, "index.html"))
            with open(os.path.join(KCE, co, "matrix.html"), encoding="utf-8") as f:
                orig = _TB.search(f.read()).group(2)
            self.assertEqual(orig, render_matrix_body(D), "%s matrix 재생성 불일치" % co)

    def test_trace_identical(self):
        for co in COS:
            D = extract_data(os.path.join(KCE, co, "index.html"))
            with open(os.path.join(KCE, co, "trace.html"), encoding="utf-8") as f:
                m = _TRACE.search(f.read())
            self.assertEqual(json.loads(m.group(1)), D["fq"], "%s trace FQ" % co)
            self.assertEqual(json.loads(m.group(2)), render_trace_sites(D),
                             "%s trace SITES 재생성 불일치" % co)


if __name__ == "__main__":
    unittest.main()
