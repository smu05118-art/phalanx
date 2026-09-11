# KDEF 진행 체크포인트

패스가 끊겨 다시 불려도 이 파일과 `git log -- argus/kdef` 로 이어서 한다. 같은 일을 두 번 하지 않는다.

## 완료

- [x] `argus/_specs/COMMON.md`·`kdef.md` 정독 · **원문 실측** → `tools/FINDINGS.md`
- [x] `kdef_lib.py` · `assets/kdef.css`(+ 인포그래픽 전용 규칙)
- [x] `kdef_universe.py` — 네 겹 모집단 **71종목**(④ 탐색 승격 27 포함) → `assets/universe.json`
- [x] `kdef_scan.py` — 본문 탐색(후보 224 · 승격 27 · 제외 187) → `assets/universe_probe.json`
- [x] `kdef_contracts.py` — I001 계약 공시 → `assets/contracts.json` (352건, 민수 100건 분리)
      · 코스닥 양식(「1. 판매ㆍ공급계약 내용」) 인식 · 정정공시 supersedes
- [x] **공용 버그 수정** `kce_fetch._decode` — 코스닥 거래소공시(rcpNo[8]=='9') EUC-KR 판정.
      깨진 캐시 366건 삭제 후 재수집.
- [x] `kdef_reports.py` — 71사 수집(체계업체 8분기 · 나머지 2분기), 표 5갈래 · 두 줄 머리행 ·
      단위 물림 · 수량 단위 거부 · 본체 표 선택 · 연매출(직전 사업연도 열) → `assets/reports.json`
- [x] `build_dicts.py` — 계통 9 · 계약유형 6 · 부품 11/31 · 실루엣 4/영역 22
- [x] `kdef_suppliers.py` — 부품 분류 42사 · 체계업체 연결 20사(근거 등급) → `assets/suppliers.json`
- [x] `kdef_page.py` — 허브 · 회사 70쪽 · 커버리지
- [x] `kdef_parts.py` — `parts.html` 인포그래픽(실루엣 4종 · 영역 클릭 → 부품 → 회사)
- [x] `tools/tests` 21건 통과 · `site.json` · `_config.yml` exclude · `update-kdef.yml` ·
      `tools/.gitignore` · README/LOGIC/HANDOFF

## 남은 일

1. [ ] 계약 수집 마무리(`kdef_contracts.py --collect` 잔여 회사) → `--build` → `kdef_suppliers/page/parts` 재생성
2. [ ] 계통 '미상' 중 계약명이 빈칸인 정정공시는 원본 계약명을 물려받게(HANDOFF ③)
3. [ ] 부품 분류 정밀화 — 정기보고서 「II-2 주요 제품」 절을 따로 수집해 제품 문구로 분류

## 다음 명령

```sh
cd argus/kdef/tools
python3 kdef_contracts.py --collect && python3 kdef_contracts.py --build
python3 kdef_suppliers.py --build && python3 kdef_page.py --all && python3 kdef_parts.py
python3 -m unittest discover -s tests
```
