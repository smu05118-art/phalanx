# KNUKE 진행 체크포인트 — 원자력·발전기자재 (argus/knuke)

패스가 끊겨 다시 불려도 이 파일과 `git log -- argus/knuke` 로 이어서 한다. 같은 일을 두 번 하지 않는다.

## 축 (원문에서 확인한 것 — `_specs/knuke.md`)
- **발전원(domain)**: 원자력·화력·신재생·송변전·기타산업설비
- **공급 계층(tier)**: 주기기·보조기기·계측제어·설계엔지니어링·정비O&M·검사방사선·해체방폐물·기자재공급
- **발주 성격(party)**: 관급(한수원·한전·발전5사) · 민간IPP · 해외(EPC 하도·직수출)
- 차별점: II-4 수주표에 **발주처 실명·사업명·계약기간**이 행마다 있다(한전기술 23행·한전KPS) →
  '호기별 타임라인'·'발주처 집중도'를 만들 수 있다(조선의 익명 선주 문제가 없다).

## 완료
- [x] `_specs/COMMON.md`·`knuke.md`·scout_tools(probe/contracts)·kdef 본보기 정독

## 진행 중 / 남은 일
1. [ ] `knuke_lib.py` · `assets/knuke.css`(kdef.css 복제) · vendor/chart · site.json · .gitignore
2. [ ] `build_dicts.py` — 발전원 9 · 공급계층 · 부품 · 발전소 SVG
3. [ ] `knuke_universe.py` — 모집단 ①KIND ②지정 ③탐색 ④제외
4. [ ] `knuke_scan.py` — II절 본문 탐색(한수원·원전·발전소 언급) 승격
5. [ ] `knuke_contracts.py` — I001 단일판매공급계약 (발주처 관급/해외 갈래)
6. [ ] `knuke_reports.py` — II-4 수주상황(도급형·표준형·롤포워드) + 발주처·사업명·계약기간 행 + 부문매출
7. [ ] `knuke_suppliers.py` — 공급계층 분류 · 발주처/주기기사 연결
8. [ ] `knuke_page.py` — 허브·회사·커버리지 (+ 호기별 타임라인)
9. [ ] `knuke_parts.py` — 발전소 단면 인포그래픽
10. [ ] `tools/tests` · `.github/workflows/update-knuke.yml`(concurrency kship-dart) · `_config.yml` exclude
11. [ ] README/LOGIC/HANDOFF · site.json 공개 · `/tmp/knuke.done`

## 다음 명령
```sh
cd argus/knuke/tools
python3 build_dicts.py --write && python3 knuke_universe.py --write
python3 knuke_scan.py --scan && python3 knuke_universe.py --write
python3 knuke_contracts.py --collect && python3 knuke_contracts.py --build
python3 knuke_reports.py --collect --n 8 && python3 knuke_reports.py --build
python3 knuke_suppliers.py --build && python3 knuke_page.py --all && python3 knuke_parts.py
python3 -m unittest discover -s tests
```
