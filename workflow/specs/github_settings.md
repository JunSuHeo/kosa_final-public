# GitHub Actions 및 저장소 설정

이 문서는 `.github/workflows/issue-approval.yml`을 해당 GitHub 저장소에서 작동시키기 위한 운영 설정을 설명합니다. 현재 workflow와 실행 코드는 저장소 로컬에 있습니다. Issue 이벤트를 받는 기본 브랜치에 workflow가 검토·반영되기 전에는 GitHub Actions가 이를 실행하지 않습니다.

## 먼저 대상 프로젝트를 확인하세요

프로젝트 설정은 두 가지입니다. [PRJ 설정](../config/projects/prj.json)은 `project_root`와 `allowed_paths`를 `PRJ/`로 제한하고, [sandbox 설정](../config/projects/sandbox.json)은 `sandbox/`로 제한합니다. GitHub Issue 작업은 Repository Variable `WORKFLOW_CONFIG_PATH`에 지정한 설정 하나만 사용합니다. PRJ 설정은 PostgreSQL 백엔드 테스트를 필수로 요구하므로, 격리 runner에서 PostgreSQL 서비스를 제공하지 못하면 테스트가 실패해 게시가 차단됩니다. 실행 대상과 테스트 인프라를 확인한 뒤 적절한 설정 파일을 선택하세요.

## 1. Workflow 반영과 Actions 정책

1. `.github/workflows/issue-approval.yml`, `workflow/runtime/`, Schema와 연결할 프로젝트 설정을 함께 검토합니다.
2. 신뢰하는 기본 브랜치에 workflow와 실행 코드가 들어가도록 반영합니다. 이벤트가 발생할 때 checkout될 `WORKFLOW_BASE_BRANCH`에도 같은 코드와 설정이 존재해야 합니다.
3. Repository의 **Settings → Actions → General**에서 GitHub Actions 사용이 허용되는지 확인합니다. 조직 정책이 Repository 설정보다 우선할 수 있습니다.
4. 다른 설정을 먼저 준비하고 사전 점검한 뒤 `WORKFLOW_ISSUES_ENABLED`를 활성화합니다.

Workflow가 다루는 이벤트는 `issues.opened`, `issues.edited`, `issue_comment.created`입니다. Issue 댓글에는 단독 `/approve`, 단독 `/reject` 또는 `/plan <결정사항>` 명령을 사용할 수 있습니다. Pull Request 대화는 제외합니다. concurrency group은 Repository와 Issue 번호 단위로 실행을 직렬화합니다.

## 2. Repository Variables

**Settings → Secrets and variables → Actions → Variables**에서 다음 Repository Variables를 설정합니다.

| 변수 | 예시 | 설명 |
| --- | --- | --- |
| `WORKFLOW_ISSUES_ENABLED` | `true` | workflow job 활성화 스위치입니다. 정확히 소문자 `true`여야 합니다. 다른 값이나 미설정은 job을 실행하지 않습니다. |
| `WORKFLOW_BASE_BRANCH` | `main` | workflow가 실행 코드와 설정을 checkout하는 신뢰 브랜치입니다. 프로젝트 설정의 `base_branch` 및 `pr_policy.target_branch`와 일치해야 합니다. |
| `WORKFLOW_CONFIG_PATH` | PRJ: `workflow/config/projects/prj.json`<br>sandbox: `workflow/config/projects/sandbox.json` | checkout 저장소 루트 기준 JSON 설정 경로입니다. 선택한 설정의 `project_root`, 허용 경로와 테스트를 확인하세요. |

Issue 이벤트를 받는 기본 브랜치에도 workflow 파일이 있어야 합니다. 게시 엔진은 검증 당시의 Git 기준 SHA, 현재 source HEAD, 원격 기본 브랜치가 일치하는지도 확인합니다. 기준이 다르면 게시하지 않습니다.

## 3. Repository Secrets 및 Token 권한

**Settings → Secrets and variables → Actions → Secrets**에 설정합니다. Secret 값은 JSON 설정, Issue, PR 본문 또는 터미널 기록에 넣지 않습니다.

