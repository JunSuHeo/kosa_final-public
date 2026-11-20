# GitHub Issue 승인 실행: 구현 및 운영 안내

Issue 등록은 읽기 전용 요구사항 분석과 계획 댓글 작성까지만 수행한다. 저장소 Write 이상의 권한을 가진 사람은 `/plan <결정사항 또는 수정사항>`으로 계획을 바꾸고, 별도의 `/approve` 댓글로 준비된 계획을 승인할 수 있다. 검증된 `/approve`를 받으면 기존 코드 생성·독립 검증·PR 게시 엔진을 호출한다. `/reject`는 거부 이력을 저장하고 종료한다. PR 리뷰와 병합은 사람이 수행한다.

## 기존 구현 분석 및 재사용

| 기존 모듈 | 확인한 인터페이스와 이번 연결 |
| --- | --- |
| `schemas/project.schema.json`, `validate_config.py`, `branch_rules.py` | v1 Schema, 중복 JSON 키·경로·프로젝트 경계·테스트 정책 및 manual/Issue branch template 검증. `run._load()`로 검증한 설정을 사용한다. |
| `codex_adapter.CodexCLI` | 버전 및 안전 옵션 확인, stdin 입력, 제한된 환경, 프로세스 그룹 종료. 기존 `execute()`를 유지하고 `analyze()`의 `read-only` 및 JSON 출력 경로를 추가했다. |
| `workspace.py` | 허용 경로의 별도 inode 복사, 보호 파일 제외, 내용/경로/링크 검사. 분석도 이 파일 복사와 inventory를 사용하며 Branch나 Git metadata를 만들지 않는다. |
| `run.execute_request()` | 설정 고정 → Codex → 변경 수집 → 독립 검증 → `result.json`. 선택적 `issue_context`, `stage_callback`만 추가했다. |
| `test_runner.validate_workspace()` | 별도 후보 복사본과 Bubblewrap에서 설정된 Unit/E2E를 실행한다. 구현을 변경하지 않았다. |
| `publish.publish()` | sealed evidence, 기준 Git tree, 기존 사용자 변경, 원격 권한, 사람 리뷰 Branch protection을 검사한다. 승인 이후 별도 Git 저장소에서 Commit/Branch를 준비한다. 선택적 `publication_guard`를 추가했다. |
| `orchestrator.execute_workflow()` | 기존 생성·검증 및 게시 함수를 연결한다. Issue context와 단계 callback을 전달하고 승인 무효화 오류를 보존한다. |
| `evidence.py` | 원자적인 외부 JSON 저장과 체크섬을 재사용한다. 체크섬은 로컬 사용자 위조에 대한 서명이 아니다. 원격 Issue journal에는 별도로 HMAC을 적용했다. |
| `github_adapter.GitHubCLI` | 기존 gh CLI 경계, 제한된 환경, 고정된 오류 메시지와 PR 게시 인증을 재사용했다. Issue 전용 subclass와 게시 전용 토큰 선택을 추가했다. |
| 기존 Actions / 테스트 | 루트 `.github/workflows/`가 없었다. 기존 unittest Mock·로컬 Git·모의 게시 fixture를 확장했다. |

제품 `PRJ/`와 `workflow/specs/` 요구사항·아키텍처 문서는 수정하지 않았다. 수동 `run`/`publish` CLI 인자와 기본 모드를 유지한다.

`prj.json`과 `sandbox.json`의 `publishing.branch_template`은 `feature/ai/{date}/{approver}/{issue_title}`이다. 실행 시작일의 한국 시간 날짜, 실제 승인자의 GitHub login, 승인된 Issue 제목으로 브랜치명을 생성한다. 제목의 공백·Git에서 허용하지 않는 문자는 정리하며 한글은 유지한다. 수동 CLI 요청은 `manual_branch_template=ai/{project_id}/{run_id}`를 사용한다. Schema와 Validator도 이 두 규칙을 지원하도록 확장했으며 경로·검증·승인 정책은 유지한다. 상세 규칙은 `PUBLISHING.md`를 참고한다.

## 파일별 변경

