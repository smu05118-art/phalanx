#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scout_lib — 웨이브 SCOUT 공용 유틸.

DART 수집·표 파싱·KIND 모집단은 `argus/kce/tools`(와 `argus/kship/tools`)의 것을
**그대로 import** 한다. 복사하지 않는다 — 프로세스 간 요청 게이트·EUC-KR 판정·머리행
평탄화는 산업과 무관한 층이고, 두 벌로 갈라지면 한쪽만 고쳐지는 날이 온다(COMMON.md §1).

여기서 새로 만드는 것은 '수주기반인가'를 재는 자 하나뿐이다.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))            # argus/_specs/scout_tools
SPECS = os.path.dirname(HERE)                                 # argus/_specs
ARGUS = os.path.dirname(SPECS)                                # argus
KCE_TOOLS = os.path.join(ARGUS, "kce", "tools")
KSHIP_TOOLS = os.path.join(ARGUS, "kship", "tools")
ASSETS = os.path.join(HERE, "assets")

for p in (KCE_TOOLS, KSHIP_TOOLS):
    if p not in sys.path:
        sys.path.insert(0, p)

from kce_lib import atomic_write, latest_quarter, num_of, report_kind   # noqa: E402,F401
from kce_fetch import (_get, fetch_section, find_sections, pick_report,  # noqa: E402,F401
                       search_reports, toc)
from kce_parse import parse_tables, unit_scale                           # noqa: E402,F401
from kce_probe import report_window                                      # noqa: E402,F401
from kce_universe import KIND_URL, parse_kind                            # noqa: E402,F401

KIND_CACHE = os.path.join(ASSETS, "kind.json")


def kind_all(force=False):
    """KIND 상장법인목록 전수(업종·주요제품). 한 번 받아 캐시한다 — 요청을 아낀다."""
    if os.path.exists(KIND_CACHE) and not force:
        with open(KIND_CACHE, encoding="utf-8") as f:
            return json.load(f)["rows"]
    rows = parse_kind(_get(KIND_URL))
    os.makedirs(ASSETS, exist_ok=True)
    atomic_write(KIND_CACHE, json.dumps({"source": KIND_URL, "n": len(rows), "rows": rows},
                                        ensure_ascii=False, indent=1) + "\n")
    return rows


def load_asset(name):
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return json.load(f)


def write_asset(name, data):
    os.makedirs(ASSETS, exist_ok=True)
    atomic_write(os.path.join(ASSETS, name),
                 json.dumps(data, ensure_ascii=False, indent=1) + "\n")


def text_of(html):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"[ \t\xa0]+", " ", s)
