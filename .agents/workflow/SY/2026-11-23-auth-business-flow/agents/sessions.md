# Task 2: 프런트 세션 안정성과 감사 이력

- 날짜: 2026-11-23 (Asia/Seoul)
- 담당 팀원: SY
- 참여 AI: sessions
- 상태: 구현 및 담당 범위 검증 완료
- 대표 기록: [작업 README](../README.md)
- 목표: 일시 인증 장애가 현재 입력·화면을 지우지 않도록 하고, 재인증 후 같은 재설정 작업을 재시도하며 감사 이력 200개 이후를 조회한다.
- 담당 파일: `PRJ/frontend/src/accounts/*`, `PRJ/frontend/src/api.ts`, `PRJ/frontend/src/UserManagement.tsx`, `PRJ/frontend/tests/supabase-accounts.spec.ts`.
- 의존성: root가 App의 시작 재시도 화면, 강제 401 무효화와 명시 로그아웃 구분, 제품 문서를 맡는다. backend가 감사 응답의 `next: string | null`과 구조화된 불명확 변경 오류를 맡는다.

## 읽은 근거와 계획

`AGENTS.md`, `PRJ/AGENTS.md`, `PRJ/rules/project.md`, `PRJ/rules/frontend.md`, 관련 소스·기존 Supabase UI 테스트, TDD·systematic-debugging·verification-before-completion 스킬을 확인했다. `.agent-local.md`는 분리 작업 공간에 없으며 대표 작업의 명시 담당 SY를 적용했다.

1. 실제 UI/API 경계 테스트로 장애·누락을 재현한다.
2. 마지막 서버 확인 identity 유지, 복구 상태, 재설정 작업 ID 보존, 감사 페이지를 최소 변경한다.
3. 같은 테스트 전체와 TypeScript/Vite 빌드를 실행한다.

## 확인과 결정

- 원인: `useAuth`의 예외 처리에서 모든 오류에 `authed=false`를 적용했다. `current()` 자체는 401에서만 서버 세션을 지우고 있었다.
- 일시 오류에는 마지막 확인 identity와 authed를 유지한다. 시작 단계에서 identity를 확인하지 못하면 `unavailable=true`, `recovering`, `retry()`를 App에 제공한다. 저장된 가짜 identity를 읽지 않는다.
- 요청 세대를 사용해 앞선 sync 응답이 뒤의 로그인·로그아웃 상태를 덮지 않도록 한다. 실제 App의 명시 로그아웃은 완료 후 페이지를 교체한다.
- `logout(options?: { explicit?: boolean })`은 기본 명시 로그아웃이다. `explicit:false`는 서버 로그아웃 호출을 생략하고 로컬 자격만 지워 미완료 작업 ID를 보존한다. 작업 성공은 기존처럼 해당 ID를 지운다.
- `api()`는 문자열 `detail`과 구조화된 `detail.message`를 표시한다. 객체 전체나 민감 요청값은 표시하지 않는다.
- `audit(cursor?: string): Promise<AuditPage>`에서 `AuditPage={items:AuditEntry[],next:string|null}`이다. 서버의 기존 `before` 쿼리 키를 유지하며 `Number`로 변환하지 않는다.
- 감사 UI는 ID로 중복을 제거해 과거 항목을 추가한다. 최신 페이지를 재조회해도 이미 읽은 과거 이력과 현재 커서는 유지한다. 동시 감사 요청을 막고, 실패해도 목록·커서를 보존한다. 로딩·오류·재시도 상태를 표시하며 401만 상위 인증 해제에 전달한다.

## 검증

모든 브라우저 인증/API 응답은 Playwright route fixture다. 실제 서비스 DB, Supabase, 외부 모델은 호출하지 않았다.

