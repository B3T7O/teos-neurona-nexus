#!/usr/bin/env python3
"""Evaluación retrospectiva aislada; no modifica datos ni producción."""

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/bitaxe_samples.jsonl"
PREDS = ROOT / "data/processed/learning_predictions_v2.jsonl"
OUTCOMES = ROOT / "data/processed/learning_outcomes_v2.jsonl"

EVENT_ISO = "2026-10-22T22:35:46.909234+00:00"
EXCLUSION_SECONDS = 15 * 60
THRESHOLDS = (1.5, 2.0, 3.0)


def load_jsonl(path):
    result = []
    if not path.exists():
        raise SystemExit(f"Falta el archivo requerido: {path}")
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    result.append(value)
            except json.JSONDecodeError:
                continue
    return result


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, OverflowError):
        return None


def number(row, *keys):
    for key in keys:
        value = row.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


raw = []
for row in load_jsonl(RAW):
    ts = timestamp(
        row.get("timestamp") or row.get("captured_at") or row.get("datetime")
    )
    actual = number(row, "hashRate", "hashrate", "hashrate_GHs")
    if ts is not None and actual is not None:
        raw.append({
            "time": ts,
            "actual": actual,
            "r1h": number(row, "hashRate_1h", "hashrate_1h_GHs"),
        })

raw.sort(key=lambda row: row["time"])
if not raw:
    raise SystemExit("No hay muestras válidas en el histórico.")

# Reconstruir la mediana usando solo lecturas previas no detectadas como picos.
history = []
context = {}
for row in raw:
    previous = history[-10:]
    median = (
        statistics.median(x["actual"] for x in previous)
        if len(previous) >= 5 else None
    )
    actual, r1h = row["actual"], row["r1h"]
    spike = (
        median is not None and r1h is not None
        and median > 0 and r1h > 0
        and actual > 3 * median
        and actual > 3 * r1h
    )
    context[row["time"]] = {
        "median": median,
        "r1h": r1h,
        "spike": spike,
    }
    if not spike:
        history.append(row)

times = [row["time"] for row in raw]
predictions = {
    row.get("prediction_id"): row
    for row in load_jsonl(PREDS)
    if row.get("prediction_id")
}
outcomes = load_jsonl(OUTCOMES)
event_time = timestamp(EVENT_ISO)

pairs = []
for outcome in outcomes:
    pred = predictions.get(outcome.get("prediction_id"))
    if not pred or pred.get("method") != "referencia_1h":
        continue

    source_time = timestamp(pred.get("source_timestamp"))
    actual = number(outcome, "actual_hashRate_GHs")
    original = number(pred, "predicted_hashRate_GHs")
    if source_time is None or actual is None or original is None:
        continue

    nearest = min(times, key=lambda t: abs(t - source_time))
    if abs(nearest - source_time) > 2:
        continue

    info = context[nearest]
    median, reference = info["median"], info["r1h"]
    if median is None or median <= 0 or reference is None:
        continue

    pairs.append({
        "time": source_time,
        "actual": actual,
        "original": original,
        "reference": reference,
        "median": median,
        "near_event": (
            event_time is not None
            and abs(source_time - event_time) <= EXCLUSION_SECONDS
        ),
    })

pairs.sort(key=lambda row: row["time"])
if not pairs:
    raise SystemExit("No se pudieron emparejar predicciones y resultados.")

cut_index = int(len(pairs) * 0.70)
cut_time = pairs[cut_index]["time"]
test = [row for row in pairs if row["time"] >= cut_time]
outside_event = [row for row in test if not row["near_event"]]

print("TEOS NEURONA NEXUS — EVALUADOR AISLADO")
print("Solo lectura: no se modificaron predicciones, resultados ni servicios.")
print(f"Casos emparejados: {len(pairs)}")
print("Inicio de tramo temporal de prueba:",
      datetime.fromtimestamp(cut_time, timezone.utc).isoformat())
print(f"Casos en prueba temporal: {len(test)}")
print(f"Casos fuera de ±15 min del evento: {len(outside_event)}")


def report(label, rows):
    print(f"\n--- {label} | n={len(rows)} ---")
    if not rows:
        print("Muestra vacía.")
        return

    base_errors = [abs(x["actual"] - x["original"]) for x in rows]
    base_mae = statistics.mean(base_errors)
    print(f"Original MAE: {base_mae:.3f} GH/s")

    for factor in THRESHOLDS:
        new_errors = []
        changed = improved = worsened = tied = 0

        for x in rows:
            old_error = abs(x["actual"] - x["original"])
            new_prediction = x["original"]

            if x["reference"] > factor * x["median"]:
                new_prediction = x["median"]
                changed += 1

            new_error = abs(x["actual"] - new_prediction)
            new_errors.append(new_error)

            if new_error < old_error:
                improved += 1
            elif new_error > old_error:
                worsened += 1
            else:
                tied += 1

        mae = statistics.mean(new_errors)
        print(
            f"Umbral {factor:.1f}x | MAE {mae:.3f} GH/s | "
            f"cambio MAE {mae-base_mae:+.3f} | "
            f"sustituciones {changed} | "
            f"mejoran {improved} | empeoran {worsened} | iguales {tied}"
        )


report("PRUEBA TEMPORAL COMPLETA", test)
report("PRUEBA EXCLUYENDO EL ENTORNO DEL PICO", outside_event)

print("\nNOTA: la exclusión del pico no equivale a una validación")
print("independiente. El umbral debe probarse también en datos futuros.")
