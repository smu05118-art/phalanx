#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_universe — 조선사·조선기자재 모집단을 KIND 상장법인목록에서 확정한다.

건설(kce_universe)과 달리 **업종 하나로는 안 된다.** KIND 업종이 '선박 및 보트 건조업'인
종목은 13개뿐이고, 정작 핵심 기자재사(엔진·보냉재·피팅·케이블·항해장비)는 '일반 목적용 기계',
'1차 철강', '기초 화학물질', '통신 및 방송 장비' 같은 업종에 흩어져 있다. 지주회사
HD한국조선해양은 '기타 금융업'이다.

모집단 규칙(재현 가능한 세 겹):
  ① 업종  — '선박 및 보트 건조업' 전 종목
  ② 제품  — KIND 주요제품 문구에 선박·조선·해양·선용·marine 등 해상 어휘가 있는 종목
  ③ 지정  — 업종·제품 문구 모두에 안 걸리지만 실질이 조선 공급망인 종목(사유 필수)
여기까지는 후보다. **납품 관계는 프로브(kship_probe)가 DART 원문의 주요 매출처·사업의
내용을 열어 확인**하고, 확인되지 않은 후보는 '미확인'으로 남긴다 — 이름으로 배제하지 않는다.

역할(role): yard(조선사) / holding(지주) / equip(기자재) / steel(강재) / engine(엔진).
슬러그는 종목코드다(수십 곳이라 약칭 관리 불가).

    python3 kship_universe.py            # 조회만
    python3 kship_universe.py --write    # assets/universe.json 갱신
