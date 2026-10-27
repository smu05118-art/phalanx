#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""duksan_dart 오프라인 계약 테스트 — 네트워크를 절대 쓰지 않는다.

fixtures/ 는 덕산하이메탈 2026 1분기보고서(20260515000596)·2026 반기보고서(20260813001579)의
II-2·II-3·II-4 절 원문(DART 뷰어 HTML 그대로)이다. 기대값은 원문 표와 2026 2Q IR 자료로 손으로 맞춘 값이다.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import duksan_dart as D  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
Q1, H1 = "20260515000596", "20260813001579"


def htmls(rcp):
    out = {}
    for k in ("ii2", "ii3", "ii4"):
        with open(os.path.join(FIX, "sec_%s_%s.html" % (rcp, k)), encoding="utf-8") as f:
            out[k] = f.read()
    return out


def himetal(rows, key="product_sales"):
    return [r for r in rows[key] if r["scope"] == "하이메탈 부문"]


class NoNetwork(object):
    """search/toc/fetch 를 막는다. 호출되면 실패시킨다."""

    def __enter__(self):
        self.saved = (D.search_reports, D.toc, D.fetch_section)

        def boom(*a, **k):
            raise AssertionError("테스트가 네트워크를 쓰려 했다")
        D.search_reports, D.toc, D.fetch_section = boom, boom, boom
        return self

    def __exit__(self, *exc):
        D.search_reports, D.toc, D.fetch_section = self.saved


class ParseTests(unittest.TestCase):
    def test_product_sales_amount_share_scope(self):
        res = D.parse_report(htmls(H1), "2026-H1", H1)
        hm = himetal(res)
        self.assertEqual(len(hm), 1)
        self.assertEqual(hm[0]["amount"], 100342)            # 100,342(62.93%) 한 칸 분리
        self.assertEqual(hm[0]["unit"], "백만원")
        self.assertAlmostEqual(hm[0]["share_pct"], 62.93)
        total = [r for r in res["product_sales"] if r["total"]]
        self.assertEqual(total[0]["amount"], 159454)
        self.assertEqual(total[0]["scope"], "연결")
        # 자회사(방산·가스용기)는 하이메탈 부문으로 섞이지 않는다
        self.assertFalse(any("넵코어스" in " ".join(r["labels"]) for r in hm))

    def test_capacity_output_and_utilization(self):
        res = D.parse_report(htmls(H1), "2026-H1", H1)
        hm = himetal(res, "capacity")
        self.assertEqual(len(hm), 1)
        self.assertEqual(hm[0]["output"], 84705)
        self.assertEqual(hm[0]["unit"], "백만원")
        self.assertEqual(hm[0]["output_basis"], "제조원가 금액 기준")
        self.assertAlmostEqual(hm[0]["utilization_pct"], 87.6)
        self.assertEqual(hm[0]["util_detail"]["가동가능시간"], 99912)
        self.assertEqual(hm[0]["util_detail"]["실제가동시간"], 87510)

    def test_sales_export_domestic(self):
        res = D.parse_report(htmls(H1), "2026-H1", H1)
        rows = [r for tb in res["sales"][0]["tables"] for r in tb["rows"] if r["scope"] == "하이메탈 부문"]
        by = {r["channel"]: r for r in rows}
        p = res["sales"][0]["tables"][0]["periods"][0]
        self.assertAlmostEqual(by["exp"]["vals"][p], 89254.504)
        self.assertAlmostEqual(by["dom"]["vals"][p], 11087.247)
        self.assertAlmostEqual(by["tot"]["vals"][p], 100341.751)

    def test_no_table_sections_become_quoted_notes(self):
        res = D.parse_report(htmls(H1), "2026-H1", H1)
        self.assertEqual(res["prices"], [])                  # 가격변동은 서술뿐 — 지어내지 않는다
        kinds = {n["kind"] for n in res["notes"]}
        self.assertTrue({"가격변동추이", "생산능력"} <= kinds)
        self.assertEqual(res["issues"], [])


