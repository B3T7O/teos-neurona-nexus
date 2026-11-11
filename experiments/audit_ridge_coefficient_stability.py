#!/usr/bin/env python3
"""Auditoría independiente de estabilidad de coeficientes Ridge."""

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

SNAPSHOT = ROOT / "experiments/frozen_bitaxe_samples.marked.jsonl"
MANIFEST = ROOT / "experiments/frozen_evaluation_manifest.json"
SCRIPT = ROOT / "experiments/first_learning_model.py"
ORIGINAL_REPORT = ROOT / "experiments/first_learning_model_report.json"
OUTPUT = ROOT / "experiments/ridge_coefficient_stability_report.json"

HASHES = {
    SNAPSHOT: "dfdd8f2533d89190e94f5ef113c2a24a43325df1d51c93ad810ff417b53379a5",
    SCRIPT: "b1e1a69fd272c09574a89ac866918889065fab5746ed214b98bdd6eaf8bdab7d",
    ORIGINAL_REPORT: "835002b3e7720fcbf9c6d0b6ad450a86ff474d01bf5126aaf75c8d8dc9a752ba",
}

EXPECTED_OOS = 422
ALPHA = 10.0
SIGN_EPSILON = 1e-8
CORRELATION_THRESHOLD = 0.90
TOLERANCE = 1e-10

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


def stop(message):
    raise SystemExit(f"AUDITORÍA DETENIDA: {message}")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    error = actual - predicted

    return {
        "n": int(len(actual)),
        "mae_ghs": float(np.mean(np.abs(error))),
        "rmse_ghs": float(np.sqrt(np.mean(error ** 2))),
    }


def verify_metrics(name, new, original):
    if new["n"] != original["n"]:
        stop(f"{name}: número de muestras diferente.")

    for field in ("mae_ghs", "rmse_ghs"):
        if not math.isclose(
            new[field],
            original[field],
            rel_tol=TOLERANCE,
            abs_tol=TOLERANCE,
        ):
            stop(f"{name}: diferencia en {field}.")


def sign(value):
    if value > SIGN_EPSILON:
        return "positivo"
    if value < -SIGN_EPSILON:
        return "negativo"
    return "cercano_a_cero"


def analyze_correlations(X, names):
    corr = np.corrcoef(X, rowvar=False)
    pairs = []

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            value = corr[i, j]

            if (
                math.isfinite(float(value))
                and abs(value) >= CORRELATION_THRESHOLD
            ):
                pairs.append({
                    "feature_a": names[i],
                    "feature_b": names[j],
                    "correlation": float(value),
                })

    return sorted(
        pairs,
        key=lambda item: abs(item["correlation"]),
        reverse=True,
    )


