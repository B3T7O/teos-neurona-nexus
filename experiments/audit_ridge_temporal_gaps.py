#!/usr/bin/env python3
"""Diagnóstico temporal independiente del primer experimento Ridge de TEOS."""

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]

SNAPSHOT = ROOT / "experiments/frozen_bitaxe_samples.jsonl"
MANIFEST = ROOT / "experiments/frozen_evaluation_manifest.json"
ORIGINAL_SCRIPT = ROOT / "experiments/first_learning_model.py"
ORIGINAL_REPORT = ROOT / "experiments/first_learning_model_report.json"

OUTPUT = ROOT / "experiments/ridge_temporal_gap_report.json"

EXPECTED_SNAPSHOT_SHA256 = (
    "dfdd8f2533d89190e94f5ef113c2a24a43325df1d51c93ad810ff417b53379a5"
)
EXPECTED_SCRIPT_SHA256 = (
    "b1e1a69fd272c09574a89ac866918889065fab5746ed214b98bdd6eaf8bdab7d"
)
EXPECTED_REPORT_SHA256 = (
    "835002b3e7720fcbf9c6d0b6ad450a86ff474d01bf5126aaf75c8d8dc9a752ba"
)

EXPECTED_OOS_SAMPLES = 422
GAP_THRESHOLD_SECONDS = 120.0
METRIC_TOLERANCE = 1e-10

