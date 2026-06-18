CREATE OR REPLACE FUNCTION fn_atualizar_minigrafico()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    r RECORD;
    last_fundo TEXT := '';
    rends NUMERIC[] := '{}';
BEGIN
    FOR r IN
        SELECT fnet_documento_id, codigo_fundo, rendimento
        FROM fnet_tudo
        WHERE tipo_documento LIKE '%Rendimentos%'
          AND rendimento IS NOT NULL
          AND codigo_fundo IS NOT NULL
        ORDER BY codigo_fundo, data_entrega ASC, fnet_documento_id ASC
    LOOP
        IF r.codigo_fundo != last_fundo THEN
            last_fundo := r.codigo_fundo;
            rends := '{}';
        END IF;
        UPDATE fnet_tudo
        SET historico_minigrafico = to_jsonb(rends),
            rendimento_anterior = CASE WHEN array_length(rends, 1) > 0 THEN rends[array_length(rends, 1)] ELSE NULL END
        WHERE fnet_documento_id = r.fnet_documento_id;
        rends := rends || r.rendimento;
        IF array_length(rends, 1) > 36 THEN
            rends := rends[array_length(rends, 1) - 35 : array_length(rends, 1)];
        END IF;
    END LOOP;
END;
$$;
