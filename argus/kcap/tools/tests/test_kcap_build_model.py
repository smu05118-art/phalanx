# -*- coding: utf-8 -*-
"""원장 조립(kcap_build)·매핑/모델(kcap_model) 계약 — 네트워크 없음. 캐파 fixture 를 임시 캐시로 복사해 원장을 만들고,
스프레드·환율·재무는 합성 입력으로 모델을 돌린다."""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import kcap_lib          # noqa: E402
import kcap_build as B   # noqa: E402
import kcap_model as M   # noqa: E402

FX = os.path.join(HERE, "fixtures")
PMAP = kcap_lib.load_asset("product_map.json")


class TestBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kcap_cache_")
        cls.orig_cache = kcap_lib.CACHE
        kcap_lib.CACHE = cls.tmp
        B.CACHE = cls.tmp
        os.makedirs(os.path.join(cls.tmp, "011170"))
        for q in ("2025Q4", "2026Q2"):
            shutil.copy(os.path.join(FX, "cap_011170_%s.html" % q), os.path.join(cls.tmp, "011170", "%s_cap.html" % q))
            with open(os.path.join(cls.tmp, "011170", "%s_cap.meta.json" % q), "w", encoding="utf-8") as f:
                json.dump({"rcp": "x" + q, "title": "t", "node": "3. 원재료 및 생산설비"}, f)

    @classmethod
    def tearDownClass(cls):
        kcap_lib.CACHE = cls.orig_cache
        B.CACHE = cls.orig_cache
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_period_years(self):
        yrs = B.period_years([("2026년반기(당기)", True), ("2025년(전기)", False)], "2026Q2")
        self.assertEqual(yrs["2026년반기(당기)"], (2026, 6))
        self.assertEqual(yrs["2025년(전기)"], (2025, 12))
        yrs = B.period_years([("제58기반기", True), ("제57기", False), ("제56기", False)], "2026Q2")
        self.assertEqual(yrs["제57기"], (2025, 12))
        self.assertEqual(yrs["제56기"], (2024, 12))

    def test_company_ledger_from_two_reports(self):
        co = B.build_company("011170", "롯데케미칼")
        self.assertEqual(co["quarters"], ["2025Q4", "2026Q2"])
        nc = [p for p in co["products"] if p["product_raw"] == "NC" and "롯데케미칼(주)" in p["entity"]][0]
        self.assertEqual(nc["annual"]["2024"], 3521000.0)
        self.assertEqual(nc["annual"]["2025"], 3521000.0)
        self.assertIn("연간 열", nc["annual_src"]["2025"])
        self.assertIn("연환산", nc["annual_src"]["2026"])
        self.assertEqual(nc["changes"], [])                     # 연간 열끼리 같다
        self.assertIsNone(nc["latest_vs_annual"])               # 연환산 3,521,000 vs 연간 3,521,000
        self.assertEqual(nc["latest"]["quarter"], "2026Q2")
        self.assertEqual(nc["latest"]["util_pct"], 60.7)
        self.assertEqual([u["q"] for u in nc["util_history"]], ["2025Q4", "2026Q2"])
        meg = [p for p in co["products"] if p["product_raw"] == "MEG"][0]
        self.assertTrue({"2024", "2025", "2026"} <= set(meg["annual"]))

    def test_changes_only_between_annual_columns(self):
        # 국도화학: 2026 반기 값(기간값 그대로)의 근거 문구에 '직전 연간 열 없음' 이 들어 있어도 연간 열이 아니다 → 982→506 (−48%) 가짜 축소 금지
        annual = {"2024": 952000.0, "2025": 982000.0, "2026": 506000.0}
        src = {"2024": "2024Q4 보고서 연간 열(미상)", "2025": "2025Q4 보고서 연간 열(미상)",
               "2026": "2026Q2 보고서 당기 연환산(연환산 근거 없음(직전 연간 열 없음) — 기간값 그대로)"}
        changes, lva = B.changes_of(annual, src)
        self.assertEqual(changes, [])
        self.assertEqual(lva["est_year"], "2026")                         # 저신뢰 비교로만 남는다
        annual["2026"] = 0.0
        src["2026"] = "2026Q4 보고서 연간 열(2026년)"
        changes, _ = B.changes_of({"2025": 982000.0, "2026": 1200000.0}, {"2025": src["2025"], "2026": src["2026"]})
        self.assertEqual(changes[0]["kind"], "증설")

    def test_cross_report_annualize(self):
        r = {"capacity_ton_annual": 506000.0, "capacity_period": 506000.0, "ton_mul": 1.0, "basis": "연환산 근거 없음(직전 연간 열 없음) — 기간값 그대로"}
        val, basis = B.cross_report_annualize(r, 6, 982000.0)             # 원장의 2025 연간 982kt 대비 52% → 기간비례
        self.assertEqual(val, 1012000.0)
        self.assertIn("원장 직전 연도", basis)
        val, basis = B.cross_report_annualize(dict(r, capacity_ton_annual=932000.0, capacity_period=932000.0), 6, 932000.0)
        self.assertEqual(val, 932000.0)                                   # 명판 그대로(100%)
        self.assertEqual(B.cross_report_annualize(r, 6, None), (506000.0, r["basis"]))    # 근거 없으면 그대로
        self.assertEqual(B.cross_report_annualize(dict(r, basis="기간비례(6개월)→연환산"), 6, 982000.0)[0], 506000.0)   # 파서가 이미 판정한 건 건드리지 않는다


