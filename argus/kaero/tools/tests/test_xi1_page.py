#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XI-1 계약 진행(반기·사업보고서 「나. 단일판매ㆍ공급계약 진행 현황」) 화면 연결 — 네트워크 없이.

(1) 진행 현황이 있으면 회사 페이지에 섹션(id="xi1")과 수시공시 계약 표의 '진행(XI-1)' 열, 허브 섹션,
    커버리지 수집 상태 표, 꼬리말 출처가 붙고 (2) 없거나(None)·못 읽거나·렌더가 터지면 예외 없이
    예전 화면 그대로 나온다(fail-soft). 진행 현황은 공용 xi1_sector 산출을 한 회사(하이즈항공 221840)로 줄인
    고정 픽스처(fixtures/xi1_progress_221840.json)를 쓴다 — 매일 갱신되는 progress.json 에 묶이지 않게.
"""
import copy
import io
import json
import os
import re
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import kaero_page as P                                       # noqa: E402
import xi1_sector                                            # noqa: E402  (kaero_lib 가 kce/tools 를 경로에 넣는다)
import xi1_view                                              # noqa: E402

# *_lib 이 argus/kce/tools·kship/tools 를 sys.path 앞에 넣는다 — 이 탭 tools 를 다시 맨 앞에(같은 이름 모듈 충돌 방지)
sys.path.remove(TOOLS)
sys.path.insert(0, TOOLS)

ST = "221840"
XI_SRC = "XI-1 공시내용 진행 및 변경사항"


def _fixture():
    with open(os.path.join(HERE, "fixtures", "xi1_progress_221840.json"), encoding="utf-8") as f:
        return json.load(f)


def _row(rcp, supersedes=None, name="부품공급계약"):
    r = {"rcp": rcp, "stock": ST, "name": name, "domain": "aero_struct", "nature": "LTA", "amount": 1000.0,
         "cur": "KRW", "party": "Boeing", "signed": "2020-01-30", "start": "2020-02-01"}
    if supersedes:
        r["supersedes"] = supersedes
    return r


def _con_table(html):
    """수시공시 계약 표 — 머리 칸 수와 각 행 칸 수."""
    i = html.find("<h2>수시공시 계약")
    t = html[i:html.find("</table>", i)]
    head = t[t.find("<thead>"):t.find("</thead>")]
    body = t[t.find("<tbody>"):]
    rows = [len(re.findall(r"<td[ >]", tr)) for tr in body.split("</tr>") if "<td" in tr]
    return len(re.findall(r"<th[ >]", head)), rows, t


class TestXi1Page(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with redirect_stderr(io.StringIO()):
            cls.base = P.load_all()
        cls.prog = _fixture()
        rcps = sorted(cls.prog["by_rcp"])
        cls.rcp_a, cls.rcp_b = rcps[0], rcps[1]

    def data(self, prog=True):
        d = dict(self.base)
        d["xi1"], d["xi1_view"] = (copy.deepcopy(self.prog), xi1_view) if prog else (None, None)
        return d

    def summary(self, data, rows=None):
        s = P.summary(ST, data)
        s["contracts"] = rows if rows is not None else [
            _row(self.rcp_a),                                     # 최신 rcp 가 그대로 진행 계약에 이어진다
            _row("20990101000001", supersedes=self.rcp_b),        # 정정 사슬(원접수)로 이어진다
            _row("20990101000002", name="이어지지 않은 계약")]    # 진행 계약 없음 → '—'
        return s

    # ── 진행 현황이 있을 때 ──────────────────────────────────

    def test_company_section_and_column(self):
        d = self.data()
        html = P.company_html(self.summary(d), d)
        self.assertEqual(html.count('id="xi1"'), 1)
        self.assertIn('href="#xi1"', html)                       # 머리 내비
        self.assertIn(XI_SRC, html[html.find("<footer>"):])      # 꼬리말 출처
        self.assertIn(".xi1c .xb", html)                         # 조각 CSS 한 번
        self.assertEqual(html.count("<style>"), 1)
        nth, rows, t = _con_table(html)
        self.assertEqual(t.count("진행(XI-1)</th>"), 1)
        self.assertEqual(nth, 8)                                 # 7 → 8 칸
        self.assertEqual(rows, [8, 8, 8])                        # 행마다 칸 수가 머리와 같다(정렬 data-v 열 위치 보존)
        cells = re.findall(r'<td class="n xi1c[^"]*" data-v="([^"]+)"', t)
        self.assertEqual(len(cells), 3)
        self.assertEqual(sorted(float(v) >= 0 for v in cells), [False, True, True])
        self.assertIn('data-v="-1">—</td>', t)                   # 이어지지 않은 행은 0 이 아니라 '—'
        # 열은 '금액' 바로 뒤
        self.assertRegex(t, r"<th>금액</th><th class=\"n\"[^>]*>진행\(XI-1\)</th><th class=\"l\">상대</th>")

    def test_no_column_when_nothing_links(self):
        d = self.data()
        html = P.company_html(self.summary(d, rows=[_row("20990101000009")]), d)
        nth, rows, t = _con_table(html)
        self.assertEqual((nth, rows), (7, [7]))
        self.assertNotIn("xi1c", t)
        self.assertIn('id="xi1"', html)                          # 섹션(XI-1 쪽 계약)은 그대로 있다

    def test_hub_and_coverage(self):
        d = self.data()
        sums = [P.summary(r["stock"], d) for r in d["uni"]]
        hub = P.hub_html(d, sums)
        self.assertEqual(hub.count('id="xi1"'), 1)
        self.assertIn('<a href="%s/index.html">' % ST, hub)      # 회사 페이지가 있는 종목만 링크
        self.assertIn(XI_SRC, hub[hub.find("<footer>"):])
        self.assertLess(hub.find('id="xi1"'), hub.find('<h2 class="sec">더 보기'))
        self.assertGreater(hub.find('id="xi1"'), hub.find('id="cbig"'))
        cov = P.coverage_html(d, sums)
        self.assertEqual(cov.count('id="xi1cov"'), 1)
        self.assertIn(XI_SRC, cov[cov.find("<footer>"):])

    def test_dual_segment_note(self):
        d = self.data()
        s = self.summary(d)
        s["dup"] = [{"tab": "kdef", "seg": "국내방산", "closing": 1.0, "cur": "KRW"}]
        html = P.company_html(s, d)
        sec = html[html.find('id="xi1"'):]
        self.assertIn("<b>겸업사</b>", sec[:sec.find('<div class="xk">')])  # 섹션 제목 바로 밑
        self.assertIn("방산(한국방산 탭)", sec)
        self.assertEqual(P._xi1_dual_note({"stock": "012450", "dup": []}).count("탭)"), 2)  # 목록 대체값
        self.assertEqual(P._xi1_dual_note({"stock": ST, "dup": []}), "")

    # ── 없을 때 — 예전 화면 그대로 ────────────────────────────

    def test_absent_progress_keeps_page(self):
        d = self.data(prog=False)
        html = P.company_html(self.summary(d), d)
        for marker in ('id="xi1"', "xi1c", "#xi1", XI_SRC, "<style>", "진행(XI-1)"):
            self.assertNotIn(marker, html)
        nth, rows, _ = _con_table(html)
        self.assertEqual((nth, rows), (7, [7, 7, 7]))
        self.assertIn("「II-4 매출 및 수주상황」(과 XII 상세표)·수시공시「단일판매ㆍ공급계약체결」", html)
        sums = [P.summary(r["stock"], d) for r in d["uni"]]
        hub, cov = P.hub_html(d, sums), P.coverage_html(d, sums)
        for marker in ('id="xi1"', "xi1cov", XI_SRC, "<style>"):
            self.assertNotIn(marker, hub)
            self.assertNotIn(marker, cov)
        self.assertIn('</section>\n<h2 class="sec">더 보기', hub)

    def test_loader_fail_soft(self):
        with mock.patch.object(xi1_sector, "load_progress", return_value=None):
            self.assertEqual(P.load_xi1([ST]), (None, None))
        err = io.StringIO()
        with mock.patch.object(xi1_sector, "load_progress", side_effect=ValueError("깨진 JSON")), redirect_stderr(err):
            self.assertEqual(P.load_xi1([ST]), (None, None))
        self.assertIn("XI-1 계약 진행 비활성", err.getvalue())

    def test_loader_subsets_to_screen_population(self):
        prog = copy.deepcopy(self.prog)
        prog["companies"]["999999"] = dict(prog["companies"][ST], name="모집단 밖")
        with mock.patch.object(xi1_sector, "load_progress", return_value=prog):
            got, view = P.load_xi1([ST])
        self.assertIs(view, xi1_view)
        self.assertEqual(sorted(got["companies"]), [ST])

    def test_render_failure_is_soft(self):
        d = self.data()
        err = io.StringIO()
        with mock.patch.object(xi1_view, "company_section", side_effect=KeyError("agg")), \
                mock.patch.object(xi1_view, "progress_cell", side_effect=KeyError("m")), redirect_stderr(err):
            html = P.company_html(self.summary(d), d)
        self.assertNotIn('id="xi1"', html)
        self.assertNotIn('href="#xi1"', html)
        nth, rows, _ = _con_table(html)
        self.assertEqual((nth, rows), (8, [8, 8, 8]))            # 칸이 터져도 열 수는 맞는다('—')
        self.assertIn("XI-1", err.getvalue())


if __name__ == "__main__":
    unittest.main()
