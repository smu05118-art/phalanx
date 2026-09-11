#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_dicts — 방산 탭의 정적 사전을 코드에서 생성한다(손으로 JSON을 쓰지 않는다).

  assets/domains.json         계통(domain) 8 + 민수(CIVIL) — 계약명·품목명 → 계통
  assets/contract_types.json  계약유형(체계개발·최초양산·후속양산·성능개량·PBL·구매)
  assets/parts_taxonomy.json  부품 계층(대분류 10 · 소분류) — 제품 문구 → 부품
  assets/svg_regions.json     무기체계 실루엣 4종(전차·전투기·함정·미사일)의 영역 폴리곤

한 곳에서 만드는 이유는 **교차 참조를 생성 시점에 검증**하기 위해서다 —
소분류의 `regions` 가 실제 SVG 영역에 있는지, 영역의 `cats` 가 실제 소분류인지(fail-closed).

계통 매칭은 길이가 아니라 **우선순위**로 한다. `천궁Ⅱ 다기능레이다 수출`을 길이로 고르면
`다기능레이다`(ISR)가 이기지만, 이 계약이 속한 **무기체계**는 천궁(유도무기)이다.
체계 이름(천궁·L-SAM·KF-21)에 가장 높은 우선순위를 준다.

    python3 build_dicts.py --write
