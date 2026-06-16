---
name: invest-ranking-analyst
description: Use this skill whenever working on Invest Ranking — any task involving B3, CVM, or FNET data, FIIs (fundos imobiliários) or ações, financial metrics/indicators, ranking algorithms, scraper/ETL scripts that populate the database, or analysis tools shown to users. Trigger this for designing rankings, validating scraped data, calculating indicators (DY, P/VP, vacância, FFO, AFFO, ROE, P/L, liquidez, etc.), handling corporate events (splits, amortizations, incorporações), or reasoning about what an asset's numbers mean. Think like a professional sell-side/buy-side equity and real-estate-fund analyst, not just a data pipeline.
---

# Invest Ranking — Analyst Skill

Invest Ranking aggregates data on FIIs (fundos imobiliários) and ações from
B3, CVM, and FNET, and turns it into ranking tools. This skill governs how to
think about that data: as an analyst first, an engineer second. A ranking
that is technically correct but financially misleading is a bug.

## 1. Know your sources and their quirks

| Source | What it gives you | Known pitfalls |
|---|---|---|
| **B3** | Prices, volume, ticker metadata, dividends/JCP calendar, sector classification | Tickers get reused/reissued; ex-date vs payment-date confusion; suspended/delisted tickers still appear in old data |
| **CVM** | Regulatory filings, FRE (Formulário de Referência), financial statements (DFP/ITR), shareholder structure | Filings can be restated/corrected — always keep the *latest valid version* per period, but retain history for audit |
| **FNET** | FII periodic reports (informe mensal, relatório gerencial), fato relevante, assembleia documents | Highly inconsistent formats across administradoras; same field (e.g. vacância) reported differently by different funds; PDFs/unstructured data common |

When a scraper pulls from any of these, the skill is to ask: *what period
does this number actually refer to, and is this the authoritative/latest
version?* Never assume the most recently scraped row is the most recently
*valid* one — CVM/FNET allow retroactive corrections.

## 2. Core financial concepts — use correctly, don't approximate

### For FIIs
- **Dividend Yield (DY)**: distributions over a period ÷ price. Always state
  the period (12m, current month annualized, YTD) — these give very
  different numbers and mixing them in one ranking is misleading.
- **P/VP**: market price ÷ valor patrimonial por cota (from the latest
  informe mensal/balanço). If the VP figure is stale (e.g. from a report
  several months old) relative to price, flag it — comparing a live price to
  a 6-month-old VP can distort a ranking.
- **Vacância (física vs financeira)**: these are different metrics and FIIs
  report them inconsistently. Track which type each source provides; never
  silently merge them into one "vacancy" field.
- **FFO / AFFO**: cash-generation metrics distinct from net income (which can
  include non-cash items like fair-value adjustments to properties). Prefer
  FFO/AFFO for yield-sustainability analysis over accounting net income.
- **Liquidez**: average daily trading volume/value — essential for usability
  rankings (a fund with a great DY but near-zero liquidity is not investable
  for most users; either exclude it or flag it prominently).
- **Segment/type**: lajes corporativas, galpões logísticos, shoppings, papel
  (recebíveis/CRI), fundo de fundos (FOF), híbrido — never rank across
  segments with the same raw metric without normalizing or segmenting,
  since e.g. "fundos de papel" naturally show different DY/P-VP profiles than
  "fundos de tijolo."

### For Ações
- **P/L (P/E), P/VP, EV/EBITDA, ROE, Margem líquida, Dívida líquida/EBITDA**:
  standard, but always check the *trailing period* used (LTM vs last fiscal
  year vs latest quarter annualized) and be consistent within a ranking.
- **Setor/segmento (B3 classification)**: comparing P/L of a bank to a
  commodities company without segmenting is a classic beginner mistake —
  don't let a ranking do this implicitly.
- **Eventos corporativos**: splits, grupamentos, bonificações, subscrições,
  incorporações/fusões. These break naive time-series continuity (price
  history, historical DY based on old share count). Adjust historical data
  for these events before computing trailing metrics — or clearly document
  if you haven't.
- **Proventos**: dividendos vs JCP (juros sobre capital próprio) have
  different tax treatment for the end user — if the tool shows yield, note
  whether it's gross or net of the 15% IR on JCP if that distinction matters
  for the feature.

## 3. Data quality — think like an analyst auditing a dataset

Before any number reaches a ranking, the skill is to sanity-check it the way
an analyst would before putting it in a report:

- **Outlier sanity checks**: DY of 50%, P/VP of 0.01, negative vacância —
  these are almost always data errors (wrong unit, decimal shift, scraping a
  cancelled/restated filing), not real numbers. Flag/quarantine, don't
  silently include in rankings.
