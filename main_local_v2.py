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

        if len(r.text) < 500:
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

    return soup.get_text(" ", strip=True)[:500]


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
        "ingegneria naturalistica",
        "difesa del suolo",
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
        "elettorale",
        "bonus",
        "asilo",
        "infanzia",
        "tribut",
        "riscossione"
    ]

    if any(k in text for k in excluded_keywords):
        return False

    if any(k in text for k in strong_keywords):
        return True

    if any(k in text for k in technical_keywords) and any(k in text for k in territory_keywords):
        return True

    return False


# -----------------------------
# PARSER HTML
# -----------------------------


def parse_html_list(source):

    soup = get_page(source["url"])

    if not soup:
        return []

    results = []

    for a in soup.find_all("a", href=True):

        href = a["href"]
        title = a.get_text(strip=True)

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

        results.append(
            {
                "source": source["name"],
                "title": title,
                "link": link
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

        page_text = get_text_from_page(link)

        if not title or len(title) < 8:
            title = page_text

        if not is_recent(page_text):
            continue

        results.append(
            {
                "source": source["name"],
                "title": title if title else "Procedura di gara",
                "link": link
            }
        )

    return results


# -----------------------------
# MAIN
# -----------------------------


def main():

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

        all_results = []

        for source in sources:

            source_type = source.get("type", "")

            if source_type == "html_list":
                results = parse_html_list(source)

            elif source_type == "traspare":
                results = parse_traspare(source)

            else:
                results = []

            health[source["name"]] = {
                "last_results": len(results)
            }

            all_results.extend(results)

        new_items = []
        seen_keys_run = set()

        for item in all_results:

            if not is_relevant(item["title"]):
                continue

            key = item.get("seen_key", item["link"])

            if key in seen:
                continue

            if key in seen_keys_run:
                continue

            new_items.append(item)
            seen.append(key)
            seen_keys_run.add(key)

        save_json("seen.json", seen)
        save_health(health)

        if not new_items:
            return

        subject = f"Monitor bandi – {len(new_items)} nuovi risultati"

        body = ""

        for item in new_items:

            body += (
                f"{item['source']}\n"
                f"{item['title']}\n"
                f"{item['link']}\n\n"
            )

        send_email(subject, body)

    except Exception as e:

        subject = "Monitor bandi – errore"
        body = f"Errore monitor:\n\n{repr(e)}"

        send_email(subject, body)


if __name__ == "__main__":
    main()
