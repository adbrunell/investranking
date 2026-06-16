import os
import sys
import csv
import io
import re
import time
from datetime import datetime, timezone, timedelta

import httpx
from playwright.sync_api import sync_playwright

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

TABELA = "status_dividendos"
DATA_DIR = "data_statusinvest"

PAGINAS = [
    {"url": "https://statusinvest.com.br/acoes/proventos/", "tipo": "Acoes", "ctrl": "acao"},
    {"url": "https://statusinvest.com.br/fundos-imobiliarios/proventos/", "tipo": "FIIs", "ctrl": "fii"},
    {"url": "https://statusinvest.com.br/fiagros/proventos/", "tipo": "Fiagro", "ctrl": "fiagro"},
    {"url": "https://statusinvest.com.br/fiinfras/proventos", "tipo": "Fiinfra", "ctrl": "fiinfra"},
]

MAPA_CSV = {
    "ATIVO": "ticker",
    "TICKER": "ticker",
    "VALOR": "valor",
    "DATA COM": "data_com",
    "DATA PAGAMENTO": "data_pagamento",
    "DATA PAG.": "data_pagamento",
    "TIPO": "tipo_provento",
    "DY": "rendimento",
    "RENDIMENTO": "rendimento",
}


def parse_br_date(value: str) -> str | None:
    if not value or value.strip() in ("", "-", "--"):
        return None
    value = value.strip()
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", value)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None


def parse_br_number(value: str) -> float | None:
    if not value or value.strip() in ("", "-", "--", "R$ 0"):
        return None
    value = value.strip()
    value = re.sub(r"^[RUS]?\$?\s*%?\s*", "", value)
    value = value.replace("%", "").strip()
    value = value.replace(".", "").replace(",", ".")
    try:
        return round(float(value), 6)
    except ValueError:
        return None


def format_br_date(d: datetime) -> str:
    return d.strftime("%d/%m/%Y")


def get_existing_keys(tipo_ativo: str) -> set[tuple[str, str, str, str]]:
    keys: set[tuple[str, str, str, str]] = set()
    base = f"{SUPABASE_URL}/rest/v1/{TABELA}"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    off = 0
    while True:
        r = httpx.get(
            f"{base}?select=ticker,data_com,tipo_provento,tipo_ativo&tipo_ativo=eq.{tipo_ativo}&limit=1000&offset={off}",
            headers=headers,
            timeout=30,
        )
        if r.status_code not in (200, 206):
            break
        rows = r.json()
        if not rows:
            break
        for row in rows:
            t = (
                (row.get("ticker") or "").strip().upper(),
                (row.get("data_com") or "").strip(),
                (row.get("tipo_provento") or "").strip().upper(),
                (row.get("tipo_ativo") or "").strip(),
            )
            if t[0] and t[1]:
                keys.add(t)
        if len(rows) < 1000:
            break
        off += 1000
    return keys


