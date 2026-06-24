import os
import csv
import io
import sys

import httpx
from supabase import create_client, Client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

TABLES = {
    "cvm_fii_dadoscadastrais": {
        "url": "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi.csv",
        "unique_key": ["cnpj_fundo"],
    },
    "cvm_acoes_dadoscadastrais": {
        "url": "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv",
        "unique_key": ["cnpj_cia"],
    },
}


def get_db_columns(table_name: str) -> set:
    r = supabase.table(table_name).select("*").limit(1).execute()
    if not r.data:
        return set()
    return {k for k in r.data[0].keys() if k != "id"}


def download_csv(url: str) -> str:
    print(f"  Downloading...")
    resp = httpx.get(url, follow_redirects=True, timeout=120)
    resp.raise_for_status()
    return resp.content.decode("latin-1")


def parse_csv(text: str, db_cols: set) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    rows = []
    for row in reader:
        clean = {}
        for k, v in row.items():
            if not k:
                continue
            name = k.lower().strip()
            if db_cols and name not in db_cols:
                continue
            clean[name] = v.strip() if v else None
        rows.append(clean)
    return rows


def get_existing_keys(table_name: str, unique_keys: list[str]) -> set:
    all_keys = set()
    offset = 0
    limit = 1000
    while True:
        r = (
            supabase.table(table_name)
            .select(",".join(unique_keys))
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


def upsert_rows(table_name: str, rows: list[dict], unique_keys: list[str]) -> int:
    if not rows:
        return 0

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
    total_inserted = 0
    error_count = 0

    for table_name, config in TABLES.items():
        print(f"\n=== {table_name} ===")
        db_cols = get_db_columns(table_name)
        unique_keys = config["unique_key"]

        try:
            decoded = download_csv(config["url"])
        except httpx.HTTPError as e:
            print(f"  Download failed: {e}")
            error_count += 1
            continue

        rows = parse_csv(decoded, db_cols)
        existing = get_existing_keys(table_name, unique_keys)
        new_rows = [r for r in rows if tuple(r.get(k) for k in unique_keys) not in existing]
        count = upsert_rows(table_name, new_rows, unique_keys)
        total_inserted += count

    if error_count > 0:
        print(f"RESULT:ERRO({error_count})")
        sys.exit(1)
    else:
        print(f"RESULT:OK({total_inserted})")
        sys.exit(0)


if __name__ == "__main__":
    main()
