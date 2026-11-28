# 검증 결과의 PR 게시

생성·검증과 `publish`는 독립 모듈이며, 통합 `run` CLI가 순서대로 연결한다. Codex와 테스트는 별도 프로세스에서 실행하고 GitHub 게시 권한을 받지 않는다. 게시 프로그램은 후보 코드·테스트·설치 스크립트를 실행하지 않는다. 승인·자동 병합·배포는 구현하지 않았다.

## 통합 실행과 모의 게시

`python3 -B -m workflow.runtime.run --config CONFIG --task "작업 내용"`은 기본적으로 생성·독립 검증 후 게시 조건을 재확인하고 모의 게시까지 진행한다. 실패한 단계의 후속 단계는 실행하지 않으며, 테스트 실패에 대한 명시적 게시 허용 정책은 아래 조건을 따른다. 기본값 `--publish-mode simulate`는 GitHub CLI·인증정보·실제 원격 전송을 사용하지 않는다. 준비 Commit·Branch는 원본이 아닌 외부의 별도 로컬 Git 저장소에 만든다. `--publish-mode prepare`는 로컬 준비까지만 수행하고, 실제 게시 모드에는 명시적인 `--publish-mode real`이 필요하다.

기존 게시 기능만 모의 실행하려면 다음 명령을 사용한다.

```bash
python3 -B -m workflow.runtime.publish \
  --config workflow/config/projects/prj.json \
  --result /private/runs/<RUN_ID>/result.json \
  --simulate
```

모의 모드는 기존 검증 근거·변경 범위·전체 Git 기준 트리 검사·PR 본문 생성·로컬 Commit 준비를 재사용한다. 이후 인증·기준 Branch·Push·PR 생성 요청은 메모리 어댑터에서만 처리한다. 실제 인증이나 원격 권한은 확인하지 않는다. `status=simulated`, `simulated_attempted=true`, `attempted=false`, `pr_url=null`, `publishable=false`로 실제 게시와 구분한다. 실제 게시 모드와 모의 모드를 동시에 지정할 수 없다. 모의 어댑터를 실제 전송 어댑터로 바꾸는 CLI 옵션도 없다.

모의 이력은 `publish.simulated.json`, 준비 파일은 `publication.simulated/`에 저장한다. 실제 준비·게시 이력 `publish.json`, `publication/`과 분리하여 모의 PR이 실제 PR로 재사용되지 않게 한다. 통합 보고서는 `workflow.json`에 저장하며 봉인된 검증 근거 `result.json`은 덮어쓰지 않는다. 모의 실행도 기준 Branch 불일치나 사용자 미커밋·미등록 파일을 발견하면 차단한다.

## 수동 사용 순서

1. 프로젝트 담당자가 기준 브랜치에 테스트 프로젝트의 의도한 초기 파일을 먼저 등록한다. 자동화는 기존 사용자 파일을 대신 Commit하지 않는다. 허용 범위의 수정·삭제·미등록 파일이 있으면 게시를 차단한다. 범위 밖의 기존 사용자 변경은 원본 그대로 보존한다.
2. 프로젝트 설정의 `publishing`을 확인한다. 설정 확정 후 `run`으로 새 작업·독립 검증 결과를 만든다. 설정을 바꿨다면 다시 실행해야 한다.
3. 아래의 기본 명령으로 게시 준비와 PR 본문을 검토한다. 원본 Git 저장소는 바뀌지 않는다. 별도 임시 Git 저장소 안에 로컬 Commit과 Branch를 만든다. GitHub 조회·Push·PR 생성은 하지 않는다.

```bash
python3 -B -m workflow.runtime.publish \
  --config workflow/config/projects/prj.json \
  --result /private/runs/<RUN_ID>/result.json
```

