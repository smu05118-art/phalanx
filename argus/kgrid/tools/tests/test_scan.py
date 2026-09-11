#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kgrid_scan 승격 규칙 계약 테스트.

fixture 는 **DART 원문 그대로**다 — `assets/_raw/probe/2026Q2/<종목>.txt`(정기보고서
「II. 사업의 내용」 1·2·4절에서 태그만 벗긴 것)를 `tests/fixtures/body_<종목>.txt` 로 옮겨 놓았다.
첫 줄은 `<접수번호>\\t<보고서명>` 이고 그 아래가 본문이다.

검증하는 계약은 셋이다(COMMON §4 — 형식이 아니라 계약).
  1) 화면에 실리는 승격/제외 판정이 **그 원문에서** 나오는가 (파워넷·대양전기공업·제일일렉트릭은
     제외, 산일전기·보성파워텍·미창석유공업은 승격)
  2) `evidence` 의 인용문이 **원문에 그대로 있는 문자열**인가 (추정 금지, COMMON §0-1)
  3) FINDINGS §1 의 어휘 함정(`GIS`·`ESS`·`초고압` 단독)이 다시 살아나지 않는가
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import kgrid_scan as S            # noqa: E402


def body(stock):
    """fixture 원문 → (본문, 보고서명). 첫 줄은 접수번호·보고서명 머리다."""
    with open(os.path.join(FIX, "body_%s.txt" % stock), encoding="utf-8") as f:
        head = f.readline().rstrip("\n")
        return f.read(), head.partition("\t")[2]


def measured(stock, **rec):
    row = dict({"stock": stock, "name": stock, "industry": "", "product": ""}, **rec)
    text, title = body(stock)
    row["title"] = title
    S.measure(row, text)
    return row, text


