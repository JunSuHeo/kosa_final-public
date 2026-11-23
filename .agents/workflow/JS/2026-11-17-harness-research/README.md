# 프로젝트에 적용할 하네스 보강 조사

- 날짜: 2026-11-17 (Asia/Seoul)
- 상태: 조사 완료, 구현 제안
- 담당 팀원: JS (.agent-local.md 확인)
- 참여 AI 에이전트·담당 범위: 단일 개발 에이전트, 저장소 정적 조사·공식 자료 조사·우선순위 제안
- 공동 작업의 대표 기록·관련 팀원 기록: 해당 없음
- 요청·목표: 에이전트 하네스의 일반적인 구성과 현재 프로젝트에 적합한 추가 항목을 조사한다.
- 완료 조건: 기존 구성·부족한 부분을 구분하고 실제 근거와 함께 적용 우선순위·구체적 파일/절차를 제안한다.
- 변경 범위: 조사 기록과 작업 목록만 갱신한다. 제안한 하네스 기능과 서비스 코드는 구현하지 않는다.

## 읽은 근거

- AGENTS.md, PRJ/AGENTS.md, PRJ/agents/project.md·infra.md, workflow 규칙·로컬 팀원 설정.
- PRJ의 테스트·E2E·평가 스크립트·의존성·검증 문서.
- OpenAI Docs 스킬로 아래 공식 문서·개발 자료를 검색하고 본문을 확인했다.

## 계획

1. 현재 구성과 반복·실패 지점 확인 → 실제 파일·명령·설정 대조.
2. 공식 자료 조사 → 구현 맥락과 적용 범위 확인.
3. 후보·우선순위·단계별 제안 정리 → 링크·문서 변경 범위 검증.

## 판단·진행 요약

- 조사 대상은 팀의 개발 에이전트 하네스다. 제품 내부 AI 런타임은 별도 개선 대상으로 구분한다.
- 현재 서비스 실행·키·모델·DB는 변경하지 않는다.

## 조사 결과

하네스에는 보통 지침·맥락 탐색, 반복 작업 도구, 실행 환경 분리, 작업 상태·인계, 검증·평가, 실행 근거가 포함된다. 현재 저장소에는 지침·맥락 문서·팀원별 기록·개별 검증 도구가 있다. 우선 보강할 부분은 변경 유형에 따른 검증 연결과 동시 작업의 환경 분리다. 아래 우선순위는 공식 자료와 현재 저장소를 비교한 제안이다.

### 현재 확인한 구성

| 구성 | 확인한 근거 | 보강할 부분 |
| --- | --- | --- |
| 지침·문서 탐색 | 루트/PRJ AGENTS.md, PRJ/agents 4개 | 지침을 계속 늘리기보다 반복 확인을 도구화 |
| 팀원·작업 기록 | .agent-local.md, .agents/workflow/JS·SY·SW | 브랜치·기준 커밋·다음 행동 등 재개 정보 |
| UI 빌드 | PRJ/frontend/package.json의 `tsc -b && vite build` | 변경별 검증 진입점. lint 명령은 현재 등록되지 않음 |
| 서버 검증 | PRJ/backend/tests, compose test profile | 실행기에서 격리 DB·mock 전제 확인 |
| E2E | PRJ/scripts/e2e.sh | Compose 프로젝트명·포트가 고정되어 같은 호스트에서 동시 실행 충돌 가능 |
| 계약 | docs/spec의 OpenAPI·snapshot schema·예시와 서버/클라이언트 타입 | 계약 문서와 실제 구현의 자동 대조 |
| AI 평가·운영 검증 | evaluate_luna.py, verify_operations.py 등, docs/evaluation-plan.md | 기존 자료 재사용·실패 재현·새 변경의 비교. 과거 기록을 현재 결과로 단정하지 않음 |
| 저장소 자동화 | 루트/PRJ의 .github, .agents, .codex, Makefile·justfile 확인 시 없음 | 공통 검증이 정리된 다음 CI·재사용 스킬 연결 |

### 1. 변경 유형별 검증 실행기 — 우선 적용

