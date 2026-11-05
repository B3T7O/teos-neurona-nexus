import json
from collections import defaultdict
from pathlib import Path

PRED = Path("data/processed/learning_predictions_v2.jsonl")
OUT = Path("data/processed/learning_outcomes_v2.jsonl")
REPORT = Path("data/processed/adaptive_regime_audit.json")

METHODS = ("adaptativo_neurona", "referencia_1h")
THRESHOLD = 1.0  # Cambio mínimo porcentual para clasificar una caída/subida

def read_jsonl(path):
    rows = []
    invalid = 0
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                line = line.replace("\0", "").strip()
                if line:
                    rows.append(json.loads(line))
            except (ValueError, TypeError):
                invalid += 1
    return rows, invalid

predictions, bad_predictions = read_jsonl(PRED)
outcomes, bad_outcomes = read_jsonl(OUT)

source_by_id = {
    r["prediction_id"]: r.get("source_hashRate_GHs")
    for r in predictions
    if r.get("method") in METHODS and r.get("prediction_id")
}

pairs = defaultdict(dict)
for r in outcomes:
    if r.get("method") not in METHODS:
        continue
    key = (r.get("source_timestamp"), r.get("target_timestamp"))
    if all(key) and r.get("prediction_id"):
        pairs[key][r["method"]] = r

segments = defaultdict(list)
missing_source = 0
for key, methods in pairs.items():
    if not all(m in methods for m in METHODS):
        continue

    adaptive = methods["adaptativo_neurona"]
    baseline = methods["referencia_1h"]
    source = source_by_id.get(adaptive["prediction_id"])

    if source is None or float(source) <= 0:
        missing_source += 1
        continue

    actual = float(adaptive["actual_hashRate_GHs"])
    source = float(source)
    change = (actual - source) / source * 100

    if change <= -THRESHOLD:
        segment = "caida"
    elif change >= THRESHOLD:
        segment = "subida"
    else:
        segment = "estable"

    segments[segment].append({
        "adaptive_error": float(adaptive["absolute_error_GHs"]),
        "baseline_error": float(baseline["absolute_error_GHs"]),
        "adaptive_prediction": float(adaptive["predicted_hashRate_GHs"]),
        "baseline_prediction": float(baseline["predicted_hashRate_GHs"]),
        "source": source,
    })

report = {
    "threshold_percent": THRESHOLD,
    "segments": {},
    "invalid_prediction_lines": bad_predictions,
    "invalid_outcome_lines": bad_outcomes,
    "pairs_without_source": missing_source,
}

print("EVALUACIÓN DEL APRENDIZ ADAPTATIVO")
print("Clasificación retrospectiva por cambio real del hashrate")
print("-" * 65)

for name in ("caida", "estable", "subida"):
    rows = segments[name]
    if not rows:
        continue

    n = len(rows)
    adaptive_mae = sum(x["adaptive_error"] for x in rows) / n
    baseline_mae = sum(x["baseline_error"] for x in rows) / n
    adaptive_hits = sum(
        x["adaptive_prediction"] < x["source"] * (1 - THRESHOLD / 100)
        for x in rows
    )
    baseline_hits = sum(
        x["baseline_prediction"] < x["source"] * (1 - THRESHOLD / 100)
        for x in rows
    )

    result = {
        "samples": n,
        "adaptive_mae_GHs": round(adaptive_mae, 4),
        "reference_1h_mae_GHs": round(baseline_mae, 4),
        "adaptive_minus_reference_GHs": round(adaptive_mae - baseline_mae, 4),
        "adaptive_predicted_drops": adaptive_hits,
        "reference_predicted_drops": baseline_hits,
    }
    report["segments"][name] = result

    print(f"\n{name.upper()} — {n} muestras")
    print(f"MAE adaptativo: {adaptive_mae:.4f} GH/s")
    print(f"MAE referencia 1h: {baseline_mae:.4f} GH/s")
    print(f"Diferencia: {adaptive_mae - baseline_mae:+.4f} GH/s")
    if name == "caida":
        print(f"Predicciones que anticiparon caída (umbral {THRESHOLD}%):")
        print(f"Adaptativo: {adaptive_hits}/{n}")
        print(f"Referencia: {baseline_hits}/{n}")

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"\nInforme guardado: {REPORT}")
print("Nota: análisis retrospectivo; no demuestra anticipación prospectiva.")
