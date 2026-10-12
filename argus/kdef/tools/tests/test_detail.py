#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""방산 디테일화(2026-10) 테스트 — 추가 수집 없이 사전·판정·화면 조각으로 만든 축을 지킨다.

  · 계통 사전 — SPACE 신설, 군위성→C4I, 민수 어휘 + 되짚기(TICN용·해군·국방 조달기관 상대)
  · 수출 재판정 — 상대 ∨ 공급지역(국내 화이트리스트) ∨ 체계업체 경유 간접수출
  · 계약유형 — 수출사업 이행(EXPORT_EXEC): 이름으로, 이름이 없으면 G2G 상대로
  · 유형×상대 매트릭스 합 = 원장 합 · 종료연도별 인도 일정 · II-4 납기 연도 · 수량 축 · 해지 pill
  · 색 세 벌(kdef_lib.PALETTE · kdef.css --sN · kdef_orders_views.DOMAINS) 일치
  · 생성 사전(assets/domains.json·contract_types.json)이 build_dicts 코드와 같다(stale 방지)

    python3 -m unittest discover -s tests
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import build_dicts                                                   # noqa: E402
import kdef_contracts as KC                                          # noqa: E402
import kdef_orders_views as OV                                       # noqa: E402
import kdef_page as KP                                               # noqa: E402
from kdef_lib import KDEF, PALETTE, is_segment_label, load_asset, slot_color   # noqa: E402


def _data():
    """kdef_page.load_all 의 사전 부분만 — 보고서·모집단은 비운다."""
    doms = load_asset("domains.json")["domains"]
    ctypes = load_asset("contract_types.json")["types"]
    return {"doms": {d["id"]: d for d in doms}, "dom_order": [d["id"] for d in doms],
            "ctypes": {c["id"]: c for c in ctypes}, "ctype_order": [c["id"] for c in ctypes] + ["UNKNOWN"],
            "by_stock": {}, "reports": {}, "contracts": [], "sup": {}, "uni": [], "quarters": [],
            "tax": {"cats": []}, "probe": {}}


def _c(**kw):
    """원장 한 행(contracts.json 의 필드 전부)."""
    row = {"rcp": "20260101000001", "stock": "012450", "title": "단일판매ㆍ공급계약체결", "corrected": False,
           "name": "K9자주포 후속양산", "domain": "GROUND", "domain_hint": None, "ctype": "FOLLOW",
           "civil": False, "amt_krw_m": 1000.0, "rev_ratio": None, "party": "방위사업청", "party_kind": "GOV",
           "party_prime": None, "region": "대한민국", "export": False, "export_kind": "", "export_basis": "",
           "start": "2026-01-01", "end": "2027-12-31", "years": 2.0, "end_raw": "2027-12-31",
           "signed": "2026-01-01", "advance": "", "payterm": "", "def_payrule": False,
           "withheld": "", "withheld_until": "", "note": ""}
    row.update(kw)
    return row


class TestDomains(unittest.TestCase):
    def test_space(self):
        """우주 계통 — 발사체·위성체는 SPACE, `425사업 SAR위성체`는 체계 이름(ISR)이 이긴다."""
        self.assertEqual(KC.domain_of("누리호 엔진 컴포넌트 제작"), "SPACE")
        self.assertEqual(KC.domain_of("차세대발사체 1단 엔진 시험설비"), "SPACE")
        self.assertEqual(KC.domain_of("425사업 SAR위성체 구성품"), "ISR")
        self.assertEqual(KC.domain_of("초소형위성체계 EO위성체"), "ISR")      # 군 정찰위성 사업 — `위성체계`≠`위성체`
        self.assertEqual(KC.domain_of("정지궤도 기상.우주기상 위성 시스템 및 본체개발"), "SPACE")
        self.assertIn("SPACE", {d["id"] for d in load_asset("domains.json")["domains"]})

    def test_gunwisung_c4i(self):
        """`군위성통신체계`는 통신 체계다 — 유도무기(MISSILE)로 가면 안 된다."""
        self.assertEqual(KC.domain_of("군위성통신체계-II 단말 양산"), "C4I")
        self.assertEqual(KC.domain_of("천궁Ⅱ 다기능레이다 수출"), "MISSILE")

    def test_civil_guard(self):
        """민수 어휘는 맞아도 군 용도·국방 조달 상대면 되짚는다. 민항기·은행 IT 는 민수."""
        self.assertNotEqual(KC.domain_of("발전기세트(디젤엔진식)[TICN용]"), "CIVIL")
        self.assertEqual(KC.domain_of("해군함정용 조타기 공급"), "NAVAL")
        self.assertNotEqual(KC.domain_of("발전기세트(제어장치 포함)", party="방위사업청"), "CIVIL")
        self.assertNotEqual(KC.domain_of("전자신호처리부 양산"), "CIVIL")          # `신호` 홀로는 민수 아님
        self.assertEqual(KC.domain_of("SA Wing 구조물 공급"), "CIVIL")
        self.assertEqual(KC.domain_of("GE9X 엔진 부품 공급"), "CIVIL")
        self.assertEqual(KC.domain_of("IBK 차세대 은행 S/W 구축"), "CIVIL")
        self.assertEqual(KC.domain_of("VX4 eVTOL 기체 공급"), "CIVIL")
        # `Plant` 홀로는 민수 어휘가 아니다 — 한화에어로(체계업체) 발주 MCS Plant 2건(5,212억)은 공시에 용도가
        # 없어 민수로 단정하지 않고 계통 미상(방산 집계 안)에 둔다. `시스템 구축`(민수 어휘)도 건너뛴다.
        self.assertIsNone(KC.domain_of("MCS Plant 구축 공사", party="한화에어로스페이스(주)"))
        self.assertIsNone(KC.domain_of("MCS Plant 지능화 물류 시스템 구축", party="한화에어로스페이스(주)"))
        self.assertIsNone(KC.part_hint("MCS Plant 구축 공사"))
        self.assertIsNone(KC.domain_of("Plant 공사"))
        self.assertEqual(KC.domain_of("광양 No.8 CGL 신설 (EP) H2 Plant"), "CIVIL")
        self.assertEqual(KC.domain_of("H2 Plant 모듈 제작"), "CIVIL")

    def test_part_hint(self):
        """계통 미상이라도 부품 이름이 있으면 '부품(계통 미상)'으로 가른다."""
        self.assertIsNone(KC.domain_of("관성측정장치(IMU) 공급"))
        self.assertEqual(KC.part_hint("관성측정장치(IMU) 공급"), "PART")
        self.assertEqual(KC.part_hint("자이로 칩 공급"), "PART")
        self.assertIsNone(KC.part_hint("잠수함 3척"))
        self.assertEqual(KP.dom_key({"domain": None, "domain_hint": "PART"}), "PART")
        self.assertEqual(KP.dom_key({"domain": None, "domain_hint": None}), "UNKNOWN")
        self.assertEqual(KP.dom_meta(_data(), "PART")["ko"], "부품(계통 미상)")

    def test_dict_assets_fresh(self):
        """커밋된 사전 JSON 은 build_dicts 코드에서 생성한 것과 같아야 한다(손으로 고치지 않는다)."""
        self.assertEqual(load_asset("domains.json"), build_dicts.build_domains())
        self.assertEqual(load_asset("contract_types.json"), build_dicts.build_types())


