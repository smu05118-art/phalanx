#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hdrmap — 머리행 지도 공용 엔진 (argus 전 탭 · 표준 라이브러리만).

왜 있나
  DART 정기보고서 표는 회사가 분기마다 열 이름을 바꾸거나 표를 쪼개고, 그것이 조용한 데이터 손실의
  원인이다(headers.html 머리말). 지금까지 기록은 kce 정밀 17사의 headers.html(상류 산출, 우리 빌더는
  한 번도 적지 않았다)뿐이고, lite 36사·kdef·kship 등은 머리행을 어디에도 남기지 않는다. 이 모듈은
  **파서가 본 표(채택·비채택·미지)를 탭 공통 스키마로 기록**하고, 직전 분기와 대조하고, 미지 열을
  사람/자동 큐로 올리고, headers.html 꼴의 지도를 그린다. 파서는 호출하지 않는다 — kship_parse 가
  kce_parse._HDR_VOCAB 전역을 잠시 바꾸는 레이스가 있어, 엔진은 파싱 **결과**만 받는다.

데이터 모델 (모두 `argus/<tab>/tools/assets/` 아래, 정규화 JSON = 키 정렬·indent 1·개행 고정·실행 시각 없음)
  hdrmap.json   {"tab": tab, "companies": {key: {"name", "stock", "fq": [분기…],
                                                 "roles": {role: {분기: [entry…]}}}}}
      key  = kce 는 슬러그(hec…), 다른 탭은 종목코드.  role ∈ ROLES (orders|progress|xi|revenue|segsales|customers)
             — 절 키가 아니라 **표 역할**이다. kdef 등은 'sales' 한 절에 수주·매출·부문 표가 섞인다.
      entry = {cols_raw, cols(복구본), ncols(norm_col), fields(별칭 매핑), n, n_rec, lead(꼬리 120자),
               ent, tag, basis, cur, unit_seen, synth(None|True|'2row'), shape, pick, reason, sec_title, rcpNo}
          n     = 머리행 **포함** 원행수 — 상류 D 의 관례(현대건설 2026Q2 II-4 [62,43,21,4]). **호출측이 명시한 값만** 적는다.
          n_rec = 파서가 레코드로 삼은 행수([61,42,20,3]). 둘을 병기해 '합계·소계를 뺐는가'를 지도에서 읽는다.
                  둘 다 **추정하지 않는다** — 입력 조합별 해석(_entry):
                      n, n_rec   → n, n_rec          n, rows → n, len(rows)       n 만 → n, None
                      rows 만    → None, len(rows)   둘 다 없음 → None, None
                  hdr_rows 로 n 을 만들지 않는다: 파서의 rows 는 합계·소계·공종 소제목이 빠진 레코드라 len+1 은
                  조작된 값이었다(dbe p8 50 vs 상류 51, khe p8 33 vs 35, kre ii4 134 vs 137). 상류 D 와 맞는 n 은
                  U2 가 parse_tables 의 원행수를 n 으로 실어 보내야 한다. 페이지(_to_js)는 n 이 None 이면 n_rec 를 내보낸다.
          reason ∈ REASONS — 아니면 HdrmapError(지도에 임의 문자열이 들어가지 않게).
          디스크에는 압축해 적는다: cols_raw 는 cols 와 다를 때만, ncols 는 norm_col(cols) 와 다를 때만 남긴다
          (load_map 이 복원하므로 읽는 쪽은 항상 전체 꼴을 본다). fields 는 '어느 사전 버전으로 읽었나'의 증거라 남긴다.
          rows 는 저장하지 않는다. 파일 5MB 가드(MAX_BYTES) — kdef 캐시 2,318표·kce 정밀+lite 2,100표가 들어가는지는
          tests.test_map_compact_and_size 가 단언한다.
  hdr_queue.json  [item…]  append-only(항목 삭제 없음) · id 순 정렬 · 시각 없음. 봇은 open 추가와
                  resolved 전환만 한다. 사람은 큐를 손으로 고치지 않고 사전·파서·테스트를 고친다 — 다음 실행이 큐를 닫는다.
      item = {id: sha1(tab|key|role|kind|mask(ncols))[:12], tab, key, stock, name, role, kind, status: open|resolved,
              grade: A|B, quarter_first, quarter_last, reopened, rcpNo, cols_raw, ncols, fields_got, need_missing,
              lead, suggest({ncol: field}|None), reason, resolved_in}
      kind ∈ unknown | changed | new_company | synth | zero_rows | no_tables | engine_error
      id 에 kind 를 넣은 것은 설계서(tab|key|role|mask ncols)와 다른 점 — 같은 머리행이 'unknown' 과 'changed' 로
      동시에 열릴 수 있고(engine_error 는 사유 앞 80자까지), 하나로 합치면 한쪽 사유가 지워진다. 같은 (kind, 머리행)
      이 다시 오면 새 항목이 아니라 quarter_last·판정만 갱신되고, resolved 였으면 open 으로 되돌아간다(reopened +1 = 회귀).
      write 의 자동 resolved 전환(종류별):
        unknown              채택된 표와 마스킹 머리행이 같은 항목 — 사전·파서가 고쳐져 읽히기 시작했다.
        zero_rows|no_tables  같은 (key, role) 에 채택 표가 생긴 분기.
        new_company          그 회사가 처음 기록·커밋된 분기.
        synth                같은 (key, role) 에서 **비합성** 머리행이 **뒤 분기**(quarter_first < q)에 채택될 때만.
        changed              **뒤 분기**에 같은(마스킹) 머리행이 다시 채택될 때만(=정착).
      synth·changed 는 '채택된 표 자체를 사람에게 보이려고' 올리는 항목이라 같은 write 에서 즉시 닫히면 사람 눈에
      닿기 전에 소멸한다(심사 지적) — 그래서 뒤 분기 조건이 붙는다. 명시 resolve_clean 은 종류를 가리지 않는다.
  col_alias_auto.json  {ncol: {"field", "provenance": {stock, quarter, rcpNo, raw}}}
      등급 A 판정만 적힌다. **COL_ALIAS 키는 절대 가리지 않는다**(record_auto_alias 가 거른다). kce_lib 은
      `merge_auto(COL_ALIAS, os.environ.get("KCE_ALIAS_AUTO"))` 한 줄로 **없는 키만** 더한다(손 사전 우선,
      env 없으면 no-op) — 6탭이 kce_lib 을 공유하므로 호출측(update-kce.yml)만 env 를 켠다.

잠금
  스테이지·큐·자동사전의 읽기-고치기-쓰기는 전부 **프로세스 내** 잠금(_LOCK, RLock) 아래서 한다 — 엔진이 붙는 자리는
  kce_fetch.parallel(ThreadPoolExecutor, KCE_LANES 8) 레인 안(kce_series·kce_probe·kce_detail·ksemi_reports)이라
  잠금 없이는 8스레드 × 25건 enqueue 가 28건만 남았다(심사 실측 — 조용한 증거 소실). 프로세스 간(같은 job 의 순차 스텝,
  별도 워크플로)은 러너의 순차 실행 규약으로 막는다 — 파일락은 없다.

대조 키 (headers.html JS L98-151 재현)
  구간 id gseq = ent|tag|'/'.join(공백 제거 cols)  — 같은 구간이 이어지면 한 구간. JS 와 같은 수가 나와야
      지도의 #번호가 상류 표 대장과 맞는다(17사 3절 132구간, DL이앤씨 II-4 8구간 실측).
  직전 분기 대조 키 = ent|tag#순번(같은 구분의 n번째 표). 열 비교는 **마스킹한 ncols** 로 한다 —
      `(2022.01.01)`·`제27기`·`2024년` → '#'. 날짜가 열 이름에 박힌 회사(KAI 95건)가 매 분기 「바뀜」으로
      뜨는 가짜 신호를 막는다. 당기/전기/전분기 는 **말·초 가 붙은 날짜성 꼴만** 접는다(당기말·전기초 → '#말'·'#초');
      단독 '당기'·'전기' 는 그대로 둔다 — '당기매출액'≠'전기매출액', 전력(kgrid) '전기판매액'≠'당기판매액'. 둘을 같은
      '#' 로 접으면 (구분|당기|전기)→(구분|전기|당기) 자리바꿈이 chg 0 이 되고 _resolve 가 '당기…' 채택으로 '전기…'
      미지를 닫는다(심사 지적; 설계 A 의 '당기|전기|전분기 → #' 는 이렇게 좁힌다). 마스킹은 비교용이고 저장값은 원문 그대로다.

