#!/usr/bin/env python3
"""Evaluación prospectiva de Ridge sobre muestras posteriores al conjunto congelado."""

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

SNAPSHOT = ROOT / "experiments/frozen_bitaxe_samples.jsonl"
MANIFEST = ROOT / "experiments/frozen_evaluation_manifest.json"
SCRIPT = ROOT / "experiments/first_learning_model.py"
ORIGINAL = ROOT / "experiments/first_learning_model_report.json"
CANDIDATE = ROOT / "experiments/ridge_reduced_candidate_report.json"
RAW = ROOT / "data/raw/bitaxe_samples.jsonl"

OUTPUT = ROOT / "experiments/ridge_prospective_report.json"

EXPECTED_HASHES = {
    SNAPSHOT: "dfdd8f2533d89190e94f5ef113c2a24a43325df1d51c93ad810ff417b53379a5",
    SCRIPT: "b1e1a69fd272c09574a89ac866918889065fab5746ed214b98bdd6eaf8bdab7d",
    ORIGINAL: "835002b3e7720fcbf9c6d0b6ad450a86ff474d01bf5126aaf75c8d8dc9a752ba",
}

BASE_FIELDS = [
    "hashRate_1h", "hashRate_10m", "hashRate_1m",
    "hashRate", "expectedHashrate", "temp", "vrTemp",
    "power", "voltage", "frequency", "fanrpm",
    "errorPercentage", "wifiRSSI",
]

FEATURES = BASE_FIELDS + [
    "delta_hashRate",
    "delta_hashRate_10m",
    "delta_hashRate_1h",
]

REMOVED_FEATURES = [
    "expectedHashrate",
    "frequency",
    "voltage",
    "fanrpm",
    "errorPercentage",
    "hashRate_10m",
]

REDUCED_FEATURES = [
    f for f in FEATURES if f not in REMOVED_FEATURES
]

ALPHA = 10.0


def stop(message):
    raise SystemExit(f"EVALUACIÓN PROSPECTIVA DETENIDA: {message}")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(path.read_bytes())


def parse_timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp inválido.")

    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def valid_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def metrics(actual, predicted):
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    if len(actual) == 0 or len(actual) != len(predicted):
        stop("Conjunto de evaluación vacío o desalineado.")

    error = actual - predicted

    return {
        "n": int(len(actual)),
        "mae_ghs": float(np.mean(np.abs(error))),
        "rmse_ghs": float(np.sqrt(np.mean(error ** 2))),
    }


def compare_methods(records):
    actual = [r["actual"] for r in records]
    original = [r["ridge_original"] for r in records]
    reduced = [r["ridge_reducido"] for r in records]
    baseline = [r["baseline_1h"] for r in records]

    if not records:
        return {"n": 0}

    original_metrics = metrics(actual, original)
    reduced_metrics = metrics(actual, reduced)
    baseline_metrics = metrics(actual, baseline)

    return {
        "n": len(records),
        "ridge_original": original_metrics,
        "ridge_reducido": reduced_metrics,
        "referencia_1h": baseline_metrics,
        "mae_delta_reducido_vs_original_ghs": (
            reduced_metrics["mae_ghs"] - original_metrics["mae_ghs"]
        ),
        "mae_delta_reducido_vs_referencia_ghs": (
            reduced_metrics["mae_ghs"] - baseline_metrics["mae_ghs"]
        ),
        "reducido_supera_original": (
            reduced_metrics["mae_ghs"] < original_metrics["mae_ghs"]
        ),
        "reducido_supera_referencia": (
            reduced_metrics["mae_ghs"] < baseline_metrics["mae_ghs"]
        ),
    }


def fit_predict(train_x, train_y, test_x, selected):
    # Escalado exclusivamente con las muestras congeladas.
    A0 = train_x[:, selected]
    B0 = test_x[:, selected]

    mu = A0.mean(axis=0)
    sigma = A0.std(axis=0)
    sigma[sigma < 1e-9] = 1.0

    A = (A0 - mu) / sigma
    B = (B0 - mu) / sigma

    A = np.column_stack([np.ones(len(A)), A])
    B = np.column_stack([np.ones(len(B)), B])

    penalty = np.eye(A.shape[1]) * ALPHA
    penalty[0, 0] = 0.0

    coefficients = np.linalg.solve(
        A.T @ A + penalty,
        A.T @ train_y,
    )

    return B @ coefficients


