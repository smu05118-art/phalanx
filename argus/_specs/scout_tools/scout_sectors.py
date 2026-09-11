#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scout_sectors — 후보 산업(섹터) 정의와 표본 선정. **DART를 두드리지 않는다**(KIND 캐시만 쓴다).

왜 업종만으로는 안 되는가 — KIND 업종명(KSIC)은 넓다. `특수 목적용 기계 제조업` 169사 안에
반도체·이차전지·디스플레이 장비가 다 들어 있고, `철도장비 제조업`이라는 업종은 **아예 없다**
(현대로템은 `그외 기타 운송장비 제조업`). 그래서 섹터를 **(업종 ∩ 주요제품 어휘)** 로 정의한다.

표본은 **업종 대표성** 기준(시총·매출 순이 아니다, scout.md §2):
  ① 앵커 — 그 산업을 정의하는 회사. **이름으로 KIND를 조회**해 종목코드를 얻는다(기억 금지).
  ② 어휘 적중 수가 많은 회사(제품 문구가 그 산업을 직접 말하는 회사)
  ③ 동점이면 시장 구분(유가/코스닥) 다양성 → 종목코드 오름차순(결정적)

    python3 scout_sectors.py                # 섹터별 후보 수·표본 명단
    python3 scout_sectors.py --sector npp   # 한 섹터 자세히
    python3 scout_sectors.py --write        # assets/sample.json
