#!/usr/bin/env python3
"""Seguimiento del error según magnitud de las bajadas."""

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import audit_ridge_residual_direction_extended as direction

audit = direction.audit
OUTPUT = ROOT / "experiments/ridge_downward_tracking_report.json"
captured = {}
original_summarize = audit.summarize


def capture(records):
    for record in records:
        captured[id(record)] = dict(record)
    return original_summarize(records)


def stop(message):
    raise SystemExit(f"AUDITORÍA DETENIDA: {message}")


def summarize(group):
    if not group:
        return {"n": 0}

    actual = np.array([r["actual"] for r in group])
    reduced = np.array([r["ridge_reducido"] for r in group])
    baseline = np.array([r["baseline_1h"] for r in group])
    drops = np.array([r["absolute_change_ghs"] for r in group])

    rr = reduced - actual
    rb = baseline - actual

    return {
        "n": len(group),
        "caida_mediana_ghs": float(np.median(drops)),
        "caida_p90_ghs": float(np.percentile(drops, 90)),
        "mae_reducido_ghs": float(np.mean(np.abs(rr))),
        "mae_referencia_ghs": float(np.mean(np.abs(rb))),
        "diferencia_mae_ghs": float(
            np.mean(np.abs(rr)) - np.mean(np.abs(rb))
        ),
        "sesgo_reducido_ghs": float(np.mean(rr)),
        "sesgo_referencia_ghs": float(np.mean(rb)),
        "sobreestimacion_reducido_pct": float(
            np.mean(rr > 1e-9) * 100
        ),
        "sobreestimacion_referencia_pct": float(
            np.mean(rb > 1e-9) * 100
        ),
    }


def main():
    if OUTPUT.exists():
        stop(f"El informe ya existe: {OUTPUT.name}")

    audit.summarize = capture

    try:
        with tempfile.TemporaryDirectory(
            dir=ROOT / "experiments",
            prefix=".tmp_downward_",
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
        stop(f"Se capturaron {len(records)} registros, no 9922.")

    habitual_down = [
        r for r in records
        if r["operational_context"] == "funcionamiento_habitual"
        and r["direction"] == "bajada"
    ]

    if len(habitual_down) != 4938:
        stop(
            f"Bajadas habituales inesperadas: {len(habitual_down)}."
        )

    # Cuatro grupos equilibrados según la caída real por muestra.
    ordered = np.argsort(
        [r["absolute_change_ghs"] for r in habitual_down],
        kind="stable",
    )
    quartiles = np.array_split(ordered, 4)

    groups = {}

    for number, indices in enumerate(quartiles, 1):
        group = [habitual_down[int(i)] for i in indices]
        groups[f"cuartil_{number}"] = summarize(group)

    report = {
        "title": "TEOS NEURONA - Seguimiento de bajadas",
        "validation": {
            "prospective_pairs": len(records),
            "habitual_downward_pairs": len(habitual_down),
            "same_fixed_models": True,
            "future_data_used_for_training": False,
            "previous_reports_modified": False,
        },
        "method": (
            "Cuatro grupos equilibrados ordenados por magnitud "
            "de la caída real entre muestras consecutivas."
        ),
        "groups": groups,
        "warning": (
            "Análisis retrospectivo descriptivo. No demuestra "
            "causalidad ni modifica los predictores."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA - SEGUIMIENTO DE BAJADAS")
    print("Pares habituales de bajada:", len(habitual_down))

    for name, result in groups.items():
        print(f"\n{name}: n={result['n']}")
        print(
            f"Caída mediana={result['caida_mediana_ghs']:.3f} GH/s"
        )
        print(
            f"MAE reducido={result['mae_reducido_ghs']:.3f} | "
            f"referencia={result['mae_referencia_ghs']:.3f} GH/s"
        )
        print(
            f"Diferencia MAE={result['diferencia_mae_ghs']:+.3f} GH/s"
        )
        print(
            f"Sesgo reducido={result['sesgo_reducido_ghs']:+.3f} GH/s"
        )
        print(
            f"Sobreestimaciones reducido="
            f"{result['sobreestimacion_reducido_pct']:.1f}%"
        )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("Modelos, RAW y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
