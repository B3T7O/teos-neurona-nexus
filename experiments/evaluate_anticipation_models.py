#!/usr/bin/env python3
"""Evaluacion independiente de anticipacion a 5, 10 y 15 minutos."""

import sys
import json
import hashlib
from pathlib import Path
from bisect import bisect_left
from datetime import timedelta

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_ridge_prospective as core

ROOT = core.ROOT
TRAIN = ROOT / "experiments/anticipation_training_20261105.jsonl"
TRAIN_MANIFEST = ROOT / "experiments/anticipation_training_20261105_manifest.json"
HOLDOUT = ROOT / "experiments/anticipation_holdout_20261105.jsonl"
HOLDOUT_MANIFEST = ROOT / "experiments/anticipation_holdout_20261105_manifest.json"
OUTPUT = ROOT / "experiments/anticipation_models_holdout_report.json"

CUTOFF = core.parse_timestamp("2026-11-05T00:37:10.103606+00:00")
HORIZONS = (5, 10, 15)
TOLERANCE = 90

SELECTED = np.asarray([
    core.FEATURES.index(f) for f in core.REDUCED_FEATURES
])


def stop(message):
    raise SystemExit("ANTICIPACION DETENIDA: " + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_rows(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        row["_dt"] = core.parse_timestamp(row["timestamp"])
        rows.append(row)
    return rows


def build_pairs(rows, minutes, origins_after=None):
    """Un objetivo: primera muestra en o despues del horizonte."""
    times = [r["_dt"] for r in rows]
    horizon = timedelta(minutes=minutes)
    pairs = []

    for i in range(1, len(rows)):
        origin = rows[i]
        previous = rows[i - 1]

        if origins_after is not None and origin["_dt"] <= origins_after:
            continue

        x = core.feature_at(origin, previous)
        if x is None:
            continue

        current_hash = origin.get("hashRate")
        reference_1h = origin.get("hashRate_1h")

        if (
            not core.valid_number(current_hash)
            or not core.valid_number(reference_1h)
        ):
            continue

        target_time = origin["_dt"] + horizon
        j = bisect_left(times, target_time, i + 1)

        if j >= len(rows):
            continue

        target = rows[j]
        delay = (target["_dt"] - target_time).total_seconds()

        if delay < 0 or delay > TOLERANCE:
            continue

        actual = target.get("hashRate")
        if not core.valid_number(actual):
            continue

        pairs.append({
            "x": x,
            "actual": float(actual),
            "current_hash": float(current_hash),
            "reference_1h": float(reference_1h),
            "origin": origin["_dt"].isoformat(),
            "target": target["_dt"].isoformat(),
            "target_delay_seconds": float(delay),
        })

    return pairs


def evaluate(train_pairs, test_pairs, minutes):
    if len(train_pairs) < 100 or not test_pairs:
        stop(f"Muestras insuficientes para {minutes} minutos.")

    train_x = np.asarray([p["x"] for p in train_pairs], dtype=float)
    train_y = np.asarray([p["actual"] for p in train_pairs], dtype=float)
    test_x = np.asarray([p["x"] for p in test_pairs], dtype=float)

    prediction = core.fit_predict(
        train_x, train_y, test_x, SELECTED
    )

    actual = [p["actual"] for p in test_pairs]
    persistence = [p["current_hash"] for p in test_pairs]
    reference = [p["reference_1h"] for p in test_pairs]

    metrics = {
        "persistencia_hashRate_actual": core.metrics(actual, persistence),
        "referencia_hashRate_1h": core.metrics(actual, reference),
        "ridge_anticipacion": core.metrics(actual, prediction),
    }

    ridge = metrics["ridge_anticipacion"]

    for name in ("persistencia_hashRate_actual", "referencia_hashRate_1h"):
        baseline = metrics[name]
        metrics[name + "_delta_mae_ridge"] = (
            ridge["mae_ghs"] - baseline["mae_ghs"]
        )
        metrics[name + "_delta_rmse_ridge"] = (
            ridge["rmse_ghs"] - baseline["rmse_ghs"]
        )

    return {
        "horizon_minutes": minutes,
        "training_pairs": len(train_pairs),
        "holdout_pairs": len(test_pairs),
        "metrics": metrics,
        "delay_seconds": {
            "median": float(np.median([
                p["target_delay_seconds"] for p in test_pairs
            ])),
            "p90": float(np.percentile([
                p["target_delay_seconds"] for p in test_pairs
            ], 90)),
        },
        "prediction_beats_persistence_mae": (
            ridge["mae_ghs"]
            < metrics["persistencia_hashRate_actual"]["mae_ghs"]
        ),
        "prediction_beats_persistence_rmse": (
            ridge["rmse_ghs"]
            < metrics["persistencia_hashRate_actual"]["rmse_ghs"]
        ),
        "prediction_beats_reference_1h_mae": (
            ridge["mae_ghs"]
            < metrics["referencia_hashRate_1h"]["mae_ghs"]
        ),
        "prediction_beats_reference_1h_rmse": (
            ridge["rmse_ghs"]
            < metrics["referencia_hashRate_1h"]["rmse_ghs"]
        ),
    }


def main():
    if OUTPUT.exists():
        stop("El informe ya existe. No se sobrescribio.")

    for path in (TRAIN, TRAIN_MANIFEST, HOLDOUT, HOLDOUT_MANIFEST):
        if not path.is_file():
            stop("Falta archivo: " + path.name)

    train_bytes = TRAIN.read_bytes()
    holdout_bytes = HOLDOUT.read_bytes()

    tm = json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))
    hm = json.loads(HOLDOUT_MANIFEST.read_text(encoding="utf-8"))

    train_hash = sha(train_bytes)
    holdout_hash = sha(holdout_bytes)

    if train_hash != tm["training_sha256"]:
        stop("SHA-256 de entrenamiento incorrecto.")

    if holdout_hash != hm["holdout_sha256"]:
        stop("SHA-256 del holdout incorrecto.")

    if tm["holdout_used_for_training"] is not False:
        stop("El manifiesto no garantiza separacion.")

    if hm["used_for_training"] is not False:
        stop("El holdout figura como entrenamiento.")

    if tm["cutoff_utc"] != CUTOFF.isoformat():
        stop("Corte de entrenamiento incorrecto.")

    train_rows = read_rows(TRAIN)
    holdout_rows = read_rows(HOLDOUT)

    if len(holdout_rows) != hm["holdout_rows"] + 2:
        stop("Cantidad de filas del holdout incorrecta.")

    # Las dos filas iniciales son contexto, no objetivos evaluados.
    for old, current in zip(train_rows[-2:], holdout_rows[:2]):
        for field in ["timestamp"] + core.BASE_FIELDS:
            if old.get(field) != current.get(field):
                stop("Contexto diferente en campo: " + field)

    if holdout_rows[2]["_dt"].isoformat() != hm["first_holdout_timestamp"]:
        stop("Primera muestra del holdout incorrecta.")

    if holdout_rows[-1]["_dt"].isoformat() != hm["last_holdout_timestamp"]:
        stop("Ultima muestra del holdout incorrecta.")

    results = {}

    for minutes in HORIZONS:
        train_pairs = build_pairs(train_rows, minutes)
        test_pairs = build_pairs(holdout_rows, minutes, origins_after=CUTOFF)

        expected_train = tm["training_pairs_by_horizon"][f"{minutes}_minutos"]
        expected_test = hm["horizon_pairs"][f"{minutes}_minutos"]

        if len(train_pairs) != expected_train:
            stop(f"Conteo de entrenamiento diferente a {minutes} minutos.")

        if len(test_pairs) != expected_test:
            stop(f"Conteo holdout diferente a {minutes} minutos.")

        results[f"{minutes}_minutos"] = evaluate(
            train_pairs, test_pairs, minutes
        )

    report = {
        "title": "TEOS NEURONA - Anticipacion predictiva",
        "integrity": {
            "training_sha256": train_hash,
            "holdout_sha256": holdout_hash,
            "training_holdout_separated": True,
            "original_experiments_modified": False,
        },
        "validation": {
            "cutoff_utc": CUTOFF.isoformat(),
            "training_records": len(train_rows),
            "holdout_records": len(holdout_rows) - 2,
            "holdout_context_rows": 2,
            "horizons_minutes": list(HORIZONS),
            "model": "Ridge",
            "alpha": core.ALPHA,
            "features": list(core.REDUCED_FEATURES),
            "scaling_fitted_on_training_only": True,
            "future_data_used_for_training": False,
            "holdout_used_for_tuning": False,
            "model_refitted_during_holdout": False,
            "target_tolerance_seconds": TOLERANCE,
            "promotion_authorized": False,
        },
        "results": results,
        "conclusion": {
            "all_horizons_beat_persistence": all(
                r["prediction_beats_persistence_mae"]
                and r["prediction_beats_persistence_rmse"]
                for r in results.values()
            ),
            "all_horizons_beat_reference_1h": all(
                r["prediction_beats_reference_1h_mae"]
                and r["prediction_beats_reference_1h_rmse"]
                for r in results.values()
            ),
            "promotion_recommended": False,
        },
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA - ANTICIPACION PREDICTIVA")
    print("Integridad de entrenamiento y holdout: verificada")
    print("Entrenamiento separado: SI")
    print("Holdout usado para ajustes: NO")

    for key, result in results.items():
        print(f"\n--- HORIZONTE {result['horizon_minutes']} MINUTOS ---")
        print("Entrenamiento:", result["training_pairs"])
        print("Evaluacion:", result["holdout_pairs"])

        for method, label in (
            ("persistencia_hashRate_actual", "Persistencia actual"),
            ("referencia_hashRate_1h", "Referencia 1h"),
            ("ridge_anticipacion", "Ridge anticipacion"),
        ):
            m = result["metrics"][method]
            print(
                f"{label}: MAE={m['mae_ghs']:.6f} | "
                f"RMSE={m['rmse_ghs']:.6f} GH/s"
            )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("Integracion autorizada: NO")


if __name__ == "__main__":
    main()
