# -*- coding: utf-8 -*-
"""kship_scan — 후보 풀·승격 규칙은 순수 함수라 DART 없이 검증한다."""
import datetime
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kship_scan as S  # noqa: E402


class TestPool(unittest.TestCase):
    def test_pool_filters_by_product_and_industry(self):
        recs = [
            {"stock": "187790", "name": "나노", "industry": "기초 화학물질 제조업", "product": "SCR촉매"},          # EXTRA
            {"stock": "044490", "name": "태웅", "industry": "기타 금속 가공제품 제조업", "product": "자유형단조품"},  # 어휘 '단조'
            {"stock": "090080", "name": "평화산업", "industry": "자동차 신품 부품 제조업", "product": "호스류"},     # 업종 제외
            {"stock": "064820", "name": "케이프", "industry": "선박 및 보트 건조업", "product": "실린더라이너"},     # 이미 모집단
            {"stock": "000001", "name": "무관", "industry": "특수 목적용 기계 제조업", "product": "공작기계"},
        ]
        got = {r["stock"] for r in S.pool(recs, [{"stock": "064820"}])}
        self.assertEqual(got, {"187790", "044490"})

    def test_promotion_rule_is_fail_closed(self):
        J = S.judge
        self.assertTrue(J({"ok": True, "industry": "일반 목적용 기계 제조업", "mentions": {"042660": 3}, "hits": 6}))
        self.assertTrue(J({"ok": True, "industry": "기초 화학물질 제조업", "mentions": {}, "hits": 10}))          # 나노
        self.assertTrue(J({"ok": True, "industry": "전동기 제조업", "mentions": {"010140": 3, "097230": 1}, "hits": 3}))  # 서호전기
        self.assertFalse(J({"ok": True, "industry": "전동기 제조업", "mentions": {"042660": 2}, "hits": 0}))    # 효성重 — 언급뿐
        self.assertFalse(J({"ok": True, "industry": "전동기 제조업", "mentions": {"329180": 1, "KSOE_GRP": 1}, "hits": 1}))
        self.assertFalse(J({"ok": True, "industry": "연료용 가스 제조 및 배관공급업", "mentions": {"010140": 2}, "hits": 7}))  # 가스공사=고객
        self.assertFalse(J({"ok": True, "industry": "일반 목적용 기계 제조업", "mentions": {"329180": 1}, "hits": 4}))   # 디케이락 근접
        self.assertFalse(J({"ok": False, "industry": "일반 목적용 기계 제조업", "mentions": {"329180": 9}, "hits": 99}))  # II 절 못 읽음

    def test_role_for(self):
        self.assertEqual(S.role_for({"industry": "1차 철강 제조업", "product": "후판"}, {}), "steel")
        self.assertEqual(S.role_for({"industry": "일반 목적용 기계 제조업", "product": "선박용 엔진"}, {"marine_terms": {"박용": 3}}), "engine")
        self.assertEqual(S.role_for({"industry": "기초 화학물질 제조업", "product": "SCR촉매"}, {"marine_terms": {"선박": 9}}), "equip")


# 직전 스캔의 승격 증거(f650a100, 2026-09-11 판의 두 행을 그대로 — 재판정 규칙으로도 승격이다)
_PREV = {
    "187790": {"stock": "187790", "name": "나노", "industry": "기초 화학물질 제조업", "product": "SCR촉매", "hits": 10,
               "terms": {"선박": 10}, "mentions": {}, "rcp": "20260814001571", "note": "", "role": "equip",
               "reason": "탐색 — 정기보고서 본문: 조선 낱말 10회(선박 10) · 나노 — 선박용 SCR 탈질촉매"},
    "065710": {"stock": "065710", "name": "서호전기", "industry": "전동기, 발전기 및 전기 변환 · 공급 · 제어 장치 제조업", "product": "크레인 제어시스템",
               "hits": 3, "terms": {"조선소": 2, "선박": 1}, "mentions": {"010140": 3, "HSHI": 1, "097230": 1}, "rcp": "20260814000574",
               "note": "", "role": "equip", "reason": "탐색 — 정기보고서 본문: 조선 낱말 3회(조선소 2, 선박 1) · 조선사 언급 {...}"},
}


