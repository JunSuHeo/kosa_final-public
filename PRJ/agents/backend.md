# 백엔드 개발 안내

기준일: 2026-11-17, 현재 소스의 정적 확인 기준. 먼저 [project.md](project.md)를 읽는다. 경로는 `PRJ/` 기준이다.

## 구성과 책임

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
- migration은 새 번호의 SQL로 추가하고 재시작 때 재실행하는 `db.initialize()` 방식에 맞춘다.
- API·schema 변경은 UI 타입·프롬프트·`docs/spec/` 계약·예시·관련 테스트와 함께 검토한다.

## 실행과 검증

DB·환경변수는 [infra.md](infra.md)를 따른다. 직접 실행은 `PRJ/backend/`에서 한다. API와 worker는 각각 별도 터미널을 사용한다.

```sh
uv sync --frozen
uv run uvicorn app.main:app --host 127.0.0.1 --port 8010
uv run python -m app.worker
```

설정 파일은 실행 디렉토리 기준 `../.env`다. API·worker 환경을 동일하게 맞춘다. 시작 시 migration을 실행하므로 검증에는 별도 DB를 지정한다.

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