A/B 등급 (classify)
  A(자동 반영) = ① 벗김(전각·가운뎃점·단위 괄호·날짜 괄호·각주·공종 접미·'금액/총액' 둘째 머리행) 뒤 COL_ALIAS
      키와 **정확 일치**, 또는 편집거리 1(길이≥4·숫자 없음·후보 유일)  ② 그 매핑으로 역할의 NEED 충족 **그리고**
      레코드 성립을 실측(rows 가 있으면 kce_parse._records, 없으면 checks.records=True 로 호출측이 확인했다는 뜻) —
      둘 다 없으면 ② 미검증이라 B(records_unverified)  ③ 수치 검증 — checks.recon 95~105% 또는 bal_sum/bal_prev ±30%
      — 셋 전부. 하나라도 빠지면 B(사람 확인): 새 의미 열·다의 열(계약금액·구분)·중복 필드·합성 머리행·후보 2개·
      수치 검증 불가. 파서의 fail-closed 는 어느 쪽이든 유지된다. kce parse_ii4 의 unknown 항목은 {cols, n} 뿐이라
      rows 를 동봉하지 않으면 그 경로는 영구 B 다(U2 TODO: unknown 항목에 rows 또는 _records 결과 bool 동봉).

API (모든 함수에 root=None — 기본은 이 파일 기준 argus/; 테스트는 임시 디렉터리를 준다)
  record(tab, key, q, role, tables, picks=(), *, rejected=(), unknown=(), meta=None, root=None, strict=False) -> [entry]
      메모리 스테이지. tables = 파서가 본 표 dict 목록(cols·ncols·fields·rows|n·lead… 와 entry 메타 키).
      picks = 채택 인덱스 집합 또는 {통화: 인덱스}(kaero 통화별 다중 채택 — cur 로 기록).
      rejected = 파서가 돌려준 비채택 후보({cols,…,reason}) → pick False. unknown = 미지 표 → pick False +
      **즉시** 큐(kind unknown; rows/checks 가 있으면 A/B 판정에 쓰고 저장하지 않는다). 스테이지를 버려도 큐는 남는다.
  write(tab, key=None, root=None, strict=False) -> {"companies","tables","quarters","resolved"}
      스테이지를 디스크 지도에 병합해 원자 쓰기, 큐의 자동 resolved 전환(위 종류별 규칙).
      key 를 주면 그 회사 몫만 쓴다(kce 는 회사 단위 fail-closed 라 다른 회사 스테이지를 끌어오면 안 된다).
  discard(tab, key=None)  실패 분기에서 스테이지 폐기(지도에 오기록이 영구화되지 않게).
  diff_prev(tab, key, role, q, root=None) -> [{"key","kind": new|chg|gone, "prev", "now"}]   (스테이지 포함)
  gseq(fq, by_q, prefix) -> {gk: "prefix-NN"}   JS 구간 번호 재현(순수 함수).
  enqueue(tab, item, root=None) -> item   kind 기본 unknown. unknown 이면 suggest 로 A/B 를 매기고 A 는 자동 사전에 적는다.
  resolve_clean(tab, key, role, q, ncols=None, root=None) -> n   ncols 가 None 이면 그 (key,role) 의 open 전부.
  load_queue(tab, root=None) / load_map(tab, root=None)
  classify(ncols, fields, need, checks=None) -> ("A", {ncol: field}) | ("B", reason) ; suggest(item) -> item
  record_auto_alias(tab, alias, provenance, root=None) -> [추가된 ncol] ; merge_auto(alias_dict, path) -> n ; load_auto_alias(path)
  render_headers(tab, out_html=None, order=None, add_company=True, labels=None, root=None, write=True, strict=False,
                 keys=None, stage=True) -> html
      kce: 기존 headers.html 의 `const D`·`ORDER` 만 교체(cfgsig·LAB·JS 불변, 멱등, 지도에 없는 회사·분기는
      바이트 불변 — 빈 지도로 돌리면 17사 262,291자 그대로). 다른 탭: 없으면 tools/assets/headers_tpl.html
      (kce JS L80-173 복제, 절 목록은 LAB 키·앞 구간 자르기는 LAB[key][2]=='trim')에서 argus/<tab>/headers.html 을
      만든다. 신규 회사는 D(sections 는 LAB 의 절 전부)와 ORDER 끝(kce 는 COMPANIES 순)에 추가.
      keys = 회사 부분집합 — D·ORDER 를 그 회사로 제한한다(lite 36사 headers_lite.html 을 같은 지도에서 따로 그린다).
      stage = 스테이지 덧씌움(_entries_at 과 같은 우선순위: 스테이지 우선) — True 전부 · False 디스크만 · 회사 키 모음.
  check(tab, critical=(), root=None) -> {"exit", "regressions", "open", "open_by_kind", "new_company_open"}
      exit 1 은 **회귀**만 — 직전 분기 clean(채택 표 있음)이던 (key,role) 이 현 분기에 채택 표 없이 open 미지로 바뀜,
      critical 회사의 수주표(orders) 채택 소실. 현 분기에 채택 표가 살아 있는 미지표(채택 + 근접 미지, 이화공영 꼴)·
      신규사 open·B 항목 증가는 경고(0). kce 정밀은 unknown 시 raise+discard 라 현 분기 항목이 없어 회귀로 잡힌다.
  onboard(tab, prev_stocks, rows, q="", root=None) -> [신규 row]   universe 저장 직전 2줄로 신규 종목을 큐에.
  replay_cache(tab, loader, root=None) -> {"records","errors"}   loader 가 내는 record 인자 dict 를 순서대로 기록·커밋.
  kce 어댑터: record_kce(co, q, headers, meta=None, root=None, strict=False) — rep['headers']{ii4,p8,xinb} →
      orders/progress/xi.  render_headers_html(path, co, quarter, headers) — kce_render 의 같은 이름 함수와
      시그니처·반환(텍스트) 동일, **기록(스테이지)+스테이지를 덧씌운 렌더만**(커밋 없음, 엄격 모드).
      commit_kce(co) — 호출측이 pending 쓰기에 성공한 뒤 부르는 커밋(= write("kce", key=co, strict=True)).
  예외: HdrmapError(RuntimeError) 와 그 하위 UnknownHeaderError — kce 정밀(fail-closed) 경로가 enqueue 뒤 raise 하고
      discard 하는 예외. U2·U4 가 같은 클래스를 쓴다.

오류 처리
  내부 예외는 삼키되 **흔적 없이는 안 된다**: stderr 한 줄 + 큐 kind engine_error(open) 를 남기고 None 을 돌려
  호출측(수집·갱신)이 계속 가게 한다. strict=True 또는 HDRMAP_STRICT=1 이면 그대로 raise(테스트·어댑터).
