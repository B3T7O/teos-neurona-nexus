#!/usr/bin/env python3
"""Evaluación prospectiva independiente de Ridge residual."""

import sys
import json
import hashlib
from pathlib import Path
from collections import defaultdict

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_ridge_prospective as core

OUTPUT = core.ROOT / "experiments/ridge_residual_fresh_report.json"
FRESH_CUTOFF = core.parse_timestamp("2026-11-03T02:26:18.123668+00:00")


def stop(message):
    raise SystemExit(f"EVALUACIÓN RESIDUAL DETENIDA: {message}")


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(records):
    if not records:
        return {"n": 0}

    actual = [r["actual"] for r in records]
    methods = {
        "referencia_1h": [r["baseline"] for r in records],
        "ridge_reducido_absoluto": [r["absolute"] for r in records],
        "ridge_residual": [r["residual"] for r in records],
    }
    result = {
        name: core.metrics(actual, prediction)
        for name, prediction in methods.items()
    }

    for name in ("ridge_reducido_absoluto", "ridge_residual"):
        result[f"{name}_delta_mae_vs_referencia"] = (
            result[name]["mae_ghs"]
            - result["referencia_1h"]["mae_ghs"]
        )
        result[f"{name}_delta_rmse_vs_referencia"] = (
            result[name]["rmse_ghs"]
            - result["referencia_1h"]["rmse_ghs"]
        )

    return result


