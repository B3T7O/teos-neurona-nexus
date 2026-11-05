#!/usr/bin/env python3
"""Compara referencias de hashrate sobre los mismos pares pasado-futuro."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/bitaxe_samples.jsonl"
OUTPUT = ROOT / "data/processed/learning_method_comparison.json"


def read_jsonl(path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except json.JSONDecodeError:
                continue
    return rows


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


def positive_number(row, *keys):
    for key in keys:
        try:
            value = float(row.get(key))
            if math.isfinite(value) and value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return None


def main():
    if not RAW.exists():
        raise SystemExit(f"No existe el archivo de muestras: {RAW}")

    # Ordena las lecturas por tiempo y elimina duplicados temporales.
    by_time = {}
    for row in read_jsonl(RAW):
        ts = next(
            (row.get(k) for k in
             ("timestamp", "captured_at", "datetime", "time", "ts")
             if parse_time(row.get(k)) is not None),
            None,
        )
        t = parse_time(ts)
        actual = positive_number(row, "hashRate", "hashrate", "hashrate_GHs")
        if t is None or actual is None:
            continue

        by_time[t] = {
            "timestamp": ts,
            "time": t,
            "actual": actual,
            "rate_10m": positive_number(
                row, "hashRate_10m", "hashrate_10m_GHs"
            ),
            "rate_1h": positive_number(
                row, "hashRate_1h", "hashrate_1h_GHs"
            ),
        }

    samples = [by_time[t] for t in sorted(by_time)]
    if len(samples) < 6:
        raise SystemExit("Se necesitan al menos seis muestras válidas.")

    # Para que la comparación sea justa, todos los métodos se evalúan
    # en los mismos instantes de origen y contra el mismo siguiente dato.
    methods = {
        "ultimo_hashrate": [],
        "referencia_10m": [],
        "referencia_1h": [],
        "media_ultimas_5": [],
    }

    for i in range(4, len(samples) - 1):
        current = samples[i]
        future = samples[i + 1]

        values = [
            current["actual"],
            current["rate_10m"],
            current["rate_1h"],
            sum(s["actual"] for s in samples[i - 4:i + 1]) / 5,
        ]

        if any(v is None or not math.isfinite(v) for v in values):
            continue

        predictions = dict(zip(methods.keys(), values))
        for name, prediction in predictions.items():
            methods[name].append({
                "origin_timestamp": current["timestamp"],
                "target_timestamp": future["timestamp"],
                "predicted": prediction,
                "actual": future["actual"],
                "error": future["actual"] - prediction,
            })

    # Conserva únicamente orígenes con todos los métodos disponibles.
    common_origins = set.intersection(
        *[
            {r["origin_timestamp"] for r in records}
            for records in methods.values()
        ]
    )
    if not common_origins:
        raise SystemExit("No hay orígenes comunes para comparar.")

    metrics = {}
    for name, records in methods.items():
        selected = [
            r for r in records if r["origin_timestamp"] in common_origins
        ]
        errors = [r["error"] for r in selected]
        metrics[name] = {
            "n": len(errors),
            "MAE_GHs": round(sum(abs(e) for e in errors) / len(errors), 6),
            "RMSE_GHs": round(
                math.sqrt(sum(e * e for e in errors) / len(errors)), 6
            ),
        }

    ranking = sorted(
        metrics.items(), key=lambda item: item[1]["MAE_GHs"]
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "data/raw/bitaxe_samples.jsonl",
        "target": "siguiente muestra válida",
        "comparison": "mismos orígenes y mismos valores reales",
        "uses_future_data_for_prediction": False,
        "warning": (
            "Backtest histórico de un paso; no garantiza rendimiento futuro. "
            "Las lecturas consecutivas pueden estar correlacionadas."
        ),
        "common_origins": len(common_origins),
        "metrics": metrics,
        "ranking_by_MAE": [name for name, _ in ranking],
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("=== TEOS NEURONA | COMPARACIÓN DE REFERENCIAS ===")
    print(f"Muestras válidas: {len(samples)}")
    print(f"Orígenes comparables: {len(common_origins)}")
    print("Objetivo: siguiente muestra válida")
    print()
    print(f"{'Método':<22} {'MAE GH/s':>12} {'RMSE GH/s':>12} {'N':>7}")
    print("-" * 56)
    for name, result in ranking:
        print(
            f"{name:<22} {result['MAE_GHs']:>12.3f} "
            f"{result['RMSE_GHs']:>12.3f} {result['n']:>7}"
        )

    print()
    print(f"Mejor referencia histórica por MAE: {ranking[0][0]}")
    print("Esto no demuestra que sea la mejor para muestras futuras.")
    print(f"Informe guardado: {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
