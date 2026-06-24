"""Busca COTAHIST do Google Drive, extrai OHLCV+ISIN dos tickers da 00_Master."""
import os, sys, io, zipfile
from datetime import datetime, date

import httpx
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

_proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

from utils.scraper.config import config

TABELA = "b3_cotacoes_historico"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data_b3")
DRIVE_KEY = os.path.join(os.path.dirname(__file__), "gdrive-key.json")
FOLDER_NAME = "COTAHIST"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# ─── parsing ─────────────────────────────────────

def parse_price(s):
    try: return int(s.strip()) / 100
    except: return None

def parse_volume(s):
    try: return int(s.strip()) / 100
    except: return None

def parse_data(s):
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"

# ─── Google Drive ────────────────────────────────

def get_drive_service():
    if not os.path.exists(DRIVE_KEY):
        raise FileNotFoundError(f"Arquivo de chave nao encontrado: {DRIVE_KEY}")
    creds = service_account.Credentials.from_service_account_file(DRIVE_KEY, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)

def find_zip(service, ano):
    filename = f"COTAHIST_A{ano}.ZIP"
    folders = service.files().list(
        q=f"name='{FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id)", pageSize=1
    ).execute()
    files = folders.get("files", [])
    if not files:
        raise Exception(f"Pasta '{FOLDER_NAME}' nao encontrada no Drive")
    folder_id = files[0]["id"]

    result = service.files().list(
        q=f"name='{filename}' and '{folder_id}' in parents and trashed=false",
        fields="files(id,modifiedTime)", pageSize=1
    ).execute()
    rows = result.get("files", [])
    if not rows:
        return None, None
    return rows[0]["id"], rows[0]["modifiedTime"]

def download_zip(service, file_id, destino):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    with open(destino, "wb") as f:
        f.write(fh.getvalue())

def precisa_baixar(service, ano):
    """Drive mais recente que o ZIP local ou faltam dados atuais?"""
    file_id, modified_time = find_zip(service, ano)
    if not file_id or not modified_time:
        print(f"  COTAHIST_A{ano}.ZIP nao encontrado no Drive", flush=True)
        return False

    gdrive_dt = datetime.fromisoformat(modified_time.replace("Z", "+00:00"))

    local = os.path.join(DATA_DIR, f"COTAHIST_A{ano}.ZIP")
    if os.path.exists(local):
        local_dt = datetime.fromtimestamp(os.path.getmtime(local), tz=gdrive_dt.tzinfo)
        if gdrive_dt <= local_dt:
            if ano < datetime.now().year:
                return False
            h = {"apikey": config.supabase_key, "Authorization": f"Bearer {config.supabase_key}"}
            rest = f"{config.supabase_url}/rest/v1"
            r = httpx.get(f"{rest}/{TABELA}?select=data&order=data.desc&limit=1", headers=h, timeout=30)
            if r.status_code == 200 and r.json():
                ultima = r.json()[0].get("data", "")
                if ultima and datetime.strptime(ultima[:10], "%Y-%m-%d").date() >= date.today():
                    return False
            return True
    return True

def baixar_do_drive(service, ano):
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f"COTAHIST_A{ano}.ZIP"
    filepath = os.path.join(DATA_DIR, filename)
    file_id, _ = find_zip(service, ano)
    if not file_id:
        return None
    print(f"  Baixando {filename} do Google Drive...", flush=True)
    download_zip(service, file_id, filepath)
    print(f"  OK", flush=True)
    return filepath

# ─── extrair ─────────────────────────────────────

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

# ─── main ────────────────────────────────────────

def main():
    from supabase import create_client
    supabase = create_client(config.supabase_url, config.supabase_key)

    h = {"apikey": config.supabase_key, "Authorization": f"Bearer {config.supabase_key}"}
    rest = f"{config.supabase_url}/rest/v1"
    anos = [datetime.now().year]

    print("[1/4] Carregando tickers da 00_Master...", flush=True)
    tickers = set()
    off = 0
    while True:
        r = httpx.get(
            f"{rest}/00_Master?select=Ticker&limit=1000&offset={off}",
            headers={**h, "Prefer": "count=exact"}, timeout=30
        )
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
    print(f"  -> {len(tickers)} tickers.", flush=True)

    print("[2/4] Verificando Google Drive...", flush=True)
    try:
        service = get_drive_service()
    except Exception as e:
        print(f"  Erro ao conectar no Drive: {e}", flush=True)
        print("RESULT:ERRO(drive)", flush=True)
        return

    zips = []
    for ano in anos:
        if precisa_baixar(service, ano):
            p = baixar_do_drive(service, ano)
            if p:
                zips.append(p)
        else:
            p = os.path.join(DATA_DIR, f"COTAHIST_A{ano}.ZIP")
            zips.append(p)
            print(f"  COTAHIST_A{ano}.ZIP ja atualizado", flush=True)

    if not zips:
        print("Nenhum ZIP disponivel.", flush=True)
        print("RESULT:OK(0)", flush=True)
        return

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
            batch = regs[i:i + 500]
            try:
                supabase.table(TABELA).upsert(batch, on_conflict="ticker,data").execute()
                total_ok += len(batch)
            except Exception as e:
                print(f"    Erro lote {i}: {e}", flush=True)

    print(f"\nRESULT:OK({total_ok})", flush=True)


if __name__ == "__main__":
    main()
