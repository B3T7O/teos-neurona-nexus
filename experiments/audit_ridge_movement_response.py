#!/usr/bin/env python3
"""Sensibilidad del residuo al movimiento real del hashrate."""

import contextlib
import io
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

OUTPUT = ROOT / "experiments/ridge_movement_response_report.json"

captured = {}
original_summarize = audit.summarize


def stop(message):
    raise SystemExit(f"AUDITORÍA DETENIDA: {message}")


def capture(records):
    for record in records:
        captured[id(record)] = dict(record)
    return original_summarize(records)


def regression(records, prediction_field):
    if len(records) < 3:
        return {"n": len(records)}

    change = np.asarray(
        [r["signed_change_ghs"] for r in records],
        dtype=float,
    )
    residual = np.asarray(
        [r[prediction_field] - r["actual"] for r in records],
        dtype=float,
    )

    if np.std(change) < 1e-12:
        return {"n": len(records), "slope": None}

    slope, intercept = np.polyfit(change, residual, 1)
    correlation = float(np.corrcoef(change, residual)[0, 1])

    predicted_residual = intercept + slope * change
    total = float(np.sum((residual - np.mean(residual)) ** 2))
    unexplained = float(np.sum((residual - predicted_residual) ** 2))

    return {
        "n": len(records),
        "pendiente_residuo_vs_cambio": float(slope),
        "intercepto_ghs": float(intercept),
        "correlacion_pearson": correlation,
        "r_squared": (
            float(1 - unexplained / total) if total > 0 else None
        ),
        "cambio_medio_ghs": float(np.mean(change)),
        "sesgo_medio_ghs": float(np.mean(residual)),
        "mae_ghs": float(np.mean(np.abs(residual))),
    }


def main():
    if OUTPUT.exists():
        stop(f"El informe ya existe: {OUTPUT.name}")

    audit.summarize = capture

    try:
        with tempfile.TemporaryDirectory(
            dir=ROOT / "experiments",
            prefix=".tmp_movement_response_",
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
        stop(f"Predicciones reconstruidas: {len(records)}; esperadas: 9922.")

    prospective = __import__("json").loads(
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
    future = [r for r in rows if r["_dt"] > cutoff]

    timeline = [frozen[-2], frozen[-1]] + future
    timeline_index = {
        row["_dt"].isoformat(): i
        for i, row in enumerate(timeline)
    }

    grouped = defaultdict(list)

    for record in records:
        if record["operational_context"] != "funcionamiento_habitual":
            continue

        index = timeline_index.get(record["timestamp"])

        if index is None or index < 2:
            stop("No se pudo alinear una predicción con el RAW.")

        target = timeline[index]
        previous = timeline[index - 1]

        signed_change = (
            float(target["hashRate"]) - float(previous["hashRate"])
        )

        record["signed_change_ghs"] = signed_change

        if signed_change > 1e-9:
            grouped["subida"].append(record)
        elif signed_change < -1e-9:
            grouped["bajada"].append(record)

    report_groups = {}

    for movement in ("subida", "bajada"):
        group = grouped[movement]

        report_groups[movement] = {
            "ridge_reducido": regression(group, "ridge_reducido"),
            "referencia_1h": regression(group, "baseline_1h"),
        }

    report = {
        "title": "TEOS NEURONA - Sensibilidad al movimiento",
        "validation": {
            "prospective_predictions": len(records),
            "habitual_upward_pairs": len(grouped["subida"]),
            "habitual_downward_pairs": len(grouped["bajada"]),
            "fixed_models": True,
            "future_data_used_for_training": False,
            "original_reports_modified": False,
            "raw_modified": False,
            "bitaxe_modified": False,
        },
        "method": (
            "Regresión descriptiva del residuo (predicción menos real) "
            "contra el cambio real entre muestras consecutivas."
        ),
        "groups": report_groups,
        "warning": (
            "Las pendientes y correlaciones describen asociaciones; "
            "no constituyen un nuevo predictor ni prueban causalidad."
        ),
    }

    import json
    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA - RESPUESTA AL MOVIMIENTO")
    print("Predicciones reconstruidas:", len(records))

    for movement, models in report_groups.items():
        print(f"\n--- {movement.upper()} ---")

        for name, result in models.items():
            print(
                f"{name}: n={result['n']} | "
                f"pendiente={result['pendiente_residuo_vs_cambio']:.4f} | "
                f"correlación={result['correlacion_pearson']:.4f} | "
                f"R²={result['r_squared']:.4f} | "
                f"MAE={result['mae_ghs']:.4f} GH/s"
            )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("RAW, modelos y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