| 파일 | 변경 |
| --- | --- |
| `.github/workflows/issue-approval.yml` | Issue 이벤트, 같은 Issue concurrency, 신뢰한 Branch checkout, 승인 단계와 실행 단계 분리 |
| `workflow/runtime/issue_workflow.py` | 계획 contract, 읽기 전용 분석, 댓글 Markdown, 서명된 상태 복구, 승인/거부, 재검증, CLI |
| `workflow/runtime/issue_github.py` | Issue 조회, 댓글 pagination/조회/등록, 작성자 repository permission API |
| `workflow/runtime/codex_adapter.py` | 기존 실행 경계를 공유하는 구조화된 읽기 전용 분석 |
| `workflow/runtime/run.py` | 승인 Issue 데이터를 prompt와 실행 결과에 포함하고 단계 callback 호출 |
| `workflow/runtime/orchestrator.py` | Issue context와 callback 연결, 게시 직전 추가 재검증 연결 |
| `workflow/runtime/publish.py` | 준비 이후와 Push/PR 직전에 선택적 승인 guard 호출 |
| `workflow/runtime/github_adapter.py` | Issue 토큰과 게시 토큰을 각각 gh subprocess에 전달 |
| `workflow/runtime/tests/test_issue_workflow.py` | 승인·실패·변경·복구·실제 통합 엔진 연결의 Mock 테스트 |
| `workflow/runtime/README.md`, `ISSUE_APPROVAL.md` | 입력 방식 및 운영·검증 안내 |
| `workflow/runtime/branch_rules.py`, `workflow/runtime/validate_config.py`, `workflow/schemas/project.schema.json` | 설정 가능한 Issue/manual branch template 검증과 제목 안전화 |
| `workflow/config/projects/prj.json` | 요청한 Issue 브랜치 template과 기존 수동 template 반영 |
| `workflow/runtime/tests/test_branch_rules.py`, `workflow/runtime/tests/test_issue_workflow.py` | 날짜 경계, Git ref 안전성 및 승인 Issue 정보와 게시 브랜치 연결 검증 |

## 이벤트 처리 및 실행 경계

1. `issues.opened`: API로 현재 open Issue 정보를 수집한다. 목적·요약·영역·파일·단계·테스트·위험·질문을 JSON으로 분석하고 Markdown 계획과 메타데이터를 댓글로 게시한다. 분석은 격리된 파일 복사본에서 Codex `--sandbox read-only`로 실행하며 파일 변경을 검사한다. 준비된 계획은 `awaiting_approval`로 저장한다. 사용자 결정이 필요한 항목은 첫 계획에서 함께 묻고, `awaiting_plan`으로 저장한다. 댓글에는 AI가 질문에 맞춰 생성한 `/plan` 답변 예시를 포함한다.
2. `issues.edited`: 제목/본문 snapshot이 같으면 중복으로 처리한다. 달라졌으면 기존 계획·승인을 무효화하고 최신 Issue로 다시 분석한다. 실행이 중단되어 `executing` 등의 상태가 남아 있으면 자동으로 재실행하지 않는다.
3. `issue_comment.created`: PR 댓글은 제외한다. 두 대기 상태에서 `/plan` 뒤에 결정사항 또는 수정사항을 적어 계획을 고칠 수 있다. 기존 Issue, 계획, 댓글과 작성자의 권한을 검증한 뒤 결정사항을 누적 반영한 계획을 게시한다. 위임되거나 생략된 항목은 저장소 관례와 기존 동작을 참고해 기본값을 정하고 계획에 기록한다. 안전하고 합리적인 기본값이 없는 필수 결정만 다시 묻는다. 계획이 준비되면 `awaiting_approval`에서 대기한다. 앞뒤 공백과 줄바꿈을 제외한 댓글 전체가 `/approve`이고 현재 계획이 검증된 경우에만 계획 UUID를 Actions output에 전달한다. `/reject`는 두 대기 상태에서 단독 명령으로 처리한다.
4. Actions 실행 단계: 새 Python 프로세스가 서명된 댓글 상태를 복구한다. 같은 실제 댓글, 승인자, 계획 ID, API 권한, 현재 snapshot 및 계획 댓글 내용을 다시 검증한 후 실행한다. 기본 Python API 모드는 `simulate`이며, 제공된 Actions 실행 단계는 설정된 게시 토큰을 사용해 `real` 모드를 선택한다.
5. 코드 실행 직전, 독립 검증 직전, 게시 진입, 로컬 게시 준비 후, Push 직전, PR 생성 직전에도 Issue·계획·권한·서명된 현재 상태를 확인한다. 설정 파일 해시도 코드 실행 단계의 고정 설정과 비교한다. 검증 실패는 후속 코드 실행 또는 게시를 막는다.

