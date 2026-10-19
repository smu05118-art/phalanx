#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계약 진행(XI-1) 화면 통합 — 공용 층 argus/kce/tools/xi1_sector·xi1_view 를 ksemi 페이지에 붙인 자리.

지키는 것(네트워크 0 — 커밋된 tools/assets/xi1/progress.json 과 원장만 읽는다):
  · progress 가 있으면 회사 페이지·허브에 섹션(id="xi1"), 원장 표(#ct·최근 대형 수주)에 '진행(XI-1)' 열(td.xi1c),
    coverage.html 에 수집 상태 표(id="xi1cov"), 꼬리말에 XI-1 원천, 내비에 #xi1 이 붙는다.
  · 화면 모집단 = members(83사) — progress.json(154종목 전수)을 subset 해 허브·커버리지 숫자를 화면과 맞춘다.
  · 원장 병합 행은 supersedes 가 리스트다 — 정정 전 원접수 번호로도 진행 계약을 찾는다.
  · progress 가 없거나(None) 공용 층이 던지면 페이지는 예외 없이 지금 화면 그대로(섹션·열·꼬리말 없음).
  · 열을 더해도 표의 칸 수가 머리행과 같다(TABLE_JS 정렬은 td[data-v] 를 칸 번호로 읽는다).
"""
import copy
import io
import os
import re
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C                                          # noqa: E402

import ksemi_page as P                                       # noqa: E402

HAS = C.has_asset(os.path.join("xi1", "progress.json"))


def _cells(table_html):
    """(머리 칸 수, [본문 행 칸 수, …])."""
    head, _, body = table_html.partition("</thead>")
    return (len(re.findall(r"<th[ >]", head)),
            [len(re.findall(r"<td[ >]", tr)) for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S)])


def _table(page_html, marker):
    """marker 가 머리행에 들어 있는 첫 data-sortable 표."""
    for t in re.findall(r"<table[^>]*data-sortable.*?</table>", page_html, re.S):
        if marker in t.partition("</thead>")[0]:
            return t
    return None


class TestRcps(unittest.TestCase):

    def test_supersedes_list_string_none(self):
        self.assertEqual(P.xi_rcps({"rcp": "20260101000001"}), ["20260101000001"])
        self.assertEqual(P.xi_rcps({"rcp": "B", "supersedes": ["A0", "A1"]}), ["B", "A0", "A1"])
        self.assertEqual(P.xi_rcps({"rcp": "B", "supersedes": "A0"}), ["B", "A0"])
        self.assertEqual(P.xi_rcps({"rcp": "B", "supersedes": None}), ["B"])

    def test_missing_file_is_none(self):
        self.assertIsNone(P.load_xi1(["042700"], path=os.path.join(C.HERE, "no_such_progress.json")))

    def test_import_failure_is_none(self):
        # 공용 층을 못 불러오면(None 을 sys.modules 에 두면 import 가 ImportError) 경고만 남기고 None
        with mock.patch.dict(sys.modules, {"xi1_view": None}), redirect_stderr(io.StringIO()) as err:
            self.assertIsNone(P.load_xi1(["042700"]))
        self.assertIn("XI-1", err.getvalue())


@unittest.skipUnless(HAS, "tools/assets/xi1/progress.json 이 아직 없다")
class TestXi1Pages(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with redirect_stderr(io.StringIO()):
            cls.data = P.load_all()
        cls.sums = [P.summary(cls.data, r) for r in P.members(cls.data)]
        cls.mem = {s["stock"] for s in cls.sums}
        x = cls.data["xi1"]
        assert x, "progress.json 이 있는데 load_xi1 이 None"
        cls.prog, cls.V = x["prog"], x["view"]
        # 섹션이 있고 원장 표에 진행 칸이 붙는 회사 하나
        cls.pick = None
        for s in cls.sums:
            if cls.V.company_section(cls.prog, s["stock"]) and \
                    any(cls.V.contract_of(cls.prog, P.xi_rcps(c)) for c in s["contracts"]):
                cls.pick = s
                break

    def _off(self):
        d = dict(self.data)
        d["xi1"] = None
        return d

    def test_subset_matches_screen_population(self):
        self.assertEqual(set(self.prog["companies"]), self.mem & set(self.prog["companies"]))
        self.assertTrue(all(c["stock"] in self.mem for c in self.prog["contracts"]))
        sec = self.prog["sector"]
        self.assertEqual(sec["linkA"] + sec["linkB"] + sec["xi_only"], len(self.prog["contracts"]))
        hub = P.hub_html(self.data, self.sums)
        self.assertIn("<b>%d / %d</b>" % (sec["cos_with_rows"], len(self.prog["companies"])), hub)

    def test_company_page_has_section_and_column(self):
        if self.pick is None:
            self.skipTest("섹션과 원장 연결이 함께 있는 회사가 없다")
        h = P.company_html(self.data, self.pick)
        self.assertIn('id="xi1"', h)
        self.assertIn('<a href="#xi1">계약 진행</a>', h)
        self.assertIn("XI-1 「공시내용 진행 및 변경사항」", h.split("<footer>")[1])
        self.assertEqual(h.count("<style>%s</style>" % self.V.CSS), 1)
        t = _table(h, "진행(XI-1)")
        self.assertIsNotNone(t)
        self.assertIn('id="ct"', t)
        nth, rows = _cells(t)
        self.assertEqual(len(rows), len(self.pick["contracts"]))
        self.assertTrue(all(n == nth for n in rows), (nth, set(rows)))
        vals = re.findall(r'<td class="n xi1c[^"]*" data-v="([^"]+)"', t)
        self.assertEqual(len(vals), len(rows))
        self.assertTrue(any(v != "-1" for v in vals))
        # 진행 열은 금액(억) 바로 뒤 — 정렬 칸 번호가 머리행과 맞는다
        heads = re.findall(r"<th[^>]*>(.*?)</th>", t.partition("</thead>")[0])
        self.assertEqual(heads.index("금액(억)") + 1, heads.index("진행(XI-1)"))

    def test_supersedes_chain_finds_progress(self):
        rcp, cid = next(iter(self.prog["by_rcp"].items()))
        fake = {"rcp": "99999999999999", "supersedes": [rcp]}
        th, cells = P.xi1_column(self.data, [fake, {"rcp": "99999999999998"}])
        self.assertIn("진행(XI-1)", th)
        self.assertIn("xi1c", cells[0])
        c = self.V.contract_of(self.prog, [rcp])
        if self.V._segs(c):
            self.assertNotIn('data-v="-1"', cells[0])
        self.assertIn('data-v="-1">—<', cells[1])               # 진행 계약 없음 = '—'(0 이 아니다)

    def test_hub_and_coverage(self):
        hub = P.hub_html(self.data, self.sums)
        self.assertIn('id="xi1"', hub)
        self.assertIn('<a href="#xi1">계약 진행</a>', hub)
        t = _table(hub, "진행(XI-1)")
        self.assertIsNotNone(t)
        nth, rows = _cells(t)
        self.assertTrue(rows and all(n == nth for n in rows))
        # 허브 회사 링크는 회사 페이지가 있는 종목만
        sec = hub[hub.index('id="xi1"'):]
        for st in re.findall(r'<a href="(\d{6})/index.html">', sec):
            self.assertIn(st, self.mem)
        cov = P.coverage_html(self.data, self.sums)
        self.assertIn('id="xi1cov"', cov)
        self.assertIn('<a href="#xi1cov">', cov)
        part = cov[cov.index('id="xi1cov"'):]
        part = part[:part.index("</section>")]
        listed = set(re.findall(r"<tr><td>(\d{6})</td>", part))
        self.assertEqual(listed, set(self.prog["companies"]))
        self.assertTrue(listed <= self.mem)

    def test_off_is_current_page(self):
        d = self._off()
        for h in [P.hub_html(d, self.sums), P.coverage_html(d, self.sums)] + \
                 [P.company_html(d, s) for s in self.sums[:12] + ([self.pick] if self.pick else [])]:
            self.assertNotIn("xi1", h)
            self.assertNotIn("진행(XI-1)", h)
            self.assertNotIn("XI-1", h.split("<footer>")[1])
            self.assertNotIn('href="#xi1', h)

    def test_view_failure_drops_column_and_section(self):
        class Boom(object):
            CSS = ".xi1{}"

            def __getattr__(self, k):
                def f(*a, **kw):
                    raise RuntimeError("boom " + k)
                return f
        d = dict(self.data)
        d["xi1"] = {"prog": copy.deepcopy(self.prog), "view": Boom()}
        s = self.pick or self.sums[0]
        with redirect_stderr(io.StringIO()) as err:
            h = P.company_html(d, s)
            hub = P.hub_html(d, self.sums)
            cov = P.coverage_html(d, self.sums)
        self.assertIn("boom", err.getvalue())
        for x in (h, hub, cov):
            self.assertNotIn('id="xi1', x)
            self.assertNotIn("진행(XI-1)", x)
            self.assertNotIn("XI-1", x.split("<footer>")[1])
        if s["contracts"]:
            nth, rows = _cells(_table(h, "금액(억)"))
            self.assertTrue(all(n == nth for n in rows))


if __name__ == "__main__":
    unittest.main()