"""
import hashlib
import json
import os
import re
import sys
import threading
import unicodedata
from collections import Counter

from kce_lib import COL_ALIAS, COMPANIES, CORP, atomic_write, json_for_html, norm_col
from kce_parse import _SUFFIX_KIND          # 공종 접미 벗김은 파서와 한 식이어야 한다(두 벌이면 벗김 결과가 갈라진다)

HERE = os.path.dirname(os.path.abspath(__file__))
ARGUS = os.path.dirname(os.path.dirname(HERE))              # …/argus
TEMPLATE = os.path.join(HERE, "assets", "headers_tpl.html")
MAX_BYTES = 5 * 1024 * 1024                                  # AGENTS.md: 데이터 파일 5MB 이하

ROLES = ("orders", "progress", "xi", "revenue", "segsales", "customers")
KINDS = ("unknown", "changed", "new_company", "synth", "zero_rows", "no_tables", "engine_error")
REASONS = ("picked", "near_miss", "no_core", "meta_p8", "few_fields", "dup_section", "unit_unknown",
           "progress_fail")
# kce headers.html 의 절 키(상류 JS 가 이 셋을 그린다). 다른 탭은 role 이름이 곧 절 키다.
KCE_SECTIONS = {"orders": "ii4", "progress": "p8", "xi": "xinb"}
# 새 탭 지도의 절 라벨 [짧은 이름, 설명, (trim: 값이 있는 첫 분기 앞을 잘라 그린다)]
ROLE_LABELS = {
    "orders": ["수주", "수주상황표"],
    "progress": ["진행률", "진행률 적용 수주계약 현황"],
    "xi": ["XI-1", "단일판매·공급계약 진행 현황", "trim"],
    "revenue": ["매출", "매출실적"],
    "segsales": ["부문", "부문별 매출"],
    "customers": ["거래처", "주요 매출처"],
}
KCE_LAB = {"ii4": ["II-4", "수주상황(상세)"], "p8": ["III-8", "진행률적용 수주계약 현황"],
           "xinb": ["XI-1", "단일판매·공급계약 진행 현황"]}

# 역할별 필수 필드. kce_parse 의 _II4_NEED/_P8_NEED 와 같은 값을 **읽어** 쓴다(복제하면 두 곳이 갈라진다).
# XI 는 설계서 C 의 NEED(kce_xi1 지역 사전 — 전역 COL_ALIAS 에 없는 필드라 여기 값만 둔다).
# kce_xi1.NEED 와 같아야 한다 — 대금수령 열이 없는 표도 읽는다(2026-10-16 섹터 304사 실측). 순환 import 를 피해 값으로 둔다.
_XI_NEED = {"xi_nm", "xi_amt", "xi_supCum"}

_ENTRY_META = ("ent", "tag", "basis", "cur", "unit_seen", "synth", "shape", "sec_title", "rcpNo")
_Q_RE = re.compile(r"^\d{4}Q[1-4]$")
_WS = re.compile(r"\s+")
# 비교용 마스크 — 날짜 괄호 `(2022.01.01)`·`2025-06-30`, 기수 `제27기`, 연도 `2024년`,
# 당기/전기/전분기 는 날짜성 접미(말·초)가 붙은 꼴만(단독 당기·전기 는 서로 다른 열이다 — 모듈 docstring '대조 키').
_MASK = re.compile(r"\(?\d{4}[.\-/]\d{1,2}(?:[.\-/]\d{1,2})?\)?|제\d+기|\d{4}년|(?:전분기|당기|전기)(?=말|초)")


class HdrmapError(RuntimeError):
    pass


class UnknownHeaderError(HdrmapError):
    """미지 머리행 — kce 정밀(fail-closed) 경로가 `enqueue(...)` 뒤 raise 하고 `discard` 하는 예외(설계 A·G).
    U2(kce_build L808-810·L824-825)·U4 가 이 클래스를 쓴다. HdrmapError·RuntimeError 로도 잡힌다."""


def _need_of(role):
    if role == "orders":
        from kce_parse import _II4_NEED
        return set(_II4_NEED)
    if role == "progress":
        from kce_parse import _P8_NEED
        return set(_P8_NEED)
    if role == "xi":
        return set(_XI_NEED)
    return set()


def _field_of(ncol):
    from kce_parse import _field_of as f
    return f(ncol)


# ── 경로 · 정규화 JSON ───────────────────────────────────────────

def assets_dir(tab, root=None):
    return os.path.join(root or ARGUS, tab, "tools", "assets")


def map_path(tab, root=None):
    return os.path.join(assets_dir(tab, root), "hdrmap.json")


def queue_path(tab, root=None):
    return os.path.join(assets_dir(tab, root), "hdr_queue.json")


def auto_alias_path(tab, root=None):
    return os.path.join(assets_dir(tab, root), "col_alias_auto.json")


def headers_path(tab, root=None):
    return os.path.join(root or ARGUS, tab, "headers.html")


def _dumps(obj):
    """같은 데이터 → 같은 바이트. 키 정렬·indent 1·개행 고정(AGENTS.md 정규화 JSON)."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n"


def _write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    atomic_write(path, _dumps(obj))


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _compact(e):
    """디스크 꼴 — cols_raw 는 cols 와 다를 때만, ncols 는 norm_col(cols) 와 다를 때만 남긴다(복원은 _expand).
    표마다 네 목록(cols_raw·cols·ncols·fields)을 다 적으면 표당 ≈1.5KB(상류 1,302표 1.9MB) — kdef 2,318표·lite 를 같은
    가드 안에 넣기 위한 압축. 원 dict 는 건드리지 않는다(스테이지 엔트리는 쓰기 실패 시 그대로 남아야 한다)."""
    c = dict(e)
    cols = list(c.get("cols") or [])
    if c.get("cols_raw") == cols:
        c.pop("cols_raw", None)
    if c.get("ncols") == [norm_col(x) for x in cols]:
        c.pop("ncols", None)
    return c


def _expand(e):
    """_compact 의 역 — 읽는 쪽은 항상 전체 꼴(cols_raw·ncols 포함)을 본다. 제자리 갱신."""
    cols = list(e.get("cols") or [])
    if "cols_raw" not in e:
        e["cols_raw"] = list(cols)
    if "ncols" not in e:
        e["ncols"] = [norm_col(c) for c in cols]
    return e


def _compact_map(M):
    out = {k: v for k, v in M.items() if k != "companies"}
    out["companies"] = {}
    for key, co in M["companies"].items():
        c = {k: v for k, v in co.items() if k != "roles"}
        c["roles"] = {role: {q: [_compact(e) for e in entries] for q, entries in by_q.items()}
                      for role, by_q in (co.get("roles") or {}).items()}
        out["companies"][key] = c
    return out


def _save_map(tab, M, root):
    """지도를 압축해 원자 쓰기. 5MB 가드는 압축본 기준. 쓴 바이트 수를 돌려준다."""
    text = _dumps(_compact_map(M))
    nb = len(text.encode("utf-8"))
    if nb > MAX_BYTES:
        raise HdrmapError("hdrmap.json 이 %d bytes — 5MB 가드. 회사별 분할이 필요하다" % nb)
    os.makedirs(assets_dir(tab, root), exist_ok=True)
    atomic_write(map_path(tab, root), text)
    return nb


def load_map(tab, root=None):
    M = _load_json(map_path(tab, root), None)
    if not M:
        M = {"tab": tab, "companies": {}}
    M.setdefault("companies", {})
    for co in M["companies"].values():
        for by_q in (co.get("roles") or {}).values():
            for entries in by_q.values():
                for e in entries:
                    _expand(e)
    return M


def load_queue(tab, root=None):
    return _load_json(queue_path(tab, root), [])


# ── 마스킹 · 대조 키 ─────────────────────────────────────────────

def mask(s):
    """비교용 정규화: 공백 제거 뒤 날짜·기수·연도 토큰과 당기말/전기초 꼴을 '#'로. 단독 당기/전기 는 그대로."""
    return _MASK.sub("#", _WS.sub("", s or ""))


def mask_cols(cols):
    return [mask(c) for c in (cols or []) if c and str(c).strip()]


def _cmp_cols(e):
    """엔트리의 비교용 열 목록 — ncols 가 있으면 그것(정규화본), 없으면 cols."""
    return mask_cols(e.get("ncols") or e.get("cols") or [])


def gseq(fq, by_q, prefix):
    """구간 번호 — headers.html JS L98-104 재현. by_q = {분기: [entry|D 항목]}.
    키 = ent|tag|'/'.join(빈칸 뺀 cols 의 공백 제거본). 같은 키가 처음 나온 순서로 NN 을 매긴다."""
    out = {}
    for q in fq:
        for r in (by_q.get(q) or []):
            gk = ((r.get("ent") or "") + "|" + (r.get("tag") or "") + "|"
                  + "/".join(_WS.sub("", c) for c in (r.get("cols") or []) if c and c.strip()))
            if gk not in out:
                out[gk] = "%s-%02d" % (prefix, len(out) + 1)
    return out


def _nth_keys(entries):
    """직전 분기 대조 키 ent|tag#순번 — JS L121-125 와 같은 규칙."""
    nth = Counter()
    keys = []
    for e in entries:
        kk = (e.get("ent") or "") + "|" + (e.get("tag") or "")
        nth[kk] += 1
        keys.append("%s#%d" % (kk, nth[kk]))
    return keys


# ── 엔트리 ───────────────────────────────────────────────────────

