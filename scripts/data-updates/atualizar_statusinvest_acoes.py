import os
import sys
import csv
import io
import re
from datetime import datetime, timezone

import httpx
from playwright.sync_api import sync_playwright

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

TABELA = "status_acoes"
DATA_DIR = "data_statusinvest"
URL = "https://statusinvest.com.br/acoes/busca-avancada"

MAPA_CSV_PARA_DB = {
    "TICKER": "ticker",
    "PRECO": "preco",
    "DY": "dy",
    "P/L": "p_l",
    "P/VP": "p_vp",
    "P/ATIVOS": "p_ativo",
    "MARGEM BRUTA": "margem_bruta",
    "MARGEM EBIT": "margem_ebit",
    "MARG. LIQUIDA": "margem_liquida",
    "P/EBIT": "p_ebit",
    "EV/EBIT": "ev_ebit",
    "DIVIDA LIQUIDA / EBIT": "divida_liquida_ebit",
    "DIV. LIQ. / PATRI.": "divida_liquida_patrimonio",
    "PSR": "p_sr",
    "P/CAP. GIRO": "p_capital_giro",
    "P. AT CIR. LIQ.": "p_ativo_circulante",
    "LIQ. CORRENTE": "liquidez_corrente",
    "ROE": "roe",
    "ROA": "roa",
    "ROIC": "roic",
    "PATRIMONIO / ATIVOS": "pl_ativo",
    "PASSIVOS / ATIVOS": "passivo_ativo",
    "GIRO ATIVOS": "giro_ativos",
    "CAGR RECEITAS 5 ANOS": "receitas_cagr5",
    "CAGR LUCROS 5 ANOS": "lucros_cagr5",
    "LIQUIDEZ MEDIA DIARIA": "liquidez_media_diaria",
    "VPA": "vpa",
    "LPA": "lpa",
    "PEG Ratio": "peg_ratio",
    "VALOR DE MERCADO": "valor_mercado",
}


def parse_br_number(value: str) -> float | None:
    if not value or value.strip() in ("", "-", "--"):
        return None
    value = value.strip()
    value = re.sub(r"^[RUS]?\$?\s*%?\s*", "", value)
    value = value.replace("%", "").strip()
    value = value.replace(".", "").replace(",", ".")
    try:
        return round(float(value), 4)
    except ValueError:
        return None


def download_csv() -> str | None:
    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, "status_acoes.csv")

    print("  Abrindo navegador...")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True, locale="pt-BR")
        page = context.new_page()

        try:
            page.goto(URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            print("  Clicando em Buscar...")
            page.click("button.find")

            print("  Aguardando resultados...")
            page.wait_for_selector("#list-result table", state="attached", timeout=30000)
            page.wait_for_timeout(5000)

            page.evaluate("""
                () => {
                    const el = document.querySelector('.popup-fixed');
                    if (el) el.remove();
                    const footer = document.querySelector('#footer-fixed');
                    if (footer) footer.remove();
                }
            """)
            page.wait_for_timeout(500)

            print("  Baixando planilha...")
            with page.expect_download(timeout=30000) as download_info:
                page.click("a.btn-download", force=True)

            download = download_info.value
            download.save_as(filepath)
            print(f"  Baixado: {os.path.basename(filepath)} ({os.path.getsize(filepath) / 1024:.1f} KB)")
            return filepath

        except Exception as e:
            print(f"  Erro: {e}")
            return None
        finally:
            browser.close()


def parse_csv(filepath: str) -> list[dict]:
    registros: list[dict] = []
    print(f"  Lendo {os.path.basename(filepath)}...")

    with open(filepath, encoding="utf-8-sig") as f:
        content = f.read()

    dialect = csv.Sniffer().sniff(content[:4096])
    reader = csv.DictReader(io.StringIO(content), delimiter=dialect.delimiter)

    raw_headers = reader.fieldnames or []
    mapa: dict[str, str] = {}
    for raw_h in raw_headers:
        clean_h = raw_h.strip()
        if clean_h in MAPA_CSV_PARA_DB:
            mapa[raw_h] = MAPA_CSV_PARA_DB[clean_h]

    if not mapa:
        print(f"  Headers: {raw_headers}")
        print(f"  Nenhum mapeamento encontrado.")
        return registros

    print(f"  Colunas mapeadas: {len(mapa)}/{len(MAPA_CSV_PARA_DB)}")

    for row in reader:
        registro: dict[str, object] = {"data_atualizacao": datetime.now(timezone.utc).isoformat()}
        ticker = None
        for orig_col, db_col in mapa.items():
            val = (row.get(orig_col) or "").strip()
            if db_col == "ticker":
                ticker = val.upper() if val else None
                registro[db_col] = ticker
            else:
                registro[db_col] = parse_br_number(val)
        if ticker:
            registros.append(registro)

    print(f"  Linhas extraidas: {len(registros)}")
    return registros


def save(registros: list[dict]):
    if not registros:
        print("  Nada a inserir.")
        return

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    url = f"{SUPABASE_URL}/rest/v1/{TABELA}"
    print(f"  Inserindo/atualizando {len(registros)} registros...")

    ok = 0
    for i in range(0, len(registros), 500):
        batch = registros[i : i + 500]
        try:
            resp = httpx.post(url, headers=headers, json=batch, timeout=60)
            if resp.status_code in (200, 201):
                ok += len(batch)
            else:
                print(f"  Lote {i // 500 + 1} falhou: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"  Lote {i // 500 + 1} erro: {e}")
    print(f"  Inseridos/atualizados {ok} de {len(registros)}.")


def main():
    print("\n=== StatusInvest - Acoes Busca Avancada ===")

    csv_path = download_csv()
    if not csv_path or not os.path.exists(csv_path):
        print("Falha no download.")
        sys.exit(1)

    registros = parse_csv(csv_path)
    if registros:
        save(registros)

    if os.path.exists(csv_path):
        os.remove(csv_path)

    print(f"RESULT:OK({len(registros)})")
    sys.exit(0)


if __name__ == "__main__":
    main()
