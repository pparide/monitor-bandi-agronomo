import json
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


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
        r = requests.get(url, timeout=20, allow_redirects=True)
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
    links = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue

        full = urljoin(base_url, href)

        # Tieni solo http/https
        if not full.startswith("http"):
            continue

        links.add(full)

    return list(links)


def normalize_link(link):
    # Rimuove eventuale fragment finale
    return link.split("#")[0].strip()


def is_pdf_link(link):
    return ".pdf" in link.lower()


def is_candidate_link(link):
    l = link.lower()

    positive_markers = [
        "bando",
        "gara",
        "avviso",
        "procedura",
        "manifestazione",
        "incarico",
        "affidamento",
        "appalto",
        "bandi",
        "contratti",
        "trasparenza",
        "announcements",
        "dettaglio",
        "news",
        "articolo",
        ".pdf"
    ]

    negative_markers = [
        "facebook",
        "instagram",
        "linkedin",
        "youtube",
        "mailto:",
        "tel:",
        "/feed",
        "/tag/",
        "/category/"
    ]

    if any(x in l for x in negative_markers):
        return False

    return any(x in l for x in positive_markers)


def page_text(url):
    r = get_response(url)
    if not r:
        return ""

    content_type = r.headers.get("Content-Type", "").lower()

    # Se è PDF, per ora non lo leggiamo davvero come testo.
    # Lo consideriamo però candidato in base a titolo/link.
    if "application/pdf" in content_type or url.lower().endswith(".pdf"):
        return f"pdf document {url.lower()}"

    try:
        soup = BeautifulSoup(r.text, "html.parser")
        return soup.get_text(" ", strip=True).lower()
    except Exception:
        return ""


def looks_like_archive_or_result(link, text):
    combined = f"{link.lower()} {text.lower()}"

    bad_words = [
        "esito",
        "gara esperita",
        "verbale",
        "aggiudicazione",
        "graduatoria",
        "convocazione",
        "nomina commissione",
        "commissione esaminatrice",
        "ammissione candidati",
        "rettifica esito",
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

    for source in sources:
        source_name = source.get("name", "Fonte senza nome")
        source_url = source.get("url", "")

        if not source_url:
            continue

        soup = get_page(source_url)
        if not soup:
            continue

        raw_links = extract_links(source_url, soup)
        candidate_links = []

        for raw_link in raw_links:
            link = normalize_link(raw_link)

            if not is_candidate_link(link):
                continue

            if link in candidate_links:
                continue

            candidate_links.append(link)

        for link in candidate_links:
            if link in seen:
                continue

            text = page_text(link)

            if not text:
                continue

            if looks_like_archive_or_result(link, text):
                continue

            include_matches = [w for w in include if w in text or w in link.lower()]
            exclude_matches = [w for w in exclude if w in text or w in link.lower()]

            if not include_matches:
                continue

            if exclude_matches:
                continue

            found.append(
                f"Nuovo bando locale individuato\n\n"
                f"Fonte: {source_name}\n"
                f"Parole trovate: {', '.join(include_matches[:5])}\n"
                f"Link: {link}"
            )

            updated_seen.append(link)

    if found:
        message = "\n\n".join(found[:10])

        # Se ci sono più di 10 risultati, manda un avviso finale
        if len(found) > 10:
            message += f"\n\n...e altri {len(found) - 10} risultati."

        send_telegram_message(message)
        save_json("seen.json", updated_seen)


if __name__ == "__main__":
    main()
