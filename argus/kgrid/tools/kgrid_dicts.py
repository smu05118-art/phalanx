#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kgrid_dicts — 전력기기 탭의 정적 사전을 코드에서 생성한다(손으로 JSON을 쓰지 않는다).

  assets/products.json   제품군 9갈래 — 품목 문구 → 제품군
  assets/demand.json     수요처 6갈래 — 매출처·계약상대 문구 → 수요처
  assets/grid_regions.json  전력망 단선도(발전→승압→송전→변전→배전→수용가) 영역과 제품군 연결

한 곳에서 만드는 이유는 **교차 참조를 생성 시점에 검증**하기 위해서다 —
단선도 영역의 `products` 가 실제 제품군 키인지, 제품군이 `kgrid_lib.PRODUCT_ORDER` 와
어긋나지 않는지(fail-closed). 어긋나면 만들지 않고 멈춘다.

어휘는 **원문에서 본 것만** 넣었다(FINDINGS §6 — 각 갈래의 근거 회사를 주석에 적었다).
매칭은 길이가 아니라 **우선순위**다. `초고압 변압기`를 길이로 고르면 `변압기`(배전용)가
이길 수 있다 — 전압 계급이 붙은 이름에 높은 우선순위를 준다.

    python3 kgrid_dicts.py --write
