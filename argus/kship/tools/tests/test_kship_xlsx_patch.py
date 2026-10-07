#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_xlsx_patch 계약 테스트 — 레퍼런스 subQ xlsx 제자리 패치(MODEL_SPEC 2-6).

실행: cd argus/kship/tools && python3 -m unittest tests.test_kship_xlsx_patch -v
- 순수 함수(기간 순서·라벨·sharedStrings·행 재조립·fin 값 규칙)는 픽스처 없이 돈다.
- 실제 원본(`KSHIP_REFERENCE_DIR/*_orig.xlsx`, 사용자 사유 파일)이 있을 때만
  통합 테스트가 돈다. 출력은 항상 임시 폴더 — 레퍼런스 폴더에 쓰지 않는다.
- 표본 fin: tests/fixtures/fin/fin_sample_010140.json (삼성중공업 2026Q2·2025Q4, 픽스처 HTML 에서 손으로 옮김).
- 세진·미포는 합성 fin(값은 의미 없음) 으로 4시트 매핑·충돌 보존·/U 나눗셈 경로만 확인한다.
"""
import contextlib
import copy
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import unittest.mock
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures", "fin")
sys.path.insert(0, TOOLS)

import kship_xlsx_patch as P  # noqa: E402

REF = P.REF_DIR
SAMPLE = os.path.join(FIX, "fin_sample_010140.json")
FX_JSON = os.path.join(TOOLS, "assets", "fx.json")          # 실측 환율(ECB) — --fx-actuals 통합 테스트용


if not os.path.isdir(REF):                    # 조용한 공허 통과 방지 — 통합 테스트 23건이 왜 건너뛰는지 보이게
    sys.stderr.write("[test_kship_xlsx_patch] 레퍼런스 원본 폴더 없음: %s — 통합 테스트는 건너뜀(KSHIP_REFERENCE_DIR 로 지정)\n" % REF)


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

    def test_is_convention(self):
        """분기 IS: is_ytd_diff 우선(FnGuide 누적차분, MODEL_SPEC 5-4) → 그 계정·분기에 없으면 is → '3m' 은 항상 is.
        BS·연간(is_ytd[Q4]) 은 관행과 무관."""
        fin = {"cons": {"bs": {"2026Q2": {"자산총계": 10.0}},
                        "is": {"2026Q2": {"매출액(수익)": 100.0, "이자수익": 7.0}, "2026Q1": {"매출액(수익)": 90.0}},
                        "is_ytd_diff": {"2026Q2": {"매출액(수익)": 103.0, "이자수익": None}},
                        "is_ytd": {"2025Q4": {"매출액(수익)": 400.0}}}}
        q2 = ("Q", 2026, 2)
        self.assertEqual(P.IS_CONVENTION_DEFAULT, "ytd_diff")
        self.assertEqual(P.value_for(fin, "cons", "매출액(수익)", q2), (103.0, "is_ytd_diff"))
        self.assertEqual(P.value_for(fin, "cons", "이자수익", q2), (7.0, "is"))                # 주석 채움 계정 — 3개월 값만 있다
        self.assertEqual(P.value_for(fin, "cons", "매출액(수익)", ("Q", 2026, 1)), (90.0, "is"))  # 그 분기엔 is_ytd_diff 없음
        self.assertEqual(P.value_for(fin, "cons", "자산총계", q2), (10.0, "bs"))
        self.assertEqual(P.value_for(fin, "cons", "매출액(수익)", q2, is_convention="3m"), (100.0, "is"))
        self.assertEqual(P.value_for(fin, "cons", "매출액(수익)", ("A", 2025)), (400.0, "is_ytd"))
        self.assertEqual(P.value_for(fin, "cons", "매출액(수익)", ("A", 2025), is_convention="3m"), (400.0, "is_ytd"))
        with self.assertRaises(ValueError):
            P.value_for(fin, "cons", "매출액(수익)", q2, is_convention="ytd")
        # 표본 fin(is_ytd_diff 없음) 은 기본 관행에서도 is 로 떨어진다(R1 --build 전 fin 과 호환)
        self.assertEqual(P.value_for(self.fin, "cons", "매출액(수익)", q2), (3230712.01, "is"))


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


@unittest.skipUnless(_has("010140") and os.path.exists(SAMPLE), "삼성중공업 원본 또는 표본 fin 없음")
class TestIsConventionSamsung(unittest.TestCase):
    """표본 fin 에 2026Q2 is_ytd_diff 를 합성해 넣고(매출액 +5.0 = 재작성, 별도 +0.5 = 문턱 이내, 영업이익은 빼서 is 폴백)
    기본 관행(patch_file) 과 3m 관행(CLI --is-convention·--report) 두 번 패치 — 값·restated_cells·⑤사슬·보고 필드."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kship_xlsx_")
        with open(SAMPLE, encoding="utf-8") as f:
            fin = json.load(f)
        cls.is_cons = fin["cons"]["is"]["2026Q2"]["매출액(수익)"]           # 3230712.01
        cls.is_sep = fin["sep"]["is"]["2026Q2"]["매출액(수익)"]             # 3224937.5
        cls.op_cons = fin["cons"]["is"]["2026Q2"]["영업이익"]
        cons_d = copy.deepcopy(fin["cons"]["is"]["2026Q2"])
        cons_d["매출액(수익)"] = round(cls.is_cons + 5.0, 2)                # 1백만원 초과 → 재작성 셀
        cons_d.pop("영업이익")                                              # 누적차분에 없는 계정 → is 폴백
        sep_d = copy.deepcopy(fin["sep"]["is"]["2026Q2"])
        sep_d["매출액(수익)"] = round(cls.is_sep + 0.5, 2)                  # 문턱(RESTATED_TOL=1.0) 이내 → 재작성 아님
        fin["cons"]["is_ytd_diff"] = {"2026Q2": cons_d}
        fin["sep"]["is_ytd_diff"] = {"2026Q2": sep_d}
        cls.fin, cls.fins = fin, {"010140": fin}
        cls.out = os.path.join(cls.tmp, "shi_ytd_diff.xlsx")
        cls.rep = P.patch_file("010140", cls.fins, "2026Q2", "2026-09-30", out_path=cls.out)
        cls.ver = P.verify_all(cls.rep, cls.fins)
        # 3m 관행은 CLI 경로로(--is-convention → patch_file → 보고 JSON)
        cls.fin_path = os.path.join(cls.tmp, "fin_010140.json")
        with open(cls.fin_path, "w", encoding="utf-8") as f:
            json.dump(fin, f, ensure_ascii=False)
        cls.out3 = os.path.join(cls.tmp, "shi_3m.xlsx")
        cls.report3 = os.path.join(cls.tmp, "report_3m.json")
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            cls.rc3 = P.main(["--stock", "010140", "--fin", "010140=" + cls.fin_path,
                              "--fx", os.path.join(cls.tmp, "no_fx.json"), "--prices", os.path.join(cls.tmp, "no_prices.json"),
                              "--out", cls.out3, "--verify", "--is-convention", "3m", "--today", "2026-09-30", "--report", cls.report3])
        cls.stdout3 = buf.getvalue()
        with open(cls.report3, encoding="utf-8") as f:
            cls.rep3 = json.load(f)[0]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @staticmethod
    def _row(ws, acct):
        return next(r for r in range(5, ws.max_row + 1) if ws.cell(r, 3).value == acct)

    def test_default_uses_ytd_diff_and_falls_back(self):
        self.assertTrue(self.rep["written"], self.rep.get("error"))
        self.assertEqual(self.rep["is_convention"], "ytd_diff")
        sheets = {s["sheet"]: s for s in self.rep["sheets"]}
        for s in sheets.values():
            self.assertEqual(s["is_convention"], "ytd_diff")
            self.assertTrue(s["is_ytd_diff_available"])
            self.assertGreater(s["sources"]["is_ytd_diff"], 5)
        self.assertEqual(sheets["BS연결"]["sources"]["is"], 1)             # 영업이익만 폴백(표본 is 는 2026Q2 한 분기)
        self.assertNotIn("is", sheets["BS별도"]["sources"])                # 별도는 전 계정이 누적차분에 있다
        op = P.load_openpyxl()
        wb = op.load_workbook(self.out, data_only=True, keep_links=False)
        ws = wb["BS연결"]
        self.assertEqual(ws["DF69"].value, round(self.is_cons + 5.0, 2))                   # 매출액 = 누적차분 값
        self.assertEqual(ws.cell(self._row(ws, "영업이익"), P.col_idx("DF")).value, self.op_cons)   # 폴백 = 3개월 열
        wss = wb["BS별도"]
        self.assertEqual(wss.cell(self._row(wss, "매출액(수익)"), P.col_idx("DF")).value, round(self.is_sep + 0.5, 2))

    def test_restated_cells(self):
        sheets = {s["sheet"]: s for s in self.rep["sheets"]}
        self.assertEqual(sheets["BS연결"]["restated_cells"],
                         [{"cell": "DF69", "acct": "매출액(수익)", "period": "2026Q2",
                           "is": self.is_cons, "ytd_diff": round(self.is_cons + 5.0, 2), "diff": 5.0}])
        self.assertEqual(sheets["BS별도"]["restated_cells"], [])           # 0.5 는 문턱 이내
        self.assertIn("DF69", sheets["BS연결"]["written"])

    def test_verify_chain_uses_same_convention(self):
        v = self.ver
        self.assertTrue(v["all_ok"], (v["4_unchanged"]["problems"], v["5_chain"]["problems"]))
        got = {(r["table"], c["period"]): c for r in v["5_chain"]["rows"] for c in r["checks"]}
        self.assertEqual(got[("BS연결", "2026Q2")]["value_bs"], round(self.is_cons + 5.0, 2))
        self.assertEqual(got[("BS연결", "2026Q2")]["src"], "is_ytd_diff")
        self.assertEqual(got[("BS별도", "2026Q2")]["src"], "is_ytd_diff")
        self.assertEqual(got[("BS연결", "2025A")]["src"], "is_ytd")           # 연간은 관행 무관
        # 보고 문장에 관행·재작성 셀이 찍힌다
        text = P.summarize(self.rep)
        self.assertIn("IS 관행 ytd_diff(fin.is_ytd_diff 있음)", text)
        self.assertIn("재작성 셀 1", text)
        self.assertIn("≠ DF69 매출액(수익) 2026Q2", text)

    def test_3m_via_cli(self):
        self.assertEqual(self.rc3, 0, self.stdout3)
        self.assertEqual(self.rep3["is_convention"], "3m")
        self.assertTrue(self.rep3["verify"]["all_ok"])
        for s in self.rep3["sheets"]:
            self.assertEqual(s["is_convention"], "3m")
            self.assertNotIn("is_ytd_diff", s["sources"])
            self.assertEqual(s["restated_cells"], [])
        got = {(r["table"], c["period"]): c for r in self.rep3["verify"]["5_chain"]["rows"] for c in r["checks"]}
        self.assertEqual(got[("BS연결", "2026Q2")]["src"], "is")
        op = P.load_openpyxl()
        ws = op.load_workbook(self.out3, data_only=True, keep_links=False)["BS연결"]
        self.assertEqual(ws["DF69"].value, self.is_cons)
        self.assertIn("IS 관행 3m", self.stdout3)


