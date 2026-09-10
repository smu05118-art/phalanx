#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_dicts — 조선 탭의 정적 사전 2종을 코드에서 생성한다.

  assets/parts_taxonomy.json  부품 분류(대분류 14 · 소분류 53)와 원문 제품 문구 → 분류 키워드
  assets/svg_regions.json     선박 단면 인포그래픽의 영역(폴리곤)·선종별 variant·기관실 확대

손으로 JSON을 쓰지 않고 여기서 만든다 — 키워드·좌표를 고칠 때 한 곳만 바꾸고, 두 파일의
교차 참조(소분류.region ↔ region.cats)를 생성 시점에 검증하기 위해서다(fail-closed).
설계 원문은 assets/design_taxonomy_source.json (부품 분류·관련도·SVG 배치 설계).

    python3 build_dicts.py            # 생성 + 검증
"""
import json
import os
import sys

from kship_lib import ASSETS, load_asset, write_asset

GROUPS = [
    ("HULL", "선체·구조", "Hull & structure"), ("PROP", "추진", "Propulsion"),
    ("ENG", "엔진부품", "Engine components"), ("CARGO", "화물", "Cargo systems"),
    ("DECK", "갑판", "Deck machinery"), ("PIPE", "배관·유체", "Piping & fluid"),
    ("ELEC", "전장·자동화", "Electrical & automation"), ("NAV", "항해통신", "Navigation & comms"),
    ("ACCOM", "거주구", "Accommodation"), ("SAFE", "안전·환경", "Safety & environment"),
    ("COAT", "도장·단열", "Coating & insulation"), ("OFFSH", "해양플랜트", "Offshore"),
    ("SVC", "설계·검사·인력", "Design, inspection & labour"), ("UNCL", "미분류", "Unclassified"),
]

# (id, ko, en, prio, ctx, kw, neg, regions)
#  prio 높을수록 먼저 매칭(특수 키워드가 일반 키워드를 이긴다). ctx=True 는 문맥(선박/조선/해양)
#  이 함께 있어야 채택 — 육상·자동차·플랜트와 겹치는 낱말.
CATS = [
    ("HULL.BLOCK", "선체블록·모듈", "Hull blocks & modules", 60, False,
     ["선체블록", "선박블록", "조립블록", "탑재블록", "메가블록", "PE블록", "블록", "선박구성부분품", "선박부분품", "선수부", "선미부", "보강재", "선체구조", "곡블록"],
     ["데크하우스", "거주구"], ["R_HULL_SIDE", "R_BOW"]),
    ("HULL.PLATE", "후판·형강·강재", "Plate & sections", 55, True,
     ["후판", "조선용후판", "형강", "선박용강재", "앵글", "벌브플랫", "강판", "부등변앵글", "조선용형강", "선재"],
     [], ["R_HULL_SIDE"]),
    ("HULL.CAST", "주단강(선미재·러더혼)", "Castings & forgings", 55, True,
     ["선미재", "스턴프레임", "러더혼", "주강품", "단조품", "주단강", "선박용주물", "형단조"], [], ["R_STERN_RUDDER"]),
    ("HULL.OUTFIT", "선체의장", "Hull outfitting", 40, True,
     ["그레이팅", "핸드레일", "맨홀", "선체의장", "의장품", "사다리", "래더"], [], ["R_MAIN_DECK"]),
    ("PROP.MAIN", "주기관", "Main engine", 80, False,
     ["주기관", "선박용엔진", "저속엔진", "2행정", "이중연료엔진", "DF엔진", "ME-GI", "X-DF", "메탄올엔진", "대형엔진", "대형선박용엔진", "저속디젤엔진", "선박엔진"],
     ["힘센엔진", "중속엔진", "발전기엔진", "엔진부품", "실린더라이너"], ["R_MAIN_ENGINE"]),
    ("PROP.AUX", "보기·발전기엔진·보일러", "Auxiliary engines & boilers", 75, False,
     ["힘센엔진", "중속엔진", "발전기엔진", "보조엔진", "보기", "선박용보일러", "발전기세트", "디젤발전기", "중형엔진", "4행정"], [], ["R_AUX"]),
    ("PROP.PROP", "프로펠러·스러스터", "Propellers & thrusters", 75, True,
     ["프로펠러", "추진기", "스러스터", "아지무스", "사이드스러스터", "포드추진", "바우스러스터"], ["로켓"], ["R_STERN_PROP", "R_BOW"]),
    ("PROP.SHAFT", "축계·선미관·베어링", "Shafting", 70, True,
     ["축계", "프로펠러축", "중간축", "선미관", "스턴튜브", "축베어링", "커플링", "감속기어", "추진축"], [], ["R_SHAFT"]),
    ("PROP.RUDDER", "러더·조타기", "Rudder & steering", 70, True,
     ["러더", "조타기", "조타장치", "러더스톡", "스티어링기어", "타기"], [], ["R_STERN_RUDDER"]),
    ("PROP.ESD", "에너지절감장치·축발전기", "Energy-saving devices", 65, True,
     ["ESD", "에너지절감장치", "프리스월", "러더벌브", "축발전기", "PTO", "샤프트제너레이터", "공기윤활", "덕트프로펠러"], [], ["R_STERN_PROP"]),
    ("ENG.LINER", "실린더라이너·커버", "Cylinder liners & covers", 85, False,
     ["실린더라이너", "실린더커버", "실린더헤드", "라이너"], [], ["Z_LINER"]),
    ("ENG.PISTON", "피스톤·링·크로스헤드", "Pistons", 85, False,
     ["피스톤", "피스톤링", "피스톤크라운", "연접봉", "크로스헤드", "커넥팅로드"], [], ["Z_PISTON"]),
    ("ENG.VALVE", "배기밸브·연료분사밸브", "Engine valves", 90, False,
     ["배기밸브", "흡배기밸브", "연료분사밸브", "인젝터", "밸브시트", "밸브스핀들", "엔진밸브", "선박엔진용밸브"], [], ["Z_VALVE"]),
    ("ENG.CRANK", "크랭크샤프트·베드플레이트·프레임", "Crankshaft & frame", 85, False,
     ["크랭크샤프트", "크랭크축", "캠샤프트", "베드플레이트", "엔진프레임", "엔진블록", "MBS", "엔진구조재", "베드플레이트"], [], ["Z_CRANK"]),
    ("ENG.TURBO", "터보차저", "Turbochargers", 85, False, ["터보차저", "과급기", "터보챠저"], [], ["Z_TURBO"]),
    ("ENG.FUEL", "연료공급(FGSS·LFSS)", "Fuel supply systems", 85, False,
     ["FGSS", "LFSS", "연료가스공급", "연료공급시스템", "고압펌프", "연료분사펌프", "벙커링", "연료공급장치", "LNG연료공급"], [], ["Z_FUEL", "R_FUEL_TANK"]),
    ("CARGO.LNG", "LNG 화물창·보냉재", "LNG containment & insulation", 95, False,
     ["화물창", "보냉재", "멤브레인", "Mark III", "NO96", "인바", "2차방벽", "트리플렉스", "R-PUF", "폴리우레탄폼", "단열패널", "보냉판넬", "앵커스트립", "마스틱", "초저온보냉재", "LNG보냉", "카고컨테인먼트"],
     [], ["R_CARGO_1", "R_CARGO_2", "R_CARGO_3", "R_CARGO_4"]),
    ("CARGO.LPG", "압력·독립형탱크", "LPG/ammonia tanks", 90, False,
     ["LPG탱크", "압력탱크", "독립형탱크", "TypeC", "Type C", "카고탱크제작", "암모니아탱크", "LPG Tank", "카고탱크"], [], ["R_CARGO_1", "R_CARGO_2", "R_CARGO_3", "R_CARGO_4"]),
    ("CARGO.PUMP", "카고펌프·심정펌프", "Cargo pumps", 88, False,
     ["카고펌프", "화물펌프", "화물유펌프", "심정펌프", "딥웰펌프", "스트리핑펌프", "카고펌프터빈", "카고오일펌프"], [], ["R_CARGO_MACHINERY"]),
    ("CARGO.GASHANDLE", "재액화·재기화·BOG", "Gas handling", 88, False,
     ["재액화", "재기화", "BOG", "가스압축기", "GCU", "가스연소장치", "질소발생", "화물취급", "카고핸들링", "기화기", "재액화장치", "재기화설비"], [], ["R_CARGO_MACHINERY"]),
    ("CARGO.CONT", "셀가이드·래싱", "Container securing", 88, False,
     ["셀가이드", "래싱브리지", "래싱", "트위스트락", "컨테이너고박", "고박장치"], [], ["R_DECK_CARGO", "R_CARGO_1", "R_CARGO_2", "R_CARGO_3", "R_CARGO_4"]),
    ("CARGO.INERT", "불활성가스·가스검지", "Inert gas", 85, False, ["불활성가스", "IGS", "이너트가스", "이너트가스시스템"], [], ["R_CARGO_MACHINERY"]),
    ("DECK.CRANE", "데크크레인·호스크레인", "Deck cranes", 80, True,
     ["데크크레인", "선박용크레인", "프로비전크레인", "호스핸들링", "넉클붐", "오프쇼어크레인", "크레인", "호스크레인", "선용크레인"], ["타워크레인", "천장크레인", "스테거"], ["R_CRANE_1", "R_CRANE_2", "R_CRANE_3"]),
    ("DECK.WINCH", "윈치·윈드라스·계류", "Winches & mooring", 78, True,
     ["윈치", "무어링", "윈드라스", "앵커", "앵커체인", "체인", "캡스턴", "계선", "계류장치", "무어링윈치"], ["교량용", "영구앵커"], ["R_AFT_MOORING", "R_FORECASTLE"]),
    ("DECK.HATCH", "해치커버·램프·카데크", "Hatch covers & ramps", 80, True,
     ["해치커버", "창구덮개", "램프", "카데크", "선측문", "스턴램프", "해치"], [], ["R_MAIN_DECK", "R_STERN_RAMP"]),
    ("DECK.OTHER", "갑판기계 기타", "Other deck machinery", 40, True,
     ["데크머시너리", "갑판기계", "통풍통", "벤틸레이터", "마스트", "갑판의장"], [], ["R_MAIN_DECK"]),
    ("PIPE.VALVE", "밸브·액추에이터", "Valves & actuators", 70, True,
     ["선박용밸브", "버터플라이밸브", "볼밸브", "글로브밸브", "게이트밸브", "체크밸브", "안전밸브", "극저온밸브", "액추에이터", "원격조작밸브", "밸브", "계장용밸브"], ["배기밸브", "연료분사밸브", "엔진밸브"], ["R_DECK_PIPING"]),
    ("PIPE.FITTING", "피팅·플랜지", "Fittings & flanges", 70, True,
     ["피팅", "관이음쇠", "플랜지", "엘보", "파이프피팅", "계장용피팅", "튜브피팅"], [], ["R_DECK_PIPING"]),
    ("PIPE.PIPE", "배관·스풀·극저온배관", "Piping & spools", 68, True,
     ["배관", "선박용배관", "파이프스풀", "스풀", "이중배관", "극저온배관", "진공단열배관", "배관제작", "파이프", "배관자재"], ["교량용케이블"], ["R_DECK_PIPING"]),
    ("PIPE.PUMP", "일반펌프", "Service pumps", 60, True,
     ["발라스트펌프", "빌지펌프", "냉각수펌프", "원심펌프", "펌프", "선박용펌프"], ["카고펌프", "고압펌프", "심정펌프"], ["R_AUX", "R_DOUBLE_BOTTOM"]),
    ("PIPE.HEX", "열교환기·조수기·청정기", "Heat exchangers & purifiers", 65, True,
     ["열교환기", "쿨러", "조수기", "청수발생기", "청정기", "유수분리기", "유청정기", "공기압축기", "압축기"], [], ["R_AUX"]),
    ("PIPE.BWTS", "평형수처리", "Ballast water treatment", 88, False, ["평형수", "BWTS", "발라스트수처리", "밸러스트수", "평형수처리"], [], ["R_DOUBLE_BOTTOM"]),
    ("PIPE.SCRUBBER", "스크러버·SCR·EGR", "Exhaust cleaning", 86, True,
     ["스크러버", "탈황", "SOx", "SCR", "탈질", "EGCS", "EGR", "배기가스정화", "탈황장치"], ["반도체", "백연"], ["R_FUNNEL"]),
    ("ELEC.CABLE", "선박용케이블", "Marine cables", 82, False,
     ["선박용케이블", "선박전선", "케이블트레이", "관통부", "MCT", "해양용케이블", "선용케이블"], ["해저케이블", "통신케이블", "교량용케이블", "타이케이블"], ["R_CABLE_RUN"]),
    ("ELEC.SWBD", "배전반·변압기·전기추진", "Switchboards & electric propulsion", 70, True,
     ["배전반", "배전판", "스위치보드", "분전반", "제어반", "MCC", "변압기", "정류기", "전동기", "인버터", "전력변환", "전기추진", "배터리시스템", "ESS", "선박용전기", "연료전지"], [], ["R_AUX", "R_CABLE_RUN"]),
    ("ELEC.LIGHT", "조명·항해등", "Lighting", 65, True, ["조명", "등기구", "항해등", "탐조등", "LED", "해상용조명"], [], ["R_DECKHOUSE"]),
    ("ELEC.AUTO", "자동화·계측", "Automation & sensors", 65, True,
     ["자동화", "통합제어", "AMS", "IAS", "알람모니터링", "원격제어", "레벨게이지", "탱크레벨", "유량계", "센서", "계측", "원격자동측정", "원격자동경보"], [], ["R_BRIDGE", "R_CABLE_RUN"]),
    ("NAV.NAV", "항해·통신·스마트십", "Navigation & communications", 80, True,
     ["항해장비", "레이더", "ECDIS", "자이로", "오토파일럿", "항해통신", "AIS", "VDR", "위성통신", "선내통신", "스마트십", "자율운항", "브릿지시스템", "GMDSS", "위성안테나", "해상용위성"], [], ["R_BRIDGE"]),
    ("ACCOM.DECKHOUSE", "거주구블록·선실모듈", "Deckhouse & cabin modules", 78, False,
     ["데크하우스", "거주구", "선실모듈", "거주구블록", "위생유닛", "캐빈유닛", "Deck House", "Living Quarter", "LQ"], [], ["R_DECKHOUSE"]),
    ("ACCOM.INTERIOR", "선실 내장·가구", "Cabin interiors", 70, True,
     ["선실내장", "내장재", "선실패널", "천장재", "바닥재", "선박용가구", "선실가구", "갤리", "주방기기", "선박용창", "선박용문", "방화문", "방화패널"], [], ["R_DECKHOUSE"]),
    ("ACCOM.HVAC", "공조·냉동·통풍", "HVAC", 65, True, ["HVAC", "공조", "냉동공조", "선박용냉동", "에어컨", "덕트", "냉동창고", "선박용공조"], [], ["R_DECKHOUSE"]),
    ("SAFE.FIRE", "소화·화재탐지", "Fire safety", 78, True,
     ["소화", "소화장치", "고정식소화", "CO2", "워터미스트", "스프링클러", "화재탐지", "화재경보", "소화설비"], ["소화기계"], ["R_LIFEBOAT", "R_DECK_CARGO"]),
    ("SAFE.LIFE", "구명정·대빗", "Life-saving", 78, True, ["구명정", "구명뗏목", "구명벌", "대빗", "구명동의", "구명설비", "탈출"], [], ["R_LIFEBOAT"]),
    ("SAFE.ENV", "오수처리·소각기·가스탐지", "Environmental", 60, True, ["오수처리", "소각기", "폐기물", "가스탐지", "가스검지", "환경장비"], [], ["R_AUX"]),
    ("COAT.PAINT", "선박용도료", "Marine coatings", 72, True, ["선박용도료", "방오도료", "방식도료", "도료", "페인트", "에폭시", "방오"], [], ["R_WATERLINE", "R_HULL_SIDE"]),
    ("COAT.WORK", "도장공사·족장·음극방식", "Coating works", 62, True, ["도장공사", "블라스팅", "족장", "발판", "표면처리", "희생양극", "음극방식", "ICCP", "도장"], [], ["R_HULL_SIDE"]),
    ("COAT.INSUL", "일반 단열·보온", "General insulation", 55, True, ["단열재", "보온재", "방열", "단열"], ["보냉재", "LNG"], ["R_DECKHOUSE"]),
    ("OFFSH.TOPSIDE", "탑사이드모듈", "Topside modules", 80, False,
     ["탑사이드", "해양모듈", "해양구조물", "자켓", "FPSO모듈", "해양설비", "해상풍력하부구조물", "하부구조물", "모노파일", "재킷"], [], ["R_TOPSIDE_1", "R_TOPSIDE_2", "R_TOPSIDE_3", "R_TOPSIDE_4"]),
    ("OFFSH.MOORING", "터렛·계류시스템", "Turret & mooring", 80, False, ["터렛", "계류시스템", "계류체인", "무어링시스템"], [], ["R_TURRET"]),
    ("OFFSH.SUBSEA", "라이저·해저구조", "Risers & subsea", 80, False, ["라이저", "해저구조물", "서브시", "해저"], ["해저케이블"], ["R_TURRET"]),
    ("SVC.DESIGN", "선박설계", "Ship design", 50, True, ["선박설계", "기본설계", "상세설계", "생산설계", "엔지니어링", "설계"], [], []),
    ("SVC.INSPECT", "비파괴검사·시운전", "Inspection & trials", 50, True, ["비파괴검사", "시운전", "모형시험", "검사", "선급"], [], []),
    ("SVC.LABOR", "사내협력·임가공", "Subcontract labour", 45, True, ["사내협력", "임가공", "블록가공", "의장공사", "용접"], [], []),
]

CTX_KW = ["선박", "조선", "해양", "선용", "marine", "ship", "vessel", "offshore", "해상"]

# ── SVG 영역 ─────────────────────────────────────────────────
# 뷰박스 1000×400. 선미(좌)→선수(우). 용골 y≈360, 흘수선 y≈300, 주갑판 y≈215.
# 좌표는 설계값을 출발점으로 겹치지 않게 다듬었다. 폴리곤 [[x,y],…] 또는 circle [cx,cy,r].
def P(*pts):
    return [list(p) for p in pts]


REGIONS = [
    # id, ko, cats, zoom, {variant: poly}
    ("R_HULL_SIDE", "선체 외판", ["HULL.PLATE", "HULL.BLOCK", "COAT.WORK"], None,
     {"default": P((60, 306), (920, 306), (955, 330), (880, 360), (125, 360), (45, 335))}),
    ("R_DOUBLE_BOTTOM", "이중저·발라스트", ["PIPE.BWTS", "PIPE.PUMP"], None,
     {"default": P((135, 344), (875, 344), (875, 356), (135, 356))}),
    ("R_WATERLINE", "흘수선(방오도장)", ["COAT.PAINT"], None,
     {"default": P((58, 293), (922, 293), (922, 305), (58, 305))}),
    ("R_STERN_RUDDER", "러더", ["PROP.RUDDER", "HULL.CAST"], None,
     {"default": P((28, 300), (58, 300), (58, 364), (28, 364))}),
    ("R_STERN_PROP", "프로펠러", ["PROP.PROP", "PROP.ESD"], None,
     {"default": {"circle": [82, 330, 24]}}),
    ("R_SHAFT", "축계", ["PROP.SHAFT"], None,
     {"default": P((108, 322), (198, 322), (198, 334), (108, 334))}),
    ("R_ENGINE_ROOM", "기관실", [], "engine",
     {"default": P((120, 216), (280, 216), (280, 342), (130, 342))}),
    ("R_MAIN_ENGINE", "주기관", ["PROP.MAIN", "ENG.LINER", "ENG.PISTON", "ENG.VALVE", "ENG.CRANK", "ENG.TURBO"], "engine",
     {"default": P((150, 262), (250, 262), (250, 340), (150, 340))}),
    ("R_AUX", "보기·발전기", ["PROP.AUX", "ELEC.SWBD", "PIPE.HEX", "PIPE.PUMP", "SAFE.ENV"], None,
     {"default": P((135, 222), (270, 222), (270, 256), (135, 256))}),
    ("R_FUEL_TANK", "연료탱크", ["ENG.FUEL"], None,
     {"default": P((256, 262), (278, 262), (278, 340), (256, 340))}),
    ("R_FUNNEL", "연돌", ["PIPE.SCRUBBER"], None,
     {"default": P((192, 62), (238, 62), (238, 198), (192, 198)),
      "CONT": P((150, 62), (196, 62), (196, 198), (150, 198))}),
    ("R_BRIDGE", "조타실", ["NAV.NAV", "ELEC.AUTO"], None,
     {"default": P((110, 72), (208, 72), (208, 96), (110, 96)),
      "CONT": P((520, 72), (618, 72), (618, 96), (520, 96)),
      "NAVAL": P((300, 62), (440, 62), (440, 96), (300, 96))}),
    ("R_DECKHOUSE", "거주구", ["ACCOM.DECKHOUSE", "ACCOM.INTERIOR", "ACCOM.HVAC", "ELEC.LIGHT", "COAT.INSUL"], None,
     {"default": P((120, 98), (200, 98), (200, 214), (120, 214)),
      "CONT": P((530, 98), (610, 98), (610, 214), (530, 214)),
      "NAVAL": P((310, 98), (430, 98), (430, 214), (310, 214))}),
    ("R_LIFEBOAT", "구명정·소화", ["SAFE.LIFE", "SAFE.FIRE"], None,
     {"default": P((92, 150), (118, 150), (118, 170), (92, 170)),
      "CONT": P((500, 150), (526, 150), (526, 170), (500, 170))}),
    ("R_AFT_MOORING", "선미 계류", ["DECK.WINCH"], None,
     {"default": P((90, 182), (118, 182), (118, 214), (90, 214))}),
    ("R_CARGO_MACHINERY", "화물기계실", ["CARGO.GASHANDLE", "CARGO.INERT", "CARGO.PUMP"], None,
     {"default": P((284, 152), (360, 152), (360, 194), (284, 194)),
      "CONT": [], "BULK": [], "PCTC": []}),
    ("R_CARGO_1", "화물창 1", ["CARGO.LNG", "CARGO.LPG", "CARGO.PUMP", "CARGO.CONT", "HULL.PLATE"], None,
     {"default": P((284, 218), (428, 218), (428, 342), (284, 342))}),
    ("R_CARGO_2", "화물창 2", ["CARGO.LNG", "CARGO.LPG", "CARGO.PUMP", "CARGO.CONT", "HULL.PLATE"], None,
     {"default": P((434, 218), (578, 218), (578, 342), (434, 342))}),
    ("R_CARGO_3", "화물창 3", ["CARGO.LNG", "CARGO.LPG", "CARGO.PUMP", "CARGO.CONT", "HULL.PLATE"], None,
     {"default": P((584, 218), (728, 218), (728, 342), (584, 342))}),
    ("R_CARGO_4", "화물창 4", ["CARGO.LNG", "CARGO.LPG", "CARGO.PUMP", "CARGO.CONT", "HULL.PLATE"], None,
     {"default": P((734, 218), (876, 218), (876, 342), (734, 342))}),
    ("R_MAIN_DECK", "주갑판", ["DECK.HATCH", "DECK.OTHER", "HULL.OUTFIT"], None,
     {"default": P((284, 196), (878, 196), (878, 214), (284, 214))}),
    ("R_DECK_PIPING", "갑판 배관", ["PIPE.PIPE", "PIPE.VALVE", "PIPE.FITTING"], None,
     {"default": P((300, 184), (860, 184), (860, 194), (300, 194)),
      "CONT": [], "BULK": [], "PCTC": []}),
    ("R_CRANE_1", "크레인 1", ["DECK.CRANE"], None,
     {"default": [], "BULK": P((422, 118), (438, 118), (438, 194), (422, 194)),
      "OFFSH": P((360, 100), (376, 100), (376, 194), (360, 194))}),
    ("R_CRANE_2", "크레인 2", ["DECK.CRANE"], None,
     {"default": [], "BULK": P((572, 118), (588, 118), (588, 194), (572, 194))}),
    ("R_CRANE_3", "크레인 3", ["DECK.CRANE"], None,
     {"default": [], "BULK": P((722, 118), (738, 118), (738, 194), (722, 194))}),
    ("R_DECK_CARGO", "갑판적 컨테이너", ["CARGO.CONT", "SAFE.FIRE"], None,
     {"default": [], "CONT": P((284, 112), (878, 112), (878, 194), (284, 194)),
      "PCTC": P((284, 112), (878, 112), (878, 194), (284, 194))}),
    ("R_STERN_RAMP", "선미 램프", ["DECK.HATCH"], None,
     {"default": [], "PCTC": P((42, 216), (120, 216), (120, 258), (42, 258))}),
    ("R_FORECASTLE", "선수루", ["DECK.WINCH"], None,
     {"default": P((882, 152), (958, 152), (958, 214), (882, 214))}),
    ("R_BOW", "선수·구상선수", ["HULL.BLOCK", "PROP.PROP"], None,
     {"default": P((882, 218), (958, 218), (994, 300), (944, 346), (882, 346))}),
    ("R_CABLE_RUN", "케이블 런", ["ELEC.CABLE", "ELEC.AUTO", "ELEC.SWBD"], None,
     {"default": P((132, 204), (880, 204), (880, 210), (132, 210))}),
    ("R_TOPSIDE_1", "탑사이드 1", ["OFFSH.TOPSIDE"], None, {"default": [], "OFFSH": P((300, 104), (430, 104), (430, 194), (300, 194))}),
    ("R_TOPSIDE_2", "탑사이드 2", ["OFFSH.TOPSIDE"], None, {"default": [], "OFFSH": P((442, 104), (572, 104), (572, 194), (442, 194))}),
    ("R_TOPSIDE_3", "탑사이드 3", ["OFFSH.TOPSIDE"], None, {"default": [], "OFFSH": P((584, 104), (714, 104), (714, 194), (584, 194))}),
    ("R_TOPSIDE_4", "탑사이드 4", ["OFFSH.TOPSIDE"], None, {"default": [], "OFFSH": P((726, 104), (856, 104), (856, 194), (726, 194))}),
    ("R_TURRET", "터렛·계류", ["OFFSH.MOORING", "OFFSH.SUBSEA"], None, {"default": [], "OFFSH": P((900, 218), (958, 218), (958, 346), (900, 346))}),
]

ENGINE_ZOOM = [
    ("Z_LINER", "실린더라이너·커버", ["ENG.LINER"], P((330, 70), (670, 70), (670, 150), (330, 150))),
    ("Z_VALVE", "배기밸브·연료분사", ["ENG.VALVE"], P((330, 20), (670, 20), (670, 66), (330, 66))),
    ("Z_PISTON", "피스톤·크로스헤드", ["ENG.PISTON"], P((330, 154), (670, 154), (670, 250), (330, 250))),
    ("Z_CRANK", "크랭크샤프트·베드플레이트", ["ENG.CRANK"], P((300, 254), (700, 254), (700, 370), (300, 370))),
    ("Z_TURBO", "터보차저", ["ENG.TURBO"], P((720, 40), (900, 40), (900, 180), (720, 180))),
    ("Z_FUEL", "연료공급(FGSS·고압펌프)", ["ENG.FUEL"], P((100, 40), (280, 40), (280, 180), (100, 180))),
]

Z_ORDER = ["R_HULL_SIDE", "R_DOUBLE_BOTTOM", "R_WATERLINE", "R_CARGO_1", "R_CARGO_2", "R_CARGO_3", "R_CARGO_4",
           "R_ENGINE_ROOM", "R_MAIN_ENGINE", "R_AUX", "R_FUEL_TANK", "R_SHAFT", "R_STERN_PROP", "R_STERN_RUDDER",
           "R_BOW", "R_FORECASTLE", "R_AFT_MOORING", "R_MAIN_DECK", "R_DECK_PIPING", "R_CABLE_RUN",
           "R_CARGO_MACHINERY", "R_DECK_CARGO", "R_STERN_RAMP", "R_CRANE_1", "R_CRANE_2", "R_CRANE_3",
           "R_TOPSIDE_1", "R_TOPSIDE_2", "R_TOPSIDE_3", "R_TOPSIDE_4", "R_TURRET",
           "R_DECKHOUSE", "R_LIFEBOAT", "R_FUNNEL", "R_BRIDGE"]

VARIANTS = ["default", "CONT", "BULK", "PCTC", "OFFSH", "NAVAL"]


def build():
    cats = []
    for cid, ko, en, prio, ctx, kw, neg, regions in CATS:
        cats.append({"id": cid, "p": cid.split(".")[0], "ko": ko, "en": en, "prio": prio,
                     "ctx": ctx, "ctx_kw": CTX_KW if ctx else [], "kw": kw, "neg": neg, "region": regions})
    tax = {"ver": "2026-09", "groups": [{"id": g, "ko": ko, "en": en, "order": i} for i, (g, ko, en) in enumerate(GROUPS)],
           "cats": cats}
    regions = []
    for rid, ko, rcats, zoom, variants in REGIONS:
        v = {}
        for name in VARIANTS:
            if name in variants:
                v[name] = variants[name]
            elif name != "default":
                v[name] = variants.get("default", [])
        regions.append({"id": rid, "ko": ko, "cats": rcats, "zoom": zoom, "variants": v})
    svg = {"viewBox": "0 0 1000 400", "z": Z_ORDER, "variants": VARIANTS,
           "chips": ["ELEC", "PIPE", "COAT", "SAFE", "SVC", "HULL"],
           "regions": regions,
           "engine_zoom": {"viewBox": "0 0 1000 400",
                           "regions": [{"id": i, "ko": ko, "cats": c, "poly": p} for i, ko, c, p in ENGINE_ZOOM]}}
    # ── 교차 검증(fail-closed) ──
    cat_ids = {c["id"] for c in cats}
    reg_ids = {r["id"] for r in regions} | {z["id"] for z in svg["engine_zoom"]["regions"]}
    for c in cats:
        bad = [r for r in c["region"] if r not in reg_ids]
        if bad:
            raise RuntimeError("%s 가 없는 영역을 가리킨다: %s" % (c["id"], bad))
    for r in regions:
        bad = [x for x in r["cats"] if x not in cat_ids]
        if bad:
            raise RuntimeError("%s 가 없는 소분류를 가리킨다: %s" % (r["id"], bad))
    if set(Z_ORDER) != {r["id"] for r in regions}:
        raise RuntimeError("z-order 와 영역 목록이 다르다: %s" % (set(Z_ORDER) ^ {r["id"] for r in regions}))
    st = load_asset("ship_types.json")
    rel_keys = set(st["rel"]["LNGC"])
    if rel_keys != cat_ids:
        raise RuntimeError("ship_types.rel 과 소분류가 다르다: %s" % sorted(rel_keys ^ cat_ids))
    # 키워드 중복(같은 키워드가 두 소분류에) — 우선순위가 같으면 모호하다
    seen = {}
    for c in cats:
        for k in c["kw"]:
            key = k.lower().replace(" ", "")
            if key in seen and seen[key][0] != c["id"] and seen[key][1] == c["prio"]:
                raise RuntimeError("키워드 '%s' 가 %s·%s 에 같은 우선순위로 있다" % (k, seen[key][0], c["id"]))
            seen.setdefault(key, (c["id"], c["prio"]))
        c["kw"] = list(dict.fromkeys(c["kw"]))          # 같은 소분류 안의 중복은 조용히 접는다
    write_asset("parts_taxonomy.json", tax)
    write_asset("svg_regions.json", svg)
    return tax, svg


def main():
    tax, svg = build()
    print("parts_taxonomy.json: groups %d · cats %d · kw %d" % (
        len(tax["groups"]), len(tax["cats"]), sum(len(c["kw"]) for c in tax["cats"])))
    print("svg_regions.json: regions %d · engine_zoom %d · variants %s" % (
        len(svg["regions"]), len(svg["engine_zoom"]["regions"]), svg["variants"]))


if __name__ == "__main__":
    sys.exit(main())
