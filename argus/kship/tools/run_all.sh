#!/usr/bin/env bash
# 한국조선(kship) 실적 모델 — 재현 한 줄. MODEL.md §7·§12-7 과 HANDOFF 의 명령 순서를 한 스크립트로 묶었다(2026-10-05 V9).
# 네트워크 단계는 플래그로만 켠다. 기본은 캐시·산출물만으로 도는 오프라인 사슬이다(bash 3.2 호환 — 맥 기본 bash).
#
#   tools/run_all.sh                                   # 오프라인: sls → model(+xlsx) → pages(페이지·허브) → link → tests → check
#   tools/run_all.sh --market                          # + ② 환율·시세 (ECB·aik, 키 없음)
#   tools/run_all.sh --collect --fin --notes           # + 계약·정기보고서·기자재(KIND·DART) + ① 재무제표 + ①′ 주석 — DART 는 프로세스 하나, 순차
#   tools/run_all.sh --net                             # = --collect --fin --notes --market
#   tools/run_all.sh --patch                           # + ⑤ 레퍼런스 원본 패치 (맥미니 로컬 전용 — 레퍼런스 폴더가 있을 때만, *_orig.xlsx 는 건드리지 않는다)
#   tools/run_all.sh --today 2026-10-05 --quarter 2026Q3    # built_at 고정 · 정기보고서 분기 강제(기본: 분기말 +50일 · 사업보고서 +95일 규칙)
#   tools/run_all.sh --only sls,model --skip tests     # 단계 고르기 / 빼기 (쉼표 구분)
#   tools/run_all.sh --dry-run --net --patch           # 실행할 명령만 출력 — 아무것도 바꾸지 않는다
#   tools/run_all.sh --print-quarter [--today D]       # 기대 최신 분기만 출력 (update-kship.yml 재무제표 단계와 같은 규칙)
#
# 단계 순서(계약 — MODEL.md §7: ② 가 ③ 보다, ① 이 ④ 보다, ④ 가 ⑥ 보다 앞):
#   collect → fin → notes → market → sls → model → patch → pages → link → tests → check
# 환경: PY(기본 ~/Library/phalanx_venv/bin/python, 없으면 python3) · KSHIP_REF_DIR(레퍼런스 폴더 재지정 → --ref-dir) · KSHIP_FORCE_BUILD=1(fin json 무조건 재생성)
# 종료 코드: 0 전부 성공 · 2 인자 오류 · 그 외 첫 실패 단계에서 중단(set -e). 성공 문구를 믿지 말고 마지막 check 요약(summary counts·골든 합계·테스트 건수)을 본다.
# 보고는 실행한 명령과 출력으로 — 이 스크립트는 "완료" 를 선언하지 않는다.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PY="${PY:-$HOME/Library/phalanx_venv/bin/python}"
if [ ! -x "$PY" ]; then PY="python3"; fi

ALL_STAGES="collect fin notes market sls model patch pages link tests check"
DEFAULT_STAGES="sls model pages link tests check"

TODAY=""; QUARTER=""; DRY=0; PRINT_Q=0; ONLY=""; SKIP=""
ADD=""

usage() { sed -n '2,20p' "$0"; }

die() { echo "run_all: $*" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --collect|--fin|--notes|--market|--patch) ADD="$ADD ${1#--}" ;;
    --net) ADD="$ADD collect fin notes market" ;;
    --today) [ $# -ge 2 ] || die "--today 값 없음"; TODAY="$2"; shift ;;
    --quarter) [ $# -ge 2 ] || die "--quarter 값 없음"; QUARTER="$2"; shift ;;
    --only) [ $# -ge 2 ] || die "--only 값 없음"; ONLY="$2"; shift ;;
    --skip) [ $# -ge 2 ] || die "--skip 값 없음"; SKIP="$2"; shift ;;
    --dry-run) DRY=1 ;;
    --print-quarter) PRINT_Q=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "모르는 인자 $1 (--help)" ;;
  esac
  shift
done

