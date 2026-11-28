# 일반 PR 게시 정책 구현 계획

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 보호 규칙 없이 테스트 실패에도 PRJ의 일반 PR을 생성하고 검증 실패를 보존한다.

**Architecture:** 기존 게시·검증 경로에 optional 정책 두 개를 추가한다. 기존 `allow_draft_on_failure`는 Draft 전용 예외로 유지하고 `allow_pr_on_failure`만 일반 PR을 허용한다. 원격 보호 검사만 선택 가능하며 identity·권한·SHA와 봉인된 검증 근거는 항상 확인한다.

**Tech Stack:** Python 표준 라이브러리, unittest, JSON schema, GitHub CLI

**Spec:** [요청·완료 조건과 판단](README.md)

## 공통 조건

- `require_branch_protection` 기본 true, `allow_pr_on_failure` 기본 false. PRJ에서 false/true로 설정하고 `publishing.draft=false`로 한다.
- `require_human_approval=true`, `allow_auto_merge=false` 유지.
- 실패·시간 초과·실행 불가만 게시 예외이며 결과를 passed로 덮어쓰지 않는다.
- 기존 `draft_on_test_failure` 보고 필드는 실제 Draft 예외 여부로 유지하고, 일반 게시 예외는 `publish_on_test_failure`로 표현한다.
- 제품 DB·운영 서비스·GitHub 설정과 원격 브랜치를 변경하지 않는다.

## 검토 초점

- 새 정책 생략 시 기존 보호 검사와 Draft 강제 유지.
- 보호 검사 비활성 상태에서도 identity·push 권한·기준 SHA 오류는 차단.
- 일반 PR 정책에서도 누락·위조된 테스트 근거, 입력 변경과 정당하지 않은 미실행은 차단.
- 실패 댓글은 실제 PR 유형을 안내하며 게시보다 먼저 기록.
- Draft 설정이 명시적으로 true이면 일반 PR 예외가 있어도 Draft로 게시.

### Task 1: 선택 가능한 보호 검사와 실패 게시 정책

**Files:** `workflow/schemas/project.schema.json`, `runtime/github_adapter.py`, `simulated_github.py`, `test_runner.py`, `run.py`, `publish.py`, `orchestrator.py`, `issue_workflow.py`, `runtime/tests/test_{validate_config,publish,orchestrator,issue_workflow}.py`

**Interfaces:** `GitHubCLI.check_repository(..., *, require_branch_protection=True)`; `test_runner.allow_failure_publication(config, validation)`; `publish_on_test_failure` 보고 필드.

- [x] 선택 정책 schema 검증, 보호 없는 저장소, 실패 후 일반 PR·실패 근거 보존, 댓글 순서의 회귀 테스트 작성.
- [x] `python3 -B -m unittest workflow.runtime.tests.test_validate_config workflow.runtime.tests.test_publish workflow.runtime.tests.test_orchestrator workflow.runtime.tests.test_issue_workflow -q` 실행. Expected: 새 동작의 테스트가 실패.
- [x] 최소 구현. 기존 Draft 정책의 기본값과 검증 판정 유지.
- [x] 전체 런타임 mock 테스트 실행. Expected: 전체 통과. 결과: 272개 통과.

### Task 2: PRJ 설정·운영 안내·완료 검증

**Files:** `workflow/config/projects/prj.json`, `workflow/README.md`, `runtime/{README,PUBLISHING,ISSUE_APPROVAL}.md`, `specs/github_settings.md`, `PRJ/README.md`, `PRJ/rules/infra.md`, 작업 기록.

- [x] PRJ에서 두 정책과 일반 PR 설정 활성화. 관련 문서의 보호/Draft 전제 갱신.
- [x] 설정 검증과 `python3 -B -m unittest discover -s workflow/runtime/tests -p 'test_*.py' -q` 실행. Expected: 설정 유효, 전체 통과.
- [x] diff·문서 링크·영향 범위 리뷰. Expected: 요청과 무관한 변경 없음.
- [x] 검증·인계 기록을 갱신하고 원본 작업 공간에 이번 변경만 반영.

## 진행 기록

- 계획 확정. 원격 게시 없이 구현 결과와 검증 근거를 제공한다.
- Task 1: 구현 완료. 기준 262개 통과, 회귀 테스트 RED 확인 후 전체 272개 GREEN.
- Task 1: schema의 default annotation은 지원되지 않아 description과 런타임 기본값으로 구현했다. 공통 검증기 변경을 피했다.
- Task 2: 설정·문서·전체 272개 테스트·별도 리뷰 완료. 25개 변경 파일의 SHA-256 일치와 diff 확인 후 원본 작업 공간에 반영했다.
- Final review: `review_pr_policy`, Critical / Important / Minor 지적 없음. 리뷰 범위와 기존 운영 경계는 [기록](agents/review.md)에 남겼다.
