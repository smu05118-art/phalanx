#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hdrmap(머리행 지도 엔진) 계약 테스트.

실측 근거(2026-10-12 맥미니):
  · fixtures/headers_2026Q2.html = 상류 headers.html 2026-09-10 스냅샷(452,824B, md5 e79a0b6f) 17사 × ii4/p8/xinb 표 1,302개
    → JS 구간(gseq) 132개, DL이앤씨 II-4 8구간. 라이브 argus/kce/headers.html 은 봇이 갱신하는 배포물이라 절대값 단언은
    전부 이 fixture 에서 읽고(tools/tests 는 _config.yml 로 배포 제외), 라이브 파일은 상대 단언만(test_live_headers_roundtrip_relative).
  · 현대건설 2026Q2 II-4 상류 n=[62,43,21,4](머리행 포함 원행수) vs fixture hec_수주상황.html 파서 레코드 [61,42,20,3].
  · KAI(047810) kdef 캐시 2025Q4→2026Q1→2026Q2 채택 cols 는 `기 초(2025.01.01) 금액`처럼 날짜만 바뀐다 — 마스킹 없이는 매 분기 「바뀜」.
  · 이화공영(001840) probe_2026Q2 미지 머리행 `구 분|매출처|계약명|도급금액|당기매출액|비율(%)|비고` — 매출처 표 오탐, 사람 확인(B).
  · 잠금 없는 큐: 8스레드 × 25건 enqueue → 28건(심사 실측). kce_fetch.parallel 레인(KCE_LANES 8)이 엔진이 붙는 자리다.
모든 파일 쓰기는 임시 root 로 간다(실제 argus/ 는 읽기만).
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
KCE = os.path.dirname(TOOLS)
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, TOOLS)

import hdrmap  # noqa: E402
import kce_parse  # noqa: E402
import kce_render  # noqa: E402
from kce_lib import COL_ALIAS, json_for_html, norm_col  # noqa: E402
from kce_parse import parse_ii4  # noqa: E402

HEADERS_HTML = os.path.join(FIX, "headers_2026Q2.html")       # 고정 스냅샷 — 절대값 단언은 여기서
LIVE_HEADERS = os.path.join(KCE, "headers.html")             # 배포물(봇 갱신) — 상대 단언만
TABS = ("kce", "kdef", "kaero")

# KAI 047810 — kdef reports_cache 2025Q4·2026Q1·2026Q2 orders.cols 그대로(openclose 모양, 기초/기말 날짜가 열 이름에 박힘).
KAI = {
    "2025Q4": ["구 분", "기 초(2025.01.01) 수량", "기 초(2025.01.01) 금액", "기 말(2025.12.31) 수량", "기 말(2025.12.31) 금액", "비 고"],
    "2026Q1": ["구 분", "기 초(2026.01.01) 수량", "기 초(2026.01.01) 금액", "기 말(2026.03.31) 수량", "기 말(2026.03.31) 금액", "비 고"],
    "2026Q2": ["구 분", "기 초(2026.01.01) 수량", "기 초(2026.01.01) 금액", "기 말(2026.06.30) 수량", "기 말(2026.06.30) 금액", "비 고"],
}
# 이화공영 001840 — assets/probe_2026Q2.json rows[].unknown_headers[0]
EWHA = ["구 분", "매출처", "계약명", "도급금액", "당기매출액", "비율(%)", "비고"]
# 표준 II-4 상세표 머리행(대우건설 2021Q4 꼴)
STD = ["공사명", "계약일 (공사착공일)", "완공예정일", "기본도급액", "완성공사액", "계약잔액"]
# 각주 벗김 대상(기본도급액 ※1) 7열 머리행과, 그 표의 레코드 한 줄(② 실측용)
STRIP = ["공사명", "발주처", "계약일", "완공예정일", "기본도급액 ※1", "완성공사액", "계약잔액"]
ROW7 = [["A현장", "서울시", "2025.01.01", "2026.12.31", "100", "50", "50"]]
II4_NEED = {"nm", "amt", "cmp", "bal"}


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _js_gseq(co, key, d, S):
    """headers.html JS L98-104 의 축자 이식 — 엔진 gseq 가 이 규칙과 같아야 지도 #번호가 상류 표 대장과 맞는다."""
    gseq = {}
    for q in d["fq"]:
        for r in S.get(q) or []:
            gk = ((r.get("ent") or "") + "|" + (r.get("tag") or "") + "|"
                  + "/".join(re.sub(r"\s+", "", c) for c in r["cols"] if c and c.strip()))
            if gk not in gseq:
                gseq[gk] = "%s-%s-%02d" % (co, key, len(gseq) + 1)
    return gseq


def _js_lines(lines, start, end="</script>"):
    """start 가 참인 줄 다음부터 end 줄 앞까지의 JS 중 빈 줄·주석 줄을 뺀 것(끝 공백 제거)."""
    out, on = [], False
    for l in lines:
        if not on:
            if start(l):
                on = True
            continue
        if l.strip() == end:
            break
        s = l.rstrip()
        if not s.strip() or s.strip().startswith("//"):
            continue
        out.append(s)
    return out


class _Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="hdrmap_test_")
        for t in TABS:
            hdrmap.discard(t)
        os.environ.pop("HDRMAP_STRICT", None)

    def tearDown(self):
        for t in TABS:
            hdrmap.discard(t)
        shutil.rmtree(self.root, ignore_errors=True)

    def rec(self, tab, key, q, role, tables, picks=(), **kw):
        kw.setdefault("root", self.root)
        kw.setdefault("strict", True)
        return hdrmap.record(tab, key, q, role, tables, picks, **kw)

    def kce_page(self, src=HEADERS_HTML):
        """headers.html 스냅샷(fixture)을 임시 root 에 복사해 돌려준다(원본은 읽기만)."""
        os.makedirs(os.path.join(self.root, "kce", "tools", "assets"), exist_ok=True)
        dst = os.path.join(self.root, "kce", "headers.html")
        shutil.copy(src, dst)
        return dst, _read(dst)


class TestKeys(_Base):

    def test_mask_catalog(self):
        self.assertEqual(hdrmap.mask("기 초(2025.01.01) 금액"), "기초#금액")
        self.assertEqual(hdrmap.mask("기 말(2026.06.30) 수량"), "기말#수량")
        self.assertEqual(hdrmap.mask("제27기 2분기"), "#2분기")
        self.assertEqual(hdrmap.mask("전기말 수주잔(2025.12.31)"), "#말수주잔#")
        self.assertEqual(hdrmap.mask("2024년 수주"), "#수주")
        self.assertEqual(hdrmap.mask("2025-06-30 기준"), "#기준")
        # 날짜가 아닌 숫자(열 번호·금액 단위)는 건드리지 않는다
        self.assertEqual(hdrmap.mask("수주총액(백만원)"), "수주총액(백만원)")
        self.assertEqual(hdrmap.mask_cols(["", " ", "공사명", None]), ["공사명"])
        # 당기/전기/전분기 는 날짜성 접미(말·초)가 붙은 꼴만 접는다 — 당기말·전기말·전분기말 은 같은 자리표
        self.assertEqual(hdrmap.mask("당기말"), hdrmap.mask("전기말"))
        self.assertEqual(hdrmap.mask("전분기말 잔고"), "#말잔고")
        self.assertEqual(hdrmap.mask("전기초 잔고"), "#초잔고")
        # 단독 당기≠전기 유지 — 자리바꿈(구분|당기|전기 → 구분|전기|당기)이 chg 0 이 되거나 '당기…' 채택이 '전기…' 미지를 닫지 않게
        self.assertNotEqual(hdrmap.mask("당기"), hdrmap.mask("전기"))
        self.assertNotEqual(hdrmap.mask("당기매출액"), hdrmap.mask("전기매출액"))
        self.assertEqual(hdrmap.mask("당기매출액"), "당기매출액")
        # 전력(kgrid) 어휘 — '전기판매액' 은 '당기판매액' 이 아니고 '전기요금' 은 날짜가 아니다
        self.assertNotEqual(hdrmap.mask("전기판매액"), hdrmap.mask("당기판매액"))
        self.assertEqual(hdrmap.mask("전기요금"), "전기요금")
        self.assertNotEqual(hdrmap._qid("kgrid", "015760", "revenue", "unknown", ["구분", "전기판매액"]),
                            hdrmap._qid("kgrid", "015760", "revenue", "unknown", ["구분", "당기판매액"]))
        self.assertEqual(hdrmap._diff([{"cols": ["구분", "당기", "전기"]}], [{"cols": ["구분", "전기", "당기"]}])[0]["kind"], "chg")

    def test_mask_dates(self):
        """KAI: 날짜만 다른 머리행 3분기 → 직전 분기 대조 chg 0. 저장값(cols)은 원문 그대로."""
        for q, cols in KAI.items():
            self.rec("kdef", "047810", q, "orders", [{"cols": cols, "n": 6, "lead": "수주상황", "tag": "openclose", "ent": "parent"}], {0},
                     meta={"name": "한국항공우주", "stock": "047810"})
        hdrmap.write("kdef", root=self.root, strict=True)
        for q in ("2026Q1", "2026Q2"):
            self.assertEqual(hdrmap.diff_prev("kdef", "047810", "orders", q, root=self.root, strict=True), [], q)
        M = hdrmap.load_map("kdef", root=self.root)
        self.assertEqual(M["companies"]["047810"]["roles"]["orders"]["2026Q2"][0]["cols"], KAI["2026Q2"])
        self.assertEqual(M["companies"]["047810"]["fq"], ["2025Q4", "2026Q1", "2026Q2"])
        # 첫 분기(직전 없음)는 빈 목록
        self.assertEqual(hdrmap.diff_prev("kdef", "047810", "orders", "2025Q4", root=self.root, strict=True), [])

    def test_real_change_still_detected(self):
        """대우건설 2023Q1 「계약일(공사착공일)」→「계약시작일」은 chg 로 남아야 한다. 법인 키(ent|tag#순번)로 짝짓는다."""
        before = STD
        after = ["공사명", "계약시작일", "완공예정일", "기본도급액", "완성공사액", "계약잔액"]
        self.rec("kce", "dwe", "2022Q4", "orders", [{"cols": before, "n": 30, "ent": "대우건설"}], {0})
        self.rec("kce", "dwe", "2023Q1", "orders", [{"cols": after, "n": 31, "ent": "대우건설"}], {0})
        d = hdrmap.diff_prev("kce", "dwe", "orders", "2023Q1", root=self.root, strict=True)
        self.assertEqual([(x["key"], x["kind"]) for x in d], [("대우건설|#1", "chg")])
        self.assertEqual(d[0]["prev"], before)
        self.assertEqual(d[0]["now"], after)
        # 법인 표 순서가 바뀌어도 법인 키로 짝지으므로 chg 가 아니다(현대건설 4표 꼴)
        a = {"cols": STD, "n": 62, "ent": "현대건설"}
        b = {"cols": STD, "n": 43, "ent": "현대엔지니어링"}
        c = {"cols": STD[:4] + ["누적기성금액", "계약잔액"], "n": 21, "ent": "현대스틸산업"}
        self.rec("kce", "hec", "2026Q1", "orders", [a, b, c], {0, 1, 2})
        self.rec("kce", "hec", "2026Q2", "orders", [b, a], {0, 1})
        d = hdrmap.diff_prev("kce", "hec", "orders", "2026Q2", root=self.root, strict=True)
        self.assertEqual([(x["key"], x["kind"]) for x in d], [("현대스틸산업|#1", "gone")])
        # 표가 비어 있던 분기는 건너뛰고 '기록된' 직전 분기와 대조한다
        self.rec("kce", "hec", "2026Q3", "orders", [], ())
        self.rec("kce", "hec", "2026Q4", "orders", [a, b, {"cols": STD, "n": 5, "ent": "현대스틸산업"}], {0, 1, 2})
        d = hdrmap.diff_prev("kce", "hec", "orders", "2026Q4", root=self.root, strict=True)
        self.assertEqual([(x["key"], x["kind"]) for x in d], [("현대스틸산업|#1", "new")])
        with self.assertRaises(hdrmap.HdrmapError):
            hdrmap.diff_prev("kce", "hec", "orders", "2030Q1", root=self.root, strict=True)

    def test_gseq_matches_js_132(self):
        """엔진 gseq == headers.html JS 구간 규칙(축자 이식) — 스냅샷 17사 3절 전부: 132구간·1,302표(dle-ii4 8, hec-ii4 6, dbe-ii4 10)."""
        D, LAB, ORDER, s, e3 = hdrmap._parse_page(_read(HEADERS_HTML))
        self.assertEqual(set(LAB), {"ii4", "p8", "xinb"})
        self.assertEqual(len(ORDER), 17)
        total = ntab = 0
        per = {}
        for co, d in D.items():
            for key in LAB:
                S = d["sections"].get(key) or {}
                ours = hdrmap.gseq(d["fq"], S, "%s-%s" % (co, key))
                self.assertEqual(ours, _js_gseq(co, key, d, S), "%s %s 구간 불일치" % (co, key))
                per[(co, key)] = len(ours)
                total += len(ours)
                ntab += sum(len(v) for v in S.values())
        self.assertEqual(total, 132)
        self.assertEqual((per[("dle", "ii4")], per[("hec", "ii4")], per[("dbe", "ii4")]), (8, 6, 10))
        self.assertEqual(ntab, 1302)
        # 공시가 끊긴 회사(DL건설 2024Q4·금호산업 꼴 xca 2022Q4)도 스냅샷에 그대로 있다 — 지도는 '끝난 회사'를 지우지 않는다
        self.assertEqual({k: d["fq"][-1] for k, d in D.items() if d["fq"][-1] != "2026Q2"}, {"dlc": "2024Q4", "xca": "2022Q4"})


