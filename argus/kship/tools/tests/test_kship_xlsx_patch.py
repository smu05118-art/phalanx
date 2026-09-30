#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_xlsx_patch 계약 테스트 — 레퍼런스 subQ xlsx 제자리 패치(MODEL_SPEC 2-6).

실행: cd argus/kship/tools && ~/Library/phalanx_venv/bin/python -m unittest tests.test_kship_xlsx_patch -v
- 순수 함수(기간 순서·라벨·sharedStrings·행 재조립·fin 값 규칙)는 픽스처 없이 돈다.
- 실제 원본(`~/phalanx/jem_data/kship_models/reference/*_orig.xlsx`, 사용자 사유 파일)이 있을 때만
  통합 테스트가 돈다. 출력은 항상 임시 폴더 — 레퍼런스 폴더에 쓰지 않는다.
- 표본 fin: tests/fixtures/fin/fin_sample_010140.json (삼성중공업 2026Q2·2025Q4, 픽스처 HTML 에서 손으로 옮김).
- 세진·미포는 합성 fin(값은 의미 없음) 으로 4시트 매핑·충돌 보존·/U 나눗셈 경로만 확인한다.
"""
import copy
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures", "fin")
sys.path.insert(0, TOOLS)

import kship_xlsx_patch as P  # noqa: E402

REF = P.REF_DIR
SAMPLE = os.path.join(FIX, "fin_sample_010140.json")
FX_JSON = os.path.join(TOOLS, "assets", "fx.json")          # 실측 환율(ECB) — --fx-actuals 통합 테스트용


def _orig(stock):
    return os.path.join(REF, "%s_%s_subQ_orig.xlsx" % (P.FILES[stock]["name"], stock))


def _has(stock):
    return os.path.exists(_orig(stock))


class TestPeriods(unittest.TestCase):
    def test_period_seq_from_q3(self):
        seq = [P.period_key(p) for p in P.period_seq(("Q", 2023, 3), "2026Q2")]
        self.assertEqual(seq[:3], ["2023Q4", "2023A", "2024Q1"])
        self.assertEqual(seq[-2:], ["2026Q1", "2026Q2"])
        self.assertEqual(len(seq), 14)                  # 세진·삼성중: CS..DF

    def test_period_seq_from_annual(self):
        seq = [P.period_key(p) for p in P.period_seq(("A", 2024), "2026Q2")]
        self.assertEqual(seq, ["2025Q1", "2025Q2", "2025Q3", "2025Q4", "2025A", "2026Q1", "2026Q2"])  # 미포: CZ..DF

    def test_period_seq_q4_target_includes_annual(self):
        seq = [P.period_key(p) for p in P.period_seq(("Q", 2025, 3), "2025Q4")]
        self.assertEqual(seq, ["2025Q4", "2025A"])

    def test_labels(self):
        self.assertEqual(P.row1_label(("Q", 2026, 2)), "2Q26")
        self.assertEqual(P.row1_label(("A", 2025)), "2025")
        self.assertEqual(P.row4_label(("Q", 2023, 4)), ("2023.12", False))
        self.assertEqual(P.row4_label(("A", 2023)), ("2023.12A", True))
        self.assertEqual(P.parse_row4_label("2023.09", False), ("Q", 2023, 3))
        self.assertEqual(P.parse_row4_label("2024.12A", True), ("A", 2024))
        self.assertIsNone(P.parse_row4_label("Account", True))
        self.assertIsNone(P.parse_row4_label("3", False))

    def test_columns(self):
        self.assertEqual(P.col_idx("CS"), 97)
        self.assertEqual(P.col_letters(97), "CS")
        self.assertEqual(P.col_letters(P.col_idx("DF")), "DF")

    def test_fmt_num(self):
        self.assertEqual(P.fmt_num(544559.82), "544559.82")
        self.assertEqual(P.fmt_num(2023.0), "2023")
        self.assertEqual(P.fmt_num(-61044.99), "-61044.99")
        with self.assertRaises(ValueError):
            P.fmt_num(float("nan"))


class TestSharedStrings(unittest.TestCase):
    XML = ('<?xml version="1.0"?><sst xmlns="x" count="5" uniqueCount="3"><si><t>a</t></si>'
           '<si><r><t>b1</t></r><r><t>b2</t></r></si><si><t xml:space="preserve"> c</t></si></sst>')

    def test_parse_and_add(self):
        s = P.SharedStrings(self.XML)
        self.assertEqual(s.texts, ["a", "b1b2", " c"])
        self.assertEqual(s.find(" c"), 2)
        self.assertEqual(s.add("a"), 0)                 # 기존 → 인덱스 재사용, 참조만 +1
        self.assertEqual(s.add("2023.12A"), 3)
        self.assertEqual(s.add("2023.12A"), 3)
        self.assertEqual(s.add(" 원/달러"), 4)
        out = s.render()
        self.assertIn('count="9"', out)                 # 5 + 4 참조
        self.assertIn('uniqueCount="5"', out)
        self.assertTrue(out.endswith('<si><t>2023.12A</t></si><si><t xml:space="preserve"> 원/달러</t></si></sst>'))
        self.assertTrue(out.startswith(self.XML[:self.XML.index("<si>")].replace('count="5"', 'count="9"').replace('uniqueCount="3"', 'uniqueCount="5"')))

    def test_untouched_when_nothing_added(self):
        s = P.SharedStrings(self.XML)
        self.assertEqual(s.render(), self.XML)


class TestRowRebuild(unittest.TestCase):
    ROW = ('<sheetData><row r="5" spans="1:10" s="34" customFormat="1"><c r="A5" s="75"><v>1</v></c>'
           '<c r="C5" s="76" t="s"><v>207</v></c><c r="CR5" s="77"><v>544559.82</v></c>'
           '<c r="CS5" s="77"/><c r="CT5" s="78"/></row><row r="6"/></sheetData>')

    def test_replace_empty_and_append(self):
        xml, w, conf, _ = P.rebuild_row(self.ROW, 5, {"CS": (1.5, False), "CT": (7, True), "CV": (2.0, False)})
        self.assertEqual(conf, [])
        self.assertEqual(w, [("CS", "77"), ("CT", "78"), ("CV", "78")])   # 빈 자리 셀은 자기 s, 새 셀은 직전 s
        self.assertIn('<c r="CS5" s="77"><v>1.5</v></c><c r="CT5" s="78" t="s"><v>7</v></c><c r="CV5" s="78"><v>2</v></c></row>', xml)
        self.assertIn('<c r="CR5" s="77"><v>544559.82</v></c>', xml)     # 기존 셀 그대로
        self.assertTrue(xml.endswith('<row r="6"/></sheetData>'))

    def test_conflict_preserved(self):
        xml, w, conf, _ = P.rebuild_row(self.ROW, 5, {"CR": (1.0, False), "CS": (2.0, False)})
        self.assertEqual([c for c, _ in conf], ["CR"])
        self.assertIn('<c r="CR5" s="77"><v>544559.82</v></c>', xml)
        self.assertEqual([c for c, _ in w], ["CS"])

    def test_insert_between(self):
        row = '<row r="4"><c r="D4" s="74"><v>1</v></c><c r="F4" s="74"><v>3</v></c></row>'
        xml, w, conf, _ = P.rebuild_row(row, 4, {"E": (2.0, False)})
        self.assertEqual(xml, '<row r="4"><c r="D4" s="74"><v>1</v></c><c r="E4" s="74"><v>2</v></c><c r="F4" s="74"><v>3</v></c></row>')

    def test_self_closing_row(self):
        row = '<row r="4" spans="1:3"/>'
        xml, w, conf, _ = P.rebuild_row(row, 4, {"B": (9, False)})
        self.assertEqual(xml, '<row r="4" spans="1:3"><c r="B4"><v>9</v></c></row>')

    def test_replace_cell(self):
        xml = P.replace_cell(self.ROW, 5, "C", '<c r="C5" s="76" t="s"><v>999</v></c>')
        self.assertIn('<c r="C5" s="76" t="s"><v>999</v></c><c r="CR5"', xml)

    def test_calc_pr(self):
        class W:                                   # Workbook.set_calc_full 만 빌려 쓴다
            pass
        w = W()
        w.wb_xml = '<workbook><calcPr calcId="152511"/></workbook>'
        self.assertTrue(P.Workbook.set_calc_full(w))
        self.assertEqual(w.wb_xml, '<workbook><calcPr calcId="152511" fullCalcOnLoad="1"/></workbook>')
        self.assertFalse(P.Workbook.set_calc_full(w))


class TestValueRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SAMPLE, encoding="utf-8") as f:
            cls.fin = json.load(f)

    def test_quarter_bs_is(self):
        self.assertEqual(P.value_for(self.fin, "cons", "자산총계", ("Q", 2026, 2)), (17959382.2, "bs"))
        self.assertEqual(P.value_for(self.fin, "cons", "매출액(수익)", ("Q", 2026, 2)), (3230712.01, "is"))
        self.assertEqual(P.value_for(self.fin, "sep", "매출액(수익)", ("Q", 2026, 2)), (3224937.5, "is"))
        self.assertEqual(P.value_for(self.fin, "cons", "매출액(수익)", ("Q", 2026, 1)), (None, None))   # 표본에 없는 분기

    def test_annual_rules(self):
        self.assertEqual(P.value_for(self.fin, "cons", "자산총계", ("A", 2025)), (14948871.09, "bs"))     # BS = Q4 시점
        self.assertEqual(P.value_for(self.fin, "cons", "매출액(수익)", ("A", 2025)), (10650010.7, "is_ytd"))
        self.assertEqual(P.value_for(self.fin, "cons", "매출액(수익)", ("A", 2026)), (None, None))        # 4분기 미완
        fin = {"cons": {"is": {"2024Q%d" % n: {"x": 1.5} for n in (1, 2, 3, 4)}}}
        self.assertEqual(P.value_for(fin, "cons", "x", ("A", 2024)), (6.0, "is_sum4"))
        fin["cons"]["is"].pop("2024Q3")
        self.assertEqual(P.value_for(fin, "cons", "x", ("A", 2024)), (None, None))

    def test_shares_and_dividend(self):
        self.assertEqual(P.value_for(self.fin, "cons", "기말발행주식수(백만주)", ("Q", 2026, 2)), (880.114845, "shares"))
        self.assertEqual(P.value_for(self.fin, "sep", "보통주기말자기주식수", ("Q", 2026, 2)), (25.964429, "shares"))
        v, src = P.value_for(self.fin, "cons", "우선주기말발행주식수", ("Q", 2026, 2))
        self.assertAlmostEqual(v, 0.114845)
        self.assertEqual(P.value_for(self.fin, "cons", P.DPS_ACCT, ("Q", 2025, 4)), (0, "dividend"))
        self.assertEqual(P.value_for(self.fin, "cons", P.DPS_ACCT, ("Q", 2026, 2)), (None, None))

    def test_mcap_needs_prices(self):
        self.assertEqual(P.value_for(self.fin, "cons", "보통주시가총액(기말, 십억원)", ("Q", 2026, 2)), (None, None))
        prices = {"rows": {"010140": {"history_quarterly": {"2026Q2": {"close_end": 23450}}}}}
        self.assertEqual(P.value_for(self.fin, "cons", "보통주시가총액(기말, 십억원)", ("Q", 2026, 2), prices), (20636.0, "mcap"))


@unittest.skipUnless(_has("010140") and os.path.exists(SAMPLE), "삼성중공업 원본 또는 표본 fin 없음")
class TestSamsungPatch(unittest.TestCase):
    """실제 원본 + 표본 fin → 임시 폴더 출력 → 검증 5항."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kship_xlsx_")
        with open(SAMPLE, encoding="utf-8") as f:
            cls.fin = json.load(f)
        cls.fins = {"010140": cls.fin}
        cls.prices = {"as_of": "2026-09-30", "rows": {"010140": {"close": 20100, "as_of": "20260928",
                      "history_quarterly": {"2026Q2": {"close_end": 23450, "high": 35900, "low": 22200, "avg": 28821.3}}}}}
        cls.fx = {"quarters": {"2026Q2": {"USDKRW_avg": 1501.75}}, "annual": {}}
        cls.out = os.path.join(cls.tmp, "shi_2026Q2.xlsx")
        cls.rep = P.patch_file("010140", cls.fins, "2026Q2", "2026-09-30", out_path=cls.out, fx=cls.fx, prices=cls.prices)
        cls.ver = P.verify_all(cls.rep, cls.fins)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_written_and_orig_untouched(self):
        self.assertTrue(self.rep["written"], self.rep.get("error"))
        self.assertTrue(os.path.exists(self.out))
        self.assertEqual(self.rep["orig"], _orig("010140"))
        self.assertNotEqual(self.rep["out"], self.rep["orig"])

    def test_1_zip(self):
        self.assertTrue(self.ver["1_zip"]["ok"], self.ver["1_zip"])

    def test_2_reopen(self):
        v = self.ver["2_reopen"]
        self.assertTrue(v["ok"], v["diff"])
        self.assertEqual(v["sheets_orig"], v["sheets_patched"])
        self.assertEqual(v["formula_cells_orig"], v["formula_cells_patched"])
        self.assertGreater(v["formula_cells_orig"], 1000)

    def test_3_patched_cells(self):
        sheets = {s["sheet"]: s for s in self.rep["sheets"]}
        self.assertEqual(set(sheets), {"BS연결", "BS별도"})
        for s in sheets.values():
            self.assertIsNone(s.get("error"), s.get("error"))
            self.assertEqual(s["last_actual"], "2023Q3")
            self.assertEqual(s["new_periods"][0], "2023Q4")
            self.assertEqual(s["new_periods"][-1], "2026Q2")
            self.assertEqual(len(s["new_periods"]), 14)
            self.assertEqual(s["columns"]["2023Q4"], "CS")           # 행1 라벨로 찾은 결과(하드코딩 아님)
            self.assertEqual(s["columns"]["2026Q2"], "DF")
            self.assertEqual(s["cells_label"], 14)
            self.assertEqual(s["cells_stamp"], 1)
            self.assertGreater(s["cells_value"], 30)
            self.assertEqual(s["conflicts"], [])                     # 표본엔 2023Q4 값이 없어 가이던스 셀과 안 부딪힘
            self.assertIn("2026Q1", s["missing_quarters"])
            self.assertIn("매출채권및기타채권", s["missing_accounts"])   # 표본에 없는 계정은 비움+목록
        self.assertGreater(self.ver["3_patched_cells"]["count"], 100)
        self.assertEqual(self.rep["sst_added"], ["2023.12A", "2024.12A", "2025.12A", "UPDATE: 26-09-30", "종가(09월 28일)"])
        self.assertTrue(self.rep["calcPr_changed"])

    def test_4_unchanged(self):
        v = self.ver["4_unchanged"]
        self.assertTrue(v["ok"], v["problems"])
        # 허용 교체: 두 BS 시트의 C3 스탬프 + 종가 셀·라벨
        self.assertEqual(len(v["changed_existing_cells"]), 4)
        self.assertEqual(v["replaced_empty_cells"], 9)                # BS별도 행4 의 비어 있던 CS..DA 자리 셀
        self.assertEqual(set(v["changed_members"]) - {"xl/workbook.xml", "xl/sharedStrings.xml"},
                         {s["member"] for s in self.rep["sheets"]} | {P.Workbook(self.rep["orig"]).sheets["TP_BPS"]})

    def test_prefilled_guidance_cells_kept(self):
        """BS연결 CS69/CT69(애널리스트 가이던스 수식·상수) 는 바이트 그대로."""
        member = {s["sheet"]: s["member"] for s in self.rep["sheets"]}["BS연결"]
        a = zipfile.ZipFile(self.rep["orig"]).read(member).decode("utf-8")
        b = zipfile.ZipFile(self.out).read(member).decode("utf-8")
        for ref in ("CS69", "CT69", "CS143", "CT144"):
            ca = {m.group(1) + m.group(2): m.group(0) for m in P.CELL_RE.finditer(a)}[ref]
            cb = {m.group(1) + m.group(2): m.group(0) for m in P.CELL_RE.finditer(b)}[ref]
            self.assertEqual(ca, cb, ref)
        self.assertIn("<f>CT69-SUM(CP69:CR69)</f>", b)

    def test_5_chain(self):
        v = self.ver["5_chain"]
        self.assertTrue(v["ok"], v["problems"])
        self.assertGreaterEqual(v["checked"], 3)
        got = {(r["table"], c["period"]): c for r in v["rows"] for c in r["checks"]}
        self.assertEqual(got[("BS연결", "2026Q2")]["value_bs"], 3230712.01)
        self.assertEqual(got[("BS연결", "2025A")]["value_bs"], 10650010.7)
        self.assertEqual(got[("BS연결", "2026Q2")]["label"], "2Q26")
        self.assertEqual(got[("BS별도", "2026Q2")]["value_bs"], 3224937.5)

    def test_readback_values(self):
        op = P.load_openpyxl()
        wb = op.load_workbook(self.out, data_only=True, keep_links=False)
        ws = wb["BS연결"]
        self.assertEqual(ws["C3"].value, "UPDATE: 26-09-30")
        self.assertEqual(ws["CS4"].value, 2023.12)
        self.assertEqual(ws["CT4"].value, "2023.12A")
        self.assertEqual(ws["DF4"].value, 2026.06)
        self.assertEqual(ws["DF5"].value, 17959382.2)                # 자산총계 2026Q2
        self.assertEqual(ws["DD5"].value, 14948871.09)               # 2025A = 2025Q4 시점 BS
        self.assertEqual(ws["DC5"].value, 14948871.09)
        self.assertIsNone(ws["DE5"].value)                            # 2026Q1 표본에 없음 → 비움
        self.assertEqual(ws["DF69"].value, 3230712.01)               # 매출액(수익)
        self.assertEqual(wb["TP_BPS"]["C1"].value, 20100)
        self.assertEqual(wb["TP_BPS"]["B1"].value, "종가(09월 28일)")
        self.assertEqual(self.rep["fx"]["filled"], 0)                # 환율 행은 2030 까지 가정 상수가 이미 있어 보존
        self.assertGreater(self.rep["fx"]["kept"], 0)

    def test_no_output_without_fin(self):
        rep = P.patch_file("010140", {}, "2026Q2", "2026-09-30", out_path=os.path.join(self.tmp, "none.xlsx"))
        self.assertFalse(rep["written"])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "none.xlsx")))
        self.assertEqual(len(rep["skipped_sheets"]), 2)


