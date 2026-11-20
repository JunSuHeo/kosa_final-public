import { useEffect, useState, type ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { accountService, type Account } from "./accounts";
import { api } from "./api";
import { Brand } from "./BusinessHome";
import type { BusinessSource } from "./types";
export default function AssignmentSettings({
  navigation,
  accountMenu,
  onHome,
  onError,
}: {
  navigation: ReactNode;
  accountMenu: ReactNode;
  onHome: () => void;
  onError: (error: unknown) => void;
}) {
  const [sources, setSources] = useState<BusinessSource[]>([]);
  const [accounts, setAccounts] = useState<
    Pick<Account, "id" | "name" | "loginId" | "active">[]
  >([]);
  const [sourceId, setSourceId] = useState("");
  const [assigned, setAssigned] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([
      api<BusinessSource[]>("/api/sources"),
      accountService.assignmentAccounts(),
    ])
      .then(([all, users]) => {
        if (active) {
          setSources(all.filter((s) => s.can_manage && s.publication_id));
          setAccounts(users);
        }
      })
      .catch(onError);
    return () => {
      active = false;
    };
  }, [onError]);
  useEffect(() => {
    let active = true;
    setLoaded(false);
    setNotice("");
    if (sourceId)
      api<{ account_id: string }[]>(`/api/sources/${sourceId}/assignments`)
        .then((all) => {
          if (active) {
            setAssigned(all.map((a) => a.account_id));
            setLoaded(true);
          }
        })
        .catch(onError);
    return () => {
      active = false;
    };
  }, [sourceId, onError]);
  return (
    <div className="management-page">
      <header className="business-header">
        <div className="header-brand">
          {navigation}
          <Brand />
        </div>
        <div className="business-header-actions">
          <button className="secondary" onClick={onHome}>
            <ArrowLeft size={16} />
            업무 홈
          </button>
          {accountMenu}
        </div>
      </header>
      <main className="management-main">
        <div className="page-heading">
          <span className="eyebrow">업무 연결 준비</span>
          <h1>업무 배정</h1>
          <p>
            본인이 게시한 업무를 계정별로 배정합니다. 배정을 해제해도 기존
            문서와 확인본은 유지됩니다.
          </p>
        </div>
        <section className="management-card account-editor">
          <label>
            배정할 업무
            <select
              aria-label="배정할 업무"
              value={sourceId}
              disabled={busy}
              onChange={(e) => setSourceId(e.target.value)}
            >
              <option value="">업무를 선택해 주세요</option>
              {sources.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          {!sources.length && (
            <p>
              본인이 게시한 업무가 없습니다. 업무 연결 권한이 있는 담당자가 연결
              준비와 게시를 먼저 진행해 주세요.
            </p>
          )}
          {notice && <p role="status">{notice}</p>}
          {loaded &&
            accounts.map((a) => (
              <label className="assignment-row" key={a.id}>
                <input
                  aria-label={`${a.loginId} 업무 배정`}
                  type="checkbox"
                  checked={assigned.includes(a.id)}
                  disabled={busy}
                  onChange={(e) => {
                    const enabled = e.target.checked;
                    const previous = assigned;
                    setAssigned((current) =>
                      enabled
                        ? [...current, a.id]
                        : current.filter((id) => id !== a.id),
                    );
                    setBusy(true);
                    setNotice("");
                    void (async () => {
                      try {
                        await api(
                          `/api/sources/${sourceId}/assignments/${a.id}`,
                          undefined,
                          enabled ? "PUT" : "DELETE",
                        );
                        await accountService.recordAssignment(
                          a.loginId,
                          sources.find((s) => s.id === sourceId)!.name,
                          enabled,
                        );
                        setNotice(
                          `${a.loginId} 계정의 업무 배정을 ${enabled ? "추가" : "해제"}했습니다.`,
                        );
                      } catch (error) {
                        setAssigned(previous);
                        onError(error);
                      } finally {
                        setBusy(false);
                      }
                    })();
                  }}
                />
                <span>
                  <strong>
                    {a.name} · {a.loginId}
                  </strong>
                  <small>{a.active ? "사용 중" : "사용 중지"}</small>
                </span>
              </label>
            ))}
        </section>
      </main>
    </div>
  );
}
