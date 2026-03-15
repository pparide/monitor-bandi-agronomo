import json
import os
import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }
    requests.post(url, data=data, timeout=20)


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default if default else []


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_page(url):
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except:
        return None


def main():

    sources = load_json("sources_traspare.json", [])
    keywords = load_json("keywords.json", {"include": [], "exclude": []})
    seen = load_json("seen_traspare.json", [])

    include = [k.lower() for k in keywords["include"]]
    exclude = [k.lower() for k in keywords["exclude"]]

    found = []
    updated_seen = list(seen)

    for source in sources:

        name = source["name"]
        url = source["url"]

        soup = get_page(url)

        if not soup:
            continue

        links = soup.find_all("a")

        for a in links:

            href = a.get("href")

            if not href:
                continue

            if "announcements" not in href and "announcement" not in href:
                continue

            if href.startswith("/"):
                href = url.rstrip("/") + href

            if href in seen:
                continue

            text = a.get_text(" ", strip=True).lower()

            include_matches = [w for w in include if w in text]
            exclude_matches = [w for w in exclude if w in text]

            if not include_matches:
                continue

            if exclude_matches:
                continue

            found.append(
                f"Nuovo bando Traspare\n\n"
                f"Fonte: {name}\n"
                f"Parole trovate: {', '.join(include_matches)}\n"
                f"Link: {href}"
            )

            updated_seen.append(href)

    if found:

        message = "\n\n".join(found[:10])

        send_telegram_message(message)

        save_json("seen_traspare.json", updated_seen)


if __name__ == "__main__":
    main()
