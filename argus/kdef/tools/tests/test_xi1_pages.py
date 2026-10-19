#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계약 진행(XI-1) 화면 통합 테스트 — 네트워크 없이.

  · progress 가 있으면 원장 표에 '진행(XI-1)' 열(정정 사슬 supersedes 로도 찾는다) · 회사/허브 섹션(id="xi1") ·
    커버리지 수집 상태(id="xi1cov") · 꼬리말 원천 · 내비 #xi1 이 나온다.
  · progress 가 None 이면 페이지가 예외 없이 **지금과 같은 바이트**로 나온다(열·섹션·꼬리말 없음).
  · 열을 더해도 표의 기존 표지(해지 pill 수)는 그대로다.
  · load_xi1 은 fail-soft(읽기 실패 → None)이고, 화면 모집단 밖 종목은 subset 으로 걸러낸다.

픽스처 fixtures/xi1_progress_sample.json = xi1_sector.subset(progress.json, [013810 스페코, 000880 한화]) — 2026Q2 실측.

    python3 -m unittest discover -s tests
"""
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for _p in (TOOLS, HERE):                      # HERE — test_detail 의 원장 행 도우미를 같이 쓴다
    if _p not in sys.path:
        sys.path.insert(0, _p)

import kdef_page as KP                                               # noqa: E402
from test_detail import _c, _data                                    # noqa: E402

FIX = os.path.join(HERE, "fixtures", "xi1_progress_sample.json")
ST = "013810"


def _prog():
    with open(FIX, encoding="utf-8") as f:
        return json.load(f)


def _ledger():
    """스페코 원장 — 픽스처의 연결 접수번호로 만든다(계통·금액은 시험용)."""
    return [
        _c(rcp="20230511900430", stock=ST, name="해군함정용 조타기 공급", domain="NAVAL", amt_krw_m=4100.0,
           signed="2023-05-11"),
        # 정정 공시 — 진행 계약은 원접수(…543)와 정정(…548) 둘 다로 이어진다. supersedes 는 문자열.
        _c(rcp="20240401900548", supersedes="20240401900543", stock=ST, name="해군함정용 조타기 및 타 공급",
           domain="NAVAL", amt_krw_m=4200.0, signed="2024-04-01", corrected=True),
        _c(rcp="20241101900578", stock=ST, name="아스팔트 믹싱플랜트 공급", domain="CIVIL", civil=True,
           amt_krw_m=4237.21, signed="2024-11-01"),
        # 외화 계약 — 진행 막대 없이 통화만. supersedes 리스트 형도 펼친다.
        _c(rcp="20260727900272", supersedes=["20260306901749"], stock=ST, name="아스팔트 배처플랜트 공급",
           domain="CIVIL", civil=True, amt_krw_m=4609.506, signed="2026-03-05"),
        # XI-1 에 짝이 없는 원장 행 — '—'.
        _c(rcp="20241127900290", stock=ST, name="아스팔트 믹싱플랜트, 순환 아스팔트 플랜트 공급", domain="CIVIL",
           civil=True, amt_krw_m=4250.0, signed="2024-03-19"),
        _c(rcp="20250101000009", stock=ST, title="단일판매ㆍ공급계약해지", amt_krw_m=100.0, signed="2025-01-01"),
    ]


def _page_data(prog):
    data = _data()
    recs = [{"stock": ST, "name": "스페코", "role": "part", "market": "KOSDAQ", "industry": "", "product": "",
             "source": "industry", "reason": ""},
            {"stock": "000880", "name": "한화", "role": "part", "market": "KOSPI", "industry": "", "product": "",
             "source": "industry", "reason": ""}]
    data["uni"] = recs
    data["by_stock"] = {r["stock"]: r for r in recs}
    data["contracts"] = _ledger()
    if prog is not ...:
        data["xi1"] = prog
    return data


def _pages(data):
    sums = [KP.summary(r["stock"], data) for r in data["uni"]]
    by = {s["stock"]: s for s in sums}
    return {"company": KP.company_html(by[ST], data), "hub": KP.hub_html(data, sums),
            "coverage": KP.coverage_html(data, sums), "table": KP.contracts_table(data["contracts"], data, tid="t")}


class TestXi1Column(unittest.TestCase):
    def test_column_cells_and_supersedes(self):
        data = _page_data(_prog())
        html = KP.contracts_table(data["contracts"], data, tid="t")
        self.assertIn("진행(XI-1)</th>", html)
        cells = [l for l in html.split("<td") if "xi1c" in l]
        self.assertEqual(len(cells), len(data["contracts"]))                 # 행마다 한 칸 — 열이 어긋나지 않는다
        # 금액(억) 바로 뒤 — 헤더 순서
        self.assertLess(html.index("<th>금액(억)</th>"), html.index("진행(XI-1)</th>"))
        self.assertLess(html.index("진행(XI-1)</th>"), html.index("<th>기간(년)</th>"))
        num = [l for l in cells if 'data-v="-1"' not in l]
        self.assertEqual(len(num), 3)              # 조타기 2건(정정 사슬 포함) + 민수 믹싱플랜트 1건이 진행률을 가진다
        self.assertIn('data-v="0.9841"', html)
        self.assertIn('data-v="0.8917"', html)     # 정정(…548) — supersedes(…543) 사슬로 찾는다
        self.assertIn(">USD<", html)               # 외화 — 막대 없이 통화(supersedes 리스트형)

    def test_pills_unchanged(self):
        with_xi = _page_data(_prog())
        without = _page_data(None)
        a = KP.contracts_table(with_xi["contracts"], with_xi, tid="t")
        b = KP.contracts_table(without["contracts"], without, tid="t")
        for mark in ('class="pill term"', 'class="pill"', 'class="pill exp"', "<tr>"):
            self.assertEqual(a.count(mark), b.count(mark), mark)
        self.assertEqual(a.count('class="pill term"'), 1)


class TestXi1Pages(unittest.TestCase):
    def test_sections_present(self):
        p = _pages(_page_data(_prog()))
        co, hub, cov = p["company"], p["hub"], p["coverage"]
        self.assertIn('id="xi1"', co)
        self.assertIn("xi1c", co)
        self.assertIn('href="#xi1"', co)                                      # 내비
        self.assertIn(KP.XI1_FOOT, co)                                        # 꼬리말 원천
        self.assertIn("<style>", co)
        self.assertIn("민수(계통 CIVIL)를 빼지 않습니다", co)
        self.assertIn("원장 연결로 민수 확인 2건", co)                        # 믹싱플랜트·배처플랜트
        self.assertIn("XI 전용 2건", co)
        # 계약 공시 표 바로 아래
        self.assertLess(co.index('id="ct013810"'), co.index('id="xi1"'))
        self.assertIn('id="xi1"', hub)
        self.assertIn('href="#xi1"', hub)
        self.assertIn(KP.XI1_FOOT, hub)
        self.assertIn('id="xi1cov"', cov)
        self.assertIn('href="#xi1cov"', cov)
        self.assertIn(KP.XI1_FOOT, cov)

    def test_hub_links_only_paged_companies(self):
        sec = KP.xi1_hub(_page_data(_prog()), {ST})
        self.assertIn('href="013810/index.html"', sec)
        self.assertNotIn('href="000880/index.html"', sec)            # 회사 페이지 없는 종목은 이름만
        self.assertIn("한화", sec)

    def test_company_without_rows_has_no_section(self):
        data = _page_data(_prog())
        self.assertEqual(KP.xi1_company(data, "999999"), "")

    def test_none_is_unchanged(self):
        """progress 없음(None) = 키 자체가 없는 지금 화면과 같은 바이트, XI-1 흔적 없음."""
        base = _pages(_page_data(...))
        none = _pages(_page_data(None))
        for k in base:
            self.assertEqual(base[k], none[k], k)
            self.assertNotIn("xi1", none[k], k)
            self.assertNotIn("XI-1", none[k], k)
            self.assertNotIn("진행(XI-1)", none[k], k)

    def test_render_error_is_fail_soft(self):
        data = _page_data(_prog())
        v = KP._xi1_view()
        with mock.patch.object(v, "progress_cell", side_effect=RuntimeError("boom")), \
                mock.patch.object(v, "company_section", side_effect=RuntimeError("boom")):
            html = KP.contracts_table(data["contracts"], data, tid="t")
            self.assertNotIn("진행(XI-1)", html)
            self.assertEqual(KP.xi1_company(data, ST), "")


class TestLoadXi1(unittest.TestCase):
    def test_missing_or_broken_is_none(self):
        import xi1_sector
        with mock.patch.object(xi1_sector, "load_progress", return_value=None):
            self.assertIsNone(KP.load_xi1(["013810"]))
        with mock.patch.object(xi1_sector, "load_progress", side_effect=ValueError("bad json")):
            self.assertIsNone(KP.load_xi1(["013810"]))

    def test_subset_to_screen_universe(self):
        import xi1_sector
        with mock.patch.object(xi1_sector, "load_progress", return_value=_prog()):
            prog = KP.load_xi1([ST])
        self.assertEqual(set(prog["companies"]), {ST})
        self.assertTrue(all(c["stock"] == ST for c in prog["contracts"]))
        with mock.patch.object(xi1_sector, "load_progress", return_value=_prog()):
            full = KP.load_xi1([ST, "000880"])
        self.assertEqual(set(full["companies"]), {ST, "000880"})

    def test_real_asset_loads(self):
        """커밋된 assets/xi1/progress.json — 있으면 화면 모집단(universe) 안의 회사만."""
        from kdef_universe import load as load_universe
        stocks = [r["stock"] for r in load_universe()]
        prog = KP.load_xi1(stocks)
        if prog is None:
            self.skipTest("progress.json 없음")
        for k in ("contracts", "companies", "sector", "periods", "by_rcp"):
            self.assertIn(k, prog)
        self.assertLessEqual(set(prog["companies"]), set(stocks))


if __name__ == "__main__":
    unittest.main()
