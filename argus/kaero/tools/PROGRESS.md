# KAERO 진행 체크포인트 — 우주·항공부품 (`argus/kaero`)

패스가 끊겨 다시 불려도 이 파일과 `git log -- argus/kaero` 로 이어서 한다. 같은 일을 두 번 하지 않는다.

## 완료

- [x] `argus/_specs/COMMON.md`·`kaero.md` 정독 · 본보기 코드(kdef/kship/kce) 확인
- [x] **원문 실측 7건** → `tools/FINDINGS.md`
      (아스트 USD/원 분리표 · 한화에어로 수주상황(상세) RSP 원장 · 겸업사 중복계상 ·
       하이즈 캡션 물림 · 켄코아 표 안 통화 혼재 · 케이피 수주표 없음 · `[첨부정정]` 목차 함정)
- [x] `kaero_lib.py` — kce/kship import 층 + 통화 표기 + 영역 팔레트 + `open_sections` + 페이지 셸
- [x] `assets/kaero.css` (kdef 것을 복사, 경로만 kaero)
- [x] `kaero_universe.py` — 네 겹 모집단 **20종목**(④ 탐색 2: 대한항공·아이쓰리시스템)
- [x] `kaero_scan.py` — ④ 탐색 74사. **표 근거(II-4 부문·품목 이름)가 문구 근거를 이기는** 승격 규칙
- [x] `kaero_reports.py` — **통화별** 수주표 · 상세표(계약 원장) · 부문 필터(중복 계상) ·
      영역/계약성격/고객 판정 · 매출처 표 · 연매출 열 · 합계 여러 벌 방어
- [x] `kaero_contracts.py` — I001 얇은 원장(외화 계약금액 통화 보존)
- [x] `build_dicts.py` — 영역 6 · 계약성격 6 · 고객계층 4 · 부품 6/23 · 실루엣 4/영역 25
- [x] `kaero_suppliers.py` — 부품 분류 · 고객 연결(근거 등급 4단)
- [x] `kaero_page.py` — 허브 · 회사 · 커버리지  /  `kaero_parts.py` — 인포그래픽
- [x] `tools/tests` **50건 통과**(픽스처는 DART 원문 절)
- [x] `site.json` · `_config.yml` exclude · `.github/workflows/update-kaero.yml` · `vendor/`
- [x] README.md · LOGIC.md

## 진행 중

- [ ] `kaero_reports.py --collect --force` 재수집(`/tmp/kaero_collect2.log`)
      — `_carry_units` 가 **제목까지** 물려주도록 고친 뒤 전량 다시 읽는 중
- [ ] `kaero_contracts.py --collect` (`/tmp/kaero_con.log`)

## 남은 일

1. [ ] 재수집 끝나면 `--build` → `kaero_suppliers --build` → `kaero_page --all` → `kaero_parts`
2. [ ] HANDOFF.md
3. [ ] 커밋 · `/tmp/kaero.done`

## 다음 명령

```sh
cd argus/kaero/tools
python3 kaero_reports.py --build --n 6 && python3 kaero_contracts.py --build
python3 kaero_suppliers.py --build && python3 kaero_page.py --all && python3 kaero_parts.py
python3 -m unittest discover -s tests
```
