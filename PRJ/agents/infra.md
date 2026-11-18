# 인프라·실행 개발 안내

기준일: 2026-11-17, 현재 설정 파일의 정적 확인 기준. 포트·모드는 기본 설정이며 현재 실행 상태를 뜻하지 않는다. 먼저 [project.md](project.md)를 읽는다. 명령은 별도 표시가 없으면 `PRJ/`에서 실행한다.

## 구성과 요청 흐름

```text
브라우저 → web nginx (:5174 → :80)
             ├─ 정적 frontend/dist + SPA fallback
             └─ /api/, /health → api (:8000)
호스트 API 접근 (:8010) ───────────┘
api / worker → db PostgreSQL (:5432)
호스트 DB 접근 (:54331) ───────────┘
worker → 모델 공급자 / 허용된 로컬 저장소 / GitHub
```

| 파일·서비스 | 현재 구성 |
| --- | --- |
| `compose.yaml` | 기본 프로젝트명 `planning-studio`, db/api/worker/web |
| `db` | PostgreSQL 17 Alpine, named volume `studio-data`, 호스트 loopback 공개 |
| `api` | backend 이미지, uvicorn `app.main:app`, DB healthcheck 뒤 시작 |
| `worker` | API와 같은 이미지·환경, `python -m app.worker` |
| `web` | frontend 빌드 후 nginx, API healthcheck 뒤 시작 |
| `backend/Dockerfile` | uv/Python 3.12, Git, frozen 서버 의존성, 코드·프롬프트 |
| `infra/frontend.Dockerfile` | Node 24에서 npm ci·build, nginx로 배포 |
| `infra/nginx.conf` | Docker DNS로 API 주소 갱신, API proxy, 300초 read timeout, SPA fallback |
| `infra/repositories.compose.yaml` | opt-in 읽기 전용 `/repositories` 마운트, API·worker에 같이 제공 |
| `infra/supabase.compose.yaml` | opt-in 외부 PostgreSQL 접속, API·worker에 동일 URL 전달, 내장 DB의 자동 실행 해제 |
| `test-db`, `test` | test profile, tmpfs PostgreSQL `studio_test`, mock pytest |

실제 volume 이름은 Compose 프로젝트명에 따라 달라진다. 기본은 `planning-studio_studio-data`다. 사용자 DB volume을 삭제하거나 테스트 대상으로 재사용하지 않는다.

## 서비스 확인과 신규 실행

기존 상태를 먼저 확인한다. `.env` 원문은 로그에 출력하지 않는다.

```sh
docker compose ps
curl -fsS http://localhost:8010/health
```

`/health`는 DB 연결과 API의 인증/AI 모드·공급자·모델을 보여준다. worker 설정·처리 상태는 별도로 확인한다.

처음 설치할 때만 예제 환경 파일을 복사한다. 아래 명령은 기존 `.env`를 덮어쓰지 않는다.

```sh
test -f .env || cp .env.example .env
docker compose up --build -d
```

설정 변경·재기동은 사용자 요청 범위와 서비스 영향을 확인한 뒤 수행한다. 문서·정적 코드 작업 때문에 서비스나 모델 설정을 변경하지 않는다.

## 환경변수 연결

