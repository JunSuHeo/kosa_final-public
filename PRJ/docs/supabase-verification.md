# Supabase 실계정 검증

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