def main():
    for path, expected in HASHES.items():
        if not path.is_file():
            stop(f"Falta {path.relative_to(ROOT)}")
        if digest(path) != expected:
            stop(f"SHA-256 inesperado: {path.name}")

    if OUTPUT.exists():
        stop(f"El informe ya existe; no se sobrescribió: {OUTPUT.name}")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    original = json.loads(
        ORIGINAL_REPORT.read_text(encoding="utf-8")
    )

    snapshot_hash = digest(SNAPSHOT)

    if manifest.get("sha256") != snapshot_hash:
        stop("La fotografía no coincide con el manifiesto.")

    if original.get("snapshot_sha256") != snapshot_hash:
        stop("El informe original no corresponde a la fotografía.")

    # Reconstrucción idéntica al experimento Ridge original.
    rows = []

    for line in SNAPSHOT.read_bytes().splitlines():
        try:
            row = json.loads(line)
            row["_ts"] = row["timestamp"]
            row["_target"] = float(row["hashRate"])
            rows.append(row)
        except (
            ValueError, TypeError, KeyError, json.JSONDecodeError
        ):
            continue

    rows.sort(key=lambda r: r["_ts"])

    unique = {}
    for row in rows:
        unique[row["_ts"]] = row

    rows = [unique[t] for t in sorted(unique)]

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

    if len(y) != original.get("usable_samples"):
        stop("No coincide el número de muestras utilizables.")

    # Los cinco tramos y el entrenamiento son idénticos al original.
    bounds = [
        int(len(y) * p)
        for p in (0.50, 0.60, 0.70, 0.80, 0.90, 1.00)
    ]

    folds = []
    all_actual, all_ridge, all_baseline = [], [], []
    oos_count = 0

    for fold in range(5):
        start, end = bounds[fold], bounds[fold + 1]
        train_end = start

        X_train = X[:train_end]
        y_train = y[:train_end]
        X_test = X[start:end]
        y_test = y[start:end]

        mu = X_train.mean(axis=0)
        sigma = X_train.std(axis=0)
        sigma[sigma < 1e-9] = 1.0

        A = (X_train - mu) / sigma
        B = (X_test - mu) / sigma

        A = np.column_stack([np.ones(len(A)), A])
        B = np.column_stack([np.ones(len(B)), B])

        penalty = np.eye(A.shape[1]) * ALPHA
        penalty[0, 0] = 0.0

        coefficients = np.linalg.solve(
            A.T @ A + penalty,
            A.T @ y_train,
        )

        predictions = B @ coefficients

        baseline = np.asarray([
            float(rows[int(idx) - 1]["hashRate_1h"])
            for idx in indices[start:end]
        ])

        ridge_score = metrics(y_test, predictions)
        baseline_score = metrics(y_test, baseline)

        # Coeficientes principales: efecto por una desviación
        # estándar de cada característica dentro del entrenamiento.
        standardized = coefficients[1:]
        raw_units = standardized / sigma

        total_abs = float(np.sum(np.abs(standardized)))

        feature_coefficients = {}

        for j, name in enumerate(FEATURES):
            feature_coefficients[name] = {
                "standardized_beta": float(standardized[j]),
                "raw_unit_beta": float(raw_units[j]),
                "sign": sign(float(standardized[j])),
                "absolute_importance_share_pct": (
                    float(abs(standardized[j]) / total_abs * 100)
                    if total_abs > 0 else 0.0
                ),
            }

        correlations = analyze_correlations(X_train, FEATURES)

        folds.append({
            "fold": fold + 1,
            "train_samples": int(train_end),
            "test_samples": int(end - start),
            "ridge_metrics": ridge_score,
            "baseline_1h_metrics": baseline_score,
            "intercept_standardized_model": float(coefficients[0]),
            "coefficients": feature_coefficients,
            "high_correlations_training_only": correlations,
        })

        all_actual.extend(y_test.tolist())
        all_ridge.extend(predictions.tolist())
        all_baseline.extend(baseline.tolist())
        oos_count += len(y_test)

    if oos_count != EXPECTED_OOS:
        stop(f"Se esperaban 422 predicciones y se obtuvieron {oos_count}.")

    # Validar que la reconstrucción reproduce el experimento original.
    if len(original["folds"]) != 5:
        stop("El informe original no contiene cinco tramos.")

    for new, old in zip(folds, original["folds"]):
        verify_metrics(
            f"Tramo {new['fold']} Ridge",
            new["ridge_metrics"],
            old["ridge"],
        )
        verify_metrics(
            f"Tramo {new['fold']} referencia 1h",
            new["baseline_1h_metrics"],
            old["previous_hashRate_1h"],
        )

    overall_ridge = metrics(all_actual, all_ridge)
    overall_baseline = metrics(all_actual, all_baseline)

    verify_metrics(
        "Global Ridge",
        overall_ridge,
        original["overall"]["ridge"],
    )
    verify_metrics(
        "Global referencia 1h",
        overall_baseline,
        original["overall"]["previous_hashRate_1h"],
    )

    # Resumen cronológico de estabilidad de cada coeficiente.
    stability = {}

    for name in FEATURES:
        values = [
            fold["coefficients"][name]["standardized_beta"]
            for fold in folds
        ]

        signs = [sign(value) for value in values]

        positive = signs.count("positivo")
        negative = signs.count("negativo")
        near_zero = signs.count("cercano_a_cero")

        changes = sum(
            1
            for a, b in zip(signs, signs[1:])
            if a != b
        )

        mean_beta = float(np.mean(values))
        std_beta = float(np.std(values))

        if positive == 5 or negative == 5:
            classification = "signo_consistente"
        elif positive > 0 and negative > 0:
            classification = "cambio_de_signo"
        elif near_zero > 0:
            classification = "incluye_coeficiente_cercano_a_cero"
        else:
            classification = "sin_clasificacion"

        importance = [
            fold["coefficients"][name]["absolute_importance_share_pct"]
            for fold in folds
        ]

        stability[name] = {
            "classification": classification,
            "signs_by_fold": signs,
            "positive_folds": positive,
            "negative_folds": negative,
            "near_zero_folds": near_zero,
            "chronological_sign_changes": changes,
            "same_nonzero_sign_in_all_folds": (
                positive == 5 or negative == 5
            ),
            "mean_standardized_beta": mean_beta,
            "std_standardized_beta": std_beta,
            "min_standardized_beta": float(min(values)),
            "max_standardized_beta": float(max(values)),
            "magnitude_variation_pct": (
                std_beta / abs(mean_beta) * 100
                if abs(mean_beta) > SIGN_EPSILON else None
            ),
            "mean_absolute_importance_share_pct": float(
                np.mean(importance)
            ),
        }

    ranked = sorted(
        FEATURES,
        key=lambda name: stability[name][
            "mean_absolute_importance_share_pct"
        ],
        reverse=True,
    )

    report = {
        "title": "TEOS NEURONA — Estabilidad de coeficientes Ridge",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "integrity": {
            "snapshot_sha256": snapshot_hash,
            "original_script_sha256": digest(SCRIPT),
            "original_report_sha256": digest(ORIGINAL_REPORT),
            "original_files_modified": False,
        },
        "validation": {
            "original_experiment_reproduced": True,
            "out_of_sample_predictions": oos_count,
            "five_folds_verified": True,
            "global_metrics_verified": True,
            "ridge_alpha": ALPHA,
        },
        "methodology": {
            "feature_count": len(FEATURES),
            "features": FEATURES,
            "coefficient_units": (
                "GH/s por una desviación estándar de la característica "
                "en el conjunto de entrenamiento del tramo."
            ),
            "raw_unit_beta": (
                "Coeficiente expresado por unidad original de cada variable."
            ),
            "importance_share": (
                "Porcentaje de valor absoluto del coeficiente estandarizado "
                "respecto a la suma de valores absolutos del tramo."
            ),
            "near_zero_threshold": SIGN_EPSILON,
            "high_correlation_threshold": CORRELATION_THRESHOLD,
        },
        "overall_metrics": {
            "ridge": overall_ridge,
            "previous_hashRate_1h": overall_baseline,
        },
        "folds": folds,
        "coefficient_stability": stability,
        "ranking_by_mean_absolute_importance": ranked,
        "interpretation_warning": (
            "Los coeficientes representan asociaciones condicionadas "
            "a las demás características, no causalidad. La multicolinealidad "
            "puede redistribuir pesos entre variables correlacionadas. "
            "La importancia relativa no demuestra capacidad predictiva "
            "individual ni superioridad frente a la referencia."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA — ESTABILIDAD DE COEFICIENTES RIDGE")
    print("Integridad de archivos: verificada")
    print("Reproducción original: SUPERADA")
    print("Predicciones verificadas:", oos_count)
    print("Cinco tramos: verificados")

    print("\n--- ESTABILIDAD POR CARACTERÍSTICA ---")
    for name in FEATURES:
        item = stability[name]
        print(
            f"{name}: {item['classification']} | "
            f"signos={','.join(item['signs_by_fold'])} | "
            f"beta medio={item['mean_standardized_beta']:+.5f} | "
            f"variación={item['magnitude_variation_pct']}"
        )

    print("\n--- MAYOR IMPORTANCIA RELATIVA MEDIA ---")
    for name in ranked[:8]:
        value = stability[name]["mean_absolute_importance_share_pct"]
        print(f"{name}: {value:.2f}%")

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("Predictor original, datos y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
