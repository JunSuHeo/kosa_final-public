# Supabase PostgreSQL 연결 준비

- 날짜: 2026-11-18 (Asia/Seoul)
- 상태: 연결 준비 완료
- 담당 팀원: JS
- 참여 AI 에이전트·담당 범위: Codex, 실행 구성·DB migration·문서·격리 검증
- 기준: `main`, `bc17958`. 연결된 Issue/PR 없음.
- 요청·목표: 기획실 Studio의 API와 worker가 Supabase PostgreSQL을 사용할 수 있도록 설정한다.
- 완료 조건: 기본 Docker 실행 유지, 별도 Supabase 구성에서 API와 worker에 외부 DB 연결값 전달, 앱 테이블 초기화 및 격리 검증.

## 계획

1. 실행 설정·SQL·세션 잠금을 확인한다.
2. Supabase용 설정, 테이블 접근 제한과 실행 안내를 추가한다.
3. Compose 구성과 격리 PostgreSQL에서 마이그레이션·서비스 동작을 검증한다.

## 판단·변경

- `PRJ/compose.yaml`은 API와 worker를 내장 PostgreSQL에 고정한다. 기본 구성을 유지하고 `PRJ/infra/supabase.compose.yaml`에서만 두 서비스의 DSN과 DB 의존성을 바꿨다. worker는 세션 잠금을 사용하므로 Session pooler 또는 Direct connection을 쓴다.
- `PRJ/.env.supabase.example`에서 연결값의 형식을 안내한다. 추적 중인 `PRJ/.env` 대신 권한 600의 로컬 `PRJ/.env.supabase`를 준비하고 Git과 Docker 컨텍스트에서 제외했다.
- `PRJ/backend/migrations/004_studio_row_security.sql`은 앱 테이블 9개의 RLS를 켠다. 서버는 테이블 소유자로 연결하며 브라우저 역할에는 정책을 제공하지 않는다.
- `PRJ/README.md`, `PRJ/agents/infra.md`, `PRJ/agents/backend.md`에 실행·권한 조건을 기록했다.

## 검증

| 실행 위치 | 실제 검사 | 결과 |
| --- | --- | --- |
| PRJ/ | 기본 및 Supabase Compose `config --format json`의 서비스·DB URL·의존성 확인, 빈 값으로 `config -q` | 기본 연결 유지, 별도 구성은 API와 worker에 같은 URL을 전달, 내장 DB 자동 실행 해제, web에는 DB 값 미전달, 빈 URL은 오류 |
| PRJ/ | `docker compose -p planning-studio-sbtest --profile test run --build --rm test` | 격리 PostgreSQL과 mock 인증/AI에서 35개 통과. Starlette TestClient 의존성 deprecation 경고 1건 |
| PRJ/ | 격리 프로젝트 `planning-studio-sbsmoke` 및 `planning-studio-sbowner`에서 Supabase 구성으로 API·worker 기동, HTTP·psql 확인 | `/health`, 프로젝트와 확인 질문 저장, 슈퍼유저 권한 없는 테이블 소유자 초기화, 테이블 9개 RLS, SELECT 권한만 있는 anon의 행 조회 차단 확인 |
| 저장소 루트 | `git diff --check`, 새 파일 및 문서 링크 확인, `git check-ignore PRJ/.env.supabase` | 통과 |

## 결과·인계

- 격리된 테스트 컨테이너는 정리했다. 기존 서비스 설정과 로컬 DB는 유지했다.
- 실제 Supabase DSN, TLS 및 관리형 pooler 연결은 미검증이다. `PRJ/.env.supabase`의 `DATABASE_URL`을 채운 후 [연결 절차](../../../../PRJ/README.md#supabase-postgresql-연결)를 따른다. 기존 데이터 이관은 별도 작업이다.
- 이번 작업은 로컬 미커밋 상태다. 작업 시작 전부터 루트 하네스와 `PRJ/AGENTS.md`, `PRJ/agents/`에 별도 변경이 있었다.
