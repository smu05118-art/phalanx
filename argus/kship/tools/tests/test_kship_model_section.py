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
        self.assertFalse(M._is_company_folder_target(os.path.join(tempfile.gettempdir(), "009540_check.html")))
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


# ── 라운드 3(MODEL_SPEC §5-5) — 신규수주 행·시나리오·코호트 모드·잔고 캡·영업외 세부·OOS 라벨 ──────────────

def _yard_r3(model, sls):
    """모의 픽스처(파일은 그대로)에 R2·R3 실물 산출과 같은 키를 메모리에서 얹는다: 매출조선신규/OP조선신규 행, scenarios 블록,
    new_orders_included, driver 의 sls_cohort_mode·backlog_cap_applied, sls 의 cohort_mode(_alt)·backlog_cap·target_opm_alt·by_cohort_alt,
    영업외 세부 행(환관련손익 전부 0 → 숨김, 지분법손익 값 있음 → 표시)."""
    m, s = json.loads(json.dumps(model)), json.loads(json.dumps(sls))
    qs = m["periods"]["quarters"]
    est = [q for q in qs if q > m["periods"]["last_actual"]]

    def row(key, label, per_q):
        return {"key": key, "label": label, "group": "사업부", "unit": "억원",
                "q": {q: ({"v": per_q * (est.index(q) + 1), "kind": "estimate", "basis": "forecast_panel.json.gz scenarios.base new_order_revenue — 매출조선에 포함(합산 금지)"}
                          if q in est else {"v": 0.0, "kind": "actual", "src": "origin 이전 실적 분기 — 정의상 0"})
                      for q in qs},
                "a": {"2026": {"v": per_q, "kind": "mixed"}, "2027": {"v": per_q * 20, "kind": "estimate"}, "2028": {"v": per_q * 80, "kind": "estimate"}}}
    m["rows"] += [row("매출조선신규", "매출 조선·해양 신규수주(forecast_panel base — 매출조선에 포함)", 100.0),
                  row("OP조선신규", "OP 조선·해양 신규수주(매출조선신규 × OPM — OP조선에 포함)", 10.0),
                  {"key": "환관련손익", "label": "환관련손익(모델 추정분)", "group": "손익", "unit": "억원", "a": {},
                   "q": {q: {"v": -0.0, "kind": "estimate", "basis": "외화 순노출 × Δ기말환율"} for q in est}},
                  {"key": "지분법손익", "label": "지분법손익", "group": "손익", "unit": "억원", "a": {},
                   "q": {q: {"v": 1.5, "kind": "actual", "src": "fin.cons.is.종속기업,공동지배기업및관계기업관련손익"} for q in qs if q not in est}}]
    m["new_orders_included"] = True
    m["new_orders"] = {"source": "forecast_panel.json.gz", "scenario_in_rows": "base", "scenarios": ["conservative", "base", "optimistic"],
                       "calibrated": False, "panel_status": "partial", "panel_reason_codes": ["book_value_only"], "base_total_fq": 10100.0}

    def case(in_rows, k):
        return {"in_rows": in_rows, "quarterly": {},
                "annual": {y: {"rev": 90000.0 * g + 10000.0 * k * (i + 1), "op": 9000.0 * g + 1000.0 * k * (i + 1),
                               "new_order_revenue": 10000.0 * k * (i + 1), "kind": "mixed" if y == "2026" else "estimate"}
                           for i, (y, g) in enumerate((("2026", 1.0), ("2027", 1.1), ("2028", 1.2)))}}
    m["scenarios"] = {"meta": {"cases": ["existing_only", "conservative", "base", "optimistic"], "fiscal_years": ["2026", "2027", "2028"],
                               "in_rows": "base", "calibrated": False, "panel_status": "partial", "panel_reason_codes": ["book_value_only"],
                               "source": "forecast_panel.json.gz scenarios.*.quarterly[].new_order_revenue",
                               "existing_revenue": "SLS 해양 원화 + 원장 밖 잔고 소진 + 기타 부문", "note": "base 는 행과 동일 · 보수/낙관 합산 안 함"},
                      "existing_only": case(False, 0), "conservative": case(False, 1), "base": case(True, 2), "optimistic": case(False, 3)}
    m["segments"][0]["driver"].update({"new_orders_included": True, "sls_cohort_mode": "reference_anchor", "backlog_cap_applied": True,
                                       "target_opm_alt_median": 0.062, "calibrated_shift": -0.05})
    s.update({"cohort_mode": "reference_anchor", "cohort_mode_alt": "ledger_relative", "backlog_cap_applied": True,
              "backlog_cap": {"applied": True, "kind": "estimate", "factor": 0.859276, "coverage_at_origin": 1.1638},
              "calibration": {"calibrated_shift": -0.0526, "mode": "reference_anchor"},
              "calibration_alt": {"calibrated_shift": 0.0359, "mode": "ledger_relative"},
              "target_opm_alt": {q: {"opm": 0.06, "mode": "ledger_relative"} for q in s["target_opm"]}})
    for b in s["by_quarter"].values():
        b["by_cohort_alt"] = {"③중마진": 300.0, "④호황": 100.0}
    return m, s


