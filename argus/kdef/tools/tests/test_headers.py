#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한국방산 머리행 지도·미지 열 큐 계약 테스트 — 2026-10-12 (공용 엔진 argus/kce/tools/hdrmap.py).

여기서 지키는 것(전부 DART 0 — 캐시 원문 표 assets/reports_cache 와 tests/fixtures 만 읽는다):
  · 재생 — 캐시 전 파일을 메모리에서 다시 읽어 지도·큐·페이지를 만든다. 캐시 파일은 쓰지 않는다. 증분 재실행은 같은 바이트.
  · 실패 45건(2026-10-12 캐시)의 갈래 — no_tables 33 · no_orders_table(수주표 없음) 10 · award 2.
  · 판별 근거(matched) — KAI 두 줄 머리행에서 기초·기말 **금액** 열을 집는다(수량 열이 아니라).
  · 채택 플래그 — orders_all 전부를 기록하고 화면 값의 표 한 장만 pick=True(KAI 5장 중 지배회사 표).
  · 어휘 — 대한항공 종속 표 36장(18분기 × 2)의 금액 열을 읽는다(잔고 단독·납품금액·매출금액).
  · 부머리행 병합 — 풍산·한화(000880)의 `수주총액|수주총액` 아래 `수량|금액` 줄. 수량이 금액으로 실리지 않는다.
  · 체계업체 7사 잔고 불변 — 화면 창(reports.json 분기)에서 새 파서의 잔고 = 지금 화면 값.
  · advisory — 엔진이 터져도 수집(collect_one)은 캐시를 쓰고 돌아온다.
  · 탐색 이월(carry_forward)·신규 편입(onboard)·실행 시각 없음.

    python3 -m unittest discover -s tests
