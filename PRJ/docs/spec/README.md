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
- `GET /api/sources/github`는 GitHub App 설정과 현재 H‑PlanIT 계정의 연결 상태를 반환한다. `POST /api/sources/github/start`는 10분 동안 유효한 일회성 OAuth 요청을 생성하고, `POST /api/sources/github/complete`는 동일 계정의 state와 PKCE를 확인하고 코드를 교환한다. `GET /api/sources/github/repositories`는 GitHub App 및 연결 계정이 읽을 수 있는 저장소의 이름·기본 브랜치·공개 여부를 반환한다. 네 경로 모두 `sources.manage` 권한을 검사한다. GitHub 토큰은 서버에 암호화해 보관한다.
- `POST /api/sources/{source_id}/analyze`는 현재 참조를 commit SHA로 확인하고 `source_id/commit_sha/analysis_version` 당 하나의 분석을 예약한다. 커밋 확인 실패는 기준 프로젝트의 오류로 기록한다.
- `GET /api/sources/{source_id}/snapshots/{snapshot_id}`는 상태·제외 사유·읽은 파일의 경로와 SHA-256을 반환한다. `POST .../retry`는 같은 커밋의 실패 분석만 재개한다. 준비된 분석은 DB에서 수정할 수 없다.
- `POST .../preview`는 `{idea}`로 모델에 전달할 발췌, 공급자·모델, 확인 fingerprint를 계산한다. 이 요청에서 모델을 호출하지 않는다.
- `POST /api/projects`에 `source_id`와 `code_snapshot_id`를 함께 보내면 기존 프로젝트 기획이 된다. live에서는 동일 요청·스냅샷·모델의 `code_consent`가 필요하다. `forked_from`은 같은 기준 프로젝트의 다른 스냅샷에 새 작업을 연결한다. 두 참조를 생략하면 신규 서비스 기획으로 처리한다.
- 소유권과 준비 상태를 서버에서 검사하고, 기준을 revision 0·생성 job과 한 트랜잭션으로 저장한다. `GET /api/projects?source_id=...`로 기준 프로젝트별 작업을 조회한다. 프로젝트의 기준 참조를 바꾸는 API는 제공하지 않는다.
- 기존 프로젝트의 생성에는 `implementation` 단계가 추가된다. 질문·수정·보정·역할 검토는 같은 기준의 고정 발췌를 받는다. 수정안의 근거 원문, 줄 범위, 경로, 내용 해시를 확정본의 서버 발급 기준과 대조한다. 구현 작업의 기존 대상 및 요구사항·근거·수용 기준 ID를 연결 검사한다.
- 승인 snapshot은 `source_context`와 `implementation`을 보존한다. JSON에는 인계 지시 `handoff`를 추가하고 Markdown에는 고정 커밋·근거·적용 범위·구현 순서·검수·미결정을 포함한다.
- 역할 검토는 코드 스냅샷과 커밋도 표시한다. `attempts`에는 호출별 상태·시간·오류·응답 usage가 남는다. 프로세스 중단이나 공급자가 사용량을 반환하지 않은 경우에는 확인 가능한 상태만 기록한다.

## H-PlanIT 업무 대화 계약 (2026-11-16)

기존 API와 불변 revision 계약을 유지하며 다음 흐름을 추가한다. 계정/권한 관리와 IT 최종 승인 분리는 후속 범위다. 화면의 ‘현업 확인본 저장’은 기존 approve에 해당하며 IT 승인 상태를 만들지 않는다.

- 홈은 게시된 업무를 선택한다. 첫 업무 설명을 전송할 때 `POST /api/projects`에 `start_mode=conversation`, `planning_intent=new_feature|improve|process`, `source_publication_id`와 대응하는 source/snapshot을 보낸다. 프로젝트·revision 0·첫 메시지·discuss job을 원자 저장한다. 기존 generate 모드와 source 없는 과거 기획은 호환한다.
- `POST /api/projects/{id}/jobs`의 kind는 generate/revise/discuss/repair다. discuss는 업무 대화와 `project.conversation_brief`만 저장한다. generate/revise는 사용자의 명시적인 작성 요청에서 실행한다. 실행에는 prompt_version, 대화 요약과 최근 대화(최대 24,000자), 대상 항목을 고정한다.
- 미확정 초안을 수정/보정할 때 `base_proposal_id`를 지정한다. 해당 candidate가 생성 기준이며 확정 revision은 그대로다. 현재 pending ID와 일치하지 않으면 409다. 이전 waiting_review job은 completed로 정리하지만 pending candidate는 새 결과의 저장 성공 때만 superseded로 전환한다. 실패·취소는 이전 candidate를 보존한다.
- 직접 편집은 `base_proposal_id`를 지원한다. conversation 모드의 편집은 현재 pending ID를 검증한다. 승인 시 서버 검증과 기준 revision 대비 diff를 다시 적용한다.
- Bundle은 프로젝트의 업무 요약, job의 대화 결과/suggestions, `changed_block_ids`를 제공한다. 변경 요소는 생성의 기준 초안 또는 현업 확인본과 비교하며 재접속 후에도 복원된다.

