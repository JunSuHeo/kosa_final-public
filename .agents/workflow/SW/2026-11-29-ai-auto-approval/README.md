# ai-auto Issue 자동 실행 승인

- 날짜: 2026-11-29 (Asia/Seoul)
- 상태: 완료
- 담당 팀원: SW
- 참여 AI 에이전트·담당 범위: Codex(root), GitHub Issue workflow와 runtime·테스트·운영 안내·PR 게시. review_ai_auto, 읽기 전용 코드 리뷰와 [리뷰 기록](agents/review.md).
- 공동 작업의 대표 기록·관련 팀원 기록: 해당 없음
- 요청·목표: `ai-auto` 라벨만으로 Issue 분석을 시작하고 추가 질문이 없는 준비된 계획을 자동 승인한다.
- 완료 조건: 라벨 추가 이벤트, 질문 대기와 `/plan` 해결 후 자동 승인, Actions 단계 간 승인 복구, 라벨 제거·변조 차단, 중복 실행 방지가 검증된다. `ai-plan`의 수동 승인 동작은 유지한다.
- 변경 범위: `.github/workflows/issue-approval.yml`, `workflow/runtime/issue_workflow.py`, 관련 테스트·운영 안내.

## 읽은 근거

- 루트 `AGENTS.md`, `.agent-local.md`, `PRJ/AGENTS.md`, `PRJ/rules/project.md`, `.agents/workflow/README.md`
- `workflow/README.md`, `workflow/runtime/README.md`, `workflow/runtime/ISSUE_APPROVAL.md`, `workflow/specs/github_settings.md`, `workflow/specs/requirements.md`
- `workflow/runtime/issue_workflow.py`, `issue_github.py`, `publish.py`, `branch_rules.py`, `tests/test_issue_workflow.py`
- 사용 스킬: using-superpowers, caveman, brainstorming, systematic-debugging, writing-plans, test-driven-development, verification-before-completion. 전달된 hive-images 지침은 이미지 작업이 없어 호출하지 않는다.

## 설계와 판단

- 변경 전 Actions job은 `ai-plan`만 허용하고 라벨 추가 이벤트를 받지 않았다. runtime과 Actions output도 사람의 `/approve` 댓글만 승인·실행 티켓으로 인정했다.
- 기존 계획·상태 HMAC 및 재검증 흐름에 자동 승인 종류를 추가한다. 별도의 봇 `/approve` 댓글을 위조하는 방식은 기존 사람 댓글 계약과 충돌하므로 사용하지 않는다.
- `ai-auto`가 현재 API 응답에 있고 계획 검증에서 질문·필수 결정이 없을 때만 자동 승인한다. 승인 시점과 실행·게시 경계에서 라벨을 다시 확인한다.
- 자동 승인자는 브랜치명으로도 안전한 `ai-auto`로 기록하고, 승인 근거는 서명된 상태와 검증된 봇 계획 댓글로 남긴다.
- PR 리뷰·병합 정책은 기존 계약을 따른다. 이번 요청의 approve는 Issue 계획 실행 승인이다.
- 현재 checkout에서 관련 파일만 수정한다. 기존 스킬 스크립트 변경은 작업 범위 밖이다.

## 계획

1. 시작·라벨 추가·질문·Actions 분리 실행 및 취소·중복 회귀 테스트를 작성하고 실패를 확인한다.
2. `ai-plan` 또는 `ai-auto` 시작 조건, 자동 승인 티켓·재검증, Actions output을 구현한다.
3. 대상 테스트와 workflow runtime 전체 Mock 테스트를 실행하고 운영 문서를 갱신한다.

## 변경 파일

- `.github/workflows/issue-approval.yml`: 두 라벨 중 하나로 시작, `issues.labeled` 추가.
- `workflow/runtime/issue_workflow.py`: 현재 라벨과 준비된 계획으로 자동 승인, 승인 종류별 재검증, 새 승인 티켓만 Actions output 전달.
- `workflow/runtime/tests/test_issue_workflow.py`: 12개 회귀 테스트 추가. 단독 라벨·기존 계획·질문 해결·단계 분리·위조 및 제거·중복·실제 모의 게시 경로 확인.
- `workflow/README.md`, `workflow/runtime/README.md`, `workflow/runtime/ISSUE_APPROVAL.md`, `workflow/specs/github_settings.md`, `workflow/specs/requirements.md`: 라벨별 실행 승인, 운영 이벤트, 자동 승인 기록과 PR 리뷰 계약 반영.
- `.agents/workflow/SW/README.md`: 이 작업 기록 연결.

## 검증

