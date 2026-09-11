#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scout_probe — 표본 각 사의 정기보고서 II-4 「매출 및 수주상황」을 **실제로 열어** 잰다.

추측하지 않는다. 재는 것은 다섯 가지뿐이다(scout.md §2):
  ① 수주상황 표가 있는가 — 있으면 어떤 모양인가
  ② 수주잔고 금액 / 연매출 = 몇 년치 일감인가
  ③ 행 입도(프로젝트 단위인가 부문 단위인가) · 발주처 열 · 수주일자·납기 열이 있는가
  ④ 단일 계약이 잔고의 몇 %인가
  ⑤ 본문 낱말 신호(진행기준·환위험·관급·지체상금…) — 그 산업의 축 후보

원문 3건(두산에너빌리티·현대로템·HD현대일렉트릭)에서 확인한 두 모양을 다 받는다:
  · 표준형   `품목|수주일자|납기|수주총액|기납품액|수주잔고`  (kce COL_ALIAS가 이미 안다)
  · 롤포워드 `구분|주요계약명|기초|증감|매출계상액|기말`
단위는 **표마다** 읽는다(두산은 매출 백만원·수주 억원). 못 읽으면 unit_seen=false로 남긴다.

    python3 scout_probe.py --quarter 2025Q4                 # assets/sample.json 전수
    python3 scout_probe.py --only 034020,064350 --dump      # 일부만, 근거 출력
