import json
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else []


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }
    requests.post(url, data=data, timeout=20)


def get_response(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25, allow_redirects=True)
        r.raise_for_status()
        return r
    except Exception:
        return None


def get_page(url):
    r = get_response(url)
    if not r:
        return None
    try:
        return BeautifulSoup(r.text, "html.parser")
    except Exception:
        return None


def extract_links(base_url, soup):
    links = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue

        full = urljoin(base_url, href)

        if not full.startswith("http"):
            continue

        full = full.split("#")[0].strip()
        title = a.get_text(" ", strip=True)

        if full in seen_urls:
            continue

        seen_urls.add(full)
        links.append({
            "url": full,
            "title": title
        })

    return links


def is_candidate_link(link, title=""):
    combined = f"{link} {title}".lower()

    positive = [
        "bando",
        "gara",
        "avviso",
        "appalto",
        "incarico",
        "affidamento",
        "procedura",
        "manifestazione",
        "contratti",
        "trasparenza",
        "bandi",
        ".pdf",
        "news",
        "dettaglio",
        "announcements",
        "announcement"
    ]

    negative = [
        "facebook",
        "instagram",
        "linkedin",
        "mailto",
        "tel:",
        "/feed",
        "/tag/",
        "/category/"
    ]

    if any(x in combined for x in negative):
        return False

    return any(x in combined for x in positive)


def page_text(url):
    r = get_response(url)
    if not r:
        return ""

    content_type = r.headers.get("Content-Type", "").lower()

    # Per ora i PDF non li parsifichiamo davvero:
    # restituiamo almeno l'URL come testo minimo.
    if "application/pdf" in content_type or url.lower().endswith(".pdf"):
        return url.lower()

    try:
        soup = BeautifulSoup(r.text, "html.parser")
        return soup.get_text(" ", strip=True).lower()
    except Exception:
        return ""


def looks_like_archive_or_result(link, text, title=""):
    combined = f"{link} {text} {title}".lower()

    bad_words = [
        "esito",
        "gara esperita",
        "verbale",
        "aggiudicazione",
        "graduatoria",
        "convocazione",
        "commissione",
        "ammissione candidati",
        "presa d'atto",
        "approvazione atti"
    ]

    return any(word in combined for word in bad_words)


def main():
    sources = load_json("sources.json", [])
    keywords = load_json("keywords.json", {"include": [], "exclude": []})
    seen = load_json("seen.json", [])

    include = [k.lower() for k in keywords["include"]]
    exclude = [k.lower() for k in keywords["exclude"]]

    found = []
    updated_seen = list(seen)
    debug_lines = []

    for source in sources:
        source_name = source.get("name", "fonte")
        source_url = source.get("url", "")

        if not source_url:
            debug_lines.append(f"{source_name}: URL mancante")
            continue

        soup = get_page(source_url)

        if not soup:
            debug_lines.append(f"{source_name}: pagina non leggibile")
            continue

        raw_links = extract_links(source_url, soup)

        candidate_links = []
        seen_candidates = set()

        for item in raw_links:
            link = item["url"]
            title = item["title"]

            if not is_candidate_link(link, title):
                continue

            if link in seen_candidates:
                continue

            seen_candidates.add(link)
            candidate_links.append(item)

        matched = 0

        for item in candidate_links:
            link = item["url"]
            title = item["title"]

            if link in seen:
                continue

            text = page_text(link)

            if not text and not title:
                continue

            if looks_like_archive_or_result(link, text, title):
                continue

            combined = f"{text} {link.lower()} {title.lower()}"

            include_matches = [w for w in include if w in combined]
            exclude_matches = [w for w in exclude if w in combined]

            if not include_matches:
                continue

            if exclude_matches:
                continue

            found.append(
                f"Nuovo bando locale individuato\n\n"
                f"Fonte: {source_name}\n"
                f"Titolo link: {title if title else '(senza titolo)'}\n"
                f"Parole trovate: {', '.join(include_matches[:5])}\n"
                f"Link: {link}"
            )

            updated_seen.append(link)
            matched += 1

        debug_lines.append(
            f"{source_name}: link totali={len(raw_links)} candidati={len(candidate_links)} trovati={matched}"
        )

    message_parts = []

    if found:
        message_parts.append("\n\n".join(found[:10]))
        if len(found) > 10:
            message_parts.append(f"... altri {len(found) - 10} risultati.")
        save_json("seen.json", updated_seen)
    else:
        message_parts.append("Nessun nuovo bando locale trovato.")

    message_parts.append("DEBUG monitor locale\n\n" + "\n".join(debug_lines[:20]))

    final_message = "\n\n".join(message_parts)
    send_telegram_message(final_message)


if __name__ == "__main__":
    main()
