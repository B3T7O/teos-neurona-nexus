#!/usr/bin/env python3
"""Localiza los errores individuales más influyentes de Ridge reducido."""

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import audit_ridge_residual_direction as direction

audit = direction.audit
ev = audit.ev

captured = {}
original_summarize = audit.summarize


def capture(records):
    for record in records:
        captured[id(record)] = dict(record)
    return original_summarize(records)


def stop(message):
    raise SystemExit(f"INSPECCIÓN DETENIDA: {message}")


def fields(row):
    names = (
        "hashRate", "hashRate_1m", "hashRate_10m", "hashRate_1h",
        "power", "temp", "vrTemp", "frequency",
        "sharesAccepted", "uptimeSeconds", "errorPercentage",
    )
    return {name: row.get(name) for name in names}


def main():
    audit.summarize = capture

    try:
        with tempfile.TemporaryDirectory(
            dir=ROOT / "experiments",
            prefix=".tmp_outlier_inspection_",
        ) as temporary:
            previous_output = direction.OUTPUT
            direction.OUTPUT = Path(temporary) / "rebuild.json"

            try:
                with redirect_stdout(io.StringIO()):
                    direction.main()
            finally:
                direction.OUTPUT = previous_output
    finally:
        audit.summarize = original_summarize

    records = list(captured.values())
    if len(records) != audit.EXPECTED_PAIRS:
        stop(f"Se capturaron {len(records)} predicciones, no {audit.EXPECTED_PAIRS}.")

    if any("timestamp" not in r for r in records):
        stop("Faltan marcas temporales en las predicciones.")

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
    future = [r for r in rows if r["_dt"] > frozen[-1]["_dt"]]
    timeline = [frozen[-2], frozen[-1]] + future
    timeline_index = {
        row["_dt"].isoformat(): i
        for i, row in enumerate(timeline)
    }

    candidates = []

    for record in records:
        index = timeline_index.get(record["timestamp"])
        if index is None or index < 2:
            stop("No se pudo asociar una predicción con su telemetría.")

        target = timeline[index]
        previous = timeline[index - 1]
        earlier = timeline[index - 2]

        if (
            record["operational_context"] != "funcionamiento_habitual"
            or record["change_class"] != "variacion_baja"
            or record["direction"] != "bajada"
        ):
            continue

        actual = record["actual"]
        reduced = record["ridge_reducido"]
        baseline = record["baseline_1h"]

        reduced_error = abs(reduced - actual)
        baseline_error = abs(baseline - actual)

        candidates.append({
            "index": index,
            "timestamp": target["_dt"].isoformat(),
            "actual": actual,
            "reduced": reduced,
            "baseline": baseline,
            "reduced_residual": reduced - actual,
            "baseline_residual": baseline - actual,
            "reduced_error": reduced_error,
            "baseline_error": baseline_error,
            "excess_error": reduced_error - baseline_error,
            "change": record["absolute_change_ghs"],
            "interval": record["interval_seconds"],
            "target_data": fields(target),
            "previous_data": fields(previous),
            "earlier_data": fields(earlier),
        })

    if not candidates:
        stop("No se encontraron registros en el grupo solicitado.")

    ranked = sorted(
        candidates,
        key=lambda r: r["excess_error"],
        reverse=True,
    )

    group_excess = sum(r["excess_error"] for r in candidates)
    top = ranked[:5]

    print("TEOS NEURONA - INSPECCIÓN DE ERRORES EXTREMOS")
    print("Grupo: funcionamiento habitual / variación baja / bajada")
    print("Observaciones:", len(candidates))
    print(
        "Diferencia acumulada de error absoluto reducido - referencia:",
        f"{group_excess:.4f} GH/s",
    )

    print("\n--- CINCO REGISTROS CON MAYOR PERJUICIO PARA RIDGE REDUCIDO ---")

    for rank, item in enumerate(top, 1):
        print(f"\nREGISTRO {rank}")
        print("UTC:", item["timestamp"])
        print(f"Hashrate real: {item['actual']:.4f} GH/s")
        print(f"Ridge reducido: {item['reduced']:.4f} GH/s")
        print(f"Referencia 1h: {item['baseline']:.4f} GH/s")
        print(f"Residuo reducido: {item['reduced_residual']:+.4f} GH/s")
        print(f"Residuo referencia: {item['baseline_residual']:+.4f} GH/s")
        print(f"Exceso de error reducido: {item['excess_error']:+.4f} GH/s")
        print(f"Cambio real entre muestras: {item['change']:.4f} GH/s")
        print(f"Intervalo: {item['interval']:.2f} segundos")

        print("Telemetría objetivo:", item["target_data"])
        print("Telemetría muestra anterior:", item["previous_data"])
        print("Telemetría dos muestras anteriores:", item["earlier_data"])

    if group_excess > 0:
        contribution = top[0]["excess_error"] / group_excess * 100
        print(
            "\nContribución del registro más perjudicial "
            "a la diferencia acumulada:",
            f"{contribution:.2f}%",
        )

    print("\nRAW, informes anteriores, modelos y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
