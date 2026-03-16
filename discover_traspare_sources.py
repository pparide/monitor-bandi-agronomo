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
        with open(path, "r") as f:
            return json.load(f)
    except:
        return {}


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def slugify(name):
    text = name.lower()

    replacements = {
        "à": "a", "è": "e", "é": "e", "ì": "i", "ò": "o", "ù": "u",
        "'": "", "’": "", ".": "", ",": "", "-": "", "/": ""
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = text.replace(" ", "")

    return text


def check_traspare(url):

    try:

        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)

        if r.status_code != 200:
            return False

        text = r.text.lower()

        if "traspare" in text and "announcements" in text:
            return True

    except:
        return False

    return False


def main():

    comuni = load_json(INPUT_FILE)

    valid_sources = []

    for provincia in comuni:

        for comune in comuni[provincia]:

            slug = slugify(comune)

            url = f"https://{slug}.traspare.com/announcements"

            print(f"Test: {comune}")

            if check_traspare(url):

                print("   ✔ trovato")

                valid_sources.append(
                    {
                        "name": f"Comune di {comune}",
                        "url": url,
                        "type": "traspare"
                    }
                )

            else:

                print("   ✘ no")

            time.sleep(1)

    save_json(OUTPUT_FILE, valid_sources)

    print("\nFonti valide trovate:", len(valid_sources))


if __name__ == "__main__":
    main()
