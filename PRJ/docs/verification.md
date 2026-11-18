# Studio v2 검증 기록

검증일: 2026-10-15. 새 구현을 기준으로 기록했다. 이전 구현의 테스트 수나 live 결과를 재사용하지 않았다.

## REA와 보관

- 공식 `rea-agents@6.5.0` CLI로 공개 JS를 정적 분석했다. 전체 Evidence와 원본은 Git 제외 `.research/manyfast/`에 있다.
- 로그인된 실제 편집기는 읽기 위주로 화면/메뉴/탭을 관찰했다. 원본 서버/프롬프트/DB는 미확인이다.
- 이전 소스는 별도 내부 백업에 보관했다.
- 압축 파일의 169개 파일/링크를 manifest로 기록하고 모든 일반 파일의 SHA-256을 압축본에서 재검증했다. node_modules/.venv/파이썬 캐시만 재생성 가능 항목으로 압축에서 제외했다. 원래 디렉터리 파일도 original-files에 옮겼다.
- 기존 PostgreSQL/export volume을 삭제하거나 새 데이터로 덮어쓰지 않았다.

## 재현 설치와 서버 검증

`uv lock`, `uv sync --frozen`, `npm install`로 lockfile을 작성했다. 이후 Docker와 격리 E2E의 `npm ci`, Docker의 `uv sync --frozen --no-dev`가 성공했다.

`docker compose --profile test run --build --rm test`: **21 passed (2.23s)**. SQLite를 사용하지 않고 별도 PostgreSQL `studio_test` DB에서 실행했다.

검증한 항목:

- 프로젝트+revision 0+초기 job 원자 저장, 생성 요청의 멱등성.
- 401/404 소유권 경계, RS256/ES256 JWT의 서명과 필수 claims/issuer/audience/만료 검증.
- 운영 mock 거부와 설정 오류의 비밀값 비노출.
- 질문 ID/전체 key/기준 버전, 중복 답변.
- 생성 후 proposal 유지, 경고 확인, 동시 중복 승인, 반대 결정 충돌, 거절.
- 수동 수정 시 이전 candidate/확정 revision 불변, stale 기준 거부, DB trigger.
- 끊긴 참조/도달 불가 노드 차단, 항목 삭제 경고, 실행 코드 block 거부.
- 취소/재처리/단계 복원, committed proposal의 worker 실패 덮어쓰기 방지.
- 실제 공급자 오류를 mock으로 대체하지 않는 실패 경로.
- 승인 버전의 JSON/Markdown export와 와이어프레임/연결 ID 보존.

Starlette TestClient의 httpx 지원에 대한 deprecation warning 1개가 있다. 테스트 실패는 아니다.

## 브라우저

`sh scripts/e2e.sh`는 별도 Compose 프로젝트/DB volume/포트에서 실제 API+worker+브라우저를 실행한다. 제품 데이터와 모델을 공유하지 않는다. 일반 E2E에서는 live 전용 화면 테스트 한 개를 의도적으로 skip한다.

세 시나리오: 아이디어→질문→네 산출물→승인→수동 편집→새로고침→과거 버전→복원 제안→거절→다운로드, 와이어프레임 편집의 승인 전 불변성, 390px 모바일의 패널·와이어프레임 속성 토글.

초기 통과 후 모바일 속성 패널/긴 지표 설명/수정 진행 표시를 보완했다. 한 검증 실행은 병렬 Playwright가 같은 test-results를 정리해 trace 파일을 잃는 오류가 있었고, live/mock 결과 디렉터리를 분리해 재검증했다. 최종 결과: **mock E2E 3 passed (15.0s)**, live 전용 검증 1 skipped. 별도 실제 프로젝트 화면 검증은 **1 passed (2.1s)**이며 브라우저 pageerror 0개다. PRD·와이어프레임·유저플로우 화면을 docs/screenshots/에 저장하고 시각 확인했다.

## 실제 AI 생성