- **Unit and scale consistency**: values in R$ vs R$ thousands vs R$
  millions; percentages as `0.085` vs `8.5` — a frequent source of silent
  10x/100x errors. Validate units at ingestion, not at display time.
- **Survivorship and delisting**: when a ticker stops trading or a fund is
  liquidated, decide explicitly how it's handled in historical rankings
  (excluded going forward but kept for historical accuracy — don't let it
  vanish retroactively and don't let it keep appearing as "active").
- **Freshness**: every metric shown to a user should be traceable to a
  reference date (data do informe, data da cotação). A ranking mixing a
  price from today with a financial statement from 8 months ago should make
  that age visible, not hide it.
- **Duplicates and re-issues**: B3 occasionally reuses or changes tickers
  (mergers, ticker code changes). Map these to a stable internal identifier
  rather than relying on the raw ticker as a primary key.

## 4. Ranking methodology

When designing or reviewing a ranking tool, the analyst's questions are:

1. **What question does this ranking actually answer?** "Best FIIs" is not
   a question — "highest sustainable DY among logistics FIIs with liquidity
   above X" is. Name rankings precisely.
2. **Is the metric comparable across all ranked assets?** Same period, same
   units, same segment (or explicitly cross-segment with normalization).
3. **Does the ranking reward sustainability or just a snapshot?** A single
   month's distribution spike (e.g. from a one-off sale of property) can
   dominate a 12m DY ranking — consider smoothing, medians, or flagging
   non-recurring distributions.
4. **How are missing/incomplete data handled?** Excluding an asset silently
   vs showing "dados insuficientes" — be explicit, since silent exclusion can
   bias a ranking (e.g. newer funds with less history disappear).
5. **Is there a minimum quality/liquidity floor?** Rankings that include
   illiquid or barely-traded assets at the top are not useful and damage
   user trust — define and document floors (min. liquidez, min. patrimônio,
   min. track record).
6. **Transparency to the user**: each ranking tool should be able to show
   *why* an asset ranks where it does — the underlying metric value, its
   reference date, and the formula/period used. "Black box" rankings erode
   trust in a financial product.

## 5. ETL / scraper conventions specific to this domain

- Each scraper run should record: source, fetch timestamp, reference period
  of the data, and a status (success/partial/error) — don't just overwrite
  the latest value with no provenance.
- Store raw scraped data (or a reference to it) separately from the
  *processed/normalized* metrics used by rankings, so a bad normalization
  can be re-run without re-scraping, and so you can audit "what did the
  source actually say."
- When CVM/FNET issue a corrected filing for a past period, update the
  historical record but keep a log of the correction (old value, new value,
  date of correction) — useful both for debugging and for not silently
  changing numbers users may have seen before.
- Calendar-sensitive jobs (e.g. monthly informes, dividend ex-dates) should
  be idempotent — safe to re-run without creating duplicates if a scrape
  partially failed and is retried.

## 6. When asked to build or modify an analysis/ranking feature

Apply this checklist:
1. Define the exact metric(s), their formulas, periods, and units.
2. Identify the data source(s) and known quirks from §1.
3. Define segmentation/comparability rules from §4.
4. Define data-quality floors and outlier handling from §3.
5. Decide how missing data and edge cases (delisted, new, restated) are
   displayed — never just "drop the row" without a documented reason.
6. Make sure the UI can show provenance (reference date, formula) for any
   number that drives a ranking position.

If any of these aren't addressed, surface them to the user before
considering the feature complete — a ranking tool with undocumented
methodology is a liability for a financial product.

---

## 7. Database Schema — Complete Reference (20 tables)

This section documents every table in the `public` schema, their columns,
relationships, and how to join them for analysis. Maintain this as the
single source of truth for the data model.

### 7.1 Entity-Relationship Overview

```
00_fundos_master ──── CNPJ ──── fundos_map ──── ticker_principal ──── cotacoes_tempo_real
                                        │                                    │
                                   ticker_principal ──── b3_cotacoes (ticker)
                                        │
                                   CNPJ ──── cvm_fii_dadoscadastrais ──── (CNPJ fundo)
                                        │
                                   CNPJ ──── cvm_fii_geral (cnpj_fundo_classe)
                                   CNPJ ──── cvm_fii_complemento (cnpj_fundo_classe)
                                   CNPJ ──── cvm_fii_ativo_passivo (cnpj_fundo_classe)
                                        │
                                   CNPJ ──── fnet_relatorios (CNPJ do fundo)
                                   CNPJ ──── fnet_relevantes (CNPJ do fundo)
                                   CNPJ ──── fnet_rendimentos (CNPJ do fundo)
                                   CNPJ ──── fnet_tudo (CNPJ do fundo)
                                        │
                              cvm_fii_registro_fundo ── id_registro_fundo ──── cvm_fii_registro_classe ── id_registro_classe ──── cvm_fii_registro_subclasse
                                        │                                       │
                                   CNPJ fundo                               CNPJ classe

b3_cotacoes_aovivo ──── (by ticker or codigo_instrumento)
youtube_videos ──── (by ticker)
cvm_fiagro_geral ──── (by CNPJ da classe)
cvm_fiagro_subclasse ──── (by CNPJ da classe)
cvm_acoes_dadoscadastrais ──── (by CNPJ da companhia)
```

### 7.2 Master / Mapping Tables

#### `00_fundos_master` (716 rows)
**Purpose**: Curated list of all FIIs tracked. The central fund registry.
**PK**: `id`
**Unique**: `ticker`

| Column | Type | Meaning |
|---|---|---|
| `id` | bigint | Internal ID |
| `ticker` | text | Ticker (e.g. `CXCO11`, `HGLG11`) |
| `segmento` | text | Segment: `Logísticos`, `Shoppings`, `Lajes Corporativas`, `CRI`, `FoF`, `Fiagro`, `Híbrido`, `FI-Infra`, `FIP-IE`, `Residenciais`, `Renda Urbana`, `Desenvolvimento`, `Hotéis`, `Hospitais`, `Educacionais`, `Agronegócio`, `Fundo Encerrado`, `Pré-operacional` |
| `tipo` | text | Type: `Tijolo`, `Papel`, `FoF`, `Híbrido`, `Fiagro`, `FI-Infra`, `FIP-IE` |
| `cnpj` | text | CNPJ do fundo (links to all other tables) |
| `codigo_isin` | text | ISIN code |
| `atualizado_em` | timestamptz | Last update timestamp |

**Joins**: `fundos_map.cnpj`, `cvm_fii_dadoscadastrais.cnpj_fundo`, `fnet_*`, `cotacoes_tempo_real.codigo_fundo` (via ticker)

---

#### `fundos_map` (666 rows)
**Purpose**: Maps CNPJ → ticker + ISIN, handles name aliases across sources.
**PK**: `cnpj`

| Column | Type | Meaning |
|---|---|---|
| `cnpj` | text | CNPJ (PK, links to all other tables) |
| `ticker_principal` | text | Primary ticker (may be empty `''` for non-traded funds) |
| `nome_principal` | text | Official fund name |
| `isin_principal` | text | Primary ISIN |
| `nomes_alternativos` | text[] | Array of alternative names found in source data |
| `updated_at` | timestamptz | Last update |

**Key role**: This is the **bridge table**. Every other table references either CNPJ
or ticker; `fundos_map` is the authoritative mapping between them.

**Joins**:
- `fundos_map.cnpj` ↔ `00_fundos_master.cnpj`
- `fundos_map.ticker_principal` ↔ `b3_cotacoes.ticker`
- `fundos_map.cnpj` ↔ `fnet_*.cnpj`
- `fundos_map.cnpj` ↔ `cvm_fii_*.cnpj_fundo_classe`
- `fundos_map.ticker_principal` ↔ `cotacoes_tempo_real.codigo_fundo`

---

### 7.3 Pricing Tables

#### `b3_cotacoes` (188,733 rows)
**Purpose**: Historical daily OHLCV prices from B3.
**PK**: `id`
**Unique**: `(ticker, data)`

| Column | Type | Meaning |
|---|---|---|
| `id` | bigint | Internal ID |
| `ticker` | text | Ticker e.g. `HGLG11` |
| `data` | date | Trading date |
| `abertura` | numeric | Open price (R$) |
| `maximo` | numeric | High price (R$) |
| `minimo` | numeric | Low price (R$) |
| `fechamento` | numeric | Close/adjusted price (R$) |
| `volume` | numeric | Total traded volume (R$) |
| `isin` | text | ISIN code |
| `created_at` | timestamptz | Ingestion timestamp |

**Uses**: Historical price charts, DY calculation (price at ex-date), P/VP,
trailing returns, liquidity calculation.

---

#### `b3_cotacoes_aovivo` (9,662 rows)
**Purpose**: Live/current session quotes from B3 (during trading hours).
**PK**: `id`
**Unique**: `(codigo_instrumento, data_referencia)`

| Column | Type | Meaning |
|---|---|---|
| `id` | bigint | Internal ID |
| `codigo_instrumento` | text | Instrument code (usually ticker) |
| `data_referencia` | date | Reference date |
| `preco_ultimo_negocio` | numeric | Last trade price (R$) |
| `volume_total` | numeric | Total volume in session (R$) |
| `quantidade_total` | bigint | Total quantity traded |
| `horario_ultima_transacao` | time | Time of last trade |
| `atualizado_em` | timestamptz | Last update |
| `fechamento_anterior` | numeric | Previous close (R$) |
| `variacao` | numeric | Variation (%) |
| `tipo` | text | Type classification |

**Uses**: Real-time price display during market hours.

---

#### `cotacoes_tempo_real` (909 rows)
**Purpose**: Snapshot of latest known prices for all tracked FIIs (post-market).
**PK**: `id`

| Column | Type | Meaning |
|---|---|---|
| `id` | bigint | Internal ID |
| `tipo` | text | Always `FII` in current data |
| `codigo_fundo` | text | Ticker (matches `fundos_map.ticker_principal`) |
| `segmento` | text | Segment |
| `cnpj` | text | CNPJ |
| `isin` | text | ISIN code |
| `updated_at` | timestamptz | Last price refresh |
| `categoria` | text | `Tijolo`, `Papel`, `FoF`, `FI-Infra`, `Fiagro`, `Híbrido` |
| `cotacao` | numeric | Latest price (R$) |
| `variacao` | numeric | Variation from previous close (%) |

**Uses**: Current price for ranking UIs. One row per fund with latest snapshot.
**Indexed on**: `codigo_fundo`, `updated_at DESC`.

---

### 7.4 CVM — FII Registration Data

#### `cvm_fii_registro_fundo` (2,127 rows)
**Purpose**: CVM registration of FII funds (top-level entity).
**PK**: `id_registro_fundo`

| Column | Type | Meaning |
|---|---|---|
| `id_registro_fundo` | integer | Registry ID (PK, FK → `cvm_fii_registro_classe`) |
| `cnpj_fundo` | text | Fund CNPJ |
| `codigo_cvm` | text | CVM code |
| `data_registro` | date | Registration date with CVM |
| `data_constituicao` | date | Constitution date |
| `tipo_fundo` | text | Fund type |
| `denominacao_social` | text | Legal name |
| `data_cancelamento` | date | Cancellation date (if cancelled) |
| `situacao` | text | Status: `EM FUNCIONAMENTO`, `CANCELADO`, etc. |
| `data_inicio_situacao` | date | Status start date |
| `patrimonio_liquido` | numeric | Net equity (R$) |
| `data_patrimonio_liquido` | date | Net equity reference date |
| `diretor` | text | Director name |
| `cnpj_administrador`, `administrador` | text | Administrator CNPJ/name |
| `gestor`, `cpf_cnpj_gestor` | text | Manager |
| `created_at`, `updated_at` | timestamptz | Audit timestamps |

---

#### `cvm_fii_registro_classe` (1,498 rows)
**Purpose**: CVM registration of FII classes (child of fund).
**PK**: `id_registro_classe`
**FK**: `id_registro_fundo` → `cvm_fii_registro_fundo`

| Column | Type | Meaning |
|---|---|---|
| `id_registro_classe` | integer | Class ID (PK) |
| `id_registro_fundo` | integer | FK → `cvm_fii_registro_fundo` |
| `cnpj_classe` | text | Class CNPJ |
| `codigo_cvm` | text | CVM code |
| `data_registro` | date | Registration date |
| `tipo_classe` | text | Class type |
| `denominacao_social` | text | Legal name |
| `situacao` | text | Status |
| `classificacao` | text | Classification |
| `classificacao_anbima` | text | ANBIMA classification |
| `patrimonio_liquido`, `data_patrimonio_liquido` | numeric/date | Net equity |
| `auditor`, `custodiante`, `controlador` | text | Service providers |

---

#### `cvm_fii_registro_subclasse` (509 rows)
**Purpose**: Sub-classes of FII classes (for multi-series funds).
**PK**: `(id_registro_classe, id_subclasse)`
**FK**: `id_registro_classe` → `cvm_fii_registro_classe`

| Column | Type | Meaning |
|---|---|---|
| `id_registro_classe` | integer | FK → `cvm_fii_registro_classe` |
| `id_subclasse` | text | Subclass identifier |
| `codigo_cvm` | text | CVM code |
| `denominacao_social` | text | Legal name |
| `situacao` | text | Status |
| `exclusivo` | text | Exclusive fund? |
| `publico_alvo` | text | Target audience |

**Hierarchy**: Fundo → 1+ Classes → 1+ Subclasses

---

### 7.5 CVM — FII Periodic Reports (Informe Mensal)

#### `cvm_fii_geral` (78,030 rows)
**Purpose**: General info from monthly reports — identity, segment, administrator.
**Unique**: `(cnpj_fundo_classe, data_referencia, versao)`

| Column | Type | Meaning |
|---|---|---|
| `cnpj_fundo_classe` | text | CNPJ of fund/class (links to `fundos_map.cnpj`) |
| `data_referencia` | date | Report month (e.g. `2026-05-01` for May) |
| `versao` | integer | Version (higher = more recent/corrected) |
| `tipo_fundo_classe` | text | `Fundo` or `Classe` |
| `nome_fundo_classe` | text | Name of fund/class |
| `segmento_atuacao` | text | Segment (e.g. `Shoppings`, `Lajes Corporativas`) |
| `tipo_gestao` | text | Management type: `Definida` or `Ativa` |
| `prazo_duracao` | text | Duration: `Indeterminado` or date |
| `mercado_negociacao_*` | text | Trading markets (Bolsa, MBO, MB) |
| `quantidade_cotas_emitidas` | numeric | Total shares issued |
| `codigo_isin` | text | ISIN |
| `administrador` fields | text | Administrator info |
| Address fields | text | Full address of administrator |

**Uses**: Segment classification, share count, ISIN mapping, administrator data.

---

#### `cvm_fii_complemento` (78,030 rows)
**Purpose**: Financial summary from monthly reports — NAV, DY, rentabilidade.
**Unique**: `(cnpj_fundo_classe, data_referencia, versao)` — same shape as `cvm_fii_geral`

| Column | Type | Meaning |
|---|---|---|
| `cnpj_fundo_classe` | text | CNPJ (joins to `cvm_fii_geral`) |
| `data_referencia` | date | Report month |
| `versao` | integer | Version |
| `total_numero_cotistas` | numeric | Total number of shareholders |
| All `numero_cotistas_*` columns | numeric | Breakdown by investor type |
| `valor_ativo` | numeric | Total asset value (R$) |
| `patrimonio_liquido` | numeric | Net equity / NAV (R$) |
| `cotas_emitidas` | numeric | Total shares issued |
| `valor_patrimonial_cotas` | numeric | NAV per share (VP/cota) (R$) |
| `percentual_despesas_taxa_administracao` | numeric | Management fee rate (decimal, e.g. `0.000219` = 0.0219%) |
| `percentual_despesas_agente_custodiante` | numeric | Custodian fee rate |
| `percentual_rentabilidade_efetiva_mes` | numeric | Monthly effective return (decimal, e.g. `0.001312` = 0.1312%) |
| `percentual_rentabilidade_patrimonial_mes` | numeric | Monthly NAV return (decimal) |
| `percentual_dividend_yield_mes` | numeric | Monthly dividend yield (decimal, e.g. `0.004321` = 0.4321%) |
| `percentual_amortizacao_cotas_mes` | numeric | Monthly amortization rate |

**CRITICAL**: All percentages are stored as **decimals** (e.g. 0.004321 = 0.4321%).
Multiply by 100 for display. These are reported by the administrator; consistency
varies.

**Uses**: P/VP calculation (price ÷ VP/cota), DY calculation, NAV tracking,
cotistas analysis, management fee comparison.

---

#### `cvm_fii_ativo_passivo` (77,799 rows)
**Purpose**: Asset/liability breakdown from monthly reports.
**Unique**: `(cnpj_fundo_classe, data_referencia, versao)` — same shape

| Column | Type | Meaning |
|---|---|---|
| `cnpj_fundo_classe` | text | CNPJ |
| `data_referencia` | date | Report month |
| `versao` | integer | Version |
| **ASSETS** | | |
| `disponibilidades` | numeric | Cash and equivalents (R$) |
| `titulos_publicos` | numeric | Government bonds (R$) |
| `titulos_privados` | numeric | Private bonds (R$) |
| `direitos_bens_imoveis` | numeric | Real estate assets (R$) |
| `imoveis_renda_acabados` | numeric | Completed income properties (R$) |
| `imoveis_renda_construcao` | numeric | Properties under construction (R$) |
| `contas_receber_aluguel` | numeric | Rent receivables (R$) |
| `acoes`, `debentures`, `cri`, `lci`, `fii` | numeric | Securities holdings |
| **LIABILITIES** | | |
| `rendimentos_distribuir` | numeric | Distributable income payable (R$) |
| `taxa_administracao_pagar` | numeric | Management fees payable |
| `obrigacoes_aquisicao_imoveis` | numeric | Property acquisition obligations |
| `total_passivo` | numeric | Total liabilities (R$) |

**Uses**: Asset composition analysis, cash position, leverage ratios, sector exposure
of the fund's investments. A fund with `total_passivo = 0` likely has no debt.

---

### 7.6 CVM — Ações (Stocks)

#### `cvm_acoes_dadoscadastrais` (2,528 rows)
**Purpose**: CVM registration data for publicly-held companies (companhias abertas).
**Unique**: `cnpj_cia`

| Column | Type | Meaning |
|---|---|---|
| `cnpj_cia` | text | Company CNPJ |
| `denom_social` | text | Legal name |
| `denom_comerc` | text | Trade name |
| `dt_reg` | date | Registration with CVM |
| `dt_const` | date | Constitution date |
| `dt_cancel` | date | Cancellation date |
| `sit` | text | Status: `ATIVO`, `CANCELADO`, etc. |
| `cd_cvm` | text | CVM code |
| `setor_ativ` | text | Economic sector |
| `tp_merc` | text | Market type |
| `categ_reg` | text | Registration category |
| `auditor`, `cnpj_auditor` | text | Auditor |
| Full address fields | text | Company address |
| Contact fields | text | Phone, fax, email |

**Uses**: Company lookup, sector classification, status verification for stocks.

---

### 7.7 CVM — Fiagro

#### `cvm_fiagro_geral` (1,766 rows)
**Purpose**: Monthly reports for Fiagro funds (agro funds), similar to FII complemento + ativo_passivo combined.
**Unique**: `(cnpj_classe, data_referencia, versao)`

This table is essentially the **Fiagro equivalent of `cvm_fii_complemento` + `cvm_fii_ativo_passivo`**
combined into one table. Columns include:

| Category | Key columns |
|---|---|
| Identity | `cnpj_classe`, `nome_classe`, `codigo_isin` |
| Management | `cnpj_administrador`, `nome_gestor`, `publico_alvo` |
| Cotistas | `numero_cotistas`, breakdown by type |
| Portfolio | `valor_ativo`, `patrimonio_liquido`, `cotas_emitidas`, `valor_patrimonial_cotas` |
| Performance | `rentabilidade_efetiva_mes`, `dividend_yield_mes`, `percentual_despesas_taxa_administracao` |
| **Fiagro-specific breakdown** | `imoveis_rurais`, `lca`, `lci`, `cpr` (CPR financeira/física), `cra`, `cri`, `cdca`, `cda_wa`, credits (carbono, descarbonização) |
| Maturity schedule | `a_vencer` broken into buckets (30d, 60d, 90d, etc.), `vencidos` (overdue) buckets |
| Liabilities | `rendimentos_distribuir`, `taxa_administracao_pagar`, `obrigacoes_aquisicao_ativos`, `total_passivo` |

**Uses**: Fiagro-specific analysis — understanding exposure to rural credit, CPR,
CRAs, land ownership. The maturity buckets let you assess the fund's duration
and overdue ratio.

---

#### `cvm_fiagro_subclasse` (3,872 rows)
**Purpose**: Sub-class breakdown for Fiagro classes (NAV per share per subclass).
**Unique**: `(cnpj_classe, data_referencia, nome_subclasse)`

| Column | Type | Meaning |
|---|---|---|
| `cnpj_classe` | text | Class CNPJ → `cvm_fiagro_geral` |
| `data_referencia` | date | Report month |
| `nome_subclasse` | text | Subclass name |
| `numero_cotas` | numeric | Shares in this subclass |
| `valor_patrimonial_cota` | numeric | NAV per share for this subclass (R$) |

---

### 7.8 FNET — Documents and Events

#### `fnet_relatorios` (29,523 rows)
**Purpose**: FNET periodic reports (informes mensais, relatórios gerenciais) for FIIs.
**PK**: `id` | **Unique**: `fnet_documento_id`

| Column | Type | Meaning |
|---|---|---|
| `fnet_documento_id` | varchar | FNET document ID (links to FNET system) |
| `cnpj` | varchar | Fund CNPJ |
| `nome_fundo` | varchar | Fund name |
| `tipo_documento` | varchar | Document type (e.g. `Informe Mensal`, `Relatório Gerencial`) |
| `data_referencia` | timestamp | Reference month |
| `data_entrega` | timestamptz | Delivery date |
| `link_documento` | text | Download URL |
| `link_visualizar` | text | View URL |
| `status` | text | Document status |
| `versao` | text | Version |
| `codigo_fundo` | text | Fund code (may be different from ticker) |

**Uses**: Document discovery, determining the latest report version per fund/period.

---

#### `fnet_relevantes` (14,031 rows)
**Purpose**: "Fatos Relevantes" (material facts) for FIIs.
**PK**: `id` | **Unique**: `fnet_documento_id`

| Column | Type | Meaning |
|---|---|---|
| `fnet_documento_id` | text | FNET document ID |
| `cnpj` | text | Fund CNPJ |
| `nome_fundo` | text | Fund name |
| `tipo_documento` | text | Always `Fato Relevante` |
| `data_referencia` | timestamp | Event date |
| `data_entrega` | timestamp | Filing date |
| `link_documento` | text | PDF URL |
| `codigo_fundo` | text | Fund code |

**Uses**: Corporate events display (radar de anúncios), material changes affecting
fundamentals.

---

#### `fnet_rendimentos` (33,755 rows)
**Purpose**: Income distribution declarations (rendimentos e amortizações).
**PK**: `id` | **Unique**: `fnet_documento_id`

| Column | Type | Meaning |
|---|---|---|
| `fnet_documento_id` | text | FNET document ID |
| `cnpj` | text | Fund CNPJ |
| `nome_fundo` | text | Fund name |
| `codigo_fundo` | text | Fund code (often the ticker) |
| `isin` | text | ISIN (empty for some) |
| `tipo` | text | `Dividendo` or `Amortização` |
| `rendimento` | numeric | Value per share (R$/cota) |
| `data_com` | date | Ex-date (data com) |
| `data_pagamento` | date | Payment date |
| `periodo_referencia` | text | Reference period (e.g. `Maio-2026`) |
| `ano` | text | Year |
| `rendimento_isento_ir` | text | `Sim` or `Não` |
| `dividend_yield` | numeric | Pre-calculated DY (may be null) |
| `analisado` | boolean | Whether already processed |
| `status` | text | Document status |
| `versao` | text | Version |
| `nome_administrador` | text | Administrator name |
| `responsavel`, `telefone` | text | Contact info |

**CRITICAL**: This is the **primary source for DY calculation**. To compute
trailing 12m DY: `SUM(rendimento WHERE tipo='Dividendo' AND data_com >= 12m ago)`.

**Joins**: `cnpj` ↔ `fundos_map.cnpj` to get ticker.

---

#### `fnet_tudo` (194,796 rows)
**Purpose**: Aggregated FNET feed — all document types in one table.
**PK**: `id` | **Unique**: `fnet_documento_id`

| Column | Type | Meaning |
|---|---|---|
| `fnet_documento_id` | text | FNET document ID |
| `codigo_fundo` | text | Fund code |
| `cnpj` | text | CNPJ |
| `codigo_isin` | text | ISIN |
| `nome_pregao` | text | Trading name |
| `nome_oficial` | text | Official name |
| `categoria_documento` | text | Category |
| `tipo_documento` | text | Type (e.g. `Rendimentos e Amortizações`) |
| `especie_documento` | text | Species |
| `data_referencia` | timestamptz | Reference date |
| `data_entrega` | timestamptz | Delivery date |
| `status`, `descricao_status` | text | Status |
| `versao` | integer | Version |
| `modalidade`, `descricao_modalidade` | text | Modality |
| `link_documento`, `link_visualizar` | text | URLs |
| `analisado` | boolean | Processed flag |
| `informacoes_adicionais` | text | Additional info |
| — plus income fields: | | |
| `data_com`, `data_pagamento` | timestamptz | Ex/payment dates |
| `tipo` | text | `Dividendo`/`Amortização` |
| `rendimento` | numeric | Value per share |

**Uses**: Comprehensive document search/filter, combined with income data.
Has many nullable columns since it merges multiple document types.

---

### 7.9 YouTube Videos

#### `youtube_videos` (9,956 rows)
**Purpose**: YouTube videos about specific FIIs, tracked for content.
**PK**: `id` | **Unique**: `video_id`

| Column | Type | Meaning |
|---|---|---|
| `ticker` | text | Related ticker |
| `video_id` | text | YouTube video ID |
| `canal` | text | Channel name |
| `titulo` | text | Video title |
| `publicacao` | timestamptz | Publication date |
| `duracao` | text | Duration |
| `link` | text | Full YouTube link |

---

### 7.10 Cross-Table Join Recipes for Common Analysis

#### A. Latest price + latest NAV for P/VP
```sql
SELECT
  fm.ticker,
  c.cotacao AS preco_atual,
  comp.valor_patrimonial_cotas AS vp_cota,
  c.cotacao / NULLIF(comp.valor_patrimonial_cotas, 0) AS p_vp
FROM fundos_map fm
JOIN cotacoes_tempo_real c ON c.codigo_fundo = fm.ticker_principal
JOIN LATERAL (
  SELECT valor_patrimonial_cotas, data_referencia
  FROM cvm_fii_complemento
  WHERE cnpj_fundo_classe = fm.cnpj
  ORDER BY data_referencia DESC, versao DESC
  LIMIT 1
) comp ON true;
```

#### B. Trailing 12-month DY
```sql
SELECT
  fm.ticker_principal,
  SUM(r.rendimento) AS dy_12m_reais,
  AVG(c.cotacao) AS preco_medio_12m,
  SUM(r.rendimento) / AVG(c.cotacao) AS dy_12m_pct
FROM fundos_map fm
JOIN fnet_rendimentos r ON r.cnpj = fm.cnpj
  AND r.tipo = 'Dividendo'
  AND r.data_com >= CURRENT_DATE - INTERVAL '12 months'
JOIN cotacoes_tempo_real c ON c.codigo_fundo = fm.ticker_principal
GROUP BY fm.ticker_principal;
```

#### C. Latest monthly report per fund
```sql
SELECT g.cnpj_fundo_classe, g.nome_fundo_classe, g.segmento_atuacao,
       c.patrimonio_liquido, c.valor_patrimonial_cotas,
       c.percentual_dividend_yield_mes, c.percentual_rentabilidade_efetiva_mes,
       c.total_numero_cotistas, g.data_referencia
FROM cvm_fii_geral g
JOIN cvm_fii_complemento c ON c.cnpj_fundo_classe = g.cnpj_fundo_classe
  AND c.data_referencia = g.data_referencia AND c.versao = g.versao
WHERE g.cnpj_fundo_classe = :cnpj
ORDER BY g.data_referencia DESC, g.versao DESC
LIMIT 1;
```

#### D. Asset composition breakdown
```sql
SELECT cnpj_fundo_classe, data_referencia,
  disponibilidades, titulos_publicos,
  imoveis_renda_acabados, imoveis_renda_construcao,
  contas_receber_aluguel,
  cri, lci, debentures, fii,
  total_passivo
FROM cvm_fii_ativo_passivo
WHERE cnpj_fundo_classe = :cnpj
ORDER BY data_referencia DESC, versao DESC
LIMIT 1;
```

#### E. Income calendar (ex-dates + payments)
```sql
SELECT fm.ticker_principal, r.data_com, r.data_pagamento,
       r.rendimento, r.tipo, r.periodo_referencia, r.rendimento_isento_ir
FROM fnet_rendimentos r
JOIN fundos_map fm ON fm.cnpj = r.cnpj
WHERE fm.ticker_principal = :ticker
  AND r.tipo = 'Dividendo'
ORDER BY r.data_com DESC;
```

#### F. Fiagro credit portfolio breakdown
```sql
SELECT cnpj_classe, nome_classe, data_referencia,
  imoveis_rurais, lca, lci, cpr, cpr_financeira, cpr_fisica,
  cra, cri, direitos_creditorios_agronegocio,
  a_vencer, vencidos, total_passivo
FROM cvm_fiagro_geral
WHERE cnpj_classe = :cnpj
ORDER BY data_referencia DESC, versao DESC
LIMIT 1;
```

### 7.11 Important Data Rules

1. **Version handling**: All CVM monthly tables (`cvm_fii_geral`, `cvm_fii_complemento`,
   `cvm_fii_ativo_passivo`, `cvm_fiagro_geral`) have versions. Always query
   `ORDER BY data_referencia DESC, versao DESC LIMIT 1` for the latest, or use
   `DISTINCT ON (cnpj_fundo_classe, data_referencia)` with `ORDER BY versao DESC`
   to get the latest version per month.

2. **Percentage format**: In CVM tables, all `percentual_*` fields are decimals
   (0 to 1 range). Multiply by 100 for percentage display.

3. **CNPJ formatting**: CNPJs appear with punctuation (`00.332.266/0001-31`) or
   without (`07253654000176`). The `fundos_map.cnpj` has punctuation. Use
   `REPLACE(cnpj, '.', '')` for joins where format differs.

4. **Ticker vs codigo_fundo**: Some FNET tables use `codigo_fundo` which can be
   either a ticker (`HGLG11`) or a numerical code (`6089025UN1`). Join via CNPJ
   when possible, not ticker.

5. **cotacoes_tempo_real** is a snapshot — one row per fund, updated post-market.
   For historical prices use `b3_cotacoes`.

6. **fnet_rendimentos** can have multiple documents for the same fund/month
   (corrections, different series). Use `DISTINCT ON (cnpj, data_com, tipo)` to
   deduplicate if needed. Prefer higher `versao`.

7. **CVM registration hierarchy**: Fundo (registro_fundo) → Classe (registro_classe)
   → Subclasse (registro_subclasse). But monthly data uses `cnpj_fundo_classe`
   which can be either fund or class level — check `tipo_fundo_classe`.

8. **fiagro_geral vs fii tables**: Fiagro data is in its own tables with a different
   schema. Don't mix with FII tables in the same query without a type discriminator.
   Use `00_fundos_master.tipo = 'Fiagro'` to filter.