def _entry(t, pick, reason, meta):
    if not isinstance(t, dict):
        raise HdrmapError("표는 dict 여야 한다: %r" % (type(t).__name__,))
    if reason not in REASONS:
        raise HdrmapError("알 수 없는 reason: %r (허용 %s)" % (reason, "|".join(REASONS)))
    cols = [str(c) for c in (t.get("cols") or [])]
    cols_raw = [str(c) for c in t["cols_raw"]] if t.get("cols_raw") is not None else list(cols)
    ncols = list(t["ncols"]) if t.get("ncols") is not None else [norm_col(c) for c in cols]
    fields = list(t["fields"]) if t.get("fields") is not None else [_field_of(c) for c in ncols]
    rows = t.get("rows")
    # n·n_rec 은 추정하지 않는다 — 모듈 docstring 의 입력 조합표. hdr_rows 는 읽지 않는다.
    n = int(t["n"]) if t.get("n") is not None else None
    if t.get("n_rec") is not None:
        n_rec = int(t["n_rec"])
    elif rows is not None:
        n_rec = len(rows)
    else:
        n_rec = None
    e = {"cols_raw": cols_raw, "cols": cols, "ncols": ncols, "fields": fields,
         "n": n, "n_rec": n_rec, "lead": (t.get("lead") or "")[-120:]}
    meta = meta or {}
    for k in _ENTRY_META:
        v = t.get(k, meta.get(k))
        if k in ("ent", "tag"):
            v = v or ""
        e[k] = v
    e["pick"] = bool(pick)
    e["reason"] = reason
    return e


def _picks(picks):
    """채택 인덱스 집합과 {인덱스: 통화}. kaero 는 통화별로 표를 하나씩 채택한다({'KRW': 0, 'USD': 1})."""
    if isinstance(picks, dict):
        return {int(v) for v in picks.values() if v is not None}, {int(v): k for k, v in picks.items() if v is not None}
    return {int(i) for i in (picks or ())}, {}


# ── 스테이지 · 커밋 ──────────────────────────────────────────────

_STAGE = {}
_LOCK = threading.RLock()        # 프로세스 내 잠금 — 스테이지·큐·자동사전 전부(모듈 docstring '잠금')


def _guard(tab, where, strict, root, fn, *args):
    """내부 예외 → stderr 한 줄 + 큐 engine_error(open). strict 면 그대로 raise."""
    try:
        return fn(*args)
    except Exception as e:
        if strict or os.environ.get("HDRMAP_STRICT"):
            raise
        msg = "%s: %s" % (type(e).__name__, e)
        sys.stderr.write("hdrmap %s %s(%s): %s\n" % (tab, where.get("fn"), where.get("key") or "-", msg))
        try:
            _enqueue(tab, {"kind": "engine_error", "key": where.get("key") or "", "role": where.get("role") or "*",
                           "quarter": where.get("q") or "", "reason": "%s %s" % (where.get("fn"), msg[:300]),
                           "name": where.get("name"), "stock": where.get("stock")}, root)
        except Exception as e2:                      # 큐까지 못 쓰면 stderr 가 마지막 흔적이다
            sys.stderr.write("hdrmap %s engine_error 큐 기록 실패: %s\n" % (tab, e2))
        return None


def _default_meta(tab, key, meta):
    meta = dict(meta or {})
    if tab == "kce" and key in CORP:
        meta.setdefault("name", CORP[key]["name"])
        meta.setdefault("stock", CORP[key]["stock"])
    return meta


def _record(tab, key, q, role, tables, picks, rejected, unknown, meta, root):
    if role not in ROLES:
        raise HdrmapError("알 수 없는 표 역할: %r (허용 %s)" % (role, "|".join(ROLES)))
    if not _Q_RE.match(q or ""):
        raise HdrmapError("분기 형식 오류: %r" % (q,))
    if not key:
        raise HdrmapError("key 가 비었다")
    meta = _default_meta(tab, key, meta)
    pick_idx, pick_cur = _picks(picks)
    entries = []
    for i, t in enumerate(tables or []):
        pk = i in pick_idx
        e = _entry(t, pk, "picked" if pk else (t.get("reason") or "no_core"), meta)
        if pk and pick_cur.get(i) and not e.get("cur"):
            e["cur"] = pick_cur[i]
        entries.append(e)
    for r in rejected or ():
        entries.append(_entry(r, False, r.get("reason") or "near_miss", meta))
    for u in unknown or ():
        e = _entry(u, False, u.get("reason") or "near_miss", meta)
        entries.append(e)
        # 스테이지가 버려져도 증거는 남아야 한다 — 큐는 즉시 쓴다(원자적·append-only·잠금 아래).
        _enqueue(tab, {"kind": "unknown", "key": key, "role": role, "quarter": q,
                       "cols_raw": e["cols_raw"], "ncols": e["ncols"], "fields": e["fields"], "n": e["n"],
                       "lead": e["lead"], "rcpNo": e["rcpNo"], "name": meta.get("name"),
                       "stock": meta.get("stock"), "need": u.get("need"),
                       "rows": u.get("rows"), "checks": u.get("checks") or meta.get("checks"),
                       "synth": u.get("synth", meta.get("synth"))}, root)
    with _LOCK:
        co = _STAGE.setdefault(tab, {}).setdefault(key, {"name": None, "stock": None, "roles": {}})
        if meta.get("name"):
            co["name"] = meta["name"]
        if meta.get("stock"):
            co["stock"] = meta["stock"]
        co["roles"].setdefault(role, {})[q] = entries
    return entries


def record(tab, key, q, role, tables, picks=(), *, rejected=(), unknown=(), meta=None, root=None, strict=False):
    where = {"fn": "record", "key": key, "role": role, "q": q,
             "name": (meta or {}).get("name"), "stock": (meta or {}).get("stock")}
    return _guard(tab, where, strict, root, _record, tab, key, q, role, tables, picks, rejected, unknown, meta, root)


stage = record          # 설계서 A 의 이름


def discard(tab, key=None):
    with _LOCK:
        if key is None:
            _STAGE.pop(tab, None)
        elif tab in _STAGE:
            _STAGE[tab].pop(key, None)


def staged(tab, key=None):
    """스테이지 조회(읽기 전용 복사)."""
    with _LOCK:
        s = _STAGE.get(tab) or {}
        return json.loads(json.dumps(s if key is None else s.get(key)))


def _merge_stage(M, st):
    """스테이지(회사 → roles)를 지도 dict 에 덧씌운다(같은 분기 재적재 = 교체, 스테이지 우선). (표 수, 분기 수)."""
    ntab = nq = 0
    for k, co in sorted(st.items()):
        c = M["companies"].setdefault(k, {"name": co["name"], "stock": co["stock"], "fq": [], "roles": {}})
        if co["name"]:
            c["name"] = co["name"]
        if co["stock"]:
            c["stock"] = co["stock"]
        for role, by_q in co["roles"].items():
            for q, entries in by_q.items():
                c["roles"].setdefault(role, {})[q] = [dict(e) for e in entries]
                if q not in c["fq"]:
                    c["fq"].append(q)
                ntab += len(entries)
                nq += 1
        c["fq"].sort()
    return ntab, nq


def _write(tab, key, root):
    with _LOCK:
        # 스테이지는 **쓰기가 끝난 뒤** 비운다 — 5MB 가드·디스크 오류로 실패하면 호출측이 고쳐서
        # 다시 write 하거나 discard 로 버릴 수 있어야 한다(먼저 pop 하면 실패 시 기록이 증발한다).
        if key is None:
            st = dict(_STAGE.get(tab) or {})
        else:
            st = {key: _STAGE[tab][key]} if key in _STAGE.get(tab, {}) else {}
        if not st:
            return {"companies": 0, "tables": 0, "quarters": 0, "resolved": 0}
        M = load_map(tab, root)
        ntab, nq = _merge_stage(M, st)
        _save_map(tab, M, root)
        for k in st:                                     # 디스크에 올라갔으니 이제 스테이지를 비운다
            _STAGE.get(tab, {}).pop(k, None)
        if tab in _STAGE and not _STAGE[tab]:
            del _STAGE[tab]
        # 큐 전환 — 종류별 규칙은 모듈 docstring. synth·changed 는 뒤 분기 조건(before=q) 이 붙는다.
        resolved = 0
        for k, co in st.items():
            qs = sorted({q for by_q in co["roles"].values() for q in by_q})
            for role, by_q in co["roles"].items():
                for q, entries in by_q.items():
                    picked = [e for e in entries if e["pick"]]
                    for e in picked:
                        resolved += _resolve(tab, k, role, q, e["ncols"], root, ("unknown",))
                        resolved += _resolve(tab, k, role, q, e["ncols"], root, ("changed",), before=q)
                    if picked:
                        resolved += _resolve(tab, k, role, q, None, root, ("zero_rows", "no_tables"))
                    if any(not e.get("synth") for e in picked):
                        resolved += _resolve(tab, k, role, q, None, root, ("synth",), before=q)
            if qs:
                resolved += _resolve(tab, k, "*", qs[-1], None, root, ("new_company",))
        return {"companies": len(st), "tables": ntab, "quarters": nq, "resolved": resolved}


