# 수동 요청 및 GitHub Issue 승인 통합 워크플로우

Python 3.12 이상과 표준 라이브러리를 사용한다. 현재 Codex 어댑터의 실제 실행 대상은 Linux와 WSL이다. 일반 Unit Test는 Codex 설치나 인증 없이 실행할 수 있다.

수동 CLI와 GitHub Issue는 같은 생성·검증·게시 엔진을 사용하는 작업 입력 방식이다. Issue 입력은 읽기 전용 분석과 계획 댓글을 먼저 작성한다. `/plan <결정사항 또는 수정사항>`을 받으면 이를 반영한 계획을 게시한다. 준비된 계획은 `awaiting_approval` 상태에서 권한 있는 사람의 별도 `/approve` 댓글을 검증해 실행한다. Issue 이벤트, 서명된 영속 상태, 운영 Secrets 및 테스트 결과는 [ISSUE_APPROVAL.md](ISSUE_APPROVAL.md)를 참고한다. `run` CLI의 기본 모드는 GitHub 게시 모의 실행이며, Commit과 Branch는 외부의 별도 Git 저장소에만 준비한다. 원본 checkout·index·Branch는 변경하지 않는다. 실제 Push·PR 생성은 명시적 `--publish-mode real`에서만 가능하다. 별도 `publish` CLI도 유지하며, 기본은 로컬 준비, `--simulate`는 모의 게시, `--execute`는 실제 게시다. PR 검토와 병합은 사람이 수행한다. 자세한 게시 조건은 [PUBLISHING.md](PUBLISHING.md)를 참고한다.

## 실행 흐름

`CLI → 설정의 고정된 복사본 검증 → 환경·문서·CLI 확인 → 격리된 파일 복사 → Codex 실행 → 변경 경로·내용 검증 → 별도 임시 복사본에서 Unit/E2E 실행 → 실제 결과 판정 → 검증 근거 저장 → 게시 조건 재검사 → 외부 로컬 Commit 준비 → 모의 Push·PR 요청 → 통합 결과 저장`

`orchestrator.execute_workflow(...)`는 기존 `run.execute_request(...)`와 `publish.publish(...)`를 호출하는 통합 제어 함수다. `execute_request(...)`의 기존 생성·검증 전용 인터페이스는 유지한다. Codex 실패 시 변경 수집·테스트·게시를 진행하지 않으며, 허용 범위 위반 시 테스트·게시를 차단한다. 필수 또는 차단 정책 테스트가 실패하면 후속 테스트를 `not_run`으로 기록한다. `pr_policy.allow_draft_on_failure=true`이면 테스트 실패·실행 불가·시간 초과를 보존하고 검토용 Draft PR 게시로 이어진다. PRJ 설정은 이 정책을 활성화했다. 변경 없음, 기준 Branch 불일치, 기존 사용자 변경, 근거 손상이나 테스트 입력 변경은 게시를 차단한다.

`run.py`는 기존 `validate_config.validate_config(config_path, repo_root)`를 호출한다. 검증기의 JSON 읽기·경로 검사 함수를 내부적으로 재사용한다. 설정의 임시 복사본은 개인 접근 권한으로 생성하고 Codex 실행 전에 삭제한다. 이후 테스트도 이때 고정한 설정으로 실행하며 후보나 원본에서 변경된 설정을 다시 읽지 않는다.

## 프로젝트 설정

기존 v1 설정에 다음 `execution` 영역을 추가한다. 이 영역은 기존 오프라인 검증과의 호환성을 위해 Schema 최상위 필수 항목에는 넣지 않았지만, 실행 엔진에서는 반드시 필요하다. 일부만 제공하거나 필수값을 누락하면 차단한다.

