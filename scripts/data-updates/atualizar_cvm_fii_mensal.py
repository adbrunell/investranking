import os
import csv
import io
import sys
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

COLUMN_MAP = {"cnpj_fundo": "cnpj_fundo_classe"}


def get_db_columns(table_name: str) -> set:
    r = supabase.table(table_name).select("*").limit(1).execute()
    if not r.data:
        return set()
    return {k for k in r.data[0].keys() if k != "id"}


def download_zip(year: int) -> bytes:
    url = f"{CVM_BASE}/inf_mensal_fii_{year}.zip"
    print(f"  Downloading...")
    resp = httpx.get(url, follow_redirects=True, timeout=120)
    resp.raise_for_status()
    return resp.content


def parse_csv(data: bytes, csv_filename: str, db_cols: set) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        with z.open(csv_filename) as f:
            text = f.read().decode("latin-1")
            reader = csv.DictReader(io.StringIO(text), delimiter=";")
            rows = []
            for row in reader:
                clean = {}
                for k, v in row.items():
                    if not k:
                        continue
                    name = k.lower().strip()
                    name = COLUMN_MAP.get(name, name)
                    if name not in db_cols:
                        continue
                    clean[name] = v.strip() if v else None
                rows.append(clean)
            return rows


def get_existing_keys(table_name: str, year: int) -> set:
    all_keys = set()
    offset = 0
    limit = 1000
    while True:
        r = (
            supabase.table(table_name)
            .select(",".join(UNIQUE_KEYS))
            .gte("data_referencia", f"{year}-01-01")
            .lte("data_referencia", f"{year}-12-31")
            .range(offset, offset + limit - 1)
            .execute()
        )
        if not r.data:
            break
        for row in r.data:
            key = tuple(str(row[k]) if row[k] is not None else None for k in UNIQUE_KEYS)
            all_keys.add(key)
        if len(r.data) < limit:
            break
        offset += limit
    return all_keys


def upsert_rows(table_name: str, rows: list[dict]) -> int:
    if not rows:
        print(f"  Nothing to insert.")
        return 0

    seen = set()
    deduped = []
    for row in rows:
        key = tuple(row.get(k) for k in UNIQUE_KEYS)
        if key not in seen:
            seen.add(key)
            deduped.append(row)

    if not deduped:
        print(f"  Nothing to insert.")
        return 0

    batch_size = 500
    total = 0
    for i in range(0, len(deduped), batch_size):
        batch = deduped[i : i + batch_size]
        supabase.table(table_name).upsert(batch, on_conflict=",".join(UNIQUE_KEYS)).execute()
        total += len(batch)
    print(f"  Synced {total} rows.")
    return total


def main():
    current_year = datetime.now().year
    total_inserted = 0
    error_count = 0

    db_cols_cache = {}
    for db_table in TABLES:
        db_cols_cache[db_table] = get_db_columns(db_table)

    r = supabase.table("cvm_fii_geral").select("data_referencia").order("data_referencia", desc=True).limit(1).execute()
    last_year = datetime.strptime(r.data[0]["data_referencia"], "%Y-%m-%d").year if r.data else 2016
    start_year = min(last_year, current_year)

    for year in range(start_year, current_year + 1):
        print(f"\n=== Year {year} ===")
        try:
            zip_data = download_zip(year)
        except httpx.HTTPError as e:
            print(f"  Download failed: {e}")
            error_count += 1
            continue

        for db_table, csv_prefix in TABLES.items():
            csv_filename = f"{csv_prefix}_{year}.csv"
            db_cols = db_cols_cache[db_table]
            print(f"  {csv_filename}")
            try:
                rows = parse_csv(zip_data, csv_filename, db_cols)
                existing = get_existing_keys(db_table, year)
                new_rows = [r for r in rows if tuple(r.get(k) for k in UNIQUE_KEYS) not in existing]
                count = upsert_rows(db_table, new_rows)
                total_inserted += count
            except KeyError:
                print(f"  Not in zip, skipping.")
                continue

    if error_count > 0:
        print(f"RESULT:ERRO({error_count})")
        sys.exit(1)
    else:
        print(f"RESULT:OK({total_inserted})")
        sys.exit(0)


if __name__ == "__main__":
    main()