def write(tab, key=None, root=None, strict=False):
    return _guard(tab, {"fn": "write", "key": key}, strict, root, _write, tab, key, root)


commit = write          # 설계서 A 의 이름


def _entries_at(tab, key, role, q, root):
    """디스크 지도 + 스테이지(스테이지 우선)의 (key, role, q) 엔트리. 없으면 None(기록 안 됨)."""
    with _LOCK:
        s = _STAGE.get(tab, {}).get(key)
        if s and q in s["roles"].get(role, {}):
            return s["roles"][role][q]
    co = load_map(tab, root)["companies"].get(key)
    if not co:
        return None
    return (co["roles"].get(role) or {}).get(q)


def _quarters_of(tab, key, role, root):
    qs = set()
    co = load_map(tab, root)["companies"].get(key)
    if co:
        qs |= set((co["roles"].get(role) or {}).keys())
    with _LOCK:
        s = _STAGE.get(tab, {}).get(key)
        if s:
            qs |= set(s["roles"].get(role, {}).keys())
    return sorted(qs)


def _diff(prev, now):
    """두 분기 엔트리 목록을 ent|tag#순번 으로 짝지어 마스킹 열 비교."""
    pk = dict(zip(_nth_keys(prev), prev))
    nk = dict(zip(_nth_keys(now), now))
    out = []
    for k in list(nk) + [k for k in pk if k not in nk]:
        p, n = pk.get(k), nk.get(k)
        if p is None:
            out.append({"key": k, "kind": "new", "prev": None, "now": n["cols"]})
        elif n is None:
            out.append({"key": k, "kind": "gone", "prev": p["cols"], "now": None})
        elif _cmp_cols(p) != _cmp_cols(n):
            out.append({"key": k, "kind": "chg", "prev": p["cols"], "now": n["cols"]})
    return out


def _diff_prev(tab, key, role, q, root):
    now = _entries_at(tab, key, role, q, root)
    if now is None:
        raise HdrmapError("기록되지 않은 분기: %s %s %s" % (key, role, q))
    before = [x for x in _quarters_of(tab, key, role, root) if x < q]
    prev = None
    for pq in reversed(before):                    # 직전 '기록된' 분기 — 표가 비어 있던 분기는 건너뛴다
        cand = _entries_at(tab, key, role, pq, root)
        if cand:
            prev = cand
            break
    if prev is None:
        return []
    return _diff(prev, now)


def diff_prev(tab, key, role, q, root=None, strict=False):
    return _guard(tab, {"fn": "diff_prev", "key": key, "role": role, "q": q}, strict, root,
                  _diff_prev, tab, key, role, q, root)


# ── 큐 ───────────────────────────────────────────────────────────

def _qid(tab, key, role, kind, ncols, extra=""):
    base = "|".join([tab, key or "", role or "", kind, "/".join(mask_cols(ncols)), extra])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


def _save_queue(tab, items, root):
    items.sort(key=lambda x: x["id"])
    _write_json(queue_path(tab, root), items)


def _enqueue(tab, item, root):
    kind = item.get("kind") or "unknown"
    if kind not in KINDS:
        raise HdrmapError("알 수 없는 큐 종류: %r" % (kind,))
    key = item.get("key") or item.get("stock") or ""
    role = item.get("role") or ("*" if kind in ("new_company", "engine_error") else "orders")
    q = item.get("quarter") or item.get("quarter_first") or ""
    cols_raw = [str(c) for c in (item.get("cols_raw") or item.get("cols") or [])]
    ncols = list(item["ncols"]) if item.get("ncols") is not None else [norm_col(c) for c in cols_raw]
    extra = ""
    if kind == "engine_error":
        extra = (item.get("reason") or "")[:80]           # 같은 자리·같은 오류는 하나로
    sid = _qid(tab, key, role, kind, ncols, extra)
    sug = suggest({"role": role, "ncols": ncols, "cols_raw": cols_raw, "fields": item.get("fields"),
                   "need": item.get("need"), "rows": item.get("rows"), "checks": item.get("checks"),
                   "synth": item.get("synth"), "kind": kind, "reason": item.get("reason")})
    with _LOCK:                                           # 읽기-고치기-쓰기 한 묶음 — 레인 8개가 동시에 올려도 증발 0
        items = load_queue(tab, root)
        for it in items:
            if it["id"] == sid:
                if q and (not it.get("quarter_last") or q > it["quarter_last"]):
                    it["quarter_last"] = q
                if it["status"] == "resolved" and q and (not it.get("resolved_in") or q > it["resolved_in"]):
                    it["status"], it["resolved_in"] = "open", None      # 닫혔던 문제가 재발 → 회귀
                    it["reopened"] = int(it.get("reopened") or 0) + 1
                for k in ("grade", "suggest", "reason", "fields_got", "need_missing"):
                    it[k] = sug[k]
                if item.get("rcpNo") and not it.get("rcpNo"):
                    it["rcpNo"] = item["rcpNo"]
                _save_queue(tab, items, root)
                if sug["grade"] == "A" and sug["suggest"] and kind == "unknown":
                    record_auto_alias(tab, sug["suggest"], _prov(item, q, cols_raw, ncols), root)
                return it
        it = {"id": sid, "tab": tab, "key": key, "stock": item.get("stock"), "name": item.get("name"),
              "role": role, "kind": kind, "status": "open", "grade": sug["grade"],
              "quarter_first": q, "quarter_last": q, "reopened": 0, "rcpNo": item.get("rcpNo"),
              "cols_raw": cols_raw, "ncols": ncols, "fields_got": sug["fields_got"], "need_missing": sug["need_missing"],
              "lead": (item.get("lead") or "")[-120:], "suggest": sug["suggest"], "reason": sug["reason"],
              "resolved_in": None}
        items.append(it)
        _save_queue(tab, items, root)
        if sug["grade"] == "A" and sug["suggest"] and kind == "unknown":
            record_auto_alias(tab, sug["suggest"], _prov(item, q, cols_raw, ncols), root)
        return it


def _prov(item, q, cols_raw, ncols):
    raw = {}
    for c, n in zip(cols_raw, ncols):
        raw.setdefault(n, c)
    return {"stock": item.get("stock"), "quarter": q, "rcpNo": item.get("rcpNo"), "raw": raw}


def enqueue(tab, item, root=None, strict=True):
    """큐에 open 항목을 더한다(같은 id 는 quarter_last·판정만 갱신). 기본 strict — 큐는 증거라 못 쓰면 알려야 한다."""
    return _guard(tab, {"fn": "enqueue", "key": (item or {}).get("key"), "role": (item or {}).get("role")},
                  strict, root, _enqueue, tab, dict(item or {}), root)


def _resolve(tab, key, role, q, ncols, root, kinds=None, before=None):
    """open → resolved(resolved_in=q). ncols 가 있으면 마스킹 머리행이 같은 항목만, kinds 가 있으면 그 종류만,
    before 가 있으면 quarter_first < before 인(=앞 분기에 열린) 항목만."""
    with _LOCK:
        items = load_queue(tab, root)
        want = mask_cols(ncols) if ncols is not None else None
        n = 0
        for it in items:
            if it["status"] != "open" or it["tab"] != tab or it["key"] != key:
                continue
            if role is not None and it["role"] != role:
                continue
            if kinds is not None and it["kind"] not in kinds:
                continue
            if want is not None and mask_cols(it.get("ncols")) != want:
                continue
            if before is not None and not ((it.get("quarter_first") or "") < before):
                continue
            it["status"], it["resolved_in"] = "resolved", q
            n += 1
        if n:
            _save_queue(tab, items, root)
        return n


def resolve_clean(tab, key, role, q, ncols=None, root=None, strict=False):
    """(key, role) 의 open 항목을 resolved 로 — 종류를 가리지 않는 명시 전환. ncols 를 주면 마스킹 머리행이 같은 항목만."""
    return _guard(tab, {"fn": "resolve_clean", "key": key, "role": role, "q": q}, strict, root,
                  _resolve, tab, key, role, q, ncols, root, None)


def open_items(tab, root=None, kind=None):
    return [i for i in load_queue(tab, root) if i["status"] == "open" and (kind is None or i["kind"] == kind)]


# ── A/B 판정 ─────────────────────────────────────────────────────

