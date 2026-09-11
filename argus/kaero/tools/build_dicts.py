#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_dicts — 우주항공 탭의 정적 사전을 코드에서 생성한다(손으로 JSON을 쓰지 않는다).

  assets/domains.json         영역 5 + 기타 — 화면 메타(이름·색·설명)와 판정 근거 문구
  assets/natures.json         계약 성격(RSP·PBL·LTA·개발·정비·양산) — 이 산업의 이익 성격 축
  assets/tiers.json           고객 계층(OEM 직납 · Tier-1 하도 · 국내 체계업체 · 정부/기관)
  assets/parts_taxonomy.json  부품 계층(대분류 6 · 소분류 21) — 제품·계약 문구 → 부품
  assets/svg_regions.json     실루엣 4종(여객기·터보팬 엔진·위성·발사체)의 영역 폴리곤

**영역·성격 판정 자체는 여기서 만들지 않는다.** 그 규칙은 `kaero_reports.domain_of`·
`nature_of` 한 곳에만 있고(원문 문구에서 읽는다), 이 파일은 그 결과를 **화면에 어떻게
보일지**와 부품 분류(제품 문구 → 부품)를 만든다. 두 벌로 갈라지지 않게 라벨은
`kaero_lib.DOMAINS`·`kaero_reports.NATURES`·`TIERS` 에서 가져온다.

한 곳에서 만드는 이유는 **교차 참조를 생성 시점에 검증**하기 위해서다 —
소분류의 `regions` 가 실제 SVG 영역에 있는지, 영역의 `cats` 가 실제 소분류인지(fail-closed).

    python3 build_dicts.py --write