- RED: 신규 5개 테스트가 기존 코드에서 예상대로 실패했다. network/429/503 후 계정 관리 화면 소실, 시작 재시도 부재, 200개 이후 버튼 부재를 확인했다.
- RED: 불명확 비밀번호 변경 오류가 일반 입력 오류로 표시됐다. 오류 메시지 처리 후에는 같은 테스트에서 강제 재인증 뒤 작업 ID가 달라지는 실패를 별도로 확인했다.
- 첫 브라우저 실행은 `libnspr4.so` 부재로 시작하지 못했다. 기존 `/tmp/kosa-push-browser-libs/extracted/usr/lib/x86_64-linux-gnu`를 `LD_LIBRARY_PATH`에 지정하고 실행했다. 격리 Vite 포트 5181을 사용했다.
- 최종 명령(저장소 루트): `LD_LIBRARY_PATH=/tmp/kosa-push-browser-libs/extracted/usr/lib/x86_64-linux-gnu E2E_BASE_URL=http://127.0.0.1:5181 npm --prefix PRJ/frontend run test:e2e -- tests/supabase-accounts.spec.ts --output=/tmp/kosa-auth-sessions-final`
- 결과: **8 passed (17.9s), exit 0**. 기존 관리자 로그인·갱신·명시 로그아웃, 모바일 관리자 차단·401 무효화, 3종 일시 오류의 화면·입력 보존, 시작 재시도·가짜 identity 차단, 201개 이력·중복 제거·동일 커서 재시도, 불명확 변경 안내·강제 재인증 후 동일 operation ID·성공 후 ID 제거를 포함한다.
- 감사 fixture는 JS 안전 정수보다 큰 `9007199254740993` 문자열이 `before`에 그대로 전달되는지 확인한다.
- `PRJ/frontend`에서 `npm run build`: **exit 0**. TypeScript와 Vite production build 통과.
- 병렬 Playwright 실행의 공용 test-results 정리 충돌을 확인해 후속 실행은 별도 `/tmp` output을 사용했다.

## 단계별 인계

담당 구현·검증을 root에 전달했다. root는 통합 backend/계약/E2E 검증과 제품 문서 갱신을 계속한다. 커밋·푸시·배포는 하지 않았다. 실제 Supabase 및 외부 모델 검증은 이번 담당 범위에서 미실행이다.

## 독립 리뷰 수정 1차

[인증·감사 리뷰](review-auth.md)의 필수 수정 3건을 반영했다. root가 이 수정 라운드를 위임했으며 backend 담당자는 관련 파일 소유권을 해제했다.

### 재현과 구현

1. 감사 이력 201건 급증 후 최신 페이지와 기존 목록의 공통 ID가 없어도 이전 커서를 유지하면 중간 항목이 빠졌다. 신규 테스트는 200개 예상에 기존 코드가 400개를 병합하는 RED를 확인했다. 공통 ID가 없는 최신 페이지는 목록과 커서를 함께 새 경계로 교체하고 안내한다. 공통 ID가 있는 일반 새로고침은 읽은 과거 목록과 커서를 유지한다. 신규 테스트는 201건 급증 뒤 전체 이력을 다시 읽고, 중간에 겹치는 최신 기록 1건을 추가해도 마지막 과거 항목까지 빠짐없이 읽는지 검증한다.
2. 오래된 reset에 더 새 작업이 있으면 backend가 HTTP409 `detail.code=account_operation_superseded`와 재제출 안내를 반환한다. `ApiError.code`로 이 경우만 구분해 이전 ID와 메모리 입력을 제거한다. 자동 재전송은 하지 않으며 다음 사용자 제출은 새 ID를 발급한다. 기존 최신 비밀번호 보호 테스트는 구조화된 code가 없어 RED인 뒤 GREEN을 확인했다.
3. 비밀번호를 바꾸거나 페이지를 다시 열어 입력의 동일성을 확인하지 못할 때 기존 완료 작업 ID를 재사용하면 거짓 성공이 발생했다. create/reset 각각 변경 입력과 전체 새로고침을 재현한 4개 테스트가 기존 ID 재사용으로 RED였다. 이제 모듈 메모리의 원래 `{id,password}`가 현재 저장 ID 및 입력과 정확히 일치할 때만 같은 ID를 재사용한다. 입력이 달라지거나 새로고침으로 메모리가 사라지면 새 UUID를 사용한다. 같은 SPA의 401 재인증에서는 메모리를 유지하므로 동일 입력은 같은 ID로 재개한다. 성공·명시 로그아웃·superseded 충돌에는 해당 메모리를 지운다.

