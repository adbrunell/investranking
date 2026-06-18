CREATE TABLE IF NOT EXISTS setups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    nome TEXT NOT NULL DEFAULT 'Setup sem nome',
    filtros JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE setups ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Usuarios podem criar seus proprios setups"
    ON setups FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Usuarios podem ver seus proprios setups"
    ON setups FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Usuarios podem atualizar seus proprios setups"
    ON setups FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Usuarios podem deletar seus proprios setups"
    ON setups FOR DELETE
    USING (auth.uid() = user_id);