def load_frozen():
    raw = SNAPSHOT.read_bytes()
    rows = []

    for line in raw.splitlines():
        try:
            row = json.loads(line)
            row["_ts"] = row["timestamp"]
            row["_target"] = float(row["hashRate"])
            row["_dt"] = parse_timestamp(row["_ts"])
            rows.append(row)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue

    # Misma ordenación y deduplicación del experimento original.
    rows.sort(key=lambda r: r["_ts"])

    unique = {}
    for row in rows:
        unique[row["_ts"]] = row

    rows = [unique[t] for t in sorted(unique)]

    return rows, sha256_bytes(raw)


def load_raw_future(cutoff):
    raw_bytes = RAW.read_bytes()
    by_time = {}
    invalid = 0
    duplicates = 0

    for line in raw_bytes.splitlines():
        try:
            row = json.loads(line)
            dt = parse_timestamp(row.get("timestamp"))
            hr = row.get("hashRate")

            if not valid_number(hr):
                invalid += 1
                continue

            row["_dt"] = dt

            if dt in by_time:
                duplicates += 1

            by_time[dt] = row

        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            invalid += 1

    ordered = sorted(by_time.items())

    historical = [
        row for dt, row in ordered if dt <= cutoff
    ]
    future = [
        row for dt, row in ordered if dt > cutoff
    ]

    return (
        historical,
        future,
        invalid,
        duplicates,
        sha256_bytes(raw_bytes),
    )


def verify_context(frozen_rows, raw_historical):
    if len(frozen_rows) < 2 or len(raw_historical) < 2:
        stop("No hay dos muestras históricas para verificar continuidad.")

    expected = frozen_rows[-2:]
    observed = raw_historical[-2:]

    for index in range(2):
        frozen = expected[index]
        raw = observed[index]

        if frozen["_dt"] != raw["_dt"]:
            stop("Las últimas marcas históricas RAW no coinciden con la fotografía.")

        for field in ["timestamp"] + BASE_FIELDS:
            if frozen.get(field) != raw.get(field):
                stop(
                    f"Contexto histórico diferente en "
                    f"{field}, muestra {index + 1}."
                )


def feature_at(previous, earlier):
    values = []

    for field in BASE_FIELDS:
        value = previous.get(field)

        if not valid_number(value):
            return None

        values.append(float(value))

    for field in ("hashRate", "hashRate_10m", "hashRate_1h"):
        now = previous.get(field)
        before = earlier.get(field)

        if not valid_number(now) or not valid_number(before):
            return None

        values.append(float(now) - float(before))

    return np.asarray(values, dtype=float)


