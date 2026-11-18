# 매니패스트 조사와 독립 구현

조사일: 2026-10-15 (Asia/Seoul). 대상: https://manyfast.io/ 와 사용자가 이미 로그인한 실제 편집기. 사용자가 REA 기반 전체 재구축과 와이어프레임 포함을 선택했다.

## 직접 관찰

Chrome의 로그인된 프로젝트에서 읽기 위주로 탭과 패널을 전환했다. 기존 기획 내용·답변·댓글을 수정하지 않았고 새 생성/재생성이나 유료 동작을 실행하지 않았다.

| 영역 | 확인한 UI와 동작 | 새 구현에 적용한 내용 |
|---|---|---|
| 작업 공간 | 왼쪽 도구 레일, 채팅 패널, 오른쪽 산출물, 상단 문서 탭 | 채팅/검토/문서/버전 레일과 네 산출물 탭 |
| 질문 | 선택지·직접 입력·다음/이전·AI가 알아서 진행 | 최대 3개 질문과 답변 저장/재개 |
| PRD | 섹션별 본문 편집, 완성도, 사용자 역할/기기 속성 | 구조화된 PRD 필드, 속성, 직접 편집 proposal |
| 기능명세 | 그래프/디렉토리/도큐먼트 전환, 선택 항목 상세·수용 기준 | 요구사항→기능 그래프, 검색, 세 가지 보기, 상세 |
| 유저플로우 | 시작·페이지·분기·행동과 간선, 섹션별 캔버스 | 검증된 JSON 노드/간선의 확대·이동·상세·위치 편집 |
| 와이어프레임 | 전체/단일 보기, 이전/다음, 확대/축소, 재생성/직접 편집 진입 | 전체/단일, 요소 편집/정렬, 기기 변경, 연결 미리보기 |
| 검토 | 개발 관점의 주의/심각 항목, 근거·관련 항목, 채팅에서 해결 | 이번 구현은 구조적 검사와 proposal diff/승인에 한정 |

화면 관찰만으로 저장 방식이나 서버 트랜잭션을 확인할 수는 없다. 관찰한 메뉴 중 커넥터·공동편집·결제·문서 업로드 등은 이번 구현에서 제외했다.

## REA 실행 증거

공식 npm 패키지 `rea-agents@6.5.0`을 CLI로 실행했다. 별도 네이티브 디컴파일러나 사용자 브라우저의 디버깅 설정 변경 없이, 공개 응답의 JS 파일만 정적으로 분석했다.

1. 실제 편집기 URL의 공개 HTML에 선언된 엔트리 JS를 수집했다.
2. 엔트리에서 참조하는 EditorLayout, WireframeViewer, EditorSocketManager와 editor vendor 파일을 제한적으로 수집했다. 쿠키·브라우저 토큰·개인 저장소를 추출하지 않았다.
3. 엔트리 분석: 파싱 실패 0, JS 1개, AST 노드 10,885개, 정적 finding 487개.
4. 편집기 분석: 선택 JS 3개, AST 노드 76,298개, 정적 finding 520개, 파싱 실패 0. 미수집 import와 실행 여부는 미확인으로 남는다.

원본 파일과 전체 Evidence JSON은 Git 제외 경로 `.research/manyfast/`에 로컬 보관한다. 해시·Evidence ID·제한은 요약 JSON(`rea-evidence-summary.json`)에 기록했다. 대상 JS는 앱 코드나 빌드 산출물에 포함하지 않았다.

```sh
npx -y rea-agents@6.5.0 analyze-javascript-application .research/manyfast/public-artifacts --format json
npx -y rea-agents@6.5.0 analyze-javascript-application .research/manyfast/public-artifacts \
  --source-path EditorLayout-Hwn62PSN.js \
  --source-path WireframeViewer-DDKx4m4B.js \
  --source-path EditorSocketManager-C0x2lSKN.js \
  --max-semantic-nodes 15000 --max-semantic-nodes-per-file 5000 \
  --analysis-timeout-ms 30000 --format json
```

배포된 파일명은 이후 바뀔 수 있다. 재조사 시 provenance에 새 URL과 해시를 남겨야 한다.

## 독립적으로 설계한 부분

PostgreSQL 스키마, 인증, 질문 상태 머신, 모델 프롬프트, proposal/승인 트랜잭션, React 컴포넌트, 제한된 와이어프레임 JSON schema는 우리 요구사항을 기준으로 새로 작성했다. 매니패스트의 원본과 같은 구현이라는 의미는 아니다.

특히 와이어프레임 내부 구현 방식은 복원하지 않았다. 새 서비스는 허용된 8개 block 타입만 React로 표시하고 AI가 만든 HTML·JS·CSS를 실행하지 않는다. REA의 정적 결과는 런타임 실행이나 실제 API 동작을 증명하지 않는다.

참고: [REA](https://github.com/morluto/rea), [REA 웹 관찰 가이드](https://github.com/morluto/rea/blob/main/docs/browser-observation.md), [매니패스트](https://manyfast.io/ko/).
