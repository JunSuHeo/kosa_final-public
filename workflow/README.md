# GitHub Issue 승인 기반 실행 워크플로

GitHub Issue에서 요구사항을 접수해 AI가 분석 계획을 댓글로 제시합니다. `ai-plan` 라벨은 수동 승인, `ai-auto` 라벨은 추가 질문이 없는 준비된 계획의 자동 실행 승인을 선택합니다. `ai-auto`만 있어도 시작하며 두 라벨이 함께 있으면 자동 승인을 적용합니다. 저장소 `Write` 이상의 권한이 있는 사람은 `/plan <결정사항 또는 수정사항>`으로 계획을 바꾸고, 준비된 계획은 별도의 `/approve` 댓글로 승인할 수 있습니다. `/reject`는 거부 상태를 기록하고 종료합니다. PR 검토와 병합은 사람이 수행합니다.

공개본에는 엔진과 로컬 데모를 제공합니다. GitHub Issue 연동은 별도 비공개 저장소에서 구성합니다. GitHub에서 실행하려면 먼저 [GitHub 저장소 설정 안내](specs/github_settings.md)를 따르세요. 상세 상태·복구와 보안 동작은 [Issue 승인 운영 안내](runtime/ISSUE_APPROVAL.md)에 정리되어 있습니다.

## GitHub Issue 작업

1. 신뢰하는 기본 브랜치에 `.github/workflows/issue-approval.yml`, 실행 모듈 및 대상 프로젝트 설정을 검토해 반영합니다.
2. Repository Variables와 Secrets, Actions 권한, macOS ARM64 self-hosted runner를 설정합니다. `pr_policy.require_branch_protection=true`인 프로젝트는 사람 리뷰를 요구하는 Branch protection도 설정합니다. PRJ는 이를 요구하지 않습니다. 세부 순서는 [GitHub 설정 안내](specs/github_settings.md)를 참고하세요.
3. `ai-plan` 또는 `ai-auto` 라벨이 있는 Issue를 등록하거나 해당 라벨을 추가하면 Actions가 제목과 본문을 읽고 계획을 작성합니다. 사용자 결정이 필요한 항목은 처음에 모아서 묻고, AI가 해당 질문에 맞는 `/plan` 답변 예시를 작성합니다. `received`와 `analyzing` 상태는 내부 기록에만 남습니다.
4. `awaiting_plan`에서는 `/plan <결정사항>`으로 답합니다. 생략하거나 AI에 맡긴 세부사항은 AI가 합리적인 기본값을 선택해 계획에 적습니다. 실행에 꼭 필요한 결정이 남아 있으면 다시 질문하고, 계획이 준비되면 `awaiting_approval`로 이동합니다. 이 상태에서도 `/plan <수정사항>`으로 계획을 바꿀 수 있습니다.
5. `ai-auto`가 있으면 준비된 계획을 자동 승인하고 실행합니다. 질문이 있으면 `/plan` 답변을 기다리며 해결된 계획도 자동 승인합니다. `ai-plan`만 있으면 `awaiting_approval`에서 새 댓글에 `/approve`만 작성하면 실행합니다. 앞뒤 공백과 줄바꿈은 허용합니다. 거부하려면 `/reject`만 작성합니다.
6. 승인된 Issue와 계획을 기존 실행 엔진에 전달해 코드를 생성하고, 프로젝트에 설정된 Unit/E2E 검증을 실행합니다. 게시 조건과 프로젝트의 테스트 실패 허용 정책에 따라 PR을 게시합니다. PRJ는 테스트 실패를 기록한 뒤 일반 PR을 생성합니다. 코드를 최종 검토하고 병합하는 역할은 사람에게 있습니다.

Issue 제목이나 본문이 바뀌면 기존 분석과 승인을 무효화합니다. 새 계획에는 현재 라벨에 따른 승인 방식을 다시 적용합니다. 자동 승인 후 `ai-auto`가 제거되면 이후 실행·게시 경계에서 차단합니다. 실행이 중단된 상태는 중복 실행을 피하기 위해 자동 재시도하지 않습니다. 복구 방법은 [Issue 승인 운영 안내](runtime/ISSUE_APPROVAL.md)를 확인하세요.

## GitHub 설정

Issue 이벤트를 처리하려면 비공개 저장소의 기본 브랜치에 `.github/workflows/issue-approval.yml` 진입점을 구성합니다. Actions job을 켜려면 아래 설정이 모두 필요합니다.

- Repository Variables: `WORKFLOW_ISSUES_ENABLED=true`, `WORKFLOW_BASE_BRANCH`, `WORKFLOW_CONFIG_PATH`
- Repository Secrets: `WORKFLOW_STATE_KEY`, `WORKFLOW_PUBLISH_TOKEN`
- `self-hosted`, `macOS`, `ARM64`, `workflow-isolated` labels를 가진 runner와 Codex CLI, gh, Git, Python 및 프로젝트 테스트 도구. PRJ 백엔드는 macOS runner에서 직접 실행합니다. 계산기 데모 등 일반 검사는 시스템 `sandbox-exec`가 필요하며 격리 점검 실패 시 실행을 차단합니다.
- workflow 기본 `GITHUB_TOKEN`에 `contents: read`, `issues: write`; 게시용 토큰에는 저장소 Push/PR 생성 권한. 보호 규칙을 요구하는 설정에서는 branch protection 조회 권한도 필요
- 실제 Collaborator 권한 API 조회와 프로젝트 정책에 따른 보호 Branch