class 승격규칙(unittest.TestCase):

    # ── 제외 (모집단에 이름만으로 들어와 있던 것들) ──────────────

    def test_파워넷_037030_은_가전용_SMPS라_제외된다(self):
        """KIND 주요제품이 `전력변환장치`여서 업종 경로로 들어왔지만, II절 본문은 가전 전원장치다.

        원문: "주력 제품인 SMPS는 … IT, OA, 가전, 산업용 등 다양한 분야에 적용되는 핵심부품"
        """
        row, text = measured("037030", product="전력변환장치")
        self.assertEqual(row["strong"], 0, "전력망 고유 낱말이 하나라도 잡히면 어휘가 헐거운 것이다")
        self.assertIn("SMPS", row["neg_terms"])
        ok, why = S.judge(row)
        self.assertFalse(ok)
        self.assertIn("전력망 고유 낱말이 하나도 없다", why)
        self.assertIn("SMPS", text)

    def test_대양전기공업_108380_의_배전반은_선박철도용이라_제외된다(self):
        """KIND 문구 `배전반류`로 들어왔으나 본문 제품설명은 `선박용 배전반`·`철도차량용 배전반`이다."""
        row, text = measured("108380", product="해상용 조명등기구, (함정용)전자시스템, 배전반류 등")
        self.assertEqual(row["strong"], 0)
        self.assertGreater(row["mid"], 0, "`배전반`은 잡혀야 한다 — 잡히되 전력망은 아니라는 판정이다")
        self.assertGreater(row["neg"], row["mid"], "선박·철도 문맥이 압도해야 한다")
        ok, why = S.judge(row)
        self.assertFalse(ok)
        self.assertIn("선박용", row["neg_terms"])
        self.assertIn("선박용 배전반", text)

    def test_제일일렉트릭_199820_의_분전반은_세대_저압_배선기구라_제외된다(self):
        """`분전반`으로 들어왔으나 본문은 "세대 간선으로부터 각 분기회로로 갈라지는 곳"이다."""
        row, text = measured("199820", product="PCB Assay, 배선기구, 분전반 등")
        self.assertEqual(row["strong"], 0)
        self.assertGreater(row["mid"], 20, "`차단기`·`분전반` 같은 관련 낱말은 많이 나온다")
        ok, why = S.judge(row)
        self.assertFalse(ok, "관련 낱말이 많아도 전력망 고유 낱말이 0이면 승격하지 않는다")
        self.assertIn("배선기구", row["neg_terms"])
        self.assertIn("세대 간선으로부터 각 분기회로로 갈라지는 곳", text)

    # ── 승격 ────────────────────────────────────────────────

    def test_산일전기_062040_변압기_본문은_승격선을_넘는다(self):
        row, text = measured("062040", product="유입, 몰드, 주상, 건식 변압기 등")
        ok, why = S.judge(row)
        self.assertTrue(ok, why)
        self.assertGreaterEqual(S.score_of(row), S.PROMOTE_SCORE)
        self.assertTrue(any(k.startswith("유입") for k in row["terms"]),
                        "`유입변압기`가 고유 낱말로 잡혀야 한다: %s" % row["terms"])

    def test_보성파워텍_006910_송배전용자재는_part로_승격된다(self):
        row, text = measured("006910", industry="구조용 금속제품, 탱크 및 증기발생기 제조업",
                             product="송배전용자재")
        ok, why = S.judge(row)
        self.assertTrue(ok, why)
        self.assertEqual(S.role_for(row), "part", "기기가 아니라 그 주변 자재다")
        self.assertGreater(row["kepco"], 0, "발주처(한국전력공사) 언급이 있어야 한다")

    def test_미창석유공업_003650_절연유는_고유낱말만으로_승격된다(self):
        """관련 낱말(`변압기` 등)은 거의 없고 `절연유`만 나오는 소재 회사다 —
        한전·체계업체 언급이 받쳐 주는 경로로 올라온다."""
        row, text = measured("003650", industry="석유 정제품 제조업",
                             product="윤활유,고무배합유,전기절연유 제조,판매,수출입")
        self.assertIn("절연유", row["terms"])
        ok, why = S.judge(row)
        self.assertTrue(ok, why)
        self.assertEqual(S.role_for(row), "part")

    # ── 증거 ────────────────────────────────────────────────

    def test_evidence_는_원문에_그대로_있는_문자열이다(self):
        for stock in ("062040", "006910", "003650"):
            row, text = measured(stock)
            self.assertTrue(row["evidence"], "%s 인용문이 비었다" % stock)
            for q in row["evidence"]:
                self.assertIn(q, text, "%s 인용문이 원문에 없다: %r" % (stock, q))

    def test_고유낱말이_0인_회사도_제외_인용문은_남는다(self):
        """파워넷·대양전기공업·제일일렉트릭은 고유 낱말이 0이라 `evidence` 가 빈다 —
        그러면 제외 근거를 보여 줄 원문이 없어진다. `neg_evidence` 가 그 자리를 메운다."""
        for stock in ("037030", "108380", "199820", "377330"):
            row, text = measured(stock)
            self.assertEqual(row["evidence"], [], "%s 는 고유 낱말이 0이어야 한다" % stock)
            self.assertTrue(row["neg_evidence"], "%s 제외 인용문이 비었다" % stock)
            for q in row["neg_evidence"]:
                self.assertIn(q, text, "%s 제외 인용문이 원문에 없다: %r" % (stock, q))

    def test_본문을_못_읽으면_승격하지_않는다(self):
        """fail-closed — ok=False 면 낱말 수가 아무리 커도 승격 금지(COMMON §0-2)."""
        ok, why = S.judge({"ok": False, "strong": 99, "mid": 99, "note": "정기보고서 없음",
                           "evidence": ["아무 말"]})
        self.assertFalse(ok)
        self.assertIn("읽지 못했다", why)

    def test_인용문이_없으면_승격하지_않는다(self):
        ok, why = S.judge({"ok": True, "strong": 9, "mid": 99, "neg": 0, "kepco": 0,
                           "mentions": {}, "terms": {"변전소": 9}, "evidence": []})
        self.assertFalse(ok)
        self.assertIn("증거 없는 승격", why)


class 어휘함정(unittest.TestCase):
    """FINDINGS §1 에서 실측한 오탐이 다시 살아나지 않는지 지킨다."""

    TRAPS = [
        ("넥스틴 AEGIS", "반도체 검사장비 AEGIS 시리즈를 공급한다"),
        ("제이에스링크 EGIS", "EGIS 플랫폼"),
        ("지어소프트 Internet GIS", "Internet GIS 서비스"),
        ("세보엠이씨 ACESS FLOOR", "ACESS FLOOR 시공"),
        ("에이아이코리아 CESS", "CESS 기반 솔루션"),
        ("일진디스플 초고압용공구", "분말야금제품(초고압용공구)을 제조한다"),
        ("이차전지 ESS", "ESS 용 이차전지 셀을 양산한다"),
    ]

    def test_GIS_ESS_초고압_단독은_전력망_낱말로_세지_않는다(self):
        for label, text in self.TRAPS:
            self.assertIsNone(S.STRONG.search(text), "%s 가 고유 낱말로 잡혔다" % label)

    def test_가스절연과_초고압변압기는_문맥이_붙으면_잡는다(self):
        self.assertTrue(S.STRONG.search("가스절연개폐장치(GIS) 및 GIS차단기를 제조한다"))
        self.assertTrue(S.STRONG.search("초고압 변압기와 초고압케이블"))
        self.assertTrue(S.STRONG.search("154kV 변전소용 부싱과 탭체인저"))

    def test_초고압용공구는_MID에도_걸리지_않는다(self):
        self.assertIsNone(S.MID.search("분말야금제품(초고압용공구)"))


