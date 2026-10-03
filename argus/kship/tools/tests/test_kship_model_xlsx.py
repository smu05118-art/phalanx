#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_model_xlsx 계약 테스트 — 표본 모델 json(fixtures/model_sample.json) → xlsx → 재오픈 검증.

실행: cd argus/kship/tools && python3 -m unittest tests.test_kship_model_xlsx -v
확인하는 것: 시트 목록·헤더 규약(행1 '4Q21'/2021 숫자, 행4 '2021.12'/'2021.12A', E열 시작)·이름정의·
확정 행 VLOOKUP 수식과 파이썬 VLOOKUP 흉내(2026Q2 매출액 = BS연결 값/100)·추정 행 가정 셀 참조와 재계산 일치·
추정 열 연노랑·경계 굵은 테두리·메모(basis)·파일 크기.
V5 검증 회귀: README 재현 명령·UPDATE 스탬프/문서속성/zip 시각 = built_at·두 번 생성 바이트 동일·
BS 에 없는 확정 셀은 모델값/빈 칸(VLOOKUP 0 금지)·역산 기준 = 시트 값·세전 항등식에 환관련손익.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

from openpyxl import load_workbook                          # noqa: E402

import kship_model_xlsx as X                                # noqa: E402

SAMPLE = os.path.join(HERE, "fixtures", "model_sample.json")


def _load_sample():
    with open(SAMPLE, encoding="utf-8") as f:
        return json.load(f)


