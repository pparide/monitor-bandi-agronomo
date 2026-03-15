import json
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import io
from PyPDF2 import PdfReader

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "it-IT,it;q=0.9"
}


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default if default else []


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text
        },
        timeout=20
    )


def get_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
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

        if not full.startswith("http"):
            continue

        links.append({
            "url": full,
            "title": title
        })

    return links


def read_pdf(url):

    try:

        r = requests.get(url, headers=HEADERS, timeout=30)

        pdf = PdfReader(io.BytesIO(r.content))

        text = ""

        for page in pdf.pages[:5]:
            try:
                text += page.extract_text() or ""
            except:
                pass

        return text.lower()

    except:
        return ""


def read_html(url):

    try:

        r = requests.get(url, headers=HEADERS, timeout=25)

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

    sources = load_json("sources.json")
    rules = load_json("rules.json")
    seen = load_json("seen.json", [])

    found = []
    debug = []
    updated_seen = list(seen)

    for source in sources:

        name = source["name"]
        url = source["url"]

        soup = get_page(url)

        if not soup:
            debug.append(f"{name}: pagina non leggibile")
            continue

        links = extract_links(url, soup)

        links = links[:30]  # limita archivio

        matches = 0

        for item in links:

            link = item["url"]
            title = item["title"]

            if link in seen:
                continue

            content = read_content(link)

            combined = f"{title} {link} {content}".lower()

            score = score_text(combined, rules)

            if score < rules["threshold"]:
                continue

            found.append(
                f"Nuovo bando individuato\n\n"
                f"Fonte: {name}\n"
                f"Titolo: {title}\n"
                f"Score: {score}\n"
                f"Link: {link}"
            )

            updated_seen.append(link)
            matches += 1

        debug.append(
            f"{name}: link analizzati={len(links)} match={matches}"
        )

    if found:

        message = "\n\n".join(found[:10])

        send_telegram_message(message)

        save_json("seen.json", updated_seen)

    else:

        send_telegram_message(
            "Nessun nuovo bando trovato\n\nDEBUG\n\n" + "\n".join(debug)
        )


if __name__ == "__main__":
    main()
