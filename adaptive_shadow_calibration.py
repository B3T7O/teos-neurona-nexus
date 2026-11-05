import json
from pathlib import Path
from datetime import datetime

P = Path("data/processed/learning_predictions_v2.jsonl")
O = Path("data/processed/learning_outcomes_v2.jsonl")
REPORT = Path("data/processed/adaptive_shadow_calibration.json")

def load(path):
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

predictions, bad_p = load(P)
outcomes, bad_o = load(O)

def number(value):
    try:
        value = float(value)
        return value if value == value and abs(value) != float("inf") else None
    except (TypeError, ValueError):
        return None

pred = {
    r["prediction_id"]: r
    for r in predictions
    if r.get("method") == "adaptativo_neurona"
    and r.get("prediction_id")
}

adaptive = {
    r["prediction_id"]: r
    for r in outcomes
    if r.get("method") == "adaptativo_neurona"
    and r.get("prediction_id")
}

reference = {
    (r.get("source_timestamp"), r.get("target_timestamp")): r
    for r in outcomes
    if r.get("method") == "referencia_1h"
}

rows = []
for pid, p in pred.items():
    a = adaptive.get(pid)
    if not a:
        continue

    key = (a.get("source_timestamp"), a.get("target_timestamp"))
    ref = reference.get(key)
    if not ref:
        continue

    actual = number(a.get("actual_hashRate_GHs"))
    ref_actual = number(ref.get("actual_hashRate_GHs"))
    base = number(p.get("adaptive_base_prediction_GHs"))
    global_candidate = number(p.get("online_candidate_prediction_GHs"))
    contextual_candidate = number(p.get("contextual_candidate_prediction_GHs"))
    ref_prediction = number(ref.get("predicted_hashRate_GHs"))

    values = [actual, ref_actual, base, global_candidate,
              contextual_candidate, ref_prediction]

    if any(v is None for v in values):
        continue
    if abs(actual - ref_actual) > 0.00001:
        continue

    rows.append({
        "source": p["source_timestamp"],
        "target": a["target_timestamp"],
        "actual": actual,
        "base": base,
        "global": global_candidate,
        "contextual": contextual_candidate,
        "reference": ref_prediction,
    })

rows.sort(key=lambda r: datetime.fromisoformat(
    r["source"].replace("Z", "+00:00")
))

if len(rows) < 100:
    raise SystemExit(f"Muestras insuficientes: {len(rows)}")

split = int(len(rows) * 0.60)
train, test = rows[:split], rows[split:]

def mae(data, field, alpha=1.0):
    return sum(
        abs(r["actual"] - (
            r["base"] + alpha * (r[field] - r["base"])
        ))
        for r in data
    ) / len(data)

def calibrate(field):
    candidates = [(mae(train, field, i / 20), i / 20)
                  for i in range(21)]
    train_error, alpha = min(candidates)
    return {
        "alpha": alpha,
        "train_mae": train_error,
        "test_mae": mae(test, field, alpha),
        "raw_test_mae": mae(test, field, 1.0),
    }

global_result = calibrate("global")
context_result = calibrate("contextual")

results = {
    "total_common_pairs": len(rows),
    "training_pairs": len(train),
    "holdout_pairs": len(test),
    "reference_1h_test_mae": mae(test, "reference"),
    "adaptive_base_test_mae": sum(
        abs(r["actual"] - r["base"]) for r in test
    ) / len(test),
    "global": global_result,
    "contextual": context_result,
    "invalid_prediction_lines": bad_p,
    "invalid_outcome_lines": bad_o,
    "method": "calibracion temporal 60/40",
}

REPORT.write_text(json.dumps(results, indent=2), encoding="utf-8")

print("\nCALIBRACIÓN TEMPORAL DE APRENDICES SHADOW")
print("Muestras comunes:", len(rows))
print("Entrenamiento:", len(train))
print("Validación posterior:", len(test))
print(f"\nReferencia 1h: {results['reference_1h_test_mae']:.4f} GH/s")
print(f"Base adaptativa: {results['adaptive_base_test_mae']:.4f} GH/s")

for name, result in [
    ("Global", global_result),
    ("Contextual", context_result),
]:
    print(f"\n{name}:")
    print(f"Intensidad óptima: {result['alpha']:.2f}")
    print(f"MAE entrenamiento: {result['train_mae']:.4f}")
    print(f"MAE validación: {result['test_mae']:.4f}")
    print(f"MAE sin calibrar: {result['raw_test_mae']:.4f}")

print("\nInforme:", REPORT)
