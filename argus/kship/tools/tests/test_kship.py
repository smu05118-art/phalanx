#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국조선 파이프라인 계약 테스트.

실행: cd argus/kship/tools && python3 -m unittest discover -s tests
원문 픽스처: HD현대중공업 2026 반기 수주상황(부문 롤포워드)·척당 계약 공시(LPGC 4척).
"""
import contextlib
import io
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, TOOLS)

import kship_lib as L                                     # noqa: E402
from kship_parse import parse_orders, unit_of, is_total   # noqa: E402
from kship_contracts import parse_contract, ship_type_of  # noqa: E402
from kship_yards import parse_orders_table, parse_revenue_table  # noqa: E402
from kship_suppliers import classify_product              # noqa: E402
import kship_universe as U                                # noqa: E402


def _fx(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class TestUnits(unittest.TestCase):
    def test_currency_and_scale(self):
        self.assertEqual(unit_of("(단위 : 백만달러, 척)"), ("USD", 1.0, True))
        self.assertEqual(unit_of("(단위 : 천달러)"), ("USD", 0.001, True))
        self.assertEqual(unit_of("(단위 : 억원)"), ("KRW", 100.0, True))
        self.assertEqual(unit_of("", ["(단위 : 천원) 품목"]), ("KRW", 0.001, True))
        self.assertEqual(unit_of("")[2], False)          # 단위를 못 읽으면 unit_seen=False

    def test_total_rows(self):
        for s in ("합 계", "합계", "총계", "소계"):
            self.assertTrue(is_total(s), s)
        for s in ("조 선", "LNG운반선", "기 타", "기본설계"):
            self.assertFalse(is_total(s), s)


class TestShipOrdersTable(unittest.TestCase):
    """조선 수주표 방언: 척수 열 보존 · 합계행 보존 · 달러 단위."""

    HTML = """<p>가. 수주상황</p><p>(단위 : 백만달러, 척)</p><table>
