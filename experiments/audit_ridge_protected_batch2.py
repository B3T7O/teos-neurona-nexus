#!/usr/bin/env python3
"""Evaluación definitiva del segundo lote de Ridge protegido."""

import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import evaluate_ridge_prospective as ev
import audit_ridge_residual_conditions_extended as audit

OUTPUT = ROOT / "experiments/ridge_protected_batch2_report.json"

BATCH_START = "2026-10-30T22:49:22.416615+00:00"
BATCH_END = "2026-11-02T17:57:40.379187+00:00"

EXPECTED_PAIRS = 3649
EXPECTED_ACTIVATIONS = 16
EXPECTED_TRAINING = 844

FEATURES = (
    "delta_hashRate",
    "delta_hashRate_10m",
    "delta_hashRate_1h",
)

# Incluye el apagón y la recuperación de las ventanas temporales.
OUTAGE_START = "2026-11-01T11:39:00+00:00"
OUTAGE_END = "2026-11-01T11:50:36.832364+00:00"


def stop(message):
    raise SystemExit(f"EVALUACIÓN DETENIDA: {message}")


def metrics(records, field):
    if not records:
        return {"n": 0}

    actual = np.asarray(
        [r["actual"] for r in records], dtype=float
    )
    predicted = np.asarray(
        [r[field] for r in records], dtype=float
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
        audit.SNAPSHOT,
        audit.SCRIPT,
        audit.ORIGINAL,
        audit.CANDIDATE,
        audit.PROSPECTIVE,
        audit.EVENT_REPORT,
        ev.MANIFEST,
        ev.RAW,
    ]

    for path in required:
        if not path.is_file():
            stop(f"Falta el archivo {path.name}.")

    # Integridad del experimento histórico congelado.
    for path, expected in audit.EXPECTED_HASHES.items():
        if ev.sha256_file(path) != expected:
            stop(f"SHA-256 inesperado: {path.name}")

    frozen, snapshot_hash = ev.load_frozen()

    manifest = json.loads(
        ev.MANIFEST.read_text(encoding="utf-8")
    )
    prospective = json.loads(
        audit.PROSPECTIVE.read_text(encoding="utf-8")
    )
    candidate = json.loads(
        audit.CANDIDATE.read_text(encoding="utf-8")
    )
    protected = json.loads(
        (ROOT / "experiments/ridge_protected_predictor_report.json")
        .read_text(encoding="utf-8")
    )

    if manifest.get("sha256") != snapshot_hash:
        stop("Manifiesto histórico diferente.")

    if prospective["integrity"]["snapshot_sha256"] != snapshot_hash:
        stop("Evaluación prospectiva histórica diferente.")

    if candidate["integrity"]["snapshot_sha256"] != snapshot_hash:
        stop("Candidato reducido diferente.")

    if protected.get("snapshot_sha256") != snapshot_hash:
        stop("Protección histórica diferente.")

    if len(frozen) != 846:
        stop("La fotografía no contiene los 846 registros esperados.")

    # Recuperar el RAW exactamente hasta el último objetivo del lote.
    end_dt = ev.parse_timestamp(BATCH_END)
    start_dt = ev.parse_timestamp(BATCH_START)

    raw_data = ev.RAW.read_bytes()
    offset = 0
    prefix = None
    invalid_lines = 0

    for line in raw_data.splitlines(keepends=True):
        offset += len(line)

        try:
            row = json.loads(line)
            timestamp = ev.parse_timestamp(row.get("timestamp"))
        except (ValueError, TypeError, json.JSONDecodeError):
            invalid_lines += 1
            continue

        if timestamp == end_dt:
            prefix = raw_data[:offset]
            break

    if prefix is None:
        stop("No se encontró el último registro del lote.")

    raw_prefix_hash = hashlib.sha256(prefix).hexdigest()
    rows = audit.load_prefix_rows(prefix)

    cutoff = frozen[-1]["_dt"]
    historical = [r for r in rows if r["_dt"] <= cutoff]
    future = [r for r in rows if r["_dt"] > cutoff]

    ev.verify_context(frozen, historical)

    if not future:
        stop("No existen muestras futuras.")

    # Reproducir exactamente las 844 muestras de entrenamiento.
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

    if len(train_y) != EXPECTED_TRAINING:
        stop("No coinciden las 844 muestras históricas.")

    # Verificar que los límites de protección siguen congelados.
    saved_limits = protected["protection_rule"]["historical_training_ranges"]
    limits = {}

    for name in FEATURES:
        values = train_x[:, ev.FEATURES.index(name)]
        minimum = float(np.min(values))
        maximum = float(np.max(values))

        if (
            minimum != saved_limits[name]["minimum"]
            or maximum != saved_limits[name]["maximum"]
        ):
            stop(f"Ha cambiado el límite histórico de {name}.")

        limits[name] = {
            "minimum": minimum,
            "maximum": maximum,
        }

    # El lote comienza después del primer periodo prospectivo de 180.
    stream = [frozen[-2], frozen[-1]] + future

    test_x = []
    records = []
    skipped = 0

    outage_start = ev.parse_timestamp(OUTAGE_START)
    outage_end = ev.parse_timestamp(OUTAGE_END)

    for i in range(2, len(stream)):
        previous = stream[i - 1]
        earlier = stream[i - 2]
        target = stream[i]

        timestamp = target["_dt"]

        if timestamp <= start_dt:
            continue

        x = ev.feature_at(previous, earlier)
        actual = target.get("hashRate")
        baseline = previous.get("hashRate_1h")
        interval = (
            timestamp - previous["_dt"]
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

        records.append({
            "timestamp": timestamp.isoformat(),
            "actual": float(actual),
            "baseline_1h": float(baseline),
            "interval_seconds": float(interval),
        })

    test_x = np.asarray(test_x, dtype=float)

    if len(records) != EXPECTED_PAIRS:
        stop(
            f"Se obtuvieron {len(records)} predicciones; "
            f"se esperaban {EXPECTED_PAIRS}."
        )

    if (
        records[0]["timestamp"] != "2026-10-30T22:50:29.508862+00:00"
        or records[-1]["timestamp"] != BATCH_END
    ):
        stop("Los límites temporales del lote no coinciden.")

    # Ajustes únicos con los 844 registros congelados.
    full_indices = np.arange(len(ev.FEATURES))
    reduced_indices = np.asarray([
        ev.FEATURES.index(name) for name in ev.REDUCED_FEATURES
    ])

    original_predictions = ev.fit_predict(
        train_x, train_y, test_x, full_indices
    )

    reduced_predictions = ev.fit_predict(
        train_x, train_y, test_x, reduced_indices
    )

    # Aplicar los límites congelados sin mirar el objetivo futuro.
    outside_counts = defaultdict(int)
    route_counts = defaultdict(int)

    for i, record in enumerate(records):
        record["ridge_original"] = float(original_predictions[i])
        record["ridge_reducido"] = float(reduced_predictions[i])

        outside = []

        for name in FEATURES:
            j = ev.FEATURES.index(name)
            value = float(test_x[i, j])

            if (
                value < limits[name]["minimum"]
                or value > limits[name]["maximum"]
            ):
                outside.append(name)
                outside_counts[name] += 1

        record["outside_features"] = outside

        if outside:
            record["ridge_protegido"] = record["baseline_1h"]
            record["route"] = "referencia_1h"
        else:
            record["ridge_protegido"] = record["ridge_reducido"]
            record["route"] = "ridge_reducido"

        route_counts[record["route"]] += 1

        timestamp = ev.parse_timestamp(record["timestamp"])

        if outage_start <= timestamp <= outage_end:
            record["context"] = "apagon_y_recuperacion_1_noviembre"
        else:
            record["context"] = "funcionamiento_habitual"

    activation_count = route_counts["referencia_1h"]

    if activation_count != EXPECTED_ACTIVATIONS:
        stop(
            f"Se reprodujeron {activation_count} activaciones; "
            f"el control anterior declaró {EXPECTED_ACTIVATIONS}."
        )

    if sum(route_counts.values()) != EXPECTED_PAIRS:
        stop("La selección no conserva las 3649 observaciones.")

    # Verificar que no se ha alterado ningún objetivo.
    if any(r["actual"] is None for r in records):
        stop("Existen objetivos inválidos.")

    fields = (
        "ridge_original",
        "ridge_reducido",
        "baseline_1h",
        "ridge_protegido",
    )

    grouped = defaultdict(list)

    for record in records:
        grouped[record["context"]].append(record)

    expected_context_total = sum(map(len, grouped.values()))

    if expected_context_total != EXPECTED_PAIRS:
        stop("La clasificación operativa perdió observaciones.")

    results = {
        "global_todas_las_muestras": {
            field: metrics(records, field) for field in fields
        },
        "by_operational_context": {
            context: {
                field: metrics(group, field) for field in fields
            }
            for context, group in grouped.items()
        },
    }

    report = {
        "title": "TEOS NEURONA - Segunda validación prospectiva Ridge protegido",
        "snapshot_sha256": snapshot_hash,
        "raw_prefix_sha256": raw_prefix_hash,
        "batch_start_exclusive_utc": BATCH_START,
        "batch_end_inclusive_utc": BATCH_END,
        "validation": {
            "prospective_predictions": len(records),
            "training_samples": len(train_y),
            "protection_activations": activation_count,
            "activation_target": EXPECTED_ACTIVATIONS,
            "fixed_training": True,
            "fixed_coefficients": True,
            "fixed_historical_limits": True,
            "future_data_used_for_training": False,
            "selection_uses_only_prior_features": True,
            "all_observations_preserved": True,
            "original_reports_modified": False,
            "raw_modified": False,
            "bitaxe_modified": False,
        },
        "protection_rule": {
            "features": list(FEATURES),
            "historical_training_ranges": limits,
            "outside_feature_counts": dict(outside_counts),
            "route_counts": dict(route_counts),
        },
        "outage_window_utc": {
            "start": OUTAGE_START,
            "end": OUTAGE_END,
            "description": (
                "Apagón del 1 de noviembre y recuperación inicial "
                "de las ventanas temporales."
            ),
        },
        "metrics": results,
        "raw_invalid_lines_before_batch_end": invalid_lines,
        "warning": (
            "Esta evaluación es prospectiva respecto del primer lote, "
            "pero el intervalo incluye un apagón. Se informan por separado "
            "el funcionamiento habitual y la recuperación del evento."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA - SEGUNDA VALIDACIÓN PROSPECTIVA")
    print("Predicciones:", len(records))
    print("Entrenamiento congelado:", len(train_y))
    print("Activaciones reproducidas:", activation_count)
    print("Límites recalculados: NO")
    print("Reentrenamiento futuro: NO")

    print("\n--- RESULTADOS GLOBALES ---")

    for field in fields:
        item = results["global_todas_las_muestras"][field]
        print(
            f"{field}: MAE={item['mae_ghs']:.4f} | "
            f"RMSE={item['rmse_ghs']:.4f} | "
            f"sesgo={item['bias_ghs']:+.4f} GH/s"
        )

    print("\n--- CONTEXTOS OPERATIVOS ---")

    for context, methods in results["by_operational_context"].items():
        print(f"\n{context}: n={methods['ridge_protegido']['n']}")

        for field in fields:
            item = methods[field]
            print(
                f"{field}: MAE={item['mae_ghs']:.4f} | "
                f"RMSE={item['rmse_ghs']:.4f} | "
                f"sesgo={item['bias_ghs']:+.4f} GH/s"
            )

    print("\n--- ACTIVACIONES POR CARACTERÍSTICA ---")
    for name, count in outside_counts.items():
        print(f"{name}: {count}")

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("RAW, modelos, límites históricos y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
