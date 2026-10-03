#!/usr/bin/env python3
"""국가 큐브(data_<reg>_country.js)를 core_set 단위 샤드로 쪼갠다.

배경: data_jp_country.js는 8.92MB로 AGENTS.md 8항(파일당 5MB)을 넘는다.
그런데 프론트의 소비 지점 countrySrc()는 언제나 setKey() 하나만 본다
(index.html: `(P.country||{})[sk]`). 158개 세트를 한 덩어리로 받을 이유가 없다.
세트별로 쪼개면 최대 178KB·중앙값 56KB — 한도 준수와 별개로 국가뷰 진입
시 받는 양이 8.92MB에서 수십 KB로 줄어든다.

tools/split_country_shard.py(리전 샤드 → 국가 큐브 분리)의 다음 단계다.
이 스크립트도 검증용 참조 구현이며, 맥스튜디오의 jem_site_build.py에 이식한다.

  usage: split_country_sets.py data_jp_country.js JP [outdir]
         split_country_sets.py data_jp_country.js JP outdir --verify

  출력: <outdir>/<setkey>.js   — PSHC[reg].country[setkey] (+ country_i) 병합 스니펫
        <outdir>/_index.json   — 빌더가 manifest region.csets에 넣을 세트 목록

빌더 계약(맥스튜디오 반영 필요):
  manifest region.cdir  = "data_jp_country/"   ← 샤드 디렉토리
  manifest region.csets = ["probe_core", ...]  ← 존재하는 세트 키(404 방지)
  기존 region.cfile은 cdir 미적용 리전의 폴백으로 남긴다.
"""
import json
import os
import re
import sys

# 파일명으로 그대로 쓰는 키라 경로 조작 문자를 원천 차단한다(fail-closed).
SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
SAFE_REG = re.compile(r"^[A-Z0-9]+$")
DUMP = dict(ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def parse(path, reg):
    """data_<reg>_country.js → {"country":…,"country_i":…} 딕트."""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    marker = 'PSHC["%s"]=' % reg
    i = src.find(marker)
    if i < 0:
        raise SystemExit("ERROR: %s 에 %s 가 없다" % (path, marker))
    return json.loads(src[i + len(marker):].strip().rstrip(";")), len(src.encode())


def shard_js(reg, key, blocks):
    """세트 하나를 PSHC에 병합하는 스니펫. 로드 순서에 무관하게 멱등이다."""
    body = ["var PSHC=window.PSHC||(window.PSHC={});",
            '(function(){var R=PSHC["%s"]||(PSHC["%s"]={});' % (reg, reg)]
    for top in ("country", "country_i"):
        if top in blocks:
            body.append('(R.%s||(R.%s={}))["%s"]=%s;'
                        % (top, top, key, json.dumps(blocks[top], **DUMP)))
    body.append("})();")
    return "".join(body)


def write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    path, reg = argv[1], argv[2]
    outdir = argv[3] if len(argv) > 3 and not argv[3].startswith("-") else "split_sets_out"
    verify = "--verify" in argv

    if not SAFE_REG.match(reg):
        raise SystemExit("ERROR: 리전 코드가 이상하다: %r" % reg)

    cube, srcbytes = parse(path, reg)
    unknown = set(cube) - {"country", "country_i"}
    if unknown:                      # 스키마가 바뀌었는데 조용히 버리면 안 된다
        raise SystemExit("ERROR: 모르는 최상위 키 %s — 스키마 변경 확인" % sorted(unknown))

    # 세트 키 수집(country ∪ country_i). 두 큐브에 같은 키가 있으면 한 파일에 담는다.
    keys = sorted(set(cube.get("country") or {}) | set(cube.get("country_i") or {}))
    bad = [k for k in keys if not SAFE_KEY.match(k)]
    if bad:
        raise SystemExit("ERROR: 파일명으로 쓸 수 없는 세트 키 %s" % bad[:5])
    os.makedirs(outdir, exist_ok=True)
    sizes = {}
    for k in keys:
        blocks = {t: cube[t][k] for t in ("country", "country_i")
                  if k in (cube.get(t) or {})}
        js = shard_js(reg, k, blocks)
        write_atomic(os.path.join(outdir, k + ".js"), js)
        sizes[k] = len(js.encode())

    index = {"region": reg, "sets": keys,
             "in_country": sorted(cube.get("country") or {}),
             "in_country_i": sorted(cube.get("country_i") or {})}
    write_atomic(os.path.join(outdir, "_index.json"),
                 json.dumps(index, indent=1, sort_keys=True, ensure_ascii=False) + "\n")

    if verify and not roundtrip(outdir, reg, cube, keys):
        raise SystemExit("ERROR: 라운드트립 검증 실패 — 샤드를 신뢰하지 마라")

    if not sizes:                    # 국가 큐브가 비어 있는 리전(정상) — 목록만 남긴다
        print("원본 %.2fMB → 세트 0개 (빈 국가 큐브 — 샤드 없음)" % (srcbytes / 1048576))
        return
    mx, tot = max(sizes.values()), sum(sizes.values())
    med = sorted(sizes.values())[len(sizes) // 2]
    print("원본 %.2fMB → 세트 %d개  최대 %.0fKB · 중앙값 %.0fKB · 합계 %.2fMB%s"
          % (srcbytes / 1048576, len(keys), mx / 1024, med / 1024, tot / 1048576,
             "  (라운드트립 OK)" if verify else ""))
    over = [k for k, v in sizes.items() if v > 5 * 1048576]
    if over:
        print("경고: 여전히 5MB를 넘는 세트 %s" % over)


def roundtrip(outdir, reg, cube, keys):
    """샤드를 순서대로 합치면 원본 큐브와 같은가 — 빌더 이식 전 안전장치."""
    got = {}
    for k in keys:
        with open(os.path.join(outdir, k + ".js"), encoding="utf-8") as f:
            js = f.read()
        for top in ("country", "country_i"):
            m = '(R.%s||(R.%s={}))["%s"]=' % (top, top, k)
            i = js.find(m)
            if i < 0:
                continue
            j = js.index(";", i)
            # 값 안의 ';'는 문자열 내부에만 나올 수 있어 json 파서로 되짚는다
            while True:
                try:
                    got.setdefault(top, {})[k] = json.loads(js[i + len(m):j])
                    break
                except ValueError:
                    j = js.index(";", j + 1)
    return got == {t: v for t, v in cube.items() if v}


if __name__ == "__main__":
    main(sys.argv)
