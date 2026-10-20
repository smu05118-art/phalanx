# NeoCloud GPU spot tracker — 261020

Mac Studio Codex Astra의 격리 구현을 기반으로 `ui/patch.js`와 `ui/patch.css`에 독립 모듈/스타일을 추가했다. 생성 HTML, data_ai.js, manifest, offline HTML, neocloud_charts.js는 수정하지 않았다. Studio 작업 자체는 배포·커밋·인증 변경·웹 조회를 수행하지 않았고, 통합 단계에서 별도 교차감사와 실제 브라우저 검증을 거쳤다.

## 증거와 초기값

유일한 관측 출처는 입력 번들의 `user_chart_261020.jpg`다. 원본 표시 기간은 **260919–261020**, 캡처/Atlas 날짜는 **261020**이다. `source_type=user_supplied_chart_image`, `currency=USD`, `unit=USD/GPU-hour`, `cadence=daily_avg`를 보존했다. 공식 Nebius API나 검증된 실시간 피드가 아니다. 이미지의 수치 자체는 독립 검증하지 않았다.

| 제품 | 261020 정확한 인쇄값 |
|---|---:|
| B300 | $8.16 |
| B200 | $3.92 |
| H200 | $1.87 |
| H100 | $0.79 |
| RTX PRO 6000 | $1.18 |

초기 데이터에는 위 끝점 5개만 있다. 중간 일별 값, 시작일 가격, 평균 계산의 기초 데이터는 추출하지 않았다. 초기 차트는 관측점만 표시하며 과거 추세선을 만들어내지 않는다. 테스트의 합성 관측값은 테스트 중에만 사용한다.

## 통합과 렌더링

코디네이터가 기존 저장소 루트에 반환 파일을 상대 경로대로 반영하거나 `integration.patch`를 적용한다. `index.html`에 스크립트를 추가하지 않는다. 기존 UI 패치 로더가 두 UI 파일을 로드해야 하며 같은 origin에서 `data/neocloud_spot/history.json`을 제공해야 한다. 로컬 file:// 열기는 지원하지 않는다.

현재 번들의 `renderAI2`는 `#main` 아래 `.nc`에 NeoCloud를 렌더링한다. 모듈은 `renderAI2`/`renderNeocloud`의 반환값과 호출 인자를 보존해 후속 마운트를 예약한다. DOM 관찰은 지연 로딩과 직접 재렌더도 처리한다. `.nc`의 첫 `.nc-panel`(회사 개요) 뒤에 삽입하며 긴 방법론 앞에 위치한다. 동일 루트에 패널 하나만 생성하고 제거된 패널의 Chart.js 인스턴스를 해제한다. 원본 렌더러가 이 DOM 계약을 바꾸면 위치 선택자를 재검토해야 한다.

각 제품의 마지막 비누락 관측값과 해당 날짜·증거 등급을 카드에 표시한다. 기본 범위는 전체 관측이며 날짜는 시간순이다. 텍스트 제품명과 서로 다른 색을 함께 사용한다. 표에는 모든 날짜·가격·불확실성·출처가 있다. 사람에게 보이는 날짜는 YYMMDD다.

Chart.js가 있으면 외부 추가 로드 없이 사용한다. 없거나 생성에 실패하면 inline SVG로 대체한다. 추정값이 들어오면 SVG 오차막대를 사용한다. 하루보다 큰 간격이나 누락값은 선으로 연결하지 않으며 정확/추정 경계도 연결하지 않는다. 데이터가 전부 누락이면 관측값 없음 상태를 표시한다. 테마 변경 시 Chart.js를 다시 그리며 CSS는 패널 범위로 한정한다. 모바일 카드 배치와 가로 스크롤 관측 표를 제공한다.

fetch는 15초 제한과 동시 요청 공유를 사용한다. HTTP/파싱/스키마/중복 충돌 실패는 `GPU spot 데이터 미로드`와 재시도 버튼으로 표시하고 다른 NeoCloud 콘텐츠는 유지한다. 실패 응답은 캐시하지 않는다. 성공 데이터는 페이지 수명 동안 캐시하므로 파일 업데이트 확인은 페이지 새로고침으로 한다. 값이나 HTML을 네트워크 오류 대체 데이터로 만들어 넣지 않는다.

## 데이터 계약과 업데이트

최상위 필드는 `schema_version: 1`, `currency: USD`, `unit: USD/GPU-hour`, `cadence: daily_avg`, `observations`다. 스냅샷도 같은 형식이며 새 관측만 담아도 된다. 알 수 없는 필드는 거부한다.

관측 필드:

