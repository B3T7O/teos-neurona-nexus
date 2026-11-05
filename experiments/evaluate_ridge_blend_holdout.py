#!/usr/bin/env python3
"""Evaluacion final e independiente de mezcla Ridge 7d + referencia."""

import sys
import json
import hashlib
from pathlib import Path
from datetime import timedelta

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_ridge_prospective as core

ROOT = core.ROOT
SNAPSHOT = ROOT / "experiments/expanded_training_20261103.jsonl"
MANIFEST = ROOT / "experiments/expanded_training_20261103_manifest.json"
CV_REPORT = ROOT / "experiments/ridge_training_window_cv_report.json"
CAL_REPORT = ROOT / "experiments/ridge_blend_calibration_report.json"
OUTPUT = ROOT / "experiments/ridge_blend_holdout_report.json"

OLD_CUTOFF = core.parse_timestamp("2026-11-03T23:35:24.026790+00:00")
CUTOFF = core.parse_timestamp("2026-11-04T11:53:12.015883+00:00")
HOLDOUT_END = core.parse_timestamp("2026-11-05T00:37:10.103606+00:00")
EXPECTED_FIRST = "2026-11-04T11:54:19.066912+00:00"
EXPECTED_LAST = "2026-11-05T00:37:10.103606+00:00"
EXPECTED_PAIRS = 502


