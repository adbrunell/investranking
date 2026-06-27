"""Lê Fatos Relevantes sem Resumo_ia, envia para Gemini e salva o resumo."""
import os, sys, logging, time, json
from datetime import datetime, timezone

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
from google import genai
from google.genai import types

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

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

* **[Impacto Financeiro]:** [Bullet point curto sobre valores, dividendos ou yields envolvidos, se houver].
* **[Próximos Passos]:** [Bullet point curto sobre o que o fundo ou o investidor precisa fazer agora].
* **[Risco/Oportunidade]:** [Bullet point curto com a visão analítica do especialista].

### REGRAS DE NEGÓCIO (CRÍTICAS):
1. Substitua [CLASSIFICAÇÃO] por uma destas 3 opções exatas (em caixa alta):
   - POSITIVO (VERDE) -> Se aumenta o dividend yield, reduz vacância, vende imóvel com lucro, etc.
   - NEGATIVO (VERMELHO) -> Se há inadimplência, rescisão de contrato, aumento de vacância, emissão abaixo do VP, etc.
   - INDIFERENTE (BRANCO) -> Para trocas de administradora sem custos, desdobramentos, ou fatos puramente burocráticos.
2. Seja cirúrgico. Evite jargões jurídicos ou textões copiados do documento original. Traduza o "juridiquês" para o impacto no bolso do investidor.
3. Se o fato relevante não trouxer dados de alguma das bullets (ex: sem impacto financeiro imediato), omita a linha correspondente."""


def buscar_fatos_sem_resumo() -> list[dict]:
    url = f"{SUPABASE_URL}/rest/v1/fnet_tudo"
    params = {
        "select": "fnet_documento_id,codigo_fundo,link_documento,link_visualizar",
        "categoria_documento": "eq.Fato Relevante",
        "Resumo_ia": "is.null",
        "limit": 10,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    r = httpx.get(f"{url}?{qs}", headers=HEADERS, timeout=30)
    if r.status_code != 200:
        print(f"  Erro ao buscar fatos: {r.status_code}")
        return []
    return r.json()


def baixar_pdf(url: str, viz_url: str = "") -> bytes | None:
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for tentativa_url in [url, viz_url]:
        if not tentativa_url:
            continue
        try:
            r = httpx.get(tentativa_url, headers=ua, timeout=120, follow_redirects=True)
            if r.status_code == 200 and len(r.content) > 100:
                return r.content
        except Exception as e:
            print(f"  Erro ao baixar {tentativa_url[:60]}: {e}")
    return None


def gerar_resumo(pdf_bytes: bytes, ticker: str) -> str | None:
    if not GEMINI_KEY:
        print("  GEMINI_API_KEY não configurada")
        return None
    client = genai.Client(api_key=GEMINI_KEY)
    try:
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[PROMPT, types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")],
        )
        return resp.text.strip() if resp.text else None
    except Exception as e:
        print(f"  Erro Gemini: {e}")
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

    if not GEMINI_KEY:
        print("  GEMINI_API_KEY não encontrada. Pule este script ou configure .env")
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

        resumo = gerar_resumo(pdf, ticker)
        if not resumo:
            print(f"    Falha ao gerar resumo")
            erros += 1
            continue

        salvar_resumo(doc_id, resumo)
        processados += 1
        print(f"    Resumo salvo ({len(resumo)} chars)")
        time.sleep(1)

    print(f"RESULT:OK(processados={processados}, erros={erros})")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
