#!/usr/bin/env python3
"""korea_trade.html(9.84MB)에서 국가 드릴다운 큐브를 떼어내 5MB 아래로 내린다.

AGENTS.md 8항(파일당 5MB) 위반 3건 중 하나. 이 페이지는 index.html의 iframe
오버레이로 열리는 자체완결 대시보드인데, 전체가 사실상 `var TD={…}` 인라인
스크립트 하나(9.81MB)다. 그중 rows[].c(HS6×국가 월별)가 6.66MB로 75%를
차지하는데, 이걸 읽는 곳은 **클릭해야 열리는 드릴다운 두 군데뿐**이다:

  · toggleExpand(tr,r)          — 급등·급락 표의 행 펼침
  · renderBrowse()의 BR.openHs  — 분류 브라우저의 행 펼침

둘 다 `dimItems(r.c, lat)` 한 줄이라, c를 HS2별 JSON으로 떼어 클릭 시점에
fetch하면 된다. 여기에 `c[].nm` 중복 제거(같은 국가명을 3.8만 번 반복한다)를
더하면 본문이 9.84MB → 3.2MB가 된다.

주의: "최신월만 남기자"는 안 된다. 월 선택 <select id="month">가 meta.months
15개월을 전부 옵션으로 깔고 state.lat을 바꾸며, 드릴다운이 그 값을 쓴다.
15개월은 전부 살려야 한다.

  usage: shrink_korea_trade.py korea_trade.html [--out DIR] [--check]

  --check  쓰지 않고 예상 크기만 보고한다
  멱등하다 — 이미 줄인 파일에 다시 돌리면 아무것도 하지 않는다.

출력: korea_trade.html                  (본문, rows[].c 없음)
      korea_trade_country/<hs2>.json    (HS2별 국가 큐브, 96개)
"""
import json
import os
import re
import sys

MARK = "/*shrunk:v1*/"
SHARD_DIR = "korea_trade_country"
DUMP = dict(ensure_ascii=False, separators=(",", ":"))

# 드릴다운 지연 로더. dimItems는 이미 `dim[k].nm||CN[k]||RN[k]||k` 로 폴백하므로
# c[].nm 을 지워도 확장된 TD.cnames 로 이름이 나온다.
LOADER = MARK + """
/* 국가 드릴다운 지연 로드 — rows[].c 는 HS2별 샤드로 분리돼 클릭 시 붙는다.
   (tools/shrink_korea_trade.py 가 주입. 원본은 c를 인라인으로 들고 있었다.) */
const CDIR='%s/', _CS={}, _CQ={}, _ROWBYHS={};
TD.rows.forEach(r=>{_ROWBYHS[r.hs]=r;});
function _applyShard(h2){const j=_CS[h2];if(!j||j==='err')return;
  Object.keys(j).forEach(hs=>{const r=_ROWBYHS[hs];if(r&&!r.c)r.c=j[hs];});}
function needC(hs,cb){
  const r=_ROWBYHS[hs];
  if(!r||r.c)return cb();
  const h2=String(hs).slice(0,2);
  if(_CS[h2]){ if(_CS[h2]==='err'){r.c={};} else {_applyShard(h2);} return cb(); }
  if(_CQ[h2]){ _CQ[h2].push(cb); return; }
  _CQ[h2]=[cb];
  const done=()=>{const q=_CQ[h2]||[];_CQ[h2]=null;q.forEach(f=>{try{f();}catch(e){console.warn(e);}});};
  fetch(CDIR+h2+'.json')
    .then(x=>x.ok?x.json():Promise.reject(x.status))
    .then(j=>{_CS[h2]=j;_applyShard(h2);})
    .catch(e=>{_CS[h2]='err';r.c={};console.warn('국가 큐브 로드 실패',h2,e);})
    .then(done);
}
""" % SHARD_DIR


def fail(msg):
    raise SystemExit("ERROR: " + msg)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def split_td(html):
    """`var TD=` … `;</script>` 구간을 (앞, TD딕트, 뒤)로 가른다."""
    i = html.find("var TD=")
    if i < 0:
        fail("var TD= 를 찾지 못했다 — 페이지 구조가 바뀌었다")
    j = html.index("</script>", i)
    raw = html[i + len("var TD="):j].strip().rstrip(";")
    try:
        return i, json.loads(raw), j
    except ValueError as e:
        fail("TD JSON 파싱 실패: %s" % e)


