#!/usr/bin/env python3
"""Evaluación cronológica de referencias de hashrate.
Solo lectura: no modifica los datos ni el estado de TEOS.
"""

import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/raw/bitaxe_samples.marked.jsonl"
TRAIN_FRACTION = 0.70
WINDOW = 5


def parse_time(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def load_samples():
    rows = []
    invalid = 0

    with SOURCE.open(encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                invalid += 1
                continue

            ts = parse_time(row.get("timestamp"))
            hr = row.get("hashRate")

            if (
                ts is None
                or isinstance(hr, bool)
                or not isinstance(hr, (int, float))
                or not math.isfinite(hr)
                or hr < 0
            ):
                invalid += 1
                continue

            rows.append((ts, float(hr)))

    rows.sort(key=lambda x: x[0])

    # Evita comparar dos registros con la misma marca temporal.
    unique = {}
    duplicates = 0
    for ts, hr in rows:
        if ts in unique:
            duplicates += 1
        unique[ts] = hr

    return sorted(unique.items()), invalid, duplicates


def metrics(actual, predicted):
    errors = [p - a for a, p in zip(actual, predicted)]
    return {
        "mae": mean(abs(e) for e in errors),
        "rmse": math.sqrt(mean(e * e for e in errors)),
    }


def main():
    if not SOURCE.exists():
        raise SystemExit(f"No existe el archivo: {SOURCE}")

    rows, invalid, duplicates = load_samples()

    print("TEOS NEURONA — PRUEBA BASE DE HASHRATE")
    print("Modo: lectura solamente")
    print(f"Muestras válidas únicas: {len(rows)}")
    print(f"Líneas inválidas: {invalid}")
    print(f"Marcas temporales duplicadas: {duplicates}")

    if len(rows) < WINDOW + 10:
        raise SystemExit("No hay suficientes muestras para la prueba.")

    split = int(len(rows) * TRAIN_FRACTION)
    if split <= WINDOW or split >= len(rows):
        raise SystemExit("No se pudo separar entrenamiento y prueba.")

    # Predicciones de la prueba: cada estimación usa solo datos anteriores.
    actual, persistence, rolling = [], [], []

    for i in range(max(WINDOW, split), len(rows)):
        previous = [rows[j][1] for j in range(i - WINDOW, i)]
        actual.append(rows[i][1])
        persistence.append(previous[-1])
        rolling.append(mean(previous))

    print(f"Entrenamiento histórico: {split} muestras")
    print(f"Prueba futura reservada: {len(actual)} muestras")
    print(f"Ventana de referencia: {WINDOW} muestras anteriores")

    results = {
        "Último valor observado": metrics(actual, persistence),
        "Media de las últimas cinco": metrics(actual, rolling),
    }

    print("\n--- Resultados fuera de muestra ---")
    for name, result in results.items():
        print(f"\n{name}")
        print(f"  MAE:  {result['mae']:.4f} GH/s")
        print(f"  RMSE: {result['rmse']:.4f} GH/s")

    best_baseline = min(r["mae"] for r in results.values())
    print("\nConclusión:")
    print(f"Mejor MAE de referencia: {best_baseline:.4f} GH/s")
    print("Esta prueba compara referencias; todavía no entrena una red neuronal.")
    print("No demuestra capacidad para predecir bloques Bitcoin.")


if __name__ == "__main__":
    main()
