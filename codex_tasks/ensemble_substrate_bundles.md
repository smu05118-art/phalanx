# 앙상블 기판 섹터 — 나머지 6개 묶음(FC-BGA·BT/메모리·MLB·프로브카드 PCB·소재·장비) — 로컬 생성기 반영 필요

작성 2026-10-28 · 대상: 맥스튜디오(kioxia)의 composite_preview 생성기 · 선행: `codex_tasks/ensemble_substrate_solder.md`(섹터 등록부·bundle/lines/entity_scope/aggregate 필드)

## 배경
- 솔더볼 묶음 요청서의 섹터 등록부에 기판 섹터의 나머지 묶음을 채운다. 회사 행 필드·6축·엣지 규칙은 솔더볼 요청서와 같다.
- 아래 구성원·축 원천은 공개 자료(회사 IR·결산, DART·MOPS 공시, 보도)만으로 정했다. 축 칸의 "원천"은 그 축을 채울 수 있는 공개 문서 도메인이다(값은 생성기가 원천에서 직접 읽는다).
- 근거가 없는 축은 미관측으로 둔다(0으로 그리지 않음).

## 데이터 파일
`data/ensemble/substrate.json` 의 `bundles[]`(이 문서의 6개 + 솔더볼)와 `companies[]`(bundle 필드로 구분)를 그대로 쓰면 된다. 아래 표는 그 파일의 요약이다.

## 묶음 등록부
| id | 이름 | 수요 동인 | 구성원 수 |
|---|---|---|---|
| `fcbga` | FC-BGA·ABF 기판 | AI 가속기·서버 CPU·ASIC 패키지(대면적·고다층 FC-BGA) | 12 |
| `bt_memory` | BT·메모리 기판 | 메모리 패키지(DDR5·SoCAMM)·모바일 FC-CSP 물량과 BT 공급 축소 | 5 |
| `mlb` | MLB·AI 서버 PCB | AI 서버·스위치 고다층(HLC/HDI) 기판, 메모리 모듈 PCB | 5 |
| `probe_pcb` | 프로브카드·테스트 PCB | 메모리·HBM 웨이퍼/패키지 테스트(프로브카드·로드보드) | 2 |
| `materials` | 기판 소재(ABF·CCL·T-glass·SR) | 기판 물량·층수 증가에 따른 CCL·절연필름·유리섬유 수요 | 6 |
| `equipment` | 기판 장비(검사·드릴·노광) | 기판사 증설(FC-BGA 대면적·고다층)에 따른 검사·리페어·드릴 장비 발주 | 5 |

## `fcbga` — FC-BGA·ABF 기판

