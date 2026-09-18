#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scout_probe 파서 회귀 테스트.

여기 있는 표 모양은 전부 **실제 DART 원문에서 겪은 것**이다(PROGRESS.md §파서 보정).
픽스처는 원문 HTML을 그대로 담지 않는다 — 그 표의 '모양'만 최소로 재현한다
(감독 메모: 대용량 원문 캐시를 저장소에 넣지 않는다).

    python3 tests/test_scout_probe.py
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

import scout_probe as P  # noqa: E402


def tbl(rows, head=None, th=True):
    """[[셀…]] → <table>. head=None 이면 머리행을 <td>로 낸다(두산·HD현대 사고)."""
    out = ["<table>"]
    if head:
        cell = "th" if th else "td"
        out.append("<tr>" + "".join("<%s>%s</%s>" % (cell, c, cell) for c in head) + "</tr>")
    for r in rows:
        out.append("<tr>" + "".join("<td>%s</td>" % c for c in r) + "</tr>")
    out.append("</table>")
    return "".join(out)


STD_HEAD = ["품목", "수주일자", "납기", "수주총액 수량", "수주총액 금액",
            "기납품액 수량", "기납품액 금액", "수주잔고 수량", "수주잔고 금액"]


class TestCurrency(unittest.TestCase):
    """단위 캡션의 통화 — 못 읽으면 잔고가 1000배가 된다."""

    def test_bare_usd(self):
        # 아스트 067390 국외수주현황: `(단위 : USD )`
        self.assertEqual(P._currency_of("(기준일 :2025년 12월 31일) (단위 : USD )"), "USD")

    def test_million_usd(self):
        # 씨에스윈드 112610: `(단위 : 백만USD)`
        self.assertEqual(P._currency_of("6) 수주 상황 (단위 : 백만USD)"), "USD")

    def test_thousand_usd(self):
        # 일진전기 103590: `(단위 : 천USD )` — 백만원으로 읽으면 잔고가 1.6조가 된다
        self.assertEqual(P._currency_of("다. 수주상황 (단위 : 천USD )"), "USD")

    def test_krw_is_none(self):
        self.assertIsNone(P._currency_of("(단위 : 백만원)"))
        self.assertIsNone(P._currency_of("(단위 : 억원)"))
        self.assertIsNone(P._currency_of("(단위 : 원)"))

    def test_krw_with_parenthetical_fx_is_krw(self):
        """원화 단위가 같이 적힌 캡션은 원화 표 — 외화는 괄호 병기일 뿐이다."""
        # 포메탈 119500 / 로체시스템즈 071280 — 여기서 배수를 버리면 멀쩡한 관측을 잃는다
        self.assertIsNone(P._currency_of("가. 매출실적 [단위 : 백만원 (천USD)]"))
        self.assertIsNone(P._currency_of("가. 품목별 매출 유형 (단위 :천원, 천USD )"))
        self.assertIsNone(P._currency_of("(단위 : 수량-EA/금액-백만원)"))

    def test_no_caption(self):
        self.assertIsNone(P._currency_of(""))
        self.assertIsNone(P._currency_of("미국 달러 기준으로 계약하였습니다"))   # '단위' 없음

    def test_last_caption_wins(self):
        """껍데기 표 lead 이어붙임으로 캡션이 둘 붙는다 — 마지막 것이 그 표의 단위다."""
        self.assertIsNone(P._currency_of("1) 국외수주 (단위 : USD) 2) 국내수주 (단위 : 원)"))
        self.assertEqual(P._currency_of("1) 국내수주 (단위 : 원) 2) 국외수주 (단위 : USD)"), "USD")

    def test_norm_tables_carries_cur(self):
        html = ("<p>1) 국외수주현황 (단위 : USD )</p>"
                + tbl([["Boeing 부품", "2024-03", "2027-12", "1", "3,000,000",
                        "1", "1,000,000", "0", "2,000,000"]], STD_HEAD)
                + "<p>2) 국내수주현황 (단위 : 원)</p>"
                + tbl([["국내 부품", "2024-05", "2026-12", "1", "300,000,000",
                        "1", "100,000,000", "0", "200,000,000"]], STD_HEAD))
        ts = P.norm_tables(html)
        self.assertEqual([t["cur"] for t in ts], ["USD", None])
        self.assertEqual([t["unit"] for t in ts], [1.0, 1e-6])

    def test_currency_rows_table_is_mixed(self):
        """행 자체가 통화인 표(KC코트렐 119650 「주요 환종별 수주상황」) — 세로 합계가 허수다."""
        html = "<p>사. 주요 환종별 수주상황 (단위 : 천원, USD 등)</p>" + tbl(
            [["구분(*)", "기초 계약잔액", "당기 신규/변동", "당기 공사수익", "기말 계약잔액"],
             ["KRW", "29,145,799", "49,100,522", "61,642,403", "16,603,919"],
             ["USD", "109,395,933.69", "869,981.75", "54,081,580.39", "56,184,335.05"],
             ["INR", "894,313,112.61", "29,483,795.87", "476,630,727.41", "447,166,181.07"]])
        self.assertEqual(P.norm_tables(html)[0]["cur"], "MIX")

    def test_fx_backlog_is_not_converted(self):
        """외화 표는 금액을 백만원 칸에 싣지 않는다(환율 없이 환산하지 않는다)."""
        html = "<p>수주상황 (단위 : USD )</p>" + tbl(
            [["부품A", "2024-03", "2027-12", "1", "3,000,000", "1", "1,000,000", "0", "2,000,000"]],
            STD_HEAD)
        t = P.norm_tables(html)[0]
        b = P.backlog_of(t, "std")
        self.assertEqual(b["cur"], "USD")
        self.assertEqual(b["raw"], 2000000)


