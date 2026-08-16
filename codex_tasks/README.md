# BadOnion 벤치마킹 확장 — 전체 아키텍처 & 트랙 분할

2026-08-16 설계. 상용 서비스 나쁜양파(badonion.co.kr) 벤치마킹에서 도출한 8개 확장 트랙.
**원천 공개데이터로 직접 구축**한다(타 서비스 데이터 수집 없음).

## 병렬 실행 구조

```
Codex 클라우드 (이 레포 포크 → PR)          로컬 (운영자+Claude)
──────────────────────────────           ──────────────────────────────
T1 US 주별·세관구별 수출입    ─┐          T5 컨센서스 수집→Beat확률→나우캐스트 통합
T2 PPI 4개국(JP·KR·CN 추가)  ─┼─ PR ──→  T8 프론트 통합(빌더에 렌더 추가)
T3 세관 발표 캘린더 데이터     ─┤          T6 급등 스크리너 상설화(fpx→일일)
T4 중국 성별 수출입 정찰+수집  ─┘          T7 커버리지 국가 확장(+8국 Comtrade)
```

- Codex 트랙(T1~T4)은 **자립형 수집기 + GitHub Action + 정규화 JSON** 산출까지.
  프론트(index.html) 통합은 하지 않는다(AGENTS.md 참조) — 데이터 계약만 지키면 T8이 붙인다.
- 각 트랙 스펙: `codex_tasks/T1_us_census.md` ~ `T4_cn_province.md`. **Codex에 이 파일 하나씩 태스크로 투입**하면 된다.
- 모범 사례: `panoptes/tools/update_tga_target.py` + `.github/workflows/update-tga-target.yml` (구조·테스트·fail-closed 철학을 그대로 따를 것)

## 데이터 계약 공통 규칙

- 출력: `data/<source>/` 아래 정규화 JSON (키 정렬, ensure_ascii=False, indent 없음+개행 고정)
- 모든 시계열 파일에 `{"schema":"<name>/1","updated":"YYYY-MM-DD","series":{...}}` 헤더
- 월 키: `"YYYY-MM"`. 값: 정수(달러·해당통화 원단위) 또는 null(결측 — 0으로 채우지 마라. 부분분기 왜곡 사고 전례)
- window-merge: 최근 N개월 재수집분을 기존 이력에 병합, 과거는 절대 삭제하지 않음

## 트랙별 요약

| # | 트랙 | 산출물 | 프론트 통합처(T8) |
|---|---|---|---|
| T1 | US Census 주별(statehs)·세관구별(porths) | `data/uscensus/*.json` | US 카드 주별 분해·니어쇼어링 뷰 |
| T2 | PPI 일본 CGPI·한국 ECOS·중국 NBS | `data/ppi4/*.json` | PPI 탭 4국화 + 홈 PPI 급등 TOP |
| T3 | 14개국 세관 발표일 규칙+계산기 | `data/tradecal/schedule.json` | ecal 탭 세관 레이어 |
| T4 | 중국 성별 총액+기전+하이테크 (MOFCOM — GACC 직접수집은 정찰 결과 불가 판정) | `data/cnprov/monthly.json` | CN 허브 성별 신호(광둥·저장·푸젠) |
| T5 | 어닝 컨센서스 수집 + predyoy 대비 Beat확률 | `jem_data/consensus.json`(로컬) | 나우캐스트 탭 "컨센 대비" 컬럼 |
| T6 | HS 품목 무버 일일 스크리너 | `jem_data/surge.json`(로컬) | 홈/대시보드 급등 위젯 + 신규카드 후보 자동발굴 |
| T7 | Comtrade 리포터 +8국(MY·MX·ID·IN·BR·CA·PH·CR) | `jem_data/<cc>_long.csv`(로컬) | 글로벌 트리맵 + 기업 다면 대조 |
| T8 | 프론트 통합 전부 | 빌더 수정(로컬) | — |

## ⚠️ 사전 준비 (운영자가 직접 — Codex 착수 전 완료 권장)

1. **CENSUS_API_KEY** (T1 필수): https://api.census.gov/data/key_signup.html 무료 발급 →
   GitHub 레포 Settings → Secrets and variables → Actions 에 등록
2. **ECOS_API_KEY** (T2 한국 파트): ecos.bok.or.kr 가입 후 발급 → 동일하게 Secrets 등록
   (없으면 T2는 일본·중국만 수집하고 한국은 스킵 — 나중에 추가 가능)

## Beat 확률 모델 (T5 설계 요지)

나우캐스트 predyoy(세관→매출 회귀 예측)와 컨센서스 내포 YoY를 비교:
```
z = (predyoy − consensus_yoy) / σ_resid     # σ_resid = 회귀 잔차 표준편차(홀드아웃)
P(Beat) = Φ(z)                              # 정규 근사, 표본<12분기면 t분포
```
표기 규칙: P≥0.65 "상회 우세" / 0.55~0.65 "소폭 상회 우세" / 0.45~0.55 "접전" / 미만은 대칭.
컨센이 없는 종목은 표기 생략(추정 금지). 검증: 과거 8분기 백테스트 hit-rate를 종목별 병기.
