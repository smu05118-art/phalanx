# 앙상블(composite_preview.html)에 리서치 페이지 링크 추가 — 로컬 생성기 반영 필요

작성 2026-10-13 · 대상: 맥스튜디오(kioxia)의 composite_preview 생성기 (이 레포에 없음)

## 배경
- `research/<id>/` 에 종목별 자동 갱신 나우캐스트 페이지가 있다: `research/mjc/`, `research/jem/`, `research/tpro/` (목록: `research/index.html`).
- 팔랑크스 본문(index.html)은 `ui/patch.js`의 `RESEARCH` 맵으로 회사 상세 상단에 링크를 이미 노출한다.
- 앙상블은 생성기가 데이터를 박아 만드는 산출물이라 이 레포에서 고치면 다음 생성 때 사라진다 → 생성기에서 반영해야 한다.

## 요청 (계약)
1. 생성기가 회사 카드를 만들 때 `research/<id 소문자>/index.html` 파일이 레포에 존재하면
   회사 상세의 링크 줄(`공식 IR` · `사업·제품` · `앙상블` · `Phalanx 허브` 옆)에 **`리서치 나우캐스트 ↗`** 를 추가한다.
   - href: `research/<id 소문자>/` (레포 루트 기준 상대경로)
   - 현재 대상 id: `MJC`, `JEM` (Technoprobe는 앙상블 카드가 없으면 생략)
2. 존재 여부를 파일 시스템으로 판정하므로 이후 `research/<id>/` 폴더만 추가하면 자동 노출된다.
3. 검증: 생성 후 `composite_preview.html#c=MJC` 에서 링크가 보이고 `research/mjc/` 로 이동하는지 확인.

## 참고
- 엔진: `research/nowcast.js` (inputs.json: lag · fy_end_month · ports · source=comext · guidance · consensus · forecast_log)
- Technoprobe 프록시 데이터: `data/comext/it_90309000.json` (`.github/workflows/update-comext.yml`이 주 2회 갱신)
