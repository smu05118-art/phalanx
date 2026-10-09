# KCHEM — 한국화학 스프레드 (`argus/kchem`) 스펙 · 빌더 반영 제안

작성 2026-10-09. 배경 문서: 사용자 로컬 `phalanx_chem_spread_20261008/CHEM_SPREAD_REFLECTION_FINAL.md`(wj-stock 확인 전 반영안, 30행 매트릭스).
이 스펙은 그중 **P1(원천·외부 확인 불필요)** 을 구현한 결과와, 허브·빌더 쪽에 넘길 제안을 적는다.

## 1. 왜 이 탭인가 — 다른 ARGUS 산업 탭과 다른 점

- kce·kship·kdef 는 **DART 수주·재무**가 축이지만, 화학은 **스프레드(제품−원료)** 가 축이다. 모집단은 상장사가 아니라 **스프레드 시리즈**(원장 209 + 가격 12 + 자동 21).
- 입력이 **ARGUS 빌더 산출물**뿐이다. DART·네트워크·API 키를 쓰지 않는다. 그래서 수집기 규약 중 "출처 allowlist·응답 상한" 대신 **입력 스키마 fail-closed** 와 **결정성(fingerprint)** 이 핵심 계약이다.
- 원장은 유료 스팟(Platts류)이며 수동 xlsm 드롭이라 2026-08-24 주차 이후 멈춰 있다. 탭은 이것을 숨기지 않고 `원장 정지 N주` 로 맨 위에 보인다.
- wj-stock(회원 전용, robots `ai-input=no`)은 입력이 아니다. 화면 요소 중 "wj-stock 확인 필요" 행은 사용자가 체크리스트에 답할 때까지 보류.

## 2. 데이터 원천 (전부 레포 안)

| 축 | 원천 | 비고 |
|---|---|---|
| 시리즈·pos·m4·신선도 | `argus/data/argus_data.js` `spread.series` | 화학 13 카테고리 |
| 5년 추이 | `argus/data/chunk_<cat>.js` | 255주 축(2021-10-11~2026-08-24 고정) |
| 산식 역산 | `argus/data/connections.js` observations(주간 104) | 제품·원료 가격 포함 |
| 맵 링크 | `argus/data_map.js` | `map.html#series=argus:<sid>` |
| 사전 | `argus/kchem/tools/assets/aliases.json` | 한글→영문, 참조 지역 순서, 복합 원료 후보, 탐침 원료, 체인 추정, 中선물 매핑, 파생 정의 |

## 3. 분류축

- **chain** 허브 7 화학 체인(refining·ncc·aromatics·butadiene·vinyls·urethane·solvents) + `chain_est`(패널 None 51 에 추정 배정).
- **layer** integrated(−나프타) · step(−직접원료) · composite(복수 원료) · crack(−원유) · price · proxy · index.
- **region** 이름 접미사: 한국·대만·일본·동남아·동북아·중국·중국 Huadong/Huanan·인도·싱가포르·미국·유럽·나프타 허브 6. **ref_region** 은 역산으로 확정(모든 −납사 = Naphtha 일본, 중국 제품 = 한국 원료).
- **basis** ledger(원장 USD/MT) · derived(원장끼리 파생) · cnfut(中선물 CNY/t, 참고만) · index(PPI). 서로 다른 basis 를 한 산식에 넣지 않는다.
- **freshness** 패널 값 + expected_cadence(D/W/T/M)·stale_after·weeks_since(평가일 = argus asof).

## 4. 화면

`index`(KPI·고지·카테고리·체인 카드) · `spreads`(표 289행) · `matrix`(제품×지역, 셀 클릭 비교 차트) · `chains`(원료→제품 그래프 자동 다이어그램) · `coverage`(전수·규칙·결함·미재현·미배정·dead·자동 소스) · `<종목>`(21, 체인 역참조).
의존성 0(인라인 SVG, Chart.js 미사용). CSS 는 `kship.css` 복사 + kchem 규칙.

