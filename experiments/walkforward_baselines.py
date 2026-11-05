import hashlib
import json
import math
from pathlib import Path
from statistics import mean

snapshot = Path("experiments/frozen_bitaxe_samples.jsonl")
manifest_path = Path("experiments/frozen_evaluation_manifest.json")
output = Path("experiments/walkforward_baseline_report.json")

if output.exists():
    raise SystemExit(f"Ya existe {output}; no se sobrescribió.")

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
raw = snapshot.read_bytes()
digest = hashlib.sha256(raw).hexdigest()

if digest != manifest["sha256"]:
    raise SystemExit("ERROR: el hash de la fotografía no coincide.")

rows = []
for line in raw.splitlines():
    try:
        row = json.loads(line)
        ts = row["timestamp"]
        hr = row.get("hashRate")
        if (
            not isinstance(ts, str)
            or isinstance(hr, bool)
            or not isinstance(hr, (int, float))
            or not math.isfinite(hr)
            or hr < 0
        ):
            continue
        row["_hr"] = float(hr)
        rows.append(row)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        continue

# Orden temporal y una fila por timestamp.
rows.sort(key=lambda r: r["timestamp"])
unique = {}
for row in rows:
    unique[row["timestamp"]] = row
rows = [unique[t] for t in sorted(unique)]

n = len(rows)
if n < 50:
    raise SystemExit("Insuficientes datos para cinco tramos.")

# Cinco tramos cronológicos consecutivos entre el 50 % y el final.
boundaries = [int(n * x / 10) for x in (5, 6, 7, 8, 9, 10)]
folds = []
all_actual = []
all_predictions = {
    "previous_hashRate_1h": [],
    "previous_hashRate_10m": [],
    "mean_previous_5": [],
    "last_hashRate": [],
}

for fold_number in range(5):
    start = boundaries[fold_number]
    end = boundaries[fold_number + 1]
    actual = []
    predictions = {name: [] for name in all_predictions}

    for i in range(max(start, 5), end):
        prev = rows[i - 1]
        candidates = {
            "previous_hashRate_1h": prev.get("hashRate_1h"),
            "previous_hashRate_10m": prev.get("hashRate_10m"),
            "mean_previous_5": mean(
                rows[j]["_hr"] for j in range(i - 5, i)
            ),
            "last_hashRate": prev["_hr"],
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
            predictions[name].append(float(value))

    def score(y, p):
        errors = [a - b for a, b in zip(y, p)]
        return {
            "n": len(y),
            "mae_ghs": mean(abs(e) for e in errors) if errors else None,
            "rmse_ghs": (
                math.sqrt(mean(e * e for e in errors)) if errors else None
            ),
        }

    fold_results = {
        name: score(actual, pred)
        for name, pred in predictions.items()
    }
    best = min(
        (name for name, result in fold_results.items()
         if result["mae_ghs"] is not None),
        key=lambda name: fold_results[name]["mae_ghs"],
    ) if actual else None

    folds.append({
        "fold": fold_number + 1,
        "start_index": start,
        "end_index_exclusive": end,
        "results": fold_results,
        "best_by_mae": best,
    })

    all_actual.extend(actual)
    for name in all_predictions:
        all_predictions[name].extend(predictions[name])

def score_all(y, p):
    errors = [a - b for a, b in zip(y, p)]
    return {
        "n": len(y),
        "mae_ghs": mean(abs(e) for e in errors) if errors else None,
        "rmse_ghs": (
            math.sqrt(mean(e * e for e in errors)) if errors else None
        ),
    }

overall = {
    name: score_all(all_actual, pred)
    for name, pred in all_predictions.items()
}

report = {
    "snapshot_sha256": digest,
    "unique_samples": n,
    "folds": folds,
    "overall": overall,
    "training_performed": False,
    "purpose": "Comprobar estabilidad temporal de referencias simples.",
}

output.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("VALIDACIÓN WALK-FORWARD")
print("SHA-256 verificado:", digest)
print("Registros únicos:", n)
for fold in folds:
    print(f"\nTramo {fold['fold']} — mejor: {fold['best_by_mae']}")
    for name, result in sorted(
        fold["results"].items(),
        key=lambda item: (
            float("inf") if item[1]["mae_ghs"] is None
            else item[1]["mae_ghs"]
        ),
    ):
        if result["mae_ghs"] is not None:
            print(
                f"  {name}: MAE={result['mae_ghs']:.4f}, "
                f"RMSE={result['rmse_ghs']:.4f} GH/s"
            )

print("\nRESUMEN GLOBAL")
for name, result in sorted(
    overall.items(), key=lambda item: item[1]["mae_ghs"]
):
    print(
        f"{name}: MAE={result['mae_ghs']:.4f}, "
        f"RMSE={result['rmse_ghs']:.4f} GH/s"
    )

print("\nInforme:", output)
print("Sin entrenamiento ni cambios en los datos originales.")