class TestCarryForward(unittest.TestCase):
    """2026-09-12 회귀: 승격 16사가 universe.json 에 '탐색' 행으로 들어가 다음 스캔의 후보 풀(모집단 제외)에서 빠지자
    promoted 가 {} 로 덮여 kship_universe --write 가 16행을 지웠다(57→41). 이월은 순수 함수 carry_forward 가 맡는다."""

    def test_pool_shrink_keeps_promoted(self):
        # 이번 스캔은 두 종목 모두 후보에 없었다(이미 모집단) — 새 promoted 는 빈 사전. 그대로 이월돼야 한다.
        promoted, carried = S.carry_forward(_PREV, {}, [], "2026-09-11")
        self.assertEqual(set(promoted), set(_PREV))
        self.assertEqual(carried, sorted(_PREV))
        for st, row in promoted.items():
            self.assertEqual(row["carried_from"], "2026-09-11")
            for k in ("hits", "terms", "mentions", "rcp", "role", "reason"):        # 증거는 그대로
                self.assertEqual(row[k], _PREV[st][k], k)
        self.assertEqual(list(promoted), sorted(promoted))                            # 종목코드 순 — 결정론

    def test_explicit_rejection_demotes(self):
        # 본문을 읽고(ok=True) 규칙에 못 미쳤다 — 이것만 강등이다.
        rejected = [{"stock": "065710", "ok": True, "hits": 1, "mentions": {}}]
        promoted, carried = S.carry_forward(_PREV, {}, rejected, "2026-09-11")
        self.assertNotIn("065710", promoted)
        self.assertIn("187790", promoted)
        self.assertEqual(carried, ["187790"])

    def test_fetch_failure_is_not_demotion(self):
        # ok=False(II 절을 못 읽음)로 rejected 에 실렸더라도 강등 근거가 아니다 — 직전 증거 유지.
        rejected = [{"stock": "065710", "ok": False, "hits": 0, "mentions": {}, "note": "II 절을 찾지 못함"}]
        promoted, carried = S.carry_forward(_PREV, {}, rejected, "2026-09-11")
        self.assertIn("065710", promoted)
        self.assertEqual(promoted["065710"]["hits"], 3)
        self.assertEqual(carried, ["065710", "187790"])

    def test_fresh_promotion_replaces_carried(self):
        new = {"187790": dict(_PREV["187790"], hits=12, rcp="20261114000001")}
        promoted, carried = S.carry_forward(_PREV, new, [], "2026-09-11")
        self.assertEqual(promoted["187790"]["hits"], 12)
        self.assertNotIn("carried_from", promoted["187790"])                          # 새 증거 — 이월 표식 없음
        self.assertEqual(carried, ["065710"])

    def test_already_carried_keeps_original_scan_date(self):
        prev = {"187790": dict(_PREV["187790"], carried_from="2026-09-11")}
        promoted, _ = S.carry_forward(prev, {}, [], "2026-09-19")
        self.assertEqual(promoted["187790"]["carried_from"], "2026-09-11")