Repository Variables와 Secrets는 [GitHub 저장소 설정 안내](specs/github_settings.md), self-hosted runner 설치와 Codex 인증은 [GitHub runner 설정 안내](specs/github_runner.md)를 참고하세요.

## 프로젝트 설정 예시

설정 파일의 `repository.owner`와 `repository.name`은 GitHub 연동 시 대상 저장소에 맞게 설정합니다. 프로젝트별 설정은 두 가지입니다. [prj.json](config/projects/prj.json)은 제품 `PRJ/`만 수정하도록 허용하고, [sandbox.json](config/projects/sandbox.json)은 `sandbox/` 아래 데모만 허용합니다. GitHub Issue 작업 대상은 Repository Variable `WORKFLOW_CONFIG_PATH`가 가리키는 설정으로 결정됩니다. PRJ PostgreSQL 백엔드는 필수 검사이며, 실패·시간 초과·실행 불가 결과를 이슈 댓글에 기록한 뒤 일반 PR을 생성하도록 `allow_pr_on_failure=true`, `publishing.draft=false`를 적용했습니다. `require_branch_protection=false`로 보호 규칙 없이도 게시합니다. [러너 준비 요건](specs/github_runner.md)을 확인하세요.

현재 Issue PR 브랜치 형식은 `feature/ai/{date}/{approver}/{issue_title}`입니다. 날짜는 실행 시작일의 한국 시간(`YY.MM.DD`), 승인자는 수동 승인자의 GitHub login 또는 자동 승인의 `ai-auto`, 제목은 브랜치에 안전한 문자로 정리한 Issue 제목입니다. 수동 CLI 실행에는 `ai/{project_id}/{run_id}`를 사용합니다. 동일 브랜치가 이미 있으면 기존 작업을 덮어쓰지 않고 게시를 중단합니다.

## 수동 실행

GitHub Issue 연동 없이 로컬에서 작업을 실행할 수 있습니다. Python 3.12 이상과 설정에 선언된 실행·테스트 도구를 준비하고 저장소 루트에서 명령을 실행합니다.

먼저 프로젝트 설정의 schema와 로컬 경로를 확인합니다.

```bash
python3 -B -m workflow.runtime.validate_config \
  workflow/config/projects/sandbox.json \
  --repo-root .
```

요청을 실행하고 Unit/E2E 검증까지 수행합니다. 게시 옵션 기본값은 `simulate`입니다.

```bash
python3 -B -m workflow.runtime.run \
  --config workflow/config/projects/sandbox.json \
  --repo-root . \
  --task "계산기 입력 검증을 개선해줘"
```

`simulate`는 네트워크 Push와 실제 PR 생성을 하지 않습니다. 결과 JSON에 기록된 `result_path`를 `publish` 명령에 주면 별도 결과 폴더 안에 게시 준비물을 생성해 검토할 수 있습니다.

```bash
python3 -B -m workflow.runtime.publish \
  --config workflow/config/projects/sandbox.json \
  --repo-root . \
  --result /private/ai-workflow-runs/<RUN_ID>/result.json
```

`publish` 기본 동작은 로컬 준비입니다. `run --publish-mode prepare`도 로컬 준비까지만 합니다. `run --publish-mode real` 또는 `publish --execute`를 선택하면 검증 근거, 원격 저장소 권한과 설정에 따른 Branch protection 확인 뒤 실제 Branch Push 및 PR 생성을 시도합니다. 준비가 되지 않았거나 실제 게시 권한이 불필요한 경우 이 옵션을 사용하지 마세요.

## 로컬 테스트

Workflow 런타임의 Mock 기반 테스트는 GitHub API, 실제 Push/PR 생성이나 Codex 호출 없이 실행합니다.

```bash
python3 -B -m unittest discover -s workflow/runtime/tests -p 'test_*.py'
```

## 주요 파일

| 경로 | 용도 |
| --- | --- |
| `.github/workflows/issue-approval.yml` | GitHub Issue 및 승인 댓글 이벤트 |
| `workflow/runtime/issue_workflow.py` | 분석, 상태 복구, 권한 확인, 사람 승인 처리 |
| `workflow/runtime/orchestrator.py` | 기존 실행·검증 엔진과 게시 엔진 연결 |
| `workflow/runtime/publish.py` | 검증 결과를 확인하고 브랜치/PR 준비·게시 |
| `workflow/config/projects/prj.json` | 제품 `PRJ/` 프로젝트 설정 |
| `workflow/config/projects/sandbox.json` | `sandbox/` 데모 프로젝트 설정 |
| `workflow/specs/github_settings.md` | GitHub Variables, Secrets, runner 및 보호 규칙 설정 |
| `workflow/runtime/ISSUE_APPROVAL.md` | 상태 관리, 복구, 운영 한계와 검증 근거 |
| `workflow/runtime/PUBLISHING.md` | 로컬 준비, Branch·PR 규칙과 게시 조건 |
