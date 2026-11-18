# AI 개발 자동화 시스템 사전 환경 분석 및 기술 결정

**분석 기준 문서:** `workflow/specs/requirements.md`, `workflow/specs/architecture.md`

**확인 시점:** 2026-11-13
**범위:** 현재 저장소·도구 확인과 구현 방향 제안. 자동화 코드, workflow, GitHub 설정을 구현하거나 변경하지 않는다.

## A. 현재 환경 분석

### 저장소 상태

- Git 저장소 루트는 `/root/work/kosa_final`이며, GitHub 원격 `origin`이 설정되어 있다.
- 현재 브랜치는 `main`이고 확인 시점의 `origin/main`과 일치한다.
- WSL 내부 Git 기준, 추적 중인 파일에는 변경이 없고 다음 설계 문서 두 개가 미추적 상태다.
  - `workflow/specs/requirements.md`
  - `workflow/specs/architecture.md`
- 현재 작업에서는 파일을 수정하거나, commit·push·Issue·PR 작업을 수행하지 않았다.

### 디렉터리 구조와 프로젝트 도구

| 경로 | 확인된 구조 및 파일 이름 |
| --- | --- |
| 저장소 루트 | `PRJ/`, `workflow/`, `README.md` |
| `PRJ/` | `backend/`, `frontend/`, `docs/`, `scripts/`, `infra/`, `prompts/`, `artifacts/` |
| `workflow/` | `README.md`, `specs/`. 자동화 런타임과 프로젝트 설정은 아직 없음 |
| `.github/` | 디렉터리가 없으며 저장소 내 Actions workflow가 없음 |

`PRJ/`의 파일 이름과 manifest에서 확인된 사항은 다음과 같다.

- Backend는 Python `>=3.12`와 pytest를 선언한다. `backend/tests/`에 테스트 파일 5개가 있다.
- Frontend는 TypeScript/Vite 프로젝트다. script 이름은 `dev`, `build`, `test:e2e`이고 Playwright 의존성을 선언한다. `frontend/tests/`에 테스트 파일 5개가 있다.
- Frontend manifest에서 별도 Unit Test 실행기는 확인되지 않았다.
- `frontend/node_modules/`와 `backend/.venv/`는 없다. 의존성 설치 상태는 확인되지 않았다.
- 프로젝트 코드, 문서 본문, 환경 파일의 인증정보는 조사에 사용하지 않았다.

### 실행 환경 도구

| 환경 | 확인한 도구 |
| --- | --- |
| Windows PowerShell 5.1 | Git 2.41, Node.js 20.9, npm 10.4, Python 3.12, uv 0.13, Docker CLI 24 |
| WSL Ubuntu | Git 2.53, npm 10.4, Python 3.14, uv 0.12, Docker CLI 29 |

`gh`, `codex`, `act`는 Windows와 WSL의 PATH에서 찾지 못했다. WSL에서는 `node`도 찾지 못했지만 `npm`은 실행됐다. Docker CLI는 있으나 daemon 접속은 확인되지 않았다. Codex CLI가 로컬에서 보이지 않아도 GitHub Actions에서 별도 실행 도구를 제공할 수 있지만, 그 실행 경로는 아직 구성·검증되지 않았다.

GitHub 원격이 존재한다는 사실만 확인했다. repository Settings, Actions 사용 가능 여부·한도, Secrets, branch protection, GitHub 인증 및 Codex 계정·모델 접근은 확인하지 않았다. 인증정보는 조회·요청·출력하지 않았다.

PowerShell에서 WSL 경로를 통해 실행한 Git은 `Zone.Identifier` 경로에 대해 대량 변경처럼 보이는 결과를 냈다. WSL 내부 Git의 결과를 기준으로 판단했으며, 이후 Git 상태·diff 확인은 한 환경의 Git을 일관되게 사용하는 편이 안전하다.

## B. 기술 결정 목록

아래 권장안은 아키텍처를 구현 관점에서 구체화하기 위한 제안이다. 계정·조직 권한·비용 등 저장소 외부 사항은 확인되지 않았다.

