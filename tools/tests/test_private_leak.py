#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""비공개 가정층 누출 가드.

앙상블 기판 섹터(codex_tasks/ensemble_substrate_solder.md)는 애널리스트 메모에서 온 가정을
레포 **밖**(~/phalanx-private/)의 로컬 가정 파일에만 둔다. 이 테스트는 레포에 올라갈 수 있는
파일 전부(추적 파일 + 무시되지 않은 새 파일)를 훑어 세 가지를 막는다.

1. 가정 파일의 표시 문자열(`_marker`·`visibility` 값)
2. 메모 원본 형식(.enex) 파일 자체
3. 로컬 가정 파일이 있는 기계에서는 그 파일의 서술 문장 조각(공백 제거) — 메모리에서만 비교하고 값은 출력하지 않는다

빌더(맥스튜디오 생성기)도 1의 문자열로 공개 산출물을 검사한다(요청서 5항).
"""
import json
import os
import re
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PRIVATE = os.path.expanduser("~/phalanx-private")
# 표시 문자열은 이어 붙여 만든다 — 이 파일 자체가 가드에 걸리지 않게.
MARKERS = (
    "PHALANX-" + "PRIVATE-LAYER",
    '"visibility":' + ' "private"',
    '"visibility":' + '"private"',
)
TEXT_EXT = {".json", ".js", ".html", ".md", ".css", ".py", ".yml", ".yaml", ".txt", ".csv", ".svg", ".cjs", ".mjs"}
BANNED_EXT = {".enex"}
SELF = os.path.abspath(__file__)
NON_NARRATIVE = {"public_check", "from", "to", "line", "kind", "grade", "id", "model", "sector", "bundle",
                 "visibility", "updated", "memo_date"}
MIN_PHRASE = 12            # 이보다 짧은 문장 조각은 흔한 표현과 겹칠 수 있어 비교하지 않는다


def candidate_files():
    """추적 파일 + 무시되지 않은 새 파일(커밋 직전 상태까지 본다)."""
    out = set()
    for args in (["ls-files", "-z"], ["ls-files", "-z", "--others", "--exclude-standard"]):
        res = subprocess.run(["git", "-C", ROOT] + args, check=True, capture_output=True).stdout
        out.update(p for p in res.decode("utf-8").split("\0") if p)
    return sorted(out)


def norm(s):
    return re.sub(r"\s+", "", s)


def private_phrases():
    """로컬 가정 파일의 서술 문장 조각(공백 제거) 집합. 메모리에서만 비교하고 출력하지 않는다. 없으면 빈 집합."""
    out = set()
    if not os.path.isdir(PRIVATE):
        return out
    for dirpath, _dirs, files in os.walk(PRIVATE):
        for name in files:
            if not name.endswith(".json"):
                continue
            with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                data = json.load(f)
            stack = [data]
            while stack:
                v = stack.pop()
                if isinstance(v, dict):
                    # 메타(`_*`)·공개 출처(public_check)·식별자(엔티티 이름·코드)는 비공개 내용이 아니다 — 서술만 본다
                    stack.extend(x for k, x in v.items() if not k.startswith("_") and k not in NON_NARRATIVE)
                elif isinstance(v, list):
                    stack.extend(v)
                elif isinstance(v, str):
                    for part in re.split(r"[.,;:()·—\-\n]+", v):
                        q = norm(part)
                        if len(q) >= MIN_PHRASE:
                            out.add(q)
    return out


class PrivateLeakTests(unittest.TestCase):
    def test_no_private_marker_or_memo_file(self):
        hits = []
        for rel in candidate_files():
            ext = os.path.splitext(rel)[1].lower()
            if ext in BANNED_EXT:
                hits.append("%s: 메모 원본 형식(%s)" % (rel, ext))
                continue
            if ext not in TEXT_EXT:
                continue
            path = os.path.join(ROOT, rel)
            if os.path.abspath(path) == SELF or not os.path.isfile(path):
                continue
            with open(path, "rb") as f:
                data = f.read()
            for m in MARKERS:
                if m.encode("utf-8") in data:
                    hits.append("%s: 비공개 표시" % rel)
        self.assertEqual(hits, [], "비공개 가정층이 레포에 들어오려 함:\n" + "\n".join(hits))

    def test_private_phrases_not_in_repo(self):
        phrases = private_phrases()
        if not phrases:
            self.skipTest("로컬 가정층 없음(CI)")
        hits = []
        for rel in candidate_files():
            if os.path.splitext(rel)[1].lower() not in TEXT_EXT:
                continue
            path = os.path.join(ROOT, rel)
            if os.path.abspath(path) == SELF or not os.path.isfile(path) or os.path.getsize(path) > 3_000_000:
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                text = norm(f.read())
            if any(q in text for q in phrases):
                hits.append(rel)
        self.assertEqual(hits, [], "로컬 가정 파일의 문장이 레포 파일에서 발견됨(값은 출력하지 않음):\n" + "\n".join(hits))

    def test_private_layer_lives_outside_repo(self):
        if not os.path.isdir(PRIVATE):
            self.skipTest("로컬 가정층 없음")
        self.assertFalse(os.path.abspath(PRIVATE).startswith(ROOT + os.sep), "로컬 가정층이 레포 안에 있음")


if __name__ == "__main__":
    unittest.main()
