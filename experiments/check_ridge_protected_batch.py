import json
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path("experiments").resolve()))

import evaluate_ridge_prospective as ev

CUTOFF = ev.parse_timestamp(
    "2026-10-30T22:49:22.416615+00:00"
)

FEATURES = (
    "delta_hashRate",
    "delta_hashRate_10m",
    "delta_hashRate_1h",
)

frozen, snapshot_hash = ev.load_frozen()

prospective = json.loads(ev.OUTPUT.read_text())
previous = json.loads(
    Path("experiments/ridge_protected_prospective_report.json").read_text()
)
protected = json.loads(
    Path("experiments/ridge_protected_predictor_report.json").read_text()
)

for report in (previous, protected):
    if report["snapshot_sha256"] != snapshot_hash:
        raise SystemExit("Fotografía histórica diferente.")

if prospective["integrity"]["snapshot_sha256"] != snapshot_hash:
    raise SystemExit("Evaluación prospectiva diferente.")

if previous["evaluation_end_utc"] != CUTOFF.isoformat():
    raise SystemExit("Punto de corte diferente.")

if previous["validation"]["new_raw_samples"] != 180:
    raise SystemExit("El primer lote no coincide.")

train_x = []

for i in range(2, len(frozen)):
    x = ev.feature_at(frozen[i-1], frozen[i-2])
    baseline = frozen[i-1].get("hashRate_1h")

    if x is not None and ev.valid_number(baseline):
        train_x.append(x)

train_x = np.asarray(train_x, dtype=float)

if len(train_x) != 844:
    raise SystemExit("Entrenamiento histórico diferente.")

saved = protected["protection_rule"]["historical_training_ranges"]

for name in FEATURES:
    values = train_x[:, ev.FEATURES.index(name)]

    if (
        float(values.min()) != saved[name]["minimum"]
        or float(values.max()) != saved[name]["maximum"]
    ):
        raise SystemExit(f"Límite histórico diferente: {name}")

by_time = {}
invalid = 0

with ev.RAW.open(encoding="utf-8") as f:
    for line in f:
        try:
            row = json.loads(line)
            dt = ev.parse_timestamp(row.get("timestamp"))

            if ev.valid_number(row.get("hashRate")):
                row["_dt"] = dt
                by_time[dt] = row

        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            invalid += 1

rows = [by_time[t] for t in sorted(by_time)]

ev.verify_context(
    frozen,
    [r for r in rows if r["_dt"] <= frozen[-1]["_dt"]]
)

timeline = [frozen[-2], frozen[-1]] + [
    r for r in rows if r["_dt"] > frozen[-1]["_dt"]
]

valid = 0
activations = 0
first = None
last = None

for i in range(2, len(timeline)):
    previous_row = timeline[i-1]
    earlier = timeline[i-2]
    target = timeline[i]

    if target["_dt"] <= CUTOFF:
        continue

    x = ev.feature_at(previous_row, earlier)

    if (
        x is None
        or not ev.valid_number(target.get("hashRate"))
        or not ev.valid_number(previous_row.get("hashRate_1h"))
        or (target["_dt"] - previous_row["_dt"]).total_seconds() <= 0
    ):
        continue

    valid += 1
    first = first or target["_dt"]
    last = target["_dt"]

    outside = any(
        x[ev.FEATURES.index(name)] < saved[name]["minimum"]
        or x[ev.FEATURES.index(name)] > saved[name]["maximum"]
        for name in FEATURES
    )

    activations += int(outside)

print("CONTROL DEL SEGUNDO LOTE")
print("Fotografía histórica: verificada")
print("Entrenamiento congelado:", len(train_x))
print("Límites originales: verificados")
print("Predicciones nuevas válidas:", valid)
print("Activaciones de protección:", activations)
print("Primera muestra:", first.isoformat() if first else "N/D")
print("Última muestra:", last.isoformat() if last else "N/D")
print("Líneas RAW inválidas:", invalid)
print("RAW, modelos y Bitaxe: intactos.")
