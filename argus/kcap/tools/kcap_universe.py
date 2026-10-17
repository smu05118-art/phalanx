#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kcap_universe — 한국화학 캐파 탭의 모집단(전수) 후보.

KIND 상장법인목록(kce_universe.KIND_URL, 1요청)에서 네 겹으로 **후보**를 뽑는다. 후보는 모집단이 아니다 —
편입은 `kcap_capacity` 가 그 회사 정기보고서의 「원재료 및 생산설비」 절에서 **톤 단위 생산능력 표에
석유화학 품목**을 실제로 찾았을 때만 한다(fail-closed, 근거는 coverage 에 남는다).

  ① 업종(KIND 표준산업분류명 완전일치): 기초 화학물질 · 합성고무 및 플라스틱 물질 · 석유 정제품 · 화학섬유 제조업
  ② 주요제품 문구에 석유화학 어휘(한글 품목 + 영문 약어는 단어 경계)
  ③ 지정 시드(이름으로 KIND 에서 찾는다 — 종목코드를 기억으로 적지 않는다, COMMON.md)
  ④ 제외: 제품·업종 문구가 의약·반도체·디스플레이·2차전지·염료·시약·가스 등 비석유화학이 분명한 경우(사유 기록)

사용례:
  python3 kcap_universe.py --write      # assets/universe.json
