import requests
import json
import time
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

TIMEOUT = 15

KEYWORDS = [
    "agronomo",
    "agronomica",
    "forestale",
    "verde",
    "verde urbano",
    "manutenzione verde",
    "paesaggio",
    "piano del verde",
    "agricolo",
    "agricoltura"
]


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default if default else []


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fetch_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.text
    except:
        pass
    return ""


def extract_basic_links(html, base_url):

    results = []

    html = html.replace("\n", " ")

    parts = html.split("<a ")

    for part in parts:

        if "href" not in part:
            continue

        try:

            href = part.split("href=")[1].split(">")[0]

            href = href.replace('"', "").replace("'", "")

            if href.startswith("/"):
                href = base_url + href

            title = part.split(">")[1].split("<")[0]

            title = title.strip()

            if len(title) < 5:
                continue

            results.append((title, href))

        except:
            pass

    return results


def keyword_filter(title):

    t = title.lower()

    for k in KEYWORDS:
        if k in t:
            return True

    return False


def deduplicate_sources(sources):

    unique = []
    seen = set()

    for s in sources:

        url = s.get("url", "").strip()

        if not url:
            continue

        if url in seen:
            continue

        seen.add(url)
        unique.append(s)

    return unique


def run_monitor():

    print("Monitor bandi – avvio")

    sources = load_json("sources.json", [])

    traspare_sources = load_json("traspare_valid_sources.json", [])

    sources.extend(traspare_sources)

    sources = deduplicate_sources(sources)

    print("fonti caricate:", len(sources))

    seen = load_json("seen.json", [])

    new_results = []

    total_raw = 0

    for s in sources:

        name = s.get("name")
        url = s.get("url")

        print(name)

        html = fetch_page(url)

        if not html:
            print("  pagina non raggiungibile")
            continue

        links = extract_basic_links(html, url)

        print("  risultati parser=", len(links))

        total_raw += len(links)

        for title, link in links:

            if link in seen:
                continue

            seen.append(link)

            if keyword_filter(title):

                new_results.append({
                    "ente": name,
                    "titolo": title,
                    "url": link
                })

        time.sleep(1)

    print("\ntotale risultati grezzi:", total_raw)
    print("nuovi risultati:", len(new_results))

    save_json("seen.json", seen)

    if new_results:

        print("\nNUOVI BANDI TROVATI\n")

        for r in new_results:

            print(r["ente"])
            print(r["titolo"])
            print(r["url"])
            print()

    else:

        print("\nNessun nuovo bando trovato.")


if __name__ == "__main__":

    start = datetime.now()

    run_monitor()

    end = datetime.now()

    print("\ndurata:", end - start)