if [ -n "$TODAY" ] && ! printf '%s' "$TODAY" | grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then die "--today 형식 YYYY-MM-DD: $TODAY"; fi
if [ -n "$TODAY" ] && ! "$PY" -c 'import datetime, sys; datetime.date.fromisoformat(sys.argv[1])' "$TODAY" 2>/dev/null; then die "--today 날짜 아님: $TODAY"; fi
if [ -n "$QUARTER" ] && ! printf '%s' "$QUARTER" | grep -Eq '^[0-9]{4}Q[1-4]$'; then die "--quarter 형식 YYYYQn: $QUARTER"; fi

# 기대 최신 분기 — update-kship.yml 재무제표 단계와 같은 규칙(분기·반기보고서 분기말 +50일, 사업보고서 +95일).
expected_quarter() {
  TODAY="$TODAY" "$PY" - <<'PYQ'
import datetime, os
d = datetime.date.fromisoformat(os.environ["TODAY"]) if os.environ.get("TODAY") else datetime.date.today()
y, q = d.year, (d.month - 1) // 3 + 1
while True:
    q -= 1
    if q == 0:
        y, q = y - 1, 4
    m = q * 3
    end = datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)
    if end + datetime.timedelta(days=95 if q == 4 else 50) <= d:
        print("%dQ%d" % (y, q)); break
PYQ
}

Q1="${QUARTER:-$(expected_quarter)}"
if [ "$PRINT_Q" = 1 ]; then echo "$Q1"; exit 0; fi

# 단계 집합 — --only 가 있으면 그것만, 없으면 기본 + 플래그 추가, 그 뒤 --skip 제거. 순서는 ALL_STAGES 가 정한다.
want=" $DEFAULT_STAGES $ADD "
if [ -n "$ONLY" ]; then want=" $(printf '%s' "$ONLY" | tr ',' ' ') "; fi
skip=" $(printf '%s' "$SKIP" | tr ',' ' ') "
enabled() {  # $1 단계 이름 → 켜져 있으면 0
  case "$want" in *" $1 "*) ;; *) return 1 ;; esac
  case "$skip" in *" $1 "*) return 1 ;; esac
  return 0
}
for s in $(printf '%s' "$ONLY,$SKIP" | tr ',' ' '); do
  case " $ALL_STAGES " in *" $s "*) ;; *) die "모르는 단계 $s (가능: $ALL_STAGES)" ;; esac
done

TODAY_ARGS=""
[ -n "$TODAY" ] && TODAY_ARGS="--today $TODAY"
QUARTER_ARGS=""
[ -n "$QUARTER" ] && QUARTER_ARGS="--quarter $QUARTER"

STAGE=""; SUMMARY=""
run() {  # 명령을 보여 주고 실행한다(--dry-run 이면 출력만)
  if [ "$DRY" = 1 ]; then echo "DRY ▶ [$STAGE] $*"; return 0; fi
  echo "▶ [$STAGE] $*"
  "$@"
}
note() { echo "· [$STAGE] $*"; }

listing() { find assets/fin_cache -type f -not -name '.collect.lock' 2>/dev/null | LC_ALL=C sort | "$PY" -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest()[:16])'; }

begin() { STAGE="$1"; T0=$(date +%s); echo; echo "━━ $STAGE ━━"; }
end_stage() { local dt=$(( $(date +%s) - T0 )); SUMMARY="$SUMMARY$STAGE ${dt}s · "; }

echo "run_all: PY=$PY · 기대 최신 분기 $Q1${TODAY:+ · today $TODAY}${DRY:+ }$( [ "$DRY" = 1 ] && echo '· DRY-RUN(실행 안 함)' )"
echo "run_all: 단계 =$(for s in $ALL_STAGES; do enabled "$s" && printf ' %s' "$s"; done)"

# ── collect: 모집단(KIND) · 척당 계약 · 조선사 정기보고서 · 기자재 · 사전 (KIND·DART 네트워크, 순차 한 프로세스) ──
if enabled collect; then
  begin collect
  run "$PY" kship_universe.py --write
  run "$PY" kship_contracts.py --collect
  run "$PY" kship_contracts.py --build
  run "$PY" kship_yards.py --collect $QUARTER_ARGS
  run "$PY" kship_suppliers.py --collect $QUARTER_ARGS
  run "$PY" kship_suppliers.py --build
  run "$PY" build_dicts.py
  end_stage
