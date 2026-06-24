---
name: project-organizer
description: Use this skill whenever working on this project's file structure — creating new files, refactoring, cleaning up, deciding where code should live, handling temporary/scratch/debug files, or when the project "feels messy." Also use it any time a database credential, API key, .env file, or Supabase config is touched, to enforce security rules. Trigger this proactively before creating any new file or script, not just when the user explicitly asks to "organize" or "clean up." Covers the full stack: frontend (vanilla HTML/CSS/JS), backend (Python ETL), Supabase (PostgreSQL), and GitHub.
---

# Project Organizer

Keeps this full-stack project (frontend + backend + Supabase + Python ETL) in a clean, professional, predictable structure. Apply these rules continuously — every time you create, move, or rename a file — not just when asked to "clean up."

## 1. Canonical folder structure

```
project-root/
├── frontend/                   # Vanilla HTML/CSS/JS (no build tools)
│   ├── index.html              # Shell: sidebar + iframe, entry point
│   ├── pages/                  # One HTML file per page, linked via `?p=`
│   ├── js/                     # Shared JS (supabase.js only)
│   └── robots.txt | sitemap.xml
├── backend/                    # Python ETL + orchestrator
│   ├── data-updates/           # Recurring Python scripts (run_all.ps1)
│   ├── utils/                  # Shared helpers (config, scrapers)
│   ├── .venv/                  # Python virtualenv (gitignored)
│   └── mcp-supabase.ps1        # MCP server for OpenCode
├── database/
│   └── migrations/             # Timestamped SQL migration files (22 files)
├── .scratch/                   # 🗑️ Dead files moved here. Never committed.
├── .env                        # Secrets (gitignored)
├── .env.example
├── .gitignore
├── AGENTS.md                   # OpenCode project instructions
├── opencode.json               # OpenCode config
├── servidor.ps1                # Local dev server (Python http.server)
└── vercel.json                 # Vercel deployment (rootDirectory = frontend/)
```

Naming rules:
- Folders: lowercase, hyphen-separated (`data-updates`, not `DataUpdates`).
- Files: lowercase, hyphen-separated, descriptive — `atualizar_b3_cotacoes_aovivo.py`, not `script2.py`.
- Python scripts follow the repo convention: `atualizar_<fonte>_<entidade>.py` (Brazilian Portuguese).
- One concept per file. If a file's name needs "and" to describe it, split it.

Key structure facts:
- **No build step** — every page is a self-contained `.html` file in `frontend/pages/`.
- **All Python lives under `backend/`** — ETL scripts in `data-updates/`, shared libs in `utils/`.
- **Dead files go to `.scratch/`** preserving relative path (e.g. `.scratch/frontend/pages/inicio.html`).
- **`.env` at project root** is the single source of secrets for all ETL scripts and MCP.

## 2. GitHub conventions

- `main` is always deployable (auto-deploys to Vercel).
- Commit messages follow the existing style: `type: short description` — types: `feat`, `fix`, `chore`, `docs`, `refactor`, `cleanup`, `db`.
- Never commit: `.env`, `.scratch/`, credentials, `gdrive-key.json`, `.venv/`, `__pycache__/`, `*.pyc`, `*.zip`, `log.txt`. Check `.gitignore` before generating files in sensitive folders.
- Database schema changes go through `database/migrations/` as timestamped SQL files committed alongside the code that depends on them.

## 3. Garbage / scratch file handling (critical)

All temporary, exploratory, debug, or intermediate files that tools/agents generate while working — test scripts, throwaway JSON dumps, "let me check this" files, log captures, half-finished experiments — go into `.scratch/`.

Rules:
- NEVER create temporary files in `frontend/`, `backend/`, `database/`, or the project root. If a file is needed only to test/debug something during the current session, it goes in `.scratch/`.
- `.scratch/` is in `.gitignore` — nothing inside it is ever committed.
- Dead/orphan files found during cleanup should be MOVED to `.scratch/` preserving their relative path (e.g. `frontend/pages/old.html` → `.scratch/frontend/pages/old.html`).
- At the end of a work session, summarize what's in `.scratch/` and ask the user whether to delete it. Never delete it silently, but never leave it scattered across the real project either.
- If a "scratch" file turns out to be useful permanently, explicitly move (don't copy) it into its proper home in the canonical structure above, and rename it according to the naming rules.

## 4. Supabase / database security (critical)

- **Credentials**: Supabase URL, anon key, and service_role key must only ever live in `.env` (gitignored). `.env.example` lists variable names with placeholder values only.
- **Never** hardcode keys/URLs in source files — except the **publishable anon key** (`sb_publishable_ekx47MbcOg-C1uoAPJnKWg_c9t9ndQR`) which is hardcoded in multiple frontend files as `H`/`HEADERS`/`apikey` (this is the client-side key, acceptable for browser use).
- **Service role key usage**: only Python scripts in `backend/data-updates/` should use the service role key. Frontend uses only the publishable anon key with RLS.
- **RLS**: all user tables (`user_ativos`, `user_profiles`, `user_setup`) have RLS by `auth.uid() = user_id`. Public data tables (CVM, B3, FNET) are anon read-only.
- **Python update scripts**: load credentials via environment variables (`os.environ`/`.env` file), never via inline strings. Each script should log what it changed (rows affected) without logging secret values.

## 5. Workflow checklist (apply on every task)

Before finishing any task that creates or touches files, verify:

1. New files are in the correct canonical folder (§1) with a clear, descriptive, hyphenated name matching the repo convention.
2. Any throwaway output went to `.scratch/`, not the project tree.
3. No secrets or `.env` content appear in any file outside `.env` itself (including `.scratch/`).
4. `.gitignore` still covers `.scratch/`, `.venv/`, `__pycache__/`, `*.pyc`, `*.zip`, `log.txt`, `gdrive-key.json`.
5. Any DB schema change has a corresponding migration file in `database/migrations/`.
6. If the change is non-trivial, suggest a commit message following the existing repo style.

If any of these aren't true, fix them before considering the task done.
