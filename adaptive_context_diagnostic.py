import json
from pathlib import Path
from collections import defaultdict

P = Path("data/processed/learning_predictions_v2.jsonl")
O = Path("data/processed/learning_outcomes_v2.jsonl")
REPORT = Path("data/processed/adaptive_context_diagnostic.json")

def load(path):
    rows = []
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            rows.append(json.loads(line.replace("\0", "")))
        except (ValueError, TypeError):
            pass
    return rows

def num(x):
    try:
        x = float(x)
        return x if x == x and abs(x) != float("inf") else None
    except (TypeError, ValueError):
        return None

predictions = {
    r["prediction_id"]: r
    for r in load(P)
    if r.get("method") == "adaptativo_neurona"
    and r.get("prediction_id")
}

adaptive = {
    r["prediction_id"]: r
    for r in load(O)
    if r.get("method") == "adaptativo_neurona"
    and r.get("prediction_id")
}

reference = {
    (r.get("source_timestamp"), r.get("target_timestamp")): r
    for r in load(O)
    if r.get("method") == "referencia_1h"
}

fields = {
    "referencia_1h": None,
    "base_adaptativa": "adaptive_base_prediction_GHs",
    "aprendiz_global": "online_candidate_prediction_GHs",
    "aprendiz_contextual": "contextual_candidate_prediction_GHs",
}

regimes = defaultdict(list)
contexts = defaultdict(list)
all_rows = []

for pid, p in predictions.items():
    a = adaptive.get(pid)
    if not a:
        continue

    key = (a.get("source_timestamp"), a.get("target_timestamp"))
    ref = reference.get(key)
    if not ref:
        continue

    source = num(p.get("source_hashRate_GHs"))
    actual = num(a.get("actual_hashRate_GHs"))
    ref_actual = num(ref.get("actual_hashRate_GHs"))
    ref_forecast = num(ref.get("predicted_hashRate_GHs"))

    if None in (source, actual, ref_actual, ref_forecast):
        continue
    if abs(actual - ref_actual) > 0.00001 or source <= 0:
        continue

    forecasts = {"referencia_1h": ref_forecast}
    valid = True

    for name, field in fields.items():
        if field is None:
            continue
        value = num(p.get(field))
        if value is None:
            valid = False
            break
        forecasts[name] = value

    if not valid:
        continue

    change = (actual - source) / source * 100
    regime = "caida" if change <= -1 else (
        "subida" if change >= 1 else "estable"
    )

    row = {
        "actual": actual,
        "forecasts": forecasts,
        "regime": regime,
    }
    all_rows.append(row)
    regimes[regime].append(row)

    keys = p.get("contextual_context_keys") or ["SIN_CONTEXTO"]
    for context in set(keys):
        contexts[str(context)].append(row)

def metrics(rows):
    result = {}
    for name in fields:
        errors = [
            abs(r["actual"] - r["forecasts"][name])
            for r in rows
        ]
        result[name] = round(sum(errors) / len(errors), 4)
    return result

report = {
    "common_pairs": len(all_rows),
    "overall": metrics(all_rows),
    "regimes": {},
    "contexts": {},
}

print("\nEVALUACIÓN POR CONTEXTO Y RÉGIMEN")
print("Pares comunes:", len(all_rows))

print("\nRESULTADO GENERAL")
for name, mae in report["overall"].items():
    print(f"{name:24} MAE: {mae:.4f} GH/s")

print("\nPOR RÉGIMEN")
for name, rows in regimes.items():
    result = metrics(rows)
    report["regimes"][name] = {
        "samples": len(rows), "mae": result
    }
    print(f"\n{name.upper()} — {len(rows)} muestras")
    for method, value in result.items():
        print(f"  {method:22} {value:.4f}")

print("\nPOR CONTEXTO (mínimo 100 muestras)")
ranked = []

for name, rows in contexts.items():
    if len(rows) < 100:
        continue
    result = metrics(rows)
    report["contexts"][name] = {
        "samples": len(rows), "mae": result
    }
    ranked.append((
        result["aprendiz_contextual"] - result["referencia_1h"],
        name, len(rows), result
    ))

for delta, name, count, result in sorted(ranked):
    print(f"\n{name} — {count} muestras")
    for method, value in result.items():
        print(f"  {method:22} {value:.4f}")
    print(f"  Diferencia contextual vs 1h: {delta:+.4f}")

REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print("\nInforme:", REPORT)