def processar_pagina(pagina: dict) -> int:
    hoje = datetime.now()
    data_inicio = hoje - timedelta(days=30)

    existing_keys = get_existing_keys(pagina["tipo"])
    print(f"  Registros existentes: {len(existing_keys)}")

    print(f"\n  [{pagina['tipo']}] Abrindo {pagina['url']}...")

    registros_final: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(locale="pt-BR")
        page = context.new_page()

        try:
            page.goto(pagina["url"], timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            print(f"  [{pagina['tipo']}] Clicando na aba DATA COM...")
            page.click("a.dateCon")
            page.wait_for_timeout(1000)

            print(f"  [{pagina['tipo']}] Ajustando datas...")
            start_str = format_br_date(data_inicio)
            end_str = format_br_date(hoje)
            page.evaluate(f"""
                () => {{
                    const s = document.querySelector('#Start');
                    if (s) {{ s.value = '{start_str}'; s.dispatchEvent(new Event('change', {{ bubbles: true }})); }}
                    const e = document.querySelector('#End');
                    if (e) {{ e.value = '{end_str}'; e.dispatchEvent(new Event('change', {{ bubbles: true }})); }}
                }}
            """)
            page.wait_for_timeout(5000)

            page.evaluate("""
                () => {
                    document.querySelectorAll('.popup-fixed, #footer-fixed').forEach(el => el.remove());
                    document.querySelectorAll('#dateCon,#datePag,#provi').forEach(el => el.style.display = 'block');
                }
            """)

            print(f"  [{pagina['tipo']}] Aguardando grid...")
            page.wait_for_selector("#dateCon .card-grid table tbody tr", timeout=30000)
            page.wait_for_timeout(2000)

            select_exists = page.evaluate("""() => {
                const sel = document.querySelector('#dateCon select.small');
                return sel ? sel.value : null;
            }""")
            tr_count = 0
            if select_exists:
                print(f"  [{pagina['tipo']}] Select paginacao atual: {select_exists}")
                if select_exists != "-1":
                    print(f"  [{pagina['tipo']}] Selecionando TODOS...")
                    page.evaluate("""() => {
                        const sel = document.querySelector('#dateCon select.small');
                        if (sel) { sel.value = '-1'; sel.dispatchEvent(new Event('change', { bubbles: true })); }
                    }""")
                    print(f"  [{pagina['tipo']}] Aguardando carregamento completo...")
                    tr_count_anterior = 0
                    estabilizado = 0
                    for _ in range(120):
                        time.sleep(1)
                        tr_count = page.evaluate("document.querySelectorAll('#dateCon .card-grid table tbody tr').length")
                        if tr_count == tr_count_anterior and tr_count > 0:
                            estabilizado += 1
                            if estabilizado >= 3:
                                print(f"  [{pagina['tipo']}] Grid carregado: {tr_count} linhas")
                                break
                        else:
                            estabilizado = 0
                        tr_count_anterior = tr_count
                    else:
                        print(f"  [{pagina['tipo']}] Timeout, dados: {tr_count} linhas")
            else:
                print(f"  [{pagina['tipo']}] Select de paginacao nao encontrado")

            headers_raw = page.evaluate("""() => {
                const ths = document.querySelectorAll('#dateCon .card-grid table thead th');
                return Array.from(ths).map(th => th.innerText.trim());
            }""")
            print(f"  [{pagina['tipo']}] Headers: {headers_raw}")

            rows_data = page.evaluate("""() => {
                const rows = document.querySelectorAll('#dateCon .card-grid table tbody tr');
                return Array.from(rows).map(row => {
                    const cells = row.querySelectorAll('td');
                    return Array.from(cells).map(cell => cell.innerText.trim());
                });
            }""")
            print(f"  [{pagina['tipo']}] Linhas extraidas: {len(rows_data)}")

            if not headers_raw or not rows_data:
                print(f"  [{pagina['tipo']}] Sem dados.")
                return 0

            cabecalho_csv = ";".join(headers_raw)
            linhas_csv = "\n".join(";".join(row) for row in rows_data)
            conteudo_csv = f"{cabecalho_csv}\n{linhas_csv}"

            os.makedirs(DATA_DIR, exist_ok=True)
            filepath = os.path.join(DATA_DIR, f"dividendos_{pagina['ctrl']}.csv")
            with open(filepath, "w", encoding="utf-8-sig") as f:
                f.write(conteudo_csv)

        except Exception as e:
            print(f"  [{pagina['tipo']}] Erro: {e}")
            return 0
        finally:
            browser.close()

    if not os.path.exists(filepath):
        return 0

    with open(filepath, encoding="utf-8-sig") as f:
        content = f.read()

    reader = csv.DictReader(io.StringIO(content), delimiter=";")
    raw_headers = reader.fieldnames or []
    mapa = {}
    for raw_h in raw_headers:
        clean_h = raw_h.strip().upper()
        if clean_h in MAPA_CSV:
            mapa[raw_h] = MAPA_CSV[clean_h]

    if not mapa:
        print(f"  Headers: {raw_headers}, nenhum mapeamento")
        os.remove(filepath)
        return 0

    print(f"  Colunas mapeadas: {len(mapa)}")
    novos = 0

    for row in reader:
        ticker = ""
        data_com = ""
        tipo_provento = ""
        registro: dict[str, object] = {
            "tipo_ativo": pagina["tipo"],
            "data_atualizacao": datetime.now(timezone.utc).isoformat(),
        }
        for orig_col, db_col in mapa.items():
            val = (row.get(orig_col) or "").strip()
            if db_col == "ticker":
                ticker = val.upper() if val else ""
                registro[db_col] = ticker if ticker else None
            elif db_col == "tipo_provento":
                tipo_provento = val.upper() if val else ""
                registro[db_col] = tipo_provento if tipo_provento else None
            elif db_col in ("data_com", "data_pagamento"):
                registro[db_col] = parse_br_date(val)
            elif db_col in ("valor", "rendimento"):
                registro[db_col] = parse_br_number(val)
        if not ticker:
            continue
        dc_val = registro.get("data_com")
        dc = dc_val if isinstance(dc_val, str) else ""
        key = (ticker, dc, tipo_provento, pagina["tipo"])
        if key in existing_keys:
            continue
        registros_final.append(registro)
        existing_keys.add(key)
        novos += 1

    if os.path.exists(filepath):
        os.remove(filepath)

    print(f"  Novos registros: {novos}")
    if registros_final:
        save(registros_final)
    return novos


def save(registros: list[dict]):
    if not registros:
        return

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    url = f"{SUPABASE_URL}/rest/v1/{TABELA}"
    print(f"  Inserindo {len(registros)} registros...")

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
    print(f"  Inseridos {ok} de {len(registros)}.")


def main():
    print("=== StatusInvest - Dividendos ===")
    total = 0

    for pagina in PAGINAS:
        print(f"\n--- {pagina['tipo']} ---")
        total += processar_pagina(pagina)

    print(f"\nRESULT:OK({total})")
    sys.exit(0)


if __name__ == "__main__":
    main()
