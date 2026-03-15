import json
import os
import io
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from PyPDF2 import PdfReader

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HEADERS = {"User-Agent": "Mozilla/5.0"}


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})


def get_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except:
        return None


def extract_links(base_url, soup):

    links = []

    for a in soup.find_all("a", href=True):

        href = a["href"].strip()
        title = a.get_text(" ", strip=True)

        if not href:
            continue

        full = urljoin(base_url, href)
        full = full.split("#")[0]

        links.append({
            "url": full,
            "title": title
        })

    return links


def looks_like_bando(url, title):

    text = (url + " " + title).lower()

    keywords = [
        "bando",
        "gara",
        "avviso",
        "manifestazione",
        "affidamento",
        "incarico",
        "disciplinare",
        "capitolato",
        "appalto",
        ".pdf"
    ]

    return any(k in text for k in keywords)


def read_pdf(url):

    try:

        r = requests.get(url, headers=HEADERS, timeout=30)
        reader = PdfReader(io.BytesIO(r.content))

        text = ""

        for page in reader.pages[:6]:
            try:
                text += page.extract_text() or ""
            except:
                pass

        return text.lower()

    except:
        return ""


def read_html(url):

    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        return soup.get_text(" ", strip=True).lower()
    except:
        return ""


def read_content(url):

    if url.lower().endswith(".pdf"):
        return read_pdf(url)

    return read_html(url)


def score_text(text, rules):

    score = 0

    for word, value in rules["positive"].items():
        if word in text:
            score += value

    for word, value in rules["negative"].items():
        if word in text:
            score += value

    return score


def main():

    sources = load_json("sources.json", [])
    rules = load_json("rules.json", {})
    seen = load_json("seen.json", [])

    found = []
    new_seen = list(seen)

    debug = []

    for source in sources:

        name = source["name"]
        url = source["url"]

        soup = get_page(url)

        if not soup:
            debug.append(f"{name}: pagina non leggibile")
            continue

        links = extract_links(url, soup)

        candidates = []

        for link in links:

            if looks_like_bando(link["url"], link["title"]):
                candidates.append(link)

        matches = 0

        for link in candidates:

            url = link["url"]
            title = link["title"]

            if url in seen:
                continue

            content = read_content(url)

            text = (title + " " + url + " " + content).lower()

            score = score_text(text, rules)

            if score < rules["threshold"]:
                continue

            found.append(
                f"Nuovo bando individuato\n\n"
                f"Fonte: {name}\n"
                f"Titolo: {title}\n"
                f"Score: {score}\n"
                f"Link: {url}"
            )

            new_seen.append(url)

            matches += 1

        debug.append(
            f"{name}: link totali={len(links)} candidati={len(candidates)} match={matches}"
        )

    if found:

        message = "\n\n".join(found[:10])

        if len(found) > 10:
            message += f"\n\nAltri {len(found)-10} risultati."

        send_telegram(message)

        save_json("seen.json", new_seen)

    else:

        send_telegram(
            "Nessun nuovo bando trovato\n\nDEBUG\n\n" + "\n".join(debug)
        )


if __name__ == "__main__":
    main()
