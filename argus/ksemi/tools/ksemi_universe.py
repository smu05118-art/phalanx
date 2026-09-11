#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ksemi_universe — 반도체 **장비·부품·공정서비스** 상장사 모집단(전수).

KIND 상장법인목록(업종·주요제품)만으로 만든다. DART는 두드리지 않는다 —
본문 근거로 승격/배제하는 일은 `ksemi_scan.py` 가 한다(스펙 ④).

## 왜 업종 단독 필터가 아닌가 (2026-09-11 KIND 실측)

스펙은 KIND 업종 `반도체 제조용 기계 제조업` 전 종목을 ①로 쓰라고 했지만 **그 업종명은
KIND에 없다**(전체 2,759행에 0건). KIND 업종은 KSIC 중분류 수준으로 굵고, 반도체 장비·
부품사는 여러 업종에 흩어져 있다:

    특수 목적용 기계 제조업                     169  원익IPS·주성·유진테크·테스·피에스케이·한미·HPSP·넥스틴…
    반도체 제조업                                74  하나머티리얼즈·미코 (+ 소자·팹리스가 같이 들어있다)
    전자부품 제조업                             136  월덱스 (+ MLCC·PCB·카메라모듈이 같이)
    측정, 시험, 항해, 제어 및 …; 광학기기 제외   31  케이씨텍·파크시스템스
    기타 비금속 광물제품 제조업                       티씨케이
    기타 금속 가공제품 제조업                         (부품 가공사)

그래서 **업종은 후보 문을 열 뿐**이고, 편입은 `주요제품` 어휘가 결정한다. 스펙의 경고가
그대로 들어맞는다 — '반도체'는 너무 넓다. 소자(메모리·파운드리)·팹리스(설계)·유통은
빼고 **장비·부품·공정 서비스**만 남긴다.

## 이 모듈이 내놓는 것은 **후보**다

여기서 나오는 155종목(2026-09-11)은 확정 모집단이 아니라 **관대하게 받은 후보**다.
KIND `주요제품`은 40자짜리 한 줄이라 '반도체 장비'와 '반도체 소재'를 가르기에 부족하다 —
그 판정은 `ksemi_scan.py` 가 정기보고서 II절 본문을 열어 근거와 함께 내린다(스펙 ④).
여기서 좁게 자르면 본문을 볼 기회조차 없어지므로, **의심스러우면 후보로 남긴다**.

| 값 | 뜻 |
|---|---|
| `지정` | 스펙 ③ 지정 종목(종목코드를 KIND 조회로 확인했다) — 배제 판정 대상 아님 |
| `어휘` | 후보 업종 + 주요제품에 장비·공정·부품 어휘가 있고 배제어가 없다 |
| `승격` | `ksemi_scan.py` 가 정기보고서 II절 본문 근거로 올렸다(여기서는 만들지 않는다) |

사용:
    python3 ksemi_universe.py                 # 표준출력에 목록
    python3 ksemi_universe.py --write         # assets/universe.json 갱신
    python3 ksemi_universe.py --why 042700    # 한 종목이 왜 들어왔나/빠졌나