"""
import argparse
import re
import sys

from kship_lib import _get, load_asset, write_asset
from kce_universe import KIND_URL, parse_kind        # noqa: E402  (kce 도구 재사용)

YARD_INDUSTRY = "선박 및 보트 건조업"

# ② 제품 문구 해상 어휘. '보트'·'요트'는 레저용 소형선 제조사를 끌어오므로 뺀다.
# 실측 오탐에서 배운 제약: '반도체배선박막'의 선박, '소화기계류'의 계류, 반도체 스크러버,
# 로켓 추진기, 교량 앵커 — 짧은 낱말은 앞뒤를 보고, 다른 산업과 겹치는 낱말은 뺀다.
_MARINE = re.compile(
    r"(?<!배)(?<!배선)선박|조선(?!소)|해양(?!수산|경찰)|선용|선체|선실|marine|vessel|offshore|"
    r"LNG선|LNG운반|컨테이너선|탱커|유조선|벌크선|FPSO|FSRU|FLNG|해상풍력|해상용|"
    r"함정|잠수함|군함|보냉재|화물창|프로펠러|선미|러더|조타|갑판|해치커버|윈치|"
    r"(?<!기)계류|평형수|밸러스트|BWTS", re.I)
# 제품 문구 경로에서 뺄 업종 — 해운사는 조선사의 **고객**이지 공급망이 아니다.
_NOT_SUPPLY = ("해상 운송업", "상품 종합 도매업", "기계장비 및 관련 물품 도매업",
               "의약품 제조업", "항공기,우주선 및 부품 제조업")

# ③ 지정 — 업종·제품 문구가 조선을 말하지 않지만 실질이 조선 공급망인 종목.
#    사유를 반드시 적는다. 프로브가 원문에서 납품 관계를 확인하지 못하면 '미확인'으로 남는다.
SEED = {
    "009540": ("holding", "HD한국조선해양 — 조선 중간지주(HD현대중공업·HD현대미포·HD현대삼호 연결)"),
    "071970": ("engine", "HD현대마린엔진 — 선박용 중형엔진(힘센)·부품"),
    "077970": ("engine", "STX엔진 — 선박용 디젤엔진·함정 엔진"),
    "082740": ("engine", "한화엔진 — 대형 선박용 저속엔진(舊 HSD엔진)"),
    "033500": ("equip", "동성화인텍 — LNG 화물창 초저온 보냉재(PUF)"),
    "017960": ("equip", "한국카본 — LNG 화물창 보냉재(트리플렉스·PUF), 주요제품 문구는 카본"),
    "013030": ("equip", "하이록코리아 — 계장용 피팅·밸브(조선·해양)"),
    "014620": ("equip", "성광벤드 — 관이음쇠(조선·플랜트)"),
    "023160": ("equip", "태광 — 관이음쇠(조선·플랜트)"),
    "086670": ("equip", "비엠티 — 계장용 피팅·밸브"),
    "217590": ("equip", "티엠씨 — 선박용·해양용 케이블"),
    "065570": ("equip", "삼영이엔씨 — 선박 항해통신(GMDSS)"),
    "100090": ("equip", "SK오션플랜트 — 해상풍력 하부구조물·후육강관(舊 삼강엠앤티)"),
    "133820": ("steel", "화인베스틸 — 조선용 형강"),
    "025550": ("steel", "한국선재 — 선재(조선용 용접재 원자재)"),
    "073010": ("equip", "케이에스피 — 선박엔진용 밸브·형단조"),
    "014940": ("equip", "오리엔탈정공 — 선박용 크레인·데크하우스"),
    "101000": ("equip", "KS인더스트리 — 선박용 크레인·의장품"),
    "085310": ("equip", "엔케이 — 선박용 소화설비·고압가스용기"),
    "096350": ("equip", "대창솔루션 — 선박엔진 구조재(MBS) 주단조"),
    "012210": ("equip", "삼미금속 — 선박부품 단조"),
    "011700": ("equip", "한신기계공업 — 선박용 공기압축기"),
}
# 시드는 **근거가 확실한 것만** 둔다. 기억으로 적은 종목코드가 실제로는 다른 회사였던
# 사고가 있었다(036560=KZ정밀, 043370=피에이치에이, 049470=비트플래닛). 확신이 없으면
# 시드에 넣지 말고 프로브가 원문에서 찾게 둔다 — 이름으로 포함하는 것도 배제만큼 위험하다.

MIN_ROWS = 2000
MIN_UNIVERSE = 20


def role_of(rec, seed_role=None):
    if seed_role:
        return seed_role
    if rec["industry"] == YARD_INDUSTRY:
        p = rec["product"]
        # 업종은 조선업이지만 실제로는 블록·기자재를 만드는 회사가 섞여 있다(현대힘스·세진중공업).
        # 조선업 업종에 XML 솔루션 회사(메디콕스)도 있다 — 조선 실질이 없으면 equip 후보로 두고
        # 프로브가 수주 절 부재로 걸러낸다.
        if re.search(r"기자재|부품|블록|Deck House|배관|측정|경보|라이너|조명|배전반|환경장비|XML|솔루션", p, re.I):
            return "equip"
        return "yard"
    if "선박건조" in (rec["product"] or ""):
        return "yard"                     # HJ중공업 — 업종은 토목건설이지만 조선부문이 있다
    if re.search(r"엔진|내연기관", rec["product"]):
        return "engine"
    if "철강" in rec["industry"] or re.search(r"형강|후판|강재|선재", rec["product"]):
        return "steel"
    return "equip"


def _probe_promoted():
    """kship_scan.py 가 정기보고서 본문으로 찾아 승격한 종목 — assets/universe_probe.json (없으면 빈 사전)."""
    try:
        return load_asset("universe_probe.json").get("promoted") or {}
    except Exception:
        return {}


def select(recs):
    picked = []
    seen = set()
    probe = _probe_promoted()
    for r in recs:
        src = None
        seed = SEED.get(r["stock"])
        pr = probe.get(r["stock"])
        if r["industry"] == YARD_INDUSTRY:
            src = "업종"
        elif seed:
            src = "지정"
        elif _MARINE.search(r["product"] or "") and r["industry"] not in _NOT_SUPPLY:
            src = "제품"
        elif pr:
            src = "탐색"                      # ④ 본문 탐색 — 근거 문장은 pr["reason"]
        if not src:
            continue
        d = dict(r)
        d["slug"] = r["stock"]
        d["source"] = src
        d["role"] = role_of(r, seed[0] if seed else (pr["role"] if (pr and src == "탐색") else None))
        d["reason"] = seed[1] if seed else (pr["reason"] if (pr and src == "탐색") else "")
        d["confirmed"] = None            # 프로브가 원문에서 납품 관계를 확인하면 True/False
        picked.append(d)
        seen.add(r["stock"])
    missing = sorted(set(SEED) - seen)
    if missing:
        # 지정 종목이 KIND에 없으면 상장폐지·합병이다. 조용히 빼지 말고 알린다.
        sys.stderr.write("[warn] 지정 종목이 상장법인목록에 없음(상장폐지·합병?): %s\n" % missing)
    if len(picked) < MIN_UNIVERSE:
        raise RuntimeError("모집단이 %d개뿐 — KIND 응답이 깨졌거나 업종명 체계가 바뀌었다" % len(picked))
    picked.sort(key=lambda r: ({"yard": 0, "holding": 1, "engine": 2, "equip": 3, "steel": 4}[r["role"]],
                               r["stock"]))
    return picked


def fetch(write=False):
    recs = parse_kind(_get(KIND_URL))
    if len(recs) < MIN_ROWS:
        raise RuntimeError("KIND 목록이 %d행뿐" % len(recs))
    picked = select(recs)
    if write:
        write_asset("universe.json", {"source": KIND_URL, "n": len(picked), "rows": picked})
    return picked


def load():
    try:
        return load_asset("universe.json")["rows"]
    except FileNotFoundError:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    recs = fetch(write=a.write)
    for r in recs:
        print("%-7s %-8s %-3s %-16s %-4s %-28s %s" % (r["role"], r["stock"], r["source"][:3],
                                                     r["name"][:16], r["market"][:4],
                                                     r["industry"][:28], (r["reason"] or r["product"])[:48]))
    from collections import Counter
    print("— %d종목 %s" % (len(recs), dict(Counter(r["role"] for r in recs))), file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
