#!/usr/bin/env python3
"""Frecuencia y concentración de errores de Ridge reducido."""

import json
import math
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import audit_ridge_residual_direction_extended as direction

audit = direction.audit
OUTPUT = ROOT / "experiments/ridge_residual_error_frequency_extended_report.json"
PRIOR = ROOT / "experiments/ridge_residual_direction_extended_report.json"

ERROR_EPSILON = 1e-9
METHODS = {
    "ridge_reducido": "ridge_reducido",
    "referencia_1h": "baseline_1h",
}
CLASSES = direction.CLASSES
DIRECTIONS = direction.DIRECTIONS


def stop(message):
    raise SystemExit(f"AUDITORÍA DETENIDA: {message}")


def side_metrics(errors, mask, total_abs):
    values = errors[mask]
    count = len(values)

    if count == 0:
        return {
            "n": 0,
            "porcentaje_predicciones": 0.0,
            "error_absoluto_medio_ghs": None,
            "error_absoluto_mediano_ghs": None,
            "error_absoluto_p90_ghs": None,
            "error_absoluto_maximo_ghs": None,
            "porcentaje_error_absoluto_total": 0.0,
            "concentracion_top_1pct_error_del_grupo_pct": None,
        }

    side_total = float(np.sum(values))
    top_count = max(1, math.ceil(count * 0.01))
    top_values = np.sort(values)[-top_count:]

    return {
        "n": int(count),
        "porcentaje_predicciones": float(count / len(errors) * 100),
        "error_absoluto_medio_ghs": float(np.mean(values)),
        "error_absoluto_mediano_ghs": float(np.median(values)),
        "error_absoluto_p90_ghs": float(np.percentile(values, 90)),
        "error_absoluto_maximo_ghs": float(np.max(values)),
        "porcentaje_error_absoluto_total": (
            float(side_total / total_abs * 100) if total_abs else 0.0
        ),
        "concentracion_top_1pct_error_del_grupo_pct": (
            float(np.sum(top_values) / side_total * 100)
            if side_total else 0.0
        ),
    }


def error_profile(records, prediction_field):
    if not records:
        return {"n": 0}

    actual = np.asarray([r["actual"] for r in records], dtype=float)
    predicted = np.asarray(
        [r[prediction_field] for r in records], dtype=float
    )
    residual = predicted - actual
    absolute = np.abs(residual)

    over = residual > ERROR_EPSILON
    under = residual < -ERROR_EPSILON
    ties = ~(over | under)

    total_abs = float(np.sum(absolute))
    top_count = max(1, math.ceil(len(absolute) * 0.01))
    top_all = np.sort(absolute)[-top_count:]

    return {
        "n": len(records),
        "sesgo_prediccion_menos_real_ghs": float(np.mean(residual)),
        "mae_ghs": float(np.mean(absolute)),
        "sobreestimaciones": side_metrics(absolute, over, total_abs),
        "subestimaciones": side_metrics(absolute, under, total_abs),
        "empates": {
            "n": int(np.sum(ties)),
            "porcentaje_predicciones": float(np.mean(ties) * 100),
        },
        "sobreestimacion_es_mayoria": bool(np.sum(over) > len(records) / 2),
        "sobreestimacion_es_mayoria_entre_no_empates": bool(
            np.sum(over) > (np.sum(over) + np.sum(under)) / 2
        ),
        "concentracion_top_1pct_de_todos_los_errores_pct": (
            float(np.sum(top_all) / total_abs * 100)
            if total_abs else 0.0
        ),
    }


def summarize(records):
    return {
        method: error_profile(records, field)
        for method, field in METHODS.items()
    }


def nested_summary(records, key_function, keys):
    groups = defaultdict(list)

    for record in records:
        groups[key_function(record)].append(record)

    return {
        key: summarize(groups.get(key, []))
        for key in keys
    }