| 설정 | 용도·조건 |
| --- | --- |
| `APP_ENV`, `AUTH_MODE`, `AI_MODE` | 인증·AI는 독립. mock은 local에서만 허용 |
| `LLM_PROVIDER` | openai / openrouter |
| `LLM_MODEL`, `LLM_API_KEY` | 공급자별 모델·키보다 우선 |
| `OPENROUTER_MODEL`, `OPENROUTER_API_KEY`, `OPENAI_MODEL`, `OPENAI_API_KEY` | 서버 공급자 설정. 코드 기본값과 배포값 구분 |
| `DATABASE_URL` | 직접 실행 DB. 기본 Compose는 `db:5432/studio`, Supabase 구성은 Git 제외 `.env.supabase`의 URL을 사용 |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_AUDIENCE` | 실제 로그인·JWT 검증 |
| `LOCAL_REPOSITORY_ROOT` | API·worker의 허용 저장소 루트 |
| `STUDIO_REPOSITORY_HOST_ROOT` | 선택적 마운트의 호스트 절대 경로 |
| `GITHUB_USER_TOKENS`, `GITHUB_LOCAL_TOKEN` | 서버 전용. JWT subject별 매핑 / local 검증용 |
| `LOCAL_SCREEN_PREVIEWS` | local HTTP 미리보기 매핑, config.py 제약 확인 |
| `STUDIO_COMPOSE_PROJECT`, `STUDIO_DB_PORT`, `STUDIO_API_PORT`, `STUDIO_WEB_PORT` | Compose 프로젝트·포트 격리 |

API와 worker는 같은 `.env`와 주요 environment를 사용한다. 프런트엔드 `VITE_*`에는 서버 키·JWT/DB 비밀·GitHub 토큰을 넣지 않는다. 환경변수를 펼치는 `docker compose config` 등의 출력을 기록에 복사하지 않는다.

외부 DB 실행은 [Supabase PostgreSQL 연결](../README.md#supabase-postgresql-연결)을 따른다. Supabase 구성은 Compose의 `!reset`을 지원하는 Docker Compose를 사용한다. DB 비밀번호가 들어간 `.env.supabase`는 Git과 Docker 빌드 컨텍스트에서 제외하고 API·worker의 실행 환경으로만 전달한다.

허용된 로컬 저장소 분석을 활성화하는 예시다. 마운트 경로에는 분석을 허용하는 저장소만 둔다.

```sh
STUDIO_REPOSITORY_HOST_ROOT=/절대경로/허용저장소모음 \
  docker compose -f compose.yaml -f infra/repositories.compose.yaml up --build -d
```

저장소 루트는 앱 소스와 분리하고 읽기 전용으로 유지한다. `repositories.py`의 상한은 파일당 40,000 bytes, 360개, 총 2,400,000 bytes, 모델 발췌 32,000 bytes, 60초다.

## 격리 검증 사용 예시

Backend 테스트는 별도 tmpfs `studio_test`를 사용한다.

```sh
docker compose --profile test run --build --rm test
```

UI·API·worker 통합 검증은 다음을 사용한다.

```sh
sh scripts/e2e.sh
```

스크립트는 `planning-studio-e2e`, 포트 `54332/8011/5175`, mock auth/AI를 사용한다. `.research/` 아래 임시 Git fixture를 읽기 전용으로 마운트하고 의존성·Chromium 설치 뒤 Playwright를 실행한다. 종료 시 해당 컨테이너·임시 fixture를 정리하며 named volume은 삭제하지 않는다. 고정 이름·포트를 사용하므로 병렬 실행하지 않는다.

운영 검증은 [README](../README.md)의 별도 `planning-studio-ops` / `54333/8012/5176` 전제를 따른다. 원본 DB를 덮어쓰지 않고 별도 DB에 복원한다. dump·민감 원시 로그는 Git 제외 경로에 둔다.

## 변경 후 확인

- 해당 이미지 build·healthcheck·프록시·worker 재연결을 검증한다. API 재생성 뒤 프록시 확인 도구는 `scripts/verify_proxy_recovery.py`다.
- migration·재시작·백업 복구는 격리 환경에서 한다. 사용자 volume의 `down -v` / prune을 사용하지 않는다.
- 의존성 변경은 uv.lock / package-lock.json과 frozen 설치를 확인한다.
- 실행법·환경변수·포트 변경은 README.md, .env.example, 이 문서에 반영한다.
- 실제 명령·결과·mock/live·미확인 사항을 저장소 루트의 `.agents/workflow/`에 기록한다.
