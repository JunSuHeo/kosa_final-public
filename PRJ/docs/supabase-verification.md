# Supabase 실계정 검증

## DB 계정 통일 검증 (2026-11-20)

브라우저 계정 구현을 제거한 뒤 관리형 Supabase의 `admin`/`user1`/`user2`를 각각 ADMINISTRATOR/USER1/USER2로 구성했다. 사용자 지정 공통 테스트 비밀번호는 `seed-test-accounts --password-file … --reset-passwords`로 적용했으며 Git 제외 `.env.supabase.test-password`와 `.env.supabase.admin-password`는 권한 0600이다. 기존 관리자 ID, 기획 ID·소유자·확정 버전이 동일함을 적용 전후 비교했다.

실제 실행한 검증:

- `make test`: 격리 PostgreSQL에서 **61 passed**, 기존 TestClient deprecation warning 1건. 신규 테스트는 빈 DB의 세 계정 생성, 중복 방지, 기존 비밀번호·이름·정책·기획 보존, 명시적 재설정의 세션 해제, 역할 충돌 및 nonlocal 실행 거부를 확인했다.
- `npm run build`와 Compose 프런트엔드 빌드: 통과. `check_contracts.py`: **3 generated contracts and 2 examples verified**. 기존 계정 API의 누락된 OpenAPI 계약도 동기화했다.
- 최종 격리 Playwright E2E: **23 passed**. 실제 앱 API·DB와 테스트 전용 ES256 Auth를 사용하며 DB/Auth 상태는 각 테스트마다 초기화했다. 로그인·계정 CRUD·마지막 관리자 보호·권한 정책·타 탭 세션 해제·브라우저 저장소 변조 차단·새 브라우저 로그인·업무 배정·기획 생성/승인/복원/내보내기를 검증했다.
- 전환 중 계정 관리 폼의 추가 필드 때문에 발생한 422를 서버 계약에 맞춘 요청 구성으로 수정했다. 서버 작업 중 내보내기 요청이 무시되는 문제는 작업 중 버튼 비활성화로 수정했다. 테스트의 대화 완료 대기를 보완했고, 호스트 시각 역행에 따른 fixture JWT의 미래 iat는 테스트 토큰 발급 시각만 5초 앞당겨 해결했다. 제품 JWT 검증은 완화하지 않았다.
- `make ps`, `make up`: 기존 `planning-studio-supabase` 프로젝트와 웹 5178/API 8014를 재사용했고 API·worker·web이 정상 기동했다. 기존 로컬 서비스는 변경하지 않았다.
- 실제 Supabase API에서 세 계정 로그인, 관리자 계정/정책 조회, 일반 계정 관리자 API 403·타인/없는 기획 404, USER1 작성 권한 해제 시 생성 403, USER2 사용 중지 시 세션 401, 로그아웃 후 401 및 `local:` 토큰 거부를 확인했다. 검증 중 변경한 역할 정책·계정 정보·활성 상태는 원래 값으로 복원했다.
- 실제 Supabase에 연결한 Chromium의 서로 다른 브라우저 context에서 세 계정 로그인·역할 표시·새로고침 복원·로그아웃을 확인했다. admin의 계정 관리 화면에 세 계정이 표시되고 일반 계정에는 관리자 메뉴가 없었다. 비밀번호·인증 trace 없이 관리자 화면만 `.research/screenshots/db-accounts.png`에 보존했다.

AI는 mock이며 실제 모델 호출은 하지 않았다. 자연 만료된 실제 JWT에 대한 401과 운영 데이터 이전은 이번 검증 범위가 아니다. 실패한 중간 E2E의 진단은 Git 제외 `.research/`에 보존하고, 통과한 전용 테스트 컨테이너·볼륨·이미지는 정리했다.

## 관리형 Supabase 연결 검증 (2026-11-20)

실제 관리형 Supabase DB 및 Auth와 별도 Compose 프로젝트 `planning-studio-supabase`를 사용했다. `APP_ENV=local`, `AUTH_MODE=supabase`, `AUTO_MIGRATE=false`, `AI_MODE=mock`이며 실제 모델은 호출하지 않았다. 기존 로컬 DB와 서비스는 보존하고 데이터 이전 없이 시작했다.

실제 실행한 검증:

- `docker compose -p planning-studio-supabase-check --profile test run --build --rm test`: 별도 tmpfs PostgreSQL의 백엔드 테스트 **58 passed**. Starlette의 TestClient 관련 deprecation warning 1건.
- 관리형 DB의 기존 앱 테이블이 비어 있음을 읽기 전용으로 확인하고 `app.manage`의 `migrate`, `runtime-role`, `bootstrap-admin`을 실행했다. 앱→Session pooler TLS가 활성화됐고 Auth JWKS는 ES256, 관리자 키 조회는 HTTP 200이었다.
- 전용 실행 계정은 superuser가 아니며 public 스키마 생성 권한 없이 앱 테이블에 접근했다. API/worker는 같은 DB와 모드를 사용하고 관리/이전 연결은 비어 있다. worker의 Auth 관리자 키도 비어 있다.
- 웹 프록시 `/health`: HTTP 200, `database=ready`, `auth_mode=supabase`, `ai_mode=mock`.
- 실제 `admin` 로그인과 계정·정책·감사 조회: HTTP 200. 생성→worker 질문→답변→수정안→승인으로 v1 저장, 재조회 및 Markdown/JSON 내보내기를 확인했다. 5개 역할 검토도 완료됐다.
- 별도 일반 계정에서 관리자 기획·revision·export·역할 검토·존재하지 않는 기획 조회는 모두 404, 계정 관리 조회는 403이었다. 검증 계정은 종료 시 비활성화했고 기존 세션은 401이었다.
- 미인증·잘못된 토큰은 401. 실제 refresh token 갱신 후 저장 기획 조회, 로그아웃 후 접근 및 refresh 차단(401)을 확인했다.
- Playwright Chromium으로 실제 로그인 화면→관리 메뉴→계정 관리→새로고침을 검증했다. 브라우저 저장소의 만료 시각을 앞당긴 뒤 실제 Auth 갱신과 화면 복원을 확인했고, 로그아웃 후 로그인 화면 및 저장소의 세션 삭제를 확인했다. 비밀번호·토큰·인증 요청 trace는 기록하지 않았다.

검증용 기획 `Supabase 연결 검증`의 확정 v1과 비활성 검증 계정은 감사 근거로 남겨 두었다. 자연 만료된 실제 JWT에 대한 401과 만료 후 수동 재로그인, 실제 모델 호출, 운영 데이터 이전은 이번에 검증하지 않았다. 초기 관리자 비밀번호는 Git 제외 `.env.supabase.admin-password`에 있으며 비밀값을 이 문서에 기록하지 않는다. 실행 명령은 [README](../README.md#supabase-postgresql-연결)를 따른다.

## 기존 자체 호스팅 검증과 추가 검증 절차

2026-11-10 격리 자체 호스팅 Supabase Auth v2.197.0에 임시 계정 두 개를 생성해 브라우저에서 이메일/비밀번호 로그인을 검증했다. Auth가 발급한 ES256 토큰으로 기획을 생성·승인하고 역할 5개를 완료했다. 다른 계정 또는 존재하지 않는 대상에 대한 8개 접근이 404였다. 인증 헤더 없음·잘못된 토큰·실제 만료 토큰은 401이었고, 만료 뒤 로그인 화면에서 재인증하면 기존 v1이 복원됐다. 결과 JSON(`supabase-self-hosted-verification.json`)

아래 절차는 외부 관리형 Supabase 프로젝트에서 같은 시나리오를 확인할 때 사용한다. 자체 호스팅의 서명 키는 Supabase의 ES256 설정을 사용했다. [Supabase 자체 호스팅 인증 키 문서](https://supabase.com/docs/guides/self-hosting/self-hosted-auth-keys)

## 필요한 입력

- 테스트용 Supabase 프로젝트 URL과 anon key.
- 서로 다른 테스트 계정 2개. 이메일 확인 등 프로젝트의 로그인 조건을 충족해야 한다.
- 계정 비밀번호는 사용자가 로그인 화면에 직접 입력한다. 채팅·문서·실행 로그에 비밀번호나 토큰을 남기지 않는다.

URL과 anon key는 Git 제외 `.env`의 `SUPABASE_URL`, `SUPABASE_ANON_KEY`에 설정한다. 실제 JWT/JWKS 계약에 맞는 프로젝트를 사용한다.

## 검증 환경

제품의 로컬 인증을 바꾸기 전에 별도 Compose 프로젝트에서 검증한다. 모델 호출이 목적이 아니므로 `AI_MODE=mock`을 명시한다.

```sh
STUDIO_COMPOSE_PROJECT=planning-studio-auth STUDIO_DB_PORT=54334 STUDIO_API_PORT=8013 STUDIO_WEB_PORT=5177 APP_ENV=local AUTH_MODE=supabase AI_MODE=mock docker compose up --build -d db api worker web
```

테스트 UI는 `http://localhost:5177/`이다. 두 계정은 서로 다른 브라우저 프로필/시크릿 창에서 사용한다.

## 관리형 프로젝트에서 확인할 항목

- [ ] 계정 A 로그인 후 프로젝트 생성·질문 응답·초안 조회·승인·역할 검토가 동작한다.
- [ ] 새로고침 후 동일 계정의 프로젝트가 유지된다.
- [ ] 계정 B 로그인 후 A의 프로젝트·revision·proposal·job·역할 검토 API 접근이 404다.
- [ ] 존재하지 않는 ID도 같은 404를 반환해 소유권 정보를 노출하지 않는다.
- [ ] 인증 헤더 없음·잘못된 토큰·실제 만료 토큰은 401이다.
- [ ] 만료 시 로그인 UI로 돌아가고 다시 로그인한 뒤 계정의 저장 상태를 조회할 수 있다.

완료 시 계정 A/B라는 별칭, 상태 코드, 수행 시각, 화면 동작만 검증 기록에 남긴다. 실계정 준비 전에는 위 항목을 완료로 표시하지 않는다.

검증을 마치면 아래 명령으로 전용 컨테이너만 종료한다. 제품 컨테이너와 볼륨은 영향을 받지 않는다.

```sh
STUDIO_COMPOSE_PROJECT=planning-studio-auth docker compose down
```
