# Invest Ranking

## Tech Stack
- **DB**: Supabase (PostgreSQL) — `oaqmnaekrpukwmrxjtud`
- **Frontend**: Vanilla HTML/CSS/JS (no build tools)
- **ETL**: Python scripts in `scripts/data-updates/`
- **Charts**: Canvas 2D API (Scanner page), D3.js v7 CDN (Mosaico treemap)

## Critical Setup
- **Serve**: `.\servidor.ps1` → http://localhost:8080 (NUNCA abrir `frontend/index.html` via `file://`)
- **Python**: `scripts/.venv/Scripts/python.exe` — activate or use directly
- **Deps**: `pip install playwright && playwright install chromium` (required for captcha-based scrapers)
- **Client key**: `sb_publishable_ekx47MbcOg-C1uoAPJnKWg_c9t9ndQR`

## ETL Orchestration
`run_all.ps1` at `scripts/data-updates/` handles scheduling with state tracking (`.run_state.json`):

| Group | Scripts | When |
|---|---|---|
| **Always** | `b3_cotacoes_aovivo`, `fnet_dados`, `youtube_videos` | Every run |
| **2h interval** | `cvm_fii_mensal`, `cvm_fiagro_mensal`, `cvm_cadastral`, `statusinvest_acoes`, `statusinvest_dividendos` | Skip if <2h since last |
| **Conditional** | `b3_cotahist` | Only if `aovivo` has newer data than `historico` |

`fnet_dados` always calls `fnet_rendimentos` at the end.

### Captcha-dependent scripts (require interactive browser)
- `atualizar_b3_cotahist.py` — download COTAHIST ZIP from B3
- `atualizar_statusinvest_acoes.py` — download stock screener CSV

Both use Playwright `headless=False` — **will wait for you to solve captcha**.

## Database
**View vs Table**: Scripts query the view `00_Master` (columns: `Ticker`, `Classe`, `CNPJ`), while the actual table is `00_fundos_master` (`ticker`, `segmento`, `tipo`, `cnpj`).

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

## PostgREST Quirks
- `like` uses `*` wildcard: `like.*Relat*rio*`
- `limit` defaults to 1000 — paginate with `&offset=N`
- `tipo=neq.` means `tipo != ''` (excludes NULL)
- CVM date columns use `data_referencia` (NOT `data_informacao`)
- Intermittent 500 errors with `like` + `order` on `fnet_tudo`

## ETL Pitfalls
- **CRITICAL**: `atualizar_fnet_dados.py` must **strip** `tipo`, `rendimento`, `data_com`, `data_pagamento` before upsert — otherwise it overwrites values extracted by `fnet_rendimentos.py` (done in `_scrape_primeira_pagina`)
- `percentual_despesas_taxa_administracao` in `cvm_fii_complemento` is decimal (e.g. `0.000693` = 0.0693%). Multiply by 100 for display.
- CVM monthly tables use versioned rows — always `ORDER BY data_referencia DESC, versao DESC LIMIT 1` for latest
- B3 intraday scraper: skips tickers with `< 10 trades` on the day
- `.run_state.json` prevents re-running CVM/StatusInvest scripts more than once per 2h — delete the file to force re-run
- `run_all.ps1` now logs each script run to `00.log_atualizacao` table (view at `/pages/status.html`)

## Frontend
- `analise-fii.html` (Scanner, default ticker `GARE11`): self-contained (inline CSS/JS)
- `fii.html`: loads `../js/app.js` + `../css/style.css`
- Sidebar (`index.html`) shows: mosaico, radar-mais, analise-fii, status
- Font Awesome 6.5.0 CDN for icons

## opencode.json Config
- **MCP**: Supabase via `scripts/mcp-supabase.ps1` (loads `.env` vars)
- **Commands**: `test`/`lint`/`build` defined but are generic templates — no test framework exists
- **Formatter + LSP**: enabled
- **Skill**: `invest-ranking-analyst` covers database schema (20+ tables) + financial methodology — load it for ranking/analysis work
