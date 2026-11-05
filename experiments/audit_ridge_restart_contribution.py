#!/usr/bin/env python3
"""Descomposición matemática de la predicción anómala tras el reinicio."""

import json
import math
from pathlib import Path

import numpy as np

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import evaluate_ridge_prospective as ev
import audit_ridge_residual_conditions as audit

TARGET_UTC = "2026-10-29T02:10:01.696459+00:00"
EXPECTED_PREDICTION = 3453.7795

OUTPUT = ROOT / "experiments/ridge_restart_contribution_report.json"
CANDIDATE = ROOT / "experiments/ridge_reduced_candidate_report.json"
ORIGINAL = ROOT / "experiments/first_learning_model_report.json"
PROSPECTIVE = ROOT / "experiments/ridge_prospective_report.json"

def stop(message):
    raise SystemExit(f"AUDITORÍA DETENIDA: {message}")


def main():
    if OUTPUT.exists():
        stop(f"El informe ya existe: {OUTPUT.name}")

    for path, expected in ev.EXPECTED_HASHES.items():
        if ev.sha256_file(path) != expected:
            stop(f"Integridad incorrecta: {path.name}")

    frozen, snapshot_hash = ev.load_frozen()

    original = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    prospective = json.loads(PROSPECTIVE.read_text(encoding="utf-8"))
    manifest = json.loads(ev.MANIFEST.read_text(encoding="utf-8"))

    if manifest.get("sha256") != snapshot_hash:
        stop("Manifiesto histórico diferente.")

    if candidate.get("integrity", {}).get(
        "snapshot_sha256"
    ) != snapshot_hash:
        stop("El candidato no corresponde al histórico congelado.")

    if prospective["integrity"]["snapshot_sha256"] != snapshot_hash:
        stop("Evaluación prospectiva diferente.")

    # Recuperar exactamente el prefijo RAW original.
    raw_hash = prospective["integrity"]["raw_sha256"]
    last_target = ev.parse_timestamp(
        prospective["evaluation_period_utc"]["last_target"]
    )

    prefix = audit.recover_original_prefix(raw_hash, last_target)
    rows = audit.load_prefix_rows(prefix)

    cutoff = frozen[-1]["_dt"]
    historical = [r for r in rows if r["_dt"] <= cutoff]
    future = [r for r in rows if r["_dt"] > cutoff]

    ev.verify_context(frozen, historical)

    if len(future) != prospective["validation"]["future_raw_rows"]:
        stop("Cantidad de muestras futuras diferente.")

    # Reconstruir exactamente las 844 muestras originales.
    train_x, train_y = [], []

    for i in range(2, len(frozen)):
        x = ev.feature_at(frozen[i - 1], frozen[i - 2])
        target = frozen[i]["_target"]
        baseline = frozen[i - 1].get("hashRate_1h")

        if (
            x is None
            or not math.isfinite(target)
            or not ev.valid_number(baseline)
        ):
            continue

        train_x.append(x)
        train_y.append(target)

    train_x = np.asarray(train_x, dtype=float)
    train_y = np.asarray(train_y, dtype=float)

    if len(train_y) != original["usable_samples"]:
        stop("No se reprodujo el entrenamiento original.")

    if len(train_y) != 844:
        stop("Se esperaba exactamente 844 muestras.")

    # Localizar el objetivo y sus dos muestras de contexto.
    target_dt = ev.parse_timestamp(TARGET_UTC)
    stream = [frozen[-2], frozen[-1]] + future

    indexes = [
        i for i, row in enumerate(stream)
        if row["_dt"] == target_dt
    ]

    if len(indexes) != 1 or indexes[0] < 2:
        stop("No se encontró el objetivo o su contexto temporal.")

    index = indexes[0]
    earlier = stream[index - 2]
    previous = stream[index - 1]
    target = stream[index]

    x = ev.feature_at(previous, earlier)

    if x is None:
        stop("Características temporales inválidas.")

    # Reproducir el ajuste Ridge reducido, sin datos futuros.
    selected = np.asarray([
        ev.FEATURES.index(name)
        for name in ev.REDUCED_FEATURES
    ])

    A0 = train_x[:, selected]
    x0 = x[selected]

    mu = A0.mean(axis=0)
    sigma = A0.std(axis=0)
    sigma[sigma < 1e-9] = 1.0

    A = (A0 - mu) / sigma
    z = (x0 - mu) / sigma

    A = np.column_stack([np.ones(len(A)), A])

    penalty = np.eye(A.shape[1]) * ev.ALPHA
    penalty[0, 0] = 0.0

    coefficients = np.linalg.solve(
        A.T @ A + penalty,
        A.T @ train_y,
    )

    prediction = float(
        coefficients[0] + np.dot(z, coefficients[1:])
    )

    if not math.isclose(
        prediction, EXPECTED_PREDICTION,
        rel_tol=1e-6, abs_tol=0.01
    ):
        stop(
            f"Predicción reconstruida {prediction:.6f} "
            "no coincide con la inspección anterior."
        )

    contributions = []

    for i, name in enumerate(ev.REDUCED_FEATURES):
        contributions.append({
            "feature": name,
            "input_value": float(x0[i]),
            "training_mean": float(mu[i]),
            "training_std": float(sigma[i]),
            "standardized_value": float(z[i]),
            "standardized_coefficient": float(coefficients[i + 1]),
            "prediction_contribution_ghs": float(
                z[i] * coefficients[i + 1]
            ),
        })

    contributions.sort(
        key=lambda item: abs(item["prediction_contribution_ghs"]),
        reverse=True,
    )

    delta_names = {
        "delta_hashRate",
        "delta_hashRate_10m",
        "delta_hashRate_1h",
    }

    delta_contribution = sum(
        item["prediction_contribution_ghs"]
        for item in contributions
        if item["feature"] in delta_names
    )

    report = {
        "title": "TEOS NEURONA - Contribución del reinicio a Ridge",
        "snapshot_sha256": snapshot_hash,
        "raw_prefix_sha256": raw_hash,
        "validation": {
            "frozen_training_samples": len(train_y),
            "original_prediction_reproduced": True,
            "future_data_used_for_training": False,
            "model_weights_fixed": True,
            "original_files_modified": False,
            "bitaxe_modified": False,
        },
        "target_utc": TARGET_UTC,
        "context": {
            "earlier_timestamp": earlier["_dt"].isoformat(),
            "previous_timestamp": previous["_dt"].isoformat(),
            "target_actual_ghs": float(target["hashRate"]),
            "previous_baseline_1h_ghs": float(previous["hashRate_1h"]),
            "earlier_hashrate_ghs": float(earlier["hashRate"]),
            "previous_hashrate_ghs": float(previous["hashRate"]),
        },
        "ridge_reduced": {
            "prediction_ghs": prediction,
            "intercept_ghs": float(coefficients[0]),
            "actual_ghs": float(target["hashRate"]),
            "baseline_1h_ghs": float(previous["hashRate_1h"]),
            "residual_ghs": prediction - float(target["hashRate"]),
            "delta_features_total_contribution_ghs": float(
                delta_contribution
            ),
            "prediction_after_removing_delta_contributions_ghs": float(
                prediction - delta_contribution
            ),
            "feature_contributions": contributions,
        },
        "warning": (
            "La retirada aritmética de contribuciones es una "
            "descomposición del modelo, no una nueva predicción "
            "ni una propuesta de modificación."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA - CONTRIBUCIÓN DEL REINICIO")
    print("Entrenamiento congelado:", len(train_y))
    print(f"Predicción reproducida: {prediction:.4f} GH/s")
    print(f"Hashrate real: {target['hashRate']:.4f} GH/s")
    print(f"Referencia 1h: {previous['hashRate_1h']:.4f} GH/s")
    print(
        "Contribución conjunta de las tres diferencias:",
        f"{delta_contribution:+.4f} GH/s",
    )

    print("\n--- CONTRIBUCIONES POR CARACTERÍSTICA ---")

    for item in contributions:
        print(
            f"{item['feature']}: "
            f"entrada={item['input_value']:+.4f} | "
            f"z={item['standardized_value']:+.4f} | "
            f"aporte={item['prediction_contribution_ghs']:+.4f} GH/s"
        )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("Modelos, histórico RAW y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
