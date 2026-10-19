# -*- coding: utf-8 -*-
"""kcap_events·kcap_fin 계약 테스트 — 네트워크 없이 fixture 만 쓴다.

fixture(실제 DART 원문):
  ev_006650_생산중단_20261006800696   대한유화 생산중단(정기보수)
  ev_011170_신규시설투자_20260917800509 롯데케미칼 [기재정정] 신규시설투자등(자율공시) — 투자 중단 정정
  ev_009830_영업정지_20240425800253   한화솔루션 영업정지(종속회사의 주요경영사항)
  ev_051910_생산중단_20261008800790   LG화학 [기재정정] 생산중단 — 생산재개예정일자 확정
  fin_006650_2026Q2_cons              대한유화 2026 반기보고서 `2. 연결재무제표` 절
DART 를 두드리는 함수(search_reports·toc·fetch_section)와 assets 쓰기는 모듈 적재 때 전부 막는다 — collect 흐름 테스트는 가짜로 바꿔 돌린다.

실행: cd argus/kcap/tools && python3 -m unittest discover -s tests -p 'test_kcap_events_fin.py'
"""
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import kcap_events as EV           # noqa: E402
import kcap_fin as FIN             # noqa: E402

FX = os.path.join(HERE, "fixtures")
F_DAEHAN = "ev_006650_생산중단_20261006800696.html"
F_LOTTE = "ev_011170_신규시설투자_20260917800509.html"
F_HANWHA = "ev_009830_영업정지_20240425800253.html"
F_LGCHEM = "ev_051910_생산중단_20261008800790.html"
F_FIN = "fin_006650_2026Q2_cons.html"
_LOG = io.StringIO()                       # collect/rebuild 의 진행 로그 — 테스트 출력에 섞이지 않게