모델: `openrouter` / `openai/gpt-6.1-sol`, 프롬프트 `studio.v1`.

- 생성 시간: 215.15초, 실제 모델 호출 5회.
- PRD 10개 항목, 요구사항 5개, 기능 9개.
- 유저플로우 25개 노드/51개 간선, 모바일 와이어프레임 6개.
- 새 서버 검증에서도 blocking 0. 가정 확인 warning 1개.
- 원시 usage/단계 시각/응답 ID는 `live-smoke.json`에 보존했다.

## 실제 AI 수정

검증용 프로젝트에 생성한 초안을 v1으로 확정한 뒤, '독서 기록 수정' 화면의 버튼 문구 한 개만 바꾸도록 요청했다.

- 수정 시간: 125.53초, 실제 모델 호출 1회.
- 요청한 label만 변경: True.
- 기존 승인 snapshot과 current_version=1 유지: True.
- blocking 0. 결과는 승인하지 않은 새 proposal로 남겼다.
- 비교와 usage는 `live-revision-smoke.json`에 있다.

전체 실제 호출 6회, 공급자 usage의 총 토큰 56,784, 보고 비용 합계 **US$0.308072**다. 이 값은 해당 1개 도메인의 생성·수정 검증 비용이며 일반적인 비용/품질 벤치마크가 아니다.

## 미검증과 범위

Supabase 실계정 로그인은 미검증이다. JWT 검증 자체의 단위 테스트와 실제 로그인 서비스의 통합 검증을 구분한다. 다양한 도메인의 품질 반복 평가, 다중 사용자 부하, 운영 백업 복구 리허설, 장기 사용성 평가는 수행하지 않았다.

결제/공동편집/문서 업로드/MCP는 구현 범위에 포함하지 않는다. 다섯 관점의 의미 검토는 아래 추가 검증을 참고한다.

## 최종 실행 상태

새 서비스 localhost:5174와 API localhost:8010이 실행 중이다. /health는 database=ready, auth_mode=mock, ai_mode=live, openrouter/openai/gpt-6.1-sol을 반환한다. 검증용 프로젝트는 v1 확정본과 버튼 문구 하나를 바꾼 검토 대기 proposal을 보관한다.

이전 planning-agent의 API/worker/web/DB/test DB 컨테이너는 중지했다. 기존 볼륨을 삭제하지 않았다. 격리 E2E 컨테이너는 종료했고 backend test DB도 중지했다. 새 서비스의 API/worker/web/DB만 유지한다.

이 디렉터리는 부모 Git 저장소에서 미추적 상태였다. 이번 작업에서 Git commit/push 또는 외부 배포는 하지 않았다.


## 추가: 개발자·기획자·보안·UI/UX·QA 검토

프롬프트 `review.v1`, 모델 `openrouter/openai/gpt-6.1-sol`. 독립된 다섯 역할의 입력은 동일한 저장 snapshot이며 다른 역할의 결과를 사용하지 않는다. 동시 호출 상한은 3이다.

실제 독서 기록 프로젝트의 pending proposal에 **5회 호출, 66.63초**, 개발자 4·기획자 3·보안 3·UI/UX 3·QA 3으로 총 **16개 지적**을 생성했다. 5개 역할 모두 완료했고 서버의 ID/원문 인용 검증을 통과했다. 공급자 보고 usage 합계 133,678 tokens, 비용 **US$0.391540**. 단일 사례의 결과이며 일반 품질·비용 벤치마크가 아니다. 원본 보고서·usage·상태·대상 해시는 실제 검증 증거(`live-review-smoke.json`)에 있다.

검토 전후 revision·pending proposal·current_version이 동일함을 비교했다. 역할 결과는 원문 근거·문제·수정 제안·관찰 가능한 검수 기준을 담는다. 실제 구현 취약점을 발견했다고 주장하지 않는다.

