#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_universe — 국내 상장 건설사 모집단을 KIND 상장법인목록에서 확정한다.

모집단 규칙(UPDATE.md §0):
  · **핵심**: KRX KIND 상장법인목록의 업종(표준산업분류)이 건설업 4종인 종목 전부
    — 건물 건설업 / 토목 건설업 / 실내건축 및 건축마무리 공사업 /
      기반조성 및 시설물 축조관련 전문공사업
  · **부가**: 업종이 건설업이 아니지만 실질이 건설인 종목(삼성물산=기타 전문 도매업,
    삼성E&A=건축기술 엔지니어링). 원본 encprojects 7사가 여기에 걸린다.
업종만으로 자르면 삼성물산·삼성E&A가 빠지고, 반대로 게임·발전 회사가 섞여 들어온다.
전자는 SEED로 되살리고 후자는 프로브(kce_probe.py)가 수주 절 부재로 걸러낸다 —
**이름으로 임의 배제하지 않는다.** 배제는 관측 근거(수주 절 없음)로만 한다.

규약: stdlib 전용 · fail-closed(목록이 급감하면 쓰지 않고 예외).
사용:
    python3 kce_universe.py            # 조회만 — 무엇이 잡히는지 출력
    python3 kce_universe.py --write    # assets/universe.json 갱신
"""
import argparse
import html as _html
import json
import os
import re
import sys

from kce_lib import CORP, atomic_write

HERE = os.path.dirname(os.path.abspath(__file__))
UNIVERSE = os.path.join(HERE, "assets", "universe.json")

KIND_URL = ("https://kind.krx.co.kr/corpgeneral/corpList.do"
            "?method=download&searchType=13")

# 표준산업분류상 건설업(KSIC 41~43)에 해당하는 KIND 업종명. 부분일치가 아니라
# 완전일치로 본다 — '건축자재 도매업'처럼 '건축'만 겹치는 업종을 끌어오지 않기 위해.
CONSTRUCTION_INDUSTRIES = (
    "건물 건설업",
    "토목 건설업",
    "실내건축 및 건축마무리 공사업",
    "기반조성 및 시설물 축조관련 전문공사업",
)

# 업종 밖이지만 건설 실질이 있어 반드시 포함해야 하는 종목(종목코드 → 사유)
SEED_EXTRA = {
    "028260": "삼성물산 — 업종은 기타 전문 도매업이나 건설부문이 주력 (원본 7사)",
    "028050": "삼성E&A — 업종은 건축기술 엔지니어링이나 EPC 시공사 (원본 7사)",
}

# 원본 복제본의 슬러그. 신규 종목은 종목코드를 슬러그로 쓴다(로마자 표기 추정 배제).
LEGACY_SLUG = {v["stock"]: co for co, v in CORP.items()}

MIN_ROWS = 2000            # KIND 전체 목록이 이보다 적으면 응답이 깨진 것으로 본다
MIN_CONSTRUCTION = 40      # 건설업 종목이 이보다 적으면 업종명 체계가 바뀐 것


def _cells(tr):
    return [_html.unescape(re.sub("<[^>]+>", "", c)).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]


def parse_kind(raw):
    """KIND 상장법인목록(EUC-KR HTML 표) → 레코드 목록.

    열: 회사명·시장구분·종목코드·업종·주요제품·상장일·결산월·대표자명·홈페이지·지역.
    머리행을 위치로 믿지 않고 이름으로 찾는다 — 열 순서가 바뀌면 예외로 막는다.
    """
    text = raw.decode("euc-kr", "replace") if isinstance(raw, bytes) else raw
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S)
    if not trs:
        raise RuntimeError("KIND 목록에서 행을 찾지 못했다 — 응답 형식이 바뀌었다")
    head = _cells(trs[0])
    need = ("회사명", "시장구분", "종목코드", "업종", "주요제품", "상장일")
    idx = {}
    for k in need:
        if k not in head:
            raise RuntimeError("KIND 머리행에 '%s'가 없다: %r" % (k, head))
        idx[k] = head.index(k)
    out, seen = [], set()
    for tr in trs[1:]:
        c = _cells(tr)
        if len(c) < len(head):
            continue
        # 종목코드는 숫자 6자리가 아닐 수 있다 — 스팩·리츠에 'KB제33호스팩=0072Z0'처럼
        # 영문이 섞인다. 비숫자를 지우면 '000720'(현대건설)과 충돌해 실종목을 덮는다.
        stock = c[idx["종목코드"]].strip().upper()
        if not re.fullmatch(r"[0-9A-Z]{6}", stock) or stock in seen:
            continue                       # KIND는 같은 종목을 중복 게재하기도 한다
        seen.add(stock)
        out.append({
            "stock": stock,
            "name": c[idx["회사명"]],
            "market": c[idx["시장구분"]],
            "industry": c[idx["업종"]],
            "product": c[idx["주요제품"]],
            "listed": c[idx["상장일"]],
        })
    if len(out) < MIN_ROWS:
        raise RuntimeError("KIND 목록이 %d행뿐 — 응답이 잘렸다" % len(out))
    return out


def select(recs):
    """모집단 선별. 반환 레코드에 slug·source를 붙인다."""
    picked = []
    for r in recs:
        if r["industry"] in CONSTRUCTION_INDUSTRIES:
            src = "업종"
        elif r["stock"] in SEED_EXTRA:
            src = "지정"
        else:
            continue
        d = dict(r)
        d["slug"] = LEGACY_SLUG.get(r["stock"], r["stock"])
        d["source"] = src
        picked.append(d)
    got = {r["stock"] for r in picked}
    missing = sorted(set(SEED_EXTRA) - got) + sorted(set(LEGACY_SLUG) - got)
    if missing:
        raise RuntimeError("모집단에서 필수 종목이 빠졌다(상장폐지·업종변경?): %s" % missing)
    n_ind = sum(1 for r in picked if r["source"] == "업종")
    if n_ind < MIN_CONSTRUCTION:
        raise RuntimeError("건설업 종목이 %d개뿐 — KIND 업종명 체계가 바뀌었다" % n_ind)
    picked.sort(key=lambda r: r["stock"])
    return picked


def fetch(write=False):
    from kce_fetch import _get                       # 순환 임포트 회피(호출 시점 로드)
    recs = select(parse_kind(_get(KIND_URL)))
    if write:
        os.makedirs(os.path.dirname(UNIVERSE), exist_ok=True)
        atomic_write(UNIVERSE, json.dumps(
            {"source": KIND_URL, "n": len(recs), "rows": recs},
            ensure_ascii=False, indent=1) + "\n")
    return recs


def load():
    """캐시된 모집단. 없으면 빈 목록(호출측이 fetch 여부를 정한다)."""
    if not os.path.exists(UNIVERSE):
        return []
    with open(UNIVERSE, encoding="utf-8") as f:
        return json.load(f)["rows"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="assets/universe.json 갱신")
    a = ap.parse_args()
    recs = fetch(write=a.write)
    for r in recs:
        print("%-8s %-6s %-20s %-4s %s" % (r["slug"], r["stock"], r["name"],
                                           r["market"], r["industry"]))
    print("— %d종목 (업종 %d · 지정 %d)"
          % (len(recs), sum(r["source"] == "업종" for r in recs),
             sum(r["source"] == "지정" for r in recs)), file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