# 다의 열 — **사전에 있지만** 문맥에 따라 다른 필드로 가는 키. 벗긴 결과가 여기 닿으면 자동 반영 금지
# (금호 III-8 '계약금액'→xi_amt 선점 사례, '구분'은 분류열/공사명 양쪽). 사전에 없는 '비고·합계' 같은 열은
# 뜻이 없는 열이지 다의 열이 아니다 — 그냥 지나가야 한다(이화공영 매출처 표의 '비고'가 B 사유를 가로채면
# 진짜 사유 need_missing 이 안 보인다).
AMBIGUOUS = {"계약금액", "구분"}
_UNIT_PAREN = re.compile(r"[(（]\s*(?:단위\s*[:：]\s*)?(?:십억원|백만원|천원|억원|만원|원|천USD|USD|\$|%)\s*[)）]")
_DATE_PAREN = re.compile(r"[(（]?\s*(?:기준일\s*[:：]?\s*)?\d{4}\s*[.\-/년]\s*\d{1,2}\s*(?:[.\-/월]\s*\d{1,2}\s*일?)?\s*[)）]?")
_FOOT = re.compile(r"[※*＊]+\d*|[(（]\s*주\s*\d*\s*[)）]")
_STRIP_SUB = ("금액", "총액")        # 둘째 머리행 어휘 중 벗겨도 뜻이 같은 것. '수량·중량'은 **금액이 아니라** 안 벗긴다.


def _variants(ncol):
    """벗김 단계를 하나씩 쌓은 후보열. 앞 단계에서 사전에 맞으면 거기서 멈춘다(과벗김 방지)."""
    out = []

    def add(x):
        x = _WS.sub("", x or "")
        if x and x not in out:
            out.append(x)

    add(ncol)
    x = unicodedata.normalize("NFKC", ncol or "").replace("ㆍ", "").replace("·", "").replace("/", "")
    add(x)
    x = _UNIT_PAREN.sub("", x)
    add(x)
    x = _DATE_PAREN.sub("", x)
    add(x)
    x = _FOOT.sub("", x)
    add(x)
    m = _SUFFIX_KIND.match(x)
    if m:
        x = m.group(1)
        add(x)
    for suf in _STRIP_SUB:
        if x.endswith(suf) and len(x) > len(suf):
            add(x[:-len(suf)])
    return out


def _lev1(a, b):
    """편집거리 1(치환·삽입·삭제 하나)인가. 같은 문자열은 False(정확 일치는 앞 단계에서 끝난다)."""
    if a == b:
        return False
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    if la > lb:
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def _alias_for(ncol):
    """① 벗김 → COL_ALIAS 정확 일치 ② 편집거리 1(길이≥4·숫자 없음·후보 유일). (키, 방법) 또는 (None, 사유)."""
    vs = _variants(ncol)
    for v in vs:
        if v in COL_ALIAS:
            if v in AMBIGUOUS:
                return None, "ambiguous:%s" % v
            return v, "strip"
    for v in vs:
        if len(v) < 4 or re.search(r"\d", v):
            continue
        cands = sorted(k for k in COL_ALIAS if len(k) >= 4 and _lev1(v, k))
        if len(cands) == 1:
            if cands[0] in AMBIGUOUS:
                return None, "ambiguous:%s" % cands[0]
            return cands[0], "edit1"
        if len(cands) > 1:
            return None, "edit1_multi:%s" % "/".join(cands)
    return None, "no_alias"


def classify(ncols, fields, need, checks=None):
    """('A', {ncol: field}) | ('B', reason). 설계서 A 의 세 조건을 전부 통과해야 A.

    checks: synth(합성 머리행) · rows(+cols/lead/spans — kce_parse._records 로 ② 실측) · records(bool — 호출측이
            ② 를 이미 확인했으면 True) · recon(합계행 대조율) · bal_sum/bal_prev(직전 분기 잔고합).
            rows 도 records 도 없으면 ② 미검증 → B(records_unverified). recon 도 bal 도 없으면 B(no_numeric_check).
    """
    checks = dict(checks or {})
    ncols = [str(c) for c in (ncols or [])]
    need = set(need or ())
    if fields is None:
        fields = [_field_of(c) for c in ncols]
    fields = (list(fields) + [None] * len(ncols))[:len(ncols)]
    if checks.get("synth"):
        return "B", "synth_header"
    if not need:
        return "B", "no_need"
    got = {f for f in fields if f}
    alias, new_fields = {}, list(fields)
    for i, (c, f) in enumerate(zip(ncols, fields)):
        if f or not c:
            continue
        k, how = _alias_for(c)
        if k is None:
            if how.startswith("ambiguous") or how.startswith("edit1_multi"):
                return "B", how
            continue                                   # 뜻 모를 열은 그냥 남는다(비고 등) — NEED 가 판단한다
        fld = COL_ALIAS[k]
        if fld in got or fld in alias.values():
            return "B", "dup_field:%s" % fld           # 한 필드에 두 열 — 사람이 봐야 한다
        alias[c] = fld
        new_fields[i] = fld
    missing = sorted(need - {f for f in new_fields if f})
    if missing:
        return "B", "need_missing:%s" % ",".join(missing)
    # ② 레코드 성립 — 매핑이 맞아 보여도 레코드가 0 이면(전부 합계행 등) 자동 반영 금지. 실측할 수 없으면 B.
    if checks.get("rows") is not None:
        from kce_parse import _records
        t = {"ncols": ncols, "fields": new_fields, "cols": list(checks.get("cols") or ncols),
             "rows": checks["rows"], "lead": checks.get("lead") or "", "spans": checks.get("spans") or []}
        if not _records(t, need):
            return "B", "records_none"
    elif checks.get("records") is True:
        pass
    elif checks.get("records") is False:
        return "B", "records_none"
    else:
        return "B", "records_unverified"
    recon = checks.get("recon")
    if recon is not None:
        if not (0.95 <= float(recon) <= 1.05):
            return "B", "recon:%.3f" % float(recon)
    else:
        bs, bp = checks.get("bal_sum"), checks.get("bal_prev")
        if bs is None or not bp:
            return "B", "no_numeric_check"
        ratio = float(bs) / float(bp)
        if not (0.7 <= ratio <= 1.3):
            return "B", "bal_ratio:%.2f" % ratio
    return "A", alias


def suggest(item):
    """큐 항목에 grade/suggest/reason/fields_got/need_missing 을 채운다(원 dict 를 갱신해 돌려준다)."""
    role = item.get("role") or "orders"
    ncols = [str(c) for c in (item.get("ncols") or [])]
    fields = item.get("fields")
    if fields is None:
        fields = [_field_of(c) for c in ncols]
    fields = (list(fields) + [None] * len(ncols))[:len(ncols)]
    need = set(item.get("need") or _need_of(role))
    got = sorted({f for f in fields if f})
    item["fields_got"] = got
    item["need_missing"] = sorted(need - set(got))
    kind = item.get("kind") or "unknown"
    if kind != "unknown":
        item["grade"], item["suggest"] = "B", None
        item["reason"] = item.get("reason") or kind
        return item
    checks = dict(item.get("checks") or {})
    if item.get("rows") is not None:
        checks.setdefault("rows", item["rows"])
        checks.setdefault("cols", item.get("cols_raw"))
        checks.setdefault("lead", item.get("lead"))
    if item.get("synth"):
        checks["synth"] = item["synth"]
    grade, res = classify(ncols, fields, need, checks)
    item["grade"] = grade
    item["suggest"] = res if grade == "A" else None
    item["reason"] = res if grade == "B" else ("auto_alias" if res else "clean")
    return item


# ── 자동 사전 ────────────────────────────────────────────────────

