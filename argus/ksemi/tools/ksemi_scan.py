#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ksemi_scan — 모집단 후보를 **정기보고서 II절 본문으로** 판정한다(스펙 ksemi.md ④).

## 왜 이 모듈이 필요한가

`ksemi_universe.py` 가 내놓는 154종목은 KIND `주요제품` 한 줄(40자)로 관대하게 받은
**후보**다. 그 한 줄로는 갈라지지 않는 것이 셋 있다.

  · 스톰테크 `정수기 피팅, 밸브, 파우셋 등 부품` — '밸브' 하나로 걸렸다. 반도체와 무관하다.
  · 삼양엔씨켐 `반도체 포토레지스트용 기초화합물(KrF PR용 소재…)` — '포토'·'RF'로 걸렸다.
    반도체 밸류체인이지만 **소모 소재**라 장비 탭의 대상이 아니다.
  · 원익IPS `반도체 제조용 기계` — 맞다. 그런데 이 문구만으로는 어느 공정인지 모른다.

그래서 후보의 II절 본문을 실제로 열어 **장비·공정 낱말과 그 주변 문장**을 근거로 남기고,
장비·부품·부분품·공정서비스 회사인지 판정한다. 스펙의 경고("'반도체'는 너무 넓다")가
여기서 규칙이 된다 — 소자사(메모리·파운드리)·팹리스·유통·소모 소재는 뺀다.

## 판정 등급

| 등급 | 뜻 |
|---|---|
| `편입` | 본문에 반도체 장비/장비부품/공정서비스 실질이 확인됐다 |
| `배제` | 소자사·팹리스·유통·소모 소재·타산업. **왜 배제인지 원문 인용(`quote`)을 남긴다** |
| `보류` | 본문이 애매하거나 II절을 못 찾았다 — 사람이 봐야 한다 |
| `오류` | 접근 실패. **배제가 아니다.** 다시 돌리면 빠진 것만 받는다 |

`source == "지정"`(스펙 ③ 21종목)은 판정 대상이 아니다 — 무조건 `편입`이지만 본문 근거는
같이 모은다(공정 단계 분류에 쓴다). 수집이 실패해도 등급은 `편입`이고 `ok=false`로 남는다.

## 판정 규칙 (원문에서 확인한 것만)

숫자 임계값은 **아래 실측으로 잡았다**(2026-09-11, 2026Q2 반기보고서 본문):

  · 원익IPS(240810, rcpNo 20260814001845) — 반도체 언급 다수, 증착(ALD·CVD)·식각 장비 낱말.
  · 한미반도체(042700) — `TC BONDER`·`다이본더` 등 후공정 장비 낱말 + HBM 문맥.
  · 하나머티리얼즈(166090) — `실리콘 부품`·`Focus Ring` 등 장비 부분품 낱말. 다만 KIND
    문구에 `특수가스`가 함께 있어(겸업) 소재 낱말도 같이 잡힌다 → 부품 쪽이 더 세면 편입.
  · 삼양엔씨켐(482630) — `포토레지스트`·`Wet Chemical` 등 소재 낱말이 장비 낱말을 압도한다.
  · 스톰테크(352090) — 반도체 언급이 거의 없고 정수기·냉온수기 낱말만 나온다.

규칙(순서대로, fail-closed):
  0. II절을 못 열었으면 `오류`(수집 실패) 또는 `보류`(절이 없다). **조용히 배제하지 않는다.**
  1. 반도체 문맥 낱말(반도체·웨이퍼·Fab…)이 `SEMI_MIN` 미만이면 `배제`(타산업).
  2. 다른 산업 낱말(디스플레이·이차전지·태양광…)이 반도체의 `OTHER_RATIO` 배를 넘으면 `배제`.
  3. 소자·팹리스 낱말이 세고 장비 낱말이 약하면 `배제`(고객 업종 자신).
  4. 소모 소재 낱말이 장비·부품 낱말보다 세면 `배제`(소재).
  5. 유통 낱말만 있고 장비 낱말이 약하면 `배제`(유통).
  6. 장비·부품·서비스 낱말 점수가 `EQUIP_IN` 이상이면 `편입`, `EQUIP_HOLD` 이상이면 `보류`.
  7. 그 밖은 `배제`(장비 실질 낱말 없음) — 인용을 남긴다.

## 원문 캐시 (COMMON.md §0-4)

`assets/cache/` 아래에 절 HTML을 그대로 남긴다. 파서가 자라면 **재수집 없이** 다시 뽑는다
(`--rejudge`). 파일명 규칙:

    assets/cache/sec_<rcpNo>_<key>.html      절 HTML 원문 (key: overview|products|sales|etc|ii)
    assets/cache/meta_<stock>_<quarter>.json 어느 보고서의 어느 절을 받았나(rcpNo·제목·절 목록)

캐시 디렉터리는 커밋하지 않는다(원문 수백 MB). 5MB를 넘는 절은 캐시하지 않고 `big=true`로
남긴다 — 다음 실행에서 다시 받는다. **실패는 캐시하지 않는다.**

사용:
    python3 ksemi_scan.py --only 240810,042700,166090,482630,352090 --write
    python3 ksemi_scan.py --write [--quarter 2026Q2]      # 전수
    python3 ksemi_scan.py --rejudge --write               # 규칙만 바꿔 캐시로 재판정(DART 무접속)
    python3 ksemi_scan.py --only 482630 --show            # 한 종목 근거를 사람이 읽는 형태로