| 항목 | 의미 |
| --- | --- |
| `execution.instructions` | 저장소 기준 상대 경로의 프로젝트 작업 지침 파일 목록. 프로젝트 경계 안의 기존 파일만 읽으며 수정할 수 없다. `[]`는 추가 지침이 없음을 명시한다. |
| `execution.environment.platform` | `linux` 또는 `macos` (x86_64 및 ARM64). Apple Silicon에서 x86_64 Python을 사용하는 경우도 `macos`로 인식한다. |
| `execution.environment.required_programs` | PATH에서 반드시 발견되어야 하는 프로그램 이름. `[]`는 이 단계에서 추가 도구 검사를 요구하지 않음을 명시한다. 설치나 버전·서비스 검증을 대신하지 않는다. |
| `execution.codex.version` | 실제 설치·검증한 Codex CLI 버전. `codex --version` 결과와 일치해야 한다. |
| `execution.codex.model` | 현재 인증 계정에서 이용 가능하다고 확인한 모델 식별자. 엔진이 임의의 기본 모델을 선택하지 않는다. |
| `execution.codex.timeout_seconds` | 명시적인 실행 시간 제한, 1~3600초 |

`allowed_paths`, `design_documents`, 테스트 `cwd`, 지침 파일은 모두 **원본 저장소 루트 기준 POSIX 상대 경로**다. 공통 코드에 PRJ 경로나 제품 테스트 명령을 넣지 않는다. PRJ 예시는 실행 정보도 `null`로 표시한 미확정 예시이며 검증을 통과하지 않는다. `.example` 확장자를 바꾸는 것만으로 활성화되지 않는다.

## CLI

저장소 루트에서 실행하며, 설정 파일로 작업 대상을 선택한다. 제품 `PRJ/`에는 `prj.json`, 테스트용 계산기에는 `sandbox.json`을 사용한다. 아래 예시는 sandbox 설정을 사용하며 Codex와 테스트를 실행하고 GitHub 게시 부분은 모의 실행한다.

```bash
python -B -m workflow.runtime.run \
  --config workflow/config/projects/sandbox.json \
  --task "계산기의 덧셈 구현을 정리하고 설계문서를 갱신해줘"
```

다른 실행 디렉터리에서는 모듈을 찾을 수 있는 환경과 `--repo-root /absolute/repository`를 제공한다. 기본 저장소 루트는 현재 디렉터리이며 `.git`이 있는 최상위 checkout인지 확인한다. 설정 파일도 대상 저장소 안에 있어야 한다.

`--results-dir /private/path/runs`로 저장 위치를 지정할 수 있다. 기본값은 해당 실행 환경의 임시 디렉터리 아래 `ai-workflow-runs`다. 원본 저장소 내부 또는 원본을 포함하는 상위 경로를 결과 경로로 지정하면 차단한다. 기본 임시 위치는 OS 정리로 사라질 수 있으므로 필요한 장기 보존 위치와 보존 기간은 운영자가 정한다.

`--publish-mode simulate`가 기본값이다. 이 모드는 실제 `gh`·인증정보·원격 연결을 사용하지 않고 메모리 안의 GitHub 및 Git 전송 어댑터를 사용한다. `--publish-mode prepare`는 로컬 준비까지만 수행한다. `--publish-mode real`은 실제 원격 Push·PR 생성을 요청하는 옵션이며 이번 구현 검증에서는 실행하지 않았다. 관련 Issue가 이미 있으면 `--issue 123`으로 본문에 연결할 수 있다. Issue를 생성하거나 감지하지 않는다.

CLI 종료 코드 `0`은 전체 흐름 성공, `1`은 실행·검증·게시 실패, `2`는 인자 오류다. 성공 시 기존 `final_status=completed`를 유지하고 `workflow_status`로 `completed_simulation`, `prepared`, `published`를 구분한다. 게시 실패는 `final_status=publication_failed`로 기록한다. 통합 결과에서 모의 성공은 실제 GitHub 권한이나 원격 게시 성공을 뜻하지 않는다. 기존 검증 근거 `result.json`은 게시 실패 시에도 덮어쓰지 않는다. 과거 결과의 `completed_unverified`는 독립 검증 이전 상태이며 검증 통과로 재해석하지 않는다. 테스트 통과는 사용자 요청의 완전한 달성이나 병합 승인을 보증하지 않는다.

실패 후 Draft PR 게시가 완료되면 통합 보고서 `workflow.json`의 `final_status`는 `completed`이며 `validation_status=failed`와 실제 검사 결과·오류는 유지한다. 검증 근거 `result.json`의 `final_status=validation_failed`도 그대로 보존한다. `draft_on_test_failure`는 고정된 정책과 테스트 결과로 판정한 Draft 게시 대상 여부이며, 게시 모듈은 설정과 근거를 다시 검증한다.

## 독립 테스트 설정과 실행

