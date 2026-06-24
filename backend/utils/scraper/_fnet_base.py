import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

FNET_HOMEPAGE = "https://fnet.bmfbovespa.com.br/fnet/publico/"


def _cookies_from_fnet() -> dict[str, str]:
    """Get session cookies from FNET homepage."""
    try:
        resp = httpx.get(FNET_HOMEPAGE, timeout=5, verify=False)
        cookies = {}
        for c in resp.cookies.jar:
            cookies[c.name] = c.value
        return cookies
    except Exception as e:
        logger.warning("Falha ao obter cookies do FNET: %s", e)
        return {}


def _parse_date(value: str) -> str | None:
    """Parse date string to ISO format."""
    if not value or not value.strip():
        return None
    cleaned = value.strip()
    # Already ISO
    if cleaned[:10] != cleaned and len(cleaned) >= 10 and cleaned[4] == "-":
        return cleaned[:10]
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except (ValueError, IndexError):
            continue
    # Fallback: try to extract first 10 chars if it looks like a date
    if len(cleaned) >= 10:
        candidate = cleaned[:10]
        if candidate[2] == "/" and candidate[5] == "/":
            try:
                return datetime.strptime(candidate, "%d/%m/%Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
        if candidate[4] == "-":
            return candidate
    return None
