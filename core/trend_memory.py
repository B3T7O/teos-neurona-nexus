#!/usr/bin/env python3
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/bitaxe_samples.jsonl"
OUTCOMES = ROOT / "data/processed/learning_outcomes_v2.jsonl"
REPORT = ROOT / "data/processed/trend_memory_report.json"
MIN_GROUP = 10


def load_jsonl(path):
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
            except json.JSONDecodeError:
                continue
    return rows


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def parse_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def summarize(rows):
    errors = [number(r.get("absolute_error_GHs")) for r in rows]
    errors = [x for x in errors if x is not None]
    signed = [number(r.get("error_GHs")) for r in rows]
    signed = [x for x in signed if x is not None]
    actual = [number(r.get("actual_hashRate_GHs")) for r in rows]
    actual = [x for x in actual if x is not None]

    result = {"n": len(errors)}
    if errors:
        result["mae_GHs"] = round(mean(errors), 4)
        result["rmse_GHs"] = round(
            math.sqrt(mean(x * x for x in errors)), 4
        )
    if signed:
        result["mean_signed_error_GHs"] = round(mean(signed), 4)
    if actual:
        result["mean_actual_hashRate_GHs"] = round(mean(actual), 4)
    return result


def condition_bucket(field, value):
    x = number(value)
    if x is None:
        return "sin_dato"

    if field == "temp":
        return "<55" if x < 55 else "55-<60" if x < 60 else \
               "60-<65" if x < 65 else ">=65"
    if field == "frequency":
        return "<500" if x < 500 else "500-<525" if x < 525 else \
               "525-550" if x <= 550 else ">550"
    if field == "power":
        return "<=20" if x <= 20 else "20-<30" if x < 30 else \
               "30-<40" if x < 40 else ">=40"
    if field == "errorPercentage":
        return "0" if x == 0 else "0-<=0.1" if x <= 0.1 else ">0.1"
    return "sin_dato"


def main():
    for path in (RAW, OUTCOMES):
        if not path.is_file():
            raise SystemExit(f"Falta archivo necesario: {path}")

    samples = load_jsonl(RAW)
    outcomes = load_jsonl(OUTCOMES)

    # Indexar únicamente las capturas originales por su timestamp.
    sample_by_time = {}
    for sample in samples:
        timestamp = sample.get("timestamp")
        if timestamp:
            sample_by_time[str(timestamp)] = sample

    matched = []
    unmatched = 0
    invalid = 0

    for outcome in outcomes:
        source_time = str(outcome.get("source_timestamp") or "")
        sample = sample_by_time.get(source_time)
        if sample is None:
            unmatched += 1
            continue

        if number(outcome.get("absolute_error_GHs")) is None:
            invalid += 1
            continue

        row = dict(outcome)
        row["_sample"] = sample
        row["_time"] = parse_time(source_time)
        matched.append(row)

    dimensions = defaultdict(list)
    methods = defaultdict(list)

    for row in matched:
        method = str(row.get("method") or "desconocido")
        methods[method].append(row)
        dt = row["_time"]

        if dt:
            dimensions[("hora_utc", f"{dt.hour:02d}")].append(row)
            dimensions[("dia_semana_utc", dt.strftime("%A") )].append(row)

        sample = row["_sample"]
        for field in ("temp", "frequency", "power", "errorPercentage"):
            dimensions[(field, condition_bucket(field, sample.get(field)))].append(row)

    by_method = {
        method: summarize(rows)
        for method, rows in sorted(methods.items())
    }

    trends = {}
    for (dimension, bucket), rows in sorted(dimensions.items()):
        if len(rows) < MIN_GROUP:
            continue
        key = f"{dimension}={bucket}"
        trends[key] = {
            "total": len(rows),
            "metodos": {
                method: summarize([r for r in rows if r.get("method") == method])
                for method in sorted({
                    str(r.get("method") or "desconocido") for r in rows
                })
            },
        }

    ranked = []
    for method, metrics in by_method.items():
        if metrics.get("n", 0):
            ranked.append({
                "method": method,
                **metrics,
            })
    ranked.sort(key=lambda x: x.get("mae_GHs", float("inf")))

    report = {
        "module": "NEURONA TREND MEMORY V1",
        "generated_at_utc": datetime.now().astimezone().isoformat(),
        "read_only_sources": [
            str(RAW.relative_to(ROOT)),
            str(OUTCOMES.relative_to(ROOT)),
        ],
        "policy": {
            "source_conditions_only": True,
            "minimum_group_observations": MIN_GROUP,
            "trend_timezone": "UTC",
            "raw_and_v2_files_modified": False,
            "warning": "Los grupos describen el histórico; no prueban causalidad ni garantizan rendimiento futuro.",
        },
        "counts": {
            "raw_captures": len(samples),
            "outcomes": len(outcomes),
            "matched_to_source_capture": len(matched),
            "unmatched_source_timestamp": unmatched,
            "invalid_absolute_error": invalid,
        },
        "overall_by_method": by_method,
        "methods_ranked_by_historical_mae": ranked,
        "trends": trends,
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    temp_report = REPORT.with_suffix(".json.tmp")
    temp_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_report.replace(REPORT)

    print("=== NEURONA TREND MEMORY V1 ===")
    print(f"Capturas: {len(samples)}")
    print(f"Evaluaciones: {len(outcomes)}")
    print(f"Vinculadas a captura de origen: {len(matched)}")
    print(f"Sin captura exacta: {unmatched}")
    print(f"Grupos de tendencias útiles: {len(trends)}")
    print("\nMAE histórico por método (menor es mejor):")
    for item in ranked:
        print(
            f"  {item['method']}: MAE={item['mae_GHs']:.3f} GH/s"
            f" | RMSE={item['rmse_GHs']:.3f} GH/s"
            f" | n={item['n']}"
        )
    print(f"\nInforme guardado: {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