검토할 파일은 실행 폴더의 `publication/changes.patch`, `publication/pr-title.txt`, `publication/pr-body.md`, `publish.json`이다. `prepared`는 로컬 준비 완료이며 GitHub 게시 완료나 원격 권한 확인을 뜻하지 않는다. 이때 `local_eligible=true`, `publishable=false`, `remote_check=not_run`이다.

4. 사용자가 준비 내용을 확인하고 실제 게시를 원하면 직접 `--execute`를 추가한다. 관련 Issue가 이미 있으면 `--issue 123`을 추가할 수 있다. Issue를 만들거나 자동 종료하지 않는다.

```bash
python3 -B -m workflow.runtime.publish \
  --config workflow/config/projects/prj.json \
  --result /private/runs/<RUN_ID>/result.json \
  --execute
```

명시적 실행은 인증·저장소 권한·기준 Branch·설정에 따른 보호 정책 확인 → 새로운 Branch Push → PR 생성 → PR 조회 및 결과 확인 순서다. 기본 명령에 `gh pr create --dry-run`을 사용하지 않는다. 공식 문서상 이 옵션도 Push할 수 있기 때문이다.

CLI 종료 코드는 `prepared`·`published`·`simulated`에서 0, 차단·실패·불확실한 결과에서 1, 인자 오류에서 2다. `--issue`는 양의 정수만 받는다. `run` CLI 입력과 기존 결과 필드는 유지했다.

## 설정과 게시 조건

`publishing`은 게시 모듈에서 필수이고 기존 생성·검증 설정에서는 선택 사항이다.

| 항목 | 의미 |
| --- | --- |
| `remote` | 원본 저장소에 이미 구성된 remote 이름. URL을 임의 선택하지 않음 |
| `branch_template` | `{project_id}/{run_id}` 또는 승인된 Issue의 `{date}/{approver}/{issue_title}` 치환 규칙. 현재 설정은 `feature/ai/{date}/{approver}/{issue_title}` |
| `manual_branch_template` | Issue 치환 규칙을 사용하는 설정에서 수동 CLI 요청용 규칙. `{project_id}`와 `{run_id}`를 사용하며 현재 값과 기본값은 `ai/{project_id}/{run_id}` |
| `draft` | 검증 통과 또는 일반 PR 실패 예외의 Draft 여부. PRJ는 `false`, 데모는 `true` |
| `commit_author` | 선택 사항인 `name`, `email`. 없으면 원본 저장소의 로컬 Git user 설정을 조회하며 없으면 차단. 전역 Git 설정은 가져오지 않음 |

기존 `pr_policy.require_human_approval=true`, `allow_auto_merge=false`를 유지한다. 테스트 실패 게시 정책은 다음과 같다.

- `allow_draft_on_failure=true`만 있으면 필수·차단 정책 검사 실패, 시간 초과, 실행 불가 결과를 보존하고 Draft를 강제한다.
- optional `allow_pr_on_failure=true`이면 같은 실패를 보존하면서 `publishing.draft`에 따라 게시한다. false이면 일반 PR, true이면 Draft다. 두 실패 허용 정책이 모두 true이면 이 정책을 따른다. 생략 시 false다.
- 두 정책이 모두 false이면 실패한 검증은 게시를 차단한다. PRJ는 `allow_pr_on_failure=true`, `publishing.draft=false`를 적용한다.

PR 본문에 검증 실패와 실제 결과를 표시한다. Codex 실패, 경로 위반, 입력 변경, 누락·손상된 검증 근거에는 예외를 적용하지 않는다.

`{date}`는 실행 결과 `started_at`의 한국 시간(Asia/Seoul) 날짜를 `YY.MM.DD`로 표시한다. 이후 같은 결과를 다시 게시 준비해도 날짜가 달라지지 않는다. `{approver}`와 `{issue_title}`은 실행 결과에 저장된 승인 Issue 데이터에서 읽는다. 제목은 한글을 유지하고 공백·Git 금지 문자를 `-`로 바꾸며, 경로 구분자·`..`·`.lock`을 정리한다. 제목 부분은 UTF-8 120바이트까지 사용하고 정리한 결과가 비면 `issue`를 사용한다. 예: `feature/ai/26.11.17/JunSuHeo/로그인-화면-개선`.

