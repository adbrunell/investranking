CREATE TABLE IF NOT EXISTS user_profiles (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE,
  nome TEXT NOT NULL DEFAULT '',
  estado TEXT NOT NULL DEFAULT '',
  cidade TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Usuarios veem apenas seu perfil"
  ON user_profiles FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Usuarios inserem apenas seu perfil"
  ON user_profiles FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Usuarios atualizam apenas seu perfil"
  ON user_profiles FOR UPDATE
  USING (auth.uid() = user_id);
