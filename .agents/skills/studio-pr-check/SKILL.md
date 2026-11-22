---
name: studio-pr-check
description: Use when preparing or reviewing a 기획실 Studio PR, selecting Studio checks for a change, or recording PR verification results.
---

# Studio PR 검증

저장소 루트에서 변경 파일과 실제 동작을 확인한다. 제품 규칙은 [PRJ/AGENTS.md](../../../PRJ/AGENTS.md), 명령의 전제는 [팀 개발 가이드](../../../README.md#자주-쓰는-명령)와 [서비스 검증 안내](../../../PRJ/README.md#검증)를 따른다.

## 변경별 검증

여러 항목이 해당하면 검증을 합쳐 실행한다.

| 변경 범위 | 검증 |
| --- | --- |
| 문서만 변경 | 수정한 링크·경로·예시 명령을 확인하고 `git diff --check`를 실행한다. |
| 프런트엔드 코드·표시 문구·스타일 | `(cd PRJ/frontend && npm ci && npm run build)`으로 빌드한다. 확인할 화면이 있으면 변경 전후를 비교한다. |
| 브라우저에서 조작하는 흐름이나 UI·API 연동 | `make e2e`를 실행한다. 변경 동작을 기존 시나리오가 다루는지 확인하고, 빠져 있으면 격리 환경에서 해당 동작을 직접 확인한다. |
| 백엔드·마이그레이션·worker | `make test`를 실행하고 관련 경계 조건을 확인한다. |
| API·스키마·저장된 계약 JSON 또는 예시 변경 | 아래 계약 검사를 실행한다. `PRJ/docs/spec/`의 계약 JSON이나 예시만 바뀐 경우도 포함한다. |

계약 검사에는 `uv`가 필요하다. mock 모드에서 저장 계약과 예시를 생성 모델·API와 대조한다.

```sh
(cd PRJ/backend && APP_ENV=local AUTH_MODE=mock AI_MODE=mock uv run --frozen python ../scripts/check_contracts.py)
```

승인·복원 변경은 승인 전 `current_version`과 기존 revision이 유지되는지 확인한다. 인증·소유권 변경은 401, 리소스 없음과 다른 소유자에 대한 동일한 404, 버전·멱등성 충돌의 409를 변경 범위에 맞춰 확인한다. UI에서 승인 흐름과 API 계약을 동시에 바꾸는 경우 UI 빌드와 E2E, 백엔드 테스트, 계약 검사를 함께 검토한다.

## PR에 남길 내용

[PR 양식](../../../.github/PULL_REQUEST_TEMPLATE.md)의 검증 항목에 이번 변경에서 실행한 명령과 결과를 적는다. 검증 환경이 mock인지 live인지 밝히고, 수행할 수 없었던 검증은 항목과 이유를 적는다. 예를 들어 Docker가 없으면 UI 코드 빌드 결과와 E2E 미실행 사유를 각각 적는다. 과거 결과를 인용할 때는 그 실행 시점과 범위를 표시한다. UI 변경이면 리뷰에 필요한 화면을 첨부한다.
