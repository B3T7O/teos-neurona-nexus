#!/usr/bin/env python3
"""Sensibilidad de Ridge prospectivo frente a eventos de telemetría."""

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import evaluate_ridge_prospective as ev

SNAPSHOT = ROOT / "experiments/frozen_bitaxe_samples.jsonl"
SCRIPT = ROOT / "experiments/first_learning_model.py"
ORIGINAL = ROOT / "experiments/first_learning_model_report.json"
PROSPECTIVE = ROOT / "experiments/ridge_prospective_report.json"

OUTPUT = ROOT / "experiments/ridge_prospective_event_impact_extended_report.json"

EXPECTED = {
    SNAPSHOT: "dfdd8f2533d89190e94f5ef113c2a24a43325df1d51c93ad810ff417b53379a5",
    SCRIPT: "b1e1a69fd272c09574a89ac866918889065fab5746ed214b98bdd6eaf8bdab7d",
    ORIGINAL: "835002b3e7720fcbf9c6d0b6ad450a86ff474d01bf5126aaf75c8d8dc9a752ba",
}

EVENTS = {
    "anomalia_telemetria_22_octubre": (
        "2026-10-22T22:35:46.909234+00:00",
        "2026-10-22T23:41:23.930744+00:00",
    ),
    "reinicio_bitaxe_29_octubre": (
        "2026-10-29T02:07:54.967364+00:00",
        "2026-10-29T02:10:01.696459+00:00",
    ),
}

TOLERANCE = 1e-10

RAW_PREFIX_BYTES = 6763269


def load_original_raw_prefix(cutoff, expected_hash):
    data = ev.RAW.read_bytes()

    if len(data) < RAW_PREFIX_BYTES:
        stop("RAW demasiado corto para recuperar el prefijo original.")

    prefix = data[:RAW_PREFIX_BYTES]
    prefix_hash = hashlib.sha256(prefix).hexdigest()

    if prefix_hash != expected_hash:
        stop("El prefijo RAW no coincide con el hash prospectivo original.")

    by_time = {}
    invalid = 0
    duplicates = 0

    for line in prefix.splitlines():
        try:
            row = json.loads(line)
            dt = ev.parse_timestamp(row.get("timestamp"))
            hr = row.get("hashRate")

            if not ev.valid_number(hr):
                invalid += 1
                continue

            row["_dt"] = dt

            if dt in by_time:
                duplicates += 1

            by_time[dt] = row

        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            invalid += 1

    ordered = sorted(by_time.items())
    historical = [row for dt, row in ordered if dt <= cutoff]
    future = [row for dt, row in ordered if dt > cutoff]

    return historical, future, invalid, duplicates, prefix_hash




def stop(message):
    raise SystemExit(f"AUDITORÍA DETENIDA: {message}")


def verify_metrics(current, previous, label):
    if current["n"] != previous["n"]:
        stop(f"{label}: cantidad de muestras diferente.")

    for key in ("mae_ghs", "rmse_ghs"):
        if not math.isclose(
            current[key], previous[key],
            rel_tol=TOLERANCE, abs_tol=TOLERANCE
        ):
            stop(f"{label}: no coincide {key}.")


def error_contribution(group, all_records):
    methods = {
        "ridge_original": "ridge_original",
        "ridge_reducido": "ridge_reducido",
        "referencia_1h": "baseline_1h",
    }

    result = {}

    for name, field in methods.items():
        group_abs = sum(
            abs(r["actual"] - r[field]) for r in group
        )
        total_abs = sum(
            abs(r["actual"] - r[field]) for r in all_records
        )

        group_sq = sum(
            (r["actual"] - r[field]) ** 2 for r in group
        )
        total_sq = sum(
            (r["actual"] - r[field]) ** 2 for r in all_records
        )

        result[name] = {
            "absolute_error_contribution_pct": (
                group_abs / total_abs * 100 if total_abs else None
            ),
            "squared_error_contribution_pct": (
                group_sq / total_sq * 100 if total_sq else None
            ),
        }

    return result


def summarize(group, all_records):
    if not group:
        return {"n": 0}

    return {
        **ev.compare_methods(group),
        "error_contribution": error_contribution(group, all_records),
    }


