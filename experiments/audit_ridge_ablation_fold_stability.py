#!/usr/bin/env python3
"""Estabilidad cronológica de la ablación individual Ridge."""

import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

SNAPSHOT = ROOT / "experiments/frozen_bitaxe_samples.jsonl"
MANIFEST = ROOT / "experiments/frozen_evaluation_manifest.json"
SCRIPT = ROOT / "experiments/first_learning_model.py"
ORIGINAL = ROOT / "experiments/first_learning_model_report.json"
ABLATION = ROOT / "experiments/ridge_feature_ablation_report.json"

OUTPUT = ROOT / "experiments/ridge_ablation_fold_stability_report.json"

HASHES = {
    SNAPSHOT: "dfdd8f2533d89190e94f5ef113c2a24a43325df1d51c93ad810ff417b53379a5",
    SCRIPT: "b1e1a69fd272c09574a89ac866918889065fab5746ed214b98bdd6eaf8bdab7d",
    ORIGINAL: "835002b3e7720fcbf9c6d0b6ad450a86ff474d01bf5126aaf75c8d8dc9a752ba",
}

BASE_FIELDS = [
    "hashRate_1h", "hashRate_10m", "hashRate_1m",
    "hashRate", "expectedHashrate", "temp", "vrTemp",
    "power", "voltage", "frequency", "fanrpm",
    "errorPercentage", "wifiRSSI",
]

FEATURES = BASE_FIELDS + [
    "delta_hashRate",
    "delta_hashRate_10m",
    "delta_hashRate_1h",
]

EXPECTED_SAMPLES = 422
ALPHA = 10.0
TOLERANCE = 1e-10
DELTA_EPSILON = 1e-8


def stop(message):
    raise SystemExit(f"AUDITORÍA DETENIDA: {message}")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    if len(actual) == 0 or len(actual) != len(predicted):
        stop("Conjunto de evaluación vacío o desalineado.")

    error = actual - predicted

    return {
        "n": int(len(actual)),
        "mae_ghs": float(np.mean(np.abs(error))),
        "rmse_ghs": float(np.sqrt(np.mean(error ** 2))),
    }


def verify_metrics(name, current, reference):
    if current["n"] != reference["n"]:
        stop(f"{name}: número de muestras diferente.")

    for key in ("mae_ghs", "rmse_ghs"):
        if not math.isclose(
            current[key],
            reference[key],
            rel_tol=TOLERANCE,
            abs_tol=TOLERANCE,
        ):
            stop(f"{name}: no coincide {key}.")


def fit_predict(train_x, train_y, test_x, selected):
    A0 = train_x[:, selected]
    B0 = test_x[:, selected]

    mu = A0.mean(axis=0)
    sigma = A0.std(axis=0)
    sigma[sigma < 1e-9] = 1.0

    A = (A0 - mu) / sigma
    B = (B0 - mu) / sigma

    A = np.column_stack([np.ones(len(A)), A])
    B = np.column_stack([np.ones(len(B)), B])

    penalty = np.eye(A.shape[1]) * ALPHA
    penalty[0, 0] = 0.0

    coefficients = np.linalg.solve(
        A.T @ A + penalty,
        A.T @ train_y,
    )

    return B @ coefficients


def classify_effect(deltas):
    positive = sum(d > DELTA_EPSILON for d in deltas)
    negative = sum(d < -DELTA_EPSILON for d in deltas)
    neutral = len(deltas) - positive - negative

    if positive == 5:
        status = "beneficio_consistente"
    elif negative == 5:
        status = "perjuicio_consistente"
    elif positive > 0 and negative > 0:
        status = "efecto_inestable"
    elif positive > 0:
        status = "beneficio_parcial"
    elif negative > 0:
        status = "perjuicio_parcial"
    else:
        status = "sin_cambio_apreciable"

    return {
        "classification": status,
        "folds_removing_feature_worsens_mae": positive,
        "folds_removing_feature_improves_mae": negative,
        "folds_without_material_change": neutral,
        "mae_delta_by_fold_ghs": deltas,
    }


