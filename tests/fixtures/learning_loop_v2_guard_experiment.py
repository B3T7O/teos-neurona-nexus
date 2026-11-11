#!/usr/bin/env python3
"""TEOS NEURONA: comparación prospectiva de cuatro métodos."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
try:
    from core import online_error_learner
except ModuleNotFoundError:
    import online_error_learner

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/bitaxe_samples.marked.jsonl"
OUT = ROOT / "data/processed"
PREDICTIONS = OUT / "learning_predictions_v2.jsonl"
OUTCOMES = OUT / "learning_outcomes_v2.jsonl"

METHODS = (
    "ultimo_hashrate",
    "referencia_10m",
    "referencia_1h",
    "media_ultimas_5",
)


def read_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
            except (json.JSONDecodeError, TypeError):
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


def number(row, *keys):
    for key in keys:
        try:
            value = float(row.get(key))
            if math.isfinite(value) and value > 0:
                return value
        except (TypeError, ValueError):
            pass
    return None


def append_jsonl(path, row):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")



def choose_adaptive_method(outcomes, latest_timestamp):
    """Selecciona por MAE reciente sin consultar resultados futuros."""
    def epoch(value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            ).timestamp()
        except (ValueError, TypeError, OverflowError):
            return None

    cutoff = epoch(latest_timestamp)
    if cutoff is None:
        return "referencia_1h", 0, None

    candidates = []
    for method in METHODS:
        eligible = []
        for outcome in outcomes:
            if outcome.get("method") != method:
                continue
            target = epoch(outcome.get("target_timestamp"))
            error = outcome.get("absolute_error_GHs")
            if target is None or target > cutoff:
                continue
            if not isinstance(error, (int, float)) or not math.isfinite(error):
                continue
            eligible.append((target, float(error)))

        eligible.sort(key=lambda item: item[0])
        recent = eligible[-50:]
        if len(recent) >= 20:
            mae = sum(item[1] for item in recent) / len(recent)
            candidates.append((mae, method, len(recent)))

    if not candidates:
        return "referencia_1h", 0, None

    mae, method, count = min(candidates, key=lambda item: item[0])
    return method, count, mae


def estimate_bias_correction(
    outcomes, latest_timestamp, window=50, min_samples=10
):
    """Estima el sesgo usando solo resultados conocidos en el origen."""
    cutoff = parse_time(latest_timestamp)
    if cutoff is None:
        return 0.0, 0, False

    eligible = []
    for outcome in outcomes:
        if outcome.get("method") != "adaptativo_neurona":
            continue

        target = parse_time(outcome.get("target_timestamp"))
        error = outcome.get("error_GHs")

        if target is None or target > cutoff:
            continue
        if isinstance(error, bool) or not isinstance(error, (int, float)):
            continue
        if not math.isfinite(error):
            continue

        eligible.append((target, float(error)))

    eligible.sort(key=lambda item: item[0])
    recent = eligible[-window:]

    if len(recent) < min_samples:
        return 0.0, len(recent), False

    correction = sum(error for _, error in recent) / len(recent)
    return correction, len(recent), True


def filter_contextual_anomalies(samples, factor=3.0, window=10):
    """Filtra picos que contradicen la mediana previa y la referencia de 1h."""
    accepted = []
    rejected = []

    for sample in samples:
        history = [s["actual"] for s in accepted[-window:]]
        baseline = None

        if len(history) >= 5:
            ordered = sorted(history)
            n = len(ordered)
            mid = n // 2
            baseline = ordered[mid] if n % 2 else (
                ordered[mid - 1] + ordered[mid]
            ) / 2

        actual = sample.get("actual")
        rate_1h = sample.get("rate_1h")
        anomalous = (
            baseline is not None
            and isinstance(actual, (int, float))
            and isinstance(rate_1h, (int, float))
            and baseline > 0 and rate_1h > 0
            and actual > factor * baseline
            and actual > factor * rate_1h
        )

        if anomalous:
            rejected.append(sample)
        else:
            accepted.append(sample)

    for sample in rejected:
        print(
            "ANOMALIA CONTEXTUAL EXCLUIDA:",
            sample.get("timestamp"),
            "hashRate=", sample.get("actual"),
            "referencia_1h=", sample.get("rate_1h"),
        )

    if rejected:
        print("Muestras excluidas del cálculo:", len(rejected))
    return accepted


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # Leer el histórico sin modificar el archivo raw.
    by_timestamp = {}
    for row in read_jsonl(RAW):
        ts = row.get("timestamp") or row.get("captured_at") or row.get("datetime")
        t = parse_time(ts)
        actual = number(row, "hashRate", "hashrate", "hashrate_GHs")
        if t is None or actual is None:
            continue

        by_timestamp[str(ts)] = {
            "timestamp": str(ts),
            "_time": t,
            "actual": actual,
            "rate_10m": number(row, "hashRate_10m", "hashrate_10m_GHs"),
            "rate_1h": number(row, "hashRate_1h", "hashrate_1h_GHs"),
        }

    samples = sorted(by_timestamp.values(), key=lambda x: x["_time"])
    from core.anomaly_memory import record_contextual_anomalies
    record_contextual_anomalies(samples)
    samples = filter_contextual_anomalies(samples)
    if len(samples) < 5:
        raise SystemExit("Aún no hay cinco muestras válidas. No se crearon predicciones.")

    predictions = read_jsonl(PREDICTIONS)
    outcomes = read_jsonl(OUTCOMES)
    prediction_ids = {p.get("prediction_id") for p in predictions}
    outcome_ids = {o.get("prediction_id") for o in outcomes}

    # Resolver cada predicción pendiente contra la primera muestra posterior.
    new_outcomes = 0
    for pred in predictions:
        pid = pred.get("prediction_id")
        if not pid or pid in outcome_ids:
            continue

        source_time = parse_time(pred.get("source_timestamp"))
        forecast = number(pred, "predicted_hashRate_GHs")
        if source_time is None or forecast is None:
            continue

        future = next((s for s in samples if s["_time"] > source_time), None)
        if future is None:
            continue

        actual = future["actual"]
        error = actual - forecast
        append_jsonl(OUTCOMES, {
            "prediction_id": pid,
            "method": pred["method"],
            "source_timestamp": pred["source_timestamp"],
            "target_timestamp": future["timestamp"],
            "predicted_hashRate_GHs": round(forecast, 6),
            "actual_hashRate_GHs": round(actual, 6),
            "error_GHs": round(error, 6),
            "absolute_error_GHs": round(abs(error), 6),
            "squared_error_GH2": round(error * error, 6),
            "absolute_percentage_error": round(abs(error) / actual * 100, 6),
            "evaluation": "primera muestra válida posterior al origen",
        })
        outcome_ids.add(pid)
        new_outcomes += 1

    # APRENDIZAJE ONLINE TEOS: aprende de resultados ya observados.
    adaptive_history = [
        o for o in read_jsonl(OUTCOMES)
        if o.get("method") == "adaptativo_neurona"
    ]
    adaptive_history.sort(
        key=lambda o: str(o.get("target_timestamp") or "")
    )

    learned_now = 0
    for outcome in adaptive_history:
        pid = outcome.get("prediction_id")
        predicted = outcome.get("predicted_hashRate_GHs")
        actual = outcome.get("actual_hashRate_GHs")

        if not pid or predicted is None or actual is None:
            continue

        result = online_error_learner.learn(
            prediction_id=pid,
            predicted_GHs=predicted,
            actual_GHs=actual,
            target_timestamp=outcome.get("target_timestamp"),
        )
        if result.get("updated"):
            learned_now += 1

    print(
        f"Aprendiz online: {learned_now} nuevas actualizaciones; "
        f"{len(adaptive_history)} resultados adaptativos revisados."
    )

    # Predicciones de la muestra más reciente; no reconstruye el pasado.
    latest = samples[-1]
    previous = latest["_time"]
    source = latest["timestamp"]

    if latest["rate_10m"] is None or latest["rate_1h"] is None:
        print("Muestra más reciente sin referencias 10m/1h; se omite.")
    else:
        forecasts = {
            "ultimo_hashrate": latest["actual"],
            "referencia_10m": latest["rate_10m"],
            "referencia_1h": latest["rate_1h"],
            "media_ultimas_5": sum(s["actual"] for s in samples[-5:]) / 5,
        }

        known_outcomes = read_jsonl(OUTCOMES)
        selected_method, selection_n, selection_mae = choose_adaptive_method(
            known_outcomes, source
        )

        base_forecast = forecasts[selected_method]
        online = online_error_learner.predict(base_forecast)
        adaptive_forecast = online["prediction_GHs"]
        forecasts["adaptativo_neurona"] = adaptive_forecast

        print(
            f"Base adaptativa: {selected_method}; "
            f"resultados para selección: {selection_n}; "
            f"sesgo aprendido: {online['learned_bias_GHs']:+.3f} GH/s; "
            f"actualizaciones persistidas: {online['updates']}"
        )


        for method in list(METHODS) + ["adaptativo_neurona"]:
            pid = f"{source}|{method}"
            if pid in prediction_ids:
                continue

            forecast = forecasts[method]
            record = {
                "prediction_id": pid,
                "created_at": datetime.now().astimezone().isoformat(),
                "source_timestamp": source,
                "source_hashRate_GHs": round(latest["actual"], 6),
                "predicted_hashRate_GHs": round(forecast, 6),
                "method": method,
                "target": "siguiente muestra válida de hashRate",
                "uses_future_data": False,
            }

            if method == "adaptativo_neurona":
                record["selected_method"] = selected_method
                record["selection_history_n"] = selection_n
                record["selection_mae_GHs"] = (
                    round(selection_mae, 6)
                    if selection_mae is not None else None
                )
                record["adaptive_base_prediction_GHs"] = round(
                    base_forecast, 6
                )
                record["online_bias_GHs"] = round(
                    online["learned_bias_GHs"], 6
                )
                record["online_updates"] = online["updates"]
                record["online_learning_enabled"] = online["updates"] > 0

            append_jsonl(PREDICTIONS, record)
            prediction_ids.add(pid)

    # Métricas prospectivas separadas para cada método.
    all_outcomes = read_jsonl(OUTCOMES)
    print("=== TEOS NEURONA | COMPARADOR PROSPECTIVO V2 ===")
    print(f"Muestras válidas: {len(samples)}")
    print(f"Última muestra: {source}")
    print(f"Hashrate observado: {latest['actual']:.3f} GH/s")
    print(f"Resultados nuevos: {new_outcomes}")
    print(f"Predicciones v2: {len(read_jsonl(PREDICTIONS))}")
    print(f"Resultados v2: {len(all_outcomes)}")
    print("Los resultados pendientes esperan una muestra posterior.")

    print("\nMétodo                 N      MAE GH/s    RMSE GH/s")
    print("-" * 54)
    for method in list(METHODS) + ["adaptativo_neurona"]:
        errors = [
            float(o["error_GHs"])
            for o in all_outcomes
            if o.get("method") == method
            and isinstance(o.get("error_GHs"), (int, float))
            and math.isfinite(float(o["error_GHs"]))
        ]
        if errors:
            mae = sum(abs(e) for e in errors) / len(errors)
            rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
            print(f"{method:22} {len(errors):4d} {mae:12.3f} {rmse:12.3f}")
        else:
            print(f"{method:22} {0:4d} {'pendiente':>12} {'pendiente':>12}")

    print("\nPredicciones:", PREDICTIONS.relative_to(ROOT))
    print("Resultados:  ", OUTCOMES.relative_to(ROOT))


if __name__ == "__main__":
    main()
