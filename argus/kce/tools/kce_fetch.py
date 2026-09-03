#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_fetch — DART에서 수주 관련 절 HTML을 수집한다 (전 경로 실검증됨, UPDATE.md §2).

두 경로:
  · 무키(웹): detailSearch.ax 검색 → dsaf001/main.do 목차 JS → report/viewer.do 절 다운로드
  · OpenAPI: list.json(rcept_no 목록)·corpCode.xml — DART_API_KEY 환경변수 필요.
    본문 추출은 키가 있어도 viewer.do 절 단위가 더 가볍다(document.xml은 전체 ZIP).

규약: stdlib 전용 · https·호스트 allowlist 강제 · 응답 크기 상한 · fail-closed.
사용례:
  python3 kce_fetch.py --co sct --quarter 2026Q2 --out /tmp/kce_raw
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

from kce_lib import CORP, report_kind, atomic_write

ALLOW_HOSTS = ("dart.fss.or.kr", "opendart.fss.or.kr")
MAX_BYTES = 30 * 1024 * 1024
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) kce_fetch/1.0"}

# 정기보고서 목차에서 찾을 절 (제목 부분 문자열 → 저장 키)
SECTION_PATTERNS = [
    ("ii4",  ["수주상황", "매출 및 수주상황"]),
    ("ii4x", ["상세표", "수주현황(상세)", "건설계약 수주현황"]),   # 삼성물산형 XII 상세표
    ("p8",   ["기타 재무에 관한 사항"]),                         # 라. 진행률적용 수주계약 포함 절
]


def _get(url, data=None, timeout=60):
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or u.hostname not in ALLOW_HOSTS:
        raise ValueError("allowlist 밖 URL: %s" % url)
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("응답 크기 상한 초과: %s" % url)
    return body


def _decode(body, rcp_no=""):
    # 거래소공시(rcpNo 9번째 자리부터 800)는 EUC-KR
    if len(rcp_no) == 14 and rcp_no[8:11] == "800":
        return body.decode("euc-kr", "replace")
    return body.decode("utf-8", "replace")


# ── 무키 웹 경로 ─────────────────────────────────────────────

def search_reports(corp_name, start, end, public_type):
    """공시 검색. public_type: A001 사업 / A002 반기 / A003 분기 / I001 거래소 수시.
    반환: [(rcpNo, 제목)] 접수일 내림차순."""
    body = urllib.parse.urlencode({
        "currentPage": 1, "maxResults": 100, "sort": "date", "series": "desc",
        "textCrpNm": corp_name, "startDate": start, "endDate": end,
        "publicType": public_type,
    }).encode()
    html = _decode(_get("https://dart.fss.or.kr/dsab007/detailSearch.ax", body))
    out = []
    # 제목에 중첩 태그가 섞이는 경우가 있다([기재정정] 배지 등) — <a> 안쪽을 통째로 잡아
    # 태그를 걷어내야 제목이 빈 문자열로 남지 않는다.
    for m in re.finditer(r"main\.do\?rcpNo=(\d{14})[^>]*>(.*?)</a>", html, re.S):
        title = re.sub(r"<[^>]*>", " ", m.group(2))
        out.append((m.group(1), re.sub(r"\s+", " ", title).strip()))
    return out


_REPORT_TITLE = re.compile(r"(사업|반기|분기)보고서\s*\((\d{4})\.(\d{2})\)")


def pick_report(reports, quarter):
    """검색 결과에서 그 분기의 정기보고서 후보를 **적합한 순서로** 돌려준다.

    `reports[0]`을 그냥 쓰면 안 된다 — 같은 기간에 접수된 `정정신고(보고)`가 목록 맨 위에
    오면 수주 절이 없는 문서를 붙잡고 실패한다(DL이앤씨 2025Q4 실사례). 제목의 기준월이
    분기말과 맞는 것만 남기고, 그마저 없으면 원래 순서로 폴백한다.
    """
    y, qn = int(quarter[:4]), int(quarter[5])
    want = "%04d.%02d" % (y, qn * 3)
    good, rest = [], []
    for rcp, title in reports:
        m = _REPORT_TITLE.search(title or "")
        if m and "%s.%s" % (m.group(2), m.group(3)) == want:
            good.append((rcp, title))
        else:
            rest.append((rcp, title))
    return good + rest


