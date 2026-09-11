#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ksemi_contracts — 반도체 장비·부품사의 **대형 수주**를 수시공시
「단일판매ㆍ공급계약체결」(publicType I001)에서 모은다.

## 왜 이 공시인가

정기보고서 II-4 수주상황 표는 회사마다 모양이 다르고, 아예 안 적는 회사도 있다.
한미반도체 2026 반기 수주상황은 *"계약 내용은 고객의 투자 정보 등이 노출될 수 있어
공시된 내용 외에 기재하지 않았습니다"* 라고 못 박는다(PROGRESS.md §1-5) — 즉
**계약 상대·금액·기간·공급지역이 남는 곳은 이 수시공시뿐**이다. 그래서 이 모듈이
장비 탭의 「최근 대형 수주」와 「중국 노출」의 원천이다.

## 원문에서 확인한 것 (2026-09-11 실측)

서식이 **두 벌**이고 라벨 이름이 다르다. 한 벌만 보고 파서를 쓰면 나머지가 통째로 빈다.

· 한미반도체 `20260608800436` (유가 = rcpNo[8]=='8', 의무공시)
    `1. 판매ㆍ공급계약 구분`=기타 판매ㆍ공급계약 / `- 체결계약명`=HBM4 제조용 'TC BONDER 4.5
    GRIFFIN' 장비 수주 / `2. 계약내역 · 계약금액(원)`=44,200,000,000 / `최근매출액(원)` /
    `매출액대비(%)`=7.66 / `3. 계약상대`=SK하이닉스(SK Hynix Inc.) / `4. 판매ㆍ공급지역`=한국 /
    `5. 계약기간 시작일/종료일`=2026-06-08 / 2026-09-02 / `7. 계약(수주)일자`.
    같은 회사 `20260114800028` 은 계약명 라벨이 `- 세부내용`, 수주일 라벨이 `7. 계약(수주)일`
    이다 — **같은 회사 안에서도 라벨이 흔들린다**(그래서 라벨 후보를 여러 개 둔다).

· 주성엔지니어링 `20240710900488` (코스닥 = rcpNo[8]=='9', 자율공시 · **EUC-KR**)
    `1. 판매ㆍ공급계약 내용`=반도체 제조장비 / `확정 계약금액`·`조건부 계약금액`·
    `계약금액 총액(원)`=19,426,988,796 / `최근 매출액(원)`=284,745,246,660 /
    `매출액 대비(%)`=6.82 / `3. 계약상대방`=SK하이닉스 / `4. 판매ㆍ공급지역`=**중국** /
    `5. 계약기간` 2024-07-09~2024-08-15 / `7. 판매ㆍ공급방식`(자체생산) / `8. 계약(수주)일자`.
    **덫**: 이 서식에는 `최근 매출액(원)` 행이 **둘**이다 — 하나는 우리 회사(2,847억),
    하나는 계약상대방 SK하이닉스(`-최근 매출액(원)` 32,765,719,000,000 = 32.8조).
    라벨을 정규화하면 앞의 `-`가 떨어져 둘이 같은 키가 되고, 짧은 쪽(상대방)이 이긴다.
    그래서 우리 매출액은 **`계약내역` 아래의 것만** 받는다(`_our_revenue`).

· 정정공시 주성 `20240814902954` [기재정정]
    앞에 `정정일자` / `1. 정정관련 공시서류` / `3. 정정사유`(반입 일정 조정에 따른 납품일자
    변경) / `정정항목·정정전·정정후`(계약기간 종료일 2024-08-15 → 2024-08-20) 표가 붙고,
    **본표는 정정된 값으로 다시 실린다**. 그래서 원 공시를 덮되(`supersedes`) 정정 사실을
    `amendments`(항목·전·후·사유)로 남긴다 — kship 이 801172 에서 겪은 사고(정정본을 별건으로
    세어 척수가 두 배가 된 일)를 되풀이하지 않기 위한 것.

계약금액 단위는 두 서식 모두 **라벨 괄호 안**에 있다(`계약금액(원)`). 표 앞의 `(단위: …)`
캡션이 아니므로 `kce_parse.unit_scale` 로는 못 읽는다 — 라벨에서 읽고, **못 읽으면 금액을
0이나 백만원 가정으로 두지 않고 `amt_mkrw=null` + `unit_seen=false`** 로 남긴다(fail-closed).
외화 표기(`계약금액(USD)`)도 환율을 지어내지 않고 `currency`만 적고 `amt_mkrw=null`.

## 검색 상한 (실측)

`kce_fetch.search_reports` 는 `maxResults=100` 고정이다. 한미반도체를 2021-01-01~2026-09-11
한 번에 검색하면 **정확히 100건**이 오고 가장 오래된 것이 2024-07이다 — 잘린 것이다.
그래서 창을 1년씩 쪼개 검색하고, 100건이 오면 그 창을 **반으로 갈라 다시 검색**한다.

