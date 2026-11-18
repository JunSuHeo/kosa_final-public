# 기획실 Studio

REA로 매니패스트의 공개 JavaScript를 분석하고 로그인된 편집기의 동작을 관찰한 뒤, 소스 재사용 없이 새로 만든 AI 기획 작업 공간이다. 이전 구현은 별도 보관했다.

아이디어 → 확인 질문 → PRD → 요구사항·기능명세 → 유저플로우 → 와이어프레임 → 수정 검토·승인 → 버전·내보내기를 연결한다. 실제 생성은 OpenRouter/OpenAI의 서버 API를 사용한다. REA는 개발 중 조사 도구이며 서비스 실행에는 필요하지 않다.

## 실행

Docker Desktop이 필요하다. 처음 설치할 때 예제에서 로컬 환경 파일을 만든다.

```sh
test -f .env || (umask 077; cp .env.example .env)
docker compose up --build -d
docker compose ps
curl -f http://localhost:8010/health
```

기존 체크아웃을 갱신할 때는 추적 해제 전에 로컬 `.env`를 안전한 위치에 백업한다. 공용 설정이 필요하면 예제에서 다시 만들고 현재 발급된 값으로 채운다.

- 웹: [http://localhost:5174/](http://localhost:5174/)
- API: [http://localhost:8010/docs](http://localhost:8010/docs)
- DB: localhost:54331, Docker volume `planning-studio_studio-data`
- 소스: `frontend/`, `backend/app/`, `backend/migrations/`, `prompts/`

`.env.example`의 기본값은 로컬 인증과 명시적 AI 데모다. 화면에 해당 모드가 표시된다. mock은 `APP_ENV=local`에서만 실행할 수 있다.

## Supabase PostgreSQL 연결

1. Supabase 프로젝트의 **Connect → Session pooler**에서 포트 `5432` 연결 문자열을 복사한다. 실행 환경에서 직접 접속이 가능하면 **Direct connection**도 사용할 수 있다. worker가 PostgreSQL 세션 잠금을 사용하므로 **Transaction pooler**는 사용하지 않는다. [Supabase 연결 가이드](https://supabase.com/docs/guides/database/connecting-to-postgres)
2. 아래 명령으로 비밀 파일을 준비한다. `.env.supabase`의 `DATABASE_URL`에 연결 문자열을 작은따옴표로 감싸 넣는다. DB 비밀번호의 특수문자를 URL 인코딩하고 `sslmode=require`를 지정한다. 첫 실행에서 테이블을 만들므로 대상 스키마에 DDL 권한이 있고 생성한 테이블을 소유하는 DB 계정을 사용한다.

   ```sh
   test -f .env.supabase || (umask 077; cp .env.supabase.example .env.supabase)
   ```

3. `PRJ/`에서 Supabase 전용 Compose 구성을 실행한다. 아래 예시는 기본 로컬 인스턴스와 별도로 띄우기 위해 다른 프로젝트명과 포트를 사용한다.

   ```sh
   STUDIO_API_PORT=8014 STUDIO_WEB_PORT=5178 docker compose -p planning-studio-supabase \
     --env-file .env --env-file .env.supabase \
     -f compose.yaml -f infra/supabase.compose.yaml up --build -d
   curl -fsS http://localhost:8014/health
   ```

   웹은 [http://localhost:5178/](http://localhost:5178/)에서 연다. `/health`의 `database: ready`로 API의 DB 연결을 확인한다. 프로젝트를 생성해 worker가 확인 질문을 저장하는지 확인한다.

API와 worker는 동일한 DB에 연결하고 시작할 때 [SQL 마이그레이션](backend/migrations/)을 적용한다. 앱 테이블은 RLS를 켜고 브라우저 역할에 대한 정책을 만들지 않는다. 전용 Supabase 프로젝트에 다른 Data API 소비자가 없다면 Data API를 끌 수 있다. [Supabase Data API 보안 가이드](https://supabase.com/docs/guides/api/securing-your-api)

Supabase DB와 [Supabase 로그인](#인증)은 별개다. 동일 인스턴스에서 실제 로그인도 쓰려면 `.env.supabase`에 해당 인증 설정을 함께 넣는다. 기존 로컬 프로젝트 데이터 이전은 별도 작업이다. 기본 Docker 실행으로 돌아갈 때는 [기본 실행 명령](#실행)을 사용한다.

## 실제 AI

서버 `.env`에서 설정한다. 키를 프런트엔드 또는 `VITE_*` 변수에 넣지 않는다.

```dotenv
APP_ENV=local
AUTH_MODE=mock
AI_MODE=live
LLM_PROVIDER=openrouter
OPENROUTER_MODEL=openai/gpt-6.1-sol
OPENROUTER_API_KEY=서버에서만_사용할_키
```

기존 `LLM_API_KEY`와 `LLM_MODEL`도 지원하며 공급자별 키/모델보다 우선한다. 공급자를 바꿀 때 일반 키와 모델도 함께 변경한다. OpenAI는 `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_MODEL`을 사용한다.

```sh
docker compose up --build -d api worker
```

실패한 실제 호출을 mock으로 대체하지 않는다. 실행에 AI 모드·공급자·모델을 고정하며, 설정을 바꾼 뒤 이전 실행을 이어서 처리하지 않는다. 실제 모델 출력은 서버에서 JSON schema와 항목 연결을 검증한다. 연결 오류의 보정은 최대 한 번이다.

## 사용

1. 홈에서 아이디어를 입력하고 기획을 시작한다.
2. 채팅의 확인 질문에 답하거나, AI가 가정하고 진행하도록 선택한다.
3. 생성된 네 산출물을 탭으로 확인한다. 기능명세는 그래프·디렉토리·문서 보기를 제공한다.
4. 와이어프레임은 전체 목록/단일 화면을 전환한다. 미리보기에서 연결된 버튼으로 화면을 이동한다.
5. `직접 편집`에서 PRD·기능 상세·흐름 노드 위치·화면 제목/기기·요소 내용/순서/연결을 고친다. `수정안 검토`로 새 proposal을 만든다.
6. 검토에서 diff와 경고를 확인하고 승인한다. 승인 전에는 기존 확정본과 current_version이 변하지 않는다.
7. 확정 후 AI에 수정을 요청할 수 있다. 선택한 문서/기능/화면 요소를 채팅에 연결할 수 있다.
8. 버전에서 과거 확정본을 조회하거나 복원 proposal을 만든다. 내보내기는 선택한 확정 버전의 Markdown/JSON을 다운로드한다.

새로고침과 재접속 후에도 프로젝트·질문·메시지·proposal·확정본이 PostgreSQL에 유지된다. worker 재시작은 저장된 단계부터 재개한다. DB 결과는 중복 생성하지 않지만, 저장 직전에 중단된 외부 모델 호출은 다시 일어날 수 있다.

## 인증

실제 인증은 `AUTH_MODE=supabase`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_AUDIENCE`로 설정한다. 등록된 Supabase 계정의 이메일/비밀번호로 로그인한다. 서버는 JWKS와 RS256/ES256 서명, issuer/audience/sub/iat/exp를 확인한다. 토큰 만료 시 다시 로그인한다. 회원가입·조직·초대는 이번 범위에 없다.

mock 인증은 로컬 UI 검증 전용이다. 모든 API는 서버에서 소유권을 검사한다. 인증 오류는 401, 없는/다른 소유자의 리소스는 동일한 404, 버전·멱등성 충돌은 409다.

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

Frontend 재현 설치와 빌드:

```sh
cd frontend
npm ci
npm run build
```

격리된 mock E2E는 루트에서 다음을 실행한다. 별도의 Compose 프로젝트·DB volume과 5175/8011/54332 포트를 사용한다. 종료 시 테스트 컨테이너를 내리며 사용자 서비스에는 영향을 주지 않는다.

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

## 저장소를 기준으로 기획하기

홈에서 **기준 프로젝트 등록**으로 GitHub URL과 브랜치를 등록하거나 허용된 로컬 저장소의 상대 경로를 입력한다. 로컬 저장소는 Git 메타데이터를 가진 일반 체크아웃을 지원한다. 대규모 저장소에는 `frontend/src`처럼 분석에서 먼저 읽을 경로를 지정할 수 있다.

로컬 분석을 사용할 때는 별도 읽기 전용 마운트를 연결한다. 마운트 대상에는 분석을 허용하는 저장소만 둔다.

```sh
STUDIO_REPOSITORY_HOST_ROOT=/절대경로/저장소모음 \
  docker compose -f compose.yaml -f infra/repositories.compose.yaml up --build -d
```

호스트에서 API와 worker를 실행할 때는 두 프로세스에 동일한 `LOCAL_REPOSITORY_ROOT`를 설정한다. GitHub 공개 저장소는 토큰 없이 읽을 수 있다. 비공개 저장소에는 읽기 전용 Contents 권한을 연결한다. 서버 관리자가 `GITHUB_USER_TOKENS`에 실제 JWT subject별 토큰을 매핑한다. `GITHUB_LOCAL_TOKEN`은 로컬 mock의 기본 웹 사용자만 사용하는 검증용이다. 이 값은 서버 환경에만 둔다.

분석을 시작하면 branch에서 확인한 커밋만 읽는다. 워킹 트리의 미커밋 변경은 상태에 표시한다. 개별 파일 40KB, 최대 360개, 총 2.4MB, 분석 60초, 모델 발췌 32KB를 상한으로 적용한다. 읽기 상한·제외 규칙·민감 패턴에 해당하는 파일은 분석 결과에 사유를 기록한다. 등록과 분석은 저장소의 설치 스크립트와 애플리케이션을 실행하지 않는다.

기획 시작 전 코드 범위를 확인한다. live 모델은 표시된 발췌를 전송하며, Studio는 고정 기준과 발췌를 기획·검토 기록에 보관한다. 공급자에서의 처리와 보관은 해당 공급자 설정과 정책을 따른다. 민감 패턴 검사는 자동 필터이므로 비공개 저장소를 전송하기 전에 발췌를 검토한다.

승인된 변경안의 **구현 지침**에 현재·제안 동작, 적용·제외 범위, 근거, 구현 순서와 수용 테스트가 있다. **최신 코드 확인**으로 기준 커밋과 비교할 수 있다. 최신 스냅샷으로 이어가려면 **새 코드 기준으로 분기**를 사용한다. 기존 승인본은 같은 기준으로 내보낼 수 있다. [API 계약](docs/spec/README.md) · [검증 요약](docs/verification.md)
