# GitHub macOS runner 백엔드 검사 직접 실행

- 날짜: 2026-11-29 (Asia/Seoul)
- 상태: 완료 (구현·로컬 검증, 실제 macOS Actions 미확인)
- 담당 팀원: SW
- 참여 AI·담당 범위: Codex, workflow 백엔드 검사 실행 경로·검증·안내
- 공동 작업·관련 팀원 기록: 해당 없음
- 요청·목표: GitHub Actions의 macOS runner에서 prj-backend-check를 sandbox-exec 없이 직접 실행한다.
- 완료 조건: macOS 백엔드 검사에서 격리 도구 조회와 capability 점검을 호출하지 않는다. 임시 PostgreSQL·오프라인 설치·실패/시간 초과 보고를 유지한다.
- 변경 범위: workflow runtime·회귀 검사·관련 실행 안내.

## 읽은 근거·설계

- 루트 AGENTS.md, .agent-local.md(SW), .agents/workflow/README.md, PRJ/AGENTS.md, PRJ/rules/project.md, PRJ/rules/infra.md.
- workflow/runtime/test_runner.py, prj_backend_check.sh, 관련 unittest, workflow/config/projects/prj.json, .github/workflows/issue-approval.yml.
- 사용자 로그는 macOS sandbox 초기화 SIGABRT이며 실제 백엔드 검사는 시작되지 않았다.
- macOS에서 prj-backend-check만 직접 실행한다. 새 설정 없이 기존 명령으로 구분한다. Linux와 계산기 데모의 검사 격리는 기존 경로를 사용한다.
- 테스트는 후보 복사본에서 수행하고 HOME·TMPDIR·DB·venv를 실행별 scratch로 지정한다. 호스트 환경변수나 인증값을 상속하지 않는다. OS sandbox의 호스트 파일·네트워크 차단은 macOS 백엔드 검사에 적용하지 않는다.
- sandbox 정책을 추가 수정하는 대안은 사용자가 요청한 직접 실행에 맞지 않는다. 모든 프로젝트의 격리를 해제하는 대안은 요청 범위를 넘는다.
- 실제 GitHub runner는 macOS ARM64 self-hosted다. 현재 세션은 Windows·WSL이므로 실제 macOS 실행은 확인할 수 없다.

## 계획

1. [x] 실제 GitHub macOS runner와 검사·launcher 연결을 확인한다.
2. [x] 직접 실행 회귀 검사를 먼저 작성하고 기존 코드에서 실패를 확인한다.
3. [x] macOS 백엔드 직접 실행을 구현하고 관련 실행 안내를 갱신한다.
4. [x] 관련 unittest·문법·diff를 확인하고 실제 실행한 검증과 macOS 미확인 항목을 기록한다.

## 변경 파일

- workflow/runtime/test_runner.py: macOS PRJ 명령은 sandbox 도구 조회·점검을 생략하고 scratch의 신뢰된 launcher를 직접 실행한다. 기존 macOS PRJ 전용 sandbox profile·socket 점검 분기와 이에 따라 불필요해진 socket import를 제거한다. 직접 실행 결과에 environment=macos-native를 기록하고 macOS 검증 환경은 macos로 표시한다.
- workflow/runtime/prj_backend_check.sh: 직접 실행 경로를 반영한 설명. 임시 DB·오프라인 설치·종료 정리 로직은 기존대로 사용한다.
- workflow/runtime/tests/test_test_runner.py: native 명령·cwd·scratch·인증 환경변수 제외·정리·이전 sandbox 실패 무시·실패/시간 초과 보고 및 일반 macOS 검사 격리를 확인한다.
- workflow/config/projects/prj.json: 실행 방식 설명을 갱신한다. 검사·게시·모델 설정은 바꾸지 않는다.
- .github/workflows/issue-approval.yml: 도구 준비 실패와 test_unavailable 안내에 PRJ macOS 직접 실행을 반영한다. runner 라벨과 실행 단계는 기존대로 사용한다.
- workflow/README.md, workflow/runtime/README.md, workflow/runtime/ISSUE_APPROVAL.md, workflow/specs/github_runner.md, workflow/specs/github_settings.md, PRJ/rules/infra.md: 실제 실행 경로와 도구 전제를 갱신하고 기존 비활성·Linux 전용 안내 불일치를 수정한다.
- SW README: 이번 작업 기록에 연결한다.

