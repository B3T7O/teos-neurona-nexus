#!/usr/bin/env python3
"""Detector independiente de episodios de hashrate para TEOS NEURONA NEXUS."""

import json
from datetime import datetime
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = ROOT / "data/raw/bitaxe_samples.marked.jsonl"
REPORT_FILE = ROOT / "data/processed/episodes_report.json"

THRESHOLD_PCT = 3.0
BASELINE_SAMPLES = 5
GROUP_GAP_SECONDS = 300
POST_SAMPLES = 5


def parse_timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def read_samples():
    if not RAW_FILE.exists():
        raise FileNotFoundError(f"No existe el archivo: {RAW_FILE}")

    rows = []
    damaged = 0

    with RAW_FILE.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                timestamp = parse_timestamp(row["timestamp"])
                hashrate = float(row["hashRate"])
                if timestamp.tzinfo is None:
                    damaged += 1
                    continue
                if hashrate <= 0:
                    damaged += 1
                    continue
                rows.append({
                    "timestamp": timestamp,
                    "hashRate": hashrate,
                    "raw": row,
                })
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                damaged += 1

    rows.sort(key=lambda x: x["timestamp"])
    return rows, damaged


def number(row, key):
    try:
        value = float(row[key])
        return value if value > 0 else None
    except (KeyError, TypeError, ValueError):
        return None


def pct_change(value, baseline):
    if value is None or baseline is None or baseline == 0:
        return None
    return (value / baseline - 1) * 100


def detect_episodes(rows):
    hits = []

    for i in range(BASELINE_SAMPLES, len(rows)):
        baseline = mean(
            x["hashRate"]
            for x in rows[i - BASELINE_SAMPLES:i]
        )
        current = rows[i]["hashRate"]
        change = pct_change(current, baseline)

        if change is not None and change > THRESHOLD_PCT:
            hits.append({
                "index": i,
                "baseline": baseline,
                "change_pct": change,
            })

    # Agrupa lecturas que superan el umbral y están separadas
    # por un máximo de cinco minutos.
    groups = []

    for hit in hits:
        timestamp = rows[hit["index"]]["timestamp"]

        if (
            not groups
            or (
                timestamp - rows[groups[-1][-1]["index"]]["timestamp"]
            ).total_seconds() > GROUP_GAP_SECONDS
        ):
            groups.append([])

        groups[-1].append(hit)

    episodes = []

    for episode_number, group in enumerate(groups, start=1):
        peak_hit = max(
            group,
            key=lambda h: rows[h["index"]]["hashRate"]
        )
        i = peak_hit["index"]
        peak_row = rows[i]
        peak = peak_row["hashRate"]

        previous = rows[max(0, i - BASELINE_SAMPLES):i]
        previous_baseline = (
            mean(x["hashRate"] for x in previous)
            if len(previous) == BASELINE_SAMPLES
            else None
        )

        post = rows[i + 1:i + 1 + POST_SAMPLES]
        post_mean = (
            mean(x["hashRate"] for x in post)
            if len(post) == POST_SAMPLES
            else None
        )
        post_change = pct_change(post_mean, previous_baseline)

        # Nivel 1: pico instantáneo confirmado por la regla inicial.
        level = 1
        classification = "pico_instantaneo"

        # Nivel 2: la ventana de 1 minuto supera su propia referencia
        # de cinco muestras anteriores en más del 3 %.
        window_values = [
            number(x["raw"], "hashRate_1m") for x in rows
        ]
        window_baseline = None
        window_peak = number(peak_row["raw"], "hashRate_1m")
        if i >= BASELINE_SAMPLES and window_peak is not None:
            prior_window = window_values[i - BASELINE_SAMPLES:i]
            if all(v is not None for v in prior_window):
                window_baseline = mean(prior_window)

        window_change = pct_change(window_peak, window_baseline)
        if window_change is not None and window_change > THRESHOLD_PCT:
            level = 2
            classification = "senal_acompanada_1m"

        # Nivel 3: requiere las cinco muestras posteriores y un
        # promedio posterior >3 % sobre la referencia previa.
        if (
            post_change is not None
            and post_change > THRESHOLD_PCT
        ):
            level = 3
            classification = "persistencia_provisional"

        def rounded(value):
            return round(value, 3) if value is not None else None

        episodes.append({
            "episode": episode_number,
            "classification": classification,
            "level": level,
            "start": rows[group[0]["index"]]["timestamp"].isoformat(),
            "end": rows[group[-1]["index"]]["timestamp"].isoformat(),
            "threshold_readings": len(group),
            "peak_timestamp": peak_row["timestamp"].isoformat(),
            "peak_hashrate_GHs": rounded(peak),
            "baseline_hashrate_GHs": rounded(previous_baseline),
            "peak_change_pct": rounded(
                pct_change(peak, previous_baseline)
            ),
            "hashRate_1m_at_peak": rounded(window_peak),
            "hashRate_1m_baseline": rounded(window_baseline),
            "hashRate_1m_change_pct": rounded(window_change),
            "post_samples_available": len(post),
            "post_mean_hashrate_GHs": rounded(post_mean),
            "post_change_pct": rounded(post_change),
            "persistence_evaluable": len(post) == POST_SAMPLES,
        })

    return hits, episodes


def main():
    rows, damaged = read_samples()
    if not rows:
        raise SystemExit("No hay muestras válidas para analizar.")

    hits, episodes = detect_episodes(rows)

    report = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "input_file": str(RAW_FILE.relative_to(ROOT)),
        "sample_count": len(rows),
        "damaged_lines_skipped": damaged,
        "threshold_pct": THRESHOLD_PCT,
        "baseline_samples": BASELINE_SAMPLES,
        "group_gap_seconds": GROUP_GAP_SECONDS,
        "post_samples_required": POST_SAMPLES,
        "hit_count": len(hits),
        "episode_count": len(episodes),
        "episodes": episodes,
        "note": (
            "Exploratorio; no predice bloques. Persistencia solo se evalúa "
            "cuando hay cinco muestras posteriores al pico."
        ),
    }

    # No sobrescribir silenciosamente un informe anterior.
    if REPORT_FILE.exists():
        backup = REPORT_FILE.with_name(
            f"episodes_report.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        REPORT_FILE.replace(backup)
        print(f"Informe anterior respaldado en: {backup.relative_to(ROOT)}")

    REPORT_FILE.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA — DETECTOR DE EPISODIOS")
    print(f"Muestras válidas: {len(rows)}")
    print(f"Líneas dañadas omitidas: {damaged}")
    print(f"Lecturas sobre umbral: {len(hits)}")
    print(f"Episodios agrupados: {len(episodes)}")

    for ep in episodes:
        print(
            f"\nEpisodio {ep['episode']} | Nivel {ep['level']} "
            f"| {ep['classification']}"
        )
        print(f"  Pico: {ep['peak_hashrate_GHs']} GH/s")
        print(f"  Cambio sobre referencia: {ep['peak_change_pct']}%")
        print(f"  Cambio ventana 1m: {ep['hashRate_1m_change_pct']}%")
        print(
            f"  Muestras posteriores: {ep['post_samples_available']}/"
            f"{POST_SAMPLES}"
        )
        print(f"  Cambio posterior: {ep['post_change_pct']}%")

    print(f"\nInforme guardado en: {REPORT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