"""
import argparse
import json
import os
import re
import sys
import time

from scout_lib import (ASSETS, atomic_write, fetch_section, load_asset, num_of,
                       parse_tables, pick_report, report_kind, report_window,
                       search_reports, text_of, toc, unit_scale, write_asset)
from kce_lib import COL_ALIAS, norm_col

CACHE = os.path.join(ASSETS, "probe_cache")
# 절 원문은 따로 보관한다 — 파서를 고쳤을 때 원문을 다시 받지 않기 위해.
# `assets/_raw/` 는 .gitignore 대상이다(원문 HTML을 저장소에 넣지 않는다 — 감독 메모 2026-09-11).
HTML_CACHE = os.path.join(ASSETS, "_raw", "probe_html")

# 목차에서 찾을 절. 기업공시서식 표준은 「4. 매출 및 수주상황」이지만 회사마다 제목이 흔들린다.
SECTION_PATTERNS = [
    ("ii4", ["매출 및 수주상황", "수주상황", "수주 상황", "수주현황", "매출실적"]),
]

_SUM = re.compile(r"^(합\s*계|총\s*계|계|소\s*계|연결기준합계|합계\(.*\)|총합계)$")
_SUM_LOOSE = re.compile(r"합\s*계|총\s*계|^계$")
# 롤포워드형 머리행
_ROLL_BEGIN = re.compile(r"^(기초|전기이월|기초잔액|기초수주잔고)")
_ROLL_END = re.compile(r"^(기말|기말잔액|기말수주잔고|차기이월|당기말)")
# 날짜 방언(kce_probe와 같은 규칙 — 부문 합계 행에는 날짜가 없다)
_DATE = re.compile(r"(?:(?:19|20)\d{2}\s*[-./년]|(?:19|20)\d{4}|\b\d{2}\s*[.\-년]\s*\d{1,2})")
# 익명화된 계약명('철도A'·'선박 A'·'Project B'·'A사') — 조선의 익명 선주와 같은 문제
_ANON = re.compile(r"^[\w가-힣]{0,6}\s*[A-Z]{1,3}\d*$")

# 본문 낱말 신호 → 그 산업의 축 후보. 값은 (정규식, 설명).
TEXT_FLAGS = [
    ("progress", r"진행기준|진행률|투입원가|총계약원가", "매출인식이 진행기준(인도와 매출 시점이 다름)"),
    ("fx", r"통화선도|환위험|환헤지|환율변동위험|파생상품계약", "환노출·환헤지 축"),
    ("gov", r"조달청|관급|정부기관|공공기관|국가기관|방위사업청|한국수력원자력|한국전력", "공공 발주 축"),
    ("ld", r"지체상금|지연배상금|납기지연|Liquidated", "납기·지체상금(실행 리스크) 축"),
    ("export", r"수\s*출", "내수/수출 구분"),
    ("turnkey", r"턴키|EPC|일괄도급|설계.{0,4}구매.{0,4}시공", "EPC/턴키 축"),
    ("option", r"옵션\s*계약|옵션분|추가\s*발주", "옵션 계약 축"),
    ("longterm", r"장기공급계약|장기계약|다년|LTSA|MRO|유지보수계약", "다년 계약 축"),
]


# ── 표 정규화 ───────────────────────────────────────────────

_UNIT_ONLY = re.compile(r"^[(（\[]?\s*단위")


def norm_tables(html):
    """parse_tables 위에 **첫 행 머리행 폴백**과 **껍데기 표의 lead 이어붙임**을 얹는다.

    원문 확인에서 본 사고 둘:
    ① 두산에너빌리티·HD현대일렉트릭의 수주표는 머리행 셀이 `<th>`가 아니라 `<td>`여서
       `parse_tables`의 `cols`가 비고 머리행이 rows[0]으로 들어온다. 그대로 쓰면
       '수주잔고' 열을 영원히 못 찾는다.
    ② 단위 캡션만 담은 **1×n 껍데기 표**를 앞에 두고 실제 표를 그 뒤에 놓는 회사가 있다
       (SFA 056190: `(단위 : 백만원)` 표 → 매출실적 표). 껍데기를 그냥 버리면 소절 제목
       ('(1) 매출실적')과 단위가 같이 사라져 뒤 표가 **분류도 단위 확인도 안 된다**.
       → 껍데기는 표로 내보내지 않고 lead·캡션을 다음 표에 넘긴다.
    """
    out = []
    pending = ""
    for t in parse_tables(html):
        lead = (pending + "\n" + (t.get("lead") or "")) if pending else (t.get("lead") or "")
        cols, rows = list(t["cols"]), [list(r) for r in t["rows"]]
        cells = [c.strip() for r in rows for c in r if c and c.strip()]
        if not cols and cells and all(_UNIT_ONLY.match(c) for c in cells):
            pending = lead + " " + " ".join(cells)        # 껍데기 — 다음 표로 넘긴다
            continue
        pending = ""
        if cols and all(_UNIT_ONLY.match(c or "") for c in cols if (c or "").strip()):
            # 머리행 자리에 단위 캡션만 들어간 표(금호건설 002990) — 단위는 lead로 넘기고
            # 진짜 머리행은 아래 첫 행 폴백에 맡긴다.
            lead = lead + " " + cols[0]
            cols = []
        if not cols and rows:
            head = rows[0]
            # 숫자가 하나도 없고 셀이 2개 이상이면 머리행으로 본다
            if len(head) >= 2 and not any(num_of(c) is not None for c in head):
                cols, rows = head, rows[1:]
        if not rows:
            continue
        # 2단 머리행: 첫 데이터 행이 숫자 없이 '수량/금액/수출/내수/비중'뿐이면 머리행의 아랫단이다.
        # 병합하지 않으면 '기 말'이 두 개가 되어 **수량 열**을 금액으로 읽는다(한국항공우주 실사례).
        if cols and rows and len(rows[0]) == len(cols) \
                and not any(num_of(c) is not None for c in rows[0]) \
                and sum(1 for c in rows[0]
                        if re.search(r"수량|금액|비중|수출|내수|국내|합\s*계|당기|전기|20\d{2}", c or "")) >= 2:
            cols = [("%s %s" % (a, b)).strip() for a, b in zip(cols, rows[0])]
            rows = rows[1:]
            if not rows:
                continue
        ncols = [norm_col(c) for c in cols]
        # 통화는 unit_scale 과 **같은 캡션**에서 읽는다(lead 우선, 없으면 머리행).
        cap = lead if re.search(r"단위", lead) else " ".join(cols)
        cur = _currency_of(cap) or ("MIX" if _MIXED_CUR.search(lead) else None)
        out.append({"lead": lead, "cols": cols, "ncols": ncols,
                    "fields": [COL_ALIAS.get(c) for c in ncols], "rows": rows,
                    "unit": unit_scale(lead, cols), "cur": cur,
                    "unit_seen": bool(re.search(r"단위", lead + " ".join(cols)))})
    return out


_FX = re.compile(r"(USD|US\s*\$|\$|달러|EUR|유로|JPY|엔화|CNY|위안)", re.I)
_FX_NORM = {"USD": "USD", "US$": "USD", "$": "USD", "달러": "USD",
            "EUR": "EUR", "유로": "EUR", "JPY": "JPY", "엔화": "JPY",
            "CNY": "CNY", "위안": "CNY"}
_KRW_UNIT = re.compile(r"십억원|백만원|천원|만원|억원|원")
# 행 자체가 통화인 표(KC코트렐 119650 「주요 환종별 수주상황」: KRW/USD/EUR/INR/TWD 5행).
# 열을 세로로 더하면 원·달러·루피가 섞인 숫자가 나온다 — 환율 없이 합계를 만들 수 없다.
_MIXED_CUR = re.compile(r"환종|통화별|외화별|화폐별")


def _currency_of(blob):
    """표의 단위 캡션이 **외화**면 통화 코드를 돌려준다(원화면 None).

    아스트 067390의 국외수주 표는 `(단위 : USD )`, 씨에스윈드 112610은 `(단위 : 백만USD)`,
    일진전기 103590은 `(단위 : 천USD )`다. 이걸 백만원으로 읽으면 아스트 잔고가 2,688조원이
    된다(실제 26.9억달러). 환율은 무키 경로로 못 얻으므로 **환산하지 않고 배수 계산에서
    뺀다**(COMMON.md §0: 모르면 빈칸).

    단 원화 단위가 **같이 적힌** 캡션은 원화 표다 — 외화는 괄호 병기일 뿐이고 표의 숫자는
    원화다(포메탈 119500 `[단위 : 백만원 (천USD)]`, 로체시스템즈 071280 `(단위 :천원, 천USD )`).
    여기서 배수를 버리면 멀쩡한 관측을 잃는다.

    lead 에 단위 캡션이 여러 개 붙을 수 있으므로(껍데기 표 이어붙임) `unit_scale` 과 같이
    **마지막 캡션**만 본다. 앞 절에 남은 '(단위 : USD)'가 뒤 원화 표를 오염시키지 않게.
    """
    blob = blob or ""
    i = blob.rfind("단위")
    if i < 0:
        return None
    cap = blob[i:i + 20]
    m = _FX.search(cap)
    if not m or _KRW_UNIT.search(cap):
        return None
    return _FX_NORM.get(m.group(1).upper().replace(" ", ""))


def _idx(t, field):
    try:
        return t["fields"].index(field)
    except ValueError:
        return None


def _find_col(t, pat):
    for i, c in enumerate(t["ncols"]):
        if pat.search(c or ""):
            return i
    return None


def _amount_col(t, pat):
    """pat에 걸리는 열 중 **금액 열**을 고른다.

    표준 양식은 `기초수주잔액(수량, 금액)`처럼 (수량, 금액) 쌍으로 온다. 첫 매칭을 그냥 쓰면
    값이 전부 '-'인 **수량** 열을 잡아 잔고가 통째로 사라진다(HD현대중공업 56조가 0이 됐다).
    kce의 COL_ALIAS가 '수주잔고금액'만 매핑하는 것과 같은 이유다.
    """
    hit = [i for i, c in enumerate(t["ncols"]) if pat.search(c or "")]
    if not hit:
        return None
    amt = [i for i in hit if "금액" in (t["ncols"][i] or "")]
    if amt:
        return amt[0]
    qty = [i for i in hit if "수량" in (t["ncols"][i] or "")]
    rest = [i for i in hit if i not in qty]
    if rest:
        return rest[0]
    return None


def _cell(row, i):
    return row[i] if i is not None and i < len(row) else ""


def _is_sum(row, n_label):
    for c in row[:max(1, n_label)]:
        if _SUM.match(norm_col(c) or ""):
            return True
    return False


def _n_label(t):
    """머리행에서 숫자가 아닌 라벨 열의 개수(대부분 행에서 비숫자인 선두 열)."""
    n = 0
    for i in range(len(t["cols"])):
        vals = [num_of(_cell(r, i)) for r in t["rows"][:12]]
        if any(v is not None for v in vals):
            break
        n += 1
    return n


def sum_column(t, i):
    """열 i의 금액 합계. 합계 행은 버리지 않고 따로 돌려준다(COMMON.md §2).

    반환 {'sum': 비합계행 합, 'total': 합계행 값, 'n': 비합계 행수, 'max': 최대값}.
    """
    n_label = max(1, _n_label(t))
    vals, total = [], None
    for r in t["rows"]:
        v = num_of(_cell(r, i))
        if v is None:
            continue
        if _is_sum(r, n_label):
            total = v if total is None else max(total, v)   # 부문합계가 여럿이면 총계가 최대
            continue
        vals.append(v)
    return {"sum": round(sum(vals), 3) if vals else None, "total": total,
            "n": len(vals), "max": max(vals) if vals else None}


# ── 수주 표 ─────────────────────────────────────────────────

# 매출실적 표의 소절 제목 방언(공백 제거 후). '매출및수주상황'(절 제목 자체)은 넣지 않는다 —
# 절의 첫 표 아무것이나 매출표로 만들어 버린다.
_SALES_CUE = r"매출실적|매출액현황|매출현황|매출에관한사항|매출및매출원가|매출유형|판매실적|매출개요"


def _period_cols(t):
    """머리행에서 '기수/연도/당기' 열 인덱스 — 매출실적 표의 표지. (비중·증감 열은 뺀다)"""
    out = []
    for i, c in enumerate(t["ncols"]):
        if re.search(r"비중|비율|증감|구성비|^%", c or ""):
            continue
        if re.search(r"수\s*량", c or ""):      # '제40기 수량'은 매출액이 아니다
            continue
        if re.search(r"제\d+기|20\d{2}|^당기|^당분기|^당반기|^금기", c or ""):
            out.append(i)
    return out


def classify(t):
    """표 한 개 → 'std'(수주총액·기납품액·수주잔고) / 'roll'(기초·증감·기말) / 'sales' / None."""
    f = set(x for x in t["fields"] if x)
    lead = t["lead"]
    if "bal" in f and ("amt" in f or "cmp" in f):
        return "std"
    if _find_col(t, _ROLL_BEGIN) is not None and _find_col(t, _ROLL_END) is not None:
        return "roll"
    # 잔고 열만 있는 변형(계약잔액·수주잔액)
    if _amount_col(t, re.compile(r"수주잔고|수주잔액|계약잔액|잔여수주")) is not None:
        return "std"
    # 계약 목록형 — 잔고 열은 없지만 **발주처가 실명으로 적힌** 그 해 수주 목록
    # (두산에너빌리티 '당해년도 체결된 주요 수주 상황' 20행: 프로젝트·계약시기·발주처·계약금액).
    # 잔고를 못 주므로 점수의 잔고 축에는 안 쓰지만 '계약상대 공개' 축의 증거다.
    if (_idx(t, "cl") is not None or _find_col(t, re.compile(r"발주처|계약상대|고객|수요처")) is not None) \
            and _find_col(t, re.compile(r"계약금액|수주금액|금액|계약규모")) is not None:
        return "clist"
    # '매출 실적'처럼 낱말 사이에 공백이 들어가는 회사가 있다(현대로템) — 공백을 지우고 본다
    # 소절 제목 방언 + 표 모양(기수/연도 열 또는 '매출액' 열 또는 부문·품목 라벨)
    # (세명전기 017510: 소절 제목이 '가. 매출에 관한 사항'이고 열은 `사업부문|품 목|제42기…`)
    lab = re.search(r"사업부문|품\s*목|구\s*분|제품|유형|부문", "".join(t["cols"]))
    if re.search(_SALES_CUE, re.sub(r"\s", "", lead)) and (
            _period_cols(t) or "매출액" in "".join(t["ncols"]) or lab):
        return "sales"
    if "매출액" in "".join(t["ncols"]) and re.search(r"사업부문|품목|사업구분|구분", "".join(t["ncols"])):
        return "sales"
    return None


def backlog_of(t, kind):
    """수주 표 → 잔고(백만원)와 근거. 단위 배수를 곱해 정규화한다."""
    if kind == "roll":
        i = _amount_col(t, _ROLL_END)
        label = t["cols"][i] if i is not None and i < len(t["cols"]) else "기말"
    else:
        i = _idx(t, "bal")
        if i is None:
            i = _amount_col(t, re.compile(r"수주잔고|수주잔액|계약잔액|잔여수주"))
        label = t["cols"][i] if i is not None and i < len(t["cols"]) else "수주잔고"
    if i is None:
        return None
    s = sum_column(t, i)
    raw = s["total"] if s["total"] is not None else s["sum"]
    if raw is None:
        return None
    mul = t["unit"]
    return {"col": label, "raw": raw, "unit_mul": mul, "unit_seen": t["unit_seen"], "cur": t.get("cur"),
            "bal": round(raw * mul, 3), "rows": s["n"],
            "row_sum": round(s["sum"] * mul, 3) if s["sum"] is not None else None,
            "max_row": round(s["max"] * mul, 3) if s["max"] is not None else None,
            "total_row": s["total"] is not None}


def grain_of(t):
    """행이 개별 계약(프로젝트)인가 부문 묶음인가 — 판별은 **날짜 유무**(kce_probe와 같은 규칙)."""
    i_sd, i_ed = _idx(t, "sd"), _idx(t, "ed")
    rows = [r for r in t["rows"] if not _is_sum(r, max(1, _n_label(t)))]
    if not rows:
        return "segment", 0
    if i_sd is None and i_ed is None:
        return ("project" if len(rows) >= 8 else "segment"), len(rows)
    def _contract_date(r):
        cell = _cell(r, i_sd) + " " + _cell(r, i_ed)
        # "'25.12.31일까지"는 **기준일** 표기지 계약일이 아니다 — 부문 한 줄에 붙는다
        # (HD현대중공업 조선/해양플랜트/기타 3행, HD현대일렉트릭 전기전자부문 1행).
        if "까지" in cell:
            return False
        return bool(_DATE.search(cell))
    dated = sum(1 for r in rows if _contract_date(r))
    # 행이 1~2개면 날짜가 있어도 계약 단위가 아니다 — HD현대일렉트릭은 '전기전자부문' **한 줄**에
    # 수주일자 '2025.12.31 까지'를 적는다. 날짜만 보고 project라 부르면 없는 입도를 주장하게 된다.
    return (("project" if dated >= 0.6 * len(rows) and len(rows) >= 3 else "segment"), len(rows))


def sales_of(t):
    """매출실적 표 → 당기 총매출(백만원). 당기 열은 '제N기'의 최대 N·'당기'·최대 연도로 고른다."""
    cand = []
    for i, c in enumerate(t["ncols"]):
        if re.search(r"비중|비율|증감|구성비|^%|수\s*량", c or ""):
            continue
        m = re.search(r"제(\d+)기", c or "")
        if m:
            cand.append((int(m.group(1)), i, c))
            continue
        m = re.search(r"(20\d{2})", c or "")
        if m:
            cand.append((int(m.group(1)), i, c))
            continue
        if re.search(r"^당기|^당분기|^당반기|^금기", c or ""):
            cand.append((10 ** 6, i, c))
    if not cand:
        # 머리행에 기수가 없으면 첫 숫자 열(대부분 당기)로 폴백하되 근거를 남긴다
        n_label = _n_label(t)
        for i in range(n_label, len(t["cols"]) or 0):
            if any(num_of(_cell(r, i)) is not None for r in t["rows"]):
                cand = [(0, i, (t["cols"][i] if i < len(t["cols"]) else "?") + " (폴백)")]
                break
    if not cand:
        return None
    cand.sort(key=lambda x: -x[0])
    _, i, label = cand[0]
    n_label = max(1, _n_label(t))
    # ① 첫 셀이 합계인 행(총합계)  ② 없으면 라벨 어딘가가 합계인 행을 부문별로 하나씩 더한다
    grand = None
    for r in t["rows"]:
        if _SUM.match(norm_col(_cell(r, 0)) or ""):
            v = num_of(_cell(r, i))
            if v is not None:
                grand = v if grand is None else max(grand, v)
    how = "총합계 행"
    if grand is None:
        groups = {}
        for r in t["rows"]:
            labs = [norm_col(c) for c in r[:n_label]]
            if not any(_SUM_LOOSE.search(x or "") for x in labs):
                continue
            key = tuple(labs[:max(0, next((j for j, x in enumerate(labs) if _SUM_LOOSE.search(x or "")), 0))])
            v = num_of(_cell(r, i))
            if v is not None:
                groups[key] = v
        if groups:
            grand, how = sum(groups.values()), "부문별 합계 행 %d개 합" % len(groups)
    if grand is None:
        return None
    return {"col": label, "raw": grand, "unit_mul": t["unit"], "unit_seen": t["unit_seen"], "cur": t.get("cur"),
            "rev": round(grand * t["unit"], 3), "how": how}


# ── 한 회사 관측 ────────────────────────────────────────────

def probe_one(rec, quarter, force=False, refetch=False):
    st = rec["stock"]
    path = os.path.join(CACHE, "%s_%s.json" % (st, quarter))
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    out = {"stock": st, "name": rec["name"], "market": rec.get("market"),
           "industry": rec.get("industry"), "product": rec.get("product"),
           "quarter": quarter, "tier": "error", "note": "", "rcpNo": None, "title": None}
    try:
        start, end = report_window(quarter)
        reports = search_reports(st, start, end, report_kind(quarter))
        if not reports:                      # 결산월이 12월이 아니거나 신규상장 — 직전 연도로
            q0 = "%dQ4" % (int(quarter[:4]) - 1)
            start, end = report_window(q0)
            reports = search_reports(st, start, end, report_kind(q0))
            if reports:
                out["quarter"] = quarter = q0
        if not reports:
            out.update(tier="error", note="정기보고서 없음(2년)")
            return out
        # 후보를 순서대로 열어 **수주 절이 있는 문서**를 찾는다. 첫 후보로 끝내면 안 된다 —
        # `[첨부정정] 사업보고서 (2025.12)` 는 제목의 기준월이 맞아 맨 앞에 오지만 목차가
        # 「정정 신고」·「영업보고서」 두 줄뿐이다(한화에어로스페이스 012450 실사례).
        cands = pick_report(reports, quarter)[:3]
        rcp = title = found = None
        tried = []
        for rcp_c, title_c in cands:
            nodes = toc(rcp_c)
            hit = None
            for n in nodes or []:
                if any(p in (n.get("text") or "") for p in SECTION_PATTERNS[0][1]):
                    hit = n
                    break
            tried.append({"rcpNo": rcp_c, "title": title_c, "n_nodes": len(nodes or []),
                          "has_sec": bool(hit)})
            if rcp is None:                      # 첫 후보는 근거로 남긴다(절을 못 찾아도)
                rcp, title = rcp_c, title_c
            if hit:
                rcp, title, found = rcp_c, title_c, hit
                break
        out.update(rcpNo=rcp, title=title)
        if len(tried) > 1:
            out["tried"] = tried
        if not found:
            if not any(t["n_nodes"] for t in tried):
                out.update(tier="error", note="목차 없음")
                return out                       # 접근 실패 — 캐시하지 않는다
            out.update(tier="none_sec", note="목차에 매출·수주 절 없음(후보 %d건 확인)" % len(tried))
            os.makedirs(CACHE, exist_ok=True)
            atomic_write(path, json.dumps(out, ensure_ascii=False, indent=1) + "\n")
            return out
        out["sec_title"] = found.get("text")
        hpath = os.path.join(HTML_CACHE, "%s_%s.html" % (st, rcp))
        if os.path.exists(hpath) and not refetch:
            with open(hpath, encoding="utf-8") as f:
                html = f.read()
        else:
            html = fetch_section(found)
            os.makedirs(HTML_CACHE, exist_ok=True)
            atomic_write(hpath, html)
        tabs = norm_tables(html)
        txt = text_of(html)
        out["flags"] = {k: len(re.findall(p, txt, re.I)) for k, p, _ in TEXT_FLAGS}
        out["na_phrase"] = bool(re.search(r"수주[^.\n]{0,20}(해당\s*사항\s*이?\s*없|해당없|없습니다)", txt))
        out["n_tables"] = len(tabs)

        orders, sales, clists = [], [], []
        for t in tabs:
            k = classify(t)
            if k == "clist":
                ic = _idx(t, "cl")
                if ic is None:
                    ic = _find_col(t, re.compile(r"발주처|계약상대|고객|수요처"))
                names = [(_cell(r, ic) or "").strip() for r in t["rows"]]
                names = [n for n in names if n and not _SUM.match(norm_col(n) or "")]
                hidden = sum(1 for n in names if re.search(r"공개\s*유보|비공개|영업비밀|미공개|익명", n))
                clists.append({"n_rows": len(names), "hidden": hidden, "sample": names[:6],
                               "cols": t["cols"], "lead": t["lead"][-120:]})
                continue
            if k in ("std", "roll"):
                b = backlog_of(t, k)
                if b:
                    g, nr = grain_of(t)
                    anon = sum(1 for r in t["rows"] if _ANON.match((_cell(r, 0) or "").strip()))
                    b.update(kind=k, grain=g, n_rows=nr,
                             has_client=_idx(t, "cl") is not None,
                             has_date=(_idx(t, "sd") is not None or _idx(t, "ed") is not None),
                             anon_rows=anon, cols=t["cols"], lead=t["lead"][-120:])
                    orders.append(b)
            elif k == "sales":
                s = sales_of(t)
                if s:
                    s.update(cols=t["cols"], lead=t["lead"][-120:])
                    sales.append(s)
        # 수주 표가 여럿이면 **행이 가장 잘게 쪼개진 것**을 대표로(요약표에 희석되지 않게)
        orders.sort(key=lambda b: (-b["n_rows"], -(b["bal"] or 0)))
        out["orders"] = orders
        out["sales"] = sales
        out["clists"] = clists
        if clists:
            b = max(clists, key=lambda c: c["n_rows"])
            out["clist_rows"], out["clist_hidden"] = b["n_rows"], b["hidden"]
        if sales:
            revs = [s["rev"] for s in sales if s["rev"]]
            out["rev"] = sales[0]["rev"]
            out["rev_cur"] = sales[0].get("cur")
            out["rev_conflict"] = bool(revs and max(revs) > 1.05 * min(revs))
        if orders:
            # 잔고는 **총액이 가장 큰 표**(전사 합계)를 쓴다 — 잘게 쪼갠 표가 일부 부문만일 수 있다.
            # 다만 원화 표를 먼저 본다 — 외화 표(아스트 국외수주 USD)는 환산 없이 비교할 수 없다.
            krw = [b for b in orders if not b.get("cur")]
            fx = [b for b in orders if b.get("cur")]
            best = max(krw or orders, key=lambda b: b["bal"] or 0)
            out["bal_src"] = best["col"]
            out["bal_cur"] = best.get("cur")
            # 원화표·외화표로 **쪼개 실은** 회사(아스트: 국내수주=원, 국외수주=USD)는
            # 원화 표만으로 잔고를 대표할 수 없다 — 합계를 못 만드니 배수를 버린다.
            out["bal_fx_split"] = fx[0]["cur"] if (krw and fx) else None
            # 외화 표뿐이면 **금액을 싣지 않는다**(원문 값은 orders[].raw 에 남는다)
            out["bal"] = None if best.get("cur") else best["bal"]
            if best.get("cur") == "MIX":
                out["note"] = "잔고 표가 환종별(행마다 통화) — 환율 없이 합계를 만들지 않는다"
            elif best.get("cur"):
                out["note"] = "잔고 표가 외화(%s) — 환율 없이 원화로 바꾸지 않는다" % best["cur"]
            out["grain"] = orders[0]["grain"]
            out["n_rows"] = orders[0]["n_rows"]
            out["has_client"] = any(b["has_client"] for b in orders)
            out["has_date"] = any(b["has_date"] for b in orders)
            out["anon_rows"] = max(b["anon_rows"] for b in orders)
            out["top_share"] = (round(100.0 * best["max_row"] / best["bal"], 1)
                                if best.get("max_row") and best["bal"] else None)
            out["tier"] = "proj" if out["grain"] == "project" else "seg"
        else:
            out["tier"] = "no_table"
            out["note"] = ("절에 '수주 해당사항 없음' 문구" if out["na_phrase"]
                           else "수주 절은 있으나 인식되는 수주표 없음(표 %d개)" % len(tabs))
        if out.get("bal") and out.get("rev"):
            m = round(out["bal"] / out["rev"], 2)
            # fail-closed: 배수를 못 믿을 이유가 있으면 **숫자를 버리고 사유를 남긴다**.
            #  · 외화 표를 원화로 읽으면 1000배가 된다(아스트 국외수주 USD)
            #  · 20년치 일감은 수주기반 산업에도 없다 — 단위·열 오독의 신호다
            why = None
            c = out.get("bal_cur") or out.get("rev_cur")
            if c == "MIX":
                why = "행마다 통화가 다른 환종별 표 — 환율 없이 합계를 만들 수 없다"
            elif c:
                why = "외화 표(%s) — 환율 없이 환산하지 않는다" % c
            elif out.get("bal_fx_split"):
                why = ("수주표가 원화·외화(%s)로 나뉘어 있다 — 환율 없이 잔고 합계를 못 만든다"
                       % out["bal_fx_split"])
            elif m > 20:
                why = "배수 %.1f년 — 단위·열 오독으로 보고 버린다" % m
            elif m <= 0:
                why = "잔고 0 이하"
            if why:
                out["mult_reject"] = why
            else:
                out["mult"] = m
        os.makedirs(CACHE, exist_ok=True)
        atomic_write(path, json.dumps(out, ensure_ascii=False, indent=1) + "\n")
        return out
    except Exception as e:
        out.update(tier="error", note="%s: %s" % (type(e).__name__, str(e)[:90]))
        return out                      # 실패는 캐시하지 않는다 — 다시 돌리면 빠진 것만 받는다


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarter", default="2025Q4")
    ap.add_argument("--only", help="종목코드 쉼표 구분")
    ap.add_argument("--force", action="store_true", help="관측 JSON을 무시하고 다시 파싱(원문 캐시는 그대로 쓴다)")
    ap.add_argument("--refetch", action="store_true", help="원문 캐시까지 버리고 DART에서 다시 받는다")
    ap.add_argument("--dump", action="store_true", help="표·근거를 자세히 출력")
    ap.add_argument("--sector", help="그 섹터만")
    a = ap.parse_args()

    if a.only:
        recs = [{"stock": s.strip(), "name": s.strip()} for s in a.only.split(",")]
    else:
        d = load_asset("sample.json")
        seen, recs = set(), []
        for r in d["rows"]:
            if a.sector and r["sector"] != a.sector:
                continue
            if r["stock"] in seen:
                continue
            seen.add(r["stock"])
            recs.append(r)
    t0 = time.time()
    for i, r in enumerate(recs, 1):
        d = probe_one(r, a.quarter, a.force or a.refetch, a.refetch)
        sys.stderr.write("[%3d/%d] %-6s %-16s %-9s bal=%-12s rev=%-12s ×%-6s %s\n" % (
            i, len(recs), d["stock"], (d.get("name") or "")[:16], d["tier"],
            d.get("bal"), d.get("rev"), d.get("mult"), (d.get("note") or "")[:40]))
        sys.stderr.flush()
        if a.dump:
            print(json.dumps(d, ensure_ascii=False, indent=1))
    sys.stderr.write("== %d사 %.0fs\n" % (len(recs), time.time() - t0))


if __name__ == "__main__":
    sys.exit(main())
