# KGRID 진행 체크포인트

패스가 끊겨 다시 불려도 이 파일과 `git log -- argus/kgrid` 로 이어서 한다. 같은 일을 두 번 하지 않는다.

## 완료

- [x] `argus/_specs/COMMON.md`·`kgrid.md` 정독
- [x] **원문 실측** — 엘에스일렉트릭 010120(롤포워드 12열·단위 억원·종속회사별 표),
      HD현대일렉트릭 267260(총액−기납품 1행·매출처 실명 NextEra 15.9%·사우디전력청 5.0%),
      일진전기 103590(**단위 천USD**·국내/해외 분리) → `tools/FINDINGS.md`
- [x] **공용 층 수정** `kship_parse._UNIT_TABLE` — `천USD`·`백만USD`·`천EUR` 표기를 넣고
      원화 단위가 병기된 캡션은 원화로 판정. 일진전기 잔고가 1000배 작아지던 것을 막았다(FINDINGS §5)
- [x] `kgrid_lib.py`(제품군 9슬롯 색·잔고 성격·통화 보존 표기·커버리지 fail-closed) · `assets/kgrid.css`

## 남은 일

1. [ ] `kgrid_universe.py` — 모집단(업종 4갈래 + 제품 어휘 + 지정 + 탐색)
2. [ ] `kgrid_scan.py` — 본문 탐색으로 부품사 승격
3. [ ] `kgrid_reports.py` — II-4 수주표·매출처·부문매출 수집
4. [ ] `kgrid_contracts.py` — I001 계약 공시
5. [ ] `build_dicts.py` — 제품군·수요처 분류 사전 + 전력망 계통도 영역
6. [ ] `kgrid_page.py` — 허브·회사·커버리지
7. [ ] 테스트·`site.json`·`_config.yml`·`update-kgrid.yml`·README/LOGIC/HANDOFF

## 다음 명령

```sh
cd argus/kgrid/tools
python3 kgrid_universe.py --write
```
