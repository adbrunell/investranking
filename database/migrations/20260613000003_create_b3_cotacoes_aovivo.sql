CREATE TABLE IF NOT EXISTS b3_cotacoes_aovivo (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo_instrumento TEXT NOT NULL,
    data_referencia DATE NOT NULL,
    preco_ultimo_negocio NUMERIC(18, 4),
    volume_total NUMERIC(18, 2),
    quantidade_total BIGINT,
    horario_ultima_transacao TIME,
    atualizado_em TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (codigo_instrumento, data_referencia)
);

ALTER TABLE b3_cotacoes_aovivo ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Todos podem ler b3_cotacoes_aovivo"
    ON b3_cotacoes_aovivo FOR SELECT
    USING (true);

CREATE POLICY "Servico pode inserir b3_cotacoes_aovivo"
    ON b3_cotacoes_aovivo FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Servico pode atualizar b3_cotacoes_aovivo"
    ON b3_cotacoes_aovivo FOR UPDATE
    USING (true)
    WITH CHECK (true);
