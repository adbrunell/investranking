"""Check FNET first page per fund; upsert tudo (on_conflict)."""
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

_proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

_env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

from utils.scraper.config import config
from utils.scraper._fnet_base import _parse_date, _cookies_from_fnet

logger = logging.getLogger(__name__)

TABELA = "fnet_tudo"
FNET_AJAX = "https://fnet.bmfbovespa.com.br/fnet/publico/pesquisarGerenciadorDocumentosDados"
MAX_WORKERS = 25
TIMO = 5.0

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://fnet.bmfbovespa.com.br/fnet/publico/",
}


def _norm_cnpj(cnpj: str) -> str:
    d = re.sub(r"\D", "", cnpj or "")
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return d


def _cnpj_digits(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj or "")


def _parse_float(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", ".").replace("R$", "").replace(" ", "")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _scrape_todas_paginas(client: httpx.Client, fund: dict) -> list[dict]:
    """Pagina por todas as paginas do FNET para o fundo, retorna todos os docs."""
    cnpj_raw = _cnpj_digits(fund["cnpj"])
    CAT_KEEP = {
        "Aviso aos Cotistas - Estruturado": {"Rendimentos e Amortizações"},
        "Relatórios": {"Relatório Gerencial"},
        "Fato Relevante": set(),
    }
    LIMIT = 100
    todos_docs = []
    offset = 0

    while True:
        params = {
            "d": "1", "s": str(offset), "l": str(LIMIT),
            "cnpjFundo": cnpj_raw,
            "o[0][dataReferencia]": "desc",
            "_": str(int(time.time() * 1000)),
        }
        try:
            resp = client.get(FNET_AJAX, params=params, headers=_HEADERS, timeout=TIMO * 2)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break

        if not data or not data.get("data"):
            break

        rows = data["data"]
        for row in rows:
            fid = str(row.get("id", ""))
            if not fid:
                continue
            cat = (row.get("categoriaDocumento") or "").strip()
            tdoc = (row.get("tipoDocumento") or "").strip()
            tipos_esperados = CAT_KEEP.get(cat)
            if tipos_esperados is None:
                continue
            if tipos_esperados and tdoc not in tipos_esperados:
                continue
            todos_docs.append({
                "fnet_documento_id": fid,
                "codigo_fundo": fund.get("codigo_fundo", ""),
                "cnpj": fund.get("cnpj", ""),
                "codigo_isin": fund.get("codigo_isin", ""),
                "nome_oficial": fund.get("nome_oficial", ""),
                "nome_pregao": row.get("nomePregao") or "",
                "nome_fundo": row.get("descricaoFundo", ""),
                "categoria_documento": row.get("categoriaDocumento") or "",
                "tipo_documento": row.get("tipoDocumento") or "",
                "especie_documento": row.get("especieDocumento") or "",
                "data_referencia": _parse_date(row.get("dataReferencia", "")),
                "data_entrega": _parse_date(row.get("dataEntrega", "")),
                "status": row.get("status", ""),
                "descricao_status": row.get("descricaoStatus") or "",
                "versao": int(row.get("versao", 0)) if row.get("versao") else 0,
                "modalidade": row.get("modalidade") or "",
                "descricao_modalidade": row.get("descricaoModalidade") or "",
                "link_documento": f"https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id={fid}",
                "link_visualizar": f"https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id={fid}&cvm=true",
                "situacao_documento": row.get("situacaoDocumento") or "",
                "analisado": row.get("analisado") == "S",
                "fundo_ou_classe": row.get("fundoOuClasse") or "",
                "informacoes_adicionais": row.get("informacoesAdicionais") or "",
                "arquivo_estruturado": row.get("arquivoEstruturado") or "",
                "nome_fundo_documento": row.get("nomeFundoDocumento") or "",
            })

        if len(rows) < LIMIT:
            break
        offset += LIMIT

    return todos_docs


def extract(max_funds: int | None = None) -> list[dict]:
    """Scrape FNET first page per fund concurrentemente;
       retorna apenas docs NOVOS (nao existentes no BD)."""
    print("Carregando lista de fundos...", file=sys.stderr)
    h = {"apikey": config.supabase_key, "Authorization": f"Bearer {config.supabase_key}"}
    rest = f"{config.supabase_url}/rest/v1"

    print("Buscando fundos com ISIN na planilha master...", file=sys.stderr)
    resp = httpx.get(
        f"{rest}/00_fundos_master"
        "?select=ticker,cnpj,codigo_isin"
        "&codigo_isin=not.is.null&codigo_isin=neq."
        "&cnpj=not.is.null&cnpj=neq."
        "&limit=5000",
        headers=h, timeout=30,
    )
    if resp.status_code != 200:
        print("ERRO: nao foi possivel carregar 00_fundos_master", file=sys.stderr)
        return []

    fundos = []
    for row in resp.json():
        cnpj = _norm_cnpj(row.get("cnpj", ""))
        ticker = (row.get("ticker") or "").strip()
        isin = (row.get("codigo_isin") or "").strip()
        if len(cnpj) == 18 and ticker and isin:
            fundos.append({
                "cnpj": cnpj,
                "codigo_fundo": ticker,
                "codigo_isin": isin,
                "nome_oficial": "",
            })

    if not fundos:
        print("Nenhum fundo com ISIN encontrado.", file=sys.stderr)
        return []

    if max_funds:
        fundos = fundos[:max_funds]

    print(f"{len(fundos)} fundos com ISIN. Buscando todas as paginas no FNET de cada (concorrente, max {MAX_WORKERS})...",
          file=sys.stderr)

    # Get FNET session cookies first
    cookies = _cookies_from_fnet()
    if cookies:
        print(f"Cookies FNET obtidos: {len(cookies)}", file=sys.stderr)

    todos_docs: list[dict] = []
    total = len(fundos)

    with httpx.Client(verify=False, cookies=cookies) as client:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exec:
            fut_map = {exec.submit(_scrape_todas_paginas, client, f): f for f in fundos}
            done = 0
            for fut in as_completed(fut_map):
                docs = fut.result()
                if docs:
                    todos_docs.extend(docs)
                done += 1
                if done % 10 == 0 or done == total:
                    pct = f"{done}/{total}"
                    print(f"  FNET {pct} fundos ({len(todos_docs)} docs acumulados)", file=sys.stderr, flush=True)

    return todos_docs


def upsert_docs(docs: list[dict]) -> int:
    """Upsert batch em lote."""
    from supabase import create_client
    supabase = create_client(config.supabase_url, config.supabase_key)
    total = 0
    if docs:
        print(f"Salvando {len(docs)} documentos no banco...", file=sys.stderr, flush=True)
        # deduplicate by fnet_documento_id
        seen = {}
        for d in docs:
            fid = d.get("fnet_documento_id")
            if fid and fid not in seen:
                seen[fid] = d
        unique = list(seen.values())
        if len(unique) < len(docs):
            print(f"  Removidas {len(docs)-len(unique)} duplicatas", file=sys.stderr, flush=True)
        batch_size = 2000
        for i in range(0, len(unique), batch_size):
            batch = unique[i:i + batch_size]
            try:
                supabase.table(TABELA).upsert(batch, on_conflict="fnet_documento_id").execute()
                total += len(batch)
            except Exception as e:
                print(f"  Erro no lote {i}: {e}", file=sys.stderr, flush=True)
            print(f"  Salvos {total}/{len(unique)}", file=sys.stderr, flush=True)

    # Extrair detalhes de rendimentos do viewer FNET
    try:
        from atualizar_fnet_rendimentos import extrair_rendimentos
        extrair_rendimentos(max_docs=500)
    except Exception as e:
        logger.warning("Falha ao extrair detalhes de rendimentos: %s", e)

    return total





if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
    docs = extract()
    total = upsert_docs(docs)
    print(f"RESULT:OK({total})")