class TestScanWiring(unittest.TestCase):
    """scan() 전체를 DART 없이 — KIND 응답·수집·자산 읽기/쓰기·sleep 을 전부 바꿔 끼운다."""

    RECS = [
        {"stock": "187790", "name": "나노", "industry": "기초 화학물질 제조업", "product": "SCR촉매", "market": "KOSDAQ", "listed": ""},      # EXTRA
        {"stock": "044490", "name": "태웅", "industry": "기타 금속 가공제품 제조업", "product": "자유형단조품", "market": "KOSDAQ", "listed": ""},  # 어휘 '단조'
    ]

    def _run(self, universe_rows, prev_probe, collect):
        saved = {}
        assets = {"universe.json": {"rows": universe_rows}, "universe_probe.json": prev_probe}
        with mock.patch.object(S, "_get", return_value=b""), \
                mock.patch.object(S, "parse_kind", return_value=list(self.RECS)), \
                mock.patch.object(S, "load_asset", side_effect=lambda n: assets[n]), \
                mock.patch.object(S, "write_asset", side_effect=lambda n, d: saved.__setitem__(n, d)), \
                mock.patch.object(S.sup, "collect_one", side_effect=collect), \
                mock.patch.object(S.time, "sleep", lambda *_: None):
            out = S.scan("2026Q2", log=io.StringIO())
        self.assertIs(saved["universe_probe.json"], out)
        return out

    @staticmethod
    def _prev():
        return {"quarter": "2026Q2", "scanned": "2026-09-11", "pool": 230, "promoted": {"187790": dict(_PREV["187790"])},
                "rejected": [], "failed": []}

    def test_pool_shrinks_but_promoted_survives(self):
        # 나노는 직전 스캔에서 승격돼 universe 에 있다 → 후보 풀에서 빠진다(pool 2→1). 그래도 promoted 에 남아야 한다.
        def collect(r, q):
            self.assertEqual(r["stock"], "044490")
            return {"ok": True, "marine_hits": 1, "marine_terms": {"선박": 1}, "mentions": {}, "rcp": "x", "title": "반기보고서"}
        out = self._run([{"stock": "187790"}], self._prev(), collect)
        self.assertEqual(out["pool"], 1)
        self.assertIn("187790", out["promoted"])
        self.assertEqual(out["promoted"]["187790"]["carried_from"], "2026-09-11")
        self.assertEqual(out["promoted"]["187790"]["hits"], 10)
        self.assertEqual(out["carried"], ["187790"])
        self.assertEqual([r["stock"] for r in out["rejected"]], ["044490"])
        self.assertEqual(out["failed"], [])

    def test_fetch_failure_keeps_promoted(self):
        # universe 가 비어 나노가 다시 후보에 들었지만 DART 가 타임아웃 — failed 에 남고 승격은 유지.
        def collect(r, q):
            if r["stock"] == "187790":
                raise OSError("<urlopen error timed out>")
            return {"ok": True, "marine_hits": 0, "marine_terms": {}, "mentions": {}, "rcp": "x", "title": "반기보고서"}
        out = self._run([], self._prev(), collect)
        self.assertEqual(out["pool"], 2)
        self.assertEqual([f["stock"] for f in out["failed"]], ["187790"])
        self.assertIn("187790", out["promoted"])
        self.assertEqual(out["carried"], ["187790"])
        self.assertNotIn("187790", [r["stock"] for r in out["rejected"]])

    def test_empty_body_keeps_promoted(self):
        # 보고서를 찾았지만 II 절이 비었다(ok=False) — rejected 가 아니라 failed 로, 승격 유지.
        def collect(r, q):
            if r["stock"] == "187790":
                return {"ok": False, "note": "II 절을 찾지 못함", "marine_hits": 0, "marine_terms": {}, "mentions": {}}
            return {"ok": True, "marine_hits": 0, "marine_terms": {}, "mentions": {}, "rcp": "x", "title": "반기보고서"}
        out = self._run([], self._prev(), collect)
        self.assertEqual([(f["stock"], f["err"], f.get("carried")) for f in out["failed"]], [("187790", "II 절을 찾지 못함", True)])
        self.assertIn("187790", out["promoted"])
        self.assertEqual([r["stock"] for r in out["rejected"]], ["044490"])

    def test_rule_miss_after_fetch_demotes(self):
        # 본문을 제대로 읽었는데 조선 낱말이 없다 — 이것은 명시적 강등.
        def collect(r, q):
            return {"ok": True, "marine_hits": 0, "marine_terms": {}, "mentions": {}, "rcp": "x", "title": "반기보고서"}
        out = self._run([], self._prev(), collect)
        self.assertEqual(out["promoted"], {})
        self.assertEqual(out["carried"], [])
        self.assertEqual(sorted(r["stock"] for r in out["rejected"]), ["044490", "187790"])

    def test_no_previous_probe(self):
        # 첫 스캔(probe 파일 없음) — load_asset 이 던져도 빈 이월로 돈다.
        saved = {}
        def load(n):
            if n == "universe_probe.json":
                raise FileNotFoundError(n)
            return {"rows": []}
        def collect(r, q):
            return {"ok": True, "marine_hits": 9, "marine_terms": {"선박": 9}, "mentions": {}, "rcp": "x", "title": "반기보고서"}
        with mock.patch.object(S, "_get", return_value=b""), mock.patch.object(S, "parse_kind", return_value=list(self.RECS)), \
                mock.patch.object(S, "load_asset", side_effect=load), mock.patch.object(S, "write_asset", side_effect=lambda n, d: saved.__setitem__(n, d)), \
                mock.patch.object(S.sup, "collect_one", side_effect=collect), mock.patch.object(S.time, "sleep", lambda *_: None):
            out = S.scan("2026Q2", log=io.StringIO())
        self.assertEqual(sorted(out["promoted"]), ["044490", "187790"])
        self.assertEqual(out["carried"], [])



