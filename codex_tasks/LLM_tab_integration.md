# 🤖 LLM 탭 (OpenRouter 랭킹) — 로컬 빌더 반영 필요

2026-08-26 신설. openrouter.ai/rankings 의 전체 데이터셋(리더보드·주간 추이·제작사 점유율·
벤치마크·태스크별 지출·코딩 세션 비용·자연어/프로그래밍 언어·컨텍스트 길이·툴콜·이미지·
Top Apps·지연/처리량)을 파놉테스 탭으로 노출. 데이터는 CC BY 4.0 (출처 고지 푸터 포함).

## 구성 요소

| 파일 | 역할 | 관리 주체 |
|---|---|---|
| `panoptes/tools/update_llm_rankings.py` | 수집기 (stdlib만, fail-closed, 원자적 쓰기) | 레포 |
| `panoptes/tools/tests/test_update_llm_rankings.py` | 단위 테스트 | 레포 |
| `.github/workflows/update-llm-rankings.yml` | 매일 23:55 UTC(=08:55 KST) 자동 수집·커밋 | GitHub Action |
| `panoptes/data/llm_rankings.json` | 정규화 산출물 (~340KB) | GitHub Action (tga_target.json과 같은 예외 취급) |
| `panoptes/llm.html` | **독립 페이지** — 탭 통합 전에도 바로 접속 가능 | 레포 신규 |
| `panoptes/llm_charts.js` | 렌더러 `window.renderLLM(el, data)` — 의존성 0, 순수 SVG | 레포 신규 → **로컬 원본에도 복사 필요** |
| `panoptes/app.js` · `panoptes/index.html` | 탭 등록 (아래 diff — AGENTS.md 규약대로 **레포에 커밋하지 않음**) | **로컬 원본이 소스** |

## 지금 바로 보기

푸시 직후부터 **https://smu05118-art.github.io/phalanx/panoptes/llm.html** 에서 전체 화면으로 동작한다
(금지 파일을 건드리지 않는 신규 파일이라 크론과 충돌 없음).

## ⚠️ 파놉테스 본체 탭으로 넣으려면 — 맥스튜디오(로컬 원본)에서 아래 반영

app.js·index.html은 로컬 원본이 소스라서(AGENTS.md) 레포에 직접 커밋하지 않았다.
**주의: AGENTS.md의 `~/phalanx/panoptes/` 경로는 맥스튜디오에 실존하지 않음(2026-08-29 확인).**
실제 레포 클론은 `/Users/kioxia/Downloads/jem_site` (phalanx_update.sh의 `SITE`). 파놉테스
원본 소스 디렉토리는 launchd 크론 스크립트가 참조하는 경로를 grep으로 찾아 함께 패치할 것:

```bash
grep -rhoE "/Users/kioxia[^\"' ]*panoptes" /Users/kioxia/Downloads/*.sh /Users/kioxia/Downloads/*.py ~/Library/LaunchAgents/com.phalanx.*.plist 2>/dev/null | sort -u
```

찾은 원본 디렉토리(+ `jem_site/panoptes`)에 아래 diff 2건 적용 + `llm_charts.js`·`llm.html` 복사 후,
`jem_site`에서 `git add panoptes/ && git commit && git pull --rebase && git push`.

### app.js diff — switchTab에 llm 분기 + loadLLM 추가

```diff
   document.getElementById('shipview').hidden=(tab!=='ship');
+  document.getElementById('llmview').hidden=(tab!=='llm');
   document.getElementById('headStat').style.display=isMap?'':'none';
   if(isMap && MAP){setTimeout(()=>MAP.resize(),50);}
   if(tab==='liq' && !_liqLoaded){ _liqLoaded=true; loadLiq(); }
   if(tab==='tech'){ loadTech2(); }
   if(tab==='ship'){ loadShip(); }
+  if(tab==='llm'){ loadLLM(); }
+}
+async function loadLLM(){
+  const box=document.getElementById('llmview');
+  if(box.dataset.loaded) return;
+  box.innerHTML='<p class="hint" style="padding:20px">LLM 랭킹 데이터 로딩…</p>';
+  try{ const d=await fetch('data/llm_rankings.json').then(r=>r.json());
+    box.innerHTML=''; renderLLM(box, d); box.dataset.loaded='1';
+  }catch(e){ console.warn('llm', e); box.innerHTML='<p class="hint" style="padding:20px">LLM 랭킹 데이터 준비 중…</p>'; }
 }
```

### index.html diff — 탭 · 뷰 컨테이너 · 스크립트 3줄

```diff
       <span class="ptab" data-tab="ship">🚢 해운</span>
+      <span class="ptab" data-tab="llm">🤖 LLM</span>
```
```diff
   <div id="shipview" hidden style="flex:1;overflow-y:auto;padding:24px clamp(16px,4vw,48px)"></div>
+  <div id="llmview" hidden style="flex:1;overflow-y:auto;padding:24px clamp(16px,4vw,48px)"></div>
```
```diff
 <script src="shipping_charts.js"></script>
+<script src="llm_charts.js"></script>
```

## 데이터 계약 (llm_rankings.json)

- `as_of` 사용량 기준일 · `updated` 수집 시각(UTC) · `models{slug:{n,a,ad,ctx,r}}` 표시명 사전
- `leaderboard.{day|week|month|trending}[]` = `{m,v,pt,ct,tok,rq,ch}` (변형별 별도 랭킹, ch=전주 대비)
- 시계열 공통형 `{dates:[], series:{slug:[int]}}`: `top_chart`(52주) `market_share`(제작사)
  `languages.{English…}` `programming.{Python…}` `context.{1K|10K|100K|1M|10M}` `tools_series` `images_series`
- `benchmarks.{intelligence|coding|agentic}[]={m,p,name,score}` + `price_in`(가중 입력단가) — 출처 Artificial Analysis
- `tasks.{spend|tokens}` 매크로 4종 + 태스크 29종(상위 모델·전월 대비 pp)
- `session_cost.harnesses[]` = Hermes/Claude Code/Kilo/Codex × 모델 × `{single,short,core}` 중앙값 USD
- `apps.{day|week|month}[]` 상위 20 앱 · `performance[]` p50 지연·처리량

수집 실패 시 fail-closed(기존 파일 보존·비정상 종료). 엔드포인트는 무인증 공개
`openrouter.ai/api/frontend/v1/rankings/*` — 스키마가 바뀌면 Action이 빨간불로 알려준다.
