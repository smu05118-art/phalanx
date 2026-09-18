# AI·클라우드 업체별 관측과 앙상블

AI·클라우드 탭의 `업체별 신호 / 앙상블 / 연동 점검 / 기존 차트`를 제공한다.
`ui/patch.js`가 `renderAI2`를 감싸 `ui/cloud_signals.js`를 지연 로드한다.
index.html·data_*.js·manifest.js는 수정하지 않는다. UI 패치 훅이 이미 빌더에 존재한다.

업체별 URL: `?cloud=NBIS&cloudView=ledger#tab=ai`
앙상블 URL: `?cloudView=ensemble#tab=ai`
연동 URL: `?cloudView=integration#tab=ai`
기존 차트는 원래 렌더러를 호출한다. 모듈 로드 실패 시 원래 차트를 유지한다.

## 원본과 갱신

- 기존 `data_ai.js`의 `AID.cloud` 22개 업체, `AID.neocloud`, `AID.capex`를 **JSON 파싱**한다. JS 코드를 실행하지 않는다.
- 최초 원문 대조: 2026-09-10. `data/cloud_signals/reviewed.json`에 공식 실적발표 6개와 23개 관측을 기록했다. 실제 URL·공표일·검증일·정의·판정 근거가 각 행에 있다.
- 분기 공시가 주요 입력이다. `update-cloud-signals.yml`은 매일 22:40 UTC에 기존 팔랑크스 생성물을 스냅샷한다. 외부 IR·채용·가격 페이지를 자동으로 새로 읽는 수집기는 아니다.
- 추가 공식 관측을 reviewed.json에 검토 후 입력하고 원장을 다시 빌드해야 신규 신호가 검증 상태로 들어간다. 기존 데이터에 URL/conf=high가 있어도 자동으로 공식 확인으로 승격하지 않는다.
- 참고 사이트: https://nbistracker.com/signals — 근거 유형·기간·관측 이력 UX 참고. 데이터를 복제하거나 그 사이트를 공식 소스로 취급하지 않는다.

```sh
python3 tools/cloud_signals/build.py
node tools/cloud_signals/export_ensemble.cjs
python3 -m unittest discover -s tools/cloud_signals/tests -v
node --test ui/tests/cloud_signals.test.cjs
node --check ui/patch.js
node --check ui/cloud_signals.js
git diff --check
```

## 데이터 계약

`data/cloud_signals/ledger.json` (`cloud_signals/1`, 5MB 상한)

- `updated`, `tracking_started`: 실제 스냅샷 날짜와 추적 개시일.
- `providers`: 원본 티커/ID 기준 업체 사전. 별칭, 그룹, 공시 출처, 확인 대기 항목.
- `signals[]`: `id, key, revision, supersedes?, fingerprint, provider, metric, axis, period, value, unit, scope, evidence, verified, verified_at?, published_at, effective_at, first_seen_at, observed_at, source_url, source_path, correlation_group, direction, rule?, note`.
- 동일 관측 key의 내용이 바뀌면 버전을 추가한다. 기존 버전과 최초 수집일은 유지한다. 같은 값은 다시 관측했다고 시점을 갱신하지 않는다.
- 원장에 기록되기 전 시점의 first_seen은 복원하지 않는다. 기존 값의 실제 공표일을 모르므로 `published_at=null`을 유지한다. 분기 종료일을 공표일로 대체하지 않는다.
- 이전 기간 기록은 보존한다. 소스가 조용히 빠졌다고 확정 철회로 해석하지 않는다. 철회/정정이 확인되면 같은 key에 새 상태로 기록한다.
- `confirmed`(확인), `target`(목표), `external`(외부 관측), `inference`(추론), `unverified`(미검증). 초기 가져온 434개 관측은 전부 점수 제외.
- `integration`: 실제 공유 원본 비교와 업체별 DC 프로젝트 연결. 운영사·고객 관계 분리.

`data/cloud_signals/ensemble.json` (`cloud_ensemble/1`)

- 업체별 `score|null`, `coverage`, `axis_count`, `axes`, `source_count`, `used_ids`, `conflict`, `status`, `asof`.
- `used_ids`로 입력 원장의 근거까지 추적한다. UI와 저장 결과 모두 같은 JS 함수를 사용한다.
- 브라우저 API: `window.PhxCloud.ensemble(ledger.signals, 'NBIS', '2026-09-10')`.
- 특정 과거일 계산 시 관측·공표·검증·대상일이 그날 이후인 행은 사용하지 않는다.

## 계산 방법

수요 30 / 가동 25 / 계약 20 / 단가·수익성 15 / 자금 10. 방향은 근거를 명시한
규칙으로 -1, 0, +1을 부여한다. 동일 지표는 최신 기록을 사용하며, 같은 근거 그룹의
여러 지표는 평균한다. 축 평균에 90일 반감기 가중을 적용한다. 대상일 180일을 초과하면 제외한다.
목표·미검증·추론·비교 기준 없는 절대값·단위/스코프가 불명확한 값은 점수에 넣지 않는다.

가용축 가중평균을 0~100으로 변환한다. 결측은 분자와 분모에서 제외하고 충족률을 낮춘다.
2축/40% 미만은 점수 null이다. 점수는 **관측 방향 요약이며 검증된 예측모형이 아니다**.
동일 실적발표의 다른 축들이 통계적으로 독립이라고 주장하지 않는다. source_count를 병기한다.
현재 업체별 가용 지표가 다르므로 비교 가능한 매수 순위로 해석하지 않는다.

## 로컬 빌더 반영 필요

UI는 패치 레이어에서 동작하므로 별도 index.html 수정이 필요 없다. 아래는 기존 원본 정의의
수정 제안이며 이 PR은 생성물을 수정하지 않는다.

1. `neocloud_model.json`의 `NBIS.quarterly[2026-Q2].rpo_usd_m=5975`: 기존 note는 선수수익이라고 설명한다. 회계 원문을 대조하고 `deferred_revenue_usd_m`로 이름 변경할지 확인. RPO 합계에서 제외.
2. `NBIS.quarterly[*].contracted_mw`: 5,000MW는 2026년 말 계약전력 **목표** 공시다. 실적/목표 스키마를 분리하고 `actual/target`, 대상일을 명시.
3. `CRWV.quarterly[2026-Q2].rpo_usd_m=104000`: 공식 발표 정의는 RPO+기타 약정의 **revenue backlog**. `revenue_backlog_usd_m` 별도 필드 사용.
4. `ai_cloud.json`: `_meta.network_verified=false`인 기억 기반 자료를 후속 IR 대조 없이 확정치로 사용하지 않음. 행별 공표일·대상일·검증일을 추가.
5. `insights`/`nowcast` 원본 생성기에서 ensemble.json 입력을 받아 `used_ids`로 근거를 연결할 수 있음. 고객 노출·시차 검증과 홀드아웃 통과 전 자동 예측 입력은 보류.
6. 실제 launchd 파이프라인에도 build.py → export_ensemble.cjs를 마지막에 넣으면 매일 Action 대기 없이 생성물과 즉시 동기화 가능.
