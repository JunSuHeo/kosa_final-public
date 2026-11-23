# 테스트 실패 보고 후 Draft PR 게시

- 날짜: 2026-11-24 (Asia/Seoul)
- 상태: 완료
- 담당 팀원: SW (`.agent-local.md` 설정)
- 참여 AI 에이전트·담당 범위: Codex, 워크플로 실행·검증·게시 정책과 이슈 댓글
- 공동 작업의 대표 기록·관련 팀원 기록: 해당 없음
- 요청·목표: 테스트 실패를 이슈 댓글에 남기고 PR 게시 단계로 계속 진행한다.
- 완료 조건: 실패·시간 초과·실행 불가 결과를 보존하고 댓글 작성 후 Draft PR을 생성한다. 검증 근거 누락·손상이나 입력 변경은 게시를 차단한다.
- 변경 범위: `workflow/runtime/`, PRJ 프로젝트 설정, Actions 의존성 준비 단계, 관련 실행 안내와 테스트

## 읽은 근거

- 루트 `AGENTS.md`, `PRJ/AGENTS.md`, `PRJ/rules/project.md`, `PRJ/rules/infra.md`
- `workflow/runtime/README.md`, `PUBLISHING.md`, `ISSUE_APPROVAL.md`
- `studio-pr-check`, `finishing-a-development-branch`, `verification-before-completion` 스킬

## 계획

1. 기존 Draft 허용 정책과 검증·게시 경로 확인 → 정책과 코드의 차이 확인
2. 실패 결과 보존, 댓글, Draft 게시 구현 → 실패·시간 초과·실행 불가 사례 검증
3. 최신 main 반영 후 검증 → 커밋·푸시·PR 작성

## 판단·진행 요약

- 확인한 사실: `allow_draft_on_failure` 설정은 존재했으나 게시 모듈은 검증 통과 결과만 허용했다.
- 선택과 이유: 기존 설정을 연결하고 PRJ에서 활성화했다. 검사 결과와 봉인된 `result.json`을 수정하지 않고 검토용 Draft만 게시한다.
- 검증 근거가 없는 경우와 테스트 입력 변경은 Draft 예외에서 제외했다.
- 캐시 준비 실패는 검사 실행 불가로 보고할 수 있도록 Actions가 코드 실행·검증으로 이어지게 했다.
- 이전 작업 브랜치의 변경을 새 브랜치 `fix/test-failure-draft-pr`에 커밋하고 `origin/main` (`6d82204`) 위로 rebase했다. 충돌은 없었다.

## 변경 파일

- `workflow/runtime/test_runner.py`, `run.py`, `orchestrator.py`, `publish.py`: 실패 후 Draft 허용 판정과 게시, 실패 근거 보존
- `workflow/runtime/issue_workflow.py`: 게시 전 실패 검사·오류 댓글과 완료 안내
- `workflow/config/projects/prj.json`, `.github/workflows/issue-approval.yml`: PRJ 정책 활성화와 캐시 준비 실패 후 진행
- `workflow/runtime/tests/`: 실패·시간 초과·실행 불가, 미실행 근거, 입력 변경 차단, 댓글 순서·중복 방지·비밀값 가림 검증
- `PRJ/README.md`, `workflow/README.md`, 런타임 안내 문서: 변경된 실행 흐름과 결과 상태 설명

## 검증

| 실행 위치 | 명령·확인 방법 | 결과 | 근거·한계 |
| --- | --- | --- | --- |
| 저장소 루트, Linux/WSL | `python3 -B -m unittest discover -s workflow/runtime/tests -q` | 통과, 종료 코드 0 | 최신 main 반영 후 262개 통과. Codex·검사 프로세스와 원격 게시를 모의 처리한 런타임 검증 |
| 저장소 루트 | `git diff --check` | 통과, 종료 코드 0 | 변경 파일 공백 오류 없음 |

## 결과·인계

- 완료 내용: 실패한 검증을 그대로 기록하며 게시 전에 이슈 댓글을 작성하고 Draft PR을 생성하는 흐름을 구현했다.
- 미확인·남은 작업: 실제 macOS 러너의 실패 후 게시 흐름은 미실행이다. PR 검토와 main 병합 후 새 승인 작업에서 확인한다.
- 제품 DB·모델 키·운영 서비스를 사용하는 테스트는 실행하지 않았다.
- 다른 에이전트 기록·정제한 로그 링크: 해당 없음