def main():
    if OUTPUT.exists():
        stop(f"El informe ya existe; no se sobrescribió: {OUTPUT.name}")

    if not PRIOR.is_file():
        stop("Falta el informe direccional anterior.")

    prior = json.loads(PRIOR.read_text(encoding="utf-8"))

    if prior.get("validation", {}).get(
        "official_prospective_metrics_reproduced"
    ) is not True:
        stop("El informe direccional previo no está validado.")

    # Capturar las mismas predicciones reconstruidas por el auditor anterior.
    # Se interceptan sus agrupaciones sin modificar su lógica ni sus datos.
    captured = {}
    original_summarize = audit.summarize

    def capture(records):
        for record in records:
            captured[id(record)] = dict(record)
        return original_summarize(records)

    audit.summarize = capture

    try:
        with tempfile.TemporaryDirectory(
            dir=ROOT / "experiments",
            prefix=".tmp_direction_rebuild_",
        ) as temporary:
            previous_output = direction.OUTPUT
            direction.OUTPUT = Path(temporary) / "rebuild.json"

            try:
                direction.main()
            finally:
                direction.OUTPUT = previous_output
    finally:
        audit.summarize = original_summarize

    records = list(captured.values())

    if len(records) != audit.EXPECTED_PAIRS:
        stop(
            f"Se esperaban {audit.EXPECTED_PAIRS} predicciones "
            f"y se reconstruyeron {len(records)}."
        )

    # Verificar que la captura cubre todas las categorías y direcciones.
    habitual = [
        r for r in records
        if r["operational_context"] == "funcionamiento_habitual"
    ]

    all_class_direction = nested_summary(
        records,
        lambda r: (r["change_class"], r["direction"]),
        [(c, d) for c in CLASSES for d in DIRECTIONS],
    )

    habitual_class_direction = nested_summary(
        habitual,
        lambda r: (r["change_class"], r["direction"]),
        [(c, d) for c in CLASSES for d in DIRECTIONS],
    )

    context_direction = nested_summary(
        records,
        lambda r: (r["operational_context"], r["direction"]),
        [
            (context, d)
            for context in sorted({
                r["operational_context"] for r in records
            })
            for d in DIRECTIONS
        ],
    )

    global_summary = summarize(records)

    habitual_directions = (
        prior.get("operational_context_by_direction", {})
        .get("funcionamiento_habitual", {})
    )

    expected_habitual = sum(
        group.get("n", 0)
        for group in habitual_directions.values()
    )

    if not isinstance(expected_habitual, int):
        stop("El informe direccional no declara el total habitual.")

    if len(habitual) != expected_habitual:
        stop(
            f"Observaciones habituales: {len(habitual)}; "
            f"esperadas: {expected_habitual}."
        )

    report = {
        "title": "TEOS NEURONA - Frecuencia y concentración de residuos",
        "snapshot_sha256": prior["snapshot_sha256"],
        "raw_prefix_sha256": prior["raw_prefix_sha256"],
        "validation": {
            "directional_audit_reconstructed": True,
            "prospective_predictions": len(records),
            "habitual_observations": len(habitual),
            "same_fixed_models": True,
            "future_data_used_for_training": False,
            "all_valid_observations_preserved": True,
            "previous_reports_modified": False,
            "bitaxe_modified": False,
        },
        "definitions": {
            "residual": "Predicción menos valor real.",
            "overestimation": "Residuo mayor que +1e-9 GH/s.",
            "underestimation": "Residuo menor que -1e-9 GH/s.",
            "tie": "Residuo entre -1e-9 y +1e-9 GH/s.",
            "top_1pct": (
                "Suma del 1% de errores absolutos más grandes, "
                "comparada con la suma de errores del grupo indicado."
            ),
            "contribution": (
                "Porcentaje del error absoluto total explicado "
                "por sobreestimaciones o subestimaciones."
            ),
        },
        "global_all_observations": global_summary,
        "all_contexts_by_variation_and_direction": {
            c: {d: all_class_direction[(c, d)] for d in DIRECTIONS}
            for c in CLASSES
        },
        "habitual_operation_by_variation_and_direction": {
            c: {d: habitual_class_direction[(c, d)] for d in DIRECTIONS}
            for c in CLASSES
        },
        "operational_context_by_direction": {
            context: {
                d: context_direction[(context, d)] for d in DIRECTIONS
            }
            for context in sorted({
                r["operational_context"] for r in records
            })
        },
        "warning": (
            "Desglose descriptivo retrospectivo. No implica causalidad "
            "ni introduce cambios en los modelos."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("\nTEOS NEURONA - FRECUENCIA DE ERRORES")
    print("Predicciones reconstruidas:", len(records))
    print("Funcionamiento habitual:", len(habitual))
    print("Modelos modificados: NO")

    print("\n--- FUNCIONAMIENTO HABITUAL ---")

    for change_class in CLASSES:
        print(f"\n{change_class.upper()}")

        for direction_name in DIRECTIONS:
            group = habitual_class_direction[(change_class, direction_name)]
            reduced = group["ridge_reducido"]
            baseline = group["referencia_1h"]

            if reduced["n"] == 0:
                print(f"  {direction_name}: n=0")
                continue

            print(
                f"  {direction_name}: n={reduced['n']}"
            )

            for name, item in (
                ("Reducido", reduced),
                ("Referencia", baseline),
            ):
                over = item["sobreestimaciones"]
                under = item["subestimaciones"]

                print(
                    f"    {name}: sobre={over['n']} "
                    f"({over['porcentaje_predicciones']:.1f}%) | "
                    f"bajo={under['n']} "
                    f"({under['porcentaje_predicciones']:.1f}%)"
                )
                print(
                    f"      Error total por sobreestimación="
                    f"{over['porcentaje_error_absoluto_total']:.1f}% | "
                    f"Top 1% de sobreestimaciones="
                    f"{over['concentracion_top_1pct_error_del_grupo_pct']}"
                )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("RAW, informes anteriores, modelos y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