class RefDirTest(unittest.TestCase):
    def test_default_ref_dir(self):
        """레포 기준 후보가 없으면 ~/phalanx 후보로, 둘 다 없으면 첫 후보. 환경변수가 있으면 그것(폴더 유무 무관)."""
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KSHIP_REFERENCE_DIR", None)
            self.assertEqual(P.default_ref_dir(("/nonexistent/x", HERE)), HERE)
            self.assertEqual(P.default_ref_dir((HERE, "/nonexistent/x")), HERE)
            self.assertEqual(P.default_ref_dir(("/nonexistent/x", "/nonexistent/y")), "/nonexistent/x")
        with unittest.mock.patch.dict(os.environ, {"KSHIP_REFERENCE_DIR": "/nonexistent/env"}):
            self.assertEqual(P.default_ref_dir((HERE,)), "/nonexistent/env")


class ExtendFormulaUnitTest(unittest.TestCase):
    """--extend-formulas 순수 함수 — 소스 기간 규칙(같은 분기 위치)·상대참조 치환·수식 셀 XML·합성 시트 연장."""

    def test_source_period_same_position(self):
        L = ("Q", 2023, 3)                                                         # 세진·삼성重: 마지막 실적 3Q23
        self.assertEqual(P.source_period(("Q", 2023, 4), L), ("Q", 2022, 4))       # 4Q23 ← 4Q22
        self.assertEqual(P.source_period(("A", 2023), L), ("A", 2022))             # 2023 ← 2022
        self.assertEqual(P.source_period(("Q", 2024, 1), L), ("Q", 2023, 1))       # 1Q24 ← 1Q23(직전 열이 연간인 구조 유지)
        self.assertEqual(P.source_period(("Q", 2024, 3), L), ("Q", 2023, 3))
        self.assertEqual(P.source_period(("Q", 2026, 2), L), ("Q", 2023, 2))
        M = ("A", 2024)                                                            # 미포: 마지막 실적 2024 연간
        self.assertEqual(P.source_period(("Q", 2025, 1), M), ("Q", 2024, 1))
        self.assertEqual(P.source_period(("A", 2025), M), ("A", 2024))
        Q4 = ("Q", 2024, 4)                                                        # 4Q 까지만 실적 → 연간 열은 목표라 전년
        self.assertEqual(P.source_period(("A", 2024), Q4), ("A", 2023))
        self.assertEqual(P.source_period(("Q", 2025, 2), Q4), ("Q", 2024, 2))

    def test_translate_formula(self):
        t = P.translate_formula
        self.assertEqual(t("VLOOKUP($D13,BS연결,MATCH(SUBQH,BS연결H,0),0)/U", "CS13", "CT13"),
                         "VLOOKUP($D13,BS연결,MATCH(SUBQH,BS연결H,0),0)/U")                # 확정 행: 이름·$D 만 → 텍스트 동일
        self.assertEqual(t("CS80-CS84", "CS81", "CT81"), "CT80-CT84")
        self.assertEqual(t("SUM(CL87:CO87)", "CP87", "CU87"), "SUM(CQ87:CT87)")           # 연간←연간(+5): 분기 4개 범위 유지
        self.assertEqual(t('IF(CN387="","",CS387/CN387-1)', "CS389", "CX389"), 'IF(CS387="","",CX387/CS387-1)')
        self.assertEqual(t("보고서로!AV24", "CS2", "CX2"), "보고서로!BA24")                  # 시트 한정 참조도 이동
        self.assertEqual(t("매출액-34:34", "CS43", "CX43"), "매출액-34:34")                  # 이름·행 범위는 열 이동 무관
        self.assertEqual(t("$CS$5+CS$5+$CS5+LOG10(CS6)", "CS7", "CU8"), "$CS$5+CU$5+$CS6+LOG10(CU7)")   # 함수명 유지·행도 +1
        self.assertEqual(t("OFFSET(E3,0,-1)+1", "E3", "G5"), "OFFSET(G5,0,-1)+1")        # 앵커→다른 행·열의 셀
        with self.assertRaises(ValueError):
            t("A1", "B1", "A1")                                                      # 열 < A

    def test_formula_cell_xml_and_f_text(self):
        self.assertEqual(P.cell_xml("CT", 13, "77", P.Formula('IF(A1<0,"x&y",1)')),
                         '<c r="CT13" s="77"><f>IF(A1&lt;0,"x&amp;y",1)</f></c>')
        self.assertEqual(P.cell_xml("CT", 13, None, P.Formula("CS1")), '<c r="CT13"><f>CS1</f></c>')
        self.assertEqual(P.f_text('<f t="shared" ref="E3:G3" ca="1" si="0">IF(A1&lt;0,&quot;x&amp;y&quot;,1)</f><v>2</v>'),
                         'IF(A1<0,"x&y",1)')
        self.assertIsNone(P.f_text('<f t="shared" si="0"/><v>3</v>'))
        self.assertIsNone(P.f_text("<v>3</v>"))
        xml, w, conf, _ = P.rebuild_row('<row r="5"><c r="CS5" s="1"><f>CR5*2</f><v>2</v></c><c r="CT5" s="1"/></row>', 5,
                                        {"CT": (P.Formula("CS5*2"), False)})
        self.assertEqual(xml, '<row r="5"><c r="CS5" s="1"><f>CR5*2</f><v>2</v></c><c r="CT5" s="1"><f>CS5*2</f></c></row>')
        self.assertEqual(P.Formula("a"), P.Formula("a"))
        self.assertNotEqual(P.Formula("a"), "a")

    # 합성 subQ: 열 E.. = 1Q22 2Q22 3Q22 4Q22 2022 1Q23 2Q23 3Q23 | 4Q23 2023 1Q24 (E F G H I J K L | M N O). 마지막 실적 3Q23.
    SST = ('<sst count="8" uniqueCount="8"><si><t>1Q22</t></si><si><t>2Q22</t></si><si><t>3Q22</t></si><si><t>4Q22</t></si>'
           '<si><t>1Q23</t></si><si><t>2Q23</t></si><si><t>3Q23</t></si><si><t>4Q23</t></si><si><t>1Q24</t></si></sst>')
    SHEET = ('<worksheet><sheetData>'
             '<row r="1"><c r="E1" t="s"><v>0</v></c><c r="F1" t="s"><v>1</v></c><c r="G1" t="s"><v>2</v></c><c r="H1" t="s"><v>3</v></c>'
             '<c r="I1"><v>2022</v></c><c r="J1" t="s"><v>4</v></c><c r="K1" t="s"><v>5</v></c><c r="L1" t="s"><v>6</v></c>'
             '<c r="M1" t="s"><v>7</v></c><c r="N1"><v>2023</v></c><c r="O1" t="s"><v>8</v></c></row>'
             # r5 확정 행(단순 VLOOKUP) — 소스 H·I·J 에 수식, 목표 M·N·O 비어 있음(O 는 스타일만 있는 자리 셀)
             '<row r="5"><c r="H5" s="7"><f>VLOOKUP($D5,BS연결,MATCH(SUBQH,BS연결H,0),0)/U</f><v>1</v></c>'
             '<c r="I5" s="7"><f>VLOOKUP($D5,BS연결,MATCH(SUBQH,BS연결H,0),0)/U</f><v>4</v></c>'
             '<c r="J5" s="7"><f>VLOOKUP($D5,BS연결,MATCH(SUBQH,BS연결H,0),0)/U</f><v>2</v></c><c r="O5" s="9"/></row>'
             # r6 상대참조 수식(분기·연간 구조가 다른 수식)
             '<row r="6"><c r="H6"><f>H5*2</f><v>2</v></c><c r="I6"><f>SUM(E5:H5)</f><v>9</v></c><c r="J6"><f>J5/I5</f><v>0.5</v></c></row>'
             # r7 공유수식 그룹 E7:L7 (앵커 E7, 의존 F7..L7)
             '<row r="7"><c r="E7"><f t="shared" ref="E7:L7" si="0">E5-E6</f><v>1</v></c><c r="F7"><f t="shared" si="0"/><v>1</v></c>'
             '<c r="G7"><f t="shared" si="0"/><v>1</v></c><c r="H7"><f t="shared" si="0"/><v>1</v></c><c r="I7"><f t="shared" si="0"/><v>1</v></c>'
             '<c r="J7"><f t="shared" si="0"/><v>1</v></c><c r="K7"><f t="shared" si="0"/><v>1</v></c><c r="L7"><f t="shared" si="0"/><v>1</v></c></row>'
             # r8 소스가 상수(H8)·수식(I8)·없음(J8)
             '<row r="8"><c r="H8"><v>5</v></c><c r="I8"><f>I5</f><v>4</v></c></row>'
             # r9 목표 M9 에 값이 있음(보존), N9 는 연장, O9 는 소스 없음
             '<row r="9"><c r="H9"><f>H5</f><v>1</v></c><c r="I9"><f>I5</f><v>4</v></c><c r="M9"><v>1</v></c></row>'
             # r10 배열수식 소스
             '<row r="10"><c r="H10"><f t="array" ref="H10">SUM(H5:H6)</f><v>3</v></c></row>'
             '</sheetData></worksheet>')

    class _FakeWB:
        """extend_formulas 가 쓰는 Workbook 표면(sheets·sst·sheet_xml·set_sheet)만."""

        def __init__(self, sheet_xml, sst_xml):
            self.sheets = {"subQ": "xl/worksheets/sheet3.xml"}
            self.sst = P.SharedStrings(sst_xml)
            self._xml, self.saved = sheet_xml, None

        def sheet_xml(self, name):
            return self._xml

        def set_sheet(self, name, xml):
            self.saved = xml

    PERIODS = [("Q", 2023, 4), ("A", 2023), ("Q", 2024, 1)]

    def test_extend_all(self):
        wb = self._FakeWB(self.SHEET, self.SST)
        rep = P.extend_formulas(wb, ("Q", 2023, 3), self.PERIODS, mode="all")
        self.assertIsNone(rep.get("error"))
        self.assertEqual(rep["columns"], {"2023Q4": "M", "2023A": "N", "2024Q1": "O"})
        self.assertEqual(rep["sources"], {"2023Q4": "2022Q4@H", "2023A": "2022A@I", "2024Q1": "2023Q1@J"})
        self.assertEqual((rep["extended"], rep["extended_plain"], rep["extended_shared"], rep["rows"]), (11, 8, 3, 5))
        self.assertEqual((rep["kept_nonempty"], rep["skipped_const"], rep["skipped_array"], rep["skipped_shared"], rep["errors"]), (1, 1, 1, 0, []))
        f = {c["cell"]: c for c in rep["cells"]}
        self.assertEqual(f["M5"]["formula"], "VLOOKUP($D5,BS연결,MATCH(SUBQH,BS연결H,0),0)/U")       # 확정 행: 텍스트 동일
        self.assertEqual((f["M5"]["source"], f["N5"]["source"], f["O5"]["source"]), ("H5", "I5", "J5"))
        self.assertEqual((f["M6"]["formula"], f["N6"]["formula"], f["O6"]["formula"]), ("M5*2", "SUM(J5:M5)", "O5/N5"))   # 연간←연간 +5
        self.assertEqual((f["M7"]["formula"], f["N7"]["formula"], f["O7"]["formula"]), ("M5-M6", "N5-N6", "O5-O6"))      # 앵커 E7 기준 치환
        self.assertEqual(f["M7"]["kind"], "shared")
        self.assertEqual(sorted(c for c in f if c.endswith("8")), ["N8"])                               # M8 상수 소스·O8 소스 없음
        self.assertEqual(sorted(c for c in f if c.endswith("9")), ["N9"])                               # M9 보존·O9 소스 없음
        self.assertNotIn("M10", f)
        xml = wb.saved
        self.assertIn('<c r="J5" s="7"><f>VLOOKUP($D5,BS연결,MATCH(SUBQH,BS연결H,0),0)/U</f><v>2</v></c>'
                      '<c r="M5" s="7"><f>VLOOKUP($D5,BS연결,MATCH(SUBQH,BS연결H,0),0)/U</f></c>'
                      '<c r="N5" s="7"><f>VLOOKUP($D5,BS연결,MATCH(SUBQH,BS연결H,0),0)/U</f></c>'
                      '<c r="O5" s="9"><f>VLOOKUP($D5,BS연결,MATCH(SUBQH,BS연결H,0),0)/U</f></c></row>', xml)   # 자리 셀 O5 는 자기 s
        self.assertIn('<f t="shared" ref="E7:L7" si="0">E5-E6</f>', xml)                                 # 그룹 불변
        self.assertIn('<c r="L7"><f t="shared" si="0"/><v>1</v></c><c r="M7"><f>M5-M6</f></c>', xml)
        self.assertIn('<c r="M9"><v>1</v></c><c r="N9"><f>N5</f></c></row>', xml)
        self.assertEqual(P.CELL_RE.sub("", xml), P.CELL_RE.sub("", self.SHEET))                            # 셀 외 XML 동일
        self.assertEqual(P.shared_formula_orphans(xml), [])

    def test_extend_plain_only_and_errors(self):
        wb = self._FakeWB(self.SHEET, self.SST)
        rep = P.extend_formulas(wb, ("Q", 2023, 3), self.PERIODS, mode="plain")
        self.assertEqual((rep["extended"], rep["extended_plain"], rep["extended_shared"], rep["skipped_shared"]), (8, 8, 0, 3))
        self.assertNotIn("M7", {c["cell"] for c in rep["cells"]})
        with self.assertRaises(ValueError):
            P.extend_formulas(wb, ("Q", 2023, 3), self.PERIODS, mode="shared")
        rep = P.extend_formulas(wb, ("Q", 2023, 3), [("Q", 2027, 1)], mode="all")                     # 행1 에 없는 라벨
        self.assertEqual(rep["error"], "연장할 기간 열 없음")
        self.assertTrue(rep["errors"] and "1Q27" in rep["errors"][0])
        self.assertEqual(P.extend_formulas(wb, ("Q", 2023, 3), self.PERIODS, sheet="없음")["error"], "시트 없음")