"""
import argparse
import re
import sys

from scout_lib import kind_all, write_asset

CAP = 8              # 섹터당 표본 상한(scout.md §2)
MAX_SAMPLE = 200     # 전체 표본 상한(scout.md 말미)

# ── 섹터 정의 ────────────────────────────────────────────────
# ind: 업종 정규식(None이면 업종 무관) · kw: 주요제품 어휘 · neg: 배제(업종+제품 합친 문자열에 적용)
SECTORS = [
 {"id": "npp", "label": "원자력·발전기자재", "cap": CAP,
  "ind": r"기계 제조업|구조용 금속제품|1차 철강|금속 가공|측정, 시험|전기장비|기타 과학기술|엔지니어링",
  "kw": r"원자력|원전|원자로|핵연료|방사선|발전설비|발전용|발전기자재|보일러|터빈|터어빈|주단조|압력용기|열교환기",
  "neg": r"리츠|부동산|금융|소프트웨어 개발|의약|화장품|식품",
  "why": "원전 주기기·발전설비는 계약당 수천억, 납기 5~10년. 체코 두코바니로 신규 수주가 살아났다"},

 {"id": "power", "label": "전력기기(변압기·차단기)", "cap": CAP,
  "ind": r"전동기, 발전기|전기장비|절연선|전기 및 통신 공사업",
  "kw": r"변압기|차단기|배전반|수배전|개폐기|전력기기|송전|배전|전력변환|계전기|전력설비|가스절연|GIS",
  "neg": r"리츠|부동산|금융|의약|화장품|건전지|이차전지 제조",
  "why": "북미·중동 전력망 교체 사이클. HD현대일렉트릭은 잔고/매출 2.3년(원문 실측)"},

 {"id": "batt_eq", "label": "이차전지 장비", "cap": CAP,
  "ind": r"특수 목적용 기계|일반 목적용 기계|기계장비 및 관련 물품 도매",
  "kw": r"이차전지|2차전지|전지.{0,6}장비|배터리.{0,6}장비|전극|노칭|와인딩|스태킹|조립설비|화성공정|활성화공정|폴더블.{0,4}전지",
  "neg": r"리츠|부동산|금융|의약|화장품",
  "why": "고객(셀 3사)의 CAPEX에 종속된 발주형 산업. 수주공시 빈도가 높다고 알려져 있다 — 원문으로 확인"},

 {"id": "disp_eq", "label": "디스플레이 장비", "cap": CAP,
  "ind": r"특수 목적용 기계|일반 목적용 기계|측정, 시험|전자부품",
  "kw": r"디스플레이.{0,8}장비|OLED.{0,8}장비|LCD.{0,8}장비|평판디스플레이|디스플레이 제조|증착기|봉지|레이저.{0,6}장비",
  "neg": r"리츠|부동산|금융|의약|필름|박판|소재",
  "why": "단일 고객(삼성D·LGD) 대형 발주. 반도체장비(ksemi)와 축이 같은지 다른지 확인 대상"},

 {"id": "rail", "label": "철도차량·철도시스템", "cap": CAP,
  "ind": None,
  "kw": r"철도차량|전동차|기관차|객차|철도(신호|시스템|부품|차량|인프라|교통)|철도 (신호|차량)|궤도",
  "neg": r"리츠|부동산|금융|의약|자동차 신품 부품",
  "why": "관급 다년 계약. 현대로템 II-4는 42행 진행률적용 수주표(원문 실측)"},

 {"id": "aero", "label": "우주·항공부품", "cap": CAP,
  "ind": r"항공기,우주선|기계 제조업|금속 가공|전자부품|측정, 시험|자연과학 및 공학 연구개발",
  "kw": r"항공기|항공부품|우주|위성|발사체|기체|항공.{0,4}구조물|엔진부품|MRO",
  "neg": r"리츠|부동산|금융|여행|운송업|항공 여객",
  "why": "기체구조물 장기공급계약(LTA)·방산 겸업. kdef와 겹치는 범위를 확인해야 한다"},

 {"id": "wind", "label": "해상풍력", "cap": CAP,
  "ind": r"구조용 금속제품|기계 제조업|1차 철강|금속 가공|전기장비|선박 및 보트",
  "kw": r"풍력|해상풍력|풍력타워|나셀|블레이드|하부구조물|자켓|모노파일",
  "neg": r"리츠|부동산|금융|의약",
  "why": "프로젝트 단위 대형 수주·다년 납기. 조선(kship)의 구조물 공급망과 겹칠 수 있다"},

 {"id": "epc", "label": "플랜트·EPC(비건설업)", "cap": CAP,
  "ind": r"엔지니어링|기계 제조업|구조용 금속제품|전문 도매|기타 과학기술",
  "kw": r"플랜트|EPC|일괄도급|턴키|정유.{0,4}설비|석유화학.{0,4}설비|가스.{0,4}설비|화공기기|화공설비|화공플랜트|산업설비|환경.{0,4}플랜트",
  "neg": r"리츠|부동산|금융|의약|화장품|건물 건설업|토목 건설업",
  "why": "건설(kce)이 이미 덮는 범위를 뺀 나머지 — 기자재·모듈·설계 전문사가 별도 산업인지 확인"},

 {"id": "env", "label": "환경·수처리", "cap": CAP,
  "ind": r"기계 제조업|엔지니어링|폐기물|하수|건설업|기타 화학|전기장비",
  "kw": r"수처리|폐수|하수|정수장|환경설비|소각|매립|대기오염|집진|탈황|탈질|바이오가스|슬러지",
  "neg": r"리츠|부동산|금융|의약|정수기|생활용품|가정용",
  "why": "관급 시설 공사 발주. 다만 정수기·생활가전이 같은 어휘에 걸려 배제가 필요하다"},

 {"id": "fa", "label": "스마트팩토리·물류자동화", "cap": CAP,
  "ind": r"특수 목적용 기계|일반 목적용 기계|컴퓨터 프로그래밍|전자부품|소프트웨어",
  "kw": r"물류자동화|자동화설비|스마트팩토리|공장자동화|반송|컨베이어|물류시스템|자동창고|AGV|OHT|무인반송",
  "neg": r"리츠|부동산|금융|의약|게임",
  "why": "설비 단위 수주. 고객 CAPEX 종속이라 이차전지 장비와 성격이 비슷한지 확인"},

 {"id": "med", "label": "의료기기", "cap": CAP,
  "ind": r"의료용 기기|측정, 시험|전자부품|사진장비 및 광학기기",
  "kw": r"의료기기|영상진단|초음파|X-?ray|CT|MRI|내시경|임플란트|치과|수술|재활|의료용",
  "neg": r"리츠|부동산|금융|화장품|건강기능식품|의약품 제조|진단시약|체외진단",
  "why": "대조군에 가깝다 — 소모품·판매형이면 수주기반이 아니다. 원문으로 확인해 '아니다'를 기록"},

 {"id": "telco_eq", "label": "통신장비", "cap": CAP,
  "ind": r"통신 및 방송 장비|전자부품|측정, 시험",
  "kw": r"통신장비|기지국|중계기|광전송|교환기|안테나|네트워크장비|스위치|라우터|위성통신|광케이블",
  "neg": r"리츠|부동산|금융|전기 통신업|방송프로그램|의약",
  "why": "통신사 투자 사이클. 납품형(PO)이라 수주잔고 공시가 없을 가능성 — 확인 대상"},

 {"id": "elev", "label": "승강기·산업기계(대조군)", "cap": 5,
  "ind": r"일반 목적용 기계|특수 목적용 기계",
  "kw": r"엘리베이터|에스컬레이터|승강기|주차설비|크레인|호이스트|공작기계|사출성형기|프레스",
  "neg": r"리츠|부동산|금융|의약|선박|선용|조선",
  "why": "대조군 — 설치형 기계가 수주잔고를 공시하는지. 공시하면 후보, 아니면 '아니다'의 기준선"},

 # ── 보정(calibration) — 이미 탭이 있는 산업. 후보가 아니라 **점수 눈금의 기준점**이다.
 {"id": "cal_kship", "label": "[보정] 조선", "cap": 4,
  "ind": r"선박 및 보트 건조업", "kw": r".", "neg": None,
  "why": "보정 — 수주기반의 전형(잔고/매출 3년 내외). 점수 상단 기준점"},
 {"id": "cal_kce", "label": "[보정] 건설", "cap": 4,
  "ind": r"^건물 건설업$|^토목 건설업$", "kw": r".", "neg": None,
  "why": "보정 — 수주기반의 전형(현장 단위 공시). 점수 상단 기준점"},
]

# 앵커: 그 산업을 정의하는 회사. **이름만 적고 종목코드는 KIND에서 조회한다**(기억으로 적지 않는다).
ANCHORS = {
 "npp":      ["두산에너빌리티", "비에이치아이", "우진", "한전KPS", "한전기술", "오르비텍"],
 "power":    ["HD현대일렉트릭", "엘에스일렉트릭", "효성중공업", "일진전기", "산일전기", "제룡전기"],
 "batt_eq":  ["씨아이에스", "피엔티", "엠플러스", "윤성에프앤씨", "디이엔티", "하나기술"],
 "disp_eq":  ["SFA", "원익IPS", "필옵틱스", "아이씨디", "베셀", "케이씨텍"],
 "rail":     ["현대로템", "대아티아이", "에스트래픽", "세명전기"],
 "aero":     ["한국항공우주", "하이즈항공", "아스트", "켄코아에어로스페이스", "이노스페이스", "루미르"],
 "wind":     ["씨에스윈드", "SK오션플랜트", "유니슨", "동국S&C", "삼강엠앤티", "씨에스베어링"],
 "epc":      ["삼성E&A", "한텍", "우양에이치씨", "성광벤드", "태광", "동성화인텍"],
 "env":      ["KC코트렐", "코엔텍", "와이엔텍", "웰크론한텍"],
 "fa":       ["SFA", "현대엘리베이터", "신성이엔지", "에이치브이엠", "로체시스템즈"],
 "med":      ["클래시스", "루닛", "제이피아이헬스케어", "뷰웍스", "레이"],
 "telco_eq": ["인텔리안테크", "에치에프알", "쏠리드", "케이엠더블유", "다산네트웍스", "유비쿼스"],
 "elev":     ["현대엘리베이터", "티에스아이", "화천기공", "한신기계공업"],
 "cal_kship": ["HD현대중공업", "삼성중공업", "한화오션"],
 "cal_kce":  ["현대건설", "GS건설", "대우건설", "금호건설"],
}


def _by_name(rows):
    d = {}
    for r in rows:
        d.setdefault(r["name"], r)
        d.setdefault(re.sub(r"\s+", "", r["name"]).upper(), r)
    return d


def candidates(rows, sec):
    """섹터 후보 = 업종 조건 ∧ 제품 어휘 ∧ ¬배제."""
    ind = re.compile(sec["ind"]) if sec.get("ind") else None
    kw = re.compile(sec["kw"], re.I)
    neg = re.compile(sec["neg"]) if sec.get("neg") else None
    out = []
    for r in rows:
        blob = (r["industry"] or "") + " " + (r["product"] or "")
        if neg and neg.search(blob):
            continue
        if ind and not ind.search(r["industry"] or ""):
            continue
        if not kw.search(r["product"] or ""):
            continue
        out.append(r)
    return out


def _hits(sec, r):
    """제품 문구가 몇 개의 **서로 다른** 어휘에 걸리는가 — 그 산업을 얼마나 직접 말하는가."""
    return len(set(m.group(0).lower()
                   for m in re.finditer(sec["kw"], r["product"] or "", re.I)))


def pick(rows, sec, anchors_by_name):
    """표본 선정. 앵커 우선 → 어휘 적중 수 → 시장 다양성 → 종목코드(결정적)."""
    cap = sec.get("cap", CAP)
    cands = candidates(rows, sec)
    cset = {r["stock"]: r for r in cands}
    picked, missing = [], []
    for nm in ANCHORS.get(sec["id"], []):
        r = anchors_by_name.get(nm) or anchors_by_name.get(re.sub(r"\s+", "", nm).upper())
        if not r:
            missing.append(nm)
            continue
        if r["stock"] in {p["stock"] for p in picked}:
            continue
        picked.append(dict(r, anchor=True, hits=_hits(sec, r),
                           pick_reason="앵커 — 이 산업을 정의하는 회사(KIND 이름 조회로 종목코드 확인)"))
    # 앵커가 후보 조건에 안 걸려도 표본에는 넣는다(어휘가 산업을 다 담지 못하는 증거로 남긴다)
    rest = [r for r in cands if r["stock"] not in {p["stock"] for p in picked}]
    rest.sort(key=lambda r: (-_hits(sec, r), r["market"] != "유가증권시장", r["stock"]))
    for r in rest:
        if len(picked) >= cap:
            break
        n = _hits(sec, r)
        kws = sorted(set(m.group(0) for m in re.finditer(sec["kw"], r["product"] or "", re.I)))[:3]
        picked.append(dict(r, anchor=False, hits=n,
                           pick_reason="제품 문구 %s %d개 어휘 적중 · %s" % (
                               "·".join(kws) or "-", n, r["market"])))
    return picked[:cap], len(cands), missing


def select_all(rows=None, cap=CAP):
    rows = rows or kind_all()
    by_name = _by_name(rows)
    out, missing, seen = [], {}, {}
    sec_meta = []
    for sec in SECTORS:
        picked, n_cand, miss = pick(rows, sec, by_name)
        if miss:
            missing[sec["id"]] = miss
        for r in picked:
            out.append({"stock": r["stock"], "name": r["name"], "market": r["market"],
                        "industry": r["industry"], "product": r["product"],
                        "sector": sec["id"], "sector_label": sec["label"],
                        "anchor": r["anchor"], "hits": r["hits"],
                        "pick_reason": r["pick_reason"]})
            seen.setdefault(r["stock"], []).append(sec["id"])
        sec_meta.append({"id": sec["id"], "label": sec["label"], "why": sec["why"],
                         "ind": sec.get("ind"), "kw": sec["kw"], "neg": sec.get("neg"),
                         "n_cand": n_cand, "n_sample": len(picked)})
    overlap = {k: v for k, v in seen.items() if len(v) > 1}
    if len(seen) > MAX_SAMPLE:
        raise RuntimeError("표본 %d사 — 상한 %d 초과(scout.md)" % (len(seen), MAX_SAMPLE))
    return {"cap": cap, "n_rows": len(out), "n_unique": len(seen), "sectors": sec_meta,
            "rows": out, "missing_anchors": missing, "overlap": overlap}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--sector")
    a = ap.parse_args()
    d = select_all()
    if a.sector:
        for r in d["rows"]:
            if r["sector"] == a.sector:
                print("%s %-16s %-6s %-30s %-34s %s" % (
                    r["stock"], r["name"][:16], r["market"][:6], (r["industry"] or "")[:30],
                    (r["product"] or "")[:34], r["pick_reason"]))
        return
    for s in d["sectors"]:
        print("%-10s %-22s 후보 %4d → 표본 %2d" % (s["id"], s["label"], s["n_cand"], s["n_sample"]))
        print("   ", ", ".join("%s%s" % (r["name"], "*" if r["anchor"] else "")
                               for r in d["rows"] if r["sector"] == s["id"]))
    print("\n표본 행 %d · 유니크 종목 %d (상한 %d)" % (d["n_rows"], d["n_unique"], MAX_SAMPLE))
    if d["missing_anchors"]:
        print("KIND에서 못 찾은 앵커:", d["missing_anchors"])
    if d["overlap"]:
        print("두 섹터 이상에 걸린 종목 %d개:" % len(d["overlap"]),
              dict(list(d["overlap"].items())[:10]))
    if a.write:
        write_asset("sample.json", d)
        print("→ assets/sample.json", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