def main():
    required = [
        SNAPSHOT, MANIFEST, SCRIPT, ORIGINAL, ABLATION
    ]

    for path in required:
        if not path.is_file():
            stop(f"Falta el archivo {path.name}")

    if OUTPUT.exists():
        stop(f"El informe ya existe: {OUTPUT.name}. No se sobrescribió.")

    # Verificación de la evidencia original.
    for path, expected in HASHES.items():
        if sha256(path) != expected:
            stop(f"SHA-256 inesperado: {path.name}")

    snapshot_hash = sha256(SNAPSHOT)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    original = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    ablation = json.loads(ABLATION.read_text(encoding="utf-8"))

    if manifest.get("sha256") != snapshot_hash:
        stop("La fotografía no coincide con el manifiesto.")

    if original.get("snapshot_sha256") != snapshot_hash:
        stop("El informe original no corresponde a la fotografía.")

    if ablation.get("snapshot_sha256") != snapshot_hash:
        stop("El informe de ablación no corresponde a la fotografía.")

    if ablation.get("ridge_alpha") != ALPHA:
        stop("El alpha de la ablación no coincide.")

    # Reconstrucción idéntica al predictor original.
    rows = []

    for line in SNAPSHOT.read_bytes().splitlines():
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

    X, y, indices = [], [], []

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

    if len(y) != original.get("usable_samples"):
        stop("No coincide el número de muestras utilizables.")

    if len(FEATURES) != X.shape[1]:
        stop("El número de características no coincide.")

    expected_ablation = ablation.get("feature_ablation", {})
    if set(expected_ablation) != set(FEATURES):
        stop("El informe anterior no contiene las 16 ablaciones.")

    bounds = [
        int(len(y) * p)
        for p in (0.50, 0.60, 0.70, 0.80, 0.90, 1.00)
    ]

    full_selected = np.arange(len(FEATURES))

    all_actual = []
    all_full = []
    all_baseline = []

    variants = {
        feature: {"actual": [], "predicted": []}
        for feature in FEATURES
    }

    folds = []

    # Cinco tramos cronológicos.
    for fold in range(5):
        start, end = bounds[fold], bounds[fold + 1]

        if start < 50 or end <= start:
            stop(f"Tramo inválido: {fold + 1}")

        train_x = X[:start]
        train_y = y[:start]
        test_x = X[start:end]
        test_y = y[start:end]

        # Modelo completo.
        full_prediction = fit_predict(
            train_x, train_y, test_x, full_selected
        )

        # Referencia original de 1 hora.
        baseline = np.asarray([
            float(rows[int(idx) - 1]["hashRate_1h"])
            for idx in indices[start:end]
        ])

        full_score = metrics(test_y, full_prediction)
        baseline_score = metrics(test_y, baseline)

        old_fold = original["folds"][fold]

        verify_metrics(
            f"Tramo {fold + 1} Ridge completo",
            full_score,
            old_fold["ridge"],
        )

        verify_metrics(
            f"Tramo {fold + 1} referencia 1h",
            baseline_score,
            old_fold["previous_hashRate_1h"],
        )

        all_actual.extend(test_y.tolist())
        all_full.extend(full_prediction.tolist())
        all_baseline.extend(baseline.tolist())

        fold_ablation = {}

        # Retirar una sola característica en cada variante.
        for j, feature in enumerate(FEATURES):
            selected = np.asarray([
                k for k in range(len(FEATURES)) if k != j
            ])

            prediction = fit_predict(
                train_x, train_y, test_x, selected
            )

            score = metrics(test_y, prediction)

            delta_mae = (
                score["mae_ghs"] - full_score["mae_ghs"]
            )

            delta_rmse = (
                score["rmse_ghs"] - full_score["rmse_ghs"]
            )

            fold_ablation[feature] = {
                "without_feature": score,
                "mae_delta_vs_full_ghs": delta_mae,
                "rmse_delta_vs_full_ghs": delta_rmse,
            }

            variants[feature]["actual"].extend(test_y.tolist())
            variants[feature]["predicted"].extend(prediction.tolist())

        folds.append({
            "fold": fold + 1,
            "train_samples": int(start),
            "test_samples": int(end - start),
            "full_model": full_score,
            "baseline_1h": baseline_score,
            "feature_ablation": fold_ablation,
        })

    # Confirmar las 422 predicciones y el modelo completo.
    if len(all_actual) != EXPECTED_SAMPLES:
        stop(f"Se esperaban 422 predicciones, obtenidas: {len(all_actual)}.")

    global_full = metrics(all_actual, all_full)
    global_baseline = metrics(all_actual, all_baseline)

    verify_metrics(
        "Ridge global",
        global_full,
        original["overall"]["ridge"],
    )

    verify_metrics(
        "Referencia global",
        global_baseline,
        original["overall"]["previous_hashRate_1h"],
    )

    # Validar las 16 ablaciones contra su informe global anterior.
    feature_summary = {}

    for feature in FEATURES:
        variant = variants[feature]

        aggregate = metrics(
            variant["actual"],
            variant["predicted"],
        )

        previous = expected_ablation[feature]["without_feature"]

        verify_metrics(
            f"Ablación global de {feature}",
            aggregate,
            previous,
        )

        global_delta = (
            aggregate["mae_ghs"] - global_full["mae_ghs"]
        )

        fold_deltas = [
            fold["feature_ablation"][feature]["mae_delta_vs_full_ghs"]
            for fold in folds
        ]

        fold_rmse_deltas = [
            fold["feature_ablation"][feature]["rmse_delta_vs_full_ghs"]
            for fold in folds
        ]

        stability = classify_effect(fold_deltas)

        feature_summary[feature] = {
            **stability,
            "aggregate_without_feature": aggregate,
            "aggregate_mae_delta_vs_full_ghs": global_delta,
            "aggregate_rmse_delta_vs_full_ghs": (
                aggregate["rmse_ghs"] - global_full["rmse_ghs"]
            ),
            "rmse_delta_by_fold_ghs": fold_rmse_deltas,
            "previous_global_ablation_verified": True,
        }

        old_delta = expected_ablation[feature]["mae_delta_vs_full_ghs"]

        if not math.isclose(
            global_delta,
            old_delta,
            rel_tol=TOLERANCE,
            abs_tol=TOLERANCE,
        ):
            stop(f"{feature}: diferencia frente a la ablación anterior.")

    # Orden: primero efectos positivos estables, luego efectos negativos.
    ranking = sorted(
        FEATURES,
        key=lambda feature: (
            feature_summary[feature]["folds_removing_feature_worsens_mae"],
            -feature_summary[feature]["folds_removing_feature_improves_mae"],
            feature_summary[feature]["aggregate_mae_delta_vs_full_ghs"],
        ),
        reverse=True,
    )

    report = {
        "title": "TEOS NEURONA — Estabilidad cronológica de ablaciones Ridge",
        "snapshot_sha256": snapshot_hash,
        "source_ablation_report_sha256": sha256(ABLATION),
        "source_ablation_script_sha256": (
            sha256(ROOT / "experiments/audit_ridge_feature_ablation.py")
            if (ROOT / "experiments/audit_ridge_feature_ablation.py").exists()
            else None
        ),
        "validation": {
            "original_model_reproduced": True,
            "original_five_folds_verified": True,
            "out_of_sample_predictions": EXPECTED_SAMPLES,
            "global_ridge_metrics_verified": True,
            "global_baseline_metrics_verified": True,
            "all_16_global_ablations_reproduced": True,
            "same_targets_in_all_variants": True,
            "original_files_modified": False,
        },
        "methodology": {
            "folds": 5,
            "ridge_alpha": ALPHA,
            "one_feature_removed_per_variant": True,
            "mae_delta_definition": (
                "MAE sin característica menos MAE del Ridge completo. "
                "Positivo significa que eliminarla empeora el resultado."
            ),
            "rmse_delta_definition": (
                "RMSE sin característica menos RMSE del Ridge completo."
            ),
            "neutral_tolerance_ghs": DELTA_EPSILON,
        },
        "global_reference": {
            "ridge": global_full,
            "baseline_1h": global_baseline,
        },
        "folds": folds,
        "feature_stability": feature_summary,
        "ranking_by_fold_consistency": ranking,
        "warning": (
            "La estabilidad entre cinco tramos históricos es descriptiva. "
            "No demuestra causalidad ni garantiza generalización futura. "
            "Las decisiones definitivas requieren validación prospectiva."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA — ESTABILIDAD DE ABLACIONES RIDGE")
    print("Integridad y reproducción original: SUPERADAS")
    print("Predicciones verificadas:", EXPECTED_SAMPLES)
    print("Cinco tramos verificados.")
    print("16 ablaciones globales reproducidas.")

    print("\n--- ESTABILIDAD POR CARACTERÍSTICA ---")

    for feature in ranking:
        item = feature_summary[feature]

        print(
            f"{feature}: {item['classification']} | "
            f"retirarla empeora: "
            f"{item['folds_removing_feature_worsens_mae']}/5 | "
            f"retirarla mejora: "
            f"{item['folds_removing_feature_improves_mae']}/5 | "
            f"delta global: "
            f"{item['aggregate_mae_delta_vs_full_ghs']:+.6f} GH/s"
        )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("Modelo original, datos congelados y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