"""
import glob
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import kdef_reports as KR                                            # noqa: E402
import kdef_headers as KH                                            # noqa: E402
import kdef_scan as KS                                               # noqa: E402
import kdef_universe as KU                                           # noqa: E402
import hdrmap                                                        # noqa: E402
import kce_fetch                                                     # noqa: E402

# kdef_lib 이 argus/kce/tools·argus/kship/tools 를 sys.path **앞**에 넣는다 — 이 파일이 먼저 import 되면(discover 는
# 이름 순: test_headers < test_parsers) 뒤 테스트의 `import build_dicts` 가 kship 의 것을 잡는다. kdef/tools 를 다시 맨 앞에.
sys.path.remove(TOOLS)
sys.path.insert(0, TOOLS)

FIX = os.path.join(HERE, "fixtures")
CACHE = KR.CACHE
PRIMES = ("012450", "042660", "047810", "064350", "079550", "103140", "272210")


def cache(st, q):
    p = os.path.join(CACHE, st, q + ".json")
    if not os.path.exists(p):
        raise unittest.SkipTest("캐시 없음: %s %s" % (st, q))
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def md5(p):
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


_NULL = open(os.devnull, "w")       # 수집 로그를 버리는 곳(모듈 하나 — 테스트마다 열면 ResourceWarning)


def _no_dart(*a, **k):
    raise AssertionError("DART 요청 금지(재생은 캐시만 읽는다)")


def backlog(o):
    """kdef_reports.build 의 잔고 식 그대로(금액 표가 아니면 None)."""
    if not o:
        return None
    orows = o.get("rows") or []
    if not (bool(o.get("unit_seen")) and not o.get("qty_unit")):
        return None
    tot = [r for r in orows if r["total"]]
    return tot[0]["closing"] if tot and tot[0].get("closing") is not None else KR._sum_rows(orows, "closing")


class TestReplay(unittest.TestCase):
    """캐시 전부 → 지도·큐·페이지. 한 번 돌려 여러 단언에 쓴다(≈3초)."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="kdef_hdr_")
        cls.n_files = len(glob.glob(os.path.join(CACHE, "*", "*.json")))
        before = {p: os.path.getmtime(p) for p in glob.glob(os.path.join(CACHE, "*", "*.json"))}
        with mock.patch.object(kce_fetch, "_get", _no_dart), \
                mock.patch.object(KR, "search_reports", _no_dart), \
                mock.patch.object(KR, "fetch_section", _no_dart), \
                mock.patch.object(KR, "toc", _no_dart):
            cls.res = KH.replay(root=cls.root, log=_NULL)
            cls.html = KH.render(root=cls.root)
        cls.cache_untouched = before == {p: os.path.getmtime(p) for p in before}
        cls.M = hdrmap.load_map("kdef", cls.root)
        cls.Q = hdrmap.load_queue("kdef", cls.root)

    @classmethod
    def tearDownClass(cls):
        hdrmap.discard("kdef")
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_replay_all_cache_no_dart(self):
        """캐시 전 파일(2026-10-12 1,125)을 DART 없이 재생하고, 캐시 파일은 한 개도 쓰지 않는다."""
        self.assertGreaterEqual(self.n_files, 1125)
        self.assertEqual(self.res["files"], self.n_files)
        self.assertTrue(self.cache_untouched, "재생이 캐시 파일을 썼다")
        dirs = {os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(CACHE, "*", "*.json"))}
        self.assertEqual(set(self.M["companies"]), dirs)
        nb = os.path.getsize(hdrmap.map_path("kdef", self.root))
        self.assertLess(nb, hdrmap.MAX_BYTES)
        # 페이지 — tools 밖 argus/kdef/headers.html, 회사 버튼·절 라벨이 들어 있다
        self.assertTrue(os.path.exists(os.path.join(self.root, "kdef", "headers.html")))
        D, LAB, ORDER, _, _ = hdrmap._parse_page(self.html)
        self.assertEqual(set(D), dirs)
        self.assertEqual(set(LAB), {"orders", "revenue", "segsales", "customers"})
        self.assertIn(KH.TITLE, self.html)

    def test_incremental_rerun_same_bytes(self):
        """증분 재실행은 아무것도 다시 읽지 않고 세 파일이 같은 바이트다(매일 돌아도 커밋 노이즈 0)."""
        paths = [hdrmap.map_path("kdef", self.root), hdrmap.queue_path("kdef", self.root),
                 hdrmap.headers_path("kdef", self.root)]
        h0 = [md5(p) for p in paths]
        with mock.patch.object(kce_fetch, "_get", _no_dart):
            r = KH.replay(root=self.root, log=_NULL)
            KH.render(root=self.root)
        self.assertEqual(r["files"], 0)
        self.assertEqual([md5(p) for p in paths], h0)

    def test_queue_schema_latest_only_no_time(self):
        """큐 — 시각 필드 없음·id 정렬·회사마다 최신 분기에서만 열린다(과거 분기는 지도에만)."""
        self.assertEqual([i["id"] for i in self.Q], sorted(i["id"] for i in self.Q))
        latest = {}
        for p in glob.glob(os.path.join(CACHE, "*", "*.json")):
            st, q = os.path.basename(os.path.dirname(p)), os.path.basename(p)[:-5]
            latest[st] = max(latest.get(st, ""), q)
        for it in self.Q:
            self.assertFalse({k for k in it if "time" in k or k.endswith("_at")}, it)
            self.assertIn(it["kind"], hdrmap.KINDS)
            self.assertEqual(it["grade"], "B", "kdef 는 자동 반영(A) 대상이 아니다 — 사전이 kce 건설 사전이다")
            if it["kind"] != "new_company":
                self.assertEqual(it["quarter_first"], latest[it["key"]], it)
        with open(hdrmap.queue_path("kdef", self.root), encoding="utf-8") as f:
            self.assertNotIn("scanned_at", f.read())

    def test_pick_flags_orders_all(self):
        """KAI 2026Q2 — 수주표 5장(지배 1 + 종속 4) 전부 기록, 채택은 화면 값의 지배회사 표 한 장."""
        ent = self.M["companies"]["047810"]["roles"]["orders"]["2026Q2"]
        self.assertEqual(len(ent), 5)
        picked = [e for e in ent if e["pick"]]
        self.assertEqual(len(picked), 1)
        self.assertEqual(picked[0]["ent"], "parent")
        self.assertEqual(picked[0]["tag"], "openclose")
        # 종속 4장 — 첫 장만 lead 에 `[ 종속회사의 내용 ]` 이 있고 나머지는 회사 이름뿐이라 unknown(원문 그대로)
        self.assertEqual(sorted(e["ent"] for e in ent if not e["pick"]), ["sub", "unknown", "unknown", "unknown"])
        # 다른 역할도 채택은 분기당 많아야 한 장
        for st, co in self.M["companies"].items():
            for role, by_q in co["roles"].items():
                for q, entries in by_q.items():
                    self.assertLessEqual(sum(1 for e in entries if e["pick"]), 1, (st, role, q))

    def test_fields_are_kdef_meanings(self):
        """수주 역할의 fields 는 이 탭이 읽은 뜻(open…due·qty·label) — 건설 사전 별칭이 섞이지 않는다."""
        ok = set(KR.MATCH_KEYS) | set(KR._AWARD_KEYS) | {"qty", "label"}
        for co in self.M["companies"].values():
            for entries in (co["roles"].get("orders") or {}).values():
                for e in entries:
                    self.assertTrue(set(e["fields"]) <= ok, e["fields"])

    def test_check_runs_and_regressions_are_orders(self):
        rep = hdrmap.check("kdef", critical=PRIMES, root=self.root)
        self.assertIn(rep["exit"], (0, 1))
        for r in rep["regressions"]:
            self.assertEqual(r["role"], "orders")
            self.assertNotIn(r["key"], PRIMES, "체계업체 수주표 소실 — 화면 잔고가 빠졌다")


