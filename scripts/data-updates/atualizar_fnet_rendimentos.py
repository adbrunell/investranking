"""Busca detalhes de rendimentos no FNET viewer page para docs sem rendimento preenchido."""
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

import httpx

_proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

from utils.scraper.config import config
from utils.scraper._fnet_base import _parse_date

TABELA = "fnet_tudo"
VIEWER_URL = "https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento"
MAX_WORKERS = 10
MAX_RETRIES = 1


def atualizar_minigrafico(updates):
    """Atualiza historico_minigrafico, rendimento_anterior e dividend_yield
    para os fundos que tiveram novos rendimentos extraídos."""
    from supabase import create_client
    supabase = create_client(config.supabase_url, config.supabase_key)
    h = {"apikey": config.supabase_key, "Authorization": f"Bearer {config.supabase_key}"}
    rest = f"{config.supabase_url}/rest/v1"

    fundos = set(u.get("codigo_fundo", "") for u in updates if u.get("codigo_fundo"))
    if not fundos:
        return

    base_cols = "fnet_documento_id,codigo_fundo,data_entrega,rendimento"
    for isin in fundos:
        try:
            r = httpx.get(
                f"{rest}/{TABELA}?select={base_cols}"
                f"&codigo_fundo=eq.{isin}"
                "&tipo_documento=like.*Rendimentos*"
                "&rendimento=not.is.null"
                "&order=data_entrega.asc",
                headers=h, timeout=30
            )
            if r.status_code not in (200, 206):
                continue
            rows = r.json()
            if len(rows) < 2:
                continue

            vals = [r["rendimento"] for r in rows]
            to_update = []
            for i, row in enumerate(rows):
                hist = vals[:i]
                ant = vals[i - 1] if i > 0 else None
                to_update.append({
                    "fnet_documento_id": row["fnet_documento_id"],
                    "historico_minigrafico": hist,
                    "rendimento_anterior": ant,
                })

            if to_update:
                supabase.table(TABELA).upsert(to_update, on_conflict="fnet_documento_id").execute()
                print(f"  [minigrafico] {isin}: {len(to_update)} registros atualizados", flush=True)
        except Exception as e:
            print(f"  [minigrafico] ERRO ao processar {isin}: {e}", flush=True)


def fetch_viewer(doc_id):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9",
    }
    try:
        with httpx.Client(verify=False, timeout=httpx.Timeout(5.0, connect=3.0)) as c:
            r = c.get(f"{VIEWER_URL}?id={doc_id}&cvm=true", headers=headers, follow_redirects=True)
            if r.status_code == 200 and len(r.text) > 200:
                return r.text
    except Exception:
        pass
    return None


def parse_rendimento(raw):
    if not raw:
        return None
    html = raw
    result = {"tipo": "", "valor": None, "data_com": None, "data_pagamento": None}

    # Detect tipo: check which column has the valor (Rendimento vs Amortização)
    m_valor_row = re.search(
        r'Valor\s+do\s+provento.*?</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>',
        html, re.DOTALL | re.IGNORECASE
    )
    if m_valor_row:
        rend_val = re.sub(r'<[^>]+>', '', m_valor_row.group(1)).strip()
        amort_val = re.sub(r'<[^>]+>', '', m_valor_row.group(2)).strip()
        if rend_val:
            result["tipo"] = "Dividendo"
        elif amort_val:
            result["tipo"] = "Amortização"

    clean = re.sub(r'<[^>]+>', ' ', html)
    clean = re.sub(r'\s+', ' ', clean)

    # Valor do provento (com ou sem decimal)
    m = re.search(r'Valor do provento.*?(\d+(?:[.,]\d+)?)', clean)
    if m:
        val = m.group(1).replace('.', '').replace(',', '.')
        try:
            result["valor"] = float(val)
        except:
            pass

    # Data com — linha "Data-base" ou "com" direito ao provento
    m_dc = re.search(r'(?:data[-\s]*base|com\s+direito).*?(\d{2}/\d{2}/\d{4})', clean, re.IGNORECASE)
    if m_dc:
        result["data_com"] = _parse_date(m_dc.group(1))

    # Data pagamento
    m_dp = re.search(r'Data do pagamento.*?(\d{2}/\d{2}/\d{4})', clean, re.IGNORECASE)
    if m_dp:
        result["data_pagamento"] = _parse_date(m_dp.group(1))

    if result["valor"] is not None:
        return result
    return None


