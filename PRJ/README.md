# H-PlanIT (에이치플래닛)

REA로 매니패스트의 공개 JavaScript를 분석하고 로그인된 편집기의 동작을 관찰한 뒤, 소스 재사용 없이 새로 만든 AI 기획 작업 공간이다. 이전 구현은 별도 보관했다.

업무 선택 → 업무 대화 → 명시적 초안 작성 → 기획 내용·기능 상세·업무 흐름·화면 시안 → 현업 확인본·내보내기를 연결한다. 실제 생성은 OpenRouter/OpenAI의 서버 API를 사용한다. REA는 개발 중 조사 도구이며 서비스 실행에는 필요하지 않다.

## 실행

팀 개발용 Supabase 환경과 공용 명령은 [루트 팀 개발 가이드](../README.md)를 참고한다. 아래 명령은 `PRJ/`에서 실행한다.

Docker Desktop이 필요하다. 처음 설치할 때 예제에서 로컬 환경 파일을 만든다.

```sh
test -f .env || (umask 077; cp .env.example .env)
# 아래 Supabase 연결 절차로 .env.supabase 및 스키마·계정을 먼저 준비한다.
cd ..
make up
make ps
```

기존 체크아웃을 갱신할 때는 추적 해제 전에 로컬 `.env`를 안전한 위치에 백업한다. 공용 설정이 필요하면 예제에서 다시 만들고 현재 발급된 값으로 채운다.

- 웹/API: `make up` 출력 또는 `make ps`의 포트를 사용한다. 이 장비의 Supabase 앱은 웹 5178/API 8014다.
- DB: `.env.supabase`의 외부 Supabase PostgreSQL. 기존 로컬 DB는 자동 실행하거나 이전하지 않는다.
- 소스: `frontend/`, `backend/app/`, `backend/migrations/`, `prompts/`

`.env.example`은 공통 설정과 격리 백엔드 테스트용 mock 값을 제공한다. 브라우저 앱은 `.env.supabase`와 Supabase Compose 구성으로 실행한다. mock 인증은 백엔드 격리 검사 전용이며 브라우저 계정 저장소는 사용하지 않는다.

## Supabase PostgreSQL 연결