def _fx(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return f.read()


def _forbid(*a, **k):
    raise AssertionError("네트워크·assets 쓰기 금지 — 테스트는 fixture 만 쓴다: %r %r" % (a[:2], sorted(k)))


_GUARDED = ("search_reports", "toc", "fetch_section", "write_cache", "write_asset")


def setUpModule():
    """collect() 가 실수로 불려도 DART 에 닿지 못하게 모듈 전역을 막는다."""
    for mod in (EV, FIN):
        for name in _GUARDED:
            setattr(mod, name, _forbid)


class _Patched(unittest.TestCase):
    """모듈 전역을 가짜로 바꿨다가 되돌린다."""

    def _patch(self, mod, **fns):
        saved = {k: getattr(mod, k) for k in fns}
        for k, v in fns.items():
            setattr(mod, k, v)
        self.addCleanup(lambda: [setattr(mod, k, v) for k, v in saved.items()])


# ── classify ────────────────────────────────────────────────────────────────

class TestClassify(unittest.TestCase):
    def test_titles(self):
        table = [
            ("신규시설투자등", "invest"),
            ("신규 시설투자 등(자율공시)", "invest"),
            ("[기재정정]신규시설투자등(자율공시)", "invest"),
            ("생산중단", "halt"),
            ("[기재정정] 생산중단", "halt"),
            ("생산중단(자회사의 주요경영사항)", "halt"),
            ("생산재개", "restart"),
            ("영업정지(종속회사의 주요경영사항)", "suspend"),
            ("영업정지(종속회사의주요경영사항)", "suspend"),
            ("유형자산 양도결정", "asset_sale"),
            ("[첨부정정]유형자산양도결정", "asset_sale"),
            ("유형자산 취득결정(자율공시)", "asset_buy"),
            ("영업양도 결정", "biz_sale"),
            ("영업양수 결정", "biz_buy"),
            ("단일판매ㆍ공급계약체결", None),
            ("타법인주식및출자증권취득결정", None),       # '취득' 이지만 유형자산이 아니다
            ("기업설명회(IR)개최(안내공시)", None),
            ("주요사항보고서(유상증자결정)", None),
            ("", None),
            (None, None),
        ]
        for title, want in table:
            self.assertEqual(EV.classify(title), want, title)

    def test_flags(self):
        self.assertEqual(EV.title_flags("[기재정정]신규시설투자등(자율공시)"), {"corrected": True, "subsidiary": False})
        self.assertEqual(EV.title_flags("[첨부정정]생산중단(자회사의 주요경영사항)"), {"corrected": True, "subsidiary": True})
        self.assertEqual(EV.title_flags("영업정지(종속회사의주요경영사항)"), {"corrected": False, "subsidiary": True})
        self.assertEqual(EV.title_flags("[첨부추가]생산중단"), {"corrected": False, "subsidiary": False})


# ── parse_event — fixture 4건 ───────────────────────────────────────────────

class TestParseDaehan(unittest.TestCase):
    """대한유화 생산중단(2026-10-06) — 정정 없음·자회사 아님."""

    @classmethod
    def setUpClass(cls):
        cls.rec = EV.parse_event(_fx(F_DAEHAN), "20261006800696", "생산중단", "006650")

    def test_head(self):
        r = self.rec
        self.assertEqual((r["type"], r["corrected"], r["subsidiary"], r["subsidiary_name"]), ("halt", False, False, None))
        self.assertEqual((r["rcp"], r["filed"], r["stock"], r["n_tables"]), ("20261006800696", "2026-10-06", "006650", 1))
        self.assertIsNone(r["correction"])
        self.assertIsNone(r["correction_reason"])
        self.assertIsNone(r["corrects_filed"])

    def test_fields(self):
        f = self.rec["fields"]
        self.assertEqual(f["scope"], "대한유화(주) 사업장 전체")
        self.assertEqual(f["amount_krw"], 2828725728648)              # 생산중단 분야의 매출액(원) — 최근매출액이 아니다
        self.assertEqual(f["pct"], 84.49)
        self.assertEqual(f["purpose"], "대한유화(주) 사업장 전체 생산중단")
        self.assertEqual(f["reason"], "정기보수")
        self.assertEqual(f["halt_date"], "2026-10-13")
        self.assertEqual(f["restart_date"], "2026-11-24")
        self.assertEqual(f["decided"], "2026-10-06")
        self.assertIsNone(f["period_start"])
        self.assertIsNone(f["period_end"])
        self.assertIsNone(f["capa_text"])
        self.assertEqual(set(f), set(EV.FIELDS))

    def test_kv_keeps_original_labels(self):
        kv = self.rec["kv"]
        self.assertEqual(kv["1. 생산중단분야"], "대한유화(주) 사업장 전체")
        self.assertEqual(kv["2. 생산중단내역 생산중단 분야의 매출액(원)"], "2,828,725,728,648")
        self.assertEqual(kv["2. 생산중단내역 최근매출액(원)"], "3,347,821,791,902")
        self.assertEqual(kv["2. 생산중단내역 매출액대비(%)"], "84.49")
        self.assertEqual(kv["2. 생산중단내역 대규모법인여부"], "해당")
        self.assertEqual(kv["5. 향후대책"], "정기보수 완료 후 생산재개")
        self.assertEqual(kv["9. 이사회결의일(결정일)"], "2026-10-06")
        self.assertEqual(kv["- 사외이사 참석여부 참석(명)"], "-")
        self.assertEqual(kv["※ 관련공시"], "-")
        self.assertIn("정기보수에 따른 것으로", kv["10. 기타 투자판단과 관련한 중요사항"])
        self.assertEqual(len(kv), 17)


class TestParseLotte(unittest.TestCase):
    """롯데케미칼 [기재정정] 신규시설투자등(자율공시) 2026-09-17 — 투자 중단 정정(정정전 → 정정후)."""

    @classmethod
    def setUpClass(cls):
        cls.rec = EV.parse_event(_fx(F_LOTTE), "20260917800509", "[기재정정]신규시설투자등(자율공시)", "011170")

    def test_head(self):
        r = self.rec
        self.assertEqual((r["type"], r["corrected"], r["subsidiary"], r["filed"], r["n_tables"]), ("invest", True, False, "2026-09-17", 4))
        self.assertEqual(r["correction_reason"], "투자 중단 결정에 따른 기재사항 정정")
        self.assertEqual(r["corrects_filed"], "2023-12-06")           # 정정관련 공시서류제출일 — 앞 공시와 잇는 고리

    def test_correction_table(self):
        c = self.rec["correction"]
        self.assertEqual(c["2. 투자내역 - 투자금액(원)"], {"before": "77,000,000,000", "after": "16,618,835,927"})
        self.assertEqual(c["2. 투자내역 - 자기자본대비(%)"], {"before": "0.56", "after": "0.12"})
        self.assertEqual(c["3. 투자목적"], {"before": "폐PET의 화학적 재활용을 통한 친환경 사업 진출", "after": "-"})
        self.assertEqual(c["4. 투자기간"], {"before": "2021-05-20 ~ 2027-12-31", "after": "2021-05-20 ~ 2026-09-17"})
        self.assertEqual(c["5. 이사회결의일(결정일)"], {"before": "2021-05-20", "after": "2026-09-17"})
        self.assertEqual(c["- 독립(사외)이사 참석여부 참석(명)"], {"before": "6", "after": "5"})
        self.assertIn("7. 기타 투자판단과 관련한 중요사항", c)
        self.assertEqual(len(c), 7)

    def test_fields_are_after_values(self):
        f = self.rec["fields"]
        self.assertEqual(f["amount_krw"], 16618835927)
        self.assertEqual(f["pct"], 0.12)
        self.assertIsNone(f["purpose"])                                 # 정정후 '-' — 추정하지 않고 null
        self.assertEqual(f["scope"], "울산공장 내 폐PET 화학적 재활용 시설 투자")
        self.assertEqual(f["period_start"], "2021-05-20")
        self.assertEqual(f["period_end"], "2026-09-17")
        self.assertEqual(f["decided"], "2026-09-17")
        self.assertIsNone(f["reason"])                                  # '정정사유' 는 사유가 아니다
        self.assertIsNone(f["halt_date"])
        self.assertIsNone(f["restart_date"])
        self.assertIsNone(f["capa_text"])

    def test_kv(self):
        kv = self.rec["kv"]
        self.assertEqual(kv["정정일자"], "2026-09-17")
        self.assertEqual(kv["1. 정정관련 공시서류"], "신규 시설투자 등(자율공시)")
        self.assertEqual(kv["2. 정정관련 공시서류제출일"], "2023-12-06")
        self.assertEqual(kv["1. 투자구분"], "신규시설투자")
        self.assertEqual(kv["- 투자대상"], "울산공장 내 폐PET 화학적 재활용 시설 투자")
        self.assertEqual(kv["2. 투자내역 투자금액(원)"], "16,618,835,927")
        self.assertEqual(kv["2. 투자내역 자기자본(원)"], "13,712,355,293,944")
        self.assertEqual(kv["3. 투자목적"], "-")
        self.assertEqual(kv["4. 투자기간 시작일"], "2021-05-20")
        self.assertEqual(kv["4. 투자기간 종료일"], "2026-09-17")
        self.assertEqual(kv["※ 관련공시"], "2021-05-20 신규시설투자등(자율공시) 2023-12-06 신규시설투자등(자율공시)")

    def test_correction_overlay_wins_over_main_table(self):
        """본표가 옛 값이라도 정정후가 fields 에 들어간다 — 정정 표만 있는 문서를 흉내 낸 합성 HTML."""
        html = ("<table><tr><td>정정항목</td><td>정정전</td><td>정정후</td></tr>"
                "<tr><td>2. 투자내역 - 투자금액(원)</td><td>100</td><td>250</td></tr>"
                "<tr><td>4. 투자기간</td><td>2024-01-01 ~ 2025-12-31</td><td>2024-01-01 ~ 2026-06-30</td></tr></table>"
                "<table><tr><td>2. 투자내역</td><td>투자금액(원)</td><td>100</td><td>100</td></tr>"
                "<tr><td colspan=2>4. 투자기간 시작일</td><td colspan=2>2024-01-01</td></tr></table>")
        r = EV.parse_event(html, "20260101800001", "신규시설투자등")
        self.assertTrue(r["corrected"])                                  # 제목에 배지가 없어도 정정 표가 있으면 정정본
        self.assertEqual(r["fields"]["amount_krw"], 250)
        self.assertEqual((r["fields"]["period_start"], r["fields"]["period_end"]), ("2024-01-01", "2026-06-30"))


class TestParseHanwha(unittest.TestCase):
    """한화솔루션 영업정지(종속회사의 주요경영사항) 2024-04-25 — Hanwha Q CELLS(Qidong)."""

    @classmethod
    def setUpClass(cls):
        cls.rec = EV.parse_event(_fx(F_HANWHA), "20240425800253", "영업정지(종속회사의 주요경영사항)", "009830")

    def test_head(self):
        r = self.rec
        self.assertEqual((r["type"], r["corrected"], r["subsidiary"], r["filed"], r["n_tables"]), ("suspend", False, True, "2024-04-25", 3))
        self.assertEqual(r["subsidiary_name"], "Hanwha Q CELLS(Qidong) Co., Ltd.")
        self.assertIsNone(r["correction"])

    def test_fields(self):
        f = self.rec["fields"]
        self.assertEqual(f["amount_krw"], 531007113166)
        self.assertEqual(f["pct"], 3.996)
        self.assertEqual(f["scope"], "태양광 모듈 생산 및 판매")
        self.assertEqual(f["purpose"], "태양광 모듈 생산 및 판매 중단")
        self.assertEqual(f["reason"], "전사 모듈 생산 운영 효율성 제고")
        self.assertEqual(f["halt_date"], "2024-06-30")
        self.assertEqual(f["decided"], "2024-04-25")
        self.assertIsNone(f["restart_date"])
        self.assertIsNone(f["period_start"])
        self.assertIsNone(f["capa_text"])

    def test_kv_subsidiary_block(self):
        kv = self.rec["kv"]
        self.assertEqual(kv["종속회사인"], "Hanwha Q CELLS(Qidong) Co., Ltd.")
        self.assertEqual(kv["2. 영업정지내역 영업정지금액(원)"], "531,007,113,166")
        self.assertEqual(kv["2. 영업정지내역 최근 지배회사 연결 매출총액(원)"], "13,288,744,762,930")
        self.assertEqual(kv["7. 영업정지일자"], "2024-06-30")
        self.assertEqual(kv["종속회사명"], "Hanwha Q CELLS(Qidong) Co., Ltd.")
        self.assertEqual(kv["종속회사명 영문"], "Hanwha Q CELLS(Qidong) Co., Ltd.")
        self.assertEqual(kv["종속회사의 자산총액(원)"], "567,629,072,389")
        self.assertEqual(kv["지배회사의 연결 자산총액 대비(%)"], "2.318")


class TestParseLGChem(unittest.TestCase):
    """LG화학 [기재정정] 생산중단 2026-10-08 — 여수 NCC 2공장 생산재개예정일자 '-' → 2026-10-12."""

    @classmethod
    def setUpClass(cls):
        cls.rec = EV.parse_event(_fx(F_LGCHEM), "20261008800790", "[기재정정] 생산중단", "051910")

    def test_head(self):
        r = self.rec
        self.assertEqual((r["type"], r["corrected"], r["subsidiary"], r["filed"], r["n_tables"]), ("halt", True, False, "2026-10-08", 4))
        self.assertEqual(r["correction_reason"], "여수 NCC 2공장 가동재개 일정 확정에 따른 정정")
        self.assertEqual(r["corrects_filed"], "2026-03-23")

    def test_correction_table(self):
        c = self.rec["correction"]
        self.assertEqual(c["8. 생산재개예정일자"], {"before": "-", "after": "2026-10-12"})
        self.assertIn("10. 기타 투자판단과 관련한 중요사항", c)
        self.assertEqual(len(c), 2)

    def test_fields(self):
        f = self.rec["fields"]
        self.assertEqual(f["scope"], "LG화학 여수 NCC 2공장")
        self.assertEqual(f["amount_krw"], 2488517000000)
        self.assertEqual(f["pct"], 5.09)
        self.assertEqual(f["purpose"], "여수 NCC 2공장의 일시적 생산중단")
        self.assertTrue(f["reason"].startswith("이란 전쟁 등에 따른 NCC"))
        self.assertEqual(f["halt_date"], "2026-03-23")
        self.assertEqual(f["restart_date"], "2026-10-12")
        self.assertEqual(f["decided"], "2026-03-23")
        self.assertIsNone(f["capa_text"])
        self.assertEqual(self.rec["kv"]["2. 생산중단내역 최근매출액(원)"], "48,916,104,472,005")

    def test_corrected_without_badge_in_title(self):
        """캐시 <title> 에는 [기재정정] 배지가 없다 — 정정 표만으로도 corrected."""
        r = EV.parse_event(_fx(F_LGCHEM), "20261008800790", "생산중단")
        self.assertTrue(r["corrected"])
        self.assertEqual(r["corrects_filed"], "2026-03-23")
        self.assertEqual(r["fields"]["restart_date"], "2026-10-12")

    def test_title_from_cached_html(self):
        self.assertEqual(EV._title_from_html(_fx(F_LGCHEM)), "생산중단")
        self.assertEqual(EV._title_from_html(_fx(F_HANWHA)), "영업정지(종속회사의 주요경영사항)")
        self.assertEqual(EV._title_from_html(_fx(F_LOTTE)), "신규시설투자등(자율공시)")


class TestCapaText(unittest.TestCase):
    def test_extract_only(self):
        html = "<table><tr><td>3. 투자목적</td><td>연산 80만톤 규모 NCC 증설로 에틸렌 생산능력 확대</td></tr></table>"
        r = EV.parse_event(html, "20250101800001", "신규시설투자등")
        self.assertIn("80만톤", r["fields"]["capa_text"])
        self.assertEqual(EV.capa_text("설비 CAPA 는 연 30 천톤"), "설비 CAPA 는 연 30 천톤")
        self.assertIn("톤/년", EV.capa_text("x" * 100 + " 120,000톤/년 " + "y" * 100))
        self.assertLessEqual(len(EV.capa_text("x" * 100 + " 120,000톤/년 " + "y" * 100)), 40 + len(" 120,000톤/년 ") + 40)
        self.assertIsNone(EV.capa_text("생산능력 확대 1,000톤 규모"))      # 'N톤' 만으로는 잡지 않는다(규약: 만톤·천톤·톤/년·capa)
        self.assertIsNone(EV.capa_text(""))


# ── supersede ───────────────────────────────────────────────────────────────

def _ev(rcp, etype, corrected=False, corrects_filed=None, **fields):
    f = dict.fromkeys(EV.FIELDS)
    f.update(fields)
    return {"rcp": rcp, "filed": EV._filed(rcp), "type": etype, "corrected": corrected,
            "corrects_filed": corrects_filed, "fields": f}


class TestSupersede(unittest.TestCase):
    def test_chain_by_filed_and_key(self):
        a = _ev("20210520800001", "invest", scope="울산공장 내 폐PET 시설", period_start="2021-05-20", decided="2021-05-20")
        b = _ev("20231206800002", "invest", corrected=True, corrects_filed="2021-05-20",
                scope="울산공장 내 폐PET 시설", period_start="2021-05-20", decided="2021-05-20")
        c = _ev("20260917800509", "invest", corrected=True, corrects_filed="2023-12-06",
                scope="울산공장 내 폐PET 시설", period_start="2021-05-20", decided="2026-09-17")   # 이사회결의일이 바뀌어도 이어진다
        d = _ev("20260323800100", "halt", scope="LG화학 여수 NCC 2공장", decided="2026-03-23")
        e = _ev("20261008800790", "halt", corrected=True, scope="LG화학 여수 NCC 2공장", decided="2026-03-23")   # 키로 연결
        f = _ev("20251001800050", "halt", scope="다른 공장", decided="2025-10-01")
        g = _ev("20250101800009", "restart")                                                             # 키 없음 — 덮지도 덮이지도 않는다
        out = EV.supersede([e, d, c, b, a, f, g])
        by = {x["rcp"]: x for x in out}
        self.assertEqual([x["rcp"] for x in out], sorted(by))                 # 접수번호 순
        self.assertEqual(by[b["rcp"]]["supersedes"], a["rcp"])
        self.assertEqual(by[c["rcp"]]["supersedes"], b["rcp"])
        self.assertEqual(by[a["rcp"]]["superseded_by"], b["rcp"])
        self.assertEqual(by[b["rcp"]]["superseded_by"], c["rcp"])
        self.assertIsNone(by[c["rcp"]]["superseded_by"])
        self.assertEqual(by[e["rcp"]]["supersedes"], d["rcp"])
        self.assertEqual(by[d["rcp"]]["superseded_by"], e["rcp"])
        self.assertIsNone(by[f["rcp"]]["supersedes"])
        self.assertIsNone(by[f["rcp"]]["superseded_by"])
        self.assertIsNone(by[g["rcp"]]["supersedes"])
        self.assertEqual(sorted(x["rcp"] for x in EV.active_events(out)), sorted([c["rcp"], e["rcp"], f["rcp"], g["rcp"]]))
        self.assertEqual(len(out), 7)                                          # 이력 보존 — 덮인 것도 남는다

    def test_scope_normalization_and_ambiguity(self):
        a = _ev("20250101800001", "halt", scope="대한유화(주) 사업장 전체", decided="2025-01-01")
        b = _ev("20250301800002", "halt", scope="대한유화 사업장전체", decided="2025-01-01")             # (주)·공백 차이는 같은 키
        out = EV.supersede([a, b])
        self.assertEqual(out[1]["supersedes"], a["rcp"])
        # 같은 날 같은 type 이 둘이고 scope 도 다르면 '정정관련 공시서류제출일' 로는 못 잇는다 — 키로도 못 이으면 독립 이벤트
        x = _ev("20250601800001", "halt", scope="A공장", decided="2025-06-01")
        y = _ev("20250601800002", "halt", scope="B공장", decided="2025-06-01")
        z = _ev("20250701800003", "halt", corrected=True, corrects_filed="2025-06-01", scope="C공장", decided="2025-07-01")
        out = EV.supersede([x, y, z])
        self.assertIsNone(out[2]["supersedes"])
        # scope 가 같으면 그쪽으로 잇는다
        z2 = _ev("20250701800004", "halt", corrected=True, corrects_filed="2025-06-01", scope="B공장", decided="2025-07-01")
        out = EV.supersede([x, y, z2])
        self.assertEqual(out[2]["supersedes"], y["rcp"])

    def test_parsed_fixtures_do_not_collide(self):
        recs = [EV.parse_event(_fx(F_DAEHAN), "20261006800696", "생산중단"),
                EV.parse_event(_fx(F_LGCHEM), "20261008800790", "[기재정정] 생산중단"),
                EV.parse_event(_fx(F_LOTTE), "20260917800509", "[기재정정]신규시설투자등(자율공시)"),
                EV.parse_event(_fx(F_HANWHA), "20240425800253", "영업정지(종속회사의 주요경영사항)")]
        out = EV.supersede(recs)
        self.assertEqual([r["supersedes"] for r in out], [None] * 4)
        self.assertEqual(len(EV.active_events(out)), 4)


# ── collect 흐름(가짜 DART·가짜 캐시) ───────────────────────────────────────

class TestYearWindows(unittest.TestCase):
    def test_windows(self):
        self.assertEqual(EV.year_windows("20240101", "20261017"),
                         [("20240101", "20241231"), ("20250101", "20251231"), ("20260101", "20261017")])
        self.assertEqual(EV.year_windows("20240315", "20240601"), [("20240315", "20240601")])
        self.assertEqual(EV.year_windows("20261231", "20261231"), [("20261231", "20261231")])
        self.assertEqual(EV.year_windows("20270101", "20261231"), [])


class TestEventsCollect(_Patched):
    RCPS = {"20261006800696": F_DAEHAN, "20260917800509": F_LOTTE, "20240425800253": F_HANWHA, "20261008800790": F_LGCHEM}
    LISTING = {
        "2024": [("20240425800253", "영업정지(종속회사의 주요경영사항)"), ("20240301800001", "단일판매ㆍ공급계약체결")],
        "2025": [],
        "2026": [("20261008800790", "[기재정정]생산중단"), ("20261006800696", "생산중단"),
                 ("20260917800509", "[기재정정]신규시설투자등(자율공시)"), ("20260105800002", "기업설명회(IR)개최(안내공시)")],
    }

    def setUp(self):
        self.calls = {"search": [], "toc": [], "fetch": []}
        self.cache, self.assets = {}, {}
        self.fail_fetch = set()

        def search(stock, start, end, kind):
            self.assertEqual(kind, "I001")
            self.calls["search"].append((start, end))
            return list(self.LISTING.get(start[:4], []))

        def toc_(rcp):
            self.calls["toc"].append(rcp)
            return [{"text": "본문", "rcpNo": rcp, "dcmNo": "1", "eleId": "0", "offset": "0", "length": "0", "dtd": "HTML"}]

        def fetch(node):
            self.calls["fetch"].append(node["rcpNo"])
            if node["rcpNo"] in self.fail_fetch:
                raise OSError("timed out")
            return _fx(self.RCPS[node["rcpNo"]])

        self._patch(EV, search_reports=search, toc=toc_, fetch_section=fetch,
                    read_cache=lambda s, n: self.cache.get((s, n)),
                    write_cache=lambda s, n, t: self.cache.__setitem__((s, n), t),
                    write_asset=lambda n, d: self.assets.__setitem__(n, d),
                    load_asset=lambda n, default=None: self.assets.get(n, default))

    def test_collect_filters_caches_and_writes(self):
        res = EV.collect("006650", "대한유화", since="20240101", until="20261017", log=_LOG)
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(self.calls["search"], [("20240101", "20241231"), ("20250101", "20251231"), ("20260101", "20261017")])
        self.assertEqual(self.calls["fetch"], sorted(self.RCPS))            # classify 된 것만, 접수번호 순
        self.assertEqual(res["fetched"], 4)
        self.assertIn(("006650", "ev_20261006800696.html"), self.cache)
        self.assertIn(("006650", "ev_20261006800696.meta.json"), self.cache)
        data = self.assets["events/006650.json"]
        self.assertEqual((data["n"], data["n_active"], data["stock"], data["name"]), (4, 4, "006650", "대한유화"))
        self.assertEqual(sorted(e["type"] for e in data["events"]), ["halt", "halt", "invest", "suspend"])
        self.assertEqual([e["rcp"] for e in data["events"]], sorted(self.RCPS))
        lg = [e for e in data["events"] if e["rcp"] == "20261008800790"][0]
        self.assertEqual(lg["title"], "[기재정정]생산중단")
        self.assertTrue(lg["corrected"])
        # 두 번째 실행 — 캐시 적중이라 본문 요청 0, 검색만 다시
        res2 = EV.collect("006650", "대한유화", since="20240101", until="20261017", log=_LOG)
        self.assertTrue(res2["ok"])
        self.assertEqual(res2["fetched"], 0)
        self.assertEqual(len(self.calls["fetch"]), 4)
        self.assertEqual(len(self.calls["search"]), 6)
        self.assertEqual(self.assets["events/006650.json"]["n"], 4)

    def test_fetch_failure_is_recorded_not_cached(self):
        self.fail_fetch.add("20261006800696")
        res = EV.collect("006650", "대한유화", since="20240101", until="20261017", log=_LOG)
        self.assertFalse(res["ok"])
        self.assertTrue(res["written"])
        self.assertEqual([e["rcp"] for e in res["errors"]], ["20261006800696"])
        self.assertEqual(res["errors"][0]["stage"], "fetch")
        self.assertNotIn(("006650", "ev_20261006800696.html"), self.cache)   # 실패는 캐시하지 않는다
        self.assertEqual(self.assets["events/006650.json"]["n"], 3)
        # 다음 실행에서 빠진 것만 다시 받고 원장에 합쳐진다
        self.fail_fetch.clear()
        res = EV.collect("006650", "대한유화", since="20240101", until="20261017", log=_LOG)
        self.assertTrue(res["ok"])
        self.assertEqual(res["fetched"], 1)
        self.assertEqual(self.assets["events/006650.json"]["n"], 4)

    def test_search_failure_keeps_existing_file(self):
        self.assets["events/006650.json"] = {"events": [{"rcp": "20200101800001", "type": "halt", "fields": {}}], "n": 1}

        def search(stock, start, end, kind):
            if start[:4] == "2025":
                raise OSError("urlopen error timed out")
            return list(self.LISTING.get(start[:4], []))
        self._patch(EV, search_reports=search)
        res = EV.collect("006650", "대한유화", since="20240101", until="20261017", log=_LOG)
        self.assertFalse(res["ok"])
        self.assertFalse(res["written"])
        self.assertEqual(res["errors"][0]["stage"], "search")
        self.assertEqual(self.assets["events/006650.json"]["n"], 1)         # 기존 파일 그대로
        self.assertEqual(res["fetched"], 4)                                   # 받은 본문은 캐시에 남아 재실행이 싸다

    def test_truncated_window_is_split(self):
        def search(stock, start, end, kind):
            self.calls["search"].append((start, end))
            d0, d1 = EV._d(start), EV._d(end)
            if (d1 - d0).days > 200:
                return [("%s8%05d" % (start, i), "기타 경영사항(자율공시)") for i in range(EV.MAX_RESULTS)]   # 상한에 걸린 창
            return [("20240425800253", "영업정지(종속회사의 주요경영사항)")] if start[:4] == "2024" else []
        self._patch(EV, search_reports=search)
        res = EV.collect("006650", "대한유화", since="20240101", until="20261017", log=_LOG)
        self.assertTrue(res["ok"], res["errors"])
        self.assertIn(("20240101", "20241231"), self.calls["search"])
        self.assertIn(("20240101", "20240701"), self.calls["search"])         # 반으로 쪼갠 창
        self.assertIn(("20240702", "20241231"), self.calls["search"])
        self.assertEqual(len(self.calls["search"]), 9)
        self.assertEqual(self.calls["fetch"], ["20240425800253"])

    def test_rebuild_from_cache_only(self):
        for rcp, name in self.RCPS.items():
            self.cache[("006650", "ev_%s.html" % rcp)] = _fx(name)
        self.cache[("006650", "ev_20261008800790.meta.json")] = '{"rcp": "20261008800790", "title": "[기재정정]생산중단"}'

        def listdir(folder):
            return sorted("ev_%s.html" % r for r in self.RCPS)
        self._patch(EV, search_reports=_forbid, toc=_forbid, fetch_section=_forbid)
        self._patch(EV.os, listdir=listdir)
        self._patch(EV.os.path, isdir=lambda p: True)
        res = EV.rebuild("006650", "대한유화", log=_LOG)
        self.assertTrue(res["ok"], res["errors"])
        data = self.assets["events/006650.json"]
        self.assertEqual(data["n"], 4)
        by = {e["rcp"]: e for e in data["events"]}
        self.assertEqual(by["20261008800790"]["title"], "[기재정정]생산중단")   # 메타가 있으면 메타 제목
        self.assertEqual(by["20261006800696"]["title"], "생산중단")            # 없으면 <title> 에서
        self.assertTrue(by["20260917800509"]["corrected"])                    # 배지 없이도 정정 표로 판정
        self.assertEqual(by["20240425800253"]["type"], "suspend")


# ── kcap_fin ────────────────────────────────────────────────────────────────

class TestFinNode(unittest.TestCase):
    def test_cons_first_then_sep_and_skip_notes(self):
        nodes = [{"text": "1. 요약재무정보"}, {"text": "2. 연결재무제표"}, {"text": "3. 연결재무제표 주석"},
                 {"text": "4. 재무제표"}, {"text": "5. 재무제표 주석"}]
        node, basis = FIN.fin_node(nodes)
        self.assertEqual((node["text"], basis), ("2. 연결재무제표", "cons"))
        node, basis = FIN.fin_node([{"text": "1. 요약재무정보"}, {"text": "2. 재무제표"}, {"text": "3. 재무제표 주석"}])
        self.assertEqual((node["text"], basis), ("2. 재무제표", "sep"))
        self.assertEqual(FIN.fin_node([{"text": "3. 연결재무제표 주석"}, {"text": "Ⅲ. 재무에 관한 사항"}]), (None, None))
        self.assertEqual(FIN.fin_node([]), (None, None))
        self.assertEqual(FIN.fin_node([{"text": "２. 연결재무제표"}])[1], "cons")      # 전각 숫자

    def test_title_ok(self):
        self.assertTrue(FIN._title_ok("반기보고서 (2026.06)", "2026Q2"))
        self.assertTrue(FIN._title_ok("[기재정정]사업보고서 (2025.12)", "2025Q4"))
        self.assertFalse(FIN._title_ok("분기보고서 (2026.03)", "2026Q2"))
        self.assertFalse(FIN._title_ok("정정신고(보고)", "2026Q2"))

    def test_parse_quarters(self):
        self.assertEqual(FIN.parse_quarters("2024Q3..2025Q2"), ["2024Q3", "2024Q4", "2025Q1", "2025Q2"])
        self.assertEqual(FIN.parse_quarters("2026Q1,2026Q2"), ["2026Q1", "2026Q2"])
        self.assertEqual(FIN.parse_quarters(""), [])


class TestParseQuarter(unittest.TestCase):
    """대한유화 2026 반기보고서 연결 포괄손익계산서 — 제58기 반기 3개월·누적 열, (단위: 원) → 백만원."""

    @classmethod
    def setUpClass(cls):
        cls.p = FIN.parse_quarter(_fx(F_FIN), "2026Q2", basis="cons", rcp="20260814000000")

    def test_three_month_column(self):
        cur = self.p["cur"]
        self.assertEqual(cur["매출액"], 956254.32)        # 956,254,316,742 원
        self.assertEqual(cur["영업이익"], -3876.53)       # (3,876,526,721) 원 — 괄호 음수
        self.assertEqual(cur["당기순이익"], -1466.15)     # 반기순이익(손실) 3개월 (1,466,147,003)

    def test_ytd_column(self):
        y = self.p["cur_ytd"]
        self.assertEqual(y["매출액"], 1803360.56)         # 1,803,360,563,654 원
        self.assertEqual(y["영업이익"], 69686.05)         # 69,686,047,732 원
        self.assertEqual(y["당기순이익"], 65802.59)       # 65,802,587,170 원

    def test_meta(self):
        p = self.p
        self.assertEqual((p["q"], p["basis"], p["rcp"], p["unit"], p["unit_assumed"]), ("2026Q2", "cons", "20260814000000", "백만원", False))
        self.assertEqual(p["tags_seen"], ["cur_q", "cur_ytd", "prev_q", "prev_ytd"])
        self.assertIn("cis", p["found"])                   # 단일 포괄손익계산서 회사 — kship_fin 이 cis 에서 IS 를 읽는다
        self.assertEqual(p["flags"], [])

    def test_series_from_fixture_uses_3m_column(self):
        s = FIN.build_series({"2026Q2": self.p})["quarters"]
        self.assertEqual(len(s), 1)
        r = s[0]
        self.assertEqual((r["q"], r["basis"], r["src"], r["unit"]), ("2026Q2", "cons", "3m_column", "백만원"))
        self.assertEqual((r["rev_q"], r["op_q"], r["ni_q"]), (956254.32, -3876.53, -1466.15))
        self.assertEqual((r["rev_ytd"], r["op_ytd"]), (1803360.56, 69686.05))
        self.assertEqual(r["flags"], [])                   # 직전 누적이 없어도 3개월 열이 있으면 flag 없음

    def test_no_income_statement(self):
        p = FIN.parse_quarter("<p>본문 없음</p>", "2026Q2")
        self.assertIsNone(p["cur"])
        self.assertIsNone(p["cur_ytd"])
        self.assertIn("no_income_statement", p["flags"])
        s = FIN.build_series({"2026Q2": p})["quarters"][0]
        self.assertEqual((s["rev_q"], s["op_q"], s["src"]), (None, None, None))
        self.assertIn("no_income_data", s["flags"])


def _q(q, ytd=None, cur=None, basis="cons"):
    def m(t):
        return None if t is None else {"매출액": t[0], "영업이익": t[1], "당기순이익": t[2]}
    return {"q": q, "basis": basis, "rcp": "r" + q, "unit": "백만원", "unit_assumed": False, "found": [], "tags_seen": [],
            "cur": m(cur), "cur_ytd": m(ytd), "flags": []}


class TestBuildSeriesYtdDiff(unittest.TestCase):
    """누적차분 — Q1 = 누적, Qn = 누적 − 직전 분기 누적, Q4 = 연간 − 3Q 누적. 직전 누적 없으면 null + flag."""

    def test_q1_to_q4(self):
        per_q = {
            "2025Q1": _q("2025Q1", ytd=(100.0, 10.0, 8.0)),
            "2025Q2": _q("2025Q2", ytd=(250.0, 25.0, 20.0)),
            "2025Q3": _q("2025Q3", ytd=(450.0, 40.0, 30.0)),
            "2025Q4": _q("2025Q4", ytd=(700.0, 70.0, 55.5)),                 # 사업보고서 연간(cur_full)
        }
        s = {r["q"]: r for r in FIN.build_series(per_q)["quarters"]}
        self.assertEqual((s["2025Q1"]["rev_q"], s["2025Q1"]["op_q"], s["2025Q1"]["src"], s["2025Q1"]["how"]), (100.0, 10.0, "ytd_diff", "ytd_as_3m(Q1)"))
        self.assertEqual((s["2025Q2"]["rev_q"], s["2025Q2"]["op_q"], s["2025Q2"]["how"]), (150.0, 15.0, "ytd_minus_prev_ytd"))
        self.assertEqual((s["2025Q3"]["rev_q"], s["2025Q3"]["op_q"], s["2025Q3"]["ni_q"]), (200.0, 15.0, 10.0))
        self.assertEqual((s["2025Q4"]["rev_q"], s["2025Q4"]["op_q"], s["2025Q4"]["ni_q"], s["2025Q4"]["how"]), (250.0, 30.0, 25.5, "annual_minus_9M"))
        for q in per_q:
            self.assertEqual(s[q]["src"], "ytd_diff")
            self.assertEqual(s[q]["unit"], "백만원")
            self.assertEqual(s[q]["flags"], [])
        self.assertEqual([r["q"] for r in FIN.build_series(per_q)["quarters"]], sorted(per_q))

    def test_missing_prior_ytd_is_null_with_flag(self):
        per_q = {"2026Q3": _q("2026Q3", ytd=(900.0, 90.0, 70.0)),             # 2026Q2 없음
                 "2024Q4": _q("2024Q4", ytd=(800.0, 80.0, 60.0))}             # 2024Q3 없음 — 연간만으로 Q4 를 만들지 않는다
        s = {r["q"]: r for r in FIN.build_series(per_q)["quarters"]}
        self.assertEqual((s["2026Q3"]["rev_q"], s["2026Q3"]["op_q"], s["2026Q3"]["src"]), (None, None, None))
        self.assertIn("no_prior_ytd:2026Q2", s["2026Q3"]["flags"])
        self.assertEqual((s["2024Q4"]["rev_q"], s["2024Q4"]["src"]), (None, None))
        self.assertIn("no_prior_ytd:2024Q3", s["2024Q4"]["flags"])
        self.assertEqual(s["2026Q3"]["rev_ytd"], 900.0)                        # 누적은 그대로 싣는다

    def test_prior_year_q4_is_not_used_for_q1(self):
        per_q = {"2025Q4": _q("2025Q4", ytd=(700.0, 70.0, 55.0)), "2026Q1": _q("2026Q1", ytd=(120.0, 12.0, 9.0))}
        s = {r["q"]: r for r in FIN.build_series(per_q)["quarters"]}
        self.assertEqual((s["2026Q1"]["rev_q"], s["2026Q1"]["op_q"], s["2026Q1"]["how"]), (120.0, 12.0, "ytd_as_3m(Q1)"))

    def test_three_month_column_wins_and_mismatch_is_flagged(self):
        per_q = {"2026Q1": _q("2026Q1", ytd=(120.0, 12.0, 9.0), cur=(120.0, 12.0, 9.0)),
                 "2026Q2": _q("2026Q2", ytd=(260.0, 30.0, 20.0), cur=(140.0, 15.0, 11.0))}   # 영업이익: 차분 18 vs 3개월 열 15
        s = {r["q"]: r for r in FIN.build_series(per_q)["quarters"]}
        self.assertEqual((s["2026Q2"]["rev_q"], s["2026Q2"]["op_q"], s["2026Q2"]["src"]), (140.0, 15.0, "3m_column"))
        self.assertEqual(s["2026Q2"]["flags"], ["ytd_diff_mismatch:영업이익:3.0"])
        self.assertEqual(s["2026Q1"]["flags"], [])
        self.assertIsNone(s["2026Q2"]["how"])

    def test_partial_prev_values(self):
        per_q = {"2025Q1": _q("2025Q1", ytd=(100.0, None, 8.0)), "2025Q2": _q("2025Q2", ytd=(250.0, 25.0, 20.0))}
        s = {r["q"]: r for r in FIN.build_series(per_q)["quarters"]}
        self.assertEqual((s["2025Q2"]["rev_q"], s["2025Q2"]["op_q"], s["2025Q2"]["ni_q"]), (150.0, None, 12.0))   # 직전 영업이익 없음 → null


class TestFinCollect(_Patched):
    def setUp(self):
        self.calls = {"search": [], "toc": [], "fetch": []}
        self.cache, self.assets = {}, {}
        self.listing = [("20260814000123", "반기보고서 (2026.06)")]

        def search(stock, start, end, kind):
            self.calls["search"].append((stock, start, end, kind))
            return list(self.listing)

        def toc_(rcp):
            self.calls["toc"].append(rcp)
            return [{"text": "1. 요약재무정보", "rcpNo": rcp, "dcmNo": "1"}, {"text": "2. 연결재무제표", "rcpNo": rcp, "dcmNo": "1", "eleId": "7"},
                    {"text": "3. 연결재무제표 주석", "rcpNo": rcp, "dcmNo": "1"}, {"text": "4. 재무제표", "rcpNo": rcp, "dcmNo": "1"}]

        def fetch(node):
            self.calls["fetch"].append(node["text"])
            return _fx(F_FIN)

        self._patch(FIN, search_reports=search, toc=toc_, fetch_section=fetch,
                    read_cache=lambda s, n: self.cache.get((s, n)),
                    write_cache=lambda s, n, t: self.cache.__setitem__((s, n), t),
                    write_asset=lambda n, d: self.assets.__setitem__(n, d),
                    load_asset=lambda n, default=None: self.assets.get(n, default))

    def test_collect_sequential_cache_and_asset(self):
        res = FIN.collect("006650", "대한유화", ["2026Q2"], log=_LOG)
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(self.calls["search"], [("006650", "20260701", "20261127", "A002")])   # search_window·report_kind
        self.assertEqual(self.calls["fetch"], ["2. 연결재무제표"])
        self.assertIn(("006650", "2026Q2_fin.html"), self.cache)
        data = self.assets["fin/006650.json"]
        q = data["quarters"]["2026Q2"]
        self.assertEqual((q["basis"], q["rcp"], q["title"]), ("cons", "20260814000123", "반기보고서 (2026.06)"))
        self.assertEqual(q["cur"]["영업이익"], -3876.53)
        self.assertEqual(q["cur_ytd"]["매출액"], 1803360.56)
        self.assertEqual(data["series"][0]["src"], "3m_column")
        self.assertEqual(data["series"][0]["rev_q"], 956254.32)
        # 두 번째 실행 — 캐시 적중, 요청 0
        FIN.collect("006650", "대한유화", ["2026Q2"], log=_LOG)
        self.assertEqual(len(self.calls["search"]), 1)
        self.assertEqual(len(self.calls["fetch"]), 1)

    def test_wrong_period_title_is_not_opened(self):
        self.listing = [("20260515000001", "분기보고서 (2026.03)")]
        res = FIN.collect("006650", "대한유화", ["2026Q2"], log=_LOG)
        self.assertFalse(res["ok"])
        self.assertFalse(res["written"])                                       # 파싱된 분기가 없으면 산출 파일을 건드리지 않는다
        self.assertEqual(self.calls["fetch"], [])
        self.assertEqual(res["errors"][0]["stage"], "search")
        self.assertNotIn("fin/006650.json", self.assets)

    def test_existing_quarters_are_kept(self):
        self.assets["fin/006650.json"] = {"quarters": {"2026Q1": _q("2026Q1", ytd=(900000.0, 50000.0, 40000.0), cur=(900000.0, 50000.0, 40000.0))}}
        res = FIN.collect("006650", "대한유화", ["2026Q2"], log=_LOG)
        self.assertTrue(res["ok"])
        data = self.assets["fin/006650.json"]
        self.assertEqual(sorted(data["quarters"]), ["2026Q1", "2026Q2"])
        self.assertEqual([r["q"] for r in data["series"]], ["2026Q1", "2026Q2"])
        self.assertEqual(data["series"][1]["src"], "3m_column")


if __name__ == "__main__":
    unittest.main()
