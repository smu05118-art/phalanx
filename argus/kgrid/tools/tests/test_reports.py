#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정기보고서 파서 계약 테스트 — 형식이 아니라 **계약**을 지킨다(COMMON §4).

fixture 는 DART 원문 표를 `cols`·`rows`·`lead` 그대로 담은 것이다(`tests/fixtures/orders_*.json`,
`kgrid_reports` 캐시에서 뽑았다). 여기서 검증하는 것은 "파서가 뽑은 값이 **원문에 적힌 값과
같은가**"이며, 값은 내가 눈으로 확인해 주석에 원문 그대로 적어 두었다(FINDINGS §2).

각 테스트가 막는 실제 사고:
  · 통화     일진전기 `(단위 : 천USD )` 를 1e-6 로 읽어 잔고가 1000배 작아지던 것
  · 총계     일진전기 `합 계|국내` 를 총계로 집어 잔고가 절반이 되던 것
  · 소계     `전력선 등|계` 를 낱 행으로 세어 잔고가 두 배가 되던 것
  · 수량 열  제룡전기 `제40기 수량` 을 매출로 읽어 배수가 5,585년이 되던 것
  · 금액 열  엘에스일렉트릭 수주표에서 수량 열이 금액 열보다 앞에 와 잔고가 `-` 가 되던 것
  · 종속회사 `[LS메탈]` 표를 본체로 골라 전력기기 잔고가 666억이 되던 것
  · 머리행   HD현대일렉트릭 `품 목|품 목` 중복 머리행 표를 버려 내수/수출이 사라지던 것
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import kgrid_dicts                                                  # noqa: E402
import kgrid_reports as R                                           # noqa: E402
from kgrid_lib import backlog_kind, coverage, fmt_money, unit_of     # noqa: E402