| 항목 | 현재 상태 | 권장 선택 | 선택 이유 | 추가 확인사항 |
| --- | --- | --- | --- | --- |
| 자동화 실행 환경 | Actions workflow가 없고 workspace는 WSL 경로 | GitHub Actions의 일회성 Linux runner | 실행별 격리와 이벤트 기반 운영에 맞고 Windows·WSL 도구 차이를 줄인다 | Hosted runner 이용 가능 여부, 사내망·Docker·비용 요건 |
| Codex 실행 | Codex CLI가 로컬 PATH에 없음 | 고정 버전의 공식 Codex GitHub Action을 사용해 Actions에서 CLI 실행 | 로컬 설치에 의존하지 않고 아키텍처의 변경 생성 역할을 구현할 수 있다 | 고정 참조, sandbox, API 인증 격리, 사용 모델·한도 |
| 제어 프로그램 | Windows Python 3.12, WSL Python 3.14 | Python 3.12 고정, 표준 라이브러리 중심의 작은 제어 프로그램 | PRJ가 Python `>=3.12`를 선언하며 JSON·경로·상태 검증에 상시 서비스가 필요 없다 | 하나의 실제 실행 환경 선정 및 버전 재현 확인 |
| 프로젝트 설정 | 설정 파일·schema 없음 | 버전을 포함한 JSON. 프로젝트 값은 `workflow/config/projects/`, schema는 `workflow/schemas/` | 별도 파서 의존성을 줄이며 Actions workflow YAML과 목적이 분리된다 | 필수 필드, 버전 호환성, 비밀정보 참조 형식 |
| Issue 감지·승인 | workflow와 인증 미구성 | 권한 있는 담당자의 승인 표시를 시작 조건으로 하고 수동 실행을 보조로 제공 | 임의 공개 Issue로 인한 불필요한 실행과 비용을 줄인다 | 승인 가능한 행위자, 중복·수정·종료 Issue 처리 |
| Branch 규칙 | 전용 규칙 없음. 현재 local branch는 `main` | `automation/issue-<번호>` 제안 | 작업 식별과 중복 확인이 단순하다 | 원격 기본 브랜치, 기존 PR 갱신과 재실행 규칙 |
| Unit Test·E2E | Backend는 pytest 선언, frontend는 Playwright 및 `test:e2e` 선언 | Backend pytest·현재 Playwright를 우선 확인. Frontend Unit Test는 필요 시 Vitest 검토 | 이미 선언된 도구를 우선하고 확인 전 새 도구를 추가하지 않는다 | 실제 검사 명령, 테스트 종류·필수 조건, E2E 환경 |
| GitHub API·CLI | `gh`가 로컬 PATH에 없음 | Actions runner에서 API 호출 수단을 검증해 하나로 표준화. `gh`를 쓰면 버전·설치를 고정 | 로컬과 runner 환경이 다르므로 CLI 존재를 가정할 수 없다 | runner의 `gh` 가용성, API 권한·pagination 필요성 |
| Codex 변경 전달 | 산출물 전달 기능 없음 | AI job에서 패치와 실행 ID·내용 해시를 artifact로 전달. 별도 검증·게시 job에서 재적용 | Codex와 테스트에 GitHub 쓰기 권한을 주지 않는다 | artifact 보존·크기, 신규 파일·binary patch 처리와 무결성 확인 |
| 검증 결과·PR | 자동 저장 경로 없음 | Actions job 결과·요약과 짧은 보존 artifact를 사용. PR에 검사 결과·실행 링크·SHA 기록 | 별도 DB 없이 작업 추적을 시작할 수 있다 | 조직 로그·artifact 보존 정책, 병합 필수 검사 방식 |
| GitHub Token | Actions 권한·Secrets 미확인 | job별 최소 권한. 자동 PR 후속 workflow가 필요하면 단일 저장소 GitHub App 검토 | Codex와 테스트에는 쓰기 권한을 주지 않는다 | `GITHUB_TOKEN` 이벤트 승인 동작, Issue·Contents·PR 권한, 보호 규칙 |
| 실패 재시도 | 횟수·한도 미결정 | 범위 안의 코드 결함에 한해 최대 1회 수정 후 전체 필수 검사 재실행 제안 | 반복 비용과 무한 재시도를 막으면서 한 번의 복구 기회를 둔다 | 시간·비용 한도, 환경 실패·flaky test 구분, Draft 허용 |
| 로그·결과 보존 | 구체 보존 정책 없음 | Actions 로그·요약을 기본 기록으로 삼고 artifact는 만료 기간을 설정해 최소 보존 | 상시 저장소를 추가하지 않아 초기 복잡도가 낮다 | 조직 retention 제한, 민감정보 필터와 보존 기간 |
| Spec Kit·MCP | 사용 구성 없음 | 초기에는 추가하지 않음 | 기존 설계문서·checkout·API 호출로 요구를 충족할 수 있다 | 반복되는 명세 분해 또는 외부 지식 연동이 실제 문제인지 추후 평가 |