class TestRenderYardRound3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model, cls.sls = _yard_r3(_fx("model_mock_010140.json"), _fx("model_mock_sls_010140.json"))
        cls.entry = {"stock": "010140", "name": "삼성중공업", "role": "yard"}
        cls.html = M.render_model_section(cls.entry, cls.model, sls=cls.sls)

    def test_scenario_card_added_as_ninth_section(self):
        h = self.html
        self.assertEqual(h.count('<section class="card">'), 9)
        self.assertEqual(M.check_tag_balance(h), [])
        self.assertIn("<h2>신규수주 시나리오", h)
        self.assertIn('<canvas id="kship-model-010140-scn">', h)
        self.assertIn("FY2028E 매출 보수 138,000 ~ 낙관 198,000억", h)           # conservative 108000+30000 · optimistic 108000+90000
        self.assertIn('<tr class="base"><th class="rowh" scope="row">기준(base)<span class="pill">손익표 반영</span></th>', h)
        for name in ("기존 잔고만", "보수", "낙관"):
            self.assertIn('<th class="rowh" scope="row">%s</th>' % name, h)
        self.assertIn("FY28E<br>신규 매출(억)", h)
        self.assertIn("기준(base)만 손익표 행에 반영 · 보수/낙관은 합산 안 함", h)
        self.assertIn("calibrated=false — 장부가 대용치(book-value proxy), 보정된 수주 예측이 아님", h)
        # 시나리오 카드는 선표 카드 뒤·가정 패널 앞
        self.assertLess(h.index("<h2>선표 매출인식"), h.index("<h2>신규수주 시나리오"))
        self.assertLess(h.index("<h2>신규수주 시나리오"), h.index("<h2>가정 "))

    def test_new_orders_label_everywhere(self):
        h = self.html
        self.assertIn('data-model-new-orders="included"', h)
        self.assertGreaterEqual(h.count(M.NEW_ORDERS_LABEL), 3)                 # 섹션 머리 · KPI · 시나리오 카드
        self.assertIn('<span class="tag" title="행 반영 base · 패널 status partial · book_value_only · FY합 10,100억 · calibrated=false">%s</span>' % M.NEW_ORDERS_LABEL, h)
        self.assertIn("<b>포함(base)<span class=\"pill est\">가정</span></b><span>신규수주(origin 이후 수주분)</span>", h)
        self.assertIn("<li>신규수주: %s — 행 반영 base" % M.NEW_ORDERS_LABEL, h)

    def test_new_order_rows_are_indented_sub_rows(self):
        h = self.html
        self.assertIn('<tr class="sub"><th class="rowh" scope="row" title="매출 조선·해양 신규수주(forecast_panel base — 매출조선에 포함)">'
                      '└ 신규수주 매출(forecast_panel base · 매출조선에 포함)</th>', h)
        self.assertIn("└ 신규수주 OP(매출조선신규 × 타겟 OPM · OP조선에 포함)", h)
        self.assertIn('title="추정 · forecast_panel.json.gz scenarios.base new_order_revenue — 매출조선에 포함(합산 금지)">900</td>', h)

    def test_nonop_detail_rows_only_when_valued(self):
        h = self.html
        self.assertNotIn("환관련손익(모델 추정분)", h)                                # 전부 0 → 숨김
        self.assertIn('<tr class="sub"><th class="rowh" scope="row">지분법손익</th>', h)   # 값 있음 → 들여쓴 하위 행
        self.assertLess(h.index('scope="row">금융손익'), h.index('scope="row">지분법손익</th>'))
        self.assertLess(h.index('scope="row">지분법손익</th>'), h.index('scope="row">법인세비용차감전이익'))   # 세전이익 앞에 온다

    def test_cohort_mode_and_backlog_cap_shown(self):
        h = self.html
        self.assertIn('data-model-cohort-mode="reference_anchor"', h)
        self.assertIn('data-model-backlog-cap="applied"', h)
        self.assertIn("<b>코호트 모드</b> reference_anchor(레퍼런스 앵커(수주연도→등급)) 기본 · 대안 ledger_relative(원장 상대등급) 타겟 OPM 중위 6.2%"
                      " · 캘리브레이션 shift 기본 -5.3%p / 대안 +3.6%p.", h)
        self.assertIn("<b>선표 잔고 캡</b> 적용 ×0.859(원장 잔여/공시 해양 잔고 1.16 → 1.00 · 원값 *_raw 보존).", h)
        self.assertIn("→ 타겟 OPM · 코호트 모드 reference_anchor</em>", h)
        self.assertIn("<span>코호트 모드(타겟 OPM 판정)</span>", h)
        self.assertIn("<b>적용<span class=\"pill est\">가정</span></b><span>선표 잔고 캡</span>", h)
        self.assertIn(M.json_for_html("타겟 OPM 대안 ledger_relative(%)"), h)      # 대안 모드 선 라벨(임베드 JSON)
        self.assertIn('"opm_alt":[6.0', h)
        self.assertIn("③중마진 75% · ④호황 25%", h)                                   # 툴팁용 대안 비중 문장
        self.assertIn("화해 비율 0.82", h)                                            # 기존 문장 유지

    def test_excluded_yard_gets_off_tag_and_no_scenario_card(self):
        m = json.loads(json.dumps(self.model))
        m["new_orders_included"] = False
        m["new_orders"] = {"source": "forecast_panel.json.gz", "panel_status": "partial", "note": "new_order_revenue 전부 None → 미포함"}
        m.pop("scenarios")
        m["rows"] = [r for r in m["rows"] if r["key"] not in ("매출조선신규", "OP조선신규")]
        h = M.render_model_section(self.entry, m, sls=self.sls)
        self.assertEqual(h.count('<section class="card">'), 8)
        self.assertEqual(M.check_tag_balance(h), [])
        self.assertIn('data-model-new-orders="excluded"', h)
        self.assertIn('<span class="tag off" title="new_order_revenue 전부 None → 미포함">%s</span>' % M.NEW_ORDERS_EXCL_LABEL, h)
        self.assertNotIn("신규수주 시나리오", h)
        self.assertNotIn(M.NEW_ORDERS_LABEL, h)
        self.assertIn("<b>미포함<span class=\"pill est\">가정</span></b><span>신규수주(origin 이후 수주분)</span>", h)

    def test_scenario_card_absent_without_block_and_equip_has_no_label(self):
        self.assertEqual(M._scenario_card(_fx("model_mock_010140.json"), "x", 1), "")
        h = M.render_model_section({"stock": "075580", "name": "세진중공업", "role": "equip"}, _fx("model_mock_075580.json"))
        self.assertIn('data-model-new-orders="n/a"', h)
        self.assertNotIn('class="tag', h)
        self.assertNotIn("신규수주(origin 이후 수주분)", h)

    def test_model_summary_round3_keys(self):
        s = M.model_summary(self.model)
        self.assertEqual(s["new_orders"], "included")
        self.assertEqual(s["scn"]["2028"], {"cons": 138000.0, "opt": 198000.0})
        self.assertEqual(M.model_summary(_fx("model_mock_075580.json"))["new_orders"], "n/a")
        self.assertEqual(M.model_summary(_fx("model_mock_075580.json"))["scn"], {})

