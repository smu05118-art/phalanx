#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_dicts — 원전·발전기자재 탭의 정적 사전을 코드에서 생성한다(손으로 JSON을 쓰지 않는다).

  assets/domains.json         발전원(domain) — 계약명·사업명 → 원자력/화력/신재생/송변전/기타
  assets/contract_types.json  공급 계층(tier) — 주기기·보조기기·계측제어·설계·정비O&M·검사·해체·기자재
  assets/parts_taxonomy.json  부품 계층(대분류·소분류) — 제품/사업명 문구 → 부품
  assets/svg_regions.json     발전소 단면 2종(원전·화력/복합)의 영역 폴리곤

한 곳에서 만드는 이유는 **교차 참조를 생성 시점에 검증**하기 위해서다(fail-closed) —
소분류의 `regions` 가 실제 SVG 영역에 있는지, 영역의 `cats` 가 실재 소분류인지.

발전원 매칭은 길이가 아니라 **우선순위**로 한다. `신한울 3,4호기 종합설계용역`을 길이로 고르면
`설계`(공급계층)가 끼어들 여지가 있지만, 이 계약이 붙은 **발전원**은 원자력(신한울)이다.
호기·사업 이름(신한울·두코바니·삼척화력)에 가장 높은 우선순위를 준다.

    python3 build_dicts.py --write