class TestRecord(_Base):

    def test_n_includes_header(self):
        """n = 머리행 **포함** 원행수(상류 D 관례), n_rec = 파서 레코드 수 — 둘 다 추정하지 않는다(호출측 명시만).
        현대건설 2026Q2: 상류 D n [62,43,21,4] vs parse_ii4 레코드 [61,42,20,3]."""
        out = parse_ii4(_read(os.path.join(FIX, "hec_수주상황.html")))
        self.assertEqual(out["unknown_headers"], [])
        up = hdrmap._parse_page(_read(HEADERS_HTML))[0]["hec"]["sections"]["ii4"]["2026Q2"]
        self.assertEqual([r["n"] for r in up], [62, 43, 21, 4])            # 상류는 머리행 포함 원행수
        # ① 지금의 parse_ii4 출력(n=len(recs), rows=recs)을 그대로 넣으면 n == n_rec — 머리행을 더해 꾸미지 않는다
        ents = self.rec("kce", "hec", "2026Q2", "orders", out["tables"], set(range(len(out["tables"]))))
        self.assertEqual([e["n"] for e in ents], [61, 42, 20, 3])
        self.assertEqual([e["n_rec"] for e in ents], [61, 42, 20, 3])
        self.assertEqual([e["cols"] for e in ents], [r["cols"] for r in up])
        # ② U2 계약: rows 와 n(원행수)이 함께 오면 n 은 그대로 믿고 n_rec = len(rows) — 그래야 상류 D 와 맞는다
        tabs = [dict(t, n=r["n"]) for t, r in zip(out["tables"], up)]
        ents = self.rec("kce", "hec", "2026Q2", "orders", tabs, set(range(4)))
        self.assertEqual([e["n"] for e in ents], [62, 43, 21, 4])
        self.assertEqual([e["n_rec"] for e in ents], [61, 42, 20, 3])
        self.assertTrue(all(e["pick"] and e["reason"] == "picked" for e in ents))
        self.assertEqual(hdrmap.staged("kce", "hec")["name"], "현대건설")        # CORP 에서 이름·종목코드를 채운다
        # ③ 입력 조합표(모듈 docstring): 명시한 값만 적는다
        e = self.rec("kce", "hec", "2026Q3", "orders", [{"cols": STD, "n": 10, "n_rec": 8}], {0})[0]
        self.assertEqual((e["n"], e["n_rec"]), (10, 8))
        e = self.rec("kce", "hec", "2026Q4", "orders", [{"cols": STD, "n": 10}], {0})[0]
        self.assertEqual((e["n"], e["n_rec"]), (10, None))                  # rows 없이 n 만 — n_rec 를 n 으로 꾸미지 않는다
        e = self.rec("kce", "hec", "2027Q1", "orders", [{"cols": STD, "rows": [[""] * 6] * 7, "hdr_rows": 2}], {0})[0]
        self.assertEqual((e["n"], e["n_rec"]), (None, 7))                   # hdr_rows 로 n 을 추정하지 않는다
        self.assertEqual(e["lead"], "")
        self.assertEqual(e["ncols"], [norm_col(c) for c in STD])
        self.assertEqual(e["fields"], ["nm", "sd", "ed", "amt", "cmp", "bal"])
        e = self.rec("kce", "hec", "2027Q2", "orders", [{"cols": STD}], {0})[0]
        self.assertEqual((e["n"], e["n_rec"]), (None, None))
        # ④ 페이지(D 항목)에는 n 이 없으면 n_rec 가 간다 — 그 값은 레코드 수다
        self.assertEqual(hdrmap._to_js({"cols": STD, "n": None, "n_rec": 7, "pick": True}, False)["n"], 7)
        self.assertEqual(hdrmap._to_js({"cols": STD, "n": 9, "n_rec": 7, "pick": True}, False)["n"], 9)
        self.assertIsNone(hdrmap._to_js({"cols": STD, "n": None, "n_rec": None, "pick": True}, False)["n"])

    def test_multi_pick_kaero(self):
        """kaero 는 통화별로 표를 하나씩 채택한다({'KRW': 0, 'USD': 1}) — 둘 다 pick, cur 기록. 나머지·rejected 는 pick False."""
        tabs = [{"cols": ["사업명", "수주금액", "기납품액", "수주잔고"], "n": 5, "lead": "(단위: 백만원)"},
                {"cols": ["사업명", "수주금액", "기납품액", "수주잔고"], "n": 4, "lead": "(단위: 천USD)", "cur": "US$"},
                {"cols": ["구분", "매출액"], "n": 3}]
        rej = [{"cols": ["품목", "수주일자", "납기"], "n": 2, "reason": "few_fields"}]
        ents = self.rec("kaero", "012450", "2026Q2", "orders", tabs, {"KRW": 0, "USD": 1}, rejected=rej,
                        meta={"name": "한화에어로스페이스", "stock": "012450"})
        self.assertEqual([e["pick"] for e in ents], [True, True, False, False])
        self.assertEqual([e["cur"] for e in ents], ["KRW", "US$", None, None])      # 표가 cur 를 이미 가지면 덮지 않는다
        self.assertEqual([e["reason"] for e in ents], ["picked", "picked", "no_core", "few_fields"])
        r = hdrmap.write("kaero", root=self.root, strict=True)
        self.assertEqual((r["companies"], r["tables"], r["quarters"]), (1, 4, 1))
        M = hdrmap.load_map("kaero", root=self.root)
        self.assertEqual(M["companies"]["012450"]["name"], "한화에어로스페이스")
        self.assertEqual(len(M["companies"]["012450"]["roles"]["orders"]["2026Q2"]), 4)
        # picks 가 None 값을 가진 통화는 채택 없음
        ents = self.rec("kaero", "012450", "2026Q3", "orders", tabs, {"KRW": 0, "USD": None})
        self.assertEqual([e["pick"] for e in ents], [True, False, False])

    def test_reason_validated_and_shared_pieces(self):
        """reason 은 REASONS 밖이면 HdrmapError(dead constant 금지). UnknownHeaderError 선언, _SUFFIX_KIND·_blob_end 는 파서·렌더와 한 식."""
        with self.assertRaises(hdrmap.HdrmapError):
            self.rec("kce", "hec", "2026Q2", "orders", [{"cols": STD, "n": 5, "reason": "weird"}], ())
        with self.assertRaises(hdrmap.HdrmapError):
            self.rec("kce", "hec", "2026Q2", "orders", [], (), rejected=[{"cols": STD, "n": 5, "reason": "typo"}])
        with self.assertRaises(hdrmap.HdrmapError):
            self.rec("kce", "hec", "2026Q2", "orders", [], (), unknown=[{"cols": EWHA, "n": 5, "reason": "huh"}])
        self.assertEqual(hdrmap.load_queue("kce", root=self.root), [])           # 깨진 입력은 큐에도 안 간다
        others = [r for r in hdrmap.REASONS if r != "picked"]
        ents = self.rec("kce", "hec", "2026Q2", "orders", [{"cols": STD, "n": 5, "reason": r} for r in others], ())
        self.assertEqual([e["reason"] for e in ents], others)
        # UnknownHeaderError(HdrmapError(RuntimeError)) — kce 정밀이 enqueue 뒤 raise 하는 예외, U2·U4 공용
        self.assertTrue(issubclass(hdrmap.UnknownHeaderError, hdrmap.HdrmapError))
        self.assertTrue(issubclass(hdrmap.UnknownHeaderError, RuntimeError))
        with self.assertRaises(hdrmap.HdrmapError):
            raise hdrmap.UnknownHeaderError("미지 머리행")
        # 공종 접미 벗김은 kce_parse 의 식 하나(두 벌이면 벗김 결과가 갈라진다)
        self.assertIs(hdrmap._SUFFIX_KIND, kce_parse._SUFFIX_KIND)
        self.assertIn("현장명건축", hdrmap._variants("현장명건축")[0])
        self.assertIn("현장명", hdrmap._variants("현장명건축"))
        # _blob_end 는 복사본 — kce_render 의 것과 결과가 같고, kce_render 가 없어도 렌더가 산다
        h = _read(HEADERS_HTML)
        s = hdrmap._D_RE.search(h).end()
        self.assertEqual(hdrmap._blob_end(h, s), kce_render._blob_end(h, s))
        blob = '[1,"]",{"a":[2,"\\"}"]}]'
        self.assertEqual(hdrmap._blob_end("x=" + blob + ";", 2), 2 + len(blob))
        with self.assertRaises(ValueError):
            hdrmap._blob_end("x=[1,2", 2)
        src = _read(hdrmap.__file__)
        self.assertIsNone(re.search(r"^\s*(?:from|import)\s+kce_render\b", src, re.M), "hdrmap 은 kce_render 를 import 하지 않는다")

    def test_unknown_is_queued_even_if_stage_discarded(self):
        """미지 표는 기록 즉시 큐에 간다 — 호출측이 실패 분기에서 discard 해도 증거는 남는다."""
        ents = self.rec("kce", "001840", "2026Q2", "orders", [], (), unknown=[{"cols": EWHA, "n": 13, "lead": "나. 매출처별 현황"}],
                        meta={"name": "이화공영", "stock": "001840", "rcpNo": "20260814003697"})
        self.assertEqual([(e["pick"], e["reason"]) for e in ents], [(False, "near_miss")])
        hdrmap.discard("kce")
        self.assertIsNone(hdrmap.staged("kce", "001840"))
        self.assertFalse(os.path.exists(hdrmap.map_path("kce", self.root)))
        items = hdrmap.load_queue("kce", root=self.root)
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual((it["kind"], it["status"], it["grade"], it["key"], it["stock"], it["name"]),
                         ("unknown", "open", "B", "001840", "001840", "이화공영"))
        self.assertEqual(it["need_missing"], ["bal", "cmp"])
        self.assertEqual(it["fields_got"], ["amt", "nm"])
        self.assertEqual(it["cols_raw"], EWHA)
        self.assertEqual(it["rcpNo"], "20260814003697")
        self.assertTrue(it["reason"].startswith("need_missing:"))
        self.assertIsNone(it["suggest"])

    def test_engine_error_queued(self):
        """내부 예외는 삼키되 흔적을 남긴다: stderr 1줄 + 큐 engine_error. strict 면 raise."""
        err = io.StringIO()
        with redirect_stderr(err):
            r = hdrmap.record("kce", "hec", "2026Q2", "bogus", [], (), root=self.root)
        self.assertIsNone(r)
        self.assertIn("hdrmap kce record(hec)", err.getvalue())
        items = hdrmap.load_queue("kce", root=self.root)
        self.assertEqual([(i["kind"], i["status"], i["key"], i["role"]) for i in items], [("engine_error", "open", "hec", "bogus")])
        self.assertTrue(items[0]["reason"].startswith("record HdrmapError"))
        with self.assertRaises(hdrmap.HdrmapError):
            hdrmap.record("kce", "hec", "2026Q2", "bogus", [], (), root=self.root, strict=True)
        with self.assertRaises(hdrmap.HdrmapError):
            hdrmap.record("kce", "hec", "26Q2", "orders", [], (), root=self.root, strict=True)
        os.environ["HDRMAP_STRICT"] = "1"
        try:
            with self.assertRaises(hdrmap.HdrmapError):
                hdrmap.record("kce", "", "2026Q2", "orders", [], (), root=self.root)
        finally:
            del os.environ["HDRMAP_STRICT"]
        # 같은 자리·같은 오류는 큐에 하나
        with redirect_stderr(io.StringIO()):
            hdrmap.record("kce", "hec", "2026Q2", "bogus", [], (), root=self.root)
        self.assertEqual(len(hdrmap.load_queue("kce", root=self.root)), 1)

    def test_write_keeps_stage_on_failure(self):
        """5MB 가드 등으로 쓰기가 실패하면 스테이지가 남아 있어야 한다(먼저 pop 하면 기록이 증발한다)."""
        self.rec("kce", "hec", "2026Q2", "orders", [{"cols": STD, "n": 5}], {0})
        old = hdrmap.MAX_BYTES
        hdrmap.MAX_BYTES = 10
        try:
            with self.assertRaises(hdrmap.HdrmapError):
                hdrmap.write("kce", root=self.root, strict=True)
        finally:
            hdrmap.MAX_BYTES = old
        self.assertIsNotNone(hdrmap.staged("kce", "hec"))
        self.assertEqual(hdrmap.staged("kce", "hec")["roles"]["orders"]["2026Q2"][0]["ncols"], [norm_col(c) for c in STD])  # 압축이 스테이지를 건드리지 않았다
        self.assertFalse(os.path.exists(hdrmap.map_path("kce", self.root)))
        r = hdrmap.write("kce", root=self.root, strict=True)
        self.assertEqual(r["companies"], 1)
        self.assertIsNone(hdrmap.staged("kce", "hec"))
        self.assertTrue(os.path.exists(hdrmap.map_path("kce", self.root)))

    def test_write_per_company_and_deterministic(self):
        """key 를 주면 그 회사만 쓴다(kce 회사 단위 fail-closed). 같은 데이터 → 같은 바이트, 같은 분기 재적재 = 교체."""
        self.rec("kce", "hec", "2026Q2", "orders", [{"cols": STD, "n": 5}], {0})
        self.rec("kce", "sct", "2026Q2", "orders", [{"cols": STD, "n": 7}], {0})
        r = hdrmap.write("kce", key="hec", root=self.root, strict=True)
        self.assertEqual(r["companies"], 1)
        self.assertIsNone(hdrmap.staged("kce", "hec"))
        self.assertIsNotNone(hdrmap.staged("kce", "sct"))
        self.assertEqual(sorted(hdrmap.load_map("kce", root=self.root)["companies"]), ["hec"])
        hdrmap.write("kce", root=self.root, strict=True)
        t1 = _read(hdrmap.map_path("kce", self.root))
        M = json.loads(t1)
        self.assertEqual(sorted(M["companies"]), ["hec", "sct"])
        self.assertEqual(M["companies"]["hec"]["stock"], "000720")
        self.assertEqual(t1, json.dumps(M, ensure_ascii=False, sort_keys=True, indent=1) + "\n")
        self.rec("kce", "hec", "2026Q2", "orders", [{"cols": STD, "n": 5}], {0})
        hdrmap.write("kce", root=self.root, strict=True)
        self.assertEqual(_read(hdrmap.map_path("kce", self.root)), t1)
        self.assertEqual(hdrmap.write("kce", root=self.root, strict=True)["companies"], 0)
        self.assertNotIn("time", t1.lower())

    def test_map_compact_and_size(self):
        """디스크 지도는 압축본: cols_raw 는 cols 와 다를 때만, ncols 는 norm_col(cols) 와 다를 때만. load_map 이 복원한다.
        크기: 최악 꼴(7열 한글·cols_raw 상이·lead 120자·메타 전부) 엔트리 2,318개(kdef 캐시 표 수) < 5MB 가드, kce 1,302+lite 798 도."""
        raw = ["공 사 명", "발주처", "계약일", "완공예정일", "기본도급액 ※1", "완성공사액", "계약잔액"]
        custom = ["공사명", "발주처", "계약일", "완공예정일", "기본도급액", "완성공사액", "계약잔액"]      # 호출측(kship)의 자체 정규화
        self.rec("kce", "hec", "2026Q2", "orders", [{"cols": STD, "n": 62, "n_rec": 61, "lead": "1) 현대건설 [국내공사]", "ent": "현대건설", "tag": "국내"}], {0})
        self.rec("kce", "hec", "2026Q2", "progress", [{"cols": STRIP, "cols_raw": raw, "ncols": custom, "n": 40, "basis": "연결"}], {0})
        hdrmap.write("kce", root=self.root, strict=True)
        disk = json.loads(_read(hdrmap.map_path("kce", self.root)))["companies"]["hec"]["roles"]
        e0 = disk["orders"]["2026Q2"][0]
        self.assertNotIn("ncols", e0)
        self.assertNotIn("cols_raw", e0)
        self.assertEqual(set(e0), {"cols", "fields", "n", "n_rec", "lead", "pick", "reason"} | set(hdrmap._ENTRY_META))
        e1 = disk["progress"]["2026Q2"][0]
        self.assertEqual((e1["cols_raw"], e1["ncols"]), (raw, custom))                 # 다르면 남긴다(복구 전 원문·자체 정규화)
        M = hdrmap.load_map("kce", root=self.root)
        o = M["companies"]["hec"]["roles"]["orders"]["2026Q2"][0]
        self.assertEqual((o["cols_raw"], o["ncols"]), (STD, [norm_col(c) for c in STD]))
        p = M["companies"]["hec"]["roles"]["progress"]["2026Q2"][0]
        self.assertEqual((p["cols_raw"], p["ncols"]), (raw, custom))
        # 복원본으로 다시 쓰면 바이트 동일(압축이 멱등)
        self.rec("kce", "hec", "2026Q2", "orders", [dict(o)], {0})
        t1 = _read(hdrmap.map_path("kce", self.root))
        hdrmap.write("kce", root=self.root, strict=True)
        self.assertEqual(_read(hdrmap.map_path("kce", self.root)), t1)
        # 크기 단언 — 61사 × 2역할 × 19분기 = 2,318표(맥미니 kdef reports_cache 1,125파일 실측 표 수)
        root2 = os.path.join(self.root, "size")
        worst = {"cols": EWHA, "cols_raw": [c + "※" for c in EWHA], "n": 123, "n_rec": 120,
                 "lead": ("가. 수주상황 — 당사 및 종속회사의 보고기간 종료일 현재 진행 중인 공사 계약 현황은 다음과 같습니다 " * 3)[:120],
                 "ent": "한국항공우주산업", "tag": "openclose", "basis": "연결", "cur": "KRW", "unit_seen": True, "synth": "2row",
                 "shape": "openclose", "sec_title": "II. 사업의 내용 4. 수주상황", "rcpNo": "20260814003697"}
        qs = ["%dQ%d" % (y, q) for y in range(2022, 2027) for q in range(1, 5)][:19]
        for i in range(61):
            for role in ("orders", "revenue"):
                for q in qs:
                    self.rec("kdef", "%06d" % i, q, role, [worst], {0}, root=root2, meta={"name": "회사%d" % i, "stock": "%06d" % i})
        hdrmap.write("kdef", root=root2, strict=True)
        nb = os.path.getsize(hdrmap.map_path("kdef", root2))
        per = nb / 2318.0
        self.assertLess(nb, hdrmap.MAX_BYTES, "kdef 2,318표 %d bytes" % nb)
        self.assertLessEqual(per, 1300, "최악 꼴 표당 %d bytes" % per)                # 실측 1,239 B/표(압축 전 ≈1,468)
        self.assertLess((1302 + 798) * per, hdrmap.MAX_BYTES, "kce 정밀+lite 를 최악 꼴로 채워도 가드 안")
        self.assertLess(len(hdrmap._dumps(hdrmap._compact(hdrmap._entry(dict(worst, cols_raw=EWHA), True, "picked", {})))),
                        len(hdrmap._dumps(hdrmap._entry(dict(worst, cols_raw=EWHA), True, "picked", {}))))
        self.assertEqual(len(hdrmap.load_map("kdef", root=root2)["companies"]), 61)
        # 보통 꼴(kce II-4: 6열·cols_raw 동일·메타 일부) 은 표당 ≤800 B(실측 724)
        hdrmap.discard("kdef")
        root3 = os.path.join(self.root, "typ")
        typ = {"cols": STD, "n": 62, "n_rec": 61, "lead": "1) 현대건설 [국내공사] (단위: 백만원)", "ent": "현대건설", "tag": "국내"}
        for i in range(61):
            for role in ("orders", "revenue"):
                for q in qs:
                    self.rec("kdef", "%06d" % i, q, role, [typ], {0}, root=root3, meta={"name": "회사%d" % i, "stock": "%06d" % i})
        hdrmap.write("kdef", root=root3, strict=True)
        self.assertLessEqual(os.path.getsize(hdrmap.map_path("kdef", root3)) / 2318.0, 800)

    def test_replay_upstream_D_lossless(self):
        """상류 D(스냅샷 17사 1,302표)를 전부 지도에 기록하면 1.3MB 안(압축 전 1,910,734 B)이고, 그 지도로 다시 그린 페이지는
        스냅샷과 바이트 동일 — 지도 → 페이지가 무손실(비-lead 필드 diff 0·lead 절단 0·fq·ORDER·LAB 동일). DART 요청 0."""
        path, orig = self.kce_page()
        D = hdrmap._parse_page(orig)[0]
        n = 0
        for co, d in D.items():
            for sec, role in hdrmap._KCE_ROLE:
                for q, items in (d["sections"].get(sec) or {}).items():
                    tabs = [{"cols": r["cols"], "n": r["n"], "lead": r["lead"], "ent": r.get("ent"), "tag": r.get("tag")} for r in items]
                    self.rec("kce", co, q, role, tabs, {i for i, r in enumerate(items) if r["pick"]})
                    n += len(items)
        self.assertEqual(n, 1302)
        r = hdrmap.write("kce", root=self.root, strict=True)
        self.assertEqual((r["companies"], r["tables"]), (17, 1302))
        nb = os.path.getsize(hdrmap.map_path("kce", self.root))
        self.assertLess(nb, 1_300_000, "상류 1,302표 %d bytes" % nb)
        self.assertLess(nb, 1_910_734)                                                 # 압축 전 실측
        M = hdrmap.load_map("kce", root=self.root)
        self.assertEqual(sorted(M["companies"]), sorted(D))
        for co in D:
            self.assertEqual(M["companies"][co]["stock"], hdrmap.CORP[co]["stock"], co)
        text = hdrmap.render_headers("kce", root=self.root, write=False, strict=True)
        self.assertEqual(text, orig)


