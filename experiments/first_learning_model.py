import hashlib
import json
import math
from pathlib import Path

import numpy as np

SNAPSHOT = Path("experiments/frozen_bitaxe_samples.marked.jsonl")
MANIFEST = Path("experiments/frozen_evaluation_manifest.json")
OUTPUT = Path("experiments/first_learning_model_report.json")

if OUTPUT.exists():
    raise SystemExit(f"Ya existe {OUTPUT}; no se sobrescribió.")

raw = SNAPSHOT.read_bytes()
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
digest = hashlib.sha256(raw).hexdigest()

if digest != manifest["sha256"]:
    raise SystemExit("ERROR: el SHA-256 no coincide.")

rows = []
for line in raw.splitlines():
    try:
        row = json.loads(line)
        row["_ts"] = row["timestamp"]
        row["_target"] = float(row["hashRate"])
        rows.append(row)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        continue

rows.sort(key=lambda r: r["_ts"])
unique = {}
for row in rows:
    unique[row["_ts"]] = row
rows = [unique[t] for t in sorted(unique)]

# Solo variables disponibles en el registro anterior.
# Se excluyen contadores acumulativos, altura de bloque,
# bestDiff, networkDifficulty y campos constantes/sin utilidad conocida.
BASE_FIELDS = [
    "hashRate_1h",
    "hashRate_10m",
    "hashRate_1m",
    "hashRate",
    "expectedHashrate",
    "temp",
    "vrTemp",
    "power",
    "voltage",
    "frequency",
    "fanrpm",
    "errorPercentage",
    "wifiRSSI",
]

def feature_at(i):
    previous = rows[i - 1]
    values = []

    for field in BASE_FIELDS:
        value = previous.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            return None
        values.append(float(value))

    # Tendencias recientes, calculadas solo con datos anteriores.
    for field in ("hashRate", "hashRate_10m", "hashRate_1h"):
        now = previous.get(field)
        earlier = rows[i - 2].get(field) if i >= 2 else None
        if (
            isinstance(now, bool)
            or isinstance(earlier, bool)
            or not isinstance(now, (int, float))
            or not isinstance(earlier, (int, float))
            or not math.isfinite(now)
            or not math.isfinite(earlier)
        ):
            return None
        values.append(float(now) - float(earlier))

    return np.asarray(values, dtype=float)

# X[i] utiliza datos hasta i-1; y[i] es el hashRate de la muestra i.
X, y, indices = [], [], []
for i in range(2, len(rows)):
    x = feature_at(i)
    target = rows[i]["_target"]
    baseline = rows[i - 1].get("hashRate_1h")
    if (
        x is None
        or not math.isfinite(target)
        or isinstance(baseline, bool)
        or not isinstance(baseline, (int, float))
        or not math.isfinite(baseline)
    ):
        continue
    X.append(x)
    y.append(target)
    indices.append(i)

X = np.asarray(X, dtype=float)
y = np.asarray(y, dtype=float)
indices = np.asarray(indices, dtype=int)

if len(y) < 100:
    raise SystemExit(f"Insuficientes muestras utilizables: {len(y)}")

# Cinco tramos cronológicos; cada modelo solo ve targets anteriores.
bounds = [int(len(y) * p) for p in (0.50, 0.60, 0.70, 0.80, 0.90, 1.00)]
folds = []
all_actual, all_model, all_baseline = [], [], []

for fold in range(5):
    start, end = bounds[fold], bounds[fold + 1]
    train_end = start
    if train_end < 50 or end <= start:
        continue

    X_train, y_train = X[:train_end], y[:train_end]
    X_test, y_test = X[start:end], y[start:end]

    # Escalado ajustado solo con el conjunto de entrenamiento.
    mu = X_train.mean(axis=0)
    sigma = X_train.std(axis=0)
    sigma[sigma < 1e-9] = 1.0
    A = (X_train - mu) / sigma
    B = (X_test - mu) / sigma

    # Intercepto explícito; penalización Ridge solo sobre coeficientes.
    A = np.column_stack([np.ones(len(A)), A])
    B = np.column_stack([np.ones(len(B)), B])
    penalty = np.eye(A.shape[1]) * 10.0
    penalty[0, 0] = 0.0

    coefficients = np.linalg.solve(A.T @ A + penalty, A.T @ y_train)
    predictions = B @ coefficients

    # Referencia anterior, alineada exactamente con el mismo objetivo.
    baseline = np.asarray([
        float(rows[int(idx) - 1]["hashRate_1h"])
        for idx in indices[start:end]
    ])

    def metrics(actual, predicted):
        error = actual - predicted
        return {
            "n": int(len(actual)),
            "mae_ghs": float(np.mean(np.abs(error))),
            "rmse_ghs": float(np.sqrt(np.mean(error ** 2))),
        }

    model_score = metrics(y_test, predictions)
    baseline_score = metrics(y_test, baseline)

    folds.append({
        "fold": fold + 1,
        "train_samples": int(train_end),
        "test_samples": int(end - start),
        "ridge": model_score,
        "previous_hashRate_1h": baseline_score,
        "model_improved_mae": model_score["mae_ghs"] < baseline_score["mae_ghs"],
    })

    all_actual.extend(y_test.tolist())
    all_model.extend(predictions.tolist())
    all_baseline.extend(baseline.tolist())

def overall_metrics(actual, predicted):
    actual = np.asarray(actual)
    predicted = np.asarray(predicted)
    error = actual - predicted
    return {
        "n": len(actual),
        "mae_ghs": float(np.mean(np.abs(error))),
        "rmse_ghs": float(np.sqrt(np.mean(error ** 2))),
    }

model_overall = overall_metrics(all_actual, all_model)
baseline_overall = overall_metrics(all_actual, all_baseline)

report = {
    "snapshot_sha256": digest,
    "valid_unique_records": len(rows),
    "usable_samples": len(y),
    "features": BASE_FIELDS + [
        "delta_hashRate",
        "delta_hashRate_10m",
        "delta_hashRate_1h",
    ],
    "model": "Ridge regression, alpha=10",
    "folds": folds,
    "overall": {
        "ridge": model_overall,
        "previous_hashRate_1h": baseline_overall,
        "mae_improvement_pct": (
            (baseline_overall["mae_ghs"] - model_overall["mae_ghs"])
            / baseline_overall["mae_ghs"] * 100
        ),
    },
    "training_performed": True,
    "live_system_modified": False,
    "bitcoin_block_prediction": False,
}

OUTPUT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("PRIMER EXPERIMENTO DE APRENDIZAJE TEOS NEURONA")
print("SHA-256 verificado:", digest)
print("Registros utilizables:", len(y))
for fold in folds:
    print(
        f"Tramo {fold['fold']}: "
        f"Ridge MAE={fold['ridge']['mae_ghs']:.4f} | "
        f"referencia 1h MAE={fold['previous_hashRate_1h']['mae_ghs']:.4f} GH/s | "
        f"mejora={fold['model_improved_mae']}"
    )
print("\nRESUMEN GLOBAL")
print(f"Ridge: MAE={model_overall['mae_ghs']:.4f}, RMSE={model_overall['rmse_ghs']:.4f} GH/s")
print(f"Referencia 1h: MAE={baseline_overall['mae_ghs']:.4f}, RMSE={baseline_overall['rmse_ghs']:.4f} GH/s")
print(f"Mejora de MAE: {report['overall']['mae_improvement_pct']:.2f}%")
print("Informe:", OUTPUT)
print("Solo se creó un experimento; colector y panel intactos.")
