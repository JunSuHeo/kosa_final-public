# macOS 샌드박스 런타임 매핑 권한 수정

- 날짜: 2026-11-29 (Asia/Seoul)
- 상태: 완료 (코드 수정·정적 확인 완료)
- 담당 팀원: SW (`.agent-local.md` 설정)
- 참여 AI·담당 범위: Codex, macOS 격리 정책과 시작 진단
- 공동 작업: 해당 없음
- 목표: PR #29 반영 후에도 `initialization`, 종료 코드 `-6`으로 중단되는 문제의 실행 정책 결함을 수정한다.
- 완료 조건: 승인된 런타임·테스트 경로에 실행 매핑을 명시적으로 허용한다. Python 본문 진입·모듈 import 전 단계와 종료 신호 이름을 기록한다. 코딩 후 검증·테스트 실패 후 일반 PR 게시 정책은 유지한다.
- 변경 범위: `workflow/runtime/test_runner.py`, 관련 실행 안내와 SW 기록.
- 작업 브랜치: `fix/macos-sandbox-runtime-mapping`, 기준 `origin/main` (`e353c29`).
- 이전 기록: [macOS 임시 경로·실패 진단 수정](../2026-11-29-macos-sandbox-diagnostics/README.md).

## 확인한 근거

- 사용자 결과: `isolation_stage=initialization`, `return_code=-6`, stdout/stderr 없음. `-6`은 POSIX의 `SIGABRT` 종료이며 첫 단계 표시도 실행되지 않았다.
- 실제 Actions 실행 [46164935192](https://github.com/JunSuHeo/kosa_final-public/actions/runs/46164935192)은 PR #29 병합 커밋에서 실행됐다. 샌드박스 밖 의존성 준비는 CPython 3.12.16으로 성공했고 35개 패키지를 설치했다. Actions 전체 성공은 실패 후 PR 게시 정책에 따른 결과이며 테스트 통과를 뜻하지 않는다.
- 현재 정책은 `deny default`, `process-exec`와 파일 읽기를 허용하지만 `file-map-executable`을 허용하지 않는다.
- [Apple dyld 원본](https://github.com/apple-oss-distributions/dyld/blob/fd8d0c4d52320ebf64db34f3cb280310d905c5ae/dyld/DyldDelegates.cpp#L1002)은 mmap 허용 여부를 `file-map-executable`, 파일 읽기는 `file-read-data`로 별도 검사한다.
- [공개 런타임 정책 참고](https://github.com/openai/codex/blob/065e18b04021008e2e7d504db8dc50275f589f73/codex-rs/sandboxing/src/seatbelt_read_only_platform_defaults.sbpl)는 실행 로더의 framework/dylib에 `file-map-executable`을 별도로 허용한다.
- 실행 매핑 권한 누락은 확인된 정책 결함이다. 실제 Mac의 dyld crash report는 확보하지 못했으므로 이번 `SIGABRT`의 직접 원인이 해당 거부였는지는 실행 검증 전까지 미확인이다.

## 계획·결정

- [x] 기존 허용 런타임 경로와 검증 복사본·scratch에만 `file-map-executable`을 추가한다.
- [x] `os`·`socket` import 전에 Python 진입을 표시하고 격리 프로세스 종료 신호 이름을 사유에 기록한다.
- [x] 안내·문법·diff를 정적으로 확인한다.
- [x] 수정 PR을 전달한다.
- 사용자 요청에 따라 자동 테스트 추가·실행은 계속 제외한다. Mac 명령 실행을 사용자에게 요청하지 않는다.
- 샌드박스 해제, 광범위한 IPC 허용, 코딩 전 격리 검사, 서비스 DB·환경·모델 변경은 범위에 추가하지 않는다.

## 변경 파일

- `workflow/runtime/test_runner.py`: 기존 읽기 허용 경로·snapshot·scratch의 실행 매핑을 허용한다. `python_imports`를 import 전에 기록하고 신호 종료 이름을 `reason`에 남긴다.
- `workflow/runtime/README.md`, `PRJ/rules/infra.md`: 실행 매핑, Python 초기 진입과 신호 진단의 의미를 설명한다.
- SW 작업 기록과 목록: 실제 Actions·Apple 소스 근거, 결정과 미확인 범위를 기록한다.

## 검증·인계

- WSL/Python에서 변경된 실행기와 내장 기본/PG 점검 문자열을 AST/compile로 문법 확인했다. 종료 코드 0이며 코드는 실행하지 않았다.
- `git diff --check`가 종료 코드 0으로 통과했다. 소스 diff에서 파일·네트워크 차단과 기존 코딩 후 검증·실패 후 일반 PR 정책이 유지됨을 확인했다.
- 사용자 요청에 따라 자동 테스트 추가·실행은 제외했다. 실제 Mac에서의 `SIGABRT` 해소와 백엔드 테스트 통과는 미확인이다.
- 구현 커밋 `871f9fa`를 푸시하고 [PR #32](https://github.com/JunSuHeo/kosa_final-public/pull/32)를 생성했다. `fix/macos-sandbox-runtime-mapping` → `main`, 일반 PR (`isDraft=false`), 생성 후 `OPEN` 상태와 구현 HEAD를 GitHub CLI로 확인했다.
- PR 본문에 실제 Actions·Apple 근거, 수정 범위, 정적 확인과 실제 macOS 검증 미실행을 기록했다.