class TestRenderFallbackNewOrders(unittest.TestCase):
    """한화오션·HJ — 패널이 전범위 new_order_revenue 를 비워 covered_scope_new_revenue 로 폴백한 모델: 라벨·허브 칸에 폴백·저신뢰가 보이고 일반 라벨은 안 나온다."""

    NOTE = "폴백(저신뢰): 패널이 전범위 new_order_revenue 를 비웠다 → 모델 대상 부문 상선·기타만 덮는다 — 신규 매출 과소 가능 — 낙관 시나리오가 더 가깝다"

    @classmethod
    def setUpClass(cls):
        cls.model, cls.sls = _yard_r3(_fx("model_mock_010140.json"), _fx("model_mock_sls_010140.json"))
        no = cls.model["new_orders"]
        no.update({"source_field": "covered_scope_new_revenue", "fallback": True, "confidence": "low", "fallback_note": cls.NOTE})
        cls.entry = {"stock": "010140", "name": "삼성중공업", "role": "yard"}
        cls.html = M.render_model_section(cls.entry, cls.model, sls=cls.sls)

    def test_state_and_label(self):
        st, lab, det = M.new_orders_state(self.model)
        self.assertEqual((st, lab), ("included", M.NEW_ORDERS_FALLBACK_LABEL))
        self.assertNotEqual(M.NEW_ORDERS_FALLBACK_LABEL, M.NEW_ORDERS_LABEL)
        self.assertIn("저신뢰", M.NEW_ORDERS_FALLBACK_LABEL)
        self.assertIn("폴백 covered_scope_new_revenue(전범위 new_order_revenue 없음)", det)
        self.assertIn(self.NOTE, det)
        self.assertIn("calibrated=false", det)
        plain = json.loads(json.dumps(self.model))
        plain["new_orders"].update({"fallback": False})
        self.assertEqual(M.new_orders_state(plain)[:2], ("included", M.NEW_ORDERS_LABEL))             # 전범위 필드면 일반 라벨
        self.assertNotIn("폴백", M.new_orders_state(plain)[2])

    def test_rendered_labels(self):
        h = self.html
        self.assertEqual(M.check_tag_balance(h), [])
        self.assertGreaterEqual(h.count(M.NEW_ORDERS_FALLBACK_LABEL), 3)                              # 섹션 머리 · KPI · 시나리오 카드
        self.assertNotIn(M.NEW_ORDERS_LABEL, h)
        self.assertIn(self.NOTE.split(" — ")[0], h)

    def test_hub_cell_shows_fallback(self):
        yard = self.model
        tmp = tempfile.mkdtemp(prefix="kmodels_")
        try:
            with open(os.path.join(tmp, "010140.json"), "w", encoding="utf-8") as f:
                json.dump(yard, f, ensure_ascii=False)
            h = M.build_models_hub(tmp, write=False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        tr = next(r for r in re.findall(r"<tr>(.*?)</tr>", h[h.index("<tbody>"):h.index("</tbody>")], re.S) if "010140" in r)
        self.assertIn('<b class="wn">포함</b><span class="mut"> 폴백</span>', tr)
        self.assertIn(M.NEW_ORDERS_FALLBACK_LABEL, tr)
        self.assertEqual(M.check_tag_balance(h), [])


class TestOOSLabel(unittest.TestCase):
    """드라이버 라벨의 OOS 선택 결과(결정 ⓘ): `WAPE 연동 x% vs 추세 y%` + 채택/폴백."""
    OOS = {"freeze": "2025Q2", "horizon": 4, "n": 4, "wape_link": 12.0, "wape_trend": 12.3, "adopted": True,
           "rule": "동결 2025Q2 이후 4분기 매출 WAPE: 연동 ≤ 추세 × 1.10 이면 채택, 아니면 추세+계절성 폴백"}

    def _equip(self, adopted):
        m = _fx("model_mock_075580.json")
        m["segments"][0]["driver"]["selection_oos"] = dict(self.OOS, adopted=adopted, wape_link=12.0 if adopted else 32.2, wape_trend=12.3 if adopted else 3.6)
        if not adopted:
            m["driver_type"] = "trend_seasonal"
            m["segments"][0]["driver"]["type"] = "trend_seasonal"
        return m

    def test_text_helpers(self):
        self.assertEqual(M.oos_text({}), "")
        self.assertEqual(M.oos_text({"selection_oos": {"adopted": True}}), "")                       # WAPE 도 note 도 없으면 표기 없음
        self.assertEqual(M.oos_text({"selection_oos": {"adopted": True, "wape_link": None, "wape_trend": None,
                                                       "note": "동결 2025Q2 이전 실적 7분기 → OOS 비교 불가, 유의성 조건만으로 채택"}}, short=True),
                         "OOS 비교 불가 — 동결 2025Q2 이전 실적 7분기 → OOS 비교 불가, 유의성 조건만으로 채택")     # WAPE 미산출은 빈 판정 대신 note
        self.assertEqual(M.oos_text({"selection_oos": self.OOS}, short=True), "WAPE 연동 12.0% vs 추세 12.3% → 연동 채택")
        self.assertEqual(M.oos_text({"selection_oos": dict(self.OOS, adopted=False, wape_link=32.2, wape_trend=3.6)}),
                         "OOS 동결 2025Q2 · 4분기 · WAPE 연동 32.2% vs 추세 3.6% → 추세 폴백(연동 미채택)")
        self.assertEqual(M.model_oos(_fx("model_mock_075580.json")), "")

    def test_adopted_shown_in_header_chart_panel_footnote(self):
        h = M.render_model_section({"stock": "075580", "name": "세진중공업", "role": "equip"}, self._equip(True))
        self.assertIn("드라이버 고객 조선사 매출 연동 (WAPE 연동 12.0% vs 추세 12.3% → 연동 채택) · ", h)          # 섹션 머리
        self.assertIn("<b>매출 드라이버</b> — 고객 조선사 매출 연동 · OOS 동결 2025Q2 · 4분기 · WAPE 연동 12.0% vs 추세 12.3% → 연동 채택", h)
        self.assertIn(" · OOS WAPE 연동 12.0% vs 추세 12.3% → 연동 채택", h)                                    # 부문 드라이버 줄
        self.assertIn("<li>드라이버 선택(OOS): OOS 동결 2025Q2 · 4분기 · WAPE 연동 12.0% vs 추세 12.3% → 연동 채택 — 동결 2025Q2 이후", h)
        self.assertEqual(M.check_tag_balance(h), [])

    def test_rejected_shows_fallback(self):
        h = M.render_model_section({"stock": "075580", "name": "세진중공업", "role": "equip"}, self._equip(False))
        self.assertIn("드라이버 추세+계절성 폴백 (WAPE 연동 32.2% vs 추세 3.6% → 추세 폴백(연동 미채택))", h)
        self.assertIn('data-model-driver="trend_seasonal"', h)


class TestHubRound3(unittest.TestCase):
    def test_hub_new_orders_column_and_oos(self):
        yard, _ = _yard_r3(_fx("model_mock_010140.json"), _fx("model_mock_sls_010140.json"))
        equip = _fx("model_mock_075580.json")
        equip["segments"][0]["driver"]["selection_oos"] = TestOOSLabel.OOS
        tmp = tempfile.mkdtemp(prefix="kmodels_")
        try:
            for m in (yard, equip):
                with open(os.path.join(tmp, "%s.json" % m["stock"]), "w", encoding="utf-8") as f:
                    json.dump(m, f, ensure_ascii=False)
            h = M.build_models_hub(tmp, write=False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(M.check_tag_balance(h), [])
        thead = h[h.index("<thead>"):h.index("</thead>")]
        n_th = len(re.findall(r"<th[\s>]", thead))
        self.assertIn('<th class="l">신규<br>수주</th>', thead)
        rows = re.findall(r"<tr>(.*?)</tr>", h[h.index("<tbody>"):h.index("</tbody>")], re.S)
        self.assertGreaterEqual(len(rows), 41)
        for r in rows:                                                          # 모델 있음·없음 행 모두 열 수가 머리글과 같다
            self.assertEqual(len(re.findall(r"<td[\s>]", r)), n_th, r[:120])
        yard_tr = next(r for r in rows if "010140" in r)
        self.assertIn('<td class="l" data-v="2" title="%s · 행 반영 base' % M.NEW_ORDERS_LABEL, yard_tr)
        self.assertIn('<b class="wn">포함</b>', yard_tr)
        self.assertIn('title="신규수주 시나리오 보수 138,000 ~ 낙관 198,000억(base 는 표 값)"', yard_tr)
        equip_tr = next(r for r in rows if "075580" in r)
        self.assertIn('<td class="l" data-v="0"><span class="mut">—</span></td>', equip_tr)        # n/a 는 빈 title 속성을 만들지 않는다
        self.assertIn('>고객 조선사 매출 연동 <span class="mut">WAPE 연동 12.0% vs 추세 12.3% → 연동 채택</span></td>', equip_tr)
        self.assertIn("<b>1<small>/ 0</small></b><span>신규수주 포함 · 미포함", h)
        self.assertIn("신규수주 '포함' 행의 FY 매출은 forecast_panel base(미보정)를 품음", h)


class TestRealAssetsRound3(unittest.TestCase):
    """실제 R2·R3 산출(assets/models·assets/sls)이 있으면 렌더가 깨지지 않고 §5-5 요소가 보이는지 — 값은 검사하지 않는다(다른 레인 소유)."""
    def _render(self, stock):
        model = M.load_model(stock)
        if not model:
            self.skipTest("assets/models/%s.json 없음" % stock)
        sls = M._load_json(os.path.join(M.SLS_DIR, "%s.json" % stock))
        return model, M.render_model_section({"stock": stock, "name": model.get("name"), "role": model.get("role")}, model, sls=sls)

    def test_yard_real(self):
        model, h = self._render("010140")
        self.assertEqual(M.check_tag_balance(h), [])
        state = M.new_orders_state(model)[0]
        self.assertIn('data-model-new-orders="%s"' % state, h)
        if state == "included":
            self.assertIn("<h2>신규수주 시나리오", h)
            self.assertIn("└ 신규수주 매출(forecast_panel base · 매출조선에 포함)", h)
            self.assertIn(M.NEW_ORDERS_LABEL, h)
        if M.sls_mode_info(model, M._load_json(os.path.join(M.SLS_DIR, "010140.json"))).get("mode"):
            self.assertIn("<b>코호트 모드</b> ", h)
            self.assertIn("<b>선표 잔고 캡</b> ", h)

    def test_equip_real_oos(self):
        model, h = self._render("075580")
        self.assertEqual(M.check_tag_balance(h), [])
        if M.model_oos(model):
            self.assertIn("WAPE 연동 ", h)
            self.assertIn("<li>드라이버 선택(OOS): ", h)


# ── 5차(V7, T6 D7) — status/driver_fallback 분리 표기 · 상단 '모델 상태' 한 줄 · 허브 폴백 열·각주·모집단 외 · 모바일 CSS ─────────

def _rejected_oos():
    return {"rejected_by": "oos", "corr": 0.9111, "n": 8, "significance": {"r_crit_p05_two_sided": 0.7067},
            "selection_oos": {"freeze": "2025Q2", "n": 4, "wape_link": 17.6, "wape_trend": 12.3, "adopted": False}}


class TestDriverFallbackLabel(unittest.TestCase):
    """driver_fallback(corr|significance|n|oos|no_link|none)은 status 와 따로 — 섹션 머리·상태 줄·data 속성. 필드가 없으면 추정하지 않는다."""
    def _equip(self, code=None, rejected=None):
        m = _fx("model_mock_075580.json")
        if code is not None:
            m["driver_fallback"] = code
        if rejected is not None:
            m["segments"][0]["driver"]["customer_link_rejected"] = rejected
        return m

    def test_info_vocabulary(self):
        self.assertEqual(M.driver_fallback_info(self._equip()), (None, "", ""))                       # 필드 없음 → 표기 없음
        self.assertEqual(M.driver_fallback_info(self._equip("bogus")), (None, "", ""))                # 모르는 코드 → 표기 없음
        self.assertEqual(M.driver_fallback_info(self._equip("none"))[:2], ("none", "폴백 없음"))
        code, lab, det = M.driver_fallback_info(self._equip("oos", _rejected_oos()))
        self.assertEqual((code, lab), ("oos", "OOS 기각 → 추세 폴백"))
        for s in ("상관 0.91", "n=8", "WAPE 연동 17.6% vs 추세 12.3% → 추세 폴백(연동 미채택)", "× 1.10"):
            self.assertIn(s, det)
        code, lab, det = M.driver_fallback_info(self._equip("significance", {"rejected_by": "significance", "corr": 0.8748, "n": 5,
                                                                              "significance": {"r_crit_p05_two_sided": 0.8783}}))
        self.assertEqual(lab, "유의성 미달 → 추세 폴백")
        self.assertIn("상관 0.87 (임계 r 0.88) · n=5", det)
        # 최상위 필드가 없어도 customer_link_rejected.rejected_by 는 모델이 적은 명시적 증거 → 그걸로 판정
        self.assertEqual(M.driver_fallback_info(self._equip(None, {"rejected_by": "n", "n": 3}))[0], "n")
        code, lab, det = M.driver_fallback_info(self._equip("no_link"))
        self.assertEqual(lab, "고객 연결 없음 → 추세 폴백")
        self.assertIn("추세+계절성", det)
        self.assertEqual(list(M.DRIVER_FALLBACK_KO), ["none", "oos", "significance", "n", "corr", "no_link"])  # kship_model.DRIVER_FALLBACKS 와 같은 집합

    def test_header_status_line_and_attr(self):
        e = {"stock": "075580", "name": "세진중공업", "role": "equip"}
        h = M.render_model_section(e, self._equip("oos", _rejected_oos()))
        self.assertIn('data-model-driver-fallback="oos"', h)
        self.assertIn(" · 폴백 사유 oos(OOS 기각 → 추세 폴백) · ", h)                                      # 섹션 머리
        self.assertIn("드라이버 폴백 oos — OOS 기각 → 추세 폴백</span></p>", h)                              # 상태 줄
        self.assertIn('title="%s"' % M.E(M.driver_fallback_info(self._equip("oos", _rejected_oos()))[2]), h)  # 상세는 툴팁
        self.assertLess(h.index('<p class="status">'), h.index("<h2>실적 모델 KPI"))                       # KPI 바로 위
        self.assertGreater(h.index('<p class="status">'), h.index('<h2class="sec">'.replace("<h2c", "<h2 c")))
        self.assertEqual(M.check_tag_balance(h), [])
        h2 = M.render_model_section(e, self._equip("none"))
        self.assertIn(" · 폴백 없음 · ", h2)
        self.assertIn('data-model-driver-fallback="none"', h2)
        self.assertIn("드라이버 폴백 none — 폴백 없음", h2)
        h3 = M.render_model_section(e, self._equip())
        self.assertIn('data-model-driver-fallback=""', h3)
        self.assertNotIn("폴백 사유", h3)
        self.assertNotIn("드라이버 폴백 ", h3)


class TestStatusLine(unittest.TestCase):
    """상단 한 줄: full 은 데이터 완전 사실, partial 은 quality 로 되짚은 사유(못 되짚으면 '미기재' — 지어내지 않는다)."""
    def test_full_and_partial_reasons(self):
        m = _fx("model_mock_075580.json")
        m["status"] = "full"
        m["quality"] = dict(m.get("quality") or {}, status="full", fin_quarters=19, identities_ok=True, sep_filled=[], missing=[], warnings=[])
        h = M.status_line(m)
        self.assertIn('<b class="up" title="%s">모델 상태 완성(full)</b>' % M.E(M.STATUS_RULE), h)
        self.assertIn("데이터 완전 — fin 19분기 · 항등식 OK · 최신 분기 %s" % m["periods"]["last_actual"], h)
        self.assertEqual(M.status_reasons(m), [])
        m["status"] = "partial"
        m["quality"].update(status="partial", fin_quarters=5, sep_filled=["2022Q1", "2021Q4", "2022Q2"],
                            warnings=["마지막 fin 분기 2025Q3 < 최신 완결 분기 2026Q2 — 최신 보고서 미수집(no_report) 상태의 모델", "무관한 경고"])
        rs = M.status_reasons(m)
        self.assertEqual(rs[0], "fin 5분기(< 8)")
        self.assertIn("별도 보충 3분기(2021Q4~2022Q2)", rs)
        self.assertTrue(any("최신 완결 분기" in r for r in rs))
        self.assertFalse(any("무관한 경고" in r for r in rs))
        h = M.status_line(m)
        self.assertIn('<b class="wn" title=', h)
        self.assertIn("모델 상태 부분(partial)</b>사유: fin 5분기(&lt; 8) · 별도 보충 3분기(2021Q4~2022Q2) · 마지막 fin 분기 2025Q3 &lt; 최신 완결 분기", h)
        m["quality"].update(identities_ok=False, missing=["BPS", "EPS"])
        rs = M.status_reasons(m)
        self.assertIn("항등식 불일치", rs)
        self.assertIn("누락 2건: BPS, EPS", rs)
        # 추정 매출 분기가 10 미만이면 그것도 사유
        rev = next(r for r in m["rows"] if r["key"] == "매출액")
        for q in [q for q in m["periods"]["quarters"] if q > m["periods"]["last_actual"]][-3:]:
            rev["q"].pop(q, None)
        self.assertIn("추정 매출 7분기(< 10)", M.status_reasons(m))
        # 사유를 되짚을 수 없는 partial → '미기재'
        m2 = _fx("model_mock_075580.json")
        m2["status"] = "partial"
        m2["quality"] = dict(m2.get("quality") or {}, status="partial", fin_quarters=19, identities_ok=True, sep_filled=[], missing=[], warnings=[])
        self.assertEqual(M.status_reasons(m2), [])
        self.assertIn("모델 상태 부분(partial)</b>사유: 미기재 — quality.warnings 참조", M.status_line(m2))
        self.assertEqual(M.check_tag_balance(M.render_model_section({"stock": "075580", "name": "세진중공업", "role": "equip"}, m2)), [])


class TestHubV7(unittest.TestCase):
    def _hub(self, extra=None):
        yard, _ = _yard_r3(_fx("model_mock_010140.json"), _fx("model_mock_sls_010140.json"))
        yard["driver_fallback"] = "none"
        equip = _fx("model_mock_075580.json")
        equip["driver_fallback"] = "oos"
        equip["segments"][0]["driver"]["customer_link_rejected"] = _rejected_oos()
        equip["status"] = "partial"
        equip["quality"] = dict(equip.get("quality") or {}, status="partial", fin_quarters=5)
        tmp = tempfile.mkdtemp(prefix="kmodels_")
        try:
            for m in [yard, equip] + (extra or []):
                with open(os.path.join(tmp, "%s.json" % m["stock"]), "w", encoding="utf-8") as f:
                    json.dump(m, f, ensure_ascii=False)
            return M.build_models_hub(tmp, write=False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_fallback_column_status_title_footnote(self):
        h = self._hub()
        self.assertEqual(M.check_tag_balance(h), [])
        thead = h[h.index("<thead>"):h.index("</thead>")]
        self.assertIn('<th class="l">드라이버</th><th class="l">폴백<br>사유</th><th class="l">신규<br>수주</th>', thead)
        n_th = len(re.findall(r"<th[\s>]", thead))
        rows = re.findall(r"<tr>(.*?)</tr>", h[h.index("<tbody>"):h.index("</tbody>")], re.S)
        self.assertEqual(len(rows), len(M.population()))
        for r in rows:                                                          # 모델 있음·없음 행 모두 열 수 == 머리글 th 수
            self.assertEqual(len(re.findall(r"<td[\s>]", r)), n_th, r[:120])
        yard_tr = next(r for r in rows if "010140" in r)
        equip_tr = next(r for r in rows if "075580" in r)
        self.assertIn('<td class="l" data-v="none" title="%s"><span class="mut">none · 폴백 없음</span></td>' % M.E(M.DRIVER_FALLBACK_DESC["none"]), yard_tr)
        self.assertIn('<td class="l" data-v="oos" title="', equip_tr)
        self.assertIn('<b class="wn">oos</b> · OOS 기각 → 추세 폴백</td>', equip_tr)
        self.assertIn("WAPE 연동 17.6% vs 추세 12.3%", equip_tr)                                       # 툴팁에 수치
        self.assertIn('<b class="wn" title="%s — 사유: fin 5분기(&lt; 8)">부분</b>' % M.E(M.STATUS_RULE), equip_tr)   # 상태 칸 툴팁에 사유
        self.assertIn('<b class="up" title="%s">완성</b>' % M.E(M.STATUS_RULE), yard_tr)
        none_tr = next(r for r in rows if "모델 없음" in r)
        self.assertIn('<td class="mut">—</td>' * (n_th - 5), none_tr)
        self.assertIn("<b>1<small>/ 1</small></b><span>드라이버 폴백 없음(none) · 폴백 — oos 1</span>", h)   # KPI 타일
        self.assertIn("status 는 데이터 완전성(T6 D7)", h)
        self.assertIn("<h2>각주 <em>마지막 갱신 · 출처 · 단위 · 면책 — 고정</em></h2>", h)
        self.assertIn("<li>마지막 갱신: 모델 생성 %s(summary.json built_at — · 기준 분기 —)" % M.E(str(_fx("model_mock_010140.json")["built_at"])), h)   # 임시 디렉터리엔 summary 없음 → —
        self.assertIn("시계를 읽지 않는다", h)
        self.assertIn("<li>출처: 재무 DART 정기보고서", h)
        self.assertIn("이 표는 억원(백만원÷100)", h)
        self.assertIn("none=폴백 없음 · oos=OOS 기각 → 추세 폴백", h)
        self.assertIn("<li><b>%s</b> — 컨센서스·목표주가가 아니며" % M.DISCLAIMER, h)
        self.assertLess(h.index('<div class="note info">'), h.index("<h2>각주 <em>마지막 갱신"))      # 각주는 표·안내 뒤, 스크립트 앞
        self.assertLess(h.index("<h2>각주 <em>마지막 갱신"), h.index("<script>"))
        self.assertNotIn('title=""', h)

    def test_model_outside_population_listed(self):
        m = _fx("model_mock_075580.json")
        m["stock"], m["name"], m["driver_fallback"] = "999999", "모집단외테스트", "no_link"
        h = self._hub([m])
        rows = re.findall(r"<tr>(.*?)</tr>", h[h.index("<tbody>"):h.index("</tbody>")], re.S)
        self.assertEqual(len(rows), len(M.population()) + 1)
        tr = next((r for r in rows if "999999" in r), None)
        self.assertIsNotNone(tr)
        self.assertTrue(tr.startswith('<td class="l">모집단외테스트 <span class="mut" title="'), tr[:120])
        self.assertIn(">모집단 외</span></td>", tr)
        self.assertNotIn('href="999999/index.html', tr)                                              # 회사 페이지 없음 → 링크 없음
        self.assertIn('data-v="no_link"', tr)
        self.assertIn("(모집단 외 1 포함 — 피합병 참고용)", h)
        self.assertIn("<title>한국조선 실적 모델 — %d사 FY2026E~28E</title>" % (len(M.population()) + 1), h)
        self.assertEqual(M.check_tag_balance(h), [])

    def test_peek_and_dir_helpers(self):
        tmp = tempfile.mkdtemp(prefix="kpeek_")
        try:
            with open(os.path.join(tmp, "010140.json"), "w", encoding="utf-8") as f:
                f.write('{\n "stock": "010140",\n "collected_at": "2026-10-02",\n "quarters": []}')
            with open(os.path.join(tmp, "summary.json"), "w", encoding="utf-8") as f:
                f.write("{}")
            self.assertEqual(M._peek_json_key(os.path.join(tmp, "010140.json"), "collected_at"), "2026-10-02")
            self.assertIsNone(M._peek_json_key(os.path.join(tmp, "010140.json"), "nope"))
            self.assertIsNone(M._peek_json_key(os.path.join(tmp, "missing.json"), "collected_at"))
            self.assertEqual(M._models_in_dir(tmp), ["010140"])                                     # summary.json 은 종목이 아니다
            self.assertEqual(M._models_in_dir(os.path.join(tmp, "none")), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestMobileCss(unittest.TestCase):
    """360px: grid2 카드가 360px 고정 최소폭으로 본문을 밀어내지 않게 min(360px,100%) · 표는 .wrap 안에서 가로 스크롤."""
    def test_rules_present(self):
        css = M.SECTION_CSS
        self.assertIn(".kmodel .grid2{grid-template-columns:repeat(auto-fit,minmax(min(360px,100%),1fr))}", css)
        self.assertIn(".kmodel .grid2>*{min-width:0}", css)
        self.assertIn(".kmodel .wrap{overflow-x:auto;max-width:100%", css)
        # 띄어쓰기 없는 긴 토큰(드라이버 type 'sls_marine_plus_uncovered_backlog_runoff', 파일명, URL)이 각주·가정 칸 밖으로 새지 않게
        self.assertIn(".kmodel .fn,.kmodel .assum>div,.kmodel h2 em,.kmodel .bandlbl span{overflow-wrap:anywhere}", css)
        self.assertIn("@media(max-width:480px)", css)
        self.assertIn(".kmodel .status{", css)


class TestRealAssetsAll(unittest.TestCase):
    """assets/models 전부(있으면): 태그 균형 · 상태 줄 · 폴백 라벨이 모델 필드와 일치 · 화면 텍스트에 -0/None/nan 누출 없음. 값은 검사하지 않는다(다른 레인 소유)."""
    def test_every_model_renders(self):
        stocks = M._models_in_dir(M.MODELS_DIR)
        if not stocks:
            self.skipTest("assets/models 없음")
        neg0 = re.compile(r">\s*-0(?:\.0+)?(?:%|배|원|억|%p)?\s*<")
        for st in stocks:
            model = M.load_model(st)
            sls = M._load_json(os.path.join(M.SLS_DIR, "%s.json" % st))
            h = M.render_model_section({"stock": st, "name": model.get("name"), "role": model.get("role")}, model, sls=sls)
            self.assertEqual(M.check_tag_balance(h), [], st)
            self.assertIn('<p class="status"><b class="', h, st)
            code = model.get("driver_fallback")
            if code in M.DRIVER_FALLBACK_KO:
                self.assertIn('data-model-driver-fallback="%s"' % code, h, st)
                self.assertIn("폴백 없음" if code == "none" else "폴백 사유 %s(" % code, h, st)
            if model.get("status") == "partial":
                self.assertIn("모델 상태 부분(partial)</b>사유: ", h, st)
                self.assertNotIn("사유: 미기재", h, st)                                              # 실물 partial 10사는 전부 되짚힌다
            text = re.sub(r"<script>.*?</script>", "", h, flags=re.S)
            self.assertIsNone(neg0.search(text), st)
            for bad in (">None<", ">nan<", ">NaN<", ">null<", ">undefined<", "title=\"\""):
                self.assertNotIn(bad, text, st)


if __name__ == "__main__":
    unittest.main()
