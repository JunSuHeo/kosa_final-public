# 프런트엔드 개발 안내

기준일: 2026-11-17, 현재 소스의 정적 확인 기준. 먼저 [project.md](project.md)를 읽는다. 경로는 `PRJ/` 기준이다.

## 구성과 진입점

React 19, TypeScript, Vite 6, React Flow(`@xyflow/react`), `lucide-react`를 사용한다. 정확한 의존성은 `frontend/package.json` / `package-lock.json`이 기준이다.

| 소스 | 책임 |
| --- | --- |
| `frontend/src/main.tsx` | 전역·React Flow CSS 로드, StrictMode로 App 마운트 |
| `frontend/src/App.tsx` | 홈·로그인·프로젝트 선택, polling, 탭, 편집 draft, proposal/확정본/과거 버전 전환 |
| `frontend/src/api.ts` | 공통 JSON 요청, Bearer 토큰, `ApiError`, 다운로드 |
| `frontend/src/types.ts` | Snapshot·Project·Job·Proposal·RoleReport·소스 분석 타입 |
| `frontend/src/Chat.tsx` | 확인 질문, 생성 진행 상태, 수정 요청 |
| `frontend/src/Documents.tsx` | PRD, 기능명세, React Flow Canvas, Inspector |
| `frontend/src/Wireframes.tsx` | 화면 목록·단일 화면·블록 편집, `WirePage` 미리보기 |
| `frontend/src/Review.tsx` | diff·경고, 수정안 승인·거절, 역할 검토 연결 |
| `frontend/src/RoleReview.tsx` | 다섯 역할별 근거·지적·재시도, 결과 polling |
| `frontend/src/Sources.tsx` | `SourcePicker`, `CodePreview`, `Evidence`, `ImplementationDocument` |
| `frontend/src/styles.css` | 공통 스타일과 반응형 레이아웃 |

별도 전역 상태 라이브러리나 라우터 없이 hooks와 History API를 사용한다. 프로젝트 주소는 `/?project=<id>`다. 비동기 처리를 바꿀 때 프로젝트 전환·언마운트 후 늦게 도착한 응답이 현재 화면을 덮어쓰지 않는지 확인한다.

관리자 홈의 업무 연결 설정은 왼쪽 햄버거 메뉴에서 연다. 관리자 내비게이션이 있는 경우 오른쪽 위의 중복 바로가기는 표시하지 않는다. 관리자 내비게이션 없이 업무 관리·배정 권한을 받은 사용자는 홈의 바로가기를 사용한다.

브라우저 앱은 ID 로그인을 사용한다. `accounts/server.ts`가 서버 계정 API와 탭 세션·토큰 갱신을 처리하며 `accounts/index.ts`는 서버 구현만 제공한다. 브라우저 계정·정책·비밀번호 검증 구현은 제거했다. 실제 권한 검증은 API 서버가 수행한다. 실제 계정 전환의 검증 상태는 [전환 인계](../docs/supabase-transition.md)를 확인한다.

## 실제 코드 사용 예시

`App.tsx:create`의 호출 형태다. `api()`는 body가 있으면 기본 POST, 없으면 GET이며 인증 흐름에서 설정한 토큰을 붙인다.

```tsx
import { api } from "./api";
import type { Project } from "./types";

const project = await api<Project>("/api/projects", {
  id: crypto.randomUUID(),
  idea: "작은 팀의 일정 관리 서비스",
});
// 이후 project.id의 상세 응답에서 job / proposal / revision을 표시한다.
```

이 호출은 데이터와 생성 job을 만든다. 재현은 격리 mock 환경에서 한다. 동일 요청 재시도는 같은 ID를 재사용해야 서버의 멱등성 계약을 활용할 수 있다.

`App.tsx:update`는 편집 snapshot을 `structuredClone`한 뒤 콜백으로 바꾼다. 아래 예시는 편집 draft가 열린 상태를 전제로 한다.

```tsx
update((snapshot) => {
  snapshot.prd.title = "팀 일정 관리 서비스";
});
```

`수정안 검토`는 서버에 proposal을 만든다. UI 편집만으로 확정 revision·current_version을 갱신하지 않는다.

`WirePage`는 JSON 화면을 표시한다. 아래 `screen`은 `Screen` 타입이며 상태 갱신 함수는 호출자가 제공한다.

```tsx
<WirePage
  screen={screen}
  interactive
  onNavigate={(screenId) => setCurrentScreenId(screenId)}
/>
```

연결된 `target_screen_id`로 이동하는 미리보기다. AI HTML·JavaScript·CSS를 실행하는 방식으로 확장하지 않는다.

## 변경 시 확인할 계약

- 표시 우선순위는 편집 draft → 과거 revision → 선택된 proposal → 현재 revision이다. 확정본과 검토 중인 수정안을 구분한다.
- 서버 로그인 응답 토큰·만료 시각은 `hplan-supabase-session.v1`, API 토큰은 `studio-token`에 보관한다. 초기화 시 과거 목업 계정·세션과 `local:` 토큰을 제거한다. 계정·역할 정책·감사 이력은 브라우저에 저장하지 않는다.
- 401에서 인증 초기화, 404/409 오류 표시·새 상태 조회, 프로젝트 전환 중 응답 취소를 확인한다.
- snapshot 변경은 서버 schema·검증·프롬프트·문서와 `types.ts`를 함께 검토한다.
- 역할 검토는 proposal ID 또는 확정 버전에 연결한다. 다른 대상의 결과를 재사용하지 않는다.
- 서버 키·DB 비밀·GitHub 토큰을 UI·`VITE_*`·로그에 넣지 않는다.

## 실행과 검증

다음은 `PRJ/frontend/`에서 실행한다. DB·API·worker는 별도로 필요하다.

```sh
npm ci
npm run dev
npm run build
```

개발 서버는 `127.0.0.1:5174`, `/api`·`/health` 프록시는 `127.0.0.1:8010`이다. Compose web도 기본 5174이므로 동시 실행 때 포트를 조정한다.

UI 동작 검증은 `PRJ/`에서 `sh scripts/e2e.sh`를 실행한다. 세부 전제는 [infra.md](infra.md)를 따른다. 스크립트는 테스트 환경을 기동하고 자동 할당된 주소를 Playwright에 전달한다. DB 계정 E2E는 `server-fixture.ts`로 각 테스트의 격리 DB/Auth를 초기화하고 실제 API 로그인을 사용한다. `E2E_BASE_URL`과 `E2E_AUTH_URL`은 실행 스크립트가 제공한다. 테스트 전용 Auth의 초기화 API를 실제 환경에 노출하지 않는다.

| 테스트 | 용도 |
| --- | --- |
| `frontend/tests/studio.spec.ts` | 생성·승인·직접 편집·복원·내보내기 |
| `frontend/tests/source-planning.spec.ts` | 저장소 기준 선택·변경 기획 |
| `frontend/tests/live-review.spec.ts`, `live-preview.spec.ts` | 실제 호출 결과가 있는 대상 검사. 파일별 전제 확인 |
| `frontend/tests/luna-usability.spec.ts` | 지정한 기존 프로젝트의 데스크톱·모바일 관찰 |

실제 Supabase 검사와 격리 Auth/mock AI E2E를 구분한다. 기존 통과 기록을 이번 변경의 결과로 보고하지 않는다. UI 구조·사용 흐름 변경은 이 문서와 관련 테스트에 반영한다.
