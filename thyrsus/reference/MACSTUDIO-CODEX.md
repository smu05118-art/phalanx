# 맥스튜디오에서 Codex 리뷰 돌리는 절차 (복사·붙여넣기용)

이 클라우드 세션에서는 맥스튜디오 세션에 메시지를 보낼 수 없는 것으로 확인됨
(계정에 Remote Control(bridge) 세션은 존재하나, 웹 세션의 에이전트 주소록에 등재되지 않음).
따라서 **맥스튜디오에서 직접 실행 → 결과를 git으로 전달** 방식을 쓴다.

## 방법 A — 맥스튜디오의 Claude Code에게 맡기기 (권장)
맥스튜디오 터미널에서 저장소 폴더로 이동해 `claude` 실행 후, 아래를 그대로 붙여넣는다.

```
저장소의 thyrsus/index.html(단일 HTML 앱)을 OpenAI Codex CLI로 교차 검증해줘.

1. git fetch origin claude/trouble-brewing-script-1sv6lg && git checkout claude/trouble-brewing-script-1sv6lg && git pull
2. thyrsus/reference/codex-review-packet.md 를 읽어 리뷰 범위를 확인
3. codex CLI로 리뷰 실행 (설치 여부·서브커맨드는 `codex --help`로 확인 후 맞춰서):
   예) codex exec --full-auto "$(cat thyrsus/reference/codex-review-packet.md)
       대상 파일: thyrsus/index.html. 파일:라인 기준으로 결함을 심각도순으로 보고."
   - 출력이 길면 파일로 받아: ... > /tmp/codex-out.txt
4. Codex 출력을 thyrsus/reference/codex-review.md 로 정리(원문 출력 + 네 요약 포함)
5. git add thyrsus/reference/codex-review.md && git commit -m "Codex 교차 검증 결과" && git push origin claude/trouble-brewing-script-1sv6lg

주의: index.html은 수정하지 마. 리뷰 결과만 커밋해줘. 수정은 클라우드 세션에서 진행한다.
아래 항목은 이미 수정 완료라 중복 보고 불필요:
사망자 투표 분모 불일치, 탕녀 계승 기준, __stepKiller 오귀속, 좀버얼 fakedead 잔존,
별 넘기기 오안내, 위저드 씬 전역 오염, 이름 따옴표 XSS, 낮 보호 토큰 영구 잔존,
체크리스트 속성 탈출, 클라우드 스냅샷 모달 포함, 설정 3단계 ReferenceError,
사망 투표 이름 기반 기록, 악 승리 미감지, 사망자 처형 버튼, 중독 중복, 암살자-어릿광대.
```

## 방법 B — 직접 실행
```bash
cd <저장소>
git fetch origin claude/trouble-brewing-script-1sv6lg && git checkout claude/trouble-brewing-script-1sv6lg && git pull
codex exec --full-auto "$(cat thyrsus/reference/codex-review-packet.md)
대상: thyrsus/index.html. 파일:라인 기준, 심각도순 보고." > thyrsus/reference/codex-review.md
git add thyrsus/reference/codex-review.md && git commit -m "Codex 교차 검증 결과" && git push
```

푸시가 끝나면 클라우드 세션(이 대화)에 "코덱스 결과 푸시했어"라고만 알려주면
내가 pull 해서 결함을 수정하고 회귀 검증까지 진행한다.

## 참고 — 이 세션에서 확인한 계정 상태
- Remote Control(bridge) 세션 다수 존재, 그중 2개가 방금까지 활성(connected)
- 일부는 `computer_unreachable` 로 브리지 재연결 실패 기록 있음
- 이 웹 세션의 ListAgents에는 서브에이전트만 표시되어 bridge 세션을 주소로 지정할 수 없었음
  (`SendMessage` 시도 → "No agent named ... is reachable")
