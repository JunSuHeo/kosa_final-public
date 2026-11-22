# Backend authentication and project progress

- 담당 팀원: SY
- 참여 AI: backend subagent
- 상태: 구현·격리 검증 완료
- 작업 경로: `/tmp/kosa-auth-journey`
- 소유 범위: `PRJ/backend/**` (생성 OpenAPI 제외), `PRJ/infra/nginx.conf`, Compose 프록시 구성
- 목표: 재시도 가능한 비밀번호 재설정, 분리된 로그인 제한, 인증 오류 분류, 감사 페이지 문자열 cursor, 프로젝트 진행 상태.
- 완료 조건: PostgreSQL 회귀 테스트 RED/GREEN, 전체 격리 테스트, 소유권·마지막 관리자 보호 유지.
- 계획: 기존 소스와 계약 확인 → 동작 회귀 테스트 RED → 최소 구현 → 격리 전체 검증.
- 의존성: root가 문서·OpenAPI 통합을 담당하고 frontend 에이전트가 응답 타입·오류 표시를 연결한다.

## 조사

- 기존 재설정은 계정을 pending으로 변경하고 최초 시도에서만 세션을 해제한다. 실패 후 기존 비밀번호로 재인증할 수 없고 호출 중 생성된 세션은 살아남는다.
- 기존 로그인 제한은 성공·외부 오류도 ID/IP 각각 30회에 포함하며 예외에서 증가가 rollback될 수 있다.
- 감사 next는 bigint를 숫자로 반환한다. 프로젝트 목록은 기존 project row만 반환한다.
- 테스트 DB: 사용자 서비스와 분리된 임시 PostgreSQL17, `studio_test`, tmpfs. 실제 Supabase/모델 호출 없음.

## 결정과 구현

- 기존 계정의 재설정 실패에도 active/ready를 유지한다. 실제 각 재시도 직전과 원격 성공 후 세션을 해제한다. 완료한 operation 재요청은 해제·감사를 반복하지 않는다.
- 원격 쓰기의 timeout/연결 오류/5xx/읽을 수 없는 응답은 HTTP503 `detail.code=auth_write_uncertain`로 분류한다. 원격 읽기·token 서비스 장애는 503, upstream429는 429, 무효 JWT·session claim은 401이다.
- 재인증 후 같은 operation ID로 재개할 수 있다. 실패한 작업 ID를 잃은 경우 새 작업도 허용한다. 더 새 reset 작업이 있으면 오래된 미완료 작업의 재개는 409로 막는다. 비밀번호를 operation input에 저장하지 않는다.
- 계정별 잘못된 자격증명 30회/15분과 IP별 요청 600회/15분을 분리한다. 성공·원격503/429는 계정 실패 한도를 소비하지 않는다. 계정의 내부 이메일 별칭도 같은 한도를 사용한다. 원자 upsert와 계정 advisory transaction lock으로 다중 API 프로세스·동시 실패를 제어한다.
- nginx는 전달받은 X-Forwarded-For를 `$remote_addr`로 덮어쓴다. Compose의 전용 studio-proxy 네트워크에는 api/web만 연결한다. Linux Docker 전용 launcher는 자체 network alias와 연결 route로 할당 CIDR을 찾고 그 CIDR만 Uvicorn에 전달한다. wildcard나 고정 CIDR을 쓰지 않아 병렬 스택과 충돌하지 않는다. 별도 직접 uvicorn 실행은 기존 방식을 유지한다.
- 감사 응답의 id와 next를 문자열로 유지하며 기존 `before` query를 보존한다. 405개 추가 감사 행과 JavaScript 안전 정수 범위를 넘는 ID로 페이지 순회를 검증한다.
- 프로젝트 진행 상태는 persisted job/proposal/revision에서 조회 시 계산한다. 취소한 job과 실패하지 않은 discuss job은 생성 진행 판단에서 제외한다. awaiting_answers → generating → 최신 실패 작업의 failed → pending proposal의 review_ready → 확정 revision의 confirmed → conversation 순으로 계산한다. owner/source 권한 검증을 유지한다.

## 소유 변경 파일

- `PRJ/backend/app/accounts.py`: 재설정·quota·Auth 응답·감사 cursor.
- `PRJ/backend/app/auth.py`: JWKS 장애 분류.
- `PRJ/backend/app/main.py`: 프로젝트 목록 진행 상태.
- `PRJ/backend/app/proxy.py`: Compose Linux Docker 전용 신뢰 네트워크 launcher.
- `PRJ/backend/tests/test_accounts.py`: 재설정·로그인 제한·감사 회귀, 테스트 간 감사 초기화.
- `PRJ/backend/tests/test_auth_errors.py`: Auth HTTP/JWKS/불확실 쓰기 분류.
- `PRJ/backend/tests/test_project_progress.py`: 생성·질문·초안·실패·확정·대화·취소 상태와 소유권.
- `PRJ/backend/tests/test_proxy.py`: 전용 subnet 신뢰 및 직접/default network의 XFF 차단, route 누락 fail closed.
- `PRJ/compose.yaml`, `PRJ/infra/nginx.conf`: 전용 프록시 네트워크·헤더 덮어쓰기.

