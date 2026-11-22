import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, Plus, Search } from "lucide-react";
import {
  accountService,
  can,
  fixedPermissions,
  permissionLabels,
  permissions,
  roles,
  type Account,
  type AuditEntry,
  type Identity,
  type Policy,
  type Role,
} from "./accounts";
import { api, ApiError } from "./api";
import { Brand } from "./BusinessHome";
import type { Source } from "./types";

type Form = {
  loginId: string;
  name: string;
  role: Role;
  active: boolean;
  password: string;
};
const blank: Form = {
  loginId: "",
  name: "",
  role: "USER1",
  active: true,
  password: "",
};
const date = (value: string | null) =>
  value ? new Date(value).toLocaleString("ko-KR") : "기록 없음";
const descriptions: Record<Role, string> = {
  USER1: "담당 업무를 바탕으로 본인의 기획을 작성합니다.",
  USER2: "USER1과 동일한 기본 기획 권한을 갖습니다. 필요 시 별도로 조정합니다.",
  ADMINISTRATOR:
    "계정·권한을 관리하고 본인이 연결한 업무를 배정합니다. 다른 사람의 기획은 열람하지 않습니다.",
};
export default function UserManagement({
  page,
  identity,
  navigation,
  accountMenu,
  onHome,
  onError,
}: {
  page: string;
  identity: Identity;
  navigation: ReactNode;
  accountMenu: ReactNode;
  onHome: () => void;
  onError: (e: unknown) => void;
}) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [history, setHistory] = useState<AuditEntry[]>([]);
  const historyRef = useRef<AuditEntry[]>([]);
  const [auditNext, setAuditNext] = useState<string | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState("");
  const [auditNotice, setAuditNotice] = useState("");
  const auditLoaded = useRef(false);
  const auditLoadingRef = useRef(false);
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<Account | "new" | null>(null);
  const [form, setForm] = useState<Form>(blank);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [assignments, setAssignments] = useState<Record<string, boolean>>({});
  const [assignmentsLoaded, setAssignmentsLoaded] = useState(false);
  const loadAudit = useCallback(async (cursor?: string) => {
    if (auditLoadingRef.current) return;
    auditLoadingRef.current = true;
    setAuditLoading(true);
    setAuditError("");
    try {
      const result = await accountService.audit(cursor);
      const current = historyRef.current;
      const ids = new Set(current.map((entry) => entry.id));
      const reset = !cursor && current.length > 0 && !result.items.some((entry) => ids.has(entry.id));
      const combined = reset ? result.items : cursor ? [...current, ...result.items] : [...result.items, ...current];
      historyRef.current = Array.from(new Map(combined.map((entry) => [entry.id, entry])).values());
      setHistory(historyRef.current);
      if (cursor || !auditLoaded.current || reset) setAuditNext(result.next);
      if (reset) setAuditNotice("새 이력이 많이 추가되어 최신 이력부터 다시 표시합니다. 이전 이력을 이어서 확인해 주세요.");
      auditLoaded.current = true;
    } catch (error) {
      setAuditError(error instanceof Error ? error.message : "이력을 불러오지 못했습니다.");
      if (error instanceof ApiError && error.status === 401) onError(error);
    } finally {
      auditLoadingRef.current = false;
      setAuditLoading(false);
    }
  }, [onError]);
  const refresh = useCallback(async () => {
    if (page === "audit") return loadAudit();
    const p = await accountService.policy();
    setPolicy(p);
    if (page === "accounts") setAccounts(await accountService.accounts());
  }, [page, loadAudit]);
  useEffect(() => {
    void refresh().catch(onError);
    return accountService.subscribe(() => void refresh().catch(() => {}));
  }, [refresh, onError]);
  useEffect(() => {
    let active = true;
    setAssignments({});
    setAssignmentsLoaded(false);
    setSources([]);
    if (!selected || selected === "new" || !can(identity, "sources.assign"))
      return;
    api<Source[]>("/api/sources")
      .then(async (all) => {
        const owned = all.filter((s) => s.can_manage && s.publication_id);
        const values = await Promise.all(
          owned.map(
            async (s) =>
              [
                s.id,
                (
                  await api<{ account_id: string }[]>(
                    `/api/sources/${s.id}/assignments`,
                  )
                ).some((a) => a.account_id === selected.id),
              ] as const,
          ),
        );
        if (active) {
          setSources(owned);
          setAssignments(Object.fromEntries(values));
          setAssignmentsLoaded(true);
        }
      })
      .catch(onError);
    return () => {
      active = false;
    };
  }, [selected, identity.account.id, can(identity, "sources.assign"), onError]);
  const run = async (action: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    setNotice("");
    try {
      await action();
      await refresh();
    } catch (error) {
      onError(error);
    } finally {
      setBusy(false);
    }
  };
  const choose = (account: Account | "new") => {
    setSelected(account);
    setNotice("");
    setForm(
      account === "new"
        ? blank
        : {
            loginId: account.loginId,
            name: account.name,
            role: account.role,
            active: account.active,
            password: "",
          },
    );
  };
  const shown = accounts.filter(
    (a) =>
      `${a.loginId} ${a.name}`.toLowerCase().includes(query.toLowerCase()) &&
      (!roleFilter || a.role === roleFilter) &&
      (!statusFilter || String(a.active) === statusFilter),
  );
  const title =
    page === "permissions"
      ? "역할·권한 설정"
      : page === "audit"
        ? "변경 이력"
        : "계정 관리";
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
          <span className="eyebrow">사용자 관리</span>
          <h1>{title}</h1>
          <p>
            {page === "accounts"
              ? "계정별 역할과 사용 상태, 기획할 업무를 관리하세요."
              : page === "permissions"
                ? "모든 기획 권한은 본인 소유의 기획에만 적용됩니다."
                : "계정·권한 변경과 로그인 기록을 확인하세요."}
          </p>
        </div>
        {notice && (
          <div role="status" className="management-notice">
            {notice}
          </div>
        )}
        {page === "accounts" ? (
          <>
            <div className="management-toolbar">
              <label className="search-field">
                <Search size={16} />
                <input
                  aria-label="계정 검색"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="ID 또는 이름 검색"
                />
              </label>
              <select
                aria-label="역할 필터"
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value)}
              >
                <option value="">모든 역할</option>
                {roles.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
              <select
                aria-label="사용 상태 필터"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="">모든 상태</option>
                <option value="true">사용 중</option>
                <option value="false">사용 중지</option>
              </select>
              <button className="primary" onClick={() => choose("new")}>
                <Plus size={17} />
                계정 등록
              </button>
            </div>
            <div className="management-columns">
              <section
                className="management-card account-list"
                aria-label="계정 목록"
              >
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>ID / 이름</th>
                        <th>역할</th>
                        <th>사용 상태</th>
                        <th>최근 로그인</th>
                        <th>관리</th>
                      </tr>
                    </thead>
                    <tbody>
                      {shown.map((a) => (
                        <tr
                          key={a.id}
                          className={
                            selected !== "new" && selected?.id === a.id
                              ? "selected"
                              : ""
                          }
                        >
                          <td>
                            <strong>{a.loginId}</strong>
                            <small>{a.name}</small>
                          </td>
                          <td>
                            <span className="role-badge">{a.role}</span>
                          </td>
                          <td>{a.active ? "사용 중" : "사용 중지"}</td>
                          <td>{date(a.lastLoginAt)}</td>
                          <td>
                            <button
                              className="secondary small"
                              aria-label={`${a.loginId} 관리`}
                              onClick={() => choose(a)}
                            >
                              관리
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!shown.length && (
                  <p className="empty-text">검색한 계정이 없습니다.</p>
                )}
              </section>
              {selected && (
                <section
                  className="management-card account-editor"
                  aria-label="계정 상세"
                >
                  <h2>
                    {selected === "new"
                      ? "새 계정 등록"
                      : `${selected.loginId} 계정`}
                  </h2>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      void run(async () => {
                        if (selected === "new") {
                          const a = await accountService.create(form);
                          choose(a);
                          setNotice("계정을 등록했습니다.");
                        } else {
                          await accountService.update(selected.id, form);
                          setNotice(
                            "계정 정보를 저장했습니다. 역할·상태 변경 시 기존 세션이 종료됩니다.",
                          );
                        }
                      });
                    }}
                  >
                    <label>
                      로그인 ID
                      <input
                        required
                        value={form.loginId}
                        disabled={selected !== "new"}
                        onChange={(e) =>
                          setForm({ ...form, loginId: e.target.value })
                        }
                        autoComplete="off"
                      />
                    </label>
                    {selected !== "new" && (
                      <small>등록한 ID는 변경할 수 없습니다.</small>
                    )}
                    <label>
                      표시 이름
                      <input
                        required
                        maxLength={80}
                        value={form.name}
                        onChange={(e) =>
                          setForm({ ...form, name: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      역할
                      <select
                        aria-label="역할"
                        value={form.role}
                        onChange={(e) =>
                          setForm({ ...form, role: e.target.value as Role })
                        }
                      >
                        {roles.map((r) => (
                          <option key={r}>{r}</option>
                        ))}
                      </select>
                    </label>
                    {selected === "new" ? (
                      <label>
                        초기 비밀번호
                        <input
                          type="password"
                          required
                          minLength={10}
                          maxLength={128}
                          value={form.password}
                          onChange={(e) =>
                            setForm({ ...form, password: e.target.value })
                          }
                          autoComplete="new-password"
                        />
                      </label>
                    ) : (
                      <label>
                        사용 상태
                        <select
                          aria-label="사용 상태"
                          value={String(form.active)}
                          onChange={(e) =>
                            setForm({
                              ...form,
                              active: e.target.value === "true",
                            })
                          }
                        >
                          <option value="true">사용 중</option>
                          <option value="false">사용 중지</option>
                        </select>
                      </label>
                    )}
                    <button className="primary" disabled={busy}>
                      {selected === "new" ? "등록하기" : "계정 정보 저장"}
                    </button>
                  </form>
                  {selected !== "new" && (
                    <>
                      <form
                        className="editor-section"
                        onSubmit={(e) => {
                          e.preventDefault();
                          void run(async () => {
                            await accountService.resetPassword(
                              selected.id,
                              form.password,
                            );
                            setForm((current) => ({
                              ...current,
                              password: "",
                            }));
                            setNotice(
                              "비밀번호를 재설정하고 기존 세션을 종료했습니다.",
                            );
                          });
                        }}
                      >
                        <h3>비밀번호 재설정</h3>
                        <p>
                          현재 비밀번호는 표시하지 않습니다. 재설정하면 해당
                          계정의 기존 로그인 세션이 종료됩니다.
                        </p>
                        <label>
                          새 비밀번호
                          <input
                            type="password"
                            required
                            minLength={10}
                            maxLength={128}
                            autoComplete="new-password"
                            value={form.password}
                            onChange={(e) =>
                              setForm({ ...form, password: e.target.value })
                            }
                          />
                        </label>
                        <button className="secondary" disabled={busy}>
                          비밀번호 재설정
                        </button>
                      </form>
                      {can(identity, "sources.assign") && (
                        <div className="editor-section">
                          <h3>사용 가능한 업무</h3>
                          <p>
                            본인이 게시한 업무를 배정합니다. 해제해도 기존
                            문서와 확인본은 유지됩니다.
                          </p>
                          {!assignmentsLoaded ? (
                            <p>업무 배정을 불러오는 중…</p>
                          ) : !sources.length ? (
                            <p>먼저 업무 연결 설정에서 업무를 게시해 주세요.</p>
                          ) : (
                            sources.map((s) => (
                              <label
                                className="assignment-row"
                                data-source-id={s.id}
                                key={s.id}
                              >
                                <input
                                  type="checkbox"
                                  disabled={
                                    busy || selected.id === identity.account.id
                                  }
                                  checked={
                                    !!assignments[s.id] ||
                                    selected.id === identity.account.id
                                  }
                                  onChange={(e) => {
                                    const assigned = e.target.checked;
                                    setAssignments((current) => ({
                                      ...current,
                                      [s.id]: assigned,
                                    }));
                                    void run(async () => {
                                      try {
                                        await api(
                                          `/api/sources/${s.id}/assignments/${selected.id}`,
                                          undefined,
                                          assigned ? "PUT" : "DELETE",
                                        );
                                      } catch (error) {
                                        setAssignments((current) => ({
                                          ...current,
                                          [s.id]: !assigned,
                                        }));
                                        throw error;
                                      }
                                      await accountService.recordAssignment(
                                        selected.loginId,
                                        s.name,
                                        assigned,
                                      );
                                      setNotice(
                                        `${s.name} 업무를 ${assigned ? "배정" : "해제"}했습니다.`,
                                      );
                                    });
                                  }}
                                />
                                <span>
                                  <strong>{s.name}</strong>
                                  <small>
                                    {s.description || "게시된 업무"}
                                    {selected.id === identity.account.id &&
                                      " · 업무 소유자"}
                                  </small>
                                </span>
                              </label>
                            ))
                          )}
                        </div>
                      )}
                    </>
                  )}
                </section>
              )}
            </div>
          </>
        ) : page === "permissions" ? (
          <>
            <div className="role-description-grid">
              {roles.map((r) => (
                <section className="management-card" key={r}>
                  <h2>{r}</h2>
                  <p>{descriptions[r]}</p>
                </section>
              ))}
            </div>
            <section className="management-card">
              <div className="table-scroll">
                <table className="permission-table">
                  <thead>
                    <tr>
                      <th>기능</th>
                      {roles.map((r) => (
                        <th key={r}>{r}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {permissions.map((p) => (
                      <tr key={p}>
                        <th>
                          {permissionLabels[p]}
                          {fixedPermissions.includes(p) && (
                            <small>관리자 전용 · 고정</small>
                          )}
                        </th>
                        {roles.map((r) => (
                          <td key={r}>
                            <input
                              type="checkbox"
                              aria-label={`${r} ${permissionLabels[p]}`}
                              checked={!!policy?.[r][p]}
                              disabled={
                                busy ||
                                !policy ||
                                r === "ADMINISTRATOR" ||
                                fixedPermissions.includes(p)
                              }
                              onChange={(e) => {
                                const enabled = e.target.checked;
                                setPolicy(
                                  (current) =>
                                    current && {
                                      ...current,
                                      [r]: { ...current[r], [p]: enabled },
                                    },
                                );
                                void run(async () => {
                                  try {
                                    await accountService.setPolicy(
                                      r,
                                      p,
                                      enabled,
                                    );
                                  } catch (error) {
                                    setPolicy(await accountService.policy());
                                    throw error;
                                  }
                                  setNotice(
                                    "권한을 변경했습니다. 열린 탭에도 반영됩니다.",
                                  );
                                });
                              }}
                            />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="muted">
                계정·권한·이력 관리는 ADMINISTRATOR에 고정됩니다. 다른 사용자의
                기획을 조회하는 권한은 제공하지 않습니다.
              </p>
            </section>
          </>
        ) : (
          <section className="management-card">
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>시각</th>
                    <th>처리 계정</th>
                    <th>작업</th>
                    <th>대상</th>
                    <th>변경 내용</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((h) => (
                    <tr key={h.id}>
                      <td>{date(h.at)}</td>
                      <td>{h.actor}</td>
                      <td>{h.action}</td>
                      <td>{h.target}</td>
                      <td>{h.detail || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {auditLoading && <p role="status">변경 이력을 불러오는 중…</p>}
            {auditNotice && <p role="status">{auditNotice}</p>}
            {auditError && <p role="alert">{auditError}</p>}
            {!history.length && !auditLoading && !auditError && <p>아직 변경 이력이 없습니다.</p>}
            {(auditNext || auditError) && (
              <button
                className="secondary"
                disabled={auditLoading}
                onClick={() => void loadAudit(auditNext || undefined)}
              >
                {auditError ? "다시 시도" : "이전 이력 더 보기"}
              </button>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