## 5. 판정 규칙 요약

`argus/kchem/LOGIC.md` §2. 핵심: 절편 없는 최소제곱, |잔차|≤1.5 USD/MT, 안쪽 90%·마지막 주 포함, 최근 26주 산식 변경 탐지, 복합 원료 후보·탐침, 결측-0 결함 탐지. 2026-10-05 입력 기준 재현 183/209.

## 6. 로컬 빌더 반영 필요 (제안 — `argus/index.html`·`data/*` 는 빌더 산출물이라 직접 수정하지 않음)

kchem 이 자체 해결한 항목이지만 허브·빌더(`~/phalanx/argus/argus_build.py` 등, Mini `task_claim` 필요)에서 고치면 kchem 의 우회가 필요 없어진다.

| # | 제안 | 근거(kchem 에서 확인한 사실) | 제안 diff 요지 |
|---|---|---|---|
| 1 | 청크·패널 `spread.series[]` 에 `region` 필드 | 지역이 이름 접미사에만 있다(한국 44·동남아 32·일본 31·대만 29·유럽 27·미국 27·…). kchem 은 정규식으로 파생 | 빌더 `series` 생성 시 `"region": <괄호 접미사>` 추가(없으면 null) |
| 2 | 허브 스프레드 카드에 `m4` 표시 | `argus_charts.js:834` 가 `(fin(r.m4)?'':'')` 로 값을 버린다 | `fin(r.m4)?'<span class="ag-m4">'+fmtPct(r.m4)+'</span>':''` |
| 3 | `spread.series[].stocks` | 카드에 종목 칩이 없다(체인 카드·시그널 표에만). kchem 은 `chains[].stocks` 를 체인 단위로 조인 | 빌더에서 `chain→stocks` 조인 결과를 행에 넣고 카드에 `stockChips` |
| 4 | 청크 축을 **live 소스 기준**으로 확장 | 청크 28개 axis 가 2026-08-24 고정 → `cf_benzene`(last 8695, 2026-09-30) 등 자동 소스의 최근 5~6주가 차트에서 잘림. kchem 은 connections 관측으로 우회 | axis = max(원장 축, 자동 소스 마지막 주); 원장 시리즈는 뒤를 null 로 |
| 5 | chain None 51 배정 | 화섬 17·중국내수 13·기초유분 9·초산체인 6·아크릴 5·중국선물 1 에 체인·종목 라벨 없음. kchem `aliases.chain_est` 참고(추정) | `chains.json` 멤버/카테고리 매핑 보강 |
| 6 | 원장 결함 처리 | BR−BD(한국): BR 가격 2026-04-06 정지 후 스프레드 = −BD(결측을 0 으로 계산) · PX−자일렌(대만) 2025-12-29 부터 −Naphtha 일본 · 에틸렌−납사(미국) 2026-01-12 부터 −Ethane | 원장 수정이 아니라 **인제스트에서 결측 제품 → 스프레드 null**, 열 참조 검사(같은 이름 시리즈의 지역별 k 분산 경고) |
| 7 | 스프레드 카드 → kchem 딥링크 | 허브 카드에 산식·표가 없다 | 카드 링크에 `kchem/spreads.html#cat=<cat>` 추가 |
| 8 | (선택) 레지스트리 산식 병기 | kchem `registry.json` 의 `formula`·`k`·`ref_region` 을 빌더가 읽어 카드 보조 텍스트로 | `argus/kchem/tools/assets/registry.json` 은 읽기 전용 입력으로 참조 가능(fingerprint 로 입력 버전 확인) |

## 7. 하지 않은 것 (의도)

- wj-stock 접속·값 복제 · 원장 값 수정 · csv 재배포 · DART/KIND 호출 · ECOS `sample` 키 호출 · tradedata 신규 HS 호출 · stale 시리즈에 시그널 생성 · `argus_charts.js`·`argus/index.html`·`_config.yml` 수정.
