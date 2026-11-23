# 현업 대화 화면 구현

- 담당: journey / SY
- 목표: 한 번의 업무 선택으로 대화 시작, 탭 내 입력 복원, 미전송 생성 방지, 한글 조합 보호, 업무 변경 비교.
- 소유 파일: BusinessHome.tsx, Chat.tsx, Review.tsx, hplan.css, business E2E tests/helpers. App.tsx·drafts.ts·types.ts는 root 담당.
- 완료 조건: 새 상호작용 회귀 테스트와 기존 흐름의 격리 mock E2E 통과, 빌드 통과.
- 계획: 테스트 RED → 최소 화면 변경 → 통합 GREEN → 기록.
- 적용 스킬: TDD, web-design-guidelines(최신 가이드 확인), Playwright 검증.
- 검증 상태: 격리 DB/Auth/mock AI RED 실행 중. 실제 서비스·실제 모델 사용 없음.

## 조사와 구현 인계

- 기존 홈은 업무 선택 뒤 유형·시작 버튼을 요구했고, Chat 입력·질문 선택은 메모리 상태라 새로고침 때 사라졌다.
- BusinessHome: 업무 카드에서 기본 improve로 intake 진입. 유형은 intake 선택 사항, 첫 설명과 함께 계정·업무별 탭 초안 저장. 내 기획 업무 필터와 초기화를 별도 제공. progress_status별 진행·다음 행동 안내.
- Chat: 계정·프로젝트별 입력, job·question별 답변 임시 저장. 한글 조합 Enter 전송 방지. 미전송 입력·질문 선택이 있으면 생성 비활성화와 전송 안내. 현재 질문은 최신 메시지의 일치하는 질문 suffix만 화면에서 제거해 카드에 한 번 표시하며 과거 원문 이력은 보존. 미정 선택 추가.
- Review: 서버 diff에서 바뀐 업무 필드만 결정적으로 추출해 이전/이번 내용을 표시. 별도 모델 호출 없음. 기술 식별자는 기본 비교에서 제외.
- App 통합 계약: Chat draftScope=`accountId:projectId`, input key=tabDraftKey(scope,"chat","input"); onUnsentChange callback. Intake draftOwner=accountId, onCreate/onAnswer Promise<boolean>. 성공 true에서만 입력을 비운다.
- 기존 E2E: 1클릭 업무 진입·산출물 전 대화 집중·파일 내보내기 이름을 반영. 정책 테스트는 게시 업무 배정 후 카드 비활성화를 확인한다.

## 검증 근거

- RED 실행: `LD_LIBRARY_PATH=/tmp/kosa-push-browser-libs/extracted/usr/lib/x86_64-linux-gnu sh scripts/e2e.sh tests/business-journey.spec.ts` (PRJ, 격리 DB/Auth/mock AI).
- 4개 모두 기대한 기능 부재로 실패: 업무 한 번 선택 뒤 설명 입력 없음, 미전송 대화에도 생성 활성, 질문 직접 답변 새로고침 후 소실, 수정 비교에 이전/이번 내용 없음.
- RED 증거: Git 제외 `PRJ/.research/e2e.HkPVrfBs`의 Playwright screenshot/trace. 종료 시 disposable Compose 컨테이너·볼륨 삭제 확인.
- `npm run build` 실제 통과: 1762 modules transformed. 기존 대용량 번들 알림 외 오류 없음.
- `git diff --check` 실제 통과.
- GREEN 전체 E2E: root 통합 실행 대기. 중복 green 실행은 npm 단계에서 취소했고 컨테이너 시작 전 종료했다.
- live 모델·실제 Supabase·실제 서비스 DB 검증은 수행하지 않았다.

## 남은 작업

root의 전체 격리 E2E 결과 확인 후 발생 회귀 수정 및 최종 GREEN 기록. 문서 변경은 root 통합 담당.

## 독립 리뷰 후 수정 (Task 3·4)

root가 `review-journey.md`의 발견 사항과 App.tsx 수정 소유권을 이관했다.

