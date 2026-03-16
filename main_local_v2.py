import json
import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

EMAIL_HOST = os.environ["EMAIL_HOST"]
EMAIL_PORT = int(os.environ["EMAIL_PORT"])
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
EMAIL_TO = os.environ["EMAIL_TO"]

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


def load_health():
    return load_json("source_health.json", {})


def save_health(data):
    save_json("source_health.json", data)


def send_email(subject, body):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT) as server:
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())


def get_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)

        if r.status_code != 200:
            print(f"ERRORE HTTP {r.status_code} su {url}")
            return None

        if len(r.text) < 500:
            print(f"Pagina sospetta (troppo corta): {url}")
            return None

        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"Errore richiesta {url}: {e}")
        return None


def get_text_from_page(url):
    soup = get_page(url)
    if not soup:
        return ""

    for tag in ["h1", "h2", "title"]:
        el = soup.find(tag)
        if el:
            text = el.get_text(" ", strip=True)
            if text:
                return text

    return soup.get_text(" ", strip=True)[:500]


def slugify_comune(name):
    text = name.lower().strip()

    replacements = {
        "à": "a", "è": "e", "é": "e", "ì": "i", "ò": "o", "ù": "u",
        "'": "", "’": "", ".": "", ",": "", "-": "", "/": "",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = text.replace(" ", "")
    return text


def candidate_traspare_slugs(name):
    base = slugify_comune(name)
    candidates = {base}

    if "cava de' tirreni" in name.lower():
        candidates.add("cavadetirreni")
    if "mercato san severino" in name.lower():
        candidates.add("mercatosanseverino")
    if "vallo della lucania" in name.lower():
        candidates.add("vallodellalucania")
    if "pontecagnano faiano" in name.lower():
        candidates.add("pontecagnanofaiano")
    if "capaccio paestum" in name.lower():
        candidates.add("capacciopaestum")

    return list(candidates)


def generate_traspare_sources():
    comuni = load_json("comuni_sa_av.json", {})
    sources = []

    for provincia in ["salerno", "avellino"]:
        for comune in comuni.get(provincia, []):
            for slug in candidate_traspare_slugs(comune):
                sources.append(
                    {
                        "name": f"Comune di {comune}",
                        "url": f"https://{slug}.traspare.com/announcements",
                        "type": "traspare"
                    }
                )

    return sources


def is_recent(text, days=120):
    today = datetime.today()
    limit = today - timedelta(days=days)

    pattern = r"\b\d{2}/\d{2}/\d{4}\b"

    for match in re.findall(pattern, text):
        try:
            d = datetime.strptime(match, "%d/%m/%Y")
            if d >= limit:
                return True
        except Exception:
            pass

    return False


def is_relevant(title):
    text = title.lower()

    strong_keywords = [
        "agronom",
        "forest",
        "verde",
        "alber",
        "vta",
        "paesagg",
        "giardin",
        "parchi",
        "agricolt",
        "ambient",
        "territorio",
        "biodivers",
        "rinatural",
        "idraulico forest",
        "sistemazione idraulico",
        "ingegneria naturalistica",
        "landscape",
        "idraulico",
        "difesa del suolo",
        "assetto idrogeologico",
        "forestazione"
    ]

    technical_keywords = [
        "progettazione",
        "servizi di ingegneria",
        "direzione lavori",
        "piano",
        "manutenzione",
        "accordo quadro",
        "appalto",
        "servizi tecnici"
    ]

    territory_keywords = [
        "verde",
        "ambient",
        "territorio",
        "forest",
        "paesagg",
        "agricolt"
    ]

    excluded_keywords = [
        "servizio civile",
        "censimento",
        "elettorale",
        "bonus",
        "asilo",
        "infanzia",
        "riscossione",
        "tribut",
        "protes",
        "acciaio",
        "fem",
        "strength"
    ]

    if any(k in text for k in excluded_keywords):
        return False

    if any(k in text for k in strong_keywords):
        return True

    if any(k in text for k in technical_keywords) and any(k in text for k in territory_keywords):
        return True

    return False


def parse_pdf_archive(source):
    soup = get_page(source["url"])

    if not soup:
        return []

    main_doc_keywords = [
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

    ignore_keywords = [
        "tav",
        "tavola",
        "computo",
        "cronoprogramma",
        "psc",
        "piano di sicurezza",
        "piano manutenzione",
        "elenco prezzi",
        "relazione tecnica",
        "schema",
        "grafico"
    ]

    results = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(strip=True)

        if ".pdf" not in href.lower():
            continue

        pdf_link = urljoin(source["url"], href)
        text = f"{title} {href}".lower()

        if any(word in text for word in ignore_keywords):
            continue

        if any(word in text for word in main_doc_keywords):
            results.append(
                {
                    "source": source["name"],
                    "title": title if title else "Documento di gara",
                    "link": source["url"],
                    "seen_key": pdf_link
                }
            )

    return results


def parse_html_list(source):
    soup = get_page(source["url"])

    if not soup:
        return []

    results = []

    generic_bad_titles = [
        "vai alla pagina",
        "home",
        "pagina iniziale",
        "clicca qui",
        "maggiori informazioni",
        "leggi tutto",
        "scarica",
        "download",
        "procedure di gara"
    ]

    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(strip=True)

        text = (title + " " + href).lower()

        if title.strip().lower() in generic_bad_titles:
            continue

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

        if "unisa.it" in source["url"]:
            if link.lower().endswith(".pdf"):
                continue
            if "bando=" not in link and "anno=" not in link:
                continue

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
    seen_links = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue

        link = urljoin(source["url"], href)
        l = link.lower()

        if not re.search(r"/announcements/\d+/?$", l):
            continue

        if link in seen_links:
            continue

        seen_links.add(link)

        title = a.get_text(" ", strip=True)
        page_text = get_text_from_page(link)

        if not title or len(title) < 8:
            title = page_text

        if not is_recent(page_text):
            continue

        results.append(
            {
                "source": source["name"],
                "title": title if title else "Procedura di gara",
                "link": link,
            }
        )

    return results


def parse_portale_appalti(source):
    soup = get_page(source["url"])

    if not soup:
        return []

    results = []
    seen_links = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(" ", strip=True)

        if not href:
            continue

        link = urljoin(source["url"], href)
        text = f"{title} {href}".lower()

        if not any(k in text for k in [
            "bando",
            "gara",
            "avviso",
            "procedura",
            "manifestazione",
            "affidamento"
        ]):
            continue

        if any(k in text for k in [
            "home",
            "pagina iniziale",
            "accedi",
            "login",
            "profilo",
            "contatti",
            "faq",
            "help",
            "manuale"
        ]):
            continue

        if link in seen_links:
            continue

        seen_links.add(link)

        if not title or len(title) < 8:
            title = get_text_from_page(link)

        results.append(
            {
                "source": source["name"],
                "title": title if title else "Procedura di gara",
                "link": link,
            }
        )

    return results


def main():
    debug = []

    try:
        sources = load_json("sources.json", [])
        sources.extend(load_json("traspare_valid_sources.json", []))

        unique_sources = []
        seen_urls = set()

        for s in sources:
            url = s.get("url", "").strip()

            if not url:
                continue

            if url in seen_urls:
                continue

            seen_urls.add(url)
            unique_sources.append(s)

        sources = unique_sources

        seen = load_json("seen.json", [])
        health = load_health()

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

            health[source_name] = {
                "last_results": len(results)
            }

            all_results.extend(results)

        debug.append(f"totale risultati grezzi: {len(all_results)}")

        new_items = []
        seen_keys_run = set()

        for item in all_results:
            if not is_relevant(item["title"]):
                continue

            key = item.get("seen_key", item["link"])

            if key in seen_keys_run:
                continue

            if key in seen:
                continue

            new_items.append(item)
            seen.append(key)
            seen_keys_run.add(key)

        debug.append(f"nuovi risultati dopo deduplica: {len(new_items)}")

        save_json("seen.json", seen)
        debug.append("seen.json salvato")

        save_health(health)
        debug.append("source_health.json salvato")

        if not new_items:
            subject = "Monitor bandi – debug"
            body = "Nessun nuovo bando trovato.\n\nDEBUG\n\n" + "\n".join(debug)
            send_email(subject, body)
            return

        subject = f"Monitor bandi – {len(new_items)} nuovi risultati"
        body = "Monitor bandi – nuovi risultati\n\n"

        for item in new_items:
            body += (
                f"{item['source']}\n"
                f"{item['title']}\n"
                f"{item['link']}\n\n"
            )

        body += "DEBUG\n" + "\n".join(debug)

        send_email(subject, body)

    except Exception as e:
        subject = "Monitor bandi – errore"
        body = "Si è verificato un errore nel monitor.\n\n"
        body += "DEBUG\n\n" + "\n".join(debug) + f"\n\nERRORE: {repr(e)}"
        send_email(subject, body)


if __name__ == "__main__":
    main()