<tr><td rowspan=2>선종</td><td colspan=2>수주총액</td><td colspan=2>기납품액</td><td colspan=2>수주잔고</td><td rowspan=2>인도예정</td></tr>
<tr><td>수량</td><td>금액</td><td>수량</td><td>금액</td><td>수량</td><td>금액</td></tr>
<tr><td>LNG운반선</td><td>42</td><td>10,500.5</td><td>12</td><td>3,000</td><td>30</td><td>7,500.5</td><td>2026~2029</td></tr>
<tr><td>합 계</td><td>42</td><td>10,500.5</td><td>12</td><td>3,000</td><td>30</td><td>7,500.5</td><td>-</td></tr></table>"""

    def test_quantity_total_currency(self):
        r = parse_orders(self.HTML)
        self.assertEqual(r["unknown_headers"], [])
        t = r["tables"][0]
        self.assertEqual(t["cur"], "USD")
        rows = t["rows"]
        self.assertEqual(rows[0]["qty"], 42)
        self.assertEqual(rows[0]["qty_bal"], 30)
        self.assertAlmostEqual(rows[0]["bal"], 7500.5)
        self.assertTrue(rows[1]["total"])                 # 합계행이 사라지지 않는다
        self.assertEqual(t["n"], 1)


class TestYardRollforward(unittest.TestCase):
    """HD현대중공업 2026 반기 원문 — 부문 롤포워드와 매출실적."""

    def test_rollforward_from_fixture(self):
        from kship_lib import parse_tables
        tabs = parse_tables(_fx("hhi_orders_2026H1.html"))
        orders = [x for x in (parse_orders_table(t) for t in tabs if t["cols"]) if x and x["rows"]]
        self.assertTrue(orders)
        o = max(orders, key=lambda o: len(o["rows"]))
        tot = [r for r in o["rows"] if r["total"]][0]
        self.assertEqual(tot["closing"], 69514154)
        self.assertEqual(tot["opening"] + tot["new"] - tot["delivered"], tot["closing"])
        segs = {r["seg"].replace(" ", ""): r for r in o["rows"] if not r["total"]}
        self.assertEqual(segs["조선"]["closing"], 55573921)
        self.assertEqual(o["cur"], "KRW")

    def test_revenue_from_fixture(self):
        from kship_lib import parse_tables
        tabs = parse_tables(_fx("hhi_orders_2026H1.html"))
        rev = [x for x in (parse_revenue_table(t) for t in tabs if t["cols"]) if x]
        self.assertTrue(rev)
        rows = rev[0]["rows"]
        ship_export = [r for r in rows if r["seg"].replace(" ", "") == "조선" and r["kind"] == "수출"][0]
        self.assertEqual(ship_export["vals"][0], 8882303)


class TestContract(unittest.TestCase):
    def test_parse_contract_fixture(self):
        r = parse_contract(_fx("hhi_contract_20260824800122.html"), "20260824800122", "단일판매ㆍ공급계약체결", "329180")
        self.assertEqual(r["name"], "LPGC 4척")
        self.assertEqual(r["type"], "VLGC")
        self.assertEqual(r["ships"], 4)
        self.assertEqual(r["amt_krw_m"], 515400.0)
        self.assertEqual(r["end"], "2030-03-31")
        self.assertTrue(r["party_anon"])
        self.assertEqual(r["payterm"], "공사진척에 따른 수금")

    def test_new_krx_template_fields(self):
        """2025~ 신형 서식: 계약명이 '판매ㆍ공급계약 구분/세부내용'에, 수주일 라벨이 '계약(수주)일'."""
        from kship_contracts import _fields_from_kv, _kv_from_raw
        raw = [("1. 판매ㆍ공급계약 구분", "공사수주"), ("- 세부내용", "VLCC 2척"),
               ("2. 계약내역 계약금액(원)", "349,000,000,000"), ("3. 계약상대", "아시아 소재 선사"),
               ("4. 판매ㆍ공급지역", "아시아"), ("5. 계약기간 시작일", "2025-06-12"), ("5. 계약기간 종료일", "2027-08-31"),
               ("6. 주요 계약조건 계약금ㆍ선급금 유무", "유"), ("7. 계약(수주)일", "2025-06-12")]
        f = _fields_from_kv(_kv_from_raw(raw))
        self.assertEqual((f["name"], f["type"], f["ships"], f["amt_krw_m"], f["signed"], f["end"], f["region"]),
                         ("VLCC 2척", "VLCC", 2, 349000.0, "2025-06-12", "2027-08-31", "아시아"))
        # 정정공시: 앞에 붙는 정정 표의 '5. 계약기간 -종료일 2029-03-31'→'2028-11-30' 은 본표 값을 덮지 않는다
        raw2 = [("정정항목 정정전", "정정후"), ("5. 계약기간 -종료일 2029-03-31", "2028-11-30")] + raw
        self.assertEqual(_fields_from_kv(_kv_from_raw(raw2))["end"], "2027-08-31")

    def test_ship_type_tokens(self):
        cases = {"LPGC 4척": "VLGC", "LNG운반선 2척": "LNGC", "17,000TEU급 컨테이너선 6척": "CONT",
                 "VLCC 2척": "VLCC", "MR탱커 4척": "PC", "PCTC 4척": "PCTC", "KDDX 1척": "NAVAL",
                 "FPSO 1기": "OFFSH", "보령화력 1~8호기 저탄장 옥내화 공사": "OTHER",
                 "엔진발전기 공급": "OTHER", "다목적 화학방제함 1척 건조": "NAVAL",
                 "초대형 LPG/AMMONIA 운반선 1척": "VLGC", "부산 범천5구역 재개발정비사업": "OTHER",
                 "KSS-II 성능개량 체계개발사업": "NAVAL", "필리핀 따굼 홍수조절사업": "OTHER"}
        for name, want in cases.items():
            self.assertEqual(ship_type_of(name), want, name)


class TestHedgeNote(unittest.TestCase):
    """주석의 '당반기말' 표 뒤에 오는 '전기말' 비교표를 더하면 명목액이 두 배가 된다(삼성重 482억달러 오류의 원인)."""

    def test_hedge_note_skips_prior_period(self):
        from kship_yards import parse_hedge_any
        tbl = ("<table><tr><th></th><th>금융상품 파생상품 파생상품1 위험회피 매매 목적</th></tr>"
               "<tr><td>외화파생상품 매도금액, USD [USD, 천]</td><td>%s</td></tr></table>")
        html = ("<p>위험회피에 대한 세부 정보 공시 당반기말 (단위 : 천원)</p>" + tbl % "1,000,000"
                + "<p>전기말 (단위 : 천원)</p>" + tbl % "2,000,000")
        h = parse_hedge_any(html, "note")
        self.assertEqual(h["shape"], "note-label")
        self.assertEqual(h["usd_sell_m"], 1000.0)            # 천달러 → 백만달러, 전기 표 제외
        # 기간 표기가 없어도 같은 라벨 묶음이 반복되면 뒤 표는 비교표시다
        html2 = "<p>(단위 : 천원)</p>" + tbl % "1,000,000" + "<p>(단위 : 천원)</p>" + tbl % "2,000,000"
        self.assertEqual(parse_hedge_any(html2, "note")["usd_sell_m"], 1000.0)


class TestHedgeNoteColumns(unittest.TestCase):
    def test_hedge_note_uses_total_column(self):
        """사업보고서 주석: 멤버마다 목적별 3열 + 합계 열 — 합계 열만 세어야 두 배가 되지 않는다."""
        from kship_yards import parse_hedge_any
        html = ("<p>당기 (단위 : 천원)</p><table><tr><th></th><th>파생상품1 매매 목적</th><th>파생상품1 공정가치위험회피</th>"
                "<th>파생상품1 현금흐름위험회피</th><th>파생상품1 합계</th></tr>"
                "<tr><td>외화파생상품 매도금액, USD [USD, 천]</td><td>1,000</td><td>2,000</td><td>3,000</td><td>6,000</td></tr></table>")
        self.assertEqual(parse_hedge_any(html, "note")["usd_sell_m"], 6.0)
        # 멤버별 합계 열 + 총합계 열(삼성重 사업보고서): 총합계만
        html2 = ("<p>당기 (단위 : 천원)</p><table><tr><th></th><th>통화 관련 파생상품5 파생상품 목적의 지정 합계</th>"
                 "<th>통화 관련 파생상품15 파생상품 목적의 지정 합계</th><th>파생상품 계약 유형 합계</th></tr>"
                 "<tr><td>외화파생상품 매도금액, USD [USD, 천]</td><td>1,000</td><td>5,000</td><td>6,000</td></tr></table>")
        self.assertEqual(parse_hedge_any(html2, "note")["usd_sell_m"], 6.0)


class TestTaxonomy(unittest.TestCase):
    """정적 사전의 교차 참조가 깨지면 인포그래픽이 잘못된 회사를 보여 준다."""

    def test_rel_keys_match_categories(self):
        tax = L.load_asset("parts_taxonomy.json")
        st = L.load_asset("ship_types.json")
        cat_ids = {c["id"] for c in tax["cats"]}
        for tid, row in st["rel"].items():
            self.assertEqual(set(row), cat_ids, tid)

    def test_regions_reference_existing_categories(self):
        tax = L.load_asset("parts_taxonomy.json")
        svg = L.load_asset("svg_regions.json")
        cat_ids = {c["id"] for c in tax["cats"]}
        for r in svg["regions"] + svg["engine_zoom"]["regions"]:
            for c in r["cats"]:
                self.assertIn(c, cat_ids, r["id"])

    def test_classify_examples(self):
        self.assertIn("CARGO.LNG", classify_product("초저온 보냉재", True))
        self.assertIn("PIPE.FITTING", classify_product("관이음쇠", True))
        self.assertIn("ENG.PARTS", classify_product("선박엔진부품", False))
        self.assertIn("PROP.MAIN", classify_product("대형선박용엔진", False))
        self.assertEqual(classify_product("XML/SGML 관련 제품 및 솔루션", False), ["UNCL"])
        # 문맥 필요 낱말은 해상 문맥이 없으면 채택하지 않는다(육상 밸브·크레인 오탐 방지)
        self.assertEqual(classify_product("볼밸브", False), ["UNCL"])
        self.assertIn("PIPE.VALVE", classify_product("선박용 볼밸브", False))


class TestPageShell(unittest.TestCase):
    def test_external_scripts_precede_body(self):
        h = L.page("t", "<script>Chart.x</script>", depth=1, scripts=("../vendor/chart.umd.min.js",))
        self.assertLess(h.index("chart.umd.min.js"), h.index("Chart.x"))
        self.assertIn('href="../assets/kship.css"', h)

    def test_json_for_html_escapes_script_close(self):
        s = L.json_for_html({"nm": "악성</script><img>"})
        self.assertNotIn("</script>", s)


class TestUniverseExplored(unittest.TestCase):
    """모집단 ④ 탐색 행 — probe 에 판정이 없으면 유지, 강등은 probe 의 명시적 rejected(ok=True)만.
    2026-09-12 스캔이 promoted 를 {} 로 덮어 '탐색' 16행이 지워진 회귀(57→41)의 두 번째 방어선."""

    NANO = {"stock": "187790", "name": "나노", "market": "KOSDAQ", "industry": "기초 화학물질 제조업", "product": "SCR촉매", "listed": ""}
    PREV = {"187790": {"stock": "187790", "source": "탐색", "role": "equip",
                       "reason": "탐색 — 정기보고서 본문: 조선 낱말 10회(선박 10) · 나노 — 선박용 SCR 탈질촉매"}}

    def _recs(self):
        # MIN_UNIVERSE(20) 을 넘기려고 조선업 업종 20행을 깐다 — 나노는 업종·제품·지정 어느 경로에도 걸리지 않는다.
        yards = [{"stock": "%06d" % i, "name": "조선%d" % i, "market": "KOSPI", "industry": U.YARD_INDUSTRY,
                  "product": "선박건조", "listed": ""} for i in range(1, 21)]
        return yards + [dict(self.NANO)]

    def _select(self, probe, prev):
        with contextlib.redirect_stderr(io.StringIO()):
            return U.select(self._recs(), probe=probe, prev_explored=prev)

    def test_kept_without_probe_verdict(self):
        picked = self._select({"promoted": {}, "rejected": [], "failed": []}, self.PREV)
        row = next(r for r in picked if r["stock"] == "187790")
        self.assertEqual(row["source"], "탐색")
        self.assertEqual(row["role"], "equip")
        self.assertEqual(row["reason"], self.PREV["187790"]["reason"])

    def test_kept_when_probe_failed_or_unread(self):
        probe = {"promoted": {}, "failed": [{"stock": "187790", "err": "timed out"}],
                 "rejected": [{"stock": "187790", "ok": False, "hits": 0, "note": "II 절을 찾지 못함"}]}
        self.assertIn("187790", [r["stock"] for r in self._select(probe, self.PREV)])

    def test_demoted_only_by_explicit_rejected(self):
        probe = {"promoted": {}, "rejected": [{"stock": "187790", "ok": True, "hits": 1, "mentions": {}}], "failed": []}
        self.assertNotIn("187790", [r["stock"] for r in self._select(probe, self.PREV)])

    def test_fresh_promotion_wins_over_prev_row(self):
        probe = {"promoted": {"187790": {"role": "engine", "reason": "탐색 — 새 증거"}}, "rejected": [], "failed": []}
        row = next(r for r in self._select(probe, self.PREV) if r["stock"] == "187790")
        self.assertEqual((row["source"], row["role"], row["reason"]), ("탐색", "engine", "탐색 — 새 증거"))

    def test_not_selected_without_prev_or_probe(self):
        self.assertNotIn("187790", [r["stock"] for r in self._select({}, {})])

    def test_probe_demoted_reads_only_ok_rows(self):
        probe = {"rejected": [{"stock": "A", "ok": True}, {"stock": "B", "ok": False}, {"stock": "C"}]}
        self.assertEqual(U.probe_demoted(probe), {"A", "C"})          # ok 키가 없는 옛 행은 본문을 읽은 판정으로 본다



import tempfile                                            # noqa: E402
import kship_suppliers as SUP                              # noqa: E402


class TestYardNames(unittest.TestCase):
    """영문 약칭의 단어 경계 — 'SHI' 가 HANSHIN·SHIPYARD 에, 'HHI' 가 HHIC 에 걸려 가짜 언급을 만들던 회귀(2026-10-05 주석 캐시 실측:
    한신기계 종속기업 'HANSHIN JAPAN' 이 삼성重 언급으로 셌다)."""

    def test_abbreviations_need_word_boundary(self):
        self.assertEqual(SUP.find_yard_mentions("HANSHIN JAPAN SHIPYARD SHIPBUILDING HHIC"), {})
        self.assertEqual(SUP.find_yard_mentions("삼성중공업(SHI) 및 HD현대중공업(HHI), DSME"), {"010140": 2, "329180": 2, "042660": 1})
        # 조선과 무관한 HD현대 계열·지주는 그룹(모호) 언급으로 세지 않는다
        self.assertEqual(SUP.find_yard_mentions("HD현대오일뱅크·HD현대사이트솔루션·HD현대㈜ 와 HD현대 그룹"), {"KSOE_GRP": 1})

    def test_major_customer_sentence_normalizes_party(self):
        cs = SUP.parse_major_customers("<p>당사 매출기준으로 현대중공업 41.6%, 해외 SHIPYARD 30%</p>")
        self.assertEqual([(c["yard"], c["share"]) for c in cs], [("329180", 41.6)])


class TestParseProducts(unittest.TestCase):
    STD = """<p>가. 주요 제품 등의 현황</p><p>(단위 : 백만원, %)</p>
