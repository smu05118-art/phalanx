#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""생성 페이지(lite 대시보드·커버리지 지도·회사 선택)의 계약 테스트.

이 계층에는 테스트가 없었다 — 감사에서 "kce_page를 다루는 테스트가 하나도 없어
json_for_html 이스케이프 계약이 회귀를 감지하지 못한다"가 지적됐다.

실행: cd argus/kce/tools && python3 -m unittest discover -s tests
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

import kce_page                                       # noqa: E402
from kce_lib import CORP                              # noqa: E402
from kce_universe import load as load_universe        # noqa: E402


def _probe():
    path = kce_page.newest_probe()
    with open(path, encoding="utf-8") as f:
        return {r["stock"]: r for r in json.load(f)["rows"]}


def _base_D(**over):
    """company_html이 받는 최소 DATA."""
    fq = ["2026Q1", "2026Q2"]
    D = {
        "co": "테스트건설", "stock": "999999", "slug": "999999",
        "market": "코스닥", "industry": "건물 건설업",
        "fq": fq, "codeGen": "2026-09-10", "grain": "project",
        "src": {"2026Q2": "20260814000001"},
        "sites": [{
            "id": "999999-0001", "nm": "테스트현장", "cl": "테스트발주처",
            "reg": "국내", "seg": "건축", "sd": "2025-01", "ed": "2027-12",
            "s": {"amt": [100, 100], "cmp": [10, 20], "bal": [90, 80],
                  "pr": [10.0, 20.0]},
        }],
        "summary": {"amt": [100, 100], "cmp": [10, 20], "bal": [90, 80]},
        "declared": [90, 80], "dom": [90, 80], "ovs": [None, None],
        "segList": ["건축"], "seg": {"건축": [90, 80]},
        "recon": [100.0, 100.0], "reconOver": [],
    }
    D.update(over)
    return D


class TestScriptSafety(unittest.TestCase):
    """DART 셀 텍스트는 신뢰할 수 없는 입력이다 — 임베드 JSON이 스크립트를 깨면 안 된다."""

    def test_closing_script_tag_in_site_name_is_escaped(self):
        D = _base_D()
        D["sites"][0]["nm"] = "악성</script><img src=x onerror=alert(1)>현장"
        html = kce_page.company_html(D)
        # 원문 그대로의 종료 태그가 문서에 남으면 그 자리에서 스크립트가 끝난다
        self.assertNotIn("</script><img", html)
        self.assertIn("\\u003c/script", html)
        # 스크립트 블록 수가 그대로여야 한다(조기 종료로 늘어나지 않았는가)
        self.assertEqual(html.count("<script"), html.count("</script>"))

    def test_embedded_json_round_trips(self):
        D = _base_D()
        D["sites"][0]["cl"] = "따옴표\"와 <꺾쇠> 그리고 \u2028줄바꿈"
        html = kce_page.company_html(D)
        m = re.search(r"const DATA\s*=\s*(\{.*?\});", html, re.S)
        self.assertIsNotNone(m, "임베드 DATA를 찾지 못했다")
        blob = (m.group(1).replace("\\u003c", "<")
                          .replace("\\u2028", "\u2028")
                          .replace("\\u2029", "\u2029"))
        back = json.loads(blob)
        self.assertEqual(back["sites"][0]["cl"], D["sites"][0]["cl"])


class TestGrainHonesty(unittest.TestCase):
    """부문 단위로만 공시하는 회사에 '현장별'이라고 쓰면 없는 정밀도를 주장하게 된다."""

    def test_project_grain_says_site(self):
        html = kce_page.company_html(_base_D(grain="project"))
        self.assertIn("현장별 데이터", html)
        self.assertNotIn("부문별 데이터", html)

    def test_segment_grain_says_segment(self):
        html = kce_page.company_html(_base_D(grain="segment"))
        self.assertIn("부문별 데이터", html)
        self.assertNotIn("현장별 데이터", html)

    def test_segment_grain_discloses_the_limitation(self):
        """부문 단위라는 사실이 화면 어딘가에 **글로** 남아야 한다.

        라벨만 바꾸면 '부문별'이 무슨 뜻인지 모르는 사람에게는 같은 화면으로 보인다.
        """
        html = kce_page.company_html(_base_D(grain="segment"))
        self.assertRegex(html, r"사업부문|부문 단위|부문 합계")


