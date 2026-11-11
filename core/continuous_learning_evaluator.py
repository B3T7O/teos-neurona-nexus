#!/usr/bin/env python3
"""Evaluación continua de referencias; no modifica datos ni memorias existentes."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/bitaxe_samples.marked.jsonl"
REPORT = ROOT / "data/processed/learning_continuous_report.json"
WINDOW = 100

METHODS = (
    "referencia_1h",
    "referencia_10m",
    "media_ultimas_5",
    "ultimo_hashrate",
)


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


def positive(row, *keys):
    for key in keys:
        try:
            value = float(row.get(key))
            if math.isfinite(value) and value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return None


def calculate_metrics(records):
    if not records:
        return {"n": 0, "MAE_GHs": None, "RMSE_GHs": None, "bias_GHs": None}

    errors = [r["actual"] - r["predicted"] for r in records]
    return {
        "n": len(errors),
        "MAE_GHs": round(sum(abs(e) for e in errors) / len(errors), 6),
        "RMSE_GHs": round(math.sqrt(sum(e * e for e in errors) / len(errors)), 6),
        "bias_GHs": round(sum(errors) / len(errors), 6),
    }


def read_quarantined_timestamps():
    ledger = ROOT / "data/processed/anomaly_events.jsonl"
    quarantined = set()
    if ledger.exists():
        for row in read_jsonl(ledger):
            ts = parse_time(row.get("timestamp"))
            if ts is not None:
                quarantined.add(ts)
    return quarantined


def main():
    if not RAW.exists():
        raise SystemExit(f"No existe el archivo de muestras: {RAW}")

    # Excluir objetivos registrados en cuarentena; preservar el archivo RAW.
    quarantined = read_quarantined_timestamps()

    # Deduplicación temporal en memoria; no se escribe sobre el archivo original.
    by_time = {}
    for row in read_jsonl(RAW):
        ts = next(
            (
                row.get(k)
                for k in ("timestamp", "captured_at", "datetime", "time", "ts")
                if parse_time(row.get(k)) is not None
            ),
            None,
        )
        t = parse_time(ts)
        actual = positive(row, "hashRate", "hashrate", "hashrate_GHs")
        if t is None or actual is None or t in quarantined:
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
        raise SystemExit("No hay suficientes muestras válidas para evaluar.")

    # Evaluación retrospectiva de un paso: la predicción solo usa el origen;
    # la lectura siguiente se utiliza exclusivamente como valor observado.
    pairs = []
    for i in range(4, len(samples) - 1):
        current = samples[i]
        target = samples[i + 1]

        if current["10m"] is None or current["1h"] is None:
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
        raise SystemExit("No hay suficientes pares comparables.")

    # Ventanas comunes: todos los métodos se miden con los mismos objetivos.
    previous = pairs[max(0, len(pairs) - 2 * WINDOW):len(pairs) - WINDOW]
    recent = pairs[max(0, len(pairs) - WINDOW):]
    all_metrics = {}
    previous_metrics = {}
    recent_metrics = {}
    degradation = {}

    for method in METHODS:
        def records(window):
            return [
                {
                    "predicted": pair["predictions"][method],
                    "actual": pair["actual"],
                }
                for pair in window
            ]

        all_metrics[method] = calculate_metrics(records(pairs))
        previous_metrics[method] = calculate_metrics(records(previous))
        recent_metrics[method] = calculate_metrics(records(recent))

        old_mae = previous_metrics[method]["MAE_GHs"]
        new_mae = recent_metrics[method]["MAE_GHs"]

        if old_mae is None or new_mae is None:
            status = "datos_insuficientes"
            change_pct = None
        elif old_mae == 0:
            change_pct = 0.0 if new_mae == 0 else None
            status = "estable" if new_mae == 0 else "referencia_previa_cero"
        else:
            change_pct = round((new_mae - old_mae) / old_mae * 100, 3)
            if change_pct >= 20:
                status = "posible_degradacion"
            elif change_pct <= -20:
                status = "mejora_observada"
            else:
                status = "sin_cambio_marcado"

        degradation[method] = {
            "previous_MAE_GHs": old_mae,
            "recent_MAE_GHs": new_mae,
            "change_pct": change_pct,
            "status": status,
        }

    ranked = sorted(
        METHODS,
        key=lambda m: all_metrics[m]["MAE_GHs"]
        if all_metrics[m]["MAE_GHs"] is not None else float("inf"),
    )
    recent_ranked = sorted(
        METHODS,
        key=lambda m: recent_metrics[m]["MAE_GHs"]
        if recent_metrics[m]["MAE_GHs"] is not None else float("inf"),
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "data/raw/bitaxe_samples.marked.jsonl",
        "mode": "evaluación retrospectiva de un paso",
        "target": "siguiente muestra válida",
        "uses_future_data_for_prediction": False,
        "window_size": WINDOW,
        "sample_count": len(samples),
        "comparable_pairs": len(pairs),
        "overall": all_metrics,
        "previous_window": {
            "from": previous[0]["origin_timestamp"] if previous else None,
            "to": previous[-1]["origin_timestamp"] if previous else None,
            "metrics": previous_metrics,
        },
        "recent_window": {
            "from": recent[0]["origin_timestamp"],
            "to": recent[-1]["origin_timestamp"],
            "metrics": recent_metrics,
        },
        "degradation_monitor": degradation,
        "ranking_overall_by_MAE": ranked,
        "ranking_recent_by_MAE": recent_ranked,
        "warning": (
            "El informe recalcula el historial disponible; no sustituye una "
            "evaluación prospectiva. Las ventanas consecutivas pueden "
            "correlacionarse y los intervalos entre lecturas pueden variar. "
            "Una alerta es una señal de revisión, no una conclusión estadística."
        ),
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("=== TEOS NEURONA | EVALUADOR CONTINUO ===")
    print(f"Muestras válidas: {len(samples)}")
    print(f"Pares comparables: {len(pairs)}")
    print(f"Ventana anterior: {len(previous)} pares")
    print(f"Ventana reciente: {len(recent)} pares")
    print()
    print(f"{'Método':<22} {'MAE total':>11} {'MAE reciente':>14} {'Cambio %':>11}")
    print("-" * 62)

    for method in ranked:
        total = all_metrics[method]["MAE_GHs"]
        recent_mae = recent_metrics[method]["MAE_GHs"]
        change = degradation[method]["change_pct"]
        change_text = "N/D" if change is None else f"{change:+.1f}%"
        print(
            f"{method:<22} {total:>11.3f} {recent_mae:>14.3f} "
            f"{change_text:>11}"
        )

    print()
    print("Ranking histórico:", " > ".join(ranked))
    print("Ranking reciente:", " > ".join(recent_ranked))
    alerts = [
        m for m, d in degradation.items()
        if d["status"] == "posible_degradacion"
    ]
    print(
        "Posibles degradaciones:",
        ", ".join(alerts) if alerts else "ninguna detectada por el umbral",
    )
    print(f"Informe guardado: {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
