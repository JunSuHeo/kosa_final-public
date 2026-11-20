import { useEffect, useRef } from "react";
import {
  ClipboardList,
  Home,
  Settings2,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
export default function AdminNavigation({
  page,
  onNavigate,
  onClose,
}: {
  page: string;
  onNavigate: (page: string) => void;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current!;
    element.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      element.close();
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className="admin-drawer"
      aria-label="관리자 내비게이션"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="admin-drawer-content">
        <div className="drawer-heading">
          <strong>H-PlanIT</strong>
          <button aria-label="내비게이션 닫기" onClick={onClose}>
            <X size={21} />
          </button>
        </div>
        <span className="eyebrow">ADMINISTRATOR</span>
        <nav aria-label="관리자 메뉴">
          <button onClick={() => onNavigate("home")}>
            <Home size={18} />
            업무 홈
          </button>
          <button onClick={() => onNavigate("settings")}>
            <Settings2 size={18} />
            업무 연결 설정
          </button>
          <p>사용자 관리</p>
          {[
            ["accounts", "계정 관리", Users],
            ["permissions", "역할·권한 설정", ShieldCheck],
            ["audit", "변경 이력", ClipboardList],
          ].map(([id, label, Icon]) => {
            const ItemIcon = Icon as typeof Users;
            return (
              <button
                key={String(id)}
                aria-current={page === id ? "page" : undefined}
                onClick={() => onNavigate(String(id))}
              >
                <ItemIcon size={18} />
                {String(label)}
              </button>
            );
          })}
        </nav>
        <small>계정·권한은 이 브라우저의 테스트 설정으로 보관됩니다.</small>
      </div>
    </dialog>
  );
}
