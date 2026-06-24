import csv
import io
import os
import sys

import httpx
from supabase import create_client, Client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

GSHEET_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vQCAHauBLlaNEYi4veEKlYVvTFBNPfKNHpJiMbDpd8HvooxTCgZd7E-KFWyIaTQgle495_F577-Jlod/"
    "pub?gid=0&single=true&output=csv"
)

TABLE = "00_fundos_master"
UNIQUE_KEY = "ticker"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def download_csv() -> str:
    print("  Baixando planilha do Google Sheets...")
    resp = httpx.get(GSHEET_URL, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_csv(content: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    for row in reader:
        ticker = row.get("TICKER", "").strip()
        if not ticker:
            continue
        rows.append({
            "ticker": ticker,
            "segmento": row.get("SEGMENTO", "").strip(),
            "tipo": row.get("TIPO", "").strip(),
            "cnpj": row.get("CNPJ", "").strip(),
        })
    return rows


def upsert_rows(rows: list[dict]) -> int:
    if not rows:
        return 0
    batch_size = 500
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        supabase.table(TABLE).upsert(batch, on_conflict=UNIQUE_KEY).execute()
        total += len(batch)
    return total


def main():
    print(f"\n=== Sincronizando {TABLE} com Google Sheets ===")

    csv_content = download_csv()
    rows = parse_csv(csv_content)
    print(f"  Registros baixados: {len(rows)}")

    total = upsert_rows(rows)
    print(f"  Sincronizados: {total}")

    if total > 0:
        print(f"RESULT:OK({total})")
    else:
        print("RESULT:OK(0)")


if __name__ == "__main__":
    main()
