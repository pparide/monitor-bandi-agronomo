import json
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

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


# -----------------------------
# PARSER PDF ARCHIVE
# -----------------------------


def parse_pdf_archive(source):

    soup = get_page(source["url"])

    if not soup:
        return []

    # Documenti che ci fanno capire che la pagina contiene davvero una gara
    good_words = [
        "bando",
        "avviso",
        "disciplinare",
        "manifestazione",
        "incarico",
        "affidamento",
        "capitolato",
        "lettera",
        "invito",
        "determina"
    ]

    found_titles = []

    for a in soup.find_all("a", href=True):

        href = a["href"]
        title = a.get_text(strip=True)

        if ".pdf" not in href.lower():
            continue

        text = (title + " " + href).lower()

        if any(word in text for word in good_words):
            found_titles.append(title if title else "Documento di gara")

    # Se non troviamo documenti principali, non segnaliamo nulla
    if not found_titles:
        return []

    # Scegliamo il titolo migliore da mostrare
    priority_order = [
        "bando",
        "avviso",
        "disciplinare",
        "manifestazione",
        "affidamento",
        "incarico",
        "capitolato",
        "determina"
    ]

    best_title = found_titles[0]

    for keyword in priority_order:
        for title in found_titles:
            if keyword in title.lower():
                best_title = title
                break
        else:
            continue
        break

    return [
        {
            "source": source["name"],
            "title": best_title,
            "link": source["url"]
        }
    ]


# -----------------------------
# PARSER HTML LIST
# -----------------------------


def parse_html_list(source):

    soup = get_page(source["url"])

    if not soup:
        return []

    results = []

    for a in soup.find_all("a", href=True):

        href = a["href"]
        title = a.get_text(strip=True)

        text = (title + href).lower()

        keywords = [
            "bando",
            "gara",
            "avviso",
            "manifestazione",
            "incarico",
            "affidamento",
        ]

        if not any(k in text for k in keywords):
            continue

        link = urljoin(source["url"], href)

        results.append(
            {
                "source": source["name"],
                "title": title,
                "link": link,
            }
        )

    return results


# -----------------------------
# PARSER TRASPARE
# -----------------------------


def parse_traspare(source):

    soup = get_page(source["url"])

    if not soup:
        return []

    results = []

    for a in soup.find_all("a", href=True):

        href = a["href"]
        title = a.get_text(strip=True)

        if "announcement" not in href and "gara" not in href:
            continue

        link = urljoin(source["url"], href)

        results.append(
            {
                "source": source["name"],
                "title": title,
                "link": link,
            }
        )

    return results


# -----------------------------
# PARSER PORTALE APPALTI
# -----------------------------


def parse_portale_appalti(source):

    soup = get_page(source["url"])

    if not soup:
        return []

    results = []

    for a in soup.find_all("a", href=True):

        href = a["href"]
        title = a.get_text(strip=True)

        text = (title + href).lower()

        if "bando" not in text and "gara" not in text:
            continue

        link = urljoin(source["url"], href)

        results.append(
            {
                "source": source["name"],
                "title": title,
                "link": link,
            }
        )

    return results


# -----------------------------
# MAIN
# -----------------------------


def main():

    sources = load_json("sources.json", [])
    seen = load_json("seen.json", [])

    all_results = []

    debug = []

    for source in sources:

        if source["type"] == "pdf_archive":
            results = parse_pdf_archive(source)

        elif source["type"] == "html_list":
            results = parse_html_list(source)

        elif source["type"] == "traspare":
            results = parse_traspare(source)

        elif source["type"] == "portale_appalti":
            results = parse_portale_appalti(source)

        else:
            results = []

        debug.append(f"{source['name']}: trovati {len(results)} link")

        all_results.extend(results)

    new_items = []

    for item in all_results:

        if item["link"] in seen:
            continue

        new_items.append(item)
        seen.append(item["link"])

    save_json("seen.json", seen)

    if not new_items:

        send_telegram(
            "Monitor bandi\n\nNessun nuovo bando trovato.\n\n"
            + "\n".join(debug)
        )

        return

    message = "Monitor bandi – nuovi risultati\n\n"

    for item in new_items[:10]:

        message += (
            f"{item['source']}\n"
            f"{item['title']}\n"
            f"{item['link']}\n\n"
        )

    if len(new_items) > 10:
        message += f"... altri {len(new_items)-10} risultati"

    message += "\nDEBUG\n" + "\n".join(debug)

    send_telegram(message)


if __name__ == "__main__":
    main()