| Secret | 용도 | 설정 |
| --- | --- | --- |
| `WORKFLOW_STATE_KEY` | Issue에 저장하는 workflow 상태 댓글의 HMAC 서명 | 암호학적으로 안전한 32바이트 이상의 무작위 값. 분석과 실행 단계에서 같은 값을 사용합니다. 키가 바뀌면 기존 상태 서명이 검증되지 않으므로 상태 복구를 수동으로 점검해야 합니다. |
| `WORKFLOW_PUBLISH_TOKEN` | 승인·검증 이후 Branch Push와 PR 게시 | 이 저장소 하나만 대상으로 제한한 fine-grained PAT 또는 동등한 GitHub App 자격 증명. 관리자 승인과 조직 정책에 맞춰 필요한 최소 권한만 부여합니다. |

Workflow에 선언한 기본 `GITHUB_TOKEN` 권한은 `contents: read`, `issues: write`입니다. Issue 조회, 계획/상태 댓글, 승인 댓글 조회에 사용합니다. 게시용 Secret은 승인된 실행 단계에만 전달됩니다.

게시 엔진은 원격 저장소 identity, Collaborator 권한, Branch protection을 조회하고 검증 결과를 새 Branch에 Push한 뒤 PR을 만듭니다. 토큰 종류와 조직 설정마다 API 접근 가능 범위가 다르므로 아래 권한을 최소 후보로 검토하고, 실제 API 확인을 수행해야 합니다.

- **Contents: Read and write** — 새 게시 브랜치 생성 및 Push
- **Pull requests: Read and write** — 기존 PR 조회 및 새 PR 생성
- **Administration: Read** — classic Branch protection 설정 조회
- **Metadata: Read-only** — Repository 식별. 일반적으로 자동 부여되는 기본 읽기 권한
- **Collaborator/멤버 권한 조회** — 승인자의 저장소 `admin`, `maintain`, `write` 권한을 확인하는 API 접근

실제 API가 요청한 Collaborator 권한 또는 보호 규칙을 확인할 수 없으면 fail closed로 멈춥니다. `Administration: Write`, auto-merge 권한이나 Branch protection 우회 권한은 부여하지 않습니다. 사용 중인 PAT/App이 이 저장소의 Branch protection 응답 형식을 지원하는지 관리자 계정으로 먼저 확인하세요.

## 4. 전용 Linux self-hosted runner

Runner 생성·라벨·Codex 로그인·호스트 도구 설정의 자세한 절차는 [GitHub runner 설정 안내](github_runner.md)를 참고하세요.

Workflow의 runner labels는 다음과 같습니다.

```text
self-hosted, linux, workflow-isolated
```

실행 환경에는 다음 도구와 접근이 필요합니다.

- Linux, Python 3.12 이상, Git, GitHub CLI `gh`
- 프로젝트 설정 `execution.codex.version`과 일치하는 Codex CLI, 기존 Codex 로그인과 설정 모델 사용 권한
- test 설정에서 선언한 명령·패키지·서비스 및 test runner 격리에 필요한 Bubblewrap
- 실행 결과를 임시 보관할 수 있는 runner 디스크 공간

Issue 본문은 외부 사용자가 제출하는 입력이므로 개인 개발 PC나 중요 자격 증명이 있는 상시 runner를 등록하지 마세요. 일회성 ephemeral VM/container와 최소 권한 계정을 사용하고 작업 후 폐기합니다. Codex 로그인 정보 외 GitHub 개인 인증, 다른 프로젝트 파일, 클라우드 자격 증명을 남기지 마세요. 이 workflow는 `gh`와 Codex CLI의 실제 설치·인증·모델 접근을 대신 설치하거나 준비하지 않습니다.

## 5. 보호 브랜치 및 사람의 최종 리뷰

프로젝트의 기준 및 PR 대상 Branch(두 설정 모두 `main`)에 사람 승인 리뷰어 최소 1명을 요구하고 관리자에게도 규칙이 적용되도록 설정합니다. review bypass가 있거나 병합 전에 사람이 검토하지 않아도 되는 설정은 게시 엔진의 요구와 맞지 않습니다. `WORKFLOW_PUBLISH_TOKEN`으로 protection을 조회할 수 있는지도 확인합니다.

현재 게시 설정은 `draft: true`여서 PR을 Draft로 만듭니다. Workflow는 자동 merge하지 않습니다. 사람은 Draft를 검토하고 필요할 때 일반 PR로 전환한 뒤 직접 병합합니다.