공통 실행 코드는 프로젝트의 `tests.unit`, `tests.e2e` 항목에서 `command.program`, `command.args`, `cwd`, `required`를 사용한다. 통합 실행은 Unit Test 이후 E2E를 실행하며, 차단되는 실패가 발생하면 후속 검사를 `not_run`과 사유로 남긴다. `on_failure=record`인 선택 검사 실패는 기록 후 계속할 수 있다. 기존 `validate_workspace(...)`와 `execute_request(...)`를 직접 호출하면 기본적으로 나머지 검사도 수집하는 동작을 유지하며, 통합 제어 함수는 `stop_on_failure=True`를 전달한다. 명령과 인수는 배열로 전달하고 셸 문자열로 합치지 않는다. 명령 자체가 실행하는 코드의 안전성은 별도 검토가 필요하다.

기존 v1 설정을 깨지 않도록 다음 필드는 선택 사항이다. 누락 시 적용하는 보수적인 호환 정책은 아래와 같고 데모 설정에는 모두 명시했다.

| 필드 | 의미와 호환 정책 |
| --- | --- |
| `timeout_seconds` | 테스트당 시간 제한 1~3600초, 기존 항목은 300초. Codex 시간 제한과 별도다. |
| `run_if` | 기본 `always`. 필수 테스트는 반드시 `always`다. |
| `run_if: never`, `skip_reason` | 선택 테스트의 명시적 미실행·해당 없음. 비어 있지 않은 사유 필수. 결과는 `not_run`. |
| `run_if: changed_paths`, `changed_paths` | 선택 테스트는 지정한 저장소 상대 파일/디렉터리 범위에 추가·수정·삭제가 있을 때 실행. glob을 사용하지 않는다. |
| `on_failure` | 기본 `block`. 선택 테스트의 실패·실행 불가·시간 초과를 기록만 하려면 `record`를 명시한다. 필수 테스트는 `record`를 사용할 수 없다. |

`test_runner.py`는 Codex와 별개 프로세스로 테스트를 실행한다. 실행 전 후보의 허용 경로와 설정 구조·필수 경로를 다시 확인하고 후보 전체의 내용 해시를 기록한다. 후보는 새로운 임시 검증 폴더로 복사하며 테스트는 이 복사본에서만 수행한다. 원본 사용자 변경은 Codex 실행 직전의 스냅샷에 포함되므로 Codex 변경으로 오인하지 않는다. Git 메타데이터가 없는 스냅샷에서는 Git diff 대신 SHA-256·실행 비트의 전후 비교로 추가·수정·삭제를 구분한다.

Linux/WSL에서는 Bubblewrap(`bwrap`), macOS x86_64/ARM64에서는 Seatbelt 기반 `sandbox-exec`로 테스트를 격리한다. macOS sandbox preflight는 후보 snapshot과 private temp 쓰기, host home 차단, network bind 차단을 확인한다. `sandbox-exec`는 Apple이 deprecated 처리했으므로 도구가 없거나 capability 점검에 실패하면 `unavailable`로 기록하고 host에서 실행하지 않는다. 설치·인증·권한 상승은 수행하지 않는다.

독립 검증은 엔진이 만든 임시 복사본의 루트를 실제 경로로 정규화한 뒤 테스트 cwd와 포함 관계를 비교한다. macOS의 `/var` → `/private/var`, `/tmp` → `/private/tmp` 별칭을 같은 경로로 처리하며, 후보 내부의 심볼릭 링크·허용 경로 밖 변경은 계속 차단한다. `validation_failed`와 `path_violation`이 함께 표시되면 원본 `result.json`의 `changed_files`, `validation.scope_status`, `validation.errors`, 검사 실행 여부를 확인한다. 이 코드는 임시 복사본과 파일 링크의 경계 오류에도 사용되므로 표시만으로 PRJ 밖 코드 변경을 의미하지 않는다.

Linux 검증은 시스템 런타임(`/usr`, `/bin`, `/lib`, `/lib64`, `/etc/alternatives`, `/etc/ld.so.cache`)만 읽기 전용으로 제공한다. 테스트 복사본만 `/workspace`에 쓰기 가능하게 마운트하고 HOME·TMPDIR를 임시 경로로 둔 뒤 환경 변수를 비운다. PID·network namespace와 capability 제한을 적용한다. macOS에서는 시스템 runtime 경로, 검증 snapshot, private HOME/TMPDIR만 허용하는 Seatbelt profile을 적용하고 host home과 network 접근을 차단한다. 두 환경 모두 원본 checkout, Codex 인증 파일, host 서비스에 접근하지 않는다.