class QuarterlyTests(unittest.TestCase):
    def data_for(self, *pairs):
        data = {k: [] for k in D.ROW_KEYS}
        for rcp, period in pairs:
            res = D.parse_report(htmls(rcp), period, rcp)
            for k in D.ROW_KEYS:
                data[k].extend(res[k])
        return data

    def test_decumulate_matches_ir(self):
        q = {r["quarter"]: r for r in D.quarterly(self.data_for((Q1, "2026-Q1"), (H1, "2026-H1")))}
        self.assertEqual(q["2026Q1"]["revenue"], 42632)      # IR 26.1Q 426억
        self.assertEqual(q["2026Q2"]["revenue"], 57710)      # IR 26.2Q 577억
        self.assertEqual(q["2026Q2"]["basis"], "누계 차분")
        self.assertAlmostEqual(q["2026Q2"]["util_pct"], 80.1)  # (87,510−47,255)/(99,912−49,680)
        self.assertEqual(q["2026Q2"]["avail_hours"], 50232)

    def test_missing_prior_cumulative_is_skipped(self):
        q = D.quarterly(self.data_for((H1, "2026-H1")))
        self.assertEqual(q, [])                              # 1분기 누계가 없으면 2분기를 추정하지 않는다


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_fail_closed_on_empty(self):
        data = {k: [] for k in D.ROW_KEYS}
        with self.assertRaises(SystemExit):
            D.write_output(self.root, data, None)
        self.assertFalse(os.path.exists(os.path.join(self.root, D.REL_OUT)))

    def test_dumps_deterministic_and_generated_ignored(self):
        a = {"generated": "x", "b": [2, 1], "a": {"z": 1, "y": "가"}}
        b = dict(a, generated="y")
        self.assertEqual(D.dumps(a), D.dumps(json.loads(D.dumps(a))))
        self.assertTrue(D.same_content(a, b))
        self.assertTrue(D.dumps(a).endswith("\n"))

    def test_build_reparses_cache_without_network(self):
        cache = os.path.join(self.root, D.REL_CACHE)
        os.makedirs(cache)
        for name in os.listdir(FIX):
            shutil.copy(os.path.join(FIX, name), cache)
        prev = {"reports": [{"rcp_no": Q1, "period": "2026-Q1", "title": "분기보고서 (2026.03)", "filed": "2026-05-15"},
                            {"rcp_no": H1, "period": "2026-H1", "title": "반기보고서 (2026.06)", "filed": "2026-08-13"}],
                "product_sales": [{"source_rcp": Q1}]}
        out = os.path.join(self.root, D.REL_OUT)
        os.makedirs(os.path.dirname(out))
        with open(out, "w", encoding="utf-8") as f:
            json.dump(prev, f)
        with NoNetwork():
            data, fetched, _ = D.build(self.root, quarters=["2026Q1", "2026Q2"], log=lambda s: None)
        self.assertEqual(fetched, 0)
        self.assertEqual([r["period"] for r in data["reports"]], ["2026-H1", "2026-Q1"])
        self.assertEqual({r["quarter"] for r in data["quarterly"]}, {"2026Q1", "2026Q2"})
        self.assertTrue(D.write_output(self.root, data, prev))
        with open(out, encoding="utf-8") as f:
            written = json.load(f)
        self.assertNotIn("_failures", written)               # 내부 키는 기록하지 않는다
        self.assertEqual(D.dumps(written), D.dumps({k: v for k, v in data.items() if not k.startswith("_")}))

    def test_unfiled_quarter_is_recorded_not_invented(self):
        with NoNetwork():                                    # toc/fetch 는 막힌 채로, 검색만 빈 결과
            D.search_reports = lambda *a, **k: []
            data, fetched, _ = D.build(self.root, quarters=["2026Q3"], log=lambda s: None)
        self.assertEqual(fetched, 0)
        self.assertEqual(data["reports"], [])
        self.assertIn("2026-Q3: 정기보고서 검색 결과 없음(미공시)", data["issues"])


