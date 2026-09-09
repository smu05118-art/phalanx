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


if __name__ == "__main__":
    unittest.main()
