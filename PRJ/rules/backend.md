# 백엔드 개발 안내

기준일: 2026-11-17, 현재 소스의 정적 확인 기준. 먼저 [project.md](project.md)를 읽는다. 경로는 `PRJ/` 기준이다.

## 구성과 책임

이 버전에는 `accounts.py`의 서버 계정·역할·세션·감사 API와 `manage.py`의 명시적 운영 명령, `transfer.py`의 오프라인 이전 도구가 추가되어 있다. Supabase 인증 모드의 앱 시작은 기본적으로 DDL을 실행하지 않는다. 실제 운영 전환 상태와 미완료 사항은 [전환 인계](../docs/supabase-transition.md)를 확인한다.

Python 3.12 이상, FastAPI, Pydantic, psycopg, PostgreSQL을 사용한다. API와 worker는 별도 프로세스이며 DB에 저장한 작업을 주고받는다. 별도 메시지 브로커는 사용하지 않는다.

| 소스 | 책임 |
| --- | --- |
| `backend/app/main.py` | 프로젝트·job·질문·proposal·승인·revision·export·역할 검토 API |
| `backend/app/source_api.py` | `/api/sources`, 등록·분석·발췌 preview·코드 전송 확인 |
| `backend/app/config.py` | 환경변수·모드 검증·키/모델 선택, 캐시된 `settings()` |
| `backend/app/auth.py` | mock Bearer / Supabase JWT 검증과 사용자 식별 |
| `backend/app/db.py` | psycopg 연결, 정렬된 SQL migration 실행과 초기화 잠금 |
| `backend/app/schema.py` | 엄격한 snapshot·출력 타입, 연결 검증, diff |
| `backend/app/review.py` | AI/수동 proposal과 승인에 공유하는 검증·diff |
| `backend/app/worker.py` | 저장소 분석 → 생성 job → 역할 검토 큐 조회, 단계별 저장·재개 |
| `backend/app/generation.py` | 단계별 출력 schema, OpenAI/OpenRouter 호출, mock 결과 |
| `backend/app/role_reviews.py` | 독립 검토, snapshot hash·근거 ID·원문 검증, 실패 역할 재시도 |
| `backend/app/repositories.py` | 고정 커밋의 읽기 전용 로컬 Git / GitHub 분석·상한·제외 규칙 |
| `backend/app/source_review.py` | 코드 근거·구현 지침 검증과 Markdown 인계 |
| `backend/migrations/001_studio.sql` | 프로젝트·불변 revision·job·proposal·message |
| `backend/migrations/002_role_reviews.sql` | review·review_agent |
| `backend/migrations/003_source_planning.sql` | 기준 저장소·코드 snapshot·프로젝트 기준 고정 |
| `backend/migrations/004_studio_row_security.sql` | 앱 테이블의 RLS 활성화, 서버 연결 역할은 테이블 소유권으로 접근 |
| `backend/migrations/006_accounts.sql` | 서버 계정·권한·세션·감사 테이블 |
| `backend/migrations/007_runtime_security.sql` | 전용 런타임 역할, RLS 및 데이터 이전 제약 |

`manage.py seed-test-accounts`는 local Supabase 환경에서만 admin/user1/user2를 명시적으로 구성한다. 비밀번호는 대화형 입력 또는 `--password-file`로 받고 일반 재실행은 기존 계정·정책을 유지한다. `--reset-passwords`만 기존 비밀번호를 바꾸고 세션을 해제한다. 역할·활성 상태가 다르면 자동 변경하지 않는다. `test_seed_accounts.py`가 생성·재실행·정책/소유 데이터 보존·세션 해제·모드/역할 충돌을 검증한다.

## 생성·승인 흐름

1. `POST /api/projects`는 프로젝트·초기 revision 0·generate job을 한 트랜잭션으로 만든다.
2. worker는 `questions` 결과를 저장하고 `awaiting_answers`로 반환한다. 답변 대기 중 worker를 점유하지 않는다.
3. 답변 뒤 `prd → features → flow → wireframes → implementation → validation`으로 진행한다. 저장소 기준이 없으면 implementation은 건너뛴다.
4. 단계별 결과·usage를 저장하고 proposal 생성 후 job은 `waiting_review`가 된다.
5. approve는 기준 버전·blocking·경고 확인을 재검증한다. 프로젝트 row lock 아래 새 revision과 관련 상태를 원자 처리한다.