class TestPeriods(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(X.qlabel("2021Q4"), "4Q21")
        self.assertEqual(X.qlabel("2026Q1"), "1Q26")
        self.assertEqual(X.qdate("2021Q4"), "2021.12")
        self.assertEqual(X.qdate("2026Q2"), "2026.06")

    def test_columns_annual_after_q4(self):
        cols = X.build_columns(["2021Q4", "2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q1"], ["2021", "2022", "2023"])
        keys = [c["key"] for c in cols]
        self.assertEqual(keys, ["2021Q4", "2021", "2022Q1", "2022Q2", "2022Q3", "2022Q4", "2022", "2023Q1", "2023"])
        self.assertEqual(cols[0]["col"], 5)                       # E열 시작
        self.assertEqual(cols[1]["label"], 2021)                  # 연간 라벨은 숫자
        self.assertEqual(cols[1]["date"], "2021.12A")


class TestBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = _load_sample()
        cls.tmp = tempfile.mkdtemp(prefix="kship_xlsx_")
        cls.out = os.path.join(cls.tmp, "sample_model.xlsx")
        # 다른 레인 산출(fin/sls/fx/prices)에 의존하지 않도록 없는 경로를 준다 — 표본만으로 만든다
        none = os.path.join(cls.tmp, "none.json")
        cls.rep = X.build_one(SAMPLE, out_path=cls.out, fin_path=none, sls_path=none, fx_path=none, prices_path=none, do_verify=True)
        cls.wb = load_workbook(cls.out, data_only=False)
        cls.lay = X.Layout(cls.model)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _subq_row(self, key):
        ws = self.wb["subQ"]
        for r in range(X.DATA_ROW, ws.max_row + 1):
            if ws.cell(r, 1).value == key:
                return r
        raise KeyError(key)

    def test_sheets_and_names(self):
        self.assertEqual(self.wb.sheetnames, ["README", "변수", "BS연결", "BS별도", "subQ", "분기", "연간예상", "TP", "외화"])
        names = set(self.wb.defined_names.keys())
        for n in ("SUBQH", "BS연결H", "BS별도H", "BS연결", "BS별도", "변수H", "환율", "subQ"):
            self.assertIn(n, names)
        self.assertTrue(self.wb.defined_names["BS연결"].attr_text.startswith("BS연결!$C$5:"))
        self.assertTrue(self.wb.defined_names["SUBQH"].attr_text.startswith("subQ!$A$1:"))

    def test_header_convention(self):
        for sn in ("subQ", "BS연결", "BS별도", "변수"):
            ws = self.wb[sn]
            self.assertEqual(ws.cell(1, 5).value, "4Q21", sn)
            self.assertEqual(ws.cell(1, 6).value, 2021, sn)             # 4분기 뒤 연간(숫자)
            self.assertEqual(ws.cell(1, 7).value, "1Q22", sn)
            self.assertEqual(ws.cell(4, 5).value, "2021.12", sn)
            self.assertEqual(ws.cell(4, 6).value, "2021.12A", sn)
            self.assertIsNone(ws.cell(1, 4).value if sn != "subQ" else None)   # D열은 데이터 아님
        self.assertEqual(self.wb["subQ"]["A1"].value, "YQ")
        self.assertEqual(self.wb["BS연결"]["B1"].value, "(백만원)")

    def test_actual_cell_is_vlookup_and_resolves(self):
        ws = self.wb["subQ"]
        r = self._subq_row("매출액")
        L = self.lay.letter("2026Q2")
        f = ws["%s%d" % (L, r)].value
        self.assertEqual(f, '=IFERROR(VLOOKUP($D%d,BS연결,MATCH(%s$1,BS연결H,0),0)/100,"")' % (r, L))
        self.assertEqual(ws.cell(r, 4).value, "매출액(수익)")
        chk = self.rep["verify"]["checks"][0]
        self.assertTrue(chk["ok"], chk)
        self.assertAlmostEqual(chk["emulated"], 32307.12, places=2)   # 3,230,712 백만원 / 100 (shi_2026Q2_cons)
        self.assertEqual(chk["vlookup_trace"]["bs_value_million"], 3230712)
        # 직접 흉내: BS연결 행1 라벨 → 열, C열 계정명 → 행
        bs = self.wb["BS연결"]
        col = next(c for c in range(5, bs.max_column + 1) if bs.cell(1, c).value == "2Q26")
        row = next(rr for rr in range(5, bs.max_row + 1) if bs.cell(rr, 3).value == "매출액(수익)")
        self.assertAlmostEqual(bs.cell(row, col).value / 100, 32307.12, places=2)

    def test_estimate_cell_references_vars_and_recomputes(self):
        ws = self.wb["subQ"]
        r = self._subq_row("매출액")
        L, LP = self.lay.letter("2026Q3"), self.lay.letter("2025Q3")
        f = ws["%s%d" % (L, r)].value
        self.assertTrue(f.startswith("=IFERROR(%s%d*(1+변수!%s" % (LP, r, L)), f)
        self.assertIsNotNone(ws["%s%d" % (L, r)].comment)
        self.assertIn("표본 가정", ws["%s%d" % (L, r)].comment.text)
        em = X.Emulator(self.wb)
        got = em.value("subQ", "%s%d" % (L, r))
        model_v = [x for x in self.model["rows"] if x["key"] == "매출액"][0]["q"]["2026Q3"]["v"]
        self.assertAlmostEqual(got, model_v, delta=0.05)
        # 가정 셀을 바꾸면 결과가 따라간다(수식이 진짜 가정 셀을 참조)
        vr = self.wb["변수"]
        drv = next(rr for rr in range(5, vr.max_row + 1) if vr.cell(rr, 1).value == "drv:매출액")
        g = vr["%s%d" % (L, drv)].value
        self.assertIsInstance(g, float)
        vr["%s%d" % (L, drv)].value = g + 0.10
        em2 = X.Emulator(self.wb)
        self.assertAlmostEqual(em2.value("subQ", "%s%d" % (L, r)), got + 0.10 * em2.value("subQ", "%s%d" % (LP, r)), delta=0.05)
        vr["%s%d" % (L, drv)].value = g

    def test_estimate_recalc_all_rows(self):
        e = self.rep["verify"]["estimate_recalc"]
        self.assertEqual(e["quarters"], ["2026Q3", "2026Q4"])
        self.assertGreater(e["rows"], 40)
        self.assertEqual(e["mismatch"], [], e["mismatch"])

    def test_identity_rows_are_formulas_of_subq(self):
        ws = self.wb["subQ"]
        L = self.lay.letter("2027Q1")
        r_cogs, r_rev, r_gp = self._subq_row("매출원가"), self._subq_row("매출액"), self._subq_row("매출총이익")
        self.assertEqual(ws["%s%d" % (L, r_cogs)].value, '=IFERROR(%s%d-%s%d,"")' % (L, r_rev, L, r_gp))
        r_a, r_l, r_e = self._subq_row("자산총계"), self._subq_row("부채총계"), self._subq_row("자본총계")
        self.assertEqual(ws["%s%d" % (L, r_a)].value, '=IFERROR(%s%d+%s%d,"")' % (L, r_l, L, r_e))
        r_eps, r_ni, r_sh = self._subq_row("EPS"), self._subq_row("지배주주순이익"), self._subq_row("주식수")
        self.assertEqual(ws["%s%d" % (L, r_eps)].value, '=IFERROR(%s%d*100/%s%d,"")' % (L, r_ni, L, r_sh))

    def test_annual_columns(self):
        ws = self.wb["subQ"]
        r = self._subq_row("매출액")
        # 2022(실적·계정 매핑) → BS연결 연간 열 VLOOKUP, 2027(추정) → 4분기 SUM, 자산총계 연간 → 4Q 값
        self.assertIn("VLOOKUP($D%d,BS연결" % r, ws["%s%d" % (self.lay.letter("2022"), r)].value)
        q1, q4 = self.lay.letter("2027Q1"), self.lay.letter("2027Q4")
        self.assertEqual(ws["%s%d" % (self.lay.letter("2027"), r)].value, "=SUM(%s%d:%s%d)" % (q1, r, q4, r))
        ra = self._subq_row("자산총계")
        self.assertEqual(ws["%s%d" % (self.lay.letter("2027"), ra)].value, "=%s%d" % (q4, ra))
        em = X.Emulator(self.wb)
        got = em.value("subQ", "%s%d" % (self.lay.letter("2022"), r))
        self.assertAlmostEqual(got, 59446.67, places=1)           # golden 2022.12A 매출액(수익) 5,944,667.45 백만원

    def test_styles_boundary_and_estimate_fill(self):
        ws = self.wb["subQ"]
        r = self._subq_row("영업이익")
        c_last = ws.cell(r, self.lay.col_of("2026Q2"))
        self.assertEqual(c_last.border.right.style, "medium")
        c_est = ws.cell(r, self.lay.col_of("2026Q3"))
        self.assertEqual(c_est.fill.fgColor.rgb[-6:], "FFF9DB")
        c_act = ws.cell(r, self.lay.col_of("2026Q1"))
        self.assertNotEqual(c_act.fill.fgColor.rgb[-6:], "FFF9DB")
        self.assertEqual(c_est.number_format, "#,##0")
        # 갭필 추정(실적 구간)도 노랑 + 메모
        c_gap = ws.cell(r, self.lay.col_of("2024Q2"))
        self.assertEqual(c_gap.fill.fgColor.rgb[-6:], "FFF9DB")
        self.assertIn("갭필", c_gap.comment.text)

    def test_views_lookup_subq(self):
        q = self.wb["분기"]
        self.assertEqual(q.cell(1, 5).value, "4Q21")
        self.assertIsNone(next((c for c in range(5, q.max_column + 1) if isinstance(q.cell(1, c).value, int)), None))  # 분기만
        r = next(rr for rr in range(5, q.max_row + 1) if q.cell(rr, 1).value == "영업이익")
        self.assertEqual(q.cell(r, 5).value, '=IFERROR(VLOOKUP($A%d,subQ,MATCH(E$1,SUBQH,0),0),"")' % r)
        em = X.Emulator(self.wb)
        col = next(c for c in range(5, q.max_column + 1) if q.cell(1, c).value == "2Q26")
        self.assertAlmostEqual(em.value("분기", "%s%d" % (X.get_column_letter(col), r)), 3250.24, places=2)
        a = self.wb["연간예상"]
        self.assertEqual(a.cell(1, 5).value, 2021)
        ra = next(rr for rr in range(5, a.max_row + 1) if a.cell(rr, 1).value == "매출액")
        col = next(c for c in range(5, a.max_column + 1) if a.cell(1, c).value == 2025)
        self.assertAlmostEqual(em.value("연간예상", "%s%d" % (X.get_column_letter(col), ra)), 106500.11, places=1)

    def test_tp_and_fx_sheets(self):
        tp = self.wb["TP"]
        self.assertEqual(tp["B1"].value, "종가")
        self.assertTrue(str(tp["C1"].value).startswith("=변수!D"))
        formulas = [c.value for row in tp.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=")]
        self.assertTrue(any("PER_" in f or "ROUND(" in f for f in formulas))
        fx = self.wb["외화"]
        self.assertIn("VLOOKUP($D5,환율,MATCH(E$1,변수H,0),0)", fx["E5"].value)

    def test_size_and_counts(self):
        v = self.rep["verify"]
        self.assertTrue(v["size_ok"])
        self.assertLess(v["size_bytes"], 2 * 1024 * 1024)
        self.assertGreater(v["formulas_total"], 1500)
        self.assertGreater(v["sheets"]["subQ"]["comments"], 100)
        self.assertNotIn("error", self.rep)


class TestSlsSheet(unittest.TestCase):
    def test_sls_from_inline_dict(self):
        model = _load_sample()
        model["sls"] = {"stock": "010140", "origin": "2026Q2", "unit": "USD_million",
                        "contracts": [{"rcp": "r1", "type": "LNGC", "ships": 2, "amt_usd_m": 500, "cohort": "⑤초호황", "schedule": {"2026Q3": 50}}],
                        "by_quarter": {"2026Q3": {"usd_m": 50, "by_type": {"LNGC": 50}, "by_cohort": {"⑤초호황": 50}, "hedged_krw_m": 69000,
                                                  "applied_rate": 1380, "hedge_ratio": 0.7, "hedge_rate": 1350, "spot_assumed": 1450}},
                        "by_year": {"2026": {"usd_m": 50}}, "target_opm": {"2026Q3": {"opm": 0.12, "basis": "test"}},
                        "warnings": ["테스트"]}
        tmp = tempfile.mkdtemp(prefix="kship_sls_")
        try:
            b = X.Builder(model)
            wb = b.build()
            self.assertIn("SLS", wb.sheetnames)
            self.assertEqual(wb.sheetnames.index("SLS"), wb.sheetnames.index("subQ") + 1)
            ws = wb["SLS"]
            self.assertEqual(ws.cell(1, 5).value, "3Q26")
            self.assertEqual(ws.cell(1, 6).value, 2026)
            keys = [ws.cell(r, 1).value for r in range(5, ws.max_row + 1)]
            for k in ("usd_m", "type:LNGC", "cohort:⑤초호황", "hedge_ratio", "applied_rate", "target_opm"):
                self.assertIn(k, keys)
            out = os.path.join(tmp, "x.xlsx")
            X.save_atomic(wb, out)
            self.assertTrue(os.path.getsize(out) > 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestReadmeAndDeterminism(unittest.TestCase):
    """V5 검증에서 잡은 결함의 회귀 테스트 — README 재현 명령, UPDATE 스탬프·문서 속성·zip 시각 = built_at, 두 번 생성 바이트 동일."""

    @classmethod
    def setUpClass(cls):
        cls.model = _load_sample()
        cls.tmp = tempfile.mkdtemp(prefix="kship_xlsx_det_")
        none = os.path.join(cls.tmp, "none.json")
        cls.out1 = os.path.join(cls.tmp, "a.xlsx")
        cls.out2 = os.path.join(cls.tmp, "b.xlsx")
        X.build_one(SAMPLE, out_path=cls.out1, fin_path=none, sls_path=none, fx_path=none, prices_path=none)
        X.build_one(SAMPLE, out_path=cls.out2, fin_path=none, sls_path=none, fx_path=none, prices_path=none)
        cls.wb = load_workbook(cls.out1)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_readme_has_source_disclaimer_and_repro(self):
        txt = "\n".join(str(c.value) for row in self.wb["README"].iter_rows() for c in row if c.value is not None)
        self.assertIn("출처: DART", txt)
        self.assertIn("추천 아님", txt)
        self.assertIn("재현: cd argus/kship/tools", txt)
        self.assertIn("kship_model_xlsx.py --model assets/models/010140.json --verify", txt)
        self.assertIn("kship_model.py --build --all --xlsx", txt)

    def test_bs_update_stamp_is_built_at_not_today(self):
        self.assertTrue(str(self.model["built_at"]).startswith("2026-09-30"))
        for sn in ("BS연결", "BS별도"):
            self.assertEqual(self.wb[sn]["C3"].value, "UPDATE: 26-09-30", sn)

    def test_core_modified_equals_created_and_zip_times_fixed(self):
        import hashlib
        import re
        import zipfile
        z = zipfile.ZipFile(self.out1)
        core = z.read("docProps/core.xml").decode("utf-8")
        created = re.search(r"<dcterms:created[^>]*>([^<]*)<", core).group(1)
        modified = re.search(r"<dcterms:modified[^>]*>([^<]*)<", core).group(1)
        self.assertEqual(created, "2026-09-30T00:00:00Z")
        self.assertEqual(modified, created)
        self.assertEqual({i.date_time for i in z.infolist()}, {(2026, 9, 30, 0, 0, 0)})
        h1 = hashlib.sha256(open(self.out1, "rb").read()).hexdigest()
        h2 = hashlib.sha256(open(self.out2, "rb").read()).hexdigest()
        self.assertEqual(h1, h2, "같은 입력인데 바이트가 다르다")


class TestBsMissingAndIdentity(unittest.TestCase):
    """BS 시트에 값이 없는 확정 셀은 VLOOKUP(→0) 대신 모델값/빈 칸 · 역산 기준은 시트 값 · 세전 항등식에 환관련손익 포함."""

    def _fin(self, model):
        rev = {x["key"]: x for x in model["rows"]}["매출액"]
        # 2026Q2 매출만 BS 에 있고, 2026Q1 매출(실측)은 모델 v 보다 0.4 억원(40 백만원) 큰 '반올림 전' 값
        return {"cons": {"bs": {}, "cf": {}, "is": {
            "2026Q2": {"매출액(수익)": round(rev["q"]["2026Q2"]["v"] * 100, 2)},
            "2026Q1": {"매출액(수익)": round(rev["q"]["2026Q1"]["v"] * 100 + 40, 2)}}}}

    def test_actual_cells_without_bs_value(self):
        model = _load_sample()
        rows = {x["key"]: x for x in model["rows"]}
        rows["금융손익"]["q"]["2026Q1"] = {"v": None, "kind": "actual", "src": "테스트 — 값 없음"}
        b = X.Builder(model, fin=self._fin(model))
        wb = b.build()
        ws = wb["subQ"]
        lay = X.Layout(model)
        row_of = lambda k: next(r for r in range(X.DATA_ROW, ws.max_row + 1) if ws.cell(r, 1).value == k)
        L2 = lay.letter("2026Q2")
        self.assertIn("VLOOKUP($D", ws["%s%d" % (L2, row_of("매출액"))].value)              # BS 에 있음 → VLOOKUP
        c = ws["%s%d" % (L2, row_of("지배주주순이익"))]
        self.assertEqual(c.value, rows["지배주주순이익"]["q"]["2026Q2"]["v"])                 # BS 에 없음 → 모델값 직접
        self.assertIn("BS연결 시트에 (지배주주지분)당기순이익 2026.06 값 없음", c.comment.text)
        c1 = ws["%s%d" % (lay.letter("2026Q1"), row_of("금융손익"))]
        self.assertIsNone(c1.value)                                                        # 모델도 BS 도 없음 → 빈 칸(0 표시 금지)
        # 2022 연간: BS 에 연간 값 없음 + 4분기 있음 → SUM 수식(VLOOKUP 0 아님)
        q1, q4 = lay.letter("2022Q1"), lay.letter("2022Q4")
        r = row_of("매출액")
        self.assertEqual(ws["%s%d" % (lay.letter("2022"), r)].value, "=SUM(%s%d:%s%d)" % (q1, r, q4, r))
        # 역산 기준 = 시트 값: 2027Q1 매출 YoY 는 BS 의 2026Q1(모델 v + 0.4, VLOOKUP 셀) 기준이어야 재계산이 모델과 맞는다
        vr = wb["변수"]
        drv = next(rr for rr in range(5, vr.max_row + 1) if vr.cell(rr, 1).value == "drv:매출액")
        L3 = lay.letter("2027Q1")
        g = vr["%s%d" % (L3, drv)].value
        v3, v_prev = rows["매출액"]["q"]["2027Q1"]["v"], rows["매출액"]["q"]["2026Q1"]["v"]
        self.assertAlmostEqual(g, v3 / (v_prev + 0.4) - 1, places=5)
        self.assertNotAlmostEqual(g, v3 / v_prev - 1, places=5)                            # 모델 반올림값 기준이 아니다
        em = X.Emulator(wb)
        self.assertAlmostEqual(em.value("subQ", "%s%d" % (L3, r)), v3, delta=0.05)

    def test_pretax_identity_includes_fx_pnl_row(self):
        model = _load_sample()
        rows = {x["key"]: x for x in model["rows"]}
        i = [x["key"] for x in model["rows"]].index("세전이익")
        fx_row = {"key": "환관련손익", "label": "환관련손익", "group": "손익", "unit": "억원",
                  "q": {q: {"v": 132.71, "kind": "estimate", "basis": "테스트 — 외화 순노출 × Δ환율"} for q in model["periods"]["quarters"] if q > "2026Q2"}}
        model["rows"].insert(i, fx_row)
        for q in fx_row["q"]:
            rows["세전이익"]["q"][q]["v"] = round(rows["세전이익"]["q"][q]["v"] + 132.71, 2)
        plan = X.plan_drivers(model["rows"])
        self.assertIn(("+", "환관련손익"), plan["세전이익"]["expr"])
        b = X.Builder(model)
        wb = b.build()
        ws = wb["subQ"]
        lay = X.Layout(model)
        L = lay.letter("2026Q3")
        r_pt, r_fx, r_op = b.subq_row["세전이익"], b.subq_row["환관련손익"], b.subq_row["영업이익"]
        f = ws["%s%d" % (L, r_pt)].value
        self.assertTrue(f.startswith("=IFERROR(%s%d+" % (L, r_op)), f)
        self.assertIn("+%s%d" % (L, r_fx), f)
        em = X.Emulator(wb)
        self.assertAlmostEqual(em.value("subQ", "%s%d" % (L, r_pt)), rows["세전이익"]["q"]["2026Q3"]["v"], delta=0.05)


if __name__ == "__main__":
    unittest.main()
