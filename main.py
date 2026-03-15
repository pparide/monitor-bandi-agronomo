import json
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

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


def get_page(url):
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
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

        if not full.startswith("http"):
            continue

        links.add(full)

    return list(links)


def is_candidate_link(link):
    link = link.lower()

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
        "dettaglio"
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

    if any(x in link for x in negative):
        return False

    return any(x in link for x in positive)


def page_text(url):

    try:
        r = requests.get(url, timeout=20)

        content_type = r.headers.get("Content-Type", "").lower()

        if "pdf" in content_type or url.lower().endswith(".pdf"):
            return url.lower()

        soup = BeautifulSoup(r.text, "html.parser")
        return soup.get_text(" ", strip=True).lower()

    except Exception:
        return ""


def looks_like_archive_or_result(link, text):

    combined = (link + " " + text).lower()

    bad_words = [
        "esito",
        "gara esperita",
        "verbale",
        "aggiudicazione",
        "graduatoria",
        "convocazione",
        "commissione",
        "ammissione candidati",
        "presa d'atto"
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

        soup = get_page(source_url)

        if not soup:
            debug_lines.append(f"{source_name}: pagina non leggibile")
            continue

        raw_links = extract_links(source_url, soup)

        candidate_links = []

        for link in raw_links:

            if not is_candidate_link(link):
                continue

            if link not in candidate_links:
                candidate_links.append(link)

        matched = 0

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

            matched += 1

        debug_lines.append(
            f"{source_name}: link totali={len(raw_links)} candidati={len(candidate_links)} trovati={matched}"
        )

    if found:

        message = "\n\n".join(found[:10])

        if len(found) > 10:
            message += f"\n\n... altri {len(found)-10} risultati."

        send_telegram_message(message)

        save_json("seen.json", updated_seen)

    else:

        debug_message = "DEBUG monitor locale\n\n" + "\n".join(debug_lines[:20])

        send_telegram_message(debug_message)


if __name__ == "__main__":
    main()
