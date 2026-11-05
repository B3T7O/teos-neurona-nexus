import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean

ROOT = Path(".")
SOURCE = ROOT / "data/raw/bitaxe_samples.jsonl"
REPORT = ROOT / "experiments/hashrate_window_comparison.json"
WINDOW = 5


def parse_time(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt
    except (AttributeError, TypeError, ValueError):
        return None


rows = []
invalid = 0

with SOURCE.open(encoding="utf-8") as f:
    for line in f:
        try:
            row = json.loads(line)
            ts = parse_time(row.get("timestamp"))
            hr = row.get("hashRate")
            if (
                ts is None
                or isinstance(hr, bool)
                or not isinstance(hr, (int, float))
                or not math.isfinite(hr)
                or hr < 0
            ):
                invalid += 1
                continue
            row["_time"] = ts
            row["_hr"] = float(hr)
            rows.append(row)
        except (json.JSONDecodeError, TypeError):
            invalid += 1

rows.sort(key=lambda r: r["_time"])

unique = {}
for row in rows:
    unique[row["_time"]] = row
rows = [unique[t] for t in sorted(unique)]

if len(rows) < 30:
    raise SystemExit("No hay suficientes muestras válidas.")

split = int(len(rows) * 0.70)
predictions = {
    "Último hashRate": [],
    "Media de cinco hashRate": [],
    "hashRate_10m previo": [],
    "hashRate_1h previo": [],
}
actual = []

for i in range(max(split, WINDOW), len(rows)):
    previous = rows[i - 1]
    history = [rows[j]["_hr"] for j in range(i - WINDOW, i)]

    candidates = {
        "Último hashRate": previous["_hr"],
        "Media de cinco hashRate": mean(history),
        "hashRate_10m previo": previous.get("hashRate_10m"),
        "hashRate_1h previo": previous.get("hashRate_1h"),
    }

    # Comparar exactamente los mismos instantes para todos los métodos.
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
        predictions[name].append(float(value))

def metrics(y, p):
    errors = [a - b for a, b in zip(y, p)]
    return {
        "n": len(y),
        "mae_ghs": mean(abs(e) for e in errors),
        "rmse_ghs": math.sqrt(mean(e * e for e in errors)),
        "mean_absolute_relative_error_pct": mean(
            abs(a - b) / abs(a) * 100
            for a, b in zip(y, p) if a != 0
        ) if any(a != 0 for a in y) else None,
    }

results = {
    name: metrics(actual, pred)
    for name, pred in predictions.items()
}

report = {
    "title": "TEOS — Comparación de referencias de hashrate",
    "source": str(SOURCE),
    "read_only": True,
    "valid_unique_samples": len(rows),
    "invalid_lines": invalid,
    "historical_split": split,
    "test_samples_common": len(actual),
    "prediction_target": "hashRate de la siguiente muestra",
    "results": results,
    "note": (
        "Solo se usan valores de la muestra anterior y anteriores. "
        "Esto compara referencias; no entrena un modelo."
    ),
}

REPORT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("TEOS NEURONA — COMPARACIÓN DE VENTANAS")
print("Modo: solo lectura; sin entrenamiento")
print(f"Muestras únicas: {len(rows)}")
print(f"Muestras comunes de prueba: {len(actual)}")

for name, result in sorted(
    results.items(), key=lambda item: item[1]["mae_ghs"]
):
    print(f"\n{name}")
    print(f"  MAE: {result['mae_ghs']:.4f} GH/s")
    print(f"  RMSE: {result['rmse_ghs']:.4f} GH/s")
    print(
        "  Error relativo medio: "
        f"{result['mean_absolute_relative_error_pct']:.4f}%"
    )

print(f"\nInforme: {REPORT}")
