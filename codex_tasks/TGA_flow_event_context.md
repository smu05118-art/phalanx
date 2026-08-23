# Panoptes TGA 공식 이벤트 컨텍스트 — 로컬 빌더 반영 필요

## 목적

- `WALCL−TGA−RRP` 산식과 기존 신호등은 그대로 둔다.
- 추정세 납부일의 직접 회계효과(`TGA↑·준비금↓·Net Liquidity↓`)와
  `예정된 계절적 drain`이라는 해석을 분리한다.
- 재무부 분기말 현금잔고 가정은 상한선이 아닌 동일 기준일 참고값으로만
  비교한다.
- 가정 상회만으로 방출을 확정하지 않고 실제 TGA 감소 또는 DTS 순인출이
  확인될 때만 `RELEASE_CONFIRMED`로 전환한다.

## 신규 자립 파일

- `data/tga-flow-events/current.json`: 공개용 공식 일정·근거·해석 계약
- `tools/tga-flow-events/update_tga_flow_events.py`: stdlib 기반 fail-closed
  공식 HTML 수집기
- `tools/tga-flow-events/tests/`: 픽스처 단위 테스트와 브라우저 계약 검증
- `.github/workflows/update-tga-flow-events.yml`: 주 1회 및 수동 갱신
- `panoptes/tga_flow_events.js`: fail-closed 검증·상태 해석 모듈
- `panoptes/tga_flow_events_bridge.js`: 기존 v2 렌더러를 감싸는 표시 브리지
- `panoptes/tests/tga_flow_events_contract.test.mjs`: 계약·상태·보안 회귀 테스트

이 파일들은 생성 산출물 파일을 직접 수정하지 않는다.

## 데이터 출처·주기·계약

공개 수집기는 다음 6개 공식 HTML을 정확한 HTTPS URL·호스트
allowlist로만 읽는다.

- IRS Publication 509 (2026):
  `https://www.irs.gov/publications/p509`
- IRS 2026 2·3·4분기 Tax Calendar:
  `https://www.irs.gov/businesses/small-businesses-self-employed/second-quarter-tax-calendar`,
  `https://www.irs.gov/businesses/small-businesses-self-employed/third-quarter-tax-calendar`,
  `https://www.irs.gov/businesses/small-businesses-self-employed/fourth-quarter-tax-calendar`
- U.S. Treasury Quarterly Refunding Statement (260805):
  `https://home.treasury.gov/news/press-releases/sb0590`
- Federal Reserve TGA 준비금 메커니즘:
  `https://www.federalreserve.gov/monetarypolicy/bsd-background-202008.htm`

주 1회 자동 실행하며 `workflow_dispatch`도 제공한다. 파싱·합의·해시·
스키마 검증을 모두 통과한 경우에만 원자적으로 교체하고, 실패하면
기존 last-known-good를 보존한다. 의미가 같으면 수집 시간만으로 커밋을
만들지 않는다.

출력 계약은 `data/tga-flow-events/current.json` / schema
`atlas-panoptes-tga-event-context-v1`이다. 공개 산출물에는 페르소나,
내부 GS 근거, 로컬 경로가 없다. Atlas 내부의 8종 원문·PDF 불변
아카이브와 비공개 Persona v2 렌즈는 별도 계층으로 유지한다.

## 로컬 Panoptes producer 변경

`panoptes/index.html`을 생성하는 원본에서 `liq_charts.js` 다음, `app.js` 전에
아래 두 줄만 추가한다.

```html
<script src="tga_flow_events.js"></script>
<script src="liq_charts.js"></script>
<script src="tga_flow_events_bridge.js"></script>
<script src="app.js"></script>
```

현재 배포 산출물의 기존 순서는 `tga_target.js → liq_charts.js → app.js`다.
따라서 실제 변경은 `liq_charts.js`와 `app.js` 사이에 두 신규 모듈 중
브리지를 두고, 검증 모듈은 `liq_charts.js`보다 앞에 두는 것이다.

정확한 최종 순서:

```html
<script src="tga_target.js"></script>
<script src="tga_flow_events.js"></script>
<script src="liq_charts.js"></script>
<script src="tga_flow_events_bridge.js"></script>
<script src="app.js"></script>
```

브리지는 다음 동작만 추가한다.

1. `liquidity2.json.updated`가 현재 확인일보다 미래면 유동성 화면을 품질
   차단한다.
2. 공식 이벤트 계약을 검증한 뒤 기존 `renderLiq2` 결과 아래에 네 층의
   해석 카드(기계효과·계절성·재무부 대응·분기말 가정/방출)를 붙인다.
3. 기존 TGA 카드의 색을 바꾸지 않고 설명만 “이벤트 맥락 별도 표시”로
   정정한다.
4. 공식 계약이 만료되거나 로드에 실패하면 이벤트 해석만 보류하고 임의의
   일정·수치로 대체하지 않는다.

## 검증

```sh
python3 -m unittest discover -s tools/tga-flow-events/tests -p 'test_*.py'
python3 tools/tga-flow-events/update_tga_flow_events.py \
  --output data/tga-flow-events/current.json
node tools/tga-flow-events/tests/verify_frontend_contract.mjs
node --check panoptes/tga_flow_events.js
node --check panoptes/tga_flow_events_bridge.js
node panoptes/tests/tga_flow_events_contract.test.mjs
node panoptes/tests/tga_target_contract.test.mjs
git diff --check
```

공개 계약에는 내부 GS 보고서나 Persona v2 근거를 넣지 않는다. 매크로
페르소나 한줄 렌즈는 Atlas 비공개 enrichment에서만 관리한다.
