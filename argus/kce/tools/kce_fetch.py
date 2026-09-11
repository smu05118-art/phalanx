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
try:
    import fcntl                                   # POSIX 전용 — 없으면 프로세스 간 게이트를 끈다
except ImportError:                              # pragma: no cover
    fcntl = None
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from concurrent import futures

from kce_lib import CORP, report_kind, atomic_write

HERE = os.path.dirname(os.path.abspath(__file__))
ALLOW_HOSTS = ("dart.fss.or.kr", "opendart.fss.or.kr", "kind.krx.co.kr")
MAX_BYTES = 30 * 1024 * 1024
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) kce_fetch/1.0"}

# 정기보고서 목차에서 찾을 절 (제목 부분 문자열 → 저장 키)
SECTION_PATTERNS = [
    ("ii4",  ["수주상황", "매출 및 수주상황"]),
    ("ii4x", ["상세표", "수주현황(상세)", "건설계약 수주현황"]),   # 삼성물산형 XII 상세표
    ("p8",   ["기타 재무에 관한 사항"]),                         # 라. 진행률적용 수주계약 포함 절
]


# DART는 연속 요청에 약하다 — GitHub Actions에서 7사를 잇달아 조회하다 전 회사가
# `urlopen error timed out`으로 실패한 적이 있다(2026-09-06 실행). 재시도와 요청 간
# 최소 간격으로 흡수한다.
RETRIES = 5
BACKOFF = (2, 5, 10, 20, 30)  # 초
MIN_GAP = 0.7                 # 요청 사이 최소 간격(초) — **전역** 총 요청률 상한
_last_call = [0.0]
_pace_lock = threading.Lock()

# 병렬 레인 수. 수집 시간의 대부분은 DART 응답 대기라 레인을 늘리면 그 대기가 겹쳐
# 빨라진다. 총 요청률은 위 MIN_GAP 토큰버킷이 전역으로 묶으므로 레인을 늘려도
# DART가 받는 부하는 그대로다 — 스로틀을 피하면서 벽시계 시간만 줄인다.
LANES = int(os.environ.get("KCE_LANES") or 6)


# ── 프로세스 사이 게이트 ─────────────────────────────────────────────────────
# DART는 **공인 IP 단위**로 막는다. 스레드 레인은 위 _pace_lock이 묶지만, 수집기를 두세 개
# 동시에 띄우면(탭이 늘면서 실제로 일어난다) 각자 자기 몫만 지켜 총 요청률이 배가 되고
# 30~60분 차단당한다(2026-09-10 실측). 그래서 같은 머신의 **모든 프로세스**가 파일 락
# 하나로 마지막 요청 시각을 공유한다 — 락은 간격 계산 동안만 잡고, 응답 대기 중에는 푼다.
_GATE = os.environ.get("DART_GATE") or os.path.join(tempfile.gettempdir(), "argus_dart_gate")


def _pace_cross_process():
    """파일 락으로 마지막 요청 시각을 공유해 프로세스가 몇 개든 총 요청률을 1/MIN_GAP로 묶는다.

    fcntl이 없거나(윈도우) 락 파일을 못 쓰면(권한·tmpfs 없음) 조용히 스레드 페이싱만 쓴다 —
    수집을 세우는 것보다 낫지만, 그때는 수집기를 하나씩 돌려야 한다.
    """
    if fcntl is None:
        return False
    try:
        fd = os.open(_GATE, os.O_RDWR | os.O_CREAT, 0o666)
    except OSError:
        return False
    try:
        while True:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                raw = os.read(fd, 64).decode("ascii", "replace").split("\x00")[0].strip()
                last = float(raw) if raw.replace(".", "", 1).isdigit() else 0.0
                now = time.time()                      # 프로세스 간 비교라 monotonic 불가
                wait = MIN_GAP - (now - last)
                if wait <= 0 or wait > 60:             # 시계가 뒤로 갔거나 오래된 값
                    stamp = ("%.6f" % now).encode("ascii")
                    os.lseek(fd, 0, os.SEEK_SET)
                    os.write(fd, stamp)
                    os.ftruncate(fd, len(stamp))       # NUL 패딩이 남으면 값이 안 읽혀 게이트가 열린다
                    return True
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
            time.sleep(min(wait, MIN_GAP))
    finally:
        os.close(fd)


def _pace():
    """전역 요청 간격 유지. 여러 레인·여러 프로세스가 동시에 들어와도 총 요청률은 1/MIN_GAP를 넘지 않는다."""
    while True:
        with _pace_lock:
            now = time.monotonic()
            wait = MIN_GAP - (now - _last_call[0])
            if wait <= 0:
                _last_call[0] = now
                _pace_cross_process()
                return
        time.sleep(wait)


def parallel(items, fn, lanes=None, on_done=None):
    """items를 레인 나눠 처리하고 **입력 순서 그대로** 결과를 돌려준다.

    한 항목이 실패해도 전체를 세우지 않는다 — 예외를 그 자리에 담아 호출측이 판단한다.
    """
    lanes = lanes or LANES
    out = [None] * len(items)
    if lanes <= 1:
        for i, it in enumerate(items):
            try:
                out[i] = fn(it)
            except Exception as e:
                out[i] = e
            if on_done:
                on_done(i, it, out[i])
        return out
    with futures.ThreadPoolExecutor(max_workers=lanes) as ex:
        fut = {ex.submit(fn, it): i for i, it in enumerate(items)}
        for f in futures.as_completed(fut):
            i = fut[f]
            try:
                out[i] = f.result()
            except Exception as e:
                out[i] = e
            if on_done:
                on_done(i, items[i], out[i])
    return out


