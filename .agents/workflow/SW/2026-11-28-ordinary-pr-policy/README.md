# 보호 규칙 없는 저장소와 테스트 실패의 일반 PR 허용

- 날짜: 2026-11-28 (Asia/Seoul)
- 상태: 완료
- 담당 팀원: SW (`.agent-local.md` 설정)
- 참여 AI 에이전트·담당 범위: Codex, PR 게시 정책과 검증; `review_pr_policy`, 읽기 전용 최종 리뷰 ([기록](agents/review.md))
- 공동 작업의 대표 기록·관련 팀원 기록: 해당 없음
- 요청·목표: GitHub 브랜치 보호 규칙이 없고 테스트가 실패해도 일반 PR을 생성한다. 검토 요청 후 사용자가 구현을 승인했다.
- 완료 조건: PRJ에서 보호 규칙 없이 일반 PR 생성 가능. 실패 상태와 근거를 보존한다. 기존 설정의 기본 동작과 실행 승인·권한·코드 범위·검증 근거 확인을 유지한다.
- 변경 범위: `workflow/runtime/`, schema, PRJ 설정, 관련 테스트와 운영 안내
- 작업 공간: `/tmp/kosa-pr-policy-20261128`, `fix/ordinary-pr-policy`, 시작 커밋 `dff9e19`

## 읽은 근거

- 루트 `AGENTS.md`, `.agent-local.md`, `PRJ/AGENTS.md`, `PRJ/rules/project.md`, `backend.md`, `infra.md`
- `workflow/README.md`, `runtime/README.md`, `PUBLISHING.md`, `ISSUE_APPROVAL.md`, `specs/github_settings.md`
- `github_adapter.py`, `publish.py`, `test_runner.py`, `run.py`, `orchestrator.py`, `issue_workflow.py`, 관련 테스트
- [이전 Draft PR 작업](../2026-11-24-test-failure-draft-pr/README.md)

## 계획

1. 정책과 호환 범위 확정, 기준 테스트 → [구현 계획](plan.md)
2. 보호 규칙 선택 설정과 실패 후 일반 PR 구현 → 실패하는 회귀 테스트를 먼저 확인
3. PRJ 설정·문서 갱신 → 런타임 전체 mock 테스트와 diff 확인

## 판단·진행 요약

- GitHub 어댑터가 classic branch protection과 사람 리뷰·관리자 적용·우회 금지를 강제한다.
- 게시 모듈은 실패한 검증에 Draft를 강제하며 PRJ의 `publishing.draft`도 true다.
- 선택과 이유: optional `require_branch_protection`(기본 true), `allow_pr_on_failure`(기본 false)를 추가한다. PRJ에서는 각각 false/true와 `publishing.draft=false`를 적용한다. 기존 설정은 변경하지 않아도 이전 정책을 따른다.
- 브랜치 보호 확인을 끄더라도 저장소 identity, push 권한, 기준 SHA를 확인한다. 보호 규칙을 요구하는 설정에서 API 오류를 무시하지 않는다.
- 테스트 실패·시간 초과·실행 불가만 예외로 허용한다. 검증 근거 누락·손상, 입력 변경, 범위 위반, Codex 실패는 계속 차단한다.
- 보호 규칙을 요구하지 않으면 GitHub가 리뷰와 통과한 검사를 병합 전에 강제하지 않는다. 워크플로의 `/approve`는 구현 실행 승인이다.
- 기록과 계획은 프로젝트 지침에 따라 `.agents/workflow/SW/`에 유지한다. 별도 작업 공간은 원본 파일을 건드리지 않도록 저장소 밖에 만들었다.
- 구현 중 schema 검증기가 `default` 키워드를 지원하지 않는 것을 확인했다. 검증기 확장 없이 설명과 런타임의 `.get()` 기본값으로 처리했다.
- 기존 승인 무효화 테스트의 원격 검사 wrapper가 새 keyword 인수를 전달하도록 수정했다. 보호 검사 중 Issue 변경 시 게시가 중단되는 기존 동작을 검증한다.

## 변경 파일