class TestExport(unittest.TestCase):
    def test_party_government(self):
        """`폴란드 정부`·`해외 정부기관`은 G2G, `정부출연연구기관`은 GOV, `타이중 시정부`는 FOREIGN."""
        self.assertEqual(KC.party_kind("폴란드 정부")[0], "G2G")
        self.assertEqual(KC.party_kind("해외 정부기관")[0], "G2G")
        self.assertEqual(KC.party_kind("정부출연연구기관")[0], "GOV")
        self.assertEqual(KC.party_kind("대한민국 정부")[0], "GOV")
        self.assertNotEqual(KC.party_kind("Taichung City Government")[0], "G2G")
        # 맨 `정부`는 fail-open 이었다 — 국내 정부 시설·기관은 GOV(내수), `○○ 정부`는 이름 끝에서만 G2G.
        for p in ("정부통합데이터센터", "행정안전부 정부청사관리본부", "정부세종청사", "정부출연 연구기관"):
            self.assertEqual(KC.party_kind(p)[0], "GOV", p)
        for p in ("이라크 정부", "말레이시아 정부", "이라크 정부 (MOD)", "필리핀 공화국 정부", "해외 정부기관"):
            self.assertEqual(KC.party_kind(p)[0], "G2G", p)
        for p in ("우리 정부", "지방정부", "에드먼턴 시정부 (The City of Edmonton)",
                  "타이중시 정부 도시철도공정국(Rapid Transit System Bureau of Taichung City Government)"):
            self.assertNotEqual(KC.party_kind(p)[0], "G2G", p)
        # 경계: `호주 정부`는 해외 정부(`주 정부` 지방정부 규칙에 걸리면 안 된다), `중앙정부`는 국내,
        # 대문자 `GOVERNMENT OF INDIA`도 해외 정부.
        self.assertEqual(KC.party_kind("호주 정부")[0], "G2G")
        self.assertEqual(KC.party_kind("호주정부")[0], "G2G")
        self.assertNotEqual(KC.party_kind("중앙정부")[0], "G2G")
        self.assertEqual(KC.party_kind("GOVERNMENT OF INDIA")[0], "G2G")

    def test_korean_name_with_english_paren_in_domestic_region(self):
        """법인 접미 없는 한글 이름 + 괄호 영문 + 공급지역 국내 → 국내(수출 아님). 지역이 해외면 그대로."""
        self.assertTrue(KC._ko_paren_domestic("현대중공업 (HYUNDAI HEAVY INDUSTRIES CO., LTD.)", "대한민국"))
        self.assertTrue(KC._ko_paren_domestic("한국철도공사(KORAIL)", "대한민국"))
        self.assertFalse(KC._ko_paren_domestic("한국철도공사(KORAIL)", ""))
        self.assertFalse(KC._ko_paren_domestic("이집트 철도청(Egyptian National Railways)", "이집트"))
        self.assertFalse(KC._ko_paren_domestic("Larsen & Toubro Limited (L&T)", "대한민국"))

    def test_party_domestic_corp_and_prime_aliases(self):
        """국내 법인 + 괄호 영문 병기는 FOREIGN 이 아니다. KARI≠KAI, LIG D&A·한화디펜스는 체계업체 별칭."""
        for p in ("현대위아(주) (HYUNDAI WIA CORP)", "기아 주식회사(KIA CORPORATION)",
                  "에이치디현대중공업(주) (HD HYUNDAI HEAVY INDUSTRIES CO., LTD.)", "삼성중공업(주)"):
            self.assertEqual(KC.party_kind(p), ("DOMESTIC", None), p)
        for p in ("Larsen & Toubro Limited (L&T)", "터키 이스탄불 市 (Istanbul Metropolitan Municipality)",
                  "EVE UAM, LLC社, EMBRAER S.A.社", "ABC Korea 주식회사"):
            self.assertEqual(KC.party_kind(p)[0], "FOREIGN", p)
        self.assertEqual(KC.party_kind("한국항공우주연구원"), ("GOV", None))
        self.assertEqual(KC.party_kind("Korea Aerospace Research Institute(KARI)")[0], "GOV")
        self.assertEqual(KC.party_kind("한국항공우주산업㈜ (KOREA AEROSPACE INDUSTRIES, LTD.)"), ("PRIME", "047810"))
        self.assertEqual(KC.party_kind("엘아이지디펜스앤에어로스페이스 주식회사"), ("PRIME", "079550"))
        self.assertEqual(KC.party_kind("LIG D&A"), ("PRIME", "079550"))
        self.assertEqual(KC.party_kind("한화디펜스(주)"), ("PRIME", "012450"))

    def test_region_whitelist(self):
        """지역 열은 납품처 이름·주소로 오염돼 있다 — 국내 표기가 하나라도 있으면 내수."""
        for r in ("대한민국", "국내", "-", "", "한화시스템 구미사업장", "한국항공우주산업(주) 사천본사",
                  "충남 계룡시", "충남 논산 계룡대 국방통합데이터센터", "발주자 지정납품장소",
                  '"원사업자"의 지정 장소', "지정 우주궤도", "경기도 성남시"):
            self.assertFalse(KC.region_is_foreign(r), r)
        for r in ("미국", "아랍에미레이트", "폴란드", "오세아니아 지역", "US, Cincinnati", "해외",
                  "대한민국외 해외지점", "국외지점"):
            self.assertTrue(KC.region_is_foreign(r), r)

    def test_export_rules(self):
        """수출 = 상대(G2G·FOREIGN·해외 익명) ∨ 공급지역 해외 ∨ (체계업체 상대 ∧ 계약명 '수출' → 간접)."""
        self.assertEqual(KC.export_of("G2G", "폴란드 군비청", "폴란드", "K2"), (True, "direct", "party"))
        self.assertEqual(KC.export_of("FOREIGN", "Hanwha WB", "폴란드", "K9"), (True, "direct", "party"))
        self.assertEqual(KC.export_of("ANON", "해외 방산업체", "", "부품"), (True, "direct", "party"))
        self.assertEqual(KC.export_of("DOMESTIC", "한국항공우주산업(주)", "미국", "날개"), (True, "direct", "region"))
        self.assertEqual(KC.export_of("PRIME", "한화에어로스페이스", "대한민국", "T-50 수출사업용 엔진"),
                         (True, "indirect", "name"))
        self.assertEqual(KC.export_of("PRIME", "한화시스템", "한화시스템 구미사업장", "TICN 부품"), (False, "", ""))
        self.assertEqual(KC.export_of("GOV", "방위사업청", "대한민국", "K9 후속양산"), (False, "", ""))
        self.assertEqual(KC.export_of("DOMESTIC", "국내 업체", "충남 계룡시", "장비"), (False, "", ""))

    def test_export_recount_superset(self):
        """실데이터: 재판정 수출은 상대만 본 종전 수출(G2G·FOREIGN)의 상위집합이고, 모든 G2G·FOREIGN 은 수출."""
        rows = KC.load()
        if not rows or "export" not in rows[0]:
            self.skipTest("contracts.json 이 없거나 export 필드가 아직 없다")
        defc = [r for r in rows if not r["civil"]]
        by_party = [r for r in defc if r["party_kind"] in ("G2G", "FOREIGN")]
        self.assertTrue(all(r["export"] for r in by_party))
        self.assertGreaterEqual(sum(1 for r in defc if r["export"]), len(by_party))
        self.assertTrue(all(r["export_kind"] == "indirect" for r in defc
                            if r["export"] and r["party_kind"] == "PRIME"))

    def test_export_exec_g2g6(self):
        """유형 미상 G2G 6건 — 이름(`수출사업`·`이행계약`·`수출 계약`)으로, 이름이 없으면 상대로 EXPORT_EXEC."""
        for nm in ("폴란드 K2전차사업 2차 이행계약", "M-SAM(천궁-II) 수출 계약", "천무 다연장로켓 수출사업",
                   "크로아티아 천무 다연장로켓 수출사업", "방산수출 이행약정서"):
            self.assertEqual(KC.ctype_of(nm), "EXPORT_EXEC", nm)
        self.assertEqual(KC.ctype_of("잠수함 3척", "G2G"), "EXPORT_EXEC")
        self.assertEqual(KC.ctype_of("필리핀 FA-50 추가 사업", "G2G"), "EXPORT_EXEC")
        self.assertEqual(KC.ctype_of("잠수함 3척"), "UNKNOWN")                 # 상대 없이 이름만으론 미상
        self.assertEqual(KC.ctype_of("잠수함 3척", "FOREIGN"), "UNKNOWN")      # 해외 기업은 되짚지 않는다
        # 생산·공급 유형이 함께 적히면 그쪽이 먼저 — 판로(수출)는 유형이 아니다.
        self.assertEqual(KC.ctype_of("인도 K9 자주포 2차 수출사업 (구성품 공급)"), "SUPPLY")
        self.assertEqual(KC.ctype_of("K9외 2종 수출사업 변속기조립체 물품구매계약"), "SUPPLY")
        self.assertEqual(KC.ctype_of("K9자주포 4차 양산 수출사업"), "FOLLOW")
        self.assertEqual(KC.ctype_of("대전차유도무기 3차사업"), "FOLLOW")
        self.assertEqual(KC.ctype_of("KUH-1 PBL 2차 사업"), "PBL")

    def test_export_exec_by_party(self):
        """유형 축(계약 성격)과 판로 축(수출)을 상대 갈래로 가른다 — G2G 우선, PRIME 금지, DOMESTIC 은 이행 낱말만."""
        # 해외 정부(G2G): `공급`이 있어도 EXPORT_EXEC 패턴이 맞으면 SUPPLY 보다 먼저(FA-50 4.21조).
        self.assertEqual(KC.ctype_of("폴란드 FA-50 항공기 공급 사업 실행계약", "G2G"), "EXPORT_EXEC")
        self.assertEqual(KC.ctype_of("폴란드 FA-50 항공기 공급 사업 실행계약"), "SUPPLY")           # 상대 없이는 종전대로
        self.assertEqual(KC.ctype_of("폴란드 FA-50 항공기 공급 사업 실행계약", "FOREIGN"), "SUPPLY")
        self.assertEqual(KC.ctype_of("유도무기류 공급계약", "G2G"), "SUPPLY")                       # 패턴이 없으면 SUPPLY 그대로
        self.assertEqual(KC.ctype_of("K9자주포 4차 양산 수출사업", "G2G"), "FOLLOW")               # 양산·개량·PBL 은 여전히 먼저
        self.assertEqual(KC.ctype_of("필리핀 FA-50 성능개량 사업", "G2G"), "UPGRADE")
        # 국내 체계업체(PRIME) 상대: 부품사의 공급계약 — EXPORT_EXEC 금지, 공급 낱말이 없으면 UNKNOWN.
        self.assertNotEqual(KC.ctype_of("T-50 수출사업용 엔진", "PRIME"), "EXPORT_EXEC")
        self.assertEqual(KC.ctype_of("T-50 수출사업용 엔진", "PRIME"), "UNKNOWN")
        self.assertEqual(KC.ctype_of("[수출] 사우디 MSAM-Ⅱ MFR 수출사업-주장비(개발 재료비)_배열안테나조립체 외 3건 계약",
                                     "PRIME"), "UNKNOWN")
        self.assertEqual(KC.ctype_of("수출사업 변속기조립체 물품구매계약(3종)", "PRIME"), "SUPPLY")
        self.assertEqual(KC.ctype_of("폴란드 K9 2차 이행계약 구성품", "PRIME"), "UNKNOWN")         # PRIME 은 이행 낱말로도 안 된다
        # 국내 기업(DOMESTIC): `수출사업`만으로는 판로 낱말, `이행약정·이행계약·실행계약`이 적혀야 EXPORT_EXEC.
        self.assertEqual(KC.ctype_of("K9 수출사업 부품", "DOMESTIC"), "UNKNOWN")
        self.assertEqual(KC.ctype_of("K9 수출사업 이행계약", "DOMESTIC"), "EXPORT_EXEC")
        # GOV(KOTRA)·FOREIGN·ANON 은 이름대로.
        self.assertEqual(KC.ctype_of("방산수출 이행약정서", "GOV"), "EXPORT_EXEC")
        self.assertEqual(KC.ctype_of("인도 K9 자주포 2차 부품 수출사업", "FOREIGN"), "EXPORT_EXEC")
        self.assertEqual(KC.ctype_of("스페인 K9 자주포 등 수출 실행계약 (Derivative Contract)", "FOREIGN"), "EXPORT_EXEC")
        # 사전(contract_types.json)의 순서 자체는 그대로다 — 비G2G 는 SUPPLY 가 EXPORT_EXEC 앞.
        ids = [c["id"] for c in load_asset("contract_types.json")["types"]]
        self.assertLess(ids.index("SUPPLY"), ids.index("EXPORT_EXEC"))
        self.assertEqual([cid for _, cid in KC._ctypes_for("G2G")].index("EXPORT_EXEC"),
                         [cid for _, cid in KC._ctypes_for("G2G")].index("SUPPLY") - 1)


