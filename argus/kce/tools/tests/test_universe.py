#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""커버리지 확장(모집단·프로브·새 방언) 회귀 테스트.

실행: cd argus/kce/tools && python3 -m unittest discover -s tests
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

from kce_lib import COL_ALIAS, norm_col              # noqa: E402
from kce_parse import parse_ii4, unit_scale          # noqa: E402
import kce_probe                                     # noqa: E402
import kce_universe as U                             # noqa: E402


def _kind_html(rows):
    """KIND 상장법인목록과 같은 모양의 최소 HTML(EUC-KR 바이트)."""
    head = ("회사명", "시장구분", "종목코드", "업종", "주요제품",
            "상장일", "결산월", "대표자명", "홈페이지", "지역")
    out = ["<table>", "<tr>" + "".join("<td>%s</td>" % h for h in head) + "</tr>"]
    for r in rows:
        out.append("<tr>" + "".join("<td>%s</td>" % c for c in r) + "</tr>")
    out.append("</table>")
    return "\n".join(out).encode("euc-kr")


def _row(name, stock, industry, market="유가"):
    return (name, market, stock, industry, "주요제품", "1990-01-01",
            "12월", "대표", "", "서울특별시")


class TestUniverseParse(unittest.TestCase):

    def _parse(self, rows, min_rows=0):
        old = U.MIN_ROWS
        U.MIN_ROWS = min_rows
        try:
            return U.parse_kind(_kind_html(rows))
        finally:
            U.MIN_ROWS = old

    def test_alnum_stock_code_does_not_shadow_real_one(self):
        """스팩 종목코드 `0072Z0`에서 영문을 지우면 `000720`(현대건설)과 충돌한다.

        중복 제거가 먼저 온 스팩을 남기고 현대건설을 통째로 버렸던 실제 버그.
        """
        recs = self._parse([_row("KB제33호스팩", "0072Z0", "금융 지원 서비스업"),
                            _row("현대건설", "000720", "토목 건설업")])
        by = {r["stock"]: r["name"] for r in recs}
        self.assertEqual(by.get("000720"), "현대건설")
        self.assertEqual(by.get("0072Z0"), "KB제33호스팩")

    def test_duplicate_rows_collapse(self):
        recs = self._parse([_row("금호건설", "002990", "건물 건설업"),
                            _row("금호건설", "002990", "건물 건설업")])
        self.assertEqual(len(recs), 1)

    def test_header_change_is_fail_closed(self):
        """열 이름이 바뀌면 조용히 어긋난 열을 읽지 말고 멈춰야 한다."""
        bad = _kind_html([_row("현대건설", "000720", "토목 건설업")]).replace(
            "종목코드".encode("euc-kr"), "코드".encode("euc-kr"))
        old, U.MIN_ROWS = U.MIN_ROWS, 0
        try:
            with self.assertRaises(RuntimeError):
                U.parse_kind(bad)
        finally:
            U.MIN_ROWS = old

    def test_truncated_response_is_fail_closed(self):
        with self.assertRaises(RuntimeError):     # MIN_ROWS 기본값 사용
            U.parse_kind(_kind_html([_row("현대건설", "000720", "토목 건설업")]))


class TestUniverseSelect(unittest.TestCase):

    def _full(self, extra=()):
        """SEED·LEGACY 필수 종목을 모두 포함한 최소 모집단.

        필수 집합을 **코드에서 파생**시킨다. 7사 시절의 종목코드를 문자열로 박아 두면
        정밀 경로(CORP)가 늘 때마다 이 픽스처가 낡아 실패한다 — 실제로 CORP가 7→17로
        늘면서 깨졌다. 검증하려는 계약은 "필수 종목이 빠지면 막는다"이지
        "그 필수 종목이 정확히 이 일곱이다"가 아니다.
        """
        rows = []
        for stock in sorted(set(U.SEED_EXTRA) | set(U.LEGACY_SLUG)):
            # 지정(SEED) 종목은 업종 필터에 걸리지 않는 쪽으로 둬야 '지정' 경로가
            # 실제로 시험된다. 나머지는 업종으로 들어오게 한다.
            ind = ("기타 전문 도매업" if stock in U.SEED_EXTRA
                   else "건물 건설업")
            rows.append({"name": "회사%s" % stock, "market": "유가",
                         "stock": stock, "industry": ind})
        rows += [dict(r) for r in extra]
        for r in rows:
            r.setdefault("product", "")
            r.setdefault("listed", "")
        return rows

    def _select(self, rows):
        old, U.MIN_CONSTRUCTION = U.MIN_CONSTRUCTION, 0
        try:
            return U.select(rows)
        finally:
            U.MIN_CONSTRUCTION = old

    def test_industry_and_seed_both_selected(self):
        recs = self._select(self._full([{"name": "태영건설", "market": "유가",
                                         "stock": "009410", "industry": "토목 건설업",
                                         "product": "", "listed": ""}]))
        by = {r["stock"]: r for r in recs}
        self.assertEqual(by["009410"]["source"], "업종")
        self.assertEqual(by["028260"]["source"], "지정")   # 업종 밖이지만 지정 포함
        # 정밀 경로(CORP) 종목은 그 슬러그를 유지하고, 신규는 종목코드를 슬러그로 쓴다
        self.assertEqual(by["000720"]["slug"], "hec")
        self.assertEqual(by["009410"]["slug"], "009410")
        # 비상장 자회사(stock=None)는 상장법인 모집단의 원소가 아니다
        self.assertNotIn(None, {r["stock"] for r in recs})

    def test_missing_seed_is_fail_closed(self):
        rows = [r for r in self._full() if r["stock"] != "028260"]
        with self.assertRaises(RuntimeError):
            self._select(rows)


