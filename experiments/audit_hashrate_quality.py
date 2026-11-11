#!/usr/bin/env python3
"""Auditoría de calidad y errores de referencias de hashrate.
No modifica los datos originales ni el estado operativo de TEOS.
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/raw/bitaxe_samples.marked.jsonl"
REPORT = ROOT / "experiments/hashrate_audit_report.json"
WINDOW = 5
TRAIN_FRACTION = 0.70


def parse_time(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        return None


def percentile(values, p):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * p
    lo = int(position)
    hi = min(lo + 1, len(values) - 1)
    weight = position - lo
    return values[lo] * (1 - weight) + values[hi] * weight


def load_data():
    by_time = {}
    invalid = 0
    duplicates = 0

    with SOURCE.open(encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
                ts = parse_time(item.get("timestamp"))
                hr = item.get("hashRate")
                if (
                    ts is None
                    or isinstance(hr, bool)
                    or not isinstance(hr, (int, float))
                    or not math.isfinite(hr)
                    or hr < 0
                ):
                    invalid += 1
                    continue
                if ts in by_time:
                    duplicates += 1
                by_time[ts] = float(hr)
            except (json.JSONDecodeError, AttributeError):
                invalid += 1

    return sorted(by_time.items()), invalid, duplicates


def summarize(values):
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "mean": mean(values),
        "median": median(values),
        "p90": percentile(values, 0.90),
        "min": min(values),
        "max": max(values),
    }


def score(actual, predicted):
    if not actual:
        return {"count": 0}
    errors = [p - a for a, p in zip(actual, predicted)]
    abs_errors = [abs(e) for e in errors]
    relative = [
        abs(p - a) / abs(a) * 100
        for a, p in zip(actual, predicted)
        if a != 0
    ]
    return {
        "count": len(actual),
        "mae_ghs": mean(abs_errors),
        "rmse_ghs": math.sqrt(mean(e * e for e in errors)),
        "mean_absolute_relative_error_pct": (
            mean(relative) if relative else None
        ),
        "median_absolute_error_ghs": median(abs_errors),
        "p90_absolute_error_ghs": percentile(abs_errors, 0.90),
    }


def main():
    if not SOURCE.exists():
        raise SystemExit(f"No existe el archivo: {SOURCE}")

    rows, invalid, duplicates = load_data()
    if len(rows) < WINDOW + 20:
        raise SystemExit("No hay suficientes muestras válidas.")

    times = [r[0] for r in rows]
    rates = [r[1] for r in rows]
    intervals = [
        (times[i] - times[i - 1]).total_seconds()
        for i in range(1, len(times))
    ]
    changes = [
        abs(rates[i] - rates[i - 1])
        for i in range(1, len(rates))
    ]

    split = int(len(rows) * TRAIN_FRACTION)
    if split <= WINDOW or split >= len(rows):
        raise SystemExit("No se pudo separar el tramo de prueba.")

    # Umbral de cambios bruscos calculado únicamente con el tramo histórico.
    train_changes = [
        abs(rates[i] - rates[i - 1])
        for i in range(1, split)
    ]
    abrupt_threshold = percentile(train_changes, 0.90)

    actual, predicted, previous_values = [], [], []
    test_times, test_changes = [], []

    for i in range(split, len(rows)):
        previous = rates[i - WINDOW:i]
        prediction = mean(previous)
        actual.append(rates[i])
        predicted.append(prediction)
        previous_values.append(previous[-1])
        test_times.append(times[i].isoformat())
        test_changes.append(abs(rates[i] - rates[i - 1]))

    errors = [p - a for a, p in zip(actual, predicted)]
    abs_errors = [abs(e) for e in errors]
    error_median = median(abs_errors)
    mad = median(abs(e - error_median) for e in abs_errors)
    outlier_cutoff = error_median + 3 * 1.4826 * mad

    outliers = []
    for i, error in enumerate(abs_errors):
        if error > outlier_cutoff:
            outliers.append({
                "timestamp": test_times[i],
                "actual_ghs": actual[i],
                "predicted_ghs": predicted[i],
                "absolute_error_ghs": error,
                "change_from_previous_ghs": test_changes[i],
            })

    stable_idx = [
        i for i, change in enumerate(test_changes)
        if change <= abrupt_threshold
    ]
    abrupt_idx = [
        i for i, change in enumerate(test_changes)
        if change > abrupt_threshold
    ]

    def subset(indices):
        return score(
            [actual[i] for i in indices],
            [predicted[i] for i in indices],
        )

    report = {
        "title": "TEOS NEURONA — Auditoría de calidad de hashrate",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(SOURCE.relative_to(ROOT)),
        "read_only_source": True,
        "data_quality": {
            "valid_unique_samples": len(rows),
            "invalid_lines": invalid,
            "duplicate_timestamps": duplicates,
            "first_timestamp": times[0].isoformat(),
            "last_timestamp": times[-1].isoformat(),
            "sampling_interval_seconds": summarize(intervals),
        },
        "split": {
            "historical_samples": split,
            "test_samples": len(actual),
            "train_fraction": TRAIN_FRACTION,
            "baseline": "mean_of_previous_5",
            "abrupt_change_threshold_ghs": abrupt_threshold,
            "threshold_basis": "90th percentile of historical absolute changes",
        },
        "test_metrics": score(actual, predicted),
        "test_segments": {
            "stable": subset(stable_idx),
            "abrupt_change": subset(abrupt_idx),
        },
        "absolute_error_outliers": {
            "method": "median absolute error + 3 * 1.4826 * MAD",
            "cutoff_ghs": outlier_cutoff,
            "count": len(outliers),
            "examples": outliers[:20],
        },
        "limitations": [
            "No se entrena una red neuronal.",
            "Los grupos estable y cambio brusco se clasifican retrospectivamente.",
            "El error relativo excluye valores reales iguales a cero.",
            "La auditoría no demuestra capacidad para predecir bloques Bitcoin.",
        ],
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("TEOS NEURONA — AUDITORÍA DE CALIDAD")
    print("Datos originales: solo lectura")
    print(f"Muestras válidas únicas: {len(rows)}")
    print(f"Líneas inválidas: {invalid}")
    print(f"Marcas temporales duplicadas: {duplicates}")
    print(f"Intervalo entre muestras (mediana): "
          f"{median(intervals):.2f} s")
    print(f"Intervalo entre muestras (P90): "
          f"{percentile(intervals, 0.90):.2f} s")
    print(f"Tramo de prueba: {len(actual)} muestras")
    print(f"Umbral de cambio brusco: {abrupt_threshold:.4f} GH/s")

    print("\n--- Prueba completa: media de cinco ---")
    result = score(actual, predicted)
    print(f"MAE: {result['mae_ghs']:.4f} GH/s")
    print(f"RMSE: {result['rmse_ghs']:.4f} GH/s")
    print(f"Error relativo absoluto medio: "
          f"{result['mean_absolute_relative_error_pct']:.4f}%")

    print("\n--- Por tipo de movimiento ---")
    for label, indices in (
        ("Estable", stable_idx),
        ("Cambio brusco", abrupt_idx),
    ):
        result = subset(indices)
        if result["count"]:
            print(f"{label}: n={result['count']}, "
                  f"MAE={result['mae_ghs']:.4f} GH/s, "
                  f"RMSE={result['rmse_ghs']:.4f} GH/s")
        else:
            print(f"{label}: sin muestras")

    print(f"\nErrores extremos detectados: {len(outliers)}")
    print(f"Informe guardado en: {REPORT.relative_to(ROOT)}")
    print("Sin entrenamiento ni cambios en el estado operativo.")


if __name__ == "__main__":
    main()
