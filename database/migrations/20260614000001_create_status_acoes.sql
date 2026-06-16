CREATE TABLE IF NOT EXISTS status_acoes (
    ticker TEXT PRIMARY KEY,
    empresa TEXT,
    preco NUMERIC(18, 4),
    dy NUMERIC(18, 4),
    p_l NUMERIC(18, 4),
    p_vp NUMERIC(18, 4),
    p_ebit NUMERIC(18, 4),
    p_ativo NUMERIC(18, 4),
    ev_ebit NUMERIC(18, 4),
    margem_bruta NUMERIC(18, 4),
    margem_ebit NUMERIC(18, 4),
    margem_liquida NUMERIC(18, 4),
    p_sr NUMERIC(18, 4),
    p_capital_giro NUMERIC(18, 4),
    p_ativo_circulante NUMERIC(18, 4),
    giro_ativos NUMERIC(18, 4),
    roe NUMERIC(18, 4),
    roa NUMERIC(18, 4),
    roic NUMERIC(18, 4),
    divida_liquida_patrimonio NUMERIC(18, 4),
    divida_liquida_ebit NUMERIC(18, 4),
    pl_ativo NUMERIC(18, 4),
    passivo_ativo NUMERIC(18, 4),
    liquidez_corrente NUMERIC(18, 4),
    peg_ratio NUMERIC(18, 4),
    receitas_cagr5 NUMERIC(18, 4),
    lucros_cagr5 NUMERIC(18, 4),
    liquidez_media_diaria NUMERIC(18, 4),
    vpa NUMERIC(18, 4),
    lpa NUMERIC(18, 4),
    valor_mercado NUMERIC(18, 4),
    data_atualizacao TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE status_acoes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Todos podem ler status_acoes"
    ON status_acoes FOR SELECT
    USING (true);

CREATE POLICY "Servico pode inserir status_acoes"
    ON status_acoes FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Servico pode atualizar status_acoes"
    ON status_acoes FOR UPDATE
    USING (true)
    WITH CHECK (true);
