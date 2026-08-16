# T3 — 14개국 세관 무역통계 발표 캘린더

> **먼저 레포 루트 `AGENTS.md`를 읽어라.**

## 목적

각국 세관 월별 무역통계의 **잠정/확정 발표 일정**을 규칙+공식 캘린더로 데이터화한다.
"내일 대만 잠정치 발표 → 관련 카드 갱신 대기" 같은 흐름을 대시보드 캘린더에 얹기 위한 기반.

## 대상 14개국 — 검증된 규칙 (2026-08-16 조사 완료, 이 표 기반으로 구현)

| 국가 | 규칙(전부 M+1 기준) | 근거 소스 |
|---|---|---|
| 🇰🇷 한국 | 잠정 1·11·21일(직전 순보) + 확정 15일경 | customs.go.kr 보도자료 목록 |
| 🇯🇵 일본 | 속보 17~21일 08:50 JST · 확보 하순 · 당월 上中旬속보 당월 말 · 확정 익년 3월 | customs.go.jp/toukei/shinbun/happyou.htm (공표예정 페이지 — **파싱 대상**) |
| 🇺🇸 미국 | FT-900 4일± 08:30 ET (2026: 6월분→8/4, 7월분→9/3, 8월분→10/6) | census.gov/foreign-trade/reference/release_schedule.html (**파싱 대상**) |
| 🇨🇦 캐나다 | **미국과 동일일** 08:30 ET | www150.statcan.gc.ca Daily 캘린더 |
| 🇨🇳 중국 | 총액 7~9일 · 상세(품목×국가) +열흘가량 | GACC 연도별 Release Calendar (TLS self-signed — curl -k) |
| 🇹🇼 대만 | 8~9일 16:00 (보도자료 말미 '下次發布日期' 명시 — 실측 1/9→2/9) | mof.gov.tw/htmlList/103 |
| 🇧🇷 브라질 | 월간확정 ~4영업일 (7월분→8/6 실측) + 주간 | balanca.economia.gov.br cronograma (TLS 체인 — curl -k) |
| 🇲🇾 말레이시아 | ~20일 (12월분→1/20 실측) | dosm.gov.my release-calendar (TLS 체인) |
| 🇮🇩 인도네시아 | **2025-06-02부터 체계 변경**: 잠정 폐지, 매월 첫 영업일에 M-2월 확정만 (7월분→9/1) | bps.go.id (403 봇차단 — 아래 참조) |
| 🇮🇳 인도 | 13~15일 ±2일 변동 | commerce.gov.in — **폴링 설계** |
| 🇲🇽 멕시코 | oportuna 27일경 · 확정 M+2 초순 | INEGI 캘린더 (JS 로딩 — 연도별 PDF 경로 사용) |
| 🇵🇭 필리핀 | 말 영업일 (3월분→4/30, 4월분→5/29 실측) | psa.gov.ph (403 봇차단) |
| 🇹🇭 태국 | 20~27일 유동 | tradereport.moc.go.th — **폴링 설계** |
| 🇨🇷 코스타리카 | 고정 캘린더 없음 | procomer.go.cr — **폴링 설계** |

주의사항(전부 실측): 인니는 옛 '15일 잠정' 규칙을 쓰면 틀린다 / 태국·코스타리카·인도 3국은 규칙 계산이 아니라
**폴링 타입**(`"type":"poll"`)으로 스키마에 표기 / 한국 발표일이 휴일이면 익영업일 / 중국 1·2월 합산 발표.
403 봇차단 소스(BPS·PSA)는 우회하지 말 것 — 규칙만 하드코딩하고 `verified_against`에 과거 실측일을 남겨라.

## 출력 계약

- `data/tradecal/schedule.json`:
```json
{"schema":"tradecal/1","updated":"YYYY-MM-DD",
 "countries":{"KR":{"name_ko":"한국","rules":[
    {"type":"prelim","rule":"day:1,11,21","desc_ko":"관세청 잠정(순보)"},
    {"type":"final","rule":"biz_day_around:15","desc_ko":"월간 확정"}],
   "source":"https://...","verified_against":["2026-06-15","2026-07-15"]}, ...},
 "upcoming":[{"date":"2026-08-18","cc":"TW","type":"final","label_ko":"대만 26.06 확정치"}, ...]}
```
- `upcoming`은 **향후 60일 계산 결과**(규칙→구체 날짜, 주말·각국 공휴일 보정). 공휴일 테이블은
  `data/tradecal/holidays.json`에 최소한(신정·설·국경일 수준)으로 동봉하고 한계를 명시
- 규칙 문자열 문법: `day:1,11,21` / `biz_day:5`(n번째 영업일) / `biz_day_around:15` / `weekday_after:day15,Tue` 등 —
  파서와 함께 정의하고 README에 문법 문서화

## 구현 요구

1. `tools/tradecal/build_schedule.py` — 규칙 정의(코드 내 상수)→검증→upcoming 60일 계산→JSON
2. 공식 캘린더 페이지가 있는 국가(일본·미국 최소 2국)는 fetcher로 실제 일정을 받아 규칙 계산과 대조,
   불일치 시 공식 페이지 값을 우선하고 로그
3. 테스트: 규칙 파서 단위테스트 + 과거 발표일 역검증 fixture
4. `.github/workflows/update-tradecal.yml` — 매주 월 07:00 UTC + dispatch (upcoming 재계산), pull --rebase 후 push

## 수용 기준

- [ ] 14국 전부 rules + 최소 2개 과거 발표일 역검증 기록
- [ ] upcoming 60일 산출이 8월 실제(예: 대만 8/18 확정, 중국 8/20 확정, 미국 8/27 잠정 등)와 부합
- [ ] PR 본문: 국가별 근거 URL 표