class 역할힌트(unittest.TestCase):
    """role 은 힌트다 — 수주표·계약 공시가 확인하면 뒤 단계가 고친다(kgrid_universe 머리말)."""

    def test_KIND문구가_소재라도_본문이_변압기를_만든다면_maker다(self):
        """KBI메탈 024840 실측: 제품 문구는 `동ROD, 모터코어`인데 본문에
        "변압기 사업부인 KBI일렉트릭(주)은 … 몰드변압기 제조를 목적으로 설립된 회사"가 나온다."""
        self.assertEqual(S.role_for({"industry": "1차 비철금속 제조업", "product": "동ROD, 모터코어",
                                     "terms": {"몰드변압기": 2, "유입변압기": 1, "규소강판": 2}}),
                         "maker")

    def test_금구류_회사가_부르는_주상변압기로는_maker가_되지_않는다(self):
        """보성파워텍 006910 실측: `주상변압기` 2회는 **설치 대상**이지 자기 제품이 아니다."""
        self.assertEqual(S.role_for({"industry": "구조용 금속제품, 탱크 및 증기발생기 제조업",
                                     "product": "송배전용자재",
                                     "terms": {"전력기자재": 5, "변전소": 3, "주상변압기": 2}}),
                         "part")

    def test_케이블_업종은_cable_정비는_epc다(self):
        self.assertEqual(S.role_for({"industry": "절연선 및 케이블 제조업",
                                     "product": "전선,통신케이블", "terms": {"송배전": 2}}), "cable")
        self.assertEqual(S.role_for({"industry": "전기 및 통신 공사업",
                                     "product": "일반전기공사,발전설비정비공사,점검,수리",
                                     "terms": {"송변전": 9}}), "epc")


class 후보풀(unittest.TestCase):
    """어휘로 **먼저 좁힌다**(COMMON §2 — 수천 건을 한 번에 긁지 않는다)."""

    RECS = [
        {"stock": "062040", "name": "산일전기", "market": "유가증권",
         "industry": "전동기, 발전기 및 전기 변환 · 공급 · 제어 장치 제조업",
         "product": "유입, 몰드, 주상, 건식 변압기 등"},                      # 이미 모집단
        {"stock": "015760", "name": "한국전력공사", "market": "유가증권",
         "industry": "전기업", "product": "전력 판매"},                       # 발주처(스펙 ④)
        {"stock": "262260", "name": "에이프로", "market": "코스닥",
         "industry": "전동기, 발전기 및 전기 변환 · 공급 · 제어 장치 제조업",
         "product": "2차전지 장비 등(일반충방전기, 고온가압 충방전기 등)"},      # 이차전지 장비
        {"stock": "260870", "name": "SK시그넷", "market": "코스닥",
         "industry": "전동기, 발전기 및 전기 변환 · 공급 · 제어 장치 제조업",
         "product": "전기차 충전기"},                                          # 충전기
        {"stock": "006340", "name": "대원전선", "market": "유가증권",
         "industry": "절연선 및 케이블 제조업",
         "product": "전선,통신케이블,무선통신장비,합성수지 제조,도매/부동산 매매,임대"},  # EXTRA
        {"stock": "006260", "name": "LS", "market": "유가증권",
         "industry": "기타 금융업", "product": "전력용전선,일반전선"},          # 지주(이중계산)
        {"stock": "009470", "name": "삼화전기", "market": "유가증권",
         "industry": "전자부품 제조업", "product": "콘덴서 제조,판매"},        # 부품 후보
        {"stock": "999999", "name": "무슨제약", "market": "코스닥",
         "industry": "의약품 제조업", "product": "전력계통 소프트웨어"},        # 업종 제외
    ]
    UNI = [{"stock": "062040"}]

    def setUp(self):
        self.picked = {r["stock"] for r in S.pool(self.RECS, self.UNI)}

    def test_이미_모집단인_회사는_후보에_넣지_않는다(self):
        self.assertNotIn("062040", self.picked)

    def test_발주처_이차전지_충전기_지주_무관업종은_후보에서_뺀다(self):
        for st, why in (("015760", "전기업(발주처)"), ("262260", "이차전지 장비"),
                        ("260870", "전기차 충전기"), ("006260", "지주회사"),
                        ("999999", "의약품 업종")):
            self.assertNotIn(st, self.picked, "%s 가 후보에 남았다" % why)

    def test_EXTRA_와_소재부품_업종은_후보에_넣는다(self):
        self.assertIn("006340", self.picked, "EXTRA 지정 후보(대원전선)가 빠졌다")
        self.assertIn("009470", self.picked, "전자부품 업종 콘덴서 회사가 빠졌다")


