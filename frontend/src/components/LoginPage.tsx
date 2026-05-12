import { useState, FormEvent } from "react";
import { login, LoginError } from "../auth";
import { useT } from "../i18n/LocaleProvider";

export default function LoginPage({ onSuccess }: { onSuccess: () => void }) {
  const t = useT();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  // Default ON — the user's intent here is "don't log me out every day"
  // and the cookie still expires after 90d so this isn't permanent state.
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password, remember);
      onSuccess();
    } catch (err) {
      if (err instanceof LoginError) {
        if (err.status === 429 && err.retryAfter) {
          const mins = Math.max(1, Math.ceil(err.retryAfter / 60));
          setError(`Too many attempts. Try again in ${mins} min.`);
        } else {
          setError(err.message);
        }
      } else {
        setError("Login failed");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-base px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm rounded-lg border border-surface-border bg-surface-card p-6 shadow-card space-y-4"
      >
        <div>
          <h1 className="text-lg font-semibold tracking-wide">{t("login.title")}</h1>
          <p className="text-xs text-slate-500 mt-1">{t("login.tagline")}</p>
        </div>
        <label className="block">
          <span className="text-[11px] uppercase tracking-widest text-slate-500">{t("login.username")}</span>
          <input
            type="text"
            autoFocus
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mt-1 w-full rounded-md border border-surface-border bg-surface-base px-3 py-2 text-sm focus:outline-none focus:border-slate-400"
            required
          />
        </label>
        <label className="block">
          <span className="text-[11px] uppercase tracking-widest text-slate-500">{t("login.password")}</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-md border border-surface-border bg-surface-base px-3 py-2 text-sm focus:outline-none focus:border-slate-400"
            required
          />
        </label>
        <label className="flex items-center gap-2 text-xs text-slate-300 select-none cursor-pointer">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
            className="accent-brand h-4 w-4 cursor-pointer"
          />
          <span>{t("login.remember")}</span>
        </label>
        {error && (
          <p className="text-xs text-red-400" role="alert">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-slate-200 text-slate-900 text-sm font-medium py-2 hover:bg-white disabled:opacity-50"
        >
          {submitting ? t("login.submitting") : t("login.submit")}
        </button>
      </form>
    </div>
  );
}
