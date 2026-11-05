#!/usr/bin/env python3
"""Ablación individual de características Ridge sobre datos congelados."""

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
OUTPUT = ROOT / "experiments/ridge_feature_ablation_report.json"

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

ALPHA = 10.0
EXPECTED_OOS = 422


def stop(message):
    raise SystemExit("ABlACIÓN DETENIDA: " + message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(actual, predicted):
    error = np.asarray(actual) - np.asarray(predicted)
    return {
        "n": len(error),
        "mae_ghs": float(np.mean(np.abs(error))),
        "rmse_ghs": float(np.sqrt(np.mean(error ** 2))),
    }


def verify(new, old, label):
    if new["n"] != old["n"]:
        stop(f"{label}: número de muestras diferente.")

    for key in ("mae_ghs", "rmse_ghs"):
        if not math.isclose(
            new[key], old[key], rel_tol=1e-10, abs_tol=1e-10
        ):
            stop(f"{label}: no coincide {key}.")


def fit_predict(train_x, train_y, test_x, selected):
    a_train = train_x[:, selected]
    a_test = test_x[:, selected]

    mu = a_train.mean(axis=0)
    sigma = a_train.std(axis=0)
    sigma[sigma < 1e-9] = 1.0

    A = (a_train - mu) / sigma
    B = (a_test - mu) / sigma

    A = np.column_stack([np.ones(len(A)), A])
    B = np.column_stack([np.ones(len(B)), B])

    penalty = np.eye(A.shape[1]) * ALPHA
    penalty[0, 0] = 0.0

    coefficients = np.linalg.solve(
        A.T @ A + penalty,
        A.T @ train_y,
    )

    return B @ coefficients


def main():
    for path, expected in HASHES.items():
        if not path.is_file():
            stop(f"Falta {path.name}")
        if digest(path) != expected:
            stop(f"SHA-256 diferente: {path.name}")

    if OUTPUT.exists():
        stop("El informe ya existe. No se sobrescribió.")

    manifest = json.loads(MANIFEST.read_text())
    original = json.loads(ORIGINAL.read_text())

    snapshot_hash = digest(SNAPSHOT)

    if manifest.get("sha256") != snapshot_hash:
        stop("La fotografía no coincide con el manifiesto.")

    if original.get("snapshot_sha256") != snapshot_hash:
        stop("El informe original no corresponde a la fotografía.")

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
    unique = {r["_ts"]: r for r in rows}
    rows = [unique[t] for t in sorted(unique)]

    X, y = [], []

    for i in range(2, len(rows)):
        previous = rows[i - 1]
        values = []

        for field in BASE_FIELDS:
            value = previous.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                break
            values.append(float(value))

        if len(values) != len(BASE_FIELDS):
            continue

        valid = True

        for field in ("hashRate", "hashRate_10m", "hashRate_1h"):
            a = previous.get(field)
            b = rows[i - 2].get(field)

            if (
                isinstance(a, bool) or isinstance(b, bool)
                or not isinstance(a, (int, float))
                or not isinstance(b, (int, float))
                or not math.isfinite(a) or not math.isfinite(b)
            ):
                valid = False
                break

            values.append(float(a) - float(b))

        baseline = previous.get("hashRate_1h")
        target = rows[i]["_target"]

        if (
            not valid
            or isinstance(baseline, bool)
            or not isinstance(baseline, (int, float))
            or not math.isfinite(baseline)
            or not math.isfinite(target)
        ):
            continue

        X.append(values)
        y.append(target)

    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)

    if len(y) != original["usable_samples"]:
        stop("No coincide el conjunto de entrenamiento original.")

    bounds = [
        int(len(y) * p)
        for p in (0.50, 0.60, 0.70, 0.80, 0.90, 1.00)
    ]

    all_actual = []
    full_predictions = []
    baseline_predictions = []
    fold_data = []

    # Primero reproducimos el modelo completo y guardamos sus tramos.
    for fold in range(5):
        start, end = bounds[fold], bounds[fold + 1]

        train_x, train_y = X[:start], y[:start]
        test_x, test_y = X[start:end], y[start:end]

        selected = np.arange(len(FEATURES))
        prediction = fit_predict(
            train_x, train_y, test_x, selected
        )

        baseline = np.asarray([
            float(rows[i - 1]["hashRate_1h"])
            for i in range(2, len(rows))
            if False
        ])

        # La referencia se reconstruye con los mismos índices válidos.
        # Se conserva el orden de las filas utilizables.
        valid_indices = []
        for i in range(2, len(rows)):
            previous = rows[i - 1]
            valid = True

            for field in BASE_FIELDS:
                v = previous.get(field)
                if (
                    isinstance(v, bool)
                    or not isinstance(v, (int, float))
                    or not math.isfinite(v)
                ):
                    valid = False
                    break

            if valid:
                for field in ("hashRate", "hashRate_10m", "hashRate_1h"):
                    a, b = previous.get(field), rows[i - 2].get(field)
                    if (
                        isinstance(a, bool) or isinstance(b, bool)
                        or not isinstance(a, (int, float))
                        or not isinstance(b, (int, float))
                        or not math.isfinite(a) or not math.isfinite(b)
                    ):
                        valid = False
                        break

            ref = previous.get("hashRate_1h")
            if (
                isinstance(ref, bool)
                or not isinstance(ref, (int, float))
                or not math.isfinite(ref)
            ):
                valid = False

            if valid:
                valid_indices.append(i)

        baseline = np.asarray([
            float(rows[i - 1]["hashRate_1h"])
            for i in valid_indices[start:end]
        ])

        fold_data.append((start, end, train_x, train_y, test_x, test_y))
        all_actual.extend(test_y.tolist())
        full_predictions.extend(prediction.tolist())
        baseline_predictions.extend(baseline.tolist())

    if len(all_actual) != EXPECTED_OOS:
        stop(f"Predicciones fuera de muestra: {len(all_actual)}.")

    full_metrics = metrics(all_actual, full_predictions)
    base_metrics = metrics(all_actual, baseline_predictions)

    verify(full_metrics, original["overall"]["ridge"], "Ridge completo")
    verify(
        base_metrics,
        original["overall"]["previous_hashRate_1h"],
        "Referencia 1h",
    )

    # Ablación: quitar exactamente una característica en cada variante.
    results = {}

    for j, feature in enumerate(FEATURES):
        selected = np.asarray([
            k for k in range(len(FEATURES)) if k != j
        ])

        actual_all = []
        predicted_all = []
        constant_folds = []

        for fold, data in enumerate(fold_data):
            start, end, train_x, train_y, test_x, test_y = data

            if np.std(train_x[:, j]) < 1e-9:
                constant_folds.append(fold + 1)

            prediction = fit_predict(
                train_x, train_y, test_x, selected
            )

            actual_all.extend(test_y.tolist())
            predicted_all.extend(prediction.tolist())

        score = metrics(actual_all, predicted_all)

        results[feature] = {
            "without_feature": score,
            "mae_delta_vs_full_ghs": (
                score["mae_ghs"] - full_metrics["mae_ghs"]
            ),
            "rmse_delta_vs_full_ghs": (
                score["rmse_ghs"] - full_metrics["rmse_ghs"]
            ),
            "constant_training_folds": constant_folds,
            "interpretation": (
                "la característica aporta señal incremental"
                if score["mae_ghs"] > full_metrics["mae_ghs"] + 1e-8
                else
                "eliminarla mejora el MAE"
                if score["mae_ghs"] < full_metrics["mae_ghs"] - 1e-8
                else
                "sin diferencia apreciable en MAE"
            ),
        }

    ranked = sorted(
        FEATURES,
        key=lambda f: results[f]["mae_delta_vs_full_ghs"],
        reverse=True,
    )

    report = {
        "title": "TEOS NEURONA — Ablación individual Ridge",
        "snapshot_sha256": snapshot_hash,
        "ridge_alpha": ALPHA,
        "validation": {
            "original_experiment_reproduced": True,
            "oos_predictions": EXPECTED_OOS,
            "five_chronological_folds": True,
            "global_metrics_verified": True,
            "same_targets_all_variants": True,
            "original_files_modified": False,
        },
        "full_model": full_metrics,
        "baseline_1h": base_metrics,
        "feature_ablation": results,
        "ranking_by_contribution_to_mae": ranked,
        "interpretation": (
            "Delta positivo: retirar la característica empeora el MAE; "
            "delta negativo: retirarla mejora el MAE. "
            "Es una medición de contribución incremental condicionada "
            "a las demás características y a alpha=10."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    )

    print("TEOS NEURONA — ABLACIÓN RIDGE")
    print("Integridad y reproducción original: SUPERADAS")
    print("Predicciones comunes:", EXPECTED_OOS)
    print(
        f"Ridge completo MAE: {full_metrics['mae_ghs']:.6f} GH/s"
    )
    print(
        f"Referencia 1h MAE: {base_metrics['mae_ghs']:.6f} GH/s"
    )

    print("\n--- CONTRIBUCIÓN INDIVIDUAL ---")
    for feature in ranked:
        item = results[feature]
        print(
            f"{feature}: "
            f"delta MAE={item['mae_delta_vs_full_ghs']:+.6f} GH/s | "
            f"{item['interpretation']}"
        )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("Modelo original y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