"""
import argparse
import sys

from knuke_lib import write_asset

# ── 발전원(domain) ─────────────────────────────────────────
# (id, ko, en, slot, 호기·사업이름[prio 90], 일반어휘[prio 50])
DOMAINS = [
    ("NUKE", "원자력", "Nuclear", 1,
     ["신한울", "신고리", "새울", "한빛", "한울", "월성", "고리", "울진", "영광",
      "두코바니", "Dukovany", "테멜린", "Temelin", "바라카", "Barakah", "체코원전",
      "APR1400", "APR-1400", "APR+", "SMR", "i-SMR", "혁신형소형모듈원자로",
      "웨스팅하우스", "Westinghouse", "루마니아", "체르나보다", "Cernavoda", "CTRF"],
     ["원자력", "원전", "원자로", "핵연료", "방사선", "사용후핵연료", "계속운전",
      "방사성폐기물", "원자력발전", "격납", "핵증기공급", "NSSS", "가동원전", "해체"]),
    ("THERMAL", "화력", "Thermal", 2,
     ["삼척화력", "신서천", "강릉안인", "고성하이", "당진", "태안", "보령", "하동",
      "여수화력", "영흥", "신인천", "안동복합", "통영복합"],
     ["화력", "석탄", "무연탄", "유연탄", "복합화력", "복합발전", "LNG복합", "가스복합",
      "석탄화력", "열병합", "집단에너지", "화력발전", "석탄가스화", "IGCC"]),
    ("RENEW", "신재생", "Renewables", 3,
     ["해상풍력", "새만금", "탐라해상", "서남해", "제주한림", "안마"],
     ["풍력", "태양광", "수소", "연료전지", "신재생", "재생에너지", "그린수소",
      "암모니아", "풍력발전", "조력", "지열", "바이오매스", "ESS", "수전해"]),
    ("GRID", "송변전", "Transmission", 4,
     ["동해안변환소", "북당진"],
     ["송변전", "변전소", "송전", "배전", "변압기", "개폐기", "가스절연", "HVDC",
      "전력계통", "계통연계", "송전선로", "초고압", "수배전"]),
    # 발전기자재사가 같은 양식으로 올리는 **기타 산업설비**(제철·석유화학·담수) — 버리지 않고 갈라 둔다.
    ("IND", "기타 산업설비", "Industrial plant", 5,
     ["사우디", "쿠웨이트", "UAE"],
     ["제철설비", "석유화학", "정유", "담수", "해수담수", "담수화", "환경설비",
      "산업용보일러", "산업설비", "폐열회수", "제강", "소각"]),
]

# ── 공급 계층(tier) ─────────────────────────────────────────
# 스펙 §분류 '공급 계층'을 그대로 옮긴다. 계약명·사업명에서 위에서부터 먼저 맞는 것.
# 주기기가 정비보다 먼저여야 한다(`원자로설비 정비`는 주기기 계약이 아니라 정비다 →
# 하지만 `원자로` 낱말이 강하므로 OM 을 MAIN 보다 **뒤**가 아니라, '정비/공사'가 붙으면 OM 이
# 이기도록 OM·검사·해체 계열을 주기기보다 **앞**에 둔다).
CONTRACT_TYPES = [
    ("DECOM", "해체·방폐물", "Decommissioning & waste", 8,
     r"해체|제염|방사성폐기물|방폐물|폐기물\s*처리|사용후핵연료\s*저장|중저준위", None),
    ("INSP", "검사·방사선관리", "Inspection & RP", 8,
     r"방사선\s*안전관리|방사선관리|비파괴검사|가동중검사|건전성평가|환경방사능|"
     r"안전성\s*평가|검사\s*용역|계측검교정|방사능\s*측정", None),
    ("OM", "정비·O&M", "Maintenance / O&M", 6,
     r"경상정비|예방정비|계획예방정비|정비공사|정비\s*용역|성능\s*개선|개보수|O\s*&\s*M|"
     r"유지보수|오버홀|점검|정비\b|설비진단|화력정비|발전설비정비", None),
    ("ENG", "설계·엔지니어링", "Design & engineering", 4,
     r"종합설계|기본설계|상세설계|설계\s*용역|엔지니어링|기술\s*용역|감리|사업관리|"
     r"설계\b|타당성|기술지원|인허가", None),
    ("INC", "계측제어", "I&C", 7,
     r"계측제어|계측기|제어시스템|I\s*&\s*C|MMIS|RSP|원전계측|디지털제어|"
     r"감시제어|안전등급\s*제어|원자로보호계통", None),
    ("MAIN", "주기기", "NSSS / main equipment", 1,
     r"원자로설비|원자로\b|증기발생기|가압기|냉각재펌프|주기기|핵증기공급|NSSS|"
     r"증기터빈|가스터빈|터빈발전기|터빈\b|발전기\b|주단조|원자로냉각재", None),
    ("AUX", "보조기기", "BOP / auxiliaries", 5,
     r"열교환기|압력용기|저장탱크|복수기|급수가열기|탈기기|보일러|HRSG|배열회수보일러|"
     r"펌프|밸브|배관|탱크|저장조|팬\b|블로워|집진|탈황|탈질|스크러버", None),
    ("SUPPLY", "기자재 공급", "Equipment supply", 0,
     r"기자재|자재|부품|소재|공급계약|납품|제작\s*공급|제작\s*설치|구매", None),
]

# ── 부품 계층(공급 계층 부품) ──────────────────────────────
PART_GROUPS = [
    ("NSSS", "원자로계통", "Reactor systems"),
    ("TG", "터빈·발전기", "Turbine & generator"),
    ("BOP", "보조기기", "Balance of plant"),
    ("IANDC", "계측제어", "I&C"),
    ("ELEC", "전기설비", "Electrical"),
    ("ENG", "설계·엔지니어링", "Engineering"),
    ("OM", "정비·검사", "O&M & inspection"),
    ("MAT", "소재·주단조", "Materials & forgings"),
    ("UNCL", "미분류", "Unclassified"),
]

# (id, ko, en, prio, ctx, kw, neg, regions)
#  ctx=True 는 발전 문맥(원전·발전·보일러·터빈…)이 함께 있어야 채택 — `펌프`·`밸브`·`탱크`처럼
#  일반 기계와 겹치는 낱말.
PART_CATS = [
    ("NSSS.RV", "원자로·압력용기", "Reactor vessel", 85, False,
     ["원자로용기", "원자로압력용기", "원자로\b", "압력용기", "핵증기공급", "NSSS", "격납"],
     [], ["REACTOR", "CONTAIN"]),
    ("NSSS.SG", "증기발생기", "Steam generator", 85, False,
     ["증기발생기", "스팀제너레이터", "가압기", "냉각재펌프", "원자로냉각재"],
     [], ["SG", "PZR"]),
    ("NSSS.FUEL", "핵연료·연료취급", "Fuel", 80, False,
     ["핵연료", "연료집합체", "연료취급", "핵연료취급", "원자력연료"], [], ["FUEL"]),
    ("TG.TURBINE", "증기터빈·가스터빈", "Turbines", 75, False,
     ["증기터빈", "가스터빈", "터빈\b", "터어빈", "터빈블레이드", "터빈로터", "블레이드"],
     [], ["TURB", "GT"]),
    ("TG.GEN", "발전기", "Generators", 70, True,
     ["발전기", "터빈발전기", "여자기", "회전자", "고정자"], ["발전기자재"], ["GEN"]),
    ("BOP.HX", "열교환기·복수기", "Heat exchangers", 75, False,
     ["열교환기", "복수기", "급수가열기", "탈기기", "냉각기", "응축기"], [], ["COND"]),
    ("BOP.VESSEL", "압력용기·저장탱크", "Vessels & tanks", 70, True,
     ["압력용기", "저장탱크", "저장조", "탱크", "드럼", "저장설비"], [], ["COND"]),
    ("BOP.BOILER", "보일러·HRSG", "Boilers", 75, False,
     ["보일러", "HRSG", "배열회수보일러", "관류보일러", "온수보일러", "산업용보일러"],
     [], ["BOILER"]),
    ("BOP.PUMP", "펌프·밸브·배관", "Pumps, valves & piping", 60, True,
     ["펌프", "밸브", "배관", "피팅", "배관재", "관로", "송풍기", "블로워"], [], ["PUMP"]),
    ("BOP.ENV", "탈황·탈질·집진", "Emission control", 70, False,
     ["탈황", "탈질", "집진", "스크러버", "전기집진", "환경설비", "SCR"], [], ["STACK"]),
    ("IANDC.MMIS", "계측제어·MMIS", "I&C / MMIS", 80, False,
     ["계측제어", "MMIS", "RSP", "원전계측", "디지털제어", "감시제어", "원자로보호계통",
      "안전등급제어"], [], ["IC"]),
    ("IANDC.INSTR", "계측기·센서", "Instruments & sensors", 75, True,
     ["계측기", "온도센서", "노내계측", "방사선측정", "검출기", "센서", "측정기"],
     [], ["IC"]),
    ("ELEC.SWGR", "변압기·수배전", "Transformers & switchgear", 65, True,
     ["변압기", "배전반", "수배전", "개폐기", "차단기", "전동기", "전력변환", "가스절연"],
     [], ["TRANSF"]),
    ("ELEC.CABLE", "케이블·전선", "Cables", 60, True,
     ["케이블", "전선", "전력케이블", "제어케이블"], [], ["TRANSF"]),
    # 설계·정비·검사는 물리적 위치가 없다 — 영역에 매달지 않고(regions=[]) 부품 대분류 칩으로 진입한다.
    ("ENG.DESIGN", "설계·엔지니어링", "Design", 75, False,
     ["종합설계", "기본설계", "상세설계", "설계용역", "엔지니어링", "감리", "사업관리",
      "원자로설계", "기술용역"], [], []),
    ("OM.MAINT", "정비·O&M", "Maintenance", 70, False,
     ["경상정비", "예방정비", "계획예방정비", "정비공사", "정비용역", "성능개선", "개보수",
      "오버홀", "발전설비정비"], [], []),
    ("OM.INSP", "검사·방사선관리", "Inspection & RP", 75, False,
     ["방사선안전관리", "방사선관리", "비파괴검사", "가동중검사", "건전성평가",
      "환경방사능", "안전성평가"], [], []),
    ("MAT.FORGE", "주·단조·특수강", "Forgings & special steel", 65, True,
     ["주단조", "단조품", "주조품", "주강", "특수강", "합금강", "소전", "봉강", "판재",
      "클래드"], [], ["REACTOR", "TURB"]),
]

# ── SVG 실루엣(발전소 단면) ─────────────────────────────────
# 외부 이미지 없이 단순 기하 도형으로 직접 그린다. viewBox 0 0 400 200.
SILHOUETTES = [
    ("NPP", "원자력발전소", "Nuclear power plant", "NUKE"),
    ("FOSSIL", "화력·복합발전소", "Thermal/CC power plant", "THERMAL"),
]

REGIONS = [
    # (id, 실루엣, 이름, 폴리곤 좌표, 라벨 위치)
    # 원전: 원자로건물(격납·원자로·증기발생기·가압기) → 터빈건물(터빈·발전기·복수기) → 계측제어 → 변전
    ("CONTAIN", "NPP", "격납건물",
     "40,120 40,70 60,45 100,45 120,70 120,120", (80, 132)),
    ("REACTOR", "NPP", "원자로·압력용기",
     "62,110 98,110 98,80 62,80", (80, 97)),
    ("SG", "NPP", "증기발생기",
     "48,78 60,78 60,118 48,118", (54, 100)),
    ("PZR", "NPP", "가압기·냉각재펌프",
     "100,78 112,78 112,118 100,118", (106, 100)),
    ("FUEL", "NPP", "핵연료취급",
     "40,122 120,122 120,140 40,140", (80, 133)),
    ("TURB", "NPP", "증기터빈",
     "150,80 230,80 230,108 150,108", (190, 96)),
    ("GEN", "NPP", "발전기",
     "232,80 290,80 290,108 232,108", (261, 96)),
    ("COND", "NPP", "복수기·급수",
     "150,110 290,110 290,132 150,132", (220, 123)),
    ("IC", "NPP", "계측제어(MMIS)",
     "150,58 230,58 230,78 150,78", (190, 70)),
    ("TRANSF", "NPP", "변압기·송변전",
     "310,90 360,90 360,132 310,132", (335, 113)),
    # 화력·복합: 보일러/HRSG → 가스터빈 → 증기터빈 → 발전기 → 탈황탈질(연돌)
    ("BOILER", "FOSSIL", "보일러·배열회수보일러",
     "40,40 90,40 90,140 40,140", (65, 92)),
    ("GT", "FOSSIL", "가스터빈",
     "110,95 170,95 170,125 110,125", (140, 112)),
    ("STURB", "FOSSIL", "증기터빈",
     "180,95 250,95 250,125 180,125", (215, 112)),
    ("GEN2", "FOSSIL", "발전기",
     "252,95 300,95 300,125 252,125", (276, 112)),
    ("STACK", "FOSSIL", "탈황·탈질·연돌",
     "320,20 350,20 350,140 320,140", (335, 92)),
    ("PUMP", "FOSSIL", "펌프·밸브·배관",
     "110,128 300,128 300,148 110,148", (205, 140)),
]
# 화력 실루엣에도 계측제어·복수기를 매핑하기 위해 소분류 regions 는 원전 영역을 쓴다
# (BOILER/GT/STURB/GEN2/STACK/PUMP 가 새로 생겼으므로 거기에도 소분류를 잇는다).
_EXTRA_REGION_CATS = {
    "BOILER": ["BOP.BOILER"], "GT": ["TG.TURBINE"], "STURB": ["TG.TURBINE"],
    "GEN2": ["TG.GEN"], "STACK": ["BOP.ENV"], "PUMP": ["BOP.PUMP"],
}


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
                      for i, ko, en, p, s, _ in CONTRACT_TYPES]}


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
        cats = sorted(c[0] for c in PART_CATS if rid in c[7])
        cats = sorted(set(cats) | set(_EXTRA_REGION_CATS.get(rid, [])))
        regs.append({"id": rid, "silhouette": s, "ko": ko, "points": pts,
                     "label": {"x": label[0], "y": label[1]}, "cats": cats})
    return {"viewBox": "0 0 400 200", "silhouettes": sil, "regions": regs}


def check(parts, svg):
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
    print("발전원 %d · 공급계층 %d · 부품 대분류 %d/소분류 %d · 실루엣 %d/영역 %d"
          % (len(dom["domains"]), len(typ["types"]), len(parts["groups"]), len(parts["cats"]),
             len(svg["silhouettes"]), len(svg["regions"])))


if __name__ == "__main__":
    sys.exit(main())
