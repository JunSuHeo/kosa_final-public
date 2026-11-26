# 초안 이후 산출물 중심 배치와 시안 중앙 정렬

- 날짜: 2026-11-26 (Asia/Seoul)
- 상태: 완료
- 담당 팀원: SY
- 참여 AI 에이전트·담당 범위: Codex — 프런트엔드 구현·테스트·검증; layout_review — 최종 코드 읽기 전용 리뷰([별도 기록](agents/review.md))
- 공동 작업의 대표 기록·관련 팀원 기록: 해당 없음
- 요청·목표: 저장된 초안 표시 후 대화창 기본 폭을 42%에서 30%로 전환하고 상세 시안을 캔버스 중앙에 정렬한다.
- 완료 조건: 단계별 너비 저장·복원, 확대/축소된 시안 중앙 정렬·넘침 접근, 프런트엔드 빌드 및 격리 E2E 검증.
- 변경 범위: App의 단계 연결, WorkspaceDivider, Wireframes 상세 표시, 관련 CSS·브라우저 테스트·프런트엔드 안내.

## 읽은 근거

- 루트 AGENTS.md, PRJ/AGENTS.md, PRJ/rules/project.md, frontend.md, infra.md
- PRJ/docs/spec/README.md, PRJ/README.md, 관련 소스와 workspace-width/visual-fit/Studio 테스트
- 승인된 계획은 현재 대화의 「초안 생성 후 산출물 중심 배치와 시안 중앙 정렬」이다.

## 계획

1. 단계별 너비와 시안 정렬 회귀 테스트 작성 → 변경 전 실패 확인.
2. 단계별 너비 저장 및 확대/축소 크기 기반 정렬 구현 → 회귀 테스트 통과.
3. 빌드·격리 E2E·최종 리뷰 → 실제 결과와 미확인 사항 기록.

## 판단·진행 요약

- 확인한 사실: 대화/산출물 단계가 이미 구분되어 있지만 너비는 단일 저장값(기본 42%)을 사용한다. hplan.css가 시안 상세를 왼쪽 정렬하고 top-left 확대/축소를 강제한다.
- 선택과 이유: 승인된 계획의 기존 미커밋 변경 보존을 위해 현재 feat/source-user-assignments 체크아웃에서 작업한다. 별도 worktree로 기존 작업을 옮기거나 커밋하지 않는다.
- 단계별 기본값: conversation=0.42, documents=0.30. 기존 hplan-workspace-ratio.v1은 대화 단계에서만 사용한다.
- 검증 경계: UI 상태별 배치 회귀는 API 응답을 제어하는 Playwright 테스트, 실제 API 연계는 별도 DB/Auth/mock AI를 쓰는 scripts/e2e.sh로 구분한다.
- 실패·대안·범위 변경: Docker 소켓·테스트 서버 포트는 기본 샌드박스에서 접근이 거부되어 테스트 실행에만 추가 권한을 사용한다. Chromium은 libnspr4/libnss3/libasound가 누락되어 첫 실행이 시작 전에 실패했다. 기존 `/tmp/kosa-push-browser-libs/extracted/usr/lib/x86_64-linux-gnu`를 테스트 프로세스의 LD_LIBRARY_PATH에 지정하고 재실행했다. 제품 설정은 변경하지 않는다.
- 조사 인계: 서버 결과의 persistedArtifact가 단계 전환 근거이며, 작업 중 partial에는 영향받지 않는다. CSS의 무조건적인 flex-start/top-left 조합이 확대/축소된 시안의 왼쪽 치우침 원인이다.
- 구현: 단계별 기본값·저장값을 분리하고, 상세 시안은 ResizeObserver로 원본 너비/높이를 측정해 확대/축소된 크기의 래퍼를 중앙 정렬한다. 가용 영역을 넘으면 일반 블록의 auto margin이 0이 되어 시작을 보존한다.
- 최종 리뷰: 별도 read-only 리뷰 에이전트가 700px 이하 속성 패널의 기존 absolute 배치가 시안을 덮는 문제를 지적했다. 브라우저에서 실제 275px 겹침을 재현한 뒤, 화면 시안 속성 패널만 일반 flex 배치로 유지해 가용 캔버스에서 제외한다. 흐름도 inspector 배치는 변경하지 않는다. 다른 확정 결함·보류 경미 항목은 없었다.

