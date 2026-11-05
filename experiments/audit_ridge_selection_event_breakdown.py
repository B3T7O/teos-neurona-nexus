#!/usr/bin/env python3
"""Descompone el rendimiento del selector en los eventos conocidos."""

import contextlib
import io
import json
import math
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import audit_ridge_residual_direction_extended as direction

audit = direction.audit
ev = audit.ev

OUTPUT = ROOT / "experiments/ridge_selection_event_breakdown_report.json"
SELECTOR_REPORT = ROOT / "experiments/ridge_predictor_selection_report.json"

captured = {}
original_summarize = audit.summarize


def stop(message):
    raise SystemExit(f"AUDITORÍA DETENIDA: {message}")


def capture(records):
    for record in records:
        captured[record["timestamp"]] = dict(record)
    return original_summarize(records)


def metrics(records, policy):
    if not records:
        return {"n": 0}

    actual = [r["actual"] for r in records]
    predictions = []

    for r in records:
        if policy == "ridge_reducido":
            prediction = r["ridge_reducido"]
        elif policy == "referencia_1h":
            prediction = r["baseline_1h"]
        elif policy == "seleccion_tendencia_previa":
            prediction = (
                r["ridge_reducido"]
                if r["past_delta_hashRate"] > 1e-9
                else r["baseline_1h"]
            )
        else:
            stop(f"Política desconocida: {policy}")

        predictions.append(prediction)

    residuals = [
        prediction - real
        for prediction, real in zip(predictions, actual)
    ]

    return {
        "n": len(records),
        "mae_ghs": sum(abs(x) for x in residuals) / len(residuals),
        "rmse_ghs": math.sqrt(
            sum(x*x for x in residuals) / len(residuals)
        ),
        "bias_ghs": sum(residuals) / len(residuals),
    }


def verify_metrics(current, reference, label):
    if current["n"] != reference["n"]:
        stop(f"{label}: cantidad de muestras diferente.")

    for field in ("mae_ghs", "rmse_ghs"):
        if not math.isclose(
            current[field],
            reference[field],
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            stop(f"{label}: no se reproduce {field}.")


def main():
    if OUTPUT.exists():
        stop(f"El informe ya existe: {OUTPUT.name}")

    if not SELECTOR_REPORT.is_file():
        stop("Falta el informe previo del selector.")

    # Reconstrucción de las mismas predicciones.
    audit.summarize = capture

    try:
        with tempfile.TemporaryDirectory(
            dir=ROOT / "experiments",
            prefix=".tmp_event_breakdown_",
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

    if len(records) != 9922:
        stop(f"Predicciones reconstruidas: {len(records)}, esperadas: 9922.")

    prospective = json.loads(
        audit.PROSPECTIVE.read_text(encoding="utf-8")
    )
    event_report = json.loads(
        audit.EVENT_REPORT.read_text(encoding="utf-8")
    )
    selector_report = json.loads(
        SELECTOR_REPORT.read_text(encoding="utf-8")
    )

    # Recuperación del RAW histórico verificado.
    frozen, snapshot_hash = ev.load_frozen()

    if prospective["integrity"]["snapshot_sha256"] != snapshot_hash:
        stop("La fotografía prospectiva no coincide.")

    if event_report.get("snapshot_sha256") != snapshot_hash:
        stop("El informe de eventos usa otra fotografía.")

    if event_report.get("raw_sha256") != prospective["integrity"]["raw_sha256"]:
        stop("El informe de eventos usa otro prefijo RAW.")

    if selector_report.get("results", {}).get(
        "global_todas_las_muestras", {}
    ).get("referencia_1h", {}).get("n") != 9922:
        stop("El informe del selector no contiene las 9922 muestras.")

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
        stop("La secuencia RAW no coincide.")

    timeline = [frozen[-2], frozen[-1]] + future

    timeline_index = {
        row["_dt"].isoformat(): i
        for i, row in enumerate(timeline)
    }

    # Clasificación temporal de los dos eventos.
    windows = {
        name: (
            ev.parse_timestamp(window["start"]),
            ev.parse_timestamp(window["end"]),
        )
        for name, window in event_report["event_windows_utc"].items()
    }

    groups = defaultdict(list)

    for record in records:
        timestamp = ev.parse_timestamp(record["timestamp"])
        index = timeline_index.get(record["timestamp"])

        if index is None or index < 2:
            stop("No se pudo reconstruir el contexto anterior.")

        previous = timeline[index - 1]
        earlier = timeline[index - 2]

        record["past_delta_hashRate"] = (
            float(previous["hashRate"]) - float(earlier["hashRate"])
        )

        matching = [
            name for name, (start, end) in windows.items()
            if start <= timestamp <= end
        ]

        if len(matching) > 1:
            stop("Una muestra pertenece a más de un evento.")

        context = (
            matching[0]
            if matching
            else "funcionamiento_habitual"
        )

        groups[context].append(record)

    expected_counts = {
        "anomalia_telemetria_22_octubre": 61,
        "reinicio_bitaxe_29_octubre": 3,
        "funcionamiento_habitual": 9858,
    }

    for name, expected in expected_counts.items():
        if len(groups[name]) != expected:
            stop(
                f"{name}: se encontraron {len(groups[name])}, "
                f"esperadas {expected}."
            )

    if sum(map(len, groups.values())) != len(records):
        stop("La partición de eventos no conserva todas las muestras.")

    policies = (
        "ridge_reducido",
        "referencia_1h",
        "seleccion_tendencia_previa",
    )

    results = {
        name: {
            policy: metrics(group, policy)
            for policy in policies
        }
        for name, group in groups.items()
    }

    # Comprobar que los resultados globales y habituales del selector
    # siguen reproduciendo el informe previo.
    previous = selector_report["results"]

    for policy in policies:
        verify_metrics(
            metrics(records, policy),
            previous["global_todas_las_muestras"][policy],
            f"Global {policy}",
        )
        verify_metrics(
            metrics(groups["funcionamiento_habitual"], policy),
            previous["funcionamiento_habitual"][policy],
            f"Habitual {policy}",
        )

    report = {
        "title": "TEOS NEURONA - Selector por episodio operativo",
        "snapshot_sha256": snapshot_hash,
        "validation": {
            "prospective_predictions": len(records),
            "event_and_habitual_counts_verified": True,
            "selector_previous_metrics_reproduced": True,
            "same_fixed_models": True,
            "future_data_used_for_training": False,
            "previous_reports_modified": False,
            "raw_modified": False,
            "bitaxe_modified": False,
        },
        "groups": results,
        "warning": (
            "Los grupos de eventos son análisis retrospectivos. "
            "El episodio del reinicio contiene solo tres muestras; "
            "sus métricas no permiten generalizaciones."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA - SELECTOR POR EVENTO")
    print("Predicciones:", len(records))

    for context, group in results.items():
        print(f"\n{context}: n={group['ridge_reducido']['n']}")

        for policy, item in group.items():
            print(
                f"{policy}: MAE={item['mae_ghs']:.4f} | "
                f"RMSE={item['rmse_ghs']:.4f} | "
                f"sesgo={item['bias_ghs']:+.4f} GH/s"
            )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("RAW, informes anteriores, modelos y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
