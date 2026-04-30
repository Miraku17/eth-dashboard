# Auth setup

Etherscope ships a single-account session login that gates both the dashboard
UI and every protected API endpoint. `/api/health` is intentionally public so
uptime checks and the topbar status indicator continue to work.

## Generate a password hash

```bash
cd backend
python -m app.scripts.hash_password
```

Enter the password twice. The script prints an argon2id hash. Paste it into
`.env`:

```env
AUTH_USERNAME=admin
AUTH_PASSWORD_HASH=$argon2id$v=19$m=65536,t=3,p=4$...
```

## Required env

| Var | Required | Default | Notes |
| --- | --- | --- | --- |
| `AUTH_USERNAME` | yes | – | Login name. |
| `AUTH_PASSWORD_HASH` | yes | – | argon2id hash from the CLI. |
| `SESSION_COOKIE_SECURE` | no | `true` | Set `false` only on local http. |
| `CORS_ORIGINS` | yes (prod) | dev defaults | Explicit list; `*` is rejected. |

If `AUTH_USERNAME` or `AUTH_PASSWORD_HASH` is unset, `/api/auth/login`
responds with `503 auth not configured on this server` and the dashboard
cannot be entered.

## Rotate / reset the password

1. Re-run the hash CLI with the new password.
2. Replace `AUTH_PASSWORD_HASH` in `.env` and restart the api container.
3. Existing sessions remain valid until their TTL (24h) expires. To force
   immediate logout, flush the relevant Redis keys:

   ```bash
   docker compose exec redis redis-cli --scan --pattern "session:*" | xargs -r docker compose exec -T redis redis-cli DEL
   ```

## Session lifetime

24h fixed TTL, no sliding expiry, no "remember me." After 24h the user is
sent back to the login page.

## Rate limit

10 failed logins from a single IP within 15 minutes returns `429 Too Many
Requests` with `Retry-After`. The window resets when the Redis key expires.
