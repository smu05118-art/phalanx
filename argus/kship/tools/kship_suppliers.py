#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_suppliers — 기자재사의 부품·납품처를 정기보고서 II. 사업의 내용에서 읽는다.

원하는 것 세 가지:
  ① 무슨 부품을 만드는가   — II.2 「주요 제품 및 서비스」 표(품목·매출액·비중)와 KIND 주요제품 문구
  ② 어느 조선사에 파는가   — II 절 본문에서 조선사 이름의 언급(주요 매출처·매출 비중이 있으면 함께)
                              + 재무제표 **주석**(fin_cache — L1 kship_fin 의 DART 원문 캐시, 읽기만)의
                              주요 고객(K-IFRS 1108호)·특수관계자 거래 표. DART 를 다시 두드리지 않고
                              캐시에서 읽는다(--scan-notes → suppliers_cache/<stock>/notes.json)
  ③ 얼마나 파는가          — II.4 매출실적 표(부문·품목별, 수출/내수)

납품 관계의 근거 등급(basis): ifrs8(주요 고객 주석 — 10% 이상 고객·부문별 주요고객에 **이름**이 적힌 것) >
contract(단일판매공급계약 상대방) > related(특수관계자 거래 표의 매출 — 금액 있음) > text(사업의 내용
본문 언급, 비중 없음) > kind(KIND 제품 문구에만 근거). 등급이 낮을수록 화면에서 '추정'으로 표시한다 —
없는 정밀도를 주장하지 않는다. 한 조선사에 근거가 여럿이면 yards 행 하나로 합치고(가장 높은 등급),
증거는 evidence 에 전부 남긴다. 2026-10-05 실측: 주석의 주요 고객은 대부분 'A사·고객 1'로 익명이라
51사 중 4사(동성화인텍·엔케이·한라IMS·현대힘스)만 이름이 있고, 특수관계자 매출 표는 계열 기자재사
4사(HD현대마린솔루션·HD현대마린엔진·한화시스템·현대힘스)에서 조선사별 금액이 나온다.

부품 분류는 parts_taxonomy.json 의 키워드 규칙으로 한다(긴 키워드·높은 우선순위 우선, 부정
키워드 배제, 문맥 필요 낱말은 선박·조선·해양이 함께 있을 때만). 매칭 실패는 UNCL 로 남겨
사람이 override 할 수 있게 한다(assets/parts_override.csv: stock,prod_text,cat[,note] — 근거 'manual').
'제품'·'상품'·'기타'·'합계'·'내부거래' 같은 구분 행과 스크랩·부산물 행은 제품명이 아니라 **건너뛴다**
(분류 실패가 아니다 — unclassified.csv 에 싣지 않고 skipped 로 센다).

    python3 kship_suppliers.py --collect [--quarter 2026Q2] [--only 033500]   # DART II 절 → suppliers_cache/<stock>/<q>.json
    python3 kship_suppliers.py --scan-notes [--only 033500]                   # fin_cache 주석 → suppliers_cache/<stock>/notes.json (DART 없음)
    python3 kship_suppliers.py --build            # 캐시 → assets/suppliers.json (+ unclassified.csv)
