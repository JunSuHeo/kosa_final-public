# macOS 임시 검증 경로의 path_violation 수정

- 날짜: 2026-11-23 (Asia/Seoul)
- 상태: 완료 (코드 수정·검증 완료)
- 담당 팀원: SW (원래 체크아웃의 `.agent-local.md` 기준)
- 참여 AI: Codex, 조사·수정·회귀 검증
- 공동 작업: 해당 없음
- 목표: PRJ 하위 수정이 독립 검증에서 path_violation으로 실패하는 원인을 확인하고 코드 결함을 수정한다.
- 완료 조건: 임시 폴더 부모가 링크인 경우에도 정상 후보의 검증이 통과하고 실제 범위 위반 차단이 유지된다.
- 변경 범위: workflow/runtime/test_runner.py, 관련 테스트·안내, SW 작업 기록.
- 기준: main `1af47d6`, worktree `fix/macos-validation-path`.

## 근거와 계획

- 루트/PRJ AGENTS.md, PRJ/rules/project.md, PRJ/rules/infra.md, PRJ/README.md, workflow/runtime/README.md.
- test_runner.py, workspace.py, validate_config.py, run.py, issue_workflow.py, test_test_runner.py.
1. Actions 실행과 경로 검사 흐름을 확인한다.
2. macOS 임시 경로의 링크 별칭을 로컬에서 재현하고 최소 수정한다.
3. 관련 회귀 및 전체 워크플로 테스트를 실행하고 PR로 전달한다.

## 확인한 사실

- Actions 실행 `45179946669`, 계획 `05aac03c-8307-4d78-8c8d-4497014f3b52`가 validation_failed / path_violation으로 실패했다.
- 해당 상태는 생성 결과의 collect 단계 후 독립 검증에서 반환된다. PRJ 밖 변경을 collect에서 감지하면 execution_failed / path_violation이므로 이번 표시만으로 PRJ 밖 변경이라고 단정할 수 없다.
- 런타임은 엔진이 만든 임시 검증 루트를 resolve하지 않고, 하위 테스트 cwd만 resolve해 포함 여부를 비교한다. macOS의 /var와 /private/var 또는 /tmp와 /private/tmp 별칭에서 같은 실제 디렉터리도 범위 밖으로 판정한다.
- Linux에서 임시 폴더 부모에 같은 형태의 링크를 만들어 재현했다. 결과는 status=failed, scope_status=failed, 테스트 결과 빈 배열, executor 호출 0회이며 오류는 허용 경계 밖이라는 고정 메시지다.
- 원격 로그에는 원본 result.json 오류 상세가 없고 Actions artifact도 없다. 실제 러너의 changed_files와 validation.errors를 사용자에게 요청했다.

## 검증·인계

- 수정: 엔진 소유 임시 검증 루트를 `.resolve()`로 실제 경로로 통일했다. 후보 내부 링크나 허용 범위 밖 변경을 허용하는 정책은 변경하지 않았다.
- 회귀 검증: `test_validation_works_when_temp_parent_has_a_symlink_alias`가 수정 전 path_violation으로 실패했고 수정 후 통과했다.
- 관련 검증: `python3 -B -m unittest workflow.runtime.tests.test_test_runner -v`, 37개 통과, 1.067초, 종료 코드 0.
- 전체 검증: `python3 -B -m unittest discover -s workflow/runtime/tests`, 255개 통과, 7.287초, 종료 코드 0.
- 정적 검증: `git diff --check` 통과.
- 검증 환경: WSL/Linux에서 실제 임시 폴더·링크·파일 복사·경로 검사를 실행했고 테스트 프로세스는 offline fake를 사용했다. 실제 모델·서비스 DB·macOS sandbox는 호출하지 않았다.
- 실제 러너의 result.json 오류 상세는 아직 미확인이다. 진단 명령의 zsh 문법 오류 보고를 받아 Python `-c` 방식으로 간소화한 명령을 다시 전달했다.
- 인계: 앞서 승인된 커밋·푸시·PR 생성 흐름으로 `fix/macos-validation-path`를 main 대상 PR에 전달한다. 병합 후 새 계획·승인으로 원격 검증을 확인한다. 이미 validation_failed로 종료한 실행은 자동 재시작하지 않는다.
