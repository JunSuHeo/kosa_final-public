# 팀 공용 스킬 3개 구축

- 날짜: 2026-11-17 (Asia/Seoul)
- 상태: 완료
- 담당 팀원: JS (.agent-local.md 확인)
- 참여 AI 에이전트·담당 범위: 단일 개발 에이전트, skill-creator로 공용 스킬·문서 작성
- 공동 작업의 대표 기록·관련 팀원 기록: 해당 없음
- 요청·목표: kosa-issue-start, kosa-verify, kosa-handoff를 루트 .agents/skills에서 팀 공용으로 관리한다.
- 완료 조건: 스킬 3개 작성, 사용 시점·관리 규칙 연결, 형식·참조·원문 보존 검증, 적용 예시와 미확인 범위 기록.
- 변경 범위: 스킬·지침·개발 안내·작업 기록. 서비스 코드는 변경하지 않는다.
- Issue·PR: 연결된 일감 없음. 이번 요청만으로 GitHub에 Issue·댓글·PR을 생성하지 않는다.
- 코드 기준: main, 시작·현재 HEAD `cda60b152f996b533d29a07d23798fd74921f3a1`. 이번에는 커밋·push를 수행하지 않았다.
- 시작 당시 변경: 이전 하네스의 루트/PRJ 지침·agents 안내·로컬 설정 예시·workflow 기록이 이미 미커밋/미추적 상태였다. 이를 보존하고 관련 안내에 이번 내용을 덧붙였다.

## 읽은 근거

- AGENTS.md, PRJ/AGENTS.md, PRJ/agents 4개, .agents/workflow/README.md.
- 기존 package.json·Compose·Playwright·E2E 스크립트와 skill-creator 지침·quick_validate.py.
- 이전 [하네스 조사](../2026-11-17-harness-research/README.md)의 공식 스킬 문서와 팀 공용 스킬 적용안.

## 계획

1. 짧은 지침형 스킬 3개 작성 → 사용 조건·입출력·기존 문서/명령 참조 검토.
2. 공통 지침·팀 관리 안내 연결 → 1~4절과 기존 제품 계약 보존·링크 확인.
3. 작성 도구의 validator와 문서 작업 검증 적용 → 실제 수행과 미실행을 구분해 인계.

## 판단·진행 요약

- 세 스킬은 하나씩 명확한 역할을 갖고, 기존 안내·계약·명령을 참조한다. 별도 실행기·서버·배포 체계는 추가하지 않는다.
- SKILL.md만으로 구성한다. 초기 버전에 불필요한 스크립트·UI 설정·참조 디렉토리를 만들지 않는다.
- 스킬 배포는 Git 변경으로 준비하며 개인 전역 스킬 디렉토리에는 복사하지 않는다.
- 자동 발견은 기본 동작을 유지한다. 이 세션에서 목록에 나타나지 않아도 파일을 직접 읽고 적용할 수 있으며, 새 세션의 선택 동작과 실제 GitHub 연동은 별도 검증 대상이다.

## 검증

이번 문서 작업에서 kosa-verify와 kosa-handoff의 파일을 직접 읽고 적용했다. 스킬 자동 선택 시험이나 독립 평가와는 구분한다.

| 실행 위치 | 확인 방법 | 결과 | 근거·한계 |
| --- | --- | --- | --- |
| kosa_final/ | skill-creator의 quick_validate.py를 각 스킬에 실행 | 통과 | 3개 모두 종료 코드 0, Skill is valid |
| kosa_final/ | YAML name·description·폴더명 대조 | 통과 | 이름 일치·필수 메타데이터 확인 |
| kosa_final/ | Markdown·로컬 링크·앵커·공백 검사 | 통과 | 18개 파일, 로컬 링크 67개. 미추적 SKILL.md 포함 |
| kosa_final/ | 작업 전 스냅샷과 지침 비교 | 통과 | 기존 루트·PRJ 지침 전체를 접두 원문으로 보존, 1~4절 포함 |
| kosa_final/ | 제품 파일 SHA-256을 작업 전과 대조 | 통과 | 서비스 소스·테스트·스크립트·설정 등 109개 내용 동일 |
| kosa_final/ | git diff --check, git check-ignore | 통과 | 공백 검사 통과, 개인 설정 Git 제외 유지 |
| kosa_final/ | Issue 준비·검증·인계 사용 예시의 입력과 결과 정적 검토 | 확인 | Issue 미지정 시 임의 조회/배정 금지, 문서 변경은 정적 검사, 인계는 기존 README 갱신. 실제 원격 Issue 처리 시험은 아님 |
| PRJ/ | 제품 테스트·Docker 기동·DB·실제 모델 호출 | 미실행 | 스킬·문서 작업 범위이므로 실행하지 않음 |
| Codex/GitHub | 새 세션 자동 발견·자동 선택·실제 Issue/PR 연동 | 미확인 | 파일 형식과 직접 적용 결과로 대체 주장하지 않음 |

## 변경 파일

- .agents/skills/kosa-issue-start/SKILL.md: 지정 Issue 준비·작업 연결.
- .agents/skills/kosa-verify/SKILL.md: 변경별 검증·환경 전제·보고.
- .agents/skills/kosa-handoff/SKILL.md: 현재 상태·검증·다음 행동 인계.
- AGENTS.md: 사용 시점과 관리 링크 추가.
- PRJ/AGENTS.md, PRJ/agents/project.md: 공용 스킬 위치·문서 역할 연결.
- .agents/workflow/README.md: 공용 변경·리뷰·공유·사용 예시와 작업 링크.
- .agents/workflow/JS/README.md, 이 파일: 작업 목록과 실제 결과.

## 결과·인계

- 세 공용 스킬과 관리 규칙을 로컬 저장소에 구성했다. 사용자·환경별 하드코딩 없이 각자의 담당 설정과 인증을 사용한다.
- 이번 변경의 스킬 파일과 새 작업 기록은 미추적, 기존 추적 지침·workflow 안내는 미커밋 상태다. 이전 작업의 미커밋/미추적 파일도 함께 존재하므로 커밋 시 변경 범위를 확인한다.
- 완료된 검증과 미확인 범위는 위 표와 같다. 제품 코드는 바꾸지 않았다.
- 다음 행동: 팀이 공유할 변경 범위를 검토해 GitHub에 반영한 뒤 각자의 체크아웃에서 kosa-verify 등 실제 요청으로 스킬 발견·동작을 확인한다. GitHub 게시나 병합은 이번에 수행하지 않았다.
