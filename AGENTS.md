# AGENTS.md — Phalanx 레포 작업 규약 (Codex/AI 에이전트 필독)

이 레포는 **GitHub Pages로 배포되는 대시보드의 산출물 레포**다. 핵심 파일 다수가
로컬 머신의 빌더/크론이 **매일 재생성·덮어쓰기** 하므로, 어디를 고쳐도 되는지가 엄격하게 정해져 있다.
이 규칙을 어긴 PR은 머지되어도 **24시간 안에 크론이 되돌린다** (실제 사고 사례 2건 있음).

## 🚫 절대 직접 수정 금지 (생성물 — 로컬 빌더가 매일 덮어씀)

| 경로 | 생성 주체 |
|---|---|
| `index.html` | 로컬 `jem_site_build.py` (이 레포에 없음) |
| `manifest.js`, `data_*.js` (전부) | 로컬 빌더·크론 |
| `phalanx_offline.html` | 로컬 빌더 |
| `panoptes/app.js`, `panoptes/liq_charts.js`, `panoptes/tech_charts.js`, `panoptes/index.html`, `panoptes/tga_target.js` | 로컬 `~/phalanx/panoptes/` 원본을 매일 cp |
| `panoptes/data/*.json` (tga_target.json 제외) | 로컬 수집 크론 |

이 파일들의 변경이 필요하면: **PR 본문에 "로컬 빌더 반영 필요" 섹션으로 diff 제안만 남겨라.**
운영자가 로컬 원본에 반영한다. 예외: `panoptes/data/tga_target.json`은 GitHub Action
(`update-tga-target.yml`)이 관리하는 레포 단일소스 — 로컬에 사본을 만들지 마라.

## ✅ 자유롭게 작업 가능

- **새 디렉토리/새 파일**: `tools/`, `data/<신규소스명>/`, `codex_tasks/`, `.github/workflows/`, `panoptes/tools/`, `panoptes/tests/`
- 기존에 Codex가 만든 자립 모듈(`panoptes/tools/update_tga_target.py` 등)의 개선

## 데이터 수집기(fetcher) 작성 규약 — PR#3(TGA)이 모범 사례

1. **의존성 없는 파이썬 stdlib만** (requests/bs4/pandas 금지 — Action 러너·로컬 양쪽에서 무설치 실행)
2. **fail-closed**: 파싱 실패·검증 실패 시 기존 데이터 파일을 절대 건드리지 않고 비정상 종료
3. **출처 검증**: 공식 도메인 allowlist(https 강제·hostname 정확 일치), 응답 크기 상한, 구조 파싱(정규식 스크래핑 최소화)
4. **원자적 쓰기**: tmp 파일에 쓰고 os.replace
5. **정규화 JSON 출력**: 키 정렬·개행 고정(같은 데이터 → 같은 바이트, diff 노이즈 방지)
6. **테스트 동봉**: `<모듈>/tests/`에 fixture 기반 unittest + (프론트 연계 시) 계약 테스트
7. **GitHub Action**: schedule + workflow_dispatch만(외부 트리거 금지), `permissions: contents: write` 명시,
   자기 데이터 파일만 `git add -- <경로>`로 커밋, 푸시 전 `git pull --rebase origin main`
8. 데이터 파일 크기: 파일당 5MB 이하 유지(Pages 레포 비대화 방지). 월별 증분이면 window-merge(기존 이력 보존)

## PR 규약

- 기능 1개 = PR 1개. PR 본문에: 데이터 소스 URL·발표 주기·출력 파일 계약(경로+스키마)·검증 방법 명시
- UI 문자열은 한국어. 코드 주석 한국어 권장
- `git diff --check` 통과(공백 오류 금지), JS는 `node --check`, 파이썬은 unittest 통과 상태로 제출
- **index.html 통합을 시도하지 마라** — 프론트 통합은 운영자가 로컬 빌더에서 수행한다.
  새 데이터의 프론트 노출이 목적이면 "데이터 계약 + 렌더 제안 스케치"까지만.

## 참고 맥락

- 배포: main 푸시 → GitHub Pages 자동 리빌드(1~2분)
- 로컬 크론들은 push 전 pull --rebase 하도록 통일돼 있음(2026-08-16 이후) — Action 커밋과 공존 가능
- 과거 사고: PR이 index.html·panoptes/app.js를 직접 수정 → 크론이 이튿날 전부 되돌림.
  이 문서의 금지 목록은 그 재발 방지다.