1. Supabase 프로젝트의 **Connect → Session pooler**에서 포트 `5432` 연결 문자열을 복사한다. 실행 환경에서 직접 접속이 가능하면 **Direct connection**도 사용할 수 있다. worker가 PostgreSQL 세션 잠금을 사용하므로 **Transaction pooler**는 사용하지 않는다. [Supabase 연결 가이드](https://supabase.com/docs/guides/database/connecting-to-postgres)
2. 예제를 복사해 `.env.supabase`를 준비한다.

   ```sh
   test -f .env.supabase || (umask 077; cp .env.supabase.example .env.supabase)
   ```

3. `MIGRATION_DATABASE_URL`은 스키마를 관리하는 계정에, `DATABASE_URL`은 `studio_runtime`을 상속하는 전용 실행 계정에 연결한다. 연결 문자열은 비밀번호를 URL 인코딩한 뒤 작은따옴표로 감싸고 `sslmode=require`를 지정한다. API와 worker는 시작할 때 마이그레이션을 실행하지 않는다.
4. 인증 값과 명시적 마이그레이션, 초기 관리자 생성, 데이터 이전의 전제는 [Supabase 전환 안내](docs/supabase-transition.md)를 확인한다. 운영에 적용하기 전에 별도 DB와 테스트 계정으로 검증한다.

2026-11-20 이 체크아웃에서 관리형 Supabase 연결을 검증했다. 기존 로컬 DB와 별도로 새 스키마·전용 실행 계정·초기 `admin`을 구성했으며 데이터 이전은 수행하지 않았다. 초기 비밀번호는 Git 제외 파일 `.env.supabase.admin-password`에 저장한다. 검증 앱은 다음 명령으로 실행하며 웹은 `http://localhost:5178`, API는 `http://localhost:8014`다.

```sh
STUDIO_COMPOSE_PROJECT=planning-studio-supabase STUDIO_API_PORT=8014 STUDIO_WEB_PORT=5178 APP_ENV=local AI_MODE=mock \
  docker compose --env-file .env --env-file .env.supabase \
  -f compose.yaml -f infra/supabase.compose.yaml up --build -d api worker web
```

실제 DB·인증과 mock AI를 사용한 검증 결과 및 제한은 [Supabase 실계정 검증](docs/supabase-verification.md#관리형-supabase-연결-검증-2026-11-20)에 기록한다. 재실행에는 이 장비의 Git 제외 설정 파일이 필요하다.

## 실제 AI

서버 `.env`에서 설정한다. 키를 프런트엔드 또는 `VITE_*` 변수에 넣지 않는다.

```dotenv
APP_ENV=local
AUTH_MODE=supabase
AI_MODE=live
LLM_PROVIDER=openrouter
OPENROUTER_MODEL=openai/gpt-6.1-sol
OPENROUTER_API_KEY=서버에서만_사용할_키
```

기존 `LLM_API_KEY`와 `LLM_MODEL`도 지원하며 공급자별 키/모델보다 우선한다. 공급자를 바꿀 때 일반 키와 모델도 함께 변경한다. OpenAI는 `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_MODEL`을 사용한다.

```sh
cd .. && make up
```

실패한 실제 호출을 mock으로 대체하지 않는다. 실행에 AI 모드·공급자·모델을 고정하며, 설정을 바꾼 뒤 이전 실행을 이어서 처리하지 않는다. 실제 모델 출력은 서버에서 JSON schema와 항목 연결을 검증한다. 연결 오류의 보정은 최대 한 번이다.

## 사용

1. IT 담당자는 **업무 연결 설정**에서 저장소를 등록하고 분석한다. 확인 가능한 색상·글꼴·간격·공통 배치를 보완하고 코드 사용 범위와 AI 공급자/모델을 확인한 뒤 **업무 게시**를 누른다. 기존 등록 업무도 처음 한 번 게시해야 홈에서 선택할 수 있다.
2. 현업은 홈에서 업무와 기획 유형(신규 기능/기존 기능 개선/업무 프로세스 변경)을 선택하고 **기획 시작하기**를 누른다. 처음 업무 설명을 보낼 때 기획 작업이 저장된다.
3. 현재 업무, 불편한 점, 원하는 변화와 업무 규칙을 AI와 대화한다. 대화만으로 산출물을 자동 생성하지 않는다.
4. **기획 초안 만들기**를 누르면 기획 내용·기능 상세·업무 흐름·화면 시안을 만든다. 시안 요소를 선택하면 이름 태그가 대화에 연결된다.
5. 미확정 초안에서도 대화할 수 있다. 보완 사항을 설명하고 **수정 내용 반영**을 누른다. 생성 실패·취소 시 이전 초안이 남으며 최초 초안을 사용하지 않기로 해도 다시 대화할 수 있다.
6. **내용 확인**에서 기획 내용·담당자와 처리 순서·업무 흐름·화면 시안을 보며 확인한다. **내용 보기**는 현재 초안의 해당 항목을 강조하고, **이 내용 수정하기**는 기획 파트너로 연결한다. 모바일은 **확인 안내로 돌아가기**로 복귀한다. 수정안은 마지막 확인본과 달라진 내용을 먼저 안내하며, 연결 오류에는 **AI로 정리하기**를 제공한다. 확인 체크만으로 오류를 무시할 수 없다.
7. **현업 확인본 저장**은 버전을 보관하는 기능이며 IT 최종 승인을 의미하지 않는다. 확인본의 Markdown/JSON을 내보낼 수 있다.
8. 기록에서 이전 확인본을 조회하고 복원 수정안을 만들 수 있다. 좁은 화면은 **대화/산출물** 전환과 **기획 도구** 메뉴를 사용한다.

계정·권한은 서버 계정 API와 DB로 관리하며 비밀번호 검증은 Supabase Auth가 담당한다. IT 최종 승인은 후속 범위다. 업무 연결은 소유자가 준비·게시하고 계정별로 배정한다. 관리자는 다른 계정의 기획을 열람하지 않는다. 코드 변경은 5분 간격으로 백그라운드 확인하며 기존 기획의 코드 기준을 자동 교체하지 않는다.

새로고침과 재접속 후에도 프로젝트·질문·메시지·proposal·확정본이 PostgreSQL에 유지된다. worker 재시작은 저장된 단계부터 재개한다. DB 결과는 중복 생성하지 않지만, 저장 직전에 중단된 외부 모델 호출은 다시 일어날 수 있다.

## 인증

실제 인증은 `AUTH_MODE=supabase`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_AUDIENCE`로 설정한다. 서버에 등록된 계정의 ID와 비밀번호로 로그인한다. 서버는 계정 관리에 `SUPABASE_SERVICE_ROLE_KEY`를 사용한다. 서버는 JWKS와 RS256/ES256 서명, issuer/audience/sub/iat/exp를 확인한다. 서버 인증 구현은 만료된 토큰을 갱신하고 갱신에 실패하면 로그인 화면으로 이동한다. 회원가입·조직·초대는 이번 범위에 없다.

로컬 테스트 계정은 `admin`(ADMINISTRATOR), `user1`(USER1), `user2`(USER2)다. 명시적 관리 명령으로 구성하며, 앱 시작이나 브라우저 진입 시 자동 생성·초기화하지 않는다. admin의 기존 내부 ID와 기획 소유권을 유지하고 일반 계정에는 서버가 고유 ID를 발급한다. 브라우저 목업의 계정 ID·비밀번호 검증값은 이전하지 않는다.

```sh
docker compose --env-file .env --env-file .env.supabase \
  -f compose.yaml -f infra/supabase.compose.yaml run --rm manage seed-test-accounts
```

비밀번호는 대화형 입력 또는 읽기 전용으로 마운트한 파일의 `--password-file`로 전달한다. 명령은 `APP_ENV=local`, `AUTH_MODE=supabase`에서만 허용한다. 기존 계정은 유지하고 없는 계정만 생성하며 역할·활성 상태가 다르면 오류로 중단한다. 기존 비밀번호도 바꾸려는 경우에만 `--reset-passwords`를 붙인다. 이 장비의 세 계정은 사용자 지정 공통 테스트 비밀번호로 구성하며 관리자 비밀번호 파일도 Git 제외 상태로 유지한다.

관리자의 왼쪽 위 메뉴에서 **계정 관리 / 역할·권한 설정 / 변경 이력**을 연다. 계정 등록·이름/역할/상태 변경·비밀번호 재설정·게시 업무 배정을 지원하며 마지막 활성 관리자는 보호한다. 업무는 연결 소유자가 게시한 뒤 배정하고, 사용자는 배정된 업무로 본인 기획을 만든다. 배정을 해제해도 기존 문서와 확인본 내보내기는 유지되지만 새 AI 요청은 차단된다.

`frontend/src/accounts/types.ts`의 비동기 `AccountService`는 서버 구현만 사용한다. `studio_accounts`는 계정·역할·활성 상태를, `studio_role_permissions`는 역할별 권한을, `studio_auth_sessions`는 세션 버전과 해제 상태를, `studio_audit`는 변경 이력을 저장한다. 비밀번호 검증은 Supabase Auth가 담당하며 브라우저와 앱 테이블에 비밀번호·검증값을 저장하지 않는다. 브라우저의 sessionStorage에는 서버 세션 토큰과 만료 시각만 보관한다. 과거 브라우저 목업 계정·세션은 초기화 시 제거한다. 역할·사용 상태·비밀번호 변경은 서버 세션을 해제하며 권한 정책은 서버 요청마다 검증한다.

업무 배정 API는 `GET /api/sources/{id}/assignments`, `PUT/DELETE /api/sources/{id}/assignments/{account_id}`다. actor는 인증 토큰에서만 가져오며 대상 account_id만 경로로 전달한다. `005_source_assignments.sql`은 배정 관계를 추가하고 프로젝트의 source-owner 복합 FK를 source FK로 바꾼다. 스냅샷·게시 기준·revision 불변성과 snapshot/source 복합 FK는 유지된다. 브라우저 사이트 데이터를 삭제해도 서버의 계정·정책·이력과 기획 데이터는 유지된다.

mock Bearer 인증은 격리 백엔드 테스트 전용이다. 브라우저 앱은 Supabase 인증을 사용한다. 모든 API는 서버에서 소유권을 검사한다. 인증 오류는 401, 없는/다른 소유자의 리소스는 동일한 404, 버전·멱등성 충돌은 409다.

## 검증

2026-11-10 이후 남은 작업과 실행 근거는 [작업 목록](docs/remaining-work.md), [평가 조건](docs/evaluation-plan.md), [3일 사용성 기록](docs/usability-log.md)에 정리한다. 실계정 로그인과 사람의 의미 품질 평가는 자동 테스트 결과와 구분한다.

Luna 실제 호출 재현(모델 사용료 발생, 전용 검증 프로젝트 생성):

```sh
python3 scripts/live_smoke.py --output docs/luna-live-smoke.json
python3 scripts/live_revision_smoke.py --input docs/luna-live-smoke.json --output docs/luna-live-revision-smoke.json
# 생성 결과의 project_id를 사용한다.
python3 scripts/live_review_smoke.py PROJECT_ID --output docs/luna-live-review-smoke.json
```

위 smoke는 새로운 실행 근거를 작성하므로 기존 증거를 보존하려면 다른 출력 파일명을 지정한다. 반복 평가는 고정된 6개 사례를 저장하고 완료된 사례는 건너뛴다. 관찰 시간 초과 시 job/review의 저장 상태를 확인하고 같은 사례를 이어서 관찰한다.

```sh
python3 scripts/evaluate_luna.py
python3 scripts/summarize_luna_evaluation.py
```

운영 검증은 제품과 다른 Compose 프로젝트·포트·볼륨에서 mock으로 실행한다. dump는 Git 제외 `.research/operations/`에 보존하고, 매 실행마다 별도 이름의 복원 DB를 만든다. `down`은 검증 컨테이너만 종료하며 볼륨은 보존한다.

```sh
STUDIO_COMPOSE_PROJECT=planning-studio-ops STUDIO_DB_PORT=54333 STUDIO_API_PORT=8012 STUDIO_WEB_PORT=5176 AI_MODE=mock AUTH_MODE=mock docker compose up --build -d db api worker
python3 scripts/verify_operations.py
python3 scripts/verify_proxy_recovery.py
STUDIO_COMPOSE_PROJECT=planning-studio-ops docker compose down
```

Luna 검증 프로젝트를 읽기 전용으로 화면 검사한다. 역할 검토가 완료된 프로젝트 ID가 필요하다.

```sh
cd frontend
E2E_BASE_URL=http://localhost:5174 LUNA_PROJECT_ID=PROJECT_ID npx playwright test tests/luna-usability.spec.ts --output=test-results-live/luna
```

Backend는 서비스 DB와 다른 `studio_test` PostgreSQL에서 실행한다.

```sh
docker compose --profile test run --build --rm test
```

GitHub Issue 승인 워크플로에서는 같은 백엔드 pytest를 Linux Bubblewrap 또는 macOS `sandbox-exec` 안의 일회성 `studio_test` DB로 실행한다. `workflow/config/projects/prj.json`의 백엔드는 모든 승인 실행에서 필수 검사다. Actions는 기준 브랜치의 `backend/uv.lock`으로 캐시를 준비하고 실제 검사는 오프라인으로 실행한다. 러너에 시스템 PATH의 `uv`, Python 3.12 이상, PostgreSQL 서버·클라이언트 도구가 필요하다. macOS Homebrew의 versioned PostgreSQL 경로도 지원한다. 설치와 macOS 실제 capability 검증은 러너에서 별도 확인하며, 상세 준비 조건과 opt-in 통합 검증은 [워크플로 실행 안내](../workflow/runtime/README.md#독립-테스트-설정과-실행)를 따른다. 서비스 DB와 모델 키를 테스트에 사용하지 않는다.

이 승인 워크플로는 테스트 실패·시간 초과·실행 불가를 이슈 댓글에 기록하고 검토용 일반 PR 게시를 진행한다. `pr_policy.allow_pr_on_failure=true`, `publishing.draft=false`를 사용하며 검증 결과는 실패로 유지한다. `pr_policy.require_branch_protection=false`로 GitHub 보호 규칙이 없어도 게시하지만 저장소 식별·Push 권한·기준 SHA는 확인한다. 코드 생성 실패, 허용 경로 위반, 테스트 입력 변경 또는 검증 근거 손상은 게시를 차단한다. `/approve`는 구현 실행 승인이고 자동 병합은 하지 않는다.

Frontend 재현 설치와 빌드:

```sh
cd frontend
npm ci
npm run build
```

격리 E2E는 `PRJ/`에서 다음을 실행한다(저장소 루트에서는 `make e2e`). 실행마다 별도 Compose 프로젝트·DB volume·자동 할당된 루프백 포트를 사용한다. `infra/e2e.compose.yaml`의 테스트 전용 Auth가 ES256 JWT/JWKS를 제공하고 실제 API·DB 계정·권한 경로를 검증한다. 각 테스트는 전용 DB/Auth 상태를 초기화하며 실제 Supabase 키·DB와 모델은 사용하지 않는다. 종료 시 해당 실행의 컨테이너와 볼륨을 정리하고 실패 증거는 Git 제외 `.research/`에 보존한다.

```sh
sh scripts/e2e.sh
```

실제 AI smoke는 localhost:8010의 명시적인 `AUTH_MODE=mock`, `AI_MODE=live` 환경에서만 실행한다. 실제 공급자 호출 비용이 발생하며, 검증용 프로젝트 한 개를 생성하고 승인하지 않는다.

```sh
python3 scripts/live_smoke.py
```

실제 수정까지 확인하려면 먼저 위 생성 smoke를 새로 실행한 뒤 다음을 실행한다. 검증 스크립트가 만든 이름의 프로젝트만 승인하고, 버튼 문구 하나의 수정 결과는 pending으로 남긴다.

```sh
python3 scripts/live_revision_smoke.py
```

자세한 결과와 미검증 범위는 [검증 기록](docs/verification.md)을 확인한다.

## 문서와 범위

- [관찰·REA 증거·분석 한계](docs/reverse-engineering.md)
- [새 데이터/API 계약](docs/spec/README.md), [OpenAPI](docs/spec/openapi.json), [Snapshot schema](docs/spec/snapshot.schema.json)
- [계약 변경 결정](docs/contract-decisions.md), [구현 상태](docs/implementation-plan.md)

실행 로그·원본 평가 자료·스크린샷·업무 저장소 검증 자료는 내부 보관 자료다. 팀원은 [환경 설정 예제](.env.example)와 [Supabase 연결 예제](.env.supabase.example)를 복사해 각자 환경 파일을 만든다. 서버 비밀은 권한 있는 팀원이나 배포 서버에 팀의 비밀 저장소를 통해 전달한다.

검토 탭의 **역할별 AI 검토**에서 개발자·기획자·보안·UI/UX·QA 검토를 시작한다. 역할마다 원문 근거·수정 제안·검수 기준을 보여주며 실패한 역할만 재시도할 수 있다. 검토 결과는 기획을 자동 수정하지 않는다.

결제·공동편집·파일 업로드·외부 공유·제품 MCP는 구현 범위에 포함하지 않았다. 매니패스트의 백엔드·원본 프롬프트·DB를 복원했다고 주장하지 않는다.


역할 검토의 실제 모델 검증은 저장된 프로젝트를 대상으로 실행한다. 확정/수정안은 바꾸지 않으며 최대 다섯 역할의 호출 비용이 발생한다. 이미 검토한 동일 대상은 보관된 결과를 반환한다.

```sh
python3 scripts/live_review_smoke.py <project_id>
```

## 저장소 연결과 검증

**업무 연결 설정**의 **기준 프로젝트 등록**으로 GitHub URL과 브랜치를 등록하거나 허용된 로컬 저장소의 상대 경로를 입력한다. 로컬 저장소는 Git 메타데이터를 가진 일반 체크아웃을 지원한다. 대규모 저장소에는 `frontend/src`처럼 분석에서 먼저 읽을 경로를 지정할 수 있다.

로컬 분석을 사용할 때는 별도 읽기 전용 마운트를 연결한다. 마운트 대상에는 분석을 허용하는 저장소만 둔다.

```sh
STUDIO_REPOSITORY_HOST_ROOT=/절대경로/저장소모음 \
  docker compose -f compose.yaml -f infra/repositories.compose.yaml up --build -d
```

호스트에서 API와 worker를 실행할 때는 두 프로세스에 동일한 `LOCAL_REPOSITORY_ROOT`를 설정한다. GitHub 공개 저장소는 토큰 없이 읽을 수 있다. 수동 설정으로 비공개 저장소를 읽으려면 서버의 `GITHUB_USER_TOKENS`에 저장소 소유자의 H‑PlanIT 계정 ID(`studio_accounts.id`)별 읽기 전용 토큰을 매핑한다. `GITHUB_LOCAL_TOKEN`은 로컬 mock의 기본 웹 사용자 검증용이다.

### 업무 연결에서 GitHub 승인

1. [GitHub App을 등록한다](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app). Repository permissions에서 **Contents: Read-only**를 부여하고, 만료형 사용자 토큰을 활성화한다. Callback URL은 웹 서비스 주소 뒤에 `/github/callback`을 붙인다. 예를 들어 웹이 5178이면 `http://localhost:5178/github/callback`을 등록한다.
2. API·worker 서버 환경에 `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_CLIENT_SECRET`, `GITHUB_APP_CALLBACK_URL`, `GITHUB_APP_SLUG`, `GITHUB_TOKEN_ENCRYPTION_KEY`를 같은 값으로 설정한다. 암호화 키는 서버 Python에서 `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`로 생성해 서버 비밀 저장소에 보관한다. Supabase 구성에서는 [Supabase 마이그레이션 절차](docs/supabase-transition.md)로 `008_github_connections.sql`을 적용한 뒤 API·worker·web을 갱신한다.
3. **업무 연결 설정 → 기준 프로젝트 등록 → GitHub → GitHub 연결**에서 승인한다. 목록에 저장소가 없으면 **GitHub App 설치·저장소 권한 설정**에서 대상 저장소를 허용하고 목록을 새로고침한다. 저장소를 선택하면 기본 브랜치가 채워진다. 필요하면 브랜치를 수정하고 등록한다. 이미 등록한 비공개 저장소는 동일 소유자 계정에서 연결한 뒤 분석을 다시 시작한다.

GitHub App이 허용한 저장소 중 로그인한 GitHub 사용자가 접근할 수 있는 저장소가 표시된다. 토큰은 서버에서 암호화해 저장하고 API·worker가 만료 전에 갱신한다. 설정하지 않은 배포에서는 URL 직접 입력과 기존 서버 토큰을 사용할 수 있다.

분석을 시작하면 branch에서 확인한 커밋만 읽는다. 워킹 트리의 미커밋 변경은 상태에 표시한다. 개별 파일 40KB, 최대 360개, 총 2.4MB, 모델 발췌 32KB를 상한으로 적용한다. 로컬 저장소 분석에는 전체 60초 제한이 적용된다. GitHub 백그라운드 분석에는 전체 시간 제한을 두지 않으며 요청별 네트워크 타임아웃과 GitHub 읽기 한도를 적용한다. 읽기 상한·제외 규칙·민감 패턴에 해당하는 파일은 분석 결과에 사유를 기록한다. 등록과 분석은 저장소의 설치 스크립트와 애플리케이션을 실행하지 않는다.

업무 연결 설정에서 소유자가 허용 코드 범위와 AI 공급자/모델을 확인하고 게시한다. live 모델은 허용 범위 안에서 요청 관련 발췌를 전송하며, H-PlanIT은 고정 기준과 발췌를 기획·검토 기록에 보관한다. 공급자에서의 처리와 보관은 해당 공급자 설정과 정책을 따른다. 민감 패턴 검사는 자동 필터이므로 비공개 저장소를 전송하기 전에 발췌를 검토한다.

**자료 → IT 전달자료**의 구현 지침에 현재·제안 동작, 적용·제외 범위, 근거, 구현 순서와 수용 테스트가 있다. 코드 변경은 백그라운드에서 확인하며, 새 스냅샷을 사용할 때는 업무 연결 설정에서 검토·게시하고 새 기획을 시작한다. 기존 확인본은 고정된 기준으로 계속 내보낼 수 있다. [API 계약](docs/spec/README.md) · [검증 기록](docs/verification.md)

## H-PlanIT 현업 개편 검증

가상 발주 업무 fixture만 사용한 PostgreSQL/브라우저 검증은 기존 명령과 같다. 시스템에 Chromium 실행 의존성이 필요하다.

```sh
cd frontend
npx playwright install --with-deps chromium
cd ..
sh scripts/e2e.sh
```

실제 모델 평가는 별도의 8013 API와 읽기 전용 `business-live-fixture` 저장소에서 실행한다. 외부 모델 호출 비용이 발생하며, 실제 업무 코드나 운영 데이터를 사용하는 명령이 아니다. 기존 결과를 보존하기 위해 새 출력 파일명을 지정한다.

```sh
python3 scripts/business_live_smoke.py --base-url http://localhost:8013 --output docs/business-live-smoke-new.json
```

이 검증은 명시적 초안 생성·현업 용어·선택 버튼 label만 수정·기준 디자인/확정본 보존을 기록한다. 사람의 현업 적합성 평가는 별도로 수행한다. [최신 계약](docs/spec/README.md) · [검증 기록](docs/verification.md).

승인된 변경안의 **구현 지침**에 현재·제안 동작, 적용·제외 범위, 근거, 구현 순서와 수용 테스트가 있다. **최신 코드 확인**으로 기준 커밋과 비교할 수 있다. 최신 스냅샷으로 이어가려면 **새 코드 기준으로 분기**를 사용한다. 기존 승인본은 같은 기준으로 내보낼 수 있다. [API 계약](docs/spec/README.md) · [검증 요약](docs/verification.md)

### 인증 안정화와 현업 이어하기 (2026-11-23)

업무 카드를 선택해 설명을 작성하고 대화를 정리한 뒤 초안을 만든다. 유형은 첫 설명의 선택사항이다. 전송 전 입력과 직접 편집은 같은 탭에 임시 보관되며 명시적 로그아웃 때 지운다. 일시적인 연결 장애는 로그인 만료와 구분해 재시도할 수 있다. 미전송 내용을 먼저 보낸 뒤 초안을 만들고 현업 확인본을 저장한 후 내려받는다. 목록은 답변·초안 확인·생성 실패 등의 다음 행동을 안내한다.

Compose API는 전용 nginx 네트워크만 신뢰하는 `app.proxy` 런처를 사용한다. Linux Docker의 네트워크 라우팅 정보를 전제로 한다. 운영/기존 서비스를 재시작하거나 실제 DB로 검증하지 않고 `make test`, `make e2e`의 일회성 환경으로 확인한다.