| 구성원 | 티커 | 관측 범위 | 주기 | 수요 | 매출 | 가동 | 가격 | 재고 | 투자 |
|---|---|---|---|---|---|---|---|---|---|
| 삼성전기 패키지솔루션 | 009150 KS | 삼성전기 패키지솔루션 사업부(FC-BGA·BGA 기판); 사업부 이익 미공시 | 분기 | ● news.mtn.co.kr | ● samsungsem.com | ◐ samsungsem.com | — | — | ● news.mtn.co.kr |
| Ibiden 전자 부문 | 4062 JP | Ibiden Electronics 부문(IC 패키지 기판) | 분기 | ◐ logi-today.com | ● ibiden.com | ◐ ibiden.com | ● ibiden.com | — | ● ibiden.com |
| Unimicron | 3037 TT | Unimicron 연결(2Q25 기준 기판 58%, 기판 중 ABF 79%) | 월 | — | ● finance.technews.tw | ● ctee.com.tw | ● ctee.com.tw | — | ● uanalyze.com.tw |
| Kinsus | 3189 TT | Kinsus 연결(ABF+BT) | 월 | — | ● finance.technews.tw | ● uanalyze.com.tw | ● uanalyze.com.tw | — | ● money.udn.com |
| Nan Ya PCB | 8046 TT | Nan Ya PCB 연결(FY2025 ABF 50~55%·BT 약 30%) | 월 | — | ● finance.technews.tw | ● tw.stock.yahoo.com | ● technews.tw | — | ◐ ctee.com.tw |
| AT&S Microelectronics | ATS AV | AT&S Microelectronics(IC 기판) 부문 | 분기 | ◐ ats.net | ● ats.net | — | ● ats.net | — | ● ats.net |
| LG이노텍 패키지솔루션 | 011070 KS | LG이노텍 패키지솔루션 사업부(RF-SiP·FC-CSP·FC-BGA) | 분기 | ◐ koreaherald.com | ● lg.co.kr | — | ● file.alphasquare.co.kr | — | ● koreaherald.com |
| 대덕전자 FC-BGA(로직) | 353200 KS | 대덕전자 로직 패키지기판(FC-BGA/FC-CSP); 가동률은 FC-BGA, 이익은 전사 | 분기 | ◐ stock.pstatic.net | ● stock.pstatic.net | ● stock.pstatic.net | ● stock.pstatic.net | — | ● stock.pstatic.net |
| Zhen Ding | 4958 TT | Zhen Ding 연결(IC 기판은 일부) | 월 | — | ● uanalyze.com.tw | ◐ technews.tw | ◐ uanalyze.com.tw | — | ◐ technews.tw |
| Toppan FC-BGA | 7911 JP | Toppan FC-BGA(니가타·싱가포르 AST JV); 부문 매출 미분리 | 없음 | — | — | — | — | — | ● evertiq.com |
| Kyocera 유기 패키지 | 6971 JP | Kyocera 유기재료(FC-BGA) 사업 | 없음 | ◐ dempa-digital.com | — | — | — | — | ● dempa-digital.com |
| Shinko Electric | 6967 JP (delisted 2025-06-06) | Shinko 플라스틱 패키지 부문(최종 공개 연도) | 없음 | — | ● edinetdb.jp | — | — | — | — |

● 수치 근거 · ◐ 정성 근거 · — 미관측

## `bt_memory` — BT·메모리 기판

| 구성원 | 티커 | 관측 범위 | 주기 | 수요 | 매출 | 가동 | 가격 | 재고 | 투자 |
|---|---|---|---|---|---|---|---|---|---|
| 심텍 | 222800 KS | 심텍 연결(패키지기판+모듈 HDI) | 분기 | — | ● en.edaily.co.kr | ◐ stock.pstatic.net | ● en.edaily.co.kr | — | — |
| 대덕전자 메모리 기판 | 353200 KS | 대덕전자 메모리 패키지기판; 이익은 전사 | 분기 | ◐ stock.pstatic.net | ● stock.pstatic.net | ◐ core.asiae.co.kr | ● stock.pstatic.net | — | ◐ stock.pstatic.net |
| 해성디에스 패키지기판 | 195870 KS | 해성디에스 패키지기판(리드프레임 제외) | 분기 | — | ● stock.pstatic.net | — | ● stock.pstatic.net | — | — |
| Kinsus BT | 3189 TT | Kinsus BT 라인; 매출은 회사 전체로 대용 | 월 | — | ● finance.technews.tw | ◐ uanalyze.com.tw | ● uanalyze.com.tw | — | — |
| 코리아써키트 패키지기판 | 007810 KS | 코리아써키트 패키지기판(별도) | 분기 | — | ● stock.pstatic.net | ◐ stock.pstatic.net | ◐ stock.pstatic.net | — | — |

● 수치 근거 · ◐ 정성 근거 · — 미관측

## `mlb` — MLB·AI 서버 PCB

| 구성원 | 티커 | 관측 범위 | 주기 | 수요 | 매출 | 가동 | 가격 | 재고 | 투자 |
|---|---|---|---|---|---|---|---|---|---|
| 이수페타시스 | 007660 KS | 이수페타시스 연결(수주잔고는 별도) | 분기 | ● tokenpost.kr | ● tokenpost.kr | — | ● tokenpost.kr | — | ● file.alphasquare.co.kr |
| Gold Circuit | 2368 TT | Gold Circuit 연결 | 월 | — | ● finance.technews.tw | — | ◐ uanalyze.com.tw | — | ● uanalyze.com.tw |
| Tripod | 3044 TT | Tripod 연결 | 월 | — | ● finance.technews.tw | — | ◐ uanalyze.com.tw | — | — |
| 티엘비 | 356860 KQ | 티엘비 연결 | 분기 | ● alphadistill.com | ● alphadistill.com | ◐ alphadistill.com | ● alphadistill.com | — | — |
| Victory Giant | 300476 CH | Victory Giant 연결 | 분기 | ◐ news.10jqka.com.cn | ● cnfin.com | — | ◐ cnfin.com | — | ● news.10jqka.com.cn |