def patch_render(js):
    """렌더 스크립트의 두 드릴다운 진입점을 지연 로드로 감싼다."""
    edits = [
        # 1) 급등·급락 표: 접기 판정 뒤, 펼치기 직전에 큐브를 확보한다
        ("""  if(nx&&nx.classList.contains('exprow')){nx.remove();tr.classList.remove('exp');return;}""",
         """  if(nx&&nx.classList.contains('exprow')){nx.remove();tr.classList.remove('exp');return;}
  if(!r.c) return needC(r.hs,()=>toggleExpand(tr,r));   /*shrunk:v1*/"""),
        # 2) 분류 브라우저: 펼치는 경우에만 받아온다(접을 땐 불필요)
        ("""function brOpen(hs){BR.openHs=BR.openHs===hs?null:hs;renderBrowse();}""",
         """function brOpen(hs){BR.openHs=BR.openHs===hs?null:hs;                    /*shrunk:v1*/
  if(BR.openHs) return needC(BR.openHs,renderBrowse);
  renderBrowse();}"""),
    ]
    for old, new in edits:
        if old not in js:
            fail("렌더 스크립트에서 패치 지점을 못 찾았다:\n  %s" % old.strip()[:70])
        js = js.replace(old, new, 1)

    anchor = "/* ============================================================ TAXONOMY ======"
    if anchor not in js:
        fail("로더 삽입 지점(TAXONOMY 주석)을 못 찾았다")
    return js.replace(anchor, LOADER + "\n" + anchor, 1)


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    src = argv[1]
    outdir = argv[argv.index("--out") + 1] if "--out" in argv else os.path.dirname(src) or "."
    check = "--check" in argv

    html = read(src)
    if MARK in html:
        print("이미 줄인 파일이다 — 할 일 없음 (%s)" % MARK)
        return
    before = len(html.encode())
    i, td, j = split_td(html)

    rows = td.get("rows")
    if not isinstance(rows, list) or not rows:
        fail("TD.rows 가 비었다")
    if "c" not in rows[0]:
        fail("rows[].c 가 없다 — 이미 분리됐거나 스키마가 바뀌었다")

    # --- 국가명 사전을 데이터에서 직접 만든다(기존 cnames는 41개국뿐) ---
    names = dict(td.get("cnames") or {})
    names_before = len(names)
    shards, nc, weird, overridden = {}, 0, 0, set()
    for r in rows:
        c = r.pop("c", None) or {}
        for code, cv in c.items():
            nm = cv.pop("nm", None)
            if nm:                          # 인라인 nm이 드릴다운에 실제로 찍히던 이름이라
                if code in names and names[code] != nm:   # 기존 cnames보다 우선한다
                    overridden.add(code)    # (CN은 dimItems에서만 쓰여 부작용이 없다)
                names[code] = nm
            if cv.pop("w", None):          # 스키마에만 남은 잔재 — 실제로 0건
                weird += 1
            nc += 1
        h2 = r["hs"][:2]
        if c:
            shards.setdefault(h2, {})[r["hs"]] = c
    td["cnames"] = names

    body = html[:i] + "var TD=" + json.dumps(td, **DUMP) + html[j:]
    tail = body.index("</script>", body.index("var TD=")) + len("</script>")
    m = re.search(r"<script[^>]*>(.*?)</script>", body[tail:], re.S)
    if not m:
        fail("렌더 스크립트를 못 찾았다")
    body = body[:tail] + body[tail:tail + m.start(1)] + patch_render(m.group(1)) \
        + body[tail + m.end(1):]

    after = len(body.encode())
    sizes = {h2: len(json.dumps(v, **DUMP).encode()) for h2, v in shards.items()}
    print("본문 %.2fMB → %.2fMB   샤드 %d개 최대 %.0fKB · 합계 %.2fMB"
          % (before / 1048576, after / 1048576, len(sizes),
             max(sizes.values()) / 1024, sum(sizes.values()) / 1048576))
    print("국가 엔트리 %d건에서 중복 국가명 제거, cnames %d → %d개국%s%s"
          % (nc, names_before, len(names),
             "  (기존 이름 %d건 교체: %s)" % (len(overridden), ",".join(sorted(overridden)))
             if overridden else "",
             "" if not weird else "  (c[].w %d건 제거)" % weird))
    if after > 5 * 1048576:
        print("경고: 본문이 아직 5MB를 넘는다")
    if check:
        print("--check — 아무것도 쓰지 않았다")
        return

    d = os.path.join(outdir, SHARD_DIR)
    os.makedirs(d, exist_ok=True)
    for h2, v in shards.items():
        if not re.match(r"^[0-9]{2}$", h2):
            fail("HS2 코드가 이상하다: %r" % h2)
        write_atomic(os.path.join(d, h2 + ".json"), json.dumps(v, sort_keys=True, **DUMP))
    write_atomic(os.path.join(outdir, os.path.basename(src)), body)
    print("→ %s + %s/*.json" % (os.path.join(outdir, os.path.basename(src)), d))


if __name__ == "__main__":
    main(sys.argv)
