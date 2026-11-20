import { useEffect, useRef, useState } from "react";
import { api, ApiError, setAccessGuard, setToken } from "../api";
import {
  accountService,
  can,
  fixedPermissions,
  type Identity,
  type Permission,
} from "./index";
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
    let active = true;
    const sync = async () => {
      if (mode !== "mock") {
        if (active) {
          setAuthed(!!sessionStorage.getItem("studio-token"));
          setReady(true);
        }
        return;
      }
      try {
        const current = await accountService.current();
        if (!active) return;
        setToken(current ? `local:${current.account.id}` : "", false);
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
    }
    void sync();
    const unsubscribe =
      mode === "mock" ? accountService.subscribe(() => void sync()) : () => {};
    return () => {
      active = false;
      unsubscribe();
      setAccessGuard(null);
    };
  }, [mode]);
  const login = async (identifier: string, password: string) => {
    if (mode === "mock") {
      const current = await accountService.login(identifier, password);
      setToken(`local:${current.account.id}`, false);
      setIdentity(current);
      wasAuthed.current = true;
    } else {
      const result = await api<{ access_token: string }>("/api/auth/login", {
        email: identifier,
        password,
      });
      setToken(result.access_token);
    }
    setNotice("");
    setAuthed(true);
  };
  const logout = async () => {
    wasAuthed.current = false;
    setToken("");
    if (mode === "mock") await accountService.logout();
    setIdentity(null);
    setAuthed(false);
  };
  const allowed = (permission: Permission) =>
    mode === "mock"
      ? can(identity, permission)
      : !fixedPermissions.includes(permission) &&
        permission !== "sources.assign";
  return { identity, authed, ready, notice, login, logout, allowed };
}
