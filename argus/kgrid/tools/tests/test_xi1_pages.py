#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계약 진행(XI-1) 화면 붙이기 — 공용 층 argus/kce/tools/xi1_sector·xi1_view 를 kgrid 페이지에 붙인 자리의 계약.

(1) progress.json 이 있으면 허브·커버리지·회사 페이지에 섹션(id="xi1"/"xi1cov")과 원장 표의 진행 열(xi1c)이 나온다.
(2) 없거나(None) 공용 층 import·렌더가 실패하면 **예외 없이 XI-1 이전 화면 그대로**(섹션·열·CSS·꼬리말 없음).
(3) 허브 집계는 지주 3사를 뺀 모집단(xi1_sector.subset) — 효성 XI-1 표는 효성중공업 계약을 다시 싣는다.
(4) 원장 행의 정정 사슬(rcp + supersedes 리스트)로 XI-1 계약을 찾는다.
네트워크 없음 — 커밋된 tools/assets(xi1/progress.json 포함)만 읽는다."""
import io
import os
import re
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import kgrid_page as P                                       # noqa: E402

# *_lib 이 argus/kce/tools·kship/tools 를 sys.path 앞에 넣는다 — 이 탭 tools 를 다시 맨 앞에(같은 이름 모듈 충돌 방지)
sys.path.remove(TOOLS)
sys.path.insert(0, TOOLS)

XI_FOOT = "XI-1 공시내용 진행 및 변경사항"
HOLDINGS = ("004800", "006260", "015860")


def _table(html, tid):
    """id 가 tid 인 표의 (머리 칸 수, [행별 칸 수])."""
    i = html.index('<table id="%s"' % tid)
    t = html[i:html.index("</table>", i)]
    head = t[:t.index("</thead>")]
    body = t[t.index("<tbody>"):]
    return len(re.findall(r"<th[\s>]", head)), [len(re.findall(r"<td[\s>]", r)) for r in body.split("<tr>")[1:]]


def _fake_prog(rcp_old):
    """최소 진행 dict — 정정 전 접수번호(rcp_old)로만 이어진 계약 하나(공급 40%·수령 30%)."""
    c = {"id": "010120-20250101-00", "stock": "010120", "nm": "가짜 변압기", "cl": "가짜 전력", "dt": "2025.01.01",
         "cur": None, "amt_fx": None, "hist": {"2026Q2": [1000, 100, 400, 50, 300]},
         "m": {"q": "2026Q2", "amt": 1000, "prog": 0.4, "recv_prog": 0.3, "basis": "xi", "rem": 600, "ar": 100, "adv": 0},
         "flags": [], "status": "active"}
    return {"by_rcp": {rcp_old: c["id"]}, "contracts": [c], "companies": {}, "periods": ["2026Q2"], "asof": "2026Q2"}


class TestXi1Pages(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = P.load_all()

    def _none(self):
        d = dict(self.data)
        d["progress"] = None
        return d

    # ── 있음 ────────────────────────────────────────────
    def test_progress_asset_present(self):
        prog = self.data["progress"]
        self.assertIsInstance(prog, dict, "tools/assets/xi1/progress.json 이 커밋돼 있어야 한다")
        self.assertEqual(prog.get("tab"), "kgrid")

    def test_hub_section_subset_without_holdings(self):
        h = P.hub(self.data)
        self.assertIn('id="xi1"', h)
        self.assertIn('href="#xi1"', h)
        self.assertIn(XI_FOOT, h)
        self.assertIn("<style>", h.split("</head>")[0])
        sec = h[h.index('id="xi1"'):]
        sec = sec[:sec.index("</section>")]
        non_holding = [r for r in self.data["uni"] if r.get("role") != "holding"]
        m = re.search(r"<b>(\d+) / (\d+)</b><span>진행 표가 있는 회사 / 모집단", sec)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(2)), len(non_holding))
        for st in HOLDINGS:
            self.assertNotIn('href="%s/index.html"' % st, sec)
        # 회사 링크는 이 탭에 회사 페이지가 있는 종목만
        for st in re.findall(r'href="(\d{6})/index.html"', sec):
            self.assertIn(st, self.data["by_stock"])

    def test_coverage_rows_all_stocks(self):
        c = P.coverage_page(self.data)
        self.assertIn('id="xi1cov"', c)
        self.assertIn('href="#xi1cov"', c)
        self.assertIn("XI-1 계약 진행률 — 외화 계약", c)
        cov = c[c.index('id="xi1cov"'):]
        cov = cov[:cov.index("</section>")]
        for r in self.data["uni"]:
            self.assertIn("<td>%s</td>" % r["stock"], cov)

    def test_company_section_and_column(self):
        x = P.company(self.data, "010120")
        self.assertIn('id="xi1"', x)
        self.assertIn('href="#xi1"', x)
        self.assertIn(XI_FOOT, x)
        self.assertIn("진행(XI-1)</th>", x)
        self.assertRegex(x, r'<td class="n xi1c" data-v="\d+\.\d{4}"')
        nth, tds = _table(x, "tct")
        self.assertTrue(tds)
        self.assertEqual(set(tds), {nth}, "진행 열을 더해도 머리·행 칸 수가 같아야 정렬이 맞는다")
        # 섹션은 원장 표 뒤, 본문 안(</main> 앞)
        self.assertLess(x.index('id="tct"'), x.index('id="xi1"'))
        self.assertLess(x.index('id="xi1"'), x.index("</main>"))

    def test_holding_page_keeps_its_table(self):
        x = P.company(self.data, "004800")
        self.assertIn('id="xi1"', x)
        self.assertIn("지주회사 보고서의 XI-1 표", x)
        self.assertIn("xi1c", x)                       # 자회사 대신 낸 공시 표에도 진행 열

    def test_vendor_order_still_holds(self):
        # test_chart_connections 와 같은 조건 — XI-1 은 SVG 만 쓰고 차트를 새로 만들지 않는다.
        for st in ("001440", "103590", "189860", "007610"):
            html = P.company(self.data, st)
            head = html.split("</head>")[0]
            self.assertNotIn("new Chart(", head)
            self.assertLess(html.index("chart.umd.min.js"), html.index("var SER="))
            self.assertEqual(html.count("var SER="), 1)

    # ── 없음 · 실패 ─────────────────────────────────────
    def test_none_is_pre_xi1_page(self):
        d = self._none()
        pages = [P.hub(d), P.coverage_page(d)] + [P.company(d, r["stock"]) for r in d["uni"]]
        for html in pages:
            self.assertNotIn("xi1", html)
            self.assertNotIn(XI_FOOT, html)
            self.assertNotIn("진행(XI-1)", html)
            self.assertNotIn("<style>", html.split("</head>")[0])

    def test_import_failure_equals_none(self):
        d = self._none()
        base = (P.hub(d), P.coverage_page(d), P.company(d, "010120"))
        with mock.patch.object(P, "XV", None), mock.patch.object(P, "XS", None):
            got = (P.hub(self.data), P.coverage_page(self.data), P.company(self.data, "010120"))
        self.assertEqual(got, base)

    def test_load_all_without_progress(self):
        with mock.patch.object(P.XS, "load_progress", return_value=None):
            self.assertIsNone(P.load_all()["progress"])
        err = io.StringIO()
        with mock.patch.object(P.XS, "load_progress", side_effect=ValueError("깨진 JSON")), redirect_stderr(err):
            self.assertIsNone(P.load_all()["progress"])
        self.assertIn("progress.json", err.getvalue())

    def test_renderer_failure_is_soft(self):
        err = io.StringIO()
        with mock.patch.object(P.XV, "company_section", side_effect=RuntimeError("boom")), \
                mock.patch.object(P.XV, "hub_section", side_effect=RuntimeError("boom")), redirect_stderr(err):
            x = P.company(self.data, "010120")
            h = P.hub(self.data)
        self.assertNotIn('id="xi1"', x)
        self.assertNotIn('href="#xi1"', x)
        self.assertNotIn('id="xi1"', h)
        self.assertNotIn(XI_FOOT, h)
        self.assertIn("company_section", err.getvalue())

    # ── 정정 사슬 ───────────────────────────────────────
    def test_rcps_chain(self):
        self.assertEqual(P.xi_rcps({"rcp": "B", "supersedes": ["A", "C"]}), ["B", "A", "C"])
        self.assertEqual(P.xi_rcps({"rcp": "B", "supersedes": "A"}), ["B", "A"])
        self.assertEqual(P.xi_rcps({"rcp": "B"}), ["B"])
        self.assertEqual(P.xi_rcps({"rcp": "B", "supersedes": []}), ["B"])

    def test_column_found_through_superseded_rcp(self):
        row = {"stock": "010120", "rcp": "20250105800002", "supersedes": ["20250101800001"], "name": "가짜 변압기",
               "party": "가짜 전력", "amt_krw_m": 1000, "signed": "2025-01-01"}
        d = dict(self.data)
        d["contracts"] = {"rows": [row]}
        d["progress"] = _fake_prog("20250101800001")
        x = P.company(d, "010120")
        self.assertIn('<td class="n xi1c" data-v="0.4000"', x)
        self.assertIn("40%", x)
        nth, tds = _table(x, "tct")
        self.assertEqual(tds, [nth])
        # 사슬 밖 접수번호면 열 자체를 달지 않는다(전부 '—' 인 열은 없다)
        d["progress"] = _fake_prog("20990101000000")
        y = P.company(d, "010120")
        self.assertNotIn("진행(XI-1)", y)
        self.assertNotIn("xi1c", y)


if __name__ == "__main__":
    unittest.main()
