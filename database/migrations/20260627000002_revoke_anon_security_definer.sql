-- Remove acesso anon a funções críticas (só service_role/chamadores autorizados mantêm)
REVOKE EXECUTE ON FUNCTION fn_deletar_conta() FROM anon;
REVOKE EXECUTE ON FUNCTION fn_refresh_ranking_fiis() FROM anon;
REVOKE EXECUTE ON FUNCTION fn_atualizar_minigrafico() FROM anon;
REVOKE EXECUTE ON FUNCTION fn_limpar_b3_historico() FROM anon;
REVOKE EXECUTE ON FUNCTION fn_calcular_variacao_aovivo() FROM anon;

-- fn_deletar_conta precisa continuar disponível para usuários logados (authenticated)
GRANT EXECUTE ON FUNCTION fn_deletar_conta() TO authenticated;
