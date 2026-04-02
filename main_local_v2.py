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

# fonte da ispezionare nei risultati scartati
AUDIT_SOURCE = "Comune di Salerno"
AUDIT_LIMIT = 10


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def normalize_sources(data):
    if not isinstance(data, list):
        return []

    cleaned = []
    for item in data:
        if not isinstance(item, dict):
            continue

        name = item.get("name")
        url = item.get("url")
        source_type = item.get("type")

        if not isinstance(name, str) or not isinstance(url, str) or not isinstance(source_type, str):
            continue

        cleaned.append(
            {
                "name": name.strip(),
                "url": url.strip(),
                "type": source_type.strip(),
            }
        )

    return cleaned


def normalize_seen(data):
    if not isinstance(data, list):
        return []

    cleaned = []
    for item in data:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip())

    return cleaned


def normalize_health(data):
    if not isinstance(data, dict):
        return {}

    cleaned = {}

    for source_name, stats in data.items():
        if not isinstance(source_name, str):
            continue

        if not isinstance(stats, dict):
            stats = {}

        cleaned[source_name] = {
            "runs": int(stats.get("runs", 0) or 0),
            "results": int(stats.get("results", 0) or 0),
            "relevant": int(stats.get("relevant", 0) or 0),
            "zero_runs": int(stats.get("zero_runs", 0) or 0),
        }

    return cleaned


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


def get_page_text(url):
    soup = get_page(url)
    if not soup:
        return ""

    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:5000]


def get_best_title_from_page(url):
    soup = get_page(url)
    if not soup:
        return ""

    for tag in ["h1", "h2", "title"]:
        el = soup.find(tag)
        if el:
            text = el.get_text(" ", strip=True)
            if text:
                return text

    return ""


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


def is_generic_bad_title(title):
    t = title.strip().lower()

    bad_titles = [
        "vai alla pagina",
        "home",
        "pagina iniziale",
        "clicca qui",
        "maggiori informazioni",
        "leggi tutto",
        "scarica",
        "download",
        "procedure di gara",
    ]

    return t in bad_titles


def keyword_score(text):
    text = text.lower()

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
        "servizi tecnici": 2,
        "servizi di ingegneria": 2,
        "progettazione": 2,
        "direzione lavori": 2,
        "vinca": 8,
        "valutazione di incidenza": 8,
        "incidenza ambientale": 7,
        "commissione locale per il paesaggio": 9,
        "commissione paesaggio": 8,
        "paesaggistica": 6,
        "autorizzazione paesaggistica": 7,
        "commissione esperti": 4,
        "esperti ambientali": 5,
        "esperti in materia ambientale": 6,
        "componente esperto": 5,
        "nomina componenti": 5,
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
        "cultural heritage": -6,
        "europrogettazione": -6,
        "beni culturali": -4,
        "lighting design": -6,
        "lightning design": -6,
    }

    score = 0
    hits = []

    for k, v in positive.items():
        if k in text:
            score += v
            hits.append(f"+{k}")

    for k, v in negative.items():
        if k in text:
            score += v
            hits.append(f"{v}{k}")

    return score, hits


def compute_score(item):
    title = item.get("title", "")
    text = item.get("text", "")

    title_score, title_hits = keyword_score(title)
    text_score, text_hits = keyword_score(text)

    final_score = title_score * 3 + int(text_score * 0.7)
    hits = sorted(set(title_hits + text_hits))

    return final_score, title_score, text_score, hits


