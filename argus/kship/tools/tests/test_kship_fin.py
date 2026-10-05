#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_fin 계약 테스트 — 네트워크 없이 픽스처 4세트로 파서·분기화·주식수·배당을 검증한다.

실행: cd argus/kship/tools && python3 -m unittest tests.test_kship_fin -v
픽스처: tests/fixtures/fin/ — 삼성중공업 2026Q2(연결·별도·주식)·2025Q4(연결·별도·배당), 세진중공업 2026Q2, 한라IMS 2026Q2,
주석 하위 노드 7개(삼성重·세진 금융수익/차입금/기타수익, 한라IMS 차입금 — 2026Q2 반기보고서 실측),
주석 부모 절 2개(한일철강 002220 2023Q4 `3. 연결재무제표 주석`·`5. 재무제표 주석` — hanil_2023Q4_note_parent_{cons,sep}.html).
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


class TestYtdDiffRestated(unittest.TestCase):
    """누적차분 병기(MODEL_SPEC §5-1) — 3개월 열이 있는 분기도 FnGuide 방식 `is_ytd_diff` 를 함께 두고,
    1백만원 초과로 다른 계정은 `restated` 에 {is, ytd_diff, diff} 로 남긴다. `is` 는 그대로 정본."""

    @staticmethod
    def _per(q1_ytd, q2_q, q2_ytd):
        mk = lambda q, y: {"found": ["is"], "bs": {}, "cf": {}, "unit_assumed": False,          # noqa: E731
                           "is": {"cur_q": dict(q), "cur_ytd": dict(y)}}
        return {"2025Q1": mk(q1_ytd, q1_ytd), "2025Q2": mk(q2_q, q2_ytd)}

    def test_ytd_diff_matches_3m_no_restated(self):
        per = self._per({"매출액(수익)": 100.0, "영업이익": 10.0, "당기순이익": 8.0},
                        {"매출액(수익)": 120.0, "영업이익": 12.0, "당기순이익": 9.0},
                        {"매출액(수익)": 220.0, "영업이익": 22.0, "당기순이익": 17.0})
        r = F._scope_quarterize("cons", per, ["2025Q1", "2025Q2"])
        self.assertEqual(r["is_ytd_diff"]["2025Q1"]["매출액(수익)"], 100.0)          # Q1 = 누적
        self.assertEqual(r["is_ytd_diff"]["2025Q2"]["매출액(수익)"], 120.0)          # Q2 = 누적 − 1Q 누적
        self.assertEqual(r["is"]["2025Q2"]["매출액(수익)"], 120.0)                   # 3개월 열이 정본
        self.assertEqual(r["derivation"]["2025Q2"]["is"], "3m_column")
        self.assertEqual(r["restated"], {})
        ck = [c for c in r["checks"] if c["rule"].startswith("ytd_diff==3m")]
        self.assertEqual(len(ck), 3)
        self.assertTrue(all(c["ok"] for c in ck))

    def test_restated_when_prior_period_rewritten(self):
        """2Q 보고서가 1Q 를 재작성한 경우: 2Q 3개월 열 110 vs 누적차분 220 − 100 = 120 → restated 에 10 차이가 남는다."""
        per = self._per({"매출액(수익)": 100.0, "영업이익": 10.0, "당기순이익": 8.0, "판관비": 5.0},
                        {"매출액(수익)": 110.0, "영업이익": 12.0, "당기순이익": 9.0, "판관비": 6.0},
                        {"매출액(수익)": 220.0, "영업이익": 22.0, "당기순이익": 17.0, "판관비": 11.0})
        r = F._scope_quarterize("cons", per, ["2025Q1", "2025Q2"])
        self.assertEqual(r["is"]["2025Q2"]["매출액(수익)"], 110.0)                   # is 는 손대지 않는다
        self.assertEqual(r["is_ytd_diff"]["2025Q2"]["매출액(수익)"], 120.0)
        rs = r["restated"]["2025Q2"]
        self.assertEqual(rs["매출액(수익)"], {"is": 110.0, "ytd_diff": 120.0, "diff": 10.0})
        self.assertNotIn("영업이익", rs)                                            # 12 == 12
        self.assertNotIn("판관비", rs)                                              # 6 == 6
        bad = [c for c in r["checks"] if c["rule"] == "ytd_diff==3m:매출액(수익)"]
        self.assertEqual(len(bad), 1)
        self.assertFalse(bad[0]["ok"])
        self.assertEqual(bad[0]["diff"], 10.0)

    def test_derived_quarters_identical_to_ytd_diff(self):
        """3개월 열이 없는 분기(Q1·Q4)는 is 가 곧 누적차분이라 둘이 같고 restated 는 비어 있다."""
        cons = F.parse_fin_section(_fx("shi_2025Q4_cons.html"))
        q4_true = {"매출액(수익)": 2713600.0, "영업이익": 250000.0, "당기순이익": 200000.0}
        ytd9 = {k: round(cons["is"]["cur_full"][k] - q4_true[k], 2) for k in q4_true}
        q3 = {"found": ["is"], "bs": {}, "cf": {}, "unit_assumed": False, "is": {"cur_ytd": ytd9}}   # 3개월 열 없음
        r = F._scope_quarterize("cons", {"2025Q3": q3, "2025Q4": cons}, ["2025Q3", "2025Q4"])
        self.assertEqual(r["derivation"]["2025Q4"]["is"], "annual_minus_9M")
        self.assertEqual(r["is"]["2025Q4"], r["is_ytd_diff"]["2025Q4"])
        self.assertIsNot(r["is"]["2025Q4"], r["is_ytd_diff"]["2025Q4"])            # 복사본 — 한쪽을 고쳐도 다른 쪽이 안 변한다
        for k, v in q4_true.items():
            self.assertAlmostEqual(r["is_ytd_diff"]["2025Q4"][k], v, places=1)
        self.assertEqual(r["restated"], {})
        self.assertIn("is_ytd_diff", F.SYNTH_BASIS)