class TestMatrix(unittest.TestCase):
    def _rows(self):
        return [_c(ctype="FOLLOW", party_kind="GOV", amt_krw_m=1000.0),
                _c(ctype="FOLLOW", party_kind="GOV", amt_krw_m=250.5),
                _c(ctype="EXPORT_EXEC", party_kind="G2G", amt_krw_m=8981406.673),
                _c(ctype="SUPPLY", party_kind="PRIME", amt_krw_m=None, withheld="경영상 비밀"),
                _c(ctype="WEIRD", party_kind="MARS", amt_krw_m=7.0)]

    def test_matrix_sum(self):
        """셀 합 = 행 합 = 열 합 = 원장 합. 금액 미기재 건은 건수에만, 모르는 유형·상대는 미상 칸."""
        m = KP.matrix(self._rows(), _data())
        want = 1000.0 + 250.5 + 8981406.673 + 7.0
        self.assertAlmostEqual(m["total"]["amt"], want, places=3)
        self.assertEqual(m["total"]["n"], 5)
        self.assertEqual(m["total"]["n_noamt"], 1)
        self.assertAlmostEqual(sum(x["amt"] for x in m["row_tot"].values()), want, places=3)
        self.assertAlmostEqual(sum(x["amt"] for x in m["col_tot"].values()), want, places=3)
        self.assertEqual(sum(x["n"] for x in m["cells"].values()), 5)
        self.assertEqual(m["cells"][("FOLLOW", "GOV")]["n"], 2)
        self.assertIn(("UNKNOWN", "UNKNOWN"), m["cells"])
        self.assertEqual(m["ctypes"], ["FOLLOW", "SUPPLY", "EXPORT_EXEC", "UNKNOWN"])   # 사전 순서
        self.assertEqual(m["parties"], ["GOV", "PRIME", "G2G", "UNKNOWN"])

    def test_matrix_html_has_numbers(self):
        html = KP.matrix_html(KP.matrix(self._rows(), _data()), _data())
        self.assertIn("89,814", html)                   # 8,981,406 백만원 → 89,814 억
        self.assertIn("유보 1", html)
        self.assertIn("<tfoot>", html)