class ReviewRegressionTests(unittest.TestCase):
    """2026-10-27 3관점 리뷰가 재현한 결함들의 회귀 방지."""
    Q1_24 = "20240513000087"

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_2024_format_parses(self):
        res = D.parse_report(htmls(self.Q1_24), "2024-Q1", self.Q1_24)
        self.assertEqual(himetal(res)[0]["amount"], 23206)   # IR 24.1Q 별도와 같은 값
        cap = himetal(res, "capacity")[0]
        self.assertEqual(cap["output"], 19459)
        self.assertAlmostEqual(cap["utilization_pct"], 82.6)
        q = D.quarterly({k: res[k] for k in D.ROW_KEYS})
        self.assertAlmostEqual(q[0]["export"], 19909.67)
        self.assertAlmostEqual(q[0]["domestic"], 3296.426)

    def test_capacity_uses_current_column_only(self):
        # 2025-Q1 원문: `DS MYANMAR | - | 8,628 | 40,019` — 당기 '-' 를 전기 값으로 메우지 않는다
        with open(os.path.join(FIX, "sec_20250515001976_ii3.html"), encoding="utf-8") as f:
            rows = D.capacity(f.read(), "2025-Q1", "20250515001976")
        mm = [r for r in rows if "MYANMAR" in r["item"]]
        self.assertTrue(mm)
        self.assertTrue(all(r["output"] is None for r in mm))
        self.assertFalse(any(r["item"].startswith(("주", "※")) for r in rows))   # 각주 줄 제외

    def test_scope_injection_does_not_leak_subsidiaries(self):
        h = htmls(H1)
        h["ii4"] = h["ii4"].replace("가. 매출실적", "가. 매출실적(반도체 소재 사업 포함)")
        data = {k: [] for k in D.ROW_KEYS}
        for rcp, period, hh in ((Q1, "2026-Q1", htmls(Q1)), (H1, "2026-H1", h)):
            res = D.parse_report(hh, period, rcp)
            for k in D.ROW_KEYS:
                data[k].extend(res[k])
        q = {r["quarter"]: r for r in D.quarterly(data)}
        self.assertAlmostEqual(q["2026Q2"]["export"], 50610.977)
        self.assertAlmostEqual(q["2026Q2"]["domestic"], 7098.479)

    def build_full(self):
        """두 보고서 캐시로 정상 결과를 한 번 기록한다."""
        cache = os.path.join(self.root, D.REL_CACHE)
        os.makedirs(cache)
        for name in os.listdir(FIX):
            if name.startswith(("sec_%s_" % Q1, "sec_%s_" % H1)):
                shutil.copy(os.path.join(FIX, name), cache)
        out = os.path.join(self.root, D.REL_OUT)
        os.makedirs(os.path.dirname(out))
        seed = {"reports": [{"rcp_no": Q1, "period": "2026-Q1", "title": "분기보고서 (2026.03)", "filed": "2026-05-15"},
                            {"rcp_no": H1, "period": "2026-H1", "title": "반기보고서 (2026.06)", "filed": "2026-08-13"}]}
        with open(out, "w", encoding="utf-8") as f:
            json.dump(seed, f)
        with NoNetwork():
            data, _, prev = D.build(self.root, quarters=["2026Q1", "2026Q2"], log=lambda s: None)
        D.write_output(self.root, data, prev)
        return out

    def test_broken_cache_keeps_previous_rows(self):
        out = self.build_full()
        with open(out, encoding="utf-8") as f:
            good = json.load(f)
        for k in ("ii2", "ii3", "ii4"):                       # 1분기 원문을 깨뜨린다
            with open(os.path.join(self.root, D.REL_CACHE, "sec_%s_%s.html" % (Q1, k)), "w") as f:
                f.write("<html>broken</html>")
        with NoNetwork():
            data, _, prev = D.build(self.root, quarters=["2026Q1", "2026Q2"], log=lambda s: None)
        self.assertEqual([r["period"] for r in data["reports"]], ["2026-H1", "2026-Q1"])
        self.assertEqual({r["quarter"] for r in data["quarterly"]}, {"2026Q1", "2026Q2"})
        self.assertEqual(len(D.quarterly(data)), len(good["quarterly"]))

    def test_shrink_and_failure_refuse_to_write(self):
        out = self.build_full()
        with open(out, encoding="utf-8") as f:
            before = f.read()
        prev = json.loads(before)
        smaller = dict(prev, reports=prev["reports"][:1], quarterly=prev["quarterly"][:1])
        with self.assertRaises(SystemExit):
            D.write_output(self.root, smaller, prev)
        failed = dict(prev, _failures=["2026-Q3: 수집 실패 RuntimeError: blocked"])
        with self.assertRaises(SystemExit):
            D.write_output(self.root, failed, prev)
        with open(out, encoding="utf-8") as f:
            self.assertEqual(f.read(), before)


class TocTests(unittest.TestCase):
    def test_pick_nodes(self):
        nodes = [{"text": "II. 사업의 내용"}, {"text": "1. 사업의 개요"}, {"text": "2. 주요 제품 및 서비스"},
                 {"text": "3. 원재료 및 생산설비"}, {"text": "4. 매출 및 수주상황"}]
        got = D.pick_nodes(nodes)
        self.assertEqual(got["ii2"]["text"], "2. 주요 제품 및 서비스")
        self.assertEqual(got["ii3"]["text"], "3. 원재료 및 생산설비")
        self.assertEqual(got["ii4"]["text"], "4. 매출 및 수주상황")
        self.assertEqual(got[D.CHAPTER_KEY]["text"], "II. 사업의 내용")


if __name__ == "__main__":
    unittest.main()
