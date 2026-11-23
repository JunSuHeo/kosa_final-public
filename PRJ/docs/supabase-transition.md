# Supabase 전환 인계

2026-11-20 기준으로 Supabase 전환 기능이 추가됐다. 같은 날 이 체크아웃에서 관리형 Supabase DB·실제 인증 연결을 검증했다. 기존 로컬 데이터를 이전하지 않고 새 DB로 시작했으며 기존 로컬 서비스는 보존했다. 운영 데이터 이전은 별도 검증이 필요하다.

## 현재 체크아웃의 연결 결과

- 기존 앱 테이블이 없는 대상을 확인한 뒤 001~007 migration을 적용했다.
- `hplanit_app` 로그인에 `studio_runtime`을 부여했다. TLS 접속·앱 테이블 접근이 가능하고 superuser 및 public 스키마 생성 권한은 없다.
- `.env.supabase`의 `DATABASE_URL`은 전용 실행 계정, `MIGRATION_DATABASE_URL`은 관리 계정으로 분리했다. 초기 `admin` 비밀번호는 Git 제외 `.env.supabase.admin-password`에 권한 0600으로 저장했다.
- `planning-studio-supabase`의 웹 5178/API 8014에서 `AUTH_MODE=supabase`, `AUTO_MIGRATE=false`, `AI_MODE=mock`으로 실행했다. 기존 5174/8010 서비스는 변경하지 않았다.
- 실제 인증·데이터 저장·권한·세션·브라우저 검증 결과는 [실계정 검증](supabase-verification.md#관리형-supabase-연결-검증-2026-11-20)에 기록했다.

## DB 테스트 계정 관리

브라우저 계정 구현을 제거하고 서버 계정 API로 통일했다. `admin`(ADMINISTRATOR), `user1`(USER1), `user2`(USER2)는 `python -m app.manage seed-test-accounts`로 명시적으로 구성한다. local Supabase 환경만 허용하고 비밀번호는 대화형 또는 `--password-file`로 전달한다. 일반 재실행은 기존 계정 ID·비밀번호·정책을 유지하며 `--reset-passwords`만 기존 비밀번호와 세션을 변경한다. 기존 역할·활성 상태가 예상과 다르면 자동 덮어쓰지 않는다. 앱 시작 시 자동 생성·초기화하지 않는다.

`make up/ps/logs/down`은 `.env.supabase`와 기존 Supabase 구성을 사용한다. 이 장비는 Git 제외 설정의 프로젝트명·포트로 기존 5178/8014 앱을 재사용한다. 백엔드 단위 테스트만 mock Bearer를 유지하고 브라우저 E2E는 별도 DB와 ES256 Auth fixture를 사용한다. Auth fixture는 테스트 구성에만 마운트하며 제품 API에 초기화 경로를 추가하지 않는다.

## 포함된 변경

- FastAPI·Worker를 유지하고 Supabase ID 로그인·계정·정책·세션·감사 API를 추가했다.
- 기존 비동기 AccountService에 서버 구현을 추가하고 실제 인증 모드의 관리자 메뉴를 연결했다.
- 006·007 SQL은 계정 관련 테이블, 서버 실행 역할·RLS, 지연 가능한 FK를 추가한다.
- `python -m app.manage`는 `migrate`, `runtime-role`, `bootstrap-admin`, `recover-admin`, `transfer` 명령을 제공한다. 초기 비밀번호는 대화형 입력 또는 `--password-file`로 받는다.
- `transfer`는 별도 원본/대상 DB에서 기본 dry-run으로 동작한다. 명시적 `--apply`만 이전을 수행하며 대상 앱 테이블이 비어 있어야 한다. `SOURCE_DATABASE_URL`은 환경 파일로 전달하고 `--transfer-id`는 재시도에 같은 UUID를 사용한다.
- 실제 이전 시 기획과 연결 업무 소유권은 기존 admin 내부 ID로 통합한다. 일반 사용자 배정은 제거한다. 불변 revision·publication 문서는 그대로 보존한다.

## 향후 운영 데이터 이전이 필요한 경우

아래는 기존 운영 데이터를 이전할 때의 별도 절차다. 현재 체크아웃은 새 DB로 시작했으므로 이 절차의 이전 명령을 실행하지 않았다.

1. 운영 적용 전 별도 코드 리뷰를 수행한다.
2. 실제 환경의 Supabase Auth URL·일반 키·관리자 키 확인. 비밀값은 Git·로그·작업 기록에 넣지 않는다.
3. 명시적 migration 및 전용 runtime DB 로그인 생성. API와 worker에 DDL 연결을 사용하지 않는다.
4. 원본 쓰기 중지·작업 완료·백업 후 이전 dry-run과 실제 이전. 원본 로컬 DB는 유지한다.
5. admin 실제 Auth 계정 생성, 실제 로그인·세션 해제·관리 기능·저장/내보내기 검증 후 로컬 앱 전환.
6. 기존 README와 API 계약 문서를 운영 전환 결과에 맞게 최종 정리한다.

## 실행 전 주의

- Session pooler 또는 직접 연결을 사용한다. Worker 세션 잠금을 transaction pooler에 연결하지 않는다.
- `infra/supabase.compose.yaml`은 `AUTH_MODE=supabase`, `AUTO_MIGRATE=false`를 적용한다. 과거 README의 "시작 시 migration 실행" 설명은 이 모드에는 해당하지 않는다.
- 관리 명령은 Supabase 설정 파일을 사용하는 `manage` 서비스에서 실행한다. API·Worker 실행과 분리한다.
- 기존 브라우저 목업 계정·비밀번호 검증값을 실제 Auth 계정으로 자동 이전하지 않는다. 초기 계정은 admin 하나다.
