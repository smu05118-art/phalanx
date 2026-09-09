#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_series — 신규 편입사의 분기 시계열을 DART 원문에서 처음부터 만든다.

원본 7사는 encprojects 복제본이 시드(19분기 + S-curve 예측 + 실적 CSV)를 갖고 있지만,
새로 편입한 회사에는 시드가 없다. 여기서는 **원문이 지지하는 것만** 만든다 —
분기별 수주표를 모아 사업장을 이름으로 이어 붙인 실측 시계열. 예측·백테스트·
실적대비는 만들지 않는다(없는 자산을 흉내 내면 화면이 거짓말을 한다).

수집은 디스크에 캐시되므로 중단해도 이어서 돌릴 수 있다.

사용:
    python3 kce_series.py --collect --from 2024Q3 --to 2026Q2      # 전 종목 수집
    python3 kce_series.py --collect --only 009410 --from 2024Q3 --to 2026Q2
    python3 kce_series.py --build --only 009410                    # 캐시 → DATA
"""
import argparse
import json
import os
import re
import sys
import time

from kce_lib import (CORP, atomic_write, latest_quarter, num_of, q_range,
                     report_kind)
from kce_fetch import (fetch_section, find_sections, parallel, pick_report,
                       search_reports, toc)
from kce_parse import parse_ii4
from kce_probe import grain_of, report_window
from kce_universe import load as load_universe

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "assets", "series_cache")
KCE = os.path.dirname(HERE)

# 사업장 이름 정규화: 공백·괄호주석·구두점을 걷어 분기 간 동일 현장을 잇는다.
# `?`·`＆`까지 거르는 이유: 원문 인코딩이 분기마다 흔들려 같은 이름이 다르게 찍힌다
# (계룡건설 `경기 성남 삼두아파트, 은영빌라` → 다음 분기 `삼두아파트? 은영빌라`).
_NM_DROP = re.compile(r"[\s()（）\[\]{}·ㆍ,，.\-–—_/\\'\"?？!~～∼〜:：;；&＆+＋*※#|]+")
_NM_TAIL = re.compile(r"(공사|현장|사업|신축|외\d+건)+$")
# 이름 끝에 붙는 주석 표시. HL D&I는 분기마다 전 현장 이름 끝에 `(A)`를 달았다 뗐다
# 한다(2025Q1·2025Q3·2026Q2에만 있다) — 이름의 일부로 보면 그 분기마다 27개 현장이
# 통째로 새 현장이 된다. 한글은 남긴다(`(옵션)`·`(파우더)`는 진짜 이름 조각이다).
_NM_MARK = re.compile(r"[\s]*[(（]\s*[A-Za-z0-9*※]{1,2}\s*[)）]\s*$")


def nm_key(s):
    """현장 이름 매칭 키. 표기 흔들림('OO 신축공사'/'OO신축 공사')을 흡수한다."""
    t = _NM_MARK.sub("", (s or "").strip())
    t = _NM_DROP.sub("", t).lower()
    return _NM_TAIL.sub("", t) or t


def _norm_date(s):
    """'2019.12'·'201506'·'24년12월'·'25.12' → 'YYYY-MM'. 실패 시 None."""
    t = re.sub(r"[\s]", "", s or "")
    m = re.match(r"^((?:19|20)\d{2})[-./년]?(\d{1,2})?", t)
    if m:
        mo = int(m.group(2) or 1)
        return "%s-%02d" % (m.group(1), min(max(mo, 1), 12))
    m = re.match(r"^(\d{2})[-./년](\d{1,2})", t)
    if m:
        return "20%s-%02d" % (m.group(1), min(max(int(m.group(2)), 1), 12))
    return None


# 착공일을 **일자까지** 읽는다. 구분자가 둘 다 있거나(2026.05.06) 8자리 붙여쓰기
# (20260506)일 때만 일자로 인정한다 — '2019.12'를 12월이 아니라 1월 2일로 읽는
# 백트래킹 사고를 막기 위해 구분자 개수를 강제한다.
_DAY_SEP = re.compile(r"^((?:19|20)\d{2})[-./년](\d{1,2})[-./월](\d{1,2})(?!\d)")
_DAY_SEP2 = re.compile(r"^(\d{2})[-./년](\d{1,2})[-./월](\d{1,2})(?!\d)")
_DAY_RUN = re.compile(r"^((?:19|20)\d{2})(\d{2})(\d{2})(?!\d)")


def _norm_day(s):
    """'2026.05.06'·'2026-05-06'·'20260506' → 'YYYY-MM-DD'. 일자가 없으면 None.

    월까지만 보면 **같은 달에 들어온 다른 계약이 한 칸으로 뭉개진다**. 남화토건
    2026Q2가 그랬다 — {토목·담양군·2026.05.06, 잔고 2,239}과 {토목·담양군·
    2026.05.13, 잔고 1,890}이 둘 다 `토목|담양군|2026-05`라 큰 쪽만 남고
    18.9억이 통째로 사라졌다(대조 97.7%의 정확한 원인).
    """
    t = re.sub(r"[\s]", "", s or "")
    for pat, pre in ((_DAY_SEP, ""), (_DAY_RUN, ""), (_DAY_SEP2, "20")):
        m = pat.match(t)
        if not m:
            continue
        mo, dy = int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= dy <= 31:
            return "%s%s-%02d-%02d" % (pre, m.group(1), mo, dy)
    return None


def site_key(row):
    """**한 분기 표 안에서** 서로 다른 계약을 절대 섞지 않는 최강 식별키.

    이름만으로 잡으면 안 된다 — 남화토건처럼 수주표에 현장명 열이 아예 없고 `품목`이
    '토목/건축' 공종뿐인 회사가 있다(기업공시서식 표준 양식은 품목·발주처·수주일자로만
    계약을 구분한다). 이름만 쓰면 20개 계약이 2개로 뭉개지고, 같은 키는 최댓값 하나만
    남기므로 **나머지 잔고가 통째로 사라진다**(남화토건 실측 잔고의 41%만 남았다).

    그래서 이름·발주처·착공일을 함께 쓰되 착공일은 **일자까지** 본다(_norm_day).
    분기를 가로지르는 연결은 이 키의 정확 일치에 맡기지 않는다 — 원문이 분기마다
    착공일이나 발주처 표기를 고쳐 적으면 같은 계약이 새 현장으로 끊기기 때문에,
    연결은 _LINK 사슬이 약한 신호까지 훑어 1:1로 맺는다.
    """
    return "|".join((nm_key(row.get("nm")),
                     nm_key(row.get("cl")),
                     _norm_day(row.get("sd")) or _norm_date(row.get("sd")) or ""))


def _ident(row):
    """계약 동일성 판단에 쓰는 필드 묶음. _LINK의 각 수준이 여기서 키를 만든다."""
    return {"nm": nm_key(row.get("nm")), "cl": nm_key(row.get("cl")),
            "d": _norm_day(row.get("sd")) or "",
            "m": _norm_date(row.get("sd")) or "",
            "em": _norm_date(row.get("ed")) or "",
            "amt": row.get("amt")}


# 분기를 가로질러 같은 계약을 잇는 후보키 — **강한 신호부터** 훑는다.
# 원문은 분기마다 표기를 조금씩 고쳐 적는다. 한 가지 키만 쓰면 그 한 필드가 흔들리는
# 순간 계약이 끊겨 새 현장이 된다(실측: 2,577현장 중 664개가 8분기 중 1분기만 관측.
# HJ중공업 185중 98, HL D&I 108중 57). 그래서 흔들린 필드를 하나씩 빼 가며 잇되,
# 약한 수준일수록 다른 필드의 동시 일치를 요구해 오연결을 막는다.
# `g`는 회사 안에서 **한 표에 두 번 이상 나오는 이름**(공종뿐인 이름) 집합이다 —
# 그런 이름은 계약을 식별하지 못하므로 이름만 쓰는 수준에서 제외한다.
_LINK = (
    # 이름·발주처·착공일자까지 같다 — 사실상 확정
    ("nm·발주처·착공일", lambda f, g: (f["nm"], f["cl"], f["d"])
        if f["nm"] and f["d"] else None),
    # 원문이 일자 표기만 다듬은 경우(종전 키와 같은 강도)
    ("nm·발주처·착공월", lambda f, g: (f["nm"], f["cl"], f["m"])
        if f["nm"] and f["m"] else None),
    # 착공일을 아예 고쳐 적은 경우 — 이름과 발주처가 함께 같으면 잇는다
    ("nm·발주처", lambda f, g: (f["nm"], f["cl"])
        if f["nm"] and f["cl"] else None),
    # 발주처 표기를 고쳐 적은 경우 — 이름이 계약을 식별하는 회사에서만
    ("nm·착공월", lambda f, g: (f["nm"], f["m"])
        if f["nm"] and f["m"] and f["nm"] not in g else None),
    # 현장명을 고쳐 적은 경우 — 발주처·착공일자·도급액이 **모두** 같아야 잇는다
    ("발주처·착공일·도급액", lambda f, g: (f["cl"], f["d"], f["amt"])
        if f["cl"] and f["d"] and f["amt"] else None),
    # 현장명을 고쳐 적은 경우 2 — 착공월과 완공예정월이 함께 같아야 잇는다
    ("발주처·착공월·완공월", lambda f, g: (f["cl"], f["m"], f["em"])
        if f["cl"] and f["m"] and f["em"] else None),
    # 발주처·착공일이 함께 흔들려도 이름이 고유하면 잇는다
    ("nm", lambda f, g: (f["nm"],) if f["nm"] and f["nm"] not in g else None),
    # 이름도 발주처도 못 쓰는 마지막 수단 — 계룡건설은 발주처 열이 아예 비어 있고
    # 원문 인코딩이 흔들려 이름도 분기마다 다르게 찍힌다. 착공월·완공예정월·도급액이
    # **셋 다** 같으면 같은 계약으로 본다(실측 8,375행에서 한 분기 안 충돌 0건).
    ("착공월·완공월·도급액", lambda f, g: (f["m"], f["em"], f["amt"])
        if f["m"] and f["em"] and f["amt"] else None),
)


def _amt_dist(a, b):
    """도급액이 얼마나 다른가(0~1). 약한 수준에서 짝을 고를 때의 거리다 —
    계약금액은 계약이 끝날 때까지 거의 그대로라 동일성 신호로 쓸 만하다."""
    a, b = a or 0, b or 0
    if a == b:
        return 0.0
    if a <= 0 or b <= 0:
        return 1.0
    return abs(a - b) / float(max(a, b))


def _generic_names(got):
    """이름만으로는 계약을 못 가르는 이름들.

    **한 표 안에서** 같은 이름이 서로 다른 계약(식별키가 다른 행)으로 두 번 이상
    나오면 그 이름은 공종·품목 라벨이다(남화토건 `토목`, 대명에너지 `O&M용역`).
    회사 전체를 한 임계값으로 자르지 않고 이름별로 재는 이유는, 개별 현장명을
    제대로 적으면서 몇 줄만 공종으로 적는 회사가 섞여 있기 때문이다
    (금호건설 1,086행 중 11행, HL D&I 259행 중 10행).
    """
    bad = set()
    for d in got:
        for tab in (d.get("tables") or [{"rows": d.get("rows") or []}]):
            first = {}
            for row in tab["rows"]:
                if is_total_row(row) or is_agg_row(row):
                    continue
                k = nm_key(row.get("nm"))
                if not k:
                    continue
                sk = site_key(row)
                if first.setdefault(k, sk) != sk:
                    bad.add(k)
    return bad


# 소계 행 판별. 회사마다 표기가 제각각이라 '합계로 끝나는가'만 보면 뚫린다 —
# 금호건설은 `총계(E=C+D)`·`국내합계(C=A+B)`·`국내건축(관급+민간) 합계(B)`·
# `국내토목 계(A)`로 적는다. 이 6행이 현장으로 섞여 수주잔고가 9.5조 → 42.8조가 됐다.
#  · 합계/총계/소계/중계/누계는 어디에 붙어도 소계로 본다(뒤에 `(B)` 같은 주석 허용)
#  · 낱자 `계`는 앞이 공백·괄호일 때만 — '기본설계'·'실시설계'를 소계로 오인하지 않기 위해
#  · 합계/총계/소계/중계/누계는 위치 무관. 다만 **뒤에 한글이 이어지면 다른 낱말**이다
#    (`종합계획`·`누계획`) — 그때는 소계가 아니다.
#  · 낱자 `계`는 앞이 공백·괄호일 때만 (`기본설계`·`실시설계`를 지키기 위해).
#  · 공백 표기가 제각각이라(`합 계`) 공백 제거형과 보존형을 **둘 다** 본다.
_TOTAL_STRICT = re.compile(r"(?:합계|총계|소계|중계|누계)(?![가-힣])")
_TOTAL_BARE = re.compile(r"(?:^|[\s)\]])계\s*(?:\([^)]*\))?\s*$")
# 조직·구분 단위 소계. 태영건설은 개별 현장을 다 적고도 `토목본부-전체`·`토목본부-국내`·
# `건축본부-국내`를 같은 표에 넣는다 — 현장으로 세면 잔고가 2.5배가 된다.
# (개별 112행의 합이 `합계 - 전체`와 정확히 일치함을 확인했다.)
_TOTAL_UNIT = re.compile(r"(?:본부|사업부|부문|사업본부|BU|팀)\s*[-–—]\s*"
                         r"(?:전체|국내|해외|합계|계)$")

# 잔여 묶음 행. 소계와 달리 **중복이 아니라 나머지**다 — 빼면 총계가 안 맞는다.
# 집계에는 남기되 현장으로는 세지 않는다(`agg` 표시).
_AGG_ROW = re.compile(r"^(?:기타|그외|그밖)(?:현장|프로젝트|공사|사업|계약|등)?$")
# '계약잔액 50억 미만'처럼 금액 기준으로 묶은 나머지 행
_AGG_THRESHOLD = re.compile(r"(?:미만|이하|미달)")


def _forms(rec):
    nm = (rec.get("nm") or "")
    return re.sub(r"[\s　]+", "", nm), re.sub(r"[\s　]+", " ", nm).strip()


def is_total_row(rec):
    """합계·소계 행인가. 사업장으로 섞이면 잔고가 몇 배로 부푼다."""
    tight, spaced = _forms(rec)
    if not tight:
        return False
    return bool(_TOTAL_STRICT.search(tight) or _TOTAL_BARE.search(spaced)
                or _TOTAL_UNIT.search(tight))


def is_agg_row(rec):
    """'기타현장'·'계약잔액 50억 미만'처럼 개별 기재를 생략한 **나머지 묶음** 행인가."""
    tight, spaced = _forms(rec)
    if not tight:
        return False
    return bool(_AGG_ROW.match(tight)
                or (_AGG_THRESHOLD.search(tight) and len(spaced) <= 20))


# ── 표 한 장 가르기(총계 · 개별 · 잔여 묶음) ──────────────────

FIELDS = ("amt", "cmp", "bal")


def _eq(a, b):
    """금액 동일성. 천원 단위로 소수를 적는 회사가 있어 부동소수 오차만 눈감는다."""
    if a is None or b is None:
        return False
    return abs(a - b) <= 1e-6 * max(1.0, abs(b))


def is_subtotal_of(row, ind_sum, n_ind):
    """묶음처럼 이름 붙은 행이 실은 **개별 행들의 소계**인가.

    이름만 보면 가릴 수 없다. HS화성 2025Q3의 `계약잔액 50억 미만` 행은 도급액·
    완성공사액·계약잔액이 앞선 개별 41행의 합과 **정확히 같다** — 나머지가 아니라
    소계다. 묶음으로 보고 더하면 잔고가 정확히 2배가 된다(대조 197.2%).
    다른 7개 분기의 같은 이름 행은 200~380억짜리 진짜 나머지라, 이름이 아니라
    **값**으로 갈라야 한다.

    오탐을 좁히려고 조건을 빡빡하게 건다: 개별이 2행 이상이고 개별 잔고 합이
    양수이며, **도급액과 계약잔액이 둘 다** 개별 합과 일치할 때만 소계로 본다.
    진짜 나머지 묶음이 두 필드에서 동시에 개별 합과 겹칠 일은 사실상 없다.
    """
    if n_ind < 2 or not (ind_sum.get("bal") or 0) > 0:
        return False
    return _eq(row.get("amt"), ind_sum.get("amt")) and \
        _eq(row.get("bal"), ind_sum.get("bal"))


def fit_agg(aggs, ind_sum, tot):
    """잔여 묶음이 원문 총계를 넘칠 때 총계에 맞춰 줄인다. 줄였으면 True.

    한신공영 2025Q2 민간부문: 개별 10행 합 792,425 + `기 타` 3,051,455 =
    3,843,880인데 원문이 적은 `계`는 3,664,094다. 차이 179,786은 **그 분기에 새로
    실린 개별 행 하나(수원당수C3D3아파트)의 계약잔액과 정확히 같고**, 도급액·
    완성공사액도 같은 행만큼 어긋난다. 원문이 `기 타`를 '계 − 개별'로 계산하면서
    새로 올린 현장을 빼지 않은 것이다(나머지 7개 분기는 오차 0~2로 맞는다).
    잔여 묶음은 정의상 '총계 − 개별'이므로 원문 총계를 믿고 묶음만 줄인다.

    **개별 합만으로 이미 총계를 넘으면 손대지 않는다** — 그건 소계가 개별로 섞여
    든 것이고, 묶음을 줄여 덮으면 대조율 경보(reconOver)가 죽어 버린다.
    """
    fixed = False
    for f in FIELDS:
        top = tot.get(f)
        if top is None:
            continue
        ind = ind_sum.get(f) or 0
        agg = sum(r.get(f) or 0 for r in aggs)
        if agg <= 0 or ind > top:
            continue
        # 원문 반올림 오차(±1~2)까지 손대면 멀쩡한 표를 매 분기 건드리게 된다
        if ind + agg <= top + max(2.0, abs(top) * 0.001):
            continue
        room, acc, last = top - ind, 0.0, None
        for r in aggs:
            v = r.get(f)
            if v is None:
                continue
            r[f] = v * room / agg
            acc += r[f]
            last = r
        if last is not None:                     # 부동소수 잔차는 마지막 행이 흡수
            last[f] = _tidy(last[f] + (room - acc))
        for r in aggs:
            if r.get(f) is not None:
                r[f] = _tidy(r[f])
        fixed = True
    return fixed


def _tidy(v):
    """원문이 정수로 적은 칸을 보정 뒤에도 정수로 되돌린다(JSON 노이즈 방지)."""
    r = round(v, 6)
    return int(r) if r == int(r) else r


def split_table(rows, ti):
    """한 표를 총계·개별·잔여 묶음으로 가른다.

    반환 (ind, aggs, tot, fixed)
      ind   {식별키: 행}  개별 계약. 표 안 중복 게재(연결/별도)는 도급액 큰 쪽만.
      aggs  [(스코프키, 행)]  잔여 묶음. **표 안 등장 순번으로 자리를 잡아 준다** —
            일성건설은 건축공공·건축민간·토목공공·토목민간·해외로 `기타`를 5줄
            적는데 이름·발주처·착공일이 전부 같아 복합키로도 갈리지 않는다
            (하나만 남기면 6,736억이 사라진다).
      tot   {"amt":…,"cmp":…,"bal":…} 또는 None — 원문이 그 표에 적은 총계 행
      fixed 잔여 묶음을 총계에 맞춰 줄였는가
    """
    tot_rows = [r for r in rows if is_total_row(r)]
    rest = [r for r in rows if not is_total_row(r)]
    raw_agg = [dict(r) for r in rest if is_agg_row(r)]

    ind = {}
    for r in rest:
        if is_agg_row(r):
            continue
        key = site_key(r)
        if not key.strip("|"):
            continue
        cur = ind.get(key)
        if cur is None or (r.get("amt") or 0) > (cur.get("amt") or 0):
            ind[key] = r
    ind_sum = {f: sum(r.get(f) or 0 for r in ind.values()) for f in FIELDS}

    # 소계로 위장한 묶음 행을 총계 쪽으로 되돌린다(HS화성 197.2%)
    aggs = []
    for r in raw_agg:
        if is_subtotal_of(r, ind_sum, len(ind)):
            tot_rows.append(r)
        else:
            aggs.append(r)

    # 총계는 **계약잔액이 가장 큰 한 행**을 고른다. 필드별로 따로 최댓값을 뽑으면
    # 서로 다른 소계 행의 칸을 섞어 존재하지 않는 총계를 만들게 된다.
    tot = None
    for r in tot_rows:
        b = r.get("bal")
        if b is not None and (tot is None or b > tot["bal"]):
            tot = {f: r.get(f) for f in FIELDS}
    fixed = bool(tot and aggs) and fit_agg(aggs, ind_sum, tot)
    return ind, [("%s#%d.%d" % (site_key(r), ti, j), r)
                 for j, r in enumerate(aggs)], tot, fixed


# ── 수집 ─────────────────────────────────────────────────────

def cache_path(stock, quarter):
    return os.path.join(CACHE, stock, "%s.json" % quarter)


def collect_one(stock, quarter, force=False):
    """한 종목·한 분기의 II-4 사업장 행을 캐시에 담는다. 이미 있으면 건너뛴다."""
    path = cache_path(stock, quarter)
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    out = {"stock": stock, "quarter": quarter, "ok": False, "note": "",
           "rcpNo": None, "rows": [], "grain": None}
    try:
        start, end = report_window(quarter)
        reports = search_reports(stock, start, end, report_kind(quarter))
        if not reports:
            out["note"] = "정기보고서 없음"
        else:
            for rcp, _title in pick_report(reports, quarter)[:3]:
                nodes = toc(rcp)
                if not nodes:
                    continue
                found = find_sections(nodes)
                if not ("ii4" in found or "ii4x" in found):
                    continue
                best = None
                for key in ("ii4", "ii4x"):
                    if key not in found:
                        continue
                    r = parse_ii4(fetch_section(found[key]))
                    n = sum(t["n"] for t in r["tables"])
                    if best is None or n > best[0]:
                        best = (n, r)
                n, r = best
                if n == 0:
                    out["note"] = "수주 표 인식 0"
                    continue
                out["rcpNo"] = rcp
                out["grain"] = grain_of(r["tables"])
                # **거르지 않고 원행 그대로** 담는다. 소계 판별 규칙은 회사가 늘수록
                # 계속 손보게 되는데, 수집 단계에서 걸러 버리면 규칙을 고칠 때마다
                # 전 종목을 다시 받아야 한다. 분류는 build()가 한다.
                # **표 경계를 보존한다.** 한 절에 `1) 공공부문`·`2) 민간부문`처럼 서로
                # 겹치지 않는 표가 여러 개 오는데(HJ중공업 조선/건설, 계룡 지배/종속),
                # 한 덩어리로 합치면 표마다 있는 `기타`·`합계` 행이 이름으로 병합돼
                # 잔고가 어긋난다(한신공영 123%).
                out["tables"] = [{"lead": (t.get("lead") or "")[-120:],
                                  "rows": t["rows"]} for t in r["tables"]]
                out["rows"] = [x for t in r["tables"] for x in t["rows"]]
                out["ok"] = True
                break
            if not out["ok"] and not out["note"]:
                out["note"] = "수주 절 있는 보고서 없음"
    except Exception as e:
        out["note"] = "%s: %s" % (type(e).__name__, e)
        out["transient"] = True
    # **일시적 실패는 캐시하지 않는다.** DART는 연속 요청에 URLError를 던지는데,
    # 그걸 캐시하면 재실행해도 영영 재시도되지 않아 회사가 2/8분기로 굳는다.
    if not out.get("transient"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        atomic_write(path, json.dumps(out, ensure_ascii=False) + "\n")
    return out


def _missing(recs, quarters):
    """아직 캐시에 성공 기록이 없는 (종목, 분기) 목록."""
    todo = []
    for rec in recs:
        for q in quarters:
            p = cache_path(rec["stock"], q)
            if not os.path.exists(p):
                todo.append((rec, q))
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
            except Exception:
                todo.append((rec, q))
                continue
            if not d.get("ok") and not d.get("note"):
                todo.append((rec, q))
    return todo


def collect(recs, quarters, force=False, log=sys.stderr, sweeps=2):
    """(종목 × 분기)를 레인 나눠 수집한다.

    작업 단위를 **회사가 아니라 분기까지 쪼개** 레인에 넣는다 — 회사 단위로 나누면
    현장 수가 제각각이라 레인이 놀고, 늦게 끝나는 한 회사가 전체를 붙잡는다.

    수집이 끝나면 아직 비어 있는 칸만 다시 훑는다(sweep). DART는 부하가 몰리면
    일시적으로 연결을 끊는데, 그 칸을 그냥 두면 회사가 영구히 2/8분기로 남는다.
    """
    if force:
        todo = [(rec, q) for rec in recs for q in quarters]
    else:
        todo = _missing(recs, quarters)
    done = [0]
    total = len(todo)

    def one(item):
        rec, q = item
        return collect_one(rec["stock"], q, force)

    def report(i, item, res):
        done[0] += 1
        rec, q = item
        bad = isinstance(res, Exception) or not (res or {}).get("ok")
        if bad or done[0] % 20 == 0:
            log.write("  [%3d/%d] %-6s %-8s %s\n"
                      % (done[0], total, rec["stock"], q,
                         "OK" if not bad else ("실패: %s" % (
                             res if isinstance(res, Exception)
                             else (res.get("note") or "?"))[:52]))) 
            log.flush()

    for sweep in range(max(1, sweeps)):
        if not todo:
            break
        log.write("[수집] %d칸 · 레인 %d · %d회차\n"
                  % (len(todo), __import__("kce_fetch").LANES, sweep + 1))
        log.flush()
        done[0], total = 0, len(todo)
        parallel(todo, one, on_done=report)
        todo = _missing(recs, quarters)      # 남은 칸만 다시
        force = False                        # 스윕은 캐시된 성공을 다시 받지 않는다

    for rec in recs:
        got = sum(1 for q in quarters
                  if os.path.exists(cache_path(rec["stock"], q))
                  and json.load(open(cache_path(rec["stock"], q),
                                     encoding="utf-8")).get("ok"))
        log.write("%-6s %-16s %d/%d분기%s\n"
                  % (rec["stock"], rec["name"][:16], got, len(quarters),
                     "" if got == len(quarters) else "  ← 미완"))
    log.flush()


# ── 빌드 ─────────────────────────────────────────────────────

_OVS = re.compile(r"해외|overseas|국외")
_DOM = re.compile(r"국내|관급|민간|내수")
_SEG = [("건축", re.compile(r"건축|주택|아파트|APT|오피스텔|빌딩")),
        ("토목", re.compile(r"토목|도로|철도|교량|터널|항만|지하|상하수|댐")),
        ("플랜트", re.compile(r"플랜트|발전|EPC|정유|석유|화공|풍력|태양광")),
        ("환경", re.compile(r"환경|소각|폐기|수처리")),
        ("기타", re.compile(r"."))]


def classify(rec, lead=""):
    """지역(국내/해외)·공종. 원문에 신호가 없으면 국내·기타로 둔다."""
    blob = " ".join(str(rec.get(k) or "") for k in ("nm", "cl", "seg")) + " " + lead
    reg = "해외" if _OVS.search(blob) else "국내"
    for name, pat in _SEG:
        if pat.search(blob):
            return reg, name
    return reg, "기타"


def link(entries, sites, order, agg_index, generic, k):
    """이번 분기 행들을 기존 사이트에 **1:1로** 맺는다. {행 키: 사이트 id}.

    한 사이트는 한 분기에 한 행만 받는다 — 그래야 남화토건처럼 같은 달·같은
    발주처로 들어온 두 계약이 약한 수준에서 한 칸으로 도로 뭉치지 않는다.
    후보가 여럿이면 **도급액이 가까운 짝부터** 맺고(계약금액은 계약 내내 거의
    그대로다), 그다음 최근에 관측된 사이트를 먼저 준다(오래 전에 끝난 현장에
    새 계약이 붙는 것을 막는다).
    """
    pair, taken = {}, set()
    # 잔여 묶음은 스코프 키(표·순번) 정확 일치로만 잇는다. 이름·발주처·착공일이
    # 전부 '기타'라 다른 수준을 열어 주면 서로 다른 묶음끼리 붙어 버린다.
    for ekey, e in entries.items():
        if not e["agg"]:
            continue
        sid = agg_index.get(ekey)
        if sid is not None and sid not in taken:
            pair[ekey] = sid
            taken.add(sid)
    for _name, keyof in _LINK:
        rest = [ek for ek, e in entries.items()
                if not e["agg"] and ek not in pair]
        if not rest:
            break
        grp = {}
        for ek in rest:
            kk = keyof(entries[ek]["f"], generic)
            if kk is not None:
                grp.setdefault(kk, ([], []))[0].append(ek)
        if not grp:
            continue
        for sid in order:
            s = sites[sid]
            if s["agg"] or sid in taken:
                continue
            kk = keyof(s["_f"], generic)
            if kk is not None and kk in grp:
                grp[kk][1].append(sid)
        for _kk, (eks, sids) in grp.items():
            if not sids:
                continue
            cand = sorted((_amt_dist(entries[ek]["f"]["amt"], sites[sid]["_f"]["amt"]),
                           k - sites[sid]["_k"], sid, ek)
                          for ek in eks for sid in sids)
            for _d, _gap, sid, ek in cand:
                if sid in taken or ek in pair:
                    continue
                pair[ek] = sid
                taken.add(sid)
    return pair


def build(rec, quarters):
    """캐시된 분기들 → DATA-lite. 관측된 분기만 축에 넣는다."""
    got = []
    for q in quarters:
        p = cache_path(rec["stock"], q)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        if d["ok"]:
            got.append(d)
    if not got:
        raise RuntimeError("%s: 수집된 분기가 없다" % rec["stock"])
    fq = [d["quarter"] for d in got]
    n = len(fq)

    generic = _generic_names(got)    # 계약을 식별하지 못하는 이름(공종·품목 라벨)
    sites, order, agg_index = {}, [], {}
    declared = [None] * n            # 원문이 명시한 수주잔고 총계(있으면)
    covered = [None] * n             # 그 총계가 덮는 표에서 우리가 센 몫
    aggfix = []                      # 잔여 묶음을 공시 총계에 맞춰 줄인 분기
    for k, d in enumerate(got):
        tables = d.get("tables") or [{"lead": "", "rows": d.get("rows") or []}]
        entries, fixed_q = {}, False
        for ti, tab in enumerate(tables):
            # 총계는 **표마다** 따로 잡아 더한다. 표들은 서로 겹치지 않는 구획이므로
            # (공공/민간 · 조선/건설 · 지배/종속) 최댓값 하나만 쓰면 총계가 모자란다.
            ind, aggs, tot, fixed = split_table(tab["rows"], ti)
            fixed_q = fixed_q or fixed
            mine = 0.0
            for is_agg, pairs in ((False, ind.items()), (True, aggs)):
                for key, row in pairs:
                    # 같은 분기의 다른 표에 같은 계약이 또 실리면 마지막 것만 남긴다
                    # (연결/별도 중복 게재). 자리는 처음 등장한 순서를 지킨다.
                    entries[key] = {"row": row, "agg": is_agg, "f": _ident(row)}
                    mine += row.get("bal") or 0
            if tot is not None and tot.get("bal") is not None:
                # 대조는 **그 총계가 덮는 표 안에서만** 성립한다. 합계행이 있는 표의
                # 총계에 우리 전체 합을 견주면 합계행이 없는 표(HJ중공업 조선부문,
                # 억원 단위 별도 표)의 몫이 통째로 초과분으로 잡혀 123%가 된다 —
                # 데이터는 맞는데 지표만 거짓 경보를 울린다.
                declared[k] = (declared[k] or 0) + tot["bal"]
                covered[k] = (covered[k] or 0) + mine
        if fixed_q:
            aggfix.append(fq[k])

        pair = link(entries, sites, order, agg_index, generic, k)
        for key, e in entries.items():
            row, sid = e["row"], pair.get(key)
            if sid is None:
                sid = "%s-%04d" % (rec["stock"], len(order) + 1)
                reg, seg = classify(row)
                sites[sid] = {
                    "id": sid,
                    "nm": (row.get("nm") or "").strip(), "cl": (row.get("cl") or "").strip(),
                    "reg": reg, "seg": seg, "agg": e["agg"],
                    "sd": _norm_date(row.get("sd")), "ed": _norm_date(row.get("ed")),
                    "s": {f: [None] * n for f in ("amt", "cmp", "bal", "pr")},
                }
                order.append(sid)
                if e["agg"]:
                    agg_index[key] = sid
            s = sites[sid]
            for f in ("amt", "cmp", "bal"):
                v = row.get(f)
                if v is not None:
                    s["s"][f][k] = v
            pr = row.get("pr")
            if pr is None:
                a, c = s["s"]["amt"][k], s["s"]["cmp"][k]
                pr = round(100.0 * c / a, 1) if (a and c is not None and a > 0) else None
            s["s"]["pr"][k] = pr
            # 이름·날짜는 최신 관측으로 갱신(원문이 표기를 다듬는 경우가 있다).
            # 식별 필드도 함께 갱신해야 표기가 조금씩 흘러가도(A → A' → A'')
            # 직전 관측과 이어져 사슬이 끊기지 않는다.
            s["nm"] = (row.get("nm") or s["nm"]).strip()
            s["cl"] = (row.get("cl") or s["cl"]).strip()
            s["sd"] = _norm_date(row.get("sd")) or s["sd"]
            s["ed"] = _norm_date(row.get("ed")) or s["ed"]
            s["_f"], s["_k"] = e["f"], k

    site_list = [sites[sid] for sid in order]
    for s in site_list:              # 연결용 내부 필드는 페이지로 내보내지 않는다
        s.pop("_f", None)
        s.pop("_k", None)
    summary = {f: [None] * n for f in ("amt", "cmp", "bal")}
    dom = [None] * n
    ovs = [None] * n
    for k in range(n):
        for f in ("amt", "cmp", "bal"):
            vals = [s["s"][f][k] for s in site_list if s["s"][f][k] is not None]
            summary[f][k] = round(sum(vals)) if vals else None
        for tgt, reg in ((dom, "국내"), (ovs, "해외")):
            vals = [s["s"]["bal"][k] for s in site_list
                    if s["reg"] == reg and s["s"]["bal"][k] is not None]
            tgt[k] = round(sum(vals)) if vals else None

    segs = sorted({s["seg"] for s in site_list})
    seg_rows = {}
    for g in segs:
        seg_rows[g] = [None] * n
        for k in range(n):
            vals = [s["s"]["bal"][k] for s in site_list
                    if s["seg"] == g and s["s"]["bal"][k] is not None]
            seg_rows[g][k] = round(sum(vals)) if vals else None

    # 총계 대조 — 수록 합이 원문 총계를 **넘으면** 중복 계상이다(금호건설 42.8조 사례).
    # 모자란 건 정상이다(상세표에 개별 기재되지 않은 소규모 현장 몫).
    recon = []
    for k in range(n):
        d, t = declared[k], covered[k]
        if d and t is not None:
            recon.append(round(100.0 * t / d, 1))
        else:
            recon.append(None)
    over = [fq[k] for k, r in enumerate(recon) if r is not None and r > 102.0]

    return {
        # aggFix는 **원문 값을 우리가 고친 분기**다. 잔여 묶음이 공시 총계를 넘겨
        # 총계에 맞춰 줄인 경우로, 숨기면 화면의 숫자가 원문과 다른 이유를 알 수 없다.
        "recon": recon, "reconOver": over, "aggFix": aggfix,
        "co": rec["name"], "stock": rec["stock"], "slug": rec["slug"],
        "market": rec["market"], "industry": rec["industry"],
        # codeGen은 **데이터에서 유도**한다. 오늘 날짜를 쓰면 내용이 같아도 매일
        # 페이지가 바뀌어 자동 갱신이 빈 커밋을 만든다.
        "fq": fq, "codeGen": fq[-1],
        "grain": got[-1]["grain"],
        "src": {d["quarter"]: d["rcpNo"] for d in got},
        "sites": site_list,
        "summary": summary, "declared": declared, "dom": dom, "ovs": ovs,
        "segList": segs, "seg": seg_rows,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--from", dest="q0", default="2024Q3")
    ap.add_argument("--to", dest="q1", default=None,
                    help="기본: 오늘 기준 접수 완료된 최신 분기")
    ap.add_argument("--only", help="종목코드 쉼표 구분")
    ap.add_argument("--force", action="store_true", help="캐시 무시하고 다시 받기")
    ap.add_argument("--lanes", type=int, help="병렬 레인 수(기본 KCE_LANES 또는 6)")
    ap.add_argument("--sweeps", type=int, default=3,
                    help="빈 칸 재훑기 횟수 — 일시적 실패를 메운다")
    ap.add_argument("--tier", default="site", help="이 등급만 (기본 site)")
    ap.add_argument("--new-only", action="store_true",
                    help="원본 7사 제외 — 그쪽은 encprojects 시드가 이미 있다")
    a = ap.parse_args()

    recs = load_universe()
    probe = {}
    ppath = os.path.join(HERE, "assets", "probe_2026Q2.json")
    if os.path.exists(ppath):
        with open(ppath, encoding="utf-8") as f:
            probe = {r["stock"]: r for r in json.load(f)["rows"]}
    if a.tier:
        want = set(a.tier.split(","))
        recs = [r for r in recs if probe.get(r["stock"], {}).get("tier") in want]
    if a.new_only:
        recs = [r for r in recs if r["stock"] not in
                {v["stock"] for v in CORP.values()}]
    if a.only:
        sel = {s.strip() for s in a.only.split(",")}
        recs = [r for r in recs if r["stock"] in sel]
    quarters = q_range(a.q0, a.q1 or latest_quarter())

    if a.collect:
        if a.lanes:
            import kce_fetch
            kce_fetch.LANES = max(1, a.lanes)
        collect(recs, quarters, a.force, sweeps=a.sweeps)
    if a.build:
        for r in recs:
            try:
                d = build(r, quarters)
                print("%-6s %-16s 분기%2d 현장%4d 잔고 %s억"
                      % (r["stock"], r["name"][:16], len(d["fq"]), len(d["sites"]),
                         format(round((d["summary"]["bal"][-1] or 0) / 100), ",d")))
            except Exception as e:
                print("%-6s %-16s 실패: %s" % (r["stock"], r["name"][:16], e))


if __name__ == "__main__":
    sys.exit(main())