## 변경 파일

- PRJ/frontend/src/App.tsx, WorkspaceDivider.tsx: 기존 단계에 따라 대화/산출물 비율·저장값 분리.
- PRJ/frontend/src/Wireframes.tsx, hplan.css: 실제 확대/축소 크기로 중앙 정렬하고 모바일 속성 패널의 겹침 제거.
- PRJ/frontend/tests/workspace-layout.spec.ts: 저장된 초안 전환·단계별 폭·실패/취소·중앙 정렬·모바일 패널·넘침 회귀.
- PRJ/scripts/e2e.sh: 기존 검사 목록을 보존하면서 workspace-layout/visual-fit 검사 추가.
- PRJ/rules/frontend.md, PRJ/README.md: 단계별 배치·저장·조절 및 시안 사용 안내.
- .agents/workflow/SY/README.md 및 이 작업 기록: 작업 연결·판단·검증 인계.

## 검증

| 실행 위치 | 명령·확인 방법 | 결과 | 근거·한계 |
| --- | --- | --- | --- |
| PRJ/frontend | npm run build (baseline) | 통과 | exit 0; 기존 미커밋 변경 포함 |
| PRJ/frontend | API 제어 Playwright workspace-layout (구현 전) | 기대한 실패 확인 | 3 failed / 3 passed: 단계 전환·단계별 저장·중앙 오차(41.5px) 재현 |
| PRJ/frontend | API 제어 Playwright workspace-layout (1차 구현 후) | 통과 | 6 passed (29.4s), exit 0 |
| PRJ/frontend | 1440px에서 시안이 들어갈 때 가로 스크롤 검사 | 통과 | 1 passed (6.9s), exit 0; 추가 결함 없음 |
| PRJ/frontend | 모바일 속성 패널 회귀 (수정 전) | 기대한 실패 확인 | 1 failed; 패널과 캔버스 275px 겹침 |
| PRJ/frontend | API 제어 Playwright workspace-layout (모바일 패널 수정 후) | 통과 | 7 passed (35.9s), exit 0 |
| PRJ/frontend | npm run build (최종 제품 코드) | 통과 | exit 0; Vite build 9.05s |
| PRJ | LD_LIBRARY_PATH 지정 후 sh scripts/e2e.sh (1차 코드) | 통과 | 75 passed (6.8m), exit 0; 모바일 패널 최종 보완 전 실행. 해당 테스트 컨테이너·볼륨 정리 완료 |
| PRJ | LD_LIBRARY_PATH 지정 후 sh scripts/e2e.sh (최종 코드·테스트) | 통과 | 76 passed (6.6m), exit 0; Studio 생성·승인·편집·복원, 기존 계정/업무 배정, 시안 목록 맞춤, 최종 레이아웃 7개, 기존 너비/모바일 전환 포함 |
| 저장소 루트 | git diff --check 및 새 기록 링크 확인 | 통과 | 제품·환경·lockfile의 요청 외 변경 없음; 기존 미커밋 변경 보존 |
| PRJ/frontend | API 제어 화면 캡처 정적 확인 | 확인 | 1800px 데스크톱, 390px 모바일, 700px 속성 패널 표시. 캔버스 중앙과 패널 비겹침 확인 |

## 결과·인계

- 완료 내용: 초안 저장 이후 30% 기본 폭 전환, 단계별 조절값 저장/복원, 상세 시안 중앙 정렬·확대/축소 크기 반영·넘침 접근, 모바일 속성 패널 비겹침, 안내·회귀 테스트 반영. 빌드 및 최종 격리 E2E 76개 통과. 리뷰의 Important 1건은 RED→GREEN으로 수정했고 보류 항목은 없다.
- 검증 인계: 별도 Compose 프로젝트의 DB/Auth/mock AI를 사용했다. 두 실행의 해당 컨테이너·볼륨·이미지 정리가 완료됐고, 임시 Vite 5193 서버도 종료했다. 기존 서비스·DB·환경 설정은 변경하거나 재시작하지 않았다.
- 미확인·남은 작업: 요청된 구현에서 남은 작업 없음. 실제 Supabase 외부 인증·live 모델 호출·운영 서비스 배포는 이번 검증 대상이 아니다. 커밋·푸시·병합은 수행하지 않고 기존 작업 브랜치에 변경을 남겼다.
- 다른 에이전트 기록·정제한 로그 링크: [최종 리뷰](agents/review.md). 실행 로그는 작업 전용 /tmp/kosa-workspace-layout-*.log이며 사용자 데이터·운영 비밀을 기록하지 않았다.

