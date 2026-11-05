#!/usr/bin/env python3
"""Memoria prospectiva TEOS: predicción, resultado y error medible."""

import json
import math
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/bitaxe_samples.jsonl"
OUT = ROOT / "data/processed"
PREDICTIONS = OUT / "learning_predictions.jsonl"
OUTCOMES = OUT / "learning_outcomes.jsonl"


def read_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except (json.JSONDecodeError, TypeError):
                continue
    return rows


def parse_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        # Normaliza fechas sin zona a UTC para poder compararlas.
        if dt.tzinfo is None:
            from datetime import timezone
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, OverflowError):
        return None


def number(row, *keys):
    for key in keys:
        value = row.get(key)
        try:
            value = float(value)
            if math.isfinite(value) and value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return None


def timestamp(row):
    for key in ("timestamp", "captured_at", "datetime", "time", "ts"):
        value = row.get(key)
        if parse_time(value) is not None:
            return str(value)
    return None


def append_once(path, row, id_key):
    existing = read_jsonl(path)
    identity = row.get(id_key)
    if any(item.get(id_key) == identity for item in existing):
        return False
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    return True


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    raw_rows = read_jsonl(RAW)

    # Una muestra válida por instante; nunca reescribe el archivo original.
    samples = {}
    for row in raw_rows:
        ts = timestamp(row)
        t = parse_time(ts)
        actual_rate = number(row, "hashRate", "hashrate", "hashrate_GHs")
        reference = number(row, "hashRate_1h", "hashrate_1h_GHs")
        if ts is not None and t is not None and actual_rate is not None:
            samples[ts] = {
                "timestamp": ts,
                "_time": t,
                "hashRate_GHs": actual_rate,
                "hashRate_1h_GHs": reference,
            }

    ordered = sorted(samples.values(), key=lambda x: x["_time"])
    if not ordered:
        raise SystemExit(
            f"No encontré muestras válidas de hashrate en {RAW}. "
            "No se modificó la memoria."
        )

    predictions = read_jsonl(PREDICTIONS)
    outcomes = read_jsonl(OUTCOMES)
    outcome_ids = {x.get("prediction_id") for x in outcomes}

    # Evalúa cada predicción pendiente contra la primera muestra posterior.
    new_outcomes = 0
    for pred in predictions:
        pid = pred.get("prediction_id")
        if not pid or pid in outcome_ids:
            continue
        pred_time = parse_time(pred.get("source_timestamp"))
        forecast = number(pred, "predicted_hashRate_GHs")
        if pred_time is None or forecast is None:
            continue

        future = next((s for s in ordered if s["_time"] > pred_time), None)
        if future is None:
            continue

        actual = future["hashRate_GHs"]
        error = actual - forecast
        outcome = {
            "prediction_id": pid,
            "source_timestamp": pred["source_timestamp"],
            "target_timestamp": future["timestamp"],
            "predicted_hashRate_GHs": round(forecast, 6),
            "actual_hashRate_GHs": round(actual, 6),
            "error_GHs": round(error, 6),
            "absolute_error_GHs": round(abs(error), 6),
            "squared_error_GH2": round(error * error, 6),
            "absolute_percentage_error": round(abs(error) / actual * 100, 6)
                if actual > 0 else None,
            "evaluation": "primera lectura válida posterior a la predicción",
        }
        if append_once(OUTCOMES, outcome, "prediction_id"):
            new_outcomes += 1
            outcome_ids.add(pid)

    # Una sola predicción nueva: siempre desde la última muestra disponible.
    latest = ordered[-1]
    existing_ids = {x.get("prediction_id") for x in predictions}
    new_prediction = False

    if latest["timestamp"] not in existing_ids:
        reference = latest["hashRate_1h_GHs"]
        if reference is not None:
            pred = {
                "prediction_id": latest["timestamp"],
                "created_at": datetime.now().astimezone().isoformat(),
                "source_timestamp": latest["timestamp"],
                "source_hashRate_GHs": round(latest["hashRate_GHs"], 6),
                "predicted_hashRate_GHs": round(reference, 6),
                "method": "baseline_hashRate_1h",
                "target": "siguiente hashRate válido",
                "uses_future_data": False,
                "note": "Referencia de comparación; no garantiza el hashrate futuro.",
            }
            new_prediction = append_once(PREDICTIONS, pred, "prediction_id")

    all_outcomes = read_jsonl(OUTCOMES)
    errors = []
    for item in all_outcomes:
        try:
            e = float(item["error_GHs"])
            if math.isfinite(e):
                errors.append(e)
        except (KeyError, TypeError, ValueError):
            pass

    print("=== TEOS NEURONA | MEMORIA Y APRENDIZAJE ===")
    print(f"Muestras válidas: {len(ordered)}")
    print(f"Última muestra: {latest['timestamp']}")
    print(f"Hashrate actual: {latest['hashRate_GHs']:.3f} GH/s")
    print(f"Predicciones nuevas: {int(new_prediction)}")
    print(f"Resultados nuevos: {new_outcomes}")
    print(f"Predicciones registradas: {len(read_jsonl(PREDICTIONS))}")
    print(f"Resultados evaluados: {len(all_outcomes)}")

    if errors:
        mae = sum(abs(e) for e in errors) / len(errors)
        rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
        print(f"MAE histórico: {mae:.3f} GH/s")
        print(f"RMSE histórico: {rmse:.3f} GH/s")
    else:
        print("MAE/RMSE: aún no disponibles; falta una predicción evaluada.")

    print(f"Memoria de predicciones: {PREDICTIONS.relative_to(ROOT)}")
    print(f"Memoria de resultados:   {OUTCOMES.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
