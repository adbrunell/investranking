CREATE TABLE IF NOT EXISTS status_dividendos (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo_ativo TEXT NOT NULL,
    ticker TEXT NOT NULL,
    tipo_provento TEXT,
    data_com DATE,
    data_pagamento DATE,
    valor NUMERIC(18, 6),
    rendimento NUMERIC(18, 4),
    data_atualizacao TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (ticker, data_com, tipo_provento, tipo_ativo)
);

ALTER TABLE status_dividendos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Todos podem ler status_dividendos"
    ON status_dividendos FOR SELECT
    USING (true);

CREATE POLICY "Servico pode inserir status_dividendos"
    ON status_dividendos FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Servico pode atualizar status_dividendos"
    ON status_dividendos FOR UPDATE
    USING (true)
    WITH CHECK (true);
