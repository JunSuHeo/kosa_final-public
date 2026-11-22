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

- 이 저장소 루트는 `kosa_final-public/`이다. 실제 서비스의 개발·수정 대상은 `PRJ/`이며, 개발 과정의 기록은 `.agents/workflow/`에 둔다.
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
2. [PRJ/rules/project.md](PRJ/rules/project.md)
3. 변경 영역에 해당하는 문서. 여러 영역이면 모두 읽는다.

| 작업 영역 | 먼저 읽을 안내 |
| --- | --- |
| 제품 흐름·디렉토리·영향 범위 | [project.md](PRJ/rules/project.md) |
| UI·컴포넌트·클라이언트 상태·화면 검증 | [frontend.md](PRJ/rules/frontend.md) |
| API·schema·DB·worker·AI·저장소 분석 | [backend.md](PRJ/rules/backend.md) |
| 실행·환경변수·Docker·배포·격리 검증 | [infra.md](PRJ/rules/infra.md) |

- `PRJ/rules/` 문서는 현재 구성, 소스 책임, 실제 호출 형태, 개발·검증 전제를 설명한다. 계약 원본은 `PRJ/docs/spec/`, 실행 안내는 `PRJ/README.md`를 함께 확인한다.
- 문서와 구현이 다르면 불일치를 기록하고 관련 소스·테스트·계약을 확인한다. 추정이나 과거 통과 기록을 현재 사실로 쓰지 않는다.
- 구조·사용법·API·실행 방법을 바꾸면 같은 작업에서 해당 `PRJ/rules/` 문서와 기존 소유 문서도 갱신한다. 필요한 안내 문서는 같은 디렉토리에 추가하고 위 표와 project.md에 연결한다.

## 7. 에이전트 작업 기록

- 모든 개발 작업은 [.agents/workflow/README.md](.agents/workflow/README.md)의 형식을 따른다. 시작 시 목표·완료 조건·계획을 적고 완료 시 변경·검증·인계 내용을 남긴다. 작은 작업은 작업 README 하나로 기록한다.
- 기록 경로는 `.agents/workflow/{JS|SY|SW}/YYYY-MM-DD-작업명/`이며 날짜는 Asia/Seoul 기준이다. JS/SY/SW는 담당 팀원 구분이고 AI 에이전트 이름이 아니다. 새 작업은 담당 팀원 폴더의 README에 연결한다. 개별 작업의 기록·검증·인계 중에는 공용 `.agents/workflow/README.md`를 수정하지 않는다. 안내 문서나 스킬에 공통 목록에도 연결하라는 문구가 있으면 이 규칙을 우선한다.
- 여러 단계의 작업은 조사·구현·검증이 끝나거나 작업을 이관할 때 [단계별 인계](.agents/workflow/README.md#단계별-인계)를 작업 README에 남긴다. 작은 작업은 마지막 인계 요약으로 마무리할 수 있다.
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

- `.agents/skills/`에서 스킬을 추가·삭제·이름 변경·이동할 때는 같은 작업에서 이 표의 이름·링크·사용 시점을 갱신한다. 스킬의 사용 조건이 바뀌면 표의 설명도 맞춘다. 작업을 마치기 전에 실제 `SKILL.md` 파일과 표를 대조해 누락·중복·깨진 링크를 확인한다.

| 공용 스킬 | 사용 시점 |
| --- | --- |
| [caveman](.agents/skills/caveman/SKILL.md) | 이 저장소의 새 세션을 시작할 때 읽고 대화 응답에 기본 적용한다. 사용자가 `normal mode` 또는 `stop caveman`이라고 하면 해당 세션에서 해제한다. |
| [find-skills](.agents/skills/find-skills/SKILL.md) | 필요한 기능을 제공하는 설치 가능 스킬을 찾을 때 |
| [studio-pr-check](.agents/skills/studio-pr-check/SKILL.md) | Studio PR의 변경 범위별 검증을 고르고 결과를 정리할 때 |
| [web-design-guidelines](.agents/skills/web-design-guidelines/SKILL.md) | 웹 화면의 접근성·UX 구현을 리뷰할 때 |
| [supabase-postgres-best-practices](.agents/skills/supabase-postgres-best-practices/SKILL.md) | PostgreSQL 쿼리·마이그레이션·RLS·풀링을 변경하거나 진단할 때 |
| [playwright](.agents/skills/playwright/SKILL.md) | 브라우저에서 UI 문제를 재현하고 스크린샷·트레이스를 확인할 때 |
| [using-superpowers](.agents/skills/superpowers/using-superpowers/SKILL.md) | 대화 시작 시 적용할 스킬과 사용 순서를 확인할 때 |
| [brainstorming](.agents/skills/superpowers/brainstorming/SKILL.md) | 새 기능이나 동작을 설계할 때 |
| [writing-plans](.agents/skills/superpowers/writing-plans/SKILL.md) | 요구사항을 여러 단계의 구현 계획으로 정리할 때 |
| [using-git-worktrees](.agents/skills/superpowers/using-git-worktrees/SKILL.md) | 현재 작업 공간에서 분리해 기능을 개발할 때 |
| [executing-plans](.agents/skills/superpowers/executing-plans/SKILL.md) | 현재 세션에서 구현 계획을 직접 실행할 때 |
| [dispatching-parallel-agents](.agents/skills/superpowers/dispatching-parallel-agents/SKILL.md) | 병렬 위임이 허용되고 서로 독립적인 작업이 여럿일 때 |
| [subagent-driven-development](.agents/skills/superpowers/subagent-driven-development/SKILL.md) | 위임이 허용된 세션에서 구현 계획의 독립 작업을 맡길 때 |
| [test-driven-development](.agents/skills/superpowers/test-driven-development/SKILL.md) | 기능이나 버그 수정의 구현 코드를 쓰기 전에 |
| [systematic-debugging](.agents/skills/superpowers/systematic-debugging/SKILL.md) | 버그, 테스트 실패, 예상 밖 동작의 원인을 조사할 때 |
| [requesting-code-review](.agents/skills/superpowers/requesting-code-review/SKILL.md) | 주요 변경을 마쳤거나 병합 전 리뷰를 요청할 때 |
| [receiving-code-review](.agents/skills/superpowers/receiving-code-review/SKILL.md) | 리뷰 피드백을 검토하고 반영할 때 |
| [verification-before-completion](.agents/skills/superpowers/verification-before-completion/SKILL.md) | 완료나 테스트 통과를 보고하기 전에 |
| [finishing-a-development-branch](.agents/skills/superpowers/finishing-a-development-branch/SKILL.md) | 구현·검증을 마친 브랜치의 통합 방법을 정할 때 |
| [writing-skills](.agents/skills/superpowers/writing-skills/SKILL.md) | 스킬을 작성·수정하거나 배포 전 동작을 검증할 때 |
| [diagnosing-superpowers](.agents/skills/superpowers/diagnosing-superpowers/SKILL.md) | Superpowers 세션에서 발생한 문제의 원인을 조사할 때 |

- `studio-pr-check`의 판단이나 보고 방식이 바뀌면 [회귀 평가](.agents/evals/studio-pr-check/README.md)를 확인한다. 반복 실수는 [팀 검토 절차](.agents/workflow/README.md#반복된-문제-반영)에 따라 지침이나 스킬에 반영한다.
- 스킬을 적용해도 사용자 요청 범위·기존 승인·도구 권한은 달라지지 않는다. GitHub 연결·개인 설정은 각 팀원이 준비한다.
- 변경·리뷰·사용 예시·공유 방법은 [공용 스킬 관리](.agents/workflow/README.md#공용-스킬-관리)를 따른다.
