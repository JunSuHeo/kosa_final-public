import { ChevronDown, LogOut, UserRound } from "lucide-react";

export default function AccountMenu({
  name,
  displayName,
  role,
  onLogout,
}: {
  name: string;
  displayName?: string;
  role?: string;
  onLogout: () => void;
}) {
  return (
    <details
      className="account-menu"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.currentTarget.open = false;
          event.currentTarget.querySelector("summary")?.focus();
        }
      }}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget))
          event.currentTarget.open = false;
      }}
    >
      <summary aria-label="계정 메뉴">
        <UserRound className="account-icon" size={16} />
        <span>{name}</span>
        <ChevronDown className="account-chevron" size={14} />
      </summary>
      <div className="account-popover">
        <span>{name}</span>
        {displayName && displayName !== name && <span>{displayName}</span>}
        {role && <small>{role}</small>}
        <button type="button" onClick={onLogout}>
          <LogOut size={16} />
          로그아웃
        </button>
      </div>
    </details>
  );
}