def toc(rcp_no):
    """뷰어 main.do의 인라인 JS 목차 → [{'text','rcpNo','dcmNo','eleId','offset','length','dtd'}]"""
    html = _decode(_get("https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + rcp_no))
    nodes, cur = [], {}
    for m in re.finditer(
            r"node\d*\['(text|rcpNo|dcmNo|eleId|offset|length|dtd)'\]\s*=\s*[\"']?([^\"';]*)[\"']?;",
            html):
        k, v = m.group(1), m.group(2)
        if k == "text" and cur:
            nodes.append(cur)
            cur = {}
        cur[k] = v
    if cur:
        nodes.append(cur)
    # 거래소공시(dtd=HTML)는 목차 없이 viewDoc(...) 한 줄
    if not any(n.get("dcmNo") for n in nodes):
        m = re.search(r'viewDoc\("(\d{14})",\s*"(\d+)"', html)
        if m:
            nodes = [{"text": "본문", "rcpNo": m.group(1), "dcmNo": m.group(2),
                      "eleId": "0", "offset": "0", "length": "0", "dtd": "HTML"}]
    return [n for n in nodes if n.get("dcmNo")]


def fetch_section(node):
    q = urllib.parse.urlencode({
        "rcpNo": node["rcpNo"], "dcmNo": node["dcmNo"], "eleId": node.get("eleId", "0"),
        "offset": node.get("offset", "0"), "length": node.get("length", "0"),
        "dtd": node.get("dtd") or "dart4.xsd"})
    return _decode(_get("https://dart.fss.or.kr/report/viewer.do?" + q),
                   node["rcpNo"])


def find_sections(nodes, patterns=SECTION_PATTERNS):
    """목차에서 절 제목 부분 문자열 매칭(eleId는 회사별 상이 — 제목으로만 결정)."""
    out = {}
    for key, pats in patterns:
        for n in nodes:
            t = n.get("text", "")
            if any(p in t for p in pats):
                out.setdefault(key, n)
    return out


# ── OpenAPI (DART_API_KEY 필요) ─────────────────────────────

def api_list(corp_code, bgn, end, detail_ty, key=None):
    key = key or os.environ.get("DART_API_KEY")
    if not key:
        raise RuntimeError("DART_API_KEY 필요 (opendart.fss.or.kr 무료 발급)")
    q = urllib.parse.urlencode({
        "crtfc_key": key, "corp_code": corp_code, "bgn_de": bgn, "end_de": end,
        "pblntf_detail_ty": detail_ty, "page_count": 100})
    j = json.loads(_get("https://opendart.fss.or.kr/api/list.json?" + q))
    if j.get("status") != "000":
        raise RuntimeError("list.json 오류: %s %s" % (j.get("status"), j.get("message")))
    return j.get("list", [])


# ── CLI ──────────────────────────────────────────────────────

def fetch_quarter(co, quarter, out_dir):
    """분기 정기보고서의 수주 관련 절 3종을 out_dir/<co>_<key>.html 로 저장."""
    name = CORP[co]["name"]
    y, qn = int(quarter[:4]), int(quarter[5])
    # 정기보고서 접수는 분기말 +45일(사업보고서 +90일) 안팎
    start = "%d%02d01" % (y, qn * 3)
    endm = qn * 3 + (4 if qn == 4 else 3)
    ey = y + (1 if endm > 12 else 0)
    end = "%d%02d28" % (ey, (endm - 1) % 12 + 1)
    reports = search_reports(name, start, end, report_kind(quarter))
    if not reports:
        raise RuntimeError("%s %s 정기보고서 검색 결과 없음" % (name, quarter))
    # 후보를 순회한다 — 첫 후보가 정정신고처럼 수주 절이 없는 문서일 수 있다.
    rcp_no = title = nodes = found = None
    tried = []
    for cand_rcp, cand_title in pick_report(reports, quarter)[:5]:
        cand_nodes = toc(cand_rcp)
        if not cand_nodes:
            tried.append((cand_rcp, "목차 없음"))
            continue
        cand_found = find_sections(cand_nodes)
        if "ii4" in cand_found or "ii4x" in cand_found:
            rcp_no, title, nodes, found = cand_rcp, cand_title, cand_nodes, cand_found
            break
        tried.append((cand_rcp, "수주 절 없음"))
    if found is None:
        raise RuntimeError("%s %s: 수주상황 절이 있는 보고서를 찾지 못함 (시도: %s)"
                           % (name, quarter, tried))
    os.makedirs(out_dir, exist_ok=True)
    meta = {"co": co, "quarter": quarter, "rcpNo": rcp_no, "title": title, "sections": {}}
    for key, node in found.items():
        html = fetch_section(node)
        path = os.path.join(out_dir, "%s_%s.html" % (co, key))
        atomic_write(path, html)
        meta["sections"][key] = {"path": path, "text": node["text"], "bytes": len(html)}
    atomic_write(os.path.join(out_dir, "%s_meta.json" % co),
                 json.dumps(meta, ensure_ascii=False, indent=1))
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--co", required=True, choices=sorted(CORP))
    ap.add_argument("--quarter", required=True, help="예: 2026Q2")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    meta = fetch_quarter(a.co, a.quarter, a.out)
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
