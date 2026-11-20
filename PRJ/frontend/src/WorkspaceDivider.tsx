import { useRef, useState, type CSSProperties, type PointerEvent } from "react";
const storageKey = "hplan-workspace-ratio.v1";
const defaultRatio = 0.42;
function initialRatio() {
  try {
    const stored = Number(localStorage.getItem(storageKey));
    return stored >= 0.25 && stored <= 0.65 ? stored : defaultRatio;
  } catch {
    return defaultRatio;
  }
}
export function useWorkspaceWidth() {
  const [ratio, setRatio] = useState(initialRatio);
  const [resizing, setResizing] = useState(false);
  const current = useRef(ratio);
  const change = (next: number, persist = false) => {
    current.current = next;
    setRatio(next);
    if (persist) {
      try {
        localStorage.setItem(storageKey, String(next));
      } catch {
        /* Layout works without browser storage. */
      }
    }
  };
  const bounds = (element: HTMLElement) => {
    const parent = element.parentElement!;
    const rail = parent
      .querySelector<HTMLElement>(".rail")!
      .getBoundingClientRect();
    const available = parent.clientWidth - rail.width - element.offsetWidth;
    return {
      left: rail.right,
      available,
      min: Math.max(0.25, 320 / available),
      max: Math.min(0.65, 1 - 420 / available),
    };
  };
  const resize = (event: PointerEvent<HTMLDivElement>) => {
    const { left, available, min, max } = bounds(event.currentTarget);
    change(
      Math.max(
        min,
        Math.min(
          max,
          (event.clientX - left - event.currentTarget.offsetWidth / 2) /
            available,
        ),
      ),
    );
  };
  const finish = () => {
    setResizing(false);
    change(current.current, true);
  };
  return {
    style: { "--conversation-ratio": ratio } as CSSProperties,
    resizing,
    divider: (
      <div
        className="workspace-divider"
        role="separator"
        aria-label="대화와 산출물 너비 조절"
        aria-orientation="vertical"
        title="드래그하여 너비 조절 · 두 번 클릭하면 기본 비율"
        onPointerDown={(event) => {
          if (event.button !== 0 || !event.isPrimary) return;
          event.preventDefault();
          event.currentTarget.setPointerCapture(event.pointerId);
          setResizing(true);
        }}
        onPointerMove={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId))
            resize(event);
        }}
        onPointerUp={(event) => {
          if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId);
            finish();
          }
        }}
        onLostPointerCapture={finish}
        onPointerCancel={finish}
        onDoubleClick={() => change(defaultRatio, true)}
      />
    ),
  };
}