class TestNotes(unittest.TestCase):
    """주석 파싱(MODEL_SPEC §5-1) — 목차 하위 노드 선택, 세 회사 세 형식의 표 파싱, face 에 없을 때만 올리는 규칙, 덩어리 분해."""

    @staticmethod
    def _nodes():
        # 삼성重 2026Q2 목차의 골격(offset 은 실측) — 주석 부모 범위 안의 하위 노드만 골라야 한다
        mk = lambda t, off, ln: {"text": t, "offset": str(off), "length": str(ln), "eleId": "x", "dcmNo": "d", "rcpNo": "r"}   # noqa: E731
        return [mk("III. 재무에 관한 사항", 238399, 3760961),
                mk("2. 연결재무제표", 262439, 181158), mk("2-2. 연결 손익계산서", 310603, 25950),
                mk("3. 연결재무제표 주석", 443601, 1657664),
                mk("6. 범주별 금융상품 (연결)", 746694, 163450), mk("8. 파생금융상품 (연결)", 966851, 472685),
                mk("12. 차입금 및 사채 (연결)", 1603316, 11922), mk("17. 기타수익과 비용 (연결)", 1790277, 36908),
                mk("18. 금융수익과 금융원가 (연결)", 1827185, 33597),
                mk("4. 재무제표", 2101269, 131165),
                mk("5. 재무제표 주석", 2232438, 1641277),
                mk("12. 차입금 및 사채", 3317497, 11840), mk("17. 기타수익과 비용", 3511823, 36632), mk("18. 금융수익과 금융원가", 3548455, 30581),
                mk("7. 증권의 발행을 통한 자금조달에 관한 사항", 3874514, 51552)]

    def test_find_note_nodes_by_parent_range(self):
        f = F.find_note_nodes(self._nodes(), "cons")
        self.assertEqual([n["text"] for n in f["fin"]], ["18. 금융수익과 금융원가 (연결)"])
        self.assertEqual([n["text"] for n in f["borrowings"]], ["12. 차입금 및 사채 (연결)"])
        self.assertEqual([n["text"] for n in f["other"]], ["17. 기타수익과 비용 (연결)"])
        s = F.find_note_nodes(self._nodes(), "sep")
        self.assertEqual([n["text"] for n in s["fin"]], ["18. 금융수익과 금융원가"])          # 별도 주석은 (연결) 꼬리 없는 쪽
        self.assertEqual(sum(len(v) for v in f.values()), 3)
        self.assertLessEqual(sum(len(v) for v in f.values()), F.NOTE_MAX_REQ)

    def test_find_note_nodes_absent(self):
        nodes = [n for n in self._nodes() if "주석" not in n["text"]]
        self.assertEqual(F.find_note_nodes(nodes, "cons"), {})                                  # 부모 없음
        only_parent = [n for n in self._nodes() if n["text"].startswith("3. 연결재무제표 주석")]
        self.assertEqual(F.find_note_nodes(only_parent, "cons"), {})                            # 하위 노드 없음(주석 한 덩어리)

    def test_tag_note_cols(self):
        nlab, tags = F.tag_note_cols(["", "장부금액 공시금액 3개월", "장부금액 공시금액 누적"], "… 금융수익과 금융원가 당반기 (단위 : 천원)")
        self.assertEqual((nlab, tags), (1, [(1, "cur_q"), (2, "cur_ytd")]))
        nlab, tags = F.tag_note_cols(["", "", "장부금액 공시금액 3개월", "장부금액 공시금액 누적"], "전반기 (단위 : 천원)")
        self.assertEqual((nlab, tags), (2, [(2, "prev_q"), (3, "prev_ytd")]))
        nlab, tags = F.tag_note_cols(["구분", "당반기", "전반기"], "")                              # 기간이 머리에 있는 옛 형식
        self.assertEqual((nlab, tags), (1, [(1, "cur_full"), (2, "prev_full")]))
        nlab, tags = F.tag_note_cols(["", "차입금 명칭 A 합계", "차입금 명칭 B 합계", "차입금 명칭 합계"], "당반기말 (단위 : 천원)", prefer_total=True)
        self.assertEqual(tags, [(3, "cur_full")])                                                # 그리드는 마지막 '합계' 열만
        self.assertIsNone(F.tag_note_cols(["", "공시금액"], "")[1] or None)                        # 기간을 어디서도 못 읽으면 태그 없음

    def test_parse_fin_note_shi(self):
        r = F.parse_note_section(_fx("shi_2026Q2_note_fin.html"), "fin")
        self.assertTrue(r["found"])
        self.assertFalse(r["unit_assumed"])
        q = r["acc"]["cur_q"]
        self.assertAlmostEqual(q["이자수익"], 10573.07, places=2)                                  # 10,573,070 천원
        self.assertAlmostEqual(q["파생상품이익"], 50010.49 + 54756.97, places=1)                   # 평가 + 거래
        self.assertAlmostEqual(q["파생상품손실"], 120079.99 + 2898.3, places=1)
        self.assertAlmostEqual(q["금융수익합계"], 123413.3, places=2)
        self.assertAlmostEqual(r["acc"]["cur_ytd"]["이자수익"], 18195.78, places=2)
        self.assertAlmostEqual(r["acc"]["prev_ytd"]["이자비용"], 80134.03, places=2)
        self.assertIn("지급보증료", [l for l, _ in r["raw"]])                                       # 매핑 안 된 줄은 raw

    def test_parse_fin_note_sejin_two_label_columns(self):
        r = F.parse_note_section(_fx("sejin_2026Q2_note_fin.html"), "fin")
        q = r["acc"]["cur_q"]
        self.assertAlmostEqual(q["이자수익"], 731.79, places=2)
        self.assertAlmostEqual(q["배당금수익"], 340.68, places=2)                                  # '배당금수익(금융수익)' 꼬리 제거
        self.assertAlmostEqual(q["외화환산손실"], 14.61, places=2)                                 # '(금융원가)' 꼬리
        self.assertAlmostEqual(q["금융수익합계"], 8207.5, places=2)                                # 구분 합계 줄(금융수익 | 금융수익)
        self.assertAlmostEqual(q["순액"], 6121.03, places=2)                                     # '금융수익(비용)' 은 합계와 섞이지 않는다
        self.assertNotIn("파생상품이익", q)
        self.assertIn("당기손익인식금융자산처분이익(금융수익)", [l for l, _ in r["raw"]])

    def test_parse_other_note(self):
        r = F.parse_note_section(_fx("shi_2026Q2_note_other.html"), "other")
        self.assertAlmostEqual(r["acc"]["cur_q"]["외환차익"], 70096.42, places=2)
        self.assertAlmostEqual(r["acc"]["cur_ytd"]["기타수익합계"], 2349676.86, places=1)
        self.assertIn("확정계약평가이익", [l for l, _ in r["raw"]])
        s = F.parse_note_section(_fx("sejin_2026Q2_note_other.html"), "other")
        self.assertAlmostEqual(s["acc"]["cur_q"]["기타수익합계"], 487.29, places=2)
        self.assertAlmostEqual(s["acc"]["cur_q"]["순액"], 381.7, places=2)                        # face '기타손익' 381.7 과 같다

    def test_parse_borrowings_three_shapes(self):
        h = F.parse_note_section(_fx("hanla_2026Q2_note_borrowings.html"), "borrowings")        # 구성내역 세 줄(단위 원)
        self.assertEqual(h["acc"]["cur_full"], {"단기차입금": 768.22, "유동성장기부채": 10000.0, "장기차입금": 46333.33})
        self.assertEqual(h["acc"]["prev_full"]["장기차입금"], 702.5)
        self.assertIn("장기차입금(유동성포함)", [l for l, _ in h["raw"]])                            # 총액 줄은 매핑하지 않는다
        s = F.parse_note_section(_fx("sejin_2026Q2_note_borrowings.html"), "borrowings")        # 은행별 그리드 + XBRL 표준 라벨
        self.assertEqual(s["acc"]["cur_full"], {"단기차입금": 45801.0, "유동성장기부채": 85480.0, "장기차입금": 119500.0})
        self.assertEqual(s["acc"]["prev_full"]["유동성장기부채"], 79580.0)                          # 장기표의 (79,580,000) 차감 표기 → 절대값
        shi = F.parse_note_section(_fx("shi_2026Q2_note_borrowings.html"), "borrowings")        # 증감표만 — 분해 없음
        self.assertTrue(shi["found"])
        self.assertEqual(shi["acc"], {})
        self.assertIn("기말", [l for l, _ in shi["raw"]])

    def test_inject_is_only_when_face_lacks(self):
        p = F.parse_fin_section(_fx("shi_2026Q2_cons.html"))
        note = F.parse_note_section(_fx("shi_2026Q2_note_fin.html"), "fin")
        face_fin_income = p["is"]["cur_q"]["금융수익"]
        self.assertIsNone(p["is"]["cur_q"].get("이자수익"))
        src = {}
        F.inject_note_is(p, note, src)
        q = p["is"]["cur_q"]
        self.assertAlmostEqual(q["이자수익"], 10573.07, places=2)
        self.assertAlmostEqual(q["이자손익"], 10573.07 - 15343.95, places=1)                      # 재합성
        self.assertEqual(q["금융수익"], face_fin_income)                                          # face 값은 건드리지 않는다
        self.assertEqual(src["이자수익"], "note:fin(3m)")
        self.assertAlmostEqual(p["is"]["prev_ytd"]["이자비용"], 80134.03, places=2)                # 전기 누적도 채운다(Q4 폴백용)
        self.assertNotIn("금융수익합계", q)                                                        # 합계 줄은 올리지 않는다

    def test_inject_is_does_not_create_tags(self):
        p = {"is": {"cur_ytd": {"매출액(수익)": 10.0}}}                                             # 3개월 열이 없는 face
        note = {"acc": {"cur_q": {"이자수익": 1.0}, "cur_ytd": {"이자수익": 2.0}, "cur_full": {"이자수익": 9.0}}}
        src = {}
        F.inject_note_is(p, note, src)
        self.assertEqual(sorted(p["is"]), ["cur_ytd"])                                            # cur_q 를 만들지 않는다
        self.assertEqual(p["is"]["cur_ytd"]["이자수익"], 2.0)
        self.assertEqual(src, {})                                                                 # 3개월 출처가 아니므로 finalize 가 적는다
        p2 = {"is": {"cur_full": {"매출액(수익)": 10.0}}}                                           # 사업보고서 face 에 주석 cur_ytd → cur_full
        F.inject_note_is(p2, {"acc": {"cur_ytd": {"이자수익": 3.0}}}, {})
        self.assertEqual(p2["is"]["cur_full"]["이자수익"], 3.0)

    def test_inject_bs_splits_face_lump(self):
        p = F.parse_fin_section(_fx("sejin_2026Q2_cons.html"))
        b = p["bs"]["cur"]
        self.assertEqual((b["단기차입금"], b["단기금융부채(face)"], b.get("유동성장기부채")), (131281.0, 131281.0, None))
        note = F.parse_note_section(_fx("sejin_2026Q2_note_borrowings.html"), "borrowings")
        src, issues = {}, []
        F.inject_note_bs(b, note, src, issues, "2026Q2", "cons")
        F.synth_bs(b)
        self.assertEqual((b["단기차입금"], b["유동성장기부채"], b["장기차입금"]), (45801.0, 85480.0, 119500.0))
        self.assertNotIn("단기금융부채(face)", b)
        self.assertNotIn("장기금융부채(face)", b)
        self.assertEqual(b["총차입금"], 250781.0)                                                   # 분해 전과 같다
        self.assertEqual(src["유동성장기부채"], "note:borrowings(split of face 단기금융부채)")
        self.assertEqual(issues, [])

    def test_inject_bs_unreconciled_leaves_face(self):
        b = {"단기차입금": 100.0, "단기금융부채(face)": 100.0, "장기차입금": 50.0}
        note = {"acc": {"cur_full": {"단기차입금": 40.0, "유동성장기부채": 50.0, "사채": 7.0}}}       # 40+50 ≠ 100 (리스부채가 섞인 덩어리)
        src, issues = {}, []
        F.inject_note_bs(b, note, src, issues, "2025Q4", "cons")
        self.assertEqual((b["단기차입금"], b["단기금융부채(face)"]), (100.0, 100.0))
        self.assertNotIn("유동성장기부채", b)                                                      # 덩어리를 못 갈랐으면 부분도 넣지 않는다
        self.assertEqual(b["사채"], 7.0)                                                          # face 에 없는 계정은 채운다
        self.assertEqual(src, {"사채": "note:borrowings"})
        self.assertEqual([i["code"] for i in issues], ["borrowings_note_unreconciled"])

    def test_inject_bs_no_op_when_face_has_split(self):
        p = F.parse_fin_section(_fx("hanla_2026Q2_cons.html"))
        b = dict(p["bs"]["cur"])
        note = F.parse_note_section(_fx("hanla_2026Q2_note_borrowings.html"), "borrowings")
        src, issues = {}, []
        F.inject_note_bs(b, note, src, issues, "2026Q2", "cons")
        self.assertEqual(b, p["bs"]["cur"])
        self.assertEqual((src, issues), ({}, []))

    def test_finalize_fills_3m_from_ytd_diff(self):
        """face 에 3개월 열이 없고 주석도 누적만 있으면 3개월 이자수익 = 누적차분(is_ytd_diff) 으로 is 에 채우고 src 에 적는다."""
        q1 = {"found": ["is"], "bs": {}, "cf": {}, "unit_assumed": False, "is": {"cur_ytd": {"매출액(수익)": 100.0, "금융수익": 5.0}}}
        q2 = {"found": ["is"], "bs": {}, "cf": {}, "unit_assumed": False, "is": {"cur_ytd": {"매출액(수익)": 220.0, "금융수익": 12.0}}}
        n1 = {"found": True, "acc": {"cur_ytd": {"이자수익": 3.0, "금융수익합계": 5.0}}, "raw": [], "unit_assumed": False}
        n2 = {"found": True, "acc": {"cur_ytd": {"이자수익": 8.0, "금융수익합계": 12.0}}, "raw": [["지급보증료", {"cur_ytd": 0.5}]], "unit_assumed": False}
        src = {"2025Q1": {}, "2025Q2": {}}
        F.inject_note_is(q1, n1, src["2025Q1"])
        F.inject_note_is(q2, n2, src["2025Q2"])
        r = F._scope_quarterize("cons", {"2025Q1": q1, "2025Q2": q2}, ["2025Q1", "2025Q2"])
        sc = {"is": r["is"], "is_ytd_diff": r["is_ytd_diff"], "bs": r["bs"]}
        self.assertEqual(r["is"]["2025Q2"]["이자수익"], 5.0)                                        # 8 − 3, 도출 경로라 이미 있다
        F.finalize_notes(sc, {"2025Q1": {"fin": n1}, "2025Q2": {"fin": n2}}, src, "cons")
        self.assertEqual(sc["notes"]["fin"]["2025Q2"]["이자수익"], 5.0)
        self.assertEqual(sc["notes"]["fin"]["2025Q2"]["basis"], "ytd_diff")
        self.assertEqual(sc["notes"]["fin"]["2025Q2"]["ytd"], {"이자수익": 8.0})
        self.assertEqual(sc["notes"]["fin"]["2025Q2"]["totals"], {"금융수익합계": 12.0})
        self.assertEqual(sc["notes"]["fin"]["2025Q2"]["raw"], [["지급보증료", None, 0.5]])
        # face 3개월 열은 있는데(다른 계정만) 주석은 누적만 — is 에 없던 이자수익을 누적차분으로 채운다
        q2b = {"found": ["is"], "bs": {}, "cf": {}, "unit_assumed": False,
               "is": {"cur_q": {"매출액(수익)": 120.0, "금융수익": 7.0}, "cur_ytd": {"매출액(수익)": 220.0, "금융수익": 12.0}}}
        src2 = {"2025Q1": {}, "2025Q2": {}}
        F.inject_note_is(q1, n1, src2["2025Q1"])
        F.inject_note_is(q2b, n2, src2["2025Q2"])
        r2 = F._scope_quarterize("cons", {"2025Q1": q1, "2025Q2": q2b}, ["2025Q1", "2025Q2"])
        self.assertIsNone(r2["is"]["2025Q2"].get("이자수익"))
        sc2 = {"is": r2["is"], "is_ytd_diff": r2["is_ytd_diff"], "bs": r2["bs"]}
        F.finalize_notes(sc2, {"2025Q1": {"fin": n1}, "2025Q2": {"fin": n2}}, src2, "cons")
        self.assertEqual(sc2["is"]["2025Q2"]["이자수익"], 5.0)
        self.assertEqual(sc2["src_notes"]["2025Q2"]["이자수익"], "note:fin(ytd_diff)")
        self.assertEqual(sc2["notes"]["fin"]["2025Q2"]["basis"], "ytd_diff")                     # basis 는 주석 값의 경로 — 표에 3개월 열이 없었다

    def test_build_company_with_notes_cache(self):
        """캐시(2026Q2 주석 포함)로 build — is/bs 에 주석 계정이 올라오고 notes/src_notes 가 스키마대로 생긴다."""
        import json
        import shutil
        import tempfile
        from unittest import mock

        assets = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.multiple(F, ASSETS=assets, FIN_CACHE=os.path.join(assets, "fin_cache")))
        # 추적된 원문 픽스처를 임시 캐시에 복사한다. meta 는 테스트용 경로 인덱스다.
        for stock, prefix, note_keys in (("010140", "shi", ("fin", "borrowings", "other")),
                                         ("075580", "sejin", ("fin", "borrowings", "other")),
                                         ("092460", "hanla", ("borrowings",))):
            paths = F.cache_paths(stock, "2026Q2")
            os.makedirs(os.path.dirname(paths["meta"]))
            meta = {"rcp": "fixture", "sections": {}, "notes": {"scope": "cons", "items": {}}}
            for scope in ("cons", "sep"):
                shutil.copyfile(os.path.join(FIX, "%s_2026Q2_%s.html" % (prefix, scope)), paths[scope])
                meta["sections"][scope] = {"path": os.path.relpath(paths[scope], assets)}
            for key in note_keys:
                path = F.note_cache_path(stock, "2026Q2", key)
                shutil.copyfile(os.path.join(FIX, "%s_2026Q2_note_%s.html" % (prefix, key)), path)
                meta["notes"]["items"][key] = {"path": os.path.relpath(path, assets)}
            with open(paths["meta"], "w", encoding="utf-8") as f:
                json.dump(meta, f)

        fin = F.build_company("010140", ["2026Q2"], "삼성중공업", golden={})
        c = fin["cons"]
        self.assertAlmostEqual(c["is"]["2026Q2"]["이자수익"], 10573.07, places=2)
        self.assertEqual(c["src_notes"]["2026Q2"]["이자수익"], "note:fin(3m)")
        self.assertEqual(c["notes"]["fin"]["2026Q2"]["basis"], "3m_column")
        self.assertEqual(c["notes"]["borrowings"]["2026Q2"]["단기차입금"], None)                   # 증감표만 — face 그대로
        self.assertIn("note_unmapped:borrowings", [i["code"] for i in fin["issues"]])
        self.assertEqual(fin["reports"]["2026Q2"]["notes"]["scope"], "cons")
        self.assertEqual(sorted(fin["reports"]["2026Q2"]["notes"]["items"]), ["borrowings", "fin", "other"])
        sj = F.build_company("075580", ["2026Q2"], "세진중공업", golden={})
        b = sj["cons"]["bs"]["2026Q2"]
        self.assertEqual((b["단기차입금"], b["유동성장기부채"], b["장기차입금"], b["총차입금"]), (45801.0, 85480.0, 119500.0, 250781.0))
        self.assertNotIn("단기금융부채(face)", b)
        self.assertEqual(sj["cons"]["is"]["2026Q2"]["배당금수익"], 340.68)
        self.assertEqual(sj["sep"]["bs"]["2026Q2"]["단기금융부채(face)"], 74070.0)                 # 별도 주석은 안 받았다 — 그대로
        hl = F.build_company("092460", ["2026Q2"], "한라IMS", golden={})
        codes = [i["code"] for i in hl["issues"] if i["quarter"] == "2026Q2"]
        self.assertIn("note_missing:fin", codes)
        self.assertIn("note_missing:other", codes)
        self.assertEqual(hl["cons"]["src_notes"], {})


