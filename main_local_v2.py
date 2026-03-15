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
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(
        url,
        data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
        timeout=20
    )
    print("Telegram status:", r.status_code)
    print("Telegram response:", r.text)


def get_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception:
        return None


def parse_pdf_archive(source):
    soup = get_page(source["url"])

    if not soup:
        return []

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

    if not found_titles:
        return []

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


def parse_traspare(source):
    soup = get_page(source["url"])

    if not soup:
        return []

    results = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(strip=True)

        h = href.lower()

        if "announcement" not in h and "gara" not in h and "announcements" not in h:
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


def parse_portale_appalti(source):
    soup = get_page(source["url"])

    if not soup:
        return []

    results = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(strip=True)

        text = (title + href).lower()

        if "bando" not in text and "gara" not in text and "avviso" not in text:
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


def main():
    debug = []
    try:
        debug.append("main avviato")

        sources = load_json("sources.json", [])
        seen = load_json("seen.json", [])

        debug.append(f"fonti caricate: {len(sources)}")
        debug.append(f"seen caricati: {len(seen)}")

        all_results = []

        for source in sources:
            source_type = source.get("type", "")
            source_name = source.get("name", "fonte")

            if source_type == "pdf_archive":
                results = parse_pdf_archive(source)
            elif source_type == "html_list":
                results = parse_html_list(source)
            elif source_type == "traspare":
                results = parse_traspare(source)
            elif source_type == "portale_appalti":
                results = parse_portale_appalti(source)
            else:
                results = []

            debug.append(f"{source_name}: risultati parser={len(results)}")
            all_results.extend(results)

        debug.append(f"risultati totali raccolti: {len(all_results)}")

        new_items = []
        seen_links_run = set()

        for item in all_results:
            link = item["link"]

            if link in seen_links_run:
                continue

            if link in seen:
                continue

            new_items.append(item)
            seen.append(link)
            seen_links_run.add(link)

        debug.append(f"nuovi risultati dopo deduplica: {len(new_items)}")

        save_json("seen.json", seen)
        debug.append("seen.json salvato")

        if not new_items:
            send_telegram(
                "Monitor bandi\n\nNessun nuovo bando trovato.\n\nDEBUG\n\n"
                + "\n".join(debug)
            )
            return

        message = "Monitor bandi – nuovi risultati\n\n"

        for item in new_items:
            message += (
                f"{item['source']}\n"
                f"{item['title']}\n"
                f"{item['link']}\n\n"
            )

        message += "DEBUG\n" + "\n".join(debug)

        send_telegram(message)

    except Exception as e:
        debug.append(f"ERRORE: {repr(e)}")
        try:
            send_telegram("Monitor bandi\n\nDEBUG ERRORE\n\n" + "\n".join(debug))
        except Exception:
            print("Errore anche nell'invio Telegram finale")
            print("\n".join(debug))


if __name__ == "__main__":
    main()