브라우저 저장소에는 operation ID만 보존한다. 비밀번호와 해시·검증값은 localStorage/sessionStorage에 쓰거나 로그에 남기지 않는다. 테스트도 저장소에 테스트 비밀번호가 없는지 확인한다. 완료된 create의 응답 유실 후 새 입력·새로고침은 새 ID를 사용하므로 서버의 기존 login ID 충돌을 실패로 표시하며, 입력한 새 비밀번호를 적용했다고 오인하지 않는다. reset의 새 작업은 새 비밀번호를 실제 적용한다.

원격 변경의 불명확 응답 안내는 변경 적용 여부를 단정하지 않도록 수정했다. 재로그인이 필요할 때 기존 또는 새 비밀번호로 확인한 뒤 재시도하도록 한다. HTTP503 및 `auth_write_uncertain` 코드는 유지한다.

### 실제 검증

- UI RED: 신규 6개 테스트 모두 예상 실패. 이력 빈틈, create/reset 변경·새로고침 ID 재사용, superseded 뒤 ID 고착을 확인했다.
- UI 최종: `LD_LIBRARY_PATH=/tmp/kosa-push-browser-libs/extracted/usr/lib/x86_64-linux-gnu E2E_BASE_URL=http://127.0.0.1:5181 npm --prefix PRJ/frontend run test:e2e -- tests/supabase-accounts.spec.ts --output=/tmp/kosa-auth-review-final` → **14 passed (27.7s), exit 0**.
- backend RED/GREEN: `PYTHONPATH=/tmp/kosa-auth-journey/PRJ/backend DATABASE_URL=<격리 studio_test> APP_ENV=local AUTH_MODE=mock AI_MODE=mock /home/ubuntu/work/kosa_final-public/PRJ/backend/.venv/bin/python -m pytest PRJ/backend/tests/test_accounts.py -k completed_new_reset_supersedes -q` → **1 passed, 22 deselected, 1 warning (0.85s), exit 0**. 전용 PostgreSQL17 `kosa-auth-review-db`, loopback 자동 할당 포트, tmpfs를 사용했고 종료·제거했다. root의 전체 E2E DB와 서비스에는 접근하지 않았다.
- `PRJ/frontend`에서 `npm run build` → **exit 0**, TypeScript·Vite 통과.
- 마지막 안내 문구 변경 뒤 기존 재인증 테스트 1건을 별도로 재실행했다. 결과는 아래 기록한다.
- backend 경고는 기존 Starlette/httpx deprecation이다. 실제 Supabase·모델 호출은 미실행이다. 전체 backend/계약/E2E 재검증은 root 통합 단계에서 수행한다.
- 안내 문구 최종 확인: 같은 Supabase 경계 명령에서 `--grep '작업 ID를 재인증' --output=/tmp/kosa-auth-review-copy` → **1 passed (3.4s), exit 0**.
- 담당 파일의 `git diff --check` → **exit 0**.

수정 라운드 인계: 제품 코드 변경을 마쳤고 root에 최종 결과와 계약 차이를 전달했다. 문서·OpenAPI 및 전체 통합 검증은 root 소유다. 커밋·푸시는 하지 않았다.

## 독립 리뷰 수정 2차: 미완료 생성 복구

