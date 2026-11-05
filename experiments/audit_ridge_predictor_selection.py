#!/usr/bin/env python3
"""Evalúa selección de predictor usando únicamente tendencia previa."""

import contextlib
import io
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import audit_ridge_residual_direction_extended as direction

audit = direction.audit
ev = audit.ev

OUTPUT = ROOT / "experiments/ridge_predictor_selection_report.json"
captured = {}
original_summarize = audit.summarize


def stop(message):
    raise SystemExit(f"AUDITORÍA DETENIDA: {message}")


def capture(records):
    for record in records:
        captured[record["timestamp"]] = dict(record)
    return original_summarize(records)


def score(records, policy):
    if not records:
        return {"n": 0}

    actual = np.array([r["actual"] for r in records])
    predictions = []

    for r in records:
        if policy == "ridge_reducido":
            pred = r["ridge_reducido"]
        elif policy == "referencia_1h":
            pred = r["baseline_1h"]
        elif policy == "seleccion_tendencia_previa":
            pred = (
                r["ridge_reducido"]
                if r["past_delta_hashRate"] > 1e-9
                else r["baseline_1h"]
            )
        else:
            stop(f"Política desconocida: {policy}")

        predictions.append(pred)

    predictions = np.asarray(predictions)
    residual = predictions - actual

    return {
        "n": len(records),
        "mae_ghs": float(np.mean(np.abs(residual))),
        "rmse_ghs": float(np.sqrt(np.mean(residual ** 2))),
        "sesgo_ghs": float(np.mean(residual)),
    }


def main():
    if OUTPUT.exists():
        stop(f"El informe ya existe: {OUTPUT.name}")

    audit.summarize = capture

    try:
        with tempfile.TemporaryDirectory(
            dir=ROOT / "experiments",
            prefix=".tmp_predictor_selection_",
        ) as temporary:
            previous_output = direction.OUTPUT
            direction.OUTPUT = Path(temporary) / "rebuild.json"

            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    direction.main()
            finally:
                direction.OUTPUT = previous_output
    finally:
        audit.summarize = original_summarize

    records = list(captured.values())

    if len(records) != audit.EXPECTED_PAIRS:
        stop(f"Se reconstruyeron {len(records)} predicciones, no 9922.")

    prospective = json.loads(
        audit.PROSPECTIVE.read_text(encoding="utf-8")
    )

    frozen, _ = ev.load_frozen()

    last_target = ev.parse_timestamp(
        prospective["evaluation_period_utc"]["last_target"]
    )

    prefix = audit.recover_original_prefix(
        prospective["integrity"]["raw_sha256"],
        last_target,
    )

    rows = audit.load_prefix_rows(prefix)
    cutoff = frozen[-1]["_dt"]
    historical = [r for r in rows if r["_dt"] <= cutoff]
    future = [r for r in rows if r["_dt"] > cutoff]

    ev.verify_context(frozen, historical)

    if len(future) != prospective["validation"]["future_raw_rows"]:
        stop("La secuencia RAW no coincide con la evaluación oficial.")

    timeline = [frozen[-2], frozen[-1]] + future
    index_by_timestamp = {
        row["_dt"].isoformat(): i
        for i, row in enumerate(timeline)
    }

    by_previous_trend = defaultdict(list)

    for record in records:
        index = index_by_timestamp.get(record["timestamp"])

        if index is None or index < 2:
            stop("No se pudo reconstruir el contexto anterior.")

        previous = timeline[index - 1]
        earlier = timeline[index - 2]

        past_delta = (
            float(previous["hashRate"])
            - float(earlier["hashRate"])
        )

        record["past_delta_hashRate"] = past_delta

        if past_delta > 1e-9:
            trend = "tendencia_previa_alcista"
        elif past_delta < -1e-9:
            trend = "tendencia_previa_bajista"
        else:
            trend = "tendencia_previa_neutra"

        record["previous_trend"] = trend
        by_previous_trend[trend].append(record)

    habitual = [
        r for r in records
        if r["operational_context"] == "funcionamiento_habitual"
    ]

    if len(habitual) != 9858:
        stop(f"Funcionamiento habitual inesperado: {len(habitual)}.")

    # Reproducir los modelos fijos y validar sus métricas oficiales.
    global_methods = ev.compare_methods(records)

    for method in audit.METHODS:
        audit.verify_metrics(
            global_methods[method],
            prospective["global"][method],
            method,
        )

    policies = (
        "ridge_reducido",
        "referencia_1h",
        "seleccion_tendencia_previa",
    )

    results = {
        "global_todas_las_muestras": {
            name: score(records, name) for name in policies
        },
        "funcionamiento_habitual": {
            name: score(habitual, name) for name in policies
        },
        "por_tendencia_previa": {
            trend: {
                name: score(group, name)
                for name in policies
            }
            for trend, group in sorted(by_previous_trend.items())
        },
    }

    report = {
        "title": "TEOS NEURONA - Selección por tendencia previa",
        "validation": {
            "prospective_predictions": len(records),
            "habitual_predictions": len(habitual),
            "official_metrics_reproduced": True,
            "fixed_predictors": True,
            "future_data_used_for_training": False,
            "selection_uses_only_previous_samples": True,
            "original_reports_modified": False,
            "raw_modified": False,
            "bitaxe_modified": False,
        },
        "selection_rule": {
            "past_variable": (
                "hashRate de la muestra anterior menos "
                "hashRate de dos muestras anteriores."
            ),
            "positive": "ridge_reducido",
            "negative_or_neutral": "referencia_1h",
            "trained_gate": False,
        },
        "results": results,
        "warning": (
            "La regla es exploratoria. La tendencia previa puede servir "
            "como señal de selección, pero su rendimiento debe confirmarse "
            "en una evaluación cronológica independiente antes de aprobarla."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA - SELECCIÓN DE PREDICTOR")
    print("Predicciones:", len(records))
    print("Funcionamiento habitual:", len(habitual))
    print("Regla entrenada: NO")
    print("Información futura para seleccionar: NO")

    for context, result in results.items():
        print(f"\n--- {context.upper()} ---")
        for policy, item in result.items():
            print(
                f"{policy}: n={item['n']} | "
                f"MAE={item['mae_ghs']:.4f} | "
                f"RMSE={item['rmse_ghs']:.4f} | "
                f"sesgo={item['sesgo_ghs']:+.4f} GH/s"
            )

    print("\n--- POR TENDENCIA PREVIA ---")

    for trend, group in results["por_tendencia_previa"].items():
        print(f"\n{trend}")
        for policy, item in group.items():
            print(
                f"{policy}: n={item['n']} | "
                f"MAE={item['mae_ghs']:.4f} GH/s"
            )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("Modelos, RAW y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
