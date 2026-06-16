"""Download COTAHIST da B3 e extrai OHLCV+ISIN para TODOS os tickers da 00_Master.
   ZIPs ficam salvos em data_b3/ para reuso. Ano atual: download condicional."""
import os
import sys
import zipfile
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

_proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

from utils.scraper.config import config

TABELA = "b3_cotacoes_historico"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data_b3")
B3_URL = "https://bvmf.bmfbovespa.com.br/en-us/historical-quotes/FormConsultaValidaI.asp"


def parse_price(s):
    try: return int(s.strip()) / 100
    except: return None

def parse_volume(s):
    try: return int(s.strip()) / 100
    except: return None

def parse_data(s):
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def precisa_baixar(ano: int) -> bool:
    """Anos passados: baixa se ZIP nao existe. Ano atual: baixa se ultima data no BD < hoje."""
    zip_path = os.path.join(DATA_DIR, f"COTAHIST_A{ano}.ZIP")
    if os.path.exists(zip_path):
        if ano < datetime.now().year:
            return False
        # Ano atual: verificar se dados estao atualizados
        h = {"apikey": config.supabase_key, "Authorization": f"Bearer {config.supabase_key}"}
        rest = f"{config.supabase_url}/rest/v1"
        r = httpx.get(
            f"{rest}/{TABELA}?select=data&order=data.desc&limit=1",
            headers=h, timeout=30,
        )
        if r.status_code == 200 and r.json():
            ultima = r.json()[0].get("data", "")
            if ultima:
                ultima_dt = datetime.strptime(ultima[:10], "%Y-%m-%d").date()
                if ultima_dt >= date.today():
                    return False
        return True
    return True


def download(ano: int) -> str | None:
    from playwright.sync_api import sync_playwright

    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f"COTAHIST_A{ano}.ZIP"
    filepath = os.path.join(DATA_DIR, filename)

    print(f"  Baixando {filename} (resolva o captcha)...", flush=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        try:
            page.goto(f"{B3_URL}?arq={filename}", timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            print("  Resolva o captcha e clique em Download...", flush=True)
            with page.expect_download(timeout=300000) as download_info:
                page.wait_for_function("() => document.readyState === 'complete'", timeout=300000)
            download = download_info.value
            download.save_as(filepath)
            print(f"  OK", flush=True)
            return filepath
        except Exception as e:
            print(f"  Erro: {e}", flush=True)
            return None
        finally:
            browser.close()


def extrair(zip_path, tickers):
    registros = []
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.upper().endswith(".TXT")]
        txt = z.read(names[0]).decode("latin1")

    for line in txt.splitlines():
        if not line.startswith("01"):
            continue
        t = line[12:24].strip()
        if t not in tickers:
            continue
        registros.append({
            "ticker": t,
            "data": parse_data(line[2:10]),
            "abertura": parse_price(line[56:69]),
            "maximo": parse_price(line[69:82]),
            "minimo": parse_price(line[82:95]),
            "fechamento": parse_price(line[108:121]),
            "volume": parse_volume(line[170:188]),
            "isin": line[230:242].strip(),
        })
    return registros


def main():
    from supabase import create_client
    supabase = create_client(config.supabase_url, config.supabase_key)

    h = {"apikey": config.supabase_key, "Authorization": f"Bearer {config.supabase_key}"}
    rest = f"{config.supabase_url}/rest/v1"
    anos = [datetime.now().year]

    # 1. Carregar todos os tickers (paginado)
    print("[1/4] Carregando tickers da 00_Master...", flush=True)
    tickers = set()
    off = 0
    while True:
        r = httpx.get(f"{rest}/00_Master?select=Ticker&limit=1000&offset={off}", headers={**h, "Prefer": "count=exact"}, timeout=30)
        if r.status_code not in (200, 206): break
        rows = r.json()
        if not rows: break
        for row in rows:
            t = row.get("Ticker")
            if t: tickers.add(t.strip().upper())
        if len(rows) < 1000: break
        off += 1000
    print(f"  -> {len(tickers)} tickers.", flush=True)

    # 2. Baixar ZIPS que faltam
    print(f"[2/4] Verificando arquivos em data_b3/...", flush=True)
    zips = []
    for ano in anos:
        if precisa_baixar(ano):
            p = download(ano)
            if p: zips.append(p)
        else:
            p = os.path.join(DATA_DIR, f"COTAHIST_A{ano}.ZIP")
            zips.append(p)
            print(f"  COTAHIST_A{ano}.ZIP ja em data_b3/", flush=True)

    if not zips:
        print("Nenhum ZIP disponivel.", flush=True)
        return

    # 3. Extrair de cada ano e upsert direto
    print(f"[3/4] Extraindo registros...", flush=True)
    total_ok = 0

    for zp in zips:
        nome = os.path.basename(zp)
        ano = nome.replace("COTAHIST_A", "").replace(".ZIP", "")
        print(f"  {nome}...", flush=True)
        regs = extrair(zp, tickers)
        if not regs:
            print(f"    -> 0 registros", flush=True)
            continue
        print(f"    -> {len(regs)} registros, salvando...", flush=True)

        for i in range(0, len(regs), 500):
            batch = regs[i:i+500]
            try:
                supabase.table(TABELA).upsert(batch, on_conflict="ticker,data").execute()
                total_ok += len(batch)
            except Exception as e:
                print(f"    Erro lote {i}: {e}", flush=True)

    print(f"\nRESULT:OK({total_ok})", flush=True)


if __name__ == "__main__":
    main()