`uv` 검사는 가상환경과 캐시를 샌드박스의 `/tmp`에 만든다. 검사마다 새 임시 공간을 사용하며, `/workspace`에 생긴 링크와 입력 파일 변경은 기존대로 차단한다.

`prj-backend-check`는 Linux와 macOS에서 임시 `studio_test` PostgreSQL로 백엔드 pytest를 실행한다. PRJ 설정은 `required: true`, `run_if: always`, `on_failure: block`이다. 러너의 시스템 PATH에 `uv`와 Python 3.12 이상, PostgreSQL 서버·클라이언트 도구가 필요하다. PostgreSQL 도구는 PATH 외에도 Linux의 `/usr/lib/postgresql/*/bin`, macOS Homebrew의 `/opt/homebrew/opt/postgresql@*/bin` 및 `/usr/local/opt/postgresql@*/bin`에서 찾는다. 실행 중 도구를 설치하거나 서비스 DB에 연결하지 않는다.

Actions는 승인 확인 후 신뢰된 기준 checkout의 잠금 파일로 별도 `/tmp/workflow-prj-deps.*` 위치에 의존성 캐시를 준비한다. 이 단계의 `uv sync`는 비밀값 없는 환경에서 `--frozen --no-build --no-python-downloads`로 실행하며, 후보의 코드나 설치 스크립트를 실행하지 않는다. 완료된 캐시만 `WORKFLOW_PRJ_UV_CACHE`로 검증기에 전달하고 실행 종료 시 삭제한다. 캐시 준비 단계의 실패 후에도 코드 실행과 검증으로 이어지며, 검증기는 준비되지 않은 캐시를 `unavailable`로 기록한다. 실제 검사는 해당 캐시에서 `--offline --frozen --no-build --no-python-downloads`로 설치하고, 후보가 새 의존성을 요구하면 검사 준비 실패로 기록한다. Draft 허용 정책에 따라 게시 여부를 판정한다.

Linux는 기존 Bubblewrap의 읽기 전용 캐시 마운트를 유지한다. macOS는 신뢰된 실행 스크립트만 private scratch로 복사하고 캐시에 읽기 권한만 준다. 짧은 `/private/tmp/wpg-*` 경로에 DB·소켓·가상환경을 만들어 Unix 소켓의 104바이트 제한을 피한다. PostgreSQL의 System V semaphore와 기본 시스템 사용자 조회를 허용하고 공유 메모리는 mmap 파일로 제한한다. 네트워크는 해당 scratch의 PostgreSQL Unix 소켓에만 허용하며 TCP, 다른 Unix 소켓, host HOME은 차단한다. 별도 capability 점검에서 사용자 조회, 소켓 왕복, 캐시 읽기·쓰기 차단, 외부 Unix 소켓·TCP·HOME 차단을 확인한 뒤 실행한다. 점검 실패나 의존성·DB 준비 실패는 `unavailable`이며 host 실행으로 대체하지 않는다.

실제 백엔드 통합 검증은 일반 discover와 분리한다. 신뢰된 기준 잠금 파일로 준비한 캐시와 위 도구가 있는 환경에서 저장소 루트의 아래 명령을 실행한다. 임시 DB만 생성하며 모델을 호출하지 않는다.

```sh
WORKFLOW_PRJ_TESTS=1 WORKFLOW_PRJ_UV_CACHE=/absolute/prepared/uv-cache \
  python3 -B -m unittest discover -s workflow/runtime/tests/integration -p test_prj_validation.py -v
```

테스트 프로세스의 종료 코드, 소요 시간, stdout·stderr를 수집한다. 시간 초과·완료 시 남은 하위 프로세스도 정리한다. 각 출력은 메모리에서 256 KiB로 제한하고 비밀정보를 가린 뒤 결과에 저장한다. 한도를 초과한 스트림은 전체 생략하고 증거 수집 불가로 `unavailable` 처리한다. 원문 로그를 디스크에 따로 저장하지 않는다.

