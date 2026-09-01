# teeroz 시계탑(clocktower.teeroz.net) 참고 자료 — 구조·명칭·디자인 토큰

수집일: 2026-08-29 · 대상: https://clocktower.teeroz.net/ko
방식: curl + Playwright(Chromium) 렌더링 후 DOM 추출. 저작권 있는 능력 설명 산문은 수록하지 않음 — 구조·명칭·순서·수치 등 사실 데이터만 정리. 구조화 데이터 전체는 `extraction.json` 참조.

## 1. 기술 스택 & 렌더링

- Next.js(App Router, Turbopack). 홈은 SSR + 클라이언트 하이드레이션, 스크립트 상세·백과사전은 클라이언트 렌더링(초기 HTML은 스피너 셸).
- PWA 매니페스트(`/manifest.json`), `theme-color #1a0a2e`.
- API: `/api/scripts/featured?category=…`, `/api/scripts/{id}`, `/api/announcements/latest`, `/api/auth/session`.

## 2. 정보 구조(IA)

- **글로벌 헤더**(sticky, 반투명+blur): 로고(시계 아이콘)+"시계탑" / 공지사항(벨) / 언어 드롭다운("한글-정식판") / 로그인.
- **사이드바(데스크톱, 폭 12rem) = 모바일 하단 탭 4항목**: 공식 스크립트(`/ko`) · 내 게임(`/ko/games`) · 내 스크립트(`/ko/my-scripts`) · 백과사전(`/ko/wiki`).
- **홈 섹션**: ① 공식 스크립트(3종 카드) ② 이달의 커스텀 스크립트 ③ 추천 스크립트 ④ 틴시빌 스크립트 ⑤ 문의하기(카카오 오픈채팅 링크). 커스텀 스크립트 카드는 "한국어 제목 + 영문 제목 by 제작자" 형식.
- **라우팅**: 공식 스크립트 `/ko/scripts/{slug}`, 커스텀 `/ko/scripts/{24자리 hex id}`, 위키 캐릭터 `/ko/wiki/{영문 캐릭터 id}`.

## 3. 스크립트 상세 페이지 구조

- 헤더: 뒤로가기 ← / 제목(h1) / "by 제작자" / 정렬 드롭다운(**가나다순·밤 순서순**) / 공유 버튼.
- 기능 버튼: **게임 시작**(금색 액센트, 전체폭) + 저장 아이콘 / **인쇄·PDF** / **JSON 다운로드**.
- 3-탭: **캐릭터 / 첫 번째 밤 / 이후 밤** (활성 탭에 금색 밑줄).
- 캐릭터 목록: 팀별 그룹 — 팀 배지(pill) + 개수 → 카드(데스크톱 2열, 모바일 1열).
- 카드 구성: 원형 아이콘(토큰색 배경 원 + 36px webp) · 한국어 이름(h4) · 영어 이름(작게 muted) · 자동화 지원 시 톱니 아이콘 · 능력 요약 1~3줄 · (i) 정보 모달 버튼.
- 밤 순서 탭: 위상 아이콘(황혼/새벽/하수인 정보/악마 정보)과 캐릭터 아이콘이 순서대로 나열.
- 커스텀 스크립트 상세도 동일 구조 재사용(예: "도자기 가게 / China Shop by Autumn" — 주민13·외지인4·하수인5·악마3).

## 4. Trouble Brewing(점철되는 혼란) 한국어 명칭 — teeroz 표기

- **주민(13)**: 군인(Soldier) · 까마귀지기(Ravenkeeper) · 사서(Librarian) · 성결자(Virgin) · 세탁부(Washerwoman) · 수도사(Monk) · 수사관(Investigator) · 시장(Mayor) · 요리사(Chef) · 장의사(Undertaker) · 점쟁이(Fortune Teller) · 처단자(Slayer) · 초공감자(Empath)
- **외지인(4)**: 성자(Saint) · 은둔자(Recluse) · 주정뱅이(Drunk) · 집사(Butler)
- **하수인(4)**: 남작(Baron) · 독살범(Poisoner) · 첩자(Spy) · 탕녀(Scarlet Woman)
- **악마(1)**: 임프(Imp)

