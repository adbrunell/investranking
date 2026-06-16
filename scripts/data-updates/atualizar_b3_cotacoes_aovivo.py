"""Baixa trades intraday da B3 (RAPI, por ativo) e salva em b3_cotacoes_aovivo.
   Agrega por ticker: ultimo preco, volume total, quantidade total.
   URL: https://drp.b3.com.br/rapinegocios/tickercsv/{TICKER}/{DATE}?type=2"""
import io
import os
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

_proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

from utils.scraper.config import config

B3_URL_TPL = "https://drp.b3.com.br/rapinegocios/tickercsv/{ticker}/{date}?type=2"
TABLE = "b3_cotacoes_aovivo"
UNIQUE_KEYS = ["codigo_instrumento", "data_referencia"]
MAX_WORKERS = 10


def parse_br_decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def process_ticker(ticker: str, ref_date: date) -> dict | None:
    url = B3_URL_TPL.format(ticker=ticker, date=ref_date.isoformat())
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except Exception as e:
        print(f"  {ticker}: erro download - {e}", flush=True)
        return None

    zip_data = resp.content
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
            txt_name = None
            for name in z.namelist():
                if name.endswith(".txt"):
                    txt_name = name
                    break
            if not txt_name:
                return None
            with z.open(txt_name) as f:
                text = f.read().decode("utf-8-sig")
    except Exception as e:
        print(f"  {ticker}: erro zip - {e}", flush=True)
        return None

    reader = io.StringIO(text)
    reader.readline()

    total_qty = 0
    total_financial = Decimal("0")
    last_price = None
    last_time = None

    trade_count = 0
    for line in reader:
        line = line.strip()
        if not line:
            continue
        cols = line.split(";")
        if len(cols) < 6:
            continue

        raw_price = cols[3]
        raw_qty = cols[4]
        raw_time = cols[5]

        price = parse_br_decimal(raw_price)
        if price is None:
            continue

        try:
            qty = int(raw_qty)
        except ValueError:
            continue

        total_qty += qty
        total_financial += price * qty
        last_price = price
        trade_count += 1

        if len(raw_time) >= 6:
            h = raw_time[0:2]
            m = raw_time[2:4]
            s = raw_time[4:6]
            ms = raw_time[6:9] if len(raw_time) >= 9 else "000"
            last_time = f"{h}:{m}:{s}.{ms}"
        else:
            last_time = None

    if last_price is None or trade_count < 10:
        return None

    return {
        "codigo_instrumento": ticker,
        "data_referencia": ref_date.isoformat(),
        "preco_ultimo_negocio": str(last_price),
        "volume_total": str(total_financial),
        "quantidade_total": total_qty,
        "horario_ultima_transacao": last_time,
    }


def main():
    h = {"apikey": config.supabase_key, "Authorization": f"Bearer {config.supabase_key}"}
    rest = f"{config.supabase_url}/rest/v1"

    print("Carregando tickers da 00_Master...")
    tickers = set()
    off = 0
    while True:
        r = httpx.get(f"{rest}/00_Master?select=Ticker&limit=1000&offset={off}", headers={**h, "Prefer": "count=exact"}, timeout=30)
        if r.status_code not in (200, 206):
            break
        rows = r.json()
        if not rows:
            break
        for row in rows:
            t = row.get("Ticker")
            if t:
                tickers.add(t.strip().upper())
        if len(rows) < 1000:
            break
        off += 1000
    print(f"  {len(tickers)} tickers.")

    today = date.today()
    ref_date = today

    print(f"\n=== B3 Ao Vivo (por ativo) - {ref_date} ===")
    print(f"  Baixando {len(tickers)} tickers com {MAX_WORKERS} workers...", flush=True)

    rows = []
    total = len(tickers)
    done = 0
    t0 = __import__("time").time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exec:
        fut_map = {exec.submit(process_ticker, t, ref_date): t for t in tickers}
        for fut in as_completed(fut_map):
            ticker = fut_map[fut]
            done += 1
            result = fut.result()
            if result:
                rows.append(result)
            if done % 50 == 0 or done == total:
                elapsed = __import__("time").time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                remaining = (total - done) / rate if rate > 0 else 0
                print(f"    {done}/{total} ({rate:.0f}/s, ETA {remaining:.0f}s) — {len(rows)} com trades", flush=True)

    print(f"  {len(rows)} tickers com negociacao no dia.", flush=True)

    # Limpar dados do dia antes de inserir (mas depois do download, pra nao ficar sem base)
    httpx.delete(
        f"{rest}/{TABLE}?data_referencia=eq.{ref_date.isoformat()}",
        headers=h, timeout=30,
    )

    saved = 0
    for i in range(0, len(rows), 500):
        batch = rows[i:i + 500]
        r = httpx.post(
            f"{rest}/{TABLE}?on_conflict={','.join(UNIQUE_KEYS)}",
            json=batch, headers={**h, "Prefer": "resolution=merge-duplicates"},
            timeout=30,
        )
        if r.status_code not in (200, 201, 204):
            print(f"  ERRO upsert lote {i}: {r.status_code} {r.text[:200]}", flush=True)
        else:
            saved += len(batch)

    print(f"  Salvos {saved} registros.", flush=True)

    # Limpar dados antigos — manter apenas o dia atual
    del_resp = httpx.delete(
        f"{rest}/{TABLE}?data_referencia=lt.{ref_date.isoformat()}",
        headers=h, timeout=30,
    )
    if del_resp.status_code in (200, 204):
        print(f"  Dados anteriores a {ref_date} removidos.", flush=True)
    else:
        print(f"  Aviso: limpeza de dados antigos retornou {del_resp.status_code}", flush=True)

    print(f"RESULT:OK({saved})")


if __name__ == "__main__":
    main()