class TestFailures(unittest.TestCase):
    """2026-10-12 캐시의 실패(ok=False) 45건 — 재파싱해도 실패이고 갈래가 셋으로 갈린다."""

    NO_TABLES = ([("003490", "2024Q4"), ("368770", "2021Q4")]
                 + [("024740", q) for q in ("2022Q1", "2022Q2", "2022Q3", "2022Q4", "2023Q1", "2023Q2", "2023Q3",
                                            "2023Q4", "2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1", "2025Q2",
                                            "2025Q3")]
                 + [("082210", q) for q in ("2021Q4", "2022Q1", "2022Q2", "2022Q4", "2023Q1", "2023Q2", "2023Q4",
                                            "2024Q1", "2024Q2", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4",
                                            "2026Q1", "2026Q2")])
    NO_ORDERS = [("049080", q) for q in ("2021Q4", "2022Q1", "2022Q2", "2022Q3", "2024Q1", "2024Q2", "2024Q3",
                                          "2024Q4", "2025Q1", "2025Q2")]
    AWARD = [("488900", "2025Q4"), ("488900", "2026Q2")]

    def test_failed45_classified(self):
        got = {}
        for want, pairs in (("no_tables", self.NO_TABLES), ("no_orders_table", self.NO_ORDERS),
                            ("award", self.AWARD)):
            for st, q in pairs:
                d = cache(st, q)
                self.assertFalse(d["ok"], (st, q))
                nd, _ = KR.reparse_dict(d)
                self.assertFalse(nd["ok"], (st, q))
                got[want] = got.get(want, 0) + (nd["fail_kind"] == want)
        self.assertEqual(got, {"no_tables": 33, "no_orders_table": 10, "award": 2})

    def test_award_is_classified_not_adopted(self):
        """비츠로넥스텍 `계약상대방|계약명|계약기간|계약금액(원)` — 잔고 열이 없는 공시 계약 목록. 잔고로 싣지 않는다."""
        nd, res = KR.reparse_dict(cache("488900", "2026Q2"))
        self.assertIsNone(nd["orders"])
        u = [x for x in nd["unknown_headers"] if x["reason"] == "award"]
        self.assertEqual(len(u), 1)
        self.assertEqual(u[0]["cols"][:2], ["계약상대방", "계약명"])

    def test_no_tables_reparse_keeps_values(self):
        """raw_tables 가 없는 실패 캐시는 다시 뽑을 것이 없다 — 값은 그대로, 갈래만 no_tables."""
        d = cache("082210", "2026Q2")
        nd, res = KR.reparse_dict(d)
        self.assertEqual(nd["fail_kind"], "no_tables")
        for k in ("orders", "revenue", "segment_sales", "customers", "note", "rcp"):
            self.assertEqual(nd.get(k), d.get(k), k)
        self.assertEqual(res["orders_all"], [])