Issue Branch template은 다음 설정을 사용합니다.

```json
"branch_template": "ai_feature/{date}/{approver}/{issue_title}",
"manual_branch_template": "ai/{project_id}/{run_id}"
```

`date`는 실행 시작일의 한국 시간 `YY.MM.DD`, `approver`는 승인자의 GitHub login, `issue_title`은 브랜치에 안전하도록 정리한 Issue 제목입니다. 수동 CLI는 `manual_branch_template`을 사용합니다. 같은 Issue 규칙 이름의 Branch/PR이 있으면 덮어쓰지 않고 중단합니다.

## 6. 최초 활성화 전 검사

Runner에서 checkout한 저장소 루트에서 선택한 프로젝트 설정을 검사합니다.

```bash
python3 -B -m workflow.runtime.validate_config \
  workflow/config/projects/prj.json \
  --repo-root .
```

`sandbox/`를 대상으로 할 때는 위 명령의 파일을 `workflow/config/projects/sandbox.json`으로 바꿉니다. GitHub Actions의 `WORKFLOW_CONFIG_PATH`에도 같은 경로를 입력해야 합니다. Validator는 JSON Schema와 로컬 경로를 검사하지만 GitHub credential, Actions 실행 가능 여부, Codex 로그인, Git remote나 서버 Branch protection은 확인하지 않습니다.

다음 항목을 관리자가 확인한 뒤 `WORKFLOW_ISSUES_ENABLED=true`로 켭니다.

- [ ] workflow와 runtime이 신뢰하는 기본 브랜치에 반영됨
- [ ] workflow default branch, `WORKFLOW_BASE_BRANCH`, 프로젝트 base/target branch가 일치함
- [ ] `WORKFLOW_CONFIG_PATH`가 작업 대상에 맞는 PRJ 또는 sandbox 설정을 가리킴
- [ ] 프로젝트 경로·쓰기 허용 범위·설계 문서·테스트가 의도한 제품만 대상으로 함
- [ ] `WORKFLOW_STATE_KEY`, 제한된 `WORKFLOW_PUBLISH_TOKEN` 등록
- [ ] 기본 `GITHUB_TOKEN` 권한이 workflow에 선언한 값으로 제한됨
- [ ] 승인 사용자 Collaborator API, 보호 Branch 조회와 PR 권한을 실제 token으로 확인함
- [ ] runner labels, CLI 로그인, 모델/version, Git/gh, Bubblewrap과 제품 테스트를 확인함
- [ ] 실행 결과가 임시 runner에서 사라질 경우 복구 담당자와 보존 정책을 결정함
- [ ] 설정 적용을 검토한 뒤 `WORKFLOW_ISSUES_ENABLED` 활성화

이 문서를 작성하거나 읽는 작업은 GitHub 저장소를 변경하거나 Actions를 활성화하지 않습니다. 저장소 반영과 Secrets 변경은 권한 있는 운영자가 검토 후 수행해야 합니다.

## 7. 운영 중 확인 및 복구

Issue 등록 후 계획 댓글과 `AI 작업 상태`를 확인합니다. `awaiting_plan`이면 계획 댓글의 예시를 참고해 `/plan <결정사항>`으로 답합니다. `awaiting_approval`에서도 `/plan <수정사항>`으로 계획을 다시 작성하도록 요청할 수 있습니다. 코드 생성을 시작하려면 `awaiting_approval`에서 새 댓글에 `/approve`만 작성합니다. 앞뒤 공백과 줄바꿈은 허용합니다. 두 명령의 작성자는 실제 저장소 쓰기 권한을 가져야 합니다. Issue 제목·본문이나 계획이 수정되면 다시 분석과 승인이 필요합니다.

Job이 실행되지 않으면 GitHub Actions 화면의 event run, 기본 브랜치의 workflow, 활성화 변수, Repository/Organization Actions 정책 및 runner labels를 확인합니다. Job은 시작했지만 중단된 경우 서명된 Issue 상태 댓글과 runner 결과, 원격 Branch/PR을 대조하고 자동 중복 실행하지 않습니다. 상세 상태와 복구 한계는 [Issue 실행 운영 안내](../runtime/ISSUE_APPROVAL.md)를 참고합니다.