"""
import argparse
import json
import sys

from kdef_lib import load_asset, write_asset

# ── 계통 ───────────────────────────────────────────────────
# (id, ko, en, slot, 체계이름[prio 90], 일반어휘[prio 50])
DOMAINS = [
    ("GROUND", "지상", "Land systems", 1,
     ["K2전차", "K1전차", "K1A2", "K9자주포", "K9", "K10", "K21", "K808", "K806", "K151",
      "차륜형장갑차", "소형전술차량", "중구난차량", "교량전차", "구난전차", "K600", "K242", "K277"],
     ["전차", "자주포", "장갑차", "궤도차량", "전술차량", "군용차량", "군수차량", "지상무기",
      "보병전투차", "전투차량", "다목적차량", "무한궤도", "지상체계", "야전"]),
    ("NAVAL", "해상", "Naval systems", 2,
     ["장보고", "KDDX", "KSS", "도산안창호", "울산급", "충남함", "포항급", "천왕봉", "소해함",
      "수상함전투체계", "잠수함전투체계", "함정전투체계"],
     ["함정", "수상함", "잠수함", "구축함", "호위함", "초계함", "상륙함", "군수지원함", "경비함",
      "함포", "어뢰", "소나", "음탐", "기뢰", "함교", "선체고정", "해군", "함정용", "잠수정"]),
    ("AIR", "공중", "Air systems", 3,
     ["KF-21", "KF-X", "KF21", "T-50", "FA-50", "TA-50", "KT-1", "KUH-1", "수리온", "LAH", "LCH",
      "MUH-1", "마린온", "P-3", "F-15K", "F-15EX", "F-15", "F-16", "F-35", "C-130", "KC-330",
      "H-47", "CH-47", "UH-60", "HH-60", "AH-64", "MH-60", "AEW&C", "AEW", "KUH", "MRO"],
     ["전투기", "훈련기", "헬기", "회전익", "고정익", "완제기", "무인기", "UAV", "무인항공기",
      "항공기", "기체구조물", "동체", "착륙장치", "항공엔진", "비행체", "항공전자", "항전",
      "주익", "미익", "날개", "파일런"]),
    ("MISSILE", "유도무기", "Guided weapons", 4,
     ["천궁", "철매", "L-SAM", "LSAM", "M-SAM", "SA-MSAM", "MSAM", "해궁", "해성", "현무",
      "신궁", "천검", "비궁", "천룡", "장공지", "천무", "군위성", "PGM"],
     ["유도탄", "유도무기", "미사일", "대공유도", "대함유도", "대지유도", "공대지", "공대공",
      "함대공", "지대공", "지대지", "다련장", "유도로켓", "탄도탄", "요격", "발사대"]),
    # `다기능레이다`는 강한 이름이 아니다 — `천궁Ⅱ 다기능레이다`는 천궁(유도무기) 체계의
    # 구성품이고, 계약이 속한 무기체계는 천궁이다. 체계 이름만 prio 90 에 둔다.
    ("ISR", "감시정찰", "ISR", 5,
     ["SAR위성", "정찰위성", "425사업", "군정찰위성"],
     ["다기능레이다", "다기능레이더", "TOD", "EO/IR",
      "레이다", "레이더", "전자광학", "열영상", "열상", "야시", "야간투시", "적외선", "감시",
      "정찰", "탐지", "추적", "위성", "관측", "표적획득", "피아식별", "전자전", "ESM", "전파탐지"]),
    ("C4I", "지휘통제통신", "C4I", 6,
     ["Link-K", "링크-K", "TICN", "전술정보통신", "공지통신무전기", "M-SAM지휘", "전장관리체계"],
     ["C4I", "지휘통제", "지휘소", "전술데이터링크", "데이터링크", "무전기", "통신장비", "암호",
      "전술통신", "위성통신", "군용통신", "통신체계", "지휘체계", "전산"]),
    ("FIRE", "화력·탄약", "Fires & ammunition", 7,
     ["K105", "155mm", "105mm", "81mm", "60mm", "12.7mm", "5.56mm", "K2소총"],
     ["탄약", "포탄", "유탄", "신관", "추진제", "화약", "화공품", "박격포", "포신", "포열",
      "소총", "기관총", "총포", "탄두", "장약", "뇌관", "사격통제", "중구경", "대공포",
      "항공투하탄", "탄체", "폭탄"]),
    ("SUPPORT", "지원·정비", "Support & MRO", 8,
     ["PBL", "창정비", "종합군수지원", "ILS"],
     ["정비", "수리부속", "시뮬레이터", "훈련체계", "모의훈련", "군수지원", "성능개선용역",
      "방탄", "방검", "피복", "위장", "군장", "야전급식", "의무"]),
    # 방산업체가 공시하는 **민수** 계약 — 버리지 않고 갈라 둔다(현대로템 철도·KAI 민항기).
    ("CIVIL", "민수", "Civil", 0,
     ["에코플랜트", "ONCF", "B787", "B767", "A350", "A320", "A321", "B737", "SWIFT", "SUMMIT",
      "ISO20022"],
     # 상선·해양플랜트 — 방산업체(한화오션)가 같은 공시 양식으로 올린다. 방산으로 세면
     # 계통 '미상'이 절반을 넘고 계약 금액이 통째로 부풀려진다(실측 145건 중 절반이 상선·철도).
     ["컨테이너선", "운반선", "유조선", "원유운반", "벌크선", "LNGC", "LPGC", "VLCC", "VLGC",
      "VLAC", "PC선", "FPSO", "FLNG", "해상철구조물", "드릴십", "셔틀탱커", "해상풍력",
      "철도차량", "전동차", "고속철", "고속전철", "기관차", "객차", "동차", "트램", "경전철",
      "차량기지", "신호시스템", "도시철도", "철도청", "EMU", "플랜트",
      "제철설비", "자동차설비", "정수", "수소충전", "발전설비", "집단에너지", "풍력", "아스팔트",
      "공작기계", "반도체장비", "민항", "여객기", "화물기", "상용차", "승용차", "버스", "굴착기",
      "신도시", "솔루션 구입", "유지보수 연장", "전산시스템", "라이선스",
      "식각장비", "중계기", "터빈블레이드", "원자력", "한울", "한빛", "정유", "석유화학"]),
]

# ── 계약유형 ───────────────────────────────────────────────
# FINDINGS §3 — 유형 낱말이 `- 체결계약명` 원문에 그대로 적힌다. 위에서부터 먼저 맞는 것.
# '수출'은 유형이 아니라 **판로**다(내수 후속양산의 수출판이 있다) — 계약유형에 섞지 않고
# party_kind(G2G·FOREIGN)와 계약명의 수출 낱말로 따로 표시한다.
CONTRACT_TYPES = [
    ("UPGRADE", "성능개량", "Upgrade", r"성능\s*개량|성능개선|개량사업|Retrofit", 3),
    ("PBL", "후속군수지원·정비", "Sustainment/PBL", r"PBL|성과기반군수지원|후속\s*군수지원|창정비|"
     r"외주\s*정비|정비\s*용역|수리부속|MRO|종합군수지원|ILS", 8),
    ("RND", "탐색·체계개발", "R&D", r"체계\s*개발|탐색\s*개발|응용연구|시험개발|체계\s*통합|시제|"
     r"연구\s*개발|선행연구|기술개발|실용화", 6),
    ("FIRST", "최초양산", "Initial production", r"최초\s*양산|초도\s*양산|초도\s*생산", 1),
    ("FOLLOW", "후속양산", "Follow-on production", r"후속\s*양산|\d+\s*차\s*양산|양산\s*\d+차|재양산|"
     r"추가\s*양산|양산", 2),
    # `H-47 항공전자장비 공급`처럼 유형 낱말 없이 '공급'만 적는 공시가 많다(실측 127건 중 절반).
    # 공시 서식 자체가 「단일판매ㆍ공급계약체결」이므로 '공급·납품·구매'는 물품 계약으로 본다.
    # 양산·개량·개발·PBL 이 먼저 판정되므로 `후속양산 공급계약`이 여기로 새지 않는다.
    ("SUPPLY", "물품구매·납품", "Supply", r"물품\s*구매|구매\s*계약|납품|공급|판매\s*계약|"
     r"실행계약|조달", 5),
]

# ── 부품 계층 ───────────────────────────────────────────────
# 대분류 10(스펙 §분류 '부품 계층'을 그대로 옮긴다).
PART_GROUPS = [
    ("PROP", "추진", "Propulsion"), ("GUN", "화력", "Armament"), ("ARMOR", "방호", "Protection"),
    ("GUID", "유도", "Guidance"), ("ELEC", "전자", "Electronics"), ("OPT", "광학", "Optronics"),
    ("AERO", "항공구조물", "Airframe"), ("SHIPEQ", "함정장비", "Naval equipment"),
    ("MAT", "소재", "Materials"), ("SVC", "시험·정비", "Test & MRO"),
    ("UNCL", "미분류", "Unclassified"),
]

# (id, ko, en, prio, ctx, kw, neg, regions)
#  prio 높을수록 먼저. ctx=True 는 방산 문맥(방산·군용·함정·전차…)이 함께 있어야 채택한다 —
#  `변속기`·`단조품`·`케이블`처럼 자동차·일반기계와 겹치는 낱말.
PART_CATS = [
    ("PROP.ENGINE", "엔진·가스터빈", "Engines", 70, True,
     ["항공엔진", "항공기엔진", "가스터빈", "디젤엔진", "추진기관", "엔진부품", "터보샤프트",
      "터보팬", "보조동력장치", "APU"], ["선박용엔진"], ["TANK_HULL", "JET_ENGINE", "SHIP_HULL"]),
    ("PROP.TRANS", "변속기·동력전달", "Transmission", 65, True,
     ["변속기", "동력전달", "감속기", "종감속", "구동장치", "트랜스미션", "파워팩"], [],
     ["TANK_HULL"]),
    ("PROP.SUSP", "현가·궤도", "Suspension & tracks", 65, True,
     ["현가장치", "궤도", "무한궤도", "로드휠", "토션바", "서스펜션모듈", "차축"], [], ["TANK_TRACK"]),
    ("PROP.ROCKET", "추진기관(로켓)", "Rocket motors", 70, False,
     ["고체추진", "로켓모터", "추진제", "로켓연소기", "가스발생기", "추력"], [], ["MSL_MOTOR"]),
    ("GUN.BARREL", "포신·포열", "Barrels", 80, False,
     ["포신", "포열", "총열", "약실", "강선"], [], ["TANK_TURRET", "SHIP_GUN"]),
    ("GUN.TURRET", "포탑·구동", "Turrets", 75, True,
     ["포탑", "포탑구동", "선회장치", "고저장치", "자동장전", "장전장치"], [], ["TANK_TURRET"]),
    ("GUN.FCS", "사격통제", "Fire control", 75, False,
     ["사격통제", "사격지휘", "FCS", "조준경", "탄도계산"], [], ["TANK_TURRET", "SHIP_CIC"]),
    ("GUN.SMALL", "총포·탄약", "Small arms & ammo", 70, False,
     ["소총", "기관총", "권총", "총포", "탄약", "포탄", "유탄", "신관", "장약", "뇌관", "탄두"],
     [], ["TANK_TURRET", "SHIP_GUN"]),
    ("ARMOR.PLATE", "장갑·방탄", "Armour", 75, False,
     ["방탄", "장갑판", "복합장갑", "방탄복", "방탄헬멧", "방검", "K-SAP", "반응장갑"], [],
     ["TANK_HULL", "TANK_TURRET"]),
    ("ARMOR.APS", "능동방호·연막", "APS & smoke", 70, False,
     ["능동방호", "APS", "연막", "레이저경고", "미사일경고", "생존장비", "위장망"], [],
     ["TANK_TURRET", "JET_EW"]),
    ("GUID.SEEKER", "탐색기", "Seekers", 85, False,
     ["탐색기", "시커", "seeker", "종말유도", "호밍"], [], ["MSL_SEEKER"]),
    ("GUID.ACT", "구동장치·조종날개", "Actuators & fins", 75, True,
     ["구동장치", "조종날개", "액추에이터", "날개구동", "조종장치"], [], ["MSL_FIN"]),
    ("GUID.FUZE", "신관·안전장전", "Fuzes", 80, False,
     ["신관", "안전장전", "기폭", "근접신관"], [], ["MSL_WARHEAD"]),
    ("GUID.INS", "관성항법·유도조종", "INS & guidance", 80, False,
     ["관성항법", "INS", "IMU", "자이로", "유도조종", "항법장치", "GPS수신"], [],
     ["MSL_BODY", "JET_AVIONICS"]),
    ("ELEC.RADAR", "레이다·안테나", "Radar & antenna", 80, False,
     ["레이다", "레이더", "안테나", "TRM", "송수신모듈", "AESA", "위상배열", "도파관"],
     ["레이더디텍터"], ["SHIP_RADAR", "JET_RADAR"]),
    ("ELEC.EW", "전자전·피아식별", "EW & IFF", 80, False,
     ["전자전", "피아식별", "IFF", "ESM", "ECM", "재밍", "전파방해", "방향탐지"], [],
     ["JET_EW", "SHIP_MAST"]),
    ("ELEC.COMM", "통신·암호", "Comms & crypto", 70, True,
     ["무전기", "위성통신", "데이터링크", "암호장비", "통신단말", "전술통신", "중계기"], [],
     ["SHIP_MAST", "JET_AVIONICS"]),
    ("ELEC.AVION", "항전·임무컴퓨터", "Avionics", 75, True,
     ["항공전자", "항전", "임무컴퓨터", "비행제어", "전시기", "싱글보드컴퓨터", "SBC",
      "임무장비", "전장품"], [], ["JET_AVIONICS"]),
    ("ELEC.POWER", "전원·배전", "Power", 60, True,
     ["전원공급", "배전반", "전원장치", "축전지", "이차전지", "연료전지", "발전기", "전력변환"],
     [], ["SHIP_HULL", "TANK_HULL"]),
    ("OPT.EOIR", "EO/IR·열영상", "EO/IR", 80, False,
     ["열영상", "적외선영상", "EO/IR", "전자광학", "적외선센서", "열상감시", "TOD", "적외선검출"],
     [], ["TANK_TURRET", "JET_EOTS", "SHIP_EOTS"]),
    ("OPT.SIGHT", "조준경·야시", "Sights & night vision", 75, False,
     ["조준경", "야시", "야간투시", "잠망경", "관측경", "레이저거리측정"], [], ["TANK_TURRET"]),
    ("AERO.STRUCT", "기체구조물", "Airframe structures", 70, False,
     ["기체구조", "동체", "날개구조", "주익", "미익", "파일런", "기체부품", "항공구조물",
      "항공가공품", "조립품"], [], ["JET_FUSELAGE", "JET_WING"]),
    ("AERO.GEAR", "착륙장치·유압", "Landing gear & hydraulics", 70, True,
     ["착륙장치", "랜딩기어", "유압시스템", "작동기"], [], ["JET_GEAR"]),
    ("SHIPEQ.CMS", "전투체계·소나", "Combat system & sonar", 80, False,
     ["전투체계", "소나", "음탐", "전투지휘체계", "함정전투", "수중음향"], [], ["SHIP_CIC"]),
    ("SHIPEQ.PROP", "함정 추진·발전", "Naval propulsion", 70, True,
     ["함정용엔진", "추진전동기", "감속기어", "축계", "프로펠러", "함정용발전"], [], ["SHIP_HULL"]),
    ("SHIPEQ.AUX", "함정 의장·보조기기", "Naval auxiliaries", 60, True,
     ["배전반", "조명등", "밸브", "펌프", "공조", "소화설비", "탈염", "청수"], [], ["SHIP_HULL"]),
    ("MAT.METAL", "특수강·비철", "Special metals", 60, True,
     ["특수강", "티타늄", "탄소강", "단조품", "주조품", "알루미늄합금", "동합금", "소전",
      "신동품", "봉강"], [], ["TANK_HULL", "MSL_BODY"]),
    ("MAT.COMP", "복합소재", "Composites", 65, True,
     ["복합소재", "복합재", "탄소섬유", "유리섬유", "프리프레그", "아라미드"], [],
     ["JET_WING", "TANK_TURRET"]),
    ("MAT.EXPL", "화약·추진제", "Explosives", 80, False,
     ["화약", "화공품", "추진화약", "폭약", "기폭약", "질산", "니트로"], [], ["MSL_WARHEAD"]),
    ("SVC.MRO", "정비·창정비", "MRO", 70, False,
     ["창정비", "정비용역", "수리부속", "오버홀", "MRO", "PBL"], [], ["SHIP_HULL", "JET_FUSELAGE"]),
    ("SVC.SIM", "시뮬레이터·훈련체계", "Simulators", 75, False,
     ["시뮬레이터", "훈련체계", "모의비행", "전술훈련", "IETM", "교보재", "종합군수지원"], [],
     ["JET_AVIONICS"]),
]

# ── SVG 실루엣 영역 ─────────────────────────────────────────
# 외부 이미지 없이 단순 기하 도형으로 직접 그린다(스펙 §parts.html).
# viewBox 는 4종 모두 0 0 400 200. points 는 폴리곤 좌표.
SILHOUETTES = [
    ("TANK", "전차", "Main battle tank", "GROUND"),
    ("JET", "전투기", "Fighter aircraft", "AIR"),
    ("SHIP", "함정", "Naval vessel", "NAVAL"),
    ("MSL", "유도탄", "Guided missile", "MISSILE"),
]

REGIONS = [
    # (id, 실루엣, 이름, 폴리곤 좌표, 라벨 위치)
    ("TANK_TURRET", "TANK", "포탑·주포",
     "150,70 300,70 305,95 285,105 150,105 140,88", (225, 88)),
    ("TANK_HULL", "TANK", "차체·동력장치",
     "70,105 340,105 350,135 60,135", (205, 122)),
    ("TANK_TRACK", "TANK", "현가·궤도",
     "58,137 352,137 352,165 58,165", (205, 153)),
    ("JET_RADAR", "JET", "기수 레이다",
     "20,95 70,82 70,112 20,105", (45, 98)),
    ("JET_AVIONICS", "JET", "항전·조종석",
     "72,80 130,78 132,112 72,112", (102, 96)),
    ("JET_FUSELAGE", "JET", "동체",
     "134,78 300,84 300,112 134,112", (215, 96)),
    ("JET_WING", "JET", "주익·미익",
     "160,112 250,112 215,168 145,168", (195, 140)),
    ("JET_EOTS", "JET", "EO/IR 조준장치",
     "110,113 150,113 150,130 110,130", (130, 124)),
    ("JET_ENGINE", "JET", "엔진·노즐",
     "300,84 370,90 370,106 300,112", (335, 99)),
    ("JET_EW", "JET", "전자전·기만",
     "250,60 320,60 320,80 250,84", (285, 73)),
    ("JET_GEAR", "JET", "착륙장치",
     "150,113 190,113 190,150 150,150", (170, 134)),
    ("SHIP_RADAR", "SHIP", "탐색·추적 레이다",
     "180,28 215,28 215,60 180,60", (198, 46)),
    ("SHIP_MAST", "SHIP", "통합마스트·전자전",
     "196,10 206,10 212,28 190,28", (201, 22)),
    ("SHIP_EOTS", "SHIP", "EO/IR 추적",
     "216,40 240,40 240,60 216,60", (228, 52)),
    ("SHIP_GUN", "SHIP", "함포·발사대",
     "90,78 140,78 140,100 90,100", (115, 91)),
    ("SHIP_CIC", "SHIP", "전투체계·소나",
     "142,62 250,62 250,100 142,100", (196, 83)),
    ("SHIP_HULL", "SHIP", "선체·추진",
     "60,102 350,102 320,150 90,150", (205, 128)),
    ("MSL_SEEKER", "MSL", "탐색기",
     "30,88 90,88 90,112 30,112", (60, 102)),
    ("MSL_WARHEAD", "MSL", "탄두·신관",
     "92,86 160,86 160,114 92,114", (126, 102)),
    ("MSL_BODY", "MSL", "유도조종부",
     "162,86 250,86 250,114 162,114", (206, 102)),
    ("MSL_MOTOR", "MSL", "추진기관",
     "252,86 350,86 350,114 252,114", (301, 102)),
    ("MSL_FIN", "MSL", "조종날개·구동",
     "300,60 360,60 360,86 300,86", (330, 74)),
]


def build_domains():
    out = []
    for did, ko, en, slot, strong, general in DOMAINS:
        out.append({"id": did, "ko": ko, "en": en, "slot": slot,
                    "keywords": ([{"kw": k, "prio": 90} for k in strong]
                                 + [{"kw": k, "prio": 50} for k in general])})
    return {"n": len(out), "domains": out}


def build_types():
    return {"n": len(CONTRACT_TYPES),
            "types": [{"id": i, "ko": ko, "en": en, "pattern": p, "slot": s}
                      for i, ko, en, p, s in CONTRACT_TYPES]}


def build_parts():
    groups = [{"id": g, "ko": ko, "en": en} for g, ko, en in PART_GROUPS]
    cats = [{"id": cid, "group": cid.split(".")[0], "ko": ko, "en": en, "prio": prio,
             "ctx": ctx, "kw": kw, "neg": neg, "regions": regs}
            for cid, ko, en, prio, ctx, kw, neg, regs in PART_CATS]
    return {"groups": groups, "cats": cats}


def build_svg():
    sil = [{"id": s, "ko": ko, "en": en, "domain": dom} for s, ko, en, dom in SILHOUETTES]
    regs = []
    for rid, s, ko, pts, label in REGIONS:
        regs.append({"id": rid, "silhouette": s, "ko": ko, "points": pts,
                     "label": {"x": label[0], "y": label[1]},
                     "cats": sorted(c[0] for c in PART_CATS if rid in c[7])})
    return {"viewBox": "0 0 400 200", "silhouettes": sil, "regions": regs}


def check(parts, svg):
    """교차 참조 검증 — 소분류의 region 이 SVG 에 있고, 모든 영역이 최소 1개 소분류를 갖는다."""
    rid = {r["id"] for r in svg["regions"]}
    sid = {s["id"] for s in svg["silhouettes"]}
    errs = []
    for c in parts["cats"]:
        for r in c["regions"]:
            if r not in rid:
                errs.append("소분류 %s 의 영역 %s 가 SVG 에 없다" % (c["id"], r))
        if c["group"] not in {g["id"] for g in parts["groups"]}:
            errs.append("소분류 %s 의 대분류 %s 가 없다" % (c["id"], c["group"]))
    for r in svg["regions"]:
        if r["silhouette"] not in sid:
            errs.append("영역 %s 의 실루엣 %s 가 없다" % (r["id"], r["silhouette"]))
        if not r["cats"]:
            errs.append("영역 %s 에 연결된 소분류가 없다" % r["id"])
    ids = [c["id"] for c in parts["cats"]]
    if len(ids) != len(set(ids)):
        errs.append("소분류 id 중복")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    dom, typ, parts, svg = build_domains(), build_types(), build_parts(), build_svg()
    errs = check(parts, svg)
    if errs:
        for e in errs:
            sys.stderr.write("[err] %s\n" % e)
        raise SystemExit("교차 참조 검증 실패 %d건" % len(errs))
    if a.write:
        write_asset("domains.json", dom)
        write_asset("contract_types.json", typ)
        write_asset("parts_taxonomy.json", parts)
        write_asset("svg_regions.json", svg)
    print("계통 %d · 계약유형 %d · 부품 대분류 %d/소분류 %d · 실루엣 %d/영역 %d"
          % (len(dom["domains"]), len(typ["types"]), len(parts["groups"]), len(parts["cats"]),
             len(svg["silhouettes"]), len(svg["regions"])))


if __name__ == "__main__":
    sys.exit(main())
