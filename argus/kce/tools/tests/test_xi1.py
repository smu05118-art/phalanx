#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""XI-1 「나. 단일판매ㆍ공급계약 진행 현황」 — 2026Q2 반기보고서 14사 원문(viewer.do 실수집) 픽스처.

검증 기준: 라이브 7사 DATA.xip 2026Q2 와 **이름이 같은 계약**의 계약금액·판매공급 누적이 전부 일치.
이름이 다른 61건은 상류가 '가. 공시내용 진행' 표의 제목(더 길다: `… 공사도급 및 PM용역 기본계약`)이나
주석 표식(`(*2)`)을 붙여 쓴 것이고, 우리는 '나' 표 원문 그대로 둔다(매칭은 최소 구현 범위 밖)."""
import glob
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
KCE = os.path.dirname(TOOLS)
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, TOOLS)

import kce_xi1 as X  # noqa: E402
from kce_lib import COL_ALIAS, extract_data  # noqa: E402
import kce_parse as KP  # noqa: E402

COS = ["dbe", "dle", "dwe", "gse", "hdi", "hec", "hse", "ipark", "khe", "klg", "kre", "sct", "sea", "xsd"]
LIVE = ["sct", "hec", "sea", "dwe", "gse", "dle", "ipark"]


def _parse(co):
    with open(os.path.join(FIX, "%s_xi1_2026Q2.html" % co), encoding="utf-8") as f:
        return X.parse_xi1(f.read())


def _rows(co):
    return [r for t in _parse(co)["tables"] for r in t["rows"]]


class TestXi1Parse(unittest.TestCase):
    def test_14co_tables_and_rows(self):
        want = {"dbe": 76, "dle": 51, "dwe": 74, "gse": 60, "hdi": 43, "hec": 49, "hse": 34, "ipark": 47,
                "khe": 34, "klg": 95, "kre": 65, "sct": 20, "sea": 19, "xsd": 21}
        got = {}
        for co in COS:
            p = _parse(co)
            self.assertEqual(len(p["tables"]), 1, co)
            self.assertEqual(p["unknown_headers"], [], co)        # 향후추진계획 부표는 미지가 아니다
            got[co] = p["tables"][0]["n_rec"]
        self.assertEqual(got, want)
        self.assertEqual(sum(got.values()), 688)

    def test_column_unit_beats_table_unit(self):
        sea = _parse("sea")["tables"][0]
        self.assertEqual(sea["unit"], 1e-06)                       # 표 단위 원
        sct = _rows("sct")
        self.assertTrue(any(r.get("amt") for r in sct))            # 계약금액총액(원) 열만 원 → 백만원
        khe = _parse("khe")["tables"][0]
        self.assertEqual(khe["unit"], 100.0)                       # 억원
        r = _rows("dwe")[0]
        self.assertAlmostEqual(r["amt"], 222875.1045, places=4)    # 열 단위 원 → 백만원(소수 보존)

    def test_sea_rowspan_pair_is_one_contract(self):
        rows = _rows("sea")
        self.assertEqual(len(rows), 19)                            # 원문 21줄 → 계약금액 rowspan 2쌍 합침
        self.assertTrue(any(r.get("nm_more") for r in rows))

    def test_foreign_currency_amount(self):
        rows = [r for co in COS for r in _rows(co) if r.get("cur")]
        self.assertTrue(rows)
        for r in rows:
            self.assertIsNone(r["amt"])
            self.assertRegex(r["cur"], r"^[A-Z]{3}$")

    def test_detail_split(self):
        d = X.split_detail("계약명 : A현장 신축공사 계약상대방 : B조합 계약기간 : 2024.01.01~2027.12.31")
        self.assertEqual((d["계약명"], d["계약상대방"], d["계약기간"]), ("A현장 신축공사", "B조합", "2024.01.01~2027.12.31"))
        d = X.split_detail("계약명: C공사계약상대방: D공사")                 # 줄바꿈이 지워져 라벨이 붙은 꼴
        self.assertEqual((d["계약명"], d["계약상대방"]), ("C공사", "D공사"))
        self.assertEqual(X.split_detail("- E 재개발사업")["계약명"], "E 재개발사업")
        cl = sum(1 for co in COS for r in _rows(co) if r.get("cl"))
        self.assertGreaterEqual(cl, 520)

    def test_norm_dt(self):
        self.assertEqual(X.norm_dt("2026-06-17"), "2026.06.17")
        self.assertEqual(X.norm_dt("`26.06.25(변경계약)"), "2026.06.25")
        self.assertEqual(X.norm_dt("'25.12.30.(변경계약)"), "2025.12.30")
        self.assertIsNone(X.norm_dt("-"))

    def test_global_dictionary_unchanged(self):
        """XI 어휘는 지역 — 전역 COL_ALIAS·머리행 어휘는 그대로(6개 탭 공용)."""
        self.assertEqual(COL_ALIAS.get("계약명"), "nm")
        self.assertEqual(COL_ALIAS.get("구분"), "nm")
        self.assertNotIn("대금수령금액당기", KP._HDR_VOCAB)
        self.assertNotIn("판매공급금액(백만원)누적", COL_ALIAS)


class TestXi1AgainstData(unittest.TestCase):
    def test_live7_amounts_match(self):
        norm = lambda s: re.sub(r"[\s()（）\[\]·ㆍ,.\-*]", "", s or "")
        tot = dict(ref=0, nm=0, amt=0, amt_ok=0, sc=0, sc_ok=0)
        for co in LIVE:
            D = extract_data(os.path.join(KCE, co, "index.html"))
            if "2026Q2" not in D["fq"]:
                self.skipTest("DATA 축에 2026Q2 없음")
            k = D["fq"].index("2026Q2")
            got = {norm(r["nm"]): r for r in _rows(co)}
            for s in D["sites"]:
                x = s.get("xip") or {}
                if not x.get("nm"):
                    continue
                a = (x.get("amt") or [None] * (k + 1))[k]
                sc = (x.get("supCum") or [None] * (k + 1))[k]
                if a is None and sc is None:
                    continue
                tot["ref"] += 1
                r = got.get(norm(x["nm"]))
                if not r:
                    continue
                tot["nm"] += 1
                if a is not None:
                    tot["amt"] += 1
                    tot["amt_ok"] += r.get("amt") is not None and abs(r["amt"] - a) <= max(1, abs(a) * 1e-6)
                if sc is not None:
                    tot["sc"] += 1
                    tot["sc_ok"] += r.get("supCum") is not None and abs(r["supCum"] - sc) <= max(1, abs(sc) * 1e-6)
        self.assertGreaterEqual(tot["nm"], 255)
        self.assertEqual(tot["amt_ok"], tot["amt"])
        self.assertEqual(tot["sc_ok"], tot["sc"])


class TestXi1Apply(unittest.TestCase):
    def test_apply_headers_cache_and_absent(self):
        with tempfile.TemporaryDirectory() as raw, tempfile.TemporaryDirectory() as cache:
            rep = {"headers": {}}
            self.assertIsNone(X.apply("hec", "2026Q2", raw, None, 0, rep))
            self.assertEqual(rep["xi1_status"], "absent")
            self.assertNotIn("xinb", rep["headers"])
            with open(os.path.join(FIX, "hec_xi1_2026Q2.html"), encoding="utf-8") as f, \
                    open(os.path.join(raw, "hec_xi1.html"), "w", encoding="utf-8") as g:
                g.write(f.read())
            rep = {"headers": {}}
            X.apply("hec", "2026Q2", raw, None, 0, rep, queue=False, cache_root=cache)
            self.assertEqual(rep["xi1_status"], "ok")
            picked = [h for h in rep["headers"]["xinb"] if h["pick"]]
            self.assertEqual([h["tag"] for h in picked], ["나"])
            self.assertEqual(picked[0]["n_rec"], 49)
            self.assertFalse(glob.glob(os.path.join(cache, "*", "*.json")))   # dry-run 은 캐시를 쓰지 않는다
            X.apply("hec", "2026Q2", raw, None, 0, {"headers": {}}, queue=True, cache_root=cache,
                    hdr_root=cache)
            with open(os.path.join(cache, "xi1_cache", "hec", "2026Q2.json"), encoding="utf-8") as f:
                doc = json.load(f)
            self.assertEqual(len(doc["tables"][0]["rows"]), 49)


if __name__ == "__main__":
    unittest.main()


class TestXi1Match(unittest.TestCase):
    """정답지 = 라이브 7사 DATA 2026Q2 의 원본 연결(사람 판정 포함). 오매칭 0 이어야 데이터에 쓴다.

    정답지 자체의 오류로 판단해 '오답'에서 뺀 2건(원본이 금액이 안 맞는 사업장에 붙였거나 신규로 뺀 건):
      · DL이앤씨 `여수신기주공지역주택조합 신축사업` — 원본은 DLE-2-0303(완성공사액 83,522), 우리는 판매공급 누적
        221,385 와 완성공사액이 **정확히 같은** DLE-2-0139(e편한세상 여수 글렌츠).
      · 대우건설 `남양주왕숙 … 통합형 민간참여 공공주택건설사업` — 원본은 XI-1 전용 신규, 우리는 누적 21,722 가 정확히
        같은 DWE-2-0249(왕숙푸르지오더퍼스트1단지)."""
    KEY_ERRORS = {("dle", "여수신기주공지역주택조합 신축사업"), ("dwe", "남양주왕숙")}

    def _eval(self, warm):
        import copy
        C = {"site": 0, "auto": 0, "wrong": 0, "new_auto": 0}
        for co in LIVE:
            D = extract_data(os.path.join(KCE, co, "index.html"))
            k = D["fq"].index("2026Q2")
            rows = _rows(co)
            truth = {}
            for i, r in enumerate(rows):
                hit = [s for s in D["sites"] if s.get("xip") and r.get("amt") is not None
                       and (s["xip"].get("amt") or [None] * 30)[k] == r.get("amt")
                       and (s["xip"].get("supCum") or [None] * 30)[k] == r.get("supCum")]
                if len(hit) != 1:
                    hit = [s for s in D["sites"] if s.get("xip") and X.nkey(s["xip"].get("nm")) == X.nkey(r["nm"])
                           and (s["xip"].get("amt") or [None] * 30)[k] is not None]
                if len(hit) == 1:
                    truth[i] = (hit[0]["id"], hit[0]["xip"].get("mt"))
            D2 = copy.deepcopy(D)
            for s in D2["sites"]:
                if not warm:
                    s.pop("xip", None)
                    s.pop("xipFull", None)
                elif s.get("xip"):
                    for f in X.XIP_ARR:
                        a = s["xip"].get(f)
                        if isinstance(a, list):
                            s["xip"][f] = [v if j < k else None for j, v in enumerate(a)]
            m = X.match_rows(D2, k, rows)
            for i, (site, mt, how, _g) in enumerate(m):
                t = truth.get(i)
                if t is None or not mt:
                    continue
                key_err = any(co == c and n in rows[i]["nm"] for c, n in self.KEY_ERRORS)
                if t[1] == "XI-1 전용(신규)":
                    C["new_auto"] += 1
                    if site != t[0] and not key_err:
                        C["wrong"] += 1
                    continue
                C["auto"] += 1
                if site != t[0] and not key_err:
                    C["wrong"] += 1
            C["site"] += sum(1 for t in truth.values() if t[1] != "XI-1 전용(신규)")
        return C

    def test_warm_history_zero_wrong(self):
        C = self._eval(True)
        self.assertEqual(C["wrong"], 0, C)
        self.assertGreaterEqual(C["auto"], 250, C)          # 실측 255/259

    def test_cold_zero_wrong(self):
        C = self._eval(False)
        self.assertEqual(C["wrong"], 0, C)
        self.assertGreaterEqual(C["auto"], 160, C)          # 이력 없는 첫 적재 — 실측 166/259, 나머지는 검토 목록

    def test_reapply_reproduces_values(self):
        """2026Q2 값을 지우고 다시 쓰면 매칭된 사업장의 xip 값이 원래와 같다."""
        import copy
        D = extract_data(os.path.join(KCE, "hec", "index.html"))
        k = D["fq"].index("2026Q2")
        D2 = copy.deepcopy(D)
        for s in D2["sites"]:
            if s.get("xip"):
                for f in X.XIP_ARR:
                    if isinstance(s["xip"].get(f), list):
                        s["xip"][f][k] = None
        rows = _rows("hec")
        m = X.match_rows(D2, k, rows)
        n = X.apply_data(D2, k, rows, m)
        self.assertGreaterEqual(n, 45)
        orig = {s["id"]: s for s in D["sites"]}
        for s in D2["sites"]:
            if s.get("xip") and s["xip"].get("amt") and s["xip"]["amt"][k] is not None:
                self.assertEqual(s["xip"]["amt"][k], orig[s["id"]]["xip"]["amt"][k], s["id"])
                self.assertEqual(s["xip"]["supCum"][k], orig[s["id"]]["xip"]["supCum"][k], s["id"])

    def test_fill_overrides_and_review_file(self):
        import copy
        D = extract_data(os.path.join(KCE, "dle", "index.html"))
        k = D["fq"].index("2026Q2")
        D2 = copy.deepcopy(D)
        for s in D2["sites"]:
            s.pop("xip", None)
            s.pop("xipFull", None)
        rows = _rows("dle")
        some = rows[0]["nm"]
        m = X.match_rows(D2, k, rows, {X.nkey(some): "SKIP"})
        self.assertIsNone(m[0][1])
        site = D2["sites"][0]["id"]
        m = X.match_rows(D2, k, rows, {X.nkey(some): site})
        self.assertEqual(m[0][:2], (site, "매칭(수동보정)"))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.csv")
            n = X.write_review("dle", "2026Q2", rows, m, D2, path=p)
            self.assertEqual(n, sum(1 for x in m if not x[1]))
            n2 = X.write_review("dle", "2026Q2", rows, m, D2, path=p)       # 멱등: 같은 줄 교체
            with open(p, encoding="utf-8") as f:
                self.assertEqual(len(f.read().strip().splitlines()) - 1, n2)