def main():
    if OUTPUT.exists():
        stop(f"El informe ya existe; no se sobrescribió: {OUTPUT.name}")

    for path, expected in core.EXPECTED_HASHES.items():
        if not path.is_file() or sha256_file(path) != expected:
            stop(f"Integridad no verificada: {path.name}")

    frozen, snapshot_hash = core.load_frozen()
    manifest = json.loads(core.MANIFEST.read_text())
    original = json.loads(core.ORIGINAL.read_text())
    candidate = json.loads(core.CANDIDATE.read_text())

    if manifest.get("sha256") != snapshot_hash:
        stop("La fotografía no coincide con el manifiesto.")

    if original.get("snapshot_sha256") != snapshot_hash:
        stop("El informe original no corresponde a la fotografía.")

    definition = candidate.get("candidate_definition", {})
    if (
        candidate.get("integrity", {}).get("snapshot_sha256") != snapshot_hash
        or definition.get("retained_features") != core.REDUCED_FEATURES
    ):
        stop("La definición del candidato reducido no está verificada.")

    cutoff = frozen[-1]["_dt"]

    # Entrenamiento histórico: objetivo residual y objetivo absoluto.
    train_x, train_residual, train_absolute = [], [], []

    for i in range(2, len(frozen)):
        x = core.feature_at(frozen[i - 1], frozen[i - 2])
        actual = frozen[i].get("_target")
        baseline = frozen[i - 1].get("hashRate_1h")

        if (
            x is None
            or not core.valid_number(actual)
            or not core.valid_number(baseline)
        ):
            continue

        train_x.append(x)
        train_residual.append(float(actual) - float(baseline))
        train_absolute.append(float(actual))

    expected_n = original.get("usable_samples")
    if len(train_x) != expected_n:
        stop("El número de muestras de entrenamiento no coincide.")

    train_x = np.asarray(train_x, dtype=float)
    train_residual = np.asarray(train_residual, dtype=float)
    train_absolute = np.asarray(train_absolute, dtype=float)

    # Carga futura y verificación de continuidad.
    historical, future, invalid, duplicates, raw_hash = (
        core.load_raw_future(cutoff)
    )
    core.verify_context(frozen, historical)

    if not future:
        stop("No hay muestras posteriores al corte.")

    stream = [frozen[-2], frozen[-1]] + future
    test_x, actual, baseline = [], [], []
    intervals, timestamps = [], []
    skipped = 0

    for i in range(2, len(stream)):
        previous, earlier, target = stream[i - 1], stream[i - 2], stream[i]
        if target["_dt"] <= FRESH_CUTOFF:
            continue
        x = core.feature_at(previous, earlier)
        y = target.get("hashRate")
        base = previous.get("hashRate_1h")
        interval = (target["_dt"] - previous["_dt"]).total_seconds()

        if (
            x is None
            or not core.valid_number(y)
            or not core.valid_number(base)
            or interval <= 0
        ):
            skipped += 1
            continue

        test_x.append(x)
        actual.append(float(y))
        baseline.append(float(base))
        intervals.append(float(interval))
        timestamps.append(target["_dt"].isoformat())

    if not test_x:
        stop("No hay pares futuros válidos.")

    test_x = np.asarray(test_x, dtype=float)
    actual = np.asarray(actual, dtype=float)
    baseline = np.asarray(baseline, dtype=float)

    selected = np.asarray([
        core.FEATURES.index(f) for f in core.REDUCED_FEATURES
    ])

    # Ambos modelos usan idénticas características y muestras históricas.
    predicted_residual = core.fit_predict(
        train_x, train_residual, test_x, selected
    )
    predicted_absolute = core.fit_predict(
        train_x, train_absolute, test_x, selected
    )

    corrected = baseline + predicted_residual

    records = []
    for i in range(len(actual)):
        records.append({
            "timestamp": timestamps[i],
            "actual": float(actual[i]),
            "baseline": float(baseline[i]),
            "absolute": float(predicted_absolute[i]),
            "residual": float(corrected[i]),
            "interval_seconds": float(intervals[i]),
        })

    global_result = summarize(records)

    by_interval = {
        "hasta_120_segundos": summarize([
            r for r in records if r["interval_seconds"] <= 120
        ]),
        "superiores_a_120_segundos": summarize([
            r for r in records if r["interval_seconds"] > 120
        ]),
    }

    daily_groups = defaultdict(list)
    for record in records:
        daily_groups[record["timestamp"][:10]].append(record)

    daily = {
        day: summarize(rows)
        for day, rows in sorted(daily_groups.items())
    }

    report = {
        "title": "TEOS NEURONA — Evaluación residual con datos nuevos",
        "integrity": {
            "snapshot_sha256": snapshot_hash,
            "raw_sha256": raw_hash,
            "original_script_sha256": sha256_file(core.SCRIPT),
            "original_report_sha256": sha256_file(core.ORIGINAL),
            "original_files_modified": False,
        },
        "validation": {
            "training_samples": len(train_x),
            "training_cutoff_utc": cutoff.isoformat(),
            "fresh_evaluation_cutoff_utc": FRESH_CUTOFF.isoformat(),
            "future_raw_rows_after_fresh_cutoff": sum(row["_dt"] > FRESH_CUTOFF for row in future),
            "all_post_training_cutoff_raw_rows": len(future),
            "valid_future_pairs": len(records),
            "skipped_pairs": skipped,
            "invalid_raw_records": invalid,
            "duplicate_raw_timestamps": duplicates,
            "historical_context_matches": True,
            "future_data_used_for_training": False,
            "model_refitted_during_evaluation": False,
            "rolling_one_step_ahead": True,
            "ridge_alpha": core.ALPHA,
            "features": list(core.REDUCED_FEATURES),
            "promotion_authorized": False,
        },
        "candidate_definition": {
            "training_target": "hashRate_actual - baseline_1h_previo",
            "final_prediction": "baseline_1h_previo + residuo_estimado",
            "scaling": "Solo con muestras históricas de entrenamiento",
        },
        "evaluation_period_utc": {
            "first_target": timestamps[0],
            "last_target": timestamps[-1],
        },
        "global": global_result,
        "by_interval": by_interval,
        "by_utc_day": daily,
        "conclusion": {
            "residual_beats_reference_mae": (
                global_result["ridge_residual"]["mae_ghs"]
                < global_result["referencia_1h"]["mae_ghs"]
            ),
            "residual_beats_reference_rmse": (
                global_result["ridge_residual"]["rmse_ghs"]
                < global_result["referencia_1h"]["rmse_ghs"]
            ),
            "promotion_recommended": False,
        },
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA — RIDGE RESIDUAL")
    print("Integridad histórica: verificada")
    print("Entrenamiento:", len(train_x))
    print("Pares futuros:", len(records))
    print("Reentrenamiento futuro: NO")

    for name, result in global_result.items():
        if isinstance(result, dict) and "mae_ghs" in result:
            print(
                f"{name}: MAE={result['mae_ghs']:.6f} | "
                f"RMSE={result['rmse_ghs']:.6f} GH/s"
            )

    print("Informe:", OUTPUT.relative_to(core.ROOT))
    print("Integración autorizada: NO")


if __name__ == "__main__":
    main()
