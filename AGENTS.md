# Invest Ranking

## Tech Stack
- **DB**: Supabase (PostgreSQL) — `oaqmnaekrpukwmrxjtud`
- **Frontend**: Vanilla HTML/CSS/JS (no build tools)
- **ETL**: Python scripts in `scripts/data-updates/`
- **Charts**: Canvas 2D API (Scanner page), D3.js v7 CDN (treemap on cotacoes page)
- **Auth**: Custom `ir_auth` key in localStorage (bypasses Supabase client's internal storage)

## Critical Setup
- **Serve**: `.\servidor.ps1` → http://localhost:8080 (Python http.server on `frontend/`). NEVER open `frontend/index.html` via `file://`
- **Prod domain**: `https://www.investranking.com.br` (Vercel auto-deploy from GitHub `main`)
- **Python**: `scripts/.venv/Scripts/python.exe` — use directly; system Python won't have deps
- **`.env.example`** lists all 5 required vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_PROJECT_REF`, `SUPABASE_ACCESS_TOKEN`
- **`.env` at project root** — loaded by `run_all.ps1` (`Get-Content` split on `=`) and by ETL scripts (manual `open().read().split("=")`)
- **No test/lint/build framework** exists — `opencode.json` commands are generic templates only
- **`vercel.json`** at repo root rewrites `/` → `pages/inicio.html`, `/?p=*` → `app.html` (shell), and serves static files from `frontend/`

## Routing & Pages
- `frontend/index.html` (shell) has sidebar + iframe. All pages render inside the iframe
- `pages/inicio.html` is the landing page / dashboard (served at root URL)
- `pages/ranking-fiis.html` — ranking table with sliders, maturidade LCI, dividend bar chart
- `pages/ranking.html` — cotacoes page with list view + D3.js treemap toggle (.mode-treemap)
- `pages/meus-ativos.html` / `pages/minha-conta.html` / `pages/recuperar-senha.html` — auth-gated pages (redirect via `window.top.location.href='/?p=login'`)
- Protected pages use `obterSessao()` which reads `ir_auth` from localStorage directly
- Sidebar: collapsible on desktop (icon-only mode), opens via hamburger in brand area, overlay closes on outside click

## Database — User Tables
- `user_ativos` — user's asset portfolio (RLS: `auth.uid() = user_id`)
- `user_profiles` — name, estado, cidade per user (RLS: `auth.uid() = user_id`)
- `user_setup` — saved filter/weight preferences (RLS: `auth.uid() = user_id`)
- `log_atualizacao` — VIEW on `"00.log_atualizacao"` (table name has dot, use view for REST API)

## Auth Flow
- **Login**: `signIn()` in `supabase.js` calls Supabase SDK, then saves session under `ir_auth` key in localStorage
- **Session check**: `getSession()` reads from `ir_auth`, NOT from Supabase client (avoids iframe storage isolation issues)
- **CRUD operations**: `_api()` helper makes raw REST calls with token from `ir_auth` — bypasses Supabase JS client entirely. Used by all user data functions (`listarAtivos`, `upsertProfile`, `listarSetups`, etc.)
- **Email confirmation**: disabled (`mailer_autoconfirm: true`). Users are active immediately on signup
- **Password recovery**: `resetSenha()` sends email via Supabase, redirects to `pages/recuperar-senha.html`
- **Email confirmation disabled** in Supabase Auth settings

## Supabase JS Client Usage
- Used ONLY for: `signIn`, `signUp`, `signOut`, `resetPasswordForEmail`, `updateUser`
- NOT used for data queries — those go through `_api()` or raw `fetch` with publishable key
- The client in iframes has session isolation issues — always use `_api()` for CRUD from iframe pages

## ETL Orchestration
`scripts/data-updates/run_all.ps1` is the **canonical runner**. Manages scheduling via `.run_state.json`:

| Group | Scripts | When |
|---|---|---|
| **Always** | `b3_cotacoes_aovivo`, `fnet_dados`, `youtube_videos` | Every run |
| **2h interval** | `cvm_fii_mensal`, `cvm_fiagro_mensal`, `cvm_cadastral`, `statusinvest_acoes`, `statusinvest_dividendos` | Skip if <2h since last |
| **24h interval** | `b3_cotahist` | Skip if <24h; also skipped from Task Scheduler (captcha) |

- `fnet_dados` always calls `fnet_rendimentos` at the end
- Post-run RPCs: `fn_atualizar_minigrafico`, `fn_refresh_ranking_fiis`, `fn_limpar_b3_historico`
- `fnet_dados` now fetches only the first page per CNPJ (base is complete, just checking for new docs)
- Task Scheduler runs every 30min; Playwright scripts (`b3_cotahist`, `statusinvest_acoes`) skipped when detected as Task Scheduler run (`$captchaScripts`)

## PostgREST API Quirks
- `like` uses `*` wildcard: `like.*Relat*rio*`
- `limit` defaults to 1000 — paginate with `limit=N&offset=M` + `Prefer: count=exact`
- `tipo=neq.` means `tipo != ''`
- Table names with dots (e.g. `00.log_atualizacao`) are interpreted as `schema.table` by PostgREST — use a VIEW without dot or quote with `%22name%22`
- Client key `sb_publishable_ekx47MbcOg-C1uoAPJnKWg_c9t9ndQR` is hardcoded in pages as `H`/`HEADERS`

## Database Schema
- `"Ranking_FIIs"` — materialized view refreshed post-ETL. Includes `historico_cotacoes` (price sparkline data) and `historico_dividendos` (last 12 dividend values), `maturidade_lci` (A|B|C classification)
- `00_fundos_master` — curated FII list (manual Google Sheet). `00_Master` is a VIEW on it
- `cvm_fii_*` tables have versioned rows — always `ORDER BY data_referencia DESC, versao DESC LIMIT 1`
- CVM `percentual_*` fields are decimals (0–1), multiply by 100 for display
- All user tables (`user_ativos`, `user_profiles`, `user_setup`) have RLS: `auth.uid() = user_id`
- `fn_deletar_conta()` — SECURITY DEFINER function that deletes user + all associated data

## RLS Security
- All public data tables (CVM, B3, FNET, etc.) are **read-only for anon** — all permissive anon INSERT/UPDATE/DELETE policies have been removed. ETL uses service_role key which bypasses RLS entirely.
- User tables have strict RLS: each user can only see/modify their own rows

## SEO
- `frontend/sitemap.xml` — lists 5 URLs with priority
- `frontend/robots.txt` — allows all crawlers, points to sitemap
- Each page has `<title>` and `<meta name="description">` with canonical URL
- Dynamic title updates via `abrir()` function based on `?p=` parameter
- Schema.org FAQPage markup on landing page
- Content is loaded in iframes — Google indexes the landing page (`inicio.html`), not the iframed tools

## ETL Pitfalls
- **CRITICAL**: `atualizar_fnet_dados.py` strips `tipo`, `rendimento`, `data_com`, `data_pagamento` before upsert — otherwise overwrites values extracted by `fnet_rendimentos.py`
- CVM date columns use `data_referencia` (NOT `data_informacao`)
- Intermittent 500 errors with `like` + `order` on `fnet_tudo`
- `.run_state.json` prevents re-running CVM/StatusInvest scripts more than once per 2h — delete to force re-run

## Frontend Conventions
- Font Awesome 6.5.0 CDN for icons (`https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css`)
- Inter font from Google Fonts used on landing page
- All pages are self-contained (inline CSS/JS) except `pages/fii.html` which loads `../js/app.js` + `../css/style.css`
- Scanner: `pages/analise-fii.html` (default ticker `GARE11`)
- Treemap on `pages/ranking.html` uses D3.js v7 CDN, toggled via `.mode-treemap` body class
- Weight/filter values auto-save to localStorage key `rankingSetup` on every `render()` call
- `await _supabase.auth.setSession()` used to restore session in iframe when needed
