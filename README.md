# H-PlanIT (기획실 Studio)

아이디어를 PRD, 기능명세, 유저플로우와 와이어프레임으로 구체화하고 변경안을 검토·승인하는 도구입니다. 연결한 GitHub 저장소의 기준 커밋을 분석해 코드 근거와 구현 지침이 포함된 변경안을 작성할 수 있습니다.

Docker Compose를 준비한 뒤 저장소 루트에서 `make up`을 실행하면 mock 인증·AI와 로컬 PostgreSQL로 Studio가 시작됩니다. 출력된 Web 주소를 여세요. `make help`에서 종료 및 테스트 명령을 확인할 수 있습니다.

- [서비스 실행 및 Supabase 연결](PRJ/README.md)
- [개발 안내](PRJ/rules/project.md)
- [Issue 워크플로 엔진과 로컬 실행](workflow/README.md)
