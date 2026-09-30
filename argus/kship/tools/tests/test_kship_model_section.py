#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""실적 모델 섹션 렌더러(kship_model_section) 계약 테스트.

실행: cd argus/kship/tools && python3 -m unittest tests.test_kship_model_section
픽스처: tests/fixtures/model_mock_010140.json(조선사·sls 있음) · model_mock_075580.json(기자재·풍력 모듈·종속사) —
스펙 2-5 스키마의 **모의** 모델이다. 실제 회사 수치가 아니며 렌더러 개발·검증에만 쓴다.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, TOOLS)

import kship_model_section as M                            # noqa: E402


def _fx(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


class TestRenderYard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = _fx("model_mock_010140.json")
        cls.sls = _fx("model_mock_sls_010140.json")
        cls.entry = {"stock": "010140", "name": "삼성중공업", "role": "yard"}
        cls.html = M.render_model_section(cls.entry, cls.model, fin=None,
                                          price={"close": 20100, "as_of": "20260928", "pe_ttm": 31.8, "pb": 3.76}, sls=cls.sls)

    def test_sections_and_wrapper(self):
        h = self.html
        self.assertIn('id="kship-model-010140"', h)
        self.assertEqual(h.count('<section class="card">'), 8)      # KPI·손익·사업부·선표·가정·밸류·파일·각주
        for title in ("실적 모델 KPI", "분기 손익", "사업부 매출·영업이익률", "선표 매출인식", "가정", "밸류에이션", "모델 파일", "각주"):
            self.assertIn("<h2>%s" % title, h)

    def test_tag_balance(self):
        self.assertEqual(M.check_tag_balance(self.html), [])

    def test_kpi_and_estimates_marked(self):
        h = self.html
        self.assertIn("FY2026E 매출", h)
        self.assertIn("FY2028E 매출", h)
        self.assertIn('title="추정 · segments_sum"', h)              # 추정 칸 basis 툴팁
        self.assertIn('title="실적 · fin.cons.is"', h)              # 실적 칸 출처
        self.assertGreaterEqual(h.count('class="est"'), 100)         # 10E 열 × 여러 행
        self.assertIn("2026Q2<br>A", h)
        self.assertIn("2026Q3<br>E", h)
        self.assertNotIn("2029Q1", h)                                # 10E 까지만

    def test_disclaimer_and_valuation(self):
        h = self.html
        self.assertIn(M.DISCLAIMER, h)
        self.assertIn("PER 밴드 lo/mid/hi", h)
        self.assertIn("PBR 기준 적정가치", h)
        self.assertIn('class="band"', h)

    def test_sls_charts_present_for_yard(self):
        h = self.html
        self.assertIn('id="kship-model-010140-sls"', h)
        self.assertIn('id="kship-model-010140-coh"', h)
        self.assertIn("⑤초호황", h)
        self.assertIn("화해 비율 0.82", h)

    def test_assumptions_panel(self):
        h = self.html
        self.assertIn("환율 원/달러 평균", h)
        self.assertIn("환헤지 비율 · 헤지환율", h)
        self.assertIn("법인세율", h)
        self.assertIn("판관비율", h)
        self.assertIn('<span class="pill est">가정</span>', h)
        self.assertIn("공사손실충당부채", h)                         # one_offs 노출

    def test_download_pending_when_no_xlsx(self):
        # assets 의 models/ 에 010140_model.xlsx 가 없는 개발 환경 기준 — 있으면 링크가 뜬다.
        if not os.path.isfile(os.path.join(M.XLSX_DIR, "010140_model.xlsx")):
            self.assertIn("010140_model.xlsx — 준비 중", self.html)
        else:
            self.assertIn('href="../models/010140_model.xlsx"', self.html)

    def test_no_global_collision_and_lazy_chart(self):
        h = self.html
        self.assertNotIn("const DATA", h)
        self.assertNotIn("SEGC", h)
        self.assertIn('"../vendor/chart.umd.min.js"', h)
        self.assertIn("if(window.Chart){go();}", h)
        self.assertNotIn("%%", h)                                    # % 포맷 잔재 없음

    def test_footnotes(self):
        h = self.html
        self.assertIn("aikstockdata.com", h)
        self.assertIn("ECB", h)
        self.assertIn("freeze 2025Q2", h)
        self.assertIn("매출 WAPE 6.8%", h)
        self.assertIn("모의 모델(L7 개발 픽스처)", h)                 # 한계에 모델 경고 노출

    def test_identity_conflict(self):
        with self.assertRaises(ValueError):
            M.render_model_section({"stock": "075580", "name": "x"}, self.model)
        with self.assertRaises(ValueError):
            M.render_model_section({"stock": "10140"}, self.model)
        other = dict(self.sls, stock="042660")
        with self.assertRaises(ValueError):
            M.render_model_section(self.entry, self.model, sls=other)


class TestRenderEquip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = _fx("model_mock_075580.json")
        cls.html = M.render_model_section({"stock": "075580", "name": "세진중공업", "role": "equip"}, cls.model)

    def test_no_sls_section_for_equip(self):
        self.assertEqual(self.html.count('<section class="card">'), 7)
        self.assertNotIn("선표 매출인식", self.html)

    def test_tag_balance(self):
        self.assertEqual(M.check_tag_balance(self.html), [])

    def test_consolidation_modules_drivers(self):
        h = self.html
        self.assertIn("일승(333430 55%)", h)
        self.assertIn("동방선기(099410 61%)", h)
        self.assertIn("separate_plus_subsidiaries", h)
        self.assertIn("회사 특유 모듈 · 풍력/플랜트", h)
        self.assertIn("customer_yard_revenue_weighted", h)
        self.assertIn("고객 비중 010620 50%, 329180 50%", h)
        self.assertIn("시차 1분기", h)

    def test_yard_without_sls_gets_placeholder(self):
        m = dict(self.model, role="yard")
        h = M.render_model_section({"stock": "075580", "name": "x", "role": "yard"}, m, sls=None)
        self.assertIn("선표 데이터(assets/sls/075580.json)가 아직 없습니다", h)
        self.assertEqual(M.check_tag_balance(h), [])


class TestFormatting(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(M.fmt_a(1234.56), "1,235")
        self.assertEqual(M.fmt_a(-1348.4), "-1,348")
        self.assertEqual(M.fmt_a(3.14), "3.1")
        self.assertEqual(M.fmt_a(-3.14), "-3.1")
        self.assertEqual(M.fmt_a(None), "—")
        self.assertEqual(M.fmt_a(float("nan")), "—")
        self.assertEqual(M.fmt_a(True), "—")
        self.assertEqual(M.fmt_won(-12345.6), "-12,346")
        self.assertEqual(M.fmt_pct(-0.0523), "-5.2%")
        self.assertEqual(M.fmt_x(12.34), "12.3배")
        self.assertEqual(M.fmt_x(None), "—")

    def test_negative_zero_is_zero(self):
        """반올림 잔재 -0.0 은 화면에 부호 없이 — 실제 페이지에서 '>-0.0<' 이 11장에 새던 결함."""
        self.assertEqual(M.fmt_a(-0.04), "0.0")
        self.assertEqual(M.fmt_a(-0.0), "0.0")
        self.assertEqual(M.fmt_won(-0.3), "0")
        self.assertEqual(M.fmt_pct(-0.0004), "0.0%")
        self.assertEqual(M.fmt_pct100(-0.02), "0.0%")
        self.assertEqual(M.fmt_x(-0.01), "0.0배")
        self.assertEqual(M.fmt_rate(-0.04), "0.0")
        self.assertEqual(M.fmt_a(-0.06), "-0.1")                       # 진짜 음수는 그대로

    def test_driver_label(self):
        self.assertEqual(M.driver_label("trend_seasonal"), "추세+계절성 폴백")
        self.assertEqual(M.driver_label("customer_yard_revenue_weighted"), "고객 조선사 매출 연동")
        self.assertEqual(M.driver_label("something_new"), "something_new")
        self.assertEqual(M.driver_label(None), "—")


class TestRenderEquipNoSegments(unittest.TestCase):
    """기자재 대부분: segments=[] + 최상위 driver_type(L4 실물 스키마). 드라이버 표기와 폴백 차트가 있어야 한다."""
    @classmethod
    def setUpClass(cls):
        m = _fx("model_mock_075580.json")
        m["segments"] = []
        m["driver_type"] = "trend_seasonal"
        rev = next(r for r in m["rows"] if r["key"] == "매출액")
        for q, c in rev["q"].items():
            if c.get("kind") == "estimate":
                c["basis"] = "전년동기 × (1+10.0%) — g=최근 4분기 합 YoY 클립, 연차별 절반 감쇠(가정)"
        m["consolidation"] = {"method": "separate_plus_subsidiaries_plus_residual",
                              "subsidiaries": [{"stock": "333430", "name": "일승", "stake": None},
                                               {"stock": None, "name": "세진베트남(비상장)", "stake": None, "note": "미공시 → 연결조정 잔차"}]}
        cls.html = M.render_model_section({"stock": "075580", "name": "세진중공업", "role": "equip"}, m)

    def test_driver_visible_everywhere(self):
        h = self.html
        self.assertIn('data-model-driver="trend_seasonal"', h)
        self.assertIn("드라이버 추세+계절성 폴백", h)                        # 섹션 머리
        self.assertIn(">추세+계절성 폴백<span class=\"pill est\">가정</span>", h)   # 가정 패널 항목
        self.assertIn("<b>매출 드라이버</b> — 추세+계절성 폴백 · 전년동기 × (1+10.0%)", h)  # 차트 각주
        self.assertEqual(h.count("추세+계절성 폴백"), 4)

    def test_fallback_chart_when_no_segments(self):
        h = self.html
        self.assertIn('id="kship-model-075580-seg"', h)
        self.assertIn("부문 분리 없음(연결 한 계열)", h)
        self.assertIn(M.json_for_html("연결 매출"), h)                    # 임베드 JSON 과 같은 직렬화로 찾는다
        self.assertIn("maintainAspectRatio:false", h)                    # .chart 컨테이너(고정 높이)를 넘치지 않게
        self.assertIn('<div class="chart tall"><canvas id="kship-model-075580-seg">', h)
        self.assertEqual(h.count('<section class="card">'), 7)
        self.assertEqual(M.check_tag_balance(h), [])

    def test_subsidiary_without_stock_has_no_empty_parens(self):
        h = self.html
        self.assertNotIn("()", h[h.index("연결 방식"):h.index("연결 방식") + 600])
        self.assertIn("일승(333430)", h)
        self.assertIn("세진베트남(비상장) — 미공시 → 연결조정 잔차", h)


class TestSummaryAndHook(unittest.TestCase):
    def test_model_summary(self):
        s = M.model_summary(_fx("model_mock_010140.json"))
        self.assertEqual(s["status"], "full")
        self.assertIsNotNone(s["fy"]["2026"]["rev"])
        self.assertAlmostEqual(s["fy"]["2027"]["opm"], s["fy"]["2027"]["op"] / s["fy"]["2027"]["rev"])
        self.assertEqual(s["per_now"], 29.17)

    def test_section_for_stock_empty_without_model(self):
        tmp = tempfile.mkdtemp(prefix="kmodel_")
        try:
            old = M.MODELS_DIR
            M.MODELS_DIR = tmp
            self.assertEqual(M.section_for_stock("010140"), "")
            shutil.copy(os.path.join(FIX, "model_mock_010140.json"), os.path.join(tmp, "010140.json"))
            h = M.section_for_stock("010140")
            self.assertIn('id="kship-model-010140"', h)
            self.assertEqual(M.check_tag_balance(h), [])
        finally:
            M.MODELS_DIR = old
            shutil.rmtree(tmp, ignore_errors=True)

    def test_window_quarters(self):
        act, est = M.window_quarters(_fx("model_mock_075580.json"))
        self.assertEqual((act[0], act[-1]), ("2024Q3", "2026Q2"))
        self.assertEqual((est[0], est[-1], len(est)), ("2026Q3", "2028Q4", 10))

    def test_tag_balance_detects_breakage(self):
        self.assertTrue(M.check_tag_balance("<div><section><p>x</div>"))
        self.assertTrue(M.check_tag_balance("</div>"))
        self.assertEqual(M.check_tag_balance("<div><br><input><p>a</p></div>"), [])


class TestHub(unittest.TestCase):
    def test_build_models_hub_with_mocks(self):
        tmp = tempfile.mkdtemp(prefix="kmodels_")
        try:
            shutil.copy(os.path.join(FIX, "model_mock_010140.json"), os.path.join(tmp, "010140.json"))
            shutil.copy(os.path.join(FIX, "model_mock_075580.json"), os.path.join(tmp, "075580.json"))
            h = M.build_models_hub(tmp, write=False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        pop = M.population()
        self.assertGreaterEqual(len(pop), 41)
        self.assertEqual(h.count("<tr>") - 1, len(pop))                  # 머리 1행 + 회사 행
        # 머리글 1행·th 수 == 본문 셀 수 — 공용 TABLE_JS 가 th 평면 순번으로 정렬하므로 이게 어긋나면 정렬 열이 틀린다
        thead = h[h.index("<thead>"):h.index("</thead>")]
        self.assertEqual(thead.count("<tr>"), 1)
        self.assertNotIn("rowspan", thead)
        self.assertNotIn("colspan", thead)
        n_th = len(re.findall(r"<th[\s>]", thead))                      # '<thead>' 는 세지 않는다
        first_tr = h[h.index("<tbody>"):]
        first_tr = first_tr[first_tr.index("<tr>"):first_tr.index("</tr>")]
        self.assertEqual(first_tr.count("<td"), n_th)
        self.assertIn("<th class=\"l\">드라이버</th>", thead)
        self.assertIn("FY26E<br>매출(억)", thead)
        self.assertIn(">고객 조선사 매출 연동<", h)                       # 075580 mock 의 드라이버 한글 표기
        self.assertIn("삼성중공업", h)
        self.assertIn("세진중공업", h)
        self.assertIn('href="010140/index.html#kship-model-010140"', h)
        self.assertIn(">모델 없음<", h)
        self.assertIn('data-sortable', h)
        self.assertIn('data-filter="#mtab"', h)
        self.assertIn("실적 모델</span>", h)                              # crumbs 끝
        self.assertIn('href="index.html">한국조선</a>', h)
        self.assertIn(M.DISCLAIMER, h)
        self.assertEqual(M.check_tag_balance(h), [])

    def test_hub_anchor_only_when_page_has_section(self):
        """회사 페이지에 섹션(id=kship-model-<stock>)이 없으면 앵커 없이 링크하고 '섹션 없음' 을 표시한다."""
        tmp = tempfile.mkdtemp(prefix="kmodels_")
        try:
            shutil.copy(os.path.join(FIX, "model_mock_010140.json"), os.path.join(tmp, "010140.json"))
            m = _fx("model_mock_075580.json")
            nosec = next((r["stock"] for r in M.population() if r.get("has_page") and not M._page_has_section(r["stock"])), None)
            if nosec is None:
                self.skipTest("섹션 없는 회사 페이지가 없음")
            m["stock"] = nosec
            with open(os.path.join(tmp, "%s.json" % nosec), "w", encoding="utf-8") as f:
                json.dump(m, f, ensure_ascii=False)
            h = M.build_models_hub(tmp, write=False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertIn('href="%s/index.html">' % nosec, h)
        self.assertNotIn('href="%s/index.html#kship-model-%s"' % (nosec, nosec), h)
        self.assertIn(">섹션 없음</span>", h)
        if M._page_has_section("010140"):
            self.assertIn('href="010140/index.html#kship-model-010140"', h)

    def test_render_check_output_is_not_a_company_page(self):
        """--render 확인 출력(제목 '실적 모델(렌더 확인)')이 회사 폴더에 놓여도 모집단의 has_page 로 치지 않고, --out 이 그 자리면 거부한다."""
        tmp = tempfile.mkdtemp(prefix="kpage_")
        try:
            p = os.path.join(tmp, "index.html")
            with open(p, "w", encoding="utf-8") as f:
                f.write("<!doctype html><html><head><title>X %s</title></head><body></body></html>" % M.RENDER_CHECK_MARK)
            self.assertFalse(M._is_company_page(p))
            with open(p, "w", encoding="utf-8") as f:
                f.write("<!doctype html><html><head><title>한일철강 — 조선기자재</title></head><body><h1>한일철강</h1></body></html>")
            self.assertTrue(M._is_company_page(p))
            self.assertFalse(M._is_company_page(os.path.join(tmp, "none.html")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertTrue(M._is_company_folder_target(os.path.join(M.KSHIP, "009540", "index.html")))
        self.assertTrue(M._is_company_folder_target(os.path.join(TOOLS, "..", "010140", "index.html")))
        self.assertFalse(M._is_company_folder_target("/tmp/009540_check.html"))
        self.assertFalse(M._is_company_folder_target(os.path.join(M.KSHIP, "models.html")))
        # 실제 레포에 렌더 확인 출력이 회사 폴더로 남아 있으면 모집단이 페이지로 세지 않아야 한다
        for r in M.population():
            if r.get("has_page"):
                self.assertTrue(M._is_company_page(os.path.join(M.KSHIP, r["stock"], "index.html")), r["stock"])

    def test_population_union(self):
        pop = M.population()
        stocks = {r["stock"] for r in pop}
        self.assertIn("010140", stocks)
        self.assertIn("075580", stocks)
        self.assertIn("009540", stocks)                                   # 지주(폴더 없음)도 모집단
        self.assertTrue(all(r.get("name") for r in pop))


if __name__ == "__main__":
    unittest.main()