<table><thead><tr><th>사업부문</th><th>매출유형</th><th>품 목</th><th>구체적용도</th><th>매출액</th><th>비율</th></tr></thead>
<tbody><tr><td>조선기자재</td><td>제품</td><td>Deck House</td><td>거주구</td><td>120,000</td><td>60.0</td></tr>
<tr><td>조선기자재</td><td>제품</td><td>LPG Tank</td><td>화물창</td><td>80,000</td><td>40.0</td></tr>
<tr><td colspan=4>합 계</td><td>200,000</td><td>100.0</td></tr></tbody></table>"""

    def test_picks_item_column_over_sales_type(self):
        rows = SUP.parse_products(self.STD)
        self.assertEqual([(r["prod"], r["share"], r["amt"], r.get("seg")) for r in rows],
                         [("Deck House", 60.0, 120000.0, "조선기자재"), ("LPG Tank", 40.0, 80000.0, "조선기자재")])

    def test_generic_values_column_is_skipped(self):
        # 한선엔지니어링 꼴: '구분' 열이 앞에 있고 값은 제품/상품뿐 — 다음 후보('품목')로 넘어가야 '제품'×9 가 되지 않는다
        html = """<table><tr><th>구분</th><th>품목</th><th>매출액</th><th>비중</th></tr>
