CREATE TABLE IF NOT EXISTS "00.log_atualizacao" (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    script_name TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_log_script_name ON "00.log_atualizacao" (script_name);
CREATE INDEX IF NOT EXISTS idx_log_finished_at ON "00.log_atualizacao" (finished_at DESC);

ALTER TABLE "00.log_atualizacao" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Todos podem ler 00.log_atualizacao"
    ON "00.log_atualizacao" FOR SELECT
    USING (true);

CREATE POLICY "Servico pode inserir 00.log_atualizacao"
    ON "00.log_atualizacao" FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Servico pode atualizar 00.log_atualizacao"
    ON "00.log_atualizacao" FOR UPDATE
    USING (true)
    WITH CHECK (true);
