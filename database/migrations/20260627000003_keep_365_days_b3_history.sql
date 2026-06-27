CREATE OR REPLACE FUNCTION fn_limpar_b3_historico()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    DELETE FROM b3_cotacoes_historico
    WHERE data < (CURRENT_DATE - INTERVAL '365 days');
END;
$$;

SELECT fn_limpar_b3_historico();
