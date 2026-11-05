#!/usr/bin/env python3
"""Evaluacion prospectiva de Ridge residual condicionado por tendencia."""

import sys
import json
import hashlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_ridge_prospective as core

OUTPUT = core.ROOT / "experiments/ridge_trend_residual_fresh_report.json"
FRESH_CUTOFF = core.parse_timestamp("2026-11-03T13:29:57.522601+00:00")
TREND_INDEX = core.FEATURES.index("delta_hashRate")
SELECTED = np.asarray([
    core.FEATURES.index(f) for f in core.REDUCED_FEATURES
])


def stop(message):
    raise SystemExit(f"EVALUACION DETENIDA: {message}")


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(records):
    if not records:
        return {"n": 0}

    actual = [r["actual"] for r in records]
    baseline = [r["baseline"] for r in records]
    candidate = [r["candidate"] for r in records]

    ref = core.metrics(actual, baseline)
    model = core.metrics(actual, candidate)

    return {
        "n": len(records),
        "referencia_1h": ref,
        "ridge_condicionado": model,
        "delta_mae_vs_referencia_ghs": (
            model["mae_ghs"] - ref["mae_ghs"]
        ),
        "delta_rmse_vs_referencia_ghs": (
            model["rmse_ghs"] - ref["rmse_ghs"]
        ),
    }


