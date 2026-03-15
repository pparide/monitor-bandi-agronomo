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
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base_url, href)
        links.append(full)
    return links


def is_candidate_link(link):
    keywords = [
        "bando",
        "gara",
        "avviso",
        "procedura",
        "manifestazione",
        "incarico",
        "affidamento"
    ]
    l = link.lower()
    return any(k in l for k in keywords)


def page_text(url):
    soup = get_page(url)
    if not soup:
        return ""
    return soup.get_text(" ", strip=True).lower()


def main():

    sources = load_json("sources.json", [])
    keywords = load_json("keywords.json", {"include": [], "exclude": []})
    seen = load_json("seen.json", [])

    include = [k.lower() for k in keywords["include"]]
    exclude = [k.lower() for k in keywords["exclude"]]

    found = []
    updated_seen = list(seen)

    for source in sources:

        source_name = source["name"]
        source_url = source["url"]

        soup = get_page(source_url)

        if not soup:
            continue

        links = extract_links(source_url, soup)

        for link in links:

            if not is_candidate_link(link):
                continue

            if link in seen:
                continue

            text = page_text(link)

            include_matches = [w for w in include if w in text]
            exclude_matches = [w for w in exclude if w in text]

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
        message = "\n\n".join(found)
        send_telegram_message(message)
        save_json("seen.json", updated_seen)


if __name__ == "__main__":
    main()
