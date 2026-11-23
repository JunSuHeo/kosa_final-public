# 팀 공용 caveman 추가

- 담당 팀원 JS, 작업 에이전트 Codex
- 목표는 짧은 답변을 원할 때 팀원이 `$caveman`을 선택해 사용할 수 있게 하는 것이다.
- 완료 조건은 고정 버전과 라이선스를 프로젝트에 두고 공용 목록에 연결한 뒤 Codex 탐색을 확인하는 것이다.

## 계획

1. 기본 `caveman` 스킬과 라이선스 파일을 원본 커밋에서 가져온다.
2. 공용 스킬 목록에 연결하고 형식과 탐색을 검증한다.

## 변경과 검증

- [`caveman` 원본](https://github.com/JuliusBrussee/caveman/tree/a192894723a8f47e7f504c7b5041967ff1f18e55/skills/caveman)과 라이선스·저작권 고지를 `.agents/skills/caveman/`에 추가했다. 모든 파일이 원본 커밋과 바이트 단위로 일치한다.
- `quick_validate.py`를 통과했다. 공용 스킬 목록과 JS 작업 목록의 새 링크를 확인했다.
- Codex app-server의 `skills/list`에서 `caveman`과 `find-skills`가 모두 활성 상태로 표시됐다. 팀 기본 응답 스타일을 정하는 설정은 추가하지 않았다.