def stop(message):
    raise SystemExit("HOLDOUT DETENIDO: " + message)


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

    snapshot_bytes = SNAPSHOT.read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cv = json.loads(CV_REPORT.read_text(encoding="utf-8"))
    calibration = json.loads(CAL_REPORT.read_text(encoding="utf-8"))

    if digest(snapshot_bytes) != manifest.get("snapshot_sha256"):
        stop("SHA-256 de fotografia incorrecto.")

    if digest(CV_REPORT.read_bytes()) != calibration["integrity"].get(
        "previous_cv_report_sha256"
    ):
        stop("El informe de seleccion cambio despues de calibrar.")

    cal = calibration["calibration"]
    if (
        cal.get("calibration_cutoff_utc") != CUTOFF.isoformat()
        or cal.get("holdout_502_pairs_used") is not False
        or cv.get("selected_window") is not None
    ):
        stop("La calibracion o la seleccion no coincide.")

    lam = float(cal["lambda_selected"])
    if abs(lam - 0.52959120) > 1e-8 or not 0 <= lam <= 1:
        stop("Lambda diferente de la calibrada.")

    frozen = []
    for line in snapshot_bytes.splitlines():
        row = json.loads(line)
        row["_dt"] = core.parse_timestamp(row["timestamp"])
        row["_target"] = float(row["hashRate"])
        frozen.append(row)

    if frozen[-1]["_dt"] != OLD_CUTOFF:
        stop("Corte de fotografia incorrecto.")

    historical, future, invalid, duplicates, raw_hash = (
        core.load_raw_future(OLD_CUTOFF)
    )
    core.verify_context(frozen, historical)

    # Reconstruir la historia completa sin utilizar el holdout para entrenar.
    stream = frozen + future
    train_start = CUTOFF - timedelta(days=7)

    train_x, train_y = [], []
    for i in range(2, len(stream)):
        previous, earlier, target = stream[i-1], stream[i-2], stream[i]
        dt = target["_dt"]

        if dt >= CUTOFF:
            break
        if dt < train_start:
            continue

        x = core.feature_at(previous, earlier)
        y = target.get("hashRate")
        base = previous.get("hashRate_1h")
        interval = (dt - previous["_dt"]).total_seconds()

        if (
            x is None or not core.valid_number(y)
            or not core.valid_number(base) or interval <= 0
        ):
            continue

        train_x.append(x)
        train_y.append(float(y))

    if not train_x:
        stop("No hay entrenamiento valido en la ventana de siete dias.")

    # Construir exclusivamente el holdout reservado.
    test_x, actual, baseline = [], [], []
    intervals, timestamps = [], []

    for i in range(2, len(stream)):
        previous, earlier, target = stream[i-1], stream[i-2], stream[i]
        dt = target["_dt"]

        if dt <= CUTOFF:
            continue
        if dt > HOLDOUT_END:
            break

        x = core.feature_at(previous, earlier)
        y = target.get("hashRate")
        base = previous.get("hashRate_1h")
        interval = (dt - previous["_dt"]).total_seconds()

        if (
            x is None or not core.valid_number(y)
            or not core.valid_number(base) or interval <= 0
        ):
            continue

        test_x.append(x)
        actual.append(float(y))
        baseline.append(float(base))
        intervals.append(float(interval))
        timestamps.append(dt.isoformat())

    if len(test_x) != EXPECTED_PAIRS:
        stop(
            f"Holdout contiene {len(test_x)} pares; "
            f"se esperaban exactamente {EXPECTED_PAIRS}."
        )

    if timestamps[0] != EXPECTED_FIRST or timestamps[-1] != EXPECTED_LAST:
        stop("Los limites temporales del holdout no coinciden.")

    train_x = np.asarray(train_x, dtype=float)
    train_y = np.asarray(train_y, dtype=float)
    test_x = np.asarray(test_x, dtype=float)
    actual = np.asarray(actual, dtype=float)
    baseline = np.asarray(baseline, dtype=float)
    intervals = np.asarray(intervals, dtype=float)

    selected = np.asarray([
        core.FEATURES.index(f) for f in core.REDUCED_FEATURES
    ])

    # Ajuste unico antes del holdout; pesos fijos durante la prueba.
    ridge = core.fit_predict(train_x, train_y, test_x, selected)
    blend = baseline + lam * (ridge - baseline)

    global_result = compare(actual, baseline, ridge, blend)

    ordinary = intervals <= 120
    long_gaps = intervals > 120

    if not ordinary.any():
        stop("No hay muestras de operacion habitual.")

    ordinary_result = compare(
        actual[ordinary], baseline[ordinary],
        ridge[ordinary], blend[ordinary]
    )

    long_result = (
        compare(
            actual[long_gaps], baseline[long_gaps],
            ridge[long_gaps], blend[long_gaps]
        )
        if long_gaps.any() else {"n": 0}
    )

    ref = global_result["referencia_1h"]
    mixed = global_result["mezcla_calibrada"]
    ordinary_ref = ordinary_result["referencia_1h"]
    ordinary_mix = ordinary_result["mezcla_calibrada"]

    report = {
        "title": "TEOS - Holdout final Ridge blend",
        "integrity": {
            "snapshot_sha256": manifest["snapshot_sha256"],
            "raw_sha256": raw_hash,
            "calibration_report_sha256": digest(CAL_REPORT.read_bytes()),
            "original_experiments_modified": False,
        },
        "validation": {
            "training_pairs": len(train_y),
            "training_window_days": 7,
            "training_start_utc": train_start.isoformat(),
            "training_end_exclusive_utc": CUTOFF.isoformat(),
            "holdout_pairs": len(actual),
            "holdout_start_exclusive_utc": CUTOFF.isoformat(),
            "holdout_end_inclusive_utc": HOLDOUT_END.isoformat(),
            "holdout_was_used_for_calibration": False,
            "future_data_used_for_training": False,
            "model_refitted_during_holdout": False,
            "lambda_fixed": lam,
            "invalid_raw_records": invalid,
            "duplicate_raw_timestamps": duplicates,
            "features": list(core.REDUCED_FEATURES),
            "promotion_authorized": False,
        },
        "evaluation_period_utc": {
            "first_target": timestamps[0],
            "last_target": timestamps[-1],
        },
        "global": global_result,
        "ordinary_operation_120s": ordinary_result,
        "long_gaps": long_result,
        "conclusion": {
            "beats_reference_mae": (
                mixed["mae_ghs"] < ref["mae_ghs"]
            ),
            "beats_reference_rmse": (
                mixed["rmse_ghs"] < ref["rmse_ghs"]
            ),
            "ordinary_mae_not_worse": (
                ordinary_mix["mae_ghs"] <= ordinary_ref["mae_ghs"]
            ),
            "ordinary_rmse_not_worse": (
                ordinary_mix["rmse_ghs"] <= ordinary_ref["rmse_ghs"]
            ),
            "promotion_recommended": False,
        },
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("HOLDOUT FINAL RIDGE BLEND")
    print("Integridad historica: verificada")
    print("Lambda fija:", f"{lam:.8f}")
    print("Entrenamiento:", len(train_y))
    print("Holdout independiente:", len(actual))

    for label, result in (
        ("GLOBAL", global_result),
        ("OPERACION HABITUAL <=120s", ordinary_result),
        ("INTERVALOS >120s", long_result),
    ):
        print("\n---", label, "---")
        if result.get("n"):
            for method in ("referencia_1h", "ridge_7_dias", "mezcla_calibrada"):
                m = result[method]
                print(
                    f"{method}: MAE={m['mae_ghs']:.6f} | "
                    f"RMSE={m['rmse_ghs']:.6f} GH/s"
                )
        else:
            print("Sin muestras.")

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("Integracion autorizada: NO")


if __name__ == "__main__":
    main()
