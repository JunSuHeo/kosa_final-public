import {
  can,
  fixedPermissions,
  permissions,
  roles,
  type Account,
  type AccountInput,
  type AccountService,
  type AuditEntry,
  type Identity,
  type Permission,
  type Policy,
  type Role,
} from "./types";

const STORE = "hplan-accounts.v1";
const SESSION = "hplan-session.v2";
const CHANGE = "hplan-accounts-changed";
interface StoredAccount extends Account {
  verifier: { salt: string; hash: string; iterations: number };
}
interface Store {
  version: 1;
  accounts: StoredAccount[];
  policy: Policy;
  history: AuditEntry[];
}
const publicAccount = ({
  verifier: _verifier,
  ...account
}: StoredAccount): Account => account;
const hex = (bytes: ArrayBuffer | Uint8Array) =>
  Array.from(new Uint8Array(bytes))
    .map((v) => v.toString(16).padStart(2, "0"))
    .join("");
async function verifier(
  password: string,
  salt = hex(crypto.getRandomValues(new Uint8Array(16))),
  iterations = 120000,
) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const hash = hex(
    await crypto.subtle.deriveBits(
      {
        name: "PBKDF2",
        hash: "SHA-256",
        salt: new TextEncoder().encode(salt),
        iterations,
      },
      key,
      256,
    ),
  );
  return { salt, hash, iterations };
}
function read(): Store {
  const value = JSON.parse(
    localStorage.getItem(STORE) || "null",
  ) as Store | null;
  if (!value || value.version !== 1)
    throw new Error(
      "계정 저장소를 불러올 수 없습니다. 브라우저 저장소를 확인해 주세요.",
    );
  return value;
}
function save(store: Store) {
  localStorage.setItem(STORE, JSON.stringify(store));
  window.dispatchEvent(new Event(CHANGE));
}
function sessionAccount(store: Store): StoredAccount | null {
  const session = JSON.parse(sessionStorage.getItem(SESSION) || "null");
  return (
    store.accounts.find(
      (a) =>
        a.id === session?.accountId &&
        a.sessionVersion === session?.version &&
        a.active,
    ) || null
  );
}
function authorize(store: Store, permission: Permission): StoredAccount {
  const account = sessionAccount(store);
  if (!account || !can({ account, policy: store.policy }, permission))
    throw new Error("이 기능을 사용할 권한이 없습니다.");
  return account;
}
function audit(
  store: Store,
  actor: string,
  action: string,
  target: string,
  detail = "",
) {
  store.history.unshift({
    id: crypto.randomUUID(),
    at: new Date().toISOString(),
    actor,
    action,
    target,
    detail,
  });
}
function checkedAccount(store: Store, id: string) {
  const account = store.accounts.find((a) => a.id === id);
  if (!account) throw new Error("계정을 찾을 수 없습니다.");
  return account;
}
function passwordCheck(password: string) {
  if (password.length < 10 || password.length > 128)
    throw new Error("테스트 비밀번호는 10~128자로 입력해 주세요.");
}
// The same asynchronous interface can be implemented by an HTTP account service.
// Web Locks prevent lost changes when two administrator tabs update the store.
async function exclusive<T>(action: () => Promise<T>): Promise<T> {
  return navigator.locks.request(STORE, action);
}
const browserAccounts: AccountService = {
  async initialize() {
    await exclusive(async () => {
      if (localStorage.getItem(STORE)) {
        read();
        return;
      }
      const policy = Object.fromEntries(
        roles.map((role) => [
          role,
          Object.fromEntries(
            permissions.map((p) => [
              p,
              role === "ADMINISTRATOR" || p.startsWith("plans."),
            ]),
          ),
        ]),
      ) as Policy;
      const accounts: StoredAccount[] = [];
      for (const [id, loginId, role] of [
        ["demo-user", "admin", "ADMINISTRATOR"],
        ["test-user-1", "user1", "USER1"],
        ["test-user-2", "user2", "USER2"],
      ] as const) {
        accounts.push({
          id,
          loginId,
          name: loginId,
          role,
          active: true,
          sessionVersion: 1,
          createdAt: new Date().toISOString(),
          lastLoginAt: null,
          verifier: await verifier("a123456789!"),
        });
      }
      save({ version: 1, accounts, policy, history: [] });
    });
  },
  async login(loginId, password) {
    await this.initialize();
    return exclusive(async () => {
      const store = read();
      const account = store.accounts.find((a) => a.loginId === loginId.trim());
      if (
        !account ||
        !account.active ||
        (
          await verifier(
            password,
            account.verifier.salt,
            account.verifier.iterations,
          )
        ).hash !== account.verifier.hash
      ) {
        audit(
          store,
          loginId.trim().slice(0, 100),
          "로그인 실패",
          loginId.trim().slice(0, 100),
        );
        save(store);
        throw new Error("ID 또는 비밀번호를 확인해 주세요.");
      }
      account.lastLoginAt = new Date().toISOString();
      sessionStorage.setItem(
        SESSION,
        JSON.stringify({
          accountId: account.id,
          version: account.sessionVersion,
        }),
      );
      audit(store, account.loginId, "로그인", account.loginId);
      save(store);
      return { account: publicAccount(account), policy: store.policy };
    });
  },
  async logout() {
    sessionStorage.removeItem(SESSION);
    window.dispatchEvent(new Event(CHANGE));
  },
  async current() {
    await this.initialize();
    const store = read();
    const account = sessionAccount(store);
    if (!account) {
      sessionStorage.removeItem(SESSION);
      return null;
    }
    return { account: publicAccount(account), policy: store.policy };
  },
  async accounts() {
    const store = read();
    authorize(store, "accounts.manage");
    return store.accounts.map(publicAccount);
  },
  async assignmentAccounts() {
    const store = read();
    authorize(store, "sources.assign");
    return store.accounts.map(({ id, loginId, name, active }) => ({
      id,
      loginId,
      name,
      active,
    }));
  },
  async create(input: AccountInput) {
    return exclusive(async () => {
      const store = read();
      const actor = authorize(store, "accounts.manage");
      const loginId = input.loginId.trim();
      const name = input.name.trim();
      if (!/^[a-zA-Z0-9._-]{3,40}$/.test(loginId))
        throw new Error(
          "ID는 영문·숫자·점·밑줄·하이픈 3~40자로 입력해 주세요.",
        );
      if (!name || name.length > 80 || !roles.includes(input.role))
        throw new Error("이름과 역할을 확인해 주세요.");
      if (store.accounts.some((a) => a.loginId === loginId))
        throw new Error("이미 사용 중인 ID입니다.");
      passwordCheck(input.password);
      const account: StoredAccount = {
        id: crypto.randomUUID(),
        loginId,
        name,
        role: input.role,
        active: true,
        sessionVersion: 1,
        createdAt: new Date().toISOString(),
        lastLoginAt: null,
        verifier: await verifier(input.password),
      };
      store.accounts.push(account);
      audit(
        store,
        actor.loginId,
        "계정 등록",
        loginId,
        `${name} · ${input.role}`,
      );
      save(store);
      return publicAccount(account);
    });
  },
  async update(id, input) {
    await exclusive(async () => {
      const store = read();
      const actor = authorize(store, "accounts.manage");
      const account = checkedAccount(store, id);
      const name = input.name.trim();
      if (!name || name.length > 80 || !roles.includes(input.role))
        throw new Error("이름과 역할을 확인해 주세요.");
      if (
        account.active &&
        account.role === "ADMINISTRATOR" &&
        (!input.active || input.role !== "ADMINISTRATOR") &&
        store.accounts.filter((a) => a.active && a.role === "ADMINISTRATOR")
          .length <= 1
      )
        throw new Error(
          "마지막 활성 ADMINISTRATOR는 사용 중지하거나 역할을 변경할 수 없습니다.",
        );
      if (account.name !== name)
        audit(
          store,
          actor.loginId,
          "정보 변경",
          account.loginId,
          `${account.name} → ${name}`,
        );
      if (account.role !== input.role)
        audit(
          store,
          actor.loginId,
          "역할 변경",
          account.loginId,
          `${account.role} → ${input.role}`,
        );
      if (account.active !== input.active)
        audit(
          store,
          actor.loginId,
          "사용 상태 변경",
          account.loginId,
          input.active ? "재활성화" : "사용 중지",
        );
      if (account.role !== input.role || account.active !== input.active)
        account.sessionVersion++;
      Object.assign(account, { name, role: input.role, active: input.active });
      save(store);
    });
  },
  async resetPassword(id, password) {
    passwordCheck(password);
    await exclusive(async () => {
      const store = read();
      const actor = authorize(store, "accounts.manage");
      const account = checkedAccount(store, id);
      account.verifier = await verifier(password);
      account.sessionVersion++;
      audit(
        store,
        actor.loginId,
        "비밀번호 재설정",
        account.loginId,
        "기존 세션 종료",
      );
      save(store);
    });
  },
  async policy() {
    const store = read();
    authorize(store, "roles.manage");
    return store.policy;
  },
  async setPolicy(role, permission, enabled) {
    await exclusive(async () => {
      const store = read();
      const actor = authorize(store, "roles.manage");
      if (role === "ADMINISTRATOR" || fixedPermissions.includes(permission))
        throw new Error("관리자 전용 권한은 고정되어 있습니다.");
      store.policy[role][permission] = enabled;
      audit(
        store,
        actor.loginId,
        "권한 변경",
        role,
        `${permission}: ${enabled ? "허용" : "차단"}`,
      );
      save(store);
    });
  },
  async audit() {
    const store = read();
    authorize(store, "audit.read");
    return store.history;
  },
  async recordAssignment(target, business, assigned) {
    await exclusive(async () => {
      const store = read();
      const actor = authorize(store, "sources.assign");
      audit(
        store,
        actor.loginId,
        "업무 배정",
        target,
        `${business} · ${assigned ? "배정" : "해제"}`,
      );
      save(store);
    });
  },
  subscribe(listener) {
    const onStorage = (event: StorageEvent) => {
      if (event.key === STORE || event.key === null) listener();
    };
    window.addEventListener("storage", onStorage);
    window.addEventListener(CHANGE, listener);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(CHANGE, listener);
    };
  },
};
export default browserAccounts;