class TestNoteParent(unittest.TestCase):
    """주석 부모 절 폴백 — 하위 노드가 없는 보고서(999 중 786)의 `3. 연결재무제표 주석` 한 덩어리를 블록으로 잘라 같은 파서에 넘긴다.
    픽스처: 한일철강(002220) 2023Q4 사업보고서 `3. 연결재무제표 주석`(356KB)·`5. 재무제표 주석`(341KB) — DART 뷰어 실물."""

    @classmethod
    def setUpClass(cls):
        cls.cons_html = _fx("hanil_2023Q4_note_parent_cons.html")
        cls.sep_html = _fx("hanil_2023Q4_note_parent_sep.html")
        cls.cons = F.parse_note_parent(cls.cons_html)
        cls.sep = F.parse_note_parent(cls.sep_html)

    # ── 블록 분할 ──
    def test_split_blocks_hanil(self):
        bl = F.split_note_blocks(self.cons_html)
        self.assertEqual(len(bl), 39)                                                           # 1. 연결회사의 개요 … 39. 우발채무 및 약정사항
        self.assertEqual([b["no"] for b in bl], [str(i) for i in range(1, 40)])
        by = {b["no"]: b["title"] for b in bl}
        self.assertEqual(by["22"], "차입금")
        self.assertEqual(by["32"], "금융수익 및 금융비용")
        self.assertEqual(by["33"], "기타수익 및 기타비용")
        self.assertEqual(by["7"], "범주별 금융상품")
        self.assertNotIn("3.15", by)                                                            # 회계정책 소절은 블록이 아니다
        self.assertTrue(bl[31]["html"].lstrip().startswith("32. 금융수익"))
        self.assertNotIn("33. 기타수익", bl[31]["html"])                                          # 다음 머리 직전까지만
        self.assertEqual(len(F.split_note_blocks(self.sep_html)), 39)
        self.assertEqual((self.cons["mode"], self.cons["blocks"]), ("heading", 39))

    def test_split_joins_span_split_heading(self):
        """삼성重 2021Q4 처럼 머리가 `<SPAN>21. 차</SPAN><SPAN>입금</SPAN>` 으로 쪼개져 있어도 한 줄로 읽는다."""
        html = ("<P>1. 일반사항</P><P>2. 회계정책</P><P>3.9 차입원가</P>"
                "<P><SPAN>3. 차</SPAN><SPAN></SPAN><SPAN>입금</SPAN><SPAN>&nbsp;및 사채</SPAN><BR/></P><P>본문</P>"
                "<P>4. 금융수익과 원가</P>")
        bl = F.split_note_blocks(html)
        self.assertEqual([(b["no"], b["title"]) for b in bl],
                         [("1", "일반사항"), ("2", "회계정책"), ("3", "차입금 및 사채"), ("4", "금융수익과 원가")])

    # ── 블록 선택·매핑(한일철강 실측 값) ──
    def test_picked_blocks_hanil(self):
        self.assertEqual(self.cons["picked"], {"fin": ["32. 금융수익 및 금융비용"], "borrowings": ["22. 차입금"],
                                               "other": ["33. 기타수익 및 기타비용"]})
        self.assertEqual(self.sep["picked"], self.cons["picked"])
        # `7. 범주별 금융상품` 에도 `이자수익(비용)` 줄이 있지만 금융수익 블록이 이기고(순위), 그 줄은 정확히 `이자수익` 이 아니다

    def test_fin_values_hanil_cons(self):
        f = self.cons["notes"]["fin"]
        self.assertFalse(f["unit_assumed"])
        c = f["acc"]["cur_full"]                                                                # 사업보고서 — 당기/전기 열(단위 : 원)
        self.assertEqual(c["이자수익"], 805.72)                                                   # 805,716,022 원
        self.assertEqual(c["이자비용"], 6047.39)                                                  # 6,047,387,835 원
        self.assertEqual(c["외환차익"], 24.25)
        self.assertEqual(c["외화환산손실"], 469.03)
        self.assertEqual(c["금융수익합계"], 2143.14)                                               # '금융수익 계'
        self.assertEqual(c["금융비용합계"], 6607.44)
        self.assertEqual(f["acc"]["prev_full"]["이자수익"], 591.48)
        self.assertEqual(f["acc"]["prev_full"]["외환차익"], -174.56)                               # 원문 (174,557,787) 그대로
        self.assertGreaterEqual(len([k for k in c if k in F.NOTE_FIN_ACCTS]), 6)
        self.assertNotIn("파생상품손실", c)                                                       # '통화스왑평가손실' 은 raw 로
        self.assertIn("통화스왑평가손실", [l for l, _ in f["raw"]])

    def test_borrowings_values_hanil(self):
        b = self.cons["notes"]["borrowings"]["acc"]
        # (1) 단기차입금 은행별 표 마지막 `합 계` 79,006,063,600 / (2) 장기차입금 표 `유동성 장기부채 대체 (20,494,000,000)`
        self.assertEqual(b["cur_full"], {"단기차입금": 79006.06, "유동성장기부채": 20494.0})
        self.assertEqual(b["prev_full"], {"단기차입금": 93382.91, "장기차입금": 16494.0})        # 전기말 `장기차입금 잔 액`
        # (3) 상환계획 합계 99,500,063,600 = 단기 + 유동성 — 분해가 원문과 맞는다
        self.assertAlmostEqual(b["cur_full"]["단기차입금"] + b["cur_full"]["유동성장기부채"], 99500.06, places=2)
        s = self.sep["notes"]["borrowings"]["acc"]["cur_full"]                                   # 별도는 단기표 마지막 줄이 `소 계`
        self.assertEqual(s, {"단기차입금": 77559.34, "유동성장기부채": 20494.0})

    def test_sep_and_other_hanil(self):
        c = self.sep["notes"]["fin"]["acc"]["cur_full"]
        self.assertEqual((c["이자수익"], c["배당금수익"], c["이자비용"]), (800.44, 60.92, 5926.64))
        o = self.cons["notes"]["other"]["acc"]["cur_full"]
        self.assertEqual(o, {"기타수익합계": 2875.29, "기타비용합계": 1998.05})

    # ── 안전장치 ──
    @staticmethod
    def _doc(*blocks):
        tbl = ("<TABLE><THEAD><TR><TH>구분</TH><TH>당기</TH><TH>전기</TH></TR></THEAD><TBODY>%s</TBODY></TABLE>")
        out = []
        for head, rows in blocks:
            body = "".join("<TR><TD>%s</TD><TD>%s</TD><TD>%s</TD></TR>" % r for r in rows)
            out.append("<P>%s</P><P>(단위 : 백만원)</P>%s" % (head, tbl % body if rows else ""))
        return "".join(out)

    def test_title_priority_and_row_check(self):
        html = self._doc(("1. 일반사항", []),
                         ("2. 금융상품 공정가치", [("이자수익", "99,999", "99,999")]),             # 순위 2 — 더 좋은 블록이 있으면 안 쓴다
                         ("3. 금융손익", [("이자수익", "50,000", "40,000"), ("이자비용", "70,000", "60,000")]),
                         ("4. 금융수익과 금융원가", [("배당금수익", "5,000", "4,000")]),           # 순위 0 이지만 이자 줄 없음 → 탈락
                         ("5. 차입금", [("은행 A", "10,000", "10,000")]),                          # 차입 줄 없음 → 탈락
                         ("6. 기타수익과 기타비용", [("기타수익 합계", "3,000", "2,000")]))
        r = F.parse_note_parent(html)
        self.assertEqual(r["picked"]["fin"], ["3. 금융손익"])
        self.assertEqual(r["notes"]["fin"]["acc"]["cur_full"], {"이자수익": 50000.0, "이자비용": 70000.0})
        self.assertNotIn("borrowings", r["notes"])
        self.assertEqual(r["picked"]["other"], ["6. 기타수익과 기타비용"])

    def test_two_fin_blocks_merged_without_double_count(self):
        html = self._doc(("1. 일반사항", []), ("2. 금융수익", [("이자수익", "50,000", "40,000")]),
                         ("3. 금융원가", [("이자비용", "70,000", "60,000"), ("이자수익", "1,000", "1,000")]), ("4. 법인세", []))
        r = F.parse_note_parent(html)
        self.assertEqual(r["picked"]["fin"], ["2. 금융수익", "3. 금융원가"])                      # fin 은 ≤2 블록
        self.assertEqual(r["notes"]["fin"]["acc"]["cur_full"], {"이자수익": 50000.0, "이자비용": 70000.0})   # 먼저 나온 값이 이긴다

    def test_instruments_block_grid_rejected(self):
        """세진 2022Q4 `5. 범주별 금융상품` 처럼 범주별 열 그리드(첫 열만 읽힌다)·음수 비용이면 금융상품 블록을 fin 으로 쓰지 않는다."""
        grid = ("<P>1. 일반사항</P><P>2. 회사 개요</P><P>3. 범주별 금융상품</P><P>당기 (단위: 천원)</P>"
                "<TABLE><THEAD><TR><TH>구 분</TH><TH>상각후원가 측정 금융자산</TH><TH>FVOCI 금융자산</TH><TH>합 계</TH></TR></THEAD>"
                "<TBODY><TR><TD>이자수익</TD><TD>836,826</TD><TD>442,734</TD><TD>1,279,560</TD></TR>"
                "<TR><TD>이자비용</TD><TD>(9,397,278)</TD><TD>-</TD><TD>(9,397,278)</TD></TR></TBODY></TABLE><P>4. 법인세</P>")
        self.assertNotIn("fin", F.parse_note_parent(grid)["notes"])
        single = self._doc(("1. 일반사항", []), ("2. 회사 개요", []),
                           ("3. 범주별 금융상품", [("이자수익", "27,000", "18,900"), ("이자비용", "159,700", "111,700")]), ("4. 법인세", []))
        r = F.parse_note_parent(single)                                                         # 기간별 열 하나·양수 비용이면 마지막 수단으로 쓴다
        self.assertEqual(r["picked"]["fin"], ["3. 범주별 금융상품"])
        self.assertEqual(r["notes"]["fin"]["acc"]["cur_full"]["이자수익"], 27000.0)

    def test_caption_mode_when_no_headings(self):
        html = ("<P>당기 금융수익과 금융비용의 내역 (단위 : 백만원)</P><TABLE><THEAD><TR><TH>구분</TH><TH>당기</TH><TH>전기</TH></TR></THEAD>"
                "<TBODY><TR><TD>이자수익</TD><TD>12,000</TD><TD>10,000</TD></TR><TR><TD>이자비용</TD><TD>30,000</TD><TD>20,000</TD></TR></TBODY></TABLE>"
                "<P>단기차입금 내역 (단위 : 백만원)</P><TABLE><THEAD><TR><TH>구분</TH><TH>당기말</TH><TH>전기말</TH></TR></THEAD>"
                "<TBODY><TR><TD>단기차입금</TD><TD>100,000</TD><TD>90,000</TD></TR></TBODY></TABLE>")
        r = F.parse_note_parent(html)
        self.assertEqual((r["mode"], r["blocks"]), ("caption", 2))
        self.assertEqual(r["notes"]["fin"]["acc"]["cur_full"], {"이자수익": 12000.0, "이자비용": 30000.0})
        self.assertEqual(r["notes"]["borrowings"]["acc"]["cur_full"], {"단기차입금": 100000.0})
        self.assertNotIn("other", r["notes"])

    def test_empty_parent(self):
        r = F.parse_note_parent("<P class='section-2'>3. 연결재무제표 주석</P><P>-</P>")          # 연결이 없는 회사의 빈 절(161건)
        self.assertEqual((r["blocks"], r["notes"]), (0, {}))

    def test_mark_parent_src(self):
        src = {"이자수익": "note:fin(3m)", "단기차입금": "note:borrowings(split of face 단기금융부채)", "x": "face"}
        F._mark_parent_src(src)
        self.assertEqual(src, {"이자수익": "note_parent:fin(3m)", "단기차입금": "note_parent:borrowings(split of face 단기금융부채)", "x": "face"})