SYN_REG = {
    "argus_asof": "2026-10-05", "fingerprint": "f",
    "rows": [
        {"sid": "sp_에틸렌_납사_스프레드_한국", "name": "에틸렌-납사 스프레드(한국)", "product": "에틸렌", "region": "한국", "layer": "integrated", "kind": "spread", "reproduced": True},
        {"sid": "sp_에틸렌_납사_스프레드_일본", "name": "에틸렌-납사 스프레드(일본)", "product": "에틸렌", "region": "일본", "layer": "integrated", "kind": "spread", "reproduced": True},
        {"sid": "sp_pp_homo_프로필렌_스프레드_한국", "name": "PP(Homo)-프로필렌 스프레드(한국)", "product": "PP(Homo)", "region": "한국", "layer": "step", "kind": "spread", "reproduced": True},
        {"sid": "sp_프로필렌_납사_스프레드_한국", "name": "프로필렌-납사 스프레드(한국)", "product": "프로필렌", "region": "한국", "layer": "integrated", "kind": "spread", "reproduced": True},
    ],
    "derived": [],
}


def syn_data():
    import datetime
    d0 = datetime.date(2024, 1, 1)
    dates = [(d0 + datetime.timedelta(days=7 * i)).isoformat() for i in range(140)]    # 2024-01-01 ~ 2026-08-31
    ramp = [100.0 + 2.0 * i for i in range(140)]                                        # 주마다 오르는 스프레드 — 회귀가 정의되게
    return {"axes": {"wk": dates}, "series": {
        "sp_에틸렌_납사_스프레드_한국": {"axis": "wk", "v": ramp},
        "sp_에틸렌_납사_스프레드_일본": {"axis": "wk", "v": [v + 10 for v in ramp]},
        "sp_pp_homo_프로필렌_스프레드_한국": {"axis": "wk", "v": [100.0] * 140},
        "sp_프로필렌_납사_스프레드_한국": {"axis": "wk", "v": [150.0] * 140},
    }}


