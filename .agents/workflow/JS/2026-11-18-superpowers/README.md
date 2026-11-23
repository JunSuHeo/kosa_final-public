# 팀 공용 Superpowers 추가

- 담당 팀원 JS, 작업 에이전트 Codex
- 목표는 팀원이 저장소를 갱신하면 Codex에서 Superpowers 스킬 묶음을 사용할 수 있게 하는 것이다.
- 완료 조건은 프로젝트 범위의 활성화 설정, 공용 목록 연결, Codex 탐색 확인이다.

## 계획

1. 공식 Codex 플러그인의 식별자를 확인하고 프로젝트에 등록한다.
2. 신뢰된 저장소에서 플러그인과 기존 스킬의 탐색을 확인한다.

## 변경과 검증

- 공식 마켓플레이스의 `superpowers@openai-curated`를 프로젝트 설정에서 활성화해 봤다. CLI 목록에서는 활성화됐지만 설치되지 않은 상태였고, 새 app-server의 `skills/list`에도 노출되지 않았다. 시험용 설정을 제거했다.
- [Superpowers 7.0.2 원본 스킬](https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills)과 MIT 라이선스를 `.agents/skills/superpowers/`에 추가했다. 원본과 파일 단위로 일치한다.
- Codex app-server `skills/list`에서 Superpowers 15개 및 `caveman`, `find-skills`가 프로젝트 경로에서 활성 상태로 검색됐고 신규 문서 링크가 열렸다. 스킬을 사용한 실제 개발 흐름은 실행하지 않았다.
- 공유 브랜치에 반영한 뒤 팀원은 체크아웃을 갱신해 `$systematic-debugging` 등 개별 스킬을 호출할 수 있다.
