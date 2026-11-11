#!/usr/bin/env python3
"""NEURONA: prueba contextual cronológica, aislada de producción."""
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/bitaxe_samples.marked.jsonl"
OUT = ROOT / "data/processed/learning_outcomes_v2.jsonl"
REPORT = ROOT / "data/processed/contextual_adaptation_report.json"

METHODS = (
    "ultimo_hashrate",
    "referencia_10m",
    "referencia_1h",
    "media_ultimas_5",
)
BASELINE = "referencia_1h"
HISTORY_WINDOW = 100
NEIGHBORS = 30
MIN_NEIGHBORS = 20

FEATURES = ("temp", "frequency", "power", "errorPercentage")
SCALES = {"temp": 5.0, "frequency": 25.0,
          "power": 5.0, "errorPercentage": 0.1}


def parse_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def read_jsonl(path):
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def main():
    captures = {}
    for row in read_jsonl(RAW):
        ts = row.get("timestamp")
        if ts and all(row.get(k) is not None for k in FEATURES):
            captures[ts] = row

    # Un único resultado por método e instante de origen.
    outcomes = {}
    for row in read_jsonl(OUT):
        ts = row.get("source_timestamp")
        target = parse_time(row.get("target_timestamp"))
        method = row.get("method")
        try:
            error = abs(float(row["error_GHs"]))
        except (KeyError, TypeError, ValueError):
            continue
        source_dt = parse_time(ts)
        if (not ts or source_dt is None or target is None
                or method not in METHODS or not math.isfinite(error)):
            continue
        if ts not in captures:
            continue
        outcomes.setdefault(ts, {})[method] = {
            "target_dt": target, "error": error
        }

    events = []
    for ts, methods in outcomes.items():
        if set(methods) != set(METHODS):
            continue
        source_dt = parse_time(ts)
        cap = captures[ts]
        events.append({
            "timestamp": ts,
            "dt": source_dt,
            "features": {k: float(cap[k]) for k in FEATURES},
            "outcomes": methods,
        })
    events.sort(key=lambda e: e["dt"])

    decisions = []
    skipped = 0

    for current in events:
        # Solo resultados cuyo objetivo ya había ocurrido al decidir.
        past = [
            e for e in events
            if e["dt"] < current["dt"]
            and all(e["outcomes"][m]["target_dt"] < current["dt"]
                    for m in METHODS)
        ][-HISTORY_WINDOW:]

        if len(past) < MIN_NEIGHBORS:
            skipped += 1
            continue

        def distance(event):
            return math.sqrt(sum(
                ((event["features"][k] - current["features"][k])
                 / SCALES[k]) ** 2
                for k in FEATURES
            ))

        neighbors = sorted(past, key=distance)[:NEIGHBORS]
        if len(neighbors) < MIN_NEIGHBORS:
            skipped += 1
            continue

        historical_mae = {
            method: mean(e["outcomes"][method]["error"]
                         for e in neighbors)
            for method in METHODS
        }
        selected = min(METHODS, key=lambda m: (historical_mae[m], m))
        chosen_error = current["outcomes"][selected]["error"]
        baseline_error = current["outcomes"][BASELINE]["error"]

        decisions.append({
            "source_timestamp": current["timestamp"],
            "neighbors_used": len(neighbors),
            "selected_method": selected,
            "historical_mae_GHs": {
                m: round(v, 6) for m, v in historical_mae.items()
            },
            "adaptive_error_GHs": chosen_error,
            "baseline_error_GHs": baseline_error,
            "improvement_GHs": baseline_error - chosen_error,
        })

    if not decisions:
        raise SystemExit(
            "No hay suficientes instantes con historial completado. "
            "No se generó informe."
        )

    adaptive = [d["adaptive_error_GHs"] for d in decisions]
    baseline = [d["baseline_error_GHs"] for d in decisions]
    improvements = [d["improvement_GHs"] for d in decisions]

    def rmse(values):
        return math.sqrt(mean(x * x for x in values))

    counts = {m: sum(d["selected_method"] == m for d in decisions)
              for m in METHODS}

    adaptive_mae = mean(adaptive)
    baseline_mae = mean(baseline)

    report = {
        "module": "NEURONA CONTEXTUAL ADAPTATION V1",
        "generated_at": datetime.now().astimezone().isoformat(),
        "mode": "offline_chronological_experiment",
        "policy": {
            "baseline": BASELINE,
            "historical_window": HISTORY_WINDOW,
            "nearest_contexts": NEIGHBORS,
            "minimum_contexts": MIN_NEIGHBORS,
            "features": list(FEATURES),
            "scales": SCALES,
            "only_completed_past_outcomes_used": True,
            "production_modified": False,
            "original_records_modified": False,
            "warning": "Resultado retrospectivo; no garantiza mejora futura."
        },
        "counts": {
            "complete_events": len(events),
            "evaluated_decisions": len(decisions),
            "skipped_insufficient_history": skipped,
        },
        "results": {
            "adaptive_mae_GHs": round(adaptive_mae, 6),
            "baseline_mae_GHs": round(baseline_mae, 6),
            "adaptive_rmse_GHs": round(rmse(adaptive), 6),
            "baseline_rmse_GHs": round(rmse(baseline), 6),
            "mae_improvement_GHs": round(baseline_mae - adaptive_mae, 6),
            "mae_improvement_percent": round(
                (baseline_mae - adaptive_mae) / baseline_mae * 100, 4
            ) if baseline_mae else None,
            "wins": sum(x > 0 for x in improvements),
            "ties": sum(x == 0 for x in improvements),
            "losses": sum(x < 0 for x in improvements),
            "selected_method_counts": counts,
        },
        "decisions": decisions,
    }

    temp = REPORT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    temp.replace(REPORT)

    print("=== NEURONA CONTEXTUAL ADAPTATION V1 ===")
    print("Eventos completos:", len(events))
    print("Decisiones evaluadas:", len(decisions))
    print("Saltados por historial insuficiente:", skipped)
    print(f"MAE contextual: {adaptive_mae:.3f} GH/s")
    print(f"MAE referencia 1h: {baseline_mae:.3f} GH/s")
    print(f"Mejora MAE: {baseline_mae - adaptive_mae:+.3f} GH/s")
    if baseline_mae:
        print(f"Mejora porcentual: "
              f"{(baseline_mae - adaptive_mae) / baseline_mae * 100:+.2f}%")
    print(f"Victorias / empates / derrotas: "
          f"{report['results']['wins']} / "
          f"{report['results']['ties']} / "
          f"{report['results']['losses']}")
    print("Métodos seleccionados:", counts)
    print("Informe:", REPORT.relative_to(ROOT))
    print("Producción y datos originales: sin cambios.")


if __name__ == "__main__":
    main()