"""
import argparse
import re
import sys

from kaero_lib import DOMAINS, write_asset
from kaero_reports import NATURES, TIERS

# ── 영역 판정에 쓰인 문구(화면 설명용) ───────────────────────
# 실제 판정은 kaero_reports 의 정규식이다. 여기 적는 것은 "무엇을 보고 갈랐는가"를
# 커버리지 화면에 그대로 보이기 위한 사람 말이다.
DOMAIN_BASIS = {
    "struct": "동체·기체·주익·날개·벌크헤드·스트링거·나셀·파일런·Section/Fuselage/Bulkhead/Deck",
    "engine": "엔진·터빈·RSP·GTF·GEnx·LEAP·HPT/LPT·디스크·블레이드·APU·추진기관·연소기",
    "mro": "창정비·정비·MRO·오버홀·PBL·성과기반군수",
    "defav": "방산·군용·해군/공군/육군·전투기·훈련기·헬기·KF-X·T-50·수리온·완제기",
    "space": "발사체·로켓·누리호·위성·탑재체·지상국·우주·궤도",
    "other": "위 어느 문구도 원문에 없음 — 추정하지 않고 '기타·미상'으로 둔다",
}

# ── 부품 계층 ───────────────────────────────────────────────
# (group_id, ko, en)
GROUPS = [
    ("STRUCT", "기체구조", "Airframe structures"),
    ("ENGINE", "엔진", "Propulsion"),
    ("AVION", "항공전자·장비", "Avionics & systems"),
    ("SPACE", "우주", "Space systems"),
    ("MAT", "소재·공정", "Materials & processes"),
    ("SVC", "정비·시험", "MRO & test"),
]

# (cat_id, group, ko, 키워드, [실루엣 영역 id])
# 키워드는 **제품·계약 문구에서 실제로 본 말**만 넣는다. 짧은 말은 넣지 않는다
# (`케이스`는 반도체 케이스와 겹치고 `디스크`는 저장장치와 겹친다 — 앞말과 붙은 꼴만).
CATS = [
    ("STRUCT.FUSELAGE", "STRUCT", "동체·섹션", ["동체", "Fuselage", "Section48", "Section 48",
                                            "벌크헤드", "Bulkhead", "스트링거", "Stringer",
                                            "프레임", "판넬", "패널", "스킨"],
     ["AIRLINER_FWD", "AIRLINER_AFT", "AIRLINER_NOSE"]),
    ("STRUCT.WING", "STRUCT", "주익·미익", ["주익", "날개구조", "날개 구조", "Wing", "Spar",
                                        "U/L Deck", "미익", "수평미익", "수직미익", "Rib"],
     ["AIRLINER_WING_U", "AIRLINER_WING_L", "AIRLINER_TAIL"]),
    ("STRUCT.NACELLE", "STRUCT", "나셀·파일런", ["나셀", "Nacelle", "파일런", "Pylon", "카울"],
     ["AIRLINER_ENG_U", "AIRLINER_ENG_L"]),
    ("STRUCT.GEAR", "STRUCT", "착륙장치·도어", ["착륙장치", "랜딩기어", "Landing Gear",
                                          "도어", "Door", "액추에이터"],
     ["AIRLINER_GEAR"]),
    ("ENGINE.FAN", "ENGINE", "팬·압축기", ["팬", "Fan", "압축기", "Compressor", "블리스크"],
     ["ENG_FAN", "ENG_COMP"]),
    ("ENGINE.TURBINE", "ENGINE", "터빈·디스크", ["터빈", "Turbine", "HPT", "LPT",
                                            "터빈디스크", "터빈 디스크", "블레이드", "Blade",
                                            "노즐가이드"],
     ["ENG_TURB"]),
    ("ENGINE.COMBUST", "ENGINE", "연소기·노즐", ["연소기", "Combustor", "노즐", "Nozzle",
                                            "라이너"],
     ["ENG_COMB", "ENG_NOZZ"]),
    ("ENGINE.CASE", "ENGINE", "케이싱·구조부", ["엔진케이스", "케이싱", "Casing", "하우징",
                                          "Housing", "디퓨저"],
     ["ENG_CASE"]),
    ("ENGINE.ACC", "ENGINE", "기어박스·보기류", ["기어박스", "Gearbox", "APU", "보기류",
                                           "액세서리", "연료펌프", "오일펌프"],
     ["ENG_ACC"]),
    ("AVION.NAV", "AVION", "항법·관성", ["관성항법", "INS", "자이로", "가속도계", "항법장치",
                                     "GPS 수신", "Gyro"],
     ["AIRLINER_NOSE"]),
    ("AVION.COMM", "AVION", "통신·안테나", ["항공통신", "데이터링크", "레이돔", "Radome",
                                       "항공용 안테나", "위성통신 안테나"],
     ["AIRLINER_NOSE", "SAT_ANT"]),
    ("AVION.FCS", "AVION", "비행제어·구동", ["비행제어", "Flight Control", "FBW", "구동장치",
                                       "플랩", "액추에이션"],
     ["AIRLINER_WING_U", "AIRLINER_WING_L"]),
    ("AVION.PWR", "AVION", "전원·배전", ["항공기 전원", "배전", "전원공급장치", "전력변환",
                                    "발전기", "축전지"],
     ["AIRLINER_FWD"]),
    ("AVION.SENSOR", "AVION", "센서·광학", ["적외선 센서", "영상센서", "초점면", "FPU",
                                       "전자광학", "EO/IR", "짐벌"],
     ["SAT_PAY", "AIRLINER_NOSE"]),
    ("SPACE.LAUNCH", "SPACE", "발사체·추진기관", ["발사체", "로켓", "누리호", "추진기관",
                                            "연소기", "터보펌프", "고체추진", "액체추진",
                                            "가스발생기"],
     ["LV_FIRST", "LV_ENGINE", "LV_UPPER"]),
    ("SPACE.BUS", "SPACE", "위성 본체·전장품", ["위성본체", "위성 본체", "위성 시스템",
                                          "인공위성", "위성전장", "전력조절", "태양전지판"],
     ["SAT_BUS", "SAT_PANEL_L", "SAT_PANEL_R"]),
    ("SPACE.PAYLOAD", "SPACE", "탑재체", ["탑재체", "Payload", "SAR", "광학탑재",
                                      "영상레이다", "관측카메라"],
     ["SAT_PAY"]),
    ("SPACE.GROUND", "SPACE", "지상국·영상", ["지상국", "위성운용국", "관제", "위성영상",
                                        "수신국", "안테나 시스템"],
     ["SAT_ANT"]),
    ("MAT.ALLOY", "MAT", "특수합금·티타늄", ["티타늄", "Titanium", "인코넬", "초내열",
                                       "니켈합금", "특수강", "단조품", "정밀단조"],
     ["ENG_TURB", "AIRLINER_FWD"]),
    ("MAT.COMP", "MAT", "복합재", ["복합재", "탄소섬유", "프리프레그", "CFRP", "샌드위치 패널"],
     ["AIRLINER_WING_U", "AIRLINER_WING_L", "LV_FAIRING"]),
    ("MAT.SURF", "MAT", "정밀가공·표면처리", ["정밀가공", "5축가공", "화학처리", "아노다이징",
                                       "熱처리", "열처리", "표면처리", "도장", "Nadcap"],
     ["AIRLINER_AFT"]),
    ("SVC.MRO", "SVC", "정비·창정비", ["창정비", "MRO", "오버홀", "기체정비", "엔진정비",
                                  "PBL", "후속지원"],
     ["ENG_CASE", "AIRLINER_AFT"]),
    ("SVC.TEST", "SVC", "시험·인증", ["환경시험", "진동시험", "비행시험", "감항", "형식증명",
                                  "AS9100", "인증시험"],
     ["LV_UPPER"]),
]

# ── 실루엣과 영역 ──────────────────────────────────────────
# viewBox 400×200. 기술 도면이 아니라 **누를 수 있는 그림**이다 — 영역은 굵게 잡는다.
SILHOUETTES = [
    ("AIRLINER", "민항 여객기(평면도)", "Airliner (plan view)", "struct"),
    ("ENG", "터보팬 엔진(단면)", "Turbofan (section)", "engine"),
    ("SAT", "인공위성", "Satellite", "space"),
    ("LV", "우주 발사체", "Launch vehicle", "space"),
]

REGIONS = [
    # 여객기 — 동체 중심선 y=100
    ("AIRLINER_NOSE", "AIRLINER", "기수·레이돔", "40,100 72,84 96,84 96,116 72,116", (68, 100)),
    ("AIRLINER_FWD", "AIRLINER", "전방동체", "96,84 172,84 172,116 96,116", (134, 100)),
    ("AIRLINER_WING_U", "AIRLINER", "주익(상)", "162,84 196,24 228,24 210,84", (196, 56)),
    ("AIRLINER_WING_L", "AIRLINER", "주익(하)", "162,116 196,176 228,176 210,116", (196, 144)),
    ("AIRLINER_ENG_U", "AIRLINER", "엔진·나셀(상)", "182,50 208,50 208,72 182,72", (195, 61)),
    ("AIRLINER_ENG_L", "AIRLINER", "엔진·나셀(하)", "182,128 208,128 208,150 182,150", (195, 139)),
    ("AIRLINER_GEAR", "AIRLINER", "착륙장치", "150,116 168,116 168,132 150,132", (159, 124)),
    ("AIRLINER_AFT", "AIRLINER", "후방동체", "172,86 300,90 300,110 172,114", (236, 100)),
    ("AIRLINER_TAIL", "AIRLINER", "미익(수평·수직)",
     "300,90 322,58 348,58 334,92 334,108 348,142 322,142 300,110", (324, 100)),
    # 터보팬 엔진 — 왼쪽이 흡입, 오른쪽이 배기
    ("ENG_FAN", "ENG", "팬", "40,52 92,44 92,156 40,148", (66, 100)),
    ("ENG_COMP", "ENG", "압축기", "92,66 172,78 172,122 92,134", (132, 100)),
    ("ENG_COMB", "ENG", "연소기", "172,76 216,76 216,124 172,124", (194, 100)),
    ("ENG_TURB", "ENG", "터빈", "216,72 282,68 282,132 216,128", (249, 100)),
    ("ENG_NOZZ", "ENG", "배기노즐", "282,68 352,86 352,114 282,132", (317, 100)),
    ("ENG_CASE", "ENG", "케이싱", "40,44 92,44 92,52 40,52", (66, 40)),
    ("ENG_ACC", "ENG", "보기류·기어박스", "130,134 210,134 210,160 130,160", (170, 147)),
    # 위성
    ("SAT_BUS", "SAT", "본체(버스)", "162,72 238,72 238,128 162,128", (200, 100)),
    ("SAT_PANEL_L", "SAT", "태양전지판(좌)", "40,82 160,82 160,118 40,118", (100, 100)),
    ("SAT_PANEL_R", "SAT", "태양전지판(우)", "240,82 360,82 360,118 240,118", (300, 100)),
    ("SAT_PAY", "SAT", "탑재체", "178,34 222,34 234,72 166,72", (200, 54)),
    ("SAT_ANT", "SAT", "안테나·지상국", "186,128 214,128 222,164 178,164", (200, 146)),
    # 발사체 — 왼쪽이 페어링, 오른쪽이 1단
    ("LV_FAIRING", "LV", "페어링·위성", "28,100 76,70 108,70 108,130 76,130", (72, 100)),
    ("LV_UPPER", "LV", "상단(2단)", "108,72 198,72 198,128 108,128", (153, 100)),
    ("LV_FIRST", "LV", "1단", "198,68 318,68 318,132 198,132", (258, 100)),
    ("LV_ENGINE", "LV", "추진기관", "318,72 352,48 372,60 372,140 352,152 318,128", (344, 100)),
]


def build():
    doms = [{"id": d["id"], "ko": d["label"], "slot": d["slot"], "hex": d["hex"],
             "desc": d["desc"], "basis": DOMAIN_BASIS.get(d["id"], "")} for d in DOMAINS]
    missing = [d["id"] for d in doms if not d["basis"]]
    if missing:
        raise SystemExit("영역 %s 의 판정 근거 문구가 비었다" % missing)

    natures = [{"id": i, "ko": ko, "desc": desc, "slot": n}
               for n, (i, ko, desc) in enumerate(NATURES, 1)]
    tiers = [{"id": t, "ko": ko, "names": list(names)} for t, ko, names in TIERS]
    tiers.append({"id": "prime", "ko": "국내 체계업체", "names": []})
    tiers.append({"id": "gov", "ko": "정부·기관", "names": []})

    groups = [{"id": g, "ko": ko, "en": en} for g, ko, en in GROUPS]
    gids = {g["id"] for g in groups}
    rids = {r[0] for r in REGIONS}
    cats = []
    for cid, grp, ko, kws, regs in CATS:
        if grp not in gids:
            raise SystemExit("부품 소분류 %s 의 대분류 %s 가 없다" % (cid, grp))
        bad = [r for r in regs if r not in rids]
        if bad:
            raise SystemExit("부품 소분류 %s 가 없는 영역 %s 를 가리킨다" % (cid, bad))
        if not kws:
            raise SystemExit("부품 소분류 %s 에 키워드가 없다" % cid)
        cats.append({"id": cid, "group": grp, "ko": ko, "regions": regs,
                     "keywords": sorted(set(kws), key=lambda k: (-len(k), k))})
    cids = {c["id"] for c in cats}

    sil = [{"id": s, "ko": ko, "en": en, "domain": dom} for s, ko, en, dom in SILHOUETTES]
    sids = {s["id"] for s in sil}
    regions = []
    for rid, sl, ko, pts, label in REGIONS:
        if sl not in sids:
            raise SystemExit("영역 %s 의 실루엣 %s 가 없다" % (rid, sl))
        if not re.match(r"^(\d+,\d+ )+\d+,\d+$", pts):
            raise SystemExit("영역 %s 의 폴리곤 좌표가 이상하다: %r" % (rid, pts))
        mine = sorted(c["id"] for c in cats if rid in c["regions"])
        if not mine:
            raise SystemExit("영역 %s 를 가리키는 부품 소분류가 없다(누르면 빈 화면이 된다)" % rid)
        regions.append({"id": rid, "silhouette": sl, "ko": ko, "points": pts,
                        "label": {"x": label[0], "y": label[1]}, "cats": mine})
    orphan = sorted(cids - {c for r in regions for c in r["cats"]})
    if orphan:
        raise SystemExit("실루엣에 걸리지 않는 부품 소분류: %s" % orphan)
    return doms, natures, tiers, groups, cats, sil, regions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    doms, natures, tiers, groups, cats, sil, regions = build()
    print("영역 %d · 계약성격 %d · 고객계층 %d · 부품 %d/%d · 실루엣 %d/영역 %d"
          % (len(doms), len(natures), len(tiers), len(groups), len(cats), len(sil), len(regions)))
    if a.write:
        write_asset("domains.json", {"n": len(doms), "domains": doms})
        write_asset("natures.json", {"n": len(natures), "natures": natures})
        write_asset("tiers.json", {"n": len(tiers), "tiers": tiers})
        write_asset("parts_taxonomy.json", {"groups": groups, "cats": cats})
        write_asset("svg_regions.json", {"viewBox": "0 0 400 200",
                                         "silhouettes": sil, "regions": regions})
        print("assets/{domains,natures,tiers,parts_taxonomy,svg_regions}.json 갱신")


if __name__ == "__main__":
    sys.exit(main())
