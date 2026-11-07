#!/usr/bin/env python3
# Copyright (c) 2026 Luis Alberto Siguencia Andrade (B3T7O)
# SPDX-License-Identifier: Apache-2.0
#
# TEOS Neurona Nexus - Reference Implementation
# https://github.com/[TU_USUARIO]/teos-neurona-nexus

"""Modelo Ridge operativo experimental para TEOS NEURONA.
Lee el historico; registra predicciones y resultados en archivos separados.
No modifica el colector ni los registros originales.
"""

import json
import hashlib
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/bitaxe_samples.jsonl"
OUT = ROOT / "data/processed"
PRED = OUT / "ridge_live_predictions.jsonl"
RESULTS = OUT / "ridge_live_outcomes.jsonl"
REPORT = OUT / "ridge_live_report.json"
MODEL_STATE = OUT / "neurona_ridge_model_state.json"

BASE_FIELDS = (
    "hashRate_1h", "hashRate_10m", "hashRate_1m", "hashRate",
    "expectedHashrate", "temp", "vrTemp", "power", "voltage",
    "frequency", "fanrpm", "errorPercentage", "wifiRSSI",
)
METHODS = (
    "ridge_live", "ultimo_hashrate", "referencia_10m",
    "referencia_1h", "media_ultimas_5",
)
MIN_TRAIN = 100
ALPHA = 10.0


def read_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
            except (json.JSONDecodeError, TypeError):
                continue
    return rows


def append_jsonl(path, item):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")


def parse_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, OverflowError):
        return None


def finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def positive_number(row, *keys):
    for key in keys:
        value = finite_number(row.get(key))
        if value is not None and value > 0:
            return value
    return None


def feature_pair(previous, earlier):
    values = []
    for field in BASE_FIELDS:
        value = finite_number(previous.get(field))
        if value is None:
            return None
        values.append(value)

    for field in ("hashRate", "hashRate_10m", "hashRate_1h"):
        now = finite_number(previous.get(field))
        before = finite_number(earlier.get(field))
        if now is None or before is None:
            return None
        values.append(now - before)

    return np.asarray(values, dtype=float)


def read_quarantined_timestamps():
    ledger = OUT / "anomaly_events.jsonl"
    quarantined = set()
    for row in read_jsonl(ledger):
        epoch = parse_time(row.get("timestamp"))
        if epoch is not None:
            quarantined.add(epoch)
    return quarantined


def load_samples():
    if not RAW.exists():
        raise RuntimeError(f"No existe el historico: {RAW}")

    unique = {}
    quarantined = read_quarantined_timestamps()
    for row in read_jsonl(RAW):
        ts = row.get("timestamp") or row.get("captured_at") or row.get("datetime")
        epoch = parse_time(ts)
        actual = positive_number(row, "hashRate", "hashrate", "hashrate_GHs")
        if epoch is None or actual is None or epoch in quarantined:
            continue
        unique[str(ts)] = {
            "timestamp": str(ts),
            "_time": epoch,
            "actual": actual,
            "raw": row,
            "rate_10m": positive_number(row, "hashRate_10m", "hashrate_10m_GHs"),
            "rate_1h": positive_number(row, "hashRate_1h", "hashrate_1h_GHs"),
        }
    return sorted(unique.values(), key=lambda s: s["_time"])