## 후속 확인과 브랜치 게시 준비 (2026-11-26)

- 사용자 요청에 따라 현재 작업분 전체를 새 브랜치에 커밋하고 원격에 게시한다. 연결 설정의 유저 배정 변경과 작업공간 배치 변경을 함께 포함한다.
- 실행 중인 5178 웹의 CSS에는 이전 왼쪽 정렬 규칙이 남아 있다. 동일한 API fixture 브라우저 검사에서 중앙 오차 41.5px로 실패했다.
- 현재 작업트리를 별도 Vite 5196 포트에서 검사한 중앙 정렬·모바일 속성 패널·넘침 접근 테스트는 3개 모두 통과했다. 테스트 서버는 종료했다.
- 게시 준비 검증으로 PRJ/frontend에서 npm run build를 다시 실행해 통과했다. 저장소 루트의 git diff --check와 sh -n PRJ/scripts/e2e.sh도 통과했다. 변경 파일 17개의 비밀키 패턴 검사에서 발견 항목은 없었다.
- 전체 격리 E2E 76개 통과는 위 구현 당시 기록이다. 이번 게시 준비에서는 빌드와 정적 검사를 실행했다.
- 게시 브랜치는 feat/source-assignments-workspace-layout이다. 실행 중인 서비스의 웹 빌드 갱신은 후속 작업으로 남아 있다.

## 최신 main 기반 게시 (2026-11-26)

- 사용자 추가 요청으로 원격 main을 fetch하고 로컬 main을 pull --ff-only로 733c849까지 갱신했다.
- 최신 main에서 feat/source-assignments-workspace-layout-main 브랜치를 생성하고 전체 작업 커밋 e244eef를 cherry-pick했다. 자동 병합된 안내 문서와 source-planning 테스트의 작업 변경을 확인했고 충돌은 없었다.
- 최신 main 통합 상태에서 PRJ/frontend의 npm run build와 origin/main...HEAD 대상 git diff --check가 통과했다. origin/main이 작업 브랜치의 조상인 것도 확인했다.
- 최초 요청 때 만든 feat/source-assignments-workspace-layout 브랜치는 로컬에 보존된다. 게시 대상은 feat/source-assignments-workspace-layout-main이다.

## 실행 웹 갱신 (2026-11-26)

- 사용자의 갱신 요청으로 feat/source-assignments-workspace-layout-main의 최신 main 통합 코드를 planning-studio-supabase 웹 5178에 빌드·적용했다. 기존 Compose 환경 파일과 compose.yaml, infra/supabase.compose.yaml, infra/dev.compose.yaml을 사용해 up --build -d --no-deps web을 실행했다.
- 이미지 빌드와 웹 컨테이너 재생성이 완료됐다. 제공 자산은 index-CikoTvri.js 및 index-CZTp_XlA.css다.
- 최신 Compose는 웹을 studio-proxy 네트워크에 배치하지만 기존 API는 default 네트워크만 사용해 최초 health 검사에서 502가 발생했다. 기존 API를 planning-studio-supabase_studio-proxy에 api 및 studio-proxy-api 별칭으로 연결해 복구했다. 이후 /health가 status=ok, auth_mode=supabase, ai_mode=mock으로 응답했다.
- 5178의 실제 정적 빌드에서 API 응답을 fixture로 대체한 workspace-layout.spec.ts 전체 7개가 통과했다(18.6s, exit 0). 단계별 폭 저장·복원, 중앙 정렬, 확대·축소, 모바일 속성 패널, 넘침 스크롤을 검증했다. 실제 사용자 데이터와 외부 인증 흐름은 이번 브라우저 검사의 대상에서 제외했다.
- 웹 갱신 후 API는 healthy, worker는 실행 상태임을 확인했다. 실행 웹 갱신 후속 항목을 완료했다. 검증 산출물은 /tmp/kosa-wire-centering-deployed-results에 보관한다.