class CalcChainUnitTest(unittest.TestCase):
    """calcChain.xml 항목 제거 — `i`(sheetId) 생략 상속·`l` 이월·바이트 보존."""
    CC = ('<?xml version="1.0"?><calcChain xmlns="x"><c r="A1" i="2" l="1"/><c r="B1" i="2"/><c r="CS69" i="13" l="1"/><c r="CT1"/>'
          '<c r="CS90" i="13" s="1"/><c r="D4" i="1" l="1"/></calcChain>')

    def test_entries_inherit_i(self):
        self.assertEqual([(i, r) for i, r, _ in P.calc_chain_entries(self.CC)],
                         [("2", "A1"), ("2", "B1"), ("13", "CS69"), ("13", "CT1"), ("13", "CS90"), ("1", "D4")])

    def test_prune_transfers_i_and_l(self):
        new, pruned = P.prune_calc_chain(self.CC, {"13": {"CS69", "CS90"}})
        self.assertEqual(pruned, [("13", "CS69"), ("13", "CS90")])
        self.assertIn('<c r="CT1" i="13" l="1"/>', new)                               # CT1 이 지운 CS69 의 i·l 을 받는다
        self.assertNotIn('r="CS69"', new)
        self.assertNotIn('r="CS90"', new)
        self.assertEqual([(i, r) for i, r, _ in P.calc_chain_entries(new)], [("2", "A1"), ("2", "B1"), ("13", "CT1"), ("1", "D4")])
        self.assertTrue(new.startswith('<?xml version="1.0"?><calcChain xmlns="x"><c r="A1" i="2" l="1"/><c r="B1" i="2"/>'))
        self.assertTrue(new.endswith('<c r="D4" i="1" l="1"/></calcChain>'))         # s="1" 은 넘기지 않고 D4 는 그대로
        self.assertEqual(P.prune_calc_chain(self.CC, {"13": {"ZZ9"}}), (self.CC, []))  # 없는 셀 → 바이트 그대로
        new, pruned = P.prune_calc_chain(self.CC, {"1": {"D4"}})                       # 마지막 항목 제거 → 이월 없음
        self.assertTrue(new.endswith('<c r="CS90" i="13" s="1"/></calcChain>'))

    def test_sheet_ids(self):
        wb = '<workbook><sheets><sheet name="변수" sheetId="4" r:id="rId1"/><sheet name="BS연결" sheetId="20" r:id="rId13"/></sheets></workbook>'
        self.assertEqual(P.sheet_ids(wb), {"변수": "4", "BS연결": "20"})


