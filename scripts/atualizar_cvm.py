import os
import csv
import io
import zipfile
from datetime import datetime

import httpx
from supabase import create_client, Client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
CVM_BASE = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

TABLES = {
    "cvm_fii_ativo_passivo": "inf_mensal_fii_ativo_passivo",
    "cvm_fii_complemento": "inf_mensal_fii_complemento",
    "cvm_fii_geral": "inf_mensal_fii_geral",
}

UNIQUE_KEYS = ["cnpj_fundo_classe", "data_referencia", "versao"]


def download_zip(year: int) -> bytes:
    url = f"{CVM_BASE}/inf_mensal_fii_{year}.zip"
    print(f"Downloading {url}...")
    resp = httpx.get(url, follow_redirects=True, timeout=120)
    resp.raise_for_status()
    return resp.content


def parse_csv(data: bytes, csv_filename: str) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        with z.open(csv_filename) as f:
            text = f.read().decode("latin-1")
            reader = csv.DictReader(io.StringIO(text), delimiter=";")
            rows = []
            for row in reader:
                clean = {k.lower(): v.strip() if v else None for k, v in row.items()}
                clean.pop(None, None)
                rows.append(clean)
            return rows


def upsert_rows(table_name: str, rows: list[dict]):
    if not rows:
        print(f"  Nothing to insert.")
        return

    batch_size = 500
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        supabase.table(table_name).upsert(batch, on_conflict=",".join(UNIQUE_KEYS)).execute()
        total += len(batch)
    print(f"  Synced {total} rows (upsert).")


def main():
    current_year = datetime.now().year
    for year in range(2016, current_year + 1):
        print(f"\n=== Year {year} ===")
        try:
            zip_data = download_zip(year)
        except httpx.HTTPError as e:
            print(f"  Download failed: {e}")
            continue

        for db_table, csv_prefix in TABLES.items():
            csv_filename = f"{csv_prefix}_{year}.csv"
            print(f"  Processing {csv_filename} -> {db_table}")
            try:
                rows = parse_csv(zip_data, csv_filename)
                upsert_rows(db_table, rows)
            except KeyError:
                print(f"  File not found in zip, skipping.")
                continue


if __name__ == "__main__":
    main()
