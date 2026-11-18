# Studio v2 계약

2026-10-15 전체 재구축 계약이다. 보관된 v1 구현/설계 파일 대신 이 디렉터리를 기준으로 한다. 사용자가 선택한 1차 범위는 핵심 기획 흐름과 와이어프레임이다.

## 데이터

`Snapshot = prd + requirements + features + flow + screens`. Pydantic/JSON schema는 미정의 필드를 거부한다.

- PRD: 섹션의 고정 ID, 그룹·제목·본문, 사용자 역할, 플랫폼, 가정.
- 요구사항: ID, 설명, P0/P1/P2 중요도, 수용 기준. P1/P2는 사용자가 기획하는 제품의 우선순위이며 이 서비스의 범위 확대를 뜻하지 않는다.
- 기능: 요구사항 ID, 역할, 사전 조건·정상 동작·예외·검수 조건.
- 흐름: `start/screen/decision/action/end` 노드, 위치·연결 기능·간선 조건.
- 화면: 실제 screen 노드 ID, 모바일/데스크톱, 제한된 block 목록.
- block: `heading/text/input/button/card/list/stat/navigation`, 표시 문자열과 선택적인 대상 화면 ID. 실행 코드/HTML은 지원하지 않는다.

전역 ID 중복, 끊긴 참조, 없는 역할, 시작/종료 누락, 시작에서 도달 불가, 불완전한 분기는 blocking이다. 가정·빈 검수/예외·항목 삭제는 warning이다. warning은 명시적인 확인 후에만 승인할 수 있다.

## 확정과 수정

프로젝트+revision 0+초기 생성 job+사용자 메시지를 원자 저장한다. revision 0은 빈 기획이며 내보낼 수 없다. revision은 DB trigger로 UPDATE/DELETE를 거부한다.

AI 결과와 직접 편집은 proposal이다. 기존 proposal candidate는 수정하지 않고 새 proposal을 만든다. 직접 편집은 이전 pending을 superseded로 바꾸고 새 candidate를 저장한다. 기준 revision은 바꾸지 않는다.

승인/거절은 project row lock 후 처리한다. 승인 때 기준 버전과 현재 버전을 비교하고 같은 서버 검증을 다시 실행한다. revision+current_version+proposal+job+메시지는 같은 트랜잭션이다. 동일 결정 재요청은 기존 결과를 반환하고 반대 결정은 409다. 과거 버전 복원도 현재 버전을 기준으로 한 새 proposal이다.

## 실행

`queued → running → awaiting_answers → queued → running → waiting_review → completed`

각 생성 단계는 `questions → prd → features → flow → wireframes → validation`이다. 수정은 확정 snapshot에서 `revise → validation`으로 진행한다. 실패/취소는 확정본을 바꾸지 않는다.

job에 AI 모드·공급자·모델을 고정한다. worker는 job별 세션 advisory lock을 유지한다. 완료 단계의 partial/usage를 저장하고 재시작 시 다음 단계부터 재개한다. 외부 호출의 정확히 한 번 실행은 보장하지 않는다. proposal.job_id UNIQUE로 DB 결과 중복은 방지한다. 이미 커밋된 proposal/결정을 worker 실패로 덮어쓰지 않는다.

질문 재개는 project 소유권, job ID, base_version, 전체 question key를 검증한다. 같은 답변 재요청은 멱등이다. 질문 대기는 worker를 점유하지 않는다. 실제 모델의 malformed 출력은 failed다. 연결 검증 blocking은 한 번 보정한 후에도 남으면 승인을 차단하는 proposal로 저장한다.

## API와 인증

`/api/projects`, `/api/projects/{id}`와 하위 jobs/answers/cancel, proposals/approve/reject, revisions/export가 공개 계약이다. 상세 요청 schema는 [OpenAPI](openapi.json)에 있다.

- Bearer 인증. body 사용자 ID는 허용하지 않는다.
- Supabase JWT/JWKS: RS256/ES256, issuer·audience·sub·iat·exp 검증.
- mock: APP_ENV=local 전용이며 UI에 표시한다. 운영 환경은 시작을 거부한다.
- 401 인증 실패, 404 리소스 없음/타인 소유 동일, 409 버전/결정/실행 충돌, 422 입력 오류.
- 비밀값과 모델의 원문 오류를 로그/API 오류에 포함하지 않는다.

## 내보내기

`GET /api/projects/{id}/revisions/{version}/export?format=json|markdown`은 지정된 승인 revision만 읽는다. pending candidate를 내보내지 않는다. LLM 호출이나 저장 파일을 만들지 않는다.

JSON envelope는 project_id/version/created_at/snapshot이다. Markdown에는 PRD·가정·요구사항·기능·노드/간선·와이어프레임·block과 연결 ID를 포함한다. 파일 저장과 만료를 운영하는 v1 큐 계약은 폐기하고 즉시 다운로드 방식으로 변경했다.


## 역할별 AI 검토