def _get(url, data=None, timeout=45):
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or u.hostname not in ALLOW_HOSTS:
        raise ValueError("allowlist 밖 URL: %s" % url)
    last = None
    for i in range(RETRIES):
        _pace()
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("응답 크기 상한 초과: %s" % url)
            return body
        except ValueError:
            raise                                  # 크기 초과·allowlist는 재시도 무의미
        except Exception as e:                     # 타임아웃·연결 리셋·5xx
            last = e
            if i < RETRIES - 1:
                sys.stderr.write("[retry %d/%d] %s — %s\n"
                                 % (i + 1, RETRIES - 1, type(e).__name__, url[:90]))
                # RETRIES와 BACKOFF 길이가 어긋나도 죽지 않는다
                time.sleep(BACKOFF[min(i, len(BACKOFF) - 1)] if BACKOFF else 1)
    raise last


def _decode(body, rcp_no=""):
    # 거래소공시(rcpNo 9번째 자리가 8 — 800xxx 뿐 아니라 801xxx 도 있다)는 EUC-KR.
    # '800' 완전일치로 두었더니 [기재정정] 단일판매ㆍ공급계약(…801172)이 전부 깨진 글자로
    # 캐시됐다(조선 척당 계약 23건). 세 자리가 아니라 첫 자리로 판정한다.
    if len(rcp_no) == 14 and rcp_no[8] == "8":
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

def api_key():
    """OpenDART 인증키(없으면 None). 있으면 목록 조회를 API로 한다."""
    k = (os.environ.get("DART_API_KEY") or "").strip()
    return k or None


_CORP_CACHE = os.path.join(HERE, "assets", "corp_codes.json")


def corp_codes(key=None):
    """종목코드 → DART 고유번호(corp_code) 매핑. 7사분만 캐시한다.

    corpCode.xml은 전 상장사를 담은 수 MB ZIP이라 매번 받지 않는다. 한 번 받아
    `assets/corp_codes.json`에 저장하면 이후 실행은 네트워크 없이 끝난다.
    키가 없으면 캐시만 읽고, 캐시도 없으면 빈 dict를 돌려준다(호출측이 웹으로 폴백).
    """
    if os.path.exists(_CORP_CACHE):
        with open(_CORP_CACHE, encoding="utf-8") as f:
            return json.load(f)
    key = key or api_key()
    if not key:
        return {}
    import io
    import xml.etree.ElementTree as ET
    import zipfile
    blob = _get("https://opendart.fss.or.kr/api/corpCode.xml?"
                + urllib.parse.urlencode({"crtfc_key": key}))
    if blob[:2] != b"PK":
        # 인증 실패 등은 ZIP이 아니라 XML 에러로 온다(status 010=미등록 키 등).
        msg = blob.decode("utf-8", "replace")
        m = re.search(r"<status>(\d+)</status>.*?<message>([^<]*)</message>", msg, re.S)
        raise RuntimeError("corpCode.xml: %s" % (
            "%s %s" % (m.group(1), m.group(2).strip()) if m else msg[:120]))
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        xml = z.read(z.namelist()[0])
    want = {v["stock"]: co for co, v in CORP.items()}
    out = {}
    for el in ET.fromstring(xml).iter("list"):
        stock = (el.findtext("stock_code") or "").strip()
        if stock in want:
            out[stock] = (el.findtext("corp_code") or "").strip()
    if len(out) != len(want):
        missing = sorted(set(want) - set(out))
        raise RuntimeError("corpCode.xml에서 못 찾은 종목: %s" % missing)
    os.makedirs(os.path.dirname(_CORP_CACHE), exist_ok=True)
    atomic_write(_CORP_CACHE, json.dumps(out, ensure_ascii=False,
                                         indent=1, sort_keys=True) + "\n")
    return out


def api_list(corp_code, bgn, end, detail_ty, key=None):
    """정기보고서 목록(rcept_no 등). 검색 HTML 파싱보다 안정적이다."""
    key = key or api_key()
    if not key:
        raise RuntimeError("DART_API_KEY 필요 (opendart.fss.or.kr 무료 발급)")
    q = urllib.parse.urlencode({
        "crtfc_key": key, "corp_code": corp_code, "bgn_de": bgn, "end_de": end,
        "pblntf_detail_ty": detail_ty, "page_count": 100})
    j = json.loads(_get("https://opendart.fss.or.kr/api/list.json?" + q))
    if j.get("status") == "013":               # 조회 결과 없음 — 오류가 아니다
        return []
    if j.get("status") != "000":
        raise RuntimeError("list.json 오류: %s %s" % (j.get("status"), j.get("message")))
    return j.get("list", [])


def api_reports(co, bgn, end, detail_ty, key=None):
    """api_list 결과를 search_reports와 같은 [(rcpNo, 제목)] 형태로 변환."""
    codes = corp_codes(key)
    cc = codes.get(CORP[co]["stock"])
    if not cc:
        raise RuntimeError("corp_code 미확보: %s" % co)
    out = []
    for it in api_list(cc, bgn, end, detail_ty, key):
        out.append((it.get("rcept_no", ""), (it.get("report_nm") or "").strip()))
    return out


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
