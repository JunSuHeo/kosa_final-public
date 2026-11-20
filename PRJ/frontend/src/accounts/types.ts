export const roles = ["USER1", "USER2", "ADMINISTRATOR"] as const;
export type Role = (typeof roles)[number];
export const permissionLabels = {
  "plans.read": "본인 기획 조회",
  "plans.create": "기획 작성",
  "plans.edit": "기획 수정·AI 대화",
  "plans.confirm": "현업 확인본 저장",
  "plans.export": "확인본 내보내기",
  "sources.manage": "업무 연결 준비",
  "sources.assign": "업무 배정",
  "accounts.manage": "계정 관리",
  "roles.manage": "역할·권한 설정",
  "audit.read": "변경 이력 조회",
} as const;
export type Permission = keyof typeof permissionLabels;
export const permissions = Object.keys(permissionLabels) as Permission[];
export const fixedPermissions: Permission[] = [
  "accounts.manage",
  "roles.manage",
  "audit.read",
];
export type Policy = Record<Role, Record<Permission, boolean>>;
export interface Account {
  id: string;
  loginId: string;
  name: string;
  role: Role;
  active: boolean;
  sessionVersion: number;
  createdAt: string;
  lastLoginAt: string | null;
}
export interface AuditEntry {
  id: string;
  at: string;
  actor: string;
  action: string;
  target: string;
  detail: string;
}
export interface Identity {
  account: Account;
  policy: Policy;
}
export interface AccountInput {
  loginId: string;
  name: string;
  role: Role;
  password: string;
}
export interface AccountService {
  initialize(): Promise<void>;
  login(loginId: string, password: string): Promise<Identity>;
  logout(): Promise<void>;
  current(): Promise<Identity | null>;
  accounts(): Promise<Account[]>;
  assignmentAccounts(): Promise<
    Pick<Account, "id" | "loginId" | "name" | "active">[]
  >;
  create(input: AccountInput): Promise<Account>;
  update(
    id: string,
    input: Pick<Account, "name" | "role" | "active">,
  ): Promise<void>;
  resetPassword(id: string, password: string): Promise<void>;
  policy(): Promise<Policy>;
  setPolicy(
    role: Role,
    permission: Permission,
    enabled: boolean,
  ): Promise<void>;
  audit(): Promise<AuditEntry[]>;
  recordAssignment(
    target: string,
    business: string,
    assigned: boolean,
  ): Promise<void>;
  subscribe(listener: () => void): () => void;
}
export function can(
  identity: Identity | null,
  permission: Permission,
): boolean {
  if (!identity?.account.active) return false;
  if (fixedPermissions.includes(permission))
    return identity.account.role === "ADMINISTRATOR";
  return identity.policy[identity.account.role][permission];
}
