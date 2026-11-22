# 인증 안정화와 현업 기획 흐름 구현 계획

승인 기준: 2026-11-23 대화에서 사용자가 명시적으로 구현을 요청한 계획. 기반 d3ca1a7 (feat/supabase-db-account-management). 실제 서비스 DB·모델 키·기존 서비스는 사용하거나 변경하지 않는다.

## Task 1: Backend authentication and project progress
- Reset keeps existing account active/ready, revokes sessions before each real attempt and after remote success; operation remains resumable after reauthentication; classify uncertain remote writes explicitly, no plaintext persisted. Completed retries do not repeat revocation/audit. Preserve last-admin protections.
- Count failed credentials separately from high-volume IP throttling; successful logins and external service failures do not exhaust failure quota. DB-wide atomic limits, trusted proxy header overwrite + explicitly trusted network, no wildcard trust.
- Preserve Auth429, map JWKS connectivity503, invalid credentials/claims401.
- Audit cursor strings, no hidden200-row cap.
- Project list includes derived progress status (conversation, awaiting_answers, generating, review_ready, failed, confirmed) from existing persisted jobs/proposals; ownership retained, no new source-of-truth table.
- Isolated PostgreSQL regression tests before changes and after; no live DB.

## Task 2: Frontend session and audit
- Retain last confirmed identity and current view on temporary network/429/503; only definitive401 invalidates. Startup without identity offers retry instead of forced credential entry.
- Preserve reset operation IDs through reauthentication, clear only on explicit success/explicit logout as appropriate; support same-id retry.
- AuditPage {items,next:string|null}; load older entries without replacing current, no duplicates; loading/error states and retry.
- UI boundary tests for transient failures vs401 and >200 history.

## Task 3: Business journey components
- Home click opens intake directly; intent optional on intake, default improve. Separate explicit plans source filter/reset from new-plan source.
- Pre-artifact conversation focused layout is integrated by root in App.
- Chat input/question drafts use tab-scoped draft helper. IME Enter cannot send. Unsent text blocks generate and says send first; labels become 기획 초안 만들기/수정안 만들기.
- Current structured dialogue question appears once while durable past transcript remains; allow 미정 answer.
- Review foreground key business before/after and open assumptions; IT review secondary.
- Status cards show derived progress and next action; root handles App resume navigation.
- Adapt existing E2E to one-click source/intake and new labels; add meaningful input/persistence/mobile tests.

## Task 4: App integration, draft persistence, contracts and verification
- Tab-scoped sessionStorage helper namespaces account/project/source/job; explicit logout clears business drafts,401 retains scoped drafts for same-account return. No cross-device draft synchronization.
- Persist first description, unsent chat, question answers and direct-edit snapshot. Match editor draft to base version/proposal before restore; stale draft requires explicit discard/recovery, never autoapply to different base.
- Generate actions all block unsent chat; stage-focused workspace before first artifact; resume review/questions/failure automatically only upon initial entry.
- Truthful save labels (server conversation saved vs local unsent/direct-edit); visible export explanation, approved-version download only, user-facing file labels.
- Update specs/OpenAPI/rules/readme, SY history, isolated backend/build/contracts/E2E; review all changes before reporting.

## Shared interfaces and rulings
- Project.progress_status optional frontend while transitioning, backend derived enum above; no API to mutate it.
- useTabDraft<T>(key:string, initial:T) returns [value,setValue,clear]; tabDraftKey(owner,kind,id), clearTabDrafts(owner?) helper. Root owns frontend/src/drafts.ts.
- Root owns App.tsx and drafts.ts; component task owns BusinessHome.tsx, Chat.tsx, Review.tsx, hplan.css and E2E business tests. Session task owns accounts/*, api.ts, UserManagement.tsx, supabase-accounts.spec.ts. Backend task owns backend/** and proxy/compose settings.
- Root owns public project types, generated contracts and documentation. No other files change without coordination.
- Existing immutable approval, owner scoping, manual draft-generation gate retained. Existing setup/code technical features not expanded.
