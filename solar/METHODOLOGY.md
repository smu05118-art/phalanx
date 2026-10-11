# 북미 태양광 원장

조사 기준일: 2026-10-11

국가: 미국(푸에르토리코 별도 표시), 캐나다, 멕시코. 원천별 관측일이 다릅니다.

- EIA 발전기, LBNL 계통접속 신청, 캐나다 시설·계약·접속신청, 멕시코 허가, GEM 보조 원장은 독립된 층입니다. 총합을 유일한 실물 발전소 수 또는 북미 설치 MW로 해석할 수 없습니다.
- 실제 가동일과 계획일, AC와 DC, 허가 MW와 접속신청 MW를 구분합니다. 공란은 추정하지 않습니다.
- 원천의 기술/연료 불일치, 음수·단위 의심값, 동일 식별자에 다른 행이 있으면 품질 표시를 남깁니다.
- GEM TZ/WKSL 권리 제한 행은 공개 원장에서 제외합니다.
- 공급사·EPC·PPA는 대량 원천에 없으면 TBD입니다.
- 필터 CSV는 현재 조건의 전행을 내려받습니다. 원천 날짜·URL·기록ID를 함께 보존합니다.
- 이 배포는 고정 조사 스냅샷입니다. 자동 갱신을 의미하지 않습니다.

## 국가별 확인 범위

- US: EIA 2026-08: 1MW 이상 발전소 소속 PV 발전기. PR별도지역. LBNL 2025년말 송전접속 Solar 신청(PV·태양열 미구분). 소재국 미공표311행과 멕시코소재2행 구분. 분산형 전수 아님.
- MX: CNE 2026-02 역사 허가 전행. 허가 기록이며 실물발전소 전수·실제 운영 증거가 아님. 혼합발전/원천 모순/이상값 MW10건 보류. GEM은 별도 보조 원장.
- CA: 공식 원장 3,430행(ON3,192·AB121·NS104·BC7·SK6)에 개별 공식 근거 21행을 별도 보강. 13개 주·준주별 확인 범위와 공백을 방법론에 기록. 모든 3,451행은 공개 재사용 조건 미확인/제한으로 내부 연구뷰에 보존. GEM CA317행 중257행 공개. 현행 전국 실물 발전소 전수 명부는 미확보. 과거 발표·허가를 현재 운영으로 간주하지 않음.

공개 제외 기록은 내부 연구본에서 원천별 이용 조건과 함께 보존합니다.

## 캐나다 주·준주별 확인 범위

공식 원천 기록 수이며, 실물 시설의 중복 제거 수가 아닙니다. 개별 사업 확인을 관할 전수 완료로 해석하지 않습니다.

| 주·준주 | 공식 기록 | 확인 범위와 한계 |
|---|---:|---|
| AB | 121 | AESO 시장 자산49·접속신청72. 시장/송전서비스 범위. |
| BC | 7 | BC Hydro EPA 운영4·개발3. 비계약 발전소 제외. |
| MB | 1 | Fisher River 2020 운영 발표. 현행 시설 전수 명부 미확보. |
| NB | 4 | Shediac 준공 근거1·선택된 환경심사3. 심사 전체 목록 미전수. |
| NL | 1 | EVREC 환경심사 태양광 성분. 시설·신청 전체 목록 미전수. |
| NS | 104 | NS Power 3개 접속큐,89개 IR의104관측. 운영 명부 아님. |
| ON | 3192 | IESO 계약3169·solar 명시 접속23. 무계약·microFIT 및 큐 연료 미표시 공백. |
| PE | 1 | Slemon Park 2023–24 연차보고. Summerside 원문 접근 실패; 현행 전수 아님. |
| QC | 2 | 2021년 두 발전소 준공 및 지명등록 근거. 개별 MW 미공표; 현행 전수 아님. |
| SK | 6 | SaskPower 개별 운영3·건설1·계획2. 자가소비·모든 제안사업 전수 아님. |
| NT | 1 | Inuvik 1MW 개발지원 근거. 실제 운영 미확인; 현행 전수 아님. |
| NU | 1 | Ikayuut 2026-09 연결 약1.4MW. 현행 전체 시설 명부 미확보. |
| YT | 9 | 2024 IPP 명세8 및 계획서술1. 규모 미공표, 현행 전수 아님. |
| 미공표 | 1 | Yukon 원천의 Lower Post. 소재 주를 추정하지 않음. |

