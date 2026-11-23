# Issue 분석 sensitive_content 오탐 수정

- 날짜: 2026-11-23 (Asia/Seoul)
- 상태: 완료 (수정·검증 및 PR #14 게시)
- 담당 팀원: SW (`kosa_final-public/.agent-local.md` 기준)
- 참여 AI: Codex, 조사·런타임 수정·회귀 검증
- 공동 작업: 해당 없음
- 목표: 최신 main의 정상 인증 코드와 격리 테스트 fixture가 Issue 분석에서 차단되는 원인을 수정한다.
- 완료 조건: 실제 PRJ snapshot 분석 준비 통과, 새 회귀 테스트와 워크플로 테스트 통과, 변경된 비밀값 차단 유지.
- 변경 범위: workflow/runtime의 민감정보 감지 예외, 관련 테스트·실행 안내, SW 작업 기록.
- 기준: 원격 main `5fce3ff`, 별도 worktree `fix/sensitive-content-analysis`.

## 근거와 계획

- AGENTS.md, PRJ/AGENTS.md, PRJ/rules/project.md, PRJ/rules/infra.md, PRJ/README.md, workflow/runtime/README.md.
- workspace.py, issue_workflow.py, test_run.py, test_issue_workflow.py와 감지된 인증 코드·테스트.
1. 최신 원격 실행과 snapshot을 비교해 모델 호출 전 실패를 재현한다.
2. 확인한 코드 표현식·테스트 fixture만 해당 경로에 허용하고 부정 사례를 검증한다.
3. 오프라인 워크플로 테스트를 실행하고 결과·미확인 사항을 기록한다.

## 조사

- 원격 Actions 실행 `45159686262`는 `5fce3ff`에서 Issue 분석 단계가 실패했다.
- 기존 작업 공간은 `5acb8b0`이며 검사에 통과했다. 최신 main을 별도 worktree로 확인하자 정상 인증 코드·테스트 6개에서 sensitive_content를 재현했다.
- 원인: 인증 관련 코드와 테스트가 변경되었으나 workspace.py의 경로별 검토된 표현식·fixture 목록이 갱신되지 않았다.
- 감지 파일: frontend/src/accounts/server.ts; frontend/tests/server-fixture.ts, app-journey-regressions.spec.ts, app-drafts.spec.ts, supabase-accounts.spec.ts; backend/tests/test_accounts.py (모두 PRJ 하위).
- 선택: 기존 감지 정책에 맞춰 확인된 표현식과 fixture만 추가한다. 전체 테스트 파일 허용이나 민감정보 검사를 해제하는 변경은 하지 않는다.

## 검증·인계

- 수정: workspace.py의 경로별 목록에 확인한 인증 표현식과 격리 fixture만 추가했다. test_run.py에 경로 제한·변경 값·상속 비밀값 회귀 검증을 추가하고 실제 PRJ 분석 준비 테스트의 대상 파일을 보강했다. runtime/README.md에 오탐 점검과 검증 방법을 기록했다.
- 수정 전: 새 회귀 2개와 실제 PRJ 분석 준비 1개를 실행했다. 표현식·fixture 하위 사례 7개가 실패했고 실제 snapshot 준비는 sensitive_content로 중단되었다.
- 수정 후: 같은 3개 테스트 통과 (종료 코드 0).
- 전체 검증: worktree 루트에서 `python3 -B -m unittest discover -s workflow/runtime/tests` 실행, 254개 통과, 10.426초, 종료 코드 0.
- 게시 전 재검증: 같은 명령으로 254개 통과, 9.906초, 종료 코드 0. 원격 main과 기준 HEAD는 같은 커밋이다.
- 정적 검증: `git diff --check` 통과.
- 게시: 사용자 요청에 따라 수정 커밋 `e177912`를 `fix/sensitive-content-analysis` 브랜치로 푸시하고 [PR #14](https://github.com/JunSuHeo/kosa_final-public/pull/14)를 `main` 대상으로 생성했다. 사람 리뷰 대기 상태다.
- 실제 모델 호출·GitHub 댓글·게시·서비스 DB는 사용하지 않았다. macOS 러너의 원격 Actions 재실행은 미확인이다.
- 인계: 최신 main 기준 worktree `fix/sensitive-content-analysis`의 수정 사항을 main에 반영한 뒤 실패한 Issue 분석 이벤트를 재실행한다. 초기 WSL GitHub CLI는 인증되지 않았으며, 후속 커밋·푸시·PR 요청에서 Windows GitHub CLI의 저장소 쓰기 권한을 확인했다. 병합·Actions 재실행은 수행하지 않았다.
- 원래 `fix/macos-backend-validation` 체크아웃의 서비스 소스는 변경하지 않았다.
