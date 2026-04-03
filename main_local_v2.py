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


def clean_text(text, max_len=6000):
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def extract_meaningful_text_from_soup(soup):
    if not soup:
        return ""

    soup = BeautifulSoup(str(soup), "html.parser")

    for tag in soup.find_all(["script", "style", "noscript", "nav", "footer", "aside", "header", "form"]):
        tag.decompose()

    priority_selectors = [
        "article",
        "main",
        '[role="main"]',
        ".entry-content",
        ".post-content",
        ".news-content",
        ".article-content",
        ".content",
        ".content-body",
        ".field-content",
        ".node__content",
        ".page-content",
        ".detail-content",
        "#content",
        "#main",
        ".box-content",
        ".contenuto",
        ".dettaglio",
        ".scheda",
        "table"
    ]

    chunks = []

    for selector in priority_selectors:
        for el in soup.select(selector):
            txt = clean_text(el.get_text(" ", strip=True), max_len=5000)
            if len(txt) >= 80:
                chunks.append(txt)

    if chunks:
        merged = " ".join(chunks)
        return clean_text(merged, max_len=6000)

    body = soup.body if soup.body else soup
    txt = clean_text(body.get_text(" ", strip=True), max_len=6000)
    return txt


def get_page_text(url):
    soup = get_page(url)
    if not soup:
        return ""
    return extract_meaningful_text_from_soup(soup)


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


def extract_salerno_portal_title_and_text(url):
    soup = get_page(url)
    if not soup:
        return "", ""

    label_candidates = [
        "oggetto",
        "titolo",
        "descrizione",
        "oggetto della procedura",
        "denominazione",
        "procedura",
        "cig",
        "cup"
    ]

    for tr in soup.find_all("tr"):
        headers = tr.find_all(["th", "td"])
        if len(headers) < 2:
            continue

        left = headers[0].get_text(" ", strip=True).lower()
        right = headers[1].get_text(" ", strip=True)

        if any(label in left for label in label_candidates) and right:
            if len(right) > 15:
                page_text = extract_meaningful_text_from_soup(soup)
                return right, page_text

    dts = soup.find_all("dt")
    for dt in dts:
        label = dt.get_text(" ", strip=True).lower()
        dd = dt.find_next_sibling("dd")
        if dd and any(l in label for l in label_candidates):
            value = dd.get_text(" ", strip=True)
            if len(value) > 15:
                page_text = extract_meaningful_text_from_soup(soup)
                return value, page_text

    page_text = extract_meaningful_text_from_soup(soup)
    patterns = [
        r"Oggetto\s*[:\-]\s*(.+?)(?:CIG|CUP|Importo|Scadenza|$)",
        r"Titolo\s*[:\-]\s*(.+?)(?:CIG|CUP|Importo|Scadenza|$)",
        r"Descrizione\s*[:\-]\s*(.+?)(?:CIG|CUP|Importo|Scadenza|$)",
        r"Denominazione\s*[:\-]\s*(.+?)(?:CIG|CUP|Importo|Scadenza|$)"
    ]

    for pattern in patterns:
        m = re.search(pattern, page_text, flags=re.IGNORECASE | re.DOTALL)
        if m:
            title = clean_text(m.group(1), max_len=300)
            if len(title) > 15:
                return title, page_text

    best_title = get_best_title_from_page(url)
    return best_title, page_text


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
        "novità",
        "amministrazione",
        "vivere il comune",
        "tutti gli argomenti",
        "tutti gli eventi",
        "avvisi",
        "comunicati",
        "notizie",
        "servizi",
        "dettaglio",
        "apri",
        "visualizza",
        "visualizza scheda",
        "grafica",
        "testo",
        "alto contrasto",
        "a",
        "sezione data e ora ufficiale:"
    ]

    if t.isdigit():
        return True

    return t in bad_titles