제안 위치: `PRJ/scripts/harness/verify.py`. 문서·frontend·backend·계약·E2E 등 검사 범위를 명시적으로 지정하고 기본은 비용 없는 정적/mock 검사로 한다. 무엇을 실행할지 먼저 보여주는 모드도 두면 검토하기 쉽다. 파일 변경 기반 자동 선택은 이 기본 흐름이 안정된 뒤 추가한다.

| 변경 | 실행할 검증 제안 |
| --- | --- |
| 안내·기록 문서 | 로컬 링크·앵커·담당자 경로·필수 안내 존재 검사 |
| UI 코드·타입 | npm ci·기존 build, 동작 변경에 관련 mock E2E |
| 서버 코드·migration | 격리 PostgreSQL pytest, 필요한 통합 시나리오 |
| API·snapshot | 계약 일치 검사 + backend·frontend 영향 확인 |
| Compose·worker 복구 | 격리 통합·복구 검사 |

실행기에는 실행 디렉토리·검증 환경·종료 코드·시각·결과 파일을 남긴다. 개인 파일·키·전체 환경변수는 기록하지 않는다. 실패·미실행·통과를 구분하고 live 호출을 자동으로 섞지 않는다. 기존 스크립트와 테스트를 호출하며 별도 테스트 체계를 복제하지 않는다.

AGENTS.md의 규칙은 실행 환경의 강제 차단 장치가 아니다. DB·모드·서비스 대상 확인과 검사 실패 시 nonzero 종료는 실행기/CI에서 구현해야 한다. 문서 경로 검증은 안내 무결성을 검사할 뿐, 지침을 실제로 읽고 준수했는지 보증하지 않는다.

### 2. 팀원·작업별 코드와 테스트 환경 분리 — 우선 적용

JS/SY/SW 폴더는 기록을 구분한다. 같은 체크아웃의 코드나 같은 Docker 환경을 분리하지 않는다. 각자의 체크아웃/브랜치에서 작업하고 한 호스트에서 여러 작업을 병행할 때는 Git worktree를 선택적으로 사용한다.

현재 e2e.sh 5~8행은 `planning-studio-e2e`, `54332/8011/5175`를 강제로 설정하고 31행도 5175를 고정한다. 같은 Docker 호스트의 동시 실행은 서비스·DB를 공유하거나 서로의 컨테이너를 종료할 수 있다. 별도 PC·별도 Docker 호스트끼리는 이 포트 충돌이 발생하지 않는다. 테스트 fixture도 테이블을 TRUNCATE하므로 DB 공유는 피해야 한다.

보강안: 담당자와 실행 ID별 Compose 프로젝트·DB volume·포트 묶음, Playwright base URL 연동, 자신이 만든 자원만 종료하는 정리 규칙. 팀원 코드만으로는 한 팀원의 동시 작업을 구분하지 못하므로 실행 ID까지 사용한다. 복잡한 포트 자동 할당보다 명시적 포트 지정·충돌 확인부터 시작할 수 있다. 새 worktree에는 Git 제외 개인 설정과 서버 환경 파일을 안전하게 준비하는 절차도 필요하다.

### 3. API·snapshot 계약 회귀 검사 — 우선 적용

제안 위치: `PRJ/scripts/harness/check_contracts.py`와 관련 기존 테스트. `PRJ/agents/testing.md`는 검증 경로·판정 기준이 기존 문서보다 길어질 때만 추가한다.

- DB 연결이나 서비스 기동 없이 비교할 수 있는 schema·예시부터 검사한다. FastAPI 앱 import/설정 로드가 필요한 검사는 mock·격리 환경을 명시한다.
- Pydantic schema와 docs/spec/snapshot.schema.json, 실제 라우트의 OpenAPI와 저장된 openapi.json을 순서 등 비의미 차이를 정규화해 비교한다. 설명·생성용 strict schema와 API 계약 schema를 혼동하지 않는다.
- 예시 snapshot·역할 검토 결과를 실제 validator에 넣고, TypeScript build와 API 시나리오로 클라이언트 영향도 확인한다. TypeScript build만으로 서버와의 계약 일치가 보장되지는 않는다.
- 승인 전 확정본 불변·타인 리소스 404·끊긴 연결 blocking·다른 snapshot의 근거 거부는 기존 테스트에서 계속 검증한다.

