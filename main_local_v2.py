import json
import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

EMAIL_HOST = os.environ["EMAIL_HOST"]
EMAIL_PORT = int(os.environ["EMAIL_PORT"])
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
EMAIL_TO = os.environ["EMAIL_TO"]

HEADERS = {"User-Agent": "Mozilla/5.0"}

# 👇 AUDIT ATTIVO SU MERCATO SAN SEVERINO
AUDIT_SOURCE = "Comune di Mercato San Severino"
AUDIT_LIMIT = 50


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

    return [x.strip() for x in data if isinstance(x, str) and x.strip()]


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
    return re.sub(r"\s+", " ", text)[:6000]


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
        "novità",
        "amministrazione",
        "servizi",
        "notizie"
    ]

    if t.isdigit():
        return True

    return t in bad_titles


def keyword_score(text):
    text = text.lower()

    positive = {
        "agronom": 5,
        "forest": 5,
        "verde": 4,
        "paesagg": 4,
        "giardin": 4,
        "parchi": 4,
        "agricolt": 4,
        "ambient": 4,
        "vinca": 8,
        "valutazione di incidenza": 8,
        "commissione": 5,
        "nomina": 4,
        "esperti": 4,
    }

    negative = {
        "elettorale": -10,
        "tribut": -10,
        "asilo": -8,
        "infanzia": -8,
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
    audit_mode = source["name"] == AUDIT_SOURCE

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(" ", strip=True)

        if not href:
            continue

        link = urljoin(source["url"], href)

        if link in seen_links:
            continue
        seen_links.add(link)

        if is_generic_bad_title(title):
            continue

        text = (title + " " + href).lower()

        if not any(k in text for k in ["bando", "avviso", "incarico", "commissione"]):
            continue

        page_text = get_page_text(link)

        results.append(
            {
                "source": source["name"],
                "title": title if title else "Avviso",
                "link": link,
                "text": page_text,
            }
        )

        if audit_mode and len(results) >= AUDIT_LIMIT:
            break

    return results


def main():
    debug = []
    audit_candidates = []

    try:
        sources = normalize_sources(load_json("sources.json", []))
        seen = normalize_seen(load_json("seen.json", []))
        health = normalize_health(load_json("source_health.json", {}))

        debug.append(f"fonti caricate: {len(sources)}")
        debug.append(f"seen caricati: {len(seen)}")

        all_results = []

        for source in sources:
            results = parse_html_list(source)
            debug.append(f"{source['name']}: risultati parser={len(results)}")
            all_results.extend(results)

        debug.append(f"totale risultati grezzi: {len(all_results)}")

        new_items = []

        for item in all_results:
            score, title_score, text_score, hits = compute_score(item)

            if item["source"] == AUDIT_SOURCE and len(audit_candidates) < AUDIT_LIMIT:
                audit_candidates.append({
                    "title": item["title"],
                    "link": item["link"],
                    "score": score,
                    "hits": hits
                })

            if score < 7:
                continue

            if item["link"] in seen:
                continue

            new_items.append(item)
            seen.append(item["link"])

        save_json("seen.json", seen)

        body = "AUDIT\n\n"
        for a in audit_candidates:
            body += f"{a['title']}\n{a['link']}\nscore: {a['score']}\n\n"

        body += "\nDEBUG\n\n" + "\n".join(debug)

        send_email("AUDIT MERCATO SAN SEVERINO", body)

    except Exception as e:
        send_email("ERRORE", str(e))


if __name__ == "__main__":
    main()
