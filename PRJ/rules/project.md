# 프로젝트 개발 안내

기준일: 2026-11-17. 현재 체크아웃을 정적으로 확인한 안내다. 실행 중인 서비스 상태나 테스트 통과를 보증하지 않는다. 경로는 별도 표시가 없으면 `PRJ/` 기준이다.

## 개발 전 읽기 순서

1. [루트 AGENTS.md](../../AGENTS.md)와 [PRJ/AGENTS.md](../AGENTS.md): 작업 규칙과 제품 불변 조건.
2. 이 문서: 제품 흐름과 변경 지점.
3. 변경 영역의 [frontend.md](frontend.md), [backend.md](backend.md), [infra.md](infra.md).
4. [데이터/API 계약](../docs/spec/README.md), [계약 결정](../docs/contract-decisions.md), 해당 소스와 테스트.

안내 문서는 탐색을 돕는 요약이다. 구현과 문서가 다르면 실제 코드·테스트를 확인하고 계약과의 차이를 기록한다. 과거 계획이나 검증 보고서만으로 현재 구현·운영 상태를 단정하지 않는다.

## 제품과 디렉토리

기획실 Studio는 아이디어를 확인 질문 → PRD → 요구사항·기능명세 → 유저플로우 → 와이어프레임으로 구체화하는 웹 서비스다. AI와 직접 편집은 수정안(proposal)을 만들며 사용자의 승인을 거쳐 확정본(revision)이 된다.

기준 저장소의 특정 커밋을 분석하고 코드 근거와 구현 지침이 포함된 변경 기획을 만드는 기능도 구현되어 있다. 대상 저장소에 구현 코드를 자동 적용하는 기능은 아니다.

```text
kosa_final-public/
├── AGENTS.md                # 전체 작업 진입점
└── PRJ/                     # 실제 서비스 개발 영역
    ├── AGENTS.md            # 제품 개발 규칙
    ├── rules/               # 개발 전 읽는 안내 문서
    ├── frontend/src/        # React UI와 API 클라이언트
    ├── frontend/tests/      # Playwright 시나리오
    ├── backend/app/         # FastAPI, worker, 모델 호출, 저장소 분석
    ├── backend/migrations/  # PostgreSQL SQL
    ├── backend/tests/       # PostgreSQL 기반 pytest
    ├── prompts/             # 생성·역할 검토·소스 기반 기획 프롬프트
    ├── infra/               # 이미지 빌드, nginx, 선택적 저장소 마운트
    ├── scripts/             # E2E, smoke, 평가·운영 검증
    ├── docs/                # 계약, 구현 계획, 기존 검증 근거
    ├── artifacts/           # 기존 아키텍처 설명 산출물
    └── compose.yaml         # 서비스·테스트 구성
```

계정·역할 정책·세션·감사 이력은 서버 DB에서 관리하고 비밀번호 검증은 Supabase Auth를 사용한다. 브라우저 계정 저장소는 사용하지 않는다. local 전용 `seed-test-accounts` 관리 명령으로 admin/user1/user2를 명시적으로 구성한다.

제품의 역할별 검토 데이터는 PostgreSQL의 `studio_reviews` / `studio_review_agents`에 저장한다.

## 실제 사용 흐름과 코드 연결

| 사용 예시 | UI 진입점 | 서버 처리·조건 |
| --- | --- | --- |
| 홈에서 “작은 팀의 일정 관리 서비스” 입력 | `App.tsx`의 `Home`, `create` | `main.py:create_project`: 프로젝트·revision 0·생성 job을 같은 트랜잭션으로 생성 |
| 질문에 답하거나 AI 가정으로 진행 | `Chat.tsx`, `App.tsx:submitAnswers` | `main.py:answer`: 전체 질문 key·기준 버전 검증, `worker.py`: 단계별 생성 |
| PRD·기능명세·흐름·화면 확인 | `Documents.tsx`, `Wireframes.tsx` | `schema.py`로 구조·연결을 검증한 JSON 표시 |
| 직접 편집 또는 AI 수정 요청 | `App.tsx`, `Review.tsx`, `Chat.tsx` | `main.py:manual_edit` 또는 job → proposal. 승인 전 current_version 유지 |
| diff·경고를 확인하고 승인·거절 | `Review.tsx` | `main.py:decide`, `review.py`: 승인 재검증과 원자적 버전 갱신 |
| 개발자·기획자·보안·UX·QA 검토 | `RoleReview.tsx` | `role_reviews.py`: 같은 snapshot, 최대 3개 동시 호출, 기획 자동 변경 없음 |
| 과거 버전 조회·복원 제안·다운로드 | `App.tsx` | 복원도 새 proposal. `main.py:export`는 선택한 확정 revision만 사용 |
| 기준 저장소 등록 → 코드 범위 확인 → 변경 기획 | `Sources.tsx`, `App.tsx` | `source_api.py`, `repositories.py`, `source_review.py`, `source.v1.md` |

재현 시나리오: [studio.spec.ts](../frontend/tests/studio.spec.ts), [source-planning.spec.ts](../frontend/tests/source-planning.spec.ts), [test_studio.py](../backend/tests/test_studio.py), [test_source_planning.py](../backend/tests/test_source_planning.py).

## 변경할 때 함께 확인할 곳

| 변경 대상 | 함께 검토할 파일·문서 |
| --- | --- |
| snapshot 필드·연결 규칙 | `schema.py`, `frontend/src/types.ts`, 프롬프트, `docs/spec/`의 schema·예시, 관련 테스트 |
| API 요청·응답 | `main.py` / `source_api.py`, 호출 UI, `docs/spec/README.md` / `openapi.json`, 관련 테스트 |
| 생성·복구·취소 | `worker.py`, `generation.py`, job 저장 구조, `test_auth_and_recovery.py` |
| 역할 검토 | `role_reviews.py`, `RoleReview.tsx`, `review.v1.md`, `test_role_reviews.py` |
| 저장소 분석·구현 인계 | `repositories.py`, `source_api.py`, `source_review.py`, `Sources.tsx`, `source.v1.md` |
| 실행·배포·환경변수 | `compose.yaml`, `infra/`, `config.py`, `.env.example`, `README.md` |

## 작업과 검증

1. 목표와 완료 조건을 정한다.
2. 관련 안내 → 계약 → 실제 구현·테스트를 확인하고 필요한 코드만 변경한다.
3. 변경 규모에 맞는 검증을 수행한다. 실행 위치와 전제는 각 영역 문서를 따른다.
4. 구조·사용법·계약 변경은 해당 `rules/*.md`와 원래 소유 문서에 함께 반영한다.
5. PR에 실제 실행 결과와 미확인 항목을 기록한다.

소스 기본 모델과 현재 실행 모델은 구분한다. 실제 설정은 `/health`와 API/worker 환경을 확인하되 비밀값을 출력하지 않는다. 후속 품질·사용성 항목은 [remaining-work.md](../docs/remaining-work.md)의 날짜와 검증 환경을 확인한다.

결제·공동편집·파일 업로드·외부 공유·제품 MCP는 기존 프로젝트 규칙상 범위 밖이다.
