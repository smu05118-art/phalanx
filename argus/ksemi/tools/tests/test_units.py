# -*- coding: utf-8 -*-
"""계약: 단위 정규화(COMMON.md §2 · §4).

표의 금액은 **표마다 원문 캡션을 읽어** 백만원으로 정규화한다. 못 읽으면
`unit_seen=False` 로 남기고 **금액을 쓰지 않는다**(fail-closed, COMMON §0-2).

핵심 함정 — PROGRESS.md §1 5행(한미반도체 2026 반기):
단위 캡션 `금 액 (단위: 원)` 이 표 앞 문맥에도, 첫 머리행에도 없고 **둘째 머리행
셀 안**에 있다. 첫 머리행만 보면 원을 백만원으로 읽어 442억이 4.4조가 된다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C                                          # noqa: E402

import ksemi_parse as P                                      # noqa: E402
from ksemi_lib import parse_tables                           # noqa: E402

# 한미반도체 원문의 단일 수주 계약 — 원(₩) 단위 그대로.
HANMI_WON = 44200000000                  # 44,200,000,000 원 = 442억
HANMI_MKRW = 44200                       # 백만원으로 정규화한 값
HANMI_ITEM = "HBM4 제조용 'TC BONDER 4.5 GRIFFIN' 장비"
HANMI_CAPTION = "금 액 (단위: 원)"


class TestScaleOf(unittest.TestCase):
    """캡션 → 백만원 환산 배수. 없으면 None(1.0 아님)."""

    def test_known_units(self):
        self.assertEqual(P._scale_of("다. 수주상황 (단위 : 백만원)"), 1.0)
        self.assertEqual(P._scale_of("(단위 : 천원)"), 0.001)
        self.assertEqual(P._scale_of(HANMI_CAPTION), 1e-06)
        self.assertEqual(P._scale_of("(단위:억원)"), 100.0)
        self.assertEqual(P._scale_of("(단위 : 십억원)"), 1000.0)
        self.assertEqual(P._scale_of("(단위 : 만원)"), 0.01)

    def test_longest_unit_wins(self):
        # '십억원'·'억원' 안에 '원'이 들어 있다 — 짧은 쪽이 먼저 걸리면 1e-6 배가 된다.
        self.assertEqual(P._scale_of("(단위 : 십억원)"), 1000.0)
        self.assertNotEqual(P._scale_of("(단위 : 억원)"), 1e-06)

    def test_no_caption_is_none_not_one(self):
        # 캡션이 없으면 None. 1.0(백만원 가정)으로 두면 천원 표가 1000배로 실린다.
        self.assertIsNone(P._scale_of("금 액"))
        self.assertIsNone(P._scale_of(""))
        self.assertIsNone(P._scale_of(None))


class TestUnitOfHanmiTrap(unittest.TestCase):
    """둘째 머리행에 숨은 열 단위를 읽는가(PROGRESS §1-5)."""

    def setUp(self):
        self.html = C.fixture(C.II4_HANMI)
        self.table = None
        for t in parse_tables(self.html):
            cols, _n, _f, rows = P.resolve_header(t)
            if any("수주총액" in c for c in cols) and rows:
                self.table = (t, cols, rows)
                break
        self.assertIsNotNone(self.table, "fixture 에 수주상황 표가 없다")

    def test_caption_is_in_the_second_header_row_only(self):
        """원문 확인: 캡션은 표 앞 문맥에도 첫 머리행에도 없다."""
        t, cols, _rows = self.table
        self.assertIn(HANMI_CAPTION, self.html)             # 원문에 실재한다
        self.assertIsNone(P._scale_of(P._txt(t.get("lead"))),
                          "표 앞 문맥(lead)에 단위가 있으면 이 함정이 아니다")
        # parse_tables 가 뽑은 첫 머리행(둘째 줄을 붙이기 전)에도 단위가 없다.
        first_head = " ".join(P._txt(c) for c in (t.get("cols") or []))
        self.assertIsNone(P._scale_of(first_head),
                          "첫 머리행에 단위가 있으면 이 함정이 아니다")
        # resolve_header 가 둘째 머리행을 이어 붙여야 비로소 캡션이 보인다.
        self.assertTrue(any("단위: 원" in c for c in cols), cols)

    def test_column_unit_wins_and_table_unit_stays_unknown(self):
        t, cols, _rows = self.table
        unit = P.unit_of(t, cols)
        self.assertIsNone(unit["scale"], "표 단위는 어디에도 없다")
        self.assertTrue(unit["seen"], "열 단위를 읽었으면 unit_seen 은 True")
        amt_i = [i for i, c in enumerate(cols) if "수주총액" in c and "단위: 원" in c]
        self.assertEqual(len(amt_i), 1, cols)
        self.assertEqual(unit["per_col"][amt_i[0]], 1e-06)

    def test_order_amount_is_442eok_not_44jo(self):
        """수주총액 = 44,200,000,000 원 = 44,200 백만원(442억)."""
        o = P.orders(self.html)
        self.assertTrue(o["unit_seen"])
        rows = [r for tb in o["tables"] for r in tb["rows"] if not r["total"]]
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["nm"], HANMI_ITEM)
        self.assertEqual(rows[0]["amt"], HANMI_MKRW)
        # 백만원 → 원으로 되돌리면 원문 숫자와 한 자리도 다르지 않다.
        self.assertEqual(int(round(rows[0]["amt"] * 1e6)), HANMI_WON)
        self.assertEqual(o["order_amt"], HANMI_MKRW)
        # 백만원으로 잘못 읽었을 때의 값(4.42경 백만원)이 실리면 안 된다.
        self.assertNotEqual(o["order_amt"], HANMI_WON)


class TestFailClosed(unittest.TestCase):
    """단위를 어디서도 못 읽으면 금액을 조용히 내보내지 않는다."""

    def test_stripping_the_caption_makes_the_value_disappear(self):
        html = C.fixture(C.II4_HANMI).replace(HANMI_CAPTION, "금 액")
        self.assertNotIn("단위", html.split("수주상황")[-1][:1500])
        o = P.orders(html)
        self.assertFalse(o["unit_seen"], "단위가 없는데 unit_seen 이 True 다")
        self.assertIsNone(o["order_amt"])
        self.assertIsNone(o["backlog"])
        self.assertIsNone(o["delivered"])
        vals = [r["amt"] for tb in o["tables"] for r in tb["rows"]]
        self.assertTrue(all(v is None for v in vals), vals)
        # 정규화되지 않은 원문 숫자가 그대로 새어 나가지 않는다.
        self.assertNotIn(HANMI_WON, vals)
        self.assertNotIn(HANMI_MKRW, vals)
        # 그래도 행과 품목은 남는다(원문을 버리지 않는다 — COMMON §0-4).
        self.assertEqual([r["nm"] for tb in o["tables"] for r in tb["rows"]][0],
                         HANMI_ITEM)

    def test_money_returns_none_when_scale_unknown(self):
        unknown = {"scale": None, "seen": False, "raw": None, "per_col": {}}
        self.assertIsNone(P._money("44,200,000,000", 0, unknown))
        self.assertIsNone(P._money("1,197,393", 3, unknown))

    def test_money_normalizes_each_unit(self):
        def u(scale):
            return {"scale": scale, "seen": True, "raw": "", "per_col": {}}
        self.assertEqual(P._money("1,197,393", 0, u(1.0)), 1197393)        # 백만원
        self.assertEqual(P._money("445,603,489", 0, u(0.001)), 445603.489)  # 천원
        self.assertEqual(P._money("44,200,000,000", 0, u(1e-06)), 44200)    # 원
        self.assertEqual(P._money("1,234", 0, u(100.0)), 123400)            # 억원
        self.assertIsNone(P._money("-", 0, u(1.0)))                         # 값 없음


class TestContractAmountUnits(unittest.TestCase):
    """계약 공시(수시공시)의 금액도 라벨 괄호에서 단위를 읽는다 — 같은 계약.

    `_amount` 는 순수 함수라 DART 없이 검증한다. kv 는 주성엔지니어링
    20210204900782 공시의 원문 라벨·값(assets/contracts.json 에 그대로 보존).
    """

    KV = {"1. 판매ㆍ공급계약 내용": "반도체 제조장비",
          "2. 계약내역 확정 계약금액": "13,032,886,123",
          "2. 계약내역 계약금액 총액(원)": "13,032,886,123",
          "2. 계약내역 최근 매출액(원)": "259,064,128,325",
          "3. 계약상대방": "SK hynix Semiconductor (China) Ltd."}

    def setUp(self):
        import ksemi_contracts as K
        self.K = K

    def test_amount_is_normalized_from_the_label_caption(self):
        a = self.K._amount(self.KV)
        self.assertTrue(a["unit_seen"])
        self.assertEqual(a["currency"], "KRW")
        self.assertEqual(a["amt_unit"], "원")
        self.assertEqual(a["amt_native"], 13032886123)
        self.assertEqual(a["amt_mkrw"], 13032.886)       # 백만원(소수 3자리까지)

    def test_missing_unit_is_fail_closed(self):
        kv = {"2. 계약내역 확정 계약금액": "13,032,886,123"}
        a = self.K._amount(kv)
        self.assertFalse(a["unit_seen"])
        self.assertIsNone(a["amt_mkrw"], "단위를 못 읽었는데 금액이 나왔다")
        self.assertEqual(a["amt_native"], 13032886123)   # 원문 값은 보존한다
        self.assertEqual(a["amt_note"], "단위 표기 없음")

    def test_foreign_currency_is_not_converted(self):
        kv = {"2. 계약내역 계약금액 총액(USD)": "11,823,356.73"}
        a = self.K._amount(kv)
        self.assertEqual(a["currency"], "USD")
        self.assertIsNone(a["amt_mkrw"], "환율을 지어내지 않는다")

    @unittest.skipUnless(C.has_asset("contracts.json"), "assets/contracts.json 없음")
    def test_stored_contracts_are_unit_consistent(self):
        rows = C.asset("contracts.json")["rows"]
        self.assertTrue(rows)
        bad = [r["rcp"] for r in rows
               if r.get("amt_mkrw") is not None and not r.get("unit_seen")]
        self.assertEqual(bad, [], "단위 미확인인데 금액이 실린 계약이 있다")
        off = [(r["rcp"], r["amt_mkrw"], r["amt_native"]) for r in rows
               if r.get("currency") == "KRW" and r.get("amt_mkrw") is not None
               and abs(r["amt_mkrw"] - r["amt_native"] / 1e6) > 0.001]
        self.assertEqual(off, [], "백만원 값이 원 단위 원문과 어긋난다")


if __name__ == "__main__":
    unittest.main()