### 업무 게시와 코드 기준

- `POST /api/sources/{id}/snapshots/{snapshot_id}/publication-preview`는 선택적 design_profile을 받고 사용 가능한 필터링된 파일 manifest, 발췌 예시, 공급자/모델, 디자인과 fingerprint를 반환한다. 외부 모델을 호출하지 않는다.
- `POST /api/sources/{id}/publish`는 snapshot_id/design_profile/fingerprint를 받는다. 소유자가 확인한 전체 허용 manifest·모델·디자인을 불변 publication으로 저장한다. 같은 fingerprint 재요청은 같은 publication을 반환한다.
- 새 업무 대화는 현재 게시된 publication을 검증하고 요청 관련 발췌와 디자인을 revision 0에 고정한다. AI 공급자/모델/모드 변경 시 다시 게시해야 하며 과거 작업을 다른 설정으로 재개하지 않는다.
- `POST /api/sources/{id}/check`는 5분 간격으로만 백그라운드에서 코드 변경 확인을 예약한다. 현재 기획이나 게시된 기준은 자동 교체하지 않는다.
- 기존의 요청별 코드 preview/consent API는 이전 generate 모드에서 유지한다. 게시 기능의 소유권은 기존 인증을 사용하며 IT라는 표시는 새로운 역할 권한을 뜻하지 않는다.

### 제한된 화면 디자인

Snapshot의 선택적 design_profile은 검증된 hex 색상 4개, 열거형 글꼴/공통 배치, 8~32px 간격과 0~24px 모서리 값, 분석된 근거 파일 목록이다. 정적 소스에서 확인 가능한 CSS 값만 후보로 추출하고 소유자가 보완한다. 임의 CSS나 스크립트를 실행하지 않는다.

Screen에 form/list/detail/dashboard layout, Block에 header/navigation/filters/content/actions region을 추가한다. table block은 columns와 열 수가 일치하는 rows를 사용한다. 구형 데이터는 기본 배치로 표시한다. 디자인 기준은 AI 결과에서 변경할 수 없으며 서버가 보존한다.


### 현업 대화 질문 카드 (2026-11-17)
새 업무 대화는 `business.v2`를 고정한다. discuss 결과는 기존 reply/brief/suggestions와 `questions`(0~1개: key/title/options 2~5개)를 반환한다. 질문이 필요하면 업무 선택지를 제공하고, 화면은 별도로 직접 입력을 제공한다. 선택 또는 직접 입력한 답변은 질문 제목과 함께 일반 discuss 요청으로 전송하며 산출물을 자동 생성하지 않는다. 질문/선택지도 assistant 기록에 저장하여 다음 대화의 맥락을 보존한다. 충분히 정리되면 질문 없이 작성 행동을 안내한다. 기존 business.v1 실행은 이전 schema/프롬프트를 유지하며 기존 awaiting_answers API도 유지한다.


### 문서를 보며 내용 확인 (2026-11-17)
내용 확인 진입 시 과거 버전 선택을 해제하고 현재 pending 초안을 보여준다. 초안이 없으면 최신 현업 확인본, 확인본도 없으면 대화·작성 안내를 표시한다. 기획 내용 → 담당자·처리 순서·업무 규칙 → 업무 흐름 → 화면 시안 순으로 이동하며 이름이 있는 실제 항목을 선택·강조한다. 모바일에서는 문서와 안내를 전환한다. 선택한 문서 항목은 기존 target_id와 base_proposal_id로 수정 대화에 전달한다.
첫 초안은 전체 문서, 이후 수정안은 마지막 현업 확인본 기준의 변경 항목을 먼저 안내한다. 변경 건수와 필드 비교는 접힌 상세에 보관한다. 현업의 가정·정책·삭제 확인과 시스템의 연결 보정을 구분하고, 기술 원문은 IT 상세 검토에 제공한다. 기존 acknowledge_warnings·blocking·busy 저장 제한을 유지하며 API/DB/프롬프트 계약은 변경하지 않는다. 안내는 저장된 산출물과 검증 결과로 만들고 별도 모델 요약을 호출하지 않는다.

