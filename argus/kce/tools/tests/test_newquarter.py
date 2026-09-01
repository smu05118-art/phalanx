#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""새 분기 적재 경로 회귀 테스트.

동일분기 재적재(k=18)만으로는 잡히지 않는 결함이 있다 — 기존 값이 이미 그 칸에 있어
"불일치 0"이 나오기 때문이다. 실운영과 같은 **빈 칸에 새로 쓰는 경로**를 따로 검사한다.

특히 `summary.src`는 `_extend_axes`가 새 칸을 None으로 채우므로, 직전 분기 값을 승계하지
않으면 '공시총계' 가드가 통째로 무력화돼 현대건설 수주잔고가 −58% 난다.
"""
import copy
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
KCE = os.path.dirname(TOOLS)
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, TOOLS)

from kce_lib import extract_data, json_for_html  # noqa: E402
import kce_build as KB  # noqa: E402


def _rep():
    return {"events": 0, "p8_cells": 0, "fcst_cells": 0, "agg_rows": [],
            "created": [], "disappeared": [], "p8_unmatched": [],
            "headers": {"ii4": [], "p8": []}}


def _fx(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class TestNewQuarterPath(unittest.TestCase):

    def _load_into_new_quarter(self, co, ii4_fx, p8_fx):
        """2026Q2 원문을 새 분기(2026Q3) 칸에 적재한다."""
        D = copy.deepcopy(extract_data(os.path.join(KCE, co, "index.html")))
        KB._extend_axes(D, "2026Q3")
        k = D["fq"].index("2026Q3")
        rep = _rep()
        KB._apply_ii4(D, KB.parse_ii4(_fx(ii4_fx)), k, "2026Q3", rep)
        if p8_fx:
            KB._apply_p8(D, KB.parse_p8(_fx(p8_fx)), k, rep)
        KB._recompute(D, k)
        return D, k, rep

    def test_axis_extension_shape(self):
        D, k, _ = self._load_into_new_quarter("sct", "sct_상세표_건설수주.html", None)
        self.assertEqual(len(D["fq"]), 20)
        self.assertEqual(len(D["fqF"]), 24)
        self.assertEqual(D["fqF"][:20], D["fq"])
        for s in D["sites"]:
            for key in ("amt", "cmp", "bal", "pr"):
                self.assertEqual(len(s["s"][key]), 24, (s["id"], key))

    def test_disclosed_total_guard_survives_new_quarter(self):
        """현대건설은 src='공시총계' — 새 분기에도 사이트 합으로 덮어쓰면 안 된다."""
        D, k, _ = self._load_into_new_quarter("hec", "hec_수주상황.html",
                                              "hec_기타재무_진행률수주.html")
        for ent in ("현대건설", "현대엔지니어링", "현대스틸산업"):
            self.assertEqual(KB._src_at(D, ent, k), "공시총계", ent)
            # 가드가 살아 있으면 새 칸은 비어 있다(원문 합계행 반영은 v1 미구현).
            # 가드가 죽으면 사이트 합이 들어가 헤드라인이 반토막 난다.
            self.assertIsNone(D["summary"]["rows"][ent][k], ent)

    def test_measured_cells_written(self):
        """가드와 무관하게 사업장 실측 셀은 새 분기에 정상 기입돼야 한다.

        새 칸에는 기존 예측(fcst)이 분기 라벨을 따라 남아 있으므로, 실측(sFilled=None)만 센다.
        """
        D, k, rep = self._load_into_new_quarter("sct", "sct_상세표_건설수주.html", None)
        meas = [s for s in D["sites"]
                if s["s"]["bal"][k] is not None
                and (s.get("sFilled") or [None] * len(D["fqF"]))[k] is None]
        self.assertEqual(len(meas), 79)
        self.assertEqual(rep["created"], [])
        # 실측이 기존 예측 셀을 덮었는지(같은 사업장에 예측이 남아 있으면 안 된다)
        self.assertTrue(all((s.get("sFilled") or [None] * len(D["fqF"]))[k] is None
                            for s in meas))

    def test_p8_backfill(self):
        """II-4 표에서 빠진 사업장은 III-8 수주총액·진행률로 채운다(sFilled='p8')."""
        D, k, rep = self._load_into_new_quarter("sct", "sct_상세표_건설수주.html",
                                                "sct_기타재무_진행률수주.html")
        KB._backfill_p8(D, k, rep)
        self.assertTrue(rep["backfilled"], "백필이 한 건도 일어나지 않았다")
        for sid in rep["backfilled"]:
            s = next(x for x in D["sites"] if x["id"] == sid)
            b = (s.get("p8") or {}).get("별도") or (s.get("p8") or {}).get("연결")
            self.assertEqual(s["s"]["amt"][k], b["tot"][k], sid)
            self.assertEqual(s["s"]["pr"][k], b["pr"][k], sid)
            self.assertEqual(s["s"]["cmp"][k], round(b["tot"][k] * b["pr"][k] / 100), sid)
            self.assertEqual(s["s"]["bal"][k], b["tot"][k] - s["s"]["cmp"][k], sid)
            self.assertEqual(s["sFilled"][k], "p8", sid)
            # III-8 전용 레코드(has[0]=0)는 백필 대상이 아니다
            self.assertEqual(s["has"][0], 1, sid)

    def test_stale_quarter_does_not_touch_scalars(self):
        """과거 분기 재적재가 최신 스칼라(cl/sd/ed)를 과거 값으로 되돌리면 안 된다."""
        s = {"id": "T-1", "nm": "x", "sd": "2025-01-01", "ed": "2027-12-31",
             "cl": "최신발주처", "s": {"amt": [None] * 23}, "ev": []}
        rep = _rep()
        rec = {"sd": "2020-01-01", "ed": "2026-01-01", "cl": "옛발주처", "amt": 100}
        KB._detect_ev(s, rec, None, "2023Q1", rep, stale=True)
        self.assertEqual(s["cl"], "최신발주처")
        self.assertEqual(s["sd"], "2025-01-01")
        self.assertEqual(s["ev"], [])            # 허위 이벤트도 남기지 않는다
        # stale이 아니면 정상 갱신된다
        KB._detect_ev(s, rec, None, "2023Q1", rep, stale=False)
        self.assertEqual(s["cl"], "옛발주처")

    def test_later_obs_ignores_forecast(self):
        """미래 예측(fcst) 칸은 '이후 관측'이 아니다 — 최신 분기 갱신을 막으면 안 된다."""
        s = {"s": {"amt": [1] * 23}, "sFilled": [None] * 19 + ["fcst"] * 4}
        self.assertFalse(KB._has_later_obs(s, 18, 19))   # 실측 축 기준
        s2 = {"s": {"amt": [1] * 23}, "sFilled": [None] * 23}
        self.assertTrue(KB._has_later_obs(s2, 16, 19))   # 뒤에 실측이 있으면 True

    def test_entity_name_normalization(self):
        """III-8 표의 `지에스건설㈜`와 집계 라벨 `GS건설`은 같은 법인이다."""
        self.assertEqual(KB._ent_key("지에스건설㈜"), KB._ent_key("GS건설"))
        self.assertEqual(KB._ent_key("(주)대우건설"), KB._ent_key("대우건설"))
        self.assertEqual(KB._ent_key("DL이앤씨㈜"), KB._ent_key("DL이앤씨"))
        self.assertNotEqual(KB._ent_key("현대건설"), KB._ent_key("현대엔지니어링"))

    def test_underscore_keys_not_remapped(self):
        """p8Full의 `_dropQ` 등은 분기 인덱스 목록이지 시계열이 아니다."""
        D = copy.deepcopy(extract_data(os.path.join(KCE, "sct", "index.html")))
        target = next(s for s in D["sites"] if s.get("p8Full"))
        marker = list(range(len(D["fqF"])))       # 길이를 축과 같게 만들어 오인을 유도
        target["p8Full"]["_dropQ"] = marker
        KB._extend_axes(D, "2026Q3")
        self.assertEqual(target["p8Full"]["_dropQ"], marker)


class TestScriptEscaping(unittest.TestCase):
    """DATA 문자열의 `</script>`가 페이지를 깨거나 마크업으로 실행되면 안 된다."""

    def test_script_tag_escaped(self):
        blob = json_for_html({"nm": "A</script><script>x=1</script>B"})
        self.assertNotIn("</script>", blob)
        self.assertNotIn("<script>", blob)
        import json
        self.assertEqual(json.loads(blob)["nm"], "A</script><script>x=1</script>B")


class TestDateGuard(unittest.TestCase):
    """원문 오기(착공일 ≥ 완공예정일)로 저장된 정상 날짜가 덮이면 안 된다."""

    def test_reversed_dates_rejected(self):
        s = {"id": "T-1", "nm": "x", "sd": "2024-10-18", "ed": "2027-02-28",
             "cl": "발주처", "s": {"amt": [None] * 23}, "ev": []}
        rep = _rep()
        KB._detect_ev(s, {"sd": "2027-02-28", "ed": "2027-02-28", "cl": "발주처"},
                      None, "2026Q2", rep)
        self.assertEqual(s["sd"], "2024-10-18")           # 기존값 유지
        self.assertEqual(s["ev"], [])                      # 허위 이벤트 없음
        self.assertEqual(len(rep.get("bad_dates") or []), 1)


if __name__ == "__main__":
    unittest.main()