def main():
    required = [
        SNAPSHOT, MANIFEST, SCRIPT,
        ORIGINAL, CANDIDATE, RAW,
    ]

    for path in required:
        if not path.is_file():
            stop(f"Falta el archivo {path.name}.")

    if OUTPUT.exists():
        stop(f"El informe ya existe. No se sobrescribió: {OUTPUT.name}")

    # Integridad de la evidencia histórica.
    for path, expected in EXPECTED_HASHES.items():
        if sha256_file(path) != expected:
            stop(f"SHA-256 inesperado: {path.name}")

    frozen, snapshot_hash = load_frozen()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    original = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))

    if manifest.get("sha256") != snapshot_hash:
        stop("La fotografía no coincide con el manifiesto.")

    if original.get("snapshot_sha256") != snapshot_hash:
        stop("El informe original no corresponde a la fotografía.")

    if candidate.get("integrity", {}).get("snapshot_sha256") != snapshot_hash:
        stop("El candidato no corresponde a la fotografía congelada.")

    definition = candidate.get("candidate_definition", {})

    if definition.get("removed_features") != REMOVED_FEATURES:
        stop("Las características retiradas no coinciden con el candidato.")

    if definition.get("retained_features") != REDUCED_FEATURES:
        stop("Las características conservadas no coinciden con el candidato.")

    validation = candidate.get("validation", {})

    if (
        validation.get("original_experiment_reproduced") is not True
        or validation.get("out_of_sample_targets") != 422
        or validation.get("same_targets_for_all_three_methods") is not True
    ):
        stop("El informe previo del candidato no está validado.")

    if len(frozen) != original.get("valid_unique_records"):
        stop("No coincide el número de registros congelados.")

    cutoff = frozen[-1]["_dt"]

    # 1. Construir entrenamiento exclusivamente con la fotografía.
    train_x = []
    train_y = []

    for i in range(2, len(frozen)):
        x = feature_at(frozen[i - 1], frozen[i - 2])
        target = frozen[i]["_target"]
        baseline = frozen[i - 1].get("hashRate_1h")

        if (
            x is None
            or not math.isfinite(target)
            or not valid_number(baseline)
        ):
            continue

        train_x.append(x)
        train_y.append(target)

    train_x = np.asarray(train_x, dtype=float)
    train_y = np.asarray(train_y, dtype=float)

    if len(train_y) != original.get("usable_samples"):
        stop("No coincide el conjunto de entrenamiento original.")

    # 2. Cargar las muestras que aparecieron después del corte.
    raw_historical, future, invalid, duplicates, raw_hash = (
        load_raw_future(cutoff)
    )

    # Verificar continuidad entre fotografía congelada y RAW.
    verify_context(frozen, raw_historical)

    if not future:
        stop("No hay muestras posteriores al corte.")

    # 3. Preparar objetivos futuros con información disponible
    # en el instante de cada predicción.
    stream = [frozen[-2], frozen[-1]] + future

    test_x = []
    actual = []
    baseline = []
    intervals = []
    target_times = []
    skipped = 0

    for i in range(2, len(stream)):
        previous = stream[i - 1]
        earlier = stream[i - 2]
        target = stream[i]

        x = feature_at(previous, earlier)
        y = target.get("hashRate")
        base = previous.get("hashRate_1h")
        interval = (
            target["_dt"] - previous["_dt"]
        ).total_seconds()

        if (
            x is None
            or not valid_number(y)
            or not valid_number(base)
            or interval <= 0
        ):
            skipped += 1
            continue

        test_x.append(x)
        actual.append(float(y))
        baseline.append(float(base))
        intervals.append(float(interval))
        target_times.append(target["_dt"])

    if not test_x:
        stop("No hay pares futuros válidos para evaluar.")

    test_x = np.asarray(test_x, dtype=float)
    actual = np.asarray(actual, dtype=float)
    baseline = np.asarray(baseline, dtype=float)

    # 4. Entrenar una sola vez con el conjunto histórico completo.
    # No existe reentrenamiento durante el período futuro.
    full_selected = np.arange(len(FEATURES))
    reduced_selected = np.asarray([
        FEATURES.index(f) for f in REDUCED_FEATURES
    ])

    prediction_original = fit_predict(
        train_x, train_y, test_x, full_selected
    )

    prediction_reduced = fit_predict(
        train_x, train_y, test_x, reduced_selected
    )

    records = []

    for i in range(len(actual)):
        records.append({
            "timestamp": target_times[i].isoformat(),
            "actual": float(actual[i]),
            "ridge_original": float(prediction_original[i]),
            "ridge_reducido": float(prediction_reduced[i]),
            "baseline_1h": float(baseline[i]),
            "interval_seconds": intervals[i],
        })

    # 5. Resultado global.
    global_result = compare_methods(records)

    # 6. Resultado por intervalo.
    regular = [
        r for r in records if r["interval_seconds"] <= 120
    ]
    long_gaps = [
        r for r in records if r["interval_seconds"] > 120
    ]

    interval_result = {
        "hasta_120_segundos": compare_methods(regular),
        "superiores_a_120_segundos": compare_methods(long_gaps),
    }

    # 7. Resultado diario UTC para detectar cambios de rendimiento.
    by_day = defaultdict(list)

    for record in records:
        day = record["timestamp"][:10]
        by_day[day].append(record)

    daily = {
        day: compare_methods(items)
        for day, items in sorted(by_day.items())
    }

    daily_wins_original = sum(
        item["ridge_reducido"]["mae_ghs"]
        < item["ridge_original"]["mae_ghs"]
        for item in daily.values()
    )

    daily_wins_baseline = sum(
        item["ridge_reducido"]["mae_ghs"]
        < item["referencia_1h"]["mae_ghs"]
        for item in daily.values()
    )

    interval_values = np.asarray(intervals, dtype=float)

    original_mae = global_result["ridge_original"]["mae_ghs"]
    reduced_mae = global_result["ridge_reducido"]["mae_ghs"]
    baseline_mae = global_result["referencia_1h"]["mae_ghs"]

    report = {
        "title": "TEOS NEURONA — Validación prospectiva Ridge",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "integrity": {
            "snapshot_sha256": snapshot_hash,
            "raw_sha256": raw_hash,
            "original_script_sha256": sha256_file(SCRIPT),
            "original_report_sha256": sha256_file(ORIGINAL),
            "candidate_report_sha256": sha256_file(CANDIDATE),
            "original_files_modified": False,
        },
        "validation": {
            "training_source": "fotografía congelada",
            "training_cutoff_utc": cutoff.isoformat(),
            "training_samples": len(train_y),
            "future_raw_rows": len(future),
            "valid_future_pairs": len(records),
            "future_pairs_skipped": skipped,
            "invalid_raw_records": invalid,
            "duplicate_raw_timestamps": duplicates,
            "historical_context_matches_frozen_snapshot": True,
            "future_data_used_for_training": False,
            "model_refitted_during_evaluation": False,
            "same_future_targets_for_all_methods": True,
            "rolling_one_step_ahead": True,
            "previous_observed_sample_used_as_input": True,
            "ridge_alpha": ALPHA,
            "original_feature_count": len(FEATURES),
            "reduced_feature_count": len(REDUCED_FEATURES),
            "promotion_authorized": False,
        },
        "evaluation_period_utc": {
            "first_target": target_times[0].isoformat(),
            "last_target": target_times[-1].isoformat(),
        },
        "global": global_result,
        "interval_distribution_seconds": {
            "count": int(len(interval_values)),
            "median": float(np.median(interval_values)),
            "p90": float(np.percentile(interval_values, 90)),
            "maximum": float(np.max(interval_values)),
        },
        "by_interval": interval_result,
        "by_utc_day": daily,
        "daily_summary": {
            "days_evaluated": len(daily),
            "days_reduced_beats_original": daily_wins_original,
            "days_reduced_beats_baseline": daily_wins_baseline,
        },
        "conclusion": {
            "reduced_beats_original_globally": (
                reduced_mae < original_mae
            ),
            "reduced_beats_baseline_globally": (
                reduced_mae < baseline_mae
            ),
            "reduced_improvement_vs_original_pct": (
                (original_mae - reduced_mae) / original_mae * 100
                if original_mae else None
            ),
            "reduced_improvement_vs_baseline_pct": (
                (baseline_mae - reduced_mae) / baseline_mae * 100
                if baseline_mae else None
            ),
            "model_promotion_recommended": False,
        },
        "warning": (
            "Prueba prospectiva con pesos fijos y evaluación rolling "
            "one-step-ahead. Cada predicción utiliza la muestra real "
            "inmediatamente anterior, pero no se reentrena el modelo. "
            "Los resultados no autorizan integración en vivo ni sustitución "
            "del predictor sin revisión adicional."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA — VALIDACIÓN PROSPECTIVA")
    print("Integridad histórica: verificada")
    print("Continuidad RAW/fotografía: verificada")
    print("Muestras de entrenamiento:", len(train_y))
    print("Muestras futuras RAW:", len(future))
    print("Pares futuros válidos:", len(records))
    print("Modelos reentrenados durante la prueba: NO")

    print("\n--- RESULTADO GLOBAL ---")

    for name in ("ridge_original", "ridge_reducido", "referencia_1h"):
        item = global_result[name]
        print(
            f"{name}: MAE={item['mae_ghs']:.6f} | "
            f"RMSE={item['rmse_ghs']:.6f} GH/s"
        )

    print(
        "\nMejora reducido vs original:",
        f"{report['conclusion']['reduced_improvement_vs_original_pct']:+.4f}%",
    )
    print(
        "Mejora reducido vs referencia:",
        f"{report['conclusion']['reduced_improvement_vs_baseline_pct']:+.4f}%",
    )

    print("\n--- RESULTADO POR INTERVALO ---")

    for name, result in interval_result.items():
        print(f"\n{name}: n={result['n']}")

        if result["n"]:
            print(
                "Ridge original MAE:",
                f"{result['ridge_original']['mae_ghs']:.6f}"
            )
            print(
                "Ridge reducido MAE:",
                f"{result['ridge_reducido']['mae_ghs']:.6f}"
            )
            print(
                "Referencia 1h MAE:",
                f"{result['referencia_1h']['mae_ghs']:.6f}"
            )

    print("\nDías evaluados:", len(daily))
    print("Días reducido supera original:", daily_wins_original)
    print("Días reducido supera referencia:", daily_wins_baseline)

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("Modelo original, fotografía y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
