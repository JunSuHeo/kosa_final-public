# 팀 온보딩과 일감 보드

담당 팀원은 JS다. 새 팀원이 로컬 앱을 실행하고 일감을 맡아 PR을 올릴 수 있게 한다.

## 계획

1. 루트 README에서 개인 설정과 개발 문서를 찾을 수 있는지 링크를 검사한다.
2. 공용 명령으로 mock 서비스와 격리 검증을 실행해 실제 동작을 확인한다.
3. PR·Issue 양식과 AI 분석 라벨 조건을 점검한다.
4. GitHub Projects에서 저장소 연결, 네 가지 상태, 비공개 여부를 확인한다.

## 변경과 검증

- 루트 README에 시작 순서, 개인 팀원 설정, 개발 문서와 Issue부터 PR까지의 흐름을 연결했다. 로컬 링크·앵커 12개를 확인했다.
- 공용 Makefile은 체크아웃 전용 mock Compose 환경과 기존 백엔드·Playwright 검사를 사용한다. `make up` 뒤 웹 HTTP 200과 API의 DB 준비·mock 인증·AI 상태를 확인했다. `make ps`로 웹·API·DB 포트를 확인했고 `make down` 뒤 개발 DB 볼륨이 유지됐다. `make logs`는 호출 명령을 확인했다.
- `make test`에서 PostgreSQL 백엔드 35개, `make e2e`에서 브라우저 시나리오 7개가 통과했다. 두 검증의 임시 Compose 환경은 정리됐다.
- PR·일반 Issue 템플릿과 Actions의 `ai-plan` 조건을 확인했다. 기본 브랜치 반영이나 GitHub Actions 실실행은 아직 진행하지 않았다.
- [비공개 팀 일감 보드](https://github.com/users/JunSuHeo/projects/1/views/1)를 저장소에 연결했다. 할 일 → 진행 중 → 리뷰 중 → 완료 순서를 화면에서 확인했다. 저장소에 `ai-plan` 라벨을 만들었다. 기존 Issue는 일괄 가져오지 않았다.
- 사용자 승인 후 현재 저장소의 두 팀원에게 보드 Write 초대를 보냈다. GitHub 보드 권한 목록에서 두 팀원 모두 Write로 표시되는 것을 확인했다.
