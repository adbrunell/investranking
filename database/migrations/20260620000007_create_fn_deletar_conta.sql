CREATE OR REPLACE FUNCTION fn_deletar_conta()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid uuid := auth.uid();
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'Não autenticado';
  END IF;
  DELETE FROM user_ativos WHERE user_id = uid;
  DELETE FROM user_profiles WHERE user_id = uid;
  DELETE FROM setups WHERE user_id = uid;
  DELETE FROM auth.users WHERE id = uid;
END;
$$;