화면 검증은 실제 저장 보고서를 조회했으며 추가 모델 호출이 없다. 데스크톱과 390px 모바일, 역할 전환·근거 이동·콘솔 pageerror 0을 확인했다. 데스크톱(`screenshots/live-role-review.png`), 모바일(`screenshots/live-role-review-mobile.png`).

추가 PostgreSQL 테스트는 다섯 역할 완료와 중복 요청/worker 잠금, 확정본 불변, 다른 소유자/프로젝트 경계, 부분 실패와 실패 역할만 재시도, 비밀 오류 비노출, 허위 근거 거부, 새 proposal과 결과 분리, 재시작 시 완료 역할 보존, 공급자 변경 시 실패, 독립된 다섯 호출과 서로 다른 역할 프롬프트를 확인한다.

최종 추가 검증 결과: PostgreSQL **29 passed (3.61s)**, 프런트엔드 빌드 성공. 격리 mock 브라우저 **4 passed (22.2s)**, 실제 역할 검토 브라우저 **1 passed (1.9s)**. 기존 Starlette/httpx deprecation warning 1개는 유지된다. OpenAPI fixture가 실행 중 API와 일치함을 확인했다.

## 2026-11-10: Luna 적용과 추가 검증

아래는 위 2026-10-15 기록과 별도인 현재 실행 근거다. 기존 Sol 결과를 덮어쓰지 않았다.

### 실행 적용 및 실제 smoke

- API·worker 양쪽에 `live / openrouter / openai/gpt-6-luna` 적용. API 및 웹 proxy health 모두 `database=ready`. 실행 설정 근거(`luna-runtime.json`).
- 실제 생성: 질문 응답 후 **56.77초**, 모델 호출 5회. PRD 4개 항목·요구사항 4개·기능 6개·흐름 노드 12개/간선 17개·화면 5개. blocking 0, 가정 확인 warning 1. 생성 근거(`luna-live-smoke.json`).
- 검증용 초안만 v1 승인 후 실제 수정: **38.51초**, 버튼 label 한 개만 변경. 요청 외 필드, 승인 snapshot과 current_version 유지. 수정 근거(`luna-live-revision-smoke.json`).
- 실제 역할 검토: 최초 **30.26초**, 4개 역할 완료·UI/UX 1개 원문 인용 불일치로 실패. 최초 실패(`luna-live-review-smoke.json`). 실패 역할만 재시도해 5개 완료했고 기존 4개 결과와 기획 데이터가 동일함을 확인했다. 재시도(`luna-live-review-retry.json`).
- 이 smoke와 재시도에서 저장된 usage 11회, 보고 토큰 하한 100,963, 보고 비용 하한 **US$0.017965505**. 최초 실패 UI/UX 호출 1회는 현재 서버가 usage를 저장하지 않아 비용 미확인이다. 따라서 실제 전체 호출은 12회이며 위 비용은 완전한 청구 합계가 아니다.

### PostgreSQL 및 mock 브라우저

- `docker compose --profile test run --build --rm test`: **29 passed (3.38s)**. 별도 PostgreSQL `studio_test`. 기존 Starlette/httpx 경고 1개.
- `sh scripts/e2e.sh`: **4 passed (21.8s), 2 skipped**. 당시 live 화면 테스트 2개는 의도적으로 제외했다. 실행 후 E2E 컨테이너를 종료했다.
- 프런트엔드 Docker 빌드 성공. npm 설치에서 moderate 취약점 1개가 보고됐다. 이번 범위에서 자동 의존성 변경은 하지 않았다.

### 격리 운영 부하 및 백업 복구