class TestScheduleByYear(unittest.TestCase):
    def _rows(self):
        return [_c(rcp="1", end="2027-06-30", end_raw="2027-06-30", ctype="FOLLOW", party_kind="GOV", amt_krw_m=1000.0),
                _c(rcp="2", end="2033-12-31", end_raw="2033-12-31", ctype="EXPORT_EXEC", party_kind="G2G",
                   amt_krw_m=8981406.673),
                _c(rcp="3", end="2024-12-31", end_raw="2024-12-31", amt_krw_m=500.0),            # 종료 경과 → 제외
                _c(rcp="4", end="", end_raw="-", years=None, amt_krw_m=300.0)]                   # 기간 미상 → 제외

    def test_schedule_by_year(self):
        """진행중 계약만 종료 연도로 묶는다 — 창(10분기) 밖 2033년도 담고, 종료 경과·기간 미상은 뺀다."""
        today = date(2026, 10, 1)
        yc = OV.build_schedule_by_year(self._rows(), "t", today, True, by="ctype")
        self.assertEqual(list(yc["years"]), ["2027", "2033"])
        self.assertEqual(yc["total_n"], 2)
        self.assertAlmostEqual(yc["total_sum"], 1000.0 + 8981406.673, places=3)
        self.assertEqual(yc["cols"], ["FOLLOW", "EXPORT_EXEC"])
        yp = OV.build_schedule_by_year(self._rows(), "t", today, True, by="party")
        self.assertEqual(yp["cols"], ["GOV", "G2G"])
        self.assertIn("2033", yp["html"])
        self.assertIn("기인식분 차감 없음", yp["html"])

    def test_schedule_by_year_empty(self):
        out = OV.build_schedule_by_year([_c(end="2020-01-01", end_raw="2020-01-01")], "t", date(2026, 10, 1), True)
        self.assertEqual(out["total_n"], 0)
        self.assertIn("진행중", out["html"])