종료 코드 0을 성공 근거로 사용하되 `Ran 0 tests`, `no tests ran/collected/found` 보고는 실패로 처리한다. 임의 테스트 도구의 실제 테스트 수를 모두 판별할 수 있는 것은 아니다. 테스트가 삭제·완화되었는지, 의미 있는 시나리오를 검증하는지는 사람의 diff 검토가 필요하다. 실행 중 입력 파일이 변경·삭제되거나 후보 내용이 외부에서 바뀌면 결과를 무효화한다. 검사 스크립트가 일시적으로 검사를 우회한 뒤 복구하는 행위까지 해시 비교로 탐지할 수는 없다.

| 검사 상태 | 의미 |
| --- | --- |
| `passed` | 실행했으며 종료 코드 0, 0개 검사 보고 없음 |
| `failed` | 실행했으며 비정상 종료 또는 0개 검사 보고 |
| `not_run` | 명시된 선택 검사 정책·조건으로 미실행 또는 앞선 실패·입력 변경으로 후속 실행 차단 |
| `unavailable` | 격리·실행 파일·런타임·출력 수집 문제로 검사 불가 |
| `timeout` | 설정한 시간 제한 초과. 종료 코드와 수집된 부분 로그 포함 |

필수 검사 중 하나라도 `passed`가 아니면 최종 검증은 실패다. 선택 검사의 `block` 정책 위반도 실패이며 `record` 정책의 결과는 그대로 남긴다. 차단하는 실패가 없고 실제 성공한 검사도 없으면 `not_run`으로 판정하며 Draft 예외를 적용하지 않는다. 테스트 실패 후 Codex를 자동 재호출하지 않는다. Draft 예외는 실패한 테스트가 있고 검증 오류가 그 테스트 판정과 일치할 때만 허용하며, 누락된 검사 근거나 입력 변경 등 별도 검증 오류에는 적용하지 않는다.

## Codex CLI 연결

공식 문서를 실제 조회해 확인한 인터페이스:

- [CLI reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli)
- [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
- [Config reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Authentication](https://learn.chatgpt.com/docs/auth)

`codex_adapter.py`는 실행 직전에 `--version`, `--help`, `exec --help`를 조회해 고정 버전과 필요한 옵션을 확인한다. 지원되지 않는 버전이나 옵션에서 다른 명령으로 추측·재시도하지 않는다.

`codex --strict-config --ask-for-approval never exec`에 `--sandbox workspace-write`, `--skip-git-repo-check`, `--ephemeral`, `--ignore-rules`, 명시한 `--model`과 프롬프트 표준입력 `-`를 사용한다. Codex 사용자 설정을 불러오며, 프로젝트 모델과 runtime 안전 옵션은 명시적으로 적용한다. 별도 workspace에는 Git 메타데이터를 복사하지 않으므로 저장소 검사 생략 옵션을 사용한다. sandbox 설정은 외부 네트워크, 추가 writable roots, 일반 `/tmp`와 `$TMPDIR` 쓰기 권한을 비활성화한다. CLI가 지원하지 않는 설정은 strict config 검사를 통해 차단해야 한다.

인증 제공자는 기존 Codex 사용자 설정을 유지한다. `ai_workspace`의 `env_key`가 `AI_WORKSPACE_API_KEY`이면 Actions의 같은 이름 Secret을 분석·실행 단계에 제공한다. 수동 실행에서는 해당 변수가 실행 환경에 있어야 한다. ChatGPT 로그인은 이 제공자의 환경변수 인증을 대신하지 않는다. 엔진은 로그인·설치·인증정보 출력·Token 요청을 수행하지 않는다.

상속 환경 변수는 명시한 OS 필수 항목으로 제한하며, `AI_WORKSPACE_API_KEY`만 Codex 프로세스의 제공자 인증에 추가한다. 키는 명령 인수나 prompt에 넣지 않는다. 키가 있으면 `shell_environment_policy`를 `inherit="core"`, 빈 `set`, 키 제외 `filters`, 셸 profile 비활성화로 덮어써 Codex 셸 명령에 전달하지 않는다. 도움말·버전 조회, GitHub 전송, 독립 테스트에는 이 키를 추가하지 않는다. GitHub Token, 다른 API Key, 제품 비밀정보와 셸 초기화 변수는 계속 제외한다. 이 설정은 OS의 모든 읽기 경계를 제한하는 기능이 아니므로 전용 러너 격리가 필요하다. 인증 방식·모델 접근·sandbox 강제 가능 여부는 설치 환경에서 별도로 검증해야 한다.

## 작업 경로 보호

`workspace.py`는 허용 경로의 파일을 새 inode로 개인 실행 디렉터리에 복사한다. 원본을 편집하거나 변경 결과를 원본으로 적용하지 않는다. 설정·작업 지침·Git 제어 파일·`.github`·공통 `workflow/`·인증 파일·`.env`·종속성 및 가상환경 디렉터리는 복사하거나 변경 대상으로 사용할 수 없다. 설정된 설계문서와 지침 내용, 승인된 파일 구조, 프로젝트 설정, 자동화 요구사항·아키텍처를 프롬프트로 제공한다.

실행 전후 SHA-256과 실행 가능 비트를 비교해 추가·수정·삭제 목록을 생성한다. 파일과 빈 디렉터리의 경계 위반, 심볼릭 링크·하드 링크·특수 파일, 민감정보 의심 내용을 차단한다. 시간 초과나 인터럽트 시 프로세스 그룹을 종료한 후 결과를 수집한다. Codex·경로 검사 실패 workspace는 삭제하고 경로가 안전한 테스트 실패 후보는 조사용으로 보존한다. 경계가 바뀌어 안전하게 삭제할 수 없으면 그 사실을 결과에 남긴다.

Issue 분석도 모델 호출 전에 같은 검사를 수행한다. `sensitive_content`가 발생하면 설정된 참고 문서와 허용 경로의 파일을 확인하되 감지 값을 로그나 댓글에 출력하지 않는다. `workspace.py`의 `_SOURCE_EXAMPLES`는 검토한 코드 표현식과 격리 테스트 fixture만 해당 파일 경로에 허용한다. 인증 코드·fixture가 바뀌면 실제 PRJ snapshot의 분석 준비 테스트와 경로·변경 값·상속 비밀값 차단 테스트를 함께 실행한다. 테스트 파일 전체나 임의의 비밀번호·토큰을 허용하지 않는다.

수집 제한은 최대 10,000개 파일, 파일당 10 MiB, 전체 100 MiB이고 컨텍스트 문서는 파일당 512 KiB다. 준비 단계와 결과 단계에서 제한을 확인한다. 파일시스템의 동시 변경이나 OS sandbox의 결함까지 검증기가 막을 수 있는 것은 아니다. Codex 변경 생성 단계의 읽기 권한 전체를 프로젝트 경로로 제한하는 별도 OS 격리는 아직 구현하지 않았다. 독립 테스트 단계에는 앞서 설명한 OS별 Bubblewrap/Seatbelt 격리를 적용한다. 생성 단계까지 강한 읽기·프로세스 격리가 필요한 환경은 추가 외부 격리를 준비해야 한다.

## 실행 결과

```text
<results-dir>/<UUID>/
  workflow.json   통합 실행 결과: 생성·검증·게시 상태와 단계별 시각
  result.json
  result.sha256   결과 파일의 무결성 검사 값
  baseline.json   Codex 실행 직전 파일 목록·해시와 Git 기준 커밋
  publish.json    별도 게시 시도 결과. 검증 결과를 덮어쓰지 않음.
  publication/    별도 게시 Git 저장소·변경 패치·PR 본문
  publish.simulated.json   실제 게시 이력과 분리한 모의 게시 결과
  publication.simulated/   모의 실행용 로컬 Git 저장소·패치·PR 본문
  workspace/      통과한 후보 또는 경로가 안전한 테스트 실패 후보. 원본 적용 없음.
```

`result.json`에는 실행 ID, 프로젝트 ID, 민감정보를 가린 요청, 시작·종료 UTC 시각, 설정 해시, Codex 상태·종료 코드·환경, 최종 상태, 변경 경로와 전후 해시, 오류, 결과·workspace 경로를 저장한다. 추가된 `validation` 객체에는 검증 시작·종료 시각, 경로 검사 상태, 검사한 후보의 내용 해시, `tests.unit`·`tests.e2e` 결과 배열, 검증 오류를 저장한다. 각 검사 결과에는 ID·종류·필수 여부·명령·cwd·시간 제한·실행 상태·종료 코드·소요 시간·stdout·stderr·실패 또는 미실행 사유가 있다. 원자적으로 저장하고 Linux에서 실행 디렉터리는 `0700`, 결과 파일은 `0600`으로 제한한다.

`workflow.json`은 위 정보를 포함하는 통합 보고서다. `execution_id`는 기존 `run_id`와 같고, `project_name`은 설정의 프로젝트 식별자를 사용한다. `stages`에 설정·환경·준비·Codex·변경 수집·검증·게시의 상태(`passed`, `failed`, `not_run`)와 시작·종료 UTC 시각을 저장한다. `publication`에는 게시 조건, 차단 사유, Commit SHA·Branch·모의 요청 이력이 있다. `workflow_result_path`는 통합 보고서, 기존 `result_path`는 검증 근거의 위치다. 모의 PR은 `simulated_pr_number`로만 기록하고 실제 `pr_number`·`pr_url`은 `null`로 유지한다. 모의 성공도 실제 원격 게시 자격은 확인하지 않았으므로 `publishable=false`, `remote_check=simulated`다.

| 최종 상태 | 의미 |
| --- | --- |
| `completed` | 생성·독립 검증 통과 또는 통합 보고서에서 정책에 따른 실패 후 Draft 게시 완료. 검증 성공 여부는 `validation_status`로 확인. 사람 승인·병합 없음. |
| `publication_failed` | 게시 조건 또는 선택한 게시 모드 실행이 실패. 통과·실패한 검증 근거는 유지. |
| `validation_failed` | 필수 또는 차단 정책 검사 실패·실행 불가·시간 초과, 전체 미실행, 입력 변경 또는 검증 준비 실패. |
| `completed_unverified` | 과거 버전 결과에서만 사용. 독립 검증을 수행하지 않았음. |
| `config_error` | 파일·JSON·Schema·실행 필수 설정 오류 |
| `input_error` | 직접 API 호출에서 작업 요청이 비어 있거나 NUL 문자 포함 |
| `environment_error` | Git 루트·필수 프로그램·문서·플랫폼·CLI 버전/옵션 문제 |
| `codex_missing` | Codex CLI가 없거나 실행 전에 사라짐 |
| `codex_failed` | Codex 시작 또는 실행 실패 |
| `timeout` | 설정한 시간 초과 |
| `result_collection_failed` | 변경 수집·저장 실패 |
| `path_violation` | 허용 경계·보호 파일·링크 위반 |
| `sensitive_content` | 작업 파일이나 참고 문서에서 민감정보 감지. 로그와 Issue 댓글에는 감지한 값을 출력하지 않음 |
| `unexpected_error` | 그 외 예외 또는 인터럽트 |

Codex의 stdout·stderr와 예외 원문은 기록하지 않는다. 요청과 메시지는 알려진 비밀정보 패턴 및 상속된 비밀정보 값을 가린다. 자동 탐지가 모든 비밀정보를 식별하는 보증은 아니므로 요청·설정·승인한 소스 자체에 비밀정보를 넣지 않아야 한다. 결과 저장에 실패하거나 안전한 저장 경로가 없으면 `result_path=null`과 실패 상태를 출력한다.

실패한 Codex 실행의 stderr는 메모리에서만 확인한다. 알려진 모델 접근 오류, 인증 오류, 사용량 제한은 원문을 포함하지 않는 고정 안내 메시지로 `errors`에 저장한다. 인식하지 못한 오류의 원문은 공개하지 않는다. CLI 버전·옵션 확인 성공만으로 계정의 모델 사용 권한까지 검증되지는 않는다. 2026-11-17 데모 환경에서는 `gpt-6.1-sol`이 ChatGPT 계정에서 거부되었고, CLI 기본 선택인 `gpt-6-luna`의 실제 요청 성공을 확인해 데모 설정에 반영했다.

## 테스트

일반 테스트는 전체 제어 흐름과 CLI 계약을 모의 worker·임시 파일·프로세스 mock으로 검사한다. 실제 Codex, GitHub, 제품 테스트를 호출하지 않는다.

```bash
python -B -m unittest discover -s workflow/runtime/tests -v
```

실제 데모 테스트 및 Linux 격리 검증은 일반 Unit Test와 분리한다. Codex·인증·네트워크는 필요 없고 Bubblewrap은 필요하다. 정상 데모, 깨진 후보, 없는 프로그램, 시간 초과, 선택 검사 미실행, 원본/환경/네트워크 격리, 인수 주입 방지, 0개 검사 차단을 실행한다.

```bash
WORKFLOW_DEMO_TESTS=1 python3 -B -m unittest discover \
  -s workflow/runtime/tests/integration -p test_demo_validation.py -v
```

통합 CLI부터 모의 PR까지 확인하는 TEMP 검증은 다음과 같다. 외부 임시 Git 저장소에 계산기 복사본과 기준 Commit을 만들고 Codex worker만 모의 객체로 교체한다. Unit/E2E 명령과 Bubblewrap은 실제 실행하며 GitHub·원격 전송은 모의 실행한다. 정상 흐름과 Unit 실패 시 중단을 검증한다. 원본 테스트 프로젝트와 저장소는 수정하지 않는다.

```bash
WORKFLOW_DEMO_TESTS=1 python3 -B -m unittest discover \
  -s workflow/runtime/tests/integration -p test_demo_workflow.py -v
```

실제 Codex smoke test는 별도 디렉터리에 두었으며 일반 discover 대상에 포함되지 않는다. 아래 환경 변수는 인증정보가 아닌 확정 설정·저장소 경로다. 명시하면 실제 호출과 비용 발생을 허용하는 것으로 취급한다.

```bash
WORKFLOW_CODEX_SMOKE_CONFIG=/absolute/path/project.json \
WORKFLOW_CODEX_SMOKE_REPO=/absolute/path/repository \
python -B -m unittest discover -s workflow/runtime/tests/integration -v
```

미지정 시 실제 테스트는 제외된다. readonly 작업 요청으로 실제 종료와 무변경 결과를 확인하며, 일반 테스트 통과를 실제 Codex 검증으로 보고하지 않는다.

## 구현 당시 확인과 다음 단계

2026-11-13 현재 Windows와 WSL PATH에서 Codex CLI를 찾지 못했다. 공식 인터페이스와 모의 테스트는 확인했지만 실제 CLI 실행, 계정 인증, 모델 접근, 파일시스템·네트워크 sandbox 강제는 검증하지 못했다. PRJ의 기준 문서·지침·테스트 환경·CLI 버전·모델은 미확정 상태다.

2026-11-17에는 데모 설정으로 실제 Codex 실행과 독립 검증을 연결해 `completed`, `validation_status=passed`를 확인했다. 원본 데모의 Unit 4개와 CLI E2E 4개가 격리 환경에서 통과했다. 별도 데모 통합 검증에서는 결함 후보, 실행 불가, 시간 초과, 미실행, 격리, 0개 검사 차단을 확인했다. PRJ 설정·의존성은 이 확인 대상에 포함하지 않는다.

독립 테스트 실행기와 별도 PR 게시 모듈이 연결되었다. 게시 모듈은 실행 ID·설정 해시·기준 스냅샷·검사한 후보 해시를 다시 확인한다. 2026-11-17 WSL에서는 `gh`가 없어 실제 GitHub 인증·Push·PR 생성은 검증하지 않았다. 다음 단계는 담당자가 준비한 Git 기준 상태·GitHub 인증·브랜치 보호 환경에서 명시적인 수동 게시 시험을 진행하는 것이다. Issue 접수, 제품 테스트의 충분성, 외부 서비스 준비, 장기 로그 보존, 자원 한도는 추가 검토가 필요하다.

통합 실행 추가 후 일반·로컬 모의 테스트 176개와 별도 데모 검증 11개가 통과했다. TEMP 통합 정상 시나리오에서 Unit 4개·CLI E2E 4개를 실제 실행하고 모의 PR 요청까지 도달했다. 이번 통합 검증에서는 실제 Codex 호출·GitHub 인증·원격 Push·PR 생성을 수행하지 않았다. 현재 원본 계산기는 Git 미등록 상태이므로 기본 설정으로 생성·테스트가 성공하더라도 게시 단계는 `user_changes`로 차단된다. 담당자가 기준 상태를 준비하기 전에는 이 제한을 우회하거나 기존 파일을 자동 Commit하지 않는다.