"""
import argparse
import json
import os
import re
import sys

from ksemi_lib import KIND_URL, atomic_write, load_asset, parse_kind, write_asset

HERE = os.path.dirname(os.path.abspath(__file__))
UNIVERSE = os.path.join(HERE, "assets", "universe.json")
KIND_RAW = os.path.join(HERE, "assets", "kind_raw.html")

# 후보 업종 — 이 업종 안에서만 어휘를 본다. 업종 밖의 회사는 ③ 지정이나 ④ 승격으로 들어온다.
# 완전일치(부분일치 금지 — '기계장비 및 관련 물품 도매업'은 유통이라 넣지 않는다).
CAND_INDUSTRIES = (
    "특수 목적용 기계 제조업",
    "일반 목적용 기계 제조업",
    "반도체 제조업",
    "전자부품 제조업",
    "측정, 시험, 항해, 제어 및 기타 정밀기기 제조업; 광학기기 제외",
    "기타 비금속 광물제품 제조업",
    "기타 금속 가공제품 제조업",
    "사진장비 및 광학기기 제조업",
    "그외 기타 전문, 과학 및 기술 서비스업",   # 테스트·신뢰성 분석 서비스(네패스아크·큐알티)
    # 아래 셋은 소재사가 대부분이라 어휘로도 잘 안 걸러진다 — 후보로만 받고
    # 「장비·부품이냐 소재냐」는 `ksemi_scan.py` 가 본문을 열어 판정한다.
    "기타 화학제품 제조업",
    "1차 비철금속 제조업",
    "플라스틱제품 제조업",
)
# 2026-09-11 KIND 실측 행 수: 특수목적기계 169 · 반도체제조업 74 · 전자부품 136 ·
# 측정정밀기기 31 · 일반목적기계 51 · 기타화학 103 · 플라스틱 46 · 기타금속가공 28 ·
# 1차비철 23 · 그외기타전문과학 17 · 사진장비광학 12 · 기타비금속광물 9.

# 공정·장비·부품 어휘. 이 중 하나라도 `주요제품`에 있으면 반도체 밸류체인 후보.
# 낱말은 **공정 단계 사전(build_dicts.py)과 같은 출처**를 쓴다 — 여기서 고르고 거기서
# 단계로 접는다. 한 어휘를 양쪽에 따로 적으면 한쪽만 고쳐지는 날이 온다.
EQUIP_WORDS = (
    # 전공정 장비
    "증착", "CVD", "ALD", "PVD", "스퍼터", "에피", "epi", "식각", "에칭", "etch", "etcher",
    "애싱", "애셔", "스트립", "세정", "세척", "클리닝", "cleaning", "cleaner", "스크러버",
    "열처리", "어닐", "annealing", "RTP", "확산", "산화", "이온주입", "이온 주입", "임플란트",
    "포토", "트랙", "코터", "디벨로퍼", "EUV", "노광", "레티클", "마스크", "CMP", "연마",
    # 계측·검사
    "계측", "검사", "검측", "결함", "defect", "오버레이", "overlay", "CD-SEM", "현미경",
    "inspection", "메트롤로지", "измер",
    # 테스트·후공정
    "테스터", "테스트", "핸들러", "프로브", "probe", "번인", "burn-in", "본더", "본딩",
    "다이싱", "소잉", "몰딩", "레이저", "마커", "트리머", "리드프레임", "패키징", "패키지",
    "범핑", "TSV", "TC BONDER", "다이본더", "플립칩",
    # 이송·진공·유틸리티
    "이송", "반송", "진공", "펌프", "밸브", "챔버", "가스", "칠러", "CCSS", "C.C.S.S",
    "배관", "클린룸", "OHT", "스토커", "로드포트", "FOUP", "카세트", "웨이퍼 캐리어",
    # 부품·소재(장비 부분품)
    "정전척", "ESC", "샤워헤드", "히터", "쿼츠", "석영", "세라믹", "흑연", "graphite",
    "SiC", "실리콘부품", "실리콘 부품", "포커스링", "포커스 링", "전극", "링", "RF",
    "제너레이터", "코팅", "부품 세정", "정밀금형", "금형", "지그", "소켓", "프로브카드",
    # 공정 서비스
    "공정 서비스", "재생", "리퍼브", "부품재생",
    # 산업 지시어(위 어휘와 함께 볼 때만 의미가 있다)
    "웨이퍼", "wafer", "반도체 제조용", "반도체제조용", "반도체 장비", "반도체장비",
    "반도체 제조 장비", "전공정", "후공정",
)

# 배제어 — 있으면 뺀다. 소자사(고객 자신)·팹리스·유통·전방이 아닌 산업.
# `주요제품`에 이 낱말이 있고 EQUIP_WORDS 점수가 2 미만이면 배제한다(겸업사는 살린다).
DENY_WORDS = (
    "설계", "팹리스", "fabless", "IP", "설계자산", "라이선스",
    "도매", "유통", "상사", "무역", "임대", "리스",
    "메모리 모듈", "메모리모듈", "SSD", "USB", "모듈 제조", "카메라모듈", "카메라 모듈",
    "이차전지", "2차전지", "배터리", "전지", "태양광", "태양전지", "solar",
    "LED", "디스플레이 패널", "OLED 패널", "TV", "휴대폰", "스마트폰",
    "화장품", "의약", "제약", "바이오", "식품", "게임", "건설", "부동산",
    "자동차", "선박", "항공", "방산", "의료기기",
    "PCB", "인쇄회로", "MLCC", "커패시터", "콘덴서", "저항기", "인덕터",
    "커넥터", "케이블", "안테나", "필름", "접착", "포장", "용기",
)

# 배제어가 있어도 이 어휘가 있으면 살린다(반도체 장비 실질이 본문에 확인된 겸업사).
KEEP_WORDS = ("반도체 제조용", "반도체제조용", "반도체 장비", "반도체장비",
              "반도체 제조 장비", "웨이퍼", "전공정", "후공정", "프로브카드",
              "반도체 부품", "반도체용")

# 스펙 ③ 지정 — **종목코드는 KIND 조회로 확인했다**(2026-09-11).
# 값은 지정 사유(화면 커버리지에 그대로 실린다).
SEED = {
    "240810": "원익IPS — 전공정 증착(PE-CVD·ALD) 장비 (스펙 지정)",
    "036930": "주성엔지니어링 — ALD·CVD 증착 장비 (스펙 지정)",
    "084370": "유진테크 — LP-CVD 증착 장비 (스펙 지정)",
    "095610": "테스 — 화학증착·건식식각 장비 (스펙 지정)",
    "319660": "피에스케이 — 드라이스트립·드라이클리닝 (스펙 지정)",
    "031980": "피에스케이홀딩스 — Descum·Reflow (스펙 지정, 지주+장비)",
    "042700": "한미반도체 — 후공정 본더(TC Bonder)·금형 (스펙 지정)",
    "039030": "이오테크닉스 — 레이저 마커·레이저 응용장비 (스펙 지정)",
    "098460": "고영 — 3차원 납도포·반도체 검사장비 (스펙 지정)",
    "140860": "파크시스템스 — 원자현미경(계측) (스펙 지정)",
    "348210": "넥스틴 — 전공정 패턴결함 검사장비 (스펙 지정)",
    "322310": "오로스테크놀로지 — 오버레이 계측장비 (스펙 지정)",
    "281820": "케이씨텍 — CMP·세정 장비 (스펙 지정)",
    "079370": "제우스 — 세정·이송 장비 (스펙 지정)",
    "039440": "에스티아이 — CCSS·세정/식각 시스템 (스펙 지정)",
    "403870": "HPSP — 고압 수소 어닐링 장비 (스펙 지정)",
    "183300": "코미코 — 장비 부품 세정·코팅(공정 서비스) (스펙 지정)",
    "166090": "하나머티리얼즈 — 실리콘·세라믹 부품 (스펙 지정)",
    "064760": "티씨케이 — 고순도 흑연·SiC 부품 (스펙 지정)",
    "059090": "미코 — 반도체 부품(세라믹·정전척) (스펙 지정)",
    "101160": "월덱스 — 실리콘 전극·링 (스펙 지정)",
}

MIN_ROWS = 2000        # KIND 전체 목록이 이보다 적으면 응답이 깨진 것으로 본다
MIN_PICKED = 60        # 어휘 경로가 이보다 적으면 KIND 업종·주요제품 체계가 바뀐 것


def _hits(text, words):
    t = (text or "")
    tl = t.lower()
    out = []
    for w in words:
        if (w.lower() in tl) if w.isascii() else (w in t):
            out.append(w)
    return out


def judge(rec):
    """한 KIND 행의 편입 판정. 반환 (source|None, 근거 dict).

    `IP`·`링`처럼 짧은 어휘는 다른 낱말에 묻어 오탐한다(`LED 링`·`IP카메라`). 그래서
    점수로 보지 않고 **어휘 목록을 그대로 남겨** 커버리지 화면에서 사람이 검증할 수 있게 한다.
    """
    why = {"industry": rec["industry"], "product": rec["product"]}
    if rec["stock"] in SEED:
        why["seed"] = SEED[rec["stock"]]
        return "지정", why
    eq = _hits(rec["product"], EQUIP_WORDS)
    dn = _hits(rec["product"], DENY_WORDS)
    kp = _hits(rec["product"], KEEP_WORDS)
    why["equip"] = eq
    why["deny"] = dn
    why["keep"] = kp
    if rec["industry"] not in CAND_INDUSTRIES:
        why["reject"] = "후보 업종 아님"
        return None, why
    if not eq:
        why["reject"] = "주요제품에 장비·부품 어휘 없음"
        return None, why
    if dn and not kp and len(eq) < 2:
        why["reject"] = "배제어 %s (장비 어휘 %s 뿐)" % (",".join(dn), ",".join(eq) or "없음")
        return None, why
    return "어휘", why


def select(recs):
    """KIND 레코드 목록 → 모집단. 반환 레코드에 slug·source·why를 붙인다."""
    picked, rejected = [], []
    for r in recs:
        src, why = judge(r)
        d = dict(r)
        d["slug"] = r["stock"]
        d["why"] = why
        if src:
            d["source"] = src
            picked.append(d)
        else:
            rejected.append(d)
    got = {r["stock"] for r in picked}
    missing = sorted(set(SEED) - got)
    if missing:
        raise RuntimeError("지정 종목이 KIND 목록에 없다(상장폐지·사명변경?): %s" % missing)
    n_voc = sum(1 for r in picked if r["source"] == "어휘")
    if n_voc < MIN_PICKED:
        raise RuntimeError("어휘 경로가 %d종목뿐 — KIND 업종·주요제품 체계가 바뀌었다" % n_voc)
    picked.sort(key=lambda r: r["stock"])
    rejected.sort(key=lambda r: r["stock"])
    return picked, rejected


def fetch(write=False, use_cache=False):
    if use_cache and os.path.exists(KIND_RAW):
        with open(KIND_RAW, "rb") as f:
            raw = f.read()
    else:
        from kce_fetch import _get                   # 순환 임포트 회피
        raw = _get(KIND_URL)
        os.makedirs(os.path.dirname(KIND_RAW), exist_ok=True)
        with open(KIND_RAW, "wb") as f:              # 원문 캐시 보존(COMMON §0-4)
            f.write(raw)
    recs = parse_kind(raw)
    if len(recs) < MIN_ROWS:
        raise RuntimeError("KIND 목록이 %d행뿐 — 응답이 잘렸다" % len(recs))
    picked, rejected = select(recs)
    if write:
        write_asset("universe.json", {
            "source": KIND_URL, "kind_rows": len(recs), "n": len(picked),
            "rows": picked,
            # 배제는 **후보 업종 안에서 어휘로 떨어진 것만** 남긴다(전체 2,700행을
            # 다 실으면 커버리지 화면이 읽을 수 없다). 업종 밖은 ④ 승격의 몫.
            "rejected": [r for r in rejected if r["industry"] in CAND_INDUSTRIES],
        })
    return picked, rejected


def load():
    """캐시된 모집단(승격분 포함). 없으면 빈 목록."""
    if not os.path.exists(UNIVERSE):
        return []
    return load_asset("universe.json")["rows"]


def load_full():
    if not os.path.exists(UNIVERSE):
        return {"rows": [], "rejected": []}
    return load_asset("universe.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="assets/universe.json 갱신")
    ap.add_argument("--cache", action="store_true", help="캐시된 KIND 원문을 쓴다")
    ap.add_argument("--why", help="종목코드 하나의 판정 근거를 보인다")
    ap.add_argument("--rejected", action="store_true", help="후보 업종 안 배제분도 보인다")
    a = ap.parse_args()
    picked, rejected = fetch(write=a.write, use_cache=a.cache or bool(a.why))
    if a.why:
        for r in picked + rejected:
            if r["stock"] == a.why:
                print(json.dumps({"stock": r["stock"], "name": r["name"],
                                  "source": r.get("source"), "why": r["why"]},
                                 ensure_ascii=False, indent=1))
                return 0
        print("KIND 목록에 %s 없음" % a.why, file=sys.stderr)
        return 1
    for r in picked:
        print("%-7s %-4s %-22s %-30s %s"
              % (r["stock"], r["market"], r["name"][:22], r["industry"][:30],
                 r["product"][:40]))
    if a.rejected:
        print("--- 후보 업종 안 배제 ---")
        for r in rejected:
            if r["industry"] in CAND_INDUSTRIES:
                print("%-7s %-22s %s" % (r["stock"], r["name"][:22], r["why"]["reject"]))
    print("— %d종목 (지정 %d · 어휘 %d)"
          % (len(picked), sum(r["source"] == "지정" for r in picked),
             sum(r["source"] == "어휘" for r in picked)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