class TestDueSchedule(unittest.TestCase):
    def test_due_year(self):
        """실측 납기 표기 전부 — 기간은 끝 연도, 연도가 없으면 None."""
        cases = {"2027.12": 2027, "2025-09-30": 2025, "2023.01 ~ 2026.12": 2026, "2025년~2027년": 2027,
                 "~2028년": 2028, "'25.1~6월": 2025, "~28년": 2028, "26.01.01~26.12.31": 2026,
                 "'24.10월이후": 2024, "2022-11-13": 2022, "2036": 2036,
                 # 아이쓰리시스템 YY-MM-DD(2024Q3~2025Q1 실측 63행) — MM·DD 토큰은 2015~2060 창에서 걸러진다.
                 "26-12-23": 2026, "32-06-03": 2032, "'25-12-31": 2025, "24-07-31~25-12-31": 2025, "26/12": 2026,
                 "12-31": None,
                 "400대": None, "*1": None, "상세내역 참조": None, "": None, "-": None, "1999.12": None}
        for s, want in cases.items():
            self.assertEqual(KP.due_year(s), want, repr(s))

    def test_due_schedule_buckets(self):
        comp = {"quarters": {"2026Q2": {"unit_seen": True, "unit_note": "", "rcp": "r", "segments": [
            {"label": "철도A", "closing": 1000.0, "due": "2027.12"},
            {"label": "철도B", "closing": 500.0, "due": "2024.01 ~ 2027.06"},
            {"label": "K2", "closing": None, "due": "2029-12-31"},
            {"label": "엔진", "closing": 70.0, "due": "상세내역 참조"},
            {"label": "없음", "closing": 70.0, "due": "-"}]}}}
        d = KP.due_schedule(comp, "2026Q2")
        self.assertEqual(d["n"], 4)                        # due '-' 는 품목 행이지만 납기가 없다
        self.assertEqual(d["years"], [2027, 2029])
        self.assertEqual(d["buckets"][2027]["n"], 2)
        self.assertAlmostEqual(d["buckets"][2027]["closing"], 1500.0)
        self.assertEqual(d["buckets"][2029]["n_noamt"], 1)
        self.assertEqual(d["unknown"]["n"], 1)
        html = KP.due_html(d)
        self.assertIn("연도 미상", html)
        self.assertIn("2029", html)

    def test_due_schedule_none_without_due(self):
        comp = {"quarters": {"2026Q2": {"unit_seen": True, "unit_note": "", "segments": [{"label": "방산", "closing": 1}]}}}
        self.assertIsNone(KP.due_schedule(comp, "2026Q2"))
        self.assertIsNone(KP.due_schedule({"quarters": {}}, "2026Q2"))


