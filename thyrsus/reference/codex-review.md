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
---

# 2차 Codex 교차 검증 — 맥미니 로컬 세션

## 실행 정보
- 실행 일시: 2026-09-01 (맥미니, MACMINI-CODEX.md 방법 A)
- 도구: OpenAI Codex CLI **v0.152.0** · 샌드박스 `read-only`(index.html 수정 불가 보장)
- 입력: `codex-review-packet.md` 전문 (1차와 동일 조건, 기수정 16건 재보고 금지)
- 검토 대상 커밋: `757a81a` — index.html 내용은 1차와 동일(`b5ea4d3` 시점) 
- 토큰: 125,345 · 공식 근거: TPI roles.json / nightsheet.json + 공식 위키
- 1차(맥스튜디오)와 **독립 실행** — 1차 결과를 입력으로 주지 않았음

## 요약 (맥미니 Claude 정리)

**결함 13건** (Critical 4 · High 4 · Medium 5). 1차 15건과 교차하면 **독립 재현된 4건**이 특히 신뢰도가 높다.

| # | 심각도 | 결함 | 위치(라인) | 1차 대조 |
|---|--------|------|-----------|----------|
| 1 | Critical | 탕녀 계승이 상태에 미반영 — `charId` 미변경으로 이후 악마 없이 게임 진행 | 910, 4365 | **신규**. 1차 #1과 같은 `return null` 지점의 반대편 증상 |
| 2 | Critical | 중독·취한 좀버얼도 첫 사망을 무조건 무효화 (`fakedead` 선부여) | 873 | **신규** |
| 3 | Critical | `doStepKill()`이 군인 면역·여관주인 보호·선원을 무시 | 1718 | 1차 #5와 **독립 재현** |
| 4 | Critical | 커스텀 캐릭터 `id`가 `onclick`에 무검증 삽입 → 저장형 XSS | 2183, 2206 | 1차 #3과 **독립 재현** |
| 5 | High | 어릿광대 첫 생존을 확인창 취소로 무산 가능 (강제 능력인데 재량 처리) | 881 | 신규 |
| 6 | High | BMR·SV 첫날 밤 순서 불일치 (BMR: 하수인→미치광이→악마 / SV: 철학자→하수인→악마) | 803, 806 | 1차 #8과 **독립 재현·동일 결론** |
| 7 | High | 낮에 부여한 보호가 정작 쓸 밤 시작에 만료 (`{kind:'night',n+1}` 오류) | 1368, 3854 | 1차 #6 인접(다른 벡터) |
| 8 | High | 좀버얼 첫 사망에서 `checkEndConditions()` 자체를 건너뜀 | 874 | 신규 |
| 9 | Medium | 사망자 투표 토큰이 선택 변경·기권 시 복원됨 | 1963 | 1차 #10 인접(취소 vs 변경) |
| 10 | Medium | 동일인 재지명 최고율 2회를 "동률 처형 없음"으로 오처리 | 1803 | 신규 |
| 11 | Medium | 화가 안내가 정상 작동 중에도 무응답을 허용 | 727 | 신규 |
| 12 | Medium | 구버전 저장본 마이그레이션이 최상위 `Object.assign`뿐 — `deadVoters` 누락 시 예외 | 832, 1967, 3080 | 신규 |
| 13 | Medium | `cloudBuildDoc()`가 `#winask`·`#gameover` 오버레이를 비우지 않음 | 3037, 3040 | 1차 미보고 |