fi

# ── fin: ① 재무제표 (DART 단일 프로세스 — kship_fin 자체가 .collect.lock(flock) 으로 둘째 프로세스를 물린다) ──
if enabled fin; then
  begin fin
  mkdir -p assets/fin_cache
  if [ "$DRY" = 1 ]; then
    run "$PY" kship_fin.py --collect --all --quarters "2021Q4..$Q1"
    echo "DRY ▶ [$STAGE] (캐시 목록이 바뀌었거나 KSHIP_FORCE_BUILD=1 이면) $PY kship_fin.py --build --all --quarters 2021Q4..$Q1"
  else
    BEFORE="$(listing)"
    run "$PY" kship_fin.py --collect --all --quarters "2021Q4..$Q1"
    AFTER="$(listing)"
    if [ "$BEFORE" != "$AFTER" ] || [ ! -f assets/fin/010140.json ] || [ "${KSHIP_FORCE_BUILD:-0}" = 1 ]; then
      note "캐시 변경($BEFORE → $AFTER) — fin json 재생성"
      run "$PY" kship_fin.py --build --all --quarters "2021Q4..$Q1"
    else
      note "캐시 변경 없음 — fin json 유지(collected_at 만 바뀌는 커밋을 막는다)"
    fi
    note "fin json $(ls assets/fin 2>/dev/null | wc -l | tr -d ' ')개 · FAIL $(grep -c ' FAIL ' assets/fin_collect.log 2>/dev/null || echo 0)건"
  fi
  end_stage
fi

# ── notes: ①′ 주석 (하위 노드 → 없으면 부모 절 1개; 캐시·체크포인트가 있으면 요청 0) ──
if enabled notes; then
  begin notes
  mkdir -p assets/fin_cache
  if [ "$DRY" = 1 ]; then
    run "$PY" kship_fin.py --collect-notes --all --notes-parent-fallback
    echo "DRY ▶ [$STAGE] (주석 캐시 목록이 바뀌면) $PY kship_fin.py --build --all --quarters 2021Q4..$Q1"
  else
    BEFORE="$(listing)"
    run "$PY" kship_fin.py --collect-notes --all --notes-parent-fallback
    AFTER="$(listing)"
    if [ "$BEFORE" != "$AFTER" ] || [ "${KSHIP_FORCE_BUILD:-0}" = 1 ]; then
      note "주석 캐시 변경($BEFORE → $AFTER) — fin json 재생성"
      run "$PY" kship_fin.py --build --all --quarters "2021Q4..$Q1"
    else
      note "주석 캐시 변경 없음 — fin json 유지"
    fi
    grep "notes parent" assets/fin_collect.log 2>/dev/null | tail -2 || true
  fi
  end_stage
fi

# ── market: ② 환율·시세 (ECB·aik, 키 없음) ──
if enabled market; then
  begin market
  run "$PY" kship_fx.py $TODAY_ARGS
  run "$PY" kship_price.py $TODAY_ARGS
  end_stage
fi

# ── sls: ③ 선표 (contracts.json · yards_cache · fx.json → assets/sls/) — reference_anchor 기본 + ledger_relative 를 *_alt 로 함께 저장 ──
if enabled sls; then
  begin sls
  run "$PY" kship_sls.py --all --report
  end_stage
fi

# ── model: ④ 모델 + 생성 xlsx (fin·fx·prices·sls·forecast_panel → assets/models/ + ../models/<stock>_model.xlsx) ──
if enabled model; then
  begin model
  run "$PY" kship_model.py --build --all --xlsx $TODAY_ARGS
  end_stage
fi

