#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_render 로직 동치 테스트.

matrix.html의 프리렌더 tbody와 trace.html의 SITES 배열을 index.html의 DATA만으로 재생성했을 때
**현재 저장된 원본과 완전히 동일**해야 한다. 정밀 경로 전사 통과 = 렌더 규칙이 원 빌더와
동치라는 증명(셀의 값·클래스·툴팁·data 속성까지 바이트 일치).

조각(tbody·SITES)만 보면 부족하다 — 조각은 맞는데 **갈아끼우다 파일의 다른 데를 잘라먹는**
회귀가 실제로 있었다(SITES 뒤 `,WT={...},RAWN={...}` 를 정규식이 삼켜 17사에서
4,723~13,477바이트가 조용히 사라졌다). 그래서 파일 전체 재생성 결과도 함께 대조한다.
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

from kce_lib import COMPANIES, extract_data  # noqa: E402
from kce_render import (matrix_matches, render_matrix_body,  # noqa: E402
                        render_matrix_html, render_trace_html,
                        render_trace_sites, trace_matches, _TB, _TRACE)

# 정밀 경로 전사. 목록을 여기 박지 않는다 — CORP가 늘면 자동으로 따라가야 한다.
COS = [co for co in COMPANIES
       if os.path.exists(os.path.join(KCE, co, "matrix.html"))]


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


    def test_matrix_file_byte_identical(self):
        """조각이 아니라 **파일 전체**가 바이트 동일해야 한다."""
        for co in COS:
            path = os.path.join(KCE, co, "matrix.html")
            D = extract_data(os.path.join(KCE, co, "index.html"))
            with open(path, encoding="utf-8") as f:
                orig = f.read()
            self.assertEqual(render_matrix_html(path, D), orig,
                             "%s matrix 파일 전체 불일치" % co)
            self.assertTrue(matrix_matches(path, D), co)

    def test_trace_file_byte_identical(self):
        for co in COS:
            path = os.path.join(KCE, co, "trace.html")
            D = extract_data(os.path.join(KCE, co, "index.html"))
            with open(path, encoding="utf-8") as f:
                orig = f.read()
            out = render_trace_html(path, D)
            self.assertEqual(out, orig, "%s trace 파일 전체 불일치" % co)
            # 삼킴 회귀 감시: 재생성물이 원본보다 짧아지면 뭔가 잘려나간 것이다.
            self.assertGreaterEqual(len(out), len(orig), "%s trace 축소" % co)
            self.assertTrue(trace_matches(path, D), co)

    def test_covers_every_precision_company(self):
        """목록이 낡아 조용히 일부만 검사하는 일이 없어야 한다."""
        self.assertGreaterEqual(len(COS), 7, "정밀 경로 회사를 찾지 못했다")
        for co in COS:
            self.assertTrue(os.path.exists(os.path.join(KCE, co, "trace.html")), co)

if __name__ == "__main__":
    unittest.main()
