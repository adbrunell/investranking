# Invest Ranking

## Tech Stack
- **DB**: Supabase (PostgreSQL) — `oaqmnaekrpukwmrxjtud`
- **Frontend**: Vanilla HTML/CSS/JS (no build tools)
- **ETL**: Python scripts in `scripts/data-updates/`
- **Charts**: Canvas 2D API (Scanner page), D3.js v7 CDN (Mosaico treemap)

## Critical Setup
- **Serve**: `.\servidor.ps1` → http://localhost:8080 (Python http.server on `frontend/`). NEVER open `frontend/index.html` via `file://`
- **Python**: `scripts/.venv/Scripts/python.exe` — use directly; system Python won't have deps
- **ETL deps**: `pip install playwright && playwright install chromium` for Playwright-based scrapers
- **`.env.example`** at root lists all 5 required vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_PROJECT_REF`, `SUPABASE_ACCESS_TOKEN`
- **`.env` at project root** — loaded by `run_all.ps1` (`Get-Content` split on `=`, no PS module) and by ETL scripts (manual `open().read().split("=")`, NOT python-dotenv)
- **Python deps**: `supabase>=2.0.0`, `httpx>=0.27.0`, `playwright>=1.60.0`, `pytesseract`, `pillow`
- **No test/lint/build framework** exists — `opencode.json` `test`/`lint`/`build` commands are generic templates only

## ETL Orchestration
`scripts/data-updates/run_all.ps1` is the **canonical runner** (`.bat` files there are deprecated). Manages scheduling via `.run_state.json`:

| Group | Scripts | When |
|---|---|---|
| **Always** | `b3_cotacoes_aovivo`, `fnet_dados`, `youtube_videos` | Every run |
| **2h interval** | `cvm_fii_mensal`, `cvm_fiagro_mensal`, `cvm_cadastral`, `statusinvest_acoes`, `statusinvest_dividendos` | Skip if <2h since last |
| **24h interval** | `b3_cotahist` | Skip if <24h; also skipped from Task Scheduler (captcha) |

`fnet_dados` always calls `fnet_rendimentos` at the end. Post-run RPCs (always called via `Invoke-RestMethod`): `fn_atualizar_minigrafico`, `fn_refresh_ranking_fiis` (materialized view `"Ranking_FIIs"`), `fn_limpar_b3_historico`.

Playwright scripts (`b3_cotahist`, `statusinvest_acoes`, `statusinvest_dividendos`) use `headless=False`. First two are skipped by `run_all.ps1` when running from Task Scheduler (`$captchaScripts` list).

Task Scheduler config: `scripts/data-updates/setup_task.ps1` — runs `run_all.ps1` at logon with 30min repetition. `executar_atualizacao.bat` is a convenience double-click wrapper.

## ETL Conventions
- All scrapers use `supabase.table().upsert(batch, on_conflict=...)` pattern (Python `supabase` client) or raw POST to `rest/v1/...?on_conflict=...`
- `utils.scraper.config.Config` singleton reads `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` from env; import via `from utils.scraper.config import config`
- `utils.scraper._fnet_base` provides shared FNET helpers (`_parse_date`, `_cookies_from_fnet`)
- `.run_state.json` prevents re-running CVM/StatusInvest scripts more than once per 2h — delete to force re-run
- B3 intraday scraper: skips tickers with `<10 trades` on the day

## Database
- **`00_Master`** is a VIEW (columns: `Ticker`, `Classe`, `CNPJ`); underlying table is `00_fundos_master` (`ticker`, `segmento`, `tipo`, `cnpj`)
- `"Ranking_FIIs"` is a **materialized view** refreshed post-ETL via `fn_refresh_ranking_fiis`

Key tables:
- `00_fundos_master` — curated FII list; `fundos_map` — CNPJ↔ticker bridge
- `fnet_tudo` — FNET docs + income fields (`data_com`, `data_pagamento`, `tipo`, `rendimento`)
- `fnet_rendimentos` — parsed income declarations (source for DY)
- `b3_cotacoes` (aka `b3_cotacoes_historico`) — daily OHLCV (PK: ticker+data)
- `b3_cotacoes_aovivo` — intraday snapshot (PK: codigo_instrumento+data_referencia)
- `cotacoes_tempo_real` — latest post-market price per fund
- `cvm_fii_geral` / `cvm_fii_complemento` / `cvm_fii_ativo_passivo` / `cvm_fiagro_geral` — monthly reports
- `status_dividendos` — unified dividends; `status_acoes` — stock indicators
- `youtube_videos` — videos about tickers
- `00.log_atualizacao` — ETL run log
- `setups` — saved scanner filters (auth-gated)
- Complete schema with column docs: load the `invest-ranking-analyst` skill

## ETL Pitfalls
- **CRITICAL**: `atualizar_fnet_dados.py` must **strip** `tipo`, `rendimento`, `data_com`, `data_pagamento` from scraped rows before upsert — otherwise it overwrites values extracted by `fnet_rendimentos.py`
- CVM `percentual_*` fields are decimals (0–1), multiply by 100 for display
- `percentual_despesas_taxa_administracao` in `cvm_fii_complemento`: decimal (e.g. `0.000693` = 0.0693%)
- CVM monthly tables use versioned rows — always `ORDER BY data_referencia DESC, versao DESC LIMIT 1` for latest
- CVM date columns use `data_referencia` (NOT `data_informacao`)
- Intermittent 500 errors with `like` + `order` on `fnet_tudo`

## PostgREST API (Frontend)
Frontend queries Supabase via **raw `fetch` to PostgREST REST API** — NOT the Supabase JS client. Auth/setups use the JS client (loaded from CDN in login/signup pages and `supabase.js`), but data pages (analise-fii, mosaico, radar, radar-mais, ranking-fiis, ranking, status) all use:

```
fetch('https://...supabase.co/rest/v1/<table>?...', {
  headers: { apikey: 'sb_publishable_...', Authorization: 'Bearer sb_publishable_...' }
})
```

Quirks:
- `like` uses `*` wildcard: `like.*Relat*rio*`
- `limit` defaults to 1000 — paginate manually with `limit=N&offset=M` + `Prefer: count=exact` header
- `tipo=neq.` means `tipo != ''` (excludes NULL)
- Client key `sb_publishable_ekx47MbcOg-C1uoAPJnKWg_c9t9ndQR` is hardcoded in every page's `H`/`HEADERS` constant

## Database Migrations
- SQL files in `database/migrations/` — apply manually via Supabase dashboard or `supabase_apply_migration` tool
- Named with timestamp prefix (`20260613000001_create_*`)

## Frontend Layout
- `frontend/index.html` is the sidebar shell; pages load in an iframe from `pages/`
- Scanner: `pages/analise-fii.html` (default ticker `GARE11`), self-contained (inline CSS/JS)
- `pages/fii.html` loads `../js/app.js` + `../css/style.css`
- Font Awesome 6.5.0 CDN for icons
- MCP: `scripts/mcp-supabase.ps1` reads `SUPABASE_*` from `.env` and pipes into `npx @supabase/mcp-server-supabase`