● 수치 근거 · ◐ 정성 근거 · — 미관측

## `probe_pcb` — 프로브카드·테스트 PCB

| 구성원 | 티커 | 관측 범위 | 주기 | 수요 | 매출 | 가동 | 가격 | 재고 | 투자 |
|---|---|---|---|---|---|---|---|---|---|
| 타이거일렉 | 219130 KQ | 타이거일렉 연결(프로브카드·로드보드·소켓보드 PCB) | 분기 | — | ● bbn.kiwoom.com | — | ● bbn.kiwoom.com | — | ◐ bbn.kiwoom.com |
| 티에스이 | 131290 KQ | 티에스이 연결 | 분기 | — | ● stock.pstatic.net | — | ● m.irgo.co.kr | — | — |

● 수치 근거 · ◐ 정성 근거 · — 미관측

## `materials` — 기판 소재(ABF·CCL·T-glass·SR)

| 구성원 | 티커 | 관측 범위 | 주기 | 수요 | 매출 | 가동 | 가격 | 재고 | 투자 |
|---|---|---|---|---|---|---|---|---|---|
| Ajinomoto (ABF) | 2802 JP | Ajinomoto 헬스케어 등 부문(ABF 포함, 기능재료 미분리) | 분기 | — | ● www2.jpx.co.jp | — | ● www2.jpx.co.jp | — | — |
| 두산 전자BG (CCL) | 000150 KS | 두산 전자BG(CCL); 이익은 자체사업 합산 | 분기 | — | ● doosan.com | — | ● doosan.com | — | ● stock.pstatic.net |
| Resonac | 4004 JP | Resonac 반도체·전자재료 부문 | 분기 | — | ● eetimes.itmedia.co.jp | — | ◐ www-web.itiger.com | — | — |
| Mitsubishi Gas Chemical | 4182 JP | MGC 전자재료(CCL·프리프레그·CRS); 부문 매출 행 없음 | 없음 | — | — | — | ● www-web.itiger.com | — | — |
| Nittobo (T-glass) | 3110 JP | Nittobo 연결(T-glass 포함) | 분기 | — | ● trendforce.com | ● uanalyze.com.tw | ◐ www-web.itiger.com | — | ◐ trendforce.com |
| Taiyo Holdings (솔더레지스트) | 4626 JP | Taiyo HD 전자 부문(솔더레지스트 등) | 분기 | — | ● taiyo-hd.co.jp | — | ◐ taiyo-hd.co.jp | — | — |

● 수치 근거 · ◐ 정성 근거 · — 미관측

## `equipment` — 기판 장비(검사·드릴·노광)

| 구성원 | 티커 | 관측 범위 | 주기 | 수요 | 매출 | 가동 | 가격 | 재고 | 투자 |
|---|---|---|---|---|---|---|---|---|---|
| 기가비스 | 420770 KQ | 기가비스 연결 | 분기 | ● home.imeritz.com | ● stock.pstatic.net | — | ● stock.pstatic.net | — | ● home.imeritz.com |
| 인텍플러스 | 064290 KQ | 인텍플러스 연결(반도체·기판 검사 + DP·배터리) | 분기 | ● home.imeritz.com | ● home.imeritz.com | — | ● home.imeritz.com | — | — |
| KLA PCB·부품 검사(Orbotech) | KLAC US | KLA PCB and Component Inspection 부문 | 분기 | — | ● sec.gov | — | — | — | — |
| Amada (Via Mechanics) | 6113 JP | Amada 연결(Via Mechanics 포함, 부문 미분리) | 분기 | ● monoist.itmedia.co.jp | ◐ monoist.itmedia.co.jp | — | — | — | — |
| Ushio | 6925 JP | Ushio 연결 | 분기 | — | ● scouter.monex.co.jp | — | — | — | — |

