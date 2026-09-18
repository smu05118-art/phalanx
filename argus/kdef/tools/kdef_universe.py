#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kdef_universe — 한국 방산 모집단을 KIND 상장법인목록에서 확정한다.

조선 탭보다 **업종이 더 못 쓴다**(FINDINGS §0 실측):
  · `항공기,우주선 및 부품 제조업` 11종목 · `무기 및 총포탄 제조업` **3종목뿐**
  · 체계업체 대부분이 그 밖에 있다 — 현대로템=`그외 기타 운송장비`, 한화시스템=`전자부품`,
    풍산=`1차 비철금속`, 빅텍=`측정,시험,항해,제어…`, SNT다이내믹스·한일단조=`자동차 신품 부품`,
    코츠테크놀로지=`컴퓨터 및 주변장치`, 스페코·엠앤씨솔루션=`특수 목적용 기계`.

그래서 **네 겹**이다(스펙 §모집단):
  ① 업종  — 위 두 업종 전 종목
  ② 제품  — KIND 주요제품 문구의 방산 어휘. 짧은 낱말은 금물이다. `탄` 하나를 넣으면
            석탄·부탄·탄산·탄소섬유·탄소배출권이 전부 들어온다(실측 42건 중 24건이 오탐).
            `레이더`도 `레이더디텍터`(차량용)를 끌어온다 — 부정 전방탐색으로 막는다.
  ③ 지정  — 사유를 적은 지정. **종목코드는 KIND에서 이름으로 조회해 확인했다**(FINDINGS §0).
            LIG넥스원은 KIND에 그 이름이 없다 — 현재 상호 `LIG디펜스앤에어로스페이스`(079550).
  ④ 탐색  — `kdef_scan.py` 가 정기보고서 II절 본문에서 찾아 승격한 종목(assets/universe_probe.json).

역할(role)은 **힌트**다. 체계업체 여부의 진짜 근거는 계약 공시의 상대(방위사업청·국방과학연구소
직계약 = GOV)이며 `kdef_contracts.py` 가 확인해 `gov_contract` 로 되돌려 준다 — 이름으로 단정하지 않는다.
  prime 체계업체 · part 부품·구성품 · material 소재·화약 · service 정비·ILS · holding 지주

    python3 kdef_universe.py            # 조회만
    python3 kdef_universe.py --write    # assets/universe.json 갱신
