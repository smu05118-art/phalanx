#!/bin/bash
# Phalanx auto-updater — fetches latest trade data, rebuilds the dashboard,
# and pushes to GitHub Pages ONLY if something changed (idempotent).
#
#   phalanx_update.sh japan   # Japan customs (JEM) only — month-end Detailed run
#   phalanx_update.sh full    # Japan + Korea + Taiwan — regular 1/11/21 run
#
# Scheduled by launchd (see ~/Library/LaunchAgents/com.phalanx.*.plist).
set -uo pipefail
MODE="${1:-full}"
ROOT="/Users/kioxia/Downloads"
PY="$ROOT/.jem_venv/bin/python"
SITE="$ROOT/jem_site"
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
LOG="$ROOT/phalanx_update.log"
exec >> "$LOG" 2>&1

echo "===================================================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] START  mode=$MODE"

# --- secrets (e-Stat appId) ---
[ -f "$ROOT/.phalanx_secrets" ] && source "$ROOT/.phalanx_secrets"
if [ -z "${ESTAT_APPID:-}" ]; then echo "ERROR: ESTAT_APPID not set — abort"; exit 1; fi

cd "$ROOT" || { echo "ERROR: cd $ROOT failed"; exit 1; }

# --- Japan (JEM probe-card proxy) ---
echo "[japan] fetching e-Stat Detailed (税関別品別国別表)…"
if "$PY" jem_estat_fetch.py fetch --appid "$ESTAT_APPID" --out ./jem_data/estat_long.csv; then
  echo "[japan] fetch OK"
else
  echo "[japan] fetch FAILED (keeping previous data)"
fi

# --- Korea: TRASS excels from Slack (잠정 1/11/21 · 확정 15) → inbox ---
echo "[korea-trass] pulling TRASS excels from Slack…"
python3 kr_trass_slack_pull.py || echo "[korea-trass] pull skipped/failed"
echo "[alt-auto] Tier-1 자동수집(kworb·YouTube·Amazon·JungleScout)…"
python3 alt_auto_fetch.py || echo "[alt-auto] skip"
echo "[wtrend] W-Trend 팀 API 수집(SNS·아마존추정매출·틱톡샵)…"
python3 wasset_pull.py || echo "[wtrend] skip"
echo "[trass-arc] TRASS 기업수출 아카이브(B2B/B2C)…"
python3 trass_archive_fetch.py || echo "[trass-arc] skip"
echo "[kr-est] 한국 TRASS 잠정 19 HSK(K-트래킹)…"
python3 kr_estimated_fetch.py || echo "[kr-est] skip"
echo "[cos-hub] 화장품 허브(카테고리×지역×국가 추세 스코어 랭킹)…"
python3 cosmetics_hub_gov.py 2>/dev/null || echo "[cos-hub] 관세청 API 키 없음/실패 — 스킵"
python3 cosmetics_hub_ingest.py 2>/dev/null   # 사용자 TRASS export(있으면) 병합
python3 cosmetics_hub_fetch.py || echo "[cos-hub] skip"
echo "[echotik] 브랜드 틱톡샵 자동 수집(Playwright 지속세션)…"
"$PY" echotik_scrape.py && echo "[echotik] scrape OK" || echo "[echotik] scrape 실패(세션 만료?) — 이전 스냅샷 유지"
echo "[echotik] 틱톡샵 스냅샷 주입…"
python3 echotik_inject.py || echo "[echotik] inject skip"
echo "[alt] parsing 주간트래킹 → alt_series.json…"
"$PY" kr_alt_ingest.py && echo "[alt] OK" || echo "[alt] failed — keeping previous alt_series.json"
# (TRASS 잠정/확정 종목 파서는 별도 — kr_trass_ingest.py, 큐레이션 확정 후)

# --- Korea (UN Comtrade keyless, HS6 national) + Taiwan (MOPS 月營收) ---
echo "[korea] fetching UN Comtrade (window merge)…"
python3 kr_comtrade.py && echo "[korea] OK" || echo "[korea] failed — keeping existing kr_long.csv"
echo "[taiwan-census] MOPS 전수 월매출(신규월 증분)…"
python3 tw_census_fetch.py && python3 tw_census_build.py && echo "[taiwan-census] OK" || echo "[taiwan-census] skip"
echo "[taiwan] fetching MOPS monthly revenue…"
python3 tw_mops_fetch.py && echo "[taiwan] OK" || echo "[taiwan] failed — keeping existing tw_revenue.json"
echo "[usa] fetching UN Comtrade (window merge)…"
python3 us_comtrade.py && echo "[usa] OK" || echo "[usa] failed — keeping existing us_long.csv"
echo "[taiwan-trade] 대만 관세 미러통계(파트너 12개국 → 對대만, window merge)…"
python3 tw_comtrade.py && echo "[taiwan-trade] OK" || echo "[taiwan-trade] failed — keeping existing tw_long.csv"
echo "[japan-monthly] JPX ready.json 재생성(수집분+분류 병합)…"
python3 jp_monthly_build.py && echo "[japan-monthly] OK" || echo "[japan-monthly] skip"

# --- Thailand (LITE/Lumentum) — AUTOMATED via UN Comtrade (keyless preview) ---
# Refreshes a recent window of HS 851762 optical exports/imports by partner and
# MERGES into jem_data/thai_long.csv (never loses history; stdlib-only, no pandas).
echo "[thai] fetching UN Comtrade (HS 851762 optical, monthly window)…"
if python3 thai_comtrade.py; then
  echo "[thai] Comtrade fetch OK"
elif ls ./jem_data/thai_raw/*.csv >/dev/null 2>&1; then
  echo "[thai] Comtrade failed — falling back to manual portal CSVs"
  "$PY" thai_fetch.py normalize && echo "[thai] normalize OK" || echo "[thai] normalize failed"
else
  echo "[thai] Comtrade failed & no manual CSVs — keeping existing thai_long.csv"
fi

# --- quarterly financials (rev/opinc) for company cards — fiscal.ai -> stockanalysis fallback ---
echo "[fin] fetching quarterly financials…"
python3 fiscal_fetch.py && echo "[fin] OK" || echo "[fin] failed — keeping previous financials.json"

# --- rebuild dashboard ---
echo "[build] rebuilding index.html…"
if ! "$PY" jem_site_build.py; then echo "[build] FAILED — abort"; exit 1; fi

# --- local offline backup (self-contained HTML; works in Obsidian/file://) ---
BACKUP="/Users/kioxia/Documents/phalanx_backup/phalanx.html"
if cp "$SITE/phalanx_offline.html" "$BACKUP" 2>/dev/null; then echo "[backup] offline single-file → $BACKUP"; else echo "[backup] copy failed"; fi

# --- regenerate Logseq admin console (registry stays in sync) ---
"$PY" "$ROOT/phalanx_logseq.py" 2>/dev/null && echo "[logseq] admin page regenerated" || echo "[logseq] skip"

# --- commit & push only if changed ---
cd "$SITE" || { echo "ERROR: cd $SITE failed"; exit 1; }
git add -A
if git diff --cached --quiet; then
  echo "[git] no change — nothing to push"
else
  git commit -q -m "auto-update $(date '+%Y-%m-%d %H:%M %Z') (mode=$MODE)"
  if git push -q origin main; then echo "[git] pushed → Pages will rebuild in ~1-2 min"; else echo "[git] push FAILED"; exit 1; fi
fi
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] DONE"