def fit_model(samples):
    xs, ys = [], []

    for i in range(2, len(samples)):
        x = feature_pair(
            samples[i - 1]["raw"],
            samples[i - 2]["raw"]
        )
        if x is not None:
            xs.append(x)
            ys.append(samples[i]["actual"])

    if len(ys) < MIN_TRAIN:
        return None, len(ys)

    X = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)

    # El escalado se calcula únicamente con las filas de entrenamiento.
    mu = X.mean(axis=0)
    sigma = X.std(axis=0)
    sigma[sigma < 1e-9] = 1.0

    A = (X - mu) / sigma
    A = np.column_stack((np.ones(len(A)), A))

    penalty = np.eye(A.shape[1]) * ALPHA
    penalty[0, 0] = 0.0
    coefficients = np.linalg.solve(
        A.T @ A + penalty,
        A.T @ y
    )

    latest_x = feature_pair(
        samples[-1]["raw"],
        samples[-2]["raw"]
    )
    if latest_x is None:
        return None, len(ys)

    z = (latest_x - mu) / sigma
    prediction = float(np.r_[1.0, z] @ coefficients)

    if not math.isfinite(prediction) or prediction <= 0:
        return None, len(ys)

    feature_names = list(BASE_FIELDS) + [
        "delta_hashRate",
        "delta_hashRate_10m",
        "delta_hashRate_1h",
    ]

    parameters = {
        "intercept": float(coefficients[0]),
        "coefficients": [float(v) for v in coefficients[1:]],
        "feature_mean": [float(v) for v in mu],
        "feature_scale": [float(v) for v in sigma],
    }

    canonical = json.dumps(
        parameters,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    previous_state = None
    if MODEL_STATE.exists():
        try:
            previous_state = json.loads(
                MODEL_STATE.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            previous_state = None

    previous_fingerprint = (
        previous_state.get("parameter_sha256")
        if isinstance(previous_state, dict)
        else None
    )

    delta_l2 = None
    previous_coefficients = (
        previous_state.get("parameters", {}).get("coefficients")
        if isinstance(previous_state, dict)
        else None
    )
    previous_intercept = (
        previous_state.get("parameters", {}).get("intercept")
        if isinstance(previous_state, dict)
        else None
    )

    if (
        isinstance(previous_coefficients, list)
        and len(previous_coefficients) == len(parameters["coefficients"])
        and isinstance(previous_intercept, (int, float))
    ):
        old_vector = np.asarray(
            [previous_intercept] + previous_coefficients,
            dtype=float
        )
        new_vector = np.asarray(
            [parameters["intercept"]] + parameters["coefficients"],
            dtype=float
        )
        delta_l2 = float(np.linalg.norm(new_vector - old_vector))

    state = {
        "model": "TEOS NEURONA Ridge",
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "training_samples": len(ys),
        "minimum_training_samples": MIN_TRAIN,
        "alpha": ALPHA,
        "feature_names": feature_names,
        "parameters": parameters,
        "parameter_sha256": fingerprint,
        "previous_parameter_sha256": previous_fingerprint,
        "parameters_changed": (
            previous_fingerprint is not None
            and previous_fingerprint != fingerprint
        ),
        "parameter_delta_l2": delta_l2,
        "trained_through_timestamp": samples[-1]["timestamp"],
        "prediction_source_timestamp": samples[-1]["timestamp"],
        "prediction_GHs": prediction,
        "training_method": "Ridge recalculado con el historial disponible",
        "uses_future_data": False,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    temp_state = MODEL_STATE.with_suffix(".json.tmp")
    temp_state.write_text(
        json.dumps(state, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    temp_state.replace(MODEL_STATE)

    return prediction, len(ys)


def resolve_pending(samples):
    predictions = read_jsonl(PRED)
    outcomes = read_jsonl(RESULTS)
    done = {o.get("prediction_id") for o in outcomes}
    added = 0

    for pred in predictions:
        pid = pred.get("prediction_id")
        if not pid or pid in done:
            continue

        source_time = parse_time(pred.get("source_timestamp"))
        if source_time is None:
            continue

        future = next((s for s in samples if s["_time"] > source_time), None)
        if future is None:
            continue

        actual = future["actual"]
        forecast = float(pred["predicted_hashRate_GHs"])
        error = actual - forecast
        append_jsonl(RESULTS, {
            "prediction_id": pid,
            "method": pred["method"],
            "source_timestamp": pred["source_timestamp"],
            "target_timestamp": future["timestamp"],
            "predicted_hashRate_GHs": round(forecast, 6),
            "actual_hashRate_GHs": round(actual, 6),
            "error_GHs": round(error, 6),
            "absolute_error_GHs": round(abs(error), 6),
            "squared_error_GH2": round(error * error, 6),
        })
        done.add(pid)
        added += 1

    return added


def summarize(outcomes):
    by_method = {}
    for method in METHODS:
        rows = [
            o for o in outcomes
            if o.get("method") == method
            and finite_number(o.get("error_GHs")) is not None
        ]
        by_method[method] = {
            "n": len(rows),
            "mae_GHs": (
                sum(abs(float(o["error_GHs"])) for o in rows) / len(rows)
                if rows else None
            ),
            "rmse_GHs": (
                math.sqrt(sum(float(o["error_GHs"]) ** 2 for o in rows) / len(rows))
                if rows else None
            ),
            "target_timestamps": sorted(
                {o["target_timestamp"] for o in rows if o.get("target_timestamp")}
            ),
        }

    sets = [set(by_method[m]["target_timestamps"]) for m in METHODS]
    common = set.intersection(*sets) if sets else set()
    matched = {}
    for method in METHODS:
        rows = [
            o for o in outcomes
            if o.get("method") == method
            and o.get("target_timestamp") in common
            and finite_number(o.get("error_GHs")) is not None
        ]
        matched[method] = {
            "n": len(rows),
            "mae_GHs": (
                sum(abs(float(o["error_GHs"])) for o in rows) / len(rows)
                if rows else None
            ),
            "rmse_GHs": (
                math.sqrt(sum(float(o["error_GHs"]) ** 2 for o in rows) / len(rows))
                if rows else None
            ),
        }

    return by_method, matched, len(common)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    samples = load_samples()
    if len(samples) < 5:
        print(f"RIDGE LIVE: solo hay {len(samples)} muestras validas.")
        return

    # Resolver primero predicciones antiguas con la primera muestra posterior.
    new_outcomes = resolve_pending(samples)

    ridge_forecast, train_n = fit_model(samples)
    latest = samples[-1]
    source = latest["timestamp"]

    # Se exige que el modelo pueda predecir y que las referencias existan.
    # Así todos los métodos se comparan sobre los mismos instantes de origen.
    baselines = {
        "ultimo_hashrate": latest["actual"],
        "referencia_10m": latest["rate_10m"],
        "referencia_1h": latest["rate_1h"],
        "media_ultimas_5": (
            sum(s["actual"] for s in samples[-5:]) / 5
            if len(samples) >= 5 else None
        ),
    }

    created = 0
    if ridge_forecast is not None and all(v is not None for v in baselines.values()):
        predictions = read_jsonl(PRED)
        existing = {p.get("prediction_id") for p in predictions}
        forecasts = {"ridge_live": ridge_forecast, **baselines}

        for method, forecast in forecasts.items():
            pid = f"{source}|{method}"
            if pid in existing:
                continue
            append_jsonl(PRED, {
                "prediction_id": pid,
                "created_at": datetime.now().astimezone().isoformat(),
                "source_timestamp": source,
                "source_hashRate_GHs": round(latest["actual"], 6),
                "predicted_hashRate_GHs": round(float(forecast), 6),
                "method": method,
                "target": "siguiente muestra válida posterior al origen",
                "uses_future_data": False,
                "model": "Ridge alpha=10" if method == "ridge_live" else "baseline",
                "training_samples": train_n,
            })
            created += 1

    outcomes = read_jsonl(RESULTS)
    metrics, matched, common_n = summarize(outcomes)
    report = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "raw_samples": len(samples),
        "training_samples": train_n,
        "minimum_training_samples": MIN_TRAIN,
        "new_predictions": created,
        "new_outcomes": new_outcomes,
        "comparison": metrics,
        "same_target_comparison": {
            "common_target_count": common_n,
            "methods": matched,
        },
        "live_system_replaced": False,
    }
    temp_report = REPORT.with_suffix(".json.tmp")
    temp_report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    temp_report.replace(REPORT)

    print("\n=== TEOS NEURONA | RIDGE LIVE EXPERIMENTAL ===")
    print(f"Muestras historicas: {len(samples)}")
    print(f"Muestras de entrenamiento: {train_n} (minimo {MIN_TRAIN})")
    print(f"Prediccion Ridge: {ridge_forecast if ridge_forecast is not None else 'NO DISPONIBLE'}")
    print(f"Predicciones nuevas: {created}; resultados nuevos: {new_outcomes}")
    print("\nComparacion sobre los mismos objetivos:")
    print(f"{'Metodo':22} {'N':>6} {'MAE GH/s':>12} {'RMSE GH/s':>12}")
    for method, result in matched.items():
        mae = result["mae_GHs"]
        rmse = result["rmse_GHs"]
        print(
            f"{method:22} {result['n']:6d} "
            f"{mae if mae is not None else float('nan'):12.3f} "
            f"{rmse if rmse is not None else float('nan'):12.3f}"
        )
    print("Informe:", REPORT.relative_to(ROOT))
    print("Historico original y V2: intactos.")


if __name__ == "__main__":
    main()