class TestQuantityAxis(unittest.TestCase):
    STD = {"cols": ["품목", "수주일자", "납기", "수주총액 수량", "수주총액 금액", "기납품액 수량", "기납품액 금액",
                    "수주잔고 수량", "수주잔고 금액"],
           "rows": [["A부품", "2024.03", "2027.12", "1,200", "36,000", "400", "12,000", "800", "24,000"],
                    ["B부품", "2025.01", "~2028년", "-", "9,000", "-", "1,000", "300", "8,000"],
                    ["합 계", "", "", "1,200", "45,000", "400", "13,000", "1,100", "32,000"]],
           "lead": "나. 수주상황 (단위 : 천개, 백만원)"}

    def test_qty_unit_from_caption(self):
        """캡션에서 수량 단위만 — 금액 단위(백만원·USD)는 뺀다. 없으면 빈 문자열(미표기)."""
        self.assertEqual(KP.qty_unit_of("(단위 : 천개, 백만원)", []), "천개")
        self.assertEqual(KP.qty_unit_of("(단위 : M/T, 백만원)", []), "M/T")
        self.assertEqual(KP.qty_unit_of("(단위 : 백만원)", []), "")
        self.assertEqual(KP.qty_unit_of("(단위 : USD )", []), "")
        self.assertEqual(KP.qty_unit_of("", ["품목", "(단위 : 대, 천원)"]), "대")
        # 포메탈(119500) 캡션 — `/`는 한쪽이 금액 단위일 때만 가른다(`M/T`는 한 단위). `수량-`·`금액-` 꼬리표는 벗긴다.
        self.assertEqual(KP.qty_unit_of("(단위 : EA / 백만원 )", []), "EA")
        self.assertEqual(KP.qty_unit_of("(단위 : EA/백만원)", []), "EA")
        self.assertEqual(KP.qty_unit_of("(단위 : 수량-EA/금액-백만원)", []), "EA")
        self.assertEqual(KP.qty_unit_of("(단위 : 백만원/EA)", []), "EA")
        self.assertEqual(KP.qty_unit_of("(단위 : M/T)", []), "M/T")

    def test_parse_qty_table_rejects_merged_money_header(self):
        """병합 머리행 `수주잔고 수량금액`(대양전기공업 2025Q1)은 금액 열이다 — 수량 축을 만들지 않는다."""
        merged = {"cols": ["품목", "수주일자", "납기", "수주잔고 수량금액"],
                  "rows": [["전원공급장치", "2024.01", "2025.12", "293,773"], ["합 계", "", "", "293,773"]],
                  "lead": "마. 수주상황 (단위 : 백만원)"}
        self.assertIsNone(KP.parse_qty_table(merged))
        both = {"cols": ["품목", "수주총액 수량금액", "수주잔고 수량", "수주잔고 금액"],
                "rows": [["A", "9,999", "12", "1,000"]], "lead": "(단위 : 개, 백만원)"}
        p = KP.parse_qty_table(both)                                       # 수량 홀로 적힌 열만 읽는다
        self.assertEqual((p["rows"][0]["gross"], p["rows"][0]["closing"], p["unit"]), (None, 12, "개"))
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "108380"))
            good = {"cols": ["품목", "수주일자", "납기", "수주총액 수량", "수주총액 금액", "기납품액 수량", "기납품액 금액",
                             "수주잔고 수량", "수주잔고 금액"],
                    "rows": [["A", "2024.03", "2027.12", "100", "1,000", "40", "400", "60", "600"]],
                    "lead": "(단위 : 천개, 백만원)"}
            for q, t in (("2024Q2", good), ("2025Q1", merged)):
                with open(os.path.join(d, "108380", q + ".json"), "w", encoding="utf-8") as f:
                    json.dump({"rcp": "r" + q, "raw_tables": [t]}, f)
            s = KP.qty_series("108380", cache_dir=d)
            self.assertEqual([(x["q"], x["unit"], x["closing"]) for x in s], [("2024Q2", "천개", 60)])
        finally:
            shutil.rmtree(d)

    def test_parse_qty_table_reads_quantity_not_money(self):
        """수량 열만 읽는다 — 금액 열(36,000)은 절대 섞이지 않는다."""
        p = KP.parse_qty_table(self.STD)
        self.assertEqual(p["unit"], "천개")
        a = [r for r in p["rows"] if r["label"] == "A부품"][0]
        self.assertEqual((a["gross"], a["delivered"], a["closing"]), (1200, 400, 800))
        self.assertEqual(a["due"], "2027.12")
        b = [r for r in p["rows"] if r["label"] == "B부품"][0]
        self.assertIsNone(b["gross"])
        self.assertEqual(b["closing"], 300)
        self.assertTrue([r for r in p["rows"] if r["total"]])
        self.assertEqual(KP._qty_total(p, "closing"), 1100)                # 합계 행이 있으면 그 값

    def test_parse_qty_table_rejects_money_only_and_dash(self):
        money = {"cols": ["품목", "수주총액 금액", "수주잔고 금액"], "rows": [["A", "1", "2"]], "lead": "(단위 : 백만원)"}
        self.assertIsNone(KP.parse_qty_table(money))
        dash = {"cols": self.STD["cols"], "rows": [["(주)한화", "상세내역 참조", "상세내역 참조", "-", "1,885,537", "-", "687,637", "-", "1,197,900"]],
                "lead": "(단위 : 백만원)"}
        self.assertIsNone(KP.parse_qty_table(dash))
        weight = {"cols": ["품목", "납기", "수주총액 중량", "수주총액 금액", "기납품액 중량", "기납품액 금액", "수주잔고 중량", "수주잔고 금액"],
                  "rows": [["탄약", "2026", "70,516", "100", "20,514", "30", "50,002", "70"]],
                  "lead": "(단위 : M/T, 백만원)"}
        w = KP.parse_qty_table(weight)
        self.assertEqual(w["unit"], "M/T")
        self.assertEqual(w["rows"][0]["closing"], 50002)

    def test_qty_series_from_cache_dir(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "103140"))
            for q, rows in (("2026Q1", [["탄약", "2026", "70,516", "100", "20,514", "30", "50,002", "70"]]),
                            ("2026Q2", [["탄약", "2026", "72,000", "100", "30,000", "30", "42,000", "70"],
                                        ["신관", "2027", "-", "5", "-", "1", "1,000", "4"]])):
                with open(os.path.join(d, "103140", q + ".json"), "w", encoding="utf-8") as f:
                    json.dump({"rcp": "r" + q, "raw_tables": [
                        {"cols": ["품목", "납기", "수주총액 중량", "수주총액 금액", "기납품액 중량", "기납품액 금액",
                                  "수주잔고 중량", "수주잔고 금액"], "rows": rows, "lead": "(단위 : M/T, 백만원)"},
                        {"cols": ["구분", "매출액"], "rows": [["방산", "1"]], "lead": ""}]}, f)
            s = KP.qty_series("103140", cache_dir=d)
            self.assertEqual([x["q"] for x in s], ["2026Q1", "2026Q2"])
            self.assertEqual(s[-1]["closing"], 43000)                       # 42,000 + 1,000 (합계 행 없음 → 품목 합)
            self.assertEqual(s[-1]["n"], 2)
            self.assertEqual(s[-1]["unit"], "M/T")
            html = KP.qty_html(s)
            self.assertIn("43,000", html)
            self.assertIn("M/T", html)
            self.assertEqual(KP.qty_series("000000", cache_dir=d), [])
        finally:
            shutil.rmtree(d)