## C. 미결정 사항

### 실제 구현·통합 전에 결정할 사항

- Actions runner와 고정 실행 환경, Codex Action·CLI 버전, sandbox·API 인증 수단, 사용할 모델·실행 한도
- Actions 실행 가능 여부와 조직 비용·네트워크·저장소 정책
- 자동화 대상 Issue 표시와 승인 행위자, 중복·재실행·기존 PR 처리
- 프로젝트 schema 필수값: 저장소·기준 branch, 허용 경로, 기준 문서, 설치·검사 명령
- Backend 및 Frontend Unit Test, E2E의 실행 명령·적용 범위·필수 여부. Frontend Unit Test 도구의 필요성
- PR 게시용 GitHub 인증과 최소 권한, PR 후속 CI가 자동으로 시작되어야 하는지 여부
- 두 설계 문서가 미추적 상태인 점을 고려한 구현 branch와 문서 보존·추적 계획

### 초기에 미뤄도 되는 사항

- Spec Kit, MCP, 자동 리뷰 에이전트 도입
- 중앙 reusable workflow와 여러 저장소 동기화
- 장기 감사 저장소·분석 UI·로그 보존 세부 조정
- 실제 실패 데이터가 생긴 뒤의 재시도 횟수·성능 최적화

## D. 단계별 구현 계획

아래 경로는 향후 구현을 위한 제안이며 현재 존재하지 않는다.

| 단계 | 목적·주요 작업 | 예정 파일·디렉터리 | 선행 조건 | 완료 기준·검증 방법 |
| --- | --- | --- | --- | --- |
| 0. 환경·정책 확정 | Runner, Codex 실행, GitHub 권한·담당자 결정 | 파일 변경 없음 | 저장소 관리자·운영 담당자 확인 | 비용·권한·branch protection·후속 CI 조건이 승인됨 |
| 1. 설정과 사전 검사 | Project schema, 버전, 설정 검증기 | `workflow/schemas/`, `workflow/config/projects/`, `workflow/runtime/` | PRJ 기준 branch·문서·검사 계약 수집 | 정상·누락·경로 이탈 설정을 local fixture로 검사. GitHub·Codex 호출 없이 실패가 보고됨 |
| 2. Issue 접수 | 승인 Issue 감지, 설정·권한·중복 검증, 작업 명세 생성 | `.github/workflows/`, `workflow/runtime/` | 0·1단계, Issue trigger 정책 | 미등록·닫힌·중복 Issue와 권한 없는 요청은 Codex 전에 차단됨 |
| 3. 격리·Branch 준비 | 기준 SHA 고정, 임시 작업 공간과 local branch 생성 | `workflow/runtime/` | 기준 branch·명명 규칙 | Test용 Git 저장소에서 사용자 변경 보존, 기존 브랜치 충돌·금지 경로 차단 확인 |
| 4. Codex 변경 생성 | Issue 분석, 설계문서 확인·수정, 최소 코드 변경, 패치 수집 | `workflow/prompts/`, `workflow/schemas/`, Actions 설정 | Action·sandbox·산출물 계약 승인 | 모호한 Issue는 중단하고, 승인된 범위의 패치만 식별자·기준 SHA와 함께 생성 |
| 5. 독립 검증 | 별도 job에서 패치 적용, 등록된 Unit Test·E2E·CI 실행 | `workflow/runtime/`, project config | 명령·필수 조건·환경 확정 | 통과·실패·실행 불가·해당 없음 구분. 0개 검사·timeout·검사 후 tree 변경을 통과 처리하지 않음 |
| 6. 실패 처리 | 제한 수정, 전체 재검사, 차단 보고 | `workflow/prompts/`, `workflow/runtime/` | 재시도·시간·Draft 정책 | 설정된 횟수만 수정하며 재검사 통과 전 정상 PR 금지. 환경·범위·권한 실패는 사람에게 전달 |
| 7. PR 게시 | 검증 결과 확인, 전용 게시 job으로 branch·PR 생성 | `.github/workflows/`, `workflow/runtime/`, PR template | 인증·권한·필수 상태 검사 확인 | 임시 저장소에서 검증한 동일 변경만 PR로 게시, 후보 코드의 게시 job 실행 금지, 승인·병합 호출 없음 |
| 8. 통합·재사용 검증 | 시험 Issue부터 PR까지 실행하고 PRJ 및 별도 프로젝트에 적용 | 각 project 설정·공통 workflow | 선행 단계 통과와 별도 운영 승인 | 중복·권한·입력 변경·branch protection을 확인하고 두 project가 공통 코드 복제 없이 설정만으로 동작 |

