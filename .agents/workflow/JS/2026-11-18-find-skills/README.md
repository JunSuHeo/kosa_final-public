# 팀 공용 find-skills 추가

- 담당 팀원 JS, 작업 에이전트 Codex
- 목표는 팀원들이 같은 `find-skills` 버전을 저장소에서 사용하도록 하는 것이다.
- 완료 조건은 `.agents/skills/find-skills/`에 고정 버전과 라이선스를 두고 공용 스킬 목록에 연결하는 것이다.

## 계획

1. Vercel Labs 원본과 라이선스를 확인한다.
2. 프로젝트 범위로 설치하고 팀 공용 스킬 목록에 연결한다.
3. 원본 일치, 스킬 형식, Codex 탐색을 확인한다.

## 변경과 검증

- Vercel Labs의 [`find-skills`](https://github.com/vercel-labs/skills/tree/57217cf86ba38148a57af9e90d14a4c049558330/skills/find-skills)를 `.agents/skills/find-skills/`에 설치했다. `SKILL.md`와 MIT 라이선스가 해당 커밋의 원본과 바이트 단위로 일치함을 확인했다.
- [팀 공용 스킬 목록](../../README.md#공용-스킬-관리)과 JS 작업 목록의 신규 링크가 실제 파일을 가리키는지 확인했다.
- `quick_validate.py`를 통과했다. 저장소 루트에서 Codex app-server의 `skills/list`로 프로젝트 경로의 `find-skills`가 활성 상태로 검색되는 것을 확인했다.
- `$find-skills`로 외부 스킬을 검색하거나 설치하는 동작은 실행하지 않았다. 팀원은 변경이 공유 브랜치에 반영된 뒤 각자 체크아웃을 갱신해 사용할 수 있다.