개발자(developer)·기획자(planner)·보안(security)·UI/UX(ux)·QA(qa)가 같은 저장된 snapshot을 독립적으로 검토한다. 생성 job과 별도 큐이며 `queued → running → completed | partial | failed`다. 각 역할은 `queued → running → completed | failed`다. 최대 세 역할을 동시에 호출한다. 일부 실패 시 완료 결과를 보존하고 실패 역할만 재시도한다. worker 재시작은 미완료 역할부터 재개한다.

- `POST /api/projects/{id}/reviews`: `proposal_id` 또는 `version>=1` 중 하나. 새 실행은 pending proposal 또는 확정 revision만 허용한다. 동일 대상의 중복 요청은 동일 보고서를 반환한다.
- `GET /api/projects/{id}/reviews?proposal_id=...` 또는 `?version=...`: 해당 대상의 검토 또는 null. 소유권 확인 후 조회한다.
- `POST /api/projects/{id}/reviews/{review_id}/retry`: `{role}`. 진행 중 재시도와 완료 역할의 재시도는 409다.

보고서에는 대상 ID/버전, snapshot_hash, 모드·공급자·모델·prompt_version, 역할별 상태·결과·오류·usage를 저장한다. 모델/공급자/모드와 프롬프트 버전을 고정하며 설정 변경 시 조용히 다른 모델로 전환하지 않는다. 역할 출력 계약은 [JSON schema](role-review.schema.json), 예시는 [fixture](example-role-review.json)다.

지적의 심각도는 critical/warning/suggestion이다. 근거의 target_id는 기획에 실재해야 하며 quote는 해당 항목의 문자열 값에 연속해서 나타나야 한다. summary와 검토 기준, 지적별 근거·이유·수정 제안·관찰 가능한 수용 기준을 반환한다. 입력 문서 안의 명령은 지시가 아닌 검토 데이터로 취급하도록 프롬프트에 명시한다.

검토 대상의 복사본과 해시를 고정한다. 새 proposal이나 다른 revision에는 이전 검토를 표시하지 않는다. 직접 편집 중에는 저장을 먼저 안내한다. 검토는 확정본/수정안을 변경하지 않으며 심각도는 기존 구조 검사와 승인 정책에 영향을 주지 않는다. 모델 판단은 실제 구현에 대한 보안 감사나 품질 보증이 아니다.

## 기준 프로젝트와 코드 스냅샷

- `POST /api/sources`는 이름, 설명, 로컬 상대 경로 또는 GitHub URL, 브랜치, 선택적인 분석 우선 경로를 받는다. `GET /api/sources`는 로그인 사용자의 등록 목록과 최근 확인 상태를 반환한다.
- `POST /api/sources/{source_id}/analyze`는 현재 참조를 commit SHA로 확인하고 `source_id/commit_sha/analysis_version` 당 하나의 분석을 예약한다. 커밋 확인 실패는 기준 프로젝트의 오류로 기록한다.
- `GET /api/sources/{source_id}/snapshots/{snapshot_id}`는 상태·제외 사유·읽은 파일의 경로와 SHA-256을 반환한다. `POST .../retry`는 같은 커밋의 실패 분석만 재개한다. 준비된 분석은 DB에서 수정할 수 없다.
- `POST .../preview`는 `{idea}`로 모델에 전달할 발췌, 공급자·모델, 확인 fingerprint를 계산한다. 이 요청에서 모델을 호출하지 않는다.
- `POST /api/projects`에 `source_id`와 `code_snapshot_id`를 함께 보내면 기존 프로젝트 기획이 된다. live에서는 동일 요청·스냅샷·모델의 `code_consent`가 필요하다. `forked_from`은 같은 기준 프로젝트의 다른 스냅샷에 새 작업을 연결한다. 두 참조를 생략하면 신규 서비스 기획으로 처리한다.
- 소유권과 준비 상태를 서버에서 검사하고, 기준을 revision 0·생성 job과 한 트랜잭션으로 저장한다. `GET /api/projects?source_id=...`로 기준 프로젝트별 작업을 조회한다. 프로젝트의 기준 참조를 바꾸는 API는 제공하지 않는다.
- 기존 프로젝트의 생성에는 `implementation` 단계가 추가된다. 질문·수정·보정·역할 검토는 같은 기준의 고정 발췌를 받는다. 수정안의 근거 원문, 줄 범위, 경로, 내용 해시를 확정본의 서버 발급 기준과 대조한다. 구현 작업의 기존 대상 및 요구사항·근거·수용 기준 ID를 연결 검사한다.
- 승인 snapshot은 `source_context`와 `implementation`을 보존한다. JSON에는 인계 지시 `handoff`를 추가하고 Markdown에는 고정 커밋·근거·적용 범위·구현 순서·검수·미결정을 포함한다.
- 역할 검토는 코드 스냅샷과 커밋도 표시한다. `attempts`에는 호출별 상태·시간·오류·응답 usage가 남는다. 프로세스 중단이나 공급자가 사용량을 반환하지 않은 경우에는 확인 가능한 상태만 기록한다.