class TestMatched(unittest.TestCase):

    def test_matched_kai_2row(self):
        """KAI 2026 반기 두 줄 머리행 — 기초·기말 **금액** 열(2·4번)을 잡고 수량 열(1·3번)은 비운다."""
        with open(os.path.join(FIX, "kai_2026Q2_orders.json"), encoding="utf-8") as f:
            tables = KR._headered(KR._carry_units(json.load(f)["tables"]))
        o = KR._pick_orders([x for x in (KR.parse_orders_table(t) for t in tables) if x])
        self.assertEqual(o["header_synth"], "2row")
        self.assertEqual(o["cols_raw"], [])
        self.assertEqual(o["matched"], {"open": 2, "new": None, "done": None, "gross": None, "close": 4,
                                        "date": None, "due": None})
        self.assertEqual(KR.order_fields(o["cols"]), ["label", "qty", "open", "qty", "close", "label"])
        self.assertEqual(o["scope"], "parent")

    def test_qty_only_column_is_not_money(self):
        """금액 열 없이 `수주잔고 수량` 만 있으면 잔고 역할을 비운다 — 예전에는 그 열을 백만원으로 읽었다."""
        m = KR._match_cols(["품목", "수주총액 금액", "수주잔고 수량"])
        self.assertEqual(m["gross"], 1)
        self.assertIsNone(m["close"])
        self.assertEqual(m["qty_only"], ["close"])
        self.assertEqual(KR.orders_unknown({"cols": ["품목", "수주잔고 수량"], "rows": [["A", "3"]]})["reason"],
                         "qty_only")

    def test_new_vocab_after_old(self):
        """새 어휘는 같은 역할의 기존 어휘 **뒤** — 지금 읽히는 표의 열 선택이 바뀌지 않는다."""
        m = KR._match_cols(["품목", "수주총액", "기납품액", "매출금액", "수주잔고", "잔고"])
        self.assertEqual((m["gross"], m["done"], m["close"]), (1, 2, 4))
        m = KR._match_cols(["사업명", "사업기간", "수주금액", "매출금액", "잔고"])
        self.assertEqual((m["gross"], m["done"], m["close"]), (2, 3, 4))

    def test_vocab_kal_36(self):
        """대한항공 종속회사 표 36장(2021Q4~2026Q2, 실패 1분기 제외 18 × 2) — 금액 열을 전부 읽는다.
        한진정보통신 `사업명|사업기간|수주금액|매출금액|잔고` 18장은 수주표로 채택 후보가 되고(잔고 단독·매출금액),
        한국공항 `품 목|품 목|수주일자|수주금액|납품금액|비고` 18장은 잔고 열이 없어(매출실적을 수주로 기재) 미지(no_close)로 남는다."""
        hanjin = kap = 0
        for p in sorted(glob.glob(os.path.join(CACHE, "003490", "*.json"))):
            q = os.path.basename(p)[:-5]
            if q > "2026Q2":
                continue
            nd, res = KR.reparse_dict(cache("003490", q))
            for o in nd["orders_all"]:
                if KR._clean(o["cols"][-1]) == "잔고":
                    m = o["matched"]
                    self.assertEqual((m["gross"], m["done"], m["close"]), (2, 3, 4))
                    hanjin += 1
            for u in nd["unknown_headers"]:
                if "납품금액" in u["cols"]:
                    m = KR._match_cols(u["cols"])
                    self.assertEqual((m["gross"], m["done"], m["close"]), (3, 4, None))
                    self.assertEqual(u["reason"], "no_close")
                    kap += 1
        self.assertEqual((hanjin, kap), (18, 18))