- pending 초안이 있는 확인본 직접 편집을 비활성화하고 작성 중 초안 선택 안내를 표시한다. startEditing 내부에서도 같은 조건을 검사한다.
- 산출물 단계는 현재 표시 snapshot이 아니라 저장된 proposal·revision의 산출물 유무로 판단한다. 빈 revision 0을 표시해도 보관된 초안 검토 도구를 유지한다.
- 프로젝트 생성 ID와 정확한 payload를 계정·업무 intake 임시 저장 안에 보관한다. 응답 유실·새로고침 재시도는 같은 ID를 쓰고 payload가 달라지면 새 ID를 만든다.
- discuss·generate/revise·repair 작업도 계정·프로젝트·작업 종류별 ID와 정확한 payload를 성공까지 보관한다. 서버가 POST를 수락한 뒤 부가 GET이 실패해도 해당 작업을 실패로 반환하지 않는다. 답변·대화·생성 POST의 Job 응답을 현재 컨텍스트에 즉시 반영해 질문 재제출을 막고 polling을 유지한다.
- 생성 후 이동은 같은 계정·업무의 intake가 여전히 열려 있을 때만 한다. 직접 편집 저장 후에는 이전 프로젝트 임시 저장만 지우고, 계정·프로젝트가 달라졌으면 현재 편집·탭·검토 화면을 변경하지 않는다.
- 생성 진입점은 Chat 마운트 여부와 관계없이 현재 job의 저장된 질문 선택·직접 답변도 확인한다.
- popstate에서 대화 패널·모바일 대화·열림 상태를 초기화한다. 기존 진입 효과가 pending·질문·실패 상태에 맞는 화면을 재개한다.
- 사용되지 않던 journey.css의 `--side-width` 선언을 제거했다. 별도 레이아웃 설정은 추가하지 않았다.

### 추가 검증

- `app-journey-regressions.spec.ts` 10개 신규 회귀: 확인본 편집 보호, 빈 확인본 검토 도구, 생성 응답 유실 ID, 생성 후 목록 실패, 대화 후 조회 실패, A 저장 중 B 편집 보존, 재진입 질문 생성 차단, popstate 질문 재개, 답변 수락 후 재제출 방지, 생성 작업 응답 유실 ID.
- 기대한 RED 9개 확인: 첫 실행의 2개 + 후속 실행의 5개 + 답변/생성 작업 2개. popstate 사례는 초기화 수정 뒤 실행되어 RED 증거 없이 회귀 GREEN으로 남겼다.
- 제한된 sandbox의 최초 Chromium 실행 오류와 최초 테스트의 숨은 모바일 내비게이션 selector 오류는 기능 RED로 계산하지 않았다. escalation 브라우저 실행과 데스크톱 selector 교정 후 실제 기능 실패를 확인했다.
- 최신 코드 focused browser: `E2E_BASE_URL=http://127.0.0.1:5197 ... playwright test ... tests/app-journey-regressions.spec.ts tests/app-drafts.spec.ts --output=/tmp/kosa-journey-fix-green2` **12 passed (37.1s)**. 실제 브라우저·mock API 경계, DB 미사용.
- 격리 DB/Auth/mock AI replay: workflow-review·business-journey·app-drafts·당시 신규 회귀 **17 passed (1.4m)**. 이전 workflow-review:17 실패도 통과했다. 다만 실행 중 root의 e2e.sh 기본 목록 편집으로 shell read offset이 바뀌어 테스트 종료 후 `scripts/e2e.sh:71:c.ts:not found`, 명령 exit 127이었다. 컨테이너·볼륨·이미지 cleanup은 완료됐고 증거는 `PRJ/.research/e2e.eB2w911c`에 남았다. 따라서 이 명령 전체를 GREEN으로 보고하지 않는다. root의 편집 없는 최종 전체 재실행이 필요하다.
- 위 replay 이미지 이후 추가된 답변 Job 즉시 반영·생성 작업 ID 보관은 최신 focused 12개와 frontend build로 확인했다. 최종 전체 E2E는 root 담당.
- 최신 `npm run build`: **통과**, 1762 modules. 최신 `git diff --check`: **통과**.
- 새 외부 API·DB 계약·패키지 변경 없음. 실제 서비스·실제 모델·실제 Supabase 사용 없음.

