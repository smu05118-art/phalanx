#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_dicts — 반도체 팹 **공정 단계 분류 사전**을 코드에서 생성한다.

  assets/stages.json      공정 단계 13종(키워드 규칙 · 부품 목록 · 팹 흐름 순서)
  assets/stage_tags.json   종목별 단계 태그(근거 낱말·출처와 함께)

손으로 JSON을 쓰지 않고 여기서 만든다 — 낱말을 고칠 때 한 곳만 바꾸고, 교차검증
(사문화 낱말 · 미분류 낱말 · 팔레트 슬롯 대응 · 부품 낱말)을 생성 시점에 돌리기 위해서다.
구조는 `argus/kship/tools/build_dicts.py`(조선 부품 분류)를 본떴다. 분류축과 낱말은
반도체 것으로 새로 만들었다 — 조선의 대분류/소분류 2층이 아니라 **팹 흐름 1층**이다.

## 낱말의 진실의 원천 (두 벌로 갈라지지 않게)

`ksemi_universe.EQUIP_WORDS` 가 **「무엇이 반도체 밸류체인 낱말인가」의 진실의 원천**이다.
이 파일은 그 낱말을 **어느 공정 단계에 배정하는가**만 정한다. 그래서

  * 이 사전의 낱말은 원칙적으로 EQUIP_WORDS 의 부분집합이다(대소문자·공백 무시 비교).
  * EQUIP_WORDS 의 낱말은 모두 어느 단계(또는 `pointer_words`)에 배정되어야 한다 —
    배정 안 된 것은 `--check` 가 `unmatched.equip_unassigned` 로 뱉는다(fail-closed).
  * EQUIP_WORDS 에 없는데 분류에 꼭 필요한 낱말은 `EXTRA_WORDS` 로 따로 모아
    `unmatched.extra_words` 에 실어 **모집단 쪽에 올려 달라고 요청**한다.
    `ksemi_universe.py` 는 이 파일에서 수정하지 않는다(모집단 판정이 흔들리므로).

EQUIP_WORDS 의 블록 주석은 챔버를 「이송·진공」에, 스크러버를 「세정」 옆에 두었지만,
단계 배정은 스펙 「산업 특성 4」를 따랐다 — 챔버·정전척은 **부품소재**, 배기 스크러버·
칠러·가스공급은 **이송/진공(유틸리티)** 이다. 어느 쪽이든 낱말 자체는 한 벌뿐이다.

## 단계는 스펙 「산업 특성 4」의 12종 + 1 (공정서비스)

스펙의 12종을 그대로 쓰고 **`service`(부품 세정·재생 공정서비스) 하나를 더했다**.
이유: KIND 주요제품 원문에 「반도체 부품 세정 및 코팅」(코미코) · 「반도체 장비 부품 제조
및 세정」(한솔아이원스) · 「반도체장비 리퍼비시」(러셀) · 「장비 보호코팅 및 소재」(그린리소스)
처럼 **장비를 만들지도, 부품을 팔지도 않고 부품을 재생·코팅하는 회사**가 여럿 있다.
부품소재로 접으면 「부품을 만드는 회사」와 「부품을 되살리는 회사」가 한 칸에 섞인다.
스펙 완료조건도 코미코를 '부품소재/공정서비스'라 적었다.

## 한 회사는 여러 단계에 걸친다

원익IPS=증착, 케이씨텍=CMP+세정, 에스티아이=이송/진공+세정+식각 이 정상이다. 단계를
하나로 강제하지 않고 매칭된 것을 모두 남긴다. `primary` 는 **강한 낱말 3점 · 약한 낱말
1점** 합으로 정하고(동점은 팹 흐름 앞선 단계), 근거 낱말을 `stages[].words` 에 남겨
사람이 뒤집을 수 있게 한다.

## 오탐을 막는 장치 세 개 (원문에서 실제로 겪은 오탐만 넣었다)

1. `not_words` — 두 가지로 동작한다(생성 시점에 자동으로 갈린다).
   · 단계 낱말을 **품고 있는** 부정 낱말(`마스크팩` ⊃ `마스크`)은 **그 자리만** 버린다.
     겸업사를 지우지 않으려고 이렇게 한다(코미코의 「반도체 부품 세정」은 세정 단계에서만
     빠지고 부품소재·공정서비스 태그는 살아야 한다).
   · 단계 낱말을 품지 않은 부정 낱말(`공작기계` · `잉크젯` · `원전`)은 **그 단계 전체**를
     버린다(화천기공 「연마기(금속공작기계)」가 CMP로 잡히던 오탐).
2. `weak_words` + `ctx_words` — `링` · `전극` · `금형` · `가스` · `부품 제조` 처럼 산업
   밖에서도 흔한 낱말은 **같은 문구에 반도체 문맥**(반도체·웨이퍼·전공정·후공정·메모리…)이
   있어야 채택한다(kship 의 `ctx` 와 같은 장치). 대동 「농업용엔진 및 부품 제조」·
   진성티이씨 「트랙롤라」가 이 규칙으로 떨어진다.
3. 점수 — 약한 낱말만 걸린 단계는 주단계가 되기 어렵다(강 3 : 약 1).

## 입력 우선순위

`assets/scan.json`(정기보고서 II절 본문 근거 — 다른 작업자가 만드는 중) > KIND `주요제품`
> 스펙 지정 사유(`universe.json` 의 `why.seed`). 어느 것을 썼는지 `stages[].source` 에
남긴다. KIND 주요제품은 40자 한 줄이라 **어휘가 얕다** — 원익IPS 는 「반도체 제조용 기계」,
케이씨텍은 「반도체, 디스플레이 제조 장비」 뿐이어서 제품 문구만으로는 단계가 안 붙는다.
그래서 지정 21종목은 스펙 지정 사유를 마지막 보루로 쓰고(`source:"seed"`), scan.json 이
들어오면 **원문 근거가 그것을 덮는다**.

사용:
    python3 build_dicts.py --write                 # stages.json + stage_tags.json 생성
    python3 build_dicts.py --check                 # 교차검증만(쓰지 않는다)
    python3 build_dicts.py --classify "PE-CVD 외"  # 한 문구 분류 시험
