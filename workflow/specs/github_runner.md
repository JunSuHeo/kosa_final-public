# GitHub Actions self-hosted runner 설정

Issue workflow는 저장소에 등록한 macOS ARM64 self-hosted runner를 대상으로 하며, `[self-hosted, macOS, ARM64, workflow-isolated]` 라벨을 사용합니다. GitHub가 앞의 세 기본 라벨을 추가하고 `workflow-isolated`는 사용자가 지정합니다. Codex 실행과 게시 runtime은 macOS ARM64를 지원합니다. 검사 격리는 macOS `sandbox-exec`를 사용하며, 도구가 없거나 격리 점검에 실패하면 host에서 실행하지 않고 차단합니다.

## 1. Runner 등록

저장소 관리자 권한이 있는 사람은 GitHub 저장소의 **Settings → Actions → Runners → New self-hosted runner**에서 macOS와 ARM64를 선택합니다. GitHub 화면에 표시되는 다운로드·압축 해제·등록 명령을 해당 호스트에서 실행합니다. 등록 토큰은 짧은 기간만 유효하므로 화면에서 발급한 값을 사용하고, 문서·Issue·로그에 복사하지 않습니다.

GitHub 화면에서 제공한 등록 명령에 사용자 라벨 `workflow-isolated`를 지정합니다. 명령은 다음 형태입니다. URL은 대상 비공개 저장소로 바꿉니다. `TOKEN_FROM_GITHUB_UI`는 GitHub가 안내한 실제 등록 토큰으로 바꿉니다.

```bash
./config.sh --url https://github.com/example-owner/example-repository \
  --token TOKEN_FROM_GITHUB_UI \
  --labels workflow-isolated
```

`runner`는 macOS 호스트에 미리 만들어 둔 로컬 계정 이름의 예시이며, `svc.sh`가 계정을 생성해주지는 않습니다. 현재 runner 파일을 소유한 로그인 계정으로 서비스를 설치하려면 다음처럼 지정합니다.

```bash
sudo ./svc.sh install "$(whoami)"
sudo ./svc.sh start
sudo ./svc.sh status
```

이 디렉터리에서 명령을 실행하는 계정이 `sangwon`이라면 서비스도 `sangwon`으로 실행됩니다. 별도 `runner` 계정을 사용하려면 먼저 계정을 만들고, runner 파일·작업 디렉터리를 해당 계정이 접근할 수 있도록 준비한 뒤 그 계정의 Codex CLI 로그인도 설정해야 합니다. 토큰은 GitHub 화면에서 발급된 값을 사용하고 문서·Issue·로그에 복사하지 않습니다. 저장소의 Actions runner 목록에서 다음 라벨이 모두 표시되는지 확인합니다.

```text
self-hosted
macOS
ARM64
workflow-isolated
```

서비스 계정은 일반 개발 계정과 분리하고, runner를 이 계정으로 실행합니다. 조직 runner group을 사용한다면 이 저장소가 해당 group을 사용할 수 있도록 접근 정책도 확인합니다.

## 2. 호스트 도구 설치

실행할 프로젝트 설정에 맞는 도구를 runner의 `PATH`에 설치합니다. Linux에서는 Bubblewrap, macOS에서는 시스템 `sandbox-exec`로 검사 프로세스를 격리합니다. `sandbox-exec`는 Apple이 deprecated 처리했으므로 macOS 업데이트에서 사라지거나 정책 실행에 실패하면 검증이 fail-closed로 중단됩니다. POSIX `fcntl.flock`은 Linux와 macOS에서 모두 사용합니다.

| 도구 | 용도 |
| --- | --- |
| Python 3.12 이상 | Workflow 런타임과 Python 테스트 |
| Git, GitHub CLI `gh` | checkout 상태·저장소 권한 확인과 게시 |
| Bubblewrap `bwrap` 또는 macOS `sandbox-exec` | 후보 코드의 격리 테스트. macOS 도구는 deprecated이며 실행 전 격리 capability를 확인합니다. |
| Codex CLI | Issue 분석과 승인된 작업 실행. 선택한 프로젝트 JSON에 적힌 버전과 일치해야 합니다. |
| `uv` | PRJ PostgreSQL 백엔드 검사를 활성화할 때만 필요 |
| PostgreSQL 서버 및 클라이언트 바이너리 | `backend-postgresql` 검사를 다시 활성화할 때만 필요. `initdb`, `pg_ctl`, `createdb` 필요 |

현재 `sandbox.json`의 calculator 테스트는 Python 표준 라이브러리만 사용합니다. 프로젝트 설정에서 테스트나 브라우저 E2E를 추가·활성화하면 그에 필요한 도구와 서비스도 준비해야 합니다. 실행 전 격리 capability 점검은 Linux Bubblewrap 또는 macOS `sandbox-exec`에서 수행하고, 통과하지 못하면 workflow는 host에서 테스트를 대신 실행하지 않고 실패 처리합니다.

