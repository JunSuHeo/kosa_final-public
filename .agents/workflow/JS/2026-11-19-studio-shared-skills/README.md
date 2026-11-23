# Studio 팀 공용 스킬 4종 추가

담당 팀원은 JS다. 변경 범위에 맞는 PR 검증과 UI·PostgreSQL·브라우저 조사에 사용할 공용 스킬을 준비한다.

## 계획

1. 팀 PR에서 반복할 검증 조건을 기존 명령과 제품 계약에 연결한다.
2. 공식 배포처의 파일과 출처·라이선스를 확인하고 저장소 공용 경로에 둔다.
3. 루트 목록, 참조 경로와 명령을 확인하고 작업 기록을 남긴다.

## 출처와 적용

| 스킬 | 가져온 기준 | 이 저장소에서의 적용 |
| --- | --- | --- |
| `studio-pr-check` | 기존 Makefile, 계약 검사, 제품 지침과 PR 양식 | 변경 범위에 맞는 검증과 결과 보고를 안내한다. |
| `web-design-guidelines` | [Vercel 원본과 라이선스 안내](https://github.com/vercel-labs/agent-skills/tree/1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62) | 원본을 가져왔다. 사용 시 안내에 따라 최신 UI 가이드 문서를 조회한다. |
| `supabase-postgres-best-practices` | [Supabase 원본](https://github.com/supabase/agent-skills/tree/c9be0e931b7930f7d02126d04774d904c381e7d7) | 공식 참조 자료와 저장소 MIT 라이선스를 포함했다. |
| `playwright` | [OpenAI 원본](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/playwright) | 안내서의 래퍼 경로를 팀 저장소 기준으로 변경했다. 래퍼 스크립트는 원본을 사용한다. |

## 검증

- 루트 목록과 실제 스킬 21개의 경로·이름·설명 및 팀 전용 스킬의 상대 링크를 확인했다.
- [추가 전 검토](baseline.md)와 [추가 후 검토](review.md)에서 같은 세 가지 가상 PR을 점검했다. 추가 후에는 명시된 계약 명령과 미실행 보고를 일관되게 선택했다.
- 팀 전용 스킬에 적힌 계약 검사는 저장 계약 3종과 예시 2종을 실제로 검증했다. `make -n test e2e`로 두 대상의 명령을 확인했다.
- Playwright 래퍼의 문법과 `--help` 실행을 확인했다. 브라우저 자동화는 실행하지 않았다.
- Vercel 가이드 URL 응답과 Supabase 참조 파일을 확인했다. 실제 UI 리뷰와 DB 변경은 수행하지 않았다.
