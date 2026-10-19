#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xi1_sector · xi1_view — 섹터 탭 계약 진행(XI-1) 공용 층. 네트워크 없이 픽스처(2024Q4~2026Q2 원문)와 임시 루트로 돈다.

  · 금액 칸 해석(칸 안 단위·외화·KRW 괄호·유보)과 계약명 머리·꼬리 정리
  · 분기 잇기(같은 신고일·이름 쌍둥이 계약은 계약기간으로 가른다), 원장 연결 근거 등급(흔한 이름은 계약일 근거 없이 안 잇는다)
  · 지표(진행·수령 진척·매출채권/선수금·경과·속도·예상 완료)와 신호(매출 역진·누적 감소·정체·납기 경과·표준 곡선 지연)
  · 외화 계약: 원장 원화 분모(ledger_krw) / 같은 외화 비율(fx_native) / 진행률 없음 — 원화 합계에는 원화 계약만
  · build 결정성(두 번 돌려 바이트 동일), collect 재시도 규칙, 화면 조각(빈 데이터 → '', 이스케이프)
"""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

import kce_xi1 as X                 # noqa: E402
import xi1_sector as S              # noqa: E402
import xi1_view as V                # noqa: E402

FIX = os.path.join(HERE, "fixtures")
QS = ["2024Q4", "2025Q2", "2025Q4", "2026Q2"]


def _rb(p):
    with open(p, "rb") as f:
        return f.read()


def fixture(st, q):
    with open(os.path.join(FIX, "xi1sector_%s_%s.html" % (st, q)), encoding="utf-8") as f:
        return f.read()


# 원장 행(탭 contracts.json 꼴) — 2026-10-16 kdef·kship 원장에서 그대로 옮긴 것
LEDGER_013810 = [
    {"rcp": "20230511900430", "stock": "013810", "name": "해군함정용 조타기 공급", "amt_krw_m": 4100.0, "party": "현대중공업(주)",
     "signed": "2023-05-11", "start": "2023-05-11", "end": "2027-11-03", "title": "단일판매ㆍ공급계약체결"},
    {"rcp": "20240401900548", "stock": "013810", "name": "해군함정용 조타기 및 타 공급", "amt_krw_m": 4200.0, "party": "한화오션(주)",
     "signed": "2024-04-01", "start": "2024-04-01", "end": "2028-06-30", "supersedes": "20240401900543",
     "title": "단일판매ㆍ공급계약체결"},
    {"rcp": "20241101900578", "stock": "013810", "name": "아스팔트 믹싱플랜트 공급", "amt_krw_m": 4237.21,
     "party": "HOANG LONG CONSTRUCTION INVESTMENT CORPORATION", "signed": "2024-11-01", "start": "2024-11-01",
     "end": "2025-12-15", "title": "단일판매ㆍ공급계약체결"},
    {"rcp": "20250911900172", "stock": "013810", "name": "해군함정용 조타기 및 타 공급", "amt_krw_m": 4615.0, "party": "한화오션(주)",
     "signed": "2025-09-11", "start": "2025-09-11", "end": "2030-12-31", "supersedes": "20250911900170",
     "title": "단일판매ㆍ공급계약체결"},
]
LEDGER_009540 = [
    {"rcp": "20251215800970", "stock": "009540", "name": "태안화력 5~8호기 저탄장 옥내화 공사", "amt_krw_m": 140700.0,
     "party": "한국서부발전", "signed": "2019-09-03", "start": "2019-09-03", "end": "2025-12-15",
     "supersedes": "20251121800432", "title": "[기재정정] 단일판매ㆍ공급계약체결"},
]


class TestMoneyCell(unittest.TestCase):
    def test_inline_units_and_currency(self):
        cases = {
            "676억원": (67600, None, None, False),
            "20,472백만원": (20472, None, None, False),
            "21,749,000,000원": (21749, None, None, False),
            "$15,544,340.00(19,251,665,090원)": (19251.66509, "USD", 15544340, False),
            "2,755,800(USD2,000,000)": (2755800, "USD", 2000000, False),
            "3,787,412(USD 2,690,000.)": (3787412, "USD", 2690000, False),
            "USD56,784천": (None, "USD", 56784000, False),
            "3,117,058.50(총액)": (3117058.5, None, None, False),
            "187,674,868.5(USD)": (None, "USD", 187674868.5, False),
            "2,663,571,150 (USD)": (None, "USD", 2663571150, False),
            "공시유보": (None, None, None, True),
            "-": (None, None, None, False),
        }
        for raw, want in cases.items():
            self.assertEqual(X.money_cell(raw, 1.0), want, raw)
        # `(천외화,백만원)` 열의 외화는 천 단위
        self.assertEqual(X.money_cell("USD 3,365,400", 1.0, 1000), (None, "USD", 3365400000, False))

    def test_name_head_tail(self):
        self.assertEqual(X.split_detail("ㅇ계약명 : UAE Barakah 원전 원자로계통설계 ㅇ계약상대자 : KEPCO"),
                         {"계약명": "UAE Barakah 원전 원자로계통설계", "계약상대방": "KEPCO"})
        self.assertEqual(X.split_detail("1.계약명: 미국 BESS Project Pad Mount 2.계약상대: X"),
                         {"계약명": "미국 BESS Project Pad Mount", "계약상대방": "X"})
        self.assertEqual(X.split_detail("1. 판매공급계약 내용 -ELECTRICAL CONTROL")["계약명"], "ELECTRICAL CONTROL")
        self.assertEqual(X.split_detail("2차전지용 X-ray 검사장비2.")["계약명"], "2차전지용 X-ray 검사장비")
        self.assertEqual(X.split_detail("LNG운반선 1척")["계약명"], "LNG운반선 1척")

    def test_foreign_row_keeps_raw_supply(self):
        p = X.parse_xi1(fixture("013810", "2025Q2"))
        r = [r for t in p["tables"] for r in t["rows"] if r.get("cur") == "USD"][0]
        self.assertIsNone(r["amt"])
        self.assertEqual(r["amt_fx"], 3072000)
        self.assertEqual(r["fx"]["supCum"], 2048000)


class TestPeriods(unittest.TestCase):
    def test_periods(self):
        self.assertEqual(S.periods("2026Q2"), QS)
        self.assertEqual(S.periods("2026Q3"), QS)
        self.assertEqual(S.periods("2024Q4"), ["2024Q4"])
        self.assertEqual(S.latest_xi(datetime.date(2026, 10, 16)), "2026Q2")
        self.assertEqual(S.period_end("2025Q4"), datetime.date(2025, 12, 31))
        self.assertEqual(S._window("2025Q2"), ("20250701", "20260630", "A002"))
        self.assertEqual(S._window("2025Q4"), ("20260101", "20261231", "A001"))


class _Root(unittest.TestCase):
    """임시 루트에 kdef(013810)·kship(009540) 두 탭을 꾸민다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="xi1sec_")
        for tab, st, name, led in (("kdef", "013810", "스페코", LEDGER_013810), ("kship", "009540", "HD한국조선해양", LEDGER_009540)):
            d = os.path.join(self.root, tab, "tools", "assets")
            os.makedirs(d)
            with open(os.path.join(d, "universe.json"), "w", encoding="utf-8") as f:
                json.dump({"rows": [{"stock": st, "name": name}]}, f, ensure_ascii=False)
            with open(os.path.join(d, "contracts.json"), "w", encoding="utf-8") as f:
                json.dump({"n": len(led), "rows": led}, f, ensure_ascii=False)
            stat = {}
            for q in QS:
                html = fixture(st, q)
                S.write_raw(tab, st, q, html, self.root)
                S.write_parsed(tab, st, q, S.parse_doc(html, "R%s%s" % (st, q)), self.root)
                stat["%s|%s" % (st, q)] = {"status": "ok", "rcp": "R%s%s" % (st, q)}
            S.save_status(tab, stat, self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def build(self, tab):
        return S.build(tab, root=self.root, qs=QS, hdr=False)


class TestThreadLinkMetrics(_Root):
    def test_twins_split_by_period(self):
        p = self.build("kdef")
        twins = [c for c in p["contracts"] if c["dt"] == "2024.04.01"]
        self.assertEqual(len(twins), 2)
        self.assertEqual(sorted(c["hist"]["2026Q2"][2] for c in twins), [3000, 3745])
        # 쌍둥이 둘 다 같은 원장 행을 원하면 점수 높은 하나만 잇는다(원장 한 행 = 한 계약)
        self.assertEqual(sum(1 for c in twins if c.get("link")), 1)

    def test_link_tiers_and_basis(self):
        p = self.build("kdef")
        by = {(c["dt"], c["nm"][:8]): c for c in p["contracts"] if c["dt"] != "2024.04.01"}
        a = by[("2023.05.11", "해군함정용 조타")]
        self.assertEqual((a["link"]["rcp"], a["link"]["tier"]), ("20230511900430", "A"))
        self.assertTrue(a["link"]["basis"].startswith("신고일+"))
        self.assertIn("20230511900430", p["by_rcp"])
        # 원장 정정 사슬의 옛 접수번호로도 찾는다
        b = [c for c in p["contracts"] if c["dt"] == "2025.09.11" and c.get("link")][0]
        self.assertEqual(p["by_rcp"]["20250911900170"], b["id"])

    def test_metrics(self):
        p = self.build("kdef")
        a = [c for c in p["contracts"] if c["dt"] == "2023.05.11"][0]
        m = a["m"]
        self.assertEqual((m["q"], m["amt"], m["basis"]), ("2026Q2", 4100, "xi"))
        self.assertAlmostEqual(m["prog"], 4035 / 4100, 4)
        self.assertAlmostEqual(m["recv_prog"], 3647 / 4100, 4)
        self.assertEqual((m["rem"], m["ar"], m["adv"]), (65, 388, 0))
        self.assertEqual((m["start"], m["end"], m["span_src"]), ("2023-05-11", "2027-11-03", "원장"))
        self.assertEqual(m["pace_src"], "Δ누적")
        self.assertEqual(m["pace"], 0)                        # 2025Q4 → 2026Q2 누적 그대로
        self.assertEqual(a["status"], "active")

    def test_fx_native_and_dropped(self):
        p = self.build("kdef")
        fx = [c for c in p["contracts"] if c["dt"] == "2024.11.01"][0]
        self.assertEqual((fx["m"]["basis"], fx["m"]["unit"]), ("fx_native", "USD"))
        self.assertAlmostEqual(fx["m"]["prog"], 2048000 / 3072000, 4)
        self.assertEqual(fx["status"], "dropped")            # 2025Q2 66.7% 뒤 표에서 빠짐
        self.assertEqual(fx["hist"]["2025Q2"][0], 3072000)   # 외화 맨숫자
        # 원화 합계(회사 series)에는 외화 계약이 들어가지 않는다
        ser = p["companies"]["013810"]["series"]["2025Q2"]
        self.assertEqual(ser["amt"], 4100 + 4200 + 4200)
        new = [c for c in p["contracts"] if c["dt"] == "2026.03.06"][0]
        self.assertIsNone(new["m"]["basis"])                 # 공급 열이 비어 비율도 없음
        self.assertEqual(new["status"], "new")

    def test_reversal_and_cum_drop(self):
        p = self.build("kship")
        z = [c for c in p["contracts"] if c["nm"] == "ZOR"][0]
        self.assertIn("reversal", z["flags"])                # 당기 −976
        self.assertNotIn("cum_drop", z["flags"])             # 1,256,538 → 1,255,562 (0.08%) 는 감소 문턱 안
        self.assertIsNone(z.get("link"))                     # 2015 계약 — 원장 창 밖, 근거 없는 짝은 만들지 않는다
        self.assertEqual(p["review"][0]["nm"], "ZOR")
        self.assertGreater(z["m"]["adv"], 0)                 # 수령 1,676,081 > 공급 1,255,562 → 선수금(순)
        self.assertEqual(z["m"]["ar"], 0)

    def test_generic_name_needs_date(self):
        L = S.ledger_rows("kship", [{"rcp": "20260930800001", "stock": "x", "name": "VLGC 2척", "amt_krw_m": 307400.0,
                                     "signed": "2026-09-29", "start": "2026-09-29", "end": "2029-12-31"}])
        th = {"hist": {"2026Q2": {"nm": "VLGC 2척", "dt": "2022.10.19", "amt": 270700, "supCum": 1}}}
        self.assertEqual(S._cands(th, L), [])                # 이름만 같고 금액 13% 차이·계약일 3년 차 → 잇지 않는다
        L[0]["signed"] = [datetime.date(2022, 10, 20)]
        self.assertEqual([x[1] for x in S._cands(th, L)], ["B"])   # 원장 계약일이 신고일 ±45일 → 추정

    def test_deterministic(self):
        a = S._dump(self.build("kdef"))
        b = S._dump(self.build("kdef"))
        self.assertEqual(a, b)
        self.assertNotIn(datetime.date.today().isoformat(), a)


class TestBlankAndCells(unittest.TestCase):
    def test_blank_zero_rules(self):
        r = {"amt": 100, "supCum": None, "recvCum": None}
        self.assertEqual(S.blank_zero(dict(r)), {"amt": 100, "supCum": 0, "recvCum": 0})        # `-` = 아직 0
        self.assertEqual(S.blank_zero(dict(r), sup_any=False, recv_any=False), r)              # 표가 대부분 비움 = 미기재
        self.assertNotIn("recvCum", S.blank_zero({"amt": 100, "supCum": None}))               # 열이 없던 표
        self.assertEqual(S.blank_zero({"amt": None, "supCum": None}), {"amt": None, "supCum": None})

    def test_cell_sanity(self):
        r = S.cell_sanity({"amt": 388180, "supCum": None, "recvCum": 121938492})               # 한화에어로 IM3 — 천원 칸
        self.assertEqual((r["recvCum"], r["cell_fix"]), (121938.492, ["recvCum"]))
        r = S.cell_sanity({"amt": 100, "supCum": 5e9})
        self.assertEqual((r["supCum"], r["cell_drop"]), (None, ["supCum"]))
        self.assertEqual(S.cell_sanity({"amt": 100, "supCum": 150}), {"amt": 100, "supCum": 150})   # 초과 공급은 over 로만


class TestCurve(unittest.TestCase):
    def test_curve_monotone_and_lag(self):
        cs = []
        for i in range(60):
            x = (i % 10) / 10 + 0.05
            y = max(0.0, min(1.0, (x - 0.3) * 1.4))          # 앞이 빈 S 자(조선형)
            cs.append({"status": "active", "flags": [], "m": {"elapsed": x, "prog": y}})
        curve = S.sector_curve(cs)
        ys = [p["y"] for p in curve]
        self.assertEqual(ys, sorted(ys))
        self.assertLess(S.curve_at(curve, 0.25), 0.05)
        c = {"status": "active", "flags": [], "m": {"elapsed": 0.8, "prog": 0.3}}
        S.apply_curve(c, curve)
        self.assertIn("lag", c["flags"])
        early = {"status": "active", "flags": [], "m": {"elapsed": 0.25, "prog": 0.0}}
        S.apply_curve(early, curve)
        self.assertNotIn("lag", early["flags"])               # 직선이면 '지연'이지만 표준 곡선으로는 정상
        self.assertEqual(S.sector_curve(cs[:4]), [])          # 표본이 적으면 곡선 없음


class TestCollect(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="xi1col_")
        d = os.path.join(self.root, "knuke", "tools", "assets")
        os.makedirs(d)
        with open(os.path.join(d, "universe.json"), "w", encoding="utf-8") as f:
            json.dump({"rows": [{"stock": "013810", "name": "A"}, {"stock": "999999", "name": "B"}]}, f)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def fake(self, calls):
        html = fixture("013810", "2026Q2")

        class F:
            @staticmethod
            def search_reports(st, s, e, kind):
                calls.append((st, s, kind))
                if st == "999999":
                    return []
                y = int(s[:4]) if kind == "A002" else int(s[:4]) - 1
                return [("R%s%s" % (st, s), "%s보고서 (%d.%s)" % ("반기" if kind == "A002" else "사업", y,
                                                               "06" if kind == "A002" else "12"))]

            pick_report = staticmethod(lambda lst, q: lst)
            toc = staticmethod(lambda rcp: [rcp])
            find_sections = staticmethod(lambda nodes, sec: {"xi1": nodes[0]})
            fetch_section = staticmethod(lambda node: html)

            @staticmethod
            def parallel(items, fn, lanes=None, on_done=None):
                for i, it in enumerate(items):
                    try:
                        r = fn(it)
                    except Exception as e:      # pragma: no cover
                        r = e
                    on_done(i, it, r)
        return F

    def test_collect_and_retry_rule(self):
        calls = []
        stat = S.collect("knuke", qs=["2025Q4", "2026Q2"], root=self.root, fetch=self.fake(calls), log=lambda m: None)
        self.assertEqual(stat["013810|2026Q2"]["status"], "ok")
        self.assertEqual(stat["999999|2025Q4"]["status"], "no_report")
        self.assertTrue(os.path.exists(S.parsed_path("knuke", "013810", "2026Q2", self.root)))
        blob = _rb(S.raw_path("knuke", "013810", "2026Q2", self.root))
        S.write_raw("knuke", "013810", "2026Q2", fixture("013810", "2026Q2"), self.root)
        self.assertEqual(blob, _rb(S.raw_path("knuke", "013810", "2026Q2", self.root)))   # gzip mtime 0
        calls.clear()
        S.collect("knuke", qs=["2025Q4", "2026Q2"], root=self.root, fetch=self.fake(calls), log=lambda m: None)
        # 받은 칸은 다시 안 받고, 없음(no_report)은 최신 분기만 다시 본다
        self.assertEqual([c[0] for c in calls], ["999999"])
        self.assertEqual(calls[0][2], "A002")

    def test_reparse_on_rev_change(self):
        S.collect("knuke", qs=["2026Q2"], root=self.root, fetch=self.fake([]), log=lambda m: None)
        p = S.parsed_path("knuke", "013810", "2026Q2", self.root)
        doc = json.loads(_rb(p).decode("utf-8"))
        doc["rev"], doc["tables"] = "old", []
        S.write_parsed("knuke", "013810", "2026Q2", doc, self.root)
        again = S.read_parsed("knuke", "013810", "2026Q2", self.root)
        self.assertEqual(again["rev"], X.PARSER_REV)
        self.assertTrue(again["tables"])
        self.assertEqual(again["rcp"], doc["rcp"])
        # CI 처럼 로컬 HTML 이 없어도 보존 원문 표(raw)로 같은 결과를 다시 낸다(COMMON §0-4)
        os.remove(S.raw_path("knuke", "013810", "2026Q2", self.root))
        stale = dict(again, rev="old", tables=[])
        S.write_parsed("knuke", "013810", "2026Q2", stale, self.root)
        third = S.read_parsed("knuke", "013810", "2026Q2", self.root)
        self.assertEqual(third, again)


class TestView(_Root):
    def test_empty_inputs(self):
        self.assertEqual(V.company_section(None, "013810"), "")
        self.assertEqual(V.hub_section(None), "")
        self.assertEqual(V.coverage_rows(None), "")
        p = self.build("kdef")
        self.assertEqual(V.company_section(p, "000000"), "")
        self.assertIn("—", V.progress_cell(p, ["nope"]))

    def test_sections_render(self):
        p = self.build("kdef")
        p["contracts"][0]["nm"] = "<script>x</script>"
        sec = V.company_section(p, "013810")
        self.assertIn('id="xi1"', sec)
        self.assertIn("<svg", sec)
        self.assertNotIn("<script>x", sec)
        self.assertNotIn("nan", sec.lower().replace("nanum", ""))
        cell = V.progress_cell(p, ["20230511900430"])
        self.assertIn('data-v="0.9841"', cell)
        hub = V.hub_section(p, co_href=lambda st: "%s/index.html" % st)
        self.assertIn("013810/index.html", hub)
        self.assertIn("xi1cv", V.coverage_rows(p))
        self.assertIn("USD", V.company_section(p, "013810"))   # fx_native 계약은 통화로 표기


if __name__ == "__main__":
    unittest.main()
