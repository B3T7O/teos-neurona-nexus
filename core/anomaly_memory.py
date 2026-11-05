#!/usr/bin/env python3
"""Memoria persistente y append-only de anomalías contextuales TEOS."""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data/processed/anomaly_events.jsonl"
FACTOR = 3.0
WINDOW = 10
DETECTOR_VERSION = "contextual-spike-v1"


def _median(values):
    values = sorted(values)
    n = len(values)
    if n % 2:
        return values[n // 2]
    return (values[n // 2 - 1] + values[n // 2]) / 2


def record_contextual_anomalies(samples):
    """Registra anomalías de forma idempotente; no modifica las muestras."""
    accepted = []
    detected = []

    for sample in sorted(samples, key=lambda s: s["_time"]):
        history = [s["actual"] for s in accepted[-WINDOW:]]
        actual = sample.get("actual")
        ref_1h = sample.get("rate_1h")
        baseline = _median(history) if len(history) >= 5 else None

        is_spike = (
            baseline is not None
            and isinstance(actual, (int, float))
            and isinstance(ref_1h, (int, float))
            and baseline > 0
            and ref_1h > 0
            and actual > FACTOR * baseline
            and actual > FACTOR * ref_1h
        )

        if is_spike:
            timestamp = sample.get("timestamp")
            event_id = hashlib.sha256(
                f"{DETECTOR_VERSION}|{timestamp}".encode()
            ).hexdigest()[:24]
            detected.append({
                "event_id": event_id,
                "event_type": "contextual_hashrate_spike",
                "pattern_key": "hashrate_spike_vs_rolling_median_and_1h",
                "timestamp": timestamp,
                "observed_hashRate_GHs": actual,
                "baseline_median_GHs": baseline,
                "reference_1h_GHs": ref_1h,
                "ratio_to_baseline": actual / baseline,
                "ratio_to_reference_1h": actual / ref_1h,
                "detector_version": DETECTOR_VERSION,
                "status": "unverified",
                "diagnosis_code": None,
                "diagnosis_note": (
                    "Pico contextual detectado; causa aún no verificada."
                ),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            })
        else:
            accepted.append(sample)

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    known_ids = set()
    if LEDGER.exists():
        with LEDGER.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    if row.get("event_id"):
                        known_ids.add(row["event_id"])
                except json.JSONDecodeError:
                    continue

    new_events = [e for e in detected if e["event_id"] not in known_ids]

    # Relaciona cada evento nuevo con episodios previos del mismo patrón.
    prior_events = []
    if LEDGER.exists():
        with LEDGER.open(encoding="utf-8") as f:
            for line in f:
                try:
                    prior_events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    with LEDGER.open("a", encoding="utf-8") as f:
        for event in new_events:
            related = [
                old["event_id"] for old in prior_events
                if old.get("pattern_key") == event["pattern_key"]
                and old.get("event_id")
            ]
            event["related_event_ids"] = related[-20:]
            event["recurrence_count_before_this_event"] = len(related)
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            prior_events.append(event)

    print(
        "Memoria de anomalías:",
        len(detected), "detectadas;",
        len(new_events), "eventos nuevos registrados."
    )
    return new_events