class TestNewDialects(unittest.TestCase):
    """확장으로 새로 흡수한 머리행 방언 — 회귀하면 그 회사가 통째로 빠진다."""

    def test_standard_manufacturing_form(self):
        # 코오롱글로벌·서희건설 등 9사가 쓰는 기업공시서식 표준 수주상황표
        for raw, want in [("수주총액 금액", "amt"), ("기납품액 금액", "cmp"),
                          ("수주잔고 금액", "bal"), ("납기", "ed")]:
            self.assertEqual(COL_ALIAS.get(norm_col(raw)), want, raw)
        # 수량 열은 금액이 아니므로 **매핑되지 않아야** 한다
        for raw in ("수주총액 수량", "기납품액 수량", "수주잔고 수량"):
            self.assertIsNone(COL_ALIAS.get(norm_col(raw)), raw)

    def test_construction_site_dialects(self):
        for raw, want in [("수주내용", "nm"), ("계약명", "nm"),
                          ("도급금액", "amt"), ("총 도급금액", "amt"),
                          ("도급액(당분기)", "amt"), ("착공일", "sd"),
                          ("준공일", "ed"), ("누적기성고", "cmp"),
                          ("차기이월", "bal")]:
            self.assertEqual(COL_ALIAS.get(norm_col(raw)), want, raw)

    def test_footnote_star_stripped(self):
        # 한신공영 `계약잔액(*)` — (*)를 남기면 bal이 통째로 빠진다
        self.assertEqual(norm_col("계약잔액(*)"), "계약잔액")
        self.assertEqual(COL_ALIAS[norm_col("계약잔액(*)")], "bal")


class TestUnitInHeader(unittest.TestCase):
    """단위 캡션이 머리행 셀에 들어간 표(동신건설) — 놓치면 값이 1000배가 된다."""

    HTML = ("<table><tr>"
            "<td>(단위 : 천원) 품목</td><td>(단위 : 천원) 발주처</td>"
            "<td>(단위 : 천원) 계약일</td><td>(단위 : 천원) 준공예정일</td>"
            "<td>(단위 : 천원) 계약금액 금액</td><td>(단위 : 천원) 매출액 금액</td>"
            "<td>(단위 : 천원) 수주잔고 금액</td></tr>"
            "<tr><td>순창인계-쌍치 도로시설개량공사</td><td>익산지방국토관리청</td>"
            "<td>2022.12</td><td>2028.11</td>"
            "<td>20,558,624</td><td>7,380,536</td><td>13,178,088</td></tr></table>")

    def test_unit_read_from_columns(self):
        self.assertEqual(unit_scale("", ["(단위 : 천원) 품목"]), 0.001)
        # lead에 단위가 있으면 그쪽이 우선(기존 동작 불변)
        self.assertEqual(unit_scale("(단위 : 억원)", ["(단위 : 천원) 품목"]), 100.0)

    def test_thousand_won_scaled_to_million(self):
        rows = [x for t in parse_ii4(self.HTML)["tables"] for x in t["rows"]]
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["amt"], 20558.624, places=3)
        self.assertAlmostEqual(rows[0]["bal"], 13178.088, places=3)


class TestGrain(unittest.TestCase):
    """현장 단위 / 사업부문 단위 판별."""

    def _t(self, rows):
        return [{"rows": rows}]

    def test_segment_rows_have_no_dates(self):
        seg = [{"nm": n, "sd": "-", "ed": "-"} for n in
               ("건축부문", "토목부문", "플랜트", "기타", "해외", "환경")]
        self.assertEqual(kce_probe.grain_of(self._t(seg)), "segment")

    def test_date_dialects_count_as_project(self):
        # 삼성E&A `201506` · 진흥기업 `24년12월` · HL D&I `25.12` · 계룡 `2022.12`
        for sd, ed in (("201506", "203009"), ("24년12월", "28년02월"),
                       ("25.12", ""), ("2022.12", "2028.11"),
                       ("2024-03-26", "")):
            rows = [{"nm": "현장%d" % i, "sd": sd, "ed": ed} for i in range(6)]
            self.assertEqual(kce_probe.grain_of(self._t(rows)), "project",
                             "%s %s" % (sd, ed))

    def test_detail_table_wins_over_summary(self):
        """삼성E&A는 요약표(3행)와 상세표(53행)를 같이 싣는다 — 상세표를 채택해야 한다."""
        summary = [{"nm": n, "sd": "", "ed": ""} for n in ("국내 관급", "국내 민간", "해외")]
        detail = [{"nm": "현장%d" % i, "sd": "201506", "ed": "203009"} for i in range(6)]
        self.assertEqual(kce_probe.grain_of([{"rows": summary}, {"rows": detail}]),
                         "project")


class TestProbeArtifact(unittest.TestCase):
    """커밋된 프로브 결과가 커버리지 페이지 계약을 지키는지."""

    def test_probe_covers_universe(self):
        recs = U.load()
        path = os.path.join(TOOLS, "assets", "probe_2026Q2.json")
        if not recs or not os.path.exists(path):
            self.skipTest("universe/probe 산출물 없음")
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        self.assertEqual({r["stock"] for r in p["rows"]},
                         {r["stock"] for r in recs}, "프로브가 모집단을 전부 덮지 않는다")
        for r in p["rows"]:
            self.assertIn(r["tier"], ("site", "segment", "agg", "none", "error"))
            # 등급이 site가 아니면 **사유가 반드시 남아야** 한다(조용한 배제 금지)
            if r["tier"] != "site":
                self.assertTrue(r["note"] or r["grain"], r["stock"])


if __name__ == "__main__":
    unittest.main()