요청한 Issue 규칙에는 실행 UUID를 추가하지 않는다. 같은 날짜·승인자·제목의 원격 Branch나 PR이 이미 있으면 기존 충돌 검사로 게시를 차단한다.

게시 전 결과의 형식·소유자·개인 접근 권한·체크섬, 실행 ID·설정 해시·Git 기준 SHA·파일 해시를 확인한다. 테스트의 종류·명령·필수 여부·종료 코드·상태·시간 정보가 설정과 일치해야 한다. 누락·중복과 정당한 사유 없는 필수 미실행은 차단한다. 선택 미실행은 명시된 설정 조건이 실제 변경 목록에 적용될 때만 인정한다. 테스트 실패 게시 예외에서는 앞선 차단 검사 실패로 후속 검사가 미실행된 근거도 인정한다. 검증 오류 전체가 기록된 테스트 판정과 일치하는지 재확인한다.

기준 Branch와 작업 시작 HEAD는 같아야 한다. SHA-1 Git 저장소를 초기 지원한다. 기준 Branch를 remote에서 다시 확인하고 검증 때와 다른 커밋이면 재생성·재검증을 요구한다. 현재 source HEAD를 무조건 Commit하거나 `git add .`로 원본 사용자 변경을 수집하지 않는다.

기준 Git 트리의 전체 허용 범위가 시작 스냅샷과 달라도 게시를 차단한다. 수정한 파일만 비교하지 않는다. 검사에 사용된 미등록·미커밋 파일을 생략한 PR은 검증한 코드와 다르기 때문이다. 시작 스냅샷과 일치한 Git 기준 위에 이 실행의 추가·수정·삭제만 반영하고, 최종 Git 트리도 검사한 후보 전체와 다시 비교한다.

## Git 및 GitHub 권한 경계

게시 Git 저장소는 실행 폴더 아래에 새로 만든다. 기준 Git 객체를 로컬에서 읽고 `read-tree`, `hash-object --stdin`, `update-index`, `write-tree`, `commit-tree`를 사용한다. 후보 파일의 checkout·Git hook·외부 filter·textconv·fsmonitor·전역 Git 설정을 실행하지 않는다. Push는 설정 규칙으로 생성한 새 Branch에만 수행하며 기존 remote Branch·PR이 있으면 차단한다. Force Push는 하지 않는다.

remote는 설정의 `owner/name`과 일치하는 credential-free GitHub HTTPS/SSH 주소여야 한다. 실제 게시에는 정규화한 HTTPS URL을 사용한다. URL에 Token을 넣지 않는다. 초기에는 github.com만 지원한다.

`gh` 설치 및 CLI 옵션을 실행 직전에 확인한다. 인증은 `gh auth status --hostname github.com`으로 확인하고 출력은 기록하지 않는다. `GH_TOKEN`/`GITHUB_TOKEN` 또는 기존 `gh` 로그인만 게시 프로세스에 제공한다. Git 읽기·Codex·제품 테스트에는 게시 Token을 전달하지 않는다. Push에 필요한 Token은 게시 프로그램의 신뢰하는 askpass helper가 Git에 직접 전달한다. Token을 파일·명령 인수·로그·remote URL에 저장하지 않는다.

GitHub 조회로 저장소 identity, Push 권한, 기준 Branch SHA를 항상 확인한다. optional `pr_policy.require_branch_protection`은 생략 시 true이며, 이때 사람 리뷰·관리자 적용·리뷰 우회 금지의 classic branch protection을 확인한다. 보호 조회 거부·오류·불충분한 규칙은 차단한다. false이면 protection API를 호출하지 않아 보호 규칙 없는 저장소도 게시할 수 있다. PRJ는 false다. 저장소 설정은 변경하지 않는다. Rulesets의 정책 해석은 지원하지 않으며 실제 토큰 scope/조직 정책은 최종 Push·PR 생성을 거부할 수 있다.

