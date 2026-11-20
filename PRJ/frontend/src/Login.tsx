import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
} from "lucide-react";
import { Brand } from "./BusinessHome";

export default function Login({
  mock,
  onLogin,
  notice,
}: {
  mock: boolean;
  onLogin: (id: string, password: string) => Promise<void>;
  notice?: string;
}) {
  const [id, setId] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const passwordInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (error && !busy) passwordInput.current?.focus();
  }, [error, busy]);
  return (
    <main className="login-screen hplan-login">
      <div className="login-shell">
        <form
          aria-label="로그인"
          aria-busy={busy}
          onSubmit={async (event) => {
            event.preventDefault();
            if (submitting.current) return;
            submitting.current = true;
            setBusy(true);
            setError("");
            try {
              await onLogin(id.trim(), password);
            } catch (cause) {
              setError(
                cause instanceof Error
                  ? cause.message
                  : "로그인하지 못했어요. 다시 시도해 주세요.",
              );
              setPassword("");
              setVisible(false);
            } finally {
              submitting.current = false;
              setBusy(false);
            }
          }}
        >
          <div className="login-brand-row">
            <Brand />
            {mock && <span className="test-badge">테스트 환경</span>}
          </div>
          <span className="login-emblem" aria-hidden="true">
            <LockKeyhole size={25} />
          </span>
          <h1>업무 기획을 시작해 보세요</h1>
          <p className="login-description">
            업무에 필요한 변화를 함께 정리해요.
          </p>
          <label htmlFor="login-id">{mock ? "아이디" : "이메일"}</label>
          <input
            id="login-id"
            name="username"
            type={mock ? "text" : "email"}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            required
            value={id}
            disabled={busy}
            aria-invalid={!!error}
            aria-describedby={error ? "login-error" : undefined}
            placeholder={
              mock ? "아이디를 입력해 주세요" : "이메일을 입력해 주세요"
            }
            onChange={(event) => {
              setId(event.target.value);
              setError("");
            }}
          />
          <label htmlFor="login-password">비밀번호</label>
          <div className="login-password-field">
            <input
              id="login-password"
              name="password"
              ref={passwordInput}
              type={visible ? "text" : "password"}
              autoComplete="current-password"
              required
              value={password}
              disabled={busy}
              aria-invalid={!!error}
              aria-describedby={error ? "login-error" : undefined}
              placeholder="비밀번호를 입력해 주세요"
              onChange={(event) => {
                setPassword(event.target.value);
                setError("");
              }}
            />
            <button
              type="button"
              className="password-toggle"
              aria-label={visible ? "비밀번호 숨기기" : "비밀번호 보기"}
              aria-pressed={visible}
              disabled={busy}
              onClick={() => setVisible((value) => !value)}
            >
              {visible ? <EyeOff size={19} /> : <Eye size={19} />}
            </button>
          </div>
          {(error || notice) && (
            <p id="login-error" className="login-error" role="alert">
              {error || notice}
            </p>
          )}
          <button
            className="primary login-submit"
            type="submit"
            disabled={busy}
          >
            {busy ? (
              <>
                <LoaderCircle size={18} className="spin" />
                로그인 중
              </>
            ) : (
              <>
                로그인
                <ArrowRight size={18} />
              </>
            )}
          </button>
        </form>
        <p className="login-footnote">현업의 언어로 함께 만드는 업무 기획</p>
      </div>
    </main>
  );
}