"""
import re
import sys

from kcap_lib import load_asset, write_asset
from kce_universe import KIND_URL, parse_kind
from kce_fetch import _get

INDUSTRIES = {"기초 화학물질 제조업", "합성고무 및 플라스틱 물질 제조업", "석유 정제품 제조업", "화학섬유 제조업"}
VOCAB = re.compile(
    r"에틸렌|프로필렌|부타디엔|벤젠|톨루엔|자일렌|파라자일렌|스티렌|폴리에틸렌|폴리프로필렌|폴리스티렌|폴리염화비닐|합성고무|합성수지|"
    r"가성소다|카프로락탐|나일론|석유화학|나프타|페놀|아세톤|에폭시|폴리올|우레탄|테레프탈|에틸렌글리콜|"
    r"(?<![A-Za-z])(HDPE|LDPE|LLDPE|PVC|ABS|EPS|MEG|TPA|PTA|BPA|TDI|MDI|PPG|SBR|NBR|EDC|VCM|MMA|VAM|NCC|PX|SM|PE|PP|PS|PO|BD|BR|EG|AN)(?![A-Za-z])")
NEG = re.compile(
    r"의약|제약|화장품|소프트웨어|반도체|디스플레이|OLED|LCD|2차전지|이차전지|전해액|양극재|동박|자동차|건설|부동산|리츠|금융|게임|바이오|진단|"
    r"식품|음료|의류|신발|도료|잉크|촉매|용기|포장|전자재료|세제|비누|향료|방사성|농약|비료|살충|염료|시약|가스|산화아연|드라이아이스|"
    r"탄산칼륨|카바이드|안료|발포제|사카린|마스크|필터|가발|타이어코드|보냉재|탄소섬유|와이어|강선|강관|파일|강교|콘크리트|윤활유|그리스|왁스")
# 지정 시드 — 이름 → 사유. 업종·어휘 그물에 안 걸리는 석유화학 실질 회사. 코드는 KIND 에서 이름으로 찾는다.
SEED = {
    "코오롱인더": "화학섬유 업종이나 석유수지·필름·화학 부문 보유",
    "태광산업": "PTA·AN 생산(화학섬유 업종)",
    "SKC": "PO·PG·SM(기타 화학제품 업종)",
    "롯데정밀화학": "가성소다·ECH·암모니아 계열(염소체인)",
    "효성화학": "PP·TPA·NF3 — KIND 주요제품 '-' 로 비어 있음",
    "효성티앤씨": "PTMEG·스판덱스(화학섬유 업종)",
    "티케이지휴켐스": "휴켐스(2026 사명 변경) — DNT·MNB·질산, TDI/MDI 원료(기타 화학제품 업종)",
    "KPX케미칼": "PPG·폴리올(우레탄 체인)",
    "금양": "발포제 — 제외 어휘에 걸리나 석유화학 원료 사용",
    "애경케미칼": "무수프탈산·가소제·PA",
    "이수화학": "알킬벤젠·노말파라핀(벤젠 체인)",
    "한솔케미칼": "과산화수소·라텍스",
    "SK케미칼": "PETG·PET 수지(폴리에스터)",
    "티케이케미칼": "PET 수지·폴리에스터·스판덱스",
    "대한유화": "NCC·PE·PP 순수 석유화학",
    "S-Oil": "정유·PX·PP/PO(석유화학부문)",
    "SK이노베이션": "정유·석유화학(SK지오센트릭)",
    "GS": "GS칼텍스(정유·석유화학 지분)",
    "동성케미컬": "폴리우레탄·EPS",
    "국도화학": "에폭시수지(BPA·ECH 다운스트림)",
    "PKC": "가성소다·합성염산(염소체인)",
    "유니드": "가성칼륨·탄산칼륨(염소·알칼리) — 제외 어휘(탄산칼륨)보다 시드 우선",
    "OCI": "타르·카본블랙·무수프탈산(석탄화학) — 폴리실리콘 어휘 제외보다 시드 우선",
    "그린케미칼": "에탄올아민·옥탄올(EO 다운스트림)",
    "HDC현대EP": "PP·PE 컴파운드",
    "삼양사": "EP·화학(BPA·PC 원료)",
    "케이씨씨": "KCC — PVC·실리콘·도료 (제외 어휘 '도료'보다 시드 우선)",
    "롯데케미칼": "NCC·PE·PP·MEG·BTX·PIA — 기준 회사",
    "LG화학": "NCC·PVC·ABS·BPA·아크릴 — 기준 회사",
    "한화솔루션": "LDPE·LLDPE·PVC·CA(가성소다)",
    "금호석유화학": "합성고무·합성수지·BD·라텍스·페놀/BPA(금호피앤비)",
}


def _norm_name(s):
    return re.sub(r"[\s(주)㈜·,.]+", "", (s or "")).upper()


def candidates(recs):
    """KIND 행 → 후보 행(stock·name·market·industry·product·why[]·excluded 사유)."""
    by_name = {_norm_name(r["name"]): r for r in recs}
    out = {}

    def add(r, why):
        row = out.setdefault(r["stock"], {"stock": r["stock"], "name": r["name"], "market": r.get("market"),
                                            "industry": r["industry"], "product": r.get("product") or "", "why": [], "seed": False})
        row["why"].append(why)
    for r in recs:
        if r["industry"] in INDUSTRIES:
            add(r, "업종 " + r["industry"])
        if VOCAB.search(r.get("product") or ""):
            add(r, "주요제품 어휘")
    for name, reason in SEED.items():
        r = by_name.get(_norm_name(name))
        if r is None:
            # 부분 일치(이름 앞부분) — 'S-Oil' vs 'S-Oil', 'LG화학' 등
            hits = [v for k, v in by_name.items() if k.startswith(_norm_name(name))]
            r = hits[0] if len(hits) == 1 else None
        if r is None:
            continue
        add(r, "지정 시드: " + reason)
        out[r["stock"]]["seed"] = True
    rows = []
    for row in out.values():
        text = row["product"] + " " + row["industry"]
        neg = NEG.search(text)
        if neg and not row["seed"] and not any(w.startswith("업종") and VOCAB.search(row["product"]) for w in row["why"]):
            row["excluded"] = "제외 어휘 '%s' (시드·업종+어휘 둘 다 아님)" % neg.group(0)
        else:
            row["excluded"] = None
        rows.append(row)
    rows.sort(key=lambda r: (r["excluded"] is not None, r["name"]))
    return rows


def fetch(write=False):
    recs = parse_kind(_get(KIND_URL))
    rows = candidates(recs)
    data = {"source": KIND_URL, "n_kind": len(recs), "n_candidates": sum(1 for r in rows if not r["excluded"]),
            "n_excluded": sum(1 for r in rows if r["excluded"]), "rows": rows,
            "rules": {"industries": sorted(INDUSTRIES), "vocab": VOCAB.pattern, "neg": NEG.pattern, "seed": SEED}}
    if write:
        write_asset("universe.json", data)
    return data


def load():
    return load_asset("universe.json")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    d = fetch(write="--write" in argv)
    print("KIND %d → 후보 %d (제외 %d)" % (d["n_kind"], d["n_candidates"], d["n_excluded"]))
    for r in d["rows"]:
        if not r["excluded"]:
            print(" ", r["stock"], r["name"], "|", r["industry"], "|", "; ".join(r["why"])[:70])
    if "--show-excluded" in argv:
        for r in d["rows"]:
            if r["excluded"]:
                print("  ✗", r["stock"], r["name"], "|", r["excluded"])


if __name__ == "__main__":
    main()
