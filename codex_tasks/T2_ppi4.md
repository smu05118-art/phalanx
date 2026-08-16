# T2 — PPI 4개국화: 일본 CGPI · 한국 ECOS · 중국 NBS 수집기

> **먼저 레포 루트 `AGENTS.md`를 읽어라.** 모범 사례: `panoptes/tools/update_tga_target.py`.

## 목적

생산자물가를 미국(기존 BLS, 로컬 수집 중) 외 **일본·한국·중국**으로 확장해, 국가별 "PPI 급등 품목 TOP"과
품목 시계열을 제공할 데이터 기반을 만든다. 인플레이션/원가압력 신호를 산업별로 가장 빨리 잡는 용도.

## 소스별 요구 (2026-08-16 라이브 검증 완료 — 아래 사실 그대로 구현)

### 🇯🇵 일본 — BOJ 기업물가지수(CGPI) [검증: 실다운로드·파싱 성공]
- **`https://www.stat-search.boj.or.jp/info/cgpi_m_en.zip`** — 인증 불요 정적 ZIP(343KB), 내부 CSV 1개
- 와이드 포맷: 1열=계열코드(`PRCG20_xxxxxxxxxx`, 2020년 기준), 2열=통계명, 3열=[그룹]+품목명, 4열~=YYYYMM 월별값.
  **3,042계열** = 국내PPI(품목~소그룹 ~750) + 소비세제외 + 수출물가(엔/계약통화) + 수입물가(엔/계약통화)
  (예: `PRCG20_2200000000` = 국내PPI 총평균, 2026-07=135.8 — 검증됨)
- 계열코드↔품목 매핑: `https://www.stat-search.boj.or.jp/info/PRList.xlsx` (xlsx 파싱은 zipfile+xml stdlib로)
- 수집 범위: **국내PPI 그룹 전 계열** + 수출입물가(엔 기준) 대분류. 발표: 익월 10~13일 08:50 JST, 소급수정 → 최근 6개월 재수집
- 자매파일(선택): `sppi_m_en.zip`(서비스PPI) — 여력 있으면 동일 구조로 추가

### 🇰🇷 한국 — 한국은행 ECOS API [검증: sample키 실호출 성공]
- 통계코드 확정: **`404Y014`**(기본분류 품목 ~525개, P_ITEM_CODE 계층+가중치), `404Y015`(특수분류 33),
  `404Y016`(품목별 최심층 ~2,680행). **404Y014 전 품목을 기본**으로, 404Y016은 용량 봐서 선택
- 형식: REST GET 경로 파라미터(`.../StatisticSearch/{KEY}/json/kr/1/1000/404Y014/M/{시작YYYYMM}/{끝YYYYMM}/...`)
- GitHub Secrets `ECOS_API_KEY`. **키 없으면 KR만 스킵**하고 나머지 국가 정상 진행(전체 실패 금지).
  키 발급은 운영자가 ecos.bok.or.kr 가입 후 즉시 무료
- 발표: 익월 20일경 06:00 KST

### 🇨🇳 중국 — NBS [검증: easyquery는 해외IP 403(WAF) 완전 차단 — 시도하지 마라]
- **easyquery.htm API는 구현 금지**(GitHub 러너=해외IP라 100% 실패. GET/POST·쿠키 무관 403 실측)
- **확정 경로: `https://www.stats.gov.cn/sj/zxfb/` 월별 PPI 보도자료 파싱**(해외 200 OK 실측).
  보도자료 본문에 **41개 분업종 표가 HTML 테이블로 포함** — html.parser 구조 파싱(2026-07분 8/9 발표, 총지수 동비 +3.5% 실파싱 검증)
- 매월 목록 페이지에서 "工业生产者出厂价格" 제목 기사 탐지 → 표 추출 → 41개 업종 동비/환비 저장.
  지수 레벨이 아닌 **동비(%YoY)·환비(%MoM)가 원계열**이므로 스키마에 `yoy`/`mom` 필드로 저장(다른 나라와 필드 구조 다름을 README에 명시)
- 발표: 익월 9~10일 09:30 CST

## 출력 계약

- `data/ppi4/{jp|kr|cn}.json`:
  `{"schema":"ppi4/1","updated":"YYYY-MM-DD","country":"JP","series":{"<코드>":{"name":"철강","name_ko":"철강","unit":"2020=100","m":{"2025-01":103.4,...}}}}`
- 값: 지수 float(소수 1~2자리). YoY는 저장하지 않는다(프론트 계산). 결측 키 생략
- 시리즈 메타에 원어 명칭 + 한국어 번역(`name_ko`) 병기 — 번역은 표준 산업용어로

## 구현 요구

1. `tools/ppi4/fetch_{boj|ecos|nbs}.py` 3개 독립 스크립트 + 공용 유틸 `tools/ppi4/common.py`
2. 각각 독립 실행 가능(한 나라 실패가 다른 나라를 막지 않게 워크플로에서 개별 스텝+`continue-on-error: false`는 커밋 스텝에서만 판단)
3. fixture 테스트: 각 소스 응답 샘플 → 파싱 검증 + fail-closed 검증
4. `.github/workflows/update-ppi4.yml` — 매월 10·15·21일 10:00 UTC + dispatch, 변경된 파일만 커밋, push 전 pull --rebase

## 수용 기준

- [ ] 일본·중국 실데이터 수집 성공(ECOS는 키 없으면 스킵 동작 시연)
- [ ] 3국 파일 스키마 동일성 검증 테스트
- [ ] PR 본문: 시리즈 수, 이력 시작월, 각국 발표일 규칙, NBS 차단 시 폴백 경로 설명
