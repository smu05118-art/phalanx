# T1 — 미국 주(州)별·세관구(district)별 수출입 수집기

> **먼저 레포 루트 `AGENTS.md`를 읽어라.** 모범 사례: `panoptes/tools/update_tga_target.py`(+테스트·워크플로) — 그 구조·fail-closed 철학을 그대로 따를 것.

## 목적

US Census Bureau International Trade API에서 **주별(state)×HS**, **세관구(district)×HS** 월별 수출입을
수집해 정규화 JSON으로 레포에 적재한다. 국가 단위만 보던 미국 데이터를 생산·반입 지리로 분해해
기업 프록시(예: 캘리포니아의 말레이시아산 SSD 수입, 휴스턴-갤버스턴 원유 수출)를 가능하게 하는 기반 데이터다.

## 데이터 소스 (2026-08-16 라이브 검증 완료 — 아래 사실 그대로 구현)

- **API 키 필수**(2025년부터 전 요청 강제 — 무키는 302→"Missing Key" 리다이렉트 실측).
  GitHub Secrets `CENSUS_API_KEY` **필수**. 키 없으면 즉시 명확한 에러로 종료(무키 폴백 만들지 마라).
  키 발급은 운영자가 https://api.census.gov/data/key_signup.html 에서(무료·이메일 즉시).
- 베이스: `https://api.census.gov/data/timeseries/intltrade/`
  - 주별 수출: `exports/statehs` — `STATE`(USPS 2자, Origin of Movement=선적 출발 주), `E_COMMODITY`, `COMM_LVL=HS6`, `ALL_VAL_MO`, `time=YYYY-MM`(from/to 범위 지원)
  - 주별 수입: `imports/statehs` — `I_COMMODITY`, `GEN_VAL_MO`(일반수입)+`CON_VAL_MO`(소비수입)
  - **세관구별: 별도 데이터셋 없음** — `exports/hs`·`imports/hs`의 `DISTRICT`/`DIST_NAME` 변수로 추출(여긴 HS10까지 지원)
  - 항만별(선택): `exports/porths`·`imports/porths` — `PORT`(4자=district2+port2), 수입은 GEN_VAL_MO만
- HS 자릿수: statehs/porths는 **HS6 상한**, hs(세관구)는 HS10까지 — 기본 HS6 통일
- 세관구 코드표: `https://www.census.gov/foreign-trade/schedules/d/dist3.txt` (정적, 무키. 휴스턴-갤버스턴=53 검증됨)
- 발표: FT-900과 동시(08:30 ET), 통계월+약 35일. 2026 검증 일정: 6월분→8/4, 7월분→9/3, 8월분→10/6, 9월분→11/4, 10월분→12/8.
  발표일은 하드코딩하지 말고 `census.gov/foreign-trade/reference/release_schedule.html` 파싱(2025년 지연 사례 있음)
- 개정: 매 릴리스에서 전월 수정 → **최근 2개월 upsert**, 매년 4월경 연간 개정 → 4월엔 전년도 전체 재수집
- 문서화된 한도는 "쿼리당 변수 50개"뿐, 페이지네이션 없음 — 대형 쿼리는 STATE/DISTRICT 단위 분할, 1~2req/s 스로틀+지수 백오프

## 수집 범위 (전량 수집 금지 — 화이트리스트)

레포 `data/uscensus/watchlist.json`(이 태스크에서 초기 버전 생성)에 정의된 HS 목록만 수집:

```json
{"hs6": ["847170","852351","854442","851762","850440","854231","854232",
          "270900","851713","903180","848620","854370","852990","880240",
          "294200","300215","871260","950450"],
 "states": "ALL", "districts": "ALL"}
```

(AI 하드웨어·광통신·스토리지·반도체장비·원유·바이오 등 기존 대시보드 카드와 겹치는 코드. 추가는 운영자가 watchlist 수정으로.)

## 출력 계약

- `data/uscensus/state_{exp|imp}.json`:
  `{"schema":"uscensus_state/1","updated":"YYYY-MM-DD","hs":{"847170":{"CA":{"2025-01":123456,...},"TX":{...}}}}`
- `data/uscensus/district_{exp|imp}.json`: 동일 구조(주 대신 district 코드, 별도 `districts_meta` 키에 코드→이름 맵)
- 값: **월별 달러 정수**. 결측은 키 생략(0 채우기 금지). 기존 이력 보존(window-merge)
- 파일당 5MB 초과 시 HS별 분할(`state_exp_847170.json` 방식)로 전환하고 인덱스 파일 추가

## 구현 요구

1. `tools/uscensus/fetch_uscensus.py` — stdlib-only, fail-closed, 원자적 쓰기, User-Agent 명시
2. 호출 실패·스키마 변화 시 기존 파일 무변경 + 비정상 종료(exit 1)
3. 응답 행수·값 합계 sanity 체크(전월 대비 100배 급변 시 경고 로그 + 해당 월 스킵)
4. `tools/uscensus/tests/` — fixture 기반 unittest(파싱·병합·fail-closed 각 1개 이상)
5. `.github/workflows/update-uscensus.yml` — 매월 5·15·25일 09:00 UTC + workflow_dispatch,
   `permissions: contents: write`, 자기 파일만 add, push 전 `git pull --rebase origin main`

## 수용 기준

- [ ] 실호출로 최근월 데이터 수집 성공(테스트 로그 첨부)
- [ ] watchlist 18개 HS 전부에 대해 state/district×월 시계열 생성
- [ ] unittest 전부 통과, `git diff --check` 클린
- [ ] PR 본문에: 사용한 정확한 데이터셋 경로·변수명·district 코드표 출처·월 지연 실측치