class TestNoteParentCollect(unittest.TestCase):
    """--collect-notes --notes-parent-fallback — 네트워크(toc·fetch_section)는 가짜로 바꾸고 임시 fin_cache 에서 돈다."""

    PARENT = {"text": "3. 연결재무제표 주석", "offset": "100", "length": "1000"}
    PARENT_SEP = {"text": "5. 재무제표 주석", "offset": "2000", "length": "1000"}
    SUB = {"text": "18. 금융수익과 금융원가 (연결)", "offset": "500", "length": "50"}

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.saved = {k: getattr(F, k) for k in ("ASSETS", "FIN_CACHE", "LOG_PATH", "toc", "fetch_section")}
        F.ASSETS, F.FIN_CACHE, F.LOG_PATH = self.tmp, os.path.join(self.tmp, "fin_cache"), os.path.join(self.tmp, "log")
        self.calls = []
        self.nodes = [self.PARENT, self.PARENT_SEP]
        self.bodies = {"3. 연결재무제표 주석": _fx("hanil_2023Q4_note_parent_cons.html"),
                       "5. 재무제표 주석": _fx("hanil_2023Q4_note_parent_sep.html"),
                       "18. 금융수익과 금융원가 (연결)": _fx("shi_2026Q2_note_fin.html")}
        F.toc = lambda rcp: (self.calls.append(("toc", rcp)), self.nodes)[1]
        F.fetch_section = lambda n: (self.calls.append(("fetch", n["text"])), self.bodies[n["text"]])[1]

    def tearDown(self):
        import shutil
        for k, v in self.saved.items():
            setattr(F, k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _meta(self, notes=None, cons_html="<table><tr><td>연결 재무상태표</td></tr></table>"):
        d = os.path.join(F.FIN_CACHE, "002220")
        os.makedirs(d, exist_ok=True)
        meta = {"stock": "002220", "quarter": "2023Q4", "rcp": "20240319000754", "kind": "A001",
                "sections": {"cons": {"path": "fin_cache/002220/2023Q4_cons.html"}, "sep": {"path": "fin_cache/002220/2023Q4_sep.html"}}}
        if notes is not None:
            meta["notes"] = notes
        with open(os.path.join(d, "2023Q4_meta.json"), "w", encoding="utf-8") as f:
            F.json.dump(meta, f, ensure_ascii=False)
        with open(os.path.join(d, "2023Q4_cons.html"), "w", encoding="utf-8") as f:
            f.write(cons_html)

    def _read(self):
        return F._read_meta("002220", "2023Q4")

    def test_subnodes_present_no_fallback(self):
        self.nodes = [self.PARENT, self.SUB, self.PARENT_SEP]
        self._meta()
        nt = F.collect_notes_quarter("002220", "한일철강", "2023Q4", parent_fallback=True)
        self.assertEqual(list(nt["items"]), ["fin"])
        self.assertNotIn("parent", nt)                                                          # 하위 노드가 있으면 폴백을 타지 않는다
        self.assertEqual(self.calls, [("toc", "20240319000754"), ("fetch", "18. 금융수익과 금융원가 (연결)")])
        self.assertFalse(os.path.exists(F.note_parent_cache_path("002220", "2023Q4", "cons")))

    def test_flag_off_keeps_old_behavior(self):
        self._meta()
        nt = F.collect_notes_quarter("002220", "한일철강", "2023Q4")
        self.assertEqual((nt["note"], nt.get("parent")), ("no_note_subnodes", None))
        self.assertEqual(self.calls, [("toc", "20240319000754")])

    def test_fresh_quarter_parent_one_fetch(self):
        self._meta()
        nt = F.collect_notes_quarter("002220", "한일철강", "2023Q4", parent_fallback=True)
        self.assertEqual(nt["note"], "no_note_subnodes")
        self.assertEqual((nt["parent"]["scope"], nt["parent"]["cached"], nt["parent"]["note"]),
                         ("cons", "fin_cache/002220/2023Q4_note_parent_cons.html", ""))
        self.assertEqual(self.calls, [("toc", "20240319000754"), ("fetch", "3. 연결재무제표 주석")])   # 목차 재사용 + 부모 1요청
        self.assertEqual(self._read()["notes"]["parent"]["scope"], "cons")                       # 체크포인트

    def test_checkpointed_no_subnodes_then_cache_reuse(self):
        self._meta(notes={"scope": None, "items": {}, "note": "no_note_subnodes", "collected_at": "2026-10-01"})
        nt = F.collect_notes_quarter("002220", "한일철강", "2023Q4", parent_fallback=True)
        self.assertEqual(nt["parent"]["scope"], "cons")
        self.assertEqual(self.calls, [("toc", "20240319000754"), ("fetch", "3. 연결재무제표 주석")])
        self.calls.clear()
        nt2 = F.collect_notes_quarter("002220", "한일철강", "2023Q4", parent_fallback=True)       # 두 번째: 체크포인트 — 요청 0
        self.assertEqual((self.calls, nt2["parent"]["cached"]), ([], nt["parent"]["cached"]))
        # meta 의 parent 를 지워도(캐시 파일만 있는 상태 — 2026-10-02 prefetch 786) 요청 없이 재사용
        m = self._read()
        del m["notes"]["parent"]
        with open(F.cache_paths("002220", "2023Q4")["meta"], "w", encoding="utf-8") as f:
            F.json.dump(m, f, ensure_ascii=False)
        nt3 = F.collect_notes_quarter("002220", "한일철강", "2023Q4", parent_fallback=True)
        self.assertEqual((self.calls, nt3["parent"]["cached"]), ([], "fin_cache/002220/2023Q4_note_parent_cons.html"))

    def test_empty_cons_goes_to_sep(self):
        """연결 재무제표 절이 비어 있으면(연결 해당없음) 별도 주석. 연결 주석을 받았는데 빈 절이어도 별도로 넘어간다."""
        self._meta(notes={"scope": None, "items": {}, "note": "no_note_subnodes"}, cons_html="<p>-</p>")
        nt = F.collect_notes_quarter("002220", "x", "2023Q4", parent_fallback=True)
        self.assertEqual(nt["parent"]["scope"], "sep")
        self.assertEqual(self.calls, [("toc", "20240319000754"), ("fetch", "5. 재무제표 주석")])
        self.calls.clear()
        os.remove(F.note_parent_cache_path("002220", "2023Q4", "sep"))
        self._meta(notes={"scope": None, "items": {}, "note": "no_note_subnodes"})              # 연결 절은 있는데
        self.bodies["3. 연결재무제표 주석"] = "<P>3. 연결재무제표 주석</P><P>-</P>"               # 연결 주석이 빈 절
        nt = F.collect_notes_quarter("002220", "x", "2023Q4", parent_fallback=True)
        self.assertEqual(nt["parent"]["scope"], "sep")
        self.assertEqual(self.calls, [("toc", "20240319000754"), ("fetch", "3. 연결재무제표 주석"), ("fetch", "5. 재무제표 주석")])

    def test_no_parent_node(self):
        self.nodes = []
        self._meta(notes={"scope": None, "items": {}, "note": "no_note_subnodes"})
        nt = F.collect_notes_quarter("002220", "x", "2023Q4", parent_fallback=True)
        self.assertEqual((nt["parent"]["scope"], nt["parent"]["note"]), (None, "no_parent_node"))

    def test_build_uses_parent(self):
        """build: 부모 절 주석이 face 에 없는 계정만 채우고 출처를 note_parent: 로 적는다. 못 찾은 키는 note_parent_missing."""
        face = """<p>2-1. 연결 재무상태표</p>
<table><tr><td>연결 재무상태표</td></tr><tr><td>제 67 기 2023.12.31 현재</td></tr><tr><td>(단위 : 백만원)</td></tr></table>
<table><thead><tr><th></th><th>제 67 기</th><th>제 66 기</th></tr></thead>
<tr><td>유동자산</td><td>300,000</td><td>300,000</td></tr><tr><td>자산총계</td><td>400,000</td><td>400,000</td></tr>
<tr><td>부채총계</td><td>150,000</td><td>150,000</td></tr><tr><td>자본총계</td><td>250,000</td><td>250,000</td></tr></table>
<table><tr><td>연결 손익계산서</td></tr><tr><td>제 67 기 2023.01.01 부터 2023.12.31 까지</td></tr><tr><td>(단위 : 백만원)</td></tr></table>
<table><thead><tr><th></th><th>제 67 기</th><th>제 66 기</th></tr></thead>
<tr><td>매출액</td><td>200,000</td><td>210,000</td></tr><tr><td>영업이익</td><td>5,000</td><td>6,000</td></tr>
<tr><td>금융수익</td><td>2,143</td><td>548</td></tr><tr><td>금융비용</td><td>6,607</td><td>6,767</td></tr>
<tr><td>당기순이익</td><td>1,000</td><td>2,000</td></tr></table>"""
        self._meta(notes={"scope": None, "items": {}, "note": "no_note_subnodes",
                          "parent": {"scope": "cons", "cached": "fin_cache/002220/2023Q4_note_parent_cons.html", "note": ""}},
                   cons_html=face)
        html = self.bodies["3. 연결재무제표 주석"].replace("33. 기타수익 및 기타비용", "33. 기타 손익 내역")   # other 를 일부러 못 찾게
        with open(F.note_parent_cache_path("002220", "2023Q4", "cons"), "w", encoding="utf-8") as f:
            f.write(html)
        fin = F.build_company("002220", ["2023Q4"], "한일철강", golden={})
        c = fin["cons"]
        self.assertEqual(c["is_ytd"]["2023Q4"]["이자수익"], 805.72)                               # face 에 없던 계정 — 연간 열(cur_full)
        self.assertEqual(c["is_ytd"]["2023Q4"]["금융수익"], 2143.0)                               # face 값은 그대로
        b = c["bs"]["2023Q4"]
        self.assertEqual((b["단기차입금"], b["유동성장기부채"], b["총차입금"]), (79006.06, 20494.0, 99500.06))   # 재합성
        self.assertNotIn("장기차입금", b)                                                         # 주석 당기말 `-` — 없는 숫자를 만들지 않는다
        self.assertEqual(c["src_notes"]["2023Q4"]["단기차입금"], "note_parent:borrowings")
        self.assertTrue(all(v.startswith("note_parent:") for v in c["src_notes"]["2023Q4"].values()))
        self.assertEqual(c["notes"]["fin"]["2023Q4"]["ytd"]["이자수익"], 805.72)
        self.assertEqual(c["notes"]["borrowings"]["2023Q4"]["단기차입금"], 79006.06)
        codes = [i["code"] for i in fin["issues"] if i["quarter"] == "2023Q4"]
        self.assertIn("note_parent_missing:other", codes)
        self.assertNotIn("notes_no_subnodes", codes)
        self.assertEqual(fin["reports"]["2023Q4"]["notes"]["parent"]["picked"]["fin"], ["32. 금융수익 및 금융비용"])


# ── 2026-10-05 V1 검증 레인 — 비용 부호 규약(face 영업외 그룹·주석 표)·IS 항등식 checks·주석 파서 보강·표준 차입금 라벨 ──
class TestExpenseSignTable(unittest.TestCase):
    """비용 부호 규약 '비용은 양수' — 관행 판정은 누적·연간 열로, 적용은 표의 모든 열에."""

    def _is(self, rows, unit="천원"):
        head = ("<table><tr><td>연결 포괄손익계산서</td></tr><tr><td>(단위 : %s)</td></tr></table>"
                "<table><thead><tr><th></th><th>제 67 기 3분기 3개월</th><th>제 67 기 3분기 누적</th><th>제 66 기 3분기 3개월</th><th>제 66 기 3분기 누적</th></tr></thead>" % unit)
        body = "".join("<tr><td>%s</td>%s</tr>" % (r[0], "".join("<td>%s</td>" % c for c in r[1:])) for r in rows)
        return head + body + "</table>"

    KCC = [("매출액", "1,000,000", "1,900,000", "900,000", "1,800,000"), ("매출원가", "600,000", "1,100,000", "500,000", "1,000,000"),
           ("매출총이익", "400,000", "800,000", "400,000", "800,000"), ("판매비와관리비", "300,000", "560,000", "300,000", "560,000"),
           ("영업이익", "100,000", "240,000", "100,000", "240,000"),
           ("기타영업외손익", "(11,000)", "(20,000)", "(5,000)", "(9,000)"), ("기타이익", "14,000", "30,000", "10,000", "20,000"), ("기타손실", "(25,000)", "(50,000)", "(15,000)", "(29,000)"),
           ("순금융손익", "36,000", "70,000", "30,000", "60,000"), ("금융수익", "50,000", "100,000", "40,000", "80,000"), ("금융원가", "(14,000)", "(30,000)", "(10,000)", "(20,000)"),
           ("법인세비용차감전순이익(손실)", "125,000", "290,000", "125,000", "291,000"), ("법인세비용(수익)", "25,000", "58,000", "25,000", "58,000"),
           ("분기순손익", "100,000", "232,000", "100,000", "233,000")]

    def test_nonop_group_negative_convention_flipped(self):
        """케이씨씨 — 영업비용은 양수, 금융원가·기타손실만 괄호(금융수익 + 금융원가(−) = 순금융손익). 그룹만 뒤집고 순액은 그대로."""
        p = F.parse_fin_section(self._is(self.KCC))
        q, y = p["is"]["cur_q"], p["is"]["cur_ytd"]
        self.assertEqual((q["금융비용"], q["기타영업외비용"], q["금융손익"], q["기타영업외손익"]), (14.0, 25.0, 36.0, -11.0))
        self.assertEqual((y["금융비용"], y["기타영업외비용"]), (30.0, 50.0))
        self.assertEqual((q["매출원가"], q["판관비"], q["법인세비용"]), (600.0, 300.0, 25.0))                  # 영업비용·법인세는 건드리지 않는다
        self.assertAlmostEqual(q["금융수익"] - q["금융비용"], q["금융손익"], places=2)
        self.assertAlmostEqual(q["기타영업외수익"] - q["기타영업외비용"], q["기타영업외손익"], places=2)
        self.assertEqual([f[0] for f in p["flags"]], ["expense_sign_negative_nonop"])
        r = F._scope_quarterize("cons", {"2024Q3": p}, ["2024Q3"])
        fin_chk = [c for c in r["checks"] if c["rule"] in ("fin=fi-fe", "oth=oi-oe", "rev-cogs=gp", "gp-sga+oth=op")]
        self.assertEqual(len(fin_chk), 4)
        self.assertTrue(all(c["ok"] for c in fin_chk), fin_chk)

    def test_negative_income_column_decided_by_identity(self):
        """케이씨씨 2024Q3 — 3개월 금융수익이 음수(평가이익 환입)여도 순액 항등식(수익 + 비용(−) = 순액)으로 관행을 가른다."""
        rows = [r for r in self.KCC if r[0] not in ("순금융손익", "금융수익", "금융원가")]
        rows += [("순금융손익", "(139,000)", "186,000", "(9,000)", "(2,000)"), ("금융수익", "(25,000)", "566,000", "108,000", "518,000"), ("금융원가", "(114,000)", "(380,000)", "(117,000)", "(520,000)")]
        q = F.parse_fin_section(self._is(rows))["is"]["cur_q"]
        self.assertEqual((q["금융수익"], q["금융비용"], q["금융손익"]), (-25.0, 114.0, -139.0))
        self.assertAlmostEqual(q["금융수익"] - q["금융비용"], q["금융손익"], places=2)

    def test_genuine_negative_3m_kept_when_cumulative_positive(self):
        """동방선기 2023Q3 별도 — 누적 기타비용은 양수(관행 아님), 3개월 열의 기타비용 (2,860)은 환입이라 그대로 두고 기타영업외손익 = 5.88 + 2.86 = 8.74(FnGuide 값)."""
        rows = [("매출액", "30,000", "90,000", "28,000", "85,000"), ("매출원가", "20,000", "60,000", "19,000", "58,000"), ("매출총이익", "10,000", "30,000", "9,000", "27,000"),
                ("영업이익", "3,000", "9,000", "2,500", "8,000"), ("기타수익", "5,880", "12,000", "1,000", "3,000"), ("기타비용", "(2,860)", "4,000", "900", "2,000"),
                ("금융수익", "500", "1,500", "400", "1,200"), ("금융원가", "300", "900", "200", "600")]
        p = F.parse_fin_section(self._is(rows))
        q, y = p["is"]["cur_q"], p["is"]["cur_ytd"]
        self.assertEqual((q["기타영업외비용"], y["기타영업외비용"]), (-2.86, 4.0))
        self.assertAlmostEqual(q["기타영업외손익"], 8.74, places=2)
        self.assertEqual(p["flags"], [])

    def test_convention_forces_3m_reversal_negative(self):
        """누적 열이 관행(금융원가 (30,000))이면 3개월 열의 양수 금융원가 4,000(환입)도 뒤집혀 −4 가 된다 — 금융수익 − 금융비용 = 순액이 맞아야 한다."""
        rows = [("매출액", "1,000", "2,000", "900", "1,800"), ("매출원가", "600", "1,100", "500", "1,000"), ("영업이익", "100", "240", "100", "240"),
                ("순금융손익", "54,000", "70,000", "30,000", "60,000"), ("금융수익", "50,000", "100,000", "40,000", "80,000"), ("금융원가", "4,000", "(30,000)", "(10,000)", "(20,000)")]
        p = F.parse_fin_section(self._is(rows))
        q, y = p["is"]["cur_q"], p["is"]["cur_ytd"]
        self.assertEqual((y["금융비용"], q["금융비용"]), (30.0, -4.0))
        self.assertAlmostEqual(q["금융수익"] - q["금융비용"], q["금융손익"], places=2)
        self.assertEqual(F.normalize_expense_signs_table({"cur_q": {"매출액(수익)": 10.0, "금융비용": -3.0, "금융수익": 5.0}}), {"cur_q": "nonop"})
        self.assertEqual(F.normalize_expense_signs_table({"cur_q": {"매출액(수익)": 10.0, "금융비용": -3.0, "금융수익": 5.0}, "cur_ytd": {"금융비용": 9.0, "금융수익": 15.0}}), {"cur_q": "", "cur_ytd": ""})

    def test_nonop_total_label_split_from_other(self):
        """삼미금속 별도 — `영업외손익`(금융+기타 총액)은 기타영업외손익이 아니다. 기타수익/비용이 있으면 그 차, 없으면 총액 − 금융손익."""
        self.assertEqual(F._entries_for("is", None, F.norm_label("영업외손익"))[0], ["영업외손익"])
        a = F.synth_is({"금융수익": 15.78, "금융비용": 642.14, "기타영업외수익": 52.51, "기타영업외비용": 222.31, "영업외손익": -796.16})
        self.assertAlmostEqual(a["기타영업외손익"], 52.51 - 222.31, places=2)
        self.assertEqual(a["영업외손익"], -796.16)
        b = F.synth_is({"금융수익": 10.0, "금융비용": 3.0, "영업외손익": 8.0})
        self.assertAlmostEqual(b["기타영업외손익"], 1.0, places=2)
        c = F.synth_is({"영업외손익": 8.0})
        self.assertEqual(c["기타영업외손익"], 8.0)
        rows = [("매출액", "22,566", "40,236", "20,000", "39,000"), ("매출원가", "19,127", "34,866", "17,000", "33,000"), ("영업이익", "1,000", "2,000", "900", "1,800"),
                ("금융수익", "16", "32", "2", "4"), ("금융원가", "(642)", "(1,379)", "(770)", "(1,582)"), ("기타수익", "53", "144", "774", "1,030"), ("기타비용", "(222)", "(283)", "(35)", "(110)"),
                ("영업외손익", "(795)", "(1,486)", "(29)", "(658)")]
        q = F.parse_fin_section(self._is(rows, "백만원"))["is"]["cur_q"]
        self.assertEqual((q["금융비용"], q["기타영업외비용"]), (642.0, 222.0))                       # 순액이 총액이라 항등식이 아니라 부호(수익 양수)로 가른다
        self.assertAlmostEqual(q["기타영업외손익"], 53.0 - 222.0, places=2)

    def test_face_other_nonop_separate_line(self):
        """동성화인텍 2022Q1 — face `기타영업외손익` 554.75 는 기타이익 2,561.09·기타손실 1,869.01 과 별도 항목. 세전 대조가 맞으면 수익 − 비용 + 그 줄."""
        rows = [("매출액", "30,000", "30,000", "28,000", "28,000"), ("매출원가", "25,000", "25,000", "24,000", "24,000"), ("영업이익(손실)", "1,304", "1,304", "1,000", "1,000"),
                ("금융수익", "34", "34", "30", "30"), ("금융원가", "396", "396", "300", "300"), ("기타이익", "2,561", "2,561", "2,000", "2,000"), ("기타손실", "1,869", "1,869", "1,500", "1,500"),
                ("기타영업외손익", "555", "555", "100", "100"), ("법인세비용차감전순이익(손실)", "2,189", "2,189", "1,330", "1,330")]
        p = F.parse_fin_section(self._is(rows, "백만원"))
        q = p["is"]["cur_q"]
        self.assertEqual((q["기타영업외손익"], q["기타영업외손익(face)"]), (1247.0, 555.0))
        self.assertIn("other_nonop_face_separate_line", [f[0] for f in p["flags"]])
        r = F._scope_quarterize("cons", {"2022Q1": p}, ["2022Q1"])
        self.assertTrue(all(c["ok"] for c in r["checks"] if c["rule"] == "oth=oi-oe"))
        a = dict(q)
        F.synth_is(a)                                                                                   # 다시 돌려도 두 번 더하지 않는다
        self.assertEqual(a["기타영업외손익"], 1247.0)
        rows2 = [r_ for r_ in rows if r_[0] != "법인세비용차감전순이익(손실)"] + [("법인세비용차감전순이익(손실)", "1,634", "1,634", "1,230", "1,230")]
        q2 = F.parse_fin_section(self._is(rows2, "백만원"))["is"]["cur_q"]
        self.assertEqual(q2["기타영업외손익"], 555.0)                                                     # 세전 대조가 안 맞으면 face 값 그대로(checks 에 남는다)
        self.assertNotIn("기타영업외손익(face)", q2)

    def test_kcc_equity_method_header_row_skipped(self):
        """케이씨씨 2023Q3 — `기타이익` 머리줄 바로 아래 `지분법손익` 이 같은 값이면 그룹 머리다. 두 번째 `기타이익` 이 기타영업외수익."""
        rows = [("매출액", "1,552,725", "4,706,012", "1,400,000", "4,500,000"), ("매출원가", "1,223,040", "3,716,456", "1,100,000", "3,600,000"), ("영업이익", "88,430", "300,000", "80,000", "290,000"),
                ("기타이익", "(14,494)", "(33,798)", "(49)", "21,420"), ("지분법손익", "(14,494)", "(33,798)", "(49)", "21,420"),
                ("기타영업외손익", "408", "(7,125)", "(2,537)", "(16,434)"), ("기타이익", "10,562", "56,100", "13,187", "48,066"), ("기타손실", "(10,154)", "(63,225)", "(15,725)", "(64,500)")]
        p = F.parse_fin_section(self._is(rows, "백만원"))
        q = p["is"]["cur_q"]
        self.assertEqual((q["기타영업외수익"], q["기타영업외비용"], q["기타영업외손익"]), (10562.0, 10154.0, 408.0))
        self.assertEqual(q["종속기업,공동지배기업및관계기업관련손익"], -14494.0)
        self.assertIn(["기타이익", -14494.0], p["raw_labels"]["is"])


class TestNoteExpenseSign(unittest.TestCase):
    """주석 표의 비용 괄호 표기 — 누적 열로 관행을 정하고 모든 열에 적용. 진짜 음수(환입)는 남긴다."""

    def _tbl(self, rows, hdr=("구 분", "당반기 3개월", "당반기 누적", "전반기 3개월", "전반기 누적"), lead="금융수익과 금융원가의 내역은 다음과 같습니다. (단위 : 천원)"):
        head = "<p>%s</p><table><thead><tr>%s</tr></thead><tbody>" % (lead, "".join("<th>%s</th>" % h for h in hdr))
        return head + "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r) for r in rows) + "</tbody></table>"

    def test_kcc_hanwha_note_flipped_all_columns(self):
        """한화시스템 2026Q2 하위 노드 주석 — 누적 열이 전부 괄호(이자비용 (57,623,651)·금융비용 합계 (68,353,632)); 3개월 외화환산손실 +5,117,789 은 환입이라 뒤집혀 음수."""
        rows = [("금융수익 합계", "26,151,868", "62,336,254", "20,000,000", "50,000,000"), ("이자수익", "16,873,657", "21,729,178", "15,000,000", "30,000,000"),
                ("외화환산이익", "7,454,208", "23,436,566", "1,000,000", "2,000,000"),
                ("금융원가 합계", "(43,068,358)", "(68,353,632)", "(30,000,000)", "(60,000,000)"), ("이자비용", "(40,154,429)", "(57,623,651)", "(29,000,000)", "(58,000,000)"),
                ("외환차손", "(8,031,718)", "(10,121,491)", "(500,000)", "(1,000,000)"), ("외화환산손실", "5,117,789", "(608,490)", "(500,000)", "(1,000,000)"),
                ("금융수익(비용)", "(16,916,490)", "(6,017,378)", "(10,000,000)", "(10,000,000)")]
        n = F.parse_note_section(self._tbl(rows), "fin")
        self.assertEqual(n["expense_sign_flipped"], 1)
        q, y = n["acc"]["cur_q"], n["acc"]["cur_ytd"]
        self.assertEqual((q["이자비용"], q["외환차손"], q["외화환산손실"]), (40154.43, 8031.72, -5117.79))
        self.assertEqual((y["이자비용"], y["외화환산손실"], y["금융비용합계"]), (57623.65, 608.49, 68353.63))
        self.assertEqual((y["이자수익"], y["순액"]), (21729.18, -6017.38))                             # 수익·순액은 그대로

    def test_positive_convention_with_3m_reversals_untouched(self):
        """태광 2023Q3 — 누적 열은 양수(관행 아님). 3개월 이자비용 (20,448)·외화환산손실 (173,542) 는 환입이라 음수로 남는다."""
        rows = [("이 자 비 용", "(20,448)", "452,796", "163,920", "509,158"), ("외 환 차 손", "695,134", "2,015,681", "195,321", "424,904"),
                ("외 화 환 산 손 실", "(173,542)", "118,832", "(87,036)", "221,866"), ("합 계", "558,535", "3,036,412", "2,561,969", "4,790,264")]
        n = F.parse_note_section(self._tbl(rows, lead="(2) 당분기와 전분기 중 금융비용의 내역은 다음과 같습니다. (단위: 천원)"), "fin")
        self.assertEqual(n["expense_sign_flipped"], 0)
        self.assertEqual((n["acc"]["cur_q"]["이자비용"], n["acc"]["cur_ytd"]["이자비용"], n["acc"]["cur_q"]["외화환산손실"]), (-20.45, 452.8, -173.54))
        self.assertEqual(n["acc"]["cur_ytd"]["금융비용합계"], 3036.41)                                     # 캡션 '금융비용의 내역' + `합 계` 줄 = 금융비용합계

    def test_summary_table_single_expense_sure_key(self):
        """케이에스피 요약표 — 비용 줄이 이자비용 하나뿐이어도 누적 열 이자비용이 (721,629) 면 관행이다."""
        rows = [("금융수익", "금융수익", "금융수익", "금융수익", "금융수익"), ("이자수익", "59,853", "98,364", "36,546", "51,312"),
                ("금융원가", "금융원가", "금융원가", "금융원가", "금융원가"), ("이자비용", "(349,170)", "(721,629)", "(332,152)", "(643,900)"),
                ("순금융수익(비용)", "(289,317)", "(623,265)", "(295,606)", "(592,588)")]
        n = F.parse_note_section(self._tbl(rows), "fin")
        self.assertEqual((n["acc"]["cur_q"]["이자비용"], n["acc"]["cur_ytd"]["이자비용"], n["acc"]["cur_ytd"]["순액"]), (349.17, 721.63, -623.26))
        merged = {"fin": n, "other": {"expense_sign_flipped": 0}}
        issues = []
        F._note_sign_issues(merged, issues, "2025Q2", "cons")
        self.assertEqual([i["code"] for i in issues], ["note_expense_sign_negative"])

    def test_sk_single_negative_without_cumulative_evidence_kept(self):
        d = {"cur_q": {"이자수익": 363.74, "이자비용": 5301.02, "외화환산손실": -25.39}}
        self.assertFalse(F.normalize_note_expense_signs("fin", d))
        self.assertEqual(d["cur_q"]["외화환산손실"], -25.39)


class TestNoteParserUpgrades(unittest.TestCase):
    """주석 파서 보강 — 머리행 다중행·`당1분기`·이자율 열·라벨 변형·캡션 합계·소절 분할·제목 변형·구분 머리줄 합계·유동성 분산 합산."""

    def test_split_hdr_two_header_rows_hint_in_second(self):
        """비엠티 차입금 표 — THEAD 없이 1행 `구 분|차입처|연 이자|금 액|금 액`, 2행 `…|당기말|전기말`."""
        t = {"cols": [], "rows": [["구 분", "차입처", "2021.12.31현재연 이자", "금 액", "금 액"], ["구 분", "차입처", "2021.12.31현재연 이자", "당기말", "전기말"],
                                  ["무역어음대출", "KEB하나은행", "2.32", "3,000,000", "3,000,000"], ["합 계", "합 계", "합 계", "40,900,000", "38,400,000"]]}
        cols, rows = F._split_hdr(t)
        self.assertEqual(cols, ["구 분", "차입처", "2021.12.31현재연 이자", "금 액 당기말", "금 액 전기말"])
        self.assertEqual(len(rows), 2)
        t2 = {"cols": [], "rows": [["구 분", "당기말", "전기말"], ["기타수익:", "", ""], ["잡이익", "1,000", "900"]]}
        self.assertEqual(F._split_hdr(t2), (["구 분", "당기말", "전기말"], [["기타수익:", "", ""], ["잡이익", "1,000", "900"]]))   # 힌트 뒤 글자 줄은 데이터

    def test_period_with_digit_and_skip_columns(self):
        self.assertEqual((F._period_of("당1분기"), F._period_of("전3분기"), F._period_of("당분기말"), F._period_of("전전기")), ("cur", "prev", "cur", "prev2"))
        nlab, tags = F.tag_note_cols(["차입처", "종류", "연이자율(%) 당기말", "연이자율(%) 전기말", "금액 당기말", "금액 전기말"], "15. 차입금 당기말과 전기말 현재 단기차입금의 내역은 다음과 같습니다.", prefer_total=True)
        self.assertEqual(tags, [(4, "cur_full"), (5, "prev_full")])                                        # 이자율 열은 금액이 아니다
        nlab, tags = F.tag_note_cols(["구 분", "차입처", "연이자율", "금 액 당1분기", "금 액 전기"], "", prefer_total=True)
        self.assertEqual(tags, [(3, "cur_full"), (4, "prev_full")])

    def test_borrowings_label_variants(self):
        self.assertEqual(F._map_note_label("borrowings", "단기차입금계"), "단기차입금")
        self.assertEqual(F._map_note_label("borrowings", "장기차입금계"), "장기차입금")
        self.assertEqual(F._map_note_label("borrowings", "차감: 유동성 대체"), "유동성장기부채")
        self.assertEqual(F._map_note_label("borrowings", "유동성대체분"), "유동성장기부채")
        self.assertEqual(F._caption_subject("(3) 당기말과 전기말 현재 사채의 내역은 다음과 같습니다. (단위:백만원)"), "사채")
        self.assertEqual(F._caption_subject("15. 차입금당기말과 전기말 현재 단기차입금의 내역은 다음과 같습니다. (단위 : 원)"), "단기차입금")

    HHI = ("<P>1. 일반사항</P><P>2. 회계정책</P><P>3. 차입금과 사채</P>"
           "<P>(1) 당기말과 전기말 현재 단기차입금의 내역은 다음과 같습니다. (단위:백만원)</P>"
           "<TABLE><THEAD><TR><TH>구 분</TH><TH>차입처</TH><TH>이자율</TH><TH>당기</TH><TH>전기</TH></TR></THEAD><TBODY>"
           "<TR><TD>외화일반대출</TD><TD>FDH</TD><TD>2.50%</TD><TD>12,775</TD><TD>9,673</TD></TR>"
           "<TR><TD>Usance L/C</TD><TD>기업은행 외</TD><TD>0.25%</TD><TD>648,763</TD><TD>450,626</TD></TR>"
           "<TR><TD>소 계</TD><TD>소 계</TD><TD>소 계</TD><TD>661,538</TD><TD>460,299</TD></TR>"
           "<TR><TD>유동성장기차입금</TD><TD>유동성장기차입금</TD><TD>유동성장기차입금</TD><TD>579,275</TD><TD>1,635,549</TD></TR>"
           "<TR><TD>합 계</TD><TD>합 계</TD><TD>합 계</TD><TD>1,240,813</TD><TD>2,095,848</TD></TR></TBODY></TABLE>"
           "<P>(2) 당기말과 전기말 현재 장기차입금의 내역은 다음과 같습니다. (단위:백만원)</P>"
           "<TABLE><THEAD><TR><TH>구 분</TH><TH>차입처</TH><TH>이자율</TH><TH>당기</TH><TH>전기</TH></TR></THEAD><TBODY>"
           "<TR><TD>원화일반대출</TD><TD>산업은행 외</TD><TD>2.33%</TD><TD>2,001,975</TD><TD>3,422,735</TD></TR>"
           "<TR><TD>소 계</TD><TD>소 계</TD><TD>소 계</TD><TD>2,001,975</TD><TD>3,422,735</TD></TR>"
           "<TR><TD>유동성장기차입금</TD><TD>유동성장기차입금</TD><TD>유동성장기차입금</TD><TD>(579,275)</TD><TD>(1,635,549)</TD></TR>"
           "<TR><TD>합 계</TD><TD>합 계</TD><TD>합 계</TD><TD>1,422,700</TD><TD>1,787,186</TD></TR></TBODY></TABLE>"
           "<P>(3) 당기말과 전기말 현재 사채의 내역은 다음과 같습니다. (단위:백만원)</P>"
           "<TABLE><THEAD><TR><TH>종 목</TH><TH>발행일</TH><TH>만기일</TH><TH>이자율</TH><TH>당기</TH><TH>전기</TH><TH>보증여부(*)</TH></TR></THEAD><TBODY>"
           "<TR><TD>제3회</TD><TD>2019-05-29</TD><TD>2022-02-28</TD><TD>3.75%</TD><TD>100,000</TD><TD>100,000</TD><TD>무보증 사채</TD></TR>"
           "<TR><TD>제4-2회</TD><TD>2021-03-05</TD><TD>2024-03-05</TD><TD>2.50%</TD><TD>703,070</TD><TD>152,320</TD><TD>무보증 사채</TD></TR>"
           "<TR><TD>소 계</TD><TD>소 계</TD><TD>소 계</TD><TD>소 계</TD><TD>803,070</TD><TD>252,320</TD><TD></TD></TR>"
           "<TR><TD>사채할인발행차금</TD><TD>사채할인발행차금</TD><TD>사채할인발행차금</TD><TD>사채할인발행차금</TD><TD>(823)</TD><TD>(163)</TD><TD></TD></TR>"
           "<TR><TD>유동성사채</TD><TD>유동성사채</TD><TD>유동성사채</TD><TD>유동성사채</TD><TD>(265,970)</TD><TD>(110,000)</TD><TD></TD></TR>"
           "<TR><TD>유동성사채할인발행차금</TD><TD>유동성사채할인발행차금</TD><TD>유동성사채할인발행차금</TD><TD>유동성사채할인발행차금</TD><TD>14</TD><TD>75</TD><TD></TD></TR>"
           "<TR><TD>합 계</TD><TD>합 계</TD><TD>합 계</TD><TD>합 계</TD><TD>536,291</TD><TD>142,232</TD><TD></TD></TR></TBODY></TABLE>"
           "<P>4. 충당부채</P>")

    def test_hhi_borrowings_split_three_tables(self):
        """HD현대重 2021Q4 `21. 차입금과 사채` — 단기 표는 소계 + 유동성 = 합계(단기차입금 = 합계 − 유동성 줄), 사채 캡션 `현재 사채의 내역`,
        유동성 대체가 장기 표(579,275)와 사채 표(265,970)에 나뉘어 있어 다른 금액만 더한다(같은 579,275 는 한 번)."""
        r = F.parse_note_parent(self.HHI)
        self.assertEqual(r["picked"]["borrowings"], ["3. 차입금과 사채"])
        acc = r["notes"]["borrowings"]["acc"]["cur_full"]
        self.assertEqual(acc, {"유동성장기부채": 845245.0, "단기차입금": 661538.0, "장기차입금": 1422700.0, "사채": 536291.0})
        self.assertEqual(r["notes"]["borrowings"]["acc"]["prev_full"]["단기차입금"], 460299.0)
        b = {"단기차입금": 1506767.83, "단기금융부채(face)": 1506767.83, "장기차입금": 1958992.31, "장기금융부채(face)": 1958992.31, "현금및현금성자산": 100.0}
        src, issues = {}, []
        F.inject_note_bs(b, r["notes"]["borrowings"], src, issues, "2021Q4", "cons")
        self.assertNotIn("단기금융부채(face)", b)
        self.assertNotIn("장기금융부채(face)", b)
        self.assertEqual((b["단기차입금"], b["장기차입금"]), (661538.0, 1422700.0))
        self.assertAlmostEqual(b["유동성장기부채"], 845245.0 + (1506767.83 - 1506783.0), places=2)         # 잔차 −15.17 흡수
        self.assertAlmostEqual(b["사채"], 536291.0 + (1958992.31 - 1958991.0), places=2)
        F.synth_bs(b)
        self.assertAlmostEqual(b["총차입금"], 1506767.83 + 1958992.31, places=2)                          # face 총액 보존
        self.assertEqual(sorted(i["code"] for i in issues), ["borrowings_note_residual", "borrowings_note_residual"])
        self.assertEqual(src["사채"], "note:borrowings(split of face 장기금융부채)")

    def test_caption_only_lender_table_accepted(self):
        """서호전기·오리엔탈정공 — 차입처별 표에 계정명이 없고(표 앞 글에만) 합계 줄도 없다 → 데이터 줄 하나를 그 계정으로. `(2) 유동성차입금` 캡션도 읽는다."""
        html = ("<P>1. 일반사항</P><P>2. 회계정책</P><P>3. 차입금</P><P>당기말과 전기말 현재 단기차입금의 내역은 다음과 같습니다. (단위 : 원)</P>"
                "<TABLE><THEAD><TR><TH>차입처</TH><TH>종류</TH><TH>연이자율(%) 당기말</TH><TH>연이자율(%) 전기말</TH><TH>금액 당기말</TH><TH>금액 전기말</TH></TR></THEAD>"
                "<TBODY><TR><TD>최대주주</TD><TD>운전자금</TD><TD>1.00</TD><TD>-</TD><TD>373,784,193</TD><TD>-</TD></TR></TBODY></TABLE>"
                "<P>(2) 유동성차입금당기말과 전기말 현재 유동성차입금의 내역은 다음과 같습니다. (단위: 천원)</P>"
                "<TABLE><THEAD><TR><TH>차입처</TH><TH>차입종별</TH><TH>이자율(%)</TH><TH>당기말</TH><TH>전기말</TH></TR></THEAD>"
                "<TBODY><TR><TD>BNK경남은행</TD><TD>운영자금등</TD><TD>3.45</TD><TD>1,632,152</TD><TD>-</TD></TR></TBODY></TABLE><P>4. 충당부채</P>")
        r = F.parse_note_parent(html)
        self.assertEqual(r["picked"]["borrowings"], ["3. 차입금"])
        self.assertEqual(r["notes"]["borrowings"]["acc"]["cur_full"], {"단기차입금": 373.78, "유동성장기부채": 1632.15})

    def test_combined_nonop_block_split_into_subsections(self):
        """동성화인텍 `29. 영업외손익` — 소절 29.1 금융수익 및 금융원가 / 29.2 기타수익 및 기타비용 으로 다시 잘라 fin·other 둘 다 읽는다."""
        tbl = lambda rows: ("<TABLE><THEAD><TR><TH>구 분</TH><TH>당기</TH><TH>전기</TH></TR></THEAD><TBODY>%s</TBODY></TABLE>"
                            % "".join("<TR><TD>%s</TD><TD>%s</TD><TD>%s</TD></TR>" % r for r in rows))
        html = ("<P>1. 일반사항</P><P>2. 회계정책</P><P>3. 영업외손익</P><P>3.1 금융수익 및 금융원가</P><P>(1) 당기와 전기 중 금융수익의 내역은 다음과 같습니다. (단위: 원)</P>"
                + tbl([("이자수익", "63,652,025", "157,340,683"), ("합 계", "63,652,025", "157,340,683")])
                + "<P>(2) 당기와 전기 중 금융원가의 내역은 다음과 같습니다. (단위: 원)</P>"
                + tbl([("이자비용", "3,067,219,491", "4,959,638,669"), ("합 계", "3,067,219,491", "4,959,638,669")])
                + "<P>3.2 기타수익 및 기타비용</P><P>(1) 당기와 전기 중 기타수익의 내역은 다음과 같습니다. (단위: 원)</P>"
                + tbl([("외환차익", "4,773,467,367", "4,345,802,683"), ("잡이익", "1,000,000", "2,000,000"), ("합 계", "4,774,467,367", "4,347,802,683")])
                + "<P>4. 법인세비용</P>")
        blocks = F.split_note_blocks(html)
        self.assertEqual([b["no"] for b in blocks], ["1", "2", "3.1", "3.2", "4"])
        r = F.parse_note_parent(html)
        self.assertEqual(r["picked"]["fin"], ["3.1. 금융수익 및 금융원가"])
        self.assertEqual(r["picked"]["other"], ["3.2. 기타수익 및 기타비용"])
        self.assertEqual(r["notes"]["fin"]["acc"]["cur_full"], {"이자수익": 63.65, "금융수익합계": 63.65, "이자비용": 3067.22, "금융비용합계": 3067.22})
        self.assertEqual(r["notes"]["other"]["acc"]["cur_full"], {"외환차익": 4773.47, "기타수익합계": 4774.47})

    def test_other_title_variants_and_both_nonop(self):
        self.assertTrue(F.NOTE_RX["other"].search("27. 기타이익 및 기타손실"))
        self.assertTrue(F.NOTE_RX["other"].search("25. 영업외수익 및 영업외비용"))
        self.assertTrue(F.NOTE_RX["other"].search("28. 기타손익"))
        self.assertFalse(F.NOTE_RX["other"].search("22. 기타포괄손익누계액"))
        self.assertEqual(F._parent_rank("other", "20. 영업외손익 및 금융손익"), 1)                      # 금융·기타가 한 블록 — other 도 읽는다
        self.assertEqual(F._parent_rank("fin", "20. 영업외손익 및 금융손익"), 1)
        self.assertIsNone(F._parent_rank("other", "28. 금융수익과 금융비용"))

    def test_caption_and_section_totals(self):
        """하이록코리아 `(1) 당기와 전기의 기타수익의 내역` + `계` 줄 → 기타수익합계; 비엠티 한 표 안 `기타수익:`·`기타비용:` 구분 머리줄 → 각 합계."""
        tbl = lambda lead, rows: ("<P>%s</P><TABLE><THEAD><TR><TH>구 분</TH><TH>당 기</TH><TH>전 기</TH></TR></THEAD><TBODY>%s</TBODY></TABLE>"
                                  % (lead, "".join("<TR><TD>%s</TD><TD>%s</TD><TD>%s</TD></TR>" % r for r in rows)))
        n = F.parse_note_section(tbl("기타수익과 기타비용 (1) 당기와 전기의 기타수익의 내역은 다음과 같습니다 (단위: 천원)",
                                     [("유형자산처분이익", "96,721", "36,370"), ("잡 이 익", "572,479", "67,559"), ("계", "877,741", "595,327")])
                                 + tbl("(2) 당기와 전기의 기타비용의 내역은 다음과 같습니다. (단위: 천원)",
                                       [("유형자산처분손실", "27,389", "22,013"), ("잡 손 실", "95,353", "435,590"), ("계", "191,067", "4,021,685")]), "other")
        self.assertEqual(n["acc"]["cur_full"], {"기타수익합계": 877.74, "기타비용합계": 191.07})
        n2 = F.parse_note_section(tbl("27. 기타수익 및 기타비용 (단위: 천원)",
                                      [("기타수익:", "기타수익:", "기타수익:"), ("유형자산처분이익", "6,543", "6,336"), ("잡이익", "218,653", "123,183"), ("소 계", "225,196", "129,519"),
                                       ("기타비용:", "기타비용:", "기타비용:"), ("기부금", "7,200", "28,800"), ("소 계", "7,200", "28,800")]), "other")
        self.assertEqual(n2["acc"]["cur_full"], {"기타수익합계": 225.2, "기타비용합계": 7.2})
        self.assertIsNone(F._table_subject_total("fin", "(1) 금융수익 및 금융원가의 내역은 다음과 같습니다."))     # 둘 다 가리키면 합계를 붙이지 않는다

    def test_face_has_borrowings_gate(self):
        self.assertFalse(F._face_has_borrowings({"bs": {"cur": {"자산총계": 1.0, "매입채무및기타채무": 5.0}}}))
        self.assertTrue(F._face_has_borrowings({"bs": {"cur": {"단기금융부채(face)": 3.0}}}))
        self.assertFalse(F._face_has_borrowings({"bs": {"cur": {"사채": 0.0}}}))


class TestFaceBorrowingLabels(unittest.TestCase):
    """face BS 의 K-IFRS 표준·묶음 라벨(10-05 전수 스캔: 유동 차입금(사채 포함) 124분기·장기차입금(사채 포함), 총액 103·비유동 기타금융부채 162 …)과
    유동성 사채의 FnGuide 분류(유동성장기부채; 단기사채는 전단채·CP만 — 골든 5사 전 기간 0)."""

    def test_standard_labels_mapped(self):
        E = lambda sec, lab: (F._entries_for("bs", sec, F.norm_label(lab)) or [None])[0]
        lump_s, lump_l = ["단기차입금", "단기금융부채(face)"], ["장기차입금", "장기금융부채(face)"]
        self.assertEqual(E("cl", "유동 차입금(사채 포함)"), lump_s)
        self.assertEqual(E("cl", "유동 차입금 및 비유동차입금(사채 포함)의 유동성 대체 부분 합계 (주5,7,22)"), lump_s)
        self.assertEqual(E("cl", "유동성 금융기관 차입금(사채 제외)"), lump_s)
        self.assertEqual(E("cl", "차입금 및 사채"), lump_s)
        self.assertEqual(E("cl", "차입부채"), lump_s)
        self.assertEqual(E("cl", "비유동차입금의 유동성 대체 부분"), ["유동성장기부채"])
        self.assertEqual(E("cl", "유동성사채"), ["유동성장기부채"])
        self.assertEqual(E("cl", "사채"), ["유동성장기부채"])
        self.assertEqual(E("cl", "전환사채"), ["유동성장기부채"])
        self.assertEqual(E("cl", "전자단기사채"), ["단기사채"])
        self.assertEqual(E("ncl", "장기차입금(사채 포함), 총액"), lump_l)
        self.assertEqual(E("ncl", "비유동차입금(사채 포함)의 비유동성 부분 (주5,7,22)"), lump_l)
        self.assertEqual(E("ncl", "장기차입금 및 사채"), lump_l)
        self.assertEqual(E("ncl", "비유동성 금융기관 차입금(사채 제외)"), ["장기차입금"])
        self.assertEqual(E("ncl", "전환사채, 총액"), ["사채"])
        self.assertEqual(E("ncl", "기타금융부채"), ["기타비유동금융부채", "장기금융부채"])
        self.assertEqual(E("cl", "기타금융부채"), ["기타유동금융부채", "단기금융부채"])
        self.assertEqual(E("cl", "당기손익-공정가치측정금융부채"), ["기타유동금융부채", "단기금융부채"])

    def test_kcc_style_face_total_debt(self):
        """케이씨씨 2026Q2 face — 유동성장기차입금 + 유동성사채 = 유동성장기부채, 총차입금 5.27조. 주석 `유동성 대체` 는 face 에 있으니 올리지 않는다."""
        html = """<table><tr><td>연결 재무상태표</td></tr><tr><td>(단위 : 백만원)</td></tr></table>
<table><thead><tr><th></th><th>제 68 기 반기말</th><th>제 67 기말</th></tr></thead>
<tr><td>유동부채</td><td>5,000,000</td><td>4,000,000</td></tr>
<tr><td>단기차입금</td><td>872,951</td><td>758,686</td></tr><tr><td>유동성장기차입금</td><td>644,880</td><td>-</td></tr><tr><td>유동성사채</td><td>1,396,988</td><td>1,313,396</td></tr>
<tr><td>비유동부채</td><td>3,000,000</td><td>3,500,000</td></tr>
<tr><td>장기차입금</td><td>199,507</td><td>840,861</td></tr><tr><td>비유동사채</td><td>2,151,185</td><td>2,097,836</td></tr>
<tr><td>부채총계</td><td>8,000,000</td><td>7,500,000</td></tr><tr><td>자본총계</td><td>2,000,000</td><td>2,000,000</td></tr><tr><td>자산총계</td><td>10,000,000</td><td>9,500,000</td></tr></table>"""
        b = F.parse_fin_section(html)["bs"]["cur"]
        self.assertEqual((b["단기차입금"], b["유동성장기부채"], b["장기차입금"], b["사채"]), (872951.0, 2041868.0, 199507.0, 2151185.0))
        self.assertNotIn("단기사채", b)
        self.assertEqual(b["총차입금"], 872951.0 + 2041868.0 + 199507.0 + 2151185.0)
        face = {"단기차입금": 77714.96, "단기사채": 38000.0}                                               # 승격 가드 — face 가 유동성 사채를 단기사채로 보이는 옛 fin 모양
        F.inject_note_bs(face, {"acc": {"cur_full": {"유동성장기부채": 38000.0, "장기차입금": 5.0}}}, {}, [], "2022Q2", "cons")
        self.assertNotIn("유동성장기부채", face)
        self.assertEqual(face["장기차입금"], 5.0)
