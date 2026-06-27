"""Lê Fatos Relevantes sem Resumo_ia, extrai texto do PDF, envia para Groq e salva o resumo."""
import os, sys, logging, time, json, io, re
from datetime import datetime, timezone, timedelta

_proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

_env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

import httpx
from pypdf import PdfReader

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
GROQ_KEY = os.environ.get("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
}

PROMPT = """Você é o maior especialista em Fundos Imobiliários (FIIs) do mercado financeiro. Sua tarefa é ler um Fato Relevante e gerar um resumo ultra-conciso para investidores.

O resultado final deve ser extremamente direto, pois será armazenado em uma única célula de banco de dados. Use estritamente a estrutura abaixo, sem textos de introdução ou conclusão.

### ESTRUTURA REQUERIDA:

**[CLASSIFICAÇÃO] - [Nome/Ticker do FII]: [Gatilho Principal em 1 Frase]**

*Resumo:* [Escreva um resumo executivo de no máximo 2 frases explicando o impacto real para o cotista].

* **[Impacto Financeiro]:** [Texto direto, sem traço ou bullet. Apenas o conteúdo].
* **[Próximos Passos]:** [Texto direto, sem traço ou bullet. Apenas o conteúdo].
* **[Risco/Oportunidade]:** [Texto direto, sem traço ou bullet. Apenas o conteúdo].

### REGRAS DE NEGÓCIO (CRÍTICAS):
1. A classificação deve ser feita na **perspectiva do investidor cotista**, não do fundo. Pergunte-se: "Isso é bom, ruim ou indiferente para quem tem cotas deste FII?"
   Substitua [CLASSIFICAÇÃO] por uma destas 3 opções exatas (em caixa alta):
   - POSITIVO (VERDE) -> Beneficia o cotista: aumento de dividendos, venda de imóvel com lucro, redução de vacância, aquisição de ativo com bom cap rate, etc.
   - NEGATIVO (VERMELHO) -> Prejudica o cotista: inadimplência, rescisão de contrato, aumento de vacância, emissão de cotas abaixo do VP, endividamento excessivo, etc.
   - NEUTRO (BRANCO) -> Não afeta o bolso do cotista: trocas de administradora sem custos, desdobramentos, alterações burocráticas sem impacto financeiro direto.
2. Seja cirúrgico. Evite jargões jurídicos ou textões copiados do documento original. Traduza o "juridiquês" para o impacto no bolso do investidor.
3. Se o fato relevante não trouxer dados de alguma das bullets (ex: sem impacto financeiro imediato), omita a linha correspondente."""


def buscar_fatos_sem_resumo() -> list[dict]:
    # Só processa fatos dos últimos 7 dias (novos)
    data_limite = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
    url = f"{SUPABASE_URL}/rest/v1/fnet_tudo"
    params = {
        "select": "fnet_documento_id,codigo_fundo,link_documento,link_visualizar",
        "categoria_documento": "eq.Fato Relevante",
        "data_entrega": f"gte.{data_limite}",
        "Resumo_ia": "is.null",
        "limit": 5,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    r = httpx.get(f"{url}?{qs}", headers=HEADERS, timeout=30)
    if r.status_code != 200:
        print(f"  Erro ao buscar fatos: {r.status_code}")
        return []
    return r.json()


def baixar_pdf(url: str, viz_url: str = "") -> bytes | None:
    import base64
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for tentativa_url in [url, viz_url]:
        if not tentativa_url:
            continue
        try:
            r = httpx.get(tentativa_url, headers=ua, timeout=120, follow_redirects=True)
            if r.status_code != 200 or len(r.content) < 100:
                continue
            raw = r.content
            # FNET returns PDF as base64 string wrapped in quotes
            if raw[0] in (0x22, 0x27):
                txt = raw.decode("latin-1").strip().strip("\"'")
                try:
                    return base64.b64decode(txt)
                except:
                    pass
            return raw
        except Exception as e:
            print(f"  Erro ao baixar {tentativa_url[:60]}: {e}")
    return None


def extrair_texto(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        texto = "\n".join(page.extract_text() or "" for page in reader.pages)
        return texto.strip()[:8000]
    except Exception as e:
        print(f"  Erro ao extrair texto: {e}")
        return ""


def gerar_resumo(texto: str, ticker: str) -> str | None:
    if not GROQ_KEY:
        print("  GROQ_API_KEY não configurada")
        return None
    headers = {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": f"Fato Relevante do fundo {ticker}:\n\n{texto}"},
        ],
        "temperature": 0.3,
        "max_tokens": 500,
    }
    try:
        r = httpx.post(GROQ_URL, headers=headers, json=payload, timeout=60)
        if r.status_code != 200:
            print(f"  Groq erro {r.status_code}: {r.text[:200]}")
            return None
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  Erro Groq: {e}")
        return None


def salvar_resumo(doc_id: str, resumo: str):
    url = f"{SUPABASE_URL}/rest/v1/fnet_tudo"
    r = httpx.patch(
        f"{url}?fnet_documento_id=eq.{doc_id}",
        headers=HEADERS,
        json={"Resumo_ia": resumo},
        timeout=30,
    )
    if r.status_code not in (200, 204):
        print(f"  Erro ao salvar resumo: {r.status_code}")


def main():
    print("\n=== Processar Fatos Relevantes com IA ===")

    if not GROQ_KEY:
        print("  GROQ_API_KEY não encontrada. Configure .env")
        print("RESULT:SKIP")
        return

    fatos = buscar_fatos_sem_resumo()
    print(f"  Fatos pendentes: {len(fatos)}")

    processados = 0
    erros = 0
    for fato in fatos:
        doc_id = fato.get("fnet_documento_id")
        ticker = fato.get("codigo_fundo", "?")
        link = fato.get("link_documento") or fato.get("link_visualizar")
        if not doc_id or not link:
            erros += 1
            continue

        print(f"  Processando {ticker} ({doc_id[:12]}...)")

        pdf = baixar_pdf(link, fato.get("link_visualizar") or "")
        if not pdf:
            print(f"    PDF não encontrado, pulando")
            erros += 1
            continue

        texto = extrair_texto(pdf)
        if not texto:
            print(f"    Texto vazio, pulando")
            erros += 1
            continue

        resumo = gerar_resumo(texto, ticker)
        if not resumo:
            print(f"    Falha ao gerar resumo")
            erros += 1
            continue

        # Remove bullet dashes that LLM sometimes adds
        resumo = re.sub(r'^(\*{0,2}\s*\[[^\]]+\]:\*{0,2}\s*)-\s+', r'\1', resumo, flags=re.MULTILINE)
        salvar_resumo(doc_id, resumo)
        processados += 1
        print(f"    Resumo salvo ({len(resumo)} chars)")
        time.sleep(1)

    print(f"RESULT:OK(processados={processados}, erros={erros})")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