"""
import argparse
import re
import sys
from collections import Counter

from kdef_lib import KIND_URL, _get, load_asset, parse_kind, write_asset

# ① 업종 — FINDINGS §0 에서 KIND 실제 표기를 그대로 확인했다(쉼표 뒤 공백 없음).
DEF_INDUSTRIES = ("항공기,우주선 및 부품 제조업", "무기 및 총포탄 제조업")

# ② 제품 문구 방산 어휘. 실측 오탐에서 배운 제약:
#   · `탄` 단독 금지(석탄·부탄·탄산·탄소) → `탄약`·`유도탄`·`방탄` 처럼 붙은 꼴만
#   · `레이더디텍터`는 차량용 과속탐지기다
#   · `군수(?!업)` — '군수업'은 지방자치(군수)와 겹치지 않지만 안전하게 남긴다
#   · `전차(?!선)` — 전차선(電車線, 철도 급전)은 방산이 아니다
_DEF = re.compile(
    r"방산|방위산업|방위력|국방|군용|군수(?!업)|군납|군장|무기체계|유도무기|유도탄|탄약|"
    r"전차(?!선)|자주포|장갑차|함정(?!없)|잠수함|전투기|전투체계|레이더(?!디텍터)|"
    r"야시장비|야간투시|열영상|항공전자|총포|방탄|방검|미사일|화약|화공품|추진기관|병기|"
    r"군함|군용기|훈련기|무인기|(?<!유)전자전(?!달)", re.I)
# `유전자전달체`(압타바이오)가 `전자전`에 걸렸다 — 앞뒤를 보고 막는다.

# ② 경로에서 뺄 업종 — 방산의 **고객·유통**이지 공급망이 아니다.
_NOT_SUPPLY = ("상품 종합 도매업", "기타 전문 도매업", "기계장비 및 관련 물품 도매업",
               "공공 행정, 국방 및 사회보장 행정", "기타 금융업")

# ③ 지정 — 업종·제품 문구가 방산을 말하지 않지만 실질이 방산인 종목.
#    종목코드는 전부 KIND 조회로 확인했다(기억으로 적지 않았다 — 과거 오적재 사고).
SEED = {
    # 업종 ①에 있지만 역할이 '부품'으로 잘못 잡히는 체계업체 — FINDINGS §1 에서 방위사업청·
    # 국방과학연구소 직계약(GOV)을 계약 공시 원문으로 확인한 회사들이다.
    "012450": ("prime", "한화에어로스페이스 — 방위사업청 직계약 확인(FINDINGS §1). 항공엔진·지상방산"),
    "047810": ("prime", "한국항공우주 — 방위사업청 직계약 확인(KF-X 체계개발). 완제기·기체부품"),
    "079550": ("prime", "LIG디펜스앤에어로스페이스 — 구 LIG넥스원. 방위사업청 직계약(L-SAM·천궁Ⅱ)"),
    "064350": ("prime", "현대로템 — 업종 `그외 기타 운송장비`. K2전차·차륜형장갑차 디펜스솔루션 부문"),
    "272210": ("prime", "한화시스템 — 업종 `전자부품`. 함정 전투체계·레이다·감시정찰"),
    "103140": ("prime", "풍산 — 업종 `1차 비철금속`. 방산(탄약) 부문 별도 공시(≠풍산홀딩스 005810)"),
    "042660": ("prime", "한화오션 — 업종 `선박 및 보트 건조업`. 특수선(잠수함·수상함) 부문"),
    "214430": ("part", "아이쓰리시스템 — 업종 `전자부품`. 적외선 영상센서(EO/IR 탐지기)"),
    "065450": ("part", "빅텍 — 전자전 시스템 장치류·피아식별·전원공급장치"),
    "013810": ("part", "스페코 — 업종 `특수 목적용 기계`(아스팔트플랜트). 방산부문(박격포·해상풍력)"),
    "024740": ("part", "한일단조 — 업종 `자동차 신품 부품`. 방산 단조품(포신·박격포)"),
    "003570": ("part", "SNT다이내믹스 — 업종 `자동차 신품 부품`. 변속기·포탑구동·자주포 동력전달"),
    "211270": ("part", "AP위성 — 위성통신 단말기(군위성통신 포함)"),
    "011210": ("part", "현대위아 — 업종 `자동차 신품 부품`. 방산(포·구동장치) — 본문 확인 대상"),
    "003490": ("part", "대한항공 — 업종 `항공 여객 운송업`이나 항공우주사업본부(군용기 MRO·기체구조물)"),
}

MIN_ROWS = 2000
MIN_UNIVERSE = 20


def role_of(rec, seed_role=None, probe_role=None):
    """역할 힌트. 계약 공시가 GOV 직계약을 확인하면 kdef_contracts 가 prime 으로 올린다."""
    if seed_role:
        return seed_role
    if probe_role:
        return probe_role
    p = rec.get("product") or ""
    ind = rec.get("industry") or ""
    if re.search(r"금융", ind):
        return "holding"
    if re.search(r"화약|화공품|추진제|특수강|티타늄|복합소재", p) \
       or (re.search(r"1차 철강|1차 비철금속|기초 화학물질", ind) and not re.search(r"완제|체계", p)):
        return "material"
    # 서비스는 **제조를 말하지 않을 때만**이다. '…제조,판매,정비'(기아)는 제조사다.
    if re.search(r"정비|창정비|ILS|군수지원|시뮬레이터|훈련체계|기술교범|용역", p, re.I) \
       and not re.search(r"제조|생산|부품|장비|시스템|발사체|위성|차량|엔진", p):
        return "service"
    return "part"


def _probe_promoted():
    """kdef_scan.py 가 정기보고서 본문으로 찾아 승격한 종목(없으면 빈 사전)."""
    try:
        return load_asset("universe_probe.json").get("promoted") or {}
    except Exception:
        return {}


def select(recs):
    picked, seen = [], set()
    probe = _probe_promoted()
    for r in recs:
        src = None
        seed = SEED.get(r["stock"])
        pr = probe.get(r["stock"])
        if r["industry"] in DEF_INDUSTRIES:
            src = "업종"
        elif seed:
            src = "지정"
        elif _DEF.search(r["product"] or "") and r["industry"] not in _NOT_SUPPLY:
            src = "제품"
        elif pr:
            src = "탐색"
        if not src:
            continue
        d = dict(r)
        d["slug"] = r["stock"]
        d["source"] = src
        d["role"] = role_of(r, seed[0] if seed else None,
                            (pr or {}).get("role") if src == "탐색" else None)
        d["reason"] = seed[1] if seed else ((pr or {}).get("reason", "") if src == "탐색" else "")
        if src == "제품":
            m = _DEF.search(r["product"])
            d["reason"] = "KIND 주요제품 문구에 `%s` — %s" % (m.group(0), (r["product"] or "")[:60])
        d["gov_contract"] = None       # 계약 공시로 확인(방위사업청·국방과학연구소 직계약)
        d["def_share"] = None          # 정기보고서 부문 매출로 확인
        picked.append(d)
        seen.add(r["stock"])
    missing = sorted(set(SEED) - seen)
    if missing:
        sys.stderr.write("[warn] 지정 종목이 상장법인목록에 없음(상장폐지·상호변경?): %s\n" % missing)
    if len(picked) < MIN_UNIVERSE:
        raise RuntimeError("모집단이 %d개뿐 — KIND 응답이 깨졌거나 업종명 체계가 바뀌었다" % len(picked))
    order = {"prime": 0, "part": 1, "material": 2, "service": 3, "holding": 4}
    picked.sort(key=lambda r: (order[r["role"]], r["stock"]))
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
        print("%-8s %-7s %-3s %-18s %-4s %-24s %s"
              % (r["role"], r["stock"], r["source"][:2], r["name"][:18], r["market"][:4],
                 r["industry"][:24], (r["reason"] or r["product"])[:56]))
    print("— %d종목 %s" % (len(recs), dict(Counter(r["role"] for r in recs))), file=sys.stderr)
    print("  출처 %s" % dict(Counter(r["source"] for r in recs)), file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