세션 advisory lock과 job별 유일 proposal로 동시 처리·중복 결과를 막는다. 저장 직전에 중단된 모델 호출은 재호출될 수 있다. 공급자·모델·모드는 job에 고정되므로 설정 변경 뒤 이전 job을 새 설정으로 이어 실행하지 않는다.

## 실제 API 사용 예시

아래는 **별도로 준비한 격리 mock 인스턴스**가 `http://localhost:8011`에 있다는 전제다. 문서 작성 중 실행한 명령은 아니다.

```sh
curl -fsS http://localhost:8011/health
curl -fsS http://localhost:8011/api/projects \
  -H 'Authorization: Bearer local:harness-example' \
  -H 'Content-Type: application/json' \
  --data '{"idea":"작은 팀의 일정 관리 서비스"}'
```

응답의 `id`를 사용해 `GET /api/projects/{project_id}`를 같은 인증 헤더로 조회한다. 상세 응답은 `project`, `revision`, `proposal`, `job`, `messages`, `revisions`, `screen_previews`를 포함한다.

`job.status=awaiting_answers`일 때 `POST /api/projects/{project_id}/jobs/{job_id}/answers`에 다음 형식을 전송한다. `실제_question_key`는 응답의 질문 key로 바꾸고 질문 수만큼 채운다. 기준 버전도 응답 값을 사용한다.

```json
{
  "base_version": 0,
  "answers": {"실제_question_key": "소규모 팀"}
}
```

AI 가정으로 진행하려면 전체 key를 유지하고 값을 빈 문자열로 보낸다. proposal이 준비되면 diff·경고를 검토한다. 승인 경로는 `POST /api/projects/{project_id}/proposals/{proposal_id}/approve`, body는 `expected_version`과 `acknowledge_warnings`다. 경고를 확인했을 때만 후자를 true로 보낸다.

승인 후 `GET /api/projects/{project_id}/revisions/{version}/export?format=json`으로 해당 확정본을 받는다. 버전 0과 pending proposal은 export 대상이 아니다.

실제 테스트 예시는 [test_studio.py](../backend/tests/test_studio.py)의 `make_project`, `generated`, `approve`다. `generated`는 질문·생성 시 `worker.process(job_id)`를 직접 호출해 상태를 검사한다.

## 변경 시 지킬 계약

- 사용자 ID는 body가 아닌 `current_user`로 결정하고 모든 소유권을 서버에서 확인한다. 인증 실패 401, 없는/타인 리소스 동일 404, 버전·멱등성 충돌 409다.
- 확정 revision을 수정·삭제하지 않는다. DB trigger도 검사한다. 복원·AI·직접 편집은 새 proposal이다.
- `schema.py` / `review.py` 검증을 우회하지 않는다. malformed 출력과 연결 오류를 구분하고 live 실패를 mock으로 대체하지 않는다.
- 다섯 역할은 같은 snapshot을 검토하며 최대 3개 동시 실행한다. 결과는 proposal/revision/current_version을 변경하지 않는다.
- 저장소 분석은 코드·설치 스크립트를 실행하지 않는다. 고정 커밋·상한·제외 사유, 코드 전송 확인 fingerprint와 공급자·모델 연결을 유지한다.
- migration은 새 번호의 SQL로 추가한다. `db.initialize()`는 mock 시작 시 또는 Supabase의 명시적 관리 명령에서 실행된다.
- API·schema 변경은 UI 타입·프롬프트·`docs/spec/` 계약·예시·관련 테스트와 함께 검토한다.

## 실행과 검증

DB·환경변수는 [infra.md](infra.md)를 따른다. 직접 실행은 `PRJ/backend/`에서 한다. API와 worker는 각각 별도 터미널을 사용한다.

```sh
uv sync --frozen
uv run uvicorn app.main:app --host 127.0.0.1 --port 8010
uv run python -m app.worker
```

설정 파일은 실행 디렉토리 기준 `../.env`다. API·worker 환경을 동일하게 맞춘다. 검증에는 별도 DB를 지정한다. Supabase 구성에서는 API·worker의 시작 시 migration을 비활성화한다.

PostgreSQL 테스트는 `PRJ/`에서 다음을 실행한다.

