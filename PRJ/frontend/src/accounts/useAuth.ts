import { useCallback, useEffect, useRef, useState } from "react";
import { setAccessGuard, setToken } from "../api";
import {
  accountService,
  can,
  type Identity,
  type Permission,
} from "./index";
import { ensureSession } from "./server";
export function useAuth(mode: string | undefined) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [authed, setAuthed] = useState(false);
  const [ready, setReady] = useState(false);
  const [notice, setNotice] = useState("");
  const [recovering, setRecovering] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const wasAuthed = useRef(false);
  const request = useRef(0);
  const syncRef = useRef<() => Promise<void>>(async () => {});
  const retry = useCallback(() => syncRef.current(), []);
  useEffect(() => {
    if (!mode) return;
    let active = true;
    const sync = async () => {
      const version = ++request.current;
      setRecovering(true);
      try {
        await accountService.initialize();
        const current = await accountService.current();
        if (!active || version !== request.current) return;
        setIdentity(current);
        setAuthed(!!current);
        setUnavailable(false);
        if (current) setNotice("");
        else if (wasAuthed.current)
          setNotice(
            "계정 설정이 변경되어 로그아웃되었습니다. 다시 로그인해 주세요.",
          );
        wasAuthed.current = !!current;
      } catch (e) {
        if (active && version === request.current) {
          setNotice(
            e instanceof Error ? e.message : "계정 정보를 불러오지 못했습니다.",
          );
          setUnavailable(true);
        }
      } finally {
        if (active && version === request.current) {
          setReady(true);
          setRecovering(false);
        }
      }
    };
    syncRef.current = sync;
    setAccessGuard(async (path) => {
      if (path.startsWith("/api/auth/")) return;
      await ensureSession();
    });
    void sync();
    const unsubscribe = accountService.subscribe(() => void sync());
    return () => {
      active = false;
      unsubscribe();
      setAccessGuard(null);
    };
  }, [mode]);
  const login = async (identifier: string, password: string) => {
    ++request.current;
    const current = await accountService.login(identifier, password);
    setIdentity(current);
    wasAuthed.current = true;
    setNotice("");
    setUnavailable(false);
    setRecovering(false);
    setAuthed(true);
  };
  const logout = async (options?: { explicit?: boolean }) => {
    ++request.current;
    wasAuthed.current = false;
    try { await accountService.logout(options); }
    finally {
      setToken("");
      setIdentity(null);
      setAuthed(false);
      setUnavailable(false);
      setRecovering(false);
    }
  };
  const allowed = (permission: Permission) =>
    can(identity, permission);
  return { identity, authed, ready, notice, recovering, unavailable, retry, login, logout, allowed };
}