class TestQueue(_Base):

    def _ewha(self, q, **kw):
        it = {"kind": "unknown", "key": "001840", "role": "orders", "quarter": q, "cols": EWHA,
              "name": "이화공영", "stock": "001840", "lead": "나. 매출처별 현황"}
        it.update(kw)
        return hdrmap.enqueue("kce", it, root=self.root)

    def test_queue_append_only_no_time(self):
        it1 = self._ewha("2026Q1")
        it2 = self._ewha("2026Q2", rcpNo="r2")
        self.assertEqual(it1["id"], it2["id"])
        items = hdrmap.load_queue("kce", root=self.root)
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0]["quarter_first"], items[0]["quarter_last"], items[0]["rcpNo"]), ("2026Q1", "2026Q2", "r2"))
        hdrmap.enqueue("kce", {"kind": "unknown", "key": "001840", "role": "orders", "quarter": "2026Q2", "cols": STD + ["비율(%)"]},
                       root=self.root)
        hdrmap.enqueue("kce", {"kind": "no_tables", "key": "002290", "role": "orders", "quarter": "2026Q2"}, root=self.root)
        items = hdrmap.load_queue("kce", root=self.root)
        self.assertEqual(len(items), 3)
        self.assertEqual([i["id"] for i in items], sorted(i["id"] for i in items))
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{12}", i["id"]) for i in items))
        want = {"id", "tab", "key", "stock", "name", "role", "kind", "status", "grade", "quarter_first", "quarter_last",
                "reopened", "rcpNo", "cols_raw", "ncols", "fields_got", "need_missing", "lead", "suggest", "reason", "resolved_in"}
        for i in items:
            self.assertEqual(set(i), want)
            for k in i:
                self.assertIsNone(re.search(r"time|_at$|date|stamp|now", k), k)
        # 같은 데이터 → 같은 바이트(정규화 JSON)
        t1 = _read(hdrmap.queue_path("kce", self.root))
        self._ewha("2026Q2", rcpNo="r2")
        self.assertEqual(_read(hdrmap.queue_path("kce", self.root)), t1)
        self.assertEqual(t1, json.dumps(items, ensure_ascii=False, sort_keys=True, indent=1) + "\n")
        # resolved 전환은 상태만 바꾼다 — 항목은 지워지지 않는다(append-only)
        n = hdrmap.resolve_clean("kce", "001840", "orders", "2026Q3", root=self.root, strict=True)
        self.assertEqual(n, 2)
        items = hdrmap.load_queue("kce", root=self.root)
        self.assertEqual(len(items), 3)
        self.assertEqual(sorted(i["status"] for i in items), ["open", "resolved", "resolved"])
        self.assertEqual({i["resolved_in"] for i in items if i["status"] == "resolved"}, {"2026Q3"})
        self.assertEqual(len(hdrmap.open_items("kce", root=self.root)), 1)
        self.assertEqual(hdrmap.open_items("kce", root=self.root, kind="no_tables")[0]["key"], "002290")
        with self.assertRaises(hdrmap.HdrmapError):
            hdrmap.enqueue("kce", {"kind": "weird", "key": "x"}, root=self.root)

    def test_enqueue_thread_safe(self):
        """큐·자동사전은 프로세스 내 잠금 아래서 읽고-고치고-쓴다 — 8스레드 × 25건(=200) 을 올려도 증발 0, 바이트 결정성.
        잠금 전 실측(심사): 200건 → 28건, stderr 0줄."""
        def item(i):
            if i % 2:          # B — 필드 부족
                return {"kind": "unknown", "key": "%06d" % i, "role": "orders", "quarter": "2026Q2", "name": "회사%d" % i,
                        "stock": "%06d" % i, "cols": STD[:3] + ["열%03d" % i]}
            # A — 각주 벗김(기본도급액 ※i) + 레코드 성립 + 합계행 대조 → 자동 사전에도 적힌다
            return {"kind": "unknown", "key": "%06d" % i, "role": "orders", "quarter": "2026Q2", "name": "회사%d" % i,
                    "stock": "%06d" % i, "cols": STRIP[:4] + ["기본도급액 ※%d" % i] + STRIP[5:],
                    "checks": {"recon": 1.0, "records": True}}
        with ThreadPoolExecutor(8) as ex:
            list(ex.map(lambda i: hdrmap.enqueue("kce", item(i), root=self.root), range(200)))
        items = hdrmap.load_queue("kce", root=self.root)
        self.assertEqual(len(items), 200)
        self.assertEqual([i["id"] for i in items], sorted(i["id"] for i in items))
        self.assertEqual(sorted(i["grade"] for i in items), ["A"] * 100 + ["B"] * 100)
        t1 = _read(hdrmap.queue_path("kce", self.root))
        self.assertEqual(t1, json.dumps(items, ensure_ascii=False, sort_keys=True, indent=1) + "\n")
        auto = hdrmap.load_auto_alias(hdrmap.auto_alias_path("kce", self.root))
        self.assertEqual(len(auto), 100)
        self.assertTrue(all(v["field"] == "amt" for v in auto.values()))
        # 스레드 순서가 달라도 같은 바이트(id 정렬·시각 없음) — 큐·자동사전 둘 다
        root2 = os.path.join(self.root, "r2")
        with ThreadPoolExecutor(8) as ex:
            list(ex.map(lambda i: hdrmap.enqueue("kce", item(i), root=root2), reversed(range(200))))
        self.assertEqual(_read(hdrmap.queue_path("kce", root2)), t1)
        self.assertEqual(_read(hdrmap.auto_alias_path("kce", root2)), _read(hdrmap.auto_alias_path("kce", self.root)))
        # record(unknown=…) 병렬(kce_series.collect_one 꼴) — 큐 건수·스테이지 회사 수 일치, 그 뒤 write·resolve_clean 도 잠금 아래
        root3 = os.path.join(self.root, "r3")

        def rec(i):
            return hdrmap.record("kce", "%06d" % i, "2026Q2", "orders", [], (), unknown=[{"cols": STD[:3] + ["열%03d" % i], "n": 3}],
                                 meta={"name": "회사%d" % i, "stock": "%06d" % i}, root=root3, strict=True)
        with ThreadPoolExecutor(8) as ex:
            list(ex.map(rec, range(80)))
        self.assertEqual(len(hdrmap.load_queue("kce", root=root3)), 80)
        self.assertEqual(len(hdrmap.staged("kce")), 80)
        with ThreadPoolExecutor(8) as ex:
            list(ex.map(lambda i: hdrmap.resolve_clean("kce", "%06d" % i, "orders", "2026Q3", root=root3, strict=True), range(80)))
        self.assertEqual(len(hdrmap.open_items("kce", root=root3)), 0)
        self.assertEqual(hdrmap.write("kce", root=root3, strict=True)["companies"], 80)

    def test_resolve_on_clean_pick_and_reopen(self):
        """write 가 깨끗이 채택된 표와 같은(마스킹) 머리행의 open 항목을 닫고, 닫힌 문제가 재발하면 reopened 가 는다(회귀)."""
        hdrmap.enqueue("kce", {"kind": "unknown", "key": "047810", "role": "orders", "quarter": "2026Q1", "cols": KAI["2026Q1"]},
                       root=self.root)
        hdrmap.enqueue("kce", {"kind": "no_tables", "key": "047810", "role": "orders", "quarter": "2026Q1"}, root=self.root)
        hdrmap.enqueue("kce", {"kind": "unknown", "key": "047810", "role": "progress", "quarter": "2026Q1", "cols": STD}, root=self.root)
        self.rec("kce", "047810", "2026Q2", "orders", [{"cols": KAI["2026Q2"], "n": 6}], {0})      # 날짜만 다른 같은 표
        r = hdrmap.write("kce", root=self.root, strict=True)
        self.assertEqual(r["resolved"], 2)
        items = {(i["role"], i["kind"]): i for i in hdrmap.load_queue("kce", root=self.root)}
        self.assertEqual(items[("orders", "unknown")]["status"], "resolved")
        self.assertEqual(items[("orders", "unknown")]["resolved_in"], "2026Q2")
        self.assertEqual(items[("orders", "no_tables")]["status"], "resolved")
        self.assertEqual(items[("progress", "unknown")]["status"], "open")        # 다른 역할은 그대로
        # 재발(resolved_in 보다 뒤 분기) → open 으로 되돌아가며 reopened +1 ; 과거 분기 재적재는 되돌리지 않는다
        it = hdrmap.enqueue("kce", {"kind": "unknown", "key": "047810", "role": "orders", "quarter": "2026Q3", "cols": KAI["2026Q2"]},
                            root=self.root)
        self.assertEqual((it["status"], it["reopened"], it["resolved_in"]), ("open", 1, None))
        hdrmap.resolve_clean("kce", "047810", "orders", "2026Q4", root=self.root, strict=True)
        it = hdrmap.enqueue("kce", {"kind": "unknown", "key": "047810", "role": "orders", "quarter": "2026Q1", "cols": KAI["2026Q2"]},
                            root=self.root)
        self.assertEqual((it["status"], it["reopened"]), ("resolved", 1))
        self.assertEqual(len(hdrmap.load_queue("kce", root=self.root)), 3)

    def test_synth_changed_stay_open_on_pick(self):
        """synth·changed 는 '채택된 표 자체를 사람에게 보이는' 항목 — 같은 분기 채택으로는 닫히지 않는다(사람 눈에 닿기 전 소멸 금지).
        synth: 뒤 분기에 같은 (key, role) **비합성** 채택 → 닫힘. changed: 뒤 분기에 같은 머리행 재채택(정착) → 닫힘.
        unknown 은 종전대로 즉시. 명시 resolve_clean 은 종류를 가리지 않는다."""
        meta = {"name": "한화", "stock": "000880"}
        for kind in ("synth", "changed", "unknown"):
            hdrmap.enqueue("kce", {"kind": kind, "key": "000880", "role": "orders", "quarter": "2026Q2", "cols": STD,
                                   "synth": "2row" if kind == "synth" else None}, root=self.root)
        self.rec("kce", "000880", "2026Q2", "orders", [{"cols": STD, "n": 5, "synth": "2row"}], {0}, meta=meta)
        r = hdrmap.write("kce", root=self.root, strict=True)
        self.assertEqual(r["resolved"], 1)                                             # unknown 만
        st = {i["kind"]: i["status"] for i in hdrmap.load_queue("kce", root=self.root)}
        self.assertEqual(st, {"synth": "open", "changed": "open", "unknown": "resolved"})
        self.assertEqual(hdrmap.check("kce", root=self.root)["open_by_kind"], {"changed": 1, "synth": 1})   # Step Summary 에 보인다
        # 다음 분기에도 합성 채택 → synth 그대로 open ; 같은 머리행 재채택 → changed 는 정착(2026Q3 에 닫힘)
        self.rec("kce", "000880", "2026Q3", "orders", [{"cols": STD, "n": 5, "synth": "2row"}], {0}, meta=meta)
        hdrmap.write("kce", root=self.root, strict=True)
        items = {i["kind"]: i for i in hdrmap.load_queue("kce", root=self.root)}
        self.assertEqual(items["synth"]["status"], "open")
        self.assertEqual((items["changed"]["status"], items["changed"]["resolved_in"]), ("resolved", "2026Q3"))
        # 비합성 채택(사전·파서가 고쳐짐) → synth 닫힘
        self.rec("kce", "000880", "2026Q4", "orders", [{"cols": STD, "n": 5}], {0}, meta=meta)
        hdrmap.write("kce", root=self.root, strict=True)
        items = {i["kind"]: i for i in hdrmap.load_queue("kce", root=self.root)}
        self.assertEqual((items["synth"]["status"], items["synth"]["resolved_in"]), ("resolved", "2026Q4"))
        self.assertEqual(items["changed"]["resolved_in"], "2026Q3")
        # 같은 분기의 비합성 채택도 synth 를 닫지 않는다(그 분기에 열린 항목은 사람이 먼저 봐야 한다)
        root2 = os.path.join(self.root, "r2")
        hdrmap.enqueue("kce", {"kind": "synth", "key": "000880", "role": "orders", "quarter": "2026Q2", "cols": STD, "synth": True}, root=root2)
        hdrmap.enqueue("kce", {"kind": "changed", "key": "000880", "role": "orders", "quarter": "2026Q2", "cols": STD}, root=root2)
        self.rec("kce", "000880", "2026Q2", "orders", [{"cols": STD, "n": 5}], {0}, meta=meta, root=root2)
        self.assertEqual(hdrmap.write("kce", root=root2, strict=True)["resolved"], 0)
        self.assertEqual(sorted(i["kind"] for i in hdrmap.open_items("kce", root=root2)), ["changed", "synth"])
        # 명시 전환은 언제나
        self.assertEqual(hdrmap.resolve_clean("kce", "000880", "orders", "2026Q2", root=root2, strict=True), 2)
        self.assertEqual(hdrmap.open_items("kce", root=root2), [])


