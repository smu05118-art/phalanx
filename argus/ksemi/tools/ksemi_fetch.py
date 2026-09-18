#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ksemi_fetch — kce_fetch 위에 **인코딩 판정 한 가지만** 덮어쓴다.

네트워크 층(무키 3단 경로·재시도·프로세스 간 요청 게이트·allowlist)은 `kce_fetch` 를 그대로
쓴다(COMMON.md §1). 여기서 다시 만드는 것은 `_decode` 의 판정 하나다.

원문 근거 — `kce_fetch._decode` 는 접수번호 9번째 자리가 `8`이면 EUC-KR로 본다.
그런데 **코스닥시장본부 접수 공시는 그 자리가 `9`** 이고 역시 EUC-KR이다:

  · 주성엔지니어링 20240710900488 「단일판매ㆍ공급계약체결(자율공시)」 — rcpNo[8]=='9'.
    UTF-8로 읽으면 전부 깨지고(`1. �ǸŤ����ް��`), EUC-KR로 읽으면
    `1. 판매ㆍ공급계약 내용 반도체 제조장비 … 3. 계약상대방 SK하이닉스 … 4. 판매ㆍ공급지역 중국`
    가 그대로 나온다(2026-09-11 실측).
  · 한미반도체 20260608800436 은 rcpNo[8]=='8' — 기존 규칙으로도 맞는다.

반도체장비사는 코스닥 상장이 대부분이라 이 한 자리를 놓치면 계약 공시가 통째로 깨져 캐시된다
(조선 탭이 801172 에서 겪은 사고와 같은 종류다). kce 의 전역 동작을 건드리지 않기 위해
**바이트를 받는 `_get` 만 재사용**하고 디코딩은 여기서 한다.
"""
import urllib.parse

from kce_fetch import _get, search_reports as _search_reports_kce   # noqa: F401

# 거래소(유가 8·코스닥 9) 접수 공시는 EUC-KR. 정기보고서(0·1·…)는 UTF-8.
EXCHANGE_MARK = ("8", "9")


def decode(body, rcp_no=""):
    if len(rcp_no) == 14 and rcp_no[8] in EXCHANGE_MARK:
        return body.decode("euc-kr", "replace")
    return body.decode("utf-8", "replace")


def search_reports(corp_name, start, end, public_type):
    """공시 검색. 반환 [(rcpNo, 제목)] 접수일 내림차순.

    검색 결과 페이지 자체는 UTF-8이라 판정이 필요 없다 — kce 와 같은 동작이지만,
    본문 디코딩을 여기서 하므로 호출측이 한 모듈만 보게 하려고 다시 내보낸다.
    """
    return _search_reports_kce(corp_name, start, end, public_type)


def toc(rcp_no):
    """뷰어 main.do 의 인라인 JS 목차 → 노드 목록. main.do 는 UTF-8."""
    from kce_fetch import toc as _toc
    return _toc(rcp_no)


def fetch_section(node):
    """절 HTML. **접수번호로 인코딩을 정한다**(위 EXCHANGE_MARK)."""
    q = urllib.parse.urlencode({
        "rcpNo": node["rcpNo"], "dcmNo": node["dcmNo"], "eleId": node.get("eleId", "0"),
        "offset": node.get("offset", "0"), "length": node.get("length", "0"),
        "dtd": node.get("dtd") or "dart4.xsd"})
    return decode(_get("https://dart.fss.or.kr/report/viewer.do?" + q), node["rcpNo"])
