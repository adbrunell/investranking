"""Baixa trades intraday da B3 e mantém últimos 2 pregões em b3_cotacoes_aovivo.

   Durante o dia: baixa ticker a ticker (RAPI).
   Fim do dia: arquivo bulk disponível, substitui dados do dia.
   Mantém sempre os 2 últimos pregões. Calcula variação com base na tabela.
"""
import io
import os
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import httpx

_proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

# Carrega .env pro caso de execucao direta
_env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

from utils.scraper.config import config

BULK_URL_TPL = "https://drp.b3.com.br/rapinegocios/tickercsv/{date}?type=2"
TICKER_URL_TPL = "https://drp.b3.com.br/rapinegocios/tickercsv/{ticker}/{date}?type=2"
TABLE = "b3_cotacoes_aovivo"
UNIQUE_KEYS = ["codigo_instrumento", "data_referencia"]
MAX_WORKERS = 10
SKIP_TRADES_IF_BELOW = 10


def parse_br_decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def parse_hora(raw: str) -> str | None:
    if len(raw) >= 6:
        h = raw[0:2]
        m = raw[2:4]
        s = raw[4:6]
        ms = raw[6:9] if len(raw) >= 9 else "000"
        return f"{h}:{m}:{s}.{ms}"
    return None


def parse_bulk_row(line: str) -> dict | None:
    cols = line.split(";")
    if len(cols) < 6:
        return None
    ticker = cols[1].strip().upper()
    if not ticker:
        return None
    price = parse_br_decimal(cols[3])
    if price is None:
        return None
    try:
        qty = int(cols[4])
    except ValueError:
        return None
    hora = parse_hora(cols[5])
    if qty < SKIP_TRADES_IF_BELOW:
        return None
    return {
        "codigo_instrumento": ticker,
        "data_referencia": cols[0],
        "preco_ultimo_negocio": str(price),
        "volume_total": str(price * qty),
        "quantidade_total": qty,
        "horario_ultima_transacao": hora,
    }


def get_tickers_set():
    """Retorna set de tickers da view 00_Master."""
    h = {"apikey": config.supabase_key, "Authorization": f"Bearer {config.supabase_key}"}
    rest = f"{config.supabase_url}/rest/v1"
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
    return tickers


def download_bulk(ref_date: date) -> list[dict] | None:
    """Tenta baixar arquivo bulk do dia. Retorna lista de registros ou None."""
    url = BULK_URL_TPL.format(date=ref_date.isoformat())
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=60)
        if resp.status_code != 200:
            return None
    except Exception:
        return None

    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            txt_name = None
            for name in z.namelist():
                if name.endswith(".txt"):
                    txt_name = name
                    break
            if not txt_name:
                return None
            with z.open(txt_name) as f:
                text = f.read().decode("utf-8-sig")
    except Exception:
        return None

    reader = io.StringIO(text)
    reader.readline()

    agg = {}
    for line in reader:
        line = line.strip()
        if not line:
            continue
        row = parse_bulk_row(line)
        if not row:
            continue
        t = row["codigo_instrumento"]
        if t not in agg:
            agg[t] = {k: row[k] for k in row}
            agg[t]["quantidade_total"] = row["quantidade_total"]
            agg[t]["volume_total"] = Decimal(row["volume_total"])
        else:
            agg[t]["quantidade_total"] += row["quantidade_total"]
            agg[t]["volume_total"] = Decimal(str(agg[t]["volume_total"])) + Decimal(row["volume_total"])
            last_p = parse_br_decimal(row["preco_ultimo_negocio"])
            if last_p:
                agg[t]["preco_ultimo_negocio"] = str(last_p)
                agg[t]["horario_ultima_transacao"] = row["horario_ultima_transacao"]

    master_tickers = get_tickers_set()
    result = []
    for t, d in agg.items():
        if t not in master_tickers:
            continue
        if d["quantidade_total"] < SKIP_TRADES_IF_BELOW:
            continue
        d["volume_total"] = str(d["volume_total"])
        result.append(d)
    return result


def process_ticker(ticker: str, ref_date: date) -> dict | None:
    url = TICKER_URL_TPL.format(ticker=ticker, date=ref_date.isoformat())
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except Exception as e:
        print(f"  {ticker}: erro download - {e}", flush=True)
        return None

    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
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
        price = parse_br_decimal(cols[3])
        if price is None:
            continue
        try:
            qty = int(cols[4])
        except ValueError:
            continue
        total_qty += qty
        total_financial += price * qty
        last_price = price
        trade_count += 1
        last_time = parse_hora(cols[5])

    if last_price is None or trade_count < SKIP_TRADES_IF_BELOW:
        return None

    return {
        "codigo_instrumento": ticker,
        "data_referencia": ref_date.isoformat(),
        "preco_ultimo_negocio": str(last_price),
        "volume_total": str(total_financial),
        "quantidade_total": total_qty,
        "horario_ultima_transacao": last_time,
    }


