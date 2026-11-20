import { useEffect, useRef, useState } from "react";
import { ApiError, setAccessGuard, setToken } from "../api";
import {
  accountService,
  configureAccountService,
  can,
  type Identity,
  type Permission,
} from "./index";
import { ensureSession } from "./server";
function requestPermission(path: string, method: string): Permission | null {
  if (path.startsWith("/api/projects")) {
    if (path.includes("/export")) return "plans.export";
    if (method === "GET") return "plans.read";
    if (path === "/api/projects") return "plans.create";
    if (path.endsWith("/approve")) return "plans.confirm";
    if (path.endsWith("/cancel")) return null;
    return "plans.edit";
  }
  if (path.startsWith("/api/sources")) {
    if (path.includes("/assignments")) return "sources.assign";
    if (method === "GET" && path === "/api/sources") return null;
    return "sources.manage";
  }
  return null;
}
export function useAuth(mode: string | undefined) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [authed, setAuthed] = useState(false);
  const [ready, setReady] = useState(false);
  const [notice, setNotice] = useState("");
  const wasAuthed = useRef(false);
  useEffect(() => {
    if (!mode) return;
    configureAccountService(mode);
    let active = true;
    const sync = async () => {
      try {
        const current = await accountService.current();
        if (!active) return;
        if (mode === "mock") setToken(current ? `local:${current.account.id}` : "", false);
        setIdentity(current);
        setAuthed(!!current);
        setReady(true);
        if (wasAuthed.current && !current)
          setNotice(
            "계정 설정이 변경되어 로그아웃되었습니다. 다시 로그인해 주세요.",
          );
        wasAuthed.current = !!current;
      } catch (e) {
        if (active) {
          setNotice(
            e instanceof Error ? e.message : "계정 정보를 불러오지 못했습니다.",
          );
          setReady(true);
          setAuthed(false);
        }
      }
    };
    if (mode === "mock") {
      sessionStorage.removeItem("hplan-test-session");
      setAccessGuard(async (path, method) => {
        if (!path.startsWith("/api/") || path.startsWith("/api/auth/")) return;
        const current = await accountService.current();
        if (!current) {
          void sync();
          throw new ApiError("다시 로그인해 주세요.", 401);
        }
        const permission = requestPermission(path, method);
        if (permission && !can(current, permission))
          throw new ApiError(
            "이 기능을 사용할 권한이 없습니다. 관리자에게 문의해 주세요.",
            403,
          );
        setToken(`local:${current.account.id}`, false);
      });
    } else {
      setAccessGuard(async (path) => {
        if (path.startsWith("/api/auth/")) return;
        await ensureSession();
      });
    }
    void sync();
    const unsubscribe = accountService.subscribe(() => void sync());
    return () => {
      active = false;
      unsubscribe();
      setAccessGuard(null);
    };
  }, [mode]);
  const login = async (identifier: string, password: string) => {
    const current = await accountService.login(identifier, password);
    if (mode === "mock") setToken(`local:${current.account.id}`, false);
    setIdentity(current);
    wasAuthed.current = true;
    setNotice("");
    setAuthed(true);
  };
  const logout = async () => {
    wasAuthed.current = false;
    try { await accountService.logout(); }
    finally { setToken(""); setIdentity(null); setAuthed(false); }
  };
  const allowed = (permission: Permission) =>
    can(identity, permission);
  return { identity, authed, ready, notice, login, logout, allowed };
}
