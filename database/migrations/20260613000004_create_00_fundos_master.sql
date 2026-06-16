CREATE TABLE IF NOT EXISTS "00_fundos_master" (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticker TEXT NOT NULL UNIQUE,
    segmento TEXT,
    tipo TEXT,
    cnpj TEXT,
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE "00_fundos_master" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Todos podem ler 00_fundos_master"
    ON "00_fundos_master" FOR SELECT
    USING (true);

CREATE POLICY "Servico pode inserir 00_fundos_master"
    ON "00_fundos_master" FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Servico pode atualizar 00_fundos_master"
    ON "00_fundos_master" FOR UPDATE
    USING (true)
    WITH CHECK (true);

DROP TABLE IF EXISTS master_fundos;
