import json
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
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


def send_email(subject, body):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())


def get_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception:
        return None


# -----------------------------
# PARSER PDF ARCHIVE
# -----------------------------


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


# -----------------------------
# MAIN
# -----------------------------


def main():
    debug = []

    try:
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
            subject = "Monitor bandi – nessun nuovo bando"
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
