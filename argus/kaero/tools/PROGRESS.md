# KAERO 진행 체크포인트 — 우주·항공부품 (`argus/kaero`)

패스가 끊겨 다시 불려도 이 파일과 `git log -- argus/kaero` 로 이어서 한다. 같은 일을 두 번 하지 않는다.

## 완료 — 웨이브 종료

- [x] `argus/_specs/COMMON.md`·`kaero.md` 정독 · 본보기 코드(kdef/kship/kce) 확인
- [x] **원문 실측 7건** → `tools/FINDINGS.md`
      (아스트 USD/원 분리표 · 한화에어로 수주상황(상세) RSP 원장 · 겸업사 중복계상 ·
       하이즈 캡션 물림 · 켄코아 표 안 통화 혼재 · 케이피 수주표 없음 · `[첨부정정]` 목차 함정)
- [x] `kaero_lib.py` · `assets/kaero.css` · 페이지 셸 · `open_sections`(정정본 폴백)
- [x] `kaero_universe.py` — 네 겹 모집단 **20종목**(④ 탐색 2: 대한항공·아이쓰리시스템)
- [x] `kaero_scan.py` — ④ 탐색 후보 74사. **표 근거가 문구 근거를 이기는** 승격 규칙
- [x] `kaero_reports.py` — 통화별 수주표 · 상세표 계약 원장 · 부문 필터 · 영역/성격/고객 ·
      매출처 표 · 연매출 열 · 합계 여러 벌 방어 · **커버리지 분모의 범위 일치**
- [x] `kaero_contracts.py` — I001 원장 **237건**(외화 통화 보존)
- [x] `build_dicts.py` — 영역 6 · 계약성격 6 · 고객계층 4 · 부품 6/23 · 실루엣 4/영역 25
- [x] `kaero_suppliers.py` — 부품 분류 16사 · 고객 연결 17사(근거 등급 4단)
- [x] `kaero_page.py` — 허브 · 회사 20쪽 · 커버리지  /  `kaero_parts.py` — `parts.html`
- [x] 수집 완료 — 6분기 · 분기레코드 **109건**(실패 0)
- [x] `tools/tests` **50건 통과**(픽스처는 DART 원문 절)
- [x] `site.json` · `.github/workflows/update-kaero.yml` · `vendor/`
      (`_config.yml` 은 **건드리지 않는다** — 감독 메모 2. `argus/*/tools/` glob 이 덮는다)
- [x] README.md · LOGIC.md · HANDOFF.md · `/tmp/kaero.done`

## 남은 일 (HANDOFF ③ 에 자세히)

1. [ ] (맥미니 몫) 공용 층 2건 — `pick_report` 의 `[첨부정정]` 문제, 표 복구 3함수의 kdef 중복.
       이 웨이브는 고치지 않고 `tools/FINDINGS.md` §8 에 근거와 함께 적었다.
2. [ ] 대한항공 매출표(부문 아래 총매출액/연결조정액/순매출액 3줄)를 읽어 커버리지 분모 만들기
3. [ ] 수주표 부문 이름 ↔ 매출표 부문 이름 사전(KAI 커버리지의 범위 오차)
4. [ ] 「II-2 주요 제품」 절을 따로 수집해 영역 `기타·미상` 줄이기
5. [ ] 매출처 표 각주(`(주1) …는 …입니다`) 파싱 → 고객 약칭을 등급 B로

## 재현 명령

```sh
cd argus/kaero/tools
python3 build_dicts.py --write && python3 kaero_universe.py --write
python3 kaero_contracts.py --collect && python3 kaero_contracts.py --build
python3 kaero_reports.py --collect --n 6 && python3 kaero_reports.py --build --n 6
python3 kaero_suppliers.py --build && python3 kaero_page.py --all && python3 kaero_parts.py
python3 -m unittest discover -s tests
```
