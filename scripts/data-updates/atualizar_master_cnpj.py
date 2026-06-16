"""Busca CNPJ no Investidor10 para codigos sem CNPJ na view 00_Master.
   Salva em 00_Master_cnpj (usado como fallback pela view).
   Uso: python scripts/data-updates/atualizar_master_cnpj.py"""
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

_proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

from utils.scraper.config import config

logger = logging.getLogger(__name__)

MAX_WORKERS = 10
TIMO = 8.0

URLS = {
    "Ação": "https://investidor10.com.br/acoes/{}/",
    "FII": "https://investidor10.com.br/fiis/{}/",
    "Fiagro": "https://investidor10.com.br/fiis/{}/",
    "FI-Infra": "https://investidor10.com.br/fiis/{}/",
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

CNPJ_RE = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")


def _buscar_cnpj(client: httpx.Client, classe: str, ticker: str) -> str | None:
    url = URLS[classe].format(ticker.lower())
    try:
        resp = client.get(url, headers=_HEADERS, timeout=TIMO, follow_redirects=True)
        if resp.status_code != 200:
            return None
        match = CNPJ_RE.search(resp.text)
        return match.group(0) if match else None
    except Exception:
        return None


def main():
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")

    h = {"apikey": config.supabase_key, "Authorization": f"Bearer {config.supabase_key}"}
    rest = f"{config.supabase_url}/rest/v1"

    print("Buscando codigos sem CNPJ na 00_Master...", file=sys.stderr)
    resp = httpx.get(
        f"{rest}/00_Master?select=Classe,Ticker&CNPJ=is.null",
        headers=h, timeout=30,
    )
    if resp.status_code != 200:
        print(f"ERRO: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
        return
    rows = resp.json()

    if not rows:
        print("Nenhum codigo sem CNPJ encontrado.", file=sys.stderr)
        return

    pendentes = [(r["Ticker"], r["Classe"]) for r in rows]
    print(f"{len(pendentes)} codigos sem CNPJ. Buscando no Investidor10...", file=sys.stderr)

    resultados: list[dict] = []
    total = len(pendentes)

    with httpx.Client(verify=False) as client:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exec:
            fut_map = {}
            for ticker, classe in pendentes:
                fut = exec.submit(_buscar_cnpj, client, classe, ticker)
                fut_map[fut] = (ticker, classe)

            done = 0
            encontrados = 0
            for fut in as_completed(fut_map):
                ticker, classe = fut_map[fut]
                cnpj = fut.result()
                if cnpj:
                    resultados.append({
                        "ticker": ticker,
                        "classe": classe,
                        "cnpj": cnpj,
                    })
                    encontrados += 1
                done += 1
                if done % 50 == 0 or done == total:
                    print(f"  {done}/{total} — encontrados {encontrados} CNPJs", file=sys.stderr)

    if not resultados:
        print("Nenhum CNPJ encontrado.", file=sys.stderr)
        return

    print(f"Salvando {len(resultados)} CNPJs no banco...", file=sys.stderr)
    from supabase import create_client
    supabase = create_client(config.supabase_url, config.supabase_key)

    for i in range(0, len(resultados), 500):
        batch = resultados[i:i + 500]
        supabase.table("00_Master_cnpj").upsert(batch, on_conflict="ticker").execute()

    print(f"RESULT:OK({encontrados}/{total})", file=sys.stderr)


if __name__ == "__main__":
    main()