class TestTwoRow(unittest.TestCase):

    def test_two_row_poongsan(self):
        """풍산 종속회사 표 `수주총액|수주총액` 아래 `판매량|금액` — 이어 붙여 금액 열을 읽는다(판매량이 아니라)."""
        nd, res = KR.reparse_dict(cache("103140", "2026Q2"))
        sub = [o for o in nd["orders_all"] if o.get("header_synth") == "2row"]
        self.assertEqual(len(sub), 1)
        o = sub[0]
        self.assertIn("수주총액 판매량", o["cols"])
        self.assertIn("수주총액 금액", o["cols"])
        self.assertEqual(o["cols_raw"][3:5], ["수주총액", "수주총액"])
        self.assertEqual(o["cols"][o["matched"]["gross"]], "수주총액 금액")
        self.assertEqual(o["cols"][o["matched"]["close"]], "수주잔고 금액")
        # 신관 행의 잔고 = 금액 열(1,609·74,729·계 76,338 백만원) — 판매량(50,002·563,972·613,974 EA)이 아니다
        self.assertEqual([r["closing"] for r in o["rows"] if r["seg"] == "신관"], [1609, 74729, 76338])
        # 종속 표는 M/T 캡션이라 금액 표가 아니다 — 채택은 지배회사 표 그대로(화면 잔고 불변)
        self.assertTrue(o["qty_unit"])
        self.assertEqual(backlog(nd["orders"]), 1789040)

    def test_poongsan_2021q4_tonnage_not_money(self):
        """풍산 2021Q4 지배회사 표 — 병합 전에는 `수주잔고` 첫 열(중량 96,206 M/T)을 백만원으로 실었다."""
        d = cache("103140", "2021Q4")
        self.assertEqual(backlog(d["orders"]), 96206)
        nd, _ = KR.reparse_dict(d)
        self.assertEqual(backlog(nd["orders"]), 1076438)

    def test_hanwha_000880_recovered(self):
        """한화(000880) 2026Q2 — 부머리행 미병합으로 표가 통째로 빠지던 분기(13분기 중 하나)가 item 으로 읽힌다."""
        d = cache("000880", "2026Q2")
        self.assertIsNone(d["orders"])
        nd, res = KR.reparse_dict(d)
        self.assertEqual(nd["orders"]["shape"], "item")
        self.assertEqual(nd["orders"]["header_synth"], "2row")
        self.assertEqual(backlog(nd["orders"]), 137370767)

    def test_merge_subrow_fail_closed(self):
        t = {"cols": ["품목", "수주총액", "수주총액"], "rows": [["품목", "수량", "금액"], ["A", "1", "100"]]}
        self.assertEqual(KR._merge_subrow(t)["cols"], ["품목", "수주총액 수량", "수주총액 금액"])
        # 부머리행 어휘가 아니면(본문 첫 줄) 손대지 않는다
        self.assertIsNone(KR._merge_subrow({"cols": ["품목", "금액", "금액"], "rows": [["A", "갑", "을"], ["B", "1", "2"]]}))
        # 이웃 중복 열이 없으면 손대지 않는다
        self.assertIsNone(KR._merge_subrow({"cols": ["품목", "수량", "금액"], "rows": [["품목", "수량", "금액"], ["A", "1", "2"]]}))


class TestPrimeBacklog(unittest.TestCase):

    def test_prime7_backlog_unchanged(self):
        """체계업체 7사 — 화면 창(reports.json 분기)에서 새 파서로 다시 읽은 잔고가 지금 화면 잔고와 같다.
        창 밖까지 보면 다른 것은 풍산 2021Q4 하나(중량을 금액으로 읽던 것을 고친 값)뿐이어야 한다."""
        with open(os.path.join(KR.ASSETS, "reports.json"), encoding="utf-8") as f:
            rep = json.load(f)
        n = 0
        for st in PRIMES:
            for q, v in rep["companies"][st]["quarters"].items():
                if not v.get("ok"):
                    continue
                nd, _ = KR.reparse_dict(cache(st, q))
                self.assertEqual(backlog(nd["orders"]), v["backlog"], (st, q))
                n += 1
        self.assertGreaterEqual(n, 50)
        diff = set()
        for st in PRIMES:
            for p in sorted(glob.glob(os.path.join(CACHE, st, "*.json"))):
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                nd, _ = KR.reparse_dict(d)
                if backlog(nd["orders"]) != backlog(d.get("orders")):
                    diff.add((st, d["quarter"]))
        self.assertTrue(diff <= {("103140", "2021Q4")}, diff)


