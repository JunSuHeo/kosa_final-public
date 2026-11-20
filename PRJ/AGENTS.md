# AGENTS.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## Project instructions

- 2026-10-15 사용자가 기존 구현 전체 폐기와 REA 기반 재구축을 승인했다. 1차 범위는 핵심 기능과 와이어프레임이다.
- 새 계약은 docs/spec/README.md, 구현/검증 상태는 docs/implementation-plan.md와 docs/verification.md를 기준으로 한다.
- frontend/는 React+TypeScript+Vite, backend/app/는 FastAPI, backend/migrations/는 PostgreSQL migration이다.
- 승인된 revision만 기획 기준이다. revision은 DB에서도 불변이며 AI와 직접 편집은 새 proposal이다.
  프로젝트와 revision 0은 같은 트랜잭션으로 만든다. 승인만 current_version을 변경한다.
- 모든 리소스는 서버에서 소유권을 검증한다. 인증 실패 401, 없는/다른 사용자의 리소스는 동일 404,
  버전/멱등성 충돌은 409다. actor 사용자 ID를 body에서 받지 않는다. 배정 대상 account_id만 배정 API 경로로 받는다.
- AUTH_MODE=mock은 APP_ENV=local에서만 허용하며 UI에 표시한다. 실제 인증은 Supabase JWT/JWKS다.
- AI_MODE=mock/live는 인증과 독립이다. live는 서버 API 키/모델이 필요하고 자동 mock fallback을 금지한다.
  LLM_PROVIDER=openai/openrouter, 기본 OpenRouter 모델은 openai/gpt-6.1-sol이다.
  공급자/모델/AI 모드는 job에 고정하며 변경된 설정으로 이전 job을 이어서 실행하지 않는다.
  API와 worker 환경변수는 동일하게 전달한다. 서버 키와 JWT/DB 비밀은 프런트엔드로 보내지 않는다.
- worker.py는 PostgreSQL job의 단계별 partial 결과를 저장한다. 세션 advisory lock과 job_id UNIQUE로
  동시 재처리와 중복 proposal을 막는다. 질문 대기에는 worker를 점유하지 않는다.
  재시작은 마지막 저장된 단계부터 재개하되 외부 모델 호출은 at-least-once일 수 있다.
- 질문은 job ID/기준 버전/전체 question key 집합을 확인한다. malformed 모델 결과는 failed,
  유효한 JSON의 연결 오류는 보정 1회 뒤 검토 대상으로 남기며 blocking을 승인하지 않는다.
- review.py의 서버 검증/diff를 AI·수동 proposal과 승인 재검증에 공유한다. 경고는 확인이 필요하다.
  승인/거절은 프로젝트 row lock 후 revision·project·proposal·job·message를 원자 처리한다.
- 와이어프레임은 제한된 JSON block 타입을 React 컴포넌트로 표시한다. AI HTML/JS/CSS를 실행하지 않는다.
  흐름도 역시 검증된 JSON 노드/간선만 React Flow로 렌더한다. 연결 ID와 시작/종료/도달성을 검증한다.
- export는 지정된 불변 revision의 Markdown/JSON만 즉시 생성한다. pending proposal과 LLM을 읽지 않는다.
  새 export는 DB 큐/저장 파일 없이 즉시 다운로드 응답하므로 과거 파일 만료/공유 볼륨 계약을 적용하지 않는다.
- 실제 관찰·REA 정적 분석·추론을 docs/reverse-engineering.md에서 구분한다. 원본 대상 코드를 제품에 넣지 않는다.
- 결제·공동편집·파일 업로드·외부 공유·제품 MCP는 이번 범위에 없다.
- 의존성 변경 후 uv.lock/package-lock.json을 갱신한다. 재현 설치는 uv sync --frozen / npm ci다.
- 실행과 backend/격리 E2E 검증 명령은 README.md에 유지한다. PostgreSQL 테스트를 SQLite로 대체하지 않는다.
- 완료 보고에서 실제 모델 호출, mock 테스트, 미확인 외부 인증을 구분한다.

- 역할 검토는 `role_reviews.py`와 별도 review/agent 테이블을 사용한다. 다섯 역할은 동일 snapshot의 독립 호출이며 최대 3개 동시 실행한다. 대상 ID/버전/해시와 공급자/모델/모드/prompt_version을 고정한다. 결과를 다른 proposal에 재사용하지 않는다. 근거 ID/원문 일치를 서버에서 검증하고 실패 역할만 재시도한다. 검토는 proposal/revision/current_version을 변경하거나 승인 조건을 완화하지 않는다.

## Development harness

- 전체 작업 규칙은 상위 `../AGENTS.md`를 함께 따른다. 이 파일의 기존 프로젝트 계약은 계속 적용한다.
- 개발 전 `rules/project.md`를 읽고 변경 영역의 `rules/frontend.md`, `rules/backend.md`, `rules/infra.md`를 읽는다. 여러 영역이면 관련 문서를 모두 확인한다.
- 안내는 소스·테스트를 찾는 진입점이다. 계약은 `docs/spec/`, 구현은 소스·테스트를 확인한다. 차이가 있으면 기록하고 작업 범위에서 함께 갱신한다.
- 구조·API·실행법·사용 예시를 바꾸면 해당 `rules/*.md`와 기존 계약/실행 문서를 함께 갱신한다. 미실행 예시와 실제 검증 결과를 구분한다.
