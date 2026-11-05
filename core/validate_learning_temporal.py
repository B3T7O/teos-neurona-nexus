#!/usr/bin/env python3
"""Validación cronológica de métodos de hashrate fuera de muestra."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/bitaxe_samples.jsonl"
REPORT = ROOT / "data/processed/learning_temporal_validation.json"


def read_jsonl(path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
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


def positive(row, *keys):
    for key in keys:
        try:
            value = float(row.get(key))
            if math.isfinite(value) and value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return None


def metrics(records):
    errors = [r["actual"] - r["predicted"] for r in records]
    if not errors:
        return {"n": 0, "MAE_GHs": None, "RMSE_GHs": None}
    return {
        "n": len(errors),
        "MAE_GHs": round(sum(abs(e) for e in errors) / len(errors), 6),
        "RMSE_GHs": round(math.sqrt(sum(e * e for e in errors) / len(errors)), 6),
    }


def main():
    if not RAW.exists():
        raise SystemExit(f"No existe el archivo: {RAW}")

    # Una muestra por instante, ordenadas cronológicamente.
    by_time = {}
    for row in read_jsonl(RAW):
        ts = next(
            (row.get(k) for k in
             ("timestamp", "captured_at", "datetime", "time", "ts")
             if parse_time(row.get(k)) is not None),
            None,
        )
        t = parse_time(ts)
        actual = positive(row, "hashRate", "hashrate", "hashrate_GHs")
        if t is None or actual is None:
            continue
        by_time[t] = {
            "timestamp": ts,
            "time": t,
            "actual": actual,
            "10m": positive(row, "hashRate_10m", "hashrate_10m_GHs"),
            "1h": positive(row, "hashRate_1h", "hashrate_1h_GHs"),
        }

    samples = [by_time[t] for t in sorted(by_time)]
    if len(samples) < 20:
        raise SystemExit("Se necesitan al menos 20 muestras válidas.")

    methods = (
        "referencia_1h",
        "referencia_10m",
        "media_ultimas_5",
        "ultimo_hashrate",
    )
    pairs = []

    # La predicción usa exclusivamente la lectura actual y su pasado.
    # El objetivo es siempre la siguiente lectura válida.
    for i in range(4, len(samples) - 1):
        current = samples[i]
        target = samples[i + 1]
        if current["1h"] is None or current["10m"] is None:
            continue

        predictions = {
            "referencia_1h": current["1h"],
            "referencia_10m": current["10m"],
            "media_ultimas_5": sum(
                s["actual"] for s in samples[i - 4:i + 1]
            ) / 5,
            "ultimo_hashrate": current["actual"],
        }
        pairs.append({
            "origin_timestamp": current["timestamp"],
            "target_timestamp": target["timestamp"],
            "actual": target["actual"],
            "predictions": predictions,
        })

    if len(pairs) < 20:
        raise SystemExit(
            "No hay suficientes pares comparables con referencias de 10m y 1h."
        )

    # Corte cronológico estricto: no barajar los datos.
    cut = int(len(pairs) * 0.70)
    train = pairs[:cut]
    test = pairs[cut:]

    train_metrics = {}
    test_metrics = {}
    for method in methods:
        train_metrics[method] = metrics([
            {
                "predicted": p["predictions"][method],
                "actual": p["actual"],
            }
            for p in train
        ])
        test_metrics[method] = metrics([
            {
                "predicted": p["predictions"][method],
                "actual": p["actual"],
            }
            for p in test
        ])

    # El método se elige exclusivamente con el tramo inicial.
    winner = min(
        methods,
        key=lambda m: train_metrics[m]["MAE_GHs"]
    )
    test_ranking = sorted(
        methods,
        key=lambda m: test_metrics[m]["MAE_GHs"]
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "data/raw/bitaxe_samples.jsonl",
        "target": "siguiente muestra válida",
        "split": "cronológico 70/30, sin barajar",
        "uses_future_data_for_prediction": False,
        "selection_rule": "menor MAE solo en entrenamiento",
        "selected_method": winner,
        "train": {
            "from": train[0]["origin_timestamp"],
            "to": train[-1]["origin_timestamp"],
            "metrics": train_metrics,
        },
        "test": {
            "from": test[0]["origin_timestamp"],
            "to": test[-1]["origin_timestamp"],
            "metrics": test_metrics,
            "ranking_by_MAE": test_ranking,
        },
        "warning": (
            "Una validación temporal; no garantiza resultados futuros. "
            "Las muestras consecutivas pueden estar correlacionadas y "
            "el intervalo entre lecturas puede variar."
        ),
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("=== TEOS NEURONA | VALIDACIÓN TEMPORAL ===")
    print(f"Muestras válidas: {len(samples)}")
    print(f"Pares comparables: {len(pairs)}")
    print(f"Entrenamiento: {len(train)} pares (70 % inicial)")
    print(f"Prueba:        {len(test)} pares (30 % final)")
    print()
    print(f"{'Método':<22} {'MAE train':>12} {'MAE test':>12} {'RMSE test':>12}")
    print("-" * 62)
    for method in sorted(methods, key=lambda m: train_metrics[m]["MAE_GHs"]):
        print(
            f"{method:<22} "
            f"{train_metrics[method]['MAE_GHs']:>12.3f} "
            f"{test_metrics[method]['MAE_GHs']:>12.3f} "
            f"{test_metrics[method]['RMSE_GHs']:>12.3f}"
        )

    print()
    print(f"Método seleccionado con entrenamiento: {winner}")
    print(f"Posición de ese método en prueba: {test_ranking.index(winner) + 1} de {len(methods)}")
    print(f"Informe: {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
