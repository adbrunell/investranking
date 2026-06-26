DROP MATERIALIZED VIEW IF EXISTS "Ranking_FIIs";

CREATE MATERIALIZED VIEW "Ranking_FIIs" AS
WITH latest_prices AS (
  SELECT DISTINCT ON (codigo_instrumento)
    codigo_instrumento AS ticker,
    preco_ultimo_negocio AS cotacao,
    variacao
  FROM b3_cotacoes_aovivo
  WHERE preco_ultimo_negocio IS NOT NULL
  ORDER BY codigo_instrumento, data_referencia DESC, atualizado_em DESC
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
), latest_alavancagem_fii AS (
  SELECT DISTINCT ON (cnpj_fundo_classe) cnpj_fundo_classe,
    valor_ativo, patrimonio_liquido
  FROM cvm_fii_complemento
  WHERE valor_ativo IS NOT NULL AND valor_ativo > 0 AND patrimonio_liquido IS NOT NULL
  ORDER BY cnpj_fundo_classe, data_referencia DESC, versao DESC
), latest_alavancagem_fiagro AS (
  SELECT DISTINCT ON (cnpj_classe) cnpj_classe,
    valor_ativo, patrimonio_liquido
  FROM cvm_fiagro_geral
  WHERE valor_ativo IS NOT NULL AND valor_ativo > 0 AND patrimonio_liquido IS NOT NULL
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
    EXTRACT(YEAR FROM age(CURRENT_DATE, data_constituicao)) * 12 +
    EXTRACT(MONTH FROM age(CURRENT_DATE, data_constituicao)) AS idade_meses
  FROM cvm_fii_registro_fundo
  WHERE data_constituicao IS NOT NULL
  ORDER BY cnpj_fundo, data_registro DESC
), maturidade AS (
  SELECT m.ticker,
    CASE
      WHEN COALESCE(l.liquidez_media, 0) > 1000000 THEN 'A'
      WHEN COALESCE(l.liquidez_media, 0) > 200000 THEN 'B'
      ELSE 'C'
    END AS liq_nota,
    CASE
      WHEN COALESCE(n.total_numero_cotistas, ng.numero_cotistas, 0) > 100000 THEN 'A'
      WHEN COALESCE(n.total_numero_cotistas, ng.numero_cotistas, 0) > 20000 THEN 'B'
      ELSE 'C'
    END AS cotistas_nota,
    CASE
      WHEN COALESCE(fi.idade_meses, 0) > 60 THEN 'A'
      WHEN COALESCE(fi.idade_meses, 0) > 24 THEN 'B'
      ELSE 'C'
    END AS idade_nota
  FROM "00_fundos_master" m
  LEFT JOIN liquidez_30d l ON l.ticker = m.ticker
  LEFT JOIN latest_nav_fii n ON n.cnpj_fundo_classe = m.cnpj
  LEFT JOIN latest_nav_fiagro ng ON ng.cnpj_classe = m.cnpj
  LEFT JOIN fund_idade fi ON fi.cnpj_fundo = replace(replace(replace(m.cnpj, '.', ''), '/', ''), '-', '')
)
SELECT m2.ticker, m2.tipo, m2.segmento,
  p.cotacao, p.variacao,
  COALESCE(l2.liquidez_media, 0) AS liquidez_media_30d,
  COALESCE(n2.total_numero_cotistas, ng2.numero_cotistas, 0) AS numero_cotistas,
  COALESCE(fi2.idade_meses, 0) AS idade_meses,
  pr.min_52s, pr.max_52s,
  CASE
    WHEN p.cotacao IS NOT NULL AND p.cotacao > 0
      AND COALESCE(n2.valor_patrimonial_cotas, ng2.valor_patrimonial_cotas, 0) > 0
    THEN round(p.cotacao / COALESCE(n2.valor_patrimonial_cotas, ng2.valor_patrimonial_cotas), 4)
    ELSE NULL
  END AS p_vp,
  CASE
    WHEN p.cotacao IS NOT NULL AND p.cotacao > 0 AND d.total_rendimentos IS NOT NULL
    THEN round(d.total_rendimentos / p.cotacao, 6)
    ELSE NULL
  END AS dividend_yield_12m,
  to_jsonb(COALESCE(ph.fechamentos, ARRAY[]::numeric[])) AS historico_cotacoes,
  to_jsonb(COALESCE(dh.dividendos, ARRAY[]::numeric[])) AS historico_dividendos,
  (ma.liq_nota || '|' || ma.cotistas_nota || '|' || ma.idade_nota) AS maturidade_lci,
  CASE
    WHEN af.valor_ativo IS NOT NULL AND af.valor_ativo > 0
      AND af.patrimonio_liquido IS NOT NULL
    THEN round((af.valor_ativo - af.patrimonio_liquido) / af.valor_ativo, 4)
    WHEN ag.valor_ativo IS NOT NULL AND ag.valor_ativo > 0
      AND ag.patrimonio_liquido IS NOT NULL
    THEN round((ag.valor_ativo - ag.patrimonio_liquido) / ag.valor_ativo, 4)
    ELSE NULL
  END AS alavancagem
FROM "00_fundos_master" m2
LEFT JOIN latest_prices p ON p.ticker = m2.ticker
LEFT JOIN latest_nav_fii n2 ON n2.cnpj_fundo_classe = m2.cnpj
LEFT JOIN latest_nav_fiagro ng2 ON ng2.cnpj_classe = m2.cnpj
LEFT JOIN latest_alavancagem_fii af ON af.cnpj_fundo_classe = m2.cnpj
LEFT JOIN latest_alavancagem_fiagro ag ON ag.cnpj_classe = m2.cnpj
LEFT JOIN dy_12m d ON d.ticker = m2.ticker
LEFT JOIN liquidez_30d l2 ON l2.ticker = m2.ticker
LEFT JOIN price_range pr ON pr.ticker = m2.ticker
LEFT JOIN price_history ph ON ph.ticker = m2.ticker
LEFT JOIN dividend_history dh ON dh.ticker = m2.ticker
LEFT JOIN fund_idade fi2 ON fi2.cnpj_fundo = replace(replace(replace(m2.cnpj, '.', ''), '/', ''), '-', '')
LEFT JOIN maturidade ma ON ma.ticker = m2.ticker
WHERE m2.tipo IN ('Tijolo', 'Papel', 'FoF', 'Híbrido', 'Fiagro', 'FI-Infra', 'FIP-IE')
  AND COALESCE(l2.liquidez_media, 0) > 0;

CREATE OR REPLACE FUNCTION fn_refresh_ranking_fiis()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  REFRESH MATERIALIZED VIEW "Ranking_FIIs";
END;
$$;
