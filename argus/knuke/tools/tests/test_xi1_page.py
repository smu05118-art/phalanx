#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계약 진행(XI-1) 화면 통합 — knuke_page 가 공용 조각(argus/kce/tools/xi1_view.py)을 붙이는지(2026-10-20).

(1) progress 가 있으면 원장 계약 표에 '진행(XI-1)' 열(머리행·행 칸 수 일치 = 정렬 칸 번호 유지), 회사·허브 섹션(id="xi1"),
    커버리지 수집 상태 표(id="xi1cov"), 내비 #xi1, 꼬리말 출처가 나온다.
(2) progress 가 None(파일 없음·import/적재 실패)이면 예외 없이 XI-1 흔적이 하나도 없는 지금 화면이 나온다.
네트워크 0 · 쓰기 0(문자열만 만든다). 픽스처는 커밋된 knuke progress.json 을 두 회사로 줄인 것:
  python3 -c "import sys,json;sys.path.insert(0,'../../kce/tools');import xi1_sector as X;
  s=X.subset(X.load_progress('knuke'),['083650','052690']);
  open('tests/fixtures/xi1_progress_083650_052690.json','w').write(json.dumps(s,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\\n')"
"""
import io
import json
import os
import re
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import knuke_page as P                                       # noqa: E402
import xi1_sector                                            # noqa: E402
import xi1_view                                              # noqa: E402

# *_lib 이 argus/kce/tools·kship/tools 를 sys.path 앞에 넣는다 — 이 탭 tools 를 다시 맨 앞에(같은 이름 모듈 충돌 방지)
sys.path.remove(TOOLS)
sys.path.insert(0, TOOLS)

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "xi1_progress_083650_052690.json")


def _prog():
    with open(FIX, encoding="utf-8") as f:
        return json.load(f)


def _row(rcp, stock="052690", supersedes=None, amt=1000.0):
    return {"rcp": rcp, "stock": stock, "title": "단일판매ㆍ공급계약체결", "corrected": bool(supersedes),
            "name": "시험 계약 %s" % rcp[-4:], "domain": None, "tier": "UNKNOWN", "smr": False, "amt_krw_m": amt,
            "party": "한국수력원자력(주)", "party_kind": "GOV", "party_prime": None, "start": "2024-01-01",
            "end": "2027-12-31", "years": 4.0, "signed": "2024-01-01", "withheld": "-", "tier_basis": "name",
            "kind_raw": "", "supersedes": supersedes}


def _cells(table_html):
    """thead th 수, tbody 각 행의 칸 수."""
    head = re.search(r"<thead>(.*?)</thead>", table_html, re.S).group(1)
    body = re.search(r"<tbody>(.*?)</tbody>", table_html, re.S).group(1)
    nth = len(re.findall(r"<th[ >]", head))
    rows = [len(re.findall(r"<td[ >]", tr)) for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S)]
    return nth, rows


def _section(html, sid):
    i = html.index('id="%s"' % sid)
    return html[i:html.index("</section>", i)]


class TestXi1Load(unittest.TestCase):

    def test_missing_progress_is_none(self):
        with mock.patch.object(xi1_sector, "load_progress", return_value=None):
            self.assertEqual(P.load_xi1(["052690"]), (None, None))

    def test_load_error_is_none_with_warning(self):
        err = io.StringIO()
        with mock.patch.object(xi1_sector, "load_progress", side_effect=ValueError("깨진 JSON")), redirect_stderr(err):
            self.assertEqual(P.load_xi1(), (None, None))
        self.assertIn("XI-1", err.getvalue())

    def test_import_error_is_none(self):
        with mock.patch.dict(sys.modules, {"xi1_view": None}), redirect_stderr(io.StringIO()):
            self.assertEqual(P.load_xi1(), (None, None))

    def test_subset_to_screen_universe(self):
        with mock.patch.object(xi1_sector, "load_progress", return_value=_prog()):
            prog, xv = P.load_xi1(["083650"])
        self.assertIs(xv, xi1_view)
        self.assertEqual(set(prog["companies"]), {"083650"})
        self.assertTrue(all(c["stock"] == "083650" for c in prog["contracts"]))
        self.assertTrue(all(i.startswith("083650-") for i in prog["by_rcp"].values()))

    def test_no_subset_when_universe_covers(self):
        p = _prog()
        with mock.patch.object(xi1_sector, "load_progress", return_value=p):
            prog, _ = P.load_xi1(["083650", "052690", "034020"])
        self.assertIs(prog, p)                     # 섹터 집계를 다시 내지 않는다(같은 바이트)


class TestXi1Column(unittest.TestCase):

    def setUp(self):
        self.prog = _prog()
        ids = {c["id"]: c for c in self.prog["contracts"]}
        self.linked = next(r for r, i in sorted(self.prog["by_rcp"].items())
                           if i.startswith("052690-") and ids[i]["m"].get("prog") is not None
                           and ids[i]["m"].get("amt") and ids[i]["hist"].get(ids[i]["m"]["q"]))
        self.data = {"doms": {}, "tiers": {}, "xi1": self.prog, "xv": xi1_view}

    def test_column_and_alignment(self):
        rows = [_row(self.linked), _row("20990101000001"), _row("20990101000002", supersedes=self.linked)]
        for show in (False, True):
            h = P.contracts_table(rows, self.data, tid="t", show_company=show, by_stock={"052690": {"name": "한전기술"}})
            nth, cells = _cells(h)
            self.assertEqual(cells, [nth] * 3)
            self.assertIn(">진행(XI-1)</th>", h)
            # 금액(억) 바로 뒤 칸
            head = re.findall(r"<th[^>]*>(.*?)</th>", re.search(r"<thead>(.*?)</thead>", h, re.S).group(1))
            self.assertEqual(head[head.index("금액(억)") + 1], "진행(XI-1)")
        # 표는 수주일 내림차순 — 같은 날이면 입력 순(sorted 는 reverse 여도 안정)
        vals = [float(v) for v in re.findall(r'<td class="n xi1c[^"]*" data-v="([^"]+)"', h)]
        self.assertEqual(len(vals), 3)
        self.assertGreaterEqual(vals[0], 0)        # rcp 로 연결
        self.assertEqual(vals[1], -1)              # 진행 표에 없는 계약 = '—'(0 이 아니다)
        self.assertEqual(vals[2], vals[0])         # 정정 공시는 supersedes(옛 rcp) 사슬로 같은 계약을 찾는다

    def test_no_column_without_progress(self):
        rows = [_row(self.linked)]
        h0 = P.contracts_table(rows, dict(self.data, xi1=None), tid="t")
        self.assertNotIn("xi1", h0)
        self.assertNotIn("진행(XI-1)", h0)
        nth, cells = _cells(h0)
        self.assertEqual((nth, cells), (9, [9]))

    def test_cell_error_keeps_alignment(self):
        err = io.StringIO()
        with mock.patch.object(xi1_view, "progress_cell", side_effect=KeyError("m")), redirect_stderr(err):
            h = P.contracts_table([_row(self.linked)], self.data, tid="t")
        nth, cells = _cells(h)
        self.assertEqual(cells, [nth])
        self.assertIn('data-v="-1">—</td>', h)


class TestXi1Pages(unittest.TestCase):
    """실제 원장·정기보고서 자산(읽기만) + 픽스처 progress 로 회사·허브·커버리지 페이지를 만든다."""

    @classmethod
    def setUpClass(cls):
        with redirect_stderr(io.StringIO()):
            cls.base = P.load_all()
        cls.sums = [P.summary(r["stock"], cls.base) for r in cls.base["uni"]]
        cls.by = {s["stock"]: s for s in cls.sums}

    def _data(self, prog):
        d = dict(self.base)
        d["xi1"], d["xv"] = (prog, xi1_view) if prog else (None, None)
        return d

    def test_company_with_progress(self):
        prog = _prog()
        for st in ("083650", "052690"):
            s = self.by[st]
            self.assertTrue(P.has_page(s))
            with redirect_stderr(io.StringIO()):
                h = P.company_html(s, self._data(prog))
            self.assertEqual(h.count('id="xi1"'), 1)
            self.assertIn('class="n xi1c', h)
            self.assertIn('href="#xi1"', h)
            self.assertIn("공시내용 진행 및 변경사항", h)
            self.assertIn(".xi1c .xb", h)          # 조각 CSS 를 한 번 싣는다
            nth, cells = _cells(h[h.index('id="ct%s"' % st):])
            self.assertTrue(cells and all(n == nth for n in cells))

    def test_company_without_progress_is_unchanged_shape(self):
        for st in ("083650", "052690"):
            with redirect_stderr(io.StringIO()):
                h = P.company_html(self.by[st], self._data(None))
            for needle in ("xi1", "XI-1", "#xi1", "진행 및 변경사항"):
                self.assertNotIn(needle, h)

    def test_company_not_in_progress_has_no_section(self):
        st = next(s["stock"] for s in self.sums if P.has_page(s) and s["contracts"] and s["stock"] not in ("083650", "052690"))
        with redirect_stderr(io.StringIO()):
            h = P.company_html(self.by[st], self._data(_prog()))
        self.assertNotIn('id="xi1"', h)
        self.assertNotIn('href="#xi1"', h)
        self.assertIn(">진행(XI-1)</th>", h)        # 열은 있되 칸은 '—'
        self.assertNotRegex(h, r'class="n xi1c" data-v="[0-9]')

    def test_hub_and_coverage(self):
        prog = _prog()
        with redirect_stderr(io.StringIO()):
            hub = P.hub_html(self._data(prog), self.sums)
            cov = P.coverage_html(self._data(prog), self.sums)
            # 회사 페이지가 없는 종목은 허브 섹션에서 링크하지 않는다
            sums2 = [s for s in self.sums if s["stock"] != "052690"]
            hub2 = P.hub_html(self._data(prog), sums2)
            hub0 = P.hub_html(self._data(None), self.sums)
            cov0 = P.coverage_html(self._data(None), self.sums)
        sec = _section(hub, "xi1")
        self.assertIn('href="#xi1"', hub)
        self.assertIn("083650/index.html", sec)
        self.assertIn("052690/index.html", sec)
        self.assertNotIn("052690/index.html", _section(hub2, "xi1"))
        nth, cells = _cells(hub[hub.index('id="cbig"'):])
        self.assertTrue(cells and all(n == nth for n in cells))
        self.assertIn('id="xi1cov"', cov)
        self.assertIn('href="#xi1cov"', cov)
        for h in (hub0, cov0):
            self.assertNotIn("xi1", h)
            self.assertNotIn("XI-1", h)


if __name__ == "__main__":
    unittest.main()
