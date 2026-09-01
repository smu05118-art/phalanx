# Codex 교차 검증 결과 — thyrsus/index.html

## 실행 정보
- 실행 일시: 2026-08-31 (맥스튜디오, MACSTUDIO-CODEX.md 방법 A)
- 도구: OpenAI Codex CLI v0.150.1 · 모델 `gpt-5.6-sol` · reasoning effort **xhigh**
- 샌드박스: `read-only` (index.html 수정 불가 보장) · approval: never
- 세션: `01a0582f-f93f-7b21-b60b-100c01c26c20`
- 입력: `codex-review-packet.md` 전문 + 기수정 16건 재보고 금지 지시
- 검토 대상 커밋: `b5ea4d3` (claude/trouble-brewing-script-1sv6lg)
- Codex 자체 검증: HTML 내 실행 스크립트 추출 후 `node --check` 통과 확인. Playwright 스위트는 저장소에 없어 미실행 — 재현 조건은 코드 경로 기준.
- 공식 근거: TPI roles.json / nightsheet.json + 공식 위키

## 요약 (맥스튜디오 Claude 정리)

**신규 결함 15건** (Critical 2 · High 6 · Medium 6 · Low 1). 기수정 16건 목록과 대조한 결과 **중복 보고 없음** — 인접 영역 4건은 아래 표 비고 참조.

| # | 심각도 | 결함 | 위치(라인) | 비고 |
|---|--------|------|-----------|------|
| 1 | Critical | 승리 차단 상태(주모자 연장전·사악한 쌍둥이)가 `null` 반환으로 기존 선 승리 판정에 떨어짐 | 4314, 4366, 4407 | 기수정 "악 승리 미감지"와 별개 — 이번엔 **선 승리 오판정** 방향 |
| 2 | Critical | 푸카가 `doPoison()` 재사용 → 중독 만료·지연 사망·오작동 판정 전부 오동작 | 1663, 3172 | 기수정 "중독 중복"과 별개 — 푸카 수명주기 자체 문제 |
| 3 | High | 커스텀 캐릭터 `ko`/`id` 무탈출 → 영속 DOM XSS | 1018, 1092, 2185, 2206 | 기수정 "이름 따옴표 XSS"와 다른 벡터(커스텀 캐릭터 경로) |
| 4 | High | 진영을 `charId`에서 유도 → 이발사 교환·건달·팡 구 진영 오염 | 844, 3551, 3377 | `alignment` 필드 부재가 근본 원인 |
| 5 | High | 공통 사망 판정기 부재 → 찻집·악마의 변호사·어릿광대·시장 보호/처형 분기 오류 | 1718, 1675, 1988 | 기수정 "암살자-어릿광대"와 별개 — 판정기 구조 문제 |
| 6 | High | 상태에 `sourcePid` 없음 → 출처 사망/변경 시 중독·취함 잔존, `drunkS` 만료 없음 | 852, 870, 3847, 723 | 기수정 "낮 보호 토큰 잔존"과 별개 — 출처 연동 문제 |
| 7 | High | 비고르모르티스가 죽인 하수인이 능력 상실 (밤 단계 스킵·마녀 판정 제외) | 1718, 1428, 1855, 3395 | |
| 8 | High | BMR·SV 첫밤 순서 공식과 불일치 + `renderSheet()`가 정보 단계 강제 선두 배치 | 803, 806, 1260 | BMR: 하수인→미치광이→악마, SV: 철학자→하수인→악마가 공식 |
| 9 | Medium | 셋업 구성 보정이 남작만 지원 (대부±1·팡 구+1·비고르모르티스−1 누락) | 1043, 1202 | |
| 10 | Medium | 지명 취소 시 소비된 사망 투표 토큰 미복원 | 1960, 1987 | |
| 11 | Medium | 집사 무효표가 경고만 뜨고 실제 집계에 포함됨 | 1956, 1977 | |
| 12 | Medium | 밤 위저드 대상 필터 오류 (꿈꾸는 자-여행자 허용, 재봉사 자기 선택, 사망자 선택 불가 등) | 2777, 3314, 3333, 3349, 3371 | 기수정 "위저드 씬 전역 오염"과 별개 — 필터 규칙 문제 |
| 13 | Medium | 미치광이 밤 지목의 악마 전달을 "재량"으로 오안내 (공식은 필수) | 637, 3155 | |
| 14 | Medium | 노 다시 독 대상을 사망 시 재계산하라고 오안내 (생사 무관 최근접 주민이 공식) | 791, 2713, 3383 | |
| 15 | Low | 곡예사를 "2일 밤" 고정 처리 → 도중 생성된 곡예사 능력 사용 불가 | 733, 3430 | |

