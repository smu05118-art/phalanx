#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_fin 계약 테스트 — 네트워크 없이 픽스처 4세트로 파서·분기화·주식수·배당을 검증한다.

실행: cd argus/kship/tools && ~/Library/phalanx_venv/bin/python -m unittest tests.test_kship_fin -v
픽스처: tests/fixtures/fin/ — 삼성중공업 2026Q2(연결·별도·주식)·2025Q4(연결·별도·배당), 세진중공업 2026Q2, 한라IMS 2026Q2.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures", "fin")
sys.path.insert(0, TOOLS)

import kship_fin as F                                      # noqa: E402


def _fx(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def _cur(p, stmt, tag):
    return p[stmt][tag]


class TestNormalize(unittest.TestCase):
    def test_norm_label(self):
        self.assertEqual(F.norm_label("Ⅳ. 발행주식의 총수 (Ⅱ-Ⅲ)"), "발행주식의총수")
        self.assertEqual(F.norm_label("영업이익(손실)"), "영업이익")
        self.assertEqual(F.norm_label("이익잉여금(결손금)"), "이익잉여금")
        self.assertEqual(F.norm_label("　　현금및현금성자산"), "현금및현금성자산")
        self.assertEqual(F.norm_label("매출채권 및 기타 유동 채권"), "매출채권및기타유동채권")
        self.assertEqual(F.norm_label("법인세비용(수익)"), "법인세비용")
        self.assertEqual(F.norm_label("매출채권(주5)"), "매출채권")

    def test_numbers_and_units(self):
        self.assertEqual(F.num_of("(3,034,382)"), -3034382)
        self.assertEqual(F.to_million("(3,034,382)", 1e-6), -3.03)
        self.assertEqual(F.to_million("1,234,567", 0.001), 1234.57)         # 천원 → 백만원
        self.assertEqual(F.unit_mul_of("(단위 : 원)"), 1e-6)
        self.assertEqual(F.unit_mul_of("(단위 : 천원)"), 0.001)
        self.assertEqual(F.unit_mul_of("(단위 : 백만원)"), 1.0)
        self.assertIsNone(F.unit_mul_of("제 53 기 반기말"))

    def test_unit_caption_scales_table(self):
        html = """<p>2-1. 연결 재무상태표</p>
<table><tr><td>연결 재무상태표</td></tr><tr><td>제 3 기 반기말 2026.06.30 현재</td></tr><tr><td>(단위 : 천원)</td></tr></table>
<table><thead><tr><th></th><th>제 3 기 반기말</th><th>제 2 기말</th></tr></thead>
<tr><td>자산</td><td></td><td></td></tr>
<tr><td>유동자산</td><td>1,500,000</td><td>1,000,000</td></tr>
<tr><td>현금및현금성자산</td><td>500,000</td><td>400,000</td></tr>
<tr><td>비유동자산</td><td>2,500,000</td><td>2,000,000</td></tr>
<tr><td>자산총계</td><td>4,000,000</td><td>3,000,000</td></tr>
<tr><td>부채총계</td><td>1,000,000</td><td>900,000</td></tr>
<tr><td>자본총계</td><td>3,000,000</td><td>2,100,000</td></tr></table>"""
        st = F.statements_of(html)
        self.assertEqual(st["bs"]["unit_mul"], 0.001)
        self.assertFalse(st["bs"]["unit_assumed"])
        p = F.parse_fin_section(html)
        self.assertEqual(p["bs"]["cur"]["자산총계"], 4000.0)
        self.assertEqual(p["bs"]["cur"]["현금및현금성자산"], 500.0)
        self.assertEqual(p["bs"]["prev"]["자산총계"], 3000.0)
        self.assertEqual(p["bs"]["cur"]["지배주주지분"], 3000.0)       # 비지배 없음 → 자본총계


class TestSHI2026Q2(unittest.TestCase):
    """삼성중공업 반기보고서(2026.06) 연결 — 4열 손익(3개월/누적), 항등식, 합성 계정."""

    @classmethod
    def setUpClass(cls):
        cls.cons = F.parse_fin_section(_fx("shi_2026Q2_cons.html"))
        cls.sep = F.parse_fin_section(_fx("shi_2026Q2_sep.html"))

    def test_statements_found(self):
        self.assertEqual(self.cons["found"], ["bs", "cf", "cis", "is", "sce"])
        self.assertTrue(self.cons["has_bs"])
        self.assertFalse(self.cons["unit_assumed"])

    def test_is_3m_and_ytd(self):
        q = _cur(self.cons, "is", "cur_q")
        y = _cur(self.cons, "is", "cur_ytd")
        self.assertAlmostEqual(q["매출액(수익)"], 3230712.01, places=2)
        self.assertAlmostEqual(y["매출액(수익)"], 6132962.61, places=2)
        self.assertAlmostEqual(q["영업이익"], 325023.82, places=2)
        self.assertAlmostEqual(q["당기순이익"], 222841.08, places=2)
        self.assertAlmostEqual(q["(지배주주지분)당기순이익"], 224332.62, places=2)
        self.assertAlmostEqual(q["(비지배주주지분)당기순이익"], -1491.54, places=2)
        self.assertAlmostEqual(q["지분법관련손익"], 0.14, places=2)           # '142,112' 원
        self.assertAlmostEqual(_cur(self.cons, "is", "prev_q")["지분법관련손익"], -3.03, places=2)   # '(3,034,382)'
        self.assertAlmostEqual(q["금융손익"], 123413.3 - 152787.27, places=1)
        self.assertAlmostEqual(q["기타영업외손익"], 648223.55 - 643851.68, places=1)
        self.assertEqual(self.cons["eps"]["cur_q"], 263)

    def test_bs_identity_and_synth(self):
        b = _cur(self.cons, "bs", "cur")
        self.assertAlmostEqual(b["자산총계"], 17959382.2, places=1)
        self.assertAlmostEqual(b["자산총계"], b["부채총계"] + b["자본총계"], places=1)
        self.assertAlmostEqual(b["부채와자본총계"], b["자산총계"], places=1)
        self.assertAlmostEqual(b["지배주주지분"], 4771398.4, places=1)
        self.assertAlmostEqual(b["비지배주주지분"], -61044.99, places=1)
        # 총차입금 = 단기차입금 + 유동장기부채 + 사채 + 장기차입금 (리스는 별도 키)
        self.assertAlmostEqual(b["총차입금"], 789943.13 + 5138.33 + 299355.35 + 7707.5, places=1)
        self.assertAlmostEqual(b["순차입금"], b["총차입금"] - b["현금및현금성자산"] - b["단기금융자산"], places=1)
        self.assertAlmostEqual(b["리스부채"], 53447.08 + 179711.06, places=1)
        self.assertAlmostEqual(b["매입채무및기타채무"], 713524.93 + 234052.16 + 487656.23, places=1)
        self.assertEqual(self.cons["raw_labels"]["bs"], [])                   # BS 라벨 전부 매핑

    def test_cf_cumulative(self):
        c = _cur(self.cons, "cf", "cur_full")
        self.assertAlmostEqual(c["영업활동으로인한현금흐름"], 2306934.41, places=1)
        self.assertAlmostEqual(c["유형자산의증가"], 96960.96, places=1)        # '(96,960,957,139)' → 절대값
        self.assertAlmostEqual(c["CAPEX"], 96960.96, places=1)
        self.assertIn("영업으로부터 창출된 현금흐름", [r[0] for r in self.cons["raw_labels"]["cf"]])

    def test_separate(self):
        b, q = _cur(self.sep, "bs", "cur"), _cur(self.sep, "is", "cur_q")
        self.assertAlmostEqual(q["매출액(수익)"], 3224937.5, places=1)
        self.assertAlmostEqual(b["종속기업및관계기업투자"], 288779.63, places=1)
        self.assertEqual(b["지배주주지분"], b["자본총계"])                       # 별도 — 비지배 없음


class TestSHI2025Q4(unittest.TestCase):
    """사업보고서(2025.12) — 연간 3열(당기/전기/전전기)·배당 표·Q4 도출."""

    @classmethod
    def setUpClass(cls):
        cls.cons = F.parse_fin_section(_fx("shi_2025Q4_cons.html"))

    def test_annual_columns(self):
        self.assertEqual(F.statements_of(_fx("shi_2025Q4_cons.html"))["is"]["tags"], ["cur_full", "prev_full", "prev2_full"])
        y = _cur(self.cons, "is", "cur_full")
        self.assertAlmostEqual(y["매출액(수익)"], 10650010.7, places=1)
        self.assertAlmostEqual(y["(지배주주지분)당기순이익"], 545539.6, places=1)
        self.assertAlmostEqual(_cur(self.cons, "is", "prev_full")["매출액(수익)"], 9903077.92, places=1)
        self.assertAlmostEqual(_cur(self.cons, "bs", "cur")["자산총계"], 14948871.09, places=1)
        self.assertNotIn("cur_q", self.cons["is"])

    def test_dividend(self):
        d = F.parse_dividend(_fx("shi_2025Q4_div.html"))
        self.assertEqual(d["term"], 52)
        self.assertEqual(d["dps_common"], 0)                                   # '-' = 무배당
        self.assertEqual(d["cash_div_total_m"], 0)

    def test_q4_derivation_annual_minus_9m(self):
        """Q4 = 연간 − 같은 해 3Q 누적. 3Q 누적은 픽스처에 없으므로 합성한다(연간 − 알려진 Q4)."""
        annual = self.cons
        q4_true = {"매출액(수익)": 2713600.0, "영업이익": 250000.0, "당기순이익": 200000.0}
        ytd9 = {k: round(annual["is"]["cur_full"][k] - q4_true[k], 2) for k in q4_true}
        q3 = {"found": ["bs", "is", "cf"], "bs": {}, "is": {"cur_q": dict(ytd9), "cur_ytd": ytd9},
              "cf": {"cur_full": {"영업활동으로인한현금흐름": 1000000.0, "유형자산의증가": 150000.0}}, "unit_assumed": False}
        per = {"2025Q3": q3, "2025Q4": annual}
        r = F._scope_quarterize("cons", per, ["2025Q3", "2025Q4"])
        self.assertEqual(r["derivation"]["2025Q4"]["is"], "annual_minus_9M")
        self.assertEqual(r["derivation"]["2025Q4"]["cf"], "annual_minus_9M")
        for k, v in q4_true.items():
            self.assertAlmostEqual(r["is"]["2025Q4"][k], v, places=1)
        self.assertAlmostEqual(r["is_ytd"]["2025Q4"]["매출액(수익)"], 10650010.7, places=1)
        self.assertAlmostEqual(r["cf"]["2025Q4"]["영업활동으로인한현금흐름"], 1562848.76 - 1000000.0, places=1)
        self.assertAlmostEqual(r["cf"]["2025Q4"]["유형자산의증가"], 216254.72 - 150000.0, places=1)
        # 항등식 체크가 남는다
        self.assertTrue(any(c["rule"] == "assets=liab+equity" and c["ok"] for c in r["checks"]))

    def test_q4_fallback_prior_year_column(self):
        """3Q 보고서가 없을 때(2021Q4) 다음 해 3Q 보고서의 '전기 누적' 열을 9M 으로 쓴다."""
        annual = self.cons
        q3_next = {"found": ["is"], "bs": {}, "cf": {},
                   "is": {"cur_q": {"매출액(수익)": 1.0}, "cur_ytd": {"매출액(수익)": 3.0},
                          "prev_q": {"매출액(수익)": 1.0}, "prev_ytd": {"매출액(수익)": 8000000.0}}, "unit_assumed": False}
        per = {"2025Q4": annual, "2026Q3": q3_next}
        r = F._scope_quarterize("cons", per, ["2025Q4", "2026Q1", "2026Q2", "2026Q3"])
        self.assertEqual(r["derivation"]["2025Q4"]["is"], "annual_minus_9M(prior_year_col_of_2026Q3)")
        self.assertAlmostEqual(r["is"]["2025Q4"]["매출액(수익)"], 10650010.7 - 8000000.0, places=1)


class TestSejin(unittest.TestCase):
    """세진중공업 — 단일 포괄손익계산서(손익계산서 없음), 별도 매출 83,367, 차입금 미분리(단기/장기금융부채)."""

    @classmethod
    def setUpClass(cls):
        cls.cons = F.parse_fin_section(_fx("sejin_2026Q2_cons.html"))
        cls.sep = F.parse_fin_section(_fx("sejin_2026Q2_sep.html"))

    def test_is_from_cis(self):
        self.assertNotIn("is", self.cons["found"])
        self.assertIn("cis", self.cons["found"])
        self.assertAlmostEqual(_cur(self.sep, "is", "cur_q")["매출액(수익)"], 83367.47, places=2)
        self.assertAlmostEqual(_cur(self.sep, "is", "cur_ytd")["매출액(수익)"], 161531.9, places=1)
        q = _cur(self.cons, "is", "cur_q")
        self.assertAlmostEqual(q["매출액(수익)"], 93498.44, places=2)
        self.assertAlmostEqual(q["(지배주주지분)당기순이익"], 16542.49, places=2)     # 포괄이익 귀속과 섞이지 않는다
        self.assertAlmostEqual(q["(비지배주주지분)당기순이익"], 20623.42 - 16542.49, places=1)
        self.assertAlmostEqual(q["총포괄손익"], 20981.81, places=2)
        self.assertAlmostEqual(q["기타영업외손익"], 381.7, places=2)                  # face 의 '기타손익'

    def test_bs_borrowings_face_label(self):
        """세진은 face 에 '단기금융부채/장기금융부채'(=차입금)만 있다 — FnGuide 관행대로 단기/장기차입금에 넣고 issue 로 표기."""
        b = _cur(self.cons, "bs", "cur")
        self.assertAlmostEqual(b["자산총계"], b["부채총계"] + b["자본총계"], places=1)
        self.assertAlmostEqual(b["단기차입금"], 131281.0, places=1)
        self.assertAlmostEqual(b["장기차입금"], 119500.0, places=1)
        self.assertAlmostEqual(b["단기금융부채"], 2674.43, places=2)          # FnGuide 의미: 리스·파생 등 비차입 금융부채
        issues = []
        F.synth_bs(b, issues, "2026Q2", "cons")
        self.assertAlmostEqual(b["총차입금"], 131281.0 + 119500.0, places=1)
        self.assertEqual(issues[0]["code"], "borrowings_face_label")
        self.assertAlmostEqual(b["확정급여부채"], 6549.88, places=2)
        self.assertAlmostEqual(b["매각예정비유동자산및처분자산"], 986.25, places=2)
        self.assertAlmostEqual(b["기타비유동자산"], 6710.03, places=2)        # 사용권자산 → 기타비유동자산(FnGuide)

    def test_shares(self):
        s = F.parse_shares(_fx("sejin_2026Q2_shares.html"))
        self.assertEqual(s["as_of"], "2026-06-30")
        self.assertEqual(s["issued"], 56849456)
        self.assertEqual(s["treasury"], 0)
        self.assertEqual(s["outstanding"], 56849456)
        self.assertEqual(s["common_issued"], 56849456)
        s2 = F.parse_shares(_fx("shi_2026Q2_shares.html"))
        self.assertEqual(s2["issued"], 880114845)
        self.assertEqual(s2["common_issued"], 880000000)
        self.assertEqual(s2["pref_issued"], 114845)
        self.assertEqual(s2["treasury"], 25964429)
        self.assertEqual(s2["common_outstanding"], 854035571)
        self.assertEqual(s2["outstanding"], 854150416)


class TestHanla(unittest.TestCase):
    """한라IMS — 연결 있음(has_bs), 손익은 포괄손익계산서, 비지배 없음."""

    def test_cons_and_sep(self):
        cons = F.parse_fin_section(_fx("hanla_2026Q2_cons.html"))
        sep = F.parse_fin_section(_fx("hanla_2026Q2_sep.html"))
        self.assertTrue(cons["has_bs"] and sep["has_bs"])
        self.assertAlmostEqual(cons["is"]["cur_q"]["매출액(수익)"], 42836.21, places=2)
        self.assertAlmostEqual(sep["is"]["cur_q"]["매출액(수익)"], 42619.59, places=2)
        self.assertAlmostEqual(cons["is"]["cur_q"]["기타영업외수익"], 3669.56, places=2)   # '기타이익'
        b = cons["bs"]["cur"]
        self.assertAlmostEqual(b["자산총계"], b["부채총계"] + b["자본총계"], places=1)
        self.assertAlmostEqual(b["지배주주지분"], 203915.84, places=1)
        self.assertAlmostEqual(b["총차입금"], 768.22 + 10000.0 + 46333.33, places=1)
        self.assertEqual(cons["eps"]["cur_q"], 489)

    def test_no_consolidation_detected(self):
        """연결 절이 '해당사항 없음' 텍스트만이면 has_bs=False — 연결 유무를 표로 판정한다."""
        p = F.parse_fin_section("<p>2. 연결재무제표</p><p>해당사항 없음</p>")
        self.assertFalse(p["has_bs"])
        self.assertEqual(p["found"], [])


class TestGoldenCompare(unittest.TestCase):
    def test_compare_shapes(self):
        fin = {"stock": "010140", "quarters": ["2023Q3"],
               "cons": {"bs": {"2023Q3": {"자산총계": 100.0, "부채총계": 60.0}}, "is": {"2023Q3": {"매출액(수익)": 50.0}},
                        "is_ytd": {}, "cf": {}, "cf_ytd": {}},
               "sep": {"bs": {}, "is": {}, "is_ytd": {}, "cf": {}, "cf_ytd": {}},
               "shares": {"2023Q3": {"issued": 880114845, "common_issued": 880000000, "common_treasury": 25964429, "pref_issued": 114845}},
               "dividend": {}}
        golden = {"companies": {"010140": {"name": "삼성중공업", "sheets": {"BS연결": {"values": {
            "2023.09": {"자산총계": 105.0, "부채총계": 60.5, "매출액(수익)": 50.0, "토지": 0.0, "무형자산": 7.0,
                        "기말발행주식수(백만주)": 880.115, "보통주기말자기주식수": 25.964}}}}}}}
        r = F.compare_golden(fin, golden)["cons:2023.09"]
        self.assertEqual(r["quarter"], "2023Q3")
        self.assertEqual(r["compared"], 5)
        self.assertEqual(r["match"], 4)                       # 자산총계 100 vs 105 만 ±3 밖(부채총계 0.5 차는 일치)
        self.assertEqual(r["missing"], ["무형자산"])           # 골든 0.0 인 토지는 비교 대상 아님
        self.assertEqual([m["acct"] for m in r["mismatch"]], ["자산총계"])


if __name__ == "__main__":
    unittest.main()


class TestRobustness(unittest.TestCase):
    """실수집에서 드러난 함정 — 법인세 부호, 같은 라벨 반복, 현금흐름 차분 음수, 보조 분기, 골든 주식수 단위."""

    def test_tax_sign_flipped_by_identity(self):
        """미포 2022: '법인세비용(수익)' 에 법인세수익을 양수로 적었다 — 세전−법인세=순이익 항등식으로 뒤집는다."""
        a = {"법인세비용차감전계속사업이익": -63247.65, "법인세비용": 19480.87, "당기순이익": -43766.78}
        flags = []
        F.synth_is(a, flags)
        self.assertAlmostEqual(a["법인세비용"], -19480.87, places=2)
        self.assertEqual(flags[0][0], "tax_sign_flipped")
        b = {"법인세비용차감전계속사업이익": 100.0, "법인세비용": 20.0, "당기순이익": 80.0}
        F.synth_is(b, flags)
        self.assertEqual(b["법인세비용"], 20.0)                          # 정상이면 그대로

    def test_duplicate_bs_label_last_wins(self):
        """동방선기 2022Q1: '매입채무 및 기타유동채무' 두 줄(앞줄이 차입금 포함 소계) — 마지막 값을 쓰고 dups 로 알린다."""
        html = """<table><tr><td>재무상태표</td></tr><tr><td>(단위 : 백만원)</td></tr></table>
<table><thead><tr><th></th><th>제 2 기</th><th>제 1 기</th></tr></thead>
<tr><td>유동부채</td><td>13,000</td><td>1</td></tr>
<tr><td>매입채무 및 기타유동채무</td><td>12,971</td><td>1</td></tr>
<tr><td>매입채무 및 기타유동채무</td><td>4,971</td><td>1</td></tr>
<tr><td>단기차입금</td><td>8,000</td><td>1</td></tr></table>"""
        p = F.parse_fin_section(html)
        self.assertEqual(p["bs"]["cur"]["매입채무및기타채무"], 4971.0)
        self.assertEqual(p["dups"], ["매입채무 및 기타유동채무"])

    def test_cf_abs_negative_dropped(self):
        """누적 차분이 음수인 절대값 계정(재분류)은 버리고 check 실패로 남긴다."""
        q3 = {"found": ["cf"], "bs": {}, "is": {}, "cf": {"cur_full": {"유형자산의증가": 6903.93, "영업활동으로인한현금흐름": 10.0}}, "unit_assumed": False}
        q4 = {"found": ["cf"], "bs": {}, "is": {}, "cf": {"cur_full": {"유형자산의증가": 1693.21, "영업활동으로인한현금흐름": 30.0}}, "unit_assumed": False}
        r = F._scope_quarterize("sep", {"2021Q3": q3, "2021Q4": q4}, ["2021Q3", "2021Q4"])
        self.assertNotIn("유형자산의증가", r["cf"]["2021Q4"])
        self.assertAlmostEqual(r["cf"]["2021Q4"]["영업활동으로인한현금흐름"], 20.0, places=2)
        self.assertTrue(any(c["rule"] == "cf_abs_nonneg:유형자산의증가" and not c["ok"] for c in r["checks"]))

    def test_helper_quarters_and_search_start(self):
        qs = F.q_range("2021Q4", "2022Q2")
        self.assertEqual(F.helper_quarters(qs), ["2021Q3"])
        self.assertEqual(F.helper_quarters(F.q_range("2022Q1", "2022Q4")), [])     # 2022Q3 이 목록에 있다
        self.assertEqual(F.search_start_for(["2021Q3", "2021Q4"]), "20211001")
        self.assertEqual(F.search_start_for(["2021Q4"]), "20220101")

    def test_golden_share_units(self):
        fin = {"stock": "333430", "quarters": ["2023Q3"], "cons": {}, "sep": {"bs": {"2023Q3": {}}, "is": {}, "is_ytd": {}, "cf": {}, "cf_ytd": {}},
               "shares": {"2023Q3": {"issued": 30726747, "common_issued": 30726747, "common_treasury": 0, "pref_issued": 0}}, "dividend": {}}
        golden = {"companies": {"075580": {"name": "세진중공업", "sheets": {"BS일승(별도)": {"values": {"2023.09": {"기말발행주식수(백만주)": 30726747.0, "보통주기말발행주식수": 30726747.0}}}}}}}
        names = {"333430": "일승"}
        sheets = F.golden_sheets_for("333430", golden, names)
        self.assertEqual([s for s, _ in sheets], ["sep"])
        r = F.compare_golden(fin, golden)
        self.assertIsNotNone(r)


class TestExpenseSignAndDiscOps(unittest.TestCase):
    """검증 레인(2026-09-30)에서 잡힌 결함 — 비용 괄호(음수) 표기, 귀속 블록의 계속영업이익, 연간에만 있는 중단영업, KCC 라벨."""

    NEG_IS = """<table><tr><td>연결 손익계산서</td></tr><tr><td>(단위 : 원)</td></tr></table>
<table><thead><tr><th></th><th>제 46 기 1분기 3개월</th><th>제 46 기 1분기 누적</th><th>제 45 기 1분기 3개월</th><th>제 45 기 1분기 누적</th></tr></thead>
<tr><td>매출액</td><td>63,698,885,259</td><td>63,698,885,259</td><td>57,168,377,134</td><td>57,168,377,134</td></tr>
<tr><td>매출원가</td><td>(43,367,412,960)</td><td>(43,367,412,960)</td><td>(39,486,600,561)</td><td>(39,486,600,561)</td></tr>
<tr><td>매출총이익</td><td>20,331,472,299</td><td>20,331,472,299</td><td>17,681,776,573</td><td>17,681,776,573</td></tr>
<tr><td>판매비와관리비</td><td>(9,586,240,940)</td><td>(9,586,240,940)</td><td>(7,790,781,598)</td><td>(7,790,781,598)</td></tr>
<tr><td>영업이익</td><td>10,745,231,359</td><td>10,745,231,359</td><td>9,890,994,975</td><td>9,890,994,975</td></tr>
<tr><td>기타수익</td><td>553,184,168</td><td>553,184,168</td><td>2,346,315,791</td><td>2,346,315,791</td></tr>
<tr><td>기타비용</td><td>(667,716,522)</td><td>(667,716,522)</td><td>(172,751,498)</td><td>(172,751,498)</td></tr>
<tr><td>금융수익</td><td>857,127,359</td><td>857,127,359</td><td>1,095,644,447</td><td>1,095,644,447</td></tr>
<tr><td>금융비용</td><td>(15,875,955)</td><td>(15,875,955)</td><td>(17,755,600)</td><td>(17,755,600)</td></tr>
<tr><td>법인세비용차감전순이익</td><td>11,471,950,409</td><td>11,471,950,409</td><td>13,142,448,115</td><td>13,142,448,115</td></tr>
<tr><td>법인세비용</td><td>(2,290,141,597)</td><td>(2,290,141,597)</td><td>(1,826,036,846)</td><td>(1,826,036,846)</td></tr>
<tr><td>분기순이익</td><td>9,181,808,812</td><td>9,181,808,812</td><td>11,316,411,269</td><td>11,316,411,269</td></tr></table>"""

    def test_negative_expense_convention_flipped(self):
        """성광벤드 2025Q1 원문 그대로 — 괄호 비용을 양수로 뒤집어 매출−원가=GP, GP−판관=OP, 세전−법인세=NI 가 맞아야 한다."""
        p = F.parse_fin_section(self.NEG_IS)
        q = p["is"]["cur_q"]
        self.assertAlmostEqual(q["매출원가"], 43367.41, places=2)
        self.assertAlmostEqual(q["판관비"], 9586.24, places=2)
        self.assertAlmostEqual(q["기타영업외비용"], 667.72, places=2)
        self.assertAlmostEqual(q["금융비용"], 15.88, places=2)
        self.assertAlmostEqual(q["법인세비용"], 2290.14, places=2)
        self.assertAlmostEqual(q["매출액(수익)"] - q["매출원가"], q["매출총이익"], places=1)
        self.assertAlmostEqual(q["매출총이익"] - q["판관비"], q["영업이익"], places=1)
        self.assertAlmostEqual(q["법인세비용차감전계속사업이익"] - q["법인세비용"], q["당기순이익"], places=1)
        self.assertAlmostEqual(q["금융손익"], 857.13 - 15.88, places=1)
        self.assertAlmostEqual(q["기타영업외손익"], 553.18 - 667.72, places=1)
        self.assertAlmostEqual(p["is"]["prev_q"]["매출원가"], 39486.6, places=1)        # 전기 열도 같은 표 관행
        self.assertEqual([f[0] for f in p["flags"]], ["expense_sign_negative"])          # 법인세는 항등식 뒤집기가 아니라 관행 정규화

    def test_positive_convention_untouched(self):
        a = {"매출액(수익)": 100.0, "매출원가": 60.0, "판관비": 20.0, "법인세비용": -3.0}
        self.assertFalse(F.normalize_expense_signs(a))
        self.assertEqual(a["매출원가"], 60.0)
        self.assertEqual(a["법인세비용"], -3.0)                                            # 진짜 법인세수익은 건드리지 않는다
        b = {"매출액(수익)": -5.0, "매출원가": -60.0}
        self.assertFalse(F.normalize_expense_signs(b))                                    # 매출이 양수가 아니면 판정하지 않는다

    def test_q4_mixed_sign_conventions(self):
        """성광벤드 2024: 3Q 분기보고서는 양수, 사업보고서는 괄호 — 각 표에서 정규화한 뒤 Q4 = 연간 − 9M 이 실제 원문 값과 맞아야 한다."""
        annual_html = """<table><tr><td>연결 손익계산서</td></tr><tr><td>(단위 : 원)</td></tr></table>
<table><thead><tr><th></th><th>제 45 기</th><th>제 44 기</th></tr></thead>
<tr><td>매출액</td><td>227,683,121,973</td><td>254,692,907,041</td></tr>
<tr><td>매출원가</td><td>(150,654,590,423)</td><td>(178,533,631,691)</td></tr>
<tr><td>매출총이익</td><td>77,028,531,550</td><td>76,159,275,350</td></tr>
<tr><td>판매비와관리비</td><td>(35,040,442,068)</td><td>(31,325,836,251)</td></tr>
<tr><td>영업이익</td><td>41,988,089,482</td><td>44,833,439,099</td></tr>
<tr><td>법인세비용차감전순이익</td><td>51,532,282,285</td><td>50,672,741,351</td></tr>
<tr><td>법인세비용</td><td>(10,524,759,491)</td><td>(11,503,618,251)</td></tr>
<tr><td>당기순이익</td><td>41,007,522,794</td><td>39,169,123,100</td></tr></table>"""
        q3_html = """<table><tr><td>연결 손익계산서</td></tr><tr><td>(단위 : 원)</td></tr></table>
<table><thead><tr><th></th><th>제 45 기 3분기 3개월</th><th>제 45 기 3분기 누적</th><th>제 44 기 3분기 3개월</th><th>제 44 기 3분기 누적</th></tr></thead>
<tr><td>매출액</td><td>45,396,783,922</td><td>169,452,528,132</td><td>57,769,992,344</td><td>191,324,660,342</td></tr>
<tr><td>매출원가</td><td>29,756,141,793</td><td>107,896,914,351</td><td>40,941,618,925</td><td>133,160,443,489</td></tr>
<tr><td>매출총이익</td><td>15,640,642,129</td><td>61,555,613,781</td><td>16,828,373,419</td><td>58,164,216,853</td></tr>
<tr><td>판매비와관리비</td><td>7,830,721,224</td><td>23,488,400,782</td><td>7,446,693,967</td><td>20,464,267,105</td></tr>
<tr><td>영업이익</td><td>7,809,920,905</td><td>38,067,212,999</td><td>9,381,679,452</td><td>37,699,949,748</td></tr>
<tr><td>법인세비용차감전순이익</td><td>5,810,692,416</td><td>42,298,555,959</td><td>12,343,625,556</td><td>43,553,962,609</td></tr>
<tr><td>법인세비용</td><td>1,667,276,834</td><td>8,780,163,540</td><td>2,872,123,662</td><td>9,791,334,665</td></tr>
<tr><td>분기순이익</td><td>4,143,415,582</td><td>33,518,392,419</td><td>9,471,501,894</td><td>33,762,627,944</td></tr></table>"""
        per = {"2024Q3": F.parse_fin_section(q3_html), "2024Q4": F.parse_fin_section(annual_html)}
        r = F._scope_quarterize("cons", per, ["2024Q3", "2024Q4"])
        q4 = r["is"]["2024Q4"]
        self.assertAlmostEqual(q4["매출액(수익)"], 227683.12 - 169452.53, places=1)
        self.assertAlmostEqual(q4["매출원가"], 150654.59 - 107896.91, places=1)         # 이전엔 −258,551 (연간 음수 − 9M 양수)
        self.assertAlmostEqual(q4["매출액(수익)"] - q4["매출원가"], q4["매출총이익"], places=1)
        self.assertAlmostEqual(q4["매출총이익"] - q4["판관비"], q4["영업이익"], places=1)
        self.assertAlmostEqual(q4["법인세비용차감전계속사업이익"] - q4["법인세비용"], q4["당기순이익"], places=1)
        self.assertTrue(all(c["ok"] for c in r["checks"] if c["rule"] == "pretax-tax=ni"))

    def test_continuing_ops_in_attribution_block(self):
        """세진 FY2023: 총액 '계속영업이익' 줄이 없고 귀속 블록에만 있다(지배주주분 17,757) — 총액은 당기순이익 − 중단영업이익."""
        html = """<table><tr><td>연결 포괄손익계산서</td></tr><tr><td>(단위 : 원)</td></tr></table>
<table><thead><tr><th></th><th>제 25 기</th><th>제 24 기</th></tr></thead>
<tr><td>매출액</td><td>384,796,445,852</td><td>410,053,666,579</td></tr>
<tr><td>법인세비용차감전순이익(손실)</td><td>25,826,040,375</td><td>17,356,908,787</td></tr>
<tr><td>법인세비용(수익)</td><td>2,460,064,241</td><td>3,284,299,665</td></tr>
<tr><td>중단영업이익(손실)</td><td>(635,648,713)</td><td>(715,044,244)</td></tr>
<tr><td>당기순이익(손실)</td><td>22,730,327,421</td><td>13,357,564,878</td></tr>
<tr><td>당기순이익(손실)의 귀속</td><td></td><td></td></tr>
<tr><td>지배기업의 소유주에게 귀속되는 당기순이익(손실)</td><td>17,121,720,198</td><td>11,613,690,743</td></tr>
<tr><td>계속영업이익</td><td>17,757,368,911</td><td>12,328,734,987</td></tr>
<tr><td>중단영업이익</td><td>(635,648,713)</td><td>(715,044,244)</td></tr>
<tr><td>비지배지분에 귀속되는 당기순이익(손실)</td><td>5,608,607,223</td><td>1,743,874,135</td></tr>
<tr><td>계속영업이익</td><td>5,608,607,223</td><td>1,743,874,135</td></tr>
<tr><td>총포괄손익</td><td>22,000,000,000</td><td>13,000,000,000</td></tr></table>"""
        a = F.parse_fin_section(html)["is"]["cur_full"]
        self.assertAlmostEqual(a["중단사업이익"], -635.65, places=2)
        self.assertAlmostEqual(a["계속사업이익"], 22730.33 + 635.65, places=1)          # 23,365.98 = 세전 − 법인세 (골든 FnGuide 방식)
        self.assertAlmostEqual(a["법인세비용차감전계속사업이익"] - a["법인세비용"], a["계속사업이익"], places=1)
        self.assertAlmostEqual(a["(지배주주지분)당기순이익"], 17121.72, places=2)
        self.assertAlmostEqual(a["총포괄손익"], 22000.0, places=1)                     # 귀속 블록 뒤의 포괄손익은 계속 잡힌다

    def test_kcc_half_year_labels(self):
        """KCC 2026Q2: '계속영업반기순이익(손실)'·'중단영업반기순이익(손실)' — (당|반|분)기 가 낀 라벨도 계속/중단사업이익."""
        self.assertEqual(F._entries_for("is", None, F.norm_label("계속영업반기순이익(손실)"))[0], ["계속사업이익"])
        self.assertEqual(F._entries_for("is", None, F.norm_label("중단영업분기순이익"))[0], ["중단사업이익"])
        self.assertEqual(F._entries_for("is", None, "계속영업이익")[0], ["계속사업이익"])
        a = {"법인세비용차감전계속사업이익": 3759350.52, "법인세비용": 916561.61, "계속사업이익": 2842788.91,
             "중단사업이익": -3631.75, "당기순이익": 2839157.16}
        F.synth_is(a, [])
        self.assertAlmostEqual(a["법인세비용차감전계속사업이익"] - a["법인세비용"], a["계속사업이익"], places=1)

    def test_q4_discontinued_only_in_annual(self):
        """한화시스템 2023: 중단영업이 사업보고서에서 처음 분류돼 9M 에 줄이 없다 — Q4 중단 = 연간값, Q4 순이익 = 계속 + 중단."""
        fy = {"found": ["is"], "bs": {}, "cf": {}, "unit_assumed": False,
              "is": {"cur_full": F.synth_is({"법인세비용차감전계속사업이익": 413446.01, "법인세비용": 57394.92, "계속사업이익": 356051.09,
                                              "중단사업이익": -12967.81, "당기순이익": 343083.29})}}
        q3 = {"found": ["is"], "bs": {}, "cf": {}, "unit_assumed": False,
              "is": {"cur_q": {"당기순이익": 1.0}, "cur_ytd": F.synth_is({"법인세비용차감전계속사업이익": 385126.14, "법인세비용": 84289.11,
                                                                            "당기순이익": 300837.04})}}
        r = F._scope_quarterize("cons", {"2023Q3": q3, "2023Q4": fy}, ["2023Q3", "2023Q4"])
        q4 = r["is"]["2023Q4"]
        self.assertEqual(r["derivation"]["2023Q4"]["is"], "annual_minus_9M+disc_ops_annual_only")
        self.assertAlmostEqual(q4["중단사업이익"], -12967.81, places=2)
        self.assertAlmostEqual(q4["계속사업이익"], 356051.09 - 300837.04, places=1)
        self.assertAlmostEqual(q4["계속사업이익"] + q4["중단사업이익"], q4["당기순이익"], places=1)
        chk = [c for c in r["checks"] if c["rule"] == "pretax-tax=ni" and c["quarter"] == "2023Q4"]
        self.assertTrue(chk and chk[0]["ok"], chk)


class TestSharesColumns(unittest.TestCase):
    """KCC 류 '의결권 있는 주식' 열, 종류 머리가 '-' 인 표, 생략 문구 판정."""

    KCC = """<p>가. 주식의 총수 현황</p><table><tr><td>(기준일 :</td><td>2026년 06월 30일</td><td>)</td><td>(단위 : 주, %)</td></tr></table>
<table><thead><tr><th rowspan="2">구 분</th><th colspan="3">주식의 종류</th><th rowspan="2">비고</th></tr>
<tr><th>의결권 있는 주식</th><th>의결권 없는 주식</th><th>합계</th></tr></thead>
<tr><td>Ⅰ. 발행할 주식의 총수</td><td>24,000,000</td><td>-</td><td>24,000,000</td><td>-</td></tr>
<tr><td>Ⅱ. 현재까지 발행한 주식의 총수</td><td>11,286,974</td><td>-</td><td>11,286,974</td><td>-</td></tr>
<tr><td>Ⅲ. 현재까지 감소한 주식의 총수</td><td>2,694,078</td><td>-</td><td>2,694,078</td><td>-</td></tr>
<tr><td>Ⅳ. 발행주식의 총수 (Ⅱ-Ⅲ)</td><td>8,592,896</td><td>-</td><td>8,592,896</td><td>-</td></tr>
<tr><td>Ⅴ. 자기주식수</td><td>1,238,725</td><td>-</td><td>1,238,725</td><td>-</td></tr>
<tr><td>Ⅵ. 유통주식수 (Ⅳ-Ⅴ)</td><td>7,354,171</td><td>-</td><td>7,354,171</td><td>-</td></tr></table>
<p>다. 자기주식 직접 취득ㆍ처분 이행현황</p><p>공시대상기간 중 해당사항 없습니다.</p>"""

    def test_voting_share_columns(self):
        s = F.parse_shares(self.KCC)
        self.assertIsNotNone(s)
        self.assertEqual(s["as_of"], "2026-06-30")
        self.assertEqual((s["issued"], s["treasury"], s["outstanding"]), (8592896, 1238725, 7354171))
        self.assertEqual((s["common_issued"], s["common_treasury"], s["common_outstanding"], s["pref_issued"]), (8592896, 1238725, 7354171, 0))
        self.assertNotIn("col_basis", s)

    def test_dash_headers_positional(self):
        html = """<table><tr><td>(기준일 :</td><td>2022년 03월 31일</td><td>)</td><td>(단위 : 주)</td></tr></table>
<table><thead><tr><th rowspan="2">구 분</th><th colspan="3">주식의 종류</th><th rowspan="2">비고</th></tr>
<tr><th>-</th><th>-</th><th>합계</th></tr></thead>
<tr><td>Ⅰ. 발행할 주식의 총수</td><td>75,000,000</td><td>5,000,000</td><td>80,000,000</td><td>-</td></tr>
<tr><td>Ⅳ. 발행주식의 총수 (Ⅱ-Ⅲ)</td><td>32,446,151</td><td>-</td><td>32,446,151</td><td>-</td></tr>
<tr><td>Ⅴ. 자기주식수</td><td>1,660,200</td><td>-</td><td>1,660,200</td><td>-</td></tr>
<tr><td>Ⅵ. 유통주식수 (Ⅳ-Ⅴ)</td><td>30,785,951</td><td>-</td><td>30,785,951</td><td>-</td></tr></table>"""
        s = F.parse_shares(html)
        self.assertEqual((s["issued"], s["common_issued"], s["outstanding"]), (32446151, 32446151, 30785951))
        self.assertEqual(s["col_basis"], "positional")

    def test_omitted_phrase_not_fooled_by_boilerplate(self):
        self.assertFalse(F.shares_omitted(self.KCC))                                        # '해당사항 없습니다' 는 생략이 아니다
        for t in ("기업공시서식 작성기준에 따라 분기보고서에는 주식의 총수 등을 기재하지 않았습니다.",
                  "분기보고서에는 본 항목을 기재하지 아니하였습니다", "분기보고서의 경우 기재를 생략합니다",
                  "본 항목을 분기보고서에는 작성하지 아니하며, 관련 내용은 사업보고서를 참고",
                  "- 분기보고서의 경우 기재 생략함.(반기/사업보고서에 기재 예정)",
                  "당 분기에 변동사항이 없으며, 관련내용은 2023.3.16에 제출된 2022년도 사업보고서를 참고하시기 바랍니다.",
                  "기업공시서식 작성기준에 의거 분기보고서의 경우 이 항목의 작성을 생략합니다.",
                  "「기업공시서식 작성기준」에 따라 분기보고서의 경우 해당 항목을 기재하지 아니할 수 있습니다"):
            self.assertTrue(F.shares_omitted("<p>4. 주식의 총수 등</p><p>%s</p>" % t), t)


class TestAttributionWithoutHeaderAndOpZone(unittest.TestCase):
    def test_attribution_block_without_header_row(self):
        """세진 FY2023 실제 형식 — '…의 귀속' 머리 없이 '지배기업 소유주지분' 줄부터 귀속이 시작된다."""
        html = """<table><tr><td>연결 포괄손익계산서</td></tr><tr><td>(단위 : 원)</td></tr></table>
<table><thead><tr><th></th><th>제 25 기</th><th>제 24 기</th></tr></thead>
<tr><td>매출액</td><td>384,796,445,852</td><td>410,053,666,579</td></tr>
<tr><td>법인세비용차감전순이익(손실)</td><td>25,826,040,375</td><td>17,356,908,787</td></tr>
<tr><td>법인세비용(수익)</td><td>2,460,064,241</td><td>3,284,299,665</td></tr>
<tr><td>중단영업이익(손실)</td><td>(635,648,713)</td><td>(715,044,244)</td></tr>
<tr><td>당기순이익(손실)</td><td>22,730,327,421</td><td>13,357,564,878</td></tr>
<tr><td>지배기업 소유주지분</td><td>17,121,720,198</td><td>11,613,690,743</td></tr>
<tr><td>계속영업이익</td><td>17,757,368,911</td><td>12,328,734,987</td></tr>
<tr><td>중단영업이익</td><td>(635,648,713)</td><td>(715,044,244)</td></tr>
<tr><td>비지배지분</td><td>5,608,607,223</td><td>1,743,874,135</td></tr>
<tr><td>계속영업이익</td><td>5,608,607,223</td><td>1,743,874,135</td></tr>
<tr><td>총포괄손익</td><td>21,500,630,000</td><td>13,826,380,000</td></tr>
<tr><td>지배기업 소유주지분</td><td>15,593,270,000</td><td>11,786,270,000</td></tr>
<tr><td>계속영업이익</td><td>16,228,920,000</td><td>12,501,310,000</td></tr></table>"""
        a = F.parse_fin_section(html)["is"]["cur_full"]
        self.assertAlmostEqual(a["계속사업이익"], 23365.98, places=1)                       # 세전 25,826 − 법인세 2,460 (FnGuide 와 같은 정의)
        self.assertAlmostEqual(a["(지배주주지분)당기순이익"], 17121.72, places=2)
        self.assertAlmostEqual(a["(비지배주주지분)당기순이익"], 5608.61, places=2)
        self.assertAlmostEqual(a["총포괄손익"], 21500.63, places=2)
        self.assertAlmostEqual(a["법인세비용차감전계속사업이익"] - a["법인세비용"], a["계속사업이익"], places=1)

    def test_op_zone_lines_absorbed_into_sga(self):
        """금강공업 2026Q2: 매출총이익 − 판매관리비 − 물류비 = 영업이익. 물류비는 매핑 규칙에 없어 raw 로 남는데, 잔차가 딱 맞으면 판관비에 더한다."""
        html = """<table><tr><td>연결 포괄손익계산서</td></tr><tr><td>(단위 : 원)</td></tr></table>
<table><thead><tr><th></th><th>제 48 기 반기 3개월</th><th>제 48 기 반기 누적</th></tr></thead>
<tr><td>매출액</td><td>229,092,310,000</td><td>425,759,950,000</td></tr>
<tr><td>매출원가</td><td>(182,845,303,301)</td><td>(340,941,640,668)</td></tr>
<tr><td>매출총이익</td><td>46,247,006,699</td><td>84,818,309,332</td></tr>
<tr><td>판매관리비</td><td>(22,623,570,155)</td><td>(43,686,326,507)</td></tr>
<tr><td>물류비</td><td>(5,633,225,836)</td><td>(9,902,520,015)</td></tr>
<tr><td>영업이익(손실)</td><td>17,990,210,708</td><td>31,229,462,810</td></tr>
<tr><td>대손상각비(환입)</td><td>1,391,858,564</td><td>2,224,012,575</td></tr>
<tr><td>법인세비용차감전순이익</td><td>15,000,000,000</td><td>25,000,000,000</td></tr>
<tr><td>법인세비용</td><td>(3,000,000,000)</td><td>(5,000,000,000)</td></tr>
<tr><td>반기순이익</td><td>12,000,000,000</td><td>20,000,000,000</td></tr></table>"""
        p = F.parse_fin_section(html)
        q = p["is"]["cur_q"]
        self.assertAlmostEqual(q["판관비"], 22623.57 + 5633.23, places=1)
        self.assertAlmostEqual(q["매출총이익"] - q["판관비"], q["영업이익"], places=1)
        self.assertAlmostEqual(p["is"]["cur_ytd"]["판관비"], 43686.33 + 9902.52, places=1)
        self.assertIn("물류비", [r[0] for r in p["raw_labels"]["is"]])                        # 원 라벨은 그대로 남는다
        self.assertIn("sga_absorbed_op_lines", [f[0] for f in p["flags"]])
        self.assertIn("expense_sign_negative", [f[0] for f in p["flags"]])
        # 잔차가 영업비용 구간 줄 합과 맞지 않으면(대손상각비는 영업이익 뒤 = 영업외) 손대지 않는다
        a = {"cur_q": {"매출총이익": 100.0, "판관비": 60.0, "영업이익": 30.0}}
        self.assertEqual(F.absorb_op_zone(a, ["cur_q"], [["기타", 3.0]]), [])
        self.assertEqual(a["cur_q"]["판관비"], 60.0)

    def test_op_zone_reversal_line_signs(self):
        """금강공업 2022Q3: '대손상각비환입(대손상각비)' 935 는 환입(수익)이 양수 — 물류비 4,300 − 환입 935 = 잔차 3,365 로 설명돼야 판관비에 흡수한다."""
        self.assertTrue(F._signs_explain([935.43, 4299.99], 3364.55))
        self.assertTrue(F._signs_explain([-2872.15, 15015.93], 12143.77))
        self.assertFalse(F._signs_explain([3.0], 5.0))
        a = {"cur_q": {"매출총이익": 27513.56, "판관비": 17697.52, "영업이익": 6451.49}}
        r = F.absorb_op_zone(a, ["cur_q"], [["대손상각비환입(대손상각비)", 935.43], ["물류비", 4299.99]])
        self.assertEqual(len(r), 1)
        self.assertAlmostEqual(a["cur_q"]["판관비"], 17697.52 + 3364.55, places=2)
        self.assertAlmostEqual(a["cur_q"]["매출총이익"] - a["cur_q"]["판관비"], a["cur_q"]["영업이익"], places=1)