class TestPageAggregates(unittest.TestCase):
    def _data(self):
        data = _data()
        data["by_stock"] = {"012450": {"stock": "012450", "name": "한화에어로스페이스", "role": "prime",
                                       "market": "KOSPI", "industry": "", "product": ""}}
        data["contracts"] = [
            _c(rcp="a", amt_krw_m=1000.0),
            _c(rcp="b", title="단일판매ㆍ공급계약해지", amt_krw_m=5000.0),                  # 해지 공시 — 집계 제외
            _c(rcp="c", domain="CIVIL", civil=True, amt_krw_m=99.0),
            _c(rcp="d", domain=None, domain_hint="PART", ctype="SUPPLY", party_kind="PRIME",
               party="한화시스템", party_prime="272210", amt_krw_m=200.0, export=True,
               export_kind="indirect", export_basis="name", name="수출사업용 커넥터 공급"),
            _c(rcp="e", party_kind="G2G", party="폴란드 군비청", region="폴란드", ctype="EXPORT_EXEC",
               amt_krw_m=3000.0, export=True, export_kind="direct", export_basis="party")]
        return data

    def test_summary_excludes_termination_and_splits_export(self):
        s = KP.summary("012450", self._data())
        self.assertEqual(len(s["terminations"]), 1)
        self.assertEqual(len(s["def_contracts"]), 3)
        self.assertEqual(s["civil_n"], 1)
        self.assertAlmostEqual(s["amt_total"], 4200.0)                   # 해지 5,000 은 들어가지 않는다
        self.assertEqual(s["export"]["n"], 2)
        self.assertEqual((s["export"]["direct"], s["export"]["indirect"]), (1, 1))
        self.assertAlmostEqual(s["export"]["amt"], 3200.0)
        self.assertEqual(s["dom_n"]["PART"], 1)
        self.assertEqual(s["dom_n"]["GROUND"], 2)                         # a·e — 해지 공시 b 는 계통 집계에도 없다

    def test_contracts_table_pills(self):
        data = self._data()
        html = KP.contracts_table(data["contracts"], data, tid="t")
        self.assertEqual(html.count('class="pill term"'), 1)
        self.assertIn("간접수출", html)
        self.assertIn('class="pill exp"', html)
        self.assertIn("부품(계통 미상)", html)
        self.assertIn("정부(G2G", html)

    def test_segment_label(self):
        """주요 거래처 표에서 부문명 행을 거른다 — 실제 거래처 이름은 남긴다."""
        for nm in ("방산", "ICT", "신사업", "위성사업", "방산부문", "10% 이상 차지하는 주요 고객수", "합계", ""):
            self.assertTrue(is_segment_label(nm), nm)
        for nm in ("방위사업청", "한화에어로스페이스", "국방과학연구소", "기타거래처", "LIG넥스원", "Boeing"):
            self.assertFalse(is_segment_label(nm), nm)