"""
import argparse
import re
import sys

from kgrid_lib import PRODUCT_LABEL, PRODUCT_ORDER, product_color, write_asset

# ── 제품군 ─────────────────────────────────────────────────
# (키, 강한 어휘[prio 90], 일반 어휘[prio 50], 근거)
PRODUCTS = [
    ("ehv",
     ["초고압변압기", "초고압 변압기", "765kV", "345kV", "154kV", "HVDC변압기",
      "HVDC 변환용 변압기", "전력용변압기", "특수변압기", "쉘타입", "Shell Type"],
     ["초고압", "전력변압기", "변압기(전력용)", "대형변압기", "UHV"],
     "HD현대일렉트릭 `변압기`·일진전기 `변압기 등중전기`·엘에스일렉트릭 본문 `특수변압기`"),
    ("dist_tr",
     ["배전용변압기", "주상변압기", "몰드변압기", "유입변압기", "건식변압기", "지상변압기",
      "패드변압기", "Pad Mount"],
     # 여기에 맨 `변압기` 를 넣으면 안 된다 — 그러면 HD현대일렉트릭(초고압 변압기의 대표
     # 회사)이 '배전용'으로 분류된다. 계급을 밝히지 않은 `변압기` 는 tr_unknown 의 몫이다.
     ["주상", "몰드", "유입변압", "건식변압", "패드마운트"],
     "산일전기 KIND `유입, 몰드, 주상, 건식 변압기 등`·제룡전기 `주상변압기`"),
    ("breaker",
     ["가스절연개폐장치", "가스절연", "GIS개폐장치", "GIS차단기", "진공차단기", "VCB", "GCB",
      "ACB", "기중차단기", "고압차단기", "초고압차단기"],
     ["차단기", "개폐장치", "스위치기어", "배선용차단기", "MCCB", "누전차단기", "ELCB"],
     "HD현대일렉트릭 `고압차단기`·광명전기 `가스절연개폐장치`·비츠로테크 `차단기`"),
    ("switchgear",
     ["수배전반", "수·배전반", "고압배전반", "저압배전반", "분전반", "전동기제어반", "MCC",
      "중앙감시반", "자동제어반"],
     ["배전반", "수배전", "배전설비", "큐비클", "패널보드"],
     "서전기전·광명전기·지투파워 `수배전반`·제일일렉트릭 `분전반`"),
    ("switch",
     ["가스절연개폐기", "기중개폐기", "자동개폐기", "부하개폐기", "리클로저", "섹셔널라이저"],
     ["개폐기", "단로기", "COS", "컷아웃"],
     "광명전기·비츠로테크 `개폐기`"),
    ("converter",
     ["ESS PCS", "전력변환장치", "인버터(PCS)", "태양광인버터", "STATCOM", "FACTS",
      "무효전력보상", "정류기"],
     ["인버터", "전력변환", "PCS", "컨버터", "UPS"],
     "엘에스일렉트릭 `인버터`·지투파워 `인버터(PCS)`·이지트로닉스 `전력변환장치`"),
    ("cable",
     ["초고압케이블", "초고압선", "해저케이블", "전력케이블", "전력선", "가공송전선",
      "OPGW", "초전도선재", "부스덕트", "부스웨이", "Busway"],
     ["케이블", "전선", "나동선", "절연선", "동선", "알루미늄선"],
     "일진전기 `전력선`·대한전선 `초고압선`·서남 `고온초전도선재`·티에스넥스젠 `Busway`"),
    ("relay",
     ["배전자동화단말장치", "보호계전기", "디지털계전기", "원방감시제어", "SCADA",
      "전력감시제어", "배전자동화"],
     ["계전기", "보호제어", "감시제어", "RTU", "FRTU", "전력량계", "원격검침", "MOF"],
     "피앤씨테크 `배전자동화단말장치`·비츠로시스 `원방감시제어시스템`·옴니시스템 `전자식전력량계`"),
    # 원문이 전압 계급을 밝히지 않은 `변압기` — 초고압인지 배전용인지 정하지 않는다.
    # 강한 어휘를 두지 않는다(강한 어휘가 있으면 ehv·dist_tr 을 이겨 버린다).
    ("tr_unknown",
     [],
     ["변압기", "변압", "중전기", "Transformer"],
     "HD현대일렉트릭 품목 `변압기, 고압차단기…` — II절 어디에도 `초고압`·`345kV`가 없다(실측)"),
    ("fitting",
     ["송배전금구류", "송배전 금구류", "송변전용금구류", "전기절연유", "변압기유", "탭체인저",
      "부싱", "애자"],
     ["금구류", "절연유", "권선", "코일", "철심", "규소강판", "몰드수지", "자재"],
     "제룡산업·보성파워텍 `송배전 금구류`·세명전기 `154/345/765kV 금구류`·미창석유공업 `전기절연유`"),
]

# ── 수요처 ─────────────────────────────────────────────────
# 매출처·계약상대 문구 → 수요처. 실명이 원문에 적힌 것만 강한 어휘로 넣었다(FINDINGS §3).
DEMAND = [
    ("na_utility",
     ["NextEra", "Xcel", "Dominion", "Duke Energy", "AEP", "Southern Company", "PG&E",
      "Exelon", "Entergy", "FirstEnergy", "National Grid", "Hydro", "TVA"],
     ["북미", "미주", "미국", "캐나다", "Utility", "Electric Power", "Energy Corp",
      "Power Company", "Electric Co"],
     "HD현대일렉트릭 주요매출처 `NextEra Energy 15.9%`(2026 반기 실측)"),
    ("me_utility",
     ["사우디 전력청", "Saudi Electricity", "SEC", "ADWEA", "DEWA", "TRANSCO", "KAHRAMAA",
      "MEW", "Aramco", "ADNOC"],
     ["중동", "사우디", "UAE", "아랍", "카타르", "쿠웨이트", "오만", "바레인", "전력청"],
     "HD현대일렉트릭 주요매출처 `사우디 전력청 5.0%`(2026 반기 실측)"),
    ("kepco",
     ["한국전력공사", "한국전력", "KEPCO", "한국수력원자력", "한국전기안전공사",
      "한국철도공사", "한국토지주택공사", "한전KDN", "한전KPS"],
     ["한전", "발전공기업", "공기업", "조달청", "지방자치단체"],
     "엘에스일렉트릭 전력-인프라 매출처 `한국전력공사 2.7%`(2026 반기 실측)"),
    ("datacenter",
     ["데이터센터", "IDC", "Data Center", "하이퍼스케일"],
     ["AI데이터", "클라우드", "전산센터"],
     "엘에스일렉트릭 판매전략 본문 `국내/외 데이터센터(IDC) … End-user 집중 공략`"),
    ("renewable",
     ["한화큐셀", "HANWHA Q CELLS", "엘지에너지솔루션", "삼성에스디아이", "GSES"],
     ["태양광", "풍력", "신재생", "재생에너지", "ESS", "계통연계", "발전단지"],
     "엘에스일렉트릭 종속회사 매출처 `HANWHA Q CELLS 44.8%`·`GSES 1 LIMITED 22.7%`"),
    ("industrial",
     ["삼성전자", "SK하이닉스", "현대제철", "포스코", "LG전자", "에쓰오일", "GS칼텍스",
      "현대중공업", "삼성중공업", "한화오션"],
     ["반도체", "제철", "석유화학", "플랜트", "조선", "EPC", "산업단지", "제조회사"],
     "산일전기 매출처 분류 `조선 산업 25.7`·`전력 산업 66.6`(고객 분류이지 실명이 아니다)"),
]

# ── 전력망 단선도 ───────────────────────────────────────────
# 조선 탭의 선박 단면과 같은 자리를 이 산업에서는 **계통 단선도**가 맡는다.
# 전기가 흐르는 순서대로 왼쪽에서 오른쪽으로 놓는다 —
#   발전 → 승압변전소 → 초고압 송전선로 → 변전소 → 배전선로 → 수용가
# 영역을 누르면 그 자리에 들어가는 제품군과 그것을 만드는 회사가 보인다.
VIEWBOX = "0 0 960 260"
REGIONS = [
    {"id": "GEN", "ko": "발전소", "en": "Generation", "x": 12, "y": 96, "w": 104, "h": 76,
     "products": [], "note": "이 탭의 모집단이 아니다 — 전력기기의 시작점으로만 그린다"},
    {"id": "STEPUP", "ko": "승압 변전소", "en": "Step-up substation", "x": 140, "y": 76, "w": 128, "h": 116,
     "products": ["ehv", "tr_unknown", "breaker", "fitting"],
     "note": "발전 전압을 345·765kV로 올린다. 초고압 변압기와 가스절연 차단기(GIS)의 자리"},
    {"id": "TRANS", "ko": "송전 선로", "en": "Transmission line", "x": 292, "y": 40, "w": 132, "h": 152,
     "products": ["cable", "fitting"],
     "note": "가공 송전선·지중 초고압 케이블·HVDC. 철탑 금구류와 애자가 여기 붙는다"},
    {"id": "SUB", "ko": "변전소", "en": "Substation", "x": 448, "y": 76, "w": 132, "h": 116,
     "products": ["ehv", "breaker", "switch", "relay"],
     "note": "전압을 154kV·22.9kV로 낮춘다. 차단기·개폐기·보호계전기가 모인다"},
    {"id": "DIST", "ko": "배전 선로", "en": "Distribution", "x": 604, "y": 76, "w": 132, "h": 116,
     "products": ["dist_tr", "tr_unknown", "switch", "cable", "fitting", "relay"],
     "note": "주상변압기·개폐기·배전자동화 단말. **회전 산업**의 자리다(잔고가 짧다)"},
    {"id": "LOAD", "ko": "수용가", "en": "Customer premises", "x": 760, "y": 56, "w": 188, "h": 156,
     "products": ["switchgear", "converter", "relay"],
     "note": "데이터센터·공장·건물. 수배전반과 전력변환(ESS PCS·인버터)이 들어간다"},
]


def _check():
    keys = set(PRODUCT_ORDER)
    got = [k for k, _s, _g, _w in PRODUCTS]
    if set(got) != keys:
        raise RuntimeError("제품군 키가 kgrid_lib.PRODUCT_ORDER 와 어긋난다: %s"
                           % sorted(keys ^ set(got)))
    for r in REGIONS:
        bad = [p for p in r["products"] if p not in keys]
        if bad:
            raise RuntimeError("단선도 영역 %s 가 없는 제품군을 가리킨다: %s" % (r["id"], bad))
    # 어느 영역도 가리키지 않는 제품군이 있으면 인포그래픽에서 영영 안 보인다 — 막는다.
    used = {p for r in REGIONS for p in r["products"]}
    orphan = keys - used
    if orphan:
        raise RuntimeError("단선도 어디에도 없는 제품군: %s" % sorted(orphan))
    seen = set()
    for _k, strong, general, _w in PRODUCTS:
        for w in strong + general:
            if len(w) < 2:
                raise RuntimeError("한 글자 어휘는 오탐을 부른다: %r" % w)
        seen |= set(strong) | set(general)
    return True


def build():
    _check()
    products = []
    for key, strong, general, why in PRODUCTS:
        products.append({
            "key": key, "label": PRODUCT_LABEL[key], "color": product_color(key),
            "order": PRODUCT_ORDER.index(key), "why": why,
            "words": ([{"w": w, "prio": 90} for w in strong]
                      + [{"w": w, "prio": 50} for w in general]),
        })
    demand = []
    for key, strong, general, why in DEMAND:
        demand.append({
            "key": key, "why": why,
            "words": ([{"w": w, "prio": 90} for w in strong]
                      + [{"w": w, "prio": 50} for w in general]),
        })
    return products, demand


def classify(text, dicts):
    """문구 → 키. 우선순위가 높은 어휘가 이기고, 같으면 긴 어휘가 이긴다. 없으면 None."""
    t = re.sub(r"[\s　]+", "", text or "")
    if not t:
        return None
    best = None
    for d in dicts:
        for w in d["words"]:
            ww = re.sub(r"[\s　]+", "", w["w"])
            if ww and ww.lower() in t.lower():
                cand = (w["prio"], len(ww), d["key"])
                if best is None or cand > best:
                    best = cand
    return best[2] if best else None


def classify_all(text, dicts, limit=3):
    """문구 → 키 여러 개(한 회사가 변압기도 차단기도 만든다). 우선순위 순."""
    t = re.sub(r"[\s　]+", "", text or "").lower()
    if not t:
        return []
    hits = {}
    for d in dicts:
        for w in d["words"]:
            ww = re.sub(r"[\s　]+", "", w["w"]).lower()
            if ww and ww in t:
                cur = hits.get(d["key"], 0)
                hits[d["key"]] = max(cur, w["prio"] + len(ww))
    return [k for k, _v in sorted(hits.items(), key=lambda kv: -kv[1])][:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    products, demand = build()
    if a.write:
        write_asset("products.json", {"n": len(products), "rows": products})
        write_asset("demand.json", {"n": len(demand), "rows": demand})
        write_asset("grid_regions.json", {"viewBox": VIEWBOX, "regions": REGIONS})
    for p in products:
        print("%-11s %-18s 어휘 %2d  %s" % (p["key"], p["label"], len(p["words"]), p["why"][:56]))
    print("— 수요처 %d · 단선도 영역 %d" % (len(demand), len(REGIONS)), file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
