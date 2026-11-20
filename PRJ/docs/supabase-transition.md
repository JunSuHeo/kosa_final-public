# Supabase 전환 인계

2026-11-20 기준으로 Supabase 전환 기능이 추가됐다. 운영 DB 이전과 실제 인증 전환은 별도 검증이 필요하다.

## 포함된 변경

- FastAPI·Worker를 유지하고 Supabase ID 로그인·계정·정책·세션·감사 API를 추가했다.
- 기존 비동기 AccountService에 서버 구현을 추가하고 실제 인증 모드의 관리자 메뉴를 연결했다.
- 006·007 SQL은 계정 관련 테이블, 서버 실행 역할·RLS, 지연 가능한 FK를 추가한다.
- `python -m app.manage`는 `migrate`, `runtime-role`, `bootstrap-admin`, `recover-admin`, `transfer` 명령을 제공한다. 초기 비밀번호는 대화형 입력 또는 `--password-file`로 받는다.
- `transfer`는 별도 원본/대상 DB에서 기본 dry-run으로 동작한다. 명시적 `--apply`만 이전을 수행하며 대상 앱 테이블이 비어 있어야 한다. `SOURCE_DATABASE_URL`은 환경 파일로 전달하고 `--transfer-id`는 재시도에 같은 UUID를 사용한다.
- 실제 이전 시 기획과 연결 업무 소유권은 기존 admin 내부 ID로 통합한다. 일반 사용자 배정은 제거한다. 불변 revision·publication 문서는 그대로 보존한다.

## 아직 필요한 작업

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