```sh
docker compose --profile test run --build --rm test
```

`tests/conftest.py`는 `studio_test`와 mock 모드를 확인한 뒤 테스트마다 테이블을 TRUNCATE한다. 서비스 DB를 연결하거나 SQLite로 대체하지 않는다.

| 테스트 | 영역 |
| --- | --- |
| `test_studio.py` | 생성·답변·편집·승인·export·멱등성 |
| `test_auth_and_recovery.py` | 인증·소유권·중단/재개 |
| `test_role_reviews.py` | 대상 고정·근거·독립 검토·재시도 |
| `test_source_planning.py` | 분석·제외·기준 고정·전송 확인·인계 |

live smoke는 호출 비용과 데이터를 발생시킨다. 실행 환경과 사용자 요청 범위를 확인하고 mock 결과와 구분해 기록한다.

## 인증 안정화와 진행 상태 (2026-11-23)

비밀번호 reset은 계정 active/ready와 별도로 operation 상태를 관리한다. 매 실제 재시도 전에 세션을 폐기하고 Auth 성공 후 다시 세션 폐기·완료·감사를 한 트랜잭션으로 저장한다. 실패해도 기존 ready 계정은 재로그인할 수 있다. 같은 operation ID의 완료 재요청은 부작용 없이 반환하며 더 최근 reset이 생긴 오래된 미완료 작업은409다. 원격 쓰기 반영 여부가 불명인 오류는503 `detail={code:"auth_write_uncertain",message:...}`로 구분한다. 암호는 operation/감사 테이블에 저장하지 않는다.

로그인 자격증명 실패는 계정별15분30회, 전체 요청 폭주는 IP별15분600회로 분리한다. 성공 및 Auth 장애는 계정 실패에 넣지 않는다. 원본 IP는 신뢰된 전용 nginx 네트워크에서만 반영한다. Auth429는429로 유지하고 JWKS 연결 오류는503, 잘못된 토큰/claim은401이다.

`GET /api/audit?before=<id>&limit=200`의 `next`는 문자열 또는 null이다. `GET /api/projects`는 소유 프로젝트의 최신 작업·pending proposal·확인본에서 `progress_status`(conversation/awaiting_answers/generating/review_ready/failed/confirmed)를 계산한다. 별도 상태 저장이나 승인 정책 변경은 없다. 테스트는 test_accounts/test_auth_errors/test_project_progress/test_proxy가 격리 PostgreSQL과 외부 Auth 대체 경계에서 검증한다.

성공한 새 대화는 과거 대화 실패 표시를 해제한다. 취소된 재시도는 실패를 해제하지 않으며 문서 생성 실패는 대화 성공만으로 해제하지 않는다. 기존 초안·확인본은 상태 표시 변경으로 바뀌지 않는다.

비밀번호 입력은 브라우저 저장소에 남기지 않는다. 같은 페이지 생명주기에서 동일 입력의 재인증 재시도는 기존 operation ID를 사용한다. 입력이 달라졌거나 탭을 새로고침해 이전 입력 동일성을 확인할 수 없으면 새 작업 ID를 사용한다. superseded409는 기존 ID를 정리하고 다음 명시적인 재시도를 허용하며 자동으로 쓰기를 재전송하지 않는다.

등록이 중단된 pending 계정은 관리자 명시 재시도에서 새 operation ID여도 동일 loginId/이름/역할이면 기존 계정·Auth UID로 완료할 수 있다. ready 계정의 중복 등록과 pending 계정의 메타데이터 변경은409다. 새 등록 작업이 만들어진 뒤 오래된 미완료 작업은 superseded409로 차단한다.

## GitHub 저장소 연결

`github_connection.py`에서 GitHub App 사용자 승인과 저장소 목록을 처리한다. state는 등록을 시작한 H‑PlanIT 계정에 묶이고 PKCE로 코드를 교환한다. 토큰은 `008_github_connections.sql` 테이블에 암호화하며, API와 worker는 저장소 소유자 기준으로 토큰을 조회하고 갱신한다. GitHub 분석 버전 `git-text.v2`는 전체 60초 제한 없이 commit, tree, blob을 읽고 파일 수·크기 상한과 GitHub 요청별 타임아웃을 적용한다. 같은 커밋의 기존 분석 버전은 보존한다.