보호 규칙이 없으면 GitHub가 병합 전 사람 리뷰와 테스트 통과를 강제하지 않는다. Issue의 `/approve`는 구현 실행 승인이고 워크플로는 자동 병합하지 않는다.

PR 생성에는 명시적인 `--repo`, `--base`, `--head`, `--title`, `--body-file`과 설정에 따른 `--draft`만 사용한다. `--head`로 gh의 자동 Fork·Push 선택을 방지한다. PR 본문에는 요청, 변경 파일, 설계문서 변경 여부, 실제 Unit/E2E 결과·명령·사유, 최종 검증, 실행 ID·내용 해시, 선택적 Issue, 남은 위험을 포함한다. 원문 테스트 로그는 PR에 복사하지 않는다.

## 저장·재실행·신뢰 제한

`result.json`은 수정하지 않고 `publish.json`에 시도 여부·로컬 준비·원격 확인·차단 사유·Commit SHA·Branch·PR 번호/URL·시각·상태를 따로 저장한다. 원본 결과의 체크섬도 보존한다.

Push 및 PR 요청 직전에 이력을 저장한다. 생성 응답이 유실되면 PR을 조회하고 실행 ID·head SHA·base Branch가 일치하는 한 건만 성공으로 확정한다. 결과를 확정할 수 없으면 `outcome_unknown`으로 남긴다. 같은 실행에 기존 외부 시도가 있으면 자동 재시도·대체 PR 생성·기존 Branch 삭제를 하지 않는다. 담당자가 GitHub 상태를 확인해야 한다. 완료된 게시의 재실행은 기록된 결과만 반환한다. 잠금이 남았거나 저장이 실패한 경우에도 원격 상태부터 확인해야 한다. 기존 `publish.json`이 손상되면 덮어쓰지 않고 `publish-error-<UUID>.json`에 새 차단 사유만 저장한다.

체크섬이 없고 Git 기준 스냅샷이 없는 이전 버전 결과는 게시할 수 없다. 설정 확정과 프로젝트 기준 Commit 이후 새 실행이 필요하다. 파일 소유자·권한·해시 검사는 로컬의 신뢰하는 운영 사용자 경계와 우발적 손상 방어다. 동일 사용자나 root가 결과·체크섬을 함께 위조하는 것을 인증하는 전자서명은 아니다. 이후 CI artifact 연결 시 신뢰하는 job의 출처 검증이 추가로 필요하다.

## 이번 구현의 검증 범위

일반 테스트는 임시 로컬 Git 저장소의 준비 Commit·Branch·diff와 모의 GitHub 경계를 검증한다. 테스트에서 실제 GitHub API·Push·PR 생성을 호출하지 않는다. 임시 fixture의 Commit은 현재 저장소의 Commit이 아니다.

```bash
python3 -B -m unittest discover -s workflow/runtime/tests -q

WORKFLOW_DEMO_TESTS=1 python3 -B -m unittest discover \
  -s workflow/runtime/tests/integration -p test_demo_validation.py -v

WORKFLOW_DEMO_TESTS=1 python3 -B -m unittest discover \
  -s workflow/runtime/tests/integration -p test_demo_workflow.py -v
```

2026-11-17 WSL에는 `gh`가 없다. 공식 GitHub CLI 문서에서 명령·옵션은 확인했지만 설치된 gh의 동작·인증·실제 Push·PR 생성은 검증하지 않았다. 현재 데모와 workflow는 Git 미등록 상태이며 자동으로 등록하지 않았다. 실제 게시 시험은 담당자가 이 전제조건을 준비한 뒤 직접 `--execute`를 요청/실행할 때 진행한다.