### 1·2차 종합 Critical 집합 (배포 전 필수 수정)
- **A.** 승리 차단(주모자·사악한 쌍둥이)이 `null` 반환 → `_orig()`가 "선한 팀 승리" 오선언 (1차 #1)
- **B.** 푸카가 `doPoison()` 재사용 → 중독 수명·지연 사망·오작동 판정 붕괴 (1차 #2)
- **C.** 탕녀 계승 미반영 → 악마 없는 게임 진행 (2차 #1)
- **D.** 오작동 좀버얼도 첫 사망 무효화 (2차 #2)
- **E.** `doStepKill()`이 군인·보호·선원 무시 (1차 #5 = 2차 #3, 독립 재현)
- **F.** 커스텀 캐릭터 `id` 저장형 XSS (1차 #3 = 2차 #4, 독립 재현)

### 주의사항
- Codex는 실행 검증 없이 정적 코드 경로 분석만 수행. 수정 후 브라우저 회귀 필수.
- 2차는 TB의 밤 순서 배열과 BMR/SV의 "그 외 밤" 배열에서는 추가 불일치를 찾지 못했다고 명시.

---

## Codex 원문 출력 (verbatim, 2차)

읽기 전용으로 검토했으며 파일은 수정하지 않았습니다. 공식 역할 데이터와 공식 밤 순서 JSON을 기준으로 대조했습니다. 자동 테스트 스위트는 저장소에 없어 정적 코드 경로 분석으로 재현 조건을 확인했습니다.

## 치명적

### 1. 탕녀 계승이 상태에 반영되지 않아 이후 게임이 악마 없이 진행됨

위치: [thyrsus/index.html:910](thyrsus/index.html:910), [thyrsus/index.html:4365](thyrsus/index.html:4365)

1. 결함 요약: 계승 조건을 감지해 안내만 할 뿐 탕녀의 `charId`를 죽은 악마로 변경하지 않는다. 이후 `demonAlive`는 계속 false이고 밤 순서에도 악마가 나타나지 않는다.
2. 재현 조건: 생존자 5명 이상에서 정상 작동 중인 탕녀가 있고 임프를 처형하거나 처단자로 죽인다.
3. 기대 동작: 탕녀가 즉시 임프로 바뀌고 이후 악마로 등록·행동해야 한다. 공식 규칙도 탕녀 토큰을 임프 토큰으로 교체하라고 명시한다. [Scarlet Woman 공식 위키](https://www.wiki.bloodontheclocktower.com/Scarlet_Woman)
4. 제안 패치: 계승을 별도 `promoteScarletWoman(deadDemonId)` 사건으로 구현해 `sw.charId=deadDemonId`와 관련 밤 순서·상태를 원자적으로 갱신한다. 단, 팡 구 점프 징크스는 이 경로를 호출하지 않아야 한다.

### 2. 중독·취한 좀버얼도 첫 사망을 무조건 무효화함

위치: [thyrsus/index.html:873](thyrsus/index.html:873)

1. 결함 요약: `killPlayer()`가 오작동 여부를 확인하기 전에 무조건 `fakedead`를 부여한다.
2. 재현 조건: 중독 또는 취한 좀버얼이 처음 죽는다.
3. 기대 동작: 오작동 상태에서는 첫 사망 생존 능력이 없으므로 실제로 죽고 선한 팀 승리를 판정해야 한다. [Zombuul 공식 위키](https://wiki.bloodontheclocktower.com/Zombuul)
4. 제안 패치: 첫 분기를 `p.charId==='zombuul' && !hasStatus(...,'fakedead') && !isMalfunctioning(p)`로 제한한다.

### 3. BMR/SV 악마 살해 자동화가 주요 생존·보호 능력을 무시함

위치: [thyrsus/index.html:1718](thyrsus/index.html:1718)

1. 결함 요약: `doStepKill()`은 찻집 여인만 자동 검사하고 곧바로 `killPlayer()`를 호출한다. 따라서 군인, 여관 주인 보호, 정상 선원 등이 샤발로스·포·팡 구 등에게 잘못 죽는다. 반대로 암살자만 찻집 여인을 관통하도록 특별 처리돼 있어 UI가 일부 자동화된 것처럼 보인다.
2. 재현 조건: 커스텀 시트의 군인을 BMR/SV 악마가 지목하거나, 여관 주인이 보호한 대상을 BMR 악마가 지목한다.
3. 기대 동작: 모든 악마 살해는 군인 면역과 해당 밤 보호를 적용해야 한다. 정상 선원은 사망 원인을 불문하고 죽지 않는다. 암살자만 이러한 방어를 관통한다. [Assassin 공식 위키](https://wiki.bloodontheclocktower.com/Assassin)
4. 제안 패치: `resolveDeathAttempt(target,{source,sourceType,bypassProtection})` 하나로 보호 우선순위를 통합하고 `doImpKill`과 `doStepKill`이 모두 사용하게 한다.

### 4. 가져온 커스텀 캐릭터 ID를 통한 저장형 XSS

위치: [thyrsus/index.html:2183](thyrsus/index.html:2183), [thyrsus/index.html:2206](thyrsus/index.html:2206)

1. 결함 요약: `importScript()`가 `customs`를 스키마 검증 없이 저장하고, `c.id`를 `onclick="delCustom('${c.id}')"`에 직접 삽입한다.
2. 재현 조건: `id`가 `x');alert(document.domain);//` 같은 커스텀 JSON을 가져온 뒤 커스텀 탭을 렌더링한다.
3. 기대 동작: 가져온 데이터는 HTML·JS 문맥을 탈출할 수 없어야 한다.
4. 제안 패치: 인라인 이벤트를 제거하고 `data-id`+`addEventListener`를 사용한다. 가져오기 시 ID를 안전한 내부 ID로 재발급하거나 `/^[A-Za-z0-9_-]+$/`로 제한하고 필드 타입·길이도 검증한다.

## 높음

### 5. 어릿광대의 첫 생존을 임의로 취소할 수 있음

위치: [thyrsus/index.html:881](thyrsus/index.html:881)

1. 결함 요약: 확인창에서 취소하면 정상 작동 중인 미사용 어릿광대가 그대로 죽는다.
2. 재현 조건: 정상 어릿광대의 첫 사망에서 확인창의 취소를 선택한다.
3. 기대 동작: “처음 죽게 될 때 죽지 않는다”는 강제 능력이다. 사회자 재량이 아니다. 암살자 또는 오작동처럼 능력을 우회하는 원인만 예외다. [Fool 공식 위키](https://wiki.bloodontheclocktower.com/Fool)
4. 제안 패치: 정상적인 첫 사망에서는 확인 없이 자동으로 `spent`를 부여하고 사망을 막는다. 확인창은 진단 안내만 제공하거나 제거한다.

### 6. 공식 밤 순서와 다른 첫날 밤 배열

위치: [thyrsus/index.html:803](thyrsus/index.html:803), [thyrsus/index.html:806](thyrsus/index.html:806)

1. 결함 요약:
   - BMR은 `minioninfo → demoninfo → lunatic`이지만 공식 순서는 `minioninfo → lunatic → demoninfo`.
   - SV는 `minioninfo → demoninfo → philosopher`이지만 공식 순서는 `philosopher → minioninfo → demoninfo`.
2. 재현 조건: BMR 또는 SV 첫날 밤 위저드를 실행한다.
3. 기대 동작: 공식 전체 밤 순서에서 해당 에디션 역할만 필터링한 순서와 같아야 한다. [공식 nightsheet.json](https://release.botc.app/resources/data/nightsheet.json)
4. 제안 패치:
   - BMR 시작부를 `['minioninfo','lunatic','demoninfo', ...]`
   - SV 시작부를 `['philosopher','minioninfo','demoninfo', ...]`
   로 변경한다.

### 7. 낮에 수동 부여한 보호가 사용할 밤 시작과 동시에 만료됨

위치: [thyrsus/index.html:1368](thyrsus/index.html:1368), [thyrsus/index.html:3854](thyrsus/index.html:3854)

1. 결함 요약: 낮에 보호를 추가하면 만료를 `{kind:'night', n:ph.n+1}`로 설정한다. `advancePhase()`가 바로 그 밤 시작에 `expireStatuses()`를 호출하므로 보호가 한 번도 작동하지 않는다.
2. 재현 조건: 낮 1에 보호 토큰을 수동 추가하고 밤 2로 진행한다.
3. 기대 동작: 밤 2 동안 유지되고 낮 2 시작에 해제돼야 한다.
4. 제안 패치: 낮에 다음 밤용으로 부여할 때 `{kind:'day', n:ph.n+1}`을 사용한다. 두 중복 구현을 공통 만료 계산 함수로 합친다.

### 8. 좀버얼 첫 사망에서 승리·생존 2인 판정 자체를 건너뜀

위치: [thyrsus/index.html:874](thyrsus/index.html:874)

1. 결함 요약: 죽은 척 처리 후 즉시 `return`하여 `checkEndConditions()`를 부르지 않는다.
2. 재현 조건: 겉보기 생존자가 좀버얼 포함 3명일 때 좀버얼이 처음 “죽는다”. 타운스퀘어상 생존자는 2명만 남는다.
3. 기대 동작: 좀버얼 특례에 따라 게임은 계속되지만, 일반 “악마 생존+생존 2인” 자동 승리와 명확히 구분해 판정해야 한다. 현재는 우연히 판정 전체를 생략해 작동한다.
4. 제안 패치: `evalWinEvent`에 `zombuulFakeDeath` 사건을 명시하고, 일반 2인 승리 규칙의 예외로 처리한다. 숨은 생존 여부를 `alive`와 별도 필드로 모델링하는 편이 안전하다.

## 중간

### 9. 사망자의 투표 선택 취소·기권 시 이미 쓴 토큰이 복원됨

위치: [thyrsus/index.html:1963](thyrsus/index.html:1963)

1. 결함 요약: 사망자가 찬성/반대를 누른 뒤 같은 선택을 취소하거나 기권으로 바꾸면 `deadVote=true`로 복원된다.
2. 재현 조건: 사망자가 2차 투표에서 찬성을 누른 뒤 다시 찬성 또는 기권을 누른다.
3. 기대 동작: 요청된 하우스룰의 “사망 토큰 1회 소진”이라면 유효 투표를 행사한 순간 영구 소진돼야 한다. UI 수정은 가능하되 토큰은 복원하지 않아야 한다.
4. 제안 패치: `deadVote`와 현재 선택을 분리한다. 최초 yes/no에 `deadVote=false`를 고정하고 이후 선택 변경은 `votes[pid]`만 변경한다.

### 10. 동일 피지명자의 동일 최고율 결과도 “동률 처형 없음”으로 처리됨

위치: [thyrsus/index.html:1803](thyrsus/index.html:1803)

1. 결함 요약: 동률을 지명 레코드 단위로 계산한다. 같은 사람을 재지명해 같은 최고 찬성률을 두 번 받으면 서로 다른 처형 후보가 아닌데도 `tie=true`가 된다.
2. 재현 조건: A를 두 번 지명하고 두 투표 모두 같은 최고 찬성률로 통과시킨다.
3. 기대 동작: “찬성률 최고자”가 한 명이면 A가 처형 후보여야 한다. 서로 다른 피지명자가 최고율일 때만 동률이다.
4. 제안 패치: 최고율 레코드들의 `nominee`를 `Set`으로 모아 서로 다른 ID가 2개 이상일 때만 동률로 처리한다.

### 11. 화가 안내가 정상 작동 중에도 사회자의 무응답을 허용함

위치: [thyrsus/index.html:727](thyrsus/index.html:727)

1. 결함 요약: `warn`에 “예/아니오/고개젓기(무응답)”라고 적혀 있다.
2. 재현 조건: 정상 작동 중인 화가가 유효한 예/아니오 질문을 한다.
3. 기대 동작: 사회자는 진실한 예 또는 아니오를 제공해야 한다. 질문이 유효한 예/아니오 질문이 아니면 재질문을 요청해야지 무응답을 규칙상 제3의 답으로 사용하면 안 된다. 공식 능력 원문은 “you learn a truthful answer”다. [공식 roles.json](https://release.botc.app/resources/data/roles.json)
4. 제안 패치: “유효한 질문이면 반드시 진실한 예/아니오. 형식이 부적절하면 다시 질문하도록 안내”로 교체한다.

### 12. 구버전 활성 지명 저장본은 투표 시 예외가 날 수 있음

위치: [thyrsus/index.html:832](thyrsus/index.html:832), [thyrsus/index.html:1967](thyrsus/index.html:1967), [thyrsus/index.html:3080](thyrsus/index.html:3080)

1. 결함 요약: 마이그레이션이 최상위 `Object.assign`뿐이다. 구버전 진행 중 지명에 `deadVoters`가 없으면 사망자 투표 시 `n.deadVoters.includes(...)`에서 예외가 발생한다. 클라우드 복원도 동일하다.
2. 재현 조건: `noms` 내 활성 지명에 `deadVoters`가 없는 구 저장본을 로드한 뒤 사망자가 찬성/반대한다.
3. 기대 동작: 신규 필드가 누락된 저장본도 기본값을 보충해 정상 동작해야 한다.
4. 제안 패치: `migrateState(raw)`에서 플레이어와 지명 각각을 정규화한다. 최소한 `statuses`, `notes`, `deadVote`, `hands`, `votes`, `deadVoters`, `closed`, `stage`를 타입 검사 후 기본값으로 채운다.

### 13. 클라우드 문서가 승리 확인·게임 종료 오버레이를 비우지 않음

위치: [thyrsus/index.html:3037](thyrsus/index.html:3037), [thyrsus/index.html:3040](thyrsus/index.html:3040)

1. 결함 요약: `cloudBuildDoc()`는 탭·wizard·pmodal만 정리한다. `#winask`와 `#gameover`의 동적 `innerHTML` 및 표시 상태는 복제본에 남는다.
2. 재현 조건: 승리 확인창 또는 게임 종료 화면이 열린 상태에서 클라우드 저장한다.
3. 기대 동작: 발행 문서는 정적 셸과 `cloudstate`만 포함하고 모든 일시적 오버레이는 숨김·비움 상태여야 한다.
4. 제안 패치: 동적 루트 allowlist 대신 `#wizard,#pmodal,#winask,#gameover`를 모두 `hidden=true; innerHTML=''`로 정규화하고, 저장 결과 문서에 열린 오버레이가 없는지 계약 테스트를 추가한다.

참고로 플레이어 이름과 메모의 일반 렌더링은 대부분 `esc()`를 통과했습니다. 가장 직접적인 XSS 경로는 검증되지 않은 커스텀 `id`와 저장·복원된 내부 ID가 인라인 이벤트 속성에 들어가는 부분입니다. 또한 공식 밤 순서 기준으로 TB의 배열과 BMR/SV의 그 외 밤 배열에서는 추가 순서 불일치를 발견하지 못했습니다.

---

# 수정 현황 (2026-09-01, 맥미니)

## 배포 전 수정 완료 — 종합 Critical 6건 (A~F)

| 코드 | 결함 | 수정 내용 |
|------|------|-----------|
| A | 승리 차단이 `null` → `_orig()`가 "선한 팀 승리" 오선언 | `evalWinEvent`가 `{kind:'continue', why}` 를 반환하도록 변경. `isWinRes()`/`announceContinue()` 신설, 호출부 4곳 모두 분기. 주모자 연장전은 `S.mastermindDay` 로 영속화하고 **연장된 낮의 처형 결과(악 처형=선 승리 / 무처형·선 처형=악 승리)를 dayEnd 에서 실제 판정** |
| B | 푸카가 `doPoison()` 재사용 | `doPukkaPick()` 신설. 페이즈 만료 없는 독 부여 → 이전 희생자 사망·해독 순서, `S.pukkaVictimId` 영속화, 오작동 시 신규 중독·지연 사망 모두 보류. 위저드 first/other 를 신규 함수로 교체 |
| C | 탕녀 계승이 안내뿐이라 악마 없는 게임 진행 | `promoteScarletWoman()` 신설 — `killPlayer()` 안에서 `charId` 를 실제 전환. 다른 악마 생존 시(팡 구 점프) 미발동, 별 넘기기 경로는 `skipSuccession` 으로 중복 계승 차단, 오작동 탕녀는 계승 불발 안내 |
| D | 오작동 좀버얼도 첫 사망 무효화 | `killPlayer()` 의 좀버얼 분기에 `!isMalfunctioning(p)` 추가 |
| E | `doStepKill()` 이 군인·보호·선원 무시 | `deathBlockReason()` 공용 판정 신설 — `doImpKill`·`doStepKill` 양쪽이 동일 규칙 사용. 암살자만 관통 |
| F | 커스텀 캐릭터 `id` 저장형 XSS | 인라인 `onclick` 제거 → `data-delcustom` + 위임 리스너. `importScript()` 에 스키마·타입·길이 검증과 안전 id 재발급(`/^[A-Za-z0-9_-]{1,64}$/`) 추가 |

부수 변경: `blank()` 에 `pukkaVictimId`·`mastermindDay`·`executedTodayPid` 추가(구 저장본은 `Object.assign` 으로 기본값 보충), `executeNominee` 가 처형자 pid 기록.

## 검증
- `node --check`: HTML 내 스크립트 블록 19개 전부 통과
- 브라우저 시나리오 회귀 **28건 전부 통과** — A~F 타깃 테스트 21건 + 기존 기능 회귀 7건
  (전 탭 렌더, 3개 에디션 밤 순서, 지명→거수→찬반 투표, 별 넘기기 악마 유일성, 상태 직렬화 왕복, 차단 요소 없을 때의 정상 선 승리 경로)

## 미수정 — 후속 과제
1·2차 종합 High 이하 **22건**은 이번 배포에 포함하지 않았다. 우선순위 상위:
- 진영을 `charId` 에서 유도(이발사 교환·건달·팡 구 진영 오염) — `alignment` 필드 도입 필요
- 상태에 `sourcePid` 없음 → 출처 사망 시 중독·취함 잔존
- BMR·SV 첫날 밤 순서(1·2차 독립 동일 결론): BMR `하수인→미치광이→악마`, SV `철학자→하수인→악마`
- 낮에 부여한 보호가 쓸 밤 시작에 만료
- 어릿광대 첫 생존이 확인창 취소로 무산 가능(강제 능력)
- 좀버얼 첫 사망에서 `checkEndConditions()` 자체를 건너뜀
- 구버전 저장본 마이그레이션이 최상위 `Object.assign` 뿐(`deadVoters` 누락 시 예외)

---

# 3차 Codex 정밀 검증 — 맥스튜디오 (밤 진행 · 캐릭터 구현 전수)

## 실행 정보
- 실행 일시: 2026-09-01 (맥스튜디오, `codex exec --sandbox read-only -c model_reasoning_effort=xhigh`)
- 도구: OpenAI Codex CLI v0.150.1 · 모델 `gpt-5.6-sol` · reasoning effort **xhigh**
- 검토 대상 커밋: `34b385b` (PR #6 머지 = **1·2차 Critical 6건 수정 반영본**)
- 초점: 1·2차의 엔진 수준 결함이 아니라 **밤 순서 인덱스 단위 대조 · 캐릭터 72종 전수 · 위저드 씬 전수 · 상태 수명주기**
- 기수정 22건 + 백로그 16건을 재보고 금지로 명시 — 아래는 전부 신규

## 요약

**신규 결함 23건** (Critical 3 · High 9 · Medium 8 · Low 3).

### 밤 순서 대조 결론
- **TB 첫날·이후 배열 모두 공식과 완전 일치** (누락·여분·역전 0)
- **BMR 이후 밤 19단계, SV 이후 밤 19단계도 완전 일치**
- 불일치는 **BMR·SV 첫날 밤의 3자 배치뿐** — 이미 백로그인 건과 동일. 다만 `renderSheet()`가 첫날 배열을 무시하고 `minioninfo`·`demoninfo`를 강제 선두 배치하므로 **배열만 고쳐도 시트는 계속 틀린다**
- 캐릭터 72종의 `first`/`other` 플래그는 공식 `roles.json` 과 **전부 일치**

### Critical 3건 — ⚠ 2건은 이번 세션(A~F) 수정분의 결함
| # | 결함 | 비고 |
|---|------|------|
| 1 | 푸카 희생자의 독을 **사망 전에** 제거 + 그 사망 경로에 보호 판정 없음 | **A~F의 B 수정분 결함.** 공식은 "죽고 나서 건강해진다" — 독이 살아 있어야 어릿광대 1회 생존이 막히고 까마귀지기·현자가 거짓 정보를 받는다 |
| 2 | 처형과 사망을 혼동 — 선원·악마의 변호사·평화주의자 미확인, 찻집 여인 보호가 처형 자체를 취소해 `executedToday` 미기록(보르톡스 오판정), 장의사가 "처형됐지만 안 죽은" 대상을 봄 | 기존 결함 |
| 3 | `deathBlockReason()`이 **대상이 오작동이면 외부 보호까지 무효화** | **A~F의 E 수정분 결함.** 공식: 취하거나 중독된 대상에게 사용된 *다른 플레이어의* 능력은 정상 작동. 수도사는 악마로부터만, 여관 주인은 모든 밤 사망으로부터 보호 |

### High 9건
사망 트리거 역할이 밤 실행 큐에서 누락·반복 · 구마사제 판정이 악마 단계와 미연결 · 달의 자손 오작동 판정 시점·주체 · 팡 구 점프가 "죽였는가"가 아니라 "외지인 지목"으로 발동 · 꿈꾸는 자 WIZ 대상·토큰 계약 위반 · 세레노버스가 사망자·외지인 광기 선택 불가 · 이발사 안내가 악마 자신의 스왑 금지 · 백치천재의 보르톡스 지침이 정반대 · 임시 취함을 영구 상태로만 표현

### Medium 8 / Low 3
오작동 정보 "반드시 거짓" 전역 오안내 · 다수 `pick-player`가 공식상 가능한 사망자 숨김 · 샤발로스·포 중복 선택 · 수학자 범위 과대 집계 · 도박사 경고에 없는 등록 재량 · 캐릭터 변경 시 타 능력 상태 일괄 삭제 · 밤 순서 미리보기가 에디션 무시하고 TB 표시 · 철학자·재봉사·사랑꾼 선택 검증 불완전 / 음유시인 여행자 예외 누락 · 중독된 암살자 소진을 재량으로 안내 · 시트의 이후 밤 행이 첫날 가이드 표시

---

## Codex 원문 출력 (verbatim, 3차)

읽기 전용으로 전수 검증했다. 파일은 수정하지 않았다.

결론부터 말하면 신규 결함은 **Critical 3건, High 9건, Medium 8건, Low 3건**이다. 이미 완료·백로그로 명시된 항목은 제외했다. 기준 데이터는 TPI 공식 [`nightsheet.json`](https://release.botc.app/resources/data/nightsheet.json), [`roles.json`](https://release.botc.app/resources/data/roles.json), [공식 위키](https://wiki.bloodontheclocktower.com/)다.

## A. 밤 순서 전수 대조

황혼·새벽은 배열 밖에서 렌더러가 삽입하므로 역할 인덱스에서는 제외했다.

### Trouble Brewing

| 밤 | 공식 순서 | 현재 배열 | 판정 |
|---|---|---|---|
| 첫날 | 1 `minioninfo` → 2 `demoninfo` → 3 `poisoner` → 4 `washerwoman` → 5 `librarian` → 6 `investigator` → 7 `chef` → 8 `empath` → 9 `fortuneteller` → 10 `butler` → 11 `spy` | 동일 | 누락·여분·역전 없음 |
| 이후 | 1 `poisoner` → 2 `monk` → 3 `scarletwoman` → 4 `imp` → 5 `ravenkeeper` → 6 `empath` → 7 `fortuneteller` → 8 `undertaker` → 9 `butler` → 10 `spy` | 동일 | 누락·여분·역전 없음 |

현재 배열: [thyrsus/index.html:554](thyrsus/index.html:554)

### Bad Moon Rising

| 밤 | 공식 순서 | 현재 배열 | 판정 |
|---|---|---|---|
| 첫날 | 1 `minioninfo` → 2 `lunatic` → 3 `demoninfo` → 4 `sailor` → 5 `courtier` → 6 `godfather` → 7 `devilsadvocate` → 8 `pukka` → 9 `grandmother` → 10 `chambermaid` | 1 `minioninfo` → 2 `demoninfo` → 3 `lunatic` → 나머지 동일 | `lunatic`/`demoninfo` 역전. 이미 백로그인 3자 배치 건 |
| 이후 | 1 `sailor` → 2 `courtier` → 3 `innkeeper` → 4 `gambler` → 5 `devilsadvocate` → 6 `lunatic` → 7 `exorcist` → 8 `zombuul` → 9 `pukka` → 10 `shabaloth` → 11 `po` → 12 `assassin` → 13 `godfather` → 14 `gossip` → 15 `professor` → 16 `tinker` → 17 `moonchild` → 18 `grandmother` → 19 `chambermaid` | 동일 | 누락·여분·역전 없음 |

현재 배열: [thyrsus/index.html:802](thyrsus/index.html:802)

### Sects & Violets

| 밤 | 공식 순서 | 현재 배열 | 판정 |
|---|---|---|---|
| 첫날 | 1 `philosopher` → 2 `minioninfo` → 3 `demoninfo` → 4 `snakecharmer` → 5 `eviltwin` → 6 `witch` → 7 `cerenovus` → 8 `clockmaker` → 9 `dreamer` → 10 `seamstress` → 11 `mathematician` | 1 `minioninfo` → 2 `demoninfo` → 3 `philosopher` → 나머지 동일 | `philosopher`가 두 정보 단계 뒤로 이동. 이미 백로그인 3자 배치 건 |
| 이후 | 1 `philosopher` → 2 `snakecharmer` → 3 `witch` → 4 `cerenovus` → 5 `pithag` → 6 `fanggu` → 7 `nodashii` → 8 `vortox` → 9 `vigormortis` → 10 `barber` → 11 `sweetheart` → 12 `sage` → 13 `dreamer` → 14 `flowergirl` → 15 `towncrier` → 16 `oracle` → 17 `seamstress` → 18 `juggler` → 19 `mathematician` | 동일 | 누락·여분·역전 없음 |

현재 배열: [thyrsus/index.html:805](thyrsus/index.html:805)

`renderSheet()`가 첫날 배열을 무시하고 `minioninfo`·`demoninfo`를 강제로 선두 배치한다([thyrsus/index.html:1292](thyrsus/index.html:1292)). 따라서 배열만 고쳐도 BMR/SV 시트는 계속 틀린다. 이 부분은 명시된 기존 백로그와 동일하므로 신규 finding으로 세지 않았다.

`nightSteps()`는 기본 배열을 재정렬하지 않으며, 커스텀 역할과 TB 주정뱅이 위장 단계만 위치 삽입한다([thyrsus/index.html:1412](thyrsus/index.html:1412)).

### `first` / `other` 플래그

공식 `roles.json`의 `firstNightReminder`/`otherNightReminder` 존재 여부와 **72종 전부 일치**했다.

| 에디션 | 첫날만 | 둘 다 | 이후만 | 밤 플래그 없음 |
|---|---|---|---|---|
| TB | 세탁부, 사서, 수사관, 요리사 | 초공감자, 점쟁이, 집사, 독살범, 첩자 | 장의사, 수도사, 까마귀지기(조건부), 탕녀(조건부), 임프 | 성결자, 처단자, 군인, 시장, 주정뱅이, 은둔자, 성자, 남작 |
| BMR | 없음 | 할머니, 선원, 객실 청소부, 궁정대신, 미치광이, 대부, 악마의 변호사, 푸카 | 구마사제, 여관 주인, 도박사, 험담꾼, 교수, 땜장이, 달의 자손, 암살자, 좀버얼, 샤발로스, 포 | 음유시인, 찻집 여인, 평화주의자, 어릿광대, 건달, 주모자 |
| SV | 시계공, 사악한 쌍둥이 | 꿈꾸는 자, 뱀 조련사, 수학자, 재봉사, 철학자, 마녀, 세레노버스 | 꽃팔이 소녀, 포고꾼, 예언자, 곡예사, 현자, 사랑꾼, 이발사, 마귀할멈, 팡 구, 노 다시, 보르톡스, 비고르모르티스 | 백치천재, 화가, 변종, 얼뜨기 |

조건부 플래그의 존재 자체도 맞다. 문제는 아래 High finding처럼 실행 큐가 그 조건을 제대로 추적하지 않는다는 점이다.

---

## Critical

### 1. 푸카 희생자의 독을 사망 전에 제거한다

[thyrsus/index.html:1702](thyrsus/index.html:1702), [thyrsus/index.html:1715](thyrsus/index.html:1715)

1. **결함:** 이전 희생자의 푸카 독을 먼저 제거한 뒤 `resolveNightDeath()`를 호출한다. 또한 이 경로는 여관 주인·찻집 여인 같은 밤 사망 보호를 전혀 확인하지 않는다.
2. **재현:** 푸카가 어릿광대를 중독시킨 뒤 다음 밤 새 대상을 문다. 현재는 어릿광대의 독이 먼저 풀려 1회 생존이 작동할 수 있다. 푸카가 현자·까마귀지기를 죽인 경우에도 건강한 상태로 사망 능력이 처리된다. 여관 주인 보호 대상도 직접 사망한다.
3. **기대:** 푸카 희생자는 **사망 순간까지 중독**되어 있어 어릿광대 능력이 작동하지 않고, 현자 등은 거짓 정보를 받을 수 있다. 보호되어 죽지 않은 경우에도 이후 건강해진다. [Pukka 공식 위키](https://wiki.bloodontheclocktower.com/Pukka)
4. **제안 패치:** 새 대상을 먼저 중독시키고, 이전 대상에게 공용 밤 사망 보호 판정을 적용한 뒤, 독을 유지한 상태로 사망·사망 능력을 전부 해결하고 마지막에 푸카 독만 제거한다. `pukkaVictimId`와 독 토큰을 별도 pending-effect 구조로 관리한다.

### 2. 처형과 사망을 혼동해 BMR 핵심 능력을 무시한다

[thyrsus/index.html:1937](thyrsus/index.html:1937), [thyrsus/index.html:2053](thyrsus/index.html:2053)

1. **결함:** 일반 처형과 성결자 처형 모두 `killPlayer()`를 바로 호출한다. 정상 선원, 악마의 변호사 보호, 평화주의자 재량을 확인하지 않는다. 찻집 여인 보호는 반대로 “처형 자체”를 취소하고 `executedToday`도 기록하지 않는다. 어릿광대처럼 처형됐지만 살지 않은 대상은 장의사에게 잘못 안내된다.
2. **재현:** 정상 선원을 처형하면 죽는다. 악마의 변호사가 보호한 대상을 처형해도 죽는다. 찻집 여인 이웃 처형에서 취소를 선택하면 보르톡스 기준으로 “오늘 처형 없음”이 된다. 어릿광대가 처형을 버텨도 장의사에게 해당 토큰을 보여주라고 안내한다.
3. **기대:** 처형은 사망과 별개다. 보호되어 살아도 그날 처형은 소모되고 보르톡스 조건을 만족한다. 장의사는 **처형으로 실제 죽은** 캐릭터만 본다. [States](https://wiki.bloodontheclocktower.com/States), [Undertaker](https://wiki.bloodontheclocktower.com/Undertaker), [Pacifist](https://wiki.bloodontheclocktower.com/Pacifist), [Sailor](https://wiki.bloodontheclocktower.com/Sailor)
4. **제안 패치:** `resolveExecution()`을 만들고 `executionOccurred`, `diedByExecutionPid`를 분리한다. 선원·악마의 변호사·찻집 여인·평화주의자·어릿광대 판정을 한 곳에서 처리하며, 성결자 경로도 동일 함수를 사용한다. 장의사는 `diedByExecutionPid`만 참조해야 한다.

### 3. 대상의 중독·취함이 외부 보호까지 무효화한다

[thyrsus/index.html:873](thyrsus/index.html:873), [thyrsus/index.html:1775](thyrsus/index.html:1775)

1. **결함:** `deathBlockReason()`이 대상이 오작동 상태면 즉시 `null`을 반환한다. 따라서 수도사·여관 주인이 준 외부 보호도 함께 사라진다. 반대로 `doStepKill()`은 살해 출처를 구분하지 않아 군인·수도사 보호가 험담꾼·대부·달의 자손 같은 비악마 사망도 막을 수 있다.
2. **재현:** 여관 주인이 두 명을 보호하고 그중 한 명을 취하게 한 뒤 악마가 그 취한 플레이어를 공격하면 현재 사망한다. 교차 스크립트에서는 수도사 보호 대상이 중독돼도 같은 문제가 난다.
3. **기대:** 취하거나 중독된 **대상에게 사용된 다른 플레이어의 능력은 정상 작동**한다. 수도사는 악마로부터만, 여관 주인은 모든 밤 사망으로부터 보호한다. [States](https://wiki.bloodontheclocktower.com/States), [Monk](https://wiki.bloodontheclocktower.com/Monk), [Innkeeper](https://wiki.bloodontheclocktower.com/Innkeeper)
4. **제안 패치:** 외부 보호와 대상 자신의 면역을 분리한다. `deathBlockReason(target, {sourceType, atNight, ignoresProtection})` 형태로 살해 출처를 전달하고, 대상 오작동은 군인·선원 같은 자기 능력에만 적용한다.

---

## High

### 4. 사망 트리거 역할이 전체 밤 실행에서 누락되거나 반복된다

[thyrsus/index.html:1460](thyrsus/index.html:1460), [thyrsus/index.html:2838](thyrsus/index.html:2838), [thyrsus/index.html:4011](thyrsus/index.html:4011)

1. **결함:** 사망한 까마귀지기는 “오늘 밤 사망” 여부와 무관하게 이후 매일 실행 가능하다. 반면 사망한 현자·이발사·사랑꾼·달의 자손은 일반 사망 필터로 전체 밤 큐에서 빠진다. `startWiz()`도 살아있는 holder만 찾는다.
2. **재현:** 2일 밤 까마귀지기가 죽고 발동한 뒤 3일 밤 전체 진행을 시작하면 다시 큐에 들어간다. 같은 밤 악마에게 죽은 현자는 큐에서 제외된다.
3. **기대:** 까마귀지기와 현자는 사망 즉시/해당 밤 한 번만, 이발사·사랑꾼은 오늘 죽었을 때 한 번만 처리되어야 한다. [Abilities](https://wiki.bloodontheclocktower.com/Abilities), [Ravenkeeper](https://wiki.bloodontheclocktower.com/Ravenkeeper), [Barber](https://wiki.bloodontheclocktower.com/Barber)
4. **제안 패치:** 사망 이벤트에 `phase`, `night`, `cause`, `resolvedTriggers`를 기록한다. `stepSkipReason()`은 현재 생존 여부가 아니라 미해결 이벤트를 검사하고, 위저드 holder도 해당 이벤트의 사망자를 사용한다.

### 5. 구마사제 판정이 실제 악마 단계에 연결되지 않는다

[thyrsus/index.html:1664](thyrsus/index.html:1664), [thyrsus/index.html:3245](thyrsus/index.html:3245)

1. **결함:** `doExorcist()`는 토스트만 띄우고 악마 단계 차단 상태를 기록하지 않는다. 전체 밤 큐는 이후 악마 위저드를 정상 실행한다. 푸카를 구마한 경우 “새 중독은 없음, 이전 독 피해는 사망”이어야 하지만 현재 두 효과가 `doPukkaPick()` 하나에 결합돼 있다.
2. **재현:** 구마사제가 실제 악마를 골라 판정한 뒤 전체 진행을 계속하면 해당 악마 WIZ가 열린다. 푸카 WIZ를 닫으면 이전 희생자도 죽지 않고, 실행하면 새 희생자까지 중독된다.
3. **기대:** 선택된 악마는 깨어나 자신의 능력을 사용하지 않는다. 단, 푸카의 이전 공격으로 인한 사망은 계속 해결된다. [Exorcist](https://wiki.bloodontheclocktower.com/Exorcist), [Pukka](https://wiki.bloodontheclocktower.com/Pukka)
4. **제안 패치:** `demonBlockedNight`를 저장해 큐에서 악마의 선택·공격 장면만 건너뛴다. 푸카는 `resolvePendingPukkaDeath()`와 `chooseNewPukkaVictim()`을 분리한다.

### 6. 달의 자손 오작동 판정 시점과 선택 주체가 틀리다

[thyrsus/index.html:644](thyrsus/index.html:644), [thyrsus/index.html:3316](thyrsus/index.html:3316)

1. **결함:** “중독 상태로 죽었으면 발동 없음”이라고 하지만 실제 판정 시점은 대상이 죽는 **그날 밤**이다. WIZ도 사회자가 선택하는 장면(`who:'st'`)으로 표시한다.
2. **재현:** 달의 자손이 중독 상태로 낮에 죽어 대상을 지목한 뒤 밤에 건강해지면 현재 불발 안내지만 공식상 대상은 죽는다. 반대 상황도 역전된다.
3. **기대:** 달의 자손이 사망 사실을 알게 된 직후 직접 생존자 한 명을 공개 선택한다. 대상의 선악은 선택 시점, 달의 자손의 건강은 밤 사망 해결 시점 기준이다. [Moonchild](https://wiki.bloodontheclocktower.com/Moonchild)
4. **제안 패치:** `moonchildChoice={pid,targetPid,alignmentAtChoice}`를 저장하고 밤에 source의 현재 오작동 상태를 검사한다. WIZ 선택 주체는 `player`로 바꾼다.

### 7. 팡 구 점프가 “죽였는가”가 아니라 “외지인을 지목했는가”로 발동한다

[thyrsus/index.html:778](thyrsus/index.html:778), [thyrsus/index.html:3463](thyrsus/index.html:3463)

1. **결함:** 외지인 지목 즉시 일반 사망 판정을 건너뛰고 점프하라고 안내한다.
2. **재현:** 여관 주인 등으로 보호된 외지인을 팡 구가 공격하면 현재 새 팡 구가 생기고 기존 팡 구가 죽는다.
3. **기대:** 첫 외지인을 **팡 구가 죽였을 때만** 점프한다. 외지인이 죽지 않았다면 점프도 없다. [Fang Gu](https://wiki.bloodontheclocktower.com/Fang_Gu)
4. **제안 패치:** 먼저 Demon 사망 판정을 수행해 실제 `alive→dead` 전이가 가능한지 확인하고, 성공했을 때 그 사망을 점프로 치환한다.

### 8. 꿈꾸는 자 WIZ가 대상·토큰 계약을 모두 위반할 수 있다

[thyrsus/index.html:692](thyrsus/index.html:692), [thyrsus/index.html:3419](thyrsus/index.html:3419)

1. **결함:** 죽은 플레이어를 선택할 수 없고 여행자를 선택할 수 있다. 선·악 토큰 풀이 둘 다 `any`라서 같은 진영 둘을 고르거나 실제 캐릭터가 없는 쌍을 보여줄 수 있다. 능력 요약도 여행자 제외를 누락했다.
2. **재현:** 죽은 플레이어는 버튼에 나타나지 않는다. `goodTok`에서 악마, `evilTok`에서 주민을 선택할 수 있다.
3. **기대:** 자신과 여행자를 제외한 살아있거나 죽은 플레이어를 고르고, 선한 캐릭터 하나와 악한 캐릭터 하나를 보여주며 둘 중 하나는 대상의 실제 캐릭터여야 한다. [Dreamer](https://wiki.bloodontheclocktower.com/Dreamer)
4. **제안 패치:** `any-not-self-not-traveller`, `good-characters`, `evil-characters` 필터를 추가하고 건강한 경우 실제 토큰 하나를 자동 고정한다. 보르톡스/오작동 때만 올바른 거짓 계약을 별도로 계산한다.

### 9. 세레노버스가 죽은 대상과 외지인 광기를 선택할 수 없다

[thyrsus/index.html:3400](thyrsus/index.html:3400)

1. **결함:** 대상 필터가 `alive`, 캐릭터 풀이 `townsfolk`뿐이다.
2. **재현:** 죽은 플레이어를 광기 대상으로 고를 수 없고 변종·사랑꾼·이발사·얼뜨기 광기를 줄 수 없다.
3. **기대:** 아무 플레이어와 아무 선한 캐릭터, 즉 주민 또는 외지인을 선택할 수 있다. 죽은 대상도 광기 위반으로 처형될 수 있다. [Cerenovus](https://wiki.bloodontheclocktower.com/Cerenovus)
4. **제안 패치:** 대상은 `any`, 캐릭터 풀은 `good-characters`로 변경한다.

### 10. 이발사 안내가 악마 자신의 스왑을 금지한다

[thyrsus/index.html:749](thyrsus/index.html:749), [thyrsus/index.html:3487](thyrsus/index.html:3487)

1. **결함:** “악마 자신은 스왑 불가”라고 명시한다.
2. **재현:** 보르톡스가 자신과 마녀의 캐릭터를 교환하려 할 때 도구가 불법이라고 안내한다.
3. **기대:** 선택하는 악마는 자신을 고를 수 있다. 금지되는 것은 **다른 악마 플레이어**다. [Barber](https://wiki.bloodontheclocktower.com/Barber)
4. **제안 패치:** 문구를 “악마 자신은 가능, 다른 악마는 불가”로 수정하고, 둘 이상의 악마가 있을 때만 다른 악마를 선택 목록에서 제외한다.

### 11. 백치천재의 보르톡스 지침이 정반대다

[thyrsus/index.html:715](thyrsus/index.html:715)

1. **결함:** 보르톡스 게임에서도 “참/거짓 구조 유지”라고 안내한다.
2. **재현:** 보르톡스가 살아 있는 날 백치천재에게 참 1개·거짓 1개를 제공한다.
3. **기대:** 보르톡스 아래 주민 정보는 전부 거짓이므로 백치천재의 두 문장 모두 거짓이어야 한다. [Vortox](https://wiki.bloodontheclocktower.com/Vortox), [Savant](https://wiki.bloodontheclocktower.com/Savant)
4. **제안 패치:** 보르톡스 분기를 별도로 두어 “두 정보 모두 거짓”을 강제한다. 중독·취함만 두 참/두 거짓/통상 구조 모두 허용한다.

### 12. 임시 취함을 전부 영구 상태로만 표현한다

[thyrsus/index.html:560](thyrsus/index.html:560), [thyrsus/index.html:3191](thyrsus/index.html:3191), [thyrsus/index.html:3933](thyrsus/index.html:3933)

1. **결함:** `drunkS`는 항상 `expiresAt:null`인 영구 취함이다. 선원·여관 주인·건달·음유시인·궁정대신의 임시 취함에 동일 버튼을 사용하면 자동 해제되지 않는다.
2. **재현:** 여관 주인 WIZ 안내에 따라 대상에게 취함 버튼을 누르고 다음 황혼으로 진행해도 상태가 남는다.
3. **기대:** 선원·여관 주인·건달·음유시인은 다음 황혼, 궁정대신은 3일 밤+3일 낮 뒤 만료된다. 주정뱅이·사랑꾼·뱀 조련사 독은 영구다. [Innkeeper](https://wiki.bloodontheclocktower.com/Innkeeper), [`roles.json`](https://release.botc.app/resources/data/roles.json)
4. **제안 패치:** `drunkS`에 `source`별 만료 정책을 지원한다. 궁정대신은 선택한 밤 `n+3`, 다음 황혼까지 역할은 `night n+1`, 영구 취함은 `null`로 저장한다.

---

## Medium

### 13. 오작동 정보가 “반드시 거짓”이라고 전역 안내된다

[thyrsus/index.html:488](thyrsus/index.html:488), [thyrsus/index.html:1570](thyrsus/index.html:1570), [thyrsus/index.html:2858](thyrsus/index.html:2858), [thyrsus/index.html:3350](thyrsus/index.html:3350), [thyrsus/index.html:3503](thyrsus/index.html:3503)

1. **결함:** 주정뱅이와 중독·취함 정보 역할에게 반드시 거짓을 주라고 한다. 꽃팔이 소녀, 예언자, 재봉사 제안도 중독과 보르톡스를 같은 규칙으로 묶는다.
2. **재현:** 중독된 꽃팔이 소녀의 실제 답이 “예”인 상황에서 “예”를 줄 수 없다고 안내한다.
3. **기대:** 중독·취함은 정보가 임의이므로 참도 거짓도 가능하다. 반드시 거짓인 것은 살아있는 보르톡스가 영향을 주는 주민 정보뿐이다. [States](https://wiki.bloodontheclocktower.com/States), [Poisoner](https://wiki.bloodontheclocktower.com/Poisoner), [Vortox](https://wiki.bloodontheclocktower.com/Vortox)
4. **제안 패치:** 배너를 “참 또는 거짓 가능”으로 바꾸고, 보르톡스 전용 `mustBeFalse` 표시를 분리한다. 세탁부·사서·수사관의 풀도 오작동·등록 시 실제 인플레이 풀로 제한하지 않는다.

### 14. 다수 `pick-player`가 공식상 가능한 사망자를 숨긴다

[thyrsus/index.html:3007](thyrsus/index.html:3007), [thyrsus/index.html:3061](thyrsus/index.html:3061), [thyrsus/index.html:3210](thyrsus/index.html:3210), [thyrsus/index.html:3245](thyrsus/index.html:3245), [thyrsus/index.html:3252](thyrsus/index.html:3252), [thyrsus/index.html:3388](thyrsus/index.html:3388), [thyrsus/index.html:3457](thyrsus/index.html:3457)

1. **결함:** 독살범, 집사, 수도사, 여관 주인, 도박사, 구마사제, 좀버얼, 푸카, 샤발로스, 포, 암살자, 대부, 마녀, 마귀할멈, 사랑꾼 및 대부분 악마 WIZ가 `alive`/`alive-not-self`를 사용한다.
2. **재현:** 도박사가 죽은 플레이어를 추측하거나 구마사제가 죽은 척한 좀버얼을 선택하려 해도 목록에 없다. 집사는 죽은 주인을 고를 수 없다.
3. **기대:** 능력에 “alive”가 명시되지 않은 `choose a player`는 사망자도 가능하다. 선원·객실 청소부·뱀 조련사·악마의 변호사·달의 자손만 명시된 생존 제한을 유지해야 한다. [Abilities](https://wiki.bloodontheclocktower.com/Abilities), [Gambler](https://wiki.bloodontheclocktower.com/Gambler), [Exorcist](https://wiki.bloodontheclocktower.com/Exorcist), [Butler](https://wiki.bloodontheclocktower.com/Butler)
4. **제안 패치:** 해당 장면을 `any`로 바꾸고 자기 제외가 필요한 집사·수도사는 `any-not-self`를 추가한다.

### 15. 샤발로스·포가 같은 플레이어를 중복 선택할 수 있다

[thyrsus/index.html:3270](thyrsus/index.html:3270), [thyrsus/index.html:3278](thyrsus/index.html:3278)

1. **결함:** 샤발로스는 두 개의 독립 `storeAs`를 써 같은 대상을 두 번 선택할 수 있다. 포는 3명 선택 장면 없이 “이전으로 돌아가 세 번 반복”하게 한다.
2. **재현:** 샤발로스 첫 공격이 보호로 막힌 뒤 같은 플레이어를 두 번째 희생자로 다시 선택할 수 있다. 충전 포도 같은 대상 반복을 막지 않는다.
3. **기대:** “2 players”, “3 players”는 서로 다른 플레이어를 한 번에 선택한다. [`roles.json`](https://release.botc.app/resources/data/roles.json)
4. **제안 패치:** 샤발로스는 `n:2` 단일 장면, 충전 포는 `n:3` 단일 장면으로 만들고 각 대상에 순차 판정을 실행한다.

### 16. 수학자 능력 범위가 과대 집계된다

[thyrsus/index.html:700](thyrsus/index.html:700), [thyrsus/index.html:3448](thyrsus/index.html:3448)

1. **결함:** “오늘 밤+낮 오작동한 플레이어”라고만 해 `since dawn`, `다른 캐릭터 능력 때문에` 조건을 누락한다. 수학자 자신의 오작동 및 중독됐지만 우연히 정상 결과를 받은 역할도 셀 수 있는 문구다.
2. **재현:** 중독된 초공감자가 우연히 정확한 숫자를 받은 경우 현재 안내대로면 카운트할 수 있다.
3. **기대:** 새벽 이후 다른 캐릭터 능력 때문에 비정상 작동한 능력만 센다. 수학자 자신과 정상 결과는 제외한다. [Mathematician](https://wiki.bloodontheclocktower.com/Mathematician)
4. **제안 패치:** 능력·가이드 문구를 공식 조건으로 교체하고 `abnormalSinceDawn` 이벤트를 역할별 1회 기록한다.

### 17. 도박사 경고에 존재하지 않는 등록 재량과 불가능한 중독 사망이 적혀 있다

[thyrsus/index.html:597](thyrsus/index.html:597)

1. **결함:** 미치광이·건달의 “등록 재량”이 정답 판정에 영향을 준다고 하며, 중독된 도박사가 정답이어도 죽을 수 있다고 한다.
2. **재현:** 미치광이를 악마로 추측하거나 건달을 다른 역할로 추측해 정답 처리할 수 있다고 오해할 수 있다.
3. **기대:** 도박사는 실제 캐릭터를 추측한다. 미치광이는 미치광이, 건달은 건달이다. 중독된 도박사는 능력이 없으므로 자신의 추측 때문에 죽지 않는다. [Gambler](https://wiki.bloodontheclocktower.com/Gambler), [States](https://wiki.bloodontheclocktower.com/States)
4. **제안 패치:** 등록 관련 경고를 제거하고 “중독이면 정오답과 무관하게 도박사 능력으로 죽지 않지만 사용 절차는 평소처럼 진행”으로 바꾼다.

### 18. 캐릭터 변경 시 다른 능력이 준 상태까지 일괄 삭제할 수 있다

[thyrsus/index.html:3628](thyrsus/index.html:3628), [thyrsus/index.html:3632](thyrsus/index.html:3632)

1. **결함:** “상태 토큰 정리 후 적용”이 대상의 모든 상태를 삭제한다.
2. **재현:** 중독된 플레이어를 마귀할멈이 다른 캐릭터로 바꿀 때 정리 버튼을 누르면 중독이 사라진다.
3. **기대:** 플레이어의 중독·취함 같은 상태는 캐릭터와 독립적이므로 캐릭터가 바뀌어도 유지된다. 다만 옛 캐릭터 능력이 만든 지속 효과는 별도로 끝날 수 있다. [States](https://wiki.bloodontheclocktower.com/States), [Abilities](https://wiki.bloodontheclocktower.com/Abilities)
4. **제안 패치:** 일괄 삭제 버튼을 제거하고, `sourceAbilityId`가 옛 캐릭터인 지속 효과만 선택적으로 해제한다.

### 19. 밤 순서 미리보기가 선택 에디션과 무관하게 TB를 표시한다

[thyrsus/index.html:1526](thyrsus/index.html:1526)

1. **결함:** `previewNightOrders()`가 항상 `FIRST_NIGHT_ORDER`/`OTHER_NIGHT_ORDER`, 즉 TB 상수를 사용한다.
2. **재현:** BMR 또는 SV를 선택한 뒤 낮/준비 화면에서 밤 순서 미리보기를 열면 독살범·세탁부 등 TB 순서가 나온다.
3. **기대:** 선택한 에디션의 공식 순서를 보여줘야 한다. [`nightsheet.json`](https://release.botc.app/resources/data/nightsheet.json)
4. **제안 패치:** `editionOf().first`와 `.other`를 사용한다.

### 20. 철학자·재봉사·사랑꾼 WIZ의 선택 검증이 불완전하다

[thyrsus/index.html:3360](thyrsus/index.html:3360), [thyrsus/index.html:3435](thyrsus/index.html:3435), [thyrsus/index.html:3492](thyrsus/index.html:3492)

1. **결함:** 철학자는 악한 캐릭터도 고를 수 있다. 재봉사는 자신을 두 대상 중 하나로 선택할 수 있다. 사랑꾼은 죽은 플레이어를 취하게 할 수 없게 제한된다.
2. **재현:** 철학자 WIZ에서 보르톡스를 선택하거나 재봉사 본인을 선택할 수 있다.
3. **기대:** 철학자는 선한 캐릭터만, 재봉사는 자신 외 두 플레이어, 사랑꾼은 아무 플레이어를 선택한다. [`roles.json`](https://release.botc.app/resources/data/roles.json), [Sweetheart](https://wiki.bloodontheclocktower.com/Sweetheart)
4. **제안 패치:** `good-characters`, `any-not-self`, `any` 풀을 각각 사용한다.

---

## Low

### 21. 음유시인 능력에서 여행자 예외가 빠졌다

[thyrsus/index.html:614](thyrsus/index.html:614)

1. **결함:** 하수인이 처형돼 죽으면 “다른 모든 플레이어”가 취한다고 적었다.
2. **재현:** 여행자가 있는 게임에서 여행자까지 취한 것으로 처리할 수 있다.
3. **기대:** 음유시인 자신과 여행자를 제외한 모든 플레이어가 다음 황혼까지 취한다. [Minstrel](https://wiki.bloodontheclocktower.com/Minstrel)
4. **제안 패치:** 능력·경고에 “여행자 제외”를 명시한다.

### 22. 중독된 암살자의 1회 능력 소진을 재량이라고 안내한다

[thyrsus/index.html:660](thyrsus/index.html:660)

1. **결함:** “소진은 재량”과 “공식: 소진됨”이 한 문장에 공존한다.
2. **재현:** 중독 암살자가 발동을 시도한 뒤 사회자가 미소진으로 남길 수 있다.
3. **기대:** 중독·취함 상태에서 1회성 능력을 시도하면 효과는 없지만 능력은 반드시 소진된다. [States](https://wiki.bloodontheclocktower.com/States)
4. **제안 패치:** “살해는 불발하지만 능력은 반드시 소진”으로 단정하고 WIZ 완료 시 `spent`를 기록한다.

### 23. 시트의 이후 밤 행이 첫날 가이드를 표시한다

[thyrsus/index.html:1262](thyrsus/index.html:1262)

1. **결함:** `nightRow()`가 첫날/이후 밤 구분을 받지 않고, `first:true`인 역할은 이후 밤 시트에서도 `guideFirst`를 선택한다.
2. **재현:** 독살범·집사·초공감자 등 양쪽 밤 역할의 이후 밤 탭을 열면 첫날 진행 문구 첫 줄이 표시된다.
3. **기대:** 이후 밤 탭에서는 `guideOther`가 우선되어야 한다.
4. **제안 패치:** `nightRow(ed,id,{firstNight})`처럼 명시적 인자를 전달해 가이드를 선택한다.

---

## 상태 수명주기 전수 결과

| 상태 | 현재 `expiresAt` | 판정 |
|---|---|---|
| 독살범 중독 | 다음 `night n+1` 시작 | 정확 |
| 푸카 중독 | `null`, 다음 지목 때 수동 해제 | 사망 전 제거 문제로 Critical 1 |
| 수도사/여관 주인 보호 | 다음 `day n` 시작 | 밤 부여 기준 기간은 정확. 대상 오작동 처리만 Critical 3 |
| 집사 주인 | 다음 `night n+1` | 정확 |
| 마녀 저주 | 다음 `night n+1` | 정확 |
| 세레노버스 광기 | 다음 `night n+1` | 정확 |
| 소진 | 영구 | 정확 |
| 좀버얼 죽은 척 | 두 번째 사망 전까지 | 정확 |
| 주정뱅이·사랑꾼 등 영구 취함 | 영구 | 정확 |
| 선원·여관 주인·건달·음유시인·궁정대신 임시 취함 | 영구로만 입력 가능 | High 12 |

정상 UI 경로에서는 독 중복 방지와 단일 주인·저주·광기 갱신이 작동해 추가 이중 부여는 재현되지 않았다. `wiz.vars`는 매 시작 시 새 객체로 만들고 씬 임시값도 제거하므로 이전 WIZ 선택값 잔존이나 전역 선택값 오염도 재현되지 않았다.

## 72종 완전성 확인

`CHARACTERS`는 정확히 TB 22 + BMR 25 + SV 25 = 72종이다.

- 아이콘 ID, 한글명, 영문명 매핑: 72종 모두 불일치 없음.
- 셋업 보정값: 남작 `+2 Outsider`, 대부 `±1`, 팡 구 `+1`, 비고르모르티스 `-1` 모두 정확.
- 소환사·정치인은 72종 `CHARACTERS` 구성원이 아니므로 이번 72종 배열의 `setupNote` 검증 대상에는 없었다.
- 캐릭터 데이터 자체에서 결함이 확인된 항목은 주정뱅이, 장의사, 도박사, 음유시인, 암살자, 달의 자손, 수학자, 꿈꾸는 자, 백치천재, 팡 구, 이발사다.
- 나머지 61종의 `ability`·`guideFirst`·`guideOther`·`warn`·`remind`에서는 위 WIZ/공용 엔진 결함과 별개인 의미상 오류를 추가로 찾지 못했다.

---

## 3차 Critical 3건 수정 완료 (2026-09-01, 맥미니)

| # | 결함 | 수정 내용 |
|---|------|-----------|
| 1 | 푸카 희생자의 독을 사망 전에 제거 + 보호 미적용 | 순서를 **새 대상 중독 → 보호 판정 → (독 유지한 채) 사망 → 해독** 으로 교정. 보호로 살아남은 경우에도 해독은 수행. 이제 중독된 어릿광대는 1회 생존이 발동하지 않고, 까마귀지기·현자는 거짓 정보를 받는다 |
| 2 | 처형과 사망 혼동 | `resolveExecution()` 신설 — 일반 처형·성결자 발동이 공유. 보호로 살아남아도 `executedToday` 가 기록되어 보르톡스·시장 판정이 성립하고, 장의사는 신설 `S.executedDiedToday`(→ 밤 전환 시 `executedPrevDay`)로 **처형으로 실제 죽은** 캐릭터만 본다. 찻집 여인은 처형 자체가 아니라 사망만 막는다 |
| 3 | `deathBlockReason()` 이 대상 오작동 시 외부 보호까지 무효화 | 외부 보호와 자기 면역을 분리. 보호 토큰·찻집 여인은 **대상이 취하거나 중독돼도 정상 작동**(다른 플레이어의 능력이므로). 수도사 출처는 악마 살해에만, 여관 주인 등은 모든 밤 사망에 적용. 군인·선원 자기 면역만 오작동의 영향을 받고, 군인은 `sourceType==='demon'` 일 때만 면역 — `doStepKill` 이 살해 출처(악마/비악마)를 구분해 전달 |

부수: `blank()` 에 `executedDiedToday` 추가. `deathBlockReason(t,{sourceType,bypass})` 로 시그니처 변경(암살자=`bypass`).

### 검증
- `node --check` 스크립트 블록 19/19 통과
- 브라우저 시나리오 **33건 전부 통과** — 3차 타깃 19건 + 1·2차 회귀 14건
  (취한/중독 대상의 외부 보호 유지, 수도사 vs 여관 주인 적용 범위, 군인의 악마 한정 면역, 중독된 어릿광대의 1회 생존 불발, 보호된 푸카 희생자의 생존·해독, 선원 처형 시 처형 소모·장의사 미표시, 정상 처형의 장의사 이월, 주모자 연장전, 탕녀 계승, 좀버얼, 암살자 관통, XSS, 전 탭 렌더, 지명→거수→찬반→처형, 별 넘기기)

**High 이하 20건은 미수정** — 목록은 위 3차 원문 참조. 최우선은 사망 트리거 역할의 밤 실행 큐 누락·반복, 구마사제-악마 단계 미연결, 팡 구 점프 발동 조건, `renderSheet()` 의 첫날 정보 단계 강제 선두 배치(BMR/SV 밤 순서 배열만 고쳐서는 시트가 계속 틀림).

---

## 4차 수정 (2026-09-02, 맥미니) — High·Medium 백로그 구조 수정 15건

| 영역 | 수정 |
|------|------|
| 밤 순서 | BMR 첫날 `하수인→미치광이→악마`, SV 첫날 `철학자→하수인→악마` (공식 nightsheet). `renderSheet()` 의 정보 단계 강제 선두 배치 제거 — 배열 순서 그대로 렌더 |
| 시트 에디션 | `sheetEd` 초기값을 `S.edition` 으로, 밤 전환 시 자동 동기화 (3차 #19) |
| 진영 | `p.alignment` 독립 필드 + `isEvil()` 우선 참조. `doSwapChars()`(이발사: 캐릭터만 교환·진영 보존), `doSnakeSwap()`(뱀 조련사: 캐릭터+진영 교환·새 조련사 영구 중독) 신설, WIZ 에 판정 연결. 이발사 "악마 자신 교환 가능·다른 악마만 불가"로 문구 교정 (3차 #10, 2차 백로그 alignment) |
| 사망 트리거 | `p.diedAt={kind,n,cause}` 기록. `DEATH_TRIGGER_STEPS`(까마귀지기·현자=그 밤, 이발사·사랑꾼·달의 자손=오늘) 로 `stepSkipReason()` 재작성 — 죽은 까마귀지기가 매일 재진입하던 것, 죽은 현자·이발사가 큐에서 빠지던 것 모두 해소 (3차 #4) |
| 구마사제 | `S.demonBlockedNight/Pid` 저장, 밤 큐가 해당 악마 단계를 실제로 스킵 (3차 #5) |
| 팡 구 | `doFangGuAttack()` 신설 — **실제로 죽였을 때만** 점프(보호 시 점프 없음), `S.fangGuJumped` 게임당 1회, 새 팡 구 `alignment='evil'` (3차 #7) |
| 어릿광대 | 확인창 제거 — 강제 능력이므로 자동 발동 (3차 #5-계열) |
| 좀버얼 | 죽은 척 시에도 `checkEndConditions()` 실행. 겉보기 생존 2인 + 죽은 척 좀버얼 = 자동 악 승리 대신 `continue(zombuul)` (2차 #8) |
| 보호 만료 | 낮 부여 보호 `{kind:'day', n+1}` — 쓸 밤 시작에 만료되던 문제 (2차 #7, 두 지점 모두) |
| 달의 자손 | 선택 주체 `player` 로, 오작동 판정 시점=밤 사망 해결 시점으로 안내 교정 (3차 #6) |
| 꿈꾸는 자 | 대상 `not-self-not-traveler`(사망자 가능), 토큰 풀 `good-characters`/`evil-characters` 분리 (3차 #8) |
| 세레노버스 | 대상 `any`(사망자 포함), 풀 `good-characters`(주민+외지인) (3차 #9) |
| 상태 보존 | `setChar()` 가 주정뱅이 출처 취함만 제거 — 사랑꾼·건달 등 외부 취함 보존 (3차 #18) |
| 중복 지목 | 샤발로스·포 두 희생자 상이 강제(사망자 재지목 차단) (3차 #15) |
| 마이그레이션 | `migrateState()` — 플레이어·지명 단위 기본값 보충(`deadVoters` 등), localStorage·클라우드 복원 공용 (2차 #12) |
| 클라우드 | `#winask`·`#gameover`·`#wizard`·`#pmodal` 오버레이 전부 숨김+비움 (2차 #13) |

검증: node --check 19/19 · 브라우저 시나리오 44건 통과(신규 37 + 회귀 7 계열 통합 18) — 이발사 진영 보존, 팡 구 3분기, 구마 봉인 큐 스킵, 사망 트리거 6분기, 좀버얼 2인 예외, 낮 보호 만료 3단계, 마이그레이션 방어, 시트 순서(BMR·SV), 에디션 동기화, setChar 보존, 전 에디션×전 탭×시트 3뷰 렌더.

---

## 공식 캐릭터 아이콘 도입 (2026-09-04)

### 정정
PR #20 본문에 "teeroz 아이콘은 제3자 저작물이라 복제하지 않았다"고 적었는데 **틀렸다**.
teeroz 가 쓰는 것은 The Pandemonium Institute 의 공식 캐릭터 아트이고, 공식 스크립트 툴
(`script.bloodontheclocktower.com`)이 그대로 배포한다. `clocktower.online`, `bra1n/townsquare`
등 커뮤니티 도구도 같은 자산을 쓴다. 그 잘못된 전제 위에서 손그림 SVG 세트를 만들었고,
이번에 공식 아트로 전면 교체했다. 손그림 SVG 는 폴백으로 남는다.

### 출처와 매핑
- 캐릭터 목록: `roles181.json` (181종) — **이미지 필드가 없다**
- 경로는 공식 툴 번들 `sbotc.js` 를 파싱해 얻었다
  - 팀 변형이 있는 156종: `/assets/{id}_{g|e}-{hash}.webp`
  - 우화·여행자 등 25종: `/assets/{id}-{hash}.webp` (예: `djinn-SYNTW9dK.webp`)
- 팀 기준으로 변형 선택 — 하수인·악마는 `_e`(적), 나머지는 `_g`(청)
- 매핑 결과 **181/181, 미매핑 0**

### 동봉 방식
| 선택지 | 판단 |
|---|---|
| data URI 인라인 | 4MB → 단일 HTML 이 감당 못 함. 기각 |
| **별도 파일 + 상대경로** | 채택 — `thyrsus/icons/{id}.webp`, 평균 22KB |

`loading="lazy"` 로 백과사전 181개 동시 렌더의 첫 페인트를 지킨다.

### 폴백
`officialIconHTML()` 이 폴백 마크업(기존 인라인 SVG → 이모지 → sysIcon)을 base64 로
`data-fb` 에 실어 두고, `onerror` 에서 `outerHTML` 을 통째로 갈아끼운다.
→ `index.html` 만 떼어 오프라인으로 열어도 아이콘 없이 그대로 동작한다.

### 크기 규칙
SVG 용으로 이미 브레이크포인트별 튜닝이 끝나 있던 `:has(svg)` 사다리(18곳)를
`:has(svg,.cicon-img)` 로 확장해 그대로 재사용했다. 공식 아트는 손그림보다 시각 밀도가
높아 `1.35em` 을 곱해 토큰 지름의 **54~66%** 를 차지한다 (SVG 는 40~48% 였다).

측정값: 원탁 64% · 그리모어 65% · 위저드 대형토큰 66% · 캐릭터확인 61% · 백과사전 64%

### 검증
- `node --check` 스크립트 블록 32/32
- 시나리오 더미 220명 — 실패 런 0
- 퍼저 400판 — 위반 0
- 돌연변이 37종 — 검출 35 · 미검출 0 · masked 2 · 앵커부실 0
- 브라우저 실측 — `img.cicon-img` 188개 로드, 깨진 이미지 0, 잔존 SVG 0,
  모바일(375px) 가로 오버플로 없음

---

## 종료 마지막 단계 · 설정 보존 초기화 · 임의종료 통계 제외 · 전설 아이콘 (2026-09-06)

### 요구
> 종료버튼 마지막단계로 정말 종료하겠습니까 → 확인/취소. 확인을 누르면 하던 게임 초기화 이후에
> (사회자 임의종료만 통계에 반영하지 않기) 게임 설정에서 1참가자 단계로 돌아가는데 전에 플레이했던
> 설정은 남아있게. 추가로 전설들도 공식 아이콘.

### 설계
| 축 | 결정 | 이유 |
|---|---|---|
| 종료 종류 | `S.endKind` = `win`·`concede`·`fiddler`·`manual` (blank+migrateState) | 마감이 "전적을 남길지"를 이 값 하나로 가른다. 경로마다 `showGameOver` 직전에 찍고, `confirmWin(false)`(계속 진행)는 되돌린다 |
| 마지막 단계 | 사후투표 결과 화면 [🏁 게임 종료] → 확인 뷰 "정말 종료하겠습니까?" [확인/취소] | 취소는 아무것도 지우지 않고 결과 화면으로 복귀. [닫기]는 그리모어를 더 볼 수 있게 남겨 두고, 종료 메뉴의 [종료 확정]으로 언제든 확인 뷰로 재진입 |
| 마감 엔진 | `finalizeEndedGame()` = 설정 스냅샷 → `resetGameState(manual?'void':'keep')` → 복원 → `setupStep=1` → `switchTab('setup')` | 초기화의 단일 경로(`resetGameState`)를 그대로 타서 정책이 갈라지지 않는다. 임의종료만 `void`(gid 로 이 판 레코드 제거) |
| 보존 설정 | edition · myScriptActive · fabled · 참가자 명단(이름·좌석 순서·등록부 링크) | 캐릭터 배정·상태·생사·기록·원장은 새 판이므로 비운다. 좌석 id 는 재발급 — 지워진 원장이 가리키던 id 를 남기지 않는다 |
| 종료 메뉴 | `S.gameOver` 면 [동료 평가 이어서](진행 중일 때)·[종료 확정]만 | 끝난 판에 종료 옵션을 다시 보여 주면 "이미 종료된 게임입니다"만 반복된다 |
| 부수 수정 | `RESET_KEEP_KEYS` 에 `myScripts` 추가 | 전체 초기화·판 무효가 **내 스크립트(빌더)** 를 통째로 지우고 있었다. 사용자 자산이므로 customs 와 같은 급으로 보존 |
| 전설 아이콘 | 설정 탭 전설 패널 각 행에 `.ctoken.fabled` + `glyph()` | 24종 전부 `icons/` 에 이미 있었고(공식 아이콘 라운드에서 우화·여행자 패턴으로 확보), 빠진 자리는 이 패널뿐이었다. 밤 순서표·백과사전은 이미 `glyph()` 경유 |

### 회귀 테스트 `thyrsus_sim/endflow_check.js` (10케이스)
A 정상 승리→투표→취소/확인→전적 보존 · B 임의종료→전적 제거(남의 판 유지) · C 기권(계속 진행 복원 포함)→전적 보존 ·
D 종료 메뉴 상태별 구성 · E 미완 판 마감 거부 · F 전체 초기화가 myScripts 보존 · G 삭제된 등록부/스크립트 링크 정리 ·
H endKind 저장본 왕복 · I 전설 glyph 공식 아이콘 · J 결과 닫기→종료 메뉴 재진입 마감 ·
K 토스트 문자열 게이트(레거시 판정)로 뜬 종료도 마감 가능 · L 손상 gameId 재발급

### 자체 점검에서 추가로 잡은 것
- `migrateState` 가 `gameId` 를 재발급한다는 `blank()` 주석과 달리 **실제 코드가 없었다** → 손상 저장본은
  `buildMatchRecord` 가 `gid:null` 을 적어 판 무효·임의종료 제외가 그 판을 못 찾는다. 재발급 추가.
- 토스트 문자열 게이트(레거시 승리 판정 4곳: 2247·2259·2261·4363행)와 `endGameManual` 은 `S.gameOver` 를
  세우지 않고 `showGameOver` 를 불렀다 → 종료 화면·동료 평가는 뜨는데 마감이 "아직 끝나지 않은 게임"으로 거부.
  합류점 `showGameOver` 에서 `gameOver=true`·`endKind||='win'` 을 확정.

### Codex 교차검증(로컬 codex-cli 0.152, 읽기 전용) — 치명 1 · 중대 3 · 경미 1 → 전부 조치
| 등급 | 지적 | 조치 |
|---|---|---|
| Critical | 토스트 문자열 게이트가 `S.gameOver`·`endKind` 없이 종료 화면만 연다 → 마감 거부 | 자체 점검과 동일 지적. `showGameOver` 합류점에서 확정 (endflow2) |
| Major | 외부 기권 훅이 종료하지 않고 돌아오면 `concede` 가 잔존 → 다음 정상 승리가 기권으로 오표기 | 종료 종류를 승리값 `res.endKind` 에 싣고 `confirmWin(true)` 가 확정. 전역 선기록 제거. 폴백(엔진 없음)만 직접 기록 (endflow3) |
| Major | `migrateState` 가 `gameId` 를 재발급하지 않아 `gid:null` → void 가 못 찾음 | 자체 점검과 동일. 재발급 추가 (endflow2) |
| Major | 사후투표 `finish()` 가 레코드 점수·MVP·최고/찐빠를 바꾸는데 프로필 캐시 서명(판 수·ts)이 같아 재빌드되지 않음 — **diff 이전부터 있던 버그** | `finish()` 끝에서 `profileRebuild()` (endflow3). 테스트 N 이 캐시 마지막 매치의 mvp·score 를 레코드와 대조 |
| Minor | `applyGameSettings` 의 전설 복원이 중복·24개 상한을 정리하지 않아 `migrateState` 와 규칙이 다름 | `[...new Set(valid)].slice(0,24)` (endflow3) |

Codex 가 제안한 추가 테스트 4종(toast-only · hook-noop · null-gid · profile-after-peer)을 K·M·L·N 으로 전부 넣었다 → **14케이스 통과**.

### 돌연변이 스위트 변동 분석 (34종: 기준선 34→29 검출)
패치 전/후 파일을 같은 도구로 따로 돌려 항목별 비교 → 상태가 바뀐 것은 `starpass_skip_succession@masked`·
`jinx_active_dedupe_removed@masked` 2종뿐이고, 둘 다 **설계상 등가**(잡히지 않아야 정상)인데 패치 전엔
`checklist_dupkey_customname` 이라는 난수 의존 신호로만 "검출"돼 있었다. 미검출은 양쪽 모두 **0**.
원인: 퍼저는 자체 RNG 를 시드하지만 앱 내부 `Math.random`(uid·gameId·무작위 배정)은 샌드박스에서
Node 것을 그대로 써 실행마다 결과가 흔들렸다 → `harness.js` 에 시드 PRNG(`THY_SIM_SEED`, 기본 7) 도입.

### 워크플로 5관점 리뷰(21건) 반영 — endflow4 · endflow5
| 지적 | 판단 | 조치 |
|---|---|---|
| `showGameOver` 가 `gameOver` 를 강제해 레거시 토스트 오판정(무신론자 판 첫 사망 등)이 되돌릴 수 없는 종료가 된다 (major ×3) | **타당 — 제 endflow2 보강이 만든 회귀** | 강제 제거. 토스트 게이트는 `askWin` 을 경유해 사회자가 [아니오]로 무를 수 있다. 합류점은 `endKind` 기본값만 채운다 |
| 임의종료 레코드가 [종료 확정] 경로에서만 제거 — 전체 초기화·시트 교체로 빠져나가면 통계에 잔존 (major ×2, minor ×1) | **타당** | 임의종료 판은 애초에 `S.history` 에 적립하지 않는다(`record()` 가 화면용 임시 레코드만 돌려줌). 마감의 `void` 는 이중 안전장치로 남김 |
| 밤 위저드 위에서 마감하면 `#wizard`·`wiz`·`body.wizopen` 잔존 (major) | 타당 | `finalizeEndedGame` 이 `closeWiz(false)`·`wizQueue`·`nomPick`·`dragPid`·`wizopen` 을 정리 |
| 종료 메뉴→[종료 확정]→[취소]가 결과 오버레이로 떨어진다 (minor) | 타당 | 진입 출처(`askEndFrom`)를 기억해 메뉴에서 열었으면 취소=닫기 |
| 집계 중(stage 1·2)에도 [종료 확정]이 열리며 안내가 거짓 (minor) | 타당 | 메뉴·확인 뷰 문구를 "진행 중인 동료 평가는 저장되지 않습니다"로 분기 |
| [종료 확정] catch 폴백이 확인 없이 즉시 마감 (minor) | 타당 | 폴백 제거 → 오류 토스트 |
| `resetGameState` 뒤 복원이라 빈 판이 먼저 저장·렌더, 예외 시 복원 누락 (minor) | 타당 | 복원을 `finally` 로 |
| 지니 수락 상태·좌석 전설(구버전) 스냅샷 누락 (minor ×3) | 타당 | `djinn` 보존, 좌석 전설은 활성 목록으로 이관하고 그 좌석은 참가자에서 제외 |
| 낡은 `pendingWin` 확정 시 endKind 덮어쓰기·전적 중복 (minor) | 타당 | `confirmWin` 과 SABER 래퍼 모두 `gameOver` 였으면 무시 |
| 전설 아이콘 토큰이 [배치]와 이름 사이 (minor) | 타당 | 아이콘 → 이름·설명 → [배치](우측) |
| 임의종료도 2단계 투표를 끝까지 돌려야 마감 (minor) | 부분 수용 | 투표 흐름은 사용자가 정한 대로 유지. 종료 메뉴 [종료 확정]으로 집계 중에도 마감 가능(문구로 안내) |
| 마감 없이 새 판 시작 시 `gameOver`·`endKind` 잔존 (minor) | 기존 동작 | `advancePhase` 셋업 분기는 원래 `gameOver` 를 보지 않는다 — 별도 라운드 |

### 게임 시작 시 미구현 캐릭터 경고 (추가 요구)
`unimplementedInPlay()` = 좌석 배정 캐릭터 중 (1) 밤 순서 자동화가 없는 공식 캐릭터(`libCharMeta().encyc`, 실험판 71종 —
스크립트 라이브러리 '진행 가능' 배지와 같은 판정) ∪ (2) 사망 판정 사슬에 `implemented:false` 로 남은 규칙의 캐릭터
(재상·사이코패스·평화주의자·리치). 커스텀은 제외. `advancePhase` 셋업 분기에서 확인 릴레이 경고보다 **앞에**
"미구현된 캐릭터 N명이 있습니다: … 그래도 진행하시겠습니까?" 를 묻고, 진행하면 게임 기록에 남긴다.
회귀 테스트 T(취소=시작 안 함 · 확인=시작+기록 · 미구현 없으면 안 뜸). 총 **19케이스 통과**.

### 배포 직후 사용자 보고 "종료 눌러도 아무것도 안 변한다" (2026-09-08)
라이브 재현: 종료 메뉴는 열리지만, **[사회자 임의 종료]가 네이티브 `prompt()` 2회에 의존**해 대화상자를
지원하지 않거나(홈화면 앱·일부 모바일 브라우저·미리보기 창) "추가 대화상자 차단"이 켜진 환경에서는
`null`이 즉시 돌아와 아무 일도 일어나지 않았다. 콘솔에도 `prompt() is not supported` 가 찍혔다.
- 조치(endflow7): 임의 종료를 `#pmodal` 인앱 카드(선한 팀 승리 / 악한 팀 승리 / 무승부·중단 + 사유 입력)로 교체.
  `endGameManualCommit(act, why)` 가 유일한 커밋 경로. 사용자 데이터는 보간하지 않고 input 값만 읽는다.
- 같이 잡은 것: 낮 페이즈 저장본으로 부팅하면 첫 `renderAll()`(4972행)이 뒤쪽 블록의 `let nomPick` 보다 먼저
  돌아 `ReferenceError`(TDZ) — `renderDay` 안에서 `typeof` 가드로 대체. 시작 시 미구현 확인은 `confirm()`이
  예외를 던지는 환경에서 진행을 막지 않도록 try/catch.
- 교훈: **종료·시작 같은 핵심 흐름에 네이티브 `prompt()`/`confirm()` 을 쓰지 말 것.** 앱 곳곳의 `confirm()`
  (확인 릴레이 미완·미구현 경고 등)은 "추가 대화상자 차단" 환경에서 조용히 `false` 가 되어 진행이 막힌다 — 후속 라운드에서 인앱 확인으로 일괄 교체 권장.

---

## 네이티브 confirm()/prompt() 전면 인앱 전환 (2026-09-09)

### 요구
> confirm() 쓰는 데 전부 인앱 확인으로 바꿔줘 (배포 직후 "종료 눌러도 아무것도 안 변한다" — 원인이 `prompt()` 미지원 환경)

### 설계
| 축 | 결정 |
|---|---|
| 모듈 | `thyDialog(opts, cb)` — kind `confirm`(→bool) · `prompt`(→string\|null, 한 줄/여러 줄·숫자) · `choice`(→id\|null, 버튼 목록) · `alert` · `copy`(클립보드 폴백 텍스트 박스). `#thydlg` z-index 150(모든 오버레이 위), Enter=확인·Esc/바탕 탭=취소, 한 번에 하나만 띄우고 나머지는 큐 |
| 동기 훅 | `window.thyDialogSync(opts)` 가 있으면 UI 없이 그 답으로 즉시 콜백 — 헤드리스 시뮬레이터(`harness.js`)가 기존 `confirm`/`prompt` 스텁을 그대로 태우는 통로. choice 는 prompt 답을 id·라벨(플레이어 이름)로 맞추고 옛 숫자 답은 `syncPromptMap`, 무응답은 `syncFallback` |
| 래핑된 함수 | `advancePhase`(6중 래핑)·`executeNominee`·`startFromSheet`·`doImpKill` 은 **묻고 → 토큰(ack) 들고 자기 자신을 재호출**. 재호출이어야 바깥 래퍼(SABER 이벤트·승리 판정·최근 스크립트 기록)가 결과를 관측한다. `thyAsk` 가 동기 답이면 그 자리에서 이어가고(재호출 없음 → 이벤트 중복 없음), UI 면 재호출 |
| 처형 전 질문 묶음 | 선한 쌍둥이·성자·고블린·공포 조장가 질문을 `executeNominee` 래퍼가 처형 **전에** 순서대로 묻고 `THY_EXEC_ANS` 에 실어, 원본·`resolveExecution` 래퍼·`evalWinEvent` 가 읽는다. 사전 질문 없이 들어온 경로(성결자 즉시 처형)는 동기 훅이 있을 때만 그 자리에서 묻고 UI 면 '아니오' |
| 시장 대체 | `offerMayorSubstitute(t, dr, cause, opts, retry)` — UI 답이 오기 전엔 '처리 중'(true)으로 시장을 살려 두고, 답이 오면 호출부(`doImpKill`/팡 구/`doStepKill`)를 `retry()` 로 재호출. 재호출로 생기는 같은 공격의 중복은 `emitEv` 가 같은 페이즈 안의 같은 주체·대상 attack 을 걸러 막는다 |
| 단순 지점 | 나머지(초기화·무효·등록부·좌석·섞기·배정 비우기·사망 처리·취함 출처·달의 자손·마녀·성결자·처단자·시트 가져오기·클라우드·낮 제한시간·기권·바이올린 연주자·정치인·아가씨·알사히르·교주·얼뜨기·내 스크립트 8곳)는 콜백 연속으로 재구성 |
| 남은 네이티브 호출 | 0 (주석 문구 제외) |

### 검증
- 헤드리스: `endflow_check` 19케이스 0실패 · 더미 220 실패 0 · 퍼저 400 위반 0 · 커스텀 90 기준선 종류만 (동기 훅 경유)
- 브라우저 실제 UI 경로: 시작 미구현 경고(취소=유지·확인=밤 1, phase 이벤트 1건) · 성자 처형 사전 질문→처형→승리 창 · 별 넘기기 선택(새 임프, star 1·attack 1) · 시장 대체(확인→6명 선택→대체 사망, 시장 생존, attack 1) · 낮 제한시간 숫자 입력 · 복사 박스 · Esc/바탕=취소·Enter=확인 · 큐 순서
- 발견·수정: 별 넘기기 재호출 사이에 death 이벤트가 끼어 "마지막 이벤트만 비교"하던 attack 중복 제거가 빗나감 → 같은 페이즈를 거슬러 비교

### Codex 교차검증(로컬 codex-cli, 한도 리셋 후 재실행) — 치명 0 · 중대 1 · 경미 1 → 전부 조치
| 등급 | 지적 | 조치 |
|---|---|---|
| Major | 정치인 진영 전환 확인이 비동기가 되면서 `confirmWin` 래퍼의 종료 이벤트·전적 적립이 전환 **전에** 끝난다 → 스냅샷의 진영이 옛 값 | 답이 오면 `thyPatchBankedAlignment(pol)` 이 이미 적립된 이 판 레코드의 그 좌석 `alignment` 를 고치고 `profileRebuild()`. 테스트 U(동기 훅 제거 → UI 경로 강제 → `thyDialogAnswer('ok')`)가 레코드·프로필 갱신을 대조 |
| Minor | 선택 대화상자에서 Enter 가 `preventDefault` 만 하고 아무것도 확정하지 않음 | Enter 는 포커스된 선택지(`[data-td^="c:"]`)만 확정, 선택지 밖에서는 무시 |
| OK | ack 토큰 범위·`THY_EXEC_ANS` 복구·UI 비동기 반환 시 호출자 가정·attack 중복 제거·마크업 esc·동기 훅 의미 재현 | 근거 확인됨 |

브라우저 실측: 선택지 밖 Enter → 창 유지, 포커스 선택지 Enter → 확정 · 정치인 [예] 뒤 적립 레코드 good→evil, 프로필 마지막 매치 evil/승.
돌연변이 34종 미검출 0(masked 5·pending 1 — 시드 기준선과 동일).

### 워크플로 4관점 리뷰 — 검증 단계가 크레딧 소진으로 전멸, 지적 6건을 직접 확인
워크플로는 리뷰어 4명 중 1명(`async`)만 완료하고 반박자 21명이 전부 실패했다. 그 결과 6건이 모두
"반박됨"으로 집계됐지만 **실제 반박이 아니라 검증자가 못 돌아 자동 탈락한 것**이다. 6건을 코드로 직접 확인 → 전부 실재.
| 지적 | 조치 |
|---|---|
| ① 정치인 전환이 전적 적립 뒤로 밀림 | Codex 라운드에서 이미 수정(`thyPatchBankedAlignment`) — 두 검증자가 독립 재현 |
| ② Enter 가 포커스를 무시하고 항상 '확인' — [취소]에 포커스를 두고 Enter 를 눌러도 판 무효가 실행 | Enter 는 **포커스된 버튼의 동작**으로 답한다. 되돌릴 수 없는 확인(`danger`)은 기본 포커스를 [취소]에. 네이티브 버튼 활성화에 맡기지 않는다 — 자동화·보조기술이 넣는 키는 기본 동작을 일으키지 않아 Enter 가 통째로 먹히는 환경이 있다(미리보기 도구에서 실측) |
| ③ 달의 자손 취소가 "그 이름의 생존 플레이어가 없어…" 경고를 띄움 | `id===null` 이면 조용히 반환(옛 `prompt(null)` 과 동일) |
| ④ 시작 확인 두 개 중 뒤엣것을 취소하면 앞 답(ack)이 남아, 배정을 바꿔도 미구현 경고를 건너뜀 | 취소 시 `thyAckClear('advance:')`, ack 키에 미구현·미확인 구성 서명을 포함 |
| ⑤ attack 중복 제거가 주체가 둘 다 `null` 인 서로 다른 살해(죽은 대부·달의 자손)를 같은 공격으로 오인 | 재호출 표식 `THY_RETRY` 를 도입해 **재호출 구간에서만** 거른다 |
| ⑥ 시장 대체·별 넘기기 재호출로 사망 근거 사슬이 같은 판정으로 두 번 쌓임 | `recordDeathTrace` 가 직전 항목과 완전히 같으면 적지 않는다 |

회귀 테스트 4종 추가(W 달의 자손 취소 · X ack 취소 정리 · Y attack 중복 제거 범위 · Z 근거 사슬) → **24케이스 통과**.
브라우저 키보드 실측 6가지: danger 기본 포커스=취소·Enter=취소 · 일반 Enter=확인 · 취소 포커스 Enter=취소 ·
선택지 Enter=그 선택 · 선택지 밖 Enter=무시 · 입력란 Enter=확인.

---

## 백로그 정리 (2026-09-09) — ① 새 판 상태 · ④ 잔여 규칙 결함

### ① 마감 없이 새 판을 시작하면 '끝난 판' 상태가 남던 문제
종료 화면을 닫고 설정으로 돌아가 곧장 [첫 번째 밤 시작]을 누르면 `S.gameOver`·`endKind` 가 그대로 남아
새 판이 '이미 끝난 판'이 됐다 — 종료 메뉴가 [종료 확정]만 보여주고 승리 판정이 전부 즉시 물러난다.
게다가 `gameId` 가 같아 지난 판과 이번 판의 전적이 같은 gid 를 갖고, **판 무효 한 번에 둘 다 지워졌다.**
- `clearEndedGameState()` — 판 단위 일회성 값(`NEWGAME_RESET_KEYS`)을 되돌리고, 직전 판이 끝나 있었으면 `gameId` 재발급
- 시작 전에 "지난 판이 마감되지 않았습니다"를 한 번 알린다(전적은 건드리지 않음)
- **`gameOver` 를 `blank()`·`migrateState` 의 선언 필드로 승격** — 선언이 없어 판 단위 초기화 목록이 이 필드를 놓치고 있었다

### ④ 사망 판정을 우회하던 경로 3종
`killPlayer` 는 `kill` 단계(어릿광대 1회 생존·좀버얼 죽은 척)만 돌린다. `block` 단계(찻집 여인·선원·폭풍잡이·
보호 토큰·악마의 변호사·군인)는 `resolveDeath(..., ['block'])` 를 호출부가 직접 거쳐야 하는데, 세 경로가 빠져 있었다.

| 경로 | 공식 | sourceType | 걸리는 것 / 걸리지 않는 것 |
|---|---|---|---|
| 처단자 | "Once per game, during the day, publicly choose a player: if they are the Demon, they die." | `slayer` | 찻집 여인·선원·폭풍잡이 ○ / 수도사·군인(악마 전용)·악마의 변호사(처형 전용)·시장 대체(밤 전용) ✕ |
| 마녀의 저주 | "Each night, choose a player: if they nominate tomorrow, they die." | `witch` | 위와 같음 |
| 여행자 추방 | 일탈자 "If you were funny today, you cannot die by exile." 가 **추방이 막을 수 있는 사망임을 공식이 인정하는 근거** | `exile` | 찻집 여인·폭풍잡이 ○ / 악마의 변호사(처형 전용) ✕ |

`resolveDayAbilityDeath(t, sourceType, cause)` 단일 창구로 정리했다. **표는 손대지 않았다** — 각 항목의
`when()` 이 이미 sourceType 을 보고 있어 새 사인에서 알아서 물러난다.

### ④ 미구현 항목 정리 — 표가 정직해졌다
| 항목 | 공식 | 조치 |
|---|---|---|
| 리치 숙주 | "You die if & only if they are dead." | `lleechHost` 토큰 도입. 숙주가 살아 있으면 리치는 **어떤 원인으로도** 죽지 않는다. 숙주가 죽으면 **알리기만** 한다 — 주모자 징크스가 예외를 만들어(숙주가 처형으로 죽으면 리치는 살아남되 능력 상실) 앱이 임의로 죽이면 되돌릴 수 없다 |
| 여관 주인 | "Each night*, choose 2 players: they can't die tonight, but 1 is drunk until dusk." | 보호 토큰 **자동 부여**. 지금까지 "🛡토큰을 놓으세요" 안내문뿐이었고, 잊히면 그날 밤 악마의 살해가 그대로 통과했다. 보호는 강제 능력이다 |
| 재상 | "You cannot die during the day." | **자동 판정**. 원인을 가리지 않는 절대 규칙이라 낮의 처형·처단자·마녀·추방 전부가 대상. 중독·취함이면 무효, 밤 사망은 대상 밖 |
| 사이코패스 | "If executed, you only die if you lose roshambo." | 결과가 앱 밖에서 정해진다 → **처형 전 재량 질문**(`executeNominee` 사전 질문 묶음)으로 받아 판정이 그 답을 읽는다 |
| 평화주의자 | "Executed good players might not die." | "might" 는 재량 → 처형되는 **선한** 플레이어에게만 묻는다 |
| 일탈자 | "If you were funny today, you cannot die by exile." | "재미있었는가"는 순수 사회자 판단 → 추방 확정 직전에 묻는다. 표 항목은 `implemented:false` 로 근거만 남긴다 |

표에 남은 `implemented:false` 는 **일탈자·지니 징크스 둘뿐**이고 둘 다 의도적이다.
`PARTIAL_IMPL_CHARS` 는 비었다 — 게임 시작 경고의 "판정 수동" 부류가 사라졌다.

### 회귀 테스트 `thyrsus_sim/rules_check.js` (15케이스)
처단자 기본·찻집 여인·선원·군인/수도사 비적용 · 여관 주인 보호(오작동 포함) · 마녀 저주 · 어릿광대 회귀 ·
리치 숙주 5사인 · 숙주 사망 알림(주모자 징크스 포함) · 추방 판정 · 일탈자 재량 양방향 · 재상(낮/밤/중독) ·
사이코패스·평화주의자 재량 · 표 정직성 · 처형/밤 살해 무회귀

## 백로그 정리 (2026-09-09) — ② 래핑 감사 · ③ 투표 산술 단일 출처

### ② 래퍼 체인 — 설계 조사의 결론은 "전면 이관하지 마라"
4관점 설계 조사(래퍼 축)가 실측한 결과와 권고:
- 래핑 지점은 **50개/34이름이 아니라 93개/48이름**(정적 81 + 헬퍼가 심는 동적 12~14).
- **지금 실제로 고장 난 것은 래퍼 구조가 아니라 감사 쪽이다.** `THY_WRAP_BASE` 가 두 곳 낡아
  매 로드마다 거짓 알림이 뜬다 — 자체 도구 `wrap_baseline.js` 와 브라우저 콘솔에서 모두 확인.
- 이관의 대표 이득(기계가 읽는 순서 있는 체인 명세)은 **감사표를 고치는 것만으로 8할이 확보**된다.
- 게임을 망칠 만큼 비싼 체인 셋(`advancePhase` 차단+재개 · `executeNominee` ack 재진입 ·
  `confirmWin` 원장 순서)이 하필 레지스트리가 **평탄화하지 못하는** `around` 유형이다.
- 렌더 훅 42곳은 DOM 골든 게이트 없이는 검증 불가 — 그 게이트 자체가 별도 프로젝트다.

→ **Stage 0(감사 수리)만 하고 멈췄다.** 레지스트리 도입과 93곳 이관은 착수하지 않았다.

| 한 일 | 내용 |
|---|---|
| 계수 정정 | `resolveExecution` 1→2 · `startFromSheet` 1→2 (거짓 알림 2건 제거) |
| 누락 등재 | `libDetail` 2 · `renderCustom` 1 · `setupIssues` 1 — 래핑돼 있는데 검사 목록 밖이었다 |
| 동적 래핑 가시화 | `THY_WRAP_DYNAMIC` 선언 + 헬퍼 5개가 설치 시점에 `THY_WRAP_LOG` 에 기록 → 로드 뒤 대조 |

동적 래핑을 **함수 표식(`__thyWrap`)** 으로 잡는 방식도 만들어 봤으나, 그 위에 정적 래퍼가 한 겹
얹히면 표식이 통째로 사라진다(`renderSheet`·`renderCustom` 이 실제로 그 경우였다). 설치 원장으로 바꿨다.

### ③ 투표 산술 단일 출처화 (무행동)
설계 조사(투표 축)가 **critical** 로 지목: 분모·문턱이 다섯 곳 이상에 각각 기재돼 있다.
실측하니 9곳이었고, **분모와 문턱의 기준 인원이 서로 다르다**는 계약이 네 곳에 각각 적혀 있었다.

| 단계 | 분모 | 문턱 |
|---|---|---|
| 1차 거수 | 생존자 | 생존자의 과반 |
| 2차 찬반 | 자격자(생존자 ∪ 1차 거수자, 사망자 포함) | **생존자**의 과반 |
| 추방 | 좌석 전원 | 좌석 전원의 과반 |

2차의 분모≠문턱 기준은 공식 "at least half the living players" 때문이다. 분모를 문턱에 쓰면
사망자가 1차에 손만 들고 2차에 기권해 **토큰도 쓰지 않고 문턱을 올려 처형을 막을 수 있다.**

`voteDenominator(nom, stageKind)` · `voteThreshold(stageKind)` 로 뽑았다. 이제 `majority()` 를
부르는 곳은 `voteThreshold()` 하나뿐이다.

**무행동 증명**: (1) 무작위 상태 400건에서 옛 인라인 식과 신 헬퍼 대조 — 불일치 0.
(2) 퍼저 400판 커버리지가 변경 전과 **완전히 동일**(사망 5.6·로그 29.4·지명 3·처형 2.4·400판 종료).

⚠ **교훈**: 차등 테스트만으로는 부족했다. 헬퍼는 옳았지만 호출부에서 표시용 변수(`aliveN2`)를
같이 지워 `renderNomOpen` 이 던졌고, **차등 테스트는 통과했는데 퍼저가 400판 중 380판을 잡았다.**
추출 리팩터링에서는 '식이 같은가'와 '호출부가 여전히 성립하는가'를 따로 증명해야 한다.

### ⚠ 설계 조사가 오늘 배포분에서 잡은 치명 2건 (같은 날 긴급 수정)
조사 에이전트가 **내가 몇 시간 전에 배포한 코드**에서 찾았고, 둘 다 직접 재현해 확인했다.

| 등급 | 결함 | 왜 테스트가 못 잡았나 | 조치 |
|---|---|---|---|
| Critical | **여관 주인 보호가 2명 중 1명에게만 붙는다.** `wizEffect` 가 배열을 통째로 넘기는 분기에 `doSwapChars`·`doSnakeSwap` 만 열거해 둬서 `doInnkeeperProtect` 는 첫 pid 하나만 받는다. 바로 옆 안내문은 "토큰 2개가 자동으로 놓였습니다"라고 **거짓을 말한다** — 두 번째 손님이 그날 밤 조용히 죽는다 | 함수 자체는 배열을 정상 처리한다. **함수를 직접 부르는 내 테스트는 전부 통과했다** — 결함은 디스패치에만 있었다 | 씬 계약에 `all:true` 표식을 도입해 이름 열거를 없앴다. 밤 스크립트 전체를 훑어 "다중 대상인데 `all` 이 없는 씬"을 잡는 **구조 불변식 테스트**를 넣어 재발을 막는다 |
| Critical | **보호 토큰이 낮 능력 사망까지 막는다.** `when()` 이 `sourceType!=='execution'` 을 '밤 사망'의 대리조건으로 썼다. 사인 어휘가 셋(demon/night/execution)이던 시절엔 동치였지만, **오늘 내가 slayer·witch·exile 을 추가하면서 깨졌다** — 낮에 수동으로 놓은 🛡 토큰이 그날 낮의 처단자 일격을 막는다 | 내 테스트는 수도사 출처 토큰만 확인했다(그건 악마 전용 절이 따로 막아 준다). 여관 주인·수동 출처를 안 봤다 | `DEATH_DAY_ABILITY_SRC=['slayer','witch','exile']` 를 명시적으로 제외. 사인이 없는 옛 호출부(`null`)는 종전대로 막는다 — 이번 수정은 새 사인만 되돌린다 |

부수 수리: 여관 주인 보호가 `emitEv('protect')` 를 안 쏴 레비아탄·폭동 징크스 감사가 영원히 '확인 필요'였다(수도사 경로는 이미 쏘고 있었다).

**돌연변이 스위트 보강** — 조사가 예고한 대로 `protect_token_blocks_execution` 앵커가 수정과 함께 부실해졌다.
재앵커하고 `protect_token_blocks_day_ability` 를 새로 넣었는데 **미검출**로 떴다. 시나리오·퍼저는 그 조합을
무작위로 만들어 내지 못한다. 그래서 `rules_check.js` 를 돌연변이 스위트에 편입했다 — 이제 규칙 판정
19케이스 전체가 검출력을 갖는다(35종 미검출 0).

**교훈**: 판정 함수를 직접 부르는 테스트는 **디스패치 결함을 구조적으로 볼 수 없다.** 밤 능력은
위저드 경로(`wizEffect`)로 태워야 한다. 그리고 판정 표의 술어에 새 사인을 추가할 때는 **기존 술어가
그 사인을 어떻게 보는지 전수로 다시 봐야 한다** — 대리조건으로 쓰인 절이 조용히 뒤집힌다.

## VOTE_MODIFIERS 실제 규칙 편입 (2026-09-10, 무행동)

`runModifiers` 는 첫 성립에서 사슬을 끊는다. 사망은 그것이 맞지만(첫 보호가 걸리면 끝) **투표 무게는
누적돼야 한다** — 관료 ×3 위에 도둑의 부호 반전이 얹혀 −3 이 되는 것이 공식이다. 표가 스스로 정하도록
`spec.terminal` 훅을 넣었다. 훅이 없으면 종전대로 항상 끊으므로 **사망 표 동작은 1비트도 안 바뀐다.**

| 항목 | 단계/효과 | 공식 |
|---|---|---|
| `butler-master` | count / void | "you may only vote if they are voting too" |
| `bureaucrat-x3` | weight / ×3 | "their vote counts as 3 votes tomorrow" |
| `thief-negate` | weight / 부호 반전(함수형 계수) | "their vote counts negatively tomorrow" |

호출부 두 곳(`weightOf`·`closeBallot` 집사 무효)을 표를 읽는 창구(`voteWeightOf`·`voteVoided`)로 돌려
**표가 단일 출처**가 됐다. 표에 넣지 않은 것과 이유도 코드 주석에 적었다(시장=처형 축 · 꽃팔이 소녀=정보 축 ·
성결자/마녀/고블린=지명 축 · 부두술사/거지=자격·비용 축).

**무행동 증명**: 무작위 300건 차등(무효 대상·7좌석 무게 전부) 불일치 0 · 퍼저 400판 커버리지 동일 ·
관료+도둑 겹침 −3 확인 · 사망 표가 여전히 첫 성립에서 끊는지 별도 확인.

**돌연변이 재앵커 3건** — 로직이 표로 옮겨가며 앵커가 부실해졌다(예고된 대로). 표 항목에 재앵커하고
`traveler_thief_negate_not_cumulative`(누적 계약을 겨눔)를 추가했다. `butler_void_ignores_malfunction` 은
오작동 가드가 두 줄에 걸쳐 서로를 가려 등가 돌연변이가 되므로 **복합 돌연변이**로 바꿨다 → 36종 미검출 0.

### 투표 이관 적대 검증 결과 — 무행동 확인 + 잠복 지뢰 1건·선재 결함 1건
검증 레인이 HEAD~1 을 꺼내 같은 상태를 두 빌드에 주입하고 결과 전체를 대조했다.
사망 표 **1,200 상태 × 7사인 × 2단계** 불일치 0 · 집사 2인 **4,000 상태** 불일치 0 ·
closeBallot 종단 **550판**(S.log 전사 포함) 불일치 0 · renderNomOpen **400판 HTML 바이트 동일** ·
순수성(상태 불변·save 0회) 확인. → **판정: 무행동 맞음.**

그 대신 두 가지를 짚었고 둘 다 고쳤다.

| | 내용 | 조치 |
|---|---|---|
| **H1 잠복 지뢰**(이번 커밋이 심음) | `defaultStages:['count','weight']` 인데 `terminal:(m)=>m.effect!=='weight'` 다. 지금은 두 창구가 늘 단일 축을 명시해 도달 불가지만, `resolveDeath` 처럼 **기본 단계를 쓰는 것이 이 파이프라인의 관용 형태**라 누군가 `runVoteModifiers(t, ctx)` 를 부르는 순간 count 성립이 사슬을 끊어 **여행자 가중이 조용히 1로 주저앉는다** | `runVoteModifiers` 가 축이 섞이면 축별로 따로 돌려 합친다. 단일 축 호출은 1비트도 안 바뀐다 |
| **H2 선재 결함**(이번 커밋 이전과 동일) | `renderNomOpen` 이 집사 무효를 **어느 숫자에서도 빼지 않는다**. 250판 스윕에서 무효가 난 38판 전부 미리보기 ≠ 확정(대개 1표 차 — 문턱 근처면 **화면은 통과, 마감은 부결**). 경고 술어도 인라인이라 집사 2인 판에서 둘 다에게 뜨는데 실제 무효는 하나뿐 | 화면도 `voteVoided` 를 쓴다 — 숫자와 경고 모두 확정과 같은 술어 |

**검출 사각 5건도 메웠다**(검증 레인이 index.html 을 실제 변형해 "21케이스 통과"를 확인한 것들):
축 혼합 · 미리보기↔확정 일치 · 집사 2인 범위 · 표가 무게의 단일 출처인가(표 항목을 지우면 답이 바뀌는가) ·
`when()` 순수성(상태·save·nom 불변). → rules_check **26케이스**.

## 남은 규칙 지적 5건 처리 (2026-09-10)
6레인 워크플로가 낸 진단은 전부 실재했지만, **제출된 패치 텍스트는 중간에서 잘려 그대로 적용하면 앱이
죽는다**(검증 레인 2명이 각각 실측해 지적). 진단만 취하고 구현은 직접 했다.

| 지적 | 조치 |
|---|---|
| 성결자 즉시 처형에서 처형 재량이 절대 발동하지 않음 | 질문 묶음을 `thyExecPrompts(p, akey, retry)` 단일 출처로 추출하고, 성결자 경로가 `virginExecute()` 로 같은 묶음을 지나게 했다. **레인이 제안한 '가장 바깥 래퍼 추가'는 쓰지 않았다** — 순서 계약이 얽혀 위험하고, 레인 스스로 그 범위 초과(evalWinEvent 추가)를 위험으로 적었다. 문제가 난 호출부에서 좁게 해결하는 편이 안전하다 |
| 추방이 '처형'으로 오분류 | 사인 문구 `여행자 추방(exile) 가결 — 처형 횟수와 무관` 안의 '처형' 두 글자가 `/처형\|성결자/` 에 걸렸다. `isExecutionCause(cause, sourceType)` 를 단일 출처로 두고 사인이 있으면 그것이 정본, 없으면 종전 문자열 추론(하위호환). `checkEndConditions` 는 사인을 받지 않는 옛 계약이라 **호출 지점을 감싸는 창구**(`checkEndWithSrc`)로 잠깐 세운다 — `killPlayer` 는 조기 반환이 여럿이라 함수 전체를 감싸면 값이 샌다 |
| 일탈자가 표 밖에서 판정돼 근거 사슬에 안 남음 | 재량 답을 `ctx.deviantFunny` 로 넘겨 표 안에서 판정. **절대 면역이 먼저 걸리면 묻지도 않는다** — 어차피 안 죽는데 "오늘 재미있었습니까?"를 묻는 것은 없는 선택지를 주는 것이다(표를 먼저 미리 밟아 확인) |
| 리치·재상의 official 이 "미구현·켜지 않는다"라 거짓 안내 | 실제 상태로 교체. 리치 라벨 "숙주 생존"이 보호 대상을 거꾸로 말해 "숙주가 살아 있으면 죽지 않음"으로 고쳤다(보호받는 쪽은 리치다). 재상은 궁정대신·설교자 징크스 예외를 명시하고 그것은 수동 판정임을 적었다 |

**켜진 항목이 '미구현'이라 말하지 않는지**를 테스트로 못 박았다(`officialTextHonest`) — 사회자 근거 사슬
화면에 그대로 뜨는 문자열이라 거짓이 남으면 안 된다. rules_check **31케이스**.

## INFO_MODIFIERS 실제 규칙 편입 (2026-09-10, 무행동)

**전수 조사 결과: 정보 규칙은 코드가 아니라 산문으로 흩어져 있었다.** 판정 코드는 `isMalfunctioning`
하나뿐이고 나머지는 전부 사회자에게 읽히는 문자열이다 — 위저드 경고바 2곳, 밤 시트의 오작동 알림,
정보 힌트의 "(등록 재량 반영 전)", 캐릭터 `warn[]` 의 첩자·은둔자 안내, 그리고 `WIZ_SUGGEST` 계산기
12개가 각자 note 에 적어 둔 "보르톡스면 반드시 거짓 / 중독이면 임의". 같은 규칙이 열 군데에 다른
문장으로 적혀 있으면 한 곳만 고쳤을 때 나머지가 조용히 어긋난다.

### 사망 표와 다른 점 둘
① **누적한다.** 중독(임의) 위에 보르톡스(반드시 거짓)가 얹혀야 하는데, 첫 성립에서 끊으면 먼저 걸린
   중독 때문에 보르톡스가 영영 평가되지 않는다. `terminal:()=>false` 로 사슬을 연다.
② **순서가 아니라 강도로 이긴다.** VOTE 의 무게는 곱해 쌓이지만 정보의 등급은 '더 센 쪽'이 이겨야
   한다. `apply` 가 `INFO_RANK` 비교로만 등급을 올리므로 항목을 어느 자리에 끼워도 답이 안 바뀐다
   (`precedence` 는 경고 문구의 나열 순서일 뿐이다). 표 뒤에 약한 항목을 끼우는 테스트로 고정했다.

### 등록(register)과 제약(constrain)을 가른 것이 핵심이다
**붉은 청어는 거짓이 아니다.** 점쟁이는 정상 작동 중이고 그 "예"는 참이다 — 단지 그 대상이 악마로
'등록'될 뿐이다. 등급을 올리면 멀쩡한 점쟁이가 중독된 것처럼 보인다. 첩자·은둔자도 같은 축이라
`register` 로 두되 "무엇으로 등록할지"는 재량이므로 `implemented:false` 로 근거만 남긴다.

### `ctx.sourceCharId` ≠ `t.charId`
주정뱅이는 사회자 눈에 '초공감자 단계'(`sourceCharId`=위장 캐릭터)지만 좌석의 실제 캐릭터는 외지인이다.
보르톡스의 "Townsfolk abilities yield false info" 는 **`t.charId`** 를 봐야 공식과 맞는다 — 주정뱅이에게는
안 걸리고 취함으로 '임의'에 머문다. 바꿔 읽으면 판정이 조용히 뒤집힌다.

| 항목 | 효과 | 공식 |
|---|---|---|
| `malfunction` | constrain / arbitrary | 중독·취함·주정뱅이 — "might" 라 **재량**이다. 자동으로 거짓을 만들면 안 된다 |
| `vortox-townsfolk-false` | constrain / false | "Townsfolk abilities yield false info" — 재량이 아니라 **강제** |
| `red-herring` | register | "There is a good player that registers as a Demon to you" — 거짓이 아니다 |
| `spy-registers`·`recluse-registers` | register (implemented:false) | "might register as…" — 무엇으로 등록할지는 사회자 재량 |
| `drunk-mask` | discretion | 위장 캐릭터를 사회자에게 알린다(판정은 malfunction 이 한다) |

**무행동**: 제품 경로 호출부 0개. 조회 창구 `infoVerdict(t, ctx, stages)` 만 열었다 — 화면 넷
(위저드 경고바·밤 시트 알림·정보 힌트·체크리스트)이 이 객체 하나만 읽으면 서로 어긋날 수 없다.
옮겨 타는 것은 화면마다 문구가 달라 별도 라운드에서 한다.
퍼저 400판 커버리지 동일 · 상태 불변·`save()` 0회 · 사망/투표 판정 불변.

**돌연변이 4종 추가**(40종 미검출 0): 누적 계약 · 강도 우선 · 등록/제약 분리 · 보르톡스가 보는 대상.
표만 있고 이를 겨눈 돌연변이가 없으면 조용히 썩는다.

---

## 라운드 12 — 정보 표로 화면 셋을 옮겨 태우다 (2026-09-10)

라운드 11 은 창구(`infoVerdict`)만 열고 제품 경로는 손대지 않았다(무행동). 이번은 **옮겨 타는** 라운드라
무행동이 아니다 — 화면 문구가 실제로 바뀐다. 바뀐 곳과 이유를 그대로 남긴다.

### 옮겨 탄 곳 셋

| 화면 | 전 | 후 |
|---|---|---|
| 위저드 경고바 `wizWarnBar` | 인라인 두 줄(오작동 / 보르톡스) | `iv.reasons` · `iv.registers` · `iv.discretion` 순회 |
| 밤 단계 카드 `renderStep` badHolders | `isMalfunctioning(p)` | `infoVerdictFor(p, st.id).mode!=='true'` |
| 위저드 캐릭터 풀 `wizCharPool` | `isMalfunctioning(wiz.holder)` | 같은 판정의 `mode!=='true'` |

창구는 얇은 어댑터 `infoVerdictFor(t, stepId)` 하나를 더 뒀다. **`sourceCharId` 와 `t.charId` 를 가르는
자리가 여기다** — 주정뱅이 좌석이면 단계는 위장 캐릭터이고 좌석의 실제 캐릭터는 외지인이다.
화면마다 이 계산을 반복하면 라운드 11 에서 경고한 "조용한 뒤집힘"이 바로 돌아온다.

### 실제로 고쳐진 오안내 하나

인라인 판정은 **보르톡스가 중독·취함이어도** "주민 정보는 반드시 거짓"을 띄웠다. 공식상 오작동한
보르톡스의 능력은 발동하지 않으므로 이건 사회자에게 주는 거짓 안내다. 표의 `vortox-townsfolk-false`
는 그 조건(`Vortox 자신이 오작동 중이 아닐 것`)을 처음부터 보고 있었다 — 옮겨 타자 저절로 맞았다.
표를 만든 값이 여기서 처음 현금화됐다.

### 캐릭터 풀을 여는 기준을 바꿨다

전에는 "홀더가 오작동인가"로 인플레이 제한을 풀었다. 보르톡스 판에서는 **정상 작동하는 주민**도
반드시 거짓을 들어야 하는데 풀이 잠겨 있어 사회자가 거짓을 만들 재료가 없었다. 기준을 "정보가
사실대로가 아닌가"로 바꾸니 두 경우가 한 문장으로 덮인다.

**검증**: 규칙 38케이스 0실패(신규 2 — `infoScreensUseTable` · `charPoolOpensOnFalseInfo`) ·
종료 25케이스 0실패 · 더미 220 실패런 0 · 퍼저 400판 위반 0(커버리지 기준선과 동일) ·
커스텀 90판 위반 1(기준선과 동일) · 돌연변이 40종 미검출 0.
퍼저 커버리지가 기준선과 한 자리도 안 다르므로 게임 진행에는 회귀가 없다 — 바뀐 것은 의도한
사회자용 안내 문구뿐이다.

### 하네스도 한 군데 고쳤다 (`thyrsus_sim/harness.js`)

로드 중 `setTimeout` 을 즉시 실행하고 있어서 구조 감사(`thyAudit`)가 **statusboard 래핑이 설치되기
전에** 돌았고, 그 결과 `동적 래핑 불일치: renderGrim` 이라는 거짓 알림이 매 실행 뜨고 있었다.
브라우저처럼 로드 중에는 큐에 쌓고 모든 `<script>` 블록이 끝난 뒤 흘리도록 바꿨다.
**거짓 알림은 진짜 알림을 가린다** — 감사를 고쳐 놓고 그 출력을 못 믿으면 고친 값이 0이 된다.
(`rules_check` 에 한 번 남는 경고는 감사가 잡는지 보려고 테스트가 일부러 원장을 지운 것이다.)

---

## 라운드 13 — 체크리스트 키 중복 수리 (2026-09-10)

커스텀 퍼저 90판 중 1판에 계속 남아 있던 `checklist_dupkey_audit` 를 걷어냈다. **기준선에 있는
위반은 시간이 지나면 배경 소음이 된다** — 다음 사람이 "원래 1건 나온다"고 넘기는 순간 진짜 회귀가
그 뒤에 숨는다.

### 무엇이었나
시트 검증 경고의 체크박스 키가 `'shadow:'+c.id` 처럼 **커스텀 id 에서** 나온다. 그런데 커스텀 id 는
중복될 수 있다(중복 자체는 `dupid:` 경고가 따로 낸다). 같은 id 를 쓰는 커스텀 둘이 동시에 기본
캐릭터를 가리면 `shadow:slayer` 키가 두 번 찍히고, **두 경고가 체크 상태를 공유한다** — 사회자가
하나만 '확인함'을 눌러도 둘 다 확인된 것처럼 보인다. 안 본 경고를 봤다고 착각하게 만든다.

### 계열마다 고치지 않고 키를 찍는 자리에서 고쳤다
`shadow:`·`infoshadow:`·`noko:` 셋이 눈에 보였다. 셋을 각각 고칠 수도 있었지만 `add()` 한 곳에서
막았다 — 회귀 테스트를 수정 전 빌드에 돌리자 **`inert:` 라는 네 번째 계열**이 나왔다. 눈으로 셋을
세고 고쳤으면 그건 그대로 샜다. 키의 유일성은 키를 찍는 자리의 책임이다.

```js
const seenKey={};
const add=(sev,cat,id,txt)=>{
  const n=(seenKey[id]=(seenKey[id]||0)+1);
  out.push({sev,cat,id:(n>1? id+'#'+n : id),txt});
};
```
첫 항목의 키는 건드리지 않는다 — 이미 체크해 둔 상태를 잃지 않기 위해서다.

**검증**: 커스텀 90판 위반 **1 → 0**(커버리지 동일) · 규칙 39케이스 0실패(신규
`checklistKeysUnique`) · 종료 25 · 더미 220 · 퍼저 400판 위반 0(커버리지 동일) ·
돌연변이 40종 미검출 0. 돌연변이 기준선의 커스텀 칸이 `[checklist_dupkey_audit]` → `[-]` 로 비었다.

---

## 라운드 14 — Codex astra ultra 전수감사 1차 반영 (2026-09-10)

`gpt-6-astra` + `model_reasoning_effort=ultra` 로 5레인(규칙·상태·흐름·구조·운영)을 격리 복사본에서
동시에 돌렸다. **확정 82건(치명 28 · 중대 50)**. 이 라운드는 그중 **내가 직접 재현하고 공식 근거를
확인한 4건**만 반영한다. 레인 산출은 진단으로만 받는다 — 과거에 레인이 낸 "정확한 패치"가 문자열
중간에서 잘려 앱을 죽인 적이 있다.

레인 A(규칙)와 레인 C(흐름)가 **서로 모르는 채 같은 두 건**을 찾았다. 교차 확인된 진단은 무겁게 본다.

### C01/A01 — 보르톡스가 물어야 할 것을 잘못 물었다 [치명]

```
공식 roles181.json : "Each day, if no-one is executed, evil wins."
공식 위키 How to Run: "Each dusk, if no player was executed today, …"
```
게이트는 **'처형이 있었는가'** 다. 앱은 `S.executedDiedToday` 를 읽어 **'처형으로 죽었는가'** 를 물었다.
악마의 변호사·찻집 여인·선원이 처형을 막아 대상이 살아남으면, **처형이 아예 없었던 것과 똑같이**
악 승리를 냈다. 처형은 있었다 — 죽지 않았을 뿐이다.

**여기 적혀 있던 근거 인용문("if no-one died by execution")은 공식에 없는 문장이었다.** 내가 이전
라운드에 그렇게 적었고, 그 잘못된 인용을 따라 코드가 서 있었다.
**근거를 적어 두는 것만으로는 부족하다 — 적어 둔 근거가 원문과 같은지 대조해야 한다.**
이제 보르톡스·레비아탄·시장 세 분기가 모두 같은 게이트(`ctx.executed`)를 쓴다.

### C02/A02 — 오작동한 악마도 승리 조항을 발동시켰다 [치명]

```
공식 용어집 Drunk/Poisoned: "A drunk player has no ability but thinks they do."
```
캐릭터 유형 예외가 없다. 같은 함수의 시장은 이미 `!isMalfunctioning` 을 쓰고 정보 표의 보르톡스
항목도 같은 조건을 본다 — **악마 두 자리만 빠져 있어 파일이 스스로와 어긋나 있었다.**

### B01 — 소생 정정이 그 사망이 소비한 상태를 남겼다 [치명]

`revivePlayer` 의 주석은 "사망에 딸려 소비된 상태를 함께 되돌리지 않으면…"이라고 원리를 이미
적어 놓고 `deadVote`·`diedAt` 둘만 되돌렸다. 좀버얼의 `fakedead` 는 **그 사망이 소비한 1회 생존**
인데 남아서, 살아난 좌석이 첫 사망을 이미 써 버린 상태가 됐다. 오늘 처형 사망 기록
(`executedDiedToday`)도 함께 정정한다 — 남으면 장의사에게 **살아 있는 좌석**을 알려준다.
`executedToday`(처형이 있었다는 사실)는 지우지 않는다. 처형은 실제로 있었고 위 C01 판정이 그것을
본다 — 사망만 정정하는 것이 사실에 맞다.

### B02 — 「첫 번째 밤 시작」이 첫 밤을 시작하지 않았다 [중대]

설정 ③의 금색 버튼이 `advancePhase()` 를 직접 불렀다. `advancePhase` 는 `S.phase.kind` 로 분기하므로
지난 판이 낮 2에서 끝났으면 '낮→밤' 분기로 들어가 **밤 3**으로 갔다 — 종료 상태와 판 식별자까지
그대로. 진행 중인 판에서는 밤 4로 갔다. 2765의 뒤처리(`clearEndedGameState`)는 정확히 이 시나리오를
서술해 놓고도 `setup` 분기 안에만 있었고, `S.phase.kind` 가 `'setup'` 이 되는 자리는 `blank()`·
마이그레이션뿐이라 **판이 한 번 시작하면 그 분기는 영영 오지 않는다.**

**이건 내 테스트의 실패다.** `endflow_check.js` 의 `newGameAfterUnfinalized` 가
`S.phase={kind:'setup',n:0}` 를 **직접 주입**하고 `advancePhase()` 를 불렀다. 그래서 '그 분기가
옳은가'만 증명했고 '실제 UI 가 그 분기에 닿는가'는 한 번도 묻지 않았다. 이미 같은 교훈을
디스패치(여관 주인)에서 배웠는데 종료 흐름에서 그대로 반복했다.

고치는 방향도 바꿨다. 버튼의 동작만 고치면 화면은 여전히 거짓말을 한다 — 낮 3이 진행 중인데
"🏰 게임 준비 완료! 첫 번째 밤을 시작하세요"라고 말한다. **화면이 상태를 사실대로 말하게** 했다:

| 상태 | 전 | 후 |
|---|---|---|
| 진행 중(낮 3) | "게임 준비 완료! 첫 번째 밤을…" → 밤 4 | "게임이 진행 중입니다(낮 3일차)" + [진행 중인 판으로 돌아가기] |
| 끝났으나 미마감 | 같은 문구 → 밤 3 | "지난 판이 아직 마감되지 않았습니다" + [지난 판 마감하고 새 판 준비] |
| 준비 상태 | 정상 | 그대로 |

진행 중인 판을 조용히 버리는 경로는 **만들지 않았다.** 새 판 경로는 앱이 이미 가진 하나
(`finalizeEndedGame` → 설정 ① 참가자)로 보낸다. `startFirstNight()` 은 낡은 렌더가 남아도
페이즈를 진행시키지 않는 방어선으로만 남는다.

**검증**: 규칙 42케이스 0실패(신규 3) · 종료 26케이스 0실패(신규 1 — **전제를 주입하지 않는다**) ·
더미 220 · 퍼저 400판 위반 0(커버리지 기준선 동일) · 커스텀 90판 위반 0 · 돌연변이 40종 미검출 0.
새 테스트 4개 전부 수정 전 빌드에서 정확히 실패하는 것을 확인했다.

### 다음 라운드로 넘긴 것 — 오작동 가드 12곳이 같은 결함을 갖고 있다

레인 C03 을 조사하다 전수로 확인했다. 효과 함수 17종 중 12종이 **똑같은 모양**의 가드를 쓴다:

```js
const monk=S.players.find(q=>q.charId==='monk');
if(monk && isMalfunctioning(monk)){ …불발… }
```

`&&` 때문에 **좌석을 못 찾으면 가드가 조용히 통과한다.** 주정뱅이가 수도사로 위장한 판에는
`charId==='monk'` 인 좌석이 아예 없어서, **있지도 않은 수도사의 보호가 실제로 부여된다.**
위저드는 행동하는 좌석(`wiz.holder`)을 이미 알고 있는데 효과 호출에서 그것을 버린다.
나머지 5종(`doCurse`·`doMad`·`doMaster`·`doSnakeSwap`·`doSwapChars`)에는 가드가 아예 없다.

고칠 자리는 하나다 — "이 단계의 능력이 실제로 작동하는가"를 **행동 좌석 기준으로** 답하는 창구를
두고 17곳이 그것만 읽게 한다. 다만 실패를 열림(fail-open)에서 닫힘(fail-closed)으로 뒤집는
변경이라, 죽었지만 능력을 유지하는 좌석(비고르모르티스) 같은 예외를 전수로 세지 않으면 멀쩡한
능력을 막는다. 표의 술어에 새 사인을 더할 때 기존 술어를 전수로 다시 봐야 한다는 교훈이 그대로
적용된다 — 별도 라운드로 뺀다.

---

## 라운드 15 — 오작동 가드가 '좌석을 못 찾으면 통과'하던 것 (2026-09-10)

레인 C03 을 조사하다 전수로 확인한 것: 밤 효과 함수 17종 중 **12종이 똑같은 모양**이었다.

```js
const monk=S.players.find(q=>q.charId==='monk');
if(monk && isMalfunctioning(monk)){ …불발… }
```

`&&` 때문에 **좌석을 못 찾으면 가드가 조용히 통과한다.** 주정뱅이가 수도사로 위장한 판에는
`charId==='monk'` 인 좌석이 아예 없어서, **있지도 않은 수도사의 보호가 실제로 부여됐다.**
공식 Drunk: "You think you are a Townsfolk character, but you are not." 가짜 수도사는 아무도
보호할 수 없다. 위저드는 그 단계를 수행하는 좌석(`wiz.holder`)을 이미 알고 있는데 효과 호출에서
그것을 버렸다 — 정보 표에서 `sourceCharId` 와 `t.charId` 를 가른 것과 같은 종류의 실수다.

### 창구 하나로 막았다

`abilityActs(p)` / `abilityActor(charId)` 를 두고 12곳이 그것만 읽는다. 각 함수의 문구·동작은
그대로 두고 **좌석을 찾는 방식만** 바꿨다. 실패 방향은 열림(fail-open) → **닫힘**(fail-closed)이다.

닫힘으로 뒤집으면 '죽었지만 능력이 작동하는 좌석'을 전수로 인정해야 한다. 세 부류다:

| 부류 | 근거 |
|---|---|
| 좀버얼 죽은 척 | 겉보기 사망·실제 생존 |
| 비고르모르티스가 죽인 하수인 | "Minions you kill keep their ability" — 비고르모르티스가 살아 정상인 동안 |
| **사망이 곧 발동 조건인 능력** | 까마귀지기·현자·이발사·연인·달의 자손 / 얼뜨기 |

세 번째를 처음에 빠뜨렸고, **시나리오 220건 중 `moonchild-pick-frozen-good` 1건이 잡았다.**
그 좌석은 죽었기 때문에 행동하는데 '죽었으니 행동 불가'로 막았다. 목록은 밤·낮 순서가 이미
쥐고 있는 것(`DEATH_TRIGGER_STEPS`·`DAY_DEAD_TRIGGER`)을 그대로 읽는다 — 따로 세면 어긋난다.

### 이름을 바꾸면 뒤의 사용처가 끊긴다 — 그리고 `try/catch` 가 그걸 삼킨다

가드 변수(`ik`·`fg`)를 개명하면서 같은 함수 뒤쪽의 사용처를 놓쳤다. 하나는
`try{ emitEv('protect', ik?…) }catch(e){}` 안이라 **ReferenceError 가 조용히 삼켜졌고**, 보호는
걸리는데 원장에만 안 남았다. 규칙 44케이스 중 `innkeeperViaWizard` 가 "보호 이벤트가 2건이
아님: 0" 으로 잡았다. 추출 리팩터링의 교훈(식과 호출부를 따로 증명하라)이 개명에도 그대로 적용된다.
**빈 catch 는 회귀를 숨긴다.**

### 퍼저가 비현실적으로 몰고 있었다

수정 뒤 퍼저 커버리지가 `avgLog` 29.4 → 27.6 으로 떨어졌다. 원인은 퍼저가 **독살범·수도사가
판에 없어도** `doPoison`/`doProtect` 를 부르고 있었고, 옛 fail-open 가드가 그걸 전부 통과시켜
없는 능력의 효과가 실제로 걸리고 있었다는 것이다 — 커버리지 감소는 고친 결함 그 자체였다.
퍼저를 "좌석이 있을 때만 부른다"로 고치자 **두 빌드의 커버리지가 25.8 로 완전히 같아졌다.**
차이는 오직 그 결함 하나였다는 차등 증명이다.

### C04 — 뱀 조련사가 공식과 달랐다 [치명]

```
공식: "Each night, choose an alive player: a chosen **Demon** swaps characters &
       alignments with you & is then poisoned."
```
씬이 `n:2` 로 두 명을 받고(플레이어는 한 명만 고른다) `doSnakeSwap` 이 **조건 없이** 맞바꿨다.
공식대로 한 명만 지목한 플레이어는 반환조차 못 했고, 사회자가 화면의 두 자리를 채우면 멀쩡한
두 사람의 캐릭터·진영이 뒤바뀌었다 — 악마는 그대로 둔 채. 이제 `n:1` 이고, 대상이 악마일
때만 교환하며, 조련사가 오작동이면 불발이다.

**검증**: 규칙 44케이스 0실패(신규 2) · 종료 26 · 더미 220 · 퍼저 400판 위반 0
(커버리지 25.8 — 수정 전 빌드와 **동일**) · 커스텀 90판 위반 0 · 돌연변이 40종 미검출 0.
차등: 가짜 수도사 보호 `true→false` · 수도사 없는 판 보호 `true→false` · 독살범 없는 판 중독
`true→false` · **진짜 수도사·독살범은 `true→true`**(과잉 차단 없음).

### 아직 가드가 없는 4종

`doCurse`·`doMad`·`doMaster`·`doSwapChars`. 각각 공식 근거를 확인해야 해서 다음 라운드로 둔다.

---

## 라운드 16 — 여행자 인원과 무신론자 (2026-09-10)

### C06 — 두 규칙의 인원 기준이 실제로 다르다 [치명]

```
공식 Character Types: "They do not count as players for the evil win condition —
    when a Traveller and two regular players are alive, evil has won."
공식 Mayor(How to Run): "Travellers count as players for the Mayor's victory,
    so must be exiled first."
```
기본 악 승리('생존 2인')는 여행자를 **빼고** 세고, 시장의 3인은 여행자를 **포함**한다.
앱은 `realAliveCount()` 하나로 둘 다 처리했다 — 일반인 2 + 여행자 1이면 이미 악이 이겼는데
3명으로 읽어 판을 계속 굴렸고, 선이 다음 처형으로 악마를 잡을 기회를 얻었다.

**하나로 합치면 둘 중 하나가 반드시 틀린다.** `realAliveCount` 는 시장용으로 그대로 두고
`realAliveNonTravelerCount()` 를 따로 뒀다. 죽은 척 좀버얼 보정은 양쪽 모두에 있다.

### C07 — 무신론자는 '사회자'가 처형돼야 한다 [치명]

```
공식 roles181.json : "The Storyteller can break the game rules, and if executed,
                      good wins, even if you are dead."
공식 위키 How to Run: "Good wins if the Storyteller is executed."
```
앱은 **무신론자 좌석**을 처형하면 선 승리 확인창을 띄웠다. 무신론자를 찾아낸 악한 팀이 그
처형으로 오히려 지는 뒤집힌 판정이었다.

같은 파일의 **폭동×무신론자 징크스는 맞게 적혀 있었다** — "사회자가 지명되면 투표를 진행한다.
사회자가 처형될 만큼 표를 받으면 게임이 끝나고…". 규칙이 한 파일 안에서 두 벌로 적혀 서로
어긋나 있었고, 승리 판정은 틀린 쪽을 따랐다. 한국어 능력문·백과·리마인더도 전부 틀린 쪽이었다
— 함께 고쳤다. **규칙 설명문은 장식이 아니라 사회자가 실제로 따르는 지시다.**

승리는 이제 자동으로 나지 않고, 처형 시 사회자에게 진짜 조건을 알려 준다(마을이 사회자를
지명·처형하면 종료 메뉴에서 [선한 팀 승리]를 선언). 앱이 관측할 수 없는 사건이므로 선언 경로가
맞다 — 고블린·선한 쌍둥이와 같은 계약이다.

**검증**: 규칙 46케이스 0실패(신규 2, 수정 전 빌드에서 정확히 실패) · 종료 26 · 더미 220 ·
퍼저 400판 위반 0(커버리지 25.8 동일) · 커스텀 90판 위반 0 · 돌연변이 40종 미검출 0.

---

## 라운드 17 — "your team" 은 현재 진영이다 · 성결자 처형이 판정을 못 받았다 (2026-09-10)

### C08 — 승리 팀을 캐릭터 기본색으로 굳혀 두었다 [치명]

```
공식 Saint : "If you die by execution, **your team** loses."
공식 Goblin: "…your team wins."
공식 Mayor : "If only 3 players live & no execution occurs, **your team** wins."
```
셋 다 팀이 **지금 그 좌석의 진영**이다. 앱은 성자·고블린을 항상 악, 시장을 항상 선으로 굳혔다.

이발사 교환은 **캐릭터만 바꾸고 진영은 각자 보존**한다(앱이 이미 지키는 공식 계약,
`applySwapAlignment`). 그래서 악한 성자·선한 고블린·악한 시장이 실제로 생긴다. 그때
승자가 통째로 뒤집혀 표시됐다 — 사전 안내 문구부터 전적에 적립할 승리값까지 같은 값을 썼다.

진영은 `isEvil(p)` 한 곳에서만 읽는다(이미 `p.alignment` 를 캐릭터보다 먼저 본다).
문구도 함께 고쳤다 — "선한 팀이 패배합니다"가 아니라 "**그 좌석이 속한 팀**이 패배합니다,
지금은 악한 팀"처럼 실제 값을 말한다.

### C09 — 성결자 즉시 처형이 판정 하나를 통째로 건너뛰었다 [치명]

처형 판정은 두 벌이다:
- `executeAct`(처형이라는 **행위**가 조건) — `resolveExecution` 래퍼에 있다
- `execute`(처형으로 **죽었는가**가 조건: 성자·선한 쌍둥이) — `executeNominee` 래퍼에만 있었다

성결자 발동은 `executeNominee` 를 거치지 않고 `resolveExecution` 을 직접 부른다. 그래서
**성결자로 즉시 처형된 선한 쌍둥이의 악 승리가 조용히 사라졌다**(통상 투표 처형은 정상).
바로 위 주석이 "두 경로가 공유하는 유일한 통로가 여기다"라고 적어 두고도 판정 하나만
그 통로에 붙였다. 나머지 하나를 같은 자리로 옮겼다.

**검증**: 규칙 48케이스 0실패(신규 2, 수정 전 빌드에서 정확히 3건 실패) · 종료 26 · 더미 220 ·
퍼저 400판 위반 0(커버리지 25.8 동일) · 커스텀 90판 위반 0 · 돌연변이 40종 미검출 0.

---

## 라운드 18 — 감사 잔여 치명 재검증과 6건 반영 (2026-09-10)

레인들이 본 것은 **6라운드 전 스냅샷**이었다. 그 뒤 줄 번호가 밀렸고 일부는 이미 고쳐졌다.
그래서 잔여 치명 17건을 **현재 빌드 기준으로 다시 재현**하고, 살아남은 것마다 렌즈 셋
(규칙 해석 · 재현 진위 · 이미 해결됐는가)으로 **반박을 시도**하는 워크플로를 돌렸다.
에이전트 68개, 오류 0.

| 판정 | 건수 | 항목 |
|---|---:|---|
| 생존(3/3 확정) | 8 | A03 A04 A06 A08 A12 A16 A18 C05 |
| 생존(2/3) | 2 | A15 A17 |
| 생존(약함) | 2 | A14 B10 |
| **반박 기각** | **5** | A05 A07 A09 A10 A13 |

### 반박이 5건(29%)을 걸렀다 — 이것이 이 라운드의 가장 큰 값이다

그대로 구현했으면 전부 **규칙 회귀**가 됐을 것들이다.

- **A07 사이코패스 무승부** — 헤드라인이 **재현 자체가 안 된다.** 앱에 무승부를 표현하는
  상태·입력·코드 경로가 없다(`'비김'` 0건, `'재경기'` 0건).
- **A09 집사 실수 표** — 근거로 든 위키 운영지침 문장이 **공식 원문 어디에도 없다.**
- **A10 교수 소생** — "되살아난 플레이어는 1회성 능력도 회복한다"가 원문에 없고 반대를 가리킨다.
- **A13 군인·수도사 면역** — `"safe from the Demon"` 을 '악마의 모든 효과에 면역'으로 읽은 것이
  틀렸다. 공식에 **악마 본인 능력으로 중독을 거는 악마가 넷** 있다.
- **A05 여관 주인** — 재현은 되나 '해결 시점 모델'이고, 지적이 확실하다고 내세운
  "앱 자신의 계약 위반"이 사실이 아니었다.

**규칙 오해로 두 번 다친 프로젝트다. 적대적 반박을 붙이지 않으면 세 번째가 온다.**

### 반영 6건

| 건 | 무엇이 틀렸나 | 공식 근거 |
|---|---|---|
| **A03 리치** | 주석이 `"if & only if"` 를 "리치의 능력이 아니라 **존재 규칙**"이라 단언 — 그 구분이 공식에 없다 | 공식은 그 문장을 `ability` 필드에 넣었고, 주모자 징크스는 연결을 끊는 수단을 `"loses their ability"` 라 부른다. 위키 예시: *"The drunk Lleech is executed and dies, and good wins."* |
| **A08 일탈자** | 자기-능력 면역 일곱은 전부 오작동 게이트를 갖는데 일탈자만 빠져 표가 스스로와 어긋남 | `"If you were funny today, you cannot die by exile."` — 자기 능력 |
| **A06 악마의 변호사** | 변호사가 죽거나 캐릭터를 잃어도 `execProtect` 토큰이 남아 **없어진 변호가 처형을 계속 막음** | 같은 부류인 수도사·여관 주인 보호는 이미 정리 대상이었다 — 내부 모순 |
| **A12 얼뜨기·아가씨** | `"your team loses"` 를 팀 상수로 굳힘. 성자·고블린·시장은 이미 고쳤는데 둘만 남아 어긋남 | 이발사 교환이 진영을 보존하므로 악한 얼뜨기가 앱 자체 경로로 생긴다 |
| **A16 얼뜨기 지목** | 좌석 전체를 후보로 넣고 콜백도 생사를 안 봐 **불법 지목이 승패 판정에 들어감** | `"publicly choose 1 alive player"` — 달의 자손이 집 안의 올바른 선례 |
| **C05 좀버얼** | 낮 지명 경로 네 곳이 `alivePlayers()` 하나만 봐서 죽은 척 좌석을 지명 불가로 만듦 | `"The 1st time you die, **you live** but register as dead."` — 앱도 `abilityActs`·`realAliveCount` 에서 이미 그렇게 안다 |

A03 의 실제 결과가 특히 무겁다: 독살자·궁정대신으로 리치를 오작동시켜 **처형해도 앱이 막아
선 승리가 사라졌다.** C05 는 "두 번째 사망이 진짜"라는 공식 조항을 앱 안에서 **도달 불가능**
하게 만들고 있었다 — 처형이 앱의 유일한 마을 살해 수단인데 그 문이 닫혀 있었다.
네 자리를 `nomineeEligible()`/`canBeNominated()` 하나로 모았다. 한 곳만 풀면 지명은 되는데
처형이 막히는 반쪽이 된다. 평범한 사망자까지 열 것인지는 공식 캐릭터 코퍼스로 결론이 나지
않아 열지 않았다 — 근거가 직접 있는 좀버얼만 열었다.

**검증**: 규칙 53케이스 0실패(신규 5 · 개별 단정 12개가 수정 전 빌드에서 정확히 실패) ·
종료 26 · 더미 220 · 퍼저 400판 위반 0(커버리지 25.8 동일) · 커스텀 90판 위반 0.

### DOM 골든 게이트를 정식 채택했다 (`thyrsus_sim/dom_golden.js`)

렌더 훅 42곳을 막고 있던 **선행 조건**이 해결됐다. 레인 D 의 프로토타입을 채택하며 임시
런타임 경로 의존을 끊고(`node_modules` 에 jsdom 30.0.1 고정) fixture 7개·양성 대조군 5개를 더했다.

| | 프로토타입 | 채택 후 |
|---|---|---|
| fixture / 프레임 | 11 / 23 | **18 / 31** |
| 양성 대조군 | 4 | **8** |

넓힌 화면: 통계·프로필·등록부·백과·체크리스트·낮 가이드+사망 근거 사슬·좀버얼 피지명 격자 —
전부 한 프레임도 안 잡히던 곳이라 손대도 게이트가 아무 말을 안 했다.
**fixture 를 넣을 때 그 화면을 겨누는 대조군도 같이 넣는다.** 안 그러면 빈 화면을 고정해 놓고
통과하는 게이트가 된다.

그 규율이 바로 값을 했다 — 좀버얼 대조군을 처음엔 `canBeNominated`(버튼 잠금)에 걸었는데
fixture 가 아무도 고르지 않아 차이가 안 났고, 게이트가 `mutants 7/8` 로 **내 대조군이 무력하다는
것을 알려줬다.** 격자를 실제로 그리는 `nomineeEligible` 로 옮겨 8/8 이 됐다.

이번 라운드 차등: 직전 빌드 대비 3개 fixture 에 차이가 났고, 실제 내용을 열어 보니
**전부 내가 편집한 HTML 주석 하나**였다 — 기능 변경 0. 게이트가 주석 수준까지 민감하다.

**범위 밖**: 레이아웃·그리기·폰트·터치. jsdom 은 layout/rendering 을 구현하지 않는다.
CSS 파싱 실패가 부팅당 9개 기록되는데 **JS 오류 0과 CSS 정상은 같은 말이 아니다.**
자세한 계약은 `thyrsus_sim/DOM_GOLDEN.md` 에 있다.

### 다음 라운드로 남긴 것

A04(임프 자살이 사망 차단 표를 통째로 건너뜀) · A18(Fiddler 승리 팀을 선택지 id 로 굳힘) —
둘 다 3/3 확정이지만 구조 변경이 커서 따로 뺀다. A15·A17(2/3) · A14·B10(약함)은 근거를
한 번 더 확인한 뒤 판단한다.

---

## 라운드 19 — 임프 자살과 바이올린 연주자 (2026-09-10)

라운드 18에서 3/3 확정이었지만 구조 변경이 커서 뺐던 둘.

### A04 — 임프 자살이 사망 차단 표를 통째로 건너뛰었다 [치명]

```
공식 Imp: "Each night*, choose a player: they die.
           If you kill yourself **this way**, a Minion becomes the Imp."
```

`doImpKill` 의 자살 분기가 하수인 승격을 끝내고 곧장 `killPlayer` 로 내려갔다. 표를 읽는
유일한 창구인 `resolveDeath(...,['block','substitute'])` 는 **정상 경로에만** 있어서, 수도사·
여관 주인 보호가 임프에게 걸려 있어도 무시하고 죽였고 **죽지 않아야 할 상황에서 별까지
넘어갔다.** `killPlayer` 는 `stage:'kill'` 항목(좀버얼 죽은 척·어릿광대)만 돌리므로
precedence 20 의 보호 토큰, 40 의 군인, 10 의 찻집 여인이 전부 건너뛰어졌다.

`"this way"`(실제로 그렇게 죽었을 때)가 조건이므로 **별 넘기기는 살해의 원인이 아니라 결과다.**
그 한 문장이 순서를 정한다 — 차단 판정을 앞에 둔다. 시장 대체는 자기 지목에서 성립할 수
없으므로(악마가 시장일 수 없다) `block` 만 태운다. 승격 대화의 비동기 재호출 때 같은 판정을
다시 밟지만 `recordDeathTrace` 가 직전 항목과 같으면 적지 않으므로 근거 사슬에는 한 줄만 남는다.

### A18 — 승리 팀을 선택지 id 로 굳혔다 [치명]

```
공식 Fiddler: "Once per game, the Demon secretly chooses an opposing player:
               all players choose which of these 2 players win."
```

승자는 **두 사람 중 하나**이고 승리 팀은 그 사람의 진영에서 나와야 한다. 그런데 `fiddlerCall`
은 두 당사자가 누구인지 아예 받지도 않고 선택지 id 를 그대로 팀 문자열로 썼다 —
'악마 쪽 = 악한 팀'을 상수로 박아 둔 것이다.

이 앱은 진영을 캐릭터에서 유도하지 않고 `p.alignment` 로 따로 들고 있고(`isEvil`), 이발사
교환은 공식대로 캐릭터만 바꾸고 진영은 각자 보존한다 — 그래서 **선한 악마가 앱 자체 경로로
실제로 생긴다.** 그 상태에서 악마가 이기면 코드는 악마의 진영(선)이 아니라 `'evil'` 을 승리
팀으로 제안했다. 반대 선택도 같은 이유로 뒤집혔다.

이제 세 단계로 두 당사자를 먼저 확정하고(① 어느 악마가 썼는가 — 악마가 하나면 묻지 않는다
② 비밀리에 지목한 반대 진영 상대 ③ 전원 투표에서 누가 이겼는가) 이긴 **사람**의 그 시점
진영으로 팀을 만든다. 상대 후보는 캐릭터 타입이 아니라 `isEvil()` 기준의 '반대 진영'으로
거른다 — 선한 악마일 때 악한 플레이어가 후보로 떠야 공식의 `"opposing player"` 와 맞는다.
세 단계 모두 이 앱의 확립된 `thyAsk` + ack 키 + 자기 재호출 패턴을 그대로 쓴다(별 넘기기와 같은 모양).
이단자 반전은 `askWin` 한 곳에서만 하므로 여기서 또 얹지 않았다.

**검증**: 규칙 55케이스 0실패(신규 2 · 개별 단정 4개가 수정 전 빌드에서 정확히 실패) ·
종료 26 · 더미 220 · 퍼저 400판 위반 0(커버리지 25.8 동일) · 커스텀 90판 위반 0 ·
돌연변이 40종 미검출 0 · **DOM 골든 게이트 직전 빌드 대비 차이 0**(렌더 무행동).

---

## 라운드 20 — 만장일치가 아니었던 넷 중 셋 (2026-09-10)

라운드 18의 반박에서 3/3 이 아니었던 넷(A15·A17·A14·B10). 반박자들이 각자 **주장을 좁혀
다시 써 준** 것이 있어서, 그 좁힌 주장만 받아 셋을 반영했다.

### A15 — 확인 문구 한 줄만 규칙과 어긋나 있었다

```
공식 Cult Leader: "Each night, you become the alignment of **an alive neighbor**.
                   If **all good players** choose to join your cult, your team wins."
```
같은 문장 안에서 생존 한정을 정렬 전환에만 붙이고 승리 조건에는 안 붙였다. 공식 코퍼스는
생존 한정이 필요하면 늘 명시한다(Mayor `"3 players live"`, Zealot `"players alive"`).

앱에서 어긋난 곳은 **확인 문구 한 줄뿐**이었다 — 바로 아래 `reason`·`rule` 과 캐릭터 카드·
코드 주석은 전부 "선한 플레이어 전원"이다. 그런데 **사회자는 화면 문구를 따른다.**
문구가 규칙과 갈라지면 그 문구가 사실상의 규칙이 된다.

### A17 — 문서와 코드가 갈라져 있었다

```
공식 Spirit of Ivory: "There can't be more than 1 extra evil player."  (reminders: "No More Evil")
```
앱 자신의 howto 가 이미 적어 두었다 — *"이미 한도에 도달했다면 이후의 성향 전환은 그냥
일어나지 않는다. 대상 본인에게는 아무 일도 없었던 것처럼 처리해 정보가 새지 않게 하라."*
그런데 건달 자동 전향만 그 상한을 한 번도 보지 않았다. **규칙 해석 다툼이 아니라 문서-코드
불일치다.**

기준선이 어디에도 없어서 선언 스키마에 `startEvilCount` 를 새로 뒀다(첫 밤이 열리는 자리에서
한 번 찍는다). `blank()` · `migrateState` · **`NEWGAME_RESET_KEYS` 셋 다**에 넣었다 —
`gameOver` 가 초기화 목록에 없어 새 판에 종료 상태가 눌어붙었던 사고가 이 교훈의 출처다.
옛 저장본은 `null` 이 되고, `null` 이면 상한을 걸지 않으므로 종전 동작 그대로다.

### B10(좁힌 주장) — 소진 검사가 '요청 시점'에만 있었다

```
공식 Slayer: "**Once per game**, during the day, publicly choose a player…"
```
`doSlayer` 의 `!hasStatus(p,'slayerUsed')` 는 **요청을 만드는 시점**에만 평가되고, 콜백은 `sl` 을
클로저에 얼려 둔다. 대화상자가 열려 있는 동안 진입 함수가 한 번 더 불리면 큐에 두 건이 쌓여
두 콜백이 모두 실행되고, **첫 오발 뒤에도 두 번째 지목으로 악마를 죽일 수 있었다.**

원래 지적(B10)은 "중복 승인"이라고 썼는데 반박자가 그것을 깨고 "**요청 중복**"으로 좁혀 줬다 —
그리고 규칙 근거가 확실한 것은 처단자 한 건뿐이라고 명시했다. 그 좁힌 주장만 받았다.
고칠 자리는 **소비하는 쪽**이다: `doSlayerOn` 진입에서 소진을 다시 본다.

### A14 는 받지 않았다

반박자 하나가 헤드라인 자체를 깼다 — 앱이 철학자에게 실제로 태우는 경로(`NIGHT_FLOW.philosopher`)
에는 `effect` 씬이 아예 없고 `storeAs:'gain'` 은 아무 데서도 소비되지 않는다. 남은 주장은
사회자 수동 경로(`ccApply` 의 `'philosopher'` 사유)에 한정되는데, 그 경로에서 정체를 바꿀지는
공식 코퍼스로 결론이 나지 않는다(`philosopher` 는 `"gain that ability"`, `pithag` 는
`"a character they **become**"` 으로 표현이 갈린다). **근거가 갈리는 것은 손대지 않는다.**

**검증**: 규칙 58케이스 0실패(신규 3 · 개별 단정 5개가 수정 전 빌드에서 정확히 실패) ·
종료 26 · 더미 220 · 퍼저 400판 위반 0(커버리지 25.8 동일) · 커스텀 90판 위반 0 ·
돌연변이 40종 미검출 0.

**DOM 골든 게이트가 18개 fixture 전부에서 울렸다 — 그리고 그게 맞다.** `blank()` 에 필드를
더하면 `S` 를 비교하는 모든 프레임이 달라진다. 끄지 않고 **달라진 것이 그 필드뿐인지** 확인했다:
`달라진 S 키: startEvilCount`. 하나뿐이므로 의도한 만큼만 번진 것이다. 확인 방법은
`thyrsus_sim/DOM_GOLDEN.md` 에 적어 두었다.

---

## 라운드 21 — 화면이 엔진과 다른 말을 하던 넷 (2026-09-10)

감사 잔여 중대 중 **행동 결함 14건**(B04~B09·C10~C17)을 현재 빌드로 재검증했다.
에이전트 56개, 오류 0. **생존 14 · 반박 기각 0.**

치명 배치에서 29%가 무너진 것과 정반대다. 이유가 분명하다 — **C 레인은 애초에 재현을 붙여
왔고, B 레인은 앱 자신의 주석에 적힌 계약을 근거로 삼았다.** 규칙 해석 다툼이 아니라
"앱이 스스로 선언한 것을 코드가 안 지킨다"는 유형이라 반박할 여지가 없다.

이번 라운드는 그중 **화면이 엔진과 다른 말을 하던 넷**을 반영한다.

### C16 — 보르톡스 판에서 건강한 능력에 "효과 없음"이라 지시했다

```
공식 Vortox: "Townsfolk abilities yield **false info**."
```
보르톡스는 **정보만** 제약한다. 그런데 밤 카드가 `mode!=='true'` 를 곧바로 "능력 오작동 상태"로
번역하고 같은 문장에서 "발동형이면 효과 없음"까지 지시했다. 중독도 취함도 아닌 **건강한**
수도사·뱀 조련사가 오작동으로 이름 붙고 능력이 무효라고 안내됐다.

**판정 엔진은 정반대로 동작한다** — `abilityActor` 는 `isMalfunctioning` 만 보므로 그 수도사의
보호는 정상 부여된다. 화면이 엔진과 어긋난 지시를 하고 있었다. 라운드 12에 함께 옮겨 탄
위저드 경고바는 이미 사유를 그대로 뿌려 맞는 문구를 냈는데 **밤 카드만 옛 술어 시절의 고정
문장을 들고 있었다.** 이제 두 축(오작동 / 정보만 거짓)을 갈라 쓴다.

### C17 — 낮 가이드가 같은 파일의 엔진 계약과 어긋났다

| 가이드가 한 말 | 엔진이 하는 일 |
|---|---|
| 2차는 생존자 전원 + 사망 투표 **토큰 보유자** | `ballotEligible` 은 1차에 **거수한** 사망자만 분모에 넣는다 |
| 하루의 지명 중 **찬성률 최고**가 처형 | `if(!best||n.yes>best.yes)` — **raw 표수**로 비교한다 |
| 배너 "최고 **찬성률** 동률" | 판정은 `n.yes` 기준 |

바로 위 하우스룰 카드는 셋 다 **올바르게** 적혀 있다 — 의도적 단순화가 아니라 갱신 누락이다.
투표 산술·자격 판정은 이미 옳으므로 **문구만** 맞췄다.

### B07 — 무승부를 `good` 으로 접었다

앱 자신의 선택지 설명이 "무승부 · 중단 — **승패 없이 마감합니다**" 인데, 커밋 함수가
`draw → 'good'` 으로 접어 종료 상태·화면·로그·저장본에 흘려보냈다. 종료 화면 제목은
🕊️ "선한 팀 승리", 로그는 "게임 종료 — 선한 팀 승리: 무승부·중단(사회자 선언)" 이라는
**자기모순 문장**이 됐다.

그리고 그 위조된 팀 값이 **판정에 실제로 쓰였다** — 정치인 게이트가
`(isEvil(pol)?'evil':'good')!==team` 으로 "내 진영이 졌는가"를 계산한다. 승리 팀이 없는
종료에서는 그 질문 자체가 성립하지 않는다. 이제 묻지 않고, **판당 1회 플래그도 태우지 않는다**
— 태우면 그 판에서 다시는 못 묻는다.

### B08 — 제한을 풀어도 만료 경고가 화석처럼 남았다

`_dtTick` 이 `if(lim>0)` 안에서만 안내 요소를 건드려서, 제한을 0으로 바꾸면 직전 틱이 써 둔
문구와 `pill warn` 클래스가 그대로 남았다. 상태는 0으로 정확히 저장되고 토스트도
"낮 제한시간 해제"를 띄우는데 **화면만 옛 제한을 계속 말한다.** 만료 뒤 해제뿐 아니라
만료 전 해제도 같다("남은 시간 04:30"이 얼어붙는다).

**한 요소의 표시 계약이 두 벌이었던 것이 결함의 본질이다** — 렌더 초기 마크업은 '제한 없음'
표현을 알고 있었는데 매초 도는 틱만 몰랐다. 이제 틱이 두 경우를 한 자리에서 결정한다.
문구만 바꾸고 클래스를 남기면 경고 색이 그대로라 반쪽 수리가 되므로 클래스까지 되돌린다.

**검증**: 규칙 61케이스 0실패(신규 3 · 개별 단정 7개가 수정 전 빌드에서 정확히 실패) ·
종료 26 · 더미 220 · 퍼저 400판 위반 0(커버리지 25.8 동일) · 커스텀 90판 위반 0 ·
돌연변이 40종 미검출 0.
**DOM 골든 게이트**: 6개 fixture 에 차이(전부 의도한 문구·무승부 표시) · CSS 원문 변경 True
(`.goteam.draw` 추가) · **달라진 S 키는 `log`·`postgame` 둘뿐**.

---

## 라운드 22 — 밤 순서가 조용히 좁아지던 셋 (2026-09-10)

### C11 — 첫밤과 이후밤이 같은 능력인데 범위가 달랐다

```
공식 Cerenovus: firstNightReminder === otherNightReminder
                "The Cerenovus chooses a player & a character."
ability: "Each night, choose a player & **a good character**: they are 'mad'…"
```
능력문이 **글자 하나 다르지 않고**, 생존 한정도 없으며, 캐릭터는 "a good character" —
주민 **또는 외지인**이다. 그런데 이후밤 가지만 `filter:'alive'` · `pool:'townsfolk'` 로
좁아져 있어 **둘째 밤부터 사망자와 외지인이 선택지에서 조용히 사라졌다.**
(`roles181.json` 에서 생존 한정을 본문에 명시하는 역할은 11개이고 세레노버스는 그 목록에 없다.)

### C12 — 위장 밤 단계가 기반 에디션으로 잠겨 있었다

`S.edition==='tb'` 가 두 곳에 손으로 복사돼 있었고(주석 자체가 "nightSteps() 의 mask 와 같은
기준"이라고 적고 있었다) BMR·SV 기반 커스텀 대본에서는 주정뱅이 위장 단계가 **통째로 사라졌다.**

정작 앱은 스스로 그 반대를 약속한다 — `setupIssues` 가 위장 지정을 **강제**하고,
`advancePhase` 가 미지정이면 첫밤을 **막고**, 설정 화면이 "밤 순서에 자동 반영"이라고 **적어 둔다.**
`S.edition` 은 커스텀 대본이 **어느 밤 순서표를 기준으로 삼는가**를 고르는 값이지 능력의 유무를
정하는 값이 아니다. 판정을 `drunkMaskSeat(stepId)` 하나로 모아 두 곳이 그것만 읽게 했다.

### C14 — 사망 트리거 표가 로스터와 따로 놀았다

`DEATH_TRIGGER_STEPS` 가 5종만 담고 있었는데, 로스터에 실려 있는 farmer·poppygrower·hatter·
plaguedoctor·banshee 는 전부 `other:true` 로 밤 단계를 가진다. `stepSkipReason` 이 이들을
트리거로 못 찾고 `!anyAlive` 분기로 흘려보내 **'사망 — 깨우지 않음'** 을 돌려줬다 —
**극성이 정확히 뒤집혀 있었다.** 이 다섯은 **죽어야** 깨우는 역할이고, 공식 otherNightReminder
가 전부 `"If the X died…"` 로 시작한다.

기존 세 종류로는 모자라 둘을 더했다:

| 종류 | 공식 근거 |
|---|---|
| `night-demon` | Banshee `"If the Demon kills you"` — 처형사(死)는 해당 없음 |
| `untildone` | Plague Doctor `"If you haven't done this yet, **do so now**."` — 밤 번호가 아니라 완료 표식이 조건 |

`night-demon` 판정을 위해 `killPlayer` 가 `diedAt.srcType` 을 함께 남긴다. **사인을 모르는 옛
저장본은 숨기지 않고 보여준다** — 사회자가 건너뛰는 비용이 놓치는 비용보다 싸다.

**덤으로 반대 방향도 고쳐졌다**: 전에는 **살아 있는** 농부·양귀비 재배자를 매일 밤 깨웠다
(트리거 표에 없으니 아무 게이트에도 안 걸렸다). 이제 "아직 생존 — 죽는 경우에만 이 시점에
깨움"이 뜬다.

**검증**: 규칙 64케이스 0실패(신규 3 · 개별 단정 9개가 수정 전 빌드에서 정확히 실패) ·
종료 26 · 더미 220 · 퍼저 400판 위반 0(커버리지 25.8 동일) · 커스텀 90판 위반 0 ·
돌연변이 40종 미검출 0.
**DOM 골든 게이트**: 사망이 있는 fixture 둘만 차이 · **달라진 player 키는 `diedAt.srcType` 하나뿐**.

돌연변이 `moonchild_trigger_nextnight_to_night` 의 앵커가 `DEATH_TRIGGER_STEPS` 를 넓히며
상했다(앵커부실 1) — 재앵커했다. **표를 고치면 그 표를 겨눈 돌연변이도 같이 봐야 한다.**

---

## 라운드 23 — 같은 상한을 두 뜻에 쓰던 것 · 진영만 고치고 점수는 안 고치던 것 (2026-09-11)

자동 라운드 1회차. 검증·범위 확정은 Fable 서브에이전트가 맡았고, 구현·검증은 직접 했다.

### B04 — 결과 순위 상한과 투표자 선택 목록 상한이 같은 값을 쓰고 있었다

`migrateState` 의 `pgList` 가 `.slice(0,8)` 을 걸고 그것을 **둘 다**에 썼다:

| 쓰는 곳 | 8이 맞는가 |
|---|---|
| `mvpTop`·`bustTop`·전적 레코드 | ✅ `topOf()` 의 동점 확장 상한(`out.length<8`)과 짝 |
| **`sel`**(현재 투표자가 이번 차례에 누른 목록) | ❌ 근거 없음 — 좌석은 15까지 간다 |

득표 객체는 `pgTally` 로 상한 없이 살아남으므로 **표는 남고 되돌릴 근거만 사라진다.**
`blank()` 의 postgame 주석이 선언한 바로 그 상태다 — *"새로고침으로 표만 남고 되돌릴 수 없게
되는 것을 막으려 함께 저장한다."*

게다가 `pick()` 이 `p.sel.indexOf(pid)` 로 토글하므로, 잘려 나간 좌석을 **취소하려고 다시 누르면
취소가 아니라 +1** 이 된다. 화면에도 `sel` 표시가 없어 투표자는 자기가 그 좌석을 골랐다는 사실
조차 볼 수 없다.

상한을 없애지 않고 15로 나눴다 — 손상·악성 저장본 방어라는 `migrateState` 의 역할은 그대로다.
15의 출처는 `addPlayer`·`ensureSeats`·설정 화면 세 곳이 모두 막는 좌석 상한이다.

### B05 — 진영만 고치고 그 진영에 의존하는 값은 안 고쳤다

`thyPatchBankedAlignment` 가 `r.alignment` 한 필드만 고치고 곧장 `profileRebuild` 를 불렀다.
그런데 `opBreakdown` 은 `isEvil(me)` 로 갈리는 함수다 — 진영이 바뀌면 xEXE 부호가 뒤집히고
선 전용 CROSS 가 빠지며 SURV·HEAT·POLI 가 붙거나 떨어진다.

**게다가 다른 좌석의 점수도 정치인의 진영에 의존한다** — 정치인을 지명·투표한 좌석의 항이
상대 진영으로 갈린다. 그래서 정치인 좌석만 고치는 것으로는 반쪽이고, 그 레코드 **전 좌석**을
다시 확정해야 한다.

**순서가 핵심이다.** `profileRebuild` 는 레코드의 `score` 를 그대로 읽고, `profileSig` 는 점수를
보지 않으므로 다음 렌더가 고쳐 주지도 않는다 — 재확정을 뒤에 두면 옛 점수가 캐시에 굳는다.
관용구는 `finish()` 가 이미 쓰는 것을 그대로 썼다. 규칙을 두 벌로 적지 않는다.

### 검증 중 확인된 경계

Fable 이 **UI 에서 1·2단계 투표를 끝내지 않고 종료 메뉴에 닿는 경로를 찾지 못했다**고 정직하게
보고했다(`#pgvote` z-index 101 > `#pmodal` 95, 투표 화면에 닫기 버튼 없음). 엔진 경로는 실재하고
재현되지만 실사용 도달성은 미확인이다. 그럼에도 고칠 값이 있다 — 답에서 `finish()` 사이에
`S.profiles` 에 옛 점수가 굳고, 정상 흐름에서는 `finish()` 가 **우연히** 덮어 주고 있을 뿐이다.

**검증**: 종료 28케이스 0실패(신규 2 · 개별 단정 7개가 수정 전 빌드에서 정확히 실패) ·
규칙 64 · 더미 220 · 퍼저 400판 위반 0(커버리지 25.8 동일) · 커스텀 90판 위반 0 ·
돌연변이 40종 미검출 0 · **DOM 골든 게이트 차이 0**(렌더 무행동).

---

## 라운드 24 — 한 화면에서 같은 분자를 두 술어로 세던 것 (2026-09-11)

자동 라운드 2회차. 위치·범위 확정과 재현은 Fable 서브에이전트, 구현·검증은 직접.

### C10 — 미리보기와 확정이 갈렸다

한 지명의 찬성 분자를 **한 화면 안에서 두 술어로** 세고 있었다:

| 블록 | 무효 술어 |
|---|---|
| 기본(`renderNomOpen` 원본) | `voteVoided(p, nom)` — **'지금' 판정** |
| 여행자 가중(voting-F 래퍼) | `nom.butlerVoided===p.id` — **지난 마감 기록** |

마감 전에는 `butlerVoided` 가 아직 없으므로 여행자 블록에서 무효표가 되살아났다.
실측: 관료가 집사를 지목한 판에서 **기본 3(fail 색)과 최종 6(pass 색)이 한 화면에 같이 뜨고
마감하면 3 부결.** 관료가 **집사가 아닌** 사람을 지목해도 `rawYes` 가 무효표를 포함해
분자가 1 어긋났다(가중과 무관한 별개의 어긋남).

**이 결함은 코드 주석이 스스로 적어 두고 있었다** — *"마감 전(renderNomOpen)에는 butlerVoided 가
아직 없으므로 화면 미리보기는 그대로다."* 사실 서술로 남겨 두었고 결함으로 읽지 않았다.
이번 감사가 반복해서 드러낸 패턴의 네 번째 사례다.

두 자리(`adjOf` 의 `voided`, 래퍼의 `rawYes`)를 기본 블록과 같은 술어로 맞췄다. 마감 경로에서는
`closeBallot` 이 방금 같은 술어·같은 상태로 `butlerVoided` 를 다시 쓰므로 **확정 결과는 1비트도
안 바뀐다.** 무효 좌석 행 문구도 '아직 찬성표 없음'에서 '집사 무효표 — 가중 대상 아님'으로
고쳤다(그 문구 자체가 또 다른 오안내였다).

### 돌연변이 둘이 masked 에서 풀렸다 — 검출 34 → 35

`butler_void_weight_adjOf` 가 `@masked` 였던 이유는 "두 규칙이 서로를 가려준다"가 아니라
**미리보기를 보는 테스트가 하나도 없었기 때문**이다(그것이 C10 결함 자체였다).
`travelerPreviewMatchesFinal` 를 넣자 단독 검출된다. `rawYes` 를 겨눈 돌연변이도 새로 넣었다.

표를 고치면 그 표를 겨눈 돌연변이 앵커도 같이 본다는 규율이 또 값을 했다 — 앵커부실 2건이
떴고, 재앵커하면서 **분류 자체가 틀렸다는 것**까지 드러났다.

**검증**: 규칙 65케이스 0실패(신규 1 · 개별 단정 4개가 수정 전 빌드에서 정확히 실패) ·
종료 28 · 더미 220 · 퍼저 400판 위반 0(커버리지 25.8 동일) · 커스텀 90판 위반 0 ·
돌연변이 40종 미검출 0(검출 35·masked 4) · **DOM 골든 게이트 차이 0**.

### B06 은 이번 라운드에 넣지 않았다

Fable 이 살아 있음을 확정하고(재부팅 뒤 질문만 사라지고 '이미 물었음'만 남는다) 라운드 21의
무승부 수정이 `draw` 분기만 덮는다는 것도 대조군으로 확인했다. 다만 고치려면 **새 영속 상태**
(`politicianPending`)와 **부팅 시 복구 자리**가 필요하고, 하네스에 '저장본을 넣고 전체 부팅하는'
관용구도 없다. 한 라운드에 섞기에는 범위가 커서 다음으로 뺀다.

---

## 라운드 25 — '물었다'와 '판단이 끝났다'를 한 값으로 쓰던 것 (2026-09-11)

자동 라운드 3회차. B09 는 Fable 이 병행 검증 중이라 이번엔 B06 만.

### B06 — 질문을 꺼내기 전에 '이미 물었음'을 저장했다

`showGameOver` 가 `thyConfirm` 을 부르기 **전에** `S.politicianAsked=true` 를 세우고, 그 상태가
저장됐다(`log()` 가 매번 `save()` 한다). 답을 기다리는 큐(`THY_DLG.q`)는 **메모리에만** 살아서
재부팅하면 질문만 사라지고 '이미 물었음'만 남는다.

게다가 **재부팅 뒤 `showGameOver` 를 다시 부르는 UI 경로가 없다** — 종료 메뉴에는
'동료 평가 이어서 / 결과 다시 보기 / 종료 확정'뿐이다. 그래서 사회자는 판단할 기회를 영영 잃는다.
정치인 질문은 승리 확정 직후 동기적으로 열리고 `#thydlg`(z 150)가 `#pgvote`(101)보다 위라
**그 순간 화면 맨 위에 있다** — 새로고침·모바일 탭 회수가 흔한 자리다.

`politicianPending`(`{pid, team, gid}` 또는 null)을 선언 스키마로 두어 **'꺼냈다'와 '판단이
끝났다'를 갈랐다.** `blank()`·`migrateState`·**`NEWGAME_RESET_KEYS` 셋 다**에 넣었다.

| 상황 | 전 | 후 |
|---|---|---|
| 질문을 꺼냄 | `asked=true` 즉시 저장 | `pending` 저장, `asked` 는 그대로 |
| 답(예/아니오) | — | `asked=true` · `pending=null` |
| 오작동·자기 진영 승리 | `asked=true` | 그대로(그 자리에서 판단이 끝난다) |
| 미응답 재부팅 | 질문 소멸·영구 미판정 | **다시 묻는다** |

**답을 추정하지 않는다** — 미완은 미완으로 남겨 다시 묻는다.

세 가지를 같이 지켰다:
- 질문을 **단일 출처 함수**(`thyAskPolitician`)로 뽑아 `showGameOver` 와 부팅 복구가 같이 부른다.
  규칙을 두 벌로 적지 않는다.
- 콜백에 **gid 가드**를 걸었다. `finalizeEndedGame` 은 열린 대화상자를 닫지 않으므로, 마감 뒤
  도착한 낡은 답이 **새 판의** 플래그를 태우면 안 된다.
- 복구 자리는 포스트게임 IIFE 끝(모든 블록 로드 뒤)이다. `showGameOver` 가 있는 블록 끝에 두면
  동기 훅 환경에서 콜백이 즉시 돌 때 아직 정의되지 않은 `profileRebuild` 를 부른다.

### 하네스에 '저장본을 넣고 전체 부팅' 관용구를 더했다

`load(html, {storage, syncDialog})`. 지금까지는 빈 저장소로만 부팅됐고, 재부팅 검사는
`migrateState` 를 직접 부르는 것으로 대신했다 — 그러면 **부팅 경로의 부수 효과**(재개 렌더·복구
블록)를 못 본다. 앱이 스스로 저장본을 읽게 해야 이 결함을 잡을 수 있다.
`syncDialog:false` 는 대화상자 큐를 관측하려면 필요하다(훅이 있으면 부팅 중 질문이 즉시 답해진다).

**검증**: 종료 30케이스 0실패(신규 2 · 개별 단정 8개가 수정 전 빌드에서 정확히 실패) ·
규칙 65 · 더미 220 · 퍼저 400판 위반 0(커버리지 25.8 동일) · 커스텀 90판 위반 0 ·
돌연변이 40종 미검출 0. **DOM 골든 게이트**는 스키마 필드 추가로 전 fixture 에서 울렸고,
**달라진 S 키는 `politicianPending` 하나뿐**임을 확인했다.