def _with_member(src_zip, dst_zip, member, body):
    """zip 복사본에서 멤버 하나만 body(bytes) 로 바꾼다(오류 주입용)."""
    with zipfile.ZipFile(src_zip) as zi, zipfile.ZipFile(dst_zip, "w") as zo:
        for info in zi.infolist():
            data = body if info.filename == member else zi.read(info.filename)
            zo.writestr(info, data)


@unittest.skipUnless(_has("010140") and os.path.exists(SAMPLE), "삼성중공업 원본 또는 표본 fin 없음")
class CalcChainSamsungTest(unittest.TestCase):
    """--overwrite-placeholders 가 바꾼 BS연결 수식 자리표시자 6셀(CS69·CS90·CS140·CS141·CS143·CS144)의 calcChain 항목이 빠진다.
    ⑥ 검사는 보고를 믿지 않고 패치본을 읽어, 항목이 남은 옛 산출(오류 주입)을 잡는다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kship_xlsx_")
        with open(SAMPLE, encoding="utf-8") as f:
            fin = json.load(f)
        accts = {"매출액(수익)": 2433161.03, "영업이익": 78999.08, "법인세비용차감전계속사업이익": -357777.51, "법인세비용": -134138.84,
                 "당기순이익": -223638.67, "(지배주주지분)당기순이익": -223397.6}
        fin["quarters"] = sorted(set(fin["quarters"]) | {"2023Q4"})
        fin["cons"]["is"]["2023Q4"] = dict(accts)                                      # CS 열(4Q23) 자리표시자 6셀
        fin["cons"]["is_ytd"]["2023Q4"] = {k: v * 4 for k, v in accts.items() if k != "법인세비용"}   # CT 열(2023A) 상수 5셀
        cls.fins = {"010140": fin}
        cls.out = os.path.join(cls.tmp, "shi_cc.xlsx")
        cls.rep = P.patch_file("010140", cls.fins, "2026Q2", "2026-10-05", out_path=cls.out, overwrite=True)
        cls.ver = P.verify_all(cls.rep, cls.fins)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_pruned_and_verified(self):
        s = {x["sheet"]: x for x in self.rep["sheets"]}["BS연결"]
        self.assertEqual(sorted(c["cell"] for c in s["replaced"] if "<f" in c["was"]), ["CS140", "CS141", "CS143", "CS144", "CS69", "CS90"])
        cc = self.rep["calc_chain"]
        self.assertTrue(cc["present"])
        self.assertEqual((cc["entries"], cc["requested"], cc["missing"]), (91976, 6, []))
        self.assertEqual(sorted(cc["pruned"]), ["BS연결!CS140", "BS연결!CS141", "BS연결!CS143", "BS연결!CS144", "BS연결!CS69", "BS연결!CS90"])
        v = self.ver["6_calc_chain"]
        self.assertTrue(v["ok"], v["problems"])
        self.assertEqual((v["entries_orig"], v["entries_patched"], v["expected_drop"], v["stale"]), (91976, 91970, 6, []))
        self.assertTrue(self.ver["all_ok"], self.ver)
        self.assertEqual(self.ver["4_unchanged"]["calc_chain_pruned"], 6)
        self.assertEqual(self.ver["2_reopen"]["formula_placeholders_replaced"], 6)
        z = zipfile.ZipFile(self.out)
        self.assertIn(P.CALC_CHAIN, z.namelist())
        ents = {(i, r) for i, r, _ in P.calc_chain_entries(z.read(P.CALC_CHAIN).decode("utf-8"))}
        self.assertNotIn(("13", "CS69"), ents)                                           # BS연결 sheetId=13
        self.assertEqual(len(ents), 91970)

    def test_error_injection_stale_entries_caught(self):
        """옛 산출처럼 calcChain 을 원본 그대로 두면 ⑥ 이 고아 항목 6개를 잡는다(④ 는 잡지 못한다 — 멤버가 원본과 같으므로)."""
        bad = os.path.join(self.tmp, "shi_cc_stale.xlsx")
        _with_member(self.out, bad, P.CALC_CHAIN, zipfile.ZipFile(self.rep["orig"]).read(P.CALC_CHAIN))
        v = P.verify_calc_chain(self.rep["orig"], bad, self.rep)
        self.assertFalse(v["ok"])
        self.assertEqual(sorted(v["stale"]), ["13!CS140", "13!CS141", "13!CS143", "13!CS144", "13!CS69", "13!CS90"])
        self.assertTrue(any("감소 0 ≠" in p for p in v["problems"]), v["problems"])
        self.assertTrue(P.verify_unchanged(self.rep["orig"], bad, self.rep)["ok"])

    def test_error_injection_extra_removal_caught(self):
        """허용 밖 항목(첫 항목)을 하나 더 지우면 ④ 가 '허용 밖 항목 제거' 로 잡는다."""
        cc = zipfile.ZipFile(self.out).read(P.CALC_CHAIN).decode("utf-8")
        first = re.search(r"<c\s+[^>]*?/>", cc).group(0)
        bad = os.path.join(self.tmp, "shi_cc_extra.xlsx")
        _with_member(self.out, bad, P.CALC_CHAIN, cc.replace(first, "", 1).encode("utf-8"))
        v = P.verify_unchanged(self.rep["orig"], bad, self.rep)
        self.assertFalse(v["ok"])
        self.assertTrue(any("허용 밖 항목 제거" in p for p in v["problems"]), v["problems"])


@unittest.skipUnless(_has("010140") and os.path.exists(SAMPLE), "삼성중공업 원본 또는 표본 fin 없음")
class ExtendFormulasSamsungTest(unittest.TestCase):
    """--extend-formulas(all) — 삼성重 subQ: 수식 수가 정확히 연장 수만큼 늘고, 쓴 셀이 재오픈 시 수식이며, 순수 VLOOKUP 셀은
    사슬 흉내 값 == fin, 모든 연장 수식이 openpyxl 의 공유수식 전개(소스 셀) → 목표 치환과 같다(독립 오라클)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kship_xlsx_")
        with open(SAMPLE, encoding="utf-8") as f:
            cls.fin = json.load(f)
        cls.fins = {"010140": cls.fin}
        cls.prices = {"as_of": "2026-10-01", "rows": {"010140": {"close": 19740, "as_of": "20261001",
                      "history_quarterly": {"2026Q2": {"close_end": 23450, "high": 35900, "low": 22200, "avg": 28821.3}}}}}
        cls.out = os.path.join(cls.tmp, "shi_ext.xlsx")
        cls.rep = P.patch_file("010140", cls.fins, "2026Q2", "2026-10-05", out_path=cls.out, prices=cls.prices, extend="all")
        cls.ver = P.verify_all(cls.rep, cls.fins, cls.prices)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_extend_report(self):
        e = self.rep["extend"]
        self.assertEqual(self.rep["extend_mode"], "all")
        self.assertIsNone(e.get("error"))
        self.assertEqual((e["sheet"], e["mode"], e["last_actual"]), ("subQ", "all", "2023Q3"))
        self.assertEqual((e["columns"]["2023Q4"], e["columns"]["2023A"], e["columns"]["2024Q1"], e["columns"]["2026Q2"]), ("CT", "CU", "CV", "DG"))
        self.assertEqual((e["sources"]["2023Q4"], e["sources"]["2023A"], e["sources"]["2024Q1"], e["sources"]["2024Q4"]),
                         ("2022Q4@CO", "2022A@CP", "2023Q1@CQ", "2022Q4@CO"))
        self.assertEqual(e["extended"], 668)                                              # 실측(원본 고정): 단순 381 + 공유앵커 287
        self.assertEqual((e["extended_plain"], e["extended_shared"], e["rows"]), (381, 287, 72))
        self.assertEqual((e["errors"], e["skipped_array"], e["skipped_shared"]), ([], 0, 0))
        self.assertGreater(e["skipped_const"], 0)
        self.assertEqual(e["extended"], len(e["cells"]))
        self.assertEqual(len(e["written"]), e["extended"])
        f = {c["cell"]: c for c in e["cells"]}
        # 삼성重 subQ 의 매출액·영업이익 등 주요 확정 행은 새 기간 열에 애널리스트 추정 수식이 이미 있어 연장 대상이 아니다(kept).
        # 비어 있던 확정 행의 예: 보통주시가총액(최고) r338 — VLOOKUP 텍스트 그대로, 2Q26 ← 2Q23(CR).
        self.assertNotIn("DG27", f)
        self.assertEqual(f["DG338"]["formula"], "VLOOKUP($D338,BS연결,MATCH(YQ,BS연결H,0),0)")
        self.assertEqual((f["DG338"]["source"], f["DG338"]["period"]), ("CR338", "2026Q2"))
        self.assertEqual(f["CU997"]["source"], "CP997")                                        # 2023 연간 ← 2022 연간
        self.assertEqual(f["CT26"]["formula"], "-(CT25-CT27)")                                   # 상대참조 치환(↕ TG 행; 소스 4Q22 는 단순 수식)
        self.assertEqual((f["CT26"]["source"], f["CT26"]["kind"]), ("CO26", "plain"))
        shared = [c for c in e["cells"] if c["kind"] == "shared"]
        self.assertEqual(len(shared), 287)
        self.assertTrue(all(c["formula"] for c in shared))

    def test_verify(self):
        v = self.ver
        self.assertTrue(v["all_ok"], {k: v[k].get("problems") for k in v if isinstance(v[k], dict) and v[k].get("problems")})
        r = v["2_reopen"]
        self.assertEqual((r["formula_cells_extended"], r["formula_placeholders_replaced"]), (668, 0))
        self.assertEqual(r["formula_cells_patched"], r["formula_cells_orig"] + 668)             # subQ 에서만 정확히 +668
        x = v["7_extend"]
        self.assertTrue(x["ok"], x["problems"])
        self.assertEqual((x["cells"], x["formula_ok"], x["formula_bad"], x["mismatch"]), (668, 668, [], []))
        self.assertGreaterEqual(x["checked"], 6)                                               # 시가총액 6행 × 2026Q2(prices 이력) 등
        self.assertEqual(x["matched"], x["checked"])
        self.assertGreater(x["unresolved"], 0)                                                 # 표본 fin 에 없는 계정(주식수 등) → BS 빈칸
        self.assertGreater(x["not_checkable"], 500)                                            # REF-REF 류는 값 검증 대상 아님
        self.assertEqual(v["4_unchanged"]["problems"], [])
        self.assertIn("DG338", self.rep["extend"]["written"])
        self.assertEqual(v["3_patched_cells"]["count"], sum(len(s["written"]) for s in self.rep["sheets"]) + 2 + 668)   # BS 두 장 + 종가 2 + 연장

    def test_readback_and_oracle(self):
        op = P.load_openpyxl()
        from openpyxl.formula.translate import Translator
        wbf = op.load_workbook(self.out, data_only=False, keep_links=False)
        wbo = op.load_workbook(self.rep["orig"], data_only=False, keep_links=False)
        ws, wso = wbf["subQ"], wbo["subQ"]
        self.assertEqual(ws["DG338"].value, "=VLOOKUP($D338,BS연결,MATCH(YQ,BS연결H,0),0)")
        self.assertIsNone(wso["DG338"].value)                                                  # 원본은 비어 있었다
        self.assertEqual(ws["DG27"].value, wso["DG27"].value)                                   # 값이 있던 셀(추정 수식)은 그대로
        bad = 0
        for c in self.rep["extend"]["cells"]:
            src = wso[c["source"]].value                                                        # openpyxl 이 전개한 소스 수식
            self.assertTrue(isinstance(src, str) and src.startswith("="), c)
            if Translator(src, origin=c["source"]).translate_formula(c["cell"])[1:] != c["formula"]:
                bad += 1
            self.assertEqual(ws[c["cell"]].value, "=" + c["formula"])
        self.assertEqual(bad, 0)
        # 새 셀은 캐시값이 없다(fullCalcOnLoad 로 계산) — data_only 는 None
        wbv = op.load_workbook(self.out, data_only=True, keep_links=False)
        self.assertIsNone(wbv["subQ"]["DG338"].value)
        self.assertEqual(wbv["BS연결"]["DF69"].value, 3230712.01)                                  # 사슬의 끝(BS 상수)은 fin 값

    def test_default_off_and_plain_cli(self):
        rep = P.patch_file("010140", self.fins, "2026Q2", "2026-10-05", out_path=os.path.join(self.tmp, "shi_noext.xlsx"))
        self.assertIsNone(rep["extend"])
        self.assertIsNone(rep["extend_mode"])
        r = P.verify_reopen(rep["orig"], rep["out"], rep)
        self.assertTrue(r["ok"], r["diff"])
        self.assertEqual((r["formula_cells_extended"], r["formula_cells_orig"] - r["formula_cells_patched"]), (0, 0))
        fin_path = os.path.join(self.tmp, "fin_010140.json")
        with open(fin_path, "w", encoding="utf-8") as f:
            json.dump(self.fin, f, ensure_ascii=False)
        out = os.path.join(self.tmp, "shi_plain.xlsx")
        report = os.path.join(self.tmp, "report_plain.json")
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = P.main(["--stock", "010140", "--fin", "010140=" + fin_path, "--fx", os.path.join(self.tmp, "no_fx.json"),
                         "--prices", os.path.join(self.tmp, "no_prices.json"), "--out", out, "--verify",
                         "--extend-formulas", "plain", "--today", "2026-10-05", "--report", report])
        self.assertEqual(rc, 0, buf.getvalue())
        with open(report, encoding="utf-8") as f:
            rep3 = json.load(f)[0]
        e = rep3["extend"]
        self.assertEqual((e["mode"], e["extended"], e["extended_shared"], e["skipped_shared"]), ("plain", 381, 0, 287))
        self.assertTrue(rep3["verify"]["7_extend"]["ok"])
        self.assertTrue(rep3["verify"]["all_ok"])
        self.assertEqual(rep3["verify"]["2_reopen"]["formula_cells_extended"], 381)
        self.assertIn("수식 연장 subQ(plain", buf.getvalue())
        self.assertIn("⑦연장 OK", buf.getvalue())

    def _cli_extend(self, tag, *flags):
        fin_path = os.path.join(self.tmp, "fin_010140.json")
        if not os.path.exists(fin_path):
            with open(fin_path, "w", encoding="utf-8") as f:
                json.dump(self.fin, f, ensure_ascii=False)
        out, report = os.path.join(self.tmp, "cli_%s.xlsx" % tag), os.path.join(self.tmp, "cli_%s.json" % tag)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = P.main(["--stock", "010140", "--fin", "010140=" + fin_path, "--fx", os.path.join(self.tmp, "no_fx.json"),
                         "--prices", os.path.join(self.tmp, "no_prices.json"), "--out", out, "--today", "2026-10-05", "--report", report, *flags])
        self.assertEqual(rc, 0, buf.getvalue())
        with open(report, encoding="utf-8") as f:
            return json.load(f)[0]

    def test_cli_extend_default_all_off_disables_bare_flag_all(self):
        """2026-10-08 오너 결정 — 운영 실행(CLI)은 --extend-formulas 를 안 줘도 all, `off` 가 끈다. API patch_file(extend=None) 기본은 꺼짐(위 test_default_off_and_plain_cli)."""
        self.assertEqual((P.EXTEND_CLI_DEFAULT, "off" in P.EXTEND_CLI_MODES), ("all", True))
        rep = self._cli_extend("default")
        self.assertEqual(rep["extend_mode"], "all")
        self.assertEqual((rep["extend"]["extended"], rep["extend"]["extended_shared"]), (668, 287))
        rep = self._cli_extend("bare", "--extend-formulas")
        self.assertEqual((rep["extend_mode"], rep["extend"]["extended"]), ("all", 668))
        rep = self._cli_extend("off", "--extend-formulas", "off")
        self.assertIsNone(rep["extend"])
        self.assertIsNone(rep["extend_mode"])


if __name__ == "__main__":
    unittest.main()
