# Invest Ranking

## Tech Stack
- **Database**: Supabase (PostgreSQL) — `oaqmnaekrpukwmrxjtud`
- **Frontend**: Vanilla HTML/CSS/JS (no framework, no build tools)
- **Backend/ETL**: Python scripts in `scripts/data-updates/`
- **Charts**: Canvas 2D API (FII/Scanner page), D3.js v7 CDN (Mosaico treemap)

## Critical Setup

**NÃO abrir `frontend/index.html` direto (file://).** Sempre usar:

```powershell
.\servidor.ps1
# Abre http://localhost:8080
```

**Python scripts** precisam carregar o `.env` antes:

```powershell
Get-Content .env | ForEach-Object { if ($_ -match "^(.*?)=(.*)$") { Set-Item -Path "env:$($matches[1])" -Value $matches[2] } }
.\.venv\Scripts\python.exe scripts/data-updates/atualizar_fnet_rendimentos.py
```

Ou usar `run_all.ps1` que já carrega o `.env`.

## Project Structure

```
/
├── frontend/
│   ├── index.html                  ← Shell com sidebar + iframe
│   ├── pages/
│   │   ├── mosaico.html            ← Treemap (D3)
│   │   ├── radar.html              ← Radar de anúncios
│   │   ├── fii.html                ← Análise FII original (app.js)
│   │   ├── analise-fii.html        ← Scanner de Fundos (novo, self-contained)
│   │   └── ...
│   ├── css/style.css               ← Compartilhado (fii.html usa)
│   └── js/app.js                   ← Usado por fii.html
├── database/migrations/
├── scripts/
│   ├── data-updates/               ← ETL Python
│   │   ├── atualizar_fnet_dados.py         ← Scrap FNET primeira página
│   │   ├── atualizar_fnet_rendimentos.py   ← Scrap rendimentos (viewer page)
│   │   └── run_all.ps1                     ← Executa todos em sequência
│   ├── utils/scraper/              ← Módulo compartilhado
│   │   └── config.py               ← Lê SUPABASE_URL + SUPABASE_SERVICE_KEY do env
│   └── .venv/
└── servidor.ps1
```

## Frontend Patterns

- **analise-fii.html** (Scanner) é self-contained: CSS inline + JS inline. Não depende de app.js.
- **fii.html** carrega `../js/app.js` + `../css/style.css`.
- **Ícones**: Font Awesome 6.5.0 CDN.
- **API Key** (publishable): `sb_publishable_ekx47MbcOg-C1uoAPJnKWg_c9t9ndQR`
- **REST endpoint**: `https://oaqmnaekrpukwmrxjtud.supabase.co/rest/v1`

## Database

Tabelas principais:
- `00_fundos_master` — ticker, cnpj, segmento, tipo
- `fnet_tudo` — documentos FNET (colunas normais + `data_com`, `data_pagamento`, `tipo`, `rendimento`)
- `b3_cotacoes_historico` — preços OHLCV diários
- `b3_cotacoes_aovivo` — cotação ao vivo
- `cvm_fii_geral` — tipo_gestao, segmento_atuacao, publico_alvo, data_funcionamento
- `cvm_fii_complemento` — valor_patrimonial_cotas, percentual_dividend_yield_mes, patrimonio_liquido, percentual_despesas_taxa_administracao
- `cvm_fii_dadoscadastrais` — taxa_adm (já em %)
- `status_dividendos` — proventos unificados (tipo_ativo: FIIs, Fiagro, Fiinfra, Acoes)
- `youtube_videos` — vídeos do YouTube

### API Quirks (PostgREST)
- `like` usa `*` como wildcard: `like.*Relat*rio*`
- `limit` padrão é 1000; para mais usa paginação com `&offset=N`
- `tipo=neq.` significa `tipo != ''` (exclui NULL)
- Colunas de data nas tabelas CVM: `data_referencia` (NÃO `data_informacao`)
- Erros 500 intermitentes com `like` + `order` em `fnet_tudo`

## ETL / Scraping

- `atualizar_fnet_dados.py` → `atualizar_fnet_rendimentos.py` (chamado ao final)
- `atualizar_fnet_rendimentos.py`:
  - Busca docs do FNET com `rendimento=is.null` em lotes de 500
  - 10 workers concorrentes
  - Parse do HTML: busca "Valor do provento", "Data-base" (data_com), "Data do pagamento"
  - Detecta Dividendo vs Amortização pela coluna da tabela que tem valor
  - `percentual_despesas_taxa_administracao` do `cvm_fii_complemento` é decimal (ex: 0.000693 = 0.0693%). Multiplicar por 100 para %.
- **CRÍTICO**: `atualizar_fnet_dados.py` NÃO pode incluir `tipo`, `rendimento`, `data_com`, `data_pagamento` no upsert, senão sobrescreve os valores extraídos pelo viewer page. Esses 4 campos são removidos do dict em `_scrape_primeira_pagina`.

## Canvas Chart Patterns

Scanner (`analise-fii.html`):
- **Gráfico de cotação**: preço (linha amarela) + liquidez (barras azuis eixo direito, animação reveal)
- **Gráfico de dividendos**: barras amarelas (zona inferior) + linhas DY (verde) e Preço (azul) na zona superior, reveal left-to-right
- **Atratividade**: barra horizontal gradiente vermelho→amarelo→verde (canvas `#gauge`)
- **Crosshair**: overlay canvas com linhas tracejadas
- **Marcadores**: ícones no topo com linha tracejada até o preço (R, !, $, ▶)
- **Animação de markers**: ícone sobe/desce da linha ao topo (400ms ease-out)
- **Animação de liquidez**: barras revelam de baixo pra cima (500ms)

FII (`app.js`):
- Canvas charts com overlay para crosshair
- Mesmo padrão de cores: yellow=`#ffde59`, green=`#2ec4b6`, blue=`#4285F4`

## Page-specific Notes

- **Scanner** (`analise-fii.html`): Ticker `GARE11` default. Toggles de eventos começam DESLIGADOS.
- **FII** (`fii.html`): Usa `app.js`. Toggles de eventos começam LIGADOS.
- **Radar** (`radar.html`): Queries `fnet_tudo` para 3 categorias + `youtube_videos`.
- **Mosaico** (`mosaico.html`): Treemap D3 via Google Sheets (fallback) ou Supabase.