<tr><td>제품</td><td>계장용 피팅</td><td>19,641</td><td>42.67</td></tr><tr><td>제품</td><td>밸브</td><td>8,843</td><td>19.21</td></tr>
<tr><td>상품</td><td>모듈</td><td>1,735</td><td>3.77</td></tr></table>"""
        self.assertEqual([r["prod"] for r in SUP.parse_products(html)], ["계장용 피팅", "밸브", "모듈"])

    def test_td_header_with_period_columns(self):
        # <td> 머리행 + 기간 열(제41기 반기) — kce_parse 가 머리로 보지 않아 30사 products 가 비던 꼴. 합계 행으로 비중을 만든다(추정).
        html = """<p>(단위 : 백만원)</p><table><tr><td>품목</td><td>제41기 반기</td><td>제40기</td></tr>
<tr><td>보냉재</td><td>900</td><td>800</td></tr><tr><td>가스</td><td>100</td><td>120</td></tr><tr><td>합계</td><td>1,000</td><td>920</td></tr></table>"""
        rows = SUP.parse_products(html)
        self.assertEqual([(r["prod"], r["amt"], r["share"], r.get("share_est")) for r in rows],
                         [("보냉재", 900.0, 90.0, True), ("가스", 100.0, 10.0, True)])
        html2 = """<table><tr><td>사업부문</td><td>매출유형</td><td>품 목</td><td>2026년 반기</td><td>2025년</td></tr>
