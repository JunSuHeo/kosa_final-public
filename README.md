# 기획실 Studio 팀 개발 가이드

기획실 Studio는 아이디어를 PRD, 기능명세, 유저플로우와 와이어프레임으로 구체화하는 웹 서비스다. 서비스 소스는 [PRJ/](PRJ/)에 있다.

## 처음 시작하기

1. Docker와 Docker Compose를 실행한다. 검증 명령은 저장소 루트에서 실행한다. Windows에서는 Docker와 연동된 WSL 환경에서 실행한다.
2. `make up`을 실행하고 출력된 **Web** 주소를 연다. 처음에는 이미지 빌드에 시간이 걸릴 수 있다. 이 개발 환경은 예제 설정의 mock 인증·AI와 로컬 PostgreSQL을 사용한다. 주소를 다시 보려면 `make ps`를 실행한다.
3. 작업 전 [루트 지침](AGENTS.md), [제품 지침](PRJ/AGENTS.md), [프로젝트 안내](PRJ/rules/project.md)를 읽는다. 변경 영역에 따라 [프런트엔드](PRJ/rules/frontend.md), [백엔드](PRJ/rules/backend.md), [인프라](PRJ/rules/infra.md) 안내를 참고한다.

## 자주 쓰는 명령

| 명령 | 동작 |
| --- | --- |
| `make up` | 현재 체크아웃 전용 mock 서비스 기동과 접속 주소 출력 |
| `make ps` | 개발 서비스 상태와 할당된 포트 확인 |
| `make logs` | 개발 로그 보기. Ctrl+C로 로그 보기를 끝낸다. |
| `make down` | 개발 서비스 종료. 개발 DB 볼륨은 유지된다. |
| `make test` | 격리 PostgreSQL에서 백엔드 테스트 실행 |
| `make e2e` | 별도 스택에서 브라우저 테스트 실행. 호스트에 Node.js와 npm 필요. |

명령 목록은 `make help`에서 확인할 수 있다. 실제 AI, Supabase, 프런트엔드 빌드와 개별 검사 명령은 [서비스 실행과 검증 안내](PRJ/README.md)를 따른다.

## 일감에서 PR까지

1. [GitHub Issues](https://github.com/JunSuHeo/kosa_final-public/issues)에 배경, 변경 범위, 완료 조건을 적는다.
2. PR에서 관련 Issue, 바뀐 동작, 실제 실행한 검증과 리뷰할 부분을 적는다. UI 변경에는 스크린샷을 첨부한다. 병합으로 완료되는 Issue는 PR에 `Closes #번호`로 연결한다.
3. 비공개 저장소에서 Issue 자동화를 구성할 때는 [Issue 자동화 안내](workflow/README.md)를 따른다.