### 수정 우선순위 제안
1. **#1, #2** (Critical): 승패 판정과 악마 능력 직결 — 최우선.
2. **#3** (XSS): `onclick` 문자열 보간 제거 + `esc()` 적용. HTML 이스케이프만으로 JS 문자열 문맥은 못 막는다는 지적 유의.
3. **#4~#6**: 공통 구조 문제(진영 필드, 사망 판정기, 상태 출처 연동). 개별 패치보다 구조 도입이 재발 방지에 유리 — #5·#6·#7이 모두 여기서 파생.
4. **#8**: 밤 순서 데이터 수정은 저위험 — 배열 교체로 즉시 해결.
5. 나머지 Medium/Low는 위저드 안내문·필터 수정 위주.

### 주의사항
- 원문 내 파일 링크는 맥스튜디오 로컬 절대경로 포함(원문 보존 차원에서 유지). 라인 번호는 커밋 `b5ea4d3` 기준.
- #11(집사)·#12(위저드 필터) 일부는 하우스룰 의도와 겹칠 수 있음 — 수정 세션에서 의도 여부 판단 필요.
- Codex는 실행 검증 없이 코드 경로 분석만 수행. 수정 후 Playwright 회귀 필수.

---

## Codex 원문 출력 (verbatim)

검토 결과, 제외 목록과 알려진 제약을 빼고도 추가 결함 15건을 확인했습니다. 파일은 수정하지 않았으며, HTML의 실행 스크립트를 추출한 `node --check`는 통과했습니다. 제공되지 않은 Playwright 스위트는 실행하지 못해 아래 재현은 코드 경로 기준입니다.