`IssueController`와 선택적 callback은 신뢰한 제어 코드의 내부 API다. 임의의 외부 사용자에게 직접 노출하는 서비스 API가 아니다. CLI는 GitHub Actions 환경, 저장소 context 및 실제 GitHub 댓글을 확인한다. Issue 본문과 계획은 JSON 작업 데이터로 전달하고 기존 허용 경로와 독립 검증 정책을 유지한다. GitHub 토큰과 HMAC key를 worker 환경이나 prompt에 전달하지 않는다.

## 상태 및 중복 실행 방지

기본 흐름은 `received → analyzing → awaiting_approval → approved → executing → validating → publishing → completed`다. `received`와 `analyzing`은 내부 이력에만 기록하고 GitHub 댓글을 남기지 않는다. 추가 질문이 있으면 분석 뒤 `awaiting_plan`으로 이동한다. `/plan`으로 재분석해 준비된 계획을 게시하면 `awaiting_approval`에서 새 `/approve`를 기다린다. 이전 버전에서 게시한 대기 중 계획도 `/plan`으로 이어갈 수 있다. 거부는 `rejected`, 실패는 `analysis_failed`, `approval_invalidated`, `execution_failed`, `validation_failed`, `publishing_failed`로 구분한다.

계획에는 UUID, Issue 번호, 제목/본문 SHA-256 snapshot, 분석 시각, version, 승인 상태를 포함한다. 별도의 bot journal 댓글은 전체 상태, 계획, 계획 댓글 ID/본문 해시, 설정 파일 해시, 승인자·승인 시각·승인 댓글 ID, 최근 100개 전이 및 실행 결과 경로를 저장한다. 이전 journal 댓글은 보존되어 전체 과거 이력을 확인할 수 있다. 같은 상태를 기존 원자적 evidence 저장으로 `<results-dir>/issues/<UUID>/issue.json`에도 기록한다. 실제 엔진 결과는 기존 `<results-dir>/<run UUID>/result.json`, `workflow.json`에 승인 Issue 데이터를 포함한다.

원격 복구는 `github-actions[bot]`의 Bot 댓글과 HMAC-SHA256 서명을 모두 확인한다. 최신 신뢰 bot journal이 손상되면 과거 상태로 돌아가 실행하지 않는다. 사람이 같은 marker나 과거 signed text를 댓글로 붙여도 bot 작성자가 아니므로 상태로 인정하지 않는다. 계획 댓글의 실제 본문과 저장된 해시, 계획 ID/snapshot을 포함한 예상 Markdown을 비교하여 수정·교체를 감지한다.

같은 내용의 Issue 이벤트는 다시 분석하지 않는다. 현재 계획보다 먼저 생성된 결정 또는 승인 댓글과 이미 처리한 댓글 ID는 새 명령으로 인정하지 않는다. 실행은 검증된 승인 티켓으로 시작하며, 실행 중·완료·거부 상태의 새 명령은 무시한다. Actions의 저장소/Issue concurrency와 Linux `flock`을 함께 사용한다. GitHub concurrency는 여러 pending run을 전부 보존하는 메시지 queue가 아니므로 대량 이벤트 중 일부가 교체될 수 있다. 처리된 이벤트는 API에서 최신 Issue와 상태를 다시 읽고, 계획 없는 승인으로 실행하지 않는다.

## 승인 권한과 snapshot

실제 `GET /repos/{owner}/{repo}/issues/comments/{id}` 결과의 전체 본문·사용자·시각·Issue URL을 이벤트와 비교한다. 수정된 댓글, Bot, 다른 Issue 댓글 및 sender 불일치는 차단한다. 작성자 권한은 `GET /repos/{owner}/{repo}/collaborators/{login}/permission`에서 조회하고 `admin`, `maintain`, `write`만 허용한다. Issue 작성자에게 추가 권한을 부여하지 않으며 API 실패나 알 수 없는 permission은 승인하지 않는다. 추가 결정사항은 댓글 ID와 원문 해시를 서명된 상태에 기록하고, 실행 전에도 변경 여부를 확인한다.

