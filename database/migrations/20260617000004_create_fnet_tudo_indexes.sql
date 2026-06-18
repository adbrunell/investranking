CREATE INDEX IF NOT EXISTS idx_fnet_tudo_cat_sit_data
  ON fnet_tudo (categoria_documento, situacao_documento, data_entrega DESC);

CREATE INDEX IF NOT EXISTS idx_fnet_tudo_tipodoc_tipo_sit_data
  ON fnet_tudo (tipo_documento, tipo, situacao_documento, data_entrega DESC);

CREATE INDEX IF NOT EXISTS idx_fnet_tudo_codigo_fundo
  ON fnet_tudo (codigo_fundo);