# ── patch: ⑤ 레퍼런스 원본 패치 — 로컬 전용(레포 밖 사유 파일). 운영 플래그 = MODEL.md §12-7. 폴더가 없으면 건너뛴다.
#    --extend-formulas 는 2026-10-08 부터 CLI 기본 all(끄려면 --extend-formulas off) — 여기서 따로 주지 않는다 ──
if enabled patch; then
  begin patch
  REF_ARGS=""
  if [ -n "${KSHIP_REF_DIR:-}" ]; then
    REF_DIR="$KSHIP_REF_DIR"; REF_ARGS="--ref-dir $KSHIP_REF_DIR"
  elif [ -d "$HERE/../../../jem_data/kship_models/reference" ]; then
    REF_DIR="$HERE/../../../jem_data/kship_models/reference"
  else
    REF_DIR="$HOME/phalanx/jem_data/kship_models/reference"
  fi
  if [ -d "$REF_DIR" ]; then
    run "$PY" kship_xlsx_patch.py --all --verify --overwrite-placeholders --fx-actuals --is-convention 3m $TODAY_ARGS $REF_ARGS
  else
    note "레퍼런스 폴더 없음($REF_DIR) — 건너뜀(맥미니 로컬 전용 단계)"
  fi
  end_stage
fi

# ── pages: ⑥ 회사 페이지·허브 — 훅이 assets/models 가 있는 회사에만 섹션을 붙인다. ④ 뒤에 돌아야 페이지가 현재 모델을 싣는다 ──
if enabled pages; then
  begin pages
  run "$PY" kship_page.py --all
  run "$PY" kship_parts.py --all
  run "$PY" kship_model_section.py --hub
  end_stage
fi

# ── link: argus/index.html 의 ⚓ 진입 링크 재주입 (로컬 크론이 지우면 다시) ──
if enabled link; then
  begin link
  run "$PY" inject_link.py --apply
  end_stage
fi

# ── tests ──
if enabled tests; then
  begin tests
  run "$PY" -m unittest discover -s tests -p 'test_*.py'
  end_stage
fi

# ── check: 산출물 요약 — 숫자는 파일에서 읽어 그대로 보인다(성공 문구 없음) ──
if enabled check; then
  begin check
  if [ -f ../010140/index.html ]; then run "$PY" kship_model_section.py --check ../010140/index.html; fi
  if [ "$DRY" = 1 ]; then
    echo "DRY ▶ [$STAGE] summary.json counts · sls origin · fin golden 합계 · fin json 수 출력"
  else
    "$PY" - <<'PYC'
import glob, json, os
def load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception as e:
        return {"_error": str(e)}
s = load("assets/models/summary.json")
print("models/summary.json: built_at %s · origin %s · n %s · counts %s" % (s.get("built_at"), s.get("origin"), s.get("n"), s.get("counts")))
ss = load("assets/sls/summary.json")
print("sls/summary.json: origin %s · cohort_mode %s · 회사 %d · shared_pairs_n %s" % (ss.get("origin"), ss.get("cohort_mode"), len(ss.get("rows") or []), ss.get("shared_pairs_n")))
fx = load("assets/fx.json"); pr = load("assets/prices.json")
print("fx.json: as_of %s · 분기 %d · daily_last %s" % (fx.get("as_of"), len(fx.get("quarters") or {}), (fx.get("daily_last") or {}).get("date")))
rows = pr.get("rows") or {}
print("prices.json: as_of %s · 종목 %d · error %d" % (pr.get("as_of"), len(rows), sum(1 for r in rows.values() if "error" in r)))
fins = sorted(glob.glob("assets/fin/*.json")); m = c = 0; dates = set()
for p in fins:
    d = load(p); dates.add(d.get("collected_at"))
    for q, g in (d.get("golden") or {}).items():
        if isinstance(g, dict) and "compared" in g:
            c += g["compared"]; m += g["compared"] - len(g.get("mismatch") or [])
print("fin: json %d · collected_at %s · 골든 합계 %d/%d%s" % (len(fins), sorted(x for x in dates if x), m, c, (" = %.1f%%" % (100.0 * m / c)) if c else ""))
print("xlsx: %d개 · 섹션 페이지 %d장" % (len(glob.glob("../models/*_model.xlsx")),
      sum(1 for p in glob.glob("../[0-9]*/index.html") if "실적 모델" in open(p, encoding="utf-8").read())))
PYC
  fi
  end_stage
fi

echo
echo "run_all 끝 — 단계 소요: ${SUMMARY%· }"
