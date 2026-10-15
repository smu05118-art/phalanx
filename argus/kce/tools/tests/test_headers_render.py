#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""머리행 지도 kce 통합(U2) — rep['headers'] 가 상류 지도 D 의 관례를 재현하는가, 기록 경로가 fail-closed 인가.

정답지는 이미 있다: fixtures/headers_2026Q2.html = 상류 headers.html 2026-09-10 스냅샷(17사 × ii4/p8/xinb 1,302표).
2026Q2 원문 픽스처(동부·금호·계룡·현대)를 **재적재 경로 그대로**(kce_build.update_quarter, dry-run) 태워 만든
rep['headers'] 가 D 의 2026Q2 항목과 cols·tag·ent·n 이 같아야 한다 — 같지 않으면 우리 첫 갱신 분기가 지도에서
통째로 「바뀜」으로 뜬다(대조 키 ent|tag#순번, headers.html JS).

배포 파일(argus/kce/headers.html·hdrmap.json·hdr_queue.json)은 건드리지 않는다 — 렌더·기록은 전부 임시 사본·임시 루트.
실행: cd argus/kce/tools && python3 -m unittest discover -s tests
"""
import copy
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
KCE = os.path.dirname(TOOLS)
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, TOOLS)

import hdrmap                                   # noqa: E402
import kce_build as KB                          # noqa: E402
import kce_page                                 # noqa: E402
import kce_parse as P                           # noqa: E402
import kce_probe                                # noqa: E402
import kce_render                               # noqa: E402
import kce_series as KS                         # noqa: E402
import kce_universe as U                        # noqa: E402
import hdrmap_onboard as HO                     # noqa: E402
from kce_lib import extract_data                # noqa: E402

HEADERS_FX = os.path.join(FIX, "headers_2026Q2.html")
Q = "2026Q2"
# 회사별 2026Q2 원문 픽스처 → update_quarter 가 읽는 raw 파일 이름(<co>_<절>.html)
RAW = {
    "dbe": {"ii4x": "dbe_ii4x_2026Q2.html", "p8": "dbe_p8_2026Q2.html"},
    "khe": {"ii4x": "khe_ii4x_2026Q2.html", "p8": "khe_p8_2026Q2.html"},
    "kre": {"ii4": "kre_ii4_2026Q2.html", "p8": "kre_p8_2026Q2.html"},
    "hec": {"ii4": "hec_수주상황.html", "p8": "hec_기타재무_진행률수주.html"},
    "sct": {"ii4": "sct_수주상황.html", "ii4x": "sct_상세표_건설수주.html", "p8": "sct_기타재무_진행률수주.html"},
}


def _upstream():
    with open(HEADERS_FX, encoding="utf-8") as f:
        return hdrmap._parse_page(f.read())[0]


def _read(fn):
    with open(os.path.join(FIX, fn), "rb") as f:
        b = f.read()
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:                  # hec_단일판매공급계약.html 은 수시공시(EUC-KR)
        return b.decode("cp949", errors="replace")


class _TmpRoot(unittest.TestCase):
    """임시 argus/ 루트 + 엔진 스테이지 정리. 엔진 기본 루트(ARGUS)도 임시로 돌려 실수로라도 배포 파일에 못 쓰게 한다."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="hdr_u2_")
        os.makedirs(os.path.join(self.root, "kce", "tools", "assets"))
        self._argus = mock.patch.object(hdrmap, "ARGUS", self.root)
        self._argus.start()
        hdrmap.discard("kce")

    def tearDown(self):
        hdrmap.discard("kce")
        self._argus.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def raw_dir(self, co):
        d = os.path.join(self.root, "raw_" + co)
        os.makedirs(d, exist_ok=True)
        for suf, fn in RAW[co].items():
            shutil.copyfile(os.path.join(FIX, fn), os.path.join(d, "%s_%s.html" % (co, suf)))
        return d

    def rep(self, co):
        return KB.update_quarter(co, Q, self.raw_dir(co), apply=False, hdr_root=self.root)


class TestMatchUpstream2026Q2(_TmpRoot):
    """동부·금호·계룡(설계 F U2 수용 기준) + 현대건설(법인 분할 4표): cols·tag·ent·n 이 상류 D 2026Q2 와 같다."""

    D = None

    @classmethod
    def setUpClass(cls):
        cls.D = _upstream()

    def _match(self, co, sec, ours, up):
        self.assertEqual(len(ours), len(up), "%s %s 표 수" % (co, sec))
        for i, (o, u) in enumerate(zip(ours, up)):
            where = "%s %s #%d" % (co, sec, i + 1)
            self.assertEqual(o["cols"], u["cols"], where)
            self.assertEqual(o["tag"], u["tag"], where)
            self.assertEqual(o["n"], u["n"], where)          # 머리행 포함 원행수
            if sec == "ii4":
                self.assertEqual(o["ent"], u["ent"], where)

    def test_dbe_match_D_2026Q2(self):
        rep = self.rep("dbe")
        up = self.D["dbe"]["sections"]
        # 상류 II-4 #1 은 본문(ii4) 절 '라-1.' 표(9행, 비채택) — 픽스처는 XII 상세표(ii4x)만 수집해 없다.
        self._match("dbe", "ii4", rep["headers"]["ii4"], up["ii4"][Q][1:])
        self.assertTrue(up["ii4"][Q][0]["lead"].startswith("라-1."))
        self._match("dbe", "p8", rep["headers"]["p8"], up["p8"][Q])
        self.assertEqual([h["n_rec"] for h in rep["headers"]["ii4"]], [102, 65])     # 레코드 수는 따로
        # pick 은 상류의 회사별 설정이라 재현 대상이 아니다 — 동부엔지니어링 표를 상류는 버리고 우리는 읽는다
        self.assertEqual([h["pick"] for h in rep["headers"]["ii4"]], [True, True])
        self.assertEqual([u["pick"] for u in up["ii4"][Q][1:]], [True, False])

    def test_khe_match_D_2026Q2(self):
        rep = self.rep("khe")
        up = self.D["khe"]["sections"]
        self._match("khe", "ii4", rep["headers"]["ii4"], up["ii4"][Q])
        self._match("khe", "p8", rep["headers"]["p8"], up["p8"][Q])
        # 지도 열 이름은 상류식('(단위: 백만원) 구분'), 파서가 사전에 물은 열(ncols)은 그대로
        self.assertEqual(rep["headers"]["p8"][0]["ncols"][0], "구분")
        self.assertIn("amt", rep["headers"]["p8"][0]["fields"])                 # xi_amt → amt 승격 흔적

    def test_kre_match_D_2026Q2(self):
        rep = self.rep("kre")
        up = self.D["kre"]["sections"]
        self._match("kre", "ii4", rep["headers"]["ii4"], up["ii4"][Q])
        self._match("kre", "p8", rep["headers"]["p8"], up["p8"][Q])
        # 종속회사(케이알산업, 늘 비집계) 표의 ent 는 대표 법인 — _apply_ii4 의 귀속과 같다
        self.assertIn("케이알산업", rep["headers"]["ii4"][1]["lead"])
        self.assertEqual(rep["headers"]["ii4"][1]["ent"], "계룡건설")

    def test_hec_entity_split_tags(self):
        rep = self.rep("hec")
        up = self.D["hec"]["sections"]
        self._match("hec", "ii4", rep["headers"]["ii4"], up["ii4"][Q])
        self._match("hec", "p8", rep["headers"]["p8"], up["p8"][Q])

    def test_sct_dup_section_order(self):
        """본문(ii4)·상세표(ii4x) 둘 다 있을 때: 원문 순서(본문 먼저), 행수 작은 절의 표는 dup_section·pick False."""
        rep = self.rep("sct")
        h = rep["headers"]["ii4"]
        self.assertEqual(rep["ii4_source"], "ii4x")
        self.assertEqual([(x["sec"], x["pick"], x["reason"]) for x in h],
                         [("ii4", False, "dup_section"), ("ii4", False, "dup_section"), ("ii4x", True, "picked")])
        up = self.D["sct"]["sections"]["ii4"][Q]
        # 상류: [본문 요약표(비채택, 5행), 상세표(85행)] — 우리 쪽 본문 바이오 표는 상류 2023Q1~ 지도에 없다(UPDATE §7-A)
        self.assertEqual((h[0]["cols"], h[0]["n"], h[0]["pick"]), (up[0]["cols"], up[0]["n"], up[0]["pick"]))
        self.assertEqual((h[2]["cols"], h[2]["n"]), (up[1]["cols"], up[1]["n"]))


class TestP8FinalBasis(_TmpRoot):

    def test_p8_basis_after_apply(self):
        """지도의 III-8 tag 는 _apply_p8 **뒤**의 최종 연결/별도다. 동부 셋째 표(동부엔지니어링)는 lead 로 구분을
        못 읽어 파서 단계에서는 None — 예전처럼 apply 전에 적으면 ''(구분 없음)로 영구 기록됐다."""
        pp = P.parse_p8(_read("dbe_p8_2026Q2.html"))
        self.assertEqual([t["basis"] for t in pp["tables"]], ["별도", "연결", None])
        rep = self.rep("dbe")
        self.assertEqual([h["tag"] for h in rep["headers"]["p8"]], ["별도", "연결", "연결"])
        self.assertEqual([h["basis"] for h in rep["headers"]["p8"]], ["별도", "연결", "연결"])

    def test_third_table_keeps_upstream_data(self):
        """셋째 표 연속성 판정은 원본 DATA 를 그대로 재현한다(예전 '별도' 기본값은 별도 6칸을 새로 만들었다)."""
        orig = extract_data(os.path.join(KCE, "dbe", "index.html"))
        D = copy.deepcopy(orig)
        k = D["fq"].index(Q)
        rep = {"events": 0, "p8_cells": 0, "fcst_cells": 0, "agg_rows": [], "created": [],
               "disappeared": [], "p8_unmatched": []}
        KB._apply_ii4(D, P.parse_ii4(_read("dbe_ii4x_2026Q2.html")), k, Q, rep)
        KB._apply_p8(D, P.parse_p8(_read("dbe_p8_2026Q2.html")), k, rep)
        bad = [(so["id"], b) for so, sn in zip(orig["sites"], D["sites"]) for b in ("별도", "연결")
               if ((so.get("p8") or {}).get(b) or {"tot": [None] * (k + 1)})["tot"][k]
               != ((sn.get("p8") or {}).get(b) or {"tot": [None] * (k + 1)})["tot"][k]]
        self.assertEqual(bad, [])

    def test_swap_by_continuity_is_recorded(self):
        """연속성 점수가 lead 의 배정을 뒤집으면 지도도 뒤집힌 값을 적는다(apply 전 basis 가 아니라)."""
        def site(nm, basis):
            b = {f: [None, None] for f in ("tot", "pr", "ub", "ubimp", "rc", "allw", "dl")}
            b["tot"][0] = 100
            return {"nm": nm, "p8": {basis: b}, "s": {"amt": [100, None]}, "has": [1, 0]}
        D = {"fqF": ["2026Q1", "2026Q2"], "sites": [site("가현장", "별도"), site("나현장", "연결")]}
        recs = lambda nm: [{"nm": nm, "amt": 100, "pr": 50.0, "ub": 1, "rc": 1}]   # noqa: E731
        pp = {"tables": [{"idx": 0, "basis": "연결", "rows": recs("가현장"), "cols": ["공사명"], "ncols": ["공사명"],
                          "fields": ["nm"], "lead": "", "n_raw": 2, "n_rec": 1},
                         {"idx": 1, "basis": "별도", "rows": recs("나현장"), "cols": ["공사명"], "ncols": ["공사명"],
                          "fields": ["nm"], "lead": "", "n_raw": 2, "n_rec": 1}], "rejected": []}
        KB._apply_p8(D, pp, 1, {"p8_unmatched": [], "p8_cells": 0})
        self.assertEqual([h["tag"] for h in KB._p8_headers(pp)], ["별도", "연결"])


class TestRejected(_TmpRoot):
    GOOD = ("<table><tr><th>공사명</th><th>발주처</th><th>기본도급액</th><th>완성공사액</th><th>계약잔액</th></tr>"
            "<tr><td>가현장</td><td>갑</td><td>100</td><td>40</td><td>60</td></tr>"
            "<tr><td>나현장</td><td>을</td><td>200</td><td>50</td><td>150</td></tr></table>")
    # 핵심 필드 셋(nm·amt·cmp)이 걸렸지만 잔액 열이 없고 행이 2줄 — 근접 미지(행≥3)에도 못 미친다
    NO_CORE = ("<p>(2) 종속회사</p><table><tr><th>공사명</th><th>기본도급액</th><th>완성공사액</th><th>비고</th></tr>"
               "<tr><td>다현장</td><td>300</td><td>100</td><td></td></tr>"
               "<tr><td>라현장</td><td>50</td><td>10</td><td></td></tr></table>")
    NOISE = ("<p>(1) 판매조직</p><table><tr><th>구분</th><th>판매조직</th></tr>"
             "<tr><td>건축</td><td>건축사업본부</td></tr><tr><td>토목</td><td>토목사업본부</td></tr></table>")

    def test_rejected_pick_false(self):
        r = P.parse_ii4(self.NOISE + self.GOOD + self.NO_CORE)
        self.assertEqual(r["unknown_headers"], [])
        self.assertEqual([(x["idx"], x["reason"]) for x in r["rejected"]], [(2, "no_core")])   # 판매조직 표는 후보 아님
        D = extract_data(os.path.join(KCE, "dbe", "index.html"))
        h = KB._ii4_headers(D, D["fq"].index(Q), [(2, "ii4", r)], "ii4")
        self.assertEqual([(x["pick"], x["reason"]) for x in h], [(True, "picked"), (False, "no_core")])
        self.assertIsNone(h[1]["n_rec"])
        # 지도 엔진에 그대로 기록돼 pick False 로 남는다
        hdrmap.record_kce("dbe", "2026Q3", {"ii4": h}, root=self.root, strict=True)
        st = hdrmap.staged("kce", "dbe")["roles"]["orders"]["2026Q3"]
        self.assertEqual([(e["pick"], e["reason"]) for e in st], [(True, "picked"), (False, "no_core")])

    def test_near_miss_is_unknown_and_rejected(self):
        nm3 = self.NO_CORE.replace("</table>", "<tr><td>마현장</td><td>70</td><td>7</td><td></td></tr></table>")
        r = P.parse_ii4(self.GOOD + nm3)
        self.assertEqual(len(r["unknown_headers"]), 1)                  # 종전 계약(fail-closed 대상) 그대로
        self.assertEqual(set(r["unknown_headers"][0]), {"cols", "n"})
        self.assertEqual([x["reason"] for x in r["rejected"]], ["near_miss"])
        self.assertEqual(len(r["rejected"][0]["rows"]), 3)              # A/B 판정 재료(지도에는 저장 안 됨)

    def test_p8_meta_table_rejected_with_empty_tag(self):
        """금호형 메타표(진행률·계약금액만, 미청구·미수금 문구 없음)는 통과(meta_p8)하되 지도에는 pick False·tag ''."""
        meta = ("<table><tr><td>구분</td><td>공사명</td><td>발주처</td><td>진행률</td><td>계약금액</td>"
                "<td>계약일</td><td>공사기한</td></tr>"
                + "".join("<tr><td>건축</td><td>%s</td><td>갑</td><td>50.0</td><td>100</td><td>2024.01.01</td>"
                          "<td>2027.01.01</td></tr>" % n for n in ("가", "나", "다")) + "</table>")
        amount = ("<p>(1) 연결 기준</p><table><tr><td>공사명</td><td>진행률</td><td>기본도급액</td><td>미청구공사 총액</td>"
                  "<td>공사미수금 총액</td></tr><tr><td>가</td><td>50.0</td><td>100</td><td>3</td><td>4</td></tr></table>")
        pp = P.parse_p8(meta + amount)
        self.assertEqual(pp["unknown_headers"], [])
        self.assertEqual([x["reason"] for x in pp["rejected"]], ["meta_p8"])
        h = KB._p8_headers(pp)
        self.assertEqual([(x["pick"], x["tag"], x["reason"]) for x in h],
                         [(False, "", "meta_p8"), (True, "연결", "picked")])


class TestSectorOf(unittest.TestCase):

    def test_sector_of_126_127(self):
        """상류 D 의 관급/민간/국내/해외 tag 127표(gse 89 + ipark 38)를 lead 만으로 재현 — 설계 목표 126, 실측 127."""
        D = _upstream()
        n = ok = 0
        for co in ("gse", "ipark"):
            for items in D[co]["sections"]["ii4"].values():
                for it in items:
                    n += 1
                    ok += (P.sector_of(it["lead"]) or P.region_of(it["lead"], None)) == it["tag"]
        self.assertEqual(n, 127)
        self.assertGreaterEqual(ok, 126)

    def test_marker_forms(self):
        self.assertEqual(P.sector_of("라. 수주현황 1) 지에스건설 [관급공사] (단위 : 백만원)"), "관급")
        self.assertEqual(P.sector_of("[BTO/BTL] 사전입찰 … 라. 수주현황 [국내공사] (단위 : 백만원)"), "국내")
        self.assertEqual(P.sector_of("(1) [공공부문] (단위 : 백만원)"), "관급")
        self.assertEqual(P.sector_of("[민간 부문]"), "민간")
        self.assertEqual(P.sector_of("4. 수주상황_민간공사(상세) ☞ 본문 위치로 이동 (단위 : 백만원)"), "민간")
        self.assertIsNone(P.sector_of("다. 수주상황 1) 현대건설 (단위 : 백만원)"))
        self.assertIsNone(P.sector_of(None))

    def test_ent_tag_reproduction_over_D(self):
        """17사 ii4 636표 전수: ent 621·tag 635 이상(불일치는 2025Q1 이전 이력 — UPDATE §7-A)."""
        D = _upstream()
        n = ok_e = ok_t = 0
        for co, d in D.items():
            data = extract_data(os.path.join(KCE, co, "index.html"))
            ents = data["summary"]["ents"]
            labels = sorted({it["ent"] for its in d["sections"]["ii4"].values() for it in its} - set(ents))
            by_ent = KB._tag_by_ent(data)
            for q, items in d["sections"]["ii4"].items():
                k = data["fq"].index(q)
                for it in items:
                    n += 1
                    ent = KB._hdr_ent(it["lead"], data, k, labels)
                    ok_e += ent == it["ent"]
                    ok_t += KB._hdr_tag(it["lead"], ent, by_ent) == it["tag"]
        self.assertEqual(n, 636)
        self.assertGreaterEqual(ok_e, 621)
        self.assertGreaterEqual(ok_t, 635)


class TestRender(_TmpRoot):
    """kce_render.render_headers_html = hdrmap 어댑터 — 스테이지+렌더(디스크 무변화), 커밋은 호출측."""

    def setUp(self):
        super().setUp()
        self.page = os.path.join(self.root, "kce", "headers.html")
        shutil.copyfile(HEADERS_FX, self.page)                 # 배포 파일이 아니라 임시 사본에 그린다
        with open(self.page, encoding="utf-8") as f:
            self.before = f.read()

    def _D(self, text):
        return hdrmap._parse_page(text)

    def test_render_stages_then_commit(self):
        rep = self.rep("dbe")
        text = kce_render.render_headers_html(self.page, "dbe", "2026Q3", rep["headers"], root=self.root)
        D, LAB, ORDER, _s, _e = self._D(text)
        D0, _l, ORDER0, _s0, _e0 = self._D(self.before)
        got = D["dbe"]["sections"]["ii4"]["2026Q3"]
        self.assertEqual([(x["tag"], x["ent"], x["cols"], x["n"], x["pick"]) for x in got],
                         [(h["tag"], h["ent"], h["cols"], h["n"], h["pick"]) for h in rep["headers"]["ii4"]])
        self.assertEqual([x["tag"] for x in D["dbe"]["sections"]["p8"]["2026Q3"]], ["별도", "연결", "연결"])
        self.assertIn("2026Q3", D["dbe"]["fq"])
        for co in D0:                                           # 다른 16사는 그대로
            if co != "dbe":
                self.assertEqual(D[co], D0[co], co)
        self.assertEqual(ORDER, ORDER0)
        # 렌더는 디스크를 건드리지 않는다 — 페이지·지도 모두
        with open(self.page, encoding="utf-8") as f:
            self.assertEqual(f.read(), self.before)
        self.assertFalse(os.path.exists(hdrmap.map_path("kce", self.root)))
        hdrmap.commit_kce("dbe", root=self.root)
        M = hdrmap.load_map("kce", self.root)
        self.assertEqual(M["companies"]["dbe"]["fq"], ["2026Q3"])
        # 커밋본으로 다시 그려도 같은 바이트(스테이지 우선 = 커밋본)
        self.assertEqual(hdrmap.render_headers("kce", out_html=self.page, root=self.root, write=False,
                                               strict=True, keys=set(D0)), text)

    def test_discard_leaves_map_untouched(self):
        rep = self.rep("khe")
        kce_render.render_headers_html(self.page, "khe", "2026Q3", rep["headers"], root=self.root)
        hdrmap.discard("kce", "khe")
        self.assertIsNone(hdrmap.staged("kce", "khe"))
        self.assertFalse(os.path.exists(hdrmap.map_path("kce", self.root)))

    def test_lite_keys_do_not_leak_into_precise_page(self):
        """kce 지도에는 lite 종목(종목코드 키)도 있다 — 정밀 갱신 렌더에 새어 들어가면 안 된다."""
        hdrmap.record("kce", "001260", "2026Q3", "orders", [{"cols": ["공사명"], "n": 3}], [0],
                      meta={"name": "남광토건", "stock": "001260"}, root=self.root, strict=True)
        hdrmap.write("kce", root=self.root, strict=True)
        rep = self.rep("kre")
        text = kce_render.render_headers_html(self.page, "kre", "2026Q3", rep["headers"], root=self.root)
        D, _l, ORDER, _s, _e = self._D(text)
        self.assertNotIn("001260", D)
        self.assertNotIn("001260", ORDER)

    def test_new_precise_company_is_added(self):
        """신규 정밀사(D 에 없는 co) — 종전 구현은 ValueError 로 그 회사 갱신 전체를 멈췄다. 이제 D·ORDER 끝에 추가."""
        D0, LAB0, ORDER0, s, e = self._D(self.before)
        del D0["xca"]
        ORDER1 = [k for k in ORDER0 if k != "xca"]
        page = (self.before[:s] + json.dumps(D0, ensure_ascii=False) + ", LAB=" + json.dumps(LAB0, ensure_ascii=False)
                + ", ORDER=" + json.dumps(ORDER1, ensure_ascii=False) + self.before[e:])
        with open(self.page, "w", encoding="utf-8") as f:
            f.write(page)
        text = kce_render.render_headers_html(self.page, "xca", "2026Q3",
                                              {"ii4": [{"cols": ["품목", "수주총액"], "n": 4, "ent": "자이씨앤에이",
                                                        "tag": "", "pick": True}], "p8": []}, root=self.root)
        D, _l, ORDER, _s, _e = self._D(text)
        self.assertEqual(ORDER[-1], "xca")
        self.assertEqual(D["xca"]["name"], "자이씨앤에이")
        self.assertEqual(D["xca"]["sections"]["ii4"]["2026Q3"][0]["cols"], ["품목", "수주총액"])


class TestApplyContract(_TmpRoot):
    """--apply 의 네 파일 쓰기와 지도 커밋 순서 — 렌더는 스테이지, 커밋은 네 파일 성공 뒤, 실패면 discard."""

    def setUp(self):
        super().setUp()
        self.kce = os.path.join(self.root, "kce")
        os.makedirs(os.path.join(self.kce, "dbe"))
        for fn in ("index.html", "matrix.html", "trace.html"):
            shutil.copyfile(os.path.join(KCE, "dbe", fn), os.path.join(self.kce, "dbe", fn))
        shutil.copyfile(HEADERS_FX, os.path.join(self.kce, "headers.html"))
        self._kce = mock.patch.object(KB, "KCE", self.kce)
        self._kce.start()

    def tearDown(self):
        self._kce.stop()
        super().tearDown()

    def test_commit_after_four_files(self):
        rep = KB.update_quarter("dbe", Q, self.raw_dir("dbe"), apply=True, hdr_root=self.root)
        self.assertTrue(rep["applied"])
        M = hdrmap.load_map("kce", self.root)
        self.assertEqual([e["n"] for e in M["companies"]["dbe"]["roles"]["orders"][Q]], [103, 66])
        with open(os.path.join(self.kce, "headers.html"), encoding="utf-8") as f:
            D = hdrmap._parse_page(f.read())[0]
        self.assertEqual([x["tag"] for x in D["dbe"]["sections"]["p8"][Q]], ["별도", "연결", "연결"])
        self.assertIsNone(hdrmap.staged("kce", "dbe"))

    def test_failed_write_discards_stage(self):
        with mock.patch.object(kce_render, "render_trace_html", side_effect=RuntimeError("렌더 실패 주입")):
            with self.assertRaises(RuntimeError):
                KB.update_quarter("dbe", Q, self.raw_dir("dbe"), apply=True, hdr_root=self.root)
        self.assertIsNone(hdrmap.staged("kce", "dbe"))
        self.assertFalse(os.path.exists(hdrmap.map_path("kce", self.root)))


class TestUnknownQueue(_TmpRoot):
    NEAR = ("<p>4. 수주현황(상세) (단위 : 백만원)</p><table><tr><th>공사명</th><th>발주처</th><th>기본도급액</th>"
            "<th>완성공사액</th><th>남은금액</th></tr>"
            + "".join("<tr><td>%s현장</td><td>갑</td><td>100</td><td>40</td><td>60</td></tr>" % n
                      for n in ("가", "나", "다")) + "</table>")

    def _raw(self, name, html):
        d = os.path.join(self.root, "raw_unk")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            f.write(html)
        return d

    def test_unknown_enqueued_then_raises(self):
        d = self._raw("dbe_ii4x.html", self.NEAR)
        with self.assertRaises(hdrmap.UnknownHeaderError) as cm:
            KB.update_quarter("dbe", Q, d, apply=False, hdr_root=self.root)
        self.assertIsInstance(cm.exception, RuntimeError)                    # 종전 except RuntimeError 그대로 잡힌다
        items = hdrmap.load_queue("kce", self.root)
        self.assertEqual([(i["kind"], i["key"], i["role"], i["status"], i["quarter_first"]) for i in items],
                         [("unknown", "dbe", "orders", "open", Q)])
        self.assertEqual(items[0]["cols_raw"], ["공사명", "발주처", "기본도급액", "완성공사액", "남은금액"])
        self.assertEqual(items[0]["need_missing"], ["bal"])
        self.assertIsNone(hdrmap.staged("kce", "dbe"))                        # 그 분기는 지도에 남지 않는다
        self.assertFalse(os.path.exists(hdrmap.map_path("kce", self.root)))

    def test_p8_unknown_role_progress(self):
        d = self.raw_dir("dbe")
        with open(os.path.join(d, "dbe_p8.html"), "w", encoding="utf-8") as f:
            f.write("<table><tr><th>공사명</th><th>기본도급액</th><th>미청구공사 총액</th><th>잔여</th></tr>"
                    + "<tr><td>가</td><td>100</td><td>3</td><td>9</td></tr>" * 3 + "</table>")
        with self.assertRaises(hdrmap.UnknownHeaderError):
            KB.update_quarter("dbe", Q, d, apply=False, hdr_root=self.root)
        self.assertEqual([i["role"] for i in hdrmap.load_queue("kce", self.root)], ["progress"])

    def test_dry_run_writes_no_queue(self):
        """dry-run(apply 없음·루트 미지정)은 파일을 건드리지 않는다 — 대기열도. 예외는 그대로."""
        d = self._raw("dbe_ii4x.html", self.NEAR)
        with self.assertRaises(hdrmap.UnknownHeaderError):
            KB.update_quarter("dbe", Q, d, apply=False)
        self.assertFalse(os.path.exists(hdrmap.queue_path("kce", self.root)))

    def test_watch_classifies_headers_stage(self):
        import kce_watch
        with mock.patch.object(kce_watch, "is_published", return_value=(True, "r1", "반기보고서", "web")), \
                mock.patch.object(kce_watch, "fetch_quarter"), \
                mock.patch.object(kce_watch.kce_build, "update_quarter",
                                  side_effect=hdrmap.UnknownHeaderError("미지 헤더")):
            out = kce_watch.run(["dbe"], apply=True, quarter="2026Q3", raw_dir=self.root)
        self.assertEqual(out["failed"][0]["stage"], "headers")
        self.assertTrue(out["failed"][0]["queue"].endswith("hdr_queue.json"))

    def test_probe_unknown_goes_to_queue(self):
        r = P.parse_ii4(self.NEAR)
        row = {"slug": "001260", "stock": "001260", "name": "남광토건", "quarter": Q,
               "_unk": kce_probe._unknown_items(r, "orders", "20260814000001")}
        self.assertEqual(kce_probe.enqueue_unknown([row], root=self.root), 1)
        self.assertNotIn("_unk", row)                                         # 산출 JSON 에는 안 남는다
        it = hdrmap.load_queue("kce", self.root)[0]
        self.assertEqual((it["key"], it["stock"], it["rcpNo"], it["kind"]), ("001260", "001260", "20260814000001", "unknown"))

    def test_probe_records_accepted_header_and_keeps_ancillary_unknown_open(self):
        """채택 수주표 + 보조 near-miss가 함께 있어도 현 분기 pick은 살아 회귀가 아니다."""
        parsed = P.parse_ii4(_read("kre_ii4_2026Q2.html"))
        tables = kce_probe._accepted_header_tables(parsed, "20260814000001")
        meta = {"name": "이화공영", "stock": "001840"}
        hdrmap.record("kce", "001840", "2026Q1", "orders",
                      tables, range(len(tables)), meta=meta, root=self.root,
                      strict=True)
        hdrmap.write("kce", root=self.root, strict=True)

        near = P.parse_ii4(self.NEAR)
        row = {"slug": "001840", "stock": "001840", "name": "이화공영",
               "quarter": Q, "_hdr_tables": tables,
               "_unk": kce_probe._unknown_items(near, "orders", "20260814000001")}
        self.assertEqual(kce_probe.enqueue_unknown([row], root=self.root), 1)
        self.assertNotIn("_hdr_tables", row)
        self.assertNotIn("_unk", row)

        cur = hdrmap.load_map("kce", self.root)["companies"]["001840"]["roles"]["orders"][Q]
        self.assertTrue(any(e["pick"] for e in cur))
        queue = hdrmap.load_queue("kce", self.root)
        self.assertEqual([(i["kind"], i["status"]) for i in queue], [("unknown", "open")])
        rep = hdrmap.check("kce", root=self.root)
        self.assertEqual((rep["exit"], rep["regressions"]), (0, []))

    def test_probe_does_not_duplicate_precise_stock_under_numeric_key(self):
        parsed = P.parse_ii4(_read("kre_ii4_2026Q2.html"))
        row = {"slug": "hec", "stock": "000720", "name": "현대건설",
               "quarter": Q,
               "_hdr_tables": kce_probe._accepted_header_tables(
                   parsed, "20260814000001")}
        self.assertEqual(kce_probe.enqueue_unknown([row], root=self.root), 0)
        self.assertNotIn("_hdr_tables", row)
        self.assertFalse(os.path.exists(hdrmap.map_path("kce", self.root)))
        self.assertIsNone(hdrmap.staged("kce", "000720"))


class TestSeriesCache(_TmpRoot):

    def setUp(self):
        super().setUp()
        self._old, KS.CACHE = KS.CACHE, os.path.join(self.root, "series_cache")
        html = _read("kre_ii4_2026Q2.html")
        self.net = [mock.patch.object(KS, "search_reports", return_value=[("20260814000001", "반기보고서 (2026.06)")]),
                    mock.patch.object(KS, "pick_report", return_value=[("20260814000001", "반기보고서 (2026.06)")]),
                    mock.patch.object(KS, "toc", return_value=[{"text": "4. 매출 및 수주상황"}]),
                    mock.patch.object(KS, "find_sections", return_value={"ii4": {"text": "4. 매출 및 수주상황"}}),
                    mock.patch.object(KS, "fetch_section", return_value=html)]
        for m in self.net:
            m.start()

    def tearDown(self):
        for m in self.net:
            m.stop()
        KS.CACHE = self._old
        super().tearDown()

    def test_series_cache_cols(self):
        out = KS.collect_one("999999", Q)
        with open(KS.cache_path("999999", Q), encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d, out)
        self.assertEqual([t["n_raw"] for t in d["tables"]], [137, 44])
        self.assertEqual(d["tables"][0]["cols"][0], "현장명 - 건축")             # 지도식 열 이름
        self.assertEqual(d["unknown_headers"], [])
        self.assertEqual([len(t["rows"]) for t in d["tables"]], [133, 39])     # build() 가 읽는 rows 는 그대로

    def test_collect_stages_fresh_only_and_commits(self):
        rec = {"stock": "999999", "slug": "999999", "name": "테스트건설"}
        old = {"stock": "999999", "quarter": "2026Q1", "ok": True, "note": "", "rcpNo": "x", "grain": "project",
               "tables": [{"lead": "", "rows": [{"nm": "가", "amt": 1, "cmp": 0, "bal": 1}]}],
               "rows": [{"nm": "가", "amt": 1, "cmp": 0, "bal": 1}]}
        os.makedirs(os.path.dirname(KS.cache_path("999999", "2026Q1")))
        with open(KS.cache_path("999999", "2026Q1"), "w", encoding="utf-8") as f:
            json.dump(old, f)                                               # 전진 저장 이전 캐시(cols 없음)
        KS.collect([rec], ["2026Q1", Q], log=io.StringIO(), sweeps=1)
        M = hdrmap.load_map("kce", self.root)
        co = M["companies"]["999999"]
        self.assertEqual(sorted(co["roles"]["orders"]), [Q])                 # 소급 없음 — 새로 받은 칸만
        self.assertEqual([e["n"] for e in co["roles"]["orders"][Q]], [137, 44])
        self.assertEqual(co["stock"], "999999")

    def test_precise_stock_not_staged(self):
        out = KS.collect_one("000720", Q)                                     # 현대건설 = 정밀 17사
        self.assertIsNone(KS.stage_headers({"stock": "000720", "slug": "hec"}, Q, out, root=self.root))
        self.assertIsNone(hdrmap.staged("kce", "000720"))


class TestOnboard(_TmpRoot):

    def setUp(self):
        super().setUp()
        self.uni = os.path.join(self.root, "universe.json")
        self._u = mock.patch.object(U, "UNIVERSE", self.uni)
        self._u.start()
        self._old, KS.CACHE = KS.CACHE, os.path.join(self.root, "series_cache")

    def tearDown(self):
        KS.CACHE = self._old
        self._u.stop()
        super().tearDown()

    def _fetch(self, recs):
        with mock.patch("kce_fetch._get", return_value=b""), mock.patch.object(U, "parse_kind", return_value=[]), \
                mock.patch.object(U, "select", return_value=recs), mock.patch("sys.stderr", io.StringIO()):
            return U.fetch(write=True)

    @staticmethod
    def _rec(stock, name):
        return {"stock": stock, "name": name, "market": "코스닥", "industry": "건물 건설업", "product": "",
                "listed": "", "slug": stock, "source": "업종"}

    def test_onboard_queue(self):
        a, b, c = self._rec("100001", "가건설"), self._rec("100002", "나건설"), self._rec("100003", "다게임")
        self._fetch([a])                                                     # 첫 생성 — 전원 신규로 올리지 않는다
        self.assertEqual(hdrmap.load_queue("kce", self.root), [])
        self._fetch([a, b, c])
        q = hdrmap.load_queue("kce", self.root)
        self.assertEqual(sorted((i["kind"], i["key"], i["status"]) for i in q),
                         [("new_company", "100002", "open"), ("new_company", "100003", "open")])
        self._fetch([a, b, c])                                               # 멱등
        self.assertEqual(len(hdrmap.load_queue("kce", self.root)), 2)
        # 온보딩: 나건설은 lite 캐시(cols 있음)를 재생해 지도에, 다게임은 수주 절 없음(none)이라 닫는다
        p = KS.cache_path("100002", Q)
        os.makedirs(os.path.dirname(p))
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"stock": "100002", "quarter": Q, "ok": True, "note": "", "rcpNo": "r", "grain": "project",
                       "tables": [{"lead": "[민간공사] (단위 : 백만원)", "cols": ["공사명", "기본도급액"], "n_raw": 3,
                                   "rows": [{"nm": "가"}, {"nm": "나"}]}], "rows": []}, f)
        res = HO.onboard_kce(root=self.root, probe={"100002": {"tier": "site"}, "100003": {"tier": "none"}},
                             quarters=[Q, "2026Q1"])
        self.assertEqual((res["recorded"], res["closed_none"]), (["100002"], ["100003"]))
        e = hdrmap.load_map("kce", self.root)["companies"]["100002"]["roles"]["orders"][Q][0]
        self.assertEqual((e["n"], e["n_rec"], e["tag"], e["pick"]), (3, 2, "민간", True))
        self.assertEqual(hdrmap.open_items("kce", self.root, kind="new_company"), [])
        # lite 지도 페이지는 템플릿에서 새로 — 정밀 headers.html 은 건드리지 않는다
        text = HO.render_lite(root=self.root)
        D, _l, ORDER, _s, _e = hdrmap._parse_page(text)
        self.assertEqual(ORDER, ["100002"])
        self.assertFalse(os.path.exists(os.path.join(self.root, "kce", "headers.html")))

    def test_summary_line(self):
        before = os.path.join(self.root, "before")
        HO.snapshot(before, self.root)
        hdrmap.onboard("kce", {"100001"}, [self._rec("100001", "가"), self._rec("100002", "나")], q=Q, root=self.root)
        hdrmap.record("kce", "100002", Q, "orders", [{"cols": ["공사명"], "n": 2}], [0], root=self.root)
        hdrmap.write("kce", root=self.root)
        s = HO.summary(before, self.root)
        self.assertEqual(s["line"], "신규 편입 1(100002) · 머리행 +1표 · 미지 열 open 0(회귀 0)")
        gh = os.path.join(self.root, "gh_out")
        with mock.patch("sys.stdout", io.StringIO()) as out:
            self.assertEqual(HO.main(["--summary", "--before", before, "--root", self.root, "--github-output", gh]), 0)
        self.assertEqual(out.getvalue(), s["line"] + "\n")
        with open(gh, encoding="utf-8") as f:
            self.assertIn("hdr_regressions=0\n", f.read())