Snapshot은 `{title, body}`의 정렬된 JSON에 SHA-256을 적용한다. 없는 본문은 빈 문자열로 처리한다. 승인 시 API로 다시 읽은 snapshot이 계획과 다르면 승인하지 않고 새 계획을 작성한다. 분석 중 내용이 변하면 최신 내용으로 한 번 다시 분석하고, 계속 바뀌면 승인 무효화 상태로 종료한다. 제목이나 본문을 명확히 수정하면 새 edited 이벤트로 재분석할 수 있다.

## 실제 GitHub 운영 설정

현재 저장소에 Push하거나 Actions를 활성화하지 않았다. 운영자는 아래 설정을 준비해야 한다.

| 설정 | 값 또는 필요한 조건 |
| --- | --- |
| Repository variable `WORKFLOW_ISSUES_ENABLED` | `true`로 설정하면 이벤트 job 활성화. 미설정은 실행하지 않는다. |
| `WORKFLOW_CONFIG_PATH` | 저장소 안의 검증된 설정 JSON 상대 경로. 기존 설정을 임의로 바꾸지 않고 대상 repository identity, 실행 모델/버전, 경로·테스트·publishing 항목을 운영자가 확인한다. |
| `WORKFLOW_BASE_BRANCH` | 설정의 `base_branch`와 같은 기존 신뢰 Branch. workflow 파일은 Issue 이벤트를 받는 기본 Branch에도 존재해야 한다. |
| Secret `WORKFLOW_STATE_KEY` | 최소 32바이트의 무작위 private key. 분석/승인과 실행 단계에서 같은 값을 사용한다. 값은 댓글에 저장하지 않는다. 교체 시 기존 서명 상태를 자동으로 승인하지 않는다. |
| Secret `WORKFLOW_PUBLISH_TOKEN` | 해당 저장소로 제한한 GitHub App 또는 fine-grained 토큰. Contents read/write, Pull requests read/write, 기존 게시 엔진의 Branch protection 조회를 위한 Administration read와 repository metadata 접근 권한이 필요하다. 자동 병합 권한/우회를 설정하지 않는다. |
| Actions `GITHUB_TOKEN` | workflow의 `contents: read`, `issues: write`. Issue API와 상태 댓글에만 사용한다. 게시 토큰은 실행 단계에서만 제공한다. |
| Runner labels | `[self-hosted, linux, workflow-isolated]`. Python 3.12+, Git, gh, 설정 버전과 일치하는 Codex CLI, 해당 CLI의 기존 로그인 및 설정된 모델 접근, Bubblewrap와 구성한 테스트 환경이 필요하다. |
| Runner 격리 | Issue 작업 전용의 일회성 격리 runner를 사용하고, Codex 로그인 외 민감한 파일이 HOME 등에 남지 않도록 운영한다. 기존 어댑터의 읽기 경계 한계를 아래 참고한다. |
| Branch protection | 기존 게시 엔진은 최소 한 명의 사람 리뷰, 관리자 적용, 리뷰 bypass 없음 등을 API로 확인한다. Repository 설정을 코드가 변경하지 않는다. |
| 커밋 작성자 | `publishing.commit_author`에 자동화 커밋의 이름과 이메일을 설정한다. 생략하면 checkout의 로컬 Git `user.name`과 `user.email`을 사용하며 머신의 전역 설정은 읽지 않는다. |
| 결과 보존 | runner 임시 결과는 없어질 수 있다. 원격 journal로 상태를 복구하지만 후보/검증 근거를 장기 보존하려면 접근이 제한된 외부 저장 위치와 보존 정책이 필요하다. |

Codex 인증은 runner에 이미 설정된 CLI 로그인을 사용한다. 제품 API key나 새 모델 기본값을 자동으로 만들지 않는다. Issue/GitHub 토큰은 gh subprocess 환경에만 전달하고 Codex에는 전달하지 않는다. 게시 토큰이 없다면 승인 후 실행 단계가 시작되기 전에 실패한다.

## 검증 결과

일반 런타임 테스트는 아래 명령으로 Linux/WSL에서 실행한다. 실제 Codex smoke test나 실제 제품 테스트 opt-in은 설정하지 않았다.

```bash
python3 -B -m unittest discover -s workflow/runtime/tests -p 'test_*.py'
```

