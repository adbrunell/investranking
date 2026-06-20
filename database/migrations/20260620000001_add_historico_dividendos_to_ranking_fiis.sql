DROP MATERIALIZED VIEW IF EXISTS "Ranking_FIIs";

CREATE MATERIALIZED VIEW "Ranking_FIIs" AS
WITH latest_prices AS (
  SELECT codigo_fundo AS ticker, cotacao, variacao
  FROM cotacoes_tempo_real
), latest_nav_fii AS (
  SELECT DISTINCT ON (cnpj_fundo_classe) cnpj_fundo_classe,
    valor_patrimonial_cotas, total_numero_cotistas
  FROM cvm_fii_complemento
  WHERE valor_patrimonial_cotas IS NOT NULL AND valor_patrimonial_cotas > 0
  ORDER BY cnpj_fundo_classe, data_referencia DESC, versao DESC
), latest_nav_fiagro AS (
  SELECT DISTINCT ON (cnpj_classe) cnpj_classe,
    valor_patrimonial_cotas, numero_cotistas
  FROM cvm_fiagro_geral
  WHERE valor_patrimonial_cotas IS NOT NULL AND valor_patrimonial_cotas > 0
  ORDER BY cnpj_classe, data_referencia DESC, versao DESC
), dy_12m AS (
  SELECT ticker, sum(valor) AS total_rendimentos
  FROM (
    SELECT ticker, valor,
      row_number() OVER (PARTITION BY ticker ORDER BY data_com DESC) AS rn
    FROM status_dividendos
    WHERE valor IS NOT NULL AND valor > 0
  ) sub
  WHERE rn <= 12
  GROUP BY ticker
), liquidez_30d AS (
  SELECT ticker, avg(volume) AS liquidez_media
  FROM b3_cotacoes_historico
  WHERE data >= (SELECT min(d.data) FROM (SELECT DISTINCT data FROM b3_cotacoes_historico ORDER BY data DESC LIMIT 30) d)
  GROUP BY ticker
), price_range AS (
  SELECT ticker,
    min(fechamento) AS min_52s,
    max(fechamento) AS max_52s
  FROM b3_cotacoes_historico
  WHERE data >= CURRENT_DATE - INTERVAL '1 year'
  GROUP BY ticker
), price_history AS (
  SELECT ticker,
    array_agg(fechamento ORDER BY data ASC) AS fechamentos
  FROM b3_cotacoes_historico
  WHERE data >= CURRENT_DATE - INTERVAL '1 year'
  GROUP BY ticker
), dividend_history AS (
  SELECT ticker,
    array_agg(valor ORDER BY data_com ASC) AS dividendos
  FROM (
    SELECT ticker, valor, data_com,
      row_number() OVER (PARTITION BY ticker ORDER BY data_com DESC) AS rn
    FROM status_dividendos
    WHERE valor IS NOT NULL AND valor > 0
  ) sub
  WHERE rn <= 12
  GROUP BY ticker
), fund_idade AS (
  SELECT DISTINCT ON (cnpj_fundo) cnpj_fundo,
    (EXTRACT(YEAR FROM age(CURRENT_DATE, data_constituicao)) * 12 + EXTRACT(MONTH FROM age(CURRENT_DATE, data_constituicao))) AS idade_meses
  FROM cvm_fii_registro_fundo
  WHERE data_constituicao IS NOT NULL
  ORDER BY cnpj_fundo, data_registro DESC
)
SELECT m.ticker, m.tipo, m.segmento,
  p.cotacao, p.variacao,
  COALESCE(l.liquidez_media, 0) AS liquidez_media_30d,
  COALESCE(n.total_numero_cotistas, ng.numero_cotistas, 0) AS numero_cotistas,
  COALESCE(fi.idade_meses, 0) AS idade_meses,
  pr.min_52s, pr.max_52s,
  CASE WHEN p.cotacao IS NOT NULL AND p.cotacao > 0
    AND COALESCE(n.valor_patrimonial_cotas, ng.valor_patrimonial_cotas, 0) > 0
    THEN ROUND(p.cotacao / COALESCE(n.valor_patrimonial_cotas, ng.valor_patrimonial_cotas), 4)
    ELSE NULL END AS p_vp,
  CASE WHEN p.cotacao IS NOT NULL AND p.cotacao > 0 AND d.total_rendimentos IS NOT NULL
    THEN ROUND(d.total_rendimentos / p.cotacao, 6)
    ELSE NULL END AS dividend_yield_12m,
  to_jsonb(COALESCE(ph.fechamentos, ARRAY[]::numeric[])) AS historico_cotacoes,
  to_jsonb(COALESCE(dh.dividendos, ARRAY[]::numeric[])) AS historico_dividendos
FROM "00_fundos_master" m
LEFT JOIN latest_prices p ON p.ticker = m.ticker
LEFT JOIN latest_nav_fii n ON n.cnpj_fundo_classe = m.cnpj
LEFT JOIN latest_nav_fiagro ng ON ng.cnpj_classe = m.cnpj
LEFT JOIN dy_12m d ON d.ticker = m.ticker
LEFT JOIN liquidez_30d l ON l.ticker = m.ticker
LEFT JOIN price_range pr ON pr.ticker = m.ticker
LEFT JOIN price_history ph ON ph.ticker = m.ticker
LEFT JOIN dividend_history dh ON dh.ticker = m.ticker
LEFT JOIN fund_idade fi ON fi.cnpj_fundo = REPLACE(REPLACE(REPLACE(m.cnpj, '.', ''), '/', ''), '-', '')
WHERE m.tipo IN ('Tijolo', 'Papel', 'FoF', 'Híbrido', 'Fiagro', 'FI-Infra', 'FIP-IE')
  AND COALESCE(l.liquidez_media, 0) > 0;