- `workflow/runtime/{github_adapter,simulated_github}.py`: 선택 가능한 보호 규칙 확인. 저장소·권한·기준 SHA 확인 유지.
- `workflow/schemas/project.schema.json`: optional boolean 정책 두 개와 기본값 설명.
- `workflow/runtime/{test_runner,run,publish,orchestrator,issue_workflow}.py`: 실패 게시 허용, 실제 Draft 선택, 실패 댓글·완료 링크, 결과 보존.
- `workflow/config/projects/prj.json`: 일반 PR·실패 허용·보호 규칙 조회 생략.
- `workflow/runtime/tests/test_{validate_config,publish,orchestrator,issue_workflow}.py`: 정책 검증·기존 기본값·실패 근거·댓글 순서·원격 확인의 회귀 테스트.
- 관련 `workflow/` 안내, `PRJ/README.md`, `PRJ/rules/infra.md`: 새 정책·기본값·실패 표시·병합 전제.
- 이번 작업 README·계획 및 `SW/README.md`: 요청·판단·검증·인계 기록.

## 검증

| 실행 위치 | 명령·확인 방법 | 결과 | 근거·한계 |
| --- | --- | --- | --- |
| 격리 작업 공간, 구현 전 | `python3 -B -m unittest discover -s workflow/runtime/tests -p 'test_*.py' -q` | 통과 | 262개. 외부 GitHub·Codex·제품 DB를 사용하지 않는 런타임 테스트 |
| 격리 작업 공간, 새 테스트·구현 전 | `python3 -B -m unittest workflow.runtime.tests.test_validate_config workflow.runtime.tests.test_publish workflow.runtime.tests.test_orchestrator workflow.runtime.tests.test_issue_workflow -q` | 예상 실패 | 167개, failures=12/errors=5. 새 설정 거부와 미지원 보호 검사 인수 확인 |
| 격리 작업 공간, 최종 구현 | `python3 -B -m unittest discover -s workflow/runtime/tests -p 'test_*.py' -q` | 통과 | 272개, 11.452초. PRJ처럼 두 실패 정책을 모두 켠 경우 일반 PR 우선도 확인 |
| 격리 작업 공간 | `python3 -B -m workflow.runtime.validate_config workflow/config/projects/prj.json --repo-root .` | 통과 | 오프라인 schema·경로 검증. 원격 인증·CLI 명령 실행 검증은 아님 |
| 격리 작업 공간 | `git diff --check` | 통과 | 공백 오류 없음 |
| 격리 작업 공간 | 새 문서 링크 대상과 별도 최종 코드 리뷰 | 통과 | 링크 대상 존재. Critical / Important / Minor 지적 없음 ([리뷰](agents/review.md)) |
| 원본 작업 공간 | patch 적용 후 25개 변경 파일 SHA-256 비교·`git diff --check` | 통과 | 검증한 worktree와 동일한 변경만 반영. 제품 코드와 새 정책은 추가 수정 없음 |
| GitHub·실제 runner | 워크플로 자체의 Push·일반 PR 생성·macOS 검사 | 미실행 | 코드 구현 요청 범위. 이 기록은 live 성공을 주장하지 않음 |

## 결과·인계

- 완료 내용: 보호 규칙 선택 검사, 실패 후 일반 PR 정책, PRJ 설정, 실패 댓글·결과 보존, 운영 안내를 구현했다. 272개 런타임 mock 테스트·설정 검사·별도 리뷰를 완료하고 현재 작업 폴더에 변경을 반영했다.
- 미확인·남은 작업: 실제 GitHub 설정 변경·워크플로를 통한 Push·PR 생성과 macOS runner live 검증은 미실행이다. GitHub Actions에 적용하려면 이 변경을 `WORKFLOW_BASE_BRANCH`가 가리키는 신뢰 브랜치에 반영해야 한다.
- 인계: 새 설정을 생략하는 프로젝트는 기존 동작을 유지한다. PRJ는 보호 규칙 없어도 일반 PR을 만들며 테스트 실패를 성공으로 표시하지 않는다. 자동 병합은 금지다.
- 다른 에이전트 기록·정제한 로그 링크: [최종 리뷰](agents/review.md). 원시 대화와 비밀값은 저장하지 않았다.

## 후속 요청: 커밋·푸시

- 사용자가 구현 완료 후 현재 변경의 커밋과 푸시를 명시적으로 요청했다.
- 대상: 현재 `fix/test-failure-draft-pr`와 추적 브랜치 `origin/fix/test-failure-draft-pr`.
- 원격 확인: 커밋 전 원격 HEAD는 로컬 기준과 동일한 `dff9e19`였다.
- 커밋 직전 검증: 원본 작업 폴더에서 전체 런타임 mock 테스트 272개 통과(11.695초), PRJ 오프라인 설정 검증 통과.
- 이번 구현·테스트·문서·작업 기록만 명시적으로 stage하고 일반 Push를 수행한다. 커밋 SHA와 원격 반영 확인 결과는 대화 완료 보고에 남긴다.
