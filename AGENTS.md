# Invest Ranking

## Tech Stack
- **DB**: Supabase (PostgreSQL) — project `oaqmnaekrpukwmrxjtud`
- **Frontend**: Vanilla HTML/CSS/JS (no build tools, no framework)
- **ETL**: Python scripts in `scripts/data-updates/`
- **Charts**: Canvas 2D API (Scanner/fii page), D3.js v7 CDN (treemap on ranking page)
- **Auth**: Custom `ir_auth` key in localStorage — bypasses Supabase client's isolated storage

## Serve & Deploy
- **Dev**: `.\servidor.ps1` → http://localhost:8080 (Python http.server on `frontend/`). NEVER use `file://`
- **Prod**: Vercel auto-deploy from `main`. Vercel project rootDirectory = `frontend/` (set in dashboard, not in repo). `vercel.json` rewrites all routes to `/index.html`
- **Python ETL**: `scripts/.venv/Scripts/python.exe` — system Python lacks deps

## Routing
- `frontend/index.html` is the shell: sidebar + iframe. `initFromQuery()` reads `?p=` param, calls `abrir()` to set iframe src. Title updates via `abrir()`
- All pages at `frontend/pages/`. Accessed as `/pages/foo.html` via Vercel
- Protected pages (`meus-ativos`, `minha-conta`): inline `obterSessao()` reads `ir_auth` from localStorage, redirects `window.top.location.href='/?p=login'` if missing

## Auth Flow
- **`signIn()`** in `frontend/js/supabase.js` calls Supabase SDK, saves session under `ir_auth` key
- **`getSession()`** reads from `ir_auth` — NOT from Supabase client (avoids iframe storage isolation)
- **CRUD**: `_api()` helper makes raw REST calls with token from `ir_auth` — bypasses Supabase JS client entirely. Used by `listarAtivos`, `upsertProfile`, `listarSetups`, etc.
- Supabase JS client (`@supabase/supabase-js@2` loaded via CDN in index.html) used ONLY for: `signIn`, `signUp`, `signOut`, `resetPasswordForEmail`, `updateUser`
- `updatePassword`: re-auths via RPC `login`, then calls Supabase `updateUser`
- Email confirmation disabled (`mailer_autoconfirm: true`). Users active immediately on signup
- Password recovery via `resetSenha()` → Supabase email → `pages/recuperar-senha.html`
- `_api(path)` — path param is raw PostgREST path (e.g. `user_ativos?select=*&user_id=eq.${uid}`)

## Database — User Tables (RLS: `auth.uid() = user_id`)
- `user_ativos` — asset portfolio
- `user_profiles` — name, estado, cidade
- `user_setup` — saved filter/weight preferences
- `"00.log_atualizacao"` — ETL run log (table name has a dot; `run_all.ps1` accesses as `00.log_atualizacao` directly)
- `fn_deletar_conta()` — SECURITY DEFINER, deletes user + all data
- All public data tables (CVM, B3, FNET) are **read-only for anon** — ETL uses service_role key (bypasses RLS)
- `database/migrations/` — 22 timestamped SQL migration files (e.g. `20260613000001_create_fiagro_tables.sql`)
- Views `00_Master` (columns: Ticker, Classe, CNPJ) and `vw_b3_tickers` exist in Supabase but have **no migration file** in repo — created manually in dashboard

