# Invest Ranking

## Tech Stack
- **DB**: Supabase (PostgreSQL) — `oaqmnaekrpukwmrxjtud`
- **Frontend**: Vanilla HTML/CSS/JS (no build tools)
- **ETL**: Python scripts in `scripts/data-updates/`
- **Charts**: Canvas 2D API (Scanner page), D3.js v7 CDN (Mosaico treemap)

## Critical Setup
- **Serve**: `.\servidor.ps1` → http://localhost:8080 (NUNCA abrir `frontend/index.html` via `file://`)
- **Python**: `scripts/.venv/Scripts/python.exe` — use directly (not system Python)
- **Deps**: `pip install playwright && playwright install chromium` (required for Playwright-based scrapers)
- **Client key**: `sb_publishable_ekx47MbcOg-C1uoAPJnKWg_c9t9ndQR`
- **`.env.example`** at root lists all 5 required vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_PROJECT_REF`, `SUPABASE_ACCESS_TOKEN`

## ETL Orchestration
`run_all.ps1` at `scripts/data-updates/` is the **canonical runner** (the `.bat` files at the same location are deprecated). Handles scheduling with `.run_state.json`:

| Group | Scripts | When |
|---|---|---|
| **Always** | `b3_cotacoes_aovivo`, `fnet_dados`, `youtube_videos` | Every run |
| **2h interval** | `cvm_fii_mensal`, `cvm_fiagro_mensal`, `cvm_cadastral`, `statusinvest_acoes`, `statusinvest_dividendos` | Skip if <2h since last |
| **24h interval** | `b3_cotahist` | Skip if <24h since last; also skipped when running from Task Scheduler (captcha) |

`fnet_dados` always calls `fnet_rendimentos` at the end.

Post-run RPCs (always called): `fn_atualizar_minigrafico`, `fn_refresh_ranking_fiis` (materialized view), `fn_limpar_b3_historico`.

### Playwright scripts (may require captcha)
- `atualizar_b3_cotahist.py` / `atualizar_statusinvest_acoes.py` / `atualizar_statusinvest_dividendos.py` — use `headless=False`. First two are explicitly skipped by `run_all.ps1` when running from Task Scheduler (`$captchaScripts` list).

### Task Scheduler
- Config: `scripts/data-updates/setup_task.ps1` — runs `run_all.ps1` at logon with 30min repetition
- `scripts/data-updates/executar_atualizacao.bat` — convenience double-click wrapper for manual runs
- `fix_repetition.ps1` / `fix_task.ps1` — utility fix scripts

## Environment
- **`.env` at project root** — loaded by `run_all.ps1` (`Get-Content` split on `=`) and by ETL scripts (inline `open().read().split("=")` or `os.environ["VAR"]`)
- **`utils.scraper.config.Config`** — dataclass reading `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` from env; import via `from utils.scraper.config import config`
- **`utils.scraper._fnet_base`** — shared FNET helpers (`_parse_date`, `_cookies_from_fnet`)
- **MCP** (`scripts/mcp-supabase.ps1`): reads `SUPABASE_*` vars from `.env` and pipes into `npx @supabase/mcp-server-supabase`

## Database Migrations
- SQL files in `database/migrations/` — apply manually via Supabase dashboard or `supabase_apply_migration` tool
- Named with timestamp prefix (`20260613000001_create_*`)

## Database
**View vs Table**: Scripts query the view `00_Master` (columns: `Ticker`, `Classe`, `CNPJ`), while the actual table is `00_fundos_master` (`ticker`, `segmento`, `tipo`, `cnpj`). `"Ranking_FIIs"` is a **materialized view** refreshed by `run_all.ps1` via `fn_refresh_ranking_fiis`.

Key tables:
- `00_fundos_master` — curated FII list (ticker, cnpj, segmento, tipo)
- `fundos_map` — CNPJ ↔ ticker bridge (connects all other tables)
- `fnet_tudo` — FNET documents + income fields (`data_com`, `data_pagamento`, `tipo`, `rendimento`)
- `fnet_rendimentos` — parsed income declarations (source for DY calculation)
- `b3_cotacoes` (aka `b3_cotacoes_historico`) — daily OHLCV (PK: ticker+data)
- `b3_cotacoes_aovivo` — intraday snapshot (PK: codigo_instrumento+data_referencia)
- `cotacoes_tempo_real` — latest post-market price per fund
- `cvm_fii_geral` / `cvm_fii_complemento` / `cvm_fii_ativo_passivo` — monthly reports
- `cvm_fiagro_geral` — Fiagro equivalent of FII monthly reports
- `status_dividendos` — unified dividends (tipo_ativo: FIIs, Fiagro, Fiinfra, Acoes)
- `status_acoes` — stock indicators (P/L, DY, ROE, etc.)
- `youtube_videos` — YouTube videos about tickers
- `00.log_atualizacao` — ETL run log (populated by `run_all.ps1` on each execution)

Complete schema with full column docs is in `.opencode/skills/invest-ranking-analyst/SKILL.md` — load the `invest-ranking-analyst` skill for ranking/analysis work.

## PostgREST Quirks
- `like` uses `*` wildcard: `like.*Relat*rio*`
- `limit` defaults to 1000 — paginate with `&offset=N`
- `tipo=neq.` means `tipo != ''` (excludes NULL)
- CVM date columns use `data_referencia` (NOT `data_informacao`)
- Intermittent 500 errors with `like` + `order` on `fnet_tudo`

## ETL Pitfalls
- **CRITICAL**: `atualizar_fnet_dados.py` must **strip** `tipo`, `rendimento`, `data_com`, `data_pagamento` before upsert — otherwise it overwrites values extracted by `fnet_rendimentos.py` (done in `_scrape_todas_paginas`)
- `percentual_despesas_taxa_administracao` in `cvm_fii_complemento` is decimal (e.g. `0.000693` = 0.0693%). Multiply by 100 for display.
- CVM monthly tables use versioned rows — always `ORDER BY data_referencia DESC, versao DESC LIMIT 1` for latest
- B3 intraday scraper: skips tickers with `< 10 trades` on the day
- `.run_state.json` prevents re-running CVM/StatusInvest scripts more than once per 2h — delete the file to force re-run
- `run_all.ps1` now logs each script run to `00.log_atualizacao` table (view at `/pages/status.html`)
- All CVM `percentual_*` fields are decimals (0 to 1 range), multiply by 100 for display

## Frontend
- `frontend/pages/analise-fii.html` (Scanner, default ticker `GARE11`): self-contained (inline CSS/JS)
- `frontend/pages/fii.html`: loads `../js/app.js` + `../css/style.css`
- Sidebar (`frontend/index.html`) shows: mosaico, radar-mais, analise-fii, status, ranking-fiis, relatorios, rendimentos
- Font Awesome 6.5.0 CDN for icons
- **PostgREST REST API**: frontend calls Supabase REST API directly (`fetch` with `apikey` + `Authorization` headers), NOT the Supabase JS client
- `.opencode/rules/supabase.md` says "Use Supabase JS client" — this is **incorrect** for this project; the frontend uses raw `fetch` to PostgREST

## opencode.json Config
- **MCP**: Supabase via `scripts/mcp-supabase.ps1` (loads `.env` vars)
- **Commands**: `test`/`lint`/`build` defined but are generic templates — no test framework exists
- **Formatter + LSP**: enabled
- **Skill**: `invest-ranking-analyst` covers database schema + financial methodology — load it for ranking/analysis work
- **Theme**: Tokyo Night (`tui.json`)
