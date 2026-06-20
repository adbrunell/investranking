CREATE TABLE IF NOT EXISTS user_ativos (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL,
  quantidade NUMERIC NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, ticker)
);

ALTER TABLE user_ativos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Usuarios veem apenas seus proprios ativos"
  ON user_ativos FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Usuarios inserem apenas seus proprios ativos"
  ON user_ativos FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Usuarios atualizam apenas seus proprios ativos"
  ON user_ativos FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Usuarios deletam apenas seus proprios ativos"
  ON user_ativos FOR DELETE
  USING (auth.uid() = user_id);
