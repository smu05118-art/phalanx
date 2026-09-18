# -*- coding: utf-8 -*-
"""테스트 공용 — sys.path 부트스트랩 · fixture/asset 읽기.

`test*.py` 가 아니므로 discover 가 수집하지 않는다. 각 테스트 파일은 맨 위에서
이 디렉터리를 sys.path 에 넣고 `import _common` 만 하면 된다.

**네트워크를 쓰지 않는다.** 모든 테스트는 tests/fixtures/ 의 원문 HTML 과
tools/assets/ 의 JSON 만 읽는다(COMMON.md §0-3 · §4).
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))            # argus/ksemi/tools/tests
TOOLS = os.path.dirname(HERE)                                # argus/ksemi/tools
FIXTURES = os.path.join(HERE, "fixtures")
ASSETS = os.path.join(TOOLS, "assets")

for _p in (TOOLS, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def fixture(name):
    """fixture 원문 HTML(UTF-8). 없으면 그대로 터진다 — 조용히 넘기지 않는다."""
    with io.open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


def has_asset(name):
    return os.path.exists(os.path.join(ASSETS, name))


def asset(name):
    with io.open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return json.load(f)


# fixture 이름 — 어느 원문인지 한곳에 적어 둔다(PROGRESS.md §1 원문 확인 기록과 대응).
II4_WONIK = "ii4_240810_20260814001845.html"      # 원익IPS 2026 반기 II-4 (§1-3)
II4_HANMI = "ii4_042700_20260814.html"            # 한미반도체 2026 반기 II-4 (§1-5)
ACC_WONIK = "acc_240810_20260316001453.html"      # 원익IPS 2025 사업보고서 주석 (§1-4①)
SEG_WONIK = "seg_240810_20260316001453.html"      # 원익IPS 별도 영업부문 주석 (§1-4②)
SEG_WONIK_CONN = "seg_240810_conn_20260316001453.html"   # 같은 절 연결 기준
