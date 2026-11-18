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

## 5. 작업 영역과 지침 적용

- 이 저장소 루트는 `kosa_final/`이다. 실제 서비스의 개발·수정 대상은 `PRJ/`이며, 개발 과정의 기록은 `.agents/workflow/`에 둔다.
- 작업 시작 시 루트 `.agent-local.md`를 읽어 담당 팀원(JS/SY/SW)과 그에 맞는 `.agents/workflow/코드/` 기록 경로를 확인한다. 이 파일은 개인 식별·기록 경로 설정용이며 제품 계약이나 공통 지침을 대체하지 않는다.
- 파일이 없거나 미설정·잘못된 값이면 현재 대화에 명시된 담당 팀원을 사용한다. 대화에도 없으면 담당자를 사용자에게 확인하고 임의로 추정하지 않는다. 사용자가 이번 작업의 담당자를 명시하면 그 값을 우선하며 개인 파일은 수정 요청이 있을 때 갱신한다.
- `.agent-local.md`는 Git에서 제외한다. 다른 팀원은 `.agent-local.example.md`를 복사해 자신의 코드·경로를 설정한다.
- 서비스 변경 전 반드시 `PRJ/AGENTS.md`를 읽는다. 그 파일의 제품 계약·인증·revision·검증 규칙을 적용한다. 더 가까운 경로에 AGENTS.md가 있으면 해당 범위의 지침도 확인한다.
- `PRJ/AGENTS.md`의 경로는 PRJ 기준이다. 이 루트 문서의 경로는 kosa_final 기준이다. 기존 문서에 남은 이전 경로나 날짜를 현재 실행 상태로 가정하지 않는다.
- `PRJ/`는 사용 중인 서비스 소스다. 사용자 요청 범위 밖에서 실행 설정·모델·데이터를 바꾸거나 서비스를 재시작하지 않는다. 검증은 분리된 DB·Compose 프로젝트·포트·볼륨을 사용한다.
- `.agents/workflow/`에는 제품 코드, 서비스 환경 파일, 사용자 데이터, DB dump를 넣지 않는다.

## 6. 문서를 기준으로 개발하기

개발 전 다음 순서로 읽는다. 문서 열람만으로 끝내지 말고 관련 소스·테스트까지 확인한다.

1. `PRJ/AGENTS.md`
2. [PRJ/agents/project.md](PRJ/agents/project.md)
3. 변경 영역에 해당하는 문서. 여러 영역이면 모두 읽는다.

| 작업 영역 | 먼저 읽을 안내 |
| --- | --- |
| 제품 흐름·디렉토리·영향 범위 | [project.md](PRJ/agents/project.md) |
| UI·컴포넌트·클라이언트 상태·화면 검증 | [frontend.md](PRJ/agents/frontend.md) |
| API·schema·DB·worker·AI·저장소 분석 | [backend.md](PRJ/agents/backend.md) |
| 실행·환경변수·Docker·배포·격리 검증 | [infra.md](PRJ/agents/infra.md) |

- agents 문서는 현재 구성, 소스 책임, 실제 호출 형태, 개발·검증 전제를 설명한다. 계약 원본은 `PRJ/docs/spec/`, 실행 안내는 `PRJ/README.md`를 함께 확인한다.
- 문서와 구현이 다르면 불일치를 기록하고 관련 소스·테스트·계약을 확인한다. 추정이나 과거 통과 기록을 현재 사실로 쓰지 않는다.
- 구조·사용법·API·실행 방법을 바꾸면 같은 작업에서 해당 agents 문서와 기존 소유 문서도 갱신한다. 필요한 안내 문서는 추후 같은 디렉토리에 추가하고 위 표와 project.md에 연결한다.

## 7. 에이전트 작업 기록

- 모든 개발 작업은 [.agents/workflow/README.md](.agents/workflow/README.md)의 형식을 따른다. 시작 시 목표·완료 조건·계획을 적고 완료 시 변경·검증·인계 내용을 남긴다. 작은 작업은 작업 README 하나로 기록한다.
- 기록 경로는 `.agents/workflow/{JS|SY|SW}/YYYY-MM-DD-작업명/`이며 날짜는 Asia/Seoul 기준이다. JS/SY/SW는 담당 팀원 구분이고 AI 에이전트 이름이 아니다. 새 작업은 담당 팀원 폴더의 README에 연결한다. 개별 작업의 기록·검증·인계 중에는 공용 `.agents/workflow/README.md`를 수정하지 않는다. 안내 문서나 스킬에 공통 목록에도 연결하라는 문구가 있으면 이 규칙을 우선한다.
- 여러 팀원이 함께 하는 작업은 대표 담당자의 기록 하나를 기준으로 삼고 다른 팀원의 관련 기록을 서로 연결한다. 팀 공통 결정은 `.agents/workflow/README.md`에 요약하고 상세 근거를 링크한다. 기존 루트의 초기 공통 하네스 기록은 보존한다.
- 고민한 내용은 확인한 사실·결정·짧은 근거·대안·남은 질문으로 요약한다. 내부 사고 과정 전문이나 원시 대화 전체를 저장하지 않는다.
- 여러 에이전트가 실제 참여하면 공통 목표와 담당 파일·의존성을 명시하고 각자의 기록을 별도 파일에 남긴다. 병렬 실행을 기본으로 요구하지 않으며 사용자 요청과 실행 환경의 에이전트 사용 규칙을 따른다.
- API 키·JWT·비밀번호·개인정보·비공개 코드 원문을 기록하지 않는다. 실행 근거는 필요한 부분만 정제해 남긴다.

## 8. 완료와 검증

- 요청에 맞는 완료 조건을 먼저 정하고 변경 규모에 맞는 검증을 수행한다. 문서만 바꾼 작업은 링크·경로·명령 전제·기존 지침 보존 여부를 확인한다.
- 서비스 코드 변경은 해당 영역 문서와 PRJ/README.md의 검증 명령을 따른다. 실제 서비스 DB를 테스트에 연결하지 않는다.
- 기록과 완료 보고는 실제 실행·mock/live·정적 확인·미실행·미확인 항목을 구분한다. 실행하지 않은 예시를 통과했다고 쓰지 않는다.
- 완료 보고에는 변경 내용, 검증 결과, 남은 작업을 간결하게 적는다.

## 9. 팀 공용 스킬

- 공용 스킬 원본은 루트 `.agents/skills/`에 두고 코드와 함께 Git으로 관리한다. 개인 전역 디렉토리에 복사해 별도 원본을 만들지 않는다.
- 아래 조건에 해당하면 해당 SKILL.md를 읽고 적용한다. 문서의 역할과 실행 명령은 기존 소유 문서를 참조한다.

| 사용 시점 | 공용 스킬 |
| --- | --- |
| 지정 GitHub Issue로 개발 시작·준비 | [kosa-issue-start](.agents/skills/kosa-issue-start/SKILL.md) |
| 변경 검증·완료 전 점검 | [kosa-verify](.agents/skills/kosa-verify/SKILL.md) |
| 팀원·에이전트 인계 또는 여러 단계 작업 마무리 | [kosa-handoff](.agents/skills/kosa-handoff/SKILL.md) |

- 스킬을 적용해도 사용자 요청 범위·기존 승인·도구 권한은 달라지지 않는다. GitHub 연결·개인 설정은 각 팀원이 준비한다.
- 변경·리뷰·사용 예시·공유 방법은 [공용 스킬 관리](.agents/workflow/README.md#공용-스킬-관리)를 따른다.