프로젝트 묶음 조회는 읽기 전용 반복 읽기 트랜잭션으로 프로젝트·확인본·초안·작업·메시지를 같은 시점에 반환한다. 작업 완료와 초안 저장이 조회 사이에 일어나도 완료 상태만 먼저 노출하지 않는다.


### DB 계정·로그인·권한 (2026-11-20)

브라우저 앱은 서버 AccountService만 사용한다. 계정·역할·활성 상태는 `studio_accounts`, 역할별 권한은 `studio_role_permissions`, 등록/변경 작업은 `studio_account_operations`, 세션은 `studio_auth_sessions`, 이력은 `studio_audit`, 로그인 제한은 `studio_login_attempts`에 저장한다. 비밀번호 검증은 Supabase Auth가 수행하며 앱 테이블·브라우저에는 비밀번호와 검증값을 저장하지 않는다. sessionStorage에는 서버가 발급한 세션 토큰·만료 시각과 요청 재시도용 작업 ID만 보관한다. 이전 목업 계정/세션은 초기화 시 제거하며 `local:` 토큰이나 브라우저 권한 변조로 로그인할 수 없다.

- `POST /api/auth/login`: ID·비밀번호로 로그인한다. 응답은 access/refresh token, expires_in, identity(account/policy)다.
- `POST /api/auth/refresh`, `POST /api/auth/logout`, `GET /api/auth/me`: 갱신·세션 해제·현재 DB 계정/정책 조회다. 서버는 JWT와 등록된 세션 버전·계정 활성 상태를 확인한다.
- `GET/POST /api/accounts`, `PATCH /api/accounts/{account_id}`, `POST /api/accounts/{account_id}/reset-password`: 관리자 계정 조회·등록·이름/역할/상태 변경·비밀번호 재설정이다. 생성·재설정은 operation_id로 재시도하며 다른 입력에 같은 ID를 사용하면 409다.
- `GET /api/accounts/assignment-options`: 업무 배정 권한으로 활성 계정의 배정용 최소 필드를 조회한다.
- `GET /api/roles`, `PUT /api/roles/{role}/{permission}`, `GET /api/audit`: 관리자 정책·감사 이력 관리다. 계정/권한/감사 기능은 관리자에게 고정한다. 마지막 활성 관리자의 사용 중지·역할 해제는 409다.

서버가 요청마다 권한을 검사하며 권한 부족은 403이다. 역할·활성 상태·비밀번호 변경은 세션을 해제한다. 화면은 서버 정책을 표시하고 탭 간 알림·포커스·주기적 조회로 변경을 반영한다. 로그인 전 보호된 데이터를 요청하지 않으며 새로고침은 등록된 서버 세션으로 복원한다.

로그인 화면은 비밀번호 입력칸에 포커스가 들어온 뒤 첫 키 누름 또는 뗌 이벤트부터 Caps Lock 상태를 확인한다. 브라우저가 켜진 상태를 알려주면 비밀번호 표시 여부와 관계없이 입력칸 아래에 ‘Caps Lock이 켜져 있습니다.’를 표시한다. 이후 키 이벤트에서 꺼진 것으로 확인되거나 입력칸에서 포커스가 벗어나면 안내를 숨긴다.

`seed-test-accounts`는 local Supabase 환경에서 admin(ADMINISTRATOR)/user1(USER1)/user2(USER2)를 명시적으로 구성하는 관리 명령이다. 비밀번호는 대화형 또는 파일로 받고 앱 시작 시 자동 실행하지 않는다. 없는 계정만 생성하며 기존 계정 ID·권한·표시 이름·비밀번호는 유지한다. 예상 역할·활성 상태가 다르면 충돌을 보고하고, `--reset-passwords`를 지정한 경우에만 기존 비밀번호와 세션을 변경한다. 초기 USER1/USER2의 기획 권한은 동일하다. 브라우저 목업의 계정 ID·검증값과 기존 로컬 DB 데이터는 자동 이전하지 않는다.

## 업무 배정