def fx(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return json.load(f)


def orders(name):
    """fixture 의 표들을 수주표로 읽어 (표, 결과) 목록을 돌려준다."""
    d = fx(name)
    tables = R._headered(R._carry_units(d["tables"]))
    return [(t, R.parse_orders_table(t)) for t in tables]


def only_orders(name):
    return [o for _t, o in orders(name) if o]


class TestUnit(unittest.TestCase):
    """단위 캡션 → 통화·배수. 공용 층(kship_parse)을 kgrid 가 고쳐 둔 계약이다."""

    def test_thousand_usd(self):
        # 일진전기 103590 수주표: `(단위 : 천USD )`
        self.assertEqual(unit_of("다. 수주상황 (단위 : 천USD )")[:2], ("USD", 0.001))

    def test_million_usd(self):
        self.assertEqual(unit_of("(단위 : 백만USD)")[:2], ("USD", 1.0))

    def test_krw_wins_when_both(self):
        # 외화가 괄호 병기일 뿐이고 표의 숫자는 원화인 캡션
        self.assertEqual(unit_of("[단위 : 백만원 (천USD)]")[:2], ("KRW", 1.0))
        self.assertEqual(unit_of("(단위 :천원, 천USD )")[:2], ("KRW", 0.001))

    def test_eok(self):
        # 엘에스일렉트릭 010120 수주표: `(기준일 : 2026.06.30) (단위 : 억원 )`
        self.assertEqual(unit_of("(기준일 : 2026.06.30) (단위 : 억원 )")[:2], ("KRW", 100.0))

    def test_quantity_caption_keeps_money(self):
        # LS메탈 `(단위 : 톤, 억원 )` — 금액 단위가 같이 있으므로 금액 열은 살아 있다
        self.assertEqual(unit_of("(단위 : 톤, 억원 )")[:2], ("KRW", 100.0))

    def test_percent_is_not_a_unit(self):
        self.assertFalse(unit_of("(단위 : % )")[2])


class TestLSElectric(unittest.TestCase):
    """엘에스일렉트릭 010120 2026Q2 — 롤포워드 12열 · 단위 억원 · 종속회사별 표."""

    def setUp(self):
        self.parsed = orders("orders_010120_2026Q2.json")
        self.os = [o for _t, o in self.parsed if o]

    def test_shape_and_unit(self):
        best = R._pick_orders(self.os, "엘에스일렉트릭")
        self.assertEqual(best["shape"], "roll")
        self.assertEqual(best["cur"], "KRW")
        self.assertTrue(best["unit_seen"])

    def test_picks_body_entity_not_subsidiary(self):
        """`[LS ELECTRIC]` 을 골라야 한다. `[LS메탈]`(666억)을 고르면 7조가 사라진다."""
        best = R._pick_orders(self.os, "엘에스일렉트릭")
        self.assertEqual(best["entity"], "LS ELECTRIC")
        self.assertIn("LS메탈", [o["entity"] for o in self.os])

    def test_backlog_matches_original_total(self):
        """원문 합계 행: 수주잔고 금액 69,998(억원) → 6,999,800 백만원."""
        best = R._pick_orders(self.os, "엘에스일렉트릭")
        self.assertEqual(R._orders_total(best), 6999800)

    def test_amount_column_wins_over_quantity(self):
        """`수주잔고 수량`(`-`)이 `수주잔고 금액` 보다 앞에 온다 — 금액을 집어야 한다."""
        best = R._pick_orders(self.os, "엘에스일렉트릭")
        rows = {r["item"] or r["seg"]: r for r in best["rows"]}
        self.assertEqual(rows["T&D"]["closing"], 6889600)     # 원문 68,896 억원
        self.assertEqual(rows["T&D"]["new"], 3429300)         # 원문 34,293 억원
        self.assertEqual(rows["T&D"]["delivered"], 1429900)   # 원문 14,299 억원
        self.assertEqual(rows["T&D"]["opening"], 4890200)     # 원문 48,902 억원

    def test_rollforward_identity(self):
        """기초 + 신규 − 기납품 = 기말. 원문이 스스로 맞아야 한다."""
        best = R._pick_orders(self.os, "엘에스일렉트릭")
        for r in best["rows"]:
            if None in (r["opening"], r["new"], r["delivered"], r["closing"]):
                continue
            self.assertAlmostEqual(r["opening"] + r["new"] - r["delivered"], r["closing"],
                                   delta=max(1.0, abs(r["closing"]) * 0.001),
                                   msg="롤포워드가 안 맞는다: %s" % r["label"])

    def test_segment_kind(self):
        best = R._pick_orders(self.os, "엘에스일렉트릭")
        kinds = {(r["item"] or r["seg"]): r["kind"] for r in best["rows"]}
        self.assertEqual(kinds["T&D"], "grid")
        self.assertEqual(kinds["자동화"], "other")

    def test_entity_revenue_is_used_for_coverage(self):
        """분모는 **같은 주체**의 연매출이어야 한다 — 원문 제52기 LSELECTRIC 3,462,741."""
        tables = R._headered(R._carry_units(fx("orders_010120_2026Q2.json")["tables"]))
        rv = [x for x in (R.parse_revenue_table(t) for t in tables) if x]
        self.assertTrue(rv)
        best_rv = max(rv, key=lambda r: len(r["rows"]))
        sub = R._entity_subset(best_rv, "LS ELECTRIC")
        self.assertIsNotNone(sub, "종속회사 행을 못 맞췄다")
        fy, col, _cur = R._fy_from(sub, kind_field=True)
        self.assertEqual(fy, 3462741)
        self.assertIn("52", col)
        self.assertAlmostEqual(coverage(6999800, fy), 2.02, places=2)


class TestHDElectric(unittest.TestCase):
    """HD현대일렉트릭 267260 2026Q2 — 부문 합계 1행 · 머리행이 없는 표 · 매출처 실명."""

    def setUp(self):
        self.tables = R._headered(R._carry_units(fx("orders_267260_2026Q2.json")["tables"]))

    def test_orders_one_segment_row(self):
        os_ = [o for o in (R.parse_orders_table(t) for t in self.tables) if o]
        self.assertEqual(len(os_), 1)
        o = os_[0]
        self.assertEqual(o["cur"], "KRW")
        base = [r for r in o["rows"] if not r["total"]]
        self.assertEqual(len(base), 1)                   # 입도가 부문이다
        self.assertEqual(base[0]["closing"], 12310500)   # 원문 12,310,500 백만원
        self.assertEqual(base[0]["gross"], 14488813)     # 원문 14,488,813
        self.assertEqual(base[0]["delivered"], 2178313)  # 원문 2,178,313

    def test_duplicate_header_table_survives(self):
        """`사업부문|매출유형|품 목|품 목|제10기…` 중복 머리행을 갈라 살려야 한다.

        fixture 는 `_headered` 를 이미 지난 캐시라 머리행에 `품 목#2` 표시가 남아 있다 —
        그 표시가 있다는 것이 중복 머리행 표가 버려지지 않았다는 증거다."""
        dedup = [t for t in self.tables if any("#2" in c for c in t["cols"])]
        self.assertTrue(dedup, "중복 머리행 표가 버려졌다 — 내수/수출이 사라진다")
        rv = [x for x in (R.parse_revenue_table(t) for t in self.tables) if x]
        self.assertTrue(rv)
        rows = {r["kind"]: r["val"] for r in rv[0]["rows"]}
        self.assertEqual(rows["수출"], 1706656)   # 원문 1,706,656
        self.assertEqual(rows["내수"], 471657)    # 원문 471,657

    def test_customers_named_with_amount(self):
        cs = [x for x in (R.parse_customers(t, "HD현") for t in self.tables) if x]
        self.assertTrue(cs)
        rows = {r["name"]: r for r in cs[0]["rows"]}
        self.assertIn("NextEra Energy", rows)
        self.assertEqual(rows["NextEra Energy"]["share_pct"], 15.9)
        self.assertEqual(rows["NextEra Energy"]["amount"], 347203)
        self.assertEqual(rows["NextEra Energy"]["evidence"], "named")
        self.assertEqual(rows["사우디 전력청"]["share_pct"], 5.0)

    def test_product_group_by_segment_sales(self):
        """제품군별 매출실적(전력기기·회전기기·배전기기 外)이 제품군 구성의 근거다."""
        ss = [x for x in (R.parse_segment_sales(t) for t in self.tables) if x]
        self.assertTrue(ss)
        names = {r["seg"] for x in ss for r in x["rows"]}
        self.assertTrue({"전력기기", "회전기기"} <= names, names)

    def test_coverage_is_long_backlog(self):
        self.assertEqual(backlog_kind(coverage(12310500, 4079498)), "long")


class TestIljin(unittest.TestCase):
    """일진전기 103590 2026Q2 — 통화가 USD · 행이 국내/해외 · 소계와 총계가 섞인다."""

    def setUp(self):
        self.tables = R._headered(R._carry_units(fx("orders_103590_2026Q2.json")["tables"]))
        self.o = [o for o in (R.parse_orders_table(t) for t in self.tables) if o][0]

    def test_currency_is_usd(self):
        self.assertEqual(self.o["cur"], "USD")
        self.assertTrue(self.o["unit_seen"])

    def test_grand_total_row(self):
        """총계는 `합 계|계` 행이다 — `합 계|국내`(468,895)를 집으면 잔고가 절반이 된다."""
        g = R._grand_row(self.o["rows"])
        self.assertIsNotNone(g)
        self.assertAlmostEqual(g["closing"], 1939.091, places=3)   # 원문 1,939,091 천USD

    def test_subtotal_rows_excluded(self):
        """`전력선 등|계`(648,960)를 낱 행으로 세면 잔고가 두 배가 된다."""
        base = [r for r in self.o["rows"] if not r["total"]]
        self.assertEqual(len(base), 4)
        self.assertAlmostEqual(sum(r["closing"] for r in base), 1939.091, places=3)

    def test_domestic_overseas_split(self):
        base = [r for r in self.o["rows"] if not r["total"]]
        dom = sum(r["closing"] for r in base if r["area"] == "dom")
        ovs = sum(r["closing"] for r in base if r["area"] == "ovs")
        self.assertAlmostEqual(dom, 468.895, places=3)    # 원문 468,895 천USD
        self.assertAlmostEqual(ovs, 1470.196, places=3)   # 원문 1,470,196 천USD

    def test_coverage_not_made_across_currencies(self):
        """잔고 USD · 매출 KRW → 배수를 만들지 않는다(환율을 원문에서 못 얻는다)."""
        self.assertIsNone(coverage(1939.091, 2044552, "USD", "KRW"))
        self.assertEqual(backlog_kind(None), "unknown")

    def test_money_format_keeps_currency(self):
        self.assertEqual(fmt_money(1939.091, "USD"), "$1.94bn")
        self.assertEqual(fmt_money(12310500), "123,105억")

    def test_region_table(self):
        rg = [x for x in (R.parse_region_table(t) for t in self.tables) if x]
        self.assertTrue(rg, "「지역별 매출 현황」 표를 못 읽었다")
        rows = {r["name"]: r for r in rg[0]["rows"]}
        self.assertEqual(rows["미주"]["region"], "na")     # 원문 174,141 백만원
        self.assertEqual(rows["미주"]["val"], 174141)
        self.assertEqual(rows["유럽"]["region"], "eu")
        self.assertEqual(rows["아시아, 호주"]["region"], "asia")


class TestJeryong(unittest.TestCase):
    """제룡전기 033100 2026Q2 — 매출실적 기간 열에 **수량 열이 끼어 있다**."""

    def setUp(self):
        self.tables = R._headered(R._carry_units(fx("orders_033100_2026Q2.json")["tables"]))

    def test_quantity_columns_are_dropped(self):
        rv = [x for x in (R.parse_revenue_table(t) for t in self.tables) if x]
        self.assertTrue(rv)
        cols = rv[0]["period_cols"]
        self.assertTrue(cols, "기간 열이 통째로 사라졌다")
        self.assertFalse([c for c in cols if "수량" in c], cols)

    def test_annual_revenue_is_money_not_units(self):
        """제40기 금액으로 연매출을 만들어야 한다 — 수량을 쓰면 배수가 5,585년이 된다."""
        rv = [x for x in (R.parse_revenue_table(t) for t in self.tables) if x]
        fy, col, _cur = R._fy_from(max(rv, key=lambda r: len(r["rows"])), kind_field=True)
        self.assertIsNotNone(fy)
        self.assertNotIn("수량", col)
        self.assertGreater(fy, 100000)       # 2,240억 규모 — 대수(수만)와 자릿수가 다르다
        cov = coverage(141580, fy)
        self.assertLess(cov, 2.0)
        self.assertEqual(backlog_kind(cov), "rotating")


class TestHyosung(unittest.TestCase):
    """효성중공업 298040 2026Q2 — 전기말/당기말 열 · rowspan 중복 행 · 달 범위 기간 열."""

    def setUp(self):
        self.tables = R._headered(R._carry_units(fx("orders_298040_2026Q2.json")["tables"]))
        self.o = [o for o in (R.parse_orders_table(t) for t in self.tables) if o][0]

    def test_current_not_prior_period_balance(self):
        """`전기말 수주잔`(15,936,349)을 잔고로 집으면 안 된다 — `당기말 수주잔`이 잔고다."""
        self.assertEqual(self.o["shape"], "roll")
        rows = {(r["seg"], r["item"][:8]): r for r in self.o["rows"]}
        heavy = max(self.o["rows"], key=lambda r: r["closing"] or 0)
        self.assertEqual(heavy["seg"], "중공업")
        self.assertEqual(heavy["closing"], 23834404)   # 원문 23,834,404 백만원
        self.assertEqual(heavy["opening"], 15936349)   # 원문 전기말 15,936,349
        self.assertEqual(heavy["new"], 11010478)       # 원문 당기 수주액 11,010,478
        self.assertEqual(heavy["delivered"], 2924567)  # 원문 당기 매출액 2,924,567
        self.assertTrue(rows)

    def test_rowspan_duplicate_rows_collapsed(self):
        """`중공업` 부문 값이 종속회사 5행에 rowspan 으로 복제된다 — 접지 않으면 119조가 된다."""
        heavy = [r for r in self.o["rows"] if r["seg"] == "중공업"]
        self.assertEqual(len(heavy), 1, [r["item"] for r in heavy])
        total = sum(r["closing"] for r in self.o["rows"] if r["closing"] is not None)
        self.assertEqual(total, 32958249)     # 중공업 23.8조 + 건설 5.3조 + 진흥기업 3.8조

    def test_numeric_cell_is_not_a_label(self):
        for r in self.o["rows"]:
            self.assertIsNone(R.num_of(r["seg"]), r["seg"])
            self.assertIsNone(R.num_of(r["item"]), r["item"])

    def test_month_range_half_year_is_not_a_full_year(self):
        """`제9기(2026년 1~6월)` 은 반기다 — 1년으로 읽으면 배수가 15.4년이 된다."""
        self.assertFalse(R._is_fy("제9기(2026년 1~6월)"))
        self.assertTrue(R._is_fy("제8기(2025년 1~12월)"))
        rv = [x for x in (R.parse_revenue_table(t) for t in self.tables) if x]
        fy, col, _cur = R._fy_from(max(rv, key=lambda r: len(r["rows"])), kind_field=True)
        self.assertEqual(fy, 4097814)          # 원문 합 계 제8기 4,097,814
        self.assertIn("1~12월", col)
        self.assertAlmostEqual(coverage(32958249, fy), 8.04, places=2)


class TestGaon(unittest.TestCase):
    """가온전선 000500 — 총계 행이 **여럿**이다(`단순합계`·`내부 거래 제거`·`합 계`)."""

    def setUp(self):
        self.tables = R._headered(R._carry_units(fx("orders_000500_2026Q2.json")["tables"]))

    def test_last_grand_total_wins(self):
        """총계를 다 더하면 매출이 5.3조가 된다 — 내부거래를 지운 최종 합계만 쓴다."""
        rv = [x for x in (R.parse_revenue_table(t) for t in self.tables) if x]
        best = max(rv, key=lambda r: len(r["rows"]))
        grand = [r for r in best["rows"] if r["kind"] == "합계" and R.is_total(r["seg"])]
        self.assertGreater(len(grand), 1, "총계 후보가 하나면 이 테스트가 의미 없다")
        fy, _col, _cur = R._fy_from(best, kind_field=True)
        self.assertEqual(fy, 2545698)          # 원문 합 계 제78기 2,545,698
        self.assertNotEqual(fy, 5336705)       # 단순합계 + 합계 = 5,336,705(이중계산)


class TestDaeyang(unittest.TestCase):
    """대양전기공업 108380 — 기간마다 `수량|판매액|외화` 3열. 두 줄 머리행을 살려야 한다."""

    def setUp(self):
        self.tables = R._headered(R._carry_units(fx("orders_108380_2026Q2.json")["tables"]))

    def test_two_row_header_with_repeated_prefix(self):
        """앞쪽 이름 열(`품목|품목`)이 겹쳐도 표를 버리지 않는다 — 번호를 붙여 가른다."""
        t = {"cols": [], "lead": "가. 매출실적 (단위 : 백만원)",
             "rows": [["매출유형", "품목", "품목", "2025년", "2025년", "2025년"],
                      ["매출유형", "품목", "품목", "수량", "판매액", "외화"],
                      ["제품", "조 명", "내수", "705", "27,980", "-"]]}
        d = R._two_row_header(t)
        self.assertIsNotNone(d, "겹친 이름 때문에 두 줄 머리행 표가 버려졌다")
        self.assertEqual(d["cols"][2], "품목#2")
        self.assertEqual(d["cols"][4], "2025년 판매액")

    def test_quantity_and_fx_columns_dropped(self):
        rv = [x for x in (R.parse_revenue_table(t) for t in self.tables) if x]
        self.assertTrue(rv)
        best = max(rv, key=lambda r: len(r["rows"]))
        self.assertFalse([c for c in best["period_cols"] if "수량" in c or "외화" in c],
                         best["period_cols"])
        fy, col, _cur = R._fy_from(best, kind_field=True)
        self.assertEqual(fy, 417146)          # 원문 2025년 판매액 합계
        self.assertIn("판매액", col)
        self.assertEqual(backlog_kind(coverage(327611, fy)), "rotating")

    def test_balance_only_shape(self):
        o = [x for x in (R.parse_orders_table(t) for t in self.tables) if x]
        self.assertTrue(o)
        self.assertEqual(o[0]["shape"], "balance")
        g = R._grand_row(o[0]["rows"])
        self.assertEqual(g["closing"], 327611)   # 원문 합 계 327,611 백만원


class TestDicts(unittest.TestCase):
    """분류 사전 — 교차 참조와 어휘 함정(FINDINGS §1)."""

    def test_cross_reference_holds(self):
        self.assertTrue(kgrid_dicts._check())

    def test_generic_transformer_is_not_distribution(self):
        """맨 `변압기` 를 배전용으로 넣으면 초고압 대표 회사가 배전용이 된다."""
        prods, _dem = kgrid_dicts.build()
        self.assertEqual(kgrid_dicts.classify("변압기, 고압차단기", prods), "breaker")
        self.assertIn("tr_unknown",
                      kgrid_dicts.classify_all("변압기, 고압차단기", prods, limit=4))
        self.assertNotIn("dist_tr",
                         kgrid_dicts.classify_all("변압기, 고압차단기", prods, limit=4))

    def test_specific_transformer_classes(self):
        prods, _dem = kgrid_dicts.build()
        self.assertIn("dist_tr", kgrid_dicts.classify_all("유입, 몰드, 주상, 건식 변압기 등", prods))
        self.assertIn("ehv", kgrid_dicts.classify_all("초고압 변압기 및 HVDC 변환용 변압기", prods))

    def test_no_single_char_words(self):
        prods, dem = kgrid_dicts.build()
        for d in prods + dem:
            for w in d["words"]:
                self.assertGreaterEqual(len(w["w"]), 2, w)


class TestDemandQuotes(unittest.TestCase):
    """수요 낱말 — 표 덤프를 문장으로 인용하지 않는다."""

    def test_table_dump_rejected(self):
        bad = ("4) 주요매출처 (단위 : 백만원) 매출처명 금액 비율 "
               "NextEra Energy 347,203 15.9% 사우디 전력청 109,097 5.0%")
        self.assertFalse(R._readable(bad))

    def test_sentence_kept_and_entities_unescaped(self):
        txt = ("<p>&nbsp;AI 발전에 따른 데이터센터 건설 증가와 미국·유럽 중심의 노후 전력망 "
               "업그레이드로 전력 인프라 투자가 지속됩니다.</p>")
        out = R.demand_quotes(txt)
        self.assertIn("datacenter", out)
        self.assertIn("aging_grid", out)
        q = out["datacenter"]["quotes"][0]
        self.assertNotIn("&nbsp;", q)
        self.assertNotIn(" ", q)

    def test_hvdc_is_found_when_present(self):
        """스펙은 '원문에서 확인 못 함'이라 했지만 2026Q2 본문에는 나온다 — 찾되 없으면 없다."""
        out = R.demand_quotes("서해안 HVDC 등 초고압직류송전 사업이 순차적으로 추진됩니다. "
                              "이에 따라 초고압 변압기 수요가 확대되고 있습니다.")
        self.assertIn("hvdc", out)
        self.assertNotIn("hvdc", R.demand_quotes("수배전반을 국내 고객에게 공급합니다."))


class TestSegKind(unittest.TestCase):
    def test_grid_vs_other(self):
        self.assertEqual(R.seg_kind("전력"), "grid")
        self.assertEqual(R.seg_kind("전기전자부문"), "grid")
        self.assertEqual(R.seg_kind("중전기"), "grid")
        self.assertEqual(R.seg_kind("자동화"), "other")
        self.assertEqual(R.seg_kind("금속"), "other")
        self.assertIsNone(R.seg_kind(""))

    def test_entity_label(self):
        self.assertEqual(R.entity_of("다. 수주 상황 [LS ELECTRIC]"), "LS ELECTRIC")
        self.assertEqual(R.entity_of("[LS메탈]\r\n (기준일 : 2026.06.30) (단위 : 톤, 억원 )"),
                         "LS메탈")
        self.assertEqual(R.entity_of("다. 수주상황1) HD현대일렉트릭(주) 및 그 종속회사"), "")


class TestRelatedParty(unittest.TestCase):
    """최대 매출처가 자기 자회사인 회사 — 같은 보고서의 종속회사 목록을 근거로 가른다."""

    def test_related_detected_from_report(self):
        d = {"orders_all": [{"entity": "LS ELECTRIC"}, {"entity": "LS메탈"}],
             "revenue_all": [{"rows": [{"seg": "LS ELECTRICAmerica"}, {"seg": "LSELECTRIC"}]}],
             "segment_sales_all": []}
        rels = R._related_names(d, "엘에스일렉트릭")
        self.assertTrue(R._is_related("LS ELECTRIC AMERICA INC.", rels))
        self.assertFalse(R._is_related("(주)엘지에너지솔루션", rels))
        self.assertFalse(R._is_related("한국전력공사", rels))


if __name__ == "__main__":
    unittest.main()
