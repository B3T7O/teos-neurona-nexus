#!/usr/bin/env python3
"""Comparación independiente entre Ridge original y Ridge reducido."""

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
ORIGINAL = ROOT / "experiments/first_learning_model_report.json"
ABLATION = ROOT / "experiments/ridge_feature_ablation_report.json"
STABILITY = ROOT / "experiments/ridge_ablation_fold_stability_report.json"

OUTPUT = ROOT / "experiments/ridge_reduced_candidate_report.json"

EXPECTED_HASHES = {
    SNAPSHOT: "dfdd8f2533d89190e94f5ef113c2a24a43325df1d51c93ad810ff417b53379a5",
    SCRIPT: "b1e1a69fd272c09574a89ac866918889065fab5746ed214b98bdd6eaf8bdab7d",
    ORIGINAL: "835002b3e7720fcbf9c6d0b6ad450a86ff474d01bf5126aaf75c8d8dc9a752ba",
}

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

FEATURES = BASE_FIELDS + [
    "delta_hashRate",
    "delta_hashRate_10m",
    "delta_hashRate_1h",
]

REMOVED_FEATURES = [
    "expectedHashrate",
    "frequency",
    "voltage",
    "fanrpm",
    "errorPercentage",
    "hashRate_10m",
]

REDUCED_FEATURES = [
    feature for feature in FEATURES
    if feature not in REMOVED_FEATURES
]

ALPHA = 10.0
EXPECTED_OOS = 422
TOLERANCE = 1e-10


def stop(message):
    raise SystemExit(f"EVALUACIÓN DETENIDA: {message}")


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
        stop(f"{name}: cantidad de muestras diferente.")

    for key in ("mae_ghs", "rmse_ghs"):
        if not math.isclose(
            current[key],
            reference[key],
            rel_tol=TOLERANCE,
            abs_tol=TOLERANCE,
        ):
            stop(f"{name}: no coincide {key}.")


def fit_predict(train_x, train_y, test_x, selected):
    # El escalado se ajusta exclusivamente con entrenamiento.
    A0 = train_x[:, selected]
    B0 = test_x[:, selected]

    mu = A0.mean(axis=0)
    sigma = A0.std(axis=0)
    sigma[sigma < 1e-9] = 1.0

    A = (A0 - mu) / sigma
    B = (B0 - mu) / sigma

    A = np.column_stack([np.ones(len(A)), A])
    B = np.column_stack([np.ones(len(B)), B])

    # Mismo Ridge alpha=10 e intercepto sin penalización.
    penalty = np.eye(A.shape[1]) * ALPHA
    penalty[0, 0] = 0.0

    coefficients = np.linalg.solve(
        A.T @ A + penalty,
        A.T @ train_y,
    )

    return B @ coefficients


def verify_source_reports(snapshot_hash):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    original = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    ablation = json.loads(ABLATION.read_text(encoding="utf-8"))
    stability = json.loads(STABILITY.read_text(encoding="utf-8"))

    if manifest.get("sha256") != snapshot_hash:
        stop("La fotografía no coincide con el manifiesto.")

    if original.get("snapshot_sha256") != snapshot_hash:
        stop("El informe original utiliza otra fotografía.")

    if ablation.get("snapshot_sha256") != snapshot_hash:
        stop("El informe de ablación utiliza otra fotografía.")

    if stability.get("snapshot_sha256") != snapshot_hash:
        stop("El informe de estabilidad utiliza otra fotografía.")

    if ablation.get("ridge_alpha") != ALPHA:
        stop("Alpha de la ablación diferente.")

    validation = stability.get("validation", {})

    if (
        validation.get("original_model_reproduced") is not True
        or validation.get("all_16_global_ablations_reproduced") is not True
        or validation.get("out_of_sample_predictions") != EXPECTED_OOS
    ):
        stop("La auditoría de estabilidad anterior no está validada.")

    if set(ablation.get("feature_ablation", {})) != set(FEATURES):
        stop("No están disponibles las 16 ablaciones anteriores.")

    return original, ablation, stability