● 수치 근거 · ◐ 정성 근거 · — 미관측

## 증설 트래커(공개 발표)
`capex[]` = `{company, amount, unit, period, purpose, announced, source_url}` — 통화를 바꾸지 않고 그대로 싣는다.

| 회사 | 금액 | 단위 | 기간 | 용도 | 발표 |
|---|---|---|---|---|---|
| Ibiden | 220,000 | JPY mn | FY2026-FY2028 | Gama Cell6, AI ASIC 기판; FY2027 양산 (3개년 합계 JPY 500bn의 일부, fcbga-033) | 2026-02-03 |
| Ibiden | 280,000 | JPY mn | FY2026-FY2028 | Ono Cell8 2단계, AI 서버 IC 기판; FY2027 양산, 고객 선수금 일부 충당 | 2026-02-26 |
| AT&S | 1,750 | EUR mn (range 1,500-2,000) | FY2026/27- | 쿨림 AI 기판 증설(범위 1,500~2,000), AMD 등 고객 장기 약정으로 조달 | 2026-06-13 |
| AT&S | 1,100 | EUR mn (range 1,000-1,200) | FY2026/27 | FY2026/27 연간 capex 가이던스(1,000~1,200, 기존 400); 쿨림 증설과 일부 중복 | 2026-06-13 |
| LG Innotek | 10,000 | KRW 100mn (억원) | 2026 | 베트남 하이퐁 RF-SiP·FC-CSP 라인 1차 투자; FC-BGA는 별도 협의 | 2026-06-17 |
| 두산 전자BG | 1,800 | KRW 억원 | 2026-07 | 태국 신규 CCL 부지(NWB 최대 8라인, 첫 2라인 2H28) | 2026-07 |
| Unimicron | 53,700 | NT$ mn | FY2026 | 2026 설비투자 예산(3차 상향), 80~85% ABF; 양메이 2·3공장 | 2026-07-28 |
| 대덕전자 | — |  | ~2Q27 | FC-CSP·메모리 캐파 9,500억→1.2조(2Q27) 확대에 약 4,000억원(건물 2,130억+장비 약 2,500억); 금액은 행 비고에만 있음 | 2026-07-31 |
| Nittobo | — |  | ~FY2029 | JPY 80bn 투자로 FY2029까지 캐파 3배; 금액은 행 비고에만 있음 | 2026-08 |
| Victory Giant | 180 | CNY 億元 (not exceeding) | FY2026 | 2026 고정자산 투자 상한 | 2026-08-27 |
| Gold Circuit | 170 | TWD 億元 (over) | FY2026 | 2026 설비투자(이상), 2025년 약 50~60억; 중리 신공장 138억 승인(2026-09-04) | 2026-09-04 |
| 삼성전기 | 42,700 | KRW 억원 | 2026-09 | 세종 FC-BGA 증설, 2028-09 양산; 베트남 패키지기판 25,100억원 별도(합계 67,800억원) | 2026-09-28 |
| Gold Circuit | 79 | TWD 億元 | 2026-10 | 대만 토지·설비 신규 투자(이사회); 사모 증자에 Amazon 참여 | 2026-10-05 |
| Kinsus | 19,600 | NT$ mn | 2026Q3 | K6 공장 추가 설비투자(기존 예산 8,000); 별도 보도: 2026 현금 capex 약 14.0bn, 2027 계획 16.0bn | 2026Q3 |
| Toppan (AST Singapore JV) | 50 | JPY bn | 2024-2026 | 싱가포르 FC-BGA 공장(Nikkei 추정), Broadcom 앵커; 2026-09-29 개소 | 미상(Nikkei 추정) |

## 검증
- 기업군 "기판" 아래 묶음 선택에 7개(솔더볼 + 위 6개)가 보이고, 각 구성원 카드에 6축과 미관측 공백이 보인다.
- 같은 회사가 여러 묶음에 나오면(예: 대덕전자 FC-BGA·메모리 기판) `entity_scope` 로 사업부를 나누고 `group` 으로 합산 중복을 막는다.
- 공개 산출물에 비공개 마커(`tools/tests/test_private_leak.py`)가 없다.