이번 조사는 계약 파일의 불일치를 재현한 것은 아니다. 계약이 여러 곳에 표현되어 있어 향후 변경 누락을 찾기 위한 제안이다.

### 4. 재개·인계 정보 보강 — 적은 비용으로 적용

이미 계획·결과·인계 템플릿이 있으므로 별도 일지를 계속 추가하지 않는다. 작업 README에 다음 정보만 보강한다.

- 작업 브랜치·기준 커밋, 시작 당시 존재한 다른 변경.
- 현재 단계·마지막 실제 검증 결과·남은 문제.
- 다음에 수행할 구체적인 한 가지 행동과 관련 경로.
- 다른 팀원이 수정 중인 파일·의존 작업·미결정 사항.

긴 작업이나 인계가 있는 경우에만 별도 handoff 파일로 분리한다. 완료 기록을 작성하는 것과 새 세션에서 복구 가능한 상태를 남기는 것은 구분해 확인한다.

### 5. 반복 절차용 스킬 — 실행 절차가 안정된 뒤

제안 위치: 루트 `.agents/skills/studio-verify/SKILL.md`, `.agents/skills/studio-handoff/SKILL.md`.

첫 스킬은 변경 영역·검증 전제·기존 실행기 호출·결과 보고를, 둘째는 현재 상태·검증·다음 행동·관련 기록 연결을 담당한다. 각 영역의 agents 문서는 참조하고 복사하지 않는다. JS/SY/SW는 사람별 기록 구분이며 스킬이나 AI 역할 이름으로 재사용하지 않는다.

Codex의 repo-local 스킬 위치와 SKILL.md 형식은 공식 문서에 근거한다. 다른 에이전트 도구까지 사용하려면 해당 도구의 탐색·설치 방식을 별도로 확인해야 한다. 현재는 스킬을 만들거나 설치하지 않았다.

### 6. 같은 검증의 CI 실행 — 공통 실행기 다음 단계

제안 위치: 저장소 루트 `.github/workflows/verify.yml`. 로컬에서 쓰는 같은 명령을 실행한다. 문서·frontend build·격리 backend 검사부터 시작하고 UI E2E는 환경과 실행 시간을 보고 추가한다. 기본 CI에는 개인 설정 파일이나 실제 API 키가 없어도 동작하게 한다. 개인 식별 검사는 로컬 전용이고 CI에서는 공유 구조와 테스트 계약을 검사한다.

CI 파일 추가와 저장소의 필수 검사/브랜치 보호 설정은 별개의 작업이다. 어느 쪽도 이번 조사에서 설정하지 않았다.

### 7. 하네스 자체 평가와 실패 사례 축적 — 사용 후 보강

개발 하네스 평가와 제품 AI 품질 평가는 구분한다.

- 개발 하네스: 문서 수정 때 서비스 기동 없음, JS 기록 경로 선택, backend 수정 때 격리 검사 수행, 무관한 파일 변경 없음, 명령 실패를 통과로 보고하지 않음 등 소수 과제로 반복 관찰한다. 코드 테스트만으로 작업 절차 준수를 평가했다고 주장하지 않는다.
- 제품 AI: 기존 evaluation-plan과 스크립트를 재사용해 요청 외 수정·근거 불일치 등 실패 사례를 고정 fixture로 축적한다. mock/정적 회귀와 실제 모델의 의미 품질·비용 평가를 분리한다.
- live 평가는 입력·모델·프롬프트·반복 조건·예산을 명시하고 비용 미확인도 기록한다. 현재 runtime/model은 조사하지 않았으며 과거 Luna 수치를 현재 성능으로 해석하지 않는다.

### 적용 순서와 최소 범위

1차는 변경별 검증 실행기, 같은 호스트에서의 테스트 분리, 계약 검사와 기존 인계 템플릿 보강으로 제안한다. 작업을 나눠 완료 조건별로 검증한다. 2차에 반복 절차를 스킬로 묶고 같은 검증을 CI에 연결한다. 평가 과제는 실제 실패 기록을 바탕으로 조금씩 축적한다.

