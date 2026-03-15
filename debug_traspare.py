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
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        return str(e)


def extract_links(base_url, soup):
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        title = a.get_text(" ", strip=True)

        if not href:
            continue

        full = urljoin(base_url, href)
        links.append({
            "title": title,
            "href": href,
            "full": full
        })

    return links


def main():
    sources = [
        {
            "name": "Provincia di Salerno",
            "url": "https://provinciasalerno.traspare.com/announcements"
        },
        {
            "name": "Comune di Baronissi",
            "url": "https://baronissi.traspare.com/announcements"
        },
        {
            "name": "Comune di Cava de' Tirreni",
            "url": "https://cavadetirreni.traspare.com/announcements"
        }
    ]

    body = "DEBUG TRASPARE\n\n"

    for source in sources:
        body += f"=== {source['name']} ===\n"
        body += f"URL: {source['url']}\n"

        soup = get_page(source["url"])

        if isinstance(soup, str):
            body += f"ERRORE: {soup}\n\n"
            continue

        links = extract_links(source["url"], soup)

        body += f"LINK TOTALI: {len(links)}\n\n"

        for i, link in enumerate(links[:20], start=1):
            body += (
                f"{i}) TITLE: {link['title']}\n"
                f"   HREF: {link['href']}\n"
                f"   FULL: {link['full']}\n\n"
            )

        body += "\n"

    send_email("DEBUG Traspare", body)


if __name__ == "__main__":
    main()