공식 기준은 TPI의 [역할 데이터](https://release.botc.app/resources/data/roles.json)와 [밤 순서 데이터](https://release.botc.app/resources/data/nightsheet.json)를 사용했습니다.

## Critical

1. **승리 차단 상태가 `null`로 표현되어 오히려 기존 선 승리 판정으로 떨어짐**

   - 위치/요약: [thyrsus/index.html:4314](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:4314), [thyrsus/index.html:4366](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:4366), [thyrsus/index.html:4407](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:4407). `evalWinEvent()`가 탕녀·주모자·사악한 쌍둥이로 게임이 계속될 때 `null`을 반환하지만, 래퍼는 이를 일반 미판정으로 보고 `_orig()`를 호출합니다. `_orig()`는 마지막 악마가 죽었다며 선 승리를 선언합니다.
   - 재현: 정상 작동하는 주모자가 살아 있는 BMR에서 악마를 처형하거나, 두 쌍둥이가 살아 있는 SV에서 마지막 악마를 죽입니다. `return null` 뒤 기존 `checkEndConditions()`가 실행되어 `showGameOver('good')`까지 도달합니다.
   - 기대 동작: 주모자는 정확히 하루의 연장전을 시작해야 하며, 다음 낮에는 “죽었는지”가 아니라 어느 팀 플레이어가 처형됐는지로 승패를 결정해야 합니다. 사악한 쌍둥이는 지정된 선한 쌍둥이와 둘 다 살아 있을 때만 선 승리를 막아야 합니다. [공식 주모자 규칙](https://wiki.bloodontheclocktower.com/Mastermind)
   - 제안 패치: 승리·계속·미판정을 구분하고 상태를 저장하십시오.
     ```js
     // 예시
     return {kind:'continue', reason:'mastermind'};
     
     if (res?.kind === 'win') return askWin(res);
     if (res?.kind === 'continue') {
       if (res.reason === 'mastermind') {
         S.mastermindDay = S.phase.n + 1;
       }
       save();
       return;
     }
     _orig(cause, aliveBefore);
     ```
     `goodTwinPid`, `mastermindDay`를 영속 상태로 저장하고, 다음 낮 무처형/선 처형/악 처형을 별도 종결 이벤트로 처리해야 합니다.

2. **푸카가 독살범 로직을 재사용해 중독·사망 시점과 오작동 판정이 모두 깨짐**

   - 위치/요약: [thyrsus/index.html:1663](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1663), [thyrsus/index.html:3172](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3172). 푸카도 `doPoison()`을 호출하지만 이 함수는 독살범만 검사하고, 토큰을 다음 밤 시작 즉시 만료시킵니다. 위저드는 또한 이전 희생자의 죽음을 새 지목보다 먼저 안내합니다.
   - 재현: 첫날 푸카가 A를 고르면 A의 독은 밤 2 시작의 `expireStatuses()`에서 먼저 사라집니다. 푸카가 궁정대신 등에 의해 취해 있어도 `poisoner`를 찾지 못하므로 새 대상 B가 중독됩니다. 이전 대상 ID도 저장되지 않아 지연 사망을 자동 판정할 수 없습니다.
   - 기대 동작: 푸카는 새 대상을 지목해 중독시킨 직후 이전 중독자가 죽고 건강해집니다. 푸카가 현재 오작동이면 새 중독은 생기지 않고 이전 독의 사망도 보류되며, 정상으로 돌아오면 이어집니다. [공식 푸카 규칙](https://wiki.bloodontheclocktower.com/Pukka)
   - 제안 패치: `doPukkaPick()`을 분리하고 `S.pukkaVictimId`와 출처를 저장하십시오. 푸카 정상 작동 시 “새 독 부여 → 이전 희생자 사망 시도 → 이전 독 해제” 순으로 처리하고, 오작동 시 기존 희생자를 그대로 유지해야 합니다. 푸카 독에는 페이즈 기반 `expiresAt`을 넣으면 안 됩니다.

## High

3. **커스텀 캐릭터를 통한 영속 DOM XSS**

   - 위치/요약: [thyrsus/index.html:1018](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1018), [thyrsus/index.html:1092](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1092), [thyrsus/index.html:2185](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:2185), [thyrsus/index.html:2206](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:2206). 커스텀 `ko`가 `innerHTML`에 무탈출 삽입되고, 가져온 `id`는 검증 없이 `onclick="... '${c.id}' ..."`에 들어갑니다.
   - 재현: 커스텀 이름으로 `<img src=x onerror=alert(1)>`을 저장하고 스크립트 화면을 렌더합니다. 또는 `id`가 `x');alert(1);//`인 JSON을 가져온 뒤 삭제 버튼을 누릅니다. localStorage와 클라우드 스냅샷에도 payload가 남습니다.
   - 기대 동작: 표시 문자열은 텍스트로만 렌더되고, 가져온 JSON이 실행 가능한 HTML/JS 문맥에 들어가지 않아야 합니다.
   - 제안 패치: `S.customs.map(c => esc(c.ko))`로 표시값을 이스케이프하고, 가져오기 시 ID·타입·필드 길이를 검증하십시오. `onclick` 문자열 보간은 제거하고 `data-char-id`와 `addEventListener`를 사용해야 합니다. HTML escaping만으로 JS 문자열 문맥을 안전하게 만들 수는 없습니다.

4. **플레이어 진영을 캐릭터 타입에서 계산해 캐릭터 변경 후 진영이 오염됨**

   - 위치/요약: [thyrsus/index.html:844](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:844), [thyrsus/index.html:3551](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3551), [thyrsus/index.html:3377](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3377). `isEvil()`은 현재 `charId`만 보며, 이발사 교환도 `charId`만 맞바꿉니다. 건달·팡 구의 진영 변경을 저장할 필드도 없습니다.
   - 재현: 이발사가 죽은 뒤 선한 꿈꾸는 자와 악한 마녀의 캐릭터를 교환합니다. 이후 전자는 악, 후자는 선으로 잘못 집계되어 예언자·재봉사·얼뜨기·승리 판정 등이 뒤집힙니다. 팡 구 점프도 새 팡 구의 악 진영과 1회 사용 여부를 기록할 수 없습니다.
   - 기대 동작: 이발사 교환은 진영을 보존하며 악마 자신도 교환 대상으로 선택할 수 있고, “다른 악마”만 금지됩니다. [공식 이발사 규칙](https://wiki.bloodontheclocktower.com/Barber)
   - 제안 패치: 플레이어에 독립적인 `alignment`를 추가하고 `isEvil(p)`가 이를 읽게 하십시오. 이발사는 캐릭터만, 뱀 조련사는 캐릭터와 진영을, 건달·팡 구는 해당 플레이어의 진영만 명시적으로 갱신해야 합니다. 구버전 저장본에는 스키마 버전과 마이그레이션을 추가하고, 이미 교환된 게임은 진영 확인을 요청하는 편이 안전합니다. 752·3404행의 “악마 자신은 스왑 불가” 안내도 수정해야 합니다.

5. **공통 사망 판정기가 없어 보호 우선순위와 ‘처형됐지만 살았다’ 상태가 잘못 처리됨**

   - 위치/요약: [thyrsus/index.html:1718](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1718), [thyrsus/index.html:1675](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1675), [thyrsus/index.html:1988](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1988).
   - 재현:
     - 찻집 여인 보호 시 취소를 누르면 `executedToday`가 설정되지 않아 “처형 자체가 없었던 날”이 됩니다. 확인을 누르면 정상 작동하는 보호를 무시하고 죽일 수도 있습니다.
     - 악마의 변호사 단계는 안내문만 있고 상태 토큰/처형 분기가 없어 보호 대상이 죽습니다.
     - `doStepKill()`은 멀쩡한 선원과 여관 주인 보호를 검사하지 않습니다.
     - 정상·미소진 어릿광대에서 확인창을 취소하면 첫 생존 능력을 임의로 무시하고 죽일 수 있습니다. 공식 능력은 강제입니다. [공식 어릿광대 규칙](https://wiki.bloodontheclocktower.com/Fool)
     - 시장 대체 희생자는 살아 있는 사람만 고를 수 있고, 군인·수도사 보호도 무시합니다. 공식적으로 죽은 사람이나 보호된 사람을 대체 대상으로 고르면 아무도 죽지 않을 수 있습니다. [공식 시장 규칙](https://wiki.bloodontheclocktower.com/Mayor)
   - 기대 동작: “처형 발생”과 “사망 발생”은 분리되어야 합니다. 보호 우선순위를 적용한 뒤 실제로 죽을 때만 어릿광대 능력을 소진해야 합니다.
   - 제안 패치: 모든 경로가 사용하는 `attemptDeath(target, context)`와 `executePlayer()`를 만드십시오. 반환값을 `{executed, died, preventedBy}`로 만들고, 처형은 사망 여부와 무관하게 `executedToday`를 기록하십시오. 악마의 변호사·여관 주인 보호는 출처와 만료가 있는 상태로 실제 부여해야 합니다.

6. **상태가 출처 능력과 연결되지 않고 임시 취함도 영구 상태로만 표현됨**

   - 위치/요약: [thyrsus/index.html:852](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:852), [thyrsus/index.html:870](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:870), [thyrsus/index.html:3847](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3847), [thyrsus/index.html:723](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:723). 상태에는 사람이 읽는 `source` 문자열만 있고 `sourcePid`가 없습니다. `killPlayer()`도 출처가 사라진 효과를 정리하지 않으며, `drunkS`에는 만료가 없습니다.
   - 재현: 독살범이 A를 중독시킨 뒤 낮에 죽거나 다른 캐릭터가 되어도 A는 다음 밤까지 중독입니다. 선원·여관 주인·건달의 취함을 수동 토글하면 황혼에 해제되지 않습니다. 철학자가 죽거나 취해도 원래 능력 보유자의 “영구 취함”이 남습니다.
   - 기대 동작: 독살범이 더 이상 독살범 능력을 가지지 않으면 독이 즉시 끝나야 합니다. 철학자가 능력을 잃으면 원 보유자는 즉시 깨어나며, 선원·여관 주인·건달은 황혼, 궁정대신은 3밤+3낮에 끝나야 합니다. [독살범](https://wiki.bloodontheclocktower.com/Poisoner), [철학자](https://wiki.bloodontheclocktower.com/Philosopher), [건달](https://wiki.bloodontheclocktower.com/Goon)
   - 제안 패치: 상태를 `{key, sourcePid, sourceRole, expiryPolicy}`로 구조화하고 `phase`, `sourceAbility`, `duration` 만료 정책을 분리하십시오. 사망·캐릭터 변경·중독/취함 변경 때 `reconcileStatuses()`로 출처 의존 효과를 재평가해야 합니다.

7. **비고르모르티스가 죽인 하수인이 실제로는 능력을 잃음**

   - 위치/요약: [thyrsus/index.html:1718](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1718), [thyrsus/index.html:1428](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1428), [thyrsus/index.html:1855](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1855), [thyrsus/index.html:3395](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3395). 살해 함수는 하수인을 평범하게 죽이고, 밤 단계는 좀버얼을 제외한 모든 죽은 보유자를 건너뜁니다. 마녀 판정도 살아 있는 마녀만 찾습니다.
   - 재현: 비고르모르티스가 마녀를 죽입니다. 다음 밤 마녀 단계가 “사망 — 깨우지 않음”으로 건너뛰어지고, 기존 저주도 다음 밤 만료됩니다.
   - 기대 동작: 비고르모르티스가 죽인 모든 하수인은 비고르모르티스가 능력을 유지하는 동안 능력을 계속 가지며, 각각 주민 이웃 하나를 중독시킵니다. [공식 비고르모르티스 규칙](https://wiki.bloodontheclocktower.com/Vigormortis)
   - 제안 패치: 살해 시 `vigorAbility` 상태와 중독 대상 ID를 기록하고, `stepSkipReason()`과 마녀·쌍둥이 등 수동 판정은 `alive || hasActiveAbility(p)`를 사용하십시오. 비고르모르티스가 죽거나 오작동하면 연결된 능력·독을 재평가해야 합니다.

8. **BMR·SV 첫날 밤 순서가 공식 순서와 다르고 시트 렌더러가 배열 수정도 무시함**

   - 위치/요약: [thyrsus/index.html:803](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:803), [thyrsus/index.html:806](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:806), [thyrsus/index.html:1260](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1260).
   - 재현: BMR 첫밤은 `악마 정보 → 미치광이`로 표시되며, SV는 `하수인 정보 → 악마 정보 → 철학자`로 표시됩니다. `renderSheet()`는 어떤 에디션이든 정보 단계를 맨 앞에 다시 붙입니다.
   - 기대 동작: 공식 순서는 BMR이 `하수인 정보 → 미치광이 → 악마 정보`, SV가 `철학자 → 하수인 정보 → 악마 정보`입니다. [공식 밤 순서](https://release.botc.app/resources/data/nightsheet.json)
   - 제안 패치:
     ```js
     bmr.first = ['minioninfo','lunatic','demoninfo', /* ... */];
     sv.first  = ['philosopher','minioninfo','demoninfo', /* ... */];
     const firstFull = ed.first;
     ```

## Medium

9. **셋업 구성 계산이 남작만 지원함**

   - 위치/요약: [thyrsus/index.html:1043](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1043), [thyrsus/index.html:1202](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1202). 대부 ±1, 팡 구 +1, 비고르모르티스 −1 외지인 보정이 검증과 무작위 배정에 반영되지 않습니다.
   - 재현: 팡 구가 포함된 정상 구성에서 외지인을 하나 늘리면 “구성 불일치”가 나오며, SV 무작위 배정도 기본 구성으로 팡 구를 뽑을 수 있습니다.
   - 기대 동작: 역할의 공식 셋업 수정치를 반영해야 합니다. [공식 역할 데이터](https://release.botc.app/resources/data/roles.json)
   - 제안 패치: 선택된 역할 목록으로 `setupDelta`를 계산하고 주민/외지인 수에 적용하십시오. 대부는 `S.godfatherOutsiderDelta = -1 | 1` 선택값을 저장해야 합니다.

10. **지명 취소 시 해당 지명에서 소비한 사망 투표 토큰이 복원되지 않음**

   - 위치/요약: [thyrsus/index.html:1960](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1960), [thyrsus/index.html:1987](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1987). `castVote()`는 `deadVote=false`로 만들지만 `cancelNom()`은 지명만 삭제합니다.
   - 재현: 사망자가 찬성 또는 반대표를 낸 뒤 “지명 취소”를 누릅니다. 투표 기록은 사라지지만 토큰은 소진된 상태로 남습니다.
   - 기대 동작: 투표 자체가 취소되었으므로 그 지명에서 소비된 토큰도 복원되어야 합니다.
   - 제안 패치:
     ```js
     function cancelNom(nid) {
       const n = findNom(nid);
       for (const pid of n?.deadVoters || []) {
         const p = playerOf(pid);
         if (p) p.deadVote = true;
       }
       S.noms = S.noms.filter(x => x.id !== nid);
       // ...
     }
     ```

11. **집사의 무효 표가 경고만 표시되고 실제 집계에는 포함됨**

   - 위치/요약: [thyrsus/index.html:1956](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1956), [thyrsus/index.html:1977](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:1977). UI는 주인이 투표하지 않았다고 경고하지만 `n.hands.length`와 모든 `yes`를 그대로 셉니다.
   - 재현: 과반까지 한 표 부족한 상황에서 집사만 거수/찬성하고 주인은 참여하지 않습니다. 두 단계 모두 집사 표로 통과할 수 있습니다.
   - 기대 동작: 정상 작동하는 집사의 표는 같은 단계에서 주인도 투표할 때만 유효해야 합니다. [공식 집사 능력](https://release.botc.app/resources/data/roles.json)
   - 제안 패치: 마감 시 `validHands`와 `validYes`를 계산하거나, 집사가 선택할 때 주인의 동시 참여가 없으면 입력을 거부하십시오. 현재 2단계 UI 의미대로라면 주인의 찬성 여부를 기준으로 일관되게 집계해야 합니다.

12. **밤 위저드 대상 필터가 공식 선택 범위를 체계적으로 위반함**

   - 위치/요약: [thyrsus/index.html:2777](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:2777), [thyrsus/index.html:3314](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3314), [thyrsus/index.html:3333](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3333), [thyrsus/index.html:3349](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3349), [thyrsus/index.html:3371](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3371).
   - 재현:
     - 꿈꾸는 자는 여행자를 선택할 수 있습니다.
     - 재봉사는 자기 자신을 두 명 중 하나로 고를 수 있습니다.
     - 마귀할멈·세레노버스·도박사 및 여러 악마는 공식적으로 “플레이어”를 고르지만 위저드는 생존자만 보여줍니다.
     - 세레노버스의 광기 캐릭터 풀은 주민만 있어 외지인을 선택할 수 없습니다.
   - 기대 동작: 역할별로 `notSelf`, `notTraveller`, `aliveOnly`를 독립 적용해야 합니다. 꿈꾸는 자 제한과 재봉사 자기 제외 등은 [공식 역할 데이터](https://release.botc.app/resources/data/roles.json)에 명시되어 있습니다.
   - 제안 패치: 문자열 하나짜리 필터 대신 `{aliveOnly, excludeSelf, excludeTravellers}` 조건을 사용하고, `good` 캐릭터 풀을 주민+외지인으로 추가하십시오. 죽은 대상을 고른 살해는 “합법적인 선택이나 사망 없음”으로 기록해야 합니다.

13. **미치광이의 밤 지목을 진짜 악마에게 알려주는 것을 재량으로 안내함**

   - 위치/요약: [thyrsus/index.html:637](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:637), [thyrsus/index.html:3155](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3155).
   - 재현: 미치광이가 살해 대상을 고른 뒤 안내대로 진짜 악마에게 이를 전달하지 않고 진행합니다.
   - 기대 동작: 진짜 악마는 미치광이와 그가 밤에 고른 대상을 알아야 합니다. 선택적으로 그대로 죽일 수 있을 뿐, 대상 전달 자체는 재량이 아닙니다. [공식 미치광이 데이터](https://release.botc.app/resources/data/roles.json)
   - 제안 패치: “재량으로 전달”을 삭제하고, 미치광이를 재운 다음 진짜 악마를 깨워 미치광이 토큰과 대상 모두를 보여주는 필수 장면을 추가하십시오.

14. **노 다시 독 대상을 사망 때마다 재계산하라고 잘못 안내함**

   - 위치/요약: [thyrsus/index.html:791](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:791), [thyrsus/index.html:2713](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:2713), [thyrsus/index.html:3383](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3383).
   - 재현: 노 다시의 가장 가까운 주민 이웃이 죽으면 안내에 따라 그다음 살아 있는 주민으로 독 토큰을 옮깁니다.
   - 기대 동작: 생사와 관계없이 양방향의 가장 가까운 주민이 계속 중독됩니다. 캐릭터 타입 또는 노 다시 보유자가 바뀔 때만 대상이 달라질 수 있습니다. [공식 노 다시 규칙](https://wiki.bloodontheclocktower.com/No_Dashii)
   - 제안 패치: 세 안내문의 “사망 변동”을 삭제하고 “캐릭터 변경·노 다시 변경 시 재계산”으로 교체하십시오.

## Low

15. **곡예사를 고정된 둘째 밤에만 처리해 도중 생성된 곡예사가 능력을 못 씀**

   - 위치/요약: [thyrsus/index.html:733](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:733), [thyrsus/index.html:3430](/Users/kioxia/Downloads/jem_site/thyrsus/index.html:3430). “2일 밤에만”으로 고정되어 있습니다.
   - 재현: 마귀할멈이 셋째 밤에 플레이어를 곡예사로 만듭니다. 그 플레이어의 첫 낮 이후 밤에도 위저드는 둘째 밤 전용이라고 안내합니다.
   - 기대 동작: 곡예사는 게임의 첫날이 아니라 자신이 곡예사로서 맞는 첫날에 추측하고 그날 밤 결과를 받습니다. [공식 곡예사 능력](https://release.botc.app/resources/data/roles.json)
   - 제안 패치: `jugglerFirstDay`와 추측 기록을 플레이어별로 저장하고, 캐릭터 획득 다음 낮을 첫날로 설정하십시오. 고정된 `S.phase.n===2` 조건은 제거해야 합니다.