- `product`: B300 / B200 / H200 / H100 / RTX PRO 6000 중 하나.
- `effective_date`: ISO 날짜. 출처 기간 안에 있어야 한다.
- `price`: 유한한 비음수 숫자 또는 null/생략. bool과 숫자 문자열은 거부한다.
- `quality`: `exact_printed_label`, `approximate_from_chart`, `missing` 중 하나.
- `uncertainty`: 정확값/누락은 null. 추정값은 USD/GPU-hour 기준 양의 절대 ±불확실성 숫자 필수.
- `provenance`: `source_type`, `source_file`(경로 없는 이미지 파일명), `source_start`, `source_end`(ISO), `captured_date`, `atlas_date`(YYMMDD). 출처 기간 종료 ≤ 캡처 ≤ Atlas 날짜여야 한다.

가격 null/생략은 `quality=missing`, `uncertainty=null`만 허용하며 null로 정규화한다. 날짜가 없으면 실패한다. 미관측 날짜는 자동 생성하지 않는다. 같은 제품/날짜의 가격·등급·불확실성·모든 provenance가 같을 때만 중복을 제거한다. 누락값을 실제 값으로 덮어쓰는 것, 다른 출처로 교체하는 것, 가격 수정도 충돌로 거부한다. 정정은 이 append CLI 밖에서 별도 검토해야 한다.

저장 순서는 effective_date, product이고 JSON 키 정렬·UTF-8·개행을 고정한다. 수치가 같은 정수/실수 표현(`1`, `1.0`, `-0.0`)은 하나의 JSON 표현으로 정규화한다. 입력/출력은 5 MiB 이하로 제한한다. Python JSON 읽기는 중복 키도 거부한다. 업데이트는 대상의 정규화된 절대경로별 프로세스 간 락으로 read→merge→compare→replace 전 구간을 직렬화한다. 모든 검증을 마친 다음 같은 디렉토리 임시 파일에 쓰고 flush/fsync 후 os.replace한다. 실패 시 기존 파일은 보존하고 임시 파일을 제거한다. `--check`는 데이터 디렉토리/파일 생성이나 기존 파일 변경을 하지 않는다.

```sh
python3 tools/update_neocloud_spot.py --check --data data/neocloud_spot/history.json --snapshot snapshot.json
python3 tools/update_neocloud_spot.py --data data/neocloud_spot/history.json --snapshot snapshot.json
```

이 CLI는 주어진 JSON만 검증·병합한다. 관측의 실제 출처와 추정 불확실성의 적정성은 운영자가 원본 이미지와 대조해야 한다. API·수집 스케줄은 추가하지 않았다.

## 검증 결과 — 261020

반환 `output/` 또는 통합 저장소 루트에서 실행:

```sh
python3 -m unittest -v tools/tests/test_update_neocloud_spot.py
python3 tools/update_neocloud_spot.py --check --data data/neocloud_spot/history.json
node --check ui/patch.js
node tools/tests/test_neocloud_spot_dom.cjs
```

- Python unittest: **29개 통과**. 정상 병합, 정렬, 값/출처/등급 중복 충돌, 숫자 표현 정규화, 동시 고유 append 보존, 동시 상충 append fail-closed, UI와 일치하는 출처 파일명 길이, 멱등성, 잘못된 계약, null/생략, check-only 무변경, validation/replace 실패 시 기존 파일 보존을 포함한다.
- 데이터 check: **CHECK OK: 5 observations**.
- JavaScript 구문 검사: **통과**.
- 경량 DOM/static 계약: **13개 통과**. 정확한 다섯 렌더 문자열, 삽입 위치, SVG, Chart.js 생성/해제 mock, 실패→재시도, 중복 마운트, 출처 충돌 차단, 누락 날짜 간격, 추정 불확실성 표시를 포함한다.
- 통합 patch 적용 검사와 공백 검사: **통과**. 반환 파일과 패치 적용 결과의 바이트 일치를 확인했다.

통합 후 실제 Chrome·Chart.js 4.4.1로 desktop/mobile, dark/light, 실제 AI/NeoCloud 탭을 검증했다. 단일 관측일 축은 261019–261021, 가격축은 0–10으로 제한되며 카드 5개·출처·재렌더/해제·패널 가로 overflow 없음이 확인됐다. 배포 후 라이브 Pages 스모크는 별도로 수행한다.

Studio 원본 영수증·`SHA256SUMS`·`integration.patch`는 worker 증거로 별도 보존한다. 단일일 축, 프로세스 간 동시 쓰기, 숫자 표현 정규화 보강으로 최종 통합 파일의 SHA는 Studio 원본 SHA와 다르며 배포 영수증에서 별도로 산출한다.
