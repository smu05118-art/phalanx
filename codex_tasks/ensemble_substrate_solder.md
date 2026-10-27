# 앙상블(composite_preview.html) 기판 섹터 + 솔더볼 묶음 — 로컬 생성기 반영 필요

작성 2026-10-21 · 갱신 2026-10-27 · 대상: 맥스튜디오(kioxia)의 composite_preview 생성기 (이 레포에 없음) · 상태: 요청(데이터 원천 레포 반영 완료)

## 배경
- 관측소(`DATA.observatory`)는 섹터가 rack·mlcc 둘이고, 화면의 섹터 선택 목록(`#scSector`)과 머리 숫자("랙 N사 · MLCC N사")가 생성기 HTML에 박혀 있다.
- 기판 섹터를 셋째로 넣고, 섹터와 회사 사이에 묶음(bundle)·제품선(line) 층을 둔다. 첫 묶음은 솔더볼.
- 솔더볼 제품선 셋은 수요처가 다르다: SB(151–760µm)는 메모리·로직 BGA 패키지, MSB(≤150µm)는 FC-BGA 기판 범프·HDD, CSB(Cu 코어)는 모바일 AP PoP·2.5D. HBM 적층 마이크로범프는 도금(Sn-Ag)이라 볼 수요에서 제외.

## 요청 (계약)
1. **섹터 등록부** `observatory.sectors[]` = `{id, label, bundles:[{id, label, lines:[{id, label}]}]}`.
   - `#scSector` 옵션과 머리 숫자를 등록부에서 생성한다(하드코딩 제거). `counts`는 섹터 id별.
   - `schema_version` 2.
2. **회사 행 신규 필드** (기존 필드는 그대로)
   - `bundle`: 예 `solder_ball` · `lines`: 예 `["SB","MSB","CSB","PF"]`
   - `entity_scope`: `consolidated` | `standalone` | `segment:<이름>`
   - `aggregate`: 묶음 합계 포함 여부(bool) · `observability`: `monthly` | `quarterly` | `none`
3. **솔더볼 묶음 행**
   | id | ticker | entity_scope | aggregate | observability | group | 비고 |
   |---|---|---|---|---|---|---|
   | DUKSAN_HM | 077360.KQ | standalone | true | quarterly | duksan | 연결의 덕산넵코어스(방산)·덕산에테르씨티(가스용기) 제외. 연결 수주잔고는 자회사 몫이라 orders 축에 쓰지 않음 |
   | MI_SMBU | 5286.KL | segment:SMBU | true | quarterly | mi_technovation | Bursa 분기 세그먼트(RM)가 1차. 2026-10-28 SGX 상장 Mi Material 공시(US$)는 대조용 |
   | SHENMAO | 3305.TW | consolidated | false | monthly | shenmao | 大瑞(Daruei) BGA볼 포함. 금속가 반영이 커서 선행 보조 |
   | MKE | 033160.KQ | consolidated | false | quarterly | mke | 볼 비중 2.9%(2025), 금값 전가 지배 → 인접 |
   | SENJU · NMM · INDIUM_FUKUDA | — | — | false | none | — | 관측값 없음. 화면에 "미관측" 칩으로만(0으로 그리지 않음) |
4. **엣지** `edges[]` = `{from, to, line, kind: supply|demand|cost, grade: A|B, source_urls, note}`
   - 공개 산출물에는 A(공시·IR·투자설명서 확인)와 B(공개 정황, 사명 미기재)만 쓴다.
   - 출처 없는 엣지는 공개 산출물에 넣지 않는다. 현재 엣지와 `source_urls`:
     | from → to | line | grade | source_urls |
     |---|---|---|---|
     | DUKSAN_HM → 삼성전자 · SK하이닉스 · Amkor | SB | A | https://www.dshm.co.kr/IR_Reference/IR_Report/2026/DSHM_2026_2Q_IR_KR.pdf (p.3 회사개요 「고객사」, p.10 제품×고객 매트릭스) |
     | DUKSAN_HM → 글로벌 A사 | CSB | A | https://www.dshm.co.kr/IR_Reference/IR_Report/2026/DSHM_2026_2Q_IR_KR.pdf (p.4·p.9 「글로벌 A社」, p.10 「CSB 단일고객」) |
     | MI_SMBU → 익명 고객 X(프리미엄 가전 24%)·Y(AI 칩·네트워킹 18%)·Z(NAND 16%) | SB·MSB | A | https://drwealth.com/mi-material-ipo-strong-numbers-and-strong-ipo-candidate/ (Mi Material SGX 투자설명서 요약) |
     | 삼성전기(FC-BGA) → DUKSAN_HM | MSB | B | https://www.dshm.co.kr/IR_Reference/IR_Report/2026/DSHM_2026_2Q_IR_KR.pdf (p.8 「핵심고객사인 국내 S社의 Full Capa 수혜」 — 사명 미기재, 국내 FC-BGA 기판사 중 S社는 삼성전기뿐이라는 추정. 화면에 "추정" 표기) |
