# 업무 연결에서 GitHub 인증

- 담당 팀원 / 날짜: JS / 2026-11-25 (Asia/Seoul)
- 참여 AI: Codex, 구현 및 검증
- 목표: 기준 프로젝트 등록의 GitHub 입력에서 GitHub App을 승인하고 비공개 저장소를 분석한다.
- 완료 조건: 승인 후 기존 등록 화면으로 복귀하고, 연결된 계정으로만 저장소를 조회하며, API와 worker가 해당 소유자의 권한으로 읽는다. 공개 URL 입력과 기존 토큰 설정은 계속 동작한다.
- 근거: 루트 및 PRJ AGENTS.md, PRJ/rules, PRJ/docs/spec, SourceSettings/Sources, source_api/repositories, GitHub App 사용자 인증 문서.

## 계획

1. 계정별 OAuth state, 서버 측 토큰 교환·갱신, 저장소 목록 API를 추가한다. 격리 DB와 GitHub 응답 대체로 검증한다.
2. GitHub 등록 폼에서 승인과 저장소 선택을 이어간다. 프런트엔드 빌드와 브라우저 경로를 확인한다.
3. 실행 안내와 API 계약을 갱신한다. 계약 검사 및 전체 격리 백엔드 테스트를 실행한다.

## 변경과 인계

- 업무 연결의 기존 등록 폼에서 GitHub App 사용자 승인을 시작한다. 같은 탭의 등록 필드를 복원하고, 저장소를 고르면 URL과 기본 브랜치를 채운다.
- 서버는 일회성 state와 PKCE로 승인 코드를 교환한다. API와 worker가 같은 소유자 토큰을 사용하고 유효기간이 가까워지면 갱신한다. App 토큰으로 접근할 수 없는 기존 저장소는 서버 토큰 또는 익명 조회로 다시 확인한다.
- API 계약과 GitHub App 설정, Supabase 마이그레이션 전제를 갱신했다.
- 리뷰 에이전트는 읽기 전용으로 변경을 검토했다. [리뷰 및 반영 기록](agents/github-review.md)

## 검증

| 위치 | 명령 및 범위 | 결과 |
| --- | --- | --- |
| 루트 | `make test` (격리 PostgreSQL, GitHub HTTP 대체) | 110 통과. 계정 간 격리, 콜백 재사용 차단, 토큰 갱신, worker 파일 읽기 및 기존 서버 토큰 폴백을 확인했다. |
| PRJ/frontend | `npm run build` | 통과. |
| PRJ | `backend/.venv/bin/python scripts/check_contracts.py` | OpenAPI와 schema 3개, 예시 2개 일치. |
| PRJ | `sh scripts/e2e.sh` (격리 브라우저, GitHub 승인 응답 대체) | 60 통과, 1 실패. GitHub 등록 통과. 기존 업무 배정 테스트는 배정 업무 카드 클릭에서 45초 시간 초과했다. |
| 격리 HEAD 사본 | `sh scripts/e2e.sh tests/users.spec.ts -g '업무 배정으로 같은 업무'` | 변경 전 커밋 8fcb122에서도 동일한 업무 카드 클릭 시간 초과를 재현했다. |
| PRJ | `sh scripts/e2e.sh tests/source-planning.spec.ts -g 'GitHub 승인'` | 최종 GitHub 테스트 1 통과. GitHub 승인, 목록, 분석 요청은 대체 응답을 사용했다. |
| 루트 | `git diff --check`, 격리 Compose 설정 검사 | 통과. |

## 실제 GitHub 연동 확인

- Supabase와 로컬 서비스에 변경 사항을 적용했다. GitHub App에 비공개 저장소 한 곳의 Contents 읽기 권한을 부여하고, Chrome의 OAuth 승인과 저장소 목록 조회를 확인했다.
- 실제 GitHub 파일 조회가 총 분석 시간 제한에 도달하면 실패하던 동작을 재현했다. 처음에는 기존 제한에 도달하기 전 읽은 파일을 보존하도록 수정하고 격리 백엔드 테스트 111개를 확인했다.
- 자동 재시도는 로컬 worker를 멈춘 동안에도 권한 오류가 났다. 처리 주체를 확인하지 못해 권한이 있는 로컬 worker에서 해당 작업을 실행했다.

## GitHub 분석 제한 변경 계획

- 요청: GitHub 전체 분석의 60초 제한을 없애고 연결된 비공개 저장소를 다시 분석한다.
- GitHub 요청별 타임아웃과 기존 읽기 상한을 유지한다. GitHub 분석 버전을 올려 동일 커밋에서도 새 스냅샷을 예약하고 이전 결과를 보존한다.
- 60초를 넘겨도 읽기를 계속하는 격리 회귀 테스트를 작성한다. 전체 백엔드 검사 후 5178에 적용하고 실제 분석 상태와 파일 수를 확인한다.

### GitHub 분석 제한 변경 결과

- GitHub 분석을 git-text.v2로 올리고 전체 분석 deadline을 제거했다. 로컬 Git 60초와 GitHub 네트워크 요청별 타임아웃, 분석 파일·용량 제한은 유지했다.
- 60초를 넘기는 회귀 테스트가 변경 전 실패했고, 변경 후 격리 백엔드 테스트 112개와 계약 검사가 통과했다.
- 5178 API·worker에 적용했다. 초기 실제 재분석은 71.5초에 GitHub 읽기 오류로 실패했고, 같은 커밋을 권한이 설정된 로컬 worker에서 다시 처리해 97.4초에 완료했다.
- 같은 커밋의 새 분석에서 파일 295개를 읽었고 시간 제한 제외는 없었다. v1 분석 파일 181개는 보존했다. 브라우저에서 새 분석의 준비 완료 상태를 확인했다.

## PR 검증

- `make test`는 격리 PostgreSQL에서 112개 통과했다. `npm ci && npm run build`, OpenAPI·스키마 계약 검사와 Gitleaks 검사도 통과했다.
- `make e2e`는 60개 통과, 1개 실패했다. GitHub 사용자 승인과 등록은 통과했다. 기존 업무 배정 테스트는 배정 업무 카드에서 시간 초과했고 변경 전 main에서도 같은 위치에서 재현됐다.
- 브라우저 화면은 테스트용 저장소와 계정으로 확인했다. 공개 PR 초안의 작업 기록에는 실제 비공개 저장소 식별자와 서버 설정 값을 제외했다.
