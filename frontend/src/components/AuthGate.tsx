import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { AUTH_EXPIRED_EVENT } from "../api";
import { me, type AuthUser } from "../auth";
import LoginPage from "./LoginPage";

const AuthContext = createContext<AuthUser | null>(null);

export function useAuthUser(): AuthUser | null {
  return useContext(AuthContext);
}

type State =
  | { kind: "loading" }
  | { kind: "anon" }
  | { kind: "authed"; user: AuthUser };

export default function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  async function refresh() {
    setState({ kind: "loading" });
    try {
      const u = await me();
      setState(u ? { kind: "authed", user: u } : { kind: "anon" });
    } catch {
      setState({ kind: "anon" });
    }
  }

  useEffect(() => {
    void refresh();
    function onExpired() {
      setState({ kind: "anon" });
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, []);

  if (state.kind === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center text-xs text-slate-500">
        Loading…
      </div>
    );
  }
  if (state.kind === "anon") {
    return <LoginPage onSuccess={refresh} />;
  }
  return <AuthContext.Provider value={state.user}>{children}</AuthContext.Provider>;
}
