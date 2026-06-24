"""YouTube scraper for FII videos.

Searches YouTube by ticker hashtag and saves new videos to Supabase.
Only adds new records - never deletes existing ones.
"""
import os
import sys
import re
import json
import httpx
import logging
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

_proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

from utils.scraper.config import config

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}
REST = config.supabase_url.rstrip("/") + "/rest/v1"
API_HEADERS = {
    "apikey": config.supabase_key,
    "Authorization": f"Bearer {config.supabase_key}",
    "Content-Type": "application/json",
}
# Headers for upsert (update existing rows on conflict)
API_HEADERS_UPSERT = {
    **API_HEADERS,
    "Prefer": "resolution=merge-duplicates",
}
MAX_VIDEOS_PER_TICKER = 50
WORKERS = 10


def _strip_accents(text):
    replacements = {'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a', 'ä': 'a',
                    'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
                    'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
                    'ó': 'o', 'ò': 'o', 'õ': 'o', 'ô': 'o', 'ö': 'o',
                    'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
                    'ç': 'c', 'ñ': 'n'}
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


PREFIXOS = [
    "streamed ", "premiered ", "started streaming ", "started ",
    "was live ", "went live ", "live ",
    "transmitido ", "estreou ", "ao vivo ",
    "transmitido ao vivo ", "estreou ao vivo ",
]


def estimar_data(texto):
    hoje = datetime.now(timezone.utc)
    if not texto:
        return hoje
    try:
        texto = _strip_accents(texto.lower()).strip()

        # Remove common YouTube prefixes that precede date text
        for p in PREFIXOS:
            texto = texto.replace(p, "")

        texto = texto.replace("ha ", "").replace(" ago", "").strip()

        # Handle special date words without numbers
        if texto in ("ontem", "yesterday"):
            return hoje - timedelta(days=1)
        if texto in ("hoje", "today"):
            return hoje

        m = re.search(r"\d+", texto)
        if not m:
            if texto:
                logger.debug("Texto de data nao reconhecido: %r", texto)
            return hoje
        n = int(m.group())

        if any(x in texto for x in ["mes", "month", "months"]):
            return hoje - timedelta(days=30 * n)
        if any(x in texto for x in ["semana", "semanas", "sem.", "sem ", "sem", "week", "weeks"]):
            return hoje - timedelta(weeks=n)
        if any(x in texto for x in ["dia", "day", "days"]):
            return hoje - timedelta(days=n)
        if any(x in texto for x in ["ano", "year", "anos", "years"]):
            return hoje - timedelta(days=365 * n)
        if any(x in texto for x in ["hora", "hour", "hours"]):
            return hoje - timedelta(hours=n)
        if any(x in texto for x in ["minuto", "minute", "minutes"]):
            return hoje - timedelta(minutes=n)

        # If we have a number but no unit matched, assume days
        logger.debug("Texto com numero sem unidade reconhecida: %r (n=%s)", texto, n)
        return hoje - timedelta(days=n)

    except Exception:
        pass
    return hoje


def remover_emojis(texto):
    if not texto:
        return ""
    padrao = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002500-\U00002BEF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )
    return padrao.sub("", texto).strip()


def _get_pub_text(v):
    """Extract publication text from videoRenderer, handling both simpleText and runs formats."""
    pub = v.get("publishedTimeText")
    if not pub:
        return ""
    if isinstance(pub, dict):
        text = pub.get("simpleText")
        if text and isinstance(text, str):
            return text
        runs = pub.get("runs")
        if runs and isinstance(runs, list):
            return "".join(r.get("text", "") for r in runs if isinstance(r, dict))
    return ""


def _scrape_one(client, ticker):
    """Scrape YouTube for a single ticker using an existing client."""
    url = f"https://www.youtube.com/results?search_query=%23{ticker}&sp=CAI%253D"
    try:
        r = client.get(url)
        r.raise_for_status()
    except Exception as e:
        logger.warning("Erro ao acessar YouTube para %s: %s", ticker, e)
        return []

    page = r.content.decode("latin-1")

    match = re.search(r'var ytInitialData\s*=\s*({.*?});', page)
    if not match:
        match = re.search(r'window\["ytInitialData"\]\s*=\s*({.*?});</script>', page)
    if not match:
        return []

    try:
        texto_json = match.group(1)
        texto_json = re.sub(r"\\x[0-9A-Fa-f]{2}", "", texto_json)
        data = json.loads(texto_json.encode("latin-1"))
    except Exception:
        return []

    try:
        contents = (
            data["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"]
            ["sectionListRenderer"]["contents"][0]["itemSectionRenderer"]["contents"]
        )
    except (KeyError, IndexError):
        return []

    resultados = []
    for item in contents:
        v = item.get("videoRenderer")
        if not v:
            continue
        video_id = v.get("videoId")
        if not video_id:
            continue
        titulo = v.get("title", {}).get("runs", [{}])[0].get("text", "")
        if ticker.upper() not in titulo.upper():
            continue
        canal = v.get("ownerText", {}).get("runs", [{}])[0].get("text", "")
        data_pub_texto = _get_pub_text(v)
        duracao = v.get("lengthText", {}).get("simpleText", "")

        resultados.append({
            "ticker": ticker.upper(),
            "video_id": video_id,
            "canal": remover_emojis(canal),
            "titulo": remover_emojis(titulo),
            "publicacao": estimar_data(data_pub_texto).isoformat(),
            "duracao": duracao,
            "link": f"https://www.youtube.com/watch?v={video_id}",
        })

    return resultados[:MAX_VIDEOS_PER_TICKER]