## 캐시 (assets/cache/ — 파일명 규칙)

    assets/cache/contracts/<종목코드>/<rcpNo>.json   공시 1건. 원문 (라벨,값) 쌍 전부(`kv_raw`)
                                                    + 정정표 + 파싱 결과. 파서가 자라면
                                                    재수집 없이 `--write` 만으로 다시 뽑는다.
    assets/cache/search/<종목코드>_<YYYYMMDD>_<YYYYMMDD>.json
                                                    닫힌 창(종료일 < 오늘)의 검색 결과만 캐시.
                                                    오늘이 든 창은 결과가 자라므로 캐시 안 한다.

실패는 캐시하지 않는다(다시 돌리면 빠진 것만 받는다). 한 종목의 실패가 전체를 죽이지
않게 예외는 종목별로 담아 `errors` 로 산출물에 싣는다.

## 사용

    python3 ksemi_contracts.py --only 042700,036930 --write
    python3 ksemi_contracts.py --write                 # 지정 21종목
    python3 ksemi_contracts.py --write --all           # 모집단 전 후보(154종목)
    python3 ksemi_contracts.py --write --since 20210101 --force   # 꼭 필요한 범위만
"""
import argparse
import datetime
import json
import os
import re
import sys
import time

import ksemi_lib
from ksemi_lib import ASSETS, atomic_write, num_of, parse_tables, write_asset
import ksemi_fetch                                    # 인코딩 판정(EUC-KR: rcpNo[8] in 8,9)
from kce_fetch import parallel                        # 레인 기본값을 그대로 쓴다(KCE_LANES 손대지 않음)
from ksemi_universe import EQUIP_WORDS, load as load_universe

CACHE = os.path.join(ASSETS, "cache", "contracts")
SCACHE = os.path.join(ASSETS, "cache", "search")

# 이 두 낱말 중 하나가 제목에 있으면 단일판매·공급계약 계열 공시.
# (해지·철회 공시도 같은 계열이라 같이 받고 `event` 로 갈라 둔다 — 해지를 빼버리면
#  잔고가 과대 계상된다.)
_TITLE = re.compile(r"단일판매|공급계약")
_SEARCH_CAP = 100                                     # kce_fetch.search_reports 의 maxResults


# ── 라벨 정규화 ──────────────────────────────────────────────
# 공시 서식은 라벨 앞에 번호(`7.`)·하이픈(`- 세부내용`)을 붙이고 중점(ㆍ)·공백을 섞는다.
# 같은 항목이 `4. 판매ㆍ공급지역` / `판매·공급지역` 두 꼴로 오므로 그걸 걷어낸 키로 찾는다.
def _norm_key(key):
    return re.sub(r"^\s*\d+\.\s*|^\s*[-–]\s*|[\s　ㆍ·]", "", key or "")


# 라벨 괄호 안 단위 → 백만원 배수. **긴 것부터** 본다('백만원'에 '만원'이 들어있다).
_UNIT_SCALE = [("십억원", 1000.0), ("백만원", 1.0), ("억원", 100.0),
               ("천원", 0.001), ("만원", 0.01), ("원", 1e-6)]
# 원화가 아닌 표기. 환율을 지어내지 않으려고 통화만 기록한다.
_CURRENCY = [("천달러", "USD_K"), ("천USD", "USD_K"), ("USD", "USD"), ("US$", "USD"),
             ("달러", "USD"), ("EUR", "EUR"), ("유로", "EUR"), ("JPY", "JPY"),
             ("엔", "JPY"), ("CNY", "CNY"), ("위안", "CNY")]


def unit_of(label):
    """라벨 → (백만원 배수, 통화, 원문 단위표기). 못 읽으면 (None, None, None)."""
    m = re.search(r"\(([^)]{1,12})\)", label or "")
    if not m:
        return None, None, None
    inner = m.group(1)
    for mark, cur in _CURRENCY:                       # 외화가 원화 배수보다 먼저 — '천달러'의 '원' 오탐 방지
        if mark in inner:
            return None, cur, inner
    for mark, scale in _UNIT_SCALE:
        if mark in inner:
            return scale, "KRW", inner
    return None, None, inner


# ── 원문 표 → (라벨, 값) 쌍 ──────────────────────────────────

def _pairs(html):
    """공시 본문의 (항목, 세부항목, 값) 표 → 원문 (라벨, 값) 쌍 목록. 순서 보존.

    · 값은 마지막 셀. rowspan 으로 항목이 되풀이되므로 앞 셀들을 라벨로 잇는다.
    · 셀이 전부 같은 행은 ① 번호가 붙었으면 **절 제목**(`9. 기타 투자판단…`)이고
      ② 아니면 그 절의 **자유서술 본문**이다. 본문에 'USD 14,083,651.44를 … 환율
      1,379.40 적용' 처럼 금액의 근거가 들어있어 버리면 안 된다 — 직전 절 제목을
      라벨로 삼아 살린다.
    """
    out, pending = [], None
    for t in parse_tables(html):
        rows = list(t["rows"])
        if t.get("cols") and not t.get("inherited"):
            rows.insert(0, list(t["cols"]))           # 머리행이 정정표의 '정정항목/정정전/정정후'일 수 있다
        for row in rows:
            cells = [re.sub(r"\s+", " ", (c or "")).strip() for c in row]
            if not cells:
                continue
            val = cells[-1]
            labels = [c for c in cells[:-1] if c and c != val]
            if not labels:
                if not val:
                    continue
                # 절 제목 판정에 길이를 함께 본다. 주성 20240710900488 의 자유서술 본문은
                # `1. 상기 계약금액은 USD 14,083,651.44를 …` 로 **번호로 시작**해서
                # 번호만 보면 절 제목으로 오인되고 본문(환율 근거)이 통째로 사라진다.
                if (re.match(r"^\s*\d+\.\s*\S", val) and len(val) <= 40) or val.startswith("※"):
                    pending = val                     # 절 제목
                elif pending:
                    out.append((pending, val))
                    pending = None
                continue
            key = " ".join(dict.fromkeys(labels))     # 중복 라벨 제거, 순서 보존
            out.append((key, val))
    return out


def _index(pairs):
    """(라벨, 값) 쌍 → {정규화 라벨: 값} (첫 값 우선, 순서 보존)."""
    kv = {}
    for k, v in pairs:
        kv.setdefault(_norm_key(k), v)
    return kv


def _find(kv, *needles, **kw):
    """needle 을 모두 품은 라벨 중 **가장 짧은** 라벨의 값.

    정정공시는 본표 앞에 `계약기간 종료일 2024-08-15`(정정전 값이 라벨에 붙는다) 같은
    정정표 라벨이 먼저 오는데, 본표의 `계약기간종료일`이 더 짧아 **본표(정정된 값)가 이긴다**.
    `without` 로 특정 낱말이 든 라벨을 뺀다(`계약금액` ↛ `조건부계약금액`).
    """
    without = kw.get("without") or ()
    hits = [(len(k), i, k, v) for i, (k, v) in enumerate(kv.items())
            if all(n in k for n in needles) and not any(w in k for w in without)]
    if not hits:
        return (None, None) if kw.get("with_label") else None
    _, _, k, v = min(hits)
    return (k, v) if kw.get("with_label") else v


def _clean(v):
    """'-'·빈칸은 값이 없는 것으로 본다(0으로 읽지 않는다)."""
    if v is None:
        return ""
    v = v.strip()
    return "" if v in ("-", "–", "—", "") else v


# ── 금액 ─────────────────────────────────────────────────────
# 라벨 후보를 **우선순위대로** 본다. 조건부 계약이 있는 서식에서
# `확정 계약금액`만 읽으면 총액을 놓치므로 `계약금액 총액(원)` 이 1순위다.
_AMT_CANDS = [
    (("계약금액총액",), ()),                            # 코스닥 자율공시 서식(확정+조건부)
    (("계약금액",), ("총액", "확정", "조건부", "최근", "매출")),  # 유가 의무공시 `계약금액(원)`
    (("확정계약금액",), ()),
    (("계약금액",), ("최근", "매출")),                    # 그 밖의 변형
]


def _amount(kv):
    """계약금액 → {amt_mkrw, amt_native, amt_label, amt_unit, currency, unit_seen, amt_note}.

    단위는 라벨 괄호에서 읽는다. 고른 라벨에 단위가 없으면(`확정 계약금액`) 같은 표의
    다른 `계약금액…(원)` 라벨에서 빌려 오고, 그마저 없으면 **fail-closed**:
    `unit_seen=false`, `amt_mkrw=null`. 백만원 가정으로 두면 원 단위 442억이 4.4조가 된다
    (PROGRESS.md §1-5 한미반도체 수주표에서 실제로 겪은 종류의 사고).
    """
    label = val = None
    for needles, without in _AMT_CANDS:
        label, val = _find(kv, *needles, without=without, with_label=True)
        if label and num_of(_clean(val)) is not None:
            break
        label = val = None
    if label is None:
        return {"amt_mkrw": None, "amt_native": None, "amt_label": None,
                "amt_unit": None, "currency": None, "unit_seen": False,
                "amt_note": "계약금액 라벨 매칭 실패"}
    native = num_of(_clean(val))
    scale, cur, seen = unit_of(label)
    note = None
    if scale is None and cur is None:                  # 라벨에 단위 표기가 없다 → 형제 라벨에서 찾는다
        for k in kv:
            if "계약금액" in k and "최근" not in k:
                s2, c2, seen2 = unit_of(k)
                if s2 is not None or c2 is not None:
                    scale, cur, seen = s2, c2, seen2
                    note = "단위는 형제 라벨 '%s' 에서 읽음" % k
                    break
    if cur and cur != "KRW":
        return {"amt_mkrw": None, "amt_native": native, "amt_label": label,
                "amt_unit": seen, "currency": cur, "unit_seen": True,
                "amt_note": "외화 표기 — 환율을 지어내지 않는다"}
    if scale is None:
        return {"amt_mkrw": None, "amt_native": native, "amt_label": label,
                "amt_unit": seen, "currency": None, "unit_seen": False,
                "amt_note": "단위 표기 없음"}
    return {"amt_mkrw": round(native * scale, 3), "amt_native": native,
            "amt_label": label, "amt_unit": seen, "currency": "KRW",
            "unit_seen": True, "amt_note": note}


# ── 계약상대 ─────────────────────────────────────────────────
# 익명 표기 — **추정 금지**(COMMON §0-6). 아래 꼴이면 익명이라 적고 이름을 비운다.
_ANON = re.compile(r"비공개|미공개|공시유보|유보|영업\s*비밀|영업상|익명|비밀유지|NDA"
                   r"|^[A-Z]\s*사$|고객사|거래처|수요처|업체$|제조사$|제조업체|반도체\s*회사"
                   r"|국내\s*(?:소재)?\s*(?:반도체)?\s*(?:법인|기업|회사|업체)"
                   r"|해외\s*(?:소재)?\s*(?:반도체)?\s*(?:법인|기업|회사|업체)", re.I)

# 판매·공급지역의 중국 노출(스펙 「국산화·수출」 축). 홍콩·대만은 중국으로 세지 않는다.
_CN = re.compile(r"중국|중화인민|China|PRC|시안|西安|우시|无锡|無錫|청두|成都|다롄|大連", re.I)


def _party(kv):
    raw = _clean(_find(kv, "계약상대"))                  # '계약상대' / '계약상대방' 둘 다 잡는다
    anon = bool(raw) and bool(_ANON.search(raw))
    return {"party": "" if anon else raw, "party_raw": raw, "party_anon": anon or not raw}


def _our_revenue(kv, pairs):
    """우리 회사의 최근 매출액(원). **계약상대방의 매출액과 섞이면 안 된다.**

    주성엔지니어링 20240710900488 은 `최근 매출액(원)` 행이 둘이다(우리 2,847억 /
    SK하이닉스 32.8조). 정규화하면 상대방 라벨(`-최근 매출액(원)`)이 더 짧아 그쪽이
    이긴다 — 그래서 `계약내역` 아래의 것만 받고, 그 꼴이 없으면 **원문 라벨이
    하이픈으로 시작하지 않는 것**만 받는다.
    """
    v = _find(kv, "계약내역", "최근매출액")
    if v is None:
        for k, val in pairs:
            if k.lstrip().startswith(("-", "–")):
                continue
            if "최근" in k and "매출액" in k:
                v = val
                break
    return num_of(_clean(v)) if v is not None else None


def _party_revenue(pairs):
    """계약상대방의 최근 매출액(원) — 원문 라벨이 `-최근 매출액(원)` 인 것."""
    for k, val in pairs:
        if k.lstrip().startswith(("-", "–")) and "최근" in k and "매출액" in k:
            return num_of(_clean(val))
    return None


# ── 정정 ─────────────────────────────────────────────────────

def _amendments(html):
    """정정표(`정정항목 / 정정전 / 정정후`) → [{item, before, after}].

    정정공시는 본표를 정정된 값으로 다시 싣기 때문에 본표만 읽어도 값은 맞다.
    이 표는 **무엇이 왜 바뀌었는지**를 남기기 위해 따로 뽑는다.
    """
    out = []
    for t in parse_tables(html):
        rows = list(t["rows"])
        if t.get("cols") and not t.get("inherited"):
            rows.insert(0, list(t["cols"]))
        seen_head = False
        for row in rows:
            cells = [re.sub(r"\s+", " ", (c or "")).strip() for c in row]
            uniq = list(dict.fromkeys([c for c in cells if c]))
            if len(uniq) >= 3 and uniq[0] == "정정항목" and "정정전" in uniq[1]:
                seen_head = True
                continue
            if seen_head and len(uniq) >= 2:
                out.append({"item": uniq[0], "before": uniq[1] if len(uniq) > 2 else "",
                            "after": uniq[-1]})
    return out


# ── 계약 내용(장비 이름) ────────────────────────────────────
# 공정 단계 사전은 `build_dicts.py` 의 몫이다. 어휘를 여기 따로 적으면 한쪽만 고쳐지는
# 날이 온다(ksemi_universe 주석) — 그래서 **같은 EQUIP_WORDS 를 import 해서** 히트만 남긴다.
def _content_words(text):
    """계약 내용에서 장비·공정 어휘 히트. 공백은 무시한다 — 사전의 `반도체 제조 장비` 와
    원문의 `반도체 제조장비`(주성 20240710900488)는 같은 말인데 글자 그대로 비교하면
    한 건도 안 걸린다."""
    t = text or ""
    tl = t.lower()
    ts = re.sub(r"\s+", "", t)
    tsl = ts.lower()
    out = []
    for w in EQUIP_WORDS:
        ws = re.sub(r"\s+", "", w)
        if (w.lower() in tl or ws.lower() in tsl) if w.isascii() else (w in t or ws in ts):
            out.append(w)
    return out


def _event(title):
    """제목 → 사건 종류. 해지·철회를 체결과 섞으면 수주가 과대 계상된다."""
    t = title or ""
    if "해지" in t or "해제" in t:
        return "해지"
    if "철회" in t or "취소" in t:
        return "철회"
    return "체결"


def parse_contract(html, rcp, title, stock, name=""):
    """공시 본문 HTML → 계약 1건 레코드. 원문 (라벨,값)은 `kv_raw` 에 전부 남긴다."""
    pairs = _pairs(html)
    kv = _index(pairs)
    rec = {
        "stock": stock, "name": name, "rcp": rcp, "title": title,
        "filed": "%s-%s-%s" % (rcp[:4], rcp[4:6], rcp[6:8]),   # 공시일자 = 접수번호 앞 8자리
        "event": _event(title),
        "corrected": "정정" in (title or ""),
        "voluntary": "자율공시" in (title or ""),
        "kind": _clean(_find(kv, "판매공급계약구분")),
        # 계약 내용 = 장비 이름. 서식마다 라벨이 다르다(내용 / 체결계약명 / 세부내용).
        "content": (_clean(_find(kv, "판매공급계약내용")) or _clean(_find(kv, "체결계약명"))
                    or _clean(_find(kv, "세부내용")) or _clean(_find(kv, "계약명"))),
        "party_rev_krw": _party_revenue(pairs),
        "rev_recent_krw": _our_revenue(kv, pairs),
        "rev_ratio_pct": num_of(_clean(_find(kv, "매출액대비") or _find(kv, "매출액대비(%)"))),
        "region": _clean(_find(kv, "판매공급지역") or _find(kv, "공급지역")),
        "start": _clean(_find(kv, "계약기간", "시작") or _find(kv, "시작일")),
        "end": _clean(_find(kv, "계약기간", "종료") or _find(kv, "종료일")),
        "signed": _clean(_find(kv, "계약(수주)일") or _find(kv, "수주일자")
                         or _find(kv, "계약일자")),
        "conditional": _clean(_find(kv, "조건부계약여부")),
        "advance": _clean(_find(kv, "선급금")),
        "payterm": _clean(_find(kv, "대금지급")),
        "withheld": _clean(_find(kv, "유보사유")),
        "note": _clean(_find(kv, "기타", "중요") or _find(kv, "기타", "참고")),
        "amend_reason": _clean(_find(kv, "정정사유")),
        "amend_date": _clean(_find(kv, "정정일자")),
    }
    rec.update(_amount(kv))
    rec.update(_party(kv))
    rec["region_cn"] = bool(_CN.search(rec["region"] or ""))
    rec["content_words"] = _content_words(rec["content"] + " " + (rec["note"] or ""))
    rec["amendments"] = _amendments(html) if rec["corrected"] else []
    # 라벨 매칭이 하나도 안 된 문서(서식이 바뀐 경우)는 조용히 빈 레코드로 두지 않는다.
    rec["parse_flags"] = [f for f in (
        None if rec["content"] else "계약내용 라벨 매칭 실패",
        None if rec["party_raw"] else "계약상대 라벨 매칭 실패",
        None if rec["unit_seen"] else (rec.get("amt_note") or "금액 단위 미확인"),
        None if rec["signed"] or rec["start"] else "계약일자 라벨 매칭 실패",
    ) if f]
    rec["kv"] = _kv_dict(pairs)
    return rec


def _kv_dict(pairs):
    """원문 라벨 → 값 dict. 같은 라벨이 되풀이되면 `라벨 (2)` 로 붙여 값을 잃지 않는다."""
    out = {}
    for k, v in pairs:
        if k in out and out[k] != v:
            i = 2
            while "%s (%d)" % (k, i) in out:
                i += 1
            out["%s (%d)" % (k, i)] = v
        else:
            out.setdefault(k, v)
    return out


# ── 검색 (창 쪼개기) ────────────────────────────────────────

def _ymd(s):
    return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def _search_window(key, start, end, log):
    """한 창을 검색한다. 닫힌 창(종료일 < 오늘)만 캐시한다."""
    today = time.strftime("%Y%m%d")
    path = os.path.join(SCACHE, "%s_%s_%s.json" % (key, start, end))
    closed = end < today
    if closed and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return [tuple(x) for x in json.load(f)]
    res = ksemi_fetch.search_reports(key, start, end, "I001")
    if closed:
        os.makedirs(SCACHE, exist_ok=True)
        atomic_write(path, json.dumps(res, ensure_ascii=False) + "\n")
    return res


def search_all(key, start, end, log=sys.stderr):
    """창을 1년씩 쪼개 검색하고, 상한(100건)에 닿은 창은 반으로 갈라 다시 검색한다.

    `search_reports` 는 maxResults=100 고정이라 한 번에 5년을 검색하면 잘린다
    (한미반도체 2021~2026: 정확히 100건, 최고(最古) 2024-07 — 모듈 docstring 참조).
    """
    out, todo = {}, []
    a, b = _ymd(start), _ymd(end)
    y = a
    while y <= b:
        z = min(datetime.date(y.year, 12, 31), b)
        todo.append((y, z))
        y = z + datetime.timedelta(days=1)
    while todo:
        s, e = todo.pop(0)
        res = _search_window(key, s.strftime("%Y%m%d"), e.strftime("%Y%m%d"), log)
        if len(res) >= _SEARCH_CAP and (e - s).days > 2:
            mid = s + (e - s) // 2                       # 잘렸다 — 반으로 갈라 다시
            log.write("[split] %s %s~%s %d건(상한) → 분할\n"
                      % (key, s, e, len(res)))
            todo += [(s, mid), (mid + datetime.timedelta(days=1), e)]
            continue
        for rcp, title in res:
            out.setdefault(rcp, title)
    return sorted(out.items(), reverse=True)


# ── 수집 ─────────────────────────────────────────────────────

def collect_stock(stock, name, start, end, force=False, log=sys.stderr):
    """한 종목의 계약 공시를 캐시에 채운다. 반환 (공시수, 캐시수, 실패수)."""
    hits = [(r, t) for r, t in search_all(stock, start, end, log) if _TITLE.search(t or "")]
    got = fail = 0
    for rcp, title in hits:
        path = os.path.join(CACHE, stock, rcp + ".json")
        if os.path.exists(path) and not force:
            got += 1
            continue
        try:
            nodes = ksemi_fetch.toc(rcp)
            if not nodes:
                raise RuntimeError("목차 없음")
            html = ksemi_fetch.fetch_section(nodes[0])
            rec = parse_contract(html, rcp, title, stock, name)
            rec["kv_raw"] = _pairs(html)                 # 원문 (라벨,값) 쌍 전부 — 재수집 없이 재파싱
        except Exception as e:                           # 일시 실패는 캐시하지 않는다
            fail += 1
            log.write("[warn] %s %s %s: %s\n" % (stock, rcp, type(e).__name__, e))
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        atomic_write(path, json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
        got += 1
    return len(hits), got, fail


def collect(stocks, start, end, force=False, log=sys.stderr):
    """종목별로 수집. 한 종목이 터져도 나머지는 간다(예외를 종목별로 담는다).

    DART는 IP 단위로 막는다 — 레인은 `kce_fetch` 기본값을 그대로 쓰고(총 요청률은
    프로세스 사이 파일 락이 묶는다) 여기서 레인 수를 늘리지 않는다.
    """
    errors = []

    def one(row):
        return collect_stock(row["stock"], row.get("name", ""), start, end, force, log)

    def done(i, row, res):
        if isinstance(res, Exception):
            errors.append({"stock": row["stock"], "name": row.get("name", ""),
                           "error": "%s: %s" % (type(res).__name__, res)})
            log.write("[error] %s %s\n" % (row["stock"], res))
        else:
            n, got, fail = res
            log.write("%s %-14s 계약공시 %2d건 · 캐시 %2d · 실패 %d\n"
                      % (row["stock"], row.get("name", "")[:12], n, got, fail))
        log.flush()

    parallel(stocks, one, on_done=done)
    return errors


# ── 빌드 ─────────────────────────────────────────────────────

def _reparse(rec):
    """캐시 레코드를 **현재 파서로** 다시 뽑는다(원문 쌍이 있으면).

    캐시는 원문 보존이 목적이지 판정 보존이 아니다 — 어휘·단위 규칙이 자라면
    재수집 없이 반영돼야 한다(COMMON §0-4).
    """
    pairs = rec.get("kv_raw")
    if not pairs:
        return rec
    pairs = [(k, v) for k, v in pairs]
    kv = _index(pairs)
    out = dict(rec)
    out.update({
        "kind": _clean(_find(kv, "판매공급계약구분")),
        "content": (_clean(_find(kv, "판매공급계약내용")) or _clean(_find(kv, "체결계약명"))
                    or _clean(_find(kv, "세부내용")) or _clean(_find(kv, "계약명"))),
        "party_rev_krw": _party_revenue(pairs),
        "rev_recent_krw": _our_revenue(kv, pairs),
        "rev_ratio_pct": num_of(_clean(_find(kv, "매출액대비"))),
        "region": _clean(_find(kv, "판매공급지역") or _find(kv, "공급지역")),
        "start": _clean(_find(kv, "계약기간", "시작") or _find(kv, "시작일")),
        "end": _clean(_find(kv, "계약기간", "종료") or _find(kv, "종료일")),
        "signed": _clean(_find(kv, "계약(수주)일") or _find(kv, "수주일자")
                         or _find(kv, "계약일자")),
        "conditional": _clean(_find(kv, "조건부계약여부")),
        "advance": _clean(_find(kv, "선급금")),
        "payterm": _clean(_find(kv, "대금지급")),
        "withheld": _clean(_find(kv, "유보사유")),
        "note": _clean(_find(kv, "기타", "중요") or _find(kv, "기타", "참고")),
        "amend_reason": _clean(_find(kv, "정정사유")),
        "amend_date": _clean(_find(kv, "정정일자")),
        "event": _event(rec.get("title")),
        "kv": _kv_dict(pairs),
    })
    out.update(_amount(kv))
    out.update(_party(kv))
    out["region_cn"] = bool(_CN.search(out["region"] or ""))
    out["content_words"] = _content_words(out["content"] + " " + (out["note"] or ""))
    out["parse_flags"] = [f for f in (
        None if out["content"] else "계약내용 라벨 매칭 실패",
        None if out["party_raw"] else "계약상대 라벨 매칭 실패",
        None if out["unit_seen"] else (out.get("amt_note") or "금액 단위 미확인"),
        None if out["signed"] or out["start"] else "계약일자 라벨 매칭 실패",
    ) if f]
    return out


def _key(rec):
    """같은 계약을 가리키는 키. 정정본이 원본을 찾아가는 데 쓴다.

    계약(수주)일자는 정정 대상이 되는 일이 드물고(납기·금액이 바뀐다), 계약내용은
    서식이 달라도 같은 문구로 다시 실린다. 그래도 어긋날 수 있으므로
    `_merge` 가 (종목, 수주일) 폴백을 하나 더 둔다.
    """
    return (rec["stock"], rec.get("signed") or rec.get("start") or "",
            re.sub(r"\s+", "", rec.get("content") or ""))


def _merge(recs):
    """정정본이 원 공시를 **덮되 정정 사실을 남긴다**.

    kship 이 801172 에서 겪은 사고: 정정본을 별건으로 세어 같은 계약이 두 번 잡혔다.
    여기서는 rcpNo 오름차순으로 훑어 뒤(정정본)가 앞을 덮고, 덮인 rcpNo·정정항목·
    정정사유를 `supersedes`/`amendments` 에 쌓는다. 원본을 못 찾은 정정본은 버리지
    않고 `amend_unmatched` 플래그를 달아 화면에서 보이게 한다(fail-closed).
    """
    by, order = {}, []
    for r in sorted(recs, key=lambda r: r["rcp"]):
        k = _key(r)
        prev = by.get(k)
        if prev is None and r.get("corrected"):
            # 정정으로 계약내용 문구까지 바뀐 경우 — (종목, 수주일)이 하나뿐이면 그것으로 본다
            cands = [kk for kk in by if kk[0] == r["stock"] and kk[1] == k[1] and kk[1]]
            if len(cands) == 1:
                prev, k = by[cands[0]], cands[0]
        if prev is not None:
            hist = list(prev.get("supersedes") or [])
            hist.append(prev["rcp"])
            am = list(prev.get("amendments") or []) + list(r.get("amendments") or [])
            log = list(prev.get("amend_log") or [])
            if r.get("corrected"):
                log.append({"rcp": r["rcp"], "date": r.get("amend_date") or r["filed"],
                            "reason": r.get("amend_reason", ""),
                            "items": r.get("amendments") or []})
            r = dict(r)
            r["supersedes"] = hist
            r["amendments"] = am
            r["amend_log"] = log
            by[k] = r
            continue
        if r.get("corrected"):
            r = dict(r)
            r["amend_unmatched"] = True
            r["amend_log"] = [{"rcp": r["rcp"], "date": r.get("amend_date") or r["filed"],
                               "reason": r.get("amend_reason", ""),
                               "items": r.get("amendments") or []}]
        by[k] = r
        order.append(k)
    return [by[k] for k in order if k in by]


def build(stocks, start, end, keep_kv=True):
    """캐시 → contracts.json. 반환 rows."""
    rows, missing = [], []
    for row in stocks:
        st = row["stock"]
        d = os.path.join(CACHE, st)
        if not os.path.isdir(d):
            missing.append(st)
            continue
        recs = []
        for f in sorted(os.listdir(d)):
            if not f.endswith(".json"):
                continue
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                rec = json.load(fh)
            rec["name"] = row.get("name", rec.get("name", ""))
            recs.append(_reparse(rec))
        rows.extend(_merge(recs))
    rows.sort(key=lambda r: (r["stock"], r["filed"], r["rcp"]))
    for r in rows:
        r.pop("kv_raw", None)
        if not keep_kv:
            r.pop("kv", None)
    return rows, missing


def write(rows, start, end, errors=()):
    write_asset("contracts.json", {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "window": [start, end],
        "n": len(rows),
        "rows": rows,
        "errors": list(errors),
    })


# ── 집계 (화면이 쓴다) ──────────────────────────────────────

def by_stock(rows):
    """종목별 계약 목록. 각 목록은 **공시일 내림차순**(같은 날은 rcpNo 내림차순)."""
    out = {}
    for r in rows:
        out.setdefault(r["stock"], []).append(r)
    for st in out:
        out[st].sort(key=lambda r: (r.get("filed") or "", r["rcp"]), reverse=True)
    return out


def recent(rows, n=10, min_mkrw=None, events=("체결",)):
    """최근 대형 수주 n건 — 허브 화면이 쓴다.

    '최근'이 1순위(공시일 내림차순)이고 '대형'은 `min_mkrw`(백만원) 문턱으로 거른다.
    금액 단위를 못 읽은 건(`unit_seen=false`)은 문턱을 줄 때 **조용히 통과시키지 않고
    제외**한다 — 금액을 0으로 가정하지 않는다는 뜻이다(fail-closed). 해지·철회 공시는
    기본값에서 빠진다(`events=None` 이면 전부).
    """
    sel = [r for r in rows if (events is None or r.get("event") in events)]
    if min_mkrw is not None:
        sel = [r for r in sel if r.get("amt_mkrw") is not None and r["amt_mkrw"] >= min_mkrw]
    sel.sort(key=lambda r: (r.get("filed") or "", r["rcp"]), reverse=True)
    return sel[:n] if n else sel


def load():
    """assets/contracts.json (없으면 빈 구조)."""
    if not ksemi_lib.has_asset("contracts.json"):
        return {"n": 0, "rows": []}
    return ksemi_lib.load_asset("contracts.json")


# ── CLI ─────────────────────────────────────────────────────

def _stocks(arg_only, use_all):
    uni = load_universe()
    if arg_only:
        want = [s.strip() for s in arg_only.split(",") if s.strip()]
        byst = {r["stock"]: r for r in uni}
        return [byst.get(s) or {"stock": s, "name": ""} for s in want]
    if use_all:
        return uni
    return [r for r in uni if r.get("source") == "지정"]


def main():
    ap = argparse.ArgumentParser(description="반도체 장비사 단일판매ㆍ공급계약 공시 수집")
    ap.add_argument("--write", action="store_true", help="assets/contracts.json 갱신")
    ap.add_argument("--only", help="종목코드 쉼표 목록 (예: 042700,036930)")
    ap.add_argument("--all", action="store_true", help="모집단 전 후보(기본은 지정 21종목)")
    ap.add_argument("--since", default="20210101", help="시작일 YYYYMMDD (기본 최근 5년)")
    ap.add_argument("--until", default=time.strftime("%Y%m%d"))
    ap.add_argument("--force", action="store_true", help="캐시 무시 재수집 — 꼭 필요한 범위만")
    ap.add_argument("--no-collect", action="store_true", help="캐시만으로 빌드(DART 미접속)")
    a = ap.parse_args()
    stocks = _stocks(a.only, a.all)
    errors = []
    if not a.no_collect:
        errors = collect(stocks, a.since, a.until, a.force)
    rows, missing = build(stocks, a.since, a.until)
    for st in missing:
        errors.append({"stock": st, "error": "캐시 없음(수집 실패 또는 계약공시 0건)"})
    if a.write:
        write(rows, a.since, a.until, errors)
    bs = by_stock(rows)
    flagged = [r for r in rows if r.get("parse_flags")]
    print("계약 %d건 / %d종목 · 정정반영 %d · 금액단위 미확인 %d · 중국 %d · 익명상대 %d"
          % (len(rows), len(bs), sum(1 for r in rows if r.get("supersedes")),
             sum(1 for r in rows if not r.get("unit_seen")),
             sum(1 for r in rows if r.get("region_cn")),
             sum(1 for r in rows if r.get("party_anon"))))
    for st, lst in sorted(bs.items(), key=lambda kv: -len(kv[1]))[:5]:
        print("  %s %-12s %2d건" % (st, (lst[0].get("name") or "")[:12], len(lst)))
    for r in recent(rows, 8):
        print("  %s %-10s %-12s %-34s %12s백만 %-10s %s"
              % (r["filed"], r["stock"], (r.get("name") or "")[:10], (r.get("content") or "")[:34],
                 format(r["amt_mkrw"], ",.0f") if r.get("amt_mkrw") is not None else "미확인",
                 (r.get("party") or ("익명" if r.get("party_anon") else ""))[:10],
                 r.get("region") or ""))
    if flagged:
        print("[flag] 파싱 플래그 %d건:" % len(flagged), file=sys.stderr)
        for r in flagged[:20]:
            print("   %s %s %s" % (r["stock"], r["rcp"], r["parse_flags"]), file=sys.stderr)
    if errors:
        print("[error] %d건: %s" % (len(errors), errors[:5]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
