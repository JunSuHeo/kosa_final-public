import { useCallback, useState, type Dispatch, type SetStateAction } from "react";

const PREFIX = "hplan-tab-draft.v1:";
export function tabDraftKey(owner: string, kind: string, id: string) {
  return `${PREFIX}${encodeURIComponent(owner)}:${kind}:${id}`;
}
export function readTabDraft<T>(key: string, initial: T): T {
  try {
    const value = sessionStorage.getItem(key);
    return value === null ? initial : JSON.parse(value) as T;
  } catch { return initial; }
}
export function writeTabDraft<T>(key: string, value: T) {
  try { sessionStorage.setItem(key, JSON.stringify(value)); }
  catch { /* Input remains in memory if tab storage is unavailable. */ }
}
export function removeTabDraft(key: string) {
  try { sessionStorage.removeItem(key); } catch { /* Tab storage unavailable. */ }
}
export function clearTabDrafts(owner?: string) {
  const prefix = owner === undefined ? PREFIX : `${PREFIX}${encodeURIComponent(owner)}:`;
  try {
    Object.keys(sessionStorage).filter(key => key.startsWith(prefix))
      .forEach(key => sessionStorage.removeItem(key));
  } catch { /* Tab storage unavailable. */ }
}
export function useTabDraft<T>(key: string, initial: T): [T, Dispatch<SetStateAction<T>>, () => void] {
  const [state, setState] = useState(() => ({ key, value: readTabDraft(key, initial) }));
  // A different account, project or question must never inherit the previous input.
  const value = state.key === key ? state.value : readTabDraft(key, initial);
  const setValue: Dispatch<SetStateAction<T>> = useCallback(next => {
    setState(previous => {
      const current = previous.key === key ? previous.value : readTabDraft(key, initial);
      const result = typeof next === "function" ? (next as (value: T) => T)(current) : next;
      writeTabDraft(key, result);
      return { key, value: result };
    });
  }, [key, initial]);
  const clear = useCallback(() => {
    removeTabDraft(key);
    setState({ key, value: initial });
  }, [key, initial]);
  return [value, setValue, clear];
}
