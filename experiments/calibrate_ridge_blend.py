#!/usr/bin/env python3
"""Calibracion historica de mezcla Ridge 7 dias y referencia 1h."""

import sys
import json
import hashlib
from pathlib import Path
from datetime import timedelta

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_ridge_prospective as core

SNAPSHOT = core.ROOT / "experiments/expanded_training_20261103.jsonl"
MANIFEST = core.ROOT / "experiments/expanded_training_20261103_manifest.json"
CV_REPORT = core.ROOT / "experiments/ridge_training_window_cv_report.json"
OUTPUT = core.ROOT / "experiments/ridge_blend_calibration_report.json"

OLD_CUTOFF = core.parse_timestamp("2026-11-03T23:35:24.026790+00:00")
CUTOFF = core.parse_timestamp("2026-11-04T11:53:12.015883+00:00")
SELECTED = np.asarray([
    core.FEATURES.index(f) for f in core.REDUCED_FEATURES
])


def stop(message):
    raise SystemExit("CALIBRACION DETENIDA: " + message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def compare(actual, baseline, ridge, blend):
    return {
        "n": len(actual),
        "referencia_1h": core.metrics(actual, baseline),
        "ridge_7_dias": core.metrics(actual, ridge),
        "mezcla_calibrada": core.metrics(actual, blend),
    }


def main():
    if OUTPUT.exists():
        stop("El informe ya existe. No se sobrescribio.")

    for path, expected in core.EXPECTED_HASHES.items():
        if not path.is_file() or digest(path.read_bytes()) != expected:
            stop("Integridad historica incorrecta: " + path.name)

    raw_snapshot = SNAPSHOT.read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cv = json.loads(CV_REPORT.read_text(encoding="utf-8"))

    if digest(raw_snapshot) != manifest.get("snapshot_sha256"):
        stop("SHA-256 de la fotografia incorrecto.")

    if cv.get("selection_cutoff_utc") != CUTOFF.isoformat():
        stop("El informe de seleccion no corresponde al corte.")

    if cv.get("selected_window") is not None:
        stop("La seleccion anterior indica una ventana aprobada; revisar.")

    if "7_dias" not in cv.get("results", {}):
        stop("No existe resultado historico para la ventana de 7 dias.")

    frozen = []
    for line in raw_snapshot.splitlines():
        row = json.loads(line)
        row["_dt"] = core.parse_timestamp(row["timestamp"])
        row["_target"] = float(row["hashRate"])
        frozen.append(row)

    if frozen[-1]["_dt"] != OLD_CUTOFF:
        stop("El ultimo registro congelado no coincide.")

    historical, future, invalid, duplicates, raw_hash = (
        core.load_raw_future(OLD_CUTOFF)
    )
    core.verify_context(frozen, historical)

    past = [r for r in future if r["_dt"] <= CUTOFF]
    stream = frozen + past

    rows = []
    for i in range(2, len(stream)):
        previous, earlier, target = stream[i-1], stream[i-2], stream[i]
        dt = target["_dt"]

        if dt > CUTOFF:
            break

        x = core.feature_at(previous, earlier)
        y = target.get("hashRate")
        base = previous.get("hashRate_1h")
        interval = (dt - previous["_dt"]).total_seconds()

        if (x is None or not core.valid_number(y)
                or not core.valid_number(base) or interval <= 0):
            continue

        rows.append({
            "dt": dt,
            "x": x,
            "actual": float(y),
            "baseline": float(base),
            "interval": float(interval),
        })

    if len(rows) != cv.get("historical_usable_pairs"):
        stop("El numero de pares historicos no coincide con la seleccion.")

    # Reconstruir exactamente los mismos cinco bloques cronologicos.
    fold_specs = []
    cv_start = CUTOFF - timedelta(days=5)

    for k in range(5):
        start = cv_start + timedelta(days=k)
        end = start + timedelta(days=1)
        if k == 4:
            end = CUTOFF + timedelta(microseconds=1)
        fold_specs.append((start, end))

    actual_all = []
    baseline_all = []
    ridge_all = []
    intervals_all = []
    blocks = []

    for k, (start, end) in enumerate(fold_specs):
        train = [
            r for r in rows
            if start - timedelta(days=7) <= r["dt"] < start
        ]
        test = [r for r in rows if start <= r["dt"] < end]

        previous_fold = cv["results"]["7_dias"]["bloques"][k]

        if (len(train) != previous_fold["train_n"]
                or len(test) != previous_fold["test_n"]):
            stop(f"El bloque {k+1} no reproduce los conteos anteriores.")

        train_x = np.asarray([r["x"] for r in train], dtype=float)
        train_y = np.asarray([r["actual"] for r in train], dtype=float)
        test_x = np.asarray([r["x"] for r in test], dtype=float)

        ridge = core.fit_predict(train_x, train_y, test_x, SELECTED)

        actual = np.asarray([r["actual"] for r in test], dtype=float)
        baseline = np.asarray([r["baseline"] for r in test], dtype=float)
        intervals = np.asarray([r["interval"] for r in test], dtype=float)

        # Comprobar que la reconstruccion coincide con la auditoria anterior.
        ref_m = core.metrics(actual, baseline)
        ridge_m = core.metrics(actual, ridge)

        old_block = previous_fold
        for new_m, old_m, label in (
            (ref_m, old_block["referencia_1h"], "referencia"),
            (ridge_m, old_block["ridge_ventana"], "Ridge"),
        ):
            for metric in ("mae_ghs", "rmse_ghs"):
                if abs(new_m[metric] - old_m[metric]) > 1e-5:
                    stop(f"No se reproduce {label}, bloque {k+1}, {metric}.")

        actual_all.extend(actual.tolist())
        baseline_all.extend(baseline.tolist())
        ridge_all.extend(ridge.tolist())
        intervals_all.extend(intervals.tolist())

        blocks.append({
            "block": k + 1,
            "train_n": len(train),
            "test_n": len(test),
            "actual": actual,
            "baseline": baseline,
            "ridge": ridge,
            "intervals": intervals,
        })

    actual = np.asarray(actual_all)
    baseline = np.asarray(baseline_all)
    ridge = np.asarray(ridge_all)
    intervals = np.asarray(intervals_all)

    # Lambda analitico que minimiza RMSE sobre los cinco bloques.
    delta = ridge - baseline
    denominator = float(np.dot(delta, delta))

    if denominator <= 1e-12:
        stop("No existe variacion suficiente para calibrar lambda.")

    lambda_raw = float(np.dot(delta, actual - baseline) / denominator)
    lam = float(np.clip(lambda_raw, 0.0, 1.0))
    blend = baseline + lam * delta

    global_result = compare(actual, baseline, ridge, blend)

    ordinary = intervals <= 120
    if not ordinary.any():
        stop("No hay muestras de operacion habitual.")

    ordinary_result = compare(
        actual[ordinary],
        baseline[ordinary],
        ridge[ordinary],
        blend[ordinary],
    )

    block_results = []
    wins_mae = 0
    wins_rmse = 0

    for b in blocks:
        prediction = b["baseline"] + lam * (b["ridge"] - b["baseline"])
        result = compare(
            b["actual"], b["baseline"], b["ridge"], prediction
        )

        ref = result["referencia_1h"]
        mix = result["mezcla_calibrada"]

        wins_mae += mix["mae_ghs"] < ref["mae_ghs"]
        wins_rmse += mix["rmse_ghs"] < ref["rmse_ghs"]

        block_results.append({
            "block": b["block"],
            "train_n": b["train_n"],
            "test_n": b["test_n"],
            "result": result,
        })

    holdout_end = core.parse_timestamp(
        "2026-11-05T00:37:10.103606+00:00"
    )

    report = {
        "title": "TEOS - Calibracion de mezcla Ridge 7 dias",
        "integrity": {
            "snapshot_sha256": manifest["snapshot_sha256"],
            "raw_sha256": raw_hash,
            "previous_cv_report_sha256": digest(CV_REPORT.read_bytes()),
            "original_experiments_modified": False,
        },
        "calibration": {
            "method": "Minimizacion analitica de RMSE",
            "lambda_unclipped": lambda_raw,
            "lambda_selected": lam,
            "allowed_range": [0.0, 1.0],
            "folds": 5,
            "training_window_days": 7,
            "calibration_cutoff_utc": CUTOFF.isoformat(),
            "holdout_start_exclusive_utc": CUTOFF.isoformat(),
            "holdout_end_inclusive_utc": holdout_end.isoformat(),
            "holdout_502_pairs_used": False,
            "future_after_calibration_cutoff_used": False,
        },
        "global": global_result,
        "ordinary_operation_120s": ordinary_result,
        "by_historical_block": block_results,
        "blocks_won_vs_reference": {
            "mae": int(wins_mae),
            "rmse": int(wins_rmse),
        },
        "conclusion": {
            "blend_beats_reference_mae": (
                global_result["mezcla_calibrada"]["mae_ghs"]
                < global_result["referencia_1h"]["mae_ghs"]
            ),
            "blend_beats_reference_rmse": (
                global_result["mezcla_calibrada"]["rmse_ghs"]
                < global_result["referencia_1h"]["rmse_ghs"]
            ),
            "ordinary_mae_not_worse": (
                ordinary_result["mezcla_calibrada"]["mae_ghs"]
                <= ordinary_result["referencia_1h"]["mae_ghs"]
            ),
            "promotion_recommended": False,
        },
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("CALIBRACION RIDGE + REFERENCIA 1H")
    print("Reproduccion de cinco bloques: verificada")
    print("Pares de calibracion:", len(actual))
    print(f"Lambda sin limitar: {lambda_raw:.8f}")
    print(f"Lambda seleccionada: {lam:.8f}")

    for label, result in (
        ("GLOBAL", global_result),
        ("OPERACION HABITUAL <=120s", ordinary_result),
    ):
        print("\n---", label, "---")
        for method in ("referencia_1h", "ridge_7_dias", "mezcla_calibrada"):
            m = result[method]
            print(
                f"{method}: MAE={m['mae_ghs']:.6f} | "
                f"RMSE={m['rmse_ghs']:.6f} GH/s"
            )

    print("\nBloques ganados MAE/RMSE:", wins_mae, "/", wins_rmse)
    print("Holdout reservado utilizado: NO")
    print("Informe:", OUTPUT.relative_to(core.ROOT))
    print("Integracion autorizada: NO")


if __name__ == "__main__":
    main()