class TestHeaderFallback(unittest.TestCase):
    """머리행이 <th>가 아닌 표 — 그대로 두면 '수주잔고' 열을 영원히 못 찾는다."""

    def test_td_header_promoted(self):
        html = "<p>수주상황 (단위 : 백만원)</p>" + tbl(
            [STD_HEAD,
             ["철도A", "2024-03", "2027-12", "5", "300,000", "2", "120,000", "3", "180,000"]])
        t = P.norm_tables(html)[0]
        self.assertEqual(t["cols"], STD_HEAD)
        self.assertEqual(P.backlog_of(t, "std")["bal"], 180000.0)

    def test_rollforward(self):
        """두산에너빌리티형 롤포워드 — 억원 단위(×100)."""
        html = "<p>(2) 주요사업부문별 수주상황 (단위 : 억원)</p>" + tbl(
            [["구분", "주요 계약명", "기초", "증감", "매출계상액", "기말"],
             ["원자력", "-", "50,000", "10,000", "5,000", "55,000"],
             ["합계", "-", "240,000", "60,000", "45,025", "255,025"]])
        t = P.norm_tables(html)[0]
        b = P.backlog_of(t, "roll")
        self.assertEqual(b["raw"], 255025)
        self.assertEqual(b["unit_mul"], 100.0)
        self.assertEqual(b["bal"], 25502500.0)       # 25.5조원


class TestUnitShellTable(unittest.TestCase):
    """단위 캡션만 든 1×n 껍데기 표(SFA 056190) — 버리면 뒤 표가 단위를 잃는다."""

    def test_shell_unit_passed_on(self):
        html = ("<p>(1) 매출실적</p>" + tbl([["(단위 : 백만원)"]])
                + tbl([["매출유형", "품 목", "제30기"], ["제품", "장비", "1,630,950"]]))
        ts = P.norm_tables(html)
        self.assertEqual(len(ts), 1)                  # 껍데기는 표로 나오지 않는다
        self.assertTrue(ts[0]["unit_seen"])
        self.assertIn("매출실적", ts[0]["lead"])
        self.assertEqual(ts[0]["unit"], 1.0)

    def test_header_row_is_all_caption(self):
        """머리행 자리 전체가 캡션인 표(금호건설 002990) — 캡션을 lead로 옮기고 첫 행을 머리행으로."""
        html = "<p>가. 매출실적</p>" + tbl(
            [["매출유형", "품 목", "제30기"], ["제품", "장비", "1,000"]], ["(단위 : 천원)"])
        t = P.norm_tables(html)[0]
        self.assertEqual(t["cols"], ["매출유형", "품 목", "제30기"])
        self.assertEqual(t["unit"], 0.001)


class TestSalesDialect(unittest.TestCase):
    """'매출액'이라는 낱말이 없는 매출실적 표(세명전기 017510)."""

    def test_no_amount_word(self):
        html = "<p>가. 매출에 관한 사항 (단위 : 백만원)</p>" + tbl(
            [["사업부문", "품 목", "제42기", "제41기"],
             ["전기", "애자", "30,000", "28,000"],
             ["합계", "-", "32,333", "30,000"]])
        t = P.norm_tables(html)[0]
        self.assertEqual(P.classify(t), "sales")
        self.assertEqual(P.sales_of(t)["rev"], 32333.0)


class TestGrain(unittest.TestCase):
    """행 입도 — 1~2행짜리 부문 합계를 계약 단위로 읽으면 D축이 부푼다."""

    def test_single_segment_row_is_not_project(self):
        html = "<p>수주상황 (단위 : 백만원)</p>" + tbl(
            [["전기전자부문", "-", "-", "-", "13,502,898", "-", "4,079,498", "-", "9,423,400"]],
            STD_HEAD)
        t = P.norm_tables(html)[0]
        self.assertEqual(P.grain_of(t)[0], "segment")

    def test_many_dated_rows_is_project(self):
        rows = [["철도%s" % chr(65 + i), "2024-0%d" % (i % 9 + 1), "2027-12",
                 "5", "300,000", "2", "120,000", "3", "180,000"] for i in range(8)]
        t = P.norm_tables("<p>수주상황 (단위 : 백만원)</p>" + tbl(rows, STD_HEAD))[0]
        self.assertEqual(P.grain_of(t)[0], "project")


if __name__ == "__main__":
    unittest.main(verbosity=2)
