#!/usr/bin/env python3
"""Validación completa de Ridge reducido con protección de extrapolación."""

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import audit_ridge_residual_conditions_extended as audit
import evaluate_ridge_prospective as ev

OUTPUT = ROOT / "experiments/ridge_protected_predictor_report.json"

FEATURES = (
    "delta_hashRate",
    "delta_hashRate_10m",
    "delta_hashRate_1h",
)

EXPECTED_OUTSIDE = {
    "delta_hashRate": 21,
    "delta_hashRate_10m": 14,
    "delta_hashRate_1h": 66,
}


def stop(message):
    raise SystemExit(f"VALIDACIÓN DETENIDA: {message}")


def metrics(records, prediction_field):
    if not records:
        return {"n": 0}

    actual = np.asarray(
        [r["actual"] for r in records], dtype=float
    )
    predicted = np.asarray(
        [r[prediction_field] for r in records], dtype=float
    )

    residual = predicted - actual
    absolute = np.abs(residual)

    return {
        "n": len(records),
        "mae_ghs": float(np.mean(absolute)),
        "rmse_ghs": float(np.sqrt(np.mean(residual ** 2))),
        "bias_ghs": float(np.mean(residual)),
        "max_abs_error_ghs": float(np.max(absolute)),
    }


def main():
    if OUTPUT.exists():
        stop(f"El informe ya existe: {OUTPUT.name}")

    required = [
        audit.SNAPSHOT, audit.SCRIPT, audit.ORIGINAL,
        audit.CANDIDATE, audit.PROSPECTIVE,
        audit.EVENT_REPORT, ev.MANIFEST, ev.RAW,
    ]

    for path in required:
        if not path.is_file():
            stop(f"Falta {path.name}")

    for path, expected in audit.EXPECTED_HASHES.items():
        if ev.sha256_file(path) != expected:
            stop(f"SHA-256 inesperado: {path.name}")

    frozen, snapshot_hash = ev.load_frozen()

    prospective = json.loads(
        audit.PROSPECTIVE.read_text(encoding="utf-8")
    )
    events = json.loads(
        audit.EVENT_REPORT.read_text(encoding="utf-8")
    )
    manifest = json.loads(
        ev.MANIFEST.read_text(encoding="utf-8")
    )

    if manifest.get("sha256") != snapshot_hash:
        stop("Manifiesto histórico diferente.")

    if prospective["integrity"]["snapshot_sha256"] != snapshot_hash:
        stop("La evaluación prospectiva usa otra fotografía.")

    if events.get("snapshot_sha256") != snapshot_hash:
        stop("El informe de eventos usa otra fotografía.")

    raw_hash = prospective["integrity"]["raw_sha256"]

    if events.get("raw_sha256") != raw_hash:
        stop("Los informes no comparten el mismo prefijo RAW.")

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

    # Reconstrucción del entrenamiento congelado.
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

    if len(train_y) != 844:
        stop("El entrenamiento no coincide con las 844 muestras.")

    # Límites calculados exclusivamente con el entrenamiento congelado.
    limits = {}
    outside_flags = {}

    for name in FEATURES:
        j = ev.FEATURES.index(name)
        values = train_x[:, j]

        limits[name] = {
            "minimum": float(np.min(values)),
            "maximum": float(np.max(values)),
        }

    # Reconstrucción prospectiva.
    stream = [frozen[-2], frozen[-1]] + future
    test_x, records = [], []
    skipped = 0

    event_windows = {
        name: (
            ev.parse_timestamp(window["start"]),
            ev.parse_timestamp(window["end"]),
        )
        for name, window in events["event_windows_utc"].items()
    }

    for i in range(2, len(stream)):
        previous = stream[i - 1]
        earlier = stream[i - 2]
        target = stream[i]

        x = ev.feature_at(previous, earlier)
        actual = target.get("hashRate")
        baseline = previous.get("hashRate_1h")
        interval = (
            target["_dt"] - previous["_dt"]
        ).total_seconds()

        if (
            x is None
            or not ev.valid_number(actual)
            or not ev.valid_number(baseline)
            or interval <= 0
        ):
            skipped += 1
            continue

        test_x.append(x)

        matches = [
            name for name, (start, end) in event_windows.items()
            if start <= target["_dt"] <= end
        ]

        if len(matches) > 1:
            stop("Ventanas de eventos superpuestas.")

        records.append({
            "timestamp": target["_dt"].isoformat(),
            "actual": float(actual),
            "baseline_1h": float(baseline),
            "context": (
                matches[0] if matches
                else "funcionamiento_habitual"
            ),
        })

    test_x = np.asarray(test_x, dtype=float)

    if len(records) != 9922:
        stop(f"Se reconstruyeron {len(records)} pares, no 9922.")

    if skipped != prospective["validation"]["future_pairs_skipped"]:
        stop("No coincide el número de pares omitidos.")

    # Misma configuración de los dos modelos originales.
    full_indices = np.arange(len(ev.FEATURES))
    reduced_indices = np.asarray([
        ev.FEATURES.index(name) for name in ev.REDUCED_FEATURES
    ])

    predictions_original = ev.fit_predict(
        train_x, train_y, test_x, full_indices
    )
    predictions_reduced = ev.fit_predict(
        train_x, train_y, test_x, reduced_indices
    )

    for i, record in enumerate(records):
        record["ridge_original"] = float(predictions_original[i])
        record["ridge_reducido"] = float(predictions_reduced[i])

    # Reproducción de las métricas oficiales.
    global_methods = ev.compare_methods(records)

    for method in audit.METHODS:
        audit.verify_metrics(
            global_methods[method],
            prospective["global"][method],
            method,
        )

    # Aplicar la regla usando únicamente características disponibles antes
    # de conocer el valor real objetivo.
    counts_outside = defaultdict(int)
    policy_counts = defaultdict(int)

    for i, record in enumerate(records):
        outside = []

        for name in FEATURES:
            j = ev.FEATURES.index(name)
            value = float(test_x[i, j])
            low = limits[name]["minimum"]
            high = limits[name]["maximum"]

            if value < low or value > high:
                outside.append(name)
                counts_outside[name] += 1

        record["outside_features"] = outside

        if outside:
            record["ridge_protegido"] = record["baseline_1h"]
            record["selection"] = "referencia_1h"
        else:
            record["ridge_protegido"] = record["ridge_reducido"]
            record["selection"] = "ridge_reducido"

        policy_counts[record["selection"]] += 1

    # Verificar los conteos de extrapolación ya auditados.
    for name, expected in EXPECTED_OUTSIDE.items():
        if counts_outside[name] != expected:
            stop(f"Conteo fuera de rango inesperado: {name}")

    grouped = defaultdict(list)

    for record in records:
        grouped[record["context"]].append(record)

    expected_contexts = {
        "funcionamiento_habitual": 9858,
        "anomalia_telemetria_22_octubre": 61,
        "reinicio_bitaxe_29_octubre": 3,
    }

    for name, expected in expected_contexts.items():
        if len(grouped[name]) != expected:
            stop(
                f"{name}: {len(grouped[name])} muestras; "
                f"esperadas {expected}."
            )

    fields = (
        "ridge_original",
        "ridge_reducido",
        "baseline_1h",
        "ridge_protegido",
    )

    results = {}

    for context, group in {
        "global_todas_las_muestras": records,
        **grouped,
    }.items():
        results[context] = {
            field: metrics(group, field)
            for field in fields
        }

    report = {
        "title": "TEOS NEURONA - Ridge reducido protegido",
        "snapshot_sha256": snapshot_hash,
        "raw_prefix_sha256": raw_hash,
        "validation": {
            "official_metrics_reproduced": True,
            "prospective_pairs": len(records),
            "training_samples": len(train_y),
            "future_data_used_for_training": False,
            "weights_fixed": True,
            "selection_uses_only_previous_information": True,
            "all_observations_preserved": True,
            "original_reports_modified": False,
            "raw_modified": False,
            "bitaxe_modified": False,
        },
        "protection_rule": {
            "features_checked": list(FEATURES),
            "historical_training_ranges": limits,
            "outside_feature_counts": dict(counts_outside),
            "selected_reduced": policy_counts["ridge_reducido"],
            "selected_reference": policy_counts["referencia_1h"],
            "rule": (
                "Ridge reducido si todas las características están "
                "dentro del rango histórico; referencia 1h si alguna "
                "característica está fuera."
            ),
        },
        "results_by_context": results,
        "warning": (
            "Evaluación retrospectiva de una regla definida después "
            "de observar el periodo prospectivo. Requiere confirmación "
            "en un periodo futuro independiente antes de integración."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA - RIDGE PROTEGIDO")
    print("Integridad prospectiva: verificada")
    print("Pares:", len(records))
    print("Entrenamiento:", len(train_y))
    print(
        "Ridge reducido seleccionado:",
        policy_counts["ridge_reducido"],
    )
    print(
        "Referencia seleccionada:",
        policy_counts["referencia_1h"],
    )

    for context, methods in results.items():
        print(f"\n--- {context.upper()} ---")

        for method, item in methods.items():
            print(
                f"{method}: n={item['n']} | "
                f"MAE={item['mae_ghs']:.4f} | "
                f"RMSE={item['rmse_ghs']:.4f} | "
                f"sesgo={item['bias_ghs']:+.4f} GH/s"
            )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("RAW, modelos originales y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