<tr><td>조선</td><td>제품</td><td>보냉재</td><td>1,000</td><td>900</td></tr></table>"""
        self.assertEqual([(r["prod"], r["amt"], r.get("seg")) for r in SUP.parse_products(html2)], [("보냉재", 1000.0, "조선")])
        # 머리처럼 보이지 않는 표(첫 행에 숫자)는 그대로 버린다 — 품목 낱말 없는 표도
        self.assertEqual(SUP.parse_products("<table><tr><td>보냉재</td><td>1,000</td></tr></table>"), [])


class TestParseProductsFixture(unittest.TestCase):
    """동성화인텍 2026 반기 「2. 주요 제품 및 서비스」 원문(DART 2026-10-05 2요청 진단, rcp 20260814002437) — 2026Q2 캐시 51사 중 30사의
    products 가 빈 원인 그대로: <td> 머리행 '사업부문 | 매출 유형 | 품 목 | 구체적 용도 | 주요상표등 | 매출액 (비율)' 과 결합 셀
    '376,610(95.7%)'. 뒤따르는 '나. 가격변동추이' 표(품목 × 제42기 반기, 단위 원)는 매출이 아니라 건너뛰어야 한다."""

    def test_real_section_parses_sales_not_prices(self):
        rows = SUP.parse_products(_fx("suppliers_products_033500_2026Q2.html"))
        self.assertEqual([(r["prod"], r["amt"], r["share"], r.get("seg"), r.get("use")) for r in rows],
                         [("R-PUF 외", 376610.0, 95.7, "PU 단열재 사 업 부 문", "초저온보냉재 가정/산업/건축 단열재"),
                          ("HCFC-22 외", 17053.0, 4.3, "가 스 사 업 부 문", "냉매가스")])
        self.assertNotIn("초저온보냉재", [r["prod"] for r in rows])                 # 가격표 행이 섞이지 않는다
        self.assertEqual(SUP._amt_share("376,610(95.7%)"), (376610, 95.7))
        self.assertEqual(SUP._amt_share("376,610"), (None, None))

    def test_fixture_rows_classify_to_lng_insulation(self):
        rec = {"stock": "033500", "name": "동성화인텍", "market": "KOSDAQ", "industry": "기초 화학물질 제조업", "product": "PU단열재", "role": "equip",
               "source": "지정", "reason": ""}
        d = {"ok": True, "marine_ctx": True, "products": SUP.parse_products(_fx("suppliers_products_033500_2026Q2.html")), "mentions": {}, "customers": []}
        co, uncl, _ = SUP.build_company(rec, d, {}, None)
        self.assertEqual([(c["cat"], c["share"]) for c in co["cats"] if c["cat"] != "UNCL"], [("CARGO.LNG", 95.7)])
        self.assertEqual(uncl, [("033500", "동성화인텍", "HCFC-22 외")])              # 냉매는 조선 부품이 아니다 — 정직한 미분류


class TestSuppliersBuild(unittest.TestCase):
    REC = {"stock": "999999", "name": "테스트기자재", "market": "KOSDAQ", "industry": "일반 목적용 기계 제조업",
           "product": "선박용 밸브", "role": "equip", "source": "지정", "reason": "테스트기자재 — 선박용 밸브"}

    def test_skip_reason(self):
        for s in ("제 품", "상품", "기타 계", "기 타 주)", "-", "내부거래", "연결조정", "합계", "기 타 매 출"):
            self.assertEqual(SUP.skip_reason(s), "구분", s)
        self.assertEqual(SUP.skip_reason("스크랩, 고철등 판매外"), "부산물")
        self.assertIsNone(SUP.skip_reason("선박용 밸브"))
        self.assertIsNone(SUP.skip_reason("기타제품(선박용)"))

    def test_build_company_merges_yards_and_dedupes(self):
        d = {"ok": True, "marine_ctx": True, "rcp": "r1", "quarter": "2026Q2",
             "products": [{"prod": "선박용 밸브", "share": 60.0, "amt": None, "cur": "KRW"},
                          {"prod": "제품 계", "share": 100.0, "amt": None, "cur": "KRW"},
                          {"prod": "스크랩 판매", "share": 1.0, "amt": None, "cur": "KRW"},
                          {"prod": "WZ3300PTA 외", "share": 2.0, "amt": None, "cur": "KRW"},
                          {"prod": "WZ3300PTA 외", "share": 0.5, "amt": None, "cur": "KRW"}],
             "mentions": {"329180": 2, "010140": 1},
             "customers": [{"party": "매출기준으로 현대중공업", "share": 41.6, "basis": "text"}]}      # 옛 캐시 — yard 키 없음
        notes = {"q": "2025Q3", "ifrs8": [{"yard": "010140", "evidence": "주요고객 … 삼성중공업(주) 등"}],
                 "related": [{"yard": "042660", "sales_m": 1234.0, "share_est": 3.21, "evidence": "특수관계자 거래 매출 1,234,000"}]}
        co, uncl, skipped = SUP.build_company(self.REC, d, {}, notes)
        self.assertEqual(skipped, 2)                                                   # '제품 계'·'스크랩 판매'
        self.assertEqual(uncl, [("999999", "테스트기자재", "WZ3300PTA 외")])             # 되풀이 행은 한 번만
        self.assertEqual(sum(1 for c in co["cats"] if c["cat"] == "UNCL"), 1)
        self.assertEqual([y["yard"] for y in co["yards"]], ["010140", "042660", "329180"])   # 등급순 ifrs8 > related > text
        ys = {y["yard"]: y for y in co["yards"]}
        self.assertEqual((ys["329180"]["basis"], ys["329180"]["mentions"], ys["329180"]["share"], ys["329180"]["share_est"]), ("text", 2, 41.6, False))
        self.assertEqual((ys["010140"]["basis"], ys["010140"]["mentions"]), ("ifrs8", 1))
        self.assertEqual((ys["042660"]["basis"], ys["042660"]["share"], ys["042660"]["share_est"]), ("related", 3.21, True))
        self.assertEqual((co["link_basis"], co["confirmed"], co["notes_q"]), ("ifrs8", True, "2025Q3"))
        self.assertTrue(all(y["yard"].isdigit() or y["yard"] in ("HSHI", "KSOE_GRP") for y in co["yards"]))   # 문장 조각이 yard 가 되지 않는다

    def test_related_share_beats_sentence_share(self):
        # 현대힘스 실측: 문장 조각 95% 는 두 조선사 합산 — 조선사별 금액이 있는 특수관계자 표의 추정이 앞선다
        d = {"ok": True, "marine_ctx": True, "products": [], "mentions": {"329180": 12},
             "customers": [{"party": "일고객은 HD현대중공업", "yard": "329180", "share": 95.0, "basis": "text"}]}
        notes = {"q": "2025Q3", "ifrs8": [{"yard": "329180", "evidence": "단일고객은 HD현대중공업㈜"}],
                 "related": [{"yard": "329180", "sales_m": 74429.447, "share_est": 41.06, "evidence": "특수관계자 거래 매출 74,429,447"}]}
        co, _, _ = SUP.build_company(dict(self.REC, reason=""), d, {}, notes)
        y = co["yards"][0]
        self.assertEqual((y["yard"], y["basis"], y["share"], y["share_est"], y["mentions"]), ("329180", "ifrs8", 41.06, True, 12))
        self.assertEqual([e["basis"] for e in y["evidence"]], ["ifrs8", "related", "text"])

    def test_override_is_manual_basis(self):
        d = {"ok": True, "marine_ctx": True, "products": [{"prod": "기계품", "share": 50.0, "amt": None, "cur": "KRW"}], "mentions": {}, "customers": []}
        co, uncl, _ = SUP.build_company(dict(self.REC, reason=""), d, {("999999", "기계품"): "DECK.CRANE"}, None)
        self.assertEqual([(c["cat"], c["basis"], c["est"]) for c in co["cats"]], [("DECK.CRANE", "manual", False)])
        self.assertEqual((uncl, co["yards"], co["confirmed"], co["link_basis"]), ([], [], False, None))

    def test_segment_fallback_marks_estimate(self):
        d = {"ok": True, "marine_ctx": True, "products": [{"prod": "EH2350PTA-2260 외", "share": 1.7, "amt": None, "cur": "KRW", "seg": "도료"}],
             "mentions": {}, "customers": []}
        co, uncl, _ = SUP.build_company(dict(self.REC, reason=""), d, {}, None)
        self.assertEqual([(c["cat"], c["prod"], c["est"], c["basis"]) for c in co["cats"]], [("COAT.PAINT", "도료 › EH2350PTA-2260 외", True, "report")])
        self.assertEqual(uncl, [])

    def test_latest_cache_ignores_notes_json(self):
        with tempfile.TemporaryDirectory() as td:
            for name, body in (("2026Q1.json", {"q": 1}), ("2026Q2.json", {"q": 2}), ("notes.json", {"q": "n"})):
                with open(os.path.join(td, name), "w", encoding="utf-8") as f:
                    json.dump(body, f)
            self.assertEqual(SUP._latest_cache(td), {"q": 2})                  # sorted()[-1] 이면 notes.json 이 잡혔다
            self.assertEqual(SUP._notes_cache(td), {"q": "n"})
        self.assertIsNone(SUP._latest_cache(os.path.join(tempfile.gettempdir(), "kship-no-such-dir")))


class TestNotesCustomers(unittest.TestCase):
    """주석 캐시에서 고객 재탐색 — 이름이 적힌 주요 고객·특수관계자 매출만 연결하고, 담보·관계기업 지분·종속기업 요약표 같은
    문맥의 조선사 이름은 연결하지 않는다(문장·표는 2026-10-05 fin_cache 실측 원문을 줄인 것)."""

    SENT = ("<p>연결회사의 거래처 중 당분기 매출액의 10% 이상을 차지하는 단일고객은 HD현대중공업㈜ 및 HD현대삼호㈜이며, 해당 거래처에 대한 "
            "매출액은 각각 74,429백만원, 100,074백만원입니다(주석 24 참조). 18. 판매비와관리비 — 삼성중공업 관련 비용은 없습니다.</p>")
    SEG = ("<p>주요고객의 내역은 다음과 같습니다.</p><table><tr><th>구 분</th><th>재화(또는 용역)</th><th>주요고객</th></tr>"
           "<tr><td>보냉재사업부문</td><td>보냉재 등</td><td>현대중공업 등</td></tr><tr><td>가스사업부문</td><td>가스 등</td><td>-</td></tr></table>")
    NEG = ("<p>상기 본사건물 및 부동산은 고성 사업장 건설 관련한 삼성중공업의 공사대금에 대하여 담보로 제공되었습니다.</p>"
           "<table><tr><th>회사명</th><th>소재지</th><th>업종</th><th>지분율</th></tr><tr><td>한화오션 주식회사</td><td>대한민국</td><td>강선 건조업</td><td>12.04%</td></tr></table>"
           "<p>(3) 당반기 중 연결회사 매출액의 10% 이상을 차지하는 외부 고객은 없습니다. 주요 고객은 A사 572,853천원입니다.</p>"
           "<p>(*) 내부거래 제거 전 재무제표입니다. (단위:천원)</p><table><tr><th>회사명</th><th>자산</th><th>매출액</th></tr><tr><td>HANSHIN JAPAN</td><td>19,548</td><td>-</td></tr></table>")
    REL = ("<p>(2) 특수관계자와의 거래 — 당분기 (단위:천원)</p><table><tr><th>구 분</th><th>매출 등 매출</th><th>매출 등 기타수익</th><th>매입 등 원재료매입</th></tr>"
           "<tr><td>HD한국조선해양㈜</td><td>-</td><td>-</td><td>384,781</td></tr><tr><td>HD현대중공업㈜</td><td>74,429,447</td><td>-</td><td>76,653</td></tr>"
           "<tr><td>HD현대삼호㈜</td><td>100,074,346</td><td>-</td><td>35,278</td></tr></table>"
           "<p>2) 전분기 (단위:천원)</p><table><tr><th>구 분</th><th>매출 등 매출</th></tr><tr><td>HD현대중공업㈜</td><td>74,150,422</td></tr></table>"
           "<p>채권ㆍ채무 (단위:천원)</p><table><tr><th>구 분</th><th>채권 등 매출채권</th></tr><tr><td>HD현대미포㈜</td><td>15,841</td></tr></table>")

    def test_named_major_customer_sentence(self):
        out = SUP.extract_notes_customers(self.SENT)
        self.assertEqual(sorted(x["yard"] for x in out["ifrs8"]), ["329180", "HSHI"])      # 문장은 '…입니다.' 에서 끝난다 — 뒤의 삼성중공업은 아니다
        self.assertEqual(out["related"], [])
        self.assertIn("HD현대중공업㈜", out["ifrs8"][0]["evidence"])

    def test_segment_table_with_major_customer_column(self):
        out = SUP.extract_notes_customers(self.SEG)
        self.assertEqual([x["yard"] for x in out["ifrs8"]], ["329180"])
        self.assertIn("보냉재사업부문", out["ifrs8"][0]["evidence"])

    def test_non_customer_contexts_are_not_links(self):
        self.assertEqual(SUP.extract_notes_customers(self.NEG), {"ifrs8": [], "related": []})

    def test_related_party_sales_with_units_and_share(self):
        out = SUP.extract_notes_customers(self.REL, rev_m=181262.2)
        rel = {x["yard"]: x for x in out["related"]}
        self.assertEqual(sorted(rel), ["329180", "HSHI"])                      # '-' 매출(지주)·채권 표·전분기 표는 제외
        self.assertEqual(rel["329180"]["sales_m"], 74429.447)                    # 천원 → 백만원
        self.assertEqual((rel["329180"]["share_est"], rel["HSHI"]["share_est"]), (41.06, 55.21))
        self.assertEqual(out["ifrs8"], [])
        # 분모가 없으면 비중 추정도 없다 — 금액만
        self.assertNotIn("share_est", SUP.extract_notes_customers(self.REL)["related"][0])


class TestClassifyAdditions(unittest.TestCase):
    """2026-10-05 사전 보강 — 미분류 110행 실측에서 규칙으로 닫은 것들. 문맥 규칙은 유지된다."""

    def test_new_keywords(self):
        self.assertEqual(classify_product("단조", True), ["HULL.CAST"])
        self.assertEqual(classify_product("단조", False), ["UNCL"])                            # 문맥 없는 단조는 육상일 수 있다
        self.assertEqual(classify_product("A/F7950-REDBROWN,EX4413-L300(II) 외", True), ["COAT.PAINT"])
        self.assertEqual(classify_product("선박선 사업부문", False), ["ELEC.CABLE"])
        self.assertEqual(classify_product("기자재 판매 및 수리", True), ["SVC.INSPECT"])
        self.assertEqual(classify_product("선박 수리조선소(Ship Repair)", False), ["SVC.LABOR"])    # 수리조선은 그대로 SVC.LABOR

    def test_override_file_schema(self):
        # note 열이 있어도 (stock, prod_text) → cat 으로 읽힌다
        ovr = SUP._overrides()
        self.assertEqual(ovr.get(("014940", "기계품")), "DECK.CRANE")
        self.assertEqual(ovr.get(("014940", "구조물")), "ACCOM.DECKHOUSE")


if __name__ == "__main__":
    unittest.main()