def load_auto_alias(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def record_auto_alias(tab, alias, provenance, root=None):
    """등급 A 별칭을 col_alias_auto.json 에. COL_ALIAS 키·이미 적힌 키는 건너뛴다(손 사전 우선·첫 출처 보존)."""
    with _LOCK:
        path = auto_alias_path(tab, root)
        cur = load_auto_alias(path)
        prov = provenance or {}
        added = []
        for ncol, field in sorted((alias or {}).items()):
            if not ncol or not field or ncol in COL_ALIAS or ncol in cur:
                continue
            cur[ncol] = {"field": field,
                         "provenance": {"stock": prov.get("stock"), "quarter": prov.get("quarter"),
                                        "rcpNo": prov.get("rcpNo"),
                                        "raw": (prov.get("raw") or {}).get(ncol) if isinstance(prov.get("raw"), dict)
                                        else prov.get("raw")}}
            added.append(ncol)
        if added:
            _write_json(path, cur)
        return added


def merge_auto(alias, path):
    """자동 사전을 alias(dict) 에 **없는 키만** 더한다 — 손 사전 우선. path 가 없거나 파일이 없으면 no-op(0)."""
    n = 0
    for ncol, v in load_auto_alias(path).items():
        if ncol in alias:
            continue
        field = v.get("field") if isinstance(v, dict) else v
        if field:
            alias[ncol] = field
            n += 1
    return n


# ── 렌더(headers.html) ───────────────────────────────────────────

_D_RE = re.compile(r"(const D\s*=\s*)")
_LAB_RE = re.compile(r",\s*LAB\s*=\s*")
_ORDER_RE = re.compile(r",\s*ORDER\s*=\s*")


def _blob_end(html, start):
    """start 에서 열린 JSON 블롭([ 또는 {)의 끝 위치(배타). kce_render._blob_end 와 같은 구현 —
    kce_render.render_headers_html 은 U2 가 이 모듈로 갈아 끼울 대상이라 import 하지 않고 여기 둔다."""
    depth, i, instr, esc, q = 0, start, False, False, ""
    while i < len(html):
        ch = html[i]
        if instr:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == q:
                instr = False
        else:
            if ch in "\"'":
                instr, q = True, ch
            elif ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
                if depth == 0:
                    return i + 1
        i += 1
    raise ValueError("괄호 불균형")


def _parse_page(h):
    """`const D=…, LAB=…, ORDER=[…];` 세 상수의 위치와 값. 반환 (D, LAB, ORDER, D 시작, ';' 위치)."""
    m = _D_RE.search(h)
    if not m:
        raise HdrmapError("headers.html 의 const D 를 찾지 못함")
    s = m.end()
    e = _blob_end(h, s)
    D = json.loads(h[s:e])
    m2 = _LAB_RE.match(h, e)
    if not m2:
        raise HdrmapError("const D 뒤에 LAB= 가 없다")
    s2 = m2.end()
    e2 = _blob_end(h, s2)
    LAB = json.loads(h[s2:e2])
    m3 = _ORDER_RE.match(h, e2)
    if not m3:
        raise HdrmapError("LAB 뒤에 ORDER= 가 없다")
    s3 = m3.end()
    e3 = _blob_end(h, s3)
    ORDER = json.loads(h[s3:e3])
    if h[e3:e3 + 1] != ";":
        raise HdrmapError("ORDER 뒤에 ';' 가 없다")
    return D, LAB, ORDER, s, e3


def section_of(tab, role):
    return KCE_SECTIONS.get(role, role) if tab == "kce" else role


def _to_js(e, with_ent):
    """엔트리 → headers.html D 항목. 키 순서까지 상류와 같게(tag, ent, cols, n, lead, pick).
    n 이 None(호출측이 원행수를 안 줌)이면 n_rec(레코드 수)를 내보낸다 — 페이지 '행' 열은 그 경우 레코드 수다."""
    it = {"tag": e.get("tag") or e.get("basis") or ""}
    if with_ent:
        it["ent"] = e.get("ent") or ""
    it["cols"] = list(e.get("cols") or [])
    it["n"] = e.get("n") if e.get("n") is not None else e.get("n_rec")
    it["lead"] = e.get("lead") or ""
    it["pick"] = bool(e.get("pick"))
    return it


def _new_page(tab, labels):
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    title = (labels or {}).get("title") or "%s 파서헤드 지도" % tab
    return tpl.replace("__TITLE__", title)


def _render(tab, out_html, order, add_company, labels, root, do_write, keys, stage):
    out_html = out_html or headers_path(tab, root)
    if os.path.exists(out_html):
        with open(out_html, encoding="utf-8") as f:
            h = f.read()
    else:
        h = _new_page(tab, labels)
    D, LAB, ORDER, s, e3 = _parse_page(h)
    if not LAB and tab == "kce":
        LAB = dict(KCE_LAB)
    M = load_map(tab, root)
    # 스테이지 덧씌움 — _entries_at 과 같은 우선순위(스테이지 우선). 어댑터는 자기 회사만({co}) 덧씌운다.
    st = staged(tab) if stage else {}
    if stage is not True and stage:
        want = set(stage)
        st = {k: v for k, v in st.items() if k in want}
    _merge_stage(M, st)
    keys = set(keys) if keys is not None else None
    if keys is not None:
        for k in [k for k in D if k not in keys]:          # 페이지에 있던 다른 회사도 뺀다(부분집합 페이지)
            del D[k]
    skipped = []
    for key in sorted(M["companies"]):
        if keys is not None and key not in keys:
            continue
        co = M["companies"][key]
        if key not in D:
            if not add_company:
                skipped.append(key)
                continue
            D[key] = {"name": co.get("name") or key, "cfgsig": "", "fq": [],
                      "sections": {sec: {} for sec in LAB}}
        d = D[key]
        d.setdefault("sections", {})
        for role, by_q in sorted(co["roles"].items()):
            sec = section_of(tab, role)
            if sec not in LAB:
                LAB[sec] = list(((labels or {}).get(role)) or ROLE_LABELS.get(role) or [role, role])
            S = d["sections"].setdefault(sec, {})
            for q, entries in by_q.items():
                S[q] = [_to_js(e, role == "orders") for e in entries]
                if q not in d["fq"]:
                    d["fq"].append(q)
            d["fq"].sort()
    if skipped:
        sys.stderr.write("hdrmap render %s: 지도에만 있는 회사 %s (add_company=False)\n" % (tab, ",".join(skipped)))
    if order is not None:
        new_order = [k for k in order if k in D]
    else:
        new_order = [k for k in ORDER if k in D]
        rest = [k for k in D if k not in new_order]
        if tab == "kce":
            rest.sort(key=lambda k: (COMPANIES.index(k) if k in COMPANIES else len(COMPANIES), k))
        else:
            rest.sort()
        new_order += rest
    text = (h[:s] + json_for_html(D) + ", LAB=" + json.dumps(LAB, ensure_ascii=False)
            + ", ORDER=" + json.dumps(new_order, ensure_ascii=False) + h[e3:])
    _parse_page(text)                                   # round-trip 검증(fail-closed)
    if do_write:
        cur = None
        if os.path.exists(out_html):
            with open(out_html, encoding="utf-8") as f:
                cur = f.read()
        if cur != text:                                 # 같으면 건드리지 않는다(멱등·mtime 보존)
            os.makedirs(os.path.dirname(os.path.abspath(out_html)), exist_ok=True)
            atomic_write(out_html, text)
    return text


def render_headers(tab, out_html=None, order=None, add_company=True, labels=None, root=None, write=True,
                   strict=False, keys=None, stage=True):
    return _guard(tab, {"fn": "render_headers"}, strict, root, _render, tab, out_html, order, add_company,
                  labels, root, write, keys, stage)


render_map = render_headers      # 설계서 A 의 이름


# ── 회귀 검사 · 온보딩 · 재생 ────────────────────────────────────

def _prev_pick_quarter(co, role, q):
    """q 바로 앞에 **기록된** 분기에 채택 표가 있었으면 그 분기, 아니면 None."""
    by_q = co.get("roles", {}).get(role) or {}
    before = sorted(x for x in by_q if x < q)
    if not before:
        return None
    pq = before[-1]
    return pq if any(e.get("pick") for e in by_q.get(pq) or []) else None


def check(tab, critical=(), root=None):
    """회귀만 exit 1. 신규사 open·B 항목 증가·바뀐 열·채택 표가 살아 있는 분기의 미지표는 경고(보고에만)."""
    M = load_map(tab, root)
    opens = open_items(tab, root)
    regs = []
    for it in opens:
        if it["kind"] not in ("unknown", "zero_rows", "no_tables"):
            continue
        co = M["companies"].get(it["key"])
        if not co:
            continue
        ql = it.get("quarter_last") or ""
        cur = (co.get("roles", {}).get(it["role"]) or {}).get(ql)
        if cur is not None and any(e.get("pick") for e in cur):
            continue        # 현 분기에 채택 표가 살아 있다 — 미지표는 곁가지(이화공영 꼴). 경고로만 집계된다.
        pq = _prev_pick_quarter(co, it["role"], ql)
        if pq:
            regs.append({"key": it["key"], "role": it["role"], "quarter": it["quarter_last"], "prev_clean": pq,
                         "kind": it["kind"], "id": it["id"]})
    for key in critical or ():
        co = M["companies"].get(key)
        if not co or not co.get("fq"):
            continue
        last = co["fq"][-1]
        by_q = co["roles"].get("orders") or {}
        if last not in by_q or any(e.get("pick") for e in by_q[last]):
            continue
        pq = _prev_pick_quarter(co, "orders", last)
        if pq:
            regs.append({"key": key, "role": "orders", "quarter": last, "prev_clean": pq,
                         "kind": "lost_pick", "id": None})
    by_kind = Counter(i["kind"] for i in opens)
    return {"exit": 1 if regs else 0, "regressions": regs, "open": len(opens),
            "open_by_kind": dict(sorted(by_kind.items())), "new_company_open": by_kind.get("new_company", 0)}


def _onboard(tab, prev_stocks, rows, q, root):
    prev = set(prev_stocks or ())
    new = []
    for r in rows or []:
        st = r.get("stock")
        if not st or st in prev:
            continue
        key = r.get("key") or r.get("slug") or st
        _enqueue(tab, {"kind": "new_company", "key": key, "stock": st, "name": r.get("name"),
                       "role": "*", "quarter": q or ""}, root)
        new.append(r)
    return new


def onboard(tab, prev_stocks, rows, q="", root=None, strict=False):
    """모집단 저장 직전: 직전 universe 에 없던 종목을 큐(new_company)에. 멱등."""
    return _guard(tab, {"fn": "onboard"}, strict, root, _onboard, tab, prev_stocks, rows, q, root)


def replay_cache(tab, loader, root=None):
    """loader → record 인자 dict({key,q,role,tables,picks,rejected?,unknown?,meta?}) 순서대로 기록·커밋.
    항목 하나가 깨져도 멈추지 않는다(engine_error 큐). 캐시만 읽으므로 DART 요청 0."""
    n = errs = 0
    for it in loader:
        try:
            _record(tab, it["key"], it["q"], it["role"], it.get("tables") or [], it.get("picks") or (),
                    it.get("rejected") or (), it.get("unknown") or (), it.get("meta"), root)
            n += 1
        except Exception as e:
            errs += 1
            sys.stderr.write("hdrmap replay %s %s: %s: %s\n" % (tab, it.get("key") if isinstance(it, dict) else "?",
                                                               type(e).__name__, e))
            try:
                _enqueue(tab, {"kind": "engine_error", "key": (it.get("key") if isinstance(it, dict) else "") or "",
                               "role": (it.get("role") if isinstance(it, dict) else None) or "*",
                               "quarter": (it.get("q") if isinstance(it, dict) else "") or "",
                               "reason": "replay %s: %s" % (type(e).__name__, str(e)[:200])}, root)
            except Exception as e2:
                sys.stderr.write("hdrmap replay engine_error 큐 기록 실패: %s\n" % e2)
    out = write(tab, root=root, strict=True) or {}
    out.update({"records": n, "errors": errs})
    return out


# ── kce 어댑터 ───────────────────────────────────────────────────

_KCE_ROLE = (("ii4", "orders"), ("p8", "progress"), ("xinb", "xi"))


def record_kce(co, q, headers, meta=None, root=None, strict=False):
    """kce_build rep['headers'] → 역할별 record. 절 키가 **없으면** 기록하지 않는다(빈 리스트는 '봤는데 표 없음').
    항목 키: cols, n(머리행 포함 원행수 — 호출측 명시), n_rec, lead, ent, tag, basis, pick(기본 True), reason, rcpNo."""
    out = {}
    for sec, role in _KCE_ROLE:
        if sec not in (headers or {}):
            continue
        tables, picks = [], set()
        for i, it in enumerate(headers.get(sec) or []):
            t = dict(it)
            if role == "progress" and not t.get("tag"):
                t["tag"] = t.get("basis") or ""         # 상류 D 의 p8 tag = 연결/별도
            if role == "xi" and not t.get("tag"):
                t["tag"] = "나"       # 상류 D 의 xinb 76표 전부 '나'(원문 소절이 '가'인 sea·hdi 도) — 대조 키 유지
            if t.get("pick", True):
                picks.add(i)
            tables.append(t)
        out[role] = record("kce", co, q, role, tables, picks, meta=meta, root=root, strict=strict)
    return out


def render_headers_html(path, co, quarter, headers, root=None):
    """kce_render.render_headers_html 과 같은 시그니처·반환(텍스트 — 파일은 쓰지 않는다).
    하는 일은 **기록(스테이지) + 그 회사 스테이지를 덧씌운 렌더**뿐이다. hdrmap.json·큐는 건드리지 않는다 —
    커밋 시점은 호출측 몫(설계 A/G '호출측 성공 후 원자 쓰기, 실패 시 폐기'). 엄격 모드(실패 시 raise).

    U2 계약 — kce_build.update_quarter 의 회사 단위 fail-closed 와 맞춘다:
        text = hdrmap.render_headers_html(path, co, q, rep["headers"])   # 스테이지 + 렌더(디스크 무변화)
        … index·matrix·trace·headers 네 파일을 pending 에 모아 atomic_write 전부 성공 …
        hdrmap.commit_kce(co)              # 그제서야 hdrmap.json 커밋 + 큐 resolved 전환(resolved_in=q)
      예외(어느 단계든):
        hdrmap.discard("kce", co)          # 스테이지 폐기 — 지도·큐에 그 분기가 남지 않는다(미지 항목 큐만 남는다)
    이전 시도는 렌더 안에서 커밋해 pending 쓰기 실패 뒤에도 지도·큐가 그 분기를 가졌다(심사 지적) — 그래서 나눴다.
    커밋 뒤 render_headers("kce") 의 결과는 이 함수가 돌려준 텍스트와 바이트 동일(스테이지 우선 = 커밋본)."""
    record_kce(co, quarter, headers, root=root, strict=True)
    return render_headers("kce", out_html=path, root=root, write=False, strict=True, stage={co})


def commit_kce(co, root=None):
    """pending 쓰기 성공 뒤 그 회사 스테이지만 hdrmap.json 에 커밋(= write("kce", key=co, strict=True))."""
    return write("kce", key=co, root=root, strict=True)


# ── CLI ──────────────────────────────────────────────────────────

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="머리행 지도 엔진 — 검사·렌더·큐 조회")
    ap.add_argument("--tab", required=True)
    ap.add_argument("--root", default=None, help="argus/ 루트(기본: 이 파일 기준 — 테스트·점검용)")
    ap.add_argument("--check", action="store_true", help="회귀 검사(회귀만 exit 1)")
    ap.add_argument("--critical", default="", help="check: 수주표 소실을 회귀로 볼 회사 키(쉼표)")
    ap.add_argument("--render", action="store_true", help="headers.html 재생성(멱등)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--queue", action="store_true", help="open 큐 항목 요약")
    ap.add_argument("--drop", default=None, metavar="KEY[:ROLE[:Q]]",
                    help="지도(hdrmap.json)에서 (회사[:역할[:분기]]) 기록을 지운다 — 오기록 되돌림용. 큐는 건드리지 않고 "
                         "headers.html 의 그 분기도 남는다(--render 를 붙여도): 페이지는 git revert 로 되돌린다(설계 G 의 두 단계).")
    a = ap.parse_args(argv)
    rc = 0
    if a.drop:
        parts = a.drop.split(":")
        M = load_map(a.tab, a.root)
        co = M["companies"].get(parts[0])
        if co is None:
            sys.stderr.write("지도에 없는 회사: %s\n" % parts[0])
            return 2
        if len(parts) == 1:
            del M["companies"][parts[0]]
        elif len(parts) == 2:
            co["roles"].pop(parts[1], None)
        else:
            (co["roles"].get(parts[1]) or {}).pop(parts[2], None)
        if parts[0] in M["companies"]:
            co["fq"] = sorted({q for by in co["roles"].values() for q in by})
        _save_map(a.tab, M, a.root)
        print("dropped %s (지도만 — headers.html 은 git revert)" % a.drop)
    if a.render:
        text = render_headers(a.tab, out_html=a.out, root=a.root, strict=True)
        print("rendered %d bytes" % len(text))
    if a.queue:
        for it in open_items(a.tab, a.root):
            print("%s %s %s %s %s %s %s" % (it["id"], it["kind"], it["grade"], it["key"], it["role"],
                                           it["quarter_first"], it["reason"]))
    if a.check:
        rep = check(a.tab, critical=[c for c in a.critical.split(",") if c], root=a.root)
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        rc = rep["exit"]
    return rc


if __name__ == "__main__":
    sys.exit(main())