| 실행 위치 | 명령·확인 방법 | 결과 | 근거·한계 |
| --- | --- | --- | --- |
| 저장소 루트, WSL Python 3.14.4 | 새 핵심 회귀 테스트 5개 | 예상 실패 확인 | 기존 구현에서 자동 승인·라벨 추가·Actions output·모의 게시가 누락되어 5개 모두 실패 |
| 저장소 루트, WSL Python 3.14.4 | `python3 -B -m unittest workflow.runtime.tests.test_issue_workflow` | 64개 통과 | 실제 controller·HMAC 복구·로컬 orchestrator·모의 publisher 사용. GitHub·Codex live 호출 없음 |
| 저장소 루트, WSL Python 3.14.4 | `python3 -B -m unittest discover -s workflow/runtime/tests -p 'test_*.py'` | 282개 중 279개 통과, 3개 실패 | 변경하지 않은 test_runner 영역의 기존 테스트 1 failure·2 errors. 아래 상세 기록 |
| 저장소 루트 | 기존 실패 3개만 독립 재실행 및 `git diff --exit-code -- workflow/runtime/test_runner.py workflow/runtime/tests/test_test_runner.py` | 같은 3개 실패, 해당 파일 diff 없음 | Issue controller 테스트를 실행하지 않아도 재현됨 |
| 저장소 루트 | PyYAML BaseLoader로 Actions YAML 구조·이벤트·두 라벨 조건 확인 | 통과 | 정적 확인. 실제 GitHub Actions 실행은 미확인 |
| 저장소 루트 | Python AST 파싱 및 수정 문서의 상대 링크 확인 | 통과 | Python 파일 2개, 로컬 문서 링크 25개 확인 |
| 저장소 루트 | `git diff --check` | 통과 | 공백·충돌 마커 검사 |

### 전체 런타임의 기존 실패

- `test_macos_backend_check_uses_native_launcher_and_private_scratch`: Linux에서 macOS 분기를 mock하며 `/private/tmp`를 만들지 않아 `FileNotFoundError`.
- `test_macos_backend_setup_failure_is_unavailable`: 같은 `/private/tmp` 전제 문제로 `FileNotFoundError`.
- `test_validation_works_when_temp_parent_has_a_symlink_alias`: 기존 테스트의 `factory(dir=alias, **kwargs)`와 구현이 전달하는 `dir=None`이 중복되어 검증 준비 실패. 관련 제품·테스트는 이 작업에서 수정하지 않았다.

## 단계별 인계

- 조사: 시작 조건·사람 댓글 전용 승인·Actions output의 세 경계를 확인했다.
- 구현: 자동 승인에는 서명된 `mode=auto` 티켓을 사용하며 사람 `/approve` 댓글을 생성하지 않는다. 이미 게시된 수동 계획 Markdown의 서명 검증을 유지한다.
- 검증: Issue 64개 통과와 YAML 정적 검증. 전체 runtime의 기존 실패 3개는 Issue 변경과 독립적으로 재현·기록했다.

## PR 준비

- 사용자 요청: `pr날려줘.` — 커밋·브랜치 push·PR 작성 승인.
- 브랜치: `feat/ai-auto-approval`, 대상 `main`.
- 기준: 최신 `origin/main`의 `d18b273232d5dd2e5f74a7cba30b74217f1569d2`. 이전 작업 PR #32는 이미 병합되어 새 브랜치를 만들었다.
- PR 준비 시 전체 runtime 282개를 재실행했다. 동일한 기존 실패 3개 외에는 통과했다.
- 독립 코드 리뷰: 수정 필요 발견 사항 없음. [리뷰 기록](agents/review.md) 참조.
- 리뷰에서 판단하지 않은 실제 원격 실행, 라벨 부여 역할 관리, 기존 분산 실행 경쟁과 기존 test_runner 실패는 이번 PR의 보증 범위에 포함하지 않는다.
- 저장소의 PR 양식 파일은 현재 checkout에 없어 변경 동작·실행 검증·기존 실패·미확인 내용을 본문에 작성한다.
- PR 게시 결과: [PR #33](https://github.com/JunSuHeo/kosa_final-public/pull/33), 일반 PR, `feat/ai-auto-approval`에서 `main`으로 제출. 구현 커밋 `b849958`.
- 원격 브랜치 push와 PR 생성은 실제 GitHub 응답으로 확인했다. 모델·제품 실행 검증과 구분한다.

## 결과·인계

- 완료 내용: `ai-auto` 단독으로 분석·자동 실행 승인, 질문 대기와 해결 후 승인, 라벨 추가, 승인 단계 복구와 재검증, 운영 안내 갱신.
- 미확인·남은 작업: 실제 GitHub Actions와 실제 모델 호출은 미실행. 적용하려면 workflow/runtime이 신뢰한 기본 브랜치 및 `WORKFLOW_BASE_BRANCH`에 반영되어야 한다. 전체 runtime의 기존 실패 3개는 별도 후속 작업.
