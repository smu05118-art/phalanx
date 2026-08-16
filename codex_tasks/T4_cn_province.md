# T4 — 중국 성(省)별 수출입 (MOFCOM 분성 데이터 — 정찰 완료·범위 확정판)

> **먼저 레포 루트 `AGENTS.md`를 읽어라.**

## 정찰 결론 (2026-08-16 실측 — 재정찰 불필요, 이 결론으로 구현)

- **GACC 해관 조회플랫폼(stats.customs.gov.cn) 자동수집은 포기한다.**
  전 도메인이 瑞数 동적 JS 챌린지(curl 412)+해외 IP 차단(실브라우저도 400)+조회당 이미지 캡차.
  캡차·봇차단 우회는 하지 않는다(프로젝트 원칙). 성×HS 정식 교차는 무료로 존재하지 않음을 확인.
- **실현 경로: MOFCOM 상무부 데이터센터(data.mofcom.gov.cn) — 접근 자유(로그인·캡차 없음, 해외 OK).**
  분성(省별) 데이터 제공 범위: ①성별 총 수출입액 ②기전제품(機電産品) 수출입 ③하이테크(高新技術) 수출입
  ④중점 농산물. HS 교차는 아니지만 **광둥 하이테크 수출 가속** 같은 생산권역 신호로 충분히 유효.

## 목적 (조정판)

성별 **총액 + 기전 + 하이테크** 월별 시계열로 생산권역 프록시 기반을 만든다.
표적 활용: 광둥(전자·PCB), 저장(소비재), 푸젠(서버), 장쑤(반도체·광모듈), 쓰촨(노트북) 신호.

## 데이터 소스

- `https://data.mofcom.gov.cn/hwmy/imexmonth.shtml` 계열(월별 수출입) — 분성시(分省市) 표 페이지들
- 구현 첫 단계에서 사이트 내 분성 표들의 실제 URL·표 구조(HTML 테이블/xls 다운로드)를 파악해 PR 본문에 기록
- 발표: GACC 상세와 비슷한 월 하순(전월분). 위안/달러 표기 확인 필수(`currency` 필드)
- 이력: 사이트 제공 범위(보통 수년치 월별 아카이브) 소급 수집

## 출력 계약

- `data/cnprov/monthly.json`:
```json
{"schema":"cnprov/1","updated":"YYYY-MM-DD","currency":"USD",
 "provinces":{"广东":{"name_ko":"광둥","exp_total":{"2025-01":...},"imp_total":{...},
   "exp_hitech":{...},"imp_hitech":{...},"exp_mech":{...},"imp_mech":{...}}}}
```
- 값 월별 정수(만달러→달러 환산 시 계수 명시). 결측 키 생략, window-merge. 1·2월 합산 발표분은
  `"2025-02"`에 합산값 저장 + `notes`에 규칙 명시(월차 계산 시 프론트가 처리)

## 구현 요구

1. `tools/cnprov/fetch_mofcom.py` — stdlib-only, html.parser 구조 파싱(정규식 스크래핑 금지),
   요청 간 2초 간격, 재시도 2회+백오프, fail-closed
2. fixture 테스트(실제 표 HTML 샘플 동봉) + 병합·fail-closed 테스트
3. `.github/workflows/update-cnprov.yml` — 매월 24일 03:00 UTC + dispatch, pull --rebase 후 자기 파일만 커밋
4. GitHub 러너에서 mofcom.gov.cn 접근성은 구현 중 실측 — 차단 시 스케줄 끄고 dispatch 전용 + README 명시

## 수용 기준

- [ ] 31개 성 × (총액·기전·하이테크) 최소 12개월 실데이터
- [ ] PR 본문: 사용한 정확한 페이지 URL들, 표 구조, 통화·단위, GACC 차단 정찰 요약(위 결론 재기록)
- [ ] 러너 접근성 실측 결과