class TestClassify(_Base):

    def test_classify_A_vs_B(self):
        n = lambda cols: [norm_col(c) for c in cols]  # noqa: E731
        # 이화공영 매출처 표 — nm·amt 만 맞고 cmp·bal 없음 → 사람 확인(NEED 가 ② 보다 먼저 말한다)
        g, r = hdrmap.classify(n(EWHA), None, II4_NEED, {"recon": 1.0})
        self.assertEqual(g, "B")
        self.assertEqual(r, "need_missing:bal,cmp")
        self.assertIsNone(hdrmap._field_of(norm_col("기본도급액 ※1")))         # 파서 사전만으로는 미지
        # ② rows 도 records 도 없으면 미검증 → B. kce parse_ii4 의 unknown 항목은 {cols,n} 뿐이라 rows 를 동봉하지 않는
        #    한 이 경로는 영구 B 다 — recon 하나로 자동 사전에 들어가는 우회는 막는다.
        self.assertEqual(hdrmap.classify(n(STRIP), None, II4_NEED, {"recon": 1.0}), ("B", "records_unverified"))
        self.assertEqual(hdrmap.classify(n(STRIP), None, II4_NEED, {"bal_sum": 100, "bal_prev": 90}), ("B", "records_unverified"))
        # 각주 벗김(※1) 뒤 COL_ALIAS 정확 일치 + NEED 충족 + 레코드 실측(rows) + 합계행 대조 → 자동
        ck = {"recon": 1.0, "rows": ROW7, "cols": STRIP}
        self.assertEqual(hdrmap.classify(n(STRIP), None, II4_NEED, ck), ("A", {"기본도급액※1": "amt"}))
        self.assertEqual(hdrmap.classify(n(STRIP), None, II4_NEED, {"bal_sum": 100, "bal_prev": 90, "rows": ROW7, "cols": STRIP}),
                         ("A", {"기본도급액※1": "amt"}))
        # 호출측이 ② 를 이미 확인했으면 records=True 로 대신한다(저장 안 하는 rows 를 안 보내도 된다)
        self.assertEqual(hdrmap.classify(n(STRIP), None, II4_NEED, {"recon": 1.0, "records": True}), ("A", {"기본도급액※1": "amt"}))
        self.assertEqual(hdrmap.classify(n(STRIP), None, II4_NEED, {"recon": 1.0, "records": False}), ("B", "records_none"))
        # ③ 수치 검증이 없거나 벗어나면 B — 매핑이 맞아 보여도 값이 틀릴 수 있다
        self.assertEqual(hdrmap.classify(n(STRIP), None, II4_NEED, {"rows": ROW7, "cols": STRIP}), ("B", "no_numeric_check"))
        self.assertEqual(hdrmap.classify(n(STRIP), None, II4_NEED, dict(ck, recon=1.2)), ("B", "recon:1.200"))
        self.assertEqual(hdrmap.classify(n(STRIP), None, II4_NEED, {"bal_sum": 100, "bal_prev": 50, "rows": ROW7, "cols": STRIP}),
                         ("B", "bal_ratio:2.00"))
        # 합성 머리행은 첫 등장이면 무조건 사람 확인
        self.assertEqual(hdrmap.classify(n(STRIP), None, II4_NEED, dict(ck, synth="2row")), ("B", "synth_header"))
        # 편집거리 1(길이≥4·숫자 없음·후보 유일): 완공예정일자 → 완공예정일(ed)
        e1 = ["공사명", "발주처", "계약일", "완공예정일자", "기본도급액", "완성공사액", "계약잔액"]
        self.assertEqual(hdrmap.classify(n(e1), None, II4_NEED, {"recon": 1.0, "rows": ROW7, "cols": e1}), ("A", {"완공예정일자": "ed"}))
        # 다의 열(계약금액: amt vs xi_amt)은 자동 반영 금지
        amb = ["공사명", "계약금액", "완성공사액", "계약잔액"]
        self.assertEqual(hdrmap.classify(n(amb), ["nm", None, "cmp", "bal"], II4_NEED, {"recon": 1.0}), ("B", "ambiguous:계약금액"))
        # 한 필드에 두 열 → 사람 확인
        dup = ["공사명", "기본도급액", "도급액※", "완성공사액", "계약잔액"]
        self.assertEqual(hdrmap.classify(n(dup), None, II4_NEED, {"recon": 1.0}), ("B", "dup_field:amt"))
        # 역할 NEED 가 없으면 판정 불가(B)
        self.assertEqual(hdrmap.classify(n(STRIP), None, set(), {"recon": 1.0}), ("B", "no_need"))
        # rows 가 있으면 _records 로 ② 를 실측한다 — 전부 합계행이면 레코드 0 → B
        rows = [["합계", "", "", "", "100", "50", "50"]]
        self.assertEqual(hdrmap.classify(n(STRIP), None, II4_NEED, {"recon": 1.0, "rows": rows, "cols": STRIP}), ("B", "records_none"))

    def test_suggest_grades(self):
        it = hdrmap.suggest({"role": "orders", "kind": "unknown", "ncols": [norm_col(c) for c in EWHA]})
        self.assertEqual((it["grade"], it["suggest"], it["fields_got"], it["need_missing"]), ("B", None, ["amt", "nm"], ["bal", "cmp"]))
        it = hdrmap.suggest({"role": "orders", "kind": "unknown", "ncols": [norm_col(c) for c in STRIP], "checks": {"recon": 1.0}})
        self.assertEqual((it["grade"], it["suggest"], it["reason"]), ("B", None, "records_unverified"))
        it = hdrmap.suggest({"role": "orders", "kind": "unknown", "ncols": [norm_col(c) for c in STRIP], "cols_raw": STRIP, "rows": ROW7,
                             "checks": {"recon": 1.0}})
        self.assertEqual((it["grade"], it["suggest"], it["reason"]), ("A", {"기본도급액※1": "amt"}, "auto_alias"))
        it = hdrmap.suggest({"role": "orders", "kind": "unknown", "ncols": [norm_col(c) for c in STRIP], "synth": True,
                             "checks": {"recon": 1.0, "records": True}})
        self.assertEqual((it["grade"], it["reason"]), ("B", "synth_header"))
        it = hdrmap.suggest({"role": "*", "kind": "new_company", "ncols": []})
        self.assertEqual((it["grade"], it["suggest"], it["reason"]), ("B", None, "new_company"))
        # 역할별 NEED 는 kce_parse 의 값을 읽는다
        self.assertEqual(hdrmap._need_of("orders"), II4_NEED)
        self.assertEqual(hdrmap._need_of("progress"), {"amt", "pr", "ub", "rc"})
        # XI 는 kce_xi1.NEED 와 같아야 한다(대금수령 열 없는 표도 읽는다 — 2026-10-16 섹터 304사)
        import kce_xi1
        self.assertEqual(hdrmap._need_of("xi"), set(kce_xi1.NEED))
        self.assertEqual(hdrmap._need_of("xi"), {"xi_nm", "xi_amt", "xi_supCum"})
        self.assertEqual(hdrmap._need_of("revenue"), set())

    def test_auto_alias_never_shadows_col_alias(self):
        path = hdrmap.auto_alias_path("kce", self.root)
        prov = {"stock": "001840", "quarter": "2026Q2", "rcpNo": "r1", "raw": {"기본도급액※1": "기본도급액 ※1"}}
        added = hdrmap.record_auto_alias("kce", {"공사명": "cl", "기본도급액※1": "amt", "": "x", "빈필드": None}, prov, root=self.root)
        self.assertEqual(added, ["기본도급액※1"])
        auto = hdrmap.load_auto_alias(path)
        self.assertEqual(set(auto), {"기본도급액※1"})
        self.assertEqual(auto["기본도급액※1"], {"field": "amt", "provenance": {"stock": "001840", "quarter": "2026Q2", "rcpNo": "r1",
                                                                                "raw": "기본도급액 ※1"}})
        self.assertEqual(_read(path), json.dumps(auto, ensure_ascii=False, sort_keys=True, indent=1) + "\n")
        # 첫 출처 보존 — 같은 키를 다시 적어도 바뀌지 않는다
        self.assertEqual(hdrmap.record_auto_alias("kce", {"기본도급액※1": "cmp"}, {"stock": "x"}, root=self.root), [])
        self.assertEqual(hdrmap.load_auto_alias(path)["기본도급액※1"]["field"], "amt")
        # merge_auto: 손 사전 키는 하나도 바뀌지 않고, 없는 키만 더해진다. 파일에 손 사전 키가 섞여 있어도 가리지 않는다.
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"기본도급액※1": {"field": "amt"}, "공사명": {"field": "cl"}, "짧은형": "bal"}, f, ensure_ascii=False)
        alias = dict(COL_ALIAS)
        self.assertEqual(hdrmap.merge_auto(alias, path), 2)
        for k, v in COL_ALIAS.items():
            self.assertEqual(alias[k], v, k)
        self.assertEqual((alias["기본도급액※1"], alias["짧은형"]), ("amt", "bal"))
        self.assertEqual(hdrmap.merge_auto(dict(COL_ALIAS), None), 0)
        self.assertEqual(hdrmap.merge_auto(dict(COL_ALIAS), os.path.join(self.root, "없는파일.json")), 0)
        # 큐의 A 판정이 자동 사전을 적는다 — B 는 적지 않는다. A 는 rows(레코드 실측)까지 있어야 한다
        root2 = os.path.join(self.root, "r2")
        hdrmap.enqueue("kce", {"kind": "unknown", "key": "001840", "role": "orders", "quarter": "2026Q2", "stock": "001840", "rcpNo": "r9",
                               "cols": STRIP, "rows": ROW7, "checks": {"recon": 1.0}}, root=root2)
        hdrmap.enqueue("kce", {"kind": "unknown", "key": "001840", "role": "orders", "quarter": "2026Q2", "cols": EWHA}, root=root2)
        hdrmap.enqueue("kce", {"kind": "unknown", "key": "001840", "role": "progress", "quarter": "2026Q2", "cols": STRIP,
                               "checks": {"recon": 1.0}}, root=root2)                   # rows 없음 → B, 사전에 안 적힌다
        auto = hdrmap.load_auto_alias(hdrmap.auto_alias_path("kce", root2))
        self.assertEqual(list(auto), ["기본도급액※1"])
        self.assertEqual(auto["기본도급액※1"]["provenance"], {"stock": "001840", "quarter": "2026Q2", "rcpNo": "r9", "raw": "기본도급액 ※1"})
        self.assertEqual(sorted(i["grade"] for i in hdrmap.load_queue("kce", root=root2)), ["A", "B", "B"])
        self.assertNotIn("rows", hdrmap.load_queue("kce", root=root2)[0])               # rows 는 저장하지 않는다