class 판정선(unittest.TestCase):
    """모집단 실측값으로 맞춘 선이 흔들리면 알려 준다(kgrid_scan 주석의 점수표)."""

    def row(self, **kw):
        return dict({"ok": True, "strong": 0, "mid": 0, "neg": 0, "kepco": 0,
                     "mentions": {}, "terms": {}, "neg_terms": {},
                     "evidence": ["인용문"]}, **kw)

    def test_고유낱말이_0이면_관련낱말이_많아도_제외다(self):
        ok, _ = S.judge(self.row(strong=0, mid=41))
        self.assertFalse(ok)

    def test_모집단_하한_제룡산업_점수12는_승격선을_넘는다(self):
        ok, _ = S.judge(self.row(strong=2, mid=6, terms={"애자": 2}))
        self.assertTrue(ok)

    def test_한전_체계업체_언급이_받치면_점수6으로_승격된다(self):
        ok, why = S.judge(self.row(strong=2, mid=1, kepco=2, terms={"절연유": 2}))
        self.assertTrue(ok, why)
        self.assertIn("체계업체 언급", why)

    def test_비전력망_문맥이_점수의_두배를_넘으면_승격하지_않는다(self):
        ok, why = S.judge(self.row(strong=1, mid=0, neg=14, terms={"전력망": 1},
                                   neg_terms={"해양플랜트": 5, "조선소": 3}))
        self.assertFalse(ok)
        self.assertIn("압도한다", why)

    def test_전력을_파는_쪽은_제외다(self):
        """스펙 ④ — 금양그린파워 282720 실측: `발전매출`·`발전사업 허가`·`SMP+REC` 14회 대
        전력망 고유 낱말 2회. 신재생 발전소를 지어 전기를 파는 회사는 공급망이 아니다."""
        ok, why = S.judge(self.row(strong=2, mid=3, kepco=2, gen=14,
                                   gen_terms={"발전매출": 8, "발전사업 허가": 4},
                                   terms={"계통연계": 1, "송변전": 1}))
        self.assertFalse(ok)
        self.assertIn("파는", why)

    def test_정비_공급자는_gen_낱말이_있어도_남는다(self):
        """한전KPS 051600 실측: gen 1회 대 고유 낱말 26회(송전선로 유지·HVDC 설비점검)."""
        ok, why = S.judge(self.row(strong=26, mid=25, kepco=11, gen=1,
                                   gen_terms={"전력거래소": 1}, terms={"송변전": 9}))
        self.assertTrue(ok, why)

    def test_전력기기_낱말이_한_번도_없으면_남의_산업_이야기다(self):
        """SIMPAC 009160 실측: `전기강판` 4회가 전부고 변압기·차단기·배전은 0회다 —
        합금철이 전기강판 **생산 부원료**라는 뜻이지 전력기기 부품이 아니다."""
        ok, why = S.judge(self.row(strong=4, mid=0, terms={"전기강판": 3, "방향성 전기강판": 1}))
        self.assertFalse(ok)
        self.assertIn("한 번도 없다", why)

    def test_짧은_보고서도_빈_띠_위면_승격된다(self):
        """대원전선 006340 실측: 본문이 6.3KB뿐이라 점수는 10이지만 제품표 용도가
        `전력송배전`이다. 오탐 상한(5)과 모집단 하한(15) 사이의 빈 띠에 선을 둔 이유."""
        ok, why = S.judge(self.row(strong=2, mid=4, terms={"송배전": 2}))
        self.assertTrue(ok, why)
        self.assertGreaterEqual(S.PROMOTE_SCORE, 6)
        self.assertLessEqual(S.PROMOTE_SCORE, 14)


if __name__ == "__main__":
    unittest.main()