class TestCustomers(unittest.TestCase):

    def test_segment_column_rejected(self):
        """한화시스템 `사업부문|…|주요 매출처(비중)` — 이름 칸이 부문명(방산·ICT·기타)이라 거래처로 싣지 않는다."""
        nd, _ = KR.reparse_dict(cache("272210", "2026Q2"))
        self.assertIsNone(nd["customers"])
        nd, _ = KR.reparse_dict(cache("000880", "2026Q2"))
        self.assertIsNone(nd["customers"])

    def test_count_row_dropped(self):
        """한화오션 `10% 이상 차지하는 주요 고객수` — 거래처가 아니라 개수다."""
        nd, _ = KR.reparse_dict(cache("042660", "2026Q2"))
        self.assertIsNone(nd["customers"])

    def test_real_customers_kept(self):
        """방위사업청·국방과학연구소 같은 진짜 거래처는 '방산' 낱말이 있어도 남는다(열 이름으로 거른다)."""
        nd, _ = KR.reparse_dict(cache("079550", "2026Q2"))
        names = [r["name"] for r in nd["customers"]["rows"]]
        self.assertIn("방위사업청", names)


class TestCollectAdvisory(unittest.TestCase):
    """collect_one 의 지도 훅 — 정상이면 그 (회사, 분기)를 기록·커밋, 엔진이 터져도 수집은 끝까지 간다."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kdef_hook_")
        self.old = (KR.CACHE, KR.HDR_ROOT)
        KR.CACHE = os.path.join(self.tmp, "cache")
        KR.HDR_ROOT = self.tmp
        with open(os.path.join(FIX, "kai_2026Q2_orders.json"), encoding="utf-8") as f:
            self.tables = json.load(f)["tables"]
        self.patches = [
            mock.patch.object(KR, "search_reports", lambda *a, **k: [("20260814000001", "반기보고서")]),
            mock.patch.object(KR, "pick_report", lambda rs, q: rs),
            mock.patch.object(KR, "toc", lambda rcp: []),
            mock.patch.object(KR, "find_sections", lambda nodes, secs: {"sales": {"text": "4. 매출 및 수주상황"}}),
            mock.patch.object(KR, "fetch_section", lambda node: "<p>보안관계상</p>"),
            mock.patch.object(KR, "parse_tables", lambda html: json.loads(json.dumps(self.tables))),
            mock.patch.object(kce_fetch, "_get", _no_dart)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        KR.CACHE, KR.HDR_ROOT = self.old
        hdrmap.discard("kdef")
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_hook_records_and_commits(self):
        out = KR.collect_one({"stock": "047810", "name": "한국항공우주"}, "2026Q2", log=_NULL)
        self.assertTrue(out["ok"])
        self.assertEqual(out["unknown_headers"], [])
        # 원문 표에 합성 머리행 표지가 남는다(--reparse·재생이 '우리가 만든 머리행'을 안다)
        self.assertTrue(any(t.get("header_synth") == "2row" for t in out["raw_tables"]))
        M = hdrmap.load_map("kdef", self.tmp)
        ent = M["companies"]["047810"]["roles"]["orders"]["2026Q2"]
        self.assertEqual([e["pick"] for e in ent], [True])
        self.assertEqual(ent[0]["synth"], "2row")
        self.assertEqual(hdrmap.staged("kdef"), {})
        kinds = {i["kind"] for i in hdrmap.load_queue("kdef", self.tmp)}
        self.assertEqual(kinds, {"synth"})        # 합성 머리행 채택은 사람이 한 번 본다

    def test_engine_failure_does_not_stop_collect(self):
        def boom(*a, **k):
            raise RuntimeError("엔진 고장")
        with mock.patch.object(hdrmap, "record", boom):
            out = KR.collect_one({"stock": "047810", "name": "한국항공우주"}, "2026Q2", log=_NULL)
        self.assertTrue(out["ok"])
        self.assertTrue(os.path.exists(os.path.join(KR.CACHE, "047810", "2026Q2.json")))
        q = hdrmap.load_queue("kdef", self.tmp)
        self.assertEqual([i["kind"] for i in q], ["engine_error"])
        self.assertIn("엔진 고장", q[0]["reason"])

    def test_reparse_one_idempotent(self):
        KR.collect_one({"stock": "047810", "name": "한국항공우주"}, "2026Q2", log=_NULL)
        p = os.path.join(KR.CACHE, "047810", "2026Q2.json")
        KR.reparse_one(p, log=_NULL)
        a = md5(p)
        KR.reparse_one(p, log=_NULL)
        self.assertEqual(md5(p), a)
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        self.assertTrue(d["reparsed"])
        self.assertEqual(backlog(d["orders"]), 25750200)


class TestOnboardScan(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kdef_onb_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_onboard_new_company(self):
        prev = [{"stock": "047810"}, {"stock": "012450"}]
        rows = prev + [{"stock": "999990", "slug": "999990", "name": "새방산"}]
        new = KU.onboard(prev, rows, root=self.tmp)
        self.assertEqual([r["stock"] for r in new], ["999990"])
        q = hdrmap.load_queue("kdef", self.tmp)
        self.assertEqual([(i["kind"], i["key"], i["status"]) for i in q], [("new_company", "999990", "open")])
        self.assertEqual(KU.onboard(prev, rows, root=self.tmp)[0]["stock"], "999990")   # 멱등(같은 id)
        self.assertEqual(len(hdrmap.load_queue("kdef", self.tmp)), 1)
        # 직전 모집단이 비면(첫 생성) 아무것도 올리지 않는다
        self.assertEqual(KU.onboard([], rows, root=self.tmp), [])

    def test_carry_forward(self):
        prev = {"111110": {"role": "part", "hits": 9}, "222220": {"role": "part", "hits": 8},
                "333330": {"role": "part", "hits": 8, "carried_from": "2025Q4"}}
        promoted, carried = KS.carry_forward(prev, {"444440": {"role": "part"}},
                                             [{"stock": "222220"}], "2026Q2")
        self.assertEqual(list(promoted), ["111110", "333330", "444440"])
        self.assertEqual(carried, ["111110", "333330"])
        self.assertEqual(promoted["111110"]["carried_from"], "2026Q2")
        self.assertEqual(promoted["333330"]["carried_from"], "2025Q4")    # 처음 증거의 분기를 지킨다

    def test_scan_output_has_no_run_time(self):
        """scanned_at(실행 날짜) 제거 — 같은 결과는 같은 바이트. 이미 모집단인 직전 승격분은 이월된다."""
        got = {}
        prev = {"quarter": "2026Q2", "promoted": {"555550": {"role": "part", "hits": 9}}}
        with mock.patch.object(KS, "_get", lambda *a, **k: ""), \
                mock.patch.object(KS, "parse_kind", lambda html: []), \
                mock.patch.object(KS, "load_universe", lambda: [{"stock": "555550"}]), \
                mock.patch.object(KS, "_prev_probe", lambda: prev), \
                mock.patch.object(KS, "write_asset", lambda name, data: got.update({name: data})):
            out = KS.scan("2026Q3", log=_NULL)
        self.assertNotIn("scanned_at", out)
        self.assertEqual(list(out["promoted"]), ["555550"])
        self.assertEqual(out["carried"], ["555550"])
        self.assertIs(got["universe_probe.json"], out)


if __name__ == "__main__":
    unittest.main()
