# 관리자 업무 연결 설정의 유저 배정

- 날짜: 2026-11-25 (Asia/Seoul)
- 상태: 완료
- 담당 팀원: SY
- 참여 AI 에이전트·담당 범위: Codex — 프런트엔드 구현·테스트·문서; review_source_assignments — 구현 이후 독립 읽기 전용 리뷰
- 공동 작업의 대표 기록·관련 팀원 기록: 해당 없음
- 요청·목표: 관리자 소유 업무를 연결 설정 화면에서 여러 유저에게 선택 후 저장 방식으로 배정한다.
- 완료 조건: 게시 전 안내, 권한에 따른 표시, 변경·취소·차이 저장, 부분 실패·응답 유실 재확인, 업무 전환 응답 격리 및 모바일 검증.
- 변경 범위: PRJ 프런트엔드, 관련 E2E, README와 frontend 안내. 기존 API·DB·별도 배정 화면은 유지.

## 읽은 근거

- 루트 AGENTS.md, .agent-local.md, PRJ/AGENTS.md
- PRJ/rules/project.md, frontend.md, backend.md, infra.md
- PRJ/docs/spec/README.md, source_api.py, accounts.py, SourceSettings.tsx, AssignmentSettings.tsx, UserManagement.tsx 및 관련 테스트
- 사용자 승인 계획: 현재 대화의 「관리자 업무 연결 설정에 유저 배정 추가」

## 계획

1. 배정의 저장·취소·부분 실패·응답 격리 E2E를 작성하고 기존 화면에서 실패 확인.
2. SourceAssignments와 설정 화면 연결을 구현하고 E2E·빌드 검증.
3. 사용 안내 갱신, 변경 리뷰, 실행 근거와 인계 기록.

## 판단·진행 요약

- 확인한 사실: 기존 API가 게시된 본인 소유 업무의 배정·해제를 지원하며 감사 기록을 서버에서 같은 트랜잭션으로 남긴다.
- 선택과 이유: 새 API 없이 변경 항목만 순차 요청하고 GET으로 결과를 확인한다. 일괄 저장은 원자적 변경을 뜻하지 않는다.
- 작업 환경: .git은 기본 샌드박스에서 읽기 전용이다. 승인된 도구 실행으로 feat/source-user-assignments 브랜치를 생성했다. 공유 체크아웃과 서비스 경로를 유지하며 기존 서비스는 재시작하지 않는다.
- 업무 전환 시 미저장 선택은 초기화한다. 화면에 안내하며 다른 업무의 응답이 새 선택을 덮지 않도록 분리한다.
- 테스트 환경 조치: 첫 격리 E2E는 Chromium의 libnspr4/libnss3/libasound 공유 라이브러리 누락으로 브라우저 시작에 실패했다. 공식 install-deps는 sudo 암호가 필요해 설치하지 못했다. 기존 `/tmp/kosa-push-browser-libs/extracted/usr/lib/x86_64-linux-gnu`를 테스트 프로세스의 LD_LIBRARY_PATH에만 적용하고 ldd의 누락 없음 확인 후 재실행한다. 제품 설정은 변경하지 않는다.
- 첫 통합 검증: 12 통과, 2 실패. 저장 중 버튼은 "배정 저장 중…"으로 바뀌므로 테스트 locator를 실제 표시명에 맞췄다. 로컬 저장소 분석은 HEAD 또는 브랜치 이름만 받으므로 테스트의 두 번째 업무 ref를 SHA 대신 격리 fixture의 실제 브랜치 이름으로 바꿨다. 제품의 저장소 계약은 변경하지 않았다.
- 독립 읽기 전용 리뷰: reviewer는 프런트엔드 변경과 테스트·계약을 검토했다. Important 3건(저장 중 업무 전환으로 잔여 요청 중단, 비활성화된 실패 대상 숨김, 응답 유실 뒤 성공 확인에도 전역 오류 잔류)을 수용해 회귀 테스트부터 추가했다. 별도 배정 화면·서버 트랜잭션·운영 Supabase 인증은 변경/검증 대상에서 제외한다.
- 리뷰 수정 방향: 저장 중 연결 선택/헤더 이동을 잠근다. 활성 후보에서 사라진 실패 대상은 이전 표시명·실패 이유와 개별 선택 취소를 제공한다. 일반 쓰기 오류는 GET 재확인 후 결과로 표시하고 인증/권한 오류만 즉시 공통 처리한다.
- 후속 Minor: 개발 StrictMode의 중복 effect에서 이전 최초 조회가 새 선택을 덮는 경합 가능성. 업무별 key로 다른 업무 응답은 격리하지만 같은 업무의 개발 모드 중복 최초 조회는 현재 production E2E로 검증하지 않는다.
- 리뷰 조치 확인: 중요 3건을 두 E2E로 재현했다. 활성 상태인 업무 선택/헤더 이동, 응답 유실 후 남은 오류 토스트, 비활성화된 실패 대상 결과의 부재를 확인한 뒤 수정했다. 새 회귀 파일은 scripts/e2e.sh 기본 목록에 포함했다.
- 리뷰 수정 후 전체 회귀에서 새 배정 8개와 게시·문서 보존 검증은 통과했다. 기존 users.spec.ts:176 권한 변경 테스트 1개는 uncheck 직후 상태 확인에서 실패했다(합계 15 통과/1 실패). 정제한 trace 확인 결과 PUT /api/roles/USER2/plans.create는 200이고 이후 snapshot도 체크 해제 상태였다. 기존 권한 화면의 비동기 조회/optimistic 상태 경합으로 관찰하며 이번 작업에서는 해당 코드를 수정하지 않고 동일 코드로 전체 회귀를 재실행한다. 해당 테스트는 앞선 15개 전체 회귀에서는 통과했다.