def keyword_score(text):
    text = text.lower()

    positive = {
        "avviso pubblico": 2,
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
        "nomina componenti": 5
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
        "strength": -8,
        "rifiuti": -6,
        "igiene urbana": -6,
        "cultural heritage": -6,
        "europrogettazione": -6,
        "beni culturali": -4,
        "lighting design": -6,
        "lightning design": -6,
        "alloggi erp": -10,
        "edilizia residenziale pubblica": -10,
        "emergenza abitativa": -10,
        "inquilini morosi": -10
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


def same_domain(base_url, link):
    try:
        return urlparse(base_url).netloc == urlparse(link).netloc
    except Exception:
        return False


def is_listing_page(link):
    parsed = urlparse(link)
    path = parsed.path.lower()
    query = parse_qs(parsed.query)

    if "paged" in query:
        return True

    if re.search(r"/page/\d+/?$", path):
        return True

    listing_paths = [
        "/notizie/avvisi",
        "/notizie/comunicati",
        "/it/news",
        "/news",
        "/avvisi",
        "/bandi",
    ]

    return any(path.rstrip("/").endswith(lp) for lp in listing_paths)


def path_looks_like_detail(link):
    parsed = urlparse(link)
    path = parsed.path.lower()
    query = parse_qs(parsed.query)

    if "paged" in query:
        return False

    good = [
        "/novita/",
        "/news/",
        "/notizie/",
        "/avviso/",
        "/bando/",
        "/bandi/",
        "/albo/",
        "/amministrazione-trasparente/",
    ]

    bad = [
        "/amministrazione/",
        "/servizi-categoria/",
        "/argomento/",
        "/servizi/",
        "/vivere-il-comune/",
        "/domande-frequenti/",
        "/notizie/page/",
        "/notizie/avvisi",
        "/notizie/comunicati",
    ]

    if any(b in path for b in bad):
        return False

    return any(g in path for g in good)


def extract_detail_links_from_listing(listing_url, base_source_url, max_pages=4):
    queue = [listing_url]
    visited_listings = set()
    found = []
    seen_details = set()

    anchor_keywords = [
        "bando",
        "gara",
        "avviso",
        "manifestazione",
        "incarico",
        "affidamento",
        "vinca",
        "valutazione di incidenza",
        "paesaggio",
        "paesaggistica",
        "commissione",
        "nomina",
        "esperti",
    ]

    while queue and len(visited_listings) < max_pages:
        current = queue.pop(0)
        if current in visited_listings:
            continue
        visited_listings.add(current)

        soup = get_page(current)
        if not soup:
            continue

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            raw_title = a.get_text(" ", strip=True)

            if not href:
                continue
            if href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:"):
                continue

            link = urljoin(current, href)

            if not same_domain(base_source_url, link):
                continue

            if is_listing_page(link):
                if link not in visited_listings and link not in queue:
                    queue.append(link)
                continue

            if is_generic_bad_title(raw_title):
                continue

            probe_text = (raw_title + " " + href).lower()

            if not path_looks_like_detail(link) and not any(k in probe_text for k in anchor_keywords):
                continue

            if link in seen_details:
                continue
            seen_details.add(link)
            found.append((link, raw_title))

    return found


def extract_card_links_from_homepage(home_url):
    soup = get_page(home_url)
    if not soup:
        return []

    found = []
    seen = set()

    strong_keywords = [
        "vinca",
        "valutazione di incidenza",
        "commissione locale per il paesaggio",
        "commissione paesaggio",
        "paesaggistica",
        "nomina componenti",
        "commissione esperti",
    ]

    text_nodes = soup.find_all(["h2", "h3", "h4", "p", "span", "strong", "a"])
    for node in text_nodes:
        text = node.get_text(" ", strip=True)
        if not text:
            continue

        low = text.lower()
        if not any(k in low for k in strong_keywords):
            continue

        parent = node
        chosen_link = None
        chosen_title = text

        for _ in range(6):
            if parent is None:
                break

            links = parent.find_all("a", href=True)
            for a in links:
                href = a["href"].strip()
                if not href:
                    continue
                if href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:"):
                    continue

                link = urljoin(home_url, href)

                if not same_domain(home_url, link):
                    continue
                if is_listing_page(link):
                    continue

                path = urlparse(link).path.lower()
                if "/novita/" not in path and "/notizie/" not in path:
                    continue

                chosen_link = link
                anchor_text = a.get_text(" ", strip=True)
                if anchor_text and anchor_text.lower() not in ["vai alla pagina", "leggi tutto"]:
                    chosen_title = anchor_text
                break

            if chosen_link:
                break

            parent = parent.parent

        if chosen_link and chosen_link not in seen:
            seen.add(chosen_link)
            found.append((chosen_link, chosen_title))

    return found


def parse_html_list(source):
    soup = get_page(source["url"])
    if not soup:
        return []

    results = []
    seen_links = set()
    audit_mode = source["name"] == AUDIT_SOURCE

    anchor_keywords = [
        "bando",
        "gara",
        "avviso",
        "manifestazione",
        "incarico",
        "affidamento",
        "vinca",
        "valutazione di incidenza",
        "paesaggio",
        "paesaggistica",
        "commissione",
        "nomina",
        "esperti",
    ]

    candidate_links = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        raw_title = a.get_text(" ", strip=True)

        if not href:
            continue
        if href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:"):
            continue

        link = urljoin(source["url"], href)

        if link in seen_links:
            continue
        seen_links.add(link)

        if not same_domain(source["url"], link):
            if "unisa.it" not in link.lower():
                continue

        if is_generic_bad_title(raw_title):
            continue

        probe_text = (raw_title + " " + href).lower()

        candidate = False
        if any(k in probe_text for k in anchor_keywords):
            candidate = True
        if path_looks_like_detail(link):
            candidate = True
        if is_listing_page(link):
            candidate = True

        if not candidate:
            continue

        candidate_links.append((link, raw_title))

    if source["name"] == "Comune di San Cipriano Picentino Home":
        for link, title in extract_card_links_from_homepage(source["url"]):
            if link not in {x[0] for x in candidate_links}:
                candidate_links.append((link, title))

    expanded_links = []
    seen_expanded = set()

    for link, raw_title in candidate_links:
        if is_listing_page(link):
            for detail_link, detail_title in extract_detail_links_from_listing(link, source["url"]):
                if detail_link not in seen_expanded:
                    expanded_links.append((detail_link, detail_title))
                    seen_expanded.add(detail_link)
        else:
            if link not in seen_expanded:
                expanded_links.append((link, raw_title))
                seen_expanded.add(link)

    for link, raw_title in expanded_links:
        if "unisa.it" in source["url"].lower() or "università di salerno" in source["name"].lower():
            if link.lower().endswith(".pdf"):
                continue
            if "bando=" not in link and "anno=" not in link:
                continue

        page_text = get_page_text(link)
        best_title = raw_title if raw_title else get_best_title_from_page(link)
        page_probe = (best_title + " " + page_text[:3000]).lower()

        if not any(k in page_probe for k in anchor_keywords):
            continue

        results.append(
            {
                "source": source["name"],
                "title": best_title if best_title else "Avviso",
                "link": link,
                "text": page_text,
            }
        )

        if audit_mode and len(results) >= AUDIT_LIMIT:
            break

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


def parse_portale_appalti(source):
    soup = get_page(source["url"])
    if not soup:
        return []

    results = []
    seen_links = set()

    strict_bad_titles = {
        "vai alla pagina di aiuto alla navigazione",
        "passa al testo con caratteri di dimensione standard",
        "passa al testo con caratteri di dimensione grande",
        "passa al testo con caratteri di dimensione molto grande",
        "passa alla visualizzazione grafica",
        "passa alla visualizzazione solo testo",
        "passa alla visualizzazione in alto contrasto e solo testo",
        "grafica",
        "testo",
        "alto contrasto",
        "a",
        "istruzioni e manuali",
        "assistenza operatori economici",
        "news",
        "accessibilità",
        "credits",
        "cookies",
        "gare e procedure",
        "avvisi pubblici",
        "avvisi di aggiudicazione, esiti e affidamenti",
        "bandi e avvisi d'iscrizione",
        "bandi e avvisi d'iscrizione archiviati",
        "esiti affidamenti",
        "riepilogo contratti - link bdncp",
        "prospetti annuali (art. 1 c. 32 l.190 del 6/11/2012)",
        "delibere a contrarre o atto equivalente",
        "varianti in corso d'opera",
        "avvisi di avvio consultazione",
        "avvisi, comunicazioni e atti di carattere generale"
    }

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        raw_title = a.get_text(" ", strip=True)

        if not href:
            continue
        if href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:"):
            continue

        title_low = raw_title.strip().lower()
        link = urljoin(source["url"], href)
        link_low = link.lower()

        if link in seen_links:
            continue
        seen_links.add(link)

        if title_low in strict_bad_titles:
            continue

        is_real_detail = "view.action" in link_low and "codice=" in link_low

        if not is_real_detail:
            continue

        salerno_title, page_text = extract_salerno_portal_title_and_text(link)
        final_title = salerno_title if salerno_title else raw_title if raw_title else "Procedura di gara"

        results.append(
            {
                "source": source["name"],
                "title": final_title,
                "link": link,
                "text": page_text,
            }
        )

        if source["name"] == AUDIT_SOURCE and len(results) >= AUDIT_LIMIT:
            break

    return results


def main():
    debug = []
    audit_candidates = []

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
            elif source_type == "portale_appalti":
                results = parse_portale_appalti(source)
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

            if item["source"] == AUDIT_SOURCE and len(audit_candidates) < AUDIT_LIMIT:
                reason = "TENUTO"
                if score < 7:
                    reason = "SCARTATO_PER_SCORE"
                else:
                    key = item.get("seen_key", item["link"])
                    if key in seen_keys_run:
                        reason = "SCARTATO_DUPLICATO_RUN"
                    elif key in seen:
                        reason = "SCARTATO_GIA_VISTO"

                audit_candidates.append(
                    {
                        "title": item["title"],
                        "link": item["link"],
                        "score": score,
                        "title_score": title_score,
                        "text_score": text_score,
                        "hits": hits,
                        "reason": reason,
                    }
                )

            if score < 7:
                discarded_low_score += 1
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

        if audit_candidates:
            body += f"\nAUDIT CANDIDATI – {AUDIT_SOURCE}\n\n"

            for item in audit_candidates:
                body += (
                    f"{item['title']}\n"
                    f"motivo: {item['reason']}\n"
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