지금 추가할 필요가 낮은 것은 별도 agent 서버, 상시 다중 에이전트 실행 체계, 전용 메모리 DB, 새로운 대형 관측 플랫폼이다. 현재 3명 팀에는 기존 문서·스크립트·테스트를 연결하는 편이 적은 운영 부담으로 효과를 확인하기 쉽다는 판단이다.

## 공식 자료와 적용 근거

- 반복되는 정해진 검사는 스크립트로 만들고, 스킬은 해석·절차 선택을 묶는 데 쓴다. AGENTS.md와 repo-local 스킬, CI의 연결 사례를 참고했다. [Using skills to accelerate OSS maintenance](https://developers.openai.com/blog/skills-agents-sdk)
- 상태·계획·검증 근거를 저장소에 남기고 단계별 검증으로 긴 작업을 이어가는 사례를 인계 보강의 근거로 삼았다. [Run long horizon tasks with Codex](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex)
- worktree가 파일 체크아웃을 분리하는 기능임을 확인했다. 포트·DB 분리 필요성은 이 저장소의 E2E·fixture를 확인해 도출했다. [Worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees)
- 스킬은 name·description이 있는 SKILL.md와 선택적 스크립트·참조 자료로 구성되며 필요할 때 본문을 읽는다. [Build skills](https://learn.chatgpt.com/docs/build-skills)
- 결과뿐 아니라 절차·효율을 소수 기준으로 평가하는 방법을 하네스 평가에 적용할 수 있다. [Testing Agent Skills Systematically with Evals](https://developers.openai.com/blog/eval-skills)
- GOALS·PLANS 등은 선택적 관례이지 필수 파일이 아니므로 기존 작업 README·계약·계획과 중복 생성하지 않는 방향을 선택했다. [Iterating Development Workflows with Codex](https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex)

## 검증

- 조사 결과는 현재 파일의 정적 확인과 공식 웹 자료 본문을 대조한 것이다. 서비스·테스트·실제 모델은 실행하지 않았다.
- Python 정적 확인: 원래 AGENTS.md 1~4절과 기존 PRJ 지침 보존, Markdown 15개 펜스·공백, 로컬 링크·앵커 43개 통과. 공식 출처 6개는 웹 도구로 본문을 확인했다.
- `git diff --check` 통과. 이번 변경은 이 조사 기록과 .agents/workflow/README.md·.agents/workflow/JS/README.md의 목록 연결뿐이다.

## 결과·인계

- 구현 후보와 우선순위를 정리했다. 제안 항목은 아직 구현하지 않았다.
- 서비스 코드·설정·실행 상태를 변경하지 않았다. 다음 작업은 위 1차 제안 중 적용할 범위를 정해 구현·검증하는 것이다.

## 후속 조사: GitHub 일감 관리 연결

- 날짜: 2026-11-17 (Asia/Seoul). 상태: 조사 완료, 미구현.
- 질문: GitHub의 일감을 개발 하네스의 입력으로 사용할 수 있는가.
- 확인: 로컬 origin은 `https://github.com/JunSuHeo/kosa_final.git`이다. 현재 PATH에서 gh 명령은 확인되지 않았다. GitHub 플러그인은 검색 시 미설치 상태였으며 설치·연결 가능한 항목을 안내했다. 저장소의 실제 Issues/Projects 활성 상태·권한·데이터는 조회하지 않았다.
- 제안: Issue는 요구사항·범위·완료 조건, Projects는 담당자·우선순위·상태, workflow는 구현 판단·검증·인계, PR은 코드 리뷰·병합의 기준으로 구분한다. 원본 일감·상태는 GitHub에서 관리하고 로컬에는 Issue 링크와 작업 근거를 남긴다.
- 흐름 예시: Ready Issue 선택 → 담당 팀원 확인 → 관련 AGENTS/agents 문서 확인 → 작업 브랜치·기록 생성 → 구현·검증 → Issue를 연결한 PR → 리뷰·기본 브랜치 병합 → Issue 종료·Project Done.
- 식별: 로컬 JS/SY/SW와 실제 GitHub 계정의 대응을 설정해야 한다. 코드만으로 assignee를 추정하지 않는다. 작업 기록에 Issue URL·번호, 브랜치, PR URL을 추가하면 추적하기 쉽다.
- 초기 적용 후보: 기능/버그 Issue 템플릿, PR 템플릿, 최소 라벨, Project 보드, AGENTS의 Issue 기반 작업 규칙. 현재는 만들지 않았다.
- 자동화: 처음에는 사용자가 지정한 Issue 하나를 처리하는 방식으로 시작한다. 보드 상태 갱신·자동 일감 선택은 기본 절차가 검증되고 필요한 연결 권한을 확인한 뒤 추가한다. GitHub의 상태 변경이 로컬 에이전트 실행을 자동으로 시작하는 것은 아니며 별도 실행 트리거가 필요하다.
- 연결 범위: 플러그인 연결 후 실제 Issue·PR·Project 작업 지원 범위를 확인한다. Projects 필드 갱신 등 지원이 부족하면 인증된 GitHub CLI/API 연계를 검토한다. 이번에는 Issue·댓글·PR 생성이나 외부 상태 변경을 수행하지 않았다.
- 근거: [Projects 개요](https://docs.github.com/en/issues/planning-and-tracking-with-projects)는 Issue/PR 보드·표·사용자 정의 필드를 지원한다. [기본 자동화](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-built-in-automations)는 Issue 종료·PR 병합 등에 따른 상태 변경을 제공한다. [Issue와 PR 연결](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue)은 PR 본문의 `Closes #번호`와 기본 브랜치 대상·병합 조건을 설명한다.
- 검증: Git 원격·명령 가용성은 로컬 읽기 전용으로, GitHub 기능은 공식 문서 본문으로 확인했다. 외부 연동 실행은 미확인이다.

## 후속 조사: 팀 공용 스킬 관리

- 날짜: 2026-11-17 (Asia/Seoul). 상태: 조사 완료, 미구현.
- 제안: 이 저장소의 루트 `.agents/skills/`를 Git으로 관리한다. 현재 3명·한 프로젝트에서는 별도 스킬 저장소보다 코드와 스킬의 버전을 함께 맞추기 쉽다. 이후 여러 프로젝트에서 재사용할 필요가 생기면 별도 배포·플러그인 구성을 검토한다.
- 후보: `kosa-issue-start`(지정 Issue의 목표·범위·완료 조건을 읽고 개발 준비), `kosa-verify`(기존 검증 명령 선택·실행·보고), `kosa-handoff`(현재 상태·검증·다음 행동·Issue/PR 연결 정리). 현재 이 스킬들을 생성하지 않았다.
- 역할 구분: AGENTS.md는 공통 규칙, PRJ/agents 문서는 제품 구조·맥락, 공용 스킬은 반복 절차, workflow는 실행 결과, PRJ/prompts는 서비스 내부 모델 프롬프트다. 스킬에서 원래 문서를 참조하며 내용을 중복 관리하지 않는다.
- 팀 운영 제안: 스킬 변경도 Issue·브랜치·PR로 관리하고 사용 조건·입력·출력·예시·검증 결과를 함께 리뷰한다. 같은 Git 커밋의 스킬을 기준으로 재현하며 개인 설정·도구 인증은 각자가 준비한다. 스킬 파일 공유만으로 GitHub 접근 권한이 생기지는 않는다.
- 공식 확인: Codex는 작업 디렉토리에서 저장소 루트까지의 `.agents/skills`를 탐색한다. 각 스킬은 name·description을 포함한 SKILL.md가 필수이며 스크립트·참조 자료는 선택이다. 다른 에이전트 도구의 발견 규칙까지 동일하다고 가정하지 않는다. [Build skills](https://learn.chatgpt.com/docs/build-skills)
- 검증 범위: 공식 문서 본문 확인과 적용 위치 제안만 수행했다. 공용 스킬 생성·설치·호출 검증은 미실행이다.