class TestPrerequisites(unittest.TestCase):
    """U3(XI-1)의 전제 — parse_tables 인자화(기본 동작 불변)·rowspan 출처·kce_build 의 xi1 훅."""

    def test_fixtures14_unchanged(self):
        """U2 이전 파서(HEAD c747452d)와 같은 결과 — 15개 원문 픽스처의 parse_ii4·parse_p8 종전 키 전부(n·lead·cols·
        레코드·basis·미지 헤더). 다이제스트는 변경 전 파서로 만든 값이다. 손 사전만으로 잰다 — 자동 사전
        (KCE_ALIAS_AUTO, update-kce.yml)이 더한 키는 걷어낸다(그쪽 영향은 다른 계약 테스트가 잡는다)."""
        import kce_lib
        golden = {
            "dbe_ii4x_2026Q2.html": "4fe5b13ea0d436fc", "dbe_p8_2026Q2.html": "242164468b4fd9b6",
            "hanshin_progress_2026Q2.html": "56c38a19ee8c8f0a", "hec_기타재무_진행률수주.html": "40a2b41e5ca5a0fc",
            "hec_단일판매공급계약.html": "c8e736a6003f79ea", "hec_수주상황.html": "da9927b40e1f5c16",
            "khe_ii4x_2026Q2.html": "c25380454d0a4d75", "khe_p8_2026Q2.html": "142e163b88c2758d",
            "kre_ii4_2026Q2.html": "3d2b52777663c3f5", "kre_p8_2026Q2.html": "c3ab6344b13479b6",
            "sangji_progress_2026Q2.html": "5d6f7abc345015a7", "sct_기타재무_진행률수주.html": "30a62d5c0c620afc",
            "sct_상세표_건설수주.html": "5fd9586feea02b64", "sct_수주상황.html": "edb84c0463ff6030",
            "taeyoung_progress_2026Q2.html": "98f32c57162e3c31",
        }
        auto = set(kce_lib.AUTO_ALIAS_KEYS)
        got = {}
        with mock.patch.dict(kce_lib.COL_ALIAS), mock.patch.object(P, "_HDR_VOCAB", P._HDR_VOCAB - auto):
            for k in auto:
                kce_lib.COL_ALIAS.pop(k, None)
            for fn in golden:
                h = _read(fn)
                a, b = P.parse_ii4(h), P.parse_p8(h)
                obj = {"ii4": [[t["n"], t["lead"], t["cols"], t["rows"]] for t in a["tables"]],
                       "ii4u": a["unknown_headers"],
                       "p8": [[t["n"], t["basis"], t["lead"], t["cols"], t["rows"]] for t in b["tables"]],
                       "p8u": b["unknown_headers"]}
                got[fn] = hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True)
                                         .encode("utf-8")).hexdigest()[:16]
                # 기본 인자 parse_tables 는 지도용 키(cols_up·rspan)를 싣지 않고, 상류식 평탄화는 cols 를 바꾸지 않는다
                plain, up = P.parse_tables(h), P.parse_tables(h, upstream_hdr=True)
                self.assertFalse(any("cols_up" in t or "rspan" in t for t in plain), fn)
                self.assertEqual([t["cols"] for t in plain], [t["cols"] for t in up], fn)
        self.assertEqual(got, golden)

    def test_n_raw_counts_header_rows(self):
        t = [x for x in P.parse_tables(_read("hec_수주상황.html")) if x["rows"] and x["cols"]][1:5]
        self.assertEqual([x["n_raw"] for x in P.parse_ii4(_read("hec_수주상황.html"))["tables"]], [62, 43, 21, 4])
        self.assertTrue(all(x["n_raw"] == x["hdr_rows"] + len(x["rows"]) for x in t))

    def test_max_header_rows_and_vocab(self):
        html = ("<table><tr><td>신고일자</td><td>계약명</td><td>계약상대방</td></tr>"
                "<tr><td>최초</td><td>판매공급</td><td>대금수령</td></tr>"
                "<tr><td>당기</td><td>누적</td><td>당기</td></tr>"
                "<tr><td>2025.01.02</td><td>A공사</td><td>1,000</td></tr></table>")
        self.assertEqual(len(P.parse_tables(html)[0]["rows"]), 3)          # 기본: 어휘 머리행 최대 2줄
        vocab = P._HDR_VOCAB | {"계약명", "계약상대방", "최초", "판매공급", "대금수령"}
        t = P.parse_tables(html, max_header_rows=4, vocab=vocab)[0]
        self.assertEqual((t["hdr_rows"], len(t["rows"])), (3, 1))
        self.assertEqual(t["cols"][0], "신고일자 최초 당기")
        self.assertNotIn("최초", P._HDR_VOCAB)                               # 전역 어휘는 그대로

    def test_rowspan_provenance(self):
        html = ("<table><tr><th>계약명</th><th>구분</th><th>금액</th></tr>"
                "<tr><td rowspan='2'>A</td><td>당기</td><td>1</td></tr><tr><td>누적</td><td>2</td></tr></table>")
        t = P.parse_tables(html, keep_rowspan=True)[0]
        self.assertEqual(t["rows"], [["A", "당기", "1"], ["A", "누적", "2"]])
        self.assertEqual(t["rspan"], [[False, False, False], [True, False, False]])
        self.assertNotIn("rspan", P.parse_tables(html)[0])

    def test_xi1_hook(self):
        """kce_xi1 모듈이 있으면 III-8 다음에 apply(co, q, raw_dir, D, k, rep, hdr_root=, queue=) 를 부른다."""
        calls = []
        stub = types.SimpleNamespace(apply=lambda co, q, raw, D, k, rep, **kw: (
            calls.append((co, q, k, sorted(kw))), rep["headers"].setdefault("xinb", [])))
        tmp = tempfile.mkdtemp()
        try:
            for suf, fn in RAW["khe"].items():
                shutil.copyfile(os.path.join(FIX, fn), os.path.join(tmp, "khe_%s.html" % suf))
            with mock.patch.object(KB, "_xi1", stub):
                rep = KB.update_quarter("khe", Q, tmp, apply=False)
            self.assertEqual(calls, [("khe", Q, 18, ["hdr_root", "queue"])])
            self.assertEqual(rep["headers"]["xinb"], [])
            if not os.path.exists(os.path.join(TOOLS, "kce_xi1.py")):
                self.assertIsNone(KB._xi1)                                  # 모듈이 없으면 건너뛴다
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_merge_auto_alias(self):
        """자동 사전은 없는 키만 더한다(손 사전 우선), 경로가 없으면 no-op — KCE_ALIAS_AUTO 를 켠 실행만 영향."""
        import kce_lib
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "col_alias_auto.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"총도급액(VAT포함)": {"field": "amt", "provenance": {}}, "공사명": {"field": "cl"}}, f)
            with mock.patch.dict(kce_lib.COL_ALIAS), mock.patch.object(kce_lib, "AUTO_ALIAS_KEYS", []):
                self.assertEqual(kce_lib._merge_auto(None), 0)
                self.assertEqual(kce_lib._merge_auto(os.path.join(tmp, "없음.json")), 0)
                self.assertEqual(kce_lib._merge_auto(path), 1)
                self.assertEqual(kce_lib.COL_ALIAS["총도급액(VAT포함)"], "amt")
                self.assertEqual(kce_lib.COL_ALIAS["공사명"], "nm")              # 손 사전이 이긴다
                self.assertEqual(kce_lib.AUTO_ALIAS_KEYS, ["총도급액(VAT포함)"])
            self.assertNotIn("총도급액(VAT포함)", kce_lib.COL_ALIAS)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_coverage_unknown_column(self):
        recs = [{"stock": "100001", "slug": "100001", "name": "가건설", "market": "코스닥", "industry": "건물 건설업"}]
        probe = {"100001": {"tier": "agg", "note": "인식 0", "quarter": Q}}
        html = kce_page.coverage_html(recs, probe, {}, {"100001": 2})
        self.assertIn(">미지 열</th>", html)
        self.assertIn('<b class="wn">2</b>', html)
        self.assertIn("<td>—</td></tr>", kce_page.coverage_html(recs, probe, {}))


if __name__ == "__main__":
    unittest.main()