class TestModel(unittest.TestCase):
    def test_map_product(self):
        self.assertEqual([(m["token"], m["share"]) for m in M.map_product("NC", PMAP)], [("에틸렌", 0.6), ("프로필렌", 0.4)])
        self.assertEqual(M.map_product("LDPE 등", PMAP)[0]["token"], "LDPE")
        self.assertEqual(M.map_product("Ethylene", PMAP)[0]["token"], "에틸렌")
        self.assertEqual(M.map_product("방향족(PX)", PMAP)[0]["token"], "PX")
        self.assertEqual(M.map_product("EO/EG", PMAP)[0]["token"], "MEG")
        m = M.map_product("과산화수소, TDI", PMAP)
        self.assertEqual([(x["token"], x["share"]) for x in m], [("TDI", 0.5)])    # 매핑 안 된 부분 몫은 빠진다
        self.assertEqual(M.map_product("인조대리석", PMAP), [])
        self.assertEqual(M.map_product("가성소다(50%)", PMAP)[0]["token"], "가성소다")

    def test_spread_candidates_prefers_korea_and_step(self):
        sc = M.spread_candidates("에틸렌", SYN_REG, PMAP)
        self.assertEqual(sc[0][0], "sp_에틸렌_납사_스프레드_한국")
        sc = M.spread_candidates("PP", SYN_REG, PMAP)        # 복합 PP → PP(Homo)
        self.assertEqual([s[0] for s in sc], ["sp_pp_homo_프로필렌_스프레드_한국"])
        self.assertEqual(M.spread_candidates("가성소다", SYN_REG, PMAP), [])

    def test_quarter_means_and_ols(self):
        qm, last = M.quarter_means(syn_data(), "sp_pp_homo_프로필렌_스프레드_한국")
        self.assertEqual(qm["2025Q1"][0], 100.0)
        self.assertEqual(qm["2025Q1"][1], 13)
        self.assertEqual(last, "2026-08-31")
        fit = M.ols([1, 2, 3, 4], [3, 5, 7, 9])
        self.assertAlmostEqual(fit["a"], 1.0)
        self.assertAlmostEqual(fit["b"], 2.0)
        self.assertAlmostEqual(fit["r2"], 1.0)

    def test_util_series_cumulative_diff(self):
        p = {"by_report": {
            "2025Q1": {"capacity_ton_annual": 1000.0, "output_period": 200.0, "ton_mul": 1.0, "util_pct": 80.0, "months": 3},
            "2025Q2": {"capacity_ton_annual": 1000.0, "output_period": 450.0, "ton_mul": 1.0, "util_pct": 90.0, "months": 6},
            "2025Q4": {"capacity_ton_annual": 1000.0, "output_period": 900.0, "ton_mul": 1.0, "util_pct": 90.0, "months": 12},
        }}
        u = M.util_series(p, ["2025Q1", "2025Q2", "2025Q3", "2025Q4"])
        self.assertEqual(u["2025Q1"], (80.0, "누적차분"))
        self.assertEqual(u["2025Q2"][0], 100.0)                 # (450−200)/(1000/4)
        self.assertEqual(u["2025Q3"][1], "같은 해 뒤 보고서 기간 가동률")
        self.assertEqual(u["2025Q4"][1], "보고 기간 가동률(12개월)")   # 직전(9M) 누적이 없어 차분 불가 → 보고 가동률

    def test_util_series_uses_ton_converted_output(self):
        # GS '천톤' 표: 생산실적 527(천톤) 을 생산능력 1,338,000톤과 같은 단위로 바꿔 나눈다 — 원문 단위 그대로 나누면 0.08% 가 된다
        p = {"by_report": {
            "2026Q1": {"capacity_ton_annual": 1332000.0, "output_period": 263.0, "output_ton_period": 263000.0, "ton_mul": 1000.0, "util_pct": 80.0, "months": 3},
            "2026Q2": {"capacity_ton_annual": 1338000.0, "output_period": 527.0, "output_ton_period": None, "ton_mul": 1000.0, "util_pct": 79.0, "months": 6},
        }}
        u = M.util_series(p, ["2026Q1", "2026Q2"])
        self.assertAlmostEqual(u["2026Q1"][0], 100.0 * 263000.0 / (1332000.0 / 4), places=6)
        self.assertAlmostEqual(u["2026Q2"][0], 100.0 * (527000.0 - 263000.0) / (1338000.0 / 4), places=6)   # output_ton_period 가 없으면 ton_mul 로

    def test_util_series_negative_diff_falls_back(self):
        # 반기 누적(164,036)이 1분기(172,992)보다 작은 원문 불일치(한화솔루션 LDPE) — 음수 차분은 버리고 보고 가동률
        p = {"by_report": {
            "2026Q1": {"capacity_ton_annual": 932000.0, "output_period": 172992.0, "output_ton_period": 172992.0, "ton_mul": 1.0, "util_pct": 74.2, "months": 3},
            "2026Q2": {"capacity_ton_annual": 932000.0, "output_period": 164036.0, "output_ton_period": 164036.0, "ton_mul": 1.0, "util_pct": 35.2, "months": 6},
        }}
        u = M.util_series(p, ["2026Q1", "2026Q2"])
        self.assertEqual(u["2026Q2"], (35.2, "보고 기간 가동률(6개월)·누적차분 불일치"))

    def test_build_company_fit_and_estimate(self):
        co = {"name": "합성", "products": [
            {"key": "k1", "product_raw": "Ethylene", "entity": "", "site": "", "is_ton": True, "aggregate": False,
             "latest": {"quarter": "2026Q2", "capacity_ton_annual": 1000000.0, "basis": "연간", "util_pct": 90.0},
             "by_report": {"2026Q2": {"capacity_ton_annual": 1000000.0, "output_period": 450000.0, "ton_mul": 1.0, "util_pct": 90.0, "months": 6}}},
            {"key": "k2", "product_raw": "PIA", "entity": "", "site": "", "is_ton": True, "aggregate": False,
             "latest": {"quarter": "2026Q2", "capacity_ton_annual": 100000.0, "basis": "연간", "util_pct": 50.0}, "by_report": {}},
        ]}
        fx = {q: 1300.0 for q in M.q_range("2023Q1", "2026Q4")}
        data = syn_data()
        qm, _ = M.quarter_means(data, "sp_에틸렌_납사_스프레드_한국")
        # 영업이익 = 0.5 × 프록시 + 100 (억원) 로 만든 합성 재무 — 프록시 = 캐파/4 × 가동률 90%(2026Q2 보고, 나머지 분기는 중앙값 폴백) × 분기평균 스프레드 × 환율
        def proxy(q):
            return 1000000.0 / 4 * 0.9 * qm[q][0] * 1300.0 / 1e8
        fin = {"quarters": [{"q": q, "op_q": (0.5 * proxy(q) + 100) * 100, "rev_q": 1e6, "basis": "cons"} for q in ("2025Q3", "2025Q4", "2026Q1", "2026Q2")]}
        proxy_q = proxy("2026Q3")
        mc = M.build_company("000000", co, SYN_REG, data, fx, "2026-10-01", PMAP, fin, "2026-10-05")
        self.assertTrue(mc["promoted"])
        self.assertEqual([u["product_raw"] for u in mc["unmapped"]], ["PIA"])
        self.assertAlmostEqual(mc["coverage_pct"], 90.9, 1)
        self.assertEqual(mc["last_fin_q"], "2026Q2")
        self.assertIsNotNone(mc["fit"])
        self.assertAlmostEqual(mc["fit"]["b"], 0.5, 3)
        self.assertAlmostEqual(mc["fit"]["a"], 100.0, delta=0.5)   # 프록시 반올림(0.1억원) 오차
        ests = mc["estimates"]
        self.assertEqual([e["q"] for e in ests], ["2026Q3", "2026Q4"])
        self.assertAlmostEqual(ests[0]["proxy_eok"], round(proxy_q, 1), 0)
        self.assertAlmostEqual(ests[0]["op_fit_eok"], round(0.5 * proxy_q + 100, 1), 0)
        self.assertIn("스프레드 가정", ests[1]["assumed"])      # 2026Q4 는 관측 없음 → 최근 13주 가정
        self.assertEqual(mc["stale_weeks"], 5)                   # 2026-08-31 → 2026-10-05


if __name__ == "__main__":
    unittest.main()