class TestRender(_Base):

    def test_render_17co_bytes_same(self):
        """빈 지도로 렌더하면 headers.html 17사 바이트 불변(const D·LAB·ORDER 재조립이 상류 포맷과 같다)."""
        path, orig = self.kce_page()
        text = hdrmap.render_headers("kce", root=self.root, strict=True)
        self.assertEqual(text, orig)
        self.assertEqual(_read(path), orig)
        self.assertEqual(hdrmap.render_headers("kce", out_html=path, root=self.root, write=False, strict=True), orig)

    def test_live_headers_roundtrip_relative(self):
        """배포물 argus/kce/headers.html 은 봇이 갱신한다(신규사가 붙으면 ORDER 18) — 절대값은 fixture 가, 여기서는 상대 단언만:
        파싱 가능·17사 이상·절 ⊇ {ii4,p8,xinb}·빈 지도 렌더 = 원본 바이트."""
        if not os.path.exists(LIVE_HEADERS):
            self.skipTest("live headers.html 없음")
        live = _read(LIVE_HEADERS)
        D, LAB, ORDER, s, e = hdrmap._parse_page(live)
        self.assertGreaterEqual(len(ORDER), 17)
        self.assertTrue({"ii4", "p8", "xinb"} <= set(LAB))
        self.assertTrue(all(co in D for co in ORDER))
        path, _ = self.kce_page(LIVE_HEADERS)
        self.assertEqual(hdrmap.render_headers("kce", root=self.root, write=False, strict=True), live)

    def test_render_adds_company_and_order_idempotent(self):
        path, orig = self.kce_page()
        D0, LAB0, ORDER0, s0, e0 = hdrmap._parse_page(orig)
        d_blob0 = orig[s0:hdrmap._blob_end(orig, s0)]
        meta = {"name": "새회사", "stock": "999999"}
        self.rec("kce", "newco", "2026Q3", "orders", [{"cols": STD, "n": 5, "n_rec": 4, "lead": "1) 새회사 [국내공사]", "ent": "새회사", "tag": "국내"}],
                 {0}, meta=meta)
        self.rec("kce", "newco", "2026Q3", "progress", [{"cols": ["공사명", "수주총액", "진행률", "미청구공사 총액", "공사미수금 총액"], "n": 3,
                                                        "basis": "연결", "lead": "(1) 연결기준"}], {0}, meta=meta)
        self.rec("kce", "newco", "2026Q3", "xi", [], (), meta=meta)                     # 봤는데 표 없음
        hdrmap.write("kce", root=self.root, strict=True)
        # add_company=False 면 지도에만 있는 회사는 건너뛰고 바이트 불변
        with redirect_stderr(io.StringIO()):
            self.assertEqual(hdrmap.render_headers("kce", root=self.root, add_company=False, write=False, strict=True), orig)
        text = hdrmap.render_headers("kce", root=self.root, strict=True)
        self.assertEqual(_read(path), text)
        D1, LAB1, ORDER1, s1, e1 = hdrmap._parse_page(text)
        self.assertEqual(ORDER1, ORDER0 + ["newco"])
        self.assertEqual(LAB1, LAB0)
        self.assertEqual(text[:s0], orig[:s0])                 # 머리(CSS·본문) 불변
        self.assertEqual(text[e1:], orig[e0:])                 # JS 꼬리 불변
        self.assertTrue(text[s1:].startswith(d_blob0[:-1] + ',"newco":'), "17사 D 블롭이 바이트 그대로 앞에 있어야 한다")
        for co in ORDER0:
            self.assertEqual(json_for_html(D1[co]), json_for_html(D0[co]), co)
        n = D1["newco"]
        self.assertEqual((n["name"], n["cfgsig"], n["fq"], set(n["sections"])), ("새회사", "", ["2026Q3"], {"ii4", "p8", "xinb"}))
        ii4 = n["sections"]["ii4"]["2026Q3"]
        self.assertEqual(ii4, [{"tag": "국내", "ent": "새회사", "cols": STD, "n": 5, "lead": "1) 새회사 [국내공사]", "pick": True}])
        self.assertEqual(list(ii4[0]), ["tag", "ent", "cols", "n", "lead", "pick"])            # 상류 항목 키 순서
        p8 = n["sections"]["p8"]["2026Q3"]
        self.assertEqual(list(p8[0]), ["tag", "cols", "n", "lead", "pick"])
        self.assertEqual((p8[0]["tag"], p8[0]["n"]), ("연결", 3))
        self.assertEqual(n["sections"]["xinb"], {"2026Q3": []})
        # 멱등
        self.assertEqual(hdrmap.render_headers("kce", root=self.root, strict=True), text)
        self.assertEqual(_read(path), text)
        # 기존 회사의 새 분기는 그 회사 fq·절에만 더해진다(COMPANIES 순서 유지, 다른 16사 불변)
        self.rec("kce", "hec", "2026Q3", "orders", [{"cols": STD, "n": 62, "n_rec": 61, "ent": "현대건설", "tag": "현대건설"}], {0})
        hdrmap.write("kce", root=self.root, strict=True)
        D2, _, ORDER2, _, _ = hdrmap._parse_page(hdrmap.render_headers("kce", root=self.root, strict=True))
        self.assertEqual(ORDER2, ORDER1)
        self.assertEqual(D2["hec"]["fq"], D0["hec"]["fq"] + ["2026Q3"])
        self.assertEqual(D2["hec"]["sections"]["ii4"]["2026Q2"], D0["hec"]["sections"]["ii4"]["2026Q2"])
        self.assertEqual(D2["hec"]["sections"]["ii4"]["2026Q3"][0]["ent"], "현대건설")
        for co in ORDER0:
            if co != "hec":
                self.assertEqual(D2[co], D0[co], co)
        # 지도의 회사 순서를 호출측이 주면 그 순서(지도에 없는 키는 무시)
        D3, _, ORDER3, _, _ = hdrmap._parse_page(hdrmap.render_headers("kce", root=self.root, order=["newco", "hec", "없음"], write=False, strict=True))
        self.assertEqual(ORDER3, ["newco", "hec"])

    def test_render_keys_filter(self):
        """keys 를 주면 D·ORDER 를 그 회사로 제한한다 — 같은 kce 지도에서 정밀 17사 headers.html 과 lite 36사 headers_lite.html 을 따로 그린다
        (53사를 한 페이지에 넣으면 452KB→≈1MB 한 줄 블롭이 분기마다 통째 diff 된다)."""
        path, orig = self.kce_page()
        D0, _, ORDER0, _, _ = hdrmap._parse_page(orig)
        self.rec("kce", "lite1", "2026Q2", "orders", [{"cols": STD, "n": 5}], {0}, meta={"name": "라이트1", "stock": "777771"})
        self.rec("kce", "lite2", "2026Q2", "orders", [{"cols": STD, "n": 6}], {0}, meta={"name": "라이트2", "stock": "777772"})
        self.rec("kce", "hec", "2026Q3", "orders", [{"cols": STD, "n": 62, "ent": "현대건설"}], {0})
        hdrmap.write("kce", root=self.root, strict=True)
        lite = os.path.join(self.root, "kce", "headers_lite.html")
        text = hdrmap.render_headers("kce", out_html=lite, keys={"lite1", "lite2"}, root=self.root, strict=True)
        self.assertEqual(_read(lite), text)
        D, LAB, ORDER, s, e = hdrmap._parse_page(text)
        self.assertEqual((ORDER, set(D)), (["lite1", "lite2"], {"lite1", "lite2"}))
        self.assertEqual(LAB, hdrmap.KCE_LAB)
        self.assertEqual(D["lite1"]["sections"]["ii4"]["2026Q2"][0]["n"], 5)
        self.assertIn("const KEYS=Object.keys(LAB)", text)                          # 템플릿에서 만든 새 페이지
        self.assertEqual(_read(path), orig)                                         # 정밀 페이지는 건드리지 않았다
        # 정밀 페이지는 keys=17사 — 지도에만 있는 lite 회사가 섞여 들지 않는다(hec 새 분기만 더해진다)
        D1, _, ORDER1, _, _ = hdrmap._parse_page(hdrmap.render_headers("kce", out_html=path, keys=set(ORDER0), root=self.root, write=False, strict=True))
        self.assertEqual(ORDER1, ORDER0)
        self.assertEqual(D1["hec"]["fq"], D0["hec"]["fq"] + ["2026Q3"])
        for co in ORDER0:
            if co != "hec":
                self.assertEqual(D1[co], D0[co], co)
        # keys 는 페이지에 있던 다른 회사도 뺀다(부분집합 페이지) — 16사 / 1사
        D2, _, ORDER2, _, _ = hdrmap._parse_page(hdrmap.render_headers("kce", out_html=path, keys=set(ORDER0) - {"hec"}, root=self.root,
                                                                       write=False, strict=True))
        self.assertEqual(ORDER2, [k for k in ORDER0 if k != "hec"])
        self.assertNotIn("hec", D2)
        D3, _, ORDER3, _, _ = hdrmap._parse_page(hdrmap.render_headers("kce", out_html=path, keys={"hec"}, root=self.root, write=False, strict=True))
        self.assertEqual((ORDER3, set(D3)), (["hec"], {"hec"}))
        self.assertEqual(D3["hec"], D1["hec"])
        # 멱등
        self.assertEqual(hdrmap.render_headers("kce", out_html=lite, keys={"lite1", "lite2"}, root=self.root, strict=True), text)
        self.assertEqual(_read(lite), text)

    def test_render_new_tab_from_template(self):
        """kce 외 탭은 tools/assets/headers_tpl.html 에서 argus/<tab>/headers.html 을 만든다(멱등). JS 구간 규칙은 kce 와 같다."""
        meta = {"name": "한국항공우주", "stock": "047810"}
        for q, cols in KAI.items():
            self.rec("kdef", "047810", q, "orders", [{"cols": cols, "n": 6, "tag": "openclose", "ent": "parent", "shape": "openclose"}], {0}, meta=meta)
        self.rec("kdef", "047810", "2026Q2", "revenue", [{"cols": ["사업부문", "매출유형", "품목", "제27기 반기"], "n": 9}], {0}, meta=meta)
        self.rec("kdef", "047810", "2026Q2", "xi", [], (), meta=meta)
        hdrmap.write("kdef", root=self.root, strict=True)
        text = hdrmap.render_headers("kdef", root=self.root, labels={"title": "방산 파서헤드 지도"}, strict=True)
        path = os.path.join(self.root, "kdef", "headers.html")
        self.assertEqual(_read(path), text)
        self.assertNotIn("__TITLE__", text)
        self.assertIn("<title>방산 파서헤드 지도</title>", text)
        self.assertIn("<h1>방산 파서헤드 지도</h1>", text)
        self.assertIn("const KEYS=Object.keys(LAB)", text)
        D, LAB, ORDER, s, e = hdrmap._parse_page(text)
        self.assertEqual(ORDER, ["047810"])
        self.assertEqual(LAB, {"orders": ["수주", "수주상황표"], "revenue": ["매출", "매출실적"],
                               "xi": ["XI-1", "단일판매·공급계약 진행 현황", "trim"]})
        d = D["047810"]
        self.assertEqual((d["name"], d["fq"]), ("한국항공우주", ["2025Q4", "2026Q1", "2026Q2"]))
        self.assertEqual(set(d["sections"]), {"orders", "revenue", "xi"})
        self.assertEqual(d["sections"]["orders"]["2026Q2"][0]["ent"], "parent")
        self.assertEqual(d["sections"]["orders"]["2026Q2"][0]["tag"], "openclose")
        self.assertNotIn("ent", d["sections"]["revenue"]["2026Q2"][0])
        g = hdrmap.gseq(d["fq"], d["sections"]["orders"], "047810-orders")
        self.assertEqual(g, _js_gseq("047810", "orders", d, d["sections"]["orders"]))
        self.assertEqual(len(g), 3)                     # JS 구간은 원문 cols 기준 — 날짜가 바뀐 3분기는 3구간(마스킹은 대조용)
        self.assertEqual(hdrmap.render_headers("kdef", root=self.root, strict=True), text)
        # 두 번째 회사 추가 → ORDER 끝에 정렬되어 붙고 첫 회사 블롭 불변
        self.rec("kdef", "012450", "2026Q2", "orders", [{"cols": STD, "n": 3}], {0}, meta={"name": "한화에어로스페이스", "stock": "012450"})
        hdrmap.write("kdef", root=self.root, strict=True)
        D2, _, ORDER2, _, _ = hdrmap._parse_page(hdrmap.render_headers("kdef", root=self.root, strict=True))
        self.assertEqual(ORDER2, ["047810", "012450"])
        self.assertEqual(D2["047810"], d)

    def test_template_js_diff_allowlist(self):
        """템플릿 JS 는 kce headers.html L80-173 의 복제 — 비주석 줄 차이는 다섯 가지(KEYS·trim 2곳·빈 지도 가드·esc(LAB)·해시 가드)뿐.
        이 목록 밖의 차이가 생기면 '복제' 주장이 거짓이 된다(상류와 대조하는 다음 사람이 버그로 오해)."""
        tpl = _read(hdrmap.TEMPLATE).split("\n")
        kce = _read(HEADERS_HTML).split("\n")
        T = _js_lines(tpl, lambda l: l.startswith("const D={}, LAB={}, ORDER=[];"))
        K = _js_lines(kce, lambda l: len(l) > 2000 and l.lstrip().startswith("const D="))
        self.assertGreaterEqual(len(K), 60)
        tpl_only = [l for l in T if l not in K]
        kce_only = [l for l in K if l not in T]
        self.assertEqual(tpl_only, [
            "const KEYS=Object.keys(LAB);",
            "  if(!d){document.getElementById('out').innerHTML='<div class=\"sub\">지도에 기록된 회사가 없습니다.</div>';return;}",
            "  for(const key of KEYS){",
            "    out.push(`<h2>${esc(LAB[key][0])}<span>${esc(LAB[key][1])}</span></h2>`);",
            "    const trim=LAB[key][2]==='trim';",
            "    if(trim){",
            "    if(trim && fqs.length<d.fq.length)",
            "        +`${d.fq.indexOf(fqs[0])}개 분기는 이 절의 공시가 시작되기 전이라 뺐습니다.</div>`);",
            "  if(co && location.hash.slice(1)!==co) history.replaceState(null,'','#'+co);};",
        ])
        self.assertEqual(kce_only, [
            "  for(const key of ['ii4','p8','xinb']){",
            "    out.push(`<h2>${LAB[key][0]}<span>${LAB[key][1]}</span></h2>`);",
            "    if(key==='xinb'){",
            "    if(key==='xinb' && fqs.length<d.fq.length)",
            "        +`${d.fq.indexOf(fqs[0])}개 분기는 XI-1 공시가 시작되기 전이라 뺐습니다.</div>`);",
            "  if(location.hash.slice(1)!==co) history.replaceState(null,'','#'+co);};",
        ])
        # 구간 번호·대조 키 줄은 글자 그대로 같다
        for must in ("      const gk=(r.ent||'')+'|'+(r.tag||'')+'|'",
                     "        +r.cols.filter(c=>c&&c.trim()).map(c=>c.replace(/\\s+/g,'')).join('/');",
                     "        const k=kk+'#'+nth[kk];"):
            self.assertIn(must, T)
            self.assertIn(must, K)
        # 주석이 그 다섯 가지를 그대로 말한다(옛 '다른 점은 둘뿐' 은 거짓이었다)
        head = "\n".join(l for l in tpl if l.startswith("//"))
        for word in ("다섯 가지", "KEYS", "trim", "if(!d)", "esc()", "co &&", "test_template_js_diff_allowlist"):
            self.assertIn(word, head)
        self.assertNotIn("둘뿐", head)

    def test_kce_adapter_render_headers_html(self):
        """kce_render.render_headers_html 과 같은 시그니처: rep['headers']{ii4,p8,xinb} → 기록(스테이지)+스테이지 덧씌운 렌더(텍스트 반환).
        커밋은 commit_kce 가 따로 — pending 쓰기 전에는 지도·큐·파일 어느 것도 바뀌지 않는다(U2 계약)."""
        path, orig = self.kce_page()
        D0, _, ORDER0, _, _ = hdrmap._parse_page(orig)
        hdrmap.enqueue("kce", {"kind": "unknown", "key": "hec", "role": "orders", "quarter": "2026Q2", "cols": STD}, root=self.root)
        headers = {
            "ii4": [{"cols": STD, "n": 62, "n_rec": 61, "lead": "1) 현대건설", "ent": "현대건설", "tag": "현대건설", "rcpNo": "r1"},
                    {"cols": ["구분", "수주잔고"], "n": 3, "lead": "요약", "pick": False, "reason": "dup_section"}],
            "p8": [{"cols": ["공사명", "수주총액", "진행률", "미청구공사 총액", "공사미수금 총액"], "n": 40, "basis": "연결", "lead": "(1) 연결기준"},
                   {"cols": ["공사명", "수주총액", "진행률", "미청구공사 총액", "공사미수금 총액"], "n": 35, "basis": None, "lead": ""}],
            "xinb": [{"cols": ["신고일자", "계약내역", "계약금액총액(원)"], "n": 10, "lead": "나. 진행현황"}],
        }
        text = hdrmap.render_headers_html(path, "hec", "2026Q3", headers, root=self.root)
        self.assertEqual(_read(path), orig)                                     # 어댑터는 파일을 쓰지 않는다(kce_render 와 같다)
        self.assertFalse(os.path.exists(hdrmap.map_path("kce", self.root)))     # 지도 미커밋
        self.assertIsNotNone(hdrmap.staged("kce", "hec"))                       # 스테이지 보존
        self.assertEqual([i["status"] for i in hdrmap.load_queue("kce", root=self.root)], ["open"])   # 큐도 그대로
        D, LAB, ORDER, s, e = hdrmap._parse_page(text)
        self.assertEqual(ORDER, ORDER0)
        self.assertEqual(D["hec"]["fq"], D0["hec"]["fq"] + ["2026Q3"])
        ii4 = D["hec"]["sections"]["ii4"]["2026Q3"]
        self.assertEqual([(r["pick"], r["ent"], r["tag"], r["n"]) for r in ii4], [(True, "현대건설", "현대건설", 62), (False, "", "", 3)])
        self.assertEqual([(r["tag"], r["n"]) for r in D["hec"]["sections"]["p8"]["2026Q3"]], [("연결", 40), ("", 35)])
        self.assertEqual([(r["tag"], r["pick"]) for r in D["hec"]["sections"]["xinb"]["2026Q3"]], [("나", True)])
        for co in ORDER0:
            if co != "hec":
                self.assertEqual(D[co], D0[co], co)
        # 디스크만 보는 렌더(stage=False)는 원본 그대로 — 스테이지 덧씌움이 그 차이다
        self.assertEqual(hdrmap.render_headers("kce", out_html=path, root=self.root, write=False, strict=True, stage=False), orig)
        # pending 실패 → discard: 지도·큐·페이지 어디에도 흔적 0
        hdrmap.discard("kce", "hec")
        self.assertEqual(hdrmap.render_headers("kce", out_html=path, root=self.root, write=False, strict=True), orig)
        self.assertFalse(os.path.exists(hdrmap.map_path("kce", self.root)))
        # pending 성공 → commit_kce: 지도 커밋·스테이지 비움·큐 resolved. 커밋 뒤 렌더 == 어댑터가 돌려준 텍스트(바이트 동일)
        self.assertEqual(hdrmap.render_headers_html(path, "hec", "2026Q3", headers, root=self.root), text)
        r = hdrmap.commit_kce("hec", root=self.root)
        self.assertEqual((r["companies"], r["quarters"], r["resolved"]), (1, 3, 1))
        self.assertIsNone(hdrmap.staged("kce", "hec"))
        self.assertEqual(hdrmap.render_headers("kce", out_html=path, root=self.root, write=False, strict=True), text)
        it = hdrmap.load_queue("kce", root=self.root)[0]
        self.assertEqual((it["status"], it["resolved_in"]), ("resolved", "2026Q3"))
        M = hdrmap.load_map("kce", root=self.root)
        o = M["companies"]["hec"]["roles"]["orders"]["2026Q3"]
        self.assertEqual([(x["pick"], x["reason"], x["n_rec"]) for x in o], [(True, "picked", 61), (False, "dup_section", None)])
        self.assertEqual(o[0]["rcpNo"], "r1")
        self.assertEqual(M["companies"]["hec"]["roles"]["progress"]["2026Q3"][0]["basis"], "연결")
        self.assertEqual(M["companies"]["hec"]["roles"]["xi"]["2026Q3"][0]["tag"], "나")
        # 어댑터는 자기 회사 스테이지만 덧씌운다 — 다른 회사의 미커밋 스테이지는 그리지 않는다
        self.rec("kce", "sct", "2026Q3", "orders", [{"cols": STD, "n": 9, "ent": "삼성물산"}], {0})
        t2 = hdrmap.render_headers_html(path, "dwe", "2026Q3", {"ii4": [{"cols": STD, "n": 7, "ent": "대우건설"}]}, root=self.root)
        D2 = hdrmap._parse_page(t2)[0]
        self.assertEqual(D2["sct"], D0["sct"])
        self.assertEqual(D2["dwe"]["fq"], D0["dwe"]["fq"] + ["2026Q3"])
        hdrmap.discard("kce")
        # 절 키가 없으면(xinb 미수집) 그 역할은 기록하지 않는다 — 빈 리스트와 구분
        hdrmap.render_headers_html(path, "sct", "2026Q3", {"ii4": [], "p8": []}, root=self.root)
        self.assertEqual(sorted(hdrmap.staged("kce", "sct")["roles"]), ["orders", "progress"])
        hdrmap.commit_kce("sct", root=self.root)
        self.assertEqual(sorted(hdrmap.load_map("kce", root=self.root)["companies"]["sct"]["roles"]), ["orders", "progress"])
        # 어댑터는 엄격 모드 — 깨진 입력은 raise(apply 경로 fail-closed)
        with self.assertRaises(hdrmap.HdrmapError):
            hdrmap.render_headers_html(path, "hec", "26Q3", headers, root=self.root)


