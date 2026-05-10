#!/usr/bin/env bash
# Production deploy steps, executed on the VPS *after* the workflow has already
# done `git fetch && git reset --hard origin/main`. Lives in the repo (rather
# than inside .github/workflows/deploy.yml) so:
#
#   1. Errors report a line number we can actually grep for in this file.
#   2. The YAML stays small (<20 lines of inline shell), avoiding drone-ssh's
#      surprising line-counting when it prepends `export VAR=...` for every
#      entry in `envs:` -- a multi-line EXTRA_ENV secret used to shift the
#      transmitted script's line numbers, which made bash syntax errors
#      impossible to map back to a source location.
#   3. Logic is unit-testable with `bash -n scripts/deploy.sh` locally and
#      diffable in PRs.
#
# Required env vars (passed from the workflow):
#   DEPLOY_PATH          -- absolute path to the repo checkout on the VPS
#   FORCE                -- "true" / "false" (workflow_dispatch full-rebuild flag)
#   BACKEND, FRONTEND, MIGRATIONS, COMPOSE, CADDY  -- "true" / "false" path filters
# Optional:
#   EXTRA_ENV            -- multi-line `KEY=VALUE` block (see deploy.yml header)

set -euo pipefail

cd "$DEPLOY_PATH"

# Compose CLI prefix used for every command. The prod override swaps the Vite
# dev server for the nginx static build and drops the dev bind mount + the
# anonymous node_modules volume.
DC="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

# ---- Sync EXTRA_ENV secret into the VPS .env (idempotent) ----
# Append any KEY= line from EXTRA_ENV that isn't already present in .env.
# Never overwrites existing keys. Skips comments and blank lines. Touches
# .env only if something was actually added, so we can decide downstream
# whether to force-recreate worker+api to pick up the new env.
ENV_CHANGED=false
if [ -n "${EXTRA_ENV:-}" ]; then
  echo "-> syncing EXTRA_ENV secret into .env"
  touch .env
  ADDED_COUNT=0
  EXTRA_ENV_FILE=$(mktemp)
  printf '%s\n' "$EXTRA_ENV" > "$EXTRA_ENV_FILE"
  set +e  # grep -q legitimately returns 1 when key is absent
  while IFS= read -r raw_line; do
    line=$(printf '%s' "$raw_line" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    [ -z "$line" ] && continue
    case "$line" in
      \#*) continue ;;
    esac
    key="${line%%=*}"
    if [ "$key" = "$line" ]; then
      echo "  WARN: skipping malformed EXTRA_ENV line (no '='): $line"
      continue
    fi
    if grep -q "^${key}=" .env; then
      continue
    fi
    printf '%s\n' "$line" >> .env
    echo "  + appended $key"
    ADDED_COUNT=$((ADDED_COUNT + 1))
  done < "$EXTRA_ENV_FILE"
  set -e
  rm -f "$EXTRA_ENV_FILE"
  if [ "$ADDED_COUNT" -gt 0 ]; then
    ENV_CHANGED=true
  else
    echo "  (nothing new -- VPS .env already has every EXTRA_ENV key)"
  fi
fi

REBUILD_BACKEND=false
REBUILD_FRONTEND=false
RUN_MIGRATIONS=false
FULL=false

if [ "${FORCE:-false}" = "true" ] || [ "${COMPOSE:-false}" = "true" ]; then
  FULL=true
fi
if [ "$FULL" = "true" ] || [ "${BACKEND:-false}" = "true" ]; then
  REBUILD_BACKEND=true
fi
if [ "$FULL" = "true" ] || [ "${FRONTEND:-false}" = "true" ]; then
  REBUILD_FRONTEND=true
fi
if [ "$FULL" = "true" ] || [ "${MIGRATIONS:-false}" = "true" ]; then
  RUN_MIGRATIONS=true
fi

echo "-> plan: backend=$REBUILD_BACKEND frontend=$REBUILD_FRONTEND migrations=$RUN_MIGRATIONS full=$FULL"

if [ "$FULL" = "true" ]; then
  # rm -sfv on frontend wipes its anonymous volume so a fresh node_modules
  # from the new image can populate the container.
  $DC rm -sfv frontend || true
  # `--profile mantle` opts in the mantle_realtime sibling listener so it
  # comes up on every full deploy alongside the rest of the stack. The
  # listener is still no-op when MANTLE_WS_URL is unset.
  $DC --profile mantle up -d --build
else
  if [ "$REBUILD_BACKEND" = "true" ]; then
    $DC build api worker realtime mantle_realtime
    $DC --profile mantle up -d api worker realtime mantle_realtime
  fi
  if [ "$REBUILD_FRONTEND" = "true" ]; then
    $DC rm -sfv frontend || true
    $DC build frontend
    $DC up -d frontend
  fi
  if [ "${CADDY:-false}" = "true" ]; then
    $DC restart caddy
  fi
fi

if [ "$RUN_MIGRATIONS" = "true" ]; then
  echo "-> alembic upgrade head"
  $DC exec -T api alembic upgrade head
fi

# If we appended any new keys to .env BUT didn't already do a full rebuild
# (which would have force-recreated everything), recreate worker + api
# specifically so they re-read .env. A plain `up -d` is a no-op when the
# image hash hasn't changed, so we use --force-recreate.
if [ "$ENV_CHANGED" = "true" ] && [ "$FULL" = "false" ]; then
  echo "-> env changed: force-recreating worker + api"
  $DC up -d --force-recreate worker api
fi

echo "-> post-deploy health"
sleep 3
curl -fsS http://127.0.0.1:8000/api/health | head -c 400 || true
echo
$DC ps