`studio_source_assignments(source_id,account_id)`는 서버 관계다. GET 업무 목록은 소유 업무와 배정받은 게시 업무를 합친다. 배정자는 이름·설명·게시 ID/스냅샷·게시 시각·모델 정보만 받으며, 저장소 경로와 분석 상세는 업무 소유자에게만 제공한다. `can_manage`는 소유 여부이고 역할 권한과 별도로 판단한다.

배정 조회/변경은 `GET /api/sources/{id}/assignments`, `PUT/DELETE /api/sources/{id}/assignments/{account_id}`다. 인증 actor는 토큰에서만 얻고 서버에서 업무 소유권을 검사한다. 게시 업무만 배정한다. 프로젝트 생성은 소유자 또는 배정자를 검사하고 프로젝트 owner는 항상 인증 actor다. 다른 사람의 기획에 대한 관리자 예외는 없다.

새 AI 요청·질문 답변 재개·역할 검토 시작/재시도는 source row를 잠그고 배정을 재검사한다. 배정 해제와 새 작업 시작은 같은 잠금으로 직렬화하며 이미 시작한 작업은 고정된 기준으로 완료할 수 있다. 동일 실행 ID의 재요청은 새 작업을 만들지 않는다. 배정 해제 뒤에도 본인 프로젝트·revision·확인본 내보내기는 유지한다. 프로젝트 묶음의 `source_access`로 화면에도 상태를 안내한다.

005 마이그레이션은 project source/owner 복합 FK를 source FK로 대체한다. snapshot/source 복합 FK와 프로젝트 기준·publication·revision 불변성은 유지한다. 기획 기능 허용 정책과 소유권·배정 조건은 서버에서 함께 검사한다.

## 인증 안정화·현업 진행 상태 보완 (2026-11-23)

- reset은 계정 ready/active를 변경하지 않고 operation과 세션 폐기를 관리한다. 완료된 operation 재요청은 멱등이며 오래된 미완료 reset이 새 reset을 덮어쓰지 못한다. 원격 쓰기 결과가 불명확하면503 `detail.code=auth_write_uncertain`이며 재인증 후 재시도할 수 있다. 인증 서버429/JWKS 연결503을 인증 실패401과 구분한다.
- 자격증명 실패는 계정별15분30회, IP 전체 요청은 별도15분600회다. 성공 로그인/인증 인프라 오류는 자격증명 실패에 포함하지 않는다.
- 감사 조회의 기존 `before`와 `limit`를 유지하며 `{items,next}`의 next는 문자열/null이다. 이력 화면이 이전 페이지를 이어서 조회한다.
- 프로젝트 목록에 읽기 전용 `progress_status`를 추가한다. 최신 작업이 답변 대기이면 awaiting_answers, queued/running이면 generating, 최신 실패이면 failed, pending 초안이면 review_ready, 확인본이 있으면 confirmed, 나머지는 conversation이다. 취소된 작업과 실패하지 않은 대화 작업은 이 상태 계산에서 제외한다. 더 나중에 완료된 대화는 이전 대화 실패 표시를 해제하지만 문서 생성 실패를 해제하지는 않는다.
- 업무 선택과 목록 필터는 독립이다. 업무 선택 후 설명에서 유형(기본 improve)을 변경할 수 있다. 생성 전에는 대화/업무 요약, 생성 후에는 기존 산출물과 확인 안내를 표시한다. 현재 질문은 중복 표시하지 않으며 기존 대화 기록은 유지한다. 현업 대화에서 초안·수정안 생성이 최근 사용자 메시지를 재사용해도 같은 대화 기록을 한 번 더 추가하지 않는다.
- 미전송 입력은 생성에 암묵적으로 포함하지 않고 먼저 전송하도록 안내한다. 같은 탭에서 계정별 임시 입력과 기준 버전에 연결된 직접 편집을 복원한다. 인증 만료 시 보존하며 명시적 로그아웃 시 제거한다. 임시 보관은 서버 저장/확정과 다르다. 기존 확인본만 내보내며 자동 승인·외부 전달은 추가하지 않는다.

계정 등록 재시도는 pending 계정의 loginId/이름/역할이 동일한 경우 기존 계정/인증 UID를 사용해 완료한다. 새 작업에서 요청한 비밀번호를 실제로 적용한 뒤 ready로 전환한다. ready 계정 중복 등록 및 pending 메타데이터 불일치는409이며, 오래된 미완료 작업은 새 작업을 덮어쓰지 못한다.
