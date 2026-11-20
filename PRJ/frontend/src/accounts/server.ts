import { api, ApiError, setToken } from "../api";
import type { Account, AccountInput, AccountService, AuditEntry, Identity, Permission, Policy, Role } from "./types";

const SESSION = "hplan-supabase-session.v1";
const CHANGE = "hplan-server-accounts-changed";
type Session = { access_token: string; refresh_token: string; expires_at: number };
type LoginResult = { access_token: string; refresh_token: string; expires_in: number; identity: Identity };
let refreshing: Promise<void> | null = null;
let generation = 0;
const OPERATIONS = "hplan-account-operations.v1";
const channel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel("hplan-account-updates");

function read(): Session | null {
  try { return JSON.parse(sessionStorage.getItem(SESSION) || "null"); }
  catch { return null; }
}
function changed() {
  window.dispatchEvent(new Event(CHANGE));
  channel?.postMessage("changed");
}
function clear() {
  generation++;
  sessionStorage.removeItem(SESSION);
  setToken("");
}
function save(result: LoginResult) {
  sessionStorage.setItem(SESSION, JSON.stringify({
    access_token: result.access_token, refresh_token: result.refresh_token,
    expires_at: Date.now() + result.expires_in * 1000,
  }));
  setToken(result.access_token);
}
export async function ensureSession() {
  const session = read();
  if (!session) { setToken(""); return; }
  if (session.expires_at > Date.now() + 60_000) {
    setToken(session.access_token);
    return;
  }
  if (!refreshing) {
    const version = generation;
    refreshing = api<LoginResult>("/api/auth/refresh", { refresh_token: session.refresh_token })
      .then(result => { if (generation === version) save(result); })
      .catch(error => {
        if (generation === version && error instanceof ApiError && error.status === 401) clear();
        throw error;
      }).finally(() => { refreshing = null; });
  }
  await refreshing;
}
async function operation<T>(key: string, path: string, body: object): Promise<T> {
  const operations: Record<string, string> = JSON.parse(sessionStorage.getItem(OPERATIONS) || "{}");
  const id = operations[key] || crypto.randomUUID();
  operations[key] = id;
  sessionStorage.setItem(OPERATIONS, JSON.stringify(operations));
  const result = await api<T>(path, { ...body, operation_id: id });
  delete operations[key];
  sessionStorage.setItem(OPERATIONS, JSON.stringify(operations));
  changed();
  return result;
}

const server: AccountService = {
  async initialize() {},
  async login(identifier, password) {
    const version = ++generation;
    const result = await api<LoginResult>("/api/auth/login", { identifier, password });
    if (version !== generation) throw new Error("로그인 요청이 취소되었습니다.");
    save(result);
    return result.identity;
  },
  async logout() {
    try { if (read()) await api("/api/auth/logout", {}); }
    finally { clear(); sessionStorage.removeItem(OPERATIONS); }
  },
  async current() {
    if (!read()) { setToken(""); return null; }
    try {
      await ensureSession();
      return await api<Identity>("/api/auth/me");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) { clear(); return null; }
      throw error;
    }
  },
  accounts: () => api<Account[]>("/api/accounts"),
  assignmentAccounts: () => api<Pick<Account, "id" | "loginId" | "name" | "active">[]>("/api/accounts/assignment-options"),
  create(input: AccountInput) {
    return operation<Account>(`create:${input.loginId}:${input.name}:${input.role}`, "/api/accounts", input);
  },
  async update(id, input) {
    await api(`/api/accounts/${encodeURIComponent(id)}`, input, "PATCH");
    changed();
  },
  async resetPassword(id, password) {
    await operation(`reset:${id}`, `/api/accounts/${encodeURIComponent(id)}/reset-password`, { password });
  },
  policy: () => api<Policy>("/api/roles"),
  async setPolicy(role: Role, permission: Permission, enabled: boolean) {
    await api(`/api/roles/${role}/${permission}`, { enabled }, "PUT");
    changed();
  },
  async audit() {
    const result = await api<{ items: AuditEntry[] }>("/api/audit?limit=200");
    return result.items;
  },
  // Assignment mutations and their audit records are committed by the server together.
  async recordAssignment() { changed(); },
  subscribe(listener) {
    const onMessage = () => listener();
    const timer = window.setInterval(listener, 30_000);
    window.addEventListener(CHANGE, listener);
    window.addEventListener("focus", listener);
    channel?.addEventListener("message", onMessage);
    return () => {
      clearInterval(timer);
      window.removeEventListener(CHANGE, listener);
      window.removeEventListener("focus", listener);
      channel?.removeEventListener("message", onMessage);
    };
  },
};
export default server;
