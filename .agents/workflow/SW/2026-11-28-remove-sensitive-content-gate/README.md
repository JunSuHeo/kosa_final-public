# Workflow 소스 민감정보 차단 제거

- 날짜: 2026-11-28 (Asia/Seoul)
- 상태: 완료 (수정·오프라인 검증 및 PR #23 게시)
- 담당 팀원: SW (`.agent-local.md` 기준)
- 참여 AI 에이전트·담당 범위: Codex, 원인 조사·런타임 수정·회귀 검증
- 공동 작업의 대표 기록·관련 팀원 기록: 해당 없음
- 요청·목표: 반복되는 `analysis_failed / sensitive_content` 오탐을 막기 위해 소스·컨텍스트 내용의 자동 차단을 제거한다.
- 완료 조건: 예외 목록에 없는 인증 코드·fixture가 분석 및 생성·검증을 통과하고, 경로 보호와 출력 마스킹 회귀 검사가 통과한다.
- 변경 범위: `workflow/runtime/workspace.py`, 관련 테스트·운영 안내·아키텍처. 기존 사용자 스킬 스크립트 변경은 작업 범위 밖이다.

## 읽은 근거

- 루트 AGENTS.md, `.agent-local.md`, `.agents/workflow/README.md`, PRJ/AGENTS.md, PRJ/rules/project.md.
- workflow/README.md, workflow/runtime/README.md, workflow/runtime/ISSUE_APPROVAL.md.
- workflow/specs/architecture.md, workflow/specs/requirements.md.
- workspace.py, issue_workflow.py, run.py, test_runner.py 및 test_run.py, test_issue_workflow.py.
- [이전 오탐 수정](../2026-11-23-sensitive-content-analysis/README.md), 커밋 `d79e3eb`, `e177912`.

## 설계·계획

요청의 오류 원인은 모델 응답이 아니라 격리 snapshot을 만드는 `workspace.inventory()`의 로컬 정규식 검사다. 소스·컨텍스트·파일명 검사를 제거하고, 이 검사만 사용하는 경로별 예외 목록과 표현식 판별 함수도 제거한다. 로그·프롬프트의 `redact()`와 경로·링크·크기·snapshot 무변경 검증은 유지한다. Issue 입력·계획의 별도 검증과 게시 메타데이터 검증은 이번 소스 스캔 제거 범위에 포함하지 않는다.

1. 기존 차단 테스트를 새 동작의 회귀 테스트로 바꾸고, 컨텍스트·파일명·임의 경로 fixture 사례를 추가한다. 수정 전 실패를 확인한다.
2. `read_context()`와 `inventory()`에서 내용 기반 차단을 제거하고, 사용자가 읽는 운영 문서를 갱신한다.
3. 새 회귀 검사와 workflow 오프라인 테스트를 실행한다. 변경 diff와 경로·출력 마스킹 검사를 확인하고 실제 실행 결과를 기록한다.

## 판단·진행 요약

- 확인한 사실: 이전 수정은 검토한 PRJ 코드·fixture 문자열을 파일별 목록에 추가했다. 새로운 문자열과 코드 형태는 여전히 차단된다.
- 선택과 이유: 사용자가 검사 제거를 요청했다. 제품 코드가 바뀔 때마다 자동화 예외 목록을 갱신하는 구조를 제거한다.
- 실패·대안·범위 변경: bounded search 도구는 `QUERY_AMBIGUOUS`로 종료되어 일반 범위 제한 rg로 소스를 확인했다. Windows Git의 ownership 경고는 해당 명령의 `safe.directory` 옵션으로만 처리했으며 전역 설정은 바꾸지 않았다.
- 조사 인계: 사용자 로그의 `sensitive_content`는 로컬 workspace의 내용·파일명 검사에서 발생하는 오류다. 실제 해당 Actions 입력과 실행 커밋은 이 작업에서 조회하지 않았으며, 새 fixture로 같은 실패 경로를 재현했다.
- 구현 인계: workspace의 내용 판별 함수·파일별 허용 목록·TS 예외 정규식과 문서·파일명 차단을 제거했다. 출력 마스킹 함수는 계속 사용한다. 과거 결과의 오류 해석을 위한 호출자의 `sensitive_content` 분기는 호환성 목적으로 유지한다.
- 검증 인계: 신규 4개 테스트는 수정 전에 실패했고 수정 후 통과했다. 전체 workflow 오프라인 테스트 269개가 통과했으며, 실제 PRJ snapshot 분석 준비도 이 실행에 포함된다.

## 변경 파일

- `workflow/runtime/workspace.py`: 소스·컨텍스트·파일명 내용 검사와 전용 예외 목록 제거.
- `workflow/runtime/run.py`: 파일명에 포함된 값을 CLI 결과 표시에서 마스킹하며 개인 검증 근거는 그대로 유지.
- `workflow/runtime/tests/test_run.py`: 생성된 password fixture의 수집·검증, 임의 경로의 코드·fixture·파일명 hash 추적, 컨텍스트 허용 및 상속 값 마스킹 검증. 삭제된 예외 판별 함수의 전용 테스트를 새 계약에 맞게 대체.
- `workflow/runtime/tests/test_issue_workflow.py`: 새로운 password fixture가 계획 분석을 통과하고 상속 값은 프롬프트에서 가려지는지 검증.
- `workflow/runtime/README.md`, `workflow/runtime/ISSUE_APPROVAL.md`: 제거 범위·남은 검증·과거 실패의 재분석 방법 갱신.
- `workflow/specs/architecture.md`: 패치 수집 단계에서 정규식 내용 추정으로 차단하지 않는 계약 반영.
- `.agents/workflow/SW/README.md`, 이 README: 작업 목록·근거·검증·인계 기록.
- [agents/review.md](agents/review.md): 별도 에이전트의 검토 결과와 반영·회귀 검증 기록.

## 검증

| 실행 위치 | 명령·확인 방법 | 결과 | 근거·한계 |
| --- | --- | --- | --- |
| 저장소 루트 (WSL Python 3.14.4) | `python3 -B -m unittest workflow.runtime.tests.test_run.EngineTests.test_generated_password_fixture_is_collected_and_validated workflow.runtime.tests.test_run.EngineTests.test_inventory_accepts_authentication_code_and_fixtures_in_any_file workflow.runtime.tests.test_run.EngineTests.test_context_with_password_fixture_allows_execution_and_masks_inherited_value workflow.runtime.tests.test_issue_workflow.BoundaryTests.test_analysis_accepts_new_password_fixture_and_masks_inherited_value` | 수정 전 실패, 수정 후 통과 | 수정 전 4개 실행에서 2 failures·4 subtest/errors. 모두 기존 내용·파일명 차단 경로. 수정 후 4개 OK, 종료 코드 0, 0.041초 |
| 저장소 루트 (WSL Python 3.14.4) | `python3 -B -m unittest discover -s workflow/runtime/tests -p 'test_*.py'` | 통과 | 269개 OK, 종료 코드 0, 10.607초. Mock 어댑터·임시 파일·로컬 Git 사용. 실제 모델·GitHub API·제품 테스트·서비스 DB 호출 없음 |
| 저장소 루트 | `git diff --check`, 작업 범위 diff 검토 | 통과 | 경로·링크·크기·hash 검증과 redact 호출 유지 확인. 기존 사용자 스킬 스크립트 변경은 수정하지 않음 |
| 최신 main 기반 worktree (WSL) | `python3 -B -m unittest discover -s workflow/runtime/tests -p 'test_*.py'` | 통과 | 기준 `748af81`, 269개 OK, 종료 코드 0, 12.016초. 기존 checkout의 PRJ 소스를 바꾸지 않고 재검증 |
| 최신 main 기반 worktree (WSL) | `python3 -B -m unittest workflow.runtime.tests.test_run.EngineTests.test_cli_masks_inherited_value_in_filename_and_preserves_private_evidence` | 수정 전 실패, 수정 후 통과 | CLI에 파일명이 표시되는 회귀 1개. 수정 전 1 failure·종료 코드 1. 수정 후 OK·종료 코드 0, 0.059초 |
| 최신 main 기반 worktree (WSL) | `python3 -B -m unittest discover -s workflow/runtime/tests -p 'test_*.py'` | 최종 통과 | 검토 반영 후 270개 OK, 종료 코드 0, 11.334초 |

## 결과·인계

- 완료 내용: 소스·컨텍스트·파일명 스캔 차단 제거, 문서 갱신, 회귀 및 전체 오프라인 검증 완료.
- 미확인·남은 작업: 병합과 원격 macOS Actions 재실행은 수행하지 않았다. PR을 기준 브랜치에 반영한 뒤 실패한 Issue의 opened/edited 이벤트를 재실행해야 한다. 재분석 후 별도 `/approve`를 기다리는 기존 승인 절차는 적용된다.
- 다른 에이전트 기록·정제한 로그 링크: [PR 검토](agents/review.md).

## PR 준비 (후속 요청)

- 사용자가 PR 생성을 요청했다. 대상은 `JunSuHeo/kosa_final-public`의 `main`이다.
- 원격 main은 `748af81`이며 원래 checkout보다 4개 커밋 앞서 있다. 제품 변경을 원래 checkout에 반영하지 않기 위해 `/tmp/kosa-remove-sensitive-gate-20261128`에 `fix/remove-sensitive-content-gate` worktree를 만들고 이번 8개 파일만 복사했다.
- 참여 AI 에이전트 추가: Codex 검토 에이전트 `review_sensitive_gate_pr`, 읽기 전용 diff·계약·회귀 검토. 구현과 테스트 실행은 기존 Codex가 담당한다.
- 별도 검토에서 발견한 CLI 파일명 출력 마스킹과 아키텍처 문서 불일치를 반영했다. 처음 복사한 8개 파일에 `run.py`와 검토 기록을 추가했다.
- 최신 main 기반 최종 오프라인 검증 270개와 diff 검사가 통과했다. 커밋·Push·PR 생성을 진행한다.

## PR 게시·인계

- 사용자 후속 요청에 따라 구현 커밋 `073b28b`를 `fix/remove-sensitive-content-gate` 브랜치로 Push하고 [PR #23](https://github.com/JunSuHeo/kosa_final-public/pull/23)을 `main` 대상으로 생성했다.
- 대상 저장소는 `JunSuHeo/kosa_final-public`이며 일반 PR이다. 실제 서비스·DB·모델 호출이나 실패한 Issue Actions 재실행은 수행하지 않았다.
- PR 피드백 작업 공간은 `/tmp/kosa-remove-sensitive-gate-20261128`에 유지한다. 원래 checkout의 기존 브랜치와 사용자 스킬 스크립트 변경은 그대로 보존했다.
