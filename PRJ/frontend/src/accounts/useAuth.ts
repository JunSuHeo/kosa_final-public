import { useEffect, useRef, useState } from "react";
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
  const wasAuthed = useRef(false);
  useEffect(() => {
    if (!mode) return;
    void accountService.initialize();
    let active = true;
    const sync = async () => {
      try {
        const current = await accountService.current();
        if (!active) return;
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
    const current = await accountService.login(identifier, password);
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