def scrape_youtube(ticker):
    with httpx.Client(headers=HEADERS, timeout=20) as client:
        return _scrape_one(client, ticker)


def get_existing_ids():
    ids = set()
    offset = 0
    while True:
        r = httpx.get(
            f"{REST}/youtube_videos?select=video_id&limit=1000&offset={offset}",
            headers=API_HEADERS,
            timeout=30,
        )
        if r.status_code != 200:
            break
        rows = r.json()
        if not rows:
            break
        for row in rows:
            vid = row.get("video_id")
            if vid:
                ids.add(vid)
        if len(rows) < 1000:
            break
        offset += 1000
    return ids


def get_tickers():
    import re as _re
    tickers = set()
    offset = 0
    while True:
        r = httpx.get(
            f"{REST}/00_fundos_master?select=ticker&ticker=not.is.null&ticker=neq.&limit=1000&offset={offset}",
            headers=API_HEADERS,
            timeout=30,
        )
        if r.status_code not in (200, 206):
            break
        rows = r.json()
        if not rows:
            break
        for row in rows:
            t = (row.get("ticker") or "").strip().upper()
            if t and _re.match(r"^[A-Z]{4}11$", t):
                tickers.add(t)
        if len(rows) < 1000:
            break
        offset += 1000
    return sorted(tickers)


def _save_batch(all_videos, batch_size=1000, upsert=False):
    """Save videos to Supabase.

    When upsert=False: only inserts new videos (skips existing video_ids).
    When upsert=True: upserts all videos (updates existing rows on conflict by video_id).
    """
    if not all_videos:
        return 0
    # Deduplicate by video_id within the batch
    seen = set()
    unique = []
    for v in all_videos:
        vid = v.get("video_id")
        if vid and vid not in seen:
            seen.add(vid)
            unique.append(v)
    all_videos = unique

    if upsert:
        logger.info("Upsertando %s videos (forcar atualizacao)...", len(all_videos))
        total = 0
        with httpx.Client(timeout=60) as client:
            for i in range(0, len(all_videos), batch_size):
                batch = all_videos[i:i + batch_size]
                try:
                    r = client.post(
                        f"{REST}/youtube_videos?on_conflict=video_id",
                        headers=API_HEADERS_UPSERT,
                        json=batch,
                    )
                    if r.status_code in (200, 201):
                        total += len(batch)
                    else:
                        logger.warning("Batch %s upsert falhou: %s", i // batch_size + 1, r.status_code)
                except Exception as e:
                    logger.warning("Batch %s upsert erro: %s", i // batch_size + 1, e)
        return total

    # Check which video_ids already exist in DB (in chunks)
    existing = set()
    all_vids = [v["video_id"] for v in all_videos]
    for i in range(0, len(all_vids), 500):
        chunk = all_vids[i:i + 500]
        filter_str = ",".join(chunk)
        try:
            r = httpx.get(
                f"{REST}/youtube_videos?select=video_id&video_id=in.({filter_str})",
                headers=API_HEADERS,
                timeout=30,
            )
            if r.status_code == 200:
                existing.update(row["video_id"] for row in r.json())
        except Exception:
            pass

    new_only = [v for v in all_videos if v["video_id"] not in existing]
    if not new_only:
        logger.info("Todos os %s videos ja existem na base.", len(all_videos))
        return 0

    logger.info("Inserindo %s videos novos (de %s coletados)...", len(new_only), len(all_videos))

    total = 0
    with httpx.Client(timeout=60) as client:
        for i in range(0, len(new_only), batch_size):
            batch = new_only[i:i + batch_size]
            try:
                r = client.post(
                    f"{REST}/youtube_videos",
                    headers=API_HEADERS,
                    json=batch,
                )
                if r.status_code in (200, 201):
                    total += len(batch)
                else:
                    logger.warning("Batch %s falhou: %s", i // batch_size + 1, r.status_code)
            except Exception as e:
                logger.warning("Batch %s erro: %s", i // batch_size + 1, e)
    return total


def run(force=False):
    tickers = get_tickers()
    if not tickers:
        logger.warning("Nenhum ticker encontrado na base.")
        return

    logger.info("Buscando videos para %s tickers (%s workers)...", len(tickers), WORKERS)
    existing_ids = set() if force else get_existing_ids()
    logger.info("Videos existentes na base: %s (force=%s)", len(existing_ids), force)

    all_new = []
    total_tickers = len(tickers)

    with httpx.Client(headers=HEADERS, timeout=20) as client:
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            future_to_ticker = {
                executor.submit(_scrape_one, client, ticker): ticker
                for ticker in tickers
            }

            done_count = 0
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                done_count += 1
                try:
                    videos = future.result()
                except Exception as e:
                    logger.warning("[%s/%s] %s: erro - %s", done_count, total_tickers, ticker, e)
                    continue

                if not videos:
                    continue

                novos = videos if force else [v for v in videos if v["video_id"] not in existing_ids]
                all_new.extend(novos)
                existing_ids.update(v["video_id"] for v in novos)

                if done_count % 50 == 0 or done_count == total_tickers:
                    logger.info("[%s/%s] %s videos coletados", done_count, total_tickers, len(all_new))

    if all_new:
        logger.info("Salvando %s videos no banco...", len(all_new))
        saved = _save_batch(all_new, upsert=force)
        logger.info("Salvos: %s videos", saved)
    else:
        logger.info("Nenhum video novo encontrado.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    run()
