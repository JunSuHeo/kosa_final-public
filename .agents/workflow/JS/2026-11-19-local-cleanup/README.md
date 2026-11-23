# 로컬 생성 파일과 중복 그림 정리

담당 팀원은 JS다. 사용자 승인 범위의 로컬 생성 파일과 중복 산출물을 정리한다.

## 계획

1. 후보가 재생성 가능한 파일이거나 PDF에 담긴 그림인지 확인한다.
2. 승인한 경로만 정리한다. 루트 `workflow/`, 로컬 설정과 기존 검증 근거를 보존한다.
3. 삭제 목록과 스테이징 상태, 보존 대상의 존재 여부를 확인한다.

## 결과·인계

- `Zone.Identifier` 130개, Python 바이트코드 12개, TypeScript 증분 빌드 파일 1개를 정리했다.
- `PRJ/frontend/node_modules/`, `PRJ/backend/.venv/`, `PRJ/frontend/dist/`, 빈 `.deepeval/`과 `PRJ/.research/`를 정리했다. 정리 전 의존성 폴더 크기는 약 190 MiB였다. 필요한 경우 프런트엔드는 `PRJ/frontend`에서 `npm ci`, 백엔드는 `PRJ/backend`에서 `uv sync --frozen`으로 복원한다.
- 중복 아키텍처 PNG 4장을 삭제했다. PDF와 생성 스크립트는 보존했다.
- 대상 부재와 보존 경로, 기존 스테이징 및 루트 `workflow/`의 Git 상태를 확인했다. 환경 설정과 `PRJ/docs/`의 검증 자료는 정리 전후 파일 크기와 수정 시각이 같았다. `git diff --check`를 통과했다.
- 제품 테스트는 이번 정리에서 실행하지 않았다. PNG 삭제는 작업 트리에 있다.