## E. 첫 번째 구현 작업 제안

첫 코딩 작업은 **공통 프로젝트 설정 schema와 오프라인 사전 검사기**로 한정하는 편이 안전하다. 제안 파일은 다음과 같다.

- `workflow/schemas/project.schema.json`
- `workflow/config/projects/prj.json.example`
- `workflow/runtime/validate_config.py`
- `workflow/runtime/tests/test_validate_config.py`

사전 검사기는 저장소·프로젝트 ID, 기준 branch, 허용 경로, 설계문서 위치, 필수 Unit Test·E2E 명령과 권한 선언의 누락·오류를 검사한다. 이 작업에는 GitHub API, Codex 실행, Token, branch 생성, Actions workflow 생성을 넣지 않는다.

완료 조건은 유효한 fixture 설정이 통과하고 필수값 누락·경로 이탈·지원하지 않는 schema 버전이 차단되는 것이다. 다음 단계는 별도 Issue에서 read-only Issue 접수를 추가하는 것이다.

구현은 기존 설계 문서와 untracked 파일을 보존할 branch에서 진행해야 한다. 문서의 포함·추적 계획을 먼저 정하고, 설계 문서를 정리하거나 덮어쓰지 않는다.

## F. 위험 요소

| 위험 | 대응 |
| --- | --- |
| 설계 문서가 untracked라 branch 작업 중 유실·혼입될 수 있음 | 문서를 보존하고 추적하는 계획을 먼저 세우고, 구현은 별도 branch에서 수행 |
| PowerShell의 WSL 경로 Git 상태가 `Zone.Identifier` 변경처럼 나타날 수 있음 | WSL 내부 Git 등 한 환경의 Git을 일관되게 사용해 status·diff 확인 |
| `.github/workflows/`와 Actions 정책이 아직 없음 | remote 존재만으로 Actions 권한·Secrets·billing·승인을 추측하지 말고 관리자가 확인 |
| 로컬 `gh`·`codex`가 없고 WSL Node도 확인되지 않음 | 고정된 runner에서 필요한 도구를 검증하고 local·CI 실행 환경을 일치시킴 |
| 의존성 디렉터리가 없고 Windows·WSL의 Node·Python 버전이 다름 | runner 버전을 고정하고 lockfile 기반 환경이 만들어지는지 별도 검증 |
| Docker daemon 사용 여부 미확인 | DB·서비스 기반 테스트를 실행할 runner 조건을 통합 전 확인 |
| GitHub Token으로 생성한 PR의 후속 CI가 자동 실행되지 않을 수 있음 | 시험 저장소에서 확인하고, 자동 후속 CI가 필요하면 저장소 범위를 제한한 GitHub App 검토 |
| 테스트·설치 스크립트가 코드와 API Key를 읽을 수 있음 | 테스트는 쓰기 Token·Codex Key가 없는 일회성 job에서 실행하고 검사한 내용과 게시 tree가 같은지 확인 |
| AI 산출물을 그대로 신뢰하면 테스트나 설정을 약화시킬 수 있음 | 신뢰하는 기준의 정책으로 검사하고 실패·누락·0개 실행·실행 불가를 통과로 처리하지 않음 |
| 로그·artifact에 코드·개인정보·인증값이 남을 수 있음 | 기록을 최소화하고 민감정보를 필터링하며 retention을 명시적으로 설정 |

분석은 문서와 환경 상태를 바탕으로 한 구현 제안이다. GitHub 인증·repository Settings를 조회하지 않았고, 인증정보를 요청·출력하지 않았다. 자동화 코드·workflow·패키지·Git 설정은 추가하지 않았으며, commit·push·Issue·PR 생성 및 제품 테스트도 수행하지 않았다.