## 원천 및 이용 조건

- 미국 EIA-860M PV 발전기 명부: https://www.eia.gov/electricity/data/eia860m/xls/august_generator2026.xlsx
  - 미국 EIA-860M PV 발전기 명부; U.S. government public data; U.S. Energy Information Administration attribution
- 미국 LBNL·GridTracker 계통접속 신청: https://eta-publications.lbl.gov/sites/default/files/2026-05/lbnl_ix_queue_data_file_thru2025.xlsx
  - Lawrence Berkeley National Laboratory and GridTracker, Queued Up Data File (2026), Regents of the University of California.; CC BY 4.0
- Lista de permisos otorgados de generación de energía eléctrica: histórico (1963 - febrero de 2026): https://www.datos.gob.mx/datastore/dump/8f348d71-6d90-4d0a-9a5c-33745381c5c8?format=csv
  - Comisión Nacional de Energía (CNE); Creative Commons Attribution 4.0
- 앨버타 AESO 접속 신청: https://www.aeso.ca/assets/Uploads/project-reporting/October-2026-Project-List.xlsx
  - 앨버타 AESO 접속 신청; AESO Legal: limited non-commercial personal/educational reproduction; other uses require permission
- 앨버타 AESO 시장 자산: https://www.aeso.ca/
  - 앨버타 AESO 시장 자산; AESO Legal: limited non-commercial personal/educational reproduction; other uses require permission
- 온타리오 IESO 발전 계약: https://www.ieso.ca/-/media/Files/IESO/Document-Library/power-data/supply/IESO-Active-Contracted-Generation-List.xlsx
  - 온타리오 IESO 발전 계약; IESO limited reproduction terms; retain prescribed copyright/Terms of Use attribution
- 온타리오 IESO 명시 Solar 접속 신청: https://www.ieso.ca/-/media/files/IESO/files/applicationstatusdata.json
  - 온타리오 IESO 명시 Solar 접속 신청; IESO limited reproduction terms; retain prescribed copyright/Terms of Use attribution
- BC Hydro 운영 EPA 계약: https://www.bchydro.com/content/dam/BCHydro/customer-portal/documents/corporate/independent-power-producers-calls-for-power/independent-power-producers/ipp-supply-list-in-operation.pdf
  - BC Hydro 운영 EPA 계약; Publicly accessible; no open reuse license verified
- BC Hydro 개발 EPA 계약: https://www.bchydro.com/content/dam/BCHydro/customer-portal/documents/corporate/independent-power-producers-calls-for-power/independent-power-producers/ipp-supply-list-in-development.pdf
  - BC Hydro 개발 EPA 계약; Publicly accessible; no open reuse license verified
- SaskPower · Highfield Solar: https://www.saskpower.com/our-power-future/our-electricity/electrical-system/system-map/highfield-solar-facility
  - SaskPower · Highfield Solar; Publicly accessible; no open reuse license verified
- SaskPower · Pesâkâstêw Solar: https://www.saskpower.com/our-power-future/our-electricity/electrical-system/system-map/pesakastew-solar-facility
  - SaskPower · Pesâkâstêw Solar; Publicly accessible; no open reuse license verified
- SaskPower · Awasis Solar: https://www.saskpower.com/our-power-future/our-electricity/electrical-system/system-map/awasis-solar-facility
  - SaskPower · Awasis Solar; Publicly accessible; no open reuse license verified
- SaskPower · Turning Sun Solar: https://saskpower.com/about-us/media-information/news-releases/2026/construction-of-turning-sun-solar-underway
  - SaskPower · Turning Sun Solar; Publicly accessible; no open reuse license verified
- SaskPower · Mino Giizis Solar: https://saskpower.com/about-us/media-information/news-releases/2026/fnpa-selects-mino-giizis-solar-for-100-mw-project
  - SaskPower · Mino Giizis Solar; Publicly accessible; no open reuse license verified