- 수정 1차는 이미 ready인 계정의 거짓 성공을 차단했으나, pending 생성의 새 ID를 모두 충돌 처리해 새로고침 뒤 복구를 막았다. [재검토](review-auth.md)의 지적을 반영했다.
- 새 create 작업은 같은 login ID의 **pending** 계정에 한해 정규화된 이름(`strip`)과 역할이 일치하면 같은 account ID/Auth UID를 이어받는다. 기존 계정별 advisory lock 안에서 확인·작업 기록을 하고, 외부 Auth 사용자가 없으면 같은 UID로 생성하고 있으면 현재 요청 비밀번호를 PUT한다. 이후 ready로 전환한다. 메타데이터 불일치 및 이미 ready인 계정의 새 작업은 기존처럼 409다. bootstrap의 기존 제한은 유지한다.
- 더 새 create 작업이 있으면 이전 미완료 create는 reset과 동일한 `account_operation_superseded` 409로 막아 최신 비밀번호를 덮어쓰지 못한다. 완료된 동일 operation ID의 멱등 성공은 그대로 유지한다. 새 API·마이그레이션·비밀번호 저장은 없다.
- TDD RED 1단계: Auth 503이 원격 사용자 생성 전/후에 발생한 2개 경우에서 새 작업 복구가 기존 코드의 409로 실패했다. 변경 메타데이터 차단 2개는 기존 동작으로 통과했다.
- TDD RED 2단계: 이어받기만 적용한 뒤 이전 미완료 작업이 201로 최신 비밀번호를 덮어쓰는 실패를 별도로 확인했다. 그 뒤 create에도 supersession guard를 적용했다.
- `test_accounts.py` 전체: **27 passed, 1 warning (44.51s), exit 0**. 원격 생성 전/후의 새 작업 복구, 같은 account/Auth UID 유지, 중복 계정 부재, 새 비밀번호 로그인, 이전 작업 차단, ready 중복 차단, 완료 ID 멱등성을 포함한다. 전용 tmpfs PostgreSQL17 `kosa-auth-review-db`/자동 할당 loopback 포트 32780을 사용하고 종료·제거했다. 경고는 기존 Starlette/httpx deprecation이다.
- backend 명령: `PYTHONPATH=/tmp/kosa-auth-journey/PRJ/backend DATABASE_URL=<격리 studio_test> APP_ENV=local AUTH_MODE=mock AI_MODE=mock /home/ubuntu/work/kosa_final-public/PRJ/backend/.venv/bin/python -m pytest PRJ/backend/tests/test_accounts.py -q`.
- 1차의 4개 브라우저 테스트가 `/src/accounts/server.ts`를 직접 import하던 문제를 수정했다. 이제 전부 실제 계정 관리·생성·재설정 폼을 사용한다. pending 생성의 503 → 새로고침 → 변경 비밀번호·새 operation ID → 동일 계정 완료 UI 시나리오도 추가했다. ready 중복 거절 fixture와 pending 복구 fixture를 구분한다.
- `PRJ/frontend`에서 `npm run build`: **exit 0**. 이어서 `npx vite preview --host 127.0.0.1 --port 5182 --strictPort`로 production dist만 제공했다.
- 최종 브라우저 명령: `LD_LIBRARY_PATH=/tmp/kosa-push-browser-libs/extracted/usr/lib/x86_64-linux-gnu E2E_BASE_URL=http://127.0.0.1:5182 npm --prefix PRJ/frontend run test:e2e -- tests/supabase-accounts.spec.ts --output=/tmp/kosa-auth-create-final-preview` → **15 passed (34.4s), exit 0**.
- 테스트 파일의 동적 import·`/src/` 의존성 검색 결과 없음. 담당 파일 `git diff --check` 통과.
- root에 최종 소스·검증을 전달했다. 실제 Supabase·모델 호출, 커밋·푸시는 하지 않았다. root가 전체 backend/계약/격리 E2E와 문서 통합을 수행한다.
