# 재구축 결정 기록

## 2026-10-15: v1 전체 교체

사용자가 기존 구현을 재사용하지 않고 REA로 매니패스트를 분석해 재구축하는 방향을 선택했다. 추가 질문에서 핵심 기능과 와이어프레임을 1차 범위로 확정했다. 기존 소스/문서/설정과 lockfile은 별도 백업했다. 기존 DB volume을 마이그레이션하거나 지우지 않고 새로운 Compose 프로젝트와 PostgreSQL volume을 사용한다.

## 저장과 실행 단순화

새 구현은 PostgreSQL에 job의 단계·partial·질문·답변을 저장한다. LangGraph/checkpoint와 별도 command 테이블을 사용하던 v1을 재사용하지 않는다. job별 advisory lock, 단계별 저장, proposal.job_id UNIQUE로 재처리를 제어한다. 외부 모델 호출은 at-least-once일 수 있음을 명시한다. 이는 매니패스트 내부 설계를 확인한 결과가 아닌 새 구현의 선택이다.

## 와이어프레임

새 snapshot의 screens와 blocks는 흐름 노드/화면을 ID로 참조한다. JSON schema·fixture·migration·서버 검증·브라우저 편집/미리보기를 함께 작성한다. AI 생성 HTML/JS를 실행하는 방식 대신 제한된 컴포넌트를 사용한다.

## 내보내기

지정된 승인 버전만 읽는 계약은 유지한다. v1의 DB export queue/파일 잠금/atomic rename/24시간 파일 만료는 보관 파일을 만들지 않는 즉시 응답으로 대체한다. 프런트엔드는 요청한 버전의 다운로드만 시작하며 늦은 응답으로 화면 버전을 바꾸지 않는다.

## 외부 연동

Supabase 인증과 실제 모델 호출은 독립된 모드다. OpenRouter는 Chat Completions의 json_schema와 require_parameters를 사용한다. OpenAI는 Responses의 text.format json_schema를 사용한다. 실패 시 데모로 전환하지 않는다. 기존 서버 LLM_API_KEY/LLM_MODEL 환경변수는 호환 지원한다.

실제 모델 검증과 mock 테스트 결과, 미검증 Supabase 실계정 연동은 verification.md에 구분한다.


## 2026-10-15: 다섯 역할의 독립 검토

사용자 요청으로 개발자·기획자·보안·UI/UX·QA의 의미 검토를 추가한다. 역할별 프롬프트와 모델 호출은 독립적이며 다른 역할의 결과를 입력으로 사용하지 않는다. 별도 에이전트 프레임워크 대신 기존 구조화 출력 어댑터와 표준 ThreadPoolExecutor(동시 3개)를 사용한다.

검토 버튼을 누른 시점의 저장된 proposal 또는 불변 revision을 복사하고 SHA-256을 고정한다. 동일 대상의 중복 요청은 같은 검토를 반환한다. 역할별 진행·완료 결과·오류·usage를 PostgreSQL에 저장한다. 세션 advisory lock으로 중복 worker 실행을 막고, 재시작 시 미완료 역할만 재개한다. 명시적 재시도는 실패한 역할만 실행하며 완료된 역할은 보존한다. 중단된 외부 호출의 exactly-once는 보장하지 않는다.

각 지적은 원문 ID/인용·문제 설명·수정 제안·검증 기준을 포함한다. 서버가 ID와 연속 인용 문자열을 실제 대상 snapshot과 대조하며 일치하지 않으면 그 역할을 실패 처리한다. 단, 인용의 존재 검증이 지적의 정확성을 보장하지는 않는다. 실제 코드 감사나 사용자 조사 결과로 표현하지 않는다.

AI 심각도는 조언이며 기존 구조 검사의 blocking/warning 및 승인 조건을 변경하지 않는다. 검토는 proposal·revision·current_version을 쓰지 않는다. 수동 수정으로 새 proposal이 생기면 이전 검토를 새 기획의 결과로 재사용하지 않는다. 현재 보고서를 자동 수정에 연결하는 기능은 포함하지 않는다.