def main():
    required = [
        SNAPSHOT, SCRIPT, ORIGINAL, PROSPECTIVE,
        ev.MANIFEST, ev.CANDIDATE, ev.RAW,
    ]

    for path in required:
        if not path.is_file():
            stop(f"Falta {path.name}.")

    if OUTPUT.exists():
        stop("El informe ya existe. No se sobrescribió.")

    # Verificación de archivos históricos.
    for path, expected in EXPECTED.items():
        if ev.sha256_file(path) != expected:
            stop(f"SHA-256 inesperado: {path.name}")

    previous_report = json.loads(
        PROSPECTIVE.read_text(encoding="utf-8")
    )

    frozen, snapshot_hash = ev.load_frozen()

    if snapshot_hash != previous_report["integrity"]["snapshot_sha256"]:
        stop("La fotografía congelada no coincide.")


    # Importamos y reutilizamos exactamente el procedimiento prospectivo.
    manifest = json.loads(ev.MANIFEST.read_text(encoding="utf-8"))
    original = json.loads(ev.ORIGINAL.read_text(encoding="utf-8"))
    candidate = json.loads(ev.CANDIDATE.read_text(encoding="utf-8"))

    if manifest.get("sha256") != snapshot_hash:
        stop("Manifiesto no coincidente.")

    if original.get("snapshot_sha256") != snapshot_hash:
        stop("Informe original no coincidente.")

    if candidate.get("integrity", {}).get("snapshot_sha256") != snapshot_hash:
        stop("Candidato reducido no coincidente.")

    cutoff = frozen[-1]["_dt"]

    train_x, train_y = [], []

    for i in range(2, len(frozen)):
        x = ev.feature_at(frozen[i - 1], frozen[i - 2])
        target = frozen[i]["_target"]
        baseline = frozen[i - 1].get("hashRate_1h")

        if x is None or not math.isfinite(target) or not ev.valid_number(baseline):
            continue

        train_x.append(x)
        train_y.append(target)

    train_x = np.asarray(train_x, dtype=float)
    train_y = np.asarray(train_y, dtype=float)

    if len(train_y) != original["usable_samples"]:
        stop("No coincide el entrenamiento congelado.")

    historical, future, invalid, duplicates, raw_hash = (
        load_original_raw_prefix(
            cutoff,
            previous_report["integrity"]["raw_sha256"],
        )
    )

    if raw_hash != previous_report["integrity"]["raw_sha256"]:
        stop("Cambió el contenido RAW.")

    ev.verify_context(frozen, historical)

    # Reconstrucción de las predicciones futuras con pesos fijos.
    stream = [frozen[-2], frozen[-1]] + future

    test_x, actual, baseline = [], [], []
    intervals, timestamps = [], []

    for i in range(2, len(stream)):
        previous = stream[i - 1]
        earlier = stream[i - 2]
        target = stream[i]

        x = ev.feature_at(previous, earlier)
        y = target.get("hashRate")
        base = previous.get("hashRate_1h")
        interval = (target["_dt"] - previous["_dt"]).total_seconds()

        if (
            x is None
            or not ev.valid_number(y)
            or not ev.valid_number(base)
            or interval <= 0
        ):
            continue

        test_x.append(x)
        actual.append(float(y))
        baseline.append(float(base))
        intervals.append(interval)
        timestamps.append(target["_dt"])

    test_x = np.asarray(test_x, dtype=float)
    actual = np.asarray(actual, dtype=float)
    baseline = np.asarray(baseline, dtype=float)

    full_indices = np.arange(len(ev.FEATURES))
    reduced_indices = np.asarray([
        ev.FEATURES.index(f) for f in ev.REDUCED_FEATURES
    ])

    prediction_original = ev.fit_predict(
        train_x, train_y, test_x, full_indices
    )
    prediction_reduced = ev.fit_predict(
        train_x, train_y, test_x, reduced_indices
    )

    records = []

    for i, timestamp in enumerate(timestamps):
        records.append({
            "timestamp": timestamp,
            "actual": float(actual[i]),
            "ridge_original": float(prediction_original[i]),
            "ridge_reducido": float(prediction_reduced[i]),
            "baseline_1h": float(baseline[i]),
        })

    if len(records) != previous_report["validation"]["valid_future_pairs"]:
        stop("No coincide el número de pares prospectivos.")

    # Validar que reproducimos las métricas oficiales.
    global_result = ev.compare_methods(records)

    for method in ("ridge_original", "ridge_reducido", "referencia_1h"):
        verify_metrics(
            global_result[method],
            previous_report["global"][method],
            method,
        )

    # Clasificar episodios sin eliminar observaciones del resultado global.
    event_ranges = {
        name: (
            ev.parse_timestamp(start),
            ev.parse_timestamp(end),
        )
        for name, (start, end) in EVENTS.items()
    }

    groups = {name: [] for name in EVENTS}
    groups["resto_sin_eventos"] = []

    for record in records:
        timestamp = record["timestamp"]
        matched = False

        for name, (start, end) in event_ranges.items():
            if start <= timestamp <= end:
                groups[name].append(record)
                matched = True
                break

        if not matched:
            groups["resto_sin_eventos"].append(record)

    if sum(len(x) for x in groups.values()) != len(records):
        stop("La clasificación temporal perdió o duplicó muestras.")

    report = {
        "title": "TEOS NEURONA — Impacto de anomalías en evaluación prospectiva",
        "snapshot_sha256": snapshot_hash,
        "raw_sha256": raw_hash,
        "validation": {
            "original_prospective_metrics_reproduced": True,
            "same_future_targets": True,
            "all_records_preserved_in_global_result": True,
            "event_groups_partition_all_records": True,
            "models_retrained": False,
            "original_files_modified": False,
        },
        "event_windows_utc": {
            name: {"start": start, "end": end}
            for name, (start, end) in EVENTS.items()
        },
        "global_official_all_samples": summarize(records, records),
        "sensitivity_groups": {
            name: summarize(group, records)
            for name, group in groups.items()
        },
        "counts": {
            name: len(group) for name, group in groups.items()
        },
        "warning": (
            "El resultado global conserva todas las muestras. "
            "La sección resto_sin_eventos es únicamente un análisis "
            "de sensibilidad y no sustituye la métrica oficial. "
            "Las ventanas se basan en los episodios observados."
        ),
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("TEOS NEURONA — IMPACTO DE EVENTOS")
    print("Reproducción prospectiva original: SUPERADA")
    print("Pares conservados:", len(records))
    print("Pesos fijos: sí")

    for name, group in report["sensitivity_groups"].items():
        print(f"\n{name}: n={group['n']}")

        if group["n"]:
            for method in (
                "ridge_original", "ridge_reducido", "referencia_1h"
            ):
                item = group[method]
                share = group["error_contribution"][method][
                    "absolute_error_contribution_pct"
                ]
                print(
                    f"{method}: MAE={item['mae_ghs']:.4f} GH/s | "
                    f"aporte al error global={share:.2f}%"
                )

    print("\nInforme:", OUTPUT.relative_to(ROOT))
    print("Datos, modelos y Bitaxe: intactos.")


if __name__ == "__main__":
    main()