class TestContractsFixture(unittest.TestCase):
    """실데이터에서 얼린 대표 행(tests/fixtures/contracts_sample.json, 이름·상대·지역만) — 계통·유형·상대·수출
    판정을 정확히 단언한다. 일일 갱신에 흔들리지 않고, 사전 한 줄이 바뀌면 어느 행이 움직였는지 바로 보인다.
    기대값을 바꿀 때는 픽스처의 `why` 를 함께 고친다(판정 근거가 바뀐 것이므로)."""
    FIX = os.path.join(HERE, "fixtures", "contracts_sample.json")
    WANT = ("domain", "domain_hint", "ctype", "party_kind", "party_prime", "export", "export_kind", "export_basis",
            "civil")

    @classmethod
    def _rows(cls):
        with open(cls.FIX, encoding="utf-8") as f:
            return json.load(f)["rows"]

    @staticmethod
    def classify(row):
        """공시 (라벨,값) 세 줄 → _fields_from_kv — 빌드(kdef_contracts.build)와 같은 길."""
        raw = [("체결계약명", row["name"]), ("계약상대방", row["party"]), ("판매ㆍ공급지역", row["region"])]
        return KC._fields_from_kv(KC._kv_from_raw(raw))

    def test_fixture_rows(self):
        rows = self._rows()
        bad = []
        for r in rows:
            got = self.classify(r)
            for k in self.WANT:
                if got[k] != r["want"][k]:
                    bad.append("%s %s %r: %s %r → %r (%s)" % (r["stock"], r["rcp"], r["name"][:40], k, r["want"][k],
                                                             got[k], r.get("why", "")))
        self.assertEqual(bad, [], "\n" + "\n".join(bad))

    def test_fixture_coverage(self):
        """픽스처가 축을 다 덮는다 — 계통 전부(+미상·부품), 유형 전부(+미상), 상대 7갈래, 수출 근거 3종."""
        rows = self._rows()
        self.assertGreaterEqual(len(rows), 40)
        self.assertEqual(len({(r["stock"], r["rcp"]) for r in rows}), len(rows))
        for r in rows:
            self.assertEqual(set(r["want"]), set(self.WANT), r["rcp"])
        doms = {r["want"]["domain"] for r in rows}
        self.assertTrue({d["id"] for d in load_asset("domains.json")["domains"]} <= doms, doms)
        self.assertIn(None, doms)
        self.assertIn("PART", {r["want"]["domain_hint"] for r in rows})
        ctypes = {r["want"]["ctype"] for r in rows}
        self.assertTrue({c["id"] for c in load_asset("contract_types.json")["types"]} | {"UNKNOWN"} <= ctypes, ctypes)
        self.assertEqual({r["want"]["party_kind"] for r in rows},
                         {"GOV", "PRIME", "G2G", "FOREIGN", "DOMESTIC", "ANON", "UNKNOWN"})
        self.assertEqual({(r["want"]["export_kind"], r["want"]["export_basis"]) for r in rows if r["want"]["export"]},
                         {("direct", "party"), ("direct", "region"), ("indirect", "region"), ("indirect", "name")})
        # 검토 지적의 핵심 사례가 들어 있고 기대값이 지적대로다.
        by = {r["name"]: r["want"] for r in rows}
        self.assertEqual(by["폴란드 FA-50 항공기 공급 사업 실행계약"]["ctype"], "EXPORT_EXEC")
        self.assertEqual(by["T-50 수출사업용 엔진"]["ctype"], "UNKNOWN")
        self.assertEqual(by["T-50 수출사업용 엔진"]["export_kind"], "indirect")
        self.assertIsNone(by["MCS Plant 구축 공사"]["domain"])
        self.assertFalse(by["MCS Plant 구축 공사"]["civil"])
        self.assertEqual(by["[수정계약] 폴란드 K9 자주포 등 1차 실행계약"]["party_kind"], "G2G")


class TestPaletteSync(unittest.TestCase):
    def test_palette_css_views_agree(self):
        """계통 색 세 벌 — kdef_lib.PALETTE · kdef.css --sN · kdef_orders_views.DOMAINS — 가 같아야 한다."""
        with open(os.path.join(KDEF, "assets", "kdef.css"), encoding="utf-8") as f:
            css = dict((int(a), b.lower()) for a, b in re.findall(r"--s(\d):\s*(#[0-9a-fA-F]{6})", f.read()))
        for p in PALETTE:
            if p["slot"] == 0:
                continue
            self.assertEqual(css.get(p["slot"]), p["hex"].lower(), "css --s%d" % p["slot"])
        doms = load_asset("domains.json")["domains"]
        self.assertEqual(set(OV.DOMAINS), {d["id"] for d in doms})
        for d in doms:
            self.assertEqual(OV.DOMAINS[d["id"]][1].lower(), slot_color(d["slot"]).lower(), d["id"])
        self.assertIn("SPACE", OV.DOMAINS)
        self.assertIn("EXPORT_EXEC", OV.CTYPES)


if __name__ == "__main__":
    unittest.main()


class TestLedgerAsof(unittest.TestCase):
    def test_asof_is_latest_filing_not_today(self):
        """기준일은 원장 최신 접수일(rcpNo 앞 8자리) — 실행 날짜가 아니다."""
        import datetime
        import kdef_page as KP
        rows = [{"rcp": "20260909800123"}, {"rcp": "20261012900456"}, {"rcp": "bad"}, {}]
        self.assertEqual(KP.ledger_asof(rows), datetime.date(2026, 10, 12))
        self.assertIsNone(KP.ledger_asof([]))
