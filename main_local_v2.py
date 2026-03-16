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
            return None
        if len(r.text) < 300:
            return None
        return BeautifulSoup(r.text, "html.parser")
    except Exception:
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

    return soup.get_text(" ", strip=True)[:3000]


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


def relevance_score(text):
    t = text.lower()
    score = 0
    hits = []

    positive = {
        "agronom": 5,
        "forest": 5,
        "verde": 4,
        "verde urbano": 5,
        "alber": 4,
        "vta": 6,
        "paesagg": 4,
        "giardin": 4,
        "parchi": 4,
        "agricolt": 4,
        "ambient": 4,
        "territorio": 3,
        "biodivers": 4,
        "rinatural": 5,
        "ingegneria naturalistica": 6,
        "difesa del suolo": 6,
        "assetto idrogeologico": 6,
        "forestazione": 5,
        "idraulico forest": 7,
        "sistemazione idraulico": 6,
        "landscape": 5,
        "servizi di ingegneria": 2,
        "progettazione": 2,
        "direzione lavori": 2,
        "manutenzione": 1,
        "servizi tecnici": 2
    }

    negative = {
        "servizio civile": -10,
        "censimento": -8,
        "elettorale": -10,
        "bonus": -8,
        "asilo": -8,
        "infanzia": -8,
        "tribut": -10,
        "riscossione": -10,
        "protes": -10,
        "acciaio": -8,
        "fem": -8,
        "strength": -8,
        "rifiuti": -6,
        "igiene urbana": -6,
        "beni culturali": -3,
        "cultural heritage": -3
    }

    for k, v in positive.items():
        if k in t:
            score += v
            hits.append(f"+{k}")

    for k, v in negative.items():
        if k in t:
            score += v
            hits.append(f"{k}")

    return score, hits


def is_relevant(text):
    score, _ = relevance_score(text)
    return score >= 5


def parse_html_list(source):
    soup = get_page(source["url"])
    if not soup:
        return []

    results = []
    seen_links = set()

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
        href = a["href"].strip()
        title = a.get_text(" ", strip=True)

        if not href:
            continue

        if title.strip().lower() in generic_bad_titles:
            continue

        text = (title + " " + href).lower()

        keywords = [
            "bando",
            "gara",
            "avviso",
            "manifestazione",
            "incarico",
            "affidamento"
        ]

        if not any(k in text for k in keywords):
            continue

        link = urljoin(source["url"], href)

        if link in seen_links:
            continue
        seen_links.add(link)

        # UNISA: tieni solo la pagina html del bando
        if "unisa.it" in source["url"]:
            if link.lower().endswith(".pdf"):
                continue
            if "bando=" not in link and "anno=" not in link:
                continue

        page_text = get_text_from_page(link)

        results.append(
            {
                "source": source["name"],
                "title": title if title else "Avviso",
                "link": link,
                "text": page_text
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

        if not page_text:
            continue

        if not title or len(title) < 8:
            title = page_text[:250]

        if not is_recent(page_text):
            continue

        results.append(
            {
                "source": source["name"],
                "title": title if title else "Procedura di gara",
                "link": link,
                "text": page_text
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

            if source_type == "html_list":
                results = parse_html_list(source)
            elif source_type == "traspare":
                results = parse_traspare(source)
            else:
                results = []

            health[source_name] = {
                "last_results": len(results)
            }

            debug.append(f"{source_name}: risultati parser={len(results)}")
            all_results.extend(results)

        debug.append(f"totale risultati grezzi: {len(all_results)}")

        new_items = []
        seen_keys_run = set()

        for item in all_results:
            full_text = (item["title"] + " " + item.get("text", "")).strip()
            score, hits = relevance_score(full_text)

            item["score"] = score
            item["hits"] = hits

            if score < 5:
                continue

            key = item.get("seen_key", item["link"])

            if key in seen:
                continue

            if key in seen_keys_run:
                continue

            new_items.append(item)
            seen.append(key)
            seen_keys_run.add(key)

        debug.append(f"nuovi risultati dopo deduplica: {len(new_items)}")

        save_json("seen.json", seen)
        save_health(health)

        subject = f"Monitor bandi – {len(new_items)} nuovi risultati" if new_items else "Monitor bandi – debug"

        body = ""

        if new_items:
            body += "Monitor bandi – nuovi risultati\n\n"

            for item in new_items:
                body += (
                    f"{item['source']}\n"
                    f"{item['title']}\n"
                    f"Score: {item['score']}\n"
                    f"Match: {', '.join(item['hits'][:8])}\n"
                    f"{item['link']}\n\n"
                )
        else:
            body += "Nessun nuovo bando trovato.\n\n"

        body += "DEBUG\n\n" + "\n".join(debug)

        send_email(subject, body)

    except Exception as e:
        subject = "Monitor bandi – errore"
        body = f"Errore monitor:\n\n{repr(e)}"
        send_email(subject, body)


if __name__ == "__main__":
    main()