참고 — 다른 공식 스크립트 제목: 피로 물든 달(Bad Moon Rising), 화단에 꽃피운 이단(Sects & Violets). 전체 캐릭터 명단은 `extraction.json`.

## 5. 밤 순서 (Trouble Brewing)

- **첫 번째 밤**: 황혼 → 하수인 정보 → 악마 정보 → 독살범 → 세탁부 → 사서 → 수사관 → 요리사 → 초공감자 → 점쟁이 → 집사 → 첩자 → 새벽
- **이후 밤**: 황혼 → 독살범 → 수도사 → 탕녀 → 임프 → 까마귀지기 → 초공감자 → 점쟁이 → 장의사 → 집사 → 첩자 → 새벽

## 6. 디자인 토큰

다크 단일 테마(라이트 모드 없음). CSS 커스텀 프로퍼티:

| 역할 | 변수 | 값 |
|---|---|---|
| 배경(기본) | `--bg-primary` | `#1a0a2e` |
| 배경(보조) | `--bg-secondary` | `#200e2f` |
| 패널/카드 | `--bg-surface` | `#2d1b4e` |
| 패널 hover | `--bg-surface-hover` | `#3a2460` |
| 본문 텍스트 | `--text-primary` | `#e9e0cc` |
| 보조 텍스트 | `--text-secondary` | `#b8a88a` |
| 옅은 텍스트 | `--text-muted` | `#7a6b55` |
| 액센트(금색) | `--accent` / `--accent-hover` | `#c4a24d` / `#d4b45d` |
| 위험 | `--danger` / `--danger-hover` | `#8b2252` / `#a52a63` |
| 성공 | `--success` | `#2d7a4f` |
| 테두리 | `--border` / `--border-light` | `#3d2a5c` / `#4d3a6c` |
| 선/악 팀 | `--good` / `--evil` | `#4a90d9` / `#d94a4a` |
| 낮/밤 배경 | `--day-bg` / `--night-bg` | `#2a1a3e` / `#0d0520` |
| 토큰(아이콘 원) | `--token-bg` / `--token-border` | `#d4c9a8` / `#b8a880` |
| 리마인더 | `--reminder-bg` / `--reminder-border` | `#0d7377` / `#14b8a6` |

- **폰트**: 본문 `"Noto Sans KR", Arial, Helvetica, sans-serif` (Geist/Geist Mono 변수도 로드되나 본문은 Noto Sans KR).
- **셰이프**: 카드 radius 12px(rounded-xl), 배지 pill, 카드 패딩 12–16px, 카드 간격 8–12px.
- **팀 배지색(tailwind)**: 주민 blue-400 · 외지인 cyan-400 · 하수인 orange-400 · 악마 red-400 (`bg-{색}-500/20 + border-{색}-500/30` pill). 위키 필터엔 여행자·전설 칩 추가.
- **토스트**: bottom-center, 배경 `#2d1b4e`, 글자 `#e9e0cc`, 테두리 `#3d2a5c`.
- **아이콘**: lucide 아이콘 세트(선형). 캐릭터 아이콘 `/icons/characters/{id}_{g|e}.webp`(g=선, e=악), 위상 아이콘 `/icons/phases/{dusk,dawn,minioninfo,demoninfo}.webp`.

## 7. 백과사전(위키)

- 인덱스: 검색 입력("캐릭터 이름으로 검색...") + 팀 필터 칩(전체/주민/외지인/하수인/악마/여행자/전설) + 카드 그리드(아이콘+한국어 이름), 캐릭터 링크 181개.
- 캐릭터 페이지 섹션(제목 수준): H1 한국어 이름(영문 병기·아티스트 표기) → H2 **등장 스크립트** → H2 **요약** → H2 **진행 방법** → H2 **예시 (n)**. i18n 리소스에는 설명·징크스 규칙 섹션 키도 존재.

## 8. 스크린샷

- `screenshot-home.png` — 홈(데스크톱 1440px)
- `screenshot-trouble-brewing-full.png` — TB 스크립트 페이지 전체 스크롤
- `screenshot-trouble-brewing-first-night.png` — 첫 번째 밤 탭
- `screenshot-wiki-index-full.png` — 백과사전 인덱스 전체
- `screenshot-wiki-washerwoman-full.png` — 백과사전 캐릭터 페이지(세탁부)
