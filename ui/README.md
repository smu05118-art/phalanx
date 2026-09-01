# ui/ — 프론트 패치 레이어

`index.html`은 로컬 빌더(`jem_site_build.py`)가 매일 재생성하는 산출물이라 직접 수정하면
크론이 24시간 안에 되돌린다(AGENTS.md). 이 디렉토리는 그 제약을 우회하는 **패치 레이어**다:

- **`ui/patch.css`** — 디자인 토큰·타이포·칩 통일·모바일 미디어쿼리. index.html 인라인 `<style>` 뒤에 로드되어 동일 특이도에서 승리.
- **`ui/patch.js`** — 전역 함수 오버라이드(renderRegions·renderOverview·catDrill 등). 모듈별 try/catch 격리 — 한 모듈이 죽어도 나머지와 원본 동작은 유지.
- 근거: 2026-08-26 UX 전수 감사(확정 47건). 각 코드 블록에 감사 항목 번호(P0-xx/P1-xx/P2-xx) 주석.

## 동작 방식

index.html의 `</head>` 앞에 폰트+patch.css `<link>`, `</body>` 앞에 patch.js `<script>` 훅이 주입된다.
크론이 index.html을 덮어써 훅이 사라지면 **GitHub Action**(`.github/workflows/ui-patch-inject.yml`)이
push를 감지해 `tools/inject_ui_patch.py`로 재주입한다(멱등 — 훅이 있으면 no-op).

크론 push 직후 Pages가 훅 없는 버전을 1~2분 서빙하는 창이 있다. 이 창을 없애고 커밋 노이즈를
줄이려면 **빌더 템플릿에 훅을 직접 넣는 것이 정공법**이다:

```
# jem_site_build.py 의 index.html 템플릿에서
#   </head> 직전에:
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="ui/patch.css">
#   </body> 직전에:
<script src="ui/patch.js"></script>
```

빌더 반영 후에는 `.github/workflows/ui-patch-inject.yml`을 삭제해도 된다
(주입 마커 `ui-patch:v1`이 템플릿에 있으면 스크립트는 어차피 no-op).

## UI를 고치고 싶을 때

1. `ui/patch.css` / `ui/patch.js` 수정 → main에 push → Pages 반영 끝. **빌더를 거칠 필요 없음.**
2. 개선이 안정화되면 빌더 템플릿에 병합하고 이 파일에서 해당 모듈 삭제(패치는 얇게 유지).

## 운영 참고

- **Action run이 빨간불로 실패하는 경우**: 재주입 run 도중 다른 push(크론)가 끼어 rebase 충돌이 난 것 —
  충돌을 일으킨 push가 새 run을 큐잉하므로 **자동 복구된다. 조치 불필요.**
- **크론 push 실패 시**: 로컬 크론 스크립트에 `git pull --rebase origin main`이 push 앞에 있는지 확인
  (레포 미러 `phalanx_update.sh`에는 2026-08-26 추가됨 — **맥스튜디오의 실제 launchd 스크립트에도 같은 줄이 필요**).
- 크론 push 직후 1~2분은 Pages가 훅 없는 구 UI를 서빙할 수 있다(깨짐 아님 — Action 재주입 후 새 UI 복귀).
- 렌더러 미구현 탭(현재 ecal·tmap·ppi — 빌더에서 loadEcal/renderEcal 등 유실)은 patch.js가 자동으로 숨긴다.
  빌더가 렌더러를 복원하면 탭도 자동 재노출.

## 롤백

- 전체 끄기: `ui-patch-inject.yml` 삭제 + patch.css/patch.js를 빈 파일로 (다음 크론이 훅 없는 index.html을 밀면 원상복구).
- 일부 끄기: patch.js에서 해당 `safe('모듈명', ...)` 블록 삭제.

## manifest 필드 현황 (감사 P0-06 · P1-03 · P1-08)

2026-08-28 빌더가 `source_short`·`n`·전역 `built` 주입 완료(커밋 c2b901b) — patch.js는 이 값을 우선 사용한다
(하드코딩 SRC_SHORT/REG_NAME은 폴백으로 유지). 훅도 같은 커밋으로 빌더 템플릿에 내장되어
재주입 Action은 안전망으로만 동작(no-op).

- `last_pub`(리전별 실제 마지막 공표월)만 미주입 — 프론트가 revenue/detail 스캔으로 정확히 계산 중이라
  실익이 작음. 빌더에서 주입하면 patch.js가 자동으로 그 값을 우선 사용한다(lastPubYM 참고).