def get_tickers():
    h = {"apikey": config.supabase_key, "Authorization": f"Bearer {config.supabase_key}"}
    rest = f"{config.supabase_url}/rest/v1"
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
    return tickers


def save_to_db(rows, ref_date):
    h = {"apikey": config.supabase_key, "Authorization": f"Bearer {config.supabase_key}"}
    rest = f"{config.supabase_url}/rest/v1"
    # Remove dados do dia para substituir
    httpx.delete(f"{rest}/{TABLE}?data_referencia=eq.{ref_date}", headers=h, timeout=30)
    saved = 0
    for i in range(0, len(rows), 500):
        batch = rows[i:i + 500]
        r = httpx.post(
            f"{rest}/{TABLE}?on_conflict={','.join(UNIQUE_KEYS)}",
            json=batch, headers={**h, "Prefer": "resolution=merge-duplicates"},
            timeout=30,
        )
        if r.status_code in (200, 201, 204):
            saved += len(batch)
    return saved


def calcular_variacoes():
    """Delegado para o banco: fn_calcular_variacao_aovivo() via RPC."""
    h = {"apikey": config.supabase_key, "Authorization": f"Bearer {config.supabase_key}"}
    rest = f"{config.supabase_url}/rest/v1"
    try:
        r = httpx.post(f"{rest}/rpc/fn_calcular_variacao_aovivo", headers=h, timeout=120)
        if r.status_code in (200, 201, 204):
            print("  Variacoes calculadas pelo banco.", flush=True)
        else:
            print(f"  [var] RPC retornou {r.status_code}", flush=True)
    except Exception as e:
        print(f"  ERRO ao calcular variacoes: {e}", flush=True)


def main():
    today = date.today()
    yesterday = today - timedelta(days=1)

    # Tenta bulk primeiro
    print(f"\n=== B3 Ao Vivo - {today} ===", flush=True)
    data_today = download_bulk(today)

    if data_today:
        print(f"  Bulk disponivel: {len(data_today)} tickers.", flush=True)
    else:
        print("  Bulk indisponivel — baixando ticker a ticker...", flush=True)
        tickers = get_tickers_set()
        print(f"  {len(tickers)} tickers carregados.", flush=True)
        data_today = []
        total = len(tickers)
        done = 0
        t0 = __import__("time").time()
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exec:
            fut_map = {exec.submit(process_ticker, t, today): t for t in tickers}
            for fut in as_completed(fut_map):
                done += 1
                result = fut.result()
                if result:
                    data_today.append(result)
                if done % 50 == 0 or done == total:
                    elapsed = __import__("time").time() - t0
                    rate = done / elapsed if elapsed > 0 else 0
                    remaining = (total - done) / rate if rate > 0 else 0
                    print(f"    {done}/{total} ({rate:.0f}/s, ETA {remaining:.0f}s) — {len(data_today)} com trades", flush=True)
        print(f"  {len(data_today)} tickers com negociacao.", flush=True)

    saved_today = save_to_db(data_today, today.isoformat())
    print(f"  Salvos {saved_today} registros para {today}.", flush=True)

    # Garante que o pregão anterior existe na tabela
    h = {"apikey": config.supabase_key, "Authorization": f"Bearer {config.supabase_key}"}
    rest = f"{config.supabase_url}/rest/v1"
    r = httpx.get(f"{rest}/{TABLE}?select=data_referencia&limit=1&order=data_referencia.desc&data_referencia=lt.{today}", headers=h, timeout=30)
    has_prev = r.status_code == 200 and len(r.json()) > 0

    if not has_prev:
        print(f"\n  Tabela vazia — populando pregão anterior ({yesterday})...", flush=True)
        data_yest = download_bulk(yesterday)
        if not data_yest:
            print(f"  Bulk para {yesterday} indisponivel — ticker a ticker...", flush=True)
            tickers = get_tickers_set()
            data_yest = []
            t0 = __import__("time").time()
            total = len(tickers)
            done = 0
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exec:
                fut_map = {exec.submit(process_ticker, t, yesterday): t for t in tickers}
                for fut in as_completed(fut_map):
                    done += 1
                    result = fut.result()
                    if result:
                        data_yest.append(result)
        if data_yest:
            saved_yest = save_to_db(data_yest, yesterday.isoformat())
            print(f"  Salvos {saved_yest} registros para {yesterday}.", flush=True)

    # Mantém apenas os 2 últimos pregões
    r_dates = httpx.get(f"{rest}/{TABLE}?select=data_referencia&limit=1000&order=data_referencia.desc", headers=h, timeout=30)
    dates = sorted(set(d["data_referencia"] for d in r_dates.json()))
    if len(dates) > 2:
        keep = dates[-2:]
        for d in dates[:-2]:
            httpx.delete(f"{rest}/{TABLE}?data_referencia=eq.{d}", headers=h, timeout=30)
        print(f"  Mantidos apenas os 2 ultimos pregoes: {keep}", flush=True)

    # Calcula variações
    calcular_variacoes()

    total_rows = len(data_today)
    print(f"RESULT:OK({total_rows})")


if __name__ == "__main__":
    main()