class TestRejudge(unittest.TestCase):
    """--rejudge: 기준을 바꿔도 DART 없이 지난 증거로 다시 판정한다 — 이월 표식(carried_from)과 carried 목록이 보존돼야 하고,
    증거가 기준에 못 미치면 이월 행도 제외로 간다(이월은 판정 면제가 아니다)."""

    def _probe(self):
        return {"quarter": "2026Q2", "scanned": "2026-09-26", "pool": 214, "rule": "old",
                "promoted": {"187790": dict(_PREV["187790"], carried_from="2026-09-11"),
                             "065710": dict(_PREV["065710"])},
                "rejected": [{"stock": "105740", "name": "디케이락", "industry": "일반 목적용 기계 제조업", "product": "피팅",
                              "ok": True, "hits": 4, "terms": {"선박": 4}, "mentions": {"329180": 1}, "note": ""}],
                "failed": []}

    def _run(self, probe):
        saved = {}
        with mock.patch.object(S, "load_asset", return_value=probe), \
                mock.patch.object(S, "write_asset", side_effect=lambda n, d: saved.__setitem__(n, d)):
            out = S.rejudge(log=io.StringIO())
        self.assertIs(saved["universe_probe.json"], out)
        return out

    def test_keeps_carried_marker_and_rule(self):
        out = self._run(self._probe())
        self.assertEqual(sorted(out["promoted"]), ["065710", "187790"])
        self.assertEqual(out["promoted"]["187790"]["carried_from"], "2026-09-11")
        self.assertNotIn("carried_from", out["promoted"]["065710"])
        self.assertEqual(out["carried"], ["187790"])
        self.assertEqual(out["rule"], S.RULE)
        self.assertEqual([r["stock"] for r in out["rejected"]], ["105740"])
        self.assertEqual(out["scanned"], "2026-09-26")                       # 재판정은 스캔이 아니다 — 스캔일은 그대로

    def test_carried_row_below_rule_is_rejected(self):
        probe = self._probe()
        probe["promoted"]["187790"]["hits"] = 2                                # 증거가 기준(낱말 6)에 못 미친다
        out = self._run(probe)
        self.assertNotIn("187790", out["promoted"])
        self.assertIn("187790", [r["stock"] for r in out["rejected"]])
        self.assertEqual(out["carried"], [])


class TestDefaultQuarter(unittest.TestCase):
    """--quarter 기본값은 상수가 아니라 kship_lib.latest_quarter()(분기말 +50일·사업보고서 +95일) — kship_suppliers/kship_yards 와 같은 규칙.
    CI(scan-kship.yml)는 항상 --quarter 를 넘기므로 기본값은 단독 실행에서만 쓰인다."""

    def test_scan_without_quarter_uses_latest_quarter(self):
        with mock.patch.object(S, "latest_quarter", return_value="2026Q3") as lq, mock.patch.object(S, "scan") as scan, \
                mock.patch.object(sys, "argv", ["kship_scan.py", "--scan"]):
            S.main()
        lq.assert_called_once_with()
        scan.assert_called_once_with("2026Q3")

    def test_explicit_quarter_passes_through(self):
        with mock.patch.object(S, "latest_quarter") as lq, mock.patch.object(S, "scan") as scan, \
                mock.patch.object(sys, "argv", ["kship_scan.py", "--scan", "--quarter", "2025Q4"]):
            S.main()
        lq.assert_not_called()
        scan.assert_called_once_with("2025Q4")

    def test_latest_quarter_rule_boundaries(self):
        # run_all.sh --print-quarter · scan-kship.yml 히어독과 같은 값: Q1~Q3 는 분기말 +50일, Q4 는 +95일부터 '최신'
        for today, want in (("2026-10-08", "2026Q2"), ("2026-11-18", "2026Q2"), ("2026-11-19", "2026Q3"),
                            ("2027-04-04", "2026Q3"), ("2027-04-05", "2026Q4")):
            self.assertEqual(S.latest_quarter(datetime.date.fromisoformat(today)), want, today)


if __name__ == "__main__":
    unittest.main()