"""
import argparse
import html as _html
import json
import os
import re
import sys
import time
from collections import Counter

from ksemi_lib import (ASSETS, atomic_write, has_asset, latest_quarter, load_asset,
                       report_kind, write_asset)
import ksemi_fetch as kfetch                       # 인코딩 판정을 덮어쓴 수집기(코스닥 rcpNo[8]=='9')
from kce_fetch import find_sections, parallel, pick_report   # 산업 무관 층 — 새로 만들지 않는다
from kce_probe import report_window
import ksemi_universe

CACHE = os.path.join(ASSETS, "cache")
MAX_CACHE_BYTES = 5 * 1024 * 1024        # COMMON: 5MB 넘는 파일을 만들지 않는다

# 읽을 절. II절은 회사마다 소제목 번호가 다르므로 **제목 부분 문자열**로 찾는다.
# `기타 참고사항`에 산업 특성·공정 설명·고객이 가장 많이 적혀 있어 빼면 근거가 얕아진다.
SECTIONS = [
    ("overview", ["사업의 개요"]),
    ("products", ["주요 제품 및 서비스", "주요 제품", "주요제품", "주요 제품 및 원재료"]),
    ("sales", ["매출 및 수주상황", "매출실적", "수주상황"]),
    ("etc", ["기타 참고사항"]),
]
# 위 소제목이 하나도 없는 구형·간이 서식은 II절 통째로 받는다(fail-closed 대신 폴백).
SECTION_FALLBACK = [("ii", ["사업의 내용"])]


# ── 낱말 규칙 ────────────────────────────────────────────────────────────────
# (key, stage, strength, regex). strength 2 = 그 낱말만으로 장비/부품/서비스 실질,
# 1 = 문맥이 필요한 넓은 낱말('증착'·'검사'는 소재사·소자사 본문에도 나온다).
# 공정 단계 이름은 스펙 ksemi.md §산업특성4의 12단계를 그대로 쓴다 — build_dicts.py가
# 이 이름으로 확정 분류를 만든다. 여기서는 **힌트만** 낸다.
_EQUIP_RULES_SRC = [
    # 일반 — '반도체 장비'라고 본문이 직접 말하는 경우
    ("반도체장비", None, 2, r"반도체\s*(?:제조용?\s*)?장비|반도체장비|반도체\s*제조\s*장비|"
                            r"전공정\s*장비|후공정\s*장비|반도체\s*생산\s*장비|반도체\s*제조\s*설비|"
                            r"반도체\s*장비용|반도체\s*공정\s*장비"),
    # 증착
    ("증착장비", "증착", 2, r"\bALD\b|\bCVD\b|\bPVD\b|MOCVD|PECVD|스퍼터(?:링|ing)?|에피택(?:셜|샬)|"
                            r"증착\s*(?:장비|설비|장치)|박막\s*증착|원자층\s*증착"),
    ("증착", "증착", 1, r"증착|에피\b|Epitax"),
    # 식각
    ("식각장비", "식각", 2, r"식각\s*(?:장비|설비|장치)|에처|Etcher|건식\s*식각|습식\s*식각|드라이\s*에칭|"
                            r"애셔|애싱|Asher|드라이\s*스트립|Dry\s*Strip|플라즈마\s*식각"),
    ("식각", "식각", 1, r"식각|에칭|\bEtch"),
    # 세정
    ("세정장비", "세정", 2, r"세정\s*(?:장비|설비|장치|시스템)|웨이퍼\s*세정|부품\s*세정|매엽식|"
                            r"스핀\s*세정|Wet\s*Station|싱글\s*웨이퍼\s*세정|스크러버|Scrubber"),
    ("세정", "세정", 1, r"세정|세척|클리닝|Cleaning"),
    # 열처리
    ("열처리장비", "열처리", 2, r"\bRTP\b|급속\s*열처리|어닐(?:링)?|Anneal(?:ing)?|확산로|산화로|"
                                r"퍼니스|Furnace|고압\s*수소|열처리\s*장비"),
    ("열처리", "열처리", 1, r"열처리|열공정"),
    # 이온주입
    ("이온주입", "이온주입", 2, r"이온\s*주입|이온주입|임플란터|Implanter|Ion\s*Implant"),
    # 포토
    ("포토장비", "포토", 2, r"노광\s*(?:장비|기)|스테퍼|Stepper|트랙\s*장비|코터|Coater|디벨로퍼|"
                            r"Developer|\bEUV\b|포토\s*장비|레티클|Reticle|포토마스크|"
                            r"포토\s*공정\s*장비"),
    ("포토", "포토", 1, r"노광|포토\s*공정|리소그래?피|Litho"),
    # CMP
    ("CMP장비", "CMP", 2, r"\bCMP\b|화학적\s*기계\s*연마|연마\s*(?:장비|설비)|웨이퍼\s*연마|"
                          r"폴리싱\s*장비|Polisher"),
    # 계측·검사
    ("계측검사장비", "계측검사", 2, r"계측\s*(?:장비|설비|시스템)|검사\s*(?:장비|설비|시스템|기)|"
                                    r"결함\s*검사|패턴\s*검사|오버레이|Overlay|CD-?SEM|원자현미경|"
                                    r"\bAFM\b|웨이퍼\s*검사|Inspection|Metrology|메트롤로지|"
                                    r"3\s*차원\s*측정|X-?ray\s*검사|초음파\s*검사"),
    ("계측검사", "계측검사", 1, r"계측|검측|결함|Defect"),
    # 이송·진공
    ("이송진공장비", "이송진공", 2, r"진공\s*펌프|\bOHT\b|스토커|Stocker|\bFOUP\b|로드\s*포트|LoadPort|"
                                    r"웨이퍼\s*이(?:송|재)|반송\s*(?:장비|시스템)|클러스터\s*툴|"
                                    r"트랜스퍼\s*모듈|게이트\s*밸브|진공\s*밸브|진공\s*챔버|"
                                    r"드라이\s*펌프|터보\s*분자\s*펌프|웨이퍼\s*카세트|\bCCSS\b|C\.C\.S\.S"),
    ("이송진공", "이송진공", 1, r"이송|반송|진공"),
    # 테스트
    ("테스트장비", "테스트", 2, r"테스트\s*핸들러|핸들러|Handler|테스터|Tester|프로브\s*카드|프로브카드|"
                                r"Probe\s*Card|번인|Burn-?in|테스트\s*소켓|Test\s*Socket|"
                                r"웨이퍼\s*프로버|프로버|Prober|검사\s*소켓"),
    ("테스트", "테스트", 1, r"테스트\s*공정|번인\s*공정|최종\s*검사"),
    # 패키징·후공정 장비
    ("후공정장비", "패키징후공정", 2, r"다이\s*본더|다이본더|와이어\s*본더|플립칩\s*본더|TC\s*BONDER|"
                                      r"본딩\s*(?:장비|기)|\b본더\b|Bonder|다이싱|소잉|Sawing|"
                                      r"몰딩\s*장비|레이저\s*마(?:커|킹)|레이저\s*가공\s*장비|"
                                      r"범핑|\bTSV\b|비전\s*플레이스먼트|Sorter|쏘팅\s*장비|"
                                      r"그라인더|Grinder|디플럭서|사이드\s*뷰"),
    ("후공정", "패키징후공정", 1, r"패키징|후공정|\bHBM\b|어드밴스드\s*패키지"),
    # 장비 부분품 — 소모품이지만 **장비의 부분품**이다(소재와 가르는 축)
    ("장비부분품", "부품소재", 2, r"정전척|\bESC\b|Electrostatic\s*Chuck|샤워\s*?헤드|Shower\s*Head|"
                                  r"포커스\s*?링|Focus\s*Ring|엣지\s*?링|Edge\s*Ring|쿼츠|Quartz|"
                                  r"석영\s*(?:유리|제품|부품)|실리콘\s*부품|실리콘부품|\bSiC\s*(?:링|부품|소재)|"
                                  r"CVD\s*SiC|서셉터|Susceptor|세라믹\s*부품|히터\s*블록|세라믹\s*히터|"
                                  r"RF\s*(?:제너레이터|Generator|매처|Matcher)|공정\s*챔버|챔버\s*부품|"
                                  r"장비\s*부품|장비용\s*부품|부분품|정밀\s*세라믹|고순도\s*흑연|"
                                  r"등방성\s*흑연|실리콘\s*전극|카본\s*링"),
    ("부품", "부품소재", 1, r"챔버|세라믹|흑연|Graphite"),
    # 공정 서비스 — 코미코형(장비 부품 세정·코팅)
    ("공정서비스", "부품소재", 2, r"부품\s*세정|세정\s*및\s*코팅|코팅\s*서비스|재생\s*(?:사업|서비스|부품)|"
                                  r"리퍼비시|Refurbish|용사\s*코팅|플라즈마\s*용사|아노다이징|"
                                  r"세라믹\s*코팅|부품\s*재생"),
]

# 소모 소재 — 반도체 밸류체인이지만 **장비 부분품이 아니다**. 스펙이 배제하라고 못 박았다.
_MATERIAL_SRC = r"""포토레지스트|Photo\s*resist|Photoresist|감광액|\bPR\s*(?:소재|용)|
전구체|Precursor|프리커서|슬러리|Slurry|식각액|현상액|박리액|세정액|스트리퍼|Stripper|
씬너|Thinner|고순도\s*가스|특수\s*가스|산업용\s*가스|삼불화질소|\bNF3\b|\bWF6\b|
블랭크\s*마스크|Blank\s*Mask|스퍼터링\s*타겟|Sputtering\s*Target|CMP\s*(?:패드|슬러리)|
에폭시\s*몰딩|\bEMC\b|본딩\s*와이어|솔더\s*볼|리드\s*프레임|Lead\s*Frame|
웨이퍼\s*(?:제조|가공)용\s*소재|실리콘\s*웨이퍼\s*제조|다이\s*어태치|접착\s*필름|
기초\s*화합물|Wet\s*Chemical|전자재료|전자\s*소재|반도체\s*소재|반도체용\s*화학|
케미칼|Chemical\s*(?:사업|부문)|가스\s*충전|온사이트\s*가스"""

# 소자사·팹리스 — 장비의 **고객**이다. 스펙 ④가 명시적으로 뺀다.
_DEVICE_SRC = r"""팹리스|Fabless|반도체\s*설계|\bIC\s*설계|시스템\s*반도체\s*설계|SoC\s*설계|
설계\s*자산|설계자산|Design\s*House|디자인\s*하우스|IP\s*라이선스|
파운드리\s*(?:사업|서비스|공정|매출)|웨이퍼\s*파운드리|위탁\s*생산\s*서비스|
메모리\s*반도체\s*(?:생산|제조|양산)|D램\s*(?:생산|제조|양산)|낸드\s*(?:생산|제조|양산)|
\bOSAT\b|패키징\s*및\s*테스트\s*(?:서비스|외주)|반도체\s*후공정\s*(?:서비스|외주)|
이미지\s*센서\s*설계|디스플레이\s*구동\s*칩|\bDDI\b|전력\s*반도체\s*(?:생산|제조)|
MCU\s*(?:설계|개발)|칩\s*설계"""

# 유통 — 제조가 아니다.
_DIST_SRC = r"""장비\s*(?:유통|도매|수입\s*판매)|수입\s*판매|총판|딜러|에이전시|무역\s*업|
상사\s*(?:부문|사업)|국내\s*독점\s*판매|판매\s*대리(?:점|권)"""

# 반도체 문맥 — 이 낱말이 거의 없으면 반도체 회사가 아니다.
_SEMI_SRC = r"반도체|웨이퍼|Wafer|Semiconductor|\bFab\b|팹\b|\bIDM\b|소자\s*업체|파운드리"

# 다른 산업 — 반도체 낱말보다 압도적으로 많으면 그 산업 회사다.
_OTHER_FIELDS = {
    "디스플레이": r"디스플레이|\bOLED\b|\bLCD\b|\bLED\b|패널\s*(?:장비|공정|제조)|\bBLU\b",
    "이차전지": r"이차전지|2차전지|배터리|전지\s*(?:장비|공정|제조)|전극\s*조립|양극재|음극재",
    "태양광": r"태양광|태양전지|\bPV\s*(?:모듈|셀)",
    "자동차": r"자동차|차량용|완성차|\bOEM\s*부품|내연기관",
    "의료바이오": r"의료기기|의약품|제약|바이오\s*(?:의약|시밀러)|진단\s*키트",
    "기계일반": r"공작기계|사출성형기|농기계|트랙터|건설기계|정수기|냉온수기|보일러",
}

_FLAGS = re.I | re.X


def _rx(src):
    return re.compile(re.sub(r"\s*\n\s*", "", src) if "\n" in src else src, _FLAGS)


EQUIP_RULES = [(k, st, s, re.compile(p, re.I)) for k, st, s, p in _EQUIP_RULES_SRC]
MATERIAL_RX = _rx(_MATERIAL_SRC)
DEVICE_RX = _rx(_DEVICE_SRC)
DIST_RX = _rx(_DIST_SRC)
SEMI_RX = re.compile(_SEMI_SRC, re.I)
OTHER_RX = {k: re.compile(v, re.I) for k, v in _OTHER_FIELDS.items()}

# 고객 — 소자사·팹·장비 OEM. 짧은 약칭(TEL·ASE)은 오탐이 심해 넣지 않는다.
CUSTOMER_NAMES = [
    ("삼성전자", r"삼성전자|Samsung\s*Electronics"),
    ("SK하이닉스", r"SK\s*하이닉스|에스케이\s*하이닉스|SK\s*Hynix|하이닉스"),
    ("마이크론", r"마이크론|Micron"),
    ("TSMC", r"\bTSMC\b|대만적체전로|티에스엠씨"),
    ("인텔", r"인텔\b|\bIntel\b"),
    ("키오시아", r"키오시아|Kioxia|도시바\s*메모리"),
    ("웨스턴디지털", r"웨스턴\s*디지털|Western\s*Digital|\bWDC\b"),
    ("SMIC", r"\bSMIC\b|중신국제|중심국제"),
    ("YMTC", r"\bYMTC\b|장강\s*메모리|양쯔\s*메모리"),
    ("CXMT", r"\bCXMT\b|창신\s*메모리|Changxin"),
    ("화홍반도체", r"화홍|Hua\s*Hong"),
    ("글로벌파운드리", r"글로벌\s*파운드리|GlobalFoundries|\bGF\b"),
    ("UMC", r"\bUMC\b"),
    ("DB하이텍", r"DB\s*하이텍|디비\s*하이텍"),
    ("앰코", r"앰코|Amkor"),
    ("ASML", r"\bASML\b"),
    ("어플라이드머티리얼즈", r"Applied\s*Materials|어플라이드\s*머티리얼|\bAMAT\b"),
    ("램리서치", r"Lam\s*Research|램\s*리서치|램리서치"),
    ("도쿄일렉트론", r"Tokyo\s*Electron|도쿄\s*일렉트론"),
    ("KLA", r"\bKLA\b"),
    ("삼성디스플레이", r"삼성\s*디스플레이"),
    ("LG디스플레이", r"LG\s*디스플레이|엘지\s*디스플레이"),
    ("BOE", r"\bBOE\b"),
]
CUSTOMER_RX = [(n, re.compile(p, re.I)) for n, p in CUSTOMER_NAMES]
# 익명 고객 — 원익IPS 주석이 'A사·B사'로 적는다(PROGRESS §1-4에서 실측). 익명이면 익명이라 적는다.
ANON_RX = re.compile(r"(?<![A-Za-z0-9가-힣])([A-Z])\s?사(?![업무회원가-힣A-Za-z])")

# ── 임계값 (위 docstring의 실측으로 잡았다) ──────────────────────────────────
SEMI_MIN = 8           # 반도체 문맥 낱말이 이보다 적으면 반도체 회사가 아니다(스톰테크 0~2)
OTHER_RATIO = 2.5      # 다른 산업 낱말이 반도체의 이 배를 넘으면 그 산업 회사
EQUIP_IN = 12          # 장비·부품·서비스 점수 — 편입
EQUIP_HOLD = 4         # 이 사이는 보류(사람이 본다)
DEVICE_MARGIN = 1.2    # 소자·팹리스 점수가 장비 점수의 이 배를 넘으면 고객 업종
MATERIAL_MARGIN = 1.0  # 소재 점수가 장비 점수보다 크면 소재사
RULE = ("반도체 낱말 ≥%d · 타산업 낱말 < %.1f배 · 소자·팹리스 점수 < 장비×%.1f · "
        "소재 점수 < 장비×%.1f · 장비 점수 ≥%d → 편입(≥%d 보류)"
        % (SEMI_MIN, OTHER_RATIO, DEVICE_MARGIN, MATERIAL_MARGIN, EQUIP_IN, EQUIP_HOLD))


# ── 본문 → 텍스트·인용 ───────────────────────────────────────────────────────

def text_of(raw):
    """절 HTML → 평문. 표 셀 사이에 공백을 넣어 낱말이 붙어버리지 않게 한다.

    엔티티를 풀지 않으면 인용에 `&quot;`가 그대로 실려 사람이 읽기 어렵다(스톰테크 실측).
    태그를 먼저 걷고 나서 풀어야 `&lt;script&gt;`가 태그로 되살아나지 않는다.
    """
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    return re.sub(r"[ \t\xa0　]+", " ", s)


_SENT_END = re.compile(r"[.。!?]\s|다\.\s|니다\.\s")


def quote_at(text, start, end, want=170, lo=60, hi=200):
    """낱말 위치 주변 문장 인용(60~200자). 사람이 검증할 수 있어야 근거다."""
    if not text:
        return ""
    pad = max(0, (want - (end - start)) // 2)
    a, b = max(0, start - pad), min(len(text), end + pad)
    # 앞쪽은 문장 경계로 당긴다(문장 중간에서 시작하면 읽히지 않는다)
    m = None
    for m in _SENT_END.finditer(text, a, start):
        pass
    if m and start - m.end() < want:
        a = m.end()
    if b - a < lo:
        b = min(len(text), a + lo)
    if b - a > hi:
        b = a + hi
    return re.sub(r"\s+", " ", text[a:b]).strip()


def _hits(text, rules):
    """[(key, stage, strength, rx)] → 매칭 정보. 표면형(실제 나온 낱말)을 그대로 남긴다."""
    out = []
    for key, stage, strength, rx in rules:
        ms = list(rx.finditer(text))
        if not ms:
            continue
        forms = Counter(re.sub(r"\s+", " ", m.group(0)) for m in ms)
        out.append({"key": key, "stage": stage, "strength": strength,
                    "term": forms.most_common(1)[0][0], "n": len(ms),
                    "at": (ms[0].start(), ms[0].end())})
    return out


def _rx_hits(text, rx, cap=6):
    """정규식 하나의 점수·표면형·첫 위치. 점수는 낱말마다 cap으로 잘라 한 낱말 반복에 휘둘리지 않게."""
    ms = list(rx.finditer(text))
    if not ms:
        return 0, {}, None
    forms = Counter(re.sub(r"\s+", " ", m.group(0)) for m in ms)
    score = sum(min(n, cap) for n in forms.values())
    return score, dict(forms.most_common(6)), (ms[0].start(), ms[0].end())


def find_customers(text):
    """본문에 등장한 고객 이름. 익명('A사')이면 그렇게 적는다(추정하지 않는다)."""
    out = []
    for name, rx in CUSTOMER_RX:
        if rx.search(text):
            out.append(name)
    anon = sorted({m.group(1) + "사" for m in ANON_RX.finditer(text)})
    # 'A사'가 20개 넘게 잡히면 문장 조각 오탐이다 — 익명 고객은 보통 A~E사 몇 개다.
    if len(anon) <= 8:
        out += anon
    return out


# ── 수집 ─────────────────────────────────────────────────────────────────────

def _meta_path(stock, quarter):
    return os.path.join(CACHE, "meta_%s_%s.json" % (stock, quarter))


def _sec_path(rcp, key):
    return os.path.join(CACHE, "sec_%s_%s.html" % (rcp, key))


def collect_one(rec, quarter, force=False, cache_only=False):
    """한 종목의 II절 본문을 모은다. 반환 {ok, rcpNo, title, quarter, texts{key: 평문}, note}.

    예외를 밖으로 던지지 않는다 — 한 종목 실패가 전수를 죽이면 안 된다(caller가 `오류`로 담는다).
    캐시가 있으면 네트워크를 두드리지 않는다. **실패는 캐시하지 않는다.**
    """
    st = rec["stock"]
    out = {"stock": st, "quarter": quarter, "ok": False, "note": "",
           "rcpNo": None, "title": "", "texts": {}, "cached": False}
    mp = _meta_path(st, quarter)
    if os.path.exists(mp) and not force:
        try:
            with open(mp, encoding="utf-8") as f:
                meta = json.load(f)
            texts, missing = {}, []
            for key, s in (meta.get("sections") or {}).items():
                p = _sec_path(meta["rcpNo"], key)
                if not os.path.exists(p):
                    missing.append(key)
                    continue
                with open(p, encoding="utf-8") as f:
                    texts[key] = text_of(f.read())
            if texts and not missing:
                out.update({"ok": True, "rcpNo": meta["rcpNo"], "title": meta.get("title", ""),
                            "quarter": meta.get("quarter", quarter), "texts": texts,
                            "cached": True, "note": meta.get("note", "")})
                return out
        except Exception as e:                       # 깨진 캐시는 무시하고 다시 받는다
            out["note"] = "캐시 손상(%s)" % str(e)[:60]
    if cache_only:
        out["note"] = "캐시 없음 — 재수집 필요"
        return out

    try:
        q = quarter
        start, end = report_window(q)
        # 종목코드는 DART 검색에서 정확일치 키다(동명 회사 혼선 없음 — kce_probe에서 확인).
        reports = pick_report(kfetch.search_reports(st, start, end, report_kind(q)), q)
        if not reports and int(q[5]) != 4:
            # 코넥스·일부 코스닥은 분기·반기보고서를 내지 않는다 — 사업보고서로 폴백.
            q2 = "%dQ4" % (int(q[:4]) - 1)
            start, end = report_window(q2)
            r2 = pick_report(kfetch.search_reports(st, start, end, report_kind(q2)), q2)
            if r2:
                reports, q = r2, q2
        if not reports:
            out["note"] = "정기보고서 검색 결과 없음"
            return out                                # 오류(재시도 대상) — 배제가 아니다
        out["quarter"] = q
        # 후보를 몇 개 순회한다 — 첫 결과가 정정신고처럼 II절이 없는 문서일 수 있다.
        for rcp, title in reports[:3]:
            nodes = kfetch.toc(rcp)
            if not nodes:
                continue
            found = find_sections(nodes, SECTIONS)
            if not found:
                found = find_sections(nodes, SECTION_FALLBACK)
            if not found:
                out.update({"rcpNo": rcp, "title": title, "note": "II절 소제목을 목차에서 못 찾음"})
                continue
            texts, meta_secs = {}, {}
            for key, node in found.items():
                html = kfetch.fetch_section(node)
                texts[key] = text_of(html)
                big = len(html.encode("utf-8")) > MAX_CACHE_BYTES
                if not big:                           # 5MB 넘는 절은 캐시하지 않는다
                    os.makedirs(CACHE, exist_ok=True)
                    atomic_write(_sec_path(rcp, key), html)
                meta_secs[key] = {"text": node.get("text", ""), "bytes": len(html), "big": big}
            if not texts:
                out.update({"rcpNo": rcp, "title": title, "note": "절 본문이 비었다"})
                continue
            out.update({"ok": True, "rcpNo": rcp, "title": title, "texts": texts})
            if not any(s["big"] for s in meta_secs.values()):
                os.makedirs(CACHE, exist_ok=True)
                atomic_write(mp, json.dumps(
                    {"stock": st, "quarter": q, "rcpNo": rcp, "title": title,
                     "sections": meta_secs, "fetched": time.strftime("%Y-%m-%d %H:%M")},
                    ensure_ascii=False, indent=1) + "\n")
            return out
        if not out["note"]:
            out["note"] = "목차를 읽지 못함"
    except Exception as e:
        out["note"] = "%s: %s" % (type(e).__name__, str(e)[:120])
    return out


# ── 판정 ─────────────────────────────────────────────────────────────────────

def measure(blob):
    """본문 평문 → 근거·점수. 판정과 분리해 둔다(`--rejudge`가 이 결과만 다시 재는 게 아니라
    같은 함수를 캐시 텍스트에 다시 돌린다 — 규칙과 근거가 어긋나지 않는다)."""
    eq = _hits(blob, EQUIP_RULES)
    strong = [h for h in eq if h["strength"] == 2]
    weak = [h for h in eq if h["strength"] == 1]
    # 장비 점수: 강한 낱말은 낱말마다 최대 6, 넓은 낱말은 최대 2만 인정한다.
    equip = sum(min(h["n"], 6) for h in strong) + sum(min(h["n"], 2) for h in weak)
    mat, mat_forms, mat_at = _rx_hits(blob, MATERIAL_RX)
    dev, dev_forms, dev_at = _rx_hits(blob, DEVICE_RX)
    dist, dist_forms, dist_at = _rx_hits(blob, DIST_RX)
    semi = len(SEMI_RX.findall(blob))
    other = {}
    for k, rx in OTHER_RX.items():
        n = len(rx.findall(blob))
        if n:
            other[k] = n
    return {"strong": strong, "weak": weak,
            "scores": {"equip": equip, "material": mat, "device": dev, "dist": dist,
                       "semi": semi, "other": other},
            "material_terms": mat_forms, "device_terms": dev_forms, "dist_terms": dist_forms,
            "at": {"material": mat_at, "device": dev_at, "dist": dist_at}}


def judge(m, blob):
    """근거 → (verdict, reason, quote). 규칙 순서는 docstring과 같다. fail-closed."""
    s = m["scores"]
    equip, mat, dev, dist, semi = s["equip"], s["material"], s["device"], s["dist"], s["semi"]
    top = ", ".join("%s %d회" % (h["term"], h["n"])
                    for h in sorted(m["strong"], key=lambda h: -h["n"])[:3]) or "없음"

    if semi < SEMI_MIN:
        return ("배제", "반도체 문맥 낱말 %d회(<%d) — 반도체 밸류체인 아님" % (semi, SEMI_MIN),
                quote_at(blob, 0, 0))
    if s["other"]:
        field, n = max(s["other"].items(), key=lambda kv: kv[1])
        if n > semi * OTHER_RATIO:
            at = OTHER_RX[field].search(blob)
            return ("배제", "%s 낱말 %d회 > 반도체 %d회×%.1f — 타산업" % (field, n, semi, OTHER_RATIO),
                    quote_at(blob, *(at.span() if at else (0, 0))))
    if dev >= 4 and dev > equip * DEVICE_MARGIN:
        at = m["at"]["device"] or (0, 0)
        return ("배제", "소자·설계 낱말 %d(%s) > 장비 낱말 %d — 고객 업종(소자사·팹리스)"
                % (dev, ", ".join(list(m["device_terms"])[:3]), equip), quote_at(blob, *at))
    if mat >= 4 and mat > equip * MATERIAL_MARGIN:
        at = m["at"]["material"] or (0, 0)
        return ("배제", "소재 낱말 %d(%s) > 장비·부품 낱말 %d — 소모 소재사"
                % (mat, ", ".join(list(m["material_terms"])[:3]), equip), quote_at(blob, *at))
    if dist >= 4 and equip < EQUIP_HOLD:
        at = m["at"]["dist"] or (0, 0)
        return ("배제", "유통 낱말 %d(%s), 장비 낱말 %d — 유통·판매"
                % (dist, ", ".join(list(m["dist_terms"])[:3]), equip), quote_at(blob, *at))
    if equip >= EQUIP_IN:
        return ("편입", "장비·부품 낱말 점수 %d (%s) · 반도체 %d회" % (equip, top, semi), "")
    if equip >= EQUIP_HOLD:
        return ("보류", "장비 낱말 점수 %d — 편입선(%d) 미만, 사람 확인 필요 (%s)"
                % (equip, EQUIP_IN, top), quote_at(blob, *(m["strong"][0]["at"] if m["strong"] else (0, 0))))
    return ("배제", "반도체 %d회 언급은 있으나 장비·부품·서비스 낱말 점수 %d — 장비 실질 없음"
            % (semi, equip), quote_at(blob, 0, 0))


def row_for(rec, col):
    """수집 결과 → scan.json 한 행. 지정 종목은 판정하지 않고 근거만 모은다."""
    seed = rec.get("source") == "지정"
    row = {"stock": rec["stock"], "name": rec["name"], "source": rec.get("source"),
           "industry": rec.get("industry", ""), "product": rec.get("product", ""),
           "rcpNo": col.get("rcpNo"), "report_title": col.get("title", ""),
           "quarter": col.get("quarter"), "ok": bool(col.get("ok")),
           "evidence": [], "customers": [], "stage_hint": [],
           "verdict": "오류", "reason": col.get("note") or "수집 실패", "quote": "",
           "scores": {}, "note": col.get("note", "")}
    if not col.get("ok"):
        if seed:                                   # 지정은 무조건 편입 — 다만 근거가 없음을 남긴다
            row["verdict"] = "편입"
            row["reason"] = "스펙 지정(판정 대상 아님) — 본문 수집 실패: %s" % (col.get("note") or "")
        return row
    blob = "\n".join(col["texts"].get(k, "") for k in ("overview", "products", "etc", "sales", "ii"))
    m = measure(blob)
    row["scores"] = m["scores"]
    # 근거 인용 — 강한 낱말을 빈도순으로 최대 5개. 낱말만 두면 사람이 검증할 수 없다.
    for h in sorted(m["strong"], key=lambda h: -h["n"])[:5]:
        row["evidence"].append({"term": h["term"], "stage": h["stage"], "n": h["n"],
                                "quote": quote_at(blob, *h["at"])})
    row["customers"] = find_customers(blob)
    stages = Counter()
    for h in m["strong"]:
        if h["stage"]:
            stages[h["stage"]] += h["n"]
    if not stages:                                  # 강한 낱말이 없으면 넓은 낱말로 힌트만
        for h in m["weak"]:
            if h["stage"]:
                stages[h["stage"]] += h["n"]
    row["stage_hint"] = [k for k, _ in stages.most_common()]
    v, reason, quote = judge(m, blob)
    if seed:
        row["verdict"] = "편입"
        row["reason"] = "스펙 지정(판정 대상 아님) · 본문 근거: %s" % reason
        row["quote"] = "" if v == "편입" else quote
        row["judge_if_scanned"] = v                 # 규칙 검증용 — 지정사가 규칙으로도 통과하나
    else:
        row["verdict"], row["reason"], row["quote"] = v, reason, quote
    return row


# ── 전수 실행 ────────────────────────────────────────────────────────────────

def scan(quarter=None, only=None, force=False, cache_only=False, log=sys.stderr):
    quarter = quarter or latest_quarter()
    uni = ksemi_universe.load()
    if not uni:
        raise RuntimeError("assets/universe.json 이 없다 — 먼저 ksemi_universe.py --write")
    recs = [r for r in uni if not only or r["stock"] in only]
    if only:
        miss = sorted(set(only) - {r["stock"] for r in recs})
        if miss:
            log.write("[warn] 모집단에 없는 종목: %s\n" % ",".join(miss))
    log.write("스캔 %d종목 (지정 %d · 어휘 %d) quarter=%s%s\n"
              % (len(recs), sum(r.get("source") == "지정" for r in recs),
                 sum(r.get("source") == "어휘" for r in recs), quarter,
                 " [캐시 전용]" if cache_only else ""))
    done = [0]

    def one(rec):
        return collect_one(rec, quarter, force=force, cache_only=cache_only)

    def on_done(i, rec, res):
        done[0] += 1
        note = res.get("note") if isinstance(res, dict) else str(res)[:60]
        log.write("%4d/%d %s %-16s %s%s\n"
                  % (done[0], len(recs), rec["stock"], rec["name"][:16],
                     "ok" if isinstance(res, dict) and res.get("ok") else "FAIL",
                     (" — " + note) if note else ""))
        log.flush()

    # 레인은 kce_fetch 기본값을 그대로 쓴다(DART는 IP 단위 차단 — KCE_LANES를 건드리지 않는다).
    # 요청 간격은 프로세스 사이 파일 락이 묶으므로 다른 수집기와 같이 돌아도 총 요청률은 유지된다.
    res = parallel(recs, one, on_done=on_done) if not cache_only else [one(r) for r in recs]
    rows = []
    for rec, r in zip(recs, res):
        if isinstance(r, Exception):               # parallel은 예외를 그 자리에 담아 준다
            r = {"ok": False, "note": "%s: %s" % (type(r).__name__, str(r)[:120])}
        try:
            rows.append(row_for(rec, r))
        except Exception as e:                     # 판정 버그가 전수를 죽이지 않게
            rows.append({"stock": rec["stock"], "name": rec["name"], "source": rec.get("source"),
                         "verdict": "오류", "reason": "판정 예외 %s: %s" % (type(e).__name__, str(e)[:100]),
                         "ok": False, "evidence": [], "customers": [], "stage_hint": [], "quote": ""})
    rows.sort(key=lambda r: r["stock"])
    dist = Counter(r["verdict"] for r in rows)
    log.write("판정: %s\n" % json.dumps(dist, ensure_ascii=False))
    return rows, quarter


def rejudge(quarter=None, only=None, log=sys.stderr):
    """규칙을 바꿨을 때 **캐시 원문으로만** 다시 판정한다(DART 무접속)."""
    return scan(quarter=quarter, only=only, cache_only=True, log=log)


def merge(rows, quarter):
    """기존 scan.json에 이번 판정을 덮어쓴다(`--only` 실행이 나머지를 지우면 안 된다)."""
    old = load_asset("scan.json")["rows"] if has_asset("scan.json") else []
    by = {r["stock"]: r for r in old}
    for r in rows:
        by[r["stock"]] = r
    out = sorted(by.values(), key=lambda r: r["stock"])
    return {"generated": time.strftime("%Y-%m-%d %H:%M"), "quarter": quarter,
            "rule": RULE, "n": len(out),
            "dist": dict(Counter(r["verdict"] for r in out)), "rows": out}


def included(scan_rows, universe_rows):
    """**지정 ∪ 편입** 종목. 다른 모듈(build_dicts·reports·page)이 import 해서 쓴다.

    반환: 모집단 행(dict)에 `scan`(verdict·reason·evidence·stage_hint·customers·rcpNo)을
    붙인 목록, 종목코드 순. 판정이 없는(아직 스캔 안 한) 지정 종목도 들어간다 —
    지정은 판정 대상이 아니므로 스캔 결과를 기다리지 않는다.
    """
    by = {r["stock"]: r for r in (scan_rows or [])}
    out = []
    for u in universe_rows or []:
        s = by.get(u["stock"])
        seed = u.get("source") == "지정"
        if not (seed or (s and s.get("verdict") == "편입")):
            continue
        d = dict(u)
        if s:
            d["scan"] = {k: s.get(k) for k in ("verdict", "reason", "rcpNo", "report_title",
                                               "evidence", "customers", "stage_hint", "scores")}
        else:
            d["scan"] = {"verdict": "편입", "reason": "스펙 지정 — 스캔 미실시"}
        out.append(d)
    out.sort(key=lambda r: r["stock"])
    return out


def _show(rows):
    for r in rows:
        print("── %s %s [%s] %s" % (r["stock"], r["name"], r.get("source"), r["verdict"]))
        print("   보고서: %s %s" % (r.get("rcpNo"), r.get("report_title", "")[:50]))
        print("   사유: %s" % r["reason"])
        print("   점수: %s" % json.dumps(r.get("scores", {}), ensure_ascii=False))
        print("   단계힌트: %s · 고객: %s" % (", ".join(r["stage_hint"]) or "—",
                                              ", ".join(r["customers"]) or "—"))
        for e in r["evidence"]:
            print("   · %s(%s, %d회) “%s”" % (e["term"], e["stage"], e["n"], e["quote"][:120]))
        if r.get("quote"):
            print("   인용: “%s”" % r["quote"][:180])


def main():
    ap = argparse.ArgumentParser(description="정기보고서 II절 본문으로 반도체 장비사 판정")
    ap.add_argument("--write", action="store_true", help="assets/scan.json 갱신")
    ap.add_argument("--only", help="종목코드 쉼표 목록")
    ap.add_argument("--quarter", help="예: 2026Q2 (기본: 최신 접수분기)")
    ap.add_argument("--rejudge", action="store_true", help="재수집 없이 캐시 원문으로 재판정")
    ap.add_argument("--force", action="store_true", help="캐시를 무시하고 재수집")
    ap.add_argument("--show", action="store_true", help="근거를 사람이 읽는 형태로 출력")
    a = ap.parse_args()
    only = {s.strip() for s in a.only.split(",") if s.strip()} if a.only else None
    t0 = time.time()
    if a.rejudge:
        rows, quarter = rejudge(quarter=a.quarter, only=only)
    else:
        rows, quarter = scan(quarter=a.quarter, only=only, force=a.force)
    if a.show or not a.write:
        _show(rows)
    if a.write:
        write_asset("scan.json", merge(rows, quarter))
        sys.stderr.write("→ assets/scan.json (%d행 갱신, %.0f초)\n" % (len(rows), time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