## 변경 파일

- PRJ/frontend/src/SourceAssignments.tsx: 임시 선택·취소·변경 저장·재조회·실패 대상 결과.
- PRJ/frontend/src/SourceSettings.tsx, App.tsx, hplan.css: 권한과 소유 업무에 배정 영역 연결, 저장 중 업무 선택/헤더 이동 잠금, 반응형 스타일.
- PRJ/frontend/tests/source-assignments.spec.ts, source-planning.spec.ts, PRJ/scripts/e2e.sh: 배정 회귀·게시 직후 배정·기본 테스트 목록 연결.
- PRJ/README.md, PRJ/rules/frontend.md: 사용법과 상태·오류 처리 안내.
- .agents/workflow/SY/README.md와 이 작업 기록: 시작·결정·검증·리뷰 인계.

## 검증

| 실행 위치 | 명령·확인 방법 | 결과 | 근거·한계 |
| --- | --- | --- | --- |
| PRJ/frontend | npm run build (변경 전) | 통과 | exit 0; Vite build 완료 |
| 저장소 루트 | Docker 접근 확인 | 통과 | 기본 샌드박스는 소켓 접근 불가, 격리 검증용 승인 실행에서 29.9.0 확인 |
| PRJ | 새 배정 E2E 첫 실행 | 실패 (환경) | Chromium 공유 라이브러리 누락. 제품 테스트에 도달하지 못함 |
| PRJ | LD_LIBRARY_PATH 지정 후 새 배정 E2E (구현 전) | 실패 확인 (RED) | 유저 배정 region/user1 체크박스가 없어 기대한 기능 부재로 실패 |
| PRJ/frontend | npm run build (구현 후) | 통과 | exit 0; TypeScript/Vite build 완료 |
| PRJ | source-planning/users/source-assignments E2E 1차 | 12 통과, 2 실패 | 실패 원인은 위 테스트 locator/fixture 전제. 기존 사용자별 기획 분리·해제 후 문서 보존 회귀 통과 |
| PRJ | 같은 3개 파일 E2E 2차 | 15 통과 | 격리 실제 PostgreSQL/Auth fixture, mock AI. 생산 코드 기준 전체 통과 후 리뷰 경합 회귀를 추가함 |
| PRJ/frontend | 390px 모바일 스크린샷 확인 | 통과 | 가로 넘침 없음; 유저 배정·저장/취소 버튼 표시 확인. 임시 이미지 /tmp/kosa-source-assignments-mobile.png |
| PRJ | 리뷰 회귀 2개 (수정 전) | 실패 확인 (RED) | 중요 3건 모두 재현: 선택/이동 활성, 성공 후 오류 토스트 잔류, 비활성화 실패 대상 결과 부재 |
| PRJ | 리뷰 수정 후 16개 E2E 1차 | 15 통과, 1 실패 | 새 배정 8개 전부 통과. 기존 권한 테스트의 순간 상태 확인 실패; PUT 200과 이후 해제 상태 확인, 코드 변경 없이 재검증 |
| PRJ | 리뷰 수정 후 16개 E2E 재실행 | 16 통과 | 코드 변경 없이 격리 환경 재실행, exit 0. 앞서 실패한 기존 권한 테스트도 통과. 테스트 전용 컨테이너·볼륨·이미지 정리 완료 |
| PRJ/frontend | npm run build (최종) | 통과 | exit 0; TypeScript/Vite build 완료 |
| 저장소 루트 | git diff --check, sh -n PRJ/scripts/e2e.sh, 변경 안내·기록의 로컬 링크 확인 | 통과 | 공백 오류·셸 문법 오류·깨진 로컬 링크 없음 |

## 결과·인계

- 완료 내용: 연결 설정에 게시 후 유저 배정·변경 저장·취소·부분 실패 복구를 구현했다. 기존 API·DB·별도 배정 화면은 유지했다. 독립 리뷰의 중요 3건은 RED→GREEN으로 수정하고 최종 16개 E2E·빌드를 통과했다. feat/source-user-assignments 브랜치의 작업 트리에 변경을 남겼으며 커밋·푸시·배포는 실행하지 않았다.
- 미확인·남은 작업: 운영 Supabase 인증과 실제 모델 호출은 미검증이다. 개발 StrictMode의 중복 최초 조회 경합은 Minor 후속 항목으로 남긴다. 기존 권한 테스트의 순간 상태 경합은 재실행에서 통과했으며 이번 작업에서는 해당 소스·테스트를 변경하지 않았다.
- 단계별 인계: 조사 — 기존 배정 계약·UI 분리 확인; 구현 — SourceAssignments와 설정 연결·문서 반영; 검증 — 기능 부재 및 리뷰 3건 재현, 수정 후 격리 16개 통과. 개발 환경에서는 위 LD_LIBRARY_PATH 전제가 필요하며 운영 설정은 변경하지 않았다.
- 다른 에이전트 기록·정제한 로그 링크: [독립 코드 리뷰](agents/review.md).