- 별도 `planning-studio-ops` Compose 프로젝트·54333/8012/5176 포트·전용 volume에서 명시적 mock 사용.
- 10개 스레드의 첫 요청을 서로 다른 사용자 10명에게 배정하고 총 20개 프로젝트 생성. 최종 실행 **206 HTTP 요청**, 예상 밖 상태 코드 0. 교차 소유자 조회는 404. 생성 최장 **3.172초**, 전체 부하 구간 **5.409초**.
- 동일 proposal 동시 승인 10회가 v1 한 개로 수렴. 동일 대상 역할 검토 10회가 report 한 개로 수렴. job별 중복 proposal 0.
- worker 중지 후 실제 mock 산출물의 PRD·usage·질문 답변으로 저장 stage를 구성했다. 프로세스 재시작 뒤 해당 PRD와 앞선 usage가 보존되고 남은 단계만 실행됨을 확인했다. 실제 live 모델 호출 중 강제 종료 시험은 아니다.
- PostgreSQL custom dump를 같은 격리 서버의 별도 DB에 복원. 앱 테이블 7개의 전체 행 SHA-256/개수가 일치했다. revision 불변 trigger 차단, 역할 결과 보존, 복원된 대기 job의 단일 proposal 생성을 확인했다. 복원 **0.122초**, 복원 job 처리 **0.452초**.
- 최초 테스트는 저장 질문 답변이 누락돼 정상 보정 단계가 추가되면서 검사 두 개가 실패했다. 최초 결과(`operations-verification-initial.json`)를 보존하고 문맥을 보완했다. 문맥 보완 결과(`operations-verification-context-fix.json`), 최종 10명 동시 배정 결과(`operations-verification.json`). 제품 코드를 변경한 복구 수정은 없었다.
- dump는 Git 제외 `.research/operations/studio-mock.dump`, 복원 DB명·테이블 hash는 최종 JSON에 보존했다. 제품 DB/볼륨은 덮어쓰지 않았다. 로컬 소규모 mock 검증이며 실제 모델 처리량/운영 최대 용량의 근거가 아니다.

### 실제 화면, 연결 복구, 발견한 프록시 문제

