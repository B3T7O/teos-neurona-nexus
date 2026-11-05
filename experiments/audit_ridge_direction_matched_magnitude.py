#!/usr/bin/env python3
"""Comparación de subidas y bajadas con magnitudes equivalentes."""

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

OUTPUT = ROOT / "experiments/ridge_direction_matched_magnitude_report.json"
captured = {}
original_summarize = audit.summarize


def stop(message):
    raise SystemExit(f"AUDITORÍA DETENIDA: {message}")


def capture(records):
    for record in records:
        captured[record["timestamp"]] = dict(record)
    return original_summarize(records)


def metrics(group):
    if not group:
        return {"n": 0}

    actual = np.array([r["actual"] for r in group])
    reduced = np.array([r["ridge_reducido"] for r in group])
    baseline = np.array([r["baseline_1h"] for r in group])
    movement = np.array([r["signed_change_ghs"] for r in group])

    error_reduced = np.abs(reduced - actual)
    error_baseline = np.abs(baseline - actual)
    paired_difference = error_reduced - error_baseline

    return {
        "n": len(group),
        "magnitud_movimiento_mediana_ghs": float(
            np.median(np.abs(movement))
        ),
        "mae_reducido_ghs": float(np.mean(error_reduced)),
        "mae_referencia_ghs": float(np.mean(error_baseline)),
        "diferencia_mae_ghs": float(
            np.mean(paired_difference)
        ),
        "mediana_diferencia_error_emparejado_ghs": float(
            np.median(paired_difference)
        ),
        "victorias_reducido": int(
            np.sum(paired_difference < -1e-9)
        ),
        "derrotas_reducido": int(
            np.sum(paired_difference > 1e-9)
        ),
        "empates": int(
            np.sum(np.abs(paired_difference) <= 1e-9)
        ),
        "sesgo_reducido_ghs": float(np.mean(reduced - actual)),
        "sesgo_referencia_ghs": float(np.mean(baseline - actual)),
    }


def main():
    if OUTPUT.exists():
        stop(f"El informe ya existe: {OUTPUT.name}")

    audit.summarize = capture

    try:
        with tempfile.TemporaryDirectory(
            dir=ROOT / "experiments",
            prefix=".tmp_matched_magnitude_",
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

    records = sorted(
        captured.values(),
        key=lambda r: r["timestamp"],
    )

    if len(records) != audit.EXPECTED_PAIRS:
        stop(f"Predicciones reconstruidas: {len(records)}, esperadas: 9922.")

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
        stop("No coincide la secuencia RAW.")

    timeline = [frozen[-2], frozen[-1]] + future

    index_by_timestamp = {
        row["_dt"].isoformat(): i
        for i, row in enumerate(timeline)
    }

    habitual = []

    for record in records:
        if record["operational_context"] != "funcionamiento_habitual":
            continue

        index = index_by_timestamp.get(record["timestamp"])

        if index is None or index < 2:
            stop("No se pudo alinear una predicción con el RAW.")

        previous = timeline[index - 1]
        signed_change = (
            record["actual"] - float(previous["hashRate"])
        )

        if signed_change > 1e-9:
            record["direction"] = "subida"
        elif signed_change < -1e-9:
            record["direction"] = "bajada"
        else:
            continue

        record["signed_change_ghs"] = signed_change
        habitual.append(record)

    if len(habitual) != 9850:
        stop(f"Movimientos habituales inesperados: {len(habitual)}.")

    # Cuatro intervalos comunes calculados con ambas direcciones.
    magnitudes = np.array([
        abs(r["signed_change_ghs"]) for r in habitual
    ])

    cuts = np.quantile(magnitudes, [0.25, 0.50, 0.75])

    groups = defaultdict(list)

    for record in habitual:
        magnitude = abs(record["signed_change_ghs"])
        quartile = int(np.searchsorted(cuts, magnitude, side="right")) + 1
        groups[(quartile, record["direction"])].append(record)

    report_groups = {}

    for quartile in range(1, 5):
        report_groups[f"cuartil_{quartile}"] = {
            movement: metrics(groups[(quartile, movement)])
            for movement in ("subida", "bajada")
        }

    report = {
        "title": "TEOS NEURONA - Comparación direccional emparejada",
        "validation": {
            "prospective_predictions": len(records),
            "habitual_directional_pairs": len(habitual),
            "same_fixed_models": True,
            "future_data_used_for_training": False,
            "previous_reports_modified": False,
        },
        "method": {
            "common_magnitude_quartiles": True,
            "cutpoints_ghs": [float(x) for x in cuts],
            "magnitude_population": "Subidas y bajadas habituales combinadas",
            "paired_comparison": (
                "Error absoluto Ridge reducido menos error absoluto referencia."
            ),
        },
        "groups": report_groups,
        "warning": (
            "Comparación descriptiva retrospectiva. No demuestra causalidad "
            "ni modifica los modelos."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA - MAGNITUDES EMPAREJADAS")
    print("Predicciones:", len(records))
    print("Movimientos habituales:", len(habitual))
    print("Límites comunes:", [round(float(x), 3) for x in cuts])

    for quartile, groups_result in report_groups.items():
        print(f"\n{quartile.upper()}")

        for movement, result in groups_result.items():
            print(
                f"{movement}: n={result['n']} | "
                f"MAE reducido={result['mae_reducido_ghs']:.3f} | "
                f"referencia={result['mae_referencia_ghs']:.3f} | "
                f"diferencia={result['diferencia_mae_ghs']:+.3f} GH/s"
            )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("RAW, informes, modelos y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
