#!/usr/bin/env python3
"""Validación prospectiva de Ridge protegido en 180 muestras nuevas."""

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import evaluate_ridge_prospective as ev
import audit_ridge_residual_conditions as audit

OUTPUT = ROOT / "experiments/ridge_protected_prospective_report.json"

FEATURES = (
    "delta_hashRate",
    "delta_hashRate_10m",
    "delta_hashRate_1h",
)

BATCH_END = "2026-10-30T22:49:22.416615+00:00"
EXPECTED_NEW_SAMPLES = 180


def stop(message):
    raise SystemExit(f"VALIDACIÓN DETENIDA: {message}")


def metrics(records, field):
    if not records:
        return {"n": 0}

    actual = np.asarray([r["actual"] for r in records], dtype=float)
    predicted = np.asarray([r[field] for r in records], dtype=float)

    residual = predicted - actual
    absolute = np.abs(residual)

    result = {
        "n": len(records),
        "mae_ghs": float(np.mean(absolute)),
        "rmse_ghs": float(np.sqrt(np.mean(residual ** 2))),
        "bias_ghs": float(np.mean(residual)),
        "max_abs_error_ghs": float(np.max(absolute)),
    }

    return result


def main():
    if OUTPUT.exists():
        stop(f"El informe ya existe: {OUTPUT.name}")

    # 1. Comprobar integridad histórica.
    for path, expected in ev.EXPECTED_HASHES.items():
        if ev.sha256_file(path) != expected:
            stop(f"SHA-256 inesperado: {path.name}")

    frozen, snapshot_hash = ev.load_frozen()

    prospective = json.loads(
        ev.OUTPUT.read_text(encoding="utf-8")
    )
    original = json.loads(
        ev.ORIGINAL.read_text(encoding="utf-8")
    )
    candidate = json.loads(
        audit.CANDIDATE.read_text(encoding="utf-8")
    )
    manifest = json.loads(
        ev.MANIFEST.read_text(encoding="utf-8")
    )

    if manifest.get("sha256") != snapshot_hash:
        stop("El manifiesto no coincide con la fotografía congelada.")

    if original.get("snapshot_sha256") != snapshot_hash:
        stop("El modelo original corresponde a otra fotografía.")

    if candidate.get("integrity", {}).get(
        "snapshot_sha256"
    ) != snapshot_hash:
        stop("El modelo reducido corresponde a otra fotografía.")

    if prospective["integrity"]["snapshot_sha256"] != snapshot_hash:
        stop("El informe prospectivo corresponde a otra fotografía.")

    if len(frozen) != 846 or original.get("usable_samples") != 844:
        stop("La fotografía o el entrenamiento histórico no coinciden.")

    # 2. Recuperar el prefijo RAW original verificado.
    last_target = ev.parse_timestamp(
        prospective["evaluation_period_utc"]["last_target"]
    )

    prefix = audit.recover_original_prefix(
        prospective["integrity"]["raw_sha256"],
        last_target,
    )

    prefix_rows = audit.load_prefix_rows(prefix)

    if len(prefix_rows) < 2 or prefix_rows[-1]["_dt"] != last_target:
        stop("No se recuperó correctamente el contexto temporal anterior.")

    historical = [
        r for r in prefix_rows
        if r["_dt"] <= frozen[-1]["_dt"]
    ]
    ev.verify_context(frozen, historical)

    # 3. Capturar únicamente el lote nuevo, con límite temporal fijo.
    batch_end = ev.parse_timestamp(BATCH_END)
    by_time = {}

    with ev.RAW.open(encoding="utf-8") as file:
        for line in file:
            try:
                row = json.loads(line)
                timestamp = ev.parse_timestamp(row.get("timestamp"))

                if not last_target < timestamp <= batch_end:
                    continue

                if not ev.valid_number(row.get("hashRate")):
                    continue

                row["_dt"] = timestamp
                by_time[timestamp] = row

            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue

    new_rows = [by_time[t] for t in sorted(by_time)]

    if len(new_rows) != EXPECTED_NEW_SAMPLES:
        stop(
            f"El lote tiene {len(new_rows)} muestras válidas; "
            f"se esperaban {EXPECTED_NEW_SAMPLES}."
        )

    if new_rows[0]["_dt"] != ev.parse_timestamp(
        "2026-10-30T19:30:28.889495+00:00"
    ):
        stop("La primera muestra del lote no coincide.")

    if new_rows[-1]["_dt"] != batch_end:
        stop("La última muestra del lote no coincide.")

    # 4. Reconstruir el entrenamiento congelado.
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
        stop("No se reprodujeron las 844 muestras de entrenamiento.")

    # 5. Calcular límites exclusivamente con el entrenamiento congelado.
    limits = {}

    for name in FEATURES:
        j = ev.FEATURES.index(name)
        values = train_x[:, j]

        limits[name] = {
            "minimum": float(np.min(values)),
            "maximum": float(np.max(values)),
        }

    # 6. Construir las 180 predicciones nuevas.
    stream = [prefix_rows[-2], prefix_rows[-1]] + new_rows

    test_x = []
    records = []
    skipped = []

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
            skipped.append(target["_dt"].isoformat())
            continue

        test_x.append(x)

        records.append({
            "timestamp": target["_dt"].isoformat(),
            "actual": float(actual),
            "baseline_1h": float(baseline),
        })

    if skipped:
        stop(
            f"Hay {len(skipped)} muestras sin características válidas. "
            f"Primera: {skipped[0]}"
        )

    test_x = np.asarray(test_x, dtype=float)

    if len(records) != EXPECTED_NEW_SAMPLES:
        stop("No se reconstruyeron las 180 predicciones nuevas.")

    # 7. Ajustar una sola vez cada predictor con el histórico congelado.
    reduced_indices = np.asarray([
        ev.FEATURES.index(name)
        for name in ev.REDUCED_FEATURES
    ])

    predictions = ev.fit_predict(
        train_x,
        train_y,
        test_x,
        reduced_indices,
    )

    # 8. Aplicar la protección sin utilizar el valor real objetivo.
    outside_counts = defaultdict(int)
    route_groups = defaultdict(list)

    for i, record in enumerate(records):
        record["ridge_reducido"] = float(predictions[i])

        outside = []

        for name in FEATURES:
            j = ev.FEATURES.index(name)
            value = float(test_x[i, j])
            low = limits[name]["minimum"]
            high = limits[name]["maximum"]

            if value < low or value > high:
                outside.append(name)
                outside_counts[name] += 1

        record["outside_features"] = outside

        if outside:
            record["ridge_protegido"] = record["baseline_1h"]
            record["route"] = "referencia_1h"
        else:
            record["ridge_protegido"] = record["ridge_reducido"]
            record["route"] = "ridge_reducido"

        route_groups[record["route"]].append(record)

    # 9. Evaluar exactamente el mismo lote para los tres métodos.
    results = {
        "ridge_reducido": metrics(records, "ridge_reducido"),
        "referencia_1h": metrics(records, "baseline_1h"),
        "ridge_protegido": metrics(records, "ridge_protegido"),
    }

    comparisons = {
        "protegido_menos_reducido_mae": (
            results["ridge_protegido"]["mae_ghs"]
            - results["ridge_reducido"]["mae_ghs"]
        ),
        "protegido_menos_referencia_mae": (
            results["ridge_protegido"]["mae_ghs"]
            - results["referencia_1h"]["mae_ghs"]
        ),
        "protegido_menos_referencia_rmse": (
            results["ridge_protegido"]["rmse_ghs"]
            - results["referencia_1h"]["rmse_ghs"]
        ),
    }

    route_metrics = {
        route: {
            "ridge_reducido": metrics(group, "ridge_reducido"),
            "referencia_1h": metrics(group, "baseline_1h"),
            "ridge_protegido": metrics(group, "ridge_protegido"),
        }
        for route, group in route_groups.items()
    }

    report = {
        "title": "TEOS NEURONA - Validación prospectiva Ridge protegido",
        "snapshot_sha256": snapshot_hash,
        "training_cutoff_utc": last_target.isoformat(),
        "evaluation_end_utc": BATCH_END,
        "validation": {
            "new_raw_samples": len(new_rows),
            "predictions_evaluated": len(records),
            "training_samples": len(train_y),
            "training_frozen": True,
            "future_data_used_for_training": False,
            "model_weights_fixed": True,
            "protection_thresholds_frozen": True,
            "selection_uses_only_prior_information": True,
            "all_new_samples_evaluated": True,
            "original_reports_modified": False,
            "raw_modified": False,
            "bitaxe_modified": False,
        },
        "protection_rule": {
            "features": list(FEATURES),
            "training_ranges": limits,
            "outside_counts": dict(outside_counts),
            "route_counts": {
                name: len(group)
                for name, group in route_groups.items()
            },
            "rule": (
                "Ridge reducido cuando todas las características "
                "permanecen dentro de sus rangos históricos; referencia "
                "1h cuando alguna sale de rango."
            ),
        },
        "metrics": results,
        "comparisons": comparisons,
        "by_routing_decision": route_metrics,
        "warning": (
            "Validación prospectiva inicial de 180 muestras. "
            "No basta por sí sola para autorizar integración en vivo."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA - VALIDACIÓN PROSPECTIVA")
    print("Lote nuevo:", len(new_rows))
    print("Predicciones evaluadas:", len(records))
    print("Entrenamiento congelado:", len(train_y))
    print("Límites históricos recalculados: NO")
    print("Reentrenamiento futuro: NO")

    print("\n--- RESULTADOS ---")
    for name, item in results.items():
        print(
            f"{name}: MAE={item['mae_ghs']:.4f} | "
            f"RMSE={item['rmse_ghs']:.4f} | "
            f"sesgo={item['bias_ghs']:+.4f} GH/s"
        )

    print("\n--- ACTIVACIÓN DE PROTECCIÓN ---")
    for name, count in report["protection_rule"]["route_counts"].items():
        print(f"{name}: {count}")

    print("\n--- DIFERENCIAS ---")
    for name, value in comparisons.items():
        print(f"{name}: {value:+.4f} GH/s")

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("RAW, modelos originales y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
