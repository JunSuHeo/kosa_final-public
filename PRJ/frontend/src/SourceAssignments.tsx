import { useCallback, useEffect, useRef, useState } from "react";
import { accountService, type Account } from "./accounts";
import { api, ApiError } from "./api";

type Candidate = Pick<Account, "id" | "loginId" | "name" | "active">;
type Changes = Record<string, boolean>;
type Attempt = { changes: Changes; errors: Record<string, string> };

export default function SourceAssignments({
  sourceId,
  sourceName,
  published,
  currentAccountId,
  onSavingChange,
  onError,
}: {
  sourceId: string;
  sourceName: string;
  published: boolean;
  currentAccountId: string;
  onSavingChange: (saving: boolean) => void;
  onError: (error: unknown) => void;
}) {
  const [accounts, setAccounts] = useState<Candidate[]>([]);
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [changes, setChanges] = useState<Changes>({});
  const [results, setResults] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState("");
  const active = useRef(false);
  const saving = useRef(false);
  const pending = useRef<Attempt | null>(null);
  const knownAccounts = useRef<Record<string, Candidate>>({});
  const endpoint = `/api/sources/${sourceId}/assignments`;

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [users, assigned] = await Promise.all([
        accountService.assignmentAccounts(),
        api<{ account_id: string }[]>(endpoint),
      ]);
      if (!active.current) return;
      const actual = new Set(assigned.map((item) => item.account_id));
      for (const user of users) knownAccounts.current[user.id] = user;
      setAccounts(users.filter((user) => user.active && user.id !== currentAccountId));
      setSaved(actual);
      if (pending.current) {
        const attempt = pending.current;
        const remaining: Changes = {};
        const outcomes: Record<string, string> = {};
        for (const [id, enabled] of Object.entries(attempt.changes)) {
          if (actual.has(id) === enabled) {
            outcomes[id] = enabled ? "배정 완료" : "해제 완료";
            await accountService.recordAssignment(users.find((user) => user.id === id)?.loginId || id, sourceName, enabled);
          } else {
            remaining[id] = enabled;
            outcomes[id] = `저장 실패: ${attempt.errors[id] || "서버 반영을 확인하지 못했습니다."}`;
          }
        }
        setChanges(remaining);
        setResults(outcomes);
        setNotice(Object.keys(remaining).length
          ? "일부 배정을 저장하지 못했습니다. 실패 항목을 다시 저장해 주세요."
          : "업무 배정을 저장했습니다.");
        pending.current = null;
      } else {
        setChanges({});
      }
      setUncertain(false);
    } catch (error) {
      if (!active.current) return;
      setLoadError(error instanceof Error ? error.message : "업무 배정을 불러오지 못했습니다.");
      if (pending.current) {
        setUncertain(true);
        setNotice("저장 결과 확인 필요: 배정을 다시 조회해 주세요.");
      }
      if (error instanceof ApiError && [401, 403].includes(error.status)) onError(error);
    } finally {
      if (active.current) setLoading(false);
    }
  }, [endpoint, sourceName, currentAccountId, onError]);

  useEffect(() => {
    active.current = true;
    if (published) void load();
    return () => { active.current = false; };
  }, [published, load]);

  async function save() {
    if (saving.current || loading || loadError || uncertain || !Object.keys(changes).length) return;
    saving.current = true;
    onSavingChange(true);
    setWorking(true);
    setNotice("");
    setResults({});
    const attempt: Attempt = { changes: { ...changes }, errors: {} };
    pending.current = attempt;
    try {
      for (const [id, enabled] of Object.entries(attempt.changes)) {
        if (!active.current) return;
        try {
          await api(`${endpoint}/${encodeURIComponent(id)}`, undefined, enabled ? "PUT" : "DELETE");
        } catch (error) {
          if (!active.current) return;
          attempt.errors[id] = error instanceof Error ? error.message : "배정을 저장하지 못했습니다.";
          if (error instanceof ApiError && [401, 403].includes(error.status)) {
            onError(error);
            break;
          }
        }
      }
      if (active.current) {
        await load();
      }
    } finally {
      saving.current = false;
      onSavingChange(false);
      if (active.current) setWorking(false);
    }
  }

  const count = Object.keys(changes).length;
  const disabled = loading || working || !!loadError || uncertain;
  const unavailable = Object.keys(changes).filter((id) => !accounts.some((account) => account.id === id));
  return (
    <section className="settings-section source-assignments" aria-label="유저 배정">
      <h2>유저 배정</h2>
      {!published ? (
        <p>업무를 게시한 뒤 유저를 배정할 수 있습니다.</p>
      ) : (
        <>
          <p>이 업무를 사용할 유저를 선택하고 배정 저장을 눌러 주세요. 연결은 현재 소유자에게 유지됩니다.</p>
          <p>업무를 전환하면 저장 전 선택은 초기화됩니다. 배정을 해제해도 기존 문서와 확인본은 유지됩니다.</p>
          {loading && <p>업무 배정을 불러오는 중…</p>}
          {notice && <p role="status">{notice}</p>}
          {loadError && (
            <div>
              <p>{loadError}</p>
              <button className="secondary" disabled={loading || working} onClick={() => void load()}>
                배정 다시 조회
              </button>
            </div>
          )}
          {!loading && !loadError && !accounts.length && <p>배정할 활성 유저가 없습니다.</p>}
          {accounts.map((account) => (
            <label className="assignment-row" key={account.id}>
              <input
                type="checkbox"
                aria-label={`${account.loginId} 업무 배정`}
                disabled={disabled}
                checked={changes[account.id] ?? saved.has(account.id)}
                onChange={(event) => {
                  const enabled = event.target.checked;
                  setChanges((current) => {
                    const next = { ...current };
                    if (saved.has(account.id) === enabled) delete next[account.id];
                    else next[account.id] = enabled;
                    return next;
                  });
                  setNotice("");
                  setResults({});
                }}
              />
              <span>
                <strong>{account.loginId} · {account.name}</strong>
                {results[account.id] && <small>{results[account.id]}</small>}
              </span>
            </label>
          ))}
          {unavailable.map((id) => (
            <div className="access-notice" role="group" aria-label={`${knownAccounts.current[id]?.loginId || id} 배정 실패`} key={id}>
              <strong>{knownAccounts.current[id]?.loginId || id} · {knownAccounts.current[id]?.name || "계정"}</strong>
              <p>{results[id]}</p>
              <p>현재 사용할 수 없는 계정입니다. 계정 상태를 확인하거나 선택을 취소해 주세요.</p>
              <button className="secondary" disabled={disabled} onClick={() => {
                setChanges((current) => {
                  const next = { ...current };
                  delete next[id];
                  return next;
                });
                setNotice("");
              }}>
                선택 취소
              </button>
            </div>
          ))}
          <p>변경 {count}건</p>
          <div className="publication-actions">
            <button className="primary" disabled={disabled || !count} onClick={() => void save()}>
              {working ? "배정 저장 중…" : "배정 저장"}
            </button>
            <button className="secondary" disabled={disabled || !count} onClick={() => {
              setChanges({});
              setResults({});
              setNotice("");
            }}>
              변경 취소
            </button>
          </div>
        </>
      )}
    </section>
  );
}