BASE_FIELDS = [
    "hashRate_1h",
    "hashRate_10m",
    "hashRate_1m",
    "hashRate",
    "expectedHashrate",
    "temp",
    "vrTemp",
    "power",
    "voltage",
    "frequency",
    "fanrpm",
    "errorPercentage",
    "wifiRSSI",
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_timestamp(value):
    if not isinstance(value, str):
        raise ValueError(f"Marca temporal inválida: {value!r}")

    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def stop(message):
    raise SystemExit(f"DIAGNÓSTICO DETENIDO: {message}")


def metrics(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    if len(actual) != len(predicted) or len(actual) == 0:
        stop("Conjunto de métricas vacío o desalineado.")

    error = actual - predicted

    return {
        "n": int(len(actual)),
        "mae_ghs": float(np.mean(np.abs(error))),
        "rmse_ghs": float(np.sqrt(np.mean(error ** 2))),
    }


def verify_metric_match(name, reproduced, original):
    if reproduced["n"] != original["n"]:
        stop(f"{name}: no coincide el número de muestras.")

    for field in ("mae_ghs", "rmse_ghs"):
        if not math.isclose(
            reproduced[field],
            original[field],
            rel_tol=METRIC_TOLERANCE,
            abs_tol=METRIC_TOLERANCE,
        ):
            stop(f"{name}: no coincide la métrica {field}.")

    return True


def interval_summary(intervals):
    values = np.asarray(intervals, dtype=float)

    return {
        "count": int(len(values)),
        "min_seconds": float(np.min(values)),
        "median_seconds": float(np.median(values)),
        "p90_seconds": float(np.percentile(values, 90)),
        "max_seconds": float(np.max(values)),
    }


def compare_group(records):
    actual = [r["actual"] for r in records]
    ridge = [r["ridge"] for r in records]
    baseline = [r["baseline_1h"] for r in records]

    ridge_metrics = metrics(actual, ridge)
    baseline_metrics = metrics(actual, baseline)

    baseline_mae = baseline_metrics["mae_ghs"]
    ridge_mae = ridge_metrics["mae_ghs"]

    improvement_pct = (
        (baseline_mae - ridge_mae) / baseline_mae * 100
        if baseline_mae != 0
        else None
    )

    return {
        "n": len(records),
        "ridge": ridge_metrics,
        "previous_hashRate_1h": baseline_metrics,
        "mae_difference_ridge_minus_baseline_ghs": ridge_mae - baseline_mae,
        "mae_improvement_pct": improvement_pct,
    }


def main():
    required = [
        SNAPSHOT,
        MANIFEST,
        ORIGINAL_SCRIPT,
        ORIGINAL_REPORT,
    ]

    for path in required:
        if not path.is_file():
            stop(f"Falta el archivo requerido: {path.relative_to(ROOT)}")

    if OUTPUT.exists():
        stop(
            f"Ya existe {OUTPUT.relative_to(ROOT)}. "
            "No se sobrescribió."
        )

    # 1. Protección de la evidencia original.
    snapshot_hash = sha256(SNAPSHOT)
    script_hash = sha256(ORIGINAL_SCRIPT)
    report_hash = sha256(ORIGINAL_REPORT)

    if snapshot_hash != EXPECTED_SNAPSHOT_SHA256:
        stop("El SHA-256 de la fotografía no coincide con el registrado.")

    if script_hash != EXPECTED_SCRIPT_SHA256:
        stop("El predictor original no coincide con la versión auditada.")

    if report_hash != EXPECTED_REPORT_SHA256:
        stop("El informe original no coincide con el resultado auditado.")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    original_report = json.loads(
        ORIGINAL_REPORT.read_text(encoding="utf-8")
    )

    if manifest.get("sha256") != snapshot_hash:
        stop("La fotografía no coincide con el manifiesto.")

    if original_report.get("snapshot_sha256") != snapshot_hash:
        stop("El informe original no corresponde a esta fotografía.")

    # 2. Reconstrucción idéntica del conjunto original.
    raw = SNAPSHOT.read_bytes()
    rows = []

    for line in raw.splitlines():
        try:
            row = json.loads(line)
            row["_ts"] = row["timestamp"]
            row["_target"] = float(row["hashRate"])
            rows.append(row)
        except (
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
        ):
            continue

    rows.sort(key=lambda r: r["_ts"])

    unique = {}
    for row in rows:
        unique[row["_ts"]] = row

    rows = [unique[t] for t in sorted(unique)]

    parsed_times = {}
    for row in rows:
        try:
            parsed_times[row["_ts"]] = parse_timestamp(row["_ts"])
        except (ValueError, TypeError):
            stop(f"Timestamp no interpretable: {row['_ts']}")

    # 3. Mismas características, objetivos y filtros del Ridge original.
    def feature_at(i):
        previous = rows[i - 1]
        values = []

        for field in BASE_FIELDS:
            value = previous.get(field)

            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                return None

            values.append(float(value))

        for field in ("hashRate", "hashRate_10m", "hashRate_1h"):
            now = previous.get(field)
            earlier = rows[i - 2].get(field) if i >= 2 else None

            if (
                isinstance(now, bool)
                or isinstance(earlier, bool)
                or not isinstance(now, (int, float))
                or not isinstance(earlier, (int, float))
                or not math.isfinite(now)
                or not math.isfinite(earlier)
            ):
                return None

            values.append(float(now) - float(earlier))

        return np.asarray(values, dtype=float)

    X, y, indices = [], [], []

    for i in range(2, len(rows)):
        x = feature_at(i)
        target = rows[i]["_target"]
        baseline = rows[i - 1].get("hashRate_1h")

        if (
            x is None
            or not math.isfinite(target)
            or isinstance(baseline, bool)
            or not isinstance(baseline, (int, float))
            or not math.isfinite(baseline)
        ):
            continue

        X.append(x)
        y.append(target)
        indices.append(i)

    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    indices = np.asarray(indices, dtype=int)

    if len(y) != original_report.get("usable_samples"):
        stop("El número de muestras utilizables no coincide con el original.")

    # 4. Reproducción de los mismos cinco tramos walk-forward.
    bounds = [
        int(len(y) * p)
        for p in (0.50, 0.60, 0.70, 0.80, 0.90, 1.00)
    ]

    fold_results = []
    evaluated = []

    all_actual = []
    all_ridge = []
    all_baseline = []

    for fold in range(5):
        start, end = bounds[fold], bounds[fold + 1]
        train_end = start

        if train_end < 50 or end <= start:
            stop(f"Tramo inválido: {fold + 1}")

        X_train, y_train = X[:train_end], y[:train_end]
        X_test, y_test = X[start:end], y[start:end]

        mu = X_train.mean(axis=0)
        sigma = X_train.std(axis=0)
        sigma[sigma < 1e-9] = 1.0

        A = (X_train - mu) / sigma
        B = (X_test - mu) / sigma

        A = np.column_stack([np.ones(len(A)), A])
        B = np.column_stack([np.ones(len(B)), B])

        penalty = np.eye(A.shape[1]) * 10.0
        penalty[0, 0] = 0.0

        coefficients = np.linalg.solve(
            A.T @ A + penalty,
            A.T @ y_train,
        )

        predictions = B @ coefficients

        baseline = np.asarray([
            float(rows[int(idx) - 1]["hashRate_1h"])
            for idx in indices[start:end]
        ])

        ridge_score = metrics(y_test, predictions)
        baseline_score = metrics(y_test, baseline)

        fold_results.append({
            "fold": fold + 1,
            "train_samples": int(train_end),
            "test_samples": int(end - start),
            "ridge": ridge_score,
            "previous_hashRate_1h": baseline_score,
        })

        for actual, ridge_prediction, base_prediction, idx in zip(
            y_test,
            predictions,
            baseline,
            indices[start:end],
        ):
            target_time = parsed_times[rows[int(idx)]["_ts"]]
            origin_time = parsed_times[rows[int(idx) - 1]["_ts"]]

            gap = (target_time - origin_time).total_seconds()

            if gap < 0:
                stop("Se detectó un intervalo temporal negativo.")

            evaluated.append({
                "actual": float(actual),
                "ridge": float(ridge_prediction),
                "baseline_1h": float(base_prediction),
                "interval_seconds": float(gap),
            })

        all_actual.extend(y_test.tolist())
        all_ridge.extend(predictions.tolist())
        all_baseline.extend(baseline.tolist())

    # 5. Verificar que la reproducción coincide con el informe original.
    if len(evaluated) != EXPECTED_OOS_SAMPLES:
        stop(
            f"Se esperaban {EXPECTED_OOS_SAMPLES} predicciones "
            f"y se obtuvieron {len(evaluated)}."
        )

    original_folds = original_report["folds"]

    if len(original_folds) != len(fold_results):
        stop("No coincide el número de tramos originales.")

    for reproduced, original in zip(fold_results, original_folds):
        verify_metric_match(
            f"Tramo {reproduced['fold']} Ridge",
            reproduced["ridge"],
            original["ridge"],
        )
        verify_metric_match(
            f"Tramo {reproduced['fold']} referencia 1h",
            reproduced["previous_hashRate_1h"],
            original["previous_hashRate_1h"],
        )

    global_ridge = metrics(all_actual, all_ridge)
    global_baseline = metrics(all_actual, all_baseline)

    verify_metric_match(
        "Global Ridge",
        global_ridge,
        original_report["overall"]["ridge"],
    )
    verify_metric_match(
        "Global referencia 1h",
        global_baseline,
        original_report["overall"]["previous_hashRate_1h"],
    )

    # 6. Clasificación por intervalo. Ninguna muestra se elimina.
    normal = [
        r for r in evaluated
        if r["interval_seconds"] <= GAP_THRESHOLD_SECONDS
    ]
    long_gap = [
        r for r in evaluated
        if r["interval_seconds"] > GAP_THRESHOLD_SECONDS
    ]

    groups = {
        "hasta_120_segundos": compare_group(normal),
        "superiores_a_120_segundos": compare_group(long_gap)
        if long_gap else {
            "n": 0,
            "ridge": None,
            "previous_hashRate_1h": None,
            "mae_difference_ridge_minus_baseline_ghs": None,
            "mae_improvement_pct": None,
        },
    }

    intervals = [r["interval_seconds"] for r in evaluated]

    baseline_mae = global_baseline["mae_ghs"]
    ridge_mae = global_ridge["mae_ghs"]

    report = {
        "title": "TEOS NEURONA — Diagnóstico temporal independiente de Ridge",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_sha256": snapshot_hash,
        "original_script_sha256": script_hash,
        "original_report_sha256": report_hash,
        "validation": {
            "original_experiment_reproduced": True,
            "out_of_sample_predictions": len(evaluated),
            "expected_out_of_sample_predictions": EXPECTED_OOS_SAMPLES,
            "five_folds_verified": True,
            "global_metrics_verified": True,
            "metric_tolerance": METRIC_TOLERANCE,
            "same_targets_for_ridge_and_baseline": True,
            "all_evaluated_samples_in_global_metrics": True,
            "original_files_modified": False,
        },
        "interval_definition": {
            "origin": "timestamp de la muestra anterior",
            "target": "timestamp de la muestra evaluada",
            "threshold_seconds": GAP_THRESHOLD_SECONDS,
            "groups": {
                "hasta_120_segundos": "<= 120 segundos",
                "superiores_a_120_segundos": "> 120 segundos",
            },
        },
        "interval_distribution": interval_summary(intervals),
        "global": {
            "n": len(evaluated),
            "ridge": global_ridge,
            "previous_hashRate_1h": global_baseline,
            "mae_difference_ridge_minus_baseline_ghs": (
                ridge_mae - baseline_mae
            ),
            "mae_improvement_pct": (
                (baseline_mae - ridge_mae) / baseline_mae * 100
                if baseline_mae != 0 else None
            ),
        },
        "by_interval": groups,
        "folds": fold_results,
        "warning": (
            "El resultado global conserva todas las predicciones. "
            "Los grupos por intervalo son un diagnóstico descriptivo; "
            "los grupos pequeños no permiten conclusiones estadísticas "
            "firmes ni demuestran causalidad."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA — AUDITORÍA TEMPORAL RIDGE")
    print("Integridad de datos y código: verificada")
    print("Reproducción del experimento original: SUPERADA")
    print("Predicciones fuera de muestra:", len(evaluated))
    print("Cinco tramos y métricas originales: verificados")

    print("\n--- RESULTADO GLOBAL ---")
    print(
        f"Ridge MAE: {ridge_mae:.6f} GH/s | "
        f"RMSE: {global_ridge['rmse_ghs']:.6f}"
    )
    print(
        f"Referencia 1h MAE: {baseline_mae:.6f} GH/s | "
        f"RMSE: {global_baseline['rmse_ghs']:.6f}"
    )
    print(
        "Mejora MAE Ridge:",
        f"{report['global']['mae_improvement_pct']:.4f}%",
    )

    print("\n--- RESULTADO POR INTERVALO ---")
    for name, result in groups.items():
        print(f"\n{name}: n={result['n']}")

        if result["n"] == 0:
            print("Sin muestras.")
            continue

        print(
            f"Ridge MAE: {result['ridge']['mae_ghs']:.6f} GH/s"
        )
        print(
            "Referencia 1h MAE:",
            f"{result['previous_hashRate_1h']['mae_ghs']:.6f} GH/s",
        )
        print(
            "Diferencia MAE Ridge - referencia:",
            f"{result['mae_difference_ridge_minus_baseline_ghs']:+.6f} GH/s",
        )

    print("\nInforme nuevo:", OUTPUT.relative_to(ROOT))
    print("Predictor original, fotografía y sistema en vivo: intactos.")


if __name__ == "__main__":
    main()
