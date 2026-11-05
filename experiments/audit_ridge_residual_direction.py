#!/usr/bin/env python3
"""Auditoría direccional de residuos Ridge."""

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import audit_ridge_residual_conditions as audit

ev = audit.ev
OUTPUT = ROOT / "experiments/ridge_residual_direction_report.json"
PRIOR = ROOT / "experiments/ridge_residual_conditions_report.json"
EPSILON = 1e-9

DIRECTIONS = ("subida", "bajada", "sin_cambio")
CLASSES = audit.CHANGE_CLASSES


def stop(message):
    raise SystemExit(f"AUDITORÍA DETENIDA: {message}")


def main():
    required = [
        PRIOR, audit.SNAPSHOT, audit.SCRIPT, audit.ORIGINAL,
        audit.CANDIDATE, audit.PROSPECTIVE, audit.EVENT_REPORT,
        ev.MANIFEST, ev.RAW,
    ]

    for path in required:
        if not path.is_file():
            stop(f"Falta {path.name}")

    if OUTPUT.exists():
        stop(f"El informe ya existe; no se sobrescribió: {OUTPUT.name}")

    # Integridad de los archivos congelados.
    for path, expected in audit.EXPECTED_HASHES.items():
        if ev.sha256_file(path) != expected:
            stop(f"SHA-256 inesperado: {path.name}")

    frozen, snapshot_hash = ev.load_frozen()

    prior = json.loads(PRIOR.read_text(encoding="utf-8"))
    prospective = json.loads(audit.PROSPECTIVE.read_text(encoding="utf-8"))
    events = json.loads(audit.EVENT_REPORT.read_text(encoding="utf-8"))
    manifest = json.loads(ev.MANIFEST.read_text(encoding="utf-8"))
    original = json.loads(audit.ORIGINAL.read_text(encoding="utf-8"))

    if prior.get("snapshot_sha256") != snapshot_hash:
        stop("El diagnóstico anterior usa otra fotografía histórica.")

    if prior.get("validation", {}).get(
        "official_prospective_metrics_reproduced"
    ) is not True:
        stop("El diagnóstico anterior no está validado.")

    if manifest.get("sha256") != snapshot_hash:
        stop("La fotografía no coincide con el manifiesto.")

    if prospective["integrity"]["snapshot_sha256"] != snapshot_hash:
        stop("La evaluación prospectiva usa otra fotografía.")

    raw_hash = prospective["integrity"]["raw_sha256"]

    if prior.get("raw_prefix_sha256") != raw_hash:
        stop("El diagnóstico anterior usa otro prefijo RAW.")

    if events.get("raw_sha256") != raw_hash:
        stop("El informe de eventos usa otro prefijo RAW.")

    # Recuperar el prefijo RAW original sin modificarlo.
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
        stop("No coincide la cantidad de muestras futuras.")

    # Reconstruir el entrenamiento original congelado.
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
        stop("No coincide el entrenamiento histórico.")

    # Umbrales históricos ya validados.
    thresholds = audit.training_change_thresholds(frozen)

    event_windows = {
        name: (
            ev.parse_timestamp(window["start"]),
            ev.parse_timestamp(window["end"]),
        )
        for name, window in events["event_windows_utc"].items()
    }

    # Reconstruir todos los pares prospectivos.
    stream = [frozen[-2], frozen[-1]] + future
    test_x, records = [], []
    skipped = 0

    for i in range(2, len(stream)):
        previous, earlier, target = stream[i - 1], stream[i - 2], stream[i]

        x = ev.feature_at(previous, earlier)
        actual = target.get("hashRate")
        baseline = previous.get("hashRate_1h")
        previous_actual = previous.get("hashRate")

        interval = (target["_dt"] - previous["_dt"]).total_seconds()

        if (
            x is None
            or not ev.valid_number(actual)
            or not ev.valid_number(baseline)
            or not ev.valid_number(previous_actual)
            or interval <= 0
        ):
            skipped += 1
            continue

        signed_change = float(actual) - float(previous_actual)
        absolute_change = abs(signed_change)
        change_per_minute = absolute_change / (interval / 60.0)

        if signed_change > EPSILON:
            direction = "subida"
        elif signed_change < -EPSILON:
            direction = "bajada"
        else:
            direction = "sin_cambio"

        test_x.append(x)
        records.append({
            "timestamp": target["_dt"].isoformat(),
            "actual": float(actual),
            "baseline_1h": float(baseline),
            "interval_seconds": float(interval),
            "absolute_change_ghs": absolute_change,
            "direction": direction,
            "change_class": audit.classify_change(
                change_per_minute, thresholds
            ),
            "operational_context": audit.operational_context(
                target["_dt"], event_windows
            ),
        })

    if skipped != prospective["validation"]["future_pairs_skipped"]:
        stop("No coincide la cantidad de pares omitidos.")

    if len(records) != audit.EXPECTED_PAIRS:
        stop(f"Se esperaban {audit.EXPECTED_PAIRS} pares; hay {len(records)}.")

    test_x = np.asarray(test_x, dtype=float)

    # Modelos fijos: no se utiliza información futura para entrenar.
    full_indices = np.arange(len(ev.FEATURES))
    reduced_indices = np.asarray([
        ev.FEATURES.index(f) for f in ev.REDUCED_FEATURES
    ])

    original_predictions = ev.fit_predict(
        train_x, train_y, test_x, full_indices
    )
    reduced_predictions = ev.fit_predict(
        train_x, train_y, test_x, reduced_indices
    )

    for i, record in enumerate(records):
        record["ridge_original"] = float(original_predictions[i])
        record["ridge_reducido"] = float(reduced_predictions[i])

    # Verificar que se reproducen las métricas prospectivas oficiales.
    global_methods = ev.compare_methods(records)

    for method in audit.METHODS:
        audit.verify_metrics(
            global_methods[method],
            prospective["global"][method],
            method,
        )

    # Clasificaciones que cubren todas las observaciones.
    by_direction = defaultdict(list)
    by_class_direction = defaultdict(list)
    habitual_class_direction = defaultdict(list)
    by_context_direction = defaultdict(list)

    for record in records:
        direction = record["direction"]
        change_class = record["change_class"]
        context = record["operational_context"]

        by_direction[direction].append(record)
        by_class_direction[(change_class, direction)].append(record)
        by_context_direction[(context, direction)].append(record)

        if context == "funcionamiento_habitual":
            habitual_class_direction[(change_class, direction)].append(
                record
            )

    if sum(map(len, by_direction.values())) != len(records):
        stop("La clasificación direccional perdió observaciones.")

    if sum(map(len, by_class_direction.values())) != len(records):
        stop("La clasificación combinada perdió observaciones.")

    # Métricas por dirección.
    direction_summary = {
        d: audit.summarize(by_direction.get(d, []))
        for d in DIRECTIONS
    }

    # Métricas por variación y dirección.
    class_direction_summary = {
        c: {
            d: audit.summarize(by_class_direction.get((c, d), []))
            for d in DIRECTIONS
        }
        for c in CLASSES
    }

    # Resultado específico de funcionamiento habitual.
    habitual_summary = {
        c: {
            d: audit.summarize(
                habitual_class_direction.get((c, d), [])
            )
            for d in DIRECTIONS
        }
        for c in CLASSES
    }

    context_summary = {
        context: {
            direction: audit.summarize(
                by_context_direction.get((context, direction), [])
            )
            for direction in DIRECTIONS
        }
        for context in sorted({
            r["operational_context"] for r in records
        })
    }

    report = {
        "title": "TEOS NEURONA - Diagnóstico direccional Ridge",
        "snapshot_sha256": snapshot_hash,
        "raw_prefix_sha256": raw_hash,
        "validation": {
            "official_prospective_metrics_reproduced": True,
            "prospective_pairs": len(records),
            "training_samples": len(train_y),
            "future_data_used_for_training": False,
            "model_weights_fixed": True,
            "all_valid_observations_preserved": True,
            "original_reports_modified": False,
        },
        "direction_definition": {
            "subida": "Hashrate real actual mayor que el anterior.",
            "bajada": "Hashrate real actual menor que el anterior.",
            "sin_cambio": "Diferencia absoluta menor o igual a EPSILON.",
            "epsilon_ghs": EPSILON,
            "classification_is_post_hoc": True,
        },
        "variation_thresholds": thresholds,
        "all_directions": direction_summary,
        "variation_by_direction_all_contexts": class_direction_summary,
        "habitual_operation_by_variation_and_direction": habitual_summary,
        "operational_context_by_direction": context_summary,
        "warning": (
            "La dirección se calcula usando el hashrate real del objetivo. "
            "Es un diagnóstico retrospectivo, no una variable disponible "
            "para predecir ese mismo objetivo. Los eventos permanecen "
            "incluidos en las métricas globales."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA - DIAGNÓSTICO DIRECCIONAL")
    print("Integridad y métricas prospectivas: verificadas")
    print("Pares conservados:", len(records))
    print("Entrenamiento histórico:", len(train_y))
    print("Reentrenamiento futuro: NO")

    print("\n--- FUNCIONAMIENTO HABITUAL ---")

    for change_class in CLASSES:
        print(f"\n{change_class.upper()}")

        for direction in DIRECTIONS:
            group = habitual_summary[change_class][direction]
            n = group["n"]

            if not n:
                print(f"  {direction}: n=0")
                continue

            methods = group["methods"]
            comparison = group["ridge_reducido_vs_referencia_1h"]

            reduced_mae = methods["ridge_reducido"]["mae_ghs"]
            baseline_mae = methods["referencia_1h"]["mae_ghs"]

            print(
                f"  {direction}: n={n} | "
                f"Reducido={reduced_mae:.4f} | "
                f"Referencia={baseline_mae:.4f} | "
                f"Diferencia={reduced_mae - baseline_mae:+.4f} GH/s"
            )
            print(
                f"    Victorias reducido: "
                f"{comparison['gana_por_error_absoluto']}/{n}"
            )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("RAW, modelos y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
