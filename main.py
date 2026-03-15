import json
import os
import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


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


def page_text(url):
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        return soup.get_text(" ", strip=True).lower()
    except Exception as e:
        return f"errore lettura pagina: {e}"


def main():
    sources = load_json("sources.json", [])
    keywords = load_json("keywords.json", {"include": [], "exclude": []})
    seen = load_json("seen.json", [])

    include = [k.lower() for k in keywords["include"]]
    exclude = [k.lower() for k in keywords["exclude"]]

    found = []
    updated_seen = list(seen)

    for source in sources:
        source_id = source["url"]

        if source_id in seen:
            continue

        text = page_text(source["url"])

        if text.startswith("errore lettura pagina"):
            continue

        include_matches = [word for word in include if word in text]
        exclude_matches = [word for word in exclude if word in text]

        if include_matches and not exclude_matches:
            found.append(
                f"- {source['name']}\n"
                f"  parole trovate: {', '.join(include_matches[:5])}\n"
                f"  link: {source['url']}"
            )
            updated_seen.append(source_id)

    if found:
        message = "Nuove fonti potenzialmente interessanti trovate:\n\n" + "\n\n".join(found)
        send_telegram_message(message)
        save_json("seen.json", updated_seen)


if __name__ == "__main__":
    main()
    include = [k.lower() for k in keywords["include"]]
    exclude = [k.lower() for k in keywords["exclude"]]

    found = []

    for source in sources:
        text = page_text(source["url"])

        if text.startswith("errore lettura pagina"):
            continue

        include_matches = [word for word in include if word in text]
        exclude_matches = [word for word in exclude if word in text]

        if include_matches and not exclude_matches:
            found.append(
                f"- {source['name']}\n"
                f"  parole trovate: {', '.join(include_matches[:5])}\n"
                f"  link: {source['url']}"
            )

    if found:
        message = "Possibili bandi interessanti trovati:\n\n" + "\n\n".join(found)
    else:
        message = "Nessun bando interessante trovato nel controllo di prova."

    send_telegram_message(message)


if __name__ == "__main__":
    main()
