---
name: project-organizer
description: Use this skill whenever working on this project's file structure — creating new files, refactoring, cleaning up, deciding where code should live, handling temporary/scratch/debug files, or when the project "feels messy." Also use it any time a database credential, API key, .env file, or Supabase config is touched, to enforce security rules. Trigger this proactively before creating any new file or script, not just when the user explicitly asks to "organize" or "clean up." Covers the full stack: frontend, backend, Supabase (via MCP), Python data/update scripts, and GitHub workflow.
---

# Project Organizer

Keeps this full-stack project (frontend + backend + Supabase via MCP + Python
update scripts + GitHub) in a clean, professional, predictable structure.
Apply these rules continuously — every time you create, move, or rename a
file — not just when asked to "clean up."

## 1. Canonical folder structure

If the project doesn't already follow this layout, propose migrating to it
(don't silently restructure an established repo without confirming with the
user first). For new projects, create it from the start.

```
project-root/
├── frontend/                  # UI app (React/Vue/etc.)
│   ├── src/
│   ├── public/
│   └── ...
├── backend/                   # API server
│   ├── src/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── models/
│   │   └── middleware/
│   └── ...
├── database/
│   ├── migrations/            # numbered, sequential SQL migrations
│   ├── seeds/                 # seed/sample data, never real prod data
│   ├── schema/                # current schema snapshot (reference only)
│   └── policies/              # RLS policies, kept as version-controlled SQL
├── backend/
│   ├── data-updates/          # the recurring Python jobs that update Supabase
│   ├── one-off/                # ad-hoc/maintenance scripts, dated in filename
│   └── utils/                  # shared helper modules imported by other scripts
├── docs/
│   ├── architecture.md
│   ├── setup.md
│   └── decisions/              # short ADRs (architecture decision records)
├── .scratch/                    # 🗑️ ALL throwaway/garbage output — see §3
├── .env.example                 # template only, never real secrets
├── .gitignore
└── README.md
```

Naming rules:
- Folders: lowercase, hyphen-separated (`data-updates`, not `DataUpdates`).
- Files: lowercase, hyphen-separated, descriptive, with purpose visible from
  the name alone — `update-prices-daily.py`, not `script2.py` or `temp.py`.
- Python update scripts in `backend/data-updates/` must be named
  `update-<entity>-<frequency>.py` (e.g. `update-inventory-hourly.py`).
- One concept per file. If a file's name needs "and" to describe it, split it.

## 2. GitHub conventions

- `main` is always deployable. Work happens on `feature/<short-description>`,
  `fix/<short-description>`, or `chore/<short-description>` branches.
- Commit messages: `<type>: <imperative summary>` — types: `feat`, `fix`,
  `chore`, `docs`, `refactor`, `db`, `script`.
- Never commit: `.env`, `.scratch/`, credentials, service-role keys, raw DB
  dumps, `node_modules/`, `__pycache__/`, `venv/`. Ensure `.gitignore` covers
  all of these — check it before generating new files in sensitive folders.
- Database schema changes go through `database/migrations/` as numbered files
  (`0001_init.sql`, `0002_add_orders_table.sql`, ...), committed alongside the
  code that depends on them — never apply ad-hoc schema changes only via MCP
  without also writing the migration file.

## 3. Garbage / scratch file handling (critical)

All temporary, exploratory, debug, or intermediate files that tools/agents
generate while working — test scripts, throwaway JSON dumps, "let me check
this" files, log captures, half-finished experiments — go into:

```
.scratch/
└── YYYY-MM-DD/
    └── <short-description>.<ext>
```

Rules:
- NEVER create temporary files in `frontend/`, `backend/`, `backend/`,
  `database/`, or the project root. If a file is needed only to test/debug
  something during the current session, it goes in `.scratch/<today's date>/`.
- `.scratch/` is in `.gitignore` — nothing inside it is ever committed.
- At the end of a work session, summarize what's in `.scratch/` and ask the
  user whether to delete it. Never delete it silently, but never leave it
  scattered across the real project either.
- If a "scratch" file turns out to be useful permanently, explicitly move
  (don't copy) it into its proper home in the canonical structure above, and
  rename it according to the naming rules.

## 4. Supabase / database security (critical)

Treat every database-related action with high caution:

- **Credentials**: Supabase URL, anon key, and especially the `service_role`
  key must only ever live in `.env` (gitignored). `.env.example` lists the
  variable names with placeholder values only, e.g.
  `SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here`.
- **Never** hardcode keys/URLs in source files, scripts, notebooks, or
  committed config — including inside `.scratch/`. If a key appears in a
  file destined for `.scratch/` or any output, redact it before writing.
- **Service role key usage**: only Python scripts in `backend/data-updates/`
  that run server-side/locally should use the service role key. Frontend and
  any client-exposed code must use only the anon/public key, and must rely on
  Row Level Security (RLS).
- **RLS**: every table must have RLS enabled with explicit policies stored as
  SQL in `database/policies/`. When adding a new table via MCP, immediately
  also write/update the corresponding policy file and migration — don't leave
  the database in a state that isn't reflected in version control.
- **MCP access**: when using the Supabase MCP connection, prefer read-only or
  scoped operations for exploration. Before running destructive operations
  (DROP, TRUNCATE, DELETE without a WHERE, ALTER on production tables), state
  clearly what will happen and confirm with the user first.
- **Python update scripts**: load credentials via environment variables
  (`os environ`/`dotenv`), never via inline strings. Each script should log
  what it changed (rows affected) without logging secret values.
- **Audit trail**: significant schema or data changes should be noted in
  `docs/decisions/` with date, what changed, and why.

## 5. Workflow checklist (apply on every task)

Before finishing any task that creates or touches files, verify:

1. New files are in the correct canonical folder (§1) with a clear,
   descriptive, hyphenated name.
2. Any throwaway output went to `.scratch/YYYY-MM-DD/`, not the project tree.
3. No secrets, keys, or `.env` content appear in any file outside `.env`
   itself (including `.scratch/`).
4. `.gitignore` still covers `.env`, `.scratch/`, build artifacts, and
   language-specific caches.
5. Any DB schema change has a corresponding migration file and, if relevant,
   an updated RLS policy file.
6. If the change is non-trivial, suggest a commit message following the
   `<type>: <summary>` convention from §2.

If any of these aren't true, fix them before considering the task done.