"""
import argparse
import csv
import glob
import hashlib
import html as _html
import json
import os
import re
import sys
from collections import Counter

from kship_lib import (ASSETS, atomic_write, fetch_section, find_sections, latest_quarter,
                       load_asset, num_of, parse_tables, pick_report, report_kind,
                       search_reports, toc, write_asset)
from kship_parse import unit_of
from kship_universe import load as load_universe
from kce_probe import report_window                      # noqa: E402

CACHE = os.path.join(ASSETS, "suppliers_cache")
FIN_CACHE = os.path.join(ASSETS, "fin_cache")            # L1(kship_fin) 의 DART 원문 캐시 — 읽기만 한다(git 밖)
SECTIONS = [
    ("products", ["주요 제품", "주요 제품 및 서비스", "주요제품"]),
    ("sales", ["매출 및 수주상황", "매출실적", "수주상황"]),
    ("overview", ["사업의 개요"]),
]

# 조선사 언급 탐지 — 정식명·약칭·구명. (id → 정규식)
# 영문 약칭은 **단어 경계**를 건다 — 'SHI' 는 HANSHIN·SHIPYARD·SHIPBUILDING 의 일부에, 'HHI' 는 HHIC(옛 한진重)에
# 걸려 가짜 삼성重·HD현대重 언급을 만들었다(2026-10-05 주석 캐시 실측: 한신기계 종속기업 'HANSHIN JAPAN' → 010140).
# HD현대 그룹(모호) 표기는 조선과 무관한 계열(오일뱅크·사이트솔루션·로보틱스·엔지니어링·글로벌서비스·지주 ㈜)을 뺀다.
YARD_NAMES = {
    "329180": r"HD현대중공업|현대중공업|\bHHI\b",
    "010140": r"삼성중공업|\bSHI\b",
    "042660": r"한화오션|대우조선해양|대우조선|\bDSME\b",
    "010620": r"HD현대미포|현대미포조선|현대미포",
    "HSHI": r"HD현대삼호|현대삼호중공업|현대삼호",
    "009540": r"HD한국조선해양|한국조선해양",
    "439260": r"대한조선",
    "097230": r"HJ중공업|한진중공업",
    "KSOE_GRP": r"HD현대(?!중공업|미포|삼호|마린|일렉|에너지|건설기계|인프라|오일|사이트|로보|엔지니어링|글로벌|스포츠|㈜)",
}
_YARD_RE = {yid: re.compile(pat) for yid, pat in YARD_NAMES.items()}
BASIS_RANK = {"ifrs8": 0, "contract": 1, "related": 2, "text": 3, "kind": 4}


def _norm(s):
    return re.sub(r"[\s　]+", "", (s or "")).lower()


_TAX = None


def taxonomy():
    global _TAX
    if _TAX is None:
        t = load_asset("parts_taxonomy.json")
        cats = sorted(t["cats"], key=lambda c: -c["prio"])
        _TAX = (t, cats)
    return _TAX


def classify_product(text, marine_ctx=False):
    """제품 문구 → [소분류 id]. 우선순위 높은 소분류부터, 긴 키워드부터. 없으면 ['UNCL']."""
    t, cats = taxonomy()
    n = _norm(text)
    if not n:
        return []
    ctx = marine_ctx or any(k in n for k in ("선박", "조선", "해양", "선용", "marine", "ship", "vessel", "offshore", "해상"))
    hits = []
    for c in cats:
        if any(_norm(x) in n for x in c["neg"]):
            continue
        if c["ctx"] and not ctx:
            continue
        for k in sorted(c["kw"], key=lambda x: -len(x)):
            if _norm(k) and _norm(k) in n:
                hits.append((c["prio"], len(k), c["id"]))
                break
    if not hits:
        return ["UNCL"]
    hits.sort(key=lambda h: (-h[0], -h[1]))
    out = []
    for _, _, cid in hits:
        if cid not in out:
            out.append(cid)
    return out[:4]


# ── 주요 제품 표 ──────────────────────────────────────────────
# 품목 열 후보. '품목·품명·제품명' 이 '구분·매출유형' 보다 먼저다 — 둘 다 있는 표에서 '구분' 을 집으면
# 값이 '제품/상품/기타' 뿐이라 한선엔지니어링은 '제품'×9, 서암기계는 '제 품'×3 으로 읽혔다(2026Q2 캐시 실측).
_NAME_SPECIFIC = ("품목", "품명", "제품명", "주요제품", "제품및서비스", "서비스", "제품군", "품종")
_NAME_GENERIC = ("제품", "구분", "매출유형", "사업부문", "부문")
_GENERIC_VALUE = re.compile(r"^(제품|상품|기타|용역|반제품|수출|내수|국내|해외|합계|소계|계|서비스|제품매출|상품매출|용역매출|기타매출|-|—)$")
# 매출·비율 머리 없이 기간 열만 있는 표(품목 | 제41기 반기 | 제40기) — 첫 기간 열이 당기 금액이다
_PERIOD_COL = re.compile(r"제\s*\d+\s*기|20\d\d|당\s*(?:반\s*)?(?:분\s*)?기|전\s*(?:반\s*)?(?:분\s*)?기|누적|반기|분기")
_TOTAL_ROW = re.compile(r"합\s*계|총\s*계|소\s*계|^\s*계\s*$")
# '매출액 (비율)' 한 열에 '376,610(95.7%)' 로 붙은 셀(동성화인텍 2026 반기 실측) — 금액과 비중을 함께 뽑는다
_COMBO = re.compile(r"^\s*\(?(-?[\d,]+(?:\.\d+)?)\)?\s*\(\s*(-?\d+(?:\.\d+)?)\s*%?\s*\)\s*$")
# '나. 주요 제품 등의 가격변동추이' 표는 품목 × 기간 꼴이라 기간 열 폴백에 걸린다 — 가격표는 매출이 아니다
_PRICE_TABLE = re.compile(r"가격\s*변동|가격\s*추이|판매\s*가격|평균\s*가격|단가")


def _amt_share(cell):
    """'376,610(95.7%)' → (376610.0, 95.7). 아니면 (None, None)."""
    m = _COMBO.match(cell or "")
    if not m:
        return None, None
    return num_of(m.group(1)), num_of(m.group(2))


def _pick_name_col(cols, rows):
    """품목 열 고르기. 고른 열의 값이 절반 넘게 '제품/상품/기타' 같은 구분값이면 다음 후보 열로 넘어간다."""
    cands = [i for i, c in enumerate(cols) if any(k in c for k in _NAME_SPECIFIC)]
    cands += [i for i, c in enumerate(cols) if i not in cands and any(k in c for k in _NAME_GENERIC)]
    for i in cands:
        vals = [_norm(r[i]) for r in rows if i < len(r) and r[i].strip() and not _TOTAL_ROW.search(r[i])]
        if vals and sum(1 for v in vals if _GENERIC_VALUE.match(v)) * 2 <= len(vals):
            return i
    return cands[0] if cands else None


_HDR_NAME = re.compile(r"품목|품명|제품|구분|매출유형|사업부문|서비스")
_HDR_VALUE = re.compile(r"매출|금액|비율|비중|%|" + _PERIOD_COL.pattern)


def _promote_header(t):
    """<td> 만으로 된 머리행을 머리로 올린다 — kce_parse 의 어휘 감지는 건설 표 낱말(공사명·도급액…)이라 '품목 | 제41기 반기 |
    제40기' 나 '사업부문 | 매출유형 | 품목 | 2026년 반기 | 2025년' 을 머리로 보지 않아 cols 가 비고, 그러면 표를 통째로
    버렸다(2026Q2 캐시 51사 중 30사 products 빈 원인으로 실측). 첫 행의 셀이 전부 비수치이고 품목 낱말 하나 + 금액·비율·기간
    낱말 하나가 있으면 머리행이다. 반환 (정규화 머리, 데이터 행)."""
    cols, rows = [_norm(c) for c in t["cols"]], t["rows"]
    if cols or not rows:
        return cols, rows
    first = [c.strip() for c in rows[0]]
    if not first or any(num_of(c) is not None for c in first):
        return cols, rows
    nf = [_norm(c) for c in first]
    if any(_HDR_NAME.search(c) for c in nf) and any(_HDR_VALUE.search(c) for c in nf):
        return nf, rows[1:]
    return cols, rows


def parse_products(html):
    """주요 제품 표 → [{prod, share, amt, cur[, seg][, share_est]}]. 회사마다 열이 달라 품목 열과 '매출액·비중' 열을 찾는다.

    표에 매출·비율 머리가 없고 기간 열(제N기·20XX년·당반기)만 있으면 첫 기간 열을 금액으로 읽고, 합계 행이 있으면
    비중을 나눠 만든다(share_est — 원문에 적힌 비중이 아니다). 사업부문 열이 있으면 seg 로 남겨 분류 폴백에 쓴다."""
    out = []
    for t in parse_tables(html):
        cols, trows = _promote_header(t)
        if not cols or len(trows) < 1:
            continue
        t = dict(t, rows=trows)
        i_name = _pick_name_col(cols, t["rows"])
        # 비중 열은 이름에 '비율/비중'이 있는 열만 믿는다. '%'는 '(단위: 백만원, %)' 같은 단위
        # 캡션이 금액 열에도 붙어 한국카본의 매출액 430,877이 '비중 430877%'로 실렸다.
        i_share = next((i for i, c in enumerate(cols) if "비율" in c or "비중" in c), None)
        if i_share is None:
            i_share = next((i for i, c in enumerate(cols) if c.endswith("%") or "(%)" in c), None)
        # '매출유형'(제품/상품) 열은 금액 열이 아니다 — '매출' 이 들어 있어 금액 열로 잡히면 모든 행의 amt 가 None 이 된다
        i_amt = next((i for i, c in enumerate(cols) if ("매출" in c or "금액" in c) and "유형" not in c and i not in (i_share, i_name)), None)
        period = False
        if i_share is None and i_amt is None:
            per = [i for i, c in enumerate(cols) if i != i_name and _PERIOD_COL.search(c) and not any(k in c for k in _NAME_SPECIFIC)]
            if per:
                i_amt, period = per[0], True
        if i_name is None or (i_share is None and i_amt is None):
            continue
        if period and _PRICE_TABLE.search(t.get("lead") or ""):
            continue                                          # 가격변동추이 표 — 금액이 아니라 단가다
        i_seg = next((i for i, c in enumerate(cols) if ("사업부문" in c or "부문" in c or "사업부" in c) and i not in (i_name, i_share, i_amt)), None)
        i_use = next((i for i, c in enumerate(cols) if "용도" in c and i not in (i_name, i_share, i_amt, i_seg)), None)
        combo = i_share is not None and i_amt is None and any(k in cols[i_share] for k in ("매출", "금액"))
        cur, mul, _ = unit_of(t.get("lead"), t.get("cols"))
        rows, total = [], None
        for r in t["rows"]:
            if i_name >= len(r):
                continue
            name = r[i_name].strip()
            share = num_of(r[i_share]) if i_share is not None and i_share < len(r) else None
            amt = num_of(r[i_amt]) if i_amt is not None and i_amt < len(r) else None
            if combo and share is None and i_share < len(r):
                amt, share = _amt_share(r[i_share])           # '매출액 (비율)' 결합 셀
            if amt is not None and mul != 1.0:
                amt = round(amt * mul, 3)
            if not name or _TOTAL_ROW.search(name):
                if amt is not None and total is None:
                    total = amt                                   # 기간 열 표의 비중 계산용
                continue
            if share is not None and share > 100:      # 비중이 100%를 넘으면 금액을 잘못 읽은 것이다
                amt, share = (amt if amt is not None else share), None
            if share is not None and share < 0:        # 음수 비중은 증감률 행(전년비)이다 — 비중이 아니다
                share = None
            if share is None and amt is None:
                continue
            row = {"prod": name, "share": share, "amt": amt, "cur": cur}
            if i_seg is not None and i_seg < len(r) and r[i_seg].strip() and not _TOTAL_ROW.search(r[i_seg]):
                row["seg"] = r[i_seg].strip()
            if i_use is not None and i_use < len(r) and r[i_use].strip():
                row["use"] = r[i_use].strip()                 # 구체적 용도 — 품목이 상표·품번일 때 분류 폴백
            rows.append(row)
        if period and total:
            for row in rows:
                if row["share"] is None and row["amt"] is not None:
                    row["share"] = round(100.0 * row["amt"] / total, 1)
                    row["share_est"] = True
        out.extend(rows)
    return out


# ── 조선사 언급 ──────────────────────────────────────────────

def yard_ids_in(text):
    """문장·셀 안의 조선사 id 집합."""
    return {yid for yid, rx in _YARD_RE.items() if rx.search(text or "")}


def find_yard_mentions(text):
    """본문에서 조선사 언급을 센다. {yard_id: count}."""
    found = {}
    for yid, rx in _YARD_RE.items():
        n = len(rx.findall(text))
        if n:
            found[yid] = n
    return found


def _text_of(html):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)                                  # '&nbsp;'·'&amp;' 가 낱말을 가르지 않게
    return re.sub(r"[ \t\xa0]+", " ", s)


def parse_major_customers(html):
    """'주요 매출처'·'10% 이상 고객' 표/문장에서 비중을 뽑는다(있으면)."""
    text = _text_of(html)
    out = []
    for m in re.finditer(r"([가-힣A-Za-z&()㈜ ]{2,24}(?:중공업|조선|오션|조선해양|\bHHI\b|\bSHI\b|\bDSME\b))[^0-9%]{0,40}?(\d{1,2}(?:\.\d)?)\s*%", text):
        party = m.group(1).strip()
        # 상대 표기를 조선사 id 로 정규화한다 — 문장 조각('…매출기준으로 현대중공업')이 그대로
        # 화면에 실리던 것을 막고, 페이지가 조선사 링크를 걸 수 있게.
        yid = next((k for k, rx in _YARD_RE.items() if rx.search(party)), None)
        if not yid:
            continue
        out.append({"party": party[-12:], "yard": yid, "share": float(m.group(2)), "basis": "text"})
    seen, uniq = set(), []
    for c in out:
        if c["yard"] in seen:
            continue
        seen.add(c["yard"]); uniq.append(c)
    return uniq[:8]


_MARINE_TERM = re.compile(r"선박|조선소|조선사|조선업|조선 ?산업|조선기자재|조선해양|박용|해양플랜트|선급|선주|LNG ?선|LNG ?운반선|"
                          r"컨테이너선|유조선|벌크선|함정|잠수함|해상풍력|선박용|marine|vessel|shipyard|shipbuilding", re.I)


def collect_one(rec, quarter, force=False):
    st = rec["stock"]
    path = os.path.join(CACHE, st, quarter + ".json")
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    start, end = report_window(quarter)
    reports = pick_report(search_reports(st, start, end, report_kind(quarter)), quarter)
    if not reports and int(quarter[5]) != 4:                      # 코넥스 등 연 1회
        q2 = "%dQ4" % (int(quarter[:4]) - 1)
        start, end = report_window(q2)
        reports = pick_report(search_reports(st, start, end, report_kind(q2)), q2)
        quarter = q2 if reports else quarter
    out = {"stock": st, "quarter": quarter, "ok": False, "note": ""}
    if not reports:
        out["note"] = "정기보고서 없음"
        return out
    rcp, title = reports[0]
    nodes = toc(rcp)
    found = find_sections(nodes, SECTIONS)
    out.update({"rcp": rcp, "title": title})
    texts, products, cust = [], [], []
    for key in ("products", "sales", "overview"):
        if key not in found:
            continue
        html = fetch_section(found[key])
        texts.append(_text_of(html))
        if key == "products":
            products = parse_products(html)
        if key in ("sales", "products"):
            cust += parse_major_customers(html)
    blob = " ".join(texts)
    out["products"] = products
    out["mentions"] = find_yard_mentions(blob)
    out["customers"] = cust
    out["marine_ctx"] = bool(re.search(r"선박|조선|해양|선용|marine|offshore", blob))
    # 탐색(모집단 확장)용 증거 — 본문에서 조선을 말하는 낱말의 횟수. '조선'·'해양' 낱말 자체는 너무 넓어 뺀다.
    terms = Counter(m.group(0) for m in _MARINE_TERM.finditer(blob))
    out["marine_hits"] = sum(terms.values())
    out["marine_terms"] = dict(terms.most_common(8))
    out["ok"] = bool(texts)
    if not out["ok"]:
        out["note"] = "II 절을 찾지 못함"
        return out
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write(path, json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    return out


# ── 재무제표 주석(fin_cache) 에서 고객 재탐색 — DART 없음 ──────────────────────────

_CUST_KW = re.compile(r"주요\s*고객|단일\s*고객|주요\s*거래처|주요\s*매출처")
_SENT_END = re.compile(r"(?:습니다|입니다)(?:\s*\([^)]{0,40}\))?\s*\.")      # '…입니다(주석 24 참조).' 도 문장 끝
_REL_KW = "특수관계자"


def _plain(html):
    """주석 HTML → 평문(태그 제거·엔티티 복원·공백 정규화)."""
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s)


def _snippet(text, start, end, pad=70):
    a, b = max(0, start - pad), min(len(text), end + pad)
    return ("…" if a else "") + text[a:b].strip() + ("…" if b < len(text) else "")


def extract_notes_customers(html, rev_m=None):
    """재무제표 주석 HTML → {"ifrs8": [{yard, evidence}], "related": [{yard, sales_m, evidence[, share_est]}]}.

    ifrs8 — ① '주요 고객·단일 고객·주요 거래처' 문장(첫 '…습니다.' 까지)에 조선사 이름이 있으면(현대힘스:
            "단일고객은 HD현대중공업㈜ 및 HD현대삼호㈜이며 …입니다."), ② 머리에 '주요고객' 열이 있는 부문 표의 행에
            조선사 이름이 있으면(동성화인텍 '보냉재사업부문 | 보냉재 등 | 현대중공업 등'). 'A사·고객 1' 처럼 익명이면
            아무것도 만들지 않는다.
    related — lead 나 머리에 '특수관계자' 가 있고 '매출' 열(매출채권·채무·기타수익 제외)이 있는 표에서 앞 두 셀에
            조선사 이름이 있는 행의 **첫 매출 열** 금액. 단위 캡션으로 백만원 환산(없으면 금액 없이 연결만). 조선사마다
            첫 표(당기)만 — 전기·채권 표는 건너뛴다. rev_m(그 분기 누적 매출, 백만원)이 있으면 share_est = 매출/누적매출
            — 추정 표시.
    담보권자·관계기업 지분 표처럼 고객이 아닌 문맥의 이름은 어느 규칙에도 걸리지 않는다(실측: SK오션플랜트의
    '삼성중공업의 공사대금 담보', 한화시스템의 '관계기업 한화오션 지분 12.04%')."""
    text = _plain(html)
    ifrs8, seen = [], set()
    for m in _CUST_KW.finditer(text):
        seg = text[m.start(): m.start() + 600]
        e = _SENT_END.search(seg)
        win = seg[:e.end()] if e else seg
        for yid in sorted(yard_ids_in(win)):
            if yid in seen:
                continue
            seen.add(yid)
            mm = _YARD_RE[yid].search(win)
            ifrs8.append({"yard": yid, "evidence": _snippet(win, mm.start(), mm.end())})
    tables = parse_tables(html)
    for t in tables:
        cols = [_norm(c) for c in t["cols"]]
        if not any(("주요고객" in c or "주요거래처" in c or "주요매출처" in c) for c in cols):
            continue
        for row in t["rows"]:
            line = " | ".join(c.strip() for c in row if c.strip())
            for yid in sorted(yard_ids_in(line)):
                if yid in seen:
                    continue
                seen.add(yid)
                ifrs8.append({"yard": yid, "evidence": line[:160]})
    related, rseen = [], set()
    for t in tables:
        lead = t.get("lead") or ""
        cols = [_norm(c) for c in t["cols"]]
        if _REL_KW not in lead and not any(_REL_KW in c for c in cols):
            continue
        sales = [i for i, c in enumerate(cols) if "매출" in c and not re.search(r"채권|채무|기타수익|기타매출", c)]
        if not sales:
            continue
        cur, mul, seen_unit = unit_of(lead, t["cols"])
        for row in t["rows"]:
            ys = yard_ids_in(" ".join(row[:2]))
            if not ys:
                continue
            i = sales[0]
            v = num_of(row[i]) if i < len(row) else None
            if v is None or v <= 0:
                continue
            for yid in sorted(ys):
                if yid in rseen:
                    continue
                rseen.add(yid)
                sales_m = round(v * mul, 3) if seen_unit and cur == "KRW" else None
                who = " ".join(c.strip() for c in row[:2] if c.strip())[:40]
                x = {"yard": yid, "sales_m": sales_m, "evidence": "특수관계자 거래 매출 %s (%s)" % (row[i].strip(), who)}
                if sales_m is not None and rev_m:
                    x["share_est"] = round(100.0 * sales_m / rev_m, 2)          # 0.03% 같은 미미한 거래도 0 으로 뭉개지 않게
                related.append(x)
    return {"ifrs8": ifrs8, "related": related}


def latest_notes_file(stock):
    """fin_cache/<stock>/<q>_note_parent_cons.html 의 최신 분기(없으면 _sep). (경로, 분기, 연결/별도) 또는 (None,)*3.
    주석 **전체**(부모 절) 캐시만 본다 — 금융수익 같은 개별 주석 캐시(_note_fin)에는 고객 정보가 없다."""
    for scope in ("cons", "sep"):
        fs = sorted(glob.glob(os.path.join(FIN_CACHE, stock, "*_note_parent_%s.html" % scope)))
        if fs:
            return fs[-1], os.path.basename(fs[-1])[:6], scope
    return None, None, None


def _fin_rev_ytd(stock, q, scope):
    """assets/fin/<stock>.json 의 그 분기 누적 매출(백만원) — share_est 분모. 없으면 None."""
    try:
        f = load_asset("fin/%s.json" % stock)
    except Exception:
        return None
    v = (((f.get(scope) or {}).get("is_ytd") or {}).get(q) or {}).get("매출액(수익)")
    return v if isinstance(v, (int, float)) and v > 0 else None


def scan_notes(recs, log=sys.stderr):
    """fin_cache 주석 → suppliers_cache/<stock>/notes.json. 시각을 적지 않는다(원문 sha 로 식별) — 같은 입력은 같은 바이트.
    fin_cache 는 git 밖(actions/cache)이라 러너마다 있을 수도 없을 수도 있다 — 그래서 결과를 git 안의 suppliers_cache 에
    남기고 build 는 그것만 읽는다(scan-kship 러너처럼 fin_cache 가 없는 곳에서도 suppliers.json 이 같게)."""
    n_src = n_hit = 0
    for r in recs:
        path, q, scope = latest_notes_file(r["stock"])
        if not path:
            log.write("%s %-12s 주석 캐시 없음\n" % (r["stock"], r["name"][:12]))
            continue
        with open(path, "rb") as f:
            raw = f.read()
        html = raw.decode("utf-8", "replace")
        rev = _fin_rev_ytd(r["stock"], q, scope)
        found = extract_notes_customers(html, rev)
        out = {"stock": r["stock"], "q": q, "scope": scope, "src": os.path.basename(path),
               "sha12": hashlib.sha256(raw).hexdigest()[:12], "rev_ytd_m": rev,
               "ifrs8": found["ifrs8"], "related": found["related"]}
        os.makedirs(os.path.join(CACHE, r["stock"]), exist_ok=True)
        atomic_write(os.path.join(CACHE, r["stock"], "notes.json"), json.dumps(out, ensure_ascii=False, indent=1) + "\n")
        n_src += 1
        if found["ifrs8"] or found["related"]:
            n_hit += 1
        log.write("%s %-12s %s %s ifrs8=%s related=%s\n" % (
            r["stock"], r["name"][:12], q, scope, [x["yard"] for x in found["ifrs8"]] or "-",
            [(x["yard"], x.get("sales_m"), x.get("share_est")) for x in found["related"]] or "-"))
    log.write("주석 캐시 %d사 읽음 · 조선사 고객 근거 %d사 → suppliers_cache/<stock>/notes.json\n" % (n_src, n_hit))
    return n_src, n_hit


# ── 빌드 ─────────────────────────────────────────────────────

_QFILE = re.compile(r"^\d{4}Q[1-4]\.json$")
# 제품명이 아닌 행 — 구분(제품/상품/기타/합계/내부거래…)과 부산물(스크랩·고철). 분류 실패로 세지 않는다.
_NON_PRODUCT = re.compile(r"^(제품|상품|기타|용역|반제품|제품매출|상품매출|용역매출|기타매출|기타제품|기타수익|내부거래|연결조정|"
                          r"소계|합계|총계|제품계|상품계|기타계|기타주\)?|-|—|–|\.|n/a)$")
_BYPRODUCT = re.compile(r"스크랩|부산물|고철|폐자재")


def skip_reason(prod):
    """제품명이 아닌 행이면 그 사유('구분'·'부산물'), 제품이면 None."""
    n = _norm(prod)
    if not n or _NON_PRODUCT.match(n):
        return "구분"
    if _BYPRODUCT.search(n):
        return "부산물"
    return None


def _latest_cache(dirpath):
    """suppliers_cache/<stock>/ 의 최신 분기 캐시(<q>.json). notes.json 같은 다른 파일은 보지 않는다 —
    sorted()[-1] 로 집던 때는 'n' 이 '2' 뒤라 notes.json 이 분기 캐시로 읽혔을 것이다."""
    if not os.path.isdir(dirpath):
        return None
    fs = sorted(f for f in os.listdir(dirpath) if _QFILE.match(f))
    if not fs:
        return None
    with open(os.path.join(dirpath, fs[-1]), encoding="utf-8") as f:
        return json.load(f)


def _notes_cache(dirpath):
    p = os.path.join(dirpath, "notes.json")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _overrides():
    p = os.path.join(ASSETS, "parts_override.csv")
    if not os.path.exists(p):
        return {}
    out = {}
    with open(p, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[(row["stock"], _norm(row["prod_text"]))] = row["cat"]
    return out


def merge_yards(mentions, customers, notes):
    """조선사별 yards 행 하나 — basis 는 가장 높은 등급, share 는 원문 비중(ifrs8/text) > 특수관계자 매출 추정(share_est),
    mentions 는 II 절 언급 횟수, evidence 는 근거 전부. 정렬: 등급 → 비중 → 언급 → id (결정론)."""
    by = {}

    def ent(yid):
        return by.setdefault(yid, {"yard": yid, "mentions": None, "basis": None, "share": None, "share_est": False, "evidence": []})

    for yid, n in sorted((mentions or {}).items(), key=lambda kv: (-kv[1], kv[0])):
        e = ent(yid)
        e["mentions"], e["basis"] = n, "text"
    notes = notes or {}
    for x in notes.get("ifrs8") or []:
        e = ent(x["yard"])
        e["basis"] = "ifrs8"
        e["evidence"].append({"basis": "ifrs8", "q": notes.get("q"), "note": x.get("evidence", "")})
    for x in notes.get("related") or []:
        e = ent(x["yard"])
        if BASIS_RANK.get(e["basis"], 9) > BASIS_RANK["related"]:
            e["basis"] = "related"
        if x.get("share_est") is not None and e["share"] is None:
            e["share"], e["share_est"] = x["share_est"], True
        e["evidence"].append({"basis": "related", "q": notes.get("q"), "note": x.get("evidence", ""), "sales_m": x.get("sales_m")})
    # II 절 '주요 매출처 … N%' 문장의 비중은 조선사별 금액이 있는 특수관계자 표보다 뒤에 — 문장 조각 정규식은 둘을 합친
    # 비중('HD현대중공업 및 HD현대삼호 … 95%')을 한 조선사에 붙이기 쉽다(현대힘스 실측: 95.0 vs 41.1+55.2).
    for c in customers or []:
        yid = c.get("yard") or next((k for k, rx in _YARD_RE.items() if rx.search(c.get("party") or "")), None)
        if not yid:
            continue
        e = ent(yid)
        e["basis"] = e["basis"] or "text"
        if c.get("share") is not None and e["share"] is None:
            e["share"], e["share_est"] = c["share"], False
        e["evidence"].append({"basis": "text", "note": "II 절 주요 매출처 문장 %s%% (%s)" % (c.get("share"), c.get("party") or "")})
    return sorted(by.values(), key=lambda e: (BASIS_RANK.get(e["basis"], 9), -(e["share"] or 0), -(e["mentions"] or 0), e["yard"]))


def build_company(r, d, ovr, notes=None):
    """한 회사의 suppliers.json 행 — 순수 함수(파일 I/O 없음). 반환 (co, 미분류 행 [(stock, name, prod)], 건너뛴 행 수)."""
    ctx = bool(d and d.get("marine_ctx")) or r["industry"] == "선박 및 보트 건조업" or bool(r.get("reason"))
    cats, uncl, skipped = [], [], 0
    seen_uncl = set()
    srcs = (d.get("products") if d else None) or []
    if not srcs:
        srcs = [{"prod": r["product"], "share": None, "amt": None, "cur": None, "kind": True}]
    for pr in srcs:
        if not pr.get("kind") and skip_reason(pr.get("prod")):
            skipped += 1
            continue
        if pr.get("share") is not None and pr["share"] > 100:     # 옛 캐시의 오독 방어
            pr = dict(pr, amt=pr.get("amt") if pr.get("amt") is not None else pr["share"], share=None)
        if pr.get("share") is not None and pr["share"] < 0:       # 증감률 행 — 비중이 아니다
            pr = dict(pr, share=None)
        key = (r["stock"], _norm(pr["prod"]))
        manual = key in ovr
        ids = [ovr[key]] if manual else classify_product(pr["prod"], ctx)
        label = pr["prod"]
        if ids == ["UNCL"] and (pr.get("use") or pr.get("seg")):
            # 품목이 상표·품번·구분이라 못 나누면 '구체적 용도'(동성화인텍 'R-PUF 외' → '초저온보냉재'), 그다음 사업부문 이름으로
            # 한 번 더(KCC '도료' 부문의 제품 코드) — 추정 표시
            for alt in (pr.get("use"), pr.get("seg")):
                alt_ids = [c for c in classify_product(alt, ctx) if c != "UNCL"] if alt else []
                if alt_ids:
                    ids, label = alt_ids, "%s › %s" % (alt, pr["prod"])
                    break
        for cid in ids:
            if cid == "UNCL":
                if key[1] in seen_uncl:
                    continue                                       # 같은 품목이 수출/내수·당기/전기로 되풀이된 행
                seen_uncl.add(key[1])
                uncl.append((r["stock"], r["name"], pr["prod"]))
            cats.append({"cat": cid, "prod": label, "share": pr.get("share"), "amt": pr.get("amt"),
                         "est": (len(ids) > 1 or bool(pr.get("kind")) or label != pr["prod"] or bool(pr.get("share_est"))) and not manual,
                         "basis": "manual" if manual else ("kind" if pr.get("kind") else "report")})
    # 시드 사유에 적힌 제품도 분류에 보탠다(KIND 문구가 빈약한 회사: 한국카본 '카본').
    # 탐색('탐색 — … 선급 1회')의 사유는 증거 문장이지 제품이 아니다 — 지정 사유만 본다.
    if r.get("reason") and r.get("source") == "지정":
        for cid in classify_product(r["reason"], True):
            if cid != "UNCL" and cid not in {c["cat"] for c in cats}:
                cats.append({"cat": cid, "prod": r["reason"].split("—")[-1].strip(), "share": None, "amt": None, "est": True, "basis": "seed"})
    # 주요제품 표가 '제품'·'기타'·품번뿐이라 아무것도 못 나누면(케이씨씨·한선엔지니어링) KIND 제품 문구로 한 번 더 —
    # 근거는 'kind'(추정)로 남긴다. override 는 (종목, KIND 문구)로도 걸 수 있다.
    if not [c for c in cats if c["cat"] != "UNCL"] and r.get("product"):
        key = (r["stock"], _norm(r["product"]))
        for cid in ([ovr[key]] if key in ovr else classify_product(r["product"], ctx)):
            if cid != "UNCL" and cid not in {c["cat"] for c in cats}:
                cats.append({"cat": cid, "prod": r["product"][:40], "share": None, "amt": None, "est": key not in ovr,
                             "basis": "manual" if key in ovr else "kind"})
    yards = merge_yards((d or {}).get("mentions"), (d or {}).get("customers"), notes)
    co = {"stock": r["stock"], "nm": r["name"], "mkt": r["market"], "ind": r["industry"],
          "role": r["role"], "prod_raw": r["product"], "reason": r.get("reason", ""),
          "cats": cats, "yards": yards, "rcp": (d or {}).get("rcp"), "quarter": (d or {}).get("quarter"),
          "confirmed": bool(yards), "link_basis": yards[0]["basis"] if yards else None,
          "notes_q": (notes or {}).get("q"), "skipped": skipped, "seen": bool(d)}
    return co, uncl, skipped


def build(quarter):
    uni = load_universe()
    ovr = _overrides()
    cos, uncl, skipped = [], [], 0
    for r in uni:
        if r["role"] not in ("equip", "engine", "steel"):
            continue
        cdir = os.path.join(CACHE, r["stock"])
        co, u, s = build_company(r, _latest_cache(cdir), ovr, _notes_cache(cdir))
        cos.append(co)
        uncl.extend(u)
        skipped += s
    write_asset("suppliers.json", {"quarter": quarter, "n": len(cos), "cos": cos})
    with open(os.path.join(ASSETS, "unclassified.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stock", "name", "prod_text"])
        for row in uncl:
            w.writerow(row)
    return cos, uncl, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--scan-notes", action="store_true", help="fin_cache 주석에서 주요 고객·특수관계자 매출을 읽어 suppliers_cache/<stock>/notes.json (DART 없음)")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--quarter", default=None)
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    q = a.quarter or latest_quarter()
    recs = [r for r in load_universe() if r["role"] in ("equip", "engine", "steel")]
    if a.only:
        sel = set(a.only.split(","))
        recs = [r for r in recs if r["stock"] in sel]
    if a.collect:
        for r in recs:
            try:
                d = collect_one(r, q, a.force)
            except Exception as e:
                print("%s %s 실패: %s" % (r["stock"], r["name"], e), file=sys.stderr)
                continue
            print("%s %-12s %s 제품 %d · 조선사 언급 %s" % (r["stock"], r["name"][:12], "✓" if d.get("ok") else "✗ " + d.get("note", ""),
                                                      len(d.get("products") or []), d.get("mentions") or {}))
    if a.scan_notes:
        scan_notes(recs)
    if a.build:
        cos, uncl, skipped = build(q)
        print("기자재사 %d · 조선사 연결 %d · 미분류 제품 %d · 구분·부산물 행 건너뜀 %d" % (len(cos), sum(1 for c in cos if c["confirmed"]), len(uncl), skipped))
        print("연결 근거 등급:", dict(Counter(y["basis"] for co in cos for y in co["yards"])),
              "· 회사 최고 등급:", dict(Counter(c["link_basis"] or "none" for c in cos)))
        print("소분류 분포:", dict(Counter(c["cat"] for co in cos for c in co["cats"]).most_common(12)))


if __name__ == "__main__":
    sys.exit(main())