## 검증

| 실행 위치 | 명령·방법 | 실제 결과 | 한계 |
| --- | --- | --- | --- |
| 작업 루트 | 신규 인증·진행 상태 테스트를 원래 구현에서 실행 | RED: 18 failed, 11 passed | PostgreSQL17 임시 studio_test; 초기 sandbox loopback 차단은 승인된 실행으로 해결 |
| 작업 루트 | 프록시 신뢰 회귀를 launcher 구현 전에 실행 | RED: 2 failed | launcher 부재를 재현 |
| 작업 루트 | 인증·진행 상태·프록시 focused suite | GREEN: 35 passed, 기존 deprecation warning 1개 | 외부 Auth만 fixture/mock |
| 작업 루트 | 오래된 reset·무효 session claim·잘못된 원격 JSON 회귀 | RED: 6 failed | 해당 실패를 확인한 뒤 최소 수정 |
| 작업 루트 | `make test` | GREEN: 96 passed, 1 warning, 71.97s | Python3.12/PostgreSQL17 격리 Compose, 실제 Supabase·LLM 호출 없음 |
| 작업 루트 | discuss 진행 상태 회귀 | RED: 2 failed, 1 passed | journey 에이전트와 conversation 표시를 합의 |
| PRJ/ | `docker compose --env-file .env.example -f compose.yaml -f infra/test.compose.yaml -p kosa-auth-proxy-check --profile test config --quiet` | 통과 | 정적 Compose 검증 |
| 작업 루트 | `git diff --check -- PRJ/backend PRJ/compose.yaml PRJ/infra/nginx.conf` | 통과 | 소유 파일만 검사 |

## 인계

- root: 문서·OpenAPI·frontend 응답 타입을 통합한다. API 감사 query는 `before`, next는 string/null이다. 불확실 쓰기 detail은 `{code,message}`다.
- root: 실제 nginx·Docker published port에서 위조 XFF와 직접 API 접근의 주소 판단은 통합 E2E 환경에서 확인한다. 이 파일의 proxy 단위 검증과 구분한다.
- 마지막 discuss 수정 뒤 전체 `make test`를 다시 실행 중이며 결과를 아래에 추가한다.

### 최종 전체 검증

- 최종 소스에서 `make test`: **99 passed, 1 warning, 104.53s**, exit 0.
- 경고는 baseline에도 있던 Starlette/httpx deprecation이다.
- 격리 Compose 프로젝트 `kosa-test-390110`의 테스트 컨테이너·이미지·네트워크는 Makefile trap으로 정리됐다.
- 제품 코드 완료. 실제 Supabase·LLM 호출 및 기존 서비스 재시작은 하지 않았다. Linux Docker/nginx 실제 전달 주소 검증은 root 통합 단계에서 기록한다.

- 임시 incremental PostgreSQL 컨테이너도 제거했다. 이후 리뷰 수정은 root가 sessions 에이전트에 넘겼으며 backend 소유 파일을 해당 에이전트에 인계했다. 위 99개 결과는 그 리뷰 수정 전 최종 backend 소스 기준이다.


### 통합 후 진행 상태 우선순위 수정

- 확인한 불일치: pending proposal과 더 새로운 실패 작업이 함께 있으면 목록은 review_ready, 실제 이어가기는 실패 복구 화면을 열었다.
- 변경 범위: `backend/app/main.py`의 CASE에서 failed를 pending proposal보다 먼저 판단하도록 순서만 변경했다. 생성된 초안과 나머지 저장 상태는 변경하지 않았다.
- 회귀: `test_latest_failed_action_precedes_pending_proposal_progress`를 discuss/revise 각각 실행했다. pending proposal 생성 → 더 새로운 실패 → 그 뒤 취소한 재시도 상태에서도 failed를 유지하고 기존 pending proposal ID/상태를 보존함을 검사한다.
- RED: 변경 전 두 경우 모두 review_ready를 반환하여 **2 failed**, 1.74s.
- GREEN: 변경 후 전체 `tests/test_project_progress.py` 검증 결과는 아래에 추가한다. 전체 backend 검증은 root가 최신 이미지로 실행한다.
- GREEN: **13 passed, 1 warning, 5.34s**, exit 0. PostgreSQL17 임시 `studio_test`만 사용했다. 경고는 기존 Starlette/httpx deprecation이다.
- `git diff --check` 통과. 이 후속 변경은 main.py, test_project_progress.py, 본 기록만 수정했다.

### 마지막 대화 재시도 상태 보완

- 완료된 새 discuss가 과거 failed discuss만 해소하도록 조회한다. 취소된 작업과 문서 생성 실패, 기존 초안·확인본은 유지한다.
- 회귀 RED3건을 확인하고 진행 상태17건 통과. 이후 root의 최신 격리 backend 전체109건 통과가 이 기록의 최종 통합 검증 결과다.
