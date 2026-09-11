# KDEF 진행 체크포인트

패스가 끊겨 다시 불려도 이 파일과 `git log -- argus/kdef` 로 이어서 한다. 같은 일을 두 번 하지 않는다.

## 완료

- [x] `argus/_specs/COMMON.md`·`kdef.md` 정독
- [x] **원문 실측** → `tools/FINDINGS.md` (KIND 업종·종목코드 확인, 계약공시 19건, 정기보고서 4사 II-4)
      핵심: LIG는 상호가 `LIG디펜스앤에어로스페이스`(079550) · 계약상대 4갈래 · 수주표 3갈래(총액형/품목형/잔액형)
- [x] `tools/kdef_lib.py` — kce/kship 도구 import, 페이지 셸, 색, 포맷
- [x] `assets/kdef.css` — kship.css 복사 + 방산 토큰

## 남은 일 (순서)

1. [ ] `kdef_universe.py` — 네 겹 모집단 → `tools/assets/universe.json`
2. [ ] `kdef_contracts.py` — I001 계약 공시 → `tools/assets/contracts.json`
3. [ ] `kdef_reports.py` — 정기보고서 II-4(수주·부문매출·거래처) → `tools/assets/reports.json`
4. [ ] `kdef_scan.py` — 본문 탐색 승격 → `tools/assets/universe_probe.json`
5. [ ] `build_dicts.py` — 계통·부품·계약유형 사전
6. [ ] `kdef_page.py` / `kdef_parts.py` — 허브·회사·커버리지·parts
7. [ ] tests · site.json · `_config.yml` exclude · `.github/workflows/update-kdef.yml` · README/LOGIC/HANDOFF
8. [ ] `/tmp/kdef.done`

## 다음 명령

```sh
cd argus/kdef/tools && python3 kdef_universe.py --write
```