def parse_html_list(source):
    soup = get_page(source["url"])
    if not soup:
        return []

    results = []
    seen_links = set()

    keywords = [
        "bando",
        "gara",
        "avviso",
        "manifestazione",
        "incarico",
        "affidamento",
    ]

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(" ", strip=True)

        if not href:
            continue

        if is_generic_bad_title(title):
            continue

        text = (title + " " + href).lower()

        if not any(k in text for k in keywords):
            continue

        link = urljoin(source["url"], href)

        if link in seen_links:
            continue
        seen_links.add(link)

        if "unisa.it" in source["url"].lower() or "università di salerno" in source["name"].lower():
            if link.lower().endswith(".pdf"):
                continue
            if "bando=" not in link and "anno=" not in link:
                continue

        page_text = get_page_text(link)
        best_title = title if title else get_best_title_from_page(link)

        results.append(
            {
                "source": source["name"],
                "title": best_title if best_title else "Avviso",
                "link": link,
                "text": page_text,
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

        if not re.search(r"/announcements/\d+/?$", link.lower()):
            continue

        if link in seen_links:
            continue
        seen_links.add(link)

        title = a.get_text(" ", strip=True)
        page_text = get_page_text(link)

        if not page_text:
            continue

        if not is_recent(page_text):
            continue

        if not title or len(title) < 8:
            title = page_text[:200]

        if is_generic_bad_title(title):
            continue

        results.append(
            {
                "source": source["name"],
                "title": title if title else "Procedura di gara",
                "link": link,
                "text": page_text,
            }
        )

    return results


def main():
    debug = []
    audit_discarded = []

    try:
        manual_sources = normalize_sources(load_json("sources.json", []))
        traspare_sources = normalize_sources(load_json("traspare_valid_sources.json", []))

        sources = manual_sources + traspare_sources

        unique_sources = []
        seen_urls = set()

        for s in sources:
            url = s["url"]

            if url in seen_urls:
                continue

            seen_urls.add(url)
            unique_sources.append(s)

        sources = unique_sources

        seen = normalize_seen(load_json("seen.json", []))
        health = normalize_health(load_json("source_health.json", {}))

        debug.append(f"fonti caricate: {len(sources)}")
        debug.append(f"seen caricati: {len(seen)}")

        all_results = []

        for source in sources:
            source_type = source["type"]
            source_name = source["name"]

            if source_type == "html_list":
                results = parse_html_list(source)
            elif source_type == "traspare":
                results = parse_traspare(source)
            else:
                results = []

            debug.append(f"{source_name}: risultati parser={len(results)}")

            if source_name not in health:
                health[source_name] = {
                    "runs": 0,
                    "results": 0,
                    "relevant": 0,
                    "zero_runs": 0,
                }

            health[source_name]["runs"] += 1
            health[source_name]["results"] += len(results)

            if len(results) == 0:
                health[source_name]["zero_runs"] += 1
            else:
                health[source_name]["zero_runs"] = 0

            all_results.extend(results)

        debug.append(f"totale risultati grezzi: {len(all_results)}")

        new_items = []
        seen_keys_run = set()

        discarded_low_score = 0
        discarded_seen = 0
        discarded_same_run = 0

        for item in all_results:
            score, title_score, text_score, hits = compute_score(item)

            item["score"] = score
            item["title_score"] = title_score
            item["text_score"] = text_score
            item["hits"] = hits

            if score < 8:
                discarded_low_score += 1

                if item["source"] == AUDIT_SOURCE and len(audit_discarded) < AUDIT_LIMIT:
                    audit_discarded.append(
                        {
                            "title": item["title"],
                            "link": item["link"],
                            "score": score,
                            "title_score": title_score,
                            "text_score": text_score,
                            "hits": hits,
                        }
                    )
                continue

            key = item.get("seen_key", item["link"])

            if key in seen_keys_run:
                discarded_same_run += 1
                continue

            if key in seen:
                discarded_seen += 1
                continue

            new_items.append(item)
            seen.append(key)
            seen_keys_run.add(key)

            source_name = item["source"]
            if source_name in health:
                health[source_name]["relevant"] += 1

        debug.append(f"scartati per score basso: {discarded_low_score}")
        debug.append(f"scartati perché già visti: {discarded_seen}")
        debug.append(f"scartati duplicati nello stesso run: {discarded_same_run}")
        debug.append(f"nuovi risultati dopo deduplica: {len(new_items)}")

        save_json("seen.json", seen)
        save_json("source_health.json", health)

        debug.append("seen.json salvato")
        debug.append("source_health.json salvato")
        debug.append("")
        debug.append("STATISTICHE FONTI")

        for name, data in health.items():
            line = (
                f"{name} | "
                f"runs={data.get('runs', 0)} "
                f"results={data.get('results', 0)} "
                f"relevant={data.get('relevant', 0)} "
                f"zero_runs={data.get('zero_runs', 0)}"
            )
            debug.append(line)

        if not new_items:
            subject = "Monitor bandi – debug"
            body = "Nessun nuovo bando trovato.\n\n"
        else:
            subject = f"Monitor bandi – {len(new_items)} nuovi risultati"
            body = "Monitor bandi – nuovi risultati\n\n"

            for item in new_items:
                body += (
                    f"{item['source']}\n"
                    f"{item['title']}\n"
                    f"title_score: {item['title_score']}\n"
                    f"text_score: {item['text_score']}\n"
                    f"score finale: {item['score']}\n"
                    f"match: {', '.join(item['hits'])}\n"
                    f"{item['link']}\n\n"
                )

        if audit_discarded:
            body += f"\nAUDIT RISULTATI SCARTATI – {AUDIT_SOURCE}\n\n"

            for item in audit_discarded:
                body += (
                    f"{item['title']}\n"
                    f"title_score: {item['title_score']}\n"
                    f"text_score: {item['text_score']}\n"
                    f"score finale: {item['score']}\n"
                    f"match: {', '.join(item['hits'])}\n"
                    f"{item['link']}\n\n"
                )

        body += "\nDEBUG\n\n" + "\n".join(debug)
        send_email(subject, body)

    except Exception as e:
        subject = "Monitor bandi – errore"
        body = f"Errore nel monitor.\n\nERRORE: {repr(e)}"
        send_email(subject, body)


if __name__ == "__main__":
    main()