추가 테스트는 정상 분석/댓글/승인/전 단계 연결, 거부, permission 수준과 조회 실패, 계획 없음, 대기 상태 아님, 중복 댓글/이벤트/재시작, 잘못된 전체 명령, 제목/본문 snapshot 불일치, 승인 후 편집, 계획 ID/댓글 교체, HMAC 위조·손상, 불충분한 계획, 실제 댓글 context 불일치, 분석 파일 변경, 단계별 변경, 설정 변경, 저장 실패, 토큰 분리, gh pagination/JSON body, read-only CLI, Actions 단계 간 승인 티켓 복구를 검증한다. 실제 로컬 Git fixture에서는 기존 통합 엔진과 독립 검증을 거쳐 모의 PR 생성까지 연결하고 원본 파일/index 보존을 확인한다. 모의 원격 권한 확인 중 Issue가 바뀌면 Push와 PR 생성이 모두 호출되지 않는 것도 확인한다.

검증 환경은 Linux/WSL의 Python 3.14.4이며, 전체 런타임 테스트 216개가 통과했다. 이 중 신규 Issue 승인 테스트는 40개다. Actions YAML을 파싱하고 opened/edited/created 이벤트 및 concurrency 설정을 확인했다. 실제 GitHub Push, PR 생성, 실제 Codex 실행 및 PRJ 테스트·수정은 수행하지 않았다.

## 한계 및 복구

이슈 워크플로의 단계가 실패하면 같은 이슈에 실패 원인, 해결 방법, Actions 실행 링크를 담은 안내 댓글을 별도로 남긴다. 댓글은 기본 Actions 토큰(`issues: write`)으로 GitHub API에 작성하며 `gh`나 게시용 토큰에 의존하지 않는다. 원본 로그, 이슈 본문, 비밀값은 포함하지 않는다. 실패 단계의 구조화된 진단이 없으면 해당 단계에 맞는 기본 안내를 남기며, 이전 실행의 실패 상태를 조회하는 것만으로 댓글을 다시 달지 않는다. 러너가 중단되어 알림 단계가 실행되지 않거나 GitHub API가 댓글을 거부하면 알림을 남길 수 없다.

Actions 로그에서 `publishing_failed`가 나오면 `publication`의 `operation`, `reason`, 가능한 경우 `http_status`를 확인한다. `prepare_git_commit`의 `commit_identity_missing`은 GitHub API를 호출하기 전에 커밋 작성자가 누락된 경우다. `get_branch_protection`의 `403`은 게시 토큰의 `Administration: Read` 권한을, `404`는 토큰의 저장소 접근과 `Settings → Branches`의 classic branch protection 설정을 확인한다. Rulesets만 설정한 경우 기존 게시 엔진의 classic protection 조회를 충족하지 않는다. `attempted: false`는 Push나 PR 생성을 시도하기 전에 차단되었음을 뜻한다.

GitHub Issue 변경과 Git Push/PR 생성은 서로 다른 서비스 작업이므로 하나의 원자적 트랜잭션으로 묶을 수 없다. 각 외부 작업 직전에 다시 검사하지만 검사 직후의 극히 짧은 변경 경쟁을 완전히 없애지는 못한다. 이미 Push한 뒤 PR 직전 요구사항이 바뀌면 PR을 차단하고 기존 게시 journal에 외부 작업 이력을 남긴다. 자동으로 Branch를 삭제하거나 다시 Push하지 않는다.

runner 중단·상태 저장 응답 손실·외부 작업 결과 불확실 시 실행 중 상태를 자동 재시도하지 않는다. 상태 댓글, 로컬 evidence와 원격 Branch/PR을 사람이 먼저 대조해야 한다. `approved` 티켓은 동일한 실제 이벤트와 plan ID로 실행 단계를 재시도할 수 있으나, 이미 `executing` 이상으로 진행된 티켓은 실행하지 않는다. 서명 key 교체나 신뢰 bot journal 손상도 자동 우회하지 않는다.

기존 Codex 어댑터는 환경 토큰을 제외하지만 OS sandbox의 모든 읽기 권한을 프로젝트만으로 제한하지는 않는다. 전용 runner/컨테이너와 최소 로그인 파일로 보완해야 한다. 분석 source excerpt는 전체 128KB 및 파일별 16KB까지 제공하고 전체 파일 목록/설계 context를 함께 전달한다. 큰 프로젝트나 애매한 요청의 계획 품질은 사람의 검토가 필요하다. 사전에 설치된 실제 Codex 버전의 구조화 출력 옵션과 실제 GitHub permission/protection 응답은 운영 환경에서 확인해야 한다. 이번 검증은 Mock 기반이며 실제 GitHub Actions 실행 결과를 주장하지 않는다.
