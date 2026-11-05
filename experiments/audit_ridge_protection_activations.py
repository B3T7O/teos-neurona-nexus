#!/usr/bin/env python3
"""Auditoría individual de las activaciones de Ridge protegido."""

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import evaluate_ridge_prospective as ev
import audit_ridge_residual_conditions_extended as audit

OUTPUT = ROOT / "experiments/ridge_protection_activation_audit_report.json"
BATCH_REPORT = ROOT / "experiments/ridge_protected_batch2_report.json"
PROTECTED_REPORT = ROOT / "experiments/ridge_protected_predictor_report.json"

BATCH_START = "2026-10-30T22:49:22.416615+00:00"
BATCH_END = "2026-11-02T17:57:40.379187+00:00"

OUTAGE_START = "2026-11-01T11:39:00+00:00"
OUTAGE_END = "2026-11-01T11:50:36.832364+00:00"

FEATURES = (
    "delta_hashRate",
    "delta_hashRate_10m",
    "delta_hashRate_1h",
)

EXPECTED_PAIRS = 3649
EXPECTED_ACTIVATIONS = 16
EPSILON = 1e-9


def stop(message):
    raise SystemExit(f"AUDITORÍA DETENIDA: {message}")


def main():
    if OUTPUT.exists():
        stop(f"El informe ya existe: {OUTPUT.name}")

    required = [
        audit.SNAPSHOT, audit.SCRIPT, audit.ORIGINAL,
        audit.CANDIDATE, audit.PROSPECTIVE,
        audit.EVENT_REPORT, ev.MANIFEST, ev.RAW,
        BATCH_REPORT, PROTECTED_REPORT,
    ]

    for path in required:
        if not path.is_file():
            stop(f"Falta {path.name}.")

    # Integridad de los archivos históricos congelados.
    for path, expected in audit.EXPECTED_HASHES.items():
        if ev.sha256_file(path) != expected:
            stop(f"SHA-256 inesperado: {path.name}")

    frozen, snapshot_hash = ev.load_frozen()

    batch = json.loads(BATCH_REPORT.read_text(encoding="utf-8"))
    protected = json.loads(
        PROTECTED_REPORT.read_text(encoding="utf-8")
    )
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

    if batch.get("snapshot_sha256") != snapshot_hash:
        stop("El segundo lote utiliza otra fotografía.")

    if protected.get("snapshot_sha256") != snapshot_hash:
        stop("La protección utiliza otra fotografía.")

    if prospective["integrity"]["snapshot_sha256"] != snapshot_hash:
        stop("La evaluación prospectiva utiliza otra fotografía.")

    if events.get("snapshot_sha256") != snapshot_hash:
        stop("El informe de eventos utiliza otra fotografía.")

    if batch.get("batch_start_exclusive_utc") != BATCH_START:
        stop("El inicio del segundo lote no coincide.")

    if batch.get("batch_end_inclusive_utc") != BATCH_END:
        stop("El final del segundo lote no coincide.")

    if batch.get("validation", {}).get(
        "prospective_predictions"
    ) != EXPECTED_PAIRS:
        stop("El informe no contiene las 3649 predicciones.")

    if batch.get("validation", {}).get(
        "protection_activations"
    ) != EXPECTED_ACTIVATIONS:
        stop("El informe no confirma las 16 activaciones.")

    # Recuperar exactamente el prefijo RAW del segundo lote.
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
        stop("No se encontró el último registro del segundo lote.")

    raw_prefix_hash = hashlib.sha256(prefix).hexdigest()

    if batch.get("raw_prefix_sha256") != raw_prefix_hash:
        stop("El prefijo RAW no coincide con el informe del segundo lote.")

    rows = audit.load_prefix_rows(prefix)
    cutoff = frozen[-1]["_dt"]

    historical = [r for r in rows if r["_dt"] <= cutoff]
    future = [r for r in rows if r["_dt"] > cutoff]

    ev.verify_context(frozen, historical)

    # Reconstruir el entrenamiento congelado.
    train_x, train_y = [], []

    for i in range(2, len(frozen)):
        x = ev.feature_at(frozen[i - 1], frozen[i - 2])
        target = frozen[i]["_target"]
        baseline = frozen[i - 1].get("hashRate_1h")

        if (
            x is None
            or not np.isfinite(target)
            or not ev.valid_number(baseline)
        ):
            continue

        train_x.append(x)
        train_y.append(target)

    train_x = np.asarray(train_x, dtype=float)
    train_y = np.asarray(train_y, dtype=float)

    if len(train_y) != 844:
        stop("El entrenamiento congelado no coincide.")

    # Verificar que los límites permanecen exactamente iguales.
    limits = protected["protection_rule"]["historical_training_ranges"]

    for name in FEATURES:
        values = train_x[:, ev.FEATURES.index(name)]

        if (
            float(values.min()) != limits[name]["minimum"]
            or float(values.max()) != limits[name]["maximum"]
        ):
            stop(f"El límite histórico cambió: {name}")

    # Reconstrucción cronológica del segundo lote.
    stream = [frozen[-2], frozen[-1]] + future
    test_x, records = [], []
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
        stop(f"Se reconstruyeron {len(records)} muestras, no 3649.")

    if records[-1]["timestamp"] != BATCH_END:
        stop("El último objetivo no coincide.")

    # Reconstruir Ridge reducido con los mismos 844 registros.
    selected = np.asarray([
        ev.FEATURES.index(name)
        for name in ev.REDUCED_FEATURES
    ])

    reduced_predictions = ev.fit_predict(
        train_x, train_y, test_x, selected
    )

    # Reaplicar la regla congelada y extraer las 16 activaciones.
    activations = []
    feature_counts = Counter()
    outcome_counts = Counter()
    context_counts = defaultdict(Counter)

    for i, record in enumerate(records):
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
                feature_counts[name] += 1

        if not outside:
            continue

        timestamp = ev.parse_timestamp(record["timestamp"])

        context = (
            "apagon_y_recuperacion_1_noviembre"
            if outage_start <= timestamp <= outage_end
            else "funcionamiento_habitual"
        )

        error_reduced = abs(
            record["ridge_reducido"] - record["actual"]
        )
        error_reference = abs(
            record["baseline_1h"] - record["actual"]
        )

        # Positivo = la protección reduce el error.
        # Negativo = la protección aumenta el error.
        benefit = error_reduced - error_reference

        if benefit > EPSILON:
            outcome = "mejoro"
        elif benefit < -EPSILON:
            outcome = "empeoro"
        else:
            outcome = "empate"

        outcome_counts[outcome] += 1
        context_counts[context][outcome] += 1

        activations.append({
            "timestamp": record["timestamp"],
            "context": context,
            "features_outside_range": outside,
            "actual_ghs": record["actual"],
            "ridge_reducido_prediction_ghs": record["ridge_reducido"],
            "reference_1h_prediction_ghs": record["baseline_1h"],
            "ridge_reducido_absolute_error_ghs": error_reduced,
            "reference_1h_absolute_error_ghs": error_reference,
            "benefit_of_protection_ghs": benefit,
            "outcome": outcome,
        })

    if len(activations) != EXPECTED_ACTIVATIONS:
        stop(
            f"Se reconstruyeron {len(activations)} activaciones, "
            f"no 16."
        )

    expected_feature_counts = (
        batch.get("protection_rule", {})
        .get("outside_feature_counts", {})
    )

    for name in FEATURES:
        if feature_counts[name] != expected_feature_counts.get(name, 0):
            stop(f"Conteo de activaciones diferente para {name}.")

    if sum(outcome_counts.values()) != EXPECTED_ACTIVATIONS:
        stop("La clasificación de resultados no conserva las activaciones.")

    # Resumen cuantitativo exclusivo de las activaciones.
    reduced_errors = np.asarray([
        a["ridge_reducido_absolute_error_ghs"]
        for a in activations
    ])
    protected_errors = np.asarray([
        a["reference_1h_absolute_error_ghs"]
        for a in activations
    ])

    summary = {
        "n": len(activations),
        "mejoro": outcome_counts["mejoro"],
        "empeoro": outcome_counts["empeoro"],
        "empato": outcome_counts["empate"],
        "mae_ridge_reducido_ghs": float(np.mean(reduced_errors)),
        "mae_referencia_activaciones_ghs": float(
            np.mean(protected_errors)
        ),
        "beneficio_mae_ghs": float(
            np.mean(reduced_errors - protected_errors)
        ),
        "beneficio_total_error_absoluto_ghs": float(
            np.sum(reduced_errors - protected_errors)
        ),
    }

    by_context = {}

    for context in sorted(context_counts):
        subset = [
            a for a in activations if a["context"] == context
        ]

        by_context[context] = {
            "n": len(subset),
            "mejoro": context_counts[context]["mejoro"],
            "empeoro": context_counts[context]["empeoro"],
            "empato": context_counts[context]["empate"],
            "beneficio_total_ghs": float(sum(
                a["benefit_of_protection_ghs"] for a in subset
            )),
        }

    report = {
        "title": "TEOS NEURONA - Auditoría individual de activaciones",
        "snapshot_sha256": snapshot_hash,
        "raw_prefix_sha256": raw_prefix_hash,
        "batch_start_exclusive_utc": BATCH_START,
        "batch_end_inclusive_utc": BATCH_END,
        "validation": {
            "batch_predictions_reproduced": len(records),
            "activations_reproduced": len(activations),
            "training_samples": len(train_y),
            "fixed_coefficients": True,
            "fixed_historical_limits": True,
            "future_data_used_for_training": False,
            "all_activations_preserved": True,
            "original_reports_modified": False,
            "raw_modified": False,
            "bitaxe_modified": False,
        },
        "definitions": {
            "mejoro": (
                "Error absoluto de Ridge reducido mayor que el de "
                "referencia 1h."
            ),
            "empeoro": (
                "Error absoluto de referencia 1h mayor que el de "
                "Ridge reducido."
            ),
            "benefit_positive": (
                "Error Ridge reducido menos error referencia 1h."
            ),
            "feature_counts": (
                "No necesariamente excluyentes si una muestra activa "
                "más de una característica."
            ),
        },
        "summary": summary,
        "by_context": by_context,
        "feature_activation_counts": dict(feature_counts),
        "individual_activations": activations,
        "raw_invalid_lines_before_batch_end": invalid_lines,
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA - AUDITORÍA DE ACTIVACIONES")
    print("Predicciones reproducidas:", len(records))
    print("Activaciones reproducidas:", len(activations))
    print("Entrenamiento congelado:", len(train_y))

    print("\n--- RESULTADO DE LAS 16 ACTIVACIONES ---")
    print("Protección mejoró:", summary["mejoro"])
    print("Protección empeoró:", summary["empeoro"])
    print("Empates:", summary["empato"])
    print(
        f"MAE Ridge reducido: "
        f"{summary['mae_ridge_reducido_ghs']:.4f} GH/s"
    )
    print(
        f"MAE referencia en activaciones: "
        f"{summary['mae_referencia_activaciones_ghs']:.4f} GH/s"
    )
    print(
        f"Beneficio medio de protección: "
        f"{summary['beneficio_mae_ghs']:+.4f} GH/s"
    )

    print("\n--- DESGLOSE INDIVIDUAL ---")

    for number, item in enumerate(activations, 1):
        print(
            f"{number:02d} | {item['timestamp']} | "
            f"{','.join(item['features_outside_range'])} | "
            f"error Ridge={item['ridge_reducido_absolute_error_ghs']:.3f} | "
            f"error referencia={item['reference_1h_absolute_error_ghs']:.3f} | "
            f"beneficio={item['benefit_of_protection_ghs']:+.3f} GH/s | "
            f"{item['outcome']} | {item['context']}"
        )

    print("\n--- POR CONTEXTO ---")
    for context, item in by_context.items():
        print(
            f"{context}: n={item['n']} | "
            f"mejoró={item['mejoro']} | "
            f"empeoró={item['empeoro']} | "
            f"empató={item['empato']}"
        )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("RAW, modelos, límites e informes anteriores: intactos.")


if __name__ == "__main__":
    main()