class TestCoverageMap(unittest.TestCase):
    """커버리지 지도는 모집단을 하나도 빠뜨리지 않고, 미수록에는 사유가 붙어야 한다."""

    def setUp(self):
        self.recs = load_universe()
        if not self.recs:
            self.skipTest("universe.json 없음")
        self.probe = _probe()
        self.html = kce_page.coverage_html(self.recs, self.probe, {})

    def test_every_company_appears(self):
        for r in self.recs:
            self.assertIn(r["name"].replace("&", "&amp;"), self.html, r["stock"])

    def test_rule_text_is_derived_not_hardcoded(self):
        """규칙 문구를 손으로 적어 두면 규칙이 바뀔 때 화면만 옛말을 한다."""
        seeds = [r["name"] for r in self.recs if r.get("source") == "지정"]
        self.assertTrue(seeds, "지정 종목이 없다 — 픽스처 전제가 깨졌다")
        for nm in seeds:
            self.assertIn(nm.replace("&", "&amp;"), self.html, nm)

    def test_non_covered_companies_carry_a_reason(self):
        """조용한 배제 금지 — 수록하지 않은 회사에는 근거가 적혀야 한다."""
        for r in self.recs:
            p = self.probe.get(r["stock"])
            if p and p["tier"] not in ("site", "segment"):
                self.assertTrue(p.get("note"), "%s 사유 없음" % r["stock"])


class TestPicker(unittest.TestCase):
    """회사 선택 화면은 원형 카드를 하나도 잃지 않고 커버리지로 가는 길을 내야 한다."""

    def setUp(self):
        base = kce_page.PICKER_BASE
        if not os.path.exists(base):
            self.skipTest("picker_base.html 없음")
        with open(base, encoding="utf-8") as f:
            self.base = f.read()
        self.recs = load_universe()
        if not self.recs:
            self.skipTest("universe.json 없음")

    def test_all_base_cards_survive(self):
        cards = re.findall(r'<a class="card"[^>]*>.*?</a>', self.base, re.S)
        self.assertTrue(cards, "원형에 카드가 없다")
        out = kce_page.picker_html(self.recs, _probe(), {}, self.base)
        for c in cards:
            self.assertIn(c, out, "원형 카드가 사라졌다")

    def test_coverage_is_reachable(self):
        """lite 회사 대다수는 커버리지 지도를 통해서만 도달한다 — 링크가 끊기면 고아가 된다."""
        out = kce_page.picker_html(self.recs, _probe(), {}, self.base)
        self.assertIn('href="coverage.html"', out)


class TestGeneratedPagesOnDisk(unittest.TestCase):
    """실제로 배포될 산출물 점검(생성물이 없으면 건너뛴다)."""

    def test_no_broken_local_links(self):
        pages = []
        for name in os.listdir(KCE):
            p = os.path.join(KCE, name)
            if name == "tools":
                continue
            if name.endswith(".html"):
                pages.append(p)
            elif os.path.isdir(p):
                q = os.path.join(p, "index.html")
                if os.path.exists(q):
                    pages.append(q)
        if not pages:
            self.skipTest("생성물 없음")
        broken = []
        for page in pages:
            with open(page, encoding="utf-8") as f:
                html = f.read()
            for href in re.findall(r'(?:href|src)="([^"#?:]+)"', html):
                if href.startswith(("http", "//", "mailto:", "data:")):
                    continue
                target = os.path.normpath(
                    os.path.join(os.path.dirname(page), href))
                if not os.path.exists(target):
                    broken.append("%s -> %s" % (os.path.relpath(page, KCE), href))
        self.assertEqual(broken, [], "깨진 내부 링크")


if __name__ == "__main__":
    unittest.main()