def main():
    if OUTPUT.exists():
        stop(f"El informe ya existe; no se sobrescribio: {OUTPUT.name}")

    for path, expected in core.EXPECTED_HASHES.items():
        if not path.is_file() or sha256_file(path) != expected:
            stop(f"Integridad no verificada: {path.name}")

    frozen, snapshot_hash = core.load_frozen()
    manifest = json.loads(core.MANIFEST.read_text())
    original = json.loads(core.ORIGINAL.read_text())
    candidate_report = json.loads(core.CANDIDATE.read_text())

    definition = candidate_report.get("candidate_definition", {})

    if (
        manifest.get("sha256") != snapshot_hash
        or original.get("snapshot_sha256") != snapshot_hash
        or candidate_report.get("integrity", {}).get(
            "snapshot_sha256"
        ) != snapshot_hash
        or definition.get("retained_features") != core.REDUCED_FEATURES
    ):
        stop("La fotografia o la definicion historica no coincide.")

    training_cutoff = frozen[-1]["_dt"]

    # Construir residuos historicos sin utilizar datos futuros.
    train_x = []
    train_residual = []
    train_trend = []

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
        train_trend.append(float(x[TREND_INDEX]))

    if len(train_x) != original.get("usable_samples"):
        stop("El numero de muestras historicas no coincide.")

    train_x = np.asarray(train_x, dtype=float)
    train_residual = np.asarray(train_residual, dtype=float)
    train_trend = np.asarray(train_trend, dtype=float)

    up_train = train_trend > 0
    down_train = train_trend < 0
    stable_train = train_trend == 0

    if min(up_train.sum(), down_train.sum()) < 30:
        stop("Muestras insuficientes para entrenar ambos regimenes.")

    # Cargar RAW y verificar continuidad historica.
    historical, future, invalid, duplicates, raw_hash = (
        core.load_raw_future(training_cutoff)
    )
    core.verify_context(frozen, historical)

    # La prueba solo acepta objetivos posteriores al corte independiente.
    stream = [frozen[-2], frozen[-1]] + future
    test_x = []
    actual = []
    baseline = []
    intervals = []
    timestamps = []
    skipped = 0

    for i in range(2, len(stream)):
        previous = stream[i - 1]
        earlier = stream[i - 2]
        target = stream[i]

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
        stop("No hay pares futuros validos despues del corte.")

    test_x = np.asarray(test_x, dtype=float)
    actual = np.asarray(actual, dtype=float)
    baseline = np.asarray(baseline, dtype=float)
    test_trend = test_x[:, TREND_INDEX]

    # Entrenar un modelo residual por regimen, solo con datos congelados.
    up_prediction = core.fit_predict(
        train_x[up_train],
        train_residual[up_train],
        test_x,
        SELECTED,
    )
    down_prediction = core.fit_predict(
        train_x[down_train],
        train_residual[down_train],
        test_x,
        SELECTED,
    )

    # La tendencia se determina usando exclusivamente el contexto previo.
    prediction = baseline.copy()
    up_test = test_trend > 0
    down_test = test_trend < 0
    stable_test = test_trend == 0

    prediction[up_test] += up_prediction[up_test]
    prediction[down_test] += down_prediction[down_test]
    # En estable se conserva baseline sin correccion.

    records = []
    for i in range(len(actual)):
        records.append({
            "timestamp": timestamps[i],
            "actual": float(actual[i]),
            "baseline": float(baseline[i]),
            "candidate": float(prediction[i]),
            "trend": float(test_trend[i]),
            "interval_seconds": float(intervals[i]),
        })

    global_result = compare(records)

    by_trend = {
        "subida": compare([r for r in records if r["trend"] > 0]),
        "bajada": compare([r for r in records if r["trend"] < 0]),
        "estable": compare([r for r in records if r["trend"] == 0]),
    }

    by_interval = {
        "hasta_120_segundos": compare([
            r for r in records if r["interval_seconds"] <= 120
        ]),
        "superiores_a_120_segundos": compare([
            r for r in records if r["interval_seconds"] > 120
        ]),
    }

    ref = global_result["referencia_1h"]
    model = global_result["ridge_condicionado"]

    report = {
        "title": "TEOS NEURONA - Ridge residual condicionado",
        "integrity": {
            "snapshot_sha256": snapshot_hash,
            "raw_sha256": raw_hash,
            "original_files_modified": False,
        },
        "validation": {
            "training_samples": len(train_x),
            "training_up": int(up_train.sum()),
            "training_down": int(down_train.sum()),
            "training_stable": int(stable_train.sum()),
            "training_cutoff_utc": training_cutoff.isoformat(),
            "fresh_evaluation_cutoff_utc": FRESH_CUTOFF.isoformat(),
            "fresh_raw_rows": sum(
                row["_dt"] > FRESH_CUTOFF for row in future
            ),
            "valid_future_pairs": len(records),
            "skipped_pairs": skipped,
            "invalid_raw_records": invalid,
            "duplicate_raw_timestamps": duplicates,
            "future_data_used_for_training": False,
            "model_refitted_during_evaluation": False,
            "rolling_one_step_ahead": True,
            "stable_regime_uses_reference": True,
            "ridge_alpha": core.ALPHA,
            "features": list(core.REDUCED_FEATURES),
            "promotion_authorized": False,
        },
        "evaluation_period_utc": {
            "first_target": timestamps[0],
            "last_target": timestamps[-1],
        },
        "global": global_result,
        "by_trend": by_trend,
        "by_interval": by_interval,
        "conclusion": {
            "beats_reference_mae": model["mae_ghs"] < ref["mae_ghs"],
            "beats_reference_rmse": model["rmse_ghs"] < ref["rmse_ghs"],
            "promotion_recommended": False,
        },
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA - RIDGE CONDICIONADO")
    print("Integridad historica: verificada")
    print("Entrenamiento total:", len(train_x))
    print("Entrenamiento subida:", int(up_train.sum()))
    print("Entrenamiento bajada:", int(down_train.sum()))
    print("Entrenamiento estable:", int(stable_train.sum()))
    print("Pares nuevos evaluados:", len(records))
    print("Reentrenamiento futuro: NO")

    for label, result in [
        ("GLOBAL", global_result),
        ("OPERACION HABITUAL <=120s", by_interval["hasta_120_segundos"]),
        ("SUBIDA", by_trend["subida"]),
        ("BAJADA", by_trend["bajada"]),
        ("ESTABLE", by_trend["estable"]),
    ]:
        print(f"\n--- {label} ---")
        if result.get("n"):
            for method in ("referencia_1h", "ridge_condicionado"):
                m = result[method]
                print(
                    f"{method}: MAE={m['mae_ghs']:.6f} | "
                    f"RMSE={m['rmse_ghs']:.6f} GH/s"
                )
        else:
            print("Sin muestras.")

    print("\nInforme:", OUTPUT.relative_to(core.ROOT))
    print("Integracion autorizada: NO")


if __name__ == "__main__":
    main()
