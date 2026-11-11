# Lextari API Deployment

---

## Local Development

Prerequisites: Python 3.13, uv 0.13.4+, and Node.js 22+ (required by
`pywrangler`). If `pywrangler` reports that uv is too old, run `uv self update`.

```bash
# 1. Clone and setup
cd ~/Personal/Dev/lextari-api
mise install
uv sync

# 2. Configure
cp .dev.vars.example .dev.vars
# Edit .dev.vars with your TB_API_KEY, SUPABASE_URL, etc.

# 3. Run
uv run pywrangler dev

# 4. Test
open http://localhost:8787/docs   # Swagger UI (debug mode only)
DEBUG=true TB_API_KEY=test SUPABASE_URL=https://test.supabase.co uv run pytest
```

For a plain FastAPI process (local fallback without the Workers runtime):

```bash
cp .env.example .env
uv run uvicorn app.main:app --app-dir src --reload --port 8000
```

---

## Pre-commit Hooks

```bash
# Install (one-time)
pre-commit install --hook-type pre-commit --hook-type commit-msg

# Run manually on all files
pre-commit run --all-files

# Run on staged files only
git add .
git commit -m "feat: your message"
# Hooks run automatically
```

**Hooks:**
1. ruff — lint + auto-fix staged .py files
2. ruff-format — format staged .py files
3. conventional-pre-commit — enforce feat/fix/chore format
4. trailing-whitespace, end-of-file-fixer, check-yaml, etc.

---

## Docker

Docker is only used to run ThingsBoard locally. The API itself runs on the
Workers runtime (or `uvicorn` for a plain local fallback).

```bash
# Run ThingsBoard + PostgreSQL
docker compose up -d

# Check logs
docker compose logs -f thingsboard

# Stop
docker compose down
```

---

## Mise (Tool Versions)

```bash
# Check current
mise current

# Install Python 3.13 + Node 22 from mise.toml
mise install

# Activate in shell (add to ~/.zshrc)
eval "$(mise activate zsh)"
```

---

## Cloudflare Workers (CI/CD)

The Worker is named **`lextari-api`** and uses the D1 database **`lextari`**.

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `.github/workflows/ci.yml` | Push to `main`, pull requests | `ruff check`, `ruff format --check`, `mypy src/app`, `pytest`, Worker dry-run build |
| `.github/workflows/deploy.yml` | After CI succeeds on `main`, or manual dispatch | Applies D1 migrations, then `pywrangler deploy` |

### Required GitHub secrets

| Secret | Purpose |
|--------|---------|
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token with Workers Scripts:Edit and D1:Edit |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |

### One-time setup

```bash
# 1. Create the D1 database
npx wrangler d1 create lextari

# 2. Copy the returned database_id into wrangler.jsonc

# 3. Generate the Worker dependency lock and set runtime secrets
uv sync
uv run pywrangler sync          # writes pylock.toml; commit it
uv run pywrangler secret put TB_API_KEY

# 4. Add CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID as GitHub repository secrets
```

Update `TB_URL` in `wrangler.jsonc` to the deployed ThingsBoard URL. Use a
least-privilege API token scoped to Workers Scripts and D1.

### Local Workers development

```bash
uv sync
cp .dev.vars.example .dev.vars
uv run pywrangler dev
```

The Worker entrypoint is `src/worker.py`. Python Workers upload every `.py`
file under the entrypoint's directory, so `src/app/` is bundled automatically
while the repository-root virtualenvs and tests stay out of the upload.
`python_modules/` is added separately by `pywrangler sync`.

---

## Environment Variables

See `docs/ENVIRONMENT.md` for full reference. Key vars:

| Variable | Required | Description |
|----------|----------|-------------|
| TB_API_KEY | Yes | ThingsBoard API key (Worker secret) |
| TB_URL | Yes | ThingsBoard base URL |
| SUPABASE_URL | Yes (prod) | Supabase project URL |
| SUPABASE_JWKS_URL | No | Override JWKS endpoint |
| DEBUG | No | Enables Swagger UI |
| CORS_ORIGINS | No | Comma-separated allowed origins |
| WS_POLL_INTERVAL | No | Seconds between TB polls (default 5) |
