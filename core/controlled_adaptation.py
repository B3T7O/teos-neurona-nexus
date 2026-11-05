#!/usr/bin/env python3
"""Prueba cronológica de aprendizaje controlado. No modifica V2."""
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "data/processed/learning_outcomes_v2.jsonl"
REPORT = ROOT / "data/processed/controlled_adaptation_report.json"

METHODS = {
    "ultimo_hashrate",
    "referencia_10m",
    "referencia_1h",
    "media_ultimas_5",
}
BASELINE = "referencia_1h"
WINDOW = 50
MIN_HISTORY = 30


def parse_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def load_rows():
    rows = []
    with INPUT.open(encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            source = parse_time(row.get("source_timestamp"))
            target = parse_time(row.get("target_timestamp"))
            try:
                error = abs(float(row["error_GHs"]))
            except (TypeError, ValueError, KeyError):
                continue

            if source is None or target is None or not math.isfinite(error):
                continue
            if row.get("method") not in METHODS:
                continue

            rows.append({
                "source_timestamp": str(row["source_timestamp"]),
                "source_dt": source,
                "target_dt": target,
                "method": row["method"],
                "absolute_error_GHs": error,
            })
    return rows


def main():
    if not INPUT.is_file():
        raise SystemExit(f"No existe el archivo: {INPUT}")

    rows = load_rows()
    by_source = defaultdict(dict)

    for row in rows:
        by_source[row["source_timestamp"]][row["method"]] = row

    timeline = sorted(
        by_source,
        key=lambda ts: min(r["source_dt"] for r in by_source[ts].values())
    )

    complete = [
        ts for ts in timeline
        if set(by_source[ts]) == METHODS
    ]

    decisions = []
    skipped = 0

    for ts in complete:
        current = by_source[ts]
        current_dt = current[BASELINE]["source_dt"]

        # Solo resultados que ya habrían estado disponibles al decidir.
        past = [
            r for r in rows
            if r["source_dt"] < current_dt
            and r["target_dt"] < current_dt
        ]

        past_sources = sorted({
            r["source_timestamp"] for r in past
        }, key=lambda s: min(
            r["source_dt"] for r in past
            if r["source_timestamp"] == s
        ))

        allowed_sources = set(past_sources[-WINDOW:])
        history = [
            r for r in past
            if r["source_timestamp"] in allowed_sources
        ]

        history_by_method = defaultdict(list)
        for row in history:
            history_by_method[row["method"]].append(
                row["absolute_error_GHs"]
            )

        # No elegir método hasta que todos tengan suficiente historial.
        if any(
            len(history_by_method[m]) < MIN_HISTORY
            for m in METHODS
        ):
            skipped += 1
            continue

        historical_mae = {
            m: mean(history_by_method[m]) for m in METHODS
        }
        selected = min(
            METHODS,
            key=lambda m: (historical_mae[m], m)
        )

        selected_error = current[selected]["absolute_error_GHs"]
        baseline_error = current[BASELINE]["absolute_error_GHs"]

        decisions.append({
            "source_timestamp": ts,
            "history_instants": len(allowed_sources),
            "historical_mae_GHs": {
                m: round(v, 6) for m, v in historical_mae.items()
            },
            "selected_method": selected,
            "selected_error_GHs": selected_error,
            "baseline_method": BASELINE,
            "baseline_error_GHs": baseline_error,
            "improvement_GHs": baseline_error - selected_error,
        })

    if not decisions:
        raise SystemExit(
            "No hay suficientes resultados históricos para evaluar. "
            "No se generó un informe de evaluación."
        )

    selected_errors = [d["selected_error_GHs"] for d in decisions]
    baseline_errors = [d["baseline_error_GHs"] for d in decisions]
    improvements = [d["improvement_GHs"] for d in decisions]

    selected_mae = mean(selected_errors)
    baseline_mae = mean(baseline_errors)
    selected_rmse = math.sqrt(mean(x * x for x in selected_errors))
    baseline_rmse = math.sqrt(mean(x * x for x in baseline_errors))

    selected_counts = defaultdict(int)
    for d in decisions:
        selected_counts[d["selected_method"]] += 1

    report = {
        "module": "NEURONA CONTROLLED ADAPTATION V1",
        "generated_at": datetime.now().astimezone().isoformat(),
        "mode": "offline_chronological_test",
        "source_file": str(INPUT.relative_to(ROOT)),
        "policy": {
            "baseline": BASELINE,
            "history_window_instants": WINDOW,
            "minimum_history_per_method": MIN_HISTORY,
            "only_past_source_and_target_times_used": True,
            "production_predictor_modified": False,
            "original_records_modified": False,
            "warning": (
                "Evaluación retrospectiva cronológica; no garantiza "
                "mejora futura ni activa selección en producción."
            ),
        },
        "counts": {
            "outcome_rows_loaded": len(rows),
            "complete_instants": len(complete),
            "decisions_evaluated": len(decisions),
            "skipped_for_insufficient_history": skipped,
        },
        "results": {
            "adaptive_mae_GHs": round(selected_mae, 6),
            "baseline_mae_GHs": round(baseline_mae, 6),
            "adaptive_rmse_GHs": round(selected_rmse, 6),
            "baseline_rmse_GHs": round(baseline_rmse, 6),
            "mae_improvement_GHs": round(
                baseline_mae - selected_mae, 6
            ),
            "mae_improvement_percent": round(
                (baseline_mae - selected_mae) / baseline_mae * 100, 4
            ) if baseline_mae else None,
            "adaptive_wins": sum(x > 0 for x in improvements),
            "ties": sum(x == 0 for x in improvements),
            "adaptive_losses": sum(x < 0 for x in improvements),
            "selected_method_counts": dict(selected_counts),
        },
        "decisions": decisions,
    }

    temp = REPORT.with_suffix(".json.tmp")
    temp.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(REPORT)

    print("=== NEURONA CONTROLLED ADAPTATION V1 ===")
    print(f"Instantes completos: {len(complete)}")
    print(f"Decisiones evaluadas: {len(decisions)}")
    print(f"Saltados por historial insuficiente: {skipped}")
    print(f"Ventana histórica: {WINDOW} instantes")
    print(f"MAE adaptación: {selected_mae:.3f} GH/s")
    print(f"MAE referencia 1h: {baseline_mae:.3f} GH/s")
    print(f"Mejora MAE: {baseline_mae - selected_mae:+.3f} GH/s")
    if baseline_mae:
        print(
            "Mejora porcentual: "
            f"{(baseline_mae - selected_mae) / baseline_mae * 100:+.2f}%"
        )
    print(f"Victorias / empates / derrotas: "
          f"{report['results']['adaptive_wins']} / "
          f"{report['results']['ties']} / "
          f"{report['results']['adaptive_losses']}")
    print("Métodos seleccionados:", dict(selected_counts))
    print(f"Informe: {REPORT.relative_to(ROOT)}")
    print("Modo: experimental; predictor de producción sin cambios.")


if __name__ == "__main__":
    main()
