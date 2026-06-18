CREATE OR REPLACE FUNCTION fn_calcular_variacao_aovivo()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    r RECORD;
    last_ticker TEXT := '';
    last_price NUMERIC := NULL;
BEGIN
    FOR r IN
        SELECT codigo_instrumento, data_referencia, preco_ultimo_negocio
        FROM b3_cotacoes_aovivo
        ORDER BY codigo_instrumento, data_referencia ASC
    LOOP
        IF r.codigo_instrumento != last_ticker THEN
            last_ticker := r.codigo_instrumento;
            last_price := NULL;
        END IF;
        IF last_price IS NULL THEN
            UPDATE b3_cotacoes_aovivo
            SET fechamento_anterior = NULL,
                variacao = 0
            WHERE codigo_instrumento = r.codigo_instrumento
              AND data_referencia = r.data_referencia;
        ELSE
            UPDATE b3_cotacoes_aovivo
            SET fechamento_anterior = last_price,
                variacao = ROUND(((r.preco_ultimo_negocio - last_price) / last_price * 100)::numeric, 2)
            WHERE codigo_instrumento = r.codigo_instrumento
              AND data_referencia = r.data_referencia;
        END IF;
        last_price := r.preco_ultimo_negocio;
    END LOOP;
END;
$$;
