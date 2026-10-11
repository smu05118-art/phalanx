#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국건설 파이프라인 계약 테스트.

핵심 검증: 실제 DART 원문 fixture(2026.06 반기보고서, viewer.do로 수집)를 파싱한 값이
argus/kce/<co>/index.html에 임베드된 DATA의 2026Q2(실측) 값과 일치하는가.
실행: cd argus/kce/tools && python3 -m unittest discover -s tests -v
"""
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
KCE = os.path.dirname(TOOLS)
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, TOOLS)

from kce_lib import norm_col, num_of, q_of, q_next, extract_data  # noqa: E402
from kce_parse import parse_ii4, parse_p8, parse_tables  # noqa: E402

# fixture 보고서의 대상 분기. 새 분기가 추가돼도 인덱스를 다시 찾도록 상수로 박지 않는다.
FQ_TARGET = "2026Q2"


def _k(D):
    return D["fq"].index(FQ_TARGET)


def _fx(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def _data(co):
    return extract_data(os.path.join(KCE, co, "index.html"))


class TestDecode(unittest.TestCase):
    """거래소공시(EUC-KR) 판정 — 접수번호 9번째 자리가 8이면 전부 EUC-KR 이다."""

    def test_exchange_filings_are_euc_kr(self):
        from kce_fetch import _decode
        body = "단일판매".encode("euc-kr")
        for rcp in ("20250327800122", "20250327801172", "20260213801163"):
            self.assertEqual(_decode(body, rcp), "단일판매", rcp)

    def test_regular_reports_are_utf8(self):
        from kce_fetch import _decode
        self.assertEqual(_decode("반기".encode("utf-8"), "20260814002879"), "반기")


class TestNorm(unittest.TestCase):
    """headers.html 머리행 카탈로그의 실제 변형 사례가 흡수되는지."""

    def test_norm_col_catalog(self):
        cases = {
            "계약일 (공사착공일)": "계약일(공사착공일)",
            "완 공 예 정 일": "완공예정일",
            "기 본도 급 액": "기본도급액",
            "계약상 완성기한": "계약상완성기한",
            "진행률 (%)": "진행률",
            "(단위 : 백만원) 신고일자": "신고일자",
            "프로젝트명 (주1)": "프로젝트명",
            "판매ㆍ공급금액(백만원) 당기": "판매공급금액(백만원)당기",
            "판매/공급금액 누적": "판매공급금액누적",
        }
        for raw, want in cases.items():
            self.assertEqual(norm_col(raw), want, raw)

    def test_num_of(self):
        self.assertEqual(num_of("1,234,567"), 1234567)
        self.assertEqual(num_of("99.00%"), 99)
        self.assertEqual(num_of("(1,000)"), -1000)
        self.assertIsNone(num_of("-"))
        self.assertIsNone(num_of(""))
        self.assertIsNone(num_of("USD 2,426,809,931"))  # 외화 표기는 별도 처리

    def test_quarters(self):
        self.assertEqual(q_of(2026, 6), "2026Q2")
        self.assertEqual(q_next("2026Q4"), "2027Q1")


class TestII4Reconcile(unittest.TestCase):
    """II-4 파싱값 ↔ 임베드 DATA 2026Q2 실측값 대조."""

    def _measured(self, D):
        K = _k(D)
        out = []
        for s in D["sites"]:
            sf = s.get("sFilled") or [None] * len(D["fqF"])
            if s["s"]["bal"][K] is not None and sf[K] is None and not s.get("agg"):
                out.append(s)
        return out

    def _triples(self, sites, K):
        d = {}
        for s in sites:
            k = (s["s"]["amt"][K], s["s"]["cmp"][K], s["s"]["bal"][K])
            d[k] = d.get(k, 0) + 1
        return d

    def _reconcile(self, co, fixture, min_match):
        D = _data(co)
        K = _k(D)
        r = parse_ii4(_fx(fixture))
        self.assertEqual(r["unknown_headers"], [], "미지 헤더 발생")
        rows = [x for t in r["tables"] for x in t["rows"]]
        meas = self._measured(D)
        dset = self._triples(meas, K)
        hit, misses = 0, []
        for x in rows:
            key = (x["amt"], x["cmp"], x["bal"])
            if dset.get(key):
                dset[key] -= 1
                hit += 1
            else:
                misses.append(x)
        # 개별 사업장 전건 일치, 불일치는 합계·기타 집계 행뿐이어야 한다
        self.assertGreaterEqual(hit, min_match)
        for m in misses:
            nm = norm_col(m.get("nm") or "")
            ok = (nm.endswith("합계") or nm in ("기타", "계", "소계")
                  or "외" in nm and "현장" in nm      # '… 외 N개 현장' 기타 행
                  or m["bal"] is None)
            self.assertTrue(ok, "개별 사업장 불일치: %r" % (m,))
        return rows, meas, D

    def test_sct(self):
        rows, meas, D = self._reconcile("sct", "sct_상세표_건설수주.html", 79)
        K = _k(D)
        self.assertEqual(len(meas), 79)
        # 상류 vintage가 7사→17사로 확장되며 삼성물산도 summary를 **원문 총계**로
        # 바꿨다(Σ실측 25,179,310 → 공시 34,245,477). 차액은 상세표에 개별 기재되지
        # 않은 소규모 현장 몫이라 정상이다 — 두 값이 같아야 한다는 옛 계약은 더 이상
        # 성립하지 않는다. 대신 방향(공시 총계 ≥ Σ실측)과 산출 라벨을 검증한다.
        self.assertTrue(D["summary"]["src"]["삼성물산"][K].startswith("공시"))
        self.assertGreaterEqual(D["summary"]["total"][K],
                                sum(s["s"]["bal"][K] for s in meas))
        # summary.total은 언제나 법인별 rows의 합이어야 한다(집계 불변식).
        self.assertEqual(D["summary"]["total"][K],
                         sum(D["summary"]["rows"][e][K] or 0
                             for e in D["summary"]["ents"]))

    def test_hec(self):
        rows, meas, D = self._reconcile("hec", "hec_수주상황.html", 109)
        K = _k(D)
        self.assertEqual(len(meas), 109)
        # hec는 src='공시총계' — summary.total은 사이트 합보다 크다(LOGIC.md §3.5)
        self.assertGreater(D["summary"]["total"][K],
                           sum(s["s"]["bal"][K] for s in meas))


class TestP8Reconcile(unittest.TestCase):
    """III-8 파싱값 ↔ DATA. 빌더는 별도=연결 동일값이면 연결을 생략(중복 제거)하고,
    표의 연결/별도 순서는 회사·분기마다 뒤집히므로 값 대조로 배정을 검증한다."""

    def _dvals(self, D, basis):
        K = _k(D)
        d = {}
        for s in D["sites"]:
            b = (s.get("p8") or {}).get(basis)
            if b and b["tot"][K] is not None:
                k = (b["tot"][K], b["ub"][K], b["rc"][K])
                d[k] = d.get(k, 0) + 1
        return d

    def _hits(self, rows, dv):
        dv = dict(dv)
        n = 0
        for x in rows:
            k = (x["amt"], x["ub"], x["rc"])
            if dv.get(k):
                dv[k] -= 1
                n += 1
        return n

    def test_sct(self):
        D = _data("sct")
        r = parse_p8(_fx("sct_기타재무_진행률수주.html"))
        self.assertEqual(r["unknown_headers"], [])
        tabs = {len([x for x in t["rows"] if x["amt"] is not None]): t for t in r["tables"]}
        # 별도 표 22행 → DATA 별도 22건 전건 일치
        sep_rows = [x for x in tabs[22]["rows"] if x["amt"] is not None]
        self.assertEqual(self._hits(sep_rows, self._dvals(D, "별도")), 22)
        # 연결 표 15행 중 별도와 다른 3건만 DATA 연결에 저장(중복 제거 규칙)
        con_rows = [x for x in tabs[15]["rows"] if x["amt"] is not None]
        self.assertEqual(self._hits(con_rows, self._dvals(D, "연결")), 3)

    def test_hec(self):
        D = _data("hec")
        r = parse_p8(_fx("hec_기타재무_진행률수주.html"))
        self.assertEqual(r["unknown_headers"], [])
        tabs = {len([x for x in t["rows"] if x["amt"] is not None]): t for t in r["tables"]}
        sep_rows = [x for x in tabs[43]["rows"] if x["amt"] is not None]
        self.assertEqual(self._hits(sep_rows, self._dvals(D, "별도")), 43)
        con_rows = [x for x in tabs[30]["rows"] if x["amt"] is not None]
        self.assertEqual(self._hits(con_rows, self._dvals(D, "연결")), 16)


class TestDataContract(unittest.TestCase):
    """복제본 7사 DATA의 구조 계약(LOGIC.md §2·§5) 회귀 테스트."""

    COS = ["sct", "hec", "sea", "dwe", "gse", "dle", "ipark"]

    def test_axes_and_totals(self):
        for co in self.COS:
            D = _data(co)
            # 길이를 박지 않고 **관계**를 검증한다 — 새 분기가 들어오면 20/24가 된다.
            self.assertGreaterEqual(len(D["fq"]), 19, co)
            self.assertEqual(len(D["fqF"]), len(D["fq"]) + 4, co)
            self.assertEqual(D["fqF"][:len(D["fq"])], D["fq"], co)
            n = len(D["fqF"])
            for s in D["sites"]:
                for key in ("amt", "cmp", "bal", "pr"):
                    self.assertEqual(len(s["s"][key]), n, (co, s["id"], key))
            # summary.total == Σ법인 rows (수치검증 §5에서 오차 0 확인된 계약)
            for k in range(n):
                vals = [D["summary"]["rows"][e][k] for e in D["summary"]["ents"]]
                if all(v is None for v in vals):
                    self.assertIsNone(D["summary"]["total"][k], (co, k))
                else:
                    self.assertEqual(sum(v or 0 for v in vals),
                                     D["summary"]["total"][k], (co, k))

class TestDartGate(unittest.TestCase):
    """DART는 공인 IP 단위로 막는다 — 수집기 프로세스가 여러 개여도 총 요청률은 하나여야 한다."""

    def test_pace_is_shared_across_processes(self):
        import subprocess
        import tempfile
        import kce_fetch
        if kce_fetch.fcntl is None:
            self.skipTest("fcntl 없음 — 프로세스 간 게이트 비활성")
        gate = os.path.join(tempfile.mkdtemp(), "gate")
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        code = ("import sys, time; sys.path.insert(0, %r); import kce_fetch as f; f.MIN_GAP = 0.3\n"
                "t = time.time()\n"
                "[f._pace() for _ in range(4)]\n"
                "print('%%.3f' %% (time.time() - t))" % here)
        env = dict(os.environ, DART_GATE=gate)
        t0 = time.time()
        ps = [subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE, text=True)
              for _ in range(3)]
        for p in ps:
            p.communicate()
        elapsed = time.time() - t0
        # 12요청 × 0.3초 = 3.6초. 게이트가 없으면 프로세스마다 1.2초(≈1.2초 전체)로 끝난다.
        self.assertGreater(elapsed, 3.6 * 0.7, "프로세스 간 요청 간격이 지켜지지 않는다(%0.2fs)" % elapsed)

class TestPickReport(unittest.TestCase):
    """[첨부정정] 문서는 본문이 '정정 신고'·'영업보고서' 두 줄뿐이라 II절이 없을 때가 많다 —
    기준월이 맞아도 원본 뒤로 민다(버리지는 않는다). kaero 웨이브가 실측으로 보고한 건."""

    def test_pick_report_defers_attachment_corrections(self):
        from kce_fetch import pick_report
        reports = [("2026A", "[첨부정정]반기보고서 (2026.06)"),
                   ("2026B", "반기보고서 (2026.06)"),
                   ("2025C", "반기보고서 (2025.06)")]
        got = [r for r, _ in pick_report(reports, "2026Q2")]
        self.assertEqual(got, ["2026B", "2026A", "2025C"])

    def test_pick_report_keeps_correction_when_it_is_the_only_one(self):
        from kce_fetch import pick_report
        reports = [("2026A", "[첨부정정]반기보고서 (2026.06)"), ("2025C", "반기보고서 (2025.06)")]
        self.assertEqual([r for r, _ in pick_report(reports, "2026Q2")], ["2026A", "2025C"])


if __name__ == "__main__":
    unittest.main()


class TestOrderTableVariants(unittest.TestCase):
    """2026Q2 원문 실측으로 확인한 두 변형. 셋 다 '미수록'으로 남아 있던 회사들이다.
    증거: tools/assets/unrecorded_probe.json (접수번호·표 lead·행)."""

    def _tab(self, html):
        from kce_parse import parse_ii4
        return parse_ii4(html)

    def test_progress_style_order_table(self):
        """특수건설 `나. 수주현황` — 도급액·완성공사액·잔액 대신 계약금액·진행률(%)."""
        html = ("<p>나. 수주현황 (단위: 원)</p><table>"
                "<tr><th>현장명</th><th>구분</th><th>계약금액</th><th>계약일</th>"
                "<th>종료예정일</th><th>진행률(%)</th></tr>"
                "<tr><td>영종도해저송수관로</td><td>쉴드</td><td>33,400,584,000</td>"
                "<td>2022/06/02</td><td>2026/12/19</td><td>94.91%</td></tr></table>")
        out = self._tab(html)
        self.assertEqual(len(out["tables"]), 1, "진행률형 수주표를 인식하지 못했다")
        r = out["tables"][0]["rows"][0]
        self.assertEqual(r["nm"], "영종도해저송수관로")
        self.assertAlmostEqual(r["amt"], 33400.584, places=3)        # 원 → 백만원
        self.assertEqual(r["ed"], "2026/12/19")                       # 종료예정일 별칭
        self.assertAlmostEqual(r["cmp"], 33400.584 * 0.9491, places=2)
        self.assertIn("cmp", r.get("_derived", ""), "유도값 표시가 없다")

    def test_unit_caption_row_does_not_kill_table(self):
        """KCC건설 상세표 — 첫 행이 `(단위:원)` 반복이라 머리행 감지가 실패하던 표."""
        html = ("<p>(1) 관급공사</p><table>"
                "<tr><td>(단위:원)</td><td>(단위:원)</td><td>(단위:원)</td>"
                "<td>(단위:원)</td><td>(단위:원)</td></tr>"
                "<tr><td>발 주 처</td><td>공 사 명</td><td>기본도급액</td>"
                "<td>완성공사액</td><td>계약잔액</td></tr>"
                "<tr><td>국가철도공단</td><td>삼성동탄 광역철도 1공구</td><td>70,083,347,955</td>"
                "<td>69,157,646,103</td><td>925,701,852</td></tr></table>")
        out = self._tab(html)
        self.assertEqual(len(out["tables"]), 1, "단위 캡션 행 때문에 표가 버려졌다")
        r = out["tables"][0]["rows"][0]
        self.assertEqual(r["cl"], "국가철도공단")
        self.assertAlmostEqual(r["amt"], 70083.347955, places=5)      # 캡션이 살아 원→백만원 환산
        self.assertAlmostEqual(r["bal"], 925.701852, places=5)

    def test_revenue_table_is_not_taken_as_orders(self):
        """매출실적 표를 수주표로 세면 안 된다 — 미수록 5사가 이 함정에 걸려 있었다."""
        html = ("<p>4. 매출 및 수주상황 가. 매출실적 (단위: 백만원)</p><table>"
                "<tr><th>사업부문</th><th>매출유형</th><th>품목</th><th>제29기</th></tr>"
                "<tr><td>인테리어</td><td>제품</td><td>건설공사</td><td>4,442</td></tr></table>")
        self.assertEqual(len(self._tab(html)["tables"]), 0)


class TestHeaderMapDialects(unittest.TestCase):
    """머리행 지도(headers.html) 17사 전수 대조(2026-10-11)에서 라이브 7사 밖 회사들의 방언.
    원문 구조를 합성 표로 재현했다 — 실제 원문 픽스처는 DART 수집 후 추가한다."""

    def test_aliases_from_header_map(self):
        from kce_lib import COL_ALIAS
        for raw, want in (("완공(예정)일", "ed"), ("완공종료일", "ed"), ("발주", "cl"), ("진행율", "pr"),
                          ("용역명", "nm"), ("품목(공사명)", "nm"), ("기본도급액 금액", "amt"),
                          ("완성공사액 금액", "cmp"), ("계약잔액 금액", "bal"),
                          ("공사미수금 대손", "allw"), ("미청구공사 손상차손", "ubimp")):
            self.assertEqual(COL_ALIAS.get(norm_col(raw)), want, raw)
        self.assertEqual(norm_col("계약금액총액*2)"), "계약금액총액")      # 동부건설 XI-1 각주 표식
        self.assertEqual(norm_col("공시일자*1)"), "공시일자")

    def test_dongbu_p8_two_row_header(self):
        """동부건설 III-8 — 기본도급액/완성공사액/계약잔액 아래 '금액' 둘째 머리행, 이름 열은 '용역명'."""
        html = ("<p>(1) 연결 기준 (단위 : 백만원)</p><table>"
                "<tr><th rowspan='2'>용역명</th><th rowspan='2'>발주처</th><th rowspan='2'>계약일</th>"
                "<th rowspan='2'>준공일</th><th>기본도급액</th><th>완성공사액</th><th>계약잔액</th>"
                "<th rowspan='2'>진행률</th><th rowspan='2'>미청구공사 총액</th>"
                "<th rowspan='2'>미청구공사 손상 차손 누계액</th><th rowspan='2'>공사미수금 총액</th>"
                "<th rowspan='2'>공사미수금 대손 충당금</th></tr>"
                "<tr><th>금액</th><th>금액</th><th>금액</th></tr>"
                "<tr><td>A아파트 신축</td><td>B조합</td><td>2024.01.01</td><td>2026.12.31</td>"
                "<td>10,000</td><td>4,000</td><td>6,000</td><td>40.0</td><td>100</td><td>0</td>"
                "<td>50</td><td>0</td></tr></table>")
        out = parse_p8(html)
        self.assertEqual(out["unknown_headers"], [])
        self.assertEqual(len(out["tables"]), 1)
        r = out["tables"][0]["rows"][0]
        self.assertEqual((r["nm"], r["amt"], r["pr"], r["ub"], r["rc"]), ("A아파트 신축", 10000, 40.0, 100, 50))
        self.assertEqual(out["tables"][0]["basis"], "연결")

    def test_kumho_p8_meta_table_skipped_amount_table_read(self):
        """금호건설 III-8 2021Q4~2025Q3 — 메타표(진행률·계약금액·공사기한)와 금액표('진행율')가 따로 있다."""
        meta = ("<p>(1) 연결 기준</p><table>"
                "<tr><td>구분</td><td>공사명</td><td>발주처</td><td>진행률</td><td>계약금액</td>"
                "<td>계약일</td><td>공사기한</td></tr>"
                "<tr><td>건축</td><td>C현장</td><td>D공사</td><td>55.0</td><td>20,000</td>"
                "<td>2023.03.01</td><td>2027.02.28</td></tr>"
                "<tr><td>토목</td><td>E현장</td><td>F시</td><td>12.0</td><td>30,000</td>"
                "<td>2025.01.01</td><td>2028.12.31</td></tr>"
                "<tr><td>건축</td><td>G현장</td><td>H조합</td><td>80.0</td><td>40,000</td>"
                "<td>2022.01.01</td><td>2026.06.30</td></tr></table>")
        amount = ("<table><tr><td>구분</td><td>공사명</td><td>발주처</td><td>진행율</td><td>계 약일</td>"
                  "<td>완공 예정 일</td><td>기 본 도 급액</td><td>완성 공사액</td><td>계약잔액</td>"
                  "<td>공사미수금 총액</td><td>공사미수금 대손 충당금</td><td>미청구공사 총액</td>"
                  "<td>미청구공사 손상 차손 누계액</td></tr>"
                  "<tr><td>건축</td><td>C현장</td><td>D공사</td><td>55.0</td><td>2023.03.01</td>"
                  "<td>2027.02.28</td><td>20,000</td><td>11,000</td><td>9,000</td><td>300</td><td>0</td>"
                  "<td>700</td><td>0</td></tr></table>")
        out = parse_p8(meta + amount)
        self.assertEqual(out["unknown_headers"], [], "메타표를 미지 헤더로 올리면 갱신이 멈춘다")
        self.assertEqual(len(out["tables"]), 1)
        r = out["tables"][0]["rows"][0]
        self.assertEqual((r["nm"], r["amt"], r["pr"], r["ub"], r["rc"]), ("C현장", 20000, 55.0, 700, 300))

    def test_kumho_p8_single_table_2025q4(self):
        """금호건설 III-8 2025Q4~ — 표 하나에 계약금액(=수주총액)·진행률·미수금·미청구·초과청구공사."""
        html = ("<p>(1) 연결 기준</p><table>"
                "<tr><td>(단위: 백만원) 구분</td><td>(단위: 백만원) 공사명</td><td>(단위: 백만원) 발주처</td>"
                "<td>(단위: 백만원) 진행률</td><td>(단위: 백만원) 계약금액</td><td>(단위: 백만원) 계약일</td>"
                "<td>(단위: 백만원) 공사기한</td><td>(단위: 백만원) 공사미수금 총액</td>"
                "<td>(단위: 백만원) 공사미수금 대손충당금</td><td>(단위: 백만원) 미청구공사 총액</td>"
                "<td>(단위: 백만원) 미청구공사 대손충당금</td><td>(단위: 백만원) 초과청구공사</td></tr>"
                "<tr><td>건축</td><td>C현장</td><td>D공사</td><td>61.5</td><td>20,000</td><td>2023.03.01</td>"
                "<td>2027.02.28</td><td>250</td><td>0</td><td>640</td><td>0</td><td>90</td></tr></table>")
        out = parse_p8(html)
        self.assertEqual(out["unknown_headers"], [])
        self.assertEqual(len(out["tables"]), 1)
        r = out["tables"][0]["rows"][0]
        self.assertEqual((r["nm"], r["amt"], r["pr"], r["ub"], r["rc"]), ("C현장", 20000, 61.5, 640, 250))

    def test_kyeryong_ii4_section_rows(self):
        """계룡건설 II-4 2023Q4~ — '건축'·'토목' 공종 소제목이 머리행 둘째 줄(또는 본문 줄)로 끼어든다."""
        head = ("<p>가. 수주상황 (단위 : 백만원)</p><table>"
                "<tr><th>현장명</th><th>착공일</th><th>완공예정일</th><th>총 도급금액</th>"
                "<th>완성공사액</th><th>계약잔액</th></tr>")
        site1 = ("<tr><td>I오피스텔 신축</td><td>2023.05.01</td><td>2026.04.30</td><td>50,000</td>"
                 "<td>30,000</td><td>20,000</td></tr>")
        site2 = ("<tr><td>J도로 확장</td><td>2024.02.01</td><td>2027.01.31</td><td>80,000</td>"
                 "<td>8,000</td><td>72,000</td></tr>")
        # (a) 소제목이 본문 줄로: 병합된 한 칸
        out = parse_ii4(head + "<tr><td colspan='6'>건축</td></tr>" + site1
                        + "<tr><td colspan='6'>토목</td></tr>" + site2 + "</table>")
        self.assertEqual(out["unknown_headers"], [])
        self.assertEqual(len(out["tables"]), 1)
        self.assertEqual([r["nm"] for r in out["tables"][0]["rows"]], ["I오피스텔 신축", "J도로 확장"])
        self.assertEqual(out["tables"][0]["rows"][0]["amt"], 50000)           # 총 도급금액 → amt
        # (b) 소제목이 머리행 둘째 줄로: 평탄화하면 '현장명 건축' — 접미를 벗겨 읽는다
        head2 = ("<p>가. 수주상황 (단위 : 백만원)</p><table>"
                 "<tr><th>현장명</th><th>착공일</th><th>완공예정일</th><th>총 도급금액</th>"
                 "<th>완성공사액</th><th>계약잔액</th></tr><tr><th colspan='6'>건축</th></tr>")
        out = parse_ii4(head2 + site1 + "</table>")
        self.assertEqual(out["unknown_headers"], [])
        self.assertEqual(len(out["tables"]), 1)
        self.assertEqual(out["tables"][0]["rows"][0]["nm"], "I오피스텔 신축")
        self.assertEqual(out["tables"][0]["rows"][0]["bal"], 20000)