"""
import argparse
import os
import sys

from ksemi_lib import ASSETS, has_asset, load_asset, write_asset
from ksemi_universe import EQUIP_WORDS, SEED, load_full

VER = "2026-09"

# 반도체 문맥 낱말 — `weak_words` 채택 조건. 디스플레이는 넣지 않는다(디스플레이 전용
# 장비사가 전공정 단계로 잡히면 안 된다 — 편입 판정은 ksemi_scan.py 의 몫).
CTX_WORDS = (
    "반도체", "웨이퍼", "wafer", "전공정", "후공정", "팹", "실리콘",
    "메모리", "dram", "디램", "낸드", "nand", "파운드리", "semiconductor", "포토마스크",
)

# 산업 지시어 — 어느 한 단계로 접을 수 없는 낱말. EQUIP_WORDS 에 있으나 단계 배정에서
# 빼고 여기에 적는다(미분류로 세지 않는다). `후공정` 은 예외로 pkg 의 강한 낱말이다
# (원문 「반도체 후공정장비」(한미반도체)·「반도체 후공정 장비」(제너셈)가 단계를 확정한다).
POINTER_WORDS = (
    "웨이퍼", "wafer", "반도체 제조용", "반도체제조용", "반도체 장비", "반도체장비",
    "반도체 제조 장비", "전공정",
)

# EQUIP_WORDS 에 있으나 **일부러 단계에 배정하지 않은** 낱말과 그 이유.
# 이유 없이 배정 안 된 낱말이 생기면 `--check` 가 오류로 멈춘다(fail-closed) — 모집단에
# 낱말이 늘었는데 단계 사전이 안 따라가는 상황을 조용히 넘기지 않으려고.
UNASSIGNED_NOTE = {
    "rf": ("너무 짧아 오탐만 한다 — 「RF통신부품」(기가레인)·「RF필터 파운드리」(쏘닉스)·"
           "「RF PKG」(코스텍시스)·「GaN RF 칩」(웨이비스)이 전부 장비·부품이 아니다. "
           "부품소재는 `제너레이터`·`generator` 로 좁혀 받는다. "
           "→ EQUIP_WORDS 에서 `RF` 를 `RF제너레이터`·`RF파워`로 바꿔 달라고 요청한다."),
    "измер": ("러시아어 조각(измерение=계측)이 EQUIP_WORDS 에 섞여 들어갔다. 한국 공시 "
              "원문에 나올 수 없다 → EQUIP_WORDS 에서 지워 달라고 요청한다."),
    "정밀금형": ("후보 154종목에서 이 낱말이 걸린 회사는 「이차전지 정밀금형」(유진테크놀로지)·"
                "「대형정밀금형(가전,자동차용)」(에이테크솔루션)뿐이다 — 반도체 금형은 "
                "「반도체금형」(한미반도체)으로 적힌다. 그래서 pkg 의 부정 낱말로만 쓴다."),
}

# EQUIP_WORDS 에 없는데 분류에 필요한 낱말 — 모집단 쪽에 올려 달라고 요청할 목록.
# (여기 있는 낱말은 분류에 쓰되 `unmatched.extra_words` 로 보고한다.)
EXTRA_WORDS = (
    # 포토
    "블랭크마스크", "포토마스크", "스테퍼",
    # 식각·세정
    "dry etch", "poly etch", "에처", "건식세정", "습식세정", "드라이클리닝", "descum",
    "scrubber",
    # 열처리
    "anneal", "퍼니스", "furnace", "급속열처리",
    # CMP
    "폴리싱",
    # 계측·검사
    "비전검사", "광학검사", "x-ray", "엑스레이", "측정", "linac",
    # 이온주입
    "implant",
    # 테스트
    "socket", "burn in", "change over kit", "c.o.k", "신뢰성", "probe card", "검사용 소켓",
    # 이송·진공·유틸리티
    "efem", "lpm", "cluster tool", "진공펌프", "가스공급", "가스 공급", "chemical 공급",
    "중앙공급", "약액", "유량계", "유량 제어", "드라이룸", "트랩", "피팅",
    # 후공정
    "쏘잉", "범프", "리플로", "reflow", "백그라인딩", "laser",
    # 부품
    "히터블록", "세라믹부품", "세라믹 부품", "소모성 부품", "장비 부품", "장비용 부품",
    "반도체 부품", "반도체부품", "정밀가공 부품", "부품 제조", "반도체용", "cvd-sic",
    "generator", "지그",
    # 공정 서비스
    "리퍼비시", "부품세정", "제조 및 세정", "세정 및 코팅", "보호코팅",
)

# ── 단계 사전 ────────────────────────────────────────────────
# (key, label, flow_order, front_back, strong, weak, not_words, parts, note)
#   flow_order : 팹 흐름 순서. None 은 흐름 밖(부품소재·공정서비스).
#   front_back : 전공정 / 후공정 / 공통
#   parts      : (부품 key, 한국어 라벨, 낱말) — 인포그래픽 2단 드릴다운(단계 → 부품 → 부품사).
#                부품 낱말은 parts 단계의 낱말과 같은 벌을 쓴다(생성 시점에 교차검증).
STAGES = [
    ("photo", "포토(트랙·EUV 주변)", 1, "전공정",
     ["포토", "노광", "euv", "레티클", "코터", "디벨로퍼", "블랭크마스크", "포토마스크", "스테퍼"],
     ["트랙", "마스크"],
     ["마스크팩", "하이드로겔", "트랙터", "트랙롤라", "트랙롤러", "크롤러", "포토레지스트", "잉크젯",
      "이차전지", "2차전지", "전극장비"],
     [("quartz", "쿼츠·석영", ["쿼츠", "석영"]),
      ("chamber", "챔버", ["챔버"]),
      ("jig", "지그·치구", ["지그"])],
     "스캐너(노광기) 자체는 국내 상장사가 없다 — 원문에서 확인 못 함. 국내 상장사는 트랙(코터·"
     "디벨로퍼)·블랭크마스크(에스앤에스텍)·EUV 주변(아이엠티 「EUV Mask Baking Laser」)뿐이다. "
     "`트랙`·`마스크`는 약한 낱말로 내렸다 — 「트랙터」(대동)·「트랙롤라」(진성티이씨)·"
     "「마스크팩」(진코스텍)이 실제로 오탐했다. 소재(포토레지스트)는 단계 밖이라 부정 낱말로 뺀다. "
     "이차전지 전극 코터(케이지에이 「2차전지 전극장비 (코터, 프레스, 슬리터)」)도 단계 전체를 버린다."),

    ("etch", "식각", 2, "전공정",
     ["식각", "에칭", "etch", "etcher", "에처", "dry etch", "poly etch"],
     [],
     [],
     [("chamber", "챔버", ["챔버"]),
      ("esc", "정전척(ESC)", ["정전척", "esc"]),
      ("focusring", "포커스링·전극", ["포커스링", "포커스 링", "전극", "링"]),
      ("rfgen", "RF 제너레이터", ["제너레이터", "generator"]),
      ("quartz", "쿼츠·석영", ["쿼츠", "석영"]),
      ("sic", "SiC·흑연 부품", ["sic", "흑연", "graphite", "cvd-sic"]),
      ("vacpump", "진공펌프·밸브", ["진공펌프", "밸브"])],
     "원문 확인: 브이엠 「300mm Poly Etch System」·인베니아 「Dry Etcher」·에스티아이 "
     "「세정·식각시스템」. 스트립·애싱(포토레지스트 제거)은 식각이 아니라 **세정**에 넣었다 — "
     "피에스케이가 「드라이스트립, 드라이클리닝」을 한 묶음으로 공시하고 스펙 완료조건도 "
     "피에스케이를 세정/스트립이라 적었다."),

    ("depo", "증착(CVD·ALD·PVD·에피)", 3, "전공정",
     ["증착", "cvd", "ald", "pvd", "스퍼터", "에피", "epi"],
     [],
     ["cvd-sic", "스퍼터링타겟", "스퍼터링 타겟"],
     [("chamber", "챔버", ["챔버"]),
      ("showerhead", "샤워헤드", ["샤워헤드"]),
      ("heater", "히터·서셉터", ["히터", "히터블록"]),
      ("esc", "정전척(ESC)", ["정전척", "esc"]),
      ("quartz", "쿼츠·석영", ["쿼츠", "석영"]),
      ("sic", "SiC·흑연 부품", ["sic", "흑연", "graphite", "cvd-sic"]),
      ("rfgen", "RF 제너레이터", ["제너레이터", "generator"]),
      ("vacpump", "진공펌프·밸브", ["진공펌프", "밸브"])],
     "원문 확인: 유진테크 「실리콘질화막증착용LP-CVD」·테스 「반도체장비(화학증착장비)」·"
     "주성엔지니어링 「ALG, ALD」(ALG 는 KIND 원문 표기 그대로 — ALD 로 걸린다). "
     "원익IPS 는 주요제품이 「반도체 제조용 기계」뿐이어서 제품 문구로는 안 잡힌다 → 지정 사유. "
     "「CVD-SiC Ring」(케이엔제이)은 장비가 아니라 부품이라 부정 낱말로 뺀다."),

    ("implant", "이온주입", 4, "전공정",
     ["이온주입", "이온 주입", "임플란트", "implant"],
     [],
     [],
     [("chamber", "챔버", ["챔버"]),
      ("graphite", "흑연 부품", ["흑연", "graphite"]),
      ("vacpump", "진공펌프", ["진공펌프"])],
     "국내 상장 이온주입 장비사는 **원문에서 확인 못 함**(후보 154종목의 주요제품에 이온주입 "
     "낱말이 0건). 단계는 남긴다 — 스펙의 분류축이고, scan.json(정기보고서 II절 본문)에서 "
     "부품·서비스사의 전방 언급으로 걸릴 수 있다. 그래서 이 단계 낱말은 사문화 목록에 오른다."),

    ("thermal", "열처리/RTP", 5, "전공정",
     ["열처리", "어닐", "annealing", "anneal", "rtp", "퍼니스", "furnace", "급속열처리", "확산"],
     ["산화"],
     ["산화물", "산화방지제", "이산화", "산화망간", "산화아연", "인산아연", "산화코발트", "타이어"],
     [("quartz", "쿼츠 튜브·보트", ["쿼츠", "석영"]),
      ("heater", "히터", ["히터", "히터블록"]),
      ("sic", "SiC·흑연 보트", ["sic", "흑연", "graphite"]),
      ("chamber", "챔버", ["챔버"])],
     "원문 확인: HPSP 「고압 수소 어닐링 장비」. `산화`는 약한 낱말로 내렸다 — 「산화방지제」"
     "(송원산업)·「이산화티타늄」(코스모화학)·「산화망간」(한창산업)·「인듐계 산화물」"
     "(나노신소재)이 모두 소재사다. 비아트론(열처리 장비)은 주요제품이 「디스플레이 및 반도체 "
     "제조용 장비」뿐이라 안 잡힌다 — scan.json 이 들어오면 다시 본다."),

    ("cmp", "CMP", 6, "전공정",
     ["cmp", "폴리싱"],
     ["연마"],
     ["cmp slurry", "cmp 슬러리", "공작기계", "연마재"],
     [("pad", "CMP 패드·리테이너링", ["링"]),
      ("chamber", "챔버", ["챔버"]),
      ("jig", "지그·치구", ["지그"])],
     "원문 확인: 나노신소재 「반도체 CMP Slurry」(소재 — 부정 낱말로 뺀다). 케이씨텍은 "
     "주요제품이 「반도체, 디스플레이 제조 장비」뿐이라 지정 사유로 CMP+세정을 붙였다. "
     "`연마`는 약한 낱말 — 화천기공 「연마기(금속공작기계)」가 오탐했다."),

    ("clean", "세정(스트립·애싱 포함)", 7, "전공정",
     ["세정", "세척", "클리닝", "cleaning", "cleaner", "스트립", "애싱", "애셔",
      "descum", "건식세정", "습식세정", "드라이클리닝"],
     [],
     ["부품 세정", "부품세정", "제조 및 세정", "세정 및 코팅", "세척액"],
     [("chamber", "챔버", ["챔버"]),
      ("quartz", "쿼츠·석영", ["쿼츠", "석영"]),
      ("rfgen", "RF 제너레이터", ["제너레이터", "generator"]),
      ("nozzle", "노즐·약액 배관", ["약액", "배관"]),
      ("vacpump", "진공펌프·밸브", ["진공펌프", "밸브"])],
     "원문 확인: 피에스케이 「드라이스트립, 드라이클리닝」·피에스케이홀딩스 「Descum」·"
     "아이씨디 「건식세정기」·뉴파워프라즈마 「플라즈마 세정기(Remote Plasma Cleaning "
     "Generator)」·아이엠티 「건식세정 장비」. **부품 세정은 이 단계가 아니다** — 「반도체 "
     "부품 세정 및 코팅」(코미코)·「부품 제조 및 세정」(한솔아이원스)은 웨이퍼를 씻는 게 "
     "아니라 장비 부품을 씻는 공정서비스라 부정 낱말로 빼고 `service` 가 받는다."),

    ("metro", "계측/검사(오버레이·결함·CD)", 8, "공통",
     ["계측", "검측", "결함", "defect", "오버레이", "overlay", "cd-sem", "현미경",
      "inspection", "메트롤로지", "비전검사", "광학검사", "x-ray", "엑스레이", "측정"],
     ["검사"],
     ["검체검사", "생체현미경", "가스검지", "검지기", "신뢰성 검사", "원전", "발전소", "타이어"],
     [("stage", "정밀 스테이지·지그", ["지그"]),
      ("chamber", "진공 챔버", ["챔버"])],
     "원문 확인: 넥스틴 「전공정용 패턴결함 검사장비(AEGIS)」·오로스테크놀로지 「Overlay 계측 "
     "장비」·파크시스템스 「원자현미경」·고영 「3차원 납도포검사장비」·코셈 「주사전자현미경"
     "(SEM)」·쎄크 「X-ray 검사장비」. **`검사`는 약한 낱말로 내렸다** — 전공정 계측검사와 "
     "후공정 테스트가 같이 쓰는 말이어서(「반도체 검사용 소켓」오킨스전자·「반도체검사장치 "
     "Probe Card」프로이천·「반도체검사장비(반도체테스트핸들러)」미래산업) 강하게 두면 "
     "테스트 회사의 주단계를 빼앗는다. 더 구체적인 낱말(결함·오버레이·현미경·엑스레이 ↔ "
     "프로브카드·핸들러·소켓)이 주단계를 정하고, 둘 다 태그되는 것은 정상이다. "
     "덤으로 「LCD검사장비」(동아엘텍)·「TFT-LCD검사장비」(HB테크놀러지)처럼 반도체 문맥이 "
     "없는 디스플레이 전용 회사는 약한 낱말 규칙에 걸려 태그가 안 붙는다. "
     "「신뢰성 검사」(큐알티)는 테스트라 여기서 뺀다. 남는 오차: 「반도체 검사장비」만 적은 "
     "엑시콘·네오셈은 실제로 후공정 테스터 회사인데 여기서는 계측검사로 붙는다 — 제품 문구 "
     "40자로는 가를 수 없다(scan.json 본문 근거가 들어오면 뒤집힌다). "
     "`SEM` 단독 낱말은 넣지 않았다 — `semiconductor` 안에 묻혀 오탐한다. "
     "위드텍 「AMCs 모니터링 시스템」은 걸리지 않는다(`모니터링`은 `링` 오탐 때문에 부정 낱말). "
     "계측 장비의 광학계(렌즈·미러)는 국내 상장 부품사를 원문에서 확인 못 해 부품 목록에서 뺐다."),

    ("handling", "이송/진공·유틸리티", 9, "공통",
     ["이송", "반송", "진공", "진공펌프", "칠러", "ccss", "c.c.s.s", "클린룸", "드라이룸",
      "oht", "스토커", "로드포트", "foup", "카세트", "웨이퍼 캐리어", "efem", "lpm",
      "cluster tool", "스크러버", "scrubber", "트랩", "유량계", "유량 제어", "약액",
      "가스공급", "가스 공급", "chemical 공급", "중앙공급", "배관"],
     ["펌프", "밸브", "가스", "피팅"],
     ["진공합착", "진공포장", "펌프 디스펜서", "콘크리트펌프", "펌프트럭", "펌프카", "심정펌프",
      "온수분배기", "매몰용접", "lpg", "부탄가스", "에어졸", "특수가스", "정수기 피팅",
      "가스센서", "가스밸브", "가스검지", "분체이송"],
     [("vacpump", "진공펌프", ["진공펌프"]),
      ("valve", "밸브·피팅", ["밸브", "피팅"]),
      ("pipe", "배관·약액 라인", ["배관", "약액"]),
      ("chamber", "이송 챔버", ["챔버"])],
     "스펙의 「이송/진공」에 **유틸리티**(가스·약액 중앙공급·칠러·배기 스크러버)를 같이 넣었다. "
     "원문 확인: 에스티아이 「Chemical 중앙공급시스템(C.C.S.S)」·싸이맥스 「웨이퍼 이송장치"
     "(Cluster Tool, EFEM, LPM)」·엘오티베큠 「반도체제조용진공펌프」·3S 「반도체 웨이퍼 "
     "캐리어」·유니셈 「반도체장비(DryGasScrubber)」·케이엔솔 「클린룸 설비」·이엘씨 "
     "「반도체장비용 유량계」. 별도 '유틸리티' 단계를 세우지 않은 이유는 8슬롯 팔레트다"
     "(palette.json `rules`). `펌프`·`밸브`·`가스`·`피팅`은 약한 낱말 — LPG밸브(에쎈테크)·"
     "콘크리트펌프(현대에버다임)·부탄가스(태양)·정수기 피팅(스톰테크)이 오탐한다. "
     "아스플로·디케이락처럼 「강관, 피팅, 밸브류」만 적은 회사는 문구에 반도체 문맥이 없어 "
     "태그가 안 붙는다 — scan.json 본문 근거가 들어오면 붙는다."),

    ("test", "테스트(핸들러·프로브카드·번인)", 10, "후공정",
     ["테스터", "테스트", "핸들러", "프로브", "probe", "프로브카드", "probe card",
      "검사용 소켓", "번인", "burn-in", "burn in", "소켓", "socket",
      "change over kit", "c.o.k", "신뢰성"],
     [],
     ["테스트베드", "부탄가스"],
     [("probecard", "프로브카드·프로브핀", ["프로브카드", "프로브"]),
      ("socket", "테스트 소켓", ["소켓", "socket"]),
      ("cok", "체인지 오버 킷", ["change over kit", "c.o.k"]),
      ("jig", "지그·치구", ["지그"])],
     "원문 확인: 테크윙 「반도체테스트핸들러,C.O.K(Change Over Kit)」·유니테스트 「메모리"
     "컴포넌트테스터」·리노공업 「리노핀, 반도체 소켓」·마이크로컨텍솔 「BGA IC Burn-In "
     "Socket」·티에스이·피엠티·프로이천·마이크로투나노 「Probe Card」·제이티 「Burn-in "
     "Sorter」·큐알티 「반도체 신뢰성 검사」·두산테스나·네패스아크·아이텍·에이팩트 "
     "「반도체 테스트(서비스)」. 테스트 **서비스**사도 이 단계에 넣는다(장비가 아니라 "
     "용역이지만 공정 위치가 같고, 스펙 모집단이 공정 서비스를 포함한다). "
     "「검사용 소켓」·「probe card」를 낱말로 넣은 이유는 계측검사(`검사`)와 겹치는 회사에서 "
     "주단계를 테스트로 끌어오기 위해서다(오킨스전자·프로이천·피엠티)."),

    ("pkg", "패키징/후공정(본더·몰딩·레이저)", 11, "후공정",
     ["패키징", "패키지", "본더", "본딩", "다이본더", "tc bonder", "다이싱", "소잉", "쏘잉",
      "몰딩", "마커", "트리머", "리드프레임", "범핑", "범프", "tsv", "플립칩", "후공정",
      "리플로", "reflow", "백그라인딩"],
     ["레이저", "laser", "금형"],
     ["레이저다이오드", "laserdiode", "레이저가공 절단", "산업용 레이저", "레이저 가공장비",
      "패키지용 substrate", "통신용 패키지", "패키지 트랜지스터", "타이어 금형", "사출금형",
      "정밀금형", "판금부품", "마스크팩",
      "oled용 후공정", "디스플레이 후공정", "패널 후공정"],
     [("bondhead", "본딩 헤드·스테이지", ["지그"]),
      ("mold", "몰드 금형", ["금형"]),
      ("leadframe", "리드프레임", ["리드프레임"]),
      ("laseroptic", "레이저 광학계", ["laser", "레이저"])],
     "원문 확인: 한미반도체 「반도체 후공정장비,반도체금형」(스펙 §1 원문 확인 기록의 "
     "「HBM4 제조용 TC BONDER 4.5 GRIFFIN」이 같은 회사다)·이오테크닉스 「레이저 마커」·"
     "제너셈 「반도체 후공정 장비」·LB세미콘 「골드범핑, 솔더범핑」·시그네틱스·윈팩·"
     "하나마이크론·MSDI 「반도체 패키징」·HLB이노베이션·성우테크론 「리드프레임」·"
     "피에스케이홀딩스 「Reflow」. `레이저`·`금형`은 약한 낱말이고 부정 낱말이 길다 — "
     "레이저다이오드(큐에스아이)·레이저가공 절단기(에이치케이)·타이어 금형(다이나믹디자인)·"
     "이차전지 정밀금형(유진테크놀로지)이 모두 오탐했다. 기판(해성디에스 「패키지용 "
     "Substrate」)은 소재라 뺀다. `후공정`은 디스플레이도 쓰는 말이어서 「OLED용 후공정장비」"
     "(신도기연)는 부정 낱말로 자리를 막았다."),

    ("parts", "부품소재(챔버·ESC·쿼츠·세라믹)", None, "공통",
     ["챔버", "정전척", "esc", "샤워헤드", "히터블록", "쿼츠", "석영", "흑연", "graphite",
      "sic", "cvd-sic", "실리콘부품", "실리콘 부품", "세라믹부품", "세라믹 부품",
      "포커스링", "포커스 링", "소모성 부품", "장비 부품", "장비용 부품", "반도체 부품",
      "반도체부품", "정밀가공 부품", "제너레이터", "generator"],
     ["히터", "세라믹", "전극", "링", "부품 제조", "반도체용", "지그"],
     ["모니터링", "쿨링", "실링", "샘플링", "드릴링", "링크", "슬링", "필링", "볼링",
      "세라믹 비드", "세라믹 기판", "다층 세라믹", "이차전지 전극", "2차전지 전극",
      "전극공정", "전극장비", "엔진 및 부품", "판금부품", "통신부품", "타이어",
      "descum", "asic", "basic", "classic", "music"],
     [("chamber", "챔버", ["챔버"]),
      ("esc", "정전척(ESC)", ["정전척", "esc"]),
      ("showerhead", "샤워헤드", ["샤워헤드"]),
      ("heater", "히터·히터블록", ["히터", "히터블록"]),
      ("quartz", "쿼츠·석영", ["쿼츠", "석영"]),
      ("ceramic", "세라믹 부품", ["세라믹", "세라믹부품", "세라믹 부품"]),
      ("sic", "SiC·흑연 부품", ["sic", "흑연", "graphite", "cvd-sic"]),
      ("silicon", "실리콘 부품", ["실리콘부품", "실리콘 부품"]),
      ("focusring", "포커스링·전극", ["포커스링", "포커스 링", "전극", "링"]),
      ("rfgen", "RF 제너레이터", ["제너레이터", "generator"]),
      ("vacpump", "진공펌프·밸브", ["진공펌프", "밸브"]),
      ("jig", "지그·치구", ["지그"])],
     "장비의 **부분품**을 만드는 회사. 원문 확인: 하나머티리얼즈 「실리콘부품, 세라믹부품」·"
     "티씨케이 「고순도 흑연제품」·월덱스 「반도체용링및전극」·비씨엔씨 「합성쿼츠 포커스링」·"
     "미코 「반도체 및 디스플레이 부품 제조」·씨엠티엑스 「반도체 장비용 소모성 부품」·"
     "엔투텍 「반도체장비 부품 제조업」·포인트엔지니어링 「디스플레이 및 반도체 장비 부품」·"
     "메카로 「히터블록」·케이엔제이 「CVD-SiC Ring」·뉴파워프라즈마 「Plasma Cleaning "
     "Generator」. 흐름 밖이라 `flow_order=null`. 전구체·특수가스·슬러리·포토레지스트 같은 "
     "**소재**는 이 단계가 아니다(장비 부분품이 아니다) — 스펙이 부품소재를 챔버·정전척·"
     "샤워헤드·히터·쿼츠·세라믹·RF제너레이터·진공펌프·밸브로 한정했다. `링`·`전극`·`세라믹`·"
     "`부품 제조`는 약한 낱말 + 부정 낱말 20개 — 「모니터링」(위드텍)·「세라믹 비드」(쎄노텍)·"
     "「다층 세라믹 기판」(샘씨엔에스)·「이차전지 전극공정 장비」(SFA넥셀)·「농업용엔진 및 "
     "부품 제조」(대동)가 모두 오탐했다. 영문 약어도 막아야 한다 — `esc`가 「Descum」"
     "(피에스케이홀딩스) 안에, `sic`가 「ASIC」(싸이닉솔루션) 안에 묻혀 들어왔다."),

    ("service", "부품세정·재생 공정서비스", None, "공통",
     ["부품 세정", "부품세정", "제조 및 세정", "세정 및 코팅", "보호코팅", "리퍼브",
      "리퍼비시", "부품재생", "공정 서비스"],
     ["재생", "코팅"],
     ["신재생", "재생에너지", "ito코팅", "ito 코팅", "재생섬유", "재생에너지 발전소"],
     [("coating", "코팅 소재·설비", ["코팅"]),
      ("chamber", "재생 대상 부품(챔버·ESC·쿼츠)", ["챔버", "정전척", "esc", "쿼츠"])],
     "스펙 12종에 없지만 **원문에 있어서** 더한 단계(모듈 docstring 참조). 원문 확인: "
     "코미코 「반도체 부품 세정 및 코팅」·한솔아이원스 「반도체 장비 부품 제조 및 세정」·"
     "러셀 「반도체장비 리퍼비시」·그린리소스 「반도체 및 디스플레이 장비 보호코팅」. "
     "`재생`·`코팅`은 약한 낱말 — 「신재생에너지」(피에스텍)·「ITO코팅」(아바텍)이 오탐했다. "
     "「화학약품재생장치」(씨앤지하이테크)는 약액 재생 **장비**라 이송/진공으로 간다."),
]


# ── 낱말 매칭 ────────────────────────────────────────────────
# 문구는 소문자로 눌러 비교한다(`lower()` 는 한글에 영향이 없다). 형태소 분석 없이
# 부분문자열로 보되, 오탐은 not_words 로 자리를 막는다(위 docstring 1번).

def _norm(w):
    return w.lower().strip()


def _find(tl, w):
    out, i = [], tl.find(w)
    while i >= 0:
        out.append((i, i + len(w)))
        i = tl.find(w, i + 1)
    return out


def _compile():
    """STAGES → 매칭용 구조. not_words 를 자리거부(span)와 단계거부(hard)로 가른다."""
    out = []
    for key, label, flow, fb, strong, weak, nots, parts, note in STAGES:
        words = [(_norm(w), "strong") for w in strong] + [(_norm(w), "weak") for w in weak]
        span_not, hard_not = [], []
        for nw in nots:
            n = _norm(nw)
            if any(w in n for w, _ in words):
                span_not.append(n)
            else:
                hard_not.append(n)
        out.append({"key": key, "label": label, "flow_order": flow, "front_back": fb,
                    "words": words, "span_not": span_not, "hard_not": hard_not,
                    "strong": strong, "weak": weak, "not_words": nots,
                    "parts": parts, "note": note})
    return out


COMPILED = _compile()
_CTX = tuple(_norm(c) for c in CTX_WORDS)


def has_ctx(text):
    tl = (text or "").lower()
    return any(c in tl for c in _CTX)


def _hits(text, st):
    """한 단계의 매칭 낱말 목록. 반환 [(낱말, 'strong'|'weak')]."""
    tl = (text or "").lower()
    for nw in st["hard_not"]:
        if nw in tl:
            return []
    veto = []
    for nw in st["span_not"]:
        veto += _find(tl, nw)
    ctx = any(c in tl for c in _CTX)
    hits = []
    for w, kind in st["words"]:
        if kind == "weak" and not ctx:
            continue
        for s in _find(tl, w):
            if not any(v[0] <= s[0] and s[1] <= v[1] for v in veto):
                hits.append((w, kind))
                break
    return hits


def score(hits):
    """강한 낱말 3 · 약한 낱말 1. 약한 낱말만으로는 주단계가 되기 어렵게."""
    return sum(3 if k == "strong" else 1 for _, k in hits)


def classify(text):
    """문구 → [(stage_key, matched_words)]. 점수 내림차순(동점은 팹 흐름 순).

    한 회사가 여러 단계에 걸치는 것이 정상이라 **자르지 않고 모두** 돌려준다.
    """
    rows = []
    for st in COMPILED:
        h = _hits(text, st)
        if h:
            rows.append((st, h))
    rows.sort(key=lambda r: (-score(r[1]),
                             r[0]["flow_order"] if r[0]["flow_order"] else 99,
                             r[0]["key"]))
    return [(st["key"], [w for w, _ in h]) for st, h in rows]


def classify_full(text):
    """classify() + 점수·강약·주단계. stage_tags 와 --classify 가 쓴다."""
    rows = []
    for st in COMPILED:
        h = _hits(text, st)
        if h:
            rows.append({"key": st["key"], "label": st["label"],
                         "front_back": st["front_back"],
                         "flow_order": st["flow_order"],
                         "words": [w for w, _ in h],
                         "strong": [w for w, k in h if k == "strong"],
                         "score": score(h)})
    rows.sort(key=lambda r: (-r["score"], r["flow_order"] or 99, r["key"]))
    return rows


def front_back_of(keys):
    """회사 수준 전/후공정 표시. 전공정·후공정을 다 가지면 '전후공정 겸업'."""
    fb = {st["front_back"] for st in COMPILED if st["key"] in keys}
    front, back = "전공정" in fb, "후공정" in fb
    if front and back:
        return "전후공정 겸업"
    if front:
        return "전공정"
    if back:
        return "후공정"
    return "공통" if fb else ""


# ── 종목별 태그 ──────────────────────────────────────────────

def _scan_texts():
    """scan.json(다른 작업자 산출)에서 종목별 본문 근거 문구를 모은다.

    스키마가 아직 확정되지 않았다(2026-09-11 기준 파일 없음). 그래서 **관대하게** 읽는다 —
    리스트든 dict든, 문구 키가 evidence/hits/text/snippet/product 중 무엇이든 문자열만
    긁어 모은다. 아무 문구도 못 얻으면 그 종목은 제품 문구로 되돌린다(조용히 비우지 않는다).
    """
    if not has_asset("scan.json"):
        return {}
    try:
        raw = load_asset("scan.json")
    except Exception as e:                                   # noqa: BLE001
        print("scan.json 을 읽지 못했다(%s) — 제품 문구만 쓴다" % e, file=sys.stderr)
        return {}
    rows = raw.get("rows") if isinstance(raw, dict) else raw
    if isinstance(rows, dict):
        rows = list(rows.values())
    out = {}
    KEYS = ("evidence", "hits", "text", "texts", "snippet", "snippets", "product",
            "products", "quote", "quotes", "section")

    def walk(v, bag):
        if isinstance(v, str):
            bag.append(v)
        elif isinstance(v, list):
            for x in v:
                walk(x, bag)
        elif isinstance(v, dict):
            for k, x in v.items():
                if k in KEYS:
                    walk(x, bag)
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        code = r.get("stock") or r.get("code") or r.get("slug")
        if not code:
            continue
        bag = []
        for k in KEYS:
            if k in r:
                walk(r[k], bag)
        txt = " / ".join(dict.fromkeys(s for s in bag if s and s.strip()))
        if txt:
            out[str(code)] = txt
    return out


def tag_universe():
    """universe.json(+scan.json) → 종목별 단계 태그. 반환 (rows, 경고 목록)."""
    full = load_full()
    rows = full.get("rows") or []
    if not rows:
        return [], ["universe.json 이 비어 있다 — `python3 ksemi_universe.py --write` 먼저"]
    scan = _scan_texts()
    out, warn = [], []
    for r in rows:
        code, name = r["stock"], r["name"]
        cands = []
        if code in scan:
            cands.append(("scan", scan[code]))
        if r.get("product"):
            cands.append(("product", r["product"]))
        seed = (r.get("why") or {}).get("seed")
        if seed:
            cands.append(("seed", seed))
        merged, used = {}, []
        for src, text in cands:
            got = classify_full(text)
            if got:
                used.append({"source": src, "text": text})
            for g in got:
                prev = merged.get(g["key"])
                if prev is None or g["score"] > prev["score"]:
                    g = dict(g)
                    g["source"] = src
                    merged[g["key"]] = g
            if merged:
                break            # 상위 출처에서 단계가 붙으면 아래 출처는 보지 않는다
        stages = sorted(merged.values(),
                        key=lambda g: (-g["score"], g["flow_order"] or 99, g["key"]))
        rec = {"stock": code, "name": name,
               "stages": [{"key": g["key"], "words": g["words"], "source": g["source"]}
                          for g in stages],
               "primary": stages[0]["key"] if stages else None,
               "front_back": front_back_of({g["key"] for g in stages}),
               "evidence": used[0]["text"] if used else (r.get("product") or ""),
               "evidence_source": used[0]["source"] if used else None}
        out.append(rec)
        if not stages and code in SEED:
            warn.append("지정 %s %s — 단계가 하나도 안 붙었다: %r"
                        % (code, name, r.get("product")))
    return out, warn


# ── 교차검증 ─────────────────────────────────────────────────

def cross_check(tags=None):
    """사전 ↔ EQUIP_WORDS ↔ 후보 제품 문구 ↔ palette 교차검증. 반환 (report, errors)."""
    errs = []
    equip = {_norm(w) for w in EQUIP_WORDS}
    pointer = {_norm(w) for w in POINTER_WORDS}
    extra = {_norm(w) for w in EXTRA_WORDS}
    assigned = {}
    for st in COMPILED:
        for w, kind in st["words"]:
            assigned.setdefault(w, []).append(st["key"])
    # ① 사전 낱말이 EQUIP_WORDS(또는 EXTRA_WORDS)에 있는가
    orphan = sorted(w for w in assigned if w not in equip and w not in extra)
    if orphan:
        errs.append("사전 낱말이 EQUIP_WORDS·EXTRA_WORDS 어디에도 없다: %s" % orphan)
    # ② EQUIP_WORDS 가 모두 배정되었는가(= 미분류 낱말). 배정 안 한 낱말은 이유가 있어야 한다.
    unassigned = sorted(w for w in equip if w not in assigned and w not in pointer)
    nore = [w for w in unassigned if w not in UNASSIGNED_NOTE]
    if nore:
        errs.append("EQUIP_WORDS 의 %s 가 어느 단계에도 없고 이유도 안 적혀 있다 "
                    "(UNASSIGNED_NOTE 에 이유를 적거나 단계에 배정하라)" % nore)
    # ③ 사문화 낱말 — 후보 제품 문구(+scan)에 한 번도 안 걸리는 사전 낱말
    full = load_full()
    texts = [r.get("product") or "" for r in (full.get("rows") or [])]
    texts += [(r.get("why") or {}).get("seed") or "" for r in (full.get("rows") or [])]
    texts += list(_scan_texts().values())
    blob = " \n ".join(texts).lower()
    dead = sorted(w for w in assigned if w not in blob)
    # ④ 부품 낱말이 parts/단계 낱말과 같은 벌인가
    known = set(assigned) | extra | equip
    for st in COMPILED:
        for pk, plabel, pwords in st["parts"]:
            bad = [w for w in pwords if _norm(w) not in known]
            if bad:
                errs.append("%s 부품 %s 의 낱말이 사전에 없다: %s" % (st["key"], pk, bad))
    # ⑤ 팔레트 슬롯이 단계를 모두 덮는가(색은 단계에 고정된다 — dataviz 규격)
    pal_map, pal_err = palette_map()
    errs += pal_err
    keys = [st["key"] for st in COMPILED]
    miss = [k for k in keys if k not in pal_map]
    if miss:
        errs.append("palette.json 슬롯에 없는 단계: %s" % miss)
    # ⑥ 같은 낱말이 여러 단계에 강하게 들어가 있으면 주단계가 흔들린다 — 보고만
    shared = {w: ks for w, ks in assigned.items() if len(ks) > 1}
    rep = {"n_stages": len(COMPILED),
           "n_words": len(assigned),
           "equip_words": len(equip),
           "equip_unassigned": unassigned,
           "equip_unassigned_why": {w: UNASSIGNED_NOTE[w] for w in unassigned},
           "pointer_words": sorted(pointer),
           "extra_words": sorted(w for w in assigned if w in extra),
           "dead_words": dead,
           "shared_words": {w: ks for w, ks in sorted(shared.items())},
           "palette_slots": pal_map,
           "note": ("미분류(equip_unassigned)=EQUIP_WORDS 에 있으나 어느 단계에도 안 붙은 낱말. "
                    "사문화(dead_words)=사전에는 있으나 후보 제품 문구·지정 사유·scan 근거에 "
                    "한 번도 안 걸린 낱말 — KIND 주요제품은 40자 한 줄이라 어휘가 얕다"
                    "(이온주입·정전척·샤워헤드·FOUP 는 국내 원문에 아직 안 나타난다). "
                    "사전에서 지우지 않고 남긴다: scan.json(정기보고서 II절 본문)이 들어오면 "
                    "거기서 걸린다. extra_words=EQUIP_WORDS 에 올려 달라고 요청할 낱말.")}
    if tags is not None:
        rep["tagged"] = sum(1 for t in tags if t["stages"])
        rep["untagged"] = sum(1 for t in tags if not t["stages"])
        per = {}
        for t in tags:
            for s in t["stages"]:
                per[s["key"]] = per.get(s["key"], 0) + 1
        rep["per_stage"] = {st["key"]: per.get(st["key"], 0) for st in COMPILED}
    return rep, errs


def palette_map():
    """palette.json 의 슬롯 → 단계 대응. 반환 ({stage_key: slot}, 오류 목록)."""
    errs = []
    try:
        pal = load_asset("palette.json")
    except Exception as e:                                   # noqa: BLE001
        return {}, ["palette.json 을 읽지 못했다: %s" % e]
    out = {}
    keys = {st["key"] for st in COMPILED}
    for s in pal.get("categorical_order_fixed", []):
        for k in s.get("stages", []):
            if k not in keys:
                errs.append("palette 슬롯 %s 가 없는 단계를 가리킨다: %s" % (s["slot"], k))
            if k in out:
                errs.append("단계 %s 가 슬롯 %s·%s 두 곳에 있다" % (k, out[k], s["slot"]))
            out[k] = s["slot"]
    return out, errs


# ── 산출 ─────────────────────────────────────────────────────

def build():
    stages = []
    for st in COMPILED:
        stages.append({
            "key": st["key"],
            "label": st["label"],
            "flow_order": st["flow_order"],
            "front_back": st["front_back"],
            "words": {"strong": list(dict.fromkeys(_norm(w) for w in st["strong"])),
                      "weak": list(dict.fromkeys(_norm(w) for w in st["weak"])),
                      "not_words": list(dict.fromkeys(_norm(w) for w in st["not_words"])),
                      "not_words_kind": {"span": st["span_not"], "stage": st["hard_not"]},
                      "ctx_required_for": "weak"},
            "parts": [{"key": pk, "label": pl, "words": [_norm(w) for w in pw]}
                      for pk, pl, pw in st["parts"]],
            "note": st["note"],
        })
    return stages


def write(tags, rep):
    write_asset("stages.json", {
        "ver": VER,
        "source_of_truth": ("낱말은 ksemi_universe.EQUIP_WORDS 가 진실의 원천이고 이 파일은 "
                            "단계 배정만 한다. 낱말을 새로 쓰려면 EQUIP_WORDS 에 먼저 넣어라 "
                            "(요청 목록은 unmatched.extra_words)."),
        "spec": "argus/_specs/ksemi.md 「산업 특성 4」 12단계 + service(공정서비스) 1단계",
        "n": len(build()),
        "scoring": {"strong": 3, "weak": 1,
                    "primary": "점수 최대 · 동점은 팹 흐름(flow_order) 앞선 단계",
                    "note": "한 회사가 여러 단계에 걸치는 것이 정상이다 — 단계를 하나로 강제하지 않는다"},
        "ctx_words": [_norm(c) for c in CTX_WORDS],
        "pointer_words": sorted(_norm(w) for w in POINTER_WORDS),
        "stages": build(),
        "unmatched": {k: rep[k] for k in
                      ("equip_unassigned", "equip_unassigned_why", "dead_words",
                       "extra_words", "shared_words", "note")},
    })
    write_asset("stage_tags.json", {
        "ver": VER,
        "n": len(tags),
        "input": ("scan.json(있으면) > universe.json 주요제품 > 스펙 지정 사유. "
                  "어느 것을 썼는지 stages[].source·evidence_source 에 남긴다."),
        "per_stage": rep.get("per_stage", {}),
        "rows": sorted(tags, key=lambda t: t["stock"]),
    })


# ── CLI ──────────────────────────────────────────────────────

def _print_seed_table(tags):
    by = {t["stock"]: t for t in tags}
    print("\n지정 21종목 단계 태그 (눈으로 검토할 표)")
    print("%-7s %-14s %-10s %-34s %s" % ("코드", "이름", "주단계", "단계(점수순)", "출처"))
    for code in sorted(SEED):
        t = by.get(code)
        if not t:
            print("%-7s (universe.json 에 없다)" % code)
            continue
        ks = ",".join(s["key"] for s in t["stages"]) or "—"
        srcs = ",".join(sorted({s["source"] for s in t["stages"]})) or "—"
        print("%-7s %-14s %-10s %-34s %s"
              % (code, t["name"][:14], t["primary"] or "—", ks, srcs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="stages.json·stage_tags.json 생성")
    ap.add_argument("--check", action="store_true", help="교차검증만(쓰지 않는다)")
    ap.add_argument("--classify", help="한 문구 분류 시험")
    ap.add_argument("--tags", action="store_true", help="종목별 태그 전체를 보인다")
    a = ap.parse_args()

    if a.classify:
        rows = classify_full(a.classify)
        print("문구: %r  (반도체 문맥 %s)" % (a.classify, "있음" if has_ctx(a.classify) else "없음"))
        if not rows:
            print("→ 어느 단계에도 안 걸림")
            return 0
        for i, r in enumerate(rows):
            print("%s %-9s %-34s 점수 %2d  낱말 %s"
                  % ("주" if i == 0 else " ", r["key"], r["label"], r["score"],
                     ",".join(r["words"])))
        return 0

    tags, warn = tag_universe()
    rep, errs = cross_check(tags)
    if errs:
        for e in errs:
            print("사전 오류: %s" % e, file=sys.stderr)
        return 2
    if a.write:
        write(tags, rep)
        print("stages.json: 단계 %d · 낱말 %d (부품 %d)"
              % (rep["n_stages"], rep["n_words"],
                 sum(len(st["parts"]) for st in COMPILED)))
        print("stage_tags.json: %d종목 (태그 %d · 무태그 %d)"
              % (len(tags), rep["tagged"], rep["untagged"]))
    print("단계별 종목 수: %s"
          % " ".join("%s=%d" % (k, v) for k, v in rep["per_stage"].items()))
    print("미분류 낱말(EQUIP_WORDS 중 단계 미배정) %d: %s"
          % (len(rep["equip_unassigned"]), ", ".join(rep["equip_unassigned"]) or "없음"))
    print("사문화 낱말(후보 문구에 0건) %d: %s"
          % (len(rep["dead_words"]), ", ".join(rep["dead_words"]) or "없음"))
    print("EQUIP_WORDS 에 올려 달라고 요청할 낱말 %d개" % len(rep["extra_words"]))
    _print_seed_table(tags)
    if a.tags:
        print("\n전체 태그")
        for t in sorted(tags, key=lambda t: t["stock"]):
            print("%-7s %-16s %-10s %-30s %s"
                  % (t["stock"], t["name"][:16], t["primary"] or "—",
                     ",".join(s["key"] for s in t["stages"]) or "—",
                     (t["evidence"] or "")[:46]))
    for w in warn:
        print("경고: %s" % w, file=sys.stderr)
    return 1 if warn else 0


if __name__ == "__main__":
    sys.exit(main())