- SaskPower · Southern Springs Solar: https://saskpower.com/our-power-future/infrastructure-projects/construction-projects/planning-and-construction-projects/southern-springs-solar-project
  - SaskPower · Southern Springs Solar; Publicly accessible; no open reuse license verified
- NS Power 배전 접속 신청: https://www.nspower.ca/docs/default-source/pdf-to-upload/ieso-ns-oasis-active-distribution-interconnection-requests-distribution-q.pdf?sfvrsn=81e2a999_11
  - NS Power 배전 접속 신청; Publicly accessible; no open reuse license verified
- NS Power 송전 접속 신청: https://www.nspower.ca/docs/default-source/pdf-to-upload/ieso-ns-oasis-active-transmission-interconnection-requests-transmission-q.pdf?sfvrsn=17b5e466_10
  - NS Power 송전 접속 신청; Publicly accessible; no open reuse license verified
- NS Power 단계별 접속 신청: https://www.nspower.ca/docs/default-source/pdf-to-upload/ieso-ns-oasis-combined-interconnection-requests-advanced-q.pdf?sfvrsn=3ec91458_11
  - NS Power 단계별 접속 신청; Publicly accessible; no open reuse license verified
- GEM 북미 태양광 프로젝트·단계 보조 원장: https://raw.githubusercontent.com/GlobalEnergyMonitor/gipt-dashboard/06587e9b6c4e332e646347f6e62af54b10df5ef3/Global-Solar-Power-Tracker-February-2026.xlsx
  - Global Energy Monitor, Global Solar Power Tracker, February 2026. Filtered and normalized by Phalanx.; CC BY 4.0 except TZ-tagged CC BY-NC 4.0 and WKSL proprietary upstream rows; per-row gates apply
- PEI Energy Corporation · Slemon Park 연차보고: https://www.princeedwardisland.ca/sites/default/files/publications/peiec_annual_report_2023-24_final_toprint.pdf
  - PEI Energy Corporation · Slemon Park 연차보고; Public official source; open redistribution license not verified
- Yukon Development Corporation · IPP 2024 명세: https://open.yukon.ca/sites/default/files/YDC-2024-Fall-BN.pdf
  - Yukon Development Corporation · IPP 2024 명세; Public official source; open redistribution license not verified
- NRCan · Inuvik 개발계획: https://natural-resources.canada.ca/funding-partnerships/beaufort-delta-renewable-resource-plan-0
  - NRCan · Inuvik 개발계획; Public official source; open redistribution license not verified
- CER · Québec 두 발전소 준공 근거: https://www.cer-rec.gc.ca/en/data-analysis/energy-markets/province-territory-energy-profiles/quebec.html
  - CER · Québec 두 발전소 준공 근거; Public official source; open redistribution license not verified
- Fisher River Cree Nation · 사업 발표: https://fisherriver.ca/2020/08/fisher-river-cree-nation-unveils-manitobas-biggest-solar-farm-a-source-of-bullfrog-powers-green-energy/
  - Fisher River Cree Nation · 사업 발표; not_verified
- NB Power · Shediac 시설: https://www.nbpower.com/en/grid-modernization/smart-grid-atlantic/shediac-smart-energy-community-project/shediac-s-community-solar-farm/
  - NB Power · Shediac 시설; not_verified
- New Brunswick · 환경심사 1657 이후: https://www.gnb.ca/en/topic/environment-resources/environmental-assessment/registrations-determinations/1657-most-recent.html
  - New Brunswick · 환경심사 1657 이후; not_verified
- New Brunswick · 환경심사 1515–1534: https://www.gnb.ca/en/topic/environment-resources/environmental-assessment/registrations-determinations/1515-1534.html
  - New Brunswick · 환경심사 1515–1534; not_verified
- Newfoundland and Labrador · 환경심사 2327: https://www.gov.nl.ca/eccc/projects/project-2327/
  - Newfoundland and Labrador · 환경심사 2327; not_verified
- Nunavut 정부 · Ikayuut 연결 발표: https://climatechangenunavut.ca/news/ikayuut-solar-project-comes-online-naujaat
  - Nunavut 정부 · Ikayuut 연결 발표; source explicitly reserves text/image reuse; factual normalization only; do not publish raw source
