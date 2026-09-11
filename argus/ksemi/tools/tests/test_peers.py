# -*- coding: utf-8 -*-
"""계약: 상장사 이름 언급의 경계와 관계 분류(ksemi_peers).

이 탭의 덫은 전부 **원문에서 실제로 밟은 것**이다(ksemi_peers 모듈 docstring).
문장은 정기보고서 2026 반기 II절에서 그대로 옮겼다 — 줄이지 않았다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C                                                    # noqa: E402
import ksemi_peers as P                                                # noqa: E402

# RF머트리얼즈 20260814 — `3S`(060310)가 `3S-Photonics` 안에서 걸렸던 문장
RF_3S = ("광 Pump 모듈 분야에서 세계시장을 선도하고 있는 LUMENTUM에 공급하고 있으며, "
         "JDSU, OCLARO, 3S-Photonics 등의 글로벌 업체에 진입을 통한 매출 증대를 목표로")
# 미래산업 20260813 — 목록 안에 자기 이름이 있다(경쟁사 목록)
MIRAE = ("국내에 Test Handler를 공급하고 있는 업체는 미래산업(주), (주)제이티, (주)테크윙, "
         "AMT 그리고 일본의 Advantest 등이 있습니다.")
# 뉴파워프라즈마 20260814 — 목록 안에 자기 이름이 없다(자기 RPG가 들어가는 전방 장비사)
NPP = ("③ 주요제품의 설명 박막 공정의 종류는 PECVD, LPCVD, PEALD 종류가 있으며, 장비 "
       "제작사는 국내의 원익 IPS, 주성엔지니어링, 테스, 유진테크 등이 있고, 해외 장비 "
       "제작사는 Applied Materials (AKT), LAM, ULVAC, ASM 등이 있습니다.")
# 코스텍시스템 20260814 — 고객사 나열
KOSTEK = ("주요 고객사로는 삼성전자, SK하이닉스, 원익IPS, Tokyo Electron(TEL), ULVAC, "
          "SGS, 서울바이오시스, LC Square 등이 있습니다.")
# 하나마이크론 20260814 — 종속회사
HANA = ("비재무사항에 기재한 연결 대상법인에는 당사를 비롯한 주요 종속회사인 "
        "하나머티리얼즈(주)와 HT MICRON SEMICONDUTORES S.A.를 포함합니다.")


def call(text, name, self_name=None):
    m = P.name_rx(name).search(text)
    if not m:
        return None
    return P.classify(text, m.span(),
                      P.name_rx(self_name) if self_name else None)


class TestNameBoundary(unittest.TestCase):
    """이름 경계 — 짧은 이름 하나가 새면 지도 전체가 거짓말이 된다."""

    def test_hyphenated_foreign_name_is_not_our_3S(self):
        self.assertIsNone(P.name_rx("3S").search(RF_3S))

    def test_3S_alone_still_matches(self):
        self.assertTrue(P.name_rx("3S").search("당사는 3S 와 거래하고 있습니다."))

    def test_tes_is_not_inside_test_or_testna(self):
        for s in ("테스트 소켓", "유니테스트", "두산테스나", "테스팅"):
            self.assertIsNone(P.name_rx("테스").search(s), s)
        self.assertTrue(P.name_rx("테스").search("원익 IPS, 주성엔지니어링, 테스, 유진테크"))

    def test_psk_does_not_swallow_psk_holdings(self):
        self.assertIsNone(P.name_rx("피에스케이").search("피에스케이홀딩스의 자회사"))
        self.assertTrue(P.name_rx("피에스케이홀딩스").search("피에스케이홀딩스의 자회사"))

    def test_miko_does_not_match_its_subsidiaries(self):
        for s in ("㈜미코세라믹스", "㈜미코하이테크"):
            self.assertIsNone(P.name_rx("미코").search(s), s)

    def test_particles_are_not_part_of_the_name(self):
        """「테크윙의」·「원익IPS는」을 놓치면 언급 지도가 통째로 얇아진다."""
        self.assertTrue(P.name_rx("테크윙").search("테크윙의 핸들러"))
        self.assertTrue(P.name_rx("원익IPS").search("원익IPS는 증착 장비를"))
        self.assertIsNone(P.name_rx("테스").search("테스나가 과점하고"))   # `나`는 조사에서 뺐다

    def test_space_between_korean_and_ascii_runs(self):
        """뉴파워프라즈마는 같은 문단에서 `원익IPS`와 `원익 IPS`를 섞어 쓴다."""
        self.assertTrue(P.name_rx("원익IPS").search("장비 제작사는 국내의 원익 IPS, 주성엔지니어링"))

    def test_common_noun_name_needs_a_corporate_mark(self):
        """`미래산업`은 보통명사이기도 하다 — 법인 표시가 있어야 회사로 센다."""
        self.assertIn("025560", P.NEEDS_MARK)
        text = "유비쿼터스 시대 등의 미래산업과 더불어 디스플레이 산업은"
        self.assertTrue(P.name_rx("미래산업").search(text))      # 이름은 맞지만
        d = P.build(only={"264660"})                            # 씨앤지하이테크
        got = [m["name"] for r in d["rows"] for m in r["mentions"]]
        self.assertNotIn("미래산업", got)                        # 간선으로는 남지 않는다

    def test_longer_name_wins_in_build_order(self):
        """빌드는 긴 이름부터 맞춘다 — 같은 구간을 두 번 세지 않기 위한 전제."""
        names = ["피에스케이", "피에스케이홀딩스", "하나머티리얼즈"]
        order = sorted(names, key=lambda n: -len(n))
        self.assertEqual(order[0], "피에스케이홀딩스")


class TestClassify(unittest.TestCase):
    """관계 분류 — 단서 낱말과 '목록에 내가 있는가'."""

    def test_supplier_list_containing_self_is_competition(self):
        kind, cue = call(MIRAE, "테크윙", self_name="미래산업")
        self.assertEqual(kind, "경쟁")
        self.assertTrue(cue)

    def test_maker_list_without_self_is_left_as_a_list(self):
        kind, _cue = call(NPP, "원익IPS", self_name="뉴파워프라즈마")
        self.assertEqual(kind, "업체나열")   # 경쟁이라고 적으면 틀린다(RPG는 저 장비에 들어간다)

    def test_customer_list(self):
        self.assertEqual(call(KOSTEK, "원익IPS", self_name="코스텍시스템")[0], "고객")

    def test_subsidiary(self):
        self.assertEqual(call(HANA, "하나머티리얼즈", self_name="하나마이크론")[0], "계열")

    def test_no_cue_means_unclassified(self):
        text = "특허권 디지털 홀로그래피를 이용한 입체 측정장치 디아이티 /펨트론 /전북대 2011-09-30"
        self.assertEqual(call(text, "펨트론", self_name="디아이티"), ("미분류", ""))

    def test_nearest_cue_wins(self):
        """멀리 있는 '합작'이 바로 옆 '경쟁사'를 이기면 안 된다."""
        text = ("당사는 1990년 합작계약으로 설립되었습니다. " + "가" * 200 +
                " 구분 경쟁사 월덱스, 케이씨파츠텍 등")
        self.assertEqual(call(text, "월덱스", self_name="씨엠티엑스")[0], "경쟁")

    def test_cue_does_not_fire_inside_a_longer_word(self):
        """코미코 *"부품 제작**사업**을 영위하며"* — `제작사`로 읽으면 업체 목록이 된다."""
        text = ("분할 이후 존속법인은 반도체 고기능성 부품 제작사업을 영위하며 사명을 "
                "미코로 변경하였고, 분할 신설법인인 당사는 코미코의 사명을 사용하고 있습니다.")
        self.assertEqual(call(text, "미코", self_name="코미코")[0], "계열")

    def test_far_away_dangsa_does_not_make_it_competition(self):
        """'당사'는 흔하다 — 언급에서 멀면 목록 소속 근거가 못 된다."""
        text = "당사는 RF 제너레이터를 만듭니다. " + "나" * 150 + " 장비 제작사는 국내의 원익IPS 등"
        self.assertEqual(call(text, "원익IPS", self_name="뉴파워프라즈마")[0], "업체나열")


@unittest.skipUnless(C.has_asset("peers.json"), "assets/peers.json 없음")
class TestStoredPeers(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.d = C.asset("peers.json")
        cls.scan = {r["stock"]: r for r in C.asset("scan.json")["rows"]}
        cls.uni = {r["stock"]: r for r in C.asset("universe.json")["rows"]}

    def test_every_edge_is_between_members(self):
        bad = []
        for r in self.d["rows"]:
            for m in r["mentions"]:
                for st in (r["stock"], m["stock"]):
                    v = (self.scan.get(st) or {}).get("verdict")
                    seed = (self.uni.get(st) or {}).get("source") == "지정"
                    if not (v == "편입" or seed):
                        bad.append(st)
        self.assertEqual(bad, [])

    def test_no_self_edges(self):
        bad = [r["stock"] for r in self.d["rows"]
               if any(m["stock"] == r["stock"] for m in r["mentions"])]
        self.assertEqual(bad, [])

    def test_every_mention_carries_a_quote(self):
        bad = [(r["stock"], m["stock"]) for r in self.d["rows"] for m in r["mentions"]
               if not (m.get("quote") or "").strip()]
        self.assertEqual(bad, [])

    def test_classified_mentions_carry_the_cue_word(self):
        bad = [(r["stock"], m["stock"], m["kind"]) for r in self.d["rows"] for m in r["mentions"]
               if m["kind"] != "미분류" and not (m.get("cue") or "").strip()]
        self.assertEqual(bad, [])

    def test_reverse_index_matches_the_rows(self):
        fwd = sorted((r["stock"], m["stock"]) for r in self.d["rows"] for m in r["mentions"])
        rev = sorted((m["stock"], k) for k, v in self.d["_by_target"].items() for m in v)
        self.assertEqual(fwd, rev)


if __name__ == "__main__":
    unittest.main()
