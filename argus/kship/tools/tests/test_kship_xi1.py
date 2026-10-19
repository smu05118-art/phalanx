#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계약 진행(XI-1) 화면 통합 — kship_page / kship_parts 훅 (네트워크 없음, 레포 파일은 읽기만).

progress.json(assets/xi1, 공용 층 kce/tools/xi1_sector 적재)이 있으면
  · 조선사 페이지: 척당 계약 표(#ct) '진행(XI-1)' 열(머리글·행 칸 수 일치, data-v 정렬) + 섹션 #xi1(모델 섹션보다 앞 · 정렬 JS 보다 앞)
  · 기자재 페이지: 진행 계약이 있는 회사만 #xi1
  · 허브: #xi1(회사 페이지가 있는 종목만 링크 — 지주 009540 은 페이지가 없다) · 커버리지: #xi1cov
없으면(None·파일 없음·import 실패) 예외 없이 예전 화면(열·섹션·CSS·꼬리말 문구 없음).

실행: cd argus/kship/tools && python3 -m unittest tests.test_kship_xi1 -v
"""
import contextlib
import io
import os
import re
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

import kship_page as P                                      # noqa: E402
import kship_parts as PT                                    # noqa: E402

HAS_PROGRESS = os.path.isfile(P.XI1_PROGRESS)
YARD = "329180"


def _ct(h):
    """#ct 표 → (머리글 이름 목록, 행별 td 목록)."""
    t = re.search(r'<table id="ct".*?</table>', h, re.S).group(0)
    head = re.search(r"<thead>(.*?)</thead>", t, re.S).group(1)
    ths = [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(r"<th[^>]*>(.*?)</th>", head, re.S)]
    body = re.search(r"<tbody>(.*?)</tbody>", t, re.S).group(1)
    rows = [re.findall(r"<td[^>]*>.*?</td>", r, re.S) for r in re.findall(r"<tr>(.*?)</tr>", body, re.S)]
    return ths, rows


class TestXi1Helpers(unittest.TestCase):
    def test_rcp_chain_accepts_string_list_and_none(self):
        self.assertEqual(P.xi1_rcps({"rcp": "B", "supersedes": "A"}), ["B", "A"])
        self.assertEqual(P.xi1_rcps({"rcp": "C", "supersedes": ["B", "A"]}), ["C", "B", "A"])
        self.assertEqual(P.xi1_rcps({"rcp": "C", "supersedes": None}), ["C"])
        self.assertEqual(P.xi1_rcps({"rcp": "C"}), ["C"])

    def test_missing_progress_is_silent_none(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(P.load_xi1(path=os.path.join(HERE, "no_such_progress.json")), (None, None))
        self.assertEqual(err.getvalue(), "")                        # 파일 없음은 정상 — 경고도 없다

    def test_import_failure_is_fail_soft_with_warning(self):
        err = io.StringIO()
        with patch.dict(sys.modules, {"xi1_view": None}), contextlib.redirect_stderr(err):
            self.assertEqual(P.load_xi1(), (None, None))
        self.assertIn("[warn] 계약 진행(XI-1) 비활성", err.getvalue())

    def test_xi1_of_tolerates_old_data_dicts(self):
        self.assertEqual(P.xi1_of({}), (None, None))
        self.assertEqual(P.xi1_of({"xi1": (None, None)}), (None, None))
        self.assertEqual(P.xi1_company({}, YARD), "")
        self.assertEqual(P.xi1_css({}), "")

    @unittest.skipUnless(HAS_PROGRESS, "assets/xi1/progress.json 없음")
    def test_subset_drops_stocks_outside_screen_population(self):
        xv, prog = P.load_xi1()
        keep = [YARD, "010140"]
        xv2, sub = P.load_xi1(stocks=keep)
        self.assertEqual(sorted(sub["companies"]), sorted(keep))
        self.assertTrue(all(c["stock"] in keep for c in sub["contracts"]))
        self.assertLess(sub["sector"]["n"], prog["sector"]["n"])


@unittest.skipUnless(HAS_PROGRESS, "assets/xi1/progress.json 없음")
class TestXi1Pages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.err = io.StringIO()
        with contextlib.redirect_stderr(cls.err):
            cls.data = P.load_all()
            cls.off = dict(cls.data, xi1=(None, None))
            cls.s = P.yard_summary(YARD, cls.data)
            cls.on_html = P.yard_html(cls.s, cls.data)
            cls.off_html = P.yard_html(cls.s, cls.off)
            cls.summaries = [P.yard_summary(st, cls.data) for st, y in cls.data["yards"].items() if y["q"]]

    def test_load_all_attaches_progress_without_warnings(self):
        xv, prog = P.xi1_of(self.data)
        self.assertIsNotNone(xv)
        self.assertEqual(prog["tab"], "kship")
        self.assertNotIn("XI-1", self.err.getvalue())

    def test_yard_page_has_progress_column_and_section(self):
        h = self.on_html
        self.assertIn('id="xi1"', h)
        self.assertIn("xi1c", h)
        ths, rows = _ct(h)
        self.assertEqual(ths[ths.index("금액(억)") + 1], "진행(XI-1)")
        self.assertEqual(len(rows), len(self.s["contracts"]))
        self.assertTrue(all(len(r) == len(ths) for r in rows), "행 칸 수 ≠ 머리글")
        col = ths.index("진행(XI-1)")
        vals = [re.search(r'data-v="([^"]+)"', r[col]).group(1) for r in rows]
        self.assertTrue(all(float(v) == -1 or float(v) >= 0 for v in vals), vals)   # 정렬 키 = 진행률(없으면 -1)
        self.assertTrue(any(float(v) >= 0 for v in vals), "연결된 진행 계약이 하나도 없다")
        # 섹션은 실적 모델 섹션보다 앞(selfcheck_models._section_html 은 모델 섹션부터 끝까지 읽는다), 정렬 JS 보다 앞
        i = h.index('id="xi1"')
        self.assertLess(i, h.index('id="kship-model-%s"' % YARD) if 'id="kship-model-%s"' % YARD in h else len(h))
        self.assertLess(i, h.index("table[data-sortable]"))
        self.assertIn('href="#xi1"', h)
        self.assertIn("XI-1 「공시내용 진행 및 변경사항」", h)
        self.assertEqual(h.count(P.xi1_of(self.data)[0].CSS), 1)      # 조각 CSS 는 한 번만

    def test_yard_page_without_progress_is_unchanged_shape(self):
        h = self.off_html
        self.assertNotIn("xi1", h)
        self.assertNotIn("XI-1", h)
        ths, rows = _ct(h)
        self.assertEqual(ths, ["수주일", "선종", "계약명", "척", "금액(억)", "상대", "지역", "인도(종료일)", "대금조건", "출처"])
        self.assertTrue(all(len(r) == 10 for r in rows))
        self.assertIn("<footer>출처 DART 정기보고서·수시공시, KRX KIND", h)
        # 옛 data(키 없음)도 같은 화면
        self.assertEqual(P.yard_html(self.s, {k: v for k, v in self.data.items() if k != "xi1"}), h)

    def test_removing_xi1_parts_gives_the_old_page(self):
        """켠 화면에서 XI-1 조각(열·섹션·CSS·내비·꼬리말·리드)을 걷어 내면 끈 화면과 바이트가 같다 — 다른 곳은 건드리지 않았다."""
        xv, prog = P.xi1_of(self.data)
        h = self.on_html
        h = h.replace("<style>%s</style>\n" % xv.CSS, "", 1)
        h = h.replace(P.xi1_company(self.data, YARD), "", 1)
        h = h.replace(xv.progress_th(), "", 1)
        h = re.sub(r'<td class="n xi1c[^"]*" data-v="[^"]*"(?: title="[^"]*")?>.*?</td>', "", h)
        h = h.replace('<a href="#xi1">계약 진행</a>', "", 1).replace("(%s)" % P.XI1_SRC, "", 1).replace(P.XI1_LEAD, "", 1)
        self.assertEqual(h, self.off_html)

    def test_deterministic(self):
        self.assertEqual(P.yard_html(self.s, self.data), self.on_html)

    def test_hub_section_links_only_companies_with_pages(self):
        on = P.hub_html(self.data, self.summaries)
        off = P.hub_html(self.off, self.summaries)
        self.assertIn('id="xi1"', on)
        self.assertIn('href="#xi1"', on)
        self.assertIn("table[data-sortable]", on)                    # 허브 표 정렬 JS 는 섹션이 있을 때만
        links = set(re.findall(r'href="(\d{6})/index\.html#xi1"', on))
        pages = {s["stock"] for s in self.summaries} | {c["stock"] for c in self.data["suppliers"]["cos"]}
        self.assertTrue(links)
        self.assertLessEqual(links, pages)
        self.assertNotIn("009540/index.html", on)                     # 지주는 페이지가 없다
        self.assertNotIn("xi1", off)
        self.assertNotIn("table[data-sortable]", off)

    def test_coverage_rows(self):
        on = P.coverage_html(self.data, self.summaries)
        off = P.coverage_html(self.off, self.summaries)
        self.assertIn('id="xi1cov"', on)
        self.assertLess(on.index('id="xi1cov"'), on.index("table[data-sortable]"))
        self.assertNotIn("xi1", off)

    def test_supplier_page_section_only_with_contracts(self):
        xv, prog = P.xi1_of(self.data)
        cos = {c["stock"]: c for c in self.data["suppliers"]["cos"]}
        with_rows = [st for st in sorted(cos) if any(c["stock"] == st for c in prog["contracts"])]
        without = [st for st in sorted(cos) if st not in with_rows]
        self.assertTrue(with_rows and without)
        h = PT.supplier_html(cos[with_rows[0]], self.data)
        self.assertIn('id="xi1"', h)
        self.assertLess(h.index('id="xi1"'), h.index("table[data-sortable]"))
        if 'id="kship-model-%s"' % with_rows[0] in h:
            self.assertLess(h.index('id="xi1"'), h.index('id="kship-model-%s"' % with_rows[0]))
        self.assertNotIn("xi1", PT.supplier_html(cos[without[0]], self.data))
        self.assertNotIn("xi1", PT.supplier_html(cos[with_rows[0]], self.off))

    def test_render_failure_drops_only_the_fragment(self):
        xv, prog = P.xi1_of(self.data)

        class Boom:
            CSS = xv.CSS

            def __getattr__(self, name):
                def f(*a, **k):
                    raise RuntimeError("boom")
                return f
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            h = P.yard_html(self.s, dict(self.data, xi1=(Boom(), prog)))
        self.assertIn("[warn]", err.getvalue())
        self.assertEqual(h, self.off_html)                            # 조각만 빠지고 나머지는 예전 그대로


class TestXi1Workflow(unittest.TestCase):
    """update-kship.yml — XI-1 단계는 원장 build 뒤 · 페이지 앞, 실패해도 다음 단계가 돈다(continue-on-error), 커밋·요약·실패 판정에 들어간다."""

    @classmethod
    def setUpClass(cls):
        yml = os.path.join(TOOLS, "..", "..", "..", ".github", "workflows", "update-kship.yml")
        with open(yml, encoding="utf-8") as f:
            cls.text = f.read()
        cls.steps = re.split(r"\n      - ", cls.text)

    def _step(self, sid):
        return next(s for s in self.steps if "\n        id: %s\n" % sid in "\n" + s)

    def test_order_and_fail_soft(self):
        t = self.text
        cmd = "python3 ../../kce/tools/xi1_sector.py kship --collect --build"
        self.assertLess(t.index("python3 kship_contracts.py --build"), t.index(cmd))
        self.assertLess(t.index(cmd), t.index("python3 kship_page.py --all"))
        st = self._step("xi1")
        self.assertIn(cmd, st)
        self.assertIn("continue-on-error: true", st)
        self.assertIn("working-directory: argus/kship/tools", st)
        self.assertRegex(st, r"timeout-minutes:\s*\d+")
        self.assertNotIn("xi1", self._step("pages"))                   # 페이지 단계는 XI-1 결과에 기대지 않는다(직전 progress.json)

    def test_commit_summary_and_failure_gate(self):
        t = self.text
        self.assertIn("O_XI1: ${{ steps.xi1.outcome }}", t)
        self.assertIn('$(part XI-1 "$O_XI1")', t)
        self.assertIn("steps.xi1.outputs.summary", t)
        self.assertIn("steps.xi1.outcome == 'failure'", t)
        self.assertIn("git add -A -- argus/kship argus/index.html", t)  # assets/xi1·hdrmap 은 이미 커밋 범위


if __name__ == "__main__":
    unittest.main()
