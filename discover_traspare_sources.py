import requests
import json
import time

INPUT_FILE = "comuni_sa_av.json"
OUTPUT_FILE = "traspare_valid_sources.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

TIMEOUT = 10


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def slugify(name):
    text = name.lower().strip()

    replacements = {
        "à": "a",
        "è": "e",
        "é": "e",
        "ì": "i",
        "ò": "o",
        "ù": "u",
        "'": "",
        "’": "",
        ".": "",
        ",": "",
        "-": "",
        "/": ""
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = text.replace(" ", "")

    return text


def candidate_slugs(name):
    base = slugify(name)
    candidates = {base}

    # varianti utili per alcuni comuni
    special_cases = {
        "cava de' tirreni": ["cavadetirreni"],
        "mercato san severino": ["mercatosanseverino"],
        "vallo della lucania": ["vallodellalucania"],
        "pontecagnano faiano": ["pontecagnanofaiano"],
        "capaccio paestum": ["capacciopaestum"],
        "nocera inferiore": ["nocerainferiore"],
        "nocera superiore": ["nocerasuperiore"],
        "giffoni valle piana": ["giffonivallepiana"],
        "giffoni sei casali": ["giffoniseicasali"],
        "montecorvino rovella": ["montecorvinorovella"],
        "montecorvino pugliano": ["montecorvinopugliano"],
        "san marzano sul sarno": ["sanmarzanosulsarno"],
        "san valentino torio": ["sanvalentinotorio"],
        "sant'egidio del monte albino": ["santegidiodelmontealbino"],
        "sant'angelo dei lombardi": ["santangelodeilombardi"],
        "santo stefano del sole": ["santostefanodelsole"],
        "prata di principato ultra": ["pratadiprincipatoultra"],
        "san martino valle caudina": ["sanmartinovallecaudina"],
    }

    lower_name = name.lower().strip()
    if lower_name in special_cases:
        for variant in special_cases[lower_name]:
            candidates.add(variant)

    return list(candidates)


def check_traspare(url):
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True
        )

        if r.status_code == 200:
            final_url = r.url.lower()

            # accettiamo se siamo ancora su traspare e su una pagina plausibile
            if "traspare.com" in final_url:
                return True

    except Exception:
        return False

    return False


def main():
    comuni = load_json(INPUT_FILE)

    valid_sources = []
    seen_urls = set()

    for provincia in comuni:
        print(f"\n=== Provincia: {provincia.upper()} ===")

        for comune in comuni[provincia]:
            print(f"Test: {comune}")

            found = False

            for slug in candidate_slugs(comune):
                url = f"https://{slug}.traspare.com/announcements"

                if url in seen_urls:
                    continue

                if check_traspare(url):
                    print(f"   ✔ trovato: {url}")

                    valid_sources.append(
                        {
                            "name": f"Comune di {comune}",
                            "url": url,
                            "type": "traspare"
                        }
                    )

                    seen_urls.add(url)
                    found = True
                    break

            if not found:
                print("   ✘ no")

            time.sleep(1)

    save_json(OUTPUT_FILE, valid_sources)

    print("\nFonti valide trovate:", len(valid_sources))
    print(f"File salvato: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
