import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth";

export default function Login() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await login(email, password);
    } catch (e: any) {
      setErr(e.message || t("auth.loginFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <form onSubmit={onSubmit}>
        <div className="login-header">
          <img src="/buteo-eagle-logo-lg.svg" alt="Buteo Logo" className="login-logo" />
          <h1 className="login-title">Buteo</h1>
          <p className="login-subtitle">
            <span>{t("auth.subtitle1")}</span>
            <span>{t("auth.subtitle2")}</span>
          </p>
        </div>
        {err && <div className="err">{err}</div>}
        <input
          type="email"
          placeholder={t("auth.email")}
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <input
          type="password"
          placeholder={t("auth.password")}
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <button disabled={busy}>{busy ? "..." : t("auth.loginButton")}</button>
      </form>
    </div>
  );
}