- 실제 Luna 프로젝트를 조회하는 Playwright: 데스크톱 1600px·모바일 390px에서 PRD·와이어프레임·흐름·역할 검토 확인 **1 passed (2.4s)**. pageerror 0. 모바일은 기존 사용 흐름대로 채팅 패널을 접고 산출물을 본다.
- 접속 시 health 요청 실패를 주입하고 `다시 연결` 뒤 같은 프로젝트의 초안·제목 조회: **1 passed (1.2s)**.
- 모바일 와이어프레임(`screenshots/luna-wireframes-390.png`), 모바일 역할 검토(`screenshots/luna-review-390.png`)를 시각 확인했다. 데스크톱 증거도 같은 디렉터리의 `luna-*-1600.png`에 보존했다.
- API 교체 뒤 기존 nginx가 이전 IP를 참조해 웹 `/health`가 502를 반환하는 문제를 재현했다. `infra/nginx.conf`에 Docker DNS resolver와 동적 upstream을 적용했다. 설정 방식은 [nginx 공식 문서](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#server)를 참고했다.
- 격리 환경에서 기존 API IP를 임시 컨테이너가 점유하도록 해 새 API의 IP가 반드시 달라지게 했다. 웹 컨테이너를 교체하지 않고 `/health`와 인증된 `/api/projects`가 **10.087초**에 회복됐다. nginx 설정 검사도 통과했다. 강제 IP 변경 복구 근거(`proxy-recovery-verification.json`).

### 아직 완료할 수 없는 항목

- 사용자가 Supabase 테스트 계정이 없다고 답해 실제 로그인·두 계정 격리·실제 만료 토큰 UI 검증은 대기한다. [준비 절차](supabase-verification.md).
- 반복 평가의 실행별·항목별 의미 품질은 사람의 점수·근거가 필요하다. 사용자 총평 3/5점은 별도 기록했으며 구조 통과를 사람 평가 통과로 표시하지 않는다.
- 사용자와 3일 실제 사용 기록으로 합의했다. [사용성 기록](usability-log.md)은 아직 사용자 기록이 없으며 장기 평가를 완료 처리하지 않았다.

### 실제 반복 평가 최종 결과

- 독서 기록·회의실 예약·동네 행사 3개 도메인에서 동일 입력으로 각 2회 수행했다. 생성·수정·다섯 역할 검토 총 6개 사례를 모두 보존했다. [조건](evaluation-plan.md), [결과표](luna-evaluation-report.md), 원시 집계(`luna-evaluation-summary.json`).
- 생성 blocking 0 및 승인 후 확정본 보존 **6/6**, 요청한 label만 수정 **5/6**, 역할 검토 최초 완료 **22/30**. 이 조건을 모두 만족한 실행은 **2/6**이다. 사람 의미 품질 점수는 미평가다.
- 저장된 usage **58회**, 보고 토큰 하한 **558,465**, 보고 비용 하한 **US$0.10834927**. 근거 검증 실패 호출 8회는 usage 미보존으로 비용 미확인이다. 실제 호출은 실패를 포함해 66회다. 실패 호출을 0원으로 계산하지 않았다.
- 평가 실행은 약 **123.65~149.97초/사례**. 최초 실패 사례를 재실행 성공으로 대체하지 않았다. 좁은 수정의 범위 초과와 근거 인용 불일치의 구체적 근거는 [발견 사항](validation-findings.md)에 정리했다.
- 추가 실제 부분 실패 UI 검사: 데스크톱/모바일의 PRD 마지막 영역 스크롤, 실패 역할 선택, 해당 역할만 재시도 버튼 및 1/5 완료 표시 **1 passed (1.7s)**. 모델을 추가 호출하지 않았고 pageerror 0이다.
- 사람 평가표(`luna-human-review.md`)의 점수와 사유를 사용자에게 요청했다. 사용자는 전체 결과 **3/5점**, `failed 난게있던데`라고 답했고 전체 점수라고 확인했다. 총평 기록(`luna-user-feedback.json`). 이를 실행별·항목별 점수로 확대하지 않았다.


## 기준 프로젝트 기획

2026-11-10 코드 기반 기획을 추가했다. PostgreSQL과 격리 브라우저, 실제 GitHub·Luna 실행, 공개 저장소 코딩 인계와 업무 저장소 로컬 실험을 내부 검증 자료에 분리해 기록했다.

2026-11-10 자체 호스팅 Supabase Auth에서 실제 계정 두 개의 로그인, ES256/JWKS, 401·404, 만료 후 재로그인을 별도 브라우저로 확인했다. [인증 검증](supabase-verification.md)

### 2026-11-11 월별 집계 소스 화면 연결

- 월별 집계 프로젝트 `<project_id>`의 네 화면을 로컬 소스 미리보기로 연결했다. 별도 체크아웃의 기존 `CGCLS0002`와 공통 `MainContentTemplate`을 조합해 일자별 등록·월별 집계 탭을 표시한다.
- Playwright로 집계월 조회, 사업장별 샘플 합계, 일자별 등록 탭 복귀와 집계 결과 유지, 데이터 없음, 오류 후 재조회, Studio 네 화면의 월별 탭 선택과 iframe 내부 XLSX 다운로드를 확인했다. 브라우저 오류 0. Studio TypeScript/Vite와 소스 미리보기 Vite 빌드 통과.
- 재검증 명령은 `node .research/hyundai-catering/f2-experiment/source-preview/verify-monthly.mjs`다. 확인용 집계 항목은 근무기록 수·근무시간이며 2026년 11월 가상 사업장 두 개의 샘플이다. 운영 데이터 연동과 확정 집계 규칙 구현은 별도 작업이다. 이번 검증은 외부 모델 호출을 포함하지 않는다.

2026-11-11 전체 화면 목록의 썸네일에도 연결된 소스 화면을 축소 표시한다. Playwright로 네 상태의 로드, 카드 클릭 후 해당 소스 화면 진입, 모바일 카드 폭 일치를 확인했다. 빌드 통과, 브라우저 오류 0. 표시 데이터는 앞서 연결한 로컬 샘플이다.
