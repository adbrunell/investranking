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
CVM_BASE = "https://dados.cvm.gov.br/dados/FIAGRO/DOC/INF_MENSAL/DADOS"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

TABLES = {
    "cvm_fiagro_geral": "inf_mensal_fiagro",
    "cvm_fiagro_subclasse": "inf_mensal_fiagro_subclasse",
}

UNIQUE_KEYS = {
    "cvm_fiagro_geral": ["cnpj_classe", "data_referencia", "versao"],
    "cvm_fiagro_subclasse": ["cnpj_classe", "data_referencia", "nome_subclasse"],
}
COLUMN_MAP = {"provisoes_contigencias": "provisoes_contingencias"}


def get_db_columns(table_name: str) -> set:
    r = supabase.table(table_name).select("*").limit(1).execute()
    if not r.data:
        return set()
    return {k for k in r.data[0].keys() if k != "id"}


def download_zip(year: int, month: int) -> bytes:
    url = f"{CVM_BASE}/inf_mensal_fiagro_{year}{month:02d}.zip"
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
                    if db_cols and name not in db_cols:
                        continue
                    clean[name] = v.strip() if v else None
                rows.append(clean)
            return rows


def get_existing_keys(table_name: str, year: int, month: int) -> set:
    unique_keys = UNIQUE_KEYS[table_name]
    all_keys = set()
    offset = 0
    limit = 1000
    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1}-01-01"
    else:
        end = f"{year}-{month + 1:02d}-01"
    while True:
        r = (
            supabase.table(table_name)
            .select(",".join(unique_keys))
            .gte("data_referencia", start)
            .lt("data_referencia", end)
            .range(offset, offset + limit - 1)
            .execute()
        )
        if not r.data:
            break
        for row in r.data:
            key = tuple(str(row[k]) if row[k] is not None else None for k in unique_keys)
            all_keys.add(key)
        if len(r.data) < limit:
            break
        offset += limit
    return all_keys


def upsert_rows(table_name: str, rows: list[dict]) -> int:
    if not rows:
        return 0

    unique_keys = UNIQUE_KEYS[table_name]
    seen = set()
    deduped = []
    for row in rows:
        key = tuple(row.get(k) for k in unique_keys)
        if key not in seen:
            seen.add(key)
            deduped.append(row)

    if not deduped:
        return 0

    batch_size = 500
    total = 0
    for i in range(0, len(deduped), batch_size):
        batch = deduped[i : i + batch_size]
        supabase.table(table_name).upsert(batch, on_conflict=",".join(unique_keys)).execute()
        total += len(batch)
    print(f"  Synced {total} rows.")
    return total


def main():
    today = datetime.now()
    current_year = today.year
    current_month = today.month
    total_inserted = 0
    error_count = 0

    db_cols_cache = {}
    for db_table in TABLES:
        db_cols_cache[db_table] = get_db_columns(db_table)

    r = supabase.table("cvm_fiagro_geral").select("data_referencia").order("data_referencia", desc=True).limit(1).execute()
    if r.data:
        last_date = datetime.strptime(r.data[0]["data_referencia"], "%Y-%m-%d")
        start_year = last_date.year
        start_month = last_date.month
    else:
        start_year = 2025
        start_month = 5

    for year in range(start_year, current_year + 1):
        month_from = start_month if year == start_year else 1
        if year == current_year:
            month_to = current_month
        else:
            month_to = 12

        for month in range(month_from, month_to + 1):
            print(f"\n=== {year}-{month:02d} ===")
            try:
                zip_data = download_zip(year, month)
            except httpx.HTTPError as e:
                if e.response is not None and e.response.status_code == 404 and year == current_year and month == current_month:
                    print(f"  Data not yet available for current month.")
                    continue
                print(f"  Download failed: {e}")
                error_count += 1
                continue

            for db_table, csv_prefix in TABLES.items():
                csv_filename = f"{csv_prefix}_{year}{month:02d}.csv"
                db_cols = db_cols_cache[db_table]
                print(f"  {csv_filename}")
                try:
                    rows = parse_csv(zip_data, csv_filename, db_cols)
                    existing = get_existing_keys(db_table, year, month)
                    new_rows = [r for r in rows if tuple(r.get(k) for k in UNIQUE_KEYS[db_table]) not in existing]
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