## 검증·인계

- RED: 직접 실행·이전 sandbox 실패 무시 검사 2건은 변경 전 코드에서 예상한 assertion 실패로 재현했다.
- WSL/Python 3.14.4에서 python3 -B -m unittest workflow.runtime.tests.test_test_runner workflow.runtime.tests.test_prj_backend_launcher -v를 실행했다. 최종 42건 중 41건 통과, 기존 임시경로 검사 1건 실패(종료 코드 1)다. 전체 통과로 보고하지 않는다.
- macOS 분기와 PostgreSQL launcher 도구는 mock이다. 실제 Linux 프로세스의 출력·시간 초과·하위 프로세스 종료도 해당 단위검사에서 실행했다. 실제 PostgreSQL·모델 호출·macOS sandbox·macOS backend pytest는 실행하지 않았다.
- 실패한 test_validation_works_when_temp_parent_has_a_symlink_alias는 HEAD의 실행기와 테스트 소스를 메모리에 로드해 원본 파일 변경 없이 재실행했고 같은 실패를 확인했다. 기존 fixture가 TemporaryDirectory의 dir 인수를 중복 전달하는 문제는 이번 요청 범위에서 수정하지 않았다.
- Python AST 문법, 활성 PRJ 설정의 schema·경로, SW 기록 링크 확인이 종료 코드 0으로 통과했다. bash -n workflow/runtime/prj_backend_check.sh와 git diff --check도 종료 코드 0으로 통과했다.
- 초기 작업 공간에 있던 스킬 스크립트 실행 비트 변경은 보존했다. 구현 후 사용자가 PR 생성을 요청해 별도 fix/macos-native-backend-check 브랜치로 게시한다. Actions 재실행과 병합은 요청하지 않았다.
- 남은 작업: 변경을 GitHub의 WORKFLOW_BASE_BRANCH에 반영한 후 macOS runner에서 실제 백엔드 결과를 확인해야 한다. uv·Python·PostgreSQL·오프라인 캐시가 없으면 unavailable을 계속 보고한다.

## PR 준비

- 사용자 PR 요청 후 최신 origin/main을 fetch하고 이전 ai-auto PR #33의 MERGED 상태를 GitHub CLI로 확인했다. 현재 변경의 기준 tree는 origin/main과 동일하다.
- PR 게시 전 같은 runner/launcher 단위검사 42건을 다시 실행했다. 41건 통과, 변경 전에도 재현된 기존 임시경로 검사 1건 실패이며 종료 코드 1이다. 실패와 macOS mock·실제 macOS 미실행을 PR 본문에 명시한다.
- studio-pr-check를 적용했다. 변경 범위는 workflow 검사 실행기·회귀 검사·안내이며 PRJ 서비스 코드·UI·API·DB 계약은 바꾸지 않아 제품 build/E2E·서비스 DB 검사는 실행하지 않는다.
- 공용 PR 양식 .github/PULL_REQUEST_TEMPLATE.md는 이 checkout에 없어 변경 내용·검증·미확인 항목으로 PR 본문을 작성한다.
- PR 게시 상태: 완료. 구현 커밋 99383ea를 별도 브랜치로 push하고 [PR #35](https://github.com/JunSuHeo/kosa_final-public/pull/35)를 생성했다.
- GitHub CLI로 일반 PR(isDraft=false), OPEN 상태, main 대상, fix/macos-native-backend-check head와 구현 SHA를 확인했다. 변경 파일은 이번 작업의 13개 파일이며 이전 ai-auto 변경이나 공용 스킬 실행 비트 변경은 포함하지 않았다.
- PR 본문에 41건 통과·기존 1건 실패, 변경 전 실패 재현, macOS 분기/launcher mock, 실제 macOS 실행 미확인을 기록했다.
