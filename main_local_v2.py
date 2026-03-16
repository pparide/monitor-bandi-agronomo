def main():

    debug = []

    try:

        sources = load_json("sources.json", [])
        traspare_sources = load_json("traspare_valid_sources.json", [])

        sources.extend(traspare_sources)

        # deduplica fonti
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

            # inizializza health se non esiste
            if source_name not in health:
                health[source_name] = {
                    "runs": 0,
                    "results": 0,
                    "relevant": 0,
                    "zero_runs": 0
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

        discarded_score = 0
        discarded_seen = 0
        discarded_duplicate = 0

        for item in all_results:

            score, title_score, text_score, hits = compute_score(item)

            item["score"] = score
            item["title_score"] = title_score
            item["text_score"] = text_score
            item["hits"] = sorted(set(hits))

            if score < 15:
                discarded_score += 1
                continue

            key = item.get("seen_key", item["link"])

            if key in seen_keys_run:
                discarded_duplicate += 1
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

        debug.append(f"scartati per score basso: {discarded_score}")
        debug.append(f"scartati perché già visti: {discarded_seen}")
        debug.append(f"scartati duplicati nello stesso run: {discarded_duplicate}")
        debug.append(f"nuovi risultati dopo deduplica: {len(new_items)}")

        save_json("seen.json", seen)
        save_health(health)

        debug.append("seen.json salvato")
        debug.append("source_health.json salvato")

        # -------- REPORT FONTI --------

        debug.append("\nSTATISTICHE FONTI\n")

        for name, data in health.items():

            line = (
                f"{name} | "
                f"runs={data['runs']} "
                f"results={data['results']} "
                f"relevant={data['relevant']} "
                f"zero_runs={data['zero_runs']}"
            )

            if data["zero_runs"] >= 5:
                line += " ⚠️ possibile fonte inutile o parser rotto"

            debug.append(line)

        # -------- EMAIL --------

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

        body = (
            "Errore nel monitor.\n\n"
            "DEBUG\n\n"
            + "\n".join(debug)
            + f"\n\nERRORE: {repr(e)}"
        )

        send_email(subject, body)