## 3. Codex CLI 인증

별도의 Codex ID용 GitHub 변수는 없습니다. Codex CLI가 설치된 것만으로 인증되는 것도 아닙니다. CLI를 실행하는 **동일한 runner 계정**으로 공식 Codex 로그인 절차를 완료해야 하고, 해당 계정이 선택한 프로젝트 설정의 모델을 사용할 수 있어야 합니다. Codex CLI runtime은 Linux/WSL과 macOS ARM64를 지원합니다. 로그인 안내는 [OpenAI Codex 인증 문서](https://developers.openai.com/codex/auth)를 참고합니다.

이 workflow는 Codex 프로세스에 `HOME` 등 제한된 환경만 전달하며 `OPENAI_API_KEY`와 GitHub token을 전달하지 않습니다. 따라서 `OPENAI_API_KEY`를 Repository Variable이나 Secret에 추가해도 현재 코드에서는 Codex 인증에 사용되지 않습니다. runner 관리자 계정에서만 로그인해두고 Actions 서비스가 다른 계정으로 실행되면 로그인 상태를 찾지 못합니다.

## 4. GitHub Actions 설정과 연결

Runner는 workflow 파일의 다음 설정을 만족해야 합니다.

```yaml
runs-on: [self-hosted, macOS, ARM64, workflow-isolated]
```

Issue workflow가 실행되려면 기본 브랜치에 workflow와 런타임 코드가 push되어 있어야 하며, Repository Variables와 Secrets도 설정되어야 합니다. 변수·토큰 권한은 [GitHub 저장소 설정 안내](github_settings.md)를 따릅니다. 대상 설정 경로는 `WORKFLOW_CONFIG_PATH`에 넣습니다.

| 대상 | `WORKFLOW_CONFIG_PATH` |
| --- | --- |
| 제품 `PRJ/` | `workflow/config/projects/prj.json` |
| 테스트용 `sandbox/` | `workflow/config/projects/sandbox.json` |

Issue 등록 시 먼저 분석 계획을 댓글로 올립니다. 저장소 `Write` 권한이 있는 사람이 `/approve`를 댓글로 남겨야 코드 생성·검증 단계로 진행합니다. PR 유형과 테스트 실패 게시 여부는 프로젝트 정책을 따르며, PRJ는 보호 규칙 없이 실패 결과를 기록한 뒤 일반 PR을 만듭니다. 정책의 기본값과 권한 전제는 [게시 안내](../runtime/PUBLISHING.md)를 확인하세요. 실행 상태와 오류는 GitHub의 **Actions** 탭과 해당 Issue 댓글에서 확인합니다.

## 5. PRJ 테스트 제한

현재 `prj.json`은 PostgreSQL 백엔드 검사에 `run_if: never`를 지정해 Actions 검증에서 제외합니다. 브라우저 E2E도 비활성 상태입니다. 따라서 통과한 프로젝트 검사가 없으면 runtime의 fail-closed 정책에 따라 검증과 게시가 차단됩니다. 게시를 다시 활성화하기 전에 DB 비의존 검사를 설정해야 합니다.

`backend-postgresql` 검사는 현재 Linux 전용입니다. 다시 활성화하려면 Linux runner와 Bubblewrap을 사용하도록 workflow/runtime 설정도 함께 전환하고, Python 3.12 이상, `uv`, `PRJ/backend/uv.lock`에서 준비한 오프라인 캐시, PostgreSQL 서버 및 클라이언트 바이너리를 준비해야 합니다. 검사는 임시 `studio_test` PostgreSQL을 샌드박스 내부 Unix 소켓으로 실행하며, 호스트 DB나 외부 DB 접속은 사용하지 않습니다.

## 6. 보안 운영

Issue 본문은 외부 입력이고 Issue 등록 단계에서 Codex 분석이 시작되므로 개인 개발 PC나 다른 중요 자격 증명이 있는 장비를 runner로 등록하지 않습니다. 저장소 전용의 격리 macOS 호스트, 제한된 서비스 계정, 최소 권한의 게시 토큰을 사용합니다. 가능한 경우 작업마다 폐기되는 ephemeral VM을 사용합니다. 다만 현재 코드는 Codex 인증을 자동으로 주입하거나 ephemeral runner를 bootstrap하지 않으므로, ephemeral runner를 채택하면 신뢰할 수 있는 별도 인증 준비 경로가 필요합니다.

Runner 등록·Codex 로그인·모델 접근을 이 문서가 자동으로 수행하지 않습니다. 실제 Issue를 열기 전에 권한이 제한된 저장소나 검증용 Issue로 분석 댓글과 `/approve` 이후 실행을 확인하세요.