## 마지막 지연 응답 검토 수정

- Chat 성공 후 입력 정리는 React state updater 실행에만 의존하지 않도록 요청 당시 chat key와 원문을 캡처한다. 실제 저장된 문자열이 보낸 원문과 일치할 때 직접 제거한다. 저장된 새 입력이 있으면 이전 메모리 setter도 실행하지 않아 새 내용을 보존한다. drafts.ts 구조는 변경하지 않았다.
- root가 추가 승인한 동일 패턴: approve/reject 성공 후 UI 변경 전에 요청 당시 계정·프로젝트와 현재 컨텍스트를 비교한다. A의 늦은 승인 응답이 B에서 복원한 편집을 닫지 않는다.
- 지연 승인 회귀는 RED에서 B의 편집 버튼·입력이 사라지는 실제 실패를 확인한 뒤 수정했다 (`/tmp/kosa-journey-decision-red`).
- 지연 전송 후 홈 이동·새 입력 보존 두 사례는 수정 전에도 브라우저에서 통과했다. 홈 화면 언마운트와 저장된 문자열을 명시적으로 확인한 재실행에서도 통과했으므로 이 정적 검토 발견에 대한 RED 재현으로 보고하지 않는다. 요청된 직접 저장 정리 방식은 적용하고 회귀 검증을 유지했다.
- 최신 focused 실행: app-drafts 2개 + app-journey-regressions 13개 = **15 passed (52.7s)**, 실제 브라우저·mock API, `/tmp/kosa-journey-round2-green`.
- `npm run build` **통과**, 1762 modules, index-C7xPmNGU.js. `git diff --check` **통과**.
- root의 실행 중 E2E 스크립트나 서비스 설정은 수정하지 않았다. 최신 Chat·decide 변경의 production 정적 빌드 브라우저 재실행은 root 담당.
- 전송 종료까지 기다리는 최신 추가 assertion 재검증: 지연 전송 두 사례 **2 passed (4.7s)**, `/tmp/kosa-journey-round2-settled-green`.

## 실패 작업 재시도 경로 최종 수정

- 전체 변경 독립 검토가 발견한 기존 inline retry 경로도 동일한 멱등·전송 수락 규칙을 적용했다. account/project/원래 job ID별로 재시도 ID와 정확한 payload를 보관하고 응답 유실·새로고침 뒤 재사용한다. 성공 시 보관 키를 제거하고 반환된 Job을 현재 프로젝트에 즉시 반영한다. 부가 refresh 실패는 수락된 POST 실패로 취급하지 않는다. 늦은 응답에는 계정·프로젝트 가드를 적용한다.
- writeDraft의 기존 입력 검사만 `blockUnsentInput`으로 추출해 생성·복구·실패 재시도가 공유한다. 모든 종류의 재시도에서 새 입력을 먼저 보내도록 한다. Chat 재시도 버튼은 미전송 입력이 있으면 비활성화하며 기존 전송 안내를 유지한다. 저장된 현재 질문 초안도 React state와 독립적으로 차단한다.
- 신규 4개 RED 실제 확인: 응답 유실 재시도 UUID 변경, POST 수락 후 GET 503에서 재시도 버튼 유지, 미전송 입력에도 재시도 활성, 저장된 질문 초안의 재시도 우회. 증거 `/tmp/kosa-journey-retry-red`.
- 최신 focused 브라우저: app-drafts 2개 + app-journey-regressions 17개 = **19 passed (44.9s)**, `/tmp/kosa-journey-retry-green`. 실제 브라우저·mock API 경계, DB·외부 모델 미사용.
- 최신 `npm run build` **통과**, 1762 modules, index-B_JaPMOG.js. `git diff --check` **통과**.
- 이번 추가 범위는 App.tsx, Chat.tsx, app-journey-regressions.spec.ts와 작업 기록이다. e2e.sh·실행 설정·서비스는 수정하지 않았다. 제품 파일 소유권을 root에 반환하며 최종 production E2E와 독립 재검토는 root 담당이다.
