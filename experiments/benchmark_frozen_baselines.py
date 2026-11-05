import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean

ROOT = Path(".")
SNAPSHOT = ROOT / "experiments/frozen_bitaxe_samples.jsonl"
MANIFEST = ROOT / "experiments/frozen_evaluation_manifest.json"
OUTPUT = ROOT / "experiments/frozen_baseline_benchmark.json"

if OUTPUT.exists():
    raise SystemExit(
        f"Ya existe {OUTPUT}; no se sobrescribió."
    )

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
raw = SNAPSHOT.read_bytes()
actual_hash = hashlib.sha256(raw).hexdigest()

if actual_hash != manifest["sha256"]:
    raise SystemExit(
        "ERROR: el SHA-256 no coincide. "
        "La fotografía podría haberse alterado."
    )

rows = []
invalid = 0

for line in raw.splitlines():
    try:
        row = json.loads(line)
        ts = datetime.fromisoformat(
            row["timestamp"].replace("Z", "+00:00")
        )
        hr = row.get("hashRate")
        if (
            isinstance(hr, bool)
            or not isinstance(hr, (int, float))
            or not math.isfinite(hr)
            or hr < 0
        ):
            invalid += 1
            continue
        row["_ts"] = ts
        row["_hr"] = float(hr)
        rows.append(row)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        invalid += 1

rows.sort(key=lambda r: r["_ts"])

# Deduplicación temporal determinista.
unique = {}
for row in rows:
    unique[row["_ts"]] = row
rows = [unique[t] for t in sorted(unique)]

if len(rows) < 30:
    raise SystemExit("No hay suficientes registros válidos.")

split = int(len(rows) * 0.70)
actual = []
preds = {
    "last_hashRate": [],
    "mean_previous_5": [],
    "previous_hashRate_10m": [],
    "previous_hashRate_1h": [],
}

for i in range(max(split, 5), len(rows)):
    previous = rows[i - 1]
    history = [rows[j]["_hr"] for j in range(i - 5, i)]
    candidates = {
        "last_hashRate": previous["_hr"],
        "mean_previous_5": mean(history),
        "previous_hashRate_10m": previous.get("hashRate_10m"),
        "previous_hashRate_1h": previous.get("hashRate_1h"),
    }

    if any(
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
        or v < 0
        for v in candidates.values()
    ):
        continue

    actual.append(rows[i]["_hr"])
    for name, value in candidates.items():
        preds[name].append(float(value))

def metrics(y, p):
    errors = [a - b for a, b in zip(y, p)]
    return {
        "n": len(y),
        "mae_ghs": mean(abs(e) for e in errors),
        "rmse_ghs": math.sqrt(mean(e * e for e in errors)),
        "mean_absolute_relative_error_pct": mean(
            abs(a - b) / abs(a) * 100
            for a, b in zip(y, p) if a != 0
        ),
    }

results = {
    name: metrics(actual, pred)
    for name, pred in preds.items()
}

best = min(results, key=lambda name: results[name]["mae_ghs"])

report = {
    "snapshot_sha256": actual_hash,
    "snapshot": str(SNAPSHOT),
    "split_fraction": 0.70,
    "prediction_target": "next sample hashRate",
    "test_samples_common": len(actual),
    "invalid_rows_after_full_validation": invalid,
    "results": results,
    "best_baseline_by_mae": best,
    "training_performed": False,
    "notes": [
        "All methods use the same chronological test targets.",
        "Predictors use only the previous sample and older observations.",
        "This benchmark does not train a model.",
        "This benchmark does not establish Bitcoin block prediction ability."
    ]
}

OUTPUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print("TEOS NEURONA — REFERENCIAS CONGELADAS")
print("SHA-256 verificado:", actual_hash)
print("Muestras de prueba comunes:", len(actual))
for name, result in sorted(
    results.items(), key=lambda item: item[1]["mae_ghs"]
):
    print(
        f"{name}: MAE={result['mae_ghs']:.4f} GH/s | "
        f"RMSE={result['rmse_ghs']:.4f} GH/s | "
        f"error relativo={result['mean_absolute_relative_error_pct']:.4f}%"
    )
print("Mejor referencia:", best)
print("Informe:", OUTPUT)
print("Sin entrenamiento ni cambios en datos originales.")