def main():
    required = [
        SNAPSHOT,
        MANIFEST,
        SCRIPT,
        ORIGINAL,
        ABLATION,
        STABILITY,
    ]

    for path in required:
        if not path.is_file():
            stop(f"Falta el archivo: {path.name}")

    if OUTPUT.exists():
        stop(f"El informe ya existe. No se sobrescribió: {OUTPUT.name}")

    # 1. Verificación de integridad.
    for path, expected in EXPECTED_HASHES.items():
        if sha256(path) != expected:
            stop(f"SHA-256 inesperado: {path.name}")

    snapshot_hash = sha256(SNAPSHOT)

    original, ablation, stability = verify_source_reports(snapshot_hash)

    # 2. Reconstrucción exacta de los datos del experimento original.
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

    if len(FEATURES) != X.shape[1]:
        stop("No coincide el número de características.")

    if len(REDUCED_FEATURES) != 10:
        stop("La variante reducida no tiene diez características.")

    full_indices = np.arange(len(FEATURES))
    reduced_indices = np.asarray([
        FEATURES.index(feature) for feature in REDUCED_FEATURES
    ])

    # 3. Cinco tramos cronológicos idénticos.
    bounds = [
        int(len(y) * p)
        for p in (0.50, 0.60, 0.70, 0.80, 0.90, 1.00)
    ]

    folds = []

    all_actual = []
    all_full = []
    all_reduced = []
    all_baseline = []

    for fold in range(5):
        start, end = bounds[fold], bounds[fold + 1]

        if start < 50 or end <= start:
            stop(f"Tramo inválido: {fold + 1}")

        train_x = X[:start]
        train_y = y[:start]
        test_x = X[start:end]
        test_y = y[start:end]

        # Modelo original: 16 características.
        full_prediction = fit_predict(
            train_x, train_y, test_x, full_indices
        )

        # Modelo candidato: 10 características.
        reduced_prediction = fit_predict(
            train_x, train_y, test_x, reduced_indices
        )

        # Referencia 1h, alineada con los mismos objetivos.
        baseline = np.asarray([
            float(rows[int(idx) - 1]["hashRate_1h"])
            for idx in indices[start:end]
        ])

        full_score = metrics(test_y, full_prediction)
        reduced_score = metrics(test_y, reduced_prediction)
        baseline_score = metrics(test_y, baseline)

        # Control de reproducción del Ridge original.
        previous_fold = original["folds"][fold]

        verify_metrics(
            f"Tramo {fold + 1} Ridge original",
            full_score,
            previous_fold["ridge"],
        )

        verify_metrics(
            f"Tramo {fold + 1} referencia 1h",
            baseline_score,
            previous_fold["previous_hashRate_1h"],
        )

        folds.append({
            "fold": fold + 1,
            "train_samples": int(start),
            "test_samples": int(end - start),
            "ridge_original": full_score,
            "ridge_reducido": reduced_score,
            "referencia_1h": baseline_score,
            "mae_delta_reducido_vs_original_ghs": (
                reduced_score["mae_ghs"] - full_score["mae_ghs"]
            ),
            "mae_delta_reducido_vs_referencia_ghs": (
                reduced_score["mae_ghs"] - baseline_score["mae_ghs"]
            ),
            "reducido_supera_original": (
                reduced_score["mae_ghs"] < full_score["mae_ghs"]
            ),
            "reducido_supera_referencia": (
                reduced_score["mae_ghs"] < baseline_score["mae_ghs"]
            ),
        })

        all_actual.extend(test_y.tolist())
        all_full.extend(full_prediction.tolist())
        all_reduced.extend(reduced_prediction.tolist())
        all_baseline.extend(baseline.tolist())

    # 4. Verificación de las 422 predicciones y resultados globales.
    if len(all_actual) != EXPECTED_OOS:
        stop(f"Se esperaban 422 objetivos; obtenidos: {len(all_actual)}.")

    full_global = metrics(all_actual, all_full)
    reduced_global = metrics(all_actual, all_reduced)
    baseline_global = metrics(all_actual, all_baseline)

    verify_metrics(
        "Ridge original global",
        full_global,
        original["overall"]["ridge"],
    )

    verify_metrics(
        "Referencia 1h global",
        baseline_global,
        original["overall"]["previous_hashRate_1h"],
    )

    # 5. Resumen comparativo.
    full_mae = full_global["mae_ghs"]
    reduced_mae = reduced_global["mae_ghs"]
    baseline_mae = baseline_global["mae_ghs"]

    improvement_vs_full_pct = (
        (full_mae - reduced_mae) / full_mae * 100
        if full_mae else None
    )

    improvement_vs_baseline_pct = (
        (baseline_mae - reduced_mae) / baseline_mae * 100
        if baseline_mae else None
    )

    wins_vs_full = sum(
        fold["reducido_supera_original"] for fold in folds
    )

    wins_vs_baseline = sum(
        fold["reducido_supera_referencia"] for fold in folds
    )

    report = {
        "title": "TEOS NEURONA — Evaluación de Ridge reducido",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "integrity": {
            "snapshot_sha256": snapshot_hash,
            "original_script_sha256": sha256(SCRIPT),
            "original_report_sha256": sha256(ORIGINAL),
            "ablation_report_sha256": sha256(ABLATION),
            "fold_stability_report_sha256": sha256(STABILITY),
            "original_files_modified": False,
        },
        "validation": {
            "original_experiment_reproduced": True,
            "out_of_sample_targets": EXPECTED_OOS,
            "five_chronological_folds_verified": True,
            "global_original_metrics_verified": True,
            "same_targets_for_all_three_methods": True,
            "training_scaling_only": True,
            "ridge_alpha": ALPHA,
        },
        "candidate_definition": {
            "original_feature_count": len(FEATURES),
            "reduced_feature_count": len(REDUCED_FEATURES),
            "removed_features": REMOVED_FEATURES,
            "retained_features": REDUCED_FEATURES,
        },
        "global": {
            "ridge_original": full_global,
            "ridge_reducido": reduced_global,
            "referencia_1h": baseline_global,
            "mae_delta_reducido_vs_original_ghs": (
                reduced_mae - full_mae
            ),
            "mae_improvement_reducido_vs_original_pct": (
                improvement_vs_full_pct
            ),
            "mae_delta_reducido_vs_referencia_ghs": (
                reduced_mae - baseline_mae
            ),
            "mae_improvement_reducido_vs_referencia_pct": (
                improvement_vs_baseline_pct
            ),
        },
        "fold_summary": {
            "reduced_beats_original_by_mae": wins_vs_full,
            "total_folds": len(folds),
            "reduced_beats_baseline_by_mae": wins_vs_baseline,
        },
        "folds": folds,
        "conclusion": {
            "reduced_improves_global_mae_vs_original": (
                reduced_mae < full_mae
            ),
            "reduced_beats_original_in_majority_of_folds": (
                wins_vs_full >= 3
            ),
            "reduced_beats_baseline_globally": (
                reduced_mae < baseline_mae
            ),
            "promotion_authorized": False,
        },
        "warning": (
            "Esta variante fue seleccionada tras analizar el mismo "
            "histórico utilizado para evaluarla. El resultado es exploratorio "
            "y no autoriza sustituir el modelo original. Se requiere "
            "validación con datos futuros independientes."
        ),
    }

    # 6. Guardar únicamente el informe nuevo.
    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA — COMPARACIÓN RIDGE REDUCIDO")
    print("Integridad verificada: SUPERADA")
    print("Reproducción del Ridge original: SUPERADA")
    print("Objetivos comunes:", EXPECTED_OOS)

    print("\n--- RESULTADO GLOBAL ---")
    print(f"Ridge original: {full_mae:.6f} GH/s")
    print(f"Ridge reducido: {reduced_mae:.6f} GH/s")
    print(f"Referencia 1h: {baseline_mae:.6f} GH/s")
    print(
        "Mejora reducido frente a original:",
        f"{improvement_vs_full_pct:+.4f}%",
    )
    print(
        "Mejora reducido frente a referencia:",
        f"{improvement_vs_baseline_pct:+.4f}%",
    )

    print("\n--- RESULTADO POR TRAMO ---")
    for fold in folds:
        print(
            f"Tramo {fold['fold']}: "
            f"original={fold['ridge_original']['mae_ghs']:.4f} | "
            f"reducido={fold['ridge_reducido']['mae_ghs']:.4f} | "
            f"referencia={fold['referencia_1h']['mae_ghs']:.4f} GH/s"
        )

    print(
        f"\nEl reducido supera al original en "
        f"{wins_vs_full}/5 tramos."
    )
    print(
        f"El reducido supera a la referencia en "
        f"{wins_vs_baseline}/5 tramos."
    )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("Ridge original, datos congelados y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