@unittest.skipUnless(_has("075580"), "세진중공업 원본 없음")
class TestSejinFourSheets(unittest.TestCase):
    """합성 fin(값은 표식용) 으로 4개 BS 시트 매핑 + /U 나눗셈 사슬 + 빈 자리 셀 교체를 확인."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kship_xlsx_")

        def fin(stock, scopes):
            d = {"stock": stock, "quarters": ["2023Q4"]}
            for scope, sales in scopes.items():
                d[scope] = {"bs": {"2023Q4": {"자산총계": sales * 10}}, "is": {"2023Q4": {"매출액(수익)": sales}}}
            return d
        cls.fins = {"075580": fin("075580", {"cons": 111.0, "sep": 222.0}),
                    "333430": fin("333430", {"sep": 333.0}), "099410": fin("099410", {"sep": 444.0})}
        cls.out = os.path.join(cls.tmp, "sejin.xlsx")
        cls.rep = P.patch_file("075580", cls.fins, "2023Q4", "2026-09-30", out_path=cls.out)
        cls.ver = P.verify_all(cls.rep, cls.fins)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_four_sheets(self):
        self.assertTrue(self.rep["written"], self.rep.get("error"))
        sheets = {s["sheet"]: s for s in self.rep["sheets"]}
        self.assertEqual(set(sheets), {"BS연결", "BS별도", "BS일승(별도)", "BS동방선기(별도)"})
        for s in sheets.values():
            self.assertEqual(s["new_periods"], ["2023Q4", "2023A"])
            self.assertEqual(s["columns"], {"2023Q4": "CS", "2023A": "CT"})
            self.assertEqual(s["cells_label"], 2)
            self.assertEqual(s["conflicts"], [])
        self.assertEqual(sheets["BS일승(별도)"]["stock"], "333430")
        self.assertEqual(sheets["BS동방선기(별도)"]["stock"], "099410")

    def test_verify(self):
        v = self.ver
        self.assertTrue(v["1_zip"]["ok"])
        self.assertTrue(v["2_reopen"]["ok"], v["2_reopen"]["diff"])
        self.assertTrue(v["4_unchanged"]["ok"], v["4_unchanged"]["problems"])
        self.assertGreater(v["4_unchanged"]["replaced_empty_cells"], 4)   # CS/CT 빈 자리 셀 교체
        self.assertTrue(v["5_chain"]["ok"], v["5_chain"]["problems"])
        rows = {r["table"]: r for r in v["5_chain"]["rows"]}
        self.assertEqual(rows["BS연결"]["divisor"], 100.0)                 # 세진 subQ 는 /U (U=100)
        self.assertEqual(rows["BS연결"]["checks"][0]["value_bs"], 111.0)
        self.assertEqual(rows["BS별도"]["checks"][0]["value_bs"], 222.0)

    def test_readback(self):
        op = P.load_openpyxl()
        wb = op.load_workbook(self.out, data_only=True, keep_links=False)
        self.assertEqual(wb["BS일승(별도)"]["CS5"].value, 3330.0)
        self.assertEqual(wb["BS동방선기(별도)"]["CS5"].value, 4440.0)
        self.assertEqual(wb["BS연결"]["CT4"].value, "2023.12A")
        self.assertEqual(wb["BS연결"]["CS4"].value, 2023.12)
        self.assertEqual(wb["BS동방선기(별도)"]["C3"].value, "UPDATE: 26-09-30")


@unittest.skipUnless(_has("010620"), "HD현대미포 원본 없음")
class TestMipoConflicts(unittest.TestCase):
    """미포 BS연결 은 CZ69(1Q25 매출 가이던스) 등이 미리 채워져 있다 → 충돌로 보고하고 바이트 보존."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kship_xlsx_")
        cls.fins = {"010620": {"stock": "010620", "quarters": ["2025Q1"],
                               "cons": {"bs": {"2025Q1": {"자산총계": 5.0}}, "is": {"2025Q1": {"매출액(수익)": 7.0, "영업이익": 8.0}}},
                               "sep": {"is": {"2025Q1": {"매출액(수익)": 7.0}}}}}
        cls.out = os.path.join(cls.tmp, "mipo.xlsx")
        cls.rep = P.patch_file("010620", cls.fins, "2025Q1", "2026-09-30", out_path=cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_conflicts_reported_and_preserved(self):
        s = {x["sheet"]: x for x in self.rep["sheets"]}["BS연결"]
        self.assertEqual(s["last_actual"], "2024A")
        self.assertEqual(s["new_periods"], ["2025Q1"])
        self.assertEqual(s["columns"], {"2025Q1": "CZ"})
        cells = {c["cell"]: c for c in s["conflicts"]}
        self.assertIn("CZ69", cells)                                   # 매출액(수익) 가이던스 1183800
        self.assertIn("CZ90", cells)                                   # 영업이익 68500
        self.assertEqual(cells["CZ69"]["acct"], "매출액(수익)")
        self.assertIn("CZ5", s["written"])                             # 자산총계는 비어 있었으니 기록
        v = P.verify_unchanged(self.rep["orig"], self.out, self.rep)
        self.assertTrue(v["ok"], v["problems"])
        op = P.load_openpyxl()
        wb = op.load_workbook(self.out, data_only=True, keep_links=False)
        self.assertEqual(wb["BS연결"]["CZ69"].value, 1183800)
        self.assertEqual(wb["BS연결"]["CZ5"].value, 5.0)
        self.assertEqual(wb["BS연결"]["CZ4"].value, 2025.03)
        ws = wb["BS별도"]
        row = next(r for r in range(5, ws.max_row + 1) if ws.cell(r, 3).value == "매출액(수익)")
        self.assertEqual(ws.cell(row, P.col_idx("CZ")).value, 7.0)      # 별도엔 가이던스가 없어 기록됨


class OverwritePlaceholdersTest(unittest.TestCase):
    """--overwrite-placeholders: 값이 있는 셀도 판정 함수가 허락하면 바꾸고 replaced 로 돌려준다.
    공유수식 그룹은 전 셀이 함께 바뀔 때만."""
    ROW = ('<row r="5"><c r="CR5" s="1"><v>1</v></c>'
           '<c r="CS5" s="2"><f t="shared" ref="CS5:CT5" si="0">CR5*2</f><v>2</v></c>'
           '<c r="CT5" s="2"><f t="shared" si="0"/><v>4</v></c>'
           '<c r="CU5" s="3"><v>9</v></c></row>')

    def test_default_keeps_values(self):
        xml, w, conf, repl = P.rebuild_row(self.ROW, 5, {"CU": (5.0, False)})
        self.assertEqual(xml, self.ROW)
        self.assertEqual([c for c, _ in conf], ["CU"])
        self.assertEqual(repl, [])

    def test_overwrite_plain_value(self):
        ok = P.make_overwrite_ok(self.ROW, {"CU5"})
        xml, w, conf, repl = P.rebuild_row(self.ROW, 5, {"CU": (5.0, False)}, ok)
        self.assertIn('<c r="CU5" s="3"><v>5</v></c>', xml)
        self.assertEqual([c for c, _ in repl], ["CU"])
        self.assertEqual(conf, [])

    def test_shared_group_needs_all_cells(self):
        ok = P.make_overwrite_ok(self.ROW, {"CS5"})          # 앵커만 — 의존 CT5 가 고아가 되므로 거부
        xml, w, conf, repl = P.rebuild_row(self.ROW, 5, {"CS": (7.0, False)}, ok)
        self.assertEqual(xml, self.ROW)
        self.assertEqual([c for c, _ in conf], ["CS"])
        ok2 = P.make_overwrite_ok(self.ROW, {"CS5", "CT5"})   # 그룹 전체 → 허용
        xml, w, conf, repl = P.rebuild_row(self.ROW, 5, {"CS": (7.0, False), "CT": (8.0, False)}, ok2)
        self.assertNotIn("t=\"shared\"", xml)
        self.assertEqual(sorted(c for c, _ in repl), ["CS", "CT"])


class SharedFormulaParserTest(unittest.TestCase):
    """공유수식 파서 — 속성 순서·`ca="1"`·단일셀 ref 변형(레퍼런스에 수천 개)을 놓치지 않는다.
    순서를 고정한 정규식(`<f t="shared" ref=".." si="..">`)은 `ref` 와 `si` 사이의 `ca="1"` 을 못 봐 앵커를 놓쳤다."""
    XML = ('<sheetData><row r="3">'
           '<c r="D3" s="1"><f ca="1">OFFSET(D3,0,-1)+1</f><v>1</v></c>'
           '<c r="E3" s="1"><f t="shared" ref="E3:G3" ca="1" si="0">OFFSET(E3,0,-1)+1</f><v>2</v></c>'
           '<c r="F3" s="1"><f t="shared" ca="1" si="0"/><v>3</v></c>'
           '<c r="G3" s="1"><f t="shared" ca="1" si="0"/><v>4</v></c>'
           '<c r="H3" s="1"><f t="shared" ref="H3" si="1">A1</f><v>5</v></c>'
           '<c r="I3" s="1"><f t="shared" si="2"/><v>6</v></c>'
           '</row></sheetData>')

    def test_groups_with_ca_and_single_ref(self):
        g = P.shared_formula_groups(self.XML)
        self.assertEqual(g["0"], {"E3", "F3", "G3"})
        self.assertEqual(g["1"], {"H3"})
        self.assertEqual(g["2"], {"I3"})
        self.assertEqual(P.f_attrs('<f t="shared" ref="E3:G3" ca="1" si="0">X</f>'),
                         {"t": "shared", "ref": "E3:G3", "ca": "1", "si": "0"})
        self.assertIsNone(P.f_attrs("<v>1</v>"))
        # 순서 고정 옛 정규식은 H3(ca 없음)만 보고 E3:G3(ref 와 si 사이에 ca="1") 앵커를 놓친다
        self.assertEqual([m.group(1) for m in re.finditer(r'<f t="shared" ref="([^"]+)" si="\d+"', self.XML)], ["H3"])

    def test_overwrite_ok_respects_ca_group(self):
        ex = {"raw": ""}
        self.assertFalse(P.make_overwrite_ok(self.XML, {"E3"})("E3", ex))                # 앵커만 → 의존 F3·G3 고아
        self.assertTrue(P.make_overwrite_ok(self.XML, {"E3", "F3", "G3"})("E3", ex))
        self.assertTrue(P.make_overwrite_ok(self.XML, {"D3"})("D3", ex))                 # 일반 수식 셀은 그룹 무관

    def test_orphans(self):
        self.assertEqual(P.shared_formula_orphans(self.XML), ["I3"])                     # si=2 앵커 없음
        clean = self.XML.replace('<c r="I3" s="1"><f t="shared" si="2"/><v>6</v></c>', "")
        self.assertEqual(P.shared_formula_orphans(clean), [])


class FxScaleTest(unittest.TestCase):
    FX = {"quarters": {"2005Q1": {"K": 978.75}, "2005Q2": {"K": 1000.0}, "2005Q3": {"K": 900.0}}}
    Q3 = ["2005Q1", "2005Q2", "2005Q3"]

    @staticmethod
    def _cells(vals):
        hdr, cells = {}, {}
        for i, (lab, v) in enumerate(vals.items()):
            col = P.col_letters(4 + i)
            hdr[lab] = col
            cells[col] = {"col": col, "inner": "<v>%r</v>" % v, "t": None}
        return cells, hdr

    def test_scale_candidates(self):
        cells, hdr = self._cells({"1Q05": 9.79, "2Q05": 10.0, "3Q05": 9.0})           # 원/엔 행(라벨은 원/100Y)
        sc = P.fx_row_scale(cells, hdr, self.FX, "K", self.Q3)
        self.assertEqual((sc["scale"], sc["n"]), (0.01, 3))
        cells, hdr = self._cells({"1Q05": 980.0, "2Q05": 1001.0, "3Q05": 899.0})
        self.assertEqual(P.fx_row_scale(cells, hdr, self.FX, "K", self.Q3)["scale"], 1.0)
        cells, hdr = self._cells({"1Q05": 97875.0, "2Q05": 100000.0, "3Q05": 90000.0})
        self.assertEqual(P.fx_row_scale(cells, hdr, self.FX, "K", self.Q3)["scale"], 100.0)

    def test_scale_unresolved_and_median(self):
        cells, hdr = self._cells({"1Q05": 600.0, "2Q05": 600.0, "3Q05": 600.0})       # 비율 0.6 → 후보 밖
        sc = P.fx_row_scale(cells, hdr, self.FX, "K", self.Q3)
        self.assertIsNone(sc["scale"])
        self.assertEqual(sc["n"], 3)
        self.assertEqual(P.fx_row_scale(cells, hdr, self.FX, "K", [])["n"], 0)         # 비교 구간 없음
        self.assertIsNone(P.fx_row_scale(cells, hdr, self.FX, "K", ["2006Q1"])["scale"])   # fx 없음
        cells, hdr = self._cells({"1Q05": 980.0, "2Q05": 1000.0, "3Q05": 540.0})      # 과반 실측이면 소수 가정(0.6) 무시
        self.assertEqual(P.fx_row_scale(cells, hdr, self.FX, "K", self.Q3)["scale"], 1.0)
        self.assertEqual(P._median([3, 1, 2]), 2)
        self.assertEqual(P._median([1, 2, 3, 4]), 2.5)


@unittest.skipUnless(_has("010140") and os.path.exists(SAMPLE) and os.path.exists(FX_JSON), "삼성중공업 원본·표본 fin·fx.json 중 없음")
class FxActualsSamsungTest(unittest.TestCase):
    """--fx-actuals: `변수` 8행 × 새 기간 14열 = 112셀 실측 교체, 원/100Y 행 배율 0.01, 2026Q3~ 가정 보존, partial 보존."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kship_xlsx_")
        with open(SAMPLE, encoding="utf-8") as f:
            cls.fin = json.load(f)
        with open(FX_JSON, encoding="utf-8") as f:
            cls.fx = json.load(f)
        cls.fins = {"010140": cls.fin}
        cls.out = os.path.join(cls.tmp, "shi_fx.xlsx")
        cls.rep = P.patch_file("010140", cls.fins, "2026Q2", "2026-09-30", out_path=cls.out, fx=cls.fx, fx_actuals=True)
        cls.ver = P.verify_all(cls.rep, cls.fins)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_replaced_report(self):
        f = self.rep["fx"]
        self.assertEqual(len(f["replaced"]), 112)
        self.assertEqual((f["filled"], f["skipped_rows"], f["partial_skipped"]), (0, [], []))
        self.assertEqual(set(f["columns"]), set(self.rep["sheets"][0]["new_periods"]))    # BS 새 기간과 동일 범위
        self.assertEqual((f["columns"]["2023Q4"], f["columns"]["2023A"], f["columns"]["2026Q2"]), ("CS", "CT", "DF"))
        sc = f["scale"]
        self.assertEqual([sc[k]["scale"] for k in ("원/달러(평균)", "원/달러(기말)", "W/Euro(평균)", "W/Euro(기말)", "원/중국원(평균)", "원/중국원(기말)")], [1.0] * 6)
        self.assertEqual([sc[k]["scale"] for k in ("원/100Y(평균)", "원/100Y(기말)")], [0.01, 0.01])
        self.assertGreaterEqual(sc["원/달러(평균)"]["n"], 70)
        by = {c["cell"]: c for c in f["replaced"]}
        self.assertEqual(by["CS7"]["was_value"], 1321.2172826086958)                    # 애널리스트 가정 원값이 보고에 남는다
        self.assertIn("<v>1321.2172826086958</v>", by["CS7"]["was"])
        self.assertEqual(by["CS7"]["now"], self.fx["quarters"]["2023Q4"]["USDKRW_avg"])
        self.assertEqual(by["CS9"]["now"], round(self.fx["quarters"]["2023Q4"]["JPY100KRW_avg"] * 0.01, 6))
        self.assertEqual((by["CT7"]["period"], by["CT7"]["now"]), ("2023A", self.fx["annual"]["2023"]["USDKRW_avg"]))
        self.assertEqual(by["DF12"]["now"], self.fx["quarters"]["2026Q2"]["EURKRW_end"])

    def test_readback_and_preserved(self):
        op = P.load_openpyxl()
        ws = op.load_workbook(self.out, data_only=True, keep_links=False)["변수"]
        wso = op.load_workbook(self.rep["orig"], data_only=True, keep_links=False)["변수"]
        self.assertEqual(ws["CS7"].value, self.fx["quarters"]["2023Q4"]["USDKRW_avg"])
        self.assertEqual(ws["DF7"].value, self.fx["quarters"]["2026Q2"]["USDKRW_avg"])
        self.assertEqual(ws["DF8"].value, self.fx["quarters"]["2026Q2"]["USDKRW_end"])
        self.assertAlmostEqual(ws["CS9"].value, self.fx["quarters"]["2023Q4"]["JPY100KRW_avg"] / 100, places=6)
        self.assertEqual(ws["DD7"].value, self.fx["annual"]["2025"]["USDKRW_avg"])
        for ref in ("DG7", "DH7", "DI7", "DJ7", "DG9", "DI14", "CR7", "CQ8", "D7", "CR14"):   # 2026Q3~ 가정·과거 실적 그대로
            self.assertEqual(ws[ref].value, wso[ref].value, ref)
        wf = op.load_workbook(self.out, data_only=False, keep_links=False)["변수"]
        self.assertEqual(wf["DT7"].value, "=DS7")                                        # 2029~ 공유수식 유지

    def test_verify(self):
        v = self.ver
        self.assertTrue(v["all_ok"], v)
        self.assertEqual(v["2_reopen"]["formula_cells_orig"], v["2_reopen"]["formula_cells_patched"])   # 환율 셀은 상수 → 수식 수 불변
        self.assertEqual(len(v["4_unchanged"]["changed_existing_cells"]), 2 + 112)            # C3 두 장 + 환율 112(prices 없음)
        self.assertIn(P.Workbook(self.rep["orig"]).sheets["변수"], v["4_unchanged"]["changed_members"])
        bad = copy.deepcopy(self.rep)                                                    # 보고를 조작하면 ④ 가 잡는다
        bad["fx"]["replaced"].append({"cell": "CR7", "row": "원/달러(평균)", "period": None, "was": "", "was_value": 0, "now": 0, "scale": 1.0})
        r = P.verify_unchanged(self.rep["orig"], self.out, bad)
        self.assertFalse(r["ok"])
        self.assertTrue(any("새 기간 열 밖" in p for p in r["problems"]), r["problems"])

    def test_partial_preserved(self):
        fx = copy.deepcopy(self.fx)
        fx["quarters"]["2026Q2"]["partial"] = True                                       # 진행 중 분기로 가정 → 교체 안 함
        out = os.path.join(self.tmp, "shi_fx_partial.xlsx")
        rep = P.patch_file("010140", self.fins, "2026Q2", "2026-09-30", out_path=out, fx=fx, fx_actuals=True)
        f = rep["fx"]
        self.assertEqual((f["partial_skipped"], len(f["replaced"])), (["2026Q2"], 104))
        self.assertNotIn("2026Q2", f["columns"])
        op = P.load_openpyxl()
        self.assertEqual(op.load_workbook(out, data_only=True, keep_links=False)["변수"]["DF7"].value, 1252.5)

    def test_sst_count_invariant(self):
        """sharedStrings count == 전 시트 t="s" 셀 수 — 원본이 만족하는 불변식을 패치본도 만족(release 회계)."""
        for path in (self.rep["orig"], self.out):
            z = zipfile.ZipFile(path)
            cnt = int(re.search(r'\bcount="(\d+)"', z.read("xl/sharedStrings.xml").decode("utf-8")).group(1))
            refs = sum(len(re.findall(r'<c r="[A-Z]+\d+"[^>]*\st="s"', z.read(n).decode("utf-8")))
                       for n in z.namelist() if n.startswith("xl/worksheets/sheet"))
            self.assertEqual(cnt, refs, path)

    def test_legacy_mode_untouched(self):
        out = os.path.join(self.tmp, "shi_legacy.xlsx")                                  # --fx-actuals 없으면 값 있는 환율 셀 전부 보존
        rep = P.patch_file("010140", self.fins, "2026Q2", "2026-09-30", out_path=out, fx=self.fx)
        self.assertEqual((rep["fx"]["replaced"], rep["fx"]["filled"]), ([], 0))
        self.assertGreater(rep["fx"]["kept"], 800)


if __name__ == "__main__":
    unittest.main()