## ETL Orchestration — `scripts/data-updates/run_all.ps1`
- Canonical runner. Manages scheduling via `.run_state.json`
- Python: `scripts/.venv/Scripts/python.exe`
- `.env` at project root — loaded by `run_all.ps1` (Get-Content split on `=`) and by ETL scripts (manual file read)
- 5 required env vars in `.env.example`: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_PROJECT_REF`, `SUPABASE_ACCESS_TOKEN`

| Group | Scripts | When |
|---|---|---|
| Always | `b3_cotacoes_aovivo`, `fnet_dados` | Every run (10min via Task Scheduler) |
| 1h interval | `youtube_videos`, `gdrive_cotahist` | Skip if <1h since last |
| 2h interval | `cvm_fii_mensal`, `cvm_fiagro_mensal`, `cvm_cadastral`, `statusinvest_acoes`, `statusinvest_dividendos` | Skip if <2h since last |

- `fnet_dados` always calls `fnet_rendimentos` at the end (inline import in the same process)
- Post-run RPCs: `fn_atualizar_minigrafico`, `fn_refresh_ranking_fiis`, `fn_limpar_b3_historico`
- Task Scheduler runs every 30min (`\InvestRanking-Update` trigger ONLOGON). Playwright scripts (`statusinvest_acoes`) skipped when detected as Task Scheduler run (captcha). `gdrive_cotahist` substituiu o captcha por Google Drive
- `.run_state.json` prevents re-running CVM/StatusInvest scripts <2h — delete to force re-run
- **CRITICAL**: `atualizar_fnet_dados.py` strips `tipo`, `rendimento`, `data_com`, `data_pagamento` before upsert — otherwise overwrites values from `fnet_rendimentos.py`

## PostgREST API Quirks
- `like` uses `*` wildcard: `like.*Relat*rio*`
- `limit` defaults to 1000 — paginate with `limit=N&offset=M` + `Prefer: count=exact`. `apiAll()` in `app.js` handles this automatically
- `tipo=neq.` means `tipo != ''`
- Table names with dots (e.g. `"00.log_atualizacao"`) — use directly as path (`00.log_atualizacao`) which works despite PostgREST dot ambiguity
- Client key `sb_publishable_ekx47MbcOg-C1uoAPJnKWg_c9t9ndQR` hardcoded in multiple files as `HEADERS`/`apikey`
- Intermittent 500 errors with `like` + `order` on `fnet_tudo`

## Database Schema Tips
- `"Ranking_FIIs"` — materialized view, refreshed post-ETL via `fn_refresh_ranking_fiis()`. Reads live prices from `b3_cotacoes_aovivo` (not a bridge table). Contains `historico_cotacoes` (sparkline, 1y of closes), `historico_dividendos` (last 12 dividends), `maturidade_lci` (`A|B|C` format from liquidity/cotistas/age)
- `00_fundos_master` — curated FII list from manual Google Sheet (`atualizar_00_fundos_master.py` downloads CSV). `00_Master` is a VIEW (created outside migrations) joining this with `00_Master_cnpj`
- `cvm_fii_*` tables have versioned rows — always `ORDER BY data_referencia DESC, versao DESC LIMIT 1`
- CVM `percentual_*` fields are decimals (0–1), multiply by 100 for display
- CVM date columns: `data_referencia` for period reference, `data_informacao_numero_cotistas` for cotistas snapshot date
- DY 12m in Ranking_FIIs comes from `status_dividendos` (last 12 entries per ticker), NOT from `fnet_tudo`
- Requirements (`requirements.txt`): `supabase>=2.0.0`, `httpx>=0.27.0`, `playwright>=1.60.0`, `pytesseract>=0.3.13`, `pillow>=12.2.0`

## OpenCode Config
- `opencode.json` at root — MCP Supabase enabled via `scripts/mcp-supabase.ps1` (loads `.env` then runs `@supabase/mcp-server-supabase`). `test`/`lint`/`build` commands are generic templates only — no actual test/lint/build framework exists
- Skill `invest-ranking-analyst` at `.opencode/skills/invest-ranking-analyst/SKILL.md` — loaded for financial/data tasks. Contains deep domain guidance on FII metrics, CVM/B3/FNET data sources, and analyst reasoning patterns
- `.opencode/rules/supabase.md` contradicts actual codebase (says "Use Supabase JS client for all DB ops" — real code uses `_api()` REST calls). Prefer `_api()` pattern from this file