class TestCheckOnboard(_Base):

    def test_check_regression_only(self):
        """exit 1 은 회귀만 — 직전 분기 clean 이던 (key, role) 이 현 분기에 채택 표 없이 open 미지, critical 회사의 수주표 채택 소실."""
        self.rec("kce", "001260", "2026Q1", "orders", [{"cols": STD, "n": 5}], {0}, meta={"name": "남광토건", "stock": "001260"})
        self.rec("kce", "001260", "2026Q2", "orders", [], (), unknown=[{"cols": EWHA, "n": 5}], meta={"name": "남광토건", "stock": "001260"})
        self.rec("kce", "999999", "2026Q2", "orders", [], (), unknown=[{"cols": EWHA, "n": 5}], meta={"name": "새회사", "stock": "999999"})
        hdrmap.onboard("kce", {"001260"}, [{"stock": "888888", "name": "미기록 신규"}], q="2026Q2", root=self.root, strict=True)
        hdrmap.write("kce", root=self.root, strict=True)
        rep = hdrmap.check("kce", root=self.root)
        self.assertEqual(rep["exit"], 1)
        self.assertEqual([(r["key"], r["role"], r["quarter"], r["prev_clean"], r["kind"]) for r in rep["regressions"]],
                         [("001260", "orders", "2026Q2", "2026Q1", "unknown")])
        self.assertEqual((rep["open"], rep["new_company_open"]), (3, 1))
        self.assertEqual(rep["open_by_kind"], {"new_company": 1, "unknown": 2})
        # 회귀가 없으면(신규사 open·첫 분기 미지만) exit 0 — 신규사는 경고
        hdrmap.discard("kce")
        root2 = os.path.join(self.root, "r2")
        self.rec("kce", "999999", "2026Q2", "orders", [], (), unknown=[{"cols": EWHA, "n": 5}], root=root2)
        hdrmap.onboard("kce", set(), [{"stock": "888888", "name": "신규"}], q="2026Q2", root=root2, strict=True)
        hdrmap.write("kce", root=root2, strict=True)
        rep = hdrmap.check("kce", root=root2)
        self.assertEqual((rep["exit"], rep["regressions"], rep["open"], rep["new_company_open"]), (0, [], 2, 1))
        # critical 회사의 수주표 채택 소실(미지 없이 조용히 pick 0) 도 회귀
        root3 = os.path.join(self.root, "r3")
        self.rec("kce", "hec", "2026Q1", "orders", [{"cols": STD, "n": 5}], {0}, root=root3)
        self.rec("kce", "hec", "2026Q2", "orders", [{"cols": ["구분", "매출액"], "n": 5}], (), root=root3)
        hdrmap.write("kce", root=root3, strict=True)
        self.assertEqual(hdrmap.check("kce", root=root3)["exit"], 0)
        rep = hdrmap.check("kce", critical=["hec", "sct"], root=root3)
        self.assertEqual(rep["exit"], 1)
        self.assertEqual([(r["key"], r["kind"], r["prev_clean"]) for r in rep["regressions"]], [("hec", "lost_pick", "2026Q1")])
        # 현 분기에 채택 표가 살아 있는 미지표(채택 + 근접 미지 — 이화공영 꼴, advisory 탭의 kdef KAI 5장·대한항공 추가표)는
        # 회귀가 아니다: exit 0, open 은 집계. kce 정밀은 unknown 시 raise+discard 라 현 분기 항목이 없어 위처럼 회귀로 잡힌다.
        root4 = os.path.join(self.root, "r4")
        self.rec("kdef", "003490", "2026Q1", "orders", [{"cols": STD, "n": 5}], {0}, root=root4, meta={"name": "대한항공", "stock": "003490"})
        self.rec("kdef", "003490", "2026Q2", "orders", [{"cols": STD, "n": 5}], {0}, unknown=[{"cols": EWHA, "n": 5}], root=root4,
                 meta={"name": "대한항공", "stock": "003490"})
        hdrmap.write("kdef", root=root4, strict=True)
        rep = hdrmap.check("kdef", root=root4)
        self.assertEqual((rep["exit"], rep["regressions"], rep["open"], rep["open_by_kind"]), (0, [], 1, {"unknown": 1}))
        # 그 채택이 다음 분기에 사라지고 미지만 남으면 그때는 회귀
        self.rec("kdef", "003490", "2026Q3", "orders", [], (), unknown=[{"cols": EWHA, "n": 5}], root=root4,
                 meta={"name": "대한항공", "stock": "003490"})
        hdrmap.write("kdef", root=root4, strict=True)
        rep = hdrmap.check("kdef", root=root4)
        self.assertEqual((rep["exit"], [(r["quarter"], r["prev_clean"]) for r in rep["regressions"]]), (1, [("2026Q3", "2026Q2")]))
        # 빈 지도·빈 큐
        self.assertEqual(hdrmap.check("kce", root=os.path.join(self.root, "empty"))["exit"], 0)

    def test_onboard_new_company(self):
        """universe 저장 직전: 직전에 없던 stock 만 new_company 로. 멱등. 그 회사가 기록되면 write 가 닫는다."""
        rows = [{"stock": "000720", "name": "현대건설"}, {"stock": "999999", "name": "새회사"}, {"stock": None, "name": "비상장"}]
        new = hdrmap.onboard("kce", {"000720"}, rows, q="2026Q2", root=self.root, strict=True)
        self.assertEqual([r["stock"] for r in new], ["999999"])
        new = hdrmap.onboard("kce", {"000720"}, rows, q="2026Q2", root=self.root, strict=True)
        self.assertEqual([r["stock"] for r in new], ["999999"])
        items = hdrmap.load_queue("kce", root=self.root)
        self.assertEqual([(i["kind"], i["key"], i["stock"], i["name"], i["role"], i["status"], i["grade"], i["quarter_first"]) for i in items],
                         [("new_company", "999999", "999999", "새회사", "*", "open", "B", "2026Q2")])
        self.assertEqual(hdrmap.onboard("kce", {"000720", "999999"}, rows, q="2026Q3", root=self.root, strict=True), [])
        # 슬러그 키를 쓰는 탭은 key 를 따로 준다
        hdrmap.onboard("kce", set(), [{"stock": "000720", "name": "현대건설", "key": "hec"}], q="2026Q2", root=self.root, strict=True)
        self.assertIn("hec", [i["key"] for i in hdrmap.load_queue("kce", root=self.root)])
        # 기록·커밋되면 new_company 가 닫힌다
        self.rec("kce", "999999", "2026Q2", "orders", [{"cols": STD, "n": 5}], {0}, meta={"name": "새회사", "stock": "999999"})
        r = hdrmap.write("kce", root=self.root, strict=True)
        self.assertEqual(r["resolved"], 1)
        it = [i for i in hdrmap.load_queue("kce", root=self.root) if i["key"] == "999999"][0]
        self.assertEqual((it["status"], it["resolved_in"]), ("resolved", "2026Q2"))

    def test_replay_cache(self):
        """캐시 재생: 항목 하나가 깨져도 멈추지 않고(engine_error 큐) 나머지를 기록·커밋한다."""
        loader = iter([
            {"key": "001260", "q": "2026Q1", "role": "orders", "tables": [{"cols": STD, "n": 5}], "picks": [0], "meta": {"name": "남광토건", "stock": "001260"}},
            {"key": "001260", "q": "2026Q2", "role": "bogus", "tables": []},
            {"key": "001260", "q": "2026Q2", "role": "orders", "tables": [{"cols": STD, "n": 6}], "picks": [0]},
        ])
        with redirect_stderr(io.StringIO()) as err:
            rep = hdrmap.replay_cache("kce", loader, root=self.root)
        self.assertEqual((rep["records"], rep["errors"], rep["companies"], rep["quarters"]), (2, 1, 1, 2))
        self.assertIn("replay", err.getvalue())
        M = hdrmap.load_map("kce", root=self.root)
        self.assertEqual(M["companies"]["001260"]["fq"], ["2026Q1", "2026Q2"])
        self.assertEqual(M["companies"]["001260"]["name"], "남광토건")
        q = hdrmap.load_queue("kce", root=self.root)
        self.assertEqual([(i["kind"], i["key"], i["role"]) for i in q], [("engine_error", "001260", "bogus")])
        self.assertEqual(hdrmap.diff_prev("kce", "001260", "orders", "2026Q2", root=self.root, strict=True), [])

    def test_cli_drop_leaves_page(self):
        """--drop 은 지도(hdrmap.json)만 지운다 — headers.html 의 그 분기는 --render 를 붙여도 남으므로 페이지는 git revert 로
        되돌린다(설계 G 의 두 단계). 도움말이 그 사실을 말한다. --root 로 임시 트리를 다룬다."""
        path, orig = self.kce_page()
        self.rec("kce", "hec", "2026Q3", "orders", [{"cols": STD, "n": 5, "ent": "현대건설"}], {0})
        hdrmap.write("kce", root=self.root, strict=True)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(hdrmap.main(["--tab", "kce", "--root", self.root, "--render"]), 0)
        self.assertIn("2026Q3", hdrmap._parse_page(_read(path))[0]["hec"]["fq"])
        with redirect_stdout(out):
            self.assertEqual(hdrmap.main(["--tab", "kce", "--root", self.root, "--drop", "hec:orders:2026Q3", "--render", "--check"]), 0)
        M = hdrmap.load_map("kce", root=self.root)
        self.assertNotIn("2026Q3", M["companies"]["hec"]["roles"]["orders"])
        self.assertEqual(M["companies"]["hec"]["fq"], [])
        self.assertIn("2026Q3", hdrmap._parse_page(_read(path))[0]["hec"]["fq"])         # 페이지에는 남는다(지도만 지움)
        self.assertIn("git revert", out.getvalue())
        self.assertIn("rendered", out.getvalue())
        # 도움말
        h = io.StringIO()
        with redirect_stdout(h), self.assertRaises(SystemExit):
            hdrmap.main(["--help"])
        self.assertIn("revert", h.getvalue())                 # argparse 가 줄을 접어도 낱말은 남는다
        self.assertIn("--root", h.getvalue())
        self.assertIn("git revert", _read(hdrmap.__file__))      # --drop 도움말 원문(접히기 전)
        # 없는 회사 → 2 ; 회사 전체 drop 은 압축·정규화 경로(_save_map)로 쓴다
        with redirect_stderr(io.StringIO()):
            self.assertEqual(hdrmap.main(["--tab", "kce", "--root", self.root, "--drop", "nope"]), 2)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(hdrmap.main(["--tab", "kce", "--root", self.root, "--drop", "hec"]), 0)
        t = _read(hdrmap.map_path("kce", self.root))
        self.assertEqual(json.loads(t)["companies"], {})
        self.assertEqual(t, json.dumps(json.loads(t), ensure_ascii=False, sort_keys=True, indent=1) + "\n")


if __name__ == "__main__":
    unittest.main()