5. **누출 차단**: 생성기 입력에서 visibility 값이 private 인 항목과 grade C 엣지는 공개 산출물에 쓰지 않는다. 레포의 `tools/tests/test_private_leak.py` 가 쓰는 마커 문자열(그 파일 참조)이 공개 산출물에서 발견되면 빌드를 실패시킨다. 로컬 가정 파일은 레포 밖(`~/phalanx-private/`)에 둔다.
6. **관측 축**(기존 6축 재사용) 원천
   - orders: 고객 FC-BGA 증설 공시(DART 신규시설투자), 대만 FC-BGA 월매출(data_tw 3037·3189·8046)
   - sales: **DUKSAN_HM = `data/solder_ball/077360.json` 의 `quarterly[].revenue`·`export`·`domestic`**(백만원, 하이메탈 부문 분기 단독값 — DART 누계 차분, IR 별도 매출과 9개 분기 일치). MI_SMBU 세그먼트, 신마오 월매출
   - supply: **같은 파일 `quarterly[].util_pct`**(분기 가동률 = 실제시간 차분 ÷ 가동가능시간 차분)와 `production_cost`(제조원가 기준 생산실적). Mi Material 라인 수·가동률(투자설명서)
   - price: 정기보고서에는 가격변동 표가 없다(서술만 — 같은 파일 `notes[]`). 금속 원가지수(data_commodity Tin·Copper + 은)와 `revenue`·`production_cost` 증가율 차이로 본다
   - inventory: 덕산 별도 재고자산
   - capacity: **같은 파일 `quarterly[].avail_hours`**(가동가능시간 = 장비대수 × 일평균가동시간 × 일수 — 2026Q1 49,680시간, 2025Q4 대비 +17%, MSB 증설), 증설 공시, Mi Material 공모자금 용도
   - SB·MSB·CSB 제품선 분해는 정기보고서에 없다(IR 자료에만). 공개 화면에는 IR 링크와 함께 분기 믹스만 인용한다
7. **드라이버 타일**: data_tw(3037·3189·8046·3305), data_commodity(Tin·Copper·은 수입물가), data_kr 메모리 허브(HS 8542.32).

## 검증
- `composite_preview.html`에서 기업군 선택에 "기판"이 생기고, 솔더볼 행 4개 + 미관측 3개가 보인다.
- 묶음 합계는 aggregate=true 행만 더한다(US$ 분기 평균 환율, YoY는 현지통화).
- 공개 산출물에 비공개 마커(`tools/tests/test_private_leak.py` 참조)와 grade C 엣지가 없다.
- 기존 rack·mlcc 화면과 CSV 내보내기가 그대로 동작한다.

## 범위 밖(후속)
- 기판 섹터의 다른 묶음(FC-BGA, BT·메모리 기판, MLB, 프로브카드·테스트 PCB, 기판 소재, 기판 장비).
- MI_SEBU 행(후공정 장비 섹터). 미테크 분기 나우캐스트는 `research/mitech/`(nowcast.js `twx` 원천 — data_twx.js 피어 월매출)로 레포에 있다 → MI_SMBU·MI_SEBU 행의 링크 줄에 `리서치 나우캐스트 ↗`(codex_tasks/ensemble_research_link.md 규칙).
- 세관 바스켓(HS 8007.00 + 7106.10·7106.92): SAC305처럼 은 2% 이상 볼은 은 합금으로 분류되어 노이즈가 커서 실험용.