def extrair_rendimentos(max_docs: int | None = None) -> int:
    from supabase import create_client
    supabase = create_client(config.supabase_url, config.supabase_key)
    h = {"apikey": config.supabase_key, "Authorization": f"Bearer {config.supabase_key}"}
    rest = f"{config.supabase_url}/rest/v1"

    print("Buscando rendimentos sem detalhes...", flush=True)
    docs = []
    off = 0
    limit = min(max_docs, 1000) if max_docs else 1000
    page_retries = 0
    while True:
        try:
            r = httpx.get(
                f"{rest}/{TABELA}?select=fnet_documento_id"
                "&categoria_documento=like.*Aviso*&tipo_documento=like.*Rendimentos*"
                "&rendimento=is.null"
                "&limit={limit}&offset={off}".format(limit=limit, off=off),
                headers={**h, "Prefer": "count=exact"}, timeout=30,
            )
            page_retries = 0
        except Exception as e:
            page_retries += 1
            if page_retries >= 3:
                print(f"  ERRO: falha na consulta apos 3 tentativas: {e}", flush=True)
                break
            print(f"  Aviso: erro na consulta (tentativa {page_retries}/3): {e}", flush=True)
            time.sleep(5)
            continue
        if r.status_code not in (200, 206):
            print(f"  ERRO: status {r.status_code} na consulta", flush=True)
            break
        rows = r.json()
        if not rows: break
        docs.extend(rows)
        if max_docs and len(docs) >= max_docs:
            docs = docs[:max_docs]
            break
        if len(rows) < 1000: break
        off += 1000

    print(f"  {len(docs)} docs sem rendimento para processar.", flush=True)
    if not docs:
        print("  Nenhum documento pendente. Todos os rendimentos ja foram processados!", flush=True)
        return 0

    total = len(docs)
    t0 = time.time()
    n_parsed = 0
    BATCH_SAVE = 500

    print(f"  Processando {total} docs em lotes de {BATCH_SAVE} com {MAX_WORKERS} workers...", flush=True)

    for batch_start in range(0, total, BATCH_SAVE):
        batch_end = min(batch_start + BATCH_SAVE, total)
        batch_docs = docs[batch_start:batch_end]
        updates = []
        batch_t0 = time.time()

        print(f"  Lote {batch_start+1}-{batch_end}/{total} — baixando {len(batch_docs)} docs...", flush=True)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exec:
            fut_map = {exec.submit(fetch_viewer, d["fnet_documento_id"]): d for d in batch_docs}
            batch_done = 0
            for fut in as_completed(fut_map):
                doc = fut_map[fut]
                raw = fut.result()
                batch_done += 1
                if raw:
                    parsed = parse_rendimento(raw)
                    if parsed and parsed["valor"] is not None:
                        n_parsed += 1
                        updates.append({
                            "fnet_documento_id": doc["fnet_documento_id"],
                            "tipo": str(parsed["tipo"]),
                            "rendimento": str(parsed["valor"]),
                            "data_com": parsed["data_com"],
                            "data_pagamento": parsed["data_pagamento"],
                        })
                if batch_done % 100 == 0:
                    print(f"    {batch_done}/{len(batch_docs)} do lote — {len(updates)} encontrados", flush=True)

        batch_elapsed = time.time() - batch_t0

        if updates:
            print(f"  Lote concluido em {batch_elapsed:.0f}s — salvando {len(updates)} rendimentos...", flush=True)
            supabase.table(TABELA).upsert(updates, on_conflict="fnet_documento_id").execute()
            # Busca codigo_fundo para cada update antes de chamar o minigrafico
            ids = [u["fnet_documento_id"] for u in updates]
            try:
                r = httpx.get(
                    f"{rest}/{TABELA}?select=fnet_documento_id,codigo_fundo"
                    f"&fnet_documento_id=in.({','.join(str(i) for i in ids)})",
                    headers=h, timeout=30
                )
                if r.status_code in (200, 206):
                    fundo_map = {d["fnet_documento_id"]: d["codigo_fundo"] for d in r.json()}
                    for u in updates:
                        u["codigo_fundo"] = fundo_map.get(u["fnet_documento_id"], "")
                    atualizar_minigrafico(updates)
            except Exception as e:
                print(f"  Aviso: falha ao buscar codigo_fundo: {e}", flush=True)
        else:
            print(f"  Lote concluido em {batch_elapsed:.0f}s — nenhum rendimento encontrado", flush=True)

        elapsed = time.time() - t0
        done = batch_end
        rate = done / elapsed if elapsed > 0 else 0
        remaining = (total - done) / rate if rate > 0 else 0
        print(f"  Total: {done}/{total} ({rate:.0f}/s, ETA {remaining:.0f}s) — {n_parsed} encontrados", flush=True)

    elapsed_total = time.time() - t0
    print(f"\nRESUMO: {n_parsed}/{total} rendimentos extraidos em {elapsed_total:.0f}s", flush=True)
    return n_parsed


if __name__ == "__main__":
    n = extrair_rendimentos()
    print(f"RESULT:OK({n})")
