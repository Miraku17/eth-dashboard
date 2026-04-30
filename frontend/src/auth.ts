const RAW_BASE = import.meta.env.VITE_API_URL ?? "";
const API_BASE = RAW_BASE.replace(/\/+$/, "");

function url(path: string): string {
  return `${API_BASE}${path}`;
}

export type AuthUser = { username: string };

export class LoginError extends Error {
  constructor(message: string, readonly status: number, readonly retryAfter?: number) {
    super(message);
  }
}

export async function login(username: string, password: string): Promise<AuthUser> {
  const r = await fetch(url("/api/auth/login"), {
    method: "POST",
    credentials: "include",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (r.status === 429) {
    const retry = Number(r.headers.get("Retry-After") ?? 60);
    throw new LoginError("Too many attempts", 429, retry);
  }
  if (r.status === 401) {
    throw new LoginError("Invalid credentials", 401);
  }
  if (r.status === 503) {
    throw new LoginError("Auth not configured on this server", 503);
  }
  if (!r.ok) {
    throw new LoginError(`Login failed (${r.status})`, r.status);
  }
  return r.json();
}

export async function logout(): Promise<void> {
  await fetch(url("/api/auth/logout"), {
    method: "POST",
    credentials: "include",
  });
}

export async function me(): Promise<AuthUser | null> {
  const r = await fetch(url("/api/auth/me"), {
    credentials: "include",
  });
  if (r.status === 401) return null;
  if (!r.ok) throw new Error(`auth/me ${r.status}`);
  return r.json();
}
