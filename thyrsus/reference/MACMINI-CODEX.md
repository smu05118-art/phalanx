# 맥미니 로컬 세션에서 Codex 리뷰 실행 (복사·붙여넣기용)

대상: `thyrsus/index.html` (단일 HTML 사회자 도구 "티르소스")
브랜치: `claude/trouble-brewing-script-1sv6lg`
실행 머신: **맥미니 로컬 세션** (맥스튜디오는 다른 작업 진행 중이라 맥미니로 이관)

전달 방식: **git**. 클라우드 세션(웹 대화)에서는 로컬 세션에 직접 메시지를 보낼 수 없으므로,
맥미니에서 실행 → 결과를 브랜치에 푸시 → 클라우드 세션이 pull 해서 반영한다.

---

## 방법 A — 맥미니의 Claude Code 세션에 붙여넣기 (권장)

맥미니에서 이미 열려 있는 Claude Code 세션 아무 곳에나 아래를 그대로 붙여넣는다.

```
smu05118-art/phalanx 저장소에서 OpenAI Codex CLI로 교차 검증을 돌려줘.

1. git fetch origin claude/trouble-brewing-script-1sv6lg
   git checkout claude/trouble-brewing-script-1sv6lg && git pull
2. thyrsus/reference/codex-review-packet.md 를 읽어 리뷰 범위를 파악
3. codex CLI 확인: which codex && codex --version && codex --help | head -30
   - 설치돼 있지 않으면 그 사실만 보고하고 중단(임의 설치하지 말 것)
4. 리뷰 실행 (서브커맨드는 --help 결과에 맞춰 조정):
   codex exec --full-auto "$(cat thyrsus/reference/codex-review-packet.md)
   대상 파일: thyrsus/index.html. 파일:라인 기준으로 결함을 심각도순으로 보고." > /tmp/codex-out.txt
5. /tmp/codex-out.txt 를 thyrsus/reference/codex-review.md 로 정리
   (Codex 원문 출력 전체 + 맨 위에 네 요약 3~5줄)
6. git add thyrsus/reference/codex-review.md
   git commit -m "Codex 교차 검증 결과"
   git push origin claude/trouble-brewing-script-1sv6lg

주의:
- thyrsus/index.html 은 절대 수정하지 마. 리뷰 결과 파일만 커밋한다.
- 아래는 이미 수정 완료라 중복 보고 불필요:
  사망자 투표 분모 불일치, 탕녀 계승 기준, __stepKiller 오귀속, 좀버얼 fakedead 잔존,
  별 넘기기 오안내, 위저드 씬 전역 오염, 이름 따옴표 XSS, 낮 보호 토큰 영구 잔존,
  체크리스트 속성 탈출, 클라우드 스냅샷 모달 포함, 설정 3단계 ReferenceError,
  사망 투표 이름 기반 기록, 악 승리 미감지, 사망자 처형 버튼, 중독 중복, 암살자-어릿광대.
- 푸시가 끝나면 "코덱스 결과 푸시 완료"라고만 응답해줘.
```

## 방법 B — 맥미니 셸에서 직접

```bash
cd <저장소 경로>
git fetch origin claude/trouble-brewing-script-1sv6lg
git checkout claude/trouble-brewing-script-1sv6lg && git pull

which codex && codex --version          # 없으면 여기서 중단

codex exec --full-auto "$(cat thyrsus/reference/codex-review-packet.md)
대상: thyrsus/index.html. 파일:라인 기준, 심각도순 보고." > thyrsus/reference/codex-review.md

git add thyrsus/reference/codex-review.md
git commit -m "Codex 교차 검증 결과"
git push origin claude/trouble-brewing-script-1sv6lg
```

## 방법 C — 푸시 없이

Codex 출력 텍스트를 클라우드 세션(웹 대화)에 그대로 붙여넣어도 된다. 길면 나눠서.

---

## 클라우드 세션이 결과를 받으면 하는 일
pull → 심각도 분류(위 중복 목록 제외) → 유효 결함 수정 → 타깃 테스트 추가 →
회귀 11스위트 실행 → 커밋·푸시 → 아티팩트 재배포 → 보고.

## 참고: 이관 사유 (2026-09-01 확인)
- 맥스튜디오 bridge 세션들은 살아 있으나 전부 다른 작업 중
  (bio_weekly SSH 타임아웃 수정 / Dell 컴포짓 분석 / 플러그인 학습).
- 티르소스 Codex 리뷰 세션은 존재하지 않았고, 원격 브랜치도 8/31 이후 새 커밋 0건.
- 클라우드 세션의 ListAgents에는 bridge 세션이 등재되지 않아 직접 지시 불가
  (SendMessage 시도 → "No agent named ... is reachable").